/* 天下大勢的網頁前端：殼的掛鉤（全部拆包第 64 批；開發規範手冊 3.7、G9）。
 *
 * 最先載入：功能包的檔（web/<包>.js）一載入就叫 registerPage，app.js 排在最後，所以掛鉤不能放 app.js。
 * 跟 mall.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成
 * （tianxia/core/features.py 的 WEB_ORDER、web_scripts）。
 */
"use strict";

  // 分頁的畫法：包登記自己的分頁（registerPage("craft", { render: pageCraft })），app.js 的 renderPage 查不到自己那張表就問這裡
  const PAGES = {};

  function registerPage(name, page) {
    PAGES[name] = page;
  }
