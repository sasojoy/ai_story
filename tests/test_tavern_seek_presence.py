"""酒肆查人：「此刻就在…」只在那個人真的還在場時才寫。

Joy 2026-10-19：「我在酒館打聽到冰狼西獅在嵩山腳，過去怎麼沒看到人」。查了實機：那個人確實還在嵩山腳
（存檔的所在沒變），但他已經離線 6.8 小時，而場景的「此地還有」只列 presence_seconds（600 秒）內同步過的人。
查人原本只擋 offline_hours（24 小時），所以離開十分鐘到一天的人會被寫成「此刻就在嵩山腳，正在那裡走動」
——情報沒錯，錯在「此刻」。付了錢、走過去，那裡沒有人。
"""
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


def _game(name="沈浪", at="wan_city", silver=500, world=None, content=None):
    c = content or _content()
    game = Game.new(c, name, rng=random.Random(0), world=world or open_world())
    game.client = None
    p = game.state.player
    p.location = at
    p.tutorial_step = len(c.tutorial.steps)
    p.stats["silver"] = silver
    game.now = NOW
    p.seen_real = NOW
    CharacterStore(game.world.db).save(game.state)
    return game


def _famous_target(world, c, *, idle_seconds: float, at="wan_city"):
    """一個名望頂段（打聽度最高檔）、留在某地、最後上線在 idle_seconds 之前的人。"""
    other = _game("李尋歡", at=at, world=world, content=c)
    other.state.player.stats["fame"] = 10_000
    other.state.player.seen_real = NOW - idle_seconds
    CharacterStore(world.db).save(other.state)
    return other


def _ask(me, name="李尋歡"):
    me.choose("act:tavern")
    return me.tavern_do("seek", name)


def test_someone_who_is_really_there_still_gets_the_live_answer():
    world, c = open_world(), _content()
    me = _game(world=world, content=c)
    _famous_target(world, c, idle_seconds=60)  # 一分鐘前還在：在場
    msgs = _ask(me)
    assert any("此刻就在" in m and "宛城" in m for m in msgs), msgs


def test_someone_offline_for_hours_is_not_described_as_being_there_now():
    """Joy 碰到的那一種：人沒走，但已經離線好幾個鐘頭。"""
    world, c = open_world(), _content()
    me = _game(world=world, content=c)
    _famous_target(world, c, idle_seconds=6.8 * 3600)  # 實機那一次的 6.8 小時
    msgs = _ask(me)
    assert not any("此刻就在" in m for m in msgs), msgs
    assert not any("正在那裡走動" in m for m in msgs), msgs
    assert any("一兩個時辰前" in m and "宛城" in m for m in msgs), msgs  # 地點照給，只是寫成過去式


def test_the_place_is_still_right_so_the_information_keeps_its_value():
    """退回過去式之後，地點還是那個地點——付的錢沒有白花。"""
    world, c = open_world(), _content()
    me = _game(world=world, content=c)
    _famous_target(world, c, idle_seconds=3 * 3600, at="yingchuan")
    assert any("潁川" in m for m in _ask(me)), "地點不見了"


def test_a_day_offline_still_reads_as_nobody_has_seen_him():
    """離線超過 offline_hours（24 小時）那一段的話一個字都沒變。"""
    world, c = open_world(), _content()
    me = _game(world=world, content=c)
    _famous_target(world, c, idle_seconds=25 * 3600)
    msgs = _ask(me)
    assert any("近來沒人見過" in m for m in msgs), msgs


def test_the_threshold_is_the_same_one_the_scene_uses():
    """門檻就是「此地還有」那一個（presence_seconds），不要另外養一個數字。"""
    c = _content()
    world = open_world()
    me = _game(world=world, content=c)
    _famous_target(world, c, idle_seconds=c.config.presence_seconds - 5)
    assert any("此刻就在" in m for m in _ask(me))

    world2 = open_world()
    me2 = _game(world=world2, content=c)
    _famous_target(world2, c, idle_seconds=c.config.presence_seconds + 5)
    assert not any("此刻就在" in m for m in _ask(me2))


def test_the_wording_constants_are_the_ones_we_think():
    assert "此刻就在" in tavern.SEEN_NOW and "一兩個時辰前" in tavern.SEEN_PLACE
