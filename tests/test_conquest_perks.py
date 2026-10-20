"""領地爭奪第一批 Task 5：陣營領地加成、散人在中立地（計畫三、Task 5；設計 4.5、4.6；裁決 4：新手期在敵方領地療傷不吃 ×1.2）。"""
from __future__ import annotations

import random

import pytest

from conquest_kit import conquest_game, plain_game
from tianxia import conquest, explore_modes, sensing, territory

pytestmark = pytest.mark.slow  # 建 Game、載正式內容


def _at(game, loc, faction):
    p = game.state.player
    p.location, p.journey, p.faction = loc, None, faction


def _land(game, loc, faction):
    return territory.price_factor(game.state.world, game.content, faction, loc)


def test_prices_follow_the_holder():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    assert _land(game, "yingchuan", "guan") == pytest.approx(0.9)
    conquest.set_control(w, c, "nanyang_wilds", "huang")
    assert _land(game, "nanyang_wilds", "guan") == pytest.approx(1.2)
    assert _land(game, "nanyang_wilds", "huang") == pytest.approx(0.9)
    assert _land(game, "nanyang_wilds", None) == pytest.approx(0.9)  # 散人：開季中立的區塊算自家（設計 4.6），不論此刻歸誰
    assert _land(game, "yu_river", None) == pytest.approx(0.9)
    assert _land(game, "yingchuan", None) == 1.0  # 散人在陣營領地：原價
    assert _land(game, "yu_river", "guan") == 1.0  # 中立地沒人佔：誰都不是自家


def test_home_follows_where_you_stand():
    game = conquest_game("season21")
    s, c = game.state, game.content
    _at(game, "yingchuan", "guan")
    assert conquest.home(s, c)
    _at(game, "runan", "guan")
    assert not conquest.home(s, c)
    _at(game, "nanyang_wilds", None)
    assert conquest.home(s, c)  # 散人在開季中立的區塊
    _at(game, "haozu_fort", None)
    assert not conquest.home(s, c)  # 不是區塊


def test_newbie_heals_at_home_price_in_enemy_land():
    game = conquest_game("season21")
    s, c = game.state, game.content
    _at(game, "yingchuan", "huang")  # 潁川郡：黃巾新手出序章的第一站，官軍的領地（裁決 4）
    s.player.joined_at = s.world.time
    assert territory.price_here(s, c, heal=True) == pytest.approx(territory.price_here(s, c) / 1.2)
    s.player.joined_at = s.world.time - 100 * 3600  # 過了新手期
    assert territory.price_here(s, c, heal=True) == pytest.approx(territory.price_here(s, c))


def _found_count(game, loc_id):
    s = game.state
    before = sum(s.player.materials.values())
    game._gather(game.content.locations[loc_id], random.Random(7))
    return sum(s.player.materials.values()) - before


def _lucky_seq(game, hit):
    """找一個這一下「領地」那顆骰擲中（hit）或沒中的探索流水號（_explore_mode 擲之前先加一，所以回的是擲那一下的流水號）。"""
    p = game.state.player
    season = game.world.get_season_number()
    chance = game.content.config.conquest.gather_bonus_chance
    for seq in range(1, 200):
        if (explore_modes.rng_for(season, p.name, seq, "領地").random() < chance) == hit:
            return seq
    raise AssertionError("找不到")


def test_gather_bonus_only_at_home():
    game = conquest_game("season21")
    s, c = game.state, game.content
    _at(game, "nanyang_wilds", "guan")
    s.player.explore_seq = _lucky_seq(game, True)
    conquest.set_control(s.world, c, "nanyang_wilds", "guan")
    home = _found_count(game, "nanyang_wilds")
    conquest.set_control(s.world, c, "nanyang_wilds", "huang")
    away = _found_count(game, "nanyang_wilds")
    assert home == away + 1
    s.player.explore_seq = _lucky_seq(game, False)
    conquest.set_control(s.world, c, "nanyang_wilds", "guan")
    assert _found_count(game, "nanyang_wilds") == away  # 沒擲中：不多給


def test_sense_rate_plus_five_at_home():
    game = conquest_game("season21")
    s, c = game.state, game.content
    loc = c.locations["yu_river"]  # 開季中立（區塊表 v3 之前用嵩山深處，現在是官軍的）
    s.player.stats["wis"] = 1  # 壓低成算，免得撞到上限
    _at(game, "yu_river", "guan")
    away = sensing.rate(s, c, loc)
    conquest.set_control(s.world, c, "yu_river", "guan")
    assert sensing.rate(s, c, loc) == away + c.config.conquest.sense_bonus_points


def test_switch_off_perks_unchanged():
    game = plain_game("weekend")
    s, c = game.state, game.content
    _at(game, "deep_mountain", None)
    assert not conquest.home(s, c)
    assert territory.price_factor(s.world, c, None, "deep_mountain") == 1.0
    _at(game, "yingchuan", "huang")
    assert territory.price_here(s, c, heal=True) == territory.price_here(s, c)
