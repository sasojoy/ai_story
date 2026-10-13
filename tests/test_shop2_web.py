"""店面第二批的網頁（店面獨立介面設計第三、四節）：假瀏覽器照 test_prologue_web 的那一套跑整支 app.js（同 tests/test_shop_web.py）。
斷言只看 T.els.app.innerHTML——外殼與店面那一層；江湖頁的舊選單畫在 T.els.page，所以斷言裡的 data-act="choose" 都是店面上的鈕。"""
from __future__ import annotations

import json

import pytest
from test_prologue_web import DRIVER as PROLOGUE_DRIVER
from test_shop2 import ARMS, SCOUT, SWORD, _board, _horse, _ids, _market

import server
import webharness
from tianxia import mounts, shopview
from tianxia.state import Equipment

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
NAMES_START = 'wholeApp(["S", '
assert PROLOGUE_DRIVER.count(NAMES_START) == 1
DRIVER = PROLOGUE_DRIVER.replace(
    NAMES_START, 'wholeApp(["S", "shopHtml", "renderShop", "shopPolled", "marketHtml", "boardHtml", "boardHanded", "divineFormHtml", ')


def run(m, script, S=None, responses=None):
    return webharness.run(DRIVER, {"m": m, "script": script, "S": S or {}, "menxia": None, "stored": {}, "responses": responses or {}})


def _click(dataset: str) -> str:
    """送一次點擊給 app.js 的 click 處理器：點到的元素帶 dataset（JS 物件字面值）。同 tests/test_shop_web.py::_click。"""
    return ("await T.docListeners.click[0]({ target: { closest: () => ({ dataset: " + dataset
            + ", classList: { contains: () => false, add() {}, remove() {} }, isConnected: false }) } });")


@pytest.fixture
def market(content, world):
    game = _market(content, world, horse=_horse(edge=40))
    game.state.player.rack = [_horse("騎:2", "黑鬃馬", 1, "上品")]
    return server.main_view(game)


# ── Task 4：共用店面框與馬市 ──


def test_the_market_draws_a_row_of_stalls_and_the_ridden_horse_card(market):
    html = run(market, "H.render(); return T.els.app.innerHTML;")
    shop = market["shop"]
    assert 'class="shop-layer shop-market"' in html and shop["sign"] in html and shop["line"] in html
    assert f'data-act="choose" data-id="{mounts.BACK}"' in html and "出店" in html
    assert html.count('data-act="shop-horse"') == 3  # 你騎的、待售、裝備庫一匹
    assert f'data-act="choose" data-id="{mounts.FEED}"' in html and f"{mounts.WEAR_WORD} 40" in html  # 預設點著你騎的
    assert shopview.HUNGRY_NOTE in html and "省體力" in html
    assert "shop-tabs" not in html  # 馬市不分頁


def test_tapping_a_stall_shows_its_card(market):
    out = run(market, "return (async () => { H.render(); " + _click('{ act: "shop-horse", id: "騎:2" }') + " return T.els.app.innerHTML; })();")
    assert f'data-id="{mounts.WIELD}騎:2"' in out and shopview.SLOWER in out and f'data-id="{mounts.FEED}"' not in out


def test_no_horse_draws_an_empty_stall_and_focuses_the_sale(content, world):
    m = server.main_view(_market(content, world))
    html = run(m, "H.render(); return T.els.app.innerHTML;")
    assert shopview.NO_HORSE in html and f'data-act="choose" data-id="{mounts.BUY}"' in html
    assert html.count('data-act="shop-horse"') == 1  # 空的那一間點不了


def test_a_greyed_card_button_says_why(content, world):
    m = server.main_view(_market(content, world, silver=10))
    html = run(m, "H.render(); return T.els.app.innerHTML;")
    assert f"還差 {content.config.mounts.shop_price - 10} 兩" in html and "disabled" in html


def test_moving_from_the_smithy_to_the_market_starts_the_market_fresh(content, world, market):
    from test_shop import _smith

    smith = server.main_view(_smith(content, world, name="鐵客"))
    out = run(smith, """
      H.S.shopTab = "rack"; H.S.shopReveal = { id: "兵:1", glow: "none" }; H.S.shopHorse = "騎:9"; H.render();
      const was = H.S.main; H.setMain(H.S.next); const drew = H.shopPolled(was);
      return { tab: H.S.shopTab, reveal: H.S.shopReveal, horse: H.S.shopHorse, drew, html: T.els.app.innerHTML };""", S={"next": market})
    assert (out["tab"], out["reveal"], out["horse"], out["drew"]) == ("shelf", None, None, True)
    assert "shop-market" in out["html"] and "shop-smith" not in out["html"]


def test_a_market_poll_redraws_only_the_shop(market):
    richer = json.loads(json.dumps(market))
    richer["shop"]["silver"] = 999
    out = run(market, """
      H.render(); T.els.page.innerHTML = "OLD";
      const layer = { outerHTML: "" }; T.qs[".shop-layer"] = layer;
      const was = H.S.main; H.setMain(H.S.next); H.shopPolled(was);
      return { page: T.els.page.innerHTML, layer: layer.outerHTML };""", S={"next": richer})
    assert out["page"] == "OLD" and "銀 999" in out["layer"]
