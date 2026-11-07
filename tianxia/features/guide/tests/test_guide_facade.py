"""guide 這一包的測試，從 tests/core/test_engine.py 拆來（全部拆包第 61 批，只搬位置、不改斷言）。"""
import random
import pytest
from conftest import walk_to
from tianxia import guide
from tianxia.engine import Game
from tianxia.state import new_game_state
from engine_kit import _wugong_step_game, ids  # noqa: F401

pytestmark = pytest.mark.whole_content


def test_a_maxed_wugong_finishes_the_practice_step_as_soon_as_it_comes_up(game):
    """W6 Important 1：修練頁的鍛鍊鈕在第十成是灰的，所以走到這一步之前就練滿的人按不了「鍛鍊」。
    這一步改成「身上有一門武學」：前一步一完成，同一次 note_action 就接著完成它。"""
    reward = _wugong_step_game(game, {"武學": 10})
    silver = game.state.player.stats["silver"]
    game.view_map()
    assert game.state.player.guide_done.count("✔ 引導完成") == 2  # 對話框列出兩步（RF2）
    assert game.state.player.tutorial_step == 2
    assert game.state.player.stats["silver"] == silver + reward
    assert game.guide_box()["text"] == "出城。"


def _roll_one_season(content, world, tutorial_step=None, skip=False):
    """建一個玩家、把引導調到指定的一步（或略過），管理者收季再開下一季，玩家同步一次；回傳玩家的 Game。"""
    content.config.admins = ["管理者"]
    admin = Game.new(content, "管理者", rng=random.Random(1), world=world)
    player = Game.new(content, "玩家", rng=random.Random(2), world=world)
    if tutorial_step is not None:
        player.state.player.tutorial_step = tutorial_step
    if skip:
        player.skip_tutorial()
    admin.admin_end_season(now=200.0)
    admin.admin_next_season(now=300.0)
    player.sync(400.0)
    assert player.state.player.season_number == 2
    return player


@pytest.mark.parametrize("unfinished", [0, 1, 2], ids=["first", "second", "last"])
def test_season_roll_restarts_an_unfinished_tutorial(content, world, unfinished):
    """引導做到一半的人，新一季是新角色、沒有武學：下一步不能再叫他出城遊歷，要回到新角色的起始步（FB-034）。"""
    assert unfinished < len(content.tutorial.steps)
    start = new_game_state(content, "玩家").player.tutorial_step  # 照新角色的起始值，不寫死 0
    player = _roll_one_season(content, world, tutorial_step=unfinished)
    assert player.state.player.tutorial_step == start
    assert guide.tutorial_active(player.state, content)
    assert guide.next_hint(player.state, content) == f"（說書人）{content.tutorial.steps[start].text}"


def test_season_roll_keeps_a_finished_tutorial_finished(content, world):
    steps = len(content.tutorial.steps)
    player = _roll_one_season(content, world, tutorial_step=steps)
    assert player.state.player.tutorial_step == steps
    assert not guide.tutorial_active(player.state, content)  # 引導不再出現


def test_season_roll_keeps_a_skipped_tutorial_skipped(content, world):
    player = _roll_one_season(content, world, skip=True)
    assert player.state.player.tutorial_step == len(content.tutorial.steps)
    assert not guide.tutorial_active(player.state, content)


def test_tutorial_runs_through_engine(game):
    assert "【說書人】先探索一下。" in game.state.log
    game.choose("act:explore")
    assert game.state.player.tutorial_step == 1
    if game.state.pending_event:
        game.choose(ids(game)[-1])
    walk_to(game, "lake")
    assert game.state.player.tutorial_step == 2
    game.view_map()
    assert game.state.player.tutorial_step == 3
    assert "拜入門派" in game.quest_text()


def test_view_map_always_sets_the_flag_even_when_not_the_current_step(game):
    game.view_map()
    game.view_map()
    assert "看過地圖" in game.state.player.flags
    assert game.state.player.tutorial_step == 0
