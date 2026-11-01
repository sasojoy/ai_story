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

from . import calendar, figures, push, rules, timetable
from .models import Content, OrderTemplate
from .state import GameState, Order, WorldState

KIND_NAMES = {"siege": "攻城", "defend": "守城", "intercept": "截糧", "escort": "護糧", "strike": "打擊"}
SIGN = {"guan": -1, "huang": 1}  # 往己方推：戰況 0 是官軍穩控、100 是黃巾控制
ENEMY = {"guan": "huang", "huang": "guan"}
TOP = 3  # 達成時陣營軍情列出前幾名（軍令文件第二節）
ISSUED = "本週軍令："  # 發令那一則陣營軍情的開頭
ISSUED_DAY = "今日軍令："  # 21 天季每天發令那一則的開頭（正式季整合設計 7.1；待 joy 潤）
DONE = "【軍令達成】"  # 達成那一則陣營軍情的開頭（「你不在的時候」照這兩個開頭挑陣營軍情的要點）
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


def daily(state: GameState, content: Content) -> bool:
    """21 天季：軍令每天 00:00 發一批（正式季整合設計 7.1），照「期」記的是季曆第幾天；其他季照週。軍令的字照同一個判斷
    （calendar.orders_daily，FB-502）。"""
    return calendar.orders_daily(state.world, content)


def period_of(state: GameState, content: Content) -> int:
    """軍令這一期的號碼（Order.week 存的就是它）：21 天季是季曆第幾天，其他季是第幾週。貢獻照舊照週記（week_of）。"""
    at = calendar.point(state.world.time, content, state.world)
    return at.cal_day if daily(state, content) else at.week


def deadline(state: GameState, content: Content, order: Order) -> float:
    """這一道的截止（世界秒）：21 天季是隔天 00:00，其他季是下週一 00:00。"""
    w = state.world
    if daily(state, content):
        return calendar.day_start(order.week + 1, content, w)
    return calendar.week_start(order.week + 1, content, w)


def current(state: GameState, content: Content, faction: str | None) -> list[Order]:
    """這一週、這個陣營的軍令（含已達成的）；散人、開關關著是空的。"""
    if faction is None or not active(state, content):
        return []
    period = period_of(state, content)
    return [o for o in state.world.orders if o.faction == faction and o.week == period]


def template_of(content: Content, order: Order) -> OrderTemplate:
    return next(t for t in content.orders.templates if t.kind == order.template and t.side == order.faction)


def neighbors(content: Content, loc_id: str) -> set[str]:
    """這個地點與相鄰的站（截糧：{地點} 與相鄰站遊歷都可能遇上糧隊）。"""
    return {loc_id} | {str(conn) for conn in content.locations[loc_id].connections}


def intercept_spots(content: Content, loc_id: str) -> set[str]:
    """截糧軍令的運糧隊在哪幾站（遇得上、打贏記功、假人往哪走都照它）：出陣開著時只在 {地點} 本身（FB-248，PM 2026-10-15：截糧的地點
    一律是戰線地點；相鄰站不再有糧隊，自家大本營截糧那一週的出陣照舊是守），關著時照舊是 {地點} 與相鄰站（neighbors）。"""
    from . import sortie  # noqa: PLC0415  sortie → rules、territory：延後 import 只是保險

    return {loc_id} if sortie.on(content) else neighbors(content, loc_id)


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
    horizon = weeks * calendar.week_seconds(content, state.world)  # 7 天濃縮季的「週」是一段的平均
    gap = timetable.when(state, content, event) - state.world.time
    return event if gap <= horizon + calendar.EPS_SECONDS else None


def _enemy_sieged_last_week(state: GameState, side: str, front: str, week: int) -> bool:
    enemy = ENEMY.get(side)
    return any(
        o.done and o.faction == enemy and o.template == "siege" and o.front == front and o.week == week - 1
        for o in state.world.orders
    )


def siege_places(content: Content, faction: str, front: str, world: WorldState | None = None) -> list[str]:
    """這條戰線上打得到敵方陣營隊伍的地點（攻城的個人部分只算打贏敵方陣營的隊伍）；照內容檔的地點順序。
    地盤開著（＝領地爭奪）：這一邊此刻進度最高、推得動的那一塊（見下）。關著照舊看地點的 enemies。
    T6 審查 I2：沒有這種地點的戰線，攻城永遠湊不滿，不發攻城。潁川汝南以前沒有官軍隊伍、黃巾在那裡不發攻城；
    FB-184 開了官軍大營（整支官軍）之後黃巾在潁川汝南也有攻城（攻打官軍大營）。"""
    enemy = ENEMY.get(faction)
    from . import conquest  # noqa: PLC0415  conquest → territory → rules：在函式裡 import

    if conquest.on(content, world):
        # 領地爭奪（裁決 11；翻地與爭搶 PM 2026-10-20 第 1 條）：這條線上這一邊此刻進度最高、推得動的那一塊（conquest_day.today），而且那裡出陣攻打的對手每一路打贏都記得到
        # （同 _counts 的 siege_win，FB-531）。打贏那裡的守軍就算，還沒人佔的中立地、被敵方佔下的中立地站的中立駐軍與流寇也算
        # （裁決 20，PM 2026-10-21）。敵方大本營與廣宗搶不下（conquest.targets 先排掉），推不動、不列（裁決 18）
        return [
            loc_id for loc_id in _today(content, world, faction, "attack")
            if conquest.line_of(world, content, loc_id) == front
            and _all_enemy(content, faction, conquest.sortie_foes(world, content, loc_id, faction), garrison=True)
        ]
    return [
        loc_id for loc_id, loc in content.locations.items()
        if rules.front_of(content, loc_id) == front
        and any(content.squads[sid].faction == enemy for sid in loc.enemies if sid in content.squads)
    ]


def siege_win(faction: str | None, squad_faction: str | None, garrison: bool = False) -> bool:
    """打贏這一路算不算 faction 的攻城（軍令文件 3.1：敵方陣營的隊伍；操練、流寇、中立駐軍不算）。記功（_counts）與領地爭奪開著時
    列地點（siege_places）都問它：軍令卡、假人、記功同一個判斷（FB-531）。
    garrison（領地爭奪在這一季生效，裁決 20，PM 2026-10-21）：攻城＝此刻進度最高的那一塊（翻地與爭搶），打贏那裡的守軍就算——敵方陣營的兵，
    或沒有陣營的中立駐軍、流寇；自家的、別的陣營（豪強）的隊伍照舊不算。地點是不是那一塊由呼叫端看。"""
    if garrison and squad_faction is None:
        return True
    return squad_faction is not None and squad_faction == ENEMY.get(faction or "")


def _all_enemy(content: Content, faction: str, squads: list[str], garrison: bool = False) -> bool:
    """這裡出陣攻打的對手（至少一路）每一路打贏都算 faction 的攻城（garrison 同 siege_win）。"""
    return bool(squads) and all(siege_win(faction, content.squads[sid].faction, garrison) for sid in squads)


def _issuable(state: GameState, content: Content, t: OrderTemplate, front: str, week: int, opening: bool) -> bool:
    """這種軍令這週在這條戰線發不發得出來（濃縮版內容表 3.1「什麼時候發」）；攻城另外要那條戰線打得到敵方隊伍。
    例外：第 1 週（OPENING_WEEK）、這條戰線在 when.opening_fronts 裡就直接發，front_min／front_max、event_within_weeks、
    losing_by 都不看（FB-054，新手第一週要有一道走得到的軍令）；攻城的「打得到敵方隊伍」照舊先看。"""
    if t.kind == "siege" and not siege_places(content, t.side, front, state.world):
        return False
    if opening and front in t.when.opening_fronts:  # 開局週：這條戰線不看局勢（FB-054；21 天季是季曆第 1 週的每一天）
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
    opening = calendar.point(state.world.time, content, state.world).week == 1 if daily(state, content) else week == OPENING_WEEK
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
            if front in content.orders.slots and _issuable(state, content, t, front, week, opening):
                found.append(((t.priority, turn, -_pressure(faction, _value(state, content, front)), rank), t, front, None))
    found.sort(key=lambda item: item[0])
    if daily(state, content):
        chosen = _daily_choice(found, week, content.config.season21_daily.orders_per_day)
        return [(t, front, fid) for _, t, front, fid in chosen]
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


DAILY_TURNS = ("defend", "offense", "supply")  # 21 天季一天一道時輪流的三組：守、進攻（攻城、打擊）、補給（截糧、護糧）


def _daily_choice(found: list, day: int, slots: int) -> list:
    """21 天季一天的軍令（正式季整合設計 7.1，五種照舊）：第一格照第幾天輪流挑守、進攻、補給（進攻與補給照 preferred_offense／
    preferred_supply 偏好那一種），那一組這一天沒有候選就照優先序；其餘的格照優先序。found 已照優先序排好。"""
    if slots <= 0 or not found:
        return []
    group = DAILY_TURNS[(day - 1) % len(DAILY_TURNS)]
    kinds = {"defend": ("defend",), "offense": (preferred_offense(day), "strike" if preferred_offense(day) == "siege" else "siege"),
             "supply": (preferred_supply(day), "escort" if preferred_supply(day) == "intercept" else "intercept")}[group]
    first = next((item for kind in kinds for item in found if item[1].kind == kind), found[0])
    rest = [item for item in found if item is not first][: slots - 1]
    return sorted([first, *rest], key=lambda item: item[0])


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
    """填插槽：{戰線}{地點}{起點}{終點}{人物}；{主將} 是那條戰線己方當下的主將，沒有就寫泛稱（RF3）；{號令} 是黃巾發令的人；
    {本週}{這週} 照季寫（軍令每天一道的季〔21 天季、7 天濃縮季〕寫「今日」「今天」；其他季原本的字，calendar.week_word，
    FB-501、FB-502）。"""
    slots = {
        "{本週}": calendar.week_word("order_this", content, state.world),
        "{這週}": calendar.week_word("order_that", content, state.world),
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


def issue_day(state: GameState, content: Content, day: int, rng: random.Random, *, redraw: bool = False) -> list[str]:
    """21 天季每天 00:00 發令（world.DAY_HOOKS；正式季整合設計 7.1）：同 issue，期是季曆第幾天、一個陣營 orders_per_day 道（輪流挑，
    _daily_choice）、陣營軍情寫「今日軍令：」。其他季什麼都不做（照週一那一串）。"""
    if not active(state, content) or not daily(state, content):
        return []
    return _issue(state, content, day, ISSUED_DAY, redraw)


def issue(state: GameState, content: Content, week: int, rng: random.Random, *, redraw: bool = False) -> list[str]:
    """週初發令（world.WEEK_HOOKS 每週一 00:00 跑一次，week 是剛跨進的那一週）。先清掉上週沒達成的（達成的留著）；
    只發「現在這一週」：追趕時一次跨過好幾週，跨過的週不補發（RF1）。每道寫一則陣營軍情「本週軍令：…」。
    一律回空串列（見檔頭：回傳的訊息會進觸發同步那個人的江湖紀錄）。rng 沒用到：挑法是決定性的。
    redraw：管理者的「立刻發本週軍令」（管理者觸發鈕，審查 I-1）——這一週還沒達成的拿掉、照同樣的挑法重挑；已經達成的原封不動
    （進度、套過的效果、給 _enemy_order 與下週 or_enemy_siege 讀的紀錄都留著），重挑出來跟它同一個 id 的那一道跳過、不發軍情，
    所以同一道不會達成兩次。週一的掛鉤不帶它，照舊。"""
    if not active(state, content) or daily(state, content):  # 21 天季改走每天那一串（issue_day）
        return []
    return _issue(state, content, week, ISSUED, redraw)


def _issue(state: GameState, content: Content, week: int, prefix: str, redraw: bool) -> list[str]:
    """發一期軍令（issue、issue_day 共用；week 是這一期的號碼，21 天季是季曆第幾天）。"""
    w = state.world
    w.orders = [o for o in w.orders if o.done or o.week >= week]
    if week != period_of(state, content):
        return []
    done = {o.id for o in w.orders if o.week == week and o.done}
    if redraw:
        w.orders = [o for o in w.orders if o.week != week or o.done]
    elif any(o.week == week for o in w.orders):
        return []
    for faction in content.scenario.factions:
        if faction.allies:  # 豪強分屬兩軍：豪強接依附那一軍的軍令，自己沒有軍令（豪強第三方的打擊 2026-10-31 拿掉）
            continue
        for t, front, fid in _picks(state, content, faction.id, week):
            order = _build(state, content, t, week, front, fid)
            if order.id in done:
                continue
            w.orders.append(order)
            _faction_news(state, faction.id, f"{prefix}{order.text}")
    return []


# ── 記功與達成 ────────────────────────────────────────────

PERSONAL = {"siege": "win", "defend": "duty", "intercept": "win", "escort": "convoy", "strike": "challenge"}
# 領地爭奪：自家被戰書凍結的那一塊，攻城戰站守方、守住了（Game._settle_siege 替每一個守方的人記一次；FB-605）。那一塊守不動進度，
# 在那裡出陣守、按守勢行動（duty）不算；別的守城地方反過來只認 duty
SIEGE_GUARD = "siege_guard"


def _today(content: Content, world: WorldState | None, side: str | None, how: str) -> list[str]:
    """領地爭奪：這一邊此刻進度最高、推得動的那一塊（attack），或自家被推得最高、守得動的那一塊（defend）（conquest_day.today；
    翻地與爭搶 PM 2026-10-20 第 1 條；第二批是每天公告的目標，投票與公告拿掉了）。"""
    from . import conquest_day  # noqa: PLC0415  conquest_day → conquest → territory → rules：在函式裡 import

    return conquest_day.today(world, content, side, how) if world is not None and side is not None else []


def defend_places(content: Content, world: WorldState | None, o: Order) -> list[str]:
    """領地爭奪在這一季生效時，這道守城軍令記得了次數的地點（裁決 11、24；FB-565）：這條戰線上自家佔著、被推得最高、守得動的區塊
    （conquest_day.today 的 defend，翻地與爭搶 PM 2026-10-20 第 1 條；沒人在推就沒有），加上自家被戰書凍結的那幾塊（FB-605：那裡記的是攻城戰守住，
    _counts 的 SIEGE_GUARD）。記功（_counts）、假人往哪走（targets）、守城軍令卡的做法
    （atlas.order_how）、輿圖的守城標記（mapdata._order_marks）、duty_counts 都問它，列的與記的不會對不上。
    關著的季是空的（舊規則整條戰線都記，各處照舊）。"""
    from . import conquest  # noqa: PLC0415  conquest → territory → rules：在函式裡 import

    if o.front is None or not conquest.on(content, world):
        return []
    return [loc for loc in _today(content, world, o.faction, "defend") if conquest.line_of(world, content, loc) == o.front]


def _counts(
    content: Content, o: Order, kind: str, location: str | None, front: str | None, squad: str | None,
    squad_faction: str | None, figure: str | None, order: str | None, world: WorldState | None = None,
) -> bool:
    """這一次個人行動算不算這道軍令的一次（軍令文件 3.1～3.4、4.5）。world 給了而且領地爭奪在這一季生效時，攻城與守城照今天的時程表
    （裁決 11；翻地與爭搶 PM 2026-10-20 第 1 條：攻城＝這一邊此刻進度最高的那一塊打贏那裡的守軍〔siege_win(garrison=True)：敵方陣營的兵，
    中立駐軍、流寇也算，裁決 20；同 siege_places，FB-531〕；守城＝自家被推得最高的那一塊，被戰書凍結的那一塊認攻城戰守住〔SIEGE_GUARD，FB-605〕）。"""
    from . import conquest  # noqa: PLC0415

    guarding = kind == SIEGE_GUARD and o.template == "defend"
    if PERSONAL.get(o.template) != kind and not guarding:
        return False
    on = conquest.on(content, world)
    if o.template == "defend" and on:
        if location not in defend_places(content, world, o):  # 守城認自家被推得最高的那一塊（裁決 24；FB-565 卡與輿圖也讀它）
            return False
        return guarding == (conquest.frozen(world, location) is not None)  # 凍結的那一塊只認攻城戰守住，別處只認出陣守、守勢行動
    if guarding:  # 攻城戰只在領地爭奪的季
        return False
    if o.template == "siege" and on:
        spots = _today(content, world, o.faction, "attack")
        if location not in spots or conquest.line_of(world, content, location) != o.front:
            return False
        return siege_win(o.faction, squad_faction, garrison=True)
    if o.template == "siege":  # 在那條戰線遊歷打贏一場敵方陣營的隊伍（操練、流寇不算）
        return front == o.front and siege_win(o.faction, squad_faction)
    if o.template == "intercept":  # 在運糧隊在的那幾站（intercept_spots）打贏敵方的運糧隊
        enemy = content.orders.convoy_squads.get(ENEMY.get(o.faction, ""))
        return squad is not None and squad == enemy and location is not None and o.location is not None \
            and location in intercept_spots(content, o.location)
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


def front_push(state: GameState, content: Content, front: str, amount: int) -> tuple[int, list[str]]:
    """軍令達成推戰線 amount 點（帶正負號）：盡頭阻力開著時照推之前的戰線打折（push.resistance，出陣探索與地盤設計 5.1），
    四捨五入成整點（push.round_half_away）。回傳（真的推的整點, change_trend 的訊息）。時刻表、決戰、管理者不走這裡。"""
    tuning = push.tuning_for(state.world, content)  # 21 天季照自己那一組（7.4）
    moved = push.round_half_away(amount)
    if tuning.enabled and amount:
        moved = push.round_half_away(push.resistance(rules.trend_value(state, content, front), amount, tuning))
    return moved, rules.change_trend(state, content, front, moved)


def _complete(state: GameState, content: Content, o: Order) -> list[str]:
    """湊滿額度：效果只套一次（濃縮版內容表 3.1），發陣營軍情（列前三名）與地方外洩。
    推戰線走 front_push（盡頭阻力）；o.applied 記真的推了幾點（阻力關著、或沒有方向〔SIGN 沒有這個陣營〕時照寫好的量記，同以前）。"""
    o.done, o.done_time = True, state.world.time
    t = template_of(content, o)
    effect, sign = t.effect, SIGN.get(o.faction, 0)
    share = content.config.season21_daily.order_effect_share if daily(state, content) else 1.0  # 21 天季一天一道：效果量打折（7.1）
    msgs: list[str] = []

    def apply(nominal: int) -> int:
        moved, lines = front_push(state, content, o.front, sign * nominal * share)
        msgs.extend(lines)
        return abs(moved) if sign else nominal

    if o.template == "siege":
        defend = _enemy_order(state, o, "defend")
        halved = defend is not None and template_of(content, defend).effect.halve_enemy_siege
        o.applied = apply(effect.trend // 2 if halved else effect.trend)
    elif o.template == "defend":
        siege = _enemy_order(state, o, "siege") if effect.halve_enemy_siege else None
        # 敵方已經攻下：收回一半；敵方這週還沒攻下：往己方 3（之後敵方才攻下，只得一半，見上面）
        o.applied = apply(siege.applied - siege.applied // 2 if siege is not None else effect.trend)
        if siege is not None:  # 真的收回多少，就從對方那一筆扣多少
            siege.applied -= o.applied
    elif o.template in ("intercept", "escort"):
        o.applied = apply(effect.trend)
        event = timetable.next_event_on(state, content, o.front)
        if event is not None and o.faction in SIGN:
            timetable.add_mod(state, content, event.id, o.faction, effect.event_mod)  # 沒有 roll_side 的大事 add_mod 自己略過
    elif o.template == "strike" and o.figure is not None:
        if figures.state_of(state, content, o.figure).status == "active":  # 已經退場、下獄的不再扣（RF3）
            msgs += figures.defeat(state, content, o.figure, -effect.figure_prestige * share)
    top = sorted(o.progress.items(), key=lambda item: -item[1])[:TOP]  # 同次數照先出力的順序（sorted 是穩定的）
    names = "、".join(o.shown.get(name, name) for name, _ in top)
    news = f"{DONE}{fill(state, content, o, t.faction_rumor)}出力最多：{names}。"
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
    shown 是軍情列名用的名字，不給就用名號——引擎一律不給（陣營軍情一律具名，傳聞分層第七節）；這一版之前記下的
    「某位少俠」照舊。散人、開關關著回空。"""
    msgs: list[str] = []
    for o in current(state, content, faction):
        if o.done or not _counts(content, o, kind, location, front, squad, squad_faction, figure, order, state.world):
            continue
        o.progress[name] = o.progress.get(name, 0) + weight
        o.shown[name] = shown or name
        total = sum(o.progress.values())
        msgs.append(f"（軍令「{title(content, o)}」：你 {o.progress[name]} 次，陣營 {min(total, o.quota)}／{o.quota}）")
        if total >= o.quota:
            msgs += _complete(state, content, o)
    return msgs


def extra_enemies(state: GameState, content: Content, loc_id: str, faction: str | None) -> list[str]:
    """出陣（關著時遊歷）多出來的對手：這週有截糧軍令、人在運糧隊在的那幾站（intercept_spots：出陣開著時只有 {地點}，關著時
    {地點} 或相鄰的站），就可能遇上敵方的運糧隊（達成之後這週也照樣遇得到）。"""
    enemy = content.orders.convoy_squads.get(ENEMY.get(faction or "", ""))
    if enemy is None:
        return []
    for o in current(state, content, faction):
        if o.template == "intercept" and o.location is not None and loc_id in intercept_spots(content, o.location):
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
        if o.template == "siege" and o.front == front and loc_id in siege_places(content, o.faction, o.front, state.world):
            return True
        if o.template == "intercept" and o.location is not None and loc_id in intercept_spots(content, o.location):
            return True
    return False


def duty_counts(state: GameState, content: Content, faction: str | None, loc_id: str) -> bool:
    """在這裡做守勢行動，會替這週還沒達成的守城記一次（領地爭奪：自家被推得最高的那一塊，裁決 11、翻地與爭搶）。"""
    from . import conquest  # noqa: PLC0415

    if conquest.on(content, state.world):
        return any(o.template == "defend" and not o.done and _counts(content, o, "duty", loc_id, None, None, None, None, None, state.world)
                   for o in current(state, content, faction))
    front = rules.front_of(content, loc_id)
    return any(o.template == "defend" and not o.done and o.front == front for o in current(state, content, faction))


def strike_on(state: GameState, content: Content, faction: str | None, fid: str) -> bool:
    """這週有還沒達成、打這位人物的打擊軍令。"""
    return any(o.template == "strike" and not o.done and o.figure == fid for o in current(state, content, faction))


def targets(state: GameState, content: Content, faction: str | None, skip: frozenset[str] = frozenset()) -> list[str]:
    """假人往哪裡走：這週還沒達成的軍令要去的地點（攻城、守城：那條戰線的地點；截糧：運糧隊在的那幾站〔intercept_spots〕；護糧：身上有
    這一道的糧車就是終點，沒有而且糧草夠就是起點；打擊：人物當下的所在），照內容檔的地點順序。skip 裡的那幾種軍令不算（假人分辨「只為了截糧才去」，
    bot_policy._order_hop）。"""
    from . import conquest  # noqa: PLC0415  conquest → territory → rules：在函式裡 import
    from .materials import grain_of  # noqa: PLC0415  只有這裡用得到

    p = state.player
    wanted: set[str] = {p.convoy.to_loc} if p.convoy is not None else set()  # 押著的車一定送到（那一道沒了也照送，T6 審查 I3）
    for o in current(state, content, faction):
        if o.done or o.template in skip:
            continue
        if o.template == "siege":
            wanted |= set(siege_places(content, o.faction, o.front, state.world))
        elif o.template == "defend":
            if conquest.on(content, state.world):  # 領地爭奪：自家被推得最高的那一塊（裁決 11、翻地與爭搶；同記功，FB-565）
                wanted |= set(defend_places(content, state.world, o))
            else:
                wanted |= {loc for loc in content.locations if rules.front_of(content, loc) == o.front}
        elif o.template == "intercept" and o.location is not None:
            wanted |= intercept_spots(content, o.location)
        elif o.template == "escort":
            if p.convoy is None and o.start is not None and grain_of(state, content) >= content.config.convoy_grain:
                wanted.add(o.start)
        elif o.template == "strike" and o.figure is not None:
            fs = figures.state_of(state, content, o.figure)
            if fs.status == "active" and fs.location:
                wanted.add(fs.location)
    return [loc for loc in content.locations if loc in wanted]
