/* 天下大勢的網頁前端：引導的發光與閃一閃、入伍段看過軍令、玩法說明與重看序章（全部拆包第 66 批從 app.js 切出來）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 */
"use strict";

  // 序章之後的「初入江湖」那幾步：跟序章一樣照 reveal 露出東西。
  const onb = () => (S.main && S.main.onboard) || null;

  // 序章的發光與閃一閃（新手引導計畫一）：m.prologue.glow 列的鍵，對到的鈕加 .glow（按得下去的才加，灰的不發光）；這一步新亮起來的
  // 元件（reveal 比上一次畫的多出來的）加 .lit 閃一下，一秒內重畫也還在。data-glow 寫的是鍵，可以寫好幾個（空白隔開，例：收著的
  // 武學列「改練 修練 熔煉」）。不在序章什麼都不加。每次畫完頁面、狀態列都呼叫，前一次的先清掉
  let litBefore = null, litKeys = [], litTimer = 0;
  const guideGlow = () => (S.main && S.main.guide && S.main.guide.glow) || [];
  // 發光的鈕收在關著的摺疊裡（入伍段第一道軍令那一步，玩家把「此地還能做」收起來了，FB-087 審查 M3）：看不到的鈕發光沒有意義，
  // 位置也量不到（「在下面 ↓」會當成整個在第一屏），光改給那個摺疊的標題列（同一個 .glow）；摺疊一打開，toggle 事件重跑 applyGlow，光回到鈕上
  function glowTarget(el) {
    const closed = el.closest("details:not([open])");
    return (closed && closed.querySelector(":scope > summary")) || el;
  }
  function applyGlow() {
    document.querySelectorAll(".glow, .lit").forEach((el) => el.classList.remove("glow", "lit"));
    // 入伍段「出一次力」（FB-093）：伺服器在框上帶了能完成它的那幾顆選項的 id（guide.glow），序章外也亮；收在關著的摺疊裡的，
    // 光給摺疊的標題列（glowTarget）
    guideGlow().forEach((id) => document.querySelectorAll(`#page [data-id="${CSS.escape(id)}"]:not([disabled])`).forEach((el) => glowTarget(el).classList.add("glow")));
    // 約戰卡的「前往」、新手目標的「去做」展開移動後往那一處的那一條（FB-9001）：上面清掉了所有 .glow，這裡補回；序章裡也不例外
    const route = routeGlowKey();
    if (route) (S.main.options || []).filter((o) => routeHit(o.id, route)).forEach((o) => document.querySelectorAll(`#page .act-move [data-id="${CSS.escape(o.id)}"]`).forEach((el) => el.classList.add("glow")));
    const p = pro() || onb();
    if (!p) {
      litBefore = null;
      litKeys = [];
      guideCue(); // 發光的鈕在「此地還能做」摺疊裡、整個落在分頁列底下時，框上也要有「在下面 ↓」（FB-W1）
      return;
    }
    const fresh = litBefore ? p.reveal.filter((k) => !litBefore.includes(k)) : [];
    litBefore = p.reveal.slice();
    if (fresh.length) {
      litKeys = fresh;
      clearTimeout(litTimer);
      litTimer = setTimeout(() => { litKeys = []; }, 1000);
    }
    p.glow.forEach((key) => document.querySelectorAll(`[data-glow~="${key}"]:not([disabled])`).forEach((el) => glowTarget(el).classList.add("glow")));
    litKeys.forEach((key) => document.querySelectorAll(`[data-glow~="${key}"]`).forEach((el) => el.classList.add("lit")));
    applyFocus();
    guideCue();
  }

  // 新手引導（序章與初入江湖）有東西在發光時，跟這一步無關的區域整片壓暗（Joy 2026-10-17）：留亮的是發光的那幾顆、引導的框與它們的
  // 祖先，祖先的其他孩子壓暗（.onb-dim）；狀態列、頁面、分頁列裡整塊沒有要亮的東西就整塊壓暗。店面、抽屜這些疊在上面的不碰。
  // 沒有東西在發光（眼前是事件、框收著的那一句）不壓
  function applyFocus() {
    document.querySelectorAll(".onb-dim").forEach((el) => el.classList.remove("onb-dim"));
    const roots = [document.getElementById("top"), document.getElementById("page"), document.querySelector("nav.tabs")].filter(Boolean);
    const lit = roots.flatMap((r) => [...r.querySelectorAll(".glow")]);
    if (!(pro() || onb()) || !lit.length) return;
    const whole = new Set([...lit, ...document.querySelectorAll("#page .card.guide")]); // 這幾塊底下整塊亮著
    const keep = new Set();
    whole.forEach((el) => { for (let n = el; n && n !== document.body; n = n.parentElement) keep.add(n); });
    // 整塊沒有要亮的：壓暗它的孩子，不壓它自己——狀態列與分頁列是黏在畫面上、有底色的，整條變半透明會透出底下捲過去的字
    roots.forEach((r) => { if (!keep.has(r)) [...r.children].forEach((c) => c.classList.add("onb-dim")); });
    keep.forEach((n) => {
      if (whole.has(n) || !roots.some((r) => r.contains(n))) return;
      [...n.children].forEach((c) => { if (!keep.has(c)) c.classList.add("onb-dim"); });
    });
  }

  // 要按的東西沒有整個露在第一屏裡（修練頁的改練那一列在 y≈1300，或只露出幾 px 被分頁列蓋住）時，師父的框上多一個小小的
  // 「在下面 ↓」，點了捲到那裡（T7 審查 M7）。整個看得到＝它的底邊在分頁列的頂邊或以上（以前看頂邊離分頁列 8px 以上就算看得到：
  // 步驟 4 煉製頁的挑選清單在 747～813、分頁列 756，只露 9px，玩家看不到、也沒有提示）。
  // 只看頁面裡（#page）第一個發光的東西：分頁列與狀態列的鈕永遠在畫面上。序章，以及框上帶 glow 的框（入伍段第一道軍令那一步，
  // FB-W1；提示框不發光，沒有目標就沒有）；每次畫完頁面重算（applyGlow 呼叫），
  // 視窗大小變了（轉向、拉視窗）也重算（resize 的去抖，見檔案最後那個 resize 監聽，T7 走查 W-F）；捲動不重算
  function guideCue() {
    const head = document.querySelector(".card.guide .guide-head");
    if (!head) return;
    const old = head.querySelector(".guide-below");
    if (old) old.remove();
    const target = (pro() || onb() || guideGlow().length) && document.querySelector("#page .glow");
    if (!target) return;
    const bar = document.querySelector(".tabs");
    const limit = bar ? bar.getBoundingClientRect().top : window.innerHeight;
    if (target.getBoundingClientRect().bottom <= limit) return; // 要按的東西整個都在第一屏裡
    head.firstElementChild.insertAdjacentHTML("afterend", '<button class="linkish guide-below" data-act="guide-below">在下面 ↓</button>');
  }
  function scrollToGuideTarget() {
    const target = document.querySelector("#page .glow");
    if (target) target.scrollIntoView({ block: "center", behavior: "smooth" });
  }

  // ── 入伍段第一步（新手引導計畫二，preflight F5）：軍令卡真的在畫面上才算看過 ──
  // 框是引薦人的第一步（key 是 r2_briefing；伺服器要等序章走完、引薦人的框輪到了才送這個 key）時，軍令卡在行動列底下。手機上第一屏放不下它，
  // 一畫出來就送的話，引薦人那段話還沒讀就被換成下一步。所以等卡片至少一半進了畫面、停留 ORDERS_SEEN_MS，才送一次 view_orders；
  // 捲走了就重新計時。整頁重畫（輪詢內容一變就會）把 IntersectionObserver 重掛到新的那張卡片上，已經在跑的計時不因為重畫重來。
  // 瀏覽器沒有 IntersectionObserver 時退回「畫出來之後 ORDERS_SEEN_MS」；分頁在背景時計時走完不送、過一輪再看。
  // 「在畫面上」不含被固定的兩條蓋住的部分：觀察的範圍扣掉頂上的狀態列（#top）與底部的分頁列（.tabs）的高度；設定抽屜開著時不看。
  // 送出去的記在 S.ordersSeen（不重送）；送不出去就還回去，隔 ORDERS_RETRY_MS 再試一次（api 每次失敗都跳提示，不連著試；
  // 再失敗就等下一次重畫或捲動）；這一步過了就清掉，下一季輪到它再送。
  const ORDERS_SEEN_MS = 1500;
  const ORDERS_RETRY_MS = 5000;
  function stopOrdersTimer() {
    clearTimeout(S.ordersTimer);
    S.ordersTimer = null;
  }
  function resetOrdersWatch() { // 登入、換角色、登出
    if (S.ordersObs) S.ordersObs.disconnect();
    S.ordersObs = null;
    stopOrdersTimer();
    S.ordersSeen = false;
    S.ordersVisible = false;
    S.ordersRetried = false;
  }
  function sendOrdersSeen() {
    S.ordersTimer = null;
    const g = S.main && S.main.guide;
    if (!g || g.key !== "r2_briefing" || S.ordersSeen) return;
    if (S.ordersObs && !S.ordersVisible) return; // 計時走完時觀察者說卡片已經不在畫面上了：不送
    if (document.hidden) { S.ordersTimer = setTimeout(sendOrdersSeen, ORDERS_SEEN_MS); return; }
    S.ordersSeen = true;
    api("/api/do/view_orders", {}).then((r) => { S.ordersRetried = false; applyMain(r.main); }).catch(() => {
      S.ordersSeen = false;
      if (!S.ordersRetried && S.ordersTimer == null) { S.ordersRetried = true; S.ordersTimer = setTimeout(sendOrdersSeen, ORDERS_RETRY_MS); }
    });
  }
  function watchOrders() {
    if (S.ordersObs) S.ordersObs.disconnect(); // 整頁重畫換了卡片：舊的 observer 看的是已經不在頁面上的那一張
    S.ordersObs = null;
    const g = S.main && S.main.guide;
    const first = !!g && g.key === "r2_briefing";
    if (!first) S.ordersSeen = false;
    const card = first && !S.ordersSeen && !S.sheet && S.tab === "jianghu" ? document.querySelector("details.orders") : null;
    if (!card) { stopOrdersTimer(); return; }
    const arm = () => { if (S.ordersTimer == null) S.ordersTimer = setTimeout(sendOrdersSeen, ORDERS_SEEN_MS); };
    if (typeof IntersectionObserver === "undefined") { arm(); return; }
    const inset = (sel) => { const bar = document.querySelector(sel); const px = bar ? Math.ceil(bar.getBoundingClientRect().height) : 0; return px ? `-${px}px` : "0px"; };
    const obs = new IntersectionObserver((entries) => {
      if (S.ordersObs !== obs) return; // 已經換掉的觀察者晚到的回報（disconnect 不會清掉排好的）：不管
      const e = entries[entries.length - 1];
      S.ordersVisible = !!e.isIntersecting && e.intersectionRatio >= 0.5;
      if (S.ordersVisible) arm(); else stopOrdersTimer();
    }, { threshold: 0.5, rootMargin: `${inset("#top")} 0px ${inset(".tabs")} 0px` });
    S.ordersObs = obs;
    obs.observe(card);
  }

  // 設定頁的「重看序章」：序章的文字是內容、不會變，同一次載入只問一次。沒有序章的內容回空字串，就不畫那顆鈕
  // 設定抽屜的「玩法說明」（explain-1）：伺服器照設定與這一季寫好的一頁（/api/howto，已經是跳脫過的 HTML）。每次攤開都再問一次
  // （一個 GET、按了才問；換季、第一季的開關換了說明跟著對，審查 M5），問的時候卡上先放著上一次要到的那一頁。要不到（連不上、
  // 伺服器出錯）就記 howtoFailed，卡上寫一句、給「再試一次」。晚回來的舊請求（後面又問了一次、已經登出）不算：回傳 false
  async function loadHowto() {
    const seq = ++S.howtoSeq;
    S.howtoFailed = false;
    let text = null;
    try { text = (await api("/api/howto")).text || ""; } catch (e) { text = null; }
    if (seq !== S.howtoSeq) return false;
    if (text === null) S.howtoFailed = true;
    else S.howto = text;
    return true;
  }
  // 登出、換帳號：上一個人的那一頁與開合都不留，還在路上的請求也不算
  function forgetHowto() {
    S.howto = undefined;
    S.howtoOpen = false;
    S.howtoFailed = false;
    S.howtoSeq += 1;
  }
  // 問一次玩法說明：先畫出「正在翻書……」（或上一次那一頁），回來了（而且抽屜與這張卡還開著）再畫；抽屜停在原地
  async function refreshHowto() {
    renderKeepingSheet();
    if (await loadHowto() && S.sheet && S.howtoOpen) renderKeepingSheet();
  }

  async function loadRecap() {
    if (S.recap !== undefined) return;
    try { S.recap = (await api("/api/prologue")).text || ""; } catch (e) { return; } // 問不到：下次打開設定再問
    if (S.sheet) renderKeepingSheet();
  }
