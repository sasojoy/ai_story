"""入伍段（新手引導重做設計第四節）：第一次投靠時由那一邊的引薦人帶兩步——看戰局（看過軍令卡）、第一道軍令。
不佔 tutorial_step：記在 PlayerState.enlist_step（None＝還沒開始）。只在第一季開始（beta 季沒有軍令）。"""
from __future__ import annotations

from .models import Content, Recruiter
from .rules import season_one
from .state import GameState
from .world_state import WorldStateStore


def _steps(content: Content):
    e = content.tutorial.enlist
    return e.steps if e is not None else []


def recruiter(state: GameState, content: Content) -> Recruiter | None:
    e, faction = content.tutorial.enlist, state.player.faction
    return e.recruiters.get(faction) if e is not None and faction is not None else None


def active(state: GameState, content: Content) -> bool:
    step = state.player.enlist_step
    return step is not None and step < len(_steps(content))


def done(state: GameState, content: Content) -> bool:
    step = state.player.enlist_step
    return step is not None and step >= len(_steps(content)) > 0


def begin_if_joined(state: GameState, content: Content) -> bool:
    """剛投靠（有陣營、入伍段還沒開始、這一季是第一季、沒有略過引導、這一邊有引薦人）：開始入伍段。回傳有沒有開始。
    「剛」是呼叫端的事：Game.choose／answer_event 只在這一下動作之前還沒有陣營時才叫它——已經投靠的舊存檔、叛投都不會被拉進來
    （設計 7.2；preflight F1）。"""
    p = state.player
    if p.enlist_step is not None or p.guide_skipped or not season_one(content, state.world):
        return False
    if recruiter(state, content) is None:
        return False
    p.enlist_step = 0
    return True


def skip(state: GameState, content: Content) -> None:
    """略過新手引導（設計 7.3）：入伍段也算走完，不畫框、之後投靠也不開始。"""
    state.player.enlist_step = len(_steps(content))
    state.player.enlist_end = False


def note(state: GameState, content: Content, world: WorldStateStore, action: str) -> list[str]:
    """跟 guide.note_action 同一個做法：符合這一步就往下一步，一路到不符合為止；走完設 enlist_end（框上換結尾）。"""
    from .guide import goal_met  # guide 也 import 這裡：放在函式裡避免循環

    msgs: list[str] = []
    todo = _steps(content)
    while active(state, content) and goal_met(state, content, world, todo[state.player.enlist_step].done_when, action):
        state.player.enlist_step += 1
        msgs.append("✔ 引導完成")
    if msgs and done(state, content):
        state.player.enlist_end = True
    return msgs


def box(state: GameState, content: Content) -> dict | None:
    """入伍段的對話框：進行中是這一步的話（第一步前面接入營那一段）；剛走完是結尾、等「知道了」。其他是 None。
    key 是這一步的 id（結尾是 "enlist_end"），跟說書人的框同一個欄位（FB-076：網頁記收起記的是它）；
    眼前有事件還沒了結時話換成「先把眼前的「…」了結」、pending 標 True、收起來那一行送空字串（跟說書人的框一樣，FB-063／FB-076，
    網頁預設把這一句收成一行）；結尾永遠是 False。"""
    from .guide import pending_line

    who = recruiter(state, content)
    if who is None:
        return None
    p = state.player
    if active(state, content):
        i = p.enlist_step
        waiting = pending_line(state, content)
        text = f"{who.intro}\n\n{who.briefing}" if i == 0 else who.order_hint
        return {
            "speaker": who.name, "key": _steps(content)[i].id, "scene": "", "text": waiting or text,
            "line": "" if waiting else (who.lines[i] if i < len(who.lines) else ""),
            "done": list(p.guide_done), "end": False, "pending": waiting is not None,
        }
    if p.enlist_end:
        return {
            "speaker": who.name, "key": "enlist_end", "scene": "", "text": who.done, "line": "", "done": list(p.guide_done),
            "end": True, "pending": False,
        }
    return None
