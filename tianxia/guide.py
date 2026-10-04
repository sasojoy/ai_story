"""新手引導、個人目標與任務區塊：讓玩家知道這一季在發生什麼、下一步該做什麼。"""
from __future__ import annotations

from .models import Content, TutorialStep
from .rules import apply_effect, check_condition, season_one_off
from .state import GameState
from .world import current_act, current_storyline, season_endings, storyline_off
from .world_state import WorldStateStore


def tutorial_active(state: GameState, content: Content) -> bool:
    return state.player.tutorial_step < len(content.tutorial.steps)


def tutorial_intro(content: Content) -> list[str]:
    t = content.tutorial
    return [f"【{t.speaker}】{t.steps[0].text}"] if t.steps else []


def _step_done(state: GameState, content: Content, step: TutorialStep, action: str) -> bool:
    goal = step.done_when
    if goal.action and goal.action != action:
        return False
    if goal.locations and state.player.location not in goal.locations:
        return False
    if goal.has_wugong and state.player.member.wugong_id is None:
        return False
    return check_condition(goal.condition, state)


def note_action(state: GameState, content: Content, world: WorldStateStore, action: str) -> list[str]:
    """玩家做完一個行動後呼叫：符合目前引導步驟就推進一步並發獎勵，接著立刻檢查
    下一步是否也已經達成（例如旗標早就成立），一路完成到不再符合為止。"""
    t = content.tutorial
    msgs: list[str] = []
    while tutorial_active(state, content) and _step_done(
        state, content, t.steps[state.player.tutorial_step], action
    ):
        step = t.steps[state.player.tutorial_step]
        state.player.tutorial_step += 1
        msgs.append("✔ 引導完成")
        msgs += apply_effect(step.reward, state, content, world)
    if not msgs:
        return []
    if tutorial_active(state, content):
        msgs.append(f"【{t.speaker}】{t.steps[state.player.tutorial_step].text}")
    elif t.outro:
        msgs.append(f"【{t.speaker}】{t.outro}")
    return msgs


def _idle(state: GameState) -> bool:
    return (
        not state.world.ended and state.pending_event is None and state.player.busy_until is None
        and state.player.resting_since is None and state.player.journey is None
    )


def next_hint(state: GameState, content: Content) -> str:
    """引導還沒做完就是引導的下一步；否則是這一幕主線的目標（第一季不觸發的主線沒有，計畫 T8），體力將滿時加一句提醒。
    兩者都沒有時是空字串。"""
    if tutorial_active(state, content):
        t = content.tutorial
        return f"（{t.speaker}）{t.steps[state.player.tutorial_step].text}"
    hints = [] if storyline_off(state, content) else [current_act(state, content).goal]
    if state.player.stamina >= content.config.stamina_max * 0.9 and _idle(state):
        hints.append("體力將滿，別讓它浪費。")
    return "　".join(hints)


def quest_text(state: GameState, content: Content) -> str:
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
    hint = next_hint(state, content)
    if hint:
        parts.append(f"**下一步**：{hint}")
    return "\n\n".join(parts)  # 全部都被跳過時是空字串：網頁不畫「主線與目標」那一塊
