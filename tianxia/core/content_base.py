"""內容驗證共用的小工具（core_content：第二輪第 96 批，從 content.py 搬來）：共用層各模組的 check_* 與 content.validate 都讀它。

同 event_check 不進 MODULES（那一份是 tianxia/<名字>.py 頂層的核心模組），也不進 test_for.CORE_SERVICES。只 import models、zh，不 import content。
"""
from __future__ import annotations

import re

from ..models import Content
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
