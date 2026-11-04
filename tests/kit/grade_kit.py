"""讀內容檔原文的測試用：檢定寫難度等級（grade＋shift，屬性與跨季架構 v2 5.1）時換回難度，跟載入時 content.resolve_grades 同一張表。"""
from __future__ import annotations

from tianxia.models import CheckRules

_DC = {g.key: g.dc for g in CheckRules().grades}


def raw_difficulty(check: dict) -> int:
    if "grade" in check:
        return _DC[check["grade"]] + check.get("shift", 0)
    return check["difficulty"]
