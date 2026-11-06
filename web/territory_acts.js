/* 天下大勢的網頁前端：見聞的〈天下形勢〉（全部拆包第 66 批從 app.js 切出來）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 */
"use strict";

  // 見聞「形勢」（領地爭奪第三批 A，企劃者挑乙）：一篇一行（「是日：…」＋時刻），最新一篇攤開、其餘點了攤開（<details>）；攤開、收起記在
  // S.xingshiOpen（篇次 → 開著沒），重畫照樣。文章是伺服器給的純文字（模型寫的或照固定段拼的，看不出差別），一段一個 <p>、照字跳脫。字待 joy 潤
  const XS_EMPTY = "天下尚無定論。";
  const XS_PENDING = "今日的形勢，史官還在落筆。";
  function xingshiParas(text) {
    return String(text || "").split(/\n+/).filter((p) => p.trim()).map((p) => `<p>${esc(p.trim())}</p>`).join("");
  }
  function xingshiHtml(x) {
    if (!x) return '<p class="muted">載入中…</p>';
    if (!x.on) return '<div class="card"><p class="muted">這一季沒有〈天下形勢〉。</p></div>';
    const open = S.xingshiOpen || (S.xingshiOpen = new Map());
    const pending = x.pending ? `<p class="muted xs-pending">${XS_PENDING}</p>` : "";
    if (!x.essays.length) return `<div class="card xs-card">${pending || `<p class="muted">${XS_EMPTY}</p>`}</div>`;
    const row = (e, i) => `<details class="xs-essay" data-n="${Number(e.n)}"${(open.has(e.n) ? open.get(e.n) : i === 0) ? " open" : ""}>
        <summary><span class="xs-line">${esc(e.line)}</span><span class="xs-time">${esc(e.time)}</span></summary>
        <div class="xs-body"><p class="xs-title">${esc(e.title)}</p>${xingshiParas(e.essay)}</div></details>`;
    return `<div class="card xs-card">${pending}${x.essays.map(row).join("")}</div>`;
  }

  async function loadXingshi() {
    S.xingshi = await api("/api/xingshi");
    if (S.tab === "news" && S.news === "xingshi") renderPage();
  }
