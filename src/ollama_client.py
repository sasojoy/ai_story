import json
import logging
import requests
from typing import List, Dict, Any, Type, TypeVar, Optional
from pydantic import BaseModel, ValidationError

T = TypeVar('T', bound=BaseModel)

logger = logging.getLogger(__name__)


def clean_json_text(text: str) -> str:
    """清理 LLM 輸出中可能包含的 markdown 程式碼區塊"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


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
                "temperature": temperature
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
            
            cleaned = clean_json_text(content)
            data = json.loads(cleaned)
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
                    "temperature": temperature
                }
            }

            res = requests.post(url, json=retry_payload, timeout=self.timeout)
            if res.status_code == 404:
                raise RuntimeError(f"Ollama 回傳 404：模型 '{self.model}' 未找到，請先執行 `ollama pull {self.model}` 下載模型。")
            res.raise_for_status()
            raw_data = res.json()
            content = raw_data.get("message", {}).get("content", "")
            
            cleaned = clean_json_text(content)
            data = json.loads(cleaned)
            return response_model.model_validate(data)
