"""新手引導重做（Joy 2026-10-22 同意設計稿，「改完直接合進main」）：城外分級、新手目標、提示汰換（城裡操練與尋敵鈕第 13 批拿掉）。
Config.training 跟一類一顆（precise.on）一起才有；測試內容一類一顆關著，這裡用正式內容（週末設定），同 test_precise_actions。"""
from __future__ import annotations

import random

from conftest import real_content
from jianfa_kit import classic_explore

from tianxia import newbie
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

HOUR = 3600
MON = 1792339200  # 2026-10-19 週一 00:00（台灣）
NOW = MON + 10 * HOUR


def _game(at="yingchuan", level=None, name="沈浪"):
    c = classic_explore(real_content("week7"))  # 城外分級（減法季探索一顆開著時沒有，tests/test_explore_one.py）
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


def test_practice_spots_are_tiered_by_weakest_foe():
    game = _game(at="yingshui")
    c = game.content
    assert game._practice_tier(c.locations["yingshui"]) == 0
    assert game._practice_tier(c.locations["songshan_foot"]) == 1  # 以前手標危險度一，新人勝率 3%
    assert game._practice_tier(c.locations["huangjin_camp"]) == 2


def test_move_list_no_longer_names_tiers_and_the_map_card_says_how_fierce():
    """Joy 2026-10-22：移動清單不寫幾級練功點；輿圖地點卡（與舊地點詳情）只寫一句這一帶多兇。"""
    game = _game()
    assert not _ids(game)["move:yingshui"].note
    places = game.map_state()["places"]
    assert places["yingshui"]["fierce"] == "此地宵小出沒。" and places["songshan_foot"]["fierce"] == "此地匪寇橫行。"
    assert places["yingchuan"]["fierce"] == ""  # 城鎮不寫
    assert game.place_detail("yingshui").endswith("此地宵小出沒。")


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
