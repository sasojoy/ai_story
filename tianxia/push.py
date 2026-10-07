"""推力規則的算式（計畫 T3、第一季設計第七節）：陣營人數緩衝、每人每曆日上限、貢獻、不足一點的推力累積。
純函式，只看傳進來的數字與狀態，不碰引擎、不改任何東西；怎麼串起來見 engine.Game.push_trend。"""
from __future__ import annotations

import math

from .state import GameState, PlayerState

FRACTION_DIGITS = 9  # 浮點誤差：1.9999999999 要算成 2，不能少推一點


def buffered(delta: float, n: int) -> float:
    """陣營人數緩衝：每個人的效果是 1／√n（1 人 100%、4 人 50%、9 人 33%）。n 最少算 1，正負號照舊。"""
    return delta / math.sqrt(max(1, n))


def active_count(state: GameState, faction: str | None, now_time: float, window_seconds: float) -> int:
    """這個玩家所在陣營的活躍人數：過去 window_seconds（世界秒）內推過大勢的成員，含這一次的自己、
    真人與假人都算，最少 1。沒有陣營（散人）沒有名單可數，一律 1。"""
    if faction is None:
        return 1
    recent = {
        name for name, last in state.world.active_pushers.get(faction, {}).items() if now_time - last <= window_seconds
    }
    return max(1, len(recent | {state.player.name}))


def used_today(pushed: dict[str, float], cal_day: int, trend_id: str) -> float:
    """這個人今天（季曆第 cal_day 天）在這條線上已經推了多少（PlayerState.pushed 的帳，鍵是「曆日:大勢線 id」，緩衝後的量）。"""
    return pushed.get(f"{cal_day}:{trend_id}", 0.0)


def room_left(used: float, cap: float) -> float:
    """今天這條線已經推了 used、上限 cap：還推得動多少（不小於 0；浮點誤差留下的不到 10^-FRACTION_DIGITS 一絲當 0，
    不然選單會說還推得動、按下去卻什麼都沒推）。
    「這條線今天推滿了沒」只在這裡算：Game.push_trend（經 split_by_cap）與第 3、4 階行動的選單（經 room，企劃者裁決 E1）都走它。"""
    left = cap - used
    return left if left >= 10**-FRACTION_DIGITS else 0.0


def room(pushed: dict[str, float], cal_day: int, trend_id: str, cap: float) -> float:
    """這個人今天在這條線上還推得動多少（緩衝後的量）：0 是推滿了。"""
    return room_left(used_today(pushed, cal_day, trend_id), cap)


def split_by_cap(pushed: float, used: float, cap: float) -> tuple[float, float]:
    """緩衝後的推力 pushed 碰上今天這條線已經推了 used、上限 cap：回傳（還推得動的, 超過的）兩份，加起來是 pushed。"""
    moved = min(pushed, room_left(used, cap))
    return moved, pushed - moved


def contribution(delta: float, pushed: float, moved: float, per_push: int, over_cap_ratio: float) -> int:
    """這一次推力記多少貢獻：delta 是推力本身（不打人數緩衝的折），緩衝後的 pushed 裡有 moved 推得動、
    其餘超過上限；超過的那一份只記 over_cap_ratio（兩成）。四捨五入成整數。"""
    if pushed <= 0:
        return 0
    inside = moved / pushed
    points = delta * (inside + (1 - inside) * over_cap_ratio)
    return math.floor(points * per_push + 0.5 + 10**-FRACTION_DIGITS)


def recent_days(pushed: dict[str, float], today: int) -> dict[str, float]:
    """每曆日上限的帳（PlayerState.pushed，鍵是「曆日:大勢線 id」）只留今天與昨天兩個曆日的。"""
    days = {str(today), str(today - 1)}
    return {key: value for key, value in pushed.items() if key.partition(":")[0] in days}


def drop_stale(
    active_pushers: dict[str, dict[str, float]], now_time: float, window_seconds: float,
) -> dict[str, dict[str, float]]:
    """活躍名單（WorldState.active_pushers）清掉超過時窗的人；清空的陣營整列拿掉。回傳新的名單，不改傳進來的。"""
    kept = {
        faction: {name: last for name, last in names.items() if now_time - last <= window_seconds}
        for faction, names in active_pushers.items()
    }
    return {faction: names for faction, names in kept.items() if names}


def take_whole(accum: float, added: float) -> tuple[int, float]:
    """原本累積的不足一點的推力 accum 加上這一次的 added：回傳（滿了的整數點數, 剩下的小數）。
    往零的方向取整，所以正負推力會互相抵銷；剩下的小數跟點數同號。"""
    total = round(accum + added, FRACTION_DIGITS)
    whole = math.trunc(total)
    return whole, round(total - whole, FRACTION_DIGITS)


def add_contribution(player: PlayerState, week: int, points: int) -> None:
    """記貢獻：本季總數與那一週（季曆）的帳。推大勢（Game.push_trend）、挑戰打贏（Game._rout）、伏筆做完、
    護糧送到都經過這裡，只有這一份寫法（T4 交接備註第 2 條）。0 點什麼都不記（不留下空的一週）。"""
    if not points:
        return
    player.contrib += points
    player.contrib_weeks[week] = player.contrib_weeks.get(week, 0) + points
