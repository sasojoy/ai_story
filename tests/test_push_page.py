"""網頁怎麼用伺服器推送（線上架構推送計畫 Task 3）：web/app.js 沒有建置步驟、也沒有前端測試框架，這裡把推送那一段
（原始碼裡用「伺服器推送」兩行註解框起來的區塊）和真的 poll／busy／setMain／watchQueue 從原始碼切出來，交給 node 跑：
假的 EventSource、假的計時器與時鐘、假的 api，整段時間用 advance(毫秒) 往前撥。沒有 node 就略過（檢查原始碼的測試照跑）。

要證明的事：
- main.push 是 false（預設）：頁面跟以前一模一樣，一個每 10 秒的計時器、每一下都輪詢，從頭到尾不開 EventSource；
- 是 true：開一條 /api/events，連著時平常 60 秒才輪詢一次；每個事件（含 ping）都算有消息，約 40 秒什麼都沒收到就關掉重連，
  這段時間照舊每 10 秒輪詢（預檢 F6）；
- world：隨機等 0～push_spread 秒再抓，不會全服同時擠進來（預檢 F3）；self：馬上抓，但自己那一下動作的回聲不抓第二次；
- 看不到的分頁關掉連線、不抓；看得到了再連、補抓一次；
- 等模型的 watchQueue 照樣每 2 秒問佇列，推送的通知不會在等的時候多打 /api/main。"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
APP = ROOT / "web" / "app.js"
NODE = shutil.which("node")

BEGIN = "  // ── 伺服器推送（線上架構設計 5.3）──"
END = "  // ── 伺服器推送（完）──"

DRIVER = r"""
const fs = require("fs");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const src = fs.readFileSync(input.app, "utf8").replace(/\r\n/g, "\n");
const fn = (header) => {
  const a = src.indexOf(`\n  ${header}`);
  if (a < 0) throw new Error(`app.js 裡找不到 ${header}`);
  return src.slice(a, src.indexOf("\n  }\n", a) + 4);
};
const a = src.indexOf(input.begin), b = src.indexOf(input.end);
if (a < 0 || b < 0 || b < a) throw new Error("app.js 裡找不到「伺服器推送」那一段");
const parts = [
  src.match(/^  const POLL_MS = .*;$/m)[0],
  src.slice(a, b),
  src.match(/^  let pollInFlight = .*;$/m)[0],
  fn("function setMain("), fn("async function busy("), fn("async function poll("), fn("function watchQueue("),
].join("\n");

// ── 假的時鐘與計時器：advance(毫秒) 照時間先後把到期的計時器一個一個跑（含 setInterval），每一步之間讓 await 的東西跑完 ──
let now = 1000000;
const timers = [], scheduled = [], intervals = [];
let nextId = 1;
const settle = () => new Promise((r) => setImmediate(r));
const fake = {
  setTimeout: (f, ms = 0) => { const t = { id: nextId++, at: now + ms, f }; scheduled.push(ms); timers.push(t); return t.id; },
  setInterval: (f, ms) => { const t = { id: nextId++, at: now + ms, f, every: ms }; intervals.push(ms); timers.push(t); return t.id; },
  clearTimeout: (id) => { const i = timers.findIndex((t) => t.id === id); if (i >= 0) timers.splice(i, 1); },
};
async function advance(ms) {
  const end = now + ms;
  for (;;) {
    await settle();
    timers.sort((x, y) => x.at - y.at || x.id - y.id);
    const t = timers[0];
    if (!t || t.at > end) break;
    now = t.at;
    if (t.every) t.at += t.every; else timers.shift();
    t.f();
  }
  now = end;
  await settle();
}
// 在 advance 的時間軸上另外排一件事（測試自己的，不算頁面的計時器）
const every = (ms, f) => { timers.push({ id: nextId++, at: now + ms, f, every: ms }); };
const later = (ms, f) => { timers.push({ id: nextId++, at: now + ms, f }); };

// ── 假的 EventSource ──
class FakeES {
  constructor(url) { this.url = url; this.readyState = 0; this.handlers = {}; this.closed = false; FakeES.all.push(this); }
  addEventListener(type, f) { this.handlers[type] = f; }
  close() { this.closed = true; this.readyState = 2; }
  open() { this.readyState = 1; if (this.onopen) this.onopen(); }
  emit(type) { if (this.closed) throw new Error("關掉的連線又收到事件"); this.handlers[type](); }
  fail(final) { this.readyState = final ? 2 : 0; if (this.onerror) this.onerror(); }
}
FakeES.CLOSED = 2;
FakeES.all = [];
const live = () => FakeES.all.filter((e) => !e.closed);

// ── 假的頁面環境：每個請求記下（路徑, 時刻）；/api/main 每次回一份不一樣的 main（setMain 才算有變）──
const calls = [];
let mainSeq = 0;
const delays = {}; // 路徑 → 這個請求要等幾毫秒才回（模擬動作要一下子）
const api = async (path, body) => {
  calls.push([path, now]);
  if (delays[path]) await new Promise((r) => fake.setTimeout(r, delays[path]));
  if (path === "/api/main") return { push: S.main ? S.main.push : true, push_spread: S.main ? S.main.push_spread : 10, status: {}, seq: ++mainSeq };
  return { main: { push: true, push_spread: 10, status: {}, seq: ++mainSeq } };
};
const fetchQueue = async (url) => { calls.push([url, now]); return { json: async () => ({ ahead: 2 }) }; };
const at = (path) => calls.filter((c) => c[0] === path).map((c) => c[1] - START);
const START = now;
const listeners = {};
const document = { hidden: false, addEventListener: (type, f) => { listeners[type] = f; } };
const window = { EventSource: FakeES };
const rand = { value: 0.5 };
const FakeMath = Object.assign(Object.create(Math), { random: () => rand.value });
const FakeDate = { now: () => now };
const S = { stage: "game", main: null, mainKey: "", busy: false, pushLive: false, moveMode: "walk", unseen: false };
const env = {
  S, document, window, EventSource: FakeES, api, fetch: fetchQueue, Date: FakeDate, Math: FakeMath,
  setTimeout: fake.setTimeout, setInterval: fake.setInterval, clearTimeout: fake.clearTimeout,
  renderTop: () => {}, refreshPage: async () => {}, typing: () => false, paintNewsDot: () => {}, pageKey: () => "",
};
const names = Object.keys(env);
const run = new Function(...names, "ctx", `return (async () => {\n${parts}\n${input.script}\n})();`);
run(...names.map((n) => env[n]), { advance, every, later, calls, at, FakeES, live, listeners, intervals, scheduled, rand, delays, START, timers })
  .then((out) => process.stdout.write(JSON.stringify(out === undefined ? null : out)))
  .catch((e) => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
"""


def js() -> str:
    return APP.read_text(encoding="utf-8").replace("\r\n", "\n")


def page(script: str):
    """在 node 裡跑 script（async 函式本體，看得到推送那一段的所有東西，加上 ctx 裡的 advance、calls、at、FakeES……）；回傳它 return 的東西。"""
    if NODE is None:
        pytest.skip("沒有 node")
    done = subprocess.run(
        [NODE, "-e", DRIVER],
        input=json.dumps({"app": str(APP), "begin": BEGIN, "end": END, "script": "const { advance, every, later, calls, at, FakeES, live, listeners, intervals, scheduled, rand, delays, START, timers } = ctx;\n" + script}),
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


# 每個場景開頭：頁面剛進遊戲（S.main 有了，setMain 記下這一刻是最近一次拿到畫面），照 main.push 決定連不連
START_PAGE = """
S.main = { push: PUSH, push_spread: 10, status: {} };
setMain(S.main);
connectEvents();
"""


def start(push: bool) -> str:
    return START_PAGE.replace("PUSH", "true" if push else "false")


# ── 開關關著：跟以前一模一樣 ──


def test_with_push_off_the_page_polls_every_ten_seconds_and_never_opens_a_stream():
    """main.push 是 false（預設）：頁面只有一個每 10 秒的計時器，每一下都輪詢（跟以前的 setInterval(poll, POLL_MS) 一樣），
    進遊戲、看得到又看不到都不開 EventSource。"""
    out = page(start(False) + """
    await advance(65000);
    const ticks = at("/api/main");
    document.hidden = true; listeners.visibilitychange();
    document.hidden = false; listeners.visibilitychange();
    await advance(0);
    return { streams: FakeES.all.length, intervals, ticks, afterVisible: at("/api/main").length, live: S.pushLive };
    """)
    assert out["streams"] == 0 and out["live"] is False
    assert out["intervals"] == [10000]
    assert out["ticks"] == [10000, 20000, 30000, 40000, 50000, 60000]
    assert out["afterVisible"] == 7  # 看得到了：照舊補抓一次


def test_with_push_off_a_gate_or_a_missing_main_never_connects_either():
    out = page("""
    S.main = { push: false, status: {} };
    connectEvents(); connectEvents();
    S.stage = "gate"; S.main = { push: true, status: {} };
    connectEvents();
    S.stage = "game"; S.main = null;
    connectEvents();
    return { streams: FakeES.all.length };
    """)
    assert out["streams"] == 0  # 沒開、不在遊戲裡、還沒有畫面：都不連


# ── 開關開著：連上、放慢、約 40 秒沒消息就重連 ──


def test_with_push_on_it_opens_one_stream_and_polls_once_a_minute_while_it_is_live():
    out = page(start(True) + """
    const es = FakeES.all[0];
    const url = es.url, before = S.pushLive;
    await advance(25000);                // 還沒連上（沒有 open）：照舊每 10 秒
    const early = at("/api/main");
    es.open();
    every(15000, () => es.emit("ping")); // 伺服器每 15 秒一個 ping
    await advance(180000);
    return { n: FakeES.all.length, url, before, live: S.pushLive, early, all: at("/api/main") };
    """)
    assert out["n"] == 1 and out["url"] == "/api/events" and out["before"] is False and out["live"] is True
    assert out["early"] == [10000, 20000]
    # 連著之後：離上一次拿到畫面滿 55 秒的那一下（每 10 秒一下）才問，也就是約每 60 秒一次
    assert out["all"][2:] == [80000, 140000, 200000]


def test_a_stream_that_goes_quiet_for_forty_seconds_is_replaced_and_the_page_polls_meanwhile():
    """預檢 F6：連線半開（手機睡著、換網路）時瀏覽器很久才會發現。ping 是事件、頁面收得到：約 40 秒一個事件也沒有，
    就關掉重連，pushLive 回到 false、照舊每 10 秒輪詢；新的連上之後補抓一次（這段時間可能漏了通知）。"""
    out = page(start(True) + """
    const first = FakeES.all[0];
    first.open();
    await advance(35000);                // 35 秒沒消息：還沒到
    const stillFirst = FakeES.all.length === 1 && !first.closed;
    await advance(20000);                // 55 秒：已經超過 40 秒，一個 10 秒的計時器那一下發現
    const second = FakeES.all[1];
    const swapped = { n: FakeES.all.length, firstClosed: first.closed, live: S.pushLive, polled: at("/api/main") };
    await advance(20000);                // 新的還沒連上：照舊每 10 秒輪詢
    const meanwhile = at("/api/main");
    second.open();
    await advance(0);
    return { stillFirst, swapped, meanwhile, afterOpen: at("/api/main"), live: S.pushLive, url: second.url };
    """)
    assert out["stillFirst"] is True
    # 50 秒那一下發現：關掉重連，pushLive 回到 false，同一下就照舊輪詢（連著的時候 10～40 秒都沒問）
    assert out["swapped"] == {"n": 2, "firstClosed": True, "live": False, "polled": [50000]}
    assert out["meanwhile"] == [50000, 60000, 70000]
    assert out["afterOpen"] == [50000, 60000, 70000, 75000]  # 新的連上之後補抓一次（這段時間可能漏了通知）
    assert out["live"] is True and out["url"] == "/api/events"


def test_every_event_counts_as_news_the_ping_too():
    """ping、self、world 都算「連線還活著」：每 30 秒來一個（中間超過 15 秒、不到 40 秒），連線一直不換。"""
    out = page(start(True) + """
    const es = FakeES.all[0];
    es.open();
    for (const type of ["ping", "self", "world", "ping", "world", "self"]) {
      await advance(30000);
      es.emit(type);
    }
    await advance(9000);
    return { n: FakeES.all.length, closed: es.closed, live: S.pushLive };
    """)
    assert out == {"n": 1, "closed": False, "live": True}


def test_a_stream_the_server_refused_is_retried_only_once_a_minute():
    """連線失敗（伺服器 502、401、404）：EventSource 自己不再重連，頁面這一邊每隔 RECONNECT_MS 才再試一次；在那之前照舊每 10 秒輪詢。
    只是暫時斷（EventSource 自己在重連，readyState 不是 CLOSED）：留著那個連線，連回來就放慢、補抓一次。"""
    out = page(start(True) + """
    const first = FakeES.all[0];
    first.open();
    first.fail(true);                    // 被拒絕：不會自己重連了
    const down = { live: S.pushLive };
    await advance(59000);
    const before = FakeES.all.length;
    await advance(2000);
    const second = FakeES.all[1];
    second.fail(false);                  // 暫時斷：EventSource 自己會重連
    const retrying = { n: FakeES.all.length, live: S.pushLive, closed: second.closed };
    const polledBefore = at("/api/main").length;
    second.open();
    await advance(0);
    return { down, before, after: FakeES.all.length, retrying, caughtUp: at("/api/main").length - polledBefore, live: S.pushLive };
    """)
    assert out["down"] == {"live": False}
    assert out["before"] == 1 and out["after"] == 2
    assert out["retrying"] == {"n": 2, "live": False, "closed": False}
    assert out["caughtUp"] == 1 and out["live"] is True


# ── world：攤開、self：馬上抓而且不抓兩次 ──


def test_a_world_notice_refetches_after_a_random_wait_within_the_spread():
    """預檢 F3：收到「世界變了」的每個分頁各自隨機等 0～push_spread 秒才抓，全服不會同一兩秒擠進同一把行動鎖；
    等的時候又收到一個，不另外排（已經排的那一次抓到的就是最新的）。"""
    out = page(start(True) + """
    const es = FakeES.all[0];
    es.open();
    every(15000, () => es.emit("ping"));
    const base = scheduled.length;
    rand.value = 0.5;
    es.emit("world"); es.emit("world");
    const waits = scheduled.slice(base);
    await advance(4999);
    const early = at("/api/main").length;
    await advance(1);
    const onTime = at("/api/main").length;
    rand.value = 0.999;
    es.emit("world");
    await advance(9000);
    const notYet = at("/api/main").length;
    await advance(1000);
    const late = at("/api/main").length;
    // push_spread 是 0（兩次通知不必隔開）：馬上抓
    S.main = { ...S.main, push_spread: 0 };
    es.emit("world");
    await advance(0);
    return { waits, early, onTime, notYet, late, instant: at("/api/main").length };
    """)
    assert out["waits"] == [5000]  # 兩個 world 只排了一次，等 0.5 × 10 秒
    assert (out["early"], out["onTime"]) == (0, 1)
    assert (out["notYet"], out["late"]) == (1, 2)  # 0.999 × 10 秒：9 秒時還沒抓，10 秒時抓了
    assert out["instant"] == 3


def test_a_self_notice_refetches_right_away():
    out = page(start(True) + """
    const es = FakeES.all[0];
    es.open();
    every(15000, () => es.emit("ping"));
    await advance(3000);
    es.emit("self");
    await advance(0);
    return { polls: at("/api/main") };
    """)
    assert out["polls"] == [3000]


def test_the_echo_of_this_pages_own_action_is_not_fetched_a_second_time():
    """自己按一下動作：伺服器通知這個角色的每個分頁，包括自己這一個（回聲）。回聲通常在動作還沒回來時就到了（busy 擋掉，poll 不會跑），
    偶爾比動作的回應慢一點到：動作剛做完的一小段時間（ECHO_MS）內的 self 當作回聲，畫面已經是動作回來的那一份，不再抓第二次。
    過了那一小段，別的分頁做的動作照常馬上抓。"""
    out = page(start(True) + """
    const es = FakeES.all[0];
    es.open();
    every(15000, () => es.emit("ping"));
    delays["/api/choose"] = 200;
    const action = busy(async () => { const r = await api("/api/choose", { id: "act:rest" }); setMain(r.main); });
    await advance(100);
    es.emit("self");                     // 回聲，動作還沒回來
    await advance(150);
    await action;
    const duringBusy = at("/api/main").length;
    await advance(500);
    es.emit("self");                     // 回聲慢到：動作做完才 0.5 秒
    await advance(0);
    const afterEcho = at("/api/main").length;
    await advance(1600);
    es.emit("self");                     // 過了 ECHO_MS：這是別的分頁做的動作
    await advance(0);
    return { choose: at("/api/choose").length, duringBusy, afterEcho, final: at("/api/main").length };
    """)
    assert out == {"choose": 1, "duringBusy": 0, "afterEcho": 0, "final": 1}


# ── 看不到的分頁 ──


def test_a_hidden_page_closes_its_stream_and_does_not_refetch_until_it_is_seen_again():
    out = page(start(True) + """
    const first = FakeES.all[0];
    first.open();
    every(15000, () => { const e = live()[0]; if (e) e.emit("ping"); });
    await advance(20000);
    document.hidden = true; listeners.visibilitychange();
    const closed = { closed: first.closed, live: S.pushLive };
    const calls0 = at("/api/main").length;
    await advance(150000);               // 看不到的時候：不連、不抓（連計時器那一下也一樣）
    const whileHidden = { streams: FakeES.all.length, polled: at("/api/main").length - calls0 };
    document.hidden = false; listeners.visibilitychange();
    await advance(0);
    const second = FakeES.all[1];
    second.open();
    await advance(0);
    return { closed, whileHidden, streams: FakeES.all.length, polledOnShow: at("/api/main").length - calls0, live: S.pushLive };
    """)
    assert out["closed"] == {"closed": True, "live": False}
    assert out["whileHidden"] == {"streams": 1, "polled": 0}
    assert out["streams"] == 2 and out["polledOnShow"] == 1 and out["live"] is True  # 看得到了：連回來、補抓一次，就一次


def test_a_page_opened_in_a_hidden_tab_connects_when_it_is_first_seen():
    out = page("""
    document.hidden = true;
    S.main = { push: true, push_spread: 10, status: {} };
    setMain(S.main);
    connectEvents();
    const hiddenStreams = FakeES.all.length;
    document.hidden = false; listeners.visibilitychange();
    return { hiddenStreams, streams: FakeES.all.length };
    """)
    assert out == {"hiddenStreams": 0, "streams": 1}


def test_leaving_the_game_closes_the_stream():
    """登入失效（任何請求回 401，頁面回到登入畫面）、登出：下一下計時器就關掉連線，不留著一條沒人看的。"""
    out = page(start(True) + """
    const es = FakeES.all[0];
    es.open();
    S.stage = "gate";
    await advance(10000);
    return { closed: es.closed, live: S.pushLive, polled: at("/api/main").length };
    """)
    assert out == {"closed": True, "live": False, "polled": 0}


def test_the_page_stops_streaming_when_the_server_says_push_is_off():
    """伺服器重開成沒開推送：下一份畫面的 push 是 false，連線關掉、回到每 10 秒輪詢。"""
    out = page(start(True) + """
    const es = FakeES.all[0];
    es.open();
    every(15000, () => es.emit("ping"));
    S.main = { ...S.main, push: false };
    await advance(10000);
    return { closed: es.closed, live: S.pushLive, polled: at("/api/main") };
    """)
    assert out == {"closed": True, "live": False, "polled": [10000]}


# ── 輪詢與等模型的佇列 ──


def test_a_fresh_screen_from_an_action_postpones_the_next_slow_poll():
    """預檢 F3：動作回來的畫面（setMain）也算「最近一次拿到畫面」，連著推送時下一次慢速輪詢從那一刻起算 60 秒，不會剛按完又輪詢。"""
    out = page(start(True) + """
    const es = FakeES.all[0];
    es.open();
    every(15000, () => es.emit("ping"));
    await advance(40000);
    setMain({ push: true, push_spread: 10, status: {}, seq: 99 });   // 40 秒時動作回來一份畫面
    await advance(70000);
    return { polls: at("/api/main") };
    """)
    assert out["polls"] == [100000]  # 40 秒那一刻起算，滿 55 秒的那一下（每 10 秒一下）才問，不是 60 秒


def test_the_queue_watcher_keeps_asking_while_push_notices_arrive():
    """LLM 佇列的 watchQueue（等模型的時候每 2 秒問一次前面還有幾件）跟推送各做各的：等的時候收到 self、world，
    不多打 /api/main（busy 擋住），佇列照樣每 2 秒問、按鈕上寫「前面還有 N 件」，收掉之後不再問。"""
    out = page(start(True) + """
    const es = FakeES.all[0];
    es.open();
    every(15000, () => es.emit("ping"));
    rand.value = 0;
    delays["/api/choose"] = 5000;
    const el = { textContent: "對方沉吟中…" };
    const action = busy(async () => {
      const stop = watchQueue(el, "對方沉吟中…");
      try { await api("/api/choose", { id: "act:socialize" }); } finally { stop(); }
    });
    await advance(1000);
    es.emit("self"); es.emit("world");
    await advance(1000);                 // 2 秒：佇列第一次問
    const text = el.textContent;
    await advance(4100);
    await action;
    const during = { queue: at("/api/queue"), main: at("/api/main").filter((t) => t <= 5000).length };
    await advance(10000);
    return { text, during, queueAfter: at("/api/queue").length, busy: S.busy };
    """)
    assert out["text"] == "對方沉吟中…（前面還有 2 件）"
    assert out["during"] == {"queue": [2000, 4000], "main": 0}  # 5 秒那一下動作回來、收掉；等的時候 world 的那一抓被 busy 擋住
    assert out["busy"] is False and out["queueAfter"] == 2  # 收掉之後不再問


# ── 原始碼（不需要 node）──


def test_the_page_wiring_is_where_the_server_expects_it():
    src = js()
    # 進遊戲連、不在遊戲裡就關；登出先關再叫伺服器
    enter = src[src.index("  function enter("):src.index("\n  }\n", src.index("  function enter("))]
    assert enter.index("setMain(data.main)") < enter.index("connectEvents()") and "closeEvents()" in enter
    logout = src[src.index('case "logout":'):].split("\n", 1)[0]
    assert logout.index("closeEvents()") < logout.index('api("/api/logout"')
    # 只有一個連線的入口、一個每 10 秒的計時器；舊的 setInterval(poll, …) 沒有了
    assert src.count("new EventSource(") == 1 and "setInterval(pollTick, POLL_MS)" in src and "setInterval(poll," not in src
    # 每次輪詢與每份新畫面都記下時刻（連著推送時慢速輪詢從這裡算）
    poll = src[src.index("  async function poll("):src.index("\n  }\n", src.index("  async function poll("))]
    assert poll.index("pollInFlight = true;") < poll.index("lastPoll = Date.now()") < poll.index('api("/api/main")')
    set_main = src[src.index("  function setMain("):src.index("\n  }\n", src.index("  function setMain("))]
    assert "lastPoll = Date.now()" in set_main
    assert "pushLive: false," in src[src.index("  const S = {"):src.index("  const $app")]
