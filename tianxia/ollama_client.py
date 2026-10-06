"""跟本機 Ollama 溝通的輕量 client，供 companion_agent.py 使用。

從 ai_story（征服路線引擎）的 src/ollama_client.py 移植並精簡：拿掉串流版本
（tianxia 這邊規模小、同步呼叫可接受，見設計文件八.1），保留已經驗證過的可靠度機制——
JSON schema 用完整 schema（而非字串 "json"）啟用文法約束解碼、截斷 JSON 的修復、
options 類欄位缺席時視為失敗觸發 re-prompt 重試。
"""
from __future__ import annotations

import copy
import json
import logging
import re
from typing import TYPE_CHECKING, Any, Type, TypeVar

import requests
from pydantic import BaseModel, ValidationError

if TYPE_CHECKING:
    from .models import Config

T = TypeVar("T", bound=BaseModel)

logger = logging.getLogger(__name__)


def _trim_schema_properties(schema: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    trimmed = dict(schema)
    trimmed["properties"] = {k: v for k, v in schema.get("properties", {}).items() if k in fields}
    return trimmed


def clean_json_text(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start_idx = text.find("{")
    end_idx = text.rfind("}")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        text = text[start_idx:end_idx + 1]
    return text


def repair_truncated_json(s: str) -> str:
    s = s.strip()
    start_idx = s.find("{")
    if start_idx != -1:
        s = s[start_idx:]
    s = re.sub(r",\s*$", "", s)
    s = re.sub(r":\s*$", ': ""', s)
    in_string = False
    escape = False
    stack = []
    for char in s:
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if not in_string:
            if char in "{[":
                stack.append(char)
            elif char in "}]":
                if stack:
                    stack.pop()
    if in_string:
        s += '"'
    while stack:
        top = stack.pop()
        s += "}" if top == "{" else "]"
    return s


def parse_json_robustly(text: str) -> dict:
    cleaned = clean_json_text(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    fixed = re.sub(r",\s*([\}\]])", r"\1", cleaned)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass
    fixed_newlines = re.sub(r"(?<!\\)\n", r"\\n", cleaned)
    fixed_newlines = re.sub(r",\s*([\}\]])", r"\1", fixed_newlines)
    try:
        return json.loads(fixed_newlines)
    except json.JSONDecodeError:
        pass
    repaired = repair_truncated_json(cleaned)
    repaired_clean = re.sub(r",\s*([\}\]])", r"\1", repaired)
    return json.loads(repaired_clean)


def _ensure_required_present(data: dict, response_model: type, required: list[str]) -> None:
    """呼叫端指定「這個 schema 缺這個欄位就視同截斷失敗」的欄位清單（見 ai_story 對
    options 欄位踩過的坑：GameStateDelta.options 有 default_factory，Pydantic 驗證
    不會報錯，會靜默套用寫死的預設清單）。

    判斷的是「沒有這個鍵／是 None／是空的容器或字串」，**不是 falsy**：`success_rate: 0`
    是完全合法的答案（防灌水的提示詞就是要模型對「我必定成功」這類寫法給 0~10），
    以前用 `not data.get(name)` 會把它當成截斷丟掉、重試再拿到 0 再丟一次，最後退回
    保底 40——比正常評出來的低分還高，等於把最該壓低的寫法往上抬。"""
    fields = getattr(response_model, "model_fields", {})
    for name in required:
        if name not in fields:
            continue
        value = data.get(name)
        empty = value is None or (isinstance(value, (str, bytes, list, tuple, set, dict)) and len(value) == 0)
        if empty:
            raise ValueError(f"LLM 回應缺少必要欄位 {name!r}，疑似被截斷")


class ModelGaveUp(RuntimeError):
    """這一次拿鎖期間已經有一次模型呼叫逾時或失敗了：之後的呼叫不送出去，各處照例走退路的固定文字。"""


class ModelBudget:
    """行動鎖內的模型「額度」：一次拿鎖的期間，只要有一次模型呼叫逾時或失敗，gave_up 就設起來，之後鎖內的模型呼叫一律不送
    （引擎不讀時鐘，靠這面旗子就夠）。由 Game 持有，server._locked 與 bot_runner._bot_game 每次拿到鎖先歸零（Game.reset_model_budget）。"""

    def __init__(self) -> None:
        self.gave_up = False


class InLockClient:
    """鎖內呼叫端拿到的 client：包著一個短逾時、不重問的複本，並看著 ModelBudget——額度用完（這次拿鎖期間已經有一次失敗）
    就不送、直接丟 ModelGaveUp；這一次呼叫失敗就把額度設成用完。其他欄位（timeout、retry、base_url、model……）讀的是裡面那個複本。
    呼叫端（flavor、battle_instance、event_llm、companion_agent、naming）本來就把任何例外當作「沒取到」走退路，不必改。"""

    def __init__(self, client: Any, budget: ModelBudget) -> None:
        self._client = client
        self._budget = budget

    def __getattr__(self, name: str) -> Any:
        if name in ("_client", "_budget"):  # 還沒 __init__ 完（copy、pickle）時別遞迴
            raise AttributeError(name)
        return getattr(self._client, name)

    def chat_text(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("chat_text", args, kwargs)

    def chat_structured(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("chat_structured", args, kwargs)

    def _call(self, method: str, args: tuple, kwargs: dict) -> Any:
        if self._budget.gave_up:
            raise ModelGaveUp("這一次拿鎖期間已經有一次模型呼叫失敗，這一次不再叫模型")
        try:
            return getattr(self._client, method)(*args, **kwargs)
        except Exception:
            self._budget.gave_up = True
            raise


def capped(client: Any, seconds: int | float, retry: bool | None = None) -> Any:
    """client 的複本，HTTP 逾時最多 seconds 秒（client 自己的逾時比較短就用它的；沒有 timeout 欄位的假物件就是 seconds）；
    retry 給了就一併設上。原本的 client 不動（同一個角色別的請求可能正在用它）。鎖內的 quick_client、鎖外照預算分的
    naming.propose、fight_llm.judge、server.within_budget、悟意境取名的一趟都用它。"""
    copied = copy.copy(client)
    own = getattr(client, "timeout", None)
    copied.timeout = min(float(own), seconds) if isinstance(own, (int, float)) else seconds
    if retry is not None:
        copied.retry = retry
    return copied


def quick_client(client: Any, seconds: int | float, budget: ModelBudget) -> Any:
    """行動鎖內叫模型用的 client（Game._quick_client）：client 的複本，HTTP 逾時最多 seconds 秒、不重問（retry=False：
    chat_structured 失敗直接丟出第一次的例外，不再多送一趟），外面包一層 InLockClient 看 budget。這樣鎖內任何一步模型呼叫
    最多等 seconds 秒，這次拿鎖期間第一次失敗之後的呼叫都不送。沒有 client（None，伺服器假人）、或這次拿鎖期間額度已經用完
    就是 None，呼叫端本來就把 None 當成不叫模型。原本的 client 不動（同一個角色鎖外的請求在用它，照舊有自己的逾時與重問）。
    引擎不讀時鐘（CLAUDE.md），上限靠 HTTP 的逾時，跟 naming.propose 同一個做法。拿簡單的假物件（沒有 timeout 欄位）當 client
    的測試與腳本也一樣給複本、設上上限。"""
    if client is None or budget.gave_up:
        return None
    return InLockClient(capped(client, seconds, retry=False), budget)


class OllamaClient:
    def __init__(
        self, base_url: str = "http://localhost:11434", model: str = "qwen2.5:14b",
        timeout: int = 120, context_length: int = 8192, think: bool | None = None, keep_alive: str = "30m",
        repeat_penalty: float = 1.18, presence_penalty: float = 0.3, frequency_penalty: float = 0.3,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.context_length = context_length
        self.think = think  # None：不送 think 欄位（沒有思考模式的模型）
        self.keep_alive = keep_alive
        self.repeat_penalty = repeat_penalty
        self.presence_penalty = presence_penalty
        self.frequency_penalty = frequency_penalty
        # chat_structured 失敗（逾時、格式不對）時要不要再問一趟：預設要；行動鎖內用的複本設成 False（見 quick_client），
        # 一次呼叫最多只送一趟，失敗就丟出那一次的例外讓呼叫端走退路
        self.retry = True

    @classmethod
    def from_config(cls, cfg: Config) -> OllamaClient:
        """照設定建一個 client（Game 與伺服器假人程式共用同一套參數）。"""
        return cls(
            base_url=cfg.ollama_url, model=cfg.ollama_model, timeout=cfg.ollama_timeout, think=cfg.ollama_think,
            keep_alive=cfg.ollama_keep_alive, repeat_penalty=cfg.ollama_repeat_penalty,
            presence_penalty=cfg.ollama_presence_penalty, frequency_penalty=cfg.ollama_frequency_penalty,
        )

    def warm(self, seconds: float = 2.0) -> bool:
        """叫 Ollama 把模型載起來（/api/generate 只帶 model 與 keep_alive，不產生任何字），不等它載完：
        逾時（模型還在載）也算送到了。悟意境的畫布一出現就送（insight_llm.warm）。連不上回 False。"""
        try:
            requests.post(
                f"{self.base_url}/api/generate", json={"model": self.model, "keep_alive": self.keep_alive}, timeout=seconds,
            )
        except requests.Timeout:
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Ollama 暖機失敗: {e}")
            return False
        return True

    def _build_payload(
        self, messages: list[dict[str, str]], temperature: float, num_predict: int = 1024,
        json_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": temperature,
                "repeat_penalty": self.repeat_penalty,
                "repeat_last_n": self.context_length,
                "top_p": 0.9,
                "presence_penalty": self.presence_penalty,
                "frequency_penalty": self.frequency_penalty,
                "num_predict": num_predict,
                "num_ctx": self.context_length,
            },
        }
        if self.think is not None:
            payload["think"] = self.think
        if json_schema is not None:
            payload["format"] = json_schema
        return payload

    def chat_text(self, messages: list[dict[str, str]], temperature: float = 0.8, num_predict: int = 120) -> str:
        """非結構化的自由文字生成（flavor.py 用），不走 JSON schema、不重試——這類呼叫是
        錦上添花的裝飾句，失敗直接讓呼叫端省略即可，不值得重試拖慢行動流程。"""
        payload = self._build_payload(messages, temperature, num_predict=num_predict)
        res = requests.post(f"{self.base_url}/api/chat", json=payload, timeout=self.timeout)
        res.raise_for_status()
        return res.json().get("message", {}).get("content", "")

    def chat_structured(
        self, messages: list[dict[str, str]], response_model: Type[T], temperature: float = 0.8,
        schema_fields: list[str] | None = None, required_fields: list[str] | None = None,
        num_predict: int = 1024,
    ) -> T:
        schema = response_model.model_json_schema()
        if schema_fields:
            schema = _trim_schema_properties(schema, schema_fields)
        payload = self._build_payload(messages, temperature, num_predict=num_predict, json_schema=schema)
        url = f"{self.base_url}/api/chat"
        required = required_fields or []

        try:
            res = requests.post(url, json=payload, timeout=self.timeout)
            if res.status_code == 404:
                raise RuntimeError(f"Ollama 回傳 404：模型 '{self.model}' 未找到，請先 `ollama pull {self.model}`。")
            res.raise_for_status()
            content = res.json().get("message", {}).get("content", "")
            data = parse_json_robustly(content)
            _ensure_required_present(data, response_model, required)
            return response_model.model_validate(data)
        except (json.JSONDecodeError, ValidationError, requests.RequestException, ValueError) as e:
            if isinstance(e, requests.HTTPError) and e.response is not None and e.response.status_code == 404:
                raise RuntimeError(f"Ollama 回傳 404：模型 '{self.model}' 未找到，請先 `ollama pull {self.model}`。")
            if not self.retry:  # 行動鎖內的複本：不重問，鎖最多被這一趟佔住 timeout 秒；例外照原樣丟給呼叫端走退路
                raise
            logger.warning(f"首次 LLM JSON 解析/請求失敗 ({e})，觸發 re-prompt 重試...")
            retry_messages = list(messages) + [{
                "role": "user",
                "content": "【錯誤提醒】你上一次輸出的內容無法解析為合法的 JSON 或不符 Schema。請務必且僅輸出符合 Schema 的合法 JSON 物件，嚴禁 Markdown 標記或額外文字。",
            }]
            retry_payload = self._build_payload(retry_messages, temperature, num_predict=num_predict, json_schema=schema)
            res = requests.post(url, json=retry_payload, timeout=self.timeout)
            if res.status_code == 404:
                raise RuntimeError(f"Ollama 回傳 404：模型 '{self.model}' 未找到，請先 `ollama pull {self.model}`。")
            res.raise_for_status()
            content = res.json().get("message", {}).get("content", "")
            data = parse_json_robustly(content)
            _ensure_required_present(data, response_model, required)
            return response_model.model_validate(data)
