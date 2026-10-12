"""修練頁最上面的人物面板（企劃者 2026-10-12 給的版面）：剪影身上的光點對上五屬性、身上的兩門與開著的裝備欄，
底下那一格寫點著的那一個；有點可配時屬性多一顆「＋」，走狀態列同一條配點的路。餵真的引擎資料給 app.js；沒有 node 就略過。"""
from __future__ import annotations

import random

import pytest
from test_prologue_web import run
from test_weapons_web import _gear, _row

import server
import webharness
from tianxia.engine import Game

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


@pytest.fixture
def views(hints_content, world):
    game = Game.new(hints_content, "沈浪", rng=random.Random(0), world=world)
    game.skip_tutorial()
    return server.main_view(game), server.menxia_view(game)


def _panel(page):
    return page.split('<section class="hero"')[1].split("</section>")[0]


def test_the_panel_draws_the_five_stats_and_the_worn_arts(views):
    m, x = views
    panel = _panel(run(m, "return H.pagePractice();", menxia=x))
    for name, value, key in m["status"]["attrs"]:
        assert f'data-key="{key}"' in panel and f"{name} {value}" in panel
    assert 'data-key="內功"' in panel and 'data-key="武學"' in panel
    assert "/static/hero.webp" in panel
    assert 'data-key="weapon"' not in panel  # 裝備欄都關著（測試內容）：不畫那幾個點


def test_the_default_foot_is_constitution_and_offers_a_point_only_when_there_is_one(views):
    m, x = views
    m["status"]["stat_points"] = 0
    foot = run(m, "return H.pagePractice();", menxia=x).split('id="hero-ft"')[1]
    assert "根骨" in foot.split("</div>")[0] and 'data-act="allocate"' not in foot.split("</section>")[0]
    m["status"]["stat_points"] = 2
    foot = run(m, "return H.pagePractice();", menxia=x).split('id="hero-ft"')[1].split("</section>")[0]
    assert 'data-act="allocate" data-stat="con"' in foot and "可配 2 點" in foot


def test_a_picked_node_stays_picked_and_gear_nodes_follow_the_open_slots(views):
    m, x = views
    x["gear"] = _gear(weapon={"worn": _row(name="<i>試刃</i>"), "rack": []}, armor={"worn": None, "rack": []})
    page = run(m, "return H.pagePractice();", menxia=x, S={"heroNode": "weapon"})
    panel = _panel(page)
    assert 'data-key="weapon"' in panel and 'data-key="armor"' in panel and 'data-key="mount"' not in panel
    assert 'hero-node dim r" style' in panel.split('data-key="armor"')[0].rsplit("<button", 1)[1]  # 沒穿防具：點暗著
    foot = page.split('id="hero-ft"')[1].split("</section>")[0]
    assert "&lt;i&gt;試刃&lt;/i&gt;" in foot and "<i>試刃</i>" not in foot  # 名字跳脫
    assert 'data-act="hero-jump" data-to="gear" data-kind="weapon"' in foot
    assert 'data-slot="weapon"' in page  # 「看這件」捲得到的那一段在
