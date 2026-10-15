"""第一季豪強分屬兩軍的畫面（docs/superpowers/specs/2026-10-15-第一季豪強分屬兩軍-design.md 第十四節）：態勢只有官軍、黃巾兩方，
輿圖的「天下」那一列與「天下怎麼變」只算兩方。借 test_peek_row、test_map_web 的 node 驅動。沒有 node 就略過。"""
from __future__ import annotations

import random

import pytest

import webharness
from conftest import real_content
from tianxia.engine import Game

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


def _allied_status():
    c = real_content("weekend")
    c.config.auto_open_first_season = True
    game = Game.new(c, "甲", rng=random.Random(0))
    game.state.player.faction, game.state.player.ally = "haoqiang", "guan"
    return game.status_data()


def test_stance_chip_shows_two_sides():
    from test_peek_row import chips, run, view

    status = _allied_status()
    chip = next(x for x in chips(run(view(status))) if x["id"] == "stance")
    assert "豪強" not in chip["label"] and "undefined" not in chip["html"]
    assert chip["label"].startswith("兩軍態勢：")  # 不寫「三方」
    assert chip["text"].count("·") == 1


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
    """同 test_map_web._timeline_game，只是週末設定照預設（豪強分屬兩軍開著）：第 1 週記一筆，第 2 週把潁川汝南推到黃巾那頭再記一筆。"""
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
    for script in ("return H.timelineHtml(H.S.mapBase, H.S.mapState, H.S.mapState.now_week);",
                   "return H.hudHtml(H.S.mapBase, H.S.mapState, H.S.mapState.now_week);"):
        out = run(game, script)
        assert "豪強" not in out and ">豪 <" not in out, script
