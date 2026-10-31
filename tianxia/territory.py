"""地盤易手（docs/superpowers/specs/2026-10-14-出陣探索與地盤-design.md 第四節）。

地盤開著（on）就是領地爭奪（conquest.py）：控制方只照佔領（攻城戰、翻地、時刻表指定、管理者改），這裡留共用的那幾樣——
大本營（劇本陣營的 join_at）、控制方（controller → conquest.holder）、站的隊伍（squads_at）、地盤福利（price_*）、
易手的天下大事與每週快照（_announce、_snapshot，conquest 叫）。舊的拔河、豪強割據、工事（2026-10-27 企劃者選「拿掉舊玩法和它的測試」）拿掉了。
存在 WorldState.territory（整份 JSON，資料庫結構不動）；None＝這一季還沒算過：第一次算不發天下大事（設計第六節）。
只讀寫 WorldState；天下大事與江湖史直接記進 world.rumors／world.chronicle（rules.add_rumor 要 GameState）。
沒有地盤的季（on 是假：沒有第一季規則、劇本沒寫區塊）：controller 回 None，squads_at 照 Location.enemies。
rules → territory 只在 rules.change_trend 裡延後 import；這裡 import rules 整個模組、呼叫時才取屬性。"""
from __future__ import annotations

from . import calendar, renown, rules
from .models import FRONT_KEY, Content
from .state import GameState, Rumor, TerritoryState, TerritoryWeek, WorldState

FLIP_LINE = "{place}落入{side}之手。"  # 待 joy 潤：易手那一刻的天下大事與江湖史（設計 4.3 第 2 點）
RETAKE_LINE = "{side}收復{place}。"  # 待 joy 潤（FB-252）：這一季佔過那裡的一方再拿回來（TerritoryState.held）
CONTROL_LINE = "此刻由{side}控制"  # 待 joy 潤：輿圖詳情欄局勢那一行


SIDES = ("guan", "huang")  # 交戰兩軍（領地爭奪設計 4.1：豪強不佔地；conquest.SIDES 同一份）


def on(content: Content) -> bool:
    """地盤（＝領地爭奪，conquest.on）開著：第一季規則開著（豪強分屬兩軍跟著它，allied.on）、劇本有官軍與黃巾、寫了區塊
    （領地爭奪設計 4.1、4.10）。舊的拔河與割據（沒有第一季規則的季）2026-10-27 拿掉：那種季沒有地盤。"""
    cfg, scen = content.config, content.scenario
    if not cfg.season_one or scen.territory is None or not scen.territory.blocks:
        return False
    return set(SIDES) <= {f.id for f in scen.factions}


def line_of(content: Content, loc_id: str) -> str | None:
    """這個地點是哪一條戰線上的戰線地點（只看內容，不看季）；不是戰線地點是 None。出陣只在這種地點（sortie.mode）。"""
    loc = content.locations.get(loc_id)
    if loc is None:
        return None
    fronts = set(rules.front_ids(content))
    for key in loc.train_trend:
        line = rules.front_of(content, loc_id) if key == FRONT_KEY else key
        if line in fronts:
            return line
    return None


def bases(content: Content) -> dict[str, str]:
    """大本營：劇本陣營的投靠點 → 那個陣營（設計 4.1）。"""
    return {loc_id: f.id for f in content.scenario.factions for loc_id in f.join_at}


def held_bases(world: WorldState, content: Content) -> dict[str, str]:
    """算得上誰的地盤的大本營（控制方、各佔幾處讀它）：豪強的投靠點不算哪一方的地盤（豪強分屬兩軍，不在戰線上、豪強依附
    哪一軍都有；FB-274：以前算成豪強佔著，輿圖大區那一行多「豪 1」、三色條多一段綠的）。地盤只在第一季規則的季有，那種季豪強
    一律分屬兩軍（allied.on），所以不再問開關。"""
    return {loc_id: side for loc_id, side in bases(content).items() if not content.scenario.faction(side).allies}


def unheld(world: WorldState, content: Content, loc_id: str) -> bool:
    """這個地點是不算誰的地盤的大本營（held_bases 拿掉的那幾處）：存檔裡修好之前記下的控制方、每週的快照都照它略過。"""
    return loc_id in bases(content) and loc_id not in held_bases(world, content)


def sides(content: Content, line: str) -> tuple[str | None, str | None]:
    """這條戰線兩頭是誰：（目標往 0 推的陣營, 目標往 100 推的陣營）；照劇本陣營的 goals（內容寫的戰線 id，不換鍵）。"""
    low = next((f.id for f in content.scenario.factions if f.goals.get(line, 0) < 0), None)
    high = next((f.id for f in content.scenario.factions if f.goals.get(line, 0) > 0), None)
    return low, high


def line_value(world: WorldState, content: Content, line: str) -> int:
    """拔河看的值：這條戰線照這一季的規則換成真的會動的線（第一季是它自己；規則關著的季是黃巾聲勢）。"""
    return rules.world_trend_value(world, content, rules.resolve_trend(content, world, line) or line)


def _announce(world: WorldState, content: Content, t: TerritoryState, before: dict[str, str]) -> None:
    """換了控制方的地點各發一句天下大事、記一筆江湖史：這一季佔過那裡的一方再拿回來寫「收復」（RETAKE_LINE，FB-252），
    否則「落入…之手」（FLIP_LINE）。發完把此刻的控制方記進 t.held。"""
    for loc_id, side in t.control.items():
        if before.get(loc_id) not in (None, side):
            line = RETAKE_LINE if side in t.held.get(loc_id, []) else FLIP_LINE
            text = line.format(place=content.locations[loc_id].name, side=content.scenario.faction_name(side, side))
            world.rumors.append(Rumor(time=world.time, text=text, location=loc_id, layer="world"))
            world.chronicle.append(Rumor(time=world.time, text=text))
    _remember(t)


def _remember(t: TerritoryState) -> None:
    for loc_id, side in t.control.items():
        sides = t.held.setdefault(loc_id, [])
        if side not in sides:
            sides.append(side)


def update(world: WorldState, content: Content) -> None:
    """重算一次（設計 4.2 最後一段）：rules.change_trend 真的動了一條線、決戰結果直接寫進季（Game._apply_outcome_trends_and_flags）、
    推進世界（world.advance_world_state）時叫。地盤開著就是領地爭奪（conquest.update：不拔河、不割據）；關著什麼都不做。"""
    if not on(content):
        return
    from . import conquest  # noqa: PLC0415  conquest → territory：在函式裡 import，避免循環

    conquest.update(world, content)


def assign(world: WorldState, content: Content, given: dict[str, str]) -> None:
    """大事指定易手（TimetableOutcome.control，設計 4.2 第 3 點）：指定了就是指定了（conquest.assign，重算三條線）。大本營不收（載入時也擋）。"""
    if not on(content) or not given:
        return
    from . import conquest  # noqa: PLC0415

    conquest.assign(world, content, given)


START_WEEK = 0  # TerritoryState.weeks 裡開季那一刻的鍵：這一季第一次算地盤就在第 1 週時才記（中途上線的季沒有，FB-264）


def _snapshot(world: WorldState, content: Content, t: TerritoryState) -> None:
    """把「這一週」那一格蓋成此刻的樣子（輿圖升級設計第九節）：控制方、每條戰線拔河看的值（line_value）。
    割據（TerritoryWeek.geju）2026-10-31 拿掉，不再記；舊存檔裡記過的照留、不讀。"""
    week = calendar.point(world.time, content, world).week
    t.weeks[week] = TerritoryWeek(
        control=dict(t.control), fronts={line: line_value(world, content, line) for line in content.scenario.territory.lines},
    )


def week_at(world: WorldState, week: int) -> TerritoryWeek | None:
    """第 week 週的地盤：記到的最後一筆不晚於 week 的（沒記到的週照前一週補）；那之前什麼都沒記、或這一季還沒算過是 None。"""
    t = world.territory
    if t is None:
        return None
    known = [w for w in t.weeks if w <= week]
    return t.weeks[max(known)] if known else None


def controller(world: WorldState, content: Content, loc_id: str) -> str | None:
    """這個地點此刻歸誰（領地爭奪：只有區塊有控制方，中立而沒人佔是 None，conquest.holder）；地盤關著是 None。"""
    if not on(content) or unheld(world, content, loc_id):
        return None
    from . import conquest  # noqa: PLC0415

    return conquest.holder(world, content, loc_id)


def squads_at(world: WorldState, content: Content, loc_id: str) -> list[str]:
    """這個地點此刻站的隊伍（設計 4.3 第 1 點）：寫了 garrison 的地點是無陣營的那幾路（Location.enemies 裡的，誰控制都在）加上
    控制方那一組；其餘（開關關著、大本營沒寫 garrison）照 Location.enemies。遊歷、出陣、探索、懸賞、攻城、輿圖都讀它。"""
    loc = content.locations[loc_id]
    from . import conquest  # noqa: PLC0415

    if on(content) and conquest.start_kind(world, content, loc_id) == conquest.NEUTRAL:
        return conquest.neutral_squads(world, content, loc_id)  # 領地爭奪：開季中立的區塊照它自己那一套，不看控制方（設計 3.3）
    side = controller(world, content, loc_id)
    garrison = content.scenario.territory.garrison.get(loc_id) if side is not None else None
    if not garrison:
        return list(loc.enemies)
    neutral = [sid for sid in loc.enemies if sid in content.squads and content.squads[sid].faction is None]
    return neutral + [sid for sid in garrison.get(side, []) if sid not in neutral]


def price_factor(world: WorldState, content: Content, faction: str | None, loc_id: str) -> float:
    """地盤福利（設計 4.3 第 3 點）：在自己陣營控制的地方 own_price、別的陣營控制的地方 enemy_price；散人、沒有控制方是 1。
    faction 是那一邊（rules.side_of）。豪強分屬兩軍的季，豪強的投靠點不算哪一軍的地盤（held_bases：沒有控制方），照原價。
    領地爭奪開著的季（conquest.on），散人在開季中立的區塊算自家（設計 4.6：中立地算散人的地盤，不論此刻歸誰）。"""
    from . import conquest  # noqa: PLC0415

    cfg = content.config.territory
    if conquest.cooling(world, content, loc_id):  # 領地爭奪：剛易手還在冷卻，那一塊的加成暫停（輿圖簡化設計 4.1）：誰來都照原價
        return 1.0
    if faction is None and conquest.is_home(world, content, None, loc_id):
        return cfg.own_price
    side = controller(world, content, loc_id)
    if side is None or faction is None:
        return 1.0
    return cfg.own_price if side == faction else cfg.enemy_price


def _land_here(state: GameState, content: Content, heal: bool = False) -> float:
    """此刻所在地的地盤福利（price_factor，照 rules.side_of）。heal：療傷——領地爭奪開著的季，新手期（roster.newbie）在敵方領地療傷
    不吃加價（裁決 4：潁川郡是黃巾新手出序章的第一站）。"""
    from . import conquest, roster  # noqa: PLC0415  roster → rules：延後 import

    p = state.player
    land = price_factor(state.world, content, rules.side_of(state, content), p.location)
    if heal and land > 1 and on(content) and roster.newbie(state, content):
        return 1.0
    return land


def price_here(state: GameState, content: Content, heal: bool = False) -> float:
    """此刻在這裡買東西的倍數（名聲設計 4.1）：地盤福利（price_factor）× 名望的店家折扣（renown.price_factor）。
    療傷、打造工錢、升階工錢、買馬都走這裡；輿圖詳情欄照舊只寫地盤（那是地點的，mapdata 讀 price_factor）。
    heal：療傷那一條（_land_here：領地爭奪的新手期在敵方領地不加價）。
    放在 territory 而不是 renown：territory → rules → renown，renown 再 import territory 就繞成環。"""
    return _land_here(state, content, heal) * renown.price_factor(state, content)


def price_parts(state: GameState, content: Content, heal: bool = False) -> list[str]:
    """價錢打折的原因，一樣一段：「自家地盤・九折」「名動一方・九四折」（名聲 4.1 的寫法）；名聲關著、兩樣都沒有是空的。
    醫館另有俠的那一半（renown.clinic_part），skillview.heal_note 接在後面、寫在同一個括號裡（FB-294）。heal 同 price_here。"""
    if not renown.on(content, "discount"):
        return []
    parts = []
    land = _land_here(state, content, heal)
    if land != 1.0:
        parts.append(("自家地盤" if land < 1 else "敵方地盤") + "・" + renown.discount_word(land))
    fame = renown.price_factor(state, content)
    if fame != 1.0:
        parts.append(f"{renown.fame_title(state, content)}・{renown.discount_word(fame)}")
    return parts


def price_note(state: GameState, content: Content) -> str:
    """價錢後面的原因（名聲 4.1「寫原因」）：「（自家地盤・九折，名動一方・九四折）」；名聲關著、兩樣都沒有是空字串
    （關著時一個字都不變：地盤福利以前也不寫原因）。"""
    return renown.reasons_text(price_parts(state, content))
