"""新手引導、個人目標與任務區塊：讓玩家知道這一季在發生什麼、下一步該做什麼。"""
from __future__ import annotations

from .models import Content
from .rules import apply_effect, check_condition
from .state import GameState
from .world import current_act, current_storyline


def tutorial_active(state: GameState, content: Content) -> bool:
    return state.player.tutorial_step < len(content.tutorial.steps)


def tutorial_intro(content: Content) -> list[str]:
    t = content.tutorial
    return [f"【{t.speaker}】{t.steps[0].text}"] if t.steps else []


def note_action(state: GameState, content: Content, action: str) -> list[str]:
    """玩家做完一個行動後呼叫：符合目前引導步驟就推進一步並發獎勵。"""
    if not tutorial_active(state, content):
        return []
    t = content.tutorial
    step = t.steps[state.player.tutorial_step]
    goal = step.done_when
    if goal.action and goal.action != action:
        return []
    if goal.locations and state.player.location not in goal.locations:
        return []
    if not check_condition(goal.condition, state):
        return []
    state.player.tutorial_step += 1
    msgs = [f"✔ 引導完成：{step.text}"] + apply_effect(step.reward, state, content)
    if tutorial_active(state, content):
        msgs.append(f"【{t.speaker}】{t.steps[state.player.tutorial_step].text}")
    elif t.outro:
        msgs.append(f"【{t.speaker}】{t.outro}")
    return msgs


def next_hint(state: GameState, content: Content) -> str:
    if tutorial_active(state, content):
        t = content.tutorial
        return f"（{t.speaker}）{t.steps[state.player.tutorial_step].text}"
    hint = current_act(state, content).goal
    if state.player.stamina >= content.config.stamina_max * 0.9:
        hint += "　體力將滿，別讓它浪費。"
    return hint


def quest_text(state: GameState, content: Content) -> str:
    w = state.world
    if w.ended:
        return f"### 賽季落幕：{w.ending_title}\n\n{w.ending_text}"
    line = current_storyline(state, content)
    act = current_act(state, content)
    parts = [
        f"### 主線：{line.name}　第{w.act + 1}/{len(line.acts)}幕「{act.title}」",
        act.text,
        f"**目標**：{act.goal}",
    ]
    endings = [e for e in content.scenario.endings if e.storyline in (None, line.id) and e.hint]
    if endings:
        parts.append("**可能的結局**\n\n" + "\n".join(f"- {e.title}：{e.hint}" for e in endings))
    milestones = content.scenario.milestones
    if milestones:
        parts.append("**個人目標**\n\n" + "\n".join(
            f"- {'☑' if check_condition(m.condition, state) else '☐'} {m.text}" for m in milestones
        ))
    parts.append(f"**下一步**：{next_hint(state, content)}")
    return "\n\n".join(parts)
