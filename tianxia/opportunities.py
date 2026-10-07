"""機緣（機緣文件；正式版乙一）：升第 3、4 階除了貢獻門檻，還要完成一種機緣。

這一份管：誰做得了（自己陣營；第 4 階要已經是第 3 階）、情誼型的對話話題、累積型的計數與交付、天時地利型的
時段與檢定、線索。完成只寫一句個人敘事，不發任何傳聞。需求量照伏筆的分檔換算（foreshadow.need）。
只有第一季的規則開著才有（rules.season_one）。

乙二加三種第 4 階的：拼圖型（問將領拿一策、或在地點付錢／過檢定拿一樣東西，湊齊交給人）、推理型（由本季天機
決定嫌疑人、聽特徵、最後指認）、集體密謀型（發起、響應、各處、結算）。第 4 階的新句子是初稿，待 joy 潤。"""
from __future__ import annotations

import hashlib
import math
import random
from typing import NamedTuple

from . import calendar, figures, foreshadow, push, ranks, timetable
from .journal import fragment_line
from .models import Content, OppDef, OppPiece, Rank2Action
from .rules import GEJU, add_rumor, change_trend, front_of, roll_check, season_one
from .state import GameState, PlayerState, Plot, WorldState

DONE = "（機緣「{name}」完成。）"
NOT_NOW = "（此刻無法這麼做。）"
PLOT_IDLE = "{name}成了，可惜這一回你沒辦成哪一處，沒有你的份。"  # 只響應、沒出力的人（企劃者 2026-10-06）；新寫，待 joy 潤
# 天時地利型的窗口：機緣文件寫的曆時是底（整季夠長的季就是這些），windows() 才依季的壓縮放寬
DAWN_FROM = calendar.NIGHT_UNTIL  # 黎明從夜裡結束的那一刻起；放寬時夜裡往前長、黎明往後長，兩個窗口以這一刻為界背對背
DAWN_BASE_HOURS = 2  # 卯時：季曆 05:00～06:59（機緣文件 3.1 B）
NIGHT_BASE_HOURS = (calendar.NIGHT_UNTIL - calendar.NIGHT_FROM) % 24  # 子時到寅時 23:00～04:59＝6 個曆時
WINDOW_CAP_HOURS = 12  # 夜裡、黎明各最長半天，兩個窗口加起來剛好一整天：再怎麼壓縮也不會重疊
EPS_HOURS = 1e-9  # 換算曆時的浮點誤差：剛好整點的（例如 7 天的季卯時剛好 10 現實分鐘）不要進位成多一個曆時


class Windows(NamedTuple):
    """這一季機緣的時間窗口（windows()）。夜裡從 night_from 點整起、跨午夜到 NIGHT_UNTIL 前一刻；
    黎明從 dawn_from（＝NIGHT_UNTIL）點整起 dawn_hours 個曆時；戰後的地是決戰結算之後 showdown_seconds 個世界秒內；
    集體密謀（乙二）發起之後 plot_seconds 個世界秒內要湊齊。"""

    night_from: int
    night_hours: int
    dawn_from: int
    dawn_hours: int
    showdown_seconds: float
    plot_seconds: float


def windows(content: Content, season: WorldState | None = None) -> Windows:
    """機緣的時段窗口，依這一季的壓縮放寬（企劃者 2026-10-06「照比例調整」）。

    問題：窗口的曆時是寫死的，季壓得越緊（cal_scale 越大），同樣的曆時占的現實時間越短——週末設定
    cal_scale 33.6，一個曆時現實 1.8 分鐘，卯時兩個曆時只有 3.6 分鐘，錯過了要等一個曆日（現實 42.9 分鐘）。

    算法：每個窗口至少要開 Config.opp_window_min_minutes 個現實分鐘（預設 10），換成曆時就是
    需要＝分鐘數 × 60 × cal_scale ÷ 3600；窗口的曆時＝max(原本的曆時, ceil(需要))。
    所以放寬的曆時數跟 cal_scale 成正比（壓縮越緊、放得越寬，現實時間維持在目標），而原本就夠長的窗口
    係數是 1、一個字不動：整季 14 天（cal_scale 6）卯時現實 20 分鐘、夜裡 60 分鐘，不放寬，曆時跟機緣文件一樣；
    正式版整季更長，也不動。戰後的地不是整點的窗口，直接取 max(opp_showdown_days 個曆日, 目標分鐘) 的世界秒；
    集體密謀的期限（乙二）一樣取 max(plot_days 個曆日, 目標分鐘)。乙二的拼圖、推理沒有窗口，只有「失敗了當天不能再試」
    （以曆日算，不是窗口，這裡不動）。

    不重疊：黎明從夜裡結束的那一刻（05:00）往後長（週末設定卯時長到辰時、巳時），夜裡從同一刻往前長到傍晚，
    絕不長進黎明；兩個各最多 WINDOW_CAP_HOURS（半天），壓縮到極端時也只是剛好接滿一天。
    夜裡結束的 05:00 不動，失敗後「下一個夜裡再來」的回數鍵（_window_key）因此不變。
    只管機緣：calendar.is_night（伏筆最後一步、事件的夜裡條件）永遠是 23:00～04:59。"""
    cfg = content.config
    scale = calendar.cal_scale(content, season)
    need = cfg.opp_window_min_minutes * calendar.MINUTE * scale / calendar.HOUR  # 目標現實分鐘 → 曆時
    wanted = math.ceil(need - EPS_HOURS)
    night = min(WINDOW_CAP_HOURS, max(NIGHT_BASE_HOURS, wanted))
    dawn = min(WINDOW_CAP_HOURS, max(DAWN_BASE_HOURS, wanted))
    floor = cfg.opp_window_min_minutes * calendar.MINUTE
    return Windows(
        night_from=(calendar.NIGHT_UNTIL - night) % 24, night_hours=night,
        dawn_from=DAWN_FROM, dawn_hours=dawn,
        showdown_seconds=max(cfg.opp_showdown_days * calendar.DAY / scale, floor),
        plot_seconds=max(cfg.plot_days * calendar.DAY / scale, floor),
    )


def active(state: GameState, content: Content) -> bool:
    return season_one(content, state.world) and bool(content.opportunities)


def open_ones(state: GameState, content: Content) -> list[OppDef]:
    """這個人此刻做得了、還沒完成的機緣：自己陣營的；第 3 階的投靠了就行，第 4 階的要已經是第 3 階（機緣文件第一節）。"""
    p = state.player
    if not active(state, content) or p.faction is None:
        return []
    rank = ranks.rank_of(state)
    return [
        o for o in content.opportunities
        if o.faction == p.faction and o.id not in p.opp_done and (o.rank == 3 or rank >= 3)
    ]


def done_for_rank(state: GameState, content: Content, rank: int) -> bool:
    """這一季替目前陣營完成過第 rank 階的任一種機緣（同一階完成任一種就夠，機緣文件第一節）；計畫丙的召見讀它。"""
    p = state.player
    return any(o.rank == rank and o.faction == p.faction and o.id in p.opp_done for o in content.opportunities)


def clear(p: PlayerState) -> None:
    """叛投時清掉機緣的進度（機緣文件第一節：換季、叛投清掉）。換季不用叫：角色每季重來。
    rank2_days 不清：那是每人每曆日第 2 階行動的限次，不屬於哪個陣營的進度，叛投不能拿來重置它。
    乙二：拼圖拿到的東西與靠山一起清；opp_settled 不清（結算過的集體密謀不會因為叛投再結算一次）。
    opp_clues（聽過的線索）不清（企劃者裁決 E5.2，2026-10-07）：跟伏筆片段、符文殘片一樣是「知道的事」，個人線索照舊列著；
    舊陣營的機緣照樣做不了——做得了的一律經過 open_ones（只看自己陣營的），線索的鍵是機緣 id，也不會擋住新陣營的線索。"""
    p.opp_done, p.opp_counts, p.opp_items, p.opp_fronts, p.opp_tried = [], {}, {}, {}, {}
    p.opp_pieces, p.patron = {}, None


def _complete(state: GameState, opp: OppDef) -> list[str]:
    """記下完成、收掉這一種的計數與物品；回傳那一行「（機緣「…」完成。）」。不發傳聞。"""
    p = state.player
    p.opp_done.append(opp.id)
    p.opp_counts.pop(opp.id, None)
    p.opp_items.pop(opp.id, None)
    p.opp_fronts.pop(opp.id, None)
    p.opp_pieces.pop(opp.id, None)
    return [DONE.format(name=opp.name)]


# ── 情誼型：對話的話題 ─────────────────────────────────


def _topics(state: GameState, content: Content, companion_id: str) -> list[OppDef]:
    return [
        o for o in open_ones(state, content)
        if o.kind == "bond" and o.bond.character == companion_id
        and state.player.affinities.get(companion_id, 0) >= foreshadow.need(content, o.bond.affinity)
    ]


def talk_options(state: GameState, content: Content, companion_id: str) -> list:
    """對話選單上的話題（標籤是話題）：自己陣營的、還沒完成、在跟的就是這位才有。
    情誼型 talk:opp:<機緣>（情誼夠）；拼圖型 talk:opp:<機緣>:<東西 key>（此刻要問的正是這位、情誼夠、還沒拿）。"""
    from .engine import Option  # noqa: PLC0415  延後 import：engine → opportunities

    opts = [Option(id=f"talk:opp:{o.id}", label=o.bond.topic) for o in _topics(state, content, companion_id)]
    opts += [Option(id=f"talk:opp:{o.id}:{piece.key}", label=piece.topic)
             for o, piece in _ask_pieces(state, content, companion_id)]
    return opts


def hear_topic(state: GameState, content: Content, companion_id: str, arg: str) -> list[str]:
    """按了話題（arg 是「機緣」或「機緣:東西」）：情誼型說完就完成；拼圖型拿到那一樣東西（照說話的人挑那一句，
    不完成機緣，湊齊了去交）。不經模型、不扣體力、不算對話輪數。選項不在了就回空串列。"""
    opp_id, _, key = arg.partition(":")
    if not key:
        for o in _topics(state, content, companion_id):
            if o.id == opp_id:
                return [o.bond.text] + _complete(state, o)
        return []
    fid = figures.of_character(content, companion_id)
    for o, piece in _ask_pieces(state, content, companion_id):
        if o.id == opp_id and piece.key == key:
            _give_piece(state, o, key)
            return [piece.lines.get(fid, piece.lines.get("*", ""))]
    return []


# ── 拼圖型 ─────────────────────────────────


def _speaker_of(state: GameState, content: Content, o: OppDef, piece: OppPiece) -> str | None:
    """這一樣東西此刻要問誰（大勢人物 id）：原本那位在那條戰線上就是他，不在（重創、重挫、退場、下獄）就是那時
    己方的主將；都沒有是 None。"""
    if figures.on_front(state, piece.figure, piece.front) and figures.state_of(state, content, piece.figure).status == "active":
        return piece.figure
    return figures.commander(state, content, piece.front, o.faction)


def _has_piece(state: GameState, o: OppDef, key: str) -> bool:
    return key in state.player.opp_pieces.get(o.id, [])


def _give_piece(state: GameState, o: OppDef, key: str) -> None:
    state.player.opp_pieces.setdefault(o.id, []).append(key)


def _ask_pieces(state: GameState, content: Content, companion_id: str) -> list[tuple[OppDef, OppPiece]]:
    """對話時問得到的東西：拼圖型、how 是 ask、還沒拿、此刻要問的正是這位（對話人物 → 大勢人物 id）、情誼夠。"""
    fid = figures.of_character(content, companion_id)
    out = []
    for o in open_ones(state, content):
        if o.kind != "puzzle":
            continue
        for piece in o.puzzle.pieces:
            if piece.how != "ask" or _has_piece(state, o, piece.key):
                continue
            if fid is not None and _speaker_of(state, content, o, piece) == fid \
                    and state.player.affinities.get(companion_id, 0) >= foreshadow.need(content, piece.affinity):
                out.append((o, piece))
    return out


def _present_here(state: GameState, content: Content, o: OppDef, loc_id: str) -> str | None:
    """湊齊了、此刻在交得了的地方：回傳 {人物}；交不了是 None。官軍：固定地點，figure 在場寫他、不在寫 stand_in。
    豪強：照靠山（還沒定的話三位任一位），在那位的地點。"""
    pr = o.puzzle.present
    if not all(_has_piece(state, o, piece.key) for piece in o.puzzle.pieces):
        return None
    if pr.at is not None:
        if loc_id != pr.at:
            return None
        return figures.name_of(content, pr.figure) if pr.figure in figures.present_at(state, content, loc_id) else pr.stand_in
    for patron in _patrons_of(state, o):
        if patron.at == loc_id:
            return content.characters[patron.character].name
    return None


def _patrons_of(state: GameState, o: OppDef) -> list:
    """會收這份東西的靠山：玩家選定了的那一位；還沒選（計畫丙升第 3 階時才寫入）就是三位任一位。"""
    patrons = o.puzzle.present.patrons
    return [patrons[state.player.patron]] if state.player.patron in patrons else list(patrons.values())


# ── 第 2 階行動（設計 5.5）─────────────────────────────────


def rank2_action(state: GameState, content: Content) -> Rank2Action | None:
    """自己陣營的第 2 階行動（orders.json 的 rank2）；第一季規則沒開、散人、還沒到第 2 階、陣營沒有這種行動時是 None。"""
    p = state.player
    if not season_one(content, state.world) or p.faction is None or ranks.rank_of(state) < 2:
        return None
    return content.orders.rank2.get(p.faction)


def _today(state: GameState, content: Content) -> int:
    return calendar.point(state.world.time, content, state.world).cal_day


def rank2_left(state: GameState, content: Content) -> int:
    """今天還能做幾次（每曆日 rank2_daily 次，不論成敗）。"""
    return content.config.rank2_daily - state.player.rank2_days.get(_today(state, content), 0)


def count_rank2(state: GameState, content: Content) -> None:
    """記一次第 2 階行動（只留今天那一筆）。"""
    today = _today(state, content)
    state.player.rank2_days = {today: state.player.rank2_days.get(today, 0) + 1}


# ── 累積型 ─────────────────────────────────


def _commander_name(state: GameState, content: Content, front: str, side: str, generic: str) -> str:
    fid = figures.commander(state, content, front, side)
    return figures.name_of(content, fid) if fid is not None else generic


def after_success(state: GameState, content: Content, source: str, loc_id: str, rng: random.Random) -> list[str]:
    """第 2 階行動成功（source="rank2"）或守勢行動之後（"duty"）：累積型記一次（duty 的流民先擲 chance）；
    湊滿換算後的次數那一刻拿到東西、記下要送去哪條戰線（所在地點的戰線）。已經拿著東西的不再記。"""
    msgs: list[str] = []
    front = front_of(content, loc_id)
    place = content.locations[loc_id].name
    for o in open_ones(state, content):
        a = o.accumulate
        if o.kind != "accumulate" or a.source != source or o.id in state.player.opp_items:
            continue
        if a.chance < 1 and rng.random() >= a.chance:
            continue
        p = state.player
        p.opp_counts[o.id] = p.opp_counts.get(o.id, 0) + 1
        if a.tick:
            msgs.append(a.tick.replace("{地點}", place))
        n = foreshadow.need(content, a.count)
        if p.opp_counts[o.id] >= n:
            chief = _commander_name(state, content, front, "huang", "黃巾渠帥") if front else "黃巾渠帥"
            msgs.append(a.milestone.replace("{n}", str(n)).replace("{渠帥}", chief))
            p.opp_items[o.id] = a.item
            if front is not None:
                p.opp_fronts[o.id] = front
    return msgs


def _deliver_here(state: GameState, content: Content, o: OppDef, loc_id: str) -> str | None:
    """東西拿在手上、此刻在交得了的地方時，回傳 {主將} 要填的名字；交不了是 None。
    front_commander：那條戰線己方此刻的主將所在；沒有主將時是那條戰線上的己方投靠點，名字寫「官軍的主將」。
    nearest_base：任一個己方投靠點（不用最近，到了就能交）。"""
    p = state.player
    if o.id not in p.opp_items:
        return None
    side = content.scenario.faction(o.faction)
    deliver = o.accumulate.deliver if o.kind == "accumulate" else "front_commander"
    if deliver == "nearest_base":
        return side.name if loc_id in side.join_at else None
    front = p.opp_fronts.get(o.id)
    fid = figures.commander(state, content, front, o.faction) if front else None
    if fid is not None:
        return figures.name_of(content, fid) if figures.state_of(state, content, fid).location == loc_id else None
    on_front = [b for b in side.join_at if front_of(content, b) == front]
    return f"{side.name}的主將" if loc_id in on_front else None


# ── 天時地利型 ─────────────────────────────────


def _window_key(state: GameState, content: Content, when: str) -> int | None:
    """這一刻屬於哪一回（同一回失敗了不能再試）：夜裡是那一夜開始的曆日（跨過午夜到 NIGHT_UNTIL 前算前一天的夜），
    黎明是當天；不在時段裡回 None。窗口是依這一季放寬過的（windows）：夜裡的起點最早 17:00、一定在 NIGHT_UNTIL 之後，
    黎明從 NIGHT_UNTIL 起、最晚到 16:59，所以回數照樣是「那一夜開始的曆日」與「當天」。
    決戰之後沒有回數（時限內可以一直試），回 0。"""
    w = state.world
    at = calendar.point(w.time, content, w)
    win = windows(content, w)
    if when == "night":
        if at.hour >= win.night_from:
            return at.cal_day
        return at.cal_day - 1 if at.hour < calendar.NIGHT_UNTIL else None
    if when == "dawn":
        return at.cal_day if win.dawn_from <= at.hour < win.dawn_from + win.dawn_hours else None
    return 0


def _host_here(state: GameState, content: Content, o: OppDef, loc_id: str) -> str | None:
    """黎明的主持：照順序第一位在場（在他的地點）的人物；他的地點就是你此刻所在才算。回傳人物 id 或 None。"""
    for h in o.timing.hosts:
        if h.figure in figures.present_at(state, content, h.at):
            return h.figure if h.at == loc_id else None
    return None


def _showdown_here(state: GameState, content: Content, loc_id: str) -> bool:
    """戰後的地：有一場全服決戰在 opp_showdown_days 個曆日內（現實不到 opp_window_min_minutes 分鐘的話放寬到那麼久，
    windows）結算，這裡在那件大事的戰線上、帶野外一類的標籤。記成跳過（沒有打過）的、沒有戰線的決戰不算。"""
    loc = content.locations[loc_id]
    if not set(loc.tags) & set(content.config.opp_wild_tags):
        return False
    w = state.world
    span = windows(content, w).showdown_seconds
    for e in content.timetable:
        done = w.timeline.get(e.id)
        if e.kind == "showdown" and e.front is not None and done is not None and done.key != timetable.SKIPPED \
                and 0 <= w.time - done.time <= span and front_of(content, loc_id) == e.front:
            return True
    return False


def _timing_here(state: GameState, content: Content, o: OppDef, loc_id: str) -> tuple[bool, str] | None:
    """天時地利型此刻在這裡做得了嗎：回傳（這一回還能試、{人物} 要填的名字），不在時段或地點是 None。
    拿著東西還沒送的（密信）不再出選項。"""
    t = o.timing
    if o.id in state.player.opp_items:
        return None
    if t.when == "night":
        if loc_id not in t.at:
            return None
        who = ""
    elif t.when == "dawn":
        host = _host_here(state, content, o, loc_id)
        if host is None:
            return None
        who = figures.name_of(content, host)
    else:
        if not _showdown_here(state, content, loc_id):
            return None
        who = ""
    key = _window_key(state, content, t.when)
    if key is None:
        return None
    return (t.when == "after_showdown" or state.player.opp_tried.get(o.id) != key), who


def hear_clues(state: GameState, content: Content, region: str | None, rng: random.Random, world=None) -> list[str]:
    """花體力的行動之後（Game._hear_after_stamina）：天時地利型的線索，加上推理型「本季內鬼的特徵」片段（只透露那個
    人的特徵，在各自的大區），在它的大區（沒寫就哪裡都行）以伏筆片段的機率聽到一則（foreshadow.fragment_chance），
    每則只聽一次。world 是讀本季天機用的（None 時天機當 0，同伏筆）。寫進江湖紀錄（「你聽到一件事：…」），不發傳聞。"""
    if region is None:
        return []
    pool: list[tuple[str, str]] = []  # （記在 opp_clues 的鍵、那一句）
    for o in open_ones(state, content):
        if o.kind == "timing" and o.id not in state.player.opp_clues \
                and (not o.timing.clue_regions or region in o.timing.clue_regions):
            pool.append((o.id, o.timing.clue))
        if o.kind == "deduce":
            traits = next(s.traits for s in o.deduce.suspects if s.id == culprit(content, o, _world_tianji(world)))
            for t in o.deduce.traits:
                key = f"{o.id}:{t.key}"
                if t.key in traits and t.region == region and key not in state.player.opp_clues:
                    pool.append((key, t.text))
    if not pool or rng.random() >= foreshadow.fragment_chance(content):
        return []
    key, text = rng.choice(pool)
    state.player.opp_clues.append(key)
    return [fragment_line(text)]


def heard_clues(state: GameState, content: Content) -> list[str]:
    """聽過的機緣線索（見聞頁的「個人線索」，FB-086）：天時地利型的線索加上推理型內鬼的特徵片段，照聽到的先後（opp_clues 的順序），
    字跟當時寫進江湖紀錄的那一句一樣（hear_clues 的 text，只是不帶「你聽到一件事：」，跟伏筆片段 foreshadow.heard_texts 的寫法一致）。
    只有這個人自己聽過的（opp_clues 是他的存檔）；機緣完成了、時段過了照舊留著（跟伏筆完成之後片段還在一樣，不標記）；
    叛投之後舊陣營的線索也留著（clear 不清 opp_clues，企劃者裁決 E5.2），只是那些機緣做不了了。內容裡已經沒有的機緣或特徵（改版拿掉）略過。
    機緣沒在跑（開關關著、沒有機緣）時是空的。"""
    if not active(state, content):
        return []
    texts: dict[str, str] = {}
    for o in content.opportunities:
        if o.kind == "timing":
            texts[o.id] = o.timing.clue
        elif o.kind == "deduce":
            texts.update({f"{o.id}:{t.key}": t.text for t in o.deduce.traits})
    return [texts[key] for key in state.player.opp_clues if key in texts]


# ── 推理型 ─────────────────────────────────


def culprit(content: Content, o: OppDef, world_tianji: int) -> str:
    """本季的內鬼（嫌疑人 id）：天機決定（伏筆文件 2.9），換季（天機 +1）就可能換人。"""
    return foreshadow.tianji_answer(world_tianji, o.deduce.tianji)


def _world_tianji(world) -> int:
    return world.read().tianji if world is not None else 0


def _asker_here(state: GameState, content: Content, o: OppDef, loc_id: str) -> str | None:
    """指認時誰問：照順序第一位在場的人（張梁 → 張寶 → 張角），你要在他的地點。回傳人物 id 或 None。"""
    for h in o.deduce.askers:
        if h.figure in figures.present_at(state, content, h.at):
            return h.figure if h.at == loc_id else None
    return None


# ── 集體密謀型（機緣文件 1.1）─────────────────────────────────
# 陣營軍情、響應的選項一律寫真名（企劃者 2026-10-06：只有地方傳聞匿名）；每一場只有自己陣營的人看得到、做得了。


def _petition_here(state: GameState, content: Content, loc_id: str) -> str | None:
    """在這裡請命得了嗎：第 3 階以上，這裡有己方人物（官軍、黃巾是在場的己方大勢人物；豪強是 petition.characters 裡
    talk_at 在這裡的人）。回傳畫面上的動作名（請命、請示渠帥、聽家主吩咐），不行是 None。"""
    p = state.player
    petition = content.orders.petition.get(p.faction or "")
    if petition is None or ranks.rank_of(state) < 3:
        return None
    if petition.characters:
        here = any(content.characters[cid].talk_at == loc_id for cid in petition.characters)
    else:
        here = any(content.figures[fid].faction == p.faction for fid in figures.present_at(state, content, loc_id))
    return petition.label if here else None


def _plot_def(content: Content, plot: Plot) -> OppDef | None:
    """這場密謀的機緣；內容改版把它拿掉了（存檔的季裡還留著）就是 None，各處當成沒這場密謀。"""
    return next((o for o in content.opportunities if o.id == plot.opp and o.kind == "plot"), None)


def _live(state: GameState, plot: Plot) -> bool:
    """還在進行：開著、沒過期、而且這一季還沒落幕（休季什麼都不能再加）。"""
    return plot.status == "open" and state.world.time <= plot.deadline and not state.world.ended


def _need_parts(o: OppDef) -> int:
    return o.plot.need_parts or len(o.plot.parts)


def _headcount(content: Content, o: OppDef) -> int:
    return min(foreshadow.need(content, o.plot.headcount), _need_parts(o))


def _missing(content: Content, o: OppDef, plot: Plot) -> str:
    """陣營軍情「還缺……」：每一處都要的寫處名；湊幾處就好的（甲子）寫「N 處」。"""
    left = [x for x in o.plot.parts if x.key not in plot.parts]
    if o.plot.need_parts is None:
        return "、".join(x.name for x in left)
    return f"{_need_parts(o) - len(plot.parts)} 處"


def _cap_per_person(content: Content, o: OppDef) -> int:
    """一個人最多做幾處：要的處數 ÷ 換算後的人數、無條件進位，所以出力的人數真的湊得到那麼多（週末設定人數 1，一個人全做）。"""
    return math.ceil(_need_parts(o) / _headcount(content, o))


def _done_by(plot: Plot, name: str) -> int:
    return sum(1 for who in plot.parts.values() if who == name)


def _mark(state: GameState, content: Content, o: OppDef, plot: Plot, key: str) -> None:
    """記下這一處；湊齊處數、出力的人數也夠了，就完成（status done）。"""
    plot.parts[key] = state.player.name
    if len(plot.parts) >= _need_parts(o) and len(set(plot.parts.values())) >= _headcount(content, o):
        plot.status = "done"


def _my_plots(state: GameState) -> list[Plot]:
    """自己還在做的密謀：響應過、還開著、而且是自己現在這個陣營的（換了陣營的人打贏不能替舊陣營的密謀記一處）。"""
    p = state.player
    return [x for x in state.world.plots if p.name in x.members and x.faction == p.faction and _live(state, x)]


PLOT_ID_SPACE = 10**8


def plot_id(faction: str, opp_id: str, leader: str, time: float) -> int:
    """密謀的編號：選項 id 會送到前端，所以不用全服連號（連號的空缺會洩漏別的陣營發起過幾場、大約什麼時候）；
    由這一場自己的陣營、機緣、發起人與發起時刻（遊戲時間，引擎不讀電腦時鐘）的雜湊決定，不看別的密謀。"""
    digest = hashlib.sha256(f"{faction}|{opp_id}|{leader}|{time:.3f}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % PLOT_ID_SPACE


def _part_here(state: GameState, content: Content, o: OppDef, plot: Plot, loc_id: str):
    """check 類：這個地點是哪一處（還沒人做的）；不是就 None。"""
    return next((x for x in o.plot.parts if x.at == loc_id and x.key not in plot.parts), None)


def on_win(state: GameState, content: Content, front: str | None, squad_faction: str | None) -> list[str]:
    """遊歷打贏一場（Game._squad_encounter）：win 類的密謀，這條戰線那一處還沒人做、對手是敵方（不是自己陣營、
    也不是沒有陣營的）時記上。一個人的上限照 _cap_per_person。打贏一場只算進一場密謀（企劃者 2026-10-06）：記進
    第一場還缺這一路的就停。「第一場」看發起的先後（world.plots 的順序），不看編號大小——編號是雜湊（見 plot_id）。"""
    p = state.player
    if not active(state, content) or front is None or squad_faction is None or squad_faction == p.faction:
        return []
    for plot in _my_plots(state):
        o = _plot_def(content, plot)
        if o is None or o.plot.how != "win" or _done_by(plot, p.name) >= _cap_per_person(content, o):
            continue
        part = next((x for x in o.plot.parts if x.front == front and x.key not in plot.parts), None)
        if part is not None:
            _mark(state, content, o, plot, part.key)
            return [f"（密謀「{o.name}」：{part.name}這一路，成了。）"]
    return []


def settle(state: GameState, content: Content) -> list[str]:
    """自己參與過、已經收場（完成或過了期限）、還沒結算的密謀，各結算一次（Game.choose、Game.sync 的最後呼叫）：
    完成的——至少辦成一處的人才拿獎勵（企劃者 2026-10-06）：第 3 階以上、這種機緣還沒完成的人算機緣完成（done_text），
    其他人記 plot_contrib 點貢獻（helper_text）；一處都沒辦成的（只按了響應，發起人也一樣）只收到 PLOT_IDLE、什麼都不拿；
    期限到了還沒完成的改成 failed，收到 fail_text。只付還在 plot.faction 的人（企劃者 2026-10-06 裁決）：叛投之後，
    舊陣營的密謀只記成結算過、不給東西（叛投時開著的密謀已經先退出了，見 leave_plots）。
    這一季落幕（休季）之後不結算：收季那一刻的貢獻榜與結算畫面已經存好（world.end_season），之後不能再有貢獻、
    機緣或階級記進這一季（同 ranks.check_summons）；這一季的密謀跟著賽季整個換新，所以也不用補。"""
    if not active(state, content) or state.world.ended:
        return []
    p = state.player
    msgs: list[str] = []
    for plot in state.world.plots:
        if p.name not in plot.members or plot.id in p.opp_settled:
            continue
        if plot.status == "open" and state.world.time > plot.deadline:
            plot.status = "failed"
        if plot.status == "open":
            continue
        p.opp_settled.append(plot.id)
        o = _plot_def(content, plot)
        if o is None or plot.faction != p.faction:
            continue
        if plot.status == "failed":
            msgs.append(o.plot.fail_text)
        elif p.name not in plot.parts.values():  # 一處都沒辦成：什麼都不拿（只按了響應，發起人也一樣）
            msgs.append(PLOT_IDLE.format(name=o.name))
        elif o in open_ones(state, content):
            msgs += [o.plot.done_text] + _complete(state, o)
        else:
            msgs.append(o.plot.helper_text)
            push.add_contribution(p, calendar.point(state.world.time, content, state.world).week, content.config.plot_contrib)
    return msgs


def in_plot(state: GameState) -> bool:
    """響應或牽頭過、還沒收場也沒領的密謀：還開著（沒過期）的，或已經完成但自己還沒結算的。叛投的確認畫面讀它。"""
    p = state.player
    return any(
        p.name in x.members and x.id not in p.opp_settled and x.faction == p.faction and (_live(state, x) or x.status == "done")
        for x in state.world.plots
    )


def leave_plots(state: GameState) -> None:
    """叛投時（defection.defect）：還開著的密謀全部退出，自己做的那幾處也不再算（裁決：他的貢獻不算進成功），
    之後別人補上。已經完成或作罷的不動（成功的時候他是舊陣營的人）；那些由 settle 不付他。"""
    name = state.player.name
    for plot in state.world.plots:
        if plot.status == "open" and name in plot.members:
            plot.members.remove(name)
            plot.parts = {key: who for key, who in plot.parts.items() if who != name}


def _plot_step(state: GameState, content: Content, world, what: str, plot_id: str, rng: random.Random) -> list[str]:
    """響應（join）或在這裡做一處（part）：密謀是自己陣營的、還開著才行。"""
    p = state.player
    plot = next((x for x in state.world.plots if str(x.id) == plot_id), None)
    o = _plot_def(content, plot) if plot is not None else None
    if not active(state, content) or o is None or plot.faction != p.faction or not _live(state, plot):
        return [NOT_NOW]
    if what == "join":
        if p.name in plot.members:
            return [NOT_NOW]
        plot.members.append(p.name)
        return [f"你響應了{plot.shown}的密謀「{o.name}」。還缺：{_missing(content, o, plot)}。"]
    loc_id = p.location
    part = _part_here(state, content, o, plot, loc_id) if o.plot.how == "check" else None
    key = f"plot:{plot.id}:{part.key}" if part is not None else ""
    if part is None or p.name not in plot.members or p.opp_tried.get(key) == _today(state, content) \
            or _done_by(plot, p.name) >= _cap_per_person(content, o) or p.stamina < o.plot.stamina:
        return [NOT_NOW]
    p.stamina -= o.plot.stamina
    place = content.locations[loc_id].name
    if not roll_check(o.plot.check, state, content, world, rng):
        p.opp_tried[key] = _today(state, content)
        return [o.plot.part_fail.replace("{地點}", place)]
    _mark(state, content, o, plot, part.key)
    return [o.plot.part_ok.replace("{地點}", place)]


def _plot_options(state: GameState, content: Content, loc_id: str) -> list:
    """響應（還沒響應的、自己陣營還開著的密謀）與在這裡做一處（響應過的 check 類，這個地點是還沒人做的一處）。"""
    from .engine import Option  # noqa: PLC0415

    opts = []
    p = state.player
    if not active(state, content):
        return opts
    for plot in state.world.plots:
        o = _plot_def(content, plot)
        if o is None or plot.faction != p.faction or not _live(state, plot):
            continue
        if p.name not in plot.members:
            opts.append(Option(id=f"opp:join:{plot.id}",
                               label=f"響應{plot.shown}的密謀「{o.name}」（還缺{_missing(content, o, plot)}）"))
            continue
        if o.plot.how != "check":
            continue
        part = _part_here(state, content, o, plot, loc_id)
        if part is None:
            continue
        label = o.plot.part_label.replace("{地點}", content.locations[loc_id].name)
        tried = p.opp_tried.get(f"plot:{plot.id}:{part.key}") == _today(state, content)
        if _done_by(plot, p.name) >= _cap_per_person(content, o):
            opts.append(Option(id=f"opp:part:{plot.id}", enabled=False,
                               label=f"{label}（你已經做了 {_done_by(plot, p.name)} 處，要等別人）"))
        elif tried:
            opts.append(Option(id=f"opp:part:{plot.id}", enabled=False, label=f"{label}（今天已經試過，換人或改天再來）"))
        else:
            opts.append(Option(id=f"opp:part:{plot.id}", label=f"{label}（體力 {o.plot.stamina}）",
                               enabled=p.stamina >= o.plot.stamina))
    return opts


def _leading(state: GameState) -> bool:
    """正牽頭一場還開著的（叛投走了的不算：他已經不在名單上）。"""
    p = state.player
    return any(x.leader == p.name and x.faction == p.faction and p.name in x.members and _live(state, x)
               for x in state.world.plots)


def _start_plot(state: GameState, content: Content, o: OppDef, loc_id: str) -> list[str]:
    """請命發起：第 3 階以上、在有己方人物的地方、同時只牽頭一場。陣營軍情具名發一則（機緣文件 1.1）。"""
    p = state.player
    if _petition_here(state, content, loc_id) is None or _leading(state):
        return [NOT_NOW]
    w = state.world
    span = windows(content, w).plot_seconds
    pid = plot_id(p.faction, o.id, p.name, w.time)
    taken = {x.id for x in w.plots}
    while pid in taken:  # 雜湊撞上同一季的另一場（幾乎不會）：往後找一個空的
        pid = (pid + 1) % PLOT_ID_SPACE
    plot = Plot(id=pid, opp=o.id, faction=p.faction, leader=p.name, shown=p.name, members=[p.name], deadline=w.time + span)
    w.plots.append(plot)
    text = o.plot.start_text.replace("{name}", plot.shown).replace("{缺}", _missing(content, o, plot))
    add_rumor(state, text, layer="faction", faction=p.faction)  # 陣營軍情：只給這個陣營、寫真名、不帶地點（同叛投、軍令）
    return [f"你接下了密謀「{o.name}」，限 {content.config.plot_days:g} 天內辦成。"]


def _deliver_label(o: OppDef) -> str:
    return o.accumulate.label if o.kind == "accumulate" else o.timing.deliver_label


def _deliver_done(o: OppDef) -> str:
    return o.accumulate.done if o.kind == "accumulate" else o.timing.done


def place_options(state: GameState, content: Content, loc_id: str) -> list:
    """閒著的選單上，這個地點做得了的機緣：交東西（opp:deliver:<id>）、天時地利型此刻能做的（opp:try:<id>）；
    拼圖型在這裡拿得到的東西（opp:piece:<id>:<key>，付錢或過檢定）與湊齊後交的（opp:present:<id>）。"""
    from .engine import Option  # noqa: PLC0415

    opts = []
    for o in open_ones(state, content):
        who = _deliver_here(state, content, o, loc_id)
        if who is not None:
            opts.append(Option(id=f"opp:deliver:{o.id}", label=_deliver_label(o).replace("{主將}", who)))
        if o.kind == "timing":
            here = _timing_here(state, content, o, loc_id)
            if here is not None:
                fresh, who = here
                label = o.timing.label.replace("{人物}", who)
                cost = o.timing.stamina
                if fresh:
                    opts.append(Option(id=f"opp:try:{o.id}", label=f"{label}（體力 {cost}）",
                                       enabled=state.player.stamina >= cost))
                else:
                    opts.append(Option(id=f"opp:try:{o.id}", enabled=False, label=f"{label}（這一回已經試過，下一回再來）"))
        if o.kind == "puzzle":
            for piece in o.puzzle.pieces:
                if piece.how == "ask" or piece.at != loc_id or _has_piece(state, o, piece.key):
                    continue
                if piece.how == "silver":
                    enabled = state.player.stats.get("silver", 0) >= piece.silver
                    opts.append(Option(id=f"opp:piece:{o.id}:{piece.key}", label=piece.label, enabled=enabled))
                else:
                    tried = state.player.opp_tried.get(f"{o.id}:{piece.key}") == _today(state, content)
                    opts.append(Option(
                        id=f"opp:piece:{o.id}:{piece.key}", enabled=not tried and state.player.stamina >= piece.stamina,
                        label=f"{piece.label}（今天已經試過，改天再來）" if tried else f"{piece.label}（體力 {piece.stamina}）",
                    ))
            who = _present_here(state, content, o, loc_id)
            if who is not None:
                opts.append(Option(id=f"opp:present:{o.id}", label=o.puzzle.present.label.replace("{人物}", who)))
        if o.kind == "deduce":
            asker = _asker_here(state, content, o, loc_id)
            if asker is not None:
                tried = state.player.opp_tried.get(o.id) == _today(state, content)
                name = figures.name_of(content, asker)
                for s in o.deduce.suspects:
                    label = o.deduce.label.replace("{人物}", name).replace("{嫌疑人}", s.name)
                    opts.append(Option(id=f"opp:accuse:{o.id}:{s.id}", enabled=not tried,
                                       label=f"{label}（今天已經指認過，改天再來）" if tried else label))
        if o.kind == "plot":
            petition = _petition_here(state, content, loc_id)
            if petition is not None and not _leading(state):
                opts.append(Option(id=f"opp:plot:{o.id}", label=f"{petition}：接下密謀「{o.name}」"))
    return opts + _plot_options(state, content, loc_id)


def _trend_on_done(state: GameState, content: Content, o: OppDef, loc_id: str) -> list[str]:
    """交付完成時推一點：官軍、黃巾推那條戰線往己方（降卒、密信是記下的戰線；名冊是交在哪個據點，就是那裡的戰線），
    豪強推割據。推的是機緣的效果，不是個人推動：直接 change_trend，不走人數緩衝與上限（同軍令達成）。"""
    amount = o.accumulate.trend if o.kind == "accumulate" else 0
    if not amount:
        return []
    faction = content.scenario.faction(o.faction)
    geju_goal = faction.goals.get(GEJU, 0)  # 豪強：推割據；跟戰線那一支一樣是「目標 × 次數」，目標的正負照陣營
    if geju_goal:
        return change_trend(state, content, GEJU, geju_goal * amount)
    front = front_of(content, loc_id) if o.kind == "accumulate" and o.accumulate.deliver == "nearest_base" \
        else state.player.opp_fronts.get(o.id)
    goal = faction.goals.get(front or "", 0)
    return change_trend(state, content, front, goal * amount) if goal else []


def act(state: GameState, content: Content, world, arg: str, rng: random.Random) -> list[str]:
    """閒著的選單上按了機緣的選項（opp:<arg>）：deliver:<id> 交東西、try:<id> 試天時地利型、piece:<id>:<key> 拿拼圖的
    一樣東西、present:<id> 把湊齊的拼圖交出去。選項不在了回「此刻無法」。"""
    if state.world.ended:  # 休季：選單只剩「休季中」，走不到這裡；萬一直接叫也什麼都不做（不完成機緣、不記進收季之後）
        return [NOT_NOW]
    what, _, rest = arg.partition(":")
    opp_id, _, key = rest.partition(":")
    if what in ("join", "part"):  # 這兩種的 rest 是密謀的 id，不是機緣的 id
        return _plot_step(state, content, world, what, rest, rng)
    o = next((x for x in open_ones(state, content) if x.id == opp_id), None)
    loc_id = state.player.location
    if o is None:
        return [NOT_NOW]
    if what == "plot" and o.kind == "plot":
        return _start_plot(state, content, o, loc_id)
    if what == "deliver":
        who = _deliver_here(state, content, o, loc_id)
        if who is None:
            return [NOT_NOW]
        msgs = [_deliver_done(o).replace("{主將}", who)] + _trend_on_done(state, content, o, loc_id)
        return msgs + _complete(state, o)  # _trend_on_done 要在 _complete 之前：_complete 會把 opp_fronts 收掉
    if what == "try" and o.kind == "timing":
        here = _timing_here(state, content, o, loc_id)
        t = o.timing
        if here is None or not here[0] or state.player.stamina < t.stamina:
            return [NOT_NOW]
        who = here[1]
        state.player.stamina -= t.stamina
        if not roll_check(t.check, state, content, world, rng):
            if t.when != "after_showdown":
                state.player.opp_tried[o.id] = _window_key(state, content, t.when)
            return [t.fail.replace("{人物}", who)]
        msgs = [t.ok.replace("{人物}", who)]
        if t.item is not None:  # 先拿到東西，還要送（荒丘的密信）
            state.player.opp_items[o.id] = t.item
            state.player.opp_fronts[o.id] = t.deliver_front
            return msgs
        return msgs + _complete(state, o)
    if what == "piece" and o.kind == "puzzle":
        piece = next((x for x in o.puzzle.pieces if x.key == key), None)
        if piece is None or piece.how == "ask" or piece.at != loc_id or _has_piece(state, o, key):
            return [NOT_NOW]
        p = state.player
        if piece.how == "silver":
            if p.stats.get("silver", 0) < piece.silver:
                return [NOT_NOW]
            p.stats["silver"] -= piece.silver
            _give_piece(state, o, key)
            return [piece.ok, f"銀兩 -{piece.silver}"]
        if p.opp_tried.get(f"{o.id}:{key}") == _today(state, content) or p.stamina < piece.stamina:
            return [NOT_NOW]
        p.stamina -= piece.stamina
        if not roll_check(piece.check, state, content, world, rng):
            p.opp_tried[f"{o.id}:{key}"] = _today(state, content)
            return [piece.fail]
        _give_piece(state, o, key)
        return [piece.ok]
    if what == "present" and o.kind == "puzzle":
        who = _present_here(state, content, o, loc_id)
        if who is None:
            return [NOT_NOW]
        pr = o.puzzle.present
        if pr.at is not None:
            text = pr.done.replace("{人物}", who)
        else:
            text = next(x.done for x in _patrons_of(state, o) if x.at == loc_id)
        return [text] + _complete(state, o)
    if what == "accuse" and o.kind == "deduce":
        asker = _asker_here(state, content, o, loc_id)
        suspect = next((s for s in o.deduce.suspects if s.id == key), None)
        if asker is None or suspect is None or state.player.opp_tried.get(o.id) == _today(state, content):
            return [NOT_NOW]
        name = figures.name_of(content, asker)
        if key != culprit(content, o, _world_tianji(world)):
            p = state.player
            p.opp_tried[o.id] = _today(state, content)
            character = content.figures[asker].character
            if character is not None:
                p.affinities[character] = max(0, p.affinities.get(character, 0) + o.deduce.wrong_affinity)
            return [o.deduce.wrong.replace("{人物}", name).replace("{嫌疑人}", suspect.name)]
        msgs = [o.deduce.right.replace("{人物}", name)]
        for trend_id, amount in o.deduce.trend.items():
            msgs += change_trend(state, content, trend_id, amount)
        return msgs + _complete(state, o)
    return [NOT_NOW]


def title(state: GameState, content: Content, arg: str) -> str:
    """江湖紀錄的標題：機緣的寫「機緣・{名稱}」（arg 是 deliver:<id>、try:<id>、piece:<id>:<key>、present:<id>、
    accuse:<id>:<嫌疑人>、plot:<id>），響應與做一處寫「密謀・{名稱}」（arg 是 join:<密謀 id>、part:<密謀 id>）。"""
    what, _, rest = arg.partition(":")
    if what in ("join", "part"):
        plot = next((x for x in state.world.plots if str(x.id) == rest), None)
        o = _plot_def(content, plot) if plot is not None else None
        return f"密謀・{o.name}" if o is not None else "密謀"
    o = next((x for x in content.opportunities if x.id == rest.partition(":")[0]), None)
    return f"機緣・{o.name}" if o is not None else "機緣"
