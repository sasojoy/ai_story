"""減法季批 4 接線（主機側計畫 Task 4-2；PM 2026-10-25 第 7、8 件）：server.answer_event 的三段式在分岔開著時改叫
event_llm.judge_outcome（B 段：歸類、評分，歸到最後一種才判善惡），C 段多交那一種的 id，D／E 照舊潤色；人拉犁的那一顆只在分岔開著的季。
正式內容（yc_wilds_plow，潁川郊野）。模型一律是假的（mock 掉 event_llm 的函式），不打 11434。"""
from __future__ import annotations

import random
from unittest import mock

import pytest

import server
from conftest import FixedRandom, real_content
from tianxia import event_llm
from tianxia.characters import open_characters
from tianxia.engine import FREE_TEXT_OPTION, Game

PLOW = "yc_wilds_plow"


@pytest.fixture(autouse=True)
def _server_state(monkeypatch):
    """同 tests/test_server.py 的幾個 autouse：一季已經開打、排程不開、佇列關著、斷路器關著、伺服器記憶體從空的開始。"""
    monkeypatch.setattr(server.CONTENT.config, "auto_open_first_season", True)
    monkeypatch.setattr(server.CONTENT.config, "world_tick_seconds", 0)
    monkeypatch.setattr(server, "_breaker_until", None, raising=False)
    monkeypatch.setattr(server, "QUEUE", None)
    for store in (server.SESSIONS, server.GAMES):
        store.clear()
    yield
    for store in (server.SESSIONS, server.GAMES):
        store.clear()


def _at_the_plow(monkeypatch, on=True):
    """正式內容的伺服器上開一個站在潁川郊野、停在人拉犁的官軍；on：減法季（總開關＋這一季的章）。"""
    monkeypatch.setattr(server.CONTENT.config.jianfa, "enabled", on)
    game = Game.new(server.CONTENT, "測試", rng=random.Random(0))
    game.state.world.jianfa_on = on
    game._save_season()
    p = game.state.player
    p.location, p.faction = "yingchuan_wilds", "guan"
    p.stats["silver"] = 50
    game.state.pending_event = PLOW
    open_characters().save(game.state)
    return game


def test_the_server_classifies_then_applies_the_outcome(monkeypatch):
    game = _at_the_plow(monkeypatch)
    asked, narrated = [], []

    def judge(client, event, outcomes, text, moral_client=None):
        asked.append((event.id, [o.id for o in outcomes], text))
        return event_llm.OutcomeVerdict("give", 30)

    def narrate(client, event, text, success, effect_text, evil=False):
        narrated.append((success, effect_text, evil))
        return "你蹲下身，把錢放進老漢粗糙的掌心。"

    with mock.patch.object(server.event_llm, "judge_outcome", side_effect=judge), \
            mock.patch.object(server.event_llm, "judge_event_gamble", side_effect=AssertionError("分岔開著不走舊的評分")), \
            mock.patch.object(server.event_llm, "narrate_event_gamble", side_effect=narrate):
        server.answer_event(game, "給他十兩去租頭牛")
    give = server.CONTENT.events[PLOW].free_text.outcomes[2]
    assert asked == [(PLOW, ["labor", "chase", "give", "leave"], "給他十兩去租頭牛")]
    assert narrated == [(True, give.effect.text, False)]
    entry = game.state.journal[0]
    assert entry.title == "人拉犁・隨口應對" and entry.lines[0] == "你：「給他十兩去租頭牛」（周濟）"
    assert entry.lines[1] == "你蹲下身，把錢放進老漢粗糙的掌心。"
    assert game.state.player.stats["silver"] == 40 and game.state.world.marks["yingchuan_wilds:鄉里得濟"] == 1


@pytest.mark.parametrize("outcome, judged", [("leave", True), ("labor", False)])
def test_the_moral_is_judged_only_for_the_fallback(monkeypatch, outcome, judged):
    """PM 2026-10-25 第 8 件：歸到最後一種才另外判善惡（同一句話不加兩次）；judge_outcome 自己決定，伺服器只把剩下的預算給它。"""
    game = _at_the_plow(monkeypatch)
    game.rng = FixedRandom(0.0)
    moral_calls = []
    monkeypatch.setattr(server.event_llm, "classify_outcome", lambda client, event, outcomes, text: (outcome, 50))
    monkeypatch.setattr(server.event_llm, "judge_moral", lambda client, event, text: moral_calls.append(text) or "中")
    game.client = mock.Mock()  # 有 client 才叫得到判善惡（judge_outcome 沒有 client 一律「中」）
    with mock.patch.object(server, "within_budget", lambda client, left: client), \
            mock.patch.object(server.event_llm, "narrate_event_gamble", return_value=None):
        server.answer_event(game, "我替他把犁拉完")
    assert bool(moral_calls) is judged
    assert game.last_gamble.outcome == outcome


def test_the_plow_button_is_only_there_in_a_branching_season(monkeypatch):
    """人拉犁原本沒有隨口應對：關著的季選單、提示語、main_view 一個字都不多（PM 第 7 件）；開著的季多那一顆，帶可能的走向。"""
    off = _at_the_plow(monkeypatch, on=False)
    view = server.look(off, server.main_view)
    assert FREE_TEXT_OPTION not in {o["id"] for o in view["options"]} and view["event_free_text"] is None
    assert not any("outcomes" in o for o in view["options"])
    server.GAMES.clear()
    on = _at_the_plow(monkeypatch, on=True)
    view = server.look(on, server.main_view)
    button = next(o for o in view["options"] if o["id"] == FREE_TEXT_OPTION)
    assert [o["id"] for o in button["outcomes"]] == ["labor", "chase", "give", "leave"]
    assert set(button["outcomes"][0]) == {"id", "tag"}  # 不給後果的數字
    assert view["event_free_text"] == server.CONTENT.events[PLOW].free_text.prompt


@pytest.mark.parametrize("profile, shown", [("season21", True), ("week7", True), ("weekend", False), (None, False)])
def test_the_plow_follows_the_profile(profile, shown):
    content = real_content(profile)
    content.config.auto_open_first_season = True  # 正式內容預設要管理者開季
    game = Game.new(content, "甲", rng=random.Random(0))
    game.client = None
    game.state.player.location = "yingchuan_wilds"
    game.state.pending_event = PLOW
    assert (FREE_TEXT_OPTION in {o.id for o in game.options()}) is shown
