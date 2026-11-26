"""帶著做一次（Joy 2026-11-26「照建議」；設計稿 https://claude.ai/artifact/JGmeBcjLtjU1HWPYjhfwkD）：小事卡按下去之後一步一步帶，
存檔看得出來的步由引擎判、看不出來的由網頁回報，end 按「好」收；改天隔一陣子再出一次、第二次不出。"""
from __future__ import annotations

import random

import pytest
from conftest import real_content

from tianxia.engine import Game
from tianxia.features.unfold import cards


@pytest.fixture
def on():
    c = real_content()
    c.config.auto_open_first_season = True
    c.config.jianfa.enabled = True
    c.config.unfold.enabled = True
    c.config.zongmen.enabled = c.config.mail.enabled = c.config.jieyi.enabled = True
    return c


def _game(content, name="沈浪"):
    g = Game.new(content, name, rng=random.Random(0), prologue=True)
    g.sync(g.now + 1)
    g.choose("choice:0")
    return g


def _at_sect(g, content):
    sect = next(s for s in content.sects.values() if s.switch == "zongmen" and content.sect_open(s.id) and cards._first_art(g, s.id))
    g.state.player.location = sect.location
    g.state.player.stats["silver"] = 10_000
    g.sync(g.now + 1)
    return sect


def _lead(g):
    return g.feature_status()["unfold"]["lead"]


def test_the_sect_walk_goes_join_learn_then_ends_on_ok(on):
    g = _game(on)
    sect = _at_sect(g, on)
    book = g.state.player.unfold
    assert book.card.startswith("sect|")
    cards.start(g, book)
    lead = _lead(g)
    assert (lead["kind"], lead["step"]) == ("sect", "join") and lead["learn"].startswith("learn:") and lead["say"]
    g.choose(f"zongmen:join:{sect.id}")
    assert _lead(g)["step"] == "learn"
    g.choose(_lead(g)["learn"])
    lead = _lead(g)
    assert lead["step"] == "end" and lead["end"]
    cards.report(g, book, "sect", "end")
    assert _lead(g) is None and book.lead == ""
    g.sync(g.now + 1)
    assert book.card == "" or not book.card.startswith("sect|")  # 帶過了不再出


def test_mail_walk_waits_for_the_sent_report_and_ignores_other_steps(on):
    from tianxia.state import Mingtie, MingtieCopy

    g = _game(on)
    g.state.player.mingtie_box.append(MingtieCopy(name="王越", card=Mingtie(), when="", place="", season=1, gave=1))
    g.sync(g.now + 1)
    book = g.state.player.unfold
    assert book.card.startswith("mail|")
    cards.start(g, book)
    g.sync(g.now + 1)
    assert _lead(g)["step"] == "write"  # 存檔看不出來：不自己往下走
    cards.report(g, book, "codex", "write")
    cards.report(g, book, "mail", "end")
    assert _lead(g)["step"] == "write"  # 不是這一件、不是這一步：不認
    cards.report(g, book, "mail", "write")
    assert _lead(g)["step"] == "end"
    cards.stop(book)
    assert _lead(g) is None


def test_later_comes_back_once_after_the_gap_then_never(on):
    g = _game(on)
    _at_sect(g, on)
    book = g.state.player.unfold
    assert book.card.startswith("sect|")
    cards.close(g, book)
    g.sync(g.now + 60)
    assert book.card == ""  # 還沒隔夠
    g.sync(g.now + on.config.unfold.later_hours * 3600 + 1)
    assert book.card.startswith("sect|")  # 再碰到同一個時機：再出一次
    cards.close(g, book)
    g.sync(g.now + on.config.unfold.later_hours * 3600 * 3)
    assert book.card == ""  # 第二次改天就不再出


def test_old_book_gets_no_gift_and_title_walk_ends_at_once(on):
    g = _game(on)
    g.state.player.unfold = None
    g.sync(g.now + 1)
    book = g.state.player.unfold
    assert book.old
    book.card = "title|t1|名號"
    g.state.player.titles_worn = {"id": "t1", "name": "潁川遊俠", "grade": 3}
    cards.start(g, book)
    lead = _lead(g)
    assert lead["kind"] == "title" and lead["end"] and lead["seal"] == "潁川遊俠"
