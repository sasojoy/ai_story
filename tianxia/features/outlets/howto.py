"""銀兩出口包：玩法說明「素材的出路」那一節（全部拆包第 59 批；原 tianxia/howto.py，字一個不動；順序在核心 HOWTO_ORDER）。"""
from __future__ import annotations

from tianxia import economy, four_tiers, renown, rules
from tianxia.core.howto_base import section as _section
from tianxia.models import Content
from tianxia.state import WorldState

ECONOMY_TITLE = "素材的出路"  # 待 joy 潤：玩法說明那一節的標題（素材與經濟設計第四～六節）


def economy_lines(content: Content, allied: bool = False) -> list[str]:
    """玩法說明「素材的出路」一節（Config.economy 的收購、升階、捐軍備，開著的才寫；都關著是空的；待 joy 潤）。數字讀 Config。
    allied：豪強分屬兩軍的季，豪強捐的進依附那一邊、在自己的莊院與那一邊的大本營都能捐（新寫）。"""
    econ = content.config.economy
    reset = "台灣時間 00:00 換日" if content.config.pill_day_utc_offset_hours == 8 else "每天 00:00 換日"
    tier_word = {1: "一階", 2: "二階", 3: "三階", 4: "四階"}
    four = four_tiers.on(content)
    lines = []
    if econ.sell:
        tiers = economy.sell_tiers(content)
        prices = [f"{tier_word.get(t, f'{t}階')} {econ.sell_price[t]} 兩" for t in tiers]
        prices[0] = prices[0].replace(" ", "一個 ", 1)  # 「一階一個 2 兩、二階 6 兩」
        refused = "四階不收，留著打神器" if four else "三階不收，留著打神器"  # 素材四階（正式季整合 4.2）
        lines.append(f"城鎮的鐵匠鋪收素材：{'、'.join(prices)}；{refused}。")
        rcfg = content.config.renown
        dark_prices = {t: p for t, p in rcfg.black_market_prices.items() if t in tiers}
        if renown.on(content, "black_market") and dark_prices:  # 名聲 5.2：寇的黑市價（待 joy 潤）
            title = renown.VIRTUE_TITLES["寇"][rcfg.black_market_tier]
            dark = "、".join(f"{tier_word.get(t, f'{t}階')} {p} 兩" for t, p in sorted(dark_prices.items()))
            lines.append(f"走寇的路、到了「{title}」，鐵匠照黑市價收：{dark}。")
    if econ.upgrade:
        steps = []
        needs = economy.upgrade_needs(content)
        for tier in sorted(needs):
            if four:  # 素材四階：一般的不設每日上限，三換四一季幾個、一定同屬性（4.2、4.5）
                cap_text = f"，一季{four_tiers.count_text(content.config.four_tiers.season_cap)}個、一定出同屬性" if tier == four_tiers.TIER else ""
            else:
                cap = econ.upgrade_per_day.get(tier)
                cap_text = f"，一天{rules.count_word(cap)}個，{reset}" if cap is not None else ""
            cost = content.config.four_tiers.upgrade_silver if four and tier == four_tiers.TIER else econ.upgrade_silver.get(tier, 0)
            steps.append(f"{tier_word.get(tier - 1)}{rules.count_word(needs[tier])}個換一個{tier_word.get(tier)}"
                         f"（工錢 {cost} 兩{cap_text}）")
        astray = ""
        if econ.upgrade_same_share < 1:  # 升階隨機（企劃者 2026-10-15）：投入的屬性幾成，其餘落到別的屬性
            share = round(econ.upgrade_same_share * 10)
            astray = f"熬出來的約 {share} 成是同屬性的，其餘隨機落到別的屬性。"
        lines.append(f"鐵匠鋪也幫你把素材熬成高一階的：同屬性的{'；'.join(steps)}。{astray}工錢照地盤福利算。")
    if econ.donate:
        points = "、".join(f"{tier_word[t]} {n} 點" for t, n in sorted(econ.donate_points.items()) if t in tier_word)
        names = "、".join(econ.armaments.values())
        where = "（豪強：自己的莊院與依附那一邊的大本營都算）" if allied else ""
        gentry = "（豪強捐的進依附那一邊）" if allied else ""
        lines.append(
            f"投靠了陣營，在自家的大本營{where}可以捐軍備：{points}，一天最多 {econ.donate_daily_cap} 點（{reset}）。"
            f"捐的記成貢獻（第一季），也把大本營那一條戰線往自家推一點{gentry}；素材累積成陣營的{names}，"
            "在大決戰怎麼用，之後再定。"
        )
    return lines


def economy_section(content: Content, season: WorldState) -> list[str]:
    """「素材的出路」那一節（HOWTO_ORDER 的 economy）：素材與經濟（收購、升階、捐軍備）開著的才寫；開頭多一個空行（背包那一節沒有末尾空行）。"""
    lines = economy_lines(content, rules.haoqiang_allied(content, season))
    return ["", *_section(ECONOMY_TITLE, lines)] if lines else []
