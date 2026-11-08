"""門派的動作（設計稿 v6）：此地還能做的「拜入」與「叛出」、換季照帶門派身分（第一批）；師門武譜的獻式、試練、學式與給畫面的那一份（第二批）。
武譜的帳在全服的 SharedWorldState.sect_books（不分季），一律經 ctx.world.mutate 改；規則在 book.py。真人假人同一套。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia.characters import CharacterStore, name_key
from tianxia.core.option import Option
from tianxia import insight_fx, insights, library
from tianxia.world_state import SectBook

from . import book as B
from . import rules

if TYPE_CHECKING:
    from tianxia.engine import Game
    from tianxia.state import GameState

KIND = "zongmen"


def options(ctx: Game) -> list[Option]:
    p, c = ctx.state.player, ctx.content
    if p.journey is not None:
        return []
    out: list[Option] = []
    here = rules.sect_here(c, p.location)
    if here is not None and rules.join_problem(p, c, here) is None:
        out.append(Option(
            id=f"{KIND}:join:{here.id}", label=rules.JOIN.format(sect=here.name),
            confirm=rules.JOIN_CONFIRM.format(sect=here.name), confirm_yes="拜入",
        ))
    mine = c.sects.get(p.sect) if p.sect else None
    if mine is not None and mine.location == p.location:
        out += _try_options(ctx, mine.id)
        out.append(Option(
            id=f"{KIND}:leave:{mine.id}", label=rules.LEAVE.format(sect=mine.name),
            confirm=rules.LEAVE_CONFIRM.format(sect=mine.name), confirm_yes="叛出",
        ))
    return out


def choose(ctx: Game, arg: str) -> list[str]:
    verb, _, sect_id = arg.partition(":")
    sect_id = sect_id.partition(":")[0]
    p, c = ctx.state.player, ctx.content
    sect = c.sects.get(sect_id)
    if sect is None:
        return [rules.GONE]
    if verb == "join":
        if not rules.own(sect) or not c.sect_open(sect.id) or rules.join_problem(p, c, sect) is not None:
            return [rules.GONE]
        return rules.join(p, c, sect)
    if verb == "try":
        return try_entry(ctx, sect_id_of(arg)[0], sect_id_of(arg)[1])
    if verb == "leave":
        if p.sect != sect.id or sect.location != p.location or p.journey is not None:
            return [rules.GONE]
        return rules.leave(p, c)
    return [rules.GONE]


def carry(ctx: Game, old: GameState) -> None:
    """換季照帶門派身分（設計稿 v6「門派身分跨季保留」）：上一季拜的那一門還在就照舊是它的人。"""
    sect = old.player.sect
    if sect and sect in ctx.content.sects and ctx.content.sect_open(sect):
        ctx.state.player.sect = sect


# ── 師門武譜（第二批）──────────────────────────────


def sect_id_of(arg: str) -> tuple[str, str]:
    """「try:<門派>:<一式>」→（門派, 一式）。"""
    _, _, rest = arg.partition(":")
    sect_id, _, entry_id = rest.partition(":")
    return sect_id, entry_id


def _books(ctx: Game) -> dict[str, SectBook] | None:
    try:
        return ctx.world.read().sect_books
    except (AttributeError, NotImplementedError):
        return None


def book_of(ctx: Game, sect_id: str) -> SectBook:
    books = _books(ctx)
    return (books or {}).get(sect_id) or SectBook()


def _member_sect(ctx: Game):
    """我此刻是哪一門的人（開著的那一門）；不是誰的門人是 None。"""
    p, c = ctx.state.player, ctx.content
    return c.sects.get(p.sect) if p.sect and c.sect_open(p.sect) else None


def _at_gate(ctx: Game, sect) -> bool:
    p = ctx.state.player
    return sect is not None and p.location == sect.location and p.journey is None


def members(ctx: Game, sect_id: str) -> int:
    """這一季這一門有幾個人（真人假人一樣算）。"""
    season = ctx.world.get_season_number()
    return sum(1 for s in CharacterStore(ctx.world.db).all() if s.player.sect == sect_id and s.player.season_number == season)


def _xinde(ctx: Game) -> int:
    return int(ctx.state.player.stats.get("xinde", 0))


def _pay(ctx: Game, amount: int) -> None:
    p = ctx.state.player
    p.stats["xinde"] = p.stats.get("xinde", 0) - amount


def offerable(ctx: Game) -> list[tuple[str, str]]:
    """手上獻得了的意境（id, 名字）：自己悟的與合出來的，不是內容寫死的基本意境、不是神品。"""
    p, c = ctx.state.player, ctx.content
    sect = _member_sect(ctx)
    taken = {e.insight.name for e in book_of(ctx, sect.id).entries if e.status != "dropped"} if sect is not None else set()
    out = []
    for iid in p.insights:
        if insight_fx.base_id(iid) in c.insights or insight_fx.is_god(ctx.state, iid):
            continue
        found = insights.resolve(iid, c, ctx.world, ctx.state)
        if found is not None and found.name not in taken:  # 譜上已經有的（含自己學來的那一份）不列
            out.append((iid, found.name))
    return out


def offer(ctx: Game, insight_id: str) -> list[str]:
    sect = _member_sect(ctx)
    if not _at_gate(ctx, sect):
        return [rules.GONE]
    p, c, cfg = ctx.state.player, ctx.content, ctx.content.config.zongmen
    if insight_id not in p.insights:
        return [B.NOT_YOURS + "。"]
    if insight_fx.base_id(insight_id) in c.insights:
        return [B.BASIC + "。"]
    if insight_fx.is_god(ctx.state, insight_id):
        return [B.GOD + "。"]
    found = insights.resolve(insight_id, c, ctx.world, ctx.state)
    if found is None:
        return [B.NOT_YOURS + "。"]
    fx = insight_fx.record(ctx.state, c, ctx.world, insight_id, found)
    count = members(ctx, sect.id)
    out: list[str] = []

    def _apply(shared) -> None:
        bk = shared.sect_books.setdefault(sect.id, SectBook())
        B.expire(bk, ctx.now)
        problem = B.offer_problem(bk, cfg, p.name, found, ctx.now)
        if problem is not None:
            out.append(problem + "。")
            return
        B.offer(bk, cfg, p.name, found, fx, p.season_number, count, ctx.now)
        out.append(B.OFFERED.format(name=found.name))

    ctx.world.mutate(_apply)
    return out


def _try_options(ctx: Game, sect_id: str) -> list[Option]:
    """山門前的「試練」：同門獻上來、還在等的每一式（自己獻的、試過的不列）。"""
    cfg = ctx.content.config.zongmen
    out = []
    me = name_key(ctx.state.player.name)
    for e in B.pending(book_of(ctx, sect_id), ctx.now):
        if name_key(e.giver) == me or any(name_key(t) == me for t in e.tried):
            continue
        out.append(Option(
            id=f"zongmen:try:{sect_id}:{e.id}", label=TRY.format(name=e.insight.name, giver=e.giver),
            enabled=_xinde(ctx) >= cfg.trial_xinde, note=f"{e.giver}獻・心得 {cfg.trial_xinde}・{len(e.tried)}／{e.need} 人試過",
        ))
    return out


TRY = "試{name}"  # 待 joy 潤（此地可為一格只放得下五字；小字寫誰獻的）


def try_entry(ctx: Game, sect_id: str, entry_id: str) -> list[str]:
    sect = _member_sect(ctx)
    if sect is None or sect.id != sect_id or not _at_gate(ctx, sect):
        return [rules.GONE]
    p, cfg = ctx.state.player, ctx.content.config.zongmen
    out: list[str] = []
    paid = {"ok": False}

    def _apply(shared) -> None:
        bk = shared.sect_books.get(sect_id)
        entry = B.find(bk, entry_id) if bk is not None else None
        if entry is None:
            out.append(B.GONE)
            return
        B.expire(bk, ctx.now)
        problem = B.try_problem(entry, p.name, _xinde(ctx), cfg, ctx.now)
        if problem is not None:
            out.append(problem + "。")
            return
        paid["ok"] = True
        out.append(B.TRIED.format(name=entry.insight.name, xinde=cfg.trial_xinde))
        if B.try_entry(bk, entry, p.name, ctx.now):
            out.append(B.ENTERED.format(name=entry.insight.name, sect=sect.name, num=B.num(entry.number)))

    ctx.world.mutate(_apply)
    if paid["ok"]:
        _pay(ctx, cfg.trial_xinde)
    return out


def learn_problem(ctx: Game, entry) -> str | None:
    cfg = ctx.content.config.zongmen
    if B.learned_name(ctx.state.player, entry):
        return B.HAVE
    if library.full(ctx.state, ctx.content):
        return B.FULL
    if _xinde(ctx) < cfg.learn_xinde:
        return B.NO_XINDE.format(xinde=cfg.learn_xinde)
    return None


def learn(ctx: Game, entry_id: str) -> list[str]:
    sect = _member_sect(ctx)
    if not _at_gate(ctx, sect):
        return [rules.GONE]
    entry = B.find(book_of(ctx, sect.id), entry_id)
    if entry is None or entry.status != "in":
        return [B.GONE]
    problem = learn_problem(ctx, entry)
    if problem is not None:
        return [problem + "。"]
    insight, fx = B.learn_copy(entry)
    own = insights.add_own(ctx.state, insight)
    ctx.state.player.insight_fx[own.id] = fx
    _pay(ctx, ctx.content.config.zongmen.learn_xinde)
    return [B.LEARNED.format(sect=sect.name, num=B.num(entry.number), name=own.name)]


def view(ctx: Game) -> dict | None:
    """俠客頁門下那一段的「師門武譜」（status 的 zongmen）：不是哪一門的人是 None（不畫）。"""
    sect = _member_sect(ctx)
    if sect is None:
        return None
    c, cfg, p = ctx.content, ctx.content.config.zongmen, ctx.state.player
    bk = book_of(ctx, sect.id)
    gate = _at_gate(ctx, sect)
    me = name_key(p.name)
    entries = []
    for e in B.entries_in(bk):
        problem = learn_problem(ctx, e) if gate else rules.AT_GATE.format(place=c.locations[sect.location].name)
        entries.append({
            "id": e.id, "num": B.num(e.number), "name": e.insight.name, "attr": e.insight.attribute,
            "fx": insight_fx.label(c, B.learn_copy(e)[1]), "carve": B.carve(e), "note": e.insight.note,
            "effects": [f"{x['name']}：{x['desc']}" for x in insight_fx.effects(c, B.learn_copy(e)[1]) if x["desc"]],
            "learned": B.learned_name(p, e), "problem": problem or "",
        })
    waiting = [{
        "id": e.id, "name": e.insight.name, "giver": e.giver, "tried": len(e.tried), "need": e.need,
        "mine": name_key(e.giver) == me, "done": any(name_key(t) == me for t in e.tried),
    } for e in B.pending(bk, ctx.now)]
    offers = [{"id": iid, "name": name} for iid, name in offerable(ctx)] if gate else []
    return {
        "sect": sect.name, "place": c.locations[sect.location].name, "gate": gate, "entries": entries, "waiting": waiting,
        "offers": offers, "learn_xinde": cfg.learn_xinde, "trial_xinde": cfg.trial_xinde,
    }
