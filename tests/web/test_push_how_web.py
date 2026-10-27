"""設定頁的「怎麼收到手機通知」（Joy 2026-10-26：一顆鈕點開獨立的一步步說明，不跟玩法說明混在一起）：手機通知開關底下那一顆、
抽屜整頁換成說明、照這台裝置排（iPhone 還在瀏覽器裡先教加入主畫面、從主畫面開了直接第 5 步、Android 直接勾、電腦）、
被擋了那一段、「現在就開通知」只在開得了的時候給、關掉抽屜就回設定。照 tests/test_prologue_web.py 的做法把整支 app.js 放進
node 的假瀏覽器；沒有 node 就略過。"""
from __future__ import annotations

import random

import pytest
import webharness
from test_prologue_web import DRIVER, run

import server
from tianxia.engine import Game

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")

IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
ANDROID = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36"


def _main(content):
    g = Game.new(content, "沈浪", rng=random.Random(0))
    g.client = None
    m = server.main_view(g)
    m["web_push"] = True  # 伺服器開著手機通知
    return m


def _page(m, *, ua="", standalone=False, permission=None, supported=False, S=None):
    """假瀏覽器：userAgent、從主畫面開（navigator.standalone）、通知權限、收不收得到（PushManager 等都在才算）。回說明那一頁的 HTML。"""
    setup = f"""
      T.ctx.navigator.userAgent = {ua!r};
      T.ctx.navigator.standalone = {"true" if standalone else "false"};
      {"T.ctx.Notification = T.ctx.window.Notification = { permission: " + repr(permission) + " };" if permission else ""}
      {"T.ctx.navigator.serviceWorker = {}; T.ctx.window.PushManager = {};" if supported else ""}
      return H.sheetHtml();"""
    return run(m, setup, S={"sheet": True, "pushHow": True, **(S or {})})


def test_the_settings_drawer_has_the_button_under_the_push_toggle(content):
    m = _main(content)
    drawer = run(m, "return H.sheetHtml();", S={"sheet": True})
    assert drawer.index('id="push-on"') < drawer.index('data-act="push-how"') < drawer.index('id="anon"')
    assert "怎麼收到手機通知 ›" in drawer and "push-how-sec" not in drawer  # 鈕在設定裡、說明不在
    m["web_push"] = False  # 伺服器關著：開關與鈕都不畫
    assert 'data-act="push-how"' not in run(m, "return H.sheetHtml();", S={"sheet": True})


def test_an_iphone_still_in_safari_is_told_to_add_to_the_home_screen_first(content):
    page = _page(_main(content), ua=IPHONE)
    assert 'aria-label="怎麼收到手機通知"' in page and 'data-act="push-how-back"' in page
    assert "在 iPhone 的瀏覽器裡" in page and "第 1 到第 4 步" in page
    ios = page.index('<section class="push-how-sec"><h4>iPhone、iPad</h4>')
    assert ios < page.index("<details") and page.count("<details") == 2  # iPhone 攤開在前，Android、電腦收著
    assert "加入主畫面" in page and "Safari" in page and "iOS 16.4" in page and "被擋了怎麼辦" in page
    assert "<b>「設定」→「通知」</b>" in page  # iPhone 被擋了：系統設定那一段
    assert 'data-act="push-yes"' not in page  # 還在瀏覽器裡開不了：不給「現在就開通知」
    assert "玩法說明" not in page and "新手引導" not in page  # 自己一頁，不跟攻略混


def test_an_iphone_opened_from_the_home_screen_goes_straight_to_step_five(content):
    page = _page(_main(content), ua=IPHONE, standalone=True, permission="default", supported=True)
    assert "已經是從主畫面打開的" in page and "第 5 步" in page
    assert 'data-act="push-yes">現在就開通知' in page


def test_android_opens_its_own_section_and_can_turn_it_on_now(content):
    page = _page(_main(content), ua=ANDROID, permission="default", supported=True)
    assert "Android 直接勾就好" in page
    assert page.index('<section class="push-how-sec"><h4>Android 手機</h4>') < page.index("<details")
    assert "<summary>iPhone、iPad</summary>" in page and "<summary>電腦</summary>" in page
    assert "加到主畫面" in page and 'data-act="push-yes"' in page


def test_a_blocked_browser_is_pointed_at_the_blocked_section(content):
    page = _page(_main(content), ua=ANDROID, permission="denied", supported=True)
    assert "被擋著了" in page and 'data-act="push-yes"' not in page
    assert "鎖頭" in page and "「應用程式」→ Chrome" in page


def test_a_desktop_already_on_says_so(content):
    page = _page(_main(content), permission="granted", supported=True, S={"pushOn": True})
    assert "這一台已經開了通知" in page and 'data-act="push-yes"' not in page
    assert page.index('<section class="push-how-sec"><h4>電腦</h4>') < page.index("<details")


def test_the_button_opens_the_page_and_back_or_close_leaves_it(content):
    """照 app.js 的 click 處理：按「怎麼收到手機通知 ›」抽屜整頁換成說明；「← 回設定」回設定；「關閉」連說明一起收，下次打開是設定。"""
    m = _main(content)
    out = run(m, """
      return (async () => {
        const click = async (act) => { const el = { dataset: { act }, classList: { contains: () => false } }; await T.docListeners.click[0]({ target: { closest: () => el } }); };
        const r = {};
        await click("push-how"); r.opened = H.sheetHtml();
        await click("push-how-back"); r.back = H.S.pushHow;
        await click("push-how"); await click("sheet-close"); r.closed = [H.S.sheet, H.S.pushHow];
        H.S.sheet = true; r.again = H.sheetHtml();
        return r;
      })();""", S={"sheet": True})
    assert 'aria-label="怎麼收到手機通知"' in out["opened"] and "push-how-sec" in out["opened"]
    assert out["back"] is False and out["closed"] == [False, False]
    assert 'data-act="push-how"' in out["again"] and "push-how-sec" not in out["again"]


# ── 勾下去之後（iPhone 勾不起來，PM 2026-10-27）：假的 service worker 與 PushManager ──

PUSH_DRIVER = DRIVER.replace('"bookHtml", "peerHtml"]', '"bookHtml", "peerHtml", "pushEnable", "pushRefresh", "pushTest", "pushBoxHtml"]')
assert PUSH_DRIVER != DRIVER


def _push(m, body, *, subscribe="ok", permission="granted", responses=None):
    """iPhone 從主畫面打開、還沒開過通知。subscribe："ok" 訂得到、其他字串是丟出來的錯的 name。permission：按了之後給的權限。
    script 本體裡 box 是設定頁那一塊（pushPaint 只換它的 innerHTML），log 記下先後（perm、register、ready、subscribe、fetch 網址）。"""
    setup = f"""
      const log = [];
      const sub = {{ endpoint: "https://web.push.apple.com/abc", toJSON: () => ({{ endpoint: "https://web.push.apple.com/abc", keys: {{ p256dh: "p", auth: "a" }} }}) }};
      const reg = {{ pushManager: {{
        getSubscription: async () => null,
        subscribe: async (opts) => {{ log.push("subscribe:" + (Object.prototype.toString.call(opts.applicationServerKey) === "[object Uint8Array]")); if ({subscribe!r} !== "ok") {{ const e = new Error("boom"); e.name = {subscribe!r}; throw e; }} return sub; }},
      }} }};
      T.ctx.navigator.userAgent = {IPHONE!r};
      T.ctx.navigator.standalone = true;
      T.ctx.navigator.serviceWorker = {{ register: async () => {{ log.push("register"); return {{}}; }}, get ready() {{ log.push("ready"); return Promise.resolve(reg); }} }};
      T.ctx.window.PushManager = {{}};
      const N = {{ permission: "default", requestPermission: async () => {{ log.push("perm@" + T.calls.length); N.permission = {permission!r}; return {permission!r}; }} }};
      T.ctx.Notification = T.ctx.window.Notification = N;
      T.ctx.atob = (s) => Buffer.from(s, "base64").toString("binary");
      const box = {{ innerHTML: "" }};
      T.qs[".push-box"] = box;
      return (async () => {{ {body} }})();"""
    return webharness.run(PUSH_DRIVER, {"m": m, "script": setup, "S": {"sheet": True}, "menxia": None, "stored": {}, "responses": {**(responses or {}), "/api/push/": {}, "/api/push": {"key": "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4", "kinds": {}}}})


def test_allowing_on_an_iphone_subscribes_and_ticks_the_box(content):
    """按允許之後：先問權限（之前不等任何網路請求）、等 service worker 啟用好（ready）才訂，公鑰是 Uint8Array；訂到了交給伺服器、勾起來。"""
    out = _push(_main(content), """
      await H.pushEnable();
      return { log, html: box.innerHTML, calls: T.calls.map((c) => c[0]), on: H.S.pushOn };""")
    assert out["log"][0] == "perm@0"  # 第一件事就問權限：iPhone 只在按下去的那一下肯問
    assert out["log"].index("ready") < out["log"].index("subscribe:true")  # 啟用好了才訂；公鑰轉成 Uint8Array
    assert "/api/push/subscribe" in out["calls"] and out["on"] is True
    assert 'id="push-on" checked' in out["html"] and "傳一則測試通知" in out["html"]
    for name in ("來信", "約戰", "決戰集結", "被截殺", "被〈天下形勢〉提到"):  # 開了：五種各一個開關，預設全開
        assert f'checked > {name}</label>' in out["html"]


def test_a_failed_subscribe_is_written_on_the_page_not_swallowed(content):
    out = _push(_main(content), """
      await H.pushEnable();
      return { html: box.innerHTML, on: H.S.pushOn };""", subscribe="AbortError")
    assert out["on"] is False and 'id="push-on" ' in out["html"] and 'id="push-on" checked' not in out["html"]
    assert '<p class="push-err">推送服務沒接通（boom）' in out["html"]
    denied = _push(_main(content), "await H.pushEnable(); return box.innerHTML;", permission="denied")
    assert "「設定」→「通知」→「天下大勢」" in denied  # iPhone 按了不允許：寫去哪裡打開


def test_opening_settings_repaints_only_the_push_box(content):
    """打開設定問這台裝置訂著沒：只換「手機通知」那一塊（以前整個畫面重畫，iPhone 上一直閃），順手先拿好公鑰。"""
    out = _push(_main(content), """
      const before = T.els.app.innerHTML;
      await H.pushRefresh();
      return { same: T.els.app.innerHTML === before, key: H.S.pushKey, painted: box.innerHTML.includes('id="push-on"') };""")
    assert out["same"] and out["painted"] and out["key"].startswith("BCVx")


def test_the_test_button_writes_what_happened(content):
    m = _main(content)
    body = """
      H.S.pushOn = true;
      reg.pushManager.getSubscription = async () => sub;
      await H.pushTest();
      return { html: box.innerHTML, sent: T.calls.find((c) => c[0] === "/api/push/test") };"""
    ok = _push(m, body, responses={"/api/push/test": {"sent": True, "error": ""}})
    assert ok["sent"][1] == {"endpoint": "https://web.push.apple.com/abc"} and "送出去了" in ok["html"]
    bad = _push(m, body, responses={"/api/push/test": {"sent": False, "error": "推送服務不收（回 500）"}})
    assert "沒送出去：推送服務不收（回 500）" in bad["html"]

