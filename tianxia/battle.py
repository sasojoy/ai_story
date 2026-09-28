"""全自動戰鬥：三對三、最多八回合，產生逐回合戰報。

只處理數字與規則，不認識內容檔；由 team.py 把人物與武學轉成這裡的 Unit／Art。
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

BEATS = {"剛": "巧", "巧": "快", "快": "柔", "柔": "剛"}  # key 克制 value
ADVANTAGE = 1.25
WHOLE_BATTLE = 99  # 心法效果持續整場
STAT_NAMES = {"atk": "攻擊", "dfn": "防禦", "spd": "速度"}


@dataclass
class Eff:
    """一個武學效果。value 依 kind 而定：傷害倍率、回復比例、增減比例、控制／閃避機率、減傷比例。"""

    kind: str
    value: float
    target: str = "enemy"
    stat: str | None = None
    control: str | None = None
    rounds: int = 1


@dataclass
class Art:
    name: str
    kind: str
    style: str = "無"
    chance: float = 0.0
    prep: int = 0
    effects: list[Eff] = field(default_factory=list)


@dataclass
class Status:
    kind: str
    value: float = 0.0
    stat: str | None = None
    control: str | None = None
    rounds: int = 1


@dataclass
class Unit:
    name: str
    atk: float
    dfn: float
    spd: float
    wis: float
    hp: float
    hp_max: float
    style: str = "無"
    aptitude: dict[str, float] = field(default_factory=dict)
    arts: list[Art] = field(default_factory=list)
    leader: bool = False
    key: str = ""
    side: int = 0
    statuses: list[Status] = field(default_factory=list)
    preparing: dict[str, int] = field(default_factory=dict)

    @property
    def alive(self) -> bool:
        return self.hp > 0


@dataclass
class Rules:
    max_rounds: int = 8
    atk_factor: float = 12.0
    def_factor: float = 5.0
    min_damage: float = 5.0
    leader_focus: float = 0.3  # 每次選目標時直接打隊長的機率
    max_dodge: float = 0.6
    max_reduce: float = 0.6


@dataclass
class BattleResult:
    outcome: str  # 以 A 方角度：win / lose / draw
    rounds: int
    report: list[str]
    hp: list[float]  # A 方每人戰後血量，順序同傳入


def style_multiplier(attacker: str, defender: str) -> float:
    if BEATS.get(attacker) == defender:
        return ADVANTAGE
    if BEATS.get(defender) == attacker:
        return 1 / ADVANTAGE
    return 1.0


def stat_of(unit: Unit, stat: str) -> float:
    delta = sum(s.value for s in unit.statuses if s.kind == "buff" and s.stat == stat)
    delta -= sum(s.value for s in unit.statuses if s.kind == "debuff" and s.stat == stat)
    return getattr(unit, stat) * max(0.1, 1 + delta)


def compute_damage(att: Unit, dfd: Unit, mult: float, style: str, rules: Rules, roll: float = 1.0) -> int:
    base = max(rules.min_damage, stat_of(att, "atk") * rules.atk_factor - stat_of(dfd, "dfn") * rules.def_factor)
    pool = 0.5 + 0.5 * att.hp / att.hp_max
    reduce = min(rules.max_reduce, sum(s.value for s in dfd.statuses if s.kind == "reduce"))
    dmg = base * mult * style_multiplier(style, dfd.style) * att.aptitude.get(style, 1.0) * pool * roll * (1 - reduce)
    return max(1, round(dmg))


def run_battle(side_a: list[Unit], side_b: list[Unit], rng: random.Random, rules: Rules | None = None) -> BattleResult:
    rules = rules or Rules()
    for side_no, side in enumerate((side_a, side_b)):
        for u in side:
            u.side = side_no
        if not any(u.leader for u in side):
            side[0].leader = True
    units = side_a + side_b
    report: list[str] = []
    for u in units:
        for art in u.arts:
            if art.kind == "心法":
                report.append(f"【心法】{u.name}運起{art.name}。")
                for eff in art.effects:
                    _apply(u, eff, art.style, units, rng, report, rules, whole_battle=True)
    for rnd in range(1, rules.max_rounds + 1):
        report.append(f"── 第{rnd}回合 ──")
        for u in sorted((u for u in units if u.alive), key=lambda u: (-stat_of(u, "spd"), u.side)):
            if not u.alive:
                continue
            held = list(u.statuses)
            _act(u, units, rng, report, rules)
            _tick(u, held)
            outcome = _outcome(side_a, side_b)
            if outcome:
                loser = side_b if outcome == "win" else side_a
                report.append(f"{_leader(loser).name}倒下，{'敵方' if outcome == 'win' else '我方'}敗退。")
                return BattleResult(outcome, rnd, report, [u.hp for u in side_a])
    report.append(f"{rules.max_rounds}回合已過，雙方各自收兵，不分勝負。")
    return BattleResult("draw", rules.max_rounds, report, [u.hp for u in side_a])


def _leader(side: list[Unit]) -> Unit:
    return next(u for u in side if u.leader)


def _lost(side: list[Unit]) -> bool:
    return not _leader(side).alive or not any(u.alive for u in side)


def _outcome(side_a: list[Unit], side_b: list[Unit]) -> str | None:
    if _lost(side_b):
        return "win"
    if _lost(side_a):
        return "lose"
    return None


def _has(u: Unit, control: str) -> bool:
    return any(s.kind == "control" and s.control == control for s in u.statuses)


def _enemies(u: Unit, units: list[Unit]) -> list[Unit]:
    return [x for x in units if x.side != u.side and x.alive]


def _allies(u: Unit, units: list[Unit]) -> list[Unit]:
    return [x for x in units if x.side == u.side and x.alive]


def _pick_target(u: Unit, units: list[Unit], rng: random.Random, rules: Rules) -> Unit | None:
    enemies = _enemies(u, units)
    if not enemies:
        return None
    leader = next((e for e in enemies if e.leader), None)
    if leader is not None and rng.random() < rules.leader_focus:
        return leader
    return min(enemies, key=lambda e: e.hp / e.hp_max)


def _targets(u: Unit, target: str, units: list[Unit], rng, rules, main: Unit | None) -> list[Unit]:
    if target == "self":
        return [u]
    if target == "allies":
        return _allies(u, units)
    if target == "ally_lowest":
        allies = _allies(u, units)
        return [min(allies, key=lambda a: a.hp / a.hp_max)] if allies else []
    if target == "enemies":
        return _enemies(u, units)
    if main is not None and main.alive:
        return [main]
    picked = _pick_target(u, units, rng, rules)
    return [picked] if picked else []


def _act(u: Unit, units: list[Unit], rng: random.Random, report: list[str], rules: Rules) -> None:
    if _has(u, "點穴"):
        report.append(f"{u.name}穴道受制，動彈不得。")
        return
    _try_ultimate(u, units, rng, report, rules)
    if not _enemies(u, units):
        return
    if _has(u, "卸兵"):
        report.append(f"{u.name}兵刃被卸，無法出招。")
        return
    target = _pick_target(u, units, rng, rules)
    _hit(u, target, 1.0, u.style, rng, report, rules, "普攻")
    for art in u.arts:
        if art.kind == "連招" and _enemies(u, units) and rng.random() < art.chance:
            report.append(f"【連招】{u.name}順勢使出{art.name}！")
            for eff in art.effects:
                _apply(u, eff, art.style, units, rng, report, rules, main=target)


def _try_ultimate(u: Unit, units: list[Unit], rng, report, rules) -> None:
    ultimates = [a for a in u.arts if a.kind == "絕招"]
    if not ultimates:
        return
    if _has(u, "封脈"):
        report.append(f"{u.name}經脈受封，絕招發不出來。")
        return
    for art in ultimates:
        if art.name in u.preparing:
            u.preparing[art.name] -= 1
            if u.preparing[art.name] <= 0:
                del u.preparing[art.name]
                _cast(u, art, units, rng, report, rules)
            return
    for art in ultimates:
        if rng.random() < art.chance:
            if art.prep > 0:
                u.preparing[art.name] = art.prep
                report.append(f"【絕招】{u.name}開始蓄勢（{art.name}）……")
            else:
                _cast(u, art, units, rng, report, rules)
            return


def _cast(u: Unit, art: Art, units, rng, report, rules) -> None:
    report.append(f"【絕招】{u.name}施展{art.name}！")
    main = _pick_target(u, units, rng, rules)  # 單體特效（傷害、控制……）都落在同一個目標上
    for eff in art.effects:
        _apply(u, eff, art.style, units, rng, report, rules, main=main)


def _apply(u: Unit, eff: Eff, style: str, units, rng, report, rules, main: Unit | None = None,
           whole_battle: bool = False) -> None:
    rounds = WHOLE_BATTLE if whole_battle else eff.rounds
    for t in _targets(u, eff.target, units, rng, rules, main):
        if eff.kind == "damage":
            _hit(u, t, eff.value, style, rng, report, rules, "招式")
        elif eff.kind == "heal":
            amount = round(eff.value * t.hp_max)
            t.hp = min(t.hp_max, t.hp + amount)
            report.append(f"{t.name}回復 {amount} 點內力。")
        elif eff.kind in ("buff", "debuff"):
            t.statuses.append(Status(eff.kind, eff.value, stat=eff.stat, rounds=rounds))
            word = "提升" if eff.kind == "buff" else "降低"
            report.append(f"{t.name}{STAT_NAMES.get(eff.stat, eff.stat)}{word} {round(eff.value * 100)}%。")
        elif eff.kind == "control":
            chance = min(0.95, max(0.05, eff.value * (1 + (u.wis - t.wis) * 0.05)))
            if rng.random() < chance:
                t.statuses.append(Status("control", control=eff.control, rounds=rounds))
                report.append(f"{t.name}被{eff.control}了！")
            else:
                report.append(f"{t.name}化解了{eff.control}。")
        elif eff.kind in ("dodge", "reduce"):
            t.statuses.append(Status(eff.kind, eff.value, rounds=rounds))
            word = "閃避" if eff.kind == "dodge" else "減傷"
            report.append(f"{t.name}獲得{word} {round(eff.value * 100)}%。")


def _hit(att: Unit, dfd: Unit | None, mult: float, style: str, rng, report, rules: Rules, label: str) -> None:
    if dfd is None or not dfd.alive:
        return
    dodge = min(rules.max_dodge, sum(s.value for s in dfd.statuses if s.kind == "dodge"))
    if label == "普攻" and dodge > 0 and rng.random() < dodge:
        report.append(f"{dfd.name}閃身避開了{att.name}的攻擊。")
        return
    dmg = compute_damage(att, dfd, mult, style, rules, rng.uniform(0.9, 1.1))
    dfd.hp = max(0, dfd.hp - dmg)
    line = f"{att.name}的{label}命中{dfd.name}，造成 {dmg} 點傷害。"
    if not dfd.alive:
        line += f"{dfd.name}倒下了！"
    report.append(line)


def _tick(u: Unit, held: list[Status]) -> None:
    """持續回合以持有者自己的回合計（被點穴而跳過的回合也算）。
    只扣這一回合開始時就已持有的狀態；自己這回合才得到的，留到下一回合結束再扣。"""
    for s in held:
        s.rounds -= 1
    u.statuses = [s for s in u.statuses if s.rounds > 0]
