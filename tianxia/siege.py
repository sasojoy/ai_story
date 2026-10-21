"""領地爭奪第二批：攻城戰（設計 3.6、4.4；計畫第四章 Task 10～11；裁決 8、14）——決戰引擎的縮小版。

每個有區塊的大區一筆範本（content/battles.json 的 siege_<大區>，BattleDef.siege）：一幕 5 回合、偏離中線 40 提前收場，戰局照決戰以官軍為
正向。這一場打哪一塊、誰攻、開集結那一刻誰佔著記在 BattleInstance.siege（battle_instance.SiegeInfo）；攻城另存一串
（SharedWorldState.sieges），跟時刻表決戰、別的攻城戰同時打。名字一律「攻城・地點」（title）。

- 時程表上的那幾場是第 4 階的人下戰書排的（翻地與爭搶，輿圖簡化設計 4.4；conquest_day.place_letter），投票與 22:00 的結算拿掉了。
- 開集結（open_waiting）：時程表上到了開集結時候的那幾場（world.advance_world_state 記成 waiting）。那一刻重新看誰佔著（Review Focus 3：
  同一天先打的那一場、時刻表指定、管理者改了主人，後打的照打新的主人）；攻方自己已經是主人就作罷。起點照進度偏（start_trend）。
- 誰能站哪一格（join_problem）：攻方站自己那一格；打的是誰的區塊，那一方站守的那一格；單方攻中立地時另一格是守將（guard_side），
  另一軍站不進去、散人可以投效助守（裁決 8）。
- 兩軍同時攻同一塊中立地＝三方混戰（裁決 22，企劃者 2026-10-21）：守將留著、站第三格 battle_instance.GUARD，兩軍都打他、兩軍之間也互打，
  誰補上守將最後一刀誰拿下；回合打完守將沒倒，守住、照舊中立。散人可以投效兩軍之一或助守。守將的池子在集結結束那一刻照兩軍到場的人數定
  （size_melee_guard）。回合裡的規則在 battle_instance（resolve_round、_strike_guard）。
- 集結結束只有一軍到場（裁決 23，PM 2026-10-21）：另一軍一個人都沒來算棄權，這一場轉回單方攻中立地（lone_army）——攻方只剩到場的那一軍，
  守將站棄權那一軍那一格、池子照單方（Config.battle.generals.pool 第一個），之後守將照舊、戰線過了照原本的門檻就拿下，不用把守將打倒。
  兩軍都沒人到照舊作罷（void_absent，裁決 19）；兩軍都有人到照三方混戰。
- 留守（commanders）：守方是陣營時照龍頭上陣的挑法派那一區守方的大勢人物，沒有人物或中立地時是那裡最強的一路隊伍當守將（guard_squad）。
- 收場（verdict）：攻方贏（大勝或險勝）就易手（conquest.flip：照推滿那樣分紅、冷卻）；否則原主人留著（中立還是中立）、攻方的條砍半。
  三方混戰照誰補上最後一刀。攻方一個人都沒到（集結結束時）作罷、進度照留。
只 import models、state、battle_instance、generals、territory、conquest、conquest_day（作罷）、world_state 型別。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import atlas, battle_instance, conquest, conquest_day, generals, territory
from .battle_instance import GUARD, Commander, SiegeInfo
from .models import BattleDef, Content
from .state import DayNote, GameState, Rumor, SiegeSlot, WorldState

if TYPE_CHECKING:
    from .world_state import WorldStateStore

TITLE = "攻城・{place}"  # 待 joy 潤：畫面、戰報、天下大事一律走 title
MUSTER_LINE = "{title}：{who}的集結號角吹響了，開打前趕到{region}就能加入。"  # 待 joy 潤：開集結那一刻的天下大事
VOID_HELD = "{who}原定攻{place}，那裡已經是{who}的了，這一仗作罷。"  # 待 joy 潤：開集結那一刻攻方已經是主人（Review Focus 3）
VOID_ABSENT_NOTE = "攻方一個人都沒到，這一仗作罷，不算勝負。"  # 參戰者（守方、助守的人）那一則江湖紀錄
HELD_LINE = "{title}：{side}守住了{place}。"  # 待 joy 潤：攻方沒打下來的天下大事（打下來的照 territory 的「落入」那一句）
STALEMATE_LINE = "{title}：兩軍相持不下，{place}照舊沒人佔。"  # 待 joy 潤：兩軍同時搶同一塊中立地、那裡沒有守將（退回正面打）、戰局停在中線
# 三方混戰（裁決 22）；待 joy 潤
BLOW_RUMOR = "{title}：{who}替{side}補上最後一刀，{guard}倒下，{place}歸了{side}。"  # 天下大事（具名，天下大事一律寫名號）
BLOW_RUMOR_NOBODY = "{title}：{side}補上最後一刀，{guard}倒下，{place}歸了{side}。"
MELEE_HELD_LINE = "{title}：兩軍都沒能補上最後一刀，守軍守住了{place}，照舊沒人佔。"
MELEE_TAKEN_TITLE = "{side}補上最後一刀，拿下{place}"  # 戰報與紀錄的結果
MELEE_RULE = "守將的氣血照開打時兩軍到場的人數定，誰補上最後一刀誰拿下這一塊。"  # 三方混戰的規矩那一句（場景上跟著攻城那一條寫，scene_note）
MELEE_SCENE_LINE = "{attackers}同時攻{place}，守方{defender}兩頭迎戰；" + MELEE_RULE
MELEE_MIN_HEADS = 2  # 【開發】三方混戰守將的池子至少照幾個人算（一軍只到一個人也不會一碰就倒）
ABSENT_SCENE_LINE = "{absent}沒有人趕到，這一場只剩對面一軍來攻。"  # 待 joy 潤：三方混戰集結結束只有一軍到場（裁決 23），場景第二行多的一句
TAKEN_TITLE = "{side}{margin}，拿下{place}"  # 待 joy 潤：戰報與紀錄的結果
HELD_TITLE = "{side}守住{place}"
STALEMATE_TITLE = "相持，{place}照舊"
GUARD_NAME = "{squad}" + battle_instance.GUARD_SUFFIX  # 待 joy 潤：中立地的守將（那裡最強的一路隊伍）
LATE_MUSTER_SECONDS = 600  # 【開發】開集結晚了（伺服器停過）：集結至少留這麼久，免得一開就截止、攻方來不及加入就作罷
SCENE_LINE = "{attackers}攻{place}；守方：{defender}。"  # 待 joy 潤：攻城戰的場景第二行


def title(content: Content, info: SiegeInfo) -> str:
    """這一場的名字（「攻城・淯水河畔」）。"""
    loc = content.locations.get(info.loc)
    return TITLE.format(place=loc.name if loc is not None else info.loc)


def template(content: Content, loc_id: str) -> BattleDef | None:
    """這一塊所在的大區的攻城範本（siege_<大區>）；沒有是 None（content.check_conquest_blocks 擋了搶得下來的每一塊都要有）。"""
    region = atlas.region_of(content, loc_id) if loc_id in content.locations else None
    definition = content.battles.get(f"siege_{region.id}") if region is not None else None
    return definition if definition is not None and definition.siege else None


def _other(side: str) -> str:
    return next(s for s in conquest.SIDES if s != side)


def _squads(world: WorldState, content: Content, loc_id: str) -> list[str]:
    return [sid for sid in territory.squads_at(world, content, loc_id) if sid in content.squads]


def info(slot: SiegeSlot, world: WorldState, content: Content) -> SiegeInfo:
    """開集結那一刻的這一場：此刻誰佔著（holder）、攻方（已經是主人的那一方不算攻方）、守將站哪一格。
    兩軍同時攻同一塊中立地、那裡有隊伍當守將：三方混戰，守將站 GUARD（裁決 22）；那裡沒有隊伍（開季中立的每一塊都有）退回兩軍正面打。"""
    holder = conquest.holder(world, content, slot.loc)
    attackers = [a for a in slot.attackers if a != holder]
    if holder is None and len(attackers) == 1:
        guard = _other(attackers[0])
    elif holder is None and len(attackers) == 2 and _squads(world, content, slot.loc):
        guard = GUARD
    else:
        guard = None
    return SiegeInfo(slot_id=slot.id, loc=slot.loc, attackers=attackers, holder=holder, guard_side=guard)


def defender(info: SiegeInfo) -> str | None:
    """守的那一格：陣營佔著的是那一方，中立地是守將那一格（三方混戰是 GUARD）；兩軍同時搶沒有守將的中立地沒有。"""
    return info.holder if info.holder in conquest.SIDES else info.guard_side


def start_trend(world: WorldState, content: Content, info: SiegeInfo) -> int:
    """起點（設計 4.4）：50 − 進度往黃巾偏的點數（戰局以官軍為正向）；只有一個攻方時照他那一條進度偏（翻地與爭搶：戰書要到 60 才下得了）。"""
    return battle_instance.CENTER - conquest.progress_shift(world, content, info.loc, info.attackers)


def _guard_pool(content: Content) -> float:
    """單方攻中立地時守將的池子：同龍頭上陣的主將（Config.battle.generals.pool 第一個）。"""
    pool = content.config.battle.generals.pool
    return pool[0] if pool else 1000.0


def guard_squad(world: WorldState, content: Content, loc_id: str, side_slot: str) -> Commander | None:
    """那裡最強的一路隊伍當守將（站 side_slot 那一格；fid 是「squad:隊伍 id」，收場時 generals.after_battle 自然略過）：
    份量＝strength(難度) × 龍頭上陣主將的倍數，池子照主將（三方混戰站 GUARD 時先照 MELEE_MIN_HEADS 個人算，集結結束再照到場的人數定，
    size_melee_guard）。那裡沒有隊伍是 None。"""
    squads = _squads(world, content, loc_id)
    if not squads:
        return None
    best = max(squads, key=lambda sid: (content.squads[sid].difficulty, sid))
    gen = content.config.battle.generals
    rank, pool = (gen.ranks[0] if gen.ranks else 1.0), _guard_pool(content)
    if side_slot == GUARD:
        pool = content.config.conquest.melee_pool_per_head * MELEE_MIN_HEADS
    score = round(battle_instance.strength(content.config.battle, content.squads[best].difficulty) * rank, 1)
    return Commander(fid=f"squad:{best}", name=GUARD_NAME.format(squad=content.squads[best].name), faction=side_slot,
                     rank=0, score=score, neili=pool, neili_cap=pool)


def commanders(state: GameState, content: Content, info: SiegeInfo, definition: BattleDef) -> list[Commander]:
    """這一場的留守（不是參戰者：不佔人數、不等他、不拿軍餉）：守方是陣營時照龍頭上陣的挑法取那一區守方的大勢人物（開關開著時）；
    沒有人物、或中立地時是那裡最強的一路隊伍當守將（三方混戰站 GUARD，裁決 22）。兩軍同時搶沒有隊伍的中立地沒有守將。"""
    side = defender(info)
    if side is None:
        return []
    if info.holder in conquest.SIDES and generals.on(content):
        rows = [c for c in generals.pick(state, content, definition) if c.faction == side]
        if rows:
            return rows
    guard = guard_squad(state.world, content, info.loc, side)
    return [guard] if guard is not None else []


def lone_army(content: Content, battle: battle_instance.BattleInstance, definition: BattleDef) -> bool:
    """三方混戰集結結束、開打的那一下（Game._advance_battle_round 在 close_muster、void_absent 之後、size_melee_guard 之前叫，在 mutate 裡）：
    兩軍裡只有一軍有人到場（另一軍一個人都沒來，算棄權；裁決 23，PM 2026-10-21），這一場轉回單方攻中立地——到場的那一軍是攻方，守將改站
    棄權那一軍那一格（SiegeInfo.guard_side，跟單方攻中立地一樣：另一軍站不進去、散人可以助守），池子改回單方的（_guard_pool），助守的人
    （GUARD）跟著守將站過去，將令重喊一次；之後一切照單方攻中立地（守將照舊、戰線過了門檻就拿下，不用把守將打倒）。
    SiegeInfo.absent 記沒到場的那一軍（場景多一句）。回轉了沒；兩軍都有人到（照三方混戰）、兩軍都沒人（void_absent 已經作罷）不動。
    到場＝有參戰者站那一軍那一格（臨時投效的散人也算）。"""
    if not battle_instance.melee(battle) or battle.phase != "active":
        return False
    present = [a for a in battle.siege.attackers if any(p.faction == a for p in battle.participants.values())]
    if len(present) != 1:
        return False
    keep = present[0]
    absent = _other(keep)
    battle.siege.attackers, battle.siege.guard_side, battle.siege.absent = [keep], absent, absent
    pool = _guard_pool(content)
    for c in battle.commanders:
        if c.faction == GUARD:
            c.faction, c.neili, c.neili_cap = absent, pool, pool
    for p in battle.participants.values():
        if p.faction == GUARD:
            p.faction = absent
    battle_instance.call_orders(battle, definition, content.config.battle)
    return True


def size_melee_guard(content: Content, battle: battle_instance.BattleInstance) -> None:
    """三方混戰集結結束、開打的那一下（Game._advance_battle_round 在 close_muster 之後叫，在 mutate 裡）：守將的池子照兩軍到場的人數定
    （Config.conquest.melee_pool_per_head × max(MELEE_MIN_HEADS, 人數)，裁決 22【預設】）。不是三方混戰、還沒開打不動。"""
    if not battle_instance.melee(battle) or battle.phase != "active":
        return
    heads = sum(1 for p in battle.participants.values() if p.faction in battle.siege.attackers)
    pool = float(content.config.conquest.melee_pool_per_head * max(MELEE_MIN_HEADS, heads))
    for c in battle.commanders:
        if c.faction == GUARD and c.fallen_round is None:
            c.neili = c.neili_cap = pool


# 單方攻中立地時，散人、豪強站守將那一格（裁決 8）：那一格規則上是另一軍的 id，寫給人看的是中立的守軍、說「助守」，
# 不寫「臨時投效【另一軍】」（FB-540；那一格的名字是 battle_instance.GUARD_SIDE）。待 joy 潤
HELP_GUARD = "助守【{side}】（只算這一場）"
HELPED_GUARD = "已助守【{side}】"
HELP_GUARD_LINE = "你助守{place}，只算這一場：打完你照樣是{own}。"
HELP_GUARD_LATE = "你助守{place}，趕到了戰場，這一回合就能出手；打完你照樣是{own}。"
HELP_GUARD_TITLE = "助守"  # 江湖紀錄的標題「攻城・荒丘・助守」
HELP_GUARD_SWITCH = "改為助守"
FREE_AGENT_GUARD = "可以臨時投效{who}、或助守{place}，只算這一場"  # 集結時散人、豪強看到的那一句（取代「可以臨時投效其中一方」）

JOIN_SIDE = "（這一仗是{who}攻{place}，你這一邊插不上手。）"  # 待 joy 潤
JOIN_OWN = "（你只能站在自己陣營這一邊。）"
WATCH_LINE = "這一仗是{who}攻{place}，你這一邊插不上手，照常行動就好。"  # 待 joy 潤：另一軍站在攻中立地的那一區時，場景上那一句


def watch_line(content: Content, info: SiegeInfo) -> str:
    """另一軍的人站在這一區、這一仗沒有他站得進去的格時，場景上那一句（取代「人要到了那裡才能加入」）。"""
    who = "、".join(content.scenario.faction_name(a, a) for a in info.attackers)
    return WATCH_LINE.format(who=who, place=content.locations[info.loc].name)


def slots(info: SiegeInfo, side: str | None) -> list[str]:
    """side（照 allied.side_of：豪強依附的那一軍；散人與不是兩軍的人是 None）站得進去的格：攻方站自己那一格；打的是誰的區塊，
    那一方站守的那一格；散人與不是兩軍的人臨時投效攻方或守的那一格（助守中立地的守將，裁決 8）；另一軍站不進守將那一格。"""
    if side in conquest.SIDES:
        return [side] if side in info.attackers or side == info.holder else []
    return [*info.attackers, *([d] if (d := defender(info)) is not None and d not in info.attackers else [])]


def join_problem(content: Content, info: SiegeInfo, side: str | None, slot: str) -> str | None:
    """side 的人站 slot 那一格不成的那一句（成是 None）。"""
    if slot in slots(info, side):
        return None
    if side in conquest.SIDES and slots(info, side):
        return JOIN_OWN
    who = "、".join(content.scenario.faction_name(a, a) for a in info.attackers)
    return JOIN_SIDE.format(who=who, place=content.locations[info.loc].name)


def verdict(info: SiegeInfo, battle: battle_instance.BattleInstance, definition: BattleDef) -> tuple[str | None, str, str]:
    """收場：（易手給誰〔None＝原主人留著〕, 戰場上贏的那一方, 大勝／險勝）。照 battle_instance.result_at 判（戰局剛好 50 算守方守住；
    兩軍同時搶沒有守將的中立地停在 50 是相持，誰都沒拿下）。三方混戰（裁決 22）照誰補上最後一刀（SiegeInfo.blow）：那一軍拿下，
    大勝看那一軍最後的戰線偏過中線 BIG_WIN_MARGIN；守將沒倒是守軍（GUARD）守住、險勝。"""
    if battle_instance.melee(battle):
        if info.blow:
            lean = battle.trend if info.blow == definition.factions[0].id else 100 - battle.trend
            return info.blow, info.blow, "大勝" if lean - battle_instance.CENTER >= battle_instance.BIG_WIN_MARGIN else "險勝"
        return None, GUARD, "險勝"
    side = defender(info)
    if side is None and battle.trend == battle_instance.CENTER:
        return None, "", ""
    winner, margin = battle_instance.result_at(battle.trend, definition, None, side or definition.factions[0].id)
    return (winner if winner in info.attackers else None), winner, margin


def outcome_title(content: Content, info: SiegeInfo, taken: str | None, winner: str, margin: str) -> str:
    place = content.locations[info.loc].name
    if info.holder is None and info.guard_side == GUARD:  # 三方混戰（裁決 22）
        if taken is not None:
            return MELEE_TAKEN_TITLE.format(side=content.scenario.faction_name(taken, taken), place=place)
        return HELD_TITLE.format(side=battle_instance.GUARD_SIDE, place=place)
    if taken is not None:
        return TAKEN_TITLE.format(side=content.scenario.faction_name(taken, taken), margin=margin, place=place)
    side = defender(info)
    if side is None or not winner:
        return STALEMATE_TITLE.format(place=place)
    holder = info.holder or side
    return HELD_TITLE.format(side=content.scenario.faction_name(holder, holder) if info.holder else "守將", place=place)


def scene_line(content: Content, info: SiegeInfo, battle: battle_instance.BattleInstance) -> str:
    """攻城戰的場景第二行：誰攻、守方是誰（陣營、守將、或兩軍相爭）；三方混戰另寫誰補上最後一刀誰拿下（裁決 22）。"""
    who = "、".join(content.scenario.faction_name(a, a) for a in info.attackers)
    if battle_instance.melee(battle):
        guard = next((c.name for c in battle.commanders if c.faction == GUARD), battle_instance.GUARD_SIDE)
        return MELEE_SCENE_LINE.format(attackers=who, place=content.locations[info.loc].name, defender=guard)
    if info.holder in conquest.SIDES:
        side = content.scenario.faction_name(info.holder, info.holder)
    else:
        guard = next((c.name for c in battle.commanders if c.fid.startswith("squad:")), "")
        side = guard or ("兩軍相爭" if defender(info) is None else "守將")
    line = SCENE_LINE.format(attackers=who, place=content.locations[info.loc].name, defender=side)
    if info.absent:  # 三方混戰只有一軍到場、轉回單方攻中立地（裁決 23）：多一句沒到場的是誰
        line += ABSENT_SCENE_LINE.format(absent=content.scenario.faction_name(info.absent, info.absent))
    return line


def scene_note(content: Content, info: SiegeInfo, battle: battle_instance.BattleInstance) -> str:
    """攻城戰場景第二行（Game._battle_scene_text）：誰攻、守方是誰已經寫在畫面最上面那一條（banner，第三批 A），PM 定不再寫一次
    （scene_line 的「某軍攻某地；守方：某某。」）；只留那一條沒說到的——三方混戰的規矩（MELEE_RULE）、轉回單方時沒到場的那一軍
    （ABSENT_SCENE_LINE）。其餘是空的。"""
    if battle_instance.melee(battle):
        return MELEE_RULE
    if info.absent:
        return ABSENT_SCENE_LINE.format(absent=content.scenario.faction_name(info.absent, info.absent))
    return ""


# 攻城戰畫面最上面那一條（領地爭奪第三批 A，企劃者挑甲：「攻城・地點｜守方：某某（或守將）」；Game.siege_banner → main.siege，
# 網頁 siegeStrip 把場景的名字那一行換成這一條）。三方混戰、轉回單方、兩軍相爭那三種怎麼寫是【開發定】；全部待 joy 潤
BANNER_DEFENDER = "守方：{who}"
BANNER_MELEE = "三方混戰"  # 【開發定】兩軍同時攻同一塊中立地（裁決 22）：寫在守方前面
BANNER_ABSENT = "{absent}未到"  # 【開發定】三方混戰只有一軍到場、轉回單方攻中立地（裁決 23）：接在守方後面
BANNER_OPEN = "兩軍相爭，沒有守方"  # 【開發定】兩軍同時搶沒有守將的中立地（退回正面打）


def banner(content: Content, battle: battle_instance.BattleInstance) -> dict:
    """攻城戰畫面最上面那一條：{"title": 「攻城・地點」, "parts": 接在後面的幾段, "kind": held／neutral／melee／lone／open}。
    陣營佔著的寫那一方；中立地寫守將的名字（「某某（守將）」，找不到寫守軍）；三方混戰前面多「三方混戰」；轉回單方的後面多「某軍未到」。"""
    info_ = battle.siege
    guard = next((c.name for c in battle.commanders if c.fid.startswith("squad:")), "") or battle_instance.GUARD_SIDE
    if battle_instance.melee(battle):
        kind, parts = "melee", [BANNER_MELEE, BANNER_DEFENDER.format(who=guard)]
    elif info_.holder in conquest.SIDES:
        kind, parts = "held", [BANNER_DEFENDER.format(who=content.scenario.faction_name(info_.holder, info_.holder))]
    elif info_.absent:
        kind = "lone"
        parts = [BANNER_DEFENDER.format(who=guard), BANNER_ABSENT.format(absent=content.scenario.faction_name(info_.absent, info_.absent))]
    elif defender(info_) is not None:
        kind, parts = "neutral", [BANNER_DEFENDER.format(who=guard)]
    else:
        kind, parts = "open", [BANNER_OPEN]
    return {"title": title(content, info_), "parts": parts, "kind": kind}


def _rumor(world: WorldState, text: str, loc: str | None = None) -> None:
    world.rumors.append(Rumor(time=world.time, text=text, location=loc, layer="world"))


def mark_due(world: WorldState, content: Content) -> None:
    """時間到了開集結的（muster_at ≤ 此刻）記成 waiting（world.advance_world_state 每一步叫；開集結要 store，由 start_pending_battle 開）。"""
    if world.conquest is None or not conquest.on(content, world):
        return
    for slot in world.conquest.schedule:
        if slot.status == "planned" and slot.muster_at <= world.time:
            slot.status = "waiting"


def open_waiting(world: WorldStateStore, content: Content, now: float) -> list[str]:
    """開時間到了的攻城（world.start_pending_battle 叫；呼叫端不在任何 mutate 裡）：每一場照此刻誰佔著重算（info），攻方已經是主人就作罷；
    其餘開一場集結（store.start_siege），起點照進度偏，集結截止＝開打的那一刻（開晚了至少留 LATE_MUSTER_SECONDS），派留守、一句天下大事。
    回寫進天下大事的那幾句。開關關著、季收了、沒有在等的什麼都不做。"""
    from .world import _season_vehicle  # noqa: PLC0415  world → siege：延後 import

    season = world.get_season()
    if season.ended or season.conquest is None or not conquest.on(content, season):
        return []
    waiting = [slot for slot in season.conquest.schedule if slot.status == "waiting"]
    if not waiting:
        return []
    msgs: list[str] = []
    opened: dict[str, int] = {}
    voided: dict[str, str] = {}
    scale = content.config.time_scale
    for slot in waiting:
        definition = template(content, slot.loc)
        here = info(slot, season, content)
        name = title(content, here)
        if definition is None or not here.attackers:
            who = "、".join(content.scenario.faction_name(a, a) for a in slot.attackers)
            voided[slot.id] = VOID_HELD.format(who=who, place=content.locations[slot.loc].name)
            continue
        battle = world.start_siege(definition, now, start_trend(season, content, here), here)
        floor = min(LATE_MUSTER_SECONDS, content.config.conquest.muster_minutes * 60)  # 開晚了（伺服器停過）至少留這麼久
        deadline = now + max((slot.at - season.time) / scale, floor)
        rows = commanders(_season_vehicle(content, season), content, here, definition.model_copy(update={"name": name}))

        def _snap(b: battle_instance.BattleInstance, deadline=deadline, rows=rows) -> None:
            b.muster_deadline_real = deadline
            b.commanders = [c.model_copy() for c in rows]

        world.mutate_siege(battle.record_id, _snap)
        opened[slot.id] = battle.record_id
        region = atlas.region_of(content, slot.loc)
        who = "、".join(content.scenario.faction_name(a, a) for a in here.attackers)
        msgs.append(MUSTER_LINE.format(title=name, who=who, region=region.name if region is not None else ""))

    def _apply(s: WorldState) -> None:
        for slot in s.conquest.schedule:
            if slot.id in opened:
                slot.status, slot.record_id = "open", opened[slot.id]
            elif slot.id in voided:
                conquest_day.void(s, content, slot, voided[slot.id])
        for line in msgs:
            _rumor(s, line)

    world.mutate_season(_apply)
    return [f"🛡️ 【全服戰報】{line}" for line in msgs] + list(voided.values())


def void_absent(content: Content, battle: battle_instance.BattleInstance) -> bool:
    """集結剛結束（_advance_battle_round 收集結那一下呼叫，在 mutate 裡）：攻方一個參戰者都沒有就作罷——標成收場、不算勝負
    （unfinished，參戰者照季終收兵補一則交代、不發軍餉），SiegeInfo.void 記原因。回作罷了沒。"""
    if battle.siege is None or battle.phase != "active":
        return False
    if any(p.faction in battle.siege.attackers for p in battle.participants.values()):
        return False
    battle.phase, battle.unfinished, battle.unfinished_text = "ended", True, VOID_ABSENT_NOTE
    battle.outcome_title = battle_instance.UNFINISHED_TITLE
    battle.siege.void = "absent"
    return True


def settle(world: WorldState, content: Content, battle: battle_instance.BattleInstance, definition: BattleDef) -> dict:
    """收場那一下改季（Game._settle_siege 在 mutate_season 裡叫）：易手（conquest.flip：分紅、冷卻、「落入／收復」）或守住各一句
    天下大事；沒打下來攻方的條各砍半（設計 4.4「打輸進度砍半」）；時程表那一場記 done（winner）或 void，那一塊就此解凍。
    作罷不發天下大事、進度照留，攻方沒人到的另記一筆 day_log（裁決 19）。回 {"taken", "winner", "margin", "title"} 給戰鬥那一列寫結果。"""
    info_ = battle.siege
    name = title(content, info_)
    place = content.locations[info_.loc].name
    slot = next((s for s in world.conquest.schedule if s.id == info_.slot_id), None) if world.conquest is not None else None
    if info_.void or battle.unfinished:
        # 作罷不發天下大事（攻方沒人到：人少的服每天空轉會洗版，PM 裁決 19）：時程表記 void，沒人到的另記一筆 day_log
        if slot is not None:
            conquest_day.void(world, content, slot)
            if info_.void == "absent":
                conquest_day.note_void(world, slot, "absent")
        return {"taken": None, "winner": "", "margin": "", "title": battle.outcome_title or battle_instance.UNFINISHED_TITLE}
    taken, winner, margin = verdict(info_, battle, definition)
    if battle_instance.melee(battle):  # 三方混戰（裁決 22）：寫出誰補上最後一刀（具名），或守軍守住
        keeper = next((c for c in battle.commanders if c.faction == GUARD), None)
        if taken is not None:
            side = content.scenario.faction_name(taken, taken)
            line = BLOW_RUMOR if keeper is not None and keeper.felled_by else BLOW_RUMOR_NOBODY
            _rumor(world, line.format(title=name, who=keeper.felled_by if keeper is not None else "", side=side,
                                      guard=keeper.name if keeper is not None else battle_instance.GUARD_SIDE, place=place), info_.loc)
            conquest.flip(world, content, info_.loc, taken, note=False)  # 這一場的結果由 _note_result 記（〈天下形勢〉不寫兩條）
        else:
            _rumor(world, MELEE_HELD_LINE.format(title=name, place=place), info_.loc)
    elif taken is not None:
        conquest.flip(world, content, info_.loc, taken, note=False)
    elif winner and defender(info_) is not None:
        holder = info_.holder
        side = content.scenario.faction_name(holder, holder) if holder else "守將"
        _rumor(world, HELD_LINE.format(title=name, side=side, place=place), info_.loc)
    else:
        _rumor(world, STALEMATE_LINE.format(title=name, place=place), info_.loc)
    if taken is None:
        conquest.halve(world, content, info_.loc, info_.attackers)  # 打輸（守住、相持、三方混戰守將沒倒）：攻方的條各砍半（設計 4.4）
    if slot is not None:
        slot.status, slot.winner = "done", taken
        _note_result(world, slot, info_, battle, taken, winner, margin)
    return {"taken": taken, "winner": winner, "margin": margin, "title": outcome_title(content, info_, taken, winner, margin)}


def _note_result(world: WorldState, slot: SiegeSlot, info_: SiegeInfo, battle: battle_instance.BattleInstance,
                 taken: str | None, winner: str, margin: str) -> None:
    """收場那一下在當天的 day_log 記一筆結果（領地爭奪第三批 A：〈天下形勢〉只讀 day_log，計畫 6.3 第 1 條）：拿下（taken）、
    守住（held，戰場上贏的是守方）、相持（stalemate，兩軍同時搶沒有守將的中立地停在中線）。keeper 是開集結那一刻的守方
    （陣營 id；中立地的守將寫 guard）；三方混戰補上最後一刀的人照抄（天下大事本來就具名）。作罷的另由 conquest_day.note_void 記。"""
    if world.conquest is None:
        return
    result = "taken" if taken is not None else "held" if winner else "stalemate"
    side = defender(info_)
    keeper = side if side in conquest.SIDES and info_.holder in conquest.SIDES else "guard" if side is not None else ""
    guard = next((c for c in battle.commanders if c.faction == GUARD), None) if battle_instance.melee(battle) else None
    first = taken or (info_.attackers[0] if info_.attackers else slot.attackers[0] if slot.attackers else "")
    world.conquest.day_log.append(DayNote(
        key=slot.key, side=first, loc=slot.loc, minute=slot.minute, by=slot.by.get(first, ""), result=result,
        taken=taken or "", margin=margin, keeper=keeper, attackers=list(info_.attackers),
        blow=guard.felled_by if guard is not None and taken is not None else "",
    ))
