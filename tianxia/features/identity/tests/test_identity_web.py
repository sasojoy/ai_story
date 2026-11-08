"""登入頁的格（web/identity.js；帳號與客服第 201 批）：/api/identity/gate 關著時登入頁一個字都不變；開著時照 C 版畫三格、
快速登入那一格放開著的路與客服信箱、記住上次選的格。renderGate 是 app.js 那一支原文，identity.js 整支載進來。"""
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
  const toasts = [], slots = [];
  let html = "", renders = 0, fetched = 0;
  const gate = { get innerHTML() { return html; }, set innerHTML(v) { html = v; } };
  const $app = { get innerHTML() { return html; }, set innerHTML(v) { html = v; }, querySelector: (sel) => (sel === ".gate" ? gate : null) };
  const fetch = () => { fetched++; return Promise.resolve(opts.info ? { ok: true, json: () => Promise.resolve(opts.info) } : { ok: false }); };
  const drawGateSlots = (g) => { for (const f of slots) f(g, S); };
  const real = new Function("S", "$app", "promoHtml", "gatePatchHtml", "loadPatchNotes", "drawGateSlots", fn("renderGate") + "\nreturn renderGate;")(
    S, $app, () => '<div class="promo"></div>', () => "", () => {}, drawGateSlots);
  const renderGate = () => { renders++; real(); };
  const kit = new Function("esc", "toast", "renderGate", "fetch", "localStorage", "registerClicks", "registerGateSlot",
    idSrc + "\nreturn { identityClick };")(esc, (t) => toasts.push(t), renderGate, fetch, localStorage, () => {}, (f) => { if (opts.slot !== false) slots.push(f); });
  return { S, store, toasts, kit, renderGate, html: () => html, counts: () => [renders, fetched] };
}
const tick = () => new Promise((r) => setTimeout(r, 0));
async function main() {
  const out = {};
  for (const mode of [undefined, "login", "register"]) {
    const bare = page({ slot: false, S: { gateMode: mode } });
    bare.renderGate();
    const shut = page({ S: { gateMode: mode } });
    shut.renderGate();
    const first = shut.html();
    await tick();
    shut.renderGate();
    out["shut-" + String(mode)] = { bare: bare.html(), first, again: shut.html(), counts: shut.counts(), stored: shut.store, gateMode: shut.S.gateMode ?? null };
  }
  const info = { ways: ["line", "google", "email", "phone"], support_mail: "help@example.com", turnstile: "" };
  const open = page({ info });
  open.renderGate();
  await tick();
  out.quick = { html: open.html(), stored: { ...open.store }, counts: open.counts() };
  open.S.gateMode = "login";
  open.renderGate();
  out.login = { html: open.html(), stored: { ...open.store } };
  await open.kit.identityClick("identity-way", {}, {});
  out.toasts = open.toasts;
  const back = page({ info, stored: { tx_gate_mode: "register" } });
  back.renderGate();
  await tick();
  out.back = { html: back.html(), gateMode: back.S.gateMode };
  const mailOnly = page({ info: { ways: [], support_mail: "a<b>@example.com", turnstile: "" } });
  mailOnly.renderGate();
  const before = mailOnly.html();
  await tick();
  out.mailOnly = { before, html: mailOnly.html(), gateMode: mailOnly.S.gateMode ?? null, stored: mailOnly.store };
  return out;
}
finish(main());
"""


def _run():
    return run(DRIVER, {"identity": str(WEB / "identity.js")})


def test_gate_html_unchanged_while_closed():
    out = _run()
    for mode in ("undefined", "login", "register"):
        o = out["shut-" + mode]
        assert o["first"] == o["bare"] and o["again"] == o["bare"], mode  # 404：跟沒有這一支逐字一樣
        assert o["counts"] == [2, 1], mode  # 只問一次、不重畫
        assert o["stored"] == {} and o["gateMode"] == (None if mode == "undefined" else mode)
    assert 'id="gate-form"' in out["shut-undefined"]["bare"] and "快速登入" not in out["shut-undefined"]["bare"]


def test_gate_quick_tab_when_open():
    out = _run()
    quick = out["quick"]["html"]
    assert out["quick"]["counts"] == [2, 1]  # 問到了重畫一次
    for label in ("快速登入", "帳號登入", "註冊", "用 LINE 繼續", "用 Google 繼續", "Email", "手機"):
        assert label in quick, label
    assert 'id="gate-form"' not in quick
    assert '<button class="on" data-act="gate" data-mode="quick">快速登入</button>' in quick
    assert quick.count('data-act="identity-way"') == 4
    assert '<a href="mailto:help@example.com">help@example.com</a>' in quick and "（人工回信）" in quick
    assert out["quick"]["stored"] == {"tx_gate_mode": "quick"}
    login = out["login"]["html"]
    assert 'id="gate-form"' in login and 'name="again"' not in login and 'data-act="identity-way"' not in login
    assert '<button class="on" data-act="gate" data-mode="login">帳號登入</button>' in login
    assert out["login"]["stored"] == {"tx_gate_mode": "login"}
    assert out["toasts"] == ["尚未開放"]
    assert out["back"]["gateMode"] == "register" and 'name="again"' in out["back"]["html"]  # 記住上次的格


def test_gate_with_only_a_support_mail_keeps_the_old_tabs():
    out = _run()
    m = out["mailOnly"]
    assert m["gateMode"] is None and m["stored"] == {}
    assert m["html"] != m["before"] and "快速登入" not in m["html"] and 'id="gate-form"' in m["html"]
    assert m["html"].replace(m["html"][m["html"].index('<p class="support-mail'):m["html"].index('<section class="gate-patch"')], "") == m["before"]
    assert "a&lt;b&gt;@example.com" in m["html"] and "a<b>@" not in m["html"]


def test_identity_js_names_no_one_and_marks_new_words():
    text = Path(WEB / "identity.js").read_text(encoding="utf-8")
    for line in text.splitlines():
        if any(w in line for w in ("快速登入", "用 LINE", "尚未開放", "客服信箱")) and "IDENTITY_" in line:
            assert "待 joy 潤" in line, line
