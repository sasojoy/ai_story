"""素材與經濟（docs/superpowers/specs/2026-10-15-素材與經濟-design.md；企劃者 2026-10-15 同意）的純規則：
鐵匠鋪收購（第五節）、升階（第四節）、大本營捐軍備（第六節）的價錢、比例、每日上限、軍備的名字、捐軍備推哪一條線。

只改傳進來的 GameState（背包、銀兩、當天的計數）與回傳訊息；人在不在鐵匠鋪、在不在自家大本營、店開著沒、紀錄、推大勢、
記貢獻、軍備存量都在 engine.Game（smith_sell／smith_upgrade／donate）。「一天」照回體丹的換日（Game._pill_day，台灣 00:00），
由呼叫端傳 day。開關在 Config.economy（sell／upgrade／donate），這裡的函式不看開關（呼叫端先問）。升階出來的是哪一種擲自己的亂數
（upgrade_rng：季數｜名號｜這一季第幾次升階｜換到幾階），不碰 Game.rng。"""
from __future__ import annotations

import random

from . import materials, rules, territory
from .models import Content, Material
from .state import GameState, WorldState

# 玩家看得到的字（待 joy 潤）
SELL_DONE = "鐵匠收下{item}，數了 {silver} 兩給你。"
SELL_TIER3 = "三階的料鐵匠不收——留著打神器吧"
SELL_NONE = "你身上沒有這樣東西"
SELL_SHORT = "{name}只有 {have} 個"
UPGRADE_DONE = "鐵匠把 {count} 個{low}下爐熬煉，煉出一個【{high}】。"
UPGRADE_ASTRAY = "鐵匠把 {count} 個{low}下爐熬煉，火候一偏，煉出的是一個【{high}】。"  # 出來的不是投入的屬性
UPGRADE_ODDS = "{share}出{name}，其餘隨機"  # 鈕上與素材頁的機率（企劃者 2026-10-15：先寫出來，之後要不要藏等試玩）
UPGRADE_SURE = "出{name}"  # upgrade_same_share 是 1（或同一階沒有別的屬性）：一定照投入的屬性
UPGRADE_DAY_FULL = "三階一天只煉得出一個，明日 00:00 後再來"
UPGRADE_NO_WAY = "這一階煉不出來"
UPGRADE_NO_KIND = "沒有這樣的料"
UPGRADE_SHORT = "{name}不夠：要 {need} 個，手上 {have} 個"
SILVER_SHORT = "還差 {short} 兩"  # 同 weapons／smithing 的寫法：店面掌櫃那一句照「還差」認錢不夠（shopview.problem_key）
DONATE_DONE = "你把{items}交給軍需官，記進{faction}的軍備。"
DONATE_FULL = "今天已捐滿 {cap} 點，明日 00:00 後再捐"
DONATE_TOO_BIG = "這一樣一個就 {points} 點，今天只剩 {room} 點收得下"
DONATE_NONE = "你身上沒有這樣東西"
DONATE_KEPT = "（收不下的 {n} 個{name}留在你身上。）"
DONATE_TITLE = "捐軍備"  # 江湖紀錄的標題、大本營那一顆的名字
DONATE_OPEN = "你來到軍需官的帳前，看看身上有什麼能交給{faction}。"
DONATE_LEFT = "今天還能捐 {n} 點"
DONATE_BUTTON = "捐【{name}】×{n}（{points} 點・{armament}）"
DONATE_REFUSED = "捐【{name}】（{problem}）"
DONATE_BACK = "離開軍需官"
DONATE_CLOSED = "你向軍需官拱拱手，離開了。"
DONATE_MISC = "雜項"  # 不在 armaments 表上的屬性（陰陽虛實）：照收、記貢獻，但不進存量
# 鐵匠鋪素材頁的鈕（店面關著、整季機器人與假人走的那一串選單；待 joy 潤）
SELL_LABEL = "賣【{name}】一個（{price} 兩・手上 {have}）"
UPGRADE_LABEL = "熬【{low}】×{need}（{cost} 兩・{odds}{left}）"
UPGRADE_LEFT = "・今天還能換 {n} 個"
UPGRADE_REFUSED = "熬【{low}】×{need}（{problem}）"


ATTRIBUTE_ORDER = ("剛", "柔", "快", "慢")  # 列升階的順序（同 shopview.ATTRIBUTE_ROWS）；其餘屬性排在後面


def _material(content: Content, mid: str) -> Material | None:
    return content.materials.get(mid)


def upgradable(content: Content) -> list[tuple[str, int]]:
    """換得出來的（屬性, 換到幾階）：Config.economy.upgrade_need 的每一階、這一階與低一階都有這個屬性的素材（正式內容剛柔快慢 × 二、三階）。
    照屬性（ATTRIBUTE_ORDER）、再照階排。"""
    attrs = sorted({m.attribute for m in content.materials.values()},
                   key=lambda a: (ATTRIBUTE_ORDER.index(a), "") if a in ATTRIBUTE_ORDER else (len(ATTRIBUTE_ORDER), a))
    tiers = sorted(t for t in content.config.economy.upgrade_need if t > 1)
    return [(a, t) for a in attrs for t in tiers if _of(content, a, t) is not None and _of(content, a, t - 1) is not None]


def upgrade_pair(content: Content, attribute: str, tier: int) -> tuple[Material, Material]:
    """（換出來的那一種, 拿去換的那一種）；upgradable 列出來的才叫。"""
    return _of(content, attribute, tier), _of(content, attribute, tier - 1)


def _of(content: Content, attribute: str, tier: int) -> Material | None:
    """這個屬性、這一階的素材（正式內容一種一個）；沒有是 None（materials.by_tier 退回同階全部的那一招這裡不要）。"""
    return next((m for m in materials.by_tier(content, tier) if m.attribute == attribute), None)


# ── 收購（第五節）──────────────────────────────────────────


def sell_price(content: Content, tier: int) -> int | None:
    """一個這一階的素材收多少兩；不在表上的階（三階）不收，是 None。收購價不分地盤。"""
    return content.config.economy.sell_price.get(tier)


def sell_problem(state: GameState, content: Content, mid: str, count: int = 1) -> str | None:
    """賣 count 個 mid 不行的原因；可以時是 None。"""
    material = _material(content, mid)
    have = materials.held(state, mid)
    if material is None or have <= 0:
        return SELL_NONE
    if sell_price(content, material.tier) is None:
        return SELL_TIER3
    if count <= 0 or count > have:
        return SELL_SHORT.format(name=material.name, have=have)
    return None


def sell(state: GameState, content: Content, mid: str, count: int = 1) -> list[str]:
    """賣 count 個 mid：扣背包、加銀兩，回那一句與「銀兩 +N」。不行時什麼都不動、只回原因。"""
    problem = sell_problem(state, content, mid, count)
    if problem is not None:
        return [problem]
    silver = sell_price(content, content.materials[mid].tier) * count
    materials.take(state, mid, count)
    p = state.player
    p.stats["silver"] = p.stats.get("silver", 0) + silver
    return [SELL_DONE.format(item=materials.item_text(content, mid, count), silver=silver), f"銀兩 +{silver}"]


# ── 升階（第四節）──────────────────────────────────────────


def upgrade_cost(state: GameState, content: Content, tier: int) -> int:
    """換一個 tier 階的工錢：Config.economy.upgrade_silver 乘所在地的地盤福利（territory.price_factor），四捨五入（同 smithing.price）。"""
    base = content.config.economy.upgrade_silver.get(tier, 0)
    p = state.player
    return int(base * territory.price_factor(state.world, content, p.faction, p.location) + 0.5)


def upgrade_outcomes(content: Content, attribute: str, tier: int) -> list[tuple[Material, float]]:
    """換一個 tier 階會出哪一種、各幾成（企劃者 2026-10-15「屬性隨機、偏向投入的」）：投入的那個屬性 upgrade_same_share，
    其餘平均分給同一階其他屬性的素材（每個屬性一種，照 ATTRIBUTE_ORDER）；同一階沒有別的屬性時一定是投入的那個。
    第一個一定是投入的屬性。upgradable 列出來的才叫。"""
    same = _of(content, attribute, tier)
    others = [m for a, t in upgradable(content) if t == tier and a != attribute and (m := _of(content, a, tier)) is not None]
    share = content.config.economy.upgrade_same_share
    if not others or share >= 1:
        return [(same, 1.0)]
    rest = (1 - share) / len(others)
    return [(same, share)] + [(m, rest) for m in others]


def share_word(share: float) -> str:
    """幾成（0.5 →「五成」）；不是整成的寫百分比。"""
    tenths = round(share * 10)
    return f"{rules.count_word(tenths)}成" if abs(share * 10 - tenths) < 1e-9 and 1 <= tenths <= 9 else f"{round(share * 100)}%"


def upgrade_odds(content: Content, attribute: str, tier: int) -> str:
    """鈕上與素材頁那一句：「五成出流雲絮，其餘隨機」；一定照投入的屬性時「出流雲絮」。"""
    outcomes = upgrade_outcomes(content, attribute, tier)
    same, share = outcomes[0]
    return UPGRADE_SURE.format(name=same.name) if len(outcomes) == 1 else UPGRADE_ODDS.format(share=share_word(share), name=same.name)


def upgrade_rng(state: GameState, tier: int) -> random.Random:
    """這一次升階擲哪一種的亂數：季數｜名號｜這一季第幾次升階（PlayerState.upgrade_seq＋1）｜換到幾階。決定性，不動 Game.rng。"""
    p = state.player
    return random.Random(f"升階|{p.season_number}|{p.name}|{p.upgrade_seq + 1}|{tier}")


def roll_upgrade(state: GameState, content: Content, attribute: str, tier: int) -> Material:
    """這一次會出哪一種（不改狀態）：只有一種可能時不擲骰。"""
    outcomes = upgrade_outcomes(content, attribute, tier)
    if len(outcomes) == 1:
        return outcomes[0][0]
    rng = upgrade_rng(state, tier)
    return rng.choices([m for m, _ in outcomes], weights=[w for _, w in outcomes])[0]


def _today(p, day: int) -> dict[int, int]:
    return p.upgrades_today if p.upgrade_day == day else {}


def upgrade_left(state: GameState, content: Content, tier: int, day: int) -> int | None:
    """今天還能換幾個 tier 階（Config.economy.upgrade_per_day）；不限是 None。"""
    cap = content.config.economy.upgrade_per_day.get(tier)
    if cap is None:
        return None
    return max(0, cap - _today(state.player, day).get(tier, 0))


def upgrade_problem(state: GameState, content: Content, attribute: str, tier: int, day: int) -> str | None:
    """把同屬性低一階的換一個 tier 階不行的原因；可以時是 None。照這個順序擋：換不出這一階、沒有這樣的料、今天的上限、料不夠、錢不夠。"""
    econ = content.config.economy
    need = econ.upgrade_need.get(tier)
    high, low = _of(content, attribute, tier), _of(content, attribute, tier - 1)
    if need is None or tier <= 1:
        return UPGRADE_NO_WAY
    if high is None or low is None:
        return UPGRADE_NO_KIND
    if upgrade_left(state, content, tier, day) == 0:
        return UPGRADE_DAY_FULL
    have = materials.held(state, low.id)
    if have < need:
        return UPGRADE_SHORT.format(name=low.name, need=need, have=have)
    short = upgrade_cost(state, content, tier) - state.player.stats.get("silver", 0)
    if short > 0:
        return SILVER_SHORT.format(short=short)
    return None


def upgrade(state: GameState, content: Content, attribute: str, tier: int, day: int) -> list[str]:
    """換一個：扣同屬性低一階的 upgrade_need 個與工錢，照 upgrade_outcomes 擲出一個 tier 階（roll_upgrade）、記今天的數
    （每日上限照換了幾次算，不管出來的是什麼屬性）。不行時什麼都不動、只回原因。"""
    problem = upgrade_problem(state, content, attribute, tier, day)
    if problem is not None:
        return [problem]
    p = state.player
    need = content.config.economy.upgrade_need[tier]
    low = _of(content, attribute, tier - 1)
    got_material = roll_upgrade(state, content, attribute, tier)
    p.upgrade_seq += 1
    cost = upgrade_cost(state, content, tier)
    materials.take(state, low.id, need)
    p.stats["silver"] = p.stats.get("silver", 0) - cost
    if tier in content.config.economy.upgrade_per_day:
        counts = dict(_today(p, day))
        counts[tier] = counts.get(tier, 0) + 1
        p.upgrade_day, p.upgrades_today = day, counts
    got = materials.grant(state, content, got_material.id)
    line = UPGRADE_DONE if got_material.attribute == attribute else UPGRADE_ASTRAY
    msgs = [line.format(count=need, low=low.name, high=got_material.name)]
    return msgs + ([got] if got else []) + ([f"銀兩 -{cost}"] if cost else [])


# ── 捐軍備（第六節）──────────────────────────────────────────


def donate_points(content: Content, mid: str) -> int:
    """一個 mid 記幾點貢獻（糧草的份量：一階 1、二階 3、三階 9）；不認得的是 0。"""
    material = _material(content, mid)
    return content.config.economy.donate_points.get(material.tier, 0) if material is not None else 0


def donate_room(state: GameState, content: Content, day: int) -> int:
    """今天還能捐幾點（Config.economy.donate_daily_cap，回體丹的換日）。"""
    p = state.player
    used = p.donated_today if p.donate_day == day else 0
    return max(0, content.config.economy.donate_daily_cap - used)


def donate_take(state: GameState, content: Content, mid: str, count: int, day: int) -> int:
    """想捐 count 個 mid，今天收得下幾個：手上有的、而且份量不超過今天剩的點數（上限切一半：收得下的收，其餘留著）。"""
    points = donate_points(content, mid)
    if points <= 0 or count <= 0:
        return 0
    return max(0, min(count, materials.held(state, mid), donate_room(state, content, day) // points))


def donate_problem(state: GameState, content: Content, mid: str, day: int) -> str | None:
    """捐 mid 一個都捐不了的原因；捐得了（至少一個）時是 None。在不在自家大本營由 Game 問。"""
    points = donate_points(content, mid)
    if points <= 0 or materials.held(state, mid) <= 0:
        return DONATE_NONE
    room = donate_room(state, content, day)
    if room <= 0:
        return DONATE_FULL.format(cap=content.config.economy.donate_daily_cap)
    if points > room:
        return DONATE_TOO_BIG.format(points=points, room=room)
    return None


def take_donation(state: GameState, content: Content, mid: str, count: int, day: int) -> int:
    """真的收下：照 donate_take 扣背包、記今天的點數，回收下的點數（0＝一個都沒收）。軍備存量與貢獻由 Game 記。"""
    taken = donate_take(state, content, mid, count, day)
    if taken <= 0:
        return 0
    points = taken * donate_points(content, mid)
    materials.take(state, mid, taken)
    p = state.player
    p.donated_today = (p.donated_today if p.donate_day == day else 0) + points
    p.donate_day = day
    return points


def close_donate(state: GameState) -> None:
    """收起軍需官那一串與軍需帳上那一句（同 equipment.close_smith）：凡是把 picking_donate 設成 False 的地方都走這裡
    （離開、讀檔修補、同步時人不在自家大本營、出發）。"""
    p = state.player
    p.picking_donate = False
    p.shop_line, p.shop_clue, p.shop_hold = "", "", ""


def armament_of(content: Content, attribute: str) -> str | None:
    """素材屬性 → 陣營軍備的名字（慢 → 糧秣、快 → 箭矢、剛 → 甲冑、柔 → 戰馬）；其他屬性是 None（不進存量）。"""
    return content.config.economy.armaments.get(attribute)


def add_armament(world: WorldState, faction: str, attribute: str, points: int) -> None:
    """陣營軍備的存量照份量累積（PM 2026-10-15：一階 1、二階 3、三階 9）。"""
    if points <= 0:
        return
    stock = world.armaments.setdefault(faction, {})
    stock[attribute] = stock.get(attribute, 0) + points


def donate_target(content: Content, world: WorldState, faction: str, loc_id: str) -> tuple[str, int] | None:
    """捐軍備推哪一條線、往哪個方向（第六節第 2 點）：豪強（目標是割據的陣營）推割據；其餘推大本營所在那一條戰線
    （territory.line_of；不在戰線上的投靠點照所在大區的戰線，rules.front_of），往自己陣營的目標方向。鍵照 rules.resolve_trend 換過
    （規則關著的季三條戰線都是黃巾聲勢、沒有割據）；推不了是 None。"""
    found = content.scenario.find_faction(faction)
    if found is None:
        return None
    key = rules.GEJU if found.goals.get(rules.GEJU, 0) > 0 else (territory.line_of(content, loc_id) or rules.front_of(content, loc_id))
    if key is None:
        return None
    target = rules.resolve_trend(content, world, key, loc_id)
    direction = rules.resolve_goals(content, world, found.goals).get(target, 0) if target is not None else 0
    return (target, direction) if target is not None and direction else None


def donate_push(content: Content, points: int) -> float:
    """捐 points 點推大勢的量（PM 2026-10-15 同意）：每點 donate_push_per_point，再打事件的五折（Config.explore_modes.event_trend_share）。
    季長倍數與盡頭阻力在 Game.push_trend（source="donate"）再打，跟出陣共用每人每日的推力上限。"""
    return points * content.config.economy.donate_push_per_point * content.config.explore_modes.event_trend_share
