from unittest import mock

import pytest

from tianxia import event_gamble as eg
from tianxia.battle_instance import DEFAULT_FREE_TEXT_SUCCESS_RATE, SuccessRateJudgment
from tianxia.models import Choice, Event


@pytest.fixture
def event():
    return Event(
        id="tavern_brawl", title="酒樓鬥毆", text="兩夥人在酒樓裡掀了桌子，{marks:yingshui:棚屋}圍在門口看熱鬧。",
        choices=[Choice(text="走開")],
    )


# ── assess_event_success_rate：LLM 只評機率 ─────────────────────────


def test_assess_without_a_client_returns_the_default(event):
    assert eg.assess_event_success_rate(None, event, "大喊官兵來了") == DEFAULT_FREE_TEXT_SUCCESS_RATE


def test_assess_uses_the_llm_value(event):
    client = mock.Mock()
    client.chat_structured.return_value = SuccessRateJudgment(success_rate=62, reasoning="合理")
    assert eg.assess_event_success_rate(client, event, "大喊官兵來了") == 62


def test_assess_clamps_out_of_range_values(event):
    client = mock.Mock()
    client.chat_structured.return_value = SuccessRateJudgment(success_rate=150)
    assert eg.assess_event_success_rate(client, event, "大喊官兵來了") == 100
    client.chat_structured.return_value = SuccessRateJudgment(success_rate=-5)
    assert eg.assess_event_success_rate(client, event, "大喊官兵來了") == 0


def test_assess_falls_back_when_the_llm_call_fails(event):
    client = mock.Mock()
    client.chat_structured.side_effect = RuntimeError("連不上")
    assert eg.assess_event_success_rate(client, event, "大喊官兵來了") == DEFAULT_FREE_TEXT_SUCCESS_RATE


def test_assess_does_not_call_the_llm_for_blank_text(event):
    client = mock.Mock()
    assert eg.assess_event_success_rate(client, event, "   ") == DEFAULT_FREE_TEXT_SUCCESS_RATE
    client.chat_structured.assert_not_called()


def test_assess_prompt_carries_the_scene_and_guards_against_claimed_success(event):
    """提示詞要有事件情境與玩家的話；「我必定成功」這類宣稱結果的寫法要明講評低（設計 8.1 防灌水）。
    事件文字裡的模糊人數佔位不送給 LLM；玩家的話截到輸入框上限。"""
    client = mock.Mock()
    client.chat_structured.return_value = SuccessRateJudgment(success_rate=50)
    eg.assess_event_success_rate(client, event, "把酒罈砸在地上大喊官兵來了然後趁亂溜走順便拿走錢袋")
    system, user = (m["content"] for m in client.chat_structured.call_args.args[0])
    assert "必定成功" in system and "要求高分" in system
    assert "酒樓鬥毆" in user and "掀了桌子" in user
    assert "{marks:" not in user
    assert "「把酒罈砸在地上大喊官兵來了然後趁亂溜走" in user and "錢袋" not in user


# ── narrate_event_gamble：擲骰後潤色 ───────────────────────────────


def test_narrate_without_a_client_returns_empty(event):
    assert eg.narrate_event_gamble(None, event, "大喊官兵來了", True, "兩夥人一哄而散。") == ""


def test_narrate_falls_back_to_empty_when_the_llm_call_fails(event):
    client = mock.Mock()
    client.chat_text.side_effect = RuntimeError("連不上")
    assert eg.narrate_event_gamble(client, event, "大喊官兵來了", False, "沒人理你。") == ""


def test_narrate_converts_to_traditional_and_strips_quotes(event):
    client = mock.Mock()
    client.chat_text.return_value = "「你扯开嗓子大喊，众人闻声一愣。」\n"
    assert eg.narrate_event_gamble(client, event, "大喊官兵來了", True, "兩夥人一哄而散。") == "你扯開嗓子大喊，眾人聞聲一愣。"


def test_narrate_prompt_carries_the_outcome_and_forbids_new_rewards(event):
    client = mock.Mock()
    client.chat_text.return_value = "你大喊一聲。"
    eg.narrate_event_gamble(client, event, "大喊官兵來了", False, "沒人理你，反挨了一拳。")
    system, user = (m["content"] for m in client.chat_text.call_args.args[0])
    assert "不要改變成敗" in system and "數字" in system and "獎勵" in system
    assert "判定：失敗" in user and "沒人理你，反挨了一拳。" in user and "大喊官兵來了" in user
