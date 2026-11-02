"""走一趟的動作（功能包 tianxia/features/explore/；原本是 Game 上走一趟的 12 個方法，開發規範手冊 3.2、主動搬六包第 3＋4 批）。

ctx 是 Game（第一階）；只叫 tianxia/core/services.py 那張清單上的方法。本體照搬、一個字不改（self 換成 ctx）；函式名＝原本的方法名
去掉前導底線（`_explore_ready` 是 `explore_ready`、`_outing_watched` 是 `outing_watched`，`_outing_walk`、`_outing_trace` 同）。
Game 上留 9 個一行委派（server 的 /api/do/outing、outing_say、outing_tale〔鎖外三段式〕、outing_erase、/api/main 的 main.outing、
bot.py、bot_policy.take_turn、測試，與 engine 模組層的 `_outing_watch` 還在叫）。包裡互相叫直接叫這裡的函式。
走一趟的每一段就是一次探索一顆（ctx.choose(IDLE_MARK) → Game._act → 探索一顆）：那一段抽到什麼寫在 Game 上寄放的 ctx._beat。
"""
from __future__ import annotations

from tianxia import annals  # 過渡：待搬（行狀：撿到稀世的東西、以弱勝強記一則）
from tianxia import deeds  # 過渡：待搬（世界記事：同上）
from tianxia import journal, naming, team
from tianxia import materials  # 過渡：待搬（撿到的東西那一句的開頭）
from tianxia import prologue as prologue_rules  # 過渡：待搬（序章裡不走一趟）
from tianxia import social  # 過渡：待搬（「此地還有」那一份名單：結算卡、遠處有人揮手）
from tianxia import speech  # 過渡：待搬（留言過字表）
from tianxia.core.option import IDLE_MARK, Option
from tianxia.state import PLAYER, JournalEntry, Outing, OutingBeat

from . import explore_rules, outing_rules


def outing_go(ctx, total: int = 0) -> list[str]:
    """走一趟：total 是段數（Config.jianfa.outing_segments）就出發；0 是停在要選的事上、選完之後接著走。
    出發要閒著（選單上的探索按得下去）、體力夠走完這麼多段；每一段照舊扣一次探索的體力，沒走的段不扣。
    回的訊息只有拒絕的那一句：沿路發生的事都在 PlayerState.outing（outing.view）與每一段自己的江湖紀錄裡。"""
    s, c = ctx.state, ctx.content
    p = s.player
    if not outing_rules.on(c, s) or prologue_rules.active(s, c) or p.journey is not None:
        return ["（此刻無法這麼做。）"]
    if total:
        if total not in outing_rules.segments(c):
            return ["（此刻無法這麼做。）"]
        if explore_ready(ctx) is None:
            return ["（此刻無法這麼做。）"]
        if p.stamina < outing_rules.cost(c, total):
            return ["（體力不夠走這麼多段。）"]
        p.outing = Outing(place=p.location, total=total, n=(p.outing.n + 1) if p.outing is not None else 1)
    else:
        trip = p.outing
        if trip is None or trip.end:
            return ["（此刻無法這麼做。）"]
        if trip.place != p.location:
            trip.end = outing_rules.LEFT
            return [outing_rules.END_LINES[outing_rules.LEFT]]
    return outing_walk(ctx)


def explore_ready(ctx) -> Option | None:
    """選單上的探索此刻按得下去就回那一顆（閒著、體力夠一段）；不然是 None。"""
    option = {o.id: o for o in ctx.options(odds=False, tick=False)}.get(IDLE_MARK)
    return option if option is not None and option.enabled else None


def outing_view(ctx) -> dict | None:
    """/api/main 的 outing（outing.view）加 can_go：停在要選的事上的那一趟，事情選完了、可以接著走（網頁照它自己送「接著走」；
    最後一段是要選的事時，接著走只是把這一趟收成「走完」）。關著是 None。"""
    view = outing_rules.view(ctx.state, ctx.content)
    if view is not None and view["trip"] is not None:
        trip = view["trip"]
        trip["can_go"] = outing_can_go(ctx)
        if trip["can_say"]:
            trip["ink"] = outing_ink_left(ctx)
            trip["ink_item"] = ctx.wallet.item_for(outing_rules.INK)
            trip["people"] = [o.player.name for o in social.here(ctx)]  # 結算卡的「此地還有」：點名字開玩家卡打招呼、邀結伴
        trip["admin"] = ctx.is_admin()
    return view


def outing_can_go(ctx) -> bool:
    """停下來的那一趟可以接著走了：事情選完了（探索回到選單上；體力不夠一段也算，接著走會把它收成「累了」）。"""
    if outing_rules.active(ctx.state) is None:
        return False
    return IDLE_MARK in {o.id for o in ctx.options(odds=False, tick=False)}


def outing_watched(ctx, fn, *args, **kwargs):
    """走一趟停在要選的事上（還沒選完）時做的這一下：照做，做完把這一下寫進江湖紀錄的得失（新的那幾則的數值變化、撿到的東西）
    與另外扣的體力記在那一段（OutingBeat.after）——結果那一行、結算卡、「走一趟」那一則才寫得出數字（Joy 10/31）。
    不在路上、已經選完、正在走（_outing_walk 自己的探索）都照做、什麼都不記。"""
    trip = outing_rules.active(ctx.state)
    if getattr(ctx, "_outing_busy", False) or trip is None or not trip.beats or not trip.beats[-1].stop or outing_can_go(ctx):
        return fn(ctx, *args, **kwargs)
    p, beat = ctx.state.player, trip.beats[-1]
    stamina, before = p.stamina, {id(e): e for e in ctx.state.journal}
    head = ctx.state.journal[0] if ctx.state.journal else None
    ctx._outing_busy = True
    try:
        out = fn(ctx, *args, **kwargs)
    finally:
        ctx._outing_busy = False
    changes, notes = [], []
    for e in ctx.state.journal:
        if id(e) in before or journal.is_world_entry(e):
            continue
        merged = head is not None and id(head) not in {id(x) for x in ctx.state.journal} and e is ctx.state.journal[0] \
            and e.title == head.title  # 併進了原本最新那一則：只算這一下多出來的
        changes += [outing_rules.plain(x) for x in (journal.subtract_changes(e.changes, head.changes) if merged else e.changes)]
        notes += e.lines
    spent = round(stamina - p.stamina)
    grants = (n.removeprefix(materials.GRANT_PREFIX) for n in notes if n.startswith(materials.GRANT_PREFIX))
    parts = outing_rules.ledger_parts(beat.after) + list(grants) + changes + ([f"體力 -{spent}"] if spent > 0 else [])
    items = explore_rules.merge_items(x for x in parts if explore_rules.is_item(x))
    totals = journal.combine_changes([x for x in parts if not explore_rules.is_item(x)])
    beat.after = explore_rules.ledger(items + [x for x in totals if journal.change_class(x) == "tx-up"],
                                    [x for x in totals if journal.change_class(x) == "tx-down"])
    return out


def outing_walk(ctx) -> list[str]:
    """一段一段走（每一段是一次 choose(act:explore)，各寫各的江湖紀錄）：端出要選的事就停；打輸、氣血低於 outing_turn_back
    回頭；體力不夠一段也回頭。走完了寫 end。"""
    s, c = ctx.state, ctx.content
    p, cfg = s.player, c.config.jianfa
    trip = p.outing
    while trip.done < trip.total and not trip.end:
        if explore_ready(ctx) is None:
            if IDLE_MARK in {o.id for o in ctx.options(odds=False, tick=False)}:
                trip.end = outing_rules.TIRED  # 探索在選單上但灰了：體力不夠一段
            break  # 不在選單上：還有事要選（不該走到這裡；保險）
        ctx._beat = None
        stamina, ctx._outing_busy = p.stamina, True
        try:
            msgs = ctx.choose(IDLE_MARK)
        finally:
            ctx._outing_busy = False
        beat, ctx._beat = ctx._beat or {"kind": explore_rules.MATERIAL, "rare": False, "won": None}, None
        lines = [m for m in msgs if isinstance(m, str)]
        ledger = lines[1] if len(lines) > 1 and lines[1].startswith(("得：", "失：")) else ""
        stop = IDLE_MARK not in {o.id for o in ctx.options(odds=False, tick=False)}
        trip.done += 1
        trip.beats.append(OutingBeat(kind=beat["kind"], text=lines[0] if lines else "", ledger=ledger, rare=bool(beat["rare"]),
                                     won=beat["won"], stop=stop, feat=beat.get("feat", ""), feat_kind=beat.get("feat_kind", ""),
                                     foe=beat.get("foe", ""), spent=max(0, round(stamina - p.stamina))))
        now, cap = team.member_neili(c, p.member, team.con_of(s, c, ctx.world, PLAYER), season=s.world)
        if beat.get("lost"):
            trip.end = outing_rules.LOST
        elif cap > 0 and now < cap * cfg.outing_turn_back:
            trip.end = outing_rules.HURT
        if stop:
            break
        if trip.end != outing_rules.LOST:
            outing_trace(ctx, trip)
    if not trip.end and trip.done >= trip.total and IDLE_MARK in {o.id for o in ctx.options(odds=False, tick=False)}:
        trip.end = outing_rules.DONE  # 最後一段端出要選的事時先不收：選完、接著走那一下才收
    if trip.end:  # 撿到稀世的東西、以弱勝強（Joy 10/30：只有這種才值得記）：一段一則行狀、世界記事一筆（此地舊事、人物對話讀得到）
        place = c.locations[trip.place].name if trip.place in c.locations else trip.place
        # 整趟的得失收成一則（「剛剛」放它；留一句併進這一則，不會只剩留字，Joy 10/31）
        items, totals = outing_rules.trip_totals(trip)
        lines = [f"走了 {trip.done} 段。{outing_rules.END_LINES.get(trip.end, '')}".strip()] + (
            [f"撿到：{'、'.join(items)}"] if items else [])
        journal.add_entry(s, JournalEntry(time=s.world.time, title=outing_rules.TRIP_TITLE.format(place=place),
                                          tag=outing_rules.END_TITLES.get(trip.end, ""), lines=lines, changes=totals))
        for b in trip.beats:
            if b.feat:
                annals.note(s, c, annals.DEED, outing_rules.FEAT_ANNAL[b.feat_kind].format(place=place, what=b.feat), 3, place=place)
                deeds.record(s, c, outing_rules.DEED_KIND, outing_rules.FEAT_DEED[b.feat_kind].format(name=p.name, place=place, what=b.feat),
                             place=trip.place, actors=[p.name])
    return []


def outing_trace(ctx, trip: Outing) -> None:
    """一段走完、沒停下：擲一下路上有沒有看到東西（outing_trace_chance）——這一處有別人、這一趟還沒揮過手的話先是遠處有人揮手，
    不然是一則別人的留言。一趟最多 outing_trace_cap 行，不佔段數。亂數另起（outing.trace_rng），Game.rng 一個都不動。"""
    c = ctx.content
    if outing_rules.traces_left(trip, c) <= 0:
        return
    rng = outing_rules.trace_rng(ctx.state, trip)
    if rng.random() >= c.config.jianfa.outing_trace_chance:
        return
    beat = None
    if not trip.waved:
        beat = outing_rules.wave_beat([o.player.name for o in social.here(ctx)], rng)
        trip.waved = beat is not None
    if beat is None:
        beat = outing_rules.seen_beat(ctx.state, c, trip, rng)
    if beat is not None:
        trip.beats.append(beat)


def outing_say(ctx, preset: int = -1, text: str = "", verdict: str = "") -> list[str]:
    """走完一趟在這一處留一句（outing.say_ok）：preset 是預設句的第幾句（免費）；不然是自己寫的 text（伺服器量過長度、
    鎖外審過，verdict 是模型的判斷），過字表（speech.problem，同名帖自題那一套），用掉一張題壁墨（商城 inscribe）。
    成了刻進這一處（outing.inscribe）、寫一則江湖紀錄；不成只回一句、什麼都不動。"""
    s, c = ctx.state, ctx.content
    if not outing_rules.on(c, s):
        return ["（此刻無法這麼做。）"]
    trip = outing_rules.say_ok(s)
    if trip is None:
        p = s.player
        return [outing_rules.SAY_AGAIN if p.outing is not None and p.outing.said else outing_rules.SAY_NOT_HERE]
    token = None
    if 0 <= preset < len(outing_rules.PRESETS):
        line, is_preset = outing_rules.PRESETS[preset], True
    else:
        line, is_preset = speech.clean(text), False
        if not line:
            return [outing_rules.SAY_EMPTY]
        problem = speech.problem(line, c, speech.MOTTO, c.config.jianfa.outing_say_max, verdict)
        if problem is None and any(word in line for word in naming.BANNED_WORDS):
            problem = speech.BLOCKED  # 同酒肆題壁：牆上不寫這幾個字
        if problem:
            return [problem]
        left = ctx.wallet.tokens(outing_rules.INK)
        if not left:
            return [outing_rules.NO_INK]
        token = left[0]
    place = c.locations[trip.place].name if trip.place in c.locations else trip.place
    item = outing_rules.inscribe(s, c, line, preset=is_preset)
    ctx._save_season()  # 留言刻在全服這一季（WorldState.inscriptions），不寫回共用賽季的話下一次重讀就沒了
    if token is not None:
        ctx.wallet.consume(outing_rules.INK, place=trip.place, inscription=item.id)  # 用掉的就是上面查到的那一張（最舊的）
    said = outing_rules.SAY_DONE.format(place=place, text=line)
    journal.add_entry(s, JournalEntry(time=s.world.time, title=outing_rules.TRIP_TITLE.format(place=place), lines=[said],
                                      changes=[] if token is None else ["題壁墨 -1"]), merge=True)  # 併進這一趟那一則（Joy 10/31）
    return ctx._log([said])


def outing_tale_request(ctx) -> outing_rules.TaleRequest | list[str]:
    """遊記的 A 段（只讀）：這一趟收了、還沒請過模型就開單；不然回一句（不叫模型）。"""
    req = outing_rules.tale_request(ctx.state, ctx.content)
    return ["（此刻無法這麼做。）"] if req is None or not outing_rules.on(ctx.content, ctx.state) else req


def outing_set_tale(ctx, text: str | None, request: outing_rules.TaleRequest) -> list[str]:
    """遊記的 C 段：還是同一趟（outing.same_trip）才收；text 是 None（叫不動、不合用）就記成請過了、畫面照用模板。"""
    trip = outing_rules.same_trip(ctx.state, request)
    if trip is None:
        return []
    trip.tale, trip.tale_done = text or "", True
    return []


def outing_ink_left(ctx) -> int:
    """手上還沒用掉的題壁墨幾張；商城關著是 0。"""
    return len(ctx.wallet.tokens(outing_rules.INK))


def admin_erase_inscription(ctx, ins_id: int) -> list[str]:
    """管理者抹掉一則留言（路上那一行的 ref）。不是管理者、沒有這一則都回同一句「此刻無法」。"""
    if not ctx.is_admin() or not outing_rules.erase(ctx.state, ins_id):
        return ["（此刻無法這麼做。）"]
    ctx._save_season()
    return ctx._log([outing_rules.ERASED])
