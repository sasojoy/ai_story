import requests
from typing import Any, Dict


class RWKVClient:
    """跟 RWKV Runner 的 backend-python OpenAI 相容 API 溝通的輕量 client。

    刻意跟 src/ollama_client.py::OllamaClient 分開、不共用同一個類別：RWKV 是純續寫
    (completion) 模型而不是指令遵循 (chat) 模型，呼叫方式（/v1/completions 而非
    /api/chat）跟使用情境（給前綴文字讓它自然接續，而不是下指令要求寫什麼）完全不同，
    硬共用只會讓兩邊都變得不乾淨。

    需要先用 scripts/start_rwkv_server.ps1 啟動 backend-python 並載入模型，這個
    client 假設服務已經在跑，不負責啟動/載入模型。"""

    def __init__(self, base_url: str = "http://127.0.0.1:8000", timeout: int = 180):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def complete(
        self,
        prompt: str,
        max_tokens: int = 300,
        temperature: float = 1.0,
        top_p: float = 0.3,
        presence_penalty: float = 0.3,
        frequency_penalty: float = 1.0,
    ) -> str:
        """送出前綴文字，回傳模型接續生成的內文（不含原本的 prompt）。

        presence_penalty/frequency_penalty：實測發現多步驟接龍時，累積的前綴越長、
        裡面重複句式越多，沒有抗重複參數的 RWKV 會整段崩潰成復讀自己剛寫過的段落
        （這是 RNN 類架構比 transformer 更容易出現的失敗模式），預設值抄自
        RWKV Runner 官方範例（ModelConfigBody 的 json_schema_extra example）。"""
        payload: Dict[str, Any] = {
            "model": "rwkv",
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "presence_penalty": presence_penalty,
            "frequency_penalty": frequency_penalty,
        }
        res = requests.post(f"{self.base_url}/v1/completions", json=payload, timeout=self.timeout)
        res.raise_for_status()
        data = res.json()
        choices = data.get("choices", [])
        if not choices:
            return ""
        return (choices[0].get("text") or "").strip()

    def check_health(self) -> bool:
        try:
            res = requests.get(f"{self.base_url}/docs", timeout=5)
            return res.status_code == 200
        except Exception:
            return False
