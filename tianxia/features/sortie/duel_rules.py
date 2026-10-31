"""減法季的出陣約戰（整合設計 4.3；計畫 docs/superpowers/plans/2026-10-24-減法季-主機側實作計畫.md 第四節 Task 3b-1、4.0 之二）。
功能包 tianxia/features/sortie/ 的純規則（原 tianxia/sortie_duel.py，那個名字留成指到這裡的別名；主動搬六包第 2 批）。

只在 rules.jianfa(content, world, "sortie_duel") 開著的季用；這裡是純規則，不 import engine、不讀電腦時鐘（時刻一律是傳進來的現實秒，
Game.now），不碰 Game.rng。

- 貼約戰（open）：在推得動的塊按出陣、封好三招（Config.sortie.moves：強攻、固守、奇襲、撤退），一張卡掛 window_minutes。
- 應戰（answer）：對面陣營、站在那一塊所在的大區、還有應戰次數與體力的人，先按的那一位是守方，也封好三招；第二位回「已有人應戰」。
  同陣營的人不能應戰，只能同去（join，記進 attacker.allies；集火由接線那一批照 conquest.focus_bonus 算）。
- 到時（due → advance）：窗滿才結算。沒有真人應戰時由呼叫端給的這一邊的人補位（bot_answer：同一區的優先，沒有就任一個「趕來」，
  應戰時刻記在窗內隨機）；連補位的人都沒有才由貼的那一刻抄好的駐軍迎戰（garrison）；連駐軍都沒有記成 void。卡與戰報一律只寫名號，
  不分真人、補位；守軍寫 GARRISON。季已經結束時還沒打的記成 void；暫停中不推。結算過的跳過（只往前走），兩個程式輪流推不會重複結算。
- 三回合（resolve）：每回合攻方威力 ×（1 ＋ counter_swing × 相剋）對守方威力，照 encounter.resolve_encounter 判一次（每回合都擲一次，
  撤退的回合也擲）；撤退＝這一回合認輸、扣的氣血打 retreat_toll 折。三勝大勝、兩勝勝、一勝或平（三回合全僵持）僵持、零勝敗（攻方的角度）。
- 亂數：每一場自己一份 random.Random(f"約戰|{id}|{opened_at}")（rng_for）：補位挑誰、守軍與補位的招、三回合的運氣都從它取，誰觸發結果都一樣。
推多少、戰利、貢獻、內傷、冷卻、戰報與送達是接線那一批（這一包的 duel_actions，原本在 engine）照 SortieDuel.result 做；這裡只給
cooldown_after、side_tier 這幾樣讀法。
"""
from __future__ import annotations

import math
import random
from collections.abc import Callable
from typing import NamedTuple

from tianxia import conquest  # 過渡：待搬（地盤：推不推得動、自家的塊）
from tianxia import encounter  # 過渡：待搬（單次判定：三回合每回合一次）
from tianxia import tactics  # 過渡：待搬（戰法：三招的相剋）
from tianxia.characters import name_key
from tianxia.models import MOVES, Content, SortieRules
from tianxia.state import PlayerState, WorldState
from tianxia.world_state import SharedWorldState, SortieDuel, SortieResult, SortieRound, SortieSide

from . import rules as sortie  # 出陣的規則（同一包；原本 from tianxia import sortie）

ROUNDS = 3
RETREAT = "撤退"
TIER_WORDS = {"big": "大勝", "win": "險勝", "draw": "僵持", "lose": "落敗"}  # 給戰報那一格（battlelog 認得的四種）
GARRISON = "守軍"  # 守軍迎戰時卡上寫的應戰者（待 joy 潤）
LABEL = "約戰"  # 戰報上寫的種類（BattleRecord.label；kind 照舊是 sortie：Literal 加值舊程式讀不進新存檔，計畫 4.0 之三第 4 條）
_WON = encounter.TIERS[:2]  # 大勝、險勝：攻方贏了這一回合

# 灰掉的原因（卡上、鈕上那一句）。待 joy 潤
WHY_ROAD = "在路上，到了再說"
WHY_COOL = "還要 {n} 分"
WHY_WAIT = "等對面來約"  # 自家的塊沒人約戰時（設計 4.3【PM】）
WHY_TIRED = "體力不足（要 {n}）"
WHY_MOVES = "要封三招：{moves}"
WHY_RANGER = "散人不能應戰"
WHY_OVER = "這一場約戰已經結束了"
WHY_TAKEN = "已有人應戰"
WHY_YOU = "你已應戰"
WHY_MINE = "這是你自己約的戰"
WHY_ALLY = "同袍約戰，只能同去"
WHY_FAR = "在{region}才應得了戰"
WHY_ANSWERS = "今日應戰 {n} 次已用完"
WHY_JOINED = "已經同去了"
WHY_NOT_ALLY = "不是同袍的約戰"
WHY_GONE = "這一場約戰已經不在了"
WHY_NOT_BLOCK = "這裡不在爭奪之列"
WHY_RESTING = "休季中"

# ── 接線（減法季批 3b-2） ──
# 三個動作的選項 id（不在選單上，Game.choose 最前面接走）：sortie:go:<三招>、sortie:answer:<約戰 id>:<三招>、sortie:join:<約戰 id>
PREFIX = "sortie:"
# 下面的字都待 joy 潤
# 出陣那一格（act:train）在約戰開著時只是打開出陣前那張卡（main.sortie_card），按了不花體力、不寫紀錄（同探索的入口）
PICK = "（封好三招再出陣：從強攻、固守、奇襲、撤退裡挑三招，一回合一招。）"
GO_TITLE = "約戰・{place}"  # 貼、應、同去、結算的江湖紀錄同一個標題
GO_LINE = "你在{place}替{side}貼出約戰，封好三招：{moves}。{window} 分鐘內對面的人可以來應戰；窗滿就開打，打完戰報送到。"
ANSWER_LINE = "你應下{rival}在{place}的約戰，替{side}封好三招：{moves}。窗滿就開打，打完戰報送到。"
JOIN_LINE = "你跟{rival}同去{place}，替{side}一起推這一塊（同去算集火）。窗滿就開打。"
VOID_LINE = "{place}的約戰沒打成，出陣（應戰）的次數與體力退回。"
VS_LINE = "{attacker}約戰，{defender}應戰。"  # 補位的人跟真人一樣只寫名號（不寫假人、不寫「沒有人防守」）
VS_GARRISON = "{attacker}約戰，" + GARRISON + "迎戰。"  # 回合、對面那一行、戰報的對手、行狀、約戰卡都只寫「守軍」，不寫駐軍那一路的名字（QA 順帶）
VS_ALLIES = "同去：{names}。"
ROUND_LINE = "第{n}回合　{attacker}{a_move}，{defender}{d_move}：{verdict}"
ROUND_TOP = "{name}佔上風"
ROUND_EVEN = "不分上下"
ROUND_BACK = "{name}撤退"
TALLY_LINE = "三回合 {wins} 勝 {losses} 負 {draws} 平（{attacker}的角度）。"
MOVE_LINES = {  # 這一塊怎麼動（一句話，不寫數字）
    "big": "{side}在{place}大步推進。",
    "win": "{side}在{place}推進了一截。",
    "draw": "{side}在{place}只推進了一點。",
    "pull": "{place}守住了，{side}的進度被拉回。",
    "hold": "{place}守住了。",
}
MOVE_FLIP = "{place}被推滿，落入{side}之手！"
MOVE_STILL = "{place}此刻推不動（{why}），這一場只打了仗。"
GAP_LINE = "{side}在{place}的進度 {value}／100，離易手還差 {left}。"
GAP_DONE = "{side}在{place}的進度歸零了。"
RANK_LINE = "離升下一階還差 {n} 貢獻。"
LOSE_LINE = "這一場輸了：內傷加重，下一次出陣與應戰多等 {n} 分。"
NEXT_LINE = "下一次出陣：{sortie}；應戰：{answer}。"
NEXT_NOW = "隨時"
NEXT_LATER = "{n} 分後"
NEXT_DONE = "今日已用完"
CONVOY_LINE = "這週截糧的運糧隊正打{place}經過：在那裡按出陣就是去截糧。"
CONVOY_NAME = "截糧"  # 運糧隊經過時出陣那一格的名字（「出陣・截糧」）
LOOT_LINE = "經驗 {exp}・心得 {xinde}・銀兩 {silver}"  # 出陣前那張卡「贏了」那一段的戰利
ANNAL_LINE = "在{place}約戰{rival}，{tier}。"  # 行狀（annals.DUEL）：下戰書的攻方
# 應戰的人（含補位的）另一句（FB-897；待 joy 潤）：同一句的話，列傳補了主詞之後守方的傳讀起來像他下的戰書。名字不叫 ANSWER_LINE：那是約戰卡「你應下…」那一句
ANNAL_ANSWER_LINE = "應下{rival}在{place}的約戰，{tier}。"  # 行狀（annals.DUEL）：應戰的守方


# 出陣那一格灰著時格子裡的小字：五格、四格時每格只放得下四個字（FB-670，tests/web/test_jianghu_page_web.py 守）；整句在行動列底下那一行
# （howto.duel_line，網頁點灰格浮出那一句）與約戰卡的 why_not。散人、今天用完照舊給原句（網頁自己換成「未投靠」「今日已滿」）。待 joy 潤
CELL_WAIT = "等對面約"
CELL_COOL = "冷卻中"
CELL_STUCK = "推不動"


def cell_note(why: str) -> str:
    """貼不了約戰的原因（open_problem 那一句）換成格子裡放得下的小字（cell_note）。"""
    if why == WHY_WAIT:
        return CELL_WAIT
    if why.startswith(WHY_COOL.partition("{")[0]):
        return CELL_COOL
    if why == sortie.RANGER_NOTE or why.startswith(sortie.USED_UP.partition("{")[0]):
        return why
    return CELL_STUCK


def on(content: Content, world: WorldState | None) -> bool:
    """約戰在這一季開著：減法季的 sortie_duel 子開關（rules.jianfa：設定＋開季的章）、出陣開著、領地爭奪在這一季生效（約戰貼在區塊上）。"""
    from tianxia import rules  # noqa: PLC0415  rules → … → conquest：延後 import，免得載入時繞成環（核心的 tianxia.rules，不是包裡的出陣 rules）

    return rules.jianfa(content, world, "sortie_duel") and sortie.on(content) and conquest.on(content, world)


def progress_scale(content: Content) -> float:
    """約戰推（拉）進度的倍數：Config.sortie.duel_progress_scale，沒設照 Config.conquest.progress_scale。"""
    own = content.config.sortie.duel_progress_scale
    return content.config.conquest.progress_scale if own is None else own


def parse_moves(moves) -> list[str]:
    """網頁、選項 id 送來的三招：清單，或「強攻,固守,奇襲」（逗號、頓號、空白都算分隔）。不認得的字照留（moves_problem 擋）。"""
    if isinstance(moves, (list, tuple)):
        return [str(m).strip() for m in moves if str(m).strip()]
    text = str(moves or "")
    for sep in ("、", "，", " "):
        text = text.replace(sep, ",")
    return [m.strip() for m in text.split(",") if m.strip()]


def left_today(p: PlayerState, cfg: SortieRules, today: int) -> int:
    """約戰開著的季今天還能出陣（貼或同去）幾次：jianfa_per_day 減今天用掉的（sortie_day／sorties_today，同 sortie.left_today 的帳）。"""
    return max(0, cfg.jianfa_per_day - (p.sorties_today if p.sortie_day == today else 0))


def answers_left(p: PlayerState, cfg: SortieRules, today: int) -> int:
    """今天還能應戰幾次（answer_per_day，跟出陣分開算；answer_day／answers_today）。"""
    return max(0, cfg.answer_per_day - (p.answers_today if p.answer_day == today else 0))


def spend_answer(p: PlayerState, today: int, n: int = 1) -> None:
    """記今天應戰了（n 是 −1 時是退一次：作廢；只退今天的）。"""
    if n < 0 and p.answer_day != today:
        return
    p.answers_today = max(0, (p.answers_today if p.answer_day == today else 0) + n)
    p.answer_day = today


def cooling(until: float | None, now: float) -> bool:
    return until is not None and now < until


def minutes_text(until: float | None, now: float) -> str:
    """下一次什麼時候（戰報那一行）：還在冷卻寫「N 分後」，不然「隨時」。"""
    return NEXT_LATER.format(n=_minutes_left(until, now)) if cooling(until, now) else NEXT_NOW


def round_lines(duel: SortieDuel) -> list[str]:
    """三回合各一行（戰報的「過程」）：兩邊的名號（守軍寫 GARRISON）、出的招、誰佔上風。"""
    result, d = duel.result, duel.defender
    if result is None or d is None:
        return []
    a_name, d_name = duel.attacker.name, GARRISON if d.garrison else d.name
    out = []
    for n, r in enumerate(result.rounds, 1):
        if r.attacker_move == RETREAT and r.defender_move == RETREAT:
            verdict = ROUND_EVEN
        elif r.attacker_move == RETREAT:
            verdict = ROUND_BACK.format(name=a_name)
        elif r.defender_move == RETREAT:
            verdict = ROUND_BACK.format(name=d_name)
        else:
            verdict = {"attacker": ROUND_TOP.format(name=a_name), "defender": ROUND_TOP.format(name=d_name), "draw": ROUND_EVEN}[r.winner]
        out.append(ROUND_LINE.format(n=n, attacker=a_name, a_move=r.attacker_move, defender=d_name, d_move=r.defender_move, verdict=verdict))
    return out


def vs_line(duel: SortieDuel) -> str:
    """對面是誰（戰報、紀錄）：補位的人跟真人一樣寫「某某應戰」；連補位都沒有寫「守軍迎戰」。"""
    d = duel.defender
    if d is not None and d.garrison:
        return VS_GARRISON.format(attacker=duel.attacker.name)
    return VS_LINE.format(attacker=duel.attacker.name, defender=d.name if d is not None else GARRISON)


def scale_of(duel: SortieDuel, cfg: SortieRules) -> tuple[str, float]:
    """這一場推（拉）的方向與倍率：攻方大勝、勝、僵持是（"push", result_scale[tier]）；攻方敗是（"pull", result_scale[defender_tier]）。"""
    result = duel.result
    if result is None:
        return "push", 0.0
    if result.tier == "lose":
        return "pull", cfg.result_scale[result.defender_tier]
    return "push", cfg.result_scale[result.tier]


class Cooldown(NamedTuple):
    """一場約戰讓這個人冷卻到什麼時候（現實秒；None 是這一場不讓他冷卻）：下一次出陣、下一次應戰各一個。"""

    sortie: float | None
    answer: float | None


def rng_for(duel: SortieDuel) -> random.Random:
    return random.Random(f"約戰|{duel.id}|{duel.opened_at}")


def _minutes_left(until: float, now: float) -> int:
    return math.ceil((until - now) / 60)


def _over(duel: SortieDuel, now: float) -> bool:
    return duel.status not in ("open", "answered") or now >= duel.expires_at


def _same(a: str, b: str) -> bool:
    return name_key(a) == name_key(b)


def moves_problem(cfg: SortieRules, moves: list[str]) -> str | None:
    """封的三招合不合法：剛好三招、每一招都在 Config.sortie.moves 裡（沒有放手一搏）。"""
    if len(moves) != ROUNDS or any(m not in cfg.moves for m in moves):
        return WHY_MOVES.format(moves="、".join(cfg.moves))
    return None


def open_problem(
    cfg: SortieRules, now: float, *, side: str | None, left: int, cooldown_until: float | None, block_why: str | None,
    stamina: float, traveling: bool = False,
) -> str | None:
    """貼約戰不成的原因（成是 None）：散人、在路上、今天的次數（jianfa_per_day）、冷卻（上一次貼的冷卻、輸了多的那一截）、
    這一塊推不動（block_why＝conquest.push_problem(..., "attack")；自家的塊寫「等對面來約」）、體力（jianfa_stamina）。"""
    if side is None:
        return sortie.RANGER_NOTE
    if traveling:
        return WHY_ROAD
    if left <= 0:
        return sortie.USED_UP.format(n=cfg.jianfa_per_day)
    if cooldown_until is not None and now < cooldown_until:
        return WHY_COOL.format(n=_minutes_left(cooldown_until, now))
    if block_why is not None:
        return WHY_WAIT if block_why == conquest.WHY_OWN else block_why
    if stamina < cfg.jianfa_stamina:
        return WHY_TIRED.format(n=cfg.jianfa_stamina)
    return None


def open(  # noqa: A001  計畫的介面名（sortie_duel.open）
    shared: SharedWorldState, *, id: str, block: str, region: str | None, place: str, region_name: str, attacker: SortieSide,  # noqa: A002
    now: float, cfg: SortieRules, garrison: SortieSide | None = None,
) -> SortieDuel:
    """貼一張約戰（呼叫端先看過 open_problem、moves_problem）：攻方的快照抄一份（封招時刻＝now），窗開到 now ＋ window_minutes。
    garrison 是這一塊此刻的駐軍抄成的一方（到時連補位的人都沒有才用）。同一個 id 不能貼兩次。"""
    if id in shared.sorties:
        raise ValueError(f"約戰 {id} 已經貼過了")
    duel = SortieDuel(
        id=id, block=block, region=region, place=place, region_name=region_name,
        attacker=attacker.model_copy(update={"sealed_at": now}, deep=True),
        garrison=garrison.model_copy(update={"garrison": True}, deep=True) if garrison is not None else None,
        opened_at=now, expires_at=now + cfg.window_minutes * 60,
    )
    shared.sorties[id] = duel
    return duel


def answer_problem(
    cfg: SortieRules, duel: SortieDuel, now: float, *, name: str, side: str | None, region: str | None, answers_left: int,
    stamina: float, cooldown_until: float | None = None, traveling: bool = False,
) -> str | None:
    """這個人應這一張約戰不成的原因（成是 None）：窗過了或結算了、已經有人應了（自己應的寫「你已應戰」）、是自己貼的、散人、同陣營
    （只能同去）、在路上、不在那一塊所在的大區（地圖沒有大區不限）、今天的應戰次數（answer_per_day，跟出陣分開算）、輸了的冷卻、
    體力（answer_stamina）。應戰本身沒有冷卻。"""
    if _over(duel, now):
        return WHY_OVER
    if duel.status == "answered":
        return WHY_YOU if duel.defender is not None and _same(name, duel.defender.name) else WHY_TAKEN
    if _same(name, duel.attacker.name):
        return WHY_MINE
    if side is None:
        return WHY_RANGER
    if side == duel.attacker.side:
        return WHY_ALLY
    if traveling:
        return WHY_ROAD
    if duel.region is not None and region != duel.region:
        return WHY_FAR.format(region=duel.region_name or duel.region)
    if answers_left <= 0:
        return WHY_ANSWERS.format(n=cfg.answer_per_day)
    if cooldown_until is not None and now < cooldown_until:
        return WHY_COOL.format(n=_minutes_left(cooldown_until, now))
    if stamina < cfg.answer_stamina:
        return WHY_TIRED.format(n=cfg.answer_stamina)
    return None


def answer(duel: SortieDuel, defender: SortieSide, now: float) -> None:
    """應戰（呼叫端在同一次寫入裡先看過 answer_problem，先按的那一位才進得來）：守方的快照抄一份，封招時刻＝now。"""
    duel.defender = defender.model_copy(update={"sealed_at": now, "garrison": False}, deep=True)
    duel.status = "answered"


def join_problem(duel: SortieDuel, now: float, *, name: str, side: str | None) -> str | None:
    """同去不成的原因（成是 None）：窗過了或結算了、是自己貼的、不是同陣營、已經同去了。"""
    if _over(duel, now):
        return WHY_OVER
    if _same(name, duel.attacker.name):
        return WHY_MINE
    if side is None or side != duel.attacker.side:
        return WHY_NOT_ALLY
    if any(_same(name, n) for n in duel.attacker.allies):
        return WHY_JOINED
    return None


def join(duel: SortieDuel, name: str) -> None:
    """同袍同去（集火）：記進 attacker.allies（重按不重記、自己不記）。"""
    if _same(name, duel.attacker.name) or any(_same(name, n) for n in duel.attacker.allies):
        return
    duel.attacker.allies.append(name)


def due(duel: SortieDuel, now: float) -> bool:
    """該結算了：還沒結算、窗滿了（提早應戰也等窗滿）。"""
    return duel.status in ("open", "answered") and now >= duel.expires_at


def _valid(moves: list[str]) -> bool:
    return len(moves) == ROUNDS and all(m in MOVES or m == RETREAT for m in moves)


def _filled(side: SortieSide, rng: random.Random) -> list[str]:
    """這一方封的三招；沒封（守軍、補位的人沒給）就從現有的三招裡挑三招（不挑撤退）。"""
    return list(side.moves) if _valid(side.moves) else [rng.choice(MOVES) for _ in range(ROUNDS)]


def bot_answer(duel: SortieDuel, candidates: list[SortieSide], rng: random.Random) -> SortieSide | None:
    """到時沒有真人應戰：從 candidates（呼叫端給的這一邊能應戰的人）挑一個補位——不是攻方那一邊、不是攻方與同去的人、不是守軍；
    站在那一塊所在大區的優先，沒有就任一個「趕來」。回抄好的一份（招沒封就照這一場的亂數挑三招、應戰時刻在窗內隨機），不改 duel；
    沒有人是 None。"""
    taken = {name_key(duel.attacker.name), *(name_key(n) for n in duel.attacker.allies)}
    pool = [c for c in candidates
            if c.side and c.side != duel.attacker.side and not c.garrison and name_key(c.name) not in taken]
    if not pool:
        return None
    near = [c for c in pool if duel.region is not None and c.region == duel.region]
    pick = rng.choice(sorted(near or pool, key=lambda c: name_key(c.name)))
    moves = _filled(pick, rng)
    at = duel.opened_at + rng.uniform(0.0, max(0.0, duel.expires_at - duel.opened_at))
    return pick.model_copy(update={"moves": moves, "sealed_at": at, "garrison": False}, deep=True)


def total_tier(wins: int, losses: int) -> str:
    """三回合的總帳（攻方的角度）：三勝大勝、兩勝勝、一勝或平（勝負都沒有：三回合全僵持）僵持、其餘敗。"""
    if wins >= ROUNDS:
        return "big"
    if wins == 2:
        return "win"
    if wins == 1 or losses == 0:
        return "draw"
    return "lose"


def defender_tier(tier: str, losses: int) -> str:
    """守方那一份：攻方大勝或勝是守方敗、僵持一樣僵持；攻方敗時守方照贏的回合數（攻方輸的回合）——三回合全贏 big、其餘 win。"""
    if tier in ("big", "win"):
        return "lose"
    if tier == "draw":
        return "draw"
    return "big" if losses >= ROUNDS else "win"


def _round(a_move: str, d_move: str, a_power: float, d_power: float, cfg: SortieRules, rng: random.Random) -> SortieRound:
    a_back, d_back = a_move == RETREAT, d_move == RETREAT
    beat = 0 if a_back or d_back else tactics.counter(a_move, d_move)
    power = a_power * (1 + cfg.counter_swing * beat)
    roll = encounter.resolve_encounter(power, d_power, rng)  # 每一回合都擲：換一招不讓後面的回合的運氣位移
    if a_back and d_back:
        winner = "draw"
    elif a_back:
        winner = "defender"
    elif d_back:
        winner = "attacker"
    else:
        winner = "attacker" if roll.tier in _WON else "defender" if roll.tier == encounter.FALLBACK_TIER else "draw"
    mine = {"attacker": "win", "defender": "lose", "draw": "draw"}[winner]
    theirs = {"attacker": "lose", "defender": "win", "draw": "draw"}[winner]
    return SortieRound(
        attacker_move=a_move, defender_move=d_move, beat=beat, power=power, tier=roll.tier, winner=winner,
        attacker_toll=cfg.round_toll[mine] * (cfg.retreat_toll if a_back else 1.0),
        defender_toll=cfg.round_toll[theirs] * (cfg.retreat_toll if d_back else 1.0),
    )


def resolve(duel: SortieDuel, cfg: SortieRules, rng: random.Random) -> SortieResult:
    """三回合（呼叫端給的 rng 一般是 rng_for(duel)）：每回合一招對一招，照 _round 判；回總帳。要有守方。"""
    a, d = duel.attacker, duel.defender
    if d is None:
        raise ValueError(f"約戰 {duel.id} 沒有守方，不能結算")
    a_moves, d_moves = (list(a.moves) if _valid(a.moves) else ["固守"] * ROUNDS), (list(d.moves) if _valid(d.moves) else ["固守"] * ROUNDS)
    rounds = [_round(a_moves[i], d_moves[i], a.power, d.power, cfg, rng) for i in range(ROUNDS)]
    wins = sum(r.winner == "attacker" for r in rounds)
    losses = sum(r.winner == "defender" for r in rounds)
    tier = total_tier(wins, losses)
    return SortieResult(
        wins=wins, losses=losses, draws=ROUNDS - wins - losses, tier=tier, defender_tier=defender_tier(tier, losses), rounds=rounds,
        attacker_toll=sum(r.attacker_toll for r in rounds), defender_toll=sum(r.defender_toll for r in rounds),
    )


def prune(shared: SharedWorldState, cfg: SortieRules, now: float) -> None:
    """結算完（或作廢）超過 keep_hours 的拿掉。"""
    keep = cfg.keep_hours * 3600
    shared.sorties = {
        key: duel for key, duel in shared.sorties.items()
        if duel.status in ("open", "answered") or duel.settled_at is None or now - duel.settled_at < keep
    }


def advance(
    shared: SharedWorldState, cfg: SortieRules, now: float, candidates_for: Callable[[SortieDuel], list[SortieSide]],
) -> list[SortieDuel]:
    """把約戰推到 now（伺服器排程、任何人同步都可以叫；只往前走）：暫停中什麼都不做；季已經結束，還沒打的記成 void；窗滿的照開的先後
    一張一張結算——沒人應戰先補位（candidates_for(duel) 給這一邊能應戰的人，bot_answer），再沒有用駐軍，連駐軍都沒有記成 void；
    結算過、作廢過的不再碰。最後清掉留夠久的（prune）。回這一下結算或作廢的那幾張（status 分得出來）。"""
    if shared.paused_at is not None:
        return []
    done: list[SortieDuel] = []
    for duel in sorted(shared.sorties.values(), key=lambda d: (d.opened_at, d.id)):
        if duel.status not in ("open", "answered"):
            continue
        if shared.season.ended:
            duel.status, duel.settled_at = "void", now
            done.append(duel)
            continue
        if not due(duel, now):
            continue
        rng = rng_for(duel)
        if duel.defender is None:
            duel.defender = bot_answer(duel, candidates_for(duel), rng)
        if duel.defender is None and duel.garrison is not None:
            duel.defender = duel.garrison.model_copy(
                update={"moves": _filled(duel.garrison, rng), "sealed_at": duel.expires_at, "garrison": True}, deep=True)
        if duel.defender is None:
            duel.status, duel.settled_at = "void", now
            done.append(duel)
            continue
        duel.result = resolve(duel, cfg, rng)
        duel.status, duel.settled_at = "settled", now
        done.append(duel)
    prune(shared, cfg, now)
    return done


def cooldown_after(duel: SortieDuel, name: str, cfg: SortieRules) -> Cooldown:
    """這一場讓這個人冷卻到什麼時候（接線那一批跟存檔裡的取大）：攻方下一次出陣在貼的那一刻 ＋ cooldown_minutes，輸了再加 lose_cooldown，
    輸了連應戰也要等到結算 ＋ lose_cooldown；守方輸了出陣與應戰都等到結算 ＋ lose_cooldown（應戰本來沒有冷卻）；其餘不冷卻。"""
    hour, penalty = cfg.cooldown_minutes * 60, cfg.lose_cooldown_minutes * 60
    result, done = duel.result, duel.settled_at
    if _same(name, duel.attacker.name):
        base = duel.opened_at + hour
        if result is not None and done is not None and result.tier == "lose":
            return Cooldown(base + penalty, done + penalty)
        return Cooldown(base, None)
    d = duel.defender
    if d is not None and not d.garrison and _same(name, d.name) and result is not None and done is not None:
        if result.defender_tier == "lose":
            return Cooldown(done + penalty, done + penalty)
    return Cooldown(None, None)


def side_tier(duel: SortieDuel, name: str) -> str | None:
    """這個人看這一場的結果（給戰報那一格：大勝、險勝、僵持、落敗）：攻方與同去的照攻方、守方照守方；沒結算、不相干是 None。"""
    result = duel.result
    if result is None:
        return None
    if _same(name, duel.attacker.name) or any(_same(name, n) for n in duel.attacker.allies):
        return TIER_WORDS[result.tier]
    if duel.defender is not None and _same(name, duel.defender.name):
        return TIER_WORDS[result.defender_tier]
    return None


def card(
    duel: SortieDuel, viewer_name: str, viewer_side: str | None, viewer_region: str | None, now: float, cfg: SortieRules, *,
    answers_left: int = 0, stamina: float = 0.0, cooldown_until: float | None = None, traveling: bool = False,
    travel_minutes: int | None = None,
) -> dict:
    """約戰卡（計畫 1.3 欄位表 main.sorties 那一列）：role 是 mine（自己貼的）、join（同袍：鈕是同去）、answer（對面：鈕是應戰）；
    can_answer／can_join 是那一顆鈕按不按得下去，why_not 是灰著的原因；travel_minutes 由呼叫端算好（同一區時是 None）。
    只寫名號：補位的人跟真人一樣，守軍寫 GARRISON。"""
    if _same(viewer_name, duel.attacker.name):
        role, why = "mine", ""
    elif viewer_side is not None and viewer_side == duel.attacker.side:
        role, why = "join", join_problem(duel, now, name=viewer_name, side=viewer_side) or ""
    else:
        role = "answer"
        why = answer_problem(cfg, duel, now, name=viewer_name, side=viewer_side, region=viewer_region, answers_left=answers_left,
                             stamina=stamina, cooldown_until=cooldown_until, traveling=traveling) or ""
    same = duel.region is None or viewer_region == duel.region
    d = duel.defender
    return {
        "id": duel.id, "block": duel.block, "place": duel.place, "attacker": duel.attacker.name, "attacker_side": duel.attacker.side,
        "defender": None if d is None else GARRISON if d.garrison else d.name,
        "expires_in": max(0, int(duel.expires_at - now)) if duel.status in ("open", "answered") else 0,
        "status": duel.status, "role": role,
        "can_answer": role == "answer" and not why, "can_join": role == "join" and not why, "why_not": why,
        "answers_left": answers_left, "same_region": same, "travel_minutes": None if same else travel_minutes,
    }
