"""素材與經濟 B6 的網頁（企劃者 2026-10-15 挑草圖 A1＋B3＋C1）：鐵匠鋪多第五頁「素材」（上半升階、下半收購）、大本營的捐軍備做成店面那樣的
「軍需帳」、江湖頁戰況卡底下一行陣營軍備。假瀏覽器照 tests/test_shop2_web.py 跑整支 app.js；CSS 照原字查（375 寬不撐開、不折行）。
正式內容、週末設定（Config.economy 預設開）。"""
from __future__ import annotations

import random
import re

import pytest
from conftest import real_content
from test_prologue_web import DRIVER as PROLOGUE_DRIVER

import server
import webharness
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
NAMES_START = 'wholeApp(["S", '
assert PROLOGUE_DRIVER.count(NAMES_START) == 1
DRIVER = PROLOGUE_DRIVER.replace(NAMES_START, 'wholeApp(["S", "shopHtml", "renderShop", "shopPolled", "tradeHtml", "donateHtml", ')
TW_MIDNIGHT = 16 * 3600


def run(m, script, S=None, responses=None):
    return webharness.run(DRIVER, {"m": m, "script": script, "S": S or {}, "menxia": None, "stored": {}, "responses": responses or {}})


def _click(dataset: str) -> str:
    """送一次點擊給 app.js 的 click 處理器（同 tests/test_shop2_web.py::_click）。"""
    return ("await T.docListeners.click[0]({ target: { closest: () => ({ dataset: " + dataset
            + ", classList: { contains: () => false, add() {}, remove() {} }, isConnected: false }) } });")


def _game(at="yingchuan", faction="guan", bag=None, silver=500, **econ):
    c = real_content("week7")
    c.config.auto_open_first_season = True
    for key, value in econ.items():
        setattr(c.config.economy, key, value)
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.location, p.faction = at, faction
    p.tutorial_step = len(c.tutorial.steps)
    p.stats["silver"] = silver
    p.materials = dict(bag or {})
    game.now = TW_MIDNIGHT + 3600
    return game


@pytest.fixture
def smith():
    game = _game(bag={"rou_1": 7, "man_2": 3, "kuai_3": 1})
    game.choose("act:smith")
    return game


@pytest.fixture
def depot():
    game = _game(at="changshe", bag={"rou_1": 30, "kuai_1": 80, "man_2": 4, "gang_3": 1})
    game.choose("act:donate")
    return game


# ── A1：鐵匠鋪的第五頁「素材」──


def test_the_smith_has_a_fifth_tab_only_while_trading_is_on(smith):
    m = server.main_view(smith)
    html = run(m, "H.render(); return T.els.app.innerHTML;")
    assert 'data-tab="trade"' in html and ">素材<" in html
    off = _game(bag={"rou_1": 7}, sell=False, upgrade=False)
    off.choose("act:smith")
    html = run(server.main_view(off), "H.render(); return T.els.app.innerHTML;")
    assert 'data-tab="trade"' not in html


def test_the_materials_page_puts_upgrades_above_selling(smith):
    m = server.main_view(smith)
    trade = m["shop"]["trade"]
    html = run(m, 'H.S.shopTab = "trade"; H.render(); return T.els.app.innerHTML;')
    assert trade["up_cap"] in html and trade["sell_cap"] in html
    assert html.index(trade["up_cap"]) < html.index(trade["sell_cap"])  # 上半升階、下半收購（企劃者 2026-10-15）
    assert 'data-act="trade-up" data-attr="柔" data-tier="2"' in html and "五成・其餘隨機" in html
    assert "柳絲綿×3 →" in html and "5 兩" in html
    assert 'data-act="trade-sell" data-id="rou_1" data-n="1"' in html and "全賣 14 兩" in html
    assert 'class="shop-pages"' not in html  # 素材頁不分兵器、防具
    assert "smith-hero" not in html  # 爐火只在架上頁


def test_the_three_to_four_cell_counts_the_season_not_today():
    """FB-342：升階格的上限字照伺服器給的（三換四是「這一季還能」），網頁不再寫死「今天」。"""
    game = _game(bag={"gang_3": 5}, silver=1000)
    game.choose("act:smith")
    html = run(server.main_view(game), 'H.S.shopTab = "trade"; H.render(); return T.els.app.innerHTML;')
    assert 'data-tier="4"' in html and "這一季還能 2 個" in html and "今天還能 2 個" not in html


def test_upgrading_posts_and_says_what_came_out(smith):
    m = server.main_view(smith)
    smith.smith_upgrade("柔", 2)
    after = server.main_view(smith)
    reply = {"/api/do/smith_upgrade": {"main": after, "message": "<p>鐵匠把 3 個柳絲綿下爐熬煉，火候一偏，煉出的是一個【玄鋼骨】。</p><p>銀兩 -5</p>"}}
    out = run(m, 'return (async () => { H.S.shopTab = "trade"; H.render(); ' + _click('{ act: "trade-up", attr: "柔", tier: "2" }')
              + " return { call: T.calls.find((c) => c[0] === '/api/do/smith_upgrade'), html: T.els.app.innerHTML, note: H.S.shopNote }; })();",
              responses=reply)
    assert out["call"][1] == {"attribute": "柔", "tier": 2}
    assert out["note"] == "鐵匠把 3 個柳絲綿下爐熬煉，火候一偏，煉出的是一個【玄鋼骨】。"
    assert "煉出的是一個【玄鋼骨】" in out["html"] and 'class="shop-done"' in out["html"]


def test_a_greyed_upgrade_only_says_why(smith):
    m = server.main_view(smith)
    row = next(r for r in m["shop"]["trade"]["upgrade"] if (r["attribute"], r["tier"]) == ("剛", 2))
    assert row["problem"] and row["short"] == "手上 0／3"
    out = run(m, 'return (async () => { H.S.shopTab = "trade"; H.render(); '
              + _click('{ act: "trade-up", attr: "剛", tier: "2", why: ' + repr(row["problem"]) + " }")
              + " return { calls: T.calls.map((c) => c[0]), toast: T.els.toast.textContent, html: T.els.app.innerHTML }; })();")
    assert "/api/do/smith_upgrade" not in out["calls"] and row["problem"] in out["toast"]
    assert "手上 0／3" in out["html"]


def test_selling_all_asks_first(smith):
    m = server.main_view(smith)
    out = run(m, 'return (async () => { H.S.shopTab = "trade"; H.render(); '
              + _click('{ act: "trade-sell", id: "rou_1", n: "7", confirm: "把 7 個柳絲綿都賣了，換 14 兩？" }')
              + " return { asked: T.bodyHtml.join(''), calls: T.calls.map((c) => c[0]) }; })();")
    assert "把 7 個柳絲綿都賣了，換 14 兩？" in out["asked"] and "/api/do/smith_sell" not in out["calls"]


def test_selling_one_posts_right_away(smith):
    m = server.main_view(smith)
    smith.smith_sell("rou_1", 1)
    reply = {"/api/do/smith_sell": {"main": server.main_view(smith), "message": "<p>鐵匠收下柳絲綿 ×1，數了 2 兩給你。</p><p>銀兩 +2</p>"}}
    out = run(m, 'return (async () => { H.S.shopTab = "trade"; H.render(); ' + _click('{ act: "trade-sell", id: "rou_1", n: "1" }')
              + " return T.calls.find((c) => c[0] === '/api/do/smith_sell'); })();", responses=reply)
    assert out[1] == {"material": "rou_1", "count": 1}


def test_changing_tab_clears_the_note(smith):
    m = server.main_view(smith)
    out = run(m, 'return (async () => { H.S.shopTab = "trade"; H.S.shopNote = "舊的一句"; H.render(); '
              + _click('{ act: "shop-tab", tab: "shelf" }') + " return H.S.shopNote; })();")
    assert out is None


# ── B3：大本營的軍需帳 ──


def test_the_depot_is_a_shop_with_stores_room_and_cells(depot):
    m = server.main_view(depot)
    shop = m["shop"]
    html = run(m, "H.render(); return T.els.app.innerHTML;")
    assert 'class="shop-layer shop-donate"' in html and "長社・官軍軍需帳" in html and shop["line"] in html
    assert 'data-act="choose" data-id="donate:back"' in html and "出店" in html
    for name in ("糧秣", "箭矢", "甲冑", "戰馬"):
        assert name in html
    assert "今天還能捐 100 點" in html and html.count('data-act="dn-cell"') == 4
    assert "shop-tabs" not in html  # 軍需帳只有一頁
    assert 'data-act="dn-go" disabled' in html  # 還沒挑


def test_tapping_cells_picks_what_fits_today(depot):
    m = server.main_view(depot)
    out = run(m, "return (async () => { H.render(); " + _click('{ act: "dn-cell", id: "rou_1" }') + _click('{ act: "dn-cell", id: "kuai_1" }')
              + " return { pick: H.S.donatePick, html: T.els.app.innerHTML }; })();")
    assert out["pick"] == {"rou_1": 30, "kuai_1": 70}  # 柔一 30 點，快一只收得下剩的 70 點
    assert "捐出 100 點" in out["html"] and "捐 30" in out["html"]


def test_tapping_a_picked_cell_puts_it_back_and_steps_change_the_count(depot):
    m = server.main_view(depot)
    out = run(m, "return (async () => { H.render(); " + _click('{ act: "dn-cell", id: "rou_1" }')
              + _click('{ act: "dn-step", id: "rou_1", d: "-1" }') + " const stepped = { ...H.S.donatePick }; "
              + _click('{ act: "dn-cell", id: "rou_1" }') + " return { stepped, after: H.S.donatePick }; })();")
    assert out["stepped"] == {"rou_1": 29} and out["after"] == {}


def test_tier_one_picks_every_tier_one_until_the_room_runs_out(depot):
    m = server.main_view(depot)
    out = run(m, "return (async () => { H.render(); " + _click('{ act: "dn-tier1" }') + " return H.S.donatePick; })();")
    assert out == {"rou_1": 30, "kuai_1": 70}


def test_a_greyed_cell_only_says_why(depot):
    depot.state.player.donate_day, depot.state.player.donated_today = depot.econ_day(), 95
    m = server.main_view(depot)
    cell = next(c for c in m["shop"]["cells"] if c["id"] == "gang_3")
    assert cell["problem"]
    out = run(m, "return (async () => { H.render(); " + _click('{ act: "dn-cell", id: "gang_3", why: ' + repr(cell["problem"]) + " }")
              + " return { pick: H.S.donatePick, toast: T.els.toast.textContent }; })();")
    assert out["pick"] == {} and cell["problem"] in out["toast"]


def test_donating_posts_the_picks_and_clears_them(depot):
    m = server.main_view(depot)
    depot.donate_items([("rou_1", 30)])
    reply = {"/api/do/donate": {"main": server.main_view(depot), "message": "<p>你把柳絲綿 ×30交給軍需官，記進官軍的軍備。</p><p>戰馬 +30</p>"}}
    out = run(m, "return (async () => { H.render(); " + _click('{ act: "dn-cell", id: "rou_1" }') + _click('{ act: "dn-go" }')
              + " return { call: T.calls.find((c) => c[0] === '/api/do/donate'), pick: H.S.donatePick, note: H.S.shopNote, html: T.els.app.innerHTML }; })();",
              responses=reply)
    assert out["call"][1] == {"items": [{"material": "rou_1", "count": 30}]}
    assert out["pick"] == {} and out["note"].startswith("你把柳絲綿")
    assert "今天還能捐 70 點" in out["html"] and "戰馬" in out["html"]


def test_the_server_reads_the_items_list_and_skips_bad_ones():
    assert server.donate_items({"items": [{"material": "rou_1", "count": 3}, {"count": 2}, "x", {"material": "kuai_1"}]}) == [("rou_1", 3), ("kuai_1", 1)]
    assert server.donate_items({"items": "nope"}) == []
    assert len(server.donate_items({"items": [{"material": "rou_1"}] * 99})) == server.DONATE_ITEMS_MAX


# ── C1：江湖頁戰況卡底下一行 ──


def test_the_trends_page_has_one_line_of_stores_under_the_fronts():
    """減法季批 1：戰況圖卡與軍備那一行從江湖頁搬到見聞・大事・大勢的最上面。"""
    game = _game(at="changshe", bag={"man_1": 3})
    game.donate("man_1", 3)
    m = server.main_view(game)
    html = run(m, 'H.S.tab = "news"; H.S.news = "trends"; H.render(); return T.els.page.innerHTML;')
    line = re.search(r'<p class="arms-line">.*?</p>', html)
    assert line and "官軍軍備" in line.group(0) and "糧秣 <b>3</b>" in line.group(0) and "戰馬 <b>0</b>" in line.group(0)
    assert html.index('class="war"') < html.index('class="arms-line"')  # 排在戰況圖卡底下
    assert "arms-line" not in run(m, 'H.S.tab = "jianghu"; H.render(); return T.els.page.innerHTML;')
    ranger = _game(faction=None)
    assert "arms-line" not in run(server.main_view(ranger), 'H.S.tab = "news"; H.S.news = "trends"; H.render(); return T.els.page.innerHTML;')


# ── 375 寬：不撐開、不折行（CSS 照原字查）──


def _rule(selector: str) -> str:
    css = (server.WEB / "style.css").read_text(encoding="utf-8")
    found = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert found, selector
    return found.group(1)


def test_the_new_rows_never_push_the_page_wider():
    assert "minmax(0, 1fr)" in _rule(".shop-layer .sell-row") and "white-space: nowrap" in _rule(".shop-layer .sell-row .acts")
    assert "white-space: nowrap" in _rule(".shop-layer .sell-row .nm small") and "min-width: 0" in _rule(".shop-layer .sell-row .nm")
    assert "min-width: 0" in _rule(".shop-layer .up-cell") and "white-space: nowrap" in _rule(".shop-layer .up-cell .from")
    assert "minmax(0, 1fr)" in _rule(".shop-layer .arm-tiles")
    assert "flex-wrap: wrap" in _rule(".arms-line")


def test_the_depot_follows_the_game_column_on_desktop():
    css = (server.WEB / "style.css").read_text(encoding="utf-8")
    # FB-225：底色只畫在中間那一欄（同一條還有三間店與擂台，FB-306；照選擇器清單查，不寫死整串）
    paint = re.search(r"([^{}]+)\{\s*background-color: var\(--paper\); background-size: min\(100%, 640px\) 100%;", css)
    assert paint and ".shop-layer.shop-donate" in [s.strip() for s in paint.group(1).split(",")]
