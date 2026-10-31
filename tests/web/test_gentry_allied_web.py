"""第一季豪強分屬兩軍的畫面（docs/superpowers/specs/2026-10-15-第一季豪強分屬兩軍-design.md 第十四節）：態勢只有官軍、黃巾兩方，
輿圖的「天下」那一列與「天下怎麼變」只算兩方。借 test_map_web 的 node 驅動。沒有 node 就略過。"""
from __future__ import annotations

import random

import pytest

import webharness
from conftest import real_content
from tianxia.engine import Game

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


def _allied_status():
    c = real_content("week7")
    c.config.auto_open_first_season = True
    game = Game.new(c, "甲", rng=random.Random(0))
    game.state.player.faction, game.state.player.ally = "haoqiang", "guan"
    return game.status_data()


STANCES_DRIVER = r"""
const parts = [...["esc", "STANCE_NAMES"].map(konst), ...["stancesHtml"].map(fn), "return { stancesHtml };"];
const H = new Function(parts.join("\n"))();
finish(H.stancesHtml(input.stances, input.notes));
"""


def test_stances_line_has_no_gentry_row():
    status = _allied_status()
    html = webharness.run(STANCES_DRIVER, {"stances": status["stances"], "notes": status["stance_notes"]})
    assert "豪強" not in html and "undefined" not in html and "<br>" not in html


def _timeline_game_allied():
    """7 天季（豪強分屬兩軍）：第 1 週記一筆，第 2 週把潁川汝南推到黃巾那頭再記一筆。"""
    from test_map_web import _game

    from tianxia import calendar, territory

    game = _game()
    w, c = game.state.world, game.content
    territory.update(w, c)
    w.time = calendar.week_start(2, c, w) + 60
    w.trends["yingru"] = 90
    territory.update(w, c)
    w.time = calendar.week_start(3, c, w) + 60
    territory.update(w, c)
    return game


def test_map_counts_two_sides():
    from test_map_web import run

    game = _timeline_game_allied()
    assert game.map_state()["sides"] == ["guan", "huang"]
    # 遠看那一段大區名底下那一行（各方幾處）照疊層的 sides
    for script in ("return H.timelineHtml(H.S.mapBase, H.S.mapState, H.S.mapState.now_week);",
                   "return H.marksHtml(H.S.mapBase, H.S.mapState, { z: 0.5, x: 0, y: 0 }, { vw: 2400, vh: 3600 });"):
        out = run(game, script)
        assert "豪強" not in out and ">豪 <" not in out and "豪 " not in out, script
