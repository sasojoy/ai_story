import json
import os
from typing import Any, Dict


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def load_json_or_default(path: str, default: Dict[str, Any]) -> Dict[str, Any]:
    """統一的設定檔載入：讀 JSON，檔案不存在或解析失敗就回傳呼叫端提供的預設值。
    取代原本散落在 game_engine.py/options.py/rules.py/npc_agent.py 的多份重複讀檔邏輯。"""
    full_path = path if os.path.isabs(path) else os.path.join(BASE_DIR, path)
    if os.path.exists(full_path):
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default
