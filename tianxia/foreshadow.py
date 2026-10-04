"""關鍵伏筆（計畫 T7；伏筆文件第二節；濃縮版內容表第四節）：聽片段、對話裡的片段選項、最後一步、暗中鎖定、
豪強第三方、天機、官銀。內容在 content/foreshadows.json（models.Foreshadows）。

全部掛在第一季開關後面：calendar.season_one_on 不成立（或沒有任何鏈）時，這裡的每個入口都什麼都不做、
不擲骰、不寫字——beta 那一季一個字都不變。

鎖定不能露出來（伏筆文件 2.4、計畫 Review Focus 3）：最後一步答對時只寫 locks／lock_losers／third_party，
不發任何傳聞、不推大勢；玩家看到的敘事不論先完成還是搶輸都一模一樣。只有大事當天的公告與江湖史揭曉（timetable）。

state 是 GameState；只讀寫玩家自己（片段、物品、計數、做完的、冷卻、貢獻）與 state.world 的鎖定欄位，不碰儲存。
天機要讀全服的 SharedWorldState.tianji，所以要填天機的地方收一個 WorldStateStore（world）；沒給就當天機 0。"""
from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Iterator

from . import calendar, figures, materials, timetable
from .journal import fragment_line
from .models import (
    Check, Content, FsAsk, FsChain, FsFinal, FsFragment, FsRequires, FsStep, FsWrong, Squad,
)
from .rules import check_chance, check_who
from .state import GameState, Lock
from .world_state import WorldStateStore

DAY = 86400
BASE_FRAGMENT_CHANCE = 0.05  # 每次花體力的行動，在所在的大區聽到一則片段的機率（1000 人以上那一檔；伏筆文件 2.2）
GUANYIN = "guanyin"  # 官銀的計數鍵（PlayerState.fs_counters）
# 天機（伏筆文件 2.9）：同一個天機、同一個 key 永遠同一個答案。廣宗的內鬼（mole）這一版先不用
TIANJI: dict[str, tuple[str, ...]] = {
    "wind": ("東", "南", "西", "北"),
    "disguise": ("鹽車", "棺木", "香客", "商隊"),
}
TIANJI_SLOTS = {"{風向}": "wind", "{偽裝}": "disguise"}  # 文字裡的插槽
FIGURE_SLOT = "{人物}"  # 最後一步的敘事裡「出面的那位」：figure 在那條戰線上就是他，否則是 stand_in
TIANJI_ANSWER = "tianji:"  # 答案寫成 tianji:<key>
LOCK_SIDES = tuple(timetable.SIDE_NAMES)  # 會鎖定大事的兩方（官軍、黃巾）；其他陣營（豪強）是第三方
FRONT_RULES = {"guan": (0, 60), "huang": (40, 100)}  # 戰況（往黃巾為正）：官軍 ≤ 60、黃巾 ≥ 40
THIRD_PARTY_FRONT = (35, 65)  # 豪強（第三方）要亂局
UNREADY = "東西還沒備齊"
NOT_YET = "時候未到"
BAD_FRONT = "戰況不利"
NOT_NOW = "（此刻無法這麼做。）"


# ── 換算與天機 ───────────────────────────────────────────


def scale(content: Content) -> float:
    """需求量的係數（伏筆文件 2.8、Config.foreshadow_tiers）：人數上限未滿哪一檔就用那一檔；都不是（1000 人以上）是 1。"""
    players = content.config.server_max_players
    for bound, factor in content.config.foreshadow_tiers:
        if players < bound:
            return factor
    return 1.0


def need(content: Content, base: int) -> int:
    """基準量換算成這個伺服器的需求量：乘上係數、無條件進位、最少 1。基準量 0（或更少）就是不要，回 0。"""
    if base <= 0:
        return 0
    return max(1, math.ceil(round(base * scale(content), 9)))


def fragment_chance(content: Content) -> float:
    """片段的聽到機率反過來：5% ÷ 係數（人少時能互相轉告的人少，聽到的機會要多）。"""
    return min(1.0, BASE_FRAGMENT_CHANCE / scale(content))


def tianji_answer(world_tianji: int, key: str) -> str:
    """本季的天機答案（伏筆文件 2.9）：天機與 key 的 sha256 決定候選裡的哪一個。用 hashlib，不用 Python 內建的 hash
    （那個每次執行都不同）。不認得的 key 丟 KeyError。"""
    candidates = TIANJI[key]
    digest = hashlib.sha256(f"{world_tianji}|tianji|{key}".encode()).digest()
    return candidates[int.from_bytes(digest[:8], "big") % len(candidates)]


def _tianji(world: WorldStateStore | None) -> int:
    return world.read().tianji if world is not None else 0


# ── 找東西 ───────────────────────────────────────────────


def on(state: GameState, content: Content) -> bool:
    """伏筆有沒有在跑：第一季開關開著、這一季開季時也是開的，而且 foreshadows.json 有鏈。"""
    return bool(content.foreshadows.chains) and calendar.season_one_on(state.world, content)


def chain(content: Content, chain_id: str) -> FsChain | None:
    return next((c for c in content.foreshadows.chains if c.id == chain_id), None)


def _event(content: Content, event_id: str):
    return next((e for e in content.timetable if e.id == event_id), None)


def item_name(content: Content, item_id: str) -> str:
    return next((i.name for i in content.foreshadows.items if i.id == item_id), item_id)


def trips(final: FsFinal) -> list[FsStep]:
    """最後一步的每一趟：寫了 steps 就是 steps，否則 final 自己就是那一趟。"""
    return list(final.steps) if final.steps else [final]


def _requires_of(final: FsFinal, trip: FsStep) -> list[FsRequires]:
    """這一趟要滿足的條件：final 的（每一趟都要）加上這一趟自己的（單趟時就是同一份，只算一次）。"""
    return [final.requires] if trip is final else [final.requires, trip.requires]


def _all_requires(requires: FsRequires) -> Iterator[FsRequires]:
    yield requires
    for sub in requires.any_of:
        yield from _all_requires(sub)


def reads_counter(content: Content, key: str) -> bool:
    """有沒有任何一條鏈的條件讀這個計數（官銀只在有人讀時才擲）。"""
    for c in content.foreshadows.chains:
        for trip in trips(c.final):
            for req in _requires_of(c.final, trip):
                if any(key in r.counters for r in _all_requires(req)):
                    return True
    return False


def event_ids(content: Content) -> set[str]:
    """伏筆的事件：片段的來源事件，以及任何選項會給伏筆物品或伏筆計數的事件（準備事件、豪強的起點）。
    開關關著時這些事件不出現（events.event_candidates），beta 那一季一個字都不變。"""
    found = {f.event for c in content.foreshadows.chains for f in c.fragments if f.event}
    for event in content.events.values():
        effects = [eff for ch in event.choices for eff in (ch.effect, ch.fail_effect)]
        if event.free_text is not None:
            effects += [event.free_text.effect, event.free_text.fail_effect]
        if any(eff.clue_items or eff.fs_counters for eff in effects):
            found.add(event.id)
    return found


# ── 誰做得了 ─────────────────────────────────────────────


def capable(state: GameState, content: Content, c: FsChain) -> bool:
    """這個玩家做得了這條鏈：開關開著、是那個陣營的人（散人與其他陣營都不行）、大事還沒發生、依賴的人物還在、還沒做完。"""
    if not calendar.season_one_on(state.world, content) or state.player.faction != c.side:
        return False
    if c.event in state.world.timeline or _event(content, c.event) is None:
        return False
    if c.invalid_if.figure_out is not None and figures.is_out(state, c.invalid_if.figure_out):
        return False
    return c.id not in state.player.fs_done


def _capable_chains(state: GameState, content: Content) -> list[FsChain]:
    if not on(state, content):
        return []
    return [c for c in content.foreshadows.chains if capable(state, content, c)]


def _heard(state: GameState, chain_id: str, index: int) -> bool:
    return index in state.player.fragments.get(chain_id, [])


def _mark_heard(state: GameState, chain_id: str, index: int) -> None:
    heard = state.player.fragments.setdefault(chain_id, [])
    if index not in heard:
        heard.append(index)


# ── 文字 ─────────────────────────────────────────────────


def _version(state: GameState, content: Content, c: FsChain) -> str | None:
    event = _event(content, c.event)
    return timetable._version(state, event) if event is not None else None  # noqa: SLF001  同一個套件


def _figure_name(content: Content, fid: str | None) -> str:
    character = content.characters.get(fid) if fid else None
    return character.name if character is not None else ""


def fill(state: GameState, content: Content, c: FsChain, text: str, world: WorldStateStore | None) -> str:
    """填文字裡的插槽：{風向}、{偽裝} 是本季的天機；{人物} 是最後一步出面的那位（figure 在那條戰線上就是他，否則是 stand_in）。"""
    for slot, key in TIANJI_SLOTS.items():
        if slot in text:
            text = text.replace(slot, tianji_answer(_tianji(world), key))
    if FIGURE_SLOT in text:
        final = c.final
        front = _front(content, c)
        present = final.figure is not None and (front is None or figures.on_front(state, final.figure, front))
        fid = final.figure if present or final.stand_in is None else final.stand_in
        text = text.replace(FIGURE_SLOT, _figure_name(content, fid))
    return text


def _fragment_text(state: GameState, content: Content, c: FsChain, fragment: FsFragment, world) -> str:
    text = fragment.versions.get(_version(state, content, c) or "", fragment.text)
    return fill(state, content, c, text, world)


# ── 片段 ─────────────────────────────────────────────────


def hear_after_action(
    state: GameState, content: Content, region: str | None, rng: random.Random, world: WorldStateStore | None = None,
) -> list[str]:
    """每次花體力的行動之後（Game 呼叫），在所在的大區抽一次：做得了、還沒聽過、來源是行動、大區是這裡的片段裡
    隨機一則，機率 fragment_chance。寫進江湖紀錄的那一句（「你聽到一件事：…」），不發任何傳聞。
    沒有可聽的片段時連骰子都不擲（不打亂別的擲骰）。"""
    if region is None:
        return []
    pool = [
        (c, i, f) for c in _capable_chains(state, content) for i, f in enumerate(c.fragments)
        if f.source == "action" and f.region == region and not _heard(state, c.id, i)
    ]
    if not pool or rng.random() >= fragment_chance(content):
        return []
    c, i, f = rng.choice(pool)
    _mark_heard(state, c.id, i)
    return [fragment_line(_fragment_text(state, content, c, f, world))]


def hear_from_event(state: GameState, content: Content, event_id: str, world: WorldStateStore | None = None) -> list[str]:
    """片段事件觸發時（Game._present 呼叫）：同一則事件可能是好幾條鏈的片段來源（例：老船夫對官軍、黃巾各說一則），
    只給這個玩家做得了的鏈、還沒聽過的那幾則；不做這條鏈的人只看到事件本身（一般版本）。"""
    lines = []
    for c in _capable_chains(state, content):
        for i, f in enumerate(c.fragments):
            if f.source == "event" and f.event == event_id and not _heard(state, c.id, i):
                _mark_heard(state, c.id, i)
                lines.append(fragment_line(_fragment_text(state, content, c, f, world)))
    return lines


def _speaker(state: GameState, f: FsFragment) -> str | None:
    """對話片段由誰說：主角色退場、重創或下獄時改由 stand_in（沒寫就沒人說）；人物還沒種過當成在場。"""
    figure = state.world.figures.get(f.character) if f.character else None
    away = figure is not None and figure.status in ("retired", "crippled", "jailed")
    return f.stand_in if away else f.character


def _talk_clues(state: GameState, content: Content, companion_id: str) -> list[tuple[FsChain, int, FsFragment]]:
    out = []
    for c in _capable_chains(state, content):
        for i, f in enumerate(c.fragments):
            if f.source != "talk" or _heard(state, c.id, i) or _speaker(state, f) != companion_id:
                continue
            if state.player.affinities.get(companion_id, 0) >= need(content, f.affinity_min):
                out.append((c, i, f))
    return out


def talk_options(state: GameState, content: Content, companion_id: str) -> list:
    """對話選單上 talk:N 後面的固定選項 talk:clue:<鏈>:<片段>，標籤是話題：情誼夠、還沒聽過、出面的就是這位才有。"""
    from .engine import Option  # noqa: PLC0415  延後 import：engine → foreshadow

    return [Option(id=f"talk:clue:{c.id}:{i}", label=f.topic) for c, i, f in _talk_clues(state, content, companion_id)]


def hear_talk(
    state: GameState, content: Content, companion_id: str, chain_id: str, index: int, world: WorldStateStore | None = None,
) -> list[str]:
    """按了對話的片段選項：直接回固定文字（不經模型、不扣體力、不算對話輪數），只說一次。選項不在了就回空串列。"""
    for c, i, f in _talk_clues(state, content, companion_id):
        if c.id == chain_id and i == index:
            _mark_heard(state, c.id, i)
            return [f"{_figure_name(content, companion_id)}說：{_fragment_text(state, content, c, f, world)}"]
    return []


# ── 最後一步：做不做得了 ─────────────────────────────────


def _front(content: Content, c: FsChain) -> str | None:
    if c.front is not None:
        return c.front
    event = _event(content, c.event)
    return event.front if event is not None else None


def _window_open(state: GameState, content: Content, c: FsChain, now: float) -> bool:
    """時間窗：一般是大事（決戰照排定的時間，timetable.when）前 window_days 個曆日內；during_muster 是排定的時間到了
    （集結開始）、還沒收場。大事已經結算的鏈在 capable 就擋掉了。"""
    w = state.world
    at = timetable.when(state, content, _event(content, c.event))
    eps = calendar.EPS_SECONDS
    if c.final.window == "during_muster":
        return now + eps >= at
    start = at - c.final.window_days * DAY / calendar.cal_scale(content, w)
    return start - eps <= now < at - eps


def _front_ok(state: GameState, content: Content, c: FsChain) -> bool:
    front = _front(content, c)
    if front is None:
        return True
    low, high = FRONT_RULES.get(c.side, THIRD_PARTY_FRONT)
    return low <= timetable._front_value(state, content, front) <= high  # noqa: SLF001  T1 換成 rules.trend_value


def _one_requires_ok(state: GameState, content: Content, req: FsRequires) -> bool:
    p = state.player
    if any(p.clue_items.get(k, 0) < need(content, v) for k, v in req.clue_items.items()):
        return False
    if materials.grain_of(state, content) < need(content, req.grain):
        return False
    if any(p.donations.get(k, 0) < need(content, v) for k, v in req.donations.items()):
        return False
    if any(p.affinities.get(k, 0) < need(content, v) for k, v in req.affinity.items()):
        return False
    if any(p.fs_counters.get(k, 0) < need(content, v) for k, v in req.counters.items()):
        return False
    return not req.any_of or any(_one_requires_ok(state, content, sub) for sub in req.any_of)


def _requires_ok(state: GameState, content: Content, c: FsChain, trip: FsStep) -> bool:
    return all(_one_requires_ok(state, content, req) for req in _requires_of(c.final, trip))


def _trip_here(state: GameState, c: FsChain, loc_id: str) -> tuple[int, FsStep] | None:
    """在這個地點要做的那一趟（還沒做完的）；這裡沒有就是 None。"""
    for i, trip in enumerate(trips(c.final)):
        if trip.location == loc_id and not (c.final.steps and f"{c.id}:{i}" in state.player.fs_done):
            return i, trip
    return None


def blocked(state: GameState, content: Content, c: FsChain, trip: FsStep, now: float) -> str | None:
    """做不了的原因（選單上按不下去時寫的那句）；做得了是 None。只說做不了，不說為什麼會改變什麼。"""
    if not _window_open(state, content, c, now):
        return NOT_YET
    if c.final.night and not calendar.is_night(now, content, state.world):
        return NOT_YET
    if not _front_ok(state, content, c):
        return BAD_FRONT
    if now < state.player.fs_cooldown_until.get(c.id, 0.0):
        return NOT_YET
    if not _requires_ok(state, content, c, trip):
        return trip.unready or c.final.unready or UNREADY
    return None


def final_options(state: GameState, content: Content, loc_id: str) -> list:
    """這個地點的最後一步：只在做得了的人、在那個地點、那件大事還沒發生時出現 fs:<鏈>；
    時間窗、夜裡、戰況、冷卻、條件不合時按不下去，括號裡寫原因。"""
    from .engine import Option  # noqa: PLC0415  延後 import：engine → foreshadow

    opts = []
    for c in _capable_chains(state, content):
        found = _trip_here(state, c, loc_id)
        if found is None:
            continue
        _, trip = found
        reason = blocked(state, content, c, trip, state.world.time)
        label = trip.label if reason is None else f"{trip.label}（{reason}）"
        opts.append(Option(id=f"fs:{c.id}", label=label, enabled=reason is None))
    return opts


# ── 最後一步：答題 ───────────────────────────────────────


def _asks(trip: FsStep) -> list[FsAsk]:
    if not trip.question:
        return []
    return [FsAsk(question=trip.question, options=trip.options, answer=trip.answer or ""), *trip.then]


def _current_ask(state: GameState, content: Content) -> tuple[FsChain, FsAsk] | None:
    p = state.player
    c = chain(content, p.fs_asking) if p.fs_asking else None
    found = _trip_here(state, c, p.location) if c is not None else None
    asks = _asks(found[1]) if found is not None else []
    if c is None or p.fs_asked >= len(asks):
        return None
    return c, asks[p.fs_asked]


def asking_options(state: GameState, content: Content) -> list:
    """正在答題時的選單：這一題的選項（fs:<鏈>:<選項>），最後是永遠按得下去的「作罷」（fs:leave）。"""
    from .engine import Option  # noqa: PLC0415  延後 import：engine → foreshadow

    current = _current_ask(state, content)
    opts = [] if current is None else [Option(id=f"fs:{current[0].id}:{o.id}", label=o.text) for o in current[1].options]
    return opts + [Option(id="fs:leave", label="作罷")]


def asking_text(state: GameState, content: Content, world: WorldStateStore | None = None) -> str | None:
    """場景上的那一段：正在答的那一題（標題是這一趟的名字）；沒在答題是 None。"""
    current = _current_ask(state, content)
    if current is None:
        return None
    c, ask = current
    found = _trip_here(state, c, state.player.location)
    return f"**{found[1].label}**\n\n{fill(state, content, c, ask.question, world)}"


def trip_label(state: GameState, content: Content, chain_id: str) -> str:
    """江湖紀錄的標題用：這條鏈在所在地點那一趟的名字（例：「束苣乘城」）；找不到就寫「伏筆」。"""
    c = chain(content, chain_id)
    found = _trip_here(state, c, state.player.location) if c is not None else None
    return found[1].label if found is not None else "伏筆"


def leave(state: GameState) -> list[str]:
    state.player.fs_asking, state.player.fs_asked = None, 0
    return ["你想了想，暫且作罷。"]


def _right(ask: FsAsk, option_id: str, world: WorldStateStore | None) -> bool:
    if ask.answer.startswith(TIANJI_ANSWER):
        return option_id == tianji_answer(_tianji(world), ask.answer.removeprefix(TIANJI_ANSWER))
    return option_id == ask.answer


def attempt(
    state: GameState, content: Content, chain_id: str, option_id: str | None, now: float, rng: random.Random,
    world: WorldStateStore | None,
) -> list[str]:
    """最後一步（Game 在選了 fs:<鏈> 或 fs:<鏈>:<選項> 時呼叫）。now 是世界秒（state.world.time）。

    1. 檢查：做得了、人在這一趟的地點、時間窗、夜裡、戰況、冷卻、條件；不合就什麼都不做（題也收起來）。
    2. 這一趟有題：option_id 是 None 時看題（記在 PlayerState.fs_asking）；給了就答目前這一題——答錯照懲罰、可以再來；
       答對而還有追問就問下一題。
    3. 全對（或沒有題）：有檢定就擲（失敗照懲罰），成了就交出物品與糧草、記下這一趟；全部做完就完成這條鏈。"""
    p = state.player
    c = chain(content, chain_id)
    found = _trip_here(state, c, p.location) if c is not None and capable(state, content, c) else None
    asking = p.fs_asking == chain_id
    if found is None or blocked(state, content, c, found[1], now) is not None or (option_id is not None and not asking):
        p.fs_asking, p.fs_asked = None, 0
        return [NOT_NOW]
    index, trip = found
    asks = _asks(trip)
    msgs: list[str] = []
    if asks:
        if option_id is None:
            p.fs_asking, p.fs_asked = chain_id, 0
            return [fill(state, content, c, asks[0].question, world)]
        ask = asks[min(p.fs_asked, len(asks) - 1)]
        chosen = next((o for o in ask.options if o.id == option_id), None)
        if chosen is None:
            return [NOT_NOW]
        msgs.append(f"▸ {chosen.text}")
        if not _right(ask, option_id, world):
            p.fs_asking, p.fs_asked = None, 0
            return msgs + _punish(state, content, c, trip, chosen.wrong or trip.wrong, now)
        if p.fs_asked + 1 < len(asks):
            p.fs_asked += 1
            return msgs + [fill(state, content, c, asks[p.fs_asked].question, world)]
    p.fs_asking, p.fs_asked = None, 0
    check = next((r.check for r in _requires_of(c.final, trip) if r.check is not None), None)
    if check is not None:
        roll = Check(stat=check.stat, difficulty=check.dc, by="self")
        success = rng.random() < check_chance(roll, state, content, world)
        msgs.append(f"（{check_who(roll, state, content, world)}——{'成功' if success else '失敗'}）")
        if not success:
            return msgs + _punish(state, content, c, trip, trip.wrong, now)
    return msgs + _succeed(state, content, c, index, trip, now, world)


def _take_items(state: GameState, content: Content, item_ids, amounts: dict[str, int] | None = None) -> list[str]:
    """收走物品：amounts 給了就各扣那麼多（不夠就扣到 0），沒給就全部收走。回傳「葦束 -2」這種變化量。"""
    bag = state.player.clue_items
    lines = []
    for item_id in item_ids:
        held = bag.get(item_id, 0)
        taken = held if amounts is None else min(held, amounts[item_id])
        if taken <= 0:
            continue
        bag[item_id] = held - taken
        if bag[item_id] <= 0:
            del bag[item_id]
        lines.append(f"{item_name(content, item_id)} -{taken}")
    return lines


def _spend_grain(state: GameState, content: Content, amount: int) -> list[str]:
    """交出糧草（materials.take_grain，從低階的慢屬性素材開始用），回傳用掉的素材（「粗糧 -2」）。"""
    before = dict(state.player.materials)
    if amount <= 0 or not materials.take_grain(state, content, amount):
        return []
    lines = []
    for mid, n in before.items():
        used = n - state.player.materials.get(mid, 0)
        if used > 0:
            lines.append(f"{content.materials[mid].name} -{used}")
    return lines


def _trip_grain(content: Content, c: FsChain, trip: FsStep) -> int:
    return sum(need(content, req.grain) for req in _requires_of(c.final, trip))


def _punish(state: GameState, content: Content, c: FsChain, trip: FsStep, wrong: FsWrong, now: float) -> list[str]:
    """答錯或檢定失敗：照 wrong 處理，之後可以再來（冷卻另計）。"""
    p = state.player
    lines = [wrong.text] if wrong.text else []
    lost = list(wrong.lose_items)
    if wrong.lose_all:
        for req in _requires_of(c.final, trip):
            lost += [k for r in _all_requires(req) for k in r.clue_items]
    lines += _take_items(state, content, list(dict.fromkeys(lost)))
    if wrong.lose_grain:
        lines += _spend_grain(state, content, _trip_grain(content, c, trip))
    for cid, delta in wrong.affinity.items():
        before = p.affinities.get(cid, 0)
        p.affinities[cid] = max(0, min(100, before + delta))
        if p.affinities[cid] != before:
            lines.append(f"{_figure_name(content, cid)}情誼 {p.affinities[cid] - before:+d}")
    if wrong.cooldown_days:
        p.fs_cooldown_until[c.id] = now + wrong.cooldown_days * DAY / calendar.cal_scale(content, state.world)
    return lines


def _hand_over(state: GameState, content: Content, req: FsRequires) -> list[str]:
    """答對時交出條件裡的物品與糧草（換算後的量）；any_of 只交第一組成立的（交之前先挑）。情誼、計數、捐獻只看不扣。"""
    satisfied = next((sub for sub in req.any_of if _one_requires_ok(state, content, sub)), None)
    lines = _take_items(state, content, list(req.clue_items), {k: need(content, v) for k, v in req.clue_items.items()})
    lines += _spend_grain(state, content, need(content, req.grain))
    if satisfied is not None:
        lines += _hand_over(state, content, satisfied)
    return lines


def _succeed(
    state: GameState, content: Content, c: FsChain, index: int, trip: FsStep, now: float, world: WorldStateStore | None,
) -> list[str]:
    """這一趟成了：多趟時交出這一趟自己的條件、記下這一趟，還沒全部做完就回這一趟的那句；全部做完（或單趟）時
    交出整條的條件（final.requires）、完成這條鏈，回完成的敘事。交出去的東西接在敘事後面（「葦束 -1」）。"""
    p = state.player
    spent: list[str] = []
    if trip is not c.final:
        spent += _hand_over(state, content, trip.requires)
        p.fs_done.append(f"{c.id}:{index}")
        if not all(f"{c.id}:{i}" in p.fs_done for i in range(len(c.final.steps))):
            return [fill(state, content, c, trip.success_text, world)] + spent
    spent += _hand_over(state, content, c.final.requires)
    _complete(state, content, c, now)
    text = c.final.success_versions.get(_version(state, content, c) or "", c.final.success_text)
    return [fill(state, content, c, text, world)] + spent


def _complete(state: GameState, content: Content, c: FsChain, now: float) -> None:
    """整條完成：記做完、記貢獻（先完成、搶輸、同陣營後到都照記）；官軍、黃巾寫鎖定（已經有人就進搶輸的名單），
    其他陣營寫第三方。不發任何傳聞、不推大勢（伏筆文件 2.4）。"""
    p, w = state.player, state.world
    p.fs_done.append(c.id)
    gained = content.config.foreshadow_contrib
    if gained:
        week = calendar.point(now, content, w).week
        p.contrib += gained
        p.contrib_weeks[week] = p.contrib_weeks.get(week, 0) + gained
    if c.side in LOCK_SIDES:
        lock = Lock(side=c.side, name=p.name, time=now)
        if c.event not in w.locks:
            w.locks[c.event] = lock
        else:
            w.lock_losers.setdefault(c.event, []).append(lock)
    else:
        names = w.third_party.setdefault(c.event, [])
        if p.name not in names:
            names.append(p.name)


# ── 官銀 ─────────────────────────────────────────────────


def after_win(state: GameState, content: Content, squad: Squad, rng: random.Random, region: str | None) -> list[str]:
    """遊歷打贏之後（Game._squad_encounter 呼叫，探索撞上的野怪不算）：官銀的規則（foreshadows.json 的 guanyin）——
    那個陣營的人、在那幾個大區、打贏那個陣營的隊伍，而且有鏈讀官銀時，才擲 Config.guanyin_chance；中了計數 +1、寫一句。"""
    rule = content.foreshadows.guanyin
    if rule is None or not on(state, content) or state.player.faction != rule.side:
        return []
    if squad.faction != rule.squad_faction or region not in rule.regions or not reads_counter(content, GUANYIN):
        return []
    if rng.random() >= content.config.guanyin_chance:
        return []
    counters = state.player.fs_counters
    counters[GUANYIN] = counters.get(GUANYIN, 0) + 1
    return [rule.text]


# ── 準備事件的物品與計數（rules.apply_effect 呼叫）──────────


def grant(state: GameState, content: Content, clue_items: dict[str, int], counters: dict[str, int]) -> list[str]:
    """Effect.clue_items／fs_counters：開關關著時什麼都不做、不寫字。物品給的寫「獲得 葦束 ×1」、收的寫「葦束 -1」
    （不夠就收到 0）；計數是隱藏的，不寫字。"""
    if not calendar.season_one_on(state.world, content):
        return []
    lines = []
    bag = state.player.clue_items
    for item_id, n in clue_items.items():
        if n > 0:
            bag[item_id] = bag.get(item_id, 0) + n
            lines.append(f"獲得 {item_name(content, item_id)} ×{n}")
        elif n < 0:
            lines += _take_items(state, content, [item_id], {item_id: -n})
    for key, n in counters.items():
        state.player.fs_counters[key] = max(0, state.player.fs_counters.get(key, 0) + n)
    return lines


def asks_of(c: FsChain) -> Iterator[tuple[str, FsAsk]]:
    """每一趟的每一道題（給內容檢查用）：(哪裡, 題)。"""
    for i, trip in enumerate(trips(c.final)):
        for j, ask in enumerate(_asks(trip)):
            yield f"第 {i + 1} 趟第 {j + 1} 題", ask

