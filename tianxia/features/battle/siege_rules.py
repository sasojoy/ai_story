"""攻城戰決戰那一半（第二輪第 97 批從共用規則層 tianxia/siege.py 切過來；開集結、留守、這一場的名字、誰佔著、內容驗證留在那裡）：
只有決戰包讀的——誰站哪一格、開打那一下（作罷、只到一軍、守將的池子）、收場改季、場景與畫面最上面那一條的字。

- 誰能站哪一格（join_problem）：攻方站自己那一格；打的是誰的區塊，那一方站守的那一格；單方攻中立地時另一格是守將（guard_side），
  另一軍站不進去、散人可以投效助守（裁決 8）。
- 兩軍同時攻同一塊中立地＝三方混戰（裁決 22，企劃者 2026-10-21）：守將留著、站第三格 battle_instance.GUARD，兩軍都打他、兩軍之間也互打，
  誰補上守將最後一刀誰拿下；回合打完守將沒倒，守住、照舊中立。散人可以投效兩軍之一或助守。守將的池子在集結結束那一刻照兩軍到場的人數定
  （size_melee_guard）。回合裡的規則在 battle_instance（resolve_round、_strike_guard）。
- 集結結束只有一軍到場（裁決 23，PM 2026-10-21）：另一軍一個人都沒來算棄權，這一場轉回單方攻中立地（lone_army）——攻方只剩到場的那一軍，
  守將站棄權那一軍那一格、池子照單方（Config.battle.generals.pool 第一個），之後守將照舊、戰線過了照原本的門檻就拿下，不用把守將打倒。
  兩軍都沒人到照舊作罷（void_absent，裁決 19）；兩軍都有人到照三方混戰。
- 收場（verdict）：攻方贏（大勝或險勝）就易手（conquest.flip：照推滿那樣分紅、冷卻）；否則原主人留著（中立還是中立）、攻方的條砍半。
  三方混戰照誰補上最後一刀。攻方一個人都沒到（集結結束時）作罷、進度照留。
只 import conquest（易手、作罷、砍半照叫共用規則層那一份）、核心的 battle_base（照切開之前，不換成這一包的 instance）、models、state，
與留在 tianxia/siege.py 的 defender、title、MELEE_MIN_HEADS、_guard_pool、_other、_rumor（兩半原本在同一個檔）。

test_for 照包挑，這兩個檔挑不到，改了另外跑（-n 4）：tests/acts/test_conquest_siege.py、tianxia/features/territory_acts/tests/test_conquest_web.py。"""
from __future__ import annotations

from tianxia import conquest  # 共用規則層（地盤）
from tianxia.core import battle_base as battle_instance  # 核心本體（決戰的資料型別與別人讀的判定）
from tianxia.core.battle_base import GUARD, SiegeInfo
from tianxia.models import BattleDef, Content
from tianxia.siege import MELEE_MIN_HEADS, defender, title  # 共用規則層（siege 留下的那一半）
from tianxia.siege import _guard_pool, _other, _rumor  # noqa: SLF001  同上（兩半原本在同一個檔）
from tianxia.state import DayNote, SiegeSlot, WorldState

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
ABSENT_SCENE_LINE = "{absent}沒有人趕到，這一場只剩對面一軍來攻。"  # 待 joy 潤：三方混戰集結結束只有一軍到場（裁決 23），場景第二行多的一句
TAKEN_TITLE = "{side}{margin}，拿下{place}"  # 待 joy 潤：戰報與紀錄的結果
HELD_TITLE = "{side}守住{place}"
STALEMATE_TITLE = "相持，{place}照舊"
SCENE_LINE = "{attackers}攻{place}；守方：{defender}。"  # 待 joy 潤：攻城戰的場景第二行


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
            conquest.void(world, content, slot)
            if info_.void == "absent":
                conquest.note_void(world, slot, "absent")
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
