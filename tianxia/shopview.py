"""店面的畫面資料（docs/superpowers/specs/2026-10-13-店面獨立介面-design.md 第六節；第一批：共用店面＋鐵匠鋪；第二批：馬市、懸賞榜）。

只讀：不改數值、不碰亂數、不 import engine。每一個「做不了」的原因都從現在的規則函式拿（smithing.forge_problem、temper_problem、
weapons.buy_problem、repair_problem……），網頁不自己判斷規則。掌櫃的話照 PlayerState.shop_line（店裡最後一件事的情況鍵，引擎記）
從 content/shop_lines.json 挑一句（1.4）；鐵匠順口那一句（shop_clue）蓋過它；被拒的那一句只撐到被拒的原因還成立（shop_hold，FB-192）。"""
from __future__ import annotations

import hashlib
import json
import re

from . import arena, armor, bounties, economy, equipment, forge_secrets, four_tiers, mounts, rules, silver, skillview, smithing, tactics, team, territory, weapons
from . import duel as duel_rules
from .characters import name_key
from .models import MOVES, WEAPON_KINDS, Content
from .state import Equipment, GameState
from .world_state import WorldStateStore

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
BACKS = {"smith": ("smith:back",), "market": (mounts.BACK,), "board": ("bounty:back", bounties.UNPICK_ID), "arena": (arena.BACK_ID, arena.YIELD_ID),
         "donate": ("donate:back",), "dadian": ("dadian:back",), "tavern": ("tavern:back",)}
_HELD_HEAD = bounties.HELD_FULL.partition("{")[0]
FORGED_KEYS = {"下品": "forge_low", "中品": "forge_mid", "上品": "forge_high"}
RACK_FULL = "裝備庫滿了"  # 同 equipment.RACK_FULL（problem_key 照它認；tests/gear/test_shop.py 鎖住兩邊一樣）


def problem_key(problem: str | None, done: str) -> str:
    """這一下的情況鍵：做成了是 done；錢不夠（「還差 N 兩」）、裝備庫滿了、已經有那一件神器各一種；其餘的擋法一律 refused。"""
    if problem is None:
        return done
    if problem.startswith("還差"):
        return "short_silver"
    if problem == forge_secrets.HAVE_DIVINE:
        return "have_divine"  # FB-403
    return "rack_full" if problem == RACK_FULL else "refused"


def board_key(problem: str | None, done: str) -> str:
    """懸賞榜這一下的情況鍵：做成了是 done；手上揭滿了（bounties.HELD_FULL，寫的是手上真的有幾張）一種；其餘的擋法一律 refused。"""
    if problem is None:
        return done
    return "held_full" if problem.startswith(_HELD_HEAD) else "refused"


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
        return len(bounties.mine(state, content)) >= content.config.bounties.max_taken
    if kind == "same":
        return _mark(state) == arg
    return True


def forged_key(item: Equipment) -> str:
    """打完一爐那一句照什麼分（1.4）：神器（原品、仿品）＞名器＞品質。"""
    if item.original or item.copy_of is not None:
        return "forge_divine"
    if equipment.is_named(item):  # 隱藏配方的名器、四階擲出的名器（正式季整合 5.2）
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


def next_rule(state: GameState, content: Content) -> str:
    """鐵匠講的神器規矩（素材四階，正式季整合 5.10）：素材四階開著、背包至少有一個四階時，挑這一季還沒講過的下一句（照
    content/shop_lines.json smith.rules 的順序），記進 PlayerState.smith_rules_told；講完一輪從頭。其餘是空字串。
    只看「有沒有四階」，跟是哪幾種四階無關（不講看了背包才說得出的話）；句子本身不講任何一件神器的配方。進鐵匠鋪時叫一次。"""
    p = state.player
    pool = content.shop_lines.get("smith", {}).get("rules") or []
    if not (four_tiers.on(content) and pool and any(n > 0 and four_tiers.tier4_id(content, mid) for mid, n in p.materials.items())):
        return ""
    if len(set(p.smith_rules_told)) >= len(pool):
        p.smith_rules_told = []
    index = next(i for i in range(len(pool)) if i not in p.smith_rules_told)
    p.smith_rules_told.append(index)
    return pool[index]


def rule_line(state: GameState) -> str:
    """店面資料上的「鐵匠的規矩」那一句（等企劃者挑對比圖決定放哪裡，網頁先不畫）：鐵匠順口講配方線索的那一下不講規矩（線索比規矩重要）。"""
    p = state.player
    return "" if p.shop_clue else p.smith_rule


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
            "value": f"加成 {_pct(weapons.bonus(item, art, content, world))}{weapons.CLASH_NOTE if weapons.clashes(item, art) else ''}" if fits else None,  # 相剋時補一句（終審 F6，同 FB-127）
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
    unfit = weapons.unfit_note(item).lstrip("・") if slot == "weapon" and weapons.worn_unfit(state, art, content, world) else ""
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
            short = smithing.price(content, content.materials[mid].tier, slot, state) - silver
            why = SHORT_CELL.format(n=short) if short > 0 else None
        elif mid == main and n < 2:
            why = ONLY_ONE
        else:
            why = smithing.forge_problem(state, content, kind, main, mid)
        cells.append({"id": mid, "to": to, "ok": why is None, "why": why, "main": mid == main, "aux": mid == aux})
    out = {"kind": kind, "main": main, "aux": aux, "rack_full": equipment.RACK_FULL if full else None, "cells": cells, "ready": False}
    if main is None or aux is None:
        return out
    tianji = world.tianji()
    tier = smithing.tier_of(content, main)
    known = forge_secrets.solved_name(state, content, tianji, slot, kind, main, aux)
    recipe = forge_secrets.match(content, tianji, slot, kind, main, aux, state.world) if known else None
    divine = recipe is not None and recipe.divine
    odds = None if divine else smithing.forge_odds(state, content, world, kind, main, aux)
    price = smithing.price(content, tier, slot, state)
    head = (smithing.DIVINE_HEAD if divine else smithing.SOLVED_HEAD).format(name=known).removeprefix(" → ") if known else ""
    out.update(
        ready=True, kind_label=smithing.noun_label(kind), attribute=smithing.attribute_with(content, tianji, kind, main, aux),
        tier=equipment.TIER_WORDS[tier], price=price, divine=divine,
        odds=[{"q": q, "pct": round(w)} for q, w in odds.odds.items()] if odds is not None else None,
        reasons=list(odds.reasons) if odds is not None else [], head=head,
        # FB-341：主料是四階時同一步一步選單的開爐鈕，多「四階的料，打出名器的機會很大」（不寫百分比、不寫神器）
        named_hint=smithing.NAMED_HINT if not divine and four_tiers.named_chance(content, main, aux) > 0 else "",
        problem=smithing.forge_problem(state, content, kind, main, aux),
        go=GO_TEXT.format(price=price) + territory.price_note(state, content),  # 名聲 4.1：工錢後面寫原因
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
        "rule": rule_line(state),  # 鐵匠講的神器規矩（正式季整合 5.10）：網頁畫在平常那一句的位置、金框（設計 9.1 第 2 批甲）
        "four": four_tiers.on(content),  # 素材四階開著：打造頁素材格一排多一欄四階、升階一屬性多一格三換四（設計 9.1 第 2 批甲）
        "back": "smith:back",
        "page": page,
        "pages": [{"slot": s, "label": PAGE_NAMES[s], "id": f"smith:page:{s}"} for s in equipment.SMITH_PAGES if equipment.on(content, s)],
        "shelf": _armor_shelf(state, content, neigong) if page == "armor" else _weapon_shelf(state, content, world, art),
        "worn": _worn(state, content, world, page, art),
        "rack": _rack(state, content, world, page, art, neigong),
        "pending": forge_secrets.unnamed_originals(state, world),
        "forge": _forge(state, content, world, page, art),
    }


def trade_view(state: GameState, content: Content, day: int) -> dict | None:
    """鐵匠鋪的素材買賣（素材與經濟設計第四、五節；Game.shop_view 接在 smith_view 後面的 "trade"）：收購、升階都關著是 None。
    sell：背包裡收得了的素材（一階、二階），每一種一列（id、名字、階、屬性、手上幾個、一個幾兩、賣一個不行的原因）；收購關著是空的。
    upgrade：每一個換得出來的（屬性, 階）一列（偏向出的那一種〔name／id〕與拿去換的、要幾個、手上幾個、工錢〔套地盤福利〕、
    今天還能換幾個〔不限是 None〕、不行的原因〔economy.upgrade_problem〕、機率那一句 odds 與偏向那一種的機會 same_share〔升階隨機，
    企劃者 2026-10-15〕）；升階關著是空的。按鈕送 MAIN_ACTIONS 的 smith_sell／smith_upgrade。day 是回體丹的換日。"""
    econ = content.config.economy
    if not (econ.sell or econ.upgrade):
        return None
    sell = []
    if econ.sell:
        for material, have in sorted(
            ((content.materials[mid], n) for mid, n in state.player.materials.items() if n > 0 and mid in content.materials),
            key=lambda pair: (pair[0].tier, attribute_rank(pair[0].attribute), pair[0].id),
        ):
            price = economy.sell_price_for(state, content, material.tier)  # 名聲 5.2：寇照黑市價
            if price is not None:
                sell.append({"id": material.id, "name": material.name, "tier": material.tier, "attribute": material.attribute,
                             "tier_word": TIER_NAMES.get(material.tier, ""),
                             "have": have, "price": price, "problem": economy.sell_problem(state, content, material.id, 1),
                             "dark": BLACK_MARKET if economy.black_market(state, content, material.tier) else ""})
    upgrade = []
    if econ.upgrade:
        for attribute, tier in economy.upgradable(content):
            high, low = economy.upgrade_pair(content, attribute, tier)
            problem = economy.upgrade_problem(state, content, attribute, tier, day)
            have = state.player.materials.get(low.id, 0)
            upgrade.append({
                "attribute": attribute, "tier": tier, "name": high.name, "id": high.id, "from": low.name, "from_id": low.id,
                "need": (need := economy.upgrade_needs(content)[tier]), "have": have,
                "cost": economy.upgrade_cost(state, content, tier), "left": (left := economy.upgrade_left(state, content, tier, day)),
                # 格子上的上限字（FB-342）：三換四是這一季的，其餘是今天的；不限是空字串
                "left_text": "" if left is None else (UP_LEFT_SEASON if tier == four_tiers.TIER else UP_LEFT_DAY).format(n=left),
                "cost_note": territory.price_note(state, content),  # 名聲 4.1：工錢後面寫原因（關著是空的）
                "problem": problem,
                "short": _upgrade_short(problem, have, need),  # 素材頁格子上寫的短原因
                "odds": economy.upgrade_odds(content, attribute, tier),  # 「五成出流雲絮，其餘隨機」
                "same_share": (share := economy.upgrade_outcomes(content, attribute, tier)[0][1]),
                "lean": economy.share_word(share) if share < 1 else "",  # 素材頁格子上的短寫「五成」；一定照投入的屬性是空的
            })
    return {"sell": sell, "upgrade": upgrade, **_trade_captions(content, state)}


UP_SHORT_HAVE = "手上 {have}／{need}"  # 待 joy 潤：素材頁升階格子上的短原因
UP_SHORT_DAY = "明日再來"
UP_SHORT_SEASON = "這一季滿了"  # 待 joy 潤：三換四這一季換滿了（正式季整合 4.5）
NOT_SOLD_NOTE = {False: "三階不收，留著打神器", True: "四階不收，留著打神器"}  # 收購標題最後那一段，照素材四階開著沒（待 joy 潤）
SELL_EMPTY = "背包裡沒有收得了的素材。"  # 待 joy 潤
# 素材頁最上面那一格還沒做事時的一句（做了事換成結果；待 joy 潤）。照開關寫（FB-272）：升階關著不提熬；開著時不說「只能」
# （找素材、打贏也撿得到高階的料）
UPGRADE_HINT = "熬出來的料{share}是同一個屬性，其餘隨機落到別的屬性。鐵匠不賣素材，高階的料得自己熬。"
# 素材四階開著時（FB-342；待 joy 潤）：一換二、二換三照舊隨機，三換四一定同屬性
UPGRADE_HINT_FOUR = "一換二、二換三熬出來的料{share}是同一個屬性，其餘隨機落到別的屬性；三換四一定是同一個屬性。鐵匠不賣素材，高階的料得自己熬。"
UP_LEFT_DAY = "今天還能 {n} 個"  # 待 joy 潤：升階格子上的上限（FB-342：字由伺服器給，網頁不寫死）
UP_LEFT_SEASON = "這一季還能 {n} 個"  # 待 joy 潤：三換四一季的上限
TRADE_HINT = "鐵匠不賣素材，高階的料得自己熬。"  # 升階開著、一定照投入的屬性（upgrade_same_share 1）
SELL_ONLY_HINT = "鐵匠只收素材，不賣素材。"  # 升階關著、收購開著


def _upgrade_short(problem: str | None, have: int, need: int) -> str | None:
    """升階格子上寫得下的短原因（點了才說整句）：料不夠寫「手上 1／3」、三階今天換過了寫「明日再來」，其餘照整句（「還差 N 兩」本來就短）。"""
    if problem is None:
        return None
    if problem == economy.UPGRADE_DAY_FULL:
        return UP_SHORT_DAY
    if problem == economy.UPGRADE_SEASON_FULL:
        return UP_SHORT_SEASON
    if have < need and problem not in (economy.UPGRADE_NO_WAY, economy.UPGRADE_NO_KIND):  # upgrade_problem 照這個順序擋：料不夠排在錢之前
        return UP_SHORT_HAVE.format(have=have, need=need)
    return problem


def _trade_hint(content: Content) -> str:
    """素材頁還沒做事時那一句（FB-272）：升階關著（只剩收購）不提熬；升階開著、出來的屬性隨機時寫幾成是同一個屬性；
    素材四階開著時另說三換四一定同屬性（FB-342）。"""
    econ = content.config.economy
    if not econ.upgrade:
        return SELL_ONLY_HINT
    if econ.upgrade_same_share < 1:
        hint = UPGRADE_HINT_FOUR if four_tiers.TIER in economy.upgrade_needs(content) else UPGRADE_HINT
        return hint.format(share=economy.share_word(econ.upgrade_same_share))
    return TRADE_HINT


def _trade_captions(content: Content, state: GameState | None = None) -> dict:
    """素材頁兩段的標題（照 Config 的數字寫；開著的那一段才有）與收購沒東西時那一句。待 joy 潤。
    state 給了照這個人的收購價寫（名聲 5.2：寇的黑市價，標題後面多「黑市價」）。"""
    econ = content.config.economy
    out: dict = {"up_cap": "", "sell_cap": "", "sell_empty": SELL_EMPTY, "hint": _trade_hint(content)}
    if econ.upgrade:
        needs = economy.upgrade_needs(content)
        steps = "、".join(f"{TIER_NAMES.get(t - 1, '')}{rules.count_word(n)}個換一個{TIER_NAMES.get(t, '')}" for t, n in sorted(needs.items()))
        if four_tiers.on(content):  # 素材四階：不設每日上限，三換四一季幾個（正式季整合 4.2、4.5）
            limits = f"{TIER_NAMES[four_tiers.TIER]}一季{four_tiers.count_text(content.config.four_tiers.season_cap)}個" if four_tiers.TIER in needs else ""
        else:
            limits = "、".join(f"{TIER_NAMES.get(t, '')}一天{rules.count_word(n)}個" for t, n in sorted(econ.upgrade_per_day.items()))
        out["up_cap"] = f"升階（同屬性的{steps}{f'；{limits}' if limits else ''}）"
    if econ.sell:
        price_of = (lambda t: economy.sell_price_for(state, content, t)) if state is not None else (lambda t: econ.sell_price[t])  # noqa: E731
        tiers = economy.sell_tiers(content)
        prices = [f"{TIER_NAMES.get(t, '')} {price_of(t)} 兩" for t in tiers]
        if prices:
            prices[0] = prices[0].replace(" ", "一個 ", 1)  # 「一階一個 2 兩、二階 6 兩」（同玩法說明）
        dark = state is not None and any(economy.black_market(state, content, t) for t in tiers)
        out["sell_cap"] = f"收購（{'、'.join(prices)}{'，' + BLACK_MARKET_CAP if dark else ''}；{NOT_SOLD_NOTE[four_tiers.on(content)]}）"
    return out


# ── 軍需帳（素材與經濟 B6，企劃者 2026-10-15 選草圖 B3）──
DONATE_SIGN = "{place}・{faction}軍需帳"  # 待 joy 潤：招牌
DONATE_CAP = "背包的素材（點一下挑要捐的；{points}）"  # 待 joy 潤
DONATE_EMPTY = "背包裡沒有素材。"  # 待 joy 潤
DONATE_TIER4_ONLY = "軍需官只收一到三階的料，四階的留著打神器。"  # 待 joy 潤（FB-343）：背包裡只剩四階（四階不能捐，正式季整合 4.6）
# 軍需帳最上面那一格還沒捐時的一句（捐了換成結果；待 joy 潤）：第一季規則開著時記貢獻
DONATE_HINT = "捐的記進陣營的軍備，也替陣營推一點大勢。"  # 豪強照依附的那一邊推；這裡不寫「戰線」（大本營不一定在戰線上）
DONATE_HINT_S1 = "捐的記成貢獻、記進陣營的軍備，也替陣營推一點大勢。"
TIER_NAMES = {1: "一階", 2: "二階", 3: "三階", 4: "四階"}
BLACK_MARKET = "（黑市價）"  # 名聲 5.2：寇賣素材的鈕上（待 joy 潤）
BLACK_MARKET_CAP = "照黑市價收"  # 收購那一段的標題


def dadian_view(state: GameState, content: Content, *, day: int, room: int, base: bool, clinic: bool, smith: bool,
                bribe: list[str], prologue: bool) -> dict:
    """「打點」那一間店（21 天季的銀兩出口；企劃者挑第 9 批畫面乙：茶樓雅間、一本攤開的帳簿）：Game.shop_view 在這間店開著時給。
    五樣都列：左頁「修為」名師指點、看火候、買破境丹，右頁「人情」打點門路（此地談得上話的每一位一筆）、捐銀兩。每一筆
    {id（這裡按得下的選項 id，做不了是 None）, name, price, desc, tick, ok, note（做不了的原因或去處）}：按得下去的送原本的選項 id；
    這裡做得了但被擋（今天請過了、錢不夠）的照 silver 的原因寫，這裡做不了的寫去哪裡做（silver.WHERE）。身上掛著還沒用掉的寫在帳底下（hang）。
    base／clinic／smith 是此地有沒有自家大本營、醫館、鐵匠鋪（Game 判），bribe 是此地打點得了的大勢人物，day 是回體丹的換日。"""
    p, cfg = state.player, content.config.silver_outlets

    def entry(oid, name, price, desc, tick, here, problem, where):
        ok = here and problem is None
        return {"id": oid if ok else None, "name": name, "price": price, "desc": desc, "tick": tick, "ok": ok,
                "note": "" if ok else (problem if here else where)}

    odds = cfg.furnace_odds
    pill = content.config.legend_item_name
    left = [
        entry("act:mentor", "名師指點", f"{cfg.mentor_silver} 兩", silver.MENTOR_DESC.format(bonus=cfg.mentor_bonus), silver.ONCE_DAILY,
              clinic, silver.mentor_problem(state, content, day) if clinic else None, silver.WHERE["mentor"]),
        entry("act:furnace", "看火候", f"{cfg.furnace_silver} 兩",
              silver.FURNACE_DESC.format(low=f"{odds.get('下品', 0):g}", mid=f"{odds.get('中品', 0):g}", high=f"{odds.get('上品', 0):g}"),
              silver.ONCE_DAILY, smith, silver.furnace_problem(state, content, day, prologue) if smith else None, silver.WHERE["furnace"]),
        entry("act:buy_legend", f"買{pill}", f"{cfg.legend_silver} 兩", silver.LEGEND_DESC,
              silver.LEGEND_LEFT.format(left=silver.legend_left(state, content)), clinic,
              silver.legend_problem(state, content) if clinic else None, silver.WHERE["legend"]),
    ]
    right = []
    for fid in bribe:
        name, cid = content.figures[fid].name, content.figures[fid].character
        now = p.affinities.get(cid, 0)
        right.append(entry(f"act:bribe:{fid}", f"打點門路・{name}", f"{cfg.bribe_silver} 兩",
                           silver.BRIBE_DESC.format(name=name, now=now, then=now + silver.bribe_gain(state, content, fid), top=cfg.bribe_max),
                           silver.BRIBE_DAILY, True, silver.bribe_problem(state, content, fid, day), ""))
    if not bribe:
        right.append(entry(None, "打點門路", f"{cfg.bribe_silver} 兩", silver.BRIBE_DESC_AWAY.format(gain=cfg.bribe_affinity, top=cfg.bribe_max),
                           silver.BRIBE_DAILY, False, None, silver.WHERE["bribe"]))
    donated = p.silver_donated if p.silver_donate_day == day else 0
    tick = silver.DONATE_LEFT.format(left=max(0, cfg.donate_daily_silver - donated))
    problem = silver.donate_problem(state, content, day, room, content.config.economy.donate_daily_cap) if base else None
    if base and problem is None:
        tick = f"{silver.DONATE_NOW.format(silver=silver.donate_amount(state, content, day, room))}・{tick}"
    right.append(entry("act:silver_donate", "捐銀兩", f"每 {cfg.donate_per_point} 兩", silver.DONATE_DESC.format(per=cfg.donate_per_point),
                       tick, base, problem, silver.WHERE["donate" if p.faction else "donate_ranger"]))
    hang = [line for ready, line in ((p.mentor_ready, silver.HANG_MENTOR), (p.furnace_ready, silver.HANG_FURNACE)) if ready]
    return {
        "shop": "dadian", "sign": silver.SHOP, "silver": p.stats.get("silver", 0), "line": line_text(state, content, "dadian"),
        "back": "dadian:back",
        "pages": [{"head": silver.PAGE_SELF, "entries": left}, {"head": silver.PAGE_FAVOR, "entries": right}],
        "hang": silver.HANG_HEAD + "・".join(hang) if hang else "",
    }


def donate_view(state: GameState, content: Content, day: int) -> dict:
    """大本營的軍需帳（素材與經濟設計第六節；Game.shop_view 在軍需官那一串開著時給）：招牌、軍需官那一句、出店（donate:back）、
    陣營四種軍備的存量（同 Game.armament_view 的順序）、今天還能捐幾點與上限，背包裡每一種素材一格（照剛柔快慢、再照階排：份量、
    今天最多收得下幾個 take〔economy.donate_take〕、捐不了的原因〔economy.donate_problem〕、進哪一樣軍備）。捐出送
    MAIN_ACTIONS["donate"] 的 items（挑好的幾種一起捐，一則紀錄）。day 是回體丹的換日。"""
    p = state.player
    econ = content.config.economy
    stock = state.world.armaments.get(p.faction or "", {})
    cells = []
    for material, held in sorted(
        ((content.materials[mid], n) for mid, n in p.materials.items() if n > 0 and mid in content.materials),
        key=lambda pair: (attribute_rank(pair[0].attribute), pair[0].tier, pair[0].id),
    ):
        points = economy.donate_points(content, material.id)
        if points <= 0:
            continue
        cells.append({
            "id": material.id, "name": material.name, "attribute": material.attribute, "tier": material.tier,
            "tier_word": TIER_NAMES.get(material.tier, ""), "have": held, "points": points,
            "take": economy.donate_take(state, content, material.id, held, day),
            "problem": economy.donate_problem(state, content, material.id, day),
            "armament": economy.armament_of(content, material.attribute) or economy.DONATE_MISC,
        })
    points_text = "、".join(f"{TIER_NAMES[t]} {n} 點" for t, n in sorted(econ.donate_points.items()) if t in TIER_NAMES)
    room = economy.donate_room(state, content, day)
    return {
        "shop": "donate",
        "sign": DONATE_SIGN.format(place=content.locations[p.location].name, faction=content.scenario.faction_name(p.faction or "", "")),
        "silver": p.stats.get("silver", 0),
        "line": line_text(state, content, "donate"),
        "back": "donate:back",
        "stock": [{"name": name, "attribute": attribute, "points": stock.get(attribute, 0)} for attribute, name in econ.armaments.items()],
        "room": room,
        "cap": econ.donate_daily_cap,
        "room_text": economy.DONATE_LEFT.format(n=room) if room > 0 else economy.DONATE_FULL.format(cap=econ.donate_daily_cap),
        "caption": DONATE_CAP.format(points=points_text),
        "hint": DONATE_HINT_S1 if rules.season_one(content, state.world) else DONATE_HINT,
        "empty": DONATE_TIER4_ONLY if not cells and any(  # FB-343：只剩四階時說四階不收，不說沒有素材
            n > 0 and four_tiers.tier4_id(content, mid) for mid, n in p.materials.items()) else DONATE_EMPTY,
        "cells": cells,
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
    if equipment.is_named(item):
        return "purple"
    return GLOWS.get(item.quality, "none")


def forged_card(state: GameState, content: Content, world: WorldStateStore, item: Equipment, report: dict) -> dict:
    """出爐卡（2.3）：名字、階品（equipment.grade）、種類與屬性、兵器的加成或防具的減損（同修練頁那一列）、配不配得上（防具：對不對得上
    內功）、光色、首位發現（打中隱藏配方而且是全服第一個）、去了手上還是裝備庫、還等著定名的原品的譜名、量詞（equipment.unit_for，
    定名表單那一句用，FB-197）。"""
    art, neigong = _arts(state, content, world)
    if item.slot == "armor":
        value, fit, kind = f"少扣 {armor.pct(armor.cut(item, neigong, content))} 氣血", armor.fit_note(item, neigong), smithing.ARMOR_KIND
    else:
        usable = weapons.usable(item, art, content, world)
        value = f"加成 {_pct(weapons.bonus(item, art, content, world))}{weapons.CLASH_NOTE if weapons.clashes(item, art) else ''}" if usable else None
        fit, kind = (FITS if usable else UNFITS), weapons.NOUNS.get(item.kind, item.kind)
    worn = equipment.worn(state.player, item.slot)
    return {
        "id": item.id, "slot": item.slot, "name": item.name, "grade": equipment.grade(item), "kind": kind,
        "attribute": item.attribute, "value": value, "fit": fit, "glow": glow_of(item),
        "first": bool(report.get("first")) and item.secret is not None,
        "where": "worn" if worn is not None and worn.id == item.id else "rack",
        "divine": forge_secrets.unnamed_originals(state, world).get(item.id),
        "unit": equipment.unit_for(item.slot, item.kind),  # 定名表單那一句的量詞（FB-197：防具一件、拳套一副、其他兵器一把）
        "tactic": tactics.item_lines(content, item),  # 神器的特技（本命戰法第三批），沒有是空的
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
        "sub": sub, "coat": _coat(item), "art": mounts.art_of(item), "bars": _bars(content, item), "fed": None, "compare": "", "action": action,
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
    sale, price = mounts.shop_item(state, content), mounts.price(state, content)
    problem = mounts.buy_problem(state, content)
    note = territory.price_note(state, content)  # 名聲 4.1：馬價後面寫原因
    stalls.append(_stall(content, sale, "sale", f"{mounts.TIER_NAMES.get(sale.tier, '')}・{price} 兩{note}", {
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
HAVE_NOTE = "你有 {n} {unit}合用"  # 待 joy 潤：求兵的告示上
NO_FIT = "你身上沒有合用的"  # 待 joy 潤：求兵交不出時，放大的紙上「交出…」灰掉的原因
PRIZE_CHIP = "重賞"  # 待 joy 潤：21 天季告示正面那一格（FB-391；草圖丙）
PRIZE_SHORT = "另有重賞"  # 待 joy 潤：告示上（放大的紙上，賞那一段照 reward_text 寫是哪一種）
DROP_ASK = "把「{title}」放回榜上？放回去就不算你的了。"  # 待 joy 潤：放棄先問一次（選單上的 bounty:drop 沒有問句，問在網頁那一層）


def _headline(title: str) -> str:
    """告示上那一行大字：短標題「・」後面那一段（「打探・湖邊」→「湖邊」）。"""
    return title.partition("・")[2] or title


def board_view(state: GameState, content: Content, world: WorldStateStore) -> dict:
    """懸賞榜的店面（第四節）：最上面一排手上揭著的（bounties.mine）；木板上是看得到的告示（bounties.visible，同選單的第二層），
    揭著的在前、交得出的求兵其次、其餘照現在的順序。每一張寫哪一方掛的、標題、要做什麼、賞、期限與名額（紙上的 due_line、告示上短的 due_short，FB-196）、重賞、求兵
    你有幾件合用（fitting）；底下那一顆照現在的選項 id：揭著的「放棄」（bounty:drop，問句在網頁）、求兵「交出…」（bounty:pick，
    交不出照 only_original 或 NO_FIT）、其餘「揭下」（bounty:take，揭不了照 take_problem）。第三層開著（bounty_pick 指著一張還交得出的；
    同 Game._bounty_options 的判法）時多 picked 與 hand_in（hand_in_options 的每一顆，回到懸賞榜那一顆除外）。掛單的人（通緝的 poster）
    不寫：照現在的選單寫陣營，畫面不露出誰是假人（設計 6.6）。"""
    p = state.player
    shown = bounties.visible(state, content)
    mine = bounties.mine(state, content)
    mine_ids = {b.id for b in mine}
    picked = next((b for b in shown if b.id == p.bounty_pick and b.kind in bounties.GIVE_KINDS), None)
    picked_items = bounties.fitting(state, content, world, picked) if picked is not None else []
    if not picked_items:
        picked = None  # 那一張下榜了、交不出了就當它不存在（同 _bounty_options）
    ranked = []
    for order, b in enumerate(shown):
        title = bounties.title(content, b)
        note = {
            "id": b.id, "kind": b.kind, "kind_name": bounties.KIND_NAMES.get(b.kind, b.kind), "issuer": bounties.issuer(content, b),
            "title": title, "head": _headline(title), "how": bounties.how(content, b, state), "reward": bounties.reward_text(state, content, b),
            "due": bounties.due_line(state, content, b), "short": bounties.due_short(b, content, state.world), "prize": PRIZE_SHORT if bounties.has_prize(content, b) else "",
            "held": b.id in mine_ids, "have": "",
        }
        tags = bounties.reward_tags(state, content, b)
        if tags is not None:  # 21 天季（第 5 批畫面第三組丙）：紙上的小籤、告示角上寫銀兩的小朱印、照等級的那一句
            note.update(tags=tags, corner=bounties.reward_bits(state, content, b).silver_short, level=bounties.level_note(state, content, b),
                        gift=bounties.gift_short(state, content, b), prize_chip=PRIZE_CHIP if note["prize"] else "")  # 附贈與重賞一格（FB-391）
        rank = 2
        if b.id in mine_ids:
            rank = 0
            note["action"] = {"id": f"bounty:drop:{b.id}", "verb": "drop", "enabled": True, "why": None, "confirm": DROP_ASK.format(title=title)}
        elif b.kind in bounties.GIVE_KINDS:
            items = bounties.fitting(state, content, world, b)
            if items:
                rank, note["have"] = 1, HAVE_NOTE.format(n=len(items), unit=bounties.unit_of(b))
            # 交不出的原因照規則：只有神器原品或本命兵器對得上的照實寫，不是才寫 NO_FIT
            why = None if items else (bounties.only_original(state, b).strip("（）") or NO_FIT)
            note["action"] = {"id": f"bounty:pick:{b.id}", "verb": "pick", "enabled": bool(items), "why": why}
        else:
            problem = bounties.take_problem(state, content, b)
            note["action"] = {"id": f"bounty:take:{b.id}", "verb": "take", "enabled": problem is None, "why": problem}
        ranked.append((rank, order, note))
    hand_in = []
    if picked is not None:
        hand_in = [
            {"id": o.id, "label": o.label, "enabled": o.enabled}
            for o in bounties.hand_in_options(state, content, world, picked, picked_items) if o.id != bounties.UNPICK_ID
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


# ── 擂台（擂台賽設計；Joy 2026-10-14「擂台應該要是獨立的一頁，你這樣太混雜了」）：跟三間店同一層，台下、擂台榜兩頁，打到一半整頁是這一場 ──
ARENA_SIGN = "江湖擂台"  # 待 joy 潤：招牌（擂台哪裡都上得了，不寫地名）
ARENA_LINES = {  # 待 joy 潤：主事那一句（照你此刻的情形，不擲骰）
    "new": "擂台主事拱手：「報上名號、留個分身守擂，排到榜尾；往前三名內的人，你都挑得。」",
    "joined": "擂台主事拱手：「台上的人都留了分身。贏了，名次跟他換。」",
    "top": "擂台主事拱手：「天下第一，就等著別人來挑了。」",
    "fight": "台下圍了一圈人，等著看這一場。",
    "won": "台下一陣喝采。",
    "lost": "台下有人搖頭，也有人替你可惜。",
    "drew": "台下議論紛紛，分不出高下。",
}
YIELD_ASK = "認輸下台？這一場算你落敗。"  # 待 joy 潤：認輸先問一次
NO_ENTRY = "你還沒報名守擂。報了名排到榜尾，挑得了排在你前面三名內的人，旁人也挑得到你的分身。"  # 待 joy 潤
JOIN_NOTE = "報名、更新分身、挑擂都不花體力，一天挑 {n} 次；分身照此刻的身手，名次與戰績不動。"  # 待 joy 潤
NOBODY_YET = "擂台榜上還沒有人。"  # 待 joy 潤
WAGES_NOTE = "每天 00:00 照名次發俸：第一名銀兩 {silver}、名望 {fame}；前 {n} 名都有。"  # 待 joy 潤：擂台榜底下


def _fight_view(state: GameState, content: Content) -> dict:
    fight = state.player.arena
    log = list(fight.lines)
    lock = tactics.locks(fight.bout)  # 本命戰法（第二批）：使不出來的招灰掉、身上的狀態、看穿了架勢一定是真的
    return {
        "id": fight.id,  # 擂台動畫：認是不是同一場（換一場從頭演）
        "looks": arena.looks_view(fight.looks, fight.skins),  # 擂台動畫：兩邊手上的兵器種類與形象
        "foe": fight.foe.name,
        "arts": list((state.world.arena.get(fight.foe_key).arts if state.world.arena.get(fight.foe_key) else [])),
        "round": fight.round + 1,
        "rounds": fight.rounds,
        "edge": round(fight.edge),
        "edge_words": duel_rules.edge_words(fight.edge),
        "me": {"name": state.player.name, "hp": round(fight.me.hp), "cap": round(fight.me.hp_cap)},
        "foe_hp": {"name": fight.foe.name, "hp": round(fight.foe.hp), "cap": round(fight.foe.hp_cap)},
        "tell": fight.tell,
        "tell_note": (tactics.SEEN_NOTE if lock.sees else arena.TELL_NOTE).strip("（）"),
        "status": tactics.status_text(fight.bout),
        "howto": arena.HOWTO,
        "log": log,
        "moves": [{"id": f"arena:{m}", "move": m, "label": duel_rules.move_label(m) + (tactics.lock_note(m) if m in lock.no_moves else ""),
                   "enabled": m not in lock.no_moves} for m in MOVES],
        "yield": {"id": arena.YIELD_ID, "label": "認輸", "confirm": YIELD_ASK},
        "gamble": {"op": "duel_text", "prompt": arena.PROMPT_SHORT, "note": arena.GAMBLE_NOTE,
                   "locked": tactics.NO_GAMBLE.strip("（）") if lock.no_gamble else ""},
    }


def _ring_short(w, me: str, foe, content: Content, left: int, problem: str | None) -> list[str] | None:
    """挑不了的那一顆鈕上寫的兩行（粗字、小字）：冷卻寫還要等多久、次數用完寫幾點換日（Joy 2026-10-16「看不出還有多久才能打」）；
    整句原因照舊在 why。挑得了是 None。"""
    if problem is None:
        return None
    if left <= 0:
        return ["明日 00:00", "今天挑完了"]
    wait = arena.cool_left(w, me, foe, content.config.arena)
    if wait > 0:
        return [arena.wait_text(wait / content.config.time_scale) + "後", "可再挑"]
    return [problem, ""]


def arena_view(state: GameState, content: Content, world: WorldStateStore, power: float, left: int, bare: float | None = None) -> dict:
    """擂台那一頁：打到一半是這一場（fight）；不然是台下（自己的名次、稱號與分身，報名鈕，挑得到的人各一張、挑擂鈕）與擂台榜（board），
    剛打完的那一場有收場卡（result，PlayerState.arena_last）。鈕都是現在的選項 id（arena:join、arena:fight:<名號鍵>、arena:<招>、
    arena:yield、arena:back），挑不挑得了照 arena.challengers（同選單）。left 是今天還能挑幾次。只讀。
    bare：自己不含玉璽碎片戰力的威力（改版 FB-625：挑人卡上的「身手」兩邊都照不含碎片的算）；不給就是 power。"""
    p, w, cfg = state.player, state.world, content.config.arena
    mine = arena.entry_of(w, p.name)
    result = p.arena_last
    if p.arena is not None:
        mood = "fight"
    elif result is not None:
        mood = "won" if result.tier in arena.WIN_TIERS else "drew" if result.tier == "僵持" else "lost"
    else:
        mood = "new" if mine is None else "top" if mine.rank == 1 else "joined"
    me = {
        "joined": mine is not None,
        "rank": mine.rank if mine is not None else None,
        "title": arena.title_for(mine.rank) if mine is not None else None,
        "record": arena.record_text(mine) if mine is not None else "",
        "arts": list(mine.arts) if mine is not None else [],
        "note": JOIN_NOTE.format(n=cfg.per_day) if mine is not None else NO_ENTRY,
        "join": {"id": arena.JOIN_ID, "label": "更新分身" if mine is not None else "報名守擂", "enabled": power > 0,
                 "why": None if power > 0 else arena.NO_ARTS},
    }
    foes = []
    for e, problem in arena.challengers(w, content, p.name, left):
        foes.append({
            "id": f"arena:fight:{name_key(e.name)}", "name": e.name, "rank": e.rank, "title": arena.title_for(e.rank),
            "record": arena.record_text(e), "arts": list(e.arts), "strength": "身手" + arena.strength_words(content, power if bare is None else bare, e.shown),
            "enabled": problem is None, "why": problem, "short": _ring_short(w, p.name, e, content, left, problem),
            "famed": arena.FAMED_NOTE.format(n=arena.reach_of(e, cfg)) if e.famed else "",  # 名聲 4.7
        })
    nobody = ""
    if mine is not None and not foes:
        nobody = arena.NOBODY if mine.rank == 1 else arena.NOBODY_AHEAD
    rows = [dict(row, me=name_key(row["name"]) == name_key(p.name)) for row in arena.board(w, cfg)]
    top_silver, top_fame = cfg.wages[0] if cfg.wages else (0, 0)
    return {
        "shop": "arena",
        "sign": ARENA_SIGN,
        "silver": p.stats.get("silver", 0),
        "purse": f"今天還能挑 {left} 次" if left > 0 else arena.SPENT_PURSE,
        "line": ARENA_LINES[mood],
        "back": arena.BACK_ID,
        "me": me,
        "foes": foes,
        "nobody": nobody,
        "board": rows,
        "board_empty": "" if rows else NOBODY_YET,
        "wages": WAGES_NOTE.format(silver=top_silver, fame=top_fame, n=len(cfg.wages)) if cfg.wages else "",
        "fight": _fight_view(state, content) if p.arena is not None else None,
        "result": {"id": result.id, "foe": result.foe, "tier": result.tier, "lines": list(result.lines),
                   "changes": list(result.changes), "looks": arena.looks_view(result.looks, result.skins)} if result is not None and p.arena is None else None,
    }
