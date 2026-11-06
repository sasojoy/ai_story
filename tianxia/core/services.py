"""核心給功能包的服務與共用的字：錢包服務（票的庫存與消耗）、`not_while_preparing`、各包都會用的字與小工具（開發規範手冊 3.3、3.10）。
功能包經 Game 只准叫 `tianxia/core/services_list.md` 那張清單上的東西，和自己這一包的委派（清單第二輪第 74 批從這個說明搬過去）。"""
from __future__ import annotations

import functools  # sense（第 24 批）：outing_watch 用
from dataclasses import dataclass  # stamina_plays（第 39 批）：RaidSpoils 用
from typing import TYPE_CHECKING, NamedTuple  # zhuan（第 29 批）：Writer 用

from .. import calendar  # checkin（第 30 批）：checkin_on 用
from ..models import Content
from ..wallet import Purchase, Wallet

if TYPE_CHECKING:
    from ..engine import Game
    from ..state import GameState, WorldState  # companions（note_cheer 的型別）；checkin（checkin_on 的型別）

# 共用的字（原本寫在 engine.py；功能包要用、又不能 import engine，搬到這裡，engine 照舊叫得到）
PAUSED_TEXT = "賽季暫停中（停機維護）：這段時間不能行動，畫面照常可看"
NO_SUCH_PLAYER = "（江湖上沒有「{name}」這個人。）"  # 管理者查不到名號（玩家個人劇情、商城查帳；只有管理者看得到）
# military（全部拆包第 33 批：原本寫在 engine.py；軍情包的第 3、4 階行動選單要產生它、又不能 import engine，搬到這裡，engine 照舊叫得到）
RANK_ACTION_PREFIX = "act:rank:"  # 第 3、4 階行動的選項 id 前綴（act:rank:<行動 id>，正式版戊一）；models.ALLOW_FAMILIES 也列它，原始碼裡要真的有
# stamina_plays（全部拆包第 39 批：原本寫在 tianxia/ambush.py；移動被擋〔移動包 menu.move_option〕要用、核心不能 import 包，搬到這裡，
# ambush.MOVE_BLOCKED 照舊是同一個字串）
MOVE_BLOCKED = "守著埋伏"
# stamina_plays（全部拆包第 39 批：原本寫在 engine.py；設伏的贏家帳〔包〕與截殺〔核心〕共用，包不能 import engine，搬到這裡，
# `from tianxia.engine import RaidSpoils` 照舊拿得到，是同一個類別）
@dataclass(frozen=True)
class RaidSpoils:
    """一場截殺分出勝負之後的帳（Config.raid）：誰贏、輸的人失了多少銀兩、贏的拿走多少、輸的人掉多少氣血、贏的記多少貢獻。"""

    winner: str
    lost: int
    taken: int
    hp: int
    contrib: int
    goods: tuple[tuple[str, int], ...] = ()  # 設伏劫道：贏的搶走的素材（素材 id, 個數）；截殺沒有
    evil: int = 0  # 名聲 5.4：贏的人揭著輸的人的官府通緝，輸的人惡名少幾點（Config.renown.official_evil_loss）


# travel（全部拆包第 47 批：原本寫在 engine.py；移動包的路上小事選單與結伴分收穫要讀、核心的換季重設與讀檔清舊〔_drop_stale_references〕也讀，**留在核心**〔第 48 批 PM 認定〕，engine 照舊叫得到）
# 路上小事（路上設計第四節）：road:<id> → (名稱, 這一段做過之後寫的「這段路已經……」)；按鈕上的補充見移動包的 road_task_options
ROAD_TASKS: dict[str, tuple[str, str]] = {  # 留核心：讀檔清舊與換季重設還讀（第 47 批 PM 認定第 4 條）
    "think": ("邊走邊想", "想過了"),
    "ask": ("沿途打聽", "打聽過了"),
    "gather": ("路邊採集", "找過了"),
}
ROAD_REWARD_TASKS = ("think", "gather")  # 有經濟收穫、受每天上限管的路上小事（Config.road_reward_daily_cap）


# sortie（全部拆包第 17 批：原本寫在 engine.py；出陣包的遊歷鈕要用、又不能 import engine，搬到這裡，engine 照舊叫得到）
BIG_FIGHT_WAIT = "兩人對峙……"  # 大場面按下去、等模型判讀時按鈕上的字（武學與成長設計 8.3）


# guide（全部拆包第 22 批）：原本寫在 tianxia/guide.py；核心的 Game._guide、_menxia_entry 照它把序章步驟的獎勵（這一下的結果）跟對話框
# 那幾行分開，新手引導包產生它——核心不能 import 包，型別搬到這裡，引導包（tianxia.guide.HutReward 照舊是同一個類別）re-export
class HutReward(str):
    """序章步驟的獎勵那一行（出師的盤纏）：不進對話框，當這次行動的結果寫進「剛剛」（Game._guide 認這個型別，T7 審查 M4）。"""


def drill_share(amount: int, share: float) -> int:
    """跟自己人操練拿對手那一項獎勵的幾成（Config.drill_reward_share），四捨五入（round 是銀行家進位）。
    操練真的給的（出陣包 train_actions.drill）與行動列底下說會給什麼（train_actions.train_line）都算這一個；出陣的守與打贏（出陣包）、探索也用。
    （原本寫在 engine.py；出陣包要用、又不能 import engine，搬到這裡，`from tianxia.engine import drill_share` 照舊拿得到。）"""
    return int(amount * share + 0.5)


# companions（全部拆包第 20 批）：原本寫在 engine.py；人物對話搬進人物情誼包要用、又不能 import engine，搬到這裡，engine 照舊 import 回來
# （`from tianxia.engine import SAY_OPTION, PLAN_OPTION, ROAD_SAY, TEXT_TALKS, say_text` 照舊拿得到）
# 跟人物對話時的「自己說」（企劃者 2026-10-08）：按下去只是叫出輸入框，真正送出帶著那句話走 choose(SAY_OPTION, text=…)（server.say）
SAY_OPTION = "talk:say"
# NPC 智能 2.1（parley.py）：同「自己說」要打一句話的兩顆——對話裡跟答應陪你出陣的人商量打法、他帶路的路上跟他說一句
PLAN_OPTION = "talk:plan"
ROAD_SAY = "parley:road"
TEXT_TALKS = (SAY_OPTION, PLAN_OPTION, ROAD_SAY)
SAY_MAX = 20  # 「自己說」最多幾個字（跟隨口應對一樣）
# 並肩出陣（NPC 智能 2.0）：出陣包的 act:train 打那一場前面那一句——陪他出陣的人部曲出力加成，與商量打法沒談攏、這一仗他幫不上忙
# （原本寫在 tianxia/parley.py，出陣包 import 它；parley 搬進人物情誼包之後包不能 import 包，搬到這裡，parley re-export）
BACKED_LINE = "〔{name}的部曲與你並肩，這一仗威力 +{pct}%〕"
PLAN_MISS = "（打法沒談攏：這一仗他的部曲幫不上忙。）"


def say_text(text: str | None, limit: int = SAY_MAX) -> str | None:
    """「自己說」那句話能不能送：先去頭尾空白、中間連著的空白併成一個，1～limit 字才算數，再轉繁體（zh.to_traditional）；
    不行就是 None。長度在轉繁體之前量（轉換不改字數，量的是玩家打的）。limit 平常是 SAY_MAX，NPC 智能 2.0開著時照 Game.say_max。"""
    from .. import zh  # noqa: PLC0415  （延後載入：核心的服務檔平常不碰簡繁轉換）

    if text is None:
        return None
    text = " ".join(text.split())
    if not text or len(text) > limit:
        return None
    return zh.to_traditional(text)


# companions（全部拆包第 19 批「先做」：figure_life 讀來信改走核心）：PlayerState.cheers 那一格——舊模組 figure_life.spread 寫（他欣賞你做的事）、
# 書信（人物情誼包 letters._cheer_letter）讀；原本寫在 tianxia/letters.py，letters re-export（tianxia.letters.note_cheer 照舊是同一個函式）
CHEERS_KEEP = 5


def note_cheer(state: GameState, content: Content, cid: str, text: str) -> None:
    """figure_life.spread 讓 cid 的情誼往上動、情誼到了 letter_affinity：記下來，等著寫道賀信（最多 CHEERS_KEEP 件，舊的先丟）。
    開關同 letters.on（人物活起來開著、書信開著）。"""
    tuning = content.config.figure_life
    if not (tuning.enabled and tuning.letters) or state.player.affinities.get(cid, 0) < tuning.letter_affinity:
        return
    state.player.cheers = [c for c in state.player.cheers if not c.startswith(f"{cid}|")] + [f"{cid}|{text}"]
    del state.player.cheers[:-CHEERS_KEEP]


# sense（全部拆包第 24 批「有所感與頓悟」）：原本寫在 engine.py；搬進有所感包的動作要掛裝飾器、要回籌備中那一句，又不能 import engine，
# 搬到這裡，engine 照舊叫得到（`from tianxia.engine import PREPARING_REFUSAL`：tests/bots/test_stamina_refill.py、tianxia/features/smithy/tests/test_shop.py）。
# 賽季籌備中（管理者還沒開季）：選單上那一顆灰的、安排前往被擋的原因寫 PREPARING_TEXT；動作被擋回一句 PREPARING_REFUSAL
PREPARING_TEXT = "賽季籌備中，等待管理者開季"
PREPARING_REFUSAL = f"（{PREPARING_TEXT}。）"


def outing_watch(fn):
    """走一趟停在要選的事上時，這一下選完的得失記在那一段（探索包 outing_actions.outing_watched，Game 上留一行委派 _outing_watched）。
    第一個參數是 ctx（第一階就是 Game）：掛在 Game.choose、answer_event 與有所感包的 sense_draw、epiphany_names 上（原本是 engine.py
    模組層的 _outing_watch）。"""
    @functools.wraps(fn)
    def run(ctx, *args, **kwargs):
        return ctx._outing_watched(fn, *args, **kwargs)
    return run


CARD_KEY = "pill_cap"  # 月卡記在 mall_entitlements 的哪一格（回體丹每天的上限）


def wallet_on(content: Content) -> bool:
    """錢包開著沒（＝商城開著，Config.mall.enabled）：關著時不讀不寫三張表、月卡不加上限、沒有票。"""
    return content.config.mall.enabled


def tokens(wallet: Wallet, owner: str, effect: str, season: int | None = None) -> list[int]:
    """帶著 effect（zhuan_rewrite、rename、列傳的四件、題壁墨）還沒用掉的那幾筆購買（id，舊的在前）：沒退、data 裡沒有 used。每一筆是一次。
    season 給了只算那一季買的（列傳的票綁買的那一季，減法季批 7b、FB-845）。"""
    return [b.id for b in reversed(wallet.purchases(owner)) if b.refunded is None and b.data.get(effect) and not b.data.get("used")
            and (season is None or b.season == season)]


def look_ids(wallet: Wallet, owner: str) -> list[str]:
    """這個人買到的擂台形象（購買那一列 data 的 look_id；沒退的，舊的在前、不重複）：帳號的，換季也帶著走（Joy 2026-10-31
    「花錢買的東西不能不見」）。商城包（買過了不再賣）與形象包（穿哪一套）都照它。"""
    seen: list[str] = []
    for b in reversed(wallet.purchases(owner)):
        look = b.data.get("look_id")
        if b.refunded is None and look and look not in seen:
            seen.append(look)
    return seen


def card_bonus(content: Content, wallet: Wallet, owner: str, day: int) -> int:
    """月卡（商城架構設計 4.5）：day 這一天在卡的期間裡（開始日～到期日，不含到期日）就回 Config.mall.card_pill_bonus，其餘 0。"""
    if not wallet_on(content):
        return 0
    span = wallet.card(owner, CARD_KEY)
    return content.config.mall.card_pill_bonus if span is not None and span[0] <= day < span[1] else 0


def item_for(content: Content, effect: str) -> str | None:
    """賣這一種效果的第一件商品（照 content/mall.json 的順序；「去萬寶閣」那一顆停在這一件）；商城關著或沒賣是 None。"""
    if not wallet_on(content):
        return None
    return next((item.id for item in content.mall.values() if item.effects.get(effect)), None)


class WalletService:
    """ctx.wallet：這個人的錢包，只做票的庫存與消耗、月卡加的上限、哪一件商品賣這種效果（3.10）。
    商城關著（ctx._wallet() 是 None）時庫存是空的、消耗什麼都不做、上限不加、沒有商品。賣與記帳是商城包的事。"""

    def __init__(self, game: Game) -> None:
        self._game = game

    def tokens(self, kind: str, bought_in: int | None = None) -> list[int]:
        """手上還沒用掉的 kind 票（購買 id，舊的在前）；bought_in 給了只算那一季買的。"""
        wallet = self._game._wallet()
        return [] if wallet is None else tokens(wallet, self._game._mall_owner(), kind, bought_in)

    def consume(self, kind: str, *, bought_in: int | None = None, at: float | None = None, **marks) -> int | None:
        """用掉最舊的一張 kind 票：那一列的 data 記 used（＝at，不給是回體丹那一套的現實時間 pill_now）與 marks；回那一張的購買 id，
        沒有票回 None、什麼都不寫。"""
        left = self.tokens(kind, bought_in)
        if not left:
            return None
        self._game._wallet().mark_used(left[0], self._game.pill_now() if at is None else at, **marks)
        return left[0]

    def purchases(self) -> list[Purchase]:
        """這個人全部的購買（新的在前；列傳那幾張票照已經讀好的這一份數，zhuan_end.season_tickets）；商城關著是空的。"""
        wallet = self._game._wallet()
        return [] if wallet is None else wallet.purchases(self._game._mall_owner())

    def card_bonus(self) -> int:
        """今天月卡讓回體丹上限多幾顆（Game.pill_cap 與體力條的說明都讀這一份）；沒有卡、商城關著是 0。"""
        wallet = self._game._wallet()
        return 0 if wallet is None else card_bonus(self._game.content, wallet, self._game._mall_owner(), self._game._pill_day())

    def item_for(self, effect: str) -> str | None:
        return item_for(self._game.content, effect)


# cultivation（全部拆包第 23 批「修練」：原本寫在 engine.py；修練包的動作要掛、又不能 import engine，搬到這裡，engine 照舊叫得到——
# 還在 Game 上的動作照舊掛同一個裝飾器；它回的 PREPARING_REFUSAL 第 24 批先搬了，寫在上面 # sense 那一段）
def not_while_preparing(action):
    """Game 的動作（與修練包裡同一種動作）：籌備中什麼都不能做，只回一句 PREPARING_REFUSAL（照一般的拒絕寫進紀錄，ctx._log）；
    不然照常做。第一個參數是 ctx（第一階就是 Game 本身）。"""
    @functools.wraps(action)
    def guarded(ctx: Game, *args, **kwargs):
        if ctx._preparing():
            return ctx._log([PREPARING_REFUSAL])
        return action(ctx, *args, **kwargs)

    return guarded


# socialize（全部拆包第 21 批「交友求見」）：原本寫在 engine.py；交友求見搬進包要用、核心的選單與挑戰本人也讀、又不能 import engine，搬到這裡，
# engine 照舊 import 回來（`from tianxia.engine import SNUB_NOTE, SOCIAL_NO_ONE` 照舊拿得到：tianxia/features/peers/tests/test_social.py、tests/web/test_jianghu_page_web.py）
AUDIENCE_HALL_FIGURES = 2  # 一個地點有幾位以上的大勢人物，交友就不直接找人、改按「求見」指名（企劃者 2026-10-03 決定）
SOCIAL_NO_ONE = "這裡沒有能說上話的人"  # 待 joy 潤：一類一顆的交友沒有人物、也沒有結識事件時（鈕上不帶句號）
SNUB_NOTE = "剛吃了敗仗，閉門不見"  # 挑戰本人打贏之後，他對打贏的人關上門（軍令文件 4.5）：求見、交友、挑戰的按鈕寫這一句


# checkin（全部拆包第 30 批「簽到」）：原本寫在 tianxia/checkin.py；回體丹那一套（Game._pill_find 掉回體丹）歸核心，要問簽到開著沒、說那一句，
# 簽到包（tianxia/features/checkin/checkin.py）又不能被核心 import，搬到這裡，簽到包 re-export（`checkin.on is services.checkin_on`）
PILL_FOUND = "獲得 【{name}】一顆——不知誰落下的，正好收著。"


def checkin_on(content: Content, world: WorldState | None) -> bool:
    """簽到開著沒：設定打開（只有 season21），這一季是 21 天季（開季時蓋的章），而且還沒收季。週末與 14 天一律關著。"""
    return content.config.checkin.enabled and calendar.season21_on(world, content) and not world.ended

# zhuan（全部拆包第 29 批「列傳」）：原本寫在 tianxia/zhuan_end.py；核心的行狀（zhuan/standing.py 的 standing 的插畫鍵與寫評曰的人物）與商城（插畫票用不上不賣）要用、
# 列傳包又不能被核心與別包 import，搬到這裡，zhuan_end re-export（`zhuan_end.illustration_for is services.illustration_for`）
ART = "zhuan_art"  # mall.EFFECTS 的鍵（列傳插畫票）
ART_NO_SIDE = "沒投靠一方的人，列傳配不了插畫。"  # 插畫票不賣的原因（FB-845）
ART_FREE = "你的列傳得了第一階，插畫白送，不必買。"
AFFINITY, TIER, BOUGHT = "affinity", "tier", "bought"  # 誰替你寫：情誼 70 以上的、第一二階的主將或家主、買了親筆評曰請的
REASONS = (AFFINITY, TIER, BOUGHT)


class Writer(NamedTuple):
    fid: str  # 人物 id（content.characters）
    reason: str  # AFFINITY／TIER／BOUGHT


def illustration_for(state: GameState, content: Content, season: WorldState) -> str:
    """列傳插畫的圖庫鍵「<陣營>_<win|lose>」（第一批 6 張：三方各贏、各輸；設計第九章）。兩軍看結局贏的是不是自己；豪強看照哪一本論功
    （那一本是贏的那一軍才算贏；沒論功照此刻幫的那一軍）；和局都是 lose。散人、季還沒收是空字串。"""
    from ..wins import winner_of  # noqa: PLC0415

    p = state.player
    faction = content.scenario.find_faction(p.faction)
    if faction is None or not season.ended:
        return ""
    winner = winner_of(season, content)
    if faction.allies:
        result = season.final_tiers.get(p.name)
        side = result.ledger_used if result is not None and result.ledger_used in faction.allies else p.ally
        won = winner is not None and side == winner
    else:
        won = winner == faction.id
    return f"{faction.id}_{'win' if won else 'lose'}"


def art_problem(state: GameState, content: Content, season: WorldState) -> str | None:
    """列傳插畫票這一季用不用得上（FB-845）：用不上就不賣，回商城那一列灰掉要寫的原因；用得上是 None。
    沒投靠劇本裡的陣營的人（散人）列傳配不了插畫；休季時已經得第一階的人插畫白送（列傳包 actions.options 也是這兩條），
    季中看不出會是第幾階，照舊賣。"""
    p = state.player
    if content.scenario.find_faction(p.faction) is None:
        return ART_NO_SIDE
    result = season.final_tiers.get(p.name) if season.ended else None
    return ART_FREE if result is not None and result.tier == 1 else None


def writers(state: GameState, content: Content, season: WorldState) -> list[Writer]:
    """這一季替你寫評曰的人物（不含買了請的，那幾位照票）：第一、二階由自己這一方 FactionDef.verdict_by 裡跟你情誼最高的那一位寫
    （一樣高照寫的順序；官軍皇甫嵩或盧植、黃巾張角或波才、豪強曹操）；情誼到 signature_affinity（70）以上的人物各一位（情誼高的在前），
    最多 Config.jianfa.verdict_affinity_max（3）位——深交不限人數之後（企劃者 2026-10-28），PM 定只取情誼最高的前三位，省模型呼叫、
    固定句也不重複。同一位人物只寫一條。關著的季、散人沒有階也沒有 70 以上的人物是空的。"""
    p, c = state.player, content
    out: dict[str, str] = {}
    result = season.final_tiers.get(p.name)
    faction = c.scenario.find_faction(p.faction)
    if result is not None and result.tier in (1, 2) and faction is not None and faction.verdict_by:
        order = {cid: i for i, cid in enumerate(faction.verdict_by)}
        out[min(faction.verdict_by, key=lambda cid: (-p.affinities.get(cid, 0), order[cid]))] = TIER
    edge, room = c.config.signature_affinity, c.config.jianfa.verdict_affinity_max
    for cid, value in sorted(p.affinities.items(), key=lambda x: (-x[1], x[0])):
        if room <= 0:
            break
        if value >= edge and cid in c.characters and cid not in out:
            out[cid] = AFFINITY
            room -= 1
    return [Writer(cid, reason) for cid, reason in out.items()]
