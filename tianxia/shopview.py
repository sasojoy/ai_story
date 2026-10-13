"""店面的畫面資料（docs/superpowers/specs/2026-10-13-店面獨立介面-design.md 第六節；第一批：共用店面＋鐵匠鋪）。

只讀：不改數值、不碰亂數、不 import engine。每一個「做不了」的原因都從現在的規則函式拿（smithing.forge_problem、temper_problem、
weapons.buy_problem、repair_problem……），網頁不自己判斷規則。掌櫃的話照 PlayerState.shop_line（店裡最後一件事的情況鍵，引擎記）
從 content/shop_lines.json 挑一句（1.4）；鐵匠順口那一句（shop_clue）蓋過它。"""
from __future__ import annotations

import hashlib

from . import armor, equipment, forge_secrets, skillview, smithing, team, weapons
from .models import WEAPON_KINDS, Content
from .state import Equipment, GameState
from .world_state import WorldStateStore

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


# ── 鐵匠鋪（第二節）──
SMITH_SIGN = "鐵匠鋪"  # 待 joy 潤：招牌是「地名＋店名」
PAGE_NAMES = {"weapon": "兵器", "armor": "防具"}  # 待 joy 潤：上面那個切換
ARMOR_FORGE_NOTE = "防具不分種類：主料定階與工錢，主料與輔料合起來定屬性，名字照屬性接字。"  # 待 joy 潤（2.2）


def _pct(ratio: float) -> str:
    """同 weapons._pct：帶正負號、最多一位小數。"""
    return f"{ratio:+.1%}".replace(".0%", "%")


def _arts(state: GameState, content: Content, world: WorldStateStore):
    member = state.player.member
    return team.player_art(state, content, world, member.wugong_id), team.player_art(state, content, world, member.neigong_id)


def _weapon_shelf(state: GameState, content: Content, world: WorldStateStore, art) -> list[dict]:
    """兵器架六把（2.1）：配得上身上武學的標出來；付不起、裝備庫滿了照 weapons.buy_problem 灰掉寫原因。"""
    fit_kind = weapons.art_weapon(art.id, content, world) if art is not None else None
    out = []
    for item in weapons.stock(state, content):
        problem = weapons.buy_problem(state, content, item.kind)
        fits = weapons.usable(item, art, content, world)
        out.append({
            "id": f"smith:buy:{item.kind}", "name": item.name, "kind": weapons.NOUNS.get(item.kind, item.kind),
            "attribute": item.attribute, "tier": equipment.TIER_WORDS[1], "price": content.config.weapons.shop_price,
            "value": f"加成 {_pct(weapons.bonus(item, art, content, world))}" if fits else None,
            "fit": item.kind == fit_kind, "note": weapons.FITS_MARK.lstrip("・") if item.kind == fit_kind else "",
            "enabled": problem is None, "why": problem,
        })
    return out


def _armor_shelf(state: GameState, content: Content, neigong) -> list[dict]:
    """防具架四件（2.1）：對得上內功的標出來（armor.fit_note），減損照 armor.cut。"""
    out = []
    for attribute in armor.SHOP_ATTRIBUTES:
        item = armor.shop_item(attribute)
        problem = armor.buy_problem(state, content, attribute)
        note = armor.fit_note(item, neigong)
        out.append({
            "id": f"{armor.BUY}{attribute}", "name": item.name, "kind": smithing.ARMOR_KIND, "attribute": attribute,
            "tier": equipment.TIER_WORDS[1], "price": content.config.armor.shop_price,
            "value": f"少扣 {armor.pct(armor.cut(item, neigong, content))} 氣血", "fit": note == armor.MATCH_NOTE, "note": note,
            "enabled": problem is None, "why": problem,
        })
    return out


def _worn(state: GameState, content: Content, world: WorldStateStore, slot: str, art) -> dict:
    """淬煉與修那一頁（2.4）：身上那件的卡、修與淬煉兩顆（用哪一種素材、工錢；做不了照規則寫原因），配不上武學的提醒照 UNFIT_NOTE。"""
    item = equipment.worn(state.player, slot)
    if item is None:
        return {"item": None, "empty": armor.EMPTY if slot == "armor" else weapons.EMPTY}
    if slot == "armor":
        problem, silver, rid = armor.repair_problem(state, content), content.config.armor.repair_silver, armor.REPAIR
    else:
        problem, silver, rid = weapons.repair_problem(state, content), content.config.weapons.repair_silver, "smith:repair"
    material = equipment.repair_material(state, content)
    use = f"{content.materials[material].name}×1" if material is not None else "一個一階素材"
    tmid = smithing.temper_material(state, content, slot)
    tcost = smithing.temper_price(content, content.materials[tmid], slot) if tmid is not None else 0
    tuse = (f"{content.materials[tmid].name}×1" + (f"＋{tcost} 兩" if tcost else "")) if tmid is not None else ""
    tproblem = smithing.temper_problem(state, content, slot)
    unfit = weapons.UNFIT_NOTE.lstrip("・") if slot == "weapon" and weapons.worn_unfit(state, art, content, world) else ""
    return {
        "item": {"id": item.id, "name": item.name, "grade": equipment.grade(item), "wear_word": equipment.WEAR_WORDS[slot],
                 "wear": item.edge, "tempers": item.tempers, "temper_max": smithing.rules_of(content, slot).temper_max},
        "empty": "",
        "repair": {"id": rid, "use": f"{use}＋{silver} 兩", "enabled": problem is None, "why": problem},
        "temper": {"id": smithing.ARMOR_TEMPER if slot == "armor" else smithing.TEMPER, "use": tuse, "enabled": tproblem is None,
                   "why": tproblem},
        "unfit": unfit,
    }


def _rack(state: GameState, content: Content, world: WorldStateStore, slot: str, art, neigong) -> dict:
    """裝備庫那一頁（2.5）：這一欄裝備庫裡的每一件，列的寫法同修練頁（skillview.gear_rows 那一欄：keep、confirm、divine）。
    排法：等著定名的原品最前面，再照修好之後好的在前（防具 armor.fresh_cut；兵器照刀口磨利之後的加成，配不上的是 0）。"""
    gear = skillview.gear_rows(state, content, world)
    block = next((b for b in gear["slots"] if b["slot"] == slot), None)
    rows = list(block["rack"]) if block is not None else []
    items = {item.id: item for item in equipment.in_slot(state.player, slot)}

    def fresh(row) -> float:
        item = items[row["id"]]
        if slot == "armor":
            return armor.fresh_cut(item, neigong, content)
        return weapons.bonus(item.model_copy(update={"edge": 100}), art, content, world)

    rows.sort(key=lambda row: (row["divine"] is None, -fresh(row)))
    return {"rows": rows, "used": gear["used"], "cap": gear["cap"]}


def _forge(state: GameState, content: Content, world: WorldStateStore, slot: str, art) -> dict:
    """打造那一頁的骨架（2.2）：兵器頁一排種類（配得上身上武學的那一種標「配」、預設點著它，沒有就第一個），防具頁換成一行說明；
    素材格照 smithing.held 的順序。"""
    if slot == "armor":
        kinds, kind, note = [], smithing.ARMOR_KIND, ARMOR_FORGE_NOTE
    else:
        fit_kind = weapons.art_weapon(art.id, content, world) if art is not None else None
        kinds = [{"kind": k, "label": weapons.NOUNS[k], "fit": k == fit_kind} for k in WEAPON_KINDS]
        kind, note = (fit_kind if fit_kind in WEAPON_KINDS else WEAPON_KINDS[0]), ""
    mats = content.materials
    materials = [
        {"id": mid, "name": mats[mid].name, "attribute": mats[mid].attribute, "tier": mats[mid].tier,
         "tier_word": equipment.TIER_WORDS[mats[mid].tier], "count": n}
        for mid, n in smithing.held(state, content)
    ]
    return {"kinds": kinds, "kind": kind, "note": note, "materials": materials}


def smith_view(state: GameState, content: Content, world: WorldStateStore) -> dict:
    """鐵匠鋪的店面（第一、二節）：招牌、銀兩、掌櫃的話、出店與兵器防具切換的選項 id，四頁的資料。"""
    p = state.player
    art, neigong = _arts(state, content, world)
    page = equipment.page(p, content)
    return {
        "shop": "smith",
        "sign": f"{content.locations[p.location].name}{SMITH_SIGN}",
        "silver": p.stats.get("silver", 0),
        "line": line_text(state, content, "smith"),
        "back": "smith:back",
        "page": page,
        "pages": [{"slot": s, "label": PAGE_NAMES[s], "id": f"smith:page:{s}"} for s in equipment.SMITH_PAGES if equipment.on(content, s)],
        "shelf": _armor_shelf(state, content, neigong) if page == "armor" else _weapon_shelf(state, content, world, art),
        "worn": _worn(state, content, world, page, art),
        "rack": _rack(state, content, world, page, art, neigong),
        "pending": forge_secrets.unnamed_originals(state, world),
        "forge": _forge(state, content, world, page, art),
    }
