/* 天下大勢的網頁前端：使用條款與隱私權（功能包 tianxia/features/terms/）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 * 不改 app.js：看 #app 畫了什麼（MutationObserver）——登入頁、設定頁底下補兩個連結；進了遊戲問一次 /api/terms，
 * 要按同意就疊一層在最上面（沒同意過任何一版：按了同意才關得掉；改版的考慮期內：可以先關掉）。字待 joy 潤
 */
"use strict";

  const TERMS_LINKS = '<p class="terms-links"><a href="/terms" target="_blank" rel="noopener">使用條款</a>・<a href="/privacy" target="_blank" rel="noopener">隱私權條款</a></p>';
  const TERMS_SAY = {
    must: "開始之前，請先看過並同意天下大勢的使用條款與隱私權條款。",
    ask: "使用條款與隱私權條款有新版。{deadline} 以前沒有表示反對，就視為接受新版。",
    points: "重點：",
    agree: "我已滿 18 歲或已得到法定代理人同意，並同意以上條款",
    later: "稍後再看",
    no: "我不同意",
    noMust: "不同意的話沒辦法進遊戲。要終止帳號、退還沒用掉的元寶，請寫信到 {email}。",
    noAsk: "不同意新版的話，可以終止帳號並退還沒用掉的元寶，請寫信到 {email}。",
    logout: "登出",
  };
  let termsAsked = false; // 這一次登入問過 /api/terms 了（登出、回到登入頁就重來）
  let termsBusy = false;

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
    const lead = must ? TERMS_SAY.must : TERMS_SAY.ask.replace("{deadline}", termsEsc(t.deadline || ""));
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
          body: JSON.stringify({ version: t.version, source: t.need === "must" ? "gate" : "update" }),
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
    const inGame = typeof S !== "undefined" && S.stage === "game";
    if (!inGame) { termsAsked = false; if (document.querySelector(".terms-layer")) termsClose(); return; }
    if (!termsAsked) termsCheck();
  }

  let termsQueued = false;
  if (typeof MutationObserver !== "undefined" && typeof document !== "undefined") { // 網頁測試的 node 沒有 DOM：不看
    new MutationObserver(() => {
      if (termsQueued) return;
      termsQueued = true;
      queueMicrotask(() => { termsQueued = false; termsWatch(); });
    }).observe(document.getElementById("app") || document.body, { childList: true, subtree: true });
  }
