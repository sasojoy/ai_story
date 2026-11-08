"""登入頁的格（web/identity.js；帳號與客服第 201、202 批）：/api/me 沒帶 identity 旗標時不問 gate、登入頁一個字都不變；
旗標在、gate 404 也不變；開著時照 C 版畫三格、快速登入那一格放開著的路、記住上次選的格；LINE 與別的 App 裡藏 Google 鈕；
回呼 auth=new 切到建角色頁、表單改名、送 /api/identity/character，回登入頁或送成功都忘掉 pending。renderGate 是 app.js 那一支原文，identity.js 整支載進來。"""
from __future__ import annotations

from pathlib import Path

from webharness import WEB, run

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
  return out;
}
finish(main());
"""


def _run(path: Path | None = None):
    return run(DRIVER, {"identity": str(path or WEB / "identity.js")})


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
    assert out["toasts"] == ["尚未開放"]
    assert out["start"]["posts"] == [["/api/identity/start", {"provider": "google", "purpose": "login"}]]
    assert out["back"]["gateMode"] == "register" and 'name="again"' in out["back"]["html"]  # 記住上次的格


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
    assert n["stage"] == "create" and n["pending"] == "google" and n["forms"] == ["idp-create-form"] and n["fetched"] == 0
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
        if line.strip().startswith("const IDENTITY_") and any("一" <= ch <= "鿿" for ch in line):
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
