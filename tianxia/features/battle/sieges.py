"""全服決戰「打」那一半之一：攻城（全部拆包第 6 批；計畫 docs/superpowers/plans/2026-11-01-決戰包-第2批.md）。原本 Game 上的 7 個方法，
本體照抄、self 換成 ctx（第一階 ctx 就是 Game，開發規範手冊 3.3）。攻城的規則本身在 tianxia/siege.py（共用規則層，總表附錄甲：不搬）；
這裡是 Game 那一側——好幾場並存時的那一串、推一場、收兵、取消、收場。Game 留 6 個一行委派（核心原位在叫：_battle_status 每一場推一次、
收季與開下一季收兵、取消一場攻城、收場分進攻城那一支、選單與「我在哪一場」問定義），siege_guards 只有這裡叫。第 8 批推進與結算搬進
progress.py、收季的收兵換成接縫掛鉤之後，_shelve_siege、_settle_siege 沒人叫了、拿掉，Game 上剩 4 個（_sieges、_definition_of、_tick_siege、
_cancel_siege）。

- sieges：還沒收場的攻城戰（這一季沒開領地爭奪是空的、不讀資料庫）
- definition_of：這一場的定義（決戰照內容；攻城戰是那個大區的範本，名字換成「攻城・地點」）——view.py 與這裡都經 ctx 叫（測試直接叫）
- tick_siege：推一場（集結截止、回合逾時、補位、結算），剛收場就套結果（ctx._apply_battle_outcome：測試換掉它）
- shelve_siege、cancel_siege：季終或管理者取消時收起來（不算勝負、不發軍餉、不易手），參戰者補一則交代
- settle_siege、siege_guards：剛收場（只做一次）——龍頭敗走、最有戲與首功兩則天下大事、守城軍令（FB-605）、易手或守住（siege.settle）、
  戰鬥那一列寫上結果、補送給自己

包裡叫 definition_of 經 ctx（測試直接叫 Game._definition_of）、補送經 ctx._deliver_battle_results（test_renown_cross 換掉它）；「打」那一半
被測試換掉的 _apply_battle_outcome（tests/server/test_server.py）與讀別人的存檔（_load_kin）也經 ctx；sieges、shelve_siege、siege_guards 與
第 8 批搬進 progress.py 的 advance_battle_round、highlight_line、merit_line（第 6 批時還在 Game、經 ctx 叫）、搬進這一包的 generals 直接叫。
"""
from __future__ import annotations

from tianxia import allied, battle_instance, conquest, orders, siege  # 過渡：待搬（豪強依附、戰鬥規則核心、地盤、軍令；siege 是共用規則層 registry.SHARED）
from tianxia.characters import name_key
from tianxia.models import BattleDef
from tianxia.state import Rumor, WorldState
from tianxia.world import _season_vehicle  # 過渡：待搬（季的事用的空殼玩家）

from . import generals, progress  # 龍頭上陣、推進與結算（第 8 批搬進這一包；progress 也 import 這一檔，都在函式裡用）


def sieges(ctx) -> list[battle_instance.BattleInstance]:
    """還沒收場的攻城戰（照開集結的先後）；這一季沒開領地爭奪是空的、不讀資料庫。"""
    if not conquest.on(ctx.content, ctx.state.world):
        return []
    return [b for b in ctx.world.get_sieges() if b.phase != "ended"]


def definition_of(ctx, battle: battle_instance.BattleInstance) -> BattleDef | None:
    """這一場的定義：決戰照內容；攻城戰是那個大區的範本，名字換成「攻城・地點」（siege.title）。"""
    definition = ctx.content.battles.get(battle.battle_id)
    if definition is None or battle.siege is None:
        return definition
    return definition.model_copy(update={"name": siege.title(ctx.content, battle.siege)})


def tick_siege(ctx, battle: battle_instance.BattleInstance) -> None:
    """推一場攻城（同決戰的 _run_battle_tick：集結截止、回合逾時、補位、結算），剛收場就套結果（_apply_battle_outcome）。"""
    definition = ctx._definition_of(battle)
    if definition is None:
        return
    after = ctx.world.mutate_siege(battle.record_id, lambda b: progress.advance_battle_round(ctx, b, definition))
    if after is not None and after.phase == "ended":
        ctx._apply_battle_outcome(after)


def shelve_siege(ctx, battle: battle_instance.BattleInstance, text: str = "") -> None:
    """季終（或管理者取消）時還沒打完的攻城收起來：同 _shelve_unfinished_battle（不算勝負、不發軍餉、不易手），參戰者補一則交代。"""
    end_time = ctx.state.world.time

    def _mark(b: battle_instance.BattleInstance) -> None:
        b.phase, b.unfinished, b.unfinished_text = "ended", True, text
        b.outcome_title, b.end_time = battle_instance.UNFINISHED_TITLE, end_time
        if b.siege is not None:
            b.siege.settled = True

    ctx.world.mutate_siege(battle.record_id, _mark)
    ctx.world.drop_siege(battle.record_id)
    ctx._deliver_battle_results()


def cancel_siege(ctx, record_id: int, text: str) -> None:
    """管理者取消一場已經開了集結的攻城（admin_conquest_cancel）：照季終收兵收起來，參戰者那一則寫 text。"""
    battle = next((b for b in sieges(ctx) if b.record_id == record_id), None)
    if battle is not None:
        shelve_siege(ctx, battle, text)
        ctx.state.world = ctx.world.get_season()


def settle_siege(ctx, battle: battle_instance.BattleInstance) -> None:
    """攻城戰剛收場（_apply_battle_outcome 分進來；只做一次，SiegeInfo.settled）：龍頭上陣的留守敗走扣聲威（守將是隊伍，不扣）；
    最有戲的一搏與兩軍首功照決戰上天下大事；易手（conquest.flip：分紅、冷卻、「落入／收復」）、守住各一句天下大事（作罷不發，攻方沒人到記
    day_log，裁決 19）、打輸攻方的條砍半、時程表記 done 或 void
    （siege.settle）；戰鬥那一列寫上結果（贏的一方、大勝或險勝、「某某大勝，拿下某地」）；參戰者照決戰補戰報與軍餉（軍餉、貢獻乘
    Config.conquest.pay_share，_showdown_pay）。隨行同伴不放回江湖（裁決 14）。收場的那一場留在共用狀態裡到每天結算才拿掉
    （最後一回合的放手一搏劇情收場之後才寫好）。"""
    if battle.siege is None or battle.siege.settled:
        return
    c = ctx.content
    definition = ctx._definition_of(battle)
    if definition is None:
        return
    if not battle.unfinished:
        if any(x.fallen_round is not None and not x.settled and x.fid in c.figures for x in battle.commanders):
            generals.after_battle(ctx.world, c, battle, where=definition.name,
                                  mutate=lambda fn: ctx.world.mutate_siege(battle.record_id, fn))
        for line in (progress.highlight_line(battle, definition), progress.merit_line(ctx, battle, definition)):
            if line:
                ctx.world.mutate_season(lambda season, line=line: season.rumors.append(Rumor(time=season.time, text=line, layer="world")))
    result: dict = {}
    guards = siege_guards(ctx, battle, definition)

    def _season(season: WorldState) -> None:
        if guards:  # FB-605：守方守住，替每一個守方的人記一次守城——那一塊還凍結著（siege.settle 之前），守城的清單照樣列它
            vehicle, line = _season_vehicle(c, season), conquest.line_of(season, c, battle.siege.loc)
            for name, side in guards:
                orders.credit(vehicle, c, side, name, kind=orders.SIEGE_GUARD, location=battle.siege.loc, front=line)
        result.update(siege.settle(season, c, battle, definition))

    ctx.world.mutate_season(_season)

    def _relabel(b: battle_instance.BattleInstance) -> None:
        b.siege.settled = True
        if not b.unfinished:
            b.outcome_title = result["title"]
            b.outcome_side, b.outcome_margin = result["winner"], result["margin"]
            b.outcome_text = b.outcome_text or ""

    after = ctx.world.mutate_siege(battle.record_id, _relabel)
    battle.siege.settled = True
    ctx.state.world = ctx.world.get_season()
    if after is not None:
        battle.outcome_title, battle.outcome_side, battle.outcome_margin = after.outcome_title, after.outcome_side, after.outcome_margin
    ctx._deliver_battle_results()


def siege_guards(ctx, battle: battle_instance.BattleInstance, definition: BattleDef) -> list[tuple[str, str]]:
    """攻城戰守方守住時，替守城軍令記一次的人（FB-605，PM 2026-10-21）：[(名號, 他自己那一邊)]。打的是陣營佔著的那一塊、照常打完
    （不是作罷、季終收兵）、沒被拿下；站守方那一格、而且自己那一邊（allied.side_of：豪強依附的那一軍）就是守方的人——臨時投效、助守的
    散人與別的陣營不算（只算這一場，不記貢獻）。讀別人的存檔只為了看他是哪一邊。"""
    info_ = battle.siege
    if info_ is None or battle.unfinished or info_.void or info_.holder not in conquest.SIDES:
        return []
    if siege.verdict(info_, battle, definition)[0] is not None:
        return []
    out: list[tuple[str, str]] = []
    for name, p in battle.participants.items():
        if p.faction != info_.holder:
            continue
        kin = ctx if name_key(name) == name_key(ctx.state.player.name) else ctx._load_kin(name)
        if kin is not None and allied.side_of(kin.state, ctx.content) == info_.holder:
            out.append((name, info_.holder))
    return out
