/* 天下大勢的網頁前端：帖友書信（tianxia/features/mail；設計稿 https://claude.ai/artifact/FhMZSwH6aqNsrnNAwHBznn，Joy 2026-11-07）。
 *
 * 見聞 → 紀錄底下第三格「信匣」：一位帖友一行（最新那一封的開頭、他寄來還沒看的幾封）；點開是跟他的往來（照季分段），最底下回信。
 * 右上「⋯」：看名帖、不收他的信（他不會知道）、檢舉寄給你的那一封。名帖匣放大的那一張底下多一顆「寫信」。
 * 見聞分頁的紅點也看 main.mail.unread（mailUnread）。沒有「已讀」：寫給別人的只寫寄出的時刻與地點。
 * 跟 mall.js 一樣是一般的 <script>：頂層的名字同在一個全域裡；點擊用 registerClicks 登記在這支檔。字待 joy 潤。
 */
"use strict";

  const mailUnread = () => (S.main && S.main.mail ? S.main.mail.unread | 0 : 0);
  const mailShown = () => !!(S.main && S.main.mail);

  function mailTake(r) { // 伺服器回的 {inbox, thread?, mail}：記下來、紅點跟著改
    if (!r) return;
    if (r.inbox) S.mailBox = r.inbox;
    if (r.thread) S.mailThread = r.thread;
    if (r.mail && S.main) S.main.mail = r.mail;
  }

  async function loadMail() {
    mailTake(await api("/api/mail"));
    if (S.tab === "news" && S.news === "mail") renderPage();
  }

  async function mailOpen(name) {
    S.mailWith = name;
    S.mailThread = null;
    S.mailMenu = false;
    if (S.tab !== "news" || S.news !== "mail") {
      S.news = "mail";
      if (S.tab !== "news") { await goTab("news"); } else renderPage();
    } else renderPage();
    mailTake(await api(`/api/mail/thread?name=${encodeURIComponent(name)}`));
    if (S.news === "mail" && S.mailWith === name) renderPage();
  }

  function mailSealHtml(name) { // 名號前兩個字直排成一方印（名帖右上那一方的樣子）
    return `<span class="mail-seal" aria-hidden="true">${esc([...name].slice(0, 2).join("\n"))}</span>`;
  }

  // 見聞「信匣」
  function mailBoxHtml() {
    if (S.mailWith) return mailThreadHtml();
    const b = S.mailBox;
    if (!b) return '<p class="muted">載入中…</p>';
    if (b.closed) return '<p class="muted">書信暫時關著。</p>';
    const rows = b.threads.map((t) => `<button class="mail-row" data-act="mail-open" data-name="${esc(t.name)}">${mailSealHtml(t.name)}
        <span class="mail-who"><b>${esc(t.name)}</b><span class="mail-peek">${t.mine ? "你：" : ""}${esc(t.peek)}</span></span>
        <span class="mail-when">${t.season === b.season ? esc(t.stamp) : `第 ${t.season | 0} 季`}${t.unread ? `<i class="mail-dot">${t.unread | 0}</i>` : ""}</span></button>`).join("");
    const friends = b.friends.length
      ? `<p class="report-group">還沒寫過信的帖友</p><div class="mail-friends">${b.friends.map((n) => `<button class="btn ghost small" data-act="mail-open" data-name="${esc(n)}">寫給${esc(n)}</button>`).join("")}</div>` : "";
    const blocked = b.blocked.length
      ? `<details class="mail-blocked"><summary>不收信的人（${b.blocked.length}）</summary>${b.blocked.map((n) => `<div class="row"><span>${esc(n)}</span><button class="btn ghost small" data-act="mail-unblock" data-name="${esc(n)}">解開</button></div>`).join("")}</details>` : "";
    return `${b.muted ? `<p class="form-msg">${esc(b.muted)}</p>` : ""}
      ${rows ? `<div class="card mail-list">${rows}</div>` : '<p class="muted">還沒有信。跟人互換過名帖，就能寫信給他。</p>'}
      ${friends}
      <p class="muted mail-foot">今天還能寄 ${b.left | 0} 封。只有互換過名帖的人寫得進來。</p>${blocked}`;
  }

  // 跟一位帖友的往來：新的在下面（伺服器給的是新的在前，這裡倒過來畫），照季分段；最底下回信
  function mailThreadHtml() {
    const t = S.mailThread, name = S.mailWith;
    const head = `<div class="mail-head"><button class="linkish back" data-act="mail-back">‹ 信匣</button><b>${esc(name)}</b>
      <button class="linkish mail-more-btn" data-act="mail-menu" aria-expanded="${!!S.mailMenu}" aria-label="更多">⋯</button></div>`;
    if (!t || t.name === undefined) return `${head}<p class="muted">載入中…</p>`;
    const menu = S.mailMenu ? `<div class="card mail-menu">
        ${t.blocked ? `<button data-act="mail-unblock" data-name="${esc(name)}">又要收他的信</button>` : `<button data-act="mail-block" data-name="${esc(name)}">不收他的信（他不會知道）</button>`}
        <p class="muted">要檢舉哪一封，點那一封底下的「檢舉」。</p></div>` : "";
    let season = null;
    const letters = t.letters.slice().reverse().map((x) => {
      const bar = x.season !== season ? `<p class="mail-season">— 第 ${x.season | 0} 季 —</p>` : "";
      season = x.season;
      const who = x.mine ? "你" : name;
      return `${bar}<div class="mail-letter${x.mine ? " mine" : ""}"><p>${esc(x.text).replace(/\n/g, "<br>")}</p>
        <span class="mail-sig">${esc(who)}・${esc(x.stamp)}${x.place ? `・${esc(x.place)}` : ""}${x.mine ? "" : ` <button class="linkish mail-report" data-act="mail-report" data-id="${x.id}">檢舉</button>`}</span></div>`;
    }).join("");
    const older = t.more ? `<button class="btn ghost small mail-older" data-act="mail-older">更早的信</button>` : "";
    const draft = S.mailDraft && S.mailDraft.name === name ? S.mailDraft.text : "";
    const compose = t.problem
      ? `<p class="muted mail-cant">${esc(t.problem)}</p>`
      : `<div class="mail-compose"><textarea class="input mail-paper" id="mail-text" maxlength="${t.max_chars | 0}" rows="4" placeholder="寫信給${esc(name)}……" aria-label="寫信給${esc(name)}">${esc(draft)}</textarea>
        <div class="row mail-send-row"><span class="muted">${draft.length}／${t.max_chars | 0} 字・今天還能寄 ${t.left | 0} 封</span><button class="btn primary" data-act="mail-send">寄出</button></div>
        <p class="form-msg" id="mail-note" role="alert">${esc(S.mailNote || "")}</p></div>`;
    return `${head}${menu}<div class="mail-thread">${older}${letters || '<p class="muted">還沒有往來。寫第一封吧。</p>'}</div>${compose}`;
  }

  async function mailSend() {
    const box = document.getElementById("mail-text");
    const text = box ? box.value : "";
    const name = S.mailWith;
    S.mailDraft = { name, text };
    await busy(async () => {
      const r = await api("/api/mail/send", { name, text });
      mailTake(r);
      const line = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      if (r.ok) { S.mailDraft = null; S.mailNote = ""; toast(line || "寄出去了。"); } else S.mailNote = line;
      renderPage();
    });
  }

  async function mailBlock(name, value) {
    await busy(async () => {
      const r = await api("/api/mail/block", { name, value });
      mailTake(r);
      S.mailMenu = false;
      toast((r.message || "").replace(/<[^>]+>/g, " ").trim());
      renderPage();
    });
  }

  function mailReport(id) {
    const name = S.mailWith;
    ask(`檢舉${name}的這一封信：它會從你的信匣收起來，管理者會看到這一封。要不要順便不收他的信，之後在右上「⋯」裡可以設。確定檢舉？`, "檢舉", async () => {
      await busy(async () => {
        const r = await api("/api/mail/report", { id, name });
        mailTake(r);
        toast((r.message || "").replace(/<[^>]+>/g, " ").trim());
        renderPage();
      });
    });
  }

  async function mailOlder() {
    const t = S.mailThread;
    if (!t || !t.letters.length) return;
    const r = await api(`/api/mail/thread?name=${encodeURIComponent(S.mailWith)}&before=${t.letters[t.letters.length - 1].id}`);
    if (r && r.thread) { t.letters = t.letters.concat(r.thread.letters); t.more = r.thread.more; }
    renderPage();
  }

  // 管理頁「書信檢舉」（admin.js 的 adSecBody 叫它）：只有被檢舉的那幾封。撤下＝兩邊都看不到；沒事＝檢舉清掉；停寄幾天
  function mailAdminHtml(rows) {
    return `<p class="muted">書信檢舉（只看得到被檢舉的信）</p>${rows.map((x) => `<div class="mail-admin-row">
      <p><b>${esc(x.sender)}</b> 寫給 <b>${esc(x.recipient)}</b>・第 ${x.season | 0} 季 ${esc(x.stamp)}・${x.count | 0} 人檢舉${x.muted ? "・停寄中" : ""}</p>
      <blockquote>${esc(x.text).replace(/\n/g, "<br>")}</blockquote>
      <div class="row wrap"><button class="btn warn small" data-act="admin" data-op="mail_remove" data-id="${x.id}">撤下</button><button class="btn small" data-act="admin" data-op="mail_keep" data-id="${x.id}">沒事</button>
        ${[1, 3, 7].map((d) => `<button class="btn ghost small" data-act="admin" data-op="mail_mute" data-name="${esc(x.sender)}" data-days="${d}">停寄 ${d} 天</button>`).join("")}
        ${x.muted ? `<button class="btn ghost small" data-act="admin" data-op="mail_mute" data-name="${esc(x.sender)}" data-days="0">解開停寄</button>` : ""}</div></div>`).join("")}`;
  }

  // 打字時記下草稿（輪詢重畫頁面也不會把寫到一半的信洗掉），字數跟著跳
  if (typeof document !== "undefined" && document.addEventListener) {
    document.addEventListener("input", (ev) => {
      const box = ev.target;
      if (!box || box.id !== "mail-text") return;
      S.mailDraft = { name: S.mailWith, text: box.value };
      const count = box.parentElement && box.parentElement.querySelector(".mail-send-row .muted");
      if (count && S.mailThread) count.textContent = `${box.value.length}／${S.mailThread.max_chars | 0} 字・今天還能寄 ${S.mailThread.left | 0} 封`;
    });
  }
  async function mailClick(act, el, ev) {
    switch (act) {
        case "mail-open": await mailOpen(el.dataset.name); break;
        case "mail-write": S.mtZoom = null; await mailOpen(el.dataset.name); break; // 名帖匣放大的那一張底下的「寫信」
        case "mail-back": S.mailWith = null; S.mailThread = null; S.mailMenu = false; S.mailNote = ""; renderPage(); await loadMail(); break;
        case "mail-menu": S.mailMenu = !S.mailMenu; renderPage(); break;
        case "mail-send": await mailSend(); break;
        case "mail-block": await mailBlock(el.dataset.name, true); break;
        case "mail-unblock": await mailBlock(el.dataset.name, false); break;
        case "mail-report": mailReport(Number(el.dataset.id)); break;
        case "mail-older": await mailOlder(); break;
    } // mailClick
  } // mailClick
  registerClicks(mailClick, ["mail-open", "mail-write", "mail-back", "mail-menu", "mail-send", "mail-block", "mail-unblock", "mail-report", "mail-older"]);
