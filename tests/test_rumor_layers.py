"""傳聞分層（一）：聽得到什麼（計畫 2026-10-06-傳聞分層-1-聽得到什麼）。

用真實內容（content/）：要驗的是真實的五個大區（潁川汝南、南陽、冀州、幽州、洛陽）、地點與陣營。每個測試自己載一份，
開關在 fixture 裡才打開；開關開著的季是「蓋了章」的（auto_open_first_season 開出來的季照當下的 Config 蓋章）。
週末設定（季長 2.5 天）的季曆一天是 86400 ÷ 33.6 ≈ 2571 個世界秒。"""
from __future__ import annotations

import random
from pathlib import Path

import pytest

import server
from tianxia import atlas, foreshadow, journal, mapview, orders, ranks, rules, rumor_view, timetable
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


# ── Task 3：輿圖的 ✦、詳情欄、龍頭人物的近況 ─────────────────


def _story_marks(game) -> dict[str, str]:
    """劇情層每個地點名字前的記號（假裝每一處都摸清了，只看 ✦ 標不標）。"""
    views = {loc_id: "visible" for loc_id in game.content.locations}
    prefixes, _, _ = mapview._layer_marks(game.state, game.content, "story", views, None)
    return prefixes


def test_the_map_marks_only_places_you_can_hear(on):
    game = _game(on, "甲", "guan", at="yingchuan")
    _rumor(game, "長社一帶有人鬧事。", "changshe")  # 潁川汝南：人就在這一區
    _rumor(game, "宛城一帶有人鬧事。", "wan_city")  # 南陽：別的大區
    _rumor(game, "鉅鹿出了大事。", "julu_altar", layer="world")  # 天下大事：人人聽得到
    _rumor(game, "黃巾在盧植營外佈了暗哨。", "luzhi_camp", layer="faction", faction="huang")  # 敵方的軍情
    assert atlas.news_places(game.state, on) == {"changshe", "julu_altar"}
    marks = _story_marks(game)
    assert "✦" in marks.get("changshe", "") and "✦" in marks.get("julu_altar", "")
    assert "✦" not in marks.get("wan_city", "") and "✦" not in marks.get("luzhi_camp", "")


def test_the_star_clears_after_three_calendar_days(on):
    """週末那一季只有 2.5 個世界天：以前看世界天的「3 天」整季都不會過，✦ 永遠不消；現在看季曆天（約 2.1 個現實小時）。"""
    game = _game(on, at="yingchuan")
    day = _day(game)
    _rumor(game, "鉅鹿出了大事。", "julu_altar", layer="world", time=0.0)
    game.state.world.time = 3 * day - 1
    assert atlas.news_places(game.state, on) == {"julu_altar"}
    game.state.world.time = 3 * day + 1
    assert atlas.news_places(game.state, on) == set()
    assert "最近 3 天沒有大事或傳聞" in atlas.detail_text(game.state, on, "yingchuan", lambda squad: "穩勝")


def test_the_detail_panel_lists_only_what_you_can_hear(on):
    game = _game(on, at="yingchuan")
    game.state.player.visited |= {"changshe", "wan_city"}  # 去過：兩處都摸清了
    _rumor(game, "長社一帶有人鬧事。", "changshe")
    _rumor(game, "宛城一帶有人鬧事。", "wan_city")
    odds = lambda squad: "穩勝"  # noqa: E731
    assert "長社一帶有人鬧事。" in atlas.detail_text(game.state, on, "changshe", odds)
    there = atlas.detail_text(game.state, on, "wan_city", odds)
    assert "宛城一帶" not in there and "最近 3 天沒有大事或傳聞" in there
    assert [r.text for r in atlas.recent_news(game.state, on, "changshe")] == ["長社一帶有人鬧事。"]


def test_a_leaders_recent_news_skips_what_you_cannot_hear(on):
    game = _game(on, at="yingchuan")
    _rumor(game, "張曼成在宛城點兵。", "wan_city")
    _rumor(game, "有人在長社說起張曼成。", "changshe")
    assert [r.text for r in atlas.leader_news(game.state, on, "張曼成")] == ["有人在長社說起張曼成。"]


def test_with_the_switch_off_the_map_marks_like_before(real):
    """beta 那一季：別的大區的地方傳聞照標，「3 天」是世界天。"""
    game = _game(real, at="yingchuan")
    _rumor(game, "宛城一帶有人鬧事。", "wan_city", time=0.0)
    game.state.world.time = 2 * 86400
    assert atlas.news_places(game.state, real) == {"wan_city"}
    assert "✦" in _story_marks(game).get("wan_city", "")


@pytest.mark.parametrize("days", [1, 5])
def test_the_star_window_is_the_board_length_so_a_local_star_never_outlives_its_rumor(on, days):
    """✦ 的「最近幾天」跟傳聞板同一個旋鈕（Config.rumor_board_days），不再是另一個寫死的 3：
    板子留 1 天時天下大事的 ✦ 也 1 天就收；板子留 5 天時本區的 ✦ 跟著留 5 天（以前 3 天就先消了）。"""
    on.config.rumor_board_days = days
    game = _game(on, at="yingchuan")
    day = _day(game)
    game.state.world.time = 10 * day
    edge = (10 - days) * day  # 板上最舊的那一刻
    _rumor(game, "長社剛出的事。", "changshe", time=edge + 1)  # 本區、還在板上
    _rumor(game, "潁川更早的事。", "yingchuan", time=edge - 1)  # 本區、剛撤板
    _rumor(game, "鉅鹿剛出的大事。", "julu_altar", layer="world", time=edge + 1)
    _rumor(game, "盧植營更早的大事。", "luzhi_camp", layer="world", time=edge - 1)  # 天下大事，也過了 ✦ 的天數
    assert atlas.news_places(game.state, on) == {"changshe", "julu_altar"}
    game.state.player.visited.add("luzhi_camp")
    odds = lambda squad: "穩勝"  # noqa: E731
    assert f"最近 {days} 天沒有大事或傳聞" in atlas.detail_text(game.state, on, "luzhi_camp", odds)


# ── Task 4：見聞頁分四層 ───────────────────────────────────


def _layers(game) -> dict[str, dict[str, str]]:
    return {layer["id"]: layer for layer in game.rumor_layers()}


def test_the_news_page_splits_rumors_into_four_layers(on):
    game = _game(on, "甲", "guan", at="yingchuan")
    _rumor(game, "鉅鹿出了大事。", "julu_altar", layer="world")
    _rumor(game, "本週軍令：守長社。", layer="faction", faction="guan")
    _rumor(game, "本週軍令：圍長社。", layer="faction", faction="huang")
    _rumor(game, "長社一帶有人鬧事。", "changshe")
    _rumor(game, "宛城一帶有人鬧事。", "wan_city")
    game.state.world.rumors.append(Rumor(time=0.0, text="只說給甲聽的。", layer="personal", character="甲"))
    assert [layer["id"] for layer in game.rumor_layers()] == ["world", "faction", "local", "personal"]
    layers = _layers(game)
    assert [layers[k]["title"] for k in layers] == ["天下大事", "陣營軍情", "潁川汝南的傳聞（最近 3 天）", "個人線索"]
    assert "鉅鹿出了大事。" in layers["world"]["body"]
    assert "守長社" in layers["faction"]["body"] and "圍長社" not in layers["faction"]["body"]
    assert "長社一帶" in layers["local"]["body"] and "宛城一帶" not in layers["local"]["body"]
    assert "只說給甲聽的。" in layers["personal"]["body"]
    assert "第 1 週・週一 00:00　鉅鹿出了大事。" in layers["world"]["body"]  # 時間照季曆寫，跟以前那一條清單一樣


def test_each_layer_says_so_when_it_is_empty(on):
    layers = _layers(_game(on, "甲", "guan"))
    assert layers["world"]["body"] == rumor_view.WORLD_EMPTY
    assert layers["faction"]["body"] == rumor_view.FACTION_EMPTY
    assert layers["local"]["body"] == rumor_view.LOCAL_EMPTY
    assert layers["personal"]["body"] == rumor_view.PERSONAL_EMPTY


def test_a_loner_gets_a_note_instead_of_faction_news(on):
    game = _game(on, "丙")
    _rumor(game, "本週軍令：守長社。", layer="faction", faction="guan")
    assert _layers(game)["faction"]["body"] == rumor_view.FACTION_LONER


def test_on_the_road_the_local_layer_names_both_regions(on):
    game = _on_the_road(_game(on, at="yingchuan"))
    _rumor(game, "洛陽宮裡出了事。", "luoyang_palace")
    local = _layers(game)["local"]
    assert local["title"] == "洛陽、潁川汝南的傳聞（最近 3 天）" and "洛陽宮裡出了事。" in local["body"]  # 照地圖的大區順序


def test_heard_clues_are_personal_and_only_yours(on):
    jia, yi = _game(on, "甲", "guan"), _game(on, "乙", "guan")
    chain = next(c for c in on.foreshadows.chains if c.side == "guan" and c.fragments)
    jia.state.player.fragments[chain.id] = [0]
    clues = foreshadow.heard_texts(jia.state, on, jia.world)
    assert len(clues) == 1 and clues[0] in _layers(jia)["personal"]["body"]
    assert _layers(yi)["personal"]["body"] == rumor_view.PERSONAL_EMPTY  # 片段是一個人一個人聽的


def test_with_the_switch_off_there_are_no_layers(real):
    game = _game(real)
    assert game.rumor_layers() is None
    assert foreshadow.heard_texts(game.state, real, game.world) == []


@pytest.fixture
def server_season_one(monkeypatch):
    """server.CONTENT 是正式內容：照週末設定打開第一季、季已經開打（同 tests/test_server.py 的 season_already_open）。"""
    config = server.CONTENT.config
    monkeypatch.setattr(config, "auto_open_first_season", True)
    monkeypatch.setattr(config, "season_one", True)
    monkeypatch.setattr(config, "season_days", 2.5)
    return server.CONTENT


def test_the_main_view_sends_the_layers_and_keeps_the_old_list(server_season_one):
    game = Game.new(server_season_one, "測試")
    _rumor(game, "長社一帶有人鬧事。", "changshe")
    view = server.main_view(game)
    assert [layer["id"] for layer in view["rumor_layers"]] == ["world", "faction", "local", "personal"]
    local = view["rumor_layers"][2]
    assert local["title"] == "潁川汝南的傳聞（最近 3 天）" and "<p>" in local["body"] and "長社一帶有人鬧事。" in local["body"]
    assert "長社一帶有人鬧事。" in view["rumors"]  # 舊的一條清單照送（別的地方不會壞）


def test_the_main_view_has_no_layers_with_the_switch_off(monkeypatch):
    monkeypatch.setattr(server.CONTENT.config, "auto_open_first_season", True)
    view = server.main_view(Game.new(server.CONTENT, "測試"))
    assert "rumor_layers" not in view and "rumors" in view


def _js_function(js: str, header: str) -> str:
    """app.js 裡 IIFE 內的一個函式本體（同 tests/test_server.py 的 _js_function）。"""
    start = js.index(header)
    return js[start:js.index("\n  }\n", start)]


def test_the_page_draws_the_layers_when_the_server_sends_them():
    """網頁沒有測試框架：擋住「伺服器送了四層、網頁卻還畫一整張」與「每次輪詢都重畫」。"""
    js = (server.WEB / "app.js").read_text(encoding="utf-8")
    assert "m.rumor_layers ? rumorLayersHtml(m.rumor_layers)" in _js_function(js, "function pageNews(")
    layers = _js_function(js, "function rumorLayersHtml(")
    assert "esc(l.title)" in layers and "${l.body}" in layers  # 標題跳脫；內容是伺服器跳脫過的 HTML
    refresh = _js_function(js, "async function refreshPage(")
    assert 'rumors: ["rumors", "rumor_layers"]' in refresh and "JSON.stringify(old[k])" in refresh


# ── Task 5：你不在的時候 ───────────────────────────────────

T0 = 1000.0  # 第一次同步的現實時間（秒）
HOUR = 3600


@pytest.fixture
def slow(on):
    """季的時鐘幾乎不走（現實一小時＝季的 3.6 秒）：不會冒出軍令、大事這些自己發生的傳聞，只看測試放進去的。
    「你不在的時候」看的是現實時間，季走得再慢也照樣算離線。"""
    on.config.time_scale = 0.001
    return on


def _put(world, *rumors: Rumor) -> None:
    """往資料庫裡的這一季放幾則傳聞（別人在你離線時做的事）。"""
    world.mutate_season(lambda season: season.rumors.extend(rumors))


def _away(game):
    """江湖紀錄最新那一則是「你不在的時候」就回它，否則 None。"""
    head = game.state.journal[0] if game.state.journal else None
    return head if head is not None and head.title == journal.AWAY else None


def test_coming_back_after_an_hour_gets_a_summary_in_order(slow, world):
    jia = _game(slow, "甲", "guan", world=world)
    jia.sync(T0)
    _put(
        world,
        Rumor(time=1.0, text="天下事甲。", layer="world"),
        Rumor(time=1.5, text="本週軍令：守長社。", layer="faction", faction="guan"),
        Rumor(time=1.6, text="昨日升為屯長的有：乙。", layer="faction", faction="guan"),  # 晉升彙整不是要點
        Rumor(time=1.7, text="本週軍令：圍長社。", layer="faction", faction="huang"),  # 敵方的軍情聽不到
        Rumor(time=2.0, text="長社事。", location="changshe", layer="local", region="yingru"),
        Rumor(time=2.2, text="宛城事。", location="wan_city", layer="local", region="nanyang"),  # 別的大區
        Rumor(time=2.5, text="天下事乙。", layer="world"),
    )
    jia.sync(T0 + HOUR)
    entry = _away(jia)
    at = jia.stamp
    assert entry.tag == "共 4 則"
    assert entry.lines == [
        f"〔天下大事〕{at(1.0)}　天下事甲。",
        f"〔天下大事〕{at(2.5)}　天下事乙。",
        f"〔陣營軍情〕{at(1.5)}　本週軍令：守長社。",
        f"〔潁川汝南〕{at(2.0)}　長社事。",
    ]
    assert journal.AWAY in jia.now_entry_html()  # 江湖頁的「剛剛」先放這一份


def test_less_than_an_hour_away_gets_nothing_and_the_next_summary_starts_from_there(slow, world):
    jia = _game(slow, "甲", "guan", world=world)
    jia.sync(T0)
    _put(world, Rumor(time=1.0, text="舊事。", layer="world"))
    jia.sync(T0 + HOUR - 1)
    assert _away(jia) is None
    mark = jia.state.last_world
    assert mark == pytest.approx((HOUR - 1) * 0.001)
    _put(world, Rumor(time=mark + 1, text="新事。", layer="world"))
    jia.sync(T0 + 3 * HOUR)
    assert [line.split("　")[1] for line in _away(jia).lines] == ["新事。"]


def test_the_timetable_big_events_are_not_summarised_twice(slow, world):
    """時刻表的大事由 _deliver_big_events 補成「江湖大事」那一則（FB-038），摘要不再寫一次。"""
    jia = _game(slow, "甲", "guan", world=world)
    jia.sync(T0)

    def _settled(season):
        season.timeline["uprising"] = TimelineResult(key="fixed", time=1.0, text="三十六方同日起事。")
        season.rumors += [Rumor(time=1.0, text="三十六方同日起事。", layer="world"),
                          Rumor(time=2.0, text="天下事甲。", layer="world")]

    world.mutate_season(_settled)
    jia.sync(T0 + HOUR)
    assert [line.split("　")[1] for line in _away(jia).lines] == ["天下事甲。"]
    assert any(e.title == journal.WORLD_NEWS and e.tag == "三十六方同日起事。" for e in jia.state.journal)


def test_the_summary_keeps_twenty_and_points_to_the_news_page(slow, world):
    jia = _game(slow, "甲", "guan", world=world)
    jia.sync(T0)
    _put(world, *(Rumor(time=float(i), text=f"天下事{i}。", layer="world") for i in range(1, 23)))
    _put(world, Rumor(time=30.0, text="長社事。", layer="local", region="yingru"))
    jia.sync(T0 + HOUR)
    entry = _away(jia)
    assert entry.tag == "共 23 則"
    shown = [line.split("　")[1] for line in entry.lines[:-1]]
    assert shown == [f"天下事{i}。" for i in range(3, 23)]  # 放不下時留最近的；天下大事先放滿，地方的就放不進來
    assert entry.lines[-1] == "另有 3 則沒列出來，到「見聞」的傳聞翻。"


def test_the_cap_comes_from_the_config(slow, world):
    slow.config.away_max = 2
    jia = _game(slow, "甲", "guan", world=world)
    jia.sync(T0)
    _put(world, Rumor(time=1.0, text="天下事甲。", layer="world"),
         Rumor(time=2.0, text="本週軍令：守長社。", layer="faction", faction="guan"),
         Rumor(time=3.0, text="長社事。", layer="local", region="yingru"))
    jia.sync(T0 + HOUR)
    assert [line.split("　")[-1] for line in _away(jia).lines] == ["天下事甲。", "本週軍令：守長社。", "另有 1 則沒列出來，到「見聞」的傳聞翻。"]


def test_server_bots_and_brand_new_characters_get_no_summary(slow, world):
    bot = _game(slow, "甲", "guan", world=world)
    bot.state.player.bot = BotProfile(personality="普通", seed=1, faction="guan", season_number=1)
    bot.sync(T0)
    _put(world, Rumor(time=1.0, text="天下事甲。", layer="world"))
    bot.sync(T0 + 5 * HOUR)
    assert _away(bot) is None
    late = _game(slow, "乙", "guan", world=world)  # 第一次同步：還沒有「上次」，不算回來
    late.sync(T0 + 6 * HOUR)
    assert _away(late) is None


def test_an_old_save_without_a_mark_gets_the_season_so_far(slow, world):
    jia = _game(slow, "甲", "guan", world=world)
    jia.sync(T0)
    _put(world, Rumor(time=0.0, text="開季那一刻的事。", layer="world"))
    jia.state.last_world = None  # 這個欄位加上之前存的角色
    jia.sync(T0 + HOUR)
    assert [line.split("　")[1] for line in _away(jia).lines] == ["開季那一刻的事。"]


def test_fast_forwarding_the_season_is_not_being_away(slow, world):
    """看的是現實時間：季被快轉了三天（管理者快轉），十秒後同步不算離線；季的時鐘沒怎麼走，離線一小時照樣算（上面幾條）。"""
    jia = _game(slow, "甲", "guan", world=world)
    jia.sync(T0)
    jia.advance(3 * _day(jia))
    _put(world, Rumor(time=jia.state.world.time, text="天下事甲。", layer="world"))
    jia.sync(T0 + 10)
    assert _away(jia) is None


def test_with_the_switch_off_there_is_no_summary(real, world):
    real.config.time_scale = 0.001
    jia = _game(real, "甲", world=world)
    jia.sync(T0)
    _put(world, Rumor(time=1.0, text="天下事甲。", layer="world"))
    jia.sync(T0 + 5 * HOUR)
    assert _away(jia) is None


def test_a_real_season_rollover_restarts_the_summary_from_the_new_season(slow, world):
    """換季重來（走真的 next_season，不是手動把 last_world 設成 None）：角色整個重來，last_world 跟著回到「還沒記過」，
    隔了一個多小時回來時從新的一季開頭算；上一季的傳聞不會冒進這一份，現實時間的同步點（last_real）照樣留著。"""
    slow.config.admins = ["乙"]
    jia, admin = _game(slow, "甲", "guan", world=world), _game(slow, "乙", "guan", world=world)
    jia.sync(T0)
    _put(world, Rumor(time=1.0, text="上一季的事。", layer="world"))
    jia.advance(3 * 86400)  # 季走到尾、收季
    assert jia.state.world.ended
    jia.sync(T0 + 10)
    old_mark = jia.state.last_world
    assert old_mark is not None and old_mark > 1000 and jia.state.player.season_number == 1  # 上一季的賽季時間很大
    admin.sync(T0 + 11)
    admin.admin_next_season(now=T0 + 20)
    _put(world, Rumor(time=1.0, text="新一季的事。", layer="world"))  # 新一季的時間從 0 起算：標記要是帶過來就會漏掉它
    jia.sync(T0 + 10 + 2 * HOUR)  # 甲離線的這兩個小時，季換了
    assert jia.state.player.season_number == 2
    entry = _away(jia)
    assert [line.split("　")[1] for line in entry.lines] == ["新一季的事。"]
    assert jia.state.last_world == jia.state.world.time and jia.state.last_real == T0 + 10 + 2 * HOUR
