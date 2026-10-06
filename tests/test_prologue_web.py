"""序章的網頁（新手引導計畫一 Task 6）：畫面一步一步亮起來、要按的鈕發光、對話框、略過與重看序章。
web/app.js 沒有建置步驟、也沒有前端測試框架：這裡把整支 app.js 放進 node 的假瀏覽器（只有 document、localStorage、fetch 的假貨），
最後一行啟動的呼叫換成「把要測的函式交出來」，餵它**真的**引擎給的 /api/main 與 /api/menxia 內容（序章測試內容，走到每一步），
檢查畫出來的 HTML 與發光的鈕。沒有 node 就略過。沒有瀏覽器可開，這是瀏覽器驗收那一步（手機寬度 375 的排版另看）的替身：
驗的是「哪一步畫什麼、藏什麼、哪顆鈕發光」，不是長相。"""
from __future__ import annotations

import json
import random
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from test_prologue import _to_step

import server
from tianxia import prologue
from tianxia.engine import Game

ROOT = Path(__file__).parent.parent
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="沒有 node，前端畫面測試略過")

DRIVER = r"""
const fs = require("fs"), vm = require("vm");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
let src = fs.readFileSync(input.app, "utf8").replace(/\r\n/g, "\n"); // Windows 的 checkout 是 CRLF
const end = src.lastIndexOf("\n})();");
if (end < 0) throw new Error("app.js 的最後不是 })();");
src = src.slice(0, end) + `
  globalThis.__H = { S, pro, shown, prologueKey, topHtml, tabsHtml, idleMenu, actionBar, guideHtml, pageJianghu, pagePractice,
    pageCraft, peekBlock, sheetHtml, applyGlow, renderTop, render, goTab };
` + src.slice(end);

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
// applyGlow 用的假元素：{ glow: ["鍵", ...], disabled, classes: Set }。只認 applyGlow 會問的三種選擇器
const fake = { list: [] };
const el = (glow, disabled = false) => {
  const e = { glow, disabled, classes: new Set() };
  e.classList = { add: (...c) => c.forEach((x) => e.classes.add(x)), remove: (...c) => c.forEach((x) => e.classes.delete(x)), contains: (c) => e.classes.has(c) };
  fake.list.push(e);
  return e;
};
const matchOne = (e, sel) => {
  if (sel === ".glow") return e.classes.has("glow");
  if (sel === ".lit") return e.classes.has("lit");
  const m = sel.match(/^\[data-glow~="(.*)"\](:not\(\[disabled\]\))?$/);
  if (!m) throw new Error("假 DOM 不認得的選擇器：" + sel);
  return e.glow.includes(m[1]) && !(m[2] && e.disabled);
};
const document = {
  getElementById: (id) => (["app", "toast", "page", "top", "peek"].includes(id) ? mk(id) : null),
  querySelector: () => null,
  querySelectorAll: (sel) => fake.list.filter((e) => sel.split(", ").some((one) => matchOne(e, one))),
  addEventListener() {}, activeElement: null, hidden: false,
  // splitChips 把「剛剛」丟進 <template> 拆出數值變化那一排：假的 template 原樣吐回去、沒有那一排
  createElement: () => ({ innerHTML: "", content: { querySelector: () => null } }),
};
const ctx = {
  document, window: { addEventListener() {}, scrollTo() {}, innerWidth: 375 }, fetch: fetchStub,
  localStorage: { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => { store.set(k, String(v)); }, removeItem: (k) => { store.delete(k); } },
  setInterval() {}, setTimeout, clearTimeout, performance, console, confirm: () => true, navigator: {}, CSS: { escape: (x) => x },
  requestAnimationFrame: () => 0, Element: class {},
};
for (const [k, v] of Object.entries(input.stored || {})) store.set(k, v);
vm.createContext(ctx);
vm.runInContext(src, ctx);
const H = ctx.__H;
H.S.stage = "game";
H.S.main = input.m;
H.S.menxia = input.menxia || null;
Object.assign(H.S, input.S || {});
// script 可以是 async（回傳 Promise）：等它做完再印
Promise.resolve(new Function("H", "m", "T", input.script)(H, input.m, { els, fake, el, calls })).then((out) => {
  process.stdout.write(JSON.stringify(out === undefined ? null : out));
});
"""


def run(m, script, *, S=None, menxia=None, stored=None, responses=None):
    """在 node 裡跑 app.js：m 是 /api/main 回的那份（S.main）、menxia 是 /api/menxia 回的那份，script 是函式本體（可用 H、m、T；
    要等網路的寫成 async，fetch 是假的：T.calls 記下問了什麼，responses 是「網址開頭 → 回的 JSON」）。"""
    done = subprocess.run(
        [NODE, "-e", DRIVER], capture_output=True, text=True, encoding="utf-8", timeout=60,
        input=json.dumps({
            "app": str(ROOT / "web" / "app.js"), "m": m, "script": script, "S": S or {}, "menxia": menxia, "stored": stored or {},
            "responses": responses or {},
        }),
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


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


def chip_ids(html):
    return re.findall(r'class="peek-chip (\w+)', html)


STANCES = {"guan": 40, "huang": 30, "haoqiang": 20}
BULLETIN = ["<p><strong>甲事</strong></p>"]
FRONTS = [{"name": "潁川", "value": 40, "chaos": False}]
ORDERS = [{"title": "守關", "text": "守住", "progress": 1, "quota": 5, "done": False, "mine": 0, "deadline": "週五"}]


def season_one_view(m):
    """序章裡通常沒有的東西全放進去，才看得出是哪一步把它們藏起來、哪一步放出來。"""
    status = {**m["status"], "stances": STANCES, "stance_notes": {}, "stance_rule": "規則"}
    return {**m, "status": status, "bulletin": BULLETIN, "quest": "<p>QUESTMARK</p>", "fronts": FRONTS, "orders": ORDERS,
            "minimap": "<svg>MINIMAP</svg>"}


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
    assert "repeat(2, 1fr)" in tabs and 'data-glow="tab:practice"' in tabs
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
    assert [s["tabs"] for s in seen[:5]] == [[], ["jianghu", "practice"], ["jianghu", "practice"], ["jianghu", "practice", "craft"], ["jianghu", "practice", "craft"]]
    assert seen[1]["vitals"] == ["xinde"] and seen[2]["vitals"] == ["stamina", "xinde"]
    assert seen[2]["cells"] == ["explore"] and seen[6]["cells"] == ["explore", "rest"]
    assert seen[7]["cells"] == ["explore", "train", "rest"] and seen[7]["vitals"] == ["stamina", "hp", "xinde"]
    assert [s["toggle"] for s in seen] == [False] * 8 + [True] * 3  # 屬性（配點）從第 9 步才點得開
    for before, after in zip(seen, seen[1:]):  # 亮起來的不會再暗回去
        assert set(before["tabs"]) <= set(after["tabs"]) and set(before["cells"]) <= set(after["cells"])


def test_the_farewell_step_lights_everything_and_the_menu_is_only_the_walk(hut):
    m = main_at(hut, 10)
    out = run(m, "return { tabs: H.tabsHtml(), page: H.pageJianghu(), top: H.topHtml() };")
    assert re.findall(r'data-tab="(\w+)"', out["tabs"]) == ["jianghu", "practice", "craft", "map", "news"]
    cells = {key: cls for cls, key in re.findall(r'class="act-ink([^"]*)" data-key="(\w+)"', out["page"])}
    assert sorted(cells) == ["explore", "move", "rest", "social", "train"]
    assert " off" in cells["explore"] and " off" not in cells["move"]  # 只有走出草廬按得下去
    assert 'data-glow="act:move"' in out["page"] and "<em>銀</em>" in out["top"]


def test_after_the_prologue_the_ordinary_screen_comes_back(hut, content):
    plain = Game.new(content, "路人", rng=random.Random(0))
    m = server.main_view(plain)
    assert m["prologue"] is None
    out = run(m, "return { tabs: H.tabsHtml(), top: H.topHtml(), shown: H.shown('tab:map') && H.shown('board') && H.shown('act:move') };")
    assert re.findall(r'data-tab="(\w+)"', out["tabs"]) == ["jianghu", "practice", "craft", "map", "news"] and out["shown"] is True
    assert "第 " in out["top"] and "toggle-more" in out["top"]  # 平常的狀態列：日期、點名號展開


# ── 態勢｜大事｜主線 三塊小標 ────────────────────────────

@pytest.mark.parametrize("reveal, expected", [
    ([], []),
    (["xinde", "tab:practice"], []),  # 別的鍵不管用
    (["board"], ["board"]),
    (["stances"], ["stance"]),
    (["quest"], ["quest"]),
    (["stances", "board"], ["stance", "board"]),  # 態勢跟大事一起亮
    (["stances", "board", "quest"], ["stance", "board", "quest"]),
    (["all"], ["stance", "board", "quest"]),
])
def test_each_chip_shows_only_when_its_own_key_is_revealed(hut, reveal, expected):
    m = with_reveal(season_one_view(main_at(hut, 1)), reveal)
    assert chip_ids(run(m, "return H.peekBlock(m);")) == expected


def test_with_all_three_chips_hidden_there_is_no_row_at_all(hut):
    m = with_reveal(season_one_view(main_at(hut, 1)), ["xinde"])
    html = run(m, "return H.peekBlock(m);")
    assert html == "" and "peek" not in run(m, "return H.pageJianghu();")


def test_the_chips_come_back_at_the_farewell_step(newcomer):
    m = season_one_view(main_at(newcomer(), 10))
    assert chip_ids(run(m, "return H.peekBlock(m);")) == ["stance", "board", "quest"]
    early = season_one_view(main_at(newcomer(), 5))  # 序章中途（修練那一步）：三塊都還藏著
    assert chip_ids(run(early, "return H.peekBlock(m);")) == []


def test_the_chips_are_all_there_outside_the_prologue(content):
    plain = season_one_view(server.main_view(Game.new(content, "路人", rng=random.Random(0))))
    assert chip_ids(run(plain, "return H.peekBlock(m);")) == ["stance", "board", "quest"]


# ── 江湖頁其他的塊 ───────────────────────────────────

def test_fronts_orders_and_the_minimap_wait_for_their_keys(hut):
    m = season_one_view(main_at(hut, 3))
    hidden = run(m, "return H.pageJianghu();")
    assert "fronts" not in hidden and "orders" not in hidden and "MINIMAP" not in hidden and "看江湖紀錄" not in hidden
    for key, mark in (("fronts", 'class="fronts"'), ("orders", "本週軍令"), ("minimap", "MINIMAP")):
        lit = run(with_reveal(m, [*m["prologue"]["reveal"], key]), "return H.pageJianghu();")
        assert mark in lit, key
    assert all(mark in run(with_reveal(m, ["all"]), "return H.pageJianghu();") for mark in ('class="fronts"', "本週軍令", "MINIMAP", "看江湖紀錄"))


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
    (True, ["act:on_road", "road:back"], True, False),  # 出師那段路上：路上的選單
    (False, ["act:explore"], False, False),  # 序章外沒有打坐的選單不是閒著（對話、事件、決戰）
    (False, ["act:explore", "act:rest"], False, True),
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
    m = main_at(hut, 2)  # 探索那一步：glow ["act:explore"]
    assert m["prologue"]["glow"] == ["act:explore"]
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
    (["stamina", "hp", "silver", "xinde"], ["stamina", "hp", "silver", "xinde"]),
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
      return [same, T.els.app.innerHTML.includes('data-tab="craft"'), H.S.prologueKey];""" % json.dumps(with_reveal(m, ["xinde", "tab:practice", "tab:craft"])))
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


def test_a_shut_box_shows_the_short_line_and_remembers_the_text(hut):
    g = main_at(hut, 1)["guide"]  # line："師父：看修練頁"
    assert g["line"] == "師父：看修練頁"
    html = run({"guide": g}, "return H.guideHtml(m.guide, false);", stored={"tx-guide-shut": g["text"]})
    assert "師父</b>：師父：看修練頁" in html  # 收起來那一行用 line
    longer = run({"guide": {**g, "line": ""}}, "return H.guideHtml(m.guide, false);", stored={"tx-guide-shut": g["text"]})
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
        assert page.index("guide") < page.index('id="mx-msg"') and "把【穿林腿】換上，練到第三成。" in page
    plain = run({**m, "prologue": None}, "return H.pagePractice();", menxia=x)
    assert 'class="card guide"' not in plain  # 序章外的修練頁沒有師父


def test_the_practice_page_points_at_the_buttons_of_the_step(hut):
    m, x = pages_at(hut, 4)  # 換上、練到第三成：練成鈕發光，合成出來的那一列（還沒換上）發光
    page = run(m, "return H.pagePractice();", menxia=x)
    assert re.search(r'data-op="practice" data-glow="practice"', page)
    rows = dict(re.findall(r'data-act="art" data-id="(\w+)"( data-glow="[^"]*")?', page))
    fused = next(k for k in rows if k not in ("basic_fist", "basic_breath"))
    assert rows[fused] == ' data-glow="switch"' and rows["basic_fist"] == "" and rows["basic_breath"] == ""
    m, x = pages_at(hut, 5)  # 修練那一步：合成出來的那一門換上了，它的列發光
    page = run(m, "return H.pagePractice();", menxia=x)
    assert 'data-glow="cultivate"' in page


def test_the_practice_button_is_greyed_with_the_masters_reason(hut):
    m, x = pages_at(hut, 1)  # 看修練頁那一步：沒叫你練功
    page = run(m, "return H.pagePractice();", menxia=x)
    assert re.search(r'data-op="practice" data-glow="practice" disabled>師父這一步沒叫你練功。', page)
    m, x = pages_at(hut, 4)
    hut.switch_art(prologue.fused_arts(hut.state, hut.content, hut.world)[0].id)
    x = server.menxia_view(hut)
    page = run(server.main_view(hut), "return H.pagePractice();", menxia=x)  # 換上了：武學那一欄練得下去
    assert re.search(r'data-op="practice" data-glow="practice" >練成武學（心得', page)


def test_the_seclusion_form_and_the_insight_melt_are_greyed_in_the_hut(hut):
    """T6 review M4、M7：草廬裡不閉關、不熔意境。按鈕灰掉、寫師父的原因（跟練成鈕同一個做法），不是亮著按了才被擋。"""
    m, x = pages_at(hut, 3)
    assert x["seclude_blocked"] and x["insights"][0]["blocked"]
    page = run(m, "return H.pagePractice();", menxia=x)
    assert re.search(r'<button class="btn small" type="submit" disabled>開始閉關</button>', page) and x["seclude_blocked"] in page
    assert re.search(r'data-act="melt-insight"[^>]*disabled', page) and x["insights"][0]["blocked"] in page
    out = Game.new(hut.content, "路人", rng=random.Random(0), world=hut.world)
    out.state.player.insights.append("feng")
    x = server.menxia_view(out)
    page = run(server.main_view(out), "return H.pagePractice();", menxia=x)
    assert x["seclude_blocked"] is None and 'type="submit" disabled' not in page
    assert not re.search(r'data-act="melt-insight"[^>]*disabled', page)


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
