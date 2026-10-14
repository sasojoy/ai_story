"""店面的畫面資料（docs/superpowers/specs/2026-10-13-店面獨立介面-design.md 第六節；第一批：共用店面＋鐵匠鋪；第二批：馬市、懸賞榜）。

只讀：不改數值、不碰亂數、不 import engine。每一個「做不了」的原因都從現在的規則函式拿（smithing.forge_problem、temper_problem、
weapons.buy_problem、repair_problem……），網頁不自己判斷規則。掌櫃的話照 PlayerState.shop_line（店裡最後一件事的情況鍵，引擎記）
從 content/shop_lines.json 挑一句（1.4）；鐵匠順口那一句（shop_clue）蓋過它；被拒的那一句只撐到被拒的原因還成立（shop_hold，FB-192）。"""
from __future__ import annotations

import hashlib
import json
import re

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


# 被拒的情況（FB-192）：那一句只撐到被拒的原因還成立的時候，原因不成立了就換回平常那一句（進門那一組）——錢補夠了、裝備庫騰出位子了、
# 手上那一張作廢了；其餘的擋法（素材不夠、吃飽了、下榜了……）看不出原因，照「錢、素材、身上與裝備庫的東西都沒變」算還成立
REFUSALS = ("short_silver", "rack_full", "held_full", "refused")


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
        return len(bounties.mine(state, content)) >= content.config.bounties.max_taken
    if kind == "same":
        return _mark(state) == arg
    return True


def forged_key(item: Equipment) -> str:
    """打完一爐那一句照什麼分（1.4）：神器（原品、仿品）＞名器＞品質。"""
    if item.original or item.copy_of is not None:
        return "forge_divine"
    if item.secret is not None:
        return "forge_named"
    return FORGED_KEYS.get(item.quality, "forge_low")


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


ATTRIBUTE_ROWS = ("剛", "柔", "快", "慢")  # 打造頁素材格一屬性一排的順序（企劃者 2026-10-14 微調）；其餘屬性（陰陽虛實）排在後面


def attribute_rank(attribute: str) -> tuple[int, str]:
    """素材格排第幾排：剛、柔、快、慢，其餘照字排在後面。"""
    return (ATTRIBUTE_ROWS.index(attribute), "") if attribute in ATTRIBUTE_ROWS else (len(ATTRIBUTE_ROWS), attribute)


def _held_rows(state: GameState, content: Content) -> list[tuple[str, int]]:
    """店面素材格的順序（企劃者 2026-10-14 微調）：背包裡打得了的素材（smithing.held）照屬性一排一排（剛柔快慢，其餘在後），每排一階到三階。
    一步一步的選單照舊用 smithing.held（高階先）。"""
    mats = content.materials
    return sorted(smithing.held(state, content), key=lambda pair: (attribute_rank(mats[pair[0]].attribute), mats[pair[0]].tier, pair[0]))


def _forge(state: GameState, content: Content, world: WorldStateStore, slot: str, art) -> dict:
    """打造那一頁的骨架（2.2）：兵器頁一排種類（配得上身上武學的那一種標「配」、預設點著它，沒有就第一個），防具頁換成一行說明；
    素材格照屬性再照階排（_held_rows）。"""
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
        for mid, n in _held_rows(state, content)
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
    held = _held_rows(state, content)
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


# ── 馬市（第三節）──
NO_HORSE = "還沒有馬"  # 待 joy 潤：沒有馬時「你騎的」那一間
STALL_WHO = {"worn": "你騎的", "sale": "待售", "rack": "裝備庫"}  # 待 joy 潤：馬廄上那一行
ABILITY_NAMES = (("save", "省體力"), ("speed", "路上快"), ("cavalry", "決戰騎兵"), ("escape", "落敗脫身"))  # 同修練頁坐騎那一列（待 joy 潤）
FASTER, SLOWER, SAME = "比你騎的快", "比你騎的慢", "跟你騎的一樣快"  # 待 joy 潤：照卡上「路上快」那一條比（含飽足，FB-194）
HUNGRY_NOTE = "沒吃飽，四項本事都跟著打了折"  # 待 joy 潤：你騎的那匹飽足不到 100 時，飽足長條底下
BUY_TEXT = "買下 {price} 兩"  # 待 joy 潤
FEED_TEXT, WIELD_TEXT = "餵", "換上"  # 待 joy 潤


def _coat(item: Equipment) -> int:
    """馬廄裡那匹的毛色（畫法用）：名字開頭對上 mounts.COATS 的第幾個；名駒、名將贈禮的專名對不上是 -1（網頁畫成預設色）。"""
    return next((i for i, coat in enumerate(mounts.COATS) if item.name.startswith(coat)), -1)


def _bars(content: Content, item: Equipment) -> list[dict]:
    """四項本事的長條（第三節）：數字同修練頁那一列（mounts.abilities），value 是長條的寬（整數百分比，.5 進位同 mounts.pct）。"""
    got = mounts.abilities(content, item)
    return [{"key": key, "label": label, "value": mounts.half_up(got[key] * 100), "text": mounts.pct(got[key])} for key, label in ABILITY_NAMES]


def _speed_shown(content: Content, item: Equipment) -> int:
    """卡上「路上快」那一條寫的數（整數百分比，含飽足）：「比你騎的快／慢」照它比（FB-194）。"""
    return mounts.half_up(mounts.abilities(content, item)["speed"] * 100)


def _stall(content: Content, item: Equipment, role: str, sub: str, action: dict) -> dict:
    return {
        "id": item.id, "role": role, "who": STALL_WHO[role], "empty": False, "name": mounts.name_of(item), "grade": mounts.grade(item),
        "sub": sub, "coat": _coat(item), "bars": _bars(content, item), "fed": None, "compare": "", "action": action,
    }


def market_view(state: GameState, content: Content, world: WorldStateStore) -> dict:
    """馬市的店面（第三節）：一排馬廄——你騎的（沒有馬是一間空的）、馬販待售的那匹（mounts.shop_item）、裝備庫裡的馬一匹一間。
    每一間：名字、階品、四項本事的長條；你騎的那匹多飽足長條。卡上那一顆照現在的選項 id：你騎的「餵」（market:feed，做不了照
    mounts.feed_problem）、待售的「買下」（market:buy，mounts.buy_problem）、裝備庫裡的「換上」（market:wield:<id>，選單本來就每一匹
    各列一顆）與「比你騎的快／慢」（照卡上「路上快」那一條的數字比：乘了飽足、畫面上的整數百分比，卡上的數字與那一句對得上，FB-194；
    機器人換馬照舊比吃飽的腳力 mounts.better_mount）。focus：進門預設點著的那一間（你騎的，沒有馬就待售的）。world 沒用到（三間店同一個呼叫法）。"""
    p = state.player
    stalls: list[dict] = []
    if p.mount is not None:
        problem = mounts.feed_problem(state, content)
        worn = _stall(content, p.mount, "worn", mounts.grade(p.mount), {
            "id": mounts.FEED, "label": FEED_TEXT, "use": mounts.feed_note(state, content) if problem is None else "",
            "enabled": problem is None, "why": problem,
        })
        worn["fed"] = {"word": mounts.WEAR_WORD, "value": p.mount.edge, "note": HUNGRY_NOTE if p.mount.edge < 100 else ""}
        stalls.append(worn)
    else:
        stalls.append({"id": "", "role": "worn", "who": STALL_WHO["worn"], "empty": True, "name": NO_HORSE})
    sale, price = mounts.shop_item(state, content), content.config.mounts.shop_price
    problem = mounts.buy_problem(state, content)
    stalls.append(_stall(content, sale, "sale", f"{mounts.TIER_NAMES.get(sale.tier, '')}・{price} 兩", {
        "id": mounts.BUY, "label": BUY_TEXT.format(price=price), "use": "", "enabled": problem is None, "why": problem,
    }))
    ridden = _speed_shown(content, p.mount) if p.mount is not None else None
    for item in equipment.in_slot(p, "mount"):
        stall = _stall(content, item, "rack", mounts.grade(item),
                       {"id": f"{mounts.WIELD}{item.id}", "label": WIELD_TEXT, "use": "", "enabled": True, "why": None})
        if ridden is not None:
            mine = _speed_shown(content, item)
            stall["compare"] = FASTER if mine > ridden else SLOWER if mine < ridden else SAME
        stalls.append(stall)
    return {
        "shop": "market",
        "sign": f"{content.locations[p.location].name}{mounts.MARKET}",
        "silver": p.stats.get("silver", 0),
        "line": line_text(state, content, "market"),
        "back": mounts.BACK,
        "stalls": stalls,
        "focus": p.mount.id if p.mount is not None else sale.id,
    }


# ── 懸賞榜（第四節）──
HELD_HEAD = "你手上揭著的（{n}／{cap}）"  # 待 joy 潤：最上面那一排的標題
SLOT_LEFT = "還能揭 {n} 張"  # 待 joy 潤：那一排最後的空格
HAVE_NOTE = "你有 {n} {unit}合用"  # 待 joy 潤：求藝、求兵的告示上
NO_FIT = "你身上沒有合用的"  # 待 joy 潤：求藝、求兵交不出時，放大的紙上「交出…」灰掉的原因
PRIZE_SHORT = "另有重賞"  # 待 joy 潤：告示上（放大的紙上，賞那一段照 reward_text 寫是哪一種）
DROP_ASK = "把「{title}」放回榜上？放回去就不算你的了。"  # 待 joy 潤：放棄先問一次（選單上的 bounty:drop 沒有問句，問在網頁那一層）


def _headline(title: str) -> str:
    """告示上那一行大字：短標題「・」後面那一段（「打探・湖邊」→「湖邊」）。"""
    return title.partition("・")[2] or title


def board_view(state: GameState, content: Content, world: WorldStateStore) -> dict:
    """懸賞榜的店面（第四節）：最上面一排手上揭著的（bounties.mine）；木板上是看得到的告示（bounties.visible，同選單的第二層），
    揭著的在前、交得出的求藝求兵其次、其餘照現在的順序。每一張寫哪一方掛的、標題、要做什麼、賞、期限與名額（紙上的 due_line、告示上短的 due_short，FB-196）、重賞、求藝求兵
    你有幾件合用（fitting）；底下那一顆照現在的選項 id：揭著的「放棄」（bounty:drop，問句在網頁）、求藝求兵「交出…」（bounty:pick，
    交不出照 only_original 或 NO_FIT）、其餘「揭下」（bounty:take，揭不了照 take_problem）。第三層開著（bounty_pick 指著一張還交得出的；
    同 Game._bounty_options 的判法）時多 picked 與 hand_in（hand_in_options 的每一顆，回到懸賞榜那一顆除外）。掛單的人（通緝的 poster）
    不寫：照現在的選單寫陣營，畫面不露出誰是假人（設計 6.6）。"""
    p = state.player
    shown = bounties.visible(state, content)
    mine = bounties.mine(state, content)
    mine_ids = {b.id for b in mine}
    memo: dict = {}
    picked = next((b for b in shown if b.id == p.bounty_pick and b.kind in bounties.GIVE_KINDS), None)
    picked_items = bounties.fitting(state, content, world, picked, memo) if picked is not None else []
    if not picked_items:
        picked = None  # 那一張下榜了、交不出了就當它不存在（同 _bounty_options）
    ranked = []
    for order, b in enumerate(shown):
        title = bounties.title(content, b)
        note = {
            "id": b.id, "kind": b.kind, "kind_name": bounties.KIND_NAMES.get(b.kind, b.kind), "issuer": bounties.issuer(content, b),
            "title": title, "head": _headline(title), "how": bounties.how(content, b), "reward": bounties.reward_text(state, content, b),
            "due": bounties.due_line(state, content, b), "short": bounties.due_short(b, content, state.world), "prize": PRIZE_SHORT if bounties.has_prize(content, b) else "",
            "held": b.id in mine_ids, "have": "",
        }
        rank = 2
        if b.id in mine_ids:
            rank = 0
            note["action"] = {"id": f"bounty:drop:{b.id}", "verb": "drop", "enabled": True, "why": None, "confirm": DROP_ASK.format(title=title)}
        elif b.kind in bounties.GIVE_KINDS:
            items = bounties.fitting(state, content, world, b, memo)
            if items:
                rank, note["have"] = 1, HAVE_NOTE.format(n=len(items), unit=bounties.unit_of(b))
            # 交不出的原因照規則：只有神器原品或本命兵器對得上、只有身上正在練或等著定名的那門對得上（同第三層灰掉那幾行），都不是才寫 NO_FIT
            blocked = bounties.blocked_arts(state, content, world, b, memo)
            why = None if items else (bounties.only_original(state, b).strip("（）") or (blocked[0][1] if blocked else NO_FIT))
            note["action"] = {"id": f"bounty:pick:{b.id}", "verb": "pick", "enabled": bool(items), "why": why}
        else:
            problem = bounties.take_problem(state, content, b)
            note["action"] = {"id": f"bounty:take:{b.id}", "verb": "take", "enabled": problem is None, "why": problem}
        ranked.append((rank, order, note))
    hand_in = []
    if picked is not None:
        hand_in = [
            {"id": o.id, "label": o.label, "enabled": o.enabled}
            for o in bounties.hand_in_options(state, content, world, picked, picked_items, memo) if o.id != bounties.UNPICK_ID
        ]
    cap = content.config.bounties.max_taken
    held = [{"id": b.id, "title": bounties.title(content, b), "due": bounties.due_text(b, content, state.world)} for b in mine]
    left = max(0, cap - len(held))  # 截殺關了又開時手上可以超過上限（FB-155）：照實列，空格是 0
    return {
        "shop": "board",
        "sign": f"{content.locations[p.location].name}{bounties.BOARD}",
        "silver": p.stats.get("silver", 0),
        "line": line_text(state, content, "board"),
        "back": "bounty:back",
        "unpick": bounties.UNPICK_ID,
        "held": {"rows": held, "head": HELD_HEAD.format(n=len(held), cap=cap), "left": left, "left_text": SLOT_LEFT.format(n=left) if left else ""},
        "notes": [note for _rank, _order, note in sorted(ranked, key=lambda r: (r[0], r[1]))],
        "empty": "" if shown else bounties.BOARD_EMPTY,
        "picked": picked.id if picked is not None else None,
        "hand_in": hand_in,
    }
