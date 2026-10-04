"""陣營軍令（計畫 T6；軍令文件第二節、3.1～3.4、4.5；濃縮版內容表第三節）。

每週一 00:00（季曆）由季的事發令（world.WEEK_HOOKS → issue）：每個陣營照優先序挑 orders_per_week 道。個人照做一次記一次
（credit，由引擎在遊歷打贏、守勢行動、糧車送到、挑戰打贏時呼叫）；全陣營湊滿額度（quota）那一刻套一次效果，發陣營軍情
（列前三名）與一則不具名的地方傳聞。

全部掛在第一季開關後面（rules.season_one：開關開著、這一季開季時也蓋了章）；開關關著時每個函式都什麼都不做、回空的。
**陣營的事只寫成陣營軍情（Rumor.layer＝"faction"），issue 不回傳任何訊息**：季的事回傳的訊息會進觸發同步那個人的
江湖紀錄，那個人可能是別的陣營。

不 import world、atlas、engine（world 會 import 這裡，掛 WEEK_HOOKS）。"""
from __future__ import annotations

import math
import random

from . import calendar, figures, rules, timetable
from .models import Content, OrderTemplate
from .state import GameState, Order

KIND_NAMES = {"siege": "攻城", "defend": "守城", "intercept": "截糧", "escort": "護糧", "strike": "打擊"}
SIGN = {"guan": -1, "huang": 1}  # 往己方推：戰況 0 是官軍穩控、100 是黃巾控制
ENEMY = {"guan": "huang", "huang": "guan"}
TOP = 3  # 達成時陣營軍情列出前幾名（軍令文件第二節）
ISSUED = "本週軍令："  # 發令那一則陣營軍情的開頭


def active(state: GameState, content: Content) -> bool:
    """這一季有軍令：第一季的規則開著（開關＋這一季的章），而且內容有軍令模板。"""
    return rules.season_one(content, state.world) and bool(content.orders.templates)


def quota(content: Content, template: OrderTemplate) -> int:
    """陣營總額度：照伺服器人數上限等比例換算（模板寫的是 3000 人的量），最少 order_quota_min。"""
    cfg = content.config
    return max(cfg.order_quota_min, math.ceil(template.quota_base * cfg.server_max_players / 3000))


def week_of(state: GameState, content: Content) -> int:
    return calendar.point(state.world.time, content, state.world).week


def current(state: GameState, content: Content, faction: str | None) -> list[Order]:
    """這一週、這個陣營的軍令（含已達成的）；散人、開關關著是空的。"""
    if faction is None or not active(state, content):
        return []
    week = week_of(state, content)
    return [o for o in state.world.orders if o.faction == faction and o.week == week]


def template_of(content: Content, order: Order) -> OrderTemplate:
    return next(t for t in content.orders.templates if t.kind == order.template and t.side == order.faction)


def neighbors(content: Content, loc_id: str) -> set[str]:
    """這個地點與相鄰的站（截糧：{地點} 與相鄰站遊歷都可能遇上糧隊）。"""
    return {loc_id} | {str(conn) for conn in content.locations[loc_id].connections}


def figure_name(content: Content, fid: str | None) -> str:
    return figures.name_of(content, fid) if fid is not None else ""


def _loc_name(content: Content, loc_id: str | None) -> str:
    return content.locations[loc_id].name if loc_id is not None and loc_id in content.locations else ""


def title(content: Content, order: Order) -> str:
    """軍令的短標題：「攻城・潁川汝南」「截糧・南陽郊野」「護糧・新野→宛城」「打擊・張曼成」。"""
    if order.template == "escort":
        place = f"{_loc_name(content, order.start)}→{_loc_name(content, order.end)}"
    elif order.template == "intercept":
        place = _loc_name(content, order.location)
    elif order.template == "strike":
        place = figure_name(content, order.figure)
    else:
        place = rules.trend_name(content, order.front) if order.front else ""
    return f"{KIND_NAMES.get(order.template, order.template)}・{place}"


def _value(state: GameState, content: Content, front: str) -> int:
    return rules.trend_value(state, content, front)


def _pressure(side: str, value: int) -> int:
    """這條戰線對這一方有多吃緊：官軍看戰況（越高越吃緊）、黃巾看 100－戰況；沒有戰線方向的陣營一律 0。"""
    if side == "guan":
        return value
    if side == "huang":
        return 100 - value
    return 0


def _event_within(state: GameState, content: Content, front: str, weeks: float):
    """這條戰線的下一件時刻表大事在 weeks 週（季曆）以內就回傳它，否則 None。"""
    event = timetable.next_event_on(state, content, front)
    if event is None:
        return None
    horizon = weeks * calendar.WEEK / calendar.cal_scale(content, state.world)
    gap = timetable.when(state, content, event) - state.world.time
    return event if gap <= horizon + calendar.EPS_SECONDS else None


def _enemy_sieged_last_week(state: GameState, side: str, front: str, week: int) -> bool:
    enemy = ENEMY.get(side)
    return any(
        o.done and o.faction == enemy and o.template == "siege" and o.front == front and o.week == week - 1
        for o in state.world.orders
    )


def _issuable(state: GameState, content: Content, t: OrderTemplate, front: str, week: int) -> bool:
    """這種軍令這週在這條戰線發不發得出來（濃縮版內容表 3.1「什麼時候發」）。"""
    when, v = t.when, _value(state, content, front)
    if when.front_min is not None and v < when.front_min:
        return False
    if when.front_max is not None and v > when.front_max:
        return False
    if when.event_within_weeks is not None and _event_within(state, content, front, when.event_within_weeks) is None:
        return False
    if when.losing_by is not None and _pressure(t.side, v) < 50 + when.losing_by:
        return when.or_enemy_siege and _enemy_sieged_last_week(state, t.side, front, week)
    return True


def strike_target(state: GameState, content: Content, template: OrderTemplate) -> str | None:
    """打擊的 {人物}（濃縮版內容表 3.2）：官軍、黃巾挑敵方在交戰戰線（戰況在 front_min～front_max）上聲威最低的；
    豪強挑官軍或黃巾在亂局戰線上聲威最低的，沒有亂局戰線就在全部有戰線的人物裡挑。只算在場（active）、有戰線的人物；
    同聲威照人物表的順序。都沒有時是 None（這週不發打擊）。"""
    side, when = template.side, template.when
    picks: list[tuple[int, str, str]] = []
    for fid, figure in content.figures.items():
        fs = figures.state_of(state, content, fid)
        if fs.status != "active" or fs.front is None:
            continue
        if side in ENEMY:
            if figure.faction != ENEMY[side]:
                continue
            v = _value(state, content, fs.front)
            if (when.front_min is not None and v < when.front_min) or (when.front_max is not None and v > when.front_max):
                continue
        elif figure.faction not in ENEMY:
            continue
        picks.append((fs.prestige, fid, fs.front))
    if side not in ENEMY:
        picks = [p for p in picks if rules.in_chaos(state, content, p[2])] or picks
    return min(picks, key=lambda p: p[0])[1] if picks else None


def _picks(state: GameState, content: Content, faction: str, week: int) -> list[tuple[OrderTemplate, str | None, str | None]]:
    """這個陣營這週發哪幾道：照優先序（數字小的先），同一優先序裡戰況越吃緊的戰線先，再照模板在內容檔的順序。"""
    found: list[tuple[tuple[int, int, int], OrderTemplate, str | None, str | None]] = []
    for rank, t in enumerate(content.orders.templates):
        if t.side != faction:
            continue
        if t.kind == "strike":
            fid = strike_target(state, content, t)
            if fid is not None:
                found.append(((t.priority, 0, rank), t, None, fid))
            continue
        for front in rules.front_ids(content):
            if front in content.orders.slots and _issuable(state, content, t, front, week):
                found.append(((t.priority, -_pressure(faction, _value(state, content, front)), rank), t, front, None))
    found.sort(key=lambda item: item[0])
    return [(t, front, fid) for _, t, front, fid in found[: content.config.orders_per_week]]


def _caller(state: GameState, content: Content) -> str:
    """黃巾的號令：照順序第一個沒退場的人（張角→張寶→張梁）。"""
    for caller in content.orders.callers:
        if caller.figure is None or not figures.is_out(state, caller.figure):
            return caller.text
    return ""


def _commander(state: GameState, content: Content, order: Order) -> str:
    fid = figures.commander(state, content, order.front, order.faction) if order.front is not None else None
    return figure_name(content, fid) if fid is not None else content.orders.commander_fallback.get(order.faction, "")


def fill(state: GameState, content: Content, order: Order, text: str) -> str:
    """填插槽：{戰線}{地點}{起點}{終點}{人物}；{主將} 是那條戰線己方當下的主將，沒有就寫泛稱（RF3）；{號令} 是黃巾發令的人。"""
    slots = {
        "{戰線}": rules.trend_name(content, order.front) if order.front else "",
        "{地點}": _loc_name(content, order.location),
        "{起點}": _loc_name(content, order.start),
        "{終點}": _loc_name(content, order.end),
        "{人物}": figure_name(content, order.figure),
        "{主將}": _commander(state, content, order),
        "{號令}": _caller(state, content),
    }
    for slot, value in slots.items():
        text = text.replace(slot, value)
    return text


def _build(
    state: GameState, content: Content, t: OrderTemplate, week: int, front: str | None, fid: str | None,
) -> Order:
    location = start = end = None
    if t.kind in ("intercept", "escort"):
        slot = content.orders.slots[front][t.side]
        if t.kind == "intercept":
            location = slot.intercept
        else:
            start, end = slot.escort
            location = start
    elif t.kind == "strike":
        fs = figures.state_of(state, content, fid)
        front, location = fs.front, fs.location
    key = fid if t.kind == "strike" else front
    order = Order(
        id=f"{week}:{t.side}:{t.kind}:{key}", template=t.kind, faction=t.side, week=week, front=front,
        location=location, start=start, end=end, figure=fid, quota=quota(content, t), text="",
    )
    order.text = fill(state, content, order, t.text)
    return order


def _faction_news(state: GameState, faction: str, text: str) -> None:
    rules.add_rumor(state, text, layer="faction", faction=faction)


def issue(state: GameState, content: Content, week: int, rng: random.Random) -> list[str]:
    """週初發令（world.WEEK_HOOKS 每週一 00:00 跑一次，week 是剛跨進的那一週）。先清掉上週沒達成的（達成的留著）；
    只發「現在這一週」：追趕時一次跨過好幾週，跨過的週不補發（RF1）。每道寫一則陣營軍情「本週軍令：…」。
    一律回空串列（見檔頭：回傳的訊息會進觸發同步那個人的江湖紀錄）。rng 沒用到：挑法是決定性的。"""
    if not active(state, content):
        return []
    w = state.world
    w.orders = [o for o in w.orders if o.done or o.week >= week]
    if week != week_of(state, content) or any(o.week == week for o in w.orders):
        return []
    for faction in content.scenario.factions:
        for t, front, fid in _picks(state, content, faction.id, week):
            order = _build(state, content, t, week, front, fid)
            w.orders.append(order)
            _faction_news(state, faction.id, f"{ISSUED}{order.text}")
    return []
