"""易名帖：改自己的名號，當場生效（萬寶閣販賣清單定案；Joy 2026-10-21 在決策卡挑「當場生效」）。

名號在存檔裡到處當鑰匙（角色表、帳號、錢包、列傳、投靠名冊、這一季的全服登記、別人存檔裡的邀請與結伴……），所以改名是
一次把「整個字串剛好等於舊名號（或它的 casefold 鍵）」的地方都換成新的（`swap`）：JSON 裡的值與字典的鍵、資料表裡當身分的那幾欄。
**只換整個字串相等的**，句子裡提到舊名號的（傳聞、江湖史、戰報的字、以前寫好的傳）不動：那是當時的事，江湖史另記一行「某某改名某某」。
以前的季（seasons 表的舊列、舊季的全服登記）也不動，只換這一季；列傳照鍵搬過來（篇名照當時的名號）。

整個字串相等也可能撞到內容的 id（名號剛好叫某個地點、事件的 id），所以舊名號撞到內容裡任何一個字串鍵或 id 就不讓改（`clash`），
回一句請找管理者，不冒險。這一支只有 sqlite_world 與 engine 用。"""
from __future__ import annotations

import json
from typing import Any

from .models import Content

CLASHED = "你的名號跟江湖上的某樣東西撞了字，易名帖用不了，請找管理者處理。"  # 待 joy 潤


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


def _ids(obj: Any, out: set[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str):
                out.add(k)
            if k == "id" and isinstance(v, str):
                out.add(v)
            _ids(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _ids(v, out)


_CONTENT_IDS: dict[int, set[str]] = {}


def content_ids(content: Content) -> set[str]:
    """內容裡所有字串鍵與 id（地點、事件、人物、素材、武學……）；一份內容算一次。"""
    key = id(content)
    if key not in _CONTENT_IDS:
        out: set[str] = set()
        _ids(content.model_dump(mode="json"), out)
        _CONTENT_IDS[key] = out
    return _CONTENT_IDS[key]


def clash(name: str, key: str, content: Content) -> bool:
    """舊名號（或鍵）撞到內容的鍵或 id：整個字串換掉會改壞內容的參照，不讓改。"""
    ids = content_ids(content)
    return name in ids or key in ids
