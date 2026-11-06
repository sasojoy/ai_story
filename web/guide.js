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

  // 要發光的那一條路（FB-9001，QA 2026-10-28）：約戰卡別區那一行的「前往 N 分」、新手目標的「去做」展開移動之後，往那一處的那一條發光。
  // 記在 S.glowRoute（move:<地點>）：畫移動卡時直接寫進 class（routeGlowOn），applyGlow 清掉所有 .glow 之後也補回（routeGlowKey），
  // 所以重插的摺疊觸發 toggle、輪詢重畫都不會把光清掉（以前展開之後 .glow 直接加在畫好的元素上，24 毫秒內的 toggle 或下一次重畫就沒了）。
  // 什麼時候熄掉（都在重畫時判斷，不設計時器）：移動卡收起或換別格（S.wheelSel 不是 move；按了選項送出去之後 choose 也會收起移動卡）、
  // 換分頁、移動清單上沒有那一條了（走了、換了地方）
  const routeHit = (id, key) => id === key || id.startsWith(`${key}:`); // 疾行的 id 後面多接走法
  function routeGlowKey(m = S.main) {
    const key = S.glowRoute;
    if (!key) return "";
    const live = S.tab === "jianghu" && S.wheelSel === "move" && !!m && (m.options || []).some((o) => routeHit(o.id, key));
    if (!live) S.glowRoute = null;
    return live ? key : "";
  }
  function routeGlowOn(m, id) {
    const key = routeGlowKey(m);
    return !!key && routeHit(id, key);
  }

  // 新手目標（新手引導重做；tianxia/newbie.py，status.newbie）：引導走完、新手期裡收進這一排小標，攤開一次三條、每一條有「去做」。
  // 「去做」：go.tab 切到那一頁；go.move 是最近的那一處，移動清單上有那一條就展開移動、讓它發光，沒有就打開輿圖。字待 joy 潤
  const NEWBIE_GO = "去做", NEWBIE_DRIFTER = "就當散人";
  function newbiePeek(m) {
    const n = m.status && m.status.newbie;
    if (!n || !n.rows.length) return null;
    const rows = n.rows.map((r, i) => `<li class="nb-goal"><div><b>${esc(r.text)}</b><small>${esc(r.reward)}${r.go.place ? `・最近在${esc(r.go.place)}` : ""}</small></div>`
      + `<span class="nb-btns"><button class="btn small" data-act="newbie-go" data-i="${i}">${NEWBIE_GO}</button>`
      + `${r.drifter ? `<button class="btn small" data-act="newbie-drifter">${NEWBIE_DRIFTER}</button>` : ""}</span></li>`).join("");
    return {
      id: "newbie",
      label: `${n.title}：做到 ${n.done}／${n.total}`,
      chip: `<span class="peek-name">新手</span><span class="peek-nums">${n.done}/${n.total}</span>`,
      flag: true,
      dotNote: "",
      panel: `<ol class="nb-goals">${rows}</ol>`,
    };
  }
  function newbieGo(i) {
    const r = S.main && S.main.status && S.main.status.newbie && S.main.status.newbie.rows[i];
    if (!r) return;
    if (r.go.tab) { if (r.go.tab !== S.tab) goTab(r.go.tab); else window.scrollTo({ top: 0, behavior: "smooth" }); return; }
    const id = `move:${r.go.move}`, hit = (x) => x === id || x.startsWith(`${id}:`); // 疾行的 id 後面多接走法
    if (!S.main.options.some((o) => hit(o.id))) { mapGoto(r.go.move); goTab("map"); return; }
    S.wheelSel = "move";
    S.glowRoute = id; // 往那一處的那一條發光：記在狀態裡，重畫、摺疊 toggle 都保得住（FB-9001）
    renderPage();
    revealMoveCard();
  }

  // 說書人的對話框（引導重做設計 8.1、6.2）：行動列（或事件的選項）上方，框上寫說話的人（之後換成師父、引薦人）。
  // 做完一步先列「✔ 完成」與獎勵，再接下一步的話。可以收起成一行；記的是收起的那一句，換了下一句就自己展開。
  // 結語有「知道了」，按了就不再出現。在路上預設收成一行（FB-055）：框、走法與路上的五個選項擠不進第一屏，折返被分頁列蓋住；
  // 路上展開的記在 S.guideRoad（記的是那一句，下了路就清掉），輪詢重畫不會把它收回去（事件待處理的那一句也一樣，見 openGuide）
  const GUIDE_KEY = "tx-guide-shut";
  function guideShut() { try { return localStorage.getItem(GUIDE_KEY); } catch (e) { return null; } }
  function setGuideShut(text) { try { if (text) localStorage.setItem(GUIDE_KEY, text); else localStorage.removeItem(GUIDE_KEY); } catch (e) { /* 存不了就只在這一頁有效 */ } }
  // 收起記的是「哪一步」（伺服器給的 key：步驟的 id），不是那一句話（FB-076）：眼前有事件時框上的話換成「先把眼前的「…」了結」，
  // 每遇到新事件就換一句；記句子的話，收起的框每個新事件都會自己又展開，事件的最後一個選項就被擠出第一屏。
  // 換到下一步（新的 key）才照舊展開。舊版伺服器沒有 key 時退回認句子
  function guideKey(g) { return g && (g.key || g.text); }
  // 「先把眼前的「…」了結」那一句（伺服器標 pending）預設收成一行，玩家沒按過「收起」也一樣（FB-076，控制者裁示）：它只是重複底下
  // 事件卡片已經寫的話，展開時事件的最後一個選項被擠到分頁列底下。跟在路上一樣，點開的記在 S.guideRoad（記的是那一句，
  // 換成下一個事件的句子就又收著，了結之後清掉）；只有這一句，新的一步照舊展開
  function shutGuide(g) { setGuideShut(guideKey(g)); S.guideRoad = null; }
  function openGuide(g) { setGuideShut(null); S.guideRoad = g && g.text; }
  // 分頁的步驟（伺服器標 paged，T7 審查 I1）：師父的話照 \n\n 切成幾頁，一次一頁、按「下一段 ▸」往下，最後一頁帶著要做的事；
  // 每一頁都是整段，不切。記的是（哪一步, 第幾頁），換到下一步自己回到第一頁
  const guidePages = (g) => (g.paged ? g.text.split(/\n{2,}/) : [g.text]);
  const guidePage = (g) => (S.guidePage && S.guidePage.key === guideKey(g) ? Math.min(S.guidePage.n, guidePages(g).length - 1) : 0);
  function nextGuidePage(g) { S.guidePage = { key: guideKey(g), n: Math.min(guidePage(g) + 1, guidePages(g).length - 1) }; }
  // 但框上還有「✔ 引導完成」與獎勵（done）要讓玩家看到時不收：「剛剛」卡片依設計不放引導，收成一行那一列就沒地方看了
  // （新角色的第一次探索常常做完第一步又留下事件）；那時照舊展開。FB-076 量的那一場（遊歷打完接事件）done 是空的
  // 決戰集結的時候（場景裡有集結的倒數）入伍、步驟的框也預設收成一行（企劃者 2026-10-08，FB-107 修正輪）：場景多了戰場那一段、
  // 加入的鈕、此地還有，入伍段分頁攤開的框把行動列擠到分頁列底下（長社官軍量到 796）。點開的照在路上記在 S.guideRoad（那一句本身），
  // 輪詢時倒數在變也不收回去；自己按「收起」或集結結束才不算。序章裡師父的框不收（設計 6.2）。
  // 「知道了」的框（碰到才說、結語）集結時也收成一行，點開才有「知道了」：潁水河畔打完一場＋內傷框、別的大區在集結，控制者量到
  // 762～784，收了集結那一句還是放不下（裁示見交接報告）。在路上的「知道了」框照舊攤開（路上另有排法）
  const MUSTER_SCENE = /集結(中，)?還剩現實/; // engine._battle_scene_text 集結那一段的寫法（還沒加入、加入了、觀戰都有）
  const guideMuster = () => !!(S.main && MUSTER_SCENE.test(S.main.scene || "")) && !pro();
  function guideHtml(g, onRoad) {
    // 分頁記的是（哪一步, 第幾頁）：框換成別一步、或整個框不在了，就清掉。不然換季回草廬重走一遍，走到那一步又直接開在舊的那一頁（T7 審查 N3）
    if (S.guidePage && (!g || S.guidePage.key !== guideKey(g))) S.guidePage = null;
    const quiet = !!(g && g.pending && !g.done.length); // 事件待處理的那一句、而且沒有要看的完成列：預設收成一行
    const muster = !onRoad && guideMuster(); // 決戰集結中：框預設收成一行（「知道了」的框也是）
    if (!onRoad && !quiet && !muster) S.guideRoad = null; // 沒有框、也不是這三種預設收著的時候要清（FB-055）
    if (!g) return "";
    const folded = muster || ((onRoad || quiet) && !g.end); // 預設收著（點開的記在 S.guideRoad）
    if ((!g.end && guideShut() === guideKey(g)) || (folded && S.guideRoad !== g.text)) {
      // 收起來那一行：序章的步驟自己寫了短的一行（g.line，例：「回『江湖』按『探索』」，說話的人由這裡寫在前面、line 不重複）就用它，
      // 不然是這一句話；
      // 記著收起的是步驟的 key（guideKey，FB-076），換到下一步自己展開
      return `<button class="guide-line" data-act="guide-open" aria-label="展開${esc(g.speaker)}的話"><b>${esc(g.speaker)}</b>：${esc(g.line || g.text)}</button>`;
    }
    const done = g.done.length ? `<div class="guide-done">${g.done.map((d) => d.startsWith("✔")
      ? '<span class="ok">✔ 完成</span>' : `<span class="reward">${esc(d)}</span>`).join("")}</div>` : "";
    // 序章以外（Joy 2026-10-26：師父的話排在行動列底下）右上角一顆 ×：做的事同「知道了」（g.end）／「收起」
    const btn = !pro() ? `<button class="wk-x guide-x" data-act="${g.end ? "guide-ack" : "guide-shut"}" aria-label="${g.end ? "知道了" : "收起"}" title="${g.end ? "知道了" : "收起"}">×</button>`
      : g.end ? '<button class="btn small" data-act="guide-ack">知道了</button>'
      : '<button class="linkish" data-act="guide-shut">收起</button>';
    // 長的那幾步（軍令兩步一百多字）先露三行、點了看全文，不把行動與選項擠出第一屏（畫面批次審查 I3）
    // 序章裡師父的話不切（設計 6.2「話不會被切掉」，T7 審查 I1）：不收成三行；段落照 \n\n 排（樣式表 pre-line）。
    // 入伍段引薦人的話也一樣（設計 6.2 寫的就是「序章與入伍段」）：伺服器給 full，不收；兩段以上的那一步另外給 paged（照上面的分頁）
    const full = !!pro() || !!g.full || S.guideFull === g.text;
    const pages = guidePages(g), page = guidePage(g);
    const scene = g.scene && page === 0 ? `<p class="guide-scene">${esc(g.scene)}</p>` : ""; // 序章的旁白（「斷眉來了……」）排在話的前面（分頁的步驟只在第一頁）
    const next = page < pages.length - 1 ? '<button class="linkish guide-next" data-act="guide-next">下一段 ▸</button>' : "";
    return `<section class="card guide" aria-label="${esc(g.speaker)}的話"><div class="guide-head"><b>${esc(g.speaker)}</b>${btn}</div>${done}${scene}<p class="guide-text${full ? "" : " clamp"}" data-act="guide-more" role="button" tabindex="0" aria-expanded="${full}">${esc(pages[page])}</p>${next}</section>`;
  }

  // 序章裡師父的話也放在修練頁、煉製頁最上面（序章的第 4～6、9、10 步在這兩頁做，不用切回江湖頁看要做什麼）；序章外不畫。
  // 碰到才說的提示（伺服器標 hint）也畫在這兩頁最上面：修練失敗、改練、合成、熔煉都是在這兩頁做的，提示在做完的那一下上框、記進紀錄，
  // 不畫的話玩家要切回江湖頁才看得到（新手引導計畫三，T1 審查 I-1）。同一個框、同一顆「知道了」；說書人的步驟、結語、入伍段的框仍只在江湖頁
  const proGuide = () => (pro() || (S.main.guide && S.main.guide.hint) ? guideHtml(S.main.guide, false) : "");
