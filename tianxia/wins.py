"""三陣營四勝利（減法季整合設計第三章；計畫第五節，批 3c）：豪強兩本帳、此刻幫誰、季末四階。

- 「此刻幫誰」就是 PlayerState.ally（豪強分屬兩軍的季投靠時挑的那一軍；敵我、出陣、軍令、決戰本來就照它）：lean_of 讀它、
  set_lean 寫它，換邊不算叛投、帳不清（計畫 5.0 第 8 條）。
- 兩本帳 PlayerState.ledgers：豪強替哪一軍出的力記哪一本，contrib 照樣加總數（軍階、席次、榜照舊讀 contrib）。

純規則：只 import models、state、allied、push，不碰引擎與全服狀態。批 0（Config.jianfa、jianfa.on）還沒到，引擎現在沒有人叫這裡；
接線時 credit 的第一行補開關（關著照舊 push.add_contribution），rules_of 改讀 content.config.jianfa。"""
from __future__ import annotations

import bisect
import math

from . import allied, push
from .models import Content, FactionDef, WinsRules
from .state import PlayerState, TierResult, WorldState

BOTH = "both"  # 和局時豪強照兩本合計排（TierResult.ledger_used）
_TOP, _MID, _REST = "top", "mid", "rest"  # 一池切成三段：前 tier1／tier2_share、前 tier3_share 的其餘、其餘過門檻的
_EPS = 10**-9  # 比例乘人數的浮點誤差：0.57 × 100 算出 56.999… 也要是 57（預設的 0.1、0.4 在 5,000 人以內碰不到）

# 改幫另一軍按不下去的原因（lean_problem；待 joy 潤）
LEAN_NOT_GENTRY = "只有地方豪強能改幫另一軍。"
LEAN_BAD = "豪強只能幫官軍或黃巾其中一邊。"
LEAN_SAME = "你此刻就在幫{side}。"


def rules_of(content: Content) -> WinsRules:
    """這一季四階與傾向的數字：批 0 之前是預設的那一份（models.WinsRules）；批 0 到了改成 content.config.jianfa（同名欄位）。"""
    return WinsRules()


def is_gentry(p: PlayerState, content: Content) -> bool:
    """投靠的是要依附一軍的陣營（地方豪強，劇本寫了 allies）。散人、兩軍的人是 False。"""
    return bool(allied.allies_of(content, p.faction))


def _allies(p: PlayerState, content: Content) -> list[str]:
    return [f.id for f in allied.allies_of(content, p.faction)]


def lean_of(p: PlayerState, content: Content) -> str | None:
    """豪強此刻幫哪一軍（就是 ally）；兩軍的人、散人、還沒有傾向的豪強是 None。"""
    return p.ally if is_gentry(p, content) else None


def lean_default(content: Content, location: str, rules: WinsRules | None = None) -> str | None:
    """在 location 投靠豪強時預設幫哪一軍（企劃者 2026-10-24：照投靠點）；不是豪強的投靠點、沒寫是 None。"""
    side = (rules or rules_of(content)).lean_default_by_join.get(location)
    return side if side is not None and any(location in f.join_at and side in f.allies for f in content.scenario.factions) else None


def lean_problem(p: PlayerState, content: Content, side: str) -> str:
    """改幫 side 按不下去的原因；按得下去是空字串。兩軍的人、散人不能改；豪強只能幫劇本 allies 裡的那幾軍；本來就幫它也不算換。"""
    if not is_gentry(p, content):
        return LEAN_NOT_GENTRY
    if side not in _allies(p, content):
        return LEAN_BAD
    if side == p.ally:
        return LEAN_SAME.format(side=content.scenario.faction_name(side, side))
    return ""


def set_lean(p: PlayerState, content: Content, side: str) -> bool:
    """豪強改幫 side：寫 ally、這一季換邊的次數 +1（本來沒有傾向的第一次不算）；不算叛投（defected 不動）、兩本帳與 contrib 不清。
    按不下去（lean_problem）什麼都不動、回 False。名冊、活躍名單、決戰的那一邊由接線的人跟著改（計畫 5.0 第 8 條）。"""
    if lean_problem(p, content, side):
        return False
    if p.ally is not None:
        p.lean_changed += 1
    p.ally = side
    return True


def credit(p: PlayerState, content: Content, world: WorldState, week: int, points: int, *, side: str | None = None) -> None:
    """記貢獻：contrib 與那一週的帳照舊（push.add_contribution）；豪強另記一本——side（決戰照參戰那一刻那一邊）沒給就是此刻的傾向，
    不是它能幫的那一軍就不記帳。0 點什麼都不記。world 留給批 0 的開關（jianfa.on(content, world, "four_wins")，關著只記 contrib）。"""
    if not points:
        return
    push.add_contribution(p, week, points)
    if not is_gentry(p, content):
        return
    to = side or p.ally
    if to in _allies(p, content):
        p.ledgers[to] = p.ledgers.get(to, 0) + points


def ledger_view(p: PlayerState, content: Content) -> dict[str, int] | None:
    """三方卡、本週卡的兩本帳（欄位表 main.sides.ledger）：豪強每一軍一個數（沒記過是 0，照劇本 allies 的順序）；不是豪強是 None。"""
    if not is_gentry(p, content):
        return None
    return {side: p.ledgers.get(side, 0) for side in _allies(p, content)}


def winner_of(world: WorldState, content: Content) -> str | None:
    """這一季是哪一軍贏（收季時記下的結局的 Ending.winner）；和局、還沒收季、結局對不上劇本是 None。"""
    ending = next((e for e in content.scenario.endings if e.id == world.ending_id), None)
    return ending.winner if ending is not None else None


def title_of(rules: WinsRules, tier: int, faction: str) -> str:
    """第 tier 階、faction 那一方的稱號（「階:陣營 id」，找不到再看只寫階的鍵）；沒有階、沒寫是空字串。"""
    if not tier:
        return ""
    titles = rules.tiers.titles
    return titles.get(f"{tier}:{faction}") or titles.get(str(tier), "")


def start_grant(rules: WinsRules, tier: int) -> tuple[int, int]:
    """第 tier 階下一季開局的起手資源（銀兩, 心得）：滿額乘那一階的成數、四捨五入；沒有階是 (0, 0)。"""
    t = rules.tiers
    share = t.start_shares.get(tier, 0.0)
    return round(t.start_silver * share), round(t.start_xinde * share)


def _share(share: float, n: int) -> int:
    return math.floor(share * n + _EPS)


def _cut(pool: list[tuple[str, int]], top_share: float | None, mid_share: float) -> dict[str, tuple[str, int, int]]:
    """一池過了門檻的人（名號, 分數）照名次切三段：前 top_share（無條件捨去、至少 1 人；None 是這一池沒有最上面那一段）、
    前 mid_share（累計，捨去）的其餘、其餘。同分同名次（比他高的人數＋1）、同一段。回 名號 →（段, 名次, 池子人數）。"""
    n = len(pool)
    n_top = max(1, _share(top_share, n)) if top_share is not None and n else 0
    n_mid = _share(mid_share, n)  # 比 n_top 少時（3 人的 40% 是 1）前面那一段先拿，這一段就沒有人
    ascending = sorted(points for _, points in pool)
    out: dict[str, tuple[str, int, int]] = {}
    for name, points in pool:
        rank = 1 + n - bisect.bisect_right(ascending, points)
        out[name] = (_TOP if rank <= n_top else _MID if rank <= n_mid else _REST, rank, n)
    return out


def _results(
    members: list[PlayerState], scores: dict[str, int], books: dict[str, str], top_share: float | None,
    tiers: dict[str, int], faction: str, rules: WinsRules,
) -> dict[str, TierResult]:
    """一池的結果：members 裡分數（scores）過門檻的照 _cut 切、照 tiers 換成第幾階，帳記 books；不過門檻的不在回傳裡。"""
    floor = rules.tiers.min_contribution
    cut = _cut([(p.name, scores[p.name]) for p in members if scores[p.name] >= floor], top_share, rules.tiers.tier3_share)
    out = {}
    for name, (band, rank, of) in cut.items():
        tier = tiers[band]
        out[name] = TierResult(
            tier=tier, title=title_of(rules, tier, faction), ledger_used=books[name], points=scores[name], rank=rank, of=of,
        )
    return out


def _army(members: list[PlayerState], faction: FactionDef, winner: str | None, rules: WinsRules) -> dict[str, TierResult]:
    """兩軍之一：照 contrib 排；贏的那一軍 一 → 三 → 四，輸的（和局時兩軍都是）三 → 四。"""
    won = winner == faction.id
    scores = {p.name: p.contrib for p in members}
    books = {p.name: faction.id for p in members}
    tiers = {_TOP: 1, _MID: 3, _REST: 4}
    got = _results(members, scores, books, rules.tiers.tier1_share if won else None, tiers, faction.id, rules)
    return {p.name: got.get(p.name) or TierResult(points=scores[p.name]) for p in members}


def _gentry(members: list[PlayerState], faction: FactionDef, winner: str | None, rules: WinsRules) -> dict[str, TierResult]:
    """豪強：替贏的那一軍那一本過門檻的照它排（二 → 三 → 四）；那一本不到才看另一本（三 → 四；能幫的不只兩軍時取最多的那一本）。
    和局（或贏的那一軍不是它能幫的）照兩本合計排（三 → 四，帳記 BOTH）。"""
    floor = rules.tiers.min_contribution
    later = {_MID: 3, _REST: 4}
    if winner is None or winner not in faction.allies:
        totals = {p.name: sum(p.ledgers.get(side, 0) for side in faction.allies) for p in members}
        got = _results(members, totals, {p.name: BOTH for p in members}, None, later, faction.id, rules)
        return {p.name: got.get(p.name) or TierResult(points=totals[p.name]) for p in members}
    on_winner = {p.name: p.ledgers.get(winner, 0) for p in members}
    got = _results(members, on_winner, {p.name: winner for p in members}, rules.tiers.tier2_share,
                   {_TOP: 2, **later}, faction.id, rules)
    others = [side for side in faction.allies if side != winner]
    rest = [p for p in members if on_winner[p.name] < floor] if others else []
    books = {p.name: max(others, key=lambda side, p=p: p.ledgers.get(side, 0)) for p in rest}
    got |= _results(rest, {p.name: p.ledgers.get(books[p.name], 0) for p in rest}, books, None, later, faction.id, rules)
    return {p.name: got.get(p.name) or TierResult(points=on_winner[p.name]) for p in members}


def settle(
    world: WorldState, content: Content, players: list[PlayerState], rules: WinsRules | None = None,
) -> dict[str, TierResult]:
    """季末四階（設計 3.3；企劃者 2026-10-24 第 3、4 件）：投靠了劇本裡的陣營的人每人一筆（名號 → TierResult；沒到門檻是第 0 階），
    散人與劇本沒有的陣營不列。贏的那一軍看收季時的結局（winner_of）；和局兩軍都照輸的切、豪強照兩本合計。
    名次只在過了門檻的人裡排，人數照比例（20 人與 2,000 人同一條規則；細節見 _cut 與計畫 5.0 第 13 條）。"""
    r = rules or rules_of(content)
    winner = winner_of(world, content)
    out: dict[str, TierResult] = {}
    for faction in content.scenario.factions:
        members = [p for p in players if p.faction == faction.id]
        if members:
            out |= (_gentry if faction.allies else _army)(members, faction, winner, r)
    return out


def check(content: Content, rules: WinsRules) -> list[str]:
    """數字對得上劇本嗎（content.validate 接線後叫）：豪強每個投靠點都有預設、預設是那個豪強能幫的那一軍、沒有寫到別的地點。"""
    problems: list[str] = []
    gentry = [f for f in content.scenario.factions if f.allies]
    joins = {loc: f for f in gentry for loc in f.join_at}
    for loc, side in rules.lean_default_by_join.items():
        if loc not in joins:
            problems.append(f"lean_default_by_join：{loc} 不是豪強的投靠點")
        elif side not in joins[loc].allies:
            problems.append(f"lean_default_by_join：{loc} 預設幫 {side}，{joins[loc].id} 只能幫 {'、'.join(joins[loc].allies)}")
    missing = [loc for loc in joins if loc not in rules.lean_default_by_join]
    if missing:
        problems.append(f"lean_default_by_join：豪強的投靠點 {'、'.join(missing)} 沒寫預設")
    return problems
