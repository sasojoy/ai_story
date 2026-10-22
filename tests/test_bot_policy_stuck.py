"""量 7 天季領地爭奪時（2026-10-22，計畫 docs/superpowers/plans/2026-10-22-7天季領地爭奪調整.md 第四節）順手看到的兩個假人卡住的地方，
所有季都有、跟領地爭奪開不開無關：

1. 捐軍備（act:donate）落到 ACT_SCORES 的 0.0，隨手挑的那一半會按開；軍需官那一串的鈕（donate:*）一樣都不打分，假人就什麼都不做，
   一整季停在大本營（季末十三個假人有七到十個停在這裡；真人也看得到「這個人一直站在大本營不動」）。
2. 揭著一張還沒交的懸賞，_takeable 把它也算成「榜上有得揭」，每路過有懸賞榜的城鎮就打開、什麼都揭不了又關上，下一輪又打開。"""
from __future__ import annotations

import random

import pytest

from conquest_kit import conquest_game, go, join
from tianxia import bot_policy, bounties
from tianxia.engine import Game, Option
from tianxia.state import Bounty, BotProfile

pytestmark = pytest.mark.slow  # 建 Game、載正式內容


def _bot(game: Game, side: str) -> Game:
    game.state.player.bot = BotProfile(personality="普通", seed=7, faction=side, season_number=game.world.get_season_number())
    return game


def test_a_bot_never_opens_the_quartermaster_and_walks_out_if_it_is_inside():
    game = _bot(go(join(conquest_game("week7", name="假官"), "guan"), "changshe"), "guan")
    profile = game.state.player.bot
    assert "act:donate" in {o.id for o in game.options(odds=False) if o.enabled}
    assert bot_policy.score(game, Option(id="act:donate", label=""), profile) is None  # 修前 0.0：隨手挑的那一半會按開
    game.choose("act:donate")
    assert game.state.player.picking_donate
    options = [o for o in game.options(odds=False) if o.enabled]
    assert {o.id for o in options} == {o.id for o in options if o.id.startswith("donate:")}  # 選單上只剩軍需官那一串
    for seed in range(5):  # 挑最高分、隨手挑都只會離開（修前一樣都不打分，假人什麼都不做，一整季停在這裡）
        assert bot_policy.pick(game, options, profile, random.Random(seed)) == "donate:back"
    bot_policy.take_turn(game, profile, random.Random(0))
    assert not game.state.player.picking_donate


def _scout(game: Game, bid: str, takers: list[str]) -> Bounty:
    w = game.state.world
    b = Bounty(id=bid, kind="scout", faction="guan", week=1, expires=w.time + 86400, silver=10, deeds=1, quota=3,
               location="hilltop_wilds", takers=takers)
    w.bounties.append(b)
    return b


def test_a_held_bounty_does_not_make_the_board_worth_opening():
    game = _bot(go(join(conquest_game("week7", name="假官"), "guan"), "changshe"), "guan")
    s, c = game.state, game.content
    s.world.bounties.clear()
    _scout(game, "b-held", ["假官"])
    assert [b.id for b in bounties.mine(s, c)] == ["b-held"]
    assert bounties.take_problem(s, c, s.world.bounties[0]) is None  # 修前就是這一句讓假人以為榜上有得揭
    assert not bot_policy._takeable(game)
    _scout(game, "b-open", [])
    assert bot_policy._takeable(game)
