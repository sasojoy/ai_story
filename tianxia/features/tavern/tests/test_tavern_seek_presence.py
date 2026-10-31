"""酒肆查人：「此刻就在…」只在那個人真的還在「此地還有」的名單上時才寫。

Joy 2026-10-19：「我在酒館打聽到冰狼西獅在嵩山腳，過去怎麼沒看到人」。當時 presence_seconds 是 600 秒，
而查人只擋 offline_hours（24 小時），所以離開十分鐘到一天的人會被寫成「此刻就在嵩山腳，正在那裡走動」
——情報沒錯（人確實在那裡），錯在「此刻」：玩家付了錢走過去，名單上沒有他。

之後 Joy 把窗口拉到 24 小時（「就是要可以殺得到啊 延長到24小時怕被殺去城鎮」），所以同一個 6.8 小時的人
現在真的看得到、也截殺得到，說「此刻就在」是對的。**這一份守的是不變量，不是具體的小時數**：
酒家說得出「此刻」的範圍不能比「此地還有」還寬——兩邊同一個 presence_seconds，哪一天數字再變也不會又騙人。
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
    c = real_content("week7")
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


def test_someone_still_in_the_list_may_be_described_as_being_there_now():
    """Joy 碰到的那一種（離線 6.8 小時）：窗口拉到 24 小時之後，他真的看得到、也截殺得到，所以「此刻」是對的。"""
    world, c = open_world(), _content()
    assert c.config.presence_seconds > 6.8 * 3600, "窗口縮回去了，這個測試要重想"
    me = _game(world=world, content=c)
    _famous_target(world, c, idle_seconds=6.8 * 3600)
    assert any("此刻就在" in m and "宛城" in m for m in _ask(me)), "名單上有他，酒家卻不敢說"


def test_outside_the_window_it_never_claims_he_is_there_now(monkeypatch):
    """不變量：超出「此地還有」的範圍就不准說「此刻」——不管那個窗口被調成多少。
    這裡把窗口縮回 10 分鐘（就是 Joy 當初踩到的設定），同一個 6.8 小時的人必須退回過去式。"""
    world, c = open_world(), _content()
    monkeypatch.setattr(c.config, "presence_seconds", 600.0)
    me = _game(world=world, content=c)
    _famous_target(world, c, idle_seconds=6.8 * 3600)
    msgs = _ask(me)
    assert not any("此刻就在" in m for m in msgs), msgs
    assert not any("正在那裡走動" in m for m in msgs), msgs
    assert any("一兩個時辰前" in m and "宛城" in m for m in msgs), msgs  # 地點照給，只是寫成過去式


def test_the_place_is_still_right_so_the_information_keeps_its_value(monkeypatch):
    """退回過去式之後，地點還是那個地點——付的錢沒有白花。"""
    world, c = open_world(), _content()
    monkeypatch.setattr(c.config, "presence_seconds", 600.0)
    me = _game(world=world, content=c)
    _famous_target(world, c, idle_seconds=3 * 3600, at="yingchuan")
    assert any("潁川" in m for m in _ask(me)), "地點不見了"


def test_a_day_offline_still_reads_as_nobody_has_seen_him():
    """離線超過 offline_hours（24 小時）那一段的話一個字都沒變（也就是出了窗口的人）。"""
    world, c = open_world(), _content()
    me = _game(world=world, content=c)
    _famous_target(world, c, idle_seconds=25 * 3600)
    msgs = _ask(me)
    assert any("近來沒人見過" in m for m in msgs), msgs


def test_the_threshold_is_the_same_one_the_scene_uses(monkeypatch):
    """門檻就是「此地還有」那一個（presence_seconds），不要另外養一個數字：剛好在界內說得出「此刻」，界外說不出。"""
    c = _content()
    monkeypatch.setattr(c.config, "presence_seconds", 1800.0)
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
