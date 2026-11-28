"""門派論劍的動作（設計稿第三版；Joy 2026-11-28「季末第一就不用再送絕招動畫了 但是機制這樣可以 開始做」）。

一週一場（季曆；7 天季是一段一場）：
- 報名（lunjian:sign）：拜了門的人，這一週最後一天 draw_hour 點以前隨時報、隨時更新分身（同擂台：抄此刻的身手）。
- 抽籤（draw_hour 點）：有人報名的門派兩兩配對（單數那一門對江湖試劍客）；每一門取身手最高的三人，不夠的由師兄補位
  （這一週全服報名者威力的中間值 × elder_share），照身手由弱到強排成先鋒、中堅、大將。沒人報名的門派這一週不出場。
- 開打（fight_hour 點）：全自動，分身對分身三場；贏的場多的那一門勝，一樣多看大將那一場。
- 賞（各自下一次同步補）：上台的本人贏一場單挑一份四階素材（自己挑類，lunjian:claim:<素材>）；門派贏了上台的本人各一個論劍禮匣
  （三場全勝換上等），戴朱印「論劍三傑」到下一場開打。禮匣自己開（lunjian:open、lunjian:open_top）。師兄、試劍客沒有賞。
抽籤、開打都是「時刻到了誰先同步誰做」（全服那一份在 WorldState.lunjian，照 _save_season 寫回）。
包只 import 核心、共用層與自己。"""
from __future__ import annotations

from tianxia import (
    calendar,  # 核心（季曆第幾週）
    materials,  # 共用層（四階素材）
    prologue,  # 共用層（序章裡不算）
    team,  # 核心（分身的戰法、防具、五項）
    treasures,  # 共用層（玉璽碎片的戰力倍數）
)
from tianxia import rules as core_rules  # 核心（add_rumor）
from tianxia.core import annal_base as annals  # 核心（行狀）
from tianxia.core.option import Option
from tianxia.state import (
    ArenaEntry,
    LunjianBag,
    LunjianMatch,
    LunjianSeat,
    LunjianWeek,
    LunjianWorld,
    Rumor,
)
from tianxia.wallet import GIFT

from . import rules

# 給玩家看的字（待 joy 潤）
TITLE = "門派論劍"  # 待 joy 潤（江湖紀錄的標題、鈕的前綴）
SIGN_LABEL = "門派論劍・報名"  # 待 joy 潤
RESIGN_LABEL = "門派論劍・更新分身"  # 待 joy 潤
SIGNED = "你替{sect}報了這一週的論劍：{draw} 截止、抽籤，{fight} 開打。分身照你此刻的身手。"  # 待 joy 潤
RESIGNED = "分身換成你此刻的身手了。"  # 待 joy 潤
NO_SECT = "要先拜入一個門派，才上得了論劍台。"  # 待 joy 潤
CLOSED = "這一週已經截止報名了。"  # 待 joy 潤
NO_POWER = "你還沒有能上台的武學。"  # 待 joy 潤
GONE = "（此刻無法這麼做。）"  # 待 joy 潤
OPEN_LABEL = "門派論劍・開論劍禮匣（{n}）"  # 待 joy 潤
OPEN_TOP_LABEL = "門派論劍・開上等論劍禮匣（{n}）"  # 待 joy 潤
BOX, TOP_BOX = "論劍禮匣", "上等論劍禮匣"  # 待 joy 潤
CLAIM_LABEL = "門派論劍・挑一份四階素材：{mat}（還有 {n} 份）"  # 待 joy 潤
OPENED = {  # 待 joy 潤（開出來的那一句；{box} 是哪一種匣）
    "mat": "打開{box}：四階素材 {n} 份，自己挑一類。",
    "legend": "打開{box}：{legend} ×{n}。",
    "coin": "打開{box}：{coin} {n}。",
    "move": "打開{box}：免費製作一次絕招動畫。",
}
COIN_NAME = "元寶"  # 待 joy 潤（五銖上線之前送的那一種）
GUEST_SECT = "江湖試劍客"  # 待 joy 潤（單數那一門的對手）
DRAW_RUMOR = "這一週的門派論劍抽了籤：{pairs}。"  # 待 joy 潤
FIGHT_WIN = "第 {week} 週門派論劍，{win}勝{lose}，{score}。"  # 待 joy 潤（江湖史）
FIGHT_DRAW = "第 {week} 週門派論劍，{a}與{b}打成平手。"  # 待 joy 潤
PAY_SEAT = "你上台當{seat}，對上{foe}：{tier}。"  # 待 joy 潤
PAY_WIN = "{sect}勝了。上台的人各得一個{box}，戴上朱印「論劍三傑」，到下一場開打。"  # 待 joy 潤
PAY_LOSE = "{sect}這一場沒能贏下來。"  # 待 joy 潤
PAY_DRAW = "兩門打成平手。"  # 待 joy 潤
PAY_PICK = "你贏了這一場單挑，四階素材一份，自己挑一類。"  # 待 joy 潤
SEAL = "論劍三傑"  # 待 joy 潤（朱印）
ANNAL_WIN = "在門派論劍上替{sect}出戰，門派勝"  # 待 joy 潤（行狀）
OPENED_KEEP = 5
DIGITS = "〇一二三四五六七八九"


def _t(ctx):
    return ctx.content.config.lunjian


def _key(ctx) -> str:
    return ctx._mall_owner()


def _season(ctx) -> int:
    return int(ctx.state.player.season_number or 0)


def _now(ctx) -> float:
    return float(ctx.state.world.time)


def _week(ctx) -> int:
    w = ctx.state.world
    return int(calendar.point(w.time, ctx.content, w).week)


def _on(ctx) -> bool:
    return rules.on(ctx.content) and not prologue.active(ctx.state, ctx.content)


def _running(ctx) -> bool:
    return _on(ctx) and ctx.world.season_phase() == "running"


def _sect(ctx) -> str | None:
    sect = ctx.state.player.sect
    return sect if sect and ctx.content.sect_open(sect) else None


def sect_name(ctx, sect: str) -> str:
    if not sect:
        return GUEST_SECT
    d = ctx.content.sects.get(sect)
    return d.name if d is not None else sect


def draw_at(ctx, week: int) -> float:
    return rules.draw_at(week, ctx.content, ctx.state.world)


def fight_at(ctx, week: int) -> float:
    return rules.fight_at(week, ctx.content, ctx.state.world)


def _lw(ctx, make: bool = False) -> LunjianWorld | None:
    w = ctx.state.world
    if w.lunjian is None and make:
        w.lunjian = LunjianWorld()
    return w.lunjian


def week_of(ctx, week: int, make: bool = False) -> LunjianWeek | None:
    lw = _lw(ctx, make)
    if lw is None:
        return None
    got = next((x for x in lw.weeks if x.week == week), None)
    if got is None and make:
        got = LunjianWeek(week=week)
        lw.weeks.append(got)
    return got


def bag(ctx, make: bool = False) -> LunjianBag | None:
    p = ctx.state.player
    if p.lunjian is None and make:
        p.lunjian = LunjianBag()
    return p.lunjian


# ── 分身 ──


def snapshot(ctx) -> ArenaEntry:
    """此刻的分身（同擂台報名那一份：威力、三招份量、職位、氣血上限、戰法、防具、五項、兵器；形象在第二批畫對打時再接）。"""
    s, c, p = ctx.state, ctx.content, ctx.state.player
    _, cap = ctx._player_hp_and_cap()
    m = p.member
    arts = [a.name for a in (team.player_art(s, c, ctx.world, m.wugong_id), team.player_art(s, c, ctx.world, m.neigong_id)) if a is not None]
    return ArenaEntry(
        name=p.name, power=ctx._battle_power(), bare=_bare(ctx), scores=ctx._battle_scores(mounted=False), role=ctx._battle_role(),
        hp_cap=cap, arts=arts, kit=team.self_side(s, c, ctx.world), cut=team.duel_armor_cut(s, c, ctx.world),
        card=team.pvp_card(s, c, ctx.world), weapon=p.weapon.kind if p.weapon else "", joined=_now(ctx),
    )


def _bare(ctx) -> float | None:
    """戴著玉璽碎片（treasures.power_scale 不是 1）時不含碎片的威力（同擂台 arena_bare：給別人看的身手）；沒有是 None。"""
    if treasures.power_scale(ctx.state, ctx.content) == 1.0:
        return None
    return ctx._battle_power(seal=False)


# ── 抽籤、開打：時刻到了誰先同步誰做 ──


def resolve(ctx) -> bool:
    """回 True＝全服那一份動了（呼叫的人負責 _save_season）。"""
    lw = _lw(ctx)
    if lw is None:
        return False
    now, changed = _now(ctx), False
    for w in lw.weeks:
        if not w.drawn and now >= draw_at(ctx, w.week):
            _draw(ctx, lw, w)
            changed = True
        if w.drawn and not w.fought and now >= fight_at(ctx, w.week):
            _fight(ctx, w)
            changed = True
    return changed


def _draw(ctx, lw: LunjianWorld, w: LunjianWeek) -> None:
    c, t = ctx.content, _t(ctx)
    w.drawn = True
    entries = [e for e in w.entries.values() if c.sect_open(e.sect)]
    sects = sorted({e.sect for e in entries})
    if not sects:
        w.fought = True
        return
    power, like = rules.elder_power(entries, float(t.elder_share))
    before = [x for x in lw.weeks if x.week < w.week and x.matches]
    last = {frozenset((m.a, m.b)) for m in before[-1].matches} if before else set()
    for a, b in rules.pair_up(sects, last, _season(ctx), w.week):
        mine_a = [e for e in entries if e.sect == a]
        seats_a = rules.lineup(mine_a, t.seats, rules.elders_of(a), power, like, a)
        if b:
            seats_b = rules.lineup([e for e in entries if e.sect == b], t.seats, rules.elders_of(b), power, like, b)
        else:
            seats_b = rules.lineup([], t.seats, rules.guests(), power, like, "")
        w.matches.append(LunjianMatch(a=a, b=b, seats_a=seats_a, seats_b=seats_b))
    pairs = "；".join(f"{sect_name(ctx, m.a)}對{sect_name(ctx, m.b)}" for m in w.matches)
    core_rules.add_rumor(ctx.state, DRAW_RUMOR.format(pairs=pairs), content=c, named=False)


def score_of(m: LunjianMatch) -> tuple[int, int]:
    a = sum(1 for x in m.bouts if x.tier in rules.WIN_TIERS)
    b = sum(1 for x in m.bouts if x.tier == "落敗")
    return a, b


def _fight(ctx, w: LunjianWeek) -> None:
    s = ctx.state
    w.fought = True
    for i, m in enumerate(w.matches):
        rules.play(m, ctx.content, (_season(ctx), w.week, i))
        a, b = sect_name(ctx, m.a), sect_name(ctx, m.b)
        sa, sb = score_of(m)
        if m.winner:
            win, lose = (a, b) if m.winner == "a" else (b, a)
            hi, lo = (sa, sb) if m.winner == "a" else (sb, sa)
            text = FIGHT_WIN.format(week=w.week, win=win, lose=lose, score=f"{DIGITS[hi]}比{DIGITS[lo]}")
        else:
            text = FIGHT_DRAW.format(week=w.week, a=a, b=b)
        s.world.chronicle.append(Rumor(time=s.world.time, text=text))
        core_rules.add_rumor(s, text, content=ctx.content, named=False)


# ── 賞：各自下一次同步補 ──


def _mine(w: LunjianWeek, key: str) -> tuple[LunjianMatch, str] | None:
    for m in w.matches:
        side = rules.side_of(m, key)
        if side is not None:
            return m, side
    return None


def _pay(ctx, w: LunjianWeek, m: LunjianMatch, side: str) -> None:
    key, b = _key(ctx), bag(ctx, make=True)
    seats = m.seats_a if side == "a" else m.seats_b
    foes = m.seats_b if side == "a" else m.seats_a
    mine, other = (m.a, m.b) if side == "a" else (m.b, m.a)
    i = next(i for i, x in enumerate(seats) if x.key == key)
    tier = rules.tier_for(m, side, i) if i < len(m.bouts) else "僵持"
    lines = [PAY_SEAT.format(seat=rules.SEAT_NAMES[i] if i < len(rules.SEAT_NAMES) else "", foe=foes[i].name if i < len(foes) else sect_name(ctx, other), tier=tier)]
    wins = rules.wins_of(m, side, key)
    if wins:
        b.picks += wins
        lines.append(PAY_PICK)
    if m.winner == side:
        top = rules.sweep(m, side)
        if top:
            b.top_boxes += 1
        else:
            b.boxes += 1
        b.seal_until, b.seal_season = fight_at(ctx, w.week + 1), _season(ctx)
        lines.append(PAY_WIN.format(sect=sect_name(ctx, mine), box=TOP_BOX if top else BOX))
        annals.note(ctx.state, ctx.content, annals.DEED, ANNAL_WIN.format(sect=sect_name(ctx, mine)), 1)
    elif m.winner:
        lines.append(PAY_LOSE.format(sect=sect_name(ctx, mine)))
    else:
        lines.append(PAY_DRAW)
    ctx._write(TITLE, lines)


def on_sync(ctx) -> None:
    if not _on(ctx):
        return
    changed = resolve(ctx)
    lw, key = _lw(ctx), _key(ctx)
    for w in (lw.weeks if lw is not None else []):
        if not w.fought or key in w.paid:
            continue
        got = _mine(w, key)
        if got is None:
            continue
        w.paid.append(key)
        _pay(ctx, w, *got)
        changed = True
    if changed:
        ctx._save_season()


def carry(ctx, old) -> None:
    """換季：還沒用的素材、禮匣、絕招動畫照帶；朱印照季看（seal_season），換季自己失效。"""
    b = old.player.lunjian
    if b is not None and (b.picks or b.boxes or b.top_boxes or b.moves):
        ctx.state.player.lunjian = b.model_copy(update={"seal_until": 0.0, "seal_season": 0})


# ── 選項 ──


def claim_mats(content) -> list[str]:
    """挑得到的素材：第 material_tier 階，每一類一種（同地方大事的謝禮）。"""
    tier = int(content.config.lunjian.material_tier)
    out: dict[str, str] = {}
    for mid, mat in sorted(content.materials.items()):
        if mat.tier == tier and mat.attribute and mat.attribute not in out:
            out[mat.attribute] = mid
    return [out[k] for k in sorted(out, key=lambda x: "剛柔快慢陰陽虛實".find(x))]


def signed(ctx) -> bool:
    w = week_of(ctx, _week(ctx))
    return w is not None and _key(ctx) in w.entries


def can_sign(ctx) -> bool:
    w = week_of(ctx, _week(ctx))
    return _running(ctx) and _sect(ctx) is not None and _now(ctx) < draw_at(ctx, _week(ctx)) and not (w is not None and w.drawn)


def _bag_options(ctx) -> list[Option]:
    b = bag(ctx)
    if b is None:
        return []
    out = []
    if b.picks > 0:
        out += [Option(id=f"lunjian:claim:{mid}", label=CLAIM_LABEL.format(mat=ctx.content.materials[mid].name, n=b.picks)) for mid in claim_mats(ctx.content)]
    if b.top_boxes > 0:
        out.append(Option(id="lunjian:open_top", label=OPEN_TOP_LABEL.format(n=b.top_boxes)))
    if b.boxes > 0:
        out.append(Option(id="lunjian:open", label=OPEN_LABEL.format(n=b.boxes)))
    return out


def options(ctx) -> list[Option]:
    if not _on(ctx):
        return []
    out = []
    if can_sign(ctx):
        out.append(Option(id="lunjian:sign", label=RESIGN_LABEL if signed(ctx) else SIGN_LABEL))
    return out + _bag_options(ctx)


def title(ctx) -> str:  # noqa: ARG001
    return TITLE


def act(ctx, arg: str) -> list[str]:
    if resolve(ctx):
        ctx._save_season()
    verb, _, rest = arg.partition(":")
    if verb == "sign":
        return _sign(ctx)
    if verb == "claim":
        return _claim(ctx, rest)
    if verb in ("open", "open_top"):
        return _open(ctx, verb == "open_top")
    return [GONE]


def _sign(ctx) -> list[str]:
    sect = _sect(ctx)
    if sect is None:
        return [NO_SECT]
    if not can_sign(ctx):
        return [CLOSED]
    kit = snapshot(ctx)
    if kit.power <= 0:
        return [NO_POWER]
    week = _week(ctx)
    w = week_of(ctx, week, make=True)
    again = _key(ctx) in w.entries
    w.entries[_key(ctx)] = LunjianSeat(key=_key(ctx), name=ctx.state.player.name, sect=sect, kit=kit)
    ctx._save_season()
    if again:
        return [RESIGNED]
    return [SIGNED.format(sect=sect_name(ctx, sect), draw=ctx.stamp(draw_at(ctx, week)), fight=ctx.stamp(fight_at(ctx, week)))]


def _claim(ctx, mid: str) -> list[str]:
    b = bag(ctx)
    if b is None or b.picks <= 0 or mid not in claim_mats(ctx.content):
        return [GONE]
    b.picks -= 1
    got = materials.grant(ctx.state, ctx.content, mid, 1)
    return [got] if got else [GONE]


def _open(ctx, top: bool) -> list[str]:
    b = bag(ctx)
    if b is None or (b.top_boxes if top else b.boxes) <= 0:
        return [GONE]
    if top:
        b.top_boxes -= 1
    else:
        b.boxes -= 1
    t, key = _t(ctx), _key(ctx)
    b.count += 1
    kind, n = rules.open_box(t.top_box if top else t.box, rules.roll("匣", key, b.count, int(top)))
    box = TOP_BOX if top else BOX
    if kind == "coin":
        wallet = ctx._wallet()
        if wallet is None or not wallet.credit(key, {GIFT: n}, "grant", f"lunjian:{key}:{b.count}", time=ctx.pill_now()):
            kind, n = "mat", 1  # 商城關著（測試、沒有資料庫）：換成一份素材
    if kind == "mat":
        b.picks += n
    elif kind == "legend":
        ctx.state.player.legend_items += n
    elif kind == "move":
        b.moves += n
    line = OPENED.get(kind, OPENED["mat"]).format(box=box, n=n, legend=ctx.content.config.legend_item_name, coin=COIN_NAME)
    b.opened = ([line] + b.opened)[:OPENED_KEEP]
    return [line]


# ── 畫面那一份（main.lunjian）──


def _seat_view(x: LunjianSeat, key: str) -> dict:
    return {"name": x.name, "me": bool(key) and x.key == key, "elder": not x.key}


def match_view(ctx, m: LunjianMatch, key: str) -> dict:
    side = rules.side_of(m, key) or "a"
    flip = side == "b"
    us, them = (m.seats_b, m.seats_a) if flip else (m.seats_a, m.seats_b)
    bouts = []
    for i, x in enumerate(m.bouts):
        bouts.append({
            "seat": rules.SEAT_NAMES[i] if i < len(rules.SEAT_NAMES) else "",
            "tier": rules.tier_for(m, side, i),
            "lines": list(x.lines),
        })
    won = "" if not m.winner else ("us" if m.winner == side else "them")
    sa, sb = score_of(m)
    return {
        "us": sect_name(ctx, m.b if flip else m.a), "them": sect_name(ctx, m.a if flip else m.b),
        "seats_us": [_seat_view(x, key) for x in us], "seats_them": [_seat_view(x, key) for x in them],
        "bouts": bouts, "won": won, "score": [sb, sa] if flip else [sa, sb],
    }


def status(ctx) -> dict:
    """畫面那一份：拜了門的人看得到這一週；手上還有沒用完的賞也畫。"""
    if not _on(ctx):
        return {}
    sect, b, key = _sect(ctx), bag(ctx), _key(ctx)
    loot = b is not None and (b.picks or b.boxes or b.top_boxes)
    if sect is None and not loot:
        return {}
    week = _week(ctx)
    w = week_of(ctx, week)
    mine = None
    if w is not None and w.drawn and sect is not None:
        m = next((x for x in w.matches if sect in (x.a, x.b)), None)
        if m is not None:
            mine = match_view(ctx, m if rules.side_of(m, key) or m.a == sect else _as_b(m), key)
    count = sum(1 for e in (w.entries.values() if w is not None else []) if e.sect == sect)
    phase = "fought" if w is not None and w.fought else "drawn" if w is not None and w.drawn else "sign"
    seal = b is not None and b.seal_season == _season(ctx) and _now(ctx) < b.seal_until
    return {"lunjian": {
        "title": TITLE,
        "week": week,
        "sect": sect_name(ctx, sect) if sect else "",
        "phase": phase,
        "signed": signed(ctx),
        "can_sign": can_sign(ctx),
        "count": count,
        "seats": int(_t(ctx).seats),
        "draw": ctx.stamp(draw_at(ctx, week)),
        "fight": ctx.stamp(fight_at(ctx, week)),
        "match": mine,
        "seal": SEAL if seal else "",
        "picks": b.picks if b else 0,
        "boxes": b.boxes if b else 0,
        "top_boxes": b.top_boxes if b else 0,
        "moves": b.moves if b else 0,
        "opened": list(b.opened) if b else [],
        "claim": [{"id": f"lunjian:claim:{mid}", "name": ctx.content.materials[mid].name} for mid in claim_mats(ctx.content)] if b and b.picks else [],
        "options": [o.model_dump() for o in options(ctx)],
    }}


def _as_b(m: LunjianMatch) -> LunjianMatch:
    """沒上台的同門看自己那一門：自己那一門是 b 時翻成 a 那一邊畫（只給畫面用的複本）。"""
    return LunjianMatch(a=m.b, b=m.a, seats_a=m.seats_b, seats_b=m.seats_a,
                        bouts=[x.model_copy(update={"tier": rules.FLIP[x.tier]}) for x in m.bouts],
                        winner={"a": "b", "b": "a"}.get(m.winner, ""))
