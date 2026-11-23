"""異聞的鎖內本體（總計畫「異聞一」）：探索撞見那一格、選單接管、status、走一步（這一批不叫模型：每一幕一律寫替身）、走完、放下、
同步時收拾不見了的那一則、換季清空。包只 import 核心、共用層與自己（不 import 探索包：讀 PlayerState.explore_seq 照玉璽包 seal_find 的前例，README 寫明）。"""
from __future__ import annotations

from tianxia import materials  # 共用規則層（順的那一幕多給一個此地素材）
from tianxia import prologue  # 共用規則層（序章裡不撞見）
from tianxia import renown  # 共用規則層（發掘者走完的名望）
from tianxia import speech  # 共用規則層（自己說的字先 clean）
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


def step(ctx, body: dict, draft: rules.SceneDraft | None = None, screened: str = "") -> list[str]:
    """A＋C 在同一把鎖裡（不叫模型：B 段當成叫不到，draft 給 None 就寫替身）。異聞一的平鋪 op 與舊測試、scripts/try_yiwen.py --fake 用；
    伺服器的 /api/do/yiwen_step 走 routes.yiwen_step 的三段式（A step_request → B 鎖外 writer.write_scene → C apply_step）。"""
    req = step_request(ctx, body)
    if isinstance(req, list):
        return req
    return apply_step(ctx, req, None if isinstance(req, rules.Replay) else draft, screened)


def _choices_here(ctx, w: YiwenWalk, store):
    opening = rules.openings()[w.opening]
    here = store.node(w.node) if w.node else None
    return opening, here, rules.depth_of(here), rules.labels(opening, here)


def _tale_here(ctx, store, w: YiwenWalk, key: str, season: int) -> int:
    """A 段的「有效的則」：w.tale；還是 0 的時候，旁檔有這一季這一句、發掘者是自己的那一則（第 251 批 _reattach 的條件，只讀；真的接回在 C）。"""
    if w.tale or w.role != rules.FIND:
        return w.tale
    row = store.tale_by_opening(season, w.opening)
    if row is None or row["discoverer"] != key or row["status"] == rules.REMOVED:
        return 0
    return int(row["id"])


def _walkable(store, w: YiwenWalk, tale: int, node: int) -> bool:
    """_writable 的 A 段版（則還沒接回時照「有效的則」問）。"""
    if tale == 0 or w.own_from >= 0:
        return True
    return not store.children(tale, node)


def step_request(ctx, body: dict) -> rules.YiwenRequest | rules.Replay | list[str]:
    """A 段（鎖內只讀，不寫任何東西）：驗眼前那一則、這一步、按的是哪一顆。已經有人寫過那一顆→Replay；擋下→回那一句（或空清單）；
    其餘開一張 YiwenRequest（順逆在這裡擲定，種子照異聞一）。自己說（pick "typed"）：speech.clean 之後過 typed_problem（擋下回 refuse_typed，
    不加 tries）、這一步被擋滿或寫不下去（別人的則）回 locked、被禁寫回 locked；字跟這一步某顆做法一樣就當成按那一顆。
    別人自己說的那一幕（pick "zhupi"）：text 要是這一步底下某個自己說的子節點的字，找不到回空清單。"""
    if not _on(ctx) or not valid(ctx):
        return []
    p, t, store = ctx.state.player, _t(ctx), store_of(ctx)
    w = p.yiwen
    if _done(w) or str(body.get("opening", "")) != w.opening or _int(body.get("node")) != w.node or _int(body.get("tale")) != w.tale:
        return []
    opening, here, depth, choices = _choices_here(ctx, w, store)
    if depth > rules.DEPTH:
        return []
    key, season, clock = _key(ctx), _season(ctx), _clock(ctx)
    tale = _tale_here(ctx, store, w, key, season)
    kids = store.children(tale, w.node) if tale else []
    pick, typed, text = body.get("pick"), False, ""
    if pick == "typed":
        text = speech.clean(body.get("text", ""))
        if rules.typed_problem(text, ctx.content, t) is not None:
            return [_line(ctx, "refuse_typed", tale=tale, node=w.node)]
        label, typed = text, text not in choices
        if typed and (w.tries >= t.typed_tries or not _walkable(store, w, tale, w.node) or store.muted(key, clock)):
            if not any(n["pick"] == label for n in kids):
                return [_line(ctx, "locked", tale=tale, node=w.node)]
    elif pick == "zhupi":
        label = str(body.get("text", ""))
        if not any(n["pick"] == label and n["typed"] for n in kids):
            return []
    elif isinstance(pick, int) and not isinstance(pick, bool) and pick in (0, 1, 2) and pick < len(choices):
        label = choices[pick]
    else:
        return []
    child = next((n for n in kids if n["pick"] == label), None)
    if child is not None:
        return rules.Replay(season=season, key=key, opening=w.opening, tale=tale, node=w.node, pick=label)
    if not _walkable(store, w, tale, w.node):
        return [_line(ctx, "locked", tale=tale, node=w.node)]
    luck = rules.GOOD if rules.roll("yiwen", season, key, tale or w.opening, w.node).random() < t.luck_good else rules.BAD
    nodes = store.nodes(tale) if tale else []
    by_id = {n["id"]: n for n in nodes}
    path = [by_id[nid] for nid in rules.path_of(nodes, w.node)] if w.node else []
    typed_words = tuple(n["pick"] for n in path if n["typed"]) + ((label,) if typed else ())
    known = (str(opening.get("hook", "")), str(opening.get("title", ""))) + typed_words
    prompt = rules.build_prompt(opening, path, list(here.get("ledger") or []) if here else [], label, typed, luck, depth,
                                place=_place_name(ctx, w.place))
    return rules.YiwenRequest(season=season, key=key, opening=w.opening, tale=tale, parent=w.node, depth=depth, pick=label, typed=typed,
                              text=text if typed else "", luck=luck, branch=False, prompt=prompt, known=known, typed_words=typed_words)


def apply_step(ctx, req, draft: rules.SceneDraft | None, screened: str) -> list[str]:
    """C 段（鎖內重驗再寫）：同一季、開關與章、眼前還是那一則那一個節點（發掘的第一幕：名額還是自己的，被放回→gone 並清眼前）。
    那一顆已經有子節點：當重放（A 開的是新單＝B 中間被別人寫掉，多回 taken 那一句）。自己說的：審字 bad 或模型回 improper→不寫、tries 加一、
    refuse_typed；被擋滿、被禁寫→locked。其餘寫一幕：draft 是 None 或 problems 非空存替身（模型的字不存），合格存模型的字。"""
    s, p, t = ctx.state, ctx.state.player, _t(ctx)
    w = p.yiwen
    if not _on(ctx) or w is None or not w.opening or _season(ctx) != req.season or w.opening != req.opening or w.node != req.node:
        return []
    if not valid(ctx):
        if w.role == rules.FIND and w.tale == 0:  # B 中間世界那一格把名額放回了
            _clear(w)
            return [_line(ctx, "gone")]
        return []
    if _done(w):
        return []
    store, key, season, clock = store_of(ctx), _key(ctx), _season(ctx), _clock(ctx)
    if key != req.key:
        return []
    if w.tale == 0:
        _reattach(ctx, store, w, key, season)
    if w.tale != req.tale:
        return []
    opening, here, depth, _ = _choices_here(ctx, w, store)
    label = req.pick
    child = next((n for n in store.children(w.tale, w.node) if n["pick"] == label), None) if w.tale else None
    out: list[str] = []
    if child is not None:
        if not isinstance(req, rules.Replay):
            out.append(_line(ctx, "taken"))  # B 中間別人先寫了這一步：照那一幕重放
        out += _replay(ctx, w, child)
        nid, ndepth = child["id"], int(child["depth"])
    elif isinstance(req, rules.Replay):
        return []
    else:
        if not _writable(store, w, w.node):
            return [_line(ctx, "locked", tale=w.tale, node=w.node)]
        if req.typed and (w.tries >= t.typed_tries or store.muted(key, clock)):
            return [_line(ctx, "locked", tale=w.tale, node=w.node)]
        if req.typed and (screened == "bad" or (draft is not None and draft.verdict == rules.IMPROPER)):
            w.tries += 1
            return [_line(ctx, "refuse_typed", tale=w.tale, node=w.node)]
        got = _write_node(ctx, store, w, req, opening, depth, draft, here=here)
        if isinstance(got, list):
            return got
        nid, ndepth, written = got
        out += written
    store.step_walk(tale=w.tale, account=key, season=season, node=nid, at=clock)
    w.node, w.tries = nid, 0
    if ndepth >= rules.DEPTH:
        out += _finish(ctx, store, w, nid)
    return out


def busy_line(ctx, req: rules.YiwenRequest) -> str:
    """B 段說書人接不下去時那一句（busy 那一組，照這一則這一步挑；只讀季數）。"""
    return rules.fill(rules.pick_line(rules.lines(), "busy", season=req.season, tale=req.tale, node=req.parent))


def _replay(ctx, w: YiwenWalk, child: dict) -> list[str]:
    """重放：零等待，當場畫出存下來的那一幕（回聲一句；第一次重放這一幕給 per_replay）。"""
    out = [_line(ctx, "echo", tale=w.tale, node=child["id"], pick=child["pick"])]
    if child["id"] not in w.paid_scenes:
        w.paid_scenes.append(child["id"])
        out += _grant(ctx, _t(ctx).per_replay)
    return out


def _write_node(ctx, store, w: YiwenWalk, req: rules.YiwenRequest, opening: dict, depth: int, draft: rules.SceneDraft | None,
                here: dict | None = None):
    """寫一幕（替身與模型的字共用）：發掘的第一幕先開則；回 (節點 id, 深度, 回話) 或擋下的那一句（list）。
    here 是上一個節點（開場是 None；第 264 批：替身的做法從它來）。"""
    s, p, t = ctx.state, ctx.state.player, _t(ctx)
    key, season, clock = _key(ctx), _season(ctx), _clock(ctx)
    label, luck = req.pick, req.luck
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
    if draft is None or draft.problems or len(draft.text) != 2:  # 寫壞、叫不到、兩次都沒過：替身（模型的字不存）
        group = "broken_end" if depth >= rules.DEPTH else "broken"  # 第 264 批①：第三步的替身讀起來是這件事收了
        text = [_line(ctx, group, tale=w.tale, node=w.node, pick=label, thing=thing)]
        options = rules.fallback_options(rules.lines(), season=season, tale=w.tale, node=w.node, thing=thing) if depth < rules.DEPTH else []
        if options and depth >= 2:  # 第 264 批②(a)：上一幕的做法照理都還做得到（替身說的是「還在原處」）
            options = rules.stand_in_options(here, label, options)
        ledger, fallback = [], True
    else:
        text = list(draft.text)
        options = list(draft.options) if depth < rules.DEPTH else []
        ledger, fallback = (list(draft.ledger) if depth < rules.DEPTH else []), False
    own = w.own_from >= 0
    got = store.add_node(tale=w.tale, parent=w.node, depth=depth, pick=label, typed=req.typed, by=key, shown=p.name, luck=luck, text=text,
                         options=options, ledger=ledger, fallback=fallback, at=clock, branch_cap=t.branch_cap, free_branches=t.free_branches,
                         can_pay=False, own=True)
    if got.kind != "new":
        return [_line(ctx, "taken")]
    if not own:
        w.own_from = w.node  # 接著別人停下的地方寫：從這裡往下是自己的路
    nid = got.node["id"]
    out = list(text)
    if nid not in w.paid_scenes:
        w.paid_scenes.append(nid)
        out += _grant(ctx, t.per_scene)
        if luck == rules.GOOD:
            out += _luck_material(ctx, w, nid)
    return nid, depth, out


def _reattach(ctx, store, w: YiwenWalk, key: str, season: int) -> None:
    """第 251 批②：發掘者第一步已寫進旁檔（開則＋第一幕）、主交易卻撤回了（存檔失敗、行程被砍）：存檔的 w.tale 回到 0，
    旁檔卻有這一季這一句、發掘者是自己的那一則。接回——w.tale 指回去，已經在旁檔的幕由 step 走重放（不重寫、不另開、不多佔名額）；
    世界那一格有就把 tale 補上（已經是就不寫），沒有就補記一格。那一則是別人的、被拿掉的：不接，step 照舊開則撞 Taken。"""
    if w.role != rules.FIND:
        return
    row = store.tale_by_opening(season, w.opening)
    if row is None or row["discoverer"] != key or row["status"] == rules.REMOVED:
        return
    w.tale = int(row["id"])
    yw = ctx.state.world.yiwen = ctx.state.world.yiwen or YiwenWorld()
    claim = yw.taken.get(w.opening)
    if claim is None:
        yw.taken[w.opening] = YiwenClaim(by=key, at=float(row["discovered_at"]), tale=w.tale)
    elif claim.tale == w.tale:
        return
    else:
        claim.tale = w.tale
    ctx._save_season()


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
    t = _t(ctx)
    typed_state = "off"
    if not done and depth <= rules.DEPTH:
        kids = {n["pick"]: n for n in store.children(w.tale, w.node)} if w.tale else {}
        writable = _writable(store, w, w.node)
        labels = rules.labels(o, here)
        for i, label in enumerate(labels):
            kid = kids.get(label)
            if kid is not None:
                choices.append({"i": i, "label": label, "state": "walked", "by": kid["by_shown"], "steps": steps.get(kid["id"], 0)})
            else:
                choices.append({"i": i, "label": label, "state": "free" if writable else "locked", "by": "", "steps": 0,
                                "note": "" if writable else _line(ctx, "locked", tale=w.tale, node=w.node)})
        for label, kid in kids.items():  # 自己說寫成的那幾幕：各一塊路牌（送 pick "zhupi"＋那一句）
            if kid["typed"] and label not in labels:
                choices.append({"i": "zhupi", "label": label, "state": "walked", "by": kid["by_shown"], "steps": steps.get(kid["id"], 0), "typed": True})
        if not writable:
            typed_state = "locked"
        elif w.tries >= t.typed_tries or store.muted(key, _clock(ctx)):
            typed_state = "spent"
        else:
            typed_state = "open"
    walkers = sum(store.footprints(w.tale).values()) if w.tale else 0
    frame = _line(ctx, "first_frame") if w.role == rules.FIND else _line(ctx, f"trail_frame.{kind}", tale=w.tale, place=place)
    return {
        "opening": w.opening, "tale": w.tale, "title": o["title"], "place": w.place, "place_name": place, "kind": kind,
        "kind_word": rules.KINDS.get(kind, ""), "mark": "first" if w.role == rules.FIND else "trail", "frame": frame, "hook": o["hook"],
        "walkers": walkers, "depth": min(depth, rules.DEPTH), "node": w.node, "scenes": scenes, "choices": choices,
        "typed": {"state": typed_state, "max": t.typed_max, "tries_left": max(0, t.typed_tries - w.tries)},
        "done": done, "close": _line(ctx, "close", tale=w.tale, node=w.node) if done else "", "gains": "",
    }
