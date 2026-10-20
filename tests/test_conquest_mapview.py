"""領地爭奪第一批：輿圖上的中立地（計畫三、Task 6 最後一段；甲乙兩版等企劃者挑，這裡守的是挑之前那個最小的中立色）。
輿圖重製第 1 批（新天下）：中立地換成中原的荒丘、陣營區塊換成南陽的淯水河畔、大本營換成宛城（v1 是南陽郊野、潁水河畔、長社）。"""
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
    assert places["hilltop_wilds"]["kind"] == "neutral" and places["hilltop_wilds"]["control"] is None
    assert places["yu_river"]["kind"] == "line" and places["wan_city"]["kind"] == "base"
    assert places["guangzong"]["kind"] == "fixed"
    conquest.set_control(game.state.world, game.content, "hilltop_wilds", "huang")
    places = game.map_state()["places"]
    assert places["hilltop_wilds"]["kind"] == "neutral" and places["hilltop_wilds"]["control"] == "huang"


def test_detail_line_says_neutral():
    game = _game()
    s, c = game.state, game.content
    assert conquest.NEUTRAL_LINE in atlas.detail_text(s, c, "hilltop_wilds", game.odds)
    conquest.set_control(s.world, c, "hilltop_wilds", "huang")
    assert conquest.NEUTRAL_HELD in atlas.detail_text(s, c, "hilltop_wilds", game.odds)


def test_old_svg_paints_the_neutral_disc_and_legend():
    game = _game()
    svg = mapview.render_map(game.state, game.content, "situation")
    assert mapview.CONTROL_DISC["neutral"] in svg
    assert mapview.LEGEND_NEUTRAL in mapview.legend_data(game.state, game.content, "situation")["layer"]


def test_crossed_swords_on_every_block_you_can_attack():
    game = _game()
    armed = mapview.armed_places(game.state, game.content)
    assert {"deep_mountain", "hilltop_wilds", "runan_wilds", "zhuo_county"} <= armed  # 中立地、黃巾的陣營區塊（城鎮照控制方的巡邏）
    assert not armed & {"wan_city", "luoyang_road", "haozu_fort"}  # 自家的、不是區塊的（新天下的長社、潁川郡是中立地）


def test_switch_off_map_unchanged():
    game = go(join(plain_game("weekend"), "guan"), "yingchuan")
    places = game.map_state()["places"]
    assert all(p["kind"] != "neutral" for p in places.values())
    assert mapview.LEGEND_NEUTRAL not in mapview.legend_data(game.state, game.content, "situation")["layer"]


def test_ropes_hang_no_beads_without_tug_of_war():
    """領地爭奪沒有拔河：輿圖總覽的三條戰線照舊寫值，繩上不掛照門檻擺的地點；關著照舊掛。"""
    ropes = _game().map_state()["ropes"]
    assert len(ropes) == 3 and all(r["beads"] == [] for r in ropes)
    plain = go(join(plain_game("weekend"), "guan"), "yingchuan")
    assert any(r["beads"] for r in plain.map_state()["ropes"])


def _place_svg(out: str, loc_id: str) -> str:
    """marksSvg 裡那一處的 <g data-loc> 一段（點擊區、外圈、圓盤、字）。"""
    start = out.index(f'<g data-loc="{loc_id}"')
    return out[start:out.index("</g>", start)]


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_web_marks_draw_unheld_neutral_as_grey_disc_with_dashed_ring():
    game = _game()
    out = test_map_web.marks(game)
    wilds = _place_svg(out, "hilltop_wilds")
    assert "#ECE9E2" in wilds and "stroke-dasharray" in wilds  # 甲：灰白圓盤＋虛線圈（還沒人佔）
    assert "stroke-dasharray" not in _place_svg(out, "yu_river")  # 陣營的區塊照舊實線
    far = _place_svg(test_map_web.marks(game, k=2.5, far="true"), "hilltop_wilds")
    assert "#CFCBC2" in far and "stroke-dasharray" in far  # 看大局：小點也是灰、虛線邊
    drawer = test_map_web.run(game, 'return H.placeHtml(H.S.mapBase, H.S.mapState, "hilltop_wilds");')
    assert "中立地" in drawer and "還沒有人佔" in drawer
    conquest.set_control(game.state.world, game.content, "hilltop_wilds", "huang")
    held = _place_svg(test_map_web.marks(game), "hilltop_wilds")
    assert "stroke-dasharray" not in held and "#ECE9E2" not in held  # 被佔下了：照佔領方的顏色，不再是虛線
