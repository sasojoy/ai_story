/* 天下大勢的網頁前端：登入頁的格（帳號綁定，features/identity；帳號與客服第 201 批）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 * 載入時不做事：殼的 renderGate 畫完登入頁叫 drawGateSlots，這裡第一次被叫時問一次 /api/identity/gate。
 * 關著（404）或還沒問到時一個字都不動：登入頁跟沒有這一支一樣。開著時照企劃者 11/08 挑的 C 版：分段「快速登入｜帳號登入｜註冊」，
 * 快速登入那一格放開著的那幾條路與客服信箱；上次選的那一格記在這台瀏覽器（讀不到就從快速登入開始）。
 * 這一批四條路都還沒接（按了只說尚未開放）；畫法全在 identityGateHtml，要換版只改它。
 */
"use strict";

  const IDENTITY_MODE_KEY = "tx_gate_mode";
  const IDENTITY_MODES = ["quick", "login", "register"];
  const IDENTITY_SEG = [["quick", "快速登入"], ["login", "帳號登入"], ["register", "註冊"]]; // 待 joy 潤
  const IDENTITY_WAYS = { line: "用 LINE 繼續", google: "用 Google 繼續", email: "Email", phone: "手機" }; // 待 joy 潤
  const IDENTITY_SOON = "尚未開放"; // 待 joy 潤
  const IDENTITY_MAIL = "登不進去？寫信到客服信箱：{mail}（人工回信）"; // 待 joy 潤

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

  // 登入頁開著時的樣子（C 版）：html 是殼畫好的 .gate 裡面那一段，回改好的那一段。沒有路、也沒有客服信箱時原樣回去
  function identityGateHtml(html, info, mode) {
    const ways = (info.ways || []).filter((w) => IDENTITY_WAYS[w]);
    const mail = info.support_mail
      ? `<p class="support-mail fine">${esc(IDENTITY_MAIL).replace("{mail}", `<a href="mailto:${esc(info.support_mail)}">${esc(info.support_mail)}</a>`)}</p>`
      : "";
    if (!ways.length) return mail ? html.replace('<section class="gate-patch"', `${mail}<section class="gate-patch"`) : html;
    const seg = `<div class="seg">${IDENTITY_SEG.map(([m, label]) =>
      `<button class="${m === mode ? "on" : ""}" data-act="gate" data-mode="${m}">${label}</button>`).join("")}</div>`;
    const buttons = `<div class="idp card">${ways.map((w) =>
      `<button class="btn idp-${w}" data-act="identity-way" data-way="${w}">${IDENTITY_WAYS[w]}</button>`).join("")}</div>`;
    let out = html.replace(/<div class="seg">[\s\S]*?<\/div>/, seg);
    if (mode === "quick") out = out.replace(/<form id="gate-form"[\s\S]*?<\/form>/, buttons);
    return out.replace('<section class="gate-patch"', `${mail}<section class="gate-patch"`);
  }

  function identityGate(gate, S) {
    if (!gate) return;
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
    if (!info || (!(info.ways || []).length && !info.support_mail)) return;
    const mode = IDENTITY_MODES.includes(S.gateMode) ? S.gateMode : "login";
    if ((info.ways || []).length) identityRemember(mode);
    const html = identityGateHtml(gate.innerHTML, info, mode);
    if (html !== gate.innerHTML) gate.innerHTML = html;
  }

  async function identityClick(act, el, ev) {
    switch (act) {
        case "identity-way": toast(IDENTITY_SOON); break;
    } // identityClick
  } // identityClick
  registerClicks(identityClick, ["identity-way"]);
  registerGateSlot(identityGate);
