"""推力規則的算式（計畫 T3、第一季設計第七節）：陣營人數緩衝、每人每曆日上限、貢獻、不足一點的推力累積。
純函式，只看傳進來的數字與狀態，不碰引擎、不改任何東西；怎麼串起來見 engine.Game.push_trend。"""
from __future__ import annotations

import math

from . import calendar
from .models import Content, PushResistance
from .state import GameState, PlayerState, WorldState

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


RESISTED_LINE = "深入敵境，推進艱難。"  # 待 joy 潤：盡頭阻力打了折的那一下，推動那一行後面多這一句（出陣探索與地盤設計 5.1）
# 站在自家陣營控制的地方（守、巡哨、傳道……）推過頭：不是深入敵境（FB-432；待 joy 潤）
STEADY_LINE = "此地已穩，再推也只是聊盡人事。"


def resistance_share(value: float, direction: float, tuning: PushResistance) -> float:
    """推之前戰線在 value、這一下往 direction（正：往 100；負：往 0）推：打幾折（設計 5.1）。只看推的方向：往盡頭推
    （50 以上還往上、50 以下還往下）照離 50 多遠——full_within（15）以內全額（35～65，亂局帶）、half_within（35）以內
    mid_share、再外面 far_share；往回拉、正好在 50、方向是 0 都全額。"""
    if direction == 0 or value == 50 or (direction > 0) != (value > 50):
        return 1.0
    far = abs(value - 50)
    if far <= tuning.full_within:
        return 1.0
    if far <= tuning.half_within:
        return tuning.mid_share
    return tuning.far_share


def tuning_for(world: WorldState, content: Content) -> PushResistance:
    """這一季的盡頭阻力用哪一組數字：21 天季照 Season21Daily 的兩檔（push_mid_share、push_far_share；離 50 的兩個邊界與開關照
    Config.push_resistance，正式季整合設計 7.4），其他季就是 Config.push_resistance 本身。出陣、事件、軍令、大勢人物都走它。"""
    tuning = content.config.push_resistance
    if not calendar.season21_on(world, content):
        return tuning
    s21 = content.config.season21_daily
    return tuning.model_copy(update={"mid_share": s21.push_mid_share, "far_share": s21.push_far_share})


def resistance(value: float, delta: float, tuning: PushResistance) -> float:
    """打過盡頭阻力的推力（delta 帶正負號）。"""
    return delta * resistance_share(value, delta, tuning)


def round_half_away(x: float) -> int:
    """四捨五入成整數，.5 往離 0 遠的方向進（軍令達成推的整點：1.6 → 2、−0.6 → −1）。"""
    return int(math.copysign(math.floor(abs(x) + 0.5), x))
