"""行動鎖內的模型呼叫都有 15 秒的上限（Config.in_lock_model_timeout）。

每個玩家的行動都在 WorldStateStore.action_lock() 裡做（SQLite 的 BEGIN IMMEDIATE），鎖拿著的時候全服玩家與假人都在等。
鎖外的路徑（對話備料、開爐取名、隨口應對的評分與潤色）有自己的做法，鎖內還有幾處會叫模型：
大事潤色、決戰回合敘事、重複事件與重遊的點綴句、決戰自訂行動的評分、鎖內才備料的對話與記憶整理、鎖內才取名的開爐。
它們全都拿 Game._quick_client() 給的短逾時複本；模型慢到沒回（逾時）或根本沒有 client（伺服器假人）時，
每一處都退回固定的文字，不丟例外。

這裡把 OllamaClient 的兩個呼叫換成「記下當下那個 client 的 timeout、然後丟逾時」，一條路徑一條路徑地跑，
所以量的是真正會送出去的逾時，不是呼叫端傳了什麼。
"""
import random
from unittest import mock

import pytest
import requests

from conftest import at, walk_to
from test_engine import _install_battle_def, _install_battle_def_with_free_text, _join_and_open
from tianxia import battle_instance, companion_agent, fusion, naming
from tianxia.engine import FreeTextRequest, Game
from tianxia.models import Config, Effect, FreeTextChoice
from tianxia.ollama_client import OllamaClient

REAL_CHAT_STRUCTURED = OllamaClient.chat_structured  # 匯入時抓：conftest 的 autouse 之後會換成「連不上」，重問的測試要真的
PRODUCTION_TIMEOUT = 120  # Config.ollama_timeout 的預設：鎖外路徑照舊用這個
FAKE_TURN = companion_agent.CompanionTurn(
    narrative="他點了點頭。", options=["閒聊幾句", "就此告辭"], option_tags=["尋常寒暄", "尋常寒暄"],
)
GAMBLE = FreeTextChoice(
    prompt="自己想辦法……", stat="str", by="self",
    effect=Effect(text="醉漢被你唬住了。"), fail_effect=Effect(text="醉漢一拳揮來。"),
)


class ModelSpy:
    """替換 OllamaClient 的 chat_text／chat_structured：記下每一次呼叫當下 client.timeout 與 client.retry，再丟 requests 的逾時
    （模型太慢）。ok=True 時改成回一句話（成功），拿來對照「失敗才讓後面的呼叫不送」。"""

    def __init__(self, monkeypatch, ok: bool = False):
        self.calls: list[tuple[str, float]] = []
        self.retries: list[bool] = []

        def chat_text(client, messages, **kwargs):
            self.calls.append(("chat_text", client.timeout))
            self.retries.append(client.retry)
            if ok:
                return "山風捲過旌旗。"
            raise requests.exceptions.ReadTimeout("模型太慢，逾時了")

        def chat_structured(client, messages, response_model, **kwargs):
            self.calls.append(("chat_structured", client.timeout))
            self.retries.append(client.retry)
            raise requests.exceptions.ReadTimeout("模型太慢，逾時了")

        monkeypatch.setattr(OllamaClient, "chat_text", chat_text)
        monkeypatch.setattr(OllamaClient, "chat_structured", chat_structured)

    @property
    def timeouts(self) -> list[float]:
        return [timeout for _, timeout in self.calls]


@pytest.fixture
def spy(monkeypatch):
    return ModelSpy(monkeypatch)


@pytest.fixture
def slow(game, spy):
    """正式環境的樣子：client 的逾時是 120 秒（測試內容把它設成 3，這裡設回來，才分得出「短複本」與「原本那個」）。"""
    game.client.timeout = PRODUCTION_TIMEOUT
    return game


# ── 鎖內的每一處模型呼叫：一條路徑一個情境 ───────────────────────────
# 情境自己斷言「退回固定文字、沒有丟例外」：逾時與沒有 client 兩種情況退回的東西一模一樣，所以同一份斷言兩邊都用。


def _a_threshold_through_a_choice(game):
    game.state.world.trends["kou"] = 50  # 跨過「水寇封江」
    msgs = game.choose("act:rest")
    assert "blocked" in game.state.world.flags
    assert [m for m in msgs if "水寇封江" in m] == ["【江湖大事】水寇封江！"]  # 沒有潤色句，原文照給


def _a_threshold_through_admin_fire(game):
    game.content.config.admins = ["沈浪"]
    msgs = game.admin_fire("kou50")
    assert any("水寇封江" in m for m in msgs) and "blocked" in game.state.world.flags


def _a_threshold_through_admin_push_trend(game):
    game.content.config.admins = ["沈浪"]
    msgs = game.admin_push_trend("kou", 30)
    assert any("水寇封江" in m for m in msgs) and "blocked" in game.state.world.flags


def _a_threshold_through_admin_set_trend(game):
    game.content.config.admins = ["沈浪"]
    msgs = game.admin_set_trend("kou", 60)
    assert any("水寇封江" in m for m in msgs) and "blocked" in game.state.world.flags


def _a_threshold_through_a_free_text_answer(game):
    game.content.events["drunk"].free_text = GAMBLE
    game.state.pending_event = "drunk"
    game.state.world.trends["kou"] = 50
    msgs = game.answer_event(FreeTextRequest(event_id="drunk", text="大喊官兵來了"), llm_rate=50)
    assert any("你：「大喊官兵來了」" in m for m in msgs) and "blocked" in game.state.world.flags


def _an_unrated_free_text_answer(game):
    """直接呼叫、沒給 llm_rate（伺服器一定給，鎖外評好）：鎖內才評的那一處，評不到就是 40。"""
    game.content.events["drunk"].free_text = GAMBLE
    game.state.pending_event = "drunk"
    msgs = game.answer_event(FreeTextRequest(event_id="drunk", text="大喊官兵來了"))
    assert any("你：「大喊官兵來了」" in m for m in msgs)


def _a_round_narration(game):
    definition = _install_battle_def(game.content)
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
        game.world.mutate_battle(
            lambda b: battle_instance.join_faction(b, "機器人", "huang", neili_cap=100.0, is_bot=True)
        )
    with at(game, definition.muster_seconds + 1):
        game._battle_status()
        game.world.mutate_battle(lambda b: setattr(b.participants["機器人"], "neili", 1.0))  # 這一回合倒下：有一句系統訊息可退回
        game.choose("battle:act:guan_hold")
    battle = game.world.get_battle()
    rounds = game.world.battle_rounds(battle.record_id)
    # 潤色失敗就用系統判定的訊息本身（不含每回合那一行出招比例，那只留在回合紀錄），戰鬥不會卡住
    assert rounds and "氣血耗盡" in rounds[-1].narration and "（戰局 " not in rounds[-1].narration


def _a_custom_battle_action(game):
    definition = _install_battle_def_with_free_text(game.content)
    after_muster = _join_and_open(game.content, game, definition)
    with at(game, after_muster):
        game.submit_battle_custom_action("直取波才首級")
        assert game.battle_free_text_prompt() is None  # 評不到成功率也照樣送出去了


def _a_repeated_event(game):
    event = game.content.events["scroll"]
    _, first = game._present(event)[:2]
    _, again = game._present(event)[:2]
    assert again == first  # 重複事件的點綴句沒生出來，整句省略


def _a_revisit_by_dashing(game):
    walk_to(game, "lake")
    msgs = game.travel("town", "dash")  # 疾行在這次行動裡抵達；小鎮開局就去過，是重遊
    assert game.location_text() in msgs


def _a_dialogue_that_is_first_generated_in_the_lock(game):
    """進鎖重驗對不上、鎖外生成的結果被丟掉時的老路徑：鎖內現生成。"""
    game.content.characters["mate"].deep_interaction = True
    stamina = game.state.player.stamina
    msgs = game.choose("act:socialize")
    assert msgs == ["韓鐵似乎無心多談，你只好先行告辭。"]
    assert game.state.player.pending_companion is None and game.state.player.stamina == stamina  # 這一輪不算數、不扣體力


def _a_dialogue_turn_that_consolidates_memory_and_drift(game):
    """對話的主體是備好的（這裡直接給），鎖內才做的是每隔一陣子的記憶整理與全服性情漂移（各試 MAX_RETRIES 次）。"""
    game.content.characters["mate"].deep_interaction = True
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        game.choose("act:socialize")
    game.state.player.turns_since_consolidation["mate"] = companion_agent.MEMORY_CONSOLIDATION_INTERVAL
    for _ in range(companion_agent.DRIFT_SYNTHESIS_INTERVAL):
        game.world.record_companion_tag("mate", "尋常寒暄")
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        game.choose("talk:0")
    assert game.state.player.pending_companion == "mate"
    assert game.world.get_companion_drift_note("mate") == ""  # 漂移沒做成，下次互動再試


def _a_forge_named_in_the_lock(game):
    """直接呼叫 Game.forge、沒給 proposed（伺服器一律給，整季機器人與腳本才走這條）：鎖內取名，取不到就走退路字表。"""
    p = game.state.player
    p.member.wugong_id = "basic_fist"
    p.insights = ["feng", "huo"]
    p.stats["xinde"] = 100
    msgs = game.forge("basic_fist", ["feng"])
    assert any("第一次" in m for m in msgs) and len(p.arts) == 1
    msgs = game.forge(None, ["feng", "huo"])
    assert len(p.insights) == 3, msgs


SCENARIOS = {
    "大事潤色（行動選項）": _a_threshold_through_a_choice,
    "大事潤色（管理者觸發大事）": _a_threshold_through_admin_fire,
    "大事潤色（管理者推動大勢）": _a_threshold_through_admin_push_trend,
    "大事潤色（管理者定戰況）": _a_threshold_through_admin_set_trend,
    "大事潤色（隨口應對）": _a_threshold_through_a_free_text_answer,
    "隨口應對的鎖內評分": _an_unrated_free_text_answer,
    "決戰回合敘事": _a_round_narration,
    "決戰自訂行動的評分": _a_custom_battle_action,
    "重複事件的點綴句": _a_repeated_event,
    "疾行重遊的點綴句與大事潤色": _a_revisit_by_dashing,
    "鎖內現生成的對話": _a_dialogue_that_is_first_generated_in_the_lock,
    "記憶整理與性情漂移": _a_dialogue_turn_that_consolidates_memory_and_drift,
    "鎖內取名的開爐": _a_forge_named_in_the_lock,
}


@pytest.mark.parametrize("name", SCENARIOS)
def test_every_model_call_made_in_the_lock_has_a_short_timeout_and_falls_back(slow, spy, name):
    SCENARIOS[name](slow)
    cap = slow.content.config.in_lock_model_timeout
    assert all(timeout <= cap for timeout in spy.timeouts), spy.calls
    assert not any(spy.retries), spy.retries  # 鎖內的呼叫都不重問
    assert slow.client.timeout == PRODUCTION_TIMEOUT and slow.client.retry  # 原本那個 client 不動：鎖外的路徑照舊用它
    # 第一次逾時之後，同一次行動裡後面的鎖內呼叫都不送（兩個動作的情境，旗子要到下一次拿鎖才歸零）：整條路徑只送一趟
    assert len(spy.calls) == 1, f"{name}：{spy.calls}"


@pytest.mark.parametrize("name", SCENARIOS)
def test_without_a_client_no_model_call_is_made_anywhere_in_the_lock(game, spy, name):
    """伺服器假人（bot_runner 把 game.client 設成 None）：這些路徑一個模型都不叫，結果跟逾時退回的一樣。"""
    game.client = None
    SCENARIOS[name](game)
    assert spy.calls == []


# ── 短複本本身 ────────────────────────────────────────────


def test_the_default_cap_is_fifteen_seconds():
    assert Config().in_lock_model_timeout == 15


def test_the_quick_client_is_a_short_copy_and_leaves_the_original_alone(slow):
    quick = slow._quick_client()
    assert quick is not slow.client and quick.timeout == slow.content.config.in_lock_model_timeout == 15
    assert quick.retry is False and slow.client.retry is True  # 鎖內不重問，鎖外照舊
    assert slow.client.timeout == PRODUCTION_TIMEOUT
    assert (quick.base_url, quick.model) == (slow.client.base_url, slow.client.model)  # 其他設定照舊


def test_the_quick_client_is_none_without_a_client(game):
    game.client = None
    assert game._quick_client() is None


def test_a_client_that_is_already_faster_than_the_cap_keeps_its_own_timeout(game):
    """比上限還快的 client（測試內容的 3 秒）：逾時照它自己的，不被拉長到 15 秒；一樣是不重問的複本。"""
    game.client.timeout = 5
    quick = game._quick_client()
    assert quick.timeout == 5 and quick.retry is False and quick is not game.client
    assert game.client.retry is True


def test_the_cap_comes_from_the_config(slow, spy):
    slow.content.config.in_lock_model_timeout = 7
    _a_threshold_through_a_choice(slow)
    assert spy.timeouts and set(spy.timeouts) == {7}


def test_a_fake_client_without_a_timeout_attribute_still_gets_the_cap(game):
    """測試與腳本常拿簡單的假物件當 client（沒有 timeout 欄位）：複本照樣設上上限，不丟例外。"""

    class Fake:
        def chat_text(self, messages, **kwargs):
            return ""

    game.client = Fake()
    quick = game._quick_client()
    assert quick is not game.client and quick.timeout == 15 and not hasattr(game.client, "timeout")


# ── 硬上限（fix round 1）：不重問、記憶整理／漂移／取名只試一次、一次拿鎖只容忍一次失敗 ──────────────────


class FakeResponse:
    status_code = 200

    def __init__(self, content):
        self._content = content

    def raise_for_status(self):
        pass

    def json(self):
        return {"message": {"content": self._content}}


@pytest.fixture
def posts(monkeypatch):
    """真的 chat_structured（含重問），HTTP 層換成假的：每送一趟記下它的 timeout，回一段不是 JSON 的字。"""
    sent: list[float] = []

    def post(url, json=None, timeout=None):
        sent.append(timeout)
        return FakeResponse("這不是 JSON")

    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(OllamaClient, "chat_structured", REAL_CHAT_STRUCTURED)
    return sent


ASK = [{"role": "user", "content": "取個名字"}]


def test_an_in_lock_structured_call_with_an_unparsable_reply_makes_exactly_one_post(slow, posts):
    quick = slow._quick_client()
    with pytest.raises(ValueError):  # 解析失敗的例外照原樣丟給呼叫端，呼叫端各自走退路
        quick.chat_structured(ASK, naming.NameReply, required_fields=["name"])
    assert posts == [slow.content.config.in_lock_model_timeout]


def test_an_in_lock_structured_call_that_times_out_makes_exactly_one_post(slow, monkeypatch):
    sent = []

    def post(url, json=None, timeout=None):
        sent.append(timeout)
        raise requests.exceptions.ReadTimeout("模型太慢，逾時了")

    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(OllamaClient, "chat_structured", REAL_CHAT_STRUCTURED)
    with pytest.raises(requests.exceptions.ReadTimeout):
        slow._quick_client().chat_structured(ASK, naming.NameReply, required_fields=["name"])
    assert sent == [15]


def test_the_out_of_lock_client_keeps_its_retry(slow, posts):
    """鎖外的路徑（對話備料、開爐取名、隨口應對）拿的是 game.client：格式不對照舊重問一趟、用自己的逾時。"""
    with pytest.raises(ValueError):
        slow.client.chat_structured(ASK, naming.NameReply, required_fields=["name"])
    assert posts == [PRODUCTION_TIMEOUT, PRODUCTION_TIMEOUT]


class CountingClient:
    """每次 chat_structured 數一次、丟例外（或回一個不合格的名字）；retry 沒給就是沒有這個欄位（簡單的假物件）。"""

    def __init__(self, retry=None, reply=None):
        self.calls = 0
        self.reply = reply
        if retry is not None:
            self.retry = retry

    def chat_structured(self, messages, response_model, **kwargs):
        self.calls += 1
        if self.reply is not None:
            return self.reply
        raise RuntimeError("連不上")


@pytest.mark.parametrize(("retry", "attempts"), [(False, 1), (True, companion_agent.MAX_RETRIES), (None, companion_agent.MAX_RETRIES)])
def test_memory_consolidation_makes_one_attempt_with_the_quick_client(game, retry, attempts):
    state = game.state
    state.player.turns_since_consolidation["mate"] = companion_agent.MEMORY_CONSOLIDATION_INTERVAL
    state.player.dialogue_history["mate"] = [
        {"role": "user", "content": "你好"}, {"role": "assistant", "content": "他點了點頭。"},
    ]
    client = CountingClient(retry)
    assert companion_agent._maybe_consolidate_memory(client, state, game.content.characters["mate"], "mate") == []
    assert client.calls == attempts
    # 失敗的話計數沒歸零，下一次對話再試
    assert state.player.turns_since_consolidation["mate"] == companion_agent.MEMORY_CONSOLIDATION_INTERVAL


@pytest.mark.parametrize(("retry", "attempts"), [(False, 1), (True, companion_agent.MAX_RETRIES), (None, companion_agent.MAX_RETRIES)])
def test_drift_synthesis_makes_one_attempt_with_the_quick_client(game, retry, attempts):
    for _ in range(companion_agent.DRIFT_SYNTHESIS_INTERVAL):
        game.world.record_companion_tag("mate", "尋常寒暄")
    client = CountingClient(retry)
    companion_agent._maybe_synthesize_drift(client, game.content.characters["mate"], "mate", game.world)
    assert client.calls == attempts
    assert game.world.get_companion_drift_note("mate") == ""  # 沒做成，下次互動再試


def test_the_quick_client_gets_one_attempt_through_the_whole_dialogue_path(slow, spy):
    """跟上面兩個函式層級的測試對照：整條對話路徑（記憶整理、性情漂移各有三次重試的迴圈）用 Game 的短複本只送一趟。"""
    _a_dialogue_turn_that_consolidates_memory_and_drift(slow)
    assert spy.calls == [("chat_structured", 15)]


@pytest.mark.parametrize(("retry", "attempts"), [(False, 1), (True, naming.NAME_ATTEMPTS), (None, naming.NAME_ATTEMPTS)])
def test_naming_makes_one_attempt_with_the_quick_client(content, retry, attempts):
    """模型一直回不合格的名字（只有一個字）：鎖內的複本只問一次就走退路字表，鎖外照舊最多 NAME_ATTEMPTS 次。"""
    client = CountingClient(retry, reply=naming.NameReply(name="一"))
    assert naming.propose(client, content, ASK) == (None, "")
    assert client.calls == attempts


def test_the_out_of_lock_naming_budget_keeps_its_attempts(content):
    """鎖外取名（server.prepare_forge）：複本帶預算，retry 欄位照舊是 True，所以預算夠的話照舊多試幾次。"""
    inner = OllamaClient(timeout=PRODUCTION_TIMEOUT)
    calls = []

    def chat_structured(messages, response_model, **kwargs):
        calls.append(inner.timeout)
        return naming.NameReply(name="一")

    inner.chat_structured = chat_structured  # copy.copy 會帶著這個實例欄位走
    assert naming.propose(inner, content, ASK, budget=600) == (None, "")
    assert len(calls) == naming.NAME_ATTEMPTS


def test_a_failed_first_call_makes_later_calls_in_the_same_action_skip_the_model(slow, spy):
    """疾行重遊：先叫模型補一句點綴，逾時了；同一次行動接著跨過的大事門檻，潤色就不再叫模型（直接用原文），門檻照樣觸發。"""
    walk_to(slow, "lake")
    slow.state.world.trends["kou"] = 50
    msgs = slow.travel("town", "dash")
    assert spy.calls == [("chat_text", 15)]
    assert "blocked" in slow.state.world.flags and "【江湖大事】水寇封江！" in msgs


def test_without_a_failure_every_in_lock_call_goes_out(game, monkeypatch):
    """對照：模型回得出來，同一次行動裡兩處都叫（逾時的旗子才是後面不叫的原因，不是「一次行動只准一次」）。"""
    spy = ModelSpy(monkeypatch, ok=True)
    game.client.timeout = PRODUCTION_TIMEOUT
    walk_to(game, "lake")
    game.state.world.trends["kou"] = 50
    msgs = game.travel("town", "dash")
    assert [kind for kind, _ in spy.calls] == ["chat_text", "chat_text"]  # 重遊的點綴句＋大事潤色
    assert any("山風捲過旌旗。" in m for m in msgs)


def test_a_new_lock_hold_gets_a_fresh_budget(slow, spy):
    quick = slow._quick_client()
    with pytest.raises(requests.exceptions.ReadTimeout):
        quick.chat_text([])
    assert slow._quick_client() is None  # 這次拿鎖：後面都不叫
    with pytest.raises(RuntimeError):  # 手上已經拿著的複本也一樣不送（_arrive 與 continue_dialogue 一路拿著同一個）
        quick.chat_text([])
    assert len(spy.calls) == 1
    slow.reset_model_budget()  # server._locked 每次拿到鎖先做這件事
    assert slow._quick_client() is not None


def test_a_missing_client_stays_missing_after_a_reset(game):
    game.client = None
    game.reset_model_budget()
    assert game._quick_client() is None
