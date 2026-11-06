"""管理者：玉璽碎片的季流程那幾顆（玉璽碎片設計第十二節；公告不寫管理者，效果跟自然發生一樣）。全部拆包第 27 批從 Game 搬來：
強制現世（領地爭奪的季改成現在藏一片）、隱沒判斷、蓋天命之季。Game 留一行委派（測試叫；管理者工具在這一包的 routes.py，全部拆包第 68 批）；
「現在藏一片」（hide）只有強制現世叫，Game 上不留委派。指定、強制璽動、單挑、取消單挑、定單挑結果、管理頁的玉璽一組是第 28 批搬來的（stir、assign、duel、fix、cancel、choices）。
"""
from __future__ import annotations

from tianxia import seal_acts  # 共用規則層（璽效查詢：on）
from tianxia import timetable  # 共用規則層
from tianxia.characters import CharacterStore
from tianxia.rules import season_one

from . import acts, duel_actions, duel_rules, seal


def emerge(ctx, shard_id: str = "") -> list[str]:
    """下一場標 emerge 的時刻表決戰必定現世（略過 35%）；可以指定哪一片（還沒現世的），空的照亂數挑。給誰照 3.3 從勝方抽。"""
    refusal = ctx._admin_refusal("強制現世")
    if refusal:
        return ctx._log(refusal)
    if shard_id and shard_id not in ctx.content.seal:
        return ctx._log(["（沒有這一片。）"])
    if seal.on(ctx.content) and seal.conquest_season(ctx.content, ctx.state.world):  # 領地爭奪的季沒有宛城現世：改成現在藏一片
        return hide(ctx, shard_id)
    ctx.world.mutate(lambda st: setattr(seal.filled(st.seal, ctx.content), "force_emerge", shard_id or "*"))
    ctx._write("強制現世", ["下一場標了現世的決戰，碎片必定現世。"], tag="管理者")
    return ctx._log(["（下一場標了現世的決戰，碎片必定現世。）"])


def hide(ctx, shard_id: str) -> list[str]:
    """領地爭奪的季「強制現世」的替身（領地爭奪設計 3.9）：現在就藏一片（略過 hide_chance，可以指定哪一片），藏在哪一塊照開季的藏法
    （權重、亂數同自然擲中）；回話與紀錄都不寫藏在哪裡。這一季已經藏著、已經現世過一片、沒有可藏的都不藏。"""
    c = ctx.content
    out: list[str] = []

    def _apply(shared) -> None:
        reg = seal.filled(shared.seal, c)
        season = shared.season_number
        if seal.mandate_now(reg, season):
            out.append(seal.HIDE_MANDATE)
        elif reg.emerge_season == season:
            out.append(seal.HIDE_EMERGED)
        elif seal.live_cache(reg, season) is not None:
            out.append(seal.HIDE_HAS)
        else:
            spots = seal.hide_spots(c, shared.season)
            cache = seal.hide(reg, c, season, shared.tianji, spots, force=True, shard=shard_id or None)
            if cache is None:
                out.append(seal.HIDE_NO_SPOT if not spots else seal.HIDE_NONE)
            else:
                reg.cache = cache
                out.append(seal.HIDE_DONE)

    ctx.world.mutate(_apply)
    ctx._write("現在藏一片", out, tag="管理者")
    return ctx._log([f"（{line}）" for line in out])


def sink_check(ctx, now: float) -> list[str]:
    """照 7.6 的條件現在判一次（下一次換季會沉哪幾片），只印結果、不改。只要是管理者就能按：休季（換季之前）、暫停中照樣看得到（FB-178）。"""
    if not ctx.is_admin():
        return ctx._log(["（只有管理者能隱沒判斷。）"])
    reg = seal.filled(ctx.world.seal_state().registry.model_copy(deep=True), ctx.content)
    store = CharacterStore(ctx.world.db) if hasattr(ctx.world, "db") else None
    seen = {}
    for s in reg.shards.values():
        if s.state == "held" and s.holder:
            state = store.load(s.holder) if store is not None else None
            seen[s.holder] = None if state is None else (state.player.seen_real if state.player.seen_real is not None else state.last_real)
    sunk = seal.sink(reg, ctx.world.get_season_number(), seen, now, ctx.content.config.seal)
    lines = [f"（下一次換季會隱沒：{seal.SINK.format(holder=name, shard=ctx.content.seal[s.id].name)}）" for s, name in sunk]
    return ctx._log(lines or ["（下一次換季沒有碎片會隱沒。）"])


def mandate(ctx, when: str) -> list[str]:
    """蓋天命之季（第十二節；玉璽二）：when 是 "next"（下一季蓋章，不看七片現世過沒）、"cancel"（收回「下一季」：只清延後的記號，
    七片這一輪都現世過的話換季照樣蓋；審查 I2）或 "now"（這一季立刻蓋：還沒打的標了 seal 的決戰照天命之季的規則璽動，天命之爭排在
    預設時刻——已經過了就馬上到期——也可以用「立刻開戰」）。「下一季」與收回只要是管理者就按得了（休季正是要決定下一季的時候，同
    FB-178）；「這一季」要季在跑。公告照自然發生寫、不寫管理者。"""
    refusal = ctx._admin_refusal("蓋天命之季") if when == "now" else None if ctx.is_admin() else ["（只有管理者能蓋天命之季。）"]
    if refusal:
        return ctx._log(refusal)
    c = ctx.content
    event = seal.mandate_event(c)
    if not seal.on(c) or event is None or seal.mandate_battle(c) is None:
        return ctx._log(["（這個劇本沒有天命之爭。）"])
    season = ctx.state.world  # 每個動作開頭的 sync 剛讀過（不用 get_season：它會把整季的傳聞與江湖史讀回來）
    if season.mandate:
        return ctx._log(["（這一季已經是天命之季；收季之後七片散去。）"])
    if when == "next":
        ctx.world.mutate(lambda st: setattr(seal.filled(st.seal, c), "mandate_pending", True))
        msg = "下一季蓋天命之季的章。"
    elif when == "cancel":
        if not seal.filled(ctx.world.seal_state().registry, c).mandate_pending:
            return ctx._log(["（下一季沒有要蓋天命之季的章。）"])
        ctx.world.mutate(lambda st: setattr(seal.filled(st.seal, c), "mandate_pending", False))
        msg = "收回下一季的天命之季章（七片這一輪都現世過的話，換季時照樣會蓋）。"
    elif when == "now":
        if season.ended or not season_one(c, season):
            return ctx._log(["（這一季沒有時刻表，蓋不了天命之季。）"])
        def _stamp(st) -> None:
            seal.stamp_mandate(st, c, timetable.default_time(event, c, st.season))
            timetable.avoid_quiet_hours(st.season, c, ctx.now)  # 天命之爭照季曆排的時刻挪開半夜（企劃者 2026-10-15）

        ctx.world.mutate(_stamp)
        ctx.state.world = ctx.world.get_season()
        msg = "這一季蓋上天命之季的章。"
        # 挪不開半夜、照原時間的決戰：同開季、開啟下一季那一行（FB-265）
        kept = timetable.quiet_notes(ctx.state.world, c, ctx.now)
        ctx._write("蓋天命之季", [msg, *kept], tag="管理者")
        return ctx._log([f"（{msg}）", *kept])
    else:
        return ctx._log(["（看不懂要怎麼蓋。）"])
    ctx._write("蓋天命之季", [msg], tag="管理者")
    return ctx._log([f"（{msg}）"])


def stir(ctx, shard_id: str) -> list[str]:
    """下一場標了 seal 的決戰必定牽動這一片（略過 7%、新主保護與次數上限；那一片要有主）。"""
    refusal = ctx._admin_refusal("強制璽動")
    if refusal:
        return ctx._log(refusal)
    shard = ctx.world.seal_state().registry.shards.get(shard_id)
    if shard is None or shard.state != "held":
        return ctx._log(["（這一片現在沒有主人，牽動不了。）"])
    ctx.world.mutate(lambda st: setattr(st.seal, "force_stir", shard_id))
    ctx._write("強制璽動", [f"下一場標了璽動的決戰，必定牽動『{ctx.content.seal[shard_id].name}』。"], tag="管理者")
    return ctx._log(["（下一場標了璽動的決戰，必定牽動這一片。）"])

def assign(ctx, shard_id: str, name: str, state: str = "held") -> list[str]:
    """把一片直接記到某個名號名下（held，一人一片照擋、這一季有新主保護），或收回成未現世（hidden）、改成隱沒（sunk）。
    只改登記，不讀、不存他的存檔（「這一季上線過」看 seen_real，管理者工具碰不到它）；抄本與紀錄等他同步時補（登記記一筆 assign）。"""
    refusal = ctx._admin_refusal("指定持有者")
    if refusal:
        return ctx._log(refusal)
    if shard_id not in ctx.content.seal or state not in ("held", "hidden", "sunk") or (state == "held" and not name.strip()):
        return ctx._log(["（看不懂要怎麼改。）"])
    out: list[str] = []

    def _apply(shared) -> None:
        reg = seal.filled(shared.seal, ctx.content)
        shard = reg.shards[shard_id]
        if state == "held":
            other = seal.shard_of(reg, name)
            if other is not None and other.id != shard_id:
                out.append(f"（{name}手上已經有『{ctx.content.seal[other.id].name}』了：一人一片。）")
                return
        before = shard.holder
        shard.state, shard.holder = state, (name.strip() if state == "held" else None)
        shard.since_season = shared.season_number if state == "held" else shard.since_season
        if state == "held":
            shard.emerged_round = shard.emerged_round or reg.round
        seal.log(reg, shared.season_number, "assign", shard=shard_id, holder=shard.holder, other=before)
        out.append(f"（『{ctx.content.seal[shard_id].name}』改成{seal.BOOK_STATES[state].format(holder=shard.holder or '')}。）")

    ctx.world.mutate(_apply)
    ctx._write("指定持有者", out, tag="管理者")
    return ctx._log(out)

def duel(ctx, shard_id: str, challenger: str, factor: float, now: float) -> list[str]:
    """立刻對這一片開一場奪璽單挑，指定挑戰者，局勢係數可選（預設 1.0，上限照舊 25%）。正式伺服器只能掛在最近一場剛收場、
    還沒開過單挑的時刻表決戰上（SealRegistry.last_showdown，公告照那一場寫）；Config.seal.qa_tools 開著時不必有決戰。
    雙方的快照照 5.3「沒參戰」那一列（_seal_side_of）；挑戰者也要過一人一片。"""
    refusal = ctx._admin_refusal("強制開單挑")
    if refusal:
        return ctx._log(refusal)
    c, cfg = ctx.content, ctx.content.config.seal
    view = ctx.world.seal_state()
    reg = seal.filled(view.registry, c)
    shard = reg.shards.get(shard_id)
    if shard is None or shard.state != "held" or not challenger.strip() or seal.key(challenger) in seal.holders(reg):
        return ctx._log(["（這一片沒有主人，或挑戰者手上已經有碎片。）"])
    hung = reg.last_showdown is not None and not reg.last_showdown_dueled
    if not hung and not cfg.qa_tools:
        return ctx._log(["（正式伺服器的奪璽單挑只能掛在剛收場的時刻表決戰上；那一場不在、或已經開過單挑。）"])
    if view.duels:
        return ctx._log(["（已經有一場奪璽單挑在打。）"])
    ctx.now = now
    cap = min(cfg.cap, cfg.cap * max(0.0, min(1.0, factor)))
    duel_id = f"{reg.last_showdown}:{shard_id}" if hung else f"qa{reg.seq + 1}:{shard_id}"
    a, b = duel_actions.side_of(ctx, challenger), duel_actions.side_of(ctx, shard.holder)
    duel_rules.faced(c, a, b)  # 五項屬性的季：兩邊照對方真正的五項重算；舊的季不動
    duel = duel_rules.open_duel(
        duel_id, shard_id, reg.last_showdown if hung else None, None, reg.last_showdown_where if hung else "", "旁觀", cap,
        a, b, now, cfg,
    )
    line = (duel_rules.CALL if hung else duel_rules.CALL_QA).format(
        challenger=duel.challenger.name, holder=duel.holder.name, shard=c.seal[shard_id].name)

    def _apply(shared) -> None:
        shared.seal_duels.append(duel)
        seal.filled(shared.seal, c).last_showdown_dueled = True
        seal.rumor(shared.season, line)

    ctx.world.mutate(_apply)
    ctx._write("強制開單挑", [line], tag="管理者")
    return ctx._log([line])

def fix(ctx, take: bool) -> list[str]:
    """正在打的那一場，指定再擲中或不中（QA 用，同時刻表的「定結果」）；公告照常。"""
    refusal = ctx._admin_refusal("定單挑的結果")
    if refusal:
        return ctx._log(refusal)
    if not ctx.world.seal_state().duels:
        return ctx._log(["（沒有奪璽單挑在打。）"])
    ctx.world.mutate(lambda st: setattr(st.seal_duels[0], "fixed", bool(take)))
    return ctx._log([f"（這一場收場時{'易主' if take else '懷璽不失'}。）"])

def cancel(ctx) -> list[str]:
    """取消正在打（或下戰書中）的那一場：記成未分勝負，碎片留在原主；只寫天下大事。"""
    refusal = ctx._admin_refusal("取消單挑")
    if refusal:
        return ctx._log(refusal)
    if not ctx.world.seal_state().duels:
        return ctx._log(["（沒有奪璽單挑在打。）"])
    out: list[str] = []
    ctx.world.mutate(lambda st: out.append(duel_rules.finish(st, st.seal_duels[0], ctx.content, None, ctx.now).text))
    ctx._deliver_seal_results()
    ctx._write("取消單挑", out, tag="管理者")
    return ctx._log(out)

def choices(ctx) -> dict | None:
    """設定頁「玉璽」一組要的：七片與狀態、有沒有單挑在打、剛收場的決戰還能不能掛單挑、qa_tools、天命之季蓋了沒（mandate：
    "now" 這一季、"next" 下一季、"" 沒有）與劇本有沒有天命之爭（mandate_ok，玉璽二）。碎片關著是 None。"""
    c = ctx.content
    if not seal.on(c):
        return None
    view = ctx.world.seal_state()
    reg = seal.filled(view.registry, c)
    out = {
        "shards": [{"id": s, "name": c.seal[s].name, "state": reg.shards[s].state, "holder": reg.shards[s].holder or ""} for s in c.seal],
        "duel": bool(view.duels), "hung": reg.last_showdown is not None and not reg.last_showdown_dueled,
        "where": reg.last_showdown_where, "qa": c.config.seal.qa_tools,
        "mandate": "now" if seal.mandate_now(reg, view.season) else "next" if reg.mandate_pending else "",  # 兩個章一起蓋，讀登記那一份（不必 get_season）
        "mandate_ok": seal.mandate_event(c) is not None and seal.mandate_battle(c) is not None,
        # 領地爭奪的季「強制現世」是「現在藏一片」（網頁換鈕上的字）；只給有沒有，不給藏在哪
        "hide": seal.conquest_season(c, ctx.state.world),
    }
    if seal_acts.on(c):  # 獨門行動（改版第 2 批）：這一季誰起用了哪一片、什麼時候、指定了什麼（救場用，設計【PM】5）；改版關著不多這一鍵
        out["uses"] = [
            {"shard": c.seal[e.shard].name if e.shard in c.seal else e.shard, "who": e.holder,
             "act": acts.NAMES.get(e.act, e.act), "when": ctx.stamp(e.at) if e.at is not None else "",
             "what": e.what}
            for e in reg.uses if e.season == view.season  # FB-695：起用另記在 uses（舊資料讀進來時從 history 搬過來）
        ]
    return out
