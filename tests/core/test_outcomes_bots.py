"""減法季批 4（主機側計畫 Task 4-4；企劃者 2026-10-24 第 5 件）：假人挑後果這一版不做——bot.pick_outcome 只留位子（回 None），
整季機器人（bot.pick）與伺服器假人（bot_policy.take_turn）在分岔開著的季照舊不按隨口應對（choice:free，要寫字）。"""
from __future__ import annotations

import random

from outcomes_kit import OUTCOMES, branch_game
from tianxia import bot, bot_policy
from tianxia.engine import FREE_TEXT_OPTION, Game
from tianxia.state import BotProfile


def test_the_season_bot_never_writes_and_has_no_outcome_pick_yet(content, world):
    g = branch_game(content, world)
    options = g.options()
    assert FREE_TEXT_OPTION in {o.id for o in options}  # 分岔開著：那一顆在、帶著可能的走向
    assert all(bot.pick(g, options, random.Random(seed)) != FREE_TEXT_OPTION for seed in range(40))
    assert bot.pick_outcome(g, OUTCOMES, random.Random(0)) is None


def test_the_server_bot_never_answers_in_writing(content, world, monkeypatch):
    g = branch_game(content, world)
    g.state.player.bot = BotProfile(personality="普通", seed=7, faction="guan", season_number=g.world.get_season_number())
    monkeypatch.setattr(Game, "answer_event", lambda *a, **k: (_ for _ in ()).throw(AssertionError("假人不寫字")))
    settled = 0
    for seed in range(10):
        g.state.pending_event = "drunk"
        bot_policy.take_turn(g, g.state.player.bot, random.Random(seed))
        settled += g.state.pending_event is None
    assert settled  # 真的按了：照固定選項了結
    assert not any(e.title.endswith("隨口應對") for e in g.state.journal)
