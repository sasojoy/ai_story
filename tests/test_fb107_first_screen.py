"""FB-107（QA 93e7037，2026-10-08，375×812）：師父「碰到才說」的框、兩行的 💡、決戰集結（戰場、「此地還有」、結伴）在畫面上時，
行動列掉到分頁列底下。企劃者 10/5：框留在行動列上面、話不切。

網頁現在畫好之後量一次（web/app.js 的 fitFirstScreen）：行動列（一組選項時是最後一顆）的下緣離分頁列不到 FIT_MARGIN，就照
FIT_STEPS 的順序一步一步收，放得下就停——放得下的畫面一點都不動。順序：間距 → 框收緊（話不切）→ 💡 收成一行 → 戰鬥卡片底下的補充
收成一行 → 第一回合收進「展開過程」→「剛剛」只露三行 → 決戰時所在地的描述收成一行 → 集結那一句收成一行 → 一組選項的鈕縫與鈕高。
每一樣點得開；「得失」與結果那幾行、框裡的話不收。

這裡把那幾個函式從 app.js 切出來，在 node 裡接一個假的頁面跑：假頁面的行動列下緣照「哪幾個元素身上掛了哪個 class」算（每一樣省多少 px
寫在 SAVE），量的是收的順序、停在哪、點開過的不收、重量之前先還原、在路上與序章不收。真的 px 是 375×812 估出來的（fix-1008 的交接報告）。
樣式另外釘住：每一步只動它該動的東西。"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import server
import webharness

ROOT = Path(__file__).parent.parent
node = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")

DRIVER = r"""
// 從 app.js 切出 FB-107 那一段（FIT_MARGIN 到 ownOpen 之前，加上 ownOpen 本身）
const head = src.indexOf("\n  const FIT_MARGIN"), tail = src.indexOf("\n  function ownOpen(");
if (head < 0 || tail < 0) throw new Error("app.js 裡找不到 FB-107 那一段");
const code = src.slice(head, tail) + fn("ownOpen");

// 假的頁面：每個元素是 { kind, classes, attrs, dataset, ... }；選擇器照 app.js 用到的那幾個寫成判斷式
const all = [];
const el = (kind, classes = [], extra = {}) => {
  const e = { kind, classes: new Set(classes), attrs: {}, dataset: {}, ...extra };
  e.classList = {
    add: (...c) => c.forEach((x) => e.classes.add(x)), remove: (...c) => c.forEach((x) => e.classes.delete(x)),
    contains: (c) => e.classes.has(c), toggle: (c, on) => (on ?? !e.classes.has(c)) ? e.classes.add(c) : e.classes.delete(c),
    replace: (a, b) => { if (!e.classes.has(a)) return false; e.classes.delete(a); e.classes.add(b); return true; },
  };
  e.setAttribute = (k, v) => { e.attrs[k] = String(v); };
  e.removeAttribute = (k) => { delete e.attrs[k]; };
  all.push(e);
  return e;
};
const has = (e, ...c) => c.every((x) => e.classes.has(x));
const L = input.layout;
const page = el("page", ["page"]);
const tabs = el("tabs", ["tabs"]);
const actbar = L.actbar ? el("actbar", ["act-bar"]) : null;
const menu = L.options ? el("options", ["options"]) : null;
const last = L.options ? el("button", ["btn"]) : null;
const card = L.card ? el("card", ["card", "battle-card"]) : null;
const lines = (L.lines || []).map((h) => el("line", h ? ["tx-line", "tx-hearsay"] : ["tx-line"]));
const rounds = L.rounds ? el("rounds", L.roundsOpen ? ["rounds", "open"] : ["rounds"]) : null;
const now = L.now ? el("now", ["now", L.nowFits ? "fits" : "clamp"].concat(L.nowOpen ? ["open"] : [])) : null;
const body = L.now ? el("body", ["tx-now"]) : null;
const scene = L.scene ? el("scene", ["card", "scene"]) : null;
const box = L.box ? el("box", ["card", "guide"]) : null;
const hint = L.hint ? el("hint", ["hint"]) : null;  // 狀態列的 💡（#top 裡）；收成一行看的是 S.hintTight（renderTop 照它畫）
// 狀態列（#top）的高度（FB-123）：input.topHeight；input.realTop 時 renderTop 照真的那樣先量高度、重畫（💡 收成一行時矮 input.topSaves）、
// 再交給 fitTopMoved
const topEl = { offsetHeight: input.topHeight || 120 };
let tops = 0, HH = null;
const renderTop = () => {
  tops += 1;
  if (!input.realTop) return;
  const before = topEl.offsetHeight;
  topEl.offsetHeight = (input.topHeight || 120) - (S.hintTight && !S.hintOpen ? input.topSaves || 20 : 0);
  HH.fitTopMoved(before);
};
// 場景卡：加入的鈕在名字那一行時（L.join 不是 false）名字包在 muster-head 裡；沒有鈕時名字是場景卡第一個 <p>
const T = L.texts || {};
const mhead = L.muster && L.join !== false ? el("head", ["muster-head"], { tagName: "DIV" }) : null;
const title = L.hr && !mhead ? el("title", [], { tagName: "P", text: "廣宗決戰" }) : null;
const musterLines = (L.muster || 0) ? Array.from({ length: L.muster }, (_, i) => el("musterp", [], { tagName: "P", text: (T.muster || [])[i] || "" })) : [];
const hr = L.hr ? el("hr", [], { tagName: "HR" }) : null;
const own = (L.own || 0) ? Array.from({ length: L.own }, (_, i) => el("ownp", [], { tagName: "P", text: (T.own || [])[i] || "" })) : [];
lines.forEach((x, i) => { x.text = (T.lines || [])[i] || ""; });
// 場景卡的順序：名字那一行（muster-head 或名字那一段）、集結那一句、分隔線、所在地
const order = [mhead || title, ...musterLines, hr, ...own].filter(Boolean);
order.forEach((e, i) => { e.nextElementSibling = order[i + 1] || null; });
// 每一樣收起來省多少 px（假的；真的看 375×812 估的數字）
const SAVE = Object.assign({ space: 30, cardSpace: 6, box: 22, hint: 20, line: 20, rounds: 23, own: 27, muster: 27, options: 22 }, input.save || {});
const bodyHeight = () => (now && has(now, "fit-short") ? Math.min(L.nowBody, 72) : Math.min(L.nowBody || 0, 120));
const bottom = () => {
  let b = L.bottom;
  if (has(page, "fit-space")) b -= SAVE.space;
  if (card && has(card, "fit-space")) b -= SAVE.cardSpace;
  if (box && has(box, "fit-box")) b -= SAVE.box;
  if (hint && S.hintTight && !S.hintOpen) b -= SAVE.hint;
  lines.forEach((x) => { if (has(x, "tx-tight") && !has(x, "open")) b -= SAVE.line; });
  if (rounds && has(rounds, "fit-fold") && !has(rounds, "open")) b -= SAVE.rounds;
  if (now) b -= Math.min(L.nowBody || 0, 120) - bodyHeight();
  if (own.some((p) => has(p, "fit-clip"))) b -= SAVE.own;
  if (musterLines.some((p) => has(p, "fit-clip"))) b -= SAVE.muster;
  if (menu && has(menu, "fit-tight")) b -= SAVE.options;
  return b;
};
const target = actbar || last;
// 畫面上的位置＝頁面上的位置 − 捲了多少（分頁列固定在畫面底下）
if (target) target.getBoundingClientRect = () => ({ bottom: bottom() - globalThis.window.scrollY });
// 分頁列頂：手機網址列收起時分頁列跟著往下（FB-123），測試用 els.setTabsTop 換
let tabsTop = input.tabsTop || 756;
tabs.getBoundingClientRect = () => ({ top: tabsTop });
if (body) Object.defineProperty(body, "scrollHeight", { get: () => L.nowBody });
if (body) Object.defineProperty(body, "clientHeight", { get: () => bodyHeight() });
const where = {
  "#page > .act-bar": () => (actbar ? [actbar] : []),
  "#page > .options > :last-child": () => (last ? [last] : []),
  ".tabs": () => [tabs],
  "#page > .battle-card": () => (card ? [card] : []),
  ".battle-card .tx-extra .tx-line:not(.tx-hearsay)": () => lines.filter((x) => !has(x, "tx-hearsay")),
  ".battle-card ul.rounds:not(.open), .battle-card p.rounds-tale:not(.open)": () => (rounds && !has(rounds, "open") ? [rounds] : []),
  "#page > .now:not(.open)": () => (now && !has(now, "open") ? [now] : []),
  "#page > .card.scene:not(.road)": () => (scene ? [scene] : []),
  "#page > .options": () => (menu ? [menu] : []),
  "#page > .card.guide": () => (box ? [box] : []),
  "#top .more-stats .hint": () => (hint ? [hint] : []),
  ".fit-space": () => all.filter((x) => x !== page && has(x, "fit-space")),
  ".fit-box": () => all.filter((x) => has(x, "fit-box")),
  ".tx-tight": () => all.filter((x) => has(x, "tx-tight")),
  ".fit-fold": () => all.filter((x) => has(x, "fit-fold")),
  ".now.fit-short": () => all.filter((x) => has(x, "now", "fit-short")),
  ".fit-own, .fit-muster": () => all.filter((x) => has(x, "fit-own") || has(x, "fit-muster")),
  ".fit-clip": () => all.filter((x) => has(x, "fit-clip")),
  ".fit-tight": () => all.filter((x) => has(x, "fit-tight")),
};
const q = (sel) => { if (!where[sel]) throw new Error("假頁面不認得的選擇器：" + sel); return where[sel](); };
globalThis.document = { getElementById: (id) => (id === "page" && L.page !== false ? page : id === "top" ? topEl : null),
  querySelector: (s) => q(s)[0] || null, querySelectorAll: q, activeElement: null };
globalThis.window = { scrollY: input.scrollY || 0, innerWidth: input.width || 375 };
// 量數字露不露得出來（input.measure）：每個字 15px 寬、一行 300px，「…」佔 1em（15px）——第 19 個字以後的數字就藏起來了。
// 沒給就跟沒有 Range 的瀏覽器一樣（fitDigitsShown 當看得到）
if (input.measure) {
  document.createTreeWalker = (e) => { let done = false; return { nextNode: () => (done ? null : (done = true, { data: e.text || "" })) }; };
  document.createRange = () => ({ setStart(n, i) { this.i = i; }, setEnd() {}, getBoundingClientRect() { return { right: (this.i + 1) * 15 }; } });
  globalThis.getComputedStyle = () => ({ fontSize: "15px" });
  [...lines, ...musterLines, ...own].forEach((x) => { x.getBoundingClientRect = () => ({ right: 300 }); });
}
page.querySelectorAll = q;
if (now) now.querySelector = (s) => (s === ".tx-now" ? body : null);
if (scene) {
  scene.querySelector = (s) => (s === ":scope > hr" ? hr : s === ":scope > .muster-head" ? mhead
    : s === ":scope > p" ? (mhead ? musterLines[0] || null : title) : null);
  scene.querySelectorAll = (s) => (s === ":scope > hr ~ p" && hr ? own : s === ".fit-clip" ? all.filter((x) => has(x, "fit-clip")) : []);
}
const S = Object.assign({ stage: "game", tab: "jianghu", hearOpen: null, linesOpen: null, ownOpen: null, hintTight: false, hintOpen: false,
  fitWidth: 0, main: { card_id: 7, scene: "<p>x</p>", on_road: false } }, input.S || {});
const pro = () => input.pro || null;
const idleMenu = () => input.idle !== false;
const H = new Function("S", "pro", "idleMenu", "renderTop", code
  + "\nreturn { fitFirstScreen, fitOver, ownOpen, fitOwnKey, fitOnResize, fitTopMoved, lineToggle, FIT_STEPS };")(S, pro, idleMenu, renderTop);
HH = H;
const snap = () => ({
  fitted: S.fitted, bottom: bottom(), page: [...page.classes].sort(), card: card ? [...card.classes].sort() : null,
  box: box ? [...box.classes].sort() : null, hintTight: S.hintTight, tops, hearOpen: S.hearOpen, linesOpen: S.linesOpen,
  lines: lines.map((x) => [...x.classes].sort()), lineAttrs: lines.map((x) => x.attrs), rounds: rounds ? [...rounds.classes].sort() : null,
  now: now ? [...now.classes].sort() : null, scene: scene ? [...scene.classes].sort() : null, own: own.map((x) => x.attrs),
  ownClip: own.map((x) => has(x, "fit-clip")), musterClip: musterLines.map((x) => has(x, "fit-clip")),
  musterAttrs: musterLines.map((x) => x.attrs), menu: menu ? [...menu.classes].sort() : null,
});
finish(new Function("H", "S", "snap", "L", "W", "els", input.script || "H.fitFirstScreen(); return snap();")(
  H, S, snap, L, globalThis.window, { lines, top: topEl, setTabsTop: (v) => { tabsTop = v; } }));
"""


def run(layout, script=None, **extra):
    return webharness.run(DRIVER, {"layout": layout, "script": script, **extra})


# 打完一場、框在畫面上：戰鬥卡片（對手描述一行、第一回合）、場景、行動列
FIGHT = {"bottom": 814, "actbar": True, "card": True, "lines": [False], "rounds": True, "scene": True}


# ── 收的順序、停在哪 ─────────────────────────────────


@node
def test_a_page_that_fits_is_left_alone():
    """行動列下緣在分頁列上面 FIT_MARGIN 以內：什麼都不收（沒有框、放得下的時候畫面一個 px 都不動）。"""
    out = run({**FIGHT, "bottom": 740})
    assert out["fitted"] == [] and out["page"] == ["page"] and out["card"] == ["battle-card", "card"]
    assert out["lines"] == [["tx-line"]] and out["rounds"] == ["rounds"] and out["lineAttrs"] == [{}]


@node
def test_it_folds_step_by_step_and_stops_as_soon_as_the_row_fits():
    """756 − 16 = 740。差 50：間距（30＋卡片 6）不夠，再收對手的描述（20）就夠了——第一回合不收。"""
    out = run({**FIGHT, "bottom": 790})
    assert out["fitted"] == ["space", "lines"] and out["bottom"] <= 740
    assert "fit-space" in out["page"] and "fit-space" in out["card"]
    assert out["lines"] == [["tx-line", "tx-tight"]] and out["lineAttrs"][0]["data-act"] == "line-more"  # 點得開（自己的開合，審查 M5）
    assert out["rounds"] == ["rounds"]


@node
def test_a_scrolled_page_is_measured_from_the_top():
    """量的是捲回最上面時行動列在哪（畫面上的位置＋捲了多少）：捲下去 100px、行動列在畫面上的 700，頁面上是 800——照樣要收。"""
    out = run({**FIGHT, "bottom": 800}, scrollY=100)
    assert out["fitted"][:2] == ["space", "lines"] and out["bottom"] <= 740


@node
def test_with_a_box_up_the_battle_card_goes_to_its_short_form():
    """打完一場、框在畫面上（QA 量過 814～842 的那幾種）：間距、框收緊、描述、第一回合依序收；第一回合收進「展開過程」。"""
    out = run({**FIGHT, "box": True, "bottom": 840})
    assert out["fitted"] == ["space", "box", "lines", "rounds"] and out["bottom"] <= 740
    assert "fit-fold" in out["rounds"] and "fit-box" in out["box"]


@node
def test_the_box_is_tightened_before_anything_is_folded():
    """框收緊（「知道了」不撐高標題那一行、行高小一點）不少任何字：排在間距之後、任何收起來的東西之前。"""
    out = run({**FIGHT, "box": True, "bottom": 790})
    assert out["fitted"] == ["space", "box"] and out["lines"] == [["tx-line"]] and out["rounds"] == ["rounds"]


@node
def test_a_two_line_hint_folds_to_one_line_and_comes_back_when_there_is_room():
    """💡 在狀態列（另外畫，renderTop）：要收時記 S.hintTight、重畫狀態列；之後有空間了重量時還原、再重畫一次。"""
    layout = {"bottom": 790, "actbar": True, "scene": True, "hint": True, "card": True, "lines": [False], "rounds": True}
    script = """
      H.fitFirstScreen(); const tight = snap();
      L.bottom = 700; H.fitFirstScreen(); const roomy = snap();
      return { tight, roomy };"""
    out = run(layout, script)
    assert out["tight"]["fitted"] == ["space", "hint"] and out["tight"]["hintTight"] is True and out["tight"]["tops"] == 1
    assert out["roomy"]["fitted"] == [] and out["roomy"]["hintTight"] is False and out["roomy"]["tops"] == 2


@node
def test_a_hint_the_player_opened_stays_open():
    out = run({"bottom": 790, "actbar": True, "scene": True, "hint": True}, S={"hintTight": True, "hintOpen": True})
    assert "hint" not in out["fitted"] and out["hintTight"] is True and out["tops"] == 0


@node
def test_the_short_form_expands_fully_and_stays_open():
    """玩家按了「展開過程」（ul 掛 open）、點開過補充（S.linesOpen 是這一場）：重畫之後不再收回去，其他步驟照樣收。"""
    out = run({**FIGHT, "rounds": True, "roundsOpen": True}, S={"linesOpen": 7})
    assert "lines" not in out["fitted"] and "rounds" not in out["fitted"]
    assert out["rounds"] == ["open", "rounds"] and out["lines"] == [["tx-line"]]


@node
def test_the_description_and_the_hearsay_line_open_separately():
    """對手的描述與聽來的那一句各記各的（審查 M5）：點開描述不會讓聽來的那一句跟著攤開；攤開過聽來的那一句，描述照樣收。"""
    out = run(FIGHT, "H.fitFirstScreen(); H.lineToggle(els.lines[0]); return snap();")
    assert out["linesOpen"] == 7 and out["hearOpen"] is None and out["lines"] == [["open", "tx-line", "tx-tight"]]
    heard = run(FIGHT, S={"hearOpen": 7})
    assert "lines" in heard["fitted"] and heard["lines"] == [["tx-line", "tx-tight"]]
    again = run(FIGHT, S={"linesOpen": 6})  # 攤開的是上一場：這一場照樣收
    assert "lines" in again["fitted"]


@node
def test_a_line_whose_numbers_would_hide_behind_the_ellipsis_is_not_folded():
    """收成一行之後數字會藏到「…」後面的那一行不收（例如以後多一行「江湖大事：…戰局 62」）；數字在前面的照收。"""
    texts = {"lines": ["（偷網賊：趁漁家不在偷收漁網的毛賊，滑得像泥鰍，一見人就往水裡鑽，還說他偷過 3 張網。）"]}
    out = run({**FIGHT, "texts": texts}, measure=True)
    assert "lines" not in out["fitted"] and out["lines"] == [["tx-line"]] and out["lineAttrs"] == [{}]
    plain = run({**FIGHT, "texts": {"lines": ["（偷網賊：趁漁家不在偷收漁網的毛賊，滑得像泥鰍，一見人就往水裡鑽。）"]}}, measure=True)
    assert "lines" in plain["fitted"]


@node
def test_refitting_starts_from_the_unfolded_page():
    """轉向、拉視窗之後重量：先把自己加的全部拿掉再量，空間變大就少收。"""
    script = """
      H.fitFirstScreen(); const before = snap();
      L.bottom = 760; H.fitFirstScreen(); const after = snap();
      L.bottom = 700; H.fitFirstScreen(); const roomy = snap();
      return { before, after, roomy };"""
    out = run(FIGHT, script)
    assert out["before"]["fitted"] == ["space", "lines", "rounds"]
    assert out["after"]["fitted"] == ["space"] and out["after"]["rounds"] == ["rounds"] and out["after"]["lines"] == [["tx-line"]]
    assert out["after"]["lineAttrs"] == [{}]  # 收成一行時加的 data-act 等也拿掉
    assert out["roomy"]["fitted"] == [] and out["roomy"]["page"] == ["page"] and "fit-space" not in out["roomy"]["card"]


@node
def test_the_now_card_shows_three_lines_and_keeps_its_more_button():
    """「剛剛」（不是戰鬥卡片）：收著時只露三行；本來放得下（fits，八行以內）、三行放不下的，換回收著（有「展開全文」）。"""
    out = run({"bottom": 820, "actbar": True, "now": True, "nowFits": True, "nowBody": 110, "scene": True})
    assert out["fitted"][:2] == ["space", "now"] and "fit-short" in out["now"] and "clamp" in out["now"] and "fits" not in out["now"]
    short = run({"bottom": 820, "actbar": True, "now": True, "nowFits": True, "nowBody": 60, "scene": True})
    assert "fit-short" in short["now"] and "fits" in short["now"]  # 三行就放得下：不淡出、沒有「展開全文」
    opened = run({"bottom": 820, "actbar": True, "now": True, "nowOpen": True, "nowBody": 110, "scene": True})
    assert "now" not in opened["fitted"] and "fit-short" not in opened["now"]  # 玩家展開了：不收


@node
def test_the_location_under_a_battle_folds_only_when_idle():
    """決戰時場景卡在戰場底下接著所在地（分隔線之後）：閒著時每段收成一行、點得開；有事件、有所感時那是 joy 的字，不收。"""
    layout = {"bottom": 800, "actbar": True, "scene": True, "hr": True, "own": 2}
    out = run(layout)
    assert "own" in out["fitted"] and "fit-own" in out["scene"] and out["ownClip"] == [True, True]
    assert all(a == {"data-act": "own-more", "role": "button", "tabindex": "0", "aria-expanded": "false"} for a in out["own"])
    event = run(layout, idle=False)
    assert "own" not in event["fitted"] and "fit-own" not in event["scene"] and event["ownClip"] == [False, False]
    no_battle = run({**layout, "hr": False})
    assert "own" not in no_battle["fitted"]
    opened = run(layout, "H.fitFirstScreen(); H.ownOpen(); return { s: snap(), open: S.ownOpen, key: H.fitOwnKey() };")
    assert "fit-own" not in opened["s"]["scene"] and opened["s"]["ownClip"] == [False, False] and opened["open"] == opened["key"]
    assert opened["s"]["own"] == [{}, {}]
    again = run(layout, "S.ownOpen = H.fitOwnKey(); H.fitFirstScreen(); return snap();")
    assert "own" not in again["fitted"]  # 攤開過的同一個場景，重畫時不再收
    roomy = run(layout, "H.fitFirstScreen(); L.bottom = 700; H.fitFirstScreen(); return snap();")
    assert roomy["fitted"] == [] and "fit-own" not in roomy["scene"] and roomy["ownClip"] == [False, False]  # 重量之前全部還原


MUSTER = "<p><strong>廣宗決戰</strong></p>\n<p>集結中，還剩現實 {} 秒。選擇陣營加入；集結期間照常行動。</p>\n<hr />\n<p>【盧植營】危險 ★★</p>"


@node
def test_opened_lines_stay_open_while_the_countdown_ticks():
    """審查 I2：攤開過的所在地、集結那一句，下一次輪詢倒數變了（場景的字跟著變）也不收回去；換了地方、換了一場才重新收。"""
    layout = {"bottom": 800, "actbar": True, "scene": True, "muster": 1, "hr": True, "own": 2}
    main = {"card_id": 7, "on_road": False, "status": {"location": "luzhi_camp"}, "scene": MUSTER.format("26 分 2")}
    script = """
      H.fitFirstScreen(); const folded = snap();
      H.ownOpen(); const opened = snap();
      S.main = Object.assign({}, S.main, { scene: S.main.scene.replace("26 分 2", "25 分 52") }); H.fitFirstScreen(); const polled = snap();
      S.main = Object.assign({}, S.main, { status: { location: "guangzong" } }); H.fitFirstScreen(); const moved = snap();
      return { folded, opened, polled, moved };"""
    out = run(layout, script, S={"main": main})
    assert out["folded"]["ownClip"] == [True, True] and out["folded"]["musterClip"] == [True]
    assert out["opened"]["ownClip"] == [False, False] and out["opened"]["musterClip"] == [False]
    assert out["polled"]["ownClip"] == [False, False] and out["polled"]["musterClip"] == [False]
    assert "own" not in out["polled"]["fitted"] and "muster" not in out["polled"]["fitted"]
    assert out["moved"]["ownClip"] == [True, True]  # 換了地方：重新收


@node
def test_the_muster_line_folds_to_its_countdown_after_the_location():
    """集結、加入的鈕在名字那一行（muster-head）：所在地收過還放不下，名字底下集結那一句收成一行（開頭是倒數）；分隔線之後的不算。
    有事件時所在地不收（joy 的字），集結那一句照樣收（那是引擎的字，名字旁那一小句已經說了按哪裡）。"""
    layout = {"bottom": 800, "actbar": True, "scene": True, "muster": 1, "hr": True, "own": 2}
    out = run(layout)
    assert out["fitted"] == ["space", "own", "muster"] and out["musterClip"] == [True] and out["ownClip"] == [True, True]
    assert "fit-muster" in out["scene"] and out["bottom"] <= 740
    event = run(layout, idle=False)
    assert "muster" in event["fitted"] and event["ownClip"] == [False, False] and event["musterClip"] == [True]
    roomy = run({**layout, "bottom": 790})
    assert roomy["fitted"] == ["space", "own"] and roomy["musterClip"] == [False]  # 收所在地就放得下：集結那一句不動
    opened = run(layout, "H.fitFirstScreen(); H.ownOpen(); return snap();")
    assert opened["musterClip"] == [False] and opened["ownClip"] == [False, False] and "fit-muster" not in opened["scene"]
    plain = run({**layout, "muster": 0})
    assert "muster" not in plain["fitted"]  # 戰場名字底下沒有句子：沒有這一步


@node
def test_the_muster_notice_folds_without_a_join_row():
    """走查：在別的大區、不能加入時，「宛城之戰 集結中…這場決戰在南陽，人要到了那裡…」兩行高，以前沒有加入的鈕就從來不收。
    現在從戰場名字底下算起照樣收成一行（開頭是倒數，點得開）；數字會藏到「…」後面的那一句不收。"""
    layout = {"bottom": 800, "actbar": True, "scene": True, "muster": 1, "join": False, "hr": True, "own": 2}
    out = run(layout)
    assert out["fitted"] == ["space", "own", "muster"] and out["musterClip"] == [True] and out["bottom"] <= 740
    assert out["musterAttrs"] == [{"data-act": "own-more", "role": "button", "tabindex": "0", "aria-expanded": "false"}]
    notice = "集結中，還剩現實 26 分 2 秒。這場決戰在南陽，人要到了那裡才能加入；集結期間照常行動。"
    measured = run({**layout, "texts": {"muster": [notice]}}, measure=True)
    assert measured["musterClip"] == [True]  # 倒數在前面：收了照樣看得到
    late = run({**layout, "texts": {"muster": ["第三回合：官軍強攻、黃巾固守，兩軍在城下殺成一團，戰局 62。"]}}, measure=True)
    assert late["musterClip"] == [False] and "muster" not in late["fitted"]


@node
def test_a_choice_menu_gets_tighter_buttons_last():
    """一組選項（有所感的四個做法）：間距不夠時，鈕縫與鈕高收一點；量的是最後一顆。"""
    out = run({"bottom": 780, "options": True, "scene": True}, idle=False)
    assert out["fitted"] == ["space", "options"] and "fit-tight" in out["menu"] and out["bottom"] <= 740


@node
def test_nothing_is_folded_on_the_road_in_the_prologue_or_on_other_tabs():
    for extra in ({"S": {"main": {"card_id": 7, "scene": "", "on_road": True}}}, {"pro": {"reveal": []}}, {"S": {"tab": "practice"}}):
        out = run(FIGHT, **extra)
        assert out["fitted"] == [] and out["page"] == ["page"] and out["rounds"] == ["rounds"], extra


@node
def test_a_page_with_neither_row_nor_menu_is_left_alone():
    out = run({"bottom": 900, "card": True, "rounds": True, "scene": True})
    assert out["fitted"] == [] and out["page"] == ["page"]


def test_every_draw_and_every_resize_refits():
    """江湖頁每畫一次（afterPage，排在第一回合、聽來的那一句之後），轉向、拉視窗之後，都重量一次。"""
    js = (ROOT / "web" / "app.js").read_text(encoding="utf-8").replace("\r\n", "\n")
    after = js[js.index("\n  function afterPage()"):js.index("\n  }\n", js.index("\n  function afterPage()"))]
    jianghu = after[after.index('if (S.tab === "jianghu")'):]
    calls = re.findall(r"(?m)^\s*(\w+)\(\);", jianghu)  # 真的呼叫（行首、不在註解裡）
    assert "fitFirstScreen" in calls and calls.index("decorateHearsay") < calls.index("fitFirstScreen")
    assert calls.index("fitFirstRound") < calls.index("fitFirstScreen")
    resize = js[js.index('window.addEventListener("resize"'):]
    assert "fitOnResize()" in resize[:resize.index("});")]  # 寬度變了才重量（見下一個測試）
    assert "case \"own-more\": ownOpen(); break;" in js  # 收成一行的那幾段點得開
    assert "case \"line-more\": lineToggle(el); break;" in js
    assert re.search(r"""matches\('\.tx-tight\[data-act="line-more"\]'\)\) \{\s*ev\.preventDefault\(\);\s*lineToggle\(ev\.target\);""", js)


@node
def test_only_a_width_change_refits_on_resize():
    """審查 M6：手機捲動時網址列收起、跑出來只改視窗高度（也會觸發 resize）——不重量，不然第一屏外的那幾段會邊捲邊收、邊攤開。
    寬度變了（轉向、拉視窗）才重量；平常的重畫（afterPage）照舊每次量。"""
    script = """
      H.fitFirstScreen(); const first = snap();
      L.bottom = 700; W.innerHeight = 700; H.fitOnResize(); const tall = snap();
      W.innerWidth = 812; H.fitOnResize(); const turned = snap();
      return { first, tall, turned, width: S.fitWidth };"""
    out = run(FIGHT, script)
    assert out["first"]["fitted"] == ["space", "lines", "rounds"]
    assert out["tall"]["fitted"] == ["space", "lines", "rounds"] and "fit-fold" in out["tall"]["rounds"]  # 只有高度變了：不動
    assert out["turned"]["fitted"] == [] and out["turned"]["rounds"] == ["rounds"] and out["width"] == 812


GUIDE_DRIVER = r"""
// 說書人那一段（GUIDE_KEY 到 guideHtml）切出來：決戰集結時入伍、步驟的框預設收成一行（企劃者 2026-10-08，FB-107 修正輪）
const a = src.indexOf("\n  const GUIDE_KEY");
const b = src.indexOf("\n  }\n", src.indexOf("\n  function guideHtml(")) + 4;
const store = {};
globalThis.localStorage = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: (k) => { delete store[k]; } };
const S = { guideRoad: null, guideFull: null, guidePage: null, main: { scene: input.scene || "" } };
const esc = (s) => String(s);
const pro = () => input.pro || null;
const H = new Function("S", "esc", "pro", src.slice(a, b) + "\nreturn { guideHtml, openGuide, shutGuide };")(S, esc, pro);
const kind = (g, onRoad = false) => { const html = H.guideHtml(g, onRoad); return html.includes('class="guide-line"') ? "line" : html.includes("card guide") ? "card" : ""; };
const step = { speaker: "老石", key: "r3_battle", text: "要打大仗了。\n\n先按戰場名字旁的『加入』報名。", line: "去報名", done: [], end: false, paged: true, full: true };
const ack = { speaker: "師父", key: "h_injury", text: "打一場掉的氣血，大半會自己回來。", done: [], end: true };
finish(new Function("H", "S", "kind", "step", "ack", input.script)(H, S, kind, step, ack));
"""

MUSTER_SCENE = "<p><strong>長社火攻</strong></p>\n<p>集結中，還剩現實 {} 秒。選擇陣營加入；集結期間照常行動。</p>\n<hr />\n<p>【長社】危險 ★★</p>"


def _guide(script, scene="", **extra):
    return webharness.run(GUIDE_DRIVER, {"script": script, "scene": scene, **extra})


@node
def test_a_step_box_starts_folded_during_a_muster_and_full_otherwise():
    """企劃者 2026-10-08：決戰集結時，入伍、步驟的框（今天整段或分頁攤開的）預設收成一行，點了攤開——同在路上（FB-055）。
    「知道了」那種碰到才說的框也收（裁示：控制者量的潁水河畔＋內傷框＋別處集結 762～784，這一輪收集結那一句之後估 745～767，還是
    放不下）。沒有集結照舊攤開；序章裡師父的框不收；在路上「知道了」的框照舊攤開（路上另有排法）。"""
    out = _guide("return [kind(step), kind(ack)];", MUSTER_SCENE.format("12 分 5"))
    assert out == ["line", "line"]
    assert _guide("return [kind(step), kind(ack)];") == ["card", "card"]
    assert _guide("return [kind(step), kind(ack)];", MUSTER_SCENE.format("12 分 5"), pro={"reveal": []}) == ["card", "card"]
    assert _guide("return kind(ack, true);", MUSTER_SCENE.format("12 分 5")) == "card"
    opened = "H.openGuide(ack); const a = kind(ack); S.main = { scene: S.main.scene.replace('12 分 5', '11 分 55') }; return [a, kind(ack)];"
    assert _guide(opened, MUSTER_SCENE.format("12 分 5")) == ["card", "card"]  # 點開了：倒數變了也不收
    joined = MUSTER_SCENE.format("1 分 5").replace("集結中，還剩現實 1 分 5 秒。選擇陣營加入；集結期間照常行動。", "你已加入【官軍】，集結還剩現實 1 分 5 秒。集結結束就開打，在那之前照常行動。")
    assert _guide("return kind(step);", joined) == "line"  # 加入了、還在集結：照樣收著


@node
def test_an_opened_step_box_stays_open_while_the_countdown_ticks_and_folds_when_told():
    """點開了：輪詢倒數變了（場景的字跟著變）也不收回去；自己按「收起」才收；集結結束（開打了）就回到平常的樣子（攤開），
    下一場集結又從收著開始。"""
    script = """
      const out = [kind(step)];
      H.openGuide(step); out.push(kind(step));
      S.main = { scene: S.main.scene.replace("12 分 5", "11 分 55") }; out.push(kind(step));
      S.main = { scene: "<p><strong>長社火攻</strong></p>\\n<p>【第一幕】（第 1／9 回合）火起</p>\\n<hr />\\n<p>【長社】</p>" }; out.push(kind(step));
      S.main = { scene: S.main.scene.replace("【第一幕】（第 1／9 回合）火起", "集結中，還剩現實 9 分 0 秒。") }; out.push(kind(step));
      H.openGuide(step); H.shutGuide(step); out.push(kind(step));
      return out;"""
    assert _guide(script, MUSTER_SCENE.format("12 分 5")) == ["line", "card", "card", "card", "line", "line"]


HINT_DRIVER = r"""
const S = Object.assign({ hintOpen: false, hintTight: false, tab: "jianghu", main: { guide: null, options: [{ id: "act:rest" }] } }, input.S);
const H = new Function("S", [konst("esc"), konst("WAITING"), konst("waitingMenu"), "const idleMenu = () => true;", fn("hintHtml"),
  "return { hintHtml };"].join("\n"))(S);
finish({ html: H.hintHtml({ hint: "💡 你已攢下 45 點心得。", journey: null }), open: S.hintOpen });
"""


@node
@pytest.mark.parametrize("state, folded", [
    ({"hintTight": True}, True), ({"hintTight": False}, False), ({"hintTight": True, "tab": "practice"}, False),
])
def test_the_hint_is_drawn_folded_only_when_the_fit_asked_and_only_on_the_jianghu_page(state, folded):
    out = webharness.run(HINT_DRIVER, {"S": state})
    assert ('class="hint road-hint clamp"' in out["html"] and 'data-act="hint-more"' in out["html"]) is folded
    assert ('<span class="hint">' in out["html"]) is not folded


@node
def test_a_folded_hint_the_player_opened_stays_open_on_redraw():
    out = webharness.run(HINT_DRIVER, {"S": {"hintTight": True, "hintOpen": True}})
    assert out["open"] is True and 'class="hint road-hint"' in out["html"] and "clamp" not in out["html"]


@node
def test_an_opened_hint_stays_open_after_a_look_at_another_tab():
    """審查 M9：收成一行的 💡 點開了，去修練頁看一眼（那裡照整段畫），回來照舊攤開；不收了（hintTight 拿掉）才清掉。"""
    away = webharness.run(HINT_DRIVER, {"S": {"hintTight": True, "hintOpen": True, "tab": "practice"}})
    assert away["open"] is True and '<span class="hint">' in away["html"]
    done = webharness.run(HINT_DRIVER, {"S": {"hintTight": False, "hintOpen": True}})
    assert done["open"] is False


# ── 真的卡片：收起來的那幾樣不含得失與結果 ─────────────────────────


def _fight_card(on):
    import random

    from tianxia.engine import Game

    game = Game.new(on, "甲", rng=random.Random(0))
    game.client = None
    game.state.player.location = "yingshui"
    game.choose("act:train")
    return server.main_view(game)


def test_the_folded_parts_never_hold_the_gains_or_the_result(on):
    """收的只有回合清單（ul.rounds）與卡片底下的補充（.tx-extra 的 .tx-line）：「得失」的數字與大勝／險勝那一行在別的段落。"""
    m = _fight_card(on)
    card, extra = m["card"], m["now"]
    gains = re.search(r"<p><strong>得失</strong>.*?</p>", card, re.S)
    assert gains and re.search(r"[+-]\d", gains.group(0))
    rounds = re.search(r"<ul>.*?</ul>", card, re.S).group(0)
    assert "得失" not in rounds and not re.search(r"大勝|險勝|僵持|落敗", rounds)
    assert re.search(r"<strong>(大勝|險勝|僵持|落敗)</strong>", card.replace(rounds, ""))
    assert "得失" not in extra and "tx-line" in extra  # 補充那一行（對手的描述）不帶得失


# ── 樣式 ─────────────────────────────────────────────


def _css() -> str:
    return re.sub(r"/\*.*?\*/", "", (ROOT / "web" / "style.css").read_text(encoding="utf-8"), flags=re.S)


def _rules(css, needle):
    return {sel.strip(): body for sel, body in re.findall(r"(?m)^([^{}\n@]*" + re.escape(needle) + r"[^{}\n]*)\{([^}]*)\}", css)}


def test_each_step_only_touches_what_it_names():
    """每一步一個 class；只有第 3 步藏東西，藏的是收著的回合清單或大場面那一段話（展開 .open 就回來）；第 2、5 步是一行加「…」。"""
    css = _css()
    hiding = [sel for sel, body in re.findall(r"(?m)^([^{}\n@]*fit-[^{}\n]*)\{([^}]*)\}", css) if "display: none" in body]
    assert sorted(s.strip() for s in hiding) == [".battle-card p.rounds-tale.fit-fold:not(.open)", ".battle-card ul.rounds.fit-fold:not(.open)"]
    tight = _rules(css, ".tx-tight")
    assert "white-space: nowrap" in tight[".battle-card .tx-extra .tx-line.tx-tight"] and "text-overflow: ellipsis" in tight[".battle-card .tx-extra .tx-line.tx-tight"]
    assert "white-space: normal" in tight[".battle-card .tx-extra .tx-line.tx-tight.open"]
    assert "max-height: 4.8em" in _rules(css, "fit-short")[".now.clamp.fit-short .tx-now"]
    clip = _rules(css, "fit-clip")[".card.scene p.fit-clip"]
    assert "white-space: nowrap" in clip and "text-overflow: ellipsis" in clip
    opts = _rules(css, "fit-tight")
    assert "gap: 6px" in opts[".page > .options.fit-tight"] and "min-height: 44px" in opts[".page > .options.fit-tight > .btn"]


def test_the_spacing_step_only_shrinks_gaps_and_paddings():
    """第 1 步只動 margin 與 padding（不動字級、行高、不藏東西）；卡與卡之間 12→8。"""
    css = _css()
    rules = _rules(css, "fit-space")
    assert rules and all(re.fullmatch(r"\s*((margin|padding)(-top|-bottom)?: \d+px;\s*)+", body) for body in rules.values()), rules
    gaps = rules[".page.fit-space > .peek, .page.fit-space > .now, .page.fit-space > .card, .page.fit-space > .guide-line"]
    assert "margin-bottom: 8px" in gaps


def test_the_box_step_keeps_every_word_and_the_tap_target():
    """框收緊只動「知道了」佔的高度（鈕本身照樣 38px，上下 −9px）與話的行高；不 clamp、不藏字（設計 6.2：話不會被切掉）。
    玩家互動那幾塊（「此地還有」、結伴、邀請）是另一條線的：收的時候不碰它們的樣式。"""
    css = _css()
    rules = _rules(css, "fit-box")
    assert set(re.findall(r"([\w-]+):", rules[".card.guide.fit-box .guide-head .btn"])) == {"margin-top", "margin-bottom"}
    assert rules[".card.guide.fit-box .guide-text"].strip() == "line-height: 1.5;"
    assert not any("clamp" in body or "display: none" in body or "overflow" in body for body in rules.values())
    fit_rules = re.findall(r"(?m)^([^{}\n@]*\bfit-[^{}\n]*)\{", css)
    assert not any(re.search(r"\.(here|calls|call|party|peer)\b", sel) for sel in fit_rules), fit_rules


def _px(body: str, prop: str) -> float:
    return float(re.search(rf"(?:^|;|\s){prop}:\s*(-?[\d.]+)px", body).group(1))


def test_the_tightened_box_button_stays_inside_the_box_and_off_the_words():
    """審查 M1：收緊的框裡「知道了」（.btn.small，38px）不壓到話的第一行、也不伸出框外。照 style.css 的數字排一次：
    標題那一行（12px × 1.65）是 flex、置中；鈕的上下 margin 是負的。鈕的下緣不能超過那一行的下緣＋話的 margin-top，
    上緣不能超過框（第 1 步之後）的內距；那一行還是要比沒收時（38px）矮。"""
    css = _css()
    base = re.search(r"(?m)^body \{([^}]*)\}", css).group(1)
    line_height = float(re.search(r"font: [\d.]+px/([\d.]+)", base).group(1))
    head = re.search(r"(?m)^\.guide-head \{([^}]*)\}", css).group(1)
    assert "align-items: center" in head and "display: flex" in head
    head_line = _px(head, "font-size") * line_height
    button = _px(re.search(r"(?m)^\.btn\.small \{([^}]*)\}", css).group(1), "min-height")
    fit = _rules(css, "fit-box")[".card.guide.fit-box .guide-head .btn"]
    top, bottom = _px(fit, "margin-top"), _px(fit, "margin-bottom")
    text_gap = float(re.search(r"(?m)^\.guide-text \{[^}]*margin: ([\d.]+)px", css).group(1))
    pad = _px(_rules(css, "fit-space")[".page.fit-space > .card.guide"], "padding-top")
    row = max(head_line, button + top + bottom)  # 標題那一行的高度（鈕的 margin box 與字取大的）
    edge_top = (row - (button + top + bottom)) / 2 + top  # 鈕的上緣（相對於那一行的頂；負的是往上伸）
    edge_bottom = edge_top + button
    assert edge_bottom <= row + text_gap, (edge_bottom, row, text_gap)  # 不壓字
    assert edge_top >= -pad, (edge_top, pad)  # 不出框
    assert row < button  # 真的有收


def test_the_players_here_row_does_not_style_the_here_fold():
    """「此地還有」那一行的樣式只認 div（PR #34 寫成 .here，連「此地還能做」的 <details class="fold here"> 也套上虛線與 flex）。"""
    css = _css()
    assert not re.search(r"(?m)^\.here \{", css)
    here = re.search(r"(?m)^div\.here \{([^}]*)\}", css).group(1)
    assert "border-top: 1px dashed" in here and "display: flex" in here
    js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    assert '<div class="here">' in js and '<details class="fold here"' in js
