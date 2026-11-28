"""鐵匠鋪重排（web/tiepu.js）：開關開著時鐵匠鋪那一層換成圖頭、鐵匠那一句、眼下一張卡、五面牌（打造是寬牌）；點一面拉起那一塊，
✕ 收回進門那一頁。按的都是原本的鈕（choose、shop-tab……，smithy.js 認）。假瀏覽器照 test_prologue_web 那一套跑整支 app.js；
資料照 tianxia/features/smithy/tests/test_shop.py::_smith（測試內容）。沒有 node 的略過。"""
from __future__ import annotations

import re

import pytest
from test_prologue_web import DRIVER as PROLOGUE_DRIVER
from test_shop import _smith

import server
import webharness

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
NAMES_START = 'wholeApp(["S", '
assert PROLOGUE_DRIVER.count(NAMES_START) == 1
DRIVER = PROLOGUE_DRIVER.replace(NAMES_START, 'wholeApp(["S", "shopHtml", "renderShop", ')


def run(m, script, S=None):
    return webharness.run(DRIVER, {"m": m, "script": script, "S": S or {}, "menxia": None, "stored": {}, "responses": {}})


def _click(dataset: str) -> str:
    return ("await T.docListeners.click[0]({ target: { closest: () => ({ dataset: " + dataset
            + ", classList: { contains: () => false, add() {}, remove() {} }, isConnected: false }) } });")


def _view(content, world, on=True, **kw):
    content.config.tiepu.enabled = on
    return server.main_view(_smith(content, world, **kw))


def test_status_carries_the_switch_and_bots_get_nothing(content, world):
    content.config.tiepu.enabled = True
    g = _smith(content, world)
    assert server.main_view(g)["tiepu"] == {"on": True}
    g.state.player.bot = True
    assert "tiepu" not in server.main_view(g)


def test_switch_off_keeps_the_old_smithy(content, world):
    html = run(_view(content, world, on=False), "H.render(); return T.els.app.innerHTML;")
    assert 'class="shop-layer shop-smith"' in html and "shop-tabs" in html and "tp-pls" not in html


def test_first_screen_is_hero_say_and_plaques(content, world):
    m = _view(content, world)
    html = run(m, "H.render(); return T.els.app.innerHTML;")
    shop = m["shop"]
    assert 'class="shop-layer shop-smith tp"' in html and "shop-tabs" not in html  # 底下那一排分頁不畫
    assert "<h1>鐵匠鋪</h1>" in html and "scene-smithy.webp" in html and f'data-act="choose" data-id="{shop["back"]}"' in html
    assert shop["line"] in html  # 鐵匠那一句
    tabs = re.findall(r'class="xk-pl[^"]*" data-act="shop-tab" data-tab="([\w-]+)"', html)
    assert tabs[0] == "forge" and "tp-shelf" in tabs and "rack" in tabs  # 打造是第一面、寬牌
    assert "tp-fur" in html and "背包素材 7 個" in html  # 寬牌上畫爐口兩格、背包幾個素材
    assert "○" not in html


def test_an_empty_hand_puts_the_fitting_ware_on_the_eye_card(content, world):
    m = _view(content, world)
    fit = next(w for w in m["shop"]["shelf"] if w["fit"])
    html = run(m, "H.render(); return T.els.app.innerHTML;")
    eye = html.split('aria-label="眼下"')[1].split("</section>")[0]
    assert fit["name"] in eye and f'data-act="choose" data-id="{fit["id"]}"' in eye and f'買 {fit["price"]} 兩' in eye  # 鈕在卡上直接買
    assert 'data-act="tp-later"' in eye


def test_later_hides_the_eye_card(content, world):
    m = _view(content, world)
    out = run(m, "return (async () => { H.render(); const key = /data-act=\"tp-later\" data-key=\"([^\"]+)\"/.exec(T.els.app.innerHTML)[1];"
              + _click('{ act: "tp-later", key }') + " return T.els.app.innerHTML; })();")
    assert 'aria-label="眼下"' not in out and "tp-pls" in out


def test_a_worn_blade_below_half_asks_to_repair_on_the_eye_card(content, world):
    m = _view(content, world)
    m["shop"]["worn"] = {"item": {"id": "兵:1", "name": "厚背劍", "grade": "一階中品", "wear_word": "鋒利度", "wear": 40, "tempers": 0, "temper_max": 10,
                                  "wear_note": "", "temper_safe": 3, "temper_pct": 100},
                         "empty": "", "repair": {"id": "smith:repair", "use": "精鐵砂×1＋5 兩", "enabled": True, "why": None},
                         "temper": {"id": "smith:temper", "use": "精鐵砂×1", "enabled": True, "why": None}, "unfit": ""}
    html = run(m, "H.render(); return T.els.app.innerHTML;")
    eye = html.split('aria-label="眼下"')[1].split("</section>")[0]
    assert "該修了" in eye and "厚背劍只剩四成" in eye and 'data-act="choose" data-id="smith:repair"' in eye and "--w:40%" in eye


@pytest.mark.parametrize("tab,name", [("tp-shelf", "架上"), ("forge", "打造"), ("rack", "裝備庫")])
def test_a_plaque_pulls_up_its_sheet_and_close_goes_back(content, world, tab, name):
    m = _view(content, world)
    out = run(m, "return (async () => { H.render(); " + _click(f'{{ act: "shop-tab", tab: "{tab}" }}')
              + " const sheet = T.els.app.innerHTML; " + _click('{ act: "shop-tab", tab: "shelf" }')
              + " return { sheet, home: T.els.app.innerHTML }; })();")
    assert f"<h2>{name}</h2>" in out["sheet"] and "tp-pls" not in out["sheet"] and "xk-hero tp-hero mini" in out["sheet"]
    assert 'class="shop-body tp-body"' in out["sheet"]  # 捲的那一層照舊（renderShop 照放捲到哪裡）
    assert "tp-pls" in out["home"] and "xk-sheet" not in out["home"]


def test_the_shelf_sheet_is_ware_cards_that_buy_on_tap(content, world):
    m = _view(content, world)
    html = run(m, "H.render(); return T.els.app.innerHTML;", S={"shopTab": "tp-shelf"})
    for w in m["shop"]["shelf"]:
        assert f'data-act="choose" data-id="{w["id"]}"' in html
    assert len(re.findall(r'class="tp-ware[ "]', html)) == len(m["shop"]["shelf"]) and 'class="tp-kinds"' in html  # 兵器防具兩顆大印


def test_the_rack_sheet_draws_bars_not_pips(content, world):
    m = _view(content, world)
    m["shop"]["worn"] = {"item": {"id": "兵:1", "name": "厚背劍", "grade": "一階中品", "wear_word": "鋒利度", "wear": 80, "tempers": 3, "temper_max": 10,
                                  "wear_note": "", "temper_safe": 3, "temper_pct": 90},
                         "empty": "", "repair": {"id": "smith:repair", "use": "精鐵砂×1＋5 兩", "enabled": True, "why": None},
                         "temper": {"id": "smith:temper", "use": "精鐵砂×1", "enabled": True, "why": None}, "unfit": ""}
    html = run(m, "H.render(); return T.els.app.innerHTML;", S={"shopTab": "rack"})
    assert "tp-wcard" in html and "3／10" in html and "--w:30%" in html and 'class="tempers"' not in html  # 淬煉是長條，不是小格子
    assert 'data-id="smith:temper"' in html and "成功 90%" in html
