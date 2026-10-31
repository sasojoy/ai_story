"""OllamaClient 送給 Ollama 的參數（2026-10-03 實測換 gemma4:26b：要關掉思考、拿掉重複懲罰、拉長常駐時間）。"""
import pytest
import requests
from pydantic import BaseModel

from tianxia.battle_instance import SuccessRateJudgment
from tianxia.engine import Game
from tianxia.ollama_client import OllamaClient, _ensure_required_present
import json
import random
from tianxia import companion_agent, event_llm, fight_llm, flavor, naming
from tianxia.battle_instance import GambleVerdict, SuccessRateJudgment, assess_gamble
from tianxia.fight_llm import FightRequest
from tianxia.models import BattleAct, BattleOption
from tianxia.ollama_client import InLockClient, ModelBudget, ModelSpokeKana, OllamaClient, has_kana

REAL_CHAT_STRUCTURED = OllamaClient.chat_structured  # 匯入時抓：conftest 的 autouse 之後會換成「連不上」


def test_defaults_keep_the_old_payload_and_send_no_think_field():
    payload = OllamaClient()._build_payload([{"role": "user", "content": "hi"}], 0.8)
    assert "think" not in payload
    assert payload["keep_alive"] == "30m"
    assert payload["options"]["repeat_penalty"] == 1.18
    assert payload["options"]["presence_penalty"] == 0.3
    assert payload["options"]["frequency_penalty"] == 0.3


def test_think_keep_alive_and_penalties_are_configurable():
    client = OllamaClient(think=False, keep_alive="12h", repeat_penalty=1.0, presence_penalty=0.0, frequency_penalty=0.0)
    payload = client._build_payload([{"role": "user", "content": "hi"}], 0.8)
    assert payload["think"] is False
    assert payload["keep_alive"] == "12h"
    assert payload["options"]["repeat_penalty"] == 1.0
    assert payload["options"]["presence_penalty"] == 0.0
    assert payload["options"]["frequency_penalty"] == 0.0


def _configured(content):
    """八個參數都設成跟 OllamaClient 的預設、也跟彼此不同的值（預設是 localhost、qwen2.5:14b、120、None、30m、1.18、0.3、0.3）：
    漏帶任何一個，client 就會悄悄變回預設。回傳預期的欄位值。"""
    cfg = content.config
    cfg.ollama_url, cfg.ollama_model, cfg.ollama_timeout = "http://gpu-box:11434", "gemma4:26b", 77
    cfg.ollama_think, cfg.ollama_keep_alive = False, "12h"
    cfg.ollama_repeat_penalty, cfg.ollama_presence_penalty, cfg.ollama_frequency_penalty = 1.0, 0.0, 0.1
    return {
        "base_url": "http://gpu-box:11434", "model": "gemma4:26b", "timeout": 77, "think": False, "keep_alive": "12h",
        "repeat_penalty": 1.0, "presence_penalty": 0.0, "frequency_penalty": 0.1,
    }


def test_a_client_from_the_config_carries_every_configured_parameter(content):
    """OllamaClient.from_config（假人程式用）：照預期的值逐一比，不是跟另一個也走同一個函式的 client 比。"""
    expected = _configured(content)
    made = OllamaClient.from_config(content.config)
    assert {field: getattr(made, field) for field in expected} == expected
    payload = made._build_payload([{"role": "user", "content": "hi"}], 0.8)
    assert payload["options"]["presence_penalty"] == 0.0 and payload["options"]["frequency_penalty"] == 0.1


def test_the_games_client_carries_every_configured_parameter_too(content):
    """Game 與假人程式用同一套參數：Game 的 client 也照同樣預期的值，一個不少。"""
    expected = _configured(content)
    client = Game.new(content, "測試").client
    assert {field: getattr(client, field) for field in expected} == expected


@pytest.mark.smoke
def test_the_game_builds_its_client_from_the_config(content):
    cfg = content.config
    cfg.ollama_model = "gemma4:26b"
    cfg.ollama_think = False
    cfg.ollama_keep_alive = "12h"
    cfg.ollama_repeat_penalty = 1.0
    cfg.ollama_presence_penalty = 0.0
    cfg.ollama_frequency_penalty = 0.0
    payload = Game.new(content, "測試").client._build_payload([{"role": "user", "content": "hi"}], 0.8)
    assert payload["model"] == "gemma4:26b"
    assert payload["think"] is False and payload["keep_alive"] == "12h"
    assert payload["options"]["repeat_penalty"] == 1.0


# ── 截斷檢查（required_fields）：falsy 不等於缺欄位 ──────────────────────


def test_a_success_rate_of_zero_is_a_real_answer_not_a_truncation():
    """防灌水的提示詞要模型對「我必定成功」這類寫法給 0~10，實測 gemma4:26b 就是回 0
    （done_reason=stop、JSON 完整）。以前用 `not data.get(...)` 判斷，0 會被當成截斷丟掉，
    重試再拿到 0 再丟一次，最後退回保底 40——比正常評出來的低分還高。"""
    _ensure_required_present({"success_rate": 0, "reasoning": "在對遊戲下指令"}, SuccessRateJudgment, ["success_rate"])


def test_a_missing_or_empty_field_still_counts_as_truncated():
    for data in ({}, {"success_rate": None}, {"reasoning": "只有理由"}):
        with pytest.raises(ValueError, match="success_rate"):
            _ensure_required_present(data, SuccessRateJudgment, ["success_rate"])


def test_an_empty_list_or_string_still_counts_as_truncated():
    """原本的用意（ai_story 的 options 坑）要留著：有 default_factory 的欄位空著就是截斷。"""
    class Reply(BaseModel):
        options: list[str] = []
        name: str = ""

    for field in ("options", "name"):
        with pytest.raises(ValueError, match=field):
            _ensure_required_present({"options": [], "name": ""}, Reply, [field])
    _ensure_required_present({"options": ["甲"], "name": "鑄韌拳"}, Reply, ["options", "name"])


# ── 模型沒裝（Ollama 回 404）：錯誤訊息照字寫，三個地方都是同一句 ──────────────────────


class _Reply:
    """假的 HTTP 回應：status 400 以上時 raise_for_status 丟 HTTPError，跟 requests 一樣。"""

    def __init__(self, status, content=""):
        self.status_code, self._content = status, content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)

    def json(self):
        return {"message": {"content": self._content}}


def _first_reply_is_404():
    yield _Reply(404)


def _the_post_raises_an_http_404():
    raise requests.HTTPError("404", response=_Reply(404))
    yield  # 讓它也是個產生器：第一趟就丟例外


def _the_retry_gets_404():
    yield _Reply(200, "這不是 JSON")  # 第一趟格式不對，重問
    yield _Reply(404)


@pytest.mark.parametrize("replies", [_first_reply_is_404, _the_post_raises_an_http_404, _the_retry_gets_404],
                         ids=["first-post", "http-error", "retry"])
def test_a_missing_model_is_reported_in_the_same_words_at_each_of_the_three_places(monkeypatch, replies):
    """模型沒裝時主控台看到的那一句（整併第 8 區把三份合成 _model_missing，最終審查 M5 要釘住字）：
    第一趟就回 404、送出時就丟 404 的 HTTPError、格式不對重問那一趟回 404，都是這一句，模型名字照 client 的。"""
    stream = replies()

    def post(url, json=None, timeout=None):
        return next(stream)

    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(OllamaClient, "chat_structured", REAL_CHAT_STRUCTURED)
    client = OllamaClient(model="gemma4:26b")
    with pytest.raises(RuntimeError) as raised:
        client.chat_structured([{"role": "user", "content": "取個名字"}], SuccessRateJudgment)
    assert str(raised.value) == "Ollama 回傳 404：模型 'gemma4:26b' 未找到，請先 `ollama pull gemma4:26b`。"


def test_a_blank_string_counts_as_truncated():
    """只有空白的必填字串（人物對話的 narrative 回 "  "）跟空的一樣當截斷，重問一趟（Joy 2026-10-22「Npc不會講話了？」）。"""
    class Reply(BaseModel):
        narrative: str = ""

    with pytest.raises(ValueError, match="narrative"):
        _ensure_required_present({"narrative": " \n "}, Reply, ["narrative"])


# ── 原 test_fb104_kana.py（整檔搬進來） ──
# FB-104（QA 7cc1fd7，2026-10-08）：董卓的回話裡出現「這酒い好！」——模型文字夾了日文假名，zh.to_traditional 只轉簡繁、補異體字，
# 假名原樣上了畫面與江湖紀錄。
#
# 現在模型自己寫的假名只讓「那一段字」失敗（ollama_client.ModelSpokeKana／screen_kana；審查 I1 縮小過）：
# - chat_text 的那一段：當成這一次呼叫失敗，呼叫端走原本的退路（點綴不插句、潤色用固定文字）；
# - chat_structured：主體欄位（對話的敘事與選項、取的名字……）夾了就整個失敗——會重問的（鎖外）重問一趟、提醒用繁體中文；
#   其他欄位（放手一搏的兩版劇情、大場面的兩版過程、名字的說明）只清掉那一欄、走固定文字，成功率與優勢照用、不重問；
#   不上畫面的欄位（reasoning）不看；
# - 玩家自己寫的做法、名號裡的假名，模型照抄不算。
# 不偷偷從句子中間拿掉假名（CLAUDE.md「保底值會把模型壞了偽裝成模型給了中庸的答案」）。
# 模型有回、只是那一句不能用：鎖內的額度不因此用完、全服斷路器不打開。對話失敗跟以前叫不動模型一模一樣（不扣體力、這輪取消）。
#
# 假的模型：把 requests.post 換掉，回一段夾了假名的字；不連任何網路。

REAL_CHAT_TEXT = OllamaClient.chat_text


KANA_LINE = "這酒い好！既然你想聽……"


class _Reply_fb104:
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
        return _Reply_fb104(state["replies"].pop(0))

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


# ── 審查 I1：數字留著；玩家自己寫的假名、不顯示的欄位不算 ─────────────────────
# 評成功率、大場面判讀這種「數字＋幾段字」的回答：哪一段字夾了模型自己的假名，就只有那一段走固定文字，數字與其他段照用、不重問
# （以前整個回答作廢、退回保底 40——CLAUDE.md「保底值會把模型壞了偽裝成模型給了中庸的答案」）。玩家自己寫的做法、名號裡的假名，
# 模型照抄不算（假名在送出去的字裡就有）；reasoning 這種不上畫面的欄位不看。對話的敘事、選項、名字本身才是那一段字：照舊整個失敗。

def _judgment(**fields):
    return json.dumps({"success_rate": 0, "reasoning": "", "win": "", "lose": "", **fields}, ensure_ascii=False)


EVENT = type("E", (), {"title": "茶館", "text": "說書人拍了一下醒木。"})()


ACT = BattleAct(id="a1", title="夜襲", text="營火忽明忽暗。", goal="拖住敵軍", options=[BattleOption(text="穩守", tag="hold")])


def test_kana_in_the_players_own_answer_keeps_the_models_rate(model):
    """隨口應對寫「ああ」：模型評 3、reasoning 照抄「ああ」——用 3，不是保底 40，也不重問。"""
    model["replies"] = [_judgment(success_rate=3, reasoning="「ああ」只是一聲，不是做法。")]
    assert event_llm.assess_event_success_rate(OllamaClient(), EVENT, "ああ") == 3
    assert len(model["sent"]) == 1


def test_kana_in_a_field_nobody_sees_keeps_the_rate(model):
    model["replies"] = [_judgment(success_rate=12, reasoning="これは無理")]
    assert event_llm.assess_event_success_rate(OllamaClient(), EVENT, "拍桌子") == 12
    assert len(model["sent"]) == 1


def test_a_hidden_field_is_left_as_the_model_wrote_it(model):
    """不上畫面的欄位連看都不看（不清掉、不算數）：reasoning 照模型寫的留著。"""
    model["replies"] = [_judgment(success_rate=12, reasoning="これは無理")]
    reply = OllamaClient().chat_structured([{"role": "user", "content": "評"}], SuccessRateJudgment, required_fields=["success_rate"])
    assert (reply.success_rate, reply.reasoning) == (12, "これは無理")


def test_only_the_kana_item_of_a_list_is_cleared_and_the_order_kept(model):
    """清單裡只清掉夾了假名的那一項、換成空字串，順序不動：對話的選項與 tag 一一對應，少一項就對錯人。"""
    turn = json.dumps({"narrative": "「坐吧。」", "options": ["閒聊幾句", "就此告辭"], "option_tags": ["尋常寒暄", "いい"]}, ensure_ascii=False)
    model["replies"] = [turn]
    got = OllamaClient().chat_structured([{"role": "user", "content": "談"}], companion_agent.CompanionTurn, required_fields=["options"])
    assert got.options == ["閒聊幾句", "就此告辭"] and got.option_tags == ["尋常寒暄", ""] and len(model["sent"]) == 1


def test_a_player_named_sakura_keeps_the_gamble_rate_and_both_stories(model):
    """名號是「さくら」：兩版劇情照提示以名號開頭——72 照用、兩版都播。"""
    win, lose = "さくら大喊一聲，敵軍嚇得後退。", "さくら喊破了嗓子，被人絆了一跤。"
    model["replies"] = [_judgment(success_rate=72, reasoning="さくら的喊聲或許有用", win=win, lose=lose)]
    assert assess_gamble(OllamaClient(), ACT, "官軍", "大喊一聲衝上去", name="さくら") == GambleVerdict(72, win, lose)
    assert len(model["sent"]) == 1


def test_real_kana_in_a_story_drops_only_that_story(model):
    """模型自己寫了假名（「さくらは」不是名號）：那一版用固定句（空字串），成功率與另一版照用。"""
    lose = "さくら喊破了嗓子，被人絆了一跤。"
    model["replies"] = [_judgment(success_rate=72, win="さくらは大喊一聲。", lose=lose)]
    assert assess_gamble(OllamaClient(), ACT, "官軍", "大喊一聲衝上去", name="さくら") == GambleVerdict(72, "", lose)
    assert len(model["sent"]) == 1


def test_a_big_fight_keeps_its_advantage_when_one_account_has_kana(model):
    """大場面判讀：名號裡的假名照抄可以；模型自己寫了假名的那一版走範本回合（空字串），優勢照用。"""
    request = FightRequest(option_id="act:train", squad_id="s", location="town", battle_seq=1, event=None,
                           ours=["さくら：赤手空拳"], theirs="山賊頭目：屬剛・難度 120")
    winning, losing = "さくら一拳打在頭目胸口，頭目退了三步。", "さくらは倒れた。"
    model["replies"] = [json.dumps({"advantage": 9, "winning": winning, "losing": losing}, ensure_ascii=False)]
    assert fight_llm.judge(OllamaClient(), request, 15) == fight_llm.Judgment(advantage=9, winning=winning, losing="")
    assert len(model["sent"]) == 1


def test_a_dialogue_may_say_the_players_kana_name_but_not_speak_kana(model):
    messages = [{"role": "user", "content": "さくら走上前來拱手。"}]
    model["replies"] = [_turn("「さくら？好怪的名號。坐吧。」")]
    assert companion_agent.generate_turn(OllamaClient(), messages).narrative == "「さくら？好怪的名號。坐吧。」"
    model["replies"] = [_turn("「さくらさん，坐吧。」"), _turn("「さくらさん，坐吧。」")]  # 「さくらさん」是模型自己加的
    with pytest.raises(companion_agent.DialogueUnavailable):
        companion_agent.generate_turn(OllamaClient(), messages)


def test_the_polish_may_quote_the_players_kana(model):
    model["replies"] = ["你只「ああ」了一聲，滿座茶客都轉過頭來。"]
    assert event_llm.narrate_event_gamble(OllamaClient(), EVENT, "ああ", False, "茶客都看過來。") == "你只「ああ」了一聲，滿座茶客都轉過頭來。"


def test_a_name_reply_keeps_its_name_and_drops_a_kana_description(model):
    model["replies"] = [json.dumps({"name": "斷浪拳", "description": "これは拳"}, ensure_ascii=False)]
    reply = OllamaClient().chat_structured([{"role": "user", "content": "取名"}], naming.NameReply, required_fields=["name"])
    assert (reply.name, reply.description) == ("斷浪拳", "") and len(model["sent"]) == 1
    model["replies"] = [json.dumps({"name": "斷いの拳", "description": "一拳"}, ensure_ascii=False)] * 2  # 名字本身：照舊失敗
    with pytest.raises(ModelSpokeKana):
        OllamaClient().chat_structured([{"role": "user", "content": "取名"}], naming.NameReply, required_fields=["name"])
