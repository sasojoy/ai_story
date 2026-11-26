/* 天下大勢的網頁前端：凌煙閣的入口（功能包 tianxia/features/lingyan/）。
 *
 * 閣本身是伺服器吐的一整頁（/lingyan）；這裡只畫見聞「江湖史」頂上那一張入口，伺服器在江湖畫面多一格 lingyan（開著才有）。
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。
 */
"use strict";

  const LY_SUB = "一季一卷，冠絕當世者名垂於此"; // 待 joy 潤
  function lingyanEntryHtml(m) {
    if (!m || !m.lingyan) return "";
    return `<a class="ly-entry" href="/lingyan"><span class="ly-entry-plaque" aria-hidden="true">凌煙閣</span>`
      + `<span class="ly-entry-text"><b>凌煙閣</b><small>${LY_SUB}</small></span><span class="ly-entry-go" aria-hidden="true">›</span></a>`;
  }
