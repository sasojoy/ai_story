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

  const GATE_SLOTS = []; // 登入頁的格（identity，帳號與客服第 201 批）：包登記 registerGateSlot(fn)，renderGate 畫完叫 drawGateSlots，fn(gate, S) 自己改 .gate 那一塊
  function registerGateSlot(fn) { GATE_SLOTS.push(fn); } // 登入頁的格：登記
  function drawGateSlots(gate) { for (const fn of GATE_SLOTS) fn(gate, S); } // 登入頁的格：renderGate 畫完叫一次，一格一支照登記的先後

  // 紅點（Joy 2026-11-12「俠客那邊有紅點點 但是進去後 對應有紅點的事件應該也要標吧…以後事情可以不要只做一半嗎」）：
  // 一個來源登記一次 registerDot({ id, at, sub, on })——at 是第一層在哪（底部分頁的 id："news"、"practice"；或 "sheet"＝右上的 ⚙），
  // sub 是第二層（那一頁裡的子分頁 key：俠客頁的 S.heroTab「mates」、見聞的段「reports」；沒有子分頁的不給），on() 是現在亮不亮。
  // 第一層、第二層由殼照這張表畫（dotAt）；第三層（那一張卡、那一顆按鈕）由包自己畫 dotHtml(on)。看過之後 on() 變假，三層一起滅
  const DOTS = [];

  function registerDot(dot) {
    DOTS.push(dot);
  }

  function dotAt(at, sub) { // 這一處有沒有亮著的來源；sub 給了只算那一個子分頁的
    return DOTS.some((d) => d.at === at && (sub === undefined || (typeof d.sub === "function" ? d.sub() : d.sub) === sub) && (() => { try { return !!d.on(); } catch (e) { return false; } })());
  }

  // 一顆紅點的字：殼畫前兩層、包畫第三層（那一張卡、那一顆按鈕）都叫它
  const dotHtml = (on) => (on ? '<i class="dot" aria-hidden="true"></i>' : "");

  function paintDots() { // 輪詢、推送只重畫頁面不重畫分頁列與 ⚙：就地補上或拿掉第一層
    if (typeof document === "undefined" || typeof document.querySelectorAll !== "function") return;
    for (const b of document.querySelectorAll('.tabs .tab[data-tab]')) {
      const want = dotAt(b.dataset.tab), dot = b.querySelector(":scope > .dot");
      if (want && !dot) b.insertAdjacentHTML("beforeend", dotHtml(true));
      else if (!want && dot) dot.remove();
    }
    for (const b of document.querySelectorAll('[data-act="sheet"]')) {
      const want = dotAt("sheet"), dot = b.querySelector(":scope > .dot");
      if (want && !dot) b.insertAdjacentHTML("beforeend", dotHtml(true));
      else if (!want && dot) dot.remove();
    }
  }
