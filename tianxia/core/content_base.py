"""內容驗證共用的小工具（core_content：第二輪第 96 批，從 content.py 搬來）：共用層各模組的 check_*、各包的 checks.py 與 content.validate 都讀它（check_line、event_effects、stage_events 第二輪第 100 批搬來）。

同 event_check 不進 MODULES（那一份是 tianxia/<名字>.py 頂層的核心模組），也不進 test_for.CORE_SERVICES。只 import models、zh，不 import content。
"""
from __future__ import annotations

import re

from ..models import Content, Effect, Event
from ..zh import to_traditional

NUMBER_IN_TEXT = re.compile(r"[0-9０-９%％]")  # 心裡話不能攤出成功率（也不能寫難度）
TIMETABLE_SIDES = ("guan", "huang")  # 時刻表的鎖定、決戰、@commander 只有官軍與黃巾兩方


def check_traditional(need, where: str, text: str | None) -> None:
    """寫了的話只能用繁體中文（時刻表、伏筆的文字：空白另有檢查，數字可以寫）。"""
    if text:
        need(to_traditional(text) == text, f"{where}：文字只能用繁體中文（「{text[:12]}…」）")


def week7(c: Content) -> bool:
    """這一份設定是 7 天濃縮季（照現實天的季、季曆分段）：內容要照天另寫 7 天的那一份（real7、active_from_day7、cal_day_*7）。"""
    return bool(c.config.season21 and c.config.season_segments)


# ── core_content（第二輪第 100 批）──
def check_line(need, where: str, text: str, numbers: str = "") -> None:
    """玩家看得到、寫死在內容裡的一句：不能是空白、只能用繁體中文、不能寫數字或百分比。numbers 接在「不能寫數字或百分比」
    後面，說明這一類的句子為什麼不能寫（有所感的場景、心裡話、戰況變化各有一句）。"""
    need(bool(text.strip()), f"{where}：有空白的句子")
    need(to_traditional(text) == text, f"{where}：文字只能用繁體中文（「{text[:12]}」）")
    need(not NUMBER_IN_TEXT.search(text), f"{where}：不能寫數字或百分比{numbers}（「{text[:12]}」）")


def event_effects(ev: Event) -> list[Effect]:
    """一則事件寫的每一個效果：選項的成敗、隨口應對的成敗與分岔的每一種後果。"""
    out = [e for ch in ev.choices for e in (ch.effect, ch.fail_effect)]
    if ev.free_text is not None:
        out += [ev.free_text.effect, ev.free_text.fail_effect]
        out += [e for o in ev.free_text.outcomes for e in (o.effect, o.fail_effect)]
    return out


def stage_events(c: Content, line) -> dict[str, str]:
    """一條線的段落事件與它們 next_event 串下去的事件（事件 id → 哪一段）：都算這一條線的，選項可以寫 story。"""
    owned: dict[str, str] = {}
    for stage in line.stages:
        todo = [stage.event] if stage.event else []
        while todo:
            eid = todo.pop()
            ev = c.events.get(eid)
            if ev is None or eid in owned:
                continue
            owned[eid] = stage.id
            todo += [eff.next_event for eff in event_effects(ev) if eff.next_event]
    return owned
