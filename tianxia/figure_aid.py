"""同陣營的人護著大勢人物（Joy 2026-10-17 清單第 6 條；數字在 Config.figure_aid）：護衛、犒軍、探望。

- 護衛：替這裡的同陣營人物站一班崗（GuardPost，存在這一季的 WorldState.figure_guards），身手抄成分身；敵方挑戰他時先跟班上最強的
  分身過一招（contest），挑戰的人輸了這一次挑戰不成。人物離開那個地點、時刻到了、擋滿 guard_blocks 次，那一班就散。
- 犒軍：補人物的聲威（restore，跟每天的自然回復共用 daily_restore_cap）。
- 探望：人物被挑戰打到退場、還在等回來（FigureState.back_at）時，在自己陣營的大本營讓他早一點回來。
這裡只改 GameState（季在 state.world 上），扣體力、銀兩、記貢獻、寫紀錄是 engine 的事。只 import models、state、figures、calendar、encounter。
"""
from __future__ import annotations

import random

from . import calendar, encounter, figures
from .models import Content
from .state import GameState, GuardPost

DAY = 86400

GUARD_LABEL = "護衛{name}"  # 待 joy 潤
GUARD_ON_LABEL = "護衛{name}（站崗到{until}）"
RALLY_LABEL = "犒軍・{name}（聲威 {now}/{cap}・{silver} 兩）"
VISIT_LABEL = "探望{name}（還要{left}才回來）"
GUARD_DONE = "你在{name}身邊站崗，守到{until}；有人來挑戰，得先過你這一關。"
RALLY_DONE = "你拿出{silver}兩犒賞{name}的部眾，{name}聲威 +{n}（{now}/{cap}）。"
VISIT_DONE = "你去探望養傷的{name}，他精神好了些，會早{hours}回來。"  # 待 joy 潤
GUARDED_NOTE = "身邊有 {n} 人護衛"  # 挑戰鈕上
BLOCKED_LINE = "{guard}擋在{name}身前，你跟{guard}過了幾招沒能突破，只得退下。"  # 待 joy 潤：挑戰的人輸給護衛
BROKE_LINE = "你擊退了擋在{name}身前的護衛{guard}。"
CREDIT_LINE = "你替{name}擋下了{who}的挑戰。"
CREDIT_TITLE = "護衛"
GUARD_TITLE = "護衛"
RALLY_TITLE = "犒軍"
VISIT_TITLE = "探望"
FULL_NOTE = "今天已經犒過了"
CAP_NOTE = "他今天已經補得夠多了"
TOP_NOTE = "聲威已滿"
SLOTS_NOTE = "護衛已滿"


def on(content: Content) -> bool:
    return content.config.figure_aid.enabled and bool(content.figures)


def _day(state: GameState) -> int:
    return int(state.world.time // DAY)


def prune(state: GameState, content: Content) -> None:
    """拿掉散了的崗：時刻到了、擋滿了、人物已經不在那個地點（移動、退場）。"""
    cfg = content.config.figure_aid
    w = state.world
    keep = []
    for post in w.figure_guards:
        now = figures.state_of(state, content, post.fid) if post.fid in content.figures else None
        if (now is None or now.status != "active" or now.location != post.location or w.time >= post.until
                or post.blocks >= cfg.guard_blocks):
            continue
        keep.append(post)
    w.figure_guards = keep


def posts(state: GameState, content: Content, fid: str) -> list[GuardPost]:
    """這位人物此刻站著的崗（身手強的在前）。"""
    prune(state, content)
    return sorted((p for p in state.world.figure_guards if p.fid == fid), key=lambda p: (-p.power, p.name))


def guarding(state: GameState, content: Content, name: str, fid: str) -> GuardPost | None:
    return next((p for p in posts(state, content, fid) if p.name == name), None)


def guard_problem(state: GameState, content: Content, fid: str) -> str | None:
    """站不了崗的原因；站得了是 None（體力另外看）。"""
    p = state.player
    if guarding(state, content, p.name, fid) is not None:
        return "已經在站崗"
    if any(q.name == p.name for q in state.world.figure_guards):
        return "你在護衛別人"
    if len(posts(state, content, fid)) >= content.config.figure_aid.guard_slots:
        return SLOTS_NOTE
    return None


def guard(state: GameState, content: Content, fid: str, power: float) -> GuardPost:
    """站一班崗（呼叫端先驗過 guard_problem、扣過體力）。"""
    cfg = content.config.figure_aid
    w = state.world
    post = GuardPost(
        fid=fid, name=state.player.name, location=figures.state_of(state, content, fid).location or state.player.location,
        until=w.time + cfg.guard_hours * 3600, power=round(power, 1),
    )
    w.figure_guards.append(post)
    return post


def contest(state: GameState, content: Content, fid: str, challenger: str, power: float) -> tuple[GuardPost | None, bool]:
    """挑戰這位人物之前先過護衛那一關：班上最強的那一位的分身，本人對本人單次判定（同截殺）。沒有人站崗是（None, True）。
    回傳（那一班, 挑戰的人有沒有突破）。突破了那一班散；擋下了記一次、等著補給護衛（guard_credits）。亂數自己一份，不碰 Game.rng。"""
    rows = posts(state, content, fid)
    if not rows:
        return None, True
    post = rows[0]
    rng = random.Random(f"護衛|{post.fid}|{post.name}|{challenger}|{state.world.time}")
    result = encounter.resolve_encounter(power, max(1.0, post.power), rng)
    broke = result.tier in ("大勝", "險勝")
    if broke:
        state.world.figure_guards = [p for p in state.world.figure_guards if p is not post]
    else:
        post.blocks += 1
        state.world.guard_credits.setdefault(post.name, []).append(
            CREDIT_LINE.format(name=content.figures[fid].name, who=challenger),
        )
    return post, broke


def restored_today(state: GameState, fid: str) -> float:
    return state.world.aid_tally.get(f"restored:{fid}:{_day(state)}", 0.0)


def restore(state: GameState, content: Content, fid: str, amount: float) -> int:
    """替人物補聲威 amount（自然回復、犒軍、人物自己募兵共用）：補到開季值、一天最多 daily_restore_cap（開關關著不設上限）。
    回傳真的補了幾點。"""
    fig = content.figures.get(fid)
    now = state.world.figures.get(fid)
    if fig is None or now is None or amount <= 0:
        return 0
    room = fig.start_prestige - now.prestige
    if on(content):
        room = min(room, int(content.config.figure_aid.daily_restore_cap - restored_today(state, fid)))
    gained = max(0, min(int(amount), room))
    if gained:
        now.prestige += gained
        key = f"restored:{fid}:{_day(state)}"
        state.world.aid_tally[key] = state.world.aid_tally.get(key, 0.0) + gained
        _prune_tally(state)
    return gained


def _prune_tally(state: GameState) -> None:
    today = _day(state)
    for k in [k for k in state.world.aid_tally if k.rsplit(":", 1)[-1].isdigit() and int(k.rsplit(":", 1)[-1]) < today - 1]:
        del state.world.aid_tally[k]


def rally_problem(state: GameState, content: Content, fid: str) -> str | None:
    cfg = content.config.figure_aid
    fig, now = content.figures[fid], figures.state_of(state, content, fid)
    if now.prestige >= fig.start_prestige:
        return TOP_NOTE
    if state.world.aid_tally.get(f"rally:{fid}:{state.player.name}:{_day(state)}", 0) >= cfg.rally_per_day:
        return FULL_NOTE
    if restored_today(state, fid) >= cfg.daily_restore_cap:
        return CAP_NOTE
    if state.player.stats.get("silver", 0) < cfg.rally_silver:
        return f"銀兩不夠（要 {cfg.rally_silver} 兩）"
    return None


def rally(state: GameState, content: Content, fid: str) -> int:
    """犒軍（呼叫端先驗過 rally_problem、扣過體力與銀兩）：聲威 +rally_points，記這個人今天犒了幾次。回傳補了幾點。"""
    figures._ensure(state, content, fid)  # noqa: SLF001  沒被打過的人物也要有一筆才補得上（照開季值種）
    key = f"rally:{fid}:{state.player.name}:{_day(state)}"
    state.world.aid_tally[key] = state.world.aid_tally.get(key, 0) + 1
    return restore(state, content, fid, content.config.figure_aid.rally_points)


def visiting(state: GameState, content: Content) -> list[str]:
    """此地是自己陣營的大本營時，同陣營、被挑戰打退、還在等回來的人物（人物表的順序）。"""
    p = state.player
    faction = content.scenario.find_faction(p.faction) if p.faction else None
    if faction is None or p.location not in faction.join_at:
        return []
    return [
        fid for fid, fig in content.figures.items()
        if fig.faction == p.faction and (now := state.world.figures.get(fid)) is not None and now.back_at is not None
        and now.status in figures.OUT and now.back_at > state.world.time
    ]


def visit_problem(state: GameState, content: Content, fid: str) -> str | None:
    cfg = content.config.figure_aid
    if state.world.aid_tally.get(f"visit:{state.player.name}:{_day(state)}", 0) >= 1:
        return "今天已經探望過了"
    full = content.config.figure_return_days * 24 * calendar.cal_hour_seconds(content, state.world)
    if state.world.aid_tally.get(f"visitcut:{fid}", 0.0) >= full * cfg.visit_max_share - 1e-6:
        return "再探望也快不了了"
    return None


def visit(state: GameState, content: Content, fid: str) -> float:
    """探望（呼叫端先驗過 visit_problem、扣過體力）：回來的時刻提前 visit_hours 個季曆小時，一位人物這一次倒下最多提前
    visit_max_share（記在 aid_tally["visitcut:<id>"]，他回來時清掉）。回傳提前了幾個季曆小時。"""
    cfg = content.config.figure_aid
    w = state.world
    hour = calendar.cal_hour_seconds(content, w)
    full = content.config.figure_return_days * 24 * hour
    done = w.aid_tally.get(f"visitcut:{fid}", 0.0)
    cut = max(0.0, min(cfg.visit_hours * hour, full * cfg.visit_max_share - done))
    now = w.figures[fid]
    now.back_at = max(w.time, (now.back_at or w.time) - cut)
    w.aid_tally[f"visitcut:{fid}"] = done + cut
    key = f"visit:{state.player.name}:{_day(state)}"
    w.aid_tally[key] = w.aid_tally.get(key, 0) + 1
    return cut / hour if hour else 0.0


def left_text(state: GameState, content: Content, fid: str) -> str:
    """探望鈕上：還要多久回來（季曆小時，最少寫 1）。"""
    now = state.world.figures[fid]
    hour = calendar.cal_hour_seconds(content, state.world)
    hours = max(1, round(((now.back_at or 0) - state.world.time) / hour)) if hour else 1
    return f" {hours} 小時" if hours < 24 else f" {hours // 24} 天"


def hours_text(hours: float) -> str:
    """探望提前了多久（季曆小時）：「兩小時」這類說法不寫，照 left_text 的寫法。"""
    h = max(1, round(hours))
    return f" {h} 小時" if h < 24 else f" {h // 24} 天"
