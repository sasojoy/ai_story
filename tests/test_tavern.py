"""酒肆（tianxia/tavern.py；企劃者 2026-10-18「可以，做精緻一些，包含氛圍感」）第一批：進門、聽消息、查人、交情、素材、題壁、請酒、
藏行跡、反查、風聲。正式內容、週末設定；宛城、潁川郡帶「酒肆」標籤，黃巾大營沒有。"""
from __future__ import annotations

import random

from conftest import real_content
from tianxia import tavern
from tianxia.characters import CharacterStore
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

NOW = 16 * 3600 + 3600


def _content():
    c = real_content("weekend")
    c.config.auto_open_first_season = True
    return c


def _game(name="沈浪", at="wan_city", silver=500, world=None, content=None, faction=None):
    c = content or _content()
    game = Game.new(c, name, rng=random.Random(0), world=world or open_world())
    game.client = None
    p = game.state.player
    p.location, p.faction = at, faction
    p.tutorial_step = len(c.tutorial.steps)
    p.stats["silver"] = silver
    game.now = NOW
    p.seen_real = NOW
    CharacterStore(game.world.db).save(game.state)
    return game


def _ids(game):
    return {o.id: o for o in game.options()}


def test_only_towns_with_a_tavern_have_one():
    assert "act:tavern" in _ids(_game())
    assert "act:tavern" in _ids(_game(at="yingchuan"))
    assert "act:tavern" not in _ids(_game(at="runan_academy"))  # 汝南學宮是城鎮，沒有酒肆
    assert "act:tavern" not in _ids(_game(at="huangjin_camp"))


def test_entering_opens_the_tavern_page_and_blocks_travel():
    game = _game()
    msgs = game.choose("act:tavern")
    assert msgs and "宛城・酒肆" in msgs[0]
    ids = _ids(game)
    assert tavern.BACK_ID in ids and tavern.NEWS_ID in ids
    view = game.shop_view()
    assert view["shop"] == "tavern" and view["sign"] == "宛城・酒肆" and view["line"]
    assert len(view["chatter"]) == 2 and all(row["who"] and row["said"] for row in view["chatter"])
    assert "act:explore" not in ids  # 坐在酒肆裡：選單卡在酒肆那一串
    game.choose(tavern.BACK_ID)
    assert not game.state.player.picking_tavern
    assert "act:explore" in _ids(game)


def test_prices_follow_the_season_length():
    game = _game()
    full = game.content.config.tavern.news_price
    assert game._tavern_price(full) <= full
    assert game._tavern_price(0) == 0


def test_news_charges_once_and_does_not_repeat():
    game = _game()
    w = game.state.world
    from tianxia.rules import add_rumor
    add_rumor(game.state, "皇甫嵩移往長社，黃巾聲勢稍退。", "changshe", content=game.content, layer="world")
    game.choose("act:tavern")
    before = game.state.player.stats["silver"]
    msgs = game.tavern_do("news")
    price = game._tavern_price(game.content.config.tavern.news_price)
    assert game.state.player.stats["silver"] == before - price
    assert any("皇甫嵩移往長社" in m for m in msgs)
    assert game.state.journal[0].title == "宛城・酒肆"
    assert game.state.player.tavern_notes[-1].kind == "news"
    assert w.rumors  # 傳聞還在季上
    again = game.tavern_do("news")
    assert not any("皇甫嵩移往長社" in m for m in again)  # 聽過的不再說


def test_seeking_a_famous_player_names_the_place_and_whispers_to_him():
    world = open_world()
    c = _content()
    me = _game(world=world, content=c)
    other = _game("李尋歡", at="wan_city", world=world, content=c)
    other.state.player.stats["fame"] = 10_000  # 名望頂段
    other.state.player.seen_real = NOW
    CharacterStore(world.db).save(other.state)
    me.choose("act:tavern")
    msgs = me.tavern_do("seek", "李尋歡")
    assert any("宛城" in m for m in msgs)
    assert "李尋歡" in me.state.player.tavern_known
    me._save_season()
    other.sync(NOW + 10)
    assert other.state.player.whispers and other.state.player.whispers[-1].kind == "seek"
    assert any(e.title == tavern.WHISPER_TITLE for e in other.state.journal)


def test_an_unknown_name_and_an_obscure_player_read_the_same_and_refund_half():
    world = open_world()
    c = _content()
    me = _game(world=world, content=c)
    far = _game("無名氏", at="xiaquyang", world=world, content=c)  # 默默無名、離得遠
    far.state.player.stats["fame"] = 0
    CharacterStore(world.db).save(far.state)
    me.choose("act:tavern")
    price = me._tavern_price(c.config.tavern.seek_price)
    back = int(price * c.config.tavern.refund_share)
    before = me.state.player.stats["silver"]
    a = me.tavern_do("seek", "查無此人")
    assert me.state.player.stats["silver"] == before - price + back
    b = me.tavern_do("seek", "無名氏")
    assert a[0].split("（")[0] in (tavern.NOBODY.split("（")[0], tavern.HALF_MISS.split("（")[0])
    assert b[0].split("（")[0] in (tavern.NOBODY.split("（")[0], tavern.HALF_MISS.split("（")[0])


def test_seeking_a_figure_and_a_material():
    game = _game()
    game.choose("act:tavern")
    figure = next(iter(game.content.figures.values()))
    name = game.content.characters[figure.character].name
    msgs = game.tavern_do("seek", name)
    assert msgs and name in msgs[0]
    one = next(m for m in game.content.materials.values() if m.tier == 1)
    msgs = game.tavern_do("material", one.id)
    assert msgs and one.name in msgs[0]
    three = next(m for m in game.content.materials.values() if m.tier == 3)
    msgs = game.tavern_do("material", three.id)
    assert "傳說" in msgs[0]


def test_wall_treat_hide_and_their_limits():
    game = _game()
    c = game.content
    game.choose("act:tavern")
    assert game.tavern_do("wall", text="") == [tavern.WALL_EMPTY]
    assert game.tavern_do("wall", text="字" * (c.config.tavern.wall_chars + 1))[0].startswith("一句最多")
    game.tavern_do("wall", text="南市一壺濁酒，換得潁川三夜風。")
    view = game.shop_view()
    assert view["walls"][0]["text"] == "南市一壺濁酒，換得潁川三夜風。" and view["walls"][0]["who"] == "沈浪"
    fame = game.state.player.stats.get("fame", 0)
    game.tavern_do("treat")
    assert game.state.player.stats.get("fame", 0) == fame + c.config.tavern.treat_fame
    assert game.shop_view()["treat"]
    assert game.tavern_do("treat") == [tavern.TREAT_FULL]
    game.tavern_do("hide")
    assert game.state.player.hidden_until > game.state.world.time
    assert game.tavern_do("hide")[0].startswith("已經打點過了")


def test_hiding_makes_you_harder_to_find():
    world = open_world()
    c = _content()
    me = _game(world=world, content=c)
    other = _game("李尋歡", at="wan_city", world=world, content=c)
    base = tavern.person_reach(me.state, c, other.state)
    other.state.player.hidden_until = other.state.world.time + 1000
    assert tavern.person_reach(me.state, c, other.state) == base - c.config.tavern.hide_reach


def test_trace_with_nothing_to_trace_is_free():
    game = _game()
    game.choose("act:tavern")
    before = game.state.player.stats["silver"]
    assert game.tavern_do("trace") == [tavern.TRACE_NONE]
    assert game.state.player.stats["silver"] == before


def test_cannot_act_outside_the_tavern():
    game = _game()
    before = game.state.player.stats["silver"]
    game.tavern_do("news")
    assert game.state.player.stats["silver"] == before


def test_a_bot_drops_in_asks_one_thing_and_leaves():
    from tianxia import bot_policy
    game = _game(silver=500)
    rng = random.Random(1)
    old = bot_policy.TAVERN_CHANCE
    bot_policy.TAVERN_CHANCE = 1.0
    try:
        msgs = bot_policy._tavern(game, rng)
    finally:
        bot_policy.TAVERN_CHANCE = old
    assert msgs
    assert not game.state.player.picking_tavern
    assert game.state.player.stats["silver"] < 500


def test_a_bot_short_of_silver_stays_out():
    from tianxia import bot_policy
    game = _game(silver=5)
    old = bot_policy.TAVERN_CHANCE
    bot_policy.TAVERN_CHANCE = 1.0
    try:
        assert bot_policy._tavern(game, random.Random(1)) is None
    finally:
        bot_policy.TAVERN_CHANCE = old
