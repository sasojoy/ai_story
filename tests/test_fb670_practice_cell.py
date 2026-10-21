"""FB-670（企劃者 2026-10-22 選練功入口「丙」，PM 給號）：練功從探索卡最下面搬到行動列自己一格。這一份是伺服器那一半：
行動列底下練功那一行（Game.action_notes 的 explore:practice，句子在 howto）。跟練功鈕（Game._practice_option）同一個判斷、同一個次序：
有對手寫打誰；這裡只有頭目寫頭目；城鎮與沒有對手的地方寫最近的在哪、步行多久（Game._nearest_practice，時間走 atlas.route_text
的步行，跟移動那張卡同一個算法）；頭目冷卻中、次數用完寫鈕上同一句。網頁只照這一句畫（tests/test_fb670_practice_cell_web.py），
不另寫一份判斷。選項 id 照舊 explore:practice（假人、整季機器人、bot.pick 不受影響）。"""
from __future__ import annotations

import random

import pytest
from conftest import real_content

from tianxia import atlas, bot, explore_modes, howto
from tianxia import duel as duel_rules
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

pytestmark = pytest.mark.slow

HOUR = 3600
MON = 1792339200  # 2026-10-19 週一 00:00（台灣）
NOW = MON + 10 * HOUR
PRACTICE = "explore:practice"


def _game(at, faction=None, profile="week7"):
    c = real_content(profile)
    store = open_world()
    store.seed_first_season(c)
    store.open_season(c, NOW)
    game = Game.new(c, "沈浪", rng=random.Random(0), world=store)
    game.client = None
    game.sync(NOW)
    p = game.state.player
    p.location, p.faction, p.stamina = at, faction, 250.0
    p.tutorial_step = len(c.tutorial.steps)
    return game


def _option(game):
    return next(o for o in game.options() if o.id == PRACTICE)


def _note(game):
    return game.action_notes([o.id for o in game.options()]).get(PRACTICE)


def _reason(option):
    """灰掉的鈕括號裡那一句。"""
    return option.label.split("（", 1)[1].removesuffix("）")


def test_in_town_the_note_says_outside_the_walls_and_how_far_the_nearest_is():
    game = _game("yingchuan")
    option = _option(game)
    route = game._nearest_practice()
    place = game.content.locations[route.path[-1]].name
    walk = atlas.route_text(game.state, game.content, route, "walk")
    assert not option.enabled and _reason(option) == f"{explore_modes.NO_FOE}，最近的在{place}"  # 前提：鈕上灰著、同一個地方
    assert place == "潁水河畔" and walk.startswith("步行約 ") and walk.endswith(" 分鐘")
    assert _note(game) == f"城外才有對手，最近的在{place}（{walk}）"
    # 時間跟移動那張卡上「前往 潁水河畔（步行約 N 分鐘）」一樣（潁水河畔就在隔壁）
    assert f"前往 {place}（{walk}）" in [o.label for o in game.options()]


def test_a_place_out_of_town_without_foes_keeps_the_buttons_words():
    """官軍站在自己的大營：不是城鎮，可是一路對手都沒有（自己人不練手）。不說「城外才有」，照鈕上那一句再補步行多久。"""
    game = _game("guan_camp", faction="guan")
    option = _option(game)
    assert not explore_modes.is_town(game.content, game.content.locations["guan_camp"]) and not option.enabled
    route = game._nearest_practice()
    walk = atlas.route_text(game.state, game.content, route, "walk")
    assert _note(game) == f"{_reason(option)}（{walk}）"


def test_a_lit_practice_note_names_the_foe_the_button_names():
    game = _game("yingshui")
    option = _option(game)
    foe = game._gather_foe(game.content.locations["yingshui"]).name
    assert option.enabled and f"・{foe}・" in option.label
    assert _note(game) == howto.PRACTICE_NOTE.format(foe=foe)


def test_a_boss_only_place_names_the_boss_then_says_why_he_is_away():
    game = _game("julu_altar", faction="huang")
    s, c = game.state, game.content
    option = _option(game)
    boss_face = option.label.split("・")[1]
    assert option.enabled and option.label.endswith(f"・{explore_modes.BOSS_NOTE}）")
    assert _note(game) == howto.PRACTICE_BOSS_NOTE.format(foe=boss_face)
    s.player.duel_last = [float(s.player.season_number), s.world.time]  # 冷卻中
    option = _option(game)
    assert not option.enabled and _note(game) == _reason(option) and "後才會再現身" in _note(game)
    s.player.duel_last = []
    boss = duel_rules.here(s, c)[0]
    s.player.duel_tally[duel_rules.week_key(s, c, boss.id)] = c.config.duel.per_boss_week  # 這一段的次數用完（7 天季）
    option = _option(game)
    assert not option.enabled and _note(game) == _reason(option) and "不再現身" in _note(game)


def test_a_tired_player_still_reads_what_practice_would_be():
    """體力不夠時鈕灰著（格子寫「體力不夠」），底下那一行照亮著時那一句，跟別的格子一樣。"""
    game = _game("yingshui")
    game.state.player.stamina = 0.0
    assert not _option(game).enabled
    assert _note(game) == howto.PRACTICE_NOTE.format(foe=game._gather_foe(game.content.locations["yingshui"]).name)


def test_no_practice_no_note():
    """一類一顆沒蓋章的舊季：沒有練功鈕，也沒有這一行。"""
    game = _game("yingshui")
    game.state.world.precise_actions = False
    ids = [o.id for o in game.options()]
    assert PRACTICE not in ids and PRACTICE not in game.action_notes(ids)


def test_the_option_id_is_still_the_one_the_bots_press():
    """選項 id 照舊（explore_modes.option_id(PRACTICE)）：整季機器人要經驗時照舊按得到它。"""
    game = _game("yingshui")
    ids = [o.id for o in game.options() if o.enabled]
    assert PRACTICE == explore_modes.option_id(explore_modes.PRACTICE)
    assert bot.explore_choice(ids, want="exp") == PRACTICE
