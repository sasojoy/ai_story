"""新手引導重做（Joy 2026-10-22 同意設計稿，「改完直接合進main」）：城裡操練、城外練功分級、新手目標、提示汰換。
Config.training 跟一類一顆（precise.on）一起才有；測試內容一類一顆關著，這裡用正式內容（週末設定），同 test_precise_actions。"""
from __future__ import annotations

import random

import pytest

from conftest import real_content
from jianfa_kit import classic_explore

from tianxia import newbie, training
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

HOUR = 3600
MON = 1792339200  # 2026-10-19 週一 00:00（台灣）
NOW = MON + 10 * HOUR


def _game(at="yingchuan", level=None, name="沈浪"):
    c = classic_explore(real_content("week7"))  # 城裡操練與練功分級（減法季探索一顆開著時沒有，tests/test_explore_one.py）
    c.config.train_event_chance = 0.0
    store = open_world()
    store.seed_first_season(c)
    store.open_season(c, NOW)
    game = Game.new(c, name, rng=random.Random(0), world=store)
    game.client = None
    game.sync(NOW)
    p = game.state.player
    p.location, p.stamina = at, 250.0
    p.tutorial_step = len(c.tutorial.steps)
    if level is not None:
        p.member.level = level
    return game


def _ids(game):
    return {o.id: o for o in game.options()}


def test_town_shows_drill_and_not_practice():
    game = _game()
    ids = _ids(game)
    assert training.on(game.content, game.state.world)
    assert ids[training.DRILL_ID].enabled and "今日還能 5 次" in ids[training.DRILL_ID].label
    assert "explore:practice" not in ids  # 練功從探索三選一拿出來了


def test_drill_gives_xinde_five_times_then_points_out_of_town():
    game = _game(level=2)
    p = game.state.player
    before = p.stats.get("xinde", 0)
    for _ in range(5):
        game.choose(training.DRILL_ID)
    xinde, _ = training.gains(game.content.config.training, 2)
    assert p.stats["xinde"] - before == 5 * xinde
    assert p.stamina == 250 - 5 * game.content.config.action_cost["explore"]
    full = _ids(game)[training.DRILL_ID]
    assert not full.enabled and training.DRILL_FULL in full.label and "潁" in full.label  # 最近的練功點在潁水河畔或潁川郊野
    assert not game.state.battles  # 不打仗


def test_drill_count_resets_at_midnight():
    game = _game()
    for _ in range(5):
        game.choose(training.DRILL_ID)
    assert not _ids(game)[training.DRILL_ID].enabled
    game.sync(MON + 24 * HOUR + 60)
    game.state.player.stamina = 250.0
    assert _ids(game)[training.DRILL_ID].enabled


def test_practice_spots_are_tiered_by_weakest_foe():
    game = _game(at="yingshui")
    c = game.content
    assert game._practice_tier(c.locations["yingshui"]) == 0
    assert game._practice_tier(c.locations["songshan_foot"]) == 1  # 以前手標危險度一，新人勝率 3%
    assert game._practice_tier(c.locations["huangjin_camp"]) == 2
    label = _ids(game)["explore:practice"].label
    assert label.startswith("尋敵（") and "宵小出沒" in label and "一級" not in label  # 不寫幾級（Joy 2026-10-22）


def test_move_list_no_longer_names_tiers_and_the_map_card_says_how_fierce():
    """Joy 2026-10-22：移動清單不寫幾級練功點；輿圖地點卡（與舊地點詳情）只寫一句這一帶多兇。"""
    game = _game()
    assert not _ids(game)["move:yingshui"].note
    places = game.map_state()["places"]
    assert places["yingshui"]["fierce"] == "此地宵小出沒。" and places["songshan_foot"]["fierce"] == "此地匪寇橫行。"
    assert places["yingchuan"]["fierce"] == ""  # 城鎮不寫
    assert game.place_detail("yingshui").endswith("此地宵小出沒。")


@pytest.mark.smoke
def test_practice_battle_is_labelled_and_higher_tiers_pay_more():
    game = _game(at="songshan_foot", level=30)
    game.choose("explore:practice")
    record = game.state.battles[-1]
    assert record.label == "尋敵"
    if record.tier in ("大勝", "險勝"):
        assert "field2" in game.state.player.newbie_marks


def test_wild_exp_per_stamina_beats_town_drill():
    game = _game(at="yingshui", level=2)
    _, exp = training.gains(game.content.config.training, 2)
    foe = min(game._wild_foes(game.content.locations["yingshui"]), key=lambda f: f.difficulty)
    assert exp * 3 < foe.exp  # 同樣的體力，出城打贏的經驗至少是城裡操練的三倍（設計稿實測五倍）


def test_newbie_goals_show_after_the_guide_and_pay_once():
    game = _game()
    view = game.newbie_view()
    assert view is not None and len(view["rows"]) == 3 and view["rows"][0]["key"] == "level5"
    p = game.state.player
    pills = p.stamina_pills
    p.member.level = 5
    game._check_hints()
    assert "level5" in p.newbie_done and p.stamina_pills == pills + game.content.config.training.goal_pill
    game._check_hints()
    assert p.stamina_pills == pills + game.content.config.training.goal_pill  # 只給一次
    assert any(newbie.TITLE in g for e in game.state.journal for g in e.guide)


def test_drifter_button_counts_for_the_side_goal():
    game = _game()
    silver = game.state.player.stats.get("silver", 0)
    game.newbie_drifter()
    assert "side" in game.state.player.newbie_done
    assert game.state.player.stats.get("silver", 0) == silver  # 這一條給的是丹


def test_bots_earn_newbie_rewards_the_same_way():
    game = _game(name="假人甲")
    game.state.player.bot = True
    game.state.player.member.level = 6
    game._check_hints()
    assert "level5" in game.state.player.newbie_done


def test_newbie_go_points_at_the_nearest_spot():
    game = _game()
    go = game._newbie_go("practice0")
    assert go.get("move") in ("yingshui", "yingchuan_wilds", "hilltop_wilds")
    assert game._newbie_go("craft") == {"tab": "craft"}


def test_newbie_goals_end_after_the_newbie_window():
    game = _game()
    game.sync(NOW + 60 * HOUR)
    assert game.newbie_view() is None


def test_refine_fail_hint_is_gone_and_injury_hint_drops_when_healed():
    game = _game()
    assert all(h.id != "h_refine_fail" for h in game.content.hints.hints)
    from tianxia.state import HintNote
    p = game.state.player
    p.hint_queue = [HintNote(id="h_injury", speaker="師父", text="…")]
    p.member.injury = 0
    game._check_hints()
    assert all(n.id != "h_injury" for n in p.hint_queue) and "h_injury" not in p.hints_seen
