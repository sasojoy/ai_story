/* 天下大勢的網頁前端：使用條款與隱私權（功能包 tianxia/features/terms/）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 * 不改 app.js：看 #app 畫了什麼（MutationObserver）——登入頁、設定頁底下補兩個連結；進了遊戲問一次 /api/terms，
 * 要按同意就疊一層在最上面（沒同意過任何一版：按了同意才關得掉；改版的考慮期內：可以先關掉）。字待 joy 潤
 * 換版後同意過舊版的預設是考慮期（ask）；Config.terms.update_must 開著（第 243 批的開關，第 246 批預設關）才是按了同意才關得掉（must 帶 update：開頭換改版那一句、同意記 update）。
 */
"use strict";

  const TERMS_LINKS = '<p class="terms-links"><a href="/terms" target="_blank" rel="noopener">使用條款</a>・<a href="/privacy" target="_blank" rel="noopener">隱私權條款</a></p>';
  const TERMS_SAY = {
    must: "開始之前，請先看過並同意天下大勢的使用條款與隱私權條款。",
    ask: "使用條款與隱私權條款有新版。{deadline} 以前沒有表示反對，就視為接受新版。",
    update: "使用條款與隱私權條款有新版，請看過這次改了什麼，同意後繼續。", // 待 joy 潤（第 243 批：同意過舊版、換版後要按同意的 must）
    points: "重點：",
    agree: "我已滿 18 歲或已得到法定代理人同意，並同意以上條款",
    later: "稍後再看",
    no: "我不同意",
    noMust: "不同意的話沒辦法進遊戲。要終止帳號、退還沒用掉的元寶，請寫信到 {email}。",
    noAsk: "不同意新版的話，可以終止帳號並退還沒用掉的元寶，請寫信到 {email}。",
    logout: "登出",
    // 第 206 批：註冊頁與建角色頁的兩個勾選（拆自上面 agree 那一句）與沒勾就送出時表單下面那一句（同伺服器 terms_base.REGISTER_NEED）
    age: "我已滿 18 歲或已得到法定代理人同意", // 待 joy 潤
    read: "我已讀過並同意《使用條款》與《隱私權條款》", // 待 joy 潤
    need: "請先勾選滿 18 歲與同意使用條款、隱私權條款，再送出。", // 待 joy 潤
  };
  let termsAsked = false; // 這一次登入問過 /api/terms 了（登出、回到登入頁就重來）
  let termsBusy = false;
  // 第 255 批：分頁開著的時候才變成「必須同意」的人（新版條款部署時沒關分頁、update_must 被打開、同意紀錄不見），伺服器擋下的那一句
  // （terms_base.GATE_NEED）殼 api() 跳成吐司；看 #toast，字裡有「條款」、人在遊戲裡、同意層沒開，就重問一次 /api/terms。
  // 連著跳的吐司隔 5 秒才再問（不連打）；斷線照 termsCheck 舊寫法下一次再問。靠「條款」兩個字認，包的測試守 GATE_NEED 留著這兩個字
  const TERMS_REASK_GAP_MS = 5000;
  let termsReaskAt = 0; // 上一次因吐司重問的時刻

  // ── 第 206 批：註冊的兩個勾選 ──
  // 插在註冊模式的 #gate-form（有「再輸入一次密碼」那一格才是註冊）與 identity 建角色那一張（#idp-create-form）的 .form-msg 前面；
  // 殼自己的 #create-form（密碼帳號註冊完才建角色，帳號已經開了）不插。版號問 /api/terms/version：非 200（關著 404、伺服器沒這一包）
  // 這一頁不再問、不插；斷線下一次重畫再問。送出時（capture，先於 app.js 那一支）沒全勾就擋下、寫那一句。畫法集中在 termsChecksHtml。
  let termsVersionAsk = null; // Promise：版號字串，或 null（不問）

  function termsChecksHtml(version) {
    const read = termsEsc(TERMS_SAY.read)
      .replace("《使用條款》", '《<a href="/terms" target="_blank" rel="noopener">使用條款</a>》')
      .replace("《隱私權條款》", '《<a href="/privacy" target="_blank" rel="noopener">隱私權條款</a>》');
    return `<label class="terms-check"><input type="checkbox" name="age_ok"><span>${termsEsc(TERMS_SAY.age)}</span></label>` +
      `<label class="terms-check"><input type="checkbox" name="terms_agree"><span>${read}</span></label>` +
      `<input type="hidden" name="terms_version" value="${termsEsc(version)}">`;
  }

  function termsWantsChecks(form) {
    if (!form) return false;
    if (form.id === "idp-create-form") return true;
    return form.id === "gate-form" && !!form.querySelector('[name="again"]');
  }

  function termsVersion() {
    if (!termsVersionAsk) {
      termsVersionAsk = fetch("/api/terms/version", { credentials: "same-origin" })
        .then((res) => (res.ok ? res.json().then((d) => (d && d.version) || null) : null))
        .catch(() => { termsVersionAsk = null; return null; }); // 斷線：下一次再問
    }
    return termsVersionAsk;
  }

  async function termsInsertChecks() {
    const forms = [...document.querySelectorAll("#gate-form, #idp-create-form")].filter((f) => termsWantsChecks(f) && !f.querySelector(".terms-check"));
    if (!forms.length) return;
    const version = await termsVersion();
    if (!version) return;
    for (const form of forms) {
      if (form.isConnected === false || form.querySelector(".terms-check")) continue;
      const msg = form.querySelector(".form-msg");
      if (msg) msg.insertAdjacentHTML("beforebegin", termsChecksHtml(version));
      else form.insertAdjacentHTML("beforeend", termsChecksHtml(version));
    }
  }

  function termsBlockSubmit(ev) {
    const form = ev.target;
    if (!form || !form.querySelector || !form.querySelector(".terms-check")) return; // 沒插勾選的表單一律放行
    const boxes = [...form.querySelectorAll('.terms-check input[type="checkbox"]')];
    if (boxes.length && boxes.every((b) => b.checked)) {
      if (termsFresh.has(form)) { termsFresh.delete(form); return; } // 重問過版號的那一次：放行
      ev.preventDefault();
      ev.stopImmediatePropagation();
      termsResend(form);
      return;
    }
    ev.preventDefault();
    ev.stopImmediatePropagation();
    const msg = form.querySelector(".form-msg");
    if (msg) msg.textContent = TERMS_SAY.need;
  }

  // 第 210 批：版號快取一整頁，條款改版後沒重新整理的註冊頁會帶舊版號、被伺服器同一句擋住、重勾也沒用。所以兩格都勾了的那一次
  // 先攔下、重問 /api/terms/version（不經快取；問到的也寫回快取）、換掉 hidden 的版號，再送一次（記在 termsFresh，下一次放行、不無窮攔）。
  // 問不到（斷線、非 200）照舊版號送，讓伺服器那一句擋
  const termsFresh = new WeakSet();
  async function termsResend(form) {
    let version = null;
    try {
      const res = await fetch("/api/terms/version", { credentials: "same-origin" });
      version = res.ok ? ((await res.json()) || {}).version || null : null;
    } catch (e) { version = null; }
    if (version) {
      termsVersionAsk = Promise.resolve(version);
      const hidden = form.querySelector('[name="terms_version"]');
      if (hidden) hidden.value = version;
    }
    if (form.isConnected === false) return;
    termsFresh.add(form);
    if (typeof form.requestSubmit === "function") form.requestSubmit();
    else if (typeof form.dispatchEvent === "function") form.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
    else termsFresh.delete(form);
  }

  function termsEsc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function termsAddLinks() {
    for (const box of document.querySelectorAll('.gate, .sheet[aria-label="設定"]')) {
      if (!box.querySelector(".terms-links")) box.insertAdjacentHTML("beforeend", TERMS_LINKS);
    }
  }

  function termsLayerHtml(t) {
    const must = t.need === "must";
    const lead = must ? (t.update ? TERMS_SAY.update : TERMS_SAY.must) : TERMS_SAY.ask.replace("{deadline}", termsEsc(t.deadline || ""));
    const points = (t.summary || []).map((line) => `<li>${termsEsc(line)}</li>`).join("");
    return `<div class="terms-layer" role="dialog" aria-modal="true" aria-label="使用條款與隱私權條款">
      <div class="terms-card card">
        <h3>使用條款與隱私權條款</h3>
        <p>${lead}</p>
        ${points ? `<p class="muted">${TERMS_SAY.points}</p><ul>${points}</ul>` : ""}
        ${TERMS_LINKS}
        <p class="form-msg" role="alert"></p>
        <button class="btn primary" data-terms="agree">${TERMS_SAY.agree}</button>
        <div class="terms-row">
          ${must ? "" : `<button class="btn ghost" data-terms="later">${TERMS_SAY.later}</button>`}
          <button class="btn ghost" data-terms="no">${TERMS_SAY.no}</button>
        </div>
        <p class="terms-no muted" hidden>${(must ? TERMS_SAY.noMust : TERMS_SAY.noAsk).replace("{email}", termsEsc(t.email))}</p>
        ${must ? `<button class="btn ghost terms-out" data-act="logout" hidden>${TERMS_SAY.logout}</button>` : ""}
      </div></div>`;
  }

  // 同意記哪一種（稽核分得出改版時同意的）：第一次是 gate；換版後的 must（帶 update）與考慮期的 ask 是 update（第 243 批）
  function termsSource(t) {
    return t.need === "must" && !t.update ? "gate" : "update";
  }

  function termsClose() {
    const el = document.querySelector(".terms-layer");
    if (el) el.remove();
  }

  function termsShow(t) {
    termsClose();
    if (!t || !t.need) return;
    document.body.insertAdjacentHTML("beforeend", termsLayerHtml(t));
    const layer = document.querySelector(".terms-layer");
    layer.addEventListener("click", async (ev) => {
      const btn = ev.target.closest("[data-terms]");
      if (!btn) { if (ev.target.closest('[data-act="logout"]')) termsClose(); return; }
      const what = btn.dataset.terms;
      if (what === "later") return termsClose();
      if (what === "no") {
        layer.querySelector(".terms-no").hidden = false;
        const out = layer.querySelector(".terms-out");
        if (out) out.hidden = false;
        return;
      }
      if (termsBusy) return;
      termsBusy = true;
      btn.disabled = true;
      try {
        const res = await fetch("/api/terms/agree", {
          method: "POST", headers: { "Content-Type": "application/json" }, credentials: "same-origin",
          body: JSON.stringify({ version: t.version, source: termsSource(t) }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) { layer.querySelector(".form-msg").textContent = data.detail || data.error || "沒送出去，請再按一次。"; return; }
        termsShow(data); // need 變成空字串就收掉
      } catch (e) {
        layer.querySelector(".form-msg").textContent = "連不上伺服器，請再按一次。";
      } finally { termsBusy = false; btn.disabled = false; }
    });
  }

  async function termsCheck() {
    termsAsked = true;
    try {
      const res = await fetch("/api/terms", { credentials: "same-origin" });
      if (!res.ok) return; // 沒登入、伺服器沒這一包：什麼都不做
      termsShow(await res.json());
    } catch (e) { termsAsked = false; } // 斷線：下一次重畫再問
  }

  function termsWatch() {
    termsAddLinks();
    termsInsertChecks();
    const inGame = typeof S !== "undefined" && S.stage === "game";
    if (!inGame) { termsAsked = false; if (document.querySelector(".terms-layer")) termsClose(); return; }
    if (!termsAsked) termsCheck();
  }

  function termsShouldReask({ text, inGame, layerOpen, now, last }) {
    return String(text ?? "").includes("條款") && !!inGame && !layerOpen && now - last >= TERMS_REASK_GAP_MS;
  }

  function termsOnToast() {
    const el = document.getElementById("toast");
    const now = Date.now();
    const inGame = typeof S !== "undefined" && S.stage === "game";
    const layerOpen = !!document.querySelector(".terms-layer");
    if (!termsShouldReask({ text: el && el.textContent, inGame, layerOpen, now, last: termsReaskAt })) return;
    termsReaskAt = now;
    termsAsked = false;
    termsCheck();
  }

  let termsQueued = false;
  let termsToastQueued = false;
  if (typeof MutationObserver !== "undefined" && typeof document !== "undefined") { // 網頁測試的 node 沒有 DOM：不看
    new MutationObserver(() => {
      if (termsQueued) return;
      termsQueued = true;
      queueMicrotask(() => { termsQueued = false; termsWatch(); });
    }).observe(document.getElementById("app") || document.body, { childList: true, subtree: true });
    const termsToastEl = document.getElementById("toast"); // 第 255 批：殼的吐司（index.html 固定的元素，在 #app 外面）
    if (termsToastEl) {
      new MutationObserver(() => {
        if (termsToastQueued) return;
        termsToastQueued = true;
        queueMicrotask(() => { termsToastQueued = false; termsOnToast(); });
      }).observe(termsToastEl, { childList: true, characterData: true, subtree: true });
    }
    document.addEventListener("submit", termsBlockSubmit, true); // 第 206 批：capture，先於 app.js 的 submit 鏈
  }
