"""初入江湖（新手引導第四段，Joy 2026-10-17「不要讓玩家可以亂點，新玩家現在迷路機率太高」）：走出草廬到了潁川，
賣茶的老周一步一步帶：醫館療傷 → 探索三選一 → 進一間鋪子 → 打開輿圖。走這幾步時「此地還能做」只留教到的，畫面一樣一樣亮。"""
import random

import pytest

from tianxia import prologue
from tianxia.engine import Game
from tianxia.state import ONBOARDING_VERSION

STEPS = ["e1_clinic", "e2_explore", "e3_shops", "e4_world"]


@pytest.fixture
def newcomer(real):
    """剛走出草廬、到了潁川的真人：帶著雪恥留下的內傷，身上有師父給的盤纏。"""
    game = Game.new(real, "沈浪", rng=random.Random(0))
    p = game.state.player
    p.tutorial_step = real.tutorial.prologue_steps
    p.location = "yingchuan"
    p.member.injury = 12.0
    p.stats["silver"] = 30
    return game


def _ids(game):
    return [o.id for o in game.options()]


def _step(game):
    return game.content.tutorial.steps[game.state.player.tutorial_step].id


def test_the_four_steps_follow_the_farewell(real):
    t = real.tutorial
    assert [s.id for s in t.steps[t.prologue_steps:]] == STEPS
    assert all(not s.season_one for s in t.steps[t.prologue_steps:])


def test_arriving_shows_only_the_clinic_under_here(newcomer):
    assert _step(newcomer) == "e1_clinic"
    box = newcomer.guide_box()
    assert box["speaker"] == "賣茶的老周" and box["key"] == "e1_clinic"
    ids = _ids(newcomer)
    assert "act:heal" in ids and "act:explore" in ids and any(i.startswith("move:") for i in ids)
    assert not any(i in ids for i in ("act:smith", "act:bounties", "act:arena")) and not any(i.startswith("learn:") for i in ids)
    view = newcomer.onboard_view()
    assert "tab:news" not in view["reveal"] and "orders" not in view["reveal"] and "tab:map" in view["reveal"]
    assert newcomer.enlist_glow(ids) == ["act:heal"]
    assert newcomer.prologue_view() is None  # 草廬的規矩（略過序章、師父的框）不跟出來


def test_walking_the_four_steps_opens_everything(newcomer):
    newcomer.choose("act:heal")
    assert _step(newcomer) == "e2_explore"
    newcomer.choose("act:explore")
    gather = next(i for i in _ids(newcomer) if i.startswith("explore:"))
    newcomer.choose(gather)
    while newcomer.state.pending_event is not None:  # 撞上的事件先了結
        newcomer.choose(next(i for i in _ids(newcomer) if i.startswith("choice:")))
    assert _step(newcomer) == "e3_shops"
    assert "act:smith" in _ids(newcomer) and "act:arena" not in _ids(newcomer)
    newcomer.choose("act:smith")
    assert _step(newcomer) == "e4_world"
    newcomer.choose("smith:back")
    assert "act:arena" in _ids(newcomer)
    newcomer.view_map()
    p = newcomer.state.player
    assert p.tutorial_step == len(newcomer.content.tutorial.steps)
    assert newcomer.onboard_view() is None


def test_no_injury_skips_the_clinic(newcomer):
    newcomer.state.player.member.injury = 0.0
    newcomer.view_map()  # 任何一下動作都看一次：沒有內傷，醫館那一步直接過
    assert _step(newcomer) == "e2_explore"


def test_a_short_purse_still_counts_as_having_gone_to_the_clinic(newcomer):
    newcomer.state.player.member.injury = 200.0  # 盤纏不夠全治：治一部分也算去過
    newcomer.choose("act:heal")
    assert newcomer.state.player.member.injury > 0 and _step(newcomer) == "e2_explore"


def test_skipping_ends_it(newcomer):
    newcomer.skip_tutorial()
    assert newcomer.onboard_view() is None and "act:smith" in _ids(newcomer)


def test_bots_and_scripts_never_walk_it(real):
    t = real.tutorial
    script = Game.new(real, "腳本", rng=random.Random(0))
    bot = Game.new(real, "假人", rng=random.Random(0), graduated=True)
    for g in (script, bot):
        assert g.state.player.tutorial_step == len(t.steps) and g.onboard_view() is None


def test_players_out_of_the_hut_before_this_version_skip_it(newcomer, real):
    p = newcomer.state.player
    p.onboarding = ONBOARDING_VERSION - 1
    again = Game(real, newcomer.state, world=newcomer.world)
    assert again.state.player.tutorial_step == len(real.tutorial.steps)
    assert again.onboard_view() is None


def test_players_still_in_the_hut_walk_it_after_the_upgrade(real):
    game = Game.new(real, "草廬裡的", rng=random.Random(0), prologue=True)
    game.state.player.onboarding = ONBOARDING_VERSION - 1
    again = Game(real, game.state, world=game.world)
    assert again.state.player.tutorial_step == 0 and prologue.active(again.state, real)
