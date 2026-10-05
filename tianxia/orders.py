"""陣營軍令（計畫 T6；軍令文件第二節、3.1～3.4、4.5；濃縮版內容表第三節）。

每週一 00:00（季曆）由季的事發令（world.WEEK_HOOKS → issue）：每個陣營照優先序挑 orders_per_week 道（留一格給進攻的軍令，見 _picks）。個人照做一次記一次
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
OPENING_WEEK = 1  # 開局週（OrderWhen.opening_fronts 只在這一週放寬）


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


def siege_places(content: Content, faction: str, front: str) -> list[str]:
    """這條戰線上打得到敵方陣營隊伍的地點（攻城的個人部分只算打贏敵方陣營的隊伍）；照內容檔的地點順序。
    T6 審查 I2：潁川汝南沒有官軍隊伍，黃巾的攻城在那裡永遠湊不滿，所以沒有這種地點的戰線不發攻城。"""
    enemy = ENEMY.get(faction)
    return [
        loc_id for loc_id, loc in content.locations.items()
        if rules.front_of(content, loc_id) == front
        and any(content.squads[sid].faction == enemy for sid in loc.enemies if sid in content.squads)
    ]


def _issuable(state: GameState, content: Content, t: OrderTemplate, front: str, week: int) -> bool:
    """這種軍令這週在這條戰線發不發得出來（濃縮版內容表 3.1「什麼時候發」）；攻城另外要那條戰線打得到敵方隊伍。
    例外：第 1 週（OPENING_WEEK）、這條戰線在 when.opening_fronts 裡就直接發，front_min／front_max、event_within_weeks、
    losing_by 都不看（FB-054，新手第一週要有一道走得到的軍令）；攻城的「打得到敵方隊伍」照舊先看。"""
    if t.kind == "siege" and not siege_places(content, t.side, front):
        return False
    if week == OPENING_WEEK and front in t.when.opening_fronts:  # 開局週：這條戰線不看局勢（FB-054）
        return True
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


def preferred_offense(week: int) -> str:
    """每週留給進攻的那一格偏好哪一種：奇數週攻城、偶數週打擊（FB-061）。"""
    return "siege" if week % 2 == 1 else "strike"


SUPPLY = ("intercept", "escort")  # 優先序相同的兩種補給軍令（截糧、護糧）


def preferred_supply(week: int) -> str:
    """截糧與護糧同優先序，平手時輪流排前面：奇數週截糧、偶數週護糧（FB-061 審查：不輪流的話，留一格給進攻之後
    守城之外只剩一格優先序 2，平手永遠是截糧贏，護糧一道都發不出）。"""
    return "intercept" if week % 2 == 1 else "escort"


def _picks(state: GameState, content: Content, faction: str, week: int) -> list[tuple[OrderTemplate, str | None, str | None]]:
    """這個陣營這週發哪幾道：照優先序（數字小的先），同一優先序裡先看輪到哪一種補給軍令（preferred_supply，只動截糧、護糧
    兩種），再看戰況越吃緊的戰線先，最後照模板在內容檔的順序。
    FB-061：優先序 1～2 的守城、截糧、護糧幾乎每週把三格佔滿，攻城、打擊輪不到，所以留一格給進攻的軍令（攻城、打擊）：
    偏好的那一種（preferred_offense）有對象就發它，沒有就改發另一種，兩種都沒有就照優先序給下一道；其餘兩格照舊。
    每週只有一格時沒有「其中一格」可留，照優先序。發出的次序仍照優先序（進攻的那一道排在它的優先序上）。"""
    found: list[tuple[tuple[int, int, int, int], OrderTemplate, str | None, str | None]] = []
    for rank, t in enumerate(content.orders.templates):
        if t.side != faction:
            continue
        if t.kind == "strike":
            fid = strike_target(state, content, t)
            if fid is not None:
                found.append(((t.priority, 0, 0, rank), t, None, fid))
            continue
        turn = 1 if t.kind in SUPPLY and t.kind != preferred_supply(week) else 0  # 這週不輪到的那一種補給排後面
        for front in rules.front_ids(content):
            if front in content.orders.slots and _issuable(state, content, t, front, week):
                found.append(((t.priority, turn, -_pressure(faction, _value(state, content, front)), rank), t, front, None))
    found.sort(key=lambda item: item[0])
    slots = content.config.orders_per_week
    reserved = None  # 留給進攻的那一道；沒有留（只有一格、或兩種進攻都沒有對象）就是 None
    if slots >= 2:
        first = preferred_offense(week)
        other = "strike" if first == "siege" else "siege"
        reserved = next((item for kind in (first, other) for item in found if item[1].kind == kind), None)
    rest = [item for item in found if item is not reserved]
    chosen = rest[:slots] if reserved is None else rest[: slots - 1] + [reserved]
    chosen.sort(key=lambda item: item[0])
    return [(t, front, fid) for _, t, front, fid in chosen]


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


# ── 記功與達成 ────────────────────────────────────────────

PERSONAL = {"siege": "win", "defend": "duty", "intercept": "win", "escort": "convoy", "strike": "challenge"}


def _counts(
    content: Content, o: Order, kind: str, location: str | None, front: str | None, squad: str | None,
    squad_faction: str | None, figure: str | None, order: str | None,
) -> bool:
    """這一次個人行動算不算這道軍令的一次（軍令文件 3.1～3.4、4.5）。"""
    if PERSONAL.get(o.template) != kind:
        return False
    if o.template == "siege":  # 在那條戰線遊歷打贏一場敵方陣營的隊伍（操練、流寇不算）
        return front == o.front and squad_faction is not None and squad_faction == ENEMY.get(o.faction)
    if o.template == "intercept":  # 在 {地點} 與相鄰站打贏敵方的運糧隊
        enemy = content.orders.convoy_squads.get(ENEMY.get(o.faction, ""))
        return squad is not None and squad == enemy and location is not None and o.location is not None \
            and location in neighbors(content, o.location)
    if o.template == "defend":  # 在那條戰線做守勢行動
        return front == o.front
    if o.template == "escort":  # 這一道的糧車送到（糧車記著自己是哪一道，見 Convoy.order）
        return order == o.id
    if o.template == "strike":  # 挑戰那位人物本人打贏
        return figure is not None and figure == o.figure
    return False


def _enemy_order(state: GameState, o: Order, template: str) -> Order | None:
    """同一週、同一條戰線，敵方已經達成的那一種軍令。"""
    enemy = ENEMY.get(o.faction)
    return next(
        (x for x in state.world.orders
         if x.faction == enemy and x.week == o.week and x.front == o.front and x.template == template and x.done),
        None,
    )


def _leak(state: GameState, content: Content, o: Order, text: str) -> None:
    """達成時在那一帶外洩一則不寫名字的地方傳聞（傳聞分層 3.3）：有地點就照地點的大區，沒有（攻城、守城）就照戰線的大區
    （戰線 id 跟它主要的大區同名）。"""
    rules.add_rumor(state, text, o.location, content=content, layer="local", named=False)
    rumor = state.world.rumors[-1]
    if rumor.region is None:
        rumor.region = o.front


def _complete(state: GameState, content: Content, o: Order) -> list[str]:
    """湊滿額度：效果只套一次（濃縮版內容表 3.1），發陣營軍情（列前三名）與地方外洩。"""
    o.done, o.done_time = True, state.world.time
    t = template_of(content, o)
    effect, sign = t.effect, SIGN.get(o.faction, 0)
    msgs: list[str] = []
    if o.template == "siege":
        defend = _enemy_order(state, o, "defend")
        halved = defend is not None and template_of(content, defend).effect.halve_enemy_siege
        o.applied = effect.trend // 2 if halved else effect.trend
        msgs += rules.change_trend(state, content, o.front, sign * o.applied)
    elif o.template == "defend":
        siege = _enemy_order(state, o, "siege") if effect.halve_enemy_siege else None
        if siege is not None:  # 敵方已經攻下：收回一半
            back = siege.applied - siege.applied // 2
            siege.applied -= back
            o.applied = back
        else:  # 敵方這週還沒攻下：往己方 3（之後敵方才攻下，只得一半，見上面）
            o.applied = effect.trend
        msgs += rules.change_trend(state, content, o.front, sign * o.applied)
    elif o.template in ("intercept", "escort"):
        o.applied = effect.trend
        msgs += rules.change_trend(state, content, o.front, sign * o.applied)
        event = timetable.next_event_on(state, content, o.front)
        if event is not None and o.faction in SIGN:
            timetable.add_mod(state, content, event.id, o.faction, effect.event_mod)  # 沒有 roll_side 的大事 add_mod 自己略過
    elif o.template == "strike" and o.figure is not None:
        if figures.state_of(state, content, o.figure).status == "active":  # 已經退場、下獄的不再扣（RF3）
            msgs += figures.defeat(state, content, o.figure, -effect.figure_prestige)
    top = sorted(o.progress.items(), key=lambda item: -item[1])[:TOP]  # 同次數照先出力的順序（sorted 是穩定的）
    names = "、".join(o.shown.get(name, name) for name, _ in top)
    news = f"【軍令達成】{fill(state, content, o, t.faction_rumor)}出力最多：{names}。"
    _faction_news(state, o.faction, news)
    _leak(state, content, o, fill(state, content, o, t.leak_rumor))
    return [news] + msgs


def credit(
    state: GameState, content: Content, faction: str | None, name: str, *, kind: str, location: str | None = None,
    front: str | None = None, squad: str | None = None, squad_faction: str | None = None, figure: str | None = None,
    order: str | None = None, weight: int = 1, shown: str | None = None,
) -> list[str]:
    """一次個人行動替這週的軍令記功（軍令文件第二節）：每道符合、還沒達成的加 weight 次（這一版只有第 1 階的行動，都是 1）。
    貢獻不在這裡記——那次行動本身的推動已經經過 Game.push_trend 記過；護糧沒有推動，由引擎另記。
    shown 是軍情列名用的名字（匿名時「某位少俠」），不給就用名號。散人、開關關著回空。"""
    msgs: list[str] = []
    for o in current(state, content, faction):
        if o.done or not _counts(content, o, kind, location, front, squad, squad_faction, figure, order):
            continue
        o.progress[name] = o.progress.get(name, 0) + weight
        o.shown[name] = shown or name
        total = sum(o.progress.values())
        msgs.append(f"（軍令「{title(content, o)}」：你 {o.progress[name]} 次，陣營 {min(total, o.quota)}／{o.quota}）")
        if total >= o.quota:
            msgs += _complete(state, content, o)
    return msgs


def extra_enemies(state: GameState, content: Content, loc_id: str, faction: str | None) -> list[str]:
    """遊歷時多出來的對手：這週有截糧軍令、人在 {地點} 或相鄰的站，就可能遇上敵方的運糧隊（達成之後這週也照樣遇得到）。"""
    enemy = content.orders.convoy_squads.get(ENEMY.get(faction or "", ""))
    if enemy is None:
        return []
    for o in current(state, content, faction):
        if o.template == "intercept" and o.location is not None and loc_id in neighbors(content, o.location):
            return [enemy]
    return []


def escort_at(state: GameState, content: Content, faction: str | None, loc_id: str) -> Order | None:
    """這週在這裡可以接的糧車：還沒達成、起點是這裡的護糧軍令。"""
    return next(
        (o for o in current(state, content, faction) if o.template == "escort" and not o.done and o.start == loc_id), None,
    )


def ambusher(content: Content, faction: str | None) -> str | None:
    """護糧路上撞上的敵方截糧隊：對方的運糧隊。沒有對手陣營（豪強、散人）是 None。"""
    return content.orders.convoy_squads.get(ENEMY.get(faction or "", ""))


# ── 給假人的查詢（計畫 T6「假人」）──────────────────────────────


def win_counts(state: GameState, content: Content, faction: str | None, loc_id: str) -> bool:
    """在這裡遊歷打贏，可能替這週還沒達成的攻城或截糧記一次。"""
    front = rules.front_of(content, loc_id)
    for o in current(state, content, faction):
        if o.done:
            continue
        if o.template == "siege" and o.front == front and loc_id in siege_places(content, o.faction, o.front):
            return True
        if o.template == "intercept" and o.location is not None and loc_id in neighbors(content, o.location):
            return True
    return False


def duty_counts(state: GameState, content: Content, faction: str | None, loc_id: str) -> bool:
    """在這裡做守勢行動，會替這週還沒達成的守城記一次。"""
    front = rules.front_of(content, loc_id)
    return any(o.template == "defend" and not o.done and o.front == front for o in current(state, content, faction))


def strike_on(state: GameState, content: Content, faction: str | None, fid: str) -> bool:
    """這週有還沒達成、打這位人物的打擊軍令。"""
    return any(o.template == "strike" and not o.done and o.figure == fid for o in current(state, content, faction))


def targets(state: GameState, content: Content, faction: str | None) -> list[str]:
    """假人往哪裡走：這週還沒達成的軍令要去的地點（攻城、守城：那條戰線的地點；截糧：{地點} 與相鄰站；護糧：身上有
    這一道的糧車就是終點，沒有而且糧草夠就是起點；打擊：人物當下的所在），照內容檔的地點順序。"""
    from .materials import grain_of  # noqa: PLC0415  只有這裡用得到

    p = state.player
    wanted: set[str] = {p.convoy.to_loc} if p.convoy is not None else set()  # 押著的車一定送到（那一道沒了也照送，T6 審查 I3）
    for o in current(state, content, faction):
        if o.done:
            continue
        if o.template == "siege":
            wanted |= set(siege_places(content, o.faction, o.front))
        elif o.template == "defend":
            wanted |= {loc for loc in content.locations if rules.front_of(content, loc) == o.front}
        elif o.template == "intercept" and o.location is not None:
            wanted |= neighbors(content, o.location)
        elif o.template == "escort":
            if p.convoy is None and o.start is not None and grain_of(state, content) >= content.config.convoy_grain:
                wanted.add(o.start)
        elif o.template == "strike" and o.figure is not None:
            fs = figures.state_of(state, content, o.figure)
            if fs.status == "active" and fs.location:
                wanted.add(fs.location)
    return [loc for loc in content.locations if loc in wanted]
