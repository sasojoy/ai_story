"""江湖大勢：大勢門檻、世界事件、分幕主線與主線改寫、虛擬玩家、賽季結局。"""
from __future__ import annotations

import math
import random
import re
from collections.abc import Callable

from . import arena, battle_instance, bounties, calendar, figure_life, figures, flavor, leaderboard, orders, plans, ranks, renown, seal_acts, seats, territory, timetable, wins, yuedan
from .features.feast import rules as feasts  # 宴客的散席（功能包；還沒搬的舊模組可以 import 包，開發規範手冊 3.11）
from . import stances as stance_rules  # 人物心意（減法季批 6）；rules.stances（陣營的態勢）在這個檔裡也叫 stances
from .models import Act, BattleDef, Content, Ending, SimPlayer, SimRumor, Storyline, TimetableEvent
from .rules import (
    add_chronicle, add_rumor, add_world_flags, change_trend, check_condition, recompute_trends,
    decisive_week, ends_early, resolve_trends, season_one, season_one_off, stance_sides, stances, trend_shown, trend_value,
)
from .state import GameState, PlayerState, Rumor, TimelineResult, WorldState
from .flavor import FlavorJob
from .world_state import WorldStateStore, season_length_days

HOUR = 3600
DAY = 86400
EPS_CAL_HOURS = 1e-9  # 找下一個曆時交界時的浮點誤差（以曆時為單位）：剛好停在交界上的時間不能被算成上一個曆時

# 週初的掛鉤：季曆每跨進新的一週（週一 00:00）各跑一次，照週次、在那一刻的大事之前。第四階席次的輪替（seats.rotate）
# 排第一個、T6 的軍令（orders.issue）排第二個。現在的軍令還沒有讀在任的人；之後的軍令（計畫庚：第四階定主攻戰線）要讀，
# 所以席次先排，別把順序換掉
# （跑的時候 hooked_week 已經是剛跨進的那一週）。
WEEK_HOOKS: list[Callable[[GameState, Content, random.Random], list[str]]] = [
    lambda state, content, rng: seats.rotate(state, content, state.world.hooked_week),  # 第四階輪替（正式版丁）：排在發令之前
    lambda state, content, rng: orders.issue(state, content, state.world.hooked_week, rng),
    lambda state, content, rng: bounties.issue(state, content, state.world.hooked_week, rng),  # 懸賞榜：兩個陣營各掛討伐、打探、護送
    lambda state, content, rng: stance_rules.weekly_reset(state, content, state.world.hooked_week),  # 人物心意（減法季批 6）：每週歸零；關著不碰季
]

# 21 天季每天 00:00 的掛鉤（正式季整合設計 7.1、7.2）：季曆每跨進新的一天各跑一次，排在週初掛鉤之後、那一刻的大事之前
# （跑的時候 hooked_day 已經是剛跨進的那一天）。軍令、懸賞在 21 天季改走這一串，週初那一串略過（orders.issue、bounties.issue）
DAY_HOOKS: list[Callable[[GameState, Content, random.Random], list[str]]] = [
    lambda state, content, rng: orders.issue_day(state, content, state.world.hooked_day, rng),
    lambda state, content, rng: bounties.issue_day(state, content, state.world.hooked_day, rng),  # 懸賞榜：每天一批（7.2）
    lambda state, content, rng: stance_rules.daily(state, content),  # 人物心意（減法季批 6）：持重的每天拉下對面的進度；關著什麼都不做
]


def _now_for_battle(now: float | None) -> float:
    """開戰要知道現在的現實時間（集結截止時間從這裡算）。引擎不自己讀電腦時鐘，呼叫端要傳 now。"""
    if now is None:
        raise ValueError("開戰要知道現在的現實時間：呼叫端請傳 now（線上架構設計第四節）")
    return now


def check_thresholds(
    state: GameState, content: Content, world: WorldStateStore | None = None, polish: list[FlavorJob] | None = None,
    now: float | None = None,
) -> list[str]:
    """依序處理大勢門檻、世界事件（各只觸發一次），最後更新主線進度。world 給 _fire() 讀全服共用的潤色句（設計文件 8.2
    第 4 點）；polish 給了的話，還沒潤色過的那一件記一張單子進去，等行動鎖放掉再請模型（見 _fire）。都是選填。"""
    w = state.world
    msgs: list[str] = []
    if w.ended:
        return msgs
    off = season_one_off(content, w, "thresholds")  # 第一季不觸發的 beta 門檻（計畫 T8）
    held, battle_wait = early_end_held(state, content), battle_held(state, content)
    for th in content.scenario.thresholds:
        if th.id in w.fired_thresholds or th.id in off or (th.ends_season and held) or (th.starts_battle and battle_wait):
            continue
        value = trend_value(state, content, th.trend)  # 開關開著時黃巾聲勢是三條戰線的加權
        if not (value >= th.value if th.op == ">=" else value <= th.value):
            continue
        msgs += _fire(
            state, content, th.id, th.text, th.world_flags_add, th.ends_season, th.starts_battle, th.location,
            world, polish, now,
        )
        if w.ended:
            return msgs
    for event in content.scenario.world_events:
        if (event.id in w.fired_thresholds or event.id in season_one_off(content, w, "world_events")
                or not check_condition(event.condition, state)):
            continue
        msgs += _fire(
            state, content, event.id, event.text, event.world_flags_add, event.ends_season, event.starts_battle,
            event.location, world, polish, now,
        )
        if w.ended:
            return msgs
    return msgs + update_storyline(state, content)


def _fire(
    state: GameState, content: Content, fire_id: str, text: str, flags: list[str], ends_season: bool,
    starts_battle: str | None = None, location: str | None = None, world: WorldStateStore | None = None,
    polish: list[FlavorJob] | None = None, now: float | None = None,
) -> list[str]:
    """觸發一件江湖大事。潤色句（S-09，2026-10-31）：鎖內只用全服已經快取好的那一句；還沒有的話這一下先寫固定的原文，
    polish 給了就記一張單子（FlavorJob），由伺服器在行動鎖放掉之後請模型（三段式的 B 段），寫回時（C 段，Game.apply_flavor）
    存進全服快取、把這一則紀錄換成潤色過的那一句。鎖內一個模型都不叫。
    潤色那一句也進天下大事（Joy 2026-10-31 選「也進天下大事」）：快取裡有的這裡跟著原文記一則；還沒有的，潤色回來存進快取的
    那一下記（Game.apply_flavor）。潤色回來之前天下大事只有原文。"""
    state.world.fired_thresholds.add(fire_id)
    add_world_flags(state, flags)
    add_rumor(state, text, location, content=content)
    add_chronicle(state, text)
    shown_text = text
    if world is not None:
        flourish = flavor.clean(world.get_event_flavor(fire_id) or "")  # 舊的快取寫壞了也不再顯示（2026-10-31 自檢以前沒清理）
        if flourish:
            shown_text = f"{text}\n\n{flourish}"
            add_rumor(state, flourish, location, content=content)  # 潤色那一句也進天下大事，全服看得到（Joy 2026-10-31）
        elif polish is not None:
            polish.append(FlavorJob(fire_id, text, location))
    msgs = [f"【江湖大事】{shown_text}"]
    if starts_battle in season_one_off(content, state.world, "battles"):  # 第一季不開 beta 那場決戰（計畫 T8）
        starts_battle = None
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
    polish: list[FlavorJob] | None = None, now: float | None = None,
) -> list[str] | None:
    """管理者手動觸發：照 id 找大勢門檻或世界事件，照自然觸發的方式觸發一次（旗標、傳聞、江湖史、
    開戰、結束賽季都一樣），再更新主線。已經發生過、找不到這個 id、或是第一季不觸發的 beta 門檻，回傳 None。"""
    if (fire_id in state.world.fired_thresholds or fire_id in season_one_off(content, state.world, "thresholds")
            or fire_id in season_one_off(content, state.world, "world_events")):
        return None
    source = next((th for th in content.scenario.thresholds if th.id == fire_id), None)
    if source is None:
        source = next((ev for ev in content.scenario.world_events if ev.id == fire_id), None)
    if source is None:
        return None
    msgs = _fire(
        state, content, source.id, source.text, source.world_flags_add, source.ends_season, source.starts_battle,
        source.location, world, polish, now,
    )
    return msgs if state.world.ended else msgs + update_storyline(state, content)


def current_storyline(state: GameState, content: Content) -> Storyline:
    return next(s for s in content.scenario.storylines if s.id == state.world.storyline)


def current_act(state: GameState, content: Content) -> Act:
    return current_storyline(state, content).acts[state.world.act]


def storyline_off(state: GameState, content: Content) -> bool:
    """目前這條主線是第一季不觸發的 beta 主線（計畫 T8）：幕不推進，「主線與目標」與大地圖都不顯示它。"""
    return state.world.storyline in season_one_off(content, state.world, "storylines")


def update_storyline(state: GameState, content: Content) -> list[str]:
    """還在主線時，檢查是否被支線主線取代；接著一路推進已滿足條件的幕。第一季不觸發的主線（計畫 T8）不推進幕，
    支線照舊可以取代它。"""
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
    if storyline_off(state, content):
        return msgs
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


def sim_active(sim: SimPlayer, state: GameState, content: Content | None = None) -> bool:
    """虛擬玩家的這一條設定現在會不會行動：它需要的隱藏大勢已浮現，而且條件成立。世界模擬與大地圖詳情共用。
    給了 content 才看退場：同名的大勢人物在沒有時刻表的季退場了就不出手（丙 (c)，figures.leader_out）。"""
    if content is not None and figures.leader_out(state, content, sim.name):
        return False
    if sim.requires_revealed and sim.requires_revealed not in state.world.revealed:
        return False
    return check_condition(sim.condition, state)


def sim_tick(state: GameState, content: Content, hours: int, rng: random.Random) -> list[str]:
    """虛擬玩家每小時出手、發傳聞，再檢查一次門檻。第一季的規則開著時虛擬玩家不出手——大勢人物每曆時的推動
    （figures.tick，T4）取代它們；門檻照舊每小時檢查。開關關著時一個字都不變（beta 的 scenario.json 照留）。"""
    msgs: list[str] = []
    sims = [] if season_one(content, state.world) else content.scenario.sim_players
    for _ in range(hours):
        for sim in sims:
            if not sim_active(sim, state, content):  # 退場的龍頭人物整個跳過、不擲亂數（同 bocai_defeated 讓波才停手，丙 (c)）
                continue
            if rng.random() >= sim.actions_per_day / 24:
                continue
            for trend_id, delta in resolve_trends(content, state.world, sim.trend).items():  # 規則沒開時戰線都算黃巾聲勢
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


def season_endings(state: GameState, content: Content) -> list[Ending]:
    """這一季算的結局：第一季（開關開著＋這一季的章）只看標了 season_one 的，beta 季只看沒標的。清單照劇本的順序，
    最後一筆是那一季的保底（content.validate 檢查）。內容沒寫第一季的結局（測試夾具）時，第一季照 beta 那一份。
    天命結局（mandate）不在這裡，由 evaluate_ending 照天命之爭的結果挑（玉璽二）。
    態勢條件寫到這一季沒有的一方的結局不參與（豪強的兩個結局 2026-10-31 連割據一起拿掉），季末只比官軍、黃巾。"""
    on = season_one(content, state.world)
    sides = set(stance_sides(content, state.world))
    chosen = [
        e for e in content.scenario.endings
        if e.season_one == on and not e.mandate
        and (set(e.stance_min) | set(e.stance_max) | ({e.stance_top} if e.stance_top else set())) <= sides
    ]
    return chosen or [e for e in content.scenario.endings if not e.season_one and not e.mandate]


def stance_holds(ending: Ending, standing: dict[str, int]) -> bool:
    """結局的態勢條件（第一季設計 4.4、13.1）：至少、至多，以及「這一方最高」——平手也算最高，誰先成立交給清單順序。"""
    if any(standing[side] < value for side, value in ending.stance_min.items()):
        return False
    if any(standing[side] > value for side, value in ending.stance_max.items()):
        return False
    return ending.stance_top is None or standing[ending.stance_top] >= max(standing.values())


def evaluate_ending(state: GameState, content: Content) -> Ending:
    """照清單順序第一個成立的結局；都不成立就是這一季清單的最後一筆（保底）。第一季另外看三方態勢（rules.stances）。
    天命之季有一軍得天命時是那一軍的天命結局（玉璽二）。"""
    w = state.world
    if w.mandate and w.mandate_result:  # 天命之季、天命之爭有一軍得天命：結局改寫成那一軍的天命結局（玉璽碎片設計 8.3）
        from .seal import mandate_event  # noqa: PLC0415

        event = mandate_event(content)
        won = event.mandate_endings.get(w.mandate_result) if event is not None else None
        ending = next((e for e in content.scenario.endings if e.id == won), None)
        if ending is not None:
            return ending
    endings = season_endings(state, content)
    standing = stances(state, content) if season_one(content, state.world) else {}
    for ending in endings:
        if ending.storyline not in (None, state.world.storyline):
            continue
        if check_condition(ending.condition, state) and (not ending.season_one or stance_holds(ending, standing)):
            return ending
    return endings[-1]


def early_end_held(state: GameState, content: Content) -> bool:
    """規則關著的季，大勢門檻觸發的提前收季（黃巾稱霸）此刻先不收：照第一季決定性勝利同一條（decisive_from_week，FB-165，
    PM 2026-10-12）——季曆第 decisive_from_week 週以前不觸發收季的門檻（不記成觸發過，大勢照推、決戰照開照打），到了那一週
    還在門檻上就照規則收季。季曆照這一季蓋的章（calendar.point），不讀電腦時鐘。第一季一律 False（一個字都不變）。"""
    w = state.world
    return not season_one(content, w) and calendar.point(w.time, content, w).week < content.config.decisive_from_week


def battle_held(state: GameState, content: Content) -> bool:
    """規則關著的季，開決戰的大勢門檻（starts_battle）此刻先不開：季曆第 battle_from_week 週以前（企劃者 2026-10-13「季中，第 5 週起
    才開」，FB-168）不開集結、不記成觸發過，大勢照推，到了那一週還在門檻上就開。寫法同 early_end_held；第一季一律 False（照時刻表）。"""
    w = state.world
    return not season_one(content, w) and calendar.point(w.time, content, w).week < content.config.battle_from_week


NBSP = "\u00a0"


def _glued_time(text: str) -> str:
    """時刻寫成一整塊（FB-167：375 寬斷成「（第11」「天 12:00以前…」）：數字前後跟狀態列一樣空一格（「第 11 天」），
    空格都換成不換行的空格，整塊不會從中間斷開。"""
    return re.sub(r"第(\d+)天", r"第 \1 天", text).replace(" ", NBSP)


def early_end_note(state: GameState, content: Content) -> str:
    """「可能的結局」裡由收季門檻造成的結局後面接的那一句（待 joy 潤）：還在 early_end_held 時寫最早什麼時候才會提前收季。
    時刻整塊不斷行，後面空一格再接「以前…」：要斷行只在那裡斷（FB-167）。"""
    if not early_end_held(state, content):
        return ""
    w = state.world
    when = _glued_time(calendar.stamp_text(calendar.week_start(content.config.decisive_from_week, content, w), content, w))
    return f"（{when} 以前不會提前收季）"


def early_end_flags(content: Content) -> set[str]:
    """收季的大勢門檻會立起的旗標（結局條件看這些旗標的，就是由大勢推到門檻而結束的結局）。"""
    return {flag for th in content.scenario.thresholds if th.ends_season for flag in th.world_flags_add}


def decisive_ending(state: GameState, content: Content) -> Ending | None:
    """決定性勝利（會提前收季的結局，rules.ends_early：態勢門檻只看官軍、黃巾）此刻成立了沒（計畫 T9：季的事每曆時看一次）；
    第一季以外一律 None。提前收季只看戰線（FB-254，企劃者 2026-10-15）。季曆第 decisive_from_week 週（預設 10）以前一律 None：太早收季三場大戲就打不完
    （企劃者 2026-10-05）；到了那一週已經在門檻上的，照規則當下收；天命之季從第 13 週起（等於不提前收，玉璽二）。"""
    if not season_one(content, state.world):
        return None
    if calendar.point(state.world.time, content, state.world).week < decisive_week(state.world, content):
        return None
    standing = stances(state, content)
    return next((e for e in season_endings(state, content) if ends_early(e) and stance_holds(e, standing)), None)


def end_season(
    state: GameState, content: Content, world: WorldStateStore | None = None, rng: random.Random | None = None,
    ending: Ending | None = None,
) -> list[str]:
    """world 給的話，順便算一次榜單（天下武學榜、內功榜，2026-10-14 起加善人、惡人、名人、宗師榜）附在結局後面（設計文件 6.5），
    每張榜的前三名另寫一行江湖史；不傳就是
    原本的純結局文字，選填不影響既有呼叫端或測試。

    第一季：收季之前先把時間到了卻從沒開成的決戰照起點結算（settle_waiting_showdowns，T8 fix round 0），結局看得到
    它們的結果；正在打的那一場不在這裡，照 FB-035 收兵、不算結果。只動 state.world，不碰 store（常在 mutate 裡）。"""
    w = state.world
    if w.ended:
        return []
    msgs = settle_waiting_showdowns(state, content, rng or random.Random(0))
    # 決定性勝利收季時，結局就是觸發收季的那一種：上面照起點判掉的決戰可能把戰況拉回門檻下（T9 審查 M1），
    # 那時再算一次會得到「戰事提前收束。……黃巾坐地」這種自相矛盾的公告
    ending = ending or evaluate_ending(state, content)
    w.ended = True
    w.ending_id = ending.id
    w.ending_title = ending.title
    _close_marks(state, content)  # 減法季批 4：每個地點挑最高的那一條痕跡寫一句江湖史（開關關著什麼都不做）
    if season_one(content, w):
        # 第一季（計畫 T9）：季末公告寫進時間軸（_finale；季中收季的開頭是「戰事提前收束。」），江湖史是季末大事的那一行，
        # 記下最終戰況與各陣營出力前五，給休季的結算畫面讀
        early = w.time < season_end_time(w, content) - calendar.EPS_SECONDS
        ranks.flush_news(state, content, None)  # T5：還沒發的晉升彙整一起發掉
        if w.mandate and w.mandate_result is None:  # 天命之爭沒定下來（沒開成、管理者取消）：天命未定（8.3），江湖史只記這一次
            from .seal import MANDATE_UNSETTLED_END  # noqa: PLC0415

            w.mandate_result = ""
            add_chronicle(state, MANDATE_UNSETTLED_END)
        text = _finale(state, content, ending, early)
        w.ending_text = text or ending.text
        if not any(e.kind == "finale" and e.ending_chronicle for e in content.timetable):
            add_chronicle(state, f"賽季落幕：{ending.title}")  # 內容沒寫季末的江湖史句型（測試夾具）：照舊記一行，江湖史不會沒有結局
        w.final_trends = {
            t.id: trend_value(state, content, t.id) for t in content.scenario.trends if trend_shown(content, w, t.id)
        }
        if world is not None:
            w.final_rankings = leaderboard.contribution_rankings(content, world)
        msgs += ([f"【江湖大事】{text}"] if text else []) + [f"══ 賽季落幕：{ending.title} ══"]
    else:
        w.ending_text = ending.text
        add_chronicle(state, f"賽季落幕：{ending.title}")
        msgs += [f"══ 賽季落幕：{ending.title} ══", ending.text]
    _settle_tiers(state, content, world)
    if arena.on(content):  # 擂台：前三名記名次（休季時同步補獎勵），江湖史一句（擂主）、天下大事一句
        lines = arena.close_season(w, content.config.arena)
        if lines:  # 前三名上天下大事；江湖史只記「本季擂主」（歷屆擂主照它，跨季），擂台榜的前三名由 leaderboard.chronicle_lines 寫
            add_rumor(state, lines[0], content=content, layer="world")
            add_chronicle(state, lines[1])
    if world is not None:
        board = leaderboard.compute_boards(content, world)
        msgs += leaderboard.format_lines(board)
        for line in leaderboard.chronicle_lines(board, world.get_season_number()):  # 江湖史跨季保留：一張榜一行、前三名
            add_chronicle(state, line)
    return msgs


def _settle_tiers(state: GameState, content: Content, world: WorldStateStore | None) -> None:
    """三陣營四勝利（減法季設計 3.3；wins.settle）：收季那一刻每個投靠了陣營的人照名次分四階，存 final_tiers（結局卡、下一季的
    起手資源與稱號讀它），第一、二階寫江湖史。要讀這一季每個角色的帳，給了 store 才算（第一季收季的每一條路都給）；
    開關關著、沒給 store 什麼都不做。"""
    w = state.world
    if world is None or not wins.on(content, w):
        return
    from .characters import CharacterStore, open_characters  # noqa: PLC0415  同 leaderboard：讀角色的那一側

    db = getattr(world, "db", None)
    store = CharacterStore(db) if db is not None else open_characters()
    w.final_tiers = wins.settle(w, content, store.books(world.get_season_number()))
    for line in wins.chronicle_lines(content, w.final_tiers):
        add_chronicle(state, line)


def _close_marks(state: GameState, content: Content) -> None:
    """季末的痕跡江湖史（減法季批 4，marks.close_season；PM 2026-10-25 第 4 件照整合設計 5.2）。在函式裡 import：marks → rules。"""
    from . import marks  # noqa: PLC0415

    marks.close_season(state, content)


def season_end_time(season: WorldState, content: Content) -> float:
    """這一季在世界時鐘上何時收：第一季照排定的季末（schedule["finale"]，管理者可改，計畫 T10；舊季沒排就是季長），
    其他照季長（沒蓋章的舊季 14 天）。"""
    if calendar.season_one_on(season, content) and any(e.kind == "finale" for e in content.timetable):
        return season.schedule.get("finale", timetable.finale_default(content, season))
    return season_length_days(season, content) * DAY


def _finale(state: GameState, content: Content, ending: Ending, early: bool) -> str:
    """季末公告（時刻表結算第 12 週）：開頭（季中就收季時是 early_preface）＋結局句＋退場人物的後話（董卓兵敗）。
    寫進時間軸（key 是結局 id；本週大事面板與 _deliver_big_events 照舊補給每個人）、天下大事傳聞與江湖史一行。
    沒有季末大事、或已經寫過時回空字串。"""
    w = state.world
    event = next((e for e in content.timetable if e.kind == "finale"), None)
    if event is None or event.id in w.timeline:
        return ""
    head = event.early_preface if early and event.early_preface else event.preface
    after = "".join(line for fid, line in event.out_lines.items() if figures.is_out(state, fid))
    text = head + ending.text + after
    w.timeline[event.id] = TimelineResult(key=ending.id, time=w.time, text=text)
    add_rumor(state, text, content=content, layer="world")
    if event.ending_chronicle:
        add_chronicle(state, event.ending_chronicle.replace("{結局}", ending.title))
    return text


def _season_vehicle(content: Content, season: WorldState) -> GameState:
    """sim_tick/check_thresholds/end_season 都要一個完整的 GameState，但推進共用賽季時
    沒有「當下是哪個玩家」這回事——世界事件/門檻的條件照設計只該看大勢/世界旗標，不該看
    某個特定玩家的屬性或旗標（這份共用賽季是所有玩家共同的，依附在任何一個人身上都不對）。
    這裡造一個不會被存檔、純粹借來呼叫既有函式的空殼玩家，確保共用賽季的推進結果不會
    意外因為「剛好是誰觸發的」而有任何差異。"""
    player = PlayerState(name="", location=content.scenario.start_location, stats={}, stamina=0)
    return GameState(player=player, world=season)


def season_events(state: GameState, content: Content, rng: random.Random) -> list[str]:
    """第一季「季的事」裡跟時間點有關的那一半：先補跑還沒跑過的週初掛鉤（每週一次），再照時間順序結算到了的
    大事（季末不在這裡，見 T9），最後把時間到了的決戰記進 showdowns_waiting（T8）——決戰平常不在這裡結算，也不在這裡開：
    這裡常在 mutate_season 裡，開集結是 store 的另一次寫入，要等 mutate 結束（start_pending_battle 開，見
    open_waiting_showdown）。例外（T8 fix round 1，控制者裁定）：這一趟要結算的大事排在一件從沒開成的決戰之後時，
    先照起點把那件決戰結算掉再結算它（settle_waiting_showdowns 的 before）——追趕得到後面那件大事，表示這一整段沒有人在
    （連假人都沒推過時間），真有人在也是沒人參戰、照起點收場；這樣才照週次、決戰帶給之後大事的修正也不會丟掉。
    每曆時的交界（season_hour）與開季那一刻（settle_season_start）都跑它；
    重複呼叫是安全的——掛鉤看 hooked_week、大事看 timeline、決戰看 timeline 與 showdowns_opened，跑過的不再跑。"""
    w = state.world
    msgs: list[str] = []
    week = calendar.point(w.time, content, w).week
    while w.hooked_week < week:
        w.hooked_week += 1
        for hook in WEEK_HOOKS:
            msgs += hook(state, content, rng)
    if calendar.season21_on(w, content):  # 21 天季：每天 00:00 的掛鉤（軍令、懸賞每天一批；只發今天的，跨過的天不補）
        day = calendar.point(w.time, content, w).cal_day
        while w.hooked_day < day:
            w.hooked_day += 1
            for hook in DAY_HOOKS:
                msgs += hook(state, content, rng)
    for event in timetable.due(state, content):
        msgs += settle_waiting_showdowns(state, content, rng, before=event)
        msgs += timetable.resolve(state, content, event, rng)
    _note_due_showdowns(state, content)
    return msgs


def _note_due_showdowns(state: GameState, content: Content) -> None:
    """時間到了、還沒收場、還沒開過、內容有那一筆 BattleDef 的決戰，照時間記進 showdowns_waiting（已經記過的不重複）。
    時刻表上有、內容沒寫那一場的不記（測試夾具）。"""
    w = state.world
    for event in timetable.due_showdowns(state, content):
        if event.id in w.showdowns_waiting or event.id in w.showdowns_opened:
            continue
        if showdown_battle(state, content, event) is not None:
            w.showdowns_waiting.append(event.id)


def settle_waiting_showdowns(
    state: GameState, content: Content, rng: random.Random, before: TimetableEvent | None = None,
) -> list[str]:
    """時間到了卻從沒開成的決戰（還在 showdowns_waiting，時間軸上沒有結果）照沒人參戰的那條路結算——起點照此刻前線的
    戰況算（showdown_start），有人鎖定照鎖定（battle_instance.result_at），再交給 timetable.resolve，照時間先後一件一件來，
    記號清掉、不會再開（Review Focus 1「決戰不能被跳過」、2「開不成或沒人打照鎖定或照起點收場」，控制者 2026-10-04 的裁定）。
    兩個地方用它，同一條路：
    - 收季之前（end_season，before 是 None）：還在等的全部結算（fix round 0）；
    - 季的事要結算 before 這件大事之前（season_events）：只結算排在 before 前面的（照時刻、同一刻照時刻表的順序，fix round 1）。
    正在打（已經開過）的不在這裡：季終照 FB-035 收兵、不算結果。開關關著、或這一季開季時沒開，什麼都不做。
    回傳公告。只動 state.world，不碰 store。"""
    w = state.world
    if not calendar.season_one_on(w, content):
        return []
    _note_due_showdowns(state, content)  # 剛好停在決戰時刻、還沒跑到季的事的那一件也算
    order = {e.id: i for i, e in enumerate(timetable.events(w, content))}  # 天命之季含天命之爭（玉璽二）

    def place(event: TimetableEvent) -> tuple[float, int]:
        return timetable.when(state, content, event), order[event.id]

    msgs: list[str] = []
    for event_id in list(w.showdowns_waiting):
        event = timetable.find(content, event_id)
        event = event if event is not None and event.kind == "showdown" else None
        if event is not None and before is not None and place(event) >= place(before):
            continue  # 排在 before 之後的照舊等著開
        w.showdowns_waiting.remove(event_id)
        if event is None or event_id in w.timeline or event_id in w.showdowns_opened:
            continue
        if event.mandate_only:  # 天命之爭到季末都沒開成：天命未定（8.3），不照起點判
            w.timeline[event_id] = TimelineResult(key=timetable.SKIPPED, time=w.time)
            continue
        definition = showdown_battle(state, content, event)
        if definition is None:
            continue
        lock = w.locks.get(event_id)
        winner, margin = battle_instance.result_at(
            showdown_start(state, content, definition), definition, lock.side if lock is not None else None,
            definition.defender or definition.factions[0].id,
        )
        msgs += timetable.resolve(state, content, event, rng, key=showdown_key(definition, winner, margin))
    return msgs


def showdown_key(definition: BattleDef, winner: str, margin: str) -> str:
    """時刻表決戰交給 timetable.resolve 的結果鍵。分版本的帶上這一筆的版本（實際打的、或照起點判的那一版）：
    不讓 resolve 照收場當下的版本重算——管理者在第 3 週之前開的宛城，收場時第 3 週可能已經換了版本（審查 M-1）。"""
    return f"{definition.version}:{winner}:{margin}" if definition.version else f"{winner}:{margin}"


def showdown_battle(state: GameState, content: Content, event: TimetableEvent) -> BattleDef | None:
    """時刻表上這件決戰此刻要開的那一筆 BattleDef：分版本的照 version_from 那件的結果挑（宛城：第 3 週「成」是甲、
    「不成」是乙；那件還沒結果時當史書那一版）。內容沒有那一筆就是 None。"""
    version = timetable._version(state, event)  # noqa: SLF001  同一個套件
    return next(
        (b for b in content.battles.values() if b.timetable_event == event.id and b.version == version), None,
    )


def showdown_start(state: GameState, content: Content, definition: BattleDef) -> int:
    """時刻表決戰的起點：集結開始這一刻讀 definition.front 的戰況，照 battle_instance.start_from_front 換算（戰鬥系統 5.3）；
    沒寫戰線的照 definition.trend_start。只看公開的戰況，不看伏筆鎖定。"""
    if definition.front is None:
        return definition.trend_start
    return battle_instance.start_from_front(timetable._front_value(state, content, definition.front))  # noqa: SLF001


def _claim_showdown(state: GameState, content: Content, event_id: str) -> tuple[BattleDef, int] | None:
    """（在 mutate_season 裡）把這件決戰記成開過了，回傳要開的那一筆與起點；不該開（季已經結束、已經收場、已經開過、
    內容沒有那一筆）就是 None。不論開不開，都從 showdowns_waiting 拿掉。"""
    w = state.world
    if event_id in w.showdowns_waiting:
        w.showdowns_waiting.remove(event_id)
    if w.ended or event_id in w.timeline or event_id in w.showdowns_opened:
        return None
    event = next((e for e in timetable.events(w, content) if e.id == event_id and e.kind == "showdown"), None)  # 一般季開不了天命之爭（玉璽二）
    definition = showdown_battle(state, content, event) if event is not None else None
    if definition is None:
        return None
    w.showdowns_opened[event_id] = definition.id
    w.showdown_opened_at[event_id] = w.time  # 開的那一刻：輿圖歸週、判斷到了沒照它（FB-563）
    from . import chapters  # noqa: PLC0415

    # 章回主線：做成那一回的份量挪開打的起點（以官軍為正向，夾在 0～100）；沒人做成是 0，一個字都不變
    start = showdown_start(state, content, definition) + chapters.showdown_edge(w, content, event_id)
    return definition, max(0, min(100, start))


def open_showdown(world: WorldStateStore, content: Content, event_id: str, now: float) -> list[str]:
    """開時刻表上這件決戰的集結（管理者手動開也走這裡）：照版本挑那一筆、照前線戰況定起點，季上記下開過了
    （一場決戰只開一次：中途換季、季終收兵、跨過好幾週都不重開）。另一場還在打、季已經結束、已經收場或開過，
    什麼都不做、回傳空串列。呼叫端不在任何 mutate 裡（開戰是 store 的寫入）。"""
    return _open_claimed(world, content, now, lambda state: _claim_showdown(state, content, event_id))


def open_waiting_showdown(world: WorldStateStore, content: Content, now: float) -> list[str]:
    """時間到了、還在等的決戰（showdowns_waiting，照時間先後）開最早的那一件。另一場還在打就留著記號等它收場
    （Game 收場那一下會再呼叫這裡，所以是「收場立刻開」）；一次只開一件，其餘照順序等下一次。
    已經收場、已經開過、或內容沒有那一筆的記號順手清掉。呼叫端不在任何 mutate 裡。"""
    season = world.get_season()
    if season.ended or not season.showdowns_waiting:
        return []

    def _first_waiting(state: GameState) -> tuple[BattleDef, int] | None:
        while state.world.showdowns_waiting:
            picked = _claim_showdown(state, content, state.world.showdowns_waiting[0])  # 不論開不開都會拿掉這一筆
            if picked is not None:
                return picked
        return None

    return _open_claimed(world, content, now, _first_waiting)


def _open_claimed(
    world: WorldStateStore, content: Content, now: float, claim: Callable[[GameState], tuple[BattleDef, int] | None],
) -> list[str]:
    """另一場還在打就什麼都不做（記號留著）；否則在一次 mutate_season 裡用 claim 記下要開哪一場，mutate 結束後才開戰
    （開戰是 store 的另一次寫入，mutate 不能巢狀）。"""
    current = world.get_battle()
    if current is not None and current.phase != "ended":
        return []
    claimed: list[tuple[BattleDef, int]] = []

    def _apply(season: WorldState) -> None:
        picked = claim(_season_vehicle(content, season))
        if picked is not None:
            claimed.append(picked)

    world.mutate_season(_apply)
    if not claimed:
        return []
    definition, start = claimed[0]
    msgs = _open_battle(world, definition, now, trend_start=start)
    if msgs:  # 真的開成了：玉璽碎片的現世與璽動在集結這一刻擲（玉璽碎片設計 3.2、4.1）
        from . import seal  # noqa: PLC0415  seal → world_state：在函式裡 import，同這個模組其他延後 import

        from . import works  # noqa: PLC0415  同上

        msgs += _front_muster(world, content, definition, start)  # 起點照哪一條戰線（領地爭奪開著的季；排在屯糧、天命之爭的偏移之前）
        msgs += works.on_muster(world, content, definition)  # 屯糧練兵：兩軍屯的量換成起點的偏移（排在天命之爭的偏移之前，兩者疊加）
        msgs += seal.on_muster(world, content, definition, now)
        from . import generals  # noqa: PLC0415  同上

        msgs += generals.on_muster(world, content, definition)  # 龍頭上陣：派那條戰線上的大勢人物上陣
    return msgs


def _front_muster(world: WorldStateStore, content: Content, definition: BattleDef, start: int) -> list[str]:
    """時刻表決戰剛開集結（_open_claimed，不在任何 mutate 裡）：領地爭奪開著、寫了戰線時，把起點照的那條線上誰佔幾處快照進這一場
    （BattleInstance.front_note）、天下大事一句（企劃者 2026-10-22：不另加主場偏移，補一句說明）。其餘什麼都不寫（只讀一次季）。"""
    from . import conquest  # noqa: PLC0415  同 advance_world_state 的延後 import

    note = conquest.front_note(world.get_season(), content, definition, start)
    if note is None:
        return []

    def _snap(b: battle_instance.BattleInstance) -> None:
        if b.battle_id == definition.id and b.phase == "muster":
            b.front_note = note

    world.mutate_battle(_snap)
    line = conquest.front_rumor(content, definition, note)
    world.mutate_season(lambda s: s.rumors.append(Rumor(time=s.time, text=line, layer="world")))
    return [f"🗺️ 【天下大事】{line}"]


def season_hour(state: GameState, content: Content, rng: random.Random) -> list[str]:
    """第一季「季的事」，每跨過一個曆時跑一次（advance_world_state 照曆時切段呼叫；開關關著或舊季不跑）：
    先跑每曆時才有的事，再跑 season_events（週初掛鉤、到了的大事）。
    每曆時的 tick 一律放在 season_events 之前：T4 的 figures.tick——開季那一刻只跑
    season_events（settle_season_start），不跑這一段，才不會多算一次人物推動（T1 的割據 2026-10-31 拿掉）。"""
    msgs: list[str] = []
    ranks.flush_news(state, content, calendar.point(state.world.time, content, state.world).cal_day)  # T5：前一天的晉升彙整
    figures.tick(state, content, 1)  # T4：大勢人物每曆時累積一次推動（取代每小時的虛擬玩家）
    return msgs + season_events(state, content, rng)


def _open_greenwood(vehicle: GameState, content: Content) -> None:
    """名聲 5.1：正邪武學開著時立「綠林開寨」（綠林山寨的 unlock_flag）。新的一季在蓋章時就立了（world_state.stamp_season）；
    這裡補上線那一刻正在跑的季（第一次推進時）。已經立了就不動；lessons 關著不立：山寨不畫、去不了。"""
    if renown.on(content, "lessons") and renown.GREENWOOD_FLAG not in vehicle.world.flags:
        add_world_flags(vehicle, [renown.GREENWOOD_FLAG])


def settle_season_start(season: WorldState, content: Content, rng: random.Random) -> list[str]:
    """開季那一刻（世界秒 0）結算第 1 週週一 00:00 的事（FB-040）：只跑 season_events（週初掛鉤＋到了的大事），
    不跑每曆時的事。不補這一下，要等到第一個曆時交界（約 1 分 47 秒）第一件大事才出現，本週大事那時還是空的。
    開關關著、這一季開季時沒開（舊季）、或已經跑過（hooked_week 不是 0：週初掛鉤從沒跑過才是還沒開季結算）時不跑季的事，
    所以重複呼叫也安全。呼叫端在開季之後、不在任何 mutate 裡（見 Game._settle_season_start）。
    規則關著的季只掛第 1 週的懸賞（bounties.tick；不碰 hooked_week，同一週只掛一次）：管理者開季後第一眼看到的榜不是空的。"""
    if not calendar.season_one_on(season, content):
        return [] if season.ended else bounties.tick(_season_vehicle(content, season), content)
    if season.hooked_week != 0 or season.ended:
        return []
    return season_events(_season_vehicle(content, season), content, rng)


def _season_due(season: WorldState, content: Content) -> bool:
    """收季的時間到了：第一季照排定的季末（容一點浮點誤差：排定的時刻不一定落在曆時交界上），其他照季長（跟以前一字不差）。"""
    if calendar.season_one_on(season, content):
        return season.time >= season_end_time(season, content) - calendar.EPS_SECONDS
    return season.time >= season_length_days(season, content) * DAY


def _to_next_cal_hour(time: float, cal_hour: float) -> float:
    """從 time 到下一個曆時交界還有幾個世界秒。"""
    return (math.floor(time / cal_hour + EPS_CAL_HOURS) + 1) * cal_hour - time


def advance_world_state(
    season: WorldState, content: Content, seconds: float, rng: random.Random, world: WorldStateStore | None = None,
) -> list[str]:
    """把一份 WorldState（不管是共用賽季的副本，還是——理論上——任何 WorldState）原地
    往前推進 seconds 秒：逐小時推進、累積滿一小時才跑一次虛擬玩家模擬（避免長時間快轉時
    事件/門檻判斷太粗），照搬原本 engine.py::_advance_step 的世界部分。純函式性質（除了
    原地修改傳入的 season），不寫儲存（world 給了只讀名冊與榜單）——存不存、怎麼存是呼叫端的事：Game.advance() 直接對
    self.state.world 呼叫這個函式再自己存回共用儲存（跟 choose()/travel() 同一套模式）；
    被動的現實時間追趕（world_state.py::catch_up_season）則透過下面的 advance_season
    包在 mutate_season 裡再呼叫。"""
    vehicle = _season_vehicle(content, season)
    if not season.ended:
        _open_greenwood(vehicle, content)  # 名聲 5.1：上線那一刻正在跑的季，第一次推進時補立
    recompute_trends(season, content)  # 開關開著時，內容改版前開的一季也照三條戰線重算存下來的黃巾聲勢（條件讀它）
    territory.update(season, content)  # 舊存檔、中途上線的第一次在這裡算，不發天下大事（出陣探索與地盤設計第六節）
    msgs: list[str] = []
    remaining = seconds
    # 第一季（開關開著、這一季也蓋了章）：另外在每個曆時的交界停一下跑季的事；跨過好幾件大事也逐件照時間來
    cal_hour = calendar.cal_hour_seconds(content, season) if calendar.season_one_on(season, content) else None
    # 有沒打完的奪璽單挑時，那一個曆時先不提前收季（玉璽碎片設計 5.11，最多約 13 分鐘）：一次推進只查一次；在 advance_season 的
    # mutate_season 裡也查得到（讀只是讀，交易裡的快照直接用同一條連線）。沒傳 store（純函式的呼叫）照舊
    # 主機關掉碎片（Config.seal.enabled）時單挑推不動了，也就不擋（不然關著的那段時間每一季都收不了季）
    seal_open = (cal_hour is not None and world is not None and content.config.seal.enabled and bool(content.seal)
                 and world.seal_duel_open())
    while remaining > 0 and not season.ended:
        step = min(remaining, HOUR)
        # 玉璽碎片改版第 2 批：引將期滿那一刻另切一段，剛好在那一刻回原處（沒有還沒期滿的引將時一步都不變）
        if (pull_end := seal_acts.next_end(season)) is not None and season.time + calendar.EPS_SECONDS < pull_end < season.time + step:
            step = pull_end - season.time
        crossed = False
        # 曆時交界照季曆的整點（21 天季在 10:30 開季時，第一個交界在 11:00，calendar.next_hour_mark）
        if cal_hour is not None and (to_mark := calendar.next_hour_mark(season.time, content, season)) <= step + calendar.EPS_SECONDS:
            step, crossed = to_mark, True
        remaining -= step
        season.time += step
        season.sim_accum += step
        hours = int(season.sim_accum // HOUR)
        if hours:
            season.sim_accum -= hours * HOUR
            msgs += sim_tick(vehicle, content, hours, rng)
        if cal_hour is None and not season.ended:
            msgs += bounties.tick(vehicle, content)  # 第一季規則關著的季：季曆跨進新的一週就掛這一週的懸賞（只掛這一週，懸賞榜設計第三節）
        if not season.ended:
            # 甲 (b)：被打下來的聲威慢慢回。沒有時刻表的季，加上 21 天的第一季（正式季第 6 批）；recover 自己照 figures.upkept 擋掉
            # 週末的第一季。以前只在上面那一支（第一季規則關著）叫，21 天季永遠走不到（FB-350）
            figures.recover(vehicle, content, step * calendar.cal_scale(content, season) / HOUR)
            msgs += figures.revive(vehicle, content)  # 被挑戰打退的人物過幾個季曆天回來（PM 2026-10-16，兩種季都有）
            msgs += seal_acts.tick(vehicle, content)  # 引將期滿回原處（玉璽碎片改版第 2 批）：排在人物走動之前（期滿的那一輪他就能走）
            figure_life.tick(vehicle, content)  # 人物的每日行事（大勢人物擴充第一批）：走動、募兵、襲擾，只寫傳聞
            feasts.settle(vehicle, content)  # 時間到了的宴散席（第三批）：席間最佳那一句上天下大事
            plans.tick(vehicle, content, season_end_time(season, content))  # 世界活起來：人物照行程動身、盤算公告與結算
            yuedan.tick(vehicle, content, world)  # 月旦評（第三批）：跨進新的一週評六個人；給了 store 才評（要掃角色）
        if crossed and not season.ended:
            msgs += season_hour(vehicle, content, rng)
            decisive = None if season.ended or seal_open else decisive_ending(vehicle, content)
            if decisive is not None:  # 決定性勝利：當曆時收季，結局就是它（計畫 T9）
                msgs += end_season(vehicle, content, world, rng, ending=decisive)
        if not season.ended and _season_due(season, content):
            msgs += end_season(vehicle, content, world, rng)
        if not season.ended and season.conquest is not None:
            from . import conquest, siege  # noqa: PLC0415  siege → conquest_day → timetable：延後 import

            siege.mark_due(season, content)  # 領地爭奪第二批：到了開集結的攻城記成 waiting（start_pending_battle 開）
            conquest.decay(season, content)  # 翻地與爭搶：跨過季曆日交界，前一整天沒人推的塊往回（輿圖簡化設計 4.1）
    return msgs


# ── 賽季時鐘暫停後繼續（線上架構設計第四節、8.3；企劃者 2026-10-06 定 B3）──────────


def pause_skip(season: WorldState, content: Content, span: float) -> float:
    """賽季時鐘停了 span 個現實秒，繼續時賽季要跳過幾個現實秒（WorldStateStore.resume_clock 把對時點往後挪這麼多）。
    第一季（有季曆、有排好的決戰）照整個曆時往下取整：曆時的交界在現實時間上不動，排好的決戰才能分秒不差地照原本的現實時間開
    （季的事只在曆時交界把時間到了的決戰記下來）；不足一個曆時的零頭算進賽季（週末那季最多現實 1 分 47 秒）。
    其他（beta 那一季）照 span 一秒不差。21 天季也是整段（季曆另外對回現實的星期，realign_paused_calendar）。"""
    if not calendar.season_one_on(season, content) or calendar.season21_on(season, content):
        return span
    grid = calendar.cal_hour_seconds(content, season) / content.config.time_scale
    return math.floor(span / grid + EPS_CAL_HOURS) * grid


RESUME_NUDGE = 0.002  # 世界秒：21 天季繼續時賽季多走這一點點，暫停那一刻與繼續那一刻寫下的時刻才分得出用哪一個偏移（FB-332）


def realign_paused_calendar(season: WorldState, content: Content, skipped: float, until: float | None = None) -> None:
    """21 天季（PM 2026-10-19：季曆就是現實的週，畫面上的週六 20:00 就是真的週六晚上）：暫停的這一段整段不算進賽季（pause_skip），
    季曆的偏移加回同樣長，季曆對回現實的星期；季末照原本的現實日期收場（排定的世界秒往前挪同樣長，不往後延）。決戰照
    keep_showdowns_on_time 挪；暫停期間該發生的一般大事在繼續那一刻依序結算（resume_season_clock）。其他季什麼都不做。
    只改傳進來的 season（WorldStateStore.resume_clock 在它的 mutate 裡、keep_showdowns_on_time 之前呼叫）。
    until（FB-332）是舊的偏移用到哪一個世界秒為止（暫停那一刻與繼續那一刻之間，見 RESUME_NUDGE）：記進 cal_offset_history，
    以前寫下的時刻照舊的偏移換成季曆，不跟著往後挪。沒給（舊的呼叫）照季現在的時間記。"""
    if not calendar.season21_on(season, content):
        return
    shift = skipped * content.config.time_scale
    season.cal_offset_history.append((season.time if until is None else until, season.cal_offset))
    season.cal_offset += shift * calendar.cal_scale(content, season)
    if "finale" in season.schedule:
        season.schedule["finale"] -= shift


def keep_showdowns_on_time(season: WorldState, content: Content, skipped: float, season_now: float) -> None:
    """賽季時鐘繼續之後，排好、還沒開的決戰照原本的現實時間開（企劃者 2026-10-06 定 B3）：賽季跳過了 skipped 個現實秒，
    這些決戰的排定（世界秒）就往前挪 skipped × time_scale——季末與一般的大事不挪，跟著往後延。挪到剛好碰上一件還沒結算的
    一般大事時再往後挪一個曆時（timetable.clear_of_events）；也不挪到原本排在它前面、還沒結算的一般大事之前，最早排在那件之後
    一個曆時（B13：時刻表的先後不能亂，例如宛城要等第 3 週的結果定版本；停機很久才會碰到）。原本的時間落在暫停裡的（挪完已經不晚於 season_now，也就是繼續
    那一刻的季時間）改排在 season_now、記進 showdowns_waiting：呼叫端緊接著補算、再呼叫 start_pending_battle 就開集結（B11，
    見 resume_season_clock）；
    另一場還在打就排隊等它收場（照現在的規則）。已經開過、已經收場、已經在排隊的不動。開關關著或舊季什麼都不做。
    只改傳進來的 season（WorldStateStore.resume_clock 在它的 mutate 裡呼叫），不碰 store。"""
    if not calendar.season_one_on(season, content):
        return
    vehicle = _season_vehicle(content, season)
    shift = skipped * content.config.time_scale
    if season.conquest is not None:  # 領地爭奪第二批：排好、還沒開集結的攻城也照原本的現實時間開（Review Focus 5）
        for slot in season.conquest.schedule:
            if slot.status in ("planned", "waiting"):
                slot.at -= shift
                slot.muster_at -= shift
    cal_hour = calendar.cal_hour_seconds(content, season)
    regular = [e for e in timetable._pending(vehicle, content) if e.kind not in timetable.NOT_BY_SEASON_HOUR]  # noqa: SLF001
    for event in timetable.events(season, content):  # 天命之季含天命之爭（玉璽二）
        if event.kind != "showdown" or event.id in season.timeline or event.id in season.showdowns_opened:
            continue
        if event.id in season.showdowns_waiting:
            continue
        was = timetable.when(vehicle, content, event)
        at = was - shift
        # 21 天季的一般大事已經跟著季曆一起挪過了（realign_paused_calendar，排在這之前）：先後不會亂，照挪過的時刻比
        ref = at if calendar.season21_on(season, content) else was
        earlier = [timetable.when(vehicle, content, e) for e in regular if timetable.when(vehicle, content, e) < ref]
        if earlier and at <= max(earlier) + calendar.EPS_SECONDS:  # 不跑到原本排在它前面、還沒結算的一般大事之前（B13）
            at = max(earlier) + cal_hour
        if at <= season_now + calendar.EPS_SECONDS:
            season.schedule[event.id] = season_now
            if showdown_battle(vehicle, content, event) is not None:
                season.showdowns_waiting.append(event.id)
            continue
        season.schedule[event.id], _ = timetable.clear_of_events(vehicle, content, at)


def start_pending_battle(world: WorldStateStore, content: Content, now: float) -> list[str]:
    """背景推進跨過開戰門檻時只在賽季上記下要開哪一場（見 _fire），時間到了的時刻表決戰也只記號（見 season_events）；
    呼叫端的 mutate_season 結束之後呼叫這裡（mutate 不能巢狀），真的開戰並清掉記號。沒有待開的戰鬥就什麼都不寫。"""
    season = world.get_season()
    msgs = _start_threshold_battle(world, content, now) if season.pending_battle is not None else []
    if season.showdowns_waiting:
        msgs += open_waiting_showdown(world, content, now)
    if season.conquest is not None and any(slot.status == "waiting" for slot in season.conquest.schedule):
        from . import siege  # noqa: PLC0415

        msgs += siege.open_waiting(world, content, now)  # 領地爭奪第二批：時間到了的攻城開集結（跟決戰同時打）
    return msgs


# 繼續時那一行怎麼說「這一段」（填進 resume_line 的 {skip}）：跳過的長度第一季照整個曆時往下取整（pause_skip，B12），
# 停得比一個曆時短就什麼都沒扣，不能再說「不算進賽季」。待 S1／joy 潤
RESUME_SKIP_ALL = "這一段不算進賽季，季末往後延一樣長"
RESUME_SKIP_PART = "其中 {skipped}不算進賽季，季末往後延一樣長；不足一個季曆鐘頭的零頭（{rest}）照算進賽季"
RESUME_SKIP_NONE = "停不到一個季曆鐘頭（現實約 {grid}），不另外扣：這一段照算進賽季，季末不另外往後延"
# 照現實天的季（PM 2026-10-19）：季曆對回現實的星期（realign_paused_calendar）。待 joy 潤
# 照季寫季長與對回什麼（FB-501：7 天濃縮季寫「7 天的季：季曆對回現實的日子」；calendar.week_word 的 realign），21 天季一個字都不變
RESUME_SKIP_REAL_LINE = "{days:g} 天的季：季曆對回現實的{unit}，暫停期間的大事在這一刻一起發生，季末照原本的日期"
RESUME_SKIP_REAL = RESUME_SKIP_REAL_LINE.format(days=21, unit="星期")  # 21 天季那一句（以前寫死的就是它）


def _span_text(seconds: float) -> str:
    """現實秒數寫成給人看的長度：56 秒、3 分 45 秒、1 小時 12 分。"""
    total = int(round(seconds))
    if total < 60:
        return f"{total} 秒"
    if total < 3600:
        minutes, rest = divmod(total, 60)
        return f"{minutes} 分" + (f" {rest} 秒" if rest else "")
    hours, rest = divmod(total, 3600)
    return f"{hours} 小時" + (f" {rest // 60} 分" if rest // 60 else "")


def realign_line(season: WorldState, content: Content) -> str:
    """照現實天的季繼續時那一句（RESUME_SKIP_REAL_LINE）：照這一季蓋章的季長與 calendar.week_word("realign")（FB-501）。"""
    return RESUME_SKIP_REAL_LINE.format(days=season_length_days(season, content), unit=calendar.week_word("realign", content, season))


def resume_skip_text(season: WorldState, content: Content, span: float) -> str:
    """停了 span 個現實秒，繼續時賽季到底扣了多少，照實說（RESUME_SKIP_*）：全扣（beta 那一季、或剛好整數個曆時）、
    扣了整個曆時的部分零頭照算、什麼都沒扣（不足一個曆時）。21 天季照實說季曆對回現實的星期（RESUME_SKIP_REAL）。"""
    if calendar.season21_on(season, content):
        return realign_line(season, content)
    if not calendar.season_one_on(season, content):
        return RESUME_SKIP_ALL
    grid = calendar.cal_hour_seconds(content, season) / content.config.time_scale
    skipped = pause_skip(season, content, span)
    rest = span - skipped
    if skipped <= 0:
        return RESUME_SKIP_NONE.format(grid=_span_text(grid))
    if rest < 1:  # 差不到一秒的零頭是浮點誤差
        return RESUME_SKIP_ALL
    return RESUME_SKIP_PART.format(skipped=_span_text(skipped), rest=_span_text(rest))


def resume_season_clock(
    world: WorldStateStore, content: Content, now: float, rng: random.Random, resume_line: str,
) -> list[str] | None:
    """讓賽季時鐘繼續走，每一條「繼續」的路都走這一個（管理者的按鈕 Game.admin_resume_clock、主機端 scripts/season_clock.py、
    假人模擬）：三步一定照這個順序，不要各自再寫一遍——
    1. resume_clock：停的這一段不算進賽季；排好、還沒開的決戰往前挪，原本的時間落在暫停裡的記進排隊；
    2. catch_up_season：暫停前還沒補算的那一段（主機端直接暫停、或沒開排程時停在補算之前）裡面的一般大事先結算，不然排在這一刻的
       決戰會在它前面的大事還沒結算時就開成（時刻表的先後不能亂）；補算有推進時，排隊的決戰就在它的結尾開集結；
    3. start_pending_battle：補算沒有推進時（繼續的那一刻剛好落在曆時交界上、沒有零頭）由它開那一場。
    回傳 [resume_line（{minutes} 換成停了幾分鐘、{skip} 換成這一段實際扣了多少，見 resume_skip_text）] ＋ 補算的訊息 ＋
    開集結的訊息：集結號角那一行可能出在 2 或 3，兩邊都要接上，少一邊那一句就丟了。賽季時鐘沒有暫停回 None。
    呼叫端要拿著行動鎖（一筆交易做完：管理者的按鈕在 server.act 裡、主機端腳本與模擬自己拿），now 是現實時間。"""
    span = world.resume_clock(content, now)
    if span is None:
        return None
    line = resume_line.format(minutes=int(span // 60), skip=resume_skip_text(world.get_season(), content, span))
    caught = list(world.catch_up_season(content, now, rng))
    if calendar.season21_on(world.get_season(), content):  # 21 天季：季曆對回來了，暫停期間該發生的一般大事這一刻依序結算
        settled: list[str] = []

        def _settle(season: WorldState) -> None:
            if not season.ended:
                settled.extend(season_events(_season_vehicle(content, season), content, rng))

        world.mutate_season(_settle)
        caught += settled
    return [line] + caught + start_pending_battle(world, content, now)


def _start_threshold_battle(world: WorldStateStore, content: Content, now: float) -> list[str]:
    """開門檻記下的那一場（WorldState.pending_battle），並清掉記號。"""
    taken: dict[str, str | None] = {"id": None}
    ended = {"value": False}

    def _apply(season: WorldState) -> None:
        taken["id"], season.pending_battle = season.pending_battle, None
        ended["value"] = season.ended

    world.mutate_season(_apply)
    battle_id = taken["id"]
    if battle_id is None or battle_id not in content.battles or ended["value"]:  # 季已經結束：不開戰
        return []
    if battle_id in season_one_off(content, world.get_season(), "battles"):  # 開關打開前記下的 beta 那場：第一季不開
        return []
    return _open_battle(world, content.battles[battle_id], now)


def _open_battle(world: WorldStateStore, definition: BattleDef, now: float, trend_start: int | None = None) -> list[str]:
    """開一場全服決戰並廣播集結。已經有一場在集結或開打（例如管理者先開了戰，聲勢之後才跨過開戰門檻），
    就不另開、也不再廣播（試玩回饋 FB-015）。trend_start 是時刻表決戰照戰況算的起點（見 showdown_start）。"""
    current = world.get_battle()
    if current is not None and current.phase != "ended":
        return []
    world.start_battle(definition, now=now, trend_start=trend_start)
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
