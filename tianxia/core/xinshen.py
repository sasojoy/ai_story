"""心神（設計稿 https://claude.ai/artifact/NbTxoAPdroin7N9cRjCiP3 第 4 版；Joy 2026-11-06「可以 寫」；數字在 Config.xinshen）。

跟人物說話這種要叫模型的互動不扣體力，改扣心神。核心的資源（跟體力一樣），功能包經 Game 的服務叫（ctx.xinshen_purse、
ctx.xinshen_spend；services.py 第一段）：女性角色的隱線只叫「免費限定」那一種。本體在這個檔的檔尾（收 ctx；架構收尾第 105 批，同 core/pills.py），
Game 上留 xinshen_purse、xinshen_spend、xinshen_view 三個一行委派（status_view、companions、測試在叫；只有這裡叫的 _xinshen_card 不留）。

三份分開記：
- 免費：每天（回體丹那一套的換日，台灣 00:00）補到 free_daily，用不完不留（PlayerState.xinshen_free／_day）。
- 月卡：卡的期間每天補到 card_daily，同上（PlayerState.xinshen_card／_day）。買卡那一刻當天就有（「不是今天補的就當滿的」）。
- 存著的：萬寶閣凝神香（商品效果 xinshen）。每一筆購買那一列的 data 記買了幾點（xinshen）、用掉了幾點（xinshen_spent），
  從最舊的那一筆扣起；剩下的＝沒退的那幾筆各自「買的 − 用掉的」加總。都在帳號的購買紀錄上：不過期、換季不清
  （Joy 10/31「花錢買的東西不能不見」），易名帖改名跟著搬（sqlite_world）。退一筆只收回那一筆還沒用的，用掉的不追。
  資料庫結構不動（第 9 版）：mall_entitlements 的 kind 有 CHECK，所以不記在那裡。
扣的順序：一般交談先扣月卡（今天不用就沒了）、再扣免費、最後動存著的；免費限定只扣免費那一份。

問酒家不扣心神，另外一天最多 ask_per_day 次：規則與存檔那一格（tavern_asks）在酒肆包（features/tavern/rules.py，架構收尾第 105 批搬回），這裡只留數字（Config.xinshen）與次數用完那一句（ASKS_DONE）。

只 import models、state、wallet（月卡那一格的鍵抄一份，見 CARD_KEY）；不讀時鐘，第幾天由呼叫端給：純規則那幾個函式收 day，檔尾的本體問 ctx._pill_day()。
"""
from __future__ import annotations

from dataclasses import dataclass

from tianxia.models import Content
from tianxia.state import GameState
from tianxia.wallet import Wallet

EFFECT = "xinshen"  # 商品效果（content/mall.json 的凝神香）：買一件存幾點
SPENT = "xinshen_spent"  # 購買那一列 data 裡：這一筆用掉了幾點
CARD_KEY = "pill_cap"  # 月卡記在 mall_entitlements 的哪一格（同 core.services.CARD_KEY；這裡不 import services，免得繞回 Game）


def on(content: Content) -> bool:
    return content.config.xinshen.enabled


@dataclass(frozen=True)
class Purse:
    """此刻手上的心神：免費、月卡、存著的三份。"""

    free: int
    card: int
    bank: int

    @property
    def daily(self) -> int:
        return self.free + self.card

    @property
    def total(self) -> int:
        return self.free + self.card + self.bank

    def can(self, n: int, free_only: bool = False) -> bool:
        return (self.free if free_only else self.total) >= n


# ── 存著的（帳號） ─────────────────────────────


def card_active(wallet: Wallet | None, owner: str, day: int) -> bool:
    """今天在不在月卡的期間裡（開始日～到期日，不含到期日）。"""
    if wallet is None:
        return False
    span = wallet.card(owner, CARD_KEY)
    return span is not None and span[0] <= day < span[1]


def _lots(wallet: Wallet, owner: str) -> list[tuple[int, int]]:
    """沒退的凝神香，舊的在前：(購買 id, 這一筆還剩幾點)。"""
    out = []
    for b in reversed(wallet.purchases(owner)):
        n = int(b.data.get(EFFECT, 0))
        if b.refunded is None and n:
            out.append((b.id, max(0, n - int(b.data.get(SPENT, 0)))))
    return out


def bank(wallet: Wallet | None, owner: str) -> int:
    """存著的還剩幾點；商城關著（wallet 是 None）是 0（點數還在資料庫裡，開回來原數回來）。"""
    if wallet is None:
        return 0
    return sum(left for _, left in _lots(wallet, owner))


def use_bank(wallet: Wallet, owner: str, n: int) -> None:
    """從最舊的那一筆扣起，扣 n 點（呼叫端先確定夠）。"""
    for pid, left in _lots(wallet, owner):
        if n <= 0:
            return
        take = min(n, left)
        if take:
            spent = int((wallet.purchase(pid).data or {}).get(SPENT, 0))
            wallet.update_data(pid, **{SPENT: spent + take})
            n -= take


# ── 每天的兩份（角色） ─────────────────────────


def free_left(state: GameState, content: Content, day: int) -> int:
    p = state.player
    return p.xinshen_free if p.xinshen_free_day == day else content.config.xinshen.free_daily


def card_left(state: GameState, content: Content, day: int, card: bool) -> int:
    p = state.player
    if not card:
        return 0
    return p.xinshen_card if p.xinshen_card_day == day else content.config.xinshen.card_daily


def purse(state: GameState, content: Content, day: int, card: bool, banked: int) -> Purse:
    return Purse(free=free_left(state, content, day), card=card_left(state, content, day, card), bank=banked)


def spend(state: GameState, content: Content, day: int, card: bool, banked: int, n: int, free_only: bool = False) -> int | None:
    """扣 n 點：夠就扣（改角色身上的兩份），回要從存著的扣幾點（呼叫端寫帳號）；不夠回 None、什麼都不動。"""
    have = purse(state, content, day, card, banked)
    if n <= 0:
        return 0
    if not have.can(n, free_only):
        return None
    p = state.player
    from_card = 0 if free_only else min(n, have.card)
    from_free = min(n - from_card, have.free)
    from_bank = n - from_card - from_free
    p.xinshen_free, p.xinshen_free_day = have.free - from_free, day
    if card:
        p.xinshen_card, p.xinshen_card_day = have.card - from_card, day
    return from_bank


# ── 寫給玩家看的字（待 joy 潤） ─────────────────


def cost_note(content: Content, n: int) -> str:
    return f"{content.config.xinshen.name} {n}"  # 待 joy 潤


def short_line(content: Content) -> str:
    """心神不夠的那一句。"""
    cfg = content.config.xinshen
    return f"{cfg.name}不足，明早 00:00 回到 {cfg.free_daily}。"  # 待 joy 潤


IDLE_NOTE = "今天的情誼已到頂"  # 待 joy 潤：每位人物前幾輪之後還能聊，但情誼與條件不再動
ASKS_DONE = "酒家擺擺手：「今天問得夠多了，明天再來吧。」"  # 待 joy 潤


def view(content: Content, have: Purse, card: bool) -> dict:
    """狀態列那一格：{name, now: 今天的兩份加起來, cap: 今天補到多少, bank: 存著的}。"""
    cfg = content.config.xinshen
    return {"name": cfg.name, "now": have.daily, "cap": cfg.free_daily + (cfg.card_daily if card else 0), "bank": have.bank}


# ── 本體（收 ctx；Game 上留一行委派）──────────────


def _xinshen_card(ctx) -> bool:
    return card_active(ctx._wallet(), ctx._mall_owner(), ctx._pill_day())


def xinshen_purse(ctx) -> Purse:
    """此刻手上的心神（免費、月卡、存著的三份）。"""
    return purse(ctx.state, ctx.content, ctx._pill_day(), _xinshen_card(ctx), bank(ctx._wallet(), ctx._mall_owner()))


def xinshen_spend(ctx, n: int, free_only: bool = False) -> bool:
    """扣 n 點心神：一般交談先扣月卡、再扣免費、最後動存著的；free_only（女性角色的隱線）只扣免費那一份。夠就扣、回 True。"""
    wallet = ctx._wallet()
    from_bank = spend(ctx.state, ctx.content, ctx._pill_day(), _xinshen_card(ctx),
                      bank(wallet, ctx._mall_owner()), n, free_only)
    if from_bank is None:
        return False
    if from_bank:
        use_bank(wallet, ctx._mall_owner(), from_bank)
    return True


def xinshen_view(ctx) -> dict | None:
    """狀態列的心神那一格；關著是 None。"""
    if not on(ctx.content):
        return None
    return view(ctx.content, ctx.xinshen_purse(), _xinshen_card(ctx))
