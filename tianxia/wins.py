"""三陣營四勝利（減法季整合設計第三章；計畫第五節，批 3c）：豪強兩本帳、此刻幫誰、季末四階、三方卡與結局卡的字。

- 「此刻幫誰」就是 PlayerState.ally（豪強分屬兩軍的季投靠時挑的那一軍；敵我、出陣、軍令、決戰本來就照它）：lean_of 讀它、
  set_lean 寫它，換邊不算叛投、帳不清（計畫 5.0 第 8 條）。
- 兩本帳 PlayerState.ledgers：豪強替哪一軍出的力記哪一本，contrib 照樣加總數（軍階、席次、榜照舊讀 contrib）。
- 開關：減法季的總開關 Config.jianfa＋開季的章（on → rules.jianfa(content, world)；子開關 four_wins 2026-10-31 拿掉）；數字在 Config.jianfa
  的 tiers、lean_default_by_join（rules_of）。關著時 credit 只記 contrib，其餘函式引擎不叫，一個字都不變。

純規則：只 import models、state、allied、push（rules 在函式裡延後 import：rules → wins 會成環），不碰引擎與全服狀態。"""
from __future__ import annotations

import bisect
import hashlib
import math
import re

from . import allied, push
from .models import Content, Ending, FactionDef, JianfaRules
from .state import PlayerState, TierResult, WorldState

BOTH = "both"  # 和局時豪強照兩本合計排（TierResult.ledger_used）
_TOP, _MID, _REST = "top", "mid", "rest"  # 一池切成三段：前 tier1／tier2_share、前 tier3_share 的其餘、其餘過門檻的
_EPS = 10**-9  # 比例乘人數的浮點誤差：0.57 × 100 算出 56.999… 也要是 57（預設的 0.1、0.4 在 5,000 人以內碰不到）
TIER_NAMES = {1: "第一階", 2: "第二階", 3: "第三階", 4: "第四階"}

# 改幫另一軍（faction:lean:<side>，本週卡「改幫黃巾」）：按不下去的原因（lean_problem）與按下去的那一句（待 joy 潤）
LEAN_PREFIX = "faction:lean:"
LEAN_BUTTON = "改幫{side}"
LEAN_DONE = "你改幫{side}了：之後出陣、軍令、決戰都照{side}算；替{old}記下的那一本帳照樣留著，不算叛投。"
LEAN_NOT_GENTRY = "只有地方豪強能改幫另一軍。"
LEAN_BAD = "豪強只能幫官軍或黃巾其中一邊。"
LEAN_SAME = "你此刻就在幫{side}。"
LEAN_EVENT_PENDING = "先把眼前這件事了結，再說改幫的事。"  # 待 joy 潤：有事件待選時不收改幫（FB-820，PM 2026-10-26；Game.choose）
LEAN_NOT_DEFECT ="地方豪強換一軍幫不算叛投，按「改幫…」就好。"  # defection.refusal：同一個陣營換一軍（四勝利開著的季）

# 三方卡（欄位表 main.sides_card，設計 3.4；待 joy 潤）
GOAL_ARMY = "季末{side}的態勢高過{other}；{side}的態勢到 {bar} 就是「{ending}」。"
GOAL_ARMY_PLAIN = "季末{side}的態勢高過{other}。"
GOAL_GENTRY = "挑一軍幫：幫{a}、{a}贏，或幫{b}、{b}贏，都算你贏；季末只算你替贏的那一軍出的力；換邊隨時換，不算叛逃。"
GOAL_GENTRY_PLAIN = "挑一軍幫：幫的那一軍贏了就算你贏；季末只算你替贏的那一軍出的力；換邊隨時換，不算叛逃。"
GAP_PART = "{side}離「{ending}」還差 {gap}"  # 最後一週「離贏還差多少」的一方（gap_line 用「，」接兩軍）
REWARD_ARMY = ("貢獻前 {p1}%（至少一人）拿{t1}「{n1}」，其餘前 {p3}% {t3}「{n3}」，其餘到 {floor} 的{t4}「{n4}」；"
               "輸的那一軍照樣有{t3}、{t4}。")
REWARD_GENTRY = ("替贏的那一軍出力前 {p2}%（至少一人）拿{t2}「{n2}」，其餘前 {p3}% {t3}「{n3}」，其餘到 {floor} 的{t4}「{n4}」；"
                 "那一本不到 {floor}，照另一本排{t3}、{t4}。")
REWARD_TIER = "下一季開局銀兩 {silver}、心得 {xinde}"
NOW_ARMY = "態勢 {value}"
NOW_GENTRY_MINE = "你此刻幫{side}・{books}"
NOW_GENTRY_BOOK = "替{side} {n}"
NOW_GENTRY_ROLL = "依附{side} {n} 人"
HINT_NONE = "未入階・還差 {gap}"  # main.sides.tier_hint：此刻就收季拿不到階
HINT_GAP = "{tier}・還差 {gap}"  # 離上一階還差多少
# 季末論功的江湖史（一、二階，設計 3.3「江湖史留名」；待 joy 潤）
CHRONICLE_TIER = "季末論功，{faction}{tier}「{title}」：{names}。"
# 新的一季開局照上一季的階發起手資源（Game._season_grant；待 joy 潤）
GRANT_TITLE = "上一季論功"
GRANT_LINE = "上一季論功，你得了{tier}「{title}」：新的一季開局多帶一份盤纏。"


def rules_of(content: Content) -> JianfaRules:
    """這一季四階與傾向的數字（Config.jianfa 的 tiers、lean_default_by_join）。"""
    return content.config.jianfa


def on(content: Content, world: WorldState | None) -> bool:
    """這一季三陣營四勝利開著嗎：rules.jianfa(content, world)（減法季的設定開著＋這一季開季時蓋了章）。"""
    from .rules import jianfa  # noqa: PLC0415  rules → wins（貢獻呼叫點）：在函式裡 import，避免循環

    return jianfa(content, world)


def is_gentry(p: PlayerState, content: Content) -> bool:
    """投靠的是要依附一軍的陣營（地方豪強，劇本寫了 allies）。散人、兩軍的人是 False。"""
    return bool(allied.allies_of(content, p.faction))


def _allies(p: PlayerState, content: Content) -> list[str]:
    return [f.id for f in allied.allies_of(content, p.faction)]


def allies(p: PlayerState, content: Content) -> list[str]:
    """豪強能幫的那幾軍（照劇本 allies 的順序）；兩軍的人、散人是空的。"""
    return _allies(p, content)


def lean_of(p: PlayerState, content: Content) -> str | None:
    """豪強此刻幫哪一軍（就是 ally）；兩軍的人、散人、還沒有傾向的豪強是 None。"""
    return p.ally if is_gentry(p, content) else None


def lean_default(content: Content, location: str, rules: JianfaRules | None = None) -> str | None:
    """在 location 投靠豪強時預設幫哪一軍（企劃者 2026-10-24：照投靠點）；不是豪強的投靠點、沒寫是 None。"""
    side = (rules or rules_of(content)).lean_default_by_join.get(location)
    return side if side is not None and any(location in f.join_at and side in f.allies for f in content.scenario.factions) else None


def join_lean(content: Content, faction_id: str | None, location: str, rules: JianfaRules | None = None) -> str | None:
    """投靠 faction_id（豪強）那一下直接給的傾向：照投靠點（lean_default）；拜入豪強門派而投靠的人照門派所在地（曹氏莊院 → 官軍，
    PM 2026-10-25 第 5 件）。那裡沒寫預設照劇本 allies 的第一軍。不是要依附一軍的陣營是 None。"""
    sides = [f.id for f in allied.allies_of(content, faction_id)]
    if not sides:
        return None
    side = lean_default(content, location, rules)
    return side if side in sides else sides[0]


def bot_lean(name: str, season: int, content: Content, faction_id: str | None, rolls: dict[str, int]) -> str | None:
    """伺服器假人投靠豪強那一下的傾向（FB-810，PM 2026-10-26）：依附這個陣營（豪強）的人數少的那一軍，不看投靠點——不然新角色都從
    潁川出發、最近的豪強投靠點是曹氏莊院，假人全部幫官軍，而假人又不按「改幫」。數的是名冊裡依附這個陣營的人（rolls 是
    world.roll_counts()：「陣營@那一軍」），不是那一軍全部的人；一樣多照名號＋季的雜湊挑（同 bot.enlist_pick，不碰亂數）。
    真人照投靠點（join_lean）。不是要依附一軍的陣營、沒有陣營是 None。"""
    sides = [f.id for f in allied.allies_of(content, faction_id)]
    if not sides:
        return None
    counts = dict.fromkeys(sides, 0)
    for key, n in rolls.items():
        faction, ally = allied.split_key(key)
        if faction == faction_id and ally in counts:
            counts[ally] += n
    return min(sides, key=lambda side: (counts[side], hashlib.sha256(f"{name}|{season}|{side}".encode()).hexdigest()))


def lean_sides(p: PlayerState, content: Content) -> list[str]:
    """本週卡「改幫…」那幾顆：豪強能幫、此刻沒在幫的那幾軍（照劇本 allies 的順序）；不是豪強是空的。"""
    return [side for side in _allies(p, content) if side != p.ally]


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
    按不下去（lean_problem）什麼都不動、回 False。名冊、活躍名單、決戰的那一邊由引擎跟著改（Game._lean_step）。"""
    if lean_problem(p, content, side):
        return False
    if p.ally is not None:
        p.lean_changed += 1
    p.ally = side
    return True


def credit(p: PlayerState, content: Content, world: WorldState, week: int, points: int, *, side: str | None = None) -> None:
    """記貢獻：contrib 與那一週的帳照舊（push.add_contribution）；四勝利開著的季（on）豪強另記一本——side（決戰照參戰那一刻那一邊）
    沒給就是此刻的傾向，不是它能幫的那一軍就不記帳。0 點什麼都不記；關著只記 contrib，一個字都不變。"""
    if not points:
        return
    push.add_contribution(p, week, points)
    if not on(content, world) or not is_gentry(p, content):
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


def title_of(rules: JianfaRules, tier: int, faction: str) -> str:
    """第 tier 階、faction 那一方的稱號（「階:陣營 id」，找不到再看只寫階的鍵）；沒有階、沒寫是空字串。"""
    if not tier:
        return ""
    titles = rules.tiers.titles
    return titles.get(f"{tier}:{faction}") or titles.get(str(tier), "")


def start_grant(rules: JianfaRules, tier: int) -> tuple[int, int]:
    """第 tier 階下一季開局的起手資源（銀兩, 心得）：滿額乘那一階的成數、四捨五入；沒有階是 (0, 0)。"""
    t = rules.tiers
    share = t.start_shares.get(tier, 0.0)
    return round(t.start_silver * share), round(t.start_xinde * share)


def reward_text(rules: JianfaRules, tier: int) -> str:
    """結局卡「分到多少」（欄位表 main.ending.reward）：「下一季開局銀兩 150、心得 100」；沒有階是空字串。"""
    silver, xinde = start_grant(rules, tier)
    return REWARD_TIER.format(silver=silver, xinde=xinde) if tier else ""


def _share(share: float, n: int) -> int:
    return math.floor(share * n + _EPS)


def _cut(pool: list[tuple[str, int]], top_share: float | None, mid_share: float) -> dict[str, tuple[str, int, int]]:
    """一池過了門檻的人（名號, 分數）照名次切三段：前 top_share（無條件捨去、至少 1 人；None 是這一池沒有最上面那一段）、
    前 mid_share（累計，捨去）的其餘、其餘。同分同名次（比他高的人數＋1）、同一段。扣掉最上面那一段還有人時，中間那一段也至少
    一個名次（PM 2026-10-25 第 1 件：贏的那一軍 3 人是一、三、四，輸的那一軍只有 1 人是第三階）。回 名號 →（段, 名次, 池子人數）。"""
    n = len(pool)
    n_top = max(1, _share(top_share, n)) if top_share is not None and n else 0
    ascending = sorted(points for _, points in pool)
    ranks = {name: 1 + n - bisect.bisect_right(ascending, points) for name, points in pool}
    on_top = sum(1 for rank in ranks.values() if rank <= n_top)  # 同分的人一起進最上面那一段，可能多過 n_top
    n_mid = max(_share(mid_share, n), on_top + 1) if n > on_top else on_top
    return {name: (_TOP if rank <= n_top else _MID if rank <= n_mid else _REST, rank, n) for name, rank in ranks.items()}


def _results(
    members: list[PlayerState], scores: dict[str, int], books: dict[str, str], top_share: float | None,
    tiers: dict[str, int], faction: str, rules: JianfaRules,
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


def _army(members: list[PlayerState], faction: FactionDef, winner: str | None, rules: JianfaRules) -> dict[str, TierResult]:
    """兩軍之一：照 contrib 排；贏的那一軍 一 → 三 → 四，輸的（和局時兩軍都是）三 → 四。"""
    won = winner == faction.id
    scores = {p.name: p.contrib for p in members}
    books = {p.name: faction.id for p in members}
    tiers = {_TOP: 1, _MID: 3, _REST: 4}
    got = _results(members, scores, books, rules.tiers.tier1_share if won else None, tiers, faction.id, rules)
    return {p.name: got.get(p.name) or TierResult(points=scores[p.name]) for p in members}


def _gentry(members: list[PlayerState], faction: FactionDef, winner: str | None, rules: JianfaRules) -> dict[str, TierResult]:
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


def _settle(content: Content, players: list[PlayerState], winner: str | None, rules: JianfaRules) -> dict[str, TierResult]:
    out: dict[str, TierResult] = {}
    for faction in content.scenario.factions:
        members = [p for p in players if p.faction == faction.id]
        if members:
            out |= (_gentry if faction.allies else _army)(members, faction, winner, rules)
    return out


def settle(
    world: WorldState, content: Content, players: list[PlayerState], rules: JianfaRules | None = None,
) -> dict[str, TierResult]:
    """季末四階（設計 3.3；企劃者 2026-10-24 第 3、4 件）：投靠了劇本裡的陣營的人每人一筆（名號 → TierResult；沒到門檻是第 0 階），
    散人與劇本沒有的陣營不列。贏的那一軍看收季時的結局（winner_of）；和局兩軍都照輸的切、豪強照兩本合計。
    名次只在過了門檻的人裡排，人數照比例（20 人與 2,000 人同一條規則；細節見 _cut 與計畫 5.0 第 13 條）。"""
    return _settle(content, players, winner_of(world, content), rules or rules_of(content))


def _top_tier(p: PlayerState, content: Content, winner: str | None) -> int:
    """這個人那一池最高拿得到第幾階：贏的那一軍 1、豪強替贏的那一軍那一本 2，其餘（輸的、和局、豪強照另一本）3。"""
    if winner is not None and p.faction == winner:
        return 1
    if is_gentry(p, content) and winner in _allies(p, content):
        return 2
    return 3


def _book(p: PlayerState, book: str | None, content: Content) -> int:
    """排名次用的那個數：兩軍（book 是自己的陣營）是 contrib；豪強是那一本，和局（BOTH）是兩本合計。"""
    if not is_gentry(p, content):
        return p.contrib
    if book == BOTH:
        return sum(p.ledgers.get(side, 0) for side in _allies(p, content))
    return p.ledgers.get(book or "", 0)


def _raised(p: PlayerState, book: str | None, points: int, content: Content) -> PlayerState:
    """p 的一份複本，排名次用的那個數（_book）改成 points：兩軍改 contrib；豪強改那一本，和局的兩本合計把差額加在第一本。"""
    copy = p.model_copy(deep=True)
    if not is_gentry(p, content):
        copy.contrib = points
    elif book == BOTH:
        first = _allies(p, content)[0]
        copy.ledgers[first] = copy.ledgers.get(first, 0) + points - _book(p, BOTH, content)
    elif book is not None:
        copy.ledgers[book] = points
    return copy


def outlook(
    content: Content, players: list[PlayerState], name: str, winner: str | None, rules: JianfaRules | None = None,
) -> tuple[TierResult, int | None]:
    """此刻就收季（winner 照此刻會成立的結局）name 拿第幾階，與離上一階還差多少（已經是那一池最高、或怎麼加都升不上是 None；
    還沒到門檻是離門檻差多少）。只換自己的分數重排（二分搜尋：分數越高階只會越好），20 人與 2,000 人一樣快。"""
    r = rules or rules_of(content)
    me = next(p for p in players if p.name == name)
    members = [p for p in players if p.faction == me.faction]
    now = _settle(content, members, winner, r).get(name) or TierResult()
    if not now.tier:  # 還沒到門檻：離門檻差多少（豪強照替贏的那一軍那一本；和局照兩本合計，都是 now.points）
        return now, max(1, r.tiers.min_contribution - now.points)
    if now.tier <= _top_tier(me, content, winner):
        return now, None
    others = [p for p in members if p.name != name]

    def better(points: int) -> bool:
        tried = _settle(content, [*others, _raised(me, now.ledger_used, points, content)], winner, r)[name]
        return bool(tried.tier) and tried.tier < now.tier and tried.ledger_used == now.ledger_used

    scores = sorted({_book(p, now.ledger_used, content) for p in others})
    candidates = [s for s in scores if s > now.points] + [max([now.points, *scores]) + 1]
    lo, hi = 0, len(candidates) - 1
    if not better(candidates[hi]):
        return now, None
    while lo < hi:  # 第一個升得上去的分數
        mid = (lo + hi) // 2
        if better(candidates[mid]):
            hi = mid
        else:
            lo = mid + 1
    return now, candidates[lo] - now.points


def tier_hint(result: TierResult, gap: int | None) -> str:
    """欄位表 main.sides.tier_hint：「第三階・還差 40」（離上一階）、「第一階」（那一池最高）、「未入階・還差 20」（離門檻）。"""
    if not result.tier:
        return HINT_NONE.format(gap=gap or 0)
    name = TIER_NAMES[result.tier]
    return name if gap is None else HINT_GAP.format(tier=name, gap=gap)


def bars(content: Content) -> dict[str, tuple[int, str]]:
    """兩軍各自的「到幾分就贏」：第一季會提前收季的結局（rules.ends_early）裡，寫得成「這一方到幾分」（rules._one_bar）、而且是
    這一方贏的那幾種，取分數最低的（那一方 →（分數, 結局名，括號拿掉））。三方卡的「要做到」與最後一週「離贏還差多少」照它。"""
    from .rules import _one_bar, ends_early  # noqa: PLC0415  rules → wins：在函式裡 import，避免循環

    out: dict[str, tuple[int, str]] = {}
    for ending in content.scenario.endings:
        if not ending.season_one or ending.mandate or ending.winner is None or not ends_early(ending):
            continue
        bar = _one_bar(ending)
        if bar is not None and bar[0] == ending.winner and (ending.winner not in out or bar[1] < out[ending.winner][0]):
            out[ending.winner] = (bar[1], _short_title(ending))
    return out


def _short_title(ending: Ending) -> str:
    return re.sub(r"（[^）]*）", "", ending.title)


def _pct(share: float) -> int:
    return round(share * 100)


def gap_line(content: Content, standing: dict[str, int]) -> str:
    """最後一週「離贏還差多少」（設計 6.8；week_unlock.win_gap 的批 3c 那一句，本週卡與輿圖天下層寫同一句）：兩軍照劇本的順序，
    「官軍離「黃巾平定」還差 12，黃巾離「黃天當立」還差 28」；寫不出門檻的一方不寫，都寫不出是空字串。"""
    from .rules import STANCE_NAMES  # noqa: PLC0415  rules → wins：在函式裡 import，避免循環

    b = bars(content)
    parts = [
        GAP_PART.format(side=STANCE_NAMES.get(f.id, f.name), ending=b[f.id][1], gap=max(0, b[f.id][0] - standing.get(f.id, 0)))
        for f in content.scenario.factions if f.id in b
    ]
    return "，".join(parts)


def goal_text(content: Content, faction: FactionDef) -> str:
    """三方卡「要做到」（設計 3.4）：兩軍是態勢高過對面、到門檻就贏；豪強是挑一軍幫。"""
    if len(faction.allies) >= 2:
        a, b = (content.scenario.faction_name(side, side) for side in faction.allies[:2])
        return GOAL_GENTRY.format(a=a, b=b)
    if faction.allies:
        return GOAL_GENTRY_PLAIN
    other = next((f for f in content.scenario.factions if not f.allies and f.id != faction.id), None)
    other_name = other.name if other is not None else ""
    bar = bars(content).get(faction.id)
    if bar is None:
        return GOAL_ARMY_PLAIN.format(side=faction.name, other=other_name)
    return GOAL_ARMY.format(side=faction.name, other=other_name, bar=bar[0], ending=bar[1])


def reward_card(content: Content, faction: FactionDef, rules: JianfaRules | None = None) -> str:
    """三方卡「贏了給」：稱號照 tiers.titles，比例與門檻照 tiers（字待 joy 潤）；起手資源各階另見 reward_text。"""
    r = rules or rules_of(content)
    t = r.tiers
    names = {tier: title_of(r, tier, faction.id) for tier in (1, 2, 3, 4)}
    common = {"p3": _pct(t.tier3_share), "floor": t.min_contribution, "t3": TIER_NAMES[3], "t4": TIER_NAMES[4],
              "n3": names[3], "n4": names[4]}
    if faction.allies:
        return REWARD_GENTRY.format(p2=_pct(t.tier2_share), t2=TIER_NAMES[2], n2=names[2], **common)
    return REWARD_ARMY.format(p1=_pct(t.tier1_share), t1=TIER_NAMES[1], n1=names[1], **common)


def chronicle_lines(content: Content, results: dict[str, TierResult]) -> list[str]:
    """季末論功寫進江湖史的幾行（設計 3.3：第一、二階江湖史留名）：一個陣營、一階一行，名號照名次（同名次照名號）。"""
    lines = []
    for faction in content.scenario.factions:
        for tier in (1, 2):
            rows = sorted((r.rank, name, r.title) for name, r in results.items() if r.tier == tier and _faction_of(r, faction))
            if rows:
                lines.append(CHRONICLE_TIER.format(
                    faction=faction.name, tier=TIER_NAMES[tier], title=rows[0][2], names="、".join(name for _, name, _ in rows),
                ))
    return lines


def _faction_of(result: TierResult, faction: FactionDef) -> bool:
    """這一筆是不是這個陣營的人：一階只給兩軍（帳是自己的陣營），二階只給豪強（帳是它能幫的一軍）。"""
    if result.tier == 1:
        return result.ledger_used == faction.id
    return bool(faction.allies) and result.ledger_used in faction.allies


def condition_of(content: Content, faction_id: str | None, result: TierResult | None) -> str | None:
    """結局卡「你算在哪一條」（欄位表 main.ending.condition）：兩軍是陣營名；豪強是「地方豪強（官軍）」（照排名次的那一本；
    和局兩本合計寫「地方豪強」）。散人、劇本沒有的陣營、豪強沒有階是 None。"""
    faction = content.scenario.find_faction(faction_id)
    if faction is None:
        return None
    if not faction.allies:
        return faction.name
    if result is None or not result.tier:
        return None
    if result.ledger_used == BOTH or result.ledger_used is None:
        return faction.name
    return f"{faction.name}（{content.scenario.faction_name(result.ledger_used, result.ledger_used)}）"


def check(content: Content, rules: JianfaRules) -> list[str]:
    """數字對得上劇本嗎（content.validate 在四勝利開著時叫）：豪強每個投靠點都有預設、預設是那個豪強能幫的那一軍、沒有寫到別的地點。"""
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
