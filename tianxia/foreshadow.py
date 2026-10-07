"""關鍵伏筆（計畫 T7；伏筆文件第二節；濃縮版內容表第四節）：聽片段、對話裡的片段選項、最後一步、暗中鎖定、
豪強第三方、天機、官銀。內容在 content/foreshadows.json（models.Foreshadows）。

全部掛在同一個判斷後面（active：第一季開關開著、這一季開季時也是開的、而且有鏈）：不成立時這裡的每個入口
（片段、對話的片段選項、最後一步、官銀、準備事件的物品與計數、伏筆事件出不出現）都什麼都不做、不擲骰、不寫字——
beta 那一季一個字都不變。

鎖定不能露出來（伏筆文件 2.4、計畫 Review Focus 3）：最後一步答對時只寫 locks／lock_losers／third_party，
不發任何傳聞、不推大勢；玩家看到的敘事不論先完成還是搶輸都一模一樣。只有大事當天的公告與江湖史揭曉（timetable）。

state 是 GameState；只讀寫玩家自己（片段、物品、計數、做完的、冷卻、貢獻）與 state.world 的鎖定欄位，不碰儲存。
天機要讀全服的 SharedWorldState.tianji，所以要填天機的地方收一個 WorldStateStore（world）；沒給就當天機 0。"""
from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Iterator

from . import calendar, figures, materials, push, timetable
from .journal import fragment_line
from .models import (
    Check, Content, FsAsk, FsChain, FsFinal, FsFragment, FsItem, FsRequires, FsStep, FsWrong, Squad,
)
from .rules import can_meet, check_chance, check_result_line
from .state import GameState, Lock
from .world_state import WorldStateStore

DAY = 86400
BASE_FRAGMENT_CHANCE = 0.05  # 每次花體力的行動，在所在的大區聽到一則片段的機率（1000 人以上那一檔；伏筆文件 2.2）
GUANYIN = "guanyin"  # 官銀的計數鍵（PlayerState.fs_counters）
# 天機（伏筆文件 2.9）：同一個天機、同一個 key 永遠同一個答案。廣宗的內鬼（mole）是黃巾第 4 階機緣「營中的內鬼」
# （正式版乙二，opportunities 的推理型）用的，伏筆的鏈沒有用它
TIANJI: dict[str, tuple[str, ...]] = {
    "wind": ("東", "南", "西", "北"),
    "disguise": ("鹽車", "棺木", "香客", "商隊"),
    "mole": ("clerk", "priest", "strongman"),  # 廣宗的內鬼（伏筆文件 2.9；黃巾第 4 階機緣「營中的內鬼」）
}
TIANJI_SLOTS = {"{風向}": "wind", "{偽裝}": "disguise"}  # 文字裡的插槽
OVERHEARD = "聽說{name}說過："  # 名望不夠求見不到的人，對話片段從行動偷聽到時，原文前面加的這一句（內容表 4.0）
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


def active(state: GameState, content: Content) -> bool:
    """伏筆有沒有在跑：第一季開關開著、這一季開季時也是開的（蓋了章），而且 foreshadows.json 至少有一條鏈。
    所有入口都只看這一個判斷（審查 M4）。"""
    return bool(content.foreshadows.chains) and calendar.season_one_on(state.world, content)


def chain(content: Content, chain_id: str) -> FsChain | None:
    return next((c for c in content.foreshadows.chains if c.id == chain_id), None)


def _event(content: Content, event_id: str):
    return next((e for e in content.timetable if e.id == event_id), None)


def item_name(content: Content, item_id: str) -> str:
    return next((i.name for i in content.foreshadows.items if i.id == item_id), item_id)


def held_items(state: GameState, content: Content) -> list[tuple[FsItem, int]]:
    """手上的伏筆物品（煉製頁素材旁的「伏筆物品」畫面用，T7b）：照 foreshadows.json 的順序、不列數量 0 的。
    伏筆沒在跑（active 不成立：開關關著、這一季沒蓋章、沒有鏈）時是空的，就算背包裡有東西。"""
    if not active(state, content):
        return []
    bag = state.player.clue_items
    return [(item, bag[item.id]) for item in content.foreshadows.items if bag.get(item.id, 0) > 0]


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


def reads_counter(chains: list[FsChain], key: str) -> bool:
    """這幾條鏈裡有沒有哪一條的條件讀這個計數（官銀只在自己還做得了的鏈讀它時才擲）。"""
    for c in chains:
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
    if not active(state, content) or state.player.faction != c.side:
        return False
    if c.event in state.world.timeline or _event(content, c.event) is None:
        return False
    if c.invalid_if.figure_out is not None and figures.is_out(state, c.invalid_if.figure_out):
        return False
    return c.id not in state.player.fs_done


def _capable_chains(state: GameState, content: Content) -> list[FsChain]:
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


def grant_fragment(
    state: GameState, content: Content, chain_id: str, index: int, world: WorldStateStore | None = None,
) -> list[str]:
    """效果直接給一則片段（晉升奇遇 3.3「您該多歇著」；正式版丙二）：伏筆在跑、這個人做得了那條鏈、片段序號存在、還沒聽過才給。
    寫進江湖紀錄那一句（「你聽到一件事：…」），不發傳聞。"""
    c = chain(content, chain_id)
    if c is None or not 0 <= index < len(c.fragments):
        return []
    if not active(state, content) or not capable(state, content, c) or _heard(state, chain_id, index):
        return []
    _mark_heard(state, chain_id, index)
    return [fragment_line(_fragment_text(state, content, c, c.fragments[index], world))]


# 管理者的「給他一個伏筆片段」（管理者觸發鈕第 2 組，2026-10-07）：給的時候走上面的 grant_fragment（效果給片段的同一條），
# 這兩個只給管理者看——下拉選單的那一行與拒絕的原因。都不碰鎖定（誰鎖了、有沒有人鎖），文字裡的天機插槽也不填。
SOURCE_WORDS = {"action": "行動", "event": "事件", "talk": "對話"}


def grant_label(content: Content, c: FsChain, index: int) -> str:
    """管理者下拉選單上的那一行：「長社火攻・2／4（事件）：「這時節的大風，都是半夜從{風向}邊…」」——原文照內容檔，插槽不填。"""
    f = c.fragments[index]
    event = _event(content, c.event)
    text = f.text if len(f.text) <= 24 else f.text[:24] + "…"
    return f"{event.title if event else c.event}・{index + 1}／{len(c.fragments)}（{SOURCE_WORDS.get(f.source, f.source)}）：{text}"


def grant_refusal(state: GameState, content: Content, c: FsChain, index: int) -> str | None:
    """管理者給這個人這一則片段會被拒絕的原因；給得了是 None。跟 grant_fragment 的檢查同一套（capable、聽過沒有），只是說出為什麼。"""
    p = state.player
    if p.faction != c.side:
        who = "是散人" if p.faction is None else f"是{content.scenario.faction(p.faction).name}的人"
        return f"（這條伏筆是{content.scenario.faction(c.side).name}的，{p.name}{who}。）"
    if _heard(state, c.id, index):
        return f"（{p.name}已經聽過這一則了。）"
    event = _event(content, c.event)
    if c.event in state.world.timeline:
        return f"（{event.title if event else c.event}已經發生了，這條伏筆用不上了。）"
    if c.invalid_if.figure_out is not None and figures.is_out(state, c.invalid_if.figure_out):
        return f"（{figures.name_of(content, c.invalid_if.figure_out)}已經不在了，這條伏筆用不上了。）"
    if c.id in p.fs_done:
        return f"（{p.name}已經走完這條伏筆的最後一步。）"
    if not active(state, content) or not capable(state, content, c):
        return "（這一則片段現在給不了。）"
    return None


# ── 片段 ─────────────────────────────────────────────────


def _overheard_from(state: GameState, content: Content, f: FsFragment) -> str | None:
    """對話片段走「行動偷聽」這條路時，聽說的是誰說的（人物 id）；這一片不走這條路就是 None。
    條件：片段是對話（source=talk）、那時候出面的那位存在（_speaker：主角色退場、重創或下獄時是 stand_in）、
    而且玩家求見不到他（rules.can_meet：名望不到 audience_fame、也沒結識過；引擎的求見用同一個判斷）。
    求見得到的人照舊在對話裡用 talk:clue 直接問，行動不抽這一片，免得兩條路都在跑（內容表 4.0）。"""
    speaker = _speaker(state, f) if f.source == "talk" else None
    return None if speaker is None or can_meet(state, content, speaker) else speaker


def hear_after_action(
    state: GameState, content: Content, region: str | None, rng: random.Random, world: WorldStateStore | None = None,
) -> list[str]:
    """每次花體力的行動之後（Game 呼叫），在所在的大區抽一次：做得了、還沒聽過、大區是這裡、來源是行動的片段，
    加上名望不夠求見不到那位人物的對話片段（_overheard_from）裡隨機一則，機率 fragment_chance。
    寫進江湖紀錄的那一句（「你聽到一件事：…」；偷聽到的對話在原文前面加「聽說{人物}說過：」），不發任何傳聞。
    聽過就是聽過：偷聽到與當面問到記的是同一個序號（fragments[鏈]），之後兩條路都不再給這一片。
    沒有可聽的片段時連骰子都不擲（不打亂別的擲骰）。"""
    if region is None:
        return []
    pool: list[tuple[FsChain, int, FsFragment, str | None]] = []  # 最後一格是偷聽的那位人物，行動片段是 None
    for c in _capable_chains(state, content):
        for i, f in enumerate(c.fragments):
            if f.region != region or _heard(state, c.id, i):
                continue
            if f.source == "action":
                pool.append((c, i, f, None))
            elif (speaker := _overheard_from(state, content, f)) is not None:
                pool.append((c, i, f, speaker))
    if not pool or rng.random() >= fragment_chance(content):
        return []
    c, i, f, speaker = rng.choice(pool)
    _mark_heard(state, c.id, i)
    text = _fragment_text(state, content, c, f, world)
    if speaker is not None:
        text = OVERHEARD.format(name=_figure_name(content, speaker)) + text
    return [fragment_line(text)]


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


def heard_texts(state: GameState, content: Content, world: WorldStateStore | None = None) -> list[str]:
    """聽過的線索片段（見聞頁的「個人線索」，傳聞分層設計第六節）：照鏈與片段的順序，文字照片段的寫法填好天機與出面的人
    （偷聽到的不再加「聽說誰說過」）。只有自己看得到；伏筆沒在跑（開關關著、沒有鏈）時是空的。"""
    if not active(state, content):
        return []
    heard = state.player.fragments
    return [
        _fragment_text(state, content, c, c.fragments[i], world)
        for c in content.foreshadows.chains for i in sorted(heard.get(c.id, [])) if 0 <= i < len(c.fragments)
    ]


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
    return low <= timetable._front_value(state, content, front) <= high  # noqa: SLF001  跟時刻表同一個讀法（T1：rules.trend_value）


Plan = tuple[dict[str, int], int]  # 這一趟要交出去的（物品 id → 數量, 糧草份量），換算後的量


def _plan_one(state: GameState, content: Content, req: FsRequires, plan: Plan) -> Plan | None:
    """在已經要交的 plan 之上再加這一組條件：物品與糧草跟前面的加在一起才跟背包比（同一樣東西兩處都要，就要夠兩份）；
    情誼、計數、捐獻只看不交。any_of 照順序挑第一組加得上去的。不成立是 None。"""
    p = state.player
    items, grain = dict(plan[0]), plan[1] + need(content, req.grain)
    for item_id, n in req.clue_items.items():
        items[item_id] = items.get(item_id, 0) + need(content, n)
    if any(p.clue_items.get(k, 0) < n for k, n in items.items()) or materials.grain_of(state, content) < grain:
        return None
    if any(p.donations.get(k, 0) < need(content, v) for k, v in req.donations.items()):
        return None
    if any(p.affinities.get(k, 0) < need(content, v) for k, v in req.affinity.items()):
        return None
    if any(p.fs_counters.get(k, 0) < need(content, v) for k, v in req.counters.items()):
        return None
    if not req.any_of:
        return items, grain
    for sub in req.any_of:
        planned = _plan_one(state, content, sub, (items, grain))
        if planned is not None:
            return planned
    return None


def _plan(state: GameState, content: Content, reqs: list[FsRequires]) -> Plan | None:
    """這幾組條件一起要交出去的東西；有一組不成立就是 None（審查 M1：整條的與這一趟的加在一起算，不是各算各的）。"""
    plan: Plan | None = ({}, 0)
    for req in reqs:
        plan = _plan_one(state, content, req, plan)
        if plan is None:
            return None
    return plan


def _requires_ok(state: GameState, content: Content, c: FsChain, trip: FsStep) -> bool:
    """這一趟做得了：整條的（final.requires）加上這一趟的，一起夠。整條的那份要等完成才交，但現在就要算進去。"""
    return _plan(state, content, _requires_of(c.final, trip)) is not None


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
    main = FsAsk.model_construct(question=trip.question, options=list(trip.options), answer=trip.answer or "")
    return [main, *trip.then]


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
    for check in [r.check for r in _requires_of(c.final, trip) if r.check is not None]:  # 整條的先、這一趟的後，每個都擲
        roll = Check(stat=check.stat, difficulty=check.dc)  # 跟事件檢定一樣只看本人
        success = rng.random() < check_chance(roll, state, content, world)
        msgs.append(check_result_line(success)[1])
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


def spend_grain(state: GameState, content: Content, amount: int) -> list[str]:
    """交出糧草（materials.take_grain，從低階的慢屬性素材開始用），回傳用掉的素材（「粗糧 -2」）；amount ≤ 0 或糧不夠
    什麼都不動、回 []（交出去了就一定有至少一行）。伏筆的交東西（_hand_over 等）與效果的捐糧（rules.apply_effect）共用。"""
    before = dict(state.player.materials)
    if amount <= 0 or not materials.take_grain(state, content, amount):
        return []
    lines = []
    for mid, n in before.items():
        used = n - state.player.materials.get(mid, 0)
        if used > 0:
            lines.append(f"{content.materials[mid].name} -{used}")
    return lines


def _trip_grain(content: Content, trip: FsStep) -> int:
    """這一趟自己的糧草（單趟的鏈就是 final 的）；整條另外要的那份不算這一趟的。"""
    return need(content, trip.requires.grain)


def _punish(state: GameState, content: Content, c: FsChain, trip: FsStep, wrong: FsWrong, now: float) -> list[str]:
    """答錯或檢定失敗：照 wrong 處理，之後可以再來（冷卻另計）。"""
    p = state.player
    lines = [wrong.text] if wrong.text else []
    lost = list(wrong.lose_items)
    if wrong.lose_all:
        for req in _requires_of(c.final, trip):
            lost += [k for r in _all_requires(req) for k in r.clue_items]
    lines += _take_items(state, content, list(dict.fromkeys(lost)))
    if wrong.lose_grain:  # 沒收這一趟的糧草；手上不夠就有多少收多少（不會因為不夠就一份都不收）
        lines += spend_grain(state, content, min(_trip_grain(content, trip), materials.grain_of(state, content)))
    for cid, delta in wrong.affinity.items():
        before = p.affinities.get(cid, 0)
        p.affinities[cid] = max(0, min(100, before + delta))
        if p.affinities[cid] != before:
            lines.append(f"{_figure_name(content, cid)}情誼 {p.affinities[cid] - before:+d}")
    if wrong.cooldown_days:
        p.fs_cooldown_until[c.id] = now + wrong.cooldown_days * DAY / calendar.cal_scale(content, state.world)
    return lines


def _hand_over(state: GameState, content: Content, plan: Plan) -> list[str]:
    """照 _plan 算好的交出物品與糧草（換算後的量）。回傳「葦束 -1」「粗糧 -2」這種變化量。"""
    items, grain = plan
    return _take_items(state, content, list(items), items) + spend_grain(state, content, grain)


def _succeed(
    state: GameState, content: Content, c: FsChain, index: int, trip: FsStep, now: float, world: WorldStateStore | None,
) -> list[str]:
    """這一趟成了：多趟時交出這一趟自己的條件、記下這一趟，還沒全部做完就回這一趟的那句；全部做完（或單趟）時
    交出整條的條件（final.requires）連同這一趟的、完成這條鏈，回完成的敘事——多趟時是後完成的這一趟自己的句子，
    後面接整條完成的那一句（final.success_text，內容表 4.6；兩趟先後不限）。要交的照「一起算」重算一次：
    交不出來（不該發生，檢查時已經一起算過）就什麼都不做、不完成。"""
    p = state.player
    multi = trip is not c.final
    last = not multi or all(f"{c.id}:{i}" in p.fs_done for i in range(len(c.final.steps)) if i != index)
    plan = _plan(state, content, _requires_of(c.final, trip) if last else [trip.requires])
    if plan is None:
        return [NOT_NOW]
    spent = _hand_over(state, content, plan)
    if multi:
        p.fs_done.append(f"{c.id}:{index}")
        if not last:
            return [fill(state, content, c, trip.success_text, world)] + spent
    _complete(state, content, c, now)
    text = c.final.success_versions.get(_version(state, content, c) or "", c.final.success_text)
    done = [fill(state, content, c, text, world)]
    if multi and trip.success_text:  # 完成句寫在內容裡；這一趟自己的句子在前，先完成的那一趟不會走到這裡
        done.insert(0, fill(state, content, c, trip.success_text, world))
    return done + spent


def _complete(state: GameState, content: Content, c: FsChain, now: float) -> None:
    """整條完成：記做完、記貢獻（先完成、搶輸、同陣營後到都照記）；官軍、黃巾寫鎖定（已經有人就進搶輸的名單），
    其他陣營寫第三方。不發任何傳聞、不推大勢（伏筆文件 2.4）。
    公告與江湖史一律寫名號（傳聞分層第七節：改寫歷史的事，留名本身就是獎勵），所以不再記 Lock.shown、third_party_shown；
    這一版之前匿名記下的照舊（timetable.shown 讀得到）。"""
    p, w = state.player, state.world
    p.fs_done.append(c.id)
    push.add_contribution(p, calendar.point(now, content, w).week, content.config.foreshadow_contrib)
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
    那個陣營的人、在那幾個大區、打贏那個陣營的隊伍，而且自己還做得了的鏈裡有讀官銀的，才擲 Config.guanyin_chance；
    中了計數 +1、寫一句。"""
    rule = content.foreshadows.guanyin
    if rule is None or not active(state, content) or state.player.faction != rule.side:
        return []
    if squad.faction != rule.squad_faction or region not in rule.regions:
        return []
    if not reads_counter(_capable_chains(state, content), GUANYIN):  # 讀官銀的鏈都做完、失效或大事已過：不再掉（審查 M3）
        return []
    if rng.random() >= content.config.guanyin_chance:
        return []
    counters = state.player.fs_counters
    counters[GUANYIN] = counters.get(GUANYIN, 0) + 1
    return [rule.text]


# ── 準備事件的物品與計數（rules.apply_effect 呼叫）──────────


def grant(state: GameState, content: Content, clue_items: dict[str, int], counters: dict[str, int]) -> list[str]:
    """Effect.clue_items／fs_counters：伏筆沒在跑（active 不成立）時什麼都不做、不寫字。物品給的寫「獲得 葦束 ×1」、
    收的寫「葦束 -1」（不夠就收到 0）；計數是隱藏的，不寫字。"""
    if not active(state, content):
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

