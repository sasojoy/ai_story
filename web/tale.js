/* 天下大勢的網頁前端：戰報頁的戰記連結、戰記那一層與目錄（全部拆包第 66 批從 app.js 切出來）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 */
"use strict";

  // 戰記（Joy 2026-10-29 先叫「戰役話本」，同日改名「戰記」；版面照主機那份 長社火攻話本）：戰報頁「‹ 全部戰報」那一行右邊一顆「戰記 ›」。
  // 寫好了（ready）才按得下去；還在寫（pending）灰掉寫「史官還在落筆」；沒有（none、還沒問到、不是決戰）不畫。標題一律「<戰名>戰記」
  const taleName = (name) => (name && !String(name).endsWith("戰記") ? `${name}戰記` : String(name || ""));
  function taleLink(id) {
    const t = id == null ? null : S.tales[id];
    if (!t || t.status === "none") return "";
    if (t.status === "pending") return '<button class="linkish huaben-link" disabled>史官還在落筆</button>';
    return `<button class="linkish huaben-link" data-act="tale" data-id="${id}">戰記 ›</button>`;
  }
  // 戰記頁（Joy 2026-11-04「獨立一頁，做漂亮一些」、可以分享）：寫好了就疊一層全螢幕，開伺服器畫的那一頁（/zhanji/<代碼>?in=1，
  // 分享出去的也是同一頁、標記只有 tale_html.py 一份）；那一頁頂條的「‹ 返回」用 postMessage 叫這裡收起來（taleClose）
  function taleHtml(t) {
    const back = `<button class="linkish back" data-act="tale-back">‹ ${S.news === "chronicle" ? "江湖史" : "戰報"}</button>`;
    if (!t) return `${back}<p class="muted">載入中…</p>`;
    if (t.status !== "ready" || !t.page) return `${back}<div class="card"><p class="muted">${t.status === "pending" ? "史官還在落筆，過一會兒再來。" : "這一場沒有戰記。"}</p></div>`;
    return `${back}<div class="zj-layer"><iframe src="${esc(t.page)}" title="${esc(taleName(t.battle_name || t.title))}" allow="web-share; clipboard-write"></iframe></div>`;
  }
  function taleClose() {
    if (S.taleOpen == null) return;
    S.taleOpen = null; renderPage(); window.scrollTo(0, 0);
  }
  // 江湖史最上面的戰記目錄（main.tales，伺服器的開關關著是空的、不畫）
  function taleIndexHtml(list) {
    if (!list || !list.length) return "";
    return `<p class="report-group">戰記</p><div class="list huaben-index">${list.map((x) => `<button data-act="tale" data-id="${x.battle_id}">${esc(taleName(x.title))}<span class="muted small">${x.season ? `第 ${x.season | 0} 季` : ""}${x.result ? `・${esc(x.result)}` : ""}</span></button>`).join("")}</div>`;
  }

  // 戰記（/api/tale/<流水號>）：寫好了（ready）留著不再問；還在寫（pending）每次打開戰報都再問一次
  async function loadTale(id) {
    const had = S.tales[id];
    if (had && had.status === "ready") return;
    S.tales[id] = await api(`/api/tale/${id}`);
    if (S.tab === "news") renderPage();
  }
  async function taleClick(act, el, ev) {
    switch (act) {
        case "tale": {
          // 戰報頁的「戰記 ›」、江湖史的目錄：打開那一篇（還在寫、沒有的不畫成鈕，這裡不必再擋）
          const id = Number(el.dataset.id);
          S.taleOpen = id;
          if (S.tab !== "news") { S.tab = "news"; S.unseen = false; render(); } else renderPage();
          window.scrollTo(0, 0);
          await loadTale(id);
          break;
        }
        case "tale-back": S.taleOpen = null; renderPage(); window.scrollTo(0, 0); break;
    } // taleClick
  } // taleClick
  registerClicks(taleClick, ["tale", "tale-back"]);
