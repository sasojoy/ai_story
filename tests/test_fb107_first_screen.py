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
let tops = 0;
const renderTop = () => { tops += 1; };
const mhead = L.muster ? el("head", ["muster-head"], { tagName: "DIV" }) : null;
const musterLines = (L.muster || 0) ? Array.from({ length: L.muster }, () => el("musterp", [], { tagName: "P" })) : [];
const hr = L.hr ? el("hr", [], { tagName: "HR" }) : null;
const own = (L.own || 0) ? Array.from({ length: L.own }, () => el("ownp", [], { tagName: "P" })) : [];
// 場景卡的順序：名字那一行（muster-head）、集結那一句、分隔線、所在地
const order = [mhead, ...musterLines, hr, ...own].filter(Boolean);
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
if (target) target.getBoundingClientRect = () => ({ bottom: bottom() });
tabs.getBoundingClientRect = () => ({ top: 756 });
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
globalThis.document = { getElementById: (id) => (id === "page" && L.page !== false ? page : null), querySelector: (s) => q(s)[0] || null, querySelectorAll: q };
globalThis.window = { scrollY: 0 };
page.querySelectorAll = q;
if (now) now.querySelector = (s) => (s === ".tx-now" ? body : null);
if (scene) {
  scene.querySelector = (s) => (s === ":scope > hr" ? hr : s === ":scope > .muster-head" ? mhead : null);
  scene.querySelectorAll = (s) => (s === ":scope > hr ~ p" && hr ? own : s === ".fit-clip" ? all.filter((x) => has(x, "fit-clip")) : []);
}
const S = Object.assign({ stage: "game", tab: "jianghu", hearOpen: null, ownOpen: null, hintTight: false, hintOpen: false,
  main: { card_id: 7, scene: "<p>x</p>", on_road: false } }, input.S || {});
const pro = () => input.pro || null;
const idleMenu = () => input.idle !== false;
const H = new Function("S", "pro", "idleMenu", "renderTop", code + "\nreturn { fitFirstScreen, fitOver, ownOpen, FIT_STEPS };")(S, pro, idleMenu, renderTop);
const snap = () => ({
  fitted: S.fitted, bottom: bottom(), page: [...page.classes].sort(), card: card ? [...card.classes].sort() : null,
  box: box ? [...box.classes].sort() : null, hintTight: S.hintTight, tops,
  lines: lines.map((x) => [...x.classes].sort()), lineAttrs: lines.map((x) => x.attrs), rounds: rounds ? [...rounds.classes].sort() : null,
  now: now ? [...now.classes].sort() : null, scene: scene ? [...scene.classes].sort() : null, own: own.map((x) => x.attrs),
  ownClip: own.map((x) => has(x, "fit-clip")), musterClip: musterLines.map((x) => has(x, "fit-clip")),
  menu: menu ? [...menu.classes].sort() : null,
});
finish(new Function("H", "S", "snap", "L", input.script || "H.fitFirstScreen(); return snap();")(H, S, snap, L));
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
    assert out["lines"] == [["tx-line", "tx-tight"]] and out["lineAttrs"][0]["data-act"] == "hear-more"  # 點得開（同聽來的那一句）
    assert out["rounds"] == ["rounds"]


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
    """玩家按了「展開過程」（ul 掛 open）、點開過補充（S.hearOpen 是這一場）：重畫之後不再收回去，其他步驟照樣收。"""
    out = run({**FIGHT, "rounds": True, "roundsOpen": True}, S={"hearOpen": 7})
    assert "lines" not in out["fitted"] and "rounds" not in out["fitted"]
    assert out["rounds"] == ["open", "rounds"] and out["lines"] == [["tx-line"]]


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
    opened = run(layout, "H.fitFirstScreen(); H.ownOpen(); return { s: snap(), open: S.ownOpen };")
    assert "fit-own" not in opened["s"]["scene"] and opened["s"]["ownClip"] == [False, False] and opened["open"] == "<p>x</p>"
    assert opened["s"]["own"] == [{}, {}]
    again = run(layout, S={"ownOpen": "<p>x</p>"})
    assert "own" not in again["fitted"]  # 攤開過的同一個場景，重畫時不再收


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
    assert "muster" not in plain["fitted"]  # 沒有加入的鈕（已加入、觀戰）：沒有這一步


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
    assert "fitFirstScreen()" in resize[:resize.index("});")]
    assert "case \"own-more\": ownOpen(); break;" in js  # 收成一行的那幾段點得開


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
    assert rules[".card.guide.fit-box .guide-head .btn"].split() == "margin-top: -9px; margin-bottom: -9px;".split()
    assert rules[".card.guide.fit-box .guide-text"].strip() == "line-height: 1.5;"
    assert not any("clamp" in body or "display: none" in body or "overflow" in body for body in rules.values())
    fit_rules = re.findall(r"(?m)^([^{}\n@]*\bfit-[^{}\n]*)\{", css)
    assert not any(re.search(r"\.(here|calls|call|party|peer)\b", sel) for sel in fit_rules), fit_rules


def test_the_players_here_row_does_not_style_the_here_fold():
    """「此地還有」那一行的樣式只認 div（PR #34 寫成 .here，連「此地還能做」的 <details class="fold here"> 也套上虛線與 flex）。"""
    css = _css()
    assert not re.search(r"(?m)^\.here \{", css)
    here = re.search(r"(?m)^div\.here \{([^}]*)\}", css).group(1)
    assert "border-top: 1px dashed" in here and "display: flex" in here
    js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    assert '<div class="here">' in js and '<details class="fold here"' in js
