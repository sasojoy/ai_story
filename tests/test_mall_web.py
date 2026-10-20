"""商城第二批：畫面（企劃者 2026-10-20 挑的對比圖：入口乙＋丙、商城那一層子；docs/superpowers/specs/2026-10-20-商城架構-design.md 4.6、4.7）。

- 入口乙：右上角齒輪旁一顆錠子鈕寫元寶餘額；丙：底部分頁第六格「商城」。兩個都點了打開商城那一層。商城關著（main 沒有 mall）時
  兩個都沒有、分頁照舊五格；序章裡跟其他還沒開放的分頁一樣藏著，亮齊（reveal 有 all）或出了草廬才出現（FB-490）。
- 商城那一層沿用店面的框（shopHtml：招牌、掌櫃那一句、左上出店），底下貨架、紀錄兩頁；按一件先問一次（花多少、元寶剩多少、
  丹或月卡變成多少），買成了餘額與狀態列的丹鈕當場換；買不了的（元寶不夠、限購、下架）掌櫃回一句原因。
- 設定頁的管理者區多一組商城：查帳、補發、扣回、退一筆。
假瀏覽器照 test_prologue_web 那一套跑整支 app.js（同 test_shop2_web）。"""
from __future__ import annotations

import copy
import random
import re

import pytest
from test_prologue_web import DRIVER as PROLOGUE_DRIVER
from test_prologue_web import with_reveal
from test_mall import _items

import server
import webharness
from tianxia.engine import Game

pytestmark = [pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過"), pytest.mark.slow]
NAMES_START = 'wholeApp(["S", '
assert PROLOGUE_DRIVER.count(NAMES_START) == 1
DRIVER = PROLOGUE_DRIVER.replace(NAMES_START, 'wholeApp(["S", "shopHtml", "openMall", "renderMall", ')

HOUR = 3600
DAY = 24 * HOUR
T0 = DAY - 8 * HOUR + 20000 * DAY + 9 * HOUR  # 某一天台灣早上九點（同 test_mall）
REF = re.compile(r"^[A-Za-z0-9_-]{8,64}$")  # 伺服器照用的編號（server.MALL_REF）


def run(m, script, S=None, responses=None):
    return webharness.run(DRIVER, {"m": m, "script": script, "S": S or {}, "menxia": None, "stored": {}, "responses": responses or {}})


def _click(dataset: str) -> str:
    """送一次點擊給 app.js 的 click 處理器（同 tests/test_shop2_web.py::_click）。"""
    return ("await T.docListeners.click[0]({ target: { closest: () => ({ dataset: " + dataset
            + ", classList: { contains: () => false, add() {}, remove() {} }, isConnected: false }) } });")


def _text(html: str) -> str:
    """拿掉標籤（掌櫃那一句照標點切成不折行的小段，同打點的 sayHtml）。"""
    return re.sub(r"<[^>]+>", "", html)


def _async(body: str) -> str:
    return "return (async () => { " + body + " })();"


def _view(balance=5000, count=28, card=None):
    """/api/mall 的形狀（Game.mall_view）：兩件丹、一張月卡；三十顆那一包元寶不夠。"""
    return {
        "balance": balance, "card": card, "grant": 5000,
        "pills": {"name": "回體丹", "count": count, "today": 2, "cap": 3 if card else 2, "restore": 150, "bonus": 1},
        "items": [
            {"id": "pills_5", "name": "回體丹五顆", "note": "五顆回體丹，買下就收進行囊。", "price": 100, "kind": "consumable",
             "kind_name": "消耗品", "effects": "回體丹 5 顆", "limit": "每天限 5 次（今天已買 0）", "can": True, "why": None,
             "after": balance - 100, "gives": {"pills": 5}, "card_to": None},
            {"id": "pills_30", "name": "回體丹三十顆", "note": "三十顆回體丹。", "price": 9000, "kind": "consumable",
             "kind_name": "消耗品", "effects": "回體丹 30 顆", "limit": "", "can": False,
             "why": "元寶不夠：「回體丹三十顆」要 9000，你有 5000。", "after": balance - 9000, "gives": {"pills": 30}, "card_to": None},
            {"id": "card_30", "name": "月卡", "note": "三十天內，每天能多服一顆回體丹。", "price": 600, "kind": "card",
             "kind_name": "月卡", "effects": "月卡 30 天（每天多服 1 顆回體丹）", "limit": "每個帳號限 3 次（已買 0）", "can": True,
             "why": None, "after": balance - 600, "gives": {"card_days": 30}, "card_to": "11/19"},
        ],
    }


RECORDS = {
    "balance": 4900,
    "ledger": [
        {"time": "10/20 21:40", "delta": -100, "reason": "購買", "note": "", "balance": 4900, "item": "回體丹五顆", "refunded": False},
        {"time": "10/20 08:00", "delta": 5000, "reason": "封測發放", "note": "", "balance": 5000, "item": None, "refunded": False},
    ],
    "purchases": [{"id": 1, "time": "10/20 21:40", "item": "回體丹五顆", "price": 100, "refunded": False}],
}


def _game(content, name="沈浪", mall_on=True) -> Game:
    m = content.config.mall
    m.enabled, m.beta_grant = mall_on, 5000
    content.mall = _items()  # 測試內容沒有商品（test_mall 那四件：丹兩包、月卡、一日卡）
    content.config.stamina_pills_per_day = 2
    content.config.auto_open_first_season = True
    game = Game.new(content, name, rng=random.Random(0))
    game.client = None
    game.sync(T0)
    game.mark_seen(T0)  # 封測發放
    game.state.player.stamina_pills = 28
    return game


@pytest.fixture
def m_on(content):
    return server.main_view(_game(content))


@pytest.fixture
def m_off(content):
    return server.main_view(_game(content, mall_on=False))


def _layer(m, extra: str = "", responses=None, S=None):
    """打開商城（點錠子鈕），再做 extra；回 #app 的 HTML、送出去的請求、body 上的確認框、S 的幾欄。"""
    return run(m, _async(_click('{ act: "mall-open" }') + extra + """
      return { app: T.els.app.innerHTML, calls: T.calls, asks: T.bodyHtml, open: H.S.mallOpen, main: H.S.main,
               top: H.topHtml() };"""), S=S, responses={**(responses or {}), "/api/mall": _view()})  # 假 fetch 照網址開頭認：長的排前面


# ── 伺服器給的資料 ────────────────────────────────


def test_main_view_has_the_mall_entry_only_when_the_mall_is_on(m_on, m_off):
    assert m_on["mall"] == {"balance": 5000}
    assert "mall" not in m_off  # 關著：一個鍵都不多


def test_the_mall_view_tells_pills_what_each_item_gives_and_where_the_card_would_run_to(content):
    game = _game(content)
    view = game.mall_view()
    assert view["pills"] == {"name": content.config.stamina_pill_name, "count": 28, "today": 2, "cap": 2,
                             "restore": content.config.stamina_pill_restore, "bonus": 1}
    assert view["grant"] == 5000
    rows = {row["id"]: row for row in view["items"]}
    card = next(row for row in view["items"] if row["kind"] == "card")
    assert card["gives"] == {"card_days": 30} and card["card_to"]  # 今天買的話月卡用到哪一天（含）
    pills = next(row for row in view["items"] if row["kind"] == "consumable")
    assert pills["gives"]["pills"] > 0 and pills["card_to"] is None
    assert set(rows) == set(content.mall)


def test_records_name_the_item_on_each_purchase_row(content):
    game = _game(content)
    item = next(iter(content.mall.values()))
    game.mall_buy(item.id, "web-0001")
    ledger = game.mall_records()["ledger"]
    assert (ledger[0]["reason"], ledger[0]["item"], ledger[0]["refunded"]) == ("購買", item.name, False)
    assert ledger[1]["item"] is None  # 封測發放沒有商品


def test_buying_tells_whether_it_went_through(content):
    game = _game(content)
    item = next(iter(content.mall.values()))
    game.mall_buy(item.id, "web-0002")
    assert game.mall_bought == item.id
    game.mall_buy("沒有這件", "web-0003")
    assert game.mall_bought is None


# ── 入口：乙（齒輪旁的錠子鈕）、丙（底部第六格）──


def test_off_means_no_entry_and_five_tabs(m_off):
    out = run(m_off, "return { top: H.topHtml(), tabs: H.tabsHtml() };")
    assert "mall-open" not in out["top"] and "mall-open" not in out["tabs"]
    assert "repeat(5, 1fr)" in out["tabs"] and "商城" not in out["tabs"]


def test_on_puts_an_ingot_button_beside_the_gear_and_a_sixth_tab(m_on):
    out = run(m_on, "return { top: H.topHtml(), tabs: H.tabsHtml() };")
    top = out["top"]
    btn = top[top.index('data-act="mall-open"'):]
    assert top.index('data-act="mall-open"') < top.index('data-act="sheet"')  # 齒輪的左邊
    assert 'class="ingot"' in btn[:btn.index("</button>")] and "5000" in btn[:btn.index("</button>")]
    assert 'aria-label="商城，元寶 5000"' in top
    tabs = out["tabs"]
    assert "repeat(6, 1fr)" in tabs and tabs.count('class="tab ') == 6
    sixth = tabs[tabs.rindex('<button class="tab'):]
    assert 'data-act="mall-open"' in sixth and "商城" in sixth and 'data-glow="tab:mall"' in sixth


def test_the_prologue_hides_both_entries_like_any_tab_not_open_yet(m_on):
    early = with_reveal(m_on, ["stamina", "hp", "silver", "xinde", "stats", "tab:jianghu", "tab:practice", "tab:craft", "tab:map", "tab:news"])
    out = run(early, "return { top: H.topHtml(), tabs: H.tabsHtml() };")
    assert "mall-open" not in out["top"] and "mall-open" not in out["tabs"] and "repeat(5, 1fr)" in out["tabs"]
    done = with_reveal(m_on, ["all"])
    out = run(done, "return { top: H.topHtml(), tabs: H.tabsHtml() };")
    assert "mall-open" in out["top"] and "repeat(6, 1fr)" in out["tabs"]


def test_after_graduating_both_entries_show_through_the_onboarding_steps(real):
    """FB-490：出師後就出現（docs/guide/商城.md）。出了草廬、初入江湖那四步（m.onboard，reveal 是前幾步的聯集、沒有 all）
    兩個入口都在，不等初入江湖走完；草廬裡（m.prologue）照舊藏著。照正式內容的序章與初入江湖算，教學步驟改了也照樣抓得到。"""
    game = Game.new(real, "沈浪", rng=random.Random(0))
    game.client = None
    p = game.state.player
    p.tutorial_step = real.tutorial.prologue_steps  # e1_clinic：剛走出草廬、到了潁川
    p.location = "yingchuan"
    for step in range(real.tutorial.prologue_steps, len(real.tutorial.steps)):
        p.tutorial_step = step
        m = server.main_view(game)
        assert m.get("mall") is not None and m["onboard"] and not m["prologue"]
        out = run(m, "return { top: H.topHtml(), tabs: H.tabsHtml() };")
        assert "mall-open" in out["top"], real.tutorial.steps[step].id
        assert 'data-act="mall-open" data-tab="mall"' in out["tabs"], real.tutorial.steps[step].id
    farewell = with_reveal({**m, "onboard": None}, sorted({k for s in real.tutorial.steps[:real.tutorial.prologue_steps] for k in s.reveal}))
    out = run(farewell, "return { top: H.topHtml(), tabs: H.tabsHtml() };")  # 出師那一步（還在草廬）照舊藏著
    assert "mall-open" not in out["top"] and "mall-open" not in out["tabs"]


def test_the_entry_balance_follows_main(m_on):
    m = copy.deepcopy(m_on)
    m["mall"]["balance"] = 123456
    top = run(m, "return H.topHtml();")
    assert "123456" in top and 'aria-label="商城，元寶 123456"' in top


# ── 商城那一層 ──────────────────────────────────


def test_opening_draws_the_mall_like_a_shop(m_on):
    out = _layer(m_on)
    html = out["app"]
    assert out["open"] is True and any(c[0] == "/api/mall" for c in out["calls"])
    assert 'class="shop-layer shop-mall"' in html and "萬寶閣" in html and 'data-act="mall-close"' in html
    assert "元寶 5000" in html and 'class="shop-line' in html
    assert html.count('data-act="mall-pick"') == 3
    assert "回體丹 28 顆" in html and "今天還能服 2 顆" in html and "還沒開" in html and "每天最多服 2 顆" in html
    assert 'data-act="mall-tab" data-tab="shelf"' in html and 'data-act="mall-tab" data-tab="log"' in html
    assert "貨架" in html and "紀錄" in html
    assert "儲值" not in html and "付款" not in html  # 這一版沒有金流（設計 4.6）


def test_a_blocked_item_is_dim_and_the_shopkeeper_says_why(m_on):
    out = _layer(m_on, _click('{ act: "mall-pick", id: "pills_30" }'))
    html = out["app"]
    assert "元寶不夠：「回體丹三十顆」要 9000，你有 5000。" in _text(html)  # 掌櫃那一句換成原因（照標點切成不折行的小段）
    assert not out["asks"] and not any(c[0] == "/api/mall/buy" for c in out["calls"])
    assert 'class="mall-item off"' in html or "mall-item off" in html


def test_picking_asks_with_price_balance_and_pills(m_on):
    out = _layer(m_on, _click('{ act: "mall-pick", id: "pills_5" }'))
    ask = out["asks"][-1]
    assert "買下【回體丹五顆】？" in ask and "100 元寶" in ask
    assert "5000" in ask and "4900" in ask and "28" in ask and "33 顆" in ask
    assert 'data-act="ask-yes"' in ask and "買下（100）" in ask and 'data-act="ask-no"' in ask and "再想想" in ask
    assert "每天限 5 次（今天已買 0）" in ask
    assert "儲值" not in ask and "付款" not in ask
    assert "mall-item on" in out["app"]  # 問著的那一件框起來


def test_the_card_ask_shows_the_card_and_the_daily_cap(m_on):
    out = _layer(m_on, _click('{ act: "mall-pick", id: "card_30" }'))
    ask = out["asks"][-1]
    assert "買下【月卡】？" in ask and "600 元寶" in ask and "4400" in ask
    assert "還沒開" in ask and "到 11/19" in ask
    assert "每天最多服" in ask and "3 顆" in ask


def test_buying_posts_a_ref_then_updates_the_balance_and_the_pill_button(m_on):
    after = copy.deepcopy(m_on)
    after["mall"]["balance"] = 4900
    after["status"]["pills"] = {**after["status"]["pills"], "count": 33}
    bought = {"message": "<p>買下「回體丹五顆」：回體丹 5 顆。元寶 -100（還剩 4900）。</p>", "bought": "pills_5",
              "mall": _view(balance=4900, count=33), "main": after}
    out = _layer(m_on, _click('{ act: "mall-pick", id: "pills_5" }') + _click('{ act: "ask-yes" }'),
                 responses={"/api/mall/buy": bought})
    post = [c for c in out["calls"] if c[0] == "/api/mall/buy"]
    assert len(post) == 1 and post[0][1]["item"] == "pills_5" and REF.match(post[0][1]["ref"])
    assert out["main"]["mall"]["balance"] == 4900
    assert "4900" in out["top"] and "丹33" in out["top"]  # 狀態列的錠子鈕與丹鈕當場換
    assert "元寶 4900" in out["app"] and "買下「回體丹五顆」：回體丹 5 顆。元寶 -100（還剩 4900）。" in _text(out["app"])
    assert 'class="shop-line said ok"' in out["app"]
    assert "回體丹 33 顆" in out["app"]


def test_a_buy_that_got_no_answer_reuses_its_ref_next_time(m_on):
    """逾時、沒送出去：伺服器可能其實買好了，再按一次同一件用同一個編號（伺服器回「這一筆已經買好了」、不會扣兩次）。"""
    out = run(m_on, _async(_click('{ act: "mall-open" }') + """
      const real = T.ctx.fetch;
      T.ctx.fetch = (url, opts) => url === "/api/mall/buy" ? Promise.reject(new Error("斷線")) : real(url, opts);
      """ + _click('{ act: "mall-pick", id: "pills_5" }') + _click('{ act: "ask-yes" }') + """
      const first = H.S.mallPending && H.S.mallPending.ref;
      T.ctx.fetch = real;
      """ + _click('{ act: "mall-pick", id: "pills_5" }') + _click('{ act: "ask-yes" }') + """
      return { first, calls: T.calls };"""), responses={"/api/mall/buy": {"message": "", "bought": None, "mall": _view()}, "/api/mall": _view()})
    posts = [c for c in out["calls"] if c[0] == "/api/mall/buy"]
    assert out["first"] and posts and posts[-1][1]["ref"] == out["first"]


LOST_BUY = """
      const real = T.ctx.fetch;
      T.ctx.fetch = (url, opts) => url === "/api/mall/buy" ? Promise.reject(new Error("斷線")) : real(url, opts);
      """ + _click('{ act: "mall-pick", id: "pills_5" }') + _click('{ act: "ask-yes" }') + """
      const first = H.S.mallPending && H.S.mallPending.ref;
      T.ctx.fetch = real;
      """  # 第一次送出去沒拿到回應（逾時、斷線）：伺服器可能其實買好了


def test_a_resend_that_already_went_through_is_said_as_done(m_on):
    """FB-491：同一個編號再送、伺服器回「這一筆已經買好了」（already 有值）：照成了的樣子講（綠的），不是買不了的紅字。"""
    dup = {"message": "<p>這一筆已經買好了：「回體丹五顆」。</p>", "bought": None, "already": "pills_5",
           "mall": _view(balance=4900, count=33), "main": m_on}
    out = _layer(m_on, _click('{ act: "mall-pick", id: "pills_5" }') + _click('{ act: "ask-yes" }'),
                 responses={"/api/mall/buy": dup})
    assert "這一筆已經買好了：「回體丹五顆」。" in _text(out["app"])
    assert 'class="shop-line said ok"' in out["app"] and "said no" not in out["app"]


def test_a_lost_buy_resent_says_it_is_the_same_one(m_on):
    """FB-491：沒等到回音、貨架也還沒變（不知道成了沒）：再點同一件，確認框照實講這是上一筆再送一次（同一個編號、不會扣兩次），
    不假裝是新的一筆。"""
    out = run(m_on, _async(_click('{ act: "mall-open" }') + LOST_BUY + _click('{ act: "mall-pick", id: "pills_5" }') + """
      const asked = T.bodyHtml.slice(-1)[0];
      """ + _click('{ act: "ask-yes" }') + """
      return { first, asked, calls: T.calls };"""),
        responses={"/api/mall/buy": {"message": "", "bought": None, "already": None, "mall": _view()}, "/api/mall": _view()})
    posts = [c for c in out["calls"] if c[0] == "/api/mall/buy"]
    assert out["first"] and posts[-1][1]["ref"] == out["first"]
    asked = _text(out["asked"])
    assert "上一筆「回體丹五顆」還沒等到回音" in asked and "不會扣兩次" in asked and "再送一次（100）" in asked
    assert "買下（100）" not in asked


def test_a_lost_buy_that_shows_up_on_the_shelf_lets_the_next_one_be_new(m_on):
    """FB-491：沒等到回音，可是之後重抓到的貨架變了（元寶少了、丹多了：那一筆其實成了）：再點一件是新的一筆、用新的編號，
    確認框照新的貨架算（4900 → 4800），不寫「再送一次」。"""
    richer = copy.deepcopy(m_on)
    richer["mall"]["balance"] = 4900
    out = run(m_on, _async(_click('{ act: "mall-open" }') + LOST_BUY + """
      const later = T.ctx.fetch;
      T.ctx.fetch = (url, opts) => url === "/api/mall" ? (T.calls.push([url, null]), Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(H.S.landed) })) : later(url, opts);
      const was = H.S.main; H.setMain(H.S.next); await H.refreshPage(was);
      const pending = H.S.mallPending;
      """ + _click('{ act: "mall-pick", id: "pills_5" }') + """
      const asked = T.bodyHtml.slice(-1)[0];
      """ + _click('{ act: "ask-yes" }') + """
      return { first, pending, asked, calls: T.calls };"""), S={"next": richer, "landed": _view(balance=4900, count=33)},
        responses={"/api/mall/buy": {"message": "", "bought": None, "already": None, "mall": _view(balance=4800, count=38)},
                   "/api/mall": _view()})
    assert out["first"] and out["pending"] is None
    posts = [c for c in out["calls"] if c[0] == "/api/mall/buy"]
    assert posts[-1][1]["ref"] != out["first"] and REF.match(posts[-1][1]["ref"])
    asked = _text(out["asked"])
    assert "還沒等到回音" not in asked and "買下（100）" in asked and "4900 →" in asked and "4800" in asked


def test_a_refused_buy_lets_the_shopkeeper_say_it(m_on):
    refused = {"message": "<p>沒有這件商品。</p>", "bought": None, "mall": _view(), "main": m_on}
    out = _layer(m_on, _click('{ act: "mall-pick", id: "pills_5" }') + _click('{ act: "ask-yes" }'),
                 responses={"/api/mall/buy": refused})
    assert "沒有這件商品。" in _text(out["app"]) and "元寶 5000" in out["app"] and 'class="shop-line said no"' in out["app"]


def test_the_log_tab_lists_the_ledger(m_on):
    out = _layer(m_on, _click('{ act: "mall-tab", tab: "log" }'), responses={"/api/mall/records": RECORDS})
    html = out["app"]
    assert any(c[0] == "/api/mall/records" for c in out["calls"])
    assert "元寶餘額" in html and "回體丹五顆" in html and "封測發放" in html
    assert "−100" in html and "+5000" in html and "餘 4900" in html and "10/20 21:40" in html
    assert 'class="shop-tab on" data-act="mall-tab" data-tab="log"' in html


def test_closing_takes_the_layer_away(m_on):
    out = _layer(m_on, _click('{ act: "mall-close" }'))
    assert out["open"] is False and "shop-mall" not in out["app"]


def test_the_sixth_tab_opens_the_mall_too(m_on):
    out = run(m_on, _async(_click('{ act: "mall-open", tab: "mall" }') + "return { app: T.els.app.innerHTML, tab: H.S.tab };"),
              responses={"/api/mall": _view()})
    assert "shop-mall" in out["app"] and out["tab"] == "jianghu"  # 不換頁：出店回到原本那一頁


def test_a_poll_while_the_mall_is_open_reloads_it_only_when_the_balance_moved(m_on):
    richer = copy.deepcopy(m_on)
    richer["mall"]["balance"] = 5300
    out = run(m_on, _async(_click('{ act: "mall-open" }') + """
      const n = () => T.calls.filter((c) => c[0] === "/api/mall").length;
      const before = n();
      const was = H.S.main; H.setMain(H.S.same); await H.refreshPage(was);
      const same = n();
      const was2 = H.S.main; H.setMain(H.S.next); await H.refreshPage(was2);
      return { before, same, after: n() };"""), S={"same": m_on, "next": richer}, responses={"/api/mall": _view()})
    assert out["same"] == out["before"] and out["after"] == out["before"] + 1


# ── 設定頁的管理者區 ─────────────────────────────


def _sheet(m, S=None):
    return run(m, "return H.sheetHtml();", S={"admin": None, **(S or {})})


def test_admin_mall_tools_show_only_for_an_admin_with_the_mall_on(m_on, m_off):
    admin = {**m_on, "admin": True}
    html = _sheet(admin)
    assert 'id="ad-mall-form"' in html and 'data-op="mall_reissue"' in html and 'data-op="mall_revoke"' in html
    assert 'id="ad-mall-amount"' in html and 'id="ad-mall-note"' in html
    assert 'id="ad-mall-form"' not in _sheet(m_on)  # 不是管理者
    assert 'id="ad-mall-form"' not in _sheet({**m_off, "admin": True})  # 商城關著


def test_admin_ledger_lists_purchases_with_a_refund_button(m_on):
    ledger = {"name": "沈浪", "balance": 4800, "card": {"until": "11/19", "bonus": 1},
              "ledger": [{**RECORDS["ledger"][0], "ref": "buy:沈浪:x", "admin": None, "purchase": 1},
                         {"time": "10/20 09:00", "delta": 100, "reason": "補發", "note": "維修補償", "balance": 5000, "item": None,
                          "refunded": False, "ref": "admin:y", "admin": "管理者", "purchase": None}],
              "purchases": [{"id": 2, "time": "10/20 22:00", "item": "月卡", "price": 600, "refunded": True},
                            {"id": 1, "time": "10/20 21:40", "item": "回體丹五顆", "price": 100, "refunded": False}]}
    html = _sheet({**m_on, "admin": True}, S={"adMall": ledger, "adMallName": "沈浪"})
    assert "4800" in html and "11/19" in html and "維修補償" in html and "管理者" in html
    assert html.count('data-op="mall_refund"') == 1 and 'data-id="1"' in html and "已退" in html


def test_admin_reissue_asks_first_then_posts_with_a_ref_and_keeps_the_sheet(m_on):
    admin = {**m_on, "admin": True}
    out = run(admin, _async("""
      const fields = { "ad-mall-name": { value: "沈浪" }, "ad-mall-amount": { value: "300" }, "ad-mall-note": { value: "維修補償" } };
      const orig = T.ctx.document.getElementById;
      T.ctx.document.getElementById = (id) => fields[id] || orig(id);
      T.qs['.ask [data-act="ask-no"]'] = { focus() {} };
      """ + _click('{ act: "mall-admin", op: "mall_reissue" }') + """
      const asked = T.bodyHtml.slice(-1)[0];
      """ + _click('{ act: "ask-yes" }') + """
      return { asked, calls: T.calls, sheet: H.S.sheet, msg: H.S.adMallMsg };"""),
        S={"sheet": True, "admin": None},
        responses={"/api/do/mall_reissue": {"main": admin, "message": "<p>已替沈浪補發 300 元寶（餘額 5300）。</p>"},
                   "/api/admin/mall": {"name": "沈浪", "balance": 5300, "card": None, "ledger": [], "purchases": []}})
    assert "沈浪" in out["asked"] and "300" in out["asked"] and "維修補償" in out["asked"]
    post = next(c for c in out["calls"] if c[0] == "/api/do/mall_reissue")
    assert post[1]["name"] == "沈浪" and post[1]["amount"] == 300 and post[1]["note"] == "維修補償" and REF.match(post[1]["ref"])
    assert any(c[0] == "/api/admin/mall" for c in out["calls"])  # 補完重查一次帳
    assert out["sheet"] is True and "已替沈浪補發 300 元寶" in out["msg"]


def _admin_result(m_on, op, message):
    """管理者補發或扣回（先問、確定），回之後重畫的設定抽屜（結果寫在查帳那一行）。"""
    admin = {**m_on, "admin": True}
    return run(admin, _async("""
      const fields = { "ad-mall-name": { value: "沈浪" }, "ad-mall-amount": { value: "300" }, "ad-mall-note": { value: "維修補償" } };
      const orig = T.ctx.document.getElementById;
      T.ctx.document.getElementById = (id) => fields[id] || orig(id);
      T.qs['.ask [data-act="ask-no"]'] = { focus() {} };
      """ + _click('{ act: "mall-admin", op: "' + op + '" }') + _click('{ act: "ask-yes" }') + """
      return H.sheetHtml();"""),
        S={"sheet": True, "admin": None},
        responses={f"/api/do/{op}": {"main": admin, "message": message},
                   "/api/admin/mall": {"name": "沈浪", "balance": 400, "card": None, "ledger": [], "purchases": []}})


def test_admin_result_that_went_through_is_not_red(m_on):
    """FB-492：補發、扣回、退一筆做成了，查帳那一行帶 ok（不是被拒的紅字）；被拒的那一句（包在全形括號裡）照舊紅字。"""
    done = _admin_result(m_on, "mall_reissue", "<p>已替沈浪補發 300 元寶（餘額 400）。</p>")
    assert '<p class="form-msg ok" role="alert">已替沈浪補發 300 元寶（餘額 400）。</p>' in done
    refused = _admin_result(m_on, "mall_revoke", "<p>（沈浪只有 100 元寶，扣不了 300：餘額不能是負的。）</p>")
    assert '<p class="form-msg" role="alert">（沈浪只有 100 元寶，扣不了 300：餘額不能是負的。）</p>' in refused


def test_admin_refund_asks_then_posts_the_purchase_of_the_looked_up_player(m_on):
    admin = {**m_on, "admin": True}
    book = {"name": "沈浪", "balance": 4900, "card": None, "ledger": [], "purchases": [
        {"id": 7, "time": "10/20 21:40", "item": "回體丹五顆", "price": 100, "refunded": False}]}
    out = run(admin, _async("""
      const fields = { "ad-mall-note": { value: "買錯了" } };
      const orig = T.ctx.document.getElementById;
      T.ctx.document.getElementById = (id) => fields[id] || orig(id);
      T.qs['.ask [data-act="ask-no"]'] = { focus() {} };
      """ + _click('{ act: "mall-admin", op: "mall_refund", id: "7" }') + """
      const asked = T.bodyHtml.slice(-1)[0];
      """ + _click('{ act: "ask-yes" }') + """
      return { asked, calls: T.calls };"""),
        S={"sheet": True, "admin": None, "adMall": book, "adMallName": "沈浪"},
        responses={"/api/do/mall_refund": {"main": admin, "message": "<p>已退沈浪的「回體丹五顆」：元寶 +100（餘額 5000）。</p>"},
                   "/api/admin/mall": {**book, "balance": 5000}})
    assert "回體丹五顆" in out["asked"] and "#7" in out["asked"] and "+100" in out["asked"] and "買錯了" in out["asked"]
    post = next(c for c in out["calls"] if c[0] == "/api/do/mall_refund")
    assert post[1] == {"name": "沈浪", "id": 7, "note": "買錯了"}


def test_admin_needs_a_reason_before_asking(m_on):
    admin = {**m_on, "admin": True}
    out = run(admin, _async("""
      const fields = { "ad-mall-name": { value: "沈浪" }, "ad-mall-amount": { value: "300" }, "ad-mall-note": { value: "  " } };
      const orig = T.ctx.document.getElementById;
      T.ctx.document.getElementById = (id) => fields[id] || orig(id);
      """ + _click('{ act: "mall-admin", op: "mall_revoke" }') + """
      return { asks: T.bodyHtml, calls: T.calls, msg: H.S.adMallMsg };"""), S={"sheet": True, "admin": None})
    assert not any("ask-yes" in h for h in out["asks"]) and not any(c[0].startswith("/api/do/") for c in out["calls"])
    assert out["msg"]  # 表單那一行寫要填原因


# ── 樣式 ──────────────────────────────────────


def test_the_mall_layer_follows_the_640_column_on_desktop():
    from pathlib import Path

    css = (Path(__file__).resolve().parent.parent / "web" / "style.css").read_text(encoding="utf-8")
    wide = css[css.index("/* ── 電腦上的店面與武學譜那本書（FB-225"):]
    head = wide[wide.index("@media (min-width: 641px) {"):]
    assert ".shop-layer.shop-mall" in head[:head.index("{", head.index(".shop-layer.shop-smith"))]
    assert ".mall-btn" in css and ".shop-layer.shop-mall" in css
