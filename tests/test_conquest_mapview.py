"""領地爭奪第一批：輿圖上的中立地（計畫三、Task 6 最後一段）。網頁那一條在輿圖第三版第 4 批改寫：中立地的虛線圈拿掉了（輿圖簡化設計 5.4），
區圖上是灰的印章框加朱印「寶」。舊的 SVG（render_map）那幾條照舊。"""
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


def test_crossed_swords_on_every_block_you_can_attack():
    game = _game()
    armed = mapview.armed_places(game.state, game.content)
    assert {"yu_river", "hilltop_wilds", "runan", "xinye"} <= armed  # 中立地、黃巾的陣營區塊（城鎮照控制方的巡邏；區塊表 v3）
    assert not armed & {"yingchuan", "changshe", "zhuo_county", "haozu_fort"}  # 自家的、不是區塊的


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


def _frame(out: str, loc_id: str) -> str:
    """區圖裡那一處的印章框那一個 <rect class="r-frame">。"""
    start = out.index(f'<g class="r-label" data-act="region-place" data-id="{loc_id}"')
    start = out.index('<rect class="r-frame"', start)
    return out[start:out.index("/>", start)]


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_web_region_map_draws_unheld_neutral_with_a_grey_frame_and_the_seal():
    """輿圖第三版第 4 批（輿圖簡化設計 5.4）：中立地的虛線圈／細金邊拿掉了——還沒人佔的中立地是灰的印章框（沒人佔一色，照底圖的 unheld 調）
    加朱印「寶」；被佔下照佔領方的顏色、寶照樣在（開季中立的，不管此刻誰佔著）。卡上那一句寫「中立・高級資源領地，還沒有人佔」。"""
    import test_region_map_web

    game = _game()
    ink = {s["id"]: s for s in game.map_base()["world"]["sides"]}
    low, _ = test_region_map_web.parts(game, "nanyang")
    wilds = _frame(low, "nanyang_wilds")
    assert "stroke-dasharray" not in low.split('class="r-label"', 1)[1]  # 名字框、小圖都不畫虛線
    assert all(f'fill="{s["tint"]}"' not in wilds for s in ink.values())  # 沒人佔：灰框，不是任何一方的顏色
    assert 'class="r-seal"' in test_region_map_web._label(low, "nanyang_wilds")
    card = test_map_web.run(game, 'return H.placeCard(H.S.mapBase, H.S.mapState, "nanyang_wilds");')
    assert "中立・高級資源領地，還沒有人佔" in card
    conquest.set_control(game.state.world, game.content, "nanyang_wilds", "huang")
    held, _ = test_region_map_web.parts(game, "nanyang")
    assert f'fill="{ink["huang"]["tint"]}"' in _frame(held, "nanyang_wilds") and f'stroke="{ink["huang"]["color"]}"' in _frame(held, "nanyang_wilds")
