"""核心給功能包的服務（開發規範手冊 3.3、3.10）。第一階 ctx 就是 Game 本身；功能包只准叫下面這張清單上的東西。
清單之外要用 Game 的別的方法，先加進這張清單（在派工單或回報裡寫明，PM 看過），不要直接叫。

清單分四段（主動搬六包批次表第二節，PM 2026-10-31）：一、共用服務（每一包都可以用的）；二、查詢服務（別包問「我在哪一場」這一類，
由那一包經 Game 的委派回答）；三、過渡（別的功能還沒搬的方法，標主人：主人搬成包時改成那一包的查詢服務、或拿掉）；四、寄放
（包放在 Game 上的暫時旗標）。每一包只用自己用得到的那幾個；`tests/core/test_feature_boundaries.py` 照這一份放行。

## 一、共用服務

狀態與時刻
- `ctx.state`（GameState：`state.player`、`state.world`）、`ctx.content`、`ctx.world`（WorldStateStore）、`ctx.now`、`ctx.rng`、`ctx.client`
- `ctx.pill_now()`、`ctx._pill_day()`：回體丹那一套的現實時間與「第幾天」（台灣 00:00 換日）
- `ctx.stamp(t)`：寫給玩家看的時刻（calendar.stamp_text）
- `ctx.touched`：這一下動到的別人的名號（伺服器叫他們的分頁重抓）

記錄與存回
- `ctx._log(msgs)`：這一下的回話；`ctx._write(title, lines, tag=...)`：寫一則江湖紀錄；`ctx._guide(...)`：引導那一框
- `ctx._outcome(tag, line)`：這一下那一則江湖紀錄的結果那一格；`ctx._draft`：這一下的那一則（choose 建的 Draft，例：出陣回報掛在 front）
- `ctx._save_season()`：把這一次動到的季寫回共用賽季；`ctx._reconcile_season()`：重讀共用賽季
- `ctx._cost_option(id, label, stamina)`：花體力的選項（鈕上寫體力）

戰報（出陣第 1 批加的；打一場的包都要）
- `ctx._record_exp(record, exp, source)`：本人的經驗寫進戰報（滿級換心得）；`ctx._file_battle(record, ...)`：存戰報、回那一行
- `ctx._play_rounds(record, squad, tier, ...)`：排回合的演出；`ctx._deed_fame(kind)`：立功給名望
- `ctx._load_kin(name)`、`ctx._save_kin(game)`：同一把鎖裡讀、寫別人的存檔（混戰、截殺）

店面與戰報的補充（tavern：主動搬六包第 10 批酒肆加的）
- `ctx._shop_say(key, problem=None)`、`ctx._shop_after(problem, done, keyer=None)`：掌櫃那一句（七間店共用，shop_lines.json 的情況）
- `ctx._idle()`：閒著（不在路上、沒在閉關）才進得了店
- `ctx._last_wear`：`_file_battle` 留下的這一場兵器、防具損耗那幾句（接在戰報那一則的後面）

身分
- `ctx._side()`：站哪一軍；`ctx.is_admin()`；`ctx._admin_target(name)`、`ctx._save_target(game)`：管理者動到別人的存檔
- `ctx._quick_client()`：鎖內的模型呼叫（一步最多 in_lock_model_timeout 秒）

錢包（3.10：跨包的票經過這裡，不叫商城）
- `ctx.wallet`：WalletService（下面）——`tokens(kind)`、`consume(kind)`、`purchases()`、`card_bonus()`、`item_for(effect)`
- `ctx._wallet()`：商城開著時的 Wallet（資料庫那一側）；關著是 None。`ctx._mall_owner()`：錢包的主人（名號的 casefold）
- `ctx.pill_cap()`、`ctx.pills_left_today()`：回體丹一天的上限（含月卡）與今天還能服幾顆

共用的字與小函式（不是 Game 上的，從這個模組 import）：`PAUSED_TEXT`、`NO_SUCH_PLAYER`、`drill_share`

## 二、查詢服務

（還沒有。第 4 批決戰包起：別包要問「我在哪一場」這一類，由那一包經 Game 的委派回答，列在這裡、寫主人。）

## 三、過渡（別的功能還沒搬的方法；括號是主人）

- `ctx._squad_encounter(squad_id, as_sortie=True)`（戰鬥：打一場隊伍，出陣攻打）
- `ctx._train_option(...)`、`ctx._train_pick(loc)`、`ctx._big_trip(loc)`（舊遊歷：勝算與必敗先問的鈕、大場面挑哪一路）
- `ctx._push_progress(loc_id, nominal, source, how)`（地盤：領地爭奪推、拉進度）
- `ctx._order_credit(...)`（軍令）；`ctx._drill_gains(squad, share)`（操練）
- `ctx._spar_power(a, b)`、`ctx._spar_mirror(result, power)`（切磋：本人對本人的威力、從另一邊看同一場）
- `ctx._outing_on()`（探索：減法季探索一顆開著）
- `ctx.duel_on()`、`ctx._duel_option(loc)`（出陣約戰：第 2 批搬進出陣包之後拿掉）
- `ctx._raid_key(a, b)`（截殺：截殺與混戰共用的冷卻帳 WorldState.raids 的鍵）
- `ctx._conquest_side()`（地盤：領地爭奪算哪一邊，豪強依附的那一軍；第 2 批約戰用）
- `ctx.place_minutes(loc_id)`（輿圖與移動：走到那裡要現實幾分鐘；第 2 批約戰用）
（這三個原本列在共用段——照規劃者 plan.json 第 1 批的分法；dev/sortie-1 審查照批次表第二節「過渡＝別的功能還沒搬的方法、標主人」
搬到這裡：在 engine 裡分別定義在截殺、地盤、輿圖與移動那幾段。）
- `ctx.sorties_left()`、`ctx._sortie_hold(loc, how)`（出陣包自己的委派：測試換掉 Game.sorties_left〔test_bot_policy_conquest〕、
  腳本換掉 Game._sortie_hold〔sim_trend_sources〕，包裡經 ctx 叫，換掉的才打得到；呼叫端改完就拿掉）

tavern（主動搬六包第 10 批酒肆加的這一段；擺在段尾，不跟別條拆包線在段頭加的那幾行撞在一起）
- `ctx._battle_now()`（決戰：此刻自己參戰的那一場；殺手不找決戰裡的人。決戰搬成包時改成那一包的查詢服務）

## 四、寄放（包放在 Game 上的屬性；包外的呼叫端與測試還在 Game 上讀寫；那一包的線再碰到時搬走）

- `ctx.mall_bought`、`ctx.mall_already`（商城）：上一次 actions.buy 的結果（買成的商品 id；同一個編號早就買好的那一件），伺服器在鎖裡讀
- `ctx._clash_won`、`ctx._sortie_marked`、`ctx._sortie_moved`、`ctx._sortie_flipped`（出陣）：Game.__init__ 起的、出陣那一下設、
  `_push_progress`（地盤，留在核心）寫與讀——混戰得勝的加成、記過一筆出陣沒、這一下推（拉）動了多少、推滿易手了沒（出陣回報讀）

tavern（主動搬六包第 10 批酒肆加的這一段；擺在段尾，理由同上）
- `ctx._tavern_seek_exact`、`ctx._tavern_reply`：查人那一下問得多清楚（託酒家留意看它；None 沒查成、True 確切地點、False 沒問清楚）、
  問酒家 B 段寫好的那一句（tavern_ask 放、問完清掉）

不在清單上的：`Game` 其餘一千多個方法都是還沒搬的功能自己的，功能包碰了就是跨包（手冊 3.4 第 1 條）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..models import Content
from ..wallet import Purchase, Wallet

if TYPE_CHECKING:
    from ..engine import Game

# 共用的字（原本寫在 engine.py；功能包要用、又不能 import engine，搬到這裡，engine 照舊叫得到）
PAUSED_TEXT = "賽季暫停中（停機維護）：這段時間不能行動，畫面照常可看"
NO_SUCH_PLAYER = "（江湖上沒有「{name}」這個人。）"  # 管理者查不到名號（玩家個人劇情、商城查帳；只有管理者看得到）


def drill_share(amount: int, share: float) -> int:
    """跟自己人操練拿對手那一項獎勵的幾成（Config.drill_reward_share），四捨五入（round 是銀行家進位）。
    操練真的給的（Game._drill）與行動列底下說會給什麼（Game._train_line）都算這一個；出陣的守與打贏（出陣包）、探索也用。
    （原本寫在 engine.py；出陣包要用、又不能 import engine，搬到這裡，`from tianxia.engine import drill_share` 照舊拿得到。）"""
    return int(amount * share + 0.5)


CARD_KEY = "pill_cap"  # 月卡記在 mall_entitlements 的哪一格（回體丹每天的上限）


def wallet_on(content: Content) -> bool:
    """錢包開著沒（＝商城開著，Config.mall.enabled）：關著時不讀不寫三張表、月卡不加上限、沒有票。"""
    return content.config.mall.enabled


def tokens(wallet: Wallet, owner: str, effect: str, season: int | None = None) -> list[int]:
    """帶著 effect（zhuan_rewrite、rename、列傳的四件、題壁墨）還沒用掉的那幾筆購買（id，舊的在前）：沒退、data 裡沒有 used。每一筆是一次。
    season 給了只算那一季買的（列傳的票綁買的那一季，減法季批 7b、FB-845）。"""
    return [b.id for b in reversed(wallet.purchases(owner)) if b.refunded is None and b.data.get(effect) and not b.data.get("used")
            and (season is None or b.season == season)]


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
