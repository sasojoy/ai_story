/* 天下大勢的網頁前端：酒肆裡的招募同伴（全部拆包第 67 批從 main.js 切出來）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 */
"use strict";

  // 酒肆裡的招募（介面重整：招募從此地搬進酒肆）：先出酒肆（tavern:back）再按 hire:<id>，跟按選單上那一顆一樣
  const HIRE_HEAD = "招募同伴"; // 待 joy 潤
  const HIRE_NOTE = "招了就跟你出酒肆上路。"; // 待 joy 潤
  function tavHireHtml() {
    const list = uiV2() ? (S.main && S.main.hires) || [] : []; // 伺服器坐在酒肆裡才給（tianxia/features/hire 的 status）
    if (!list.length) return "";
    return `<h4 class="tav-h">${HIRE_HEAD}<small>${HIRE_NOTE}</small></h4><div class="options tav-hire">${list.map((o) =>
      `<button class="btn" data-act="tav-hire" data-id="${esc(o.id)}" ${o.enabled ? "" : "disabled"}><span>${dealHtml(o.label)}</span></button>`).join("")}</div>`;
  }
  async function tavHire(id) {
    let ok = false;
    await busy(async () => { const r = await api("/api/choose", { id: "tavern:back" }); applyMain(r.main); ok = true; });
    if (!ok || !(S.main.options || []).some((o) => o.id === id)) { renderPage(); return; }
    renderPage();
    await choose(document.querySelector(`[data-id="${CSS.escape(id)}"]`) || document.body, id);
  }
