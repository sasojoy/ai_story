/* 天下大勢的網頁前端：登入頁的格與設定抽屜的「帳號綁定」（帳號綁定，features/identity；帳號與客服第 201～204 批）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 * 載入時只做兩件事：網址上有回呼帶回來的 ?auth= 就記下來、replaceState 拿掉查詢（別的查詢不碰）；有 MutationObserver 的瀏覽器開始看設定抽屜。
 * 殼的 renderGate 畫完登入頁叫 drawGateSlots；/api/me 沒帶 identity 旗標（S.identity，app.js enter 那一行設的）時這裡一個字都不動、
 * 也不問 /api/identity/gate：關著的登入頁跟沒有這一支一樣。開著時第一次被叫問一次 gate，照企劃者 11/08 挑的 C 版：
 * 分段「快速登入｜帳號登入｜註冊」，快速登入那一格放開著的那幾條路；上次選的那一格記在這台瀏覽器（讀不到就從快速登入開始）。
 * LINE、Google（第 202 批）：按了 POST /api/identity/start 拿對方的網址整頁過去；回來 auth=new 就切到建角色頁（殼的 renderCreate），
 * 表單改名 idp-create-form（殼的 submit 鏈不認它，這裡的 identityForm 認），送 /api/identity/character。
 * Email、手機（第 204 批，登入頁 C 版的手機驗證碼流程）：按了在快速登入那一格換成驗證碼表單（identityCodeHtml：號碼、Turnstile、寄碼、
 * 60 秒重寄倒數、錯 5 次作廢的提示、輸碼）；已登入的瀏覽器先問一次要不要換帳號（伺服器回 {ask}）。
 * 設定抽屜（第 204 批，B 版）：app.js 不准碰，所以這裡用 MutationObserver 看到抽屜的「修改密碼」摺疊（#pw-form）就在它後面插一個
 * 「帳號綁定」摺疊（identityFoldHtml：摺著一行寫現況、紅點在摺疊列與 ⚙）；沒密碼的帳號把殼的「修改密碼」藏起來，改在這一格畫補設。
 * 資料：/api/main 的 identity 格（只給本人、開著才有；沒有這一格這裡一個字都不動），摺疊插進去時打一次 /api/identity/me。
 * 畫法全在 identityGateHtml、identityCreateHtml、identityCodeHtml、identityFoldHtml、identityAdminHtml，要換版只改它們。
 */
"use strict";

  const IDENTITY_MODE_KEY = "tx_gate_mode";
  const IDENTITY_MODES = ["quick", "login", "register"];
  const IDENTITY_SEG = [["quick", "快速登入"], ["login", "帳號登入"], ["register", "註冊"]]; // 待 joy 潤
  const IDENTITY_WAYS = { line: "用 LINE 繼續", google: "用 Google 繼續", email: "Email", phone: "手機" }; // 待 joy 潤
  const IDENTITY_THIRD = ["line", "google"];
  const IDENTITY_CODES = ["email", "phone"];
  const IDENTITY_FAIL = "登入沒有完成，請再試一次"; // 待 joy 潤
  const IDP_SWITCH_YES = "換這個帳號"; // 待 joy 潤
  const IDENTITY_CANCEL = "已取消登入"; // 待 joy 潤
  const IDENTITY_PRIVACY = "只拿 LINE、Google 給的使用者編號，不拿 Email 與個人資料。"; // 待 joy 潤
  const IDENTITY_PRIVACY_LINK = "隱私權說明"; // 待 joy 潤
  const IDENTITY_INAPP = "在 LINE 或其他 App 裡開的網頁不能用 Google 登入：請從右上角選「用瀏覽器開啟」。"; // 待 joy 潤
  const IDENTITY_STANDALONE = "從主畫面開的遊戲用 LINE、Google 登入時可能會跳到瀏覽器；回不來的話，直接在瀏覽器登入。"; // 待 joy 潤
  const IDENTITY_HAVE = "已經有帳號？用帳號密碼登入，再把這個綁上去"; // 待 joy 潤
  const IDENTITY_BACK = "用帳號密碼登入"; // 待 joy 潤
  // 第 209 批：identity 開著時全體密碼至少 n 字（n 是 /api/identity/gate 的 pw_min）：註冊格多一行、placeholder 換字
  const IDP_PW_MIN = (n) => `密碼至少 ${n} 字。`; // 待 joy 潤
  const IDP_PW_PLACEHOLDER = (n) => `至少 ${n} 字`; // 待 joy 潤
  // 第 204 批：綁定與重驗從第三方回來的四種（登入了才會碰到，toast 一句）
  const IDENTITY_BACK_TEXT = {
    bound: "綁好了。", // 待 joy 潤
    taken: "這個已綁定其他帳號。", // 待 joy 潤
    wait: "這個剛從別的帳號解綁，30 天內不能再拿來綁定或開新帳號。", // 待 joy 潤
    reauth: "驗證好了。", // 待 joy 潤
    held: "管理者剛幫這個帳號重設了密碼，72 小時內不能綁定新的登入方式。", // 待 joy 潤（第 209 批：同 binding.RESET_NO_BIND；72 = Config.identity.reset_hold_hours，同 wait 寫死 30）
  };
  const IDENTITY_AUTH_CODES = ["ok", "new", "fail", "cancel", "bound", "taken", "wait", "reauth", "held"];
  const IDENTITY_AUTH = identityReadAuth();
  // 驗證碼那一頁（第 204 批；每句待 joy 潤）
  const IDP_CODE_TITLE = { phone: "用手機驗證碼登入", email: "用 Email 驗證碼登入" }; // 待 joy 潤
  const IDP_CODE_BIND_TITLE = { phone: "綁手機", email: "綁 Email" }; // 待 joy 潤
  const IDP_CODE_REAUTH_TITLE = { phone: "用手機重新驗證", email: "用 Email 重新驗證" }; // 待 joy 潤
  const IDP_CODE_TO = { phone: "手機號碼（09 開頭十碼）", email: "Email" }; // 待 joy 潤
  const IDP_CODE_SEND = "寄驗證碼"; // 待 joy 潤
  const IDP_CODE_INPUT = "六位數驗證碼"; // 待 joy 潤
  const IDP_CODE_GO = "確認"; // 待 joy 潤
  const IDP_CODE_RESEND = "重寄驗證碼"; // 待 joy 潤
  const IDP_CODE_WAIT = (s) => `${s} 秒後可以重寄`; // 待 joy 潤
  const IDP_CODE_TRIES = "驗證碼錯 5 次就作廢，要重新取得；5 分鐘內有效。"; // 待 joy 潤
  const IDP_CODE_STAFF = "客服不會跟你要驗證碼，請勿告訴任何人。"; // 待 joy 潤
  const IDP_CODE_NOT_MINE = "這不是我的帳號"; // 待 joy 潤
  const IDP_CODE_BACK = "回上一步"; // 待 joy 潤
  const IDP_RESEND_SECONDS = 60; // = Config.identity.resend_seconds
  // 設定抽屜「帳號綁定」（B 版；每句待 joy 潤）
  const IDP_FOLD_TITLE = "帳號綁定"; // 待 joy 潤
  const IDP_RELOGIN = "管理與客服的功能要用帳號密碼重新登入才打得開（驗證碼、LINE、Google 登入的不行）。"; // 待 joy 潤（第 209 批）
  const IDP_KIND_NAMES = { password: "密碼", line: "LINE", google: "Google", email: "Email", phone: "手機" }; // 待 joy 潤
  const IDP_FOLD_LINE = (names) => `已綁：${names}`; // 待 joy 潤
  const IDP_FOLD_NO_PHONE = "・還沒綁手機"; // 待 joy 潤
  const IDP_LOADING = "讀取中……"; // 待 joy 潤
  const IDP_NEW_TAG = "新綁"; // 待 joy 潤
  const IDP_UNBIND = "解綁"; // 待 joy 潤
  const IDP_UNBIND_ASK = (name) => `確定要解綁${name}嗎？之後 30 天內不能把它綁到別的帳號。`; // 待 joy 潤
  const IDP_BIND = (name) => `綁${name}`; // 待 joy 潤
  const IDP_RECENT_NEED = "綁定、解綁、設密碼之前要先重新驗證一次。"; // 待 joy 潤
  const IDP_RECENT_LEFT = (m) => `已驗證，${m} 分鐘內可以改。`; // 待 joy 潤
  const IDP_REAUTH_PW = "打一次密碼"; // 待 joy 潤
  const IDP_REAUTH_GO = "重新驗證"; // 待 joy 潤
  const IDP_REAUTH_WITH = (name) => `用${name}重新驗證`; // 待 joy 潤
  const IDP_SETPW_TITLE = "補設密碼（設好之後也能用帳號密碼登入）"; // 待 joy 潤
  const IDP_SETPW_LOGIN = "帳號名（英文字母、數字、底線，3～20 字）"; // 待 joy 潤
  const IDP_SETPW_GO = "設密碼"; // 待 joy 潤
  const IDP_RESET_TITLE = "忘記密碼：設新密碼"; // 待 joy 潤
  const IDP_RESET_LEFT = (m) => `用綁定的方式登入了，${m} 分鐘內可以直接設新密碼（其他裝置會登出）。`; // 待 joy 潤
  const IDP_RESET_GO = "設新密碼"; // 待 joy 潤
  const IDP_PW_NEW = "新密碼"; // 待 joy 潤
  const IDP_PW_AGAIN = "再輸入一次新密碼"; // 待 joy 潤
  const IDP_HOLD = "保護期中：暫時不能設密碼或解綁。"; // 待 joy 潤
  const IDP_STAFF = "客服不會跟你要驗證碼或密碼。"; // 待 joy 潤
  // 管理頁重設密碼那一塊（選中帳號之後列綁定與時間；每句待 joy 潤）
  const IDP_ADMIN_TITLE = "這個帳號的登入方式"; // 待 joy 潤
  const IDP_ADMIN_FIRST = "開帳號時"; // 待 joy 潤
  const IDP_ADMIN_NEVER = "—"; // 待 joy 潤
  const IDP_ADMIN_LINE = (b, bound, seen) => `${b.name}：${b.shown}（綁定 ${bound}，上次驗證 ${seen}）`; // 待 joy 潤
  const IDP_ADMIN_UNBIND_ASK = (name) => `確定要幫他解綁${name}？`; // 待 joy 潤
  const IDP_ADMIN_DELETE = "刪帳號"; // 待 joy 潤
  const IDP_ADMIN_DELETE_ASK = "確定要刪這個帳號？名號仍被占住、錢包留著，不能復原。"; // 待 joy 潤

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
  // code（第 204 批）：按了 Email、手機之後的驗證碼表單（identityCodeHtml 畫好的），快速登入那一格換成它
  function identityGateHtml(html, info, mode, env, code) {
    const inside = env === "line" || env === "inapp";
    const ways = (info.ways || []).filter((w) => IDENTITY_WAYS[w] && !(inside && w === "google"));
    if (!ways.length) return html;
    const seg = `<div class="seg">${IDENTITY_SEG.map(([m, label]) =>
      `<button class="${m === mode ? "on" : ""}" data-act="gate" data-mode="${m}">${label}</button>`).join("")}</div>`;
    const third = ways.some((w) => IDENTITY_THIRD.includes(w));
    const hint = inside ? IDENTITY_INAPP : env === "standalone" && third ? IDENTITY_STANDALONE : "";
    const buttons = code || `<div class="idp card">${ways.map((w) =>
      `<button class="btn idp-${w}" data-act="identity-way" data-way="${w}">${IDENTITY_WAYS[w]}</button>`).join("")}${
      third ? `<p class="idp-fine">${esc(IDENTITY_PRIVACY)}<a href="#">${esc(IDENTITY_PRIVACY_LINK)}</a></p>` : ""}${
      hint ? `<p class="idp-fine idp-hint">${esc(hint)}</p>` : ""}</div>`;
    const out = html.replace(/<div class="seg">[\s\S]*?<\/div>/, seg);
    return mode === "quick" ? out.replace(/<form id="gate-form"[\s\S]*?<\/form>/, buttons) : out;
  }

  // 第 209 批：註冊格的密碼提示（gate-form 裡的 placeholder 換成 n 字、表單訊息那一行前面插一行）；n 沒有（關著）或已經插過原樣回
  function identityPwHint(html, n) {
    if (!n || html.includes("idp-pw-min")) return html;
    return html.replace(/<form id="gate-form"[\s\S]*?<\/form>/, (form) => form
      .replace('placeholder="至少 6 字"', `placeholder="${esc(IDP_PW_PLACEHOLDER(n))}"`)
      .replace('<p class="form-msg"', `<p class="idp-fine idp-pw-min">${esc(IDP_PW_MIN(n))}</p><p class="form-msg"`));
  }

  // 驗證碼表單（第 204 批）：st = {way, purpose, sent, to, until, notice, stale}；now 是毫秒。寄碼前：號碼、Turnstile（有網站金鑰才有那一格）、寄碼；
  // 寄出後：輸碼、錯 5 次作廢的提示、重寄倒數；門號過期（stale）多一顆「這不是我的帳號」。登入、綁定、重驗三種用途共用，只換標題
  function identityCodeHtml(st, siteKey, now) {
    const way = st.way;
    const title = (st.purpose === "bind" ? IDP_CODE_BIND_TITLE : st.purpose === "reauth" ? IDP_CODE_REAUTH_TITLE : IDP_CODE_TITLE)[way];
    const left = Math.max(0, Math.ceil(((st.until || 0) - now) / 1000));
    const body = !st.sent
      ? `<label class="field"><span>${esc(IDP_CODE_TO[way])}</span><input class="input" name="to" value="${esc(st.to || "")}" ${
          way === "phone" ? 'inputmode="tel" autocomplete="tel"' : 'type="email" autocomplete="email"'}></label>${
          siteKey ? `<div class="cf-turnstile" data-sitekey="${esc(siteKey)}" data-action="identity_code"></div>` : ""}
        <input type="hidden" name="phase" value="send"><button class="btn" type="submit">${esc(IDP_CODE_SEND)}</button>`
      : `${st.notice ? `<p class="idp-fine">${esc(st.notice)}</p>` : ""}
        <label class="field"><span>${esc(IDP_CODE_INPUT)}</span><input class="input" name="code" inputmode="numeric" maxlength="6" autocomplete="one-time-code"></label>
        <p class="idp-fine idp-tries">${esc(IDP_CODE_TRIES)}</p>
        <input type="hidden" name="phase" value="verify"><button class="btn" type="submit">${esc(IDP_CODE_GO)}</button>
        <button class="linkish idp-resend" type="button" data-act="identity-code-resend"${left > 0 ? " disabled" : ""}>${
          esc(left > 0 ? IDP_CODE_WAIT(left) : IDP_CODE_RESEND)}</button>`;
    const stale = st.stale ? `<p class="form-msg">${esc(st.stale)}</p>
      <button class="btn small ghost" type="button" data-act="identity-not-mine">${esc(IDP_CODE_NOT_MINE)}</button>` : "";
    return `<form class="idp-code card" id="idp-code-form" data-way="${esc(way)}"><p class="idp-code-title">${esc(title)}</p>${body}
      <p class="form-msg" role="alert"></p>${stale}<p class="idp-fine">${esc(IDP_CODE_STAFF)}</p>
      <button class="linkish" type="button" data-act="identity-code-back">${esc(IDP_CODE_BACK)}</button></form>`;
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
    if (!info) return;
    if (!(info.ways || []).length) { // 沒有別的路：殼的兩格照舊，註冊格照樣補 12 字那一行（第 209 批）
      const hinted = S.gateMode === "register" ? identityPwHint(gate.innerHTML, info.pw_min) : gate.innerHTML;
      if (hinted !== gate.innerHTML) gate.innerHTML = hinted;
      return;
    }
    const mode = IDENTITY_MODES.includes(S.gateMode) ? S.gateMode : "login";
    identityRemember(mode);
    const code = mode === "quick" && S.identityCode ? identityCodeHtml(S.identityCode, info.turnstile, Date.now()) : "";
    const drawn = identityGateHtml(gate.innerHTML, info, mode, identityEnvNow(), code);
    const html = mode === "register" ? identityPwHint(drawn, info.pw_min) : drawn;
    if (html !== gate.innerHTML) gate.innerHTML = html;
    if (code) identityTurnstile(info.turnstile);
  }

  // Turnstile（有網站金鑰才載；第 204 批）：script 載一次，之後新畫出來的空格各 render 一次
  function identityTurnstile(siteKey) {
    if (!siteKey || typeof document === "undefined") return;
    const draw = () => { for (const el of document.querySelectorAll(".cf-turnstile:empty")) window.turnstile.render(el); };
    if (window.turnstile) { draw(); return; }
    if (document.getElementById("idp-turnstile")) return;
    const s = document.createElement("script");
    s.id = "idp-turnstile";
    s.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
    s.async = true;
    s.onload = draw;
    document.head.appendChild(s);
  }

  // 已登入的瀏覽器再走登入：伺服器回 {ask}，用網頁自己的確認框（app.js 的 ask）問一次，要換才帶 switch: true 再送一次、回覆交給 then；
  // 按取消就停在這裡（什麼都不送、then 不叫）
  async function identityAsked(path, body, then) {
    const r = await api(path, body);
    if (!(r && r.ask)) return then(r);
    return ask(r.ask, IDP_SWITCH_YES, async () => then(await api(path, { ...body, switch: true })));
  }

  function identityCodeState() {
    return S.identityCode || (S.idp && S.idp.code) || null;
  }

  function identityCodeRedraw() {
    if (S.identityCode) renderGate();
    else identityFoldRedraw();
  }

  // 重寄倒數：每秒只改那一顆鈕的字（不重畫表單，打到一半的號碼、碼都留著）
  let identityTimer = 0;
  function identityTick() {
    clearInterval(identityTimer);
    if (typeof document === "undefined") return; // 沒有畫面（node 的測試）：不數
    identityTimer = setInterval(() => {
      const st = identityCodeState();
      const left = st ? Math.max(0, Math.ceil(((st.until || 0) - Date.now()) / 1000)) : 0;
      const btn = typeof document !== "undefined" ? document.querySelector('[data-act="identity-code-resend"]') : null;
      if (btn) { btn.disabled = left > 0; btn.textContent = left > 0 ? IDP_CODE_WAIT(left) : IDP_CODE_RESEND; }
      if (!st || left <= 0) clearInterval(identityTimer);
    }, 1000);
  }

  async function identityCodeSend(st, to, token) {
    const body = { channel: st.way, to, turnstile: token || "", purpose: st.purpose };
    const sent = (r) => {
      if (!r) return;
      Object.assign(st, { sent: true, to, notice: r.message || "", until: Date.now() + IDP_RESEND_SECONDS * 1000, stale: "" });
      identityCodeRedraw();
      identityTick();
    };
    if (st.purpose === "login") return identityAsked("/api/identity/code/send", body, sent);
    sent(await api("/api/identity/code/send", body));
  }

  async function identityCodeVerify(st, code) {
    const r = await api("/api/identity/code/verify", { code });
    if (r && r.stale) { st.stale = r.message; identityCodeRedraw(); return; }
    if (st.purpose !== "login") { // 綁定、重驗：回抽屜那一格、重抓一次
      if (r && r.message) toast(r.message);
      S.idp.code = null;
      await identityLoadMe();
      return;
    }
    S.identityCode = null;
    if (r && r.stage === "create" && r.pending) { identityToCreate(st.way); return; }
    enter(r);
  }

  // 表單：建角色（idp-create-form，只有 auth=new 進來的那一頁有）送 /api/identity/character，成功才忘掉 pending；失敗由殼的 submit 鏈寫在表單上、可以再試。
  // 第 204 批：驗證碼（idp-code-form）、重驗（idp-reauth-form）、補設密碼（idp-setpw-form）、忘記密碼（idp-reset-form）
  async function identityForm(form, data) {
      if (form.id === "idp-create-form") {
        form.querySelector("[type=submit]").disabled = true;
        const r = await api("/api/identity/character", data);
        identityForget();
        enter(r);
      } else if (form.id === "idp-code-form") {
        const st = identityCodeState();
        if (!st) return;
        if (data.phase === "send") await identityCodeSend(st, String(data.to || "").trim(), data["cf-turnstile-response"]);
        else await identityCodeVerify(st, String(data.code || "").trim());
      } else if (form.id === "idp-reauth-form") {
        const r = await api("/api/identity/reauth", { password: data.password || "" });
        if (r && r.message) toast(r.message);
        await identityLoadMe();
      } else if (form.id === "idp-setpw-form") {
        await identityPassword("/api/identity/password/set", data, true);
      } else if (form.id === "idp-reset-form") {
        await identityPassword("/api/identity/password/reset", data, false);
      } // identityForm
  } // identityForm
  registerForms(identityForm, ["idp-create-form", "idp-code-form", "idp-reauth-form", "idp-setpw-form", "idp-reset-form"]);

  // 補設密碼（made：之後這個帳號就有密碼了）與忘記密碼：送出、說一句、重抓
  async function identityPassword(path, data, made) {
    const r = await api(path, data);
    if (r && r.message) toast(r.message);
    if (made && S.main && S.main.identity) S.main.identity.has_password = true;
    await identityLoadMe();
  }

  async function identityStart(way, purpose = "login") {
    const body = { provider: way, purpose };
    const go = (r) => { if (r && r.url) location.href = r.url; };
    if (purpose === "login") return identityAsked("/api/identity/start", body, go);
    go(await api("/api/identity/start", body));
  }

  // ── 設定抽屜「帳號綁定」（B 版）──

  function identityNames(kinds) {
    return (kinds || []).map((k) => IDP_KIND_NAMES[k] || k).join("、");
  }

  // info 是 /api/main 的 identity 格 {kinds, has_password, phone_missing}；st 是 S.idp {me, code, open}；now 是毫秒
  function identityFoldHtml(info, st, now) {
    const dot = info.phone_missing ? '<span class="idp-dot" aria-hidden="true"></span>' : "";
    const line = IDP_FOLD_LINE(identityNames(info.kinds)) + (info.phone_missing ? IDP_FOLD_NO_PHONE : "");
    const me = st.me;
    let body = `<p class="muted">${esc(IDP_LOADING)}</p>`;
    if (me) {
      const rows = me.kinds.map((k) => `<div class="row idp-row"><span class="idp-kind">${esc(k.name)}</span><span class="idp-shown">${esc(k.shown || "")}</span>${
        k.new ? `<span class="tag">${esc(IDP_NEW_TAG)}</span>` : ""}${
        k.can_unbind ? `<button class="btn small ghost" type="button" data-act="identity-unbind" data-way="${esc(k.provider)}">${esc(IDP_UNBIND)}</button>` : ""}</div>`).join("");
      const binds = me.ways.length ? `<div class="row wrap">${me.ways.map((w) =>
        `<button class="btn small" type="button" data-act="identity-bind" data-way="${esc(w)}">${esc(IDP_BIND(IDP_KIND_NAMES[w] || w))}</button>`).join("")}</div>` : "";
      const others = me.kinds.filter((k) => k.provider !== "password");
      const recheck = me.recent > 0
        ? `<p class="idp-fine">${esc(IDP_RECENT_LEFT(Math.max(1, Math.ceil(me.recent / 60))))}</p>`
        : `<p class="idp-fine">${esc(IDP_RECENT_NEED)}</p>${me.has_password
          ? `<form class="row" id="idp-reauth-form"><input class="input" type="password" name="password" placeholder="${esc(IDP_REAUTH_PW)}" aria-label="${esc(IDP_REAUTH_PW)}" autocomplete="current-password"><button class="btn small" type="submit">${esc(IDP_REAUTH_GO)}</button></form>`
          : `<div class="row wrap">${others.map((k) => `<button class="btn small ghost" type="button" data-act="identity-reauth" data-way="${esc(k.provider)}">${esc(IDP_REAUTH_WITH(k.name))}</button>`).join("")}</div>`}`;
      const pwFields = `<label class="field"><span>${esc(IDP_PW_NEW)}</span><input class="input" type="password" name="new" autocomplete="new-password"></label>
          <label class="field"><span>${esc(IDP_PW_AGAIN)}</span><input class="input" type="password" name="again" autocomplete="new-password"></label>`;
      const setpw = me.has_password ? "" : `<form class="stack idp-setpw" id="idp-setpw-form"><p class="label">${esc(IDP_SETPW_TITLE)}</p>
          <label class="field"><span>${esc(IDP_SETPW_LOGIN)}</span><input class="input" name="login" autocomplete="username"></label>${pwFields}
          <p class="form-msg" role="alert"></p><button class="btn" type="submit">${esc(IDP_SETPW_GO)}</button></form>`;
      const reset = me.has_password && me.reset > 0 ? `<form class="stack idp-reset" id="idp-reset-form"><p class="label">${esc(IDP_RESET_TITLE)}</p>
          <p class="idp-fine">${esc(IDP_RESET_LEFT(Math.max(1, Math.ceil(me.reset / 60))))}</p>${pwFields}
          <p class="form-msg" role="alert"></p><button class="btn" type="submit">${esc(IDP_RESET_GO)}</button></form>` : "";
      const code = st.code ? identityCodeHtml(st.code, me.turnstile, now) : "";
      body = `${rows}${binds}${me.hold ? `<p class="form-msg">${esc(IDP_HOLD)}</p>` : ""}${recheck}${code}${reset}${setpw}<p class="idp-fine">${esc(IDP_STAFF)}</p>`;
    }
    return `<details class="fold idp-fold"${st.open ? " open" : ""}><summary>${esc(IDP_FOLD_TITLE)}${dot}<span class="idp-line">${esc(line)}</span></summary><div class="fold-body">${body}</div></details>`;
  }

  async function identityLoadMe() {
    S.idp = S.idp || {};
    try { S.idp.me = await api("/api/identity/me"); } catch (e) { return; }
    identityMeToMain(S.idp.me);
    identitySyncDot();
    identityFoldRedraw();
  }

  // 第 208 批：綁、解綁之後不重新載入就更新 ⚙ 的紅點與摺疊列——/api/identity/me 回來的照抄進 /api/main 的 identity 格（kinds、has_password、phone_missing）
  function identityMeToMain(me) {
    const info = S.main && S.main.identity;
    if (!info || !me || !Array.isArray(me.kinds)) return;
    info.kinds = me.kinds.map((k) => k.provider);
    info.has_password = !!me.has_password;
    if (typeof me.phone_missing === "boolean") info.phone_missing = me.phone_missing;
  }

  // ⚙（data-act="sheet"）的紅點照 S.main.identity.phone_missing：該有沒有就補、不該有有就拿掉
  function identitySyncDot() {
    const info = S.main && S.main.identity;
    if (!info || typeof document === "undefined") return;
    for (const b of document.querySelectorAll('[data-act="sheet"]')) {
      const dot = b.querySelector(".idp-dot");
      if (info.phone_missing && !dot) b.insertAdjacentHTML("beforeend", '<span class="idp-dot" aria-hidden="true"></span>');
      else if (!info.phone_missing && dot) dot.remove();
    }
  }

  // 第 208 批：管理頁「現在」那幾格（.ad-tiles）後面插全服池上限的通知（/api/admin 的 identity_alerts；關著、沒有通知就沒有這個鍵）
  function identityAlertHtml(lines) {
    return lines.map((t) => `<p class="muted idp-alert">${esc(t)}</p>`).join("");
  }
  function identityAlerts() {
    const lines = S.admin && S.admin.identity_alerts;
    if (!Array.isArray(lines) || !lines.length || typeof document === "undefined") return;
    const tiles = document.querySelector(".ad-tiles");
    if (!tiles || document.querySelector(".idp-alert")) return;
    tiles.insertAdjacentHTML("afterend", identityAlertHtml(lines));
  }

  // 管理頁解綁、刪帳號做完：照剛才那一列再找一次，放回 S.adPicked（刪掉了就是 null），畫面不必再按一次「找」
  async function identityAdminRefind(row) {
    if (!row) return;
    const want = row.key || row.login;
    let found = null;
    for (const q of [row.login, row.character].filter(Boolean)) {
      const r = await api("/api/identity/admin/accounts", { q });
      found = ((r && r.rows) || []).find((x) => (x.key || x.login) === want) || null;
      if (found) break;
    }
    S.adPicked = found;
    renderKeepingSheet();
  }

  function identityFoldRedraw() {
    if (typeof document === "undefined" || !S.main || !S.main.identity) return;
    const el = document.querySelector(".idp-fold");
    if (!el) return;
    S.idp = S.idp || {};
    S.idp.open = el.open;
    el.outerHTML = identityFoldHtml(S.main.identity, S.idp, Date.now());
    if (S.idp.code && S.idp.me) identityTurnstile(S.idp.me.turnstile);
  }

  // 抽屜每畫一次（殼的 render 整塊換掉）：插「帳號綁定」那一格、⚙ 的紅點；沒有 identity 格（關著、沒帳號）什麼都不做
  function identityDecorate() {
    identityAlerts();
    const info = S.main && S.main.identity;
    if (!info) return;
    identitySyncDot();
    const pw = document.getElementById("pw-form");
    const fold = pw && pw.closest("details");
    if (!fold || !fold.parentElement || fold.parentElement.querySelector(".idp-fold")) return;
    if (!info.has_password) fold.hidden = true; // 沒密碼的帳號：殼的「修改密碼」藏起來，補設在這一格
    S.idp = S.idp || {};
    fold.insertAdjacentHTML("afterend", identityFoldHtml(info, S.idp, Date.now()));
    identityLoadMe();
    if (!S.main.admin) identityRelogin(); // 已經是管理者（夠格）不問
  }

  // 第 209 批「請用密碼重新登入」：名單上、這次登入不夠格的本人，「帳號綁定」上方多一行（/api/identity/session 的 relogin）；假、404 不畫
  function identityReloginHtml() {
    return `<p class="form-msg idp-relogin">${esc(IDP_RELOGIN)}</p>`;
  }
  async function identityRelogin() {
    let got = null;
    try { got = await api("/api/identity/session"); } catch (e) { return; }
    if (!got || got.relogin !== true || typeof document === "undefined") return;
    const el = document.querySelector(".idp-fold");
    if (!el || document.querySelector(".idp-relogin")) return;
    el.insertAdjacentHTML("beforebegin", identityReloginHtml());
  }

  function identityWatch() {
    if (typeof MutationObserver !== "function" || typeof document === "undefined" || !document.body) return;
    new MutationObserver(identityDecorate).observe(document.body, { childList: true, subtree: true });
  }

  // ── 管理頁重設密碼那一塊（admin.js 選中帳號之後叫；identity 關著時 S.adPicked 沒有 binds，回空字串）──
  function identityAdminHtml() {
    const row = S.adPicked;
    if (!S.main || !S.main.identity || !row || !Array.isArray(row.binds) || (row.key || row.login) !== S.adResetTarget) return "";
    const when = (t, empty) => (t == null ? empty : new Date(t * 1000).toLocaleString("zh-TW", { hour12: false }));
    return `<div class="card idp-admin"><p class="label">${esc(IDP_ADMIN_TITLE)}</p>${row.binds.map((b) =>
      `<div class="row idp-row"><span>${esc(IDP_ADMIN_LINE(b, when(b.bound_at, IDP_ADMIN_FIRST), when(b.verified_at, IDP_ADMIN_NEVER)))}</span>${
        b.provider !== "password" ? `<button class="btn small ghost" type="button" data-act="identity-admin-unbind" data-way="${esc(b.provider)}" data-name="${esc(b.name)}">${esc(IDP_UNBIND)}</button>` : ""}</div>`).join("")}
      <button class="btn small danger" type="button" data-act="identity-admin-delete">${esc(IDP_ADMIN_DELETE)}</button></div>`;
  }

  async function identityClick(act, el, ev) {
    switch (act) {
        case "identity-way":
          if (IDENTITY_THIRD.includes(el.dataset.way)) await identityStart(el.dataset.way);
          else if (IDENTITY_CODES.includes(el.dataset.way)) { S.identityCode = { way: el.dataset.way, purpose: "login" }; renderGate(); }
          break;
        case "identity-back": identityForget(); S.stage = "gate"; S.gateMode = "login"; render(); break;
        case "identity-code-back":
          if (S.identityCode) { S.identityCode = null; renderGate(); } else if (S.idp) { S.idp.code = null; identityFoldRedraw(); }
          break;
        case "identity-code-resend": {
          const st = identityCodeState();
          if (st) { st.sent = false; identityCodeRedraw(); }
          break;
        }
        case "identity-not-mine": {
          const st = identityCodeState();
          const r = await api("/api/identity/code/release", {});
          if (r && r.message) toast(r.message);
          S.identityCode = null;
          identityToCreate(st ? st.way : "phone");
          break;
        }
        case "identity-bind":
        case "identity-reauth": {
          const way = el.dataset.way;
          const purpose = act === "identity-bind" ? "bind" : "reauth";
          if (IDENTITY_THIRD.includes(way)) await identityStart(way, purpose);
          else { S.idp = S.idp || {}; S.idp.code = { way, purpose }; identityFoldRedraw(); }
          break;
        }
        case "identity-unbind": {
          const way = el.dataset.way;
          ask(IDP_UNBIND_ASK(IDP_KIND_NAMES[way] || way), IDP_UNBIND, async () => {
            const r = await api("/api/identity/unbind", { provider: way });
            if (r && r.message) toast(r.message);
            if (S.main && S.main.identity) S.main.identity.kinds = (S.main.identity.kinds || []).filter((k) => k !== way);
            await identityLoadMe();
          });
          break;
        }
        case "identity-admin-unbind":
          ask(IDP_ADMIN_UNBIND_ASK(el.dataset.name || el.dataset.way), IDP_UNBIND, async () => {
            const picked = S.adPicked;
            S.adPicked = null; // 做完那一列的綁定就舊了：做完照那一列再找一次（第 208 批）
            await adminDo("identity_unbind", { target: S.adResetTarget, provider: el.dataset.way }, IDP_UNBIND);
            await identityAdminRefind(picked);
          });
          break;
        case "identity-admin-delete":
          ask(IDP_ADMIN_DELETE_ASK, IDP_ADMIN_DELETE, async () => {
            const picked = S.adPicked;
            S.adPicked = null;
            await adminDo("identity_delete", { target: S.adResetTarget }, IDP_ADMIN_DELETE);
            await identityAdminRefind(picked);
          });
          break;
    } // identityClick
  } // identityClick
  registerClicks(identityClick, ["identity-way", "identity-back", "identity-code-back", "identity-code-resend", "identity-not-mine", "identity-bind", "identity-reauth", "identity-unbind", "identity-admin-unbind", "identity-admin-delete"]);
  registerGateSlot(identityGate);
  identityWatch();
  // 綁定與重驗從第三方回來（登入著，不會畫登入頁）：下一拍 toast 一句（toast 在 app.js，比這一支晚載）
  if (IDENTITY_AUTH && IDENTITY_BACK_TEXT[IDENTITY_AUTH.code]) {
    setTimeout(() => { IDENTITY_AUTH.used = true; if (typeof toast === "function") toast(IDENTITY_BACK_TEXT[IDENTITY_AUTH.code]); }, 0);
  }
