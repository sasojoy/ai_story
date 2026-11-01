"""序章的網頁（新手引導計畫一 Task 6）：畫面一步一步亮起來、要按的鈕發光、對話框、略過與重看序章。
web/app.js 沒有建置步驟、也沒有前端測試框架：這裡把整支 app.js 放進 node 的假瀏覽器（只有 document、localStorage、fetch 的假貨），
最後一行啟動的呼叫換成「把要測的函式交出來」，餵它**真的**引擎給的 /api/main 與 /api/menxia 內容（序章測試內容，走到每一步），
檢查畫出來的 HTML 與發光的鈕。沒有 node 就略過。沒有瀏覽器可開，這是瀏覽器驗收那一步（手機寬度 375 的排版另看）的替身：
驗的是「哪一步畫什麼、藏什麼、哪顆鈕發光」，不是長相。"""
from __future__ import annotations

import json
import random
import re
from pathlib import Path

import pytest
from test_prologue import _to_step

import server
import webharness
from tianxia import prologue
from tianxia.engine import Game
from tianxia.models import GiveArt
from conftest import idle_step
from test_orders import _game, _order
from tianxia import guide
from tianxia.rules import front_of

ROOT = Path(__file__).parents[2]
pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")

DRIVER = r"""
const vm = require("vm");
// 整支 app.js（webharness 的 wholeApp）：最後一行啟動的呼叫前面把要測的名字交給 globalThis.__H
const app = wholeApp(["S", "pro", "shown", "prologueKey", "topHtml", "tabsHtml", "idleMenu", "actionBar", "guideHtml", "nextGuidePage",
  "guideCue", "scrollToGuideTarget", "setMain", "pageJianghu", "pagePractice", "pageCraft", "weekCardHtml", "chapterCardHtml", "trendsTopHtml", "sheetHtml", "applyGlow",
  "renderTop", "render", "goTab", "renderPage", "refreshPage", "enter", "sayLine", "pick", "forge", "updateForgeLine",
  "toggleLock", "trimForgeSel", "bookHtml", "peerHtml"]);

// fetch 的假貨：記下問了什麼；網址開頭對得上 input.responses 的鍵就回那一份（回的是 JSON），其他回空物件
const calls = [];
const fetchStub = (url, opts) => {
  if (url === "/api/me") return new Promise(() => {}); // app.js 最後的啟動呼叫：不回，免得它半途把畫面換成登入頁
  calls.push([url, opts && opts.body ? JSON.parse(opts.body) : null]);
  const key = Object.keys(input.responses || {}).find((k) => url.startsWith(k));
  const data = key ? input.responses[key] : {};
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(data) });
};

const store = new Map();
const els = {};
const mk = (id) => (els[id] = els[id] || {
  id, innerHTML: "", hidden: false, dataset: {}, classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
  querySelector: () => null, querySelectorAll: () => [], setAttribute() {}, append() {}, insertAdjacentHTML() {},
});
["app", "toast", "page", "top", "peek"].forEach(mk); // render() 只寫 #app 的 innerHTML；#top 要讀得到 hidden
// applyGlow 用的假元素：{ glow: ["鍵", ...], disabled, id, classes: Set }。只認 applyGlow（與 applyFocus）會問的幾種選擇器
const fake = { list: [] };
// closedFold：這顆鈕收在關著的摺疊裡時的假摺疊 { querySelector: () => 標題列的假元素 }；applyGlow 問 closest("details:not([open])") 才給（FB-087 審查 M3）
// id：選單鈕的 data-id（入伍段「出一次力」那一步，伺服器在框上帶的 guide.glow 是選項 id，applyGlow 照 #page [data-id="…"] 找，FB-093）
const el = (glow, disabled = false, closedFold = null, id = null) => {
  const e = { glow, disabled, id, classes: new Set() };
  e.closest = (sel) => (sel === "details:not([open])" ? closedFold : null);
  e.classList = { add: (...c) => c.forEach((x) => e.classes.add(x)), remove: (...c) => c.forEach((x) => e.classes.delete(x)), contains: (c) => e.classes.has(c) };
  fake.list.push(e);
  return e;
};
const button = (id, disabled = false) => el([], disabled, null, id); // 一顆選單鈕（沒有 data-glow，只有 data-id）
const matchOne = (e, sel) => {
  if (sel === ".glow") return e.classes.has("glow");
  if (sel === ".lit") return e.classes.has("lit");
  if (sel === ".onb-dim") return e.classes.has("onb-dim"); // applyFocus 先收掉上一次壓暗的（假元素不在 #top、#page 底下，不會被壓暗）
  const byId = sel.match(/^#page (?:\.act-move )?\[data-id="(.*)"\](:not\(\[disabled\]\))?$/); // .act-move：展開的移動卡裡的那條路（FB-9001 的 routeGlowKey）
  if (byId) return e.id === byId[1] && !(byId[2] && e.disabled);
  const m = sel.match(/^\[data-glow~="(.*)"\](:not\(\[disabled\]\))?$/);
  if (!m) throw new Error("假 DOM 不認得的選擇器：" + sel);
  return e.glow.includes(m[1]) && !(m[2] && e.disabled);
};
const qs = {}; // 測試可以放假元素：document.querySelector(選擇器) 回 qs[選擇器]
const listeners = {}; // window.addEventListener 登記的處理函式（照事件名）：測試可以觸發 resize
const docListeners = {}; // document.addEventListener 登記的處理函式（照事件名）：測試可以送一次 click（見 tests/test_hints_web.py）
const bodyHtml = []; // document.body.insertAdjacentHTML 收到的東西（ask() 的確認框、見 tests/test_prologue_web.py）
const document = {
  body: { insertAdjacentHTML: (pos, html) => { bodyHtml.push(html); } },
  getElementById: (id) => (["app", "toast", "page", "top", "peek"].includes(id) ? mk(id) : null),
  querySelector: (sel) => qs[sel] || null,
  querySelectorAll: (sel) => fake.list.filter((e) => sel.split(", ").some((one) => matchOne(e, one))),
  addEventListener(type, fn) { (docListeners[type] = docListeners[type] || []).push(fn); }, activeElement: null, hidden: false,
  // splitChips 把「剛剛」丟進 <template> 拆出數值變化那一排：假的 template 原樣吐回去、沒有那一排
  createElement: () => ({ innerHTML: "", content: { querySelector: () => null } }),
};
const ctx = {
  document, window: { addEventListener(type, fn) { (listeners[type] = listeners[type] || []).push(fn); }, scrollTo() {}, innerWidth: 375, innerHeight: 812 }, fetch: fetchStub,
  localStorage: { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => { store.set(k, String(v)); }, removeItem: (k) => { store.delete(k); } },
  setInterval() {}, setTimeout, clearTimeout, performance, console, confirm: () => true, navigator: {}, CSS: { escape: (x) => x },
  requestAnimationFrame: () => 0, Element: class {},
};
for (const [k, v] of Object.entries(input.stored || {})) store.set(k, v);
vm.createContext(ctx);
vm.runInContext(app, ctx);
const H = ctx.__H;
H.S.stage = "game";
H.S.main = input.m;
H.S.menxia = input.menxia || null;
Object.assign(H.S, input.S || {});
// script 可以是 async（回傳 Promise）：等它做完再印
// ctx 與 Element：測試可以換掉 fetch／setTimeout（讓請求被擋下來），也可以做出 instanceof Element 的假事件目標（toggle 事件，見 tests/test_jianghu_page_web.py）
finish(new Function("H", "m", "T", input.script)(H, input.m, { els, fake, el, button, calls, qs, listeners, docListeners, bodyHtml, ctx, Element: ctx.Element }));
"""


def run(m, script, *, S=None, menxia=None, stored=None, responses=None):
    """在 node 裡跑 app.js（tests/webharness.py）：m 是 /api/main 回的那份（S.main）、menxia 是 /api/menxia 回的那份，script 是函式本體
    （可用 H、m、T；要等網路的寫成 async，fetch 是假的：T.calls 記下問了什麼，responses 是「網址開頭 → 回的 JSON」）。"""
    return webharness.run(DRIVER, {
        "m": m, "script": script, "S": S or {}, "menxia": menxia, "stored": stored or {}, "responses": responses or {},
    })


@pytest.fixture
def hut(prologue_content, world):
    return Game.new(prologue_content, "沈浪", rng=random.Random(0), world=world, prologue=True)


@pytest.fixture
def newcomer(prologue_content, world):
    """一個新人一個新人地開：同一個 Game 走過第 10 步就回不到第 5 步。"""
    return lambda: Game.new(prologue_content, "沈浪", rng=random.Random(0), world=world, prologue=True)


def main_at(game, step, **over):
    """序章走到第 step 步（0 起算）時，伺服器給網頁的 /api/main；over 蓋掉幾個欄位。"""
    _to_step(game, step)
    m = server.main_view(game)
    m.update(over)
    return m


def with_reveal(m, reveal, glow=(), skip=False):
    return {**m, "prologue": {"reveal": list(reveal), "glow": list(glow), "skip": skip}}


def has_week(html):
    return 'id="week"' in html or 'class="card wk-card' in html  # 灰線一直在（沒收起）；「眼下要事」沒有要做的事不畫


STANCES = {"guan": 40, "huang": 30, "haoqiang": 20}
BULLETIN = ["<p><strong>甲事</strong></p>"]
FRONTS = [{"name": "潁川", "value": 40, "chaos": False}]
WEEK = {"label": "本週", "when": "第 1 週", "theme": "THEME", "sides": {"guan": 40, "huang": 30}, "steps": [], "next": None}
ORDERS = [{"title": "守關", "text": "守住", "progress": 1, "quota": 5, "done": False, "mine": 0, "deadline": "週五"}]


def season_one_view(m):
    """序章裡通常沒有的東西全放進去，才看得出是哪一步把它們藏起來、哪一步放出來。"""
    status = {**m["status"], "stances": STANCES, "stance_notes": {}, "stance_rule": "規則"}
    return {**m, "status": status, "bulletin": BULLETIN, "quest": "<p>QUESTMARK</p>", "fronts": FRONTS, "orders": ORDERS,
            "minimap": "<svg>MINIMAP</svg>", "week_card": m.get("week_card") or WEEK}


# ── 第一屏與每一步亮什麼 ────────────────────────────────

def test_the_first_screen_is_the_ambush_and_a_skip_link(hut):
    m = main_at(hut, 0)
    assert m["prologue"] == {"reveal": [], "glow": [], "skip": True}
    out = run(m, "return { page: H.pageJianghu(), top: H.topHtml(), tabs: H.tabsHtml() };")
    page = out["page"]
    assert page.count('data-act="choose"') == 2  # 遇險那一則的兩個選項
    assert '<button class="linkish skip-prologue" data-act="do" data-op="skip_tutorial">略過序章</button>' in page
    assert page.index("data-act=\"choose\"") < page.index("skip-prologue")  # 略過在選項底下
    assert "act-bar" not in page and 'class="peek"' not in page and "class=\"mini\"" not in page
    assert out["top"] == "" and out["tabs"] == ""  # 沒有狀態列、沒有分頁列


@pytest.mark.smoke
def test_the_whole_screen_has_no_top_and_no_tabs_on_the_first_step(hut):
    app = run(main_at(hut, 0), "H.render(); return T.els.app.innerHTML;")
    assert '<header class="top" id="top" hidden></header>' in app and "<nav" not in app


def test_after_meeting_the_master_only_the_name_and_xinde_and_two_tabs_show(hut):
    m = main_at(hut, 1)
    out = run(m, "return { top: H.topHtml(), tabs: H.tabsHtml(), page: H.pageJianghu() };")
    top = out["top"]
    assert "心得" in top and 'class="bar stam"' not in top and 'class="bar hp"' not in top and "<em>銀</em>" not in top
    assert 'data-act="toggle-more"' not in top and 'class="who static"' in top  # 屬性還沒亮：名號不是按鈕
    assert "第 " not in top and "下一件" not in top  # 序章裡所在只寫地名：沒有日期
    tabs = out["tabs"]
    assert re.findall(r'data-tab="(\w+)"', tabs) == ["jianghu", "practice"]
    assert "repeat(2, 1fr)" in tabs and re.search(r'data-glow="[^"]*\btab:practice\b', tabs)
    assert "skip-prologue" not in out["page"]  # 略過只在第一步
    assert "師父" in out["page"] and "去看修練頁" in out["page"]  # 對話框


def test_each_step_lights_up_the_next_thing(hut):
    """走完整個序章：每一步畫出來的分頁、行動格、狀態列數字跟伺服器說的 reveal 對得上，只多不少。"""
    seen = []
    for step in range(11):
        m = main_at(hut, step)
        out = run(m, "return { tabs: H.tabsHtml(), top: H.topHtml(), page: H.pageJianghu() };")
        seen.append({
            "tabs": re.findall(r'data-tab="(\w+)"', out["tabs"]),
            "cells": re.findall(r'class="act-ink[^"]*" data-key="(\w+)"', out["page"]),
            "vitals": [k for k, mark in (("stamina", 'class="bar stam"'), ("hp", 'class="bar hp"'), ("silver", "<em>銀</em>"), ("xinde", "<em>心得</em>"))
                       if mark in out["top"]],
            "toggle": 'data-act="toggle-more"' in out["top"],
        })
    # 煉製頁（減法季批 1 起在「自己」那一格底下，沒有自己的籤）到揣摩那一步（第 6 步）才亮：「自己」那一格多發 tab:craft 的光
    jp = ["jianghu", "practice"]
    assert [s["tabs"] for s in seen[:6]] == [[], jp, jp, jp, jp, jp]
    assert seen[1]["vitals"] == ["xinde"] and seen[2]["vitals"] == ["stamina", "xinde"]
    assert seen[2]["cells"] == ["explore"] and seen[6]["cells"] == ["explore", "rest"]
    assert seen[7]["cells"] == ["explore", "train"] and seen[7]["vitals"] == ["stamina", "hp", "xinde"]
    assert [s["toggle"] for s in seen] == [False] * 8 + [True] * 3  # 屬性（配點）從第 9 步才點得開
    for before, after in zip(seen, seen[1:]):  # 亮起來的不會再暗回去（調息那一格例外：只有第 7 步有，打坐 2026-10-12 拿掉了）
        assert set(before["tabs"]) <= set(after["tabs"]) and set(before["cells"]) - {"rest"} <= set(after["cells"])


def test_the_farewell_step_lights_everything_and_the_menu_is_only_the_walk(hut):
    m = main_at(hut, 10)
    out = run(m, "return { tabs: H.tabsHtml(), page: H.pageJianghu(), top: H.topHtml() };")
    assert re.findall(r'data-tab="(\w+)"', out["tabs"]) == ["jianghu", "practice", "map", "news"]
    cells = {key: cls for cls, key in re.findall(r'class="act-ink([^"]*)" data-key="(\w+)"', out["page"])}
    assert sorted(cells) == ["explore", "move", "social", "train"]  # 打坐 2026-10-12 拿掉了：出師之後是四格
    assert " off" in cells["explore"] and " off" not in cells["move"]  # 只有走出草廬按得下去
    assert 'data-glow="act:move"' in out["page"] and "<em>銀</em>" in out["top"]


def test_after_the_prologue_the_ordinary_screen_comes_back(hut, content):
    plain = Game.new(content, "路人", rng=random.Random(0))
    m = server.main_view(plain)
    assert m["prologue"] is None
    out = run(m, "return { tabs: H.tabsHtml(), top: H.topHtml(), shown: H.shown('tab:map') && H.shown('board') && H.shown('act:move') };")
    assert re.findall(r'data-tab="(\w+)"', out["tabs"]) == ["jianghu", "practice", "map", "news"] and out["shown"] is True
    assert "第 " in out["top"] and "toggle-more" in out["top"]  # 平常的狀態列：日期、點名號展開


# ── 本週卡（減法季批 1：取代態勢｜大事｜主線三塊小標） ────────────────────

@pytest.mark.parametrize("reveal, expected", [
    ([], False), (["xinde", "tab:practice", "board", "stances"], False), (["quest"], True), (["all"], True),
])
def test_the_week_card_shows_only_once_the_quest_is_revealed(hut, reveal, expected):
    m = with_reveal(season_one_view(main_at(hut, 1)), reveal)
    assert has_week(run(m, "return H.weekCardHtml(m);")) is expected
    assert has_week(run(m, "return H.pageJianghu();")) is expected


def test_the_week_card_comes_back_at_the_farewell_step(newcomer):
    assert has_week(run(season_one_view(main_at(newcomer(), 10)), "return H.weekCardHtml(m);"))
    assert not has_week(run(season_one_view(main_at(newcomer(), 5)), "return H.weekCardHtml(m);"))  # 序章中途（揣摩那一步）：還藏著


def test_the_week_card_is_there_outside_the_prologue(content):
    plain = server.main_view(Game.new(content, "路人", rng=random.Random(0)))
    assert plain["week_card"] and has_week(run(plain, "return H.weekCardHtml(m);"))


# ── 江湖頁其他的塊 ───────────────────────────────────

def test_fronts_and_orders_wait_for_their_keys(hut):
    """軍令卡在江湖頁；三條戰況搬到見聞・大事・大勢的最上面（減法季批 1，trendsTopHtml）；小地圖不在江湖頁畫了。"""
    m = season_one_view(main_at(hut, 3))
    assert "orders" not in run(m, "return H.pageJianghu();") and 'class="fronts"' not in run(m, "return H.trendsTopHtml(m);")
    assert "本週軍令" in run(with_reveal(m, [*m["prologue"]["reveal"], "orders"]), "return H.pageJianghu();")
    assert 'class="fronts"' in run(with_reveal(m, [*m["prologue"]["reveal"], "fronts"]), "return H.trendsTopHtml(m);")
    lit = run(with_reveal(m, ["all"]), "return H.pageJianghu();")
    assert "本週軍令" in lit and 'class="fronts"' not in lit and "MINIMAP" not in lit


def test_a_cell_that_is_not_lit_keeps_its_option_out_of_the_fold(hut):
    """行動列沒亮的格子，對到的選項照樣算用過：不會掉進「此地還能做」摺疊裡露出來。"""
    m = main_at(hut, 2)
    m["options"] = [{"id": "act:explore", "label": "探索（體力 10）", "enabled": True},
                    {"id": "act:train", "label": "遊歷（體力 10）", "enabled": True},
                    {"id": "move:town", "label": "前往 小鎮（步行）", "enabled": True}]
    page = run(m, "return H.pageJianghu();")
    assert 'data-key="explore"' in page and 'data-key="train"' not in page and 'data-key="move"' not in page
    assert "此地還能做" not in page and "遊歷" not in page and "前往 小鎮" not in page


def test_no_cell_lit_and_nothing_extra_draws_no_bar(hut):
    page = run(main_at(hut, 1), "return H.pageJianghu();")
    assert "act-bar" not in page and "此地還能做" not in page


@pytest.mark.parametrize("prologue, options, on_road, expected", [
    (True, [], False, True),  # 序章裡沒有選項（看修練頁那一步）：照閒著的行動列畫
    (True, ["act:explore"], False, True),  # 沒有打坐，也是閒著
    (True, ["choice:0", "choice:1"], False, False),  # 事件的選項：一排按鈕
    (True, ["sense:0", "sense:1"], False, False),  # 草廬四景的做法：一排按鈕（悟意境）
    (True, ["sense:draw", "sense:let"], False, False),  # 感悟狀態：畫下來、順其自然
    (True, ["act:on_road", "road:back"], True, False),  # 出師那段路上：路上的選單
    (False, ["talk:0", "talk:leave"], False, False),  # 序章外沒有探索的選單不是閒著（對話、事件、決戰）
    (False, ["act:explore"], False, True),  # 有探索就是閒著（以前認打坐，2026-10-12 拿掉了）
])
def test_the_idle_bar_is_drawn_for_the_prologue_menus_too(hut, prologue, options, on_road, expected):
    m = main_at(hut, 2)
    m["options"] = [{"id": i, "label": i, "enabled": True} for i in options]
    m["on_road"] = on_road
    m["prologue"] = m["prologue"] if prologue else None
    assert run(m, "return H.idleMenu(m);") is expected


@pytest.mark.parametrize("option, label, enabled", [
    ("season:preparing", "賽季籌備中，等待管理者開季", False),
    ("season:resting", "休季中，等待管理者開啟下一季", False),
    ("season:paused", "賽季暫停中", False),
    ("act:break", "提前出關", True),
])
def test_a_notice_in_the_hut_is_a_visible_button_not_a_fold(hut, option, label, enabled):
    """籌備中、休季、暫停、閉關中：草廬裡的新人選單上只有這一顆。它不是行動列的格子，不能掉進「此地還能做」的摺疊裡
    （沒有選項、也看不到原因），要跟序章外一樣畫成一顆看得見的按鈕。"""
    m = main_at(hut, 2)
    m["options"] = [{"id": option, "label": label, "enabled": enabled}]
    out = run(m, "return { idle: H.idleMenu(m), page: H.pageJianghu() };")
    assert out["idle"] is False
    assert label in out["page"] and "此地還能做" not in out["page"] and "act-bar" not in out["page"]
    assert ("disabled" in out["page"]) is (not enabled)


# ── 發光與閃一閃 ────────────────────────────────────

def test_the_glowing_buttons_are_the_ones_the_step_names(hut):
    m = main_at(hut, 2)  # 探索那一步：glow ["tab:jianghu", "act:explore"]（剛看完修練頁，江湖分頁也發光）
    assert m["prologue"]["glow"] == ["tab:jianghu", "act:explore"]
    out = run(m, """
      const explore = T.el(["act:explore"]), other = T.el(["act:rest"]), off = T.el(["act:explore"], true), both = T.el(["switch", "melt"]);
      H.applyGlow();
      return [explore, other, off, both].map((e) => [...e.classes]);""")
    assert out == [["glow"], [], [], []]  # 灰的、沒被點名的都不發光


def test_a_key_in_a_list_of_keys_glows_too(hut):
    m = with_reveal(main_at(hut, 4), ["all"], glow=["melt"])
    out = run(m, "const row = T.el(['switch', 'melt']); H.applyGlow(); return [...row.classes];")
    assert out == ["glow"]


def test_newly_revealed_things_flash_once_and_the_glow_follows_the_step(hut):
    before = with_reveal(main_at(hut, 1), ["xinde", "tab:practice"], glow=["tab:practice"])
    after = with_reveal(before, ["xinde", "tab:practice", "stamina"], glow=["stamina"])
    out = run(before, """
      const stam = T.el(["stamina"]), tab = T.el(["tab:practice"]);
      H.applyGlow();                       // 第一次畫：什麼都不閃（只是進來）
      const first = [[...stam.classes], [...tab.classes]];
      H.S.main = %s;
      H.applyGlow();                       // 多亮了體力：體力閃、發光換到體力
      return [first, [[...stam.classes].sort(), [...tab.classes]]];""" % json.dumps(after))
    assert out == [[[], ["glow"]], [["glow", "lit"], []]]


def test_nothing_glows_outside_the_prologue(content):
    plain = server.main_view(Game.new(content, "路人", rng=random.Random(0)))
    out = run(plain, "const e = T.el(['act:explore']); e.classes.add('glow'); H.applyGlow(); return [...e.classes];")
    assert out == []  # 殘留的也清掉


def test_every_button_the_prologue_points_at_carries_its_key(hut):
    """序章指的鈕：每一步 glow 寫的鍵，都要在那一步畫出來的某個元素上找得到 data-glow（不然那一步沒有東西發光）。"""
    for step in (1, 2, 8):
        m = main_at(hut, step)
        pages = run(m, "return H.tabsHtml() + H.topHtml() + H.pageJianghu();", S={"showMore": True})
        for key in m["prologue"]["glow"]:
            assert re.search(rf'data-glow="[^"]*\b{re.escape(key)}\b', pages), (step, key)


# ── 狀態列 ──────────────────────────────────────────

@pytest.mark.parametrize("reveal, bars", [
    (["xinde"], ["xinde"]), (["stamina"], ["stamina"]), (["hp"], ["hp"]), (["silver"], ["silver"]),
    (["stamina", "hp", "silver", "xinde"], ["stamina", "hp", "silver"]),  # 心得在銀兩亮了以後搬到「自己」頁（減法季批 1：狀態列三行）
])
def test_each_number_on_the_status_bar_has_its_own_key(hut, reveal, bars):
    html = run(with_reveal(main_at(hut, 1), reveal), "return H.topHtml();")
    drawn = [k for k, mark in (("stamina", 'class="bar stam"'), ("hp", 'class="bar hp"'), ("silver", "<em>銀</em>"), ("xinde", "<em>心得</em>")) if mark in html]
    assert drawn == bars and 'data-act="toggle-more"' not in html


def test_the_name_opens_the_attributes_only_when_stats_is_lit(hut):
    m = main_at(hut, 8)  # 配點那一步：升了一級，有一點可以配
    assert "stats" in m["prologue"]["reveal"] and m["status"]["stat_points"] == 1
    on = run(m, "return H.topHtml();", S={"showMore": True})
    assert 'data-act="toggle-more"' in on and 'data-glow="stats"' in on
    assert re.search(r'data-act="allocate" data-stat="\w+" data-glow="allocate"', on)
    off = run(with_reveal(m, ["xinde"]), "return H.topHtml();", S={"showMore": True})
    assert "more-stats" not in off and "allocate" not in off  # 展開著也不展開：屬性沒亮


def test_nothing_on_the_status_bar_lit_means_no_bar(hut):
    for reveal in ([], ["tab:practice", "act:explore", "board"]):
        assert run(with_reveal(main_at(hut, 1), reveal), "return H.topHtml();") == ""


def test_the_whole_page_redraws_when_the_prologue_lights_something_new(hut):
    """分頁列與狀態列只在整頁重畫時才換：renderTop 看到亮起來的東西變了就整頁重畫，沒變就只換狀態列。"""
    m = main_at(hut, 1)
    out = run(m, """
      H.render();
      T.els.app.innerHTML = "OLD";
      H.renderTop();                                   // 沒有新亮起來的：只換狀態列
      const same = [T.els.app.innerHTML, T.els.top.hidden];
      H.S.main = %s;                                   // 多亮了分頁
      H.renderTop();
      return [same, T.els.app.innerHTML !== "OLD", H.S.prologueKey];""" % json.dumps(with_reveal(m, ["xinde", "tab:practice", "tab:craft"])))
    assert out[0] == ["OLD", False] and out[1] is True and out[2] == "xinde,tab:practice,tab:craft"


def test_a_hidden_tab_cannot_be_the_page_you_are_on(hut):
    """序章重來（換季）：藏起來的分頁不能還停在那一頁。"""
    out = run(main_at(hut, 0), "H.render(); return H.S.tab;", S={"tab": "practice"})
    assert out == "jianghu"


# ── 對話框 ──────────────────────────────────────────

def test_the_box_shows_the_scene_before_the_words(hut):
    g = main_at(hut, 7)["guide"]
    assert g["scene"] == "斷眉來了。"
    html = run({"guide": g}, "return H.guideHtml(m.guide, false);")
    assert '<p class="guide-scene">斷眉來了。</p>' in html and html.index("guide-scene") < html.index("guide-text")


def test_a_shut_box_shows_the_short_line_and_remembers_the_step(hut):
    """收起記的是步驟的 key（FB-076：網頁的 guideKey），不是那一句話；收起來那一行用 line。"""
    g = main_at(hut, 1)["guide"]  # line："看修練頁"（說話的人網頁自己寫在前面，line 不再帶「師父：」）
    assert g["line"] == "看修練頁"
    html = run({"guide": g}, "return H.guideHtml(m.guide, false);", stored={"tx-guide-shut": g["key"]})
    assert "師父</b>：看修練頁" in html and "師父：師父" not in html  # 收起來那一行用 line
    longer = run({"guide": {**g, "line": ""}}, "return H.guideHtml(m.guide, false);", stored={"tx-guide-shut": g["key"]})
    assert f"師父</b>：{g['text']}" in longer  # 沒寫 line 就是原本的話
    assert "guide-scene" not in run({"guide": {**g, "scene": ""}}, "return H.guideHtml(m.guide, false);")


def test_the_skip_link_is_only_on_the_first_step(hut):
    assert "skip-prologue" in run(with_reveal(main_at(hut, 0), [], skip=True), "return H.pageJianghu();")
    assert "skip-prologue" not in run(with_reveal(main_at(hut, 0), [], skip=False), "return H.pageJianghu();")


# ── 修練頁、煉製頁 ──────────────────────────────────

def pages_at(game, step):
    _to_step(game, step)
    return server.main_view(game), server.menxia_view(game)


def test_the_masters_words_top_the_practice_and_craft_pages(hut):
    m, x = pages_at(hut, 4)
    practice = run(m, "return H.pagePractice();", menxia=x)
    craft = run(m, "return H.pageCraft();", menxia=x)
    for page in (practice, craft):
        assert page.index("guide") < page.index('id="mx-msg"') and "把【粗淺拳腳】練到第三成。" in page  # 武學重構：點名的是裝了意境的基礎拳腳
    plain = run({**m, "prologue": None}, "return H.pagePractice();", menxia=x)
    assert 'class="card guide"' not in plain  # 序章外的修練頁沒有師父


def test_the_practice_page_points_at_the_buttons_of_the_step(hut):
    m, x = pages_at(hut, 4)  # 練到第三成：練成鈕發光；師父點名的基礎拳腳本來就在身上（武學重構），功法庫裡沒有一列要人改練
    page = run(m, "return H.pagePractice();", menxia=x)
    assert re.search(r'data-op="practice" data-glow="practice"', page)
    rows = dict(re.findall(r'data-act="art" data-id="(\w+)"( data-glow="[^"]*")?', page))
    assert rows == {} and 'data-glow="switch"' not in page  # 身上的兩門是卷軸卡，不是功法庫的一列；庫裡沒有別的
    m, x = pages_at(hut, 5)  # 揣摩那一步（武學重構：以前是修練）：修練頁沒有一列發光，煉製頁剛悟到的意境發光
    page = run(m, "return H.pagePractice();", menxia=x)
    assert 'data-glow="cultivate"' not in page and 'data-glow="switch"' not in page
    craft = run(m, "H.S.craftPick = true; return H.pageCraft();", menxia=x)
    assert 'data-glow="pick:insight"' in craft


def test_the_practice_button_is_greyed_with_the_masters_reason(hut):
    m, x = pages_at(hut, 1)  # 看修練頁那一步：沒叫你練功（點了身上那一門的光點，抽屜裡的練成鈕灰著）
    page = run(m, "return H.pagePractice();", menxia=x, S={"pdrawer": {"t": "worn", "key": "武學"}})
    assert re.search(r'data-op="practice" data-glow="practice" data-kind="\w+" aria-label="師父這一步沒叫你練功。"[^>]*disabled>', page)
    assert '<p class="train-why">師父這一步沒叫你練功。</p>' in page  # 原因寫在朱印底下那一行
    m, x = pages_at(hut, 4)  # 練到第三成那一步：裝了意境的基礎拳腳就在身上（武學重構：不必先換上），武學那一欄練得下去
    page = run(m, "return H.pagePractice();", menxia=x)  # 師父叫你練：沒點過光點，抽屜也先攤開練得下去的那一門
    assert re.search(r'data-op="practice" data-glow="practice" data-kind="武學" aria-label="練成第\d+成（心得 \d+）"[^>]*><b>練</b><small>心得', page)


LONG_WORDS = "這一段師父的話很長很長，" * 8 + "\n\n" + "最後一段才是要你做的事：按底下的鈕。"


def test_the_masters_words_are_never_cut_in_the_hut(hut):
    """T7 審查 I1（設計 6.2「話不會被切掉」）：序章裡師父的框不收成三行；序章外照舊三行、點了看全文。"""
    m = main_at(hut, 4)
    guide = {**m["guide"], "text": LONG_WORDS}
    html = run({**m, "guide": guide}, "return H.guideHtml(m.guide, false);")
    assert 'class="guide-text"' in html and "clamp" not in html and "按底下的鈕" in html
    outside = run({**m, "prologue": None, "guide": guide}, "return H.guideHtml(m.guide, false);")
    assert 'class="guide-text clamp"' in outside


def test_the_masters_paragraphs_keep_their_breaks():
    """話裡的 \\n\\n 是段落（p4、p5、p7、p9、p11）：預設的空白處理會把它折成一個空格，要 pre-line。靜態檢查樣式表。"""
    css = (ROOT / "web" / "style.css").read_text(encoding="utf-8")
    rule = re.search(r"^\.guide-text \{([^}]*)\}", css, re.M)
    assert rule and "white-space: pre-line" in rule.group(1)


def test_the_huts_place_card_is_not_drawn_while_the_master_talks(hut, newcomer):
    """T7 審查 I1：草廬那張地點描寫卡是靜態的，師父的框顯示著的時候不畫它（給師父的整段話讓出地方）；事件在眼前時場景就是事件，照畫；
    沒有框的時候（例如籌備中）也照畫；序章外照畫。"""
    m = main_at(hut, 5)
    assert m["guide"] and not any(o["id"].startswith("choice:") for o in m["options"])
    page = run(m, "return H.pageJianghu();")
    assert 'class="card guide"' in page and 'class="card scene"' not in page
    assert 'class="card scene"' in run({**m, "guide": None}, "return H.pageJianghu();")
    assert 'class="card scene"' in run({**m, "prologue": None}, "return H.pageJianghu();")
    event = main_at(newcomer(), 0)
    assert 'class="card scene"' in run(event, "return H.pageJianghu();")  # 遇險的事件


PAGED = "第一段，先說天下三邊。\n\n第二段，再說使命。\n\n最後一段：打開輿圖。"


def test_a_paged_master_box_shows_one_paragraph_at_a_time_and_never_cuts_one(hut):
    """T7 審查 I1（d）、（e）：話太長、要做的事會落到分頁列底下的步驟（paged）照空一行分頁：先露第一段與「下一段 ▸」，
    最後一頁沒有鈕、帶著要做的事；旁白只在第一頁；每一段都是整段，不切。"""
    m = main_at(hut, 4)
    guide = {**m["guide"], "text": PAGED, "paged": True, "scene": "他放下酒葫蘆。"}
    out = run({**m, "guide": guide}, """
      const html = [H.guideHtml(m.guide, false)];
      H.nextGuidePage(m.guide); html.push(H.guideHtml(m.guide, false));
      H.nextGuidePage(m.guide); html.push(H.guideHtml(m.guide, false));
      H.nextGuidePage(m.guide); html.push(H.guideHtml(m.guide, false));  // 最後一頁再按：不超過
      return html;""")
    first, second, last, again = out
    assert "第一段，先說天下三邊。" in first and "第二段" not in first and "他放下酒葫蘆" in first and "下一段 ▸" in first
    assert "第二段，再說使命。" in second and "第一段" not in second and "他放下酒葫蘆" not in second and "下一段 ▸" in second
    assert "最後一段：打開輿圖。" in last and "下一段" not in last and again == last
    assert all("clamp" not in html for html in out)


def test_a_paged_step_starts_over_on_its_first_page_and_an_unpaged_one_is_one_block(hut):
    m = main_at(hut, 4)
    guide = {**m["guide"], "text": PAGED, "paged": True}
    out = run({**m, "guide": guide}, """
      H.nextGuidePage(m.guide); H.nextGuidePage(m.guide);
      const other = { ...m.guide, key: "別的一步" };
      return [H.guideHtml(other, false), H.guideHtml({ ...m.guide, paged: false }, false)];""")
    assert "第一段，先說天下三邊。" in out[0] and "第二段" not in out[0]  # 換了一步：回到第一頁
    assert all(part in out[1] for part in ("第一段", "第二段", "最後一段")) and "下一段" not in out[1]


def test_the_cue_points_at_a_target_below_the_fold_and_only_then(hut):
    """T7 審查 M7：要按的東西在第一屏之外（修練頁的改練那一列在 y≈1300）時，師父的框上有「在下面 ↓」；它在第一屏裡、或不在序章就沒有。"""
    m = main_at(hut, 4)
    script = """
      const inserted = [];
      const head = { firstElementChild: { insertAdjacentHTML: (pos, html) => inserted.push([pos, html]) }, querySelector: () => null };
      T.qs[".card.guide .guide-head"] = head;
      T.qs[".tabs"] = { getBoundingClientRect: () => ({ top: 756 }) };
      const at = (top, bottom = top + 60) => { T.qs["#page .glow"] = { getBoundingClientRect: () => ({ top, bottom }) }; inserted.length = 0; H.guideCue(); return inserted.length; };
      return { below: at(1300), onScreen: at(400), justUnderTheBar: at(760), peeking: at(747, 813), fits: at(700, 750), touching: at(696, 756),
               none: (delete T.qs["#page .glow"], inserted.length = 0, H.guideCue(), inserted.length), html: (at(1300), inserted[0]) };"""
    out = run(m, script)
    assert out["below"] == 1 and out["onScreen"] == 0 and out["justUnderTheBar"] == 1 and out["none"] == 0
    # 提示的規則是「要按的東西整個看得到」才不需要：底邊在分頁列頂邊（756）或以上。步驟 4（joy 的版本，話是一整段）基礎拳腳那顆挑選清單
    # 在 747～813：只露出 9px，玩家看不到，要有「在下面 ↓」；700～750 整個在分頁列上面、696～756 剛好貼著，不用。
    assert out["peeking"] == 1 and out["fits"] == 0 and out["touching"] == 0
    assert out["html"][0] == "afterend" and 'data-act="guide-below"' in out["html"][1] and "在下面 ↓" in out["html"][1]
    outside = run({**m, "prologue": None}, script)
    assert outside["below"] == 0  # 序章外沒有這個提示


def test_the_cue_is_worked_out_again_when_the_viewport_changes(hut):
    """T7 走查 W-F：「在下面 ↓」只在畫面重畫時算；轉向或拉視窗之後它不見了、目標還在 1269，要等下一次重畫才回來。resize 時重算（去抖，
    一連串的 resize 只算一次），不重畫。序章外沒有目標就什麼都不做。"""
    m = main_at(hut, 4)
    script = """return (async () => {
      const inserted = [];
      T.qs[".card.guide .guide-head"] = { firstElementChild: { insertAdjacentHTML: (pos, html) => inserted.push(html) }, querySelector: () => null };
      T.qs[".tabs"] = { getBoundingClientRect: () => ({ top: 756 }) };
      T.qs["#page .glow"] = { getBoundingClientRect: () => ({ top: 1269, bottom: 1329 }) };
      const fire = () => (T.listeners.resize || []).forEach((fn) => fn());
      fire(); fire(); fire();
      const early = inserted.length;                        // 去抖：馬上還沒算
      await new Promise((resolve) => setTimeout(resolve, 400));
      return { early, after: inserted.length, render: T.els.app.innerHTML };
    })();"""
    out = run(m, script)
    assert out["early"] == 0 and out["after"] == 1  # 三下 resize 只算一次
    assert out["render"] == ""  # 沒有重畫（#app 沒被寫）
    outside = run({**m, "prologue": None}, script)
    assert outside["after"] == 0


def test_the_cue_takes_the_page_to_the_target(hut):
    m = main_at(hut, 4)
    out = run(m, """
      const calls = [];
      T.qs["#page .glow"] = { scrollIntoView: (opts) => calls.push(opts) };
      H.scrollToGuideTarget();
      delete T.qs["#page .glow"]; H.scrollToGuideTarget();  // 目標不在了：什麼都不做
      return calls;""")
    assert len(out) == 1 and out[0]["block"] == "center"


def test_the_paging_state_does_not_survive_a_walk_through_other_steps(hut):
    """T7 審查 N3：換季回草廬重走一遍（不重新載入頁面）：停在第 11 步第 3 頁的記錄，在框換成別一步、或框不在的那一刻就清掉，
    再走到第 11 步是第 1 頁。"""
    m = main_at(hut, 4)
    farewell = {**m["guide"], "key": "p11_farewell", "text": PAGED, "paged": True}
    other = {**m["guide"], "key": "p3_insight"}
    out = run({**m, "guide": farewell}, """
      H.nextGuidePage(m.guide); H.nextGuidePage(m.guide);
      const last = H.guideHtml(m.guide, false);
      H.guideHtml(%s, false);               // 重走：別的步驟
      const again = H.guideHtml(m.guide, false);
      H.nextGuidePage(m.guide);
      H.guideHtml(null, false);             // 框不在了（例如事件擋著）
      return [last, again, H.guideHtml(m.guide, false), H.S.guidePage];""" % json.dumps(other))
    last, again, third, state = out
    assert "最後一段" in last and "第一段，先說天下三邊。" in again and "第二段" not in again and "第一段，先說" in third and state is None


def test_the_stats_panel_closes_when_the_stats_step_completes(hut):
    """T7 走查 W-D：步驟 9 點開的屬性面板留到步驟 11，「前往」被擠到分頁列底下（776）。配了點、步驟換掉的那一刻收起來；
    步驟還沒換（輪詢）、序章外都不動。"""
    before = main_at(hut, 8)
    assert "stats" in before["prologue"]["glow"]
    hut.allocate_stat("str")
    after = server.main_view(hut)
    assert "stats" not in after["prologue"]["glow"]
    script = "H.S.showMore = true; H.setMain(%s); return H.S.showMore;"
    assert run(before, script % json.dumps(after)) is False
    assert run(before, script % json.dumps(before)) is True  # 同一步的輪詢：不動
    outside = {**before, "prologue": None}
    assert run(outside, script % json.dumps({**after, "prologue": None})) is True  # 序章外：不動
    assert run(before, script % json.dumps({**after, "prologue": None})) is False  # 序章走完、這一步結束的那一刻也收


def test_step_five_points_at_a_row_under_the_arts_library_title(hut):
    """步驟 5 的改練（arts-polish-1）：修練頁真的有叫「功法庫」的標題，發光的那一列（改練）在它底下。武學重構：師父點名的基礎拳腳
    本來就在身上、這一步沒寫 switch；這裡自己把 switch 加進這一步的 glow、換上一門雜學，讓點名的那一門落到功法庫裡。"""
    m, x = pages_at(hut, 4)
    hut.content.tutorial.steps[4].glow.append("switch")
    prologue.give_art(hut.state, hut.content, hut.world, GiveArt(id="junk", level=5))
    hut.switch_art("junk")
    m, x = server.main_view(hut), server.menxia_view(hut)
    page = run(m, "return H.pagePractice();", menxia=x)
    assert page.index("功法庫") < page.index('data-glow="switch"')


def test_the_click_handlers_for_the_two_new_box_buttons_are_wired():
    """「下一段 ▸」與「在下面 ↓」是事件代理的 data-act：少接一個，鈕就按不動。"""
    source = webharness.app_source()
    assert 'case "guide-next": nextGuidePage(S.main.guide); renderPage(); break;' in source
    assert 'case "guide-below": scrollToGuideTarget(); break;' in source


def test_the_road_out_of_the_hut_keeps_the_road_explainer(hut):
    """T7 審查 N2：草廬的地點描寫卡在師父說話時不畫，但出師那一段路（第一條路）上那張「路上可以折返……」的說明要留著。"""
    m = main_at(hut, 10)
    hut.choose("move:town")
    road = server.main_view(hut)
    assert road["on_road"] and road["guide"] and road["prologue"]
    page = run(road, "return H.pageJianghu();")
    assert 'class="card scene road' in page
    assert 'class="card scene"' not in run(m, "return H.pageJianghu();") and "card scene" not in run(m, "return H.pageJianghu();")  # 路前（在草廬）照舊不畫


def test_the_four_sights_screen_has_no_now_card_and_its_choices_fit(hut):
    """T7 審查 I2、W1：草廬四景（有所感）的卡在眼前時沒有「剛剛」卡、師父的框也不放（畫面就是那一張卡）；四個做法都畫出來。
    高度由 375×812 的量測腳本看（見報告）。"""
    _to_step(hut, 2)
    hut.choose("act:explore")
    m = server.main_view(hut)
    assert hut.state.pending_event is None and hut.state.player.sensing is not None and m["now"] == "" and m["guide"] is None
    page = run(m, "return H.pageJianghu();")
    assert 'class="now' not in page and 'class="card guide' not in page and page.count('data-act="choose"') == 4


def test_the_insight_melt_is_greyed_in_the_hut(hut):
    """T6 review M4、M7：草廬裡不熔意境。按鈕灰掉、寫師父的原因（跟練成鈕同一個做法），不是亮著按了才被擋。
    閉關鈕 Joy 2026-10-25 從俠客頁拿掉了：引擎照舊回 seclude_blocked，頁面上不畫閉關。"""
    m, x = pages_at(hut, 3)
    assert x["seclude_blocked"] and x["insights"][0]["blocked"]
    # 卷軸卡版：意境是一顆一顆的籤，點開才有「化成心得」鈕（S.insOpen）
    page = run(m, "return H.pagePractice();", S={"insOpen": x["insights"][0]["id"]}, menxia=x)
    assert "閉關" not in page
    assert re.search(r'data-act="melt-insight"[^>]*disabled', page) and x["insights"][0]["blocked"] in page
    out = Game.new(hut.content, "路人", rng=random.Random(0), world=hut.world)
    out.state.player.insights.append("feng")
    x = server.menxia_view(out)
    page = run(server.main_view(out), "return H.pagePractice();", S={"insOpen": "feng"}, menxia=x)
    assert 'data-act="melt-insight"' in page  # 開著的那個意境的鈕在，只是沒灰
    assert x["seclude_blocked"] is None and "閉關" not in page
    assert not re.search(r'data-act="melt-insight"[^>]*disabled', page)


def _row_glows(page):
    """修練頁收著的每一列武學帶的 data-glow（沒有就是空字串）：{id: 鍵}。"""
    return {art_id: glow.strip(' "') for art_id, glow in re.findall(r'data-act="art" data-id="(\w+)"(?: data-glow="([^"]*)")?', page)}


def test_only_the_art_the_master_names_glows_to_be_switched_to(hut):
    """T7 走查 W-A：改練的發光由伺服器說是哪一列（art_rows 的 glow）：點名的那一門不在身上時只有它那一列，換上之後沒有一列；
    點開別的那一列，裡面的「改練這一門」也不發光。武學重構：點名的基礎拳腳本來就在身上、這一步沒寫 switch——先看沒有一列發光，
    再自己把 switch 加進 glow、換上一門雜學，讓它落到功法庫裡。"""
    m, x = pages_at(hut, 4)
    named = prologue.slotted_arts(hut.state, hut.content, hut.world)[0].id
    assert all("switch" not in v for v in _row_glows(run(m, "return H.pagePractice();", menxia=x)).values())  # 點名的那一門就在身上
    hut.content.tutorial.steps[4].glow.append("switch")
    prologue.give_art(hut.state, hut.content, hut.world, GiveArt(id="junk", level=5))
    hut.switch_art("junk")
    m, x = server.main_view(hut), server.menxia_view(hut)
    page = run(m, "return H.pagePractice();", menxia=x)
    glows = _row_glows(page)
    assert "switch" in glows[named] and all("switch" not in v for k, v in glows.items() if k != named)
    opened = run(m, "return H.pagePractice();", menxia=x, S={"artOpen": named})
    assert re.search(r'data-act="switch" data-glow="switch" data-id="%s"' % named, opened)
    hut.switch_art(named)
    x = server.menxia_view(hut)
    m = server.main_view(hut)
    page = run(m, "return H.pagePractice();", menxia=x)
    assert all("switch" not in v for v in _row_glows(page).values())  # 雜學在功法庫裡，不發光
    opened = run(m, "return H.pagePractice();", menxia=x, S={"artOpen": "junk"})
    assert 'data-act="switch"' in opened and not re.search(r'data-act="switch" data-glow', opened)


def test_the_slotting_step_lights_the_empty_slots_of_the_base_art_on_the_practice_page(hut):
    """裝意境那一步（爐裡只合意境之後改在修練頁，Joy 2026-10-21）：師父點名的基礎拳腳的空槽發光（prologue.art_glow 的 "slot"），
    點開空槽、挑意境的那幾顆也發光；別門武學不發光，頁面上也沒有別的東西發光。"""
    m, x = pages_at(hut, 3)
    assert m["prologue"]["glow"] == ["tab:practice", "slot"]
    page = run(m, "return H.pagePractice();", menxia=x)
    slots = re.findall(r'data-act="slot-pick" data-id="(\w+)" data-i="\d+"( data-glow="slot")?', page)
    assert slots and {i for i, g in slots if g} == {"basic_fist"} and all(g for i, g in slots if i == "basic_fist")
    tags = re.findall(r"<button[^>]*data-glow=[^>]*>", page)
    assert {re.search(r'data-glow="([^"]*)"', t).group(1) for t in tags if " disabled" not in t} == {"slot"}
    picked = run(m, "H.S.slotPick = { art: 'basic_fist', i: 0 }; return H.pagePractice();", menxia=x)
    assert re.search(r'data-act="slot-in" data-id="basic_fist" data-i="0" data-ins="\w+" data-glow="slot"', picked)


def test_the_craft_page_lights_the_two_pieces_to_put_in_the_furnace(hut):
    """T7 走查 W-B：煉製頁揣摩那一步，開爐灰著不會發光，要放進爐子的兩份意境在挑選清單裡（抽屜）：兩份都發光，
    放進爐子的那一份就不再發光；兩份都放好之後開爐發光。"""
    m, x = pages_at(hut, 5)
    assert m["prologue"]["glow"] == ["tab:craft", "pick:insight", "forge"]
    pieces = [i["id"] for i in x["insights"]]
    assert len(pieces) == 2
    page = run(m, "H.S.craftPick = true; return H.pageCraft();", menxia=x)  # 清單在抽屜裡（Joy 2026-10-19）：打開才看得到那幾顆
    assert re.findall(r'data-act="pick" data-type="ins" data-glow="pick:insight" data-id="([^"]+)"', page) == pieces
    assert 'data-type="art"' not in page  # 爐裡只合意境
    closed = run(m, "return H.pageCraft();", menxia=x)
    assert 'data-act="pot-open" data-glow="pick:insight"' in closed and 'data-act="pick"' not in closed  # 抽屜關著：空格亮
    placed = run(m, f"H.S.craftPick = true; H.S.forgeSel = [{{ type: 'ins', id: '{pieces[0]}' }}]; return H.pageCraft();", menxia=x)
    assert re.findall(r'data-glow="pick:insight" data-id="([^"]+)"', placed) == pieces[1:]  # 放進去的那一份不再亮，另一份還在清單裡
    both = run(m, f"H.S.forgeSel = [{{ type: 'ins', id: '{pieces[0]}' }}, {{ type: 'ins', id: '{pieces[1]}' }}]; return H.pageCraft();", menxia=x)
    assert 'data-glow="pick:' not in both and re.search(r'id="forge" data-act="forge" data-glow="forge"\s*>', both)  # 兩份都放好：開爐亮了


def test_the_first_glowing_thing_on_the_craft_page_is_an_insight_chip(hut):
    """W-B：師父框上的「在下面 ↓」看的是頁面裡第一個會發光的東西（#page .glow，applyGlow 只加在按得下去的）。這個測試只釘「煉製頁
    揣摩那一步的標記裡，由上往下第一個按得下去又帶發光鍵的是挑選清單裡的意境，開爐灰著不算」；它不跑 guideCue——
    node 的假 DOM 沒有版面，算位置、有沒有「在下面 ↓」的部分由上面 test_the_cue_points_at_a_target_below_the_fold_and_only_then
    （假的 getBoundingClientRect）釘。"""
    m, x = pages_at(hut, 5)
    out = run(m, "H.S.craftPick = true; return H.pageCraft();", menxia=x)  # 抽屜開著（關著時亮的是爐子的空格）
    tags = re.findall(r"<button[^>]*data-glow=[^>]*>", out)  # 發光只加在按得下去的（applyGlow 的 :not([disabled])）
    live = [re.search(r'data-glow="([^"]*)"', tag).group(1) for tag in tags if " disabled" not in tag]
    assert tags and live[0] == "pick:insight" and "forge" not in live  # 開爐灰著（不發光），頁面由上往下第一個會發光的是意境


@pytest.mark.parametrize("stored", ["ready", "內功", "武學"])
def test_a_filter_the_browser_remembers_from_an_earlier_character_never_hides_what_the_master_points_at(newcomer, stored):
    """review-ap3 I1：功法庫的篩選記在瀏覽器裡，換了新角色也還在；篩選鈕卻只在庫超過 8 門時才畫。草廬裡庫只有一兩門，記著的篩選
    把師父點名的那一列（第 5 步改練、第 10 步熔）藏起來、又沒有鈕可以改回來，新人卡住。鈕沒畫就不套篩選。"""
    key = {"tx-arts-filter-practice": stored}
    for step, glow in ((4, "switch"), (9, "melt")):
        game = newcomer()
        m, x = pages_at(game, step)
        if glow == "switch":  # 武學重構：點名的基礎拳腳本來就在身上、這一步沒寫 switch；自己加上、換上一門雜學，讓它落到功法庫裡
            game.content.tutorial.steps[4].glow.append("switch")
            prologue.give_art(game.state, game.content, game.world, GiveArt(id="junk", level=5))
            game.switch_art("junk")
            m, x = server.main_view(game), server.menxia_view(game)
        page = run(m, "return H.pagePractice();", menxia=x, stored=key)
        assert "這一類沒有功法" not in page and 'class="lib-filter"' not in page  # 庫是短的：沒有鈕，也就沒有篩選
        rows = dict(re.findall(r'data-act="art" data-id="(\w+)"( data-glow="[^"]*")?', page))
        assert any(glow in v for v in rows.values()), (step, glow, rows)  # 發光的那一列在
        opened = next(k for k, v in rows.items() if glow in v)
        card = run(m, "return H.pagePractice();", menxia=x, stored=key, S={"artOpen": opened})
        assert re.search(rf'data-act="{glow}" data-glow="{glow}"', card), (step, glow)  # 點開之後卡裡的鈕也發光


@pytest.mark.parametrize("stored", ["內功", "意境", "武學"])
def test_a_remembered_craft_filter_never_hides_the_pieces_the_master_points_at(hut, stored):
    """同一個毛病在煉製頁：揣摩那一步要放進爐子的兩份意境，不能被上一個角色留下的篩選藏起來；煉製頁不再畫功法的篩選鈕
    （爐裡只合意境），序章裡、序章外都一樣。"""
    m, x = pages_at(hut, 5)
    page = run(m, "H.S.craftPick = true; return H.pageCraft();", menxia=x, stored={"tx-arts-filter-craft": stored})
    assert len(re.findall(r'data-act="pick" data-type="ins" data-glow="pick:insight"', page)) == 2 and "fchips" not in page
    plain = run({**m, "prologue": None}, "H.S.craftPick = true; return H.pageCraft();", menxia=x, stored={"tx-arts-filter-craft": stored})
    assert len(re.findall(r'data-act="pick" data-type="ins"', plain)) == 2 and "fchips" not in plain


def test_only_the_art_the_master_names_glows_to_be_melted(hut):
    m, x = pages_at(hut, 9)  # 熔雜學那一步
    rows = dict(re.findall(r'data-act="art" data-id="(\w+)"( data-glow="[^"]*")?', run(m, "return H.pagePractice();", menxia=x)))
    assert "melt" in rows["junk"] and all("melt" not in v for k, v in rows.items() if k != "junk")
    opened = run(m, "return H.pagePractice();", menxia=x, S={"artOpen": "junk"})
    assert re.search(r'data-act="melt" data-glow="melt" data-id="junk"', opened)
    assert 'data-act="art" data-id="junk" data-glow' not in opened  # 點開了：發光換到裡面的鈕


def test_the_forge_button_carries_its_glow_key(hut):
    m, x = pages_at(hut, 3)
    assert 'id="forge" data-act="forge" data-glow="forge"' in run(m, "return H.pageCraft();", menxia=x)


# ── 設定：重看序章 ──────────────────────────────────

def test_the_sheet_offers_the_recap_only_when_there_is_one(hut):
    m = main_at(hut, 1)
    none = run(m, "return H.sheetHtml();", S={"recap": ""})
    unknown = run(m, "return H.sheetHtml();", S={"recap": None})
    assert "重看序章" not in none and "重看序章" not in unknown and "略過新手引導" in none
    closed = run(m, "return H.sheetHtml();", S={"recap": "<p>RECAP</p>"})
    opened = run(m, "return H.sheetHtml();", S={"recap": "<p>RECAP</p>", "recapOpen": True})
    assert "重看序章" in closed and "RECAP" not in closed
    assert 'aria-expanded="true"' in opened and '<div class="recap card"><p>RECAP</p></div>' in opened


# ── 打開修練頁、煉製頁本身是一步 ─────────────────────────

def test_opening_the_practice_page_in_the_prologue_is_sent_to_the_server_as_a_step(hut):
    m = main_at(hut, 1)  # 看修練頁那一步
    hut.view_tab("practice")  # 伺服器收到之後的樣子
    after, x = server.main_view(hut), server.menxia_view(hut)
    assert after["guide"]["text"] == "去探索。"
    script = "await H.goTab('practice'); return { calls: T.calls, guide: H.S.main.guide && H.S.main.guide.text, tab: H.S.tab };"
    out = run(m, "return (async () => {" + script + "})();", responses={"/api/do/view_tab": {"main": after}, "/api/menxia": x})
    assert out["calls"][0] == ["/api/do/view_tab", {"tab": "practice"}]
    assert [c[0] for c in out["calls"]] == ["/api/do/view_tab", "/api/menxia"]
    assert out["guide"] == "去探索。" and out["tab"] == "practice"


def test_opening_the_practice_page_outside_the_prologue_asks_for_no_step(content):
    plain = server.main_view(Game.new(content, "路人", rng=random.Random(0)))
    out = run(plain, "return (async () => { await H.goTab('craft'); return T.calls.map((c) => c[0]); })();",
              responses={"/api/menxia": server.menxia_view(Game.new(content, "路人", rng=random.Random(0)))})
    assert out == ["/api/menxia"]  # 序章外不送 view_tab


def test_the_status_bar_element_follows_what_the_step_shows(newcomer):
    """renderTop 只換狀態列時，#top 的 hidden 跟著有沒有東西畫：第一步整條藏著、拜師之後現出來。"""
    first = run(main_at(newcomer(), 0), "H.render(); T.els.top.hidden = false; H.renderTop(); return T.els.top.hidden;")
    second = run(main_at(newcomer(), 1), "H.render(); T.els.top.hidden = true; H.renderTop(); return T.els.top.hidden;")
    assert first is True and second is False


# ── 卷軸卡（2026-10-06，企劃者「先用捲軸卡」）────────────────

def _scroll_page(content, *, arts=0, S=None):
    """序章外的修練頁（序章測試內容開局送兩門基礎武學，但這裡不走序章）：功法庫塞 arts 門假的一列（只為了看清單怎麼畫）。"""
    game = Game.new(content, "路人", rng=random.Random(0))
    m, x = server.main_view(game), server.menxia_view(game)
    base = next(r for r in x["owned_arts"] if not r["worn"]) if any(not r["worn"] for r in x["owned_arts"]) else x["owned_arts"][0]
    x["owned_arts"] += [{**base, "id": f"lib{i}", "name": f"庫{i}", "worn": False,
                         "kind": "武學" if i % 3 else "內功", "cultivate": {**base["cultivate"], "ok": i % 4 == 0}} for i in range(arts)]
    return run(m, "return H.pagePractice();", menxia=x, S=S)


def test_the_two_worn_arts_are_scroll_cards_with_their_own_buttons(prologue_content):
    page = _scroll_page(prologue_content)  # 招式與絕學稿案第四輪：身上兩門是人形圖上的兩個光點，點了才從底下升起那一張卡
    assert "pr-sheet" not in page and 'data-act="hero-node" data-kind="art" data-key="武學"' in page and 'data-key="內功"' in page
    for kind in ("武學", "內功"):
        sheet = _scroll_page(prologue_content, S={"pdrawer": {"t": "worn", "key": kind}}).split('class="sheet pr-sheet"')[1]
        assert sheet.count('class="acard') == 1 and '<span class="worn">身上</span>' in sheet
        assert sheet.count('data-op="practice"') == 1 and f'data-op="practice" data-glow="practice" data-kind="{kind}"' in sheet  # 一顆練成鈕，帶自己那一欄
    assert "lib-filter" not in page and "再列" not in page  # 功法庫少的時候不出篩選


def test_the_cards_have_no_forge_odds_bar(prologue_content):
    """武學重構：品級不靠修練衝，卷軸卡上沒有機率條了（以前伺服器送 forge_odds 才畫）。"""
    assert 'class="odds"' not in _scroll_page(prologue_content)


def test_a_big_library_can_be_filtered_and_shows_a_page_at_a_time(prologue_content):
    page = _scroll_page(prologue_content, arts=30)
    assert 'data-act="lib-filter" data-filter="ready"' in page and "再列" in page
    assert page.count('class="art libr') == 8  # 先列 8 門
    every = _scroll_page(prologue_content, arts=30, S={"libAll": True})
    assert "再列" not in every and every.count('class="art libr') >= 30
    inner = _scroll_page(prologue_content, arts=30, S={"libFilter": "內功", "libAll": True})
    assert 'lib-kind">內功' in inner and 'lib-kind">武學' not in inner  # 照種類分段（招式與絕學稿案第四輪）：只剩內功那一段


def test_the_cards_draw_the_ten_levels_as_cells_not_circles(prologue_content):
    """企劃者 10/6：功法卡、人物卡裡的十成不要圈圈，跟卷軸卡同一種格子；修練鈕也不寫「→ 下一品」。"""
    page = _scroll_page(prologue_content, S={"artInfo": "basic_fist"})
    assert "●" not in page and "○" not in page
    # 俠客頁改版（Joy 2026-10-26）之後本人的角色卡不再整張攤在門下：門下卡上的兩門是同一種十格（sa-ten）
    assert 'class="sa-ten" role="meter"' in page and 'aria-label="粗淺拳腳第1成"' in page
    assert "→" not in page and "下一品" not in page


# ── 原 test_fb092_095.py（整檔搬進來） ──
# FB-093～095（QA 走 joy 版序章與入伍段，main 8d4d470，2026-10-06）。
#
# joy 在 GitHub 上也做了 FB-092～095（PR #30、#31），併進 main 之後 PM 裁示 joy 的為準（chain-on-main，2026-10-07）：我們的重複做法
# 拿掉了（FB-092 整段都是 joy 的，這裡沒有測試）。留下的是我們加在 joy 的做法上、joy 沒有的東西（結語、一週保底、網頁的「在下面 ↓」），
# 以及跑在 joy 的程式上、joy 的測試沒蓋到的情況。用真實內容（conftest 的 real、on：這個測試自己的一份複本）；網頁的部分（web/app.js 的
# applyGlow、guideCue、choose 的 ask）照 tests/test_prologue_web.py 的做法放進 node 跑（scripts/test_for.py 改到 app.js 時靠這個檔名挑到這裡）。
# 新寫的句子都在待 joy 潤的清單上（見 fb-report.md）：這裡的測試只認事實（講了什麼、對不對得上規則），不鎖死字句。

# ── FB-093：入伍第 2 步沒說軍令怎麼出力 ─────────────────────────────────
# joy 的版本（2026-10-07 併進 main，PM 裁示 joy 的為準）：每一道沒達成的軍令卡寫怎麼做（atlas.order_how）；第 2 步的 order_hint 點名
# 守勢行動；伺服器在框上帶能完成這一步的選項 id（guide.glow，enlist.glow），網頁讓它們發光、「此地還能做」打開。
# 這裡留下的是 joy 的測試沒蓋到的：每一種軍令卡、黃巾的守勢行動名字；我們的結語（不再整段背五種軍令）；網頁上我們加在 joy 的發光上的
# 三樣——收著的摺疊改由標題列發光、「在下面 ↓」、摺疊在那一步開頭只自動打開一次（tests/test_jianghu_page_web.py）。

DUTY = {"guan": "巡哨", "huang": "傳道", "haoqiang": "保境安民"}


JOIN_AT = {"guan": "changshe", "huang": "huangjin_camp", "haoqiang": "zhuo_militia_hall"}


def _enlisted(on, faction, place=None):
    """剛投靠、看過軍令卡：框停在「挑一道軍令，出一次力」那一步。提示關掉（長社站著大勢人物，真內容的提示表會先排一條）。"""
    game = _game(on, at=place or JOIN_AT[faction])
    game.state.player.tutorial_step = len(guide.steps(game.state, on))
    game.set_hints_off(True)
    game.choose(f"faction:{faction}")
    if faction == "haoqiang":  # 豪強先挑依附哪一軍
        game.choose("faction:ally:guan")
    game.choose("faction:confirm")
    game.view_orders()
    assert game.guide_box()["key"] == "r3_first_order"
    return game


def test_fb093_every_order_card_says_how(on):
    game = _enlisted(on, "guan")
    on_front = front_of(on, "changshe")
    _order(game, "siege", "guan", front=on_front)
    _order(game, "defend", "guan", front=on_front)
    _order(game, "intercept", "guan", location="hilltop_wilds")
    _order(game, "escort", "guan", start="luoyang_road", end="changshe")
    _order(game, "strike", "guan", figure="zhangmancheng")
    cards = {card["title"].split("・")[0]: card for card in game.orders_view()}
    assert set(cards) == {"攻城", "守城", "截糧", "護糧", "打擊"}
    for kind, card in cards.items():
        assert card.get("how"), kind  # 每一道都有做法那一行
    name = lambda loc_id: on.locations[loc_id].name  # noqa: E731
    # 豪強是第三方的季沒有地盤、沒有出陣：攻城、截糧寫遊歷（有出陣的寫法見 tests/acts/test_conquest_*.py）
    assert "遊歷" in cards["攻城"]["how"] and on.orders.duties["guan"].name in cards["守城"]["how"]
    assert name("hilltop_wilds") in cards["截糧"]["how"] and "遊歷" in cards["截糧"]["how"]
    assert name("luoyang_road") in cards["護糧"]["how"] and name("changshe") in cards["護糧"]["how"] and "糧車" in cards["護糧"]["how"]
    assert "挑戰" in cards["打擊"]["how"]  # 打擊那一行本來就有（FB-072）：不動


def test_fb093_the_defence_action_is_named_from_the_content_for_each_side(on):
    """守城的行動名字照內容（orders.json 的 duties），三邊各自的：不是三處各寫一份。"""
    for faction, name in DUTY.items():
        assert on.orders.duties[faction].name == name
    for faction in ("guan", "huang"):
        game = _enlisted(on, faction)
        _order(game, "defend", faction, front=front_of(on, JOIN_AT[faction]))
        [card] = [c for c in game.orders_view() if c["title"].startswith("守城")]
        assert DUTY[faction] in card["how"], faction
        assert not any(other in card["how"] for f, other in DUTY.items() if f != faction), faction


def test_fb093_the_ending_no_longer_recites_every_kind(on):
    """結語（做完之後）把「每一種怎麼做」整段背一遍的部分縮成一句誇獎：怎麼做改寫在軍令卡上。"""
    for faction, who in on.tutorial.enlist.recruiters.items():
        for gone in ("就到那條戰線遊歷", "就在戰線上", "先備好糧草", "到軍令說的地方遊歷", "當面挑戰"):
            assert gone not in who.done, (faction, gone)
        assert len(who.done) < 100, faction  # 以前約 200 字
        assert "陣營" in who.done  # 「陣營 幾／幾」是什麼意思還講：那是卡片上的另一件事


# ── FB-094：豪強入伍第 2 步這一週做不到 ─────────────────────────────────
# joy 選甲（Game._duty：守勢行動不在這週軍令裡也算第 2 步；tests/test_orders.py 三邊各一條）。這裡留下 joy 的測試沒蓋到的：
# 有守城軍令時巡哨照樣替它記一次又走完這一步、別的行動不算；豪強的結語（我們的）；一週（季曆）之後還沒做完，引薦人照樣說結語、
# 入伍段關起來（我們加的保底，joy 的版本沒有：enlist.expire、PlayerState.enlist_since）。


def _finished(game, on):
    assert enlist_done(game.state, on) and game.state.player.enlist_end
    box = game.guide_box()
    assert box["key"] == "enlist_end" and box["end"]
    return box


def enlist_done(state, content):
    from tianxia import enlist

    return enlist.done(state, content)


def test_fb094_patrolling_under_a_defence_order_credits_it_once_and_finishes_the_step(on):
    game = _enlisted(on, "guan")
    order = _order(game, "defend", "guan", front=front_of(on, "changshe"), quota=900)
    game.choose("act:duty")
    _finished(game, on)
    assert order.progress == {game.state.player.name: 1}  # 有守城軍令時，這一下照舊替它記了一次（軍令不動）


def test_fb094_other_actions_do_not_finish_it(on):
    game = _enlisted(on, "guan")
    idle_step(game)
    assert not enlist_done(game.state, on)


def test_fb094_the_magnates_ending_says_what_the_peace_is_for(on):
    done = on.tutorial.enlist.recruiters["haoqiang"].done
    assert "保境安民是守自家地盤" in done and "家主吩咐的大事" in done and "夠格" in done
    assert "不守城" not in done and "牆在自己家裡" not in done  # 舊的說法（不攻城也不守城）跟現在對不上


def test_fb094_a_week_later_the_recruiter_says_the_ending_anyway(on):
    """一週（季曆）之後第一道軍令還沒做完：引薦人照樣說結語、入伍段關起來。從那一步開始算起，不看電腦時鐘（世界時間）。"""
    from tianxia import calendar

    game = _enlisted(on, "haoqiang", place="cao_manor")
    week = calendar.WEEK / calendar.cal_scale(on, game.state.world)
    game.advance(week - 60)
    game.sync(1.0)
    assert not enlist_done(game.state, on)  # 還差一分鐘
    assert game.guide_box()["key"] == "r3_first_order"
    game.advance(120)
    game.sync(2.0)
    box = _finished(game, on)
    assert box["speaker"] == "季伯平" and box["text"] == on.tutorial.enlist.recruiters["haoqiang"].allied["done"]  # 豪強依附一邊的說法
    assert any(line.startswith("【季伯平】") and "保境安民" in line for e in game.state.journal for line in e.guide)  # 說的話記進江湖紀錄
    game.guide_ack()
    game.sync(3.0)
    assert game.guide_box() is None  # 關了就是關了：不會再開


def test_fb094_the_week_counts_from_when_the_step_started_not_from_joining(on):
    from tianxia import calendar

    # 投靠之後晾了 0.7 週才去看軍令卡：第一道軍令那一步從看卡的那一刻才開始，一週從那裡算（不是從投靠）。
    # 距投靠 1.3 週、距那一步開始 0.6 週時還不收；距那一步 1.1 週才收（審查 I-1：以前兩件事在同一刻做，算錯起點也看不出來）
    game = _game(on, at="cao_manor")
    game.state.player.tutorial_step = len(guide.steps(game.state, on))
    game.set_hints_off(True)
    game.choose("faction:haoqiang")
    game.choose("faction:ally:guan")  # 豪強先挑依附哪一軍
    game.choose("faction:confirm")
    week = calendar.WEEK / calendar.cal_scale(on, game.state.world)
    joined = game.state.player.enlist_since
    game.advance(week * 0.7)
    game.sync(1.0)
    assert game.guide_box()["key"] == "r2_briefing"
    game.view_orders()
    p = game.state.player
    assert game.guide_box()["key"] == "r3_first_order" and p.enlist_since == game.state.world.time > joined
    game.advance(week * 0.6)
    game.sync(2.0)
    assert game.guide_box()["key"] == "r3_first_order" and not enlist_done(game.state, on)
    game.advance(week * 0.5)
    game.sync(3.0)
    _finished(game, on)


def test_fb094_the_fallback_only_touches_the_order_step_and_old_saves_start_their_week_when_loaded(on):
    from tianxia import calendar, enlist

    game = _game(on, at="changshe")
    game.state.player.tutorial_step = len(guide.steps(game.state, on))
    game.set_hints_off(True)
    game.choose("faction:guan")
    game.choose("faction:confirm")
    week = calendar.WEEK / calendar.cal_scale(on, game.state.world)
    game.advance(week * 3)
    game.sync(1.0)
    assert game.guide_box()["key"] == "r2_briefing" and game.state.player.enlist_step == 0  # 看軍令卡那一步不被收掉
    game.view_orders()
    game.state.player.enlist_since = None  # 這一版之前存的角色：沒有記下那一步什麼時候開始
    assert enlist.expire(game.state, on) == [] and game.state.player.enlist_since == game.state.world.time  # 從現在算起的一週


# ── FB-095：剛出師的新角色去黃巾別部營寨遊歷，挨了三場打 ───────────────────────────
# joy 的版本：遊歷的標籤寫「必敗」時選項帶 confirm（engine.TRAIN_CONFIRM），網頁用自己的 ask() 問一次、按「照打」才送；師父出師那句
# 多一句別去營寨惹事（joy 的測試：tests/test_orders.py::test_hopeless_training_asks_first_and_fair_training_does_not）。這裡留下 joy 的測試沒蓋到的：真的算出來的必敗、勝算表上每一個字、不算勝算的
# 選單（機器人）不問也不擲骰、伺服器照常打、網頁上問與取消（同一個 Option.confirm、同一個 ask()，PM 裁示用到同一件東西的測試留著）。
# 出陣探索與地盤（2026-10-14）：散人沒有出陣鈕，打仗的鈕是投靠了陣營的人在別人地盤上的「出陣・攻」（同一個 act:train、同一套勝算與問句），
# 所以這一段換成官軍的人站在黃巾別部營寨（黃巾的大本營）；舊遊歷的問句見 tests/test_orders.py（那裡關著出陣）。


def _train(game):
    return next(o for o in game.options() if o.id == "act:train")


def _camp(on):
    return _game(on, faction="guan", at="huangjin_camp")


@pytest.mark.parametrize("word, asks", [("必敗", True), ("凶險", False), ("難分勝負", False), ("五五波", False), ("有把握", False), ("穩勝", False)])
def test_fb095_only_a_losing_fight_asks_first(on, monkeypatch, word, asks):
    """問不問看遊歷按鈕上的勝算那一個字（Game.odds，標籤用的就是它）：只有「必敗」問；勝算表上其他每一個字都不問。"""
    from tianxia.engine import TRAIN_CONFIRM, Game

    game = _camp(on)  # 官軍的人在黃巾的營寨：對手是黃巾的人
    monkeypatch.setattr(Game, "odds", lambda self, squad_id: word)
    option = _train(game)
    assert word in option.label
    assert (option.confirm == TRAIN_CONFIRM) is asks and (option.confirm != "") is asks


def test_fb095_a_real_newcomer_at_the_yellow_turban_camp_is_asked(on):
    """真的算出來的（不是換掉 odds）：新角色威力 0，在黃巾別部營寨遊歷寫必敗，按鈕帶著問句。"""
    game = _camp(on)
    game.state.player.member.wugong_id = None
    option = _train(game)
    assert "必敗" in option.label and option.confirm


def test_fb095_options_without_odds_never_ask_and_listing_them_rolls_nothing(on):
    """假人與整季機器人（bot.pick、bot_policy）看的是不算勝算的選單：沒有問句；列出選單也不碰 game.rng（算勝算用固定種子）。"""
    game = _camp(on)
    game.state.player.member.wugong_id = None
    state = game.rng.getstate()
    plain = {o.id: o for o in game.options(odds=False)}
    assert plain["act:train"].confirm == "" and "必敗" not in plain["act:train"].label
    game.options()
    assert game.rng.getstate() == state
    assert all(o.confirm == "" for o in game.options(odds=False))


def test_fb095_asking_is_the_pages_job_the_server_never_refuses_or_rolls(on):
    """問一次是網頁的事：伺服器收到 act:train 就照常打（機器人、腳本都這樣走），取消的人根本沒有送出；所以取消不花體力、不擲骰。"""
    game = _camp(on)
    game.state.player.member.wugong_id = None
    before = game.state.player.stamina
    state = game.rng.getstate()
    assert _train(game).confirm and game.state.player.stamina == before and game.rng.getstate() == state  # 看選單什麼都沒花
    game.choose("act:train")
    assert game.state.player.stamina < before and game.rng.getstate() != state  # 送出了才花、才擲


_ASK_SCRIPT = """return (async () => {
  const click = (act, id) => T.docListeners.click[0]({ target: { closest: () => ({ dataset: { act, id }, classList: { contains: () => false, add() {}, remove() {} } }) } });
  T.qs['.ask [data-act="ask-no"]'] = { focus() {} };
  const seen = [];
  await click("choose", "act:train");
  seen.push({ asked: T.bodyHtml.join("").includes("%(ask)s"), calls: T.calls.map((c) => c[0]) });
  %(then)s
  return { seen, calls: T.calls.map((c) => [c[0], c[1]]) };
})();"""


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_fb095_the_page_asks_with_its_own_dialog_then_fights_only_on_yes(on):
    from tianxia.engine import TRAIN_CONFIRM

    game = _camp(on)
    game.state.player.member.wugong_id = None
    m = server.main_view(game)
    train = next(o for o in m["options"] if o["id"] == "act:train")
    assert train["confirm"] == TRAIN_CONFIRM
    after = {"main": m, "message": ""}
    cancel = _ASK_SCRIPT % {"ask": TRAIN_CONFIRM, "then": 'await click("ask-no");'}
    out = run(m, cancel, responses={"/api/choose": after})
    assert out["seen"] == [{"asked": True, "calls": []}] and out["calls"] == []  # 問了；取消之後什麼都沒送
    yes = _ASK_SCRIPT % {"ask": TRAIN_CONFIRM, "then": 'await click("ask-yes");'}
    out = run(m, yes, responses={"/api/choose": after})
    assert out["seen"][0]["calls"] == [] and out["calls"] == [["/api/choose", {"id": "act:train"}]]  # 按「照打」才送
    m_safe = {**m, "options": [{**o, "confirm": ""} if o["id"] == "act:train" else o for o in m["options"]]}
    out = run(m_safe, _ASK_SCRIPT % {"ask": TRAIN_CONFIRM, "then": ""}, responses={"/api/choose": {"main": m_safe, "message": ""}})
    assert out["seen"][0]["asked"] is False and out["calls"] == [["/api/choose", {"id": "act:train"}]]  # 不必敗的：不問、直接打


_REDRAWN_ASK = """return (async () => {
  const mk = () => { const classes = new Set(); return { classes, dataset: { act: "choose", id: "act:train" },
    classList: { add: (...c) => c.forEach((x) => classes.add(x)), remove: (...c) => c.forEach((x) => classes.delete(x)), contains: (c) => classes.has(c) } }; };
  const click = (target) => T.docListeners.click[0]({ target: { closest: () => target } });
  const old = mk(), live = mk();
  T.qs['.ask [data-act="ask-no"]'] = { focus() {} };
  await click(old); // 必敗的遊歷：跳出確認框
  T.qs['[data-act="choose"][data-id="act:train"]'] = live; // 確認框開著時輪詢重畫了頁面：畫面上的遊歷是新的那一顆，old 已經不在頁面上
  T.ctx.fetch = (url, opts) => { T.calls.push([url, JSON.parse(opts.body)]); return new Promise(() => {}); }; // 伺服器還沒回（大場面在判讀）
  click({ dataset: { act: "ask-yes" }, classList: { contains: () => false, add() {}, remove() {} } }); // 「照打」
  await new Promise((resolve) => setTimeout(resolve, 0));
  return { old: [...old.classes], live: [...live.classes], calls: T.calls.map((c) => [c[0], c[1]]) };
})();"""


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_fb095_after_a_redraw_the_busy_mark_lands_on_the_button_on_the_page(on):
    """確認框開著時輪詢重畫了頁面，按「照打」之後「處理中」標在畫面上那一顆遊歷（照 id 重找），不是已經不在頁面上的舊鈕：不然等大場面判讀時
    看不到按鈕在等，伺服器擋下來時也找不到 .busy、灰掉的選項要等下一次輪詢才還原（整合審查 M1）。"""
    game = _camp(on)
    game.state.player.member.wugong_id = None
    m = server.main_view(game)
    assert next(o for o in m["options"] if o["id"] == "act:train")["confirm"]
    out = run(m, _REDRAWN_ASK)
    assert out["calls"] == [["/api/choose", {"id": "act:train"}]]
    assert out["live"] == ["busy"] and out["old"] == []


def _enlist_main(on, faction="guan"):
    """第 2 步的 /api/main：這週只有一道守城軍令（清掉開季的軍令，伺服器帶的 guide.glow 才只有守勢行動那一顆，見 enlist.glow）。"""
    game = _enlisted(on, faction)
    game.state.world.orders = []
    _order(game, "defend", faction, front=front_of(on, JOIN_AT[faction]))
    return server.main_view(game)


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_fb093_the_glow_lands_on_the_defence_button_in_the_page(on):
    """網頁：框上帶 glow（伺服器照 joy 的 enlist.glow 給的選項 id）時，「此地還能做」摺疊打開、applyGlow 給巡哨那顆（data-id）加 glow；
    沒有 glow 的框一個也不加。"""
    m = _enlist_main(on)
    assert m["guide"]["glow"] == ["act:duty"] and any(o["id"] == "act:duty" for o in m["options"])
    html = run(m, "return H.actionBar(m);")
    assert re.search(r'<details class="fold here" open>', html)  # 收著的話按鈕看不到，發光就沒有意義：發光的這一步先打開
    assert re.search(r'data-act="choose" data-id="act:duty" >', html) and "data-glow=\"act:duty\"" not in html  # 認 id，不另寫 data-glow
    script = "const e = T.button('act:duty'); const other = T.button('act:rest'); H.applyGlow(); return [[...e.classes], [...other.classes]];"
    assert run(m, script) == [["glow"], []]
    quiet = {**m, "guide": {k: v for k, v in m["guide"].items() if k != "glow"}}
    assert run(quiet, script) == [[], []]  # 沒有 glow 的框：什麼都不亮（跟序章之外一向一樣）
    assert not re.search(r'<details class="fold here" open>', run(quiet, "return H.actionBar(m);"))


# FB-W1（走查 375×812）：第一道軍令那一步發光的鈕在「此地還能做」摺疊裡，底邊 802、在分頁列（756）底下，框上卻沒有「在下面 ↓」——
# 以前只有序章的框有（pro()）。任何帶 glow 的框（入伍段）發光的東西沒整個露在第一屏裡，都要有；提示框不發光，沒有目標就沒有。
_CUE = """
  const inserted = [];
  T.qs[".card.guide .guide-head"] = { firstElementChild: { insertAdjacentHTML: (pos, html) => inserted.push([pos, html]) }, querySelector: () => null };
  T.qs[".tabs"] = { getBoundingClientRect: () => ({ top: 756 }) };
  const at = (top, bottom, via = "cue") => {
    T.qs["#page .glow"] = { getBoundingClientRect: () => ({ top, bottom }) };
    inserted.length = 0;
    if (via === "cue") H.guideCue(); else { T.button("act:duty"); H.applyGlow(); }
    return inserted.length;
  };
  %s"""


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_fbw1_an_enlistment_box_points_below_when_its_glowing_button_is_cut_off(on):
    m = _enlist_main(on)
    assert m["guide"]["glow"] == ["act:duty"]
    script = _CUE % """return {
      below: at(740, 802), peeking: at(747, 813), onScreen: at(500, 560), touching: at(696, 756),
      viaApplyGlow: at(740, 802, "glow"), html: (at(740, 802), inserted[0]),
      none: (delete T.qs["#page .glow"], inserted.length = 0, H.guideCue(), inserted.length) };"""
    out = run(m, script)
    assert out["below"] == 1 and out["peeking"] == 1 and out["viaApplyGlow"] == 1  # 底邊在分頁列（756）底下：要有
    assert out["onScreen"] == 0 and out["touching"] == 0 and out["none"] == 0  # 整個看得到、或沒有發光的東西：不要
    assert out["html"][0] == "afterend" and 'data-act="guide-below"' in out["html"][1] and "在下面 ↓" in out["html"][1]


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_fbw1_a_box_without_a_glow_never_gets_the_cue(on):
    """提示框、沒有 glow 的入伍框：頁面上就算有別的東西在發光，也不是它們指的。"""
    m = _enlist_main(on)
    quiet = {**m, "guide": {k: v for k, v in m["guide"].items() if k != "glow"}}
    out = run(quiet, _CUE % "return { below: at(740, 802), viaApplyGlow: at(740, 802, 'glow') };")
    assert out == {"below": 0, "viaApplyGlow": 0}
    hint = {**m, "guide": {"key": "h_lose", "speaker": "想起師父說過", "text": "…", "line": "…", "hint": True, "full": True}}
    assert run(hint, _CUE % "return at(740, 802);") == 0
    assert run({**m, "guide": None}, _CUE % "return at(740, 802);") == 0  # 沒有框就沒有地方放


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_fbw1_the_cue_for_an_enlistment_box_is_worked_out_again_on_resize(on):
    m = _enlist_main(on)
    script = """return (async () => {
      const inserted = [];
      T.qs[".card.guide .guide-head"] = { firstElementChild: { insertAdjacentHTML: (pos, html) => inserted.push(html) }, querySelector: () => null };
      T.qs[".tabs"] = { getBoundingClientRect: () => ({ top: 756 }) };
      T.qs["#page .glow"] = { getBoundingClientRect: () => ({ top: 740, bottom: 802 }) };
      (T.listeners.resize || []).forEach((fn) => fn());
      await new Promise((resolve) => setTimeout(resolve, 400));
      return inserted.length;
    })();"""
    assert run(m, script) == 1


# ── 審查之後的最後一輪（review-fb.md、fb-fix-brief.md）──────────────────────────────────────────────
# 老石結語不說沒發生的事。（第 2 步多的那一句與「做得了」的判斷跟著 FB-093 拿掉了：joy 的版本由引薦人的 order_hint 點名守勢
# 行動、軍令卡寫怎麼做；火的提醒跟著 FB-092 拿掉了；「守勢行動只記一次」釘的是我們的 or_actions，跟著 FB-094 換成 joy 的 _duty。）


def test_fbx_the_ending_does_not_claim_a_last_action_was_counted(on):
    """老石的結語寫過「你剛剛那一下，也算在裡頭」，可是守勢行動沒有軍令可記、或一週到了什麼都沒做就收段時，沒有什麼被記進去
    （審查 Minor 2）。三位的結語都不說這種事。"""
    for faction, who in on.tutorial.enlist.recruiters.items():
        assert "剛剛" not in who.done and "也算在裡頭" not in who.done, faction
        assert "陣營" in who.done, faction  # 卡片上「陣營 幾／幾」是什麼意思還講
    game = _enlisted(on, "guan")
    game.choose("act:duty")  # 這一週沒有守城軍令：巡哨替誰都沒記
    box = _finished(game, on)
    assert "也算在裡頭" not in box["text"]
