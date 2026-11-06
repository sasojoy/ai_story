"""管理者：玉璽碎片的季流程那幾顆（玉璽碎片設計第十二節；公告不寫管理者，效果跟自然發生一樣）。全部拆包第 27 批從 Game 搬來：
強制現世（領地爭奪的季改成現在藏一片）、隱沒判斷、蓋天命之季。Game 留一行委派（殼 server.py 的 ADMIN_ACTIONS、測試叫）；
「現在藏一片」（hide）只有強制現世叫，Game 上不留委派。指定、強制璽動、單挑、取消單挑、管理頁的玉璽一組是第 28 批（還在 Game）。
"""
from __future__ import annotations

from tianxia import timetable  # 共用規則層
from tianxia.characters import CharacterStore
from tianxia.rules import season_one

from . import seal


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
