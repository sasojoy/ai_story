"""領地爭奪第一批：輿圖上的中立地（計畫三、Task 6 最後一段；甲乙兩版等企劃者挑，這裡守的是挑之前那個最小的中立色）。"""
from __future__ import annotations

import pytest
import test_map_web

import webharness
from conquest_kit import conquest_game, go, join, plain_game
from tianxia import atlas, conquest, mapview

pytestmark = pytest.mark.slow  # 建 Game、載正式內容


def _game():
    return go(join(conquest_game("season21"), "guan"), "yingchuan")


def test_map_state_marks_neutral_blocks():
    game = _game()
    places = game.map_state()["places"]
    assert places["nanyang_wilds"]["kind"] == "neutral" and places["nanyang_wilds"]["control"] is None
    assert places["yingshui"]["kind"] == "line" and places["changshe"]["kind"] == "base"
    assert places["guangzong"]["kind"] == "fixed"
    conquest.set_control(game.state.world, game.content, "nanyang_wilds", "huang")
    places = game.map_state()["places"]
    assert places["nanyang_wilds"]["kind"] == "neutral" and places["nanyang_wilds"]["control"] == "huang"


def test_detail_line_says_neutral():
    game = _game()
    s, c = game.state, game.content
    assert conquest.NEUTRAL_LINE in atlas.detail_text(s, c, "nanyang_wilds", game.odds)
    conquest.set_control(s.world, c, "nanyang_wilds", "huang")
    assert conquest.NEUTRAL_HELD in atlas.detail_text(s, c, "nanyang_wilds", game.odds)


def test_old_svg_paints_the_neutral_disc_and_legend():
    game = _game()
    svg = mapview.render_map(game.state, game.content, "situation")
    assert mapview.CONTROL_DISC["neutral"] in svg
    assert mapview.LEGEND_NEUTRAL in mapview.legend_data(game.state, game.content, "situation")["layer"]


def test_switch_off_map_unchanged():
    game = go(join(plain_game("weekend"), "guan"), "yingchuan")
    places = game.map_state()["places"]
    assert all(p["kind"] != "neutral" for p in places.values())
    assert mapview.LEGEND_NEUTRAL not in mapview.legend_data(game.state, game.content, "situation")["layer"]


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_web_marks_paint_unheld_neutral_grey():
    game = _game()
    out = test_map_web.marks(game)
    assert '#ECE9E2' in out  # 還沒人佔的中立地：灰白圓盤
    drawer = test_map_web.run(game, 'return H.placeHtml(H.S.mapBase, H.S.mapState, "nanyang_wilds");')
    assert "中立地" in drawer and "還沒有人佔" in drawer
