"""領地爭奪：每天的鐘與攻城時段（純規則；設計 4.3，裁決 6）。翻地與爭搶（輿圖簡化設計 4.4，PM 2026-10-20）之後的樣子：

- 投票與每天 22:00 的公告結算拿掉了（第二批 Task 8、9 的 tally／plan／merge／settle／settle_now、主將定奪都不在了）。攻城戰改成第 4 階的人
  下戰書觸發（place_letter）：時段挑最近一個開得了集結的（今天的 slot_first～slot_last 整點半點，時刻表決戰前後不排；今天沒有了挑下一天的
  第一個），同一塊別一邊已經下了、還沒開集結就併進同一場（中立地就是三方混戰）。
- 一天＝當地時間（Config.pill_day_utc_offset_hours，跟回體丹同一個時區）settle_hour（22:00）起算的 24 小時，day_key 是第幾天；一邊一天一張
  戰書照它算。換天那一刻（Game._conquest_tick 第一個看到新的一天的人觸發，只准往前走）照 day_turn：前一天還沒開成的那幾場作罷、清掉舊的；
  這個掛鉤也是〈天下形勢〉每天一篇的時刻（第三批 A 合進來時接在 day_turn 後面）。
- 軍令的攻城、守城讀 today：此刻進度最高的那一塊（conquest.focus_blocks；PM 2026-10-20 第 1 條）。
只 import models、state、conquest、timetable、calendar。"""
from __future__ import annotations

import math

from . import calendar, conquest, timetable
from .models import Config, Content
from .state import DayNote, Rumor, SiegeSlot, WorldState

HOUR = 3600
DAY = 24 * HOUR

LETTER = "letter"  # SiegeSlot.by、DayNote.by：戰書排的
FLIP = "flip"  # DayNote.by：推滿當場易手（conquest.flip）
# 舊季（第二批投票那一版）的 day_log 還有這兩種；〈天下形勢〉照舊認得（第三批 A 讀它們），新的不再寫
VOTE = "vote"
COMMANDER = "commander"
BY_WORDS = {LETTER: "戰書", VOTE: "眾議", COMMANDER: "主將定奪"}  # 待 joy 潤：畫面上怎麼寫這一場是怎麼定的
REASON_PLAIN = "主將看準了{place}，下令攻打。"  # 舊季的主將定奪沒寫原因時（〈天下形勢〉讀）

# 天下大事（待 joy 潤）：時刻照 calendar.stamp_text（玩家看得到的時刻只有一個寫法），寫在句子中間（傳聞列表自己在前面寫發出的時刻）
LETTER_RUMOR = "{name}替{who}下了戰書：定於{time}攻{place}。"  # 只有真人會下戰書，具名
LETTER_JOIN_RUMOR = "{name}替{who}也下了戰書：{time}跟{others}同時攻{place}。"
VOID_LATE = "{who}原定攻{place}，時辰已過，這一仗作罷。"
VOID_CANCEL = "{who}攻{place}這一仗作罷。"  # 管理者取消（公告不寫管理者）

LIVE = ("planned", "waiting")  # 還沒開集結的：換天時前一天的作罷；別一邊下戰書時可以併進來
SHOWN = ("planned", "waiting", "open")  # 還沒打完的：那一塊被凍結（conquest.frozen）


def day_key(real: float, cfg: Config) -> int:
    """現實時間 real（epoch 秒）是第幾天：當地 settle_hour 起算（22:00 換天）。"""
    local = real + cfg.pill_day_utc_offset_hours * HOUR - cfg.conquest.settle_hour * HOUR
    return math.floor(local / DAY)


def key_start(key: int, cfg: Config) -> float:
    """第 key 天開始的那一刻（現實 epoch 秒）：當地 settle_hour 那一刻。"""
    return key * DAY + cfg.conquest.settle_hour * HOUR - cfg.pill_day_utc_offset_hours * HOUR


def slot_real(key: int, minute: int, cfg: Config) -> float:
    """第 key 天的攻城時段 minute（當地時間的分鐘）在現實的哪一刻：那一天開始之後第一個當地 minute。"""
    start = key_start(key, cfg)
    local_midnight = (key + (1 if minute * 60 < cfg.conquest.settle_hour * HOUR else 0)) * DAY
    real = local_midnight + minute * 60 - cfg.pill_day_utc_offset_hours * HOUR
    return real if real >= start else real + DAY


def to_world(minute: int, key: int, real_now: float, world_time: float, cfg: Config) -> float:
    """那一刻換成世界秒：世界秒＝此刻世界秒＋（那一刻的現實時間－此刻現實時間）× time_scale（計畫一第 8 條）。"""
    return world_time + (slot_real(key, minute, cfg) - real_now) * cfg.time_scale


def slot_text(minute: int) -> str:
    """時段的寫法「20:30」。"""
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _all_minutes(cfg: Config) -> list[int]:
    c = cfg.conquest
    return list(range(c.slot_first, c.slot_last + 1, c.slot_step_minutes))


def _showdown_reals(world: WorldState, content: Content, real_now: float) -> list[float]:
    """這一季還沒結算的時刻表決戰排定的那一刻（集結開始），換成現實時間。"""
    scale = content.config.time_scale
    return [
        real_now + (timetable.when_in(world, content, e) - world.time) / scale
        for e in timetable.events(world, content) if e.kind == "showdown" and e.id not in world.timeline
    ]


def slots(world: WorldState, content: Content, key: int, real_now: float, past: bool = False) -> list[int]:
    """第 key 天開得了的時段（當地分鐘，照先後）：扣掉時刻表決戰前 showdown_gap_before、後 showdown_gap_after 分鐘的那一段（裁決 6）；
    past 是假時再扣掉已經來不及開集結的（開打的時刻早於「此刻＋muster_minutes」）。"""
    cfg = content.config
    before, after = cfg.conquest.showdown_gap_before * 60, cfg.conquest.showdown_gap_after * 60
    showdowns = _showdown_reals(world, content, real_now)
    out = []
    for m in _all_minutes(cfg):
        at = slot_real(key, m, cfg)
        if any(s - before <= at <= s + after for s in showdowns):
            continue
        if not past and at < real_now + cfg.conquest.muster_minutes * 60:
            continue
        out.append(m)
    return out


def next_slot(world: WorldState, content: Content, real_now: float) -> tuple[int, int] | None:
    """戰書挑的時段（設計 4.4「時段挑最近的一個」）：（第幾天, 當地分鐘）——今天還開得了集結的第一個，沒有了就下一天的第一個；都沒有是 None。"""
    key = day_key(real_now, content.config)
    for k in (key, key + 1):
        minutes = slots(world, content, k, real_now)
        if minutes:
            return k, minutes[0]
    return None


def _names(content: Content, sides: list[str]) -> str:
    return "、".join(content.scenario.faction_name(s, s) for s in sides)


def _rumor(world: WorldState, text: str, loc: str | None = None) -> None:
    world.rumors.append(Rumor(time=world.time, text=text, location=loc, layer="world"))


def _ordered(content: Content, sides: list[str]) -> list[str]:
    """攻方照劇本的陣營順序（兩軍是官軍、黃巾；siege 的戰局以 factions[0] 為正向）。"""
    order = [f.id for f in content.scenario.factions]
    return sorted(sides, key=lambda s: order.index(s) if s in order else len(order))


def place_letter(world: WorldState, content: Content, side: str, loc_id: str, name: str, real_now: float) -> tuple[SiegeSlot, str] | None:
    """side 對這一塊下戰書（呼叫端已經驗過 conquest.letter_problem 與階）：同一塊別一邊下了、還沒開集結就併進那一場，不然照 next_slot 排一場
    （at／muster_at 換成世界秒）；記下這一邊今天下過了（letter_days）、天下大事一句（具名）、day_log 一筆（by="letter"，reason 是名號）。
    回（那一場, 天下大事那一句）；排不出時段是 None。"""
    state = world.conquest
    cfg = content.config
    found = conquest.frozen(world, loc_id)
    place = content.locations[loc_id].name
    who = content.scenario.faction_name(side, side)
    if found is not None and found.status in LIVE and side not in found.attackers:
        others = _names(content, found.attackers)
        found.attackers = _ordered(content, [*found.attackers, side])
        found.by[side], found.reasons[side] = LETTER, name
        slot = found
        text = LETTER_JOIN_RUMOR.format(name=name, who=who, time=calendar.stamp_text(slot.at, content, world), others=others,
                                        place=place)
    else:
        picked = next_slot(world, content, real_now)
        if picked is None:
            return None
        key, minute = picked
        at = to_world(minute, key, real_now, world.time, cfg)
        slot = SiegeSlot(
            id=f"L{key}-{int(world.time)}-{side}", key=key, loc=loc_id, minute=minute, at=at,
            muster_at=at - cfg.conquest.muster_minutes * 60 * cfg.time_scale, attackers=[side], by={side: LETTER}, reasons={side: name},
        )
        state.schedule = sorted([*state.schedule, slot], key=lambda s: s.at)
        text = LETTER_RUMOR.format(name=name, who=who, time=calendar.stamp_text(at, content, world), place=place)
    state.letter_days[side] = day_key(real_now, cfg)
    _rumor(world, text, loc_id)
    state.day_log.append(DayNote(key=slot.key, side=side, loc=loc_id, minute=slot.minute, by=LETTER, reason=name))
    return slot, text


ANNOUNCE = "{who}定於{time}攻{place}。"  # 管理者「立刻下戰書」的天下大事（公告不寫管理者；待 joy 潤）


def place_now(world: WorldState, content: Content, side: str, loc_id: str, real_now: float) -> str:
    """管理者救場（Game.admin_conquest_letter，QA 用）：替 side 排一場在「此刻＋集結」開打、集結馬上開的攻城；同一塊別一邊下了、還沒開集結
    就併進那一場。不記 letter_days（不算那一邊今天的那一張）、day_log 照戰書記（reason 空的）。回天下大事那一句。"""
    state, cfg = world.conquest, content.config
    found = conquest.frozen(world, loc_id)
    if found is not None and found.status in LIVE and side not in found.attackers:
        found.attackers = _ordered(content, [*found.attackers, side])
        found.by[side], found.reasons[side] = LETTER, ""
        slot = found
    else:
        local = (real_now + cfg.conquest.muster_minutes * 60 + cfg.pill_day_utc_offset_hours * HOUR) % DAY
        slot = SiegeSlot(
            id=f"now-{int(world.time)}-{side}", key=day_key(real_now, cfg), loc=loc_id, minute=int(local // 60),
            at=world.time + cfg.conquest.muster_minutes * 60 * cfg.time_scale, muster_at=world.time,
            attackers=[side], by={side: LETTER}, reasons={side: ""},
        )
        state.schedule = sorted([*state.schedule, slot], key=lambda s: s.at)
    text = ANNOUNCE.format(who=_names(content, slot.attackers), time=calendar.stamp_text(slot.at, content, world),
                           place=content.locations[loc_id].name)
    _rumor(world, text, loc_id)
    state.day_log.append(DayNote(key=slot.key, side=side, loc=loc_id, minute=slot.minute, by=LETTER, reason=""))
    return text


def void(world: WorldState, content: Content, slot: SiegeSlot, text: str = "") -> None:
    """這一場作罷：那一塊解凍（進度照留）；text 給了寫一句天下大事。"""
    slot.status = "void"
    if text:
        _rumor(world, text, slot.loc)


def note_void(world: WorldState, slot: SiegeSlot, why: str) -> None:
    """作罷了不發天下大事的那幾種（攻方沒人到，裁決 19）在 day_log 記一筆：那一場的每一個攻方各一筆（void 寫原因）。"""
    if world.conquest is None:
        return
    for side in slot.attackers:
        world.conquest.day_log.append(DayNote(
            key=slot.key, side=side, loc=slot.loc, minute=slot.minute, by=slot.by.get(side, ""),
            reason=slot.reasons.get(side, ""), void=why,
        ))


def day_turn(world: WorldState, content: Content, key: int) -> list[str]:
    """換天（Game._conquest_tick 確認 key 比 settled_key 大、開關開著、季在跑）：前幾天排的、到現在還沒開集結的那幾場作罷（伺服器停過）、
    一場一句天下大事；前幾天打完或作罷的從時程表拿掉（還在打的留著）；settled_key 記成 key。回寫進天下大事的那幾句。
    〈天下形勢〉（第三批 A）接在這一下之後開一篇。"""
    state = world.conquest
    out: list[str] = []
    kept: list[SiegeSlot] = []
    for slot in state.schedule:
        if slot.key < key and slot.status in LIVE:
            text = VOID_LATE.format(who=_names(content, slot.attackers), place=content.locations[slot.loc].name)
            void(world, content, slot, text)
            out.append(text)
        if slot.key >= key or slot.status == "open":
            kept.append(slot)
    state.schedule = kept
    state.settled_key = key
    return out


def today(world: WorldState, content: Content, side: str | None, how: str) -> list[str]:
    """軍令的攻城、守城認的地點（PM 2026-10-20 第 1 條，設計 4.5）：how 是 attack（這一邊此刻進度最高、推得動的那幾塊）或 defend（自家被推得
    最高、守得動的那幾塊）；每一條戰線各挑，照內容順序（conquest.focus_blocks）。開關關著是空的。名字照第二批留著（orders._today 讀它）。"""
    if side is None or not conquest.on(content, world):
        return []
    return conquest.focus_blocks(world, content, side, "attack" if how == "attack" else "defend")
