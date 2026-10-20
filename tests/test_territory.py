"""地盤易手（docs/superpowers/specs/2026-10-14-出陣探索與地盤-design.md 第四節）。正式內容、週末設定（第一季規則開著）。
開季的戰線：潁川汝南 40、南陽 35、冀州 55、割據 10。
輿圖重製第 1 批（新天下）：大勢值整個中原一個總值（企劃者 2026-10-21，暫用 yingru 那一條），舊拔河只剩中原那一條線的九處
（官軍大營、長社、黃巾別部營寨、白馬津、盧植營、汝南荒野、南陽黃巾營、官渡、己吾；第 j 處的門檻 75－50×(j－0.5)÷9），
南陽、冀州的舊線只剩大本營與 fixed。量的規則不變，換成這一條線上的地點與門檻：南陽黃巾營是第 7 處（門檻 38.9，開季 40 歸黃巾）。"""
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
    "guan_camp": "guan", "changshe": "guan", "huangjin_camp": "guan", "baima_ford": "guan", "luzhi_camp": "guan",
    "runan_wilds": "guan", "nanyang_huangjin_camp": "huang", "guandu": "huang", "jiwu": "huang",
    "dajiangjun_fu": "guan", "wan_city": "guan", "julu_altar": "huang", "qingzhou_camp": "huang", "guangzong": "huang",
}
SPOT, SPOT_NAME = "nanyang_huangjin_camp", "南陽黃巾營"  # 中原那一條線的第 7 處：門檻 38.9（±5：33.9 以下歸官軍、43.9 以上歸黃巾）


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
    assert territory.line_of(c, "changshe") == "yingru" and territory.line_of(c, "guangzong") == "jizhou"
    assert territory.line_of(c, "luoyang_road") is None and territory.line_of(c, "mengjin_ford") is None  # 寫的是 front，洛陽沒有戰線
    assert territory.line_of(c, "dajiangjun_fu") is None and territory.line_of(c, "xiaquyang") is None  # 投靠點、外圈：不在戰線上
    assert territory.bases(c)["wan_city"] == "guan" and territory.bases(c)["haozu_fort"] == "haoqiang"
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
    assert _owner(game, SPOT) == "huang"  # 照規則現算
    _push(game, "yingru", 2)  # 42：第一次重算，不發天下大事
    assert w.territory is not None and _flips(game) == []
    _push(game, "yingru", -12)  # 30
    assert _owner(game, SPOT) == "guan"
    assert _flips(game) == [territory.FLIP_LINE.format(place=SPOT_NAME, side="官軍")]
    assert w.chronicle[-1].text == _flips(game)[0]


def test_the_band_stops_flapping_on_the_threshold():
    """南陽黃巾營的門檻 38.9：34～43 之間都不動，越過 33.9 歸官軍、越過 43.9 歸黃巾，各發一句。"""
    game = _game()
    for delta in (-4, -2):  # 36、34
        _push(game, "yingru", delta)
        assert _owner(game, SPOT) == "huang"
    _push(game, "yingru", -1)  # 33
    assert _owner(game, SPOT) == "guan"
    for delta in (8, 2, -1, 1):  # 41、43、42、43
        _push(game, "yingru", delta)
        assert _owner(game, SPOT) == "guan"
    _push(game, "yingru", 1)  # 44
    assert _owner(game, SPOT) == "huang"
    for delta in (-1, 1, -1):  # 43、44、43
        _push(game, "yingru", delta)
    assert _owner(game, SPOT) == "huang" and len(_flips(game)) == 2


def test_the_gentry_takes_the_spot_nearest_each_front_and_gives_it_back():
    game = _game()
    _push(game, "geju", 50)  # 60：每條線門檻最近此刻戰線的一處（新天下只剩中原那一條：門檻 38.9 的南陽黃巾營）
    assert _owner(game, SPOT) == "haoqiang"
    _push(game, "geju", 20)  # 80：再一處（門檻 44.4 的汝南荒野）
    assert _owner(game, "runan_wilds") == "haoqiang"
    assert len(_flips(game)) == 2
    _push(game, "geju", -25)  # 55：還在 50 以上，手上的不動
    assert _owner(game, "runan_wilds") == "haoqiang" and len(_flips(game)) == 2
    _push(game, "geju", -10)  # 45：全部交還給拔河
    assert {loc: _owner(game, loc) for loc in OPENING} == OPENING and len(_flips(game)) == 4


def test_a_big_event_hands_a_spot_over_until_the_rule_changes():
    game = _game()
    w, c = game.state.world, game.content
    territory.assign(w, c, {SPOT: "guan"})  # 規則此刻算黃巾
    assert _owner(game, SPOT) == "guan" and len(_flips(game)) == 1
    _push(game, "yingru", 2)  # 42：規則還是黃巾，指定的留著
    assert _owner(game, SPOT) == "guan"
    _push(game, "yingru", -10)  # 32：規則變成官軍——回到規則（還是官軍，不發）
    assert _owner(game, SPOT) == "guan" and SPOT not in w.territory.pinned
    _push(game, "yingru", 12)  # 44
    assert _owner(game, SPOT) == "huang" and len(_flips(game)) == 2


def test_a_pinned_spot_goes_to_the_gentry_when_the_gentry_rises():
    """Review Focus 3：大事剛把南陽黃巾營交給官軍，割據漲到 60 選中它——規則算出來的控制方變了，指定作廢、歸豪強。"""
    game = _game()
    territory.assign(game.state.world, game.content, {SPOT: "guan"})
    _push(game, "geju", 50)
    assert _owner(game, SPOT) == "haoqiang" and SPOT not in game.state.world.territory.pinned
    assert territory.FLIP_LINE.format(place=SPOT_NAME, side="地方豪強") in _flips(game)


def test_bases_never_change_hands_and_guangzong_moves_only_with_its_battle():
    game = _game()
    s, c = game.state, game.content
    _push(game, "jizhou", 45)  # 100
    assert _owner(game, "guangzong") == "huang" and _owner(game, "wan_city") == "guan"
    territory.assign(s.world, c, {"wan_city": "huang"})  # 大本營不收
    assert _owner(game, "wan_city") == "guan"
    timetable.resolve(s, c, timetable.find(c, "guangzong"), random.Random(0), key="guan:大勝")
    assert _owner(game, "guangzong") == "guan"
    _push(game, "jizhou", 50)
    assert _owner(game, "guangzong") == "guan"


def test_the_garrison_follows_the_controller():
    game = _game()
    w, c = game.state.world, game.content
    assert territory.squads_at(w, c, SPOT) == ["shuikou", "huangjin_sishi"]
    _push(game, "yingru", -10)  # 30：南陽黃巾營歸官軍
    assert territory.squads_at(w, c, SPOT) == ["guan_patrol", "jun_bing"]
    assert territory.squads_at(w, c, "baima_ford") == ["he_shuikou", "jun_bing"]  # 流寇不管誰控制都在、排前面
    assert territory.squads_at(w, c, "changshe") == ["guan_patrol", "jun_bing"]  # 長社站官軍
    assert territory.squads_at(w, c, "julu_altar") == c.locations["julu_altar"].enemies  # 沒寫 garrison 的照 enemies


def test_siege_places_and_strike_bounties_follow_control():
    game = _game()
    w, c = game.state.world, game.content
    assert orders.siege_places(c, "huang", "yingru", w) == ["changshe", "runan_wilds", "guan_camp", "huangjin_camp", "luzhi_camp",
                                                             "baima_ford"]
    assert orders.siege_places(c, "guan", "yingru", w) == [SPOT, "guandu", "jiwu"]
    guan_targets = bounties._strike_spots(c, w, "guan", set())  # 官軍掛的討伐：打黃巾
    assert (SPOT, "shuikou") in guan_targets and not any(loc == "changshe" for loc, _ in guan_targets)
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
    c.scenario.territory.lines["nanyang"] = ["wan_city"]  # 宛城是官軍的投靠點（新天下南陽那條舊線上只剩它）
    with pytest.raises(ContentError, match="大本營"):
        validate(c)
