"""酒肆的網頁版面要穩（Joy 2026-10-19「酒肆操作沒兩下很容易就跑版了」「視窗大小跳來跳去」）：
四頁的框一樣高（燈籠那一幅畫在捲的那一層裡）、酒家那一句固定兩行高、做了一件事之後店裡捲到哪裡留在哪裡、
聽消息那一頁的鈕在聽到的消息上面。假瀏覽器照 test_prologue_web 的那一套跑整支 app.js。"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from test_prologue_web import DRIVER as PROLOGUE_DRIVER
from test_tavern import _game

import server
import webharness

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
NAMES_START = 'wholeApp(["S", '
assert PROLOGUE_DRIVER.count(NAMES_START) == 1
DRIVER = PROLOGUE_DRIVER.replace(NAMES_START, 'wholeApp(["S", "shopHtml", "renderShop", "shopPolled", "tavDo", ')
ROOT = Path(__file__).resolve().parents[4]  # tianxia/features/tavern/tests/ 往上四層（主動搬六包第 10 批從 tests/web/ 搬進包）


def run(m, script, S=None, responses=None):
    return webharness.run(DRIVER, {"m": m, "script": script, "S": S or {}, "menxia": None, "stored": {}, "responses": responses or {}})


@pytest.fixture
def m():
    game = _game()
    game.choose("act:tavern")
    game._tavern_run("news")
    return server.main_view(game)


def test_every_tab_starts_the_scrolling_part_at_the_same_place(m):
    """燈籠那一幅只在聽消息那一頁：畫在 .shop-body 裡，不然換頁時底下的框上下跳一百多像素。"""
    pages = run(m, """
      const out = {};
      for (const tab of ["news", "ask", "wall", "shade"]) { H.S.tavTab = tab; H.render(); out[tab] = T.els.app.innerHTML; }
      return out;""")
    assert "tav-hero" in pages["news"]
    for tab, html in pages.items():
        layer = html[html.index('class="shop-layer shop-tavern"'):]
        before_body = layer[: layer.index('class="shop-body"')]
        assert "tav-hero" not in before_body, tab  # 框上面只有招牌與酒家那一句


def test_the_buttons_on_the_news_page_sit_above_what_was_heard(m):
    html = run(m, 'H.S.tavTab = "news"; H.render(); return T.els.app.innerHTML;')
    assert "tav-note" in html
    assert html.index('data-op="treat"') < html.index("tav-note")  # 聽一則多一則，不把請酒那一顆往下推


def test_an_action_keeps_the_tavern_scrolled_where_it_was(m):
    out = run(m, """
      return (async () => {
        H.S.tavTab = "ask"; H.render();
        const fresh = { scrollTop: 0 };
        T.qs[".shop-layer"] = { className: "shop-layer shop-tavern", querySelector: (s) => (s === ".shop-body" ? { scrollTop: 260 } : null), querySelectorAll: () => [] };
        T.qs[".shop-layer .shop-body"] = fresh;
        await H.tavDo("material", { target: "x" });
        const kept = fresh.scrollTop;
        return { kept, called: T.calls.map((c) => c[0]) };
      })();""", responses={"/api/do/tavern": {"main": m, "message": "<p>酒家說了。</p>"}})
    assert "/api/do/tavern" in out["called"] and out["kept"] == 260


def test_the_keepers_line_has_a_fixed_height():
    css = (ROOT / "web" / "style.css").read_text(encoding="utf-8")
    rule = re.search(r"\.shop-tavern \.shop-line \{([^}]*)\}", css).group(1)
    assert "height: calc(3.2em" in rule and "line-clamp: 2" in rule
