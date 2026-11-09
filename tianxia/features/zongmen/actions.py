"""門派的動作（設計稿 v6）：此地還能做的「拜入」與「叛出」、換季照帶門派身分（第一批）；師門武譜的獻式、試練、學式與給畫面的那一份（第二批）。
武譜的帳在全服的 SharedWorldState.sect_books（不分季），一律經 ctx.world.mutate 改；規則在 book.py。真人假人同一套。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia.characters import CharacterStore, name_key
from tianxia.core.option import Option
from tianxia import insight_fx, insights, library, team
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


ART = "a:"  # 獻武學的 id 前綴（俠客頁的下拉選單；意境照舊是意境的 id）


def _arts_held(ctx: Game) -> list[str]:
    p = ctx.state.player
    return [a for a in dict.fromkeys([p.member.neigong_id, p.member.wugong_id, *p.arts]) if a]


def offerable(ctx: Game) -> list[tuple[str, str]]:
    """手上獻得了的（id, 寫給人看的名字）：自己悟的與合出來的意境（不是內容寫死的基本意境、不是神品），
    與自創、合成的武學（不是內容寫死的；第三批），譜上已經有同名的不列（含自己學來的那一份）。"""
    p, c = ctx.state.player, ctx.content
    sect = _member_sect(ctx)
    taken = B.taken_names(book_of(ctx, sect.id)) if sect is not None else set()
    out = []
    for iid in p.insights:
        if insight_fx.base_id(iid) in c.insights or insight_fx.is_god(ctx.state, iid):
            continue
        found = insights.resolve(iid, c, ctx.world, ctx.state)
        if found is not None and found.name not in taken:
            out.append((iid, f"意境・{found.name}"))
    for aid in _arts_held(ctx):
        art = None if aid in c.skills else team.resolve_art(aid, c, ctx.world)
        if art is not None and art.name not in taken:
            out.append((ART + aid, f"{art.kind}・{art.name}（{team.art_quality(ctx.state, art)}）"))
    return out


def offer(ctx: Game, offer_id: str) -> list[str]:
    sect = _member_sect(ctx)
    if not _at_gate(ctx, sect):
        return [rules.GONE]
    p, c, cfg = ctx.state.player, ctx.content, ctx.content.config.zongmen
    kw: dict = {}
    if offer_id.startswith(ART):
        aid = offer_id[len(ART):]
        art = None if aid in c.skills or aid not in _arts_held(ctx) else team.resolve_art(aid, c, ctx.world)
        if art is None:
            return [B.NOT_YOURS + "。"]
        name, kw = art.name, {"art": art, "art_quality": team.art_quality(ctx.state, art)}
    else:
        if offer_id not in p.insights:
            return [B.NOT_YOURS + "。"]
        if insight_fx.base_id(offer_id) in c.insights:
            return [B.BASIC + "。"]
        if insight_fx.is_god(ctx.state, offer_id):
            return [B.GOD + "。"]
        found = insights.resolve(offer_id, c, ctx.world, ctx.state)
        if found is None:
            return [B.NOT_YOURS + "。"]
        name, kw = found.name, {"insight": found, "fx": insight_fx.record(ctx.state, c, ctx.world, offer_id, found)}
    count = members(ctx, sect.id)
    out: list[str] = []

    def _apply(shared) -> None:
        bk = shared.sect_books.setdefault(sect.id, SectBook())
        B.expire(bk, ctx.now)
        problem = B.offer_problem(bk, cfg, p.name, name, ctx.now)
        if problem is not None:
            out.append(problem + "。")
            return
        B.offer(bk, cfg, p.name, p.season_number, count, ctx.now, **kw)
        out.append(B.OFFERED.format(name=name))

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
            id=f"zongmen:try:{sect_id}:{e.id}", label=TRY.format(name=B.name_of(e), giver=e.giver),
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
        out.append(B.TRIED.format(name=B.name_of(entry), xinde=cfg.trial_xinde))
        if B.try_entry(bk, entry, p.name, ctx.now):
            out.append(B.ENTERED.format(name=B.name_of(entry), sect=sect.name, num=B.num(entry.number)))

    ctx.world.mutate(_apply)
    if paid["ok"]:
        _pay(ctx, cfg.trial_xinde)
    return out


def learn_problem(ctx: Game, entry, price: int | None = None) -> str | None:
    p = ctx.state.player
    if B.learned_name(p, entry):
        return B.HAVE
    if library.full(ctx.state, ctx.content):
        return B.FULL
    price = B.learn_price(entry, p.name, ctx.content.config.zongmen) if price is None else price
    if _xinde(ctx) < price:
        return B.NO_XINDE.format(xinde=price)
    if entry.art is not None:
        there = ctx.world.get_skill(entry.art.name)
        if there is not None and there.creator != entry.art.creator:
            return B.NAME_TAKEN
    return None


def _give(ctx: Game, entry, quality: str) -> str:
    """把這一式給學的人一份：意境是私有的一份；武學照這一季的全服登記（這一季還沒有就照抄的那一份再登記一門），品質記成自己那一份的。
    回學到的名字（空字串：武學這一季登記不上，名字撞了）。"""
    if entry.art is None:
        insight, fx = B.learn_copy(entry, quality)
        own = insights.add_own(ctx.state, insight)
        ctx.state.player.insight_fx[own.id] = fx
        return own.name
    art = ctx.world.get_skill(entry.art.name)
    if art is None:
        art = entry.art.model_copy(deep=True)
        if not ctx.world.claim_skill_name(art):
            return ""
    elif art.creator != entry.art.creator:
        return ""
    library.store_art(ctx.state, art, quality)
    return art.name


def learn(ctx: Game, entry_id: str) -> list[str]:
    sect = _member_sect(ctx)
    if not _at_gate(ctx, sect):
        return [rules.GONE]
    entry = B.find(book_of(ctx, sect.id), entry_id)
    if entry is None or entry.status != "in":
        return [B.GONE]
    p, cfg = ctx.state.player, ctx.content.config.zongmen
    price = B.learn_price(entry, p.name, cfg)
    problem = learn_problem(ctx, entry, price)
    if problem is not None:
        return [problem + "。"]
    quality = B.art_learn_quality(entry) if entry.art is not None else None
    name = _give(ctx, entry, quality)
    if not name:
        return [B.NAME_TAKEN + "。"]
    _pay(ctx, price)

    def _note(shared) -> None:
        bk = shared.sect_books.get(sect.id)
        found = B.find(bk, entry_id) if bk is not None else None
        if found is not None:
            B.note_learner(found, p.name)

    ctx.world.mutate(_note)
    return [B.LEARNED.format(sect=sect.name, num=B.num(entry.number), name=name)]


# ── 殘頁（第三批）──────────────────────────────


def _hash(text: str) -> int:
    import hashlib  # noqa: PLC0415

    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:12], 16)


def raid_win(ctx: Game, target: str) -> list[str]:
    """截殺（設伏）打贏 target（事件 raid_win 的 zongmen 那一格）：他是別門的親傳、我不是那一門的人，照機率撿一張殘頁。
    寫自己那一則江湖紀錄（不混進懸賞榜那一則），回 []。"""
    if not ctx.content.config.zongmen.enabled:
        return []
    from tianxia.characters import CharacterStore  # noqa: PLC0415

    cfg, me = ctx.content.config.zongmen, ctx.state.player
    loaded = CharacterStore(ctx.world.db).load(target)
    if loaded is None:
        return []
    them = loaded.player
    sect = ctx.content.sects.get(them.sect) if them.sect and ctx.content.sect_open(them.sect) else None
    if sect is None or me.sect == sect.id:
        return []
    bk = book_of(ctx, sect.id)
    if not B.is_inner(them, bk, cfg):
        return []
    seed = f"zongmen|page|{name_key(me.name)}|{name_key(them.name)}|{ctx.state.world.time}"
    if (_hash(seed) % 10000) / 10000 >= cfg.page_chance:
        return []
    out: list[str] = []

    def _apply(shared) -> None:
        book = shared.sect_books.get(sect.id)
        entry = B.page_pick(book, me, _hash(seed + "|pick")) if book is not None else None
        if entry is None:
            return
        entry.pages.append(name_key(me.name))
        out.append(B.PAGE_FOUND.format(who=them.name, sect=sect.name, num=B.num(entry.number), name=B.name_of(entry)))

    ctx.world.mutate(_apply)
    if out and ctx._draft is None:
        ctx._write(rules.TITLE, out)
        return []
    return out


def page_learn(ctx: Game, sect_id: str, entry_id: str) -> list[str]:
    """照殘頁偷學一份下品的（哪裡都能學，花 page_xinde 心得）；學了殘頁收回。"""
    sect = ctx.content.sects.get(sect_id)
    books = _books(ctx) or {}
    entry = B.find(books.get(sect_id) or SectBook(), entry_id)
    p, cfg = ctx.state.player, ctx.content.config.zongmen
    if sect is None or entry is None or entry.status != "in" or name_key(p.name) not in entry.pages:
        return [B.GONE]
    problem = learn_problem(ctx, entry, cfg.page_xinde)
    if problem is not None:
        return [problem + "。"]
    name = _give(ctx, entry, B.PAGE_QUALITY)
    if not name:
        return [B.NAME_TAKEN + "。"]
    _pay(ctx, cfg.page_xinde)

    def _drop(shared) -> None:
        bk = shared.sect_books.get(sect_id)
        found = B.find(bk, entry_id) if bk is not None else None
        if found is not None and name_key(p.name) in found.pages:
            found.pages.remove(name_key(p.name))

    ctx.world.mutate(_drop)
    return [B.PAGE_LEARNED.format(sect=sect.name, num=B.num(entry.number), name=name)]


def _row(ctx: Game, e, problem: str) -> dict:
    c = ctx.content
    if e.art is not None:
        fx, effects, note = f"{e.art.kind}・學到的是{B.art_learn_quality(e)}", [], e.art.note
    else:
        fx = insight_fx.label(c, B.learn_copy(e)[1])
        effects = [f"{x['name']}：{x['desc']}" for x in insight_fx.effects(c, B.learn_copy(e)[1]) if x["desc"]]
        note = e.insight.note
    return {
        "id": e.id, "num": B.num(e.number), "name": B.name_of(e), "attr": B.attr_of(e), "kind": B.kind_of(e),
        "fx": fx, "carve": B.carve(e), "note": note, "effects": effects,
        "learned": B.learned_name(ctx.state.player, e), "problem": problem or "",
    }


def _pages_view(ctx: Game) -> list[dict]:
    c, cfg = ctx.content, ctx.content.config.zongmen
    out = []
    for sid, e in B.pages_of(_books(ctx) or {}, ctx.state.player.name):
        row = _row(ctx, e, learn_problem(ctx, e, cfg.page_xinde) or "")
        row.update({"sect_id": sid, "sect": c.sects[sid].name if sid in c.sects else sid})
        out.append(row)
    return out


def view(ctx: Game) -> dict | None:
    """俠客頁門下那一段的「師門武譜」（status 的 zongmen）：不是哪一門的人、手上也沒有殘頁是 None（不畫）。"""
    if not ctx.content.config.zongmen.enabled:
        return None
    sect = _member_sect(ctx)
    c, cfg, p = ctx.content, ctx.content.config.zongmen, ctx.state.player
    pages = _pages_view(ctx)
    if sect is None:
        return {"sect": None, "pages": pages, "page_xinde": cfg.page_xinde} if pages else None
    bk = book_of(ctx, sect.id)
    gate = _at_gate(ctx, sect)
    me = name_key(p.name)
    entries = []
    for e in B.entries_in(bk):
        problem = learn_problem(ctx, e) if gate else rules.AT_GATE.format(place=c.locations[sect.location].name)
        row = _row(ctx, e, problem)
        price = B.learn_price(e, p.name, cfg)
        row["price"] = price if price != cfg.learn_xinde else None
        entries.append(row)
    waiting = [{
        "id": e.id, "name": B.name_of(e), "kind": B.kind_of(e), "giver": e.giver, "tried": len(e.tried), "need": e.need,
        "mine": name_key(e.giver) == me, "done": any(name_key(t) == me for t in e.tried),
    } for e in B.pending(bk, ctx.now)]
    offers = [{"id": iid, "name": name} for iid, name in offerable(ctx)] if gate else []
    return {
        "sect": sect.name, "place": c.locations[sect.location].name, "gate": gate, "entries": entries, "waiting": waiting,
        "offers": offers, "learn_xinde": cfg.learn_xinde, "trial_xinde": cfg.trial_xinde,
        "inner": B.is_inner(p, bk, cfg), "pages": pages, "page_xinde": cfg.page_xinde,
    }
