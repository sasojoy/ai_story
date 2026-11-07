"""陣營包的內容驗證（第二輪第 100 批從核心 content.py 搬來，本體照搬）：content.validate 在原位經 features.check_at 叫（格在 core/features.py 的 CONTENT_SLOTS），先後不變；關著的包照驗。"""
from __future__ import annotations

from tianxia.models import Condition, Content


def check_faction_choices(c: Content, need) -> None:
    """選項照陣營分邊（Condition.factions／factions_none，企劃者 2026-10-08「加入黃巾軍了，探索還一堆打黃巾的任務」）之後，
    每一種身分（散人與每個陣營）碰得到的事件，至少要剩一個選項看得見——不然那個人會卡在一則沒有選項的事件上。
    只看陣營這一項：其他條件（銀兩、旗標）本來就由寫事件的人負責留一條退路。"""
    def allows(cond: Condition, faction: str | None) -> bool:
        if cond.factions and faction not in cond.factions:
            return False
        return faction is None or faction not in cond.factions_none

    for event in c.events.values():
        for faction in [None, *(f.id for f in c.scenario.factions)]:
            if not allows(event.condition, faction):
                continue
            need(
                any(allows(choice.condition, faction) for choice in event.choices),
                f"事件 {event.id}：{faction or '散人'}碰得到這則事件，選項卻全被陣營條件擋掉了",
            )
