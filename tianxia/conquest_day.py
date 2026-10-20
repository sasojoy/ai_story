"""領地爭奪第二批：每天的鐘、投票與時程表（純規則；設計 3.6、4.2、4.3，計畫第四章 Task 7，裁決 6、7、9）。

一天＝當地時間（Config.pill_day_utc_offset_hours，跟回體丹同一個時區）settle_hour（22:00）起算的 24 小時，day_key 是第幾天。
結算在換天那一刻（Game._conquest_tick 第一個看到新的一天的人觸發，只准往前走）：每一邊照票（裁決 9：每天都投，有第 4 階的人
投票時第 4 階的票合起來佔 rank4_share，其餘的人佔其餘；沒有第 4 階就每人一票）定幾塊，票定不出來的（沒人投、名額邊上平手、
投的地方已經不是目標）主將照規則補（commander_picks）；兩邊合成這一天的時程表（merge：同一塊同一刻併成一場）。排出來的攻城
都在這一天的 12:00～21:00（slot_first～slot_last），時刻表決戰前後那一段不排（裁決 6）。

下令這一條（第 4 階直接定）照裁決 9 拿掉了；假人照樣投票。票只公開加權之後的比例，不公開誰投了什麼（設計 4.9）。
亂數自己一份（主將|天機|天|陣營|區塊），不碰 Game.rng。只 import models、state、conquest、timetable、world_state（季長）、territory（兩頭）。"""
from __future__ import annotations

import math
import random

from . import conquest, territory, timetable
from .models import Config, Content
from .state import Pick, SiegeSlot, WorldState
from .world_state import season_length_days

HOUR = 3600
DAY = 24 * HOUR

VOTE = "vote"
COMMANDER = "commander"
BY_WORDS = {VOTE: "眾議", COMMANDER: "主將定奪"}  # 待 joy 潤：畫面上怎麼寫這一塊是怎麼定的（不寫誰投了什麼）

# 主將替人挑的原因（〈天下形勢〉與 DayNote 讀；待 joy 潤）
REASON_WORKED = "{place}一帶我軍已佔上風，主將下令一鼓作氣拿下。"
REASON_NEUTRAL = "{place}是中立地，主將要先搶下這片獵場。"
REASON_LOSING = "{line}一帶我軍吃緊，主將要從{place}扳回局面。"
REASON_PLAIN = "主將看準了{place}，下令攻打。"

# 每天結算的天下大事（Task 9；待 joy 潤）
ANNOUNCE = "明日 {time}，{who}攻{place}。"
ANNOUNCE_BOTH = "明日 {time}，{who}同時攻{place}。"
VOID_LATE = "{who}原定攻{place}，時辰已過，這一仗作罷。"


def day_key(real: float, cfg: Config) -> int:
    """現實時間 real（epoch 秒）是第幾天：當地 settle_hour 起算（22:00 換天）。下令、投票都是替「下一天」投的。"""
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
    """時段的寫法「20:30」（給挑時段的鈕；公告的時刻照 calendar.stamp_text）。"""
    return f"{minute // 60:02d}:{minute % 60:02d}"


def per_day(content: Content, world: WorldState | None) -> int:
    """一邊一天打幾塊（設計 4.2）：開季中立的區塊數 ÷ 這一季的天數 ≥ two_per_day_ratio 就 2，否則 1。"""
    cfg = content.config.conquest
    neutral = sum(1 for loc in conquest.blocks(content) if conquest.start_kind(world, content, loc) == conquest.NEUTRAL)
    days = season_length_days(world, content) if world is not None else content.config.season_days
    return 2 if days > 0 and neutral / days >= cfg.two_per_day_ratio else 1


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


def _distance(world: WorldState, content: Content, side: str, loc: str) -> float:
    """這一塊那條線離 side 的目標多遠（往 0 的一方看線的值、往 100 的一方看 100 − 值）；不算進任何一條線的是 0。"""
    line = conquest.line_of(world, content, loc)
    if line is None:
        return 0.0
    low, high = territory.sides(content, line)
    value = world.trends.get(line, 50)
    return float(100 - value) if side == high else float(value) if side == low else 0.0


def _mine(world: WorldState, content: Content, side: str, loc: str) -> float:
    """這一塊的進度往 side 偏多少（正的是往自己這一邊）。"""
    return (conquest.progress_of(world, loc) - 50) * conquest.direction(content, side, loc)


def _reason(world: WorldState, content: Content, side: str, loc: str) -> str:
    place = content.locations[loc].name
    if _mine(world, content, side, loc) > 0:
        return REASON_WORKED.format(place=place)
    if conquest.start_kind(world, content, loc) == conquest.NEUTRAL:
        return REASON_NEUTRAL.format(place=place)
    line = conquest.line_of(world, content, loc)
    if line is not None and _distance(world, content, side, loc) > 50:
        names = {t.id: t.name for t in content.scenario.trends}
        return REASON_LOSING.format(line=names.get(line, line), place=place)
    return REASON_PLAIN.format(place=place)


def _fit(want: int, valid: list[int], used: set[int]) -> int | None:
    """挑一個時段：想要的那一個能用就用；不然照想要的往前找最近的一個；再不然往後找；都被同一邊用掉了就隨便一個能用的。"""
    free = [m for m in valid if m not in used]
    if not free:
        return valid[-1] if valid else None
    if want in free:
        return want
    earlier = [m for m in free if m <= want]
    return earlier[-1] if earlier else free[0]


def commander_picks(
    world: WorldState, content: Content, side: str, n: int, key: int, taken: set[str], valid: list[int] | None = None,
    used: set[int] | None = None,
) -> list[tuple[Pick, str]]:
    """主將照規則替 side 挑 n 塊（Pick, 原因）：進度往自己偏的先、中立先於敵方陣營、這條線離自己目標越遠的先，最後照
    random.Random(f"主將|天機|天|陣營|區塊") 排（同一天同一邊每次挑都一樣）。時段照 commander_slots 依序（第二塊 20:00，裁決 7），
    那個時段不能用就照 _fit 換一個；valid 沒給是 slot_first～slot_last 每一個時段（不扣決戰前後；照實排要給 slots）。
    taken 是這一邊已經定了的區塊，used 是這一邊已經用掉的時段。"""
    cfg = content.config.conquest
    if n <= 0:
        return []
    if valid is None:
        valid = _all_minutes(content.config)
    used = set(used or ())
    if not valid:
        return []
    pool = [loc for loc in conquest.targets(world, content, side) if loc not in taken]

    def order(loc: str) -> tuple:
        rank = random.Random(f"主將|{world.tianji}|{key}|{side}|{loc}").random()
        neutral = 0 if conquest.start_kind(world, content, loc) == conquest.NEUTRAL else 1
        return (-_mine(world, content, side, loc), neutral, -_distance(world, content, side, loc), rank)

    out: list[tuple[Pick, str]] = []
    for i, loc in enumerate(sorted(pool, key=order)[:n]):
        want = cfg.commander_slots[min(i, len(cfg.commander_slots) - 1)] if cfg.commander_slots else valid[-1]
        minute = _fit(want, valid, used)
        if minute is None:
            break
        used.add(minute)
        out.append((Pick(loc=loc, minute=minute), _reason(world, content, side, loc)))
    return out


def weights(votes: dict[str, Pick], seated: set[str], share: float) -> dict[str, float]:
    """每一票的權重（合起來是 1；裁決 9）：在任的第 4 階（seated）與其他人兩組都有人投時，第 4 階那一組合起來 share、其他人
    1 − share，各組裡平分；只有一組有人投就每人一樣。"""
    if not votes:
        return {}
    top = [name for name in votes if name in seated]
    rest = [name for name in votes if name not in seated]
    if top and rest:
        return {**{name: share / len(top) for name in top}, **{name: (1 - share) / len(rest) for name in rest}}
    return {name: 1 / len(votes) for name in votes}


def shares(votes: dict[str, Pick], seated: set[str], share: float) -> dict[str, float]:
    """每一塊加權之後的比例（畫面寫的就是這個，不寫票數、不寫名號）。"""
    out: dict[str, float] = {}
    for name, w in weights(votes, seated, share).items():
        loc = votes[name].loc
        out[loc] = out.get(loc, 0.0) + w
    return out


def tally(votes: dict[str, Pick], n: int, seated: set[str] | None = None, share: float = 0.55) -> list[Pick]:
    """票定得出來的那幾塊（最多 n 塊，照加權之後的比例由高到低）：名額邊上平手的那幾塊都不算（交給主將補），所以可能少於 n、
    也可能是空的。一塊的時段取那一塊的票裡權重最多的時段（平手取晚的）。"""
    if n <= 0 or not votes:
        return []
    w = weights(votes, seated or set(), share)
    blocks: dict[str, float] = {}
    times: dict[str, dict[int, float]] = {}
    for name, pick in votes.items():
        blocks[pick.loc] = blocks.get(pick.loc, 0.0) + w[name]
        times.setdefault(pick.loc, {})
        times[pick.loc][pick.minute] = times[pick.loc].get(pick.minute, 0.0) + w[name]
    ranked = sorted(blocks, key=lambda loc: -blocks[loc])
    cut = round(blocks[ranked[n]], 9) if len(ranked) > n else None  # 第一個沒排進來的
    chosen = [loc for loc in ranked[:n] if cut is None or round(blocks[loc], 9) > cut]
    return [Pick(loc=loc, minute=max(times[loc], key=lambda m: (round(times[loc][m], 9), m))) for loc in chosen]


def plan(
    world: WorldState, content: Content, side: str, key: int, real_now: float, votes: dict[str, Pick] | None = None,
    seated: set[str] | None = None,
) -> list[tuple[Pick, str, str]]:
    """side 第 key 天打哪幾塊：[(Pick, 來源, 原因)]（來源 vote／commander）。票照 tally，投的地方此刻已經不是目標、時段已經不能用的票
    不算；票定不出來的名額主將照 commander_picks 補（時段避開票定的）。開關關著是空的。"""
    if not conquest.on(content, world):
        return []
    n = per_day(content, world)
    everything = slots(world, content, key, real_now, past=True)
    allowed = set(conquest.targets(world, content, side))
    good = {name: p for name, p in (votes or {}).items() if p.loc in allowed and p.minute in everything}
    out: list[tuple[Pick, str, str]] = [(p, VOTE, "") for p in tally(good, n, seated, content.config.conquest.rank4_share)]
    if len(out) < n:
        ahead = slots(world, content, key, real_now) or everything  # 主將挑還開得了集結的時段；都過了照一整天挑（之後照晚了挪）
        taken = {p.loc for p, _, _ in out}
        used = {p.minute for p, _, _ in out}
        out += [(p, COMMANDER, why) for p, why in commander_picks(world, content, side, n - len(out), key, taken, ahead, used)]
    return out


def merge(plans: dict[str, list[tuple[Pick, str, str]]], key: int) -> list[SiegeSlot]:
    """兩邊的 plan 合成這一天的時程表：同一塊同一刻併成一場（攻方兩個），同一塊不同刻照時間排；照開打的先後、同一刻照兩軍的順序。
    at／muster_at 由呼叫端照現實時間換（to_world）。一天最多 2 × per_day 場。"""
    found: dict[tuple[str, int], SiegeSlot] = {}
    order: list[tuple[str, int]] = []
    for side in conquest.SIDES:
        for pick, by, why in plans.get(side, []):
            k = (pick.loc, pick.minute)
            if k not in found:
                found[k] = SiegeSlot(id="", key=key, loc=pick.loc, minute=pick.minute)
                order.append(k)
            slot = found[k]
            if side not in slot.attackers:
                slot.attackers.append(side)
                slot.by[side], slot.reasons[side] = by, why
    rows = sorted((found[k] for k in order), key=lambda s: (s.minute, order.index((s.loc, s.minute))))
    for i, slot in enumerate(rows, 1):
        slot.id = f"{key}-{i}"
    return rows
