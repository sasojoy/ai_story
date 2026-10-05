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
from typing import Any, Type, TypeVar

import requests
from pydantic import BaseModel, ValidationError

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
    不會報錯，會靜默套用寫死的預設清單）。"""
    fields = getattr(response_model, "model_fields", {})
    for name in required:
        if name in fields and not data.get(name):
            raise ValueError(f"LLM 回應缺少必要欄位 {name!r}，疑似被截斷")


def with_timeout_cap(client: Any, seconds: int | float) -> Any:
    """client 的複本，HTTP 逾時最多 seconds 秒；沒有 client（None）就是 None，原本的 client 不動（同一個角色的別的請求
    可能正在用它）。已經比 seconds 快的 client 原樣回傳。引擎不讀時鐘（CLAUDE.md），上限靠 HTTP 的逾時來管，跟
    naming.propose 同一個做法。拿簡單的假物件（沒有 timeout 欄位）當 client 的測試與腳本也一樣給複本、設上上限。
    注意 chat_structured 一次呼叫最多送兩趟（第一次＋格式不對、逾時時的重問），兩趟都用這個逾時；chat_text 只送一趟。"""
    if client is None:
        return None
    own = getattr(client, "timeout", None)
    if isinstance(own, (int, float)) and own <= seconds:
        return client
    capped = copy.copy(client)
    capped.timeout = seconds
    return capped


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

    def check_health(self) -> bool:
        try:
            res = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return res.status_code == 200
        except Exception as e:
            logger.warning(f"Ollama 連線檢查失敗: {e}")
            return False

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
