"""地盤易手（docs/superpowers/specs/2026-10-14-出陣探索與地盤-design.md 第四節）。正式內容、週末設定（第一季規則開著）。
開季的戰線：潁川汝南 40、南陽 35、冀州 55、割據 10。"""
from __future__ import annotations

import random

import pytest

from conftest import classic_rules, real_content, third_party_gentry
from tianxia import bounties, orders, rules, territory, timetable
from tianxia.content import ContentError, validate
from tianxia.engine import Game
from tianxia.sqlite_world import open_world
from tianxia.state import TerritoryState

OPENING = {
    "guan_camp": "guan", "runan_wilds": "huang", "nanyang_wilds": "guan", "yu_river": "guan",
    "baima_ford": "guan", "xiaquyang": "guan", "juma_river": "huang", "yanshan_foot": "huang",
    "changshe": "guan", "luzhi_camp": "guan", "huangjin_camp": "huang", "julu_altar": "huang",
    "nanyang_huangjin_camp": "huang", "guangzong": "huang",
}


def _game(profile="weekend"):
    c = third_party_gentry(real_content(profile))  # 這一檔測割據佔地：豪強是第三方的規則（豪強分屬兩軍見 test_gentry_allied.py）
    c.config.auto_open_first_season = True
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    territory.update(game.state.world, c)  # 開季那一下：第一次算，不發天下大事
    return game


def _push(game, line, delta):
    rules.change_trend(game.state, game.content, line, delta)


def _owner(game, loc_id):
    return territory.controller(game.state.world, game.content, loc_id)


def _flips(game):
    """易手的天下大事：「落入…之手」與這一季佔過那裡的一方拿回來的「…收復…」（FB-252）兩種都算。"""
    return [r.text for r in game.state.world.rumors if r.text.endswith("之手。") or "收復" in r.text]


def test_the_spots_bases_and_the_two_luoyang_places():
    c = real_content("weekend")
    assert territory.line_of(c, "changshe") == "yingru" and territory.line_of(c, "xiaquyang") == "jizhou"
    assert territory.line_of(c, "luoyang_road") is None and territory.line_of(c, "mengjin_ford") is None  # 寫的是 front，洛陽沒有戰線
    assert territory.line_of(c, "wan_city") is None  # 投靠點但不在戰線上
    assert territory.bases(c)["changshe"] == "guan" and territory.bases(c)["haozu_fort"] == "haoqiang"
    assert territory.threshold(1, 2) == 62.5 and territory.threshold(2, 2) == 37.5


def test_the_season_starts_from_the_opening_fronts_without_news():
    game = _game()
    assert {loc: _owner(game, loc) for loc in OPENING} == OPENING
    game.advance(60)
    assert _flips(game) == []


def test_an_old_season_without_territory_reads_the_rule_and_announces_nothing():
    game = _game()
    w = game.state.world
    w.territory = None  # 上線之前開的季
    assert _owner(game, "runan_wilds") == "huang"  # 照規則現算
    _push(game, "yingru", 10)  # 50：第一次重算，不發天下大事
    assert w.territory is not None and _flips(game) == []
    _push(game, "yingru", -20)  # 30
    assert _owner(game, "runan_wilds") == "guan"
    assert _flips(game) == [territory.FLIP_LINE.format(place="汝南荒野", side="官軍")]
    assert w.chronicle[-1].text == _flips(game)[0]


def test_the_band_stops_flapping_on_the_threshold():
    """汝南荒野的門檻 37.5：33～42 之間都不動，越過 32.5 歸官軍、越過 42.5 歸黃巾，各發一句。"""
    game = _game()
    for delta in (-4, -3):  # 36、33
        _push(game, "yingru", delta)
        assert _owner(game, "runan_wilds") == "huang"
    _push(game, "yingru", -1)  # 32
    assert _owner(game, "runan_wilds") == "guan"
    for delta in (8, 2, -1, 1):  # 40、42、41、42
        _push(game, "yingru", delta)
        assert _owner(game, "runan_wilds") == "guan"
    _push(game, "yingru", 1)  # 43
    assert _owner(game, "runan_wilds") == "huang"
    for delta in (-1, 1, -1):  # 42、43、42
        _push(game, "yingru", delta)
    assert _owner(game, "runan_wilds") == "huang" and len(_flips(game)) == 2


def test_the_gentry_takes_the_spot_nearest_each_front_and_gives_it_back():
    game = _game()
    _push(game, "geju", 50)  # 60：每條線門檻最近此刻戰線的一處
    assert [_owner(game, x) for x in ("runan_wilds", "yu_river", "xiaquyang")] == ["haoqiang"] * 3
    _push(game, "geju", 20)  # 80：再一處
    assert [_owner(game, x) for x in ("guan_camp", "nanyang_wilds", "juma_river")] == ["haoqiang"] * 3
    assert len(_flips(game)) == 6
    _push(game, "geju", -25)  # 55：還在 50 以上，手上的不動
    assert _owner(game, "juma_river") == "haoqiang" and len(_flips(game)) == 6
    _push(game, "geju", -10)  # 45：全部交還給拔河
    assert {loc: _owner(game, loc) for loc in OPENING} == OPENING and len(_flips(game)) == 12


def test_a_big_event_hands_a_spot_over_until_the_rule_changes():
    game = _game()
    w, c = game.state.world, game.content
    territory.assign(w, c, {"runan_wilds": "guan"})  # 規則此刻算黃巾
    assert _owner(game, "runan_wilds") == "guan" and len(_flips(game)) == 1
    _push(game, "yingru", 2)  # 42：規則還是黃巾，指定的留著
    assert _owner(game, "runan_wilds") == "guan"
    _push(game, "yingru", -10)  # 32：規則變成官軍——回到規則（還是官軍，不發）
    assert _owner(game, "runan_wilds") == "guan" and "runan_wilds" not in w.territory.pinned
    _push(game, "yingru", 11)  # 43
    assert _owner(game, "runan_wilds") == "huang" and len(_flips(game)) == 2


def test_a_pinned_spot_goes_to_the_gentry_when_the_gentry_rises():
    """Review Focus 3：大事剛把汝南荒野交給官軍，割據漲到 60 選中它——規則算出來的控制方變了，指定作廢、歸豪強。"""
    game = _game()
    territory.assign(game.state.world, game.content, {"runan_wilds": "guan"})
    _push(game, "geju", 50)
    assert _owner(game, "runan_wilds") == "haoqiang" and "runan_wilds" not in game.state.world.territory.pinned
    assert territory.FLIP_LINE.format(place="汝南荒野", side="地方豪強") in _flips(game)  # 同一下另兩條線也各佔一處，不一定排最後


def test_bases_never_change_hands_and_guangzong_moves_only_with_its_battle():
    game = _game()
    s, c = game.state, game.content
    _push(game, "jizhou", 45)  # 100
    assert _owner(game, "guangzong") == "huang" and _owner(game, "luzhi_camp") == "guan"
    territory.assign(s.world, c, {"luzhi_camp": "huang"})  # 大本營不收
    assert _owner(game, "luzhi_camp") == "guan"
    timetable.resolve(s, c, timetable.find(c, "guangzong"), random.Random(0), key="guan:大勝")
    assert _owner(game, "guangzong") == "guan"
    _push(game, "jizhou", 50)
    assert _owner(game, "guangzong") == "guan"


def test_the_garrison_follows_the_controller():
    game = _game()
    w, c = game.state.world, game.content
    assert territory.squads_at(w, c, "runan_wilds") == ["louluo", "shuikou"]
    _push(game, "yingru", -10)  # 30：汝南荒野歸官軍
    assert territory.squads_at(w, c, "runan_wilds") == ["guan_patrol", "jun_bing"]
    assert territory.squads_at(w, c, "yu_river") == ["he_shuikou", "guan_patrol"]  # 流寇不管誰控制都在、排前面
    assert territory.squads_at(w, c, "changshe") == ["guan_patrol", "jun_bing"]  # 長社改站官軍
    assert territory.squads_at(w, c, "huangjin_camp") == c.locations["huangjin_camp"].enemies  # 沒寫 garrison 的照 enemies


def test_siege_places_and_strike_bounties_follow_control():
    game = _game()
    w, c = game.state.world, game.content
    assert orders.siege_places(c, "huang", "yingru", w) == ["changshe", "guan_camp"]
    assert orders.siege_places(c, "guan", "yingru", w) == ["runan_wilds", "huangjin_camp"]
    guan_targets = bounties._strike_spots(c, w, "guan", set())  # 官軍掛的討伐：打黃巾
    assert ("runan_wilds", "louluo") in guan_targets and not any(loc == "changshe" for loc, _ in guan_targets)
    assert ("changshe", "guan_patrol") in bounties._strike_spots(c, w, "huang", set())


def test_the_switch_off_has_no_controller_and_the_old_enemies():
    game = _game()
    c = classic_rules(game.content)
    assert _owner(game, "runan_wilds") is None
    assert territory.squads_at(game.state.world, c, "changshe") == c.locations["changshe"].enemies


def test_opening_a_prepared_season_starts_the_map_over(tmp_path):
    c = real_content("weekend")
    store = open_world(tmp_path / "w.db")
    store.seed_first_season(c)
    season = store.get_season()
    season.territory = TerritoryState(control={"runan_wilds": "haoqiang"})
    store.save_season(season)
    assert store.open_season(c, now=0.0)
    assert store.get_season().territory is None


def test_the_territory_content_is_checked():
    c = real_content()
    c.scenario.territory.lines["yingru"].append("changshe")
    with pytest.raises(ContentError, match="大本營"):
        validate(c)
