"""門派論劍的純規則（不讀時鐘、不碰 Game）：內容檔、幾點抽籤開打、誰上台、師兄補位、抽籤配對、分身對分身打一場、三場算輸贏、禮匣開出什麼。
設計：門派論劍設計稿第三版（https://claude.ai/artifact/DVU9c63P9mfszr7VJsmTmL；Joy 2026-11-28「機制這樣可以 開始做」）。
一場單挑照擂台那一套（核心 core/arena_bout：分身的一回合與勝負），兩邊都是分身、自己出招。亂數全用自己的（「論劍|季|週|…」），不碰 Game.rng。
打法第四版（Joy 2026-11-28「可以」）：底子照擂台；戰策（抽籤後寫的一句）由模型判誰對路（judge.py，鎖外），引擎照悟性換成起手氣勢、再夾一次；
戰策寫了哪一路，分身多出那一招；場邊事件小小推一下。模型不在照關鍵字判（rule_call），一場照樣打完。"""
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
from tianxia.models import BEATS, MOVES
from tianxia.state import (
    ArenaEntry,
    ArenaFight,
    ArenaSide,
    LunjianBout,
    LunjianCall,
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


def lineup(mine: list[LunjianSeat], seats: int, elders: list[dict], power: float, like: ArenaEntry | None, sect: str, seed: tuple = ()) -> list[LunjianSeat]:
    """一門上台的人：報名的取身手最高的 seats 位，不夠的由師兄補上；照身手由弱到強排成先鋒、中堅、大將。
    師兄、試劍客的戰策照內容檔的老法子配一句（照 seed 與名字雜湊）；報名的人的戰策抽籤之後自己寫。"""
    top = [e.model_copy(update={"plan": ""}) for e in sorted(mine, key=lambda e: (-e.kit.power, e.name))[:seats]]
    out = list(top)
    for i in range(seats - len(top)):
        e = elders[i % len(elders)] if elders else {"name": "師兄"}
        out.append(LunjianSeat(key="", name=e["name"], sect=sect, kit=elder_kit(e["name"], power, like), plan=preset_for(e["name"], *seed)))
    return sorted(out, key=lambda e: (e.kit.power, e.name))


def presets() -> list[dict]:
    """門派的老法子（內容檔 plans：一句戰策、哪一路）：自己不寫的人挑一句；師兄、試劍客照雜湊配一句。"""
    return table().get("plans", [])


def preset_for(name: str, *seed) -> str:
    rows = presets()
    return rows[roll(*seed, name, "老法子").randrange(len(rows))]["text"] if rows else ""


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


# ── 戰策 ──

# 戰策裡寫了哪一路（關鍵字；模型不在時的判法、分身多出哪一招都照它）。一個字的「守」「奇」也算，同分算沒寫
MOVE_WORDS = {
    "強攻": ("強攻", "搶攻", "猛攻", "快攻", "硬拼", "硬碰", "先發制人", "壓上", "猛打", "進逼", "搶先", "速戰", "攻"),
    "固守": ("固守", "以靜制動", "後發制人", "以逸待勞", "避其鋒", "穩", "耗", "拖", "守", "防"),
    "奇襲": ("奇襲", "出其不意", "聲東擊西", "虛招", "游鬥", "繞", "偷", "誘", "詐", "側", "奇"),
}
RULE_HIT = 4  # 照關鍵字判：一邊的戰策剋中對面要出的那一路，判讀 ±4（滿分 ±10）
ADV_MAX = 10


def plan_move(text: str) -> str:
    """戰策寫的是哪一路（強攻、固守、奇襲）；沒寫或兩路一樣多是空字串。長的詞先算，算過的字不再算。"""
    rest, count = str(text or ""), dict.fromkeys(MOVES, 0)
    for word in sorted((w for ws in MOVE_WORDS.values() for w in ws), key=len, reverse=True):
        n = rest.count(word)
        if n:
            count[next(m for m, ws in MOVE_WORDS.items() if word in ws)] += n
            rest = rest.replace(word, "　")
    top = max(count.values())
    best = [m for m, n in count.items() if n == top]
    return best[0] if top > 0 and len(best) == 1 else ""


def lean(kit: ArenaEntry) -> str:
    """分身最拿手的那一招（份量最高；給對面看的「長於…」）。"""
    if not kit.scores:
        return ""
    return max(MOVES, key=lambda m: (kit.scores.get(m, 0.0), -MOVES.index(m)))


def _counter(mine: str, theirs: str) -> int:
    if not mine or not theirs or mine == theirs:
        return 0
    return 1 if BEATS[mine] == theirs else -1 if BEATS[theirs] == mine else 0


def rule_call(a: LunjianSeat, b: LunjianSeat, seat: int) -> LunjianCall:
    """模型不在時的判讀：一邊戰策寫的那一路剋中對面要出的那一路（對面寫了戰策照戰策、沒寫照他最拿手的）就佔上風。沒寫戰策的人不加不扣。"""
    ma, mb = plan_move(a.plan), plan_move(b.plan)
    adv = RULE_HIT * _counter(ma, mb or lean(b.kit)) - RULE_HIT * _counter(mb, ma or lean(a.kit))
    return LunjianCall(seat=seat, adv=max(-ADV_MAX, min(ADV_MAX, adv)))


def cap_of(x: LunjianSeat, t) -> float:
    """戰策全佔上風時推得動的起手氣勢：悟性在基準（5）時 plan_cap，每高一點多 plan_cap_wis；師兄、舊的報名（悟性 0）照基準。"""
    return float(t.plan_cap) + float(t.plan_cap_wis) * max(0.0, float(x.wis) - 5.0)


def swing_of(call: LunjianCall | None, a: LunjianSeat, b: LunjianSeat, t) -> float:
    """判讀換成 a 那一邊的起手氣勢：佔上風的那一邊照自己的悟性換（引擎再夾一次：判讀夾在 ±10）。"""
    if call is None or not call.adv:
        return 0.0
    adv = max(-ADV_MAX, min(ADV_MAX, int(call.adv)))
    return adv / ADV_MAX * cap_of(a if adv > 0 else b, t)


def crowd_of(rng: random.Random, t, a: str, b: str) -> tuple[str, float]:
    """場邊事件：照 crowd_chance 擲一次，碰上了挑一句、挑一邊（回 那一句, a 那一邊的氣勢）。"""
    rows = table().get("crowd", [])
    if not rows or rng.random() >= float(t.crowd_chance):
        return "", 0.0
    row = rows[rng.randrange(len(rows))]
    lucky = rng.random() < 0.5
    return row["line"].format(who=a if lucky else b), float(row["edge"]) * (1 if lucky else -1)


# ── 一場單挑 ──


def _side(e: ArenaEntry) -> ArenaSide:
    return ArenaSide(name=e.name, power=e.power, scores=dict(e.scores), role=e.role, hp=e.hp_cap, hp_cap=e.hp_cap, bare=e.bare, cut=e.cut, card=e.card)


def _pick(side: ArenaSide, rng: random.Random, proxy_power: float, tilt: str = "", by: float = 1.0) -> str:
    """分身出哪一招（同擂台守擂的分身：份量的 proxy_power 次方加權）；戰策寫了哪一路（tilt），那一招的權重再乘 by（乘在次方之後，只是多出一些）。"""
    values = [max(0.0, side.scores.get(m, 0.0)) for m in MOVES]
    top = max(values)
    weights = [(v / top) ** proxy_power for v in values] if top > 0 else [1.0] * len(MOVES)
    weights = [w * (by if m == tilt else 1.0) for w, m in zip(weights, MOVES)]
    return rng.choices(MOVES, weights=weights)[0]


def bout(a: LunjianSeat, b: LunjianSeat, content, seed: tuple, call: LunjianCall | None = None) -> LunjianBout:
    """a 的分身對 b 的分身打一場（擂台的回合數、起手氣勢、勝負門檻）：回 a 那一邊的結果。
    起手氣勢多推戰策的那一份（swing_of）與場邊事件；戰策寫了哪一路，分身多出那一招。判讀有兩版過程時照勝負挑一版當戰報。"""
    cfg, duel, t = content.config.arena, content.config.duel, content.config.lunjian
    rng, trng = roll(*seed, "招"), roll(*seed, "戰法")
    swing = swing_of(call, a, b, t)
    crowd, push = crowd_of(roll(*seed, "場邊"), t, a.name, b.name)
    fight = ArenaFight(id=0, foe_key="", me=_side(a.kit), foe=_side(b.kit), rounds=cfg.rounds, edge=arena_bout._clamp(duel.start + swing + push))
    arena_bout.faced(content, fight.me, fight.foe)
    fight.bout = tactics.open_bout(a.kit.kit, b.kit.kit, a.name, b.name, pvp=True)
    ta, tb, by = plan_move(a.plan), plan_move(b.plan), float(t.plan_tilt)
    lines: list[str] = []
    picks: list[list[str]] = []
    hp: list[list[int]] = []
    tier = None
    while fight.round < fight.rounds:
        fight.move = _pick(fight.foe, rng, cfg.proxy_power, tb, by)
        mine = _pick(fight.me, rng, cfg.proxy_power, ta, by)
        out = arena_bout.exchange_full(fight, mine, content, rng, trng)
        fight.round += 1
        picks.append([out.mine or "", out.his or ""])
        hp.append([round(fight.me.hp), round(fight.foe.hp)])
        lines.append(round_line(a.name, b.name, out.mine, out.his, out.delta))
        tier = arena_bout.verdict(fight, duel)
        if tier is not None:
            break
    tier = tier or "僵持"
    story = ""
    if call is not None and call.win_a and call.win_b:
        story = call.win_a if tier in WIN_TIERS or (tier == "僵持" and fight.edge >= duel.start) else call.win_b
    return LunjianBout(seat=0, tier=tier, edge=round(fight.edge, 1), lines=lines, picks=picks, hp=hp,
                       swing=round(swing, 1), crowd=crowd, story=story, plans=[a.plan, b.plan])


def round_line(a: str, b: str, mine: str | None, his: str | None, delta: int) -> str:
    """一回合一句（待 joy 潤）。"""
    lead = a if delta > 0 else b if delta < 0 else ""
    move = f"{a}{mine or '出不了手'}、{b}{his or '出不了手'}"
    return f"{move}，{lead}佔了上風。" if lead else f"{move}，誰也沒討到便宜。"


def play(match: LunjianMatch, content, seed: tuple) -> None:
    """三場打完、定輸贏：贏的場多的那一門勝；一樣多看大將那一場；再一樣是和局。"""
    match.bouts = []
    calls = {c.seat: c for c in match.calls}
    for i, (a, b) in enumerate(zip(match.seats_a, match.seats_b)):
        call = calls.get(i) or rule_call(a, b, i)
        r = bout(a, b, content, (*seed, i), call)
        r.seat = i
        match.bouts.append(r)
    sa = sum(SCORE[x.tier] for x in match.bouts)
    sb = sum(SCORE[FLIP[x.tier]] for x in match.bouts)
    if sa == sb and match.bouts:
        last = match.bouts[-1].tier
        sa, sb = (1, 0) if last in WIN_TIERS else (0, 1) if last == "落敗" else (0, 0)
    match.winner = "a" if sa > sb else "b" if sb > sa else ""


def leader(seats: list[LunjianSeat]) -> str:
    """帶隊的人：這一邊上台的本人裡身手最高的那一位（帳號鍵；全是師兄是空字串）。他排先鋒、中堅、大將。"""
    real = [s for s in seats if s.key]
    return max(real, key=lambda s: (s.kit.power, s.name)).key if real else ""


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
