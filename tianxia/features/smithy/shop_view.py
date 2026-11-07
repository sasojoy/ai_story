"""鐵匠鋪的店面畫面資料（店面獨立介面設計第二節；第二輪第 93 批，原本在 tianxia/shopview.py；計畫 docs/superpowers/plans/2026-11-07-第二輪-第93批.md）。

只讀：不改數值、不碰亂數、不 import engine（next_rule 只記這一季講過哪幾句）。每一個「做不了」的原因都從現在的規則函式拿（smithing.forge_problem、temper_problem、
weapons.buy_problem、repair_problem……），網頁不自己判斷規則。店共用的（掌櫃那一句、素材格的排序、階名）在 core/shop_base。
page 是店面那一頁的組法（Feature.shop_view 轉交；core/features.shop_page 問）。
靠 tianxia/shopview.py 那個殼的測試（tests/gear/test_four_tiers.py、test_weapons.py、tests/arts/test_renown_trade.py、tests/battle/test_tactics_bouts.py……）改這一檔時 test_for 挑不到：另外跑 scripts/test_for.py tianxia/shopview.py。
"""
from __future__ import annotations

from tianxia import armor, art_cards, economy, equipment, forge_secrets, four_tiers, rules, silver, tactics, team, territory, weapons
from tianxia import prologue as prologue_rules
from tianxia.characters import name_key
from tianxia.core.shop_base import TIER_NAMES, attribute_rank, line_text
from tianxia.models import WEAPON_KINDS, Content
from tianxia.state import Equipment, GameState, GearFind
from tianxia.world_state import WorldStateStore

from . import smithing

FORGED_KEYS = {"下品": "forge_low", "中品": "forge_mid", "上品": "forge_high"}


def forged_key(item: Equipment) -> str:
    """打完一爐那一句照什麼分（1.4）：神器（原品、仿品）＞名器＞品質。"""
    if item.original or item.copy_of is not None:
        return "forge_divine"
    if equipment.is_named(item):  # 隱藏配方的名器、四階擲出的名器（正式季整合 5.2）
        return "forge_named"
    return FORGED_KEYS.get(item.quality, "forge_low")


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
    rid = armor.REPAIR if slot == "armor" else "smith:repair"
    problem = (armor if slot == "armor" else weapons).repair_problem(state, content)
    tproblem = smithing.temper_problem(state, content, slot)
    unfit = weapons.unfit_note(item).lstrip("・") if slot == "weapon" and weapons.worn_unfit(state, art, content, world) else ""
    return {
        "item": {"id": item.id, "name": item.name, "grade": equipment.grade(item), "wear_word": equipment.WEAR_WORDS[slot],
                 "wear": item.edge, "tempers": item.tempers, "temper_max": equipment.temper_cap(item, content),  # 照這一件的品質（3.6）
                 "wear_note": equipment.wear_note(item, content)},
        "empty": "",
        "repair": {"id": rid, "use": _repair_use(state, content, slot), "enabled": problem is None, "why": problem},
        "temper": {"id": smithing.ARMOR_TEMPER if slot == "armor" else smithing.TEMPER, "use": _temper_use(state, content, slot),
                   "enabled": tproblem is None, "why": tproblem},
        "unfit": unfit,
    }


def _repair_use(state: GameState, content: Content, slot: str) -> str:
    """修那一顆的小字（身上那張卡與裝備庫每一列共用）：用哪一種一階素材＋工錢；背包裡沒有一階素材寫「一個一階素材」。"""
    material = equipment.repair_material(state, content)
    use = f"{content.materials[material].name}×1" if material is not None else "一個一階素材"
    return f"{use}＋{smithing.rules_of(content, slot).repair_silver} 兩"


def _temper_use(state: GameState, content: Content, slot: str, item_id: str | None = None) -> str:
    """淬煉那一顆的小字：自動挑的那一種一階素材（鐵匠鋪與合成流程 3.7，料固定一階，數量多的先）＋工錢（照這一件的階，item_id 是裝備庫那一件
    的 id 時照那一件；一階的裝備不收錢就不寫）；沒有料是空字串（原因在 why）。"""
    mid = smithing.temper_material(state, content, slot, item_id)
    if mid is None:
        return ""
    cost = smithing.temper_price(state, content, slot, item_id)
    return f"{content.materials[mid].name}×1" + (f"＋{cost} 兩" if cost else "")


def _rack(state: GameState, content: Content, world: WorldStateStore, slot: str, art, neigong) -> dict:
    """裝備庫那一頁（2.5）：這一欄裝備庫裡的每一件，列的寫法同修練頁（art_cards.gear_rows 那一欄：keep、confirm、divine）。
    排法：等著定名的原品最前面，再照修好之後好的在前（防具 armor.fresh_cut；兵器照刀口磨利之後的加成，配不上的是 0）。
    每一列多四樣（鐵匠鋪與合成流程 3.4，裝備庫併頁；網頁不自己判斷規則）：
    repair／temper：{ok, why, use}，這一件現在修、淬煉得了嗎（照 weapons／armor.repair_problem、smithing.temper_problem 的 item_id 版，
    原因同身上那張卡：錢不夠、沒有一階的料、淬滿、還不用修）、鈕上小字 use（「精鐵砂×1＋5 兩」「精鐵砂×1＋80 兩」；淬煉的料固定一階、工錢照裝備的階，一階的裝備淬煉不收錢就沒有「＋」）；
    into：{name, count}，拆了得什麼（equipment.dismantle_material，一件一個；拆不得的原品、本命兵器是 None），批量拆解確認單每一行用；
    tempers 本來就在列上（淬過幾次，確認單寫「淬過 N 次一起沒了」）。"""
    gear = art_cards.gear_rows(state, content, world)
    block = next((b for b in gear["slots"] if b["slot"] == slot), None)
    items = {item.id: item for item in equipment.in_slot(state.player, slot)}
    gear_rules = armor if slot == "armor" else weapons

    def fresh(row) -> float:
        item = items[row["id"]]
        if slot == "armor":
            return armor.fresh_cut(item, neigong, content)
        return weapons.bonus(item.model_copy(update={"edge": 100}), art, content, world)

    def buttons(row: dict) -> dict:
        item = items[row["id"]]
        repair, temper = gear_rules.repair_problem(state, content, item.id), smithing.temper_problem(state, content, slot, item.id)
        into = None if equipment.kept(item) else {"name": equipment.dismantle_material(content, item).name, "count": 1}
        return {**row,
                "repair": {"ok": repair is None, "why": repair, "use": _repair_use(state, content, slot)},
                "temper": {"ok": temper is None, "why": temper, "use": _temper_use(state, content, slot, item.id)},
                "into": into}

    rows = [buttons(row) for row in (block["rack"] if block is not None else [])]
    rows.sort(key=lambda row: (row["divine"] is None, -fresh(row)))
    return {"rows": rows, "used": gear["used"], "cap": gear["cap"]}


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


FURNACE_OP = "smith_furnace"  # 爐火上「看火候」那一顆叫的 op（/api/do/smith_furnace；店開著時選單上沒有 act:furnace，不能送那個 id）


def furnace_view(state: GameState, content: Content, day: int | None, prologue: bool = False) -> dict | None:
    """打造頁爐火那一塊（鐵匠鋪與合成流程 3.2；smith_view 的 forge.furnace）：price 一次幾兩、ready 看過了還沒開爐（下一爐照新基準）、
    used_today 今天看過而且已經用掉了、problem 此刻看不了的原因（照 silver.furnace_problem：序章、看過了還沒開爐、今天用掉了、錢不夠；
    看得了是 None）、id 按下去叫的 op（FURNACE_OP）。價錢、一天一次全照 silver.furnace，跟打點帳簿同一個 furnace_ready。
    銀兩出口關著（silver.on 是 False：週末、14 天季、設定關）是 None：網頁不畫那一塊，打造頁照舊。day 是回體丹的換日（Game._pill_day）；
    沒給（只讀的直接呼叫）也是 None。"""
    if day is None or not silver.on(content, state.world):
        return None
    p = state.player
    return {
        "price": content.config.silver_outlets.furnace_silver, "ready": p.furnace_ready,
        "used_today": not p.furnace_ready and p.furnace_day == day,
        "problem": silver.furnace_problem(state, content, day, prologue), "id": FURNACE_OP,
    }


DIVINE_YOU = "你"  # 待 joy 潤（鐵匠鋪與合成流程 3.8）：神器頁「原品在誰手上」那一格，原品在你手上寫這一個字，別人寫名號


def divine_view(state: GameState, content: Content, world: WorldStateStore) -> dict | None:
    """鐵匠鋪的「神器」頁（鐵匠鋪與合成流程 3.8；smith_view 的 divine）。不是輪替季（WorldState.divine_lineup 是 None）整包 None。
    只讀、不碰亂數；神器紀錄（world.divine_records）只在輪替季讀、一次一份。

    seen（頁面上半「江湖已見」）：**這一季**已經有人打出原品的神器，每一件一列 {id, name, owner, copies, mine, solved_only}——
    name 定了名寫定名、沒定寫譜名（同神器譜）；owner 是原品主人（名號，是你寫 DIVINE_YOU）；copies 全服仿品幾把；mine 是你手上有的那一把
    （"original" 原品在手、"copy" 仿品在手、None 未有，照 forge_secrets.held_divine）；solved_only 是你自己鑄譜上打中過
    （PlayerState.divine_solved，跨季帶著走）、這一季又現世、還沒人打出的那一件——只有你自己看得到（正式季整合 5.10 的例外：你的鑄譜本來
    就寫「這一季已現世」），owner、copies 是空的。
    collected（下半「收藏 M／N」）：內容裡全部的神器各一格（N 照內容數）{id, name, have, forged, now}——forged 是任何一季有人打出過原品
    （divine_records：全服登記的加上線前照季分的），有了才給 id 與名字（沒打出過的 id、name 都是 None，網頁畫「？」、不可點）；have 是你手上有；
    now 是這一季打出的。

    **守 5.10**：這一季輪到、還沒人打出、自己也沒打中過的神器，整包裡不出現它的 id 與名字——所以不用全服登記的 seen（開季蓋章就寫），
    收藏冊沒打出過的格子連 id 都不給（不然「哪幾格有 id」就是名單），江湖已見只列這一季才打出原品的（之前季打出的只在收藏冊）。
    假人跟真人一樣：原品主人照神器譜現在的寫法寫名號。"""
    lineup = state.world.divine_lineup
    if lineup is None:
        return None
    p = state.player
    season = world.get_season_number()
    latest: dict[str, tuple[int, GearFind]] = {}
    for found_in, find in world.divine_records():  # 照季排好的：同一件隔了好幾季才有新的一筆時，後面的蓋掉前面的
        latest[find.secret] = (found_in, find)
    seen: list[dict] = []
    solved: list[dict] = []
    cells: list[dict] = []
    for recipe in (r for r in content.forge_secrets.values() if r.divine):
        held = forge_secrets.held_divine(p, recipe.id)
        mine = None if held is None else "original" if held.original else "copy"
        record = latest.get(recipe.id)
        if record is None:
            if recipe.id in lineup and recipe.id in p.divine_solved:
                solved.append({"id": recipe.id, "name": recipe.name, "owner": None, "copies": 0, "mine": None, "solved_only": True})
            known = held is not None  # 手上有就一定有人打出過（資料對不上時也不把自己手上的畫成「？」）
            cells.append({"id": recipe.id if known else None, "name": recipe.name if known else None, "have": known, "forged": known, "now": False})
            continue
        found_in, find = record
        name = find.divine_name or find.title
        if found_in == season:
            owner = DIVINE_YOU if find.owner is not None and name_key(find.owner) == name_key(p.name) else find.master_shown or find.owner
            seen.append({"id": recipe.id, "name": name, "owner": owner, "copies": find.copies, "mine": mine, "solved_only": False})
        cells.append({"id": recipe.id, "name": name, "have": held is not None, "forged": True, "now": found_in == season})
    return {"seen": seen + solved, "collected": {"have": sum(1 for cell in cells if cell["have"]), "total": len(cells), "cells": cells}}


def smith_view(state: GameState, content: Content, world: WorldStateStore, day: int | None = None, prologue: bool = False) -> dict:
    """鐵匠鋪的店面（第一、二節）：招牌、銀兩、掌櫃的話、出店與兵器防具切換的選項 id，四頁的資料（輪替季多一頁神器，divine，見 divine_view）。
    day、prologue 是 Game 給的（回體丹的換日、在不在序章），forge.furnace 要用；沒給 day 的直接呼叫 forge.furnace 是 None。"""
    p = state.player
    art, neigong = _arts(state, content, world)
    page = equipment.page(p, content)
    forge = _forge(state, content, world, page, art)
    forge["furnace"] = furnace_view(state, content, day, prologue)
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
        "forge": forge,
        "divine": divine_view(state, content, world),  # 神器頁（3.8）：輪替季才有，其餘 None（鐵匠鋪照四頁）
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


BLACK_MARKET ="（黑市價）"  # 名聲 5.2：寇賣素材的鈕上（待 joy 潤）
BLACK_MARKET_CAP = "照黑市價收"  # 收購那一段的標題


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


def page(ctx) -> dict:
    """鐵匠鋪那一頁（原本 core/page_view.shop_view 那一支）：打造頁的爐火（鐵匠鋪與合成流程 3.2，forge.furnace）要回體丹的換日與序章：Game 才知道。"""
    s, c = ctx.state, ctx.content
    view = smith_view(s, c, ctx.world, day=ctx._pill_day(), prologue=prologue_rules.active(s, c))
    view["trade"] = trade_view(s, c, ctx._pill_day())  # 素材買賣（素材與經濟設計第四、五節）：收購、升階都關著是 None
    return view
