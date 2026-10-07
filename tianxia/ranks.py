"""陣營裡的階級（計畫 T5、第一季設計 5.2、5.3）：頭銜、召見、晉升、部下、每日彙整。

只有第一季的規則開著（rules.season_one）才有這些；開關關著時狀態列照舊寫「門派・陣營」。"""
from __future__ import annotations

from . import calendar, figures, seats
from .models import Content, PromotionCast, PromotionDef
from .rules import add_rumor, season_one
from .state import GameState, Summons

NEAREST_BASE = "nearest_base"  # promotions.json 的地點寫這個：照路網挑離玩家最近的那個陣營的投靠點（豪強，內容表 2.1）
HINT = "你在陣營裡已小有名氣，只缺一個讓大人物記住你的機會。"  # 機緣文件第一節：第 3、4 階進度到了、機緣還沒有（每階說一次）

SEAT_RANK = seats.SEAT_RANK  # 有資格而且這一週在任（seats.seated）的人此刻的階：rank_of 回這個，存檔的 rank 不動（正式版丁）；階號只在 seats 寫一次
HIGHEST_RANK = SEAT_RANK - 1  # PlayerState.rank 最高到這裡：第 4 階只是資格（qualified，候缺）加上這一週的席次，求見門檻不看資格也不看席次

# 第一季設計 5.2【定】：0 號是空字串（散人沒有階），1～4 是各陣營的頭銜
TITLES: dict[str, list[str]] = {
    "guan": ["", "鄉勇", "屯長", "軍司馬", "校尉"],
    "huang": ["", "信眾", "小帥", "小方渠帥", "大方渠帥"],
    "haoqiang": ["", "鄉里子弟", "宗族頭人", "地方豪強", "一方之主"],
}


def rank_of(state: GameState) -> int:
    """此刻的階：散人 0；投靠了就至少第 1 階（存檔裡記的是晉升過的階，投靠本身不寫）；有第四階資格而且這一週在任
    （seats.seated，正式版丁）是 4。存檔的 PlayerState.rank 仍停在 HIGHEST_RANK：4 只是此刻的身份，週一被擠下來就回到 3。"""
    p = state.player
    if p.faction is None:
        return 0
    if p.qualified and seats.seated(state):
        return SEAT_RANK
    return max(p.rank, 1)


def title(content: Content, state: GameState) -> str | None:
    """狀態列陣營後面的頭銜；第一季的規則沒開、散人、或陣營沒有頭銜表時是 None。"""
    if not season_one(content, state.world):
        return None
    titles = TITLES.get(state.player.faction or "")
    if not titles:
        return None
    if state.player.qualified and rank_of(state) < SEAT_RANK:  # 有第 4 階資格、這一週沒在任（候缺）；在任的往下讀第 4 階的頭銜
        return f"{titles[3]}（{titles[4]}候缺）"  # 「X（Y候缺）」的寫法是新寫的初稿，待 joy 潤
    return titles[min(rank_of(state), len(titles) - 1)] or None


def promotion_for(content: Content, faction: str | None, rank: int) -> PromotionDef | None:
    """那個陣營升到第 rank 階的晉升定義（promotions.json，第 2 到 4 階）；沒寫的階是 None。"""
    return next((p for p in content.promotions if p.faction == faction and p.rank == rank), None)


def next_rank_up(state: GameState, content: Content) -> int | None:
    """下一次晉升真的會升階（PlayerState.rank 加一）的那一階；沒有的是 None：下一階沒有定義、或下一階只是資格（第 4 階，
    rank 停在 3、求見門檻不降）。被打發時的「或在某某再升一階」只許諾這種晉升。"""
    rank = rank_of(state) + 1
    if rank > HIGHEST_RANK or promotion_for(content, state.player.faction, rank) is None:
        return None
    return rank


def threshold(content: Content, rank: int) -> int:
    """升到第 rank 階要的本季貢獻（第 2 階 rank2_contrib，第 3、4 階另外還要完成過那一階的一種機緣）。"""
    cfg = content.config
    return {2: cfg.rank2_contrib, 3: cfg.rank3_contrib, 4: cfg.rank4_contrib}[rank]


def summons_place(state: GameState, content: Content, promo: PromotionDef) -> str:
    """召見的地點：寫死的照寫；nearest_base 照路網挑離玩家所在最近的那個陣營投靠點（一樣近照劇本列的順序），
    都走不到時是列的第一個。"""
    if promo.location != NEAREST_BASE:
        return promo.location
    from . import atlas  # noqa: PLC0415  atlas → world → ranks：在函式裡 import，避免循環

    bases = content.scenario.faction(promo.faction).join_at
    routes = atlas.shortest_routes(state, content)
    here = state.player.location
    reachable = [loc for loc in bases if loc == here or loc in routes]
    if not reachable:
        return bases[0]
    return min(reachable, key=lambda loc: 0.0 if loc == here else routes[loc].minutes)


def scout(state: GameState, content: Content, location: str) -> None:
    """把到召見地點的路摸清（企劃者裁決 E2）：從所在地到 location 路程最短的那一條（所有已開放的地點，同 summons_place），
    路上沒去過的站（含終點）記進 PlayerState.surveyed。此刻看得見的站也記：召見是之後才從別處動身的，人走開就看不見了。
    去過的站本來就記得，玩家之後走過的路也都是去過的，所以從哪裡動身都接得上這一條。發召見、往下一段、換人換了地點時呼叫；
    不另說話（同送別時的留意地形）。到不了（沒有路）或就在這裡時什麼都不做。"""
    from . import atlas  # noqa: PLC0415  atlas → world → ranks：在函式裡 import，避免循環

    route = atlas.shortest_routes(state, content).get(location)
    if route is not None:
        p = state.player
        p.surveyed |= set(route.path) - p.visited


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


def _cast_ok(state: GameState, content: Content, cast: PromotionCast, prev: str | None) -> bool:
    """這個版本此刻成立嗎：上一段演的是它的 after、它的 before_event 那件大事還沒結算、flags_none 的旗標都不在；
    寫了 figure 的，那位人物要在場（active、有所在），寫了 at 的還要正好在那裡。"""
    w = state.world
    if cast.after is not None and cast.after != prev:
        return False
    if cast.before_event is not None and cast.before_event in w.timeline:
        return False
    if any(flag in w.flags for flag in cast.flags_none):
        return False
    if cast.figure is not None:
        now = figures.state_of(state, content, cast.figure)
        if now.status != "active" or not now.location:
            return False
        if cast.at is not None and now.location != cast.at:
            return False
    return True


def current_cast(
    state: GameState, content: Content, promo: PromotionDef, leg: int, prev: str | None,
) -> tuple[PromotionCast, str] | None:
    """這一段此刻該演的版本與地點：照順序第一個成立的（晉升奇遇文件第一節）。地點：cast.at；沒寫 at 但有 figure 是
    那位此刻的所在；都沒寫是這一段的 location（nearest_base 照 T5 挑最近的投靠點）。沒有成立的、沒有這一段是 None。"""
    if leg >= len(promo.legs):
        return None
    part = promo.legs[leg]
    for cast in part.casts:
        if not _cast_ok(state, content, cast, prev):
            continue
        if cast.at is not None:
            return cast, cast.at
        if cast.figure is not None:
            return cast, figures.state_of(state, content, cast.figure).location
        place = part.location
        if place == NEAREST_BASE:
            place = summons_place(state, content, promo.model_copy(update={"location": NEAREST_BASE}))
        return cast, place
    return None


def _leg_text(content: Content, cast: PromotionCast, location: str) -> str:
    return cast.summons_text.replace("{據點}", content.locations[location].name)


def _refresh(state: GameState, content: Content, promo: PromotionDef) -> list[str]:
    """手上的多段召見照當下重挑一次版本：換了版本或地點就改寫召見（召見自動改由接手的人發、地點跟著人走）；
    沒有成立的版本時照舊等著。只有玩家讀到的那一句話變了才回傳新的那一句：只換了演的事件、人與地點與話都沒變（何進的索賄
    在盧植下獄之前、之後各一版）時悄悄換，不把同一句話又寫進紀錄一次（開發預審 N4）；事件與地點都沒換、只換了出面的人
    （營中授印的兩個版本，皇甫嵩退場、朱儁接手）話就變了，照樣說。
    這一段的奇遇已經開著（事件待處理）時不換：畫面上演的還是原來那一幕，演完照演的那一則走到下一段（最終審查 m1）。"""
    s = state.player.summons
    if _scene_open(state, promo):
        return []
    found = current_cast(state, content, promo, s.leg, s.prev)
    if found is None:
        return []
    cast, location = found
    told = _told_line(content, promo, s)
    if location != s.location:  # 換了地點（人走了、換了人，或往下一段時還沒有版本、現在補上）：說不說都摸清（裁決 E2）
        scout(state, content, location)
    s.event, s.location, s.figure = cast.event, location, cast.figure
    line = _leg_text(content, cast, location)
    return [line] if line != told else []


def _scene_open(state: GameState, promo: PromotionDef) -> bool:
    """手上這一段的奇遇正開在畫面上（待處理的事件是這一段任一個版本的事件）。"""
    s = state.player.summons
    if state.pending_event is None or s.leg >= len(promo.legs):
        return False
    return any(cast.event == state.pending_event for cast in promo.legs[s.leg].casts)


def _told_line(content: Content, promo: PromotionDef, s: Summons) -> str | None:
    """上一次告訴玩家的召見那一句（這一段原本挑中的版本、原本的地點）；這一段還沒挑到版本（等著）的是 None。
    版本用事件加出面的人認：兩個版本可以共用同一個事件（營中授印），只靠事件 id 會認成第一個。"""
    if s.event is None or not s.location or s.leg >= len(promo.legs):
        return None
    casts = [cast for cast in promo.legs[s.leg].casts if cast.event == s.event]
    old = next((cast for cast in casts if cast.figure == s.figure), casts[0] if casts else None)
    return _leg_text(content, old, s.location) if old is not None else None


def check_summons(state: GameState, content: Content) -> list[str]:
    """該不該發召見（每次行動、同步的最後檢查，所以貢獻從哪裡來都接得到）：第一季、有陣營、這一季還沒落幕、還沒拿到第 4 階
    資格。手上有多段召見的，照當下重挑版本（_refresh）。沒有召見時看下一階：本季貢獻到 threshold；第 3、4 階還要完成過那一階
    的一種機緣——貢獻到了、機緣還沒有，那一階說一次 HINT。第 3、4 階挑得到版本才發（沒有人能出面就先不發）。
    同一階只發一次（召見沒有期限，演完晉升才清掉）。"""
    p, w = state.player, state.world
    if not season_one(content, w) or p.faction is None or w.ended or p.qualified:
        return []
    if p.summons is not None:
        promo = _pending(state, content)
        return _refresh(state, content, promo) if promo is not None and promo.legs else []
    rank = rank_of(state) + 1
    promo = promotion_for(content, p.faction, rank)
    if promo is None or p.contrib < threshold(content, rank):
        return []
    from . import opportunities  # noqa: PLC0415  opportunities → ranks：在函式裡 import，避免循環

    if rank >= 3 and not opportunities.done_for_rank(state, content, rank):
        if rank in p.rank_hinted:
            return []
        p.rank_hinted.append(rank)
        return [HINT]
    if not promo.legs:  # 第 2 階：照 T5
        location = summons_place(state, content, promo)
        fid, handoff = presenter(state, content, promo, location)
        p.summons = Summons(rank=promo.rank, figure=fid, location=location, since=w.time)
        scout(state, content, location)  # 裁決 E2：每一種召見都摸清（第 2 階也是，企劃者說的是「發召見」）
        return [_summons_text(content, promo, handoff, location)]
    found = current_cast(state, content, promo, 0, None)
    if found is None:
        return []
    cast, location = found
    p.summons = Summons(rank=rank, figure=cast.figure, location=location, since=w.time, leg=0, event=cast.event)
    scout(state, content, location)
    return [_leg_text(content, cast, location)]


def next_leg(state: GameState, content: Content, from_event: str) -> list[str]:
    """這一段演完（選項效果的 summons_next）：召見往下一段，挑版本、改寫地點，回傳下一段的召見那一句。
    下一段此刻沒有成立的版本時，召見留在這一段之後等著（地點空著，之後 check_summons 會補上）。"""
    s = state.player.summons
    promo = _pending(state, content)
    if s is None or promo is None or not promo.legs:
        return []
    s.leg, s.prev, s.event, s.location = s.leg + 1, from_event, None, ""
    found = current_cast(state, content, promo, s.leg, s.prev)
    if found is None:
        return []
    cast, location = found
    s.event, s.location, s.figure = cast.event, location, cast.figure
    scout(state, content, location)  # 裁決 E2
    return [_leg_text(content, cast, location)]


def summons_line(state: GameState, content: Content) -> str | None:
    """還沒去的召見那一句，照此刻出面的人重寫（召見發出後人物才不在的，自動改由接手的人發；主線與目標列它）。
    多段（第 3、4 階）照此刻成立的版本寫（這一段的奇遇已經開著時照開著的那一幕寫，同 _refresh）；此刻沒有成立的版本時是 None。"""
    p = state.player
    promo = _pending(state, content)
    if promo is None:
        return None
    if promo.legs:
        if _scene_open(state, promo):
            return _told_line(content, promo, p.summons)
        found = current_cast(state, content, promo, p.summons.leg, p.summons.prev)
        return _leg_text(content, found[0], found[1]) if found is not None else None
    _, handoff = presenter(state, content, promo, p.summons.location)
    return _summons_text(content, promo, handoff, p.summons.location)


def summons_event(state: GameState, content: Content) -> str | None:
    """人在召見的地點時該演的晉升奇遇（主版或接手版，照此刻出面的人）；不在那裡、沒有召見、開關關著是 None。
    多段（第 3、4 階）照此刻成立的版本，人要在那個版本的地點。"""
    p = state.player
    promo = _pending(state, content)
    if promo is None:
        return None
    if promo.legs:
        found = current_cast(state, content, promo, p.summons.leg, p.summons.prev)
        return found[0].event if found is not None and found[1] == p.location else None
    if p.location != p.summons.location:
        return None
    _, handoff = presenter(state, content, promo, p.location)
    return promo.event_handoff if handoff and promo.event_handoff else promo.event_main


def _pending(state: GameState, content: Content) -> PromotionDef | None:
    p = state.player
    if p.summons is None or not season_one(content, state.world):
        return None
    return promotion_for(content, p.faction, p.summons.rank)


def promote(state: GameState, content: Content, rank: int) -> list[str]:
    """晉升奇遇選項的 promote（rules.apply_effect 呼叫）：清掉召見；第 2、3 階升到 rank，第 4 階是資格（qualified，rank 停在 3，
    候缺）。接「你升為X。」（第 4 階「你取得X的資格，候缺。」）、結尾那一句、豪強第 4 階看靠山的那一句。
    第 2 階記進當天的彙整（flush_news）；第 3 階與第 4 階資格當下發一則具名的陣營軍情（傳聞分層 4.1）。
    陣營軍情一律寫本名（傳聞分層第七節）：匿名的人也一樣，不用 display_name。開關關著、散人什麼都不做。
    「你取得X的資格，候缺。」與兩則陣營軍情「{名號}升為X。」「{名號}取得X的資格，候缺。」是新寫的初稿，待 joy 潤。"""
    p, w = state.player, state.world
    if not season_one(content, w) or p.faction is None:
        return []
    p.summons = None
    titles = TITLES.get(p.faction)
    name = titles[rank] if titles else ""
    if rank > HIGHEST_RANK:
        p.qualified = True
        p.rank = max(p.rank, HIGHEST_RANK)
        msgs = [f"你取得{name}的資格，候缺。"] if titles else []  # 新寫，待 joy 潤
    else:
        p.rank = rank
        msgs = [f"你升為{name}。"] if titles else []
    promo = promotion_for(content, p.faction, rank)
    if promo is not None and promo.closing:
        msgs.append(promo.closing)
    line = promo.patron_lines.get(p.patron or "") if promo is not None else None
    if line is not None:  # 豪強升第 4 階：看靠山多一句（晉升奇遇文件 4.3）
        from .models import Effect  # noqa: PLC0415
        from .rules import apply_effect  # noqa: PLC0415

        # 這個效果只有 text 與 affinity：apply_effect 照這兩樣走的那幾行不碰 world，所以傳 None（promote 的簽名沒有 world）
        msgs += apply_effect(Effect(text=line.text, affinity=line.affinity), state, content, None)
    if rank == 2:
        day = calendar.point(w.time, content, w).cal_day
        w.promoted_today.setdefault(f"{day}:{p.faction}:{rank}", []).append(p.name)  # 陣營軍情一律具名（傳聞分層第七節）
    elif titles:
        text = f"{p.name}取得{name}的資格，候缺。" if rank > HIGHEST_RANK else f"{p.name}升為{name}。"  # 新寫，待 joy 潤；寫本名
        add_rumor(state, text, content=content, layer="faction", faction=p.faction)
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
