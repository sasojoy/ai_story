"""異聞的鎖內本體（總計畫「異聞一」）：探索撞見那一格、選單接管、status、走一步（這一批不叫模型：每一幕一律寫替身）、走完、放下、
同步時收拾不見了的那一則、換季清空。包只 import 核心、共用層與自己（不 import 探索包：讀 PlayerState.explore_seq 照玉璽包 seal_find 的前例，README 寫明）。"""
from __future__ import annotations

from tianxia import materials  # 共用規則層（順的那一幕多給一個此地素材）
from tianxia import prologue  # 共用規則層（序章裡不撞見）
from tianxia import renown  # 共用規則層（發掘者走完的名望）
from tianxia import rules as core_rules  # 核心（apply_effect、add_rumor）
from tianxia.core import annal_base as annals  # 核心（行狀「首見異聞」）
from tianxia.core import explore_base  # 核心（地點是六種裡的哪一種）
from tianxia.core.option import IDLE_MARK, Option
from tianxia.models import Effect
from tianxia.state import Rumor, YiwenClaim, YiwenWalk, YiwenWorld

from . import rules
from .store import Taken, store_of

PREFIX = "yiwen"
OPEN_LABEL = "回到異聞"  # 待 joy 潤（選單接管：標題讀不到時的備用字）
DROP_LABEL = "放下"  # 待 joy 潤
CLOSE_LABEL = "收起"  # 待 joy 潤（走完之後收尾卡那一顆）
SAID = "你說：「{words}」"  # 待 joy 潤（發掘者自己那一步的朱批）
FIRST_ANNAL = "首見異聞〈{title}〉"  # 待 joy 潤（行狀）
CHRONICLE = "{who}首見〈{title}〉"  # 待 joy 潤（江湖史那一行，具名：總計畫「對不上的」第 14 條）
JOURNAL_TITLE = "異聞・{title}"  # 待 joy 潤（江湖紀錄的標題）
GONE_TITLE = "異聞"  # 待 joy 潤（同步時那一則不見了：江湖紀錄的標題）


def _t(ctx):
    return ctx.content.config.yiwen


def _season(ctx) -> int:
    return int(ctx.state.player.season_number or 0)


def _key(ctx) -> str:
    return ctx._mall_owner()


def _on(ctx) -> bool:
    return rules.on(ctx.content, ctx.state.world)


def _clock(ctx) -> float:
    return rules.season_clock(ctx.state.world, ctx.content)


def _place_name(ctx, loc_id: str) -> str:
    loc = ctx.content.locations.get(loc_id)
    return loc.name if loc is not None else loc_id


def _kind(ctx, loc_id: str) -> str:
    loc = ctx.content.locations.get(loc_id)
    if loc is None:
        return ""
    return explore_base.kind_of(ctx.content.config.jianfa, loc).kind


def _clear(w: YiwenWalk) -> None:
    """回到「眼前沒有」：季內的帳（free_found、paid_scenes、done……）留著。"""
    w.opening, w.tale, w.place, w.role, w.node, w.own_from, w.tries = "", 0, "", "", 0, -1, 0


def _line(ctx, group: str, *, tale=0, node=0, **slots) -> str:
    return rules.fill(rules.pick_line(rules.lines(), group, season=_season(ctx), tale=tale, node=node), **slots)


# ── 撞見（BUS_ORDER 的 outing 那一格：探索一顆收尾）──


def _can_meet(ctx) -> bool:
    s, p = ctx.state, ctx.state.player
    if p.bot:  # 假人不撞見（設計 6.6）
        return False
    if prologue.active(s, ctx.content):
        return False
    if ctx.world.season_phase() != "running":
        return False
    if p.yiwen is not None and p.yiwen.opening:
        return False
    if store_of(ctx) is None:
        return False
    # 這一段別的事已經接管了（頭目、事件攤開、親衛隊長撞見）：探索不在選單上就不撞（總計畫「對不上的」第 10 條）
    return IDLE_MARK in {o.id for o in ctx.options(odds=False, tick=False)}


def on_explore(ctx, loc_id: str) -> list[str]:
    """outing 那一格：先擲重走，沒中再擲發掘；撞見回引子一句（lead_in），接著是選單接管那一刻（menu）。包的 bus 格核心不看 enabled：第一行自己問。"""
    if not _on(ctx) or not _can_meet(ctx):
        return []
    s, p, t, store = ctx.state, ctx.state.player, _t(ctx), store_of(ctx)
    key, season = _key(ctx), _season(ctx)
    rng = rules.roll("yiwen", season, key, p.explore_seq)
    pick = rules.roll("yiwen", season, key, p.explore_seq, "pick")
    w = p.yiwen
    r_walk, r_find = rng.random(), rng.random()
    known = rules.openings()
    old = [x for x in store.tales(season) if x["place"] == loc_id and x["status"] in (rules.OPEN, rules.SETTLED)
           and x["opening"] in known and (w is None or x["id"] not in w.done) and not _finished(store, x["id"], key)]
    if old and r_walk < t.rewalk_chance:
        tale = old[pick.randrange(len(old))]
        w = p.yiwen = p.yiwen or YiwenWalk()
        _clear(w)
        w.opening, w.tale, w.place, w.role = tale["opening"], tale["id"], loc_id, rules.TRAIL
        store.restart_walk(tale=tale["id"], account=key)
        return [_line(ctx, "lead_in", tale=tale["id"])]
    if r_find >= t.discover_chance:
        return []
    yw = s.world.yiwen
    taken = yw.taken if yw is not None else {}
    if _clock(ctx) > t.discover_until_day * rules.DAY or len(taken) >= t.season_cap:
        return []
    if w is not None and w.free_found >= t.free_per_player:
        return []
    today = ctx._pill_day()
    if yw is not None and yw.free_day == today and yw.free_today >= t.free_daily_cap:
        return []
    kind = _kind(ctx, loc_id)
    used = {x["opening"] for x in store.tales(season)} | set(taken)
    free = [o for o in known.values() if kind in o.get("kinds", []) and o["id"] not in used]
    if not free:
        return []
    opening = free[pick.randrange(len(free))]
    yw = s.world.yiwen = s.world.yiwen or YiwenWorld()
    yw.taken[opening["id"]] = YiwenClaim(by=key, at=_clock(ctx))
    if yw.free_day != today:
        yw.free_day, yw.free_today = today, 0
    yw.free_today += 1
    w = p.yiwen = p.yiwen or YiwenWalk()
    _clear(w)
    w.opening, w.place, w.role, w.own_from = opening["id"], loc_id, rules.FIND, 0
    w.free_found += 1
    core_rules.add_rumor(s, _line(ctx, "discover_rumor", place=_place_name(ctx, loc_id)), loc_id, content=ctx.content, layer="local", named=False)
    ctx._save_season()
    return [_line(ctx, "lead_in")]


def _finished(store, tid: int, key: str) -> bool:
    walk = store.walk(tid, key)
    return walk is not None and walk["finished_at"] is not None


# ── 眼前那一則 ──


def valid(ctx) -> bool:
    """眼前那一則還畫得出來：旁檔在、開場還在內容檔、則還在旁檔（沒被拿掉）；發掘者還沒寫成第一幕的，名額還是他的。"""
    w = ctx.state.player.yiwen
    if w is None or not w.opening:
        return False
    store = store_of(ctx)
    if store is None or w.opening not in rules.openings():
        return False
    if w.tale > 0:
        tale = store.tale(w.tale)
        return tale is not None and tale["opening"] == w.opening and tale["status"] != rules.REMOVED
    yw = ctx.state.world.yiwen
    claim = yw.taken.get(w.opening) if yw is not None else None
    return w.role == rules.FIND and claim is not None and claim.by == _key(ctx)


def _done(w: YiwenWalk) -> bool:
    return w.tale > 0 and w.tale in w.done


def menu(ctx) -> list[Option] | None:
    """眼前有一則、開著、還畫得出來：接管選單（走一趟停在這一段；撞見卡由 web/yiwen.js 照 main.yiwen 畫）。其餘回 None、不改狀態。"""
    if not _on(ctx) or not valid(ctx):
        return None
    w = ctx.state.player.yiwen
    if _done(w):
        return [Option(id=f"{PREFIX}:drop", label=CLOSE_LABEL)]
    title = rules.openings()[w.opening].get("title") or OPEN_LABEL
    return [Option(id=f"{PREFIX}:open", label=title), Option(id=f"{PREFIX}:drop", label=DROP_LABEL)]


def title(ctx) -> str:
    w = ctx.state.player.yiwen
    o = rules.openings().get(w.opening) if w is not None else None
    return JOURNAL_TITLE.format(title=o["title"]) if o else GONE_TITLE


def act(ctx, arg: str) -> list[str]:
    if arg == "drop":
        return drop(ctx)
    if arg == "open" and valid(ctx):
        w = ctx.state.player.yiwen
        return [rules.openings()[w.opening]["hook"]]
    return []


def drop(ctx) -> list[str]:
    """放下（總計畫「放下」）：①發掘者一幕都還沒寫：開場放回（free_found、free_today 不退）；②發掘者已有幾幕：照逾時提早公開；
    ③後來的人：只清眼前那一則（沒走完的那一列留著、不算足跡）。走完的收尾卡按「收起」也走這裡（只清眼前、不回話）。"""
    p = ctx.state.player
    w = p.yiwen
    if w is None or not w.opening:
        return []
    if _done(w):
        _clear(w)
        return []
    tale, opening = w.tale, w.opening
    store = store_of(ctx)
    if w.role == rules.FIND and tale == 0:
        yw = ctx.state.world.yiwen
        if yw is not None and opening in yw.taken and yw.taken[opening].by == _key(ctx):
            del yw.taken[opening]
            ctx._save_season()
    elif w.role == rules.FIND and store is not None:
        row = store.tale(tale)
        if row is not None and row["status"] == rules.WALKING:
            store.set_status(tale, rules.OPEN)
    _clear(w)
    return [_line(ctx, "drop", tale=tale)]


def on_sync(ctx, elapsed: float) -> list[str]:
    """眼前那一則不見了（旁檔不在、旁檔還原到比主檔舊、開場改版後不在內容檔、名額被收回）：清掉、回 gone 一句。異聞四再加定論名望。"""
    w = ctx.state.player.yiwen
    if w is None or not w.opening or not _on(ctx) or valid(ctx):
        return []
    tale = w.tale
    _clear(w)
    return [_line(ctx, "gone", tale=tale)]


def on_season_start(ctx, old) -> None:
    ctx.state.player.yiwen = None  # 不在 carried：新的一季本來就是空的（保險）


# ── 走一步（/api/do/yiwen_step；這一批是平鋪：進鎖就做，異聞二拆成三段式，請求與回應的鍵不變）──


def _grant(ctx, table: dict) -> list[str]:
    stats = rules.reward(table, ctx.content, ctx.state.world)
    if not stats:
        return []
    return core_rules.apply_effect(Effect(stats=stats), ctx.state, ctx.content, ctx.world)


def _luck_material(ctx, w: YiwenWalk, nid: int) -> list[str]:
    """寫成的那一幕是「順」：多一個 luck_material_tier 階的此地素材（屬性取地點素材的第一個；沒有就不給）。"""
    c = ctx.content
    loc = c.locations.get(w.place)
    mats = [m for m in (loc.materials if loc is not None else []) if m in c.materials]
    if not mats:
        return []
    mid = materials.tier_pick(c, c.materials[mats[0]].attribute, f"異聞｜{_season(ctx)}｜{w.tale}｜{nid}", _t(ctx).luck_material_tier)
    got = materials.grant(ctx.state, c, mid) if mid is not None else None
    return [got] if got else []


def _writable(store, w: YiwenWalk, node: int) -> bool:
    """這一步沒人走過的那一顆寫不寫得下去（異聞一、二）：走在自己的路上，或這一個節點底下還沒有任何一幕（接著寫，不算岔路，設計 2.2.8）；
    別人的則上已經有人走過別的做法的，鎖著（開岔路是異聞三）。"""
    if w.tale == 0 or w.own_from >= 0:
        return True
    return not store.children(w.tale, node)


def step(ctx, body: dict) -> list[str]:
    """按一顆猜法或做法：有人走過就重放；沒人走過、寫得下去就寫一幕替身（broken 那一句＋退路做法）；鎖著回「這條路還沒開」。
    關著、眼前那一則對不上（過時的鈕）回空清單、什麼都不動。"""
    if not _on(ctx) or not valid(ctx):
        return []
    s, p, t, store = ctx.state, ctx.state.player, _t(ctx), store_of(ctx)
    w = p.yiwen
    if _done(w) or str(body.get("opening", "")) != w.opening or _int(body.get("node")) != w.node or _int(body.get("tale")) != w.tale:
        return []
    pick = body.get("pick")
    if not isinstance(pick, int) or isinstance(pick, bool) or pick not in (0, 1, 2):
        return []  # 朱批那一顆、自己說：異聞二
    opening = rules.openings()[w.opening]
    here = store.node(w.node) if w.node else None
    depth = rules.depth_of(here)
    choices = rules.labels(opening, here)
    if depth > rules.DEPTH or pick >= len(choices):
        return []
    label = choices[pick]
    key, season, clock = _key(ctx), _season(ctx), _clock(ctx)
    tale_key = w.tale or w.opening
    child = next((n for n in store.children(w.tale, w.node) if n["pick"] == label), None) if w.tale else None
    out: list[str] = []
    if child is not None:  # 重放：零等待，當場畫出存下來的那一幕
        out.append(_line(ctx, "echo", tale=w.tale, node=child["id"], pick=label))
        if child["id"] not in w.paid_scenes:
            w.paid_scenes.append(child["id"])
            out += _grant(ctx, t.per_replay)
        nid, ndepth = child["id"], int(child["depth"])
    else:
        if not _writable(store, w, w.node):
            return [_line(ctx, "locked", tale=w.tale, node=w.node)]
        luck = rules.GOOD if rules.roll("yiwen", season, key, tale_key, w.node).random() < t.luck_good else rules.BAD
        if w.tale == 0:
            yw = s.world.yiwen
            claim = yw.taken.get(w.opening) if yw is not None else None
            try:
                w.tale = store.open_tale(season=season, opening=w.opening, place=w.place, by=key, shown=p.name,
                                         at=claim.at if claim is not None else clock)
            except Taken:
                _clear(w)
                return [_line(ctx, "taken")]
            if claim is not None:
                claim.tale = w.tale
                ctx._save_season()
        thing = opening.get("thing_word", "")
        text = [_line(ctx, "broken", tale=w.tale, node=w.node, pick=label, thing=thing)]
        options = rules.fallback_options(rules.lines(), season=season, tale=w.tale, node=w.node, thing=thing) if depth < rules.DEPTH else []
        own = w.own_from >= 0
        got = store.add_node(tale=w.tale, parent=w.node, depth=depth, pick=label, typed=False, by=key, shown=p.name, luck=luck, text=text,
                             options=options, ledger=[], fallback=True, at=clock, branch_cap=t.branch_cap, free_branches=t.free_branches,
                             can_pay=False, own=True)
        if got.kind != "new":
            return [_line(ctx, "taken")]
        if not own:
            w.own_from = w.node  # 接著別人停下的地方寫：從這裡往下是自己的路
        nid, ndepth = got.node["id"], depth
        out += text
        if nid not in w.paid_scenes:
            w.paid_scenes.append(nid)
            out += _grant(ctx, t.per_scene)
            if luck == rules.GOOD:
                out += _luck_material(ctx, w, nid)
    store.step_walk(tale=w.tale, account=key, season=season, node=nid, at=clock)
    w.node, w.tries = nid, 0
    if ndepth >= rules.DEPTH:
        out += _finish(ctx, store, w, nid)
    return out


def _finish(ctx, store, w: YiwenWalk, leaf: int) -> list[str]:
    """走完三步：收場句；第一次走完給獎勵、記足跡；發掘者的那一則改成公開，多名望、行狀、江湖史一行。"""
    s, p, t = ctx.state, ctx.state.player, _t(ctx)
    out = [_line(ctx, "close", tale=w.tale, node=leaf)]
    tale = store.tale(w.tale)
    o = rules.openings()[w.opening]
    first = store.finish_walk(tale=w.tale, account=_key(ctx), side=ctx._side() or "", at=_clock(ctx)) and w.tale not in w.done
    if tale is not None and tale["status"] == rules.WALKING and w.role == rules.FIND:
        store.set_status(w.tale, rules.OPEN)
    if w.tale not in w.done:
        w.done.append(w.tale)
    if not first:
        return out
    gains: list[str] = []
    if tale is not None and tale["discoverer"] == _key(ctx):
        gains += _grant(ctx, t.finish_first)
        gains += renown.gain(s, ctx.content, "fame", t.discover_fame)
        annals.note(s, ctx.content, annals.DEED, FIRST_ANNAL.format(title=o["title"]), 3, place=w.place)
        s.world.chronicle.append(Rumor(time=s.world.time, text=CHRONICLE.format(who=p.name, title=o["title"])))
        ctx._save_season()
    else:
        gains += _grant(ctx, t.finish)
    ctx._write(JOURNAL_TITLE.format(title=o["title"]), out + gains)
    return out + gains


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


# ── 畫面那一份（main.yiwen）──


def status(ctx) -> dict:
    if not _on(ctx):
        return {}
    return {"yiwen": {"card": card(ctx), "seek": None}}


def card(ctx) -> dict | None:
    if not valid(ctx):
        return None
    w = ctx.state.player.yiwen
    store, key, season = store_of(ctx), _key(ctx), _season(ctx)
    o = rules.openings()[w.opening]
    kind = _kind(ctx, w.place)
    place = _place_name(ctx, w.place)
    nodes = store.nodes(w.tale) if w.tale else []
    by_id = {n["id"]: n for n in nodes}
    path = rules.path_of(nodes, w.node) if w.node else []
    steps = store.steps(w.tale) if w.tale else {}
    scenes = []
    for nid in path:
        n = by_id[nid]
        mine = n["by"] == key
        zhupi = int(n["depth"]) == 1
        words = n["pick"]
        scenes.append({
            "node": nid, "depth": int(n["depth"]), "pick": words, "who": n["by_shown"], "zhupi": zhupi,
            "zhupi_text": (SAID.format(words=words) if mine else _line(ctx, "zhupi", tale=w.tale, node=nid, who=n["by_shown"], words=words)) if zhupi else "",
            "echo": "" if mine else _line(ctx, "echo", tale=w.tale, node=nid, pick=words),
            "luck": rules.LUCK_SEAL.get(n["luck"], ""), "text": list(n["text"]), "summary": "", "hidden": n["hidden"], "replay": not mine,
        })
    here = by_id.get(w.node)
    depth = rules.depth_of(here)
    done = _done(w)
    choices = []
    if not done and depth <= rules.DEPTH:
        kids = {n["pick"]: n for n in store.children(w.tale, w.node)} if w.tale else {}
        writable = _writable(store, w, w.node)
        for i, label in enumerate(rules.labels(o, here)):
            kid = kids.get(label)
            if kid is not None:
                choices.append({"i": i, "label": label, "state": "walked", "by": kid["by_shown"], "steps": steps.get(kid["id"], 0)})
            else:
                choices.append({"i": i, "label": label, "state": "free" if writable else "locked", "by": "", "steps": 0,
                                "note": "" if writable else _line(ctx, "locked", tale=w.tale, node=w.node)})
    walkers = sum(store.footprints(w.tale).values()) if w.tale else 0
    frame = _line(ctx, "first_frame") if w.role == rules.FIND else _line(ctx, f"trail_frame.{kind}", tale=w.tale, place=place)
    return {
        "opening": w.opening, "tale": w.tale, "title": o["title"], "place": w.place, "place_name": place, "kind": kind,
        "kind_word": rules.KINDS.get(kind, ""), "mark": "first" if w.role == rules.FIND else "trail", "frame": frame, "hook": o["hook"],
        "walkers": walkers, "depth": min(depth, rules.DEPTH), "node": w.node, "scenes": scenes, "choices": choices,
        "typed": {"state": "off", "max": _t(ctx).typed_max, "tries_left": max(0, _t(ctx).typed_tries - w.tries)},
        "done": done, "close": _line(ctx, "close", tale=w.tale, node=w.node) if done else "", "gains": "",
    }
