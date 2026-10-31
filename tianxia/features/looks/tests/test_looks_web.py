"""擂台形象的畫面（萬寶閣「形象」那一頁，畫在商城包的網頁檔裡）：貨架上有形象才多一格「形象」；每一套一張卡，穿著的寫「穿著」、買了的「換上」、
沒買的一顆價錢（點了走貨架同一條購買確認）；換上送 /api/looks/wear。擂台動畫照 looks 的 me_look／foe_look 抓 web/img/looks/<id>/。"""
from __future__ import annotations

import pytest
from test_mall_web import _async, _click, _view, m_on, run  # noqa: F401  m_on 是 fixture

import webharness

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")

LOOKS = {"worn": "moying", "looks": [
    {"id": "", "name": "斗笠小子", "note": "", "owned": True, "item": None},
    {"id": "moying", "name": "墨影", "note": "一身墨色。", "owned": True, "item": None},
    {"id": "jinshen", "name": "金身", "note": "通體鎏金。", "owned": False, "item": "look_jinshen"},
]}


def _shelf():
    d = _view()
    d["looks"] = True
    d["items"].append({"id": "look_jinshen", "name": "金身形象", "note": "", "price": 600, "kind": "look", "kind_name": "形象",
                       "effects": "擂台形象一套（換季也帶著走）", "limit": "", "can": True, "why": None, "after": 4400,
                       "gives": {"look": 1}, "card_to": None, "look": "jinshen"})
    return d


def _layer(m, extra="", responses=None):
    """打開商城（點錠子鈕），再做 extra；/api/mall 給有形象的貨架（同 test_mall_web._layer，貨架換一份）。"""
    return run(m, _async(_click('{ act: "mall-open" }') + extra + """
      return { app: T.els.app.innerHTML, calls: T.calls };"""), responses={**(responses or {}), "/api/mall": _shelf()})


def test_the_look_tab_shows_each_look_and_wears_one(m_on):  # noqa: F811
    out = _layer(m_on, _click('{ act: "mall-tab", tab: "look" }') + _click('{ act: "look-wear", id: "" }'),
                 responses={"/api/looks/wear": {"message": "換上了「斗笠小子」。", "looks": {**LOOKS, "worn": ""}}, "/api/looks": LOOKS})
    assert any(c[0] == "/api/looks/wear" and c[1] == {"look": ""} for c in out["calls"])
    html = out["app"]
    assert "斗笠小子" in html and "墨影" in html and "金身" in html
    assert 'data-act="mall-pick" data-id="look_jinshen"' in html  # 沒買的那一套：一顆價錢、走貨架的購買確認
    assert "/static/img/looks/moying/hero_bare_idle.webp" in html
    assert "換上了「斗笠小子」" in html


def test_no_look_tab_without_looks_on_the_shelf(m_on):  # noqa: F811
    out = run(m_on, _async(_click('{ act: "mall-open" }') + "return { app: T.els.app.innerHTML };"), responses={"/api/mall": _view()})
    assert 'data-tab="look"' not in out["app"]
    assert 'data-tab="look"' in _layer(m_on)["app"]


ORDER = {"price": 900, "name_max": 6, "prompt_max": 120, "open": False, "list": [
    {"id": 3, "name": "黑衣客", "prompt": "黑衣蒙面", "status": "rejected", "status_text": "退回", "reason": "看不清楚"},
]}


def test_the_look_tab_has_the_order_form_and_my_orders(m_on):  # noqa: F811
    looks = {**LOOKS, "order": ORDER}
    out = _layer(m_on, _click('{ act: "mall-tab", tab: "look" }') + _click('{ act: "look-order" }'),
                 responses={"/api/looks": looks})
    html = out["app"]
    assert 'id="look-name"' in html and 'id="look-prompt"' in html and 'data-act="look-order"' in html
    assert "黑衣客" in html and "退回" in html and "看不清楚" in html
    assert "先替這一套取個名字" in html  # 沒填名字就按：掌櫃講原因、不送
    assert not any(c[0] == "/api/looks/order" for c in out["calls"])


def test_an_open_order_hides_the_form(m_on):  # noqa: F811
    looks = {**LOOKS, "order": {**ORDER, "open": True, "list": [{**ORDER["list"][0], "status": "pending", "status_text": "等圖中", "reason": ""}]}}
    html = _layer(m_on, _click('{ act: "mall-tab", tab: "look" }'), responses={"/api/looks": looks})["app"]
    assert 'id="look-name"' not in html and "等圖中" in html


def test_the_admin_box_lists_open_orders_with_prompts(m_on):  # noqa: F811
    import json

    from test_mall_web import DRIVER as MALL_DRIVER

    driver = MALL_DRIVER.replace('wholeApp(["S", ', 'wholeApp(["S", "looksAdminHtml", ', 1)
    admin = {"sheets": {"hero_bare_idle": 4, "hero_bare_hit": 3}, "gen": "off", "done": [], "open": [
        {"id": 5, "owner": "沈浪", "name": "白衣書生", "prompt": "白衣書生，背著竹簍", "status": "pending", "status_text": "等圖中",
         "reason": "", "look": "u5", "have": ["hero_bare_idle"], "prompts": {"hero_bare_idle": "Style: idle", "hero_bare_hit": "Style: hit"}}]}
    script = f"H.S.adLooks = {json.dumps(admin, ensure_ascii=False)}; return H.looksAdminHtml();"
    html = webharness.run(driver, {"m": m_on, "script": script, "S": {}, "menxia": None, "stored": {}, "responses": {}})
    assert "白衣書生，背著竹簍" in html and "Style: idle" in html
    assert 'id="ad-looks-file-5"' in html and 'data-op="reject"' in html
    assert 'data-op="release" data-id="5" disabled' in html  # 九張還沒齊：上架按不下去
