"""核心給功能包的服務（開發規範手冊 3.3、3.10）。第一階 ctx 就是 Game 本身；功能包只准叫下面這張清單上的東西。
清單之外要用 Game 的別的方法，先加進這張清單（在派工單或回報裡寫明，PM 看過），不要直接叫。

## 服務清單（ctx 上准用的）

狀態與時刻
- `ctx.state`（GameState：`state.player`、`state.world`）、`ctx.content`、`ctx.world`（WorldStateStore）、`ctx.now`、`ctx.rng`、`ctx.client`
- `ctx.pill_now()`、`ctx._pill_day()`：回體丹那一套的現實時間與「第幾天」（台灣 00:00 換日）
- `ctx.stamp(t)`：寫給玩家看的時刻（calendar.stamp_text）
- `ctx.touched`：這一下動到的別人的名號（伺服器叫他們的分頁重抓）

記錄與存回
- `ctx._log(msgs)`：這一下的回話；`ctx._write(title, lines, tag=...)`：寫一則江湖紀錄；`ctx._guide(...)`：引導那一框
- `ctx._save_season()`：把這一次動到的季寫回共用賽季；`ctx._reconcile_season()`：重讀共用賽季
- `ctx._cost_option(id, label, stamina)`：花體力的選項（鈕上寫體力）

身分
- `ctx._side()`：站哪一軍；`ctx.is_admin()`；`ctx._admin_target(name)`、`ctx._save_target(game)`：管理者動到別人的存檔
- `ctx._quick_client()`：鎖內的模型呼叫（一步最多 in_lock_model_timeout 秒）

錢包（3.10：跨包的票經過這裡，不叫商城）
- `ctx.wallet`：WalletService（下面）——`tokens(kind)`、`consume(kind)`、`purchases()`、`card_bonus()`、`item_for(effect)`
- `ctx._wallet()`：商城開著時的 Wallet（資料庫那一側）；關著是 None。`ctx._mall_owner()`：錢包的主人（名號的 casefold）
- `ctx.pill_cap()`、`ctx.pills_left_today()`：回體丹一天的上限（含月卡）與今天還能服幾顆

包寄放在 Game 上的屬性（過渡，同 3.10 的委派：包外的呼叫端與測試還在 Game 上讀；第 2 階那一包的線再碰到時搬走）
- `ctx.mall_bought`、`ctx.mall_already`：商城上一次 actions.buy 的結果（買成的商品 id；同一個編號早就買好的那一件），伺服器在鎖裡讀

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
