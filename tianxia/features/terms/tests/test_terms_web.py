"""註冊的兩個勾選（web/terms.js；帳號與客服第 206 批）：註冊模式的 #gate-form 與 identity 建角色那一張插兩個勾選與 hidden 版號，
登入模式與殼自己的 #create-form 不插；/api/terms/version 非 200（關著 404）不插、這一頁不再問；沒全勾就送出擋下、寫那一句。
terms.js 整支載進來（node 沒有 MutationObserver，觀察那一段跳過），假 DOM 只認這支用到的選擇器。"""
from __future__ import annotations

from webharness import WEB, run

DRIVER = r"""
const tSrc = fs.readFileSync(input.terms, "utf8").replace(/\r\n/g, "\n");
function mkForm(id, html) {
  const f = { id, inserted: "", msgText: "", boxes: [] };
  const put = (where, v) => {
    f.inserted += v;
    f.boxes = [...f.inserted.matchAll(/type="checkbox" name="(\w+)"/g)].map((m) => ({ name: m[1], checked: false }));
  };
  const msg = { insertAdjacentHTML: put, set textContent(v) { f.msgText = v; }, get textContent() { return f.msgText; } };
  f.querySelector = (sel) => {
    if (sel === '[name="again"]') return html.includes('name="again"') ? {} : null;
    if (sel === ".terms-check") return f.inserted.includes("terms-check") ? {} : null;
    if (sel === ".form-msg") return msg;
    return null;
  };
  f.querySelectorAll = (sel) => (sel === '.terms-check input[type="checkbox"]' ? f.boxes : []);
  f.insertAdjacentHTML = put;
  return f;
}
function load(forms, reply) {
  const fetched = [];
  const document = { querySelectorAll: () => forms };
  const fetch = (url) => { fetched.push(url); return reply(url); };
  const kit = new Function("document", "fetch", tSrc + "\nreturn { termsInsertChecks, termsBlockSubmit };")(document, fetch);
  return { kit, fetched };
}
const ok = (url) => Promise.resolve({ ok: true, json: () => Promise.resolve({ version: "v9" }) });
const gone = () => Promise.resolve({ ok: false, json: () => Promise.resolve({}) });
const down = () => Promise.reject(new Error("offline"));
function submit(kit, form) {
  const ev = { target: form, prevented: 0, stopped: 0, preventDefault() { this.prevented++; }, stopImmediatePropagation() { this.stopped++; } };
  kit.termsBlockSubmit(ev);
  return [ev.prevented, ev.stopped, form.msgText];
}
async function resend(reply) {
  const form = mkForm("gate-form", '<input name="again">');
  const hidden = { value: "" };
  const base = form.querySelector;
  form.querySelector = (sel) => (sel === '[name="terms_version"]' ? hidden : base(sel));
  let n = 0;
  const t = load([form], (url) => reply(url, ++n));
  await t.kit.termsInsertChecks();
  hidden.value = /name="terms_version" value="(\w+)"/.exec(form.inserted)[1];
  form.boxes.forEach((b) => { b.checked = true; });
  const shell = []; // app.js 那一支：沒被擋下（stopImmediatePropagation）才輪得到，記下它看到的版號
  const events = [];
  const fire = () => {
    const ev = { target: form, prevented: 0, stopped: 0, preventDefault() { this.prevented++; }, stopImmediatePropagation() { this.stopped++; } };
    t.kit.termsBlockSubmit(ev);
    events.push([ev.prevented, ev.stopped]);
    if (!ev.stopped) shell.push(hidden.value);
  };
  form.requestSubmit = () => { if (events.length < 5) fire(); };
  fire();
  await new Promise((r) => setTimeout(r, 10));
  return { events, shell, fetched: t.fetched, msg: form.msgText };
}
async function main() {
  const out = {};
  const reg = mkForm("gate-form", '<input name="again">'), login = mkForm("gate-form", ""), idp = mkForm("idp-create-form", ""),
    create = mkForm("create-form", "");
  const a = load([reg, login, idp, create], ok);
  await a.kit.termsInsertChecks();
  await a.kit.termsInsertChecks();
  out.insert = { reg: reg.inserted, login: login.inserted, idp: idp.inserted, create: create.inserted, fetched: [...a.fetched] }; // 抄一份：第 210 批起送出前會再問一次
  out.blocked = [submit(a.kit, reg)];
  reg.msgText = "";
  reg.boxes[0].checked = true;
  out.blocked.push(submit(a.kit, reg));
  reg.msgText = "";
  reg.boxes[1].checked = true;
  out.passed = submit(a.kit, reg);
  out.loginPassed = submit(a.kit, login);
  const reg404 = mkForm("gate-form", '<input name="again">');
  const b = load([reg404], gone);
  await b.kit.termsInsertChecks();
  await b.kit.termsInsertChecks();
  out.gone = { inserted: reg404.inserted, fetched: b.fetched, passed: submit(b.kit, reg404) };
  const regDown = mkForm("gate-form", '<input name="again">');
  const c = load([regDown], down);
  await c.kit.termsInsertChecks();
  await c.kit.termsInsertChecks();
  out.down = { inserted: regDown.inserted, fetched: c.fetched };
  // 第 210 批：兩格都勾了，送出前重問一次版號（條款改版後沒重新整理的註冊頁）：攔下、重問、換 hidden、requestSubmit 再送一次放行
  out.fresh = await resend((url, n) => Promise.resolve({ ok: true, json: () => Promise.resolve({ version: n === 1 ? "v9" : "v10" }) }));
  out.freshDown = await resend((url, n) => (n === 1 ? ok(url) : down()));
  return out;
}
finish(main());
"""


def _run():
    return run(DRIVER, {"terms": str(WEB / "terms.js")})


def test_checks_inserted_in_register_mode_only():
    out = _run()["insert"]
    for html in (out["reg"], out["idp"]):
        assert html.count('class="terms-check"') == 2  # 問兩次也只插一次
        assert 'type="checkbox" name="age_ok"' in html and 'type="checkbox" name="terms_agree"' in html
        assert '<input type="hidden" name="terms_version" value="v9">' in html
        assert "我已滿 18 歲或已得到法定代理人同意" in html
        assert '《<a href="/terms" target="_blank" rel="noopener">使用條款</a>》' in html
        assert '《<a href="/privacy" target="_blank" rel="noopener">隱私權條款</a>》' in html
    assert out["login"] == "" and out["create"] == ""
    assert out["fetched"] == ["/api/terms/version"]  # 版號只問一次


def test_unticked_submit_is_blocked_with_the_line():
    out = _run()
    need = "請先勾選滿 18 歲與同意使用條款、隱私權條款，再送出。"
    assert out["blocked"] == [[1, 1, need], [1, 1, need]]  # 沒勾、只勾一個
    # 第 210 批起兩格都勾了的第一次送出也先攔下、重問版號再放行（test_submit_reasks_version_then_goes）；不寫「請先勾選」那一句
    assert out["passed"] == [1, 1, ""] and out["loginPassed"] == [0, 0, ""]


def test_submit_reasks_version_then_goes():
    fresh = _run()["fresh"]
    assert fresh["fetched"] == ["/api/terms/version", "/api/terms/version"]  # 插的時候一次、送出前重問一次
    assert fresh["events"] == [[1, 1], [0, 0]] and fresh["shell"] == ["v10"]  # 攔一次、帶新版號再送一次，app.js 那一支只收到一次
    assert fresh["msg"] == ""


def test_submit_reask_failure_keeps_old_version():
    down = _run()["freshDown"]
    assert down["events"] == [[1, 1], [0, 0]] and down["shell"] == ["v9"]  # 問不到：照舊版號放行一次，讓伺服器那一句擋；不無窮攔


def test_version_404_inserts_nothing():
    out = _run()
    assert out["gone"] == {"inserted": "", "fetched": ["/api/terms/version"], "passed": [0, 0, ""]}  # 關著：不插、不再問、照常送
    assert out["down"] == {"inserted": "", "fetched": ["/api/terms/version", "/api/terms/version"]}  # 斷線：下一次再問


def test_terms_js_marks_new_words():
    text = (WEB / "terms.js").read_text(encoding="utf-8")
    for line in text.splitlines():
        if any(s in line for s in ("我已滿 18 歲或已得到法定代理人同意\"", "我已讀過並同意", "請先勾選滿 18 歲")):
            assert "待 joy 潤" in line, line
