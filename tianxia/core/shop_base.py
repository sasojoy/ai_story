"""店裡共用的（第二輪第 93 批，原本在 tianxia/shopview.py；計畫 docs/superpowers/plans/2026-11-07-第二輪-第93批.md，導覽 docs/guide/裝備與店面.md）。

只讀：不改數值、不碰亂數、不 import engine。每一間店都要的幾樣：掌櫃的話（店面獨立介面設計 1.4）的情況表 SITUATIONS、每間店的離開鈕 BACKS（core/page_view._shop_live 認）、
這一下的情況鍵 problem_key、被拒那一句撐到什麼時候 hold_for、still_holds（FB-192）、招牌底下那一句 line_text、素材格的排序 attribute_rank、階名 TIER_NAMES；
加上跨店的內容檢查 check_shop_lines（content/shop_lines.json；tianxia/content.py 的 validate 在原位函式內 import，不開 CONTENT_SLOTS 新格，PM 定）。
掌櫃的話照 PlayerState.shop_line（店裡最後一件事的情況鍵，引擎記）從 content/shop_lines.json 挑一句；鐵匠順口那一句（shop_clue）蓋過它；被拒的那一句只撐到被拒的原因還成立（shop_hold，FB-192）。

各間店的畫面資料在包裡（Feature.shop_view，core/features.shop_page 問；一間店只有一包認）：smithy、bout、outlets、bounties、gear 各一個 shop_view.py，酒肆在 tavern 的 actions.tavern_view。
BACKS 寫字面：讓包 import 這一檔拿常數會多一條載入得早的路（mounts → shop_base → bounty_base → weapons）；包裡那幾個常數跟這裡一樣，tianxia/features/smithy/tests/test_shop.py 鎖住。
"""
from __future__ import annotations

import hashlib
import json
import re

from .. import forge_secrets
from ..models import Content
from ..state import GameState
from . import bounty_base
from .content_base import check_line as _check_line

# ── 掌櫃的話（1.4）──
SMITH_SITUATIONS = (
    "enter", "buy", "repair", "temper", "forge_low", "forge_mid", "forge_high", "forge_named", "forge_divine",
    "short_silver", "rack_full", "refused",
    "sell", "upgrade",  # 素材與經濟（2026-10-15）：收購、升階做成了（句子待 joy 潤）
    "black_market",  # 名聲 5.2：寇照黑市價賣成了
    "rules",  # 素材四階（正式季整合 5.10）：背包有四階時鐵匠講的神器規矩（next_rule 輪著講；放在畫面哪裡等對比圖）
    "have_divine",  # 神器輪替（正式季整合 5.8）：已經有那一件神器、再開那一爐被擋下（FB-403：不挑講料的那一句）
)
# 馬市（第三節）、懸賞榜（第四節）的情況：灰掉的鈕在 Game.choose 的選單那一關就擋下，short_silver、rack_full、held_full、refused
# 多半只在兩個分頁搶的時候出現
MARKET_SITUATIONS = ("enter", "buy", "feed", "wield", "short_silver", "rack_full", "refused")
BOARD_SITUATIONS = ("enter", "take", "drop", "pick", "give", "held_full", "refused")
DONATE_SITUATIONS = ("enter", "donate", "refused")  # 軍需帳（素材與經濟 B6）：進門、捐成了、捐不了
DADIAN_SITUATIONS = ("enter", "done")  # 打點（21 天季的銀兩出口）：進門、記了一筆
TAVERN_SITUATIONS = ("enter", "chatter", "news", "nothing", "asked", "missed", "wall", "treat", "hide", "trace", "short_silver", "refused")  # 酒肆（企劃者 2026-10-18）
SITUATIONS = {"smith": SMITH_SITUATIONS, "market": MARKET_SITUATIONS, "board": BOARD_SITUATIONS,
              "donate": DONATE_SITUATIONS, "dadian": DADIAN_SITUATIONS, "tavern": TAVERN_SITUATIONS}  # 店 → 情況；content.check_shop_lines 照它驗
# 每間店的離開鈕（Game._shop_live 認「店裡那一串是眼前的選單」）：懸賞榜的第三層（替一張求兵挑東西）沒有 bounty:back，只有回到懸賞榜
BACKS = {"smith": ("smith:back",), "market": ("market:back",), "board": ("bounty:back", "bounty:unpick"), "arena": ("arena:back", "arena:yield"),
         "donate": ("donate:back",), "dadian": ("dadian:back",), "tavern": ("tavern:back",)}
TIER_NAMES = {1: "一階", 2: "二階", 3: "三階", 4: "四階"}
RACK_FULL = "裝備庫滿了"  # 同 equipment.RACK_FULL（problem_key 照它認；tianxia/features/smithy/tests/test_shop.py 鎖住兩邊一樣）


def problem_key(problem: str | None, done: str) -> str:
    """這一下的情況鍵：做成了是 done；錢不夠（「還差 N 兩」）、裝備庫滿了、已經有那一件神器各一種；其餘的擋法一律 refused。"""
    if problem is None:
        return done
    if problem.startswith("還差"):
        return "short_silver"
    if problem == forge_secrets.HAVE_DIVINE:
        return "have_divine"  # FB-403
    return "rack_full" if problem == RACK_FULL else "refused"


# 被拒的情況（FB-192）：那一句只撐到被拒的原因還成立的時候，原因不成立了就換回平常那一句（進門那一組）——錢補夠了、裝備庫騰出位子了、
# 手上那一張作廢了；其餘的擋法（素材不夠、吃飽了、下榜了……）看不出原因，照「錢、素材、身上與裝備庫的東西都沒變」算還成立
REFUSALS = ("short_silver", "rack_full", "held_full", "refused", "have_divine")


def _mark(state: GameState) -> str:
    """被拒那一下的狀態指紋：銀兩、背包、身上與裝備庫每一件的 id 與磨損、淬煉。"""
    p = state.player
    gear = [(e.id, e.edge, e.tempers) for e in (p.weapon, p.armor, p.mount, p.treasure, *p.rack) if e is not None]
    raw = json.dumps([p.stats.get("silver", 0), sorted(p.materials.items()), gear], ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def hold_for(state: GameState, content: Content, key: str, problem: str | None) -> str:
    """這一下的那一句要撐到什麼時候（PlayerState.shop_hold）：錢不夠（「還差 N 兩」）記要的銀兩、裝備庫滿了記 rack、手上揭滿了記 held，
    其餘被拒的記狀態指紋；做成了的是空字串。"""
    if key == "short_silver":
        digits = re.search(r"\d+", problem or "")
        if digits:
            return f"silver:{state.player.stats.get('silver', 0) + int(digits.group())}"
    if key == "rack_full":
        return "rack"
    if key == "held_full":
        return "held"
    return f"same:{_mark(state)}" if key in REFUSALS else ""


def still_holds(state: GameState, content: Content, hold: str) -> bool:
    """被拒的原因還成立嗎（hold_for 記的）：沒記的（舊存檔、做成了的情況）算成立。"""
    p = state.player
    kind, _, arg = hold.partition(":")
    if kind == "silver":
        return p.stats.get("silver", 0) < int(arg)
    if kind == "rack":
        return len(p.rack) >= content.config.weapons.rack_cap
    if kind == "held":
        return len(bounty_base.mine(state, content)) >= content.config.bounties.max_taken
    if kind == "same":
        return _mark(state) == arg
    return True


def line_text(state: GameState, content: Content, shop: str) -> str:
    """招牌底下那一句：鐵匠順口說了口訣就是那一句；不然照情況鍵（沒有、或內容沒寫那一種就用進門那一組）挑一句，
    照「名號｜情況｜那一下的時間」的雜湊挑（不碰 Game.rng；輪詢時同一句不換）。內容沒寫是空字串。被拒的那一句（REFUSALS）只撐到被拒的原因
    還成立（still_holds）：錢補夠了……就換回進門那一組，不必等下一個動作（FB-192）。"""
    p = state.player
    if p.shop_clue:
        return p.shop_clue
    pool = content.shop_lines.get(shop, {})
    key = p.shop_line if pool.get(p.shop_line) else "enter"
    if key in REFUSALS and not still_holds(state, content, p.shop_hold):
        key = "enter"
    lines = pool.get(key) or []
    if not lines:
        return ""
    digest = hashlib.sha256(f"{p.name}|{key}|{p.shop_line_seed}".encode()).digest()
    return lines[int.from_bytes(digest[:4], "big") % len(lines)]


ATTRIBUTE_ROWS = ("剛", "柔", "快", "慢")  # 打造頁素材格一屬性一排的順序（企劃者 2026-10-14 微調）；其餘屬性（陰陽虛實）排在後面


def attribute_rank(attribute: str) -> tuple[int, str]:
    """素材格排第幾排：剛、柔、快、慢，其餘照字排在後面。"""
    return (ATTRIBUTE_ROWS.index(attribute), "") if attribute in ATTRIBUTE_ROWS else (len(ATTRIBUTE_ROWS), attribute)


def check_shop_lines(c: Content, need) -> None:
    """店面上掌櫃的話（content/shop_lines.json，店面獨立介面設計 1.4；Joy 直接改字）：寫了的只能是認得的店與情況，每一句不能空、
    只用繁體中文、不寫數字；店面開關開著時，開門的店那一組每一種情況都要有句子：鐵匠鋪（兵器或防具開著）、馬市（坐騎開著）、
    懸賞榜（開著而且劇本有陣營）。"""
    for shop, pool in c.shop_lines.items():
        need(shop in SITUATIONS, f"shop_lines：不認得的店 {shop}")
        for key, lines in pool.items():
            need(key in SITUATIONS.get(shop, ()), f"shop_lines.{shop}：不認得的情況 {key}")
            for text in lines:
                _check_line(need, f"shop_lines.{shop}.{key}", text)
    opened = {
        "smith": c.config.weapons.enabled or c.config.armor.enabled,
        "market": c.config.mounts.enabled,
        "board": c.config.bounties.enabled and bool(c.scenario.factions),
        "donate": c.config.economy.donate and bool(c.scenario.factions),  # 大本營的軍需帳（素材與經濟 B6）
        "dadian": c.config.silver_outlets.enabled,  # 打點（21 天季的銀兩出口）
        "tavern": c.config.tavern.enabled and any("酒肆" in loc.tags for loc in c.locations.values()),  # 酒肆（企劃者 2026-10-18）
    }
    switched = {"sell": c.config.economy.sell, "upgrade": c.config.economy.upgrade,  # 素材與經濟：收購、升階關著時不必有那一句
                "rules": c.config.four_tiers.enabled,  # 素材四階關著時鐵匠不講神器的規矩（正式季整合 5.10）
                "have_divine": c.config.forge_secrets.rotation,  # 神器輪替關著時不會擋「已經有這一件神器」（FB-403）
                "black_market": c.config.economy.sell and c.config.renown.titles and c.config.renown.black_market}  # 名聲 5.2
    for shop, on in opened.items():
        if c.config.shop_screens and on:
            for key in SITUATIONS[shop]:
                if shop == "smith" and not switched.get(key, True):
                    continue
                need(bool(c.shop_lines.get(shop, {}).get(key)), f"shop_lines.{shop} 缺少情況 {key}（這間店開著時每一種情況至少一句）")
