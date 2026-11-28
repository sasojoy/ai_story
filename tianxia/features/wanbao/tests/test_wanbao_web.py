"""萬寶閣重排（web/wanbao.js）：開關開著時商城那一層換成錢袋、圖頭、掌櫃那一句、眼下一張卡、五面牌（月卡是寬牌）；點一面拉起那一類，
一件一張大卡、按下去照舊走 mall-pick（商城包的購買確認）。元寶拆兩種時錢袋寫兩種、只收儲值的蓋「儲」。
資料照 tianxia/features/mall/tests/test_mall_web.py（測試內容＋test_mall 那幾件）。沒有 node 的略過。"""
from __future__ import annotations

import copy

import pytest
from test_mall_web import _async, _click, _game, _view, run

import server
import webharness

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
COINS = {"paid": 1280, "gift": 860, "gift_name": "五銖"}


def _m(content, on=True):
    content.config.wanbao.enabled = on
    return server.main_view(_game(content))


def _open(m, view, extra="", S=None):
    return run(m, _async(_click('{ act: "mall-open" }') + extra + " return T.els.app.innerHTML;"), S=S, responses={"/api/mall": view})


def test_status_carries_the_switch_and_bots_get_nothing(content):
    content.config.wanbao.enabled = True
    g = _game(content)
    assert server.main_view(g)["wanbao"] == {"on": True}
    g.state.player.bot = True
    assert "wanbao" not in server.main_view(g)


def test_switch_off_keeps_the_old_mall(content):
    html = _open(_m(content, on=False), _view())
    assert 'class="shop-layer shop-mall"' in html and "shop-tabs" in html and "mb-pls" not in html


def test_first_screen_is_purse_hero_and_plaques(content):
    html = _open(_m(content), _view())
    assert 'class="shop-layer shop-mall wb"' in html and "shop-tabs" not in html
    assert "<h1>萬寶閣</h1>" in html and 'data-act="wb-out"' in html and 'data-act="mall-tab" data-tab="log"' in html  # 錢袋點了看紀錄
    assert "5000<small>元寶</small>" in html  # 沒拆：一種
    cats = __import__("re").findall(r'data-act="wb-cat" data-cat="(\w+)"', html)
    assert cats[0] == "card" and "dan" in cats  # 月卡寬牌在最前
    assert "還沒開" in html and "○" not in html


def test_two_coins_show_both_purses_and_the_paid_seal(content):
    view = copy.deepcopy(_view())
    view["coins"] = COINS
    view["items"][2]["paid"] = True  # 月卡只收儲值
    html = _open(_m(content), view, _click('{ act: "wb-cat", cat: "card" }'))
    assert "1280<small>元寶</small>" in html and "860<small>五銖</small>" in html and 'class="ingot gift"' in html
    assert "<h2>月卡</h2>" in html and 'data-act="mall-pick" data-id="card_30"' in html and "mall-seal" in html  # 蓋「儲」


def test_an_unclaimed_card_day_puts_the_claim_on_the_eye_card(content):
    view = _view(card={"until": "11/19", "bonus": 1, "left": 18, "daily": {"ingots": 60, "pills": 1, "claimed": False}})
    html = _open(_m(content), view)
    eye = html.split('aria-label="眼下"')[1].split("</section>")[0]
    assert "月卡的份還沒領" in eye and 'data-act="mall-claim"' in eye and "還剩 18 天" in eye and 'data-act="wb-later"' in eye
    assert "還剩 <b>18 天</b>" in html and "--w:60%" in html  # 寬牌畫還剩幾天的長條


def test_no_pills_offers_the_cheapest_pack_on_the_eye_card(content):
    html = _open(_m(content), _view(count=0))
    eye = html.split('aria-label="眼下"')[1].split("</section>")[0]
    assert "回體丹用完了" in eye and 'data-act="mall-pick" data-id="pills_5"' in eye


def test_a_category_sheet_lists_its_wares_and_close_goes_back(content):
    out = run(_m(content), _async(_click('{ act: "mall-open" }') + _click('{ act: "wb-cat", cat: "dan" }')
                                   + " const sheet = T.els.app.innerHTML; " + _click('{ act: "wb-close" }')
                                   + " return { sheet, home: T.els.app.innerHTML };"), responses={"/api/mall": _view()})
    sheet = out["sheet"]
    assert "<h2>丹藥</h2>" in sheet and sheet.count('class="mb-ware') == 2 and "mb-pls" not in sheet
    assert 'class="mb-ware off" data-act="mall-pick" data-id="pills_30"' in sheet  # 買不了的畫淡、照樣點得到（掌櫃講原因）
    assert "mb-pls" in out["home"] and "mb-sheet" not in out["home"]


def test_picking_a_ware_in_the_sheet_still_asks_first(content):
    out = run(_m(content), _async(_click('{ act: "mall-open" }') + _click('{ act: "wb-cat", cat: "dan" }') + _click('{ act: "mall-pick", id: "pills_5" }')
                                   + " return { asks: T.bodyHtml, app: T.els.app.innerHTML };"), responses={"/api/mall": _view()})
    assert "回體丹五顆" in "".join(out["asks"]) and "<h2>丹藥</h2>" in out["app"]  # 確認框照舊、那一塊還拉著


def test_out_closes_the_layer_and_forgets_the_sheet(content):
    out = run(_m(content), _async(_click('{ act: "mall-open" }') + _click('{ act: "wb-cat", cat: "dan" }') + _click('{ act: "wb-out" }')
                                   + " return { open: H.S.mallOpen, cat: H.S.wbCat || null };"), responses={"/api/mall": _view()})
    assert out == {"open": False, "cat": None}
