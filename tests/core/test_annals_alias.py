"""列傳包的 standing.py（全部拆包第 29 批之二）：記一筆那一半在 core/annal_base.py，查詢那一半在這一檔，
別的包讀的那一串公開名字從這裡都拿得到同一個物件（第二輪第 103 批舊名的別名收掉，本地名 annals 留著）。"""
from __future__ import annotations

from tianxia.features.zhuan import standing as annals
from tianxia.core import annal_base
from tianxia.features.zhuan import standing

CORE = ("note", "entry", "trim", "kept_names", "clip", "first_sentence", "figure_name", "on", "heard", "mark", "watch", "_notable", "_gear",
        "KINDS", "GROUPS", "UNHEARD", "SHOWDOWN", "FIGURE", "FIGHT", "DEED", "CONQUER", "SEAL", "MARK", "STANCE", "ERRAND", "XINGSHI",
        "TIER", "DUEL", "STORY", "TEXT_MAX", "QUOTE_MAX", "REPLY_MAX", "STORY_TEXT_MAX", "MASTERED")
QUERY = ("profile", "standing", "tier_text", "tier_note", "xingshi_notes", "rows", "_said", "_tier_side", "_zhuan_end",
         "TIER_LINE", "TIER_GENTRY", "TIER_BOTH", "XINGSHI_LINE", "XINGSHI_SAID_MAX")


def test_alias_reexports_both_halves():
    for name in CORE:
        assert getattr(annals, name) is getattr(annal_base, name), name
    for name in QUERY:
        assert getattr(annals, name) is getattr(standing, name), name
