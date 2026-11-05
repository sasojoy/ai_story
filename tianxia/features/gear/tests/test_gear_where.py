"""FB-138：修練頁「裝備」那一塊，每一段都要說得出「哪裡買得到、哪裡得來」——新角色身上什麼都沒有時，網頁畫一塊精簡的（見 tests/test_weapons_web.py），
地點資料出在 skillview.gear_rows 每一段的 where：鐵匠鋪看「城鎮」標籤、馬市看「馬市」標籤、寶物寫來源，一律從內容讀，不寫死地名。"""
from __future__ import annotations

import random

from conftest import real_content
from tianxia import equipment, mounts, skillview, treasures
from tianxia.engine import Game


def _on(content):
    """測試內容四欄都關著：全打開。"""
    for rule in (content.config.weapons, content.config.armor, content.config.mounts, content.config.treasures):
        rule.enabled = True
    return content


def _game(content, world, at):
    game = Game.new(content, "尋裝", rng=random.Random(0), world=world)
    game.client = None
    game.sync(0.0)
    game.state.player.location = at
    return game


def _where(game, world):
    return {s["slot"]: s["where"] for s in skillview.gear_rows(game.state, game.content, world)["slots"]}


def test_each_slot_says_where_to_get_one(content, world):
    """測試內容：小鎮是城鎮、湖邊不是；沒有任何地點帶「馬市」。鐵匠鋪那兩段站在城鎮多一句「此地就有」；馬市內容裡沒有就不寫；寶物寫來源。"""
    game = _game(_on(content), world, "town")
    where = _where(game, world)
    assert list(where) == ["weapon", "armor", "mount", "treasure"]
    assert where["weapon"] == where["armor"] == equipment.SMITH_WHERE + equipment.WHERE_HERE
    assert where["mount"] == ""  # 這份內容沒有馬市：沒有地方可指，就不寫
    assert where["treasure"] == treasures.WHERE
    game.state.player.location = "lake"  # 湖邊不是城鎮
    away = _where(game, world)
    assert away["weapon"] == away["armor"] == equipment.SMITH_WHERE
    assert equipment.WHERE_HERE not in away["weapon"]


def test_the_mount_slot_lists_every_market_by_name_from_the_content(content, world):
    _on(content)
    content.locations["town"].tags.append(mounts.MARKET_TAG)
    content.locations["lake"].tags.append(mounts.MARKET_TAG)
    game = _game(content, world, "cave")
    assert _where(game, world)["mount"] == mounts.MARKET_WHERE.format(names="小鎮、湖邊")  # 內容的先後，名字用內容的
    game.state.player.location = "town"
    assert _where(game, world)["mount"] == mounts.MARKET_WHERE.format(names="小鎮、湖邊") + equipment.WHERE_HERE


def test_a_content_without_towns_names_no_smithy(content, world):
    _on(content)
    for loc in content.locations.values():
        loc.tags = [t for t in loc.tags if t != equipment.TOWN_TAG]
    where = _where(_game(content, world, "lake"), world)
    assert where["weapon"] == where["armor"] == ""


def test_a_closed_slot_has_no_section_to_say_anything_in(content, world):
    content.config.mounts.enabled = True
    assert list(_where(_game(content, world, "town"), world)) == ["mount"]


def test_the_real_content_names_its_four_markets_and_a_new_player_stands_in_a_smithy_town():
    """正式內容：馬市就是帶「馬市」標籤的地點（涿郡、汝南集市、宛城、下曲陽），名字照 locations.json 的先後；開局的潁川是城鎮、不是馬市。"""
    from tianxia.sqlite_world import open_world
    c = _on(real_content())
    names = [loc.name for loc in c.locations.values() if mounts.MARKET_TAG in loc.tags]
    assert sorted(names) == sorted(["涿郡", "汝南集市", "宛城", "下曲陽"])
    world = open_world()
    game = _game(c, world, "yingchuan")
    where = _where(game, world)
    assert where["mount"] == mounts.MARKET_WHERE.format(names="、".join(names))  # 這裡不是馬市：不寫「此地就有」
    assert where["weapon"].endswith(equipment.WHERE_HERE) and where["armor"].endswith(equipment.WHERE_HERE)  # 潁川有鐵匠鋪


def test_the_practice_page_carries_where_to_the_web(content, world):
    import server
    game = _game(_on(content), world, "town")
    sent = {s["slot"]: s["where"] for s in server.menxia_view(game)["gear"]["slots"]}
    assert sent == _where(game, world)
