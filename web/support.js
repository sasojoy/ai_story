/* 天下大勢的網頁前端：客服（帳號與客服第 211 批；設計 docs/superpowers/specs/2026-11-08-帳號綁定與客服-design.md 6.1、6.2、6.6）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 * 開關關著時伺服器的 /api/main 沒有 support_unread、support_staff：這裡每一個畫法都回空字串，設定抽屜與管理頁一個位元組都不變。
 * 畫面照企劃者 2026-11-08 挑的：抽屜 C（一行「客服 ›」，點了自己一頁，分段「我的單／寫新單」），管理頁 B（寬版左清單、右單＋帳號卡；窄版照清單頁）。
 * 換版只換 supportPageHtml、supportDeskHtml 兩個函式；帳號卡（第 212 批：點開單直接帶出、查別的帳號查到的）只換 supportCardHtml。玩家與客服寫的字一律只過 esc，不經 markdown。字待 joy 潤。
 */
"use strict";

  // 類別的字（伺服器也回一份 categories；先後照這裡）
  const SUPPORT_CATS = [["account", "帳號"], ["mall", "商城"], ["game", "遊戲問題"], ["other", "其他"]]; // 待 joy 潤
  const SUPPORT_STATUS = { open: "處理中", answered: "已回覆", closed: "已結" }; // 待 joy 潤
  const SUPPORT_NOTE = "同時最多 3 張沒結的單，一天最多送 5 張。帳號、名號、時間、版本會自動附上。"; // 待 joy 潤
  const SUPPORT_ADMIN_NOTE = "要補發、退款、重設密碼、解綁、刪帳號：在單上註記，請管理者做。"; // 待 joy 潤

  function supportOn() { return !!(S.main && "support_unread" in S.main); }

  function supportWhen(ts) { // 秒 → 「11/08 14:05」（照這台裝置的時區）
    const d = new Date(Number(ts) * 1000);
    const two = (n) => String(n).padStart(2, "0");
    return `${two(d.getMonth() + 1)}/${two(d.getDate())} ${two(d.getHours())}:${two(d.getMinutes())}`;
  }
  function supportCat(t) { return esc(t.category_name || t.category); }
  function supportStatus(st) { return `<span class="sup-st sup-${esc(st)}">${esc(SUPPORT_STATUS[st] || st)}</span>`; }

  // ── 設定抽屜那一行（關著回 ""）──
  function supportRow() {
    if (!supportOn()) return "";
    const n = Number(S.main.support_unread) || 0;
    return `<div class="row sup-row"><button class="btn small" data-act="support-open">客服 ›${n ? `<span class="sup-dot" aria-label="有新回覆"></span>` : ""}</button></div>`; // 待 joy 潤
  }

  // 「管理者工具 ›」那一格：不是管理者、是客服才給（關著回 ""）
  function supportDeskLink() {
    if (!(S.main && S.main.support_staff)) return "";
    return `<a class="btn small ghost ad-entry" href="/admin">客服單 ›</a>`; // 待 joy 潤
  }

  // ── 客服自己一頁（S.supportPage 時設定抽屜整個換成它）──
  function supportTicketHtml(t) { // 點開一張單：對話與「再回一句」
    const msgs = [`<div class="sup-msg sup-me"><span class="sup-who">你・${supportWhen(t.created)}</span>${esc(t.body)}</div>`]
      .concat((t.replies || []).map((r) => r.staff
        ? `<div class="sup-msg sup-cs"><span class="sup-who">客服・回覆　${supportWhen(r.created)}</span>${esc(r.body)}</div>` // 待 joy 潤
        : `<div class="sup-msg sup-me"><span class="sup-who">你・${supportWhen(r.created)}</span>${esc(r.body)}</div>`));
    const form = t.status === "closed" ? "" : `<form id="support-reply-form" class="stack" data-id="${Number(t.id)}">
        <textarea class="input" name="body" maxlength="1000" placeholder="再回一句（1,000 字內）"></textarea>
        <p class="form-msg"></p><button class="btn" type="submit">送出</button></form>`; // 待 joy 潤
    return `<div class="top-row"><button class="btn small ghost" data-act="support-list">‹ 回客服</button><h3 style="flex:1">#${Number(t.id)}・${supportCat(t)}</h3></div>
      <p class="sup-meta">${supportStatus(t.status)}　送出 ${supportWhen(t.created)}</p>
      ${msgs.join("")}${form}`; // 待 joy 潤
  }
  function supportListHtml(mine) {
    const list = (mine && mine.tickets) || [];
    if (!list.length) return `<p class="muted">還沒有單。</p>`; // 待 joy 潤
    return list.map((t) => {
      const last = (t.replies || []).filter((r) => r.staff).slice(-1)[0];
      return `<button class="sup-tk${t.status === "answered" ? " sup-hot" : ""}" data-act="support-ticket" data-id="${Number(t.id)}">
        <span class="sup-tk-top">${supportStatus(t.status)}#${Number(t.id)}・${supportCat(t)}<span class="sup-when">${supportWhen(t.updated)}</span></span>
        <span class="sup-sum">${esc(t.body)}</span>${last ? `<span class="sup-reply">客服：${esc(last.body)}</span>` : ""}</button>`; // 待 joy 潤
    }).join("") + `<p class="muted sup-fine">同時最多 3 張沒結的單，一天最多送 5 張。</p>`; // 待 joy 潤
  }
  function supportNewHtml() {
    return `<form id="support-new-form" class="stack">
        <h4>寫一張單</h4>
        <label>類別：<select name="category">${SUPPORT_CATS.map(([k, name]) => `<option value="${k}">${name}</option>`).join("")}</select></label>
        <textarea class="input" name="body" maxlength="1000" placeholder="想說的事（1,000 字內）"></textarea>
        <p class="muted sup-fine">${SUPPORT_NOTE}</p>
        <p class="form-msg"></p><button class="btn primary" type="submit">送出</button></form>`; // 待 joy 潤
  }
  function supportPageHtml() {
    const mine = S.supportMine;
    const open = S.supportTicket != null && mine ? (mine.tickets || []).find((t) => t.id === S.supportTicket) : null;
    const tab = S.supportTab === "new" ? "new" : "mine";
    const body = open ? supportTicketHtml(open) : `
        <div class="top-row"><button class="btn small ghost" data-act="support-back">‹ 回設定</button><h3 style="flex:1">客服</h3><button class="btn small ghost" data-act="support-close">關閉</button></div>
        <div class="sup-seg"><button class="${tab === "mine" ? "on" : ""}" data-act="support-tab" data-tab="mine">我的單</button><button class="${tab === "new" ? "on" : ""}" data-act="support-tab" data-tab="new">寫新單</button></div>
        ${tab === "new" ? supportNewHtml() : (mine ? supportListHtml(mine) : `<p class="muted">讀取中…</p>`)}
        ${tab === "mine" && mine ? `<div class="row"><button class="btn small" data-act="support-tab" data-tab="new">＋ 寫一張新單</button></div>` : ""}`; // 待 joy 潤
    return `
      <div class="sheet-bg" data-act="support-close"></div>
      <div class="sheet sup-page" role="dialog" aria-label="客服">
        <div class="grip"></div>${body}
      </div>`; // 待 joy 潤
  }

  async function supportLoad() {
    try {
      S.supportMine = await api("/api/support/mine");
      if (S.main) S.main.support_unread = 0;
    } catch (e) { S.supportMine = S.supportMine || { tickets: [] }; }
    if (S.supportPage) renderKeepingSheet();
  }

  // ── 管理頁（客服身分；admin.js 的 renderAdmin 開頭分流過來，不叫 /api/admin）──
  const SUPPORT_LOOKUP_KINDS = [["login", "帳號"], ["email", "Email"], ["phone", "手機"]]; // 待 joy 潤
  const SUPPORT_LOOKUP_NOTE = "只收完整帳號、Email、手機（不收名號）。每小時 20 次，每次都留紀錄（查無也算），客服改不到。"; // 待 joy 潤

  function supportDay(ts) { // 秒 → 「11/08」
    const d = new Date(Number(ts) * 1000);
    return `${String(d.getMonth() + 1).padStart(2, "0")}/${String(d.getDate()).padStart(2, "0")}`;
  }
  function supportAmount(n) { // +3000／−300（減號用 U+2212）
    const v = Number(n) || 0;
    return v > 0 ? `+${v}` : v < 0 ? `−${-v}` : "0";
  }

  // 帳號卡（第 212 批；換版只換這一個函式）：看單時伺服器帶的 card，或「查別的帳號」查到的。沒有 binds 的（舊的回應）只畫單上已有的三樣
  function supportCardHtml(card) {
    if (!card) return "";
    if (card.gone) return `<section class="card sup-acct"><p class="muted">單上的帳號已經不在了。</p></section>`; // 待 joy 潤
    const rows = [`<dt>名號</dt><dd>${card.character ? esc(card.character) : "還沒建角色。"}</dd>`]; // 待 joy 潤
    let ledger = "";
    if (Array.isArray(card.binds)) {
      const binds = card.binds.map((b) => esc(b.name) + (b.shown ? ` ${esc(b.shown)}` : "")).join("、") || "—";
      rows.push(`<dt>綁了</dt><dd>${binds}</dd>`, `<dt>餘額</dt><dd>${Number(card.balance) || 0} 元寶</dd>`); // 待 joy 潤
      const lines = (card.ledger || []).map((e) => `<tr><td>${supportDay(e.time)}</td><td>${esc(e.reason)}</td><td class="sup-amt">${supportAmount(e.delta)}</td><td>${esc(e.note)}</td></tr>`).join("");
      ledger = `<div class="sup-ledger-h">元寶帳本</div>${lines ? `<table class="sup-ledger">${lines}</table>` : `<p class="muted">還沒有帳。</p>`}`; // 待 joy 潤
    }
    return `<section class="card sup-acct"><div class="sup-title">帳號 ${esc(card.login)}<span class="muted">建帳號 ${supportWhen(card.created)}</span></div>
        <dl>${rows.join("")}</dl>${ledger}</section>`; // 待 joy 潤
  }

  // 「查別的帳號」：種類、完整的字、單號（預設目前選的那張）；查到的卡畫在表單底下
  function supportLookupHtml() {
    const q = S.supportLookupQ || {};
    const kind = SUPPORT_LOOKUP_KINDS.some(([k]) => k === q.kind) ? q.kind : "login";
    const id = q.id != null && q.id !== "" ? q.id : (S.supportDeskPick != null ? S.supportDeskPick : "");
    return `<section class="card"><div class="sup-title">查別的帳號</div>
        <form id="support-lookup-form" class="sup-lookup">
          <select name="kind">${SUPPORT_LOOKUP_KINDS.map(([k, name]) => `<option value="${k}"${k === kind ? " selected" : ""}>${name}</option>`).join("")}</select>
          <input class="input" name="text" value="${esc(q.text || "")}" placeholder="完整帳號、Email 或手機">
          <input class="input sup-lookup-id" name="ticket" inputmode="numeric" value="${esc(id)}" placeholder="單號">
          <button class="btn small" type="submit">查</button>
          <p class="form-msg">${esc(S.supportLookupMsg || "")}</p>
        </form>
        <p class="muted sup-fine">${SUPPORT_LOOKUP_NOTE}</p></section>${supportCardHtml(S.supportDeskCard)}`; // 待 joy 潤
  }

  function supportDeskTicketHtml(t) {
    const acct = t.account || {};
    const msgs = [`<div class="sup-msg sup-me"><span class="sup-who">玩家 ${esc(acct.character)}・${supportWhen(t.created)}</span>${esc(t.body)}</div>`]
      .concat((t.replies || []).map((r) => `<div class="sup-msg ${r.staff ? (r.internal ? "sup-note" : "sup-cs") : "sup-me"}"><span class="sup-who">${r.staff ? (r.internal ? "請管理者處理" : "客服・回覆") : "玩家"}　${supportWhen(r.created)}</span>${esc(r.body)}</div>`)); // 待 joy 潤
    const id = Number(t.id);
    const form = t.status === "closed" ? `<p class="muted">${supportStatus("closed")}</p>` : `<div class="stack sup-answer">
        <textarea class="input" id="support-answer-body" maxlength="1000" placeholder="回覆（1,000 字內）"></textarea>
        <div class="row"><button class="btn small" data-act="support-answer" data-id="${id}" data-then="wait">回覆並等玩家</button><button class="btn small" data-act="support-answer" data-id="${id}" data-then="close">回覆並結單</button><button class="btn small ghost" data-act="support-answer" data-id="${id}" data-then="admin">請管理者處理</button></div>
        <p class="muted sup-fine">${SUPPORT_ADMIN_NOTE}</p></div>`; // 待 joy 潤
    return `<section class="card"><div class="sup-title">#${Number(t.id)}・${supportCat(t)}<span class="muted">${supportWhen(t.created)}・${esc(t.version)}</span></div>${msgs.join("")}${form}</section>
      ${supportCardHtml(t.card || { login: acct.login, created: acct.created, character: acct.character })}`;
  }
  function supportDeskHtml() {
    const head = `<header class="ad-head"><a class="btn small ghost" href="/">‹ 回江湖</a><h2>客服</h2><button class="btn small" data-act="support-desk-refresh">重新整理</button></header>`; // 待 joy 潤
    const q = S.supportDesk;
    if (!q) return `${head}<p class="muted">讀取中…</p>`; // 待 joy 潤
    const tile = (k, v, sub) => `<div class="sup-tile"><small>${k}</small><b>${Number(v) || 0}</b><span>${sub}</span></div>`;
    const tiles = `<div class="sup-tiles">${tile("沒回的", q.open, "處理中")}${tile("等玩家", q.waiting, "回過了")}${tile("今天", q.fresh, "新單")}${tile("查帳剩", q.lookups_left, "這一小時")}</div>`; // 待 joy 潤
    const rows = (q.tickets || []).map((t) => `<button class="sup-row-tk${S.supportDeskPick === t.id ? " sel" : ""}" data-act="support-desk-pick" data-id="${Number(t.id)}">
        <span class="sup-n">#${Number(t.id)}</span><span class="sup-s">${supportStatus(t.status)}<span class="sup-cat">${supportCat(t)}</span> ${esc(t.body)}</span>
        <span class="sup-p">${esc(t.character)}${t.login ? `（帳號 ${esc(t.login)}）` : ""}${t.admin_flag ? "・請管理者處理" : ""}</span></button>`).join("") || `<p class="muted">沒有沒結的單。</p>`; // 待 joy 潤
    const list = `<div>${tiles}<section class="card"><div class="sup-title">客服單</div>${rows}</section>${supportLookupHtml()}</div>`; // 待 joy 潤
    const one = S.supportDeskTicket ? `<div>${supportDeskTicketHtml(S.supportDeskTicket)}</div>` : "";
    return `${head}<div class="sup-split${one ? " sup-has-one" : ""}">${list}${one}</div>`;
  }
  function renderSupportDesk() {
    if (typeof hideMapHost === "function") hideMapHost();
    $app.innerHTML = `<div class="ad-shell sup-wide">${supportDeskHtml()}</div>`;
    if (!S.supportDesk && !S.supportDeskLoading) supportDeskReload();
  }
  async function supportDeskReload() {
    S.supportDeskLoading = true;
    try {
      S.supportDesk = await api("/api/support/queue");
      if (S.supportDeskPick != null) S.supportDeskTicket = await api(`/api/support/ticket/${Number(S.supportDeskPick)}`);
    } catch (e) { S.supportDesk = S.supportDesk || { open: 0, waiting: 0, fresh: 0, tickets: [] }; }
    S.supportDeskLoading = false;
    if (S.adminPage) renderKeepingSheet();
  }

  async function supportClick(act, el, ev) {
    switch (act) {
        case "support-open": S.supportPage = true; S.supportTab = "mine"; S.supportTicket = null; render(); await supportLoad(); break; // 設定抽屜「客服 ›」
        case "support-back": S.supportPage = false; S.supportTicket = null; render(); break;
        case "support-tab": S.supportTab = el.dataset.tab === "new" ? "new" : "mine"; S.supportTicket = null; renderKeepingSheet(); break;
        case "support-ticket": S.supportTicket = Number(el.dataset.id); renderKeepingSheet(); break;
        case "support-list": S.supportTicket = null; renderKeepingSheet(); break;
        case "support-desk-refresh": S.supportDesk = null; renderKeepingSheet(); break;
        case "support-close": S.sheet = false; S.supportPage = false; S.supportTicket = null; render(); break; // 客服那一頁的「關閉」與底下的灰幕：下次打開設定回到設定
        case "support-desk-pick":
          S.supportDeskPick = Number(el.dataset.id);
          S.supportDeskTicket = await api(`/api/support/ticket/${S.supportDeskPick}`);
          renderKeepingSheet();
          break;
        case "support-answer": { // 客服回一則：回覆並等玩家／回覆並結單／請管理者處理
          const box = document.getElementById("support-answer-body");
          const was = S.supportDeskTicket;
          S.supportDeskTicket = await api("/api/support/answer", { id: Number(el.dataset.id), body: box ? box.value : "", then: el.dataset.then });
          if (was && was.card && S.supportDeskTicket && S.supportDeskTicket.id === was.id) S.supportDeskTicket.card = was.card; // 回單的回應不帶卡：沿用看單時的
          S.supportDesk = null; // 清單跟著重讀（數字會變）
          renderKeepingSheet();
          break;
        }
    } // supportClick
  } // supportClick
  registerClicks(supportClick, ["support-open", "support-back", "support-tab", "support-ticket", "support-list", "support-desk-refresh", "support-close", "support-desk-pick", "support-answer"]);

  async function supportForm(form, data) {
      if (form.id === "support-new-form") {
        const r = await api("/api/support/ticket", { category: data.category, body: data.body || "" });
        S.supportMine = r.mine;
        S.supportTab = "mine";
        S.supportTicket = r.id;
        renderKeepingSheet();
      } else if (form.id === "support-reply-form") {
        const r = await api("/api/support/reply", { id: Number(form.dataset.id), body: data.body || "" });
        S.supportMine = r.mine;
        renderKeepingSheet();
      } else if (form.id === "support-lookup-form") { // 查別的帳號（第 212 批）：查到的卡留著，回單後也還在。單號那一欄叫 ticket：欄位叫 id 的話瀏覽器會拿它蓋掉 form.id，殼就找不到這支處理函式（K 波落地時實機點出來的）
        S.supportLookupQ = { kind: data.kind, text: data.text || "", id: data.ticket };
        const r = await api("/api/support/lookup", { id: Number(data.ticket), kind: data.kind, text: data.text || "" });
        S.supportDeskCard = r.card;
        if (S.supportDesk) S.supportDesk.lookups_left = r.left;
        S.supportLookupMsg = r.found ? `已查到 ${r.card.login}（這一小時還剩 ${r.left} 次）。` : `${r.message}這一小時還剩 ${r.left} 次。`; // 待 joy 潤
        renderKeepingSheet();
      } // supportForm
  } // supportForm
  registerForms(supportForm, ["support-new-form", "support-reply-form", "support-lookup-form"]);
