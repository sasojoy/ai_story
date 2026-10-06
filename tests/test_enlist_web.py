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

from conftest import real_content


@pytest.fixture
def on():
    """真實內容、第一季開著（照 tests/test_orders.py 的 real＋on：開關、季長 2.5 天、人數上限 2）。"""
    c = real_content()
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    c.config.season_one, c.config.season_days, c.config.server_max_players = True, 2.5, 2
    return c


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
const env = { now: 0, timers: new Map(), nextId: 1, observers: [], calls: [], applied: [], card: { id: "card" }, hidden: false, apiFail: false, topH: 110, tabsH: 56 };
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
  // 固定的兩條：頂上的狀態列（#top，sticky）與底部分頁列（.tabs，fixed）；它們蓋住的部分不算「在畫面上」
  querySelector: (sel) => (sel === "details.orders" ? env.card
    : sel === "#top" ? { getBoundingClientRect: () => ({ height: env.topH }) }
    : sel === ".tabs" ? { getBoundingClientRect: () => ({ height: env.tabsH }) } : null),
};
const api = (path, body) => {
  env.calls.push([path, body]);
  return env.apiFail ? Promise.reject(new Error("離線")) : Promise.resolve({ main: { from: "view_orders" } });
};
const applyMain = (m) => { env.applied.push(m); };
const S = { tab: "jianghu", sheet: false, main: { guide: { key: "r2_briefing", end: false }, orders: [{ id: "o" }] }, ordersSeen: false, ordersObs: null, ordersTimer: null, ordersVisible: false, ordersRetried: false };
const useObserver = input.noObserver ? undefined : FakeObserver;
const H = new Function(
  "S", "document", "IntersectionObserver", "setTimeout", "clearTimeout", "api", "applyMain",
  src.slice(a, b) + "\nreturn { watchOrders, resetOrdersWatch, ORDERS_SEEN_MS, ORDERS_RETRY_MS };",
)(S, documentFake, useObserver, fakeSetTimeout, fakeClearTimeout, api, applyMain);
const tick = async (ms) => { env.tick(ms); await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); };
Promise.resolve(new Function("H", "S", "env", "tick", "return (async () => {" + input.script + "})()")(H, S, env, tick)).then((out) => {
  process.stdout.write(JSON.stringify(out === undefined ? null : out));
});
"""


GUIDE_DRIVER = r"""
const fs = require("fs");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const src = fs.readFileSync(input.app, "utf8").replace(/\r\n/g, "\n");
const a = src.indexOf("\n  const GUIDE_KEY");
const b = src.indexOf("\n  }\n", src.indexOf("\n  function guideHtml(")) + 4;
if (a < 0 || b < 4) throw new Error("app.js 裡找不到說書人的那一段");
const store = {};
globalThis.localStorage = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: (k) => { delete store[k]; } };
const S = { guideRoad: null, guideFull: null, guidePage: null };
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const pro = () => null; // 序章之外
const H = new Function("S", "esc", "pro", src.slice(a, b) + "\nreturn { guideHtml, nextGuidePage, openGuide };")(S, esc, pro);
process.stdout.write(JSON.stringify(new Function("H", "S", "boxes", input.script)(H, S, input.boxes)));
"""


def run_guide_js(script, boxes):
    if NODE is None:
        pytest.skip("沒有 node")
    done = subprocess.run(
        [NODE, "-e", GUIDE_DRIVER], input=json.dumps({"app": str(APP), "script": script, "boxes": boxes}),
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def _real_boxes(on):
    """真內容、真的引擎：長社投靠官軍之後入伍段三個框（r2、r3、結尾）與一個事件待處理的 r2。"""
    from tests.test_enlist import _joined
    from tests.test_orders import _order, _win

    game = _joined(on)
    boxes = {"r2": game.guide_box()}
    game.state.pending_event = next(iter(on.events))
    boxes["pending"] = game.guide_box()
    game.state.pending_event = None
    game.view_orders()
    boxes["r3"] = game.guide_box()
    _order(game, "siege", "guan", front="yingru")
    with _win():
        game.choose("act:train")
    boxes["end"] = game.guide_box()
    return boxes


def test_the_recruiters_box_is_never_clamped_and_the_first_step_is_paged_by_paragraph(on):
    """G2-W1（設計 6.2「話不會被切掉」）：序章之外，說書人的框長話收成三行（FB-076）；入伍段的框不收：r2 一次一段、按「下一段 ▸」，
    指示（「…在『江湖』頁行動列底下，自己挑一道」）在最後一頁；r3 與結尾整段都在。真的引擎給的框、真的 app.js 畫。"""
    from tianxia import enlist  # noqa: F401（fixture 先把入伍段內容放好）

    boxes = _real_boxes(on)
    got = run_guide_js("""
      const html = (g) => H.guideHtml(g, false);
      const r2 = boxes.r2, first = html(r2);
      H.nextGuidePage(r2);
      const second = html(r2);
      const long = { speaker: "說書人", key: "s2", scene: "", text: "長".repeat(120), line: "", done: [], end: false, pending: false };
      return {
        first, second, r3: html(boxes.r3), end: html(boxes.end),
        narrator: html(long),                              // 一般的長話：照舊收成三行
        pendingShut: html(boxes.pending).includes("guide-line"),   // 事件待處理：預設收成一行，不動
      };
    """, boxes)
    assert "clamp" not in got["first"] and "clamp" not in got["second"] and "clamp" not in got["r3"] and "clamp" not in got["end"]
    assert "一個跛腳的老兵" in got["first"] and "下一段 ▸" in got["first"] and "上頭每週發幾道軍令" not in got["first"]
    assert "上頭每週發幾道軍令，在『江湖』頁行動列底下，自己挑一道。" in got["second"] and "下一段" not in got["second"]
    assert "一個跛腳的老兵" not in got["second"]  # 一次一段
    assert "挑一道軍令，出一次力" in got["r3"] and "知道了" in got["end"] and "你剛剛那一下，也算在裡頭。" in got["end"]
    assert "guide-text clamp" in got["narrator"]  # FB-076：不是入伍段的框不動
    assert got["pendingShut"] is True


def test_the_ending_box_is_one_unpaged_card_with_its_acknowledge_button_in_the_head(on):
    """結尾那一段（老石的「做得乾淨……」一整段，沒有段落）不分頁，因為「知道了」在框的頭、不在文字底下：375×812、真內容、真的做完一道軍令
    （「剛剛」是戰鬥卡片 173–427、場景 439–576）時，框 588–847、「知道了」597–635，離分頁列（756）還有一百多 px，行動列在分頁列底下（859–973），
    按掉「知道了」就回來。量出來的數字；改版面時要重量。這裡釘結構：整段一頁、沒有「下一段」、「知道了」排在文字前面。"""
    boxes = _real_boxes(on)
    assert boxes["end"]["full"] is True and "paged" not in boxes["end"]
    got = run_guide_js("""
      const html = H.guideHtml(boxes.end, false);
      return { html, ack: html.indexOf("guide-ack"), text: html.indexOf("guide-text"), next: html.includes("guide-next"), clamp: html.includes("clamp") };
    """, boxes)
    assert 0 < got["ack"] < got["text"] and not got["next"] and not got["clamp"]
    assert "你剛剛那一下，也算在裡頭。" in got["html"]


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
      await tick(H.ORDERS_RETRY_MS);                                    // 過一陣子自己再送一次（細節見重試的那個測試）
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


def test_the_fixed_bars_do_not_count_as_screen():
    """卡片躲在底部分頁列（或頂上的狀態列）後面不算在畫面上：觀察的範圍扣掉這兩條的高度；設定抽屜開著時整個不看。"""
    got = run_js("""
      H.watchOrders();
      const margin = env.live()[0].opts.rootMargin;
      S.sheet = true;                                     // 設定抽屜蓋在上面
      H.watchOrders();
      const sheet = env.live().length;
      S.sheet = false;
      env.topH = 0; env.tabsH = 0;                         // 兩條都沒有（還沒畫、狀態列藏著）：不扣
      H.watchOrders();
      return { margin, sheet, bare: env.live()[0].opts.rootMargin };
    """)
    assert got == {"margin": "-110px 0px -56px 0px", "sheet": 0, "bare": "0px 0px 0px 0px"}


def test_opening_the_settings_sheet_mid_countdown_cancels_the_wait():
    got = run_js("""
      H.watchOrders();
      env.live()[0].show(1);
      await tick(1000);
      S.sheet = true;
      H.watchOrders();                                    // 抽屜一開整頁重畫
      await tick(5000);
      return env.calls.length;
    """)
    assert got == 0


def test_a_late_callback_from_a_replaced_observer_is_ignored():
    """disconnect 不會清掉已經排好的回報：舊觀察者晚到的回報不能替已經換掉的卡片開始或取消計時。"""
    got = run_js("""
      H.watchOrders();
      const old = env.live()[0];
      H.watchOrders();                                    // 重畫：換了一個觀察者
      env.live()[0].show(0);                              // 新的說：不在畫面上
      old.show(1);                                        // 舊的晚到一個「在畫面上」
      await tick(5000);
      const stale = env.calls.length;
      env.live()[0].show(1);                              // 新的說在畫面上、計時開始
      old.show(0);                                        // 舊的晚到一個「離開了」：不能取消它
      await tick(1500);
      return { stale, calls: env.calls.length };
    """)
    assert got == {"stale": 0, "calls": 1}


def test_a_failed_send_is_tried_once_more_after_a_few_seconds_and_not_forever():
    got = run_js("""
      env.apiFail = true;
      H.watchOrders();
      env.live()[0].show(1);
      await tick(1500);
      const first = env.calls.length;
      await tick(H.ORDERS_RETRY_MS - 1);
      const early = env.calls.length;
      await tick(1);                                      // 一次重試（不等重畫）
      const second = env.calls.length;
      await tick(120000);                                 // 又失敗了：api 每次失敗都跳提示，不連著試；等下一次重畫或捲動
      const later = env.calls.length;
      env.apiFail = false;
      H.watchOrders();
      env.live()[0].show(1);
      await tick(1500);
      return { first, early, second, later, healed: env.calls.length, seen: S.ordersSeen, ms: H.ORDERS_RETRY_MS };
    """)
    assert got["ms"] >= 3000 and got["ms"] <= 10000
    assert (got["first"], got["early"], got["second"], got["later"], got["healed"], got["seen"]) == (1, 1, 2, 2, 3, True)


def test_the_retry_does_not_send_once_the_card_is_gone_or_the_step_has_moved_on():
    got = run_js("""
      env.apiFail = true;
      H.watchOrders();
      env.live()[0].show(1);
      await tick(1500);                                   // 失敗，重試在 ORDERS_RETRY_MS 之後
      env.card = null;
      H.watchOrders();                                    // 卡片不見了：計時收掉
      await tick(60000);
      return env.calls.length;
    """)
    assert got == 1


def test_switching_tab_or_losing_the_card_mid_countdown_cancels_the_wait():
    got = run_js("""
      H.watchOrders();
      env.live()[0].show(1);
      await tick(1000);
      S.tab = "practice";                                 // 切到修練頁：軍令卡在江湖頁，看不到了
      H.watchOrders();
      await tick(5000);
      const tab = env.calls.length;
      S.tab = "jianghu";
      H.watchOrders();
      env.live()[0].show(1);
      await tick(1000);
      env.card = null;                                    // 卡片被拿掉了（這一週還沒發令）
      H.watchOrders();
      await tick(5000);
      return { tab, card: env.calls.length };
    """)
    assert got == {"tab": 0, "card": 0}


def test_the_timer_does_not_send_if_the_observer_last_said_the_card_is_off_screen():
    """白箱：計時走完的那一刻，觀察者最後一次的說法是「不在畫面上」就不送（正常路徑離開畫面時計時早就收掉了，這是多一道保險）。"""
    got = run_js("""
      H.watchOrders();
      env.live()[0].show(1);
      S.ordersVisible = false;
      await tick(1500);
      return env.calls.length;
    """)
    assert got == 0


def test_the_next_page_button_leaves_no_gap_above_it():
    """375×812 量過（長社投靠官軍、剛剛卡片是「投靠官軍」）：入伍段第一步第一頁，「下一段 ▸」上面留 4px 的話行動列下緣是 757，碰到
    分頁列（756）；不留是 753。這是量出來的數字，改樣式表時要重量。"""
    css = (APP.parent / "style.css").read_text(encoding="utf-8")
    rule = next(line for line in css.splitlines() if line.startswith(".guide-next {"))
    assert "margin: 0 0 0 auto" in rule


def test_the_timer_rechecks_the_box_and_the_seen_flag_when_it_fires():
    got = run_js("""
      H.watchOrders();
      env.live()[0].show(1);
      S.main.guide = null;                                // 計時還沒走完框就沒了（略過）：不送
      await tick(1500);
      const gone = env.calls.length;
      S.main.guide = { key: "r2_briefing", end: false };
      H.watchOrders();
      env.live()[0].show(1);
      S.ordersSeen = true;                                // 別的地方已經送了：不重送
      await tick(1500);
      return { gone, seen: env.calls.length };
    """)
    assert got == {"gone": 0, "seen": 0}


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
