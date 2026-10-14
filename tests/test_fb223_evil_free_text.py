"""FB-223（回饋單丙批 QA，2026-10-14，模型 gemma4:26b）：成算一成不到的惡行擲中，潤色照字面寫惡行、接上善果、還給善名。

荒丘「壕中逃卒」寫「原地挖坑把他埋了」（成算一成不到）擲中：潤色寫活埋，後面接內容寫好的「這條命是你給的」，善名 +2。

企劃者 2026-10-14 選「模型另外判善惡」，PM 定的做法：
- 評分那一次（event_llm.judge_event_gamble）順便判這個做法本身是「善」「惡」「中」；清單外的值、缺欄位、模型叫不動一律當「中」，
  引擎拿到再驗一次（event_llm.moral_of）。
- 只有「惡」而且擲中了才換（rules.evil_success）：加的善名換成同樣多的惡名、扣惡名的拿掉、情誼的增加拿掉，其他獎勵照給；
  內容寫好的結果句不接，潤色照惡行寫（narrate_event_gamble 的 evil），沒寫成用 rules.EVIL_DONE 收尾；行狀照實寫。
- 「善」「中」、或「惡」沒擲中：一個字都不變。不碰 Game.rng 的序列。

假的模型：mock 的 client，或把 requests.post 換掉走真的 OllamaClient.chat_structured（tests/test_fb104_kana.py 的做法）；
不連任何網路，也不碰 11434。"""
from __future__ import annotations

import json
import random
from unittest import mock

import pytest
import requests

from conftest import FixedRandom
from tianxia import event_llm, rules
from tianxia.battle_instance import DEFAULT_FREE_TEXT_SUCCESS_RATE, SuccessRateJudgment
from tianxia.engine import EVIL_ANNAL, Game
from tianxia.models import Effect, FactionDef, FreeTextChoice
from tianxia.ollama_client import OllamaClient

REAL_CHAT_STRUCTURED = OllamaClient.chat_structured  # 匯入時抓：conftest 的 autouse 之後會換成「連不上」
NOWHERE = "http://127.0.0.1:9"  # 萬一 requests.post 沒換到，也不會碰到模型的 port

GOOD_TEXT = "那郡兵總算有了著落，他啞著嗓子說，這條命是你給的。"
GAMBLE = FreeTextChoice(
    prompt="自己想辦法安頓他", stat="str", by="self",
    effect=Effect(
        text=GOOD_TEXT, stats={"good": 2, "evil": -1, "fame": 1, "silver": 10},
        affinity={"scholar": 5, "thug": -3}, rumor="有人在荒丘救了一個逃卒。",  # 傳聞不寫名號：兩個角色比對時才一樣
    ),
    fail_effect=Effect(text="他嚇得爬出壕溝跑了。", stamina=-10),
)
DEED = "原地挖坑把他埋了"
STORY = "你一言不發地揮鏟掘土，把那哀求的郡兵推進坑裡填平，荒丘上只剩一片新翻的黃土。"


@pytest.fixture
def make(content, world):
    """測試內容的「醉漢」事件掛上這個隨口應對；劇本補兩個陣營（tests/test_ranger.py 的做法：散人加的善名惡名才記遊俠名號的帳），
    打開行狀。make(rng) 開一個停在這則事件上的角色（每次換一個名號），rng 在開好之後才換上（擲骰從同一個地方開始）。"""
    content.scenario.factions = [
        FactionDef(id="guan", name="官軍", join_at=["town"]),
        FactionDef(id="huang", name="黃巾", join_at=["lake"]),
    ]
    content.config.biography.enabled = True
    content.events["drunk"].free_text = GAMBLE
    names = iter("甲乙丙丁")

    def new(rng):
        g = Game.new(content, next(names), rng=random.Random(0), world=world)
        g.client = None
        g.state.pending_event = "drunk"
        g.state.player.affinities.update({"scholar": 20, "thug": 20})
        g.state.player.stats.update({"good": 3, "evil": 4})
        g.rng = rng
        return g

    return new


def _answer(game, moral, llm_rate=3):
    return game.answer_event(game.free_text_request(DEED), llm_rate, moral)


def _snapshot(game):
    p = game.state.player
    entry = game.state.journal[0]
    return {
        "stats": dict(p.stats), "affinities": dict(p.affinities), "ranger": (p.ranger_good, p.ranger_evil),
        "lines": list(entry.lines), "changes": list(entry.changes), "tag": entry.tag, "title": entry.title,
        "annals": [(a.text, a.quote) for a in p.annals], "rng": game.rng.getstate(),
        "outcome": game.last_gamble.model_dump(exclude={"time"}),
    }


# ── 判惡、擲中：善名換惡名、情誼拿掉、不接結果句 ─────────────────────


def test_an_evil_deed_that_lands_earns_infamy_instead_of_the_good_ending(make):
    g = make(FixedRandom(0.0))  # 擲 0：成算一成不到也成
    p = g.state.player
    silver, fame = p.stats.get("silver", 0), p.stats.get("fame", 0)
    _answer(g, "惡")
    assert p.stats["good"] == 3  # 善名一點都沒加
    assert p.stats["evil"] == 4 + 2  # 加的善名換成同樣多的惡名；扣惡名的那一點拿掉了
    assert (p.stats["silver"], p.stats["fame"]) == (silver + 10, fame + 1)  # 其他獎勵照給
    assert p.affinities == {"scholar": 20, "thug": 17}  # 情誼的增加拿掉，扣的照扣
    assert (p.ranger_good, p.ranger_evil) == (0, 2)  # 遊俠名號的帳照實際動了多少記：散人走寇那一條
    entry = g.state.journal[0]
    assert entry.title == "醉漢・隨口應對" and entry.tag == "成功"
    assert entry.lines[0].startswith(f"你：「{DEED}」（成算一成不到）")  # 照舊寫成算
    assert entry.lines[1] == rules.EVIL_DONE and GOOD_TEXT not in entry.lines  # 內容寫好的善果不接
    assert not any("救了一個逃卒" in line for line in entry.lines)  # 照善果寫的傳聞也拿掉
    assert "惡名 +2" in entry.changes and not any(c.startswith("善名") for c in entry.changes)  # 得失照實際給的寫
    assert not any("情誼 +" in c for c in entry.changes)
    assert g.last_gamble.evil is True and g.last_gamble.effect_text == rules.EVIL_DONE
    said = [a.text for a in p.annals if a.quote == DEED]
    assert said == ["遇上【醉漢】，隨口應對" + EVIL_ANNAL]  # 行狀照實寫


def test_an_evil_deed_that_misses_is_an_ordinary_failure(make):
    evil, neutral = make(FixedRandom(0.99)), make(FixedRandom(0.99))
    _answer(evil, "惡")
    _answer(neutral, None)
    assert _snapshot(evil) == _snapshot(neutral)  # 照 fail_effect，一個字都不變
    assert evil.state.journal[0].tag == "失敗" and "他嚇得爬出壕溝跑了。" in evil.state.journal[0].lines
    assert evil.last_gamble.evil is False


@pytest.mark.parametrize("moral", ["善", "中", "", "大惡", "evil", 3, None])
@pytest.mark.parametrize("roll", [0.0, 0.99], ids=["landed", "missed"])
def test_good_neutral_missing_or_odd_judgments_change_nothing(make, moral, roll):
    """判善、判中、沒判（None：舊的呼叫端、腳本）、清單外的怪值：跟沒有這一欄時一模一樣（成功照內容的善果、善名照加）。"""
    judged, plain = make(FixedRandom(roll)), make(FixedRandom(roll))
    judged.answer_event(judged.free_text_request(DEED), 3, moral)
    plain.answer_event(plain.free_text_request(DEED), 3)
    assert _snapshot(judged) == _snapshot(plain)
    if roll == 0.0:
        assert judged.state.player.stats["good"] == 3 + 2 and GOOD_TEXT in judged.state.journal[0].lines


def test_the_moral_does_not_touch_the_engine_dice(make):
    """善惡不擲骰：同一個種子，判惡與判中擲完之後 Game.rng 停在同一個地方。"""
    evil, neutral = make(random.Random(1)), make(random.Random(1))
    _answer(evil, "惡", llm_rate=60)
    _answer(neutral, "中", llm_rate=60)
    assert evil.last_gamble.success is neutral.last_gamble.success is True
    assert evil.rng.getstate() == neutral.rng.getstate()
    assert evil.last_gamble.evil and not neutral.last_gamble.evil


def test_without_a_judged_rate_the_engine_judges_in_the_lock(make, monkeypatch):
    """沒給成功率（直接呼叫的測試、腳本）：鎖內評的那一次（_quick_client）也拿到善惡。"""
    g = make(FixedRandom(0.0))
    g.client = OllamaClient(base_url=NOWHERE)
    judged = event_llm.EventJudgment(success_rate=2, reasoning="活埋求救的人", moral="惡")
    monkeypatch.setattr(OllamaClient, "chat_structured", lambda self, *args, **kwargs: judged)
    g.answer_event(g.free_text_request(DEED))
    assert g.last_gamble.evil is True and g.state.player.stats["good"] == 3


# ── 潤色：惡行成了，潤色那一段就是結果；沒寫成用固定那一句 ───────────────


def test_the_evil_narration_replaces_the_fixed_line(make):
    g = make(FixedRandom(0.0))
    _answer(g, "惡")
    before = list(g.state.journal[0].lines)
    g.add_gamble_narration(g.last_gamble, STORY)
    lines = g.state.journal[0].lines
    assert lines[0].startswith(f"你：「{DEED}」") and lines[1] == STORY
    assert rules.EVIL_DONE not in lines and GOOD_TEXT not in lines
    assert [x for x in lines if x != STORY] == [x for x in before if x != rules.EVIL_DONE]


@pytest.mark.parametrize("narration", [None, ""])
def test_without_a_narration_the_fixed_line_closes_it(make, narration):
    g = make(FixedRandom(0.0))
    _answer(g, "惡")
    before = list(g.state.journal[0].lines)
    g.add_gamble_narration(g.last_gamble, narration)
    assert g.state.journal[0].lines == before and rules.EVIL_DONE in before


def test_the_evil_narration_prompt_tells_the_model_and_hides_the_good_ending():
    event = mock.Mock(title="壕中逃卒", text="舊營壕裡蜷著一個郡兵，只求一口水。")
    client = mock.Mock()
    client.chat_text.return_value = STORY
    assert event_llm.narrate_event_gamble(client, event, DEED, True, rules.EVIL_DONE, evil=True) == STORY
    system, user = (m["content"] for m in client.chat_text.call_args.args[0])
    assert "惡行，而且成了" in system and "感激" in system and "善報" in system
    assert "這是一件惡行，而且成了" in user and DEED in user
    assert rules.EVIL_DONE not in user and "結果文字" not in user  # 沒有句子要接，也不給模型看
    assert client.chat_text.call_args.kwargs["num_predict"] == event_llm.NARRATE_EVIL_NUM_PREDICT
    # 不是惡行：提示照舊
    event_llm.narrate_event_gamble(client, event, DEED, True, GOOD_TEXT)
    system, user = (m["content"] for m in client.chat_text.call_args.args[0])
    assert "惡行" not in system and f"結果文字（會接在你寫的句子後面）：{GOOD_TEXT}" in user
    assert client.chat_text.call_args.kwargs["num_predict"] == event_llm.NARRATE_NUM_PREDICT


# ── 評分那一次順便判善惡 ───────────────────────────────────


def test_the_scoring_prompt_asks_for_the_moral_and_defines_evil():
    event = mock.Mock(title="壕中逃卒", text="舊營壕裡蜷著一個郡兵。")
    client = mock.Mock()
    client.chat_structured.return_value = event_llm.EventJudgment(success_rate=3, moral="惡")
    assert event_llm.judge_event_gamble(client, event, DEED) == event_llm.EventVerdict(3, "惡")
    args, kwargs = client.chat_structured.call_args
    system, user = (m["content"] for m in args[0])
    assert args[1] is event_llm.EventJudgment and kwargs["required_fields"] == ["success_rate"]  # 善惡不是必填：缺了不拖垮成功率
    assert "moral" in system and "「善」「惡」「中」" in system
    for word in ("傷害無辜", "殺人滅口", "搶奪弱者", "欺凌", "背信"):
        assert word in system
    assert "不看它成不成" in system and "不影響 success_rate" in system
    assert "moral" in user
    schema = event_llm.EventJudgment.model_json_schema()
    assert schema["properties"]["moral"]["enum"] == ["善", "惡", "中"]
    assert list(schema["properties"])[:2] == ["success_rate", "reasoning"]  # 先評分、再判善惡
    assert "description" not in schema  # 寫給開發者的說明不送給模型
    assert "moral" not in SuccessRateJudgment.model_json_schema()["properties"]  # 決戰的放手一搏不多這一欄


@pytest.mark.parametrize("reply, verdict", [
    (event_llm.EventJudgment(success_rate=3, moral="惡"), (3, "惡")),
    (event_llm.EventJudgment(success_rate=55, moral="善"), (55, "善")),
    (event_llm.EventJudgment(success_rate=20, moral=" 惡 "), (20, "惡")),
    (event_llm.EventJudgment(success_rate=20, moral="邪"), (20, "中")),
    (event_llm.EventJudgment(success_rate=20), (20, "中")),
    (SuccessRateJudgment(success_rate=20), (20, "中")),  # 沒有這一欄的回答
], ids=["evil", "good", "padded", "odd", "default", "no-field"])
def test_the_moral_is_read_strictly(reply, verdict):
    client = mock.Mock()
    client.chat_structured.return_value = reply
    assert tuple(event_llm.judge_event_gamble(client, mock.Mock(title="t", text="x"), DEED)) == verdict


def test_no_model_means_forty_and_neutral():
    event = mock.Mock(title="t", text="x")
    assert event_llm.judge_event_gamble(None, event, DEED) == (DEFAULT_FREE_TEXT_SUCCESS_RATE, "中")
    client = mock.Mock()
    client.chat_structured.side_effect = RuntimeError("連不上")
    assert event_llm.judge_event_gamble(client, event, DEED) == (DEFAULT_FREE_TEXT_SUCCESS_RATE, "中")
    assert event_llm.assess_event_success_rate(client, event, DEED) == DEFAULT_FREE_TEXT_SUCCESS_RATE


class _Reply:
    def __init__(self, content):
        self._content = content
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {"message": {"content": self._content}}


@pytest.mark.parametrize("body, verdict", [
    ({"success_rate": 3, "reasoning": "活埋求救的人", "moral": "惡"}, (3, "惡")),
    ({"success_rate": 3, "reasoning": "活埋求救的人"}, (3, "中")),  # 缺欄位
    ({"success_rate": 3, "reasoning": "活埋求救的人", "moral": "大惡不赦"}, (3, "中")),  # 清單外：成功率照用，不是保底 40
    ({"success_rate": 3, "reasoning": "活埋求救的人", "moral": None}, (3, "中")),
    ({"success_rate": 3, "reasoning": "活埋求救的人", "moral": ["惡"]}, (3, "中")),
], ids=["evil", "missing", "odd", "null", "list"])
def test_the_real_client_reads_the_moral_without_failing_the_rate(monkeypatch, body, verdict):
    """走真的 OllamaClient.chat_structured（假的 requests.post）：善惡缺了、寫怪值都不會讓整個回答驗不過、退回保底 40。"""
    sent = []

    def post(url, **kwargs):
        sent.append(kwargs["json"])
        return _Reply(json.dumps(body, ensure_ascii=False))

    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(OllamaClient, "chat_structured", REAL_CHAT_STRUCTURED)
    got = event_llm.judge_event_gamble(OllamaClient(base_url=NOWHERE), mock.Mock(title="壕中逃卒", text="x"), DEED)
    assert tuple(got) == verdict and len(sent) == 1  # 一趟就讀進來了，沒有重問
    assert sent[0]["format"]["properties"]["moral"]["enum"] == ["善", "惡", "中"]


# ── rules.evil_success ────────────────────────────────────


def test_evil_success_swaps_the_good_for_infamy_and_keeps_the_rest():
    effect = Effect(
        text=GOOD_TEXT, stats={"good": 2, "fame": 1, "evil": -3, "xinde": 4}, stamina=-5, affinity={"scholar": 5, "thug": -2},
        materials={"iron": 1}, marks={"town:棚屋": 1}, rumor="{name}救了人。", chronicle="{name}救了人。",
    )
    turned = rules.evil_success(effect)
    assert turned.text == rules.EVIL_DONE
    assert list(turned.stats.items()) == [("evil", 2), ("fame", 1), ("xinde", 4)]  # 順序照舊：得失照這個順序寫
    assert turned.affinity == {"thug": -2}
    assert (turned.rumor, turned.chronicle) == ("", "")
    assert (turned.stamina, turned.materials, turned.marks) == (-5, {"iron": 1}, {"town:棚屋": 1})
    assert effect.stats["good"] == 2 and effect.text == GOOD_TEXT  # 內容那一份不動
    # 扣善名的照扣；加惡名的照加（跟善名換來的合起來）
    assert rules.evil_success(Effect(stats={"good": -1, "evil": 1})).stats == {"good": -1, "evil": 1}
    assert rules.evil_success(Effect(stats={"evil": 1, "good": 2})).stats == {"evil": 3}
