"""閉關的動作（功能包 tianxia/features/seclusion/；原本是 Game 上的 seclusion_refusal、seclude、_finish_seclusion，開發規範手冊 3.2）。
ctx 是 Game（第一階）；只叫 tianxia/core/services.py 那張清單上的方法。Game 上留一行委派（server 的修練頁、_advance_player_local 與測試叫的）；
act:break（提早出關）由 SeclusionFeature.verbs() 的 Verb("break") 直接叫 finish。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import journal, prologue, treasures
from tianxia.state import JournalEntry

if TYPE_CHECKING:
    from tianxia.engine import Game

HOUR = 3600


def refusal(ctx: Game) -> str | None:
    """閉關現在做不做得了（序章裡不閉關，prologue.seclude_problem）：修練頁的閉關鈕灰掉、寫它，跟 seclude 的拒絕同一個判斷。"""
    return prologue.seclude_problem(ctx.state, ctx.content)


def seclude(ctx: Game, hours: int) -> list[str]:
    p = ctx.state.player
    problem = refusal(ctx)
    if problem is not None:
        return ctx._log([problem])  # 跟練成、熔煉的序章拒絕一樣：只回一句話，不寫紀錄
    if not ctx._idle():
        msgs = ["你現在無法閉關。"]
        ctx._write("閉關", msgs)
        return ctx._log(msgs)
    hours = max(1, min(12, int(hours)))
    ctx.state.battle_card = None
    p.busy_until = ctx.state.world.time + hours * HOUR
    p.seclusion_start = ctx.state.world.time
    real_hours = hours / ctx.content.config.time_scale  # 閉關的小時是世界時鐘的小時；寫給玩家看的是現實小時（FB-062）
    msgs = [f"你閉關靜修，預計現實 {real_hours:g} 小時後出關；閉關期間氣血回復加倍。"]
    ctx._write("閉關", msgs, tag=f"{hours} 小時")
    return ctx._log(msgs)


def finish(ctx: Game, end_time: float) -> list[str]:
    p, cfg = ctx.state.player, ctx.content.config
    hours = (end_time - p.seclusion_start) / HOUR
    # 寶物「閉關心得」（裝備四欄 6.2）：照出關那一刻身上那件算——寶物隨時能換（2.3【定】，企劃者 2026-10-11），閉關到一半換上也算
    bonus = 1 + treasures.amount(ctx.state, ctx.content, "seclusion")
    amount = round(hours * cfg.seclusion_xinde_per_hour * (1 + p.stats["wis"] / 20) * bonus)
    p.busy_until = None
    p.seclusion_done = end_time  # 天時地利的「心靜」：出關之後一陣子開爐（fusion.setting_points）
    p.stats["xinde"] = p.stats.get("xinde", 0) + amount
    msg = f"你結束閉關（{hours:.1f} 小時），心得 +{amount}。"
    tag, change = f"{hours:.1f} 小時", f"心得 +{amount}"
    if ctx._draft is not None:
        ctx._draft.outcome(tag, msg)
        ctx._draft.changes.append(change)
    else:
        journal.add_entry(ctx.state, JournalEntry(time=end_time, title="出關", tag=tag, changes=[change]))
    return [msg]
