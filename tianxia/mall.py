"""商城（docs/superpowers/specs/2026-10-20-商城架構-design.md）：元寶、商品、購買與發貨、月卡、封測發放、管理者工具的規則。

- 開關 Config.mall.enabled（on）：關著時什麼都不做、不讀不寫資料庫（月卡不加上限），呼叫端照舊。
- 商品寫在 content/mall.json（joy 寫），效果只能從允許的效果表 EFFECTS 挑（4.3：用允許表不用禁止表）；載入時 content.check_mall
  叫 item_problems 擋表外的。外觀、通行證的種類留著，允許表裡還沒有它們的效果，所以這一版寫不出來。
- 錢包的讀寫在 tianxia/wallet.py；這裡只排順序與寫字。一次購買：查重 → 上架 → 限購 → 餘額 → 寫購買紀錄 → 扣元寶 → 發貨，
  呼叫端（伺服器的行動鎖）是一筆交易，出錯整筆撤回（4.4）。
- 不讀時鐘：現實時間 now 與回體丹的那一天 day（Game._pill_day）都由呼叫端傳進來。

新寫給玩家看的字都待 joy 潤。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

from . import naming
from .models import Content, MallItem
from .wallet import Wallet


@dataclass(frozen=True)
class EffectSpec:
    kind: str  # 這個效果屬於哪一種商品（MallItem.kind）
    label: str  # 寫給玩家看的那一句；{n} 是數量、{pill} 是回體丹的名字、{bonus} 是月卡多幾顆
    max: int  # 一件商品最多寫多少


# 允許的效果表（4.3）：第一版只有回體丹與月卡。要加新的效果先改這張表、再上架；外觀、通行證開了才會有它們的效果。
EFFECTS: dict[str, EffectSpec] = {
    "pills": EffectSpec("consumable", "{pill} {n} 顆", 999),
    "card_days": EffectSpec("card", "月卡 {n} 天（每天多服 {bonus} 顆{pill}）", 366),
}
KIND_NAMES = {"look": "外觀", "consumable": "消耗品", "card": "月卡", "pass": "通行證"}
REASONS = {"grant": "封測發放", "buy": "購買", "refund": "退款", "reissue": "補發", "revoke": "扣回", "topup": "儲值"}
CARD_KEY = "pill_cap"  # 月卡記在 mall_entitlements 的哪一格（回體丹每天的上限）
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_EPOCH = date(1970, 1, 1)

TITLE = "商城"  # 江湖紀錄的標題（發放、購買）
GRANT_LINE = "封閉測試期間，帳上先撥給你 {n} 元寶，可以到商城看看。"  # 待 joy 潤


def on(content: Content) -> bool:
    return content.config.mall.enabled


def grant_ref(owner: str) -> str:
    return f"grant:beta:{owner}"


def grant_beta(content: Content, wallet: Wallet, owner: str, now: float) -> int:
    """封測發放（4.2）：這個錢包還沒發過就發 Config.mall.beta_grant，回發了幾個；發過了、數字是 0、開關關著回 0。
    編號只看主人（grant:beta:<主人>），所以換季、再登入、換一份設定都不會再發一次。"""
    amount = content.config.mall.beta_grant
    if not on(content) or amount <= 0:
        return 0
    return amount if wallet.post(owner, amount, "grant", grant_ref(owner), time=now) else 0


def card_bonus(content: Content, wallet: Wallet, owner: str, day: int) -> int:
    """月卡（4.5）：day 這一天在卡的期間裡（開始日～到期日，不含到期日）就回 Config.mall.card_pill_bonus，其餘 0。"""
    if not on(content):
        return 0
    span = wallet.card(owner, CARD_KEY)
    return content.config.mall.card_pill_bonus if span is not None and span[0] <= day < span[1] else 0


def date_day(text: str) -> int:
    """台灣日期 YYYY-MM-DD → 回體丹那一套的日數（Game._pill_day：照台灣日期、從 1970-01-01 起算）。格式不對丟 ValueError。"""
    if not _DATE.fullmatch(text or ""):
        raise ValueError(text)
    return (date.fromisoformat(text) - _EPOCH).days


def day_text(day: int) -> str:
    """日數 → 「10/25」（台灣日期）。"""
    d = _EPOCH + timedelta(days=day)
    return f"{d.month}/{d.day}"


def item_problems(item: MallItem, content: Content) -> list[str]:
    """一件商品哪裡寫錯（content.check_mall 用）；空的是可以上架。"""
    where = f"商城 {item.id}"
    out: list[str] = []
    if not item.effects:
        out.append(f"{where}：沒有效果")
    for key, n in item.effects.items():
        spec = EFFECTS.get(key)
        if spec is None:
            out.append(f"{where}：效果 {key} 不在允許的效果表裡（{'、'.join(EFFECTS)}）")
            continue
        if spec.kind != item.kind:
            out.append(f"{where}：效果 {key} 是{KIND_NAMES[spec.kind]}的，這件的種類寫{KIND_NAMES[item.kind]}")
        if not 1 <= n <= spec.max:
            out.append(f"{where}：{key} 的數量要 1～{spec.max}（寫了 {n}）")
    problem = naming.name_problem(item.name, content)
    if problem:
        out.append(f"{where}：名字「{item.name}」{problem}")
    window = item.on_sale
    days: list[int] = []
    for text in (window.start, window.end):
        if text is None:
            continue
        try:
            days.append(date_day(text))
        except ValueError:
            out.append(f"{where}：上架日期要寫 YYYY-MM-DD（寫了 {text}）")
    if window.start and window.end and len(days) == 2 and days[0] > days[1]:
        out.append(f"{where}：上架日期的開始（{window.start}）在結束（{window.end}）之後")
    if any(n < 1 for n in window.seasons):
        out.append(f"{where}：上架的季要是正整數（寫了 {window.seasons}）")
    return out
