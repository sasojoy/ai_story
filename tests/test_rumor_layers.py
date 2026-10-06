"""傳聞分層（一）：聽得到什麼（計畫 2026-10-06-傳聞分層-1-聽得到什麼）。

用真實內容（content/）：要驗的是真實的五個大區（潁川汝南、南陽、冀州、幽州、洛陽）、地點與陣營。每個測試自己載一份，
開關在 fixture 裡才打開；開關開著的季是「蓋了章」的（auto_open_first_season 開出來的季照當下的 Config 蓋章）。
週末設定（季長 2.5 天）的季曆一天是 86400 ÷ 33.6 ≈ 2571 個世界秒。"""
from __future__ import annotations

import random
from pathlib import Path

import pytest

import server
from tianxia import atlas, foreshadow, journal, mapview, orders, ranks, rules, timetable
from tianxia.content import load_content
from tianxia.engine import Game
from tianxia.martial_arts import Insight, shown_creator
from tianxia.models import Effect
from tianxia.state import BotProfile, Lock, Order, Rumor, TimelineResult

CONTENT_DIR = Path(__file__).parent.parent / "content"


@pytest.fixture
def real():
    """真實內容，開關關著（beta 那一季的樣子）。"""
    c = load_content(CONTENT_DIR)
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    return c


@pytest.fixture
def on(real):
    """同一份真實內容，照週末設定打開：開關、季長 2.5 天、人數上限 2。"""
    real.config.season_one = True
    real.config.season_days = 2.5
    real.config.server_max_players = 2
    return real


def _game(content, name="甲", faction=None, at="yingchuan", world=None):
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.state.player.faction = faction
    game.state.player.location = at
    return game


def _rumor(game, text, location=None, layer="local", time=None, **kw) -> Rumor:
    """在這個人手上的賽季放一則傳聞（只在記憶體，畫面讀的就是這一份）；大區照 add_rumor 自己算。"""
    rules.add_rumor(game.state, text, location, content=game.content, layer=layer, **kw)
    rumor = game.state.world.rumors[-1]
    if time is not None:
        rumor.time = time
    return rumor


def _day(game) -> float:
    """這一季的一個「天」是幾個世界秒（第一季是季曆天，beta 是世界天）。"""
    return rules.recent_seconds(1, game.content, game.state.world)


def _hears(game, rumor) -> bool:
    return rules.audible(rumor, rules.ears_of(game.state, game.content))


# ── Task 1：一條「聽得到」的規則 ─────────────────────────────


def test_world_news_reaches_everyone_and_faction_news_only_its_own_side(on):
    guan, huang, loner = _game(on, "甲", "guan"), _game(on, "乙", "huang"), _game(on, "丙")
    for game in (guan, huang, loner):
        world = _rumor(game, "天下大事一則。", layer="world")
        intel = _rumor(game, "本週軍令：守長社。", layer="faction", faction="guan")
        assert _hears(game, world)
        assert _hears(game, intel) is (game is guan)  # 敵方、散人都聽不到官軍的軍情


def test_local_news_is_heard_only_inside_its_region(on):
    game = _game(on, at="yingchuan")  # 潁川汝南
    here = _rumor(game, "長社一帶有人鬧事。", "changshe")
    there = _rumor(game, "宛城一帶有人鬧事。", "wan_city")
    assert (here.region, there.region) == ("yingru", "nanyang")
    assert _hears(game, here) and not _hears(game, there)
    game.state.player.location = "wan_city"  # 走進南陽：聽到南陽的，潁川的就聽不到了
    assert not _hears(game, here) and _hears(game, there)


def test_the_local_board_keeps_three_calendar_days_and_world_news_the_whole_season(on):
    game = _game(on)
    day = _day(game)
    assert day == pytest.approx(86400 / 33.6)  # 週末那一季：季曆天，不是世界天
    game.state.world.time = 10 * day
    fresh = _rumor(game, "剛貼上板的。", "changshe", time=7 * day + 1)
    stale = _rumor(game, "四天前的。", "changshe", time=7 * day - 1)
    old_world = _rumor(game, "很久以前的天下大事。", "changshe", layer="world", time=0.0)
    assert _hears(game, fresh) and not _hears(game, stale)
    assert _hears(game, old_world)  # 天下大事整季都在


def test_the_board_length_comes_from_the_config(on):
    on.config.rumor_board_days = 1
    game = _game(on)
    day = _day(game)
    game.state.world.time = 10 * day
    assert not _hears(game, _rumor(game, "兩天前的。", "changshe", time=8 * day))
    assert _hears(game, _rumor(game, "半天前的。", "changshe", time=9.5 * day))


def test_personal_clues_only_reach_that_player(on):
    jia, yi = _game(on, "甲"), _game(on, "乙")
    clue = Rumor(time=0.0, text="只說給甲聽的。", layer="personal", character="甲")
    assert _hears(jia, clue) and not _hears(yi, clue)


def test_local_news_without_a_region_reaches_everyone(on):
    """地圖沒有大區、或發生地不明的地方傳聞：沒有大區可比，人人都聽得到（不會整則消失）。"""
    game = _game(on, at="wan_city")
    assert _hears(game, Rumor(time=0.0, text="不知道哪裡的事。", layer="local"))


def test_the_news_page_list_only_shows_what_you_can_hear(on):
    game = _game(on, "甲", "huang", at="yingchuan")
    _rumor(game, "長社一帶有人鬧事。", "changshe")
    _rumor(game, "宛城一帶有人鬧事。", "wan_city")
    _rumor(game, "本週軍令：守長社。", layer="faction", faction="guan")
    _rumor(game, "天下大事一則。", layer="world")
    text = game.rumors_text()
    assert "長社一帶" in text and "天下大事一則" in text
    assert "宛城一帶" not in text and "守長社" not in text


def test_with_the_switch_off_everything_is_heard_like_before(real):
    """beta 那一季：地方傳聞不分大區、不撤板（只看陣營與名號，跟以前一樣）。"""
    game = _game(real, "甲", "huang", at="yingchuan")
    game.state.world.time = 30 * 86400
    there = _rumor(game, "宛城一帶有人鬧事。", "wan_city", time=0.0)
    intel = _rumor(game, "官軍的事。", layer="faction", faction="guan")
    assert _hears(game, there) and not _hears(game, intel)
    assert "宛城一帶" in game.rumors_text()
    assert rules.recent_seconds(3, real, game.state.world) == 3 * 86400  # beta 的「天」是世界天


def test_an_unstamped_season_keeps_the_beta_rule(real):
    """開關後來才打開、這一季開季時沒蓋「開」的章：照 beta 的規則（開關打開後開的下一季才分層）。"""
    game = _game(real, at="yingchuan")
    real.config.season_one = True
    assert not rules.season_one(real, game.state.world)
    assert _hears(game, _rumor(game, "宛城一帶有人鬧事。", "wan_city"))


def test_can_hear_still_answers_the_faction_and_name_half(on):
    """can_hear 留著給手上沒有 content 的呼叫端：只看陣營與名號（不分大區），跟以前一樣。"""
    game = _game(on, "甲", "huang", at="yingchuan")
    assert rules.can_hear(_rumor(game, "宛城一帶有人鬧事。", "wan_city"), game.state)
    assert not rules.can_hear(_rumor(game, "官軍的事。", layer="faction", faction="guan"), game.state)


# ── Task 2：在路上 ─────────────────────────────────────────


def _on_the_road(game, dest="luoyang_road"):
    """從潁川（潁川汝南）往洛陽官道（洛陽）出發，停在半路上（還沒抵達）。"""
    game.choose(f"move:{dest}")
    assert game.state.player.journey is not None
    return game


def test_on_the_road_both_ends_of_the_leg_count(on):
    game = _on_the_road(_game(on, at="yingchuan"))
    assert rules.here_regions(game.state, on) == {"yingru", "luoyang"}
    behind = _rumor(game, "長社一帶有人鬧事。", "changshe")
    ahead = _rumor(game, "洛陽宮裡出了事。", "luoyang_palace")
    elsewhere = _rumor(game, "宛城一帶有人鬧事。", "wan_city")
    assert _hears(game, behind) and _hears(game, ahead) and not _hears(game, elsewhere)


def test_arriving_leaves_the_old_region_behind(on):
    game = _on_the_road(_game(on, at="yingchuan"))
    behind = _rumor(game, "長社一帶有人鬧事。", "changshe")
    journey = game.state.player.journey
    game.advance(journey.arrive_at[-1] - game.state.world.time)
    assert game.state.player.journey is None and game.state.player.location == "luoyang_road"
    assert rules.here_regions(game.state, on) == {"luoyang"}
    assert not _hears(game, behind)  # 見聞紀錄（離開大區後還翻得到）是傳聞分層第二份計畫的事


def test_asking_along_the_road_only_picks_from_the_board(on):
    game = _game(on, at="yingchuan")
    day = _day(game)
    game.state.world.time = 10 * day
    _rumor(game, "四天前長社的事。", "changshe", time=7 * day - 1)
    _rumor(game, "四天前的天下大事。", "changshe", layer="world", time=7 * day - 1)
    _rumor(game, "昨天長社的事。", "changshe", time=9 * day)
    msgs = _on_the_road(game).choose("road:ask")
    assert any("聽說：昨天長社的事。" in m for m in msgs)
    assert not any("四天前" in m for m in msgs)


def test_asking_along_the_road_finds_nothing_when_the_board_is_bare(on):
    game = _game(on, at="yingchuan")
    day = _day(game)
    game.state.world.time = 10 * day
    _rumor(game, "四天前長社的事。", "changshe", time=day)
    msgs = _on_the_road(game).choose("road:ask")
    assert any("這一帶最近沒什麼新鮮事" in m for m in msgs)


def test_asking_along_the_road_with_the_switch_off_still_hears_old_news(real):
    game = _game(real, at="yingchuan")
    game.state.world.time = 10 * 86400
    _rumor(game, "很久以前長社的事。", "changshe", time=0.0)
    msgs = _on_the_road(game).choose("road:ask")
    assert any("聽說：很久以前長社的事。" in m for m in msgs)
