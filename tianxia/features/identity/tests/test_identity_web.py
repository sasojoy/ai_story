"""登入頁的格（web/identity.js；帳號與客服第 201、202 批）：/api/me 沒帶 identity 旗標時不問 gate、登入頁一個字都不變；
旗標在、gate 404 也不變；開著時照 C 版畫三格、快速登入那一格放開著的路、記住上次選的格；LINE 與別的 App 裡藏 Google 鈕；
回呼 auth=new 切到建角色頁、表單改名、送 /api/identity/character，回登入頁或送成功都忘掉 pending。renderGate 是 app.js 那一支原文，identity.js 整支載進來。"""
from __future__ import annotations

import functools
import re
from pathlib import Path

from webharness import WEB, run

from tianxia.features.identity import codes

DRIVER = r"""
const idSrc = fs.readFileSync(input.identity, "utf8").replace(/\r\n/g, "\n");
const esc = new Function(konst("esc") + "\nreturn esc;")();
function page(opts) {
  const S = Object.assign({ stage: "gate" }, opts.S || {});
  const store = Object.assign({}, opts.stored || {});
  const localStorage = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } };
  const toasts = [], slots = [], posts = [], replaced = [];
  const FORMS = Object.create(null);
  let html = "", renders = 0, fetched = 0, entered = [];
  const gate = {
    get innerHTML() { return html; }, set innerHTML(v) { html = v; },
    insertAdjacentHTML: (where, v) => { html += v; },
  };
  const $app = { get innerHTML() { return html; }, set innerHTML(v) { html = v; }, querySelector: (sel) => (sel === ".gate" ? gate : null) };
  const fetch = () => { fetched++; return Promise.resolve(opts.info ? { ok: true, json: () => Promise.resolve(opts.info) } : { ok: false }); };
  const drawGateSlots = (g) => { for (const f of slots) f(g, S); };
  const real = new Function("S", "$app", "promoHtml", "gatePatchHtml", "loadPatchNotes", "drawGateSlots", fn("renderGate") + "\nreturn renderGate;")(
    S, $app, () => '<div class="promo"></div>', () => "", () => {}, drawGateSlots);
  const renderGate = () => { renders++; real(); };
  const render = () => { if (S.stage === "gate") renderGate(); else html = '<div class="gate"><form id="create-form"></form></div>'; };
  const api = async (path, body) => { posts.push([path, body]); return opts.reply ? opts.reply(path, body) : { stage: "game" }; };
  const enter = (d) => { entered.push(d); };
  const location = { href: opts.href || "https://example.com/" };
  const history = { replaceState: (a, b, u) => { replaced.push(u); } };
  const kit = new Function("S", "esc", "toast", "renderGate", "render", "fetch", "localStorage", "registerClicks", "registerGateSlot",
    "registerForms", "FORMS", "$app", "api", "enter", "location", "history",
    idSrc + "\nreturn { identityClick, identityGateHtml, identityEnv, identityForm };")(
    S, esc, (t) => toasts.push(t), renderGate, render, fetch, localStorage, () => {}, (f) => { if (opts.slot !== false) slots.push(f); },
    (f, keys) => { for (const k of keys) FORMS[k] = f; }, FORMS, $app, api, enter, location, history);
  return { S, store, toasts, kit, renderGate, posts, replaced, FORMS, location, entered: () => entered,
           html: () => html, counts: () => [renders, fetched] };
}
const tick = () => new Promise((r) => setTimeout(r, 0));
const submitForm = { id: "idp-create-form", querySelector: () => ({ disabled: false }) };
async function main() {
  const out = {};
  const info = { ways: ["line", "google", "email", "phone"], turnstile: "" };
  for (const mode of [undefined, "login", "register"]) {
    const bare = page({ slot: false, S: { gateMode: mode } });
    bare.renderGate();
    const shut = page({ S: { gateMode: mode, identity: true } });  // 旗標在、gate 404
    shut.renderGate();
    const first = shut.html();
    await tick();
    shut.renderGate();
    const noflag = page({ info, S: { gateMode: mode } });  // 沒旗標：開著的 gate 也不問
    noflag.renderGate();
    await tick();
    noflag.renderGate();
    out["shut-" + String(mode)] = { bare: bare.html(), first, again: shut.html(), counts: shut.counts(), stored: shut.store,
      gateMode: shut.S.gateMode ?? null, noflag: noflag.html(), noflagCounts: noflag.counts(), noflagStored: noflag.store };
  }
  const open = page({ info, S: { identity: true } });
  open.renderGate();
  await tick();
  out.quick = { html: open.html(), stored: { ...open.store }, counts: open.counts() };
  open.S.gateMode = "login";
  open.renderGate();
  out.login = { html: open.html(), stored: { ...open.store } };
  await open.kit.identityClick("identity-way", { dataset: { way: "email" } }, {});
  out.toasts = open.toasts;
  await open.kit.identityClick("identity-way", { dataset: { way: "google" } }, {});
  out.start = { posts: open.posts, href: open.location.href };
  const back = page({ info, stored: { tx_gate_mode: "register" }, S: { identity: true } });
  back.renderGate();
  await tick();
  out.back = { html: back.html(), gateMode: back.S.gateMode };
  const empty = page({ info: { ways: [], turnstile: "" }, S: { identity: true } });
  empty.renderGate();
  const before = empty.html();
  await tick();
  empty.renderGate();
  out.empty = { before, html: empty.html(), gateMode: empty.S.gateMode ?? null, stored: empty.store };
  const k = open.kit;
  const base = '<div class="seg"><button>x</button></div><form id="gate-form" class="card"></form>';
  out.envHtml = Object.fromEntries(["line", "inapp", "standalone", "browser"].map((env) => [env, k.identityGateHtml(base, info, "quick", env)]));
  out.googleOnlyInLine = k.identityGateHtml(base, { ways: ["google"] }, "quick", "line");
  out.env = [
    ["Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari Line/13.20.0", false],
    ["Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36 Line/14.0.0/IAB", true],
    ["Mozilla/5.0 (iPhone) AppleWebKit/605.1.15 [FBAN/FBIOS;FBAV/440.0]", false],
    ["Mozilla/5.0 (iPhone) AppleWebKit/605.1.15 Instagram 300.0", false],
    ["Mozilla/5.0 (Linux; Android 14; Pixel 8; wv) AppleWebKit/537.36 Version/4.0 Chrome/120 Mobile Safari/537.36", false],
    ["Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36", true],
    ["Mozilla/5.0 (Macintosh) AppleWebKit/605.1.15 Version/17 Safari/605.1.15", false],
    ["Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36 Online/1", false],
  ].map(([ua, sa]) => k.identityEnv(ua, sa));
  // 回呼回來：auth=new 切到建角色頁、補一行；回登入頁交還表單
  const fresh = page({ info, S: { identity: true }, href: "https://example.com/?x=1&auth=new&via=google#top" });
  fresh.renderGate();
  const sameTick = { stage: fresh.S.stage };
  await tick();
  out.authNew = { replaced: fresh.replaced, sameTick, stage: fresh.S.stage, pending: fresh.S.identityPending, forms: Object.keys(fresh.FORMS),
    html: fresh.html(), fetched: fresh.counts()[1] };
  await fresh.kit.identityClick("identity-back", {}, {});
  out.backToLogin = { stage: fresh.S.stage, gateMode: fresh.S.gateMode, pending: fresh.S.identityPending ?? null };
  for (const code of ["fail", "cancel", "weird"]) {
    const p = page({ info, S: { identity: true }, href: `https://example.com/?auth=${code}` });
    p.renderGate();
    p.renderGate();
    out["toast-" + code] = { toasts: p.toasts, replaced: p.replaced };
  }
  // 建角色送出：有 pending 走 identity、成功交還；沒有 pending 走殼的 /api/character
  const made = page({ info, S: { identity: true }, href: "https://example.com/?auth=new&via=line" });
  made.renderGate();
  await tick();
  await made.FORMS["idp-create-form"](submitForm, { name: "柳如煙", gender: "女" });
  out.createIdentity = { posts: made.posts, entered: made.entered(), pending: made.S.identityPending ?? null };
  const plain = page({ info, S: { identity: true } });
  await plain.kit.identityForm({ id: "create-form", querySelector: submitForm.querySelector }, { name: "沈青衫" });
  out.createPlain = { posts: plain.posts, entered: plain.entered() };
  const failing = page({ info, S: { identity: true }, href: "https://example.com/?auth=new&via=line",
    reply: () => { throw new Error("這個名號已有人使用。"); } });
  failing.renderGate();
  await tick();
  let caught = "";
  try { await failing.FORMS["idp-create-form"](submitForm, { name: "周泰安" }); } catch (e) { caught = e.message; }
  out.createFails = { caught, pending: failing.S.identityPending };
  // 第 209 批：identity 開著（gate 帶 pw_min）時註冊格多一行「密碼至少 12 字」、placeholder 換字；登入格、gate 沒帶 pw_min 不動
  const pwInfo = Object.assign({}, info, { pw_min: 12 });
  for (const [key, mode, inf] of [["pwReg", "register", pwInfo], ["pwLogin", "login", pwInfo],
    ["pwEmpty", "register", { ways: [], turnstile: "", pw_min: 12 }], ["pwNone", "register", info]]) {
    const p = page({ info: inf, stored: { tx_gate_mode: mode }, S: { identity: true, gateMode: mode } });
    p.renderGate();
    await tick();
    p.renderGate();
    out[key] = p.html();
  }
  // 第 209 批：管理者重設密碼之後的扣押期，第三方綁定回 ?auth=held（認得、拿掉）
  const held = page({ info, S: { identity: true }, href: "https://example.com/?auth=held&via=line" });
  await tick();
  out.held = { replaced: held.replaced, toasts: held.toasts };
  return out;
}
finish(main());
"""


@functools.cache
def _run_default():
    """沒給 path 的那一份只跑一次、各條共用（第 221 批）：回傳的 dict 各條只讀不改。"""
    return run(DRIVER, {"identity": str(WEB / "identity.js")})


def _run(path: Path | None = None):
    if path is None:
        return _run_default()
    return run(DRIVER, {"identity": str(path)})


def test_gate_does_not_fetch_without_flag():
    out = _run()
    for mode in ("undefined", "login", "register"):
        o = out["shut-" + mode]
        assert o["first"] == o["bare"] and o["again"] == o["bare"], mode  # 旗標在、gate 404：跟沒有這一支逐字一樣
        assert o["counts"] == [2, 1], mode  # 只問一次、不重畫
        assert o["stored"] == {} and o["gateMode"] == (None if mode == "undefined" else mode)
        assert o["noflag"] == o["bare"] and o["noflagCounts"] == [2, 0] and o["noflagStored"] == {}, mode  # 沒旗標：連問都不問
    assert 'id="gate-form"' in out["shut-undefined"]["bare"] and "快速登入" not in out["shut-undefined"]["bare"]


def test_gate_quick_tab_when_open():
    out = _run()
    quick = out["quick"]["html"]
    assert out["quick"]["counts"] == [2, 1]  # 問到了重畫一次
    for label in ("快速登入", "帳號登入", "註冊", "用 LINE 繼續", "用 Google 繼續", "Email", "手機", "隱私權說明"):
        assert label in quick, label
    assert 'id="gate-form"' not in quick
    assert '<button class="on" data-act="gate" data-mode="quick">快速登入</button>' in quick
    assert quick.count('data-act="identity-way"') == 4
    assert out["quick"]["stored"] == {"tx_gate_mode": "quick"}
    login = out["login"]["html"]
    assert 'id="gate-form"' in login and 'name="again"' not in login and 'data-act="identity-way"' not in login
    assert '<button class="on" data-act="gate" data-mode="login">帳號登入</button>' in login
    assert out["login"]["stored"] == {"tx_gate_mode": "login"}
    assert out["toasts"] == []  # 第 204 批：Email、手機不再說尚未開放，換成驗證碼那一頁（test_code_flow_asks_before_switch）
    assert out["start"]["posts"] == [["/api/identity/start", {"provider": "google", "purpose": "login"}]]
    assert out["back"]["gateMode"] == "register" and 'name="again"' in out["back"]["html"]  # 記住上次的格


def test_identity_privacy_link_opens_privacy():
    """第 206 批：第三方那格的「隱私權說明」連條款包的 /privacy、開新分頁（K 波留下的 href="#"）。"""
    quick = _run()["quick"]["html"]
    assert '<a href="/privacy" target="_blank" rel="noopener">隱私權說明</a>' in quick
    assert 'href="#"' not in quick


def test_gate_has_no_mail_line():
    out = _run()
    e = out["empty"]
    assert e["html"] == e["before"] and e["gateMode"] is None and e["stored"] == {}  # 沒有路：原樣（客服信箱歸客服包）
    text = Path(WEB / "identity.js").read_text(encoding="utf-8")
    assert "support_mail" not in text and "IDENTITY_MAIL" not in text and "mailto:" not in text
    assert "support-mail" not in Path(WEB / "identity.css").read_text(encoding="utf-8")


def test_line_inapp_hides_google():
    out = _run()
    h = out["envHtml"]
    for env in ("line", "inapp"):
        assert "用 Google 繼續" not in h[env] and "用 LINE 繼續" in h[env] and "用瀏覽器開啟" in h[env], env
    assert "用 Google 繼續" in h["standalone"] and "從主畫面開的遊戲" in h["standalone"] and "用瀏覽器開啟" not in h["standalone"]
    assert "用 Google 繼續" in h["browser"] and "idp-hint" not in h["browser"]
    assert out["googleOnlyInLine"] == '<div class="seg"><button>x</button></div><form id="gate-form" class="card"></form>'


def test_env_detection_table():
    assert _run()["env"] == ["line", "line", "inapp", "inapp", "inapp", "standalone", "browser", "browser"]


def test_auth_new_switches_to_create_and_back():
    out = _run()
    n = out["authNew"]
    assert n["replaced"] == ["/?x=1#top"]  # 只拿掉 auth、via
    assert n["sameTick"] == {"stage": "gate"}  # renderGate 裡不切：下一拍才切
    assert n["stage"] == "create" and n["pending"] == "google" and n["forms"] == ["idp-create-form", "idp-code-form", "idp-reauth-form", "idp-setpw-form", "idp-reset-form"] and n["fetched"] == 0
    assert 'id="idp-create-form"' in n["html"] and 'id="create-form"' not in n["html"]  # 殼的 submit 鏈不認，identityForm 認
    assert "已經有帳號？用帳號密碼登入，再把這個綁上去" in n["html"] and 'data-act="identity-back"' in n["html"]
    assert out["backToLogin"] == {"stage": "gate", "gateMode": "login", "pending": None}
    assert out["toast-fail"] == {"toasts": ["登入沒有完成，請再試一次"], "replaced": ["/"]}  # 只說一次
    assert out["toast-cancel"] == {"toasts": ["已取消登入"], "replaced": ["/"]}
    assert out["toast-weird"] == {"toasts": [], "replaced": []}  # 不認得的代碼不碰網址


def test_create_posts_to_identity_then_forgets_pending():
    out = _run()
    c = out["createIdentity"]
    assert c["posts"] == [["/api/identity/character", {"name": "柳如煙", "gender": "女"}]]
    assert c["pending"] is None and c["entered"] == [{"stage": "game"}]
    assert out["createPlain"] == {"posts": [], "entered": []}  # 殼的 create-form 不歸這裡
    f = out["createFails"]
    assert f["caught"] == "這個名號已有人使用。" and f["pending"] == "line"  # 失敗留著再試


def test_identity_js_names_no_one_and_marks_new_words():
    text = Path(WEB / "identity.js").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.strip().startswith(("const IDENTITY_", "const IDP_")) and any("一" <= ch <= "鿿" for ch in line):
            assert "待 joy 潤" in line, line
    for word in ("假人", "機器人", "bot"):
        assert word not in text.lower(), word



def test_app_enter_takes_the_flag_in_one_whole_line():
    """殼只多一整行（設計第七節；第 202 批）：enter 開頭照 data.identity 設 S.identity，facade 的放行只認這個字面。"""
    import re

    allow = r"^    if \(data\.identity\) S\.identity = true; //"
    assert ("r'|" + allow + "'") in (WEB.parent / "scripts" / "sb" / "tracks" / "facade.py").read_text(encoding="utf-8")
    lines = Path(WEB / "app.js").read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
    at = lines.index("  function enter(data) {")
    flag = lines[at + 1]
    assert flag.startswith("    if (data.identity) S.identity = true; //") and "待 joy 潤" not in flag
    assert sum("S.identity" in ln for ln in lines) == 1
    assert re.search(allow, flag)


# ── 第 204 批：設定抽屜「帳號綁定」（B 版）、驗證碼那一頁、管理頁的登入方式 ──

DRIVER_204 = r"""
const idSrc = fs.readFileSync(input.identity, "utf8").replace(/\r\n/g, "\n");
const esc = new Function(konst("esc") + "\nreturn esc;")();
function kit(opts) {
  const S = Object.assign({ stage: "gate" }, opts.S || {});
  const posts = [], toasts = [], asked = [];
  let renders = 0;
  const replies = (opts.replies || []).slice();
  const api = async (path, body) => { posts.push([path, body === undefined ? null : body]); return replies.length ? replies.shift() : {}; };
  const ask = (text, yes, go) => { asked.push(text); return opts.confirm !== false ? go() : undefined; }; // 網頁自己的確認框：按「換」才叫 go
  const k = new Function("S", "esc", "toast", "renderGate", "render", "fetch", "localStorage", "registerClicks", "registerGateSlot",
    "registerForms", "$app", "api", "enter", "location", "history", "ask",
    idSrc + "\nreturn { identityFoldHtml, identityCodeHtml, identityAdminHtml, identityClick, identityForm };")(
    S, esc, (t) => toasts.push(t), () => { renders++; }, () => {}, () => Promise.resolve({ ok: false }), { getItem: () => null, setItem: () => {} },
    () => {}, () => {}, () => {}, { querySelector: () => null }, api, () => {}, { href: "https://example.com/" },
    { replaceState: () => {} }, ask);
  return { S, k, posts, toasts, asked, renders: () => renders };
}
async function main() {
  const out = {};
  const { k } = kit({});
  const NOW = 1_800_000_000_000;
  out.closed = k.identityFoldHtml({ kinds: ["password", "line"], has_password: true, phone_missing: true }, {}, NOW);
  out.closedOk = k.identityFoldHtml({ kinds: ["password", "phone"], has_password: true, phone_missing: false }, {}, NOW);
  const meNoPw = { kinds: [{ provider: "phone", name: "手機", shown: "09*****678", new: false, can_unbind: false }], ways: ["line", "email"],
    has_password: false, recent: 0, reset: 0, hold: false, turnstile: "" };
  out.noPw = k.identityFoldHtml({ kinds: ["phone"], has_password: false, phone_missing: false }, { me: meNoPw, open: true }, NOW);
  const mePw = { kinds: [{ provider: "password", name: "密碼", shown: "shen_01", new: false, can_unbind: false },
    { provider: "phone", name: "手機", shown: "09*****678", new: true, can_unbind: true }], ways: [], has_password: true,
    recent: 300, reset: 540, hold: true, turnstile: "" };
  out.pw = k.identityFoldHtml({ kinds: ["password", "phone"], has_password: true, phone_missing: false }, { me: mePw }, NOW);
  out.pwStale = k.identityFoldHtml({ kinds: ["password"], has_password: true, phone_missing: false }, { me: { ...mePw, recent: 0, reset: 0, hold: false } }, NOW);
  out.codeSent = k.identityCodeHtml({ way: "phone", purpose: "login", sent: true, until: NOW + 30000, notice: "已寄出" }, "", NOW);
  out.codeReady = k.identityCodeHtml({ way: "phone", purpose: "login", sent: true, until: NOW - 1 }, "", NOW);
  out.codeFirst = k.identityCodeHtml({ way: "email", purpose: "bind" }, "0x4AAA", NOW);
  out.codeNoKey = k.identityCodeHtml({ way: "phone", purpose: "reauth" }, "", NOW);
  out.codeStale = k.identityCodeHtml({ way: "phone", purpose: "login", sent: true, until: 0, stale: "太久沒驗證了" }, "", NOW);
  // 第 210 批：寄碼前那一張的個資告知短文（info 是 /api/identity/gate 或 /api/identity/me 的回應）
  const INFO = { notice: input.notice, privacy: "/privacy" };
  out.noticeFirst = ["login", "bind", "reauth"].map((purpose) => k.identityCodeHtml({ way: "phone", purpose }, "", NOW, INFO));
  out.noticeSent = k.identityCodeHtml({ way: "phone", purpose: "login", sent: true, until: 0, notice: "已寄出" }, "", NOW, INFO);
  out.noticeNone = [k.identityCodeHtml({ way: "email", purpose: "login" }, "", NOW, { turnstile: "" }),
    k.identityCodeHtml({ way: "email", purpose: "login" }, "", NOW)];
  // 驗證碼登入：按 Email 換成表單；已登入先問一次（{ask}），要換才帶 switch: true 再送
  const flow = kit({ S: { identity: true }, replies: [{ ask: "要換帳號嗎？" }, { message: "驗證碼已寄出" }, { stage: "create", pending: true }] });
  await flow.k.identityClick("identity-way", { dataset: { way: "email" } }, {});
  out.flowState = JSON.parse(JSON.stringify(flow.S.identityCode));
  await flow.k.identityForm({ id: "idp-code-form" }, { phase: "send", to: " a@b.co ", "cf-turnstile-response": "tok" });
  out.flow = { posts: flow.posts, asked: flow.asked, sent: flow.S.identityCode.sent, renders: flow.renders() };
  const no = kit({ S: { identity: true }, confirm: false, replies: [{ ask: "要換帳號嗎？" }] });
  await no.k.identityClick("identity-way", { dataset: { way: "phone" } }, {});
  await no.k.identityForm({ id: "idp-code-form" }, { phase: "send", to: "0912345678" });
  out.declined = { posts: no.posts, sent: !!no.S.identityCode.sent };
  // 管理頁：選中的那一列（帳號鍵）有綁定才畫；identity 關著（S.main 沒有 identity 格）回空字串
  const row = { key: "id:7", login: "id:7", character: "沈青衫", binds: [
    { provider: "phone", name: "手機", shown: "09*****678", bound_at: null, verified_at: 1800000000 },
    { provider: "password", name: "密碼", shown: "ray_77", bound_at: 1800000000, verified_at: null }] };
  out.adminOff = kit({ S: { main: {}, adPicked: row, adResetTarget: "id:7" } }).k.identityAdminHtml();
  out.adminOther = kit({ S: { main: { identity: {} }, adPicked: row, adResetTarget: "ray_77" } }).k.identityAdminHtml();
  out.adminOn = kit({ S: { main: { identity: {} }, adPicked: row, adResetTarget: "id:7" } }).k.identityAdminHtml();
  return out;
}
finish(main());
"""


def _run_204():
    return run(DRIVER_204, {"identity": str(WEB / "identity.js"), "notice": codes.NOTICE})


def test_code_form_before_send_has_notice_and_link():
    """第 210 批（設計第五節、個資法第 8 條）：寄碼前那一張畫 codes.NOTICE，句裡的「隱私權說明」連到 privacy、開新分頁；三種用途都有。"""
    link = '<a href="/privacy" target="_blank" rel="noopener">隱私權說明</a>'
    for html in _run_204()["noticeFirst"]:
        at = html.index('<p class="idp-fine idp-notice">')
        line = html[at:html.index("</p>", at) + 4]
        assert link in line and re.sub(r"<[^>]+>", "", line) == codes.NOTICE  # 字一個不多：連結就是句裡那幾個字
        assert at < html.index('data-act="identity-code-back"') and html.index('name="to"') < at < html.index('value="send"')


def test_code_form_after_send_keeps_sent_line_only():
    sent = _run_204()["noticeSent"]
    assert "idp-notice" not in sent and '<p class="idp-fine">已寄出</p>' in sent


def test_code_form_without_notice_draws_none():
    assert all("idp-notice" not in html and "/privacy" not in html for html in _run_204()["noticeNone"])  # 舊伺服器、沒傳 info


def test_fold_html_closed_line_and_dots():
    out = _run_204()
    closed = out["closed"]
    assert closed.startswith('<details class="fold idp-fold"><summary>帳號綁定<span class="idp-dot" aria-hidden="true"></span>')
    assert "已綁：密碼、LINE・還沒綁手機" in closed and "讀取中" in closed  # 摺著一行寫現況；點開才有 /api/identity/me 的資料
    assert "idp-dot" not in out["closedOk"] and "已綁：密碼、手機" in out["closedOk"]
    pw = out["pw"]
    assert 'data-act="identity-unbind" data-way="phone"' in pw and pw.count('data-act="identity-unbind"') == 1  # 密碼不能解綁
    assert "新綁" in pw and "5 分鐘內可以改" in pw and "保護期中" in pw and 'id="idp-reset-form"' in pw and "9 分鐘內" in pw
    assert 'id="idp-setpw-form"' not in pw and 'id="idp-reauth-form"' not in pw
    stale = out["pwStale"]
    assert 'id="idp-reauth-form"' in stale and 'name="password"' in stale and 'id="idp-reset-form"' not in stale
    assert "客服不會跟你要驗證碼或密碼" in stale


def test_fold_hides_pw_fold_without_password():
    out = _run_204()
    no_pw = out["noPw"]
    assert no_pw.startswith('<details class="fold idp-fold" open>')
    assert 'id="idp-setpw-form"' in no_pw and 'name="login"' in no_pw  # 補設密碼畫在這一格
    assert 'data-act="identity-reauth" data-way="phone"' in no_pw and 'id="idp-reauth-form"' not in no_pw  # 沒密碼：用綁的那一種重驗
    assert 'data-act="identity-bind" data-way="line"' in no_pw and 'data-act="identity-bind" data-way="email"' in no_pw
    src = (WEB / "identity.js").read_text(encoding="utf-8")
    assert "if (!info.has_password) fold.hidden = true;" in src  # 殼的「修改密碼」摺疊藏起來（DOM 那一段，node 測不到）


def test_code_form_countdown_and_tries_hint():
    out = _run_204()
    sent = out["codeSent"]
    assert 'data-act="identity-code-resend" disabled>30 秒後可以重寄</button>' in sent
    assert "驗證碼錯 5 次就作廢" in sent and 'name="code"' in sent and 'autocomplete="one-time-code"' in sent and "已寄出" in sent
    assert 'data-act="identity-code-resend">重寄驗證碼</button>' in out["codeReady"]
    first = out["codeFirst"]
    assert "綁 Email" in first and 'class="cf-turnstile" data-sitekey="0x4AAA"' in first and 'name="to"' in first and 'type="email"' in first
    assert "cf-turnstile" not in out["codeNoKey"] and "用手機重新驗證" in out["codeNoKey"] and 'inputmode="tel"' in out["codeNoKey"]
    assert 'data-act="identity-not-mine">這不是我的帳號</button>' in out["codeStale"] and "太久沒驗證了" in out["codeStale"]
    assert "客服不會跟你要驗證碼" in sent


def test_code_flow_asks_before_switch():
    out = _run_204()
    assert out["flowState"] == {"way": "email", "purpose": "login"}
    body = {"channel": "email", "to": "a@b.co", "turnstile": "tok", "purpose": "login"}
    assert out["flow"]["posts"] == [["/api/identity/code/send", body], ["/api/identity/code/send", {**body, "switch": True}]]
    assert out["flow"]["asked"] == ["要換帳號嗎？"] and out["flow"]["sent"] is True and out["flow"]["renders"] >= 2
    assert out["declined"] == {"posts": [["/api/identity/code/send", {"channel": "phone", "to": "0912345678", "turnstile": "",
                                                                       "purpose": "login"}]], "sent": False}


def test_admin_js_pick_uses_key():
    src = (WEB / "admin.js").read_text(encoding="utf-8")
    assert 'data-act="ad-pick" data-login="${esc(x.key || x.login)}"' in src
    assert '"/api/identity/admin/accounts" : "/api/admin/accounts"' in src
    assert '${typeof identityAdminHtml === "function" ? identityAdminHtml() : ""}' in src
    out = _run_204()
    assert out["adminOff"] == "" and out["adminOther"] == ""  # 關著、或選的不是這一列：一個字都不多
    on = out["adminOn"]
    assert "這個帳號的登入方式" in on and "手機：09*****678（綁定 開帳號時，上次驗證 " in on
    assert 'data-act="identity-admin-unbind" data-way="phone"' in on and on.count('data-act="identity-admin-unbind"') == 1
    assert 'data-act="identity-admin-delete"' in on


def test_new_words_marked():
    """第 204 批新寫給玩家看的字：identity.js 的 IDP_ 常數、IDENTITY_BACK_TEXT 每一行都標待 joy 潤。"""
    text = (WEB / "identity.js").read_text(encoding="utf-8")
    lines = text.splitlines()
    at = next(i for i, ln in enumerate(lines) if "const IDENTITY_BACK_TEXT" in ln)
    for line in lines[at + 1:at + 5]:
        assert "待 joy 潤" in line, line
    assert sum(1 for ln in lines if ln.strip().startswith("const IDP_")) >= 40


# ── 第 208 批：綁、解綁之後 ⚙ 的紅點與摺疊列不重新載入就更新；管理頁解綁、刪帳號做完自己重找；全服池上限那一行 ──

DRIVER_208 = r"""
const idSrc = fs.readFileSync(input.identity, "utf8").replace(/\r\n/g, "\n");
const esc = new Function(konst("esc") + "\nreturn esc;")();
function el(html) {
  const node = { html, open: false, outer: null,
    insertAdjacentHTML(where, v) { node.html += v; node.inserted = (node.inserted || "") + v; },
    querySelector(sel) {
      if (sel !== ".idp-dot" || !node.html.includes("idp-dot")) return null;
      return { remove() { node.html = node.html.replace('<span class="idp-dot" aria-hidden="true"></span>', ""); } };
    },
    set outerHTML(v) { node.outer = v; }, get outerHTML() { return node.outer; } };
  return node;
}
function kit(opts) {
  const S = Object.assign({ stage: "game" }, opts.S || {});
  const posts = [], did = [];
  let renders = 0;
  const replies = (opts.replies || []).slice();
  const api = async (path, body) => { posts.push([path, body === undefined ? null : body]); return replies.length ? replies.shift() : {}; };
  const ask = (text, yes, go) => go();
  const dom = opts.dom || {};
  const document = {
    querySelectorAll: (sel) => (sel === '[data-act="sheet"]' ? (dom.sheets || []) : []),
    querySelector: (sel) => (sel === ".idp-fold" ? dom.fold || null : sel === ".ad-tiles" ? dom.tiles || null
      : sel === ".idp-alert" ? (dom.tiles && dom.tiles.inserted ? {} : null) : null),
    getElementById: () => null,
  };
  const adminDo = async (op, body) => { did.push([op, body, S.adPicked]); };
  const k = new Function("S", "esc", "toast", "renderGate", "render", "fetch", "localStorage", "registerClicks", "registerGateSlot",
    "registerForms", "$app", "api", "enter", "location", "history", "ask", "document", "adminDo", "renderKeepingSheet",
    idSrc + "\nreturn { identityLoadMe, identityDecorate, identityClick, identitySyncDot };")(
    S, esc, () => {}, () => {}, () => {}, () => Promise.resolve({ ok: false }), { getItem: () => null, setItem: () => {} },
    () => {}, () => {}, () => {}, { querySelector: () => null }, api, () => {}, { href: "https://example.com/" },
    { replaceState: () => {} }, ask, document, adminDo, () => { renders++; });
  return { S, k, posts, did, renders: () => renders };
}
const me = (kinds, missing) => ({ kinds: kinds.map((p) => ({ provider: p, name: p, shown: "", new: false, can_unbind: p !== "password" })),
  ways: [], has_password: kinds.includes("password"), recent: 0, reset: 0, hold: false, turnstile: "", phone_missing: missing });
async function main() {
  const out = {};
  // 解綁手機：⚙ 補上紅點、摺疊列的標題跟著換
  const sheet = el("⚙");
  const fold = el("");
  const a = kit({ S: { main: { identity: { kinds: ["password", "phone"], has_password: true, phone_missing: false } } },
    dom: { sheets: [sheet], fold }, replies: [me(["password"], true)] });
  await a.k.identityLoadMe();
  out.unbound = { sheet: sheet.html, fold: fold.outer, info: a.S.main.identity };
  // 綁上手機：紅點拿掉
  const bSheet = el('⚙<span class="idp-dot" aria-hidden="true"></span>');
  const bFold = el("");
  const b = kit({ S: { main: { identity: { kinds: ["password"], has_password: true, phone_missing: true } } },
    dom: { sheets: [bSheet], fold: bFold }, replies: [me(["password", "phone"], false)] });
  await b.k.identityLoadMe();
  out.bound = { info: b.S.main.identity, sheet: bSheet.html, fold: bFold.outer };
  // 管理頁：解綁之後重抓那一列；刪帳號之後是 null
  const row = { key: "id:7", login: "id:7", character: "沈青衫", binds: [{ provider: "phone" }, { provider: "line" }] };
  const fresh = { key: "id:7", login: "id:7", character: "沈青衫", binds: [{ provider: "line" }] };
  const u = kit({ S: { main: { identity: {} }, adPicked: row, adResetTarget: "id:7" }, replies: [{ rows: [fresh] }] });
  await u.k.identityClick("identity-admin-unbind", { dataset: { way: "phone", name: "手機" } }, {});
  await new Promise((r) => setTimeout(r, 10)); // ask 的回呼不在 identityClick 的 await 裡
  out.unbindAdmin = { picked: u.S.adPicked, did: u.did, posts: u.posts, renders: u.renders() };
  const d = kit({ S: { main: { identity: {} }, adPicked: row, adResetTarget: "id:7" }, replies: [{ rows: [] }, { rows: [] }] });
  await d.k.identityClick("identity-admin-delete", {}, {});
  await new Promise((r) => setTimeout(r, 10));
  out.deleteAdmin = { picked: d.S.adPicked, posts: d.posts };
  // 管理頁頂上那一行：有字才插
  const tiles = el("");
  kit({ S: { main: {}, admin: { identity_alerts: ["驗證碼全服上限到了：甲"] } }, dom: { tiles } }).k.identityDecorate();
  out.alertOn = tiles.inserted || "";
  const tiles2 = el("");
  kit({ S: { main: {}, admin: { trends: [] } }, dom: { tiles: tiles2 } }).k.identityDecorate();
  out.alertOff = tiles2.inserted || "";
  return out;
}
finish(main());
"""


def _run_208():
    return run(DRIVER_208, {"identity": str(WEB / "identity.js")})


def test_unbind_and_bind_update_dot_and_fold_without_reload():
    out = _run_208()
    un = out["unbound"]
    assert un["info"] == {"kinds": ["password"], "has_password": True, "phone_missing": True}
    assert un["sheet"] == '⚙<span class="idp-dot" aria-hidden="true"></span>'
    assert '<summary>帳號綁定<span class="idp-dot" aria-hidden="true"></span>' in un["fold"] and "還沒綁手機" in un["fold"]
    bound = out["bound"]
    assert bound["info"] == {"kinds": ["password", "phone"], "has_password": True, "phone_missing": False}
    assert bound["sheet"] == "⚙"  # 綁上之後紅點拿掉
    assert "idp-dot" not in bound["fold"] and "已綁：密碼、手機" in bound["fold"] and "還沒綁手機" not in bound["fold"]


def test_admin_unbind_and_delete_refind_the_row():
    out = _run_208()
    un = out["unbindAdmin"]
    assert un["did"] == [["identity_unbind", {"target": "id:7", "provider": "phone"}, None]]  # 做的時候那一列先清掉（照舊）
    assert un["posts"] == [["/api/identity/admin/accounts", {"q": "id:7"}]]
    assert un["picked"] == {"key": "id:7", "login": "id:7", "character": "沈青衫", "binds": [{"provider": "line"}]} and un["renders"] == 1
    de = out["deleteAdmin"]
    assert de["picked"] is None
    assert de["posts"] == [["/api/identity/admin/accounts", {"q": "id:7"}], ["/api/identity/admin/accounts", {"q": "沈青衫"}]]


def test_admin_alert_line_only_with_words():
    out = _run_208()
    assert out["alertOn"] == '<p class="muted idp-alert">驗證碼全服上限到了：甲</p>'
    assert out["alertOff"] == ""


# ── 第 209 批：註冊格的 12 字提示、?auth=held ──


def test_register_tab_shows_pw_min_only_when_on():
    out = _run()
    reg = out["pwReg"]
    assert '<p class="idp-fine idp-pw-min">密碼至少 12 字。</p><p class="form-msg"' in reg
    assert 'placeholder="至少 12 字"' in reg and 'placeholder="至少 6 字"' not in reg
    assert reg.count("idp-pw-min") == 1  # 再畫一次不重複
    assert "idp-pw-min" not in out["pwLogin"] and 'id="gate-form"' in out["pwLogin"]
    assert "idp-pw-min" in out["pwEmpty"] and 'placeholder="至少 12 字"' in out["pwEmpty"]  # 沒有別的路也畫（12 字照樣要求）
    assert "idp-pw-min" not in out["pwNone"] and 'placeholder="至少 6 字"' in out["pwNone"]  # gate 沒帶 pw_min：一個字不動


def test_auth_held_is_known_and_toasted():
    out = _run()
    assert out["held"]["replaced"] == ["/"]
    assert out["held"]["toasts"] == ["管理者剛幫這個帳號重設了密碼，72 小時內不能綁定新的登入方式。"]


# ── 第 209 批：設定抽屜「帳號綁定」上方的「請用密碼重新登入」──

DRIVER_209 = r"""
const idSrc = fs.readFileSync(input.identity, "utf8").replace(/\r\n/g, "\n");
const esc = new Function(konst("esc") + "\nreturn esc;")();
async function drawer(opts) {
  const S = Object.assign({ stage: "game" }, opts.S || {});
  const posts = [];
  const before = [];
  let inserted = false;
  const idpFold = { insertAdjacentHTML: (where, v) => before.push([where, v]), set outerHTML(v) {}, open: false };
  const parent = { querySelector: (sel) => (sel === ".idp-fold" && inserted ? idpFold : null) };
  const shellFold = { parentElement: parent, hidden: false, insertAdjacentHTML: () => { inserted = true; } };
  const pw = { closest: () => shellFold };
  const document = {
    querySelectorAll: () => [],
    querySelector: (sel) => (sel === ".idp-fold" && inserted ? idpFold : sel === ".idp-relogin" && before.length ? {} : null),
    getElementById: (id) => (id === "pw-form" ? pw : null),
  };
  const api = async (path, body) => {
    posts.push(path);
    if (path === "/api/identity/session") {
      if (opts.session === 404) throw new Error("404");
      return opts.session;
    }
    return { kinds: [], ways: [], has_password: true, recent: 0, reset: 0, hold: false, turnstile: "" };
  };
  const k = new Function("S", "esc", "toast", "renderGate", "render", "fetch", "localStorage", "registerClicks", "registerGateSlot",
    "registerForms", "$app", "api", "enter", "location", "history", "document", "renderKeepingSheet",
    idSrc + "\nreturn { identityDecorate, identityReloginHtml };")(
    S, esc, () => {}, () => {}, () => {}, () => Promise.resolve({ ok: false }), { getItem: () => null, setItem: () => {} },
    () => {}, () => {}, () => {}, { querySelector: () => null }, api, () => {}, { href: "https://example.com/" },
    { replaceState: () => {} }, document, () => {});
  k.identityDecorate();
  await new Promise((r) => setTimeout(r, 10));
  return { posts, before, html: k.identityReloginHtml() };
}
async function main() {
  const info = { kinds: ["password"], has_password: true, phone_missing: false };
  return {
    on: await drawer({ S: { main: { admin: false, identity: info } }, session: { relogin: true } }),
    off: await drawer({ S: { main: { admin: false, identity: info } }, session: { relogin: false } }),
    gone: await drawer({ S: { main: { admin: false, identity: info } }, session: 404 }),
    admin: await drawer({ S: { main: { admin: true, identity: info } }, session: { relogin: true } }),
  };
}
finish(main());
"""


def test_relogin_line_only_when_flag_true():
    out = run(DRIVER_209, {"identity": str(WEB / "identity.js")})
    line = '<p class="form-msg idp-relogin">管理與客服的功能要用帳號密碼重新登入才打得開（驗證碼、LINE、Google 登入的不行）。</p>'
    assert out["on"]["html"] == line
    assert out["on"]["before"] == [["beforebegin", line]] and "/api/identity/session" in out["on"]["posts"]
    assert out["off"]["before"] == [] and out["gone"]["before"] == []  # 假、404（關著）什麼都不畫
    assert out["admin"]["before"] == [] and "/api/identity/session" not in out["admin"]["posts"]  # 已經是管理者：不問


# ── 第 210 批：管理頁（/admin）標題下也畫「請用密碼重新登入」（admin.js 不動；MutationObserver 看到 .ad-head 才問）──

DRIVER_210 = r"""
const idSrc = fs.readFileSync(input.identity, "utf8").replace(/\r\n/g, "\n");
const esc = new Function(konst("esc") + "\nreturn esc;")();
async function page(opts) {
  const S = Object.assign({ stage: "game" }, opts.S || {});
  const posts = [];
  const after = [];
  const head = { insertAdjacentHTML: (where, v) => { after.push([where, v]); head.nextElementSibling = { className: "form-msg idp-relogin" }; },
    nextElementSibling: { className: "muted ad-wait" } };
  const document = {
    querySelectorAll: () => [],
    querySelector: (sel) => (sel === ".ad-head" && opts.head !== false ? head : null),
    getElementById: () => null,
  };
  const api = async (path) => {
    posts.push(path);
    if (path === "/api/identity/session") {
      if (opts.session === 404) throw new Error("404");
      return opts.session;
    }
    return {};
  };
  const k = new Function("S", "esc", "toast", "renderGate", "render", "fetch", "localStorage", "registerClicks", "registerGateSlot",
    "registerForms", "$app", "api", "enter", "location", "history", "document", "renderKeepingSheet",
    idSrc + "\nreturn { identityDecorate };")(
    S, esc, () => {}, () => {}, () => {}, () => Promise.resolve({ ok: false }), { getItem: () => null, setItem: () => {} },
    () => {}, () => {}, () => {}, { querySelector: () => null }, api, () => {},
    { href: "https://example.com" + (opts.path || "/admin"), pathname: opts.path || "/admin" }, { replaceState: () => {} }, document, () => {});
  k.identityDecorate();
  await new Promise((r) => setTimeout(r, 10));
  k.identityDecorate(); // 畫完又觸發一次（插進去那一行本身也會叫 MutationObserver）
  await new Promise((r) => setTimeout(r, 10));
  const once = after.length;
  head.nextElementSibling = { className: "muted ad-wait" }; // admin.js 整頁重畫：那一行被換掉
  k.identityDecorate();
  await new Promise((r) => setTimeout(r, 10));
  return { posts, after, once };
}
async function main() {
  const info = { kinds: ["password"], has_password: true, phone_missing: false };
  const S = () => ({ main: { admin: false, identity: info } });
  return {
    on: await page({ S: S(), session: { relogin: true } }),
    off: await page({ S: S(), session: { relogin: false } }),
    gone: await page({ S: S(), session: 404 }),
    closed: await page({ S: { main: { admin: false } }, session: { relogin: true } }),
    admin: await page({ S: { main: { admin: true, identity: info } }, session: { relogin: true } }),
    jianghu: await page({ S: S(), session: { relogin: true }, path: "/" }),
    nohead: await page({ S: S(), session: { relogin: true }, head: false }),
  };
}
finish(main());
"""


def test_admin_page_relogin_line_when_true():
    out = run(DRIVER_210, {"identity": str(WEB / "identity.js")})
    line = '<p class="form-msg idp-relogin">管理與客服的功能要用帳號密碼重新登入才打得開（驗證碼、LINE、Google 登入的不行）。</p>'
    on = out["on"]
    assert on["once"] == 1 and on["after"][0] == ["afterend", line]  # 標題下一行、觸發兩次只一行
    assert on["after"] == [["afterend", line]] * 2  # admin.js 重畫把那一行換掉：照記下的結果補回
    assert on["posts"].count("/api/identity/session") == 1  # 一頁只問一次


def test_admin_page_no_line_when_false_or_404():
    out = run(DRIVER_210, {"identity": str(WEB / "identity.js")})
    for case in ("off", "gone"):
        assert out[case]["after"] == [] and out[case]["posts"].count("/api/identity/session") == 1
    for case in ("closed", "admin", "jianghu", "nohead"):  # 關著（沒有 identity 格）、已經夠格、不在 /admin、標題還沒畫：不問
        assert out[case]["after"] == [] and "/api/identity/session" not in out[case]["posts"]


# 第 210 批修（R 波審查）：名單上、還不夠格的人開 /admin，殼不畫管理頁、網址換回 /：江湖頁跳同一句（toast），一頁只問一次
DRIVER_210_BOUNCE = r"""
const idSrc = fs.readFileSync(input.identity, "utf8").replace(/\r\n/g, "\n");
const esc = new Function(konst("esc") + "\nreturn esc;")();
async function page(opts) {
  const S = Object.assign({ stage: "game", adminPage: false }, opts.S || {});
  const posts = [];
  const toasts = [];
  const document = { querySelectorAll: () => [], querySelector: () => null, getElementById: () => null };
  const api = async (path) => {
    posts.push(path);
    if (path === "/api/identity/session") {
      if (opts.session === 404) throw new Error("404");
      return opts.session;
    }
    return {};
  };
  const location = { href: "https://example.com" + (opts.from || "/admin"), pathname: opts.from || "/admin" };
  const k = new Function("S", "esc", "toast", "renderGate", "render", "fetch", "localStorage", "registerClicks", "registerGateSlot",
    "registerForms", "$app", "api", "enter", "location", "history", "document", "renderKeepingSheet",
    idSrc + "\nreturn { identityDecorate };")(
    S, esc, (t) => toasts.push(t), () => {}, () => {}, () => Promise.resolve({ ok: false }), { getItem: () => null, setItem: () => {} },
    () => {}, () => {}, () => {}, { querySelector: () => null }, api, () => {}, location, { replaceState: () => {} }, document, () => {});
  location.pathname = "/"; // 殼把網址換回 /
  k.identityDecorate();
  await new Promise((r) => setTimeout(r, 10));
  k.identityDecorate();
  await new Promise((r) => setTimeout(r, 10));
  return { posts, toasts };
}
async function main() {
  const info = { kinds: ["password"], has_password: true, phone_missing: false };
  const S = () => ({ main: { admin: false, identity: info } });
  return {
    on: await page({ S: S(), session: { relogin: true } }),
    off: await page({ S: S(), session: { relogin: false } }),
    gone: await page({ S: S(), session: 404 }),
    closed: await page({ S: { main: { admin: false } }, session: { relogin: true } }),
    admin: await page({ S: { main: { admin: true, identity: info } }, session: { relogin: true } }),
    plain: await page({ S: S(), session: { relogin: true }, from: "/" }),
  };
}
finish(main());
"""


def test_admin_bounce_relogin_toast():
    out = run(DRIVER_210_BOUNCE, {"identity": str(WEB / "identity.js")})
    said = "管理與客服的功能要用帳號密碼重新登入才打得開（驗證碼、LINE、Google 登入的不行）。"
    assert out["on"]["toasts"] == [said] and out["on"]["posts"].count("/api/identity/session") == 1  # 觸發兩次只跳一次、只問一次
    for case in ("off", "gone"):
        assert out[case]["toasts"] == [] and out[case]["posts"].count("/api/identity/session") == 1
    for case in ("closed", "admin", "plain"):  # 關著、已經夠格、不是從 /admin 進來的：不問
        assert out[case]["toasts"] == [] and "/api/identity/session" not in out[case]["posts"]
