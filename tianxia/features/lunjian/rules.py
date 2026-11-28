"""門派論劍的純規則（不讀時鐘、不碰 Game）：內容檔、幾點抽籤開打、誰上台、師兄補位、抽籤配對、分身對分身打一場、三場算輸贏、禮匣開出什麼。
設計：門派論劍設計稿第三版（https://claude.ai/artifact/DVU9c63P9mfszr7VJsmTmL；Joy 2026-11-28「機制這樣可以 開始做」）。
一場單挑照擂台那一套（核心 core/arena_bout：分身的一回合與勝負），兩邊都是分身、自己出招。亂數全用自己的（「論劍|季|週|…」），不碰 Game.rng。"""
from __future__ import annotations

import hashlib
import json
import random
import statistics
from functools import lru_cache
from pathlib import Path

from tianxia import (
    calendar,  # 核心（季曆）
    tactics,  # 共用層（兩邊的本命戰法）
)
from tianxia import world as world_rules  # 核心（季末）
from tianxia.core import arena_bout  # 核心（分身的一回合與勝負）
from tianxia.models import MOVES
from tianxia.state import (
    ArenaEntry,
    ArenaFight,
    ArenaSide,
    LunjianBout,
    LunjianMatch,
    LunjianSeat,
)

HERE = Path(__file__).resolve().parent
FILE = HERE / "content" / "lunjian.json"  # 包自己讀（同 difang：Content 不加欄位）
SEAT_NAMES = ("先鋒", "中堅", "大將")  # 待 joy 潤
WIN_TIERS = ("大勝", "險勝")
SCORE = {"大勝": 1.0, "險勝": 1.0, "僵持": 0.5, "落敗": 0.0}
FLIP = {"大勝": "落敗", "險勝": "落敗", "僵持": "僵持", "落敗": "險勝"}


def on(content) -> bool:
    return bool(content.config.lunjian.enabled)


def roll(*parts) -> random.Random:
    digest = hashlib.sha256("｜".join(map(str, ("論劍", *parts))).encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


@lru_cache(maxsize=2)
def _read(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def table() -> dict:
    return _read(str(FILE))


# ── 時刻 ──


def week_end(week: int, content, season) -> float:
    """第 week 週（7 天季是第幾段）最後一刻之後那一瞬的世界秒；季末更早就照季末。"""
    return min(calendar.week_start(week + 1, content, season), world_rules.season_end_time(season, content))


def _at(week: int, hour: int, content, season) -> float:
    """那一週最後一天的 hour 點（季曆）。最後一天＝季末往前算的那一天：季末那一刻往回 24 − hour 個曆時。"""
    return week_end(week, content, season) - (24 - int(hour)) * calendar.cal_hour_seconds(content, season)


def draw_at(week: int, content, season) -> float:
    return _at(week, content.config.lunjian.draw_hour, content, season)


def fight_at(week: int, content, season) -> float:
    return _at(week, content.config.lunjian.fight_hour, content, season)


# ── 誰上台 ──


def elder_kit(name: str, power: float, like: ArenaEntry | None) -> ArenaEntry:
    """師兄（試劍客）的分身：照一份報名者的分身等比例縮到 power（份量、氣血一起縮）；沒戰法、沒防具、空手。"""
    if like is None or like.power <= 0:
        return ArenaEntry(name=name, power=power, scores={m: power for m in MOVES}, hp_cap=max(100.0, power * 4))
    k = power / like.power
    return ArenaEntry(name=name, power=power, scores={m: v * k for m, v in like.scores.items()}, role="", hp_cap=max(1.0, like.hp_cap * k),
                      arts=[], card=None)


def elder_power(entries: list[LunjianSeat], share: float) -> tuple[float, ArenaEntry | None]:
    """師兄的身手：這一週全服報名者威力的中間值 × share；回（威力, 拿來縮的那一份分身＝最接近中間值的那一位）。"""
    if not entries:
        return 0.0, None
    powers = [e.kit.power for e in entries]
    mid = statistics.median(powers)
    near = min(entries, key=lambda e: (abs(e.kit.power - mid), e.name))
    return mid * share, near.kit


def lineup(mine: list[LunjianSeat], seats: int, elders: list[dict], power: float, like: ArenaEntry | None, sect: str) -> list[LunjianSeat]:
    """一門上台的人：報名的取身手最高的 seats 位，不夠的由師兄補上；照身手由弱到強排成先鋒、中堅、大將。"""
    top = sorted(mine, key=lambda e: (-e.kit.power, e.name))[:seats]
    out = list(top)
    for i in range(seats - len(top)):
        e = elders[i % len(elders)] if elders else {"name": "師兄"}
        out.append(LunjianSeat(key="", name=e["name"], sect=sect, kit=elder_kit(e["name"], power, like)))
    return sorted(out, key=lambda e: (e.kit.power, e.name))


def elders_of(sect: str) -> list[dict]:
    t = table()
    return t.get("elders", {}).get(sect) or t.get("generic_elders", [])


def guests() -> list[dict]:
    return table().get("guests", [])


def pair_up(sects: list[str], last: set[frozenset], season: int, week: int) -> list[tuple[str, str]]:
    """有人報名的門派兩兩配對（照季、週雜湊洗牌；盡量不跟上一週同一對）；單數時多出來的那一門對江湖試劍客（b 是空字串）。"""
    order = sorted(sects)
    roll(season, week, "籤").shuffle(order)
    pairs: list[tuple[str, str]] = []
    while len(order) >= 2:
        a = order.pop(0)
        j = next((i for i, b in enumerate(order) if frozenset((a, b)) not in last), 0)
        pairs.append((a, order.pop(j)))
    if order:
        pairs.append((order[0], ""))
    return pairs


# ── 一場單挑 ──


def _side(e: ArenaEntry) -> ArenaSide:
    return ArenaSide(name=e.name, power=e.power, scores=dict(e.scores), role=e.role, hp=e.hp_cap, hp_cap=e.hp_cap, bare=e.bare, cut=e.cut, card=e.card)


def _pick(side: ArenaSide, rng: random.Random, proxy_power: float) -> str:
    """分身出哪一招（同擂台守擂的分身：份量的 proxy_power 次方加權）。"""
    values = [max(0.0, side.scores.get(m, 0.0)) for m in MOVES]
    top = max(values)
    weights = [(v / top) ** proxy_power for v in values] if top > 0 else [1.0] * len(MOVES)
    return rng.choices(MOVES, weights=weights)[0]


def bout(a: LunjianSeat, b: LunjianSeat, content, seed: tuple) -> LunjianBout:
    """a 的分身對 b 的分身打一場（擂台的回合數、起手氣勢、勝負門檻）：回 a 那一邊的結果。"""
    cfg, duel = content.config.arena, content.config.duel
    fight = ArenaFight(id=0, foe_key="", me=_side(a.kit), foe=_side(b.kit), rounds=cfg.rounds, edge=duel.start)
    arena_bout.faced(content, fight.me, fight.foe)
    fight.bout = tactics.open_bout(a.kit.kit, b.kit.kit, a.name, b.name, pvp=True)
    rng, trng = roll(*seed, "招"), roll(*seed, "戰法")
    lines: list[str] = []
    picks: list[list[str]] = []
    hp: list[list[int]] = []
    tier = None
    while fight.round < fight.rounds:
        fight.move = _pick(fight.foe, rng, cfg.proxy_power)
        mine = _pick(fight.me, rng, cfg.proxy_power)
        out = arena_bout.exchange_full(fight, mine, content, rng, trng)
        fight.round += 1
        picks.append([out.mine or "", out.his or ""])
        hp.append([round(fight.me.hp), round(fight.foe.hp)])
        lines.append(round_line(a.name, b.name, out.mine, out.his, out.delta))
        tier = arena_bout.verdict(fight, duel)
        if tier is not None:
            break
    return LunjianBout(seat=0, tier=tier or "僵持", edge=round(fight.edge, 1), lines=lines, picks=picks, hp=hp)


def round_line(a: str, b: str, mine: str | None, his: str | None, delta: int) -> str:
    """一回合一句（待 joy 潤）。"""
    lead = a if delta > 0 else b if delta < 0 else ""
    move = f"{a}{mine or '出不了手'}、{b}{his or '出不了手'}"
    return f"{move}，{lead}佔了上風。" if lead else f"{move}，誰也沒討到便宜。"


def play(match: LunjianMatch, content, seed: tuple) -> None:
    """三場打完、定輸贏：贏的場多的那一門勝；一樣多看大將那一場；再一樣是和局。"""
    match.bouts = []
    for i, (a, b) in enumerate(zip(match.seats_a, match.seats_b)):
        r = bout(a, b, content, (*seed, i))
        r.seat = i
        match.bouts.append(r)
    sa = sum(SCORE[x.tier] for x in match.bouts)
    sb = sum(SCORE[FLIP[x.tier]] for x in match.bouts)
    if sa == sb and match.bouts:
        last = match.bouts[-1].tier
        sa, sb = (1, 0) if last in WIN_TIERS else (0, 1) if last == "落敗" else (0, 0)
    match.winner = "a" if sa > sb else "b" if sb > sa else ""


def side_of(match: LunjianMatch, key: str) -> str | None:
    """這個帳號在這一對的哪一邊（a、b；沒上台是 None）。"""
    if any(s.key == key for s in match.seats_a):
        return "a"
    if any(s.key == key for s in match.seats_b):
        return "b"
    return None


def tier_for(match: LunjianMatch, side: str, i: int) -> str:
    t = match.bouts[i].tier
    return t if side == "a" else FLIP[t]


def wins_of(match: LunjianMatch, side: str, key: str) -> int:
    """這個人自己贏了幾場單挑（一個人只上一場，0 或 1）。"""
    seats = match.seats_a if side == "a" else match.seats_b
    return sum(1 for i, s in enumerate(seats) if s.key == key and i < len(match.bouts) and tier_for(match, side, i) in WIN_TIERS)


def sweep(match: LunjianMatch, side: str) -> bool:
    return bool(match.bouts) and all(tier_for(match, side, i) in WIN_TIERS for i in range(len(match.bouts)))


# ── 禮匣 ──


def open_box(rows: list[list], rng: random.Random) -> tuple[str, int]:
    """照權重開一樣：（種類, 數量）。"""
    weights = [max(0.0, float(r[2])) for r in rows]
    kind, n, _ = rows[rng.choices(range(len(rows)), weights=weights)[0]]
    return str(kind), int(n)


def cache_clear() -> None:
    _read.cache_clear()
