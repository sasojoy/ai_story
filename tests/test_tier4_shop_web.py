"""第 2 批畫面（設計 9.1，企劃者挑甲）：素材四階開著時鐵匠鋪打造頁的素材格一排多一欄四階、素材頁升階一屬性多一格三換四，
樣子跟一到三階一樣；鐵匠講神器規矩那一句畫在平常那一句的位置、金框。四階關著照舊三欄兩格，一個字都不變。"""
from __future__ import annotations

import pytest
from test_four_tiers import _smith_game
from test_shop_web import run

import server
import webharness
from tianxia import shopview

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


def _smithy(bag, on=True):
    game = _smith_game(bag)
    game.content.config.four_tiers.enabled = on
    game.choose("act:smith")
    return game


def test_the_forge_grid_gets_a_fourth_column_for_tier_four():
    game = _smithy({"gang_1": 2, "gang_2": 1, "gang_3": 1, "gang_4": 1})
    assert shopview.smith_view(game.state, game.content, game.world)["four"] is True
    html = run(server.main_view(game), "H.render(); return T.els.app.innerHTML;", S={"shopTab": "forge"})
    assert 'class="cells four"' in html and 'class="cell t4' in html


def test_the_upgrade_rows_get_a_third_cell_for_three_to_four():
    game = _smithy({"gang_3": 5})
    html = run(server.main_view(game), "H.render(); return T.els.app.innerHTML;", S={"shopTab": "trade"})
    assert 'class="up-rows four"' in html and 'data-tier="4"' in html


def test_the_three_for_four_line_breaks_only_between_its_pieces():
    """FB-410：375 寬三換四那一格（一格約 103px）「150 兩・這一季還能 2 個」斷成「這一季還／能 2 個」：價錢與「這一季還能 N 個」
    各包成不折行的小段（同 FB-132、FB-297 的 .nb），要斷只斷在「・」後面。"""
    game = _smithy({"gang_3": 5})
    html = run(server.main_view(game), "H.render(); return T.els.app.innerHTML;", S={"shopTab": "trade"})
    cell = html[html.index('data-tier="4"'):]
    cell = cell[:cell.index("</button>")]
    assert '<span class="nb">150 兩</span>' in cell and '・<span class="nb">這一季還能 2 個</span>' in cell


def test_tier_four_off_keeps_three_columns():
    game = _smithy({"gang_1": 2, "gang_3": 1}, on=False)
    assert shopview.smith_view(game.state, game.content, game.world)["four"] is False
    html = run(server.main_view(game), "H.render(); return T.els.app.innerHTML;", S={"shopTab": "forge"})
    assert 'class="cells"' in html and "cells four" not in html


def test_the_rule_takes_the_smiths_usual_line_in_a_gold_frame():
    game = _smithy({"gang_4": 1})
    rule = shopview.smith_view(game.state, game.content, game.world)["rule"]
    assert rule
    html = run(server.main_view(game), "H.render(); return T.els.app.innerHTML;")
    assert f'<p class="shop-line rule">{rule}</p>' in html
    game.state.player.shop_clue = "鐵匠順口說了一句"  # 順口講配方線索那一下照舊蓋過規矩
    html = run(server.main_view(game), "H.render(); return T.els.app.innerHTML;")
    assert "shop-line rule" not in html and "鐵匠順口說了一句" in html


def test_the_new_rules_sit_in_the_shop_section():
    from pathlib import Path

    css = (Path(__file__).resolve().parent.parent / "web" / "style.css").read_text(encoding="utf-8")
    assert ".shop-layer .cells.four .cell-row { grid-template-columns: 1.6em repeat(4, minmax(0, 1fr)); }" in css
    assert ".shop-layer .cells.four .cell-row .t4 { grid-column: 5; }" in css
    assert ".shop-layer .up-rows.four .up-row { grid-template-columns: 1.6em repeat(3, minmax(0, 1fr)); }" in css
