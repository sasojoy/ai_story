"""全自動戰鬥：三對三、最多八回合，產生逐回合戰報與結構化的戰鬥事件。

只處理數字與規則，不認識內容檔；由 team.py 把人物與武學轉成這裡的 Unit／Art。
戰鬥事件（施展絕招、控制命中、有人倒下）給戰鬥紀錄挑「關鍵時刻」用，不必從戰報文字反推。
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
    dealt: int = 0  # 這一場造成的傷害（戰報上顯示的數字加總）
    landed: int = 0  # 這一場控制命中的次數

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
class BattleEvent:
    """戰鬥中值得一提的一刻。"""

    round: int  # 第幾回合；心法在開戰前發動，記為 0
    kind: str  # ultimate：施展絕招／control：控制命中／knockout：有人倒下
    actor: str  # 施展、控制或擊倒的人
    actor_side: int  # 0＝A 方（我方）、1＝B 方
    target: str = ""  # 被控制或倒下的人；施展絕招時為空
    art: str = ""  # 施展的絕招，或造成控制的武學
    control: str = ""  # 點穴／卸兵／封脈
    is_leader: bool = False  # 倒下的是隊長


@dataclass
class BattleResult:
    outcome: str  # 以 A 方角度：win / lose / draw
    rounds: int
    report: list[str]
    hp: list[float]  # A 方每人戰後血量，順序同傳入
    events: list[BattleEvent] = field(default_factory=list)  # 依發生先後
    dealt: list[int] = field(default_factory=list)  # A 方每人造成的傷害，順序同 hp
    controls: list[int] = field(default_factory=list)  # A 方每人控制命中的次數，順序同 hp


@dataclass
class _Log:
    """一場戰鬥的紀錄：逐回合戰報文字，以及同時記下的戰鬥事件。"""

    lines: list[str] = field(default_factory=list)
    events: list[BattleEvent] = field(default_factory=list)
    round: int = 0

    def add(self, line: str) -> None:
        self.lines.append(line)

    def event(self, kind: str, actor: Unit, **detail) -> None:
        self.events.append(BattleEvent(self.round, kind, actor.name, actor.side, **detail))


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
            u.dealt = u.landed = 0
        if not any(u.leader for u in side):
            side[0].leader = True
    units = side_a + side_b
    log = _Log()
    for u in units:
        for art in u.arts:
            if art.kind == "心法":
                log.add(f"【心法】{u.name}運起{art.name}。")
                for eff in art.effects:
                    _apply(u, eff, art, units, rng, log, rules, whole_battle=True)
    for rnd in range(1, rules.max_rounds + 1):
        log.round = rnd
        log.add(f"── 第{rnd}回合 ──")
        for u in sorted((u for u in units if u.alive), key=lambda u: (-stat_of(u, "spd"), u.side)):
            if not u.alive:
                continue
            held = list(u.statuses)
            _act(u, units, rng, log, rules)
            _tick(u, held)
            outcome = _outcome(side_a, side_b)
            if outcome:
                loser = side_b if outcome == "win" else side_a
                log.add(f"{_leader(loser).name}倒下，{'敵方' if outcome == 'win' else '我方'}敗退。")
                return _result(outcome, rnd, log, side_a)
    log.add(f"{rules.max_rounds}回合已過，雙方各自收兵，不分勝負。")
    return _result("draw", rules.max_rounds, log, side_a)


def _result(outcome: str, rounds: int, log: _Log, side_a: list[Unit]) -> BattleResult:
    return BattleResult(
        outcome, rounds, log.lines, [u.hp for u in side_a], log.events,
        [u.dealt for u in side_a], [u.landed for u in side_a],
    )


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


def _foes_beaten(u: Unit, units: list[Unit]) -> bool:
    """對方隊長（或全員）已倒下：勝負已分，出手的人不再繼續。"""
    return _lost([x for x in units if x.side != u.side])


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


def _act(u: Unit, units: list[Unit], rng: random.Random, log: _Log, rules: Rules) -> None:
    if _has(u, "點穴"):
        log.add(f"{u.name}穴道受制，動彈不得。")
        return
    _try_ultimate(u, units, rng, log, rules)
    if _foes_beaten(u, units):
        return
    if _has(u, "卸兵"):
        log.add(f"{u.name}兵刃被卸，無法出招。")
        return
    target = _pick_target(u, units, rng, rules)
    _hit(u, target, 1.0, u.style, rng, log, rules, "普攻")
    for art in u.arts:
        if art.kind == "連招" and not _foes_beaten(u, units) and rng.random() < art.chance:
            log.add(f"【連招】{u.name}順勢使出{art.name}！")
            for eff in art.effects:
                _apply(u, eff, art, units, rng, log, rules, main=target)


def _try_ultimate(u: Unit, units: list[Unit], rng, log: _Log, rules) -> None:
    ultimates = [a for a in u.arts if a.kind == "絕招"]
    if not ultimates:
        return
    if _has(u, "封脈"):
        log.add(f"{u.name}經脈受封，絕招發不出來。")
        return
    for art in ultimates:
        if art.name in u.preparing:
            u.preparing[art.name] -= 1
            if u.preparing[art.name] <= 0:
                del u.preparing[art.name]
                _cast(u, art, units, rng, log, rules)
            return
    for art in ultimates:
        if rng.random() < art.chance:
            if art.prep > 0:
                u.preparing[art.name] = art.prep
                log.add(f"【絕招】{u.name}開始蓄勢（{art.name}）……")
            else:
                _cast(u, art, units, rng, log, rules)
            return


def _cast(u: Unit, art: Art, units, rng, log: _Log, rules) -> None:
    log.add(f"【絕招】{u.name}施展{art.name}！")
    log.event("ultimate", u, art=art.name)
    main = _pick_target(u, units, rng, rules)  # 單體特效（傷害、控制……）都落在同一個目標上
    for eff in art.effects:
        _apply(u, eff, art, units, rng, log, rules, main=main)


def _apply(u: Unit, eff: Eff, art: Art, units, rng, log: _Log, rules, main: Unit | None = None,
           whole_battle: bool = False) -> None:
    rounds = WHOLE_BATTLE if whole_battle else eff.rounds
    for t in _targets(u, eff.target, units, rng, rules, main):
        if eff.kind == "damage":
            _hit(u, t, eff.value, art.style, rng, log, rules, "招式")
        elif eff.kind == "heal":
            before = t.hp
            t.hp = min(t.hp_max, t.hp + round(eff.value * t.hp_max))
            log.add(f"{t.name}回復 {round(t.hp - before)} 點內力。")
        elif eff.kind in ("buff", "debuff"):
            t.statuses.append(Status(eff.kind, eff.value, stat=eff.stat, rounds=rounds))
            word = "提升" if eff.kind == "buff" else "降低"
            log.add(f"{t.name}{STAT_NAMES.get(eff.stat, eff.stat)}{word} {round(eff.value * 100)}%。")
        elif eff.kind == "control":
            chance = min(0.95, max(0.05, eff.value * (1 + (u.wis - t.wis) * 0.05)))
            if rng.random() < chance:
                t.statuses.append(Status("control", control=eff.control, rounds=rounds))
                u.landed += 1
                log.add(f"{t.name}被{eff.control}了！")
                log.event("control", u, target=t.name, art=art.name, control=eff.control)
            else:
                log.add(f"{t.name}化解了{eff.control}。")
        elif eff.kind in ("dodge", "reduce"):
            t.statuses.append(Status(eff.kind, eff.value, rounds=rounds))
            word = "閃避" if eff.kind == "dodge" else "減傷"
            log.add(f"{t.name}獲得{word} {round(eff.value * 100)}%。")


def _hit(att: Unit, dfd: Unit | None, mult: float, style: str, rng, log: _Log, rules: Rules, label: str) -> None:
    if dfd is None or not dfd.alive:
        return
    dodge = min(rules.max_dodge, sum(s.value for s in dfd.statuses if s.kind == "dodge"))
    if label == "普攻" and dodge > 0 and rng.random() < dodge:
        log.add(f"{dfd.name}閃身避開了{att.name}的攻擊。")
        return
    dmg = compute_damage(att, dfd, mult, style, rules, rng.uniform(0.9, 1.1))
    dfd.hp = max(0, dfd.hp - dmg)
    att.dealt += dmg
    line = f"{att.name}的{label}命中{dfd.name}，造成 {dmg} 點傷害。"
    if not dfd.alive:
        line += f"{dfd.name}倒下了！"
        log.event("knockout", att, target=dfd.name, is_leader=dfd.leader)
    log.add(line)


def _tick(u: Unit, held: list[Status]) -> None:
    """持續回合以持有者自己的回合計（被點穴而跳過的回合也算）。
    只扣這一回合開始時就已持有的狀態；自己這回合才得到的，留到下一回合結束再扣。"""
    for s in held:
        s.rounds -= 1
    u.statuses = [s for s in u.statuses if s.rounds > 0]
