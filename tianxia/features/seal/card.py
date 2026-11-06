"""碎片卡與七種獨門行動（全部拆包第 28 批從 Game 搬來，計畫 docs/superpowers/plans/2026-11-06-玉璽包-第2批.md；Game 留一行委派）：
持有者的碎片卡（view，status_data["seal"]）、卡上要的季況（act_season，包內互叫、Game 上不留）、起用懷中那一片的獨門行動（use，MAIN_ACTIONS["seal_use"]）。
獨門行動的規則讀舊模組 tianxia/seal_acts.py（第 51 批才拆，過渡）。叫回 Game 的都經 ctx：_log、_write、_save_season、_showdown_status、stamp、world、state、content。
"""
from __future__ import annotations

from tianxia import conquest, timetable  # 共用規則層
from tianxia import seal_acts  # 過渡：待搬（第 51 批：獨門行動的規則與璽效查詢）
from tianxia.core import annal_base as annals
from tianxia.rules import season_one

from . import seal


def view(ctx) -> dict | None:
    """持有者的碎片卡（第十節，status_data["seal"]）：哪一片與效果、這一季動過沒（新得之季此季不動／此季已動過／此季可能被牽動）、
    此刻被牽動時那一句、這一季標了 seal 還沒到的決戰時刻（Game.stamp）。不寫機率。不是持有者是 None。"""
    from tianxia.world import _season_vehicle  # noqa: PLC0415  核心本體：季的事用的空殼玩家

    c = ctx.content
    if not seal.on(c):
        return None
    view = ctx.world.seal_state()
    shard = seal.shard_of(view.registry, ctx.state.player.name)
    if shard is None or shard.id not in c.seal:
        return None
    if seal.mandate_now(view.registry, view.season):  # 天命之季沒有新主保護（8.2）
        state = seal.CARD_STIRRED if shard.stirred_season == view.season else seal.CARD_MANDATE
    else:
        state = seal.CARD_NEW if shard.since_season == view.season else seal.CARD_STIRRED if shard.stirred_season == view.season else seal.CARD_CALM
    status = ctx._showdown_status(tick=False)  # 璽動只在時刻表決戰（攻城戰不璽動）
    stir = seal.STIR_MINE.format(shard=c.seal[shard.id].name) if status is not None and status[0].seal_shard == shard.id else ""
    w = ctx.state.world
    dates = [
        ctx.stamp(timetable.when(_season_vehicle(c, w), c, e)) for e in timetable.events(w, c)
        if (e.seal or e.mandate_only) and e.id not in w.timeline and e.id not in w.showdowns_opened
    ] if season_one(c, w) else []
    out = {"name": c.seal[shard.id].name, "effect_text": seal.shard_text(c, shard.id), "state": seal.card_state(c, state),
           "stir": stir, "dates": dates}
    if seal_acts.on(c):  # 獨門行動（改版第 2、3 批）：改版關著不多這一鍵（一個字都不變）；這一片沒有行動是 None
        out["act"] = seal_acts.view(ctx.state, c, seal.filled(view.registry, c), view.season, **act_season(ctx))
    return out

def act_season(ctx) -> dict:
    """seal_acts.problem／view 要的季況：季在跑（籌備、休季都不是）、賽季時鐘停著、時刻怎麼寫（Game.stamp）。"""
    return {"running": ctx.world.season_phase() == "running" and not ctx.state.world.ended,
            "paused": ctx.world.paused_at() is not None, "stamp": ctx.stamp}

def use(ctx, target: str = "", side: str = "") -> list[str]:
    """起用懷中那一片的獨門行動（玉璽碎片改版第 2、3 批；MAIN_ACTIONS["seal_use"]）：target 是指定的目標（引將的大勢人物、傳檄的戰線、
    收心的人物、鎮地與補缺的區塊；頒詔、承露不用），side 是散人挑的那一軍（傳檄、鎮地、補缺）。不花體力、不花銀兩（PM 五之一 7）。
    補缺當場把那一塊退回原主（conquest.restore，照翻地的規則記一次易手）；鎮地只記在季上（conquest.push_problem 讀）。
    先照 seal_acts.problem／target_problem 驗（按不下去回原因、什麼都不動）；登記那一筆在 world.mutate 裡整個重驗（碎片剛被搶走、
    次數剛用完就落空），記次數與一筆 use（只給管理者看：有名號）；季上記一筆生效中的（不記是誰）、引將把人物搬過來；天下大事與
    江湖史各一句（不寫是誰，企劃者）；自己一則江湖紀錄與一則行狀。戰報不寫。假人不叫這裡（設計第四章【PM】）。"""
    c, s = ctx.content, ctx.state
    if not seal_acts.on(c):
        return ctx._log(["（此刻無法這麼做。）"])
    view = ctx.world.seal_state()
    reg = seal.filled(view.registry, c)
    why = seal_acts.problem(s, c, reg, view.season, **act_season(ctx))
    held = seal_acts.mine(s, c, reg)
    if why is None and held is not None:
        why = seal_acts.target_problem(s, c, held[1], target, side)
    if why is not None or held is None:
        return ctx._log([f"（{why or seal_acts.NO_SHARD}）"])
    shard_id, kind = held[0].id, held[1]
    act = seal_acts.plan(s, c, shard_id, kind, target, side)
    what = seal_acts.what_text(c, act)
    me, w = s.player.name, s.world
    left: list[int] = []

    def _apply(shared) -> None:
        r = seal.filled(shared.seal, c)
        now = seal.shard_of(r, me)
        number = shared.season_number
        if now is None or now.id != shard_id or seal_acts.left(now, number, c) <= 0:
            return
        ready = seal_acts.ready_at(now, number, c, w)
        if ready is not None and w.time + seal_acts.EPS < ready:
            return
        seal_acts.note_use(now, number, w.time)
        seal.log_use(r, number, shard=shard_id, holder=me, act=kind, what=what, at=w.time)  # 另記一欄（FB-695）
        left.append(seal_acts.left(now, number, c))

    ctx.world.mutate(_apply)
    if not left:
        return ctx._log(["（此刻無法這麼做。）"])
    if kind == "yinjiang":
        seal_acts.pull(s, c, act)
    w.seal_acts.append(act)
    public = seal_acts.public_text(c, act)
    seal.rumor(w, public)  # 天下大事（world 層、不帶地點與人）
    seal.chronicle(w, public)
    if kind == "bujue":  # 補缺：當場退回原主（「收復」那一句天下大事與江湖史照易手寫，排在起用那一句之後）
        conquest.restore(w, c, act.target, act.side)
    name = c.seal[shard_id].name
    line = seal_acts.MINE.format(shard=name, what=what, left=left[0])
    ctx._write(seal.SEAL_TITLE, [line], tag=f"『{name}』")
    annals.note(s, c, annals.SEAL, seal_acts.ANNAL.format(shard=name, what=what), 4)  # 酒肆打聽不到這一類（FB-643）
    ctx._save_season()
    return ctx._log([line])
