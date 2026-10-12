"""回體丹一天最多兩顆（企劃者 2026-10-12「體力丹一天最多吃兩顆每天00:00重新計算」）：Config.stamina_pills_per_day，
「一天」看現實時間（Game.pill_now），照 pill_day_utc_offset_hours（台灣 UTC+8）00:00 換日。測試內容不限（0），這裡自己打開。"""
from __future__ import annotations

import random

import pytest
from conftest import next_season, real_content
from test_prologue_web import run

import server
from tianxia import bot
from tianxia.engine import HOUR, PILL_DAY_FULL, Game
from tianxia.sqlite_world import open_world

DAY = 24 * HOUR
# 1970-01-02 00:00（台灣時間）＝ 1970-01-01 16:00 UTC：換日那一刻
MIDNIGHT_TW = DAY - 8 * HOUR


@pytest.fixture
def capped(game):
    game.content.config.stamina_pills_per_day = 2
    game.sync(MIDNIGHT_TW + 9 * HOUR)  # 台灣時間早上九點
    return game


def _eat(game):
    game.state.player.stamina = 0.0
    return game.take_stamina_pill()


def test_the_third_pill_of_the_day_is_refused(capped):
    p = capped.state.player
    _eat(capped)
    _eat(capped)
    assert p.stamina_pills == 18 and capped.pills_left_today() == 0
    entries = len(capped.state.journal)
    assert _eat(capped) == [PILL_DAY_FULL.format(n="兩")] == ["今天已服兩顆，明日 00:00 後再服。"]
    assert p.stamina_pills == 18 and p.stamina == 0 and len(capped.state.journal) == entries  # 不收丹、不寫紀錄


def test_the_count_starts_over_at_midnight_taiwan_time(capped):
    _eat(capped)
    _eat(capped)
    capped.sync(MIDNIGHT_TW + DAY - 1)  # 台灣時間 23:59:59 還是同一天
    assert capped.pills_left_today() == 0
    capped.sync(MIDNIGHT_TW + DAY)  # 00:00 換日（UTC 是下午四點）
    assert capped.pills_left_today() == 2
    _eat(capped)
    assert capped.pills_left_today() == 1 and capped.state.player.stamina_pills == 17


def test_the_offset_comes_from_the_config(capped):
    _eat(capped)
    _eat(capped)
    capped.content.config.pill_day_utc_offset_hours = 0  # 照 UTC 換日：台灣早上九點是 UTC 前一天的 01:00，還沒到換日
    capped.sync(MIDNIGHT_TW + 9 * HOUR + 1)
    assert capped.pills_left_today() == 0


def test_no_cap_means_no_limit(game):
    for _ in range(5):
        _eat(game)
    assert game.state.player.stamina_pills == 15 and game.pills_left_today() is None


def test_advancing_time_moves_the_pill_day_too(capped):
    """整季機器人只 advance、不 sync（now 開季後不動）：advance 推過的現實時間也算，不然一整季都是同一天。"""
    _eat(capped)
    _eat(capped)
    capped.advance(DAY * capped.content.config.time_scale)
    assert capped.pills_left_today() == 2


def test_bots_follow_the_same_cap(capped):
    p = capped.state.player
    for _ in range(4):
        p.stamina = 0.0
        bot.take_pill(capped)
    assert p.stamina_pills == 18 and p.stamina == 0  # 第三次起不吃（也不白按、不寫紀錄）


def test_the_count_carries_into_the_next_season(content):
    """換季不能多吃一輪：哪一天、吃了幾顆跟著帶過去。"""
    content.config.auto_open_first_season = True
    content.config.stamina_pills_per_day = 2
    world = open_world()
    game = Game.new(content, "沈浪", rng=random.Random(0), world=world)
    game.sync(100.0)  # next_season 讓玩家在 400.0 同步：同一天（台灣時間 1970-01-01 早上八點）
    _eat(game)
    _eat(game)
    next_season(content, world, game)
    assert game.pills_left_today() == 0


def test_the_status_bar_says_how_many_are_left_today(capped):
    p = capped.state.player
    p.stamina = 40.0
    assert capped.status_data()["pills"]["today"] == 2
    _eat(capped)
    assert capped.status_data()["pills"]["today"] == 1
    _eat(capped)
    assert capped.status_data()["pills"]["today"] == 0
    help_line = capped.status_data()["stamina_help"][-1]
    assert "一天最多服 2 顆，每天 00:00（台灣時間）重新計算（今天還能服 0 顆）。" in help_line


def test_the_real_content_caps_at_two_a_day():
    assert real_content().config.stamina_pills_per_day == 2
    assert real_content("weekend").config.stamina_pills_per_day == 2


def _button(today, full=False):
    m = server.main_view(_web_game())
    m["status"]["pills"] = {"name": "回體丹", "count": 28, "restore": 150, "full": full, "today": today}
    top = run(m, "return H.topHtml();")
    start = top.index('<button class="pill-btn"')
    return top[start:top.index("</button>", start)]


def _web_game():
    content = real_content("weekend")
    content.config.auto_open_first_season = True
    game = Game.new(content, "沈浪", rng=random.Random(0))
    game.client = None
    return game


def test_the_button_shows_the_three_states():
    can = _button(2)
    assert "disabled" not in can and "丹28<small>今2</small>" in can and "今天還能服 2 顆" in can
    spent = _button(0)
    assert "disabled" in spent and "丹28<small>明日</small>" in spent and "明日 00:00 後再服" in spent
    full = _button(1, full=True)
    assert "disabled" in full and "丹28<small>今1</small>" in full
