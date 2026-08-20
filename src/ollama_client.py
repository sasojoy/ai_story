import json
import logging
import re
import requests
from typing import List, Dict, Any, Type, TypeVar, Optional
from pydantic import BaseModel, ValidationError

T = TypeVar('T', bound=BaseModel)

logger = logging.getLogger(__name__)


def clean_json_text(text: str) -> str:
    """清理 LLM 輸出中可能包含的 markdown 程式碼區塊與外圍非 JSON 文字"""
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
    """嘗試修復因 token 截斷導致的不完整 JSON 結構"""
    s = s.strip()
    start_idx = s.find("{")
    if start_idx != -1:
        s = s[start_idx:]

    s = re.sub(r',\s*$', '', s)
    s = re.sub(r':\s*$', ': ""', s)

    in_string = False
    escape = False
    stack = []

    for char in s:
        if escape:
            escape = False
            continue
        if char == '\\':
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if not in_string:
            if char in '{[':
                stack.append(char)
            elif char in '}]':
                if stack:
                    stack.pop()

    if in_string:
        s += '"'

    while stack:
        top = stack.pop()
        if top == '{':
            s += '}'
        elif top == '[':
            s += ']'

    return s


def extract_partial_narrative(text: str) -> str:
    """從未完成/串流中的 JSON 文字中即時提取 narrative 欄位之內容"""
    start = text.find('"narrative"')
    if start == -1:
        return ""
    colon = text.find(':', start)
    if colon == -1:
        return ""
    quote_start = text.find('"', colon)
    if quote_start == -1:
        return ""

    content = text[quote_start + 1:]
    result = []
    i = 0
    while i < len(content):
        ch = content[i]
        if ch == '\\' and i + 1 < len(content):
            next_ch = content[i + 1]
            if next_ch == '"':
                result.append('"')
            elif next_ch == 'n':
                result.append('\n')
            elif next_ch == '\\':
                result.append('\\')
            else:
                result.append(next_ch)
            i += 2
            continue
        if ch == '"':
            break
        result.append(ch)
        i += 1
    return "".join(result)


def _ensure_options_present(data: dict) -> None:
    """LLM 回應若因復讀迴圈等原因被 num_predict 截斷，常常整個 JSON 都還沒寫到 options
    欄位就被切斷；GameStateDelta.options 有 default_factory 給的固定預設選項清單，
    Pydantic 驗證並不會報錯，會靜默套用那份寫死清單，玩家會覺得「選項永遠是那幾個」。
    這裡明確擋下來，逼它走 re-prompt 重試或上層 NPC 專屬 fallback，而不是悄悄回傳固定預設值。"""
    if not data.get("options"):
        raise ValueError("LLM 回應缺少有效的 options 欄位，疑似被截斷")


def parse_json_robustly(text: str) -> dict:
    """穩健解析 LLM 輸出的 JSON，具備容錯修復機制"""
    cleaned = clean_json_text(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 1. 嘗試修復尾隨逗號
    fixed = re.sub(r',\s*([\}\]])', r'\1', cleaned)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # 2. 嘗試修復字串內未轉義換行
    fixed_newlines = re.sub(r'(?<!\\)\n', r'\\n', cleaned)
    fixed_newlines = re.sub(r',\s*([\}\]])', r'\1', fixed_newlines)
    try:
        return json.loads(fixed_newlines)
    except json.JSONDecodeError:
        pass

    # 3. 嘗試修復截斷不完整 JSON
    repaired = repair_truncated_json(cleaned)
    repaired_clean = re.sub(r',\s*([\}\]])', r'\1', repaired)
    return json.loads(repaired_clean)


class OllamaClient:
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5:7b",
        timeout: int = 60,
        context_length: int = 4096
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.context_length = context_length

    def check_health(self) -> bool:
        """檢查 Ollama 服務是否正常運行"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Ollama 連線檢查失敗: {e}")
            return False

    def _build_payload(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        stream: bool = False,
        num_predict: int = 1024
    ) -> Dict[str, Any]:
        """組裝 /api/chat 的 request payload，統一取樣參數與 num_ctx 來源，避免三處重複字面量"""
        return {
            "model": self.model,
            "messages": messages,
            "format": "json",
            "stream": stream,
            "keep_alive": "60m",
            "options": {
                "temperature": temperature,
                "repeat_penalty": 1.18,
                "repeat_last_n": self.context_length,
                "top_p": 0.9,
                "presence_penalty": 0.3,
                "frequency_penalty": 0.3,
                "num_predict": num_predict,
                "num_ctx": self.context_length
            }
        }

    def chat_structured(
        self,
        messages: List[Dict[str, str]],
        response_model: Type[T],
        temperature: float = 0.7
    ) -> T:
        """
        發送對話請求並解析為指定 Pydantic 模型。
        具備一次自動重新提示 (Re-prompt) 的重試機制。
        """
        payload = self._build_payload(messages, temperature)

        url = f"{self.base_url}/api/chat"

        try:
            res = requests.post(url, json=payload, timeout=self.timeout)
            if res.status_code == 404:
                raise RuntimeError(f"Ollama 回傳 404：模型 '{self.model}' 未找到，請先執行 `ollama pull {self.model}` 下載模型。")
            res.raise_for_status()
            raw_data = res.json()
            content = raw_data.get("message", {}).get("content", "")
            
            data = parse_json_robustly(content)
            _ensure_options_present(data)
            return response_model.model_validate(data)

        except (json.JSONDecodeError, ValidationError, requests.RequestException, ValueError) as e:
            if isinstance(e, requests.HTTPError) and e.response is not None and e.response.status_code == 404:
                raise RuntimeError(f"Ollama 回傳 404：模型 '{self.model}' 未找到，請先執行 `ollama pull {self.model}` 下載模型。")

            logger.warning(f"首次 LLM JSON 解析/請求失敗 ({e})，觸發 Re-prompt 重試機制...")
            
            # Re-prompt 準備
            retry_messages = list(messages)
            retry_messages.append({
                "role": "user",
                "content": (
                    "【錯誤提醒】你上一次輸出的內容無法解析為合法的 JSON 格式或不符 Schema 規範。"
                    "請務必且僅輸出符合 Schema 的合法 JSON 物件，嚴禁包含 Markdown 標記或額外文字。"
                )
            })
            
            retry_payload = self._build_payload(retry_messages, temperature)

            res = requests.post(url, json=retry_payload, timeout=self.timeout)
            if res.status_code == 404:
                raise RuntimeError(f"Ollama 回傳 404：模型 '{self.model}' 未找到，請先執行 `ollama pull {self.model}` 下載模型。")
            res.raise_for_status()
            raw_data = res.json()
            content = raw_data.get("message", {}).get("content", "")
            
            data = parse_json_robustly(content)
            _ensure_options_present(data)
            return response_model.model_validate(data)

    def chat_structured_stream(
        self,
        messages: List[Dict[str, str]],
        response_model: Type[T],
        temperature: float = 0.7,
        num_predict: int = 1024
    ):
        """
        以串流 (stream: True) 方式調用 Ollama Chat API。
        過程持續 yield (partial_narrative, None)
        串流結束時 yield (full_narrative, validated_model_instance)
        """
        payload = self._build_payload(messages, temperature, stream=True, num_predict=num_predict)

        url = f"{self.base_url}/api/chat"
        full_content = ""

        try:
            res = requests.post(url, json=payload, timeout=self.timeout, stream=True)
            if res.status_code == 404:
                raise RuntimeError(f"Ollama 回傳 404：模型 '{self.model}' 未找到，請先執行 `ollama pull {self.model}` 下載模型。")
            res.raise_for_status()

            for line in res.iter_lines():
                if not line:
                    continue
                try:
                    chunk_json = json.loads(line.decode("utf-8"))
                    chunk_content = chunk_json.get("message", {}).get("content", "")
                    full_content += chunk_content
                    partial = extract_partial_narrative(full_content)
                    if partial:
                        yield (partial, None)
                except Exception:
                    pass

            data = parse_json_robustly(full_content)
            _ensure_options_present(data)
            validated = response_model.model_validate(data)
            narrative = getattr(validated, "narrative", "") or extract_partial_narrative(full_content)
            yield (narrative, validated)

        except Exception as e:
            logger.warning(f"串流請求/解析失敗 ({e})，降級至單次完整請求...")
            result = self.chat_structured(messages=messages, response_model=response_model, temperature=temperature)
            yield (result.narrative, result)
