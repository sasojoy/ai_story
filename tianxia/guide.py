"""新手引導、個人目標與任務區塊：讓玩家知道這一季在發生什麼、下一步該做什麼。"""
from __future__ import annotations

from . import library, prologue, ranks
from .martial_arts import QUALITIES
from .models import Content, TutorialStep
from .rules import apply_effect, check_condition, pending_event_title, season_one, season_one_off
from .state import GameState
from .world import current_act, current_storyline, season_endings, storyline_off
from .world_state import WorldStateStore


def steps(state: GameState, content: Content) -> list[TutorialStep]:
    """這一季的引導步驟：第一季才有的（TutorialStep.season_one）只在 rules.season_one 成立時算進來（計畫 T6）。
    它們排在最後（content.validate 檢查），所以 PlayerState.tutorial_step 這個數字在兩種季指到的都是同一步。"""
    on = season_one(content, state.world)
    return [step for step in content.tutorial.steps if on or not step.season_one]


def base_step_count(content: Content) -> int:
    """不分季都有的步驟數（第一季的步驟排在它們後面）：做到這裡就算「做完引導」，換季時保留進度（FB-034）。"""
    return sum(1 for step in content.tutorial.steps if not step.season_one)


def tutorial_active(state: GameState, content: Content) -> bool:
    return state.player.tutorial_step < len(steps(state, content))


def speaker_of(content: Content, step: TutorialStep) -> str:
    """這一步是誰說的（框上寫的人）：步驟自己寫了就用，不然是 Tutorial.speaker。"""
    return step.speaker or content.tutorial.speaker


def speakers(content: Content) -> set[str]:
    """引導裡會出現的說話的人（框上的名字）：Game._note_guide 照它把「下一步的話」跟「✔ 與獎勵」分開。"""
    return {content.tutorial.speaker} | {s.speaker for s in content.tutorial.steps if s.speaker}


def tutorial_intro(content: Content) -> list[str]:
    t = content.tutorial
    if not t.steps or not t.steps[0].text:  # 序章第一步沒有話（還沒遇到師父）
        return []
    return [f"【{speaker_of(content, t.steps[0])}】{t.steps[0].text}"]


def _step_done(
    state: GameState, content: Content, world: WorldStateStore, step: TutorialStep, action: str,
) -> bool:
    goal = step.done_when
    if goal.action and goal.action != action:
        return False
    if goal.locations and state.player.location not in goal.locations:
        return False
    if goal.has_wugong and state.player.member.wugong_id is None:
        return False
    if goal.fused or goal.fused_level or goal.fused_quality:  # 序章：合成出來的那一門（新手引導計畫一）
        arts = prologue.fused_arts(state, content, world)
        if not arts:
            return False
        if goal.fused_level and max(library.level_of(state, a.id) for a in arts) < goal.fused_level:
            return False
        if goal.fused_quality and max(QUALITIES.index(a.quality) for a in arts) < QUALITIES.index(goal.fused_quality):
            return False
    return check_condition(goal.condition, state)


def note_action(state: GameState, content: Content, world: WorldStateStore, action: str) -> list[str]:
    """玩家做完一個行動後呼叫：符合目前引導步驟就推進一步並發獎勵（序章的步驟另外給武學），接著立刻檢查
    下一步是否也已經達成（例如旗標早就成立），一路完成到不再符合為止。下一步的話是空的（序章第一步）就不說。"""
    t = content.tutorial
    todo = steps(state, content)
    msgs: list[str] = []
    while tutorial_active(state, content) and _step_done(
        state, content, world, todo[state.player.tutorial_step], action
    ):
        step = todo[state.player.tutorial_step]
        state.player.tutorial_step += 1
        msgs.append("✔ 引導完成")
        msgs += apply_effect(step.reward, state, content, world)
        if step.give_art is not None:
            msgs += prologue.give_art(state, content, world, step.give_art)
    if not msgs:
        return []
    if tutorial_active(state, content):
        nxt = todo[state.player.tutorial_step]
        if nxt.text:
            msgs.append(f"【{speaker_of(content, nxt)}】{prologue.fill(nxt.text, state, content, world)}")
    elif t.outro:
        msgs.append(f"【{t.speaker}】{t.outro}")
    return msgs


def _idle(state: GameState) -> bool:
    return (
        not state.world.ended and state.pending_event is None and state.player.busy_until is None
        and state.player.resting_since is None and state.player.journey is None
        and state.player.sensing is None
    )


def pending_line(state: GameState, content: Content) -> str | None:
    """眼前有事件還沒了結時，引導不推這一步（常常是叫人出發，事件卻擋著路），改說這一句（FB-063）；沒有待處理的事件時是 None。
    說書人的框（Game.guide_box）與「下一步」（next_hint）都用它，句子只寫在這裡。"""
    title = pending_event_title(state, content)
    return f"先把眼前的「{title}」了結" if title is not None else None


def step_text(state: GameState, content: Content, world: WorldStateStore | None = None) -> str:
    """引導目前這一步要說的話：眼前有事件待處理時是 pending_line，不然是這一步本身的話。呼叫端先確認引導還沒做完。
    給了 world，序章的話裡的 {武學} 換成合成出來的那一門（prologue.fill）；沒給就照原樣。"""
    text = pending_line(state, content) or steps(state, content)[state.player.tutorial_step].text
    return text if world is None else prologue.fill(text, state, content, world)


def next_hint(state: GameState, content: Content, world: WorldStateStore | None = None) -> str:
    """引導還沒做完就是引導的下一步（有事件待處理時見 pending_line）；否則是這一幕主線的目標（第一季不觸發的主線沒有，計畫 T8），
    體力將滿時加一句提醒。兩者都沒有時是空字串。序章第一步沒有話（還沒遇到師父）：不寫「（師父）」，也沒有下一步可寫。"""
    if tutorial_active(state, content):
        step = steps(state, content)[state.player.tutorial_step]
        if not step.text:
            return ""
        return f"（{speaker_of(content, step)}）{step_text(state, content, world)}"
    hints = [] if storyline_off(state, content) else [current_act(state, content).goal]
    if state.player.stamina >= content.config.stamina_max * 0.9 and _idle(state):
        hints.append("體力將滿，別讓它浪費。")
    return "　".join(hints)


def quest_text(state: GameState, content: Content, world: WorldStateStore | None = None) -> str:
    w = state.world
    if w.ended:
        return f"### 賽季落幕：{w.ending_title}\n\n{w.ending_text}"
    line = current_storyline(state, content)
    parts: list[str] = []
    lines: tuple[str | None, ...] = (None,)  # 結局只列不分主線的，與目前這條主線的
    if not storyline_off(state, content):  # 第一季不觸發的 beta 主線（計畫 T8）：不顯示它，其餘照舊
        act = current_act(state, content)
        parts += [f"### 主線：{line.name}　第{w.act + 1}/{len(line.acts)}幕「{act.title}」", act.text, f"**目標**：{act.goal}"]
        lines = (None, line.id)
    endings = [e for e in season_endings(state, content) if e.storyline in lines and e.hint]  # 第一季列第一季的六種（計畫 T9）
    if endings:
        parts.append("**可能的結局**\n\n" + "\n".join(f"- {e.title}：{e.hint}" for e in endings))
    hidden = season_one_off(content, w, "milestones")  # 第一季做不到的 beta 個人目標不列（計畫 T8）
    milestones = [m for m in content.scenario.milestones if m.id not in hidden]
    if milestones:
        parts.append("**個人目標**\n\n" + "\n".join(
            f"- {'☑' if check_condition(m.condition, state) else '☐'} {m.text}" for m in milestones
        ))
    summons = ranks.summons_line(state, content)  # 還沒去的召見（計畫 T5）：照此刻出面的人寫
    if summons:
        parts.append(f"**召見**：{summons}")
    hint = next_hint(state, content, world)
    if hint:
        parts.append(f"**下一步**：{hint}")
    return "\n\n".join(parts)  # 全部都被跳過時是空字串：網頁不畫「主線與目標」那一塊
