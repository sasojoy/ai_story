"""假人的共用層（第二輪第 89 批，從 bot_policy、bot 搬來；舊名 re-export 同一批物件）：出陣、探索、挑戰本人、移動幾包的 bots.py 都要讀的那一半，
放進哪一包都會變成包 import 包，留在假人殼（bot_policy、bot、bot_runner、server_bots）又得在函式裡跳回去。判準：照遞移的讀法，兩包以上讀的在這裡，一包讀的進那一包。

- 分數常數：TREND_WEIGHT、ORDER_SCORE、PRACTICE_SCORE、BOUNTY_SCORE。
- 敵我與目標：_side、_goals。
- 內傷：CLINIC_MIN_SILVER、CLINIC_URGENT、can_pay_clinic、injury_share、_crippled（醫館那幾個門檻的 CLINIC_AT、clinic_hop 只有移動讀，在 features/travel/bots.py）。
- 出陣的值：_duel_value、_train_value、_cannot_push、_outmatched、_sortie_win、SORTIE_WIN、SORTIE_WIN_FLOOR。
- 懸賞：_bounty_here（讀核心 core/bounty_base，不讀懸賞榜包）。
- 素材留多少（第二輪第 101 批，從 bot 搬來；鐵匠鋪與捐軍備都讀）：TRADE_KEEP、TRADE_MOVES、trade_keep。
- 取名的單子（第二輪第 101 批，從 bot_policy 搬來；煉製、修練、有所感、玩家互動四包開單，bot_runner 接）：NO_NAME、ForgeJob、MasterJob、SenseJob、DiscussJob、EpiphanyJob、NamingSlot。
- 下一站（第二輪第 101 批，從移動包搬來；移動、決戰、陣營都讀）：next_hop。
- 一次 pick 的快取：_TURN、_turn_cached、turn_cache。**_TURN 只有這一份**，bot_policy 不留這個名字；殼碰不得私有成員（邊界測試 test_the_bot_shell_touches_nothing_private_on_the_game），
  所以 bot_policy.pick 走公開的 turn_cache。

**包讀這裡一律 `from tianxia import bot_base`、叫的那一下寫 `bot_base.X`**：測試與 same_behavior 換 bot_base 的屬性，寫 from ... import 就換不到了。這一層跟別的共用層一樣不 import 包、不 import 殼，
函式裡也不行；Game 只放型別註記。_sortie_win 問 Game._sortie_foes（服務清單上有；出陣包 actions.sortie_foes 掛在 Game 上的同一個函式）。

另外跑：改這一份 scripts/test_for.py 只挑自己檔名（tests/bots/test_bot_base.py）、煙霧與邊界，挑不到的是讀它的那幾包與舊名：
tianxia/features/{travel,sortie,explore,figure_acts,battle,faction,smithy,outlets,stamina_plays,peers,craft,cultivation,sense}/tests、tests/bots、tests/acts/test_clinic.py、test_conquest_flip.py、test_conquest_rules.py、tests/battle/test_fronts.py、
tests/figures/test_figures.py、test_gentry_allied.py、test_promotions_high.py；same_behavior 的 tally 軌與 bots 段。
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from . import allied, atlas, conquest, four_tiers, naming, rules, team
from .core import bounty_base
from .state import PLAYER

if TYPE_CHECKING:
    from .engine import Game
    from .state import BotProfile

TREND_WEIGHT = 10.0  # 推大勢一點，抵得過十點獎勵
# 軍令（計畫 T6）：替這週的軍令記一次，比推三點大勢還值得；往軍令要去的地方走，比就地推一點大勢值得——
# 不然假人永遠就地遊歷推大勢，軍令湊不滿（整季模擬 T11 照實回報）
ORDER_SCORE = 30.0
# 一類一顆（正式季整合 9.2）：出陣照舊排在閒著的探索前面（出陣的分數另加 PRACTICE_SCORE）；出門一趟也是這個底分（OUTING_SCORE）
PRACTICE_SCORE = 1.0
# 懸賞榜（bounties.py）：城裡看得到還接得了的懸賞就去揭（不花體力），手上有就往要去的地方走、到了照做；
# 比推大勢的遊歷值得，比軍令低（陣營的事先做）【預設】
BOUNTY_SCORE = 8.0
CLINIC_MIN_SILVER = 20  # 付不起全治時（team.heal_plan 治一部分）手上至少這麼多才去、才療：不然每賺一兩就進醫館花掉
CLINIC_URGENT = 0.25  # 到這麼多就先去醫館、排在軍令前面（PM 2026-10-12：假人被軍令拉走、帶著三四成內傷打一整季）；整季機器人在 CLINIC_AT 就一律先去

_TURN: dict | None = None  # 這一次 pick 打分時記住的查詢（每個前往鈕都要問一次的軍令地點、出陣勝算）；pick 以外是 None，照舊每次算


@contextmanager
def turn_cache() -> Iterator[None]:
    """pick 打分那一輪（bot_policy.pick）：進去開一份新的 _TURN，出來無論如何清掉（打分丟例外也一樣）。"""
    global _TURN
    _TURN = {}
    try:
        yield
    finally:
        _TURN = None


def _turn_cached(key: tuple, compute):
    """pick 打分那一輪裡同一個查詢只算一次（同一輪的選單、同一個時刻，答案不會變）；不在 pick 裡（測試直接叫 score）照舊每次算。"""
    if _TURN is None:
        return compute()
    if key not in _TURN:
        _TURN[key] = compute()
    return _TURN[key]


def _side(game: Game) -> str | None:
    """敵我的一個讀法（同 Game._side 的本體 allied.side_of）：豪強分屬兩軍的季，豪強是依附的那一軍；其他人是自己的陣營（散人 None）。"""
    return allied.side_of(game.state, game.content)


def _goals(game: Game, profile: BotProfile) -> dict[str, int]:
    faction_id = _side(game) or profile.faction  # 豪強分屬兩軍：依附那一軍的目標
    if faction_id is None:
        return {}
    return rules.resolve_goals(game.content, game.state.world, game.content.scenario.faction(faction_id).goals)  # 開關關著時三條戰線都算黃巾聲勢


def can_pay_clinic(game: Game) -> bool:
    """有內傷，而且付得起全治、或手上至少 CLINIC_MIN_SILVER 兩（治一部分，team.heal_plan）。"""
    cost = team.heal_cost(game.content, game.state.player.member, game.state)
    return cost > 0 and game.state.player.stats.get("silver", 0) >= min(cost, CLINIC_MIN_SILVER)


def injury_share(game: Game) -> float:
    """本人的內傷佔氣血上限的幾成（醫館的兩道門檻 CLINIC_AT、CLINIC_URGENT 都跟它比）。"""
    s, c = game.state, game.content
    _, cap = team.member_neili(c, s.player.member, team.con_of(s, c, game.world, PLAYER), season=s.world)
    return s.player.member.injury / cap if cap > 0 else 0.0


def _crippled(game: Game) -> bool:
    """內傷到 CLINIC_URGENT 以上、卻湊不出錢去醫館：不遊歷、不挑戰本人（氣血只剩一成上下，打一場輸一場、
    輸了又掉銀兩，越打越窮；PM 2026-10-12 量到的那個一季都治不了的假人），改去探索、做事件攢錢。"""
    return injury_share(game) >= CLINIC_URGENT and not can_pay_clinic(game)


def _bounty_here(game: Game, kind: str) -> bool:
    """手上有一張要在這裡做的（討伐、打探）。"""
    s = game.state
    return any(b.kind == kind and b.location == s.player.location for b in bounty_base.mine(s, game.content))


def _duel_value(game: Game, loc_id: str) -> float:
    """約戰開著的季在這一塊貼約戰對自己陣營的分（同 effect_score 的一點抵十分）：推得動（conquest.push_problem 的攻）、打得贏守軍（不是 _outmatched）、
    今天還有出陣次數才有，量照名目量。"""
    s, c, side = game.state, game.content, _side(game)
    if side not in conquest.SIDES or loc_id not in conquest.blocks(c) or game.sorties_left() <= 0:  # 散人、不是兩軍的不推
        return 0.0
    if conquest.push_problem(s.world, c, side, loc_id, "attack") is not None or _outmatched(game, loc_id):
        return 0.0
    return TREND_WEIGHT * conquest.sortie_nominal(c, loc_id, "attack")


def _train_value(game: Game, profile: BotProfile, loc_id: str | None = None) -> float:
    """在這個地點（預設所在地）出陣（關著時遊歷）對自己陣營的大勢分（同 effect_score 的一點抵十分）。出陣今天用完了就是 0：
    不再往戰線地點拉（出陣探索與地盤設計第七節：次數用完就去探索找素材練功）。"""
    goals = _goals(game, profile)
    if game.duel_on():  # 約戰開著（減法季批 3b）：只有貼約戰推得動（沒有守）
        return _duel_value(game, loc_id or game.state.player.location)
    if conquest.on(game.content, game.state.world):  # 領地爭奪：出陣推進度、不推線——照推得動的名目量（大本營、不是區塊是 0）
        if game.sorties_left() <= 0 or _outmatched(game, loc_id or game.state.player.location):  # 贏面太低的地方攻了也推不動
            return 0.0
        return TREND_WEIGHT * game.sortie_progress(loc_id)
    return TREND_WEIGHT * sum(goals.get(t, 0) * d for t, d in game.train_trend_push(loc_id).items())


def _cannot_push(game: Game, loc_id: str | None) -> bool:
    """領地爭奪的季，在這一塊出陣（自家的守、別人的與中立地的攻）推不動進度（conquest.push_problem）。不是區塊、開關關著、散人都是假（照舊）。"""
    s, c = game.state, game.content
    side = _side(game)
    if loc_id is None or side is None or not conquest.on(c, s.world) or loc_id not in conquest.blocks(c):
        return False
    # 約戰開著（減法季批 3b）：出陣只有貼約戰（攻），自家的地方等對面來約、推不動
    how = "hold" if conquest.holder(s.world, c, loc_id) == side and not game.duel_on() else "attack"
    return conquest.push_problem(s.world, c, side, loc_id, how) is not None


# 領地爭奪：出陣攻打只有打贏才推進度，打輸扣氣血、掉銀兩、往醫館跑（2026-10-22 量 7 天季：十級以下的假人對上中立駐軍〔難度 58～82〕
# 幾乎全輸，被軍令帶去一直輸、一直療傷，練功的次數少一大截）。真人看得到鈕上的勝算，假人也照勝算挑：那裡出陣會打的幾路平均起來
# 贏面不到 SORTIE_WIN_FLOOR 的地方不去攻（不出陣、不往那裡走），去練功、去贏得了的地方。勝算的字換成機會照 team.ODDS 的門檻取中間。
SORTIE_WIN = {"穩勝": 0.95, "有把握": 0.75, "五五波": 0.5, "難分勝負": 0.25, "凶險": 0.2, "必敗": 0.03}
SORTIE_WIN_FLOOR = 0.4


def _sortie_win(game: Game, loc_id: str) -> float:
    """在這一塊出陣攻打贏的機會（領地爭奪）：那裡出陣會打的每一路（Game._sortie_foes，出陣照 Game.rng 挑一路）照勝算的字（Game.odds，
    照那一處的地利）換成機會再平均。沒有對手是 0。"""
    def compute() -> float:
        loc = game.content.locations[loc_id]
        foes = game._sortie_foes(loc)
        if not foes:
            return 0.0
        at = None if loc_id == game.state.player.location else loc_id
        return sum(SORTIE_WIN.get(game.odds(sid, at=at), 0.0) for sid in foes) / len(foes)

    return _turn_cached(("sortie_win", loc_id), compute)


def _outmatched(game: Game, loc_id: str | None) -> bool:
    """領地爭奪的季，這一塊要出陣攻打（不是自家的、搶得下來的區塊）而且贏面不到 SORTIE_WIN_FLOOR。開關關著、不是區塊、自家的（守不必打）、
    散人都是假（照舊）。"""
    s, c = game.state, game.content
    side = _side(game)
    if loc_id is None or side is None or not conquest.on(c, s.world) or loc_id not in conquest.blocks(c):
        return False
    if conquest.holder(s.world, c, loc_id) == side or not conquest.capturable(c, loc_id):
        return False
    return _sortie_win(game, loc_id) < SORTIE_WIN_FLOOR


# 第二輪第 101 批（從 bot 搬來）：鐵匠鋪的 trade_want、trade_at_smith 與捐軍備的 donate_want、donate_spare 都讀
# 素材與經濟（計畫 B5）：整季機器人與假人賣、升、捐都留這麼多（修兵器、餵馬、糧草吃一階；二階留著升三階），三階一個都不賣不捐
TRADE_KEEP = {1: 12, 2: 10, 3: 5}  # 三階只在素材四階開著時算（trade_keep）：留夠一次三換四
TRADE_MOVES = 24  # 一次在鐵匠鋪最多升、賣幾下（保險：每一下都會讓背包離留的量更近，本來就停得下來）


def trade_keep(content) -> dict[int, int]:
    """每一階留幾個不賣不捐（TRADE_KEEP）：素材四階開著時三階照一、二階的規矩、留夠三換四的（正式季整合 8.1：「留兩個三階湊神器」
    改成留四階，四階本來就不收）；關著照舊只有一、二階（三階不賣不捐）。"""
    return dict(TRADE_KEEP) if four_tiers.on(content) else {t: n for t, n in TRADE_KEEP.items() if t < 3}


# 第二輪第 101 批（從 bot_policy 搬來）：煉製、修練、有所感、玩家互動四包開單，bot_runner 接
NO_NAME: tuple[str | None, str] = (None, "")  # 開爐的 C 段不必取名：鎖內一定不叫模型（同 server.NO_NAME）


@dataclass(frozen=True)
class ForgeJob:
    """要請模型取名（或挑一個）的一爐：A 段在鎖內開的單，交給 bot_runner 在鎖外取名、再拿鎖開爐。"""

    insight_ids: tuple[str, ...]
    request: naming.NamingRequest


@dataclass(frozen=True)
class PourJob(ForgeJob):
    """意境合成改版：帶著傾注、立意的那一爐（改版沒開時不會開這種單，舊的 ForgeJob 一個欄位不多）。C 段照樣交給 Game.forge。"""

    pour: bool = False
    intent: str | None = None


@dataclass(frozen=True)
class MasterJob:
    """要請模型另取新名字的絕學定名（企劃者 2026-10-06：不沿用原名）：A 段在鎖內開的單，交給 bot_runner。"""

    art_id: str
    request: naming.NamingRequest


@dataclass(frozen=True)
class SenseJob:
    """有所感畫完那一筆、要請模型取名的私有意境（悟意境設計 0.2b 第 9 點：假人的首悟也要叫模型取名，不然首悟紀錄的名字是
    字表的樣子）：A 段在鎖內開的單（sensing.SenseRequest），交給 bot_runner 在鎖外取名、再拿鎖交回 Game.sense_draw。"""

    request: object  # sensing.SenseRequest


@dataclass(frozen=True)
class DiscussJob:
    """答應論武、首創要請模型取名（或挑一個）的那一爐：A 段在鎖內開的單（Game.peer_request），交給 bot_runner 在鎖外取名，
    C 段再拿鎖交回 Game.peer_act（params 帶 proposed）。"""

    sender: str
    item: str
    request: naming.NamingRequest


@dataclass(frozen=True)
class EpiphanyJob:
    """特殊頓悟按「靜心思名」：A 段在鎖內開的單（epiphany.NameAsk），交給 bot_runner 在鎖外請模型取三個名字，
    C 段再拿鎖交回 Game.epiphany_names（不然候選全是字表的樣子，首悟的名字看得出是假人）。"""

    request: object  # epiphany.NameAsk


@dataclass
class NamingSlot:
    """這一輪這個假人能不能把一件取名交給模型（首創的爐或絕學定名；bot_runner 給：一次一件、兩件之間要隔一段時間）。
    open 時開成單子放進 job；不 open 時那一爐不開、那個名先不定，skipped 加一（只是數字，主控台只印總數）。"""

    open: bool = False
    job: ForgeJob | MasterJob | SenseJob | DiscussJob | EpiphanyJob | None = None
    skipped: int = 0
    model: bool = True  # 這個假人程式叫得到模型（有 client、設定開著）；叫不到時頓悟取名直接用字表，不然那個假人一季都卡在取名


# 第二輪第 101 批（從移動包搬來）：移動、決戰、陣營都讀
def next_hop(game: Game, targets: list[str]) -> str | None:
    """從所在地往路程最近的目標走的下一站：照地圖連線走路程最短的路（地圖擴充設計 3.2）、跳過還沒開放的地點
    （不管摸清了沒）；已經在目標上或走不到時回傳 None。"""
    if game.state.player.location in targets:
        return None
    found = atlas.shortest_routes(game.state, game.content)
    reachable = [found[t] for t in targets if t in found and found[t].path]
    if not reachable:
        return None
    best = min(reachable, key=lambda route: (round(route.minutes, 6), len(route.path), route.path))
    return best.path[0]
