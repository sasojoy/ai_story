"""章回主線（企劃者 2026-10-29 選丙「每個陣營一條章回主線」，同日「四個都同意」；設計稿 /mnt/project-files/plan/章回主線/）。

這一季時刻表上的大事就是章回：每一件大事之前，你那一方派你做一回事。一回是一條線（storyline，kind「章回」、StoryDef.chapter），
內容寫在 content/storylines.json 與 content/events/chapter_*.json（產生器 scripts/story/gen_chapters.py）。

- 開：投靠了那一方、前面那幾回（ChapterSpec.after）做完或收了、要等的大事（after_beat）結算了、自己這一回的大事（beat）還沒結算，
  同步時就開（tick）。中途投靠的人從那一方此刻的那一回開始：大事已經結算的那幾回不開。
- 做成：走進最後一段 wait（task「chapter_beat」）那一刻（after）。記一筆貢獻（chapter_contribution）、
  替推的那一方加份量（WorldState.chapter_weights，帶著 sway_marks 的記號另加）、做成的人數 +1（chapter_done，章回卡寫）。
- 收：beat 結算了，wait 那一段的 task 成立，照結果記一個記號（「果成」「果不成」「果guan」「果huang」）往結局走；
  還沒做成的收成 missed（不能補做：歷史已經發生了，企劃者 10-29 同意）。換了陣營，手上那一回作罷（不寫傳）。
- 改歷史：擲骰的大事（timetable.roll_chance）照兩方的份量加一個修正，最多 chapter_roll_cap（±0.15），跟伏筆、軍令合計仍夾 ±0.20；
  決戰（world._claim_showdown）照份量挪開打的起點，最多 chapter_edge_cap 點。份量照開根號：20 人跟 200 人的服都推得動。

規則掛在 Config.jianfa.chapters（rules.jianfa），也要 storylines 開著。只讀時鐘 state.world.time。
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from . import calendar, deeds, storyline, wins
from .rules import jianfa

if TYPE_CHECKING:
    from .models import Content, StoryDef, TimetableEvent
    from .state import GameState, StoryProgress, WorldState
    from .world_state import WorldStateStore

KIND = "章回"
WAIT = "wait"  # 每一回最後一段的 id：走進來就是做成了，等大事結算
TASK = "chapter_beat"
MISSED = "missed"  # 大事結算了還沒做成的那個結局 id
LEFT = "作罷"  # 換了陣營：手上那一回收成這個（不寫傳、不跳卡）
DONE = "做成"  # 做成那一刻記的記號（只記一次）
DONE_LINE = "✦ 第{no}回「{title}」做成了：替{side}記了一功。{beat}結算時見分曉。"
DEED = "{name}在{where}做成了第{no}回「{title}」。"  # 世界記事的那一句
NUMERALS = "一二三四五六七八九十"


def on(content: Content, world: WorldState | None) -> bool:
    return jianfa(content, world, "chapters") and jianfa(content, world, "storylines")


def numeral(no: int) -> str:
    return NUMERALS[no - 1] if 1 <= no <= len(NUMERALS) else str(no)


def lines(content: Content, side: str | None = None) -> list[StoryDef]:
    """內容裡的章回（照 side 篩），照第幾回排。"""
    out = [d for d in content.storylines.values() if d.chapter is not None and (side is None or d.chapter.side == side)]
    return sorted(out, key=lambda d: (d.chapter.side, d.chapter.no))


def _resolved(world: WorldState, event_id: str | None) -> bool:
    return event_id is not None and event_id in world.timeline


def outcome_mark(key: str) -> str:
    """結算的結果鍵換成記號：擲骰的「成」「不成」→「果成」「果不成」；決戰「guan:大勝」→「果guan」；有版本的（「甲:成」）去掉版本。"""
    parts = key.split(":")
    if parts[0] in ("guan", "huang"):
        return f"果{parts[0]}"
    if len(parts) >= 2 and parts[1] in ("guan", "huang"):
        return f"果{parts[1]}"
    return f"果{parts[-1]}"


def _settled(progress: StoryProgress, ending: str | None) -> bool:
    return ending is not None or progress.marks.get(DONE, 0) > 0


def _ready(state: GameState, content: Content, line: StoryDef) -> bool:
    spec, p, w = line.chapter, state.player, state.world
    if line.id in p.storylines or _resolved(w, spec.beat):
        return False
    if spec.after_beat is not None and not _resolved(w, spec.after_beat):
        return False
    for before in spec.after:
        pr = p.storylines.get(before)
        if pr is None:
            # 前一回沒開過：只有它的大事已經結算了（中途投靠、錯過了開的時候）才不擋
            prev = content.storylines.get(before)
            if prev is None or prev.chapter is None or not _resolved(w, prev.chapter.beat):
                return False
        elif not _settled(pr, pr.ending):
            return False
    return True


def tick(state: GameState, content: Content, world: WorldStateStore | None) -> list[str]:
    """同步與每個動作之前（Game._story_tick）：換了陣營的作罷、大事結算了還沒做成的收成 missed、該開的開。回江湖紀錄要寫的話。"""
    if not on(content, state.world):
        return []
    p, w = state.player, state.world
    msgs: list[str] = []
    for progress in storyline.active(state):
        line = storyline.definition(content, progress)
        if line is None or line.chapter is None:
            continue
        if line.chapter.side != p.faction:
            progress.ending, progress.stage, progress.go, progress.due = LEFT, "", None, None
            progress.ended_at = w.time
            continue
        result = w.timeline.get(line.chapter.beat)
        if result is not None and progress.stage != WAIT and line.ending(MISSED) is not None:
            progress.marks[outcome_mark(result.key)] = 1
            msgs += storyline.finish(state, content, world, progress, line, line.ending(MISSED))
    if p.faction is None or w.ended:  # 休季了：錯過的照樣收成 missed（不寫此事未了），不再開新的
        return msgs
    for line in lines(content, p.faction):
        if _ready(state, content, line):  # 開的那一下不另寫一行、不跳卡：江湖頁最上面的章回卡換成這一回
            storyline.start(state, content, line, custom=False, card=False)
    return msgs


def weight(line: StoryDef, progress: StoryProgress) -> float:
    """這一個人做成這一回的份量：1 加上帶著的記號各自另加的（ChapterSpec.sway_marks），最低 0。"""
    extra = sum(v for k, v in line.chapter.sway_marks.items() if progress.marks.get(k, 0) > 0)
    return max(0.0, 1.0 + extra)


def sway_side(state: GameState, content: Content, line: StoryDef) -> str | None:
    """做成這一回推哪一軍：帶著 side_marks 的記號照那一軍（豪強賣給誰）；再來照內容寫的 sway；豪強照此刻幫的那一軍；都沒有是 None（不推）。"""
    progress = state.player.storylines.get(line.id)
    if progress is not None:
        for mark, side in line.chapter.side_marks.items():
            if progress.marks.get(mark, 0) > 0:
                return side
    return line.chapter.sway or wins.lean_of(state.player, content)


def after(state: GameState, content: Content) -> list[str]:
    """storyline.tick 之後：剛走進 wait 的那一回記成做成（只一次）。回江湖紀錄要寫的話；世界的帳改了的話呼叫端要存共用的季。"""
    if not on(content, state.world):
        return []
    p, w = state.player, state.world
    msgs: list[str] = []
    for progress in storyline.active(state):
        line = storyline.definition(content, progress)
        if line is None or line.chapter is None or progress.stage != WAIT or progress.marks.get(DONE, 0) > 0:
            continue
        progress.marks[DONE] = 1
        spec = line.chapter
        side = sway_side(state, content, line)
        if side is not None:
            book = w.chapter_weights.setdefault(spec.beat, {})
            book[side] = book.get(side, 0.0) + weight(line, progress)
        w.chapter_done[line.id] = w.chapter_done.get(line.id, 0) + 1
        points = content.config.jianfa.chapter_contribution
        wins.credit(p, content, w, calendar.point(w.time, content, w).week, points, side=side)
        beat = _beat_title(content, spec.beat)
        place = _last_place(line)  # 世界記事（「世界活起來」讀）：誰、在哪、替哪一方做成了哪一回
        where = content.locations[place].name if place in content.locations else ""
        deeds.record(state, content, "chapter", DEED.format(name=p.name, where=where, no=numeral(spec.no), title=line.title),
                     place=place, actors=[p.name], side=side or p.faction)
        msgs.append(DONE_LINE.format(no=numeral(spec.no), title=line.title, side=_side_name(content, side or p.faction or ""), beat=beat))
    return msgs


def _last_place(line: StoryDef) -> str | None:
    """這一回最後一幕做在哪（wait 前面那一段的第一個地點）；都沒寫地點是 None。"""
    for stage in reversed(line.stages):
        if stage.id != WAIT and stage.where.locations:
            return stage.where.locations[0]
    return None


def _beat_task(state: GameState, content: Content, world: WorldStateStore, progress: StoryProgress, stage) -> bool:
    """wait 那一段：這一回的大事結算了就成立，順手記下結果的記號（結局照它分）。"""
    line = storyline.definition(content, progress)
    if line is None or line.chapter is None:
        return False
    result = state.world.timeline.get(line.chapter.beat)
    if result is None:
        return False
    progress.marks[outcome_mark(result.key)] = 1
    return True


storyline.TASKS[TASK] = _beat_task


# ── 改歷史 ────────────────────────────────────────────────

def share(content: Content, amount: float) -> float:
    """份量換成推到上限的幾成：√n ÷（√n＋√half_at），0 是 0、half_at 是一半，越多越慢。"""
    if amount <= 0:
        return 0.0
    root = math.sqrt(amount)
    return root / (root + math.sqrt(content.config.jianfa.chapter_half_at))


def roll_mod(world: WorldState, content: Content, event: TimetableEvent) -> float:
    """擲骰的大事：章回替 roll_side 那一方加的修正（另一方做成的扣回去），在 ±chapter_roll_cap 之內。沒有份量是 0。"""
    book = world.chapter_weights.get(event.id)
    if not book or event.roll_side is None:
        return 0.0
    other = "huang" if event.roll_side == "guan" else "guan"
    cap = content.config.jianfa.chapter_roll_cap
    return cap * (share(content, book.get(event.roll_side, 0.0)) - share(content, book.get(other, 0.0)))


def showdown_edge(world: WorldState, content: Content, event_id: str) -> int:
    """決戰：開打的起點往官軍挪幾點（負的是往黃巾），在 ±chapter_edge_cap 之內。起點以官軍為正向（battle_instance.start_from_front）。"""
    book = world.chapter_weights.get(event_id)
    if not book:
        return 0
    cap = content.config.jianfa.chapter_edge_cap
    return round(cap * (share(content, book.get("guan", 0.0)) - share(content, book.get("huang", 0.0))))


# ── 畫面 ──────────────────────────────────────────────────

SWAY_ROLL = "{side}已有 {n} 人做完這一回：{beat}往{lean}倒 {pct}%"
SWAY_EDGE = "{side}已有 {n} 人做完這一回：{beat}開打時{lean}佔先 {pts}"
SWAY_NONE = "{side}已有 {n} 人做完這一回"  # 還推不動、或兩邊打平
WAITING = "這一回你做完了，等{beat}結算"
ON_SCENE = "眼前這一幕：{title}"  # 那一段的事件端出來了（還沒按完）


def _side_name(content: Content, side: str) -> str:
    from .rules import STANCE_NAMES  # noqa: PLC0415

    if side in STANCE_NAMES:
        return STANCE_NAMES[side]
    f = next((f for f in content.scenario.factions if f.id == side), None)
    return f.name if f is not None else side


def _event(content: Content, event_id: str) -> TimetableEvent | None:
    from . import timetable  # noqa: PLC0415  timetable 在函式裡 import 章回（roll_chance）

    return timetable.find(content, event_id)


def _beat_title(content: Content, event_id: str) -> str:
    event = _event(content, event_id)
    return event.title if event is not None else event_id


def sway_line(state: GameState, content: Content, line: StoryDef) -> str:
    """章回卡那一行：這一方做完的人數與此刻替那一件大事推了多少（看的人這一方的角度）。"""
    w, spec = state.world, line.chapter
    side = sway_side(state, content, line) or spec.side
    n = w.chapter_done.get(line.id, 0)
    name = _side_name(content, spec.side)
    event = _event(content, spec.beat)
    if event is None or n == 0:
        return SWAY_NONE.format(side=name, n=n)
    if event.kind == "showdown":
        pts = showdown_edge(w, content, event.id)
        mine = pts if side == "guan" else -pts
        if mine <= 0:
            return SWAY_NONE.format(side=name, n=n)
        return SWAY_EDGE.format(side=name, n=n, beat=event.title, lean=_side_name(content, side), pts=mine)
    mod = roll_mod(w, content, event)
    mine = mod if side == event.roll_side else -mod
    pct = round(mine * 100)
    if pct <= 0:
        return SWAY_NONE.format(side=name, n=n)
    return SWAY_ROLL.format(side=name, n=n, beat=event.title, lean=_side_name(content, side), pct=pct)


def current(state: GameState, content: Content) -> tuple[StoryDef, StoryProgress] | None:
    """江湖頁最上面那一回：手上還沒收的章回裡，大事最早結算的那一回（還沒做成的先）。沒有是 None。"""
    if not on(content, state.world):
        return None
    from . import timetable  # noqa: PLC0415

    best = None
    for progress in storyline.active(state):
        line = storyline.definition(content, progress)
        if line is None or line.chapter is None:
            continue
        event = timetable.find(content, line.chapter.beat)
        at = timetable.when_in(state.world, content, event) if event is not None else math.inf
        key = (progress.stage == WAIT, at, line.chapter.no)
        if best is None or key < best[0]:
            best = (key, line, progress)
    return None if best is None else (best[1], best[2])


def card(state: GameState, content: Content, stamp, place, live=None) -> dict | None:
    """章回卡（main.week_card.chapter）：{line, no, title, side, hint, waiting, scene, here, beat, at, live, sway, target}。
    stamp 是 Game.stamp（世界秒 → 玩家看得到的時刻），place 是 step.place 那種（地點 id → {location, name, minutes}）。
    live 是（大事 id → 那一場決戰此刻 "muster"／"active"，沒在打是 None）：那一件大事的決戰已經在集結、開打了（管理者提早開），
    卡上不再寫排定的時刻，網頁照 live 寫「集結中」「開打了」（手機介面自檢 U-17）；不給一律 None。"""
    found = current(state, content)
    if found is None:
        return None
    from . import timetable  # noqa: PLC0415

    line, progress = found
    spec = line.chapter
    event = timetable.find(content, spec.beat)
    pair = storyline.current(content, progress)
    stage = None if pair is None else pair[1]
    waiting = progress.stage == WAIT
    scene = not waiting and stage is not None and progress.opened and stage.event in content.events
    if waiting:
        hint = WAITING.format(beat=event.title if event else spec.beat)
    elif scene:
        hint = ON_SCENE.format(title=content.events[stage.event].title)
    else:
        hint = stage.hint if stage is not None else ""
    target = None  # 人已經站在那一段的地方（或那一幕正端在眼前）不給：不用再去輿圖
    if stage is not None and not waiting and not scene and stage.where.locations and not storyline.here(state, content, stage.where):
        target = place(stage.where.locations[0])
    at = timetable.when_in(state.world, content, event) if event is not None else None
    return {
        "line": line.id, "no": numeral(spec.no), "title": line.title, "side": spec.side, "hint": hint, "waiting": waiting, "scene": scene,
        "here": storyline.doable(state, content, progress), "beat": event.title if event else "",
        "at": stamp(at) if at is not None and math.isfinite(at) else "", "live": live(spec.beat) if live is not None else None,
        "sway": sway_line(state, content, line), "target": target,
    }
