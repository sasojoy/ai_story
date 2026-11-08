/* 天下大勢的網頁前端：登入頁的格（帳號綁定，features/identity；帳號與客服第 201、202 批）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 * 載入時只做一件事：網址上有回呼帶回來的 ?auth=（ok／new／fail／cancel）就記下來、replaceState 拿掉查詢（別的查詢不碰）。
 * 殼的 renderGate 畫完登入頁叫 drawGateSlots；/api/me 沒帶 identity 旗標（S.identity，app.js enter 那一行設的）時這裡一個字都不動、
 * 也不問 /api/identity/gate：關著的登入頁跟沒有這一支一樣。開著時第一次被叫問一次 gate，照企劃者 11/08 挑的 C 版：
 * 分段「快速登入｜帳號登入｜註冊」，快速登入那一格放開著的那幾條路；上次選的那一格記在這台瀏覽器（讀不到就從快速登入開始）。
 * LINE、Google（第 202 批）：按了 POST /api/identity/start 拿對方的網址整頁過去；回來 auth=new 就切到建角色頁（殼的 renderCreate），
 * 表單改名 idp-create-form（殼的 submit 鏈不認它，這裡的 identityForm 認），送 /api/identity/character。
 * Email、手機還沒接（按了只說尚未開放）。畫法全在 identityGateHtml 與 identityCreateHtml，要換版只改它們。
 */
"use strict";

  const IDENTITY_MODE_KEY = "tx_gate_mode";
  const IDENTITY_MODES = ["quick", "login", "register"];
  const IDENTITY_SEG = [["quick", "快速登入"], ["login", "帳號登入"], ["register", "註冊"]]; // 待 joy 潤
  const IDENTITY_WAYS = { line: "用 LINE 繼續", google: "用 Google 繼續", email: "Email", phone: "手機" }; // 待 joy 潤
  const IDENTITY_THIRD = ["line", "google"];
  const IDENTITY_SOON = "尚未開放"; // 待 joy 潤
  const IDENTITY_FAIL = "登入沒有完成，請再試一次"; // 待 joy 潤
  const IDENTITY_CANCEL = "已取消登入"; // 待 joy 潤
  const IDENTITY_PRIVACY = "只拿 LINE、Google 給的使用者編號，不拿 Email 與個人資料。"; // 待 joy 潤
  const IDENTITY_PRIVACY_LINK = "隱私權說明"; // 待 joy 潤
  const IDENTITY_INAPP = "在 LINE 或其他 App 裡開的網頁不能用 Google 登入：請從右上角選「用瀏覽器開啟」。"; // 待 joy 潤
  const IDENTITY_STANDALONE = "從主畫面開的遊戲用 LINE、Google 登入時可能會跳到瀏覽器；回不來的話，直接在瀏覽器登入。"; // 待 joy 潤
  const IDENTITY_HAVE = "已經有帳號？用帳號密碼登入，再把這個綁上去"; // 待 joy 潤
  const IDENTITY_BACK = "用帳號密碼登入"; // 待 joy 潤
  const IDENTITY_AUTH_CODES = ["ok", "new", "fail", "cancel"];
  const IDENTITY_AUTH = identityReadAuth();

  // 回呼帶回來的 ?auth=<代碼>&via=<provider>：認得的代碼才記、才拿掉（拿掉 auth、via 兩個，別的查詢留著）
  function identityReadAuth() {
    try {
      const url = new URL(location.href);
      const code = url.searchParams.get("auth");
      if (!IDENTITY_AUTH_CODES.includes(code)) return null;
      const via = url.searchParams.get("via") || "";
      url.searchParams.delete("auth");
      url.searchParams.delete("via");
      history.replaceState(null, "", url.pathname + url.search + url.hash);
      return { code, via };
    } catch (e) {
      return null;
    }
  }

  function identityStoredMode() {
    try {
      const v = localStorage.getItem(IDENTITY_MODE_KEY);
      return IDENTITY_MODES.includes(v) ? v : "quick";
    } catch (e) {
      return "quick";
    }
  }

  function identityRemember(mode) {
    try { localStorage.setItem(IDENTITY_MODE_KEY, mode); } catch (e) { /* 私密視窗：這一次記著就好 */ }
  }

  // 這個頁面開在哪：LINE 裡（line）、別的 App 內建的網頁（inapp：FB、IG、Android WebView）、從主畫面開（standalone）、一般瀏覽器（browser）
  function identityEnv(ua, standalone) {
    const s = String(ua || "");
    if (/\bLine\//i.test(s)) return "line";
    if (/FBAN|FBAV|Instagram|; wv\)/.test(s)) return "inapp";
    return standalone ? "standalone" : "browser";
  }

  function identityEnvNow() {
    try {
      const standalone = (typeof matchMedia === "function" && matchMedia("(display-mode: standalone)").matches) || navigator.standalone === true;
      return identityEnv(navigator.userAgent, standalone);
    } catch (e) {
      return "browser";
    }
  }

  // 登入頁開著時的樣子（C 版）：html 是殼畫好的 .gate 裡面那一段，回改好的那一段。沒有路時原樣回去。
  // env 是 identityEnv 的結果：LINE 與別的 App 裡藏 Google 鈕（Google 不准在內建網頁登入）、多一行提示；從主畫面開的多一行提示
  function identityGateHtml(html, info, mode, env) {
    const inside = env === "line" || env === "inapp";
    const ways = (info.ways || []).filter((w) => IDENTITY_WAYS[w] && !(inside && w === "google"));
    if (!ways.length) return html;
    const seg = `<div class="seg">${IDENTITY_SEG.map(([m, label]) =>
      `<button class="${m === mode ? "on" : ""}" data-act="gate" data-mode="${m}">${label}</button>`).join("")}</div>`;
    const third = ways.some((w) => IDENTITY_THIRD.includes(w));
    const hint = inside ? IDENTITY_INAPP : env === "standalone" && third ? IDENTITY_STANDALONE : "";
    const buttons = `<div class="idp card">${ways.map((w) =>
      `<button class="btn idp-${w}" data-act="identity-way" data-way="${w}">${IDENTITY_WAYS[w]}</button>`).join("")}${
      third ? `<p class="idp-fine">${esc(IDENTITY_PRIVACY)}<a href="#">${esc(IDENTITY_PRIVACY_LINK)}</a></p>` : ""}${
      hint ? `<p class="idp-fine idp-hint">${esc(hint)}</p>` : ""}</div>`;
    const out = html.replace(/<div class="seg">[\s\S]*?<\/div>/, seg);
    return mode === "quick" ? out.replace(/<form id="gate-form"[\s\S]*?<\/form>/, buttons) : out;
  }

  // 建角色頁（auth=new）：html 是殼的 renderCreate 畫好的 .gate 裡面那一段。表單改名（殼的 submit 鏈不認，identityForm 認），
  // 底下多一行「已經有帳號？」與回登入頁帳號登入格的那一顆
  function identityCreateHtml(html) {
    return html.replace('<form id="create-form"', '<form id="idp-create-form"') +
      `<p class="idp-fine idp-have">${esc(IDENTITY_HAVE)}</p><button class="linkish" data-act="identity-back">${esc(IDENTITY_BACK)}</button>`;
  }

  function identityToCreate(via) {
    S.stage = "create";
    S.identityPending = via || "line";
    render();
    const box = $app.querySelector(".gate");
    if (box) box.innerHTML = identityCreateHtml(box.innerHTML);
  }

  function identityForget() {
    S.identityPending = null;
  }

  function identityGate(gate, S) {
    if (!gate || !S.identity) return;
    if (S.identityPending) identityForget(); // 回到登入頁（登出、回帳號登入）：pending 不再用（之後建角色走殼的表單）
    const auth = IDENTITY_AUTH && !IDENTITY_AUTH.used ? IDENTITY_AUTH : null;
    if (auth) {
      auth.used = true;
      if (auth.code === "new") { setTimeout(() => identityToCreate(auth.via), 0); return; } // 下一拍：renderGate 裡不遞迴 render
      if (auth.code === "fail") toast(IDENTITY_FAIL);
      if (auth.code === "cancel") toast(IDENTITY_CANCEL);
    }
    if (S.identityGate === undefined) {
      S.identityGate = null;
      fetch("/api/identity/gate").then((r) => (r.ok ? r.json() : null)).catch(() => null).then((info) => {
        if (!info) { S.identityGate = {}; return; }
        S.identityGate = info;
        if ((info.ways || []).length && !IDENTITY_MODES.includes(S.gateMode)) S.gateMode = identityStoredMode();
        if (S.stage === "gate") renderGate();
      });
      return;
    }
    const info = S.identityGate;
    if (!info || !(info.ways || []).length) return;
    const mode = IDENTITY_MODES.includes(S.gateMode) ? S.gateMode : "login";
    identityRemember(mode);
    const html = identityGateHtml(gate.innerHTML, info, mode, identityEnvNow());
    if (html !== gate.innerHTML) gate.innerHTML = html;
  }

  // 建角色（idp-create-form，只有 auth=new 進來的那一頁有）：送 /api/identity/character，成功才忘掉 pending；失敗由殼的 submit 鏈寫在表單上、可以再試
  async function identityForm(form, data) {
      if (form.id === "idp-create-form") {
        form.querySelector("[type=submit]").disabled = true;
        const r = await api("/api/identity/character", data);
        identityForget();
        enter(r);
      } // identityForm
  } // identityForm
  registerForms(identityForm, ["idp-create-form"]);

  async function identityStart(way) {
    const r = await api("/api/identity/start", { provider: way, purpose: "login" });
    if (r && r.url) location.href = r.url;
  }

  async function identityClick(act, el, ev) {
    switch (act) {
        case "identity-way":
          if (IDENTITY_THIRD.includes(el.dataset.way)) await identityStart(el.dataset.way);
          else toast(IDENTITY_SOON);
          break;
        case "identity-back": identityForget(); S.stage = "gate"; S.gateMode = "login"; render(); break;
    } // identityClick
  } // identityClick
  registerClicks(identityClick, ["identity-way", "identity-back"]);
  registerGateSlot(identityGate);
