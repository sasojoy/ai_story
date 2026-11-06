"""點大勢人物那一層的人物簡介（功能包 socialize；主幹合回 D 段從 server.py 搬來）：跟著「此地人物」那一排走。
單獨一個檔的理由：它在 import 時讀一次這一包的 content/figure_intros.json，只有殼 import 它，引擎與假人程式不多讀。
"""
from __future__ import annotations

import json
from pathlib import Path


def _figure_intros() -> dict:
    """點大勢人物那一層的人物簡介（這一包的 content/figure_intros.json；給不熟三國的玩家看，Joy 11/6）：沒有這個檔就是空的，畫面不畫簡介。"""
    try:
        data = json.loads((Path(__file__).parent / "content" / "figure_intros.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_") and isinstance(v, dict)}


FIGURE_INTROS = _figure_intros()


def figure_intro(cid: str) -> dict | None:
    """{who 是誰, role 身分, nature 本性, now 如今, history 變化紀錄}。性子隨全服的互動改變是另一串在做（設計稿「人物性子會變」）：
    那一套開了之後 now 寫如今那一段、history 一行一筆（「第 1 週・週五 起，脾氣沒那麼火爆了」）；還沒做之前 now 是 None、history 是空的，畫面不畫這兩格。"""
    row = FIGURE_INTROS.get(cid)
    if not row:
        return None
    return {"who": row.get("who", ""), "role": row.get("role", ""), "nature": row.get("nature", ""), "now": None, "history": []}
