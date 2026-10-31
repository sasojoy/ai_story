"""NPC 智能 2.0的必填欄位要寫進送出去的 schema（2026-10-24 主機實測：gemma ask 空白 14/30、「帶我去廣宗」0/10、
商量打法 willing 沒填 4/30）。CompanionTurn 的 ask、willing……都有預設值 None，呼叫只宣告 narrative、options 必填的話，
結構化輸出的語法允許模型整個略過；10/22 narrative 踩過同一個坑。這裡釘住：帶了NPC 智能 2.0提示的那一輪，
這些欄位一定進 schema 的 required（空字串照樣算答了），平常閒聊不加。"""

import json
from unittest import mock

import pytest
import requests

from tianxia import companion_agent, figure_life, parley
from tianxia.companion_agent import CompanionTurn
from tianxia.engine import PLAN_OPTION, ROAD_SAY
from tianxia.ollama_client import OllamaClient
from tianxia.state import ParleyBacking

REAL_CHAT_STRUCTURED = OllamaClient.chat_structured  # 匯入時抓：conftest 的 autouse 之後會換成「連不上」


class _Reply:
    status_code = 200

    def __init__(self, content):
        self._content = content

    def raise_for_status(self):
        return None

    def json(self):
        return {"message": {"content": self._content}}


@pytest.fixture
def wire(monkeypatch):
    """假的 Ollama：記下每一趟送出去的 schema（payload 的 format），回 replies 的下一個。"""
    state = {"replies": [], "schemas": []}

    def post(url, json=None, timeout=None):
        state["schemas"].append(json["format"])
        return _Reply(state["replies"].pop(0))

    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(OllamaClient, "chat_structured", REAL_CHAT_STRUCTURED)
    return state


def _reply(**extra):
    return json.dumps({"narrative": "他點了點頭。", "options": ["閒聊幾句", "就此告辭"], "option_tags": ["尋常寒暄", "尋常寒暄"],
                       **extra}, ensure_ascii=False)


@pytest.mark.parametrize("fields", [parley.ASK_FIELDS, parley.PLAN_FIELDS, parley.PLEA_FIELDS])
def test_the_parley_fields_are_written_into_the_schema_sent_to_the_model(wire, fields):
    wire["replies"] = [_reply(**{f: 0 if f == "willing" else "" for f in fields})]
    companion_agent.generate_turn(OllamaClient(), [{"role": "user", "content": "談"}], fields)
    required = set(wire["schemas"][0]["required"])
    assert set(fields) <= required and {"narrative", "options"} <= required
    assert len(wire["schemas"]) == 1  # ask 空字串（只是閒聊）照樣算答了：不重問


def test_plain_chat_does_not_require_the_parley_fields(wire):
    wire["replies"] = [_reply()]
    companion_agent.generate_turn(OllamaClient(), [{"role": "user", "content": "談"}])
    assert set(wire["schemas"][0]["required"]) == {"narrative", "options"}


def test_every_parley_field_is_a_field_of_the_turn():
    fields = set(CompanionTurn.model_fields)
    assert set(parley.ASK_FIELDS + parley.PLAN_FIELDS + parley.PLEA_FIELDS) <= fields  # 拼錯的欄位 _require_in_schema 會靜靜略過


# ── 遊戲裡每一條路都帶上那一份 ────────────


@pytest.fixture
def on(content):
    content.config.parley.enabled = True
    content.characters["mate"].deep_interaction = True
    content.characters["mate"].haunts = ["lake"]
    return content


OPEN = CompanionTurn(narrative="他點了點頭。", options=["閒聊幾句", "就此告辭"], option_tags=["尋常寒暄", "尋常寒暄"])


@pytest.fixture
def talking(on, game):
    with mock.patch.object(companion_agent, "_generate", return_value=OPEN):
        game.choose("act:socialize")
    return game


def test_the_say_request_requires_the_ask_fields_and_the_plan_request_the_plan_fields(talking):
    assert talking.dialogue_request("talk:say", text="韓兄幫我一個忙").required == parley.ASK_FIELDS
    s = talking.state
    s.player.parley_backing = ParleyBacking(figure="mate", region=None, day=parley.game_day(talking.content, s.world))
    assert talking.dialogue_request(PLAN_OPTION, text="從左翼包抄").required == parley.PLAN_FIELDS


def test_the_in_lock_say_path_passes_the_ask_fields_too(talking):
    with mock.patch.object(companion_agent, "generate_turn", return_value=OPEN) as gen:
        talking.choose("talk:say", text="韓兄幫我一個忙")
    assert gen.call_args.args[2] == parley.ASK_FIELDS


def test_the_opening_requires_the_plea_fields_only_when_he_has_something_on_his_mind(on, game):
    with mock.patch.object(figure_life, "mood_any", return_value="焦慮"):
        assert game.dialogue_request("act:socialize").required == parley.PLEA_FIELDS
    with mock.patch.object(figure_life, "mood_any", return_value="平靜"):
        assert game.dialogue_request("act:socialize").required == ()


def test_the_road_request_requires_the_ask_fields(talking):
    with mock.patch.object(companion_agent, "generate_turn",
                           return_value=OPEN.model_copy(update={"ask": "escort:lake", "willing": 100})), \
            mock.patch.object(parley, "roll", return_value=1):
        talking.choose("talk:say", text="帶我去湖邊")
    assert talking.state.player.parley_escort == "mate"
    assert talking.dialogue_request(ROAD_SAY, text="將軍可有指點？").required == parley.ASK_FIELDS


def test_parley_off_requires_nothing_extra(content, game):
    content.characters["mate"].deep_interaction = True
    with mock.patch.object(companion_agent, "_generate", return_value=OPEN):
        game.choose("act:socialize")
    assert not content.config.parley.enabled
    assert game.dialogue_request("talk:say", text="韓兄好").required == ()


def test_the_prompt_keeps_refuse_out_of_condition(on, talking):
    prompt = talking._parley_prompt("mate")
    assert f"不能填 \"{parley.REFUSE}\"" in prompt and "ask 也照樣填玩家求的那件事" in prompt


def test_willing_cannot_be_null_on_the_wire(wire):
    """主機複驗：商量打法 willing 漏填 5/30——鍵已經強制要寫，模型寫成 null。型別裡的 null 也要拿掉。"""
    wire["replies"] = [_reply(willing=70, narrative_no="不成。")]
    companion_agent.generate_turn(OllamaClient(), [{"role": "user", "content": "談"}], parley.PLAN_FIELDS)
    assert wire["schemas"][0]["properties"]["willing"]["type"] == "integer"


def test_a_plan_without_a_rate_is_not_silently_floored(talking):
    s = talking.state
    s.player.parley_backing = ParleyBacking(figure="mate", region=None, day=parley.game_day(talking.content, s.world))
    with mock.patch.object(companion_agent, "generate_turn", return_value=OPEN):  # willing 是 None
        msgs = talking.choose(PLAN_OPTION, text="從左翼包抄")
    assert msgs == ["韓鐵沉吟不語。"] and s.player.parley_backing.plan is None  # 沒談成，還可以再商量
    assert PLAN_OPTION in {o.id for o in talking.options(odds=False)}


def test_the_prompt_keeps_condition_ids_out_of_ask(on, talking):
    assert "只能填在 condition，不能填在 ask" in talking._parley_prompt("mate")


def test_the_two_other_versions_must_have_words_in_the_schema(wire):
    """2026-10-31 主機實測：鍵強制要寫了，模型照樣把婉拒那一版回成空字串（5/5）。schema 上那兩版至少一個字；
    模型真的回了空字串照舊當沒寫（引擎用固定句），不因此整輪作廢、也不重問。"""
    wire["replies"] = [_reply(ask="", willing=50, condition="", narrative_terms="", narrative_no=" ")]
    turn = companion_agent.generate_turn(OllamaClient(), [{"role": "user", "content": "談"}], parley.ASK_FIELDS)
    props = wire["schemas"][0]["properties"]
    assert props["narrative_no"]["minLength"] == 1 and props["narrative_terms"]["minLength"] == 1
    assert turn.narrative_no is None and turn.narrative_terms is None and len(wire["schemas"]) == 1
