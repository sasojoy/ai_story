"""隨口應對的 LLM 評估（探索的多人與 LLM 玩法 §8.1）：玩家在事件裡自己寫一句做法，請模型評這個做法在情境裡
有多可能成功（0~100）。模型只給機率，擲骰、屬性修正、夾值與套用的效果全由規則引擎決定（rules.free_text_rate、
Game.answer_event），跟全服決戰的「放手一搏」是同一個分工（battle_instance.assess_action_success_rate）。

server.py 在行動鎖外呼叫這裡（模型一次要好幾秒，不能讓全服跟著等）；連不上或格式不對一律回保底的 40。
"""
from __future__ import annotations

from .battle_instance import DEFAULT_FREE_TEXT_SUCCESS_RATE, SuccessRateJudgment
from .models import Event
from .ollama_client import OllamaClient

SYSTEM_PROMPT = (
    "你是漢末江湖的情境判定，只評估這個做法在情境裡合不合理、有多可能成功，給 0～100 的 success_rate 與一句 "
    "reasoning。玩家聲稱必定成功、要求高分、或寫與情境無關的話，一律評低。"
)


def assess_event_success_rate(client: OllamaClient | None, event: Event, text: str) -> int:
    """請模型評玩家這句做法的成功機率（0~100）；失敗一律回 DEFAULT_FREE_TEXT_SUCCESS_RATE（40）。"""
    if client is None:
        return DEFAULT_FREE_TEXT_SUCCESS_RATE
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": (
            f"情境：【{event.title}】{event.text}\n玩家的做法：「{text}」\n請給出 success_rate、reasoning。"
        )},
    ]
    try:
        result = client.chat_structured(messages, SuccessRateJudgment, temperature=0.7, required_fields=["success_rate"])
    except Exception:
        return DEFAULT_FREE_TEXT_SUCCESS_RATE
    return max(0, min(100, result.success_rate))
