"""江湖大勢：大勢門檻、世界事件、分幕主線與主線改寫、虛擬玩家、賽季結局。"""
from __future__ import annotations

import math
import random
from collections.abc import Callable

from . import calendar, flavor, leaderboard, timetable
from .models import Act, BattleDef, Content, Ending, SimPlayer, SimRumor, Storyline
from .ollama_client import OllamaClient
from .rules import add_chronicle, add_rumor, add_world_flags, change_trend, check_condition
from .state import GameState, PlayerState, WorldState
from .world_state import WorldStateStore, season_length_days

HOUR = 3600
DAY = 86400
EPS_CAL_HOURS = 1e-9  # 找下一個曆時交界時的浮點誤差（以曆時為單位）：剛好停在交界上的時間不能被算成上一個曆時

# 週初的掛鉤：季曆每跨進新的一週（週一 00:00）各跑一次，照週次、在那一刻的大事之前。T6 的 orders.issue 掛這裡。
WEEK_HOOKS: list[Callable[[GameState, Content, random.Random], list[str]]] = []


def _now_for_battle(now: float | None) -> float:
    """開戰要知道現在的現實時間（集結截止時間從這裡算）。引擎不自己讀電腦時鐘，呼叫端要傳 now。"""
    if now is None:
        raise ValueError("開戰要知道現在的現實時間：呼叫端請傳 now（線上架構設計第四節）")
    return now


def check_thresholds(
    state: GameState, content: Content, world: WorldStateStore | None = None, client: OllamaClient | None = None,
    now: float | None = None,
) -> list[str]:
    """依序處理大勢門檻、世界事件（各只觸發一次），最後更新主線進度。world/client 給
    _fire() 用來潤色江湖大事的傳聞文字（設計文件 8.2 第 4 點）；不傳就是原本的純文字，
    兩者都是選填，不影響既有呼叫端或測試。"""
    w = state.world
    msgs: list[str] = []
    if w.ended:
        return msgs
    for th in content.scenario.thresholds:
        if th.id in w.fired_thresholds:
            continue
        value = w.trends.get(th.trend, 0)
        if not (value >= th.value if th.op == ">=" else value <= th.value):
            continue
        msgs += _fire(
            state, content, th.id, th.text, th.world_flags_add, th.ends_season, th.starts_battle, th.location,
            world, client, now,
        )
        if w.ended:
            return msgs
    for event in content.scenario.world_events:
        if event.id in w.fired_thresholds or not check_condition(event.condition, state):
            continue
        msgs += _fire(
            state, content, event.id, event.text, event.world_flags_add, event.ends_season, event.starts_battle,
            event.location, world, client, now,
        )
        if w.ended:
            return msgs
    return msgs + update_storyline(state, content)


def _fire(
    state: GameState, content: Content, fire_id: str, text: str, flags: list[str], ends_season: bool,
    starts_battle: str | None = None, location: str | None = None, world: WorldStateStore | None = None,
    client: OllamaClient | None = None, now: float | None = None,
) -> list[str]:
    state.world.fired_thresholds.add(fire_id)
    add_world_flags(state, flags)
    add_rumor(state, text, location, content=content)
    add_chronicle(state, text)
    shown_text = text
    if world is not None:
        flourish = world.get_event_flavor(fire_id)
        if not flourish and client is not None:
            flourish = flavor.polish_world_event(client, text)
            if flourish:
                world.set_event_flavor(fire_id, flourish)
                flourish = world.get_event_flavor(fire_id)  # 可能被別的玩家搶先寫入，讀回真正共用的那一份
        if flourish:
            shown_text = f"{text}\n\n{flourish}"
    msgs = [f"【江湖大事】{shown_text}"]
    if starts_battle and starts_battle in content.battles:
        if world is not None:
            msgs += _open_battle(world, content.battles[starts_battle], _now_for_battle(now))
        else:  # 背景推進（sim_tick）：先記下來，mutate 結束後由 start_pending_battle 開戰
            state.world.pending_battle = starts_battle
    if ends_season:
        msgs += end_season(state, content, world)
    return msgs


def fire_by_id(
    state: GameState, content: Content, fire_id: str, world: WorldStateStore | None = None,
    client: OllamaClient | None = None, now: float | None = None,
) -> list[str] | None:
    """管理者手動觸發：照 id 找大勢門檻或世界事件，照自然觸發的方式觸發一次（旗標、傳聞、江湖史、
    開戰、結束賽季都一樣），再更新主線。已經發生過、或找不到這個 id，回傳 None。"""
    if fire_id in state.world.fired_thresholds:
        return None
    source = next((th for th in content.scenario.thresholds if th.id == fire_id), None)
    if source is None:
        source = next((ev for ev in content.scenario.world_events if ev.id == fire_id), None)
    if source is None:
        return None
    msgs = _fire(
        state, content, source.id, source.text, source.world_flags_add, source.ends_season, source.starts_battle,
        source.location, world, client, now,
    )
    return msgs if state.world.ended else msgs + update_storyline(state, content)


def current_storyline(state: GameState, content: Content) -> Storyline:
    return next(s for s in content.scenario.storylines if s.id == state.world.storyline)


def current_act(state: GameState, content: Content) -> Act:
    return current_storyline(state, content).acts[state.world.act]


def update_storyline(state: GameState, content: Content) -> list[str]:
    """還在主線時，檢查是否被支線主線取代；接著一路推進已滿足條件的幕。"""
    w = state.world
    msgs: list[str] = []
    main = content.scenario.storylines[0]
    if w.storyline == main.id:
        for branch in content.scenario.storylines[1:]:
            if branch.replaces_when is not None and check_condition(branch.replaces_when, state):
                w.storyline, w.act = branch.id, 0
                text = f"主線改寫——「{branch.name}」。{branch.intro}"
                add_rumor(state, text, content=content)
                add_chronicle(state, text)
                msgs.append(f"【主線改寫】{branch.name}：{branch.intro}")
                break
    line = current_storyline(state, content)
    while w.act < len(line.acts) - 1:
        act = line.acts[w.act]
        if act.advance_when is None or not check_condition(act.advance_when, state):
            break
        w.act += 1
        w.act_reached = max(w.act_reached, w.act)
        nxt = line.acts[w.act]
        msgs.append(f"【主線】第{w.act + 1}幕「{nxt.title}」：{nxt.text}")
        add_chronicle(state, f"{line.name}・第{w.act + 1}幕「{nxt.title}」")
    return msgs


def sim_active(sim: SimPlayer, state: GameState) -> bool:
    """虛擬玩家的這一條設定現在會不會行動：它需要的隱藏大勢已浮現，而且條件成立。世界模擬與大地圖詳情共用。"""
    if sim.requires_revealed and sim.requires_revealed not in state.world.revealed:
        return False
    return check_condition(sim.condition, state)


def sim_tick(state: GameState, content: Content, hours: int, rng: random.Random) -> list[str]:
    msgs: list[str] = []
    for _ in range(hours):
        for sim in content.scenario.sim_players:
            if not sim_active(sim, state):
                continue
            if rng.random() >= sim.actions_per_day / 24:
                continue
            for trend_id, delta in sim.trend.items():
                change_trend(state, content, trend_id, delta, reveal=False)
            if sim.rumors and rng.random() < sim.rumor_chance:
                text, where = _rumor_place(sim, rng.choice(sim.rumors))  # 和以前一樣只抽一次亂數
                text = text.format(name=sim.name)
                add_rumor(state, text, where, content=content, layer="local")
                msgs.append(f"【江湖傳聞】{text}")
        msgs += check_thresholds(state, content)
        if state.world.ended:
            break
    return msgs


def _rumor_place(sim: SimPlayer, rumor: str | SimRumor) -> tuple[str, str | None]:
    """虛擬玩家一則傳聞的（文字, 發生地）：寫明地點的記在那裡，否則記在第一個常出沒處。不用亂數。"""
    if isinstance(rumor, SimRumor):
        return rumor.text, rumor.location
    return rumor, sim.haunts[0] if sim.haunts else None


def evaluate_ending(state: GameState, content: Content) -> Ending:
    for ending in content.scenario.endings:
        if ending.storyline not in (None, state.world.storyline):
            continue
        if check_condition(ending.condition, state):
            return ending
    return content.scenario.endings[-1]


def end_season(state: GameState, content: Content, world: WorldStateStore | None = None) -> list[str]:
    """world 給的話，順便算一次天下武學榜／內功榜附在結局後面（設計文件 6.5）；不傳就是
    原本的純結局文字，選填不影響既有呼叫端或測試。"""
    w = state.world
    if w.ended:
        return []
    ending = evaluate_ending(state, content)
    w.ended = True
    w.ending_title = ending.title
    w.ending_text = ending.text
    add_chronicle(state, f"賽季落幕：{ending.title}")
    msgs = [f"══ 賽季落幕：{ending.title} ══", ending.text]
    if world is not None:
        board = leaderboard.compute_leaderboard(content, world)
        msgs += leaderboard.format_lines(board)
    return msgs


def _season_vehicle(content: Content, season: WorldState) -> GameState:
    """sim_tick/check_thresholds/end_season 都要一個完整的 GameState，但推進共用賽季時
    沒有「當下是哪個玩家」這回事——世界事件/門檻的條件照設計只該看大勢/世界旗標，不該看
    某個特定玩家的屬性或旗標（這份共用賽季是所有玩家共同的，依附在任何一個人身上都不對）。
    這裡造一個不會被存檔、純粹借來呼叫既有函式的空殼玩家，確保共用賽季的推進結果不會
    意外因為「剛好是誰觸發的」而有任何差異。"""
    player = PlayerState(name="", location=content.scenario.start_location, stats={}, stamina=0)
    return GameState(player=player, world=season)


def season_hour(state: GameState, content: Content, rng: random.Random) -> list[str]:
    """第一季「季的事」，每跨過一個曆時跑一次（advance_world_state 照曆時切段呼叫；開關關著或舊季不跑）：
    先補跑還沒跑過的週初掛鉤（每週一次），再照時間順序結算到了的大事（決戰與季末不在這裡，見 T8、T9）。
    T1 的 geju_tick、T4 的 figures.tick 之後也掛在這裡（週初掛鉤之後、大事之前），每曆時一次。"""
    w = state.world
    msgs: list[str] = []
    week = calendar.point(w.time, content, w).week
    while w.hooked_week < week:
        w.hooked_week += 1
        for hook in WEEK_HOOKS:
            msgs += hook(state, content, rng)
    for event in timetable.due(state, content):
        msgs += timetable.resolve(state, content, event, rng)
    return msgs


def _to_next_cal_hour(time: float, cal_hour: float) -> float:
    """從 time 到下一個曆時交界還有幾個世界秒。"""
    return (math.floor(time / cal_hour + EPS_CAL_HOURS) + 1) * cal_hour - time


def advance_world_state(
    season: WorldState, content: Content, seconds: float, rng: random.Random, world: WorldStateStore | None = None,
) -> list[str]:
    """把一份 WorldState（不管是共用賽季的副本，還是——理論上——任何 WorldState）原地
    往前推進 seconds 秒：逐小時推進、累積滿一小時才跑一次虛擬玩家模擬（避免長時間快轉時
    事件/門檻判斷太粗），照搬原本 engine.py::_advance_step 的世界部分。純函式性質（除了
    原地修改傳入的 season），不碰儲存——存不存、怎麼存是呼叫端的事：Game.advance() 直接對
    self.state.world 呼叫這個函式再自己存回共用儲存（跟 choose()/travel() 同一套模式）；
    被動的現實時間追趕（world_state.py::catch_up_season）則透過下面的 advance_season
    包在 mutate_season 裡再呼叫。"""
    vehicle = _season_vehicle(content, season)
    msgs: list[str] = []
    remaining = seconds
    # 第一季（開關開著、這一季也蓋了章）：另外在每個曆時的交界停一下跑季的事；跨過好幾件大事也逐件照時間來
    cal_hour = calendar.cal_hour_seconds(content, season) if calendar.season_one_on(season, content) else None
    while remaining > 0 and not season.ended:
        step = min(remaining, HOUR)
        crossed = False
        if cal_hour is not None and (to_mark := _to_next_cal_hour(season.time, cal_hour)) <= step + calendar.EPS_SECONDS:
            step, crossed = to_mark, True
        remaining -= step
        season.time += step
        season.sim_accum += step
        hours = int(season.sim_accum // HOUR)
        if hours:
            season.sim_accum -= hours * HOUR
            msgs += sim_tick(vehicle, content, hours, rng)
        if crossed and not season.ended:
            msgs += season_hour(vehicle, content, rng)
        if not season.ended and season.time >= season_length_days(season, content) * DAY:
            msgs += end_season(vehicle, content, world)
    return msgs


def start_pending_battle(world: WorldStateStore, content: Content, now: float) -> list[str]:
    """背景推進跨過開戰門檻時只在賽季上記下要開哪一場（見 _fire）；呼叫端的 mutate_season
    結束之後呼叫這裡（mutate 不能巢狀），真的開戰並清掉記號。沒有待開的戰鬥就什麼都不寫。"""
    if world.get_season().pending_battle is None:
        return []
    taken: dict[str, str | None] = {"id": None}
    ended = {"value": False}

    def _apply(season: WorldState) -> None:
        taken["id"], season.pending_battle = season.pending_battle, None
        ended["value"] = season.ended

    world.mutate_season(_apply)
    battle_id = taken["id"]
    if battle_id is None or battle_id not in content.battles or ended["value"]:  # 季已經結束：不開戰
        return []
    return _open_battle(world, content.battles[battle_id], now)


def _open_battle(world: WorldStateStore, definition: BattleDef, now: float) -> list[str]:
    """開一場全服決戰並廣播集結。已經有一場在集結或開打（例如管理者先開了戰，聲勢之後才跨過開戰門檻），
    就不另開、也不再廣播（試玩回饋 FB-015）。"""
    current = world.get_battle()
    if current is not None and current.phase != "ended":
        return []
    world.start_battle(definition, now=now)
    return [f"🛡️ 【全服戰報】{definition.name}的集結號角已經吹響！"]


def advance_season(
    world: WorldStateStore, content: Content, seconds: float, rng: random.Random, now: float,
) -> list[str]:
    """跟 advance_world_state 做一樣的事，差別是這裡直接對共用賽季本身讀出、修改、
    寫回（mutate_season）——給被動的現實時間追趕用（world_state.py::catch_up_season），那條路徑沒有
    哪個玩家的 self.state.world 可以操作，只能直接對著共用儲存動手。mutate_season 結束之後才開
    推進途中跨過門檻的戰鬥（見 start_pending_battle）。"""
    msgs: list[str] = []
    world.mutate_season(lambda season: msgs.extend(advance_world_state(season, content, seconds, rng, world)))
    return msgs + start_pending_battle(world, content, now)
