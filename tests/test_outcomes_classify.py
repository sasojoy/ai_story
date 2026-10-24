"""減法季批 4（主機側計畫 Task 4-2 的純規則那一半；整合設計 5.1、5.9）：模型把玩家那句話歸到一種後果（event_llm.classify_outcome），
引擎照那一種的判法走（outcomes.plan）。三段式的接線（answer_event、server）等批 0 的開關，見 tests/test_outcomes_answer.py（之後）。
模型一律是假的（mock.Mock().chat_structured.return_value）：不打 11434。"""
import json
from unittest import mock

import pytest
import requests

from tianxia import event_llm, outcomes
from tianxia.battle_instance import DEFAULT_FREE_TEXT_SUCCESS_RATE
from tianxia.models import Choice, Effect, Event, Outcome
from tianxia.ollama_client import OllamaClient
from tianxia.rules import FREE_TEXT_MAX_RATE, FREE_TEXT_MIN_RATE, FREE_TEXT_PER_POINT

REAL_CHAT_STRUCTURED = OllamaClient.chat_structured  # 匯入時抓：conftest 的 autouse 之後會換成「連不上」
NOWHERE = "http://127.0.0.1:9"  # 萬一 requests.post 沒換到，也不會碰到模型的 port

PLOW = Event(
    id="plow", title="人拉犁", text="荒田邊，一個老漢把犁繩套在自己肩上。他說耕牛前幾天被一夥散兵牽走了。", locations=["town"],
    choices=[Choice(text="嘆口氣，繼續趕路")],
)
LABOR = Outcome(id="labor", tag="出力：替他拉犁、修犁、想省力的法子", check={"stat": "best_of", "stats": ["str", "wis"], "difficulty": 4},
                effect=Effect(text="你拉著犁走完一整壟。", stats={"good": 2}, marks={"town:田有人耕": 1}, contribution=2),
                fail_effect=Effect(text="犁頭卡進石縫，你閃了腰。", stamina=-15))
CHASE = Outcome(id="chase", tag="討牛：去追那夥散兵", combat="dipi",
                effect=Effect(text="你把牛奪了回來。", stats={"good": 2, "fame": 1}, marks={"town:散兵退了": 1}, contribution=4),
                fail_effect=Effect(text="流寇人多，你被打得退回田邊。", stats={"silver": -10}))
GIVE = Outcome(id="give", tag="周濟：給他錢或糧", cost={"silver": 10},
               effect=Effect(text="你把幾個錢塞進老漢手裡。", stats={"good": 1}, marks={"town:鄉里得濟": 1}, contribution=1))
LEAVE = Outcome(id="leave", tag="走開：不管、看著、對不上的", effect=Effect(text="你走出很遠。"))
ALL = [LABOR, CHASE, GIVE, LEAVE]


def _client(outcome="chase", rate=55):
    client = mock.Mock()
    client.chat_structured.return_value = event_llm.OutcomeJudgment(outcome=outcome, success_rate=rate)
    return client


# ── 歸類（event_llm.classify_outcome）──────────────────────


@pytest.mark.parametrize("text, said, expected", [
    ("我替他把犁拉完", "labor", ("labor", 55)),
    ("我去把牛搶回來", "chase", ("chase", 55)),
    ("給他十兩去買頭牛", "give", ("give", 55)),
    ("跟他聊聊天氣", "leave", ("leave", 55)),
])
def test_the_model_picks_one_of_the_listed_outcomes(text, said, expected):
    assert event_llm.classify_outcome(_client(said), PLOW, ALL, text) == expected


@pytest.mark.parametrize("said", ["fly", "", "LABOR", None, 3, ["chase"]])
def test_an_id_not_on_the_list_is_the_fallback(said):
    """模型回的 outcome 不在清單（大小寫不同、空的、不是字串）一律是最後一種（計畫 Review Focus 第 4 條）。"""
    client = mock.Mock()
    client.chat_structured.return_value = mock.Mock(outcome=said, success_rate=70)
    assert event_llm.classify_outcome(client, PLOW, ALL, "我替他把犁拉完") == ("leave", 70)


@pytest.mark.parametrize("said, rate", [(140, 100), (-5, 0), (55.6, 56), ("70", 70), ("很高", DEFAULT_FREE_TEXT_SUCCESS_RATE), (None, 40)])
def test_the_rate_is_clamped_to_zero_to_a_hundred(said, rate):
    client = mock.Mock()
    client.chat_structured.return_value = mock.Mock(outcome="labor", success_rate=said)
    assert event_llm.classify_outcome(client, PLOW, ALL, "我替他把犁拉完") == ("labor", rate)


def test_no_model_a_failed_call_or_no_words_is_the_fallback_at_forty():
    failing = mock.Mock()
    failing.chat_structured.side_effect = RuntimeError("連不上")
    assert event_llm.classify_outcome(None, PLOW, ALL, "我替他把犁拉完") == ("leave", DEFAULT_FREE_TEXT_SUCCESS_RATE) == ("leave", 40)
    assert event_llm.classify_outcome(failing, PLOW, ALL, "我替他把犁拉完") == ("leave", 40)
    assert event_llm.classify_outcome(_client(), PLOW, ALL, "   ") == ("leave", 40)


def test_the_call_lists_the_tags_but_not_the_rewards_and_keeps_the_old_prompt():
    client = _client()
    event_llm.classify_outcome(client, PLOW, ALL, "我去把牛搶回來，順便把那夥散兵統統打一頓再綁去見官")
    messages = client.chat_structured.call_args.args[0]
    system, user = messages[0]["content"], messages[1]["content"]
    assert system == event_llm.OUTCOME_PROMPT != event_llm.SYSTEM_PROMPT  # 評分那一段（test_fb223 鎖住）一個字都不動
    assert "人拉犁" in user and "「我去把牛搶回來，順便把那夥散兵統統打一頓」" in user  # 玩家的字照舊截到二十字
    for o in ALL:
        assert f"{o.id}：{o.tag}" in user
        assert o.effect.text not in user  # 模型只看得到後果的類名與做法，看不到結果與獎勵
    assert "最後一種" in system
    kwargs = client.chat_structured.call_args.kwargs
    assert kwargs["temperature"] == 0.3 and kwargs["num_predict"] == event_llm.OUTCOME_PREDICT
    schema = client.chat_structured.call_args.args[1].model_json_schema()
    assert schema["properties"]["outcome"]["enum"] == ["labor", "chase", "give", "leave"]  # 只能填清單上的 id


class _Reply:
    status_code = 200

    def __init__(self, content):
        self._content = content

    def raise_for_status(self):
        return None

    def json(self):
        return {"message": {"content": self._content}}


@pytest.mark.parametrize("body, expected", [
    ({"outcome": "give", "success_rate": 62}, ("give", 62)),
    ({"outcome": "搶牛", "success_rate": 62}, ("leave", 62)),
    ({"outcome": None, "success_rate": "很高"}, ("leave", 40)),
], ids=["listed", "unlisted", "odd"])
def test_the_real_client_sends_the_enum_and_reads_the_answer(monkeypatch, body, expected):
    """走真的 OllamaClient.chat_structured（假的 requests.post、死埠）：送出去的 schema 有這則事件的 id 清單、兩欄必填，
    num_predict 是 OUTCOME_PREDICT；回來的怪值一趟就讀進來（不重問）。"""
    sent = []

    def post(url, **kwargs):
        sent.append(kwargs["json"])
        return _Reply(json.dumps(body, ensure_ascii=False))

    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(OllamaClient, "chat_structured", REAL_CHAT_STRUCTURED)
    assert event_llm.classify_outcome(OllamaClient(base_url=NOWHERE), PLOW, ALL, "給他十兩去買頭牛") == expected
    assert len(sent) == 1
    schema = sent[0]["format"]
    assert schema["properties"]["outcome"]["enum"] == ["labor", "chase", "give", "leave"]
    assert set(schema["required"]) >= {"outcome", "success_rate"}
    assert sent[0]["options"]["num_predict"] == event_llm.OUTCOME_PREDICT


def test_outcome_of_reads_strictly():
    ids = ["labor", "leave"]
    assert event_llm.outcome_of(" labor ", ids) == "labor"
    assert event_llm.outcome_of("Labor", ids) == event_llm.outcome_of(None, ids) == "leave"


# ── 走哪一條（outcomes.plan）──────────────────────────────


def test_a_check_outcome_rolls_at_the_free_text_rate_on_its_best_stat(state, content, world):
    state.player.stats.update(str=8, wis=3)
    got = outcomes.plan(ALL, "labor", 40, state, content, world)
    assert (got.outcome, got.way, got.rate) == (LABOR, "check", 40 + (8 - 5) * FREE_TEXT_PER_POINT)
    state.player.stats.update(str=3, wis=9)
    assert outcomes.plan(ALL, "labor", 40, state, content, world).rate == 40 + (9 - 5) * FREE_TEXT_PER_POINT
    assert outcomes.plan(ALL, "labor", 100, state, content, world).rate == FREE_TEXT_MAX_RATE
    state.player.stats.update(str=0, wis=0)
    assert outcomes.plan(ALL, "labor", 0, state, content, world).rate == FREE_TEXT_MIN_RATE


def test_the_engine_clamps_the_models_rate_again(state, content, world):
    state.player.stats.update(str=5, wis=5)
    assert outcomes.plan(ALL, "labor", 900, state, content, world).rate == FREE_TEXT_MAX_RATE
    assert outcomes.plan(ALL, "labor", -900, state, content, world).rate == FREE_TEXT_MIN_RATE


def test_combat_cost_and_fallback_do_not_roll(state, content, world):
    chase = outcomes.plan(ALL, "chase", 55, state, content, world)
    assert (chase.way, chase.rate) == ("combat", None)  # 照打的那一場
    give = outcomes.plan(ALL, "give", 5, state, content, world)
    assert (give.way, give.rate) == ("cost", None)  # 掏錢必成（企劃者第 8 件 c）
    leave = outcomes.plan(ALL, "leave", 99, state, content, world)
    assert (leave.way, leave.rate) == ("fallback", None)
    assert outcomes.plan(ALL, "fly", 99, state, content, world).outcome is LEAVE  # 引擎也再認一次清單


def test_a_cost_outcome_needs_the_silver(state):
    state.player.stats["silver"] = 9
    assert outcomes.cost_problem(GIVE, state) == outcomes.NOT_ENOUGH_SILVER
    state.player.stats["silver"] = 10
    assert outcomes.cost_problem(GIVE, state) == ""
    assert outcomes.cost_problem(LABOR, state) == outcomes.cost_problem(LEAVE, state) == ""
    assert outcomes.paid(GIVE).stats == {"silver": -10, "good": 1}  # 掏的錢接在效果最前面：江湖紀錄先寫「銀兩 -10」
    assert outcomes.paid(LABOR) is LABOR.effect


def test_a_combat_outcome_fights_like_a_fixed_choice():
    choice = outcomes.as_choice(CHASE)
    assert (choice.combat, choice.effect, choice.fail_effect) == ("dipi", CHASE.effect, CHASE.fail_effect)


def test_the_options_show_only_ids_and_tags():
    """欄位表 1.3 的 options[].outcomes：給畫面寫「可能的走向」，不給後果的數字。"""
    assert outcomes.tags(ALL) == [{"id": o.id, "tag": o.tag} for o in ALL]


@pytest.mark.parametrize("points, used, credited", [(4, 0, 4), (4, 10, 2), (4, 12, 0), (0, 3, 0), (6, 13, 0)])
def test_the_daily_contribution_cap(points, used, credited):
    assert outcomes.contribution_room(points, used) == credited
    assert outcomes.DEED_CONTRIBUTION_CAP == 12
