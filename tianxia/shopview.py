"""店面的畫面資料（docs/superpowers/specs/2026-10-13-店面獨立介面-design.md 第六節；第一批：共用店面＋鐵匠鋪）。

只讀：不改數值、不碰亂數、不 import engine。每一個「做不了」的原因都從現在的規則函式拿（smithing.forge_problem、temper_problem、
weapons.buy_problem、repair_problem……），網頁不自己判斷規則。掌櫃的話照 PlayerState.shop_line（店裡最後一件事的情況鍵，引擎記）
從 content/shop_lines.json 挑一句（1.4）；鐵匠順口那一句（shop_clue）蓋過它。"""
from __future__ import annotations

import hashlib

from .models import Content
from .state import Equipment, GameState

# ── 掌櫃的話（1.4）──
SMITH_SITUATIONS = (
    "enter", "buy", "repair", "temper", "forge_low", "forge_mid", "forge_high", "forge_named", "forge_divine",
    "short_silver", "rack_full", "refused",
)
SITUATIONS = {"smith": SMITH_SITUATIONS}  # 店 → 情況（第二批加 market、board）；content.check_shop_lines 照它驗
FORGED_KEYS = {"下品": "forge_low", "中品": "forge_mid", "上品": "forge_high"}
RACK_FULL = "裝備庫滿了"  # 同 equipment.RACK_FULL（problem_key 照它認；tests/test_shop.py 鎖住兩邊一樣）


def problem_key(problem: str | None, done: str) -> str:
    """這一下的情況鍵：做成了是 done；錢不夠（「還差 N 兩」）、裝備庫滿了各一種；其餘的擋法一律 refused。"""
    if problem is None:
        return done
    if problem.startswith("還差"):
        return "short_silver"
    return "rack_full" if problem == RACK_FULL else "refused"


def forged_key(item: Equipment) -> str:
    """打完一爐那一句照什麼分（1.4）：神器（原品、仿品）＞名器＞品質。"""
    if item.original or item.copy_of is not None:
        return "forge_divine"
    if item.secret is not None:
        return "forge_named"
    return FORGED_KEYS.get(item.quality, "forge_low")


def line_text(state: GameState, content: Content, shop: str) -> str:
    """招牌底下那一句：鐵匠順口說了口訣就是那一句；不然照情況鍵（沒有、或內容沒寫那一種就用進門那一組）挑一句，
    照「名號｜情況｜那一下的時間」的雜湊挑（不碰 Game.rng；輪詢時同一句不換）。內容沒寫是空字串。"""
    p = state.player
    if p.shop_clue:
        return p.shop_clue
    pool = content.shop_lines.get(shop, {})
    key = p.shop_line if pool.get(p.shop_line) else "enter"
    lines = pool.get(key) or []
    if not lines:
        return ""
    digest = hashlib.sha256(f"{p.name}|{key}|{p.shop_line_seed}".encode()).digest()
    return lines[int.from_bytes(digest[:4], "big") % len(lines)]
