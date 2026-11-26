"""江湖錄的純規則：從存檔與江湖紀錄記下走過的每一幕、收過的結局、見過的人、拿過的東西、悟出的神品；重讀一幕時照內容檔重組全文。
不碰 ctx（同步、做完一件事、換季都叫 scan；畫面在 view.py）。"""
from __future__ import annotations

from tianxia import gender
from tianxia.mounts import COAT_ART, STEED_ART
from tianxia.state import CodexBook, CodexEnd, CodexScene, GameState
from tianxia.story_base import definition, vary

FREE = -1  # 隨口應對：lines 存全文
FREE_TAG = "隨口應對"  # Game.answer_event 的江湖紀錄標題是「事件・隨口應對」（core/event_check.py）
FAILED = "失敗"  # rules.check_result_line 的標記
MAX_SCENES = 600  # 跨季一直加：一位玩家最多記這麼多幕（最舊的先丟）


def on(content) -> bool:
    return content.config.codex.enabled


def book(state: GameState, make: bool = False) -> CodexBook | None:
    p = state.player
    if p.codex is None and make:
        p.codex = CodexBook()
    return p.codex


def _fresh(b: CodexBook, key: str, quiet: bool) -> None:
    if not quiet and key not in b.fresh:
        b.fresh.append(key)


# ── 走過的每一幕 ─────────────────────────────────────────

def stage_events(content, line) -> dict[str, tuple[str, str]]:
    """一條線每一段端出來的事件（連選項 effect.next_event 串下去的）：事件 id → (段 id, 事件 id)。"""
    out: dict[str, tuple[str, str]] = {}
    for st in line.stages:
        if st.kind != "event" or not st.event:
            continue
        todo = [st.event]
        while todo:
            eid = todo.pop()
            ev = content.events.get(eid)
            if ev is None or eid in out:
                continue
            out[eid] = (st.id, eid)
            todo += [n for c in ev.choices for n in (c.effect.next_event, c.fail_effect.next_event) if n]
    return out


def _match(state: GameState, content, title: str) -> tuple[str, str, str, int] | None:
    """江湖紀錄一則的標題是這個人哪一條線、哪一段的哪一則事件、選了第幾個（隨口應對是 FREE）；對不上是 None。"""
    for progress in state.player.storylines.values():
        line = definition(content, progress)
        if line is None or progress.custom is not None:  # 程式組的線（特殊頓悟）不在江湖錄：記了也畫不出來
            continue
        for eid, (stage, _) in stage_events(content, line).items():
            ev = content.events[eid]
            head = f"{ev.title}・"
            if not title.startswith(head):
                continue
            rest = title[len(head):]
            if rest == FREE_TAG:
                return line.id, stage, eid, FREE
            for i, ch in enumerate(ev.choices):
                if ch.text == rest:
                    return line.id, stage, eid, i
    return None


def _ok(content, eid: str, index: int, entry) -> bool:
    ch = content.events[eid].choices[index]
    if ch.check is not None:
        return entry.tag != FAILED
    if ch.combat and ch.fail_effect.text:  # 打一場：落敗那一段的字開頭出現在紀錄裡就是輸了
        head = ch.fail_effect.text.strip()[:12]
        return not any(head and head in ln for ln in entry.lines)
    return True


def scan_journal(state: GameState, content, quiet: bool = False) -> None:
    """江湖紀錄裡還沒讀過的那幾則（照時間從舊到新）：是某條線段落事件的選擇就記一幕。"""
    b = book(state, make=True)
    news = [e for e in reversed(state.journal)
            if e.time > b.upto or (e.time == b.upto and f"{e.time}|{e.title}" not in b.upto_keys)]
    for entry in news:
        hit = _match(state, content, entry.title)
        if entry.time > b.upto:  # 「open:季:線」（這條線新開過的紅點亮過了）不跟著讀到哪裡一起清：清了每多一則紀錄就又亮一次（11/13 紅點消不掉）
            b.upto, b.upto_keys = entry.time, [k for k in b.upto_keys if k.startswith("open:")]
        b.upto_keys.append(f"{entry.time}|{entry.title}")
        if hit is None:
            continue
        line, stage, eid, index = hit
        progress = state.player.storylines.get(line)
        scene = CodexScene(season=state.player.season_number, line=line, stage=stage, event=eid, choice=index,
                           marks=dict(progress.marks) if progress is not None else {}, time=entry.time)
        if index == FREE:
            scene.said = progress.said[-1] if progress is not None and progress.said else ""
            scene.lines = list(entry.lines)
        else:
            scene.ok = _ok(content, eid, index, entry)
        b.scenes.append(scene)
        _fresh(b, f"q:{line}", quiet)
    del b.scenes[:-MAX_SCENES]


def scan_lines(state: GameState, content, quiet: bool = False) -> None:
    """這一季開過的線：新開的（紅點）、收了的（記一個收法）。"""
    b = book(state, make=True)
    season = state.player.season_number
    for progress in state.player.storylines.values():
        if progress.custom is not None:  # 程式組的線（特殊頓悟）不在江湖錄
            continue
        if progress.ending is None:
            if not any(s.line == progress.line and s.season == season for s in b.scenes):
                key = f"open:{season}:{progress.line}"
                if key not in b.upto_keys and f"q:{progress.line}" not in b.fresh and not _opened(b, season, progress.line):
                    _fresh(b, f"q:{progress.line}", quiet)
                    b.upto_keys.append(key)
            continue
        if any(e.line == progress.line and e.season == season for e in b.ended):
            continue
        b.ended.append(CodexEnd(season=season, line=progress.line, ending=progress.ending,
                                time=progress.ended_at or state.world.time))
        _fresh(b, f"q:{progress.line}", quiet)
        line = definition(content, progress)
        if line is not None and line.kind == "奇事":  # 圖鑑的結局只收奇事（章回的收法不在那張表上，亮了也滅不掉）
            _fresh(b, f"e:{progress.line}:{progress.ending}", quiet)


def _opened(b: CodexBook, season: int, line: str) -> bool:
    return f"open:{season}:{line}" in b.upto_keys


# ── 見過的人、拿過的東西、悟出的神品 ──────────────────────

def seen_people(state: GameState, content) -> set[str]:
    p = state.player
    out = {cid for cid in p.affinities if cid in content.characters}
    out |= {cid for cid in p.figure_wins if cid in content.characters}
    for cid, hd in content.heroines.items():  # 女子：走過她那一條奇事就算見過
        if hd.line in p.storylines:
            out.add(cid)
    out |= {cid for cid in p.team if cid in content.characters}
    return out


def thing_keys(state: GameState, content) -> set[str]:
    p = state.player
    out: set[str] = set()
    items = [*p.rack, p.weapon, p.armor, p.mount, p.treasure]
    for it in items:
        if it is None:
            continue
        if it.slot == "treasure" and it.template in content.gear.treasures:
            out.add(f"寶:{it.template}")
        elif it.slot == "mount":
            if it.template in content.gear.steeds:
                out.add(f"騎:{it.template}")
            else:
                coat = next((k for k in COAT_ART if it.name.startswith(k)), None)
                if coat is not None:
                    out.add(f"毛:{coat}")
        if it.signature:
            out.add(f"兵:{it.signature}")
    out |= {f"材:{mid}" for mid, n in p.materials.items() if n > 0 and mid in content.materials}
    return out


def god_marks(state: GameState, content) -> dict[str, str]:
    """悟出來的神品意境：模板 id → 「名字|地點|季」（同一個模板悟過兩次，記第一次）。"""
    p = state.player
    gods = {t.id for t in content.traits.god}
    out: dict[str, str] = {}
    for iid, fx in p.insight_fx.items():
        grand = getattr(fx, "grand", None)
        own = p.own_insights.get(iid)
        if grand in gods and own is not None:
            out.setdefault(grand, f"{own.name}|{own.place}|{p.season_number}")
    return out


def scan_owned(state: GameState, content, quiet: bool = False) -> None:
    b = book(state, make=True)
    for cid in sorted(seen_people(state, content)):
        if cid not in b.people:
            b.people.append(cid)
            _fresh(b, f"p:{cid}", quiet)
    for key in sorted(thing_keys(state, content)):
        if key not in b.things:
            b.things.append(key)
            _fresh(b, f"t:{key}", quiet)
    for tid, mark in god_marks(state, content).items():
        if tid not in b.gods:
            b.gods[tid] = mark
            _fresh(b, f"g:{tid}", quiet)


def drawable(state: GameState, content) -> set[str]:
    """紅點畫得出來的鍵（每一個都要有一格點得到；畫不出來的不准亮）：這一季開過、不是程式組的線（q:），圖鑑四類有的格。"""
    b = state.player.codex
    out = {f"q:{pr.line}" for pr in state.player.storylines.values() if pr.custom is None and definition(content, pr) is not None}
    out |= {f"p:{cid}" for cid in b.people if cid in content.characters}
    out |= {f"t:{k}" for k in b.things}
    gods = {t.id for t in content.traits.god}
    out |= {f"g:{tid}" for tid in b.gods if tid in gods}
    qiyu = {lid for lid, line in content.storylines.items() if line.kind == "奇事" and line.start is not None}
    out |= {f"e:{e.line}:{e.ending}" for e in b.ended if e.line in qiyu}
    return out


def scan(state: GameState, content) -> None:
    """同步、做完一件事、換季前都叫：讀新的江湖紀錄、線的進度、身上的東西。第一次（剛打開開關）照存檔補，不亮紅點。
    最後把畫不出來的紅點拿掉（上一季的線、程式組的線、不在表上的東西）：亮著卻沒有一格點得到，就永遠滅不掉。"""
    quiet = state.player.codex is None
    scan_journal(state, content, quiet)
    scan_lines(state, content, quiet)
    scan_owned(state, content, quiet)
    b = state.player.codex
    ok = drawable(state, content)
    b.fresh = [k for k in b.fresh if k in ok]


def carry(old: GameState | None, new: GameState, content) -> None:
    """換季：上一季最後那一下也讀進去，整本照帶；江湖紀錄與世界秒換季重來，讀到哪裡重數。"""
    if old is not None and old.player.codex is not None:
        scan(old, content)
        new.player.codex = old.player.codex.model_copy(deep=True)
    b = new.player.codex
    if b is not None:
        b.upto, b.upto_keys = -1, [k for k in b.upto_keys if k.startswith("open:")]


# ── 重讀 ─────────────────────────────────────────────────

def fill(text: str, state: GameState, line: str, marks: dict[str, int]) -> str:
    text = gender.address(text, state)
    if "{?" in text or "{!" in text or "{said:" in text:
        text = vary(text, state, {line: marks})
    return text.replace("{name}", state.player.name)


def paras(text: str) -> list[str]:
    return [t.strip() for t in text.split("\n\n") if t.strip()]


def scene_text(state: GameState, content, scene: CodexScene) -> dict:
    """一幕的全文：前情（事件本文）、你選的那一句、後來（選項的結果）、沒選的那幾句。"""
    ev = content.events.get(scene.event)
    if ev is None:
        return {"title": "", "before": [], "pick": scene.said, "after": list(scene.lines), "others": []}
    f = lambda t: fill(t, state, scene.line, scene.marks)  # noqa: E731
    if scene.choice == FREE:
        return {"title": ev.title, "before": paras(f(ev.text)), "pick": scene.said, "after": [ln for ln in scene.lines if ln.strip()],
                "others": [c.text for c in ev.choices]}
    ch = ev.choices[scene.choice] if 0 <= scene.choice < len(ev.choices) else None
    if ch is None:
        return {"title": ev.title, "before": paras(f(ev.text)), "pick": "", "after": [], "others": []}
    eff = ch.effect if scene.ok else ch.fail_effect
    return {"title": ev.title, "before": paras(f(ev.text)), "pick": f(ch.text), "after": paras(f(eff.text or "")),
            "others": [f(c.text) for i, c in enumerate(ev.choices) if i != scene.choice]}
