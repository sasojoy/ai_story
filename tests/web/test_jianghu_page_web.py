"""江湖頁的畫面：第一屏與行動列、此地還能做的摺疊、狀態列、剛剛的卡片。原本一張回饋單一個檔（FB-087、105、107、120、123、135、136、198、360、663、664、670、671），2026-10-27 測試整理 1b 併成這一檔；各段開頭照抄原本那一檔的說明。"""
from __future__ import annotations
import re
from pathlib import Path
import pytest
import server
import webharness
import random
from tianxia.engine import Game
import json
from test_prologue_web import _enlist_main
import html as htmllib
from test_prologue import _to_step
from conftest import real_content, renown_unscaled
from tianxia import rules
from tianxia.engine import SOCIAL_NO_ONE, Game
from conftest import classic_rules, real_content
from jianfa_kit import no_jianfa
from test_prologue_web import run as run_prologue_web, with_reveal
from tianxia import explore_modes, sortie
from tianxia.models import REVEAL_KEYS
from tianxia.sqlite_world import open_world


# ── 原 test_fb107_first_screen.py（整檔搬進來） ──
# FB-107（QA 93e7037，2026-10-08，375×812）：師父「碰到才說」的框、兩行的 💡、決戰集結（戰場、「此地還有」、結伴）在畫面上時，
# 行動列掉到分頁列底下。企劃者 10/5：框留在行動列上面、話不切。
#
# 網頁現在畫好之後量一次（web/app.js 的 fitFirstScreen）：行動列（一組選項時是最後一顆）的下緣離分頁列不到 FIT_MARGIN，就照
# FIT_STEPS 的順序一步一步收，放得下就停——放得下的畫面一點都不動。順序：間距 → 框收緊（話不切）→ 💡 收成一行 → 戰鬥卡片底下的補充
# 收成一行 → 第一回合收進「展開過程」→「剛剛」只露三行 → 決戰時所在地的描述收成一行 → 集結那一句收成一行 → 一組選項的鈕縫與鈕高。
# 每一樣點得開；「得失」與結果那幾行、框裡的話不收。
#
# 這裡把那幾個函式從 app.js 切出來，在 node 裡接一個假的頁面跑：假頁面的行動列下緣照「哪幾個元素身上掛了哪個 class」算（每一樣省多少 px
# 寫在 SAVE），量的是收的順序、停在哪、點開過的不收、重量之前先還原、在路上與序章不收。真的 px 是 375×812 估出來的（fix-1008 的交接報告）。
# 樣式另外釘住：每一步只動它該動的東西。

ROOT = Path(__file__).parents[2]


node = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


DRIVER = r"""
// 從 app.js 切出 FB-107 那一段（FIT_MARGIN 到 ownOpen 之前，加上 ownOpen 本身）
const head = src.indexOf("\n  const FIT_MARGIN"), tail = src.indexOf("\n  function ownOpen(");
if (head < 0 || tail < 0) throw new Error("app.js 裡找不到 FB-107 那一段");
const code = src.slice(head, tail) + fn("ownOpen") + konst("callKey") + fn("callsOpened"); // 收法 6b 問 callsOpened（FB-241）

// 假的頁面：每個元素是 { kind, classes, attrs, dataset, ... }；選擇器照 app.js 用到的那幾個寫成判斷式
const all = [];
// class 屬性照真的瀏覽器（FB-9010）：classList.add 會建出 class 屬性，拿光之後屬性還在、是空的 class=""，只有 removeAttribute("class") 才真的沒有；
// e.hasClassAttr 記屬性有沒有，:not([class]) 看的就是它（沒有 class 的 <p> 一收一放就變成有 class 屬性的，除非程式自己把空的屬性拿掉）
const el = (kind, classes = [], extra = {}) => {
  const e = { kind, classes: new Set(classes), attrs: {}, dataset: {}, hasClassAttr: classes.length > 0, ...extra };
  e.classList = {
    add: (...c) => { c.forEach((x) => e.classes.add(x)); e.hasClassAttr = true; }, remove: (...c) => c.forEach((x) => e.classes.delete(x)),
    contains: (c) => e.classes.has(c),
    toggle: (c, on) => { if (on ?? !e.classes.has(c)) { e.classes.add(c); e.hasClassAttr = true; } else e.classes.delete(c); },
    replace: (a, b) => { if (!e.classes.has(a)) return false; e.classes.delete(a); e.classes.add(b); return true; },
  };
  e.setAttribute = (k, v) => { e.attrs[k] = String(v); };
  e.getAttribute = (k) => (k === "class" ? (e.hasClassAttr ? [...e.classes].join(" ") : null) : k in e.attrs ? e.attrs[k] : null);
  e.removeAttribute = (k) => { if (k === "class") { e.classes.clear(); e.hasClassAttr = false; } delete e.attrs[k]; };
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
// 場景的畫（減法季批 8；收法 5a 縮成橫幅）與戰鬥補充那一塊（收法 5c 只留第一行；L.extra 是一共幾行）
const art = L.art ? el("art", ["scene-art"]) : null;
const extra = L.extra ? el("extra", ["tx-extra"]) : null;
// 約戰卡第一張應得了、同去得了的那一行（FB-9006，收法 fitDuelRow）：L.duel 是那一行的下緣比行動列下緣低幾 px（沒給＝沒有可按的約戰，量的還是行動列）；
// 它的鈕（sortie-answer／sortie-join）掛在那一行底下，fitDuelRow 取鈕的 parentElement
const duelRow = L.duel ? el("duelrow", ["sx-drow"]) : null;
const duelBtn = L.duel ? el("duelbtn", ["btn"], { parentElement: duelRow }) : null;
if (extra) extra.querySelectorAll = (s) => (s === ":scope > .tx-line" ? Array.from({ length: L.extra }, () => ({})) : []);
const box = L.box ? el("box", ["card", "guide"]) : null;
const hint = L.hint ? el("hint", ["hint"]) : null;  // 狀態列的 💡（#top 裡）；收成一行看的是 S.hintTight（renderTop 照它畫）
// 名聲（名聲設計十一之二）：狀態列名號底下那一行稱號（1B，收不收看 S.renownTight）與決戰本場戰功名字底下的稱號（4B，L.merit 是幾行）
const renownLine = L.renown ? el("renown", ["who-renown-line"]) : null;
const meritSmalls = Array.from({ length: L.merit || 0 }, () => el("msmall", []));
// 一組選項還放不下（第 10 步 choices，企劃者 2026-10-16 選 (c)）：態勢那一排（L.peekOpen 是攤開了一格）、灰掉的俠寇鈕底下那一行原因（L.notes 行）
const peek = L.peek ? el("peek", ["peek"]) : null;
if (peek) peek.querySelector = (s) => (s === ".wk-panel" && L.peekOpen ? {} : null);
const notes = Array.from({ length: L.notes || 0 }, () => el("note", ["opt-note"]));
const chapter = L.chapter ? el("chapter", ["card", "ch-card"]) : null; // 章回卡（第 10 步跟本週卡一起收，自檢 U-09）
// 決戰輪到你出招（自檢 U-01，收法 5d～5f）：L.turn 是選單裡有三招；戰場裡最新那一回合（L.latest）、更早的幾回合（L.older 個，本來就一行）、
// 本場戰功（L.board）。三樣的 parentElement 都是場景卡
const latest = L.latest ? el("latest", ["b-round", "latest"]) : null;
const older = Array.from({ length: L.older || 0 }, () => el("older", ["b-round"]));
const board = L.board ? el("board", ["g-merit"]) : null;
// 狀態列（#top）的高度（FB-123）：input.topHeight；input.realTop 時 renderTop 照真的那樣先量高度、重畫（💡 收成一行時矮 input.topSaves）、
// 再交給 fitTopMoved
const topEl = { offsetHeight: input.topHeight || 120 };
let tops = 0, HH = null;
const renderTop = () => {
  tops += 1;
  if (!input.realTop) return;
  const before = topEl.offsetHeight;
  topEl.offsetHeight = (input.topHeight || 120) - (S.renownTight ? input.topSaves || 20 : 0);
  HH.fitTopMoved(before);
};
// 場景卡：加入的鈕在名字那一行時（L.join 不是 false）名字包在 muster-head 裡；沒有鈕時名字是場景卡第一個 <p>
const T = L.texts || {};
const mhead = L.muster && L.join !== false ? el("head", ["muster-head"], { tagName: "DIV" }) : null;
const title = L.hr && !mhead ? el("title", [], { tagName: "P", text: "廣宗決戰" }) : null;
const musterLines = (L.muster || 0) ? Array.from({ length: L.muster }, (_, i) => el("musterp", [], { tagName: "P", text: (T.muster || [])[i] || "" })) : [];
const hr = L.hr ? el("hr", [], { tagName: "HR" }) : null;
const own = (L.own || 0) ? Array.from({ length: L.own }, (_, i) => el("ownp", [], { tagName: "P", text: (T.own || [])[i] || "" })) : [];
// 閒著的場景卡（沒有分隔線）裡所在地的描述（收法 6c）：L.desc 是一共幾段，都是沒有 class 的 <p>。沒有畫（L.art 沒給）時第一段是
// 「【地名】危險 ★★」那一條（有畫時它疊在畫上、場景文字裡拿掉，sceneUnderArt）：不是描述，收法不收
const descHead = L.desc && !L.art ? el("deschead", [], { tagName: "P", text: "【白馬津】危險 ★★" }) : null;
const descParas = Array.from({ length: L.desc || 0 }, (_, i) => el("descp", [], { tagName: "P", text: (T.desc || [])[i] || "" }));
lines.forEach((x, i) => { x.text = (T.lines || [])[i] || ""; });
// 場景卡的順序：名字那一行（muster-head 或名字那一段）、集結那一句、分隔線、所在地
const order = [mhead || title, ...musterLines, hr, ...own].filter(Boolean);
order.forEach((e, i) => { e.nextElementSibling = order[i + 1] || null; });
// 場景底下別人遞來的邀請（FB-117 的第 6b 步）：L.calls 是畫出來的幾列，L.callsTotal 是一共幾份，L.callsMore 是畫的時候就有「還有 N 份」那一行
const callRows = Array.from({ length: L.calls || 0 }, () => el("call", ["call"]));
const callsBox = L.calls ? el("calls", ["calls"]) : null;
let callsMore = null;
const makeMore = (text, fit) => {
  const m = el("more", ["calls-more"]);
  m.textContent = text;
  if (fit) m.dataset.fit = "1";
  m.remove = () => { if (callsMore === m) callsMore = null; };
  return m;
};
if (callsBox) {
  callsBox.dataset.total = String(L.callsTotal || L.calls);
  if (L.callsMore) callsMore = makeMore(L.callsMore, false);
  callsBox.querySelectorAll = (s) => (s === ":scope > .call" ? callRows : []);
  callsBox.querySelector = (s) => (s === ":scope > .calls-more" ? callsMore : null);
  callsBox.insertAdjacentHTML = () => { callsMore = makeMore("", true); };
}
// 每一樣收起來省多少 px（假的；真的看 375×812 估的數字）
const SAVE = Object.assign({ chapter: 110, latest: 110, older: 40, board: 55, art: 190, extra: 60, space: 30, cardSpace: 6, box: 22, hint: 20, renown: 20, line: 20, rounds: 23, merit: 6, own: 27, muster: 27, desc: 27, options: 22, call: 70, moreLine: 0, peek: 56, note: 18 }, input.save || {});
// 「剛剛」只留時間與標題（fit-title）時剩兩行 48px；只露三行（fit-short）時最多 72px
const bodyHeight = () => (now && has(now, "fit-title") && !has(now, "open") ? Math.min(L.nowBody, 48)
  : now && has(now, "fit-short") ? Math.min(L.nowBody, 72) : Math.min(L.nowBody || 0, 120));
const bottom = () => {
  let b = L.bottom;
  if (has(page, "fit-space")) b -= SAVE.space;
  if (card && has(card, "fit-space")) b -= SAVE.cardSpace;
  if (box && has(box, "fit-box")) b -= SAVE.box;
  if (hint && S.hintTight && !S.hintOpen) b -= SAVE.hint;
  if (renownLine && S.renownTight) b -= SAVE.renown;
  meritSmalls.forEach((x) => { if (has(x, "fit-hide")) b -= SAVE.merit; });
  lines.forEach((x) => { if (has(x, "tx-tight") && !has(x, "open")) b -= SAVE.line; });
  if (rounds && has(rounds, "fit-fold") && !has(rounds, "open")) b -= SAVE.rounds;
  if (art && has(art, "fit-art")) b -= SAVE.art;
  if (extra && has(extra, "fit-extra")) b -= SAVE.extra;
  if (now) b -= Math.min(L.nowBody || 0, 120) - bodyHeight();
  if (own.some((p) => has(p, "fit-clip"))) b -= SAVE.own;
  descParas.forEach((p) => { if (has(p, "fit-clip")) b -= SAVE.desc; }); // 一段收成一行省一行（描述每段約兩、三行）
  if (musterLines.some((p) => has(p, "fit-clip"))) b -= SAVE.muster;
  if (menu && has(menu, "fit-tight")) b -= SAVE.options;
  callRows.forEach((x) => { if (has(x, "fit-hide")) b -= SAVE.call; });
  if (callsMore && callsMore.dataset.fit) b += SAVE.moreLine; // 收法 6b 補上的「還有 N 份」那一行自己也佔高度
  if (peek && has(peek, "fit-hide")) b -= SAVE.peek;
  notes.forEach((x) => { if (has(x, "fit-hide")) b -= SAVE.note; });
  if (latest && has(latest, "fit-latest")) b -= SAVE.latest;
  older.forEach((x) => { if (has(x, "fit-hide")) b -= SAVE.older; });
  if (board && has(board, "fit-board")) b -= SAVE.board;
  if (chapter && has(chapter, "fit-hide")) b -= SAVE.chapter;
  return b;
};
const target = actbar || last;
// 畫面上的位置＝頁面上的位置 − 捲了多少（分頁列固定在畫面底下）
if (target) target.getBoundingClientRect = () => ({ bottom: bottom() - globalThis.window.scrollY });
if (duelRow) duelRow.getBoundingClientRect = () => ({ bottom: bottom() + L.duel - globalThis.window.scrollY }); // 在行動列底下，一起跟著收的東西上下移
const DUEL_SEL = new Function(`return ${src.match(/const FIT_DUEL_BTN = ('[^']*'\s*\+\s*'[^']*');/)[1]}`)();
// 分頁列頂：手機網址列收起時分頁列跟著往下（FB-123），測試用 els.setTabsTop 換
let tabsTop = input.tabsTop || 756;
tabs.getBoundingClientRect = () => ({ top: tabsTop });
if (body) Object.defineProperty(body, "scrollHeight", { get: () => L.nowBody });
if (body) Object.defineProperty(body, "clientHeight", { get: () => bodyHeight() });
const where = {
  "#page > .act-bar": () => (actbar ? [actbar] : []),
  "#page > .options > :last-child": () => (last ? [last] : []),
  [DUEL_SEL]: () => (L.duel && duelBtn ? [duelBtn] : []),
  ".tabs": () => [tabs],
  "#page > .battle-card": () => (card ? [card] : []),
  ".battle-card .tx-extra .tx-line:not(.tx-hearsay)": () => lines.filter((x) => !has(x, "tx-hearsay")),
  ".battle-card ul.rounds:not(.open), .battle-card p.rounds-tale:not(.open)": () => (rounds && !has(rounds, "open") ? [rounds] : []),
  "#page > .now:not(.open)": () => (now && !has(now, "open") ? [now] : []),
  "#page > .card.scene:not(.road)": () => (scene ? [scene] : []),
  "#page > .options": () => (menu ? [menu] : []),
  "#page > .card.guide": () => (box ? [box] : []),
  "#top .more-stats .hint": () => (hint ? [hint] : []),
  "#top .who-renown-line": () => (renownLine && !S.renownTight ? [renownLine] : []),
  ".g-merit .rn-two small:not(.fit-hide)": () => meritSmalls.filter((x) => !has(x, "fit-hide")),
  ".g-merit small.fit-hide": () => meritSmalls.filter((x) => has(x, "fit-hide")),
  ".fit-space": () => all.filter((x) => x !== page && has(x, "fit-space")),
  ".fit-box": () => all.filter((x) => has(x, "fit-box")),
  ".tx-tight": () => all.filter((x) => has(x, "tx-tight")),
  ".fit-fold": () => all.filter((x) => has(x, "fit-fold")),
  ".fit-art": () => all.filter((x) => has(x, "fit-art")),
  ".fit-extra": () => all.filter((x) => has(x, "fit-extra")),
  "#page > .card.scene > .scene-art:not(.fit-art)": () => (art && !has(art, "fit-art") ? [art] : []),
  "#page .battle-card .tx-extra:not(.fit-extra)": () => (extra && !has(extra, "fit-extra") ? [extra] : []),
  ".now.fit-short": () => all.filter((x) => has(x, "now", "fit-short")),
  ".fit-own, .fit-muster": () => all.filter((x) => has(x, "fit-own") || has(x, "fit-muster")),
  ".fit-clip": () => all.filter((x) => has(x, "fit-clip")),
  ".fit-tight": () => all.filter((x) => has(x, "fit-tight")),
  "#page > .card.scene .calls": () => (callsBox ? [callsBox] : []),
  ".call.fit-hide": () => callRows.filter((x) => has(x, "fit-hide")),
  ".calls-more": () => (callsMore ? [callsMore] : []),
  "#page > .wk-card": () => (peek ? [peek] : []),
  "#page > .ch-card": () => (L.chapter && chapter ? [chapter] : []),
  "#page > .options > .btn.off .opt-note": () => notes,
  ".wk-card.fit-hide, .ch-card.fit-hide, .opt-note.fit-hide": () => [peek, chapter, ...notes].filter((x) => x && has(x, "fit-hide")),
  ".now.fit-title": () => all.filter((x) => has(x, "now", "fit-title")),
  '#page > .options [data-id^="battle:act:"]': () => (L.turn ? [{}] : []),
  "#page > .card.scene .b-round.latest:not(.fit-latest)": () => (latest && !has(latest, "fit-latest") ? [latest] : []),
  "#page > .card.scene .b-round.fit-latest": () => (latest && has(latest, "fit-latest") ? [latest] : []),
  "#page > .card.scene details.b-round:not(.fit-hide)": () => older.filter((x) => !has(x, "fit-hide")),
  "#page > .card.scene .g-merit:not(.fit-board)": () => (board && !has(board, "fit-board") ? [board] : []),
  ".fit-latest, .fit-board": () => [latest, board].filter((x) => x && (has(x, "fit-latest") || has(x, "fit-board"))),
  // 出陣回報（frontReportHtml）：假頁面沒有這一塊
  "#page .sfront": () => [],
  "#page .sfront.fit-tight": () => [],
  ".sfront.fit-min": () => [],
  '.sfront[data-act="front-more"]': () => [],
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
  [...lines, ...musterLines, ...own, ...descParas].forEach((x) => { x.getBoundingClientRect = () => ({ right: 300 }); });
}
page.querySelectorAll = q;
if (now) now.querySelector = (s) => (s === ".tx-now" ? body : null);
if (body) body.querySelector = (s) => (s === ".tx-line" && L.nowLines !== false ? {} : null); // L.nowLines false：「剛剛」只有標題、沒有敘事
if (scene) {
  // 「收起戰場」那一行（FB-120）：只能觀戰的人自己攤開了開打中的戰場（L.battleShut）
  scene.querySelector = (s) => (s === ":scope > hr" ? hr : s === ":scope > .muster-head" ? mhead
    : s === ":scope > p" ? (mhead ? musterLines[0] || null : title) : s === ":scope > .battle-shut" ? (L.battleShut ? {} : null)
    : s === ":scope > .scene-art" ? art : null);
  scene.querySelectorAll = (s) => (s === ":scope > hr ~ p" && hr ? own : s === ".fit-clip" ? all.filter((x) => has(x, "fit-clip"))
    : s === ":scope > p:not([class])" ? [descHead, ...descParas].filter((x) => x && !x.hasClassAttr)
    : s === ".fit-latest, .fit-board" ? [latest, board].filter((x) => x && (has(x, "fit-latest") || has(x, "fit-board")))
    : s === ":scope > details.b-round.fit-hide" ? older.filter((x) => has(x, "fit-hide")) : []);
  [latest, board].forEach((x) => { if (x) x.parentElement = scene; });
}
const S = Object.assign({ stage: "game", tab: "jianghu", hearOpen: null, linesOpen: null, extraOpen: null, ownOpen: null, hintTight: false, hintOpen: false, renownTight: false,
  fitWidth: 0, main: { card_id: 7, scene: "<p>x</p>", on_road: false } }, input.S || {});
const pro = () => input.pro || null;
const idleMenu = () => input.idle !== false;
// 「還有 N 份邀請」那一行的字（FB-117，socialHtml 旁邊那一行 const）
const callsMoreText = new Function(`return ${src.match(/const callsMoreText = (.*);/)[1]}`)();
const H = new Function("S", "pro", "idleMenu", "renderTop", "callsMoreText", code
  + "\nreturn { fitFirstScreen, fitOver, ownOpen, fitOwnKey, fitOnResize, fitTopMoved, lineToggle, FIT_STEPS };")(S, pro, idleMenu, renderTop, callsMoreText);
HH = H;
const snap = () => ({
  fitted: S.fitted, bottom: bottom(), page: [...page.classes].sort(), card: card ? [...card.classes].sort() : null,
  box: box ? [...box.classes].sort() : null, hintTight: S.hintTight, tops, hearOpen: S.hearOpen, linesOpen: S.linesOpen,
  lines: lines.map((x) => [...x.classes].sort()), lineAttrs: lines.map((x) => x.attrs), rounds: rounds ? [...rounds.classes].sort() : null,
  now: now ? [...now.classes].sort() : null, scene: scene ? [...scene.classes].sort() : null, own: own.map((x) => x.attrs),
  ownClip: own.map((x) => has(x, "fit-clip")), musterClip: musterLines.map((x) => has(x, "fit-clip")),
  musterAttrs: musterLines.map((x) => x.attrs), menu: menu ? [...menu.classes].sort() : null,
  calls: callRows.map((x) => has(x, "fit-hide")), more: callsMore ? [callsMore.textContent, callsMore.dataset.fit || ""] : null,
  renownTight: S.renownTight, merit: meritSmalls.map((x) => has(x, "fit-hide")),
  art: art ? [...art.classes].sort() : null, extra: extra ? [...extra.classes].sort() : null, extraAttrs: extra ? extra.attrs : null,
  desc: descParas.map((x) => [...x.classes].sort()), descAttrs: descParas.map((x) => ({ ...x.attrs })), descClassAttr: descParas.map((x) => x.getAttribute("class")), descHead: descHead ? [...descHead.classes].sort() : null,
  latest: latest ? [...latest.classes].sort() : null, latestAttrs: latest ? { ...latest.attrs } : null,
  older: older.map((x) => has(x, "fit-hide")), board: board ? [...board.classes].sort() : null,
  chapter: chapter ? [...chapter.classes].sort() : null,
  peek: peek ? [...peek.classes].sort() : null, notes: notes.map((x) => has(x, "fit-hide")), nowWas: now ? now.dataset.fitWas || null : null,
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
def test_the_titles_line_folds_after_the_spacing_and_comes_back():
    """名聲 1B：名號底下那一行稱號排在留白之後收（記 S.renownTight、重畫狀態列，善惡稱號接到頭銜後面）；有空間了重量時還原。
    （狀態列的 💡 那一步拿掉了：提示句收進本週卡，減法季批 1）"""
    layout = {"bottom": 780, "actbar": True, "scene": True, "renown": True}
    script = """
      H.fitFirstScreen(); const tight = snap();
      L.bottom = 700; H.fitFirstScreen(); const roomy = snap();
      return { tight, roomy };"""
    out = run(layout, script)
    assert out["tight"]["fitted"] == ["space", "renown"] and out["tight"]["renownTight"] is True
    assert out["tight"]["bottom"] <= 740
    assert out["roomy"]["fitted"] == [] and out["roomy"]["renownTight"] is False


# 決戰輪到你出招（自檢 U-01）：場景卡、三招（選單最後一顆是第三招）、戰場裡最新一回合、更早的兩回合、本場戰功
TURN = {"bottom": 1000, "options": True, "scene": True, "turn": True, "latest": True, "older": 2, "board": True}


@node
def test_u01_on_your_turn_the_newest_round_folds_then_the_older_ones_then_the_board():
    """390×844 第 4 回合：三招落在分頁列底下。間距收完先把最新那一回合收成一行，再收更早的幾回合，矮手機才收本場戰功的名單；
    放得下就停。收起來的點了攤開（ownOpen），記住攤開過就不再收。"""
    out = run(TURN, tabsTop=788)
    assert out["fitted"][:1] == ["space"] and out["fitted"][-3:] == ["latest", "older", "board"]
    assert "fit-latest" in out["latest"] and out["latestAttrs"]["data-act"] == "own-more" and out["older"] == [True, True]
    assert "fit-board" in out["board"] and out["bottom"] <= 772
    roomy = run({**TURN, "bottom": 900}, tabsTop=788)
    assert "latest" in roomy["fitted"] and "board" not in roomy["fitted"] and roomy["board"] == ["g-merit"]
    opened = run(TURN, "H.fitFirstScreen(); H.ownOpen(); const a = snap(); H.fitFirstScreen(); return { a, b: snap() };", tabsTop=788)
    for o in (opened["a"], opened["b"]):
        assert o["latest"] == ["b-round", "latest"] and o["older"] == [False, False] and o["board"] == ["g-merit"]
    assert "latest" not in opened["b"]["fitted"]


@node
def test_u01_the_battle_folds_wait_for_your_turn():
    """只能觀戰、已經出過招（選單裡沒有三招）時戰場不收這幾樣。"""
    out = run({**TURN, "turn": False}, tabsTop=788)
    assert "latest" not in out["fitted"] and out["latest"] == ["b-round", "latest"] and out["older"] == [False, False]


@node
def test_the_battle_board_titles_fold_before_the_moves_are_squeezed():
    """名聲 4B：輪到出招時本場戰功名字底下的稱號排在第一回合之後收（名字照舊），三招不被擠出第一屏；鈕縫在它之後。"""
    out = run({"bottom": 785, "options": True, "merit": 3})
    assert out["fitted"] == ["space", "merit"] and out["merit"] == [True, True, True] and out["bottom"] <= 740
    again = run({"bottom": 785, "options": True, "merit": 3}, "H.fitFirstScreen(); L.bottom = 700; H.fitFirstScreen(); return snap();")
    assert again["fitted"] == [] and again["merit"] == [False, False, False]


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


# 名聲的俠寇選項讓事件多到六顆（企劃者 2026-10-16 從三張截圖挑 (c)）：場景、「剛剛」、態勢那一排、六顆鈕（一顆灰掉、底下一行原因）
EVENT = {"bottom": 860, "options": True, "peek": True, "now": True, "nowBody": 110, "notes": 1, "scene": True}


@node
def test_a_choice_menu_still_too_tall_folds_the_peek_row_the_now_story_and_the_greyed_reason():
    """第 10 步（choices）：鈕收緊了還放不下，態勢那一排收起、「剛剛」只留時間與標題（「展開全文」照舊在）、灰掉的鈕底下那一行原因收掉。"""
    out = run(EVENT, idle=False)
    assert out["fitted"] == ["space", "now", "options", "choices"] and out["bottom"] <= 740
    assert "fit-hide" in out["peek"] and out["notes"] == [True]
    assert "fit-title" in out["now"] and "clamp" in out["now"] and "fits" not in out["now"]


@node
def test_u09_the_chapter_card_folds_with_the_week_card_and_comes_back():
    """自檢 U-09：集結時遇上事件、對話，章回卡跟本週卡同一步（choices）收起，有空間重量時攤回來；閒著（行動列）時不收。"""
    out = run({**EVENT, "chapter": True, "bottom": 960}, "H.fitFirstScreen(); const a = snap(); L.bottom = 700; H.fitFirstScreen(); return { a, b: snap() };", idle=False)
    assert "choices" in out["a"]["fitted"] and "fit-hide" in out["a"]["chapter"] and out["a"]["bottom"] <= 740
    assert out["b"]["chapter"] == ["card", "ch-card"]
    idle = run({"bottom": 900, "actbar": True, "scene": True, "chapter": True})
    assert idle["chapter"] == ["card", "ch-card"]


@node
def test_the_buttons_tighten_before_any_words_are_hidden():
    """收緊鈕不少任何字：排在第 10 步前面；收緊就放得下的話，態勢那一排、「剛剛」的字、原因那一行都不動。"""
    out = run({**EVENT, "bottom": 815}, idle=False)
    assert out["fitted"] == ["space", "now", "options"] and out["bottom"] <= 740
    assert out["peek"] == ["peek"] and out["notes"] == [False] and "fit-title" not in out["now"]


@node
def test_the_choices_step_leaves_the_action_bar_page_alone():
    """閒著（行動列）時沒有這一步：態勢那一排是閒著時看戰況的地方。"""
    out = run({"bottom": 900, "actbar": True, "peek": True, "now": True, "nowBody": 110, "scene": True})
    assert "choices" not in out["fitted"] and out["peek"] == ["peek"] and "fit-title" not in out["now"]


@node
def test_what_the_player_opened_stays_open_and_a_title_only_now_is_left_alone():
    """攤開了態勢那一排的一格（.peek-panel 在）不收那一排；展開了「剛剛」不收它；「剛剛」本來就只有標題、沒有敘事時不動它。"""
    panel = run({**EVENT, "peekOpen": True}, idle=False)
    assert "choices" in panel["fitted"] and panel["peek"] == ["peek"] and panel["notes"] == [True]
    opened = run({**EVENT, "nowOpen": True}, idle=False)
    assert "choices" in opened["fitted"] and "fit-title" not in opened["now"] and "open" in opened["now"]
    bare = run({**EVENT, "nowLines": False}, idle=False)
    assert "fit-title" not in bare["now"]


@node
def test_a_now_card_that_fits_in_three_lines_gets_its_more_button_back():
    """「剛剛」三行就放得下（第 6 步換回 fits、沒有「展開全文」）：只留標題時字收掉了，換回收著，「展開全文」看得到全文。"""
    out = run({**EVENT, "nowFits": True, "nowBody": 60, "bottom": 900}, idle=False)
    assert "choices" in out["fitted"] and "fit-title" in out["now"] and "clamp" in out["now"] and "fits" not in out["now"]


@node
def test_the_choices_step_comes_back_when_there_is_room():
    """重量之前全部還原：態勢那一排、原因那一行攤回來，「剛剛」回到原本的樣子（本來放得下的 fits）。"""
    script = "H.fitFirstScreen(); const folded = snap(); L.bottom = 700; H.fitFirstScreen(); return { folded, roomy: snap() };"
    out = run({**EVENT, "nowFits": True}, script, idle=False)
    assert "choices" in out["folded"]["fitted"]
    roomy = out["roomy"]
    assert roomy["fitted"] == [] and roomy["peek"] == ["peek"] and roomy["notes"] == [False]
    assert roomy["now"] == ["fits", "now"] and roomy["nowWas"] is None


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
    js = webharness.app_source().replace("\r\n", "\n")
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


# ── 真的卡片：收起來的那幾樣不含得失與結果 ─────────────────────────


def _fight_card(on):
    import random

    from conftest import classic_rules
    from tianxia.engine import Game

    on.config.terrain_arts.enabled = False  # 地利那一句會讓得失接在「結果」後面（武學隨地理環境）；這裡驗的是沒有敘事的那張卡
    game = Game.new(classic_rules(on), "甲", rng=random.Random(0))  # 拿散人的遊歷打一場（出陣開著時散人沒有這顆鈕）
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
    """每一步一個 class；藏東西的只有收著的回合清單或大場面那一段話（展開 .open 就回來）、第 5c 步收掉的戰鬥補充，與第 6b 步收掉的邀請（FB-117：
    併進「還有 N 份邀請」那一行，點了攤開）；第 2、5 步是一行加「…」。"""
    css = _css()
    hiding = [sel for sel, body in re.findall(r"(?m)^([^{}\n@]*fit-[^{}\n]*)\{([^}]*)\}", css) if "display: none" in body]
    assert sorted(s.strip() for s in hiding) == sorted([
        # 第 5c 步（extra）：戰鬥補充第一行以後的（點那一塊整塊攤開，extraOpen）
        ".battle-card .tx-extra.fit-extra > .tx-line ~ .tx-line",
        ".battle-card p.rounds-tale.fit-fold:not(.open)", ".battle-card ul.rounds.fit-fold:not(.open)", ".call.fit-hide",
        ".g-mcol li .rn-two small.fit-hide",  # 名聲 4B：本場戰功名字底下那一行稱號（名字照舊）
        # 第 10 步（choices）：「剛剛」的敘事（展開 .open 就回來）、灰掉的鈕底下那一行原因（在鈕的 title，點了說整句）、態勢那一排
        ".now.fit-title:not(.open) .tx-now > .tx-line, .now.fit-title:not(.open) .tx-now > .tx-heading, .now.fit-title:not(.open) .tx-now > .tx-glyph",
        ".options > .btn.off .opt-note.fit-hide", ".page > .wk-card.fit-hide, .page > .ch-card.fit-hide",
        # 第 6a 步（front、front2）：出陣回報那一句、標題與其餘的條（點那一塊整塊攤開，frontOpen）
        ".sfront.fit-min .sf-head, .sfront.fit-min .sf-row ~ .sf-row", ".sfront.fit-tight .sf-text",
        # 第 5d～5f 步（latest、older、board；自檢 U-01）：最新一回合第一句以後的、更早的回合、本場戰功的名單（點了整張場景卡攤開，ownOpen）
        ".scene .b-round.latest.fit-latest > .b-lines > li", ".scene details.b-round.fit-hide, .g-merit.fit-board > .g-mcols",
    ])
    title = _rules(css, "fit-title")[".now.fit-title:not(.open) .tx-now"]
    assert "max-height: none" in title and "mask-image: none" in title  # 只剩標題：不淡出
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
    gaps = rules[".page.fit-space > .wk-card, .page.fit-space > .now, .page.fit-space > .card, .page.fit-space > .guide-line"]
    assert "margin-bottom: 8px" in gaps


def test_the_box_step_keeps_every_word_and_the_tap_target():
    """框收緊只動「知道了」佔的高度（鈕本身照樣 38px，上下 −9px）與話的行高；不 clamp、不藏字（設計 6.2：話不會被切掉）。
    玩家互動那幾塊（「此地還有」、結伴）是另一條線的：收的時候不碰它們的樣式；邀請只有第 6b 步那一條（FB-117，整列收掉）。"""
    css = _css()
    rules = _rules(css, "fit-box")
    assert set(re.findall(r"([\w-]+):", rules[".card.guide.fit-box .guide-head .btn"])) == {"margin-top", "margin-bottom"}
    assert rules[".card.guide.fit-box .guide-text"].strip() == "line-height: 1.5;"
    assert not any("clamp" in body or "display: none" in body or "overflow" in body for body in rules.values())
    fit_rules = re.findall(r"(?m)^([^{}\n@]*\bfit-[^{}\n]*)\{", css)
    others = [sel for sel in fit_rules if sel.strip() != ".call.fit-hide"]
    assert not any(re.search(r"\.(here|calls|call|party|peer)\b", sel) for sel in others), others


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
    js = webharness.app_source()
    assert '<div class="here">' in js and '<details class="fold here"' in js


# ── 場景的畫與戰鬥補充（2026-10-27：pull develop 之後打完一場，行動列被推出第一屏）────────────


ART_FIGHT = {"bottom": 1060, "actbar": True, "card": True, "lines": [False, False], "rounds": True, "scene": True, "art": True, "extra": 6}


@node
def test_a_tall_fight_with_scene_art_shrinks_the_art_then_folds_the_extra_lines():
    """戰鬥卡片＋場景有畫：第一回合收進「展開過程」之後先把畫縮成橫幅，還放不下才把補充收成一行；行動列回到第一屏。"""
    out = run(ART_FIGHT)
    assert out["fitted"][:5] == ["space", "lines", "rounds", "art", "extra"]
    assert "fit-art" in out["art"] and "fit-extra" in out["extra"] and out["bottom"] <= 756 - 16
    assert out["extraAttrs"] == {"data-act": "extra-more", "role": "button", "tabindex": "0", "aria-expanded": "false"}


@node
def test_the_art_alone_is_enough_when_it_is():
    out = run({**ART_FIGHT, "bottom": 1000})
    assert "art" in out["fitted"] and "extra" not in out["fitted"] and "fit-extra" not in out["extra"]


@node
def test_opened_extra_lines_stay_open_and_one_line_is_left_alone():
    out = run(ART_FIGHT, S={"extraOpen": 7})
    assert "extra" not in out["fitted"] and "fit-extra" not in out["extra"]
    assert "extra" not in run({**ART_FIGHT, "extra": 1})["fitted"]  # 只有一行：沒東西可收


@node
def test_refitting_brings_the_art_and_the_extra_lines_back():
    out = run(ART_FIGHT, script="H.fitFirstScreen(); L.bottom = 700; H.fitFirstScreen(); return snap();")
    assert out["fitted"] == [] and "fit-art" not in out["art"] and "fit-extra" not in out["extra"] and out["extraAttrs"] == {}


# ── 約戰卡第一張那一行要露在第一屏（FB-9006，企劃者 2026-10-28「要露出來」）──────────────────────
# 約戰卡排在行動列底下。真資料下「此地還有」只有一人時場景的畫不縮（約 267 px），卡從約 732～772 px 開始、分頁列頂在 756，375×812
# 只露出「約戰 N 張」標題，應戰、同去的鈕被擠到分頁列底下。第一張是應得了或同去得了的（sxRank 把可按的排最前面）時，收法量的改成那一行
# （連右邊的鈕）：它比行動列低，所以整排行動列一起照顧到，多縮的是場景的畫；沒有可按的約戰一個像素都不變


@node
def test_an_answerable_duel_row_squeezes_the_scene_art_so_its_button_is_on_the_first_screen():
    """756 − 16 = 740。行動列下緣 690 本來放得下（什麼都不收）；第一張約戰那一行的下緣在 780：間距收了 30 還差 10，再縮場景的畫就夠。"""
    layout = {"bottom": 690, "actbar": True, "scene": True, "art": True}
    assert run(layout)["fitted"] == []  # 沒有約戰：放得下，什麼都不收
    out = run({**layout, "duel": 90})
    assert out["fitted"] == ["space", "art"] and "fit-art" in out["art"]
    assert out["bottom"] + 90 <= 740  # 那一行的下緣（鈕整顆）在分頁列頂往上 16 以內


@node
def test_a_duel_row_that_already_fits_leaves_the_page_alone():
    out = run({"bottom": 600, "actbar": True, "scene": True, "art": True, "duel": 90})
    assert out["fitted"] == [] and out["page"] == ["page"] and out["art"] == ["scene-art"]


@node
def test_without_an_answerable_duel_the_first_screen_does_not_change_by_a_pixel():
    """只有自己貼的、結算完的、別區的、約戰關著，或行動列與約戰卡之間展開了別的卡：fitDuelRow 回 null，量的還是行動列。
    同一個行動列下緣 690、同一個場景：沒有可按的那一行就一個 class 都不加。"""
    base = run({"bottom": 690, "actbar": True, "scene": True, "art": True})
    assert base["fitted"] == [] and base["art"] == ["scene-art"] and base["page"] == ["page"]
    # 行動列自己放不下的畫面，收的步驟與停的地方跟以前一樣（有沒有那個欄位都一樣：沒有 duel 就是以前的量法）
    tall = run({"bottom": 960, "actbar": True, "scene": True, "art": True})
    assert tall["fitted"] == ["space", "art"] and tall["bottom"] <= 740


@node
def test_refitting_brings_the_art_back_once_there_is_no_answerable_duel_left():
    script = "H.fitFirstScreen(); const tight = snap(); L.duel = 0; H.fitFirstScreen(); return { tight, roomy: snap() };"
    out = run({"bottom": 690, "actbar": True, "scene": True, "art": True, "duel": 90}, script=script)
    assert out["tight"]["fitted"] == ["space", "art"]
    assert out["roomy"]["fitted"] == [] and out["roomy"]["art"] == ["scene-art"] and out["roomy"]["page"] == ["page"]  # 約戰被人應了：畫攤回來


@node
def test_the_selector_follows_the_real_markup_the_duel_card_draws():
    """fitDuelRow 的選擇器照 actionBar 真的畫出來的標記寫：約戰卡緊接在行動列後面（中間沒有展開的卡）、第一張那一行的鈕是那一行的直接孩子；
    灰的（應戰按不下去）、別區的（前往）、自己貼的那一張第一行不算。"""
    row = {"id": "d1", "block": "b", "place": "某地", "attacker": "甲", "attacker_side": "huang", "defender": None, "expires_in": 300, "answers_left": 3,
           "same_region": True, "travel_minutes": None, "result": None, "why_not": "", "can_answer": True, "can_join": False, "status": "open", "role": "answer"}
    m = {"options": [], "sorties": [row], "status": {}}
    bar = run_prologue_web(m, "return H.actionBar(H.S.main);")
    assert '<div class="card sx-duels" id="sortie-duels"><p class="sx-h">' in bar
    first = bar[bar.index('<div class="sx-drow'):]
    first = first[:first.index("</div>")]  # 第一張那一行（裡面只有 span 與一顆鈕，沒有再巢一層 div）
    assert '<button class="btn small primary" data-act="sortie-answer" data-id="d1">應戰</button>' in first and "<div" not in first[4:]
    src = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    sel = re.search(r"const FIT_DUEL_BTN = ('[^']*'\s*\+\s*'[^']*');", src).group(1)
    assert '#page > .act-bar + #sortie-duels > .sx-drow:first-of-type > [data-act="sortie-answer"]' in sel and '[data-act="sortie-join"]' in sel
    grey = run_prologue_web({**m, "sorties": [{**row, "can_answer": False, "why_not": "今日應戰 3 次已用完"}]}, "return H.actionBar(H.S.main);")
    assert 'data-act="sortie-answer"' not in grey  # 灰的那一行沒有可按的鈕：選擇器抓不到、量的還是行動列


# ── 約戰那一行擠完還放不下：再把場景卡的地點描述收成一行（企劃者 2026-10-28「擠完再上」）──────────────────
# FB-9006 讓量的目標改成約戰第一行之後，375×812 放得下，矮手機還是被分頁列蓋住（實機量：375×667 蓋約 10 px、360×700、320×700 蓋 4～6 px、
# 320×568 差一百多 px）：閒著時場景卡的地點描述從來不收（第 7 步 own 只收決戰集結時分隔線之後的）。收法多一步 desc（6c，排在 6b 邀請之後、
# 7 之前）：只在量的是約戰那一行時，把沒有分隔線的閒著場景卡的描述每段收成一行，點了整張場景卡攤開（own-more、S.ownOpen）。
# 「此地還有」、結伴、邀請、地名與時刻那一條（有畫時疊在畫上，沒有畫時是第一段）不是描述


# 行動列下緣 700、約戰那一行再低 90（＝790），沒有畫，描述兩段（沒有畫時第一段是「【地名】危險 ★★」那一條，另外算）
DESC = {"bottom": 700, "actbar": True, "scene": True, "desc": 2, "duel": 90}
FOLD_ATTRS = {"data-act": "own-more", "role": "button", "tabindex": "0", "aria-expanded": "false"}


@node
def test_a_short_phone_folds_the_place_description_to_bring_the_duel_button_up():
    """756 − 16 = 740。約戰那一行下緣 790：間距收了 30 還是 760（鈕還在分頁列的邊上），描述兩段各收成一行（各省 27）才到 706。
    地名那一條（沒有畫時的第一段）不收。"""
    out = run(DESC)
    assert out["fitted"] == ["space", "desc"] and out["desc"] == [["fit-clip"], ["fit-clip"]]
    assert out["descAttrs"] == [FOLD_ATTRS, FOLD_ATTRS] and "fit-own" in out["scene"]
    assert out["descHead"] == [] and out["bottom"] + 90 <= 740  # 那一行（鈕整顆）露在分頁列頂往上 16 以內


@node
def test_the_description_is_folded_after_the_art_and_the_steps_before_it():
    """順序：間距 → 畫縮成橫幅 → 描述；有畫時地名那一條疊在畫上、不在場景文字裡，兩段都是描述。"""
    out = run({**DESC, "bottom": 730, "art": True}, save={"art": 20})
    assert out["fitted"] == ["space", "art", "desc"] and out["desc"] == [["fit-clip"], ["fit-clip"]] and out["descHead"] is None
    assert out["bottom"] + 90 <= 740


@node
def test_the_description_stays_open_when_the_screen_has_room():
    """放得下的畫面描述不收：本來就放得下（什麼都不收）、前面的步驟就夠了（只收間距）。"""
    roomy = run({**DESC, "bottom": 600})
    assert roomy["fitted"] == [] and roomy["desc"] == [[], []] and roomy["descAttrs"] == [{}, {}] and "fit-own" not in roomy["scene"]
    enough = run({**DESC, "bottom": 680})  # 770 − 30 = 740：間距就夠
    assert enough["fitted"] == ["space"] and enough["desc"] == [[], []] and "fit-own" not in enough["scene"]


@node
def test_without_an_answerable_duel_the_description_is_never_folded():
    """目標是行動列（沒有可按的約戰：自己貼的、結算完的、別區的、約戰關著）：行動列放不下也只收別的步驟，描述一個字不動；
    有沒有描述那幾段，收的步驟與停的地方都一樣。"""
    tall = {"bottom": 900, "actbar": True, "scene": True}
    with_desc, without = run({**tall, "desc": 2}), run(tall)
    assert with_desc["fitted"] == without["fitted"] == ["space"] and with_desc["bottom"] == without["bottom"] == 870
    assert with_desc["desc"] == [[], []] and with_desc["descAttrs"] == [{}, {}] and "fit-own" not in with_desc["scene"]


@node
def test_the_description_under_a_battle_or_an_event_is_not_this_steps_business():
    """決戰集結（場景卡有分隔線）：這一步不做，分隔線之後照第 7 步收；事件、有所感（不是閒著的行動列）：那是 joy 的字，不收。"""
    battle = run({**DESC, "bottom": 800, "hr": True, "own": 2})
    assert "desc" not in battle["fitted"] and battle["desc"] == [[], []] and "own" in battle["fitted"]
    event = run({**DESC, "bottom": 800}, idle=False)
    assert "desc" not in event["fitted"] and event["desc"] == [[], []] and "fit-own" not in event["scene"]


@node
def test_a_description_with_digits_that_cannot_fit_on_one_line_is_left_alone():
    """同第 7 步：收成一行之後數字會藏到「…」後面的那一段不收，其餘照收。"""
    long_run = "黃河南岸的渡口，渡船往來不絕。往南的官道這裡通往潁川有 12 條路"  # 最後一個數字在第 19 個字之後：一行（300px，每字 15px）露不出來
    assert long_run.rindex("2") > 18
    out = run({**DESC, "texts": {"desc": [long_run, "渡口今日有 5 艘船"]}}, measure=True)
    assert out["desc"] == [[], ["fit-clip"]] and out["descAttrs"][0] == {} and out["descAttrs"][1] == FOLD_ATTRS


@node
def test_an_opened_description_stays_open_when_the_page_is_redrawn():
    """點了描述（ownOpen）：整張場景卡攤開，之後重畫（輪詢、轉向、拉視窗）不再收；換了地方才重新收；約戰被人應了、放得下之後重量，攤回來。"""
    script = """
      H.fitFirstScreen(); const folded = snap();
      H.ownOpen(); const opened = snap();
      H.fitFirstScreen(); const redrawn = snap();
      S.main = Object.assign({}, S.main, { status: { location: "guangzong" } }); H.fitFirstScreen(); const moved = snap();
      return { folded, opened, redrawn, moved, key: S.ownOpen };"""
    out = run(DESC, script, S={"main": {"card_id": 7, "on_road": False, "status": {"location": "baima_ford"}, "scene": "<p>【白馬津】危險 ★★</p><p>渡口。</p>"}})
    assert out["folded"]["fitted"] == ["space", "desc"] and out["folded"]["desc"] == [["fit-clip"], ["fit-clip"]]
    assert out["opened"]["desc"] == [[], []] and out["opened"]["descAttrs"] == [{}, {}] and "fit-own" not in out["opened"]["scene"]
    assert out["redrawn"]["fitted"] == ["space"] and out["redrawn"]["desc"] == [[], []] and out["key"]  # 攤開過的同一個地方：不再收
    assert out["moved"]["fitted"] == ["space", "desc"] and out["moved"]["desc"] == [["fit-clip"], ["fit-clip"]]  # 換了地方：重新收


@node
def test_refitting_gives_the_same_result_each_time_and_unfolds_when_the_duel_is_gone():
    """重畫、轉向、拉視窗之後重量：同一個畫面每一輪都收同樣幾步（先全部還原再收），不多收也不少收；沒有可按的約戰了，描述攤回來。"""
    script = """
      H.fitFirstScreen(); const a = snap();
      H.fitFirstScreen(); const b = snap();
      W.innerWidth = 320; H.fitOnResize(); const c = snap();
      L.duel = 0; H.fitFirstScreen(); const gone = snap();
      return { a, b, c, gone };"""
    out = run(DESC, script)
    assert out["a"]["fitted"] == out["b"]["fitted"] == out["c"]["fitted"] == ["space", "desc"]
    assert out["a"]["desc"] == out["b"]["desc"] == out["c"]["desc"] == [["fit-clip"], ["fit-clip"]] and out["a"]["bottom"] == out["c"]["bottom"]
    assert out["gone"]["fitted"] == [] and out["gone"]["desc"] == [[], []] and out["gone"]["descAttrs"] == [{}, {}]  # 行動列 700 本來放得下
    assert "fit-own" not in out["gone"]["scene"]


@node
def test_the_description_is_folded_again_after_every_refit_that_does_not_redraw():
    """FB-9010：沒有重畫的重量（轉向再轉回、視窗寬 375→376→375、點名號展開再收起）都從 fitReset 開始：先把收成一行的描述攤回來、再量。
    真的瀏覽器的 classList 拿光 class 之後留下空的 class=""，第 6c 步的選擇器 :scope > p:not([class]) 就再也選不到那一段（假 DOM 照這樣做），
    折疊從第二次量起消失、約戰鈕掉回分頁列底下（實機 375×667 −18.4 → +8.7、360×700 −51.4 → +2.9）。每一種之後：描述還收著、鈕整顆在第一屏。"""
    script = """
      H.fitFirstScreen(); const first = snap();
      W.innerWidth = 376; H.fitOnResize(); const wider = snap();
      W.innerWidth = 375; H.fitOnResize(); const back = snap();
      const h0 = els.top.offsetHeight; els.top.offsetHeight = h0 + 80; H.fitTopMoved(h0); const expanded = snap();
      els.top.offsetHeight = h0; H.fitTopMoved(h0 + 80); const collapsed = snap();
      H.fitFirstScreen(); const again = snap();
      return { first, wider, back, expanded, collapsed, again };"""
    out = run(DESC, script)
    for name, shot in out.items():
        assert shot["fitted"] == ["space", "desc"], name
        assert shot["desc"] == [["fit-clip"], ["fit-clip"]] and shot["descAttrs"] == [FOLD_ATTRS, FOLD_ATTRS], name
        assert shot["bottom"] + 90 <= 740, name  # 約戰鈕整顆露在分頁列頂往上 16 以內


@node
def test_unfolding_a_description_leaves_no_empty_class_attribute_behind():
    """FB-9010 的根：收成一行（加 fit-clip）再攤回來（拿掉 fit-clip），那一段又沒有 class 屬性了（不是空的 class=""），下一次量還選得到。
    攤回來有兩條路：重量時 fitReset、點了描述 ownOpen；還有一條是收了才發現數字會被「…」吞掉、當場退回的那一段。"""
    script = """
      H.fitFirstScreen(); const folded = snap();
      L.duel = 0; H.fitFirstScreen(); const reset = snap();
      L.duel = 90; H.fitFirstScreen(); H.ownOpen(); const opened = snap();
      return { folded, reset, opened };"""
    out = run(DESC, script)
    assert out["folded"]["descClassAttr"] == ["fit-clip", "fit-clip"]
    assert out["reset"]["descClassAttr"] == [None, None] and out["opened"]["descClassAttr"] == [None, None]
    long_run = "黃河南岸的渡口，渡船往來不絕。往南的官道這裡通往潁川有 12 條路"  # 數字在一行（300px）之外：收了就退回，那一段不是空的 class=""
    edge = run({**DESC, "texts": {"desc": [long_run, "渡口今日有 5 艘船"]}}, measure=True)
    assert edge["desc"] == [[], ["fit-clip"]] and edge["descClassAttr"] == [None, "fit-clip"]


def _html_tree(html: str) -> dict:
    from html.parser import HTMLParser

    void = {"img", "hr", "br", "input", "meta", "link", "source"}
    root = {"tag": "#", "attrs": {}, "kids": [], "text": ""}
    stack = [root]

    class Reader(HTMLParser):
        def handle_starttag(self, tag, attrs):
            node = {"tag": tag, "attrs": dict(attrs), "kids": [], "text": ""}
            stack[-1]["kids"].append(node)
            if tag not in void:
                stack.append(node)

        def handle_startendtag(self, tag, attrs):
            stack[-1]["kids"].append({"tag": tag, "attrs": dict(attrs), "kids": [], "text": ""})

        def handle_endtag(self, tag):
            while len(stack) > 1 and stack[-1]["tag"] != tag:
                stack.pop()
            if len(stack) > 1:
                stack.pop()

        def handle_data(self, data):
            for node in stack[1:]:
                node["text"] += data

    Reader().feed(html)
    return root


def _scene_card(node: dict) -> dict | None:
    classes = node["attrs"].get("class", "").split()
    if node["tag"] == "section" and "card" in classes and "scene" in classes:
        return node
    for kid in node["kids"]:
        found = _scene_card(kid)
        if found:
            return found
    return None


@node
@pytest.mark.parametrize("with_art", [True, False])
def test_the_description_selector_follows_the_real_scene_markup(on, with_art):
    """第 6c 步的選擇器（app.js：場景卡直接孩子裡沒有 class 的 <p>，沒有畫時去掉第一段）照真的場景卡寫：有畫時地名那一條疊在畫上、
    場景文字裡拿掉；沒有畫時它是第一段；「此地還有」、邀請、結伴是 <div>，選不到。"""
    game = Game.new(on, "甲", rng=random.Random(0))
    game.client = None
    m = server.main_view(game)
    paras = re.findall(r"<p>(.*?)</p>", m["scene"], re.S)
    head, desc = paras[0], paras[1:]
    assert head.startswith("【") and desc
    m["art"] = ({"kind": "place", "src": "/static/img/places/world.webp", "title": "某地", "sub": "危險 ★", "time": "第 1 天 08:00", "head": f"<p>{head}</p>"}
                if with_art else None)
    m["here"] = [{"name": "沈伯安", "side": "黃巾軍"}]
    m["calls"] = [{"text": "有人跟你打招呼", "options": [{"id": "invite:accept:1", "label": "回禮", "enabled": True}]}]
    m["party"] = {"text": "你與某人結伴同行", "lead": False}
    kids = _scene_card(_html_tree(run_prologue_web(m, "return H.pageJianghu();")))["kids"]
    drawn_art = any("scene-art" in k["attrs"].get("class", "") for k in kids)
    assert drawn_art is with_art
    picked = [k for k in kids if k["tag"] == "p" and "class" not in k["attrs"]]
    if not drawn_art:
        assert picked[0]["text"].startswith("【")  # 第一段是地名那一條
        picked = picked[1:]
    norm = lambda text: " ".join(re.sub(r"<[^>]*>", "", text).split())  # noqa: E731
    assert [norm(k["text"]) for k in picked] == [norm(d) for d in desc]
    divs = {k["attrs"].get("class") for k in kids if k["tag"] == "div"}
    assert {"here", "calls"} <= divs and not any(k["tag"] == "p" and "here" in k["attrs"].get("class", "") for k in kids)
    src = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    assert 'scene.querySelectorAll(":scope > p:not([class])")' in src and 'scene.querySelector(":scope > .scene-art")' in src


def test_the_art_and_extra_folds_are_styled():
    css = _css()
    assert re.search(r"(?m)^\.card\.scene > \.scene-art\.fit-art \{[^}]*height: 84px", css)
    assert re.search(r'(?m)^\.battle-card \.tx-extra\.fit-extra::after \{[^}]*content: "展開全文 ▾"', css)


# ── 原 test_fb123_fit_baseline.py（整檔搬進來） ──
# FB-123（QA 32efa2c6，2026-10-09）：FB-107 收合的兩個殘留（web/app.js 的 fitOver、fitFirstScreen、renderTop）。
#
# 1. 量的基準跟著網址列跑：分頁列固定在畫面底下，手機捲動時網址列收起、跑出來，分頁列跟著上下移幾十 px。集結時倒數每一輪都整頁重畫、
#    重量，拿當下的分頁列頂量的話，網址列每換一次狀態第一屏就多收或少收一步、畫面跟著跳。現在同一個寬度記住量到過最小的分頁列頂
#    （網址列跑出來的時候；一開頁面、捲回頂端都是這樣）當基準，寬度變了（轉向、拉視窗）重記；打字時（輸入框有焦點，舊的 Android
#    會因為鍵盤縮小視窗）不記。
# 2. 狀態列變高變矮不重量：點名號展開配點就照展開的高度收到底，收起名號之後那幾樣還收著，要等下一個動作；💡 冒出來或變兩行，
#    行動列被推下去也不重收。現在 renderTop 重畫狀態列前後量一次 #top 的高度，變了就重量（fitTopMoved）；fitFirstScreen 自己收 💡、
#    還原 💡 時也會重畫狀態列，那時不算（S.fitting），不會一直重量。
#
# 假頁面照 tests/test_jianghu_page_web.py 的驅動程式（從 app.js 切出 FB-107 那一段；scripts/test_for.py 靠 import 與 app.js 這個名字挑到這裡）。

# ── 1. 網址列收起、跑出來：基準不跟著跑 ─────────────────────────────


@node
def test_the_url_bar_hiding_does_not_unfold_a_step_on_the_next_redraw():
    """收了間距與對手的描述（756 − 16 = 740，行動列在 790）；捲下去網址列收起、分頁列移到 812，下一輪倒數重畫：照舊收這兩步，
    畫面不跳。網址列再跑出來也一樣。"""
    script = """
      H.fitFirstScreen(); const first = snap();
      els.setTabsTop(812); H.fitFirstScreen(); const hidden = snap();
      els.setTabsTop(756); H.fitFirstScreen(); const shown = snap();
      return { first, hidden, shown };"""
    out = run({**FIGHT, "bottom": 790}, script)
    assert out["first"]["fitted"] == ["space", "lines"]
    assert out["hidden"]["fitted"] == ["space", "lines"] and out["shown"]["fitted"] == ["space", "lines"]


@node
def test_a_first_measure_with_the_url_bar_hidden_tightens_once_when_it_shows_and_then_holds():
    """第一次量的時候網址列剛好收著（812）：放得下、不收；網址列跑出來（756）：收到放得下為止；之後再收起來：不攤回去（基準記最小的）。"""
    script = """
      els.setTabsTop(812); H.fitFirstScreen(); const hidden = snap();
      els.setTabsTop(756); H.fitFirstScreen(); const shown = snap();
      els.setTabsTop(812); H.fitFirstScreen(); const again = snap();
      return { hidden, shown, again };"""
    out = run({**FIGHT, "bottom": 790}, script)
    assert out["hidden"]["fitted"] == [] and out["shown"]["fitted"] == ["space", "lines"]
    assert out["again"]["fitted"] == ["space", "lines"]


@node
def test_a_width_change_takes_a_new_baseline():
    """橫著拿（寬 812、分頁列頂 330）量過，再轉回直的（寬 375、分頁列頂 756）：照新的寬度重記基準，不沿用橫的那個小的。"""
    script = """
      W.innerWidth = 812; els.setTabsTop(330); L.bottom = 300; H.fitFirstScreen(); const wide = snap();
      W.innerWidth = 375; els.setTabsTop(756); L.bottom = 790; H.fitOnResize(); const tall = snap();
      return { wide, tall, base: S.fitBase };"""
    out = run(FIGHT, script)
    assert out["wide"]["fitted"] == [] and out["tall"]["fitted"] == ["space", "lines"]
    assert out["base"] == {"width": 375, "top": 756}


@node
def test_typing_does_not_lower_the_baseline():
    """輸入框有焦點（隨口應對、放手一搏）：舊的 Android 鍵盤會把視窗縮小、分頁列頂跳上來幾百 px——這時量到的不記成基準，
    收起鍵盤之後不會整頁收到底。"""
    script = """
      H.fitFirstScreen(); const before = snap();
      globalThis.document.activeElement = { tagName: "INPUT" }; els.setTabsTop(430); H.fitFirstScreen();
      globalThis.document.activeElement = null; els.setTabsTop(756); H.fitFirstScreen(); const after = snap();
      return { before, after, base: S.fitBase };"""
    out = run({**FIGHT, "bottom": 790}, script)
    assert out["before"]["fitted"] == ["space", "lines"] and out["after"]["fitted"] == ["space", "lines"]
    assert out["base"]["top"] == 756


# ── 2. 狀態列變高變矮：重量 ─────────────────────────────


@node
def test_a_taller_status_bar_refits_and_a_shorter_one_unfolds_again():
    """點名號展開配點（狀態列高 120 → 300，行動列跟著往下 180）：當場重量、收到放得下；收起名號（回到 120）：當場重量、全部攤回來。
    高度沒變（重畫的只是數字）：不重量。"""
    script = """
      H.fitFirstScreen(); const plain = snap();
      els.top.offsetHeight = 300; L.bottom += 180; H.fitTopMoved(120); const open = snap();
      els.top.offsetHeight = 120; L.bottom -= 180; H.fitTopMoved(300); const shut = snap();
      S.fitted = ["mark"]; H.fitTopMoved(120); const same = S.fitted;
      return { plain, open, shut, same };"""
    out = run({**FIGHT, "bottom": 730}, script)
    assert out["plain"]["fitted"] == []
    assert out["open"]["fitted"][:2] == ["space", "lines"] and "rounds" in out["open"]["fitted"]
    assert out["shut"]["fitted"] == [] and out["shut"]["page"] == ["page"] and out["shut"]["rounds"] == ["rounds"]
    assert out["shut"]["lines"] == [["tx-line"]]
    assert out["same"] == ["mark"]


@node
def test_the_hint_showing_up_pushes_the_row_down_and_refits():
    """體力回到付得起合成時 💡 冒出來（狀態列多 40）：行動列被推下去，當場重量。"""
    script = """
      H.fitFirstScreen(); const before = snap();
      els.top.offsetHeight = 160; L.bottom += 40; H.fitTopMoved(120); const after = snap();
      return { before, after };"""
    out = run({**FIGHT, "bottom": 740}, script)
    assert out["before"]["fitted"] == [] and out["after"]["fitted"] == ["space", "lines"]


@node
def test_folding_the_titles_inside_a_fit_does_not_start_another_fit():
    """fitFirstScreen 收名號底下那一行稱號（S.renownTight、重畫狀態列；以前是 💡，減法季批 1 收進本週卡）時狀態列自己變矮，還原時又變高：那是收合本身，不再重量（不然會一直重量）。
    renderTop 照真的那樣先量、重畫、再交給 fitTopMoved。"""
    layout = {"bottom": 790, "actbar": True, "scene": True, "renown": True, "card": True, "lines": [False], "rounds": True}
    script = """
      H.fitFirstScreen(); const tight = snap();
      L.bottom = 700; H.fitFirstScreen(); const roomy = snap();
      return { tight, roomy, fitting: !!S.fitting };"""
    out = run(layout, script, realTop=True, topSaves=20)
    assert out["tight"]["fitted"] == ["space", "renown"] and out["tight"]["tops"] == 1
    assert out["roomy"]["fitted"] == [] and out["roomy"]["tops"] == 2 and out["fitting"] is False


RENDER_TOP = r"""
// renderTop 本身（FB-123）：重畫狀態列之前量 #top 的高度，重畫完交給 fitTopMoved
const code = fn("renderTop");
const top = { _html: "", offsetHeight: 120, hidden: false };
Object.defineProperty(top, "innerHTML", { get() { return this._html; }, set(v) { this._html = v; this.offsetHeight = v.length > 5 ? 300 : 120; } });
globalThis.document = { getElementById: (id) => (id === "top" ? top : null) };
const S = { prologueKey: "k" };
const seen = [];
// fitBars（FB-198）：狀態列畫好之後量「體力」「氣血」兩個字放不放得下——要在新的內容寫進去之後叫
const H = new Function("S", "prologueKey", "topHtml", "applyGlow", "render", "fitTopMoved", "fitBars", code + "\nreturn { renderTop };")(
  S, () => "k", () => input.html, () => {}, () => {}, (before) => seen.push([before, top.offsetHeight]), () => seen.push(["fitBars", top.offsetHeight]));
H.renderTop();
finish(seen);
"""


@node
def test_render_top_hands_the_height_before_the_redraw_to_fit_top_moved():
    assert webharness.run(RENDER_TOP, {"html": "<div>展開的名號</div>"}) == [["fitBars", 300], [120, 300]]


# ── 原 test_fb120_battle_fold.py（整檔搬進來） ──
# FB-120（QA 32efa2c6，2026-10-09，375×812）：全服決戰開打的那段時間，戰場那一塊把每個人的第一屏都佔掉。
#
# Game.scene_text 有全服決戰時大家都看得到戰場：只能觀戰的人是戰場＋分隔線＋自己眼前的事。開打後每回合多一句開頭、放手一搏的原文與
# 模型的故事，最近 5 段都在；QA 量到宛城開打、官軍站在潁川時師父的框在 1130、行動列 1226～1324（分頁列頂 756）。
#
# 現在（只改網頁，web/app.js 的 battleScene）：沒在打這一場的人（人不在決戰的大區、沒加入、沒臨時投效），場景裡開打中的戰場收成一行
# 「宛城之戰　第 N 回合・點開看」（待 joy 潤，字在 app.js 的 BATTLE_PEEK），點了攤開、底下多一顆「收起戰場」（BATTLE_SHUT）；
# 攤開記的是戰場的名字（S.battleOpen），回合往下走、輪詢重畫都不收回去，自己按收起或這一場打完才算。參戰的人照舊。
#
# 認的是伺服器給的場景（Markdown 轉好的 HTML）：分隔線（<hr />）之前那一段有開打後的回合數（「（第 N／M 回合」）、而且不是參戰者的那一句
# （離開大區的「這回合不出手」、倒下的「你已經倒下」）。兩個正規式（BATTLE_ROUND、BATTLE_MINE）寫在 app.js、這裡用真的戰場驗：
# 戰鬥那條線（FB-109、FB-113）改了 _battle_scene_text 的寫法，這裡就紅。
#
# 網頁用真實內容（週末設定）的宛城之戰、真的 /api/main，照 tests/test_prologue_web.py 的做法把整支 app.js 放進 node
# （scripts/test_for.py 改到 app.js 時靠這個檔名挑到這裡）。

BATTLE = "wancheng_jia"  # 宛城之戰（南陽）


def _player(on, name, faction, place):
    game = Game.new(on, name, rng=random.Random(0))
    game.client = None
    game.set_hints_off(True)
    game.state.player.faction, game.state.player.location = faction, place
    return game


def _fight_round(fighter):
    """參戰的那一個送出這一回合（場上只有他，送出就結算）。對面沒人、一回合推滿 push_max（正式 20），戰局先拉回中線，免得兩回合就收場。"""
    fighter.world.mutate_battle(lambda b: setattr(b, "trend", 50))
    move = next(o.id for o in fighter.options(odds=False) if o.enabled and o.id.startswith("battle:act:"))
    fighter.choose(move)


def _text(html):
    """拿掉標籤與空白只比字：戰況一回合一段（app.js 的 roundBlocks）會把伺服器的回合標題與清單換成自己的標記，字一個不少（收成一行的舊回合多寫一次摘要，不算）。"""
    html = re.sub(r"<summary><b>(.*?)</b><span>.*?</span></summary>", r"\1", html)  # 收成一行的舊回合：那一句摘要底下清單裡還有
    return re.sub(r"\s+", "", re.sub(r"<[^>]*>", "", html))


@pytest.fixture
def battle(on):
    """宛城之戰開打、打過一回合：一個臨時投效官軍的散人在宛城打，一個官軍的人站在潁川（QA 那一場）。"""
    watcher = _player(on, "觀戰甲", "guan", "yingchuan")
    fighter = _player(on, "參戰乙", None, "wan_city")
    watcher.world.start_battle(on.battles[BATTLE], now=watcher.now)
    fighter.choose("battle:enlist:guan")
    fighter.world.mutate_battle(lambda b: setattr(b, "muster_deadline_real", -1.0))
    fighter.options()
    assert fighter.world.get_battle().phase == "active"
    _fight_round(fighter)
    return watcher, fighter


def _consts():
    driver = ('finish(new Function(konst("BATTLE_PEEK") + "\\n" + konst("BATTLE_SHUT") + '
              '"\\nreturn { peek: BATTLE_PEEK, shut: BATTLE_SHUT };")());')
    return webharness.run(driver, {})


def _scene(page):
    """場景卡的內容，拿掉戰局條（它自己的測試在 test_battle_gauge.py）：這裡比的是伺服器給的那一段文字。"""
    scene = re.search(r'<section class="card scene">(.*?)</section>', page, re.S).group(1)
    start = scene.find('<div class="gauge"')
    if start < 0:
        return scene
    depth = 0
    for tag in re.finditer(r"<(/?)div\b", scene[start:]):  # 戰局條裡還有好幾層 div：數到對應的那一個收尾
        depth += -1 if tag.group(1) else 1
        if depth == 0:
            end = scene.index(">", start + tag.start()) + 1
            return scene[:start] + scene[end:]
    return scene


def _round(m):
    return int(re.search(r"（第 (\d+)／\d+ 回合", m["scene"]).group(1))


def _folded(m):
    return (f'<p class="battle-fold" data-act="battle-open" role="button" tabindex="0" aria-expanded="false">'
            f'宛城之戰　第 {_round(m)} 回合・{_consts()["peek"]}</p>')


CLICK = """const tap = async (act) => { const el = { dataset: { act }, classList: { contains: () => false } };
  await T.docListeners.click[0]({ target: { closest: () => el } }); return T.els.page.innerHTML; };"""


def _sided(html):
    """戰報裡「〔官軍〕」開頭的那一句（有人發動戰法；開局的【基礎吐納】就帶小戰法），網頁畫成陣營的小章（觀戰的是官軍：官軍・我方）。"""
    import re
    # 網頁把「〔招名〕某某……」畫成「某某……〔招名〕」（app.js 的 trailMoves，招式與絕學稿案第一節）
    return re.sub(r"〔官軍〕〔([^〕]+)〕([^〔]*?)(?=【|$)", r"官軍・我方\2〔\1〕", _text(html))


# ── 只能觀戰的人：收成一行，點了攤開 ─────────────────────────────


@node
def test_a_spectator_sees_the_running_battle_as_one_line(battle):
    watcher, _ = battle
    m = server.main_view(watcher)
    battle_part, own = m["scene"].split("<hr />", 1)
    assert "回合" in battle_part and "這場決戰在南陽" in battle_part and "act:explore" in [o["id"] for o in m["options"]]
    scene = _scene(run_prologue_web(m, "return H.pageJianghu();"))
    assert scene.startswith(_folded(m) + "\n<hr />")  # 戰場那一塊只剩一行，分隔線之後照舊
    assert own in scene  # 自己眼前的事（所在地）一個字不動
    assert "這一回合" not in scene and "這場決戰在南陽" not in scene  # 戰報與觀戰的原因都收起來了
    assert _consts()["shut"] not in scene


@node
def test_a_gamble_that_quotes_a_participants_line_does_not_unfold_it(battle):
    """審查 M1：放手一搏的原文與模型的故事照字寫進戰報（最近五段都在戰場那一塊）。有人寫「你已經倒下」「這回合不出手」，
    每個觀戰的人的戰場也不能因此整段攤開：參戰者的那一句只認戰場那一塊的最後一段（引擎寫看戰場的原因的地方）。"""
    watcher, fighter = battle
    fighter.submit_battle_custom_action("你已經倒下這回合不出手", 35, ("他大喊：你已經倒下了！", "他說這回合不出手，轉身就走。"))
    m = server.main_view(watcher)
    battle_part = m["scene"].split("<hr />", 1)[0]
    assert "你已經倒下這回合不出手" in battle_part and "這場決戰在南陽" in battle_part.rsplit("<p>", 1)[1]
    scene = _scene(run_prologue_web(m, "return H.pageJianghu();"))
    assert scene.startswith(_folded(m) + "\n<hr />")


@node
def test_tapping_opens_it_and_it_stays_open_while_the_rounds_go_on_until_folded(battle):
    watcher, fighter = battle
    first = server.main_view(watcher)
    _fight_round(fighter)
    second = server.main_view(watcher)
    assert _round(second) == _round(first) + 1
    script = CLICK + """return (async () => {
      H.S.tab = "jianghu"; H.renderPage(); const folded = T.els.page.innerHTML;
      const opened = await tap("battle-open"); const key = H.S.battleOpen;
      const was = H.S.main; H.setMain(H.S.next); await H.refreshPage(was); const polled = T.els.page.innerHTML;
      const shut = await tap("battle-shut");
      return { folded, opened, key, polled, shut, after: H.S.battleOpen };
    })();"""
    out = run_prologue_web(first, script, S={"next": second})
    shut_btn = (f'<p class="battle-shut"><button class="linkish" data-act="battle-shut" aria-expanded="true">'
                f'{_consts()["shut"]}</button></p>')
    assert _folded(first) in out["folded"]
    battle_first = first["scene"].split("<hr />", 1)[0]
    assert _sided(battle_first + shut_btn) in _text(_scene(out["opened"])) and out["key"] == "宛城之戰"  # 整段攤開，記的是戰場的名字
    battle_second = second["scene"].split("<hr />", 1)[0]
    assert _sided(battle_second + shut_btn) in _text(_scene(out["polled"]))  # 下一回合輪詢重畫：照舊攤開，寫的是新的回合
    assert _folded(second) in out["shut"] and out["after"] is None  # 按收起：收回一行（新的回合數）


@node
def test_the_keyboard_opens_the_folded_line(battle):
    watcher, _ = battle
    m = server.main_view(watcher)
    script = """
      H.S.tab = "jianghu"; H.renderPage();
      const target = Object.assign(Object.create(T.Element.prototype), { matches: (sel) => sel === '.battle-fold[data-act="battle-open"]' });
      let prevented = false;
      for (const fn of T.docListeners.keydown) fn({ key: "Enter", target, preventDefault: () => { prevented = true; } });
      return { prevented, open: H.S.battleOpen, page: T.els.page.innerHTML };"""
    out = run_prologue_web(m, script)
    assert out["prevented"] and out["open"] == "宛城之戰" and _sided(m["scene"].split("<hr />", 1)[0]) in _text(_scene(out["page"]))


@node
def test_focus_goes_back_to_the_toggle_after_opening_and_folding(battle):
    """審查 M4：攤開、收起都整頁重畫，原本有焦點的那一行（那一顆）不見了：焦點放回新畫出來的開關（同戰況圖卡的做法），
    鍵盤再按一次就能收起、再攤開。"""
    watcher, _ = battle
    m = server.main_view(watcher)
    script = CLICK + """return (async () => {
      H.S.tab = "jianghu"; H.renderPage();
      const focused = [];
      T.qs['#page .battle-shut button'] = { focus: () => focused.push("shut") };
      T.qs['#page .battle-fold'] = { focus: () => focused.push("fold") };
      const target = Object.assign(Object.create(T.Element.prototype), { matches: (sel) => sel === '.battle-fold[data-act="battle-open"]' });
      for (const fn of T.docListeners.keydown) fn({ key: "Enter", target, preventDefault: () => {} });
      const afterOpen = focused.slice();
      await tap("battle-shut");
      return { afterOpen, afterShut: focused.slice(afterOpen.length), open: H.S.battleOpen };
    })();"""
    out = run_prologue_web(m, script)
    assert out["afterOpen"] == ["shut"] and out["afterShut"] == ["fold"] and out["open"] is None


@node
def test_the_open_state_is_forgotten_when_the_battle_is_over(battle):
    """打完了（場景裡沒有開打中的回合）：記著的攤開清掉，下一場開打照舊先收著。"""
    watcher, _ = battle
    m = server.main_view(watcher)
    calm = {**m, "scene": m["scene"].split("<hr />\n", 1)[1]}
    script = """
      H.S.battleOpen = "宛城之戰"; H.S.main = H.S.calm; H.pageJianghu(); const cleared = H.S.battleOpen;
      H.S.main = m; return { cleared, page: H.pageJianghu() };"""
    out = run_prologue_web(m, script, S={"calm": calm})
    assert out["cleared"] is None and _folded(m) in out["page"]


# ── 參戰的人、集結時：照舊 ─────────────────────────────


@node
def test_a_participant_sees_the_whole_battle(battle):
    _, fighter = battle
    m = server.main_view(fighter)
    assert "<hr />" not in m["scene"] and "battle:act:" in "".join(o["id"] for o in m["options"])
    scene = _scene(run_prologue_web(m, "return H.pageJianghu();"))
    assert "battle-fold" not in scene and "這一回合" in scene


@node
def test_a_participant_who_walked_out_of_the_region_is_not_folded(battle):
    """參戰後離開了南陽（這回合不出手、回去就能再出手）：他是這一場的人，戰場照舊整段。"""
    _, fighter = battle
    fighter.state.player.location = "yingchuan"
    fighter._sync_battle_presence()  # noqa: SLF001  出發、抵達時引擎自己記；這裡直接把人放到潁川
    m = server.main_view(fighter)
    assert "<hr />" in m["scene"] and "這回合不出手" in m["scene"]
    scene = _scene(run_prologue_web(m, "return H.pageJianghu();"))
    assert "battle-fold" not in scene and "這一回合" in scene


@node
def test_a_scene_with_enlist_buttons_on_the_name_line_is_not_folded(battle, on):
    """審查 M5：名字那一行有加入或臨時投效的鈕（musterJoins）時不收——收了的話那幾顆鈕就沒地方畫。開打後人在決戰的大區、
    還沒投效的散人就是這一種：引擎在戰場底下接自己眼前的事（FB-109），網頁照舊整段、鈕排在名字那一行。"""
    drifter = server.main_view(_player(on, "散人丙", None, "wan_city"))
    assert [o["id"] for o in drifter["options"] if o["id"].startswith("battle:")] == ["battle:enlist:guan", "battle:enlist:huang"]
    assert "<hr />" in drifter["scene"] and "回合" in drifter["scene"].split("<hr />", 1)[0]
    scene = _scene(run_prologue_web(drifter, "return H.pageJianghu();"))
    assert "battle-fold" not in scene and "這一回合" in scene
    assert scene.startswith('<div class="muster-head"><p><strong>宛城之戰</strong></p>')
    assert re.findall(r'data-id="(battle:enlist:\w+)"', scene) == ["battle:enlist:guan", "battle:enlist:huang"]


@node
def test_a_muster_is_left_to_the_first_screen_fit(on):
    """還在集結（沒有回合數）：不歸這裡收，照舊是 FB-107 收集結那一句。"""
    watcher = _player(on, "觀戰甲", "guan", "yingchuan")
    watcher.world.start_battle(on.battles[BATTLE], now=watcher.now)
    m = server.main_view(watcher)
    assert "集結中" in m["scene"] and "<hr />" in m["scene"]
    assert "battle-fold" not in _scene(run_prologue_web(m, "return H.pageJianghu();"))


# ── 第一屏收合（FB-107）不收攤開了的戰場 ─────────────────────────────


@node
def test_the_fit_does_not_clip_a_battle_the_player_opened():
    """攤開的戰場（場景卡裡有「收起戰場」那一行）：第一屏放不下時，第 8 步不把它的每一段收成一行（玩家自己攤開的不收）。"""
    layout = {"bottom": 800, "actbar": True, "scene": True, "muster": 3, "join": False, "hr": True, "own": 2}
    plain = run(layout)
    assert "muster" in plain["fitted"]
    opened = run({**layout, "battleShut": True})
    assert "muster" not in opened["fitted"] and opened["musterClip"] == [False, False, False]


# ── 原 test_fb087_here_fold.py（整檔搬進來） ──
# FB-087：江湖頁「此地還能做 N 件事」摺疊被重畫收起來（QA 驗 FB-077，2026-10-06，375×812）。
#
# 摺疊裡的按鈕（例：求見盧植）被擋下來（「對方還沒答話，稍等。」、排太久）之後，choose() 重畫整頁、摺疊就收起來了；輪詢帶來新畫面時
# renderPage() 也一樣。現在摺疊的開合記在 S.here（玩家自己開關的、這一處），重畫照它補回。附帶 guide-3b 審查 Minor 11：入伍段第一道軍令
# 那一步（框上帶 glow act:duty）摺疊本來每次重畫都自動打開、跟收起它的玩家打架——現在每一處只在那一步開頭自動打開一次，之後照玩家的。
#
# 網頁沒有建置步驟也沒有瀏覽器：照 tests/test_prologue_web.py 的做法，把整支 app.js 放進 node 的假瀏覽器，餵它真的引擎給的 /api/main，
# 用假的 toggle 事件當玩家點開、收起摺疊，看重畫出來的 HTML。假 DOM 裡 details 的開合就是 HTML 裡有沒有 open：驗的是「重畫畫出什麼」。

# 驅動程式共用的小工具：fold() 讀頁面上那個摺疊現在畫成開著（true）、收著（false）、沒畫（null）；toggle(open) 送一個玩家點開／收起
# 的 toggle 事件；refuse() 讓下一個 /api/choose 被伺服器擋下來（400）、並讓 choose() 失敗後會重畫（按下去的那顆鈕還標著 busy）
HELPERS = """
const fold = () => { const hit = T.els.page.innerHTML.match(/<details class="fold here"( open)?>/); return hit ? !!hit[1] : null; };
const toggle = (open) => T.docListeners.toggle[0]({ target: Object.assign(Object.create(T.Element.prototype), { matches: (sel) => sel === "details.here", open }) });
const redraw = () => { T.els.page.innerHTML = ""; H.renderPage(); return fold(); };
const press = (id) => T.docListeners.click[0]({ target: { closest: () => ({ dataset: { act: "choose", id }, classList: { contains: () => false, add() {}, remove() {} } }) } });
const refuse = (error) => {
  T.ctx.setTimeout = () => 0; // toast() 的計時器不要拖住這個請求
  T.ctx.fetch = (url, opts) => { T.calls.push([url, JSON.parse(opts.body)]); return Promise.resolve({ ok: false, status: 400, json: () => Promise.resolve({ error }) }); };
  T.qs[".options .btn.busy, .act-ink.busy"] = {};
};
"""


def _script(body: str) -> str:
    return HELPERS + body


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _quiet(m):
    """框上沒有 glow：入伍段別的時候（或別的玩家）平常的樣子，「此地還能做」收著。"""
    return {**m, "guide": {k: v for k, v in m["guide"].items() if k != "glow"}}


def _at(m, place):
    return {**m, "status": {**m["status"], "location": place}}


@pytest.fixture
def glowing(on):
    """入伍段第一道軍令那一步：框上帶 glow（act:duty），「此地還能做」裡有發光的巡哨。"""
    m = _enlist_main(on)
    assert m["guide"]["glow"] == ["act:duty"] and any(o["id"] == "act:duty" for o in m["options"])
    return m


@pytest.fixture
def quiet(glowing):
    return _quiet(glowing)


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_a_fold_nobody_touched_stays_shut_and_no_fold_is_drawn_without_extras(quiet):
    out = run_prologue_web(quiet, _script("""
      H.renderPage();
      const shut = fold();
      H.S.main = { ...H.S.main, options: H.S.main.options.filter((o) => ["act:explore", "act:train", "act:socialize"].includes(o.id)) };
      return { shut, none: redraw() };"""))
    assert out == {"shut": False, "none": None}


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_a_fold_the_player_opened_stays_open_after_a_refused_actions_redraw(quiet):
    """摺疊裡的鈕被伺服器擋下來（400：「對方還沒答話，稍等。」；排太久也是這一種），choose() 重畫整頁：摺疊照樣開著，剛按的那一顆還在。"""
    out = run_prologue_web(quiet, _script("""return (async () => {
      H.renderPage();
      const before = fold();
      toggle(true); // 玩家點開「此地還能做」
      refuse("對方還沒答話，稍等。");
      T.els.page.innerHTML = ""; // 確認接下來的畫面是被擋下來之後重畫出來的
      await press("act:duty");
      return { before, redrawn: T.els.page.innerHTML !== "", after: fold(), calls: T.calls.map((c) => [c[0], c[1].id]),
               button: T.els.page.innerHTML.includes('data-id="act:duty"') };
    })();"""))
    assert out["before"] is False and out["calls"] == [["/api/choose", "act:duty"]]
    assert out["redrawn"] is True and out["after"] is True and out["button"] is True


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_a_fold_the_player_left_shut_stays_shut_after_a_refused_actions_redraw(quiet):
    out = run_prologue_web(quiet, _script("""return (async () => {
      H.renderPage();
      toggle(true);
      toggle(false); // 開了又收
      refuse("這會兒人多，沒輪到你，稍後再試一次。");
      await press("act:duty");
      return { after: fold(), redrawn: T.els.page.innerHTML.includes("此地還能做") };
    })();"""))
    assert out == {"after": False, "redrawn": True}


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_a_fold_the_player_opened_stays_open_after_a_poll_redraw(quiet):
    """輪詢帶來新的畫面（拿到有變的 main 之後 refreshPage → renderPage）：以前也把摺疊收起來。摺疊裡的件數變了（標題的字不同）也一樣。"""
    out = run_prologue_web(quiet, _script("""return (async () => {
      H.renderPage();
      toggle(true);
      const was = H.S.main;
      const fewer = was.options.filter((o) => o.id !== "act:duty");
      H.setMain({ ...was, now: "天色漸暗，營裡升起了炊煙。", options: fewer }); // 世界動了、此地少了一件事
      T.els.page.innerHTML = "";
      await H.refreshPage(was);
      return { redrawn: T.els.page.innerHTML !== "", open: fold(), title: (T.els.page.innerHTML.match(/此地還能做 (\\d+) 件事/) || [])[1] };
    })();"""))
    assert out["redrawn"] is True and out["open"] is True
    before = run_prologue_web(quiet, _script("H.renderPage(); return (T.els.page.innerHTML.match(/此地還能做 (\\d+) 件事/) || [])[1];"))
    assert int(out["title"]) == int(before) - 1  # 標題照新的件數寫，摺疊照樣開著


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_the_fold_is_remembered_for_this_place_only(quiet):
    """記的是這一處：走到別處，那裡的摺疊從收著開始（不然開過一次，每個城鎮都攤著一排按鈕）；回到原處、中間沒開關過別處，還是原樣。"""
    out = run_prologue_web(quiet, _script("""
      H.renderPage();
      toggle(true);
      const here = redraw();
      H.S.main = %s;
      const elsewhere = redraw();
      H.S.main = %s;
      return { here, elsewhere, back: redraw() };""" % (_json(_at(quiet, "別處")), _json(quiet))))
    assert out == {"here": True, "elsewhere": False, "back": True}


# ── 入伍段第一道軍令那一步（guide-3b 審查 Minor 11）──────────────────────────────


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_the_glowing_step_opens_the_fold_once_and_the_glow_stays_on_the_button(glowing):
    out = run_prologue_web(glowing, _script("""
      H.renderPage();
      const html = T.els.page.innerHTML;
      return { open: fold(), glowButton: /data-id="act:duty" >/.test(html), auto: Object.keys(H.S.hereAuto) };"""))
    assert out["open"] is True and out["glowButton"] is True  # 開頭自動打開、發光的鈕還在（applyGlow 照 guide.glow 的 id 找它）
    assert len(out["auto"]) == 1  # 記下「這一步、這一處」打開過了


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_any_glowing_button_in_the_fold_opens_it_once_and_one_on_the_action_bar_does_not(glowing):
    """joy 的 guide.glow 不只守勢行動：接糧車、挑戰那位人物收在「此地還能做」裡也一樣——開頭打開一次、之後照玩家的。發光的是行動列上的
    遊歷（攻城、截糧）時摺疊裡沒有要露出來的東西，不打開。"""
    convoy = {"id": "act:convoy", "label": "接下糧車（交出 4 份糧草）", "enabled": True, "wait": "", "confirm": ""}
    cart = {**glowing, "guide": {**glowing["guide"], "glow": ["act:convoy"]}, "options": glowing["options"] + [convoy]}
    out = run_prologue_web(cart, _script("""
      const begin = redraw();
      toggle(false);
      return { begin, after: [redraw(), redraw()], auto: Object.keys(H.S.hereAuto).length };"""))
    assert out == {"begin": True, "after": [False, False], "auto": 1}
    train = {**glowing, "guide": {**glowing["guide"], "glow": ["act:train"]}}
    assert run_prologue_web(train, _script("return { open: redraw(), auto: Object.keys(H.S.hereAuto).length };")) == {"open": False, "auto": 0}


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_a_fold_the_player_closed_at_the_glowing_step_stays_closed_on_the_next_redraws(glowing):
    out = run_prologue_web(glowing, _script("""return (async () => {
      H.renderPage();
      const begin = fold();
      toggle(false); // 玩家把它收起來
      const redraws = [redraw(), redraw(), redraw()];
      const was = H.S.main;
      H.setMain({ ...was, now: "營裡的鼓聲停了。" });
      T.els.page.innerHTML = "";
      await H.refreshPage(was); // 輪詢
      const poll = fold();
      refuse("對方還沒答話，稍等。");
      await press("act:duty"); // 被擋下來
      return { begin, redraws, poll, refused: fold(), auto: Object.keys(H.S.hereAuto).length };
    })();"""))
    assert out == {"begin": True, "redraws": [False, False, False], "poll": False, "refused": False, "auto": 1}


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_the_glowing_step_opens_the_fold_once_not_on_every_redraw(glowing):
    """「每次重畫都打開」的舊做法下，玩家收起來之後的每一次重畫都會再開；現在只在這一步開頭開一次：之後開著是玩家沒收（記在 S.here），
    不是又自動打開——所以收起來、再重畫幾次都是收著，S.hereAuto 也始終只有一筆。"""
    out = run_prologue_web(glowing, _script("""
      const seen = [];
      for (let i = 0; i < 4; i++) { seen.push(redraw()); }
      toggle(false);
      for (let i = 0; i < 4; i++) { seen.push(redraw()); }
      return { seen, auto: Object.keys(H.S.hereAuto).length };"""))
    assert out == {"seen": [True] * 4 + [False] * 4, "auto": 1}


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_a_player_who_closed_the_fold_before_the_step_began_gets_it_opened_once_when_it_begins(glowing, quiet):
    out = run_prologue_web(quiet, _script("""
      H.renderPage();
      toggle(true); toggle(false); // 這一步還沒開始：玩家自己收著
      const before = redraw();
      H.S.main = %s; // 入伍段走到第一道軍令那一步：框上帶了 glow
      const begin = redraw();
      toggle(false);
      return { before, begin, after: redraw() };""" % _json(glowing)))
    assert out == {"before": False, "begin": True, "after": False}


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_the_next_glowing_step_or_place_opens_it_again_once(glowing):
    """「開頭」是這一步（框的 key）在這一處第一次發光：別的步驟、或走到別處（那裡的摺疊裡也有發光的鈕）各開一次，開過就不再自動開。"""
    other_step = {**glowing, "guide": {**glowing["guide"], "key": "another_glowing_step"}}
    out = run_prologue_web(glowing, _script("""
      H.renderPage(); toggle(false);
      const closed = redraw();
      H.S.main = %s;
      const nextStep = redraw(); toggle(false);
      const nextStepAgain = redraw();
      H.S.main = %s;
      const elsewhere = redraw(); toggle(false);
      const elsewhereAgain = redraw();
      return { closed, nextStep, nextStepAgain, elsewhere, elsewhereAgain, auto: Object.keys(H.S.hereAuto).length };"""
                              % (_json(other_step), _json(_at(glowing, "別處")))))
    assert out == {"closed": False, "nextStep": True, "nextStepAgain": False, "elsewhere": True, "elsewhereAgain": False, "auto": 3}


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_the_fold_without_a_glowing_duty_button_is_not_opened_by_the_step(glowing):
    """框上帶 glow、但這一處沒有發光的那顆鈕（沒有 act:duty）：沒有東西要露出來，摺疊不自動打開，也不記成自動打開過。"""
    other = {"id": "learn:cuquan", "label": "學粗淺拳腳（學費 0 兩）", "enabled": True, "wait": "", "confirm": ""}  # 摺疊裡留一顆別的鈕，摺疊還畫得出來
    m = {**glowing, "options": [o for o in glowing["options"] if o["id"] != "act:duty"] + [other]}
    out = run_prologue_web(m, _script("H.renderPage(); return { open: fold(), auto: Object.keys(H.S.hereAuto) };"))
    assert out == {"open": False, "auto": []}


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_logging_in_again_starts_the_fold_over(glowing):
    out = run_prologue_web(glowing, _script("""
      H.renderPage(); toggle(true);
      const remembered = H.S.here;
      H.enter({ stage: "gate" });
      return { remembered, here: H.S.here, auto: Object.keys(H.S.hereAuto) };"""))
    assert out["remembered"]["open"] is True and out["here"] is None and out["auto"] == []


# ── 收起來的摺疊裡有發光的鈕（FB-087 審查 M3）─────────────────────────────────
# 入伍段第一道軍令那一步，玩家把「此地還能做」收起來之後，發光的巡哨／傳道／保境安民藏在裡面：沒有光、也沒有「在下面 ↓」。
# 現在摺疊收著時光改給它的標題列（同一個 .glow），「在下面 ↓」把標題列當目標；打開之後光回到鈕上。
# 假 DOM 裡的摺疊：一個假摺疊（開著與否看 state.open）、一顆假的標題列、一顆發光的鈕；鈕的 closest("details:not([open])")
# 只在摺疊收著時才回摺疊（跟真的 DOM 一樣）；"#page .glow" 像真的 querySelector 一樣回第一個有 .glow 的元素，位置照 rects。
FAKE_FOLD = """
const state = { open: false };
const summary = T.el([]), duty = T.button("act:duty");
const box = { querySelector: (sel) => (sel === ":scope > summary" ? summary : null) };
duty.closest = (sel) => (sel === "details:not([open])" && !state.open ? box : null);
const rects = new Map([[summary, { top: 740, bottom: 802 }], [duty, { top: 0, bottom: 0 }]]); // 收著的鈕量不到位置：全是 0
Object.defineProperty(T.qs, "#page .glow", { configurable: true, get: () => {
  const lit = T.fake.list.find((e) => e.classes.has("glow"));
  return lit ? { getBoundingClientRect: () => rects.get(lit) || { top: 500, bottom: 560 } } : null;
} });
const inserted = [];
T.qs[".card.guide .guide-head"] = { firstElementChild: { insertAdjacentHTML: (pos, html) => inserted.push(html) }, querySelector: () => null };
T.qs[".tabs"] = { getBoundingClientRect: () => ({ top: 756 }) };
const glowing = () => ({ summary: summary.classes.has("glow"), button: duty.classes.has("glow") });
"""


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_a_closed_fold_with_the_glowing_button_inside_glows_its_summary_instead(glowing):
    out = run_prologue_web(glowing, _script(FAKE_FOLD + """
      H.applyGlow();
      return glowing();"""))
    assert out == {"summary": True, "button": False}  # 看不到的鈕不發光，光改給摺疊的標題列


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_opening_the_fold_moves_the_glow_back_to_the_button_and_closing_it_moves_it_again(glowing):
    """玩家點開、收起摺疊時 toggle 事件就重算光：不必等下一次重畫。"""
    out = run_prologue_web(glowing, _script(FAKE_FOLD + """
      H.applyGlow();
      const closed = glowing();
      state.open = true; toggle(true);
      const opened = glowing();
      state.open = false; toggle(false);
      return { closed, opened, closedAgain: glowing() };"""))
    assert out == {"closed": {"summary": True, "button": False}, "opened": {"summary": False, "button": True},
                   "closedAgain": {"summary": True, "button": False}}


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_an_open_fold_keeps_the_glow_on_the_button(glowing):
    out = run_prologue_web(glowing, _script(FAKE_FOLD + """
      state.open = true;
      H.applyGlow();
      return glowing();"""))
    assert out == {"summary": False, "button": True}


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_the_below_cue_points_at_the_summary_when_the_closed_fold_is_cut_off(glowing):
    """要按的東西整個在第一屏外時框上有「在下面 ↓」：目標是看得到的標題列（#page .glow 第一個有光的），不是量不到位置的鈕。"""
    out = run_prologue_web(glowing, _script(FAKE_FOLD + """
      H.applyGlow(); // 摺疊收著：標題列的底邊 802 在分頁列（756）底下
      const closed = inserted.length;
      inserted.length = 0;
      rects.set(duty, { top: 500, bottom: 560 }); // 打開之後鈕有了位置：整個在第一屏裡，不用再指
      state.open = true; toggle(true); // 打開之後光回到鈕
      const opened = inserted.length;
      rects.set(duty, { top: 740, bottom: 802 }); // 展開把鈕推到分頁列底下：照舊要有
      inserted.length = 0;
      toggle(true);
      return { closed, opened, pushedDown: inserted.length, html: inserted[0] };"""))
    assert out["closed"] == 1 and out["opened"] == 0 and out["pushedDown"] == 1
    assert 'data-act="guide-below"' in out["html"] and "在下面 ↓" in out["html"]


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_a_closed_fold_whose_summary_is_on_the_first_screen_gets_no_cue(glowing):
    out = run_prologue_web(glowing, _script(FAKE_FOLD + """
      rects.set(summary, { top: 600, bottom: 650 });
      H.applyGlow();
      return { glowing: glowing(), cues: inserted.length };"""))
    assert out == {"glowing": {"summary": True, "button": False}, "cues": 0}


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_a_glow_outside_any_fold_is_unchanged(glowing):
    """摺疊以外的鈕（closest 找不到收著的摺疊）：光照舊在鈕上。"""
    out = run_prologue_web(glowing, _script("""
      const e = T.button("act:duty");
      H.applyGlow();
      return [...e.classes];"""))
    assert out == ["glow"]


# ── 原 test_fb105_muster_join.py（整檔搬進來） ──
# FB-105（QA 7cc1fd7，2026-10-08，375×812）：決戰集結時「加入」收在「此地還能做」的摺疊裡。
#
# 投靠官軍、站在盧植營，廣宗決戰集結中：選單第一顆是「加入【官軍】」，可是行動列（web/app.js 的 actionBar）把五格以外的選項都收進
# 摺疊，它跟求見、拜師、巡哨擠在一起、不發光；場景只寫「選擇陣營加入」，老石那一則提示排在三則別的後面、也沒說按哪裡。集結只有
# 現實 30 分鐘，沒打開摺疊的人整場不在名單上。
#
# 現在：還沒參戰、按得下去的「加入」（自己陣營那一邊）或散人的「臨時投效」放在場景卡戰場名字那一行（加入一顆在名字旁邊，
# 投效兩顆在名字底下另起一行），不再收進摺疊；鈕旁邊一小句說在這裡報名（第二、三場決戰也看得到，不靠只說一次的提示）；老石、青禾、
# 季伯平那一則多一句。打不了這場仗的人（不是交戰的一方、已經加入或投效、不在決戰的大區、在路上）畫面不變；場景卡沒畫的時候
# （在路上、序章師父說話的那幾步）鈕照舊留在選單上，不會不見。
#
# 集結那一句（「選擇陣營加入；集結期間照常行動。」）是戰鬥引擎寫的（Game._battle_scene_text），另一條線正在改戰鬥那一段：
# fix-1008 裁示不動它，「在哪裡加入」寫在網頁上、鈕的旁邊（web/app.js 的 MUSTER_NOTE），集結那一句照伺服器給的原樣畫。
#
# 網頁用真實內容（週末設定）的廣宗決戰、真的 /api/main，照 tests/test_prologue_web.py 的做法把整支 app.js 放進 node
# （scripts/test_for.py 改到 app.js 時靠這個檔名挑到這裡）。句子待 joy 潤：那一小句照 app.js 的 MUSTER_NOTE、MUSTER_ARROW 比對，
# 不在這裡再寫一次字面；這裡只認事實（哪一顆、在哪、指向哪）。

ROOT_fb105 = webharness.ROOT


# ── 共用 ─────────────────────────────────────────────


def _muster(on, who="guan", place="luzhi_camp", battle="guangzong", name="甲"):
    """廣宗決戰集結中（真實內容、週末設定）：who 是陣營或 None（散人），人在 place；提示關掉（框不在這個測試裡）。"""
    game = Game.new(on, name, rng=random.Random(0))
    game.client = None
    game.set_hints_off(True)
    p = game.state.player
    p.faction, p.location = who, place
    if battle is not None:  # None：同一個世界裡已經開著的那一場
        game.world.start_battle(on.battles[battle], now=game.now)
    return game


def _start_fighting(game):
    """集結時間撥到過去，再讀一次選單：options() 把全服戰鬥追到現在，這一場就開打。main_view 先讀場景（不推進戰鬥）、
    最後才讀選單，所以要在它之前先推進，不然場景還寫著集結、選單已經是開打的。"""
    game.world.mutate_battle(lambda b: setattr(b, "muster_deadline_real", -1.0))
    game.options()
    assert game.world.get_battle().phase == "active"


def _page(m):
    return run_prologue_web(m, "return H.pageJianghu();")


def _fold(page):
    hit = re.search(r'<details class="fold here"[^>]*>(.*?)</details>', page, re.S)
    return hit.group(1) if hit else ""


def _consts_fb105():
    """app.js 裡那一小句與箭頭（MUSTER_NOTE、MUSTER_ARROW）：joy 潤了字，這裡跟著讀，不必改測試。"""
    driver = 'finish(new Function(konst("MUSTER_NOTE") + "\\n" + konst("MUSTER_ARROW") + "\\nreturn { note: MUSTER_NOTE, arrow: MUSTER_ARROW };")());'
    return webharness.run(driver, {})


def _note_html(kind):
    """那一小句畫出來的樣子：字照常唸，箭頭藏起來不唸，id 給那一排鈕的 aria-describedby 用。"""
    c = _consts_fb105()
    return (f'<span class="muster-note" id="muster-note">{htmllib.escape(c["note"][kind], quote=False)}'
            f'<span aria-hidden="true"> {c["arrow"][kind]}</span></span>')


ROW_ATTRS = 'role="group" aria-label="參戰" aria-describedby="muster-note"'


# ── 加入的鈕在場景卡戰場名字那一行，不在摺疊裡 ───────────────────────


@node
def test_the_join_button_sits_by_the_battles_name_and_leaves_the_fold(on):
    m = server.main_view(_muster(on, "guan"))
    assert any(o["id"] == "battle:join:guan" and o["enabled"] for o in m["options"]) and "act:explore" in [o["id"] for o in m["options"]]
    page = _page(m)
    scene = _scene(page)
    head = re.search(r'<div class="muster-head">(.*?</div>)</div>', scene, re.S).group(1)
    # 同一行：戰場名字、說在這裡報名的那一小句（箭頭指向右邊的鈕）、加入的鈕
    assert head == ('<p><strong>廣宗決戰</strong></p>' + _note_html("join")
                    + f'<div class="options muster-join" {ROW_ATTRS}><button class="btn small primary" data-act="choose" '
                    'data-id="battle:join:guan"><span>加入【官軍】</span></button></div>')
    assert _consts_fb105()["arrow"]["join"] == "→"  # 鈕在右邊
    assert "battle:join:guan" not in _fold(page) and page.count('data-id="battle:join:guan"') == 1
    assert "此地還能做" in page  # 摺疊照樣在（求見、拜師、巡哨），只是少了加入那一顆
    # 集結那一句（戰鬥引擎寫的）照伺服器給的原樣跟在名字那一行後面：網頁只換掉第一段（名字），其餘一個字不動
    rest = m["scene"].split("</p>\n", 1)[1]
    assert "集結中，還剩現實" in rest and scene.startswith('<div class="muster-head">') and rest in scene


@node
def test_a_drifters_two_enlist_buttons_get_their_own_row_under_the_name(on):
    m = server.main_view(_muster(on, None))
    page = _page(m)
    scene = _scene(page)
    title, note, row = re.search(
        r'<div class="muster-head"><p>(.*?)</p>(<span class="muster-note".*?</span></span>)'
        rf'<div class="options muster-join wide" {ROW_ATTRS}>(.*?)</div></div>', scene, re.S).groups()
    assert title == "<strong>廣宗決戰</strong>"
    assert note == _note_html("enlist") and _consts_fb105()["arrow"]["enlist"] == "↓"  # 在名字右邊、往下指那兩顆
    assert re.findall(r'data-id="(battle:enlist:\w+)"', row) == ["battle:enlist:guan", "battle:enlist:huang"]
    # 鈕上只寫括號前那一段（「只算這一場」在那一小句裡）
    labels = {o["id"]: o["label"] for o in m["options"]}
    assert re.findall(r"<span>(.*?)</span>", row) == [labels[i].split("（")[0] for i in ("battle:enlist:guan", "battle:enlist:huang")]
    assert all("（" in labels[i] for i in ("battle:enlist:guan", "battle:enlist:huang"))
    assert "battle:enlist" not in _fold(page)
    assert scene.endswith(m["scene"].split("</p>\n", 1)[1])  # 集結那一句照伺服器給的原樣


@node
def test_a_drifter_who_arrives_after_the_fighting_started_still_gets_the_row(on):
    """開打了還沒投效的散人（臨時投效照樣按得下去，試玩回饋 2026-10-08）：那兩顆一樣畫在名字底下，不收進摺疊。"""
    game = _muster(on, None)
    _start_fighting(game)
    m = server.main_view(game)
    assert "集結中" not in m["scene"] and "回合" in m["scene"]  # 場景是開打之後的戰場
    assert [o["id"] for o in m["options"] if o["id"].startswith("battle:")] == ["battle:enlist:guan", "battle:enlist:huang"]
    page = _page(m)
    assert re.search(rf'<div class="options muster-join wide" {ROW_ATTRS}>', _scene(page))
    assert "battle:enlist" not in _fold(page) and page.count('data-id="battle:enlist:guan"') == 1


@node
def test_a_late_comer_on_your_own_side_keeps_the_ordinary_join_late_button(on):
    """開打了才到的自己人：選單只有一顆「加入戰局」（battle:join_late），本來就看得到，照舊畫成一般的鈕；不搬到名字那一行。"""
    game = _muster(on, "guan")
    _start_fighting(game)
    m = server.main_view(game)
    assert "集結中" not in m["scene"]
    assert [o["id"] for o in m["options"]] == ["battle:join_late"]
    page = _page(m)
    assert "muster-" not in page and _scene(page) == m["scene"]
    assert re.search(r'<button class="btn " data-act="choose" data-id="battle:join_late" >', page)


@node
def test_once_you_joined_the_page_is_what_it_was(on):
    """已經加入（或投效過）：場景卡裡沒有加入的鈕（muster-head）；集結那一句收成一行（muster-brief，自檢 U-09），灰的「已加入」／「已臨時投效」
    不畫（以前收在摺疊裡）。"""
    for who, first in (("guan", "battle:join:guan"), (None, "battle:enlist:guan")):
        game = _muster(on, who)
        game.choose(first)
        m = server.main_view(game)
        page = _page(m)
        assert "muster-head" not in page and 'class="muster-brief"' in page, who
        assert first not in page, who


@node
def test_someone_who_cannot_join_sees_no_change(on):
    """不在決戰的大區：選單上沒有加入，場景卡照伺服器給的。（豪強以前在這裡一旁觀戰；Joy 2026-10-13 起跟散人一樣臨時投效。）"""
    elsewhere = _muster(on, "guan", place="luzhi_camp", battle=None, name="乙")  # 黃巾決戰在潁川汝南，人在冀州
    for game in (elsewhere,):
        m = server.main_view(game)
        assert not any(o["id"].startswith("battle:") for o in m["options"])
        m["art"] = None  # 站在地點時場景卡上面有圖、地名那一段疊到圖上（減法季批 8，test_scene_art.py）：這裡比的是沒圖那一份文字
        page = _page(m)
        assert "muster-" not in page and _scene(page) == m["scene"]


@node
def test_with_an_event_open_the_join_button_still_sits_by_the_name_and_only_once(on):
    """集結時碰上事件（選單是一排選項、不是行動列）：加入照樣在名字那一行，不在選項裡再列一次；事件的選項照舊。"""
    game = _muster(on, "guan")
    game.state.pending_event = "jz_gz_forge"
    m = server.main_view(game)
    assert [o["id"] for o in m["options"]][0] == "battle:join:guan" and "act:explore" not in [o["id"] for o in m["options"]]
    page = _page(m)
    assert page.count('data-id="battle:join:guan"') == 1 and "muster-join" in _scene(page)
    assert 'data-id="choice:0"' in page


# ── 場景卡沒畫的時候，鈕照舊留在選單上 ─────────────────────────────


@node
def test_on_the_road_a_join_option_stays_in_the_menu(on):
    """在路上加入不了（引擎在路上不給這幾顆）；萬一選單上有，路上的場景卡收成兩行、不畫名字那一行：鈕照舊畫在選項裡，不搬、不見。"""
    m = server.main_view(_muster(on, "guan"))
    road = {**m, "on_road": True, "options": [o for o in m["options"] if o["id"] == "battle:join:guan"]}
    page = _page(road)
    assert "muster-" not in page
    assert re.search(r'<div class="options">\s*<button class="btn " data-act="choose" data-id="battle:join:guan" >', page)


@node
def test_while_the_master_talks_in_the_hut_the_enlist_buttons_stay_in_the_menu(on):
    """序章：草廬在潁川汝南，長社火攻集結時新角色在序章第 2 步以前就有投效兩顆（審查 M2 的情形）；現在序章裡引擎不給投效、
    場景也不畫戰場（FB-113），頁面上沒有參戰那一列。
    畫面這一層守的照舊：師父在說話（框在、眼前沒有事件）時草廬那張場景卡不畫（masterTalks），選單上萬一有投效鈕也不搬
    （搬了就沒地方畫、整個不見），照舊收在「此地還能做」的摺疊裡。"""
    game = Game.new(on, "沈浪", rng=random.Random(0), prologue=True)
    game.client = None
    _to_step(game, 1)
    game.world.start_battle(on.battles["changshe_fire"], now=game.now)
    m = server.main_view(game)
    assert m["prologue"] is not None and m["guide"] is not None
    assert not any(o["id"].startswith("battle:") for o in m["options"]) and "長社火攻" not in m["scene"]  # FB-113
    assert "muster-" not in _page(m)
    enlist = [{"id": f"battle:enlist:{side}", "label": f"臨時投效【{name}】（只算這一場）", "enabled": True, "wait": "", "confirm": ""}
              for side, name in (("guan", "官軍"), ("huang", "黃巾軍"))]
    stray = {**m, "options": enlist + m["options"]}
    assert not any(o["id"].startswith("choice:") for o in stray["options"]) and not stray["on_road"]
    page = _page(stray)
    assert '<section class="card scene">' not in page and "muster-" not in page  # 場景卡沒畫
    for o in enlist:
        assert page.count(f'data-id="{o["id"]}"') == 1 and o["id"] in _fold(page)


@node
def test_a_scene_without_a_first_paragraph_puts_the_row_on_top(on):
    """認不出第一段（伺服器的場景不是 <p> 開頭）：那一小句與鈕排在卡片最上面，場景照原樣接在後面。"""
    m = server.main_view(_muster(on, "guan"))
    odd = {**m, "scene": "<h3>戰場</h3>\n<p>集結中。</p>\n"}
    scene = _scene(_page(odd))
    assert scene.startswith('<div class="muster-head">' + _note_html("join") + f'<div class="options muster-join" {ROW_ATTRS}>')
    assert scene.endswith("</div></div>\n" + odd["scene"])


@node
def test_the_button_label_is_escaped(on):
    m = server.main_view(_muster(on, "guan"))
    odd = {**m, "options": [{**o, "label": "加入【<b>官軍</b>】"} if o["id"] == "battle:join:guan" else o for o in m["options"]]}
    scene = _scene(_page(odd))
    assert "<span>加入【&lt;b&gt;官軍&lt;/b&gt;】</span>" in scene and "<b>官軍" not in scene


# ── 樣式：名字那一行不因為那顆鈕變高 ─────────────────────────────


def _css_rule(selector):
    css = re.sub(r"/\*.*?\*/", "", (ROOT_fb105 / "web" / "style.css").read_text(encoding="utf-8"), flags=re.S)
    found = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert found, f"style.css 裡找不到 {selector}"
    return {k.strip(): v.strip() for k, v in (part.split(":", 1) for part in found.group(1).split(";") if ":" in part)}


def test_the_join_button_does_not_make_the_name_line_taller():
    """375×812 估過（盧植營、剛到、沒有框）：行動列下緣 666 → 加入在名字旁邊 666（鈕 38px 高，上下各 −8px，佔的高度 22px，
    不高過名字那一行；那一小句 12px 一行、放不下就省略號，不折行）；散人兩顆另起一行 693 → 737（6px 的縫＋38px）。
    這是估出來的數字，改樣式表時要重估。"""
    head = _css_rule(".scene .muster-head")
    assert head["display"] == "flex" and head["flex-wrap"] == "wrap" and head["align-items"] == "center"
    assert _css_rule(".scene .muster-head > p")["margin"] == "0"
    note = _css_rule(".scene .muster-note")
    assert note["flex"] == "1 1 0" and note["min-width"] == "0"  # 基準寬度 0：這一句永遠不會把鈕擠到下一行
    assert note["white-space"] == "nowrap" and note["text-overflow"] == "ellipsis" and note["overflow"] == "hidden"
    assert _css_rule(".scene .muster-join")["flex"] == "none"
    btn = _css_rule(".scene .muster-join .btn")
    assert btn["margin"] == "-8px 0"  # 點擊範圍 38px，佔的高度只有 22px
    wide = _css_rule(".scene .muster-join.wide")
    assert wide["flex-basis"] == "100%"
    assert _css_rule(".scene .muster-join.wide .btn")["margin"] == "0"  # 另起一行時不往上吃，免得蓋到名字


# ── 原 test_fb360_escort_pick.py（整檔搬進來） ──
# FB-360（歷史武將同行 QA，2026-10-19，375×812）：名下有同伴的人按場景卡上的「加入」之後，挑同伴的四顆（battle:escort:*）
# 收在「此地還能做」的摺疊裡，第一屏看起來什麼都沒變——還沒加入，卻以為報名了（FB-105 那個坑換了一個地方）。
#
# 現在 web/app.js 的 musterJoins 也認 battle:escort:，挑同伴那一步畫在場景卡戰場名字那一行底下（跟加入同一個位置），一顆一行
# （鈕上寫份量與氣血，四顆擠一排放不下），旁邊那一小句說挑了才算加入（MUSTER_NOTE.escort，待 joy 潤）；摺疊裡不再列。
# 晚到（battle:join_late）挑同伴也一樣。網頁照 tests/test_jianghu_page_web.py 的做法用真實內容、真的 /api/main。

PICK = re.compile(r'data-id="(battle:escort:\w+)"')


def _owner(on, game):
    p = game.state.player
    for cid in ("liubei", "guanyu"):
        assert game.world.try_recruit(cid, p.name, cap=3)
    return p


def _row(scene):
    return re.search(rf'<div class="options muster-join pick" {ROW_ATTRS}>(.*?)</div></div>', scene, re.S)


@node
def test_after_join_the_escort_pick_sits_by_the_battles_name(on):
    game = _muster(on, "guan")
    _owner(on, game)
    game.choose("battle:join:guan")
    m = server.main_view(game)
    picks = [o["id"] for o in m["options"] if o["id"].startswith("battle:escort:")]
    assert set(picks) == {"battle:escort:liubei", "battle:escort:guanyu", "battle:escort:none", "battle:escort:back"}
    page = _page(m)
    scene = _scene(page)
    assert _note_html("escort") in scene  # 那一小句說挑了才算加入
    row = _row(scene)
    assert row is not None and PICK.findall(row.group(1)) == picks  # 照選單的順序，一顆都不少
    labels = {o["id"]: o["label"] for o in m["options"]}
    assert all(f"<span>{labels[i]}</span>" in row.group(1) for i in picks)  # 份量與氣血照寫（挑誰要看）
    assert "battle:escort" not in _fold(page) and all(page.count(f'data-id="{i}"') == 1 for i in picks)


def test_the_pick_row_stacks_one_button_per_line():
    """鈕上寫「派某某隨你出陣（份量 N・氣血 N）」，375 寬四顆擠一排放不下：另起一行、一顆一行、佔滿寬度。"""
    row = _css_rule(".scene .muster-join.pick")
    assert row["flex-basis"] == "100%" and row["flex-direction"] == "column"
    assert _css_rule(".scene .muster-join.pick .btn")["width"] == "100%"


@node
def test_a_late_comer_picks_by_the_name_too(on):
    game = _muster(on, "guan")
    _owner(on, game)
    _start_fighting(game)
    game.choose("battle:join_late")
    m = server.main_view(game)
    picks = [o["id"] for o in m["options"] if o["id"].startswith("battle:escort:")]
    assert len(picks) == 4
    page = _page(m)
    row = _row(_scene(page))
    assert row is not None and PICK.findall(row.group(1)) == picks
    assert all(page.count(f'data-id="{i}"') == 1 for i in picks)


# ── 原 test_fb663_reveal_card_web.py（整檔搬進來） ──
# FB-663（練功入口對比圖開發回報，PM 2026-10-21 給號）：點開探索（或移動）的卡，最後一顆被底部分頁列蓋住。沒有 node 就略過。
#
# 以前用 scrollIntoView({block: "nearest"}) 加 CSS 的 scroll-margin-bottom：卡本身還在視窗裡（只是落在分頁列底下）時瀏覽器認為「已經看得到」，
# 不捲，scroll-margin 不算數（量到：375×812 站潁川郡，探索卡底 797、分頁列頂 756，最後一顆〔練功〕下半截在分頁列底下，scrollY 一直 0）。
# 現在自己量卡底、分頁列頂、狀態列底再 scrollBy。node 排不了版：這裡用假的 document／window 餵幾組量到的位置，看捲了多少；
# 真正的幾何（375×812、375×667、320×568，城裡與野外）在瀏覽器裡量，數字寫在試玩回饋 FB-663 那一列。

REVEAL = r"""
const code = [konst("REVEAL_GAP"), konst("REVEAL_TOP"), fn("revealShift"), fn("revealMoveCard")].join("\n");
const rect = (r) => ({ ...r, height: r.bottom - r.top });
// 假的 document／window：card 是 null 就是沒有展開的卡；scrollIntoView 照 Chrome 的做法——卡本身整個在視窗裡就不動（scroll-margin 不算數）
function reveal(c) {
  const calls = [];
  const innerHeight = c.innerHeight || 812;
  const win = { innerHeight, scrollBy: (o) => calls.push(o), matchMedia: () => ({ matches: !!c.calm }) };
  const card = c.card && {
    getBoundingClientRect: () => rect(c.card),
    scrollIntoView: () => {
      if (c.card.bottom > innerHeight) calls.push({ legacyScrollIntoView: c.card.bottom + 64 - innerHeight });
    },
  };
  const doc = {
    querySelector: (sel) => (sel === "#page .act-move, #page .act-explore" ? card : sel === ".tabs" && !c.noTabs ? { getBoundingClientRect: () => rect({ top: c.tabsTop, bottom: innerHeight }) } : null),
    getElementById: (id) => (id === "top" ? { hidden: false, getBoundingClientRect: () => rect({ top: 0, bottom: c.topBottom }) } : null),
  };
  new Function("document", "window", code + "\nrevealMoveCard();")(doc, win);
  return calls;
}
const cases = input.cases.map((c) => ({ name: c.name, calls: reveal(c) }));
finish(cases);
"""


def _reveal(*cases):
    out = webharness.run(REVEAL, {"cases": list(cases)})
    return {c["name"]: c["calls"] for c in out}


def _case(name, **kw):
    return {"name": name, "tabsTop": 756, "topBottom": 88, **kw}


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_a_card_that_ends_under_the_tab_bar_is_scrolled_clear_of_it():
    """PM 量到的：卡底 797（視窗 812 裡）、分頁列頂 756。捲到卡底離分頁列頂至少 12 px。"""
    calls = _reveal(_case("city", card={"top": 575, "bottom": 797}))["city"]
    assert len(calls) == 1 and "legacyScrollIntoView" not in calls[0], calls
    assert calls[0]["top"] >= 797 - (756 - 12)  # 卡底落在 744 以上
    assert calls[0]["behavior"] == "smooth"


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_a_card_in_the_wilds_that_is_thirteen_pixels_under_is_scrolled_too():
    calls = _reveal(_case("wild", card={"top": 520, "bottom": 769}))["wild"]  # 野外：卡矮一點，仍然被蓋住約 13 px
    assert len(calls) == 1 and calls[0]["top"] >= 769 - (756 - 12)


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_a_card_already_clear_of_the_tab_bar_stays_put():
    assert _reveal(_case("clear", card={"top": 400, "bottom": 744}))["clear"] == []  # 剛好離 12 px：不動
    assert _reveal(_case("high", card={"top": 300, "bottom": 600}))["high"] == []  # 已經在上面：不往回捲


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_the_safe_area_under_the_tab_bar_counts():
    """iPhone 底部安全區（--bottom）讓分頁列變高、頂往上移：量的是分頁列真正的頂，不是寫死的 64 px。"""
    plain = _reveal(_case("plain", card={"top": 575, "bottom": 797}))["plain"][0]["top"]
    safe = _reveal(_case("safe", card={"top": 575, "bottom": 797}, tabsTop=722))["safe"][0]["top"]  # 分頁列高了 34 px
    assert safe == plain + 34


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_a_card_taller_than_the_visible_part_keeps_its_top_and_first_button_in_view():
    """卡比分頁列上方看得到的地方還高（320×568、攤開找素材分支）：捲到卡頂貼在狀態列底下就停，第一顆一定看得到。"""
    calls = _reveal(_case("tall", card={"top": 300, "bottom": 1000}))["tall"]
    assert len(calls) == 1
    new_top = 300 - calls[0]["top"]
    assert new_top >= 88 and new_top <= 88 + 12  # 卡頂在狀態列（底 88）底下，不被它蓋住
    # 已經貼在狀態列底下的：不再往上捲
    assert _reveal(_case("stuck", card={"top": 90, "bottom": 900}))["stuck"] == []


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_nothing_to_scroll_without_a_card_or_a_tab_bar():
    out = _reveal(_case("closed", card=None), _case("notabs", card={"top": 575, "bottom": 797}, noTabs=True))
    assert out["closed"] == [] and out["notabs"] == []


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_reduced_motion_scrolls_without_the_slide():
    calls = _reveal(_case("calm", card={"top": 575, "bottom": 797}, calm=True))["calm"]
    assert len(calls) == 1 and calls[0]["behavior"] == "auto"


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_the_stylesheet_no_longer_leans_on_scroll_margin_for_the_card():
    """scroll-margin-bottom 在這個情形不算數（上面第一條）：留在樣式表裡只會讓人以為是它在管。"""
    css = (webharness.ROOT / "web" / "style.css").read_text(encoding="utf-8")
    rule = re.search(r"\.act-move, \.act-explore \{[^}]*\}", css)
    assert rule and "scroll-margin" not in rule.group(0)


# ── 原 test_fb664_grey_cell_sub_web.py（整檔搬進來） ──
# FB-664（練功入口對比圖開發回報，PM 2026-10-21 給號）：行動列「交友」灰著時，格子小字是整句「這裡沒有能說上話的人」
# （10 個字、100 px），四格時兩頭被格子切掉。灰格小字最多六個字（一行約 60 px、10 px 的字）：格子寫短的，整句放行動列底下那一行
# （actNotesHtml）。談滿了的交友（一類一顆開著時，單人地點的交友是 act:socialize 不是 call:）同一個毛病，一併改。沒有 node 就略過。
# node 排不了版：這裡看格子裡寫什麼、底下那一行寫什麼；375／320 寬有沒有被切在瀏覽器裡量（Range 對格子的矩形），數字寫在試玩回饋 FB-664 那一列。

def _game(at, faction=None):
    content = renown_unscaled(real_content("week7"))  # 一類一顆開著（開季蓋章）；求見門檻照原數（名望 15）
    content.config.auto_open_first_season = True
    game = Game.new(content, "沈浪", rng=random.Random(0))
    game.client = None
    p = game.state.player
    p.location, p.faction, p.stamina = at, faction, float(content.config.stamina_max)
    return game


def _bar(game):
    return run_prologue_web(server.main_view(game), "return H.actionBar(H.S.main);")


def _cell(bar, key):
    return re.search(rf'<button class="act-ink[^"]*" data-key="{key}".*?</button>', bar, re.S).group(0)


def _sub(cell):
    return re.search(r"</b><small>(.*?)</small>", cell).group(1)


def _face(cell):
    """格子上看得到的那一截（開頭標籤裡 data-why 那一句不算）。"""
    return cell[cell.index(">") + 1:]


def _width(text):
    """格子小字的寬（以一個漢字為 1）：英數與空白算半個。一行約 60 px、10 px 的字，放得下六個漢字（sortie.OUT_NOTE 的註解）。"""
    return sum(1 if ord(ch) > 0x2E80 else 0.5 for ch in text)


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
@pytest.mark.slow
def test_the_social_cell_greyed_for_nobody_here_says_it_briefly_and_the_note_row_has_the_sentence():
    game = _game("yingchuan")
    social = next(o for o in game.options() if o.id == "act:socialize")
    assert not social.enabled and social.label == f"交友（{SOCIAL_NO_ONE}）"  # 前提：真的是這一句
    bar = _bar(game)
    cell = _cell(bar, "social")
    assert "<b>交友</b><small>沒有人</small>" in cell and SOCIAL_NO_ONE not in _face(cell)
    assert f'data-why="{SOCIAL_NO_ONE}。"' in cell  # 整句在點了浮出的那一句（減法季批 1 拿掉了底下那一行），不是伺服器寫的那一句「結識這裡的人」
    assert "結識這裡的人" not in bar


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
@pytest.mark.slow
def test_every_grey_cell_sub_fits_the_cell():
    """幾個真的會灰的地方：沒有人、名望還差、散人不能出陣、不在戰線。每一格小字都不超過六個字。"""
    for at in ("yingchuan", "changshe", "yingshui", "dajiangjun_fu", "luoyang_road", "wan_city"):
        bar = _bar(_game(at))
        for off in re.findall(r'<button class="act-ink off".*?</button>', bar, re.S):
            assert _width(_sub(off)) <= 6, (at, off)


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
@pytest.mark.slow
def test_a_talked_out_single_figure_social_cell_says_so_briefly_too():
    """一類一顆開著時，單人地點談滿了的交友是灰的 act:socialize，括號裡整句帶換日的那一刻（跟 call: 談滿同一句）。孟津渡是真的會這樣的地方。"""
    game = _game("mengjin_ford")
    content = game.content
    p = game.state.player
    (cid,) = game._figures_here()
    p.flags.add(f"結識:{cid}")
    p.fortune = True
    p.talks_today[cid] = [rules.game_day(content, game.state.world), content.config.talk_turns_per_day]
    option = next(o for o in game.options() if o.id == "act:socialize")
    note = game._talked_out_note()
    assert not option.enabled and option.label == f"交友（{note}）"
    bar = _bar(game)
    assert "<b>交友</b><small>已談滿</small>" in _cell(bar, "social") and "00:00" not in _face(_cell(bar, "social"))
    assert f'data-why="{note}。"' in _cell(bar, "social")


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
@pytest.mark.slow
def test_without_server_notes_the_grey_cell_still_draws_no_note_row():
    """伺服器沒給這一格的說明（舊版、序章裡是空的）：底下那一行照舊不畫（tests/test_explain_web.py::test_no_notes_without_server_notes 的約定），
    有沒有那一行由伺服器說了算，網頁只換句子；格子照樣寫短的。"""
    m = server.main_view(_game("yingchuan"))
    m["action_notes"] = {}
    m["status"]["howto_entry"] = False
    bar = run_prologue_web(m, "return H.actionBar(H.S.main);")
    assert "<b>交友</b><small>沒有人</small>" in _cell(bar, "social") and 'class="act-notes"' not in bar


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
@pytest.mark.slow
def test_the_other_grey_reasons_keep_their_cells_and_notes():
    """名望還差：四格時放得下、格子照寫。FB-670（練功多一格，五格每格約 62 px、320 寬約 51 px，灰格小字最多四個字）起，
    「名望還差 15」在 320 寬會被切，改照這一張的做法：格子寫「名望不夠」，還差多少帶句號寫在底下那一行。
    新規則的其他灰格在 tests/test_jianghu_page_web.py。"""
    game = _game("changshe")
    bar = _bar(game)
    assert "<b>交友</b><small>名望不夠</small>" in _cell(bar, "social") and "名望還差 15" not in _face(_cell(bar, "social"))
    assert 'data-why="名望還差 15。"' in _cell(bar, "social")


# ── 原 test_fb670_practice_cell_web.py（整檔搬進來） ──
# FB-670（企劃者 2026-10-22 選練功入口「丙」，PM 給號）：練功藏在探索卡最下面、城裡灰著看不到。行動列多一格「練功」，五格：
# 探索、練功、出陣、交友、移動。野外亮著寫「不限次數」、第二行照勝算上色；城裡灰著寫「城外才有」（城外沒有對手的地方寫「這裡沒有」，
# PM 2026-10-22；照伺服器給的 note），整句（最近的在哪、
# 步行多久）在行動列底下那一行，照伺服器的 action_notes（Game._practice_line，見 tests/test_practice_spots.py），網頁不另寫判斷；
# 不帶路（按不下去）。探索卡回到真的三選一。五格每格約 62 px（320 寬約 51 px）：灰格小字最多四個字，長的原因格子寫短的、整句在底下那一行
# （同 FB-664）；出陣的名字（「出陣・攪局」）只在「・」後面換行。序章與初入江湖照 reveal 的鍵（act:practice）亮，教學沒寫的步驟不畫。
# node 排不了版：這裡看畫了什麼；375／320 寬切不切字在瀏覽器裡量，數字寫在試玩回饋 FB-670 那一列。沒有 node 就略過。
# 減法季批 1（整合設計 6.3【定】）起行動列回到四格（探索、出陣、交友、移動）：練功那一格只在序章與初入江湖（引導）時畫，平常收進「此地還能做」，
# 等批 2 把練功併進探索；行動列底下那幾行說明拿掉了，灰格點了浮出那一句（data-why）。這一份留下還成立的幾條。

HOUR = 3600


MON = 1792339200  # 2026-10-19 週一 00:00（台灣）


NOW = MON + 10 * HOUR


PRACTICE = "explore:practice"


# 城裡操練（新手引導重做，Config.training）開著時城裡那一格是操練、城外練功寫級數（tests/test_training.py）；
# 這一份測的是練功一格本身（操練關著），內容一律把它關掉

def _content(profile):
    c = real_content(profile)
    c.config.training.enabled = False
    no_jianfa(c)  # 減法季探索一顆開著時沒有練功這一格（tests/test_explore_one.py）：這一份測的是舊的練功格
    return c


def _game_fb670(at, faction=None, profile="week7", classic=False):
    c = _content(profile)
    if classic:
        classic_rules(c)
    store = open_world()
    store.seed_first_season(c)
    store.open_season(c, NOW)
    game = Game.new(c, "沈浪", rng=random.Random(0), world=store)
    game.client = None
    game.sync(NOW)
    p = game.state.player
    p.location, p.faction, p.stamina = at, faction, 250.0
    p.tutorial_step = len(c.tutorial.steps)
    return game


def _bar_fb670(m, **S):
    return run_prologue_web(m, "return H.actionBar(H.S.main);", S=S)


def _keys(bar):
    return re.findall(r'class="act-ink[^"]*" data-key="(\w+)"', bar)


def _why(cell):
    return re.search(r'data-why="([^"]*)"', cell).group(1)


def _width_fb670(text):
    """格子小字的寬（以一個漢字為 1）：英數與空白算半個。"""
    return sum(1 if ord(ch) > 0x2E80 else 0.5 for ch in text)


# ── 四格（減法季批 1） ─────────────────────────────────


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
@pytest.mark.slow
def test_outside_the_guide_practice_waits_in_the_here_fold():
    bar = _bar_fb670(server.main_view(_game_fb670("yingshui")))
    assert _keys(bar) == ["explore", "train", "social", "move"] and "--cells:4" in bar
    fold = bar[bar.index("此地還能做"):]
    assert f'data-id="{PRACTICE}"' in fold


PLACES = [  # (陣營, 地點)：城裡、野外、戰線、自家大營、頭目、名望不夠、散人站在戰線上
    (None, "yingchuan"), (None, "yingshui"), (None, "changshe"), (None, "luoyang_road"), (None, "wan_city"),
    (None, "dajiangjun_fu"), (None, "mengjin_ford"), (None, "jade_cave"), ("guan", "changshe"), ("guan", "guan_camp"),
    ("huang", "huangjin_camp"), ("huang", "julu_altar"), ("huang", "changshe"), ("guan", "yingchuan_wilds"),
]


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
@pytest.mark.slow
@pytest.mark.parametrize("profile", ["week7", "season21"])
def test_every_grey_cell_says_at_most_four_characters(profile):
    seen = set()
    for faction, at in PLACES:
        bar = _bar_fb670(server.main_view(_game_fb670(at, faction, profile)))
        assert "practice" not in _keys(bar), (at, faction)
        for off in re.findall(r'<button class="act-ink[^"]* off".*?</button>', bar, re.S):
            assert _width_fb670(_sub(off)) <= 4, (profile, at, faction, off)
            seen.add(_sub(off))
    assert {"未投靠", "名望不夠", "不在戰線", "沒有人"} <= seen  # 真的量到了這幾種灰格


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
@pytest.mark.slow
def test_the_long_reasons_go_to_the_tap():
    """散人站在戰線上：格子「未投靠」，「散人不能出陣」整句是伺服器寫的出陣那一句；名望不夠：格子「名望不夠」，還差多少在點了浮出的那一句。"""
    game = _game_fb670("changshe")
    m = server.main_view(game)
    social = next(o for o in m["options"] if o["id"] == "act:socialize")
    gap = social["label"].split("（", 1)[1].removesuffix("）")
    assert not social["enabled"] and gap.startswith("名望還差 ")  # 前提
    bar = _bar_fb670(m)
    assert "<b>出陣</b><small>未投靠</small>" in _cell(bar, "train") and "<b>交友</b><small>名望不夠</small>" in _cell(bar, "social")
    assert _why(_cell(bar, "train")) == m["action_notes"]["act:train"] and _why(_cell(bar, "train")).startswith(sortie.RANGER_NOTE)
    assert _why(_cell(bar, "social")) == f"{gap}。"


# ── 舊季、序章與初入江湖 ─────────────────────────────


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
@pytest.mark.slow
def test_an_old_season_without_practice_keeps_four_cells():
    game = _game_fb670("yingshui")
    game.state.world.precise_actions = False  # 一類一顆沒蓋章：沒有練功
    bar = _bar_fb670(server.main_view(game))
    assert "practice" not in _keys(bar) and "--cells:4" in bar


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
@pytest.mark.slow
def test_practice_is_a_reveal_key_of_its_own():
    assert "act:practice" in REVEAL_KEYS
    m = server.main_view(_game_fb670("yingshui"))
    others = ["act:explore", "act:train", "act:social", "act:move"]
    assert "practice" not in _keys(_bar_fb670(with_reveal(m, others)))
    assert _keys(_bar_fb670(with_reveal(m, [*others, "act:practice"]))) == ["explore", "practice", "train", "social", "move"]
    assert "practice" in _keys(_bar_fb670(with_reveal(m, ["all"])))


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
@pytest.mark.slow
def test_the_tutorial_only_draws_the_cell_from_a_step_that_reveals_it():
    """序章（草廬）與初入江湖（出了草廬那四步）照教學內容的 reveal：寫了 act:practice 的那一步起才畫，沒寫就不畫，
    也不掉進「此地還能做」。初入江湖走完（onboard 是 None）才全亮。照正式內容的每一步算，教學改了也抓得到。"""
    c = _content("week7")
    store = open_world()
    store.seed_first_season(c)
    store.open_season(c, NOW)
    game = Game.new(c, "沈浪", rng=random.Random(0), world=store)
    game.client = None
    game.sync(NOW)
    p = game.state.player
    p.location, p.stamina = "yingchuan", 250.0
    t = c.tutorial
    lit = False
    for step in range(t.prologue_steps, len(t.steps)):
        p.tutorial_step = step
        lit = lit or "act:practice" in t.steps[step].reveal or "all" in t.steps[step].reveal
        m = server.main_view(game)
        assert m["onboard"] and any(o["id"] == PRACTICE for o in m["options"]), t.steps[step].id
        bar = _bar_fb670(m)
        assert ("practice" in _keys(bar)) is lit, t.steps[step].id
        assert PRACTICE not in bar.replace(_cell(bar, "practice"), "") if lit else PRACTICE not in bar, t.steps[step].id
    p.tutorial_step = len(t.steps)
    m = server.main_view(game)
    bar = _bar_fb670(m)
    assert m["onboard"] is None and "practice" not in _keys(bar) and PRACTICE in bar  # 走完：收進「此地還能做」


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
@pytest.mark.slow
def test_the_hut_never_has_a_practice_option():
    """草廬裡（序章）探索不展開、也沒有練功（_explore_mode_options 在序章是空的）：格子不會在序章冒出來。"""
    c = _content("week7")
    c.config.jianfa.enabled = False  # 減法季的新角色不進草廬（開局第一分鐘）：這一條測的是草廬本身
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world(), prologue=True)
    game.client = None
    m = server.main_view(game)
    assert m["prologue"] is not None and PRACTICE not in [o["id"] for o in m["options"]]
    assert explore_modes.option_id(explore_modes.PRACTICE) == PRACTICE


# ── 原 test_fb671_ink_name_spacing.py（整檔搬進來） ──
# FB-671：360 寬「出陣・守」「出陣・攻」名字 54 px、格子內寬 52.8 px，差 1 px 折成兩行，整排行動列多 21.5 px。
#
# 字距 0.5 px 是每個字後面都加（四個字 2 px）：54 = 4 × 13 + 4 × 0.5。帶「・」的名字（`inkName` 包成 `<span class="nb">`）
# 把字距收到 0 就是 52 px，放得進 360 寬的 52.8 px；沒有「・」的名字（探索、練功、交友、移動、出陣）字距照舊，畫面一個像素都不變。
# CSS 排不出版面，幾何（360／375／320 寬的行數與列高）在瀏覽器裡量；這裡鎖住那條規則。

CSS = (Path(__file__).resolve().parents[2] / "web" / "style.css").read_text(encoding="utf-8")


def _rule(selector: str) -> str:
    match = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert match, f"style.css 找不到 {selector} 這條規則"
    return match.group(1)


def test_names_with_a_middle_dot_drop_the_letter_spacing():
    assert re.search(r"letter-spacing:\s*0\s*;", _rule(".act-ink b .nb"))


def test_plain_names_keep_their_letter_spacing():
    base = _rule(".act-ink b")
    assert "letter-spacing: 0.5px" in base and "font-size: 13px" in base


def test_the_sums_fit_a_360_wide_cell():
    # 360 寬：格子 58.8 − 內距 4 − 邊框 2 = 52.8；四個字 13 px 一字不加字距 = 52。
    inner = 58.8 - 2 * 2 - 2 * 1
    assert 4 * 13 <= inner < 4 * (13 + 0.5)


# ── 原 test_fb_batch_b.py ──

# ── FB-136：決戰開打那一刻看不到三招的鈕 → 輪到出招的回合，三招緊接在場景底下，放手一搏的輸入框與說書人的框排在三招後面 ──
# 在 d2827139 上重現（14 天、官軍、騎著馬上陣、老石「要打大仗了」的框還在，375×812）：框 608～738、輸入框與底下那句 746～843、
# 三招 855～999，分頁列頂 756——第一屏一顆都看不到（QA 那時是 733 起）。照在路上的排法（FB-055）：輪到你按的排前面。
# node 裡沒有版面，這裡只比先後；量到的位置寫在試玩回饋那一列

SHOWDOWN_BOX = {"speaker": "老石", "key": "h_showdown", "scene": "", "text": "「要打大仗了。」", "line": "", "done": [], "end": True,
                "pending": False, "full": True, "hint": True}


@node
def test_fb136_in_a_battle_round_the_three_moves_come_right_after_the_scene(battle):
    _, fighter = battle
    m = {**server.main_view(fighter), "guide": SHOWDOWN_BOX}
    assert m["free_text"] is not None and [o["id"] for o in m["options"] if o["id"].startswith("battle:act:")]
    page = run_prologue_web(m, "return H.pageJianghu();")
    scene, moves = page.index('<section class="card scene">'), page.index('<div class="options">')
    free, box = page.index('<form class="free"'), page.index('<section class="card guide"')
    assert scene < moves < free < box
    assert page.index('data-id="battle:act:') < free  # 三招都在輸入框前面（選單那一塊裡）


@node
def test_u01_on_your_turn_the_chapter_card_and_just_now_sit_below_the_moves(battle):
    """自檢 U-01：輪到你出招時，章回卡（本週卡）與「剛剛」排在三招後面——這一刻要看的是戰場、要按的是三招。"""
    _, fighter = battle
    m = {**server.main_view(fighter), "now": "<p>剛才的事</p>"}
    assert m.get("week_card")
    page = run_prologue_web(m, "return H.pageJianghu();")
    moves = page.index('data-id="battle:act:')
    assert page.index('<section class="card scene') < moves < page.index('class="now')
    cards = [page.find(k) for k in ("ch-card", "wk-card") if k in page]
    assert cards and min(cards) > moves


@node
def test_u09_a_joined_muster_reads_one_line_and_drops_the_greyed_joined_button(on):
    """自檢 U-09：加入了、還在集結——戰局條只留兩端與條（沒有回合格子與「開戰時戰線在正中間」），「你已加入【官軍】，集結還剩現實…」
    收成一行「已加入【官軍】・還剩 …」、其餘點了攤開（S.musterBriefOpen），選單不再有灰的「已加入【官軍】」。"""
    joiner = _player(on, "集結丁", "guan", "wan_city")
    joiner.world.start_battle(on.battles[BATTLE], now=joiner.now)
    joiner.choose("battle:join:guan")
    m = server.main_view(joiner)
    assert any(o["id"] == "battle:join:guan" and not o["enabled"] for o in m["options"]) and "你已加入【官軍】，集結還剩現實" in m["scene"]
    page = run_prologue_web(m, "return H.pageJianghu();")
    assert re.search(r'<details class="muster-brief"><summary>已加入【官軍】・還剩 [^<]+</summary><p>[^<]*集結結束就開打', page)
    assert "你已加入【官軍】" not in page and "已加入【官軍】</span>" not in page and 'data-id="battle:join:guan"' not in page
    assert '<div class="gauge"' in page and "g-rounds" not in page and "g-cap" not in page
    assert '<details class="muster-brief" open>' in run_prologue_web(m, "return H.pageJianghu();", S={"musterBriefOpen": True})


@node
def test_fb136_outside_a_battle_round_the_box_sits_below_the_actions(battle):
    """不是輪到出招（只能觀戰、平常閒著）：序章以外說書人的框排在行動列底下（Joy 2026-10-26「至少要在行動鈕下面」；
    以前照企劃者 10/5 的決定留在行動列上面）。"""
    watcher, _ = battle
    m = {**server.main_view(watcher), "guide": SHOWDOWN_BOX}
    page = run_prologue_web(m, "return H.pageJianghu();")
    assert page.index('class="act-bar') < page.index('<section class="card guide"')


# ── 原 test_fb_batch_c.py ──

needs_node = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


# ── FB-198：375 寬只要有內傷「氣血」兩個字就讓開 → 數字放得下就寫全，放不下才讓開（體力條同一條規則）──
# app.js 的 fitBars 畫好之後量：條上那一行字的字尾（Range）碰不碰得到右邊的「傷 N」或丹的鈕；碰到先 .snug（字小一號、兩個字照寫），
# 還碰到才 .tight（拿掉兩個字）。假瀏覽器沒有排版：給每個狀態（寫全、snug、tight）各一個字尾位置與右邊那一格的左緣，看它收到哪一步。

_FIT_DRIVER = r"""
eval(fn("fitBars"));
let current = null;
const mkBar = (c) => {
  const classes = new Set(c.start || []);
  const state = () => (classes.has("tight") ? "tight" : classes.has("snug") ? "snug" : "full");
  const pick = (v) => (typeof v === "number" ? v : v[state()]);
  const tag = { classList: { contains: (x) => x === (c.pill ? "pill-btn" : "inj") }, getBoundingClientRect: () => ({ left: pick(c.tag) }) };
  const bar = {
    clientWidth: c.width ?? 109,
    classList: { add: (...x) => x.forEach((y) => classes.add(y)), remove: (...x) => x.forEach((y) => classes.delete(y)), contains: (x) => classes.has(x) },
    querySelector: (sel) => (sel.includes("pill-btn") ? (c.tag == null ? null : tag) : { end: () => pick(c.end) }),
  };
  return { bar, classes };
};
const bars = input.cases.map(mkBar);
globalThis.document = {
  getElementById: (id) => (id === "top" ? { querySelectorAll: () => bars.map((b) => b.bar) } : null),
  createRange: () => ({ selectNodeContents(n) { current = n; }, getBoundingClientRect: () => ({ right: current.end() }) }),
};
fitBars();
finish(bars.map((b) => [...b.classes].sort()));
"""


def _fit(cases):
    return webharness.run(_FIT_DRIVER, {"cases": cases})


@needs_node
def test_fb198_the_word_stays_when_the_numbers_fit():
    """QA 的例子（銀兩 50、心得 20、氣血 413/416、傷 3）：寫全放得下就不收；字尾碰到「傷 N」先收一號、兩個字照寫；收一號還碰到才拿掉。"""
    out = _fit([
        {"end": {"full": 230, "snug": 222, "tight": 200}, "tag": {"full": 236, "snug": 239, "tight": 239}},  # 放得下：寫全
        {"end": {"full": 239, "snug": 229, "tight": 207}, "tag": {"full": 236, "snug": 239, "tight": 239}},  # 寫全碰到，收一號放得下
        {"end": {"full": 262, "snug": 250, "tight": 201}, "tag": {"full": 200, "snug": 203, "tight": 203}},  # FB-135：1044/1170、傷 123
    ])
    assert out == [[], ["snug"], ["snug", "tight"]]


@needs_node
def test_fb198_the_stamina_bar_keeps_clear_of_the_pill_button():
    """體力條同一條規則：字尾離丹的鈕至少留 3px；沒有丹的鈕、沒有內傷、條還沒排版（寬 0）都不量、照寫全；上一次留下的 class 先拿掉。"""
    out = _fit([
        {"pill": True, "end": {"full": 98, "snug": 92, "tight": 70}, "tag": 102},  # 98＋3 ≤ 102：放得下
        {"pill": True, "end": {"full": 100, "snug": 92, "tight": 70}, "tag": 102},  # 100＋3 > 102：收一號
        {"end": 300, "tag": None},  # 沒有「傷 N」（沒有內傷）
        {"end": 300, "tag": 100, "width": 0},  # 還沒排版
        {"end": 100, "tag": 200, "start": ["snug", "tight"]},  # 上一次收過、這一次放得下：拿掉
    ])
    assert out == [[], ["snug"], [], [], []]


# ── 原 test_fb_batch_a.py ──

# ── FB-135：狀態列氣血條的數字跟「傷 N」互蓋 ──


def test_fb135_the_hp_word_can_step_aside_for_the_injury_on_a_narrow_bar(hints_content, world):
    """375 寬氣血條只有 99 px，「氣血 348/400」跟「傷 7」擠在一起互相蓋住。「氣血」兩個字包成一格；有內傷、字尾又碰到「傷 N」時拿掉它（FB-198 起量過才收）
    （數字與「傷 N」留著，條上的 title 照舊寫氣血）。沒有內傷時照舊寫「氣血 N/M」。"""
    import webharness
    if webharness.NODE is None:
        pytest.skip("沒有 node，前端畫面測試略過")
    from test_prologue_web import run
    from test_shop2_web import _css, _rule

    import server
    from tianxia.engine import Game

    game = Game.new(hints_content, "傷客", rng=random.Random(0), world=world)
    game.skip_tutorial()
    m = server.main_view(game)
    m["status"].update({"hp": 348, "hp_max": 400, "injury": 7})
    top = run(m, "return H.topHtml();")
    assert '<span><em class="lbl">氣血 </em>348/400</span>' in top and '<span class="inj">傷 7</span>' in top
    css = _css()
    # FB-198 之後不再照條寬一律讓開：app.js 的 fitBars 量到字尾碰到「傷 N」或丹的鈕才收（.snug 字小一號、還碰到才 .tight 拿掉兩個字）
    assert "font-size: 10px" in _rule(css, ".bar.snug > span") and "padding: 0 4px" in _rule(css, ".bar.hp.snug > span.inj")
    assert "display: none" in _rule(css, ".bar.tight .lbl")  # 四位數的氣血配三位數的內傷也放得下（實機量過）
    assert '<em class="lbl">體力 </em>' in top  # 體力條同一件事：丹的鈕蓋住「體力 250/250」
    assert "snug" not in top and "tight" not in top  # 畫出來一律寫全，量過才收
