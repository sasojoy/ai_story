"""FB-646（QA 驗玉璽碎片改版第 3 批）：同一天被補缺退回的地，〈天下形勢〉「是日」照樣寫「黃巾軍拿下涿郡」，事實的因果也排倒
（天下大事新的在前：先「官軍收復涿郡」、後「有人起用了『金角』」）。原因：補缺照開發定的不記 day_log，summary_line 只看 day_log。

PM 定：補缺記一筆 day_log（by="mend"，不記是誰——持有者要藏），〈天下形勢〉照時間順序寫：同一篇裡先被翻走、又被補回的，「是日」寫
「某軍拿下某地，旋即被補回」，事實接在那一筆易手後面寫「某地旋即又退回某軍手中」；翻走是上一篇以前的事，「是日」寫「某軍補回某地」。
territory 另發的「收復」那一句跟這一筆是同一件事，不再當天下大事列一次。新句型在 content/xingshi_lines.json（待 joy 潤）。"""
from __future__ import annotations

import random
import tempfile
from pathlib import Path

import pytest

from conftest import real_content
from conquest_kit import conquest_game, conquest_rules
from tianxia import conquest, conquest_day, seal, territory, xingshi
from tianxia.characters import CharacterStore
from tianxia.engine import Game
from tianxia.sqlite_world import open_world
from tianxia.state import DayNote

pytestmark = pytest.mark.slow  # 建 Game、載正式內容


def _person(c, w, name, side, at):
    g = Game.new(c, name, rng=random.Random(0), world=w)
    g.client = None
    p = g.state.player
    p.faction, p.location, p.tutorial_step = side, at, len(c.tutorial.steps)
    p.visited.add(at)
    g.sync(0.0)
    g._save_season()
    CharacterStore(w.db).save(g.state)


def _do(c, w, name, fn, now):
    game = Game(c, CharacterStore(w.db).load(name), random.Random(0), w)
    game.client = None
    game.sync(now)
    out = fn(game)
    game._save_season()
    CharacterStore(w.db).save(game.state)
    return out


def _mended_world(user: str = "甲客"):
    """QA 的 x_xingshi：21 天季＋領地爭奪＋〈天下形勢〉；黃巾推滿官軍的涿郡（當場易手），官軍的 user 起用金角補回來。
    甲客、乙客都是官軍、站涿郡；回（內容, 世界, 開出來的那一張單）。"""
    c = conquest_rules(real_content("season21"), xingshi=True)
    c.config.auto_open_first_season = True
    c.config.seal.revamp.enabled = True
    c.config.newbie_days, c.config.newbie_real_hours = -1, 0
    w = open_world(Path(tempfile.mkdtemp(prefix="xs646-")) / "t.db")

    def _give(st):
        s = seal.filled(st.seal, c).shards["jinjiao"]
        s.state, s.holder, s.since_season = "held", user, 0

    w.mutate(_give)
    for name in ("甲客", "乙客"):
        _person(c, w, name, "guan", "zhuo_county")
    _do(c, w, "乙客", lambda g: conquest.push(g.state.world, c, "zhuo_county", "huang", "巾甲", 100, "attack"), now=100.0)
    _do(c, w, user, lambda g: g.seal_use("zhuo_county"), now=200.0)

    def _open(g):
        g._xingshi_open(1)
        return g.state.world.xingshi_ticket

    ticket = _do(c, w, "乙客", _open, now=300.0)
    return c, w, ticket


def test_a_mend_is_logged_without_a_name():
    c, w, ticket = _mended_world()
    flip, mend = w.get_season().conquest.day_log[-2:]
    assert (flip.by, flip.side, flip.loc) == (conquest_day.FLIP, "huang", "zhuo_county")
    assert (mend.by, mend.side, mend.loc, mend.reason) == (conquest_day.MEND, "guan", "zhuo_county", "")


def test_the_day_says_taken_then_mended_in_order():
    """「是日」照時間順序：黃巾軍拿下涿郡，旋即被補回（修前「是日：黃巾軍拿下涿郡。」）；事實裡補回那一條接在易手後面，「收復」不再列一次。"""
    c, w, ticket = _mended_world()
    guan, huang = c.scenario.faction_name("guan", "guan"), c.scenario.faction_name("huang", "huang")
    summary = xingshi.lines(c)["summary"]
    assert ticket.line == f"{xingshi.SUMMARY_HEAD}{summary['taken_mended'].format(side=huang, place='涿郡')}。"
    facts = ticket.facts
    fact = xingshi.lines(c)["fact"]
    took = fact["flip"].format(who="巾甲", side=huang, place="涿郡")
    back = fact["mended"].format(side=guan, place="涿郡")
    assert facts.index(took) + 1 == facts.index(back)
    assert territory.RETAKE_LINE.format(place="涿郡", side=guan) not in facts
    assert not any("甲客" in f for f in facts) and "甲客" not in ticket.line  # 不點名起用的人


def test_who_used_it_does_not_show_in_the_xingshi():
    a, b = _mended_world("甲客")[2], _mended_world("乙客")[2]
    assert (a.facts, a.line) == (b.facts, b.line)


def _game():
    game = conquest_game("season21", xingshi=True)
    return game.state.world, game.content


def test_a_mend_after_a_siege_win_reads_the_same():
    w, c = _game()
    notes = [
        DayNote(key=1, side="huang", loc="zhuo_county", minute=12 * 60, by=conquest_day.LETTER, reason="巾帥", result="taken",
                taken="huang", margin="大勝", keeper="guan", attackers=["huang"]),
        DayNote(key=1, side="guan", loc="zhuo_county", minute=13 * 60, by=conquest_day.MEND),
    ]
    huang = c.scenario.faction_name("huang", "huang")
    assert xingshi.summary_line(notes, c) == f"{xingshi.SUMMARY_HEAD}{xingshi.lines(c)['summary']['taken_mended'].format(side=huang, place='涿郡')}。"


def test_a_mend_whose_flip_was_in_an_earlier_piece_says_mended():
    """翻走是上一篇以前的事（這一篇只有補回那一筆）：「是日」寫「官軍補回涿郡」、事實寫「涿郡退回官軍手中」（沒有「旋即」）。"""
    w, c = _game()
    guan = c.scenario.faction_name("guan", "guan")
    notes = [DayNote(key=1, side="guan", loc="zhuo_county", minute=1 * 60, by=conquest_day.MEND)]
    words = xingshi.lines(c)
    assert xingshi.summary_line(notes, c) == f"{xingshi.SUMMARY_HEAD}{words['summary']['mended'].format(side=guan, place='涿郡')}。"
    facts = xingshi.facts(w, c, notes, {})
    late = words["fact"]["mended_late"].format(side=guan, place="涿郡")
    trends = [t.name for t in c.scenario.trends]
    first_line = next(i for i, f in enumerate(facts) if any(f.startswith(f"{name}一帶") for name in trends))
    assert facts.index(late) < first_line  # 已經發生的事，排在三條線前面（不是「下一仗」）
    assert words["fact"]["mended"].format(side=guan, place="涿郡") not in facts


def test_flips_without_a_mend_are_unchanged():
    w, c = _game()
    notes = [DayNote(key=1, side="huang", loc="zhuo_county", minute=10 * 60, by=conquest_day.FLIP, reason="巾甲"),
             DayNote(key=1, side="guan", loc="runan", minute=11 * 60, by=conquest_day.FLIP)]
    words = xingshi.lines(c)["summary"]
    guan, huang = c.scenario.faction_name("guan", "guan"), c.scenario.faction_name("huang", "huang")
    assert xingshi.summary_line(notes, c) == (f"{xingshi.SUMMARY_HEAD}{words['taken'].format(side=huang, place='涿郡')}；"
                                              f"{words['taken'].format(side=guan, place='汝南')}。")
