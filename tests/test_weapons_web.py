"""兵器的網頁那一半（兵器設計 3.6）：修練頁的兵器塊——身上那把、裝備庫每把一行與「換上」鈕；字都跳脫；沒東西就不畫。
餵真的引擎給的 /api/main 與 /api/menxia 給 app.js（tests/test_prologue_web.py 的假瀏覽器）。沒有 node 就略過。"""
from __future__ import annotations

import random

import pytest
from test_prologue_web import run

import server
import webharness
from tianxia.engine import Game

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


def _row(**over):
    return {"id": "兵:1", "name": "試刃", "kind": "劍", "attribute": "柔", "tier": 1, "quality": "下品",
            "edge": 80, "fits": True, "bonus": "+4.5%", **over}


@pytest.fixture
def views(hints_content, world):
    game = Game.new(hints_content, "沈浪", rng=random.Random(0), world=world)
    game.skip_tutorial()
    return server.main_view(game), server.menxia_view(game)


def test_the_practice_page_draws_the_worn_weapon_and_the_rack(views):
    m, x = views
    x["weapons"] = {"worn": _row(), "cap": 6, "rack": [_row(id="兵:2", name="<b>厚背刀</b>", kind="刀", fits=False, bonus=None)]}
    page = run(m, "return H.pagePractice();", menxia=x)
    assert 'class="weapons"' in page and "【試刃】" in page and "鋒利度 80" in page and "威力 +4.5%" in page
    assert page.count('data-act="wield"') == 1 and 'data-id="兵:2"' in page  # 身上那把不用換上
    assert "裝備庫 1/6" in page and "用不上" in page
    assert "<b>厚背刀</b>" not in page and "&lt;b&gt;厚背刀&lt;/b&gt;" in page  # 名字跳脫


def test_the_wield_button_sends_the_weapon_id(views):
    m, x = views
    x["weapons"] = {"worn": None, "cap": 6, "rack": [_row(id="兵:2")]}
    page = run(m, "return H.pagePractice();", menxia=x)
    assert "手上沒有兵器" in page and 'data-act="wield"' in page


def test_nothing_is_drawn_without_weapons(views):
    m, x = views
    assert "class=\"weapons\"" not in run(m, "return H.pagePractice();", menxia=x)  # 測試內容把兵器關著
    x["weapons"] = {"worn": None, "rack": [], "cap": 6}
    assert 'class="weapons"' not in run(m, "return H.pagePractice();", menxia=x)
    del x["weapons"]  # 舊的伺服器沒有這一欄
    assert 'class="weapons"' not in run(m, "return H.pagePractice();", menxia=x)


def test_a_long_rack_lists_eight_and_then_a_more_button(views):
    m, x = views
    rack = [_row(id=f"兵:{i + 2}", name=f"備刃{i}") for i in range(12)]
    x["weapons"] = {"worn": _row(), "cap": 100, "rack": rack}
    page = run(m, "return H.pagePractice();", menxia=x)
    assert page.count('data-act="wield"') == 8 and "備刃7" in page and "備刃8" not in page
    assert 'data-act="rack-all"' in page and "再列 4 件" in page and "裝備庫 12/100" in page
    everything = run(m, "return H.pagePractice();", menxia=x, S={"rackAll": True})  # 按了「再列」之後全部攤開
    assert everything.count('data-act="wield"') == 12 and "rack-all" not in everything and "再列" not in everything
    x["weapons"]["rack"] = rack[:8]  # 剛好八把：不必多按一次
    short = run(m, "return H.pagePractice();", menxia=x)
    assert short.count('data-act="wield"') == 8 and "再列" not in short
