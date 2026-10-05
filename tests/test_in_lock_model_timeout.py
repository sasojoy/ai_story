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
from tianxia import battle_instance, companion_agent, fusion
from tianxia.engine import FreeTextRequest, Game
from tianxia.models import Config, Effect, FreeTextChoice
from tianxia.ollama_client import OllamaClient

PRODUCTION_TIMEOUT = 120  # Config.ollama_timeout 的預設：鎖外路徑照舊用這個
FAKE_TURN = companion_agent.CompanionTurn(
    narrative="他點了點頭。", options=["閒聊幾句", "就此告辭"], option_tags=["尋常寒暄", "尋常寒暄"],
)
GAMBLE = FreeTextChoice(
    prompt="自己想辦法……", stat="str", by="self",
    effect=Effect(text="醉漢被你唬住了。"), fail_effect=Effect(text="醉漢一拳揮來。"),
)


class ModelSpy:
    """替換 OllamaClient 的 chat_text／chat_structured：記下每一次呼叫當下 client.timeout，再丟 requests 的逾時（模型太慢）。"""

    def __init__(self, monkeypatch):
        self.calls: list[tuple[str, float]] = []

        def chat_text(client, messages, **kwargs):
            self.calls.append(("chat_text", client.timeout))
            raise requests.exceptions.ReadTimeout("模型太慢，逾時了")

        def chat_structured(client, messages, response_model, **kwargs):
            self.calls.append(("chat_structured", client.timeout))
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
        game.choose("battle:act:safe")
    battle = game.world.get_battle()
    rounds = game.world.battle_rounds(battle.record_id)
    assert rounds and rounds[-1].narration  # 潤色失敗就用系統判定的訊息本身，戰鬥不會卡住


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
    assert spy.calls, f"{name}：這條路徑沒有叫模型，測的不是鎖內的模型呼叫"
    cap = slow.content.config.in_lock_model_timeout
    assert all(timeout <= cap for timeout in spy.timeouts), spy.calls
    assert slow.client.timeout == PRODUCTION_TIMEOUT  # 原本那個 client 不動：鎖外的路徑（同一個 Game）照舊用它


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
    assert slow.client.timeout == PRODUCTION_TIMEOUT
    assert (quick.base_url, quick.model) == (slow.client.base_url, slow.client.model)  # 其他設定照舊


def test_the_quick_client_is_none_without_a_client(game):
    game.client = None
    assert game._quick_client() is None


def test_a_client_that_is_already_faster_than_the_cap_is_used_as_it_is(game):
    game.client.timeout = 5
    assert game._quick_client() is game.client


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
