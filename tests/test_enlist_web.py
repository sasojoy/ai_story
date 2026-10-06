"""入伍段第一步的網頁那一半（新手引導計畫二 Task 3，preflight F5）：框是引薦人的第一步（key 是 r2_briefing）時，要等軍令卡真的在畫面上
（IntersectionObserver，至少一半進了可視範圍）停留約 1.5 秒，才送 /api/do/view_orders；卡片離開畫面就重新計時。

把 web/app.js 裡那一段（從 ORDERS_SEEN_MS 到 watchOrders 結束）切出來在 node 裡跑，餵假的 document、IntersectionObserver、計時器與 api；
沒有 node 就略過。"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
APP = Path(__file__).parent.parent / "web" / "app.js"
DRIVER = r"""
const fs = require("fs");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const src = fs.readFileSync(input.app, "utf8").replace(/\r\n/g, "\n");
const a = src.indexOf("\n  const ORDERS_SEEN_MS");
const b = src.indexOf("\n  }\n", src.indexOf("\n  function watchOrders(")) + 4;
if (a < 0 || b < 4) throw new Error("app.js 裡找不到入伍段的那一段（ORDERS_SEEN_MS … watchOrders）");

// 假環境：虛擬時鐘的計時器、記下來的 IntersectionObserver、記下來的 api／applyMain 呼叫
const env = { now: 0, timers: new Map(), nextId: 1, observers: [], calls: [], applied: [], card: { id: "card" }, hidden: false, apiFail: false };
const fakeSetTimeout = (fn, ms) => { const id = env.nextId++; env.timers.set(id, { at: env.now + ms, fn }); return id; };
const fakeClearTimeout = (id) => { env.timers.delete(id); };
env.tick = (ms) => {
  const end = env.now + ms;
  for (;;) {
    const due = [...env.timers.entries()].filter(([, t]) => t.at <= end).sort((x, y) => x[1].at - y[1].at)[0];
    if (!due) break;
    env.timers.delete(due[0]);
    env.now = due[1].at;
    due[1].fn();
  }
  env.now = end;
};
class FakeObserver {
  constructor(cb, opts) { this.cb = cb; this.opts = opts; this.targets = []; this.live = true; env.observers.push(this); }
  observe(el) { this.targets.push(el); }
  disconnect() { this.live = false; }
  show(ratio) { this.cb([{ isIntersecting: ratio > 0, intersectionRatio: ratio, target: this.targets[0] }]); }
}
env.live = () => env.observers.filter((o) => o.live);
const documentFake = {
  get hidden() { return env.hidden; },
  querySelector: (sel) => (sel === "details.orders" ? env.card : null),
};
const api = (path, body) => {
  env.calls.push([path, body]);
  return env.apiFail ? Promise.reject(new Error("離線")) : Promise.resolve({ main: { from: "view_orders" } });
};
const applyMain = (m) => { env.applied.push(m); };
const S = { tab: "jianghu", main: { guide: { key: "r2_briefing", end: false }, orders: [{ id: "o" }] }, ordersSeen: false, ordersObs: null, ordersTimer: null, ordersOn: false };
const useObserver = input.noObserver ? undefined : FakeObserver;
const H = new Function(
  "S", "document", "IntersectionObserver", "setTimeout", "clearTimeout", "api", "applyMain",
  src.slice(a, b) + "\nreturn { watchOrders, resetOrdersWatch, ORDERS_SEEN_MS };",
)(S, documentFake, useObserver, fakeSetTimeout, fakeClearTimeout, api, applyMain);
const tick = async (ms) => { env.tick(ms); await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); };
Promise.resolve(new Function("H", "S", "env", "tick", "return (async () => {" + input.script + "})()")(H, S, env, tick)).then((out) => {
  process.stdout.write(JSON.stringify(out === undefined ? null : out));
});
"""


def run_js(script, no_observer=False):
    if NODE is None:
        pytest.skip("沒有 node")
    done = subprocess.run(
        [NODE, "-e", DRIVER], input=json.dumps({"app": str(APP), "script": script, "noObserver": no_observer}),
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_the_card_counts_as_seen_after_a_second_and_a_half_on_screen():
    got = run_js("""
      H.watchOrders();
      const watching = env.live().length;
      const threshold = env.live()[0].opts.threshold;
      await tick(5000);                      // 卡片還沒進畫面：多久都不送
      const before = env.calls.length;
      env.live()[0].show(0.6);               // 進了畫面
      await tick(H.ORDERS_SEEN_MS - 1);
      const early = env.calls.length;
      await tick(1);
      return { watching, threshold, before, early, calls: env.calls, applied: env.applied, seen: S.ordersSeen, ms: H.ORDERS_SEEN_MS };
    """)
    assert got["ms"] == 1500 and got["watching"] == 1 and got["threshold"] in (0.5, [0.5])
    assert got["before"] == 0 and got["early"] == 0
    assert got["calls"] == [["/api/do/view_orders", {}]] and got["applied"] == [{"from": "view_orders"}] and got["seen"] is True


def test_leaving_the_screen_before_it_counts_starts_over():
    got = run_js("""
      H.watchOrders();
      const o = env.live()[0];
      o.show(1);
      await tick(1000);
      o.show(0.2);                           // 捲走了（不到一半）：計時作廢
      await tick(5000);
      const away = env.calls.length;
      o.show(1);                             // 又捲回來：重新計時
      await tick(1499);
      const early = env.calls.length;
      await tick(1);
      return { away, early, after: env.calls.length };
    """)
    assert got == {"away": 0, "early": 0, "after": 1}


def test_a_redraw_keeps_the_running_timer_and_follows_the_new_card():
    """輪詢內容一變整頁重畫：舊的卡片被換掉了，要認新的卡片；已經在跑的計時不能因為重畫就重來（不然每次重畫都把 1.5 秒推遲）。"""
    got = run_js("""
      H.watchOrders();
      env.live()[0].show(1);
      await tick(1000);
      env.card = { id: "new card" };         // 重畫：換了一張新的卡片
      H.watchOrders();
      const live = env.live();
      live[0].show(1);                       // 新的 observer 第一次回報：還在畫面上
      await tick(499);
      const early = env.calls.length;
      await tick(1);
      return { live: live.length, target: live[0].targets[0].id, early, calls: env.calls.length };
    """)
    assert got == {"live": 1, "target": "new card", "early": 0, "calls": 1}


def test_a_redraw_where_the_card_is_off_screen_cancels_the_timer():
    got = run_js("""
      H.watchOrders();
      env.live()[0].show(1);
      await tick(1000);
      H.watchOrders();
      env.live()[0].show(0);                 // 重畫之後新的卡片不在畫面上
      await tick(5000);
      return env.calls.length;
    """)
    assert got == 0


def test_nothing_is_sent_unless_the_recruiters_first_step_is_in_the_box_and_the_card_is_there():
    got = run_js("""
      const out = {};
      S.main.guide = { key: "r3_first_order" };       // 第二步：已經看過了
      H.watchOrders(); out.nextStep = env.live().length;
      S.main.guide = null;                             // 沒有框
      H.watchOrders(); out.noBox = env.live().length;
      S.main.guide = { key: "outro", end: true };
      H.watchOrders(); out.outro = env.live().length;
      S.main.guide = { key: "r2_briefing" };
      S.tab = "practice";                              // 軍令卡在江湖頁，別的分頁看不到它
      H.watchOrders(); out.otherTab = env.live().length;
      S.tab = "jianghu";
      env.card = null;                                 // 沒有軍令（這一週還沒發令）：框等著
      H.watchOrders(); out.noCard = env.live().length;
      env.card = { id: "card" };
      H.watchOrders(); out.ready = env.live().length;
      await tick(60000);
      out.calls = env.calls.length;
      return out;
    """)
    assert got == {"nextStep": 0, "noBox": 0, "outro": 0, "otherTab": 0, "noCard": 0, "ready": 1, "calls": 0}


def test_it_is_sent_once_and_a_failed_send_may_be_tried_again():
    got = run_js("""
      env.apiFail = true;
      H.watchOrders();
      env.live()[0].show(1);
      await tick(1500);
      const failed = { calls: env.calls.length, seen: S.ordersSeen };   // 送不出去：不算看過
      env.apiFail = false;
      H.watchOrders();
      env.live()[0].show(1);
      await tick(1500);
      const sent = { calls: env.calls.length, seen: S.ordersSeen };
      H.watchOrders();                                                  // 看過了：不再開 observer、不再送
      const again = env.live().length;
      await tick(10000);
      return { failed, sent, again, calls: env.calls.length };
    """)
    assert got == {"failed": {"calls": 1, "seen": False}, "sent": {"calls": 2, "seen": True}, "again": 0, "calls": 2}


def test_moving_on_to_another_step_clears_the_seen_flag_for_the_next_time():
    got = run_js("""
      S.ordersSeen = true;
      S.main.guide = { key: "r3_first_order" };
      H.watchOrders();
      const reset = S.ordersSeen;
      S.main.guide = { key: "r2_briefing" };                // 下一季入伍段沒走完、又輪到第一步
      H.watchOrders();
      return { reset, watching: env.live().length };
    """)
    assert got == {"reset": False, "watching": 1}


def test_a_hidden_tab_does_not_count_and_resetting_stops_everything():
    got = run_js("""
      H.watchOrders();
      env.live()[0].show(1);
      env.hidden = true;                                     // 計時走完時分頁在背景：不送
      await tick(1500);
      const hiddenCalls = env.calls.length;
      H.resetOrdersWatch();                                  // 換角色、登出
      const after = { live: env.live().length, timers: env.timers.size, seen: S.ordersSeen };
      return { hiddenCalls, after };
    """)
    assert got == {"hiddenCalls": 0, "after": {"live": 0, "timers": 0, "seen": False}}


def test_a_browser_without_intersection_observer_still_counts_the_card_once_it_is_drawn():
    """舊瀏覽器沒有 IntersectionObserver：沒辦法知道卡片在不在畫面上，退回「畫出來之後 1.5 秒」，不讓玩家永遠卡在第一步。"""
    got = run_js("""
      H.watchOrders();
      await tick(1499);
      const early = env.calls.length;
      await tick(1);
      return { early, calls: env.calls.length };
    """, no_observer=True)
    assert got == {"early": 0, "calls": 1}


def test_the_page_calls_it_after_every_draw_and_resets_it_on_login_and_logout():
    js = APP.read_text(encoding="utf-8").replace("\r\n", "\n")
    after_page = js[js.index("\n  function afterPage() {"):js.index("\n  // ── 登入與取名號 ──")]
    assert "watchOrders();" in after_page
    enter = js[js.index("\n  function enter(data) {"):js.index("\n  function setMain(main) {")]
    assert "resetOrdersWatch();" in enter
    logout = next(line for line in js.splitlines() if 'case "logout":' in line)
    assert "resetOrdersWatch();" in logout
    assert "ordersSeen: false" in js[js.index("\n  const S = {"):js.index("\n  const $app")]
