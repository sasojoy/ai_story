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
        timeout: int = 60
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def check_health(self) -> bool:
        """檢查 Ollama 服務是否正常運行"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Ollama 連線檢查失敗: {e}")
            return False

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
        payload = {
            "model": self.model,
            "messages": messages,
            "format": "json",
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": 2048,
                "num_ctx": 4096
            }
        }

        url = f"{self.base_url}/api/chat"

        try:
            res = requests.post(url, json=payload, timeout=self.timeout)
            if res.status_code == 404:
                raise RuntimeError(f"Ollama 回傳 404：模型 '{self.model}' 未找到，請先執行 `ollama pull {self.model}` 下載模型。")
            res.raise_for_status()
            raw_data = res.json()
            content = raw_data.get("message", {}).get("content", "")
            
            data = parse_json_robustly(content)
            return response_model.model_validate(data)

        except (json.JSONDecodeError, ValidationError, requests.RequestException) as e:
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
            
            retry_payload = {
                "model": self.model,
                "messages": retry_messages,
                "format": "json",
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": 2048,
                    "num_ctx": 4096
                }
            }

            res = requests.post(url, json=retry_payload, timeout=self.timeout)
            if res.status_code == 404:
                raise RuntimeError(f"Ollama 回傳 404：模型 '{self.model}' 未找到，請先執行 `ollama pull {self.model}` 下載模型。")
            res.raise_for_status()
            raw_data = res.json()
            content = raw_data.get("message", {}).get("content", "")
            
            data = parse_json_robustly(content)
            return response_model.model_validate(data)
