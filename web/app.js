/* 天下大勢的網頁前端：沒有建置步驟、不靠外部函式庫。
 *
 * 畫面只有三種：登入、取名號、遊戲。遊戲畫面 = 頂上的狀態列 + 一頁內容 + 底部五個分頁：
 *   江湖（場景與選項）、俠客（人像與裝備、武學、屬性、煉製與自創的入口、功法庫與門下）、煉製（太極火爐：意境＋意境）、
 *   輿圖、見聞（戰報、大勢、傳聞、江湖史、紀錄）。商城開著時多第六格「商城」與齒輪旁的錠子鈕，都打開商城那一層（不是一頁）。
 * 設定與管理者工具收在右上角的抽屜裡。
 *
 * 伺服器給的 HTML（場景、角色卡、戰報、江湖紀錄、地圖）已經在伺服器端跳脫過；
 * 這裡自己組的字串一律經過 esc()。
 *
 * 網頁分三個檔（減法季批 0，企劃者 2026-10-24）：main.js（江湖頁）、map.js（輿圖）、app.js（其餘與啟動），index.html 照這個順序載入。
 * 三個檔都是一般的 <script>、頂層的名字同在一個全域裡互相看得到（以前整支包在一個 IIFE 裡）；app.js 最後才載、最後一行才啟動，
 * 所以 main.js、map.js 頂層只放宣告，載入當下不呼叫 app.js 裡的東西。縮排照舊留兩格（測試照「兩格縮排」切函式）。
 */
"use strict";

  // 底部分頁 6 改 4（減法季批 1，整合設計 6.5）：江湖、俠客、輿圖、見聞；商城從右上角的錠子鈕進。「俠客」（Joy 2026-10-24：「俠客」太直白）@@KEEP@@
  // 是修練頁（practice）加上從它底下進去的煉製頁（craft）——兩頁的 id 照舊（序章的 tab:practice、tab:craft，看過:practice 的旗標、測試都認它），
  // 分頁列上只有一格
  const TABS = [
    { id: "jianghu", ico: "江", name: "江湖" },
    { id: "practice", ico: "俠", name: "俠客", also: ["craft"] },
    { id: "map", ico: "圖", name: "輿圖" },
    { id: "news", ico: "聞", name: "見聞" },
  ];
  // 見聞 9 籤改 5（6.5 寫四籤；Joy 2026-10-24「榜單放俠客頁很奇怪」）：大事（戰報＋大勢＋形勢，底下再分）、傳聞、榜單、江湖史、
  // 紀錄（自己的紀錄＋名帖匣，底下再分）。行狀是自己的傳，從「俠客」頁人像那張卡進（SELF_NEWS），頁面照舊是見聞那一頁的同一段
  // （S.news 認得它），只是籤不排在見聞上
  const NEWS = [
    { id: "reports", name: "大事", parts: ["reports", "trends", "xingshi"] },
    { id: "rumors", name: "傳聞" },
    { id: "boards", name: "榜單" }, // 企劃者 2026-10-14，/api/boards
    { id: "chronicle", name: "江湖史" },
    { id: "journal", name: "紀錄", parts: ["journal", "mingtie"] },
  ];
  // 籤底下再分的一排小的（newsSegHtml）：大事分戰報、大勢、形勢（形勢只有開著的季〔main.xingshi〕才畫）；紀錄分紀錄、名帖匣（Joy 2026-10-19，/api/mingtie）
  const NEWS_PARTS = [
    { id: "reports", name: "戰報" },
    { id: "trends", name: "大勢" },
    { id: "xingshi", name: "形勢" }, // 領地爭奪第三批 A：每天一篇〈天下形勢〉（/api/xingshi）
    { id: "journal", name: "紀錄" },
    { id: "mingtie", name: "名帖匣" },
  ];
  // 從「俠客」頁進去的那一段（以前是見聞的籤）：行狀（玩家傳第一批，/api/annals）
  const SELF_NEWS = [
    { id: "annals", name: "行狀" },
  ];
  const POLL_MS = 10000;
  // 江湖頁「前往」的走法（跟 atlas.MODES 同一份）。選的走法只放在 S.moveMode：不寫進 localStorage、cookie，
  // 重新整理頁面就回到步行；每個請求都帶著它（見 api()），伺服器照它排選單上的「前往」
  const FREE_TEXT_OPTION = "choice:free"; // 事件的隨口應對（engine.FREE_TEXT_OPTION）
  const SAY_OPTION = "talk:say"; // 跟人物對話時的「自己說」（engine.SAY_OPTION）：按了叫出輸入框，送出走 /api/say
  // 同一個輸入框的另外兩顆（NPC 智能 2.1，engine.TEXT_TALKS）：跟答應陪你出陣的人商量打法、他帶路的路上跟他說一句。
  // S.saying 記著是哪一顆（true 是舊的寫法＝自己說），送出時連 option 一起給 /api/say
  const SAY_OPTIONS = [SAY_OPTION, "talk:plan", "parley:road"];
  const SAY_HINTS = { "talk:plan": "跟他說你想好的打法", "parley:road": "路上想跟他說的話，也可以開口求他" };
  const sayingId = () => (S.saying === true ? SAY_OPTION : S.saying);
  // 三方態勢（第一季設計 4.4，status.stances 的鍵）：狀態列展開時那一行；第一季濃縮版才有
  const STANCE_NAMES = [["guan", "官軍"], ["huang", "黃巾"], ["haoqiang", "豪強"]];
  // 手機寬度：第一次打開輿圖時，手機照原尺寸，寬螢幕照框寬（最多原尺寸），都對準所在地（見 mapReady）
  const PHONE = window.matchMedia ? window.matchMedia("(max-width: 767px)") : null;


  const $app = document.getElementById("app");
  const $toast = document.getElementById("toast");

  // ── 工具 ──
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pct = (a, b) => (b > 0 ? Math.max(0, Math.min(100, (a / b) * 100)) : 0);

  // 序章（新手引導計畫一）：伺服器送 m.prologue = {reveal, glow, skip}；不在序章是 null，畫面照平常畫。
  // shown(key)：這個元件亮了沒（reveal 有它、或 "all" 全亮）。glow 列的鈕加 .glow，新亮起來的加 .lit（見 applyGlow）。
  // prologueKey：亮起來的東西變了沒——變了就整頁重畫（分頁列、狀態列只在整頁重畫時才換，見 renderTop）
  const pro = () => (S.main && S.main.prologue) || null;
  // 初入江湖（新手引導第四段）：出了草廬之後那幾步也一樣一樣亮（m.onboard，同一個形狀）；草廬裡才有的規矩（略過序章、師父的框）照舊只看 pro()
  const shown = (key) => { const p = pro() || (S.main && S.main.onboard); return !p || p.reveal.includes("all") || p.reveal.includes(key); };
  const prologueKey = () => { const p = pro() || (S.main && S.main.onboard); return p ? p.reveal.join(",") : ""; };
  // 本季天數：整數不帶小數點（14.0 → 14），不是整數照原樣（14.5）
  const dayCount = (n) => String(Number(n));
  // FB-501（PM 2026-10-20）：7 天濃縮季的「週」是段（第 1～2、3～4、5～7 天），軍令每天一道。伺服器在 7 天季送
  // status.calendar.words（calendar.week_words：「這一段」「每段」「今日」……與每一段的名字 names、段末 ends），21 天季只送軍令的
  // 那幾個字（FB-502）；畫面上寫週的地方一律問 calWords／wkWord／wkName，沒有那個字的季照原本的字（plain），週末、14 天一個字都不變。字待 joy 潤
  function calWords() {
    const s = S.main && S.main.status;
    return (s && s.calendar && s.calendar.words) || null;
  }
  function wkWord(key, plain) { const w = calWords(); return w && w[key] ? w[key] : plain; }
  function wkName(n, plain, end) { const w = calWords(), names = w && (end ? w.ends : w.names); return (names && names[n - 1]) || plain; }
  // FB-502（PM 2026-10-20）：21 天季的軍令也是每天一道，伺服器在 21 天季只送軍令的那幾個字（order_this…，沒有 names）。
  // 「季曆有段」與「軍令每天發」分開問：段照 names，軍令照 order_this
  function wk7() { const w = calWords(); return !!(w && w.names); }
  function ordersDaily() { const w = calWords(); return !!(w && w.order_this); }
  // 江湖頁畫的東西有沒有變：狀態列（時鐘、季曆每次輪詢都在走）另外重畫，不讓「剛剛」一直重播浮現
  // 狀態列另外畫（renderTop），江湖頁不必跟著它重畫；奪璽卡與碎片卡的資料也在 status 裡（回合、氣勢、已出招、架勢），
  // 那兩張變了要重畫（FB-172）。奪璽卡的倒數（left）每秒都在變，不算進來（FB-182：單挑期間全服的江湖頁每 10 秒整頁重畫）：
  // 輪詢時只換那一行的字（refreshPage → paintSealWhen，照 renderTop 另外畫的做法）
  const pageKey = (m) => JSON.stringify({ ...m, status: null, sealCards: m.status
    ? [m.status.seal_duel ? { ...m.status.seal_duel, left: null } : null, m.status.seal || null] : null });
  // 焦點在輸入框、下拉選單：玩家正在填東西，輪詢不動畫面
  // 勾選框不算：勾完它還留著焦點，要是算打字，輪詢會一直等到玩家點別處才補畫（修練頁的「服下破境丹」）
  const typing = () => S.stroking || (!!document.activeElement && ["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)
    && document.activeElement.type !== "checkbox");

  // 表單的結果訊息（QA L3）：寫在表單裡那一行，留到下一次送出；錯誤醒目、成功用一般文字色
  function formMsg(form, text, ok = false) {
    const el = form.querySelector(".form-msg");
    if (!el) return;
    el.textContent = text || "";
    el.classList.toggle("ok", ok);
  }
  // 請求的錯誤寫成玩家看得懂的一句：連不上（api() 已經標成離線）另外講；api() 自己丟的 Error 帶著伺服器的原因，照登；
  // 其他錯誤（程式出錯，例如 TypeError）不要說成網路問題，也不要把英文的錯誤訊息丟給玩家
  const failText = (e) => (S.offline ? "連不上伺服器，請稍後再試。"
    : e && e.constructor === Error && e.message ? e.message : "出了點問題，請再試一次。");

  // 動作請求多久算逾時、逾時與沒送出去時講的話（見 api()、busy；待 joy 潤）
  // 取名、大場面判讀最多 60 秒加上等鎖；trycloudflare 約 100 秒切斷一個請求
  const ACTION_TIMEOUT_MS = 90000;
  // 逾時與沒送出去同一句（PM 2026-10-12 轉 Joy「弄個符合我們世界觀的句子」）
  const TIMEOUT_TEXT = "鴻雁折返，訊息未達——再試一次";
  const UNSENT_TEXT = "鴻雁折返，訊息未達——再試一次";

  let toastTimer = 0;
  function toast(text) {
    $toast.textContent = text;
    $toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => $toast.classList.remove("show"), 3200);
  }

  async function api(path, body) {
    const headers = { "X-Move-Mode": S.moveMode }; // 走法跟著每個請求走，兩個分頁各走各的（見 MOVE_MODES）
    const opts = body === undefined
      ? { credentials: "same-origin", headers }
      : { method: "POST", credentials: "same-origin", headers: { ...headers, "Content-Type": "application/json" }, body: JSON.stringify(body) };
    // 動作（POST）最多等 ACTION_TIMEOUT_MS：伺服器卡住時不讓按鈕永遠轉，說清楚、讓人可以再按一次（Joy 2026-10-12）。
    // 輪詢與分頁的 GET 不設：上一次沒回來就不再打（pollInFlight），連不上時照舊標離線
    const ctl = body !== undefined && typeof AbortController === "function" ? new AbortController() : null;
    const timer = ctl ? setTimeout(() => ctl.abort(), ACTION_TIMEOUT_MS) : 0;
    let res;
    try {
      res = await fetch(path, ctl ? { ...opts, signal: ctl.signal } : opts);
    } catch (e) {
      if (ctl && ctl.signal.aborted) { // 逾時：伺服器還連得上（不標離線），只是這一下沒等到回應
        toast(TIMEOUT_TEXT);
        const err = new Error(TIMEOUT_TEXT);
        err.timedOut = true;
        throw err;
      }
      setOffline(true);
      if (body !== undefined) toast(UNSENT_TEXT); // 動作沒送出去：照實講，按鈕會還原、可以再按
      throw e;
    } finally { clearTimeout(timer); }
    setOffline(false);
    if (res.status === 401) {
      S.stage = "gate";
      render();
      throw new Error("請先登入。");
    }
    if (res.status === 409) {
      S.stage = "create";
      render();
      throw new Error("這個帳號還沒有角色。");
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = data.error || data.detail || "出了點問題，請再試一次。";
      toast(msg);
      throw new Error(msg);
    }
    return data;
  }

  function setOffline(v) {
    if (S.offline === v) return;
    S.offline = v;
    const el = document.querySelector(".offline");
    if (v && !el) document.body.insertAdjacentHTML("beforeend", '<div class="offline">連不上伺服器，重試中…</div>');
    if (!v && el) el.remove();
  }

  function enter(data) {
    resetOrdersWatch(); // 換了帳號、角色：入伍段第一步的看過與計時都重來
    forgetHowto(); // 玩法說明也是（登入失效之後重新登入，沒經過登出那顆鈕）
    forgetMap(); // 輿圖也是（FB-329）：停在輿圖分頁時下面 render 之後重抓這個人的
    S.here = null; // 「此地還能做」摺疊的開合與自動打開過的記錄也重來（FB-087）
    S.hereAuto = {};
    S.moveMode = "walk"; // 登入、重新登入、建角的畫面都是伺服器照步行排的（_entry 不看走法），切換鈕跟著回到步行
    forgetMall(); // 商城那一層與管理者查的帳也是：換了帳號是另一個錢包
    if (data.stage === "game") {
      S.stage = "game";
      setMain(data.main);
      closeEvents(); // 重新連：現在這個登入的連線（上一個帳號的、登入失效前的，不能留著）
      connectEvents(); // main.push 是 true 才真的連（預設關：不開 EventSource）
      if (S.patchNotes === undefined) loadPatchNotes(); // 有沒看過的改版就跳一次（patchPopHtml）
    } else {
      S.stage = data.stage === "create" ? "create" : "gate";
      closeEvents();
    }
    render();
    if (S.stage === "game" && S.tab === "map" && !S.adminPage) loadMap().catch(() => {}); // 停在輿圖分頁登入：這個人的疊層與底圖（輪詢在沒有疊層時不抓）
  }

  function setMain(main) {
    // 破境卡：動作回來的與輪詢拿到的都走這裡（S.main 換好之後才畫）。測試只抽 setMain 出來跑，沒有 ascendCard 就不畫
    // 管理頁上不跳這三樣（破境、特殊事件、走一趟都是江湖頁的；回江湖那一下再跳）
    if (!S.adminPage && typeof ascendCard === "function") setTimeout(ascendCard, 0);
    if (!S.adminPage && typeof storyCard === "function") setTimeout(storyCard, 0); // 特殊事件的跳顯框：同上
    if (!S.adminPage && typeof outingSync === "function") setTimeout(outingSync, 0); // 走一趟停在要選的事上、選完了：接著走（outing.js）
    if (main.event_free_text == null) S.answering = false; // 事件過去了，輸入框跟著收起
    if (!(main.options || []).some((o) => o.id === sayingId())) S.saying = false; // 交談結束了（或那一顆沒了），輸入框跟著收起
    if (S.persuading && !(main.options || []).some((o) => o.id === S.persuading)) S.persuading = false; // 走開了、那一件辦完了：勸降的輸入框收起
    if (S.godNaming && !(main.options || []).some((o) => o.id === OWN_NAME_ID)) S.godNaming = false; // 取成了、換了別的：取名的輸入框收起
    if (S.sensing && !(main.options || []).some((o) => o.id === SENSE_DRAW)) closeSense(); // 感悟狀態過去了（悟成、作廢），畫布跟著收起
    // 出陣約戰：正在應的那一張應不了了（別人先應了、窗過了、走開了），應戰那張卡收起、挑到一半的招清掉
    if (S.sortieAnswer && !(main.sorties || []).some((d) => d.id === S.sortieAnswer && d.can_answer)) { S.sortieAnswer = null; S.sortiePick = []; }
    // 見聞的紅點只為新的一場亮（比 card_id）：配點之後「剛剛」照舊是升級那一場的卡片，看過戰報再配點不再亮一次（計畫二最終審查 M1）；
    // 放在這裡是因為動作回來的與輪詢拿到的都走 setMain——決戰收場的卡片常常是輪詢（sync）補送的。登入那一份不亮（S.main 還沒有）
    if (main.card && S.main && S.main.card_id !== main.card_id) {
      S.unseen = true;
      paintNewsDot();
    }
    const key = JSON.stringify(main);
    const changed = key !== S.mainKey;
    // 序章：配屬性點那一步（glow 有 stats）做完，點開的屬性面板收起來——留著的話它一路撐到出師，「前往」被擠到分頁列底下（T7 走查 W-D）
    const wasStats = !!(S.main && S.main.prologue && S.main.prologue.glow.includes("stats"));
    // 店面開了、收了或換了一間（店面獨立介面設計 1.1）：從頭來——鐵匠鋪從架上那一頁、空爐，馬市點著你騎的，懸賞榜不放大；
    // 離開鐵匠鋪時出爐卡一起收（只動 S 的欄位：setMain 會被單獨切出去測）。比的是哪一間店（main.shop.shop），不是有沒有店：出了鐵匠鋪、兩次輪詢之間又走進馬市，有沒有店都是「有」，鐵匠鋪那幾個欄位卻得清掉
    const shopKind = (v) => (v && v.shop ? v.shop.shop : null);
    if (shopKind(main) !== shopKind(S.main)) {
      S.shopTab = "shelf"; S.shopPot = null; S.shopLine = null; S.shopMore = false;
      S.shopHorse = null; S.boardZoom = null; S.boardStamp = null; S.arenaTab = "floor";
      S.shopNote = null; S.donatePick = {}; // 素材頁、軍需帳上一下的結果與挑好要捐的（素材與經濟 B6）
      S.shopBrew = null; S.rackPick = {}; S.divinePick = null; // 打造頁點開的灰格、裝備庫勾了的、神器頁點著的（鐵匠鋪與合成流程 3.3、3.4、3.8）
      S.tavTab = "news"; S.tavAsk = "seek"; // 酒肆從聽消息那一頁來
      if (shopKind(main) !== "smith") { S.shopReveal = null; S.shopOpened = false; }
    }
    S.main = main;
    // 自建形象的圖版本（main.looks_ver）：那幾支組圖網址時接成 ?v=，圖一換網址就換，手機不必清快取
    window.LOOKS_VER = main.looks_ver || "";
    // 決戰這一回合幾時逾時（引擎給還剩幾秒，battle_gauge.due）：tickDue 照它每秒倒數（Joy 2026-10-13）
    S.dueAt = main.battle_gauge && main.battle_gauge.due != null ? Date.now() + main.battle_gauge.due * 1000 : null;
    S.duePolled = false;
    // 戰場面板的倒數（battle.js 的 bpTick）：集結、回合都照它跳；集結歸零補抓一次（S.bpPolled）
    S.bpDueAt = main.battle_panel && !main.battle_panel.paused ? Date.now() + main.battle_panel.due * 1000 : null;
    S.bpPolled = false;
    // 奪璽卡的倒數同一套（FB-182）：left 是還剩幾秒，tickDue 照它每秒換 .seal-when 那一行的字
    const sealDuel = main.status && main.status.seal_duel;
    S.sealDueAt = sealDuel && sealDuel.left != null ? Date.now() + sealDuel.left * 1000 : null;
    S.sealDuePolled = false;
    document.title = sealTitle(); // 輪到奪璽出招時改分頁標題（玉璽碎片設計 5.5）：輪詢的、動作回來的畫面都走這裡
    if (wasStats && !(main.prologue && main.prologue.glow.includes("stats"))) S.showMore = false;
    S.mainKey = key;
    lastPoll = Date.now(); // 剛拿到一份新的畫面（輪詢的、動作回來的都走這裡）：連著推送時，下一次慢速輪詢從這一刻起算
    return changed;
  }

  // 分頁列上見聞那一顆補上紅點：分頁列只在整頁重畫（render）時畫，輪詢只重畫狀態列與頁面，
  // 所以紅點亮起的當下就地補一顆（已經有、或正在看見聞時不補）
  function paintNewsDot() {
    const tab = document.querySelector('.tabs .tab[data-tab="news"]');
    if (tab && S.unseen && S.tab !== "news" && !tab.querySelector(".dot")) tab.insertAdjacentHTML("beforeend", '<i class="dot"></i>');
  }

  // ── 整體 ──
  function render() {
    if (S.mallOpen && !(S.main && S.main.mall)) S.mallOpen = false; // 商城關了（主機關掉開關）：那一層跟著收
    if (S.stage !== "game" || (!S.sheet && !S.peer && !S.mallOpen && !S.adminPage)) closeAsk(); // 管理頁的確認框也是 // 確認框疊在設定抽屜、玩家卡或商城上；抽屜關了、被登出就一起收掉
    if (S.stage !== "game") hideMapHost(true); // 登出、換帳號：常駐的輿圖那一層整個清掉
    if (S.stage === "gate") return renderGate();
    if (S.stage === "create") return renderCreate();
    if (S.stage !== "game") return;
    if (S.adminPage) { // 管理頁（admin.js）：只有管理者畫得出來；不是的話照常回江湖、網址換回 /
      if (S.main && S.main.admin) return renderAdmin();
      S.adminPage = false;
      try { history.replaceState(null, "", "/"); } catch (e) { /* 換不了網址也照常畫江湖 */ }
    }
    if (S.tab !== "jianghu" && !shown(`tab:${S.tab}`)) S.tab = "jianghu"; // 序章重來（換季）：藏起來的分頁不能還停在那一頁
    legacyOfferOpen();
    S.prologueKey = prologueKey();
    const top = topHtml();
    // 疊在最上面那幾層（傳承、識海、列傳）自己捲：整個重畫會把它們捲回頂端（企劃者 2026-11-05「竹簡點下去會畫面跳到置頂」），
    // 重畫前記下捲到哪、畫完照原樣放回去；換頁（傳承↔識海、開新的一層）是另一個 class，不帶過去
    const layers = [".lg-layer", ".zhuan-layer"].map((sel) => { const el = document.querySelector(sel); return el && { sel, cls: el.className, top: el.scrollTop }; }).filter(Boolean);
    $app.innerHTML = `
      <div class="shell">
        <header class="top" id="top"${top ? "" : " hidden"}>${top}</header>
        <main class="page" id="page"></main>
      </div>
      ${tabsHtml()}
      ${S.sheet ? sheetHtml() : S.peer ? peerHtml() : S.boardCard ? boardCardHtml() : ""}
      ${S.main && S.main.shop ? shopHtml(S.main.shop) : S.mallOpen ? shopHtml(mallShop()) : ""}
      ${S.sealAct && sealActNow() ? sealActHtml(sealActNow()) : ""}
      ${S.book ? bookHtml() : ""}
      ${S.zhuan ? zhuanHtml(S.zhuan) : ""}
      ${S.legacy ? legacyPageHtml() : ""}
      ${S.main && S.main.prep ? prepHtml(S.main.prep) : ""}
      ${S.mtEdit && S.mingtie ? mtEditHtml() : ""}
      ${S.mtZoom ? mtZoomHtml() : ""}`;
    fitBars(); // 先量狀態列：所在那一行放不下會折成兩行、狀態列高一截（FB-493），第一屏（renderPage 裡的 fitFirstScreen）照折好的高度收
    renderPage();
    for (const l of layers) { const el = document.querySelector(l.sel); if (el && el.className.replace(" zh-play", "") === l.cls.replace(" zh-play", "")) el.scrollTop = l.top; }
    if (S.mtEdit) mtPadReady();
    fitBars(); // 狀態列的「體力」「氣血」放不放得下（FB-198）；頁面畫上去之後再量一次（電腦上捲軸出來，狀態列跟著窄）
    if (S.sheet) document.querySelector(".sheet-bg")?.addEventListener("wheel", sheetWheel, { passive: false }); // 暗處是每次新畫的，掛一次
    if (typeof ringSync === "function") ringSync(); // 擂台動畫（arena_anim.js）：畫布是新畫的，接著演
  }

  // 設定抽屜在電腦上只有中間 640px 寬、自己捲：滑鼠在兩旁的暗處（.sheet-bg）滾輪時，頁面不動、改捲抽屜。不然指標不在抽屜上就
  // 捲不到抽屜下半的管理者工具（企劃者 2026-10-07「管理者按鈕電腦版看不到，但手機版可以看到」；手機上抽屜滿版，怎麼滑都捲得到）。
  // 只掛在暗處（render 畫抽屜時），不掛在整份文件上：別處的捲動照舊是瀏覽器自己的、不必等主執行緒（審查 M-3）。ctrl＋滾輪與
  // 觸控板捏合是瀏覽器的縮放，不攔。點暗處照舊關掉抽屜（click 的 sheet-close），這裡只管滾輪。deltaMode 1 以「行」計（Firefox），2 以「頁」
  function sheetWheel(ev) {
    if (ev.ctrlKey) return;
    const sheet = document.querySelector(".sheet");
    if (!sheet) return;
    ev.preventDefault();
    const unit = ev.deltaMode === 1 ? 16 : ev.deltaMode === 2 ? sheet.clientHeight || 600 : 1;
    sheet.scrollBy(0, ev.deltaY * unit);
  }

  // 抽屜開著時整個重畫（查玩家、打開設定時補抓回來的管理者資料、序章回顧）：抽屜是新畫的、捲動回到頂；照原本捲到的地方放回去，
  // 查到的玩家才不會被丟回「設定」那一行之下好幾屏（審查 M-2）。抽屜原本沒開（剛打開）就照常從頂上開始
  function renderKeepingSheet() {
    if (S.adminPage) { // 管理頁捲的是整頁：重畫完捲回原處（做完一件事、查完一個人，不被丟回頂上）
      const y = typeof window.scrollY === "number" ? window.scrollY : 0;
      render();
      if (typeof window.scrollTo === "function") window.scrollTo(0, y);
      return;
    }
    const top = document.querySelector(".sheet")?.scrollTop;
    render();
    const sheet = document.querySelector(".sheet");
    if (sheet && top != null) sheet.scrollTop = top;
  }

  // 底部分頁列：序章裡只畫亮起來的分頁（格數跟著變，不是固定五格），一個都沒有就整列不畫。data-glow 給序章指路（applyGlow）
  // 商城開著（main.mall）時多第六格「商城」（商城第二批，企劃者 2026-10-20 挑的入口丙）：點了打開商城那一層、不換頁（出店回到原本那一頁）。
  // 序章裡跟其他還沒開放的分頁一樣藏著，出了草廬就在（mallShown，FB-490；齒輪旁的錠子鈕同一條）
  function tabsHtml() {
    const list = TABS.filter((t) => [t.id, ...(t.also || [])].some((id) => shown(`tab:${id}`)));
    if (!list.length) return "";
    const mall = mallShown();
    // 「俠客」那一格：在修練或煉製頁都亮著；序章要你去煉製（glow 有 tab:craft）而你不在「俠客」時，這一格也替煉製發光（data-glow 兩個鍵），
    // 人已經在修練頁時改由頁底「煉製」那一顆發光
    const on = (t) => S.tab === t.id || (t.also || []).includes(S.tab) ? !(S.tab === "news" && selfNews(S.news))
      : t.id === "practice" && S.tab === "news" && !!selfNews(S.news); // 從「俠客」進去的行狀、榜單、名帖匣：亮「俠客」
    const glow = (t) => [t.id, ...(on(t) ? [] : t.also || [])].map((id) => `tab:${id}`).join(" ");
    return `${typeof bpMiniHtml === "function" ? bpMiniHtml() : ""}<nav class="tabs"><div class="tabs-inner" style="grid-template-columns:repeat(${list.length + (mall ? 1 : 0)}, 1fr)">${list.map((t) => `
        <button class="tab ${on(t) ? "on" : ""}" data-act="tab" data-tab="${t.id}" data-glow="${glow(t)}">
          <span class="ico">${t.ico}</span>${t.name}${t.id === "news" && S.unseen && S.tab !== "news" ? '<i class="dot"></i>' : ""}
        </button>`).join("")}${mall ? `
        <button class="tab tab-mall" data-act="mall-open" data-tab="mall" data-glow="tab:mall" aria-label="商城，元寶 ${S.main.mall.balance | 0}"><span class="ico">寶</span>商城</button>` : ""}</div></nav>`;
  }



  // 名聲那一條：狀態列裡的（舊介面）只重畫狀態列；介面重整之後在俠客頁的屬性那一頁，要重畫那一頁
  function renownDraw() {
    renderTop();
    if (S.tab === "practice" && typeof uiV2 === "function" && uiV2()) renderPage();
  }
  function renderTop() {
    if (S.prologueKey !== prologueKey()) { render(); return; } // 序章亮起了新的東西：分頁列與狀態列要一起換（render 會畫好發光）
    const el = document.getElementById("top");
    if (!el) return;
    const before = el.offsetHeight; // 狀態列重畫前多高：變了就重量第一屏（fitTopMoved，FB-123）
    const html = topHtml();
    el.innerHTML = html;
    el.hidden = !html;
    fitBars();
    applyGlow();
    fitTopMoved(before);
    // 狀態列變高變矮：輿圖那一層跟著夾，地圖框換了高就重套取景（FB-710：不重套的話下一次拖縮拿新的框高配舊的取景，先跳 z×框高差÷2；
    // 同一層、同一區只換框高時拖縮帶過去，applyMapView 的 panCarry）
    if (S.tab === "map" && mapFrame()) applyMapView();
  }

  // 狀態列體力條、氣血條上的「體力」「氣血」兩個字（FB-135、FB-198，PM 2026-10-14「數字放得下就寫全，放不下才讓開」）：
  // 畫好之後量一次，條上那一行字的字尾碰不碰得到右邊的「傷 N」（氣血條）或丹的鈕（體力條）。碰到了先收一號（.snug：字小一號、
  // 內距收一點，兩個字照寫），還碰到才拿掉兩個字（.tight；條上的 title 照舊寫）。topHtml 從不帶這兩個 class：每次畫狀態列
  // （render、renderTop）、視窗換寬度、字型載入完都從寫全量起。瀏覽器量不了、條還沒排版（寬是 0）就不動（照寫全）
  // 自訂屬性變了才寫（同一個值照寫也算改了 inline style，會逼繼承它的整棵重算樣式）
  function setVar(el, name, value) {
    if (typeof el.style.getPropertyValue !== "function" || el.style.getPropertyValue(name) !== value) el.style.setProperty(name, value);
  }
  function fitBars() {
    const head = document.getElementById("top");
    // 名號底下所在那一行（📍 地名　季曆時刻，FB-493）：字尾超過那一欄（瀏覽器會收成「…」）就加 .split，地名一行、時刻一行（企劃者
    // 2026-10-20 挑乙）。同條上那兩個字：topHtml 不帶，每次從一行量起；量 Range 不量 scrollWidth（多出不到半 px 時兩個都是整數、一樣大，
    // 瀏覽器卻照樣收「…」）。序章只寫地名（沒有 .where-at）不折；還沒排版（寬 0）不動。要排在 --top-h 前面：折了狀態列高一截
    const where = typeof document.createRange === "function" && head && typeof head.querySelector === "function" ? head.querySelector(".who .where:not(.sub)") : null; // 介面重整把它包進 .who-col，舊的 .who > .where 量不到（Joy 11/7 截圖時刻被截成「09:…」）
    if (where && where.querySelector(".where-at")) {
      where.classList.remove("split");
      const range = document.createRange();
      range.selectNodeContents(where);
      if (where.clientWidth && range.getBoundingClientRect().right > where.getBoundingClientRect().right) where.classList.add("split");
    }
    // 煉製頁縮起來的太極爐（.kiln.compact）固定在狀態列底下：狀態列多高（展開名號、換寬度都會變）記在 --top-h
    if (head && document.documentElement && document.documentElement.style && typeof head.offsetHeight === "number") {
      // 變了才寫：根元素上的自訂屬性一路繼承，寫一次（就算同一個值）整頁約 1,600 個元素重算樣式，狀態列每次重畫都會叫到這裡
      setVar(document.documentElement, "--top-h", `${head.hidden ? 0 : head.offsetHeight}px`);
    }
    if (typeof document.createRange !== "function") return;
    const top = document.getElementById("top");
    if (!top || !top.querySelectorAll) return;
    const gap = 3; // 字尾離丹的鈕至少幾 px（「傷 N」自己左右有內距，不另留）
    for (const bar of top.querySelectorAll(".bar.hp, .bar.stam")) {
      bar.classList.remove("snug", "tight");
      const text = bar.querySelector(":scope > span:not(.inj)");
      const tag = bar.querySelector(":scope > .inj, :scope > .pill-btn");
      if (!text || !tag || !bar.clientWidth) continue;
      const hits = () => {
        const range = document.createRange();
        range.selectNodeContents(text);
        return range.getBoundingClientRect().right + (tag.classList.contains("pill-btn") ? gap : 0) > tag.getBoundingClientRect().left;
      };
      if (!hits()) continue;
      bar.classList.add("snug");
      if (hits()) bar.classList.add("tight");
    }
  }

  function topHtml() {
    const s = S.main.status;
    // 序章（新手引導計畫一）：狀態列的五樣（體力、氣血、銀兩、心得、點名號展開的屬性）一樣都還沒亮，整條不畫（#top 跟著 hidden）；
    // 有一樣亮了，名號那一行照畫，底下各個數字各看自己的鍵。序章裡所在只寫地名：日期、下一件、心得提示都是真實世界的事
    if (!["stamina", "hp", "silver", "xinde", "stats"].some(shown)) return "";
    const inPro = !!pro();
    if (!shown("stats")) S.showMore = false; // 屬性沒亮就點不開（序章重來、換季時也不會停在展開的樣子）
    const team = s.team.map((m) => `🧍 ${esc(m.name)} 第${m.level}級 氣血 ${m.hp}/${m.hp_max}`).join("　");
    // 名號、所在底下的小字行（下一件、閉關、路程）：排在整列底下、整個寬度都能用，不跟右上角的設定鈕擠一邊。
    // 兩種時間的寫法固定（FB-062）：下一件是「季曆時刻（現實倒數）」，路程只寫現實倒數。這兩行比原本長，擠在一邊會折成四行，
    // 在路上時把路上最底下的「走法」擠到分頁列底下（FB-060）
    // 「下一件」減法季批 1 搬進本週卡的「為什麼」（整合設計 6.2：表頭三行）；路程是這一刻的狀態，照舊。
    // 閉關的鈕 2026-10-25 拿掉了（Joy）：這一行只給拿掉之前就閉著關的人看到出關
    const subs = [
      s.busy_hours != null ? `🧘 閉關中，現實約 ${s.busy_hours} 小時後出關` : "",
      s.journey != null ? `🐎 ${esc(s.journey)}` : "",
    ].filter(Boolean).map((t) => `<div class="where sub">${t}</div>`).join("");
    // 地名、間隔、時刻各一格（FB-493，企劃者 2026-10-20 挑乙）：放得下照舊一行；錠子鈕把名號那一欄擠窄、放不下時，fitBars 量了才加
    // .split，地名一行、時刻一行（間隔拿掉）。這裡從不帶 .split
    const where = inPro ? `📍 ${esc(s.location)}` : `<span class="where-loc">📍 ${esc(s.location)}</span><span class="where-gap">　</span><span class="where-at">${s.calendar
      ? esc(s.calendar.text)
      : `第 ${s.day} 天 ${esc(s.clock)}<small>／共 ${dayCount(s.season_days)} 天</small>`}</span>`;
    const vitals = [
      // 回體丹（企劃者 2026-10-07 內測贈送）：有丹時體力條右端多一顆「丹 N」，按了吃一顆；體力滿了是灰的。序章裡伺服器不給 pills。
      // 測試期間一鍵補滿打開時（pills.refill）：沒有丹也有這顆鈕、字改成「補滿」，按了直接補滿、不花丹
      // 一天的上限（企劃者 2026-10-12，pills.today＝今天還能服幾顆，不限是 null）：鈕上多寫「今N」，服滿了灰掉寫「明日」
      // 點體力條（丹／補滿那顆鈕以外的地方）在底下攤開體力怎麼回（explain-1；s.stamina_help 是伺服器照設定寫好的幾行）
      shown("stamina") ? `<div class="bar stam" title="體力" data-glow="stamina"${s.stamina_help && s.stamina_help.length
        ? ` data-act="stam-help" role="button" tabindex="0" aria-expanded="${!!S.stamOpen}" aria-controls="stam-help"` : ""}><i style="width:${pct(s.stamina, s.stamina_max)}%"></i><span><em class="lbl">體力 </em>${s.stamina}/${s.stamina_max}</span>${s.pills
        ? `<button class="pill-btn" data-act="pill" data-glow="pill" ${s.pills.full || (!s.pills.refill && s.pills.today === 0) ? "disabled" : ""} aria-label="${s.pills.refill
          // 測試期間一鍵補滿（伺服器給 pills.refill＝鈕上的字，沒有丹也給）：鈕寫「補滿」不寫丹數；關著時沒有這個鍵，照 joy 的寫法
          ? `${esc(s.pills.refill)}體力（測試期間免費，不花${esc(s.pills.name)}）`
          : `服下${esc(s.pills.name)}（剩 ${s.pills.count} 顆，回 ${s.pills.restore} 點體力${s.pills.today == null ? "" : s.pills.today
            ? `，今天還能服 ${s.pills.today} 顆` : "，今天已經服滿，明日 00:00 後再服"}）`}">${s.pills.refill ? esc(s.pills.refill)
          : `丹${s.pills.count}${s.pills.today == null ? "" : s.pills.today ? `<small>今${s.pills.today}</small>` : "<small>明日</small>"}`}</button>` : ""}</div>` : "",
      shown("hp") && typeof bpHpBar === "function" && bpHpBar() ? bpHpBar() : shown("hp") ? `<div class="bar hp" title="氣血" data-glow="hp"><i style="width:${pct(s.hp, s.hp_max)}%"></i>${s.injury >= 1
        // 內傷（FB-049）：斜紋是上限裡被內傷佔掉、回不來的那一截（寬＝內傷÷上限，回滿時紅條剛好接到它）；
        // 「傷 N」靠右另寫在斜紋那一頭，不再接在「氣血 N/M」後面跨過紅條的交界
        // 「氣血」兩個字包成一格：條窄、又有內傷時讓開給「傷 N」（style.css 的 @container，FB-135）
        ? `<b style="width:${pct(s.injury, s.hp_max)}%"></b>` : ""}<span><em class="lbl">氣血 </em>${s.hp}/${s.hp_max}</span>${s.injury >= 1
        ? `<span class="inj">傷 ${s.injury}</span>` : ""}</div>` : "",
      shown("silver") ? `<div class="num" data-glow="silver"><em>銀</em>${s.silver}</div>` : "",
      // 心神（跟人物交談扣的；伺服器關著時沒有 s.xinshen）：今天剩幾點／今天補到多少，有凝神香存著的另寫「存 N」
      s.xinshen && shown("silver") ? `<div class="num xs" title="${esc(s.xinshen.name)}：跟人物交談用，每天 00:00 補滿"><em>${esc(s.xinshen.name)}</em>${s.xinshen.now | 0}/${s.xinshen.cap | 0}${s.xinshen.bank ? `<small>存${s.xinshen.bank | 0}</small>` : ""}</div>` : "", // 待 joy 潤
      // 心得、名望、善惡、五項屬性搬到「俠客」頁（整合設計 6.2）；序章裡心得亮了、銀兩還沒亮時照舊寫在這裡（序章的話要你看它）
      shown("xinde") && !shown("silver") ? `<div class="num" data-glow="xinde"><em>心得</em>${s.xinde}</div>` : "",
    ].join("");
    // 點名號展開屬性：序章裡「屬性」那一步才點得開（data-glow="stats" 指路）；沒亮就不是按鈕
    // 介面重整：序章、初入江湖以外，點名號去俠客頁的「屬性」（以前在這裡攤開經驗、等級、屬性一大串），頭像角上一個等級
    const rv = (typeof uiV2 === "function" && uiV2()) && !inPro && !onb() && shown("stats");
    if (rv) S.showMore = false;
    const who = rv ? `<div class="who rv" data-act="hero-attrs" role="button" tabindex="0" aria-label="看屬性"><span class="who-ava" aria-hidden="true">${esc((s.name || "").slice(0, 1))}<b>${s.level}</b></span>`
      : shown("stats")
      ? `<div class="who" data-act="toggle-more" role="button" tabindex="0" aria-expanded="${S.showMore}" data-glow="stats">`
      : '<div class="who static">';
    return `
      <div class="top-row">
        ${who}${rv ? '<div class="who-col">' : ""}
          ${whoNameHtml(s)}
          <div class="where">${where}</div>
        ${rv ? "</div>" : ""}</div>
        ${mallShown() ? mallBtnHtml(S.main.mall) : ""}
        <button class="icon-btn" data-act="sheet" aria-label="設定">⚙</button>
      </div>
      ${S.showMore && S.renownOpen && s.renown ? renownStripHtml(s.renown) : ""}
      ${inPro ? "" : subs}
      ${vitals ? `<div class="vitals">${vitals}</div>` : ""}
      ${S.stamOpen && shown("stamina") && s.stamina_help && s.stamina_help.length
        ? `<div class="more-stats stam-help" id="stam-help">${s.stamina_help.map((t) => `<p>${esc(t)}</p>`).join("")}</div>` : ""}
      ${S.showMore ? `<div class="more-stats">
        ${s.renown ? "" : `${s.minor.map(([k, v]) => `${esc(k)} ${v}`).join("　")}　｜　`}${s.attrs.map(([k, v]) => `${esc(k)} ${v}`).join("　")}
        ${s.stat_points ? `<div class="pts-label"><b class="pts">可配 ${s.stat_points} 點</b></div><div class="row alloc">${s.attrs.map(([k, v, key]) => `<button class="btn small" data-act="allocate" data-stat="${esc(key)}" data-glow="allocate" ${v >= s.stat_cap ? "disabled" : ""}>＋${esc(k)}</button>`).join("")}</div>${statUsesHtml(s)}` : ""}
        ${s.growth ? growthHtml(s.growth) : ""}
        ${s.lilian ? lilianHtml(s.lilian) : ""}
        ${S.main && S.main.legacy ? legacyHtml(S.main.legacy) : ""}
        ${team ? `<br>${team}` : ""}
        ${s.stances && shown("stances") ? stancesHtml(s.stances, s.stance_notes) : ""}
      </div>` : ""}
    `;
  }

  // 狀態列的名號那一塊（FB-071）。收起來是一行：名號、頭銜（小字，放不下加「…」）、可配 N 點、▾——「可配」放在會省略的 <span>
  // 外面（flex: none），長長的「門派・陣營」只擠頭銜、擠不掉它。展開之後各有各的位置：名號獨佔第一行（後面是 ▴），頭銜是第二行，
  // 每一段（門派、陣營、頭銜、匿名、第 N 級）各自一個不折行的 <span>（class 叫 who-seg，不能叫 seg：那是全站的分段選單），
  // 只會在段與段之間換行，不會把一個詞從中間折斷；
  // 「可配 N 點」改放在＋鈕上面當那一排的標題（見 topHtml 的 pts-label）
  // 名聲（名聲設計十一之二）：收起時名號底下一行稱號（1B），第一屏放不下（FIT_STEPS 的 renown，S.renownTight）時這一行不畫、
  // 善惡稱號（沒有就名望稱號）接在頭銜後面（放不下先收名望稱號，同草圖 1A）；展開時經驗底下「名聲」那一行，點了攤開段落條（2C）
  function whoNameHtml(s) {
    const r = s.renown;
    const spans = r ? rnTitleSpans(r) : [];
    if (!S.showMore) {
      const tight = S.renownTight && S.tab === "jianghu"; // 只有江湖頁量第一屏：別的分頁照整行畫
      const inline = tight && spans.length ? `・${spans[spans.length - 1]}` : "";
      return `<div class="who-name"><span>${esc(s.name)}<small>${esc(s.affiliation)}${s.anonymous ? "・匿名" : ""}${inline}・第${s.level}級</small></span>${s.stat_points ? `<b class="pts">可配 ${s.stat_points} 點</b>` : ""}<i class="more-ico" aria-hidden="true">▾</i></div>`
        + (spans.length && !tight ? `<div class="who-renown-line">${spans.join("・")}</div>` : "");
    }
    const segs = [...s.affiliation.split("・"), ...(s.anonymous ? ["匿名"] : []), `第${s.level}級`].filter(Boolean);
    const renownLine = r ? `<div class="who-renown" data-act="renown-toggle" role="button" tabindex="0" aria-expanded="${!!S.renownOpen}"><em>名聲</em><b>${spans.length ? spans.join("・") : "還沒有稱號"}</b><i aria-hidden="true">${S.renownOpen ? "▴" : "▾"}</i></div>` : "";
    return `<div class="who-name"><span>${esc(s.name)}</span><i class="more-ico" aria-hidden="true">▴</i></div>
          <div class="who-title">${segs.map((t) => `<span class="who-seg">${esc(t)}</span>`).join("・")}</div>${expHtml(s)}${r ? renownLine : rangerHtml(s.ranger)}`;
  }

  // 稱號一個一格（status.renown.short：名望在前、善惡在後，renown.titles）：名望金、俠青、寇赭
  const rnPathClass = (p) => (p === "寇" ? "rn-kou" : "rn-xia");
  function rnTitleSpans(r) {
    return r.short.map((t, i) => `<span class="${i === 0 && r.fame.tier >= 1 ? "rn-fame" : rnPathClass(r.virtue.path)}">${esc(t)}</span>`);
  }
  // 2C：展開時點「名聲」那一行，名號那一塊底下（整個寬度）攤開：名望一條、善惡一條圓點（現在那一段亮），這一段給什麼、
  // 下一段還差多少給什麼各一句；點圓點換成那一段的說明（S.renownDot）；散人多一行另有的好處（點開，S.renownSanren）；
  // 長的季多一句倍數；最底下名聲從哪裡來
  function renownStripHtml(r) {
    const f = r.fame, v = r.virtue, way = v.path, vcls = rnPathClass(way);
    const perks = (row) => (row && row.perks.length ? row.perks.join("・") : "");
    const dots = (rows, cur, cls, kind) => `<ol class="rn-dots ${cls}">${rows.map((t, i) => {
      const n = i + 1, pick = S.renownDot === `${kind}:${n}` ? " pick" : "";
      return `<li class="${n < cur ? "have" : n === cur ? "have cur" : ""}${pick}" data-act="renown-dot" data-dot="${kind}:${n}" role="button" tabindex="0" aria-label="${esc(t.title)}"><i></i><small>${esc(t.title)}</small></li>`;
    }).join("")}</ol>`;
    const note = (kind, x, rows, cls, none) => {
      const picked = S.renownDot && S.renownDot.startsWith(`${kind}:`) ? rows[Number(S.renownDot.split(":")[1]) - 1] : null;
      if (picked) return `<p class="rn-note"><b class="${cls}">${esc(picked.title)}</b>${picked.at}・${esc(perks(picked) || "沒有另外的好處")}</p>`;
      const now = x.tier ? `<b class="${cls}">${esc(rows[x.tier - 1].title)}</b>${esc(perks(rows[x.tier - 1]))}` : `<b>${esc(none)}</b>`;
      const next = x.next != null ? `再 ${x.gap} 到${esc(x.next)}${perks(rows[x.tier]) ? `：${esc(perks(rows[x.tier]))}` : ""}` : "已是最高的一段";
      return `<p class="rn-note">${now}<span>${next}</span></p>`;
    };
    const other = way === "寇" ? `善名 ${v.good}` : `惡名 ${v.evil}`;
    const sanren = r.sanren ? `<button class="linkish rn-more" data-act="renown-sanren" aria-expanded="${!!S.renownSanren}">散人另有的好處 ${S.renownSanren ? "▴" : "▾"}</button>${S.renownSanren
      ? `<ul class="rn-sanren">${r.sanren.map(([k, x]) => `<li><b>${esc(k)}</b>${esc(x)}</li>`).join("")}</ul>` : ""}` : "";
    return `<div class="rn-strip">
        <div class="rn-row"><span class="rn-lbl">名望 <b>${f.n}</b></span>${dots(f.ladder, f.tier, "rn-fame", "fame")}</div>
        ${note("fame", f, f.ladder, "rn-fame", f.title)}
        <div class="rn-row"><span class="rn-lbl">${esc(v.by)} <b>${way === "寇" ? v.evil : v.good}</b></span>${dots(v.ladder[way], v.tier, vcls, "virtue")}</div>
        ${note("virtue", v, v.ladder[way], vcls, "還沒有稱號")}
        <p class="rn-hint">點圓點看那一段給什麼・${other}，走${esc(way)}的路${r.scale_note ? `・${esc(r.scale_note)}` : ""}</p>
        ${sanren}
        <p class="rn-src"><b>名望從哪裡來</b>${esc(r.sources.fame)}<b>善名、惡名從哪裡來</b>${esc(r.sources.virtue)}</p>
      </div>`;
  }

  // 頭銜底下一行：這一級的經驗（status.exp，team.exp_view）。30 級以後一級要好幾倍的經驗（50 級加陡），看得到還差多少；
  // 滿級伺服器送 null，寫「已到頂」
  function expHtml(s) {
    if (s.exp === undefined) return "";
    if (!s.exp) return `<div class="who-exp">經驗已到頂</div>`;
    return `<div class="who-exp">經驗 ${s.exp.have}／${s.exp.need}，再 ${Math.max(0, s.exp.need - s.exp.have)} 升第 ${(s.level | 0) + 1} 級</div>`;
  }

  // 散人的遊俠名號（status.ranger，ranger.status）：名號本身已經在頭銜那一行（social.affiliation），這裡只補俠名與下一階，
  // 第二行是這一階的好處。投靠了陣營就凍結，伺服器送 null，這一塊不畫
  function rangerHtml(r) {
    if (!r) return "";
    const next = r.next != null ? `，再攢 ${Math.max(0, r.next - r.points)} 點可稱「${esc(r.next_title)}」` : "，已是名號的頂";
    return `<div class="who-ranger">俠名 ${r.points}${next}${r.perks ? `<small>${esc(r.perks)}</small>` : ""}</div>`;
  }

  // ＋鈕底下一行：五項各管什麼（計畫二最終審查 M2）。點數配了收不回來，按之前要讀得到；文字是引擎給的（status.stat_uses），
  // 一項一個 inline-block：手機上整項一起換行，不會把「根骨：內功威力…」從中間折斷，也不會撐出橫向捲動
  // 成長配比（五項屬性的季才有 s.growth）：一季只挑一次（開季準備卡，企劃者 2026-11-05），狀態列只寫現在怎麼長；還沒挑的時候開季準備卡蓋在上面
  function growthHtml(g) {
    const row = (split) => split.map(([k, v]) => `${esc(k)} ${v}`).join("・");
    const chosen = g.presets.find((p) => p.key === g.chosen);
    const name = chosen ? chosen.name : g.chosen === "custom" ? "自己配" : "";
    if (name) return `<div class="growth"><div class="pts-label">這一季的成長：${esc(name)}（每級 ${row(g.now)}）</div></div>`;
    // 還沒挑：序章那一步在這裡挑（序章裡沒有開季準備卡）；序章外開季準備卡蓋在上面，草稿共用 S.growthDraft
    const draft = S.main && S.main.prep ? null : S.growthDraft;
    return `<div class="growth"><div class="pts-label">挑這一季的成長（每級合計 ${g.per_level} 點，一季只挑一次）</div><div class="row alloc">${g.presets.map((p) =>
      `<button class="btn small" data-act="growth" data-preset="${esc(p.key)}" data-glow="allocate" title="${esc(row(p.split))}">${esc(p.name)}</button>`).join("")}` +
      `<button class="btn small" data-act="growth-custom" ${draft ? "disabled" : ""}>自己配</button></div>${draft ? growthEditHtml(g, draft) : ""}</div>`;
  }

  // 開季準備卡（main.prep，企劃者 2026-11-05「至少需要導引」）：新的一季第一個畫面，① 挑成長配比 ② 識海（有上一季的神品意境時）。
  // 蓋住整個畫面、沒有關掉的鈕：兩步做完才能做別的事（引擎的選單也只剩這幾顆）。挑配比先點一張再按「定下來」（一季只挑一次）
  const PREP_TAGS = { warrior: "武力、統御高：打得重、扛得住", strategist: "悟性高：內功打得重、悟意境", ranger: "身法高：落敗也容易閃成僵持",
    envoy: "魅力、悟性高：招募便宜、說得動人、放手一搏", balanced: "五項一樣：哪一樣都不缺" };
  function prepHtml(p) {
    const m = S.main, g = m.status && m.status.growth;
    const at = p.steps.indexOf(p.step);
    const steps = p.steps.length > 1 ? `<ol class="prep-steps">${p.steps.map((k, i) =>
      `<li class="${i === at ? "on" : i < at ? "done" : ""}"><b>${i < at ? "✓" : i + 1}</b>${k === "growth" ? "成長配比" : "識海"}</li>`).join("")}</ol>` : "";
    const growth = p.step === "growth" && g;
    const body = growth ? prepGrowthHtml(g) : prepShihaiHtml(m.legacy && m.legacy.shihai);
    return `<div class="prep-layer" role="dialog" aria-modal="true" aria-label="開季準備"><div class="prep-card">
      <div class="prep-head"><small>新的一季・開季準備</small><h2>${growth ? "這一季怎麼長" : "識海：帶一份前世所悟"}</h2>${steps}</div>
      ${body}</div></div>`;
  }
  function prepGrowthHtml(g) {
    const pick = S.prepPick;
    const max = g.custom_max || g.per_level;
    const bars = (split) => `<span class="prep-split">${split.map(([k, v]) =>
      `<span><i style="--w:${Math.round((v / max) * 100)}%"></i>${esc(k)} ${v}</span>`).join("")}</span>`;
    const cards = g.presets.map((x) => `<button class="prep-opt${pick === x.key ? " on" : ""}" data-act="prep-pick" data-preset="${esc(x.key)}" aria-pressed="${pick === x.key}">
        <b>${esc(x.name)}</b><small>${esc(PREP_TAGS[x.key] || "")}</small>${bars(x.split)}</button>`).join("") +
      `<button class="prep-opt${pick === "custom" ? " on" : ""}" data-act="prep-pick" data-preset="custom" aria-pressed="${pick === "custom"}"><b>自己配</b><small>五項各 ${g.custom_min}～${max} 點，合計 ${g.per_level}</small></button>`;
    const edit = pick === "custom" && S.growthDraft ? growthEditHtml(g, S.growthDraft) : "";
    const go = pick && pick !== "custom" ? `<button class="btn primary prep-go" data-act="prep-growth">照「${esc((g.presets.find((x) => x.key === pick) || {}).name || "")}」長，定下來</button>` : "";
    return `<p class="prep-lead">每升一級五項合計長 ${g.per_level} 點，照你挑的這一套分。<b>這一季只挑一次</b>，挑了就定了；每 10 級另外送的點，隨時自己配。</p>
      <div class="prep-opts">${cards}</div>${edit}${go}${g.event_cap ? `<p class="prep-note">江湖歷練每一季最多長 ${g.event_cap | 0} 點，滿了化為心得。</p>` : ""}`;
  }
  function prepShihaiHtml(sh) {
    const offers = (sh && sh.offers) || [];
    const need = ((sh && sh.need) || []).map((n) => n.text).join("、");
    return `<p class="prep-lead">上一季悟出的神品意境，可以挑一份封進識海帶進這一季。封著的用不上，${need ? `要${esc(need)}才解得開` : "解封了才用得上"}；不帶也可以。</p>
      <div class="prep-opts">${offers.map((o, i) => `<div class="prep-keep"><div><b>${esc(o.name)}</b><small>神品意境・屬${esc(o.attribute)}・第${lgNum(o.season)}季</small></div>
        <button class="btn primary small" data-act="choose" data-id="legacy:seal:${i}">封進識海</button></div>`).join("")}</div>
      <button class="btn ghost prep-go" data-act="choose" data-id="legacy:skip">這一季不帶</button>`;
  }

  // 歷練（五項屬性的季才有 s.lilian）：這一季從事件得來的屬性，跟經驗那一行一樣寫「N／上限」，底下一條細的進度；滿了寫化為心得
  function lilianHtml(l) {
    const full = l.have >= l.cap;
    const pct = l.cap ? Math.min(100, Math.round((l.have / l.cap) * 100)) : 100;
    return `<div class="lilian${full ? " full" : ""}"><span>歷練 ${l.have | 0}／${l.cap | 0}${full ? "・已到火候，此後所得化為心得" : ""}</span><i style="--w:${pct}%"></i></div>`;
  }

  // 自己配（五項屬性的季）：每一項 −／＋，合計要剛好 per_level、每一項 custom_min～custom_max；草稿只在這個分頁（S.growthDraft），按「定下來」才送
  function growthEditHtml(g, draft) {
    const left = g.per_level - g.keys.reduce((n, [k]) => n + (draft[k] || 0), 0);
    const rows = g.keys.map(([k, name]) => {
      const v = draft[k] || 0;
      return `<div class="growth-step"><span>${esc(name)}</span>` +
        `<button class="btn small" data-act="growth-step" data-key="${esc(k)}" data-d="-1" aria-label="${esc(name)}少一點" ${v <= g.custom_min ? "disabled" : ""}>−</button>` +
        `<b>${v}</b><button class="btn small" data-act="growth-step" data-key="${esc(k)}" data-d="1" aria-label="${esc(name)}多一點" ${left <= 0 || v >= (g.custom_max || g.per_level) ? "disabled" : ""}>＋</button></div>`;
    }).join("");
    const note = left > 0 ? `還剩 ${left} 點` : left < 0 ? `多了 ${-left} 點` : "剛好";
    return `<div class="growth-edit">${rows}<div class="growth-foot"><span class="growth-left">每級合計 ${g.per_level} 點，每一項 ${g.custom_min}～${g.custom_max || g.per_level}：${note}</span>` +
      `<button class="btn small" data-act="growth-save" ${left === 0 ? "" : "disabled"}>定下來</button>` +
      `<button class="btn small" data-act="growth-cancel">取消</button></div></div>`;
  }

  function statUsesHtml(s) {
    if (!s.stat_uses) return "";
    const items = s.stat_uses.map(([k, use]) => `<span>${esc(k)}：${esc(use)}</span>`);
    if (s.stat_uses_note) items.push(`<span>${esc(s.stat_uses_note)}</span>`);
    return `<div class="stat-uses">${items.join("")}</div>`;
  }

  // 目前對話框的樣子（整個框的內容；沒有框是 "null"）：修練、煉製頁只在 menxia 的欄位變了才重畫，輪詢才排進來的提示
  // （大事揭曉、決戰集結、抵達……伺服器在同步時就記成說過了）會畫不出來——頁面畫的框跟現在的框不同就重畫（新手引導計畫三，T2 審查 I-1）
  const guideSig = () => JSON.stringify((S.main && S.main.guide) || null);

  function renderPage() {
    const page = document.getElementById("page");
    if (!page) return;
    let kilnWas = false; // 重畫前爐子已經縮成一條：畫完照樣縮著，不再從上面掉下來一次
    if (S.tab === "map" && showMapHost()) page.innerHTML = ""; // 輿圖畫在常駐的那一層（FB-324）
    else {
      hideMapHost();
      const fn = { jianghu: pageJianghu, map: pageMap, news: pageNews }[S.tab] || (PAGES[S.tab] || {}).render;
      kilnWas = !!document.querySelector(".kiln.compact");
      const sheetTop = document.querySelector(".craft-sheet")?.scrollTop; // 挑東西的抽屜開著時重畫：清單捲到哪留在哪
      page.innerHTML = fn();
      if (sheetTop) { const sheet = document.querySelector(".craft-sheet"); if (sheet) sheet.scrollTop = sheetTop; }
    }
    S.guideDrawn = guideSig(); // 這一頁畫的是哪個對話框：修練、煉製頁的輪詢拿它比，框換了才重畫（見 refreshPage）
    afterPage();
    if (S.tab === "craft") fixedKiln(kilnWas);
    applyGlow();
  }


  // 戰鬥卡片底下伏筆聽來的那一句（FB-074）：常有兩三行高、多撐 46～66px，新角色前七場遊歷有三場看到。
  // 伺服器在那一行標了 tx-hearsay（journal._line_class），這裡讓它變成一顆按鈕：收著是一行、放不下加「…」（style.css），
  // 點了看全文。展開記在 S.hearOpen（記的是哪一場的卡片），輪詢重畫不會把它收回去，換了下一場就收著
  function decorateHearsay() {
    document.querySelectorAll(".battle-card .tx-hearsay").forEach((el) => {
      const open = S.hearOpen != null && S.hearOpen === S.main.card_id;
      el.classList.toggle("open", open);
      el.setAttribute("data-act", "hear-more");
      el.setAttribute("role", "button");
      el.setAttribute("tabindex", "0");
      el.setAttribute("aria-expanded", String(open));
    });
  }

  function hearToggle(el) {
    const open = !el.classList.contains("open");
    S.hearOpen = open ? S.main.card_id : null;
    el.classList.toggle("open", open);
    el.setAttribute("aria-expanded", String(open));
  }



  // 浮在最上層的那幾層（要事清單、此地可為「全部」、點人物、對話框、往來紀錄、設定抽屜）開著時：底下的頁面不跟著手指捲
  // （Joy 11/6「點開要事的時候 手指滑動畫面會是拖曳要事下面的首頁部分」）。iOS 的 Safari 不理 body 的 overflow，所以把頁面釘住
  // （position: fixed＋記下捲到哪），收起時捲回原處；層自己能捲的那一塊（.sheet、.tl-body、.vn-menu）照常捲、捲到底不帶動頁面（overscroll-behavior）
  const LAYER_SEL = ".sheet, .vn-layer";
  let lockedAt = null;
  function syncScrollLock() {
    const body = document.body;
    if (!body || !body.classList) return;
    const open = !!document.querySelector(LAYER_SEL);
    if (open && lockedAt === null) {
      lockedAt = window.scrollY || 0;
      body.style.top = `-${lockedAt}px`;
      body.classList.add("layer-open");
    } else if (!open && lockedAt !== null) {
      const y = lockedAt;
      lockedAt = null;
      body.classList.remove("layer-open");
      body.style.top = "";
      window.scrollTo(0, y);
    }
  }
  if (typeof MutationObserver === "function" && document.body) new MutationObserver(syncScrollLock).observe(document.body, { childList: true, subtree: true });

  function afterPage() {
    watchOrders(); // 入伍段第一步：軍令卡在畫面上才算看過（離開江湖頁、框不是第一步時它自己收掉）
    if (S.tab === "jianghu") {
      // 「剛剛」收著卻其實放得下：拿掉底下的淡出與「展開全文」（A4）
      const now = document.querySelector(".now.clamp");
      const body = now && now.querySelector(".tx-now");
      if (body && body.scrollHeight <= body.clientHeight + 1) now.classList.replace("clamp", "fits");
      fitFirstRound(); // 戰鬥卡片收著的第一回合最多兩行，放不下就只留數字（PM 2026-10-05）
      sensePadReady(); // 有所感的畫布：接上手指、補畫已經畫好的那一筆
      decorateHearsay(); // 戰鬥卡片底下聽來的那一句收成一行（FB-074）
      fitFirstScreen(); // 最後：第一屏放不下行動列時一步一步收（FB-107）
    }
    if (S.tab === "map") mapReady();
    if (typeof bpAfter === "function") bpAfter(); // 決戰的關鍵時刻（battle.js）：開打、主將重創、敗走、收場蓋上來演一下
  }

  // ── 登入與取名號 ──
  // 登入頁最上面的宣傳影片（企劃者 2026-10-12「我要在我們登入頁面加這個主要宣傳影片」）：手機擋有聲自動播放，所以靜音、
  // 自動播放、循環、playsinline，右下角一顆開聲音；首格 promo-poster.jpg 在影片載入前先顯示，偏好減少動態效果的人只看首格。
  // 只在登入頁：登入、註冊兩頁切換時（renderGate 重畫）把同一支影片搬回去，不會從頭播、聲音開著的也不會被關掉
  const PROMO_POSTER = "/static/promo-poster.jpg";
  const promoCalm = () => !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  function promoHtml() {
    if (promoCalm()) return `<figure class="promo"><img src="${PROMO_POSTER}" alt="天下大勢宣傳影片的首格"></figure>`;
    return `<figure class="promo">
      <video src="/static/promo.mp4" poster="${PROMO_POSTER}" muted autoplay loop playsinline preload="auto" aria-label="天下大勢宣傳影片"></video>
      <button class="promo-sound" type="button" data-act="promo-sound" aria-pressed="false">🔇 開聲音</button>
    </figure>`;
  }
  function promoSound(el) {
    const v = el.closest(".promo") && el.closest(".promo").querySelector("video");
    if (!v) return;
    v.muted = !v.muted;
    if (!v.muted && v.paused) v.play().catch(() => {});
    el.setAttribute("aria-pressed", String(!v.muted));
    el.textContent = v.muted ? "🔇 開聲音" : "🔊 關聲音";
  }

  function renderGate() {
    const reg = S.gateMode === "register";
    const playing = $app.querySelector(".gate .promo");
    $app.innerHTML = `
      <div class="gate has-promo">
        ${promoHtml()}
        <div class="brand"><h1>天下大勢</h1><p>亂世江湖，從潁川城門口開始</p></div>
        <div class="seg">
          <button class="${reg ? "" : "on"}" data-act="gate" data-mode="login">登入</button>
          <button class="${reg ? "on" : ""}" data-act="gate" data-mode="register">註冊</button>
        </div>
        <form id="gate-form" class="card">
          <label class="field"><span>帳號</span><input class="input" name="login" autocomplete="username" autocapitalize="off" ${reg ? 'placeholder="英文字母、數字、底線，3～20 字"' : ""} required></label>
          <label class="field"><span>密碼</span><input class="input" type="password" name="password" autocomplete="${reg ? "new-password" : "current-password"}" ${reg ? 'placeholder="至少 6 字"' : ""} required></label>
          ${reg ? '<label class="field"><span>再輸入一次密碼</span><input class="input" type="password" name="again" autocomplete="new-password" required></label>' : ""}
          <p class="form-msg" role="alert"></p>
          <button class="btn primary" type="submit">${reg ? "註冊" : "登入"}</button>
        </form>
        <section class="gate-patch" id="gate-patch" aria-label="近期改版">${gatePatchHtml(S.patchNotes)}</section>
      </div>`;
    if (playing) $app.querySelector(".gate .promo").replaceWith(playing);
    if (S.patchNotes === undefined) loadPatchNotes();
  }

  // 登入頁的近期改版（Joy 2026-10-21「登入首頁加改版資訊」）：登入表單底下一塊，最新一次的新功能、調整一項一行，更早的各收成一行、
  // 點了攤開。字是伺服器讀 content/patch_notes.json 給的（/api/patch_notes，不用登入，新的在前）；讀不到或沒有就不畫
  function patchLines(p) {
    return [["新功能", p.new], ["調整", p.tweak], ["修正", p.fix]].filter(([, rows]) => rows && rows.length)
      .map(([head, rows]) => `<h4>${head}</h4><ul>${rows.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>`).join("");
  }
  function gatePatchHtml(notes) {
    if (!notes || !notes.length) return "";
    const [top, ...older] = notes;
    return `<div class="card patch-card"><h3>改版資訊 ${esc(top.date)}</h3>${patchLines(top)}${
      older.map((p) => `<details class="patch-old"><summary>改版資訊 ${esc(p.date)}</summary>${patchLines(p)}</details>`).join("")}</div>`;
  }
  async function loadPatchNotes() {
    S.patchNotes = null; // 讀著，不重複讀
    try {
      const r = await fetch("/api/patch_notes");
      S.patchNotes = r.ok ? (await r.json()).notes || [] : [];
    } catch (e) { S.patchNotes = []; }
    const box = document.getElementById("gate-patch");
    if (box) box.innerHTML = gatePatchHtml(S.patchNotes);
    if (S.stage === "game" && S.tab === "jianghu" && patchUnseen().length) renderPage(); // 進了遊戲才讀到：有沒看過的就跳
  }
  // 進遊戲後跳一次的改版資訊（Joy 2026-11-07「以前改版資訊是在登入那邊 但是現在幾乎不會到那頁 因為會記錄session」）：
  // 有這支手機還沒看過的新版就從底下跳一張，照給玩家的格式【天下大勢　改版資訊 M/D】、新功能／調整／修正一項一行；按「知道了」就關、
  // 記下最新那一次，下一次改版才再跳。好幾次沒看的：最新那次攤開，其餘各收成一行。序章裡、特殊事件的跳顯框還沒看完先不跳；
  // 這支手機從沒看過任何一次的只給最新那一次。簽到小窗排在它後面（同一刻只跳一張）。記不住（私密視窗）就這一次關了算數
  const PATCH_SEEN = "tianxia.patchSeen";
  const PATCH_OK = "知道了";
  // 認一次改版：日期加三段各幾條（同一天補發一次也算新的）
  const patchKey = (p) => `${p.date}|${["new", "tweak", "fix"].map((k) => (p[k] || []).length).join(",")}`;
  function patchUnseen() {
    const notes = S.patchNotes || [];
    if (S.patchSeen === undefined) { try { S.patchSeen = localStorage.getItem(PATCH_SEEN) || ""; } catch (e) { S.patchSeen = ""; } }
    const at = notes.findIndex((p) => patchKey(p) === S.patchSeen);
    return at < 0 ? notes : notes.slice(0, at);
  }
  function patchPopHtml(m) {
    if (pro() || (m.story_cards || []).length) return "";
    if (!S.patchNotes) return ""; // 進遊戲那一刻（enter）才讀一次；還沒讀到不跳
    const [top, ...older] = patchUnseen();
    if (!top) return "";
    return `<div class="sheet-bg" data-act="patch-close"></div><div class="sheet patch-pop" role="dialog" aria-label="改版資訊"><div class="grip"></div>`
      + `<div class="patch-card"><h3>【天下大勢　改版資訊 ${esc(top.date)}】</h3>${patchLines(top)}`
      + `${(S.patchSeen ? older : []).map((p) => `<details class="patch-old"><summary>改版資訊 ${esc(p.date)}</summary>${patchLines(p)}</details>`).join("")}</div>`
      + `<button class="btn primary patch-ok" data-act="patch-close">${PATCH_OK}</button></div>`;
  }
  function patchPopClose() {
    const top = (S.patchNotes || [])[0];
    if (!top) return;
    S.patchSeen = patchKey(top);
    try { localStorage.setItem(PATCH_SEEN, S.patchSeen); } catch (e) { /* 私密視窗：這一次關了算數 */ }
  }

  function renderCreate() {
    $app.innerHTML = `
      <div class="gate">
        <div class="brand"><div class="seal">勢</div><h1>天下大勢</h1><p>這個帳號還沒有角色</p></div>
        <form id="create-form" class="card">
          <label class="field"><span>取一個名號，踏入江湖</span><input class="input" name="name" maxlength="16" placeholder="例如：沈青衫" required></label>
          <fieldset class="sex-pick"><legend>以什麼身分行走江湖（建了就不能改）</legend>
            ${[["男", "少俠", HERO_FIGURES.男.src], ["女", "女俠", HERO_FIGURES.女.src]].map(([v, hero, src], i) => `
            <label class="sex-tile"><input type="radio" name="gender" value="${v}" ${i ? "" : "checked"}>
              <img src="${src}" alt="" aria-hidden="true"><span>${hero}<small>${v}</small></span></label>`).join("")}
          </fieldset>
          <p class="form-msg" role="alert"></p>
          <button class="btn primary" type="submit">建立角色</button>
        </form>
        <button class="linkish" data-act="logout">換一個帳號</button>
      </div>`;
  }


  const QUALITY_SEAL = { 下品: ["下", "q1"], 中品: ["中", "q2"], 上品: ["上", "q3"], 絕學: ["絕", "q4"] };
  const seal = (q, big = false) => {
    const [ch, cls] = QUALITY_SEAL[q] || ["？", "q1"];
    return `<span class="qseal ${cls}${big ? " big" : ""}">${ch}</span>`;
  };
  // 武學重構：品級是武學本身的（合出來、自創時就定了），沒有「修練衝品」的機率條了；意境裝進槽裡是技能（slotsHtml）

  // 功法卡、人物卡（伺服器的 Markdown）裡的十成進度「●●●○○○○○○○」換成跟卷軸卡同一種格子（企劃者 10/6：不要圈圈）。
  // 只換剛好十個圈的那一串，換成的是固定的標記，不帶任何伺服器的字
  const tenCells = (html) => String(html || "").replace(/[●○]{10}/g, (run) =>
    `<span class="ten mini" role="img" aria-label="第${[...run].filter((c) => c === "●").length}成">${[...run].map((c) => `<i${c === "●" ? ' class="on"' : ""}></i>`).join("")}</span>`);


  const meltNum = (n) => (n > 0 ? `+${n}` : String(n).replace("-", "−"));

  // ── 修練頁最上面的人物面板（企劃者 2026-10-12：照她給的人物剪影與版面改一版）──
  // 剪影（web/hero.webp、hero-f.webp，去背過的）身上的光點各對上一樣真的東西：身上的兩門、四欄裝備（屬性不放上去，企劃者 2026-10-12「亂七八糟的」，
  // 配點照舊在狀態列）。座標是剪影圖的百分比（照圖上的光點量的），side 是名字標在點的哪一邊。點了底下那一格寫它現在是什麼，
  // 多一顆「看這一門／看這件」捲到下面那張卡。點哪一個記在 S.heroNode（只是看的方式，輪詢重畫不跳回去）
  // 男女各一張剪影（企劃者 2026-10-12：之後創角色要選性別），光點各照自己那張圖量；status.gender 是「女」就用女版，其餘（還沒有性別的角色）男版。
  // 兩張的光點對上同樣六樣東西，只是位置不同；女版的寶物是腰間的佩飾、武學在手肘
  const HERO_FIGURES = {
    男: { src: "/static/hero.webp", ratio: "674 / 900", nodes: [
      { key: "weapon", kind: "gear", x: 52.0, y: 15.1, side: "r" },
      { key: "treasure", kind: "gear", x: 20.3, y: 21.4, side: "l" },
      { key: "armor", kind: "gear", x: 47.7, y: 24.2, side: "r" },
      { key: "內功", kind: "art", x: 26.4, y: 38.7, side: "l" },
      { key: "武學", kind: "art", x: 50.0, y: 48.6, side: "r" },
      { key: "mount", kind: "gear", x: 51.8, y: 96.7, side: "l" },
    ] },
    女: { src: "/static/hero-f.webp", ratio: "693 / 900", nodes: [
      { key: "weapon", kind: "gear", x: 47.0, y: 17.5, side: "r" },
      { key: "armor", kind: "gear", x: 42.6, y: 23.6, side: "l" },
      { key: "武學", kind: "art", x: 47.2, y: 33.8, side: "r" },
      { key: "內功", kind: "art", x: 25.0, y: 38.1, side: "l" },
      { key: "treasure", kind: "gear", x: 35.8, y: 45.3, side: "r" },
      { key: "mount", kind: "gear", x: 50.1, y: 96.9, side: "l" },
    ] },
  };
  const HERO_GEAR_NAMES = { weapon: "武器", armor: "防具", mount: "坐騎", treasure: "寶物" };
  const GEAR_ICONS = {
    weapon: '<path d="M14.5 17.5L3 6V3h3l11.5 11.5M13 19l6-6M16 16l4 4M19 21l2-2"/>',
    armor: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/>',
    mount: '<path d="M4 18c1-4 3-6 6-7l2-5 3 2 3-1-1 4 3 3-2 1-2-2c-2 1-3 3-3 6M8 18v3m8-4v4"/>',
    treasure: '<path d="M12 2l3 6.5 7 .8-5.2 4.8 1.5 7-6.3-3.6-6.3 3.6 1.5-7L2 9.3l7-.8z"/>',
  };
  const ringWord = (colors) => ((colors || []).length ? `收${colors.join("")}` : "任意皆收"); // 待 joy 潤
  // 意境的強度（一重～三重）畫成三節玉
  const lvHtml = (n) => `<span class="lv" role="img" aria-label="${["", "一重", "二重", "三重"][Math.max(1, Math.min(3, n | 0))]}">${[1, 2, 3].map((k) => `<i${k <= (n | 0) ? ' class="on"' : ""}></i>`).join("")}</span>`;
  // 修練頁卡上的評分；槽裡有不發動的秘方特效時底下一行小字（skillview.score_note，Joy 2026-10-28「要讓玩家能清楚知道」）
  const scoreHtml = (a) => (typeof a.score === "number" ? `<span class="score">評 ${a.score}${a.score_note ? `<small>${esc(a.score_note)}</small>` : ""}</span>` : "");
  // 自創武學也走同一條梯子（Joy 2026-10-21「那武學呢 有分？」）：撞到幾樣稀有（create.marks_of：純或渾、招已透、稀有路數）
  const ART_LOOK_STEPS = [["凡", "三樣稀有一樣都沒撞到"], ["佳", "撞到一樣：三格同是單色或任色、招已透、稀有路數"], ["珍", "撞到兩樣"], ["神", "三樣全撞到：最好的一級"]];
  // 招的印記（招式與絕學稿案第一節）：伺服器寫「看家〔拄棍守村〕應招・…」「本命〔…〕」「絕〔…〕」「沈〔…〕」（自創：創的人名號第一個字），
  // 開頭那幾個字畫成一枚印——看家墨印、本命朱印、絕金印、其餘是私印；後面照字寫
  const TSEAL = { 看家: "ink", 本命: "red", 絕: "gold", 後勁: "gold" };
  const tsealHtml = (word) => `<b class="tseal ${TSEAL[word] || "own"}">${esc(word)}</b>`;
  // 純文字版（清單的小字、title）：「掠影二重・流光」
  const fxText = (fx) => (Array.isArray(fx) ? fx.map((e) => (e.idle ? `${e.name}（不發動）` : e.grand || e.special ? e.name : `${e.name}${FX_LAYERS[e.layers] || ""}`)).join("・") : "");

  // 功法卡上的小圖（一門武學的圖示）：裁到人形那一塊
  const figSvg = (P, weapon, cls) => `<svg class="fig${cls ? ` ${cls}` : ""}" viewBox="30 40 160 200" aria-hidden="true">${figBody(P, weapon, false)}</svg>`;

  // 還沒起意、心得不夠開始自創：還差幾點（0＝夠了或已經起意）。伺服器在執器那一步就看心得（create.begin_problem），立意那一刻才收
  const createShort = (c) => (c && !c.draft && !c.problem ? Math.max(0, (c.price | 0) - (c.xinde | 0)) : 0);
  const CN_NUM = "〇一二三四五六七八九十";
  const cnNum = (n) => n <= 10 ? CN_NUM[n] : n < 20 ? `十${CN_NUM[n - 10]}` : `${CN_NUM[Math.floor(n / 10)]}十${n % 10 ? CN_NUM[n % 10] : ""}`;
  const SHOP_ATTR = { 剛: "gang", 快: "kuai", 柔: "rou", 慢: "man" };

  // 共用的店面框（1.2）：招牌、銀兩、掌櫃那一句、左上「出店」；底下照哪一間店畫。懸賞榜的第三層（替一張求兵挑東西）
  // 選單上沒有 bounty:back：出店先送回到懸賞榜（boardLeave）。三間店捲的那一層（.shop-body）裡面一律再包一層 .shop-col：
  // 電腦上整片寬的 .shop-body 照舊捲，內容照遊戲那一欄排（style.css 的 FB-225 那一段；手機上 .shop-col 沒有樣式）
  function shopHtml(shop) {
    const kind = shop.shop || "smith";
    // 商城（商城第二批）：網頁自己開的那一層（mallShop），出店只是收起來、不送伺服器
    const back = kind === "mall" ? '<button class="shop-back" data-act="mall-close">‹ 出店</button>'
      : shop.picked ? '<button class="shop-back" data-act="shop-leave">‹ 出店</button>'
      : `<button class="shop-back" data-act="choose" data-id="${esc(shop.back)}">‹ 出店</button>`;
    // 鐵匠講神器的規矩（背包有四階時，shop.rule；設計 9.1 第 2 批甲）：就畫在平常那一句的位置、金框標出來；順口講配方線索那一下伺服器給空的
    // shop.said：商城掌櫃那一句換成買成了的那一句（said ok）或買不了的原因（said no），左邊那條線換色
    // 打造頁就地熬了一個（鐵匠鋪與合成流程 3.3）：鐵匠那一句換成素材頁的結果句（熬出了什麼，不是投的屬性也照寫），放料、換頁就換回來
    const brewed = kind === "smith" && S.shopNote && smithTab(shop) === "forge";
    const line = brewed ? `<p class="shop-line brewed" role="status">${esc(S.shopNote)}</p>`
      : shop.rule ? `<p class="shop-line rule">${esc(shop.rule)}</p>`
      : `<p class="shop-line${shop.said ? ` ${esc(shop.said)}` : ""}">${kind === "dadian" ? sayHtml(shop.line) : kind === "mall" ? nbHtml(shop.line, MALL_SAY_AFTER) : esc(shop.line)}</p>`; // 打點：掮客那一句不在詞中間斷（FB-433）；商城見 MALL_SAY_AFTER
    // 鐵匠鋪的架上頁照草圖 A 把鐵匠那一句放在爐火底下（smithHtml 畫，企劃者 2026-10-14）；其他頁、馬市、懸賞榜緊接招牌
    const underForge = kind === "smith" && smithTab(shop) === "shelf";
    const body = kind === "mall" ? mallHtml(shop) : kind === "market" ? marketHtml(shop) : kind === "board" ? boardHtml(shop) : kind === "arena" ? arenaHtml(shop)
      : kind === "donate" ? donateHtml(shop) : kind === "dadian" ? dadianHtml(shop) : kind === "tavern" ? tavernHtml(shop) : smithHtml(shop, underForge ? line : "");
    // 擂台打到一半：左上那一顆是認輸（先問一次），不是直接離開
    const leave = kind === "arena" && shop.fight
      ? `<button class="shop-back" data-act="shop-ask" data-id="${esc(shop.fight.yield.id)}" data-confirm="${esc(shop.fight.yield.confirm)}" data-yes="認輸">‹ 認輸</button>`
      : kind === "arena" ? back.replace("‹ 出店", "‹ 離開") : back;
    const purse = kind === "mall" ? `${ingotSvg()}元寶 ${shop.balance | 0}` : shop.purse ? esc(shop.purse) : `銀 ${shop.silver | 0}`;
    return `<div class="shop-layer shop-${esc(kind)}" role="dialog" aria-label="${esc(shop.sign)}">
      <header class="shop-bar">${leave}<span class="shop-sign">${esc(shop.sign)}</span><span class="shop-silver">${purse}</span></header>
      ${underForge ? "" : line}
      ${body}
    </div>`;
  }



  // 上一下的結果那一句（素材頁、軍需帳）：升階出了什麼、賣了多少、捐了多少，或為什麼不成；換頁、出店清掉。
  // 那一格一直在、高度固定兩行（還沒做事時寫伺服器給的 hint）：結果冒出來不把底下的格子往下推，連點同一格升兩次不會點偏
  function shopNoteHtml(hint = "") {
    return S.shopNote ? `<p class="shop-done" role="status">${esc(S.shopNote)}</p>` : `<p class="shop-done hint" role="status">${esc(hint)}</p>`;
  }


  // 素材頁、軍需帳的動作：送 /api/do/<op>，回來照新的畫面畫，結果的第一句記在 S.shopNote（升階出了什麼）
  async function shopDo(op, body, after) {
    await busy(async () => {
      const r = await api(`/api/do/${op}`, body);
      const first = /<p>([\s\S]*?)<\/p>/.exec(r.message || "");
      S.shopNote = (first ? first[1] : r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim() || null;
      if (after) after(r);
      setMain(r.main);
      renderKeepingShop();
    });
  }

  // 店裡做了一件事之後整個重畫（狀態列的銀兩也要換），店裡捲到哪裡、打到一半的字照放回去：不然在酒肆往下捲去打聽素材，
  // 按一下就跳回頂上、剛打的字也沒了（Joy 2026-10-19「酒肆操作沒兩下很容易就跑版了」）。店收了、換了一間照常從頂上開始
  function shopSpot() {
    const layer = document.querySelector(".shop-layer");
    if (!layer) return null;
    return {
      shop: layer.className,
      top: layer.querySelector?.(".shop-body")?.scrollTop || 0,
      left: layer.querySelector?.(".stalls")?.scrollLeft || 0, // 馬廄那一排左右滑到哪（第三節）
      kept: [...(layer.querySelectorAll?.("input[data-keep]") || [])].map((el) => [el.dataset.keep, el.value, el === document.activeElement]),
    };
  }
  function putShopSpot(spot) {
    const layer = document.querySelector(".shop-layer");
    if (!spot || !layer || layer.className !== spot.shop) return;
    for (const [k, v, focused] of spot.kept) {
      const el = document.querySelector(`.shop-layer input[data-keep="${k}"]`);
      if (!el) continue;
      el.value = v;
      if (focused) el.focus?.({ preventScroll: true });
    }
    const body = spot.top ? document.querySelector(".shop-layer .shop-body") : null;
    if (body) body.scrollTop = spot.top;
    const stalls = spot.left ? document.querySelector(".shop-layer .stalls") : null;
    if (stalls) stalls.scrollLeft = spot.left;
  }
  function renderKeepingShop() {
    const spot = shopSpot();
    render();
    putShopSpot(spot);
  }






  // 只重畫店面那一層（輪詢、爐裡換了東西）；畫面上還沒有那一層就整個重畫。店裡捲到哪裡照放回去（往下捲去點素材格，
  // 放進爐裡不能跳回頂上）；換頁（keep 為假）從頂上開始
  function renderShop(keep = true) {
    const layer = document.querySelector(".shop-layer");
    if (!layer || !S.main || !S.main.shop) { render(); return; }
    const spot = shopSpot();
    if (!keep) { spot.top = 0; spot.left = 0; }
    layer.outerHTML = shopHtml(S.main.shop);
    putShopSpot(spot);
    if (typeof ringSync === "function") ringSync(); // 擂台動畫（arena_anim.js）：這一回合打完的樣子，接著演
  }

  // 輪詢拿到新的畫面（refreshPage 最前面叫）：店面開了或收了整個重畫；開著而且店裡的資料變了只重畫店面（手指按著時等放開，
  // 同江湖頁的規則）。回 true：店面開著，底下的頁面被蓋住、不必再畫
  function shopPolled(old) {
    const was = old && old.shop ? old.shop.shop : null, now = S.main && S.main.shop ? S.main.shop.shop : null;
    if (was !== now) { render(); return true; } // 開了、收了、換了一間：整個重畫
    if (!now) return false;
    if (JSON.stringify(old.shop) !== JSON.stringify(S.main.shop)) {
      // 打造頁熬過的結果那一句蓋著鐵匠那一句（3.3）：鐵匠那一句換了（伺服器那一刻說了別的）就收起；沒換的照舊蓋著，讓人看完
      if (now === "smith" && S.shopNote && old.shop.line !== S.main.shop.line && smithTab(S.main.shop) === "forge") S.shopNote = null;
      if (pointerHeld) redrawHeld = true;
      else { renderShop(); if (now === "smith" && S.shopPot && (S.shopPot.main || S.shopPot.aux)) updateSmithLine(); }
    }
    return true;
  }

  // 店裡的換上、拆解、神器定名，裝備庫那一列的修、淬煉、批量拆解（3.4）：走修練頁那幾條（/api/menxia/…），回來照新的畫面畫、話用提示泡泡講。
  // 捲到哪裡照放回去（renderKeepingShop）：裝備庫往下捲到那一列按修、淬（上品淬七次），不能每按一下就跳回頂上
  async function shopMx(op, body) {
    let said = "";
    await busy(async () => {
      const r = await api(`/api/menxia/${op}`, body);
      if (r.menxia) S.menxia = r.menxia;
      setMain(r.main);
      renderKeepingShop();
      said = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      if (said) toast(said);
    });
    return said; // 店面上定名被拒時，表單裡留這一句（FB-193）
  }

  const reduceMotion = () => !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);



  // ── 見聞 ──
  // 第一季的傳聞分四層（傳聞分層設計第二節）：天下大事、陣營軍情、所在大區、個人線索，各一張卡。
  // 標題是伺服器給的字（這裡跳脫），內容是伺服器轉好、跳脫過的 HTML；開關關著時沒有 rumor_layers，照舊畫一整張 rumors
  function rumorLayersHtml(layers) {
    return layers.map((l) => `<div class="card rumor-layer" data-layer="${esc(l.id)}"><h3>${esc(l.title)}</h3>${l.body}</div>`).join("");
  }


  // 見聞的「榜單」（leaderboard.view）：上面一排六張榜的籤，一次看一張（S.board，預設第一張）；前十名，你在榜上標出來，
  // 不在前十名時底下多一行你排第幾。名號與那一段都是伺服器給的原文，這裡跳脫
  // 榜單的神器譜（Joy 2026-10-17 從江湖史搬過來）：不排名，照季分段、新的一季在前；一筆一列，名字一行、種類屬性與在誰手上一行
  function bookRows(book) {
    if (!book.length) return '<p class="muted">還沒有人打出神器。</p>';
    let out = "", season = null;
    for (const r of book) {
      if (r.season !== season) { out += `${season === null ? "" : "</ul>"}<p class="book-season">第 ${Number(r.season)} 季</p><ul class="board-book">`; season = r.season; }
      // 每一筆點得開那一把的唯讀卡（Joy 2026-10-22）；舊伺服器沒給 ref 就照舊只列字
      out += r.ref
        ? `<li><button class="board-open" data-act="board-card" data-board="神器" data-season="${Number(r.season)}" data-ref="${esc(r.ref)}"><span class="bk-txt"><b>${esc(r.name)}</b><small>${esc(r.text)}</small></span><span class="board-go" aria-hidden="true">›</span></button></li>`
        : `<li><b>${esc(r.name)}</b><small>${esc(r.text)}</small></li>`;
    }
    return out + "</ul>";
  }
  function boardsHtml(b) {
    if (!b) return '<p class="muted">載入中…</p>';
    const list = b.boards || [];
    if (!list.length) return '<div class="card"><p class="muted">還沒有榜單。</p></div>';
    const cur = list.find((x) => x.id === S.board) || list[0];
    const tabs = `<div class="board-tabs">${list.map((x) => `<button class="${x.id === cur.id ? "on" : ""}" data-act="board" data-board="${esc(x.id)}">${esc(x.title)}</button>`).join("")}</div>`;
    // 武學榜、內功榜的一列點得開主人那一門的唯讀功法卡（Joy 2026-10-22「上榜的武學其他玩家應該要可以點的開來看卡」），列尾一個 ›
    const open = BOARD_CARDS.includes(cur.id);
    const cells = (r) => `<span class="board-rank">${Number(r.rank)}</span><span class="board-name">${esc(r.name)}</span><span class="board-text">${esc(r.text)}${r.sub ? `<small>${esc(r.sub)}</small>` : ""}</span>`;
    const row = (r) => `<li class="board-row${r.rank <= 3 ? " podium" : ""}${r.you ? " you" : ""}">${open
      ? `<button class="board-open" data-act="board-card" data-board="${esc(cur.id)}" data-name="${esc(r.name)}" aria-label="看${esc(r.name)}的${esc(r.text)}">${cells(r)}<span class="board-go" aria-hidden="true">›</span></button>`
      : cells(r)}</li>`;
    if (cur.book) return tabs + `<div class="card board"><h3>${esc(cur.title)}</h3><p class="muted board-note">${esc(cur.note)}</p>${bookRows(cur.book)}</div>`;
    const rows = cur.rows.length ? `<ol class="board-list">${cur.rows.map(row).join("")}</ol>` : '<p class="muted">尚無人留名。</p>';
    const mine = cur.mine ? `<p class="board-mine">你：第 ${Number(cur.mine.rank)} 名・${esc(cur.mine.text)}</p>` : "";
    return tabs + `<div class="card board"><h3>${esc(cur.title)}</h3><p class="muted board-note">${esc(cur.note)}</p>${rows}${mine}</div>`;
  }

  // 榜單點開的唯讀卡（Joy 2026-10-22）：S.boardCard = {loading, card, board}。武學、內功照主人修練頁那一張畫（印記、名字、品相、
  // 第幾成與評分、屬性與收什麼、意境槽、功法卡的字〔招寫在裡面，同修練頁點開詳情時〕），沒有任何鈕；神器照修練頁裝備那一列的料畫。伺服器 /api/board_card 給料
  const BOARD_CARDS = ["武學", "內功"];
  function boardArtHtml(a) {
    const level = Math.max(0, Math.min(10, a.level | 0));
    return `<div class="acard ro${a.quality === "絕學" ? " q4" : ""}">
      <div class="hd">${a.quality === "絕學" ? '<span class="qseal q4 big">絕</span>' : ""}<div><h3>${esc(a.name)}</h3><div class="sub">${[a.kind, a.quality, a.look].filter(Boolean).map(esc).join("・")}</div></div>${a.pose ? figSvg(a.pose, a.weapon, "card-fig") : ""}</div>
      ${a.tier && a.quality !== "絕學" ? lookLadder(a.tier, ART_LOOK_STEPS) : ""}
      <div class="train"><div class="tr-meter"><div class="tr-lv"><b>第${level}成</b>${scoreHtml(a)}</div>
        <div class="ten">${Array.from({ length: 10 }, (_, k) => `<i${k < level ? ' class="on"' : ""}></i>`).join("")}</div></div></div>
      <div class="lvline"><span>${esc(a.kind)}${a.attribute ? `・屬${esc(a.attribute)}` : ""}・收${esc(a.affinity || "")}</span></div>
      ${slotsHtml(a, null, true)}
      <div class="art-card">${tenCells(a.card)}</div>
    </div>`;
  }
  // 上品磨得慢（wear_note，鐵匠鋪與合成流程 3.6「上品的卡多一句」）接在鋒利度後面，同裝備庫那一列；神器原品、本命兵器一律上品
  function boardGearHtml(g) {
    const bits = [g.what, `屬${g.attribute}`, g.grade, g.tempers ? `淬煉 ${g.tempers | 0}/${g.temper_max | 0}` : "", g.edge != null && g.wear_word ? `${g.wear_word} ${g.edge | 0}` : "", g.wear_note || ""];
    return `<div class="acard ro gear-ro">
      <div class="hd"><div><h3>${esc(g.name)}</h3><div class="sub">${bits.filter(Boolean).map(esc).join("・")}</div></div></div>
      ${(g.tactic || []).map((t) => `<p class="art-tactic">${tacticHtml(t)}</p>`).join("")}
      <p class="muted board-owner">第 ${Number(g.season)} 季・在${esc(g.owner || "")}手上</p>
    </div>`;
  }
  function boardCardHtml() {
    const B = S.boardCard;
    const c = B.card;
    const body = B.loading ? '<p class="muted">……</p>'
      : !c ? '<p class="muted">這一張現在看不到了：榜單剛換過，或主人身上換了功夫。</p>'
      : B.board === "神器" ? boardGearHtml(c)
      : `<p class="board-owner">${esc(c.owner)}身上的${esc(B.board)}</p>${boardArtHtml(c)}`;
    return `<div class="sheet-bg" data-act="board-card-close"></div>
      <div class="sheet bcard-sheet" role="dialog" aria-label="${esc(c ? c.name : "看卡")}"><div class="grip"></div>
        ${body}
        <div class="row"><button class="btn ghost" data-act="board-card-close">關閉</button></div>
      </div>`;
  }
  async function openBoardCard(el) {
    const d = el.dataset;
    const q = d.board === "神器" ? `board=${encodeURIComponent("神器")}&season=${Number(d.season)}&ref=${encodeURIComponent(d.ref)}`
      : `board=${encodeURIComponent(d.board)}&name=${encodeURIComponent(d.name)}`;
    S.boardCard = { loading: true, board: d.board, card: null };
    render();
    try {
      const r = await api(`/api/board_card?${q}`);
      if (S.boardCard) { S.boardCard = { loading: false, board: d.board, card: r.card || null }; render(); }
    } catch (e) {
      if (S.boardCard) { S.boardCard = { loading: false, board: d.board, card: null }; render(); }
    }
  }


  // 見聞的籤（NEWS，減法季批 1 起五顆）：大事（戰報、大勢、形勢在它底下再分一排小的）、傳聞、榜單、江湖史、紀錄（紀錄、名帖匣再分）。
  // 「形勢」只有〈天下形勢〉開著的季（main.xingshi）才畫。行狀是從「俠客」頁進來的（SELF_NEWS）：那一段最上面不畫見聞的籤，畫一行「‹ 俠客」回去
  const newsPart = (id) => NEWS.find((n) => (n.parts || [n.id]).includes(id));
  const selfNews = (id) => SELF_NEWS.find((n) => n.id === id);
  function newsSegHtml(m) {
    const self = selfNews(S.news);
    if (self) return `<div class="self-sub"><button class="linkish back" data-act="tab" data-tab="practice">‹ 俠客</button><h3>${esc(self.name)}</h3></div>`;
    const at = newsPart(S.news);
    const top = `<div class="seg news-seg">${NEWS.map((n) => `<button class="${at === n ? "on" : ""}" data-act="news" data-news="${n.id}">${n.name}</button>`).join("")}</div>`;
    if (!at || !at.parts) return top;
    const parts = NEWS_PARTS.filter((n) => at.parts.includes(n.id) && (n.id !== "xingshi" || (m && m.xingshi)));
    return top + `<div class="seg news-sub">${parts.map((n) => `<button class="${S.news === n.id ? "on" : ""}" data-act="news" data-news="${n.id}">${n.name}</button>`).join("")}</div>`;
  }


  // 見聞・大事的「大勢」那一段最上面（減法季批 1）：三方卡（以前本週卡的「為什麼」也有）、本週江湖大事（以前江湖頁「大事」小標的面板）、
  // 三條戰況與軍備（以前在江湖頁行動列底下，6.3 拿掉）。都沒有就是空字串
  function trendsTopHtml(m) {
    const sides = m.sides_card ? `<details class="card sides-card"><summary>三方</summary>${sidesTableHtml(m.sides_card)}</details>` : "";
    const bulletin = m.bulletin && m.bulletin.length && shown("board")
      ? `<section class="card bulletin"><h3>${esc(wkWord("this", "本週"))}江湖大事</h3>${m.bulletin.map((b) => `<div class="bulletin-item">${b}</div>`).join("")}${warHelp(m, "board")}</section>` : "";
    const fronts = (m.fronts && shown("fronts") ? frontsBlock(m) : "") + armsLine(m);
    return sides + bulletin + fronts;
  }


  function pageNews() {
    const seg = newsSegHtml(S.main);
    const m = S.main;
    let body = "";
    if (S.news === "reports") {
      const r = S.reports;
      if (!r) body = '<p class="muted">載入中…</p>';
      else if (S.taleOpen != null) body = taleHtml(S.tales[S.taleOpen]);
      else if (S.reportOpen && r.selected != null) body = `<div class="report-top"><button class="linkish back" data-act="report-list">‹ 全部戰報</button>${taleLink(r.tale_id)}</div><div class="card report-detail">${gaugeHtml(r.gauge)}${trailMoves(roundBlocks(r.detail, r.gauge, r.selected))}</div>`;
      else if (!r.list.length) body = `<div class="card">${r.detail}</div>`;
      else {
        // 決戰與奪璽單挑另外一組排在最上面，不跟遊歷野怪混在一起（Joy 2026-10-14「這種大事件的決戰不應該跟一般的放在一起被洗掉」）
        const item = (x) => `<button data-act="report" data-id="${x.id}">${esc(x.label)}</button>`;
        const big = r.list.filter((x) => x.big), rest = r.list.filter((x) => !x.big);
        body = (big.length ? `<p class="report-group">大戰</p><div class="list report-big">${big.map(item).join("")}</div>` : "")
          + (rest.length ? `${big.length ? '<p class="report-group">最近的仗</p>' : ""}<div class="list">${rest.map(item).join("")}</div>` : "");
      }
    } else if (S.news === "trends") body = `${trendsTopHtml(m)}<div class="card">${m.trends}</div>`;
    else if (S.news === "xingshi") body = xingshiHtml(S.xingshi);
    else if (S.news === "rumors") body = m.rumor_layers ? rumorLayersHtml(m.rumor_layers) : `<div class="card">${m.rumors}</div>`;
    else if (S.news === "chronicle") body = S.taleOpen != null ? taleHtml(S.tales[S.taleOpen]) : `${taleIndexHtml(m.tales)}<div class="card">${m.chronicle}</div>`;
    else if (S.news === "annals") body = annalsHtml(S.annals);
    else if (S.news === "boards") body = boardsHtml(S.boards);
    else if (S.news === "mingtie") body = mingtieBoxHtml(S.mingtie);
    else body = `<div class="card">${m.latest || ""}${m.journal || ""}${m.older || ""}${!m.latest && !m.journal ? '<p class="muted">還沒有紀錄。</p>' : ""}</div>`;
    return seg + body;
  }

  // ── 設定抽屜 ──
  // 性別（PM 2026-10-12）：建角色時選過的寫一行；還沒選過的舊角色選一次，先問一次（S.genderPick），選了就定了
  function genderRow(s) {
    if (s.gender_chosen) return `<p class="gender-row muted">性別：${esc(s.gender)}</p>`;
    if (S.genderPick) {
      const hero = S.genderPick === "女" ? "女俠" : "少俠";
      return `<div class="gender-row card"><p>往後以${hero}行走江湖？性別只能選這一次。</p>
        <div class="row"><button class="btn small" data-act="gender-go" data-value="${esc(S.genderPick)}">確定</button><button class="btn small ghost" data-act="gender-pick" data-value="">再想想</button></div></div>`;
    }
    return `<div class="gender-row"><span>性別（只能選一次）</span>
      <button class="btn small" data-act="gender-pick" data-value="男">男</button><button class="btn small" data-act="gender-pick" data-value="女">女</button></div>`;
  }


  // 成人內容（features/heroines；設計稿「三位女子出場」第三節，Joy 2026-11-06）：預設關；打開之前先跳確認卡，按了確認才送出。
  // 這一季的內容沒有女子時伺服器不給 main.heroines，這一格不出現。字句待 joy 潤
  function adultRow() {
    const h = S.main && S.main.heroines;
    if (!h) return "";
    if (S.adultAsk) {
      return `<div class="card adult-ask"><p>成人內容是成年角色之間、彼此情願的親密情節，只有你自己看得到，不會寫進傳聞、江湖史或列傳。</p>
        <p><b>我已年滿十八歲，願意看到成人內容。</b></p>
        <div class="row"><button class="btn small primary" data-act="adult-yes">確認</button><button class="btn small ghost" data-act="adult-no">取消</button></div></div>`;
    }
    return `<label class="toggle"><input type="checkbox" id="adult" ${h.adult ? "checked" : ""}> 成人內容（預設關；打開要確認年滿十八歲）</label>`;
  }

  async function adultSet(value) {
    await busy(async () => {
      const r = await api("/api/heroines/adult", { value });
      applyMain(r.main);
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      if (text) toast(text);
    }, SENT_WAITING);
  }

  function sheetHtml() {
    if (S.pushHow) return pushHowHtml(); // 「怎麼收到手機通知」自己一頁
    const s = S.main.status;
    // 「匿名行走」那一句是傳聞分層一新寫的說明（待 joy 潤）；測試只比對這一句（tests/figures/test_rumor_layers.py）
    return `
      <div class="sheet-bg" data-act="sheet-close"></div>
      <div class="sheet" role="dialog" aria-label="設定">
        <div class="grip"></div>
        <div class="top-row"><h3 style="flex:1">設定</h3>${S.main.admin ? `<a class="btn small ghost ad-entry" href="/admin">管理者工具 ›</a>` : ""}<button class="btn small ghost" data-act="sheet-close">關閉</button></div>
        ${genderRow(s)}
        ${renameRow()}
        ${adultRow()}
        ${pushRow()}
        <label class="toggle"><input type="checkbox" id="anon" ${s.anonymous ? "checked" : ""}> 匿名行走（只在地方傳聞裡不寫名號；天下大事、軍情、江湖史、排行照寫）</label>
        <div class="stack">
          <button class="btn" data-act="howto" aria-expanded="${!!S.howtoOpen}" aria-controls="howto">玩法說明</button>
          <button class="btn" data-act="do" data-op="skip_tutorial">略過新手引導</button>
          ${S.recap ? `<button class="btn" data-act="recap" aria-expanded="${!!S.recapOpen}">重看序章</button>` : ""}
          <label class="toggle"><input type="checkbox" id="hints-off" ${s.hints_off ? "checked" : ""}> 不再提示（碰到新玩法時的小提醒）</label>
        </div>
        ${S.howtoOpen ? `<div class="howto card" id="howto">${S.howtoFailed
          ? '<p class="muted">說明沒拿到，連不上伺服器。</p><button class="btn small" data-act="howto-retry">再試一次</button>'
          : S.howto || '<p class="muted">正在翻書……</p>'}</div>` : ""}
        ${S.recap && S.recapOpen ? `<div class="recap card">${S.recap}</div>` : ""}
        <details class="fold"><summary>修改密碼</summary><form class="fold-body" id="pw-form">
          <label class="field"><span>舊密碼</span><input class="input" type="password" name="old" autocomplete="current-password"></label>
          <label class="field"><span>新密碼</span><input class="input" type="password" name="new" autocomplete="new-password"></label>
          <label class="field"><span>再輸入一次新密碼</span><input class="input" type="password" name="again" autocomplete="new-password"></label>
          <p class="form-msg" role="alert"></p>
          <button class="btn" type="submit">修改密碼</button>
        </form></details>
        <div class="label">帳號</div>
        <button class="btn ghost" data-act="logout">登出</button>
      </div>`;
  }

  // 管理者動作的確認框（G3）：每一項按了都先問一次、問句說出後果。疊在設定抽屜上面、不重畫抽屜，
  // 選好的下拉選單、填好的重設密碼欄位都留著；按「取消」或旁邊的暗處就關掉，什麼都不送
  // opts.no：取消那一顆的字（自創作罷寫「再想想」，鐵匠鋪與合成流程 3.1）；opts.lines：問句底下一行一件的清單（批量拆解，3.4）；
  // opts.rich：text 是呼叫的人跳脫好的 HTML、opts.sub：問句底下一行淡字的 HTML（打造頁熬的小單：工錢後面的折扣原因、機率與上限，3.3）
  let askGo = null;
  function ask(text, yes, go, opts = {}) {
    closeAsk();
    askGo = go;
    // 清單一行切成不折行的小段（nbHtml，切在「→」後與「（」前）：320 寬「（淬過 3 次一起沒了）」會折在「一｜起」中間（FB-297 同一類）
    const lines = (opts.lines || []).length ? `<ul class="ask-list">${opts.lines.map((l) => `<li>${nbHtml(l)}</li>`).join("")}</ul>` : "";
    const sub = opts.sub ? `<p class="muted ask-sub">${opts.sub}</p>` : "";
    document.body.insertAdjacentHTML("beforeend", `
      <div class="ask-layer">
        <div class="ask-bg" data-act="ask-no"></div>
        <div class="ask" role="alertdialog" aria-modal="true" aria-labelledby="ask-text">
          <p id="ask-text">${opts.rich ? text : esc(text)}</p>${sub}${lines}
          <div class="row"><button class="btn" data-act="ask-no">${esc(opts.no || "取消")}</button><button class="btn danger" data-act="ask-yes">${esc(yes)}</button></div>
        </div>
      </div>`);
    document.querySelector('.ask [data-act="ask-no"]').focus();
  }
  function closeAsk() {
    document.querySelector(".ask-layer")?.remove();
    askGo = null;
  }

  // ── 載入各頁 ──
  async function loadMenxia() {
    S.menxia = await api(`/api/menxia${S.person ? `?person=${encodeURIComponent(S.person)}` : ""}`);
    trimPot();
    if (S.tab === "practice" || S.tab === "craft") renderPage();
    if (S.tab === "craft" && S.forgeSel.length) updateForgeLine(); // 爐裡那一樣的標記
  }

  // 打開輿圖、輪詢、做了動作之後：疊層每次重抓；底圖只在還沒有、或疊層的 key 換了（劇情開放了新地點）才抓。
  // 底圖沒換、輿圖已經畫著時只換記號與抽屜（不整頁重畫：整張山水換掉會閃、手勢會斷）
  async function loadMap() {
    const st = await api("/api/map/state");
    const fresh = !S.mapBase || S.mapBase.key !== st.key;
    if (fresh) S.mapBase = await api("/api/map/base");
    S.mapState = st;
    S.mapStateAt = Date.now();
    if (S.mapSel && !st.places[S.mapSel]) { S.mapSel = null; if (S.mapMode === "place") S.mapMode = "overview"; }
    if (S.tab !== "map") return;
    if (fresh || !document.getElementById("mk")) { renderPage(); return; }
    drawMarks();
    drawRoute();
    if (!typing()) redrawDrawer();
  }


  async function loadBoards() {
    S.boards = await api("/api/boards");
    if (S.tab === "news" && S.news === "boards") renderPage();
  }



  async function loadReports(id) {
    S.reports = await api(`/api/reports${id != null ? `?id=${id}` : ""}`);
    if (S.tab === "news") renderPage();
    if (S.reportOpen && S.reports.tale_id != null) await loadTale(S.reports.tale_id);
  }

  // 俠客頁原地重畫（Joy 2026-11-07「不要每次點門下、裝備那些按鈕，按完都給我跳置頂」）：捲到哪留在哪。
  // 換到比較短的分頁時，最多往上收到分頁鈕剛好在頂上（#page 撐高到那個位置還捲得到，不讓瀏覽器把頁面收回底部）
  function heroStay(draw) {
    const page = document.getElementById("page");
    const y = window.scrollY || 0;
    draw();
    const tabs = typeof document.querySelector === "function" ? document.querySelector("#page .hero-tabs") : null;
    if (!page || !page.style || !tabs || typeof tabs.getBoundingClientRect !== "function" || typeof window.scrollTo !== "function") return;
    const tabsTop = tabs.getBoundingClientRect().top + (window.scrollY || 0);
    const target = Math.min(y, Math.max(0, tabsTop - 8));
    const need = target + window.innerHeight - page.getBoundingClientRect().top - (window.scrollY || 0);
    page.style.minHeight = `${Math.max(0, Math.ceil(need))}px`;
    window.scrollTo(0, target);
  }
  async function goTab(tab) {
    const pg = document.getElementById("page");
    if (pg && pg.style) pg.style.minHeight = ""; // 俠客頁撐高的那一截（heroStay）換頁就放掉
    S.tab = tab;
    S.message = "";
    S.artOpen = null;
    S.artInfo = null; S.insOpen = null; S.libAll = false; S.rackAll = false; // 攤開的詳情、意境、列完的庫也收起（篩選留著）
    S.artNote = null; S.mxNote = null; S.meltNote = null;
    S.forgeResult = null; // 上一爐的結果也收起（篩選留著）
    S.forgeMade = null;
    S.book = false; // 武學譜是疊在煉製頁上的一本書：換分頁就闔上
    S.zhuan = null; clearTimeout(zhuanTimer); // 傳也一樣
    S.mtEdit = null; S.mtZoom = null; S.boardCard = null; // 名帖的畫布與放大的那一張、榜單點開的卡也收起
    S.taleOpen = null; // 戰記也闔上
    if (tab !== "map") stopPlay(); // 版圖變化的播放也停
    // 每一次打開輿圖都從第一層開始（減法季整合設計第七章：「全區」按過只這一次有效）；江湖頁的小地圖點了某一處另外挑好了（S.mapKeep）
    if (tab === "map" && !S.mapKeep) mapFirst();
    S.mapKeep = false;
    if (tab === "news") S.unseen = false;
    render();
    window.scrollTo(0, 0);
    try {
      if ((tab === "practice" || tab === "craft") && pro()) {
        // 序章裡打開修練、煉製頁本身就是一步（跟打開輿圖一樣先當一個動作送給伺服器）
        const r = await api("/api/do/view_tab", { tab });
        setMain(r.main);
        renderTop();
      }
      if (tab === "practice" || tab === "craft") await loadMenxia();
      if (tab === "map") {
        // 每一次打開輿圖都從第一層開始（減法季整合設計第七章：「全區」按過只這一次有效）；江湖頁的小地圖點了某一處另外挑好了（S.mapKeep）
        // 打開輿圖本身可能完成新手引導的一步，所以先當一個動作做
        const r = await api("/api/do/view_map", {});
        setMain(r.main);
        renderTop();
        await loadMap();
      }
      if (tab === "news" && S.news === "reports") await loadReports(null);
      if (tab === "news" && S.news === "annals") await loadAnnals();
      if (tab === "news" && S.news === "xingshi") await loadXingshi();
      if (tab === "news" && S.news === "boards") await loadBoards();
      if (tab === "news" && S.news === "mingtie") await loadMingtie();
    } catch (e) { /* api() 已經提示過 */ }
  }

  // ── 動作 ──
  // ── 送出指令的回饋 ──
  // Joy 2026-10-12「要有機制讓玩家知道指令有送出，只是在等伺服器回應」）：每一個走 busy() 的動作都一樣——
  // 按下去的那一顆馬上標「送出中」（.sending：掃光、不能再按）；過了 WAIT_HINT_MS 還沒回來，畫面底下浮一行「已送出，等候回應…」，
  // 再久改寫「伺服器還在處理」；回來了就收掉。上一個指令還沒回來時再按別的：以前一聲不響地丟掉（玩家以為按了沒反應），現在浮同一行講一聲。
  // 失敗（伺服器擋下來、連不上、逾時）由 api() 用提示泡泡講，按鈕還原、可以再按。
  const WAIT_HINT_MS = 1500; // 過了這麼久還沒回來，浮一行等候的話（照行動換句，waitLineFor）
  const SLOW_HINT_MS = 12000; // 再久改寫 SLOW_WAITING
  // 等候的話照行動換（PM 2026-10-12 轉 Joy「弄個符合我們世界觀的句子」，字照抄）
  const WAIT_LINES = {
    explore: "四下探看，尚無動靜……", train: "循著蹤跡尋敵……", rest: "調息入定……", meet: "遣人通報，候他回話……",
    move: "整頓行裝……", forge: "爐火正旺，靜待出爐……", battle: "軍令已發，靜候陣前回報……",
    discuss: "兩人各陳所學，推敲新招……", // 論武答應、等首創取名（FB-117；待 joy 潤）
    sortie: "整隊出陣，候前方回報……", // 出陣開著時的 act:train（出陣探索與地盤設計第七節；待 joy 潤）
    gather: "四下翻找，看看能撿到什麼……", seek: "四處走走，看這一帶有什麼事……", sense: "靜心凝神……", // 探索三選一（待 joy 潤）
    "gather:say": "你邊找邊盤算……", // 找素材的「自己說」（第 32 項；待 joy 潤）；其他分支照找素材那一句
  };
  const SENT_WAITING = "墨跡未乾，江湖尚未回音……"; // 沒列到的行動
  const SLOW_WAITING = "路遠消息遲，再等片刻……";
  const STILL_WAITING = "前一道號令尚未回音";
  // 選項 id → 等候的話
  function waitLineFor(id) {
    const key = String(id || "");
    if (key === "act:explore") return WAIT_LINES.explore;
    if (key === "act:train") return S.main && S.main.sortie ? WAIT_LINES.sortie : WAIT_LINES.train; // 出陣開著（m.sortie）換一句
    // 探索三選一：字面寫 "explore:"、不讀 EXPLORE_PREFIX（tests/web/test_sending_web.py 只從 app.js 切等候那一段出來，切不到行動列那邊的常數）
    // 找素材分支（explore:gather:mine）照找素材那一句，「自己說」另一句（WAIT_LINES["gather:say"]）
    if (key.startsWith("explore:")) {
      const mode = key.slice("explore:".length);
      return WAIT_LINES[mode] || (mode.startsWith("gather:") ? WAIT_LINES.gather : WAIT_LINES.explore);
    }
    if (key === "act:rest") return WAIT_LINES.rest;
    if (key === "act:socialize" || key.startsWith("call:") || key.startsWith("talk:")) return WAIT_LINES.meet;
    if (key.startsWith("move:") || key.startsWith("road:")) return WAIT_LINES.move;
    if (key.startsWith("battle:")) return WAIT_LINES.battle;
    return SENT_WAITING;
  }
  let pressed = null; // 最近一次點到的 [data-act]（點擊的處理器記下，busy 拿它標「送出中」）：{ el, at }

  // 那一行只是提示：畫不出來（測試的假 document 沒有這些）也不能讓動作本身失敗
  function sendingLine(text) {
    try {
      const el = document.getElementById("sending");
      if (!text) { if (el) el.remove(); return; }
      if (el) { el.lastElementChild.textContent = text; return; }
      document.body.insertAdjacentHTML("beforeend",
        `<div id="sending" class="sending-line" role="status" aria-live="polite"><i></i><span>${esc(text)}</span></div>`);
    } catch (e) { /* 見上 */ }
  }

  async function busy(fn, line = SENT_WAITING) {
    if (S.busy) { sendingLine(STILL_WAITING); return false; } // 回傳 false：這一下沒送（呼叫端別拿「失敗了」的還原去動上一個還在等的按鈕）
    S.busy = true;
    // 這一下是點哪一顆送出的（點擊的處理器記在 pressed；隔太久的不算，例如確認框問過才送的那一下，原本那顆早就重畫掉了）
    const btn = pressed && Date.now() - pressed.at < 1000 && pressed.el.isConnected ? pressed.el : null;
    if (btn) { btn.classList.add("sending"); btn.disabled = true; btn.setAttribute("aria-busy", "true"); }
    const hint = setTimeout(() => sendingLine(line), WAIT_HINT_MS);
    const slow = setTimeout(() => sendingLine(SLOW_WAITING), SLOW_HINT_MS);
    let timedOut = false;
    try { await fn(); } catch (e) { timedOut = !!(e && e.timedOut); /* api() 已經提示過 */ } finally {
      clearTimeout(hint);
      clearTimeout(slow);
      sendingLine(null);
      // 沒被重畫掉（動作失敗、或這個動作不重畫那一塊）：還原成按得下去
      if (btn && btn.isConnected) { btn.classList.remove("sending"); btn.disabled = false; btn.removeAttribute("aria-busy"); }
      S.busy = false;
      lastAction = Date.now();
    }
    if (timedOut) setTimeout(poll, 0); // 逾時：伺服器那邊可能其實做完了，重抓一次畫面，玩家看到的才是現在的樣子
    return true;
  }
  // ── 送出指令的回饋（完）──

  // 等模型的時候（對話、大場面、開爐、隨口應對）每 2 秒問一次佇列，按鈕上補「前面還有 N 件」。佇列關著時伺服器回 null，什麼都不多顯示
  function watchQueue(el, base) {
    let alive = true;
    (async function loop() {
      while (alive) {
        await new Promise((r) => setTimeout(r, 2000));
        if (!alive) break;
        try {
          const r = await fetch("/api/queue", { credentials: "same-origin" }).then((x) => x.json());
          // 前面有人才寫；寫過之後前面沒人了（輪到自己：0；評分與潤色之間、還沒排進去：null）就還原成原本的字，
          // 不然舊的「前面還有 N 件」會一路留到自己那一件做完。伺服器有回答（有 ahead 這個鍵）才動；問不到、回的不是答案就不動
          if (alive && el && r && "ahead" in r) el.textContent = typeof r.ahead === "number" && r.ahead > 0 ? `${base}（前面還有 ${r.ahead} 件）` : base;
        } catch (e) { /* 問不到就算了，按鈕照原本的字 */ }
      }
    })();
    return () => { alive = false; };
  }



  function applyMain(main) {
    const before = S.main ? S.main.status : null;
    setMain(main); // 見聞的紅點在 setMain 裡判斷（新的一場才亮）
    render();
    const top = document.getElementById("top");
    if (before && top && (before.hp !== main.status.hp || before.stamina !== main.status.stamina || before.silver !== main.status.silver || before.xinde !== main.status.xinde)) {
      top.classList.add("flash");
      setTimeout(() => top.classList.remove("flash"), 900);
    }
  }


  async function choose(btn, id, sure = false) {
    // 按下去之前要先問一次的選項（伺服器寫在 confirm，FB-095：必敗的遊歷）：問過、按了「照打」才送。問的當下輪詢可能重畫了頁面，
    // btn 已經不在頁面上：照 id 重找畫面上那一顆，「處理中」才標得到、擋下來時才還原得了（整合審查 M1）
    const ask0 = ((S.main && S.main.options) || []).find((o) => o.id === id);
    if (!sure && ask0 && ask0.confirm) {
      ask(ask0.confirm, ask0.confirm_yes || "照打", () => choose(document.querySelector(`[data-act="choose"][data-id="${CSS.escape(id)}"]`) || btn, id, true));
      return;
    }
    if (id === SENSE_DRAW) { // 有所感：先叫出畫布、送暖機（模型閒置後第一次看圖要一二十秒，畫的這幾秒剛好用來載入），畫好再送
      S.sensing = true;
      renderPage();
      api("/api/sense_warm", {}).catch(() => {});
      return;
    }
    if (id === FREE_TEXT_OPTION) { // 隨口應對：先叫出輸入框，寫好再送（見 answer）
      S.answering = true;
      renderPage();
      const input = document.querySelector("#answer-form .input");
      if (input) input.focus();
      return;
    }
    if (SAY_OPTIONS.includes(id)) { // 自己說（與商量打法、路上跟他說）：先叫出輸入框，寫好再送（見 sayLine）
      S.saying = id;
      renderPage();
      const input = document.querySelector("#say-form .input");
      if (input) input.focus();
      return;
    }
    if (id.startsWith(PERSUADE_PREFIX)) { // 託付的勸降：先叫出輸入框，寫好再送（見 persuadeSay；按了 /api/choose 只回一句「寫下你要怎麼勸他」，FB-829）
      S.persuading = id;
      renderPage();
      const input = document.querySelector("#persuade-form .input");
      if (input) input.focus();
      return;
    }
    if (id === OWN_NAME_ID) { // 神品意境自己取名：先叫出輸入框，寫好再送（見 godName；按了 /api/choose 只回一句「寫下你替它取的名字」，FB-901）
      S.godNaming = true;
      renderPage();
      const input = document.querySelector("#own-name-form .input");
      if (input) input.focus();
      return;
    }
    if (id === GATHER_SAY_ID) { // 找素材的「自己說」：先叫出輸入框，寫好再送（見 gatherSay）
      S.gatherSaying = true;
      renderPage();
      const input = document.querySelector("#gather-say-form .input");
      if (input) input.focus();
      return;
    }
    const sent = await busy(async () => {
      document.querySelectorAll(".options .btn").forEach((b) => { b.disabled = true; });
      btn.classList.add("busy");
      // 跟 server.py 的 may_generate_dialogue 同一個判斷：這些選項要等模型回話
      const talking = id === "act:socialize" || ((id.startsWith("talk:") || id.startsWith("call:")) && id !== "talk:leave" && id !== "call:back");
      if (talking) btn.lastElementChild.textContent = "對方沉吟中…";
      // 大場面（挑戰大勢人物本人、打頭目）：伺服器先在鎖外請模型判讀戰局，選項帶著要換上的字（「兩人對峙……」，server.prepare_fight）
      const opt = ((S.main && S.main.options) || []).find((o) => o.id === id);
      if (opt && opt.wait) (btn.lastElementChild || btn).textContent = opt.wait;
      // 等模型的這兩種（對話、大場面）每 2 秒問一次佇列，排在後面時按鈕上補「前面還有 N 件」
      const label = btn.lastElementChild || btn;
      const stop = (talking || (opt && opt.wait)) ? watchQueue(label, label.textContent) : () => {};
      try {
        const shopBefore = S.main && S.main.shop; // 懸賞榜交出之前的木板（boardHanded 比）
        const r = await api("/api/choose", { id });
        S.answering = false;
        S.saying = false;
        S.gatherSaying = false; // 找素材「自己說」的輸入框叫出來之後改按了別的（一條分支）：下次攤開分支不再停在輸入框
        S.persuading = false;
        S.wheelSel = null; // 收起展開的移動
        S.sortieAnswer = null; // 出陣約戰應戰那張卡也收起
        S.hereAll = false; S.dutyOpen = false; S.fig = null; // 介面重整：從「全部」、要事清單、點人物那一層按下去的，做成了就收起那一層（被擋下來時留著）
        applyMain(r.main);
        if (id.startsWith("bounty:give:")) boardHanded(id, shopBefore); // 店面的懸賞榜：交差了蓋朱印（第四節）
        window.scrollTo({ top: 0, behavior: "smooth" });
        // 決戰選項（加入、趕到、出招）伺服器會回一句 message；大場面等模型判讀的時候選項沒了（人被別的分頁帶走），
        // 那一仗沒打成、不寫江湖紀錄，也只有這一句；一般選項的話在江湖紀錄裡，不回
        const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
        // 這一送剛好結算了回合時，回話是整段回合敘事（場景裡的戰況就是同一段）：提示只放得下幾秒，截短、指去場景。
        // 只有決戰選項這樣（FB-162：懸賞選項的拒絕句是一句話，場景裡沒有它，不截、不指去場景）
        // 戰場面板開著時出招不跳提示：面板上已經寫「你這一回合：…」，結算了的那一回合在面板的戰報裡（PM 2026-11-06 看截圖）
        const panelSays = id.startsWith("battle:act:") && typeof bpOn === "function" && bpOn(S.main);
        if (text && !panelSays) toast(text.length > 40 && id.startsWith("battle:") ? `${text.slice(0, 40)}……（戰況見場景）` : text);
      } finally { stop(); }
    }, waitLineFor(id));
    // 失敗了（伺服器擋下來、連不上）：把按鈕還原。選單上的按鈕與閒著時行動列的格子（.act-ink：交友、求見、遊歷）都會標 busy、
    // 換上「對方沉吟中…」「兩人對峙……」，兩種都要還原（審查 I2）
    // 上一個還在等、這一下沒送（sent 是 false）：那顆 busy 是上一個的，不能動
    if (sent && document.querySelector(".options .btn.busy, .act-ink.busy")) renderPage();
  }


  // 自己說：送出後要等人物答話（跟按選項一樣十來秒），按鈕先寫「對方沉吟中…」；排在佇列後面時補「前面還有 N 件」
  async function sayLine(form, text) {
    await busy(async () => {
      form.querySelectorAll("input, button").forEach((el) => { el.disabled = true; });
      const submitBtn = form.querySelector("[type=submit]");
      submitBtn.textContent = "對方沉吟中…";
      const stop = watchQueue(submitBtn, "對方沉吟中…");
      try {
        const r = await api("/api/say", { text, option: sayingId() });
        S.saying = false;
        applyMain(r.main);
        window.scrollTo({ top: 0, behavior: "smooth" });
      } finally {
        stop();
        form.querySelectorAll("input, button").forEach((el) => { el.disabled = false; });
        submitBtn.textContent = "說出口";
      }
    });
  }

  // 找素材的「自己說」（第 32 項）：送出後要等模型評這個找法（同隨口應對），按鈕先寫「盤算中……」；等候的話照 waitLineFor(GATHER_SAY_ID)
  const GATHER_SAY_WAIT = "盤算中……"; // 待 joy 潤
  async function gatherSay(form, text) {
    await busy(async () => {
      form.querySelectorAll("input, button").forEach((el) => { el.disabled = true; });
      const submitBtn = form.querySelector("[type=submit]");
      submitBtn.textContent = GATHER_SAY_WAIT;
      const stop = watchQueue(submitBtn, GATHER_SAY_WAIT);
      try {
        const r = await api("/api/do/gather_text", { text });
        S.gatherSaying = false;
        S.wheelSel = null; // 同按了別的探索：收起展開的探索（分支展開與否照記著，S.gatherOpen）
        applyMain(r.main);
        const said = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
        // 被擋下來的那一句（字數不對、換了做法）在江湖紀錄裡沒有，用提示泡泡講；做成了的結果在「剛剛」
        if (said && !said.startsWith("你：")) toast(said);
        window.scrollTo({ top: 0, behavior: "smooth" });
      } finally {
        stop();
        form.querySelectorAll("input, button").forEach((el) => { el.disabled = false; });
        submitBtn.textContent = GATHER_SAY_GO;
      }
    }, waitLineFor(GATHER_SAY_ID));
  }


  // 隨口應對：送出後要等模型評這個做法，首次常要好幾秒，按鈕先寫「思量中……」
  async function answer(form, text) {
    await busy(async () => {
      form.querySelectorAll("input, button").forEach((el) => { el.disabled = true; });
      const submitBtn = form.querySelector("[type=submit]");
      submitBtn.textContent = "思量中……";
      const stop = watchQueue(submitBtn, "思量中……");
      try {
        const r = await api("/api/answer", { text });
        S.answering = false;
        applyMain(r.main);
        window.scrollTo({ top: 0, behavior: "smooth" });
      } finally {
        stop();
        form.querySelectorAll("input, button").forEach((el) => { el.disabled = false; });
        form.querySelector("[type=submit]").textContent = "說出口";
      }
    });
  }


  // 修練頁的動作按完停在原地（W7 起只有修練；Joy 2026-10-18「武學升級的時候為什麼要點一次升級又把畫面跳到置頂？」之後每一顆都是）：
  // 每個動作認一個錨（mxPlace）：重畫前記下它在螢幕上的位置，畫完捲回去補差——玩家的拇指底下還是那一塊。結果寫在錨附近
  // （武學寫在那一門卡片的按鈕底下 S.artNote，熔掉的寫在功法庫標題底下 S.meltNote，其餘寫在那一塊裡 S.mxNote），頁首那一行不寫。
  // 照舊回頁首的只有：這一次練成了絕學、要定名（表單在頁首），做完了引導的一步（師父的下一句在頁首），絕學定名本身與沒認的動作。
  // 回 { from: [選擇器, id], to: [選擇器, id], note: "art:<id>"｜"lib"｜S.mxNote 的 at }，認不得回 null
  function mxPlace(op, extra) {
    const x = S.menxia || {};
    const arts = x.owned_arts || [];
    const card = (kind) => [`.acard[data-worn="${kind}"]`, null];
    const slot = (id) => (((x.gear || {}).slots) || []).find((g) => (g.worn && g.worn.id === id) || (g.rack || []).some((w) => w.id === id));
    const gear = (name) => name ? { from: [`.gear-slot[data-slot="${name}"]`, null], to: [`.gear-slot[data-slot="${name}"]`, null], note: "gear:" + name } : null;
    switch (op) {
      case "practice": { // 練成：身上那一門的卡
        const a = arts.find((r) => r.worn && r.kind === S.kind);
        return a ? { from: card(S.kind), to: card(S.kind), note: "art:" + a.id } : null;
      }
      case "cultivate": return extra.art ? { from: ['[data-act="cultivate"]', extra.art], to: ['[data-act="cultivate"]', extra.art], note: "art:" + extra.art } : null;
      case "slot": case "unslot": return extra.art ? { from: ['.jade .jd', extra.art], to: ['.jade .jd', extra.art], note: "art:" + extra.art } : null; // 裝、拆意境：留在那門的卡上
      case "switch": { // 改練：從庫裡那一列換到身上那張卡，畫完讓那張卡停在剛才按的地方
        const a = arts.find((r) => r.id === extra.art);
        return a ? { from: ['[data-act="switch"]', extra.art], to: card(a.kind), note: "art:" + extra.art } : null;
      }
      case "melt": return { from: ['[data-act="melt"]', extra.art], to: null, note: "lib" }; // 那一列不在了：捲到功法庫標題底下那一句看得到為止
      case "melt_insight": return { from: [".ins", null], to: [".ins", null], note: "ins" };
      case "wield": case "dismantle": case "name_divine": case "bind_art": return gear((slot(extra.weapon) || {}).slot);
      case "feed": return gear("mount");
      case "chuangong": case "join": case "leave": return { from: [".person-card", null], to: [".person-card", null], note: "person" };
      default: return null;
    }
  }
  function placeTop(at) {
    if (!at) return null;
    const el = [...document.querySelectorAll(at[0])].find((e) => at[1] == null || (e.dataset && e.dataset.id === at[1]));
    return el ? el.getBoundingClientRect().top : null;
  }

  async function mx(op, extra = {}) {
    await busy(async () => {
      const place = mxPlace(op, extra);
      const was = S.menxia, mark = place ? placeTop(place.from) : null;
      const step = guideKey(S.main && S.main.guide);
      const drafted = !!(S.main && S.main.status && S.main.status.create && S.main.status.create.draft);
      const r = await api(`/api/menxia/${op}`, { person: S.person, kind: S.kind, ...extra });
      if (r.secret) setTimeout(() => secretPop(r.secret), 0); // 裝滿意境槽暗合「裝滿」秘方：重畫完再跳視窗
      S.menxia = r.menxia;
      trimPot(); // 熔掉的若正放在爐裡，回煉製頁時不能還留著
      const needsName = !!(r.menxia && r.menxia.naming) && !(was && was.naming);
      // 這一次做完了引導的一步（說書人的 key 換了、或框沒了）：師父的下一句在修練頁最上面（序章 p6→p7），不捲上去玩家看不到。
      // 比的是步驟，不特別認序章，所以以後任何被修練頁的動作做完的引導步驟都一樣
      const guideMoved = guideKey(r.main && r.main.guide) !== step;
      const batch = op === "melt_many";
      const stay = !!place && mark !== null && !needsName && !guideMoved;
      const note = place && mark !== null ? place.note : null; // 回頁首的那幾次結果也照樣寫在錨附近（頁首那一行也有）
      // 批量熔煉的結果寫在功法庫那裡（按的地方），不捲回頂上、不在頂上再寫一次；留在原地的動作同樣只寫在錨附近
      S.message = batch || stay ? "" : r.message;
      S.meltNote = batch || note === "lib" ? r.message : null;
      S.artNote = note && note.startsWith("art:") ? { id: note.slice(4), html: r.message } : null;
      S.mxNote = note && note !== "lib" && !note.startsWith("art:") ? { at: note, html: r.message } : null;
      if (op === "switch") S.artOpen = null; // 改練真的送出了：庫裡那一列收起（它已經換到身上那張卡）
      setMain(r.main);
      renderTop();
      // 自創武學立好、作罷：草稿沒了就在這一次重畫裡直接回修練頁、一下回頂，不先畫一張空的自創頁、
      // 捲到一半再換一次（Joy 2026-10-22「自創武學完畢那個畫面會閃爍」）
      const cr = S.main && S.main.status && S.main.status.create;
      // 只有本來有草稿、這一下沒了（立好、作罷）才回去；執器被擋下（例：心得不足）留在自創頁，原因寫在頁首（手機介面自檢 U-04）
      if (S.createOpen && drafted && !(cr && cr.draft)) { S.createOpen = false; renderPage(); window.scrollTo(0, 0); return; }
      if (op === "switch" && S.tab === "craft") { // 煉製頁新武學卡上的「改練上身」：留在卡那裡，結果用提示泡泡說
        S.message = ""; S.artNote = null;
        keepPlace(() => renderPage(), ".made-card");
        const text = String(r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
        if (text) toast(text);
        return;
      }
      renderPage();
      if (batch || (stay && note === "lib")) { document.querySelector(".melt-result")?.scrollIntoView({ block: batch ? "center" : "nearest", behavior: "smooth" }); return; }
      const now = stay ? placeTop(place.to) : null;
      // 介面重整的俠客頁：結果那一行（#mx-msg）在分頁鈕底下，不是頁首，回頂上反而看不到；留在原地，結果那一行不在畫面裡才捲到它（Joy 11/7 不要跳頂）
      if (now === null && S.tab === "practice" && (typeof uiV2 === "function" && uiV2()) && !pro() && !guideMoved && !needsName) {
        if (S.message) document.getElementById("mx-msg")?.scrollIntoView({ block: "nearest", behavior: "smooth" });
      } else if (now === null) window.scrollTo({ top: 0, behavior: "smooth" });
      else if (now !== mark) window.scrollBy({ top: now - mark, left: 0, behavior: "instant" });
    });
  }

  async function doMain(op, body = {}) {
    await busy(async () => {
      const r = await api(`/api/do/${op}`, body);
      applyMain(r.main);
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      if (text) toast(text);
    }, op === "battle_text" || op === "duel_text" ? WAIT_LINES.battle : SENT_WAITING);
  }




  // ── 事件 ──
  // 行動列點下去的水墨漣漪：記下位置，重畫之後（例如展開移動）畫在新的那一顆上
  function inkRipple(key, x, y) {
    const cell = document.querySelector(`.act-ink[data-key="${key}"]`);
    if (!cell) return;
    const r = cell.getBoundingClientRect();
    const drop = document.createElement("span");
    drop.className = "ink-drop";
    drop.style.left = `${x - r.left}px`;
    drop.style.top = `${y - r.top}px`;
    cell.appendChild(drop);
    setTimeout(() => drop.remove(), 650);
  }

  let pointerHeld = false; // 手指（滑鼠）正按著：輪詢先不重畫江湖頁（見 refreshPage）
  let redrawHeld = false; // 按著的時候輪詢帶來了新畫面：放開之後補畫
  document.addEventListener("pointerdown", () => { pointerHeld = true; }, true);
  const releasePointer = () => {
    pointerHeld = false;
    if (peerNext) { // 按著的時候玩家卡抓到了新的一張（refreshPeer）：放開、click 處理完再換
      const { P, r } = peerNext;
      setTimeout(() => { if (peerNext && peerNext.P === P) applyPeer(P, r); }, 0);
    }
    if (!redrawHeld) return;
    redrawHeld = false;
    // 放開之後 click 才送出：等它處理完再補畫；它開始了一個動作的話，動作回來會自己畫
    setTimeout(() => {
      if (S.busy || S.stage !== "game") return;
      if (S.main && S.main.shop) renderShop(); // 店面開著：補畫的是店面（店面獨立介面設計 1.3）
      else if (S.tab === "jianghu") renderPage();
    }, 0);
  };
  document.addEventListener("pointerup", releasePointer, true);
  document.addEventListener("pointercancel", releasePointer, true);
  // 戰記那一層（taleHtml）的「‹ 返回」：同一個網域的頁面才認
  window.addEventListener("message", (ev) => {
    if (ev.origin === location.origin && ev.data && ev.data.zhanji === "close") taleClose();
  });

  document.addEventListener("click", async (ev) => {
    const unroll = document.querySelector(".zhuan-layer.zh-play:not(.zh-skip)");
    if (unroll) unroll.classList.add("zh-skip"); // 竹簡還在展開：點一下直接攤開
    const el = ev.target.closest("[data-act]");
    if (!el) return;
    pressed = { el, at: Date.now() };
    const act = el.dataset.act;
    if (el.classList.contains("act-ink")) {
      const [key, x, y] = [el.dataset.key, ev.clientX, ev.clientY];
      if (act === "wheel" || act === "sortie-open") requestAnimationFrame(() => inkRipple(key, x, y)); // 展開移動（出陣卡）會重畫整頁
      else inkRipple(key, x, y);
    }
    try {
      if (act.startsWith("outing-") && typeof outingClick === "function" && await outingClick(act, el)) return; // 走一趟那一層（outing.js）
      switch (act) {
        case "gate": S.gateMode = el.dataset.mode; renderGate(); break;
        case "promo-sound": promoSound(el); break;
        case "bp-log": document.querySelector("#page .b-round")?.scrollIntoView({ behavior: "smooth", block: "center" }); break; // 戰場面板「完整戰報」：捲到場景卡的戰報
        case "tab": {
          S.craftPick = false; // 換分頁：煉製頁的抽屜收起
          const loc = el.classList.contains("mini") && ev.target.closest && ev.target.closest("[data-loc]");
          // 江湖頁的小地圖點了某一處（設計第八節）：輿圖開在那一處所在的區圖、抽屜半開它的卡（那一區照它算：mapReady）
          if (loc) mapGoto(loc.getAttribute("data-loc"));
          else if (el.dataset.goto) mapGoto(el.dataset.goto, el.dataset.then || null); // 江湖頁「去輿圖」「去宛城」：直接開在目標地點
          // 底下的「見聞」：從「俠客」進過行狀（SELF_NEWS）的話換回上一次見聞的那一段，不然籤不畫、只剩「‹ 俠客」（Joy 2026-10-28「見聞那邊只剩下行狀」）
          if (el.dataset.tab === "news" && selfNews(S.news)) S.news = S.newsBack || "reports";
          await goTab(el.dataset.tab);
          break;
        }
        case "opt-why": toast(el.dataset.why); break; // 灰掉的俠寇鈕（名聲 5B）：點了只說整句原因，不送選擇
        case "choose":
          await choose(el, el.dataset.id);
          if (S.tab === "map") await loadMap(); // 在輿圖上按的（抽屜裡的喊停）：疊層跟著換
          break;
        case "map-report": S.news = "reports"; await goTab("news"); break; // 卡上「攻城戰果」那一段的「看戰報」：開見聞的戰報
        case "map-home": mapHome(); break; // 右下「◎」：回到我
        case "map-fit": mapFit(); break; // 右下「全」：看整張天下
        case "map-more": mapOpen(); break; // 卡上「往上拉：能悟、對手……」
        case "map-place": mapPick(el.dataset.id); break; // 地圖上點了一處（小圖、名字）、附近那一排點了一張：抽屜開它的卡
        case "map-pick": mapPick(el.dataset.id, true); break; // 找地點、今天去哪裡出陣挑了一處：飛過去、開它的卡
        case "map-region": mapBack(); mapRegionFly(el.dataset.id); break; // 找地點的「跳到大區」：收起那一頁，飛過去
        case "map-filter": mapFilter(el.dataset.id); break; // 上面那一排標籤（再按一次回全部）
        case "map-wash": washToggle(); break; // 「塗層」
        case "map-search": mapFind(); break;
        case "map-open": mapOpen(); break;
        case "map-back": mapBack(); break;
        case "map-letter": { // 卡上的「下戰書」（設計 4.4）：先問一次，再照伺服器的入口條件下（Game.conquest_letter）
          const loc = el.dataset.id, place = (placeOf(S.mapBase, loc) || { name: loc }).name;
          ask(LETTER_ASK.replace("{place}", place), LETTER_WORD, async () => { await doMain("conquest_letter", { loc }); if (S.tab === "map") await loadMap(); });
          break;
        }
        case "map-travel": await travel(el.dataset.mode); break;
        case "map-timeline": mapTimeline(S.mapMode !== "timeline"); break;
        case "map-week": stopPlay(); mapWeekTo(Number(el.dataset.week)); break;
        case "map-graph": stopPlay(); graphPick(el, ev); break;
        case "map-now": stopPlay(); mapWeekTo(S.mapState.now_week); break;
        case "map-mark": mapPick(el.dataset.id); break; // 年表上點一個地點的名字：地圖上圈出它（再點一次取消）
        case "map-play": { // 從第 1 週一週一週放到現在
          stopPlay();
          let w = 1;
          mapWeekTo(w);
          mapPlaying = setInterval(() => {
            if (S.tab !== "map" || S.mapMode !== "timeline" || w >= S.mapState.now_week) { stopPlay(); return; }
            mapWeekTo(++w);
          }, PLAY_MS);
          break;
        }
        case "map-jianghu": { // 就在這裡：出陣、探索真的做（減法季整合設計第七章【PM】），回江湖頁看結果；探索三選一開著時回江湖頁攤開那三種
          const key = el.dataset.key, opts = (S.main && S.main.options) || [];
          // 出陣約戰開著（丙）：回江湖頁展開出陣前那張卡，不送 act:train（伺服器只會回一句「封好三招再出陣」）；截糧的運糧隊經過時照舊直接打
          if (key === "sortie" && S.main && sortieCardOn(S.main)) {
            S.wheelSel = SX_OPEN;
            S.sortieAnswer = null;
            S.sortiePick = [];
            await goTab("jianghu");
            revealMoveCard();
            break;
          }
          const modes = opts.some((o) => o.id.startsWith(EXPLORE_PREFIX) && !o.id.startsWith(GATHER_BRANCH) && o.id !== PRACTICE_ID);
          const id = key === "sortie" ? "act:train" : key === "explore" && !modes ? "act:explore" : null;
          const ready = id && opts.some((o) => o.id === id && o.enabled !== false);
          S.wheelSel = key === "explore" && !ready ? "explore" : null;
          await goTab("jianghu");
          if (ready) await choose(document.querySelector(`[data-id="${id}"]`) || el, id);
          break;
        }
        case "sense-clear": S.sensePts = []; S.senseNote = ""; renderPage(); break;
        case "sense-send": await senseSend(); break;
        case "move-mode": await setMoveMode(el.dataset.mode); break;
        case "toggle-more": toggleMore(); break;
        case "sides-first": S.sidesOpen = !el.parentElement.open; break; // 摺疊照瀏覽器自己開合；記下來，輪詢重畫時照舊
        // 介面重整（main.js 檔尾）：此地可為的「全部」、要事清單、點人物之後、往來紀錄、場景文字攤開
        case "here-all": S.hereAll = true; renderPage(); break;
        case "here-all-close": S.hereAll = false; renderPage(); break;
        case "duty-open": S.dutyOpen = true; renderPage(); break;
        case "duty-close": S.dutyOpen = false; renderPage(); break;
        case "fig-open": S.fig = el.dataset.id; renderPage(); break;
        case "fig-close": S.fig = null; renderPage(); break;
        case "fig-act": { const id = el.dataset.id; S.fig = null; renderPage(); await choose(document.querySelector(`[data-id="${CSS.escape(id)}"]`) || el, id); break; }
        case "fig-talk": await figTalk(el.dataset.id); break;
        case "tav-hire": await tavHire(el.dataset.id); break;
        case "fig-log": await openFigLog(el.dataset.id); break;
        case "fig-log-close": S.figLog = null; renderPage(); break;
        case "fig-log-season": await openFigLog(S.figLog.id, el.dataset.s); break;
        case "fig-log-more": await moreFigLog(); break;
        case "rv-scene": S.sceneRvOpen = !S.sceneRvOpen; renderPage(); break;
        case "hero-attrs": S.heroTab = "attrs"; await goTab("practice"); break; // 狀態列的名號：去俠客頁的屬性
        case "hero-tab": heroStay(() => { S.heroTab = el.dataset.tab; S.pdrawer = false; renderPage(); }); break; // Joy 11/7「按完不要都給我跳置頂」
        case "now-more": nowToggle(el); break; // 原地展開／收起，不重畫整頁（重畫會讓「剛剛」再播一次浮現動畫）
        case "rounds-more": {
          // 同上，原地展開／收起；展開時其餘回合照 style.css 的延遲一回合一回合浮現
          const list = el.closest(".battle-card").querySelector("ul.rounds, p.rounds-tale"); // 回合清單，或大場面那一段話
          const open = !list.classList.contains("open");
          S.roundsOpen = open ? S.main.card_id : null;
          list.classList.toggle("open", open);
          el.textContent = roundsMore(open);
          el.setAttribute("aria-expanded", String(open));
          break;
        }
        case "sheet":
          S.sheet = true;
          render();
          pushRefresh(); // 手機通知：這台裝置訂著沒有（不等它）
          loadRecap(); // 有序章的內容才有「重看序章」鈕；同一次載入只問一次
          break;
        case "peer": await openPeer(el.dataset.name); break;
        case "peer-close": S.peer = null; render(); break;
        case "peer-answer": await openPeer(el.dataset.name, "discuss"); break; // 場景底下論武的「挑一樣答應」（FB-117）
        case "peer-act": await peerAct(Number(el.dataset.i)); break;
        case "peer-pick": await peerAct(Number(el.parentElement.querySelector("select").value)); break;
        case "here-more": S.hereOpen = true; renderPage(); break;
        case "calls-more": openCalls(); break; // 場景底下收起來的邀請（FB-117、FB-241）
        case "party-leave": await leaveParty(); break;
        case "secret-close": document.getElementById("sp-pop")?.remove(); break;
        case "secret-book": document.getElementById("sp-pop")?.remove(); S.bookFrom = window.scrollY; S.book = "arts"; render(); document.querySelector(".book-layer")?.scrollTo(0, 0); break;
        case "book-open": S.bookFrom = window.scrollY; S.book = el.dataset.book === "forge" ? "forge" : "arts"; render(); document.querySelector(".book-layer")?.scrollTo(0, 0); break;
        case "book-close": S.book = false; render(); window.scrollTo(0, S.bookFrom || 0); break;
        case "zhuan-open":
          S.bookFrom = window.scrollY; S.zhuan = { season: Number(el.dataset.season), view: null }; render();
          await loadZhuan();
          break;
        case "legacy-open": S.legacy = "main"; S.legacySlip = null; render(); break; // 傳承頁（features/legacy）
        case "legacy-close": S.legacy = null; render(); break;
        case "legacy-view": S.legacy = el.dataset.v === "shihai" ? "shihai" : "main"; render(); { const L = document.querySelector(".lg-layer"); if (L) L.scrollTop = 0; } break;
        case "legacy-slip": S.legacySlip = S.legacySlip === el.dataset.k ? null : el.dataset.k; render(); break;
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
        case "sheet-close": S.sheet = false; S.recapOpen = false; S.howtoOpen = false; S.pushHow = false; render(); break;
        case "push-how": S.pushHow = true; render(); break; // 設定頁「怎麼收到手機通知 ›」：抽屜整頁換成說明
        case "push-how-back": S.pushHow = false; render(); break;
        case "howto": // 玩法說明：攤開就再問一次（refreshHowto），收起只是收起
          S.howtoOpen = !S.howtoOpen;
          if (S.howtoOpen) await refreshHowto();
          else renderKeepingSheet();
          break;
        case "howto-retry": S.howtoFailed = false; await refreshHowto(); break; // 要不到時卡上的「再試一次」
        case "howto-open": // 本週卡「為什麼」裡的「玩法說明 ›」（以前在行動列底下，explain-2）：打開設定抽屜、攤開玩法說明（跟齒輪＋「玩法說明」兩下一樣）
          S.sheet = true;
          S.howtoOpen = true;
          render();
          loadRecap();
          await refreshHowto();
          break;
        // 管理頁（admin.js；Joy 2026-11-01 管理者工具獨立一個網址）：設定抽屜頂上那顆「管理者工具 ›」是一般的連結（/admin），這幾顆是管理頁上的
        case "ad-refresh": await adminReload(true); break;
        case "ad-result-close": S.adResult = null; renderKeepingSheet(); break;
        case "ad-find": await adminFind(); break;
        case "ad-pick": adminPick(el.dataset.login); break;
        case "ad-gen": adminGenTemp(); break;
        case "recap": S.recapOpen = !S.recapOpen; render(); break;
        case "guide-shut": shutGuide(S.main.guide); renderPage(); break;
        case "guide-open": openGuide(S.main.guide); renderPage(); break;
        case "guide-more": S.guideFull = S.guideFull === (S.main.guide && S.main.guide.text) ? null : S.main.guide && S.main.guide.text; renderPage(); break;
        case "scene-more": S.sceneOpen = !S.sceneOpen; renderPage(); break;
        case "wk": wkTap(el.dataset.id); break; // 本週卡的「為什麼」「今日簽到」與兩軍態勢：只換那一張，「剛剛」不會重播
        case "wk-next": wkNext(); break; // 本週卡的「換一件事」
        case "wk-hide": wkHideOne(el.dataset.id); break; // 灰線、「眼下要事」的 ×：收到明天
        case "newbie-go": newbieGo(Number(el.dataset.i)); break; // 新手目標的「去做」
        case "newbie-drifter": await doMain("newbie_drifter"); break; // 新手目標的「就當散人」
        case "hear-more": hearToggle(el); break; // 戰鬥卡片底下聽來的那一句：原地展開／收起，不重畫
        case "front-more": frontOpen(el); break; // 收著的出陣回報：原地攤開，不重畫
        case "extra-more": // 5c 收起來的戰鬥補充：整塊攤開，不重畫（之後重量也不再收這一場）
          S.extraOpen = S.main.card_id;
          el.classList.remove("fit-extra");
          ["data-act", "role", "tabindex", "aria-expanded"].forEach((a) => el.removeAttribute(a));
          break;
        case "line-more": lineToggle(el); break; // FB-107 收成一行的補充（對手的描述）：原地展開／收起，不重畫
        case "own-more": ownOpen(); break; // FB-107：決戰時收成一行的所在地描述，原地攤開
        case "battle-open": battleOpen(); break; // FB-120：只能觀戰的人收成一行的開打中的戰場，攤開（記戰場的名字）
        case "battle-shut": battleShut(); break; // 攤開的戰場底下「收起戰場」
        case "guide-next": nextGuidePage(S.main.guide); renderPage(); break;
        case "guide-below": scrollToGuideTarget(); break;
        case "guide-ack": await doMain("guide_ack"); break;
        case "stam-help": S.stamOpen = !S.stamOpen; renderTop(); break; // 點體力條：底下攤開／收起體力怎麼回（explain-1）；丹的鈕自己是一顆，點它不會走到這裡
        // 名聲（名聲設計十一之二）：狀態列只重畫它自己
        case "renown-toggle": S.renownOpen = !S.renownOpen; S.renownDot = null; renownDraw(); break; // 2C：展開時「名聲」那一行；介面重整在屬性頁「怎麼來」
        case "renown-dot": S.renownDot = S.renownDot === el.dataset.dot ? null : el.dataset.dot; renownDraw(); break; // 點圓點看那一段
        case "renown-sanren": S.renownSanren = !S.renownSanren; renownDraw(); break; // 散人另有的好處
        case "attr-help": heroStay(() => { S.attrHelp = !S.attrHelp; renderPage(); }); break; // 屬性頁的「？」：五項各管什麼
        case "xinde-more": heroStay(() => { S.xindeOpen = !S.xindeOpen; renderPage(); }); break; // 屬性頁心得那一行：點開看整句提示
        case "renown-open": // 6B：金色的「名號傳開」；介面重整之後名聲那一條在俠客頁的「屬性」（狀態列不再攤開）
          S.renownOpen = true; S.renownDot = null;
          if ((typeof uiV2 === "function" && uiV2()) && !pro() && !onb()) { S.heroTab = "attrs"; await goTab("practice"); window.scrollTo(0, 0); break; }
          S.showMore = true; renderTop(); window.scrollTo(0, 0); break;
        case "renown-peer": peerRenownToggle(el); break; // 3B：玩家卡的稱號小籤，原地攤開說明（不重畫整張卡）
        case "fronts-help": frontsTap(); break; // 點戰況圖卡：底下攤開／收起這一季在打什麼、亂局、怎麼推（explain-2）
        case "patch-close": patchPopClose(); renderPage(); break; // 進遊戲後跳的改版資訊：看過了，下一次改版才再跳
        case "ck-pop-close": ckPopClose(); renderPage(); break; // 每天第一次登入的簽到小窗：收下或等一下再挑，同一天不再跳
        case "checkin": await doMain("checkin", el.dataset.attr ? { attribute: el.dataset.attr } : {}); break; // 「簽到」小標攤開的領取鈕（四階的日子帶屬性）
        case "pill": await doMain("pill"); break; // 體力條上的「丹 N」：服一顆回體丹（測試期間一鍵補滿打開時同一顆鈕寫「補滿」，同一條路由）
        case "hero-move-show": await heroMoveShow(el.dataset.id || ""); break; // 俠客頁武學卡底下的絕招演一次
        case "hero-move-go": await heroMoveGo(el.dataset.style || ""); break; // 換一招：萬寶閣絕招那一頁
        case "hero-node": heroTap(el); break; // 修練頁人物面板的光點：開那一樣的抽屜
        case "self-sec": { // 俠客頁「功法庫・意境 ›」那一顆：攤開底下那個摺疊、捲到它
          (S.selfOpen || (S.selfOpen = {}))[el.dataset.sec] = true;
          renderPage();
          const box = document.querySelector(`details.self-fold[data-sec="${CSS.escape(el.dataset.sec)}"]`);
          if (box && box.scrollIntoView) box.scrollIntoView({ behavior: "smooth", block: "start" });
          break;
        }
        case "drawer-close": S.pdrawer = false; S.artOpen = null; S.insOpen = null; S.slotPick = null; renderPage(); break;
        case "ins-filter": S.insFilter = el.dataset.filter; renderPage(); break;
        case "growth": S.growthDraft = null; await doMain("growth", { preset: el.dataset.preset }); break; // 五項屬性的季：挑成長配比
        case "growth-custom": { // 自己配：從現在怎麼長起草（鍵照 growth.keys 的順序，now 是同一個順序）
          const g = S.main && S.main.status && S.main.status.growth;
          if (g) S.growthDraft = Object.fromEntries(g.keys.map(([k], i) => [k, g.now[i] ? g.now[i][1] : g.custom_min]));
          render();
          break;
        }
        case "growth-step": {
          const d = S.growthDraft;
          if (d) d[el.dataset.key] = Math.max(0, (d[el.dataset.key] || 0) + Number(el.dataset.d));
          render();
          break;
        }
        case "growth-cancel": S.growthDraft = null; S.prepPick = null; render(); break;
        case "prep-pick": { // 開季準備卡：先點一張（自己配從均衡起草），再按「定下來」
          const g = S.main && S.main.status && S.main.status.growth;
          S.prepPick = el.dataset.preset;
          S.growthDraft = S.prepPick === "custom" && g ? Object.fromEntries(g.keys.map(([k], i) => [k, g.now[i] ? g.now[i][1] : g.custom_min])) : null;
          render();
          break;
        }
        case "prep-growth": { const preset = S.prepPick; S.prepPick = null; await doMain("growth", { preset }); break; }
        case "alloc-toggle": S.allocOpen = !S.allocOpen; renderPage(); break; // 江湖頁頂上「有 N 點可配」：攤開＋鈕
        case "growth-save": { const split = S.growthDraft; S.growthDraft = null; S.prepPick = null; await doMain("growth", { preset: "custom", split }); break; }
        case "allocate": await doMain("allocate", { stat: el.dataset.stat }); break; // 升級的屬性點加到一項（狀態列展開後的「＋臂力」）
        case "do": S.sheet = false; await doMain(el.dataset.op); break;
        case "letter-open": {
          const id = Number(el.dataset.id), wasOpen = el.getAttribute("aria-expanded") === "true";
          S.letterOpen = wasOpen ? null : id;
          S.letterShut = wasOpen ? id : null; // 一到就攤開的那一封（開局的託付）收攏了就記著，重畫不再自己攤開
          renderPage();
          break;
        }
        case "letter-read": S.letterOpen = null; await doMain("letter_read", { id: Number(el.dataset.id) }); break;
        case "letter-decline": await doMain("letter_decline", { id: Number(el.dataset.id) }); break;
        case "push-test": await pushTest(); break; // 設定頁「傳一則測試通知」
        case "push-yes": await pushEnable(); break; // 第一次來信時問的那一張（手機通知，減法季批 9）
        case "push-no": pushMarkAsked(); renderPage(); break;
        case "gender-pick": S.genderPick = el.dataset.value || null; render(); break;
        case "rename-ask": { const v = (document.getElementById("rename-name") || {}).value || ""; if (v.trim()) { S.renameAsk = v.trim(); render(); } break; }
        case "rename-back": S.renameAsk = null; render(); break;
        case "rename-go": await renameGo(); break;
        case "adult-yes": S.adultAsk = null; await adultSet(true); break;
        case "adult-no": S.adultAsk = null; render(); break;
        case "gender-go": S.genderPick = null; await doMain("gender", { value: el.dataset.value }); break;
        case "ad-tab": adTabPick(el.dataset.tab); break; // 管理頁的分頁籤（介面重整）
        case "ad-hold": adHoldClick(el); break; // 危險區：短按只提示要長按（長按在 admin.js 的 pointerdown）
        case "admin": {
          const op = el.dataset.op;
          const body = { hours: Number(el.dataset.hours || 1) };
          if (op === "start_battle") body.id = document.getElementById("ad-battle").value;
          if (op === "fire") body.id = document.getElementById("ad-fire").value;
          if (op === "push_trend") { body.id = document.getElementById("ad-trend").value; body.amount = Number(document.getElementById("ad-amount").value || 0); }
          if (op === "schedule") {
            const input = document.getElementById(`tt-at-${el.dataset.id}`);
            if (!input || !input.value) { toast("先選一個時間。"); break; }
            body.id = el.dataset.id;
            body.at = new Date(input.value).getTime() / 1000;
            body.title = (S.admin.timetable.find((r) => r.id === body.id) || {}).label || body.id;
            body.when = input.value.replace("T", " ");
          }
          if (op === "set_trend") { body.id = document.getElementById("ad-front").value; body.value = Number(document.getElementById("ad-value").value || 0); }
          if (op === "resolve_event") { const [id, key] = document.getElementById("ad-result").value.split("|"); body.id = id; body.key = key; }
          if (op === "clear_lock") body.id = document.getElementById("ad-lock").value;
          if (op === "revive_figure") body.id = document.getElementById("ad-fallen").value;
          if (op === "start_showdown") {
            body.id = el.dataset.id;
            body.title = ((S.admin && S.admin.showdowns) || []).find((s) => s.id === body.id)?.label || body.id;
          }
          if (op.startsWith("seal_")) { // 玉璽一組：碎片、名號、狀態、局勢係數照欄位讀（假瀏覽器沒有這些欄位時是空的）
            const val = (id) => (document.getElementById(id) || {}).value || "";
            body.id = val("ad-seal");
            body.name = val("ad-seal-name").trim();
            body.state = val("ad-seal-state") || "held";
            body.factor = Number(val("ad-seal-factor") || 1);
            body.take = el.dataset.take === "1";
            body.when = el.dataset.when || ""; // 蓋天命之季：next／now（玉璽二）
            body.hide = el.dataset.hide === "1"; // 領地爭奪的季「強制現世」是「現在藏一片」（問句不同；送出去的欄位一樣）
          }
          if (op.startsWith("mingtie_")) { body.name = el.dataset.name || ""; body.version = Number(el.dataset.version || 0); }
          if (op === "conquest_set" || op === "conquest_progress" || op === "admin_conquest_letter") { // 領地爭奪一組：區塊、陣營、進度照欄位讀
            const pick = (id) => document.getElementById(id) || {};
            const block = pick("ad-cq-block"), side = pick("ad-cq-side");
            body.id = block.value || "";
            // 問句寫地名：照伺服器給的 name（選單的字後面接了括號，地名自己也可能有括號，不從字切）
            body.place = ((((S.admin && S.admin.conquest) || {}).blocks || []).find((b) => b.id === body.id) || {}).name || body.id;
            body.side = op === "conquest_set" && el.dataset.neutral === "1" ? "" : side.value || "";
            body.sideName = (side.options && side.options[side.selectedIndex]) ? side.options[side.selectedIndex].text : body.side;
            if (op === "conquest_progress") body.value = Math.max(0, Math.min(100, Number(pick("ad-cq-value").value || 0)));
          }
          if (op === "conquest_cancel") body.id = (document.getElementById("ad-cq-siege") || {}).value || "";
          if (op === "summon" || op === "give_opportunity" || op === "give_fragment") {
            body.name = (S.adPlayer && S.adPlayer.name) || "";
            if (op === "give_opportunity") {
              body.id = document.getElementById("ad-opp").value;
              body.note = ((S.adPlayer && S.adPlayer.opportunities) || []).find((x) => x.id === body.id)?.note || "";
            }
            if (op === "give_fragment") body.id = document.getElementById("ad-frag").value;
          }
          const [text, yes] = adminAsk(op, body);
          ask(text, yes, () => adminDo(op, body, yes.replace(/^確定/, ""))); // 先問一次（G3），按了確定才送；結果條上寫做的是哪一件
          break;
        }
        case "ask-yes": {
          // 上一個動作（例如等模型回話的對話）還沒回來：送了也會被 busy() 丟掉，所以先講一聲、確認框留著再按一次
          if (S.busy) { toast("正在處理上一個動作，請稍候再按一次。"); break; }
          const go = askGo;
          closeAsk();
          if (go) await go();
          break;
        }
        case "ask-no":
          closeAsk();
          if (S.mallOpen && S.mallPick) { S.mallPick = null; renderMall(); } // 商城的購買確認按了再想想：那一格不再框著
          brewShut(); // 打造頁熬的小單按了取消：那一格灰格不再框著（3.3）
          break;
        // 商城（商城第二批）：齒輪旁的錠子鈕與底部第六格都打開那一層（不換頁）
        case "mall-open": await openMall(); break;
        case "mall-moves": await openMallMoves(el.dataset.style || ""); break; // 直接進萬寶閣的絕招那一頁（data-style 開那一種打法）
        case "mall-goto": await openMall(); mallPick(el.dataset.id); break; // 別頁引過來買某一件（修練頁沒丹時的破境丹）
        case "mall-close": closeMall(); break;
        case "mall-tab": await mallTabTo(el.dataset.tab); break;
        case "mall-pick": mallPick(el.dataset.id); break;
        case "mall-cat": mallCatTo(el.dataset.cat); break; // 貨架的分類
        case "look-sub": lookSubTo(el.dataset.sub || ""); break; // 形象那一頁裡的自建形象、絕招那一頁（空的回形象）
        case "prompt-ex-more": moveExMore(); break; // 絕招例句換下一批三句
        case "prompt-ex": promptExample(el.dataset.for || "", el.dataset.text || ""); break; // 想不到就點：把例句填進框裡
        case "look-pick": lookPickTo(el.dataset.id || ""); break; // 形象那一頁點一套：台子上換成它
        case "look-seg": lookSegTo(el.dataset.seg || "mine"); break; // 我的／官方／市集
        case "look-filter": lookFilterTo(el.dataset.filter || "all"); break; // 我的那一頁篩哪一類
        case "look-more": lookMore(); break; // 再看一頁
        case "look-fold": lookFold(el.dataset.what); break; // 摺起來的展開（沒掛的、更早退回的）
        case "look-sell": lookSellTo(el.dataset.id || ""); break; // 那一套跳出定價框
        case "look-redo": lookRedo(el.dataset.id); break; // 退回的改一改再送
        case "move-tab": moveTabTo(el.dataset.tab || ""); break; // 招式庫的打法分頁
        case "move-form": moveFormOpen(); break; // 寫一招新的（展開）
        case "mall-qty": { // 購買確認那張紙的數量：同一件、同一個編號重畫
          const now = S.mallAskNow, it = now && S.mallData && S.mallData.items.find((one) => one.id === now.id);
          if (it) mallAsk(it, S.mallData, Number(el.dataset.n), now.ref);
          break;
        }
        case "mall-claim": await mallClaim(); break;
        case "look-wear": await lookWear(el.dataset.id || ""); break; // 萬寶閣「形象」那一頁換上一套
        case "look-order": lookOrderAsk(); break; // 自建形象下單（先問一次）
        case "look-withdraw": lookWithdrawAsk(el); break; // 撤回還沒上架的單（先問一次，元寶全退）
        case "move-order": moveOrderAsk(el.dataset.basic === "1"); break; // 絕招下單（先問一次）：通用 60 不畫圖、獨門 300 畫圖等審核
        case "move-preview": await movePreview(); break; // 一句話自創的絕招：先看看（不扣元寶）
        case "move-show": await moveShowTo(el.dataset.id || ""); break; // 招式庫做好了的那一招演一次
        case "mvp-replay": if (typeof mvpReopen === "function") mvpReopen(); break; // 決戰的回合 MVP：戰場底下那一行「再看一次」重新跳出視窗
        case "mvp-again": if (typeof mvpAgain === "function") mvpAgain(); break; // MVP 視窗裡：絕招從頭再演一次
        case "mvp-close": if (typeof mvpClose === "function") mvpClose(); break; // MVP 視窗收起
        case "look-show": lookShowTo(el.dataset.id || "", el.dataset.name || ""); break; // 一套形象看動作（再按一次收起）
        case "market-buy": lookMarketAsk(el.dataset.id, el.dataset.name || "", Number(el.dataset.price) || 0); break; // 形象市集買一套（先問一次）
        case "market-list": await lookMarketList(el.dataset.id); break; // 自己做的一套掛上市集（照框裡的價錢）
        case "market-unlist": await lookMarketDo({ op: "unlist", look: el.dataset.id }); break;
        case "move-bind": await moveBind(el.dataset.id); break; // 招式庫的一招換上身（id 0 是脫下來）
        case "looks-admin": await looksAdminAsk(el.dataset.op, el.dataset.id, el.dataset.slot); break; // 管理頁「自建形象」：上架、退回先問一次
        case "ad-show": await adShow(el.dataset.kind, el.dataset.id); break; // 管理頁的全服成品動畫牆：點一個就演（再點收起）
        case "mall-retry": await (S.mallTab === "log" ? loadMallLog() : loadMall()); break;
        case "mall-admin": mallAdminAsk(el.dataset.op, el.dataset.id); break;
        case "logout": closeEvents(); await api("/api/logout", {}); resetOrdersWatch(); forgetHowto(); S.sheet = false; S.peer = null; S.adPlayer = null; S.adPlayerName = ""; S.stage = "gate"; S.main = null; forgetMap(); forgetMall(); render(); break;
        case "kind": S.kind = el.dataset.kind; renderPage(); break;
        case "mx": if (el.dataset.kind) S.kind = el.dataset.kind; await mx(el.dataset.op); break; // 卷軸卡上的練成鈕帶著是哪一欄
        case "art-info": S.artInfo = S.artInfo === el.dataset.id ? null : el.dataset.id; renderPage(); break;
        case "lib-filter": setLibFilter(el.dataset.filter); renderPage(); break;
        case "lib-all": S.libAll = true; renderPage(); break;
        case "melt-mode": S.meltSel = S.meltSel ? null : { arts: [], ins: [] }; S.artOpen = null; S.meltOpen = null; S.meltNote = null; renderPage(); break;
        case "melt-pick": meltToggle("arts", el.dataset.id); break;
        case "melt-pick-ins": meltToggle("ins", el.dataset.id); break;
        case "melt-shown": meltPickShown(); break;
        case "melt-weak": meltView().weak = !meltView().weak; renderPage(); break;
        case "melt-open": S.meltOpen = S.meltOpen === el.dataset.key ? null : el.dataset.key; renderPage(); break;
        case "melt-clear": if (S.meltSel) { S.meltSel = { arts: [], ins: [] }; renderPage(); } break;
        case "melt-go": askMeltMany(el); break;
        case "rack-all": S.rackAll = true; renderPage(); break;
        case "ins-open": S.insOpen = S.insOpen === el.dataset.id ? null : el.dataset.id; S.artOpen = null; S.pdrawer = false; renderPage(); break;
        case "slot-pick": { // 空槽：攤開（再點收起）手上空著的意境
          const same = S.slotPick && S.slotPick.art === el.dataset.id && S.slotPick.i === Number(el.dataset.i);
          S.slotPick = same ? null : { art: el.dataset.id, i: Number(el.dataset.i) };
          renderPage(); break;
        }
        case "slot-in": S.slotPick = null; await mx("slot", { art: el.dataset.id, insight: el.dataset.ins, index: Number(el.dataset.i) }); break;
        case "create-kind": { const c = S.main.status.create; S.createPick = { kind: el.dataset.val, form: "" }; if (c) renderPage(); break; }
        case "create-pick": { if (S.createPick) S.createPick.form = el.dataset.val; renderPage(); break; }
        case "create-begin": if (S.createPick && S.createPick.form) await mx("create_begin", { kind: S.createPick.kind, form: S.createPick.form }); break;
        case "create-preset": { // 起手的幾個架式：套上再拖
          const p = ((S.main.status.create || {}).presets || []).find((q) => q.name === el.dataset.val);
          if (p) { S.createPose = { ...p.angles }; const svg = document.getElementById("create-rig"); if (svg) rigRedraw(svg); }
          break;
        }
        case "create-pose": if (S.createPose) await mx("create_pose", { pose: S.createPose }); break;
        case "create-intent": await createIntent(); break;
        case "create-back": await mx("create_back", { to: el.dataset.to }); break;
        case "ascend-ok": await mx("ascend_dismiss", {}); break;
        case "story-ok": // 特殊事件的跳顯框：還有下一張就翻過去，最後一張才請伺服器清掉
          if (el.dataset.last === "1") { S.storyAt = 0; await doMain("story_seen", {}); } else { S.storyAt = (S.storyAt || 0) + 1; storyCard(); }
          break;
        case "create-name": {
          const n = document.getElementById("create-name"), m = document.getElementById("create-move");
          document.activeElement?.blur?.(); // 手機的鍵盤先在這一下收起，不要等換頁那一刻才收、整頁再跳一次
          await mx("create_name", { name: n ? n.value.trim() : "", move: m ? m.value.trim() : "" }); break; // 立好了 mx 直接回修練頁
        }
        case "create-cancel": await createCancel(); break; // 付過心得的先問一次（3.1）
        case "create-reroll": await mx("create_reroll"); break; // 重悟帖：留在成形那一步，三格換了
        case "create-reread": await createReread(); break; // 重悟帖的第二個用法：重讀這句意（Joy 2026-10-22）
        case "create-open": S.createOpen = true; S.message = ""; renderPage(); window.scrollTo(0, 0); break;
        case "create-close": S.createOpen = false; S.message = ""; renderPage(); window.scrollTo(0, 0); break;
        case "slot-out": await mx("unslot", { art: el.dataset.id, insight: el.dataset.ins }); break;
        case "person":
          S.person = S.person === el.dataset.key ? null : el.dataset.key;
          await loadMenxia();
          break;
        case "wield": await mx("wield", { weapon: el.dataset.id }); break; // 裝備庫上那一把換到手上
        case "feed": await mx("feed"); break;
        case "release-mate": { // 歷史武將同行：放他回江湖，先問一次（問句伺服器寫好，roster.RELEASE_CONFIRM）
          const who = S.person;
          ask(el.dataset.confirm, "放他走", async () => { S.person = null; await mx("release", { person: who }); });
          break;
        }
        case "teach": await mx("chuangong", { what: el.dataset.what }); break; // 傳功門下：person 是名冊上點的那個人 // 身上那匹餵一個一階素材（裝備四欄 5.4）
        case "divine-keep": await mx("name_divine", { weapon: el.dataset.id, keep: true }); break; // 神器原品沿用譜名（5.2）
        // 玉璽碎片的獨門行動（改版第 2 批）：傳承那一列的鈕——要指定目標的開那一層，頒詔、承露直接問；那一層裡挑一邊、挑一個人（先問一次）、收起；
        // 江湖頁碎片卡那一行跳到修練頁那一顆
        case "seal-act": {
          const a = sealActNow();
          if (!a || (!a.ok && !sealBrowse(a))) { if (a && a.why) toast(a.why); break; }
          if (a.kind in SEAL_VERB) { S.sealAct = true; S.sealSide = null; await keepScroll(render); } else sealAsk(a, null);
          break;
        }
        case "seal-side": { S.sealSide = el.dataset.side; const a = sealActNow(); if (a) redrawSealAct(a); break; }
        case "seal-pick": { // 灰著的那一列不問（FB-645 起整顆按不下去時也列得出灰的）
          const a = sealActNow(); const t = a && (a.targets || []).find((r) => r.id === el.dataset.id);
          if (t && a.ok && !t.why) sealAsk(a, t);
          break;
        }
        case "seal-act-close": S.sealAct = false; S.sealSide = null; await keepScroll(render); break;
        case "seal-act-go": await goTab("practice"); document.querySelector(".gear .wrow.heirloom")?.scrollIntoView({ block: "center" }); break;
        case "bind-art": { // 以器配招：送挑好的那一門（select 的 id 帶冒號，用 getElementById）
          const pick = document.getElementById("bind-art-" + el.dataset.id);
          if (pick && pick.value) ask("綁了之後不能改配（那一門熔掉、交掉才能再配），確定嗎？", "綁上", () => mx("bind_art", { weapon: el.dataset.id, art: pick.value }));
          break;
        }
        // 店面（店面獨立介面設計第二節）：換頁只在網頁上；換上、拆解、定名走修練頁的動作（shopMx）
        case "shop-tab": S.shopTab = el.dataset.tab; S.shopMore = false; S.shopNote = null; S.shopBrew = null; S.divinePick = null; renderShop(false); break;
        // 鐵匠鋪素材頁（素材與經濟 B6）：升一個（灰掉的只說原因）、賣一個、全賣（先問一次）
        case "trade-up":
          if (el.dataset.why) toast(el.dataset.why);
          else await shopDo("smith_upgrade", { attribute: el.dataset.attr, tier: Number(el.dataset.tier) });
          break;
        case "trade-sell":
          if (el.dataset.confirm) ask(el.dataset.confirm, "賣掉", () => shopDo("smith_sell", { material: el.dataset.id, count: Number(el.dataset.n) }));
          else await shopDo("smith_sell", { material: el.dataset.id, count: Number(el.dataset.n) || 1 });
          break;
        // 軍需帳（素材與經濟 B6）：挑一格、＋−個數、全選一階、捐出
        case "dn-cell": donateCell(el.dataset.id, el.dataset.why); break;
        case "dn-step": donateStep(el.dataset.id, Number(el.dataset.d)); break;
        case "dn-tier1": donateTierOne(); break;
        case "dn-go": await donateGo(); break;
        case "shop-more": S.shopMore = true; renderShop(); break;
        case "tav-tab": S.tavTab = el.dataset.tab; S.shopNote = null; renderShop(false); break; // 酒肆：四頁
        case "tav-do": await tavDo(el.dataset.op); break;
        case "tav-mode": S.tavAsk = el.dataset.mode; renderShop(); break; // 打聽：查人在哪／打聽情誼
        case "tav-tier": S.tavTier = Number(el.dataset.tier); renderShop(); break; // 買殺手：三檔
        case "tav-hit-name": { const box = document.querySelector('#tav-hit input[name="target"]'); if (box) { box.value = el.dataset.name; box.focus(); } break; }
        case "tav-name": { const box = document.querySelector('#tav-ask input[name="target"]'); if (box) { box.value = el.dataset.name; box.focus(); } break; }
        case "arena-tab": S.arenaTab = el.dataset.tab; renderShop(false); break; // 擂台：台下／擂台榜
        case "arena-seen": S.arenaSeen = Number(el.dataset.id); renderShop(); break; // 收起收場卡
        case "shop-horse": S.shopHorse = el.dataset.id; renderShop(); break; // 馬市點一匹（第三節）：只換底下那張卡
        case "board-zoom": await boardZoom(el, el.dataset.id); break; // 懸賞榜點一張告示（第四節）：放大成一張紙
        case "board-close": await boardClose(el); break; // 放回去、收起
        case "shop-ask": ask(el.dataset.confirm, el.dataset.yes || "照做", () => choose(el, el.dataset.id, true)); break; // 選單上沒有問句的，問在這一層（放棄）
        case "shop-leave": await boardLeave(el); break; // 第三層開著時出店
        case "shop-kind": setPot({ kind: el.dataset.kind }); break;
        case "shop-cell": shopCell(el.dataset.id, el.dataset.why); break;
        case "shop-brew": shopBrew(el.dataset.attr, Number(el.dataset.tier), el.dataset.why); break; // 打造頁的灰格（3.3）：點了從底下浮小單
        case "shop-slot": setPot(el.dataset.role === "main" ? { main: null, aux: null } : { aux: null }); break; // 拿掉主料，輔料跟著出來（伺服器也這樣修）
        case "shop-go": await smithForge(); break;
        case "shop-furnace": await smithFurnace(); break; // 打造頁的爐火（3.2）：看火候
        case "shop-unwrap": S.shopOpened = true; renderShop(); break; // 點開麻布（2.3）
        case "shop-keep": S.shopReveal = null; S.shopOpened = false; renderShop(); break; // 收下、留在裝備庫：收起出爐卡
        case "shop-wield":
          await shopMx("wield", { weapon: el.dataset.id });
          if (S.shopReveal && S.shopReveal.id === el.dataset.id) { S.shopReveal = null; S.shopOpened = false; renderShop(); } // 出爐卡上的「換上」：換好了卡收起
          break;
        case "shop-dismantle": ask(el.dataset.confirm || "把這一件拆成素材？拆掉就沒了。", "拆掉", () => shopMx("dismantle", { weapon: el.dataset.id })); break;
        // 裝備庫那一列的修、淬煉、勾選與批量拆解（鐵匠鋪與合成流程 3.4）：id 是裝備庫的「兵:N」「甲:N」，修淬完照舊留在裝備庫
        case "rack-repair": await shopMx("repair_item", { item: el.dataset.id }); break;
        case "rack-temper": await shopMx("temper_item", { item: el.dataset.id }); break;
        case "rack-pick": rackPick(el.dataset.id); break;
        case "rack-melt": rackMelt(); break;
        case "dv-cell": await divinePick(el.dataset.id); break; // 神器頁收藏冊的一格（3.8）：翻出神器譜那一行
        case "shop-divine-keep": await shopMx("name_divine", { weapon: el.dataset.id, keep: true }); break;
        case "dismantle": // 裝備庫上那一把拆成一個素材（兵器設計 4.7.1）：先問一次（FB-125），按「拆掉」才送
          ask(el.dataset.confirm || "把這一件拆成素材？拆掉就沒了。", "拆掉", () => mx("dismantle", { weapon: el.dataset.id }));
          break;
        case "switch": {
          // 改練真的送出了（mx 換上伺服器回來的那一份 menxia）才收起卡片；還在忙（mx 直接返回）或請求失敗就照舊開著
          await mx("switch", { art: el.dataset.id }); // 真的送出了才收起卡片（mx 換上伺服器回來的那一份才收）；還在忙或失敗就照舊開著
          break;
        }
        case "art": S.artOpen = S.artOpen === el.dataset.id ? null : el.dataset.id; S.artNote = null; S.insOpen = null; S.pdrawer = false; renderPage(); break;
        case "cultivate": {
          // 服丹衝關（use_legend，伺服器只認真正的布林 true）。真的擲了骰（mx 換上了伺服器回來的那一份 menxia、丹少了一枚）
          // 才播衝關的小動畫：那一門變成絕學是衝開了，不然是彈回來
          const id = el.dataset.id, pill = el.dataset.by === "pill";
          const row = (S.menxia?.owned_arts || []).find((a) => a.id === id);
          const was = S.menxia?.legend_items;
          await mx("cultivate", { art: id, use_legend: pill });
          if (row && pill && typeof was === "number") {
            // 看手上的丹（不是那一列的 legend：被拒絕時那一列也會變成 null，例如體力在別處花掉了，那時不能播彈回）
            const now = (S.menxia?.owned_arts || []).find((a) => a.id === id);
            const won = !!now && now.quality === "絕學";
            if (won || (S.menxia?.legend_items ?? was) < was) breakAnim(row, won);
          }
          break;
        }
        case "melt": askMelt(el); break;
        case "melt-insight": askMeltInsight(el); break;
        case "art-filter": setArtFilter(el.dataset.page, el.dataset.filter); renderPage(); break;
        case "pick": pick(el.dataset.type, el.dataset.id); break;
        case "unslot": if (S.busy) break; if (isLocked(S.forgeSel[Number(el.dataset.i)])) S.forgeLock = null; S.forgeSel.splice(Number(el.dataset.i), 1); S.forgePicks = null; S.forgePreview = null; renderPage(); updateForgeLine(); break;
        case "pot-lock": if (S.busy) break; toggleLock(Number(el.dataset.i)); break;
        case "forge": await forge(); break;
        case "craft-all": craftView().all = true; renderPage(); break;
        case "peek": window.scrollTo({ top: 0, behavior: "smooth" }); break;
        case "pot-open": if (S.busy) break; if (S.forgeSel.length >= 2) { toast("爐裡已經放滿了，點上面的拿出來再換。"); break; } S.craftPick = true; renderPage(); break;
        case "pot-close": S.craftPick = false; renderPage(); break; // 縮起來的爐子底下的預覽：捲回去看整張卡
        case "craft-ok": craftView().okOnly = !craftView().okOnly; renderPage(); break;
        case "forge-hub":
          if (forgeReady()) await forge();
          else toast("放一門武學和一個意境，或兩門武學，或兩個意境。");
          break;
        case "wheel":
          S.wheelSel = S.wheelSel === el.dataset.key ? null : el.dataset.key;
          S.sortieAnswer = null; // 出陣約戰應戰那張卡收起（同一時間只攤一張）
          renderPage();
          if (S.wheelSel) revealMoveCard(); // 收起（再點一次）不捲
          break;
        case "sortie-open": // 出陣約戰（丙）：出陣那一格點了在行動列底下展開出陣前那張卡、不送 act:train；再點收起。灰著也點得開
          S.wheelSel = S.wheelSel === SX_OPEN ? null : SX_OPEN;
          S.sortieAnswer = null;
          S.sortiePick = [];
          renderPage();
          if (S.wheelSel) revealMoveCard();
          break;
        case "sortie-answer": // 約戰卡上的「應戰」：同一張封三招的卡，卡頂寫應戰・那一塊
          S.wheelSel = null;
          S.sortieAnswer = el.dataset.id;
          S.sortiePick = [];
          renderPage();
          revealMoveCard();
          break;
        case "sortie-move": sortieMove(Number(el.dataset.round), el.dataset.move); break; // 封三招挑一招
        case "sortie-send": await sortieSend(); break; // 封好三招，出陣（應戰）
        case "sortie-join": await sortieDo("sortie_join", { id: el.dataset.id }); break; // 同袍的約戰：同去
        case "sortie-far": await sortieTravel(el.dataset.id); break; // 別區那一張的「前往 N 分」
        case "drill-full": // 操練用完了：點了展開移動（最近的練功點寫在行動列底下那一行）
          S.wheelSel = S.wheelSel === "move" ? null : "move";
          renderPage();
          if (S.wheelSel) revealMoveCard();
          break;
        case "gather-wheel": // 找素材分支（第 32 項）：「找素材」點了在它底下攤開（再點一次收起）；輸入框跟著收
          S.gatherOpen = !S.gatherOpen;
          S.gatherSaying = false;
          renderPage();
          if (S.gatherOpen) revealMoveCard();
          break;
        case "mt-edit": if (!S.mingtie) await loadMingtie(); mtEditOpen(); break;
        case "mt-close": S.mtEdit = null; render(); break;
        case "mt-ink": S.mtEdit.ink = Number(el.dataset.i); mtEditRedraw(); break;
        case "mt-pen": S.mtEdit.pen = Number(el.dataset.i); mtEditRedraw(); break;
        case "mt-undo": S.mtEdit.strokes.pop(); S.mtEdit.note = ""; mtEditRedraw(); break;
        case "mt-clear": S.mtEdit.strokes = []; S.mtEdit.note = ""; mtEditRedraw(); break;
        case "mt-title": {
          const E = S.mtEdit, t = el.dataset.t, cap = S.mingtie.limits.titles;
          if (E.titles.includes(t)) E.titles = E.titles.filter((x) => x !== t);
          else if (E.titles.length < cap) E.titles = [...E.titles, t];
          else { E.note = `頭銜最多 ${cap} 個：先點掉一個。`; }
          mtEditRedraw();
          break;
        }
        case "mt-shuffle": { // 刷新：從掙到的頭銜裡隨機換一批（只在這台裝置挑，定稿時伺服器再驗是不是你掙到的）
          const pool = S.mingtie.pool.slice();
          for (let k = pool.length - 1; k > 0; k--) { const j = Math.floor(Math.random() * (k + 1)); [pool[k], pool[j]] = [pool[j], pool[k]]; }
          S.mtEdit.titles = pool.slice(0, S.mingtie.limits.titles);
          mtEditRedraw();
          break;
        }
        case "mt-save": await mtSave(); break;
        case "mt-zoom-peer": if (S.peer && S.peer.card && S.peer.card.mingtie) { S.mtZoom = { name: S.peer.card.name, card: S.peer.card.mingtie }; render(); } break;
        case "mt-zoom-mine": if (S.mingtie && S.mingtie.mine) { S.mtZoom = { name: S.main.status.name, card: S.mingtie.mine }; render(); } break;
        case "mt-zoom-box": { const x = S.mingtie && S.mingtie.box[Number(el.dataset.i)]; if (x) { S.mtZoom = { name: x.name, card: x.card, when: [x.when, x.place].filter(Boolean).join("・") }; render(); } break; }
        case "mt-unzoom": if (ev.target.closest(".mt-zoom-box") && el.classList.contains("mt-zoom-layer")) break; S.mtZoom = null; render(); break;
        case "mt-report": await mtReport(); break;
        case "news":
          S.news = el.dataset.news;
          S.taleOpen = null;
          if (!selfNews(S.news)) S.newsBack = S.news; // 見聞的籤記下來：從行狀按底下的「見聞」回到這一段
          S.reportOpen = false;
          if (S.tab !== "news") { await goTab("news"); break; }
          renderPage();
          if (S.news === "reports") await loadReports(null);
          if (S.news === "annals") await loadAnnals();
          if (S.news === "xingshi") await loadXingshi();
          if (S.news === "boards") await loadBoards();
          if (S.news === "mingtie") await loadMingtie();
          break;
        case "board": S.board = el.dataset.board; renderPage(); break;
        case "board-card": await openBoardCard(el); break;
        case "board-card-close": S.boardCard = null; render(); break;
        case "report":
          S.news = "reports";
          S.reportOpen = true;
          S.taleOpen = null;
          if (S.tab !== "news") { S.tab = "news"; S.unseen = false; render(); }
          await loadReports(Number(el.dataset.id));
          window.scrollTo(0, 0);
          break;
        case "report-list": S.reportOpen = false; renderPage(); break;
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
      }
    } catch (e) { /* api() 已經提示過 */ }
  });

  document.addEventListener("input", mapQueryInput);
  document.addEventListener("input", (ev) => { // 名帖的自題一句：只換畫布上那一行，不重畫（游標留著）
    if (ev.target.id !== "mt-motto" || !S.mtEdit) return;
    S.mtEdit.motto = ev.target.value;
    const line = document.querySelector(".mt-layer .mt-motto");
    if (line) line.textContent = S.mtEdit.motto ? `「${S.mtEdit.motto}」` : "";
  });

  document.addEventListener("change", async (ev) => {
    if (ev.target.id === "anon") await doMain("anonymous", { value: ev.target.checked });
    if (ev.target.id === "adult") { // 成人內容：打開先跳確認卡（勾先放回去，確認了才算），關掉直接送
      if (ev.target.checked) { ev.target.checked = false; S.adultAsk = true; render(); } else await adultSet(false);
    }
    if (ev.target.id === "ad-front") { // 管理頁定戰況：換了一條線，數字欄換成那一條此刻的值
      const v = adTrendNow(ev.target.value), box = document.getElementById("ad-value");
      if (box && v != null) box.value = v;
    }
    if (ev.target.id === "push-on") await (ev.target.checked ? pushEnable() : pushDisable()); // 手機通知（減法季批 9）
    if (ev.target.classList && ev.target.classList.contains("push-kind")) await pushKind(ev.target.dataset.kind, ev.target.checked); // 五種各一個開關
    if (ev.target.id === "hints-off") await doMain("hints_off", { value: ev.target.checked }); // 碰到才說的小提醒（新手引導計畫三）；打開時排著的清掉
    if (ev.target.id === "mt-preset" && S.mtEdit && ev.target.value) { // 名帖：換成一張現成的畫（之後照樣能再畫幾筆）
      const art = (S.mingtie.presets || []).find((p) => p.id === ev.target.value);
      if (art) { S.mtEdit.strokes = art.strokes.map((x) => x.slice()); S.mtEdit.note = ""; mtEditRedraw(); }
    }
    if (ev.target.dataset && ev.target.dataset.act === "melt-view") { // 批量熔煉的篩選與排序
      meltView()[ev.target.dataset.key] = ev.target.value;
      renderPage();
    }
    if (ev.target.dataset && ev.target.dataset.act === "craft-view") { // 煉製頁的屬性、品質、排序
      const v = craftView();
      v[ev.target.dataset.key] = ev.target.value;
      v.all = false;
      renderPage();
    }
  });

  // 狀態列點名號展開／收起更多數值（S1）。鍵盤也按得到（Enter、空白鍵）；狀態列整塊重畫，所以按完把焦點放回去
  function toggleMore(keyboard = false) {
    S.showMore = !S.showMore;
    renderTop();
    if (keyboard) document.querySelector(".who")?.focus();
  }
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && askGo) { closeAsk(); brewShut(); return; } // 管理者確認框：Esc 等於取消（打造頁熬的小單也是，那一格不再框著）
    if ((ev.key === "Enter" || ev.key === " ") && ev.target instanceof Element && ev.target.matches('.who[data-act="toggle-more"]')) {
      ev.preventDefault();
      toggleMore(true);
    }
    // 名聲的幾個 role="button"（「名聲」那一行、圓點、玩家卡的小籤、金色的「名號傳開」）：Enter／空白鍵等於點一下
    if ((ev.key === "Enter" || ev.key === " ") && ev.target instanceof Element && ev.target.matches('[role="button"][data-act^="renown-"]')) {
      ev.preventDefault();
      ev.stopPropagation();
      ev.target.click();
    }
    if ((ev.key === "Enter" || ev.key === " ") && ev.target instanceof Element && ev.target.matches('.tx-hearsay[data-act="hear-more"]')) {
      ev.preventDefault();
      hearToggle(ev.target);
    }
    if ((ev.key === "Enter" || ev.key === " ") && ev.target instanceof Element && ev.target.matches('.tx-tight[data-act="line-more"]')) {
      ev.preventDefault();
      lineToggle(ev.target);
    }
    if ((ev.key === "Enter" || ev.key === " ") && ev.target instanceof Element && ev.target.matches('.sfront[data-act="front-more"]')) {
      ev.preventDefault();
      frontOpen(ev.target);
    }
    if ((ev.key === "Enter" || ev.key === " ") && ev.target instanceof Element && ev.target.matches('[data-act="own-more"]')) {
      ev.preventDefault();
      ownOpen();
    }
    if ((ev.key === "Enter" || ev.key === " ") && ev.target instanceof Element && ev.target.matches('.battle-fold[data-act="battle-open"]')) {
      ev.preventDefault();
      battleOpen(); // 收成一行的戰場是一個 role="button" 的 <p>：鍵盤也點得開（FB-120）
    }
    if ((ev.key === "Enter" || ev.key === " ") && ev.target instanceof Element && ev.target.matches('.bar.stam[data-act="stam-help"]')) {
      ev.preventDefault();
      S.stamOpen = !S.stamOpen;
      renderTop();
      document.querySelector('.bar.stam[data-act="stam-help"]')?.focus(); // 狀態列是重畫的：焦點放回體力條，鍵盤可以再按一次收起
    }
    if ((ev.key === "Enter" || ev.key === " ") && ev.target instanceof Element && ev.target.matches('.fronts[data-act="fronts-help"]')) {
      ev.preventDefault();
      frontsTap(); // 戰況圖卡是一顆 role="button" 的 div：鍵盤也點得開（explain-2）
    }
  });

  document.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const form = ev.target;
    const data = Object.fromEntries(new FormData(form));
    const submit = form.querySelector("[type=submit]");
    formMsg(form, ""); // 上一次的結果訊息留到這次送出為止
    try {
      if (form.id === "gate-form") {
        submit.disabled = true;
        enter(await api(S.gateMode === "register" ? "/api/register" : "/api/login", data));
      } else if (form.id === "peer-amount") {
        const i = S.peer ? S.peer.amountFor : null;
        const n = Math.floor(Number(data.amount));
        if (i == null || !(n >= 1)) return;
        S.peer.amountFor = null;
        await peerAct(i, false, n, data.choice || "");
      } else if (form.id === "peer-text") {
        const i = S.peer ? S.peer.textFor : null;
        if (i == null) return;
        S.peer.textFor = null;
        await peerAct(i, false, 0, "", (data.text || "").trim());
      } else if (form.id === "create-form") {
        submit.disabled = true;
        enter(await api("/api/character", data));
      } else if (form.id === "answer-form" || form.id === "outing-answer") { // outing-answer：走一趟那張卡上的隨口應對（outing.js）
        if (!data.text.trim()) return;
        await answer(form, data.text.trim());
      } else if (form.id === "say-form") {
        if (!data.text.trim()) return;
        await sayLine(form, data.text.trim());
      } else if (form.id === "persuade-form") {
        if (!data.text.trim()) return;
        await persuadeSay(form, data.text.trim());
      } else if (form.id === "own-name-form") {
        if (!data.text.trim()) return;
        await godName(form, data.text.trim());
      } else if (form.id === "gather-say-form") {
        if (!data.text.trim()) return;
        await gatherSay(form, data.text.trim());
      } else if (form.id === "tav-ask") {
        if (!data.target.trim()) return;
        const seek = S.tavAsk !== "ties";
        if (seek) S.tavWatch = !!data.watch;
        await tavDo(seek ? "seek" : "ties", { target: data.target.trim(), text: seek && data.watch ? "watch" : "" });
      } else if (form.id === "tav-q") {
        if (!data.text.trim()) return;
        await tavDo("", { text: data.text.trim() }, "tavern_ask");
        const box = document.querySelector('#tav-q input[name="text"]');
        if (box && S.shopNote == null) box.value = "";
      } else if (form.id === "tav-mat") {
        if (!data.material) return;
        S.tavMat = data.material;
        await tavDo("material", { target: data.material });
      } else if (form.id === "tav-hit") {
        if (!data.target.trim()) return;
        S.tavHush = !!data.hush;
        const tier = S.main.shop.hits.tiers.some((t) => t.tier === S.tavTier) ? S.tavTier : 1;
        const name = S.main.shop.hits.tiers.find((t) => t.tier === tier).name;
        ask(`雇${name}去找${data.target.trim()}？`, "雇", () => tavDo("hit", { target: data.target.trim(), text: `${tier}${data.hush ? ":hush" : ""}` }));
      } else if (form.id === "tav-wall") {
        if (!data.text.trim()) return;
        await tavDo("wall", { text: data.text.trim() });
        const box = document.querySelector('#tav-wall input[name="text"]');
        if (box && !(S.shopNote || "").startsWith("一句最多")) box.value = "";
      } else if (form.id === "free-form" || form.id === "arena-free") {
        if (!data.text.trim()) return;
        await doMain(["duel_text", "seal_text", "feast_text"].includes(form.dataset.op) ? form.dataset.op : "battle_text", { text: data.text }); // 決戰、奪璽或頭目戰的放手一搏
      } else if (form.id === "name-art") {
        // 絕學定名：名字合不合格、有沒有人用過都由伺服器驗，結果寫在頁面上方那一行；定成了表單就不再畫
        if (!data.name.trim()) { toast("先取個名字。"); return; }
        await mx("name", { name: data.name });
        // 被拒了（表單還在，原因寫在頁面上方那一行）：mx 重畫的表單是空的，把剛打的字放回去，不用重打；定成了表單就不在
        const again = document.querySelector('#name-art input[name="name"]');
        if (again && S.menxia && S.menxia.naming) again.value = data.name;
      } else if (form.dataset && form.dataset.op === "name-divine") {
        // 神器原品定名（5.2）：名字合不合格、有沒有人用過都由伺服器驗，結果寫在頁面上方那一行；定成了那一列就不再畫表單
        if (!data.name.trim()) { toast("先取個名字。"); return; }
        await mx("name_divine", { weapon: form.dataset.id, name: data.name.trim() });
        // 被拒了（那一列的表單還在，原因寫在頁面上方那一行）：原因也記下來、表單裡留一行（FB-193），重畫；mx 重畫的表單是空的，
        // 把剛打的字放回去，不用重打（同絕學定名那張）。表單 id 帶著裝備 id 的冒號，用 getElementById 找（不走選擇器）；
        // 定成了那一列不再畫表單，找不到就什麼都不放
        if (document.getElementById("name-divine-" + form.dataset.id)) {
          S.divineWhy[form.dataset.id] = (S.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
          renderPage();
        }
        const again = document.getElementById("name-divine-" + form.dataset.id)?.querySelector('input[name="name"]');
        if (again) again.value = data.name;
      } else if (form.dataset && form.dataset.op === "shop-name-divine") {
        // 店面上替神器原品定名（店面獨立介面設計 2.3、2.5）：同修練頁那一張；被拒了剛打的字放回去（id 帶冒號，用 getElementById）
        if (!data.name.trim()) { toast("先取個名字。"); return; }
        const said = await shopMx("name_divine", { weapon: form.dataset.id, name: data.name.trim() });
        if (document.getElementById("shop-name-divine-" + form.dataset.id)) { S.divineWhy[form.dataset.id] = said; renderShop(); } // 被拒的原因留在表單裡（FB-193）
        const again = document.getElementById("shop-name-divine-" + form.dataset.id)?.querySelector('input[name="name"]');
        if (again) again.value = data.name;
      } else if (form.id === "ad-mall-form") {
        // 管理者查一個人的元寶帳（商城第二批）：查到了畫在表單底下，查不到的原因寫在表單那一行。抽屜不關
        const name = (data.name || "").trim();
        S.adMallName = name;
        S.adMallMsg = ""; S.adMallOk = false;
        S.adMallNote = String((document.getElementById("ad-mall-note") || {}).value || "");
        if (!name) { S.adMall = null; formMsg(form, "先填名號或帳號。"); return; }
        S.adMall = await api("/api/admin/mall", { name });
        renderKeepingSheet();
      } else if (form.id === "ad-player-form") {
        // 管理者查一個玩家（玩家個人劇情）：查到了畫他的召見、機緣、伏筆三列；查不到的原因寫在表單那一行。抽屜不關
        const name = (data.name || "").trim();
        S.adPlayerName = name;
        if (!name) { S.adPlayer = null; formMsg(form, "先填名號。"); return; }
        S.adPlayer = await api("/api/admin/player", { name });
        renderKeepingSheet(); // 查到的那個人就在表單底下：抽屜停在原地（審查 M-2）
      } else if (form.id === "pw-form") {
        // 改密碼、重設密碼一律回 200，訊息就是結果（失敗時寫原因）；成功才清空欄位，失敗留著讓人改
        const r = await api("/api/password", data);
        const ok = r.message === "密碼已更新。";
        formMsg(form, r.message, ok);
        if (ok) form.reset();
      } else if (form.id === "reset-form") {
        // 重設密碼也先問一次（G3）。結果寫在表單那一行、也釘在管理頁底下（成了的那一條連臨時密碼一起寫，私下告訴他之前不必再找一次）；
        // 失敗時欄位留著改，跟改密碼一樣
        const target = (data.target || "").trim();
        const temp = String(data.temp || "");
        S.adResetTarget = target;
        if (!target) { formMsg(form, "先填要重設的帳號或名號。"); return; }
        if (temp.length < AD_PW_MIN) { formMsg(form, `臨時密碼至少 ${AD_PW_MIN} 個字（可以按「產生一組」）。`); return; }
        ask(`重設 ${target} 的密碼，臨時密碼是「${temp}」：他原本的密碼不能再用，確定？`, "確定重設", async () => {
          // 結果寫進「那時候」畫面上的表單：問的期間抽屜可能被重畫過（例如前一個動作剛回來），按下時抓到的那個已經不在了；
          // 抽屜整個關了就改用提示泡泡講
          const say = (text, ok = false) => {
            const now = document.getElementById("reset-form");
            if (now) formMsg(now, text, ok);
            else if (text) toast(text);
            return now;
          };
          say("");
          try {
            const r = await api("/api/admin/reset_password", data);
            const ok = /^已重設 .+ 的密碼。$/.test(r.message || "");
            if (S.adminPage) {
              S.adResult = { text: ok ? `${r.message}臨時密碼：${temp}（私下告訴他，登入後到設定改掉）` : r.message, ok };
              if (ok) { S.adResetTarget = ""; S.adAccounts = null; }
              renderKeepingSheet();
            }
            const now = say(r.message, ok);
            if (ok && now) now.reset();
          } catch (e) {
            say(failText(e));
          }
        });
      }
    } catch (e) {
      if (submit) submit.disabled = false;
      formMsg(form, failText(e)); // 沒有訊息行的表單不受影響
    }
  });

  // ── 計時器：體力、氣血跟著時間走；別人推動的大勢也會進來 ──
  // 上一次輪詢還沒回來就不再打（最終審查 Critical 1）：伺服器忙著的時候（等行動鎖、別人開爐取名），
  // 卡住的 /api/main 不能每 10 秒再疊一個，把伺服器的執行緒池用光
  let pollInFlight = false;
  async function poll() {
    if (pollInFlight || S.stage !== "game" || S.busy || S.adminPage || (document.hidden && !sealWatched())) return; // 管理頁不輪詢：重畫會把填到一半的欄位洗掉，要新的按「重新整理」 // 背景分頁不輪詢，奪璽例外（sealWatched）
    pollInFlight = true;
    lastPoll = Date.now();
    const was = S.main;
    try {
      const mode = S.moveMode;
      const main = await api("/api/main");
      if (mode !== S.moveMode) return; // 等回應的時候換了走法：這份是舊走法的選單，不用
      // 等回應時玩家做了動作：S.main 已經換成動作回來的那一份（比這份新），這一輪作廢
      if (S.stage !== "game" || S.busy || S.main !== was) return;
      if (!setMain(main)) return;
      renderTop();
      if (S.peer) refreshPeer(); // 玩家卡開著：卡也重抓（FB-117；不等它）
      if (!typing()) await refreshPage(was);
    } catch (e) { /* api() 提示過；下一輪再試 */ } finally { pollInFlight = false; }
  }

  // 輪詢拿到有變的 main 之後，照目前的分頁補上（QA L1）。江湖、見聞從 S.main 畫；修練、煉製、輿圖重抓自己那一份。
  // 重抓回來時玩家若已經切了分頁、按了別的（那份資料已經換過）、正在忙或正在打字，就不動畫面，下一輪再說。
  async function refreshPage(old) {
    sealActPolled(old); // 獨門行動選目標的那一層（改版第 2 批）：開著而且資料變了只換那一層；底下的頁面照常補
    if (shopPolled(old)) return; // 店面開著（或剛開、剛收）：只管店面那一層（店面獨立介面設計 1.3）
    if (S.mallOpen) { // 商城那一層開著：底下的頁面被蓋住、不畫（出店時整個重畫）；餘額變了（管理者補發、別的分頁買了）才重抓這一頁
      if (!S.main.mall) { closeMall(); return; }
      if ((old && old.mall ? old.mall.balance : null) !== S.main.mall.balance) {
        await loadMall();
        if (S.mallTab === "log") await loadMallLog();
        if (S.mallTab === "look") await loadLooks();
      }
      return;
    }
    const tab = S.tab;
    if (tab === "jianghu") {
      if (pageKey(old) !== pageKey(S.main)) { // 只有狀態列變了（時鐘在走）：上面 renderTop 已經畫過
        // 手指正按在畫面上：這時整頁換掉，按下去的那一顆就不在了，放開時 click 落空（按了沒反應）。等放開再畫
        if (pointerHeld) redrawHeld = true;
        else renderPage();
      } else paintSealWhen(); // 只有奪璽卡的倒數在走：換那一行的字就好（FB-182）
      return;
    }
    if (tab === "news") {
      // 形勢子分頁畫的是 S.xingshi（/api/xingshi）：開了新單、寫好了（main.xingshi_mark 變了）就重抓（FB-578：以前要切籤才換上）
      if (S.news === "xingshi") {
        if (old.xingshi_mark !== S.main.xingshi_mark) await loadXingshi();
        return;
      }
      // 戰報子分頁畫的是 S.reports，不用重抓；其他子分頁只在它畫的那幾欄真的變了才重畫
      const fields = { trends: ["trends"], rumors: ["rumors", "rumor_layers"], chronicle: ["chronicle"], journal: ["latest", "journal", "older"] }[S.news] || [];
      // rumor_layers 是陣列（每次輪詢都是新的物件）：比內容不比參照，沒變就不重畫
      if (fields.some((k) => JSON.stringify(old[k]) !== JSON.stringify(S.main[k]))) redrawPage(true);
      return;
    }
    if (tab === "practice" || tab === "craft") {
      const was = S.menxia;
      if (!was) return; // 還在載入，goTab 會畫
      const x = await api(`/api/menxia${S.person ? `?person=${encodeURIComponent(S.person)}` : ""}`);
      if (S.stage !== "game" || S.tab !== tab || S.busy || S.menxia !== was || typing()) return;
      S.menxia = x;
      const trimmed = trimForgeSel();
      if (S.artOpen && !x.owned_arts.some((a) => a.id === S.artOpen)) { S.artOpen = null; S.artNote = null; } // 那一門已經不在了（熔掉）
      if (!S.forgeSel.length) { S.forgeLine = ""; S.forgePreview = null; } // 爐是空的：用伺服器剛給的那一行（心得是新的）
      // 卡上的「氣血 520/639」每分鐘都在回：拿它比的話修練頁每一輪輪詢都判定「變了」而整頁重畫——
      // 畫面閃一下、捲軸彈回最上面（Joy 2026-10-22 在選意境那頁停久了遇到；上面那段註解自己就寫了
      // 「本人卡上的氣血一直在回」，卻還是把 player_card 留在清單裡）。比的時候把氣血的數字抹掉，
      // 等級、武學、內功真的變了照樣重畫；氣血的即時顯示本來就靠狀態列（renderTop 另外畫）。
      const steady = (v) => (typeof v === "string" ? v.replace(/氣血 [\d.]+\/[\d.]+/g, "氣血") : v);
      const shown = (m) => JSON.stringify(MENXIA_SHOWN[tab].map((k) => steady(m[k])));
      const changed = trimmed || shown(x) !== shown(was)
        || (tab === "practice" && old.status.injury !== S.main.status.injury) // 療傷鈕看的是內傷
        || (tab === "practice" && JSON.stringify((old.status.seal && old.status.seal.act) || null) !== JSON.stringify(sealActNow())) // 傳承那一列的鈕（獨門行動）
        || S.guideDrawn !== guideSig(); // 對話框換了（輪詢帶來新的提示、提示在別處被收掉）：兩頁最上面畫著它
      if (!changed) {
        // 合成與合併都要花體力、體力隨時間回：爐裡放著東西時說明裡的「體力不足」要跟著更新（只換那一行，不整頁重畫）
        if (tab === "craft" && S.forgeSel.length && old.status.stamina !== S.main.status.stamina) updateForgeLine();
        return;
      }
      redrawPage(true);
      // 爐裡有東西：說明裡的心得、能不能開爐也跟著更新
      if (S.forgeSel.length && (trimmed || tab === "craft")) updateForgeLine();
      return;
    }
    if (tab === "map") {
      const was = S.mapState;
      if (!was) return;
      const moved = old.status.location !== S.main.status.location || !!old.on_road !== !!S.main.on_road; // 抵達、出發、喊停
      const every = S.main.on_road ? 0 : MAP_STATE_EVERY; // 在路上：每一輪都重抓，「還有幾分鐘」跟著走
      if (!moved && Date.now() - S.mapStateAt < every) return;
      await loadMap();
    }
  }

  // 修練、煉製兩頁各自畫了 menxia 的哪幾欄（照 pagePractice／pageCraft）：輪詢只在這幾欄變了才重畫。
  // 不比整份，是因為本人卡上的氣血一直在回，整份 menxia 幾乎每分鐘都不一樣，煉製頁根本沒畫那張卡
  const MENXIA_SHOWN = {
    practice: ["rules", "slot_cards", "owned_arts", "insights", "holdings", "naming", "player_card", "roster", "person", "person_card", "on_team", "lessons", "gear"],  // 療傷鈕 2026-10-25 拿掉了（Joy）：heal、heal_cost 不再看
    craft: ["owned_arts", "insights", "holdings", "clue_items", "bag", "forge_line", "xinde"],
  };

  // 重畫這一頁但保留玩家正在做的事（輪詢時用）：填到一半的欄位（表單裡的字）、
  // 摺疊區的開合（輿圖的取景每次照地圖框重算，重畫照舊套用）。
  // quiet：輪詢的重畫，頁面上方那一行訊息沒有變，不要再播一次浮現動畫
  function redrawPage(quiet = false) {
    const page = document.getElementById("page");
    if (!page) return;
    const fields = [...page.querySelectorAll("form[id] input[name], form[id] select[name], form[id] textarea[name]")]
      .map((el) => [el.form.id, el.name, el.value]);
    const folds = [...page.querySelectorAll("details > summary")].map((s) => [s.textContent, s.parentElement.open]);
    renderPage();
    if (quiet) page.querySelectorAll(".msg").forEach((el) => el.classList.add("still"));
    for (const [form, name, value] of fields) {
      const el = page.querySelector(`#${CSS.escape(form)} [name="${CSS.escape(name)}"]`);
      if (el) el.value = value;
    }
    for (const [text, open] of folds) {
      const s = [...page.querySelectorAll("details > summary")].find((x) => x.textContent === text);
      if (s) s.parentElement.open = open;
    }
  }


  // ── 伺服器推送（線上架構設計 5.3）──
  // main.push 是 true 才用（伺服器的開關 Config.push_events，預設關）。關著的時候這一段什麼都不做，頁面跟以前一模一樣：
  // 一個每 POLL_MS 的計時器、每一下都輪詢、不開 EventSource。開著：開一條 /api/events（SSE），伺服器只送「哪一種變了」，
  // 頁面收到再抓 /api/main：
  //   self＝這個角色別的分頁做了動作，馬上抓（自己這一下動作的回聲不算）；
  //   world＝世界變了，每個分頁都會收到，所以隨機等 0～push_spread 秒再抓，全服不會同一兩秒擠進同一把行動鎖；
  //   ping＝連線上沒事時每 15 秒一個，證明連線還活著（SSE 的註解行到不了這裡，所以伺服器把心跳寫成事件）。
  // 連著的時候平常 SLOW_POLL_MS 才輪詢一次（時鐘、體力回復靠它，也是漏掉通知的安全網）；沒開、斷了、還沒連上就照舊每 POLL_MS 一次。
  const SLOW_POLL_MS = 60000;
  const BEAT_TIMEOUT_MS = 40000; // 連線上這麼久一個事件也沒有：半開的死連線（手機睡著、換網路，瀏覽器很久才發現），關掉重連
  const RECONNECT_MS = 60000; // 連線被伺服器拒絕（502、401、404：EventSource 不再自己重連）之後，隔這麼久才再試
  const ECHO_MS = 1500; // 動作剛做完這麼久之內收到的 self，當作這個動作自己的回聲（畫面已經是動作回來的那一份）
  let events = null; // 目前這一條 EventSource；沒開、關了、被伺服器拒絕時是 null
  let lastBeat = 0; // 這條連線上最後一次有消息（開了、收到任何事件）的時刻
  let lastConnect = 0; // 上一次開連線的時刻
  let lastPoll = 0; // 上一次開始輪詢、或拿到一份新畫面（動作回來的）的時刻；連著推送時慢速輪詢從這裡算（預檢 F3）
  let lastAction = 0; // 上一次動作做完的時刻
  let worldTimer = 0; // 已經排好的「世界變了」重抓
  let pushDown = false; // 連線斷過、還沒補抓：連回來時補抓一次（斷的這段時間可能漏了通知）

  // 奪璽（玉璽碎片設計 5.5）：背景分頁不輪詢，單挑的雙方、被璽動那一場的持有者與參戰者例外（status.seal_watch），在背景也照輪詢（poll 讀它）；
  // 輪到你出招時改分頁標題、之後改回原本的（setMain 每拿到一份畫面就照它改）。放在這一段裡：poll、setMain 的測試照這一段切程式
  function sealWatched() {
    return !!(S.main && S.main.status && S.main.status.seal_watch);
  }
  function sealTitle() {
    const d = S.main && S.main.status && S.main.status.seal_duel;
    return d && d.turn ? "【奪璽】輪到你出招" : S.baseTitle;
  }

  function connectEvents() {
    if (events || !window.EventSource || S.stage !== "game" || !S.main || !S.main.push || document.hidden) return;
    lastConnect = lastBeat = Date.now();
    const es = new EventSource("/api/events");
    events = es;
    es.onopen = () => {
      lastBeat = Date.now();
      S.pushLive = true;
      if (pushDown) { pushDown = false; poll(); }
    };
    es.onerror = () => {
      S.pushLive = false; // 輪詢回到每 10 秒（Review Focus 2）；EventSource 自己會重連，連回來再放慢
      pushDown = true;
      if (events === es && es.readyState === EventSource.CLOSED) events = null; // 伺服器拒絕了、不會再自己重連：pollTick 隔 RECONNECT_MS 再試
    };
    es.addEventListener("ping", () => { lastBeat = Date.now(); });
    es.addEventListener("self", () => { lastBeat = Date.now(); onPushSelf(); });
    es.addEventListener("world", () => { lastBeat = Date.now(); onPushWorld(); });
  }

  function closeEvents() {
    if (events) events.close();
    events = null;
    S.pushLive = false;
    pushDown = false;
    clearTimeout(worldTimer);
    worldTimer = 0;
  }

  // self：馬上抓。自己按的這一下動作，伺服器也會通知這個角色的每個分頁，包括這一個（回聲）：通常動作還沒回來就到了（busy 時 poll 不會跑），
  // 偶爾比回應慢一點到，所以動作剛做完的 ECHO_MS 內也不抓：畫面已經是動作回來的那一份，不為一次按鍵抓兩次。
  // 代價：這一小段時間內、別的分頁剛好也做了動作的話，這一個分頁最慢要等下一次慢速輪詢（60 秒）才跟上
  function onPushSelf() {
    if (S.busy || Date.now() - lastAction < ECHO_MS) return;
    poll();
  }

  // world：每個分頁都會收到，隨機等 0～push_spread 秒再抓（伺服器的 push_world_min_seconds）；已經排了一次就不再排，它抓到的就是最新的
  function onPushWorld() {
    if (worldTimer) return;
    const spread = Number(S.main && S.main.push_spread);
    const wait = Math.random() * (Number.isFinite(spread) && spread >= 0 ? spread : 10) * 1000;
    worldTimer = setTimeout(() => { worldTimer = 0; poll(); }, wait);
  }

  // 計時器每 POLL_MS 一下（體力、氣血跟著時間走）。推送沒開：每一下都輪詢（跟加推送以前的計時器一樣）。
  // 推送開著：先照顧連線（約 40 秒沒消息就換一條；被拒絕之後隔一陣再試；離開遊戲就關），再看要不要輪詢：
  // 連著時離上一次拿到畫面不到 55 秒就不問（這一下是 10 秒的倍數，所以約每 60 秒一次），沒連上就照舊每一下都問
  function pollTick() {
    const now = Date.now();
    if (S.stage === "game" && S.main && S.main.push) {
      if (events && now - lastBeat > BEAT_TIMEOUT_MS) { closeEvents(); pushDown = true; connectEvents(); }
      else if (!events && now - lastConnect >= RECONNECT_MS) connectEvents();
    } else if (events) closeEvents();
    if (S.pushLive && now - lastPoll < SLOW_POLL_MS - POLL_MS / 2) return;
    poll();
  }

  setInterval(pollTick, POLL_MS);

  // 決戰的「最遲 M 分 S 秒後結算」每秒自己倒數（Joy 2026-10-13：以前十秒一次的輪詢才跳一下）：只改頁面上那幾個字，不重畫；
  // 倒數到零補問一次，回合逾時結算了就換上新的一回合。奪璽卡的倒數走同一個計時器、照它自己的期限（tickSeal，FB-182）：
  // 那一行跟決戰寫法一樣，所以決戰這一段跳過奪璽卡裡的字
  const DUE_TEXT = /最遲 \d+ 分 \d+ 秒後結算|時間到了，即將結算/;
  function dueText(left) {
    return left ? `最遲 ${Math.floor(left / 60)} 分 ${left % 60} 秒後結算` : "時間到了，即將結算";
  }
  function tickDue() {
    if (S.stage !== "game") return;
    if (S.sealDueAt != null) tickSeal();
    if (S.dueAt == null) return;
    const page = document.getElementById("page");
    if (!page) return;
    const left = Math.max(0, Math.ceil((S.dueAt - Date.now()) / 1000));
    const walker = document.createTreeWalker(page, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      if (n.parentNode && n.parentNode.closest && n.parentNode.closest(".seal-duel")) continue; // 奪璽卡歸 tickSeal
      if (DUE_TEXT.test(n.nodeValue)) n.nodeValue = n.nodeValue.replace(DUE_TEXT, dueText(left));
    }
    if (!left && !S.duePolled) { S.duePolled = true; poll(); }
  }
  setInterval(tickDue, 1000);
  // 看不到的分頁：關掉連線（不佔一條連線，也不重抓）；看得到了：連回來、補抓一次（推送沒開時只有補抓，跟以前一樣）
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) { closeEvents(); return; }
    connectEvents();
    poll();
  });
  // ── 伺服器推送（完）──

  // 軍令卡的展開與否（計畫 T6）：toggle 不冒泡，用捕獲階段接。記的是週次：換週之後新畫的卡週次對不上，自然重新展開；
  // 重畫（輪詢、換分頁回來）時照 S.ordersShut 補回，那一下補出來的 toggle 記下的還是同一週，不會繞圈
  document.addEventListener("toggle", (ev) => {
    const box = ev.target;
    if (box instanceof Element && box.matches("details.bounties")) S.bountyShut = box.open ? null : box.dataset.key;
    else if (box instanceof Element && box.matches("details.seal-duel")) S.sealShut.duel = box.open ? null : box.dataset.key; // FB-182
    else if (box instanceof Element && box.matches("details.seal-card")) S.sealShut.card = box.open ? null : box.dataset.key;
    else if (box instanceof Element && box.matches("details.orders")) S.ordersShut = box.open ? null : Number(box.dataset.week);
    // 「此地還能做」：記玩家（或自動打開）之後的開合與地點（hereFold），重畫、輪詢、擋下來都照它補回（FB-087）
    else if (box instanceof Element && box.matches("details.here")) S.here = { at: (S.main && S.main.status && S.main.status.location) || "", open: box.open };
    // 俠客頁底下的摺疊（功法庫、裝備、門下、規矩）：記開合，輪詢重畫照樣
    else if (box instanceof Element && box.matches("details.self-fold")) (S.selfOpen || (S.selfOpen = {}))[box.dataset.sec] = box.open;
    // 出陣約戰的卡上收成一行的那幾段（這一塊、贏了、守住了）：記開合，輪詢重畫、挑招換卡照樣
    else if (box instanceof Element && box.matches("details.sx-det")) (S.sortieFold || (S.sortieFold = {}))[box.dataset.sec] = box.open;
    // 決戰攤開、收起舊的回合（roundBlocks）：只記下來，下一次輪詢重畫照樣
    else if (box instanceof Element && box.matches("details.b-round")) {
      const open = S.roundsOpen || (S.roundsOpen = new Set());
      if (box.open) open.add(box.dataset.round); else open.delete(box.dataset.round);
    }
    // 決戰一軍發動武學那一列攤開、收起（main.js 的 warFolds）：記下來，輪詢重畫照樣
    else if (box instanceof Element && box.matches("details.b-fold")) {
      const open = S.foldOpen || (S.foldOpen = new Set());
      if (box.open) open.add(box.dataset.fold); else open.delete(box.dataset.fold);
    }
    // 見聞「形勢」攤開、收起哪一篇（xingshiHtml）：記篇次，重畫照樣（最新那一篇收起來也記得）
    else if (box instanceof Element && box.matches("details.xs-essay")) {
      (S.xingshiOpen || (S.xingshiOpen = new Map())).set(Number(box.dataset.n), box.open);
    }
    // 摺疊開了或收了：發光的鈕在裡面的話，光在鈕與標題列之間換邊（glowTarget）
    if (S.stage === "game") applyGlow();
  }, true);

  // 視窗大小變了（轉向、拉視窗）：輿圖開著就重新夾住、套用；原本是整張就維持整張（applyMapView）
  let cueTimer = 0;
  window.addEventListener("resize", () => {
    if (S.stage === "game") fitBars(); // 條的寬度跟著變：「體力」「氣血」兩個字放不放得下重量（FB-198）
    if (S.stage === "game" && S.tab === "map") { mapFrame(); setMapDrawer(S.mapDrawer); applyMapView(); }
    if (S.stage === "game" && S.tab === "jianghu") { fitFirstRound(); fitOnResize(); } // 寬度變了，第一回合佔幾行、第一屏放不放得下也跟著變（只有高度變了不重量，見 fitOnResize）
    // 序章裡師父框上的「在下面 ↓」只在畫面重畫時算；視窗大小變了（轉向、拉視窗）目標離第一屏多遠也跟著變，去抖後重算、不重畫（T7 走查 W-F）
    clearTimeout(cueTimer);
    cueTimer = setTimeout(() => { if (S.stage === "game") guideCue(); }, 150);
  });
  // 寬度跨過手機分界（轉向、拉視窗）：江湖頁的排列順序不同（pageJianghu 的輪盤），要重畫
  const onPhoneChange = () => { if (S.stage === "game" && S.tab === "jianghu") renderPage(); };
  if (PHONE) { if (PHONE.addEventListener) PHONE.addEventListener("change", onPhoneChange); else PHONE.addListener(onPhoneChange); }
  // 字型載入完，字寬跟著變：狀態列那兩個字放不放得下重量一次（FB-198）
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => { if (S.stage === "game") fitBars(); });

  api("/api/me").then(enter).catch(() => { S.stage = "gate"; render(); });
