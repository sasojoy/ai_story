"""江湖錄的畫面資料（GET /api/codex、/api/codex/scene；狀態列的 codex 那一格只帶紅點）。給玩家看的字標「待 joy 潤」，不露數字以外的規則。"""
from __future__ import annotations

import math
from pathlib import Path

from tianxia.figures import placed_characters
from tianxia.mounts import COAT_ART, STEED_ART
from tianxia.rules import day_seconds
from tianxia.story_base import current, definition, waiting

from . import rules

WEB = Path(__file__).resolve().parents[3] / "web"

KIND_MAIN = "主線"  # 待 joy 潤：章回
KIND_QIYU = "奇事"  # 待 joy 潤
NOW = "到了就能開始"  # 待 joy 潤：這一段此刻做得了（人到了那裡）
WAIT = "{left}以後"  # 待 joy 潤：多日段還要等
LEFT = "還有 {n} 天"  # 待 joy 潤：期限
LEFT_TODAY = "今天就過期"  # 待 joy 潤
DOING = "去做那件事"  # 待 joy 潤：task 段沒寫 hint
FIGHT = "打一場"  # 待 joy 潤
UNSEEN = "？？"
STAY = "到{place}，在「此地」裡找{pron}說話。"  # 待 joy 潤：走完留下來的人
GONE = "{pron}不在了。"  # 待 joy 潤：收在留不住她的結局
UNFINISHED = "此事未了"  # 待 joy 潤
FORMS = ("攻", "守", "變", "心")
PATHS = ("快", "慢", "剛", "柔", "陽", "陰", "虛", "實", "正", "邪")
ATTR_TONE = {"快": "kuai", "慢": "man", "剛": "gang", "柔": "rou", "陽": "gang", "陰": "kuai", "虛": "rou", "實": "man", "正": "kuai", "邪": "gang"}


def _img(rel: str | None) -> str | None:
    if not rel:
        return None
    return f"/static/img/{rel}.webp" if (WEB / "img" / f"{rel}.webp").is_file() else None


def _face(cid: str) -> str | None:
    return f"/static/img/figures/full/{cid}.webp" if (WEB / "img" / "figures" / "full" / f"{cid}.webp").is_file() else None


def _loc_name(content, loc: str | None) -> str:
    return content.locations[loc].name if loc and loc in content.locations else ""


def _where(content, place) -> tuple[str, str | None]:
    """一段在哪裡做得了：寫給人看的地名、輿圖上看哪一處（沒有固定的一處是 None）。"""
    if place.locations:
        return "、".join(_loc_name(content, x) for x in place.locations[:2]), place.locations[0]
    if place.regions:
        regs = {r.id: r.name for r in content.map.regions}
        return "、".join(regs.get(r, r) for r in place.regions[:2]), None
    return "", None


def _heroine_of(content, line_id: str) -> str | None:
    return next((cid for cid, hd in content.heroines.items() if hd.line == line_id), None)


def _days(seconds: float, day: float) -> int:
    return max(0, math.ceil(seconds / day))


def _next(ctx, progress) -> dict | None:
    s, c = ctx.state, ctx.content
    pair = current(c, progress)
    if pair is None:
        return None
    _, stage = pair
    where, loc = _where(c, stage.where)
    day = day_seconds(c, s.world)
    what = stage.hint or where or (FIGHT if stage.kind == "fight" else DOING)
    when = NOW
    if waiting(s, c, progress, stage):
        wait_left = progress.entered + stage.wait_days * day - s.world.time
        when = WAIT.format(left=f"{_days(wait_left, day)} 天" if wait_left >= day else "幾個時辰")
    left = ""
    if progress.due is not None:
        n = _days(progress.due - s.world.time, day)
        left = LEFT.format(n=n) if n > 0 else LEFT_TODAY
    return {"what": what, "where": where, "loc": loc, "when": when, "left": left, "hint": bool(stage.hint), "ready": when == NOW}


def _scene_rows(ctx, b, season: int, line_id: str) -> list[dict]:
    c = ctx.content
    rows = []
    for i, sc in enumerate(b.scenes):
        if sc.season != season or sc.line != line_id:
            continue
        ev = c.events.get(sc.event)
        pick = sc.said if sc.choice == rules.FREE else (ev.choices[sc.choice].text if ev and 0 <= sc.choice < len(ev.choices) else "")
        rows.append({"i": i, "title": ev.title if ev else "", "pick": rules.fill(pick, ctx.state, sc.line, sc.marks),
                     "stamp": ctx.stamp(sc.time, clock=False) if season == ctx.state.player.season_number else f"第 {season} 季"})
    return rows


def _ends(c, line, got: set[str]) -> list[dict]:
    return [{"id": e.id, "title": e.title if e.id in got else UNSEEN, "src": _img(e.image) if e.id in got else None, "got": e.id in got,
             "failed": e.failed} for e in line.endings]


def _stay(ctx, line_id: str, ending: str) -> dict | None:
    c = ctx.content
    cid = _heroine_of(c, line_id)
    if cid is None or cid not in c.characters:
        return None
    ch, hd = c.characters[cid], c.heroines[cid]
    pron = "她"
    if ending not in hd.endings:
        return {"id": cid, "name": ch.name, "face": _face(cid), "text": GONE.format(pron=pron), "loc": None, "place": ""}
    loc = placed_characters(ctx.state, c).get(cid) or hd.stay.get(ending) or ch.talk_at
    place = _loc_name(c, loc)
    return {"id": cid, "name": ch.name, "face": _face(cid), "text": STAY.format(place=place, pron=pron), "loc": loc, "place": place,
            "said": hd.endings.get(ending, "")}


FALLBACK_ART = {True: "events/camp", False: "events/tale"}  # 線沒有圖：主線用軍營、奇事用說書（之後補專屬圖）


def _stage_image(line, progress) -> str | None:
    """線沒寫圖時借這一段（或第一段）的圖。"""
    stage = line.stage(progress.stage) if progress is not None and progress.stage else None
    return (stage.image if stage is not None else None) or next((st.image for st in line.stages if st.image), None)


def _quest(ctx, b, season: int, line, progress=None, end=None) -> dict:
    c = ctx.content
    ending_id = progress.ending if progress is not None else (end.ending if end is not None else None)
    got = {e.ending for e in b.ended if e.line == line.id}
    ending = line.ending(ending_id) if ending_id else None
    cid = _heroine_of(c, line.id)
    q = {
        "key": f"{season}:{line.id}", "line": line.id, "season": season, "title": line.title,
        "kind": KIND_MAIN if line.kind == "章回" else KIND_QIYU, "intro": line.intro,
        "who": c.characters[cid].name if cid and cid in c.characters else "",
        "src": _img(line.image) or _img(_stage_image(line, progress)) or _img(FALLBACK_ART[line.kind == "章回"]), "stages": len(line.stages),
        "scenes": _scene_rows(ctx, b, season, line.id), "ends": _ends(c, line, got),
        "dot": f"q:{line.id}" in b.fresh and season == ctx.state.player.season_number,
    }
    if ending_id is None and progress is not None:
        q["state"], q["next"] = "on", _next(ctx, progress)
    else:
        q["state"] = "done"
        q["ending"] = {"id": ending_id or "", "title": ending.title if ending else UNFINISHED, "src": _img(ending.image) if ending else None,
                       "failed": bool(ending and ending.failed)}
        if ending is not None:
            q["src"] = q["ending"]["src"] or q["src"]
        stay = _stay(ctx, line.id, ending_id or "") if season == ctx.state.player.season_number else None
        if stay is not None:
            q["stay"] = stay
    return q


def _ghost(c, line) -> dict:
    where = ""
    if line.start is not None:
        where = _where(c, line.start.where)[0]
    return {"key": f"ghost:{line.id}", "line": line.id, "state": "ghost", "title": UNSEEN, "where": where,
            "kind": KIND_MAIN if line.kind == "章回" else KIND_QIYU}


def quests(ctx) -> dict:
    s, c = ctx.state, ctx.content
    b = rules.book(s, make=True)
    season = s.player.season_number
    on, done = [], []
    for progress in s.player.storylines.values():
        line = definition(c, progress)
        if line is None or progress.custom is not None:
            continue
        (on if progress.ending is None else done).append(_quest(ctx, b, season, line, progress=progress))
    past = []
    for end in sorted(b.ended, key=lambda e: (-e.season, -e.time)):
        line = c.storylines.get(end.line)
        if line is None or end.season == season:
            continue
        past.append(_quest(ctx, b, end.season, line, end=end))
    met = {pr.line for pr in s.player.storylines.values()} | {e.line for e in b.ended} | {sc.line for sc in b.scenes}
    ghosts = [_ghost(c, line) for line in c.storylines.values()
              if line.kind == "奇事" and line.start is not None and line.id not in met]
    return {"on": on, "done": done, "past": past, "ghosts": ghosts}


def scene(ctx, index: int) -> dict | None:
    b = rules.book(ctx.state)
    if b is None or not 0 <= index < len(b.scenes):
        return None
    sc = b.scenes[index]
    out = rules.scene_text(ctx.state, ctx.content, sc)
    line = ctx.content.storylines.get(sc.line)
    out.update({"line": sc.line, "story": line.title if line else "",
                "stamp": ctx.stamp(sc.time, clock=False) if sc.season == ctx.state.player.season_number else f"第 {sc.season} 季"})
    return out


def ending_text(ctx, line_id: str, ending_id: str) -> dict | None:
    b = rules.book(ctx.state)
    line = ctx.content.storylines.get(line_id)
    if b is None or line is None or not any(e.line == line_id and e.ending == ending_id for e in b.ended):
        return None
    e = line.ending(ending_id)
    if e is None:
        return None
    return {"title": e.title, "story": line.title, "src": _img(e.image),
            "after": rules.paras(rules.fill(e.text, ctx.state, line_id, {}))}


# ── 圖鑑 ─────────────────────────────────────────────────

def people(ctx) -> dict:
    c = ctx.content
    b = rules.book(ctx.state, make=True)
    placed = placed_characters(ctx.state, c)
    rows = []
    for cid, ch in c.characters.items():
        got = cid in b.people
        if not got and _face(cid) is None:  # 圖鑑只收有立繪的人（大勢人物、女子、名士）；沒立繪的見過了才列
            continue
        loc = (placed.get(cid) or ch.talk_at) if got else ch.talk_at  # 沒見過的寫他平常在的地方（剪影＋地名）
        rows.append({"id": cid, "name": ch.name if got else UNSEEN, "face": _face(cid) if got else None, "got": got,
                     "place": _loc_name(c, loc) if loc else "", "dot": f"p:{cid}" in b.fresh,
                     "about": (ch.situation or "").split("。")[0] if got else ""})
    rows.sort(key=lambda r: not r["got"])
    return {"rows": rows, "got": sum(r["got"] for r in rows), "all": len(rows)}


def things(ctx) -> dict:
    c = ctx.content
    b = rules.book(ctx.state, make=True)
    have = set(b.things)

    def cell(key: str, name: str, src: str | None, sub: str = "") -> dict:
        got = key in have
        return {"key": key, "name": name if got else UNSEEN, "src": src if got else None, "got": got, "sub": sub if got else "",
                "dot": f"t:{key}" in b.fresh}

    def web(path: str) -> str | None:
        return f"/static/{path}" if (WEB / path).is_file() else None

    treasure = [cell(f"寶:{tid}", t.name, web(f"img/gear/treasure-{tid}.webp")) for tid, t in c.gear.treasures.items()]
    horse = [cell(f"騎:{sid}", st.name, web(f"horse-{STEED_ART.get(sid, '')}.webp"), "名駒") for sid, st in c.gear.steeds.items()]
    horse += [cell(f"毛:{coat}", f"{coat}馬", web(f"horse-{art}.webp")) for coat, art in COAT_ART.items()]
    arms = [cell(f"兵:{a.character}", a.name, None, f"{c.characters[a.character].name if a.character in c.characters else ''}・{a.kind}")
            for a in c.gear.signature_arms]
    mats = [cell(f"材:{mid}", m.name, web(f"img/gear/mat-{mid}.webp"), m.attribute) for mid, m in c.materials.items()]
    groups = [("treasure", "寶物", treasure), ("horse", "坐騎", horse), ("arms", "名兵", arms), ("mat", "素材", mats)]  # 待 joy 潤
    return {"groups": [{"id": g, "name": n, "cells": cells, "got": sum(x["got"] for x in cells), "all": len(cells)} for g, n, cells in groups]}


def gods(ctx) -> dict:
    c = ctx.content
    b = rules.book(ctx.state, make=True)
    cells = {}
    for t in c.traits.god:
        mark = b.gods.get(t.id)
        name, place, season = (mark.split("|") + ["", "", ""])[:3] if mark else ("", "", "")
        path = t.lean if t.lean in ("正", "邪") else t.attribute  # 正、邪兩路的屬性是陽、陰，照正邪那一行排
        cells[f"{path}{t.form}"] = {"id": t.id, "got": bool(mark), "name": name, "place": place,
                                          "season": int(season) if season.isdigit() else 0, "tone": ATTR_TONE.get(path, "kuai"),
                                          "dot": f"g:{t.id}" in b.fresh}
    paths = [p for p in PATHS if any(f"{p}{f}" in cells for f in FORMS)]
    return {"paths": paths, "forms": list(FORMS), "cells": cells, "got": len(b.gods), "all": len(c.traits.god)}


def endings(ctx) -> dict:
    c = ctx.content
    b = rules.book(ctx.state, make=True)
    rows = []
    for line in c.storylines.values():
        if line.kind != "奇事" or line.start is None:
            continue
        got = {e.ending for e in b.ended if e.line == line.id}
        met = bool(got) or any(sc.line == line.id for sc in b.scenes) or line.id in ctx.state.player.storylines
        rows.append({"line": line.id, "title": line.title if met else UNSEEN, "ends": _ends(c, line, got), "met": met,
                     "dot": any(f"e:{line.id}:{e}" in b.fresh for e in got)})
    rows.sort(key=lambda r: not r["met"])
    return {"rows": rows, "got": sum(sum(e["got"] for e in r["ends"]) for r in rows), "all": sum(len(r["ends"]) for r in rows)}


def page(ctx) -> dict:
    return {"quests": quests(ctx), "people": people(ctx), "things": things(ctx), "gods": gods(ctx), "endings": endings(ctx)}


def status(ctx) -> dict:
    """狀態列那一格：只帶紅點（哪幾段有新的），整本另外拿（GET /api/codex）。"""
    b = rules.book(ctx.state)
    fresh = list(b.fresh) if b is not None else []
    return {"fresh": fresh, "q": any(k.startswith("q:") for k in fresh),
            "p": any(k.startswith("p:") for k in fresh), "t": any(k.startswith("t:") for k in fresh),
            "g": any(k.startswith("g:") for k in fresh), "e": any(k.startswith("e:") for k in fresh)}


def seen(ctx, keys: list[str]) -> list[str]:
    """看過了：紅點滅。keys 是 fresh 裡的鍵，或一整類（「p:*」）。"""
    b = rules.book(ctx.state)
    if b is None:
        return []
    for k in keys:
        if k.endswith("*"):
            b.fresh = [f for f in b.fresh if not f.startswith(k[:-1])]
        elif k in b.fresh:
            b.fresh.remove(k)
    return []
