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
