/* 天下大勢的網頁前端：玩家傳那一層與行狀（全部拆包第 66 批從 app.js 切出來）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 */
"use strict";

  // ── 玩家傳（第二批）：季末的《某某傳》，疊在整個畫面上（S.zhuan = { season, view }）──
  // view 是 /api/zhuan 回的（Game.biography_view＋writing、url）。還沒寫成：一顆「請史官落筆」；正在寫：每幾秒問一次（zhuanPoll）。
  // 寫成了：段落（評曰那一段另起）、直書切換（記在這個瀏覽器，跟公開頁同一個鍵）、公開分享的開關與網址、重寫一次。字一律跳脫。
  // 樣子是竹簡，在 web/zhuan.css（跟公開頁 zhuan_html.py 共用標記），不用武學譜那本書（企劃者 2026-10-12）
  const ZHUAN_VERTICAL = "tx-zhuan-vertical";
  const ZHUAN_POLL_MS = 4000;
  function zhuanVertical() {
    if (S.zhuanVertical === undefined) {
      try { S.zhuanVertical = localStorage.getItem(ZHUAN_VERTICAL) === "1"; } catch (e) { S.zhuanVertical = false; }
    }
    return S.zhuanVertical;
  }
  // 篇名那一塊（公開頁 zhuan_html.head 同一份標記）：裝飾、直書的篇名、底下一行季數
  function zhuanHead(title, sub) {
    return `<header class="zh-head"><div class="zh-orn" aria-hidden="true">${"<i></i>".repeat(6)}</div>
      <div class="zh-label" style="--slip-size:${slipSize(title)}px"><h1 class="zh-title">${esc(title)}</h1></div>
      <p class="zh-sub">${esc(sub)}</p></header>`;
  }
  // 名號的方印（陰刻）：四字兩行兩列、其餘一直行，右行先讀。zhuan_html.seal 同一條算法
  function zhuanSeal(name) {
    const chars = [...name].slice(0, 6);
    const n = chars.length, cols = n >= 4 ? 2 : 1, rows = Math.ceil(n / cols), cell = 40 / Math.max(rows, cols);
    const glyphs = chars.map((ch, k) => {
      const col = Math.floor(k / rows), row = k % rows;
      return `<text x="${(46 - (col + 0.5) * (40 / cols)).toFixed(1)}" y="${(6 + (row + 0.5) * (40 / rows)).toFixed(1)}" font-size="${(cell * 0.86).toFixed(1)}">${esc(ch)}</text>`;
    }).join("");
    return `<svg class="zh-seal" viewBox="0 0 52 52" role="img" aria-label="${esc(name)}"><rect x="2" y="2" width="48" height="48" rx="3"/><rect class="rim" x="5" y="5" width="42" height="42" rx="1.5"/>${glyphs}</svg>`;
  }
  function zhuanHtml(z) {
    const v = z.view;
    const head = v ? v.title : "列傳";
    const wait = (inner) => `<div class="zh-body"><section class="zh-panel zh-wait">${inner}</section></div>`;
    let body;
    if (!v) body = wait("<p>翻開史冊…</p>");
    else if (!v.written) {
      body = wait(v.writing
        ? '<p class="zh-ink" aria-hidden="true"><i></i><i></i><i></i></p><p>史官正在落筆，照你這一季的行狀寫一篇列傳。</p><p class="muted">大約一兩分鐘；可以先去別處，回來再翻。</p>'
        : v.can_write
          ? '<p>這一季的行狀已經收進史館。</p><button class="btn primary zhuan-go" data-act="zhuan-write">請史官落筆</button>'
          : "<p>這一季還不能寫傳。</p>");
    } else {
      const vertical = zhuanVertical();
      const { body: paras, ping } = zhuanText(v.paragraphs);
      const share = v.public
        ? `<p class="zh-url"><span>${esc(v.url || "")}</span></p>
           <div class="row"><button class="btn primary" data-act="zhuan-send">分享給朋友</button><button class="btn" data-act="zhuan-share" data-public="0">收回</button></div>
           <p class="muted">拿到網址的人不用登入就能讀；收回之後網址就失效。</p>`
        : `<button class="btn" data-act="zhuan-share" data-public="1">公開分享</button>
           <p class="muted">預設只有你看得到。公開之後會有一個網址，可以貼到 LINE、FB，隨時能收回。</p>`;
      // 開頭那一幅水墨（列傳插畫票，減法季批 7b）：公開分享頁早就畫了（zhuan_html 的 .zh-art），
      // 遊戲裡這一層以前漏了，買了的人在遊戲裡看不到（企劃者 2026-11-04 轉的玩家問「水墨在哪？」）。
      // 伺服器圖檔不在就不給 illustration_src（zhuan_art_src），所以這裡有才畫。
      const art = v.illustration_src
        ? `<figure class="zh-art"><img src="${esc(v.illustration_src)}" alt="${esc(head)}的插畫" loading="lazy"></figure>` : "";
      body = `<div class="zh-tools"><button data-act="zhuan-vertical" aria-pressed="${vertical}">直書</button></div>
        <div class="zh-body">${art}<article class="zh-text${vertical ? " vertical" : ""}">${paras}</article>${ping}<div class="zh-seals">${zhuanSeal(head.replace(/傳$/, ""))}</div>
        <section class="zh-panel">${share}</section>
        ${v.can_rewrite ? '<button class="zh-again" data-act="zhuan-rewrite">請史官重寫一次</button>' : ""}</div>`;
    }
    // 竹簡展開（Joy 2026-11-04）：寫成的傳第一次畫出來那一下才播（z.played），之後重畫（切直書、分享）不再播；點一下跳過（zh-skip）
    const play = v && v.written && !z.played ? " zh-play" : "";
    if (play) z.played = true;
    return `<div class="zhuan-layer zh zh-bamboo${play}" role="dialog" aria-label="${esc(head)}">
      <div class="zh-bar"><button data-act="zhuan-close" aria-label="返回">‹ 返回</button><span>列傳</span></div>
      ${zhuanHead(head, `第 ${Number(z.season)} 季${v && v.scenario ? `・${esc(v.scenario)}` : ""}`)}
      ${body}
    </div>`;
  }
  // 傳的正文（公開頁 zhuan_html.text 同一份標記）：第一段放大第一個字（first）；「評曰」那一段拆出正文、另起一塊蓋「評」字印
  function zhuanText(paragraphs) {
    const plain = paragraphs.filter((p) => !p.startsWith("評曰"));
    const ping = paragraphs.find((p) => p.startsWith("評曰"));
    return {
      body: plain.map((p, i) => `<p${i === 0 ? ' class="first"' : ""}>${esc(p)}</p>`).join(""),
      ping: ping ? `<aside class="zh-ping"><span class="chop">評</span><p>${esc(ping.replace(/^評曰[：:]?/, ""))}</p></aside>` : "",
    };
  }
  // 篇名的字照字數縮：名號最長十來個字，一律直書排進一條（四字以內 30px）。zhuan_html.slip_size 同一條算法
  const slipSize = (title) => Math.min(30, Math.floor(176 / [...title].length / 1.3));
  // 入口（江湖頁休季的那一張、行狀頁的歷季列傳）的小圖：一捆竹簡
  function zhuanIcon() {
    return '<svg viewBox="0 0 42 46" aria-hidden="true"><g fill="#d9b878" stroke="#6e4f29" stroke-width=".8">' + [4, 11, 18, 25, 32].map((x) => `<rect x="${x}" y="3" width="6" height="40" rx="1.5"/>`).join("") + '</g><path d="M1 12h40M1 34h40" stroke="#5a3e1d" stroke-width="2.2"/></svg>';
  }
  function zhuanEntry(b, sub, go = b.written === false ? "立傳" : "翻閱") {
    return `<button class="zh-entry zh-bamboo" data-act="zhuan-open" data-season="${Number(b.season)}">${zhuanIcon()}<span><b>${esc(b.title)}</b><small>${esc(sub)}</small></span><i class="go">${go} ›</i></button>`;
  }
  let zhuanTimer = 0;
  async function loadZhuan() {
    const z = S.zhuan;
    if (!z) return;
    clearTimeout(zhuanTimer);
    try { z.view = await api(`/api/zhuan?season=${Number(z.season)}`); } catch (e) { return; }
    if (S.zhuan !== z) return; // 等的時候闔上了、換了一季
    render();
    if (z.view.writing) zhuanTimer = setTimeout(loadZhuan, ZHUAN_POLL_MS);
  }
  async function zhuanPost(path, body) {
    const z = S.zhuan;
    try { z.view = await api(path, { season: z.season, ...body }); } catch (e) { return; }
    if (S.zhuan !== z) return;
    render();
    if (z.view.writing) { clearTimeout(zhuanTimer); zhuanTimer = setTimeout(loadZhuan, ZHUAN_POLL_MS); }
  }
  // 分享：手機上叫系統的分享選單，沒有就複製網址，再不行就選起來讓人自己複製
  async function zhuanSend() {
    const v = S.zhuan && S.zhuan.view;
    if (!v || !v.url) return;
    if (navigator.share) {
      try { await navigator.share({ title: v.title, url: v.url }); } catch (e) { /* 取消了 */ }
      return;
    }
    try { await navigator.clipboard.writeText(v.url); toast("網址已複製"); return; } catch (e) { /* 退回選取 */ }
    const span = document.querySelector(".zh-url span");
    if (span) { const r = document.createRange(); r.selectNodeContents(span); const sel = getSelection(); sel.removeAllRanges(); sel.addRange(r); }
    toast("長按網址複製");
  }

  // 見聞的「行狀」（玩家傳第一批，Game.annals_view）：新的在上；字都是伺服器存的原文，這裡跳脫。份量 4 以上的加一點朱紅
  function annalsHtml(a) {
    if (!a) return '<p class="muted">載入中…</p>';
    if (!a.on) return '<div class="card"><p class="muted">這一季不記行狀。</p></div>';
    const head = `<div class="card annals-head"><h3>${esc(a.name)}・行狀</h3><p class="muted">這一季值得寫進傳裡的事。季末收季時，會照這些寫成一篇《${esc(a.name)}傳》。</p></div>`;
    // 歷季列傳（第二批）：存著的每一季一本，排在這一季的行狀上面
    const books = (a.books || []).length ? `<div class="zh-books"><h3>歷季列傳</h3>${a.books.map((b) =>
      zhuanEntry(b, `第 ${Number(b.season)} 季・${b.written ? (b.public ? "已公開" : "已成篇") : "尚未成篇"}`)).join("")}</div>` : "";
    if (!a.rows.length) return head + books + '<div class="card"><p class="muted">還沒有記下什麼。上陣打一場大戰、跟英雄人物說幾句話，這裡就會有了。</p></div>';
    const row = (r) => `<li class="annal${r.weight >= 4 ? " heavy" : ""}">
        <div class="annal-meta"><span class="annal-kind">${esc(r.kind)}</span><span>${esc(r.when)}${r.place ? `・${esc(r.place)}` : ""}</span></div>
        <p class="annal-text">${esc(r.text)}</p>
        ${r.quote ? `<p class="annal-quote">你：「${esc(r.quote)}」</p>` : ""}
        ${r.reply ? `<p class="annal-reply">${r.figure ? `<b>${esc(r.figure)}</b>：` : ""}${esc(r.reply)}</p>` : ""}
      </li>`;
    return head + books + `<ol class="annals card">${a.rows.slice().reverse().map(row).join("")}</ol>`;
  }

  async function loadAnnals() {
    S.annals = await api("/api/annals");
    if (S.tab === "news") renderPage();
  }
  async function zhuanClick(act, el, ev) {
    switch (act) {
        case "zhuan-open":
          S.bookFrom = window.scrollY; S.zhuan = { season: Number(el.dataset.season), view: null }; render();
          await loadZhuan();
          break;
        case "zhuan-close": S.zhuan = null; clearTimeout(zhuanTimer); render(); window.scrollTo(0, S.bookFrom || 0); break;
        case "zhuan-write": await zhuanPost("/api/zhuan/write", { rewrite: false }); break;
        case "zhuan-rewrite":
          ask("請史官重寫一次：只能重寫一次，寫好之後換掉現在這一篇（公開的網址不變），確定？", "重寫", () => zhuanPost("/api/zhuan/write", { rewrite: true }));
          break;
        case "zhuan-share": await zhuanPost("/api/zhuan/share", { public: el.dataset.public === "1" }); break;
        case "zhuan-send": await zhuanSend(); break;
        case "zhuan-vertical":
          S.zhuanVertical = !zhuanVertical();
          try { localStorage.setItem(ZHUAN_VERTICAL, S.zhuanVertical ? "1" : "0"); } catch (e) { /* 存不了：只在這一頁有效 */ }
          render();
          break;
    } // zhuanClick
  } // zhuanClick
  registerClicks(zhuanClick, ["zhuan-open", "zhuan-close", "zhuan-write", "zhuan-rewrite", "zhuan-share", "zhuan-send", "zhuan-vertical"]);
