"""商城包：玩法說明「商城」那一節（全部拆包第 59 批；原 tianxia/howto.py，字一個不動；順序在核心 HOWTO_ORDER）。"""
from __future__ import annotations

from tianxia.core.howto_base import section as _section
from tianxia.models import Content

from . import rules as mall  # 商城開不開

MALL_TITLE = "商城"  # 玩法說明那一節的標題（商城第三批）；以下待 joy 潤
MALL_WHERE = "齒輪旁的元寶鈕、底部的「寶」都打開商城，架上的東西花元寶買；買過的、元寶的進出在「紀錄」那一頁查得到。"
MALL_COIN = "元寶只能儲值取得，不能拿銀兩換，也換不成銀兩。"
MALL_BETA = "這一版是封閉測試：每個角色第一次進來先撥 {n} 元寶（只發一次，之後開新的一季也不再發），正式開服時清空。"
MALL_CARD = "月卡：有效的那幾天，每天能服的{pill}多 {bonus} 顆（{caps}）。買的那一天算第一天；還沒到期再買，從到期日往後接。"


def mall_lines(content: Content) -> list[str]:
    """玩法說明「商城」那一節（商城架構設計 4.2、4.5；商城第三批）：入口、元寶怎麼來、封測發放（Config.mall.beta_grant，0 不寫）、
    月卡（架上有月卡、回體丹一天有上限才寫；上限照 Config，跟 Game.pill_cap 加的同一份 card_pill_bonus）。不看個人：
    這個人此刻的上限寫在點體力條看的那幾句（stamina_lines 的 card，FB-480）。商城關著是空的（玩法說明一個字都不提）。"""
    if not mall.on(content):
        return []
    cfg = content.config
    lines = [MALL_WHERE, MALL_COIN]
    if cfg.mall.beta_grant > 0:
        lines.append(MALL_BETA.format(n=cfg.mall.beta_grant))
    bonus = cfg.mall.card_pill_bonus
    sells_card = any("card_days" in item.effects for item in content.mall.values())
    if sells_card and bonus > 0 and cfg.stamina_pills_per_day > 0:
        caps = [f"平常 {cfg.stamina_pills_per_day} → {cfg.stamina_pills_per_day + bonus}"]
        caps += [f"新手期 {cfg.newbie_pills_per_day} → {cfg.newbie_pills_per_day + bonus}"] * (cfg.newbie_pills_per_day > 0)
        lines.append(MALL_CARD.format(pill=cfg.stamina_pill_name, bonus=bonus, caps="、".join(caps)))
    return lines


def mall_section(content: Content) -> list[str]:
    """「商城」那一節（HOWTO_ORDER 的 mall）：開著才寫，關著一個字都不變；開頭多一個空行（前一節可能沒有末尾空行）。"""
    shop = mall_lines(content)
    return ["", *_section(MALL_TITLE, shop)] if shop else []
