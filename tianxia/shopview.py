"""店面的畫面資料（docs/superpowers/specs/2026-10-13-店面獨立介面-design.md 第六節；第一批：共用店面＋鐵匠鋪）。

只讀：不改數值、不碰亂數、不 import engine。每一個「做不了」的原因都從現在的規則函式拿（smithing.forge_problem、temper_problem、
weapons.buy_problem、repair_problem……），網頁不自己判斷規則。掌櫃的話照 PlayerState.shop_line（店裡最後一件事的情況鍵，引擎記）
從 content/shop_lines.json 挑一句（1.4）；鐵匠順口那一句（shop_clue）蓋過它。"""
from __future__ import annotations

import hashlib

from . import armor, bounties, equipment, forge_secrets, mounts, skillview, smithing, team, weapons
from .models import WEAPON_KINDS, Content
from .state import Equipment, GameState
from .world_state import WorldStateStore

# ── 掌櫃的話（1.4）──
SMITH_SITUATIONS = (
    "enter", "buy", "repair", "temper", "forge_low", "forge_mid", "forge_high", "forge_named", "forge_divine",
    "short_silver", "rack_full", "refused",
)
# 馬市（第三節）、懸賞榜（第四節）的情況：灰掉的鈕在 Game.choose 的選單那一關就擋下，short_silver、rack_full、held_full、refused
# 多半只在兩個分頁搶的時候出現
MARKET_SITUATIONS = ("enter", "buy", "feed", "wield", "short_silver", "rack_full", "refused")
BOARD_SITUATIONS = ("enter", "take", "drop", "pick", "give", "held_full", "refused")
SITUATIONS = {"smith": SMITH_SITUATIONS, "market": MARKET_SITUATIONS, "board": BOARD_SITUATIONS}  # 店 → 情況；content.check_shop_lines 照它驗
# 每間店的離開鈕（Game._shop_live 認「店裡那一串是眼前的選單」）：懸賞榜的第三層（替一張求藝、求兵挑東西）沒有 bounty:back，只有回到懸賞榜
BACKS = {"smith": ("smith:back",), "market": (mounts.BACK,), "board": ("bounty:back", bounties.UNPICK_ID)}
_HELD_HEAD = bounties.HELD_FULL.partition("{")[0]
FORGED_KEYS = {"下品": "forge_low", "中品": "forge_mid", "上品": "forge_high"}
RACK_FULL = "裝備庫滿了"  # 同 equipment.RACK_FULL（problem_key 照它認；tests/test_shop.py 鎖住兩邊一樣）


def problem_key(problem: str | None, done: str) -> str:
    """這一下的情況鍵：做成了是 done；錢不夠（「還差 N 兩」）、裝備庫滿了各一種；其餘的擋法一律 refused。"""
    if problem is None:
        return done
    if problem.startswith("還差"):
        return "short_silver"
    return "rack_full" if problem == RACK_FULL else "refused"


def board_key(problem: str | None, done: str) -> str:
    """懸賞榜這一下的情況鍵：做成了是 done；手上揭滿了（bounties.HELD_FULL，寫的是手上真的有幾張）一種；其餘的擋法一律 refused。"""
    if problem is None:
        return done
    return "held_full" if problem.startswith(_HELD_HEAD) else "refused"


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
    return {"kinds": kinds, "kind": kind, "note": note, "materials": materials, "line": smith_line(state, content, world, kind)}


SHORT_CELL = "工錢不夠，還差 {n} 兩"  # 待 joy 潤（2.2：主料格灰掉寫的）
ONLY_ONE = "只剩一個，已當主料"  # 待 joy 潤
GO_TEXT = "開爐・工錢 {price} 兩"  # 待 joy 潤（2.2：開爐鈕）


def smith_line(state: GameState, content: Content, world: WorldStateStore, kind: str, main: str | None = None,
               aux: str | None = None) -> dict:
    """這一爐會怎樣（2.2、6.3）：素材格每一格放不放得進去（點一下放的是主料還是輔料：主料空著先放主料，否則放輔料；兩格都滿了換掉輔料）、
    不行的原因；兩格都放好時寫種類、屬性、階、工錢、三個機率（smithing.forge_odds，同開爐鈕）、最多兩句原因、自己鑄譜上打中過的那一句
    （SOLVED_HEAD／DIVINE_HEAD；別人打中的、沒打中過的都不寫）、打得成沒有。客戶端送的 main、aux 照現在的背包修正（手上沒有的、
    同一種只剩一個的拿掉）。只讀。"""
    if kind not in WEAPON_KINDS and kind != smithing.ARMOR_KIND:
        return {"kind": kind, "main": None, "aux": None, "rack_full": None, "cells": [], "ready": False}
    held = smithing.held(state, content)
    counts = dict(held)
    main = main if main in counts else None
    aux = aux if main is not None and aux in counts and (aux != main or counts[aux] >= 2) else None
    slot = smithing.slot_of(kind)
    full = equipment.rack_full(state, content, slot)
    silver = state.player.stats.get("silver", 0)
    cells = []
    for mid, n in held:
        to = "main" if main is None else "aux"
        if full:
            why = equipment.RACK_FULL
        elif to == "main":
            short = smithing.price(content, content.materials[mid].tier, slot) - silver
            why = SHORT_CELL.format(n=short) if short > 0 else None
        elif mid == main and n < 2:
            why = ONLY_ONE
        else:
            why = smithing.forge_problem(state, content, kind, main, mid)
        cells.append({"id": mid, "to": to, "ok": why is None, "why": why, "main": mid == main, "aux": mid == aux})
    out = {"kind": kind, "main": main, "aux": aux, "rack_full": equipment.RACK_FULL if full else None, "cells": cells, "ready": False}
    if main is None or aux is None:
        return out
    tianji = world.read().tianji
    tier = smithing.tier_of(content, main)
    known = forge_secrets.solved_name(state, content, tianji, slot, kind, main, aux)
    recipe = forge_secrets.match(content, tianji, slot, kind, main, aux) if known else None
    divine = recipe is not None and recipe.divine
    odds = None if divine else smithing.forge_odds(state, content, world, kind, main, aux)
    price = smithing.price(content, tier, slot)
    head = (smithing.DIVINE_HEAD if divine else smithing.SOLVED_HEAD).format(name=known).removeprefix(" → ") if known else ""
    out.update(
        ready=True, kind_label=smithing.noun_label(kind), attribute=smithing.attribute_with(content, tianji, kind, main, aux),
        tier=equipment.TIER_WORDS[tier], price=price, divine=divine,
        odds=[{"q": q, "pct": round(w)} for q, w in odds.odds.items()] if odds is not None else None,
        reasons=list(odds.reasons) if odds is not None else [], head=head,
        problem=smithing.forge_problem(state, content, kind, main, aux), go=GO_TEXT.format(price=price),
    )
    return out


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


# ── 出爐卡（2.3）──
GLOWS = {"下品": "none", "中品": "cyan", "上品": "gold"}
FITS = weapons.FITS_MARK.lstrip("・")
UNFITS = "配不上你的武學"  # 待 joy 潤：出爐卡上配不上那一句（同修練頁「用不上」的意思）


def glow_of(item: Equipment) -> str:
    """麻布透出的光（2.3）：原品赤金＞仿品紅＞名器紫＞品質（下品沒光、中品青、上品金）。"""
    if item.original:
        return "redgold"
    if item.copy_of is not None:
        return "red"
    if item.secret is not None:
        return "purple"
    return GLOWS.get(item.quality, "none")


def forged_card(state: GameState, content: Content, world: WorldStateStore, item: Equipment, report: dict) -> dict:
    """出爐卡（2.3）：名字、階品（equipment.grade）、種類與屬性、兵器的加成或防具的減損（同修練頁那一列）、配不配得上（防具：對不對得上
    內功）、光色、首位發現（打中隱藏配方而且是全服第一個）、去了手上還是裝備庫、還等著定名的原品的譜名。"""
    art, neigong = _arts(state, content, world)
    if item.slot == "armor":
        value, fit, kind = f"少扣 {armor.pct(armor.cut(item, neigong, content))} 氣血", armor.fit_note(item, neigong), smithing.ARMOR_KIND
    else:
        usable = weapons.usable(item, art, content, world)
        value = f"加成 {_pct(weapons.bonus(item, art, content, world))}" if usable else None
        fit, kind = (FITS if usable else UNFITS), weapons.NOUNS.get(item.kind, item.kind)
    worn = equipment.worn(state.player, item.slot)
    return {
        "id": item.id, "slot": item.slot, "name": item.name, "grade": equipment.grade(item), "kind": kind,
        "attribute": item.attribute, "value": value, "fit": fit, "glow": glow_of(item),
        "first": bool(report.get("first")) and item.secret is not None,
        "where": "worn" if worn is not None and worn.id == item.id else "rack",
        "divine": forge_secrets.unnamed_originals(state, world).get(item.id),
    }
