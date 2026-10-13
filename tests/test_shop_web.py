"""店面第一批的網頁（店面獨立介面設計第一、二、五節）：假瀏覽器照 test_prologue_web 的那一套跑整支 app.js。"""
from __future__ import annotations

import json

import pytest
from test_prologue_web import DRIVER as PROLOGUE_DRIVER
from test_shop import _smith

import server
import webharness

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
NAMES_START = 'wholeApp(["S", '
assert PROLOGUE_DRIVER.count(NAMES_START) == 1
DRIVER = PROLOGUE_DRIVER.replace(NAMES_START, 'wholeApp(["S", "shopHtml", "renderShop", "shopPolled", "smithForge", "revealHtml", ')


def run(m, script, S=None, responses=None):
    return webharness.run(DRIVER, {"m": m, "script": script, "S": S or {}, "menxia": None, "stored": {}, "responses": responses or {}})


@pytest.fixture
def m(content, world):
    return server.main_view(_smith(content, world))


# ── Task 5：店面那一層 ──


def test_the_shop_covers_the_screen_with_the_sign_line_and_four_tabs(m):
    html = run(m, "H.render(); return T.els.app.innerHTML;")
    shop = m["shop"]
    assert 'class="shop-layer shop-smith"' in html and shop["sign"] in html and shop["line"] in html
    assert f'data-act="choose" data-id="{shop["back"]}"' in html and "出店" in html
    for tab in ("架上", "打造", "淬煉與修", "裝備庫"):
        assert tab in html
    assert 'data-act="choose" data-id="smith:page:armor"' in html  # 兵器／防具切換
    assert html.count('data-act="choose" data-id="smith:buy:') == 6


def test_each_page_sends_the_right_action(m):
    out = run(m, """
      const pages = {};
      for (const tab of ["shelf", "temper", "rack", "forge"]) { H.S.shopTab = tab; H.render(); pages[tab] = T.els.app.innerHTML; }
      return pages;""")
    assert 'data-id="smith:buy:劍"' in out["shelf"]
    assert m["shop"]["worn"]["empty"] in out["temper"]  # 手上沒有兵器
    assert "shop-cell" in out["forge"] and 'data-act="shop-go"' in out["forge"] and 'data-book="forge"' in out["forge"]


def test_no_shop_layer_without_a_shop(m):
    plain = {**m}
    plain.pop("shop")
    assert "shop-layer" not in run(plain, "H.render(); return T.els.app.innerHTML;")


def test_the_shop_layer_follows_the_server(m):
    plain = {**m}
    plain.pop("shop")
    out = run(m, """
      H.S.tab = "jianghu"; H.render();
      const was = H.S.main; H.setMain(H.S.next); const closed = H.shopPolled(was);
      return { closed, html: T.els.app.innerHTML };""", S={"next": plain})
    assert out["closed"] is True and "shop-layer" not in out["html"]


def test_a_poll_redraws_only_the_shop(m):
    richer = json.loads(json.dumps(m))
    richer["shop"]["silver"] = 999
    out = run(m, """
      H.render(); T.els.page.innerHTML = "OLD";
      const layer = { outerHTML: "" }; T.qs[".shop-layer"] = layer;
      const was = H.S.main; H.setMain(H.S.next); H.shopPolled(was);
      return { page: T.els.page.innerHTML, layer: layer.outerHTML };""", S={"next": richer})
    assert out["page"] == "OLD" and "銀 999" in out["layer"]


def test_the_shop_waits_for_the_finger(m):
    richer = json.loads(json.dumps(m))
    richer["shop"]["silver"] = 999
    out = run(m, """
      return (async () => {
        H.render();
        const layer = { outerHTML: "" }; T.qs[".shop-layer"] = layer;
        T.docListeners.pointerdown.forEach((f) => f({}));
        const was = H.S.main; H.setMain(H.S.next); H.shopPolled(was);
        const held = layer.outerHTML;
        T.docListeners.pointerup.forEach((f) => f({}));
        await new Promise((ok) => setTimeout(ok, 5));
        return { held, after: layer.outerHTML };
      })();""", S={"next": richer})
    assert out["held"] == "" and "銀 999" in out["after"]


def test_rack_rows_wield_and_dismantle_through_menxia(content, world):
    from tianxia.state import Weapon

    game = _smith(content, world)
    p = game.state.player
    p.weapon = Weapon(id="兵:9", name="手上刃", kind="劍", attribute="柔", tier=1, quality="下品")
    p.rack = [Weapon(id=f"兵:{i}", name=f"庫刃{i}", kind="刀", attribute="剛", tier=1, quality="下品") for i in range(1, 11)]
    m = server.main_view(game)
    out = run(m, 'H.S.shopTab = "rack"; H.render(); return T.els.app.innerHTML;')
    assert out.count('data-act="shop-wield"') == 8 and "再列 2 件" in out and 'data-act="shop-dismantle"' in out
