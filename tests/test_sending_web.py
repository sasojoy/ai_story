"""網頁：按下去之後看得出指令送出去了、在等伺服器（Joy 2026-10-12「點完按鈕例如探索，有時候伺服器沒有立即反應……要有機制讓玩家知道
指令有送出，只是在等伺服器回應」）。

把 web/app.js 的「送出指令的回饋」那一段（busy 與它用的東西）與 api() 切出來，接上假的時鐘、計時器、DOM 與 fetch 在 node 裡跑；沒有 node 就略過。"""
from __future__ import annotations

import pytest

import webharness

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node")

DRIVER = r"""
// 假的時鐘與計時器：tick(毫秒) 把到期的計時器照先後跑掉
let now = 1000;
const timers = [];
let nextId = 1;
const setTimeout = (f, ms = 0) => { const t = { id: nextId++, at: now + ms, f }; timers.push(t); return t.id; };
const clearTimeout = (id) => { const i = timers.findIndex((t) => t.id === id); if (i >= 0) timers.splice(i, 1); };
const settle = () => new Promise((r) => setImmediate(r));
async function tick(ms) {
  const end = now + ms;
  for (;;) {
    await settle();
    timers.sort((x, y) => x.at - y.at || x.id - y.id);
    const t = timers[0];
    if (!t || t.at > end) break;
    now = t.at;
    timers.shift();
    t.f();
  }
  now = end;
  await settle();
}
const Date = { now: () => now };
// 假的 DOM：只有「已送出」那一行與一顆按鈕
let line = null; // 畫面上那一行的字（沒有就是 null）
const lineEl = () => ({ lastElementChild: { set textContent(t) { line = t; } }, remove() { line = null; } });
const document = {
  getElementById: (id) => (id === "sending" && line !== null ? lineEl() : null),
  body: { insertAdjacentHTML: (pos, html) => { line = html.replace(/<[^>]+>/g, ""); } },
};
const button = () => {
  const classes = new Set();
  return { isConnected: true, disabled: false, aria: null, classes,
    classList: { add: (c) => classes.add(c), remove: (c) => classes.delete(c) },
    setAttribute(k, v) { this.aria = v; }, removeAttribute() { this.aria = null; } };
};
const esc = (s) => String(s);
const S = { busy: false, offline: false, moveMode: "walk" };
const toasts = [];
const toast = (t) => toasts.push(t);
let polled = 0;
const poll = () => { polled += 1; };
const setOffline = (v) => { S.offline = v; };
const render = () => {};
let fetchImpl = null;
const fetch = (path, opts) => fetchImpl(path, opts);
class AbortController { constructor() { const s = { aborted: false, listeners: [] }; this.signal = s; } abort() { this.signal.aborted = true; this.signal.listeners.forEach((f) => f()); } }
const kit = new Function(
  "S", "document", "Date", "setTimeout", "clearTimeout", "toast", "poll", "esc", "setOffline", "render", "fetch", "AbortController",
  `let lastAction = 0;
  ${konst("ACTION_TIMEOUT_MS")}
  ${konst("TIMEOUT_TEXT")}
  ${konst("UNSENT_TEXT")}
  ${busyKit()}
  ${slice("async function api(")}
  return { busy, api, press: (el) => { pressed = { el, at: Date.now() }; }, consts: { SENT_WAITING, SLOW_WAITING, STILL_WAITING, TIMEOUT_TEXT, UNSENT_TEXT, ACTION_TIMEOUT_MS } };`,
)(S, document, Date, setTimeout, clearTimeout, toast, poll, esc, setOffline, render, fetch, AbortController);
const H = { kit, tick, S, toasts, button, get line() { return line; }, get polled() { return polled; }, setFetch: (f) => { fetchImpl = f; } };
finish((async () => { return await (async () => { INPUT_SCRIPT })(); })());
"""


def run(script: str):
    return webharness.run(DRIVER.replace("INPUT_SCRIPT", script), {})


def test_the_pressed_button_shows_it_is_sending_and_a_line_appears_while_the_server_is_slow():
    out = run("""
      const { kit, tick, button } = H;
      const btn = button();
      kit.press(btn);
      let resolve;
      const done = kit.busy(() => new Promise((r) => { resolve = r; }));
      const at0 = { sending: btn.classes.has("sending"), disabled: btn.disabled, line: H.line };
      await tick(1499);
      const at1 = H.line;
      await tick(1);
      const at15 = H.line;
      await tick(10500);
      const at12 = H.line;
      resolve();
      await done;
      return { at0, at1, at15, at12, after: { line: H.line, sending: btn.classes.has("sending"), disabled: btn.disabled, busy: H.S.busy },
               c: kit.consts };
    """)
    assert out["at0"] == {"sending": True, "disabled": True, "line": None}  # 一按下去就標「送出中」、不能再按
    assert out["at1"] is None  # 很快回來的動作不浮那一行
    assert out["at15"] == out["c"]["SENT_WAITING"] == "已送出，等候回應…"
    assert out["at12"] == out["c"]["SLOW_WAITING"]
    assert out["after"] == {"line": None, "sending": False, "disabled": False, "busy": False}  # 回來了：收掉、按鈕還原


def test_pressing_again_while_waiting_says_so_instead_of_silently_dropping_the_click():
    out = run("""
      const { kit, tick, button } = H;
      let resolve, second = 0;
      kit.press(button());
      const first = kit.busy(() => new Promise((r) => { resolve = r; }));
      await tick(100);
      await kit.busy(async () => { second += 1; });
      const shown = H.line;
      resolve();
      await first;
      return { second, shown, after: H.line, c: kit.consts };
    """)
    assert out["second"] == 0  # 上一個還沒回來：不送第二個
    assert out["shown"] == out["c"]["STILL_WAITING"]  # 以前一聲不響地丟掉
    assert out["after"] is None


def test_a_failed_action_restores_the_button_so_it_can_be_pressed_again():
    out = run("""
      const { kit, tick, button } = H;
      const btn = button();
      kit.press(btn);
      await kit.busy(async () => { throw new Error("伺服器擋下來"); });
      return { sending: btn.classes.has("sending"), disabled: btn.disabled, busy: H.S.busy, line: H.line, polled: H.polled };
    """)
    assert out == {"sending": False, "disabled": False, "busy": False, "line": None, "polled": 0}


def test_a_stale_press_is_not_marked():
    """確認框問過才送的那一下：原本點的那一顆早就重畫掉了，busy 不去標一個舊的元素。"""
    out = run("""
      const { kit, tick, button } = H;
      const btn = button();
      kit.press(btn);
      await tick(5000);
      let seen;
      await kit.busy(async () => { seen = btn.classes.has("sending"); });
      return seen;
    """)
    assert out is False


def test_an_action_the_server_never_answers_times_out_says_so_and_refreshes():
    out = run("""
      const { kit, tick, button } = H;
      H.setFetch((path, opts) => new Promise((resolve, reject) => { opts.signal.listeners.push(() => reject(new Error("aborted"))); }));
      const btn = button();
      kit.press(btn);
      const done = kit.busy(() => kit.api("/api/choose", { id: "act:explore" }));
      await tick(kit.consts.ACTION_TIMEOUT_MS - 1);
      const still = { busy: H.S.busy, toasts: H.toasts.length };
      await tick(1);
      await done;
      await tick(0);
      return { still, toasts: H.toasts, offline: H.S.offline, busy: H.S.busy, disabled: btn.disabled, polled: H.polled, c: kit.consts };
    """)
    assert out["still"] == {"busy": True, "toasts": 0}
    assert out["toasts"] == [out["c"]["TIMEOUT_TEXT"]]  # 說清楚
    assert out["offline"] is False and out["busy"] is False and out["disabled"] is False  # 可以再按
    assert out["polled"] == 1  # 伺服器那邊可能其實做完了：重抓一次畫面


def test_an_action_that_could_not_be_sent_says_so():
    out = run("""
      const { kit } = H;
      H.setFetch(async () => { throw new TypeError("Failed to fetch"); });
      await kit.busy(() => kit.api("/api/choose", { id: "act:explore" }));
      const action = H.toasts.slice();
      await kit.api("/api/main").catch(() => {}); // 輪詢連不上：只標離線，不每十秒跳一次泡泡
      return { action, after: H.toasts, offline: H.S.offline, c: kit.consts };
    """)
    assert out["action"] == [out["c"]["UNSENT_TEXT"]]
    assert out["after"] == out["action"] and out["offline"] is True


def test_a_quick_answer_clears_the_action_timeout():
    out = run("""
      const { kit, tick } = H;
      H.setFetch(async () => ({ ok: true, status: 200, json: async () => ({ main: 1 }) }));
      const r = await kit.busy(() => kit.api("/api/choose", { id: "act:explore" }));
      await tick(kit.consts.ACTION_TIMEOUT_MS * 2);
      return { toasts: H.toasts, polled: H.polled };
    """)
    assert out == {"toasts": [], "polled": 0}


def test_a_poll_waits_for_the_finger_to_lift_before_redrawing_the_page(game):
    """輪詢帶來新畫面時手指正按在按鈕上：整頁換掉的話按下去的那一顆不在了，放開時 click 落空（按了沒反應）。等放開再畫。"""
    import server
    from test_prologue_web import run as page_run

    m = server.main_view(game)
    out = page_run(m, """return (async () => {
      const page = T.els.page;
      page.innerHTML = "舊畫面";
      const old = H.S.main;
      H.S.main = { ...old, scene: "<p>新的場景</p>" };
      T.docListeners.pointerdown.forEach((f) => f({}));
      await H.refreshPage(old);
      const held = page.innerHTML;
      T.docListeners.pointerup.forEach((f) => f({}));
      await new Promise((r) => setTimeout(r, 5));
      const lifted = page.innerHTML.includes("新的場景");
      page.innerHTML = "舊畫面";
      await H.refreshPage(old); // 沒按著：照舊馬上畫
      return { held, lifted, free: page.innerHTML.includes("新的場景") };
    })();""", S={"tab": "jianghu", "stage": "game"})
    assert out == {"held": "舊畫面", "lifted": True, "free": True}
