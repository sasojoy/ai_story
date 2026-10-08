"""FB-104（QA 7cc1fd7，2026-10-08）：董卓的回話裡出現「這酒い好！」——模型文字夾了日文假名，zh.to_traditional 只轉簡繁、補異體字，
假名原樣上了畫面與江湖紀錄。

現在模型的回答（chat_text 的那一段、chat_structured 的每一個字串欄位）夾了假名，就當成這一次模型呼叫失敗（ollama_client.ModelSpokeKana）：
會重問的（chat_structured，鎖外）照樣重問一趟，提醒它用繁體中文；不重問的（chat_text、鎖內的複本）丟給呼叫端走原本的退路
（對話取消、點綴不插句、潤色用固定文字）。不偷偷拿掉假名（CLAUDE.md「保底值會把模型壞了偽裝成模型給了中庸的答案」）。
模型有回、只是那一句不能用：鎖內的額度不因此用完、全服斷路器不打開。對話失敗跟以前叫不動模型一模一樣（不扣體力、這輪取消）。

假的模型：把 requests.post 換掉，回一段夾了假名的字；不連任何網路。"""
from __future__ import annotations

import json
import random

import pytest
import requests

from tianxia import companion_agent, event_llm, flavor, naming
from tianxia.battle_instance import SuccessRateJudgment
from tianxia.engine import Game
from tianxia.ollama_client import InLockClient, ModelBudget, ModelSpokeKana, OllamaClient, has_kana

REAL_CHAT_STRUCTURED = OllamaClient.chat_structured  # 匯入時抓：conftest 的 autouse 之後會換成「連不上」
REAL_CHAT_TEXT = OllamaClient.chat_text

KANA_LINE = "這酒い好！既然你想聽……"


class _Reply:
    def __init__(self, content):
        self._content = content
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {"message": {"content": self._content}}


@pytest.fixture
def model(monkeypatch):
    """假的 Ollama：replies 依序回；sent 記下每一趟送的 messages。真的 chat_text／chat_structured 換回來。"""
    state = {"replies": [], "sent": []}

    def post(url, json=None, timeout=None):
        state["sent"].append(json["messages"])
        return _Reply(state["replies"].pop(0))

    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(OllamaClient, "chat_structured", REAL_CHAT_STRUCTURED)
    monkeypatch.setattr(OllamaClient, "chat_text", REAL_CHAT_TEXT)
    return state


def _turn(narrative):
    return json.dumps({"narrative": narrative, "options": ["閒聊幾句", "就此告辭"], "option_tags": ["尋常寒暄", "尋常寒暄"]},
                      ensure_ascii=False)


# ── 認得假名 ─────────────────────────────────────────


@pytest.mark.parametrize("text, kana", [
    ("這酒い好！", True), ("ホウサイ來了", True), ("ｶﾞ", True), ("ー", True),
    ("波才・黃巾別部營寨", False), ("第 1 週・週一 00:00", False), ("這酒好！", False), ("", False), ("ok…", False),
])
def test_kana_is_hiragana_katakana_and_half_width_but_not_the_middle_dot(text, kana):
    assert has_kana(text) is kana


# ── 兩種呼叫 ─────────────────────────────────────────


def test_a_text_reply_with_kana_is_a_failed_call(model):
    model["replies"] = [KANA_LINE]
    with pytest.raises(ModelSpokeKana):
        OllamaClient().chat_text([{"role": "user", "content": "說一句"}])
    model["replies"] = ["這酒好！"]
    assert OllamaClient().chat_text([{"role": "user", "content": "說一句"}]) == "這酒好！"


def test_a_structured_reply_with_kana_is_asked_again_in_chinese(model):
    """第一趟夾了假名：重問一趟，提醒用繁體中文；第二趟乾淨就用第二趟。"""
    model["replies"] = [_turn(KANA_LINE), _turn("這酒好！既然你想聽……")]
    turn = OllamaClient().chat_structured([{"role": "user", "content": "談"}], companion_agent.CompanionTurn)
    assert turn.narrative == "這酒好！既然你想聽……" and len(model["sent"]) == 2
    assert "日文假名" in model["sent"][1][-1]["content"] and "繁體中文" in model["sent"][1][-1]["content"]


def test_kana_in_any_field_counts_and_two_kana_replies_fail(model):
    model["replies"] = [json.dumps({"narrative": "好。", "options": ["いい", "就此告辭"], "option_tags": ["a", "b"]}, ensure_ascii=False)] * 2
    with pytest.raises(ModelSpokeKana):
        OllamaClient().chat_structured([{"role": "user", "content": "談"}], companion_agent.CompanionTurn)
    assert len(model["sent"]) == 2


def test_the_in_lock_copy_does_not_ask_again_and_keeps_its_budget(model):
    """鎖內的複本不重問（一趟就丟）；這不是模型壞了，額度不用完、斷路器不開。真的失敗（連不上）照舊用完額度。"""
    model["replies"] = [_turn(KANA_LINE)]
    client = OllamaClient()
    client.retry = False
    budget = ModelBudget()
    locked = InLockClient(client, budget)
    with pytest.raises(ModelSpokeKana):
        locked.chat_structured([{"role": "user", "content": "談"}], companion_agent.CompanionTurn)
    assert len(model["sent"]) == 1 and budget.gave_up is False
    model["replies"] = [KANA_LINE]
    with pytest.raises(ModelSpokeKana):
        locked.chat_text([{"role": "user", "content": "說一句"}])
    assert budget.gave_up is False
    model["replies"] = ["{不是 JSON"]
    with pytest.raises(Exception):
        locked.chat_structured([{"role": "user", "content": "談"}], SuccessRateJudgment)
    assert budget.gave_up is True


# ── 每一條把模型的字放上畫面的路 ─────────────────────────────


def test_a_dialogue_turn_with_kana_twice_fails_like_an_unreachable_model(model):
    model["replies"] = [_turn(KANA_LINE), _turn(KANA_LINE)]
    with pytest.raises(companion_agent.DialogueUnavailable):
        companion_agent.generate_turn(OllamaClient(), [{"role": "user", "content": "談"}])


def test_a_kana_dialogue_costs_the_same_as_an_unreachable_model(model, content):
    """交友開口那一輪模型兩趟都夾假名：跟模型叫不動同一條路（退回體力、不開對話、同一句話）。"""
    content.characters["mate"].deep_interaction = True
    outcome = {}
    for case in ("kana", "down"):
        game = Game.new(content, "甲" + case[0], rng=random.Random(0))
        game.client = OllamaClient()
        before = game.state.player.stamina
        model["replies"] = [_turn(KANA_LINE)] * 2 if case == "kana" else ["{不是 JSON"] * 2
        msgs = game.choose("act:socialize")
        outcome[case] = (msgs, game.state.player.stamina - before, game.state.player.pending_companion)
    assert outcome["kana"] == outcome["down"] and outcome["kana"][1:] == (0, None)
    assert not any(has_kana(m) for m in outcome["kana"][0])


def test_flavor_and_the_free_text_polish_drop_a_kana_line(model):
    model["replies"] = [KANA_LINE]
    assert flavor._ask(OllamaClient(), "說一句") == ""  # noqa: SLF001  點綴：不插那一句
    model["replies"] = [KANA_LINE]
    event = type("E", (), {"title": "茶館", "text": "說書人拍了一下醒木。"})()
    assert event_llm.narrate_event_gamble(OllamaClient(), event, "拍桌子", True, "茶客都看過來。") is None


def test_a_name_with_kana_never_passes(content):
    assert naming.name_problem("鐵い拳", content) == "只能是中文字"
