"""陣營裡的階級（計畫 T5、第一季設計 5.2、5.3）：頭銜、召見、晉升、部下、每日彙整。

只有第一季的規則開著（rules.season_one）才有這些；開關關著時狀態列照舊寫「門派・陣營」。"""
from __future__ import annotations

from . import calendar, figures
from .models import Content, PromotionDef
from .rules import add_rumor, display_name, season_one
from .state import GameState, Summons

NEAREST_BASE = "nearest_base"  # promotions.json 的地點寫這個：照路網挑離玩家最近的那個陣營的投靠點（豪強，內容表 2.1）

# 第一季設計 5.2【定】：0 號是空字串（散人沒有階），1～4 是各陣營的頭銜
TITLES: dict[str, list[str]] = {
    "guan": ["", "鄉勇", "屯長", "軍司馬", "校尉"],
    "huang": ["", "信眾", "小帥", "小方渠帥", "大方渠帥"],
    "haoqiang": ["", "鄉里子弟", "宗族頭人", "地方豪強", "一方之主"],
}


def rank_of(state: GameState) -> int:
    """此刻的階：散人 0；投靠了就至少第 1 階（存檔裡記的是晉升過的階，投靠本身不寫）。"""
    p = state.player
    return 0 if p.faction is None else max(p.rank, 1)


def title(content: Content, state: GameState) -> str | None:
    """狀態列陣營後面的頭銜；第一季的規則沒開、散人、或陣營沒有頭銜表時是 None。"""
    if not season_one(content, state.world):
        return None
    titles = TITLES.get(state.player.faction or "")
    if not titles:
        return None
    return titles[min(rank_of(state), len(titles) - 1)] or None


def promotion_for(content: Content, faction: str | None, rank: int) -> PromotionDef | None:
    """那個陣營升到第 rank 階的晉升定義（promotions.json）；這一版只寫了第 2 階，其他是 None。"""
    return next((p for p in content.promotions if p.faction == faction and p.rank == rank), None)


def summons_place(state: GameState, content: Content, promo: PromotionDef) -> str:
    """召見的地點：寫死的照寫；nearest_base 照路網挑離玩家所在最近的那個陣營投靠點（一樣近照劇本列的順序），
    都走不到時是列的第一個。"""
    if promo.location != NEAREST_BASE:
        return promo.location
    from . import atlas  # noqa: PLC0415  atlas → world → ranks：在函式裡 import，避免循環

    bases = next(f.join_at for f in content.scenario.factions if f.id == promo.faction)
    routes = atlas.shortest_routes(state, content)
    here = state.player.location
    reachable = [loc for loc in bases if loc == here or loc in routes]
    if not reachable:
        return bases[0]
    return min(reachable, key=lambda loc: 0.0 if loc == here else routes[loc].minutes)


def presenter(state: GameState, content: Content, promo: PromotionDef, location: str) -> tuple[str | None, bool]:
    """出面的人與要不要演接手版（晉升文件第一節「人物不在」）：主版人物此刻在召見地點（在場）就是他；不在就換接手的人，
    演接手版——接手的人也不在仍演接手版（內容只寫了兩版）。沒有出面人物的（豪強的中山馬商）是 (None, False)。"""
    if promo.figure is None:
        return None, False
    if promo.successor is None or promo.figure in figures.present_at(state, content, location):
        return promo.figure, False
    return promo.successor, True


def _summons_text(content: Content, promo: PromotionDef, handoff: bool, location: str) -> str:
    text = promo.summons_handoff if handoff and promo.summons_handoff else promo.summons_text
    return text.replace("{據點}", content.locations[location].name)


def check_summons(state: GameState, content: Content) -> list[str]:
    """該不該發召見（每次行動、同步的最後檢查，所以貢獻從哪裡來都接得到）：第一季、有陣營、這一季還沒落幕、手上沒有召見、
    下一階有定義、本季貢獻夠了（第 2 階 rank2_contrib）→ 記下召見，回傳召見那一句。同一階只發一次（召見沒有期限，
    演完晉升才清掉）。"""
    p, w = state.player, state.world
    if not season_one(content, w) or p.faction is None or p.summons is not None or w.ended:
        return []
    promo = promotion_for(content, p.faction, rank_of(state) + 1)
    if promo is None or promo.rank != 2 or p.contrib < content.config.rank2_contrib:
        return []
    location = summons_place(state, content, promo)
    fid, handoff = presenter(state, content, promo, location)
    p.summons = Summons(rank=promo.rank, figure=fid, location=location, since=w.time)
    return [_summons_text(content, promo, handoff, location)]


def summons_line(state: GameState, content: Content) -> str | None:
    """還沒去的召見那一句，照此刻出面的人重寫（召見發出後人物才不在的，自動改由接手的人發；主線與目標列它）。"""
    p = state.player
    promo = _pending(state, content)
    if promo is None:
        return None
    _, handoff = presenter(state, content, promo, p.summons.location)
    return _summons_text(content, promo, handoff, p.summons.location)


def summons_event(state: GameState, content: Content) -> str | None:
    """人在召見的地點時該演的晉升奇遇（主版或接手版，照此刻出面的人）；不在那裡、沒有召見、開關關著是 None。"""
    p = state.player
    promo = _pending(state, content)
    if promo is None or p.location != p.summons.location:
        return None
    _, handoff = presenter(state, content, promo, p.location)
    return promo.event_handoff if handoff and promo.event_handoff else promo.event_main


def _pending(state: GameState, content: Content) -> PromotionDef | None:
    p = state.player
    if p.summons is None or not season_one(content, state.world):
        return None
    return promotion_for(content, p.faction, p.summons.rank)


def promote(state: GameState, content: Content, rank: int) -> list[str]:
    """晉升奇遇選項的 promote（rules.apply_effect 呼叫）：升到 rank、清掉召見，接「你升為X。」與結尾那一句；
    記進當天的彙整（第 2 階每天一則陣營軍情，flush_news）。開關關著、散人什麼都不做。"""
    p, w = state.player, state.world
    if not season_one(content, w) or p.faction is None:
        return []
    p.rank, p.summons = rank, None
    msgs = [f"你升為{TITLES[p.faction][rank]}。"] if p.faction in TITLES else []
    promo = promotion_for(content, p.faction, rank)
    if promo is not None and promo.closing:
        msgs.append(promo.closing)
    day = calendar.point(w.time, content, w).cal_day
    w.promoted_today.setdefault(f"{day}:{p.faction}:{rank}", []).append(display_name(state))
    return msgs


def add_followers(state: GameState, content: Content, follower_ids: list[str]) -> list[str]:
    """晉升奇遇給的部下（部下模板 id）：加進 PlayerState.followers，回傳「獲得部下：X、Y」。開關關著什麼都不做。"""
    if not follower_ids or not season_one(content, state.world):
        return []
    state.player.followers += follower_ids
    return ["獲得部下：" + "、".join(content.followers[f].name for f in follower_ids)]


def flush_news(state: GameState, content: Content, before_day: int | None) -> None:
    """發掉曆日早於 before_day 的晉升彙整（None＝全部，收季時用）：每個曆日、每個陣營、每一階一則陣營軍情
    「昨日升為屯長的有：甲、乙。」（收季時當天的寫「今日」）。傳聞只能新增不能改，所以過了那一天才發。"""
    w = state.world
    if not w.promoted_today:
        return
    today = calendar.point(w.time, content, w).cal_day
    for key in list(w.promoted_today):
        day_text, faction, rank_text = key.split(":")
        day, rank = int(day_text), int(rank_text)
        if before_day is not None and day >= before_day:
            continue
        names = w.promoted_today.pop(key)
        titles = TITLES.get(faction)
        if titles is None or not 0 < rank < len(titles):
            continue
        when = "今日" if day >= today else "昨日"
        add_rumor(state, f"{when}升為{titles[rank]}的有：{'、'.join(names)}。", content=content, layer="faction",
                  faction=faction)
