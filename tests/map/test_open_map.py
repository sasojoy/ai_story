"""全圖開放（企劃者 2026-10-15「未來不再限制有沒有去過的地點~都可以直接移動過去」）：
已開放的地點全部算摸清（名字、敵情、勝算、詳情都看得到，都能直接安排前往，路線照全部已開放的地點算）；劇情還沒開放的地點照舊不畫、
不能去；路上小事「留意地形」拿掉；名望不再多看一站；「還沒摸清」的字不再出現。舊的摸清規則 2026-10-27 拿掉，沒有開關了。
正式內容（預設設定：第一季規則關著，南華觀要等 xi_open）。"""
from __future__ import annotations

import random

import pytest

from conftest import real_content
from tianxia import atlas, figures, howto, mapview
from tianxia.engine import Game
from tianxia.sqlite_world import open_world
from tianxia.state import Order

FAR = ("guangzong", "zhuo_county")  # 冀州的廣宗、幽州的涿郡：新角色在潁川郡開局，舊規則下都看不見


def _game(faction=None, profile=None):
    c = real_content(profile)
    c.config.auto_open_first_season = True
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.tutorial_step = len(c.tutorial.steps)
    p.location, p.faction, p.stamina = "yingchuan", faction, float(c.config.stamina_max)
    return game


def test_a_new_character_can_head_for_jizhou_and_youzhou_at_once():
    game = _game()
    s, c = game.state, game.content
    assert not set(FAR) & (s.player.visited | s.player.surveyed)
    for loc_id in FAR:
        assert atlas.is_known(s, c, loc_id)
        buttons = game.travel_options(loc_id)
        assert buttons and all(b.enabled for b in buttons)
        detail = game.place_detail(loc_id)
        assert detail.startswith(f"### {c.locations[loc_id].name}") and atlas.UNKNOWN not in detail
        assert (c.locations[loc_id].name, loc_id) in game.map_places()
    game.travel("guangzong", "dash")
    assert game.state.player.location == "guangzong"


def test_routes_run_over_every_opened_place():
    game = _game()
    s, c = game.state, game.content
    every = atlas.shortest_routes(s, c)  # 所有已開放的地點
    assert atlas.routes(s, c) == every
    route = atlas.routes(s, c)["zhuo_county"]
    assert set(route.via) - s.player.visited  # 途經沒去過的地方


def test_a_place_the_story_has_not_opened_stays_off_the_map():
    game = _game()
    s, c = game.state, game.content
    assert c.locations["jade_cave"].unlock_flag == "xi_open" and "xi_open" not in s.world.flags
    assert atlas.views(s, c)["jade_cave"] == "hidden" and not atlas.is_known(s, c, "jade_cave")
    assert game.travel_options("jade_cave") is None
    assert "jade_cave" not in {loc_id for _, loc_id in game.map_places()}
    assert "jade_cave" not in atlas.routes(s, c)
    s.world.flags.add("xi_open")
    assert atlas.is_known(s, c, "jade_cave") and game.travel_options("jade_cave")


def test_the_road_has_no_terrain_survey_any_more():
    game = _game()
    game.choose("move:yingshui")
    ids = [o.id for o in game.options()]
    assert {"road:think", "road:ask", "road:gather"} <= set(ids) and "road:survey" not in ids
    surveyed = set(game.state.player.surveyed)
    game.choose("road:survey")
    assert game.state.player.surveyed == surveyed and "survey" not in game.state.player.leg_actions


@pytest.mark.smoke
def test_the_road_scene_lists_three_road_tasks():
    """FB-300：「在路上」那一張場景卡寫路上小事——全圖開放沒有留意地形。"""
    game = _game()
    game.choose("move:yingshui")
    scene = game.scene_text()
    assert "邊走邊想、沿途打聽、路邊採集，到下一站之前各能做一次" in scene and "留意地形" not in scene


def test_the_how_to_page_lists_three_road_tasks():
    game = _game()
    c, w = game.content, game.state.world
    assert "留意地形" not in howto.page(c, w, recruitable=False)


def test_fame_no_longer_widens_the_map():
    game = _game()
    s, c = game.state, game.content
    before = atlas.views(s, c)
    s.player.stats["fame"] = 100
    assert atlas.views(s, c) == before
    assert not any("輿圖" in line for line in howto.fame_lines(c, s.world))


def test_order_cards_never_say_a_place_is_unexplored():
    game = _game(faction="huang", profile="week7")  # 軍令只在第一季規則開著時有
    s, c = game.state, game.content
    week = 1
    front = figures.state_of(s, c, "luzhi").front
    s.world.orders += [
        Order(id="o1", template="strike", faction="huang", week=week, front=front, figure="luzhi", quota=4, text="（測試）"),
        Order(id="o2", template="siege", faction="huang", week=week, front="yingru", quota=4, text="（測試）"),
        Order(id="o3", template="siege", faction="huang", week=week, front="jizhou", quota=4, text="（測試）"),
    ]
    strike, *sieges = (atlas.order_how(s, c, o) for o in s.world.orders)
    assert f"他現在在{c.locations[figures.state_of(s, c, 'luzhi').location].name}" in strike
    for how in (strike, *sieges):
        assert "摸清" not in how
    places, regions = atlas.strike_marks(s, c)
    assert places and not regions  # 局勢層把 ◎ 標在地點上，不再退到大區


def test_the_legend_and_the_map_say_nothing_of_unknown_places():
    game = _game()
    s, c = game.state, game.content
    legend = mapview.legend_data(s, c)
    assert "摸清" not in legend["states"] and "未知" not in legend["states"]
    assert "摸清" not in mapview.LEGEND_STRIKE
    assert all(view in ("current", "visible", "hidden") for view in atlas.views(s, c).values())
    assert "？" not in game.world_map_svg()
