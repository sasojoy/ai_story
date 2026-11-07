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

  // 點擊分派：包登記自己認的 data-act（registerClicks(mapClick, ["map-home", …])），app.js 的 click 監聽查到就交給它，查不到才走殼自己的 switch
  const CLICKS = Object.create(null); // 沒有原型：data-act 是 constructor 這種字也查不到，跟 switch 一樣什麼都不做

  function registerClicks(fn, acts) {
    for (const act of acts) CLICKS[act] = fn;
  }

  // 表單分派：包登記自己認的表單（registerForms(tavernForm, ["tav-ask", …])），不照 id 認的寫 "op:<data-op>"；app.js 的 submit 監聽查到就交給它，查不到才走殼自己那條 else-if
  const FORMS = Object.create(null);

  function registerForms(fn, keys) {
    for (const key of keys) FORMS[key] = fn;
  }

  // change 分派：包登記一支（registerChanges(notifyChange)），裡面照舊自己比 ev.target；app.js 的 change 監聽每一支同步叫一次（一個元素只有一包認）
  const CHANGES = [];

  function registerChanges(fn) {
    CHANGES.push(fn);
  }
