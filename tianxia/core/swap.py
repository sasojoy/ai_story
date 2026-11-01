"""JSON 樣子的資料裡「整個字串剛好等於某個舊字串」的換掉（易名帖：名號當鑰匙的地方一起換）。
原本在 rename.py；資料庫那一側（sqlite_world.rename_character）是核心、不 import 功能包，所以這兩個通用的換字搬進核心，
商城包的 rename.py 照舊叫得到（開發規範手冊 3.10）。"""
from __future__ import annotations

import json
from typing import Any


def swap(obj: Any, mapping: dict[str, str]) -> Any:
    """JSON 樣子的資料（dict、list、字串）裡，整個字串剛好是 mapping 的鍵的值與字典鍵換成對應的新字串；其餘原樣。"""
    if isinstance(obj, str):
        return mapping.get(obj, obj)
    if isinstance(obj, list):
        return [swap(v, mapping) for v in obj]
    if isinstance(obj, dict):
        return {mapping.get(k, k) if isinstance(k, str) else k: swap(v, mapping) for k, v in obj.items()}
    return obj


def swap_json(text: str | None, mapping: dict[str, str]) -> str | None:
    """一段 JSON 文字照 swap 換過再寫回去（沒有要換的字就原樣回，不重排）。"""
    if text is None or not any(old in text for old in mapping):
        return text
    return json.dumps(swap(json.loads(text), mapping), ensure_ascii=False)
