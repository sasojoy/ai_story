/* 天下大勢的網頁前端：沒有建置步驟、不靠外部函式庫。
 *
 * 畫面只有三種：登入、取名號、遊戲。遊戲畫面 = 頂上的狀態列 + 一頁內容 + 底部五個分頁：
 *   江湖（場景與選項）、修練（練成、閉關、武學與意境、修練與熔煉、名冊）、煉製（太極火爐：武學＋意境、武學＋武學合成，意境＋意境合併）、
 *   輿圖、見聞（戰報、大勢、傳聞、江湖史、紀錄）。
 * 設定與管理者工具收在右上角的抽屜裡。
 *
 * 伺服器給的 HTML（場景、角色卡、戰報、江湖紀錄、地圖）已經在伺服器端跳脫過；
 * 這裡自己組的字串一律經過 esc()。
 */
(() => {
  "use strict";

  const TABS = [
    { id: "jianghu", ico: "江", name: "江湖" },
    { id: "practice", ico: "修", name: "修練" },
    { id: "craft", ico: "煉", name: "煉製" },
    { id: "map", ico: "圖", name: "輿圖" },
    { id: "news", ico: "聞", name: "見聞" },
  ];
  const NEWS = [
    { id: "reports", name: "戰報" },
    { id: "trends", name: "大勢" },
    { id: "rumors", name: "傳聞" },
    { id: "chronicle", name: "江湖史" },
    { id: "journal", name: "紀錄" },
  ];
  const POLL_MS = 10000;
  const KINDS = ["武學", "內功"];
  // 江湖頁「前往」的走法（跟 atlas.MODES 同一份）。選的走法只放在 S.moveMode：不寫進 localStorage、cookie，
  // 重新整理頁面就回到步行；每個請求都帶著它（見 api()），伺服器照它排選單上的「前往」
  const FREE_TEXT_OPTION = "choice:free"; // 事件的隨口應對（engine.FREE_TEXT_OPTION）
  const SAY_OPTION = "talk:say"; // 跟人物對話時的「自己說」（engine.SAY_OPTION）：按了叫出輸入框，送出走 /api/say
  const SENSE_DRAW = "sense:draw"; // 有所感進了感悟狀態：「把心中的形畫下來」叫出畫布（sensing.DRAW），畫好送 /api/sense
  const MOVE_MODES = [
    { id: "walk", name: "步行" },
    { id: "hurry", name: "趕路" },
    { id: "dash", name: "疾行" },
  ];
  // 照「走法」切換的選項：「前往」與路上的「折返」（路上設計 3.2）。切換鈕緊貼在第一個這種選項上面（A4／W6）
  const followsMode = (id) => id.startsWith("move:") || id.startsWith("road:back");
  const ROAD_TASKS = /^road:(think|ask|survey|gather)$/; // 路上的四樣小事（engine.ROAD_TASKS），排成 2×2（FB-055）
  // 路上的江湖頁多三個捷徑（路上設計 3.3）：是頁面切換，不是引擎的行動
  const ROAD_LINKS = [
    { tab: "map", name: "打開輿圖改去別處" },
    { tab: "practice", name: "去修練" },
    { tab: "craft", name: "去煉製" },
  ];
  // 三方態勢（第一季設計 4.4，status.stances 的鍵）：狀態列展開時那一行；第一季濃縮版才有
  const STANCE_NAMES = [["guan", "官軍"], ["huang", "黃巾"], ["haoqiang", "豪強"]];
  // 手機寬度：第一次打開輿圖時，手機照原尺寸，寬螢幕照框寬（最多原尺寸），都對準所在地（見 mapReady）
  const PHONE = window.matchMedia ? window.matchMedia("(max-width: 767px)") : null;

  const S = {
    stage: "boot",
    gateMode: "login",
    main: null,
    mainKey: "",
    tab: "jianghu",
    nowOpen: null, // 江湖頁「剛剛」展開的那一則（記內容本身）；換成新的一則就收回（A4）
    roundsOpen: null, // 江湖頁戰鬥卡片「過程」展開的那一場（戰報流水號）；換成新的一場就收回（計畫三 G6）
    peekOpen: null, // 江湖頁那一排小標（態勢｜大事｜主線）展開著的那一塊：{ id, week }；點同一個收起，換週就不再對得上（FB-039、正式版辛）
    hearOpen: null, // 戰鬥卡片底下聽來的那一句展開著的那一場（卡片的戰報流水號）；換成下一場就收回（FB-074）
    // 第一屏放不下時一步一步收（FB-107 的 fitFirstScreen）：
    fitted: [], // 這一次收了哪幾步（FIT_STEPS 的 key），給測試與除錯看
    fitWidth: 0, // 上一次量的是哪個寬度：視窗只有高度變了（手機網址列收合）不重量（fitOnResize）
    fitBase: null, // 量的基準：{ width, top } 這個寬度量到過最小的分頁列頂（網址列跑出來時），不跟著網址列跑（fitTabsTop，FB-123）
    fitting: false, // fitFirstScreen 正在收：它自己重畫狀態列（收 💡、還原）時不再重量（fitTopMoved，FB-123）
    hintTight: false, // 💡 收成一行（第 3 步要的）；狀態列照它畫（hintHtml），玩家點開了（hintOpen）就一直攤開
    linesOpen: null, // 戰鬥卡片底下收成一行的補充攤開著的那一場（卡片的戰報流水號），重畫時不再收（第 4 步）
    ownOpen: null, // 決戰時收成一行的所在地、集結那一句攤開過的那一處那一場（fitOwnKey），重畫時不再收（第 7、8 步）
    battleOpen: null, // 只能觀戰的人攤開了的開打中的戰場（戰場的名字）；收起、這一場打完就清掉（battleScene，FB-120）
    boardSeen: null, // 這個名號看過的本週大事：{ owner, season, week, count }；記憶體裡一份，localStorage 另存一份（見 boardSeen）
    ordersShut: null, // 江湖頁「本週軍令」收起來的那一週；換週就重新展開（計畫 T6）
    bountyShut: null, // 江湖頁「懸賞」卡收起來時手上那幾張的 id（逗號接起來）；揭了新的或交了差就重新展開
    here: null, // 江湖頁「此地還能做」摺疊的開合：{ at 地點, open }，玩家自己開關的、或發光那一步自動打開的；重畫（鈕被擋下來、輪詢）照它補回，換了地方就不對得上（FB-087）
    hereAuto: {}, // 發光那一步（框的 key）在哪一處自動打開過摺疊了：「key@地點」→ true；每一步在每一處只自動打開一次，之後照玩家的（FB-087）
    sceneOpen: false, // 在路上時場景那段說明展開著嗎（預設只露兩行，FB-055）；下了路就清掉
    hintOpen: false, // 在路上（或 FB-107 收成一行，hintTight）時狀態列的 💡 提示展開著嗎（預設只露一行，FB-060）；下了路、不收了就清掉
    guideRoad: null, // 在路上、或眼前有事件待處理（pending 的那一句）時說書人的框展開著的那一句（內容本身）；這兩種預設收成一行，離開就清掉（FB-055、FB-076）
    busy: false,
    menxia: null,
    message: "",
    person: null,
    kind: "武學",
    artOpen: null, // 修練頁武學清單裡點開的那一門（id）；切分頁、改練成功之後收起
    artInfo: null, // 修練頁哪一門攤開了「詳情」（完整的功法卡）
    libFilter: null, // 修練頁功法庫的篩選：all／武學／內功／ready（可修練）；武學多時才出現。null＝還沒讀過這個瀏覽器記的（libFilter()，FB-085）
    libAll: false, // 功法庫列完了沒（武學多時先只列 LIB_PAGE 門）
    rackAll: false, // 裝備庫列完了沒（兵器多時先只列 LIB_PAGE 件，同功法庫）
    insOpen: null, // 修練頁點開的那一個意境（攤開說明與「化成心得」）
    artNote: null, // 修練（衝品質）的結果：{ id, html }，寫在那一門卡片的按鈕底下（W7）；點別的卡片、切分頁、做別的動作就清掉
    legendTick: {}, // 修練頁每一門武學「服下破境丹」勾了沒（id → true）；預設不勾，輪詢重畫不會悄悄取消，修練送出之後清掉
    forgeSel: [], // 爐裡放的：{type: "art" | "ins", id}，最多兩樣、武學最多兩門（武學＋意境、武學＋武學＝合成，兩個意境＝合併）
    wheelSel: null, // 江湖頁行動列展開的那一格（目前只有 move）
    sensing: false, // 有所感：畫布叫出來了沒（按了「把心中的形畫下來」）；感悟狀態結束（選單上沒有 SENSE_DRAW）就收起
    sensePts: [], // 畫布上那一筆的點位 [[x, y, 毫秒], …]（畫布座標 0～256）；輪詢重畫頁面之後照它補畫回去
    senseNote: "", // 畫布底下那一行：這一筆落下了沒（/api/sense_read；不寫筆畫的幾何）
    stroking: false, // 手指正按在畫布上：輪詢不重畫（重畫會換掉畫布、手指底下的那一筆就斷了）
    forgeLine: "",
    map: null,
    layer: "situation",
    // 輿圖的視圖（W16）：{ s 倍率, cx, cy 視窗中心對著的地圖座標 }。這次載入網頁後第一次打開輿圖才決定（mapReady：
    // 對準所在地，手機原尺寸、寬螢幕照框寬，都不給整張），之後切分頁、輪詢重畫、換圖層、點地點都留著
    mapView: null,
    // 輿圖圖例展開與否：undefined＝這次載入網頁還沒讀 localStorage，null＝這位玩家沒選過（照寬度）；true／false＝選過（見 legendOpen）
    mapLegend: undefined,
    news: "reports",
    reports: null,
    reportOpen: false,
    showMore: false,
    sheet: false,
    admin: null,
    adPlayerName: "", // 管理者區「玩家個人劇情」查的名號與查到的那份（/api/admin/player）；登出清掉
    adPlayer: null,
    unseen: false,
    offline: false,
    moveMode: "walk",
    prologueKey: "", // 上一次整頁重畫時序章亮起來的東西（見 prologueKey、renderTop）
    recap: undefined, // 設定頁「重看序章」的文字：undefined＝還沒問過伺服器，""＝沒有序章；同一次載入只問一次（loadRecap）
    recapOpen: false,
    howto: undefined, // 設定抽屜「玩法說明」上一次要到的那一頁（伺服器寫好的 HTML）：undefined＝還沒要到；每次攤開都再問（loadHowto）
    howtoOpen: false,
    howtoFailed: false, // 最近一次要玩法說明沒要到：卡上寫一句、給「再試一次」
    howtoSeq: 0, // 玩法說明的第幾次請求：晚回來的舊請求（後面又問了一次、或已經登出）不蓋掉新的
    ordersSeen: false, // 入伍段第一步的 view_orders 送過了嗎（軍令卡真的在畫面上才送，見 watchOrders）；登入、登出清掉
    ordersObs: null, // 盯著軍令卡的 IntersectionObserver（整頁重畫就換一個）
    ordersTimer: null, // 軍令卡進畫面之後的計時（ORDERS_SEEN_MS）；離開畫面就取消
    ordersVisible: false, // 觀察者最後一次說的：軍令卡（扣掉頂上與底下兩條固定的）至少一半在畫面上嗎
    ordersRetried: false, // 送不出去、已經補過一次重試了嗎（不連著試）
    stamOpen: false, // 狀態列體力條點開的說明攤開著嗎（explain-1）；再點一次收起
    frontsOpen: false, // 江湖頁戰況圖卡點開的說明攤開著嗎（explain-2）；再點一次收起
    pushLive: false, // 伺服器推送連著嗎（見「伺服器推送」那一段）：連著時平常 60 秒才輪詢，沒連就每 10 秒
  };

  const $app = document.getElementById("app");
  const $toast = document.getElementById("toast");

  // ── 工具 ──
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pct = (a, b) => (b > 0 ? Math.max(0, Math.min(100, (a / b) * 100)) : 0);

  // 序章（新手引導計畫一）：伺服器送 m.prologue = {reveal, glow, skip}；不在序章是 null，畫面照平常畫。
  // shown(key)：這個元件亮了沒（reveal 有它、或 "all" 全亮）。glow 列的鈕加 .glow，新亮起來的加 .lit（見 applyGlow）。
  // prologueKey：亮起來的東西變了沒——變了就整頁重畫（分頁列、狀態列只在整頁重畫時才換，見 renderTop）
  const pro = () => (S.main && S.main.prologue) || null;
  const shown = (key) => { const p = pro(); return !p || p.reveal.includes("all") || p.reveal.includes(key); };
  const prologueKey = () => { const p = pro(); return p ? p.reveal.join(",") : ""; };
  // 本季天數：整數不帶小數點（14.0 → 14），不是整數照原樣（14.5）
  const dayCount = (n) => String(Number(n));
  // 第一季的季曆（計畫 T2）：狀態列寫「第 3 週・週二 21:40」，旁邊是下一件大事的倒數（現實時間）。
  // 兩種時間的寫法固定（FB-062）：季曆時刻一律「第 N 週・週X HH:MM」（伺服器寫好的 calendar.text 與 next_event.at，同一個寫法，
  // 畫面不自己拼），倒數一律標「現實」（季曆跑得比現實快，不標玩家會算不出來）
  const countdown = (sec) => {
    const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60);
    if (sec < 60) return "就在眼前";
    return h > 0 ? `現實約 ${h} 小時 ${m} 分後` : `現實約 ${m} 分後`;
  };
  // 江湖頁畫的東西有沒有變：狀態列（時鐘、季曆每次輪詢都在走）另外重畫，不讓「剛剛」一直重播浮現
  const pageKey = (m) => JSON.stringify({ ...m, status: null });
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
    let res;
    try {
      res = await fetch(path, opts);
    } catch (e) {
      setOffline(true);
      throw e;
    }
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
    S.here = null; // 「此地還能做」摺疊的開合與自動打開過的記錄也重來（FB-087）
    S.hereAuto = {};
    S.moveMode = "walk"; // 登入、重新登入、建角的畫面都是伺服器照步行排的（_entry 不看走法），切換鈕跟著回到步行
    if (data.stage === "game") {
      S.stage = "game";
      setMain(data.main);
      closeEvents(); // 重新連：現在這個登入的連線（上一個帳號的、登入失效前的，不能留著）
      connectEvents(); // main.push 是 true 才真的連（預設關：不開 EventSource）
    } else {
      S.stage = data.stage === "create" ? "create" : "gate";
      closeEvents();
    }
    render();
  }

  function setMain(main) {
    if (main.event_free_text == null) S.answering = false; // 事件過去了，輸入框跟著收起
    if (!(main.options || []).some((o) => o.id === SAY_OPTION)) S.saying = false; // 交談結束了，「自己說」的輸入框跟著收起
    if (S.sensing && !(main.options || []).some((o) => o.id === SENSE_DRAW)) closeSense(); // 感悟狀態過去了（悟成、作廢），畫布跟著收起
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
    S.main = main;
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
    if (S.stage !== "game" || (!S.sheet && !S.peer)) closeAsk(); // 確認框疊在設定抽屜或玩家卡上；抽屜關了、被登出就一起收掉
    if (S.stage === "gate") return renderGate();
    if (S.stage === "create") return renderCreate();
    if (S.stage !== "game") return;
    if (S.tab !== "jianghu" && !shown(`tab:${S.tab}`)) S.tab = "jianghu"; // 序章重來（換季）：藏起來的分頁不能還停在那一頁
    S.prologueKey = prologueKey();
    const top = topHtml();
    $app.innerHTML = `
      <div class="shell">
        <header class="top" id="top"${top ? "" : " hidden"}>${top}</header>
        <main class="page" id="page"></main>
      </div>
      ${tabsHtml()}
      ${S.sheet ? sheetHtml() : S.peer ? peerHtml() : ""}
      ${S.book ? bookHtml() : ""}`;
    renderPage();
    if (S.sheet) document.querySelector(".sheet-bg")?.addEventListener("wheel", sheetWheel, { passive: false }); // 暗處是每次新畫的，掛一次
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
    const top = document.querySelector(".sheet")?.scrollTop;
    render();
    const sheet = document.querySelector(".sheet");
    if (sheet && top != null) sheet.scrollTop = top;
  }

  // 底部分頁列：序章裡只畫亮起來的分頁（格數跟著變，不是固定五格），一個都沒有就整列不畫。data-glow 給序章指路（applyGlow）
  function tabsHtml() {
    const list = TABS.filter((t) => shown(`tab:${t.id}`));
    if (!list.length) return "";
    return `<nav class="tabs"><div class="tabs-inner" style="grid-template-columns:repeat(${list.length}, 1fr)">${list.map((t) => `
        <button class="tab ${S.tab === t.id ? "on" : ""}" data-act="tab" data-tab="${t.id}" data-glow="tab:${t.id}">
          <span class="ico">${t.ico}</span>${t.name}${t.id === "news" && S.unseen && S.tab !== "news" ? '<i class="dot"></i>' : ""}
        </button>`).join("")}</div></nav>`;
  }

  function renderTop() {
    if (S.prologueKey !== prologueKey()) { render(); return; } // 序章亮起了新的東西：分頁列與狀態列要一起換（render 會畫好發光）
    const el = document.getElementById("top");
    if (!el) return;
    const before = el.offsetHeight; // 狀態列重畫前多高：變了就重量第一屏（fitTopMoved，FB-123）
    const html = topHtml();
    el.innerHTML = html;
    el.hidden = !html;
    applyGlow();
    fitTopMoved(before);
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
    const subs = [
      s.calendar && s.next_event ? `下一件：${esc(s.next_event.title)}${s.next_event.at ? `・${esc(s.next_event.at)}` : ""}（${countdown(s.next_event.in_seconds)}）` : "",
      s.busy_hours != null ? `🧘 閉關中，現實約 ${s.busy_hours} 小時後出關` : "",
      s.journey != null ? `🐎 ${esc(s.journey)}` : "",
    ].filter(Boolean).map((t) => `<div class="where sub">${t}</div>`).join("");
    const where = inPro ? `📍 ${esc(s.location)}` : `📍 ${esc(s.location)}　${s.calendar
      ? esc(s.calendar.text)
      : `第 ${s.day} 天 ${esc(s.clock)}<small>／共 ${dayCount(s.season_days)} 天</small>`}${s.resting != null ? "　🧘 打坐中" : ""}`;
    const vitals = [
      // 回體丹（企劃者 2026-10-07 內測贈送）：有丹時體力條右端多一顆「丹 N」，按了吃一顆；體力滿了是灰的。序章裡伺服器不給 pills。
      // 測試期間一鍵補滿打開時（pills.refill）：沒有丹也有這顆鈕、字改成「補滿」，按了直接補滿、不花丹
      // 點體力條（丹／補滿那顆鈕以外的地方）在底下攤開體力怎麼回（explain-1；s.stamina_help 是伺服器照設定寫好的幾行）
      shown("stamina") ? `<div class="bar stam" title="體力" data-glow="stamina"${s.stamina_help && s.stamina_help.length
        ? ` data-act="stam-help" role="button" tabindex="0" aria-expanded="${!!S.stamOpen}" aria-controls="stam-help"` : ""}><i style="width:${pct(s.stamina, s.stamina_max)}%"></i><span>體力 ${s.stamina}/${s.stamina_max}</span>${s.pills
        ? `<button class="pill-btn" data-act="pill" ${s.pills.full ? "disabled" : ""} aria-label="${s.pills.refill
          // 測試期間一鍵補滿（伺服器給 pills.refill＝鈕上的字，沒有丹也給）：鈕寫「補滿」不寫丹數；關著時沒有這個鍵，照 joy 的寫法
          ? `${esc(s.pills.refill)}體力（測試期間免費，不花${esc(s.pills.name)}）`
          : `服下${esc(s.pills.name)}（剩 ${s.pills.count} 顆，回 ${s.pills.restore} 點體力）`}">${s.pills.refill ? esc(s.pills.refill) : `丹${s.pills.count}`}</button>` : ""}</div>` : "",
      shown("hp") ? `<div class="bar hp" title="氣血" data-glow="hp"><i style="width:${pct(s.hp, s.hp_max)}%"></i>${s.injury >= 1
        // 內傷（FB-049）：斜紋是上限裡被內傷佔掉、回不來的那一截（寬＝內傷÷上限，回滿時紅條剛好接到它）；
        // 「傷 N」靠右另寫在斜紋那一頭，不再接在「氣血 N/M」後面跨過紅條的交界
        ? `<b style="width:${pct(s.injury, s.hp_max)}%"></b>` : ""}<span>氣血 ${s.hp}/${s.hp_max}</span>${s.injury >= 1
        ? `<span class="inj">傷 ${s.injury}</span>` : ""}</div>` : "",
      shown("silver") ? `<div class="num" data-glow="silver"><em>銀</em>${s.silver}</div>` : "",
      shown("xinde") ? `<div class="num" data-glow="xinde"><em>心得</em>${s.xinde}</div>` : "",
    ].join("");
    // 點名號展開屬性：序章裡「屬性」那一步才點得開（data-glow="stats" 指路）；沒亮就不是按鈕
    const who = shown("stats")
      ? `<div class="who" data-act="toggle-more" role="button" tabindex="0" aria-expanded="${S.showMore}" data-glow="stats">`
      : '<div class="who static">';
    return `
      <div class="top-row">
        ${who}
          ${whoNameHtml(s)}
          <div class="where">${where}</div>
        </div>
        <button class="icon-btn" data-act="sheet" aria-label="設定">⚙</button>
      </div>
      ${inPro ? "" : subs}
      ${vitals ? `<div class="vitals">${vitals}</div>` : ""}
      ${S.stamOpen && shown("stamina") && s.stamina_help && s.stamina_help.length
        ? `<div class="more-stats stam-help" id="stam-help">${s.stamina_help.map((t) => `<p>${esc(t)}</p>`).join("")}</div>` : ""}
      ${S.showMore ? `<div class="more-stats">
        ${s.minor.map(([k, v]) => `${esc(k)} ${v}`).join("　")}　｜　${s.attrs.map(([k, v]) => `${esc(k)} ${v}`).join("　")}
        ${s.stat_points ? `<div class="pts-label"><b class="pts">可配 ${s.stat_points} 點</b></div><div class="row alloc">${s.attrs.map(([k, v, key]) => `<button class="btn small" data-act="allocate" data-stat="${esc(key)}" data-glow="allocate" ${v >= s.stat_cap ? "disabled" : ""}>＋${esc(k)}</button>`).join("")}</div>${statUsesHtml(s)}` : ""}
        ${team ? `<br>${team}` : ""}
        ${s.stances && shown("stances") ? stancesHtml(s.stances, s.stance_notes) : ""}
      </div>` : ""}
      ${inPro ? "" : hintHtml(s)}`;
  }

  // 狀態列的名號那一塊（FB-071）。收起來是一行：名號、頭銜（小字，放不下加「…」）、可配 N 點、▾——「可配」放在會省略的 <span>
  // 外面（flex: none），長長的「門派・陣營」只擠頭銜、擠不掉它。展開之後各有各的位置：名號獨佔第一行（後面是 ▴），頭銜是第二行，
  // 每一段（門派、陣營、頭銜、匿名、第 N 級）各自一個不折行的 <span>（class 叫 who-seg，不能叫 seg：那是全站的分段選單），
  // 只會在段與段之間換行，不會把一個詞從中間折斷；
  // 「可配 N 點」改放在＋鈕上面當那一排的標題（見 topHtml 的 pts-label）
  function whoNameHtml(s) {
    if (!S.showMore) return `<div class="who-name"><span>${esc(s.name)}<small>${esc(s.affiliation)}${s.anonymous ? "・匿名" : ""}・第${s.level}級</small></span>${s.stat_points ? `<b class="pts">可配 ${s.stat_points} 點</b>` : ""}<i class="more-ico" aria-hidden="true">▾</i></div>`;
    const segs = [...s.affiliation.split("・"), ...(s.anonymous ? ["匿名"] : []), `第${s.level}級`].filter(Boolean);
    return `<div class="who-name"><span>${esc(s.name)}</span><i class="more-ico" aria-hidden="true">▴</i></div>
          <div class="who-title">${segs.map((t) => `<span class="who-seg">${esc(t)}</span>`).join("・")}</div>${rangerHtml(s.ranger)}`;
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
  function statUsesHtml(s) {
    if (!s.stat_uses) return "";
    const items = s.stat_uses.map(([k, use]) => `<span>${esc(k)}：${esc(use)}</span>`);
    if (s.stat_uses_note) items.push(`<span>${esc(s.stat_uses_note)}</span>`);
    return `<div class="stat-uses">${items.join("")}</div>`;
  }

  // 💡 心得提示：兩行長，在路上又有路程那一行時，會把路上最底下的「走法」擠到分頁列底下（FB-060）。
  // 所以在路上收成一行（放不下的加「…」），點了展開看全文；下了路就清掉、照舊整段顯示
  // 不在路上、眼前是事件、有所感、對話、決戰這類一次一組的選項時（不是平常閒著的行動列）不畫（explain-2）：心得一付得起就提示之後，
  // 新人幾乎一直有這一行，會把事件的最後一個選項、有所感的最後一個做法擠到分頁列底下（同 FB-076 的對話框）；了結了就回來。
  // 打坐（只剩「起身」）與閉關（只剩「提前出關」）照畫（審查 I2）：最長的空檔，修練、煉製照樣做得了，也沒有選項會被擠下去。
  // 師父「碰到才說」的框（伺服器標 guide.hint）在畫面上時也不畫（審查 M6）：一次只給一句指點——兩樣一起，打完一場之後行動列會被推到
  // 分頁列底下；框是比較專門的那一句，提示等它，按了「知道了」（或框不在了）就回來。在路上照舊（框排在選項底下，提示收成一行）
  const WAITING = new Set(["act:stand", "act:break"]);
  const waitingMenu = (m) => m.options.length > 0 && m.options.every((o) => WAITING.has(o.id));
  // 江湖頁第一屏放不下行動列時（FB-107 的 fitFirstScreen，S.hintTight）不在路上也收成一行，點了看全文；別的分頁照舊整段
  function hintHtml(s) {
    const tight = s.journey == null && S.hintTight && S.tab === "jianghu";
    // 不在路上、也沒收成一行：清掉「點開了」。收成一行的時候去別的分頁看一眼（那裡照整段畫），回來照舊攤開（審查 M9）
    if (s.journey == null && !S.hintTight) S.hintOpen = false;
    if (!s.hint) return "";
    if (s.journey == null && S.main && S.main.guide && S.main.guide.hint) return "";
    if (s.journey == null && S.main && S.main.options && !idleMenu(S.main) && !waitingMenu(S.main)) return "";
    if (s.journey == null && !tight) return `<div class="more-stats"><span class="hint">${esc(s.hint)}</span></div>`;
    return `<div class="more-stats"><button class="hint road-hint${S.hintOpen ? "" : " clamp"}" data-act="hint-more" aria-expanded="${S.hintOpen}">${esc(s.hint)}</button></div>`;
  }

  // 目前對話框的樣子（整個框的內容；沒有框是 "null"）：修練、煉製頁只在 menxia 的欄位變了才重畫，輪詢才排進來的提示
  // （大事揭曉、決戰集結、抵達……伺服器在同步時就記成說過了）會畫不出來——頁面畫的框跟現在的框不同就重畫（新手引導計畫三，T2 審查 I-1）
  const guideSig = () => JSON.stringify((S.main && S.main.guide) || null);

  function renderPage() {
    const page = document.getElementById("page");
    if (!page) return;
    const fn = { jianghu: pageJianghu, practice: pagePractice, craft: pageCraft, map: pageMap, news: pageNews }[S.tab];
    page.innerHTML = fn();
    S.guideDrawn = guideSig(); // 這一頁畫的是哪個對話框：修練、煉製頁的輪詢拿它比，框換了才重畫（見 refreshPage）
    afterPage();
    applyGlow();
  }

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
    const p = pro();
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
    guideCue();
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
    const target = (pro() || guideGlow().length) && document.querySelector("#page .glow");
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

  // ── 第一屏放不下時一步一步收（FB-107）──
  // 企劃者：375×812 上「剛剛」、場景與整排行動都在第一屏（按完不用捲就看得到結果）。打完一場又跳出師父「碰到才說」的框、💡 兩行、
  // 決戰集結（場景多一段戰場、「此地還有」、結伴那幾行）時，行動列會掉到分頁列底下。框照企劃者 10/5 的決定留在行動列上面、話不切；
  // 這裡畫好之後量一次：行動列（事件、有所感這種一組選項時是最後一顆）的下緣離分頁列不到 FIT_MARGIN，就照 FIT_STEPS 的順序一步一步收，
  // 收到放得下就停——放得下的畫面一點都不動。先收不少任何字的（間距、框的行高），再收 💡 與看一眼就夠的（對手的描述、第一回合、
  // 剛剛的後半、決戰時所在地的描述、集結那一句的後半），每一樣都點得開、看得到全文；得失與結果那幾行（數字）、框裡的話都不收。
  // 在路上（另有自己的排法，FB-055）、序章裡不收。收到最後還放不下（集結又有框的時候：場景裡「此地還有」、結伴那幾行不歸這裡收）
  // 就是放不下，不再藏別的
  // 量的是畫面本身（字體、寬度、狀態列幾行都算進去），所以手機高一點、字少一點就少收或不收。重畫、轉向、拉視窗之後重量（先全部還原）
  const FIT_MARGIN = 16;
  const fitPage = () => document.getElementById("page");
  // 要放進第一屏的那一塊：平常閒著是行動列；事件、有所感、對話、決戰這種一組選項時是選單最後一顆
  const fitTarget = () => document.querySelector("#page > .act-bar") || document.querySelector("#page > .options > :last-child");
  function fitOver() {
    const target = fitTarget(), tabs = document.querySelector(".tabs");
    if (!target || !tabs) return 0;
    return target.getBoundingClientRect().bottom + (window.scrollY || 0) - (fitTabsTop(tabs) - FIT_MARGIN);
  }
  // 分頁列頂的基準（FB-123）：分頁列固定在畫面底下，手機捲動時網址列收起、跑出來，它跟著上下移幾十 px。集結時倒數每一輪都整頁重畫、
  // 重量，拿當下的位置量的話，網址列每換一次狀態就多收或少收一步、畫面跟著跳。同一個寬度記住量到過最小的那個（網址列跑出來的時候：
  // 一開頁面、捲回頂端都是），寬度變了（轉向、拉視窗）重記。輸入框有焦點時不記：舊的 Android 開鍵盤會把視窗縮小，記下來的話
  // 收起鍵盤之後整頁還收到底
  function fitTabsTop(tabs) {
    const top = tabs.getBoundingClientRect().top, width = window.innerWidth;
    const typing = /^(INPUT|TEXTAREA)$/.test((document.activeElement && document.activeElement.tagName) || "");
    if (!S.fitBase || S.fitBase.width !== width) {
      if (typing) return top;
      S.fitBase = { width, top };
    } else if (!typing) {
      S.fitBase.top = Math.min(S.fitBase.top, top);
    }
    return S.fitBase.top;
  }
  const FIT_STEPS = [
    // 1. 間距：卡與卡之間、卡的內距收緊一點（style.css 的 .page.fit-space），一個字都不少
    { key: "space", run: () => {
      fitPage().classList.add("fit-space");
      const card = document.querySelector("#page > .battle-card");
      if (card) card.classList.add("fit-space"); // 戰鬥卡片的內距寫在 .battle-card 底下（style.css 的 .battle-card.fit-space）
      return true;
    } },
    // 2. 師父的框收緊：「知道了」不再撐高標題那一行、話的行高小一點；框裡的話一個字都不切（設計 6.2）
    { key: "box", run: () => {
      const box = document.querySelector("#page > .card.guide");
      if (box) box.classList.add("fit-box");
      return !!box;
    } },
    // 3. 💡（狀態列底下那一行心得提示）收成一行、放不下加「…」，點了看全文（在路上那一種，FB-060）。狀態列是另外畫的（renderTop）：
    //    記在 S.hintTight，輪詢重畫狀態列時照它畫；玩家點開了（S.hintOpen）就不收
    { key: "hint", run: () => {
      if (S.hintTight || !document.querySelector("#top .more-stats .hint")) return false; // 已經收過、玩家點開了：不再收
      S.hintTight = true;
      renderTop();
      return true;
    } },
    // 4. 戰鬥卡片底下的補充（對手的描述「（偷網賊：……）」這種）每一行收成一行、放不下加「…」，點了看全文（同伴聽來的那一句的做法，FB-074）。
    //    點開記在 S.linesOpen（這一場的卡片），跟聽來的那一句（S.hearOpen）各記各的（審查 M5）；數字收不進一行的那一行不收
    { key: "lines", run: () => {
      if (S.linesOpen != null && S.linesOpen === S.main.card_id) return false; // 玩家點開過：不收回去
      let any = false;
      document.querySelectorAll(".battle-card .tx-extra .tx-line:not(.tx-hearsay)").forEach((el) => {
        el.classList.add("tx-tight");
        if (!fitDigitsShown(el)) { el.classList.remove("tx-tight"); return; }
        el.setAttribute("data-act", "line-more");
        el.setAttribute("role", "button");
        el.setAttribute("tabindex", "0");
        el.setAttribute("aria-expanded", "false");
        any = true;
      });
      return any;
    } },
    // 5. 戰鬥卡片的第一回合也收進「展開過程」（那一行與按鈕照舊在；得失照舊在）
    { key: "rounds", run: () => {
      const list = document.querySelector(".battle-card ul.rounds:not(.open), .battle-card p.rounds-tale:not(.open)");
      if (list) list.classList.add("fit-fold");
      return !!list;
    } },
    // 6. 「剛剛」（不是戰鬥卡片的那種）收著時只露三行（同在路上，FB-060），「展開全文」照舊
    { key: "now", run: () => {
      const now = document.querySelector("#page > .now:not(.open)");
      const body = now && now.querySelector(".tx-now");
      if (!body) return false;
      now.dataset.fitWas = now.classList.contains("fits") ? "fits" : "clamp";
      now.classList.replace("fits", "clamp");
      now.classList.add("fit-short");
      if (body.scrollHeight <= body.clientHeight + 1) now.classList.replace("clamp", "fits"); // 三行就放得下：不要淡出與「展開全文」
      return true;
    } },
    // 7. 決戰集結、只能觀戰時，場景卡在戰場底下接著所在地（分隔線之後）：閒著時那是地點的描述，每段收成一行、點了攤開（S.ownOpen）。
    //    有事件、有所感、對話時分隔線之後是那件事本身（joy 的字），不收
    { key: "own", run: () => {
      const scene = document.querySelector("#page > .card.scene:not(.road)");
      if (!scene || !scene.querySelector(":scope > hr") || !idleMenu(S.main) || S.ownOpen === fitOwnKey()) return false;
      scene.classList.add("fit-own");
      return fitClip(scene.querySelectorAll(":scope > hr ~ p"));
    } },
    // 8. 戰場名字底下、分隔線之前那幾句（集結、開打的消息，開頭是「集結中，還剩現實 N 分 N 秒」）收成一行，點了攤開（同上）。
    //    加入的鈕在名字那一行（FB-105 的 musterScene）時從那一行底下算起，後半（「選擇陣營加入…」）名字旁那一小句已經說了；
    //    沒有鈕（人不在那個大區、加入過了、觀戰）時從名字底下算起——別的大區集結時那一句「…這場決戰在南陽，人要到了那裡…」兩行高，
    //    以前沒有鈕就從來不收（走查）。數字收不進一行的那一句不收（fitClip）
    { key: "muster", run: () => {
      const scene = document.querySelector("#page > .card.scene:not(.road)");
      if (!scene || !scene.querySelector(":scope > hr") || S.ownOpen === fitOwnKey()) return false;
      if (scene.querySelector(":scope > .battle-shut")) return false; // 只能觀戰的人自己攤開的開打中的戰場（FB-120）：不收
      const head = scene.querySelector(":scope > .muster-head") || scene.querySelector(":scope > p");
      const lines = [];
      for (let p = head && head.nextElementSibling; p && p.tagName !== "HR"; p = p.nextElementSibling) if (p.tagName === "P") lines.push(p);
      scene.classList.add("fit-muster");
      return fitClip(lines);
    } },
    // 9. 一組選項（事件、有所感的做法）時，鈕與鈕之間收緊、鈕矮一點（44px，觸控照樣按得到）
    { key: "options", run: () => {
      const menu = document.querySelector("#page > .options");
      if (menu) menu.classList.add("fit-tight");
      return !!menu;
    } },
  ];
  // 還原（重量之前）：只拿掉 fitFirstScreen 自己加的東西
  function fitReset() {
    const page = fitPage();
    if (!page) return;
    page.classList.remove("fit-space");
    page.querySelectorAll(".fit-space").forEach((el) => el.classList.remove("fit-space"));
    page.querySelectorAll(".fit-box").forEach((el) => el.classList.remove("fit-box"));
    if (S.hintTight && !S.hintOpen) { S.hintTight = false; renderTop(); } // 玩家點開了 💡：留著（展開的就是整段）
    page.querySelectorAll(".tx-tight").forEach((el) => {
      el.classList.remove("tx-tight");
      ["data-act", "role", "tabindex", "aria-expanded"].forEach((a) => el.removeAttribute(a));
    });
    page.querySelectorAll(".fit-fold").forEach((el) => el.classList.remove("fit-fold"));
    page.querySelectorAll(".now.fit-short").forEach((el) => {
      el.classList.remove("fit-short");
      if (el.dataset.fitWas && !el.classList.contains("open")) el.classList.replace(el.classList.contains("fits") ? "fits" : "clamp", el.dataset.fitWas);
      delete el.dataset.fitWas;
    });
    page.querySelectorAll(".fit-own, .fit-muster").forEach((el) => el.classList.remove("fit-own", "fit-muster"));
    fitUnclip(page);
    page.querySelectorAll(".fit-tight").forEach((el) => el.classList.remove("fit-tight"));
  }
  // 場景卡裡收成一行的段落（第 7、8 步）：一行、放不下加「…」（style.css 的 p.fit-clip），點了整張場景卡攤開（ownOpen）。
  // 收了之後數字（倒數、戰局）會藏到「…」後面的那一段不收
  function fitClip(paras) {
    let any = false;
    paras.forEach((p) => {
      p.classList.add("fit-clip");
      if (!fitDigitsShown(p)) { p.classList.remove("fit-clip"); return; }
      p.setAttribute("data-act", "own-more");
      p.setAttribute("role", "button");
      p.setAttribute("tabindex", "0");
      p.setAttribute("aria-expanded", "false");
      any = true;
    });
    return any;
  }
  // 收成一行之後，裡面的數字還整個看得到嗎：最後一個數字的右緣要在那一行右緣往內 1em 以內（「…」佔的位置）。
  // 收成一行的字照樣排在框外面（只是畫不出來），所以量得到它在哪。量不了（瀏覽器沒有 Range）就當看得到
  function fitDigitsShown(el) {
    if (!document.createRange || !document.createTreeWalker) return true;
    const walk = document.createTreeWalker(el, 4); // NodeFilter.SHOW_TEXT
    let node = null, at = -1;
    for (let n = walk.nextNode(); n; n = walk.nextNode()) {
      const i = n.data.search(/[0-9０-９][^0-9０-９]*$/);
      if (i >= 0) { node = n; at = i; }
    }
    if (!node) return true;
    const range = document.createRange();
    range.setStart(node, at);
    range.setEnd(node, at + 1);
    const em = parseFloat(getComputedStyle(el).fontSize) || 16;
    return range.getBoundingClientRect().right <= el.getBoundingClientRect().right - em;
  }
  // 攤開過的是哪一處的哪一場（審查 I2）：所在地＋場景第一段（戰場名字），數字拿掉。集結、開打時場景裡的倒數與回合每一次輪詢都在變，
  // 拿整個場景當記號的話，玩家剛攤開的那幾段下一輪就又收回去
  function fitOwnKey() {
    const m = S.main || {};
    const first = String(m.scene || "").split("</p>")[0].replace(/[0-9０-９]+/g, "#");
    return `${(m.status && m.status.location) || ""}|${first}`;
  }
  function fitUnclip(root) {
    root.querySelectorAll(".fit-clip").forEach((p) => {
      p.classList.remove("fit-clip");
      ["data-act", "role", "tabindex", "aria-expanded"].forEach((a) => p.removeAttribute(a));
    });
  }
  // 收了哪幾步（記在 S.fitted，給測試與除錯看）
  function fitFirstScreen() {
    S.fitted = [];
    S.fitWidth = window.innerWidth; // 這一次量的是哪個寬度（fitOnResize 看它）
    if (S.stage !== "game" || S.tab !== "jianghu" || !S.main || S.main.on_road || pro() || !fitPage()) return;
    S.fitting = true; // 收 💡、還原時會重畫狀態列：那不是「狀態列變了」（fitTopMoved）
    try {
      fitReset();
      for (const step of FIT_STEPS) {
        if (fitOver() <= 0) break;
        if (step.run()) S.fitted.push(step.key);
      }
    } finally {
      S.fitting = false;
    }
  }
  // 狀態列變高變矮（FB-123）：點名號展開配點、收起，💡 冒出來或變兩行，攤開體力說明——行動列跟著上下移，重量一次（從還原開始：
  // 收起名號之後收著的那幾樣攤回來）。renderTop 把重畫之前的高度交過來；高度沒變（只是數字換了）不量。fitFirstScreen 自己收 💡、
  // 還原 💡 時重畫狀態列不算（S.fitting），不會一直重量
  function fitTopMoved(before) {
    const top = document.getElementById("top");
    if (!top || S.fitting || top.offsetHeight === before) return;
    fitFirstScreen();
  }
  // 視窗大小變了（檔案最後的 resize 監聽）：寬度變了（轉向、拉視窗）才重量。手機捲動時網址列收起、跑出來只改高度，也會觸發 resize——
  // 那時重量的話，第一屏外的那幾段會邊捲邊收、邊攤開（審查 M6）。平常的重畫（afterPage）照樣每次都量
  function fitOnResize() {
    if (window.innerWidth === S.fitWidth) return;
    fitFirstScreen();
  }
  // 戰鬥卡片底下收成一行的補充（第 4 步）：點了原地攤開、再點收起，不重畫；攤開記在 S.linesOpen（這一場的卡片），重畫時不再收
  function lineToggle(el) {
    const open = !el.classList.contains("open");
    S.linesOpen = open ? S.main.card_id : null;
    el.classList.toggle("open", open);
    el.setAttribute("aria-expanded", String(open));
  }
  // 決戰時收成一行的那幾段（所在地、集結那一句）：點了攤開（原地，不重畫）；記住這一處的這一場攤開過（fitOwnKey），重畫時不再收
  function ownOpen() {
    S.ownOpen = fitOwnKey();
    const scene = document.querySelector("#page > .card.scene:not(.road)");
    if (!scene) return;
    scene.classList.remove("fit-own", "fit-muster");
    fitUnclip(scene);
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
  }

  // ── 登入與取名號 ──
  function renderGate() {
    const reg = S.gateMode === "register";
    $app.innerHTML = `
      <div class="gate">
        <div class="brand"><div class="seal">勢</div><h1>天下大勢</h1><p>亂世江湖，從潁川城門口開始</p></div>
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
      </div>`;
  }

  function renderCreate() {
    $app.innerHTML = `
      <div class="gate">
        <div class="brand"><div class="seal">勢</div><h1>天下大勢</h1><p>這個帳號還沒有角色</p></div>
        <form id="create-form" class="card">
          <label class="field"><span>取一個名號，踏入江湖</span><input class="input" name="name" maxlength="16" placeholder="例如：沈青衫" required></label>
          <p class="form-msg" role="alert"></p>
          <button class="btn primary" type="submit">建立角色</button>
        </form>
        <button class="linkish" data-act="logout">換一個帳號</button>
      </div>`;
  }

  // ── 江湖 ──
  const nowMore = (open) => (open ? "收起 ▴" : "展開全文 ▾");
  const roundsMore = (open) => (open ? "收起過程 ▴" : "展開過程 ▾");

  // 戰鬥卡片的「過程」（計畫三 Task 1、G6 暫定）：「剛剛」那張只露第一回合，按「展開過程」才攤開（其餘回合一回合一回合浮現，
  // style.css 的 .rounds），第一屏要留給剛剛、場景與整排行動（企劃者 2026-10-04）；按鈕放在「過程」那一行的右邊，不多佔一行。
  // 戰報頁照樣整段列出，不經過這裡。認的是伺服器把「**過程**」轉成的那段 HTML（server.md）；認不出來就整段照原樣
  // （tests/test_server.py 擋住兩邊對不上）。展開記在 S.roundsOpen（記的是那一場的流水號），換成新的一場就自動收回
  const ROUNDS_MARK = "<p><strong>過程</strong></p>\n<ul>";
  // 大場面模型寫的過程是一段話（battlelog._rounds_block 的「**過程**＋換行＋一段話」，最多 200 字）：同一顆「展開過程」，
  // 收著只露前兩行（style.css 的 .battle-card p.rounds-tale，PM 2026-10-05）
  const TALE_MARK = "<p><strong>過程</strong><br />\n";
  // 「看完整戰報 ›」放在「過程」那一行的中間（PM 2026-10-05，戰鬥卡片壓縮第二輪）：那一行中間本來就是空的，不再接在「結果／得失」
  // 句尾多撐一行。點擊範圍上下各多 8px、不撐高那一行（style.css 的 .rounds-head .report-link）
  const reportLink = (id) => `<button class="linkish report-link" data-act="report" data-id="${id}">看完整戰報 ›</button>`;
  // 功效的演出句（計畫六 Task 4，引擎的 battlelog.trait_line）一律以「〔功效名〕」開頭：收著的卡片先把它們藏起來，第一回合照舊帶頭
  // （Task 4 審查 I-1：不然功效句頂掉第一回合的數字行，多佔一行、也藏了第一回合的數字）；展開之後照引擎寫的順序全部列出，戰報頁不經過這裡。
  // 認的是行首的〔（引擎擁有這段文字，tests/test_server.py 擋住兩邊對不上）；整段都是功效句（沒有回合）時不藏，免得收著的過程是空的
  const TRAIT_LEAD = "〔";
  function foldTraitItems(rest) {
    const end = rest.indexOf("</ul>");
    const list = end < 0 ? rest : rest.slice(0, end);
    const items = list.match(/<li>[\s\S]*?<\/li>/g) || [];
    if (!items.some((li) => !li.startsWith(`<li>${TRAIT_LEAD}`))) return rest;
    return list.split(`<li>${TRAIT_LEAD}`).join(`<li class="trait">${TRAIT_LEAD}`) + (end < 0 ? "" : rest.slice(end));
  }
  // 大場面的一段話：每一行以 <br /> 分開，功效句連同它後面的換行包進 <span class="trait">（收著時整個藏起來，兩行的截斷就看到模型的話）
  function foldTraitText(rest) {
    const end = rest.indexOf("</p>");
    const lines = (end < 0 ? rest : rest.slice(0, end)).split("<br />\n");
    if (lines.every((line) => line.startsWith(TRAIT_LEAD))) return rest;
    const last = lines.length - 1;
    const marked = lines.map((line, i) => {
      const text = i < last ? `${line}<br />\n` : line;
      return line.startsWith(TRAIT_LEAD) ? `<span class="trait">${text}</span>` : text;
    });
    return marked.join("") + (end < 0 ? "" : rest.slice(end));
  }
  function roundsFold(card, id) {
    const open = S.roundsOpen === id;
    const more = `<button class="linkish rounds-more" data-act="rounds-more" aria-expanded="${open}">${roundsMore(open)}</button>`;
    const head = `<p class="rounds-head"><strong>過程</strong>${id == null ? "" : reportLink(id)}${more}</p>\n`;
    let at = card.indexOf(ROUNDS_MARK);
    if (at >= 0) return card.slice(0, at) + head + `<ul class="rounds${open ? " open" : ""}">` + foldTraitItems(card.slice(at + ROUNDS_MARK.length));
    at = card.indexOf(TALE_MARK);
    if (at >= 0) return card.slice(0, at) + head + `<p class="rounds-tale${open ? " open" : ""}">` + foldTraitText(card.slice(at + TALE_MARK.length));
    return card;
  }

  // 沒有「過程」那一行的卡片（全服決戰、舊戰報）才把「看完整戰報 ›」接在卡片最後一段（「結果　…　得失　…」那一句）的句尾，
  // 不另佔一行（PM 2026-10-05，戰鬥卡片壓縮）；卡片最後不是 <p>（認不出來）時照舊放在卡片最後。
  // 伺服器的 Markdown 一律以 "</p>\n" 收尾，所以認最後一個 </p>
  function withReportLink(card, id) {
    if (id == null) return card;
    const end = card.lastIndexOf("</p>");
    return end >= 0 && !card.slice(end + 4).trim() ? `${card.slice(0, end)}${reportLink(id)}${card.slice(end)}` : card + reportLink(id);
  }
  // 「剛剛」的戰鬥卡片：有「過程」那一行（roundsFold 認得出來，卡片因此變了）連結就在那一行裡，沒有才接在最後一段的句尾
  function fightCard(card, id) {
    const folded = roundsFold(card, id);
    return folded !== card ? folded : withReportLink(card, id);
  }

  // 收著的「過程」第一回合最多兩行、而且不藏任何數字（PM 2026-10-05）：句子放得進兩行就照原樣；放不進就整句省略，只留數字
  // 「第1回合　你氣血 -13，對手氣勢 -10……」。數字就是 battlelog.round_lines 寫的那幾種結尾：「對手氣勢 -N」「你氣血 -N」，
  // 沒打中的「被對方架開」「被你閃開了」（照句子裡出現的先後）。認不出來（沒有「第N回合」、一個結尾也沒找到、扣掉認得的之後
  // 還剩任何數字）就回 null——呼叫端照原樣整句顯示，寧可多佔一行也不讓一個數字被藏起來。展開之後每一回合照舊整句列出
  const ROUND_BITS = /對手氣勢 -\d+|你氣血 -\d+|被對方架開|被你閃開了/g;
  function compactRound(text) {
    const line = String(text).trim();
    const head = /^第\d+回合/.exec(line);
    if (!head) return null;
    const rest = line.slice(head[0].length);
    const bits = rest.match(ROUND_BITS);
    if (!bits || /\d/.test(rest.replace(ROUND_BITS, ""))) return null;
    return `${head[0]}　${bits.join("，")}……`;
  }
  // 畫好之後量第一回合：高過兩行半（三行是三倍行高；兩行混著拉丁數字與漢字量出來會多一兩 px，不能算成三行）、又拼得出數字行，
  // 就把它換成數字行（.r-full 整句、.r-short 數字行，style.css 的 .tight 決定露哪個；展開時一律露整句）。
  // 每次都先拿掉 .tight 再量，轉向、拉視窗之後重量也一樣
  function fitFirstRound() {
    const list = document.querySelector(".battle-card ul.rounds");
    const first = list && list.querySelector(":scope > li:not(.trait)"); // 收著時露出的那一個：功效句藏起來，第一回合帶頭（foldTraitItems）
    if (!first) return;
    list.classList.remove("tight");
    let full = first.querySelector(":scope > .r-full");
    const lineHeight = parseFloat(getComputedStyle(first).lineHeight);
    if (!first.offsetHeight || !(lineHeight > 0) || first.offsetHeight <= 2.5 * lineHeight) return;
    const short = compactRound(full ? full.textContent : first.textContent);
    if (short == null) return;
    if (!full) {
      full = document.createElement("span");
      full.className = "r-full";
      full.append(...first.childNodes);
      const tail = document.createElement("span");
      tail.className = "r-short";
      first.append(full, tail);
    }
    first.querySelector(":scope > .r-short").textContent = short;
    list.classList.add("tight");
  }

  // 「剛剛」那一則拆成敘事與數值變化（氣血 -96、黃巾聲勢 -2…，journal.card_html 放在 .tx-now 最後）：
  // 收合只收敘事，數值變化排在收合範圍外面，收著也看得到（W6 review Minor 2）
  function splitChips(html) {
    const t = document.createElement("template");
    t.innerHTML = html;
    const chips = t.content.querySelector(".tx-now > .tx-chgs");
    if (chips) chips.remove();
    return [t.innerHTML, chips ? chips.outerHTML : ""];
  }

  // ── 太極火爐（煉製頁）──
  // 每次重畫都是新的 SVG，所以轉動用負的 animation-delay 接上時鐘，重畫不會讓圖案跳回原位
  const wpt = (r, deg) => { const a = (deg - 90) * Math.PI / 180; return [+(r * Math.cos(a)).toFixed(2), +(r * Math.sin(a)).toFixed(2)]; };
  const spinAt = (secs) => `animation-delay:-${((performance.now() / 1000) % secs).toFixed(2)}s`;
  // 煉製頁的太極火爐（企劃者 2026-10-04）。太極在爐裡慢慢轉，外圈是一圈火舌；左右兩格放進去的是一門武學與一個意境
  // （或兩門武學，或兩個意境），點有東西的那一格拿出來，點爐身開爐。開爐後等結果的這段時間整座爐子晃動（見 forge()）。
  // slots 兩格各是 {name, sub, rank}（名字、第二行小字、品階 1~3）或沒放（null）
  function furnaceHub(slots, ready) {
    const r = 54;
    const flames = Array.from({ length: 16 }, (_, k) => {
      const a = k * 22.5, [x0, y0] = wpt(r + 3, a - 7), [x1, y1] = wpt(r + 10, a), [x2, y2] = wpt(r + 3, a + 7);
      return `<path d="M${x0},${y0} Q${x1},${y1} ${x2},${y2}" style="animation-delay:-${(k % 4) * 0.23}s"/>`;
    }).join("");
    const slot = (m, i) => {
      const x = i ? 26 : -26;
      // 格子只有 46 寬：名字超過四個字（新取的武學名可到六個字）就把字距壓進格子裡，不然會溢出格外蓋到另一格
      const fit = m && [...m.name].length > 4 ? ' textLength="42" lengthAdjust="spacingAndGlyphs"' : "";
      return m
        ? `<g class="w-slot full r${m.rank}" data-act="unslot" data-i="${i}" role="button" aria-label="拿出${esc(m.name)}">
            <rect x="${x - 23}" y="-14" width="46" height="28" rx="7"/><text x="${x}" y="-3" class="w-slot-name"${fit}>${esc(m.name)}</text><text x="${x}" y="8" class="w-slot-sub">${esc(m.sub)}</text></g>`
        : `<g class="w-slot"><rect x="${x - 23}" y="-14" width="46" height="28" rx="7"/><text x="${x}" y="0" class="w-slot-sub">放入</text></g>`;
    };
    return `<g class="w-hub w-furnace${ready ? " ready" : ""}" data-act="forge-hub" role="button" aria-label="太極火爐，開爐">
      <g class="w-shake">
        <g class="w-flames${ready ? " hot" : ""}">${flames}</g>
        <circle r="${r + 3}" class="w-hub-rim"/>
        <g class="w-spin w-taichi${ready ? " hot" : ""}" style="${spinAt(ready ? 3 : 28)}">
          <circle r="${r}" class="w-yang"/>
          <path d="M0,${-r} A${r},${r} 0 0 1 0,${r} A${r / 2},${r / 2} 0 0 1 0,0 A${r / 2},${r / 2} 0 0 0 0,${-r} Z" class="w-yin"/>
          <circle cy="${-r / 2}" r="${r / 7}" class="w-yang"/><circle cy="${r / 2}" r="${r / 7}" class="w-yin"/>
        </g>
        ${slot(slots[0], 0)}${slot(slots[1], 1)}
        <text y="${r - 12}" class="w-furnace-lab">${ready ? "點爐開火" : "太極火爐"}</text>
      </g></g>`;
  }
  // 煉製頁的太極火爐自己一張圖：外面不圍東西，挑武學與意境在下面的清單
  function furnaceSvg(slots, ready) {
    return `<div class="furnace-wrap"><svg class="wheel furnace" viewBox="-74 -74 148 148" role="group" aria-label="太極火爐">
      <defs><radialGradient id="wg-disk"><stop offset="0" style="stop-color:var(--disk-2)"/><stop offset="1" style="stop-color:var(--disk)"/></radialGradient></defs>
      <circle r="72" fill="url(#wg-disk)"/><circle r="70" class="w-rim"/>${furnaceHub(slots, ready)}</svg></div>`;
  }

  // ── 江湖頁的行動列（企劃者 2026-10-04：輪盤太大，改成一排五顆，樣式是她給的「水墨氣勁」）──
  // 選項標籤「探索（體力 5・…）」拆成名字與括號裡的說明
  const optParts = (o) => { const m = /^(.*?)（(.*)）$/.exec(o.label); return m ? [m[1], m[2]] : [o.label, ""]; };
  // 決戰三招的按鈕（決戰改版一）：引擎給「選項名（強攻・82 分）」，招與分數拆到按鈕右邊的小字、名字佔剩下的寬度——
  // 375px 上一顆按鈕的字只有約 285px，括號整句接在名字後面的話，十一、十二個字的名字會把一顆按鈕折成兩行（多 20px）
  const BATTLE_MOVE_LABEL = /^(.*)（((?:強攻|固守|奇襲)・\d+ 分)）$/;
  const optLabelHtml = (o) => { const m = o.id.startsWith("battle:act:") ? BATTLE_MOVE_LABEL.exec(o.label) : null; return m ? `<span class="b-name">${esc(m[1])}</span><span class="b-move">${esc(m[2])}</span>` : `<span>${esc(o.label)}</span>`; };
  // 前四顆對到選單上哪一顆、沒有時寫什麼；第五顆是移動（點了在下面展開走法與目的地）
  const ACT_CELLS = [
    { key: "explore", ids: ["act:explore"], name: "探索", none: "不能探索", icon: '<circle cx="12" cy="12" r="9"/><path d="M12 3v3m0 12v3M3 12h3m12 0h3M15 9l-4 2-2 4 4-2z"/>' },
    { key: "train", ids: ["act:train"], name: "遊歷", none: "沒有對手", icon: '<path d="M14.5 4h-5L7 7h10zM12 7v13M8 12h8"/>' },
    { key: "rest", ids: ["act:rest"], name: "打坐", none: "不能打坐", icon: '<circle cx="12" cy="7" r="2.5"/><path d="M8 20c0-3 3-4 4-4s4 1 4 4M5 15l3-2m11 2l-3-2"/>' },
    { key: "social", ids: ["act:socialize", "act:call"], name: "交友", none: "沒有人", icon: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>' },
  ];
  const MOVE_ICON = '<path d="M13 3l-3 7h5l-4 11 8-10h-5z"/>';
  const SHORT_SUB = { "act:rest": "回體力", "act:call": "挑一位" };  // 求見先打開名單挑人（FB-044：以前又寫一次「求見」；挑了人才花體力）
  const TALKED_OUT = "已經談滿", TALKED_OUT_SUB = "已談滿";  // 談滿了的求見（Game._talked_out_note 的開頭）在行動列格子裡的短說法（待 joy 潤）
  // 勝算的顏色（FB-044）：遊歷的小字第二行照風險上色
  const ODDS_TONE = { "穩勝": "good", "有把握": "good", "零風險": "good", "五五波": "even", "難分勝負": "even", "凶險": "bad", "必敗": "bad" };
  // 選單上有「打坐」就是平常閒著的時候：用行動列。事件、對話、路上、決戰的選項每次都不一樣，照舊排成一列按鈕
  // 序章裡閒著時選單只留這一步要的（打坐常常不在）：沒有事件的選項、不在路上，也當閒著的行動列來畫，沒亮的格子不畫（F12）
  // 籌備中、休季、暫停（season:）與閉關中（act:break）的選單只有一顆通知：那顆要畫成看得見的按鈕，不能掉進行動列的摺疊裡（M2）
  const NOTICE_MENU = /^(choice:|sense:|season:|act:break$)/;
  const idleMenu = (m) => m.options.some((o) => o.id === "act:rest") || (!!m.prologue && !m.on_road && !m.options.some((o) => NOTICE_MENU.test(o.id)));
  const inkCell = (key, name, sub, icon, attrs, cls, note = "") => `<button class="act-ink${cls}" data-key="${key}" data-glow="act:${key}" ${attrs}>
      <svg class="ink-icon" viewBox="0 0 24 24" aria-hidden="true">${icon}</svg><b>${esc(name)}</b><small>${esc(sub)}</small>${
      note ? `<small class="ink-note ${ODDS_TONE[note] || ""}">${esc(note)}</small>` : ""}</button>`;

  // 決戰集結時還沒參戰的人（FB-105）：加入（自己陣營那一邊）、散人的臨時投效。以前跟求見、拜師一起收在「此地還能做」的摺疊裡，
  // 不打開摺疊的人整場不在名單上（集結只有現實 30 分鐘）。現在畫在場景卡戰場名字那一行（musterScene），摺疊與選項列都不再列一次；
  // 鈕旁邊一小句說在這裡報名（MUSTER_NOTE），每一場決戰都看得到，不靠只說一次的提示。集結那一句（「選擇陣營加入；集結期間照常行動。」）
  // 是戰鬥引擎寫的，另一條線正在改那一段，這裡不動它（fix-1008 裁示）。
  // 只認「全都按得下去」的時候：已經加入或投效過的人有一顆是灰的「已加入」，照舊收在摺疊裡，畫面跟以前一樣；打不了這場仗的人
  // （不是交戰的一方、不在決戰的大區）選單上本來就沒有這幾顆。開打了才到的散人還能投效，也一樣畫在名字那一行（開打後的「加入戰局」
  // battle:join_late 是選單上唯一的一顆，本來就看得到，不在這裡：所以 MUSTER_JOIN 結尾要有冒號）。
  // 場景卡沒畫的時候不搬，照舊留在選單上（摺疊或選項列），鈕永遠不會不見：在路上（在路上的人加入不了，選單上本來就沒有這幾顆；
  // 萬一有，路上的場景卡收成兩行、不畫名字那一行），以及序章師父說話、草廬的場景卡不畫的那幾步（masterTalks）
  const MUSTER_JOIN = /^battle:(join|enlist):/;
  // 鈕旁邊那一小句（待 joy 潤）：加入的那一顆在名字右邊，這句夾在名字與鈕中間、指向它；散人的兩顆在名字底下另起一行，這句在名字右邊、往下指。
  // 放不下時省略號收尾（style.css 的 .muster-note），名字那一行不因此變高、不折行。箭頭另外放（MUSTER_ARROW），讀螢幕的軟體不唸它（aria-hidden）
  const MUSTER_NOTE = { join: "報名在這裡", enlist: "挑一邊臨時投效，只算這一場" };
  const MUSTER_ARROW = { join: "→", enlist: "↓" };
  // 序章：師父在說話（框顯示著）、眼前又沒有事件時，草廬那張地點描寫卡不畫——它是靜態的，而師父的整段話要用這塊地方（T7 審查 I1）
  // 出師那一段路（在路上）不算：第一條路的說明卡要留著（T7 審查 N2）。pageJianghu 照它決定畫不畫場景卡，musterJoins 照它決定搬不搬加入的鈕
  const masterTalksOf = (m) => !!pro() && !!m.guide && !m.on_road && !m.options.some((o) => o.id.startsWith("choice:"));
  function musterJoins(m) {
    if (m.on_road || masterTalksOf(m)) return [];
    const joins = m.options.filter((o) => MUSTER_JOIN.test(o.id));
    return joins.length && joins.every((o) => o.enabled) ? joins : [];
  }
  // 場景卡（伺服器的 Markdown）第一段是戰場名字（「**廣宗決戰**」）：包成一行，名字、那一小句、加入的鈕排在同一行；散人臨時投效的
  // 兩顆字多，另起一行排在名字底下（.wide，鈕上只寫「臨時投效【官軍】」，「只算這一場」寫在那一小句裡）。認不出第一段就排在卡片最上面。
  // 那一小句用 aria-describedby 接到那一排鈕上（一頁只有一張場景卡，id 不會重複）
  function musterScene(m, scene) {
    const joins = musterJoins(m);
    if (!joins.length) return scene;
    const kind = joins.some((o) => o.id.startsWith("battle:enlist:")) ? "enlist" : "join";
    const wide = kind === "enlist";
    const note = `<span class="muster-note" id="muster-note">${esc(MUSTER_NOTE[kind])}<span aria-hidden="true"> ${MUSTER_ARROW[kind]}</span></span>`;
    const row = `<div class="options muster-join${wide ? " wide" : ""}" role="group" aria-label="參戰" aria-describedby="muster-note">${joins.map((o) =>
      `<button class="btn small primary" data-act="choose" data-id="${esc(o.id)}"><span>${esc(wide ? optParts(o)[0] : o.label)}</span></button>`).join("")}</div>`;
    const head = /^<p>([\s\S]*?)<\/p>\n?/.exec(scene);
    return head ? `<div class="muster-head"><p>${head[1]}</p>${note}${row}</div>\n${scene.slice(head[0].length)}` : `<div class="muster-head">${note}${row}</div>\n${scene}`;
  }

  // ── 只能觀戰的人：開打中的全服決戰收成一行（FB-120）──
  // 開打後 Game.scene_text 給只能觀戰的人的是「戰場＋分隔線＋自己眼前的事」，戰場那一塊有名字、「【幕】（第 N／M 回合・…）」、最近五段
  // 戰報（放手一搏的原文、模型的故事）與觀戰的原因，QA 量到師父的框被擠到 1130、行動列 1226 以下（分頁列頂 756）。沒在打這一場的人
  // （人不在決戰的大區、沒加入、沒臨時投效：伺服器才會在戰場底下接分隔線）那一塊收成一行，點了攤開、底下一顆「收起戰場」。
  // 人在決戰的大區、還沒投效的散人也有分隔線（FB-109），可是名字那一行有投效的鈕（musterJoins），不收；
  // 攤開記的是戰場的名字（S.battleOpen：回合每輪都在變，記名字輪詢才不會收回去），自己收起或這一場打完（場景裡沒有開打中的回合）才清掉。
  // 參戰的人照舊：在場時整個畫面就是戰場（沒有分隔線）；離開大區、倒下的人最後一句是 BATTLE_MINE。集結時沒有回合數，歸 FB-107 收
  // 集結那一句；序章裡引擎不畫戰場（FB-113）。只認伺服器給的字（戰鬥引擎 _battle_scene_text 的寫法）：兩個正規式的測試在
  // tests/test_fb120_battle_fold.py，用真的戰場驗，寫法變了那裡就紅
  // BATTLE_ROUND：開打後的回合數（「【圍城日久】（第 4／9 回合・已送出…）」），集結時沒有；
  // BATTLE_MINE：參戰者看戰場的那一句（離開了大區、倒下了），他是這一場的人，不收
  const BATTLE_ROUND = /（第\s*(\d+)\s*／\s*\d+\s*回合/;
  const BATTLE_MINE = /這回合不出手|你已經倒下/;
  // 收成一行時接在回合數後面的那兩三個字、攤開之後戰場底下那一顆（都待 joy 潤）
  const BATTLE_PEEK = "點開看";
  const BATTLE_SHUT = "收起戰場";
  // 只能觀戰、正在開打：{ block 分隔線之前的戰場那一塊, rest 分隔線起的其餘, name 戰場名字, round 第幾回合 }；不是就 null
  function battleWatch(m) {
    const scene = (m && m.scene) || "";
    const cut = scene.search(/<hr\s*\/?>/);
    if (cut < 0 || m.on_road) return null;
    const block = scene.slice(0, cut);
    const round = BATTLE_ROUND.exec(block), head = /^<p>([\s\S]*?)<\/p>/.exec(block);
    // 參戰者那一句只看戰場那一塊的最後一段：引擎把看戰場的原因（觀戰、離開大區、倒下）寫在最後；中間的戰報有放手一搏的原文與
    // 模型的故事，有人寫「你已經倒下」也不能讓每個觀戰的人的戰場整段攤開（審查 M1）
    const last = block.slice(block.lastIndexOf("<p>"));
    if (!round || !head || BATTLE_MINE.test(last)) return null;
    return { block, rest: scene.slice(cut), name: head[1].replace(/<[^>]*>/g, "").trim(), round: Number(round[1]) };
  }
  function battleScene(m) {
    if (!BATTLE_ROUND.test(m.scene || "")) S.battleOpen = null; // 這一場打完了（或還在集結、沒有決戰）：下一場照舊先收著
    const w = battleWatch(m);
    if (!w || musterJoins(m).length) return m.scene;
    if (S.battleOpen === w.name) {
      return `${w.block}<p class="battle-shut"><button class="linkish" data-act="battle-shut" aria-expanded="true">${BATTLE_SHUT}</button></p>\n${w.rest}`;
    }
    // 名字是伺服器 Markdown 轉好的 HTML 拿掉標籤：已經跳脫過，不再跳脫一次
    return `<p class="battle-fold" data-act="battle-open" role="button" tabindex="0" aria-expanded="false">${w.name}　第 ${w.round} 回合・${BATTLE_PEEK}</p>\n${w.rest}`;
  }

  // ── 決戰的即時戰局條（Joy 2026-10-10 轉玩家反饋：「有辦法看即時戰局？那個推進多少我都不知道是啥意思」）──
  // 資料是引擎的 battle_instance.gauge：拔河，左邊是看的人那一邊；lean 是往左邊那一方偏多少（0～100）。旗子畫在 100−lean：
  // 誰佔上風，旗子就被拉到誰那一頭。淺色的兩截是分勝負的那一段（大勝），兩道細線是當場分出勝負的線（偏離中線 decisive），
  // 條上那一道色帶是上一回合旗子從哪裡移到哪裡；底下一格一回合，塗上那一回合佔上風那一邊的顏色。數字只寫在條的兩端（幾比幾）。
  function gaugeHtml(g) {
    if (!g) return "";
    const x = (lean) => 100 - lean;
    const who = (s) => (s === "left" ? g.left : g.right);
    const tint = (w) => `side-${esc(w.id)}${w.mine ? " mine" : ""}`;
    const zones = g.zones.map((z) => `<i class="g-zone ${z.side} ${tint(who(z.side))}" style="left:${x(z.to)}%;width:${z.to - z.from}%"><span>${esc(z.label)}</span></i>`).join("");
    const ticks = [50 - g.decisive, 50 + g.decisive].map((v) => `<i class="g-tick" style="left:${v}%"></i>`).join("");
    const last = g.rounds.length ? g.rounds[g.rounds.length - 1] : null;
    const trail = last && last.from !== last.to
      ? `<i class="g-trail ${tint(who(last.side))}" style="left:${Math.min(x(last.from), x(last.to))}%;width:${Math.abs(last.to - last.from)}%"></i>` : "";
    const chips = Array.from({ length: g.total }, (_, i) => {
      const r = g.rounds[i];
      const now = !r && g.phase === "active" && i + 1 === g.round;
      const cls = r ? (r.side === "tie" ? "tie" : tint(who(r.side))) : now ? "g-now" : "";
      const tip = r ? `第 ${r.n} 回合：${r.side === "tie" ? "相持" : `${who(r.side).name}佔上風`}` : now ? `第 ${i + 1} 回合：正在打` : `第 ${i + 1} 回合`;
      return `<li class="g-r ${cls}" title="${esc(tip)}">${i + 1}</li>`;
    }).join("");
    const end = (w, n, right) => `<span class="g-side ${tint(w)}">${right ? `<b>${n}</b> ` : ""}${esc(w.name)}${w.mine ? "（我方）" : ""}${right ? "" : ` <b>${n}</b>`}</span>`;
    return `<div class="gauge" role="img" aria-label="${esc(`戰局：${g.left.name} ${g.lean} 比 ${100 - g.lean} ${g.right.name}，${g.caption}`)}">`
      + `<div class="g-head">${end(g.left, g.lean, false)}${end(g.right, 100 - g.lean, true)}</div>`
      + `<div class="g-bar">${zones}${ticks}<i class="g-mid"></i>${trail}<b class="g-flag" style="left:${x(g.lean)}%"></b></div>`
      + `<ol class="g-rounds">${chips}</ol><p class="g-cap">${esc(g.caption)}</p>${meritHtml(g, tint)}</div>`;
  }
  // 戰局條底下的「本場戰功」（Joy 2026-10-10 個人戰功，battle_instance.merit_board）：兩軍各列前幾名，最後一行是自己排第幾、戰功怎麼來的。
  // 集結中、還沒有人出手時不畫
  function meritHtml(g, tint) {
    const b = g.merit;
    if (!b || g.phase === "muster" || (!b.left.length && !b.right.length && !(b.me && b.me.merit))) return "";
    const col = (w, rows) => `<div class="g-mcol ${tint(w)}"><b class="g-mside">${esc(w.name)}</b>${rows.length
      ? `<ol>${rows.map((r, i) => `<li${r.mine ? ' class="mine"' : ""}><i>${i + 1}</i><span>${esc(r.name)}</span><b>${r.merit}</b></li>`).join("")}</ol>`
      : '<p class="muted">還沒有人立功</p>'}</div>`;
    const me = b.me ? `<p class="g-me">你排第 ${b.me.rank}／${b.me.of}・戰功 ${b.me.merit}${b.me.parts.length ? `：${esc(b.me.parts.join("、"))}` : "（還沒出手）"}</p>` : "";
    return `<div class="g-merit"><p class="g-mtitle">本場戰功</p><div class="g-mcols">${col(g.left, b.left)}${col(g.right, b.right)}</div>${me}</div>`;
  }
  // 場景卡裡把戰局條放在戰場名字那一行底下（集結時名字那一行連著投效的鈕，見 musterScene）；收成一行的觀戰（battleScene）不放
  function withGauge(html, g) {
    if (!g || html.startsWith('<p class="battle-fold"')) return html;
    const muster = html.startsWith('<div class="muster-head">') ? html.indexOf("</div></div>\n") : -1;
    const cut = muster >= 0 ? muster + "</div></div>\n".length : html.startsWith("<p>") ? html.indexOf("</p>") + 4 : 0;
    return html.slice(0, cut) + gaugeHtml(g) + html.slice(cut);
  }
  // 攤開、收起都整頁重畫，原本有焦點的那一行（那一顆）跟著不見：焦點放回新畫出來的開關，鍵盤再按一次就收起、再攤開
  // （同戰況圖卡的 frontsTap，審查 M4）
  function battleOpen() {
    const w = battleWatch(S.main);
    S.battleOpen = w ? w.name : null;
    renderPage();
    document.querySelector("#page .battle-shut button")?.focus();
  }
  function battleShut() {
    S.battleOpen = null;
    renderPage();
    document.querySelector("#page .battle-fold")?.focus();
  }

  function actionBar(m) {
    const byId = Object.fromEntries(m.options.map((o) => [o.id, o]));
    const used = new Set(musterJoins(m).map((o) => o.id)); // 畫在場景卡上了（FB-105），不掉進「此地還能做」
    // 這裡只有一位大勢人物、沒有交友事件、他又見不到（名望不夠、閉門不見、這個遊戲日談滿）、福緣也沒到時，引擎不給交友
    // （只會花體力換同一句打發，Game._brush_off），選單上只剩直接列的「求見某某」（設計 9.1）：社交那一格改放它。
    // 交友或求見名單（兩位以上）在選單上時照舊，這顆收在摺疊裡
    const loneCall = m.options.find((o) => o.id.startsWith("call:") && o.id !== "call:back");
    const noted = []; // 畫出來、伺服器又寫了說明的格子：[格子上的名字, 選項 id]（行動列底下那幾行，見 actNotesHtml）
    // 序章（新手引導計畫一）：還沒亮的格子不畫（act:explore、act:train、act:rest、act:social、act:move）；
    // 不畫的格子對到的選項照樣記成用過，不會掉進「此地還能做」那個摺疊裡
    const cells = ACT_CELLS.map((d) => {
      const o = d.ids.map((id) => byId[id]).find(Boolean) || (d.key === "social" ? loneCall : undefined);
      if (o) used.add(o.id);
      if (!shown(`act:${d.key}`)) return "";
      if (!o) return inkCell(d.key, d.name, d.none, d.icon, "disabled", " off");
      const lone = o.id.startsWith("call:");
      const [label, detail] = optParts(o);
      const name = lone ? "求見" : label;  // 格子窄：名字寫「求見」，人物的名字放在下面一行
      noted.push([name, o.id]);
      // 按不下去的原因：標籤括號裡寫的是體力就是「體力不夠」，寫別的就照寫；整句太長、格子裝不下（約 60 px、不換行）時只留
      // 最後一小句（例：挑戰本人打贏之後「剛吃了敗仗，閉門不見」只寫「閉門不見」，T4）
      // 談滿了的求見（「已經談滿 3 輪，第 1 週・週日 00:00 之後再來」）：最後一小句是換日的那一刻，格子裝不下會被切成碎片，
      // 格子只寫「已談滿」，整句在底下那一行（Game.action_notes，day-scale 審查 I1）
      const sub = o.enabled ? (lone ? label.replace(/^求見/, "") : (SHORT_SUB[o.id] || detail.replace(/^體力 (\d+).*$/, "體力 $1")))
        : lone && detail.startsWith(TALKED_OUT) ? TALKED_OUT_SUB
        : (detail && !detail.startsWith("體力") ? detail.split("，").pop() : "體力不夠");
      // 體力之後還有說明（遊歷的「體力 10・2 路對手・必敗」）：挑出勝算那一段另起一行（FB-044；對手數放不下就不寫）。
      // 不一定是最後一段：有自己人也有敵人的地方後面還接「・或與自己人操練」（畫面批次審查 C1）
      const parts = detail.split("・");
      const note = o.enabled && /^體力 \d+/.test(parts[0]) ? (parts.find((x) => x in ODDS_TONE) || "") : "";
      return inkCell(d.key, name, sub, d.icon, o.enabled ? `data-act="choose" data-id="${esc(o.id)}"` : "disabled", o.enabled ? "" : " off", note);
    });
    const moves = m.options.filter((o) => followsMode(o.id));
    moves.forEach((o) => used.add(o.id));
    const open = S.wheelSel === "move";
    if (shown("act:move")) {
      cells.push(inkCell("move", "移動", moves.length ? `${moves.length} 條路` : "沒有路", MOVE_ICON,
        moves.length ? `data-act="wheel" data-key="move" aria-expanded="${open}"` : "disabled", (open ? " on" : "") + (moves.length ? "" : " off")));
    }
    const moveCard = !open || !shown("act:move") ? "" : `<div class="card act-move"><div class="seg move-mode" role="group" aria-label="走法">${MOVE_MODES.map((x) => `
          <button class="${S.moveMode === x.id ? "on" : ""}" data-act="move-mode" data-mode="${x.id}" aria-pressed="${S.moveMode === x.id}">${x.name}</button>`).join("")}</div>
        <div class="options">${moves.map((o) => `<button class="btn go" data-act="choose" data-id="${esc(o.id)}" ${o.enabled ? "" : "disabled"}>
          <span class="k">→</span><span>${esc(o.label)}</span></button>`).join("")}</div></div>`;
    // 其他只在此地才有的行動（招募、投靠、多出來的求見）收在摺疊裡，不佔行動列的高度。
    // 入伍段要你按的那一顆收在這裡（巡哨、傳道、保境安民、接糧車……，伺服器在框上帶的 guide.glow，FB-093）：那一步在這一處開頭摺疊先打開
    // 一次、那一顆發光（applyGlow）；其他時候收著。開合記在 S.here（hereFold，FB-087），重畫照它補回
    const extras = m.options.filter((o) => !used.has(o.id));
    const hotHere = extras.some((o) => guideGlow().includes(o.id));
    const here = extras.length ? `<details class="fold here"${hereFold(m, hotHere) ? " open" : ""}><summary>此地還能做 ${extras.length} 件事</summary><div class="fold-body options">${extras.map((o) => `
        <button class="btn" data-act="choose" data-id="${esc(o.id)}" ${o.enabled ? "" : "disabled"}><span>${esc(o.label)}</span></button>`).join("")}</div></details>` : "";
    const drawn = cells.filter(Boolean); // 序章裡沒亮的格子是空字串；一格都沒有、也沒有「此地還能做」時整條不畫
    // 行動列底下那幾行（explain-1）排在行動列之後：不推動「剛剛」、場景與整排行動（375×812 第一屏）。展開移動時讓位（走法與目的地那張卡
    // 緊貼在行動列底下），入伍段要按的鈕在「此地還能做」裡時也讓位（不把發光的那一顆往下推）
    const notes = open || hotHere ? "" : actNotesHtml(m, noted);
    return `${drawn.length ? `<div class="act-bar" role="group" aria-label="行動">${drawn.join("")}</div>` : ""}${notes}${moveCard}${here}`;
  }

  // 行動列底下那幾行（explain-1，試玩回饋：按下去之前不知道會怎樣）：探索、遊歷、交友（或求見）這一下會遇上什麼、打贏拿什麼。
  // 句子是伺服器照規則寫好的（m.action_notes：選項 id → 一句；序章裡是空的），這裡只照格子的順序排、前面冠格子上的名字。
  // 只寫畫出來的格子；打坐、移動的格子本身就寫著（回體力、幾條路），沒有說明
  // 新手期（伺服器給 status.howto_entry：加入起跟體力回復加快同一段，序章裡沒有）最後多一行「玩法說明」的入口（explain-2，FB-100：
  // 說明藏在齒輪裡，主畫面沒有一句指向它）。排在這一塊的最後：剛剛、場景、整排行動一個 px 都不動；點了打開設定抽屜、攤開玩法說明。
  // 過了新手期這一行就不畫，抽屜裡那一顆照舊
  const HOWTO_ENTRY = '<p class="howto-entry"><button class="linkish" data-act="howto-open" aria-haspopup="dialog">玩法說明 ›</button>這一季在打什麼、名望怎麼來、投靠與軍令</p>';
  function actNotesHtml(m, noted) {
    const notes = m.action_notes || {};
    const rows = noted.filter(([, id]) => notes[id]).map(([name, id]) => `<p><b>${esc(name)}</b>${esc(notes[id])}</p>`);
    if (m.status && m.status.howto_entry) rows.push(HOWTO_ENTRY);
    return rows.length ? `<div class="act-notes">${rows.join("")}</div>` : "";
  }

  // 「此地還能做」摺疊畫成開著還是收著（FB-087）。摺疊裡的鈕（例：求見盧植）被擋下來、或輪詢帶來新畫面，整頁重畫、摺疊是新畫的 DOM，
  // 不記的話就收起來——玩家要再點開才看得到剛按的那一顆。所以開合記在 S.here（跟軍令卡記 S.ordersShut 同一個做法）：玩家點開、收起時 toggle
  // 事件記下（檔案最後的 toggle 監聽），重畫照它補回；補畫出來的那一下 toggle 記下的還是同一個值，不會繞圈。
  // 記的是這一處（S.here.at 對上目前的地點）：換了地方就沒有記，從收著開始，不然開過一次，每個城鎮都攤著一排按鈕；回到原處、中間沒在別處開關過，還是原樣。
  // 發光的那一步（guide-3b 審查 Minor 11）：hot＝摺疊裡有框上 guide.glow 點名的鈕。收著就看不到，所以那一步在這一處**開頭**自動打開一次
  // （hereAuto 記打開過了，同一步換一處、或換下一步各算一次）；打開之後就是玩家的——收起來的不再每次重畫都被打開
  function hereFold(m, hot) {
    const at = (m.status && m.status.location) || "";
    const auto = `${guideKey(m.guide) || ""}@${at}`;
    if (hot && !S.hereAuto[auto]) {
      S.hereAuto[auto] = true;
      S.here = { at, open: true };
    }
    return !!(S.here && S.here.at === at && S.here.open);
  }

  // 展開移動之後，把走法與目的地那張卡捲到剛好露出來（W18 的作法搬過來：狀態列有心得提示時整頁往下推，
  // 卡片下緣會落到底部分頁列底下）。block: "nearest"：本來就看得到就不動；離分頁列多遠由 CSS 的 scroll-margin-bottom 決定
  function revealMoveCard() {
    const card = document.querySelector("#page .act-move");
    if (!card) return;
    const calm = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    card.scrollIntoView({ block: "nearest", behavior: calm ? "auto" : "smooth" });
  }

  // 第一季濃縮版的「本週軍令」（計畫 T6；伺服器只送自己陣營的，散人沒有）：預設展開，收起來的狀態照週次記住
  function ordersHtml(list, week, convoy) {
    const done = list.filter((o) => o.done).length;
    const cart = convoy ? `<div class="order-cart">🛒 ${esc(convoy)}</div>` : "";  // 押著的糧車（那一道沒了也照樣寫）
    const rows = list.map((o) => `
      <div class="order${o.done ? " done" : ""}">
        <div class="order-head"><b>${esc(o.title)}</b><span>${o.done ? "已達成" : `陣營 ${o.progress}／${o.quota}`}</span></div>
        <div class="order-text">${esc(o.text)}</div>
        ${o.how ? `<div class="order-how">${esc(o.how)}</div>` : ""}
        <div class="order-bar" role="meter" aria-valuemin="0" aria-valuemax="${o.quota}" aria-valuenow="${o.progress}" aria-label="${esc(o.title)}"><i style="width:${pct(o.progress, o.quota)}%"></i></div>
        <div class="order-meta">你做了 ${o.mine} 次・截止 ${esc(o.deadline)}</div>
      </div>`).join("");
    return `<details class="fold orders" data-week="${week}" ${S.ordersShut === week ? "" : "open"}>
      <summary>📜 本週軍令（${list.length}${done ? `，已達成 ${done}` : ""}）</summary><div class="fold-body">${cart}${rows}</div></details>`;
  }

  // 手上揭了的懸賞（status.bounties，bounties.status）：一張一行，怎麼交差、賞什麼。懸賞榜在城鎮才看得到，
  // 選單上有 act:bounties 時卡底下一顆「看懸賞榜」（就是那個選項，按了走 choose），不在城鎮寫一句去哪裡看。
  // 預設展開，收起來的狀態照手上那幾張記住（S.bountyShut）：揭了新的、交了差，清單變了就重新展開
  function bountiesHtml(list, options) {
    const key = list.map((b) => b.id).join(",");
    const board = (options || []).find((o) => o.id === "act:bounties");
    const rows = list.map((b) => `
      <div class="order">
        <div class="order-head"><b>${esc(b.title)}</b><span>${esc(b.issuer)}</span></div>
        <div class="order-how">${esc(b.how)}</div>
        <div class="order-meta">${esc(b.reward)}</div>
      </div>`).join("");
    const open = (options || []).some((o) => o.id === "bounty:back");  // 懸賞榜正開著（選單就是榜）：卡底下不再寫什麼
    const foot = open ? "" : board
      ? `<button class="btn small" data-act="choose" data-id="act:bounties" ${board.enabled ? "" : "disabled"}>看懸賞榜</button>`
      : '<div class="order-meta">到城鎮的懸賞榜前，可以揭新的或放棄。</div>';
    return `<details class="fold bounties" data-key="${esc(key)}" ${S.bountyShut === key ? "" : "open"}>
      <summary>🪧 懸賞（${list.length}）</summary><div class="fold-body">${rows}${foot ? `<div class="bounty-foot">${foot}</div>` : ""}</div></details>`;
  }

  // 三方態勢的三條（結算卡與江湖頁態勢小標的面板共用）：各用自己陣營的顏色、底色中性（T9 審查 M3）
  function stanceBars(rows, label) {
    return `<div class="fronts" role="group" aria-label="${label}">${rows.map((x) => `
      <div class="front"><div class="front-head"><span>${esc(x.name)}</span><b>${x.value}</b></div>
        <div class="front-bar stance side-${esc(x.side)}" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${x.value}" aria-label="${esc(x.name)}"><i style="width:${pct(x.value, 100)}%"></i></div></div>`).join("")}</div>`;
  }

  // ── 江湖頁最上面的一排小標：態勢｜大事｜主線（正式版辛，PM 2026-10-06）──
  // 以前是三張各 44px 的摺疊卡疊在「剛剛」上面（連縫約 170px），打完一仗整排行動就被擠出第一屏。現在是一排 44px 的小標：
  // 點哪一個，它的內容就在這一排正下面攤開；同一時間只開一個，再點一次收起，點別的就換過去。內容跟以前摺疊卡裡的一樣
  // （態勢：三條、收季規則、怎麼算的；大事：本週的公告，標題與內文都在面板裡；主線：主線與目標）。
  // 每個小標都可以沒有：沒有態勢（開關關著，或休季由結算卡取代）、沒有大事、主線是空的就不畫那一個，三個都沒有整排不畫。
  // 序章（新手引導計畫一）把三塊一個一個藏起來（shown("stances")／shown("board")／shown("quest")，態勢跟大事一起亮）：
  // peekParts 回傳的清單裡把那一塊換成 null，peekHtml 會略過 null，三塊都藏著整排不畫。
  // 展開哪一個記在 S.peekOpen（{ id, week }，帶著週次：換週就收回；輪詢重畫整頁也不會把開著的關掉）。
  // 「大事」小標上有一個點：這一週有還沒打開看過的大事。看過的記在 S.boardSeen（名號、季、週次、則數），另存一份在 localStorage
  // 當這個瀏覽器的方便（讀寫都包 try/catch，存不了就只記在這一頁）；換週沒有人看過，點又亮起來。週次每一季都從 1 起，
  // 所以記的要帶季：上一季第 1 週看過的，下一季第 1 週的大事照樣亮點（status.season，見 Game.status_data）。
  // 小標裡只有「大事 N」加這個點，不寫標題：428～440px 的手機一行放不下，整排會折成兩行（輪三審查）
  const PEEK_SEEN_KEY = "tx-board-seen";
  const peekWeek = (m) => (m.status && m.status.calendar ? m.status.calendar.week : 0);
  const peekSeason = (m) => (m.status && m.status.season) || 0;

  // 這個名號看過的大事：先看記憶體，沒有（或是別的名號留下的）再讀 localStorage（「季:週:則數」）；讀不到、格式不對（含舊的
  // 沒有季的格式）都當沒看過
  function boardSeen(m) {
    const owner = m.status && m.status.name ? m.status.name : "";
    if (S.boardSeen && S.boardSeen.owner === owner) return S.boardSeen;
    let seen = { owner, season: -1, week: -1, count: 0 };
    try {
      const got = String(localStorage.getItem(`${PEEK_SEEN_KEY}:${owner}`) || "").match(/^(\d+):(\d+):(\d+)$/);
      if (got) seen = { owner, season: Number(got[1]), week: Number(got[2]), count: Number(got[3]) };
    } catch (e) { /* 讀不到就當沒看過 */ }
    S.boardSeen = seen;
    return seen;
  }

  function markBoardSeen(m) {
    const owner = m.status && m.status.name ? m.status.name : "";
    const seen = { owner, season: peekSeason(m), week: peekWeek(m), count: (m.bulletin || []).length };
    S.boardSeen = seen;
    try { localStorage.setItem(`${PEEK_SEEN_KEY}:${owner}`, `${seen.season}:${seen.week}:${seen.count}`); } catch (e) { /* 存不了就只在這一頁有效 */ }
  }

  function boardUnseen(m, week) {
    const seen = boardSeen(m);
    return seen.season !== peekSeason(m) || seen.week !== week || seen.count < m.bulletin.length;
  }

  // 點開說明的那幾行（explain-2：戰況圖卡、態勢、大事、主線各一小段；伺服器照規則寫好的 status.war_help[鍵]，一行一段，跳脫）。
  // 伺服器沒給（開關關著、舊版）就是空字串
  function warHelp(m, key, id = "") {
    const lines = m.status && m.status.war_help && m.status.war_help[key];
    return lines && lines.length
      ? `<div class="war-help ${key}-help"${id ? ` id="${id}"` : ""}>${lines.map((t) => `<p>${esc(t)}</p>`).join("")}</div>` : "";
  }

  // 三塊的小標與面板：{ id, label（給讀的人聽的整句）, chip（小標裡的字）, flag（要不要亮點）, panel（點開的內容） }；沒有就是 null。
  // 面板最後接一小段說明（explain-2）：小標點開才畫，所以第一屏照舊只有那一排 44px
  function stancePeek(m) {
    const s = m.status;
    if (m.season_result || !s || !s.stances) return null; // 休季：結算卡上有最終態勢；開關關著：status 沒有 stances
    const rows = STANCE_NAMES.map(([side, name]) => ({ side, name, value: s.stances[side] }));
    const n = s.stance_notes || {};
    const how = [n.sum ? `官軍、黃巾：${esc(n.sum)}` : "", n.haoqiang ? `豪強：${esc(n.haoqiang)}` : ""].filter(Boolean).join("；");
    return {
      id: "stance",
      label: `三方態勢：${rows.map((x) => `${x.name} ${x.value}`).join("、")}`,
      chip: `<span class="peek-name">態勢</span><span class="peek-nums">${rows.map((x) => `<b class="side-${esc(x.side)}">${x.value}</b>`).join("·")}</span>`,
      panel: `${stanceBars(rows, "三方態勢")}${s.stance_rule ? `<p class="stance-rule">${esc(s.stance_rule)}</p>` : ""}${how ? `<p class="stance-how">${how}</p>` : ""}${warHelp(m, "stance")}`,
    };
  }

  function boardPeek(m, week) {
    if (!m.bulletin || !m.bulletin.length) return null;
    return {
      id: "board",
      label: `本週江湖大事 ${m.bulletin.length} 則`,
      chip: `<span class="peek-name">大事</span><b class="peek-count">${m.bulletin.length}</b>`,
      flag: boardUnseen(m, week),
      panel: m.bulletin.map((b) => `<div class="bulletin-item">${b}</div>`).join("") + warHelp(m, "board"),
    };
  }

  // 第一季把 beta 的主線關掉、其他也都沒有東西時，quest 是空的：這一塊不畫（計畫 T8）
  function questPeek(m) {
    return m.quest && m.quest.trim() ? { id: "quest", label: "主線與目標", chip: '<span class="peek-name">主線</span>', panel: m.quest + warHelp(m, "quest") } : null;
  }

  const peekParts = (m) => [shown("stances") ? stancePeek(m) : null, shown("board") ? boardPeek(m, peekWeek(m)) : null, shown("quest") ? questPeek(m) : null];

  function peekHtml(parts, week) {
    const list = parts.filter(Boolean);
    if (!list.length) return "";
    const open = S.peekOpen && S.peekOpen.week === week ? list.find((p) => p.id === S.peekOpen.id) : null;
    const row = list.map((p) => {
      const on = p === open, dot = p.flag && !on; // 開著的時候就是正在看，不亮點
      return `<button class="peek-chip ${p.id}${on ? " on" : ""}" data-act="peek" data-id="${p.id}" aria-expanded="${on}" aria-label="${esc(p.label)}${dot ? "，有還沒看過的" : ""}">${p.chip}${dot ? '<i class="peek-dot" aria-hidden="true"></i>' : ""}</button>`;
    }).join("");
    return `<div class="peek" id="peek"><div class="peek-row" role="group" aria-label="態勢、大事與主線">${row}</div>${open ? `<div class="peek-panel ${open.id}">${open.panel}</div>` : ""}</div>`;
  }

  const peekBlock = (m) => peekHtml(peekParts(m), peekWeek(m));

  // 點小標：原地換掉這一塊（不重畫整頁：重畫會讓「剛剛」再播一次浮現動畫），焦點還給同一顆小標
  function peekTap(id) {
    const m = S.main, week = peekWeek(m);
    const was = S.peekOpen && S.peekOpen.week === week ? S.peekOpen.id : null;
    S.peekOpen = was === id ? null : { id, week };
    if (was === "board" || id === "board") markBoardSeen(m); // 打開或離開「大事」都算看過：開著的時候又來的新事，離開時一併算
    const box = document.getElementById("peek");
    if (box) box.outerHTML = peekBlock(m);
    const chip = document.querySelector(`.peek-chip[data-id="${id}"]`);
    if (chip) chip.focus();
  }

  // 第一季的結算卡（休季才有，計畫 T9）：結局與季末公告、最終態勢與三條戰況；十二件大事與各陣營出力前五收在摺疊裡
  function resultHtml(r) {
    // 戰況照江湖頁標兩端（FB-041）；態勢三條走 stanceBars
    const bars = (rows, label) => `<div class="fronts" role="group" aria-label="${label}">${rows.map((x) => `
      <div class="front"><div class="front-head"><span>${esc(x.name)}</span><b>${x.value}</b></div>
        <div class="front-bar" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${x.value}" aria-label="${esc(x.name)}"><i style="width:${pct(x.value, 100)}%"></i></div>${FRONT_ENDS}</div>`).join("")}</div>`;
    const events = r.timeline.map((e) => `<div class="result-event"><b>第 ${e.week} 週・${esc(e.title)}</b>${
      e.locked_by ? `<small>${esc(e.locked_by)} 改寫</small>` : ""}${e.text}</div>`).join("");
    const ranks = r.rankings.map((f) => `<div class="result-rank"><b>${esc(f.name)}</b>${f.rows.length
      ? `<ol>${f.rows.map(([n, v]) => `<li><span>${esc(n)}</span><i>${v}</i></li>`).join("")}</ol>`
      : "<p>（沒有人出力）</p>"}</div>`).join("");
    return `<section class="card result"><h2>賽季落幕：${esc(r.title)}</h2><div class="result-text">${r.text}</div>
      <h3>最終態勢</h3>${stanceBars(r.stances, "最終態勢")}<h3>最終戰況</h3>${bars(r.fronts, "最終戰況")}
      <details class="fold"><summary>這一季的十二件大事</summary><div class="fold-body">${events}</div></details>
      <details class="fold"><summary>各陣營出力前五</summary><div class="fold-body result-ranks">${ranks}</div></details></section>`;
  }

  // 戰況條兩端標陣營（FB-041）：條上左邊金色那一截是黃巾佔的、右邊藍色是官軍，字的顏色跟那一截一樣。
  // 戰線在亂局裡時（FB-065）正中間多一個小小的「亂局」標，剛好在亂局帶下面：豪強的地盤，中性的顏色，不佔多一行
  const frontEnds = (chaos) => `<div class="front-ends" aria-hidden="true"><span class="huang">黃巾</span>${
    chaos ? '<span class="chaos-tag">亂局</span>' : ""}<span class="guan">官軍</span></div>`;
  const FRONT_ENDS = frontEnds(false);

  // 態勢那一行（FB-065）：官軍、黃巾是幾條戰況合起來的，豪強是割據（有戰線在亂局就漸長）。說明由伺服器給（status.stance_notes），
  // 跟見聞→大勢的割據說明同一句，前端不自己數條數。狀態列展開時用它（江湖頁的三條在最上面那一排小標的態勢面板裡，正式版辛）
  function stancesHtml(stances, notes) {
    const n = notes || {};
    const side = (id) => `${STANCE_NAMES.find(([key]) => key === id)[1]} ${stances[id]}`;
    const note = (text) => (text ? `（${esc(text)}）` : "");
    return `<div class="stances-line"><span>態勢</span><span>${side("guan")}・${side("huang")}${note(n.sum)}<br>${side("haoqiang")}${note(n.haoqiang)}</span></div>`;
  }

  // 第一季濃縮版的三條戰況（伺服器有送 fronts 才畫）：0 是官軍穩控、100 是黃巾控制，條上黃的那一截是黃巾佔的。
  // 條上淺色的一段是亂局帶（band＝status.chaos_band，兩端含在內；豪強趁亂割據的戰況區間），戰況落在裡面的圖卡標「亂局」（f.chaos）。
  // 三方態勢在江湖頁最上面那一排小標的態勢面板裡（正式版辛），不在這一排底下重複
  // tap：伺服器有給戰況的說明（status.war_help.fronts，explain-2）時整排圖卡是一顆按鈕，點了在底下攤開說明（跟點體力條同一個做法）。
  // 變成按鈕之後裡面的 meter 不再念得出來（審查 Minor 4）：鈕的名字自己帶三條戰線的值，用的是同一份資料，畫面不變
  function frontsHtml(fronts, band, tap = false) {
    const shade = band ? `<span class="chaos-band" aria-hidden="true" title="亂局帶" style="left:${pct(band.low, 100)}%;width:${pct(band.high - band.low, 100)}%"></span>` : "";
    const act = tap ? ` data-act="fronts-help" role="button" tabindex="0" aria-expanded="${!!S.frontsOpen}" aria-controls="fronts-help"` : ' role="group"';
    const values = fronts.map((f) => `${f.name} ${f.value}${f.chaos ? "（亂局）" : ""}`).join("、");
    const label = tap ? `戰況：${values}（0 官軍穩控，100 黃巾控制；點開看說明）` : "戰況：0 官軍穩控，100 黃巾控制";
    return `<div class="fronts"${act} aria-label="${esc(label)}">${fronts.map((f) => `
      <div class="front${f.chaos ? " chaos" : ""}"><div class="front-head"><span>${esc(f.name)}</span><b>${f.value}</b></div>
        <div class="front-bar" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${f.value}" aria-label="${esc(f.name)}${f.chaos ? "，在亂局" : ""}"><i style="width:${pct(f.value, 100)}%"></i>${shade}</div>${frontEnds(f.chaos)}</div>`).join("")}</div>`;
  }

  // 江湖頁那一排戰況圖卡＋點開的說明（explain-2）：包在 #war 裡，點圖卡原地換掉這一塊（同 peekTap：不重畫整頁，「剛剛」不再播浮現動畫），
  // 說明排在圖卡底下，只推動它底下的小地圖。伺服器沒給說明（開關關著、舊版）就照舊只是一排圖卡、不能點
  function frontsBlock(m) {
    const help = !!(m.status && m.status.war_help && m.status.war_help.fronts && m.status.war_help.fronts.length);
    return `<div class="war" id="war">${frontsHtml(m.fronts, m.status && m.status.chaos_band, help)}${
      help && S.frontsOpen ? warHelp(m, "fronts", "fronts-help") : ""}</div>`;
  }

  function frontsTap() {
    S.frontsOpen = !S.frontsOpen;
    const box = document.getElementById("war");
    if (box && S.main && S.main.fronts) box.outerHTML = frontsBlock(S.main);
    document.querySelector('.fronts[data-act="fronts-help"]')?.focus(); // 換掉之後焦點放回圖卡，鍵盤可以再按一次收起
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
    const btn = g.end ? '<button class="btn small" data-act="guide-ack">知道了</button>'
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

  function pageJianghu() {
    const m = S.main;
    // 「剛剛」（A4）：預設只露出開頭幾行，太長的（例如新角色的開場故事）收著、點「展開全文」看完，不在卡片裡捲。
    // 展開記在 S.nowOpen（記的是那一則本身），換成新的一則就自動收回；其實放得下的話 afterPage() 會拿掉收合。
    // 畫的是 m.now：最新一則只是本週大事（小標點開的面板）上已經有全文的大事時，伺服器改給再前面那一則（FB-046）；江湖紀錄頁照舊用 m.latest
    const expanded = S.nowOpen === m.now;
    const [text, chips] = !m.card && m.now ? splitChips(m.now) : ["", ""];
    const now = m.card
      ? `<div class="card battle-card">${fightCard(m.card, m.card_id)}${gaugeHtml(m.card_gauge)}${m.now || ""}</div>`
      : m.now ? `<div class="now ${expanded ? "open" : "clamp"}${m.on_road ? " road" : ""}"><div class="now-text">${text}<button class="linkish now-more" data-act="now-more" aria-expanded="${expanded}">${nowMore(expanded)}</button></div>${chips}</div>` : "";
    const free = m.free_text != null
      ? `<form class="free" id="free-form" data-op="${esc(m.free_op || "battle_text")}"><input class="input" name="text" maxlength="20" placeholder="${esc(m.free_text || "輸入你想做的事（20字內）")}"><button class="btn primary small" type="submit">送出</button></form>${m.free_text_note ? `<p class="free-note">${esc(m.free_text_note)}</p>` : ""}`
      : "";
    // 路上那顆灰的「（在路上，幾時抵達）」不畫：往哪、幾時到狀態列已經寫著（FB-046），少一顆也讓路上的捷徑回到第一屏（FB-048）。
    // 決戰集結時還沒參戰的加入鈕畫在場景卡戰場名字那一行（FB-105，musterScene）：事件、對話開著時也是，選項列不再列一次
    const joined = new Set(musterJoins(m).map((o) => o.id));
    const opts = m.options.filter((o) => o.id !== "act:on_road" && !joined.has(o.id));
    // 走法切換：選單上有「前往」或路上的「折返」才出現（對話、事件、戰鬥的選單沒有），緊貼在第一個這種選項上面——
    // 它只管這兩種，放在整排選項最上面的話，第一屏就被它擠掉一個選項（A4）
    const firstMove = opts.findIndex((o) => followsMode(o.id));
    const links = m.on_road
      ? `<div class="road-links" role="group" aria-label="路上可以去的地方">${ROAD_LINKS.map((x) =>
        `<button class="btn ghost small" data-act="tab" data-tab="${x.tab}">${x.name}</button>`).join("")}</div>`
      : "";
    const modes = firstMove >= 0
      ? `<div class="seg move-mode" role="group" aria-label="走法"><span aria-hidden="true">走法</span>${MOVE_MODES.map((x) => `
          <button class="${S.moveMode === x.id ? "on" : ""}" data-act="move-mode" data-mode="${x.id}" aria-pressed="${S.moveMode === x.id}">${x.name}</button>`).join("")}
        </div>`
      : "";
    // 在路上，走法排在整排選項底下（FB-055）：路上的五個選項要全在第一屏，走法那一列（54 px）排在前面會把最後一個擠到分頁列底下
    const modesLast = m.on_road;
    // 路上的四樣小事排成 2×2（FB-055）：四樣小事共兩列，狀態列多一行提示，最後一顆也不會掉到分頁列底下
    // （折返、喊停見下面 FB-060）。標籤「名（補充）」拆成兩行：名字一行、補充小字一行
    const isTask = (o) => m.on_road && ROAD_TASKS.test(o.id);
    const firstTask = opts.findIndex(isTask);
    const lastTask = opts.length - 1 - [...opts].reverse().findIndex(isTask);
    const taskButton = (o, name, note) => {
      if (name === undefined) [, name, note] = o.label.match(/^(.*?)（(.*)）$/) || [null, o.label, ""];
      return `<button class="btn task" data-act="choose" data-id="${esc(o.id)}" ${o.enabled ? "" : "disabled"}><span class="t-name">${esc(name)}</span>${note ? `<span class="t-note">${esc(note)}</span>` : ""}</button>`;
    };
    // 多段路的「折返」與「喊停」併成一列兩格（FB-060）：各佔一整列的話，再加上狀態列的心得提示，最底下的「走法」會落到分頁列底下。
    // 只有兩個都在時才併；標籤照伺服器給的字拆成「名字／補充小字」：「折返 潁川郡（陽翟）（趕路約 2 分鐘・體力 4）」
    // →「↩ 折返 潁川郡（陽翟）」「趕路約 2 分鐘・體力 4」，「喊停（到洛陽官道就停下）」→「喊停」「到洛陽官道就停下」
    // （地名放名字那一行：補充放地名的話，趕路、疾行的字多、會折成兩行，整列又長高 16 px）
    const isWay = (o) => m.on_road && (o.id.startsWith("road:back") || o.id === "act:halt");
    const paired = opts.filter(isWay).length === 2;
    const firstWay = opts.findIndex(isWay);
    const lastWay = opts.length - 1 - [...opts].reverse().findIndex(isWay);
    const wayButton = (o) => {
      if (o.id === "act:halt") { // 「到潁川郡（陽翟）就停下」在窄的那一格折成兩行：換成同一個意思的短說法
        const [, name, note] = o.label.match(/^(.*?)（(.*)）$/) || [null, o.label, ""];
        return taskButton(o, name, note.replace(/^到(.*)就停下$/, "停在$1"));
      }
      const [, dest, note] = o.label.match(/^折返\s*(.*?)（([^（）]*)）$/) || [null, o.label.replace(/^折返\s*/, ""), ""];
      return taskButton(o, `↩ 折返 ${dest}`.trim(), note);
    };
    // 有所感選做法（explain-2）：伺服器給了 sense_help.tags 才把鈕上原本寫 1～4 的那一格改寫這個做法是哪一種心意（不多佔寬度）。
    // 審查 I1 起伺服器預設不給（sensing.SHOW_KINDS）：鈕上照舊 1～4；企劃者要恢復時伺服器那邊改一行，這裡照畫
    const senseTag = (o) => (m.sense_help && m.sense_help.tags && m.sense_help.tags[o.id]) || "";
    const menu = idleMenu(m) ? actionBar(m) : `<div class="options">${opts.map((o, i) => S.sensing && o.id === SENSE_DRAW ? sensePadHtml() : o.id === FREE_TEXT_OPTION && S.answering && o.enabled ? `
        <form class="free answer" id="answer-form"><input class="input" name="text" maxlength="20" placeholder="${esc(o.label)}（20字內）" aria-label="${esc(o.label)}"><button class="btn primary small" type="submit">說出口</button></form>` : o.id === SAY_OPTION && S.saying && o.enabled ? `
        <form class="free answer" id="say-form"><input class="input" name="text" maxlength="20" placeholder="想對他說的話（20字內）" aria-label="自己說"><button class="btn primary small" type="submit">說出口</button></form>` : isTask(o) ? `${i === firstTask ? '<div class="road-tasks">' : ""}${taskButton(o)}${i === lastTask ? "</div>" : ""}` : paired && isWay(o) ? `${i === firstWay ? '<div class="road-tasks road-ways">' : ""}${wayButton(o)}${i === lastWay ? "</div>" : ""}` : `${i === firstMove && !modesLast ? modes : ""}
        <button class="btn ${followsMode(o.id) ? "go" : ""}" data-act="choose" data-id="${esc(o.id)}" ${o.enabled ? "" : "disabled"}>
          ${senseTag(o) ? `<span class="k sense">${esc(senseTag(o))}</span>` : `<span class="k">${o.id.startsWith("move:") ? "→" : o.id.startsWith("road:back") ? "↩" : i + 1}</span>`}${optLabelHtml(o)}
        </button>`).join("")}${modesLast ? modes : ""}
      </div>`;
    // 有所感選做法（explain-2）：鈕底下兩行小字（做法跟此地的關係、意境拿來做什麼），排在做法後面，不把做法往下推
    const senseNotes = !idleMenu(m) && m.sense_help && m.sense_help.lines && m.sense_help.lines.length
      ? `<div class="act-notes sense-notes">${m.sense_help.lines.map((t) => `<p>${esc(t)}</p>`).join("")}</div>` : "";
    // 在路上，那段固定的說明只露兩行、點了看全文（FB-055）：剛按完路上小事時「剛剛」的結果卡會長高，狀態列又有提示的話，
    // 最後一排小事會掉到分頁列底下；說明的內容路上的選項與捷徑本來就寫著。展開記在 S.sceneOpen，下了路就清掉
    if (!m.on_road) S.sceneOpen = false;
    // 序章：師父在說話時草廬那張地點描寫卡不畫（masterTalksOf，那裡寫著為什麼）
    const masterTalks = masterTalksOf(m);
    const scene = masterTalks ? ""
      : m.on_road
        ? `<section class="card scene road${S.sceneOpen ? "" : " clamp"}" data-act="scene-more" role="button" tabindex="0" aria-expanded="${!!S.sceneOpen}">${m.scene}</section>`
        : `<section class="card scene">${withGauge(musterScene(m, battleScene(m)), m.battle_gauge)}${m.here && m.here.length ? hereHtml(m) : ""}${m.party || (m.calls && m.calls.length) ? socialHtml(m) : ""}</section>`;
    // 序章：小地圖與江湖紀錄的連結要等「輿圖、見聞」亮了才畫（shown("minimap")）
    const tail = shown("minimap") ? `<div class="mini" data-act="tab" data-tab="map" role="button" aria-label="展開輿圖">${m.minimap}</div>
      <button class="linkish" data-act="news" data-news="journal">看江湖紀錄 ›</button>` : "";
    // 態勢｜大事｜主線 收成一排小標（正式版辛）：排在最上面、「剛剛」之前，不管是哪一種選單；在路上才排到選項底下（FB-055）。
    // 三張摺疊卡疊起來有 170px，打完一仗整排行動就被擠出第一屏；一排只有 44px。公告的展開、已看過都是小標自己記（見 peekHtml）
    const week = peekWeek(m);
    const peek = peekBlock(m);
    // 三條戰況排在行動列下面、小地圖上面，不擠掉第一屏的「剛剛」、場景與行動列
    // 點圖卡在底下攤開說明（explain-2，frontsBlock）
    const fronts = m.fronts && shown("fronts") ? frontsBlock(m) : "";
    const resultCard = m.season_result ? resultHtml(m.season_result) : "";  // 休季的結算卡排在最上面（計畫 T9）
    // 本週軍令排在行動列（與路上捷徑）下面、三條戰況上面：不擠掉第一屏的「剛剛」、場景與行動列（計畫 T6）
    const orderCard = (m.orders || m.convoy) && shown("orders") ? ordersHtml(m.orders || [], week, m.convoy) : "";
    // 懸賞卡跟軍令卡排在一起（散人沒有軍令，這張就是他的）：手上沒揭任何一張就不畫
    const bountyCard = m.status && m.status.bounties && m.status.bounties.length && shown("orders") ? bountiesHtml(m.status.bounties, m.options) : "";
    // 序章第一步（還沒遇到師父）：選項底下一行「略過序章」，不想走序章的人直接站到起點（設計 7.3）
    const skip = pro() && pro().skip ? '<button class="linkish skip-prologue" data-act="do" data-op="skip_tutorial">略過序章</button>' : "";
    // 劇情文字在上、行動在下（企劃者 2026-10-04）。行動列只有一排，375×812 上「剛剛」、場景與整排行動都在第一屏。
    // 路上的三個捷徑（links）緊接在場景（「也可以打開輿圖改去別處，或去修練、煉製」那一段）底下、選項上面：
    // 排在路上的五六顆選項底下時落在第一屏外，要捲才看得到（FB-048）。說書人的話緊貼在行動上方（引導重做設計 8.1）
    const guide = guideHtml(m.guide, m.on_road);
    // 在路上（FB-055）：路上的五個選項要全在第一屏（375×812），所以那一排小標與說書人的框都排在選項底下——
    // 不是這一刻要按的；捷徑還是緊接在場景底下（FB-048）
    if (m.on_road) return `${resultCard}${now}${scene}${links}${free}${menu}${guide}${peek}${orderCard}${bountyCard}${fronts}${tail}`;
    return `${resultCard}${peek}${now}${scene}${links}${guide}${free}${menu}${senseNotes}${skip}${orderCard}${bountyCard}${fronts}${tail}`;
  }

  // 此地還有誰（玩家之間的互動第一層，企劃者 2026-10-08）：場景卡底下一行，名字點了打開玩家卡（peerHtml）。
  // 人多時先列 HERE_SHOW 個、其餘收在「還有 N 人」裡（點了全列，記在 S.hereOpen）。真人假人是同一份名單（伺服器不分）
  const HERE_SHOW = 5;
  function hereHtml(m) {
    const all = m.here || [];
    if (!all.length) return "";
    const open = S.hereOpen || all.length <= HERE_SHOW + 1;
    const list = open ? all : all.slice(0, HERE_SHOW);
    return `<div class="here"><span class="here-k">此地還有</span>${list.map((p) =>
      `<button class="peer-name" data-act="peer" data-name="${esc(p.name)}">${esc(p.name)}<small>（${esc(p.side)}）</small></button>`).join("")}${
      open ? "" : `<button class="linkish here-more" data-act="here-more">還有 ${all.length - HERE_SHOW} 人 ▾</button>`}</div>`;
  }

  // 玩家互動第二層：別人遞給你、還沒回的打招呼、結伴、切磋邀請（一件一行，後面是回應鈕——就是選單上的 invite: 選項，按了走 choose），
  // 以及結伴同行的那一行（跟著別人的人有「分道揚鑣」）。字都是伺服器寫好的（social.calls、Game.party_view）
  function socialHtml(m) {
    const calls = (m.calls || []).map((c) => `<div class="call"><span>${esc(c.text)}</span>${c.options.map((o) =>
      `<button class="btn small" data-act="choose" data-id="${esc(o.id)}" ${o.enabled ? "" : "disabled"}>${esc(o.label)}</button>`).join("")}</div>`).join("");
    const party = m.party ? `<div class="party"><span>${esc(m.party.text)}</span>${m.party.lead ? ""
      : '<button class="btn small ghost" data-act="party-leave">分道揚鑣</button>'}</div>` : "";
    return `<div class="calls">${calls}${party}</div>`;
  }
  async function leaveParty() {
    await busy(async () => {
      const r = await api("/api/party/leave", {});
      if (r.main) setMain(r.main);
      renderPage();
    });
  }

  // 玩家卡（第一層）：點「此地還有」的名字疊上來的抽屜。名號、門派・陣營・頭銜、等級、身上兩門（名字與品質），底下是卡上的動作鈕
  // （伺服器照 social.ACTIONS 給，第二層的贈物、結伴、打招呼、切磋、論武都掛在這裡）。人走了（card 是 null）寫伺服器給的那一句
  function peerHtml() {
    const P = S.peer;
    const c = P.card;
    const body = P.loading ? '<p class="muted">……</p>'
      : !c ? `<p>${esc(P.gone || "他已經不在這裡了。")}</p>`
      : `<div class="peer-head"><h3>${esc(c.name)}</h3><div class="peer-title">${[...c.affiliation.split("・"), `第${c.level}級`].map((t) => `<span class="peer-seg">${esc(t)}</span>`).join("・")}</div>${c.record ? `<p class="peer-record">${esc(c.record)}</p>` : ""}</div>
        <div class="peer-arts">${c.arts.length ? c.arts.map((a) => `<div class="peer-art"><small>${esc(a.kind)}</small><b>${esc(a.name)}</b><span>${esc(a.quality)}</span></div>`).join("") : '<p class="muted">身上沒有功夫。</p>'}</div>
        ${P.amountFor != null && c.actions[P.amountFor] ? `<form class="free peer-amount" id="peer-amount">${choiceSelect(c.actions[P.amountFor])}<input class="input" name="amount" type="number" inputmode="numeric" min="1" max="${c.actions[P.amountFor].amount}" placeholder="${esc(c.actions[P.amountFor].label)}：1～${c.actions[P.amountFor].amount}" aria-label="數量"><button class="btn primary small" type="submit">送出</button></form>` : ""}
        ${c.actions.length ? peerActsHtml(c.actions) : ""}`;
    return `<div class="sheet-bg" data-act="peer-close"></div>
      <div class="sheet peer-card" role="dialog" aria-label="${esc(P.name)}">
        <div class="grip"></div>
        ${P.msg ? `<div class="peer-msg">${P.msg}</div>` : ""}
        ${body}
        <div class="row"><button class="btn ghost" data-act="peer-close">關閉</button></div>
      </div>`;
  }
  // 卡上的鈕：同一個 group 的（論武出哪一樣，每一樣一顆）收成一個下拉清單＋一顆鈕，按下去送清單上選的那一顆（照它在 actions 裡的索引）；
  // 只有一顆的 group 照常畫。下拉清單整排佔滿一列，其餘的鈕照舊兩欄
  function peerActsHtml(actions) {
    const groups = {};
    actions.forEach((b, i) => { if (b.group && b.enabled) (groups[`${b.action}|${b.group}`] ||= []).push(i); });
    const done = new Set();
    const one = (b, i) => `<button class="btn" data-act="peer-act" data-i="${i}" ${b.enabled ? "" : "disabled"}>${esc(b.label)}${b.note ? `<small>${esc(b.note)}</small>` : ""}</button>`;
    const html = actions.map((b, i) => {
      const members = b.group && b.enabled ? groups[`${b.action}|${b.group}`] : null;
      if (!members || members.length < 2) return one(b, i);
      if (done.has(members)) return "";
      done.add(members);
      return `<div class="peer-pick"><select class="input" aria-label="${esc(b.group)}">${members.map((j) => `<option value="${j}">${esc(actions[j].pick || actions[j].label)}</option>`).join("")}</select>`
        + `<button class="btn" data-act="peer-pick">${esc(b.group)}${b.note ? `<small>${esc(b.note)}</small>` : ""}</button></div>`;
    }).join("");
    return `<div class="peer-acts">${html}</div>`;
  }
  // 卡上的鈕要先挑一樣（贈素材）：一個下拉選單，每一樣寫身上有幾份
  const choiceSelect = (b) => (b.choices && b.choices.length
    ? `<select class="input" name="choice" aria-label="挑一樣">${b.choices.map((x) => `<option value="${esc(x.id)}">${esc(x.label)}（${x.max}）</option>`).join("")}</select>`
    : "");
  async function openPeer(name) {
    S.peer = { name, loading: true };
    render();
    try {
      const r = await api(`/api/peer?name=${encodeURIComponent(name)}`);
      if (!S.peer || S.peer.name !== name) return; // 等的時候關掉或換了人
      S.peer = { name, card: r.card, gone: r.gone };
    } catch (e) {
      S.peer = null;
    }
    render();
  }
  // 按卡上的鈕：要填數量的先問數量（prompt 在 artifact 外照常可用，但這裡一律用頁內的輸入，見 peerAmount），有 confirm 的先問一次
  async function peerAct(i, sure = false, amount = 0, choice = "") {
    const P = S.peer;
    const b = P && P.card && P.card.actions[i];
    if (!b) return;
    if (b.amount > 0 && !amount) { S.peer.amountFor = i; render(); return; }
    if (!sure && b.confirm) { ask(b.confirm, b.label, () => peerAct(i, true, amount, choice)); return; }
    await busy(async () => {
      const r = await api("/api/peer/act", { name: P.name, action: b.action, arg: b.arg, amount, choice });
      if (r.main) setMain(r.main);
      S.peer = { name: P.name, card: r.card, gone: r.gone, msg: r.message };
      render();
    });
  }

  // 序章裡師父的話也放在修練頁、煉製頁最上面（序章的第 4～6、9、10 步在這兩頁做，不用切回江湖頁看要做什麼）；序章外不畫。
  // 碰到才說的提示（伺服器標 hint）也畫在這兩頁最上面：修練失敗、改練、合成、熔煉都是在這兩頁做的，提示在做完的那一下上框、記進紀錄，
  // 不畫的話玩家要切回江湖頁才看得到（新手引導計畫三，T1 審查 I-1）。同一個框、同一顆「知道了」；說書人的步驟、結語、入伍段的框仍只在江湖頁
  const proGuide = () => (pro() || (S.main.guide && S.main.guide.hint) ? guideHtml(S.main.guide, false) : "");

  // 武學屬性有什麼用（W2、FB-089：標題冠上「武學」，跟升級配點的「屬性」分開）：修練、煉製兩頁各摺一行，收著只多一行小字。說明的字是伺服器照程式的規則寫的（skillview.attribute_line），
  // 這裡只放進去；標題那四個字待 joy 潤。伺服器沒給（舊版）就不畫。
  const attrNoteHtml = (x) => (x.attribute_note ? `<details class="attr-note"><summary>武學屬性有什麼用</summary><p>${esc(x.attribute_note)}</p></details>` : "");

  // 熔煉的問句（W9、FB-081）：整句由伺服器寫好、放在按鈕的 data-confirm（library.melt_confirm：有心得就寫退回多少，沒有就直說
  // 只空出一格；基礎武學再接一句去哪裡重學，只說一次）。伺服器沒給（舊版）才用這句老問題
  const meltAskText = (el) => el.dataset.confirm || `把【${el.dataset.name}】熔成心得？熔掉就沒了。`;

  // 熔煉與意境化成心得都先問一次，用頁面自己的確認層（ask，管理者工具用的那一個；FB-085）：以前是瀏覽器內建的確認框，
  // 跟其他按鈕不一樣、手機上還會被擋掉。按「熔掉」才送，取消或點旁邊暗處什麼都不送
  function askMelt(el) {
    ask(meltAskText(el), "熔掉", () => mx("melt", { art: el.dataset.id }));
  }
  function askMeltInsight(el) {
    ask(`把「${el.dataset.name}」化成心得？靠它的武學從此不能修練。`, "化成心得", () => mx("melt_insight", { insight: el.dataset.id }));
  }

  // 功法清單的篩選（FB-085）：煉製頁一排四顆（全部／內功／武學／意境）；修練頁用卷軸卡自己的庫篩選（libFilter，也記在 localStorage）。
  // 選擇記在這個瀏覽器的 localStorage（存不了就只在這一頁有效，讀不到就當沒選過）。
  // 排序是伺服器排好的（skillview.art_rows：身上的先，再品質、成、名字），兩頁畫的是同一份，這裡只決定哪些要畫
  const ART_FILTERS = ["全部", "內功", "武學", "意境"];
  const filterKey = (page) => `tx-arts-filter-${page}`;
  function artFilter(page) {
    // 序章的煉製頁（第 4 步要放進爐子的基礎拳腳與剛悟到的意境）一律全列：瀏覽器記著的是上一個角色的篩選，不能把師父點名的藏起來
    if (page === "craft" && pro()) return "全部";
    S.artFilter = S.artFilter || {};
    if (!(page in S.artFilter)) {
      let saved = null;
      try { saved = localStorage.getItem(filterKey(page)); } catch (e) { /* 讀不到就當沒選過 */ }
      S.artFilter[page] = ART_FILTERS.includes(saved) ? saved : "全部";
    }
    return S.artFilter[page];
  }
  function setArtFilter(page, value) {
    if (!ART_FILTERS.includes(value)) return;
    S.artFilter = S.artFilter || {};
    S.artFilter[page] = value;
    try { localStorage.setItem(filterKey(page), value); } catch (e) { /* 存不了就只在這一頁有效 */ }
  }
  // 這一頁現在的篩選下，這一門武學要不要畫（選「意境」時武學一門都不畫）。煉製頁的意境一律畫：它是拿一門武學配一個意境的地方，
  // 「內功」「武學」篩選不把意境整排藏起來（沒有提示會讓人以為意境不見了）；修練頁的庫另有卷軸卡的篩選（libFilter）
  function showArts(page, art) {
    const f = artFilter(page);
    return f === "全部" || f === art.kind;
  }
  // 四顆小鈕排一行，併在煉製頁「功法」那一行標籤裡（第一屏不多一行）
  function filterChips(page) {
    if (page === "craft" && pro()) return ""; // 序章裡沒有篩選可選（artFilter 一律全列），不畫鈕
    const now = artFilter(page);
    return `<span class="fchips" role="group" aria-label="篩選">${ART_FILTERS.map((f) => `<button type="button" class="fchip${f === now ? " on" : ""}" data-act="art-filter" data-page="${page}" data-filter="${f}" aria-pressed="${f === now}">${f}</button>`).join("")}</span>`;
  }

  // ── 修練 ──
  // 卷軸卡版（企劃者 2026-10-06「先用捲軸卡」）：身上的兩門各一張卡，練成、修練直接在卡上按；
  // 功法庫一門一列，點開才攤成同一張卡的內容。武學多（上限 50 門）時庫可以篩選，先只列 LIB_PAGE 門，其餘按「再列 N 門」
  const QUALITY_SEAL = { 下品: ["下", "q1"], 中品: ["中", "q2"], 上品: ["上", "q3"], 絕學: ["絕", "q4"] };
  const LIB_PAGE = 8;
  const LIB_FILTERS = [["all", "全部"], ["武學", "武學"], ["內功", "內功"], ["ready", "可修練"]];
  const seal = (q, big = false) => {
    const [ch, cls] = QUALITY_SEAL[q] || ["？", "q1"];
    return `<span class="qseal ${cls}${big ? " big" : ""}">${ch}</span>`;
  };
  // 合成品質的機率條：伺服器在這一門帶了 forge_odds（[{quality, pct}]，配手上最好的那個意境 forge_with 算的）才畫；沒帶就不畫，不寫死數字
  const forgeOdds = (a) => (Array.isArray(a.forge_odds) && a.forge_odds.length ? `<div class="odds"><span>${a.forge_with ? `配「${esc(a.forge_with)}」煉製會出` : "拿去煉製會出"}</span>${a.forge_odds
    .map((o) => `<b class="${(QUALITY_SEAL[o.quality] || [, "q1"])[1]}" style="flex-grow:${Math.max(1, Number(o.pct) || 0)}">${esc(String(o.quality).slice(0, 1))} ${Number(o.pct) || 0}%</b>`).join("")}</div>` : "");

  // 功法卡、人物卡（伺服器的 Markdown）裡的十成進度「●●●○○○○○○○」換成跟卷軸卡同一種格子（企劃者 10/6：不要圈圈）。
  // 只換剛好十個圈的那一串，換成的是固定的標記，不帶任何伺服器的字
  const tenCells = (html) => String(html || "").replace(/[●○]{10}/g, (run) =>
    `<span class="ten mini" role="img" aria-label="第${[...run].filter((c) => c === "●").length}成">${[...run].map((c) => `<i${c === "●" ? ' class="on"' : ""}></i>`).join("")}</span>`);

  // 療傷鈕（FB-082，卷軸卡的兩行版）：「療傷」加一行內傷與價錢。按不按得下去由伺服器說（x.heal：沒有內傷、銀兩不夠都灰掉，原因放在
  // title 與 aria-label）；價錢是 x.heal_cost（team.heal_cost），網頁不自己算。伺服器沒給 heal（舊版）就照內傷數畫
  function healButton(x, injury) {
    const h = x.heal, hurt = injury >= 1, cost = x.heal_cost || 0;
    const sub = !hurt ? "沒有內傷" : `內傷 ${Math.round(injury)}・銀 ${cost}${h && !h.ok ? " 不夠" : ""}`;
    const why = h && h.why ? ` title="${esc(h.why)}" aria-label="療傷：${esc(h.why)}"` : "";
    return `<button class="btn" data-act="mx" data-op="heal" ${(h ? h.ok : hurt) ? "" : "disabled"}${why}>療傷<small>${esc(sub)}</small></button>`;
  }

  // 庫的篩選記在這個瀏覽器的 localStorage（FB-085）：重新整理、換頁回來還是上次選的；存不了就只在這一頁有效，讀不到就當沒選過
  const LIB_FILTER_KEY = "tx-arts-filter-practice";
  function libFilter() {
    if (!LIB_FILTERS.some(([f]) => f === S.libFilter)) {
      let saved = null;
      try { saved = localStorage.getItem(LIB_FILTER_KEY); } catch (e) { /* 讀不到就當沒選過 */ }
      S.libFilter = LIB_FILTERS.some(([f]) => f === saved) ? saved : "all";
    }
    return S.libFilter;
  }
  function setLibFilter(value) {
    if (!LIB_FILTERS.some(([f]) => f === value)) return;
    S.libFilter = value;
    S.libAll = false; // 換一類，「再列 N 門」從頭算
    try { localStorage.setItem(LIB_FILTER_KEY, value); } catch (e) { /* 存不了就只在這一頁有效 */ }
  }

  function pagePractice() {
    const x = S.menxia;
    if (!x) return '<p class="muted">載入中…</p>';
    const s = S.main.status;
    // 第一個練成絕學的人：替它取正式的名字（武學與成長設計 3.6）。名字是玩家打的，伺服器會驗；表單的字跳脫
    const naming = x.naming ? `<form class="naming" id="name-art">
        <small>你練成了絕學</small>
        <p>你是江湖上第一個把【${esc(x.naming.name)}】練成絕學的人，替它取一個正式的名字（2～6 個字，全服不能重名）。</p>
        <div class="row"><input class="input" name="name" maxlength="6" placeholder="正式的名字"><button class="btn primary small" type="submit">定名</button></div>
      </form>` : "";
    // 卡的本體（身上的卡、庫裡點開的那一列共用）：十成的格子、第幾成、兩顆大鈕、破境丹、機率條、改練／熔煉／詳情。
    // slot 是這一門那一欄的 slot_cards（只有身上的才有）：練成鈕亮不亮、價錢、序章的原因都看它
    const body = (a, slot) => {
      const lg = a.cultivate.legend, ticked = !!(lg && S.legendTick[a.id]);
      const level = Math.max(0, Math.min(10, a.level | 0));
      // 序章指路（T7 走查 W-A）：卡裡哪幾顆鈕發光由伺服器說（a.glow，只有序章裡才有；art_rows 照序章的拒絕算過），網頁不猜。
      // data-glow 的鍵寫成字面（test_content 掃 app.js 對照 models.GLOW_KEYS，內容才叫得動它們）
      const has = (key) => (a.glow || []).includes(key);
      let first;
      if (slot) {
        const why = slot.blocked ? esc(slot.blocked) : slot.maxed ? "已到第十成" : "";
        first = `<button class="btn ${why ? "" : "primary"}" data-act="mx" data-op="practice" data-glow="practice" data-kind="${esc(a.kind)}" ${why ? "disabled" : ""}>${
          why || `練成第${level + 1}成<small>心得 ${slot.price}</small>`}${slot.maxed && !slot.blocked ? "<small>練滿了</small>" : ""}</button>`;
      } else {
        first = `<button class="btn" data-act="switch"${has("switch") ? ' data-glow="switch"' : ""} data-id="${esc(a.id)}">改練這一門<small>換上身，熟練度各自保留</small></button>`;
      }
      // 修練：按得下去時寫機率；按不下去時寫原因（伺服器的那一句）。不寫下一品是哪一品（企劃者 2026-10-06）
      const hot = a.cultivate.ok && !(slot && !slot.maxed && !slot.blocked); // 練成還能按時，練成是主鈕
      const cult = `<button class="btn ${a.cultivate.ok && hot ? "primary" : ""}" data-act="cultivate"${has("cultivate") ? ' data-glow="cultivate"' : ""} data-id="${esc(a.id)}" ${a.cultivate.ok ? "" : "disabled"}>${
        "修練"}<small class="cnote">${esc(ticked ? lg.note : a.cultivate.note)}</small></button>`;
      const info = S.artInfo === a.id;
      // 功法庫的卡：跟身上同一種那門的比較（W6）直接寫在鈕的上面，改練之前看得到，不必先點「詳情」；點開詳情時功法卡裡也有，這裡就不重複
      const compare = !slot && a.compare && !info ? `<p class="cmp">${esc(a.compare)}</p>` : "";
      return `<div class="ten">${Array.from({ length: 10 }, (_, k) => `<i${k < level ? ' class="on"' : ""}></i>`).join("")}</div>
        <div class="lvline"><b>第${level}成</b><span>${esc(a.kind)}・屬${esc(a.attribute)}${a.insight ? `・意境「${esc(a.insight)}」` : ""}</span></div>
        ${compare}
        <div class="acts">${first}${cult}</div>
        ${S.artNote && S.artNote.id === a.id ? `<div class="msg art-result">${S.artNote.html}</div>` : ""}
        ${lg ? `<label class="legend"><input type="checkbox" data-legend="${esc(a.id)}" ${ticked ? "checked" : ""}><span>${esc(lg.label)}</span></label>` : ""}
        ${forgeOdds(a)}
        <div class="more">
          ${a.melt.ok ? "" : `<span class="why">${esc(a.melt.note)}</span>`}
          <button class="linkish" data-act="melt"${has("melt") ? ' data-glow="melt"' : ""} data-id="${esc(a.id)}" data-name="${esc(a.name)}" data-confirm="${esc(a.melt.confirm)}" ${a.melt.ok ? "" : "disabled"} title="${esc(a.melt.note)}">熔煉${a.melt.ok ? `（${/^退回/.test(a.melt.note) ? esc(a.melt.note.replace(/^退回/, "")) : "只空出一格"}）` : ""}</button>
          <button class="linkish" data-act="art-info" data-id="${esc(a.id)}" aria-expanded="${info}">詳情 ${info ? "▴" : "›"}</button>
        </div>
        ${info ? `<div class="art-card">${tenCells(a.card)}</div>` : ""}`;
    };
    // 身上的兩門：目前這一門那一欄若空著，畫一張只有那一句的卡（slot_cards 的 card）
    const worn = KINDS.map((k) => {
      const slot = x.slot_cards.find((c) => c.kind === k) || { learned: false };
      const a = x.owned_arts.find((r) => r.worn && r.kind === k);
      if (!a) return `<div class="acard empty">${slot.card || `你還沒有${esc(k)}。`}</div>`;
      return `<div class="acard ${(QUALITY_SEAL[a.quality] || [, "q1"])[1]}">
        <div class="hd">${seal(a.quality, true)}<div><h3>${esc(a.name)}</h3><div class="sub">${esc(a.quality)}</div></div><span class="worn">身上</span></div>
        ${body(a, slot)}</div>`;
    }).join("");
    // 功法庫：身上以外的。篩選（全部／武學／內功／可修練）與「再列 N 門」只是看的方式，記在 S，輪詢重畫不會跳回去
    // 排序是伺服器排好的（FB-085：身上的先，再品質、成、名字），這裡照順序列；選哪一類記在 localStorage（libFilter）
    const lib = x.owned_arts.filter((a) => !a.worn);
    const pass = (a, f) => f === "all" || (f === "ready" ? a.cultivate.ok : a.kind === f);
    // 篩選鈕只在庫超過 LIB_PAGE 門時才畫（chips）：沒畫鈕就不套記著的篩選——不然庫縮到 8 門以下、或換了新角色（序章的草廬庫只有一兩門），
    // 記在瀏覽器裡的篩選會把武學藏起來、又沒有鈕可以改回來（review-ap3 I1）
    const filter = lib.length > LIB_PAGE ? libFilter() : "all";
    // 展開著的那一門永遠留在清單裡：照「可修練」篩選時，最後一次修練把它修到不能再修（體力不夠、練成絕學）就不合篩選了，
    // 它的結果卻還寫在卡裡、頁面也不該跳走（W7）
    const picked = lib.filter((a) => pass(a, filter) || a.id === S.artOpen);
    const showAll = S.libAll || picked.length <= LIB_PAGE + 2; // 只多一兩門就直接列完，不必多按一次
    const first = picked.slice(0, LIB_PAGE);
    const openArt = picked.find((a) => a.id === S.artOpen);
    const rows = showAll ? picked : openArt && !first.includes(openArt) ? [...first, openArt] : first; // 展開著的那一門排在第 8 門之後時也要看得到
    // 序章指路：收著的這一列發光，要按的是它裡面的改練、修練、熔煉（要先點開它）。哪一列、哪幾個鍵由伺服器說（a.glow，只有序章裡才有；
    // art_rows 照序章的拒絕算過：改練只有師父點名的那一門、修練、熔煉只有按得下去的），網頁不猜（T7 走查 W-A）
    const libRow = (a) => {
      const todo = ["switch", "cultivate", "melt"].filter((key) => (a.glow || []).includes(key)).join(" ");
      const open = S.artOpen === a.id;
      return `<button class="art libr ${open ? "on" : ""}" data-act="art" data-id="${esc(a.id)}"${todo && !open ? ` data-glow="${todo}"` : ""}>${seal(a.quality)}<span class="txt"><b>${esc(a.name)}</b><small>${esc(a.kind)}・屬${esc(a.attribute)}・第${a.level}成${a.insight ? `・「${esc(a.insight)}」` : ""}</small></span></button>
        ${open ? `<div class="art-body ${(QUALITY_SEAL[a.quality] || [, "q1"])[1]}">${body(a, null)}</div>` : ""}`;
    };
    const chips = lib.length > LIB_PAGE ? `<div class="lib-filter">${LIB_FILTERS.map(([f, label]) => {
      const n = lib.filter((a) => pass(a, f)).length;
      return `<button class="${filter === f ? "on" : ""}" data-act="lib-filter" data-filter="${f}">${label} ${n}</button>`;
    }).join("")}</div>` : "";
    // 意境：一顆一顆的籤，點一下攤開模型寫的那句說明與「化成心得」
    const insOpen = x.insights.find((i) => i.id === S.insOpen);
    const insChips = x.insights.map((i) => `<button class="${S.insOpen === i.id ? "on" : ""}" data-act="ins-open" data-id="${esc(i.id)}">${i.own ? glyphSvg(i.glyph, "glyph-mini") : ""}「${esc(i.name)}」<small>屬${esc(i.attribute)}${i.lean !== "無" ? `・${esc(i.lean)}` : ""}</small></button>`).join("");
    // 名冊只有本人一列（還沒有同伴）時跟上面的本人卡重複，不畫（C6）
    const mates = x.roster.length > 1;
    // 兵器（兵器設計 3.6）：身上那把一行、裝備庫每把一行與「換上」鈕。字都是伺服器給的資料，一律 esc
    const wp = x.weapons;
    const weaponRow = (w, wornNow) => `<div class="wrow${w.fits ? "" : " muted"}">
        <b>【${esc(w.name)}】</b><span>${esc(w.kind)}・屬${esc(w.attribute)}・鋒利度 ${w.edge | 0}${w.bonus ? `・威力 ${esc(w.bonus)}` : "・用不上"}</span>
        ${wornNow ? "" : `<button class="btn small" data-act="wield" data-id="${esc(w.id)}">換上</button><button class="btn small ghost" data-act="dismantle" data-id="${esc(w.id)}">拆解</button>`}
      </div>`;
    const weaponsBlock = wp && (wp.worn || wp.rack.length) ? `<section class="weapons"><div class="label">兵器</div>
        ${wp.worn ? weaponRow(wp.worn, true) : '<p class="muted">手上沒有兵器。</p>'}
        ${wp.rack.length ? `<small class="muted">裝備庫 ${wp.rack.length}/${wp.cap | 0}</small>${(S.rackAll || wp.rack.length <= LIB_PAGE ? wp.rack : wp.rack.slice(0, LIB_PAGE)).map((w) => weaponRow(w, false)).join("")}
          ${S.rackAll || wp.rack.length <= LIB_PAGE ? "" : `<button class="btn ghost lib-more" data-act="rack-all">再列 ${wp.rack.length - LIB_PAGE} 件</button>`}` : ""}
        <p class="muted">城裡的鐵匠鋪買得到、修得好；用不上的拆了換素材。</p>
      </section>` : "";
    return `
      ${proGuide()}
      <div class="msg" id="mx-msg">${S.message}</div>
      ${naming}
      <div class="tune">
        ${healButton(x, s.injury)}
        <form id="seclude" class="seclude">
          <button class="btn" type="submit" ${x.seclude_blocked ? "disabled" : ""}>閉關<small>得心得，氣血回復加倍</small></button>
          <select class="input" name="hours" aria-label="閉關幾小時">${[1, 2, 4, 6, 8, 12].map((h) => `<option value="${h}" ${h === 8 ? "selected" : ""}>${h} 小時</option>`).join("")}</select>
        </form>
      </div>
      ${x.seclude_blocked ? `<p class="muted">${esc(x.seclude_blocked)}</p>` : ""}
      ${attrNoteHtml(x)}
      <div class="label">身上的兩門</div>
      ${worn}
      ${weaponsBlock}
      <div class="label">功法庫 <small class="muted">武學與意境 ${x.holdings.count}/${x.holdings.cap}</small></div>
      ${chips}
      ${lib.length ? (picked.length ? `<div class="lib">${rows.map(libRow).join("")}</div>` : '<p class="muted">這一類沒有功法。</p>')
        : '<p class="muted">功法庫是空的。合成出來的武學、學來的武學會放在這裡。</p>'}
      ${showAll ? "" : `<button class="btn ghost lib-more" data-act="lib-all">再列 ${picked.length - LIB_PAGE} 門</button>`}
      <div class="label">意境</div>
      ${x.insights.length ? `<div class="ins">${insChips}</div>
        ${insOpen ? `<div class="insight"><div>${insOpen.own ? glyphSvg(insOpen.glyph, "glyph-big") : ""}<b>「${esc(insOpen.name)}」</b>${insOpen.note ? `<p>${esc(insOpen.note)}</p>` : ""}${insOpen.own ? `<p class="glyph-from">悟於${esc(insOpen.place || "某處")}・只屬於你</p>` : ""}</div>
          <button class="btn small" data-act="melt-insight" data-id="${esc(insOpen.id)}" data-name="${esc(insOpen.name)}" ${insOpen.blocked ? "disabled" : ""}>化成心得 ${insOpen.melt}</button>${insOpen.blocked ? `<small class="muted">${esc(insOpen.blocked)}</small>` : ""}</div>` : ""}`
        : '<p class="muted">還沒悟到任何意境。去探索，荒郊野外最容易有所領悟。</p>'}
      <div class="label">門下</div>
      <details class="fold" open><summary>本人</summary><div class="fold-body">${tenCells(x.player_card)}</div></details>
      ${mates ? `<div class="list">${x.roster.map((r) => `<button class="${x.person === r.key ? "on" : ""}" data-act="person" data-key="${esc(r.key)}">${esc(r.label)}</button>`).join("")}</div>` : ""}
      ${mates && x.person ? `<div class="card">${tenCells(x.person_card)}
        ${x.person === "player" ? '<p class="muted">本人一直都在隊伍裡。</p>' // 本人不能加入、移出（引擎也會擋）
          : x.person.startsWith("follower:") ? "" // 部下（計畫 T5）也不能加入、移出；角色卡已經寫了
          : `<button class="btn ${x.on_team ? "" : "primary"}" data-act="mx" data-op="${x.on_team ? "leave" : "join"}">${x.on_team ? "移出隊伍" : "加入隊伍"}</button>`}</div>` : ""}
      <details class="fold"><summary>修練的規矩</summary><div class="fold-body">${x.rules}</div></details>`;
  }

  // ── 煉製 ──
  const QUALITY_RANK = { 下品: 1, 中品: 2, 上品: 3, 絕學: 3 };
  // 爐裡放的東西 → 送給伺服器的 body（第二門武學放 other_art，設計 12.3）
  function forgeBody() {
    const arts = S.forgeSel.filter((p) => p.type === "art").map((p) => p.id);
    return {
      art: arts[0] ?? null,
      other_art: arts[1] ?? null,
      insights: S.forgeSel.filter((p) => p.type === "ins").map((p) => p.id),
    };
  }
  // 一門武學＋一個意境、兩門武學（合成），或兩個意境（合併）才放得滿
  function forgeReady() {
    const b = forgeBody();
    if (b.other_art !== null) return b.insights.length === 0;
    return (b.art !== null && b.insights.length === 1) || (b.art === null && b.insights.length === 2);
  }
  function pick(type, id) {
    if (S.busy) return; // 開爐等結果的時候（首次取名要等模型）爐子不動
    if (S.forgeSel.length >= 2) { toast("爐裡已經放滿了，點上面的拿出來再換。"); return; }
    if (type === "art" && S.forgeSel.some((p) => p.type === "art" && p.id === id)) return; // 同一門不放兩次（下面那顆 chip 也是灰的）
    const no = pickMark(type, id);
    if (no) { toast(no.why); return; } // 跟爐裡那一樣合不了（伺服器照開爐時的判斷算好的）：說為什麼，不放進去
    if (type === "art") S.forgeSel.unshift({ type, id }); else S.forgeSel.push({ type, id }); // 武學放左邊
    renderPage();
    updateForgeLine();
  }

  // 爐裡只放了一樣時，這一樣能不能放進另一格：伺服器照開爐時同一套判斷算好的（/api/forge_line 的 picks，skillview.forge_picks）。
  // 合不了回 { short, why }，合得了或還沒算好回 null
  function pickMark(type, id) {
    const p = S.forgePicks;
    if (!p || S.forgeSel.length !== 1) return null;
    return (type === "art" ? p.arts : p.insights)[id] || null;
  }
  // 煉製頁的清單篩選（企劃者 2026-10-10「武學數量很多的時候，很難選」）：種類（ART_FILTERS 那四顆）之外再加屬性、品質、排序，
  // 爐裡放了一樣時可以「只看合得了的」。都只記在這一頁（S.craftView），不存瀏覽器
  const CRAFT_SORTS = [["", "依品質"], ["attr", "依屬性"], ["name", "依名字"]];
  // 一次先列幾門，其餘按「再列」
  const CRAFT_PAGE = 12;
  function craftView() {
    S.craftView = S.craftView || { attr: "", quality: "", sort: "", okOnly: false, all: false };
    return S.craftView;
  }
  function craftFilterRow(x) {
    if (pro()) return "";
    const v = craftView();
    const attrs = [...new Set([...x.owned_arts.map((a) => a.attribute), ...x.insights.map((i) => i.attribute)])].sort();
    const quals = [...new Set(x.owned_arts.map((a) => a.quality))].sort((a, b) => (QUALITY_RANK[a] || 1) - (QUALITY_RANK[b] || 1));
    const sel = (key, label, opts) => `<select class="input" data-act="craft-view" data-key="${key}" aria-label="${label}">${opts.map(([val, text]) =>
      `<option value="${esc(val)}"${v[key] === val ? " selected" : ""}>${esc(text)}</option>`).join("")}</select>`;
    const pot = S.forgeSel.length === 1 && S.forgePicks;
    return `<div class="craft-filter">
      ${sel("attr", "屬性", [["", "屬性"], ...attrs.map((a) => [a, `屬${a}`])])}
      ${sel("quality", "品質", [["", "品質"], ...quals.map((q) => [q, q])])}
      ${sel("sort", "排序", CRAFT_SORTS)}
      ${pot ? `<button type="button" class="fchip${v.okOnly ? " on" : ""}" data-act="craft-ok" aria-pressed="${v.okOnly}">只看合得了的</button>` : ""}
    </div>`;
  }
  // 一顆功法：合不了的灰掉、底下寫兩三個字的原因（點了說整句）
  function craftChip(type, thing, sub, rank, extra = "", used = false) {
    const no = !used && pickMark(type, thing.id);
    return `<button class="chip r${rank}${no ? " no" : ""}${used ? " used" : ""}" data-act="pick" data-type="${type}"${used ? "" : extra} data-id="${esc(thing.id)}"${used ? " disabled" : ""}>
          <b>${esc(thing.name)}</b><small>${no ? `<i class="why">${esc(no.short)}</i>` : esc(sub)}</small></button>`;
  }
  function pageCraft() {
    const x = S.menxia;
    if (!x) return '<p class="muted">載入中…</p>';
    // 爐子兩格要畫的：武學寫品質與屬性，意境寫「意境」與屬性（找不到就當空格）
    const slotOf = (p) => {
      if (!p) return null;
      if (p.type === "art") {
        const a = x.owned_arts.find((r) => r.id === p.id);
        return a && { name: a.name, sub: `${a.quality}・${a.attribute}`, rank: QUALITY_RANK[a.quality] || 1 };
      }
      const i = x.insights.find((r) => r.id === p.id);
      return i && { name: i.name, sub: `意境・${i.attribute}`, rank: 2 };
    };
    const inPot = (id) => S.forgeSel.some((p) => p.type === "art" && p.id === id);
    const v = craftView();
    const keep = (type, thing) => (!v.attr || thing.attribute === v.attr) && (!v.okOnly || !pickMark(type, thing.id));
    const order = (list) => v.sort === "name" ? [...list].sort((a, b) => a.name.localeCompare(b.name, "zh-Hant"))
      : v.sort === "attr" ? [...list].sort((a, b) => a.attribute.localeCompare(b.attribute, "zh-Hant")) : list; // 照品質＝伺服器的順序
    const arts = order(x.owned_arts.filter((a) => showArts("craft", a) && keep("art", a) && (!v.quality || a.quality === v.quality)));
    const ins = order(x.insights.filter((i) => keep("ins", i)));
    const artsShown = v.all || pro() ? arts : arts.slice(0, CRAFT_PAGE);
    const ready = forgeReady();
    const result = S.forgeResult ? `<div class="msg forge-result">${S.forgeResult.html}</div>` : "";
    // 「開爐」緊接在說明那一行下面、不黏在底部（FB-048）：黏著時會蓋住底下的清單、開爐後那一行字與「背包」。
    // 開爐的結果就寫在「開爐」底下、爐裡的東西留著（企劃者 2026-10-10「點完又會跳到畫面最上面，要繼續合成還要往下拉」），
    // 頁面不捲：拿掉一格、換一樣就能再合
    return `
      ${proGuide()}
      <div class="msg" id="mx-msg">${S.message}</div>
      ${furnaceSvg([slotOf(S.forgeSel[0]), slotOf(S.forgeSel[1])], ready)}
      <div class="card" id="forge-line">${S.forgeLine || x.forge_line}</div>
      <div class="act-row"><button class="btn primary" id="forge" data-act="forge" data-glow="forge" ${ready ? "" : "disabled"}>開爐</button></div>
      ${result}
      ${attrNoteHtml(x)}
      <div class="label">功法${filterChips("craft")}</div>
      ${craftFilterRow(x)}
      ${artFilter("craft") === "意境" ? "" : `${arts.length ? `<div class="chips">${artsShown.map((a) => craftChip("art", a, `${a.quality}・屬${a.attribute}`, QUALITY_RANK[a.quality] || 1,
        (a.glow || []).includes("pick:art") ? ' data-glow="pick:art"' : "", inPot(a.id))).join("")}</div>` : '<p class="muted">沒有合這些條件的武學。</p>'}
      ${artsShown.length < arts.length ? `<button class="btn ghost lib-more" data-act="craft-all">再列 ${arts.length - artsShown.length} 門</button>` : ""}`}
      <div class="label">意境 <small class="muted">同一個也能放兩次</small></div>
      ${x.insights.length ? (ins.length ? `<div class="chips">${ins.map((i) => craftChip("ins", i, `屬${i.attribute}${i.lean !== "無" ? `・${i.lean}` : ""}`, 2,
        (i.glow || []).includes("pick:insight") && !S.forgeSel.some((p) => p.type === "ins" && p.id === i.id) ? ' data-glow="pick:insight"' : "")).join("")}</div>`
        : '<p class="muted">沒有合這些條件的意境。</p>')
        : '<p class="muted">還沒悟到任何意境。去探索，荒郊野外最容易有所領悟。</p>'}
      ${x.clue_items?.length ? `<div class="label">伏筆物品</div>
      <div class="chips clues">${x.clue_items.map((i) => `<div class="clue"><b>${esc(i.name)}</b><span>×${i.count}</span></div>`).join("")}</div>` : ""}
      ${manualEntry(manualRows())}
      <details class="fold"><summary>背包</summary><div class="fold-body">${x.bag}</div></details>`;
  }

  // 武學譜（status.manual，secret_recipes.view；企劃者 2026-10-10「武學譜能不能獨立一頁，做得更豪華一些」）：
  // 煉製頁上只放一個入口（manualEntry），點了開全螢幕的一本書（bookHtml，S.book，疊在整個畫面上、左上返回）。
  // 一條秘方一頁，聽過的口訣直書大字，合中了蓋一方朱印寫它的名號。只列聽過的那幾句：不寫種類、配方、還差幾句（還沒拿到的線索一律不露）
  function manualRows() { return (S.main && S.main.status && S.main.status.manual) || []; }
  const CN_NUM = "〇一二三四五六七八九十";
  const cnNum = (n) => n <= 10 ? CN_NUM[n] : n < 20 ? `十${CN_NUM[n - 10]}` : `${CN_NUM[Math.floor(n / 10)]}十${n % 10 ? CN_NUM[n % 10] : ""}`;
  // 一卷線裝書（入口與封面共用）：書衣、題簽、四道線
  function bookIcon() {
    return `<svg class="book-icon" viewBox="0 0 48 56" aria-hidden="true"><rect x="4" y="3" width="40" height="50" rx="2" class="bk-cover"/>
    <rect x="22" y="9" width="12" height="32" class="bk-slip"/><path d="M28 13v24" class="bk-slip-ink"/>
    <path d="M10 3v50M4 12h6M4 24h6M4 36h6M4 48h6" class="bk-thread"/></svg>`;
  }
  function manualEntry(rows) {
    const solved = rows.filter((r) => r.solved).length;
    const sub = rows.length ? `收錄口訣 ${rows.length} 則${solved ? `・已參透 ${solved}` : ""}` : "卷中尚無一字";
    return `<button class="manual-entry" data-act="book-open">${bookIcon()}<span><b>武學譜</b><small>${sub}</small></span><i class="go">翻閱 ›</i></button>`;
  }
  // 直書一句一欄：口訣照標點斷開（「日出東嶺，」「一寸一寸爬上峰頂。」），每一段自己起一欄，不在句中折行
  const clauses = (text) => text.split(/(?<=[，。；！？、：])/).filter((t) => t.trim());
  // 朱印：名號照字數排成方印（四字兩行兩列、其餘一直行），字是白的（陰刻）。只有合中了才有
  function sealSvg(name) {
    const chars = [...name].slice(0, 6);
    const n = chars.length;
    const cols = n === 4 ? 2 : n > 4 ? 2 : 1;
    const rows = Math.ceil(n / cols);
    const cell = 40 / Math.max(rows, cols);
    // 直書的方印：右行先讀，由上而下
    const glyphs = chars.map((ch, k) => {
      const col = Math.floor(k / rows), row = k % rows;
      const cx = 46 - (col + 0.5) * (40 / cols);
      const cy = 6 + (row + 0.5) * (40 / rows);
      return `<text x="${cx.toFixed(1)}" y="${cy.toFixed(1)}" font-size="${(cell * 0.86).toFixed(1)}">${esc(ch)}</text>`;
    }).join("");
    return `<svg class="seal" viewBox="0 0 52 52" role="img" aria-label="${esc(name)}"><rect x="2" y="2" width="48" height="48" rx="3" class="seal-bg"/>
      <rect x="5" y="5" width="42" height="42" rx="1.5" class="seal-rim"/><g class="seal-ink">${glyphs}</g></svg>`;
  }
  function bookHtml() {
    const rows = manualRows();
    const solved = rows.filter((r) => r.solved).length;
    const leaves = rows.length ? rows.map((r, k) => `<article class="leaf${r.solved ? " solved" : ""}">
        <header class="leaf-head"><span>第${cnNum(k + 1)}則</span><span class="leaf-state">${r.solved ? "已參透" : "未參透"}</span></header>
        <div class="leaf-text">${r.clues.map((c) => `<p>${clauses(c).map((t) => `<span>${esc(t)}</span>`).join("")}</p>`).join("")}</div>
        <footer class="leaf-foot">${r.solved ? `${sealSvg(r.solved)}<span class="leaf-sign">合出<b>【${esc(r.solved)}】</b></span>` : '<span class="leaf-sign muted">尚待參悟</span>'}</footer>
      </article>`).join("")
      : `<article class="leaf empty"><div class="leaf-text"><p>卷中尚無一字</p></div>
        <p class="leaf-hint">江湖上流傳的老話，有時藏著合成的門道。</p></article>`;
    return `<div class="book-layer" role="dialog" aria-label="武學譜">
      <header class="book-bar"><button class="book-back" data-act="book-close" aria-label="返回">‹ 返回</button><span class="book-bar-title">武學譜</span></header>
      <div class="book-cover">
        <svg class="book-hills" viewBox="0 0 375 120" preserveAspectRatio="none" aria-hidden="true">
          <path class="hill far" d="M0 86 C40 58 70 64 104 46 C134 30 160 52 190 40 C226 26 258 48 292 36 C326 24 352 40 375 34 V120 H0Z"/>
          <path class="hill near" d="M0 104 C36 86 72 96 110 80 C150 64 178 88 222 76 C262 66 300 86 340 74 C356 70 366 72 375 70 V120 H0Z"/>
        </svg>
        <i class="book-moon" aria-hidden="true"></i>
        <div class="book-title"><span>武學譜</span></div>
        <p class="book-sub">本季所聞口訣 ${rows.length} 則${solved ? `・已參透 ${solved} 則` : ""}</p>
      </div>
      <div class="leaves">${leaves}</div>
    </div>`;
  }

  // ── 輿圖 ──
  function pageMap() {
    const m = S.map;
    if (!m) return '<p class="muted">展開輿圖…</p>';
    const toJianghu = !!(m.travel && m.travel.some((t) => t.to_jianghu));
    // 步行／趕路／疾行緊接在地圖下面、不黏在底部（FB-048）：黏著時會蓋住地點詳情「局勢」那一行以下。按了的結果寫在它下面那一行
    // 步行／趕路／疾行緊接在選地點底下、地圖上面：排在地圖下面時落在底部分頁列底下，要捲才按得到（FB-045～052 審查 I2）
    return `
      <div class="card">${m.header}</div>
      <div class="seg">${m.layers.map((l) => `<button class="${m.layer === l.id ? "on" : ""}" data-act="layer" data-layer="${esc(l.id)}">${esc(l.name)}</button>`).join("")}</div>
      <div class="map-tools">
        <select class="input" id="place">${m.places.map((p) => `<option value="${esc(p.id)}" ${p.id === m.selected ? "selected" : ""}>${esc(p.label)}</option>`).join("")}</select>
      </div>
      ${m.travel ? `<div class="travel-row${toJianghu ? " blocked" : ""}">${m.travel.map((t) =>
        `<button class="btn ${t.mode === "walk" && !t.to_jianghu ? "primary" : ""}" data-act="travel" data-mode="${esc(t.mode)}" ${t.enabled ? "" : "disabled"}>${esc(t.label)}</button>`).join("")}${
        // 事件還沒了結擋著路（灰的那顆寫了是哪一則）：旁邊給一顆回江湖頁的按鈕，伺服器的 to_jianghu 說了算（FB-063）
        toJianghu ? '<button class="btn primary" data-act="tab" data-tab="jianghu">回江湖</button>' : ""}</div>` : ""}
      <div class="map-wrap" id="map">${m.svg}${MAP_CTL}${legendHtml(m.legend)}</div>
      <div class="msg">${S.mapNotice || ""}</div>
      <div class="card">${m.detail}</div>`;
  }

  // 地圖框右上角的按鈕（給不會手勢的人，像一般地圖 App）：回到所在地、放大、縮小
  const MAP_CTL = `<div class="map-ctl">
    <button type="button" data-act="map-home" aria-label="回到所在地" title="回到所在地"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="6.5"/><path d="M12 2v4M12 18v4M2 12h4M18 12h4"/></svg></button>
    <button type="button" data-act="map-zoom" data-step="in" aria-label="放大" title="放大"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M12 5v14"/></svg></button>
    <button type="button" data-act="map-zoom" data-step="out" aria-label="縮小" title="縮小"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14"/></svg></button>
  </div>`;

  // ── 輿圖的圖例（企劃者 10/4：放大時也要看得到）──
  // 浮在地圖框左下角的一層 HTML：不畫進 SVG（畫進去會跟著地圖平移、縮放），也不被 applyMapView 的 transform 動到。
  // 內容是伺服器的 m.legend（mapview.legend_data），文字一律 esc；只有 icons[].svg 原樣放進來（引擎用常數畫的圖示，沒有玩家輸入）。
  // 展開或收合是這個瀏覽器自己的選擇，記在 localStorage（存不了就只在這一頁有效）；沒選過時寬螢幕展開、手機寬度收合——
  // 手機的地圖框矮，展開的圖例會蓋掉大半張圖。重畫（輪詢、換圖層、點地點）都從 S.mapLegend 讀，不會把玩家收合的又展開
  const LEGEND_KEY = "tx-map-legend"; // 值是 "open" 或 "shut"
  const LEGEND_OPEN_WIDE = true; // 沒選過時：寬螢幕（PHONE 之外）展開（企劃者確認前的預設；位置與透明度在 style.css 的 .map-legend）
  const LEGEND_OPEN_PHONE = false; // 沒選過時：手機寬度收合
  function legendChoice() {
    try {
      const v = localStorage.getItem(LEGEND_KEY);
      return v === "open" ? true : v === "shut" ? false : null;
    } catch (e) { return null; /* 讀不到就當沒選過 */ }
  }
  function legendOpen() {
    if (S.mapLegend === undefined) S.mapLegend = legendChoice();
    if (S.mapLegend !== null) return S.mapLegend;
    return PHONE && PHONE.matches ? LEGEND_OPEN_PHONE : LEGEND_OPEN_WIDE;
  }
  // 收合鈕在最下面、說明疊在它上面（style.css 的 column-reverse）：展開收合時鈕不跳位置
  function legendHtml(lg) {
    if (!lg) return "";
    const open = legendOpen();
    return `<div class="map-legend${open ? " open" : ""}">
      <button type="button" class="legend-toggle" data-act="legend-toggle" aria-expanded="${open}" aria-controls="map-legend-body"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 15l6-6 6 6"/></svg>圖例</button>
      <div class="legend-body" id="map-legend-body"${open ? "" : " hidden"}>
        <ul class="legend-icons">${lg.icons.map((i) => `<li>${i.svg}<span>${esc(i.label)}</span></li>`).join("")}</ul>
        <p>${esc(lg.states)}</p>
        <p>${esc(lg.ring)}</p>
        ${lg.layer ? `<p>${esc(lg.layer)}</p>` : ""}
        ${lg.strike ? `<p>${esc(lg.strike)}</p>` : ""}
      </div>
    </div>`;
  }
  // 按圖例的鈕：原地展開／收合，不重畫整頁（重畫會把地圖框整個換掉）
  function legendToggle(btn) {
    const open = btn.getAttribute("aria-expanded") !== "true";
    S.mapLegend = open;
    try { localStorage.setItem(LEGEND_KEY, open ? "open" : "shut"); } catch (e) { /* 存不了就只在這一頁有效 */ }
    btn.setAttribute("aria-expanded", String(open));
    const box = btn.closest(".map-legend");
    box.classList.toggle("open", open);
    box.querySelector(".legend-body").hidden = !open;
  }

  // ── 輿圖的視圖（W16）：純數學，不碰 DOM ──
  // 視圖 v = { s 倍率, cx, cy 視窗中心對著的地圖座標 }，地圖座標＝原尺寸的 px。存中心不存位移：視窗寬高變了（轉向、拉視窗）還對得上。
  // vw、vh 是視窗（地圖框）的大小，W、H 是地圖的大小（svg 的 viewBox）。手勢、滾輪、按鈕都走這幾個函式
  const MAP_MAX = 2; // 最多放到原尺寸的兩倍
  const fitScale = (vw, vh, W, H) => Math.min(vw / W, vh / H); // 整張看得完的倍率（也是最小倍率）
  const clampScale = (s, vw, vh, W, H) => Math.min(MAP_MAX, Math.max(fitScale(vw, vh, W, H), s));
  // 夾住：某一軸的地圖比視窗小就置中；比視窗大就不能拖到露出地圖外面
  function clampView(v, vw, vh, W, H) {
    const s = clampScale(v.s, vw, vh, W, H);
    const axis = (c, view, size) => {
      const half = view / 2 / s; // 視窗的一半，換成地圖單位
      return size * s <= view ? size / 2 : Math.min(size - half, Math.max(half, c));
    };
    return { s, cx: axis(v.cx, vw, W), cy: axis(v.cy, vh, H) };
  }
  // 視窗裡 (px, py) 底下的地圖座標；反過來，倍率 s 時要讓地圖座標 m 落在 (px, py)，中心該在哪
  const mapPoint = (v, px, py, vw, vh) => [v.cx + (px - vw / 2) / v.s, v.cy + (py - vh / 2) / v.s];
  const pinView = (s, m, px, py, vw, vh) => ({ s, cx: m[0] - (px - vw / 2) / s, cy: m[1] - (py - vh / 2) / s });
  // 以視窗裡 (px, py) 為準縮放：縮放前後那一點底下的地圖座標不變（碰到地圖邊緣被夾住時例外）
  function zoomAt(v, factor, px, py, vw, vh, W, H) {
    const s = clampScale(v.s * factor, vw, vh, W, H);
    return clampView(pinView(s, mapPoint(v, px, py, vw, vh), px, py, vw, vh), vw, vh, W, H);
  }
  // 地點點擊區的半徑（地圖單位）：螢幕上至少約 22px；上限 34，最近的兩個地點相距 68.6，再大會互相蓋住
  const hitRadius = (s) => Math.min(34, Math.max(22, 22 / s));

  // ── 輿圖的手勢（W16）──
  // 地圖照原本的像素大小放在固定高度的框裡，用 transform 平移、縮放（不改 viewBox：手勢中每一幀重描整張山水，手機會卡）。
  // 一指或滑鼠左鍵拖移、雙指縮放、滾輪縮放；按下到放開都沒移超過 8px、也從沒有第二指，才算點了一下（選地點）。
  // pointermove／up 掛在 document：重畫換掉了地圖框，手勢也接得下去（mapReady 會把指標抓回新的框）
  const TAP_SLOP = 8;
  const grip = { pts: new Map(), tap: null, ref: null, frame: 0 }; // 按著的指標（id → [x, y]）、點一下的候選、起點、排好的那一幀
  const mapHeld = () => grip.pts.size > 0;
  let mapBox = null; // 上次套用時的地圖框大小 [寬, 高]：大小變了而原本是整張，就維持整張
  let glideTimer = 0;

  // 地圖框與地圖的大小、框的內緣在畫面上的位置；地圖還沒畫出來（或框沒有大小）回 null
  function mapGeom(wrap) {
    const svg = wrap && wrap.querySelector(".tx-world-map > svg");
    const vb = svg && svg.viewBox && svg.viewBox.baseVal;
    if (!vb || !vb.width || !vb.height || !wrap.clientWidth || !wrap.clientHeight) return null;
    const r = wrap.getBoundingClientRect();
    return { wrap, svg, vw: wrap.clientWidth, vh: wrap.clientHeight, W: vb.width, H: vb.height, x0: r.left + wrap.clientLeft, y0: r.top + wrap.clientTop };
  }
  const circleAt = (c) => {
    const p = c && [Number(c.getAttribute("cx")), Number(c.getAttribute("cy"))];
    return p && p.every(Number.isFinite) ? p : null;
  };
  // 地點的中心：它那一組裡第一個透明的點擊圓
  const placePoint = (svg, id) => (id ? circleAt(svg.querySelector(`g[data-loc="${CSS.escape(id)}"] > circle[fill-opacity="0"]`)) : null);
  // 所在地：在路上用「你」那個點，否則用所在的地點，都找不到就用地圖中心
  const herePoint = (g) => circleAt(g.svg.querySelector("circle.tx-you")) || placePoint(g.svg, S.map && S.map.here) || [g.W / 2, g.H / 2];

  // 把 S.mapView 夾住、套到地圖上；glide：按鈕、下拉選單的移動滑一下（≤150ms），手勢與滾輪中不滑
  function applyMapView(glide = false, g = mapGeom(document.getElementById("map"))) {
    if (!g || !S.mapView) return;
    const { wrap, vw, vh, W, H } = g;
    // 地圖框大小變了（轉向、拉視窗，也可能是在別的分頁時變的）而原本是整張：維持整張
    if (mapBox && (mapBox[0] !== vw || mapBox[1] !== vh) && S.mapView.s <= fitScale(mapBox[0], mapBox[1], W, H) + 1e-9) {
      S.mapView = { ...S.mapView, s: fitScale(vw, vh, W, H) };
    }
    mapBox = [vw, vh];
    const v = (S.mapView = clampView(S.mapView, vw, vh, W, H));
    clearTimeout(glideTimer);
    wrap.classList.toggle("glide", glide);
    if (glide) glideTimer = setTimeout(() => wrap.classList.remove("glide"), 200);
    g.svg.style.transform = `translate(${vw / 2 - v.cx * v.s}px, ${vh / 2 - v.cy * v.s}px) scale(${v.s})`;
    // 點擊區跟著縮放：透明圓 r=16，外框寬 2×(R−16) 把它撐到半徑 R（style.css 的 --hit）
    const hit = `${Math.round(2 * (hitRadius(v.s) - 16))}px`;
    if (wrap.style.getPropertyValue("--hit") !== hit) wrap.style.setProperty("--hit", hit);
    // 到頂、到底那一顆按不下去（看得出已經到頭了）
    wrap.querySelector('[data-step="in"]').disabled = v.s >= MAP_MAX - 1e-9;
    wrap.querySelector('[data-step="out"]').disabled = v.s <= fitScale(vw, vh, W, H) + 1e-9;
  }

  // 輿圖頁每次畫好（afterPage）：第一次打開就決定視圖，之後照舊套用；掛上這個框自己的監聽
  function mapReady() {
    const wrap = document.getElementById("map");
    if (!wrap) return;
    // 手勢的監聽都掛在捕獲階段：不冒泡的事件（例如測試用 new PointerEvent 送的）也收得到
    wrap.addEventListener("pointerdown", gripDown, true);
    wrap.addEventListener("wheel", mapWheel, { passive: false, capture: true });
    // 舊版 iOS Safari 的捏合手勢、拖到地圖上的字開始原生拖曳，都擋掉
    for (const t of ["gesturestart", "gesturechange", "dragstart"]) wrap.addEventListener(t, (ev) => ev.preventDefault());
    for (const id of grip.pts.keys()) {
      try { wrap.setPointerCapture(id); } catch (e) { /* 那一指已經放開了 */ }
    }
    const g = mapGeom(wrap);
    if (g && !S.mapView) {
      // 這次載入網頁後第一次打開，對準所在地：手機照原尺寸；寬螢幕照框寬（最多原尺寸）。都不給整張——
      // 整張只有約 0.37 倍，地名剩 5px 上下（E2／FB-012），寬螢幕的橫框也一樣
      const phone = !!(PHONE && PHONE.matches);
      const [cx, cy] = herePoint(g);
      S.mapView = { s: phone ? 1 : Math.min(1, g.vw / g.W), cx, cy };
    }
    applyMapView(false, g);
  }

  function gripDown(ev) {
    if (ev.button !== 0 || ev.target.closest(".map-ctl, .map-legend")) return; // 只收滑鼠左鍵、觸控、筆；角落的按鈕與圖例照常按
    if (grip.pts.has(ev.pointerId)) gripEnd(); // 同一個指標又按下：上一次沒收到放開（例如在視窗外放開），重新來過
    if (grip.pts.size >= 2) return; // 第三指不管
    gripFlush();
    const wrap = ev.currentTarget;
    try { wrap.setPointerCapture(ev.pointerId); } catch (e) { /* 合成的事件抓不住；放開照樣由 document 收 */ }
    grip.pts.set(ev.pointerId, [ev.clientX, ev.clientY]);
    grip.tap = grip.pts.size === 1 ? { id: ev.pointerId, x: ev.clientX, y: ev.clientY, target: ev.target } : null;
    wrap.classList.remove("glide");
    wrap.classList.add("grabbing");
    if (!grip.tap) wrap.classList.add("moving");
    gripBase();
  }

  // 指標數變了（按下、放開一指）：從現在的位置與視圖重新記起點。一指記上一幀的位置（拖移）；
  // 兩指記開始時的視圖、兩指距離，以及兩指中點底下的地圖座標（之後要一直跟著中點走）
  function gripBase() {
    const pts = [...grip.pts.values()];
    const g = mapGeom(document.getElementById("map"));
    grip.ref = null;
    if (!g || !S.mapView || !pts.length) return;
    if (pts.length === 1) { grip.ref = { at: pts[0] }; return; }
    const [[ax, ay], [bx, by]] = pts;
    grip.ref = { v: S.mapView, d: Math.max(1, Math.hypot(bx - ax, by - ay)), m: mapPoint(S.mapView, (ax + bx) / 2 - g.x0, (ay + by) / 2 - g.y0, g.vw, g.vh) };
  }

  // 一幀套用一次（同一幀的多次移動合併）
  function gripStep() {
    grip.frame = 0;
    const g = mapGeom(document.getElementById("map"));
    const ref = grip.ref;
    const pts = [...grip.pts.values()];
    if (!g || !ref || !S.mapView) return;
    if (pts.length === 1 && ref.at) {
      // 地圖跟著手指（游標）走
      const [x, y] = pts[0];
      const v = S.mapView;
      S.mapView = clampView({ s: v.s, cx: v.cx - (x - ref.at[0]) / v.s, cy: v.cy - (y - ref.at[1]) / v.s }, g.vw, g.vh, g.W, g.H);
      ref.at = [x, y];
    } else if (pts.length === 2 && ref.m) {
      const [[ax, ay], [bx, by]] = pts;
      const s = clampScale(ref.v.s * Math.hypot(bx - ax, by - ay) / ref.d, g.vw, g.vh, g.W, g.H);
      S.mapView = clampView(pinView(s, ref.m, (ax + bx) / 2 - g.x0, (ay + by) / 2 - g.y0, g.vw, g.vh), g.vw, g.vh, g.W, g.H);
    } else return;
    applyMapView(false, g);
  }
  // 還沒套用的那一幀先套上（指標數要變了、或要放開了）
  function gripFlush() {
    if (!grip.frame) return;
    cancelAnimationFrame(grip.frame);
    gripStep();
  }

  function gripUp(ev) {
    if (!grip.pts.has(ev.pointerId)) return;
    gripFlush();
    grip.pts.delete(ev.pointerId);
    const tap = grip.tap;
    if (grip.pts.size) { grip.tap = null; gripBase(); return; } // 雙指放開一指：剩下那一指接著拖，不算點選
    gripEnd();
    if (ev.type === "pointerup" && tap && tap.id === ev.pointerId) mapPick(tap.target);
  }
  function gripEnd() {
    if (grip.frame) cancelAnimationFrame(grip.frame);
    grip.pts.clear();
    grip.tap = grip.ref = null;
    grip.frame = 0;
    document.getElementById("map")?.classList.remove("grabbing", "moving");
  }

  // 在地圖上點了一下：選那個地點，視圖不動
  async function mapPick(target) {
    const loc = target && target.closest && target.closest("[data-loc]");
    if (!loc) return;
    S.mapNotice = "";
    try { await loadMap(loc.getAttribute("data-loc")); } catch (e) { /* 提示過 */ }
  }

  // 滾輪以游標為準縮放；觸控板雙指捏合在 Chrome／Edge 是帶 ctrlKey 的 wheel，一樣處理（也因此擋掉瀏覽器自己的整頁放大）
  function mapWheel(ev) {
    if (ev.target.closest(".legend-body")) return; // 在圖例上滾：是捲圖例（太矮時它自己會捲）或捲頁面，不縮放地圖
    ev.preventDefault();
    const g = mapGeom(ev.currentTarget);
    if (!g || !S.mapView) return;
    const dy = ev.deltaY * (ev.deltaMode === 1 ? 16 : ev.deltaMode === 2 ? g.vh : 1);
    S.mapView = zoomAt(S.mapView, Math.exp(-dy * 0.0015), ev.clientX - g.x0, ev.clientY - g.y0, g.vw, g.vh, g.W, g.H);
    applyMapView(false, g);
  }

  // 角落的按鈕：以視窗中心縮放 1.5 倍
  function mapZoom(step) {
    const g = mapGeom(document.getElementById("map"));
    if (!g || !S.mapView) return;
    S.mapView = zoomAt(S.mapView, step === "out" ? 1 / 1.5 : 1.5, g.vw / 2, g.vh / 2, g.vw, g.vh, g.W, g.H);
    applyMapView(true, g);
  }
  // 回到所在地：倍率照舊（比原尺寸小就拉到原尺寸），中心移到所在地
  function mapHome() {
    const g = mapGeom(document.getElementById("map"));
    if (!g || !S.mapView) return;
    const [cx, cy] = herePoint(g);
    S.mapView = { s: Math.max(1, S.mapView.s), cx, cy };
    applyMapView(true, g);
  }
  // 下拉選單選了地點：倍率照舊，中心移到那個地點（它可能在視窗外）
  function mapCenterOn(id) {
    const g = mapGeom(document.getElementById("map"));
    const p = g && placePoint(g.svg, id);
    if (!p || !S.mapView) return;
    S.mapView = { ...S.mapView, cx: p[0], cy: p[1] };
    applyMapView(true, g);
  }

  // ── 見聞 ──
  // 第一季的傳聞分四層（傳聞分層設計第二節）：天下大事、陣營軍情、所在大區、個人線索，各一張卡。
  // 標題是伺服器給的字（這裡跳脫），內容是伺服器轉好、跳脫過的 HTML；開關關著時沒有 rumor_layers，照舊畫一整張 rumors
  function rumorLayersHtml(layers) {
    return layers.map((l) => `<div class="card rumor-layer" data-layer="${esc(l.id)}"><h3>${esc(l.title)}</h3>${l.body}</div>`).join("");
  }

  function pageNews() {
    const seg = `<div class="seg">${NEWS.map((n) => `<button class="${S.news === n.id ? "on" : ""}" data-act="news" data-news="${n.id}">${n.name}</button>`).join("")}</div>`;
    const m = S.main;
    let body = "";
    if (S.news === "reports") {
      const r = S.reports;
      if (!r) body = '<p class="muted">載入中…</p>';
      else if (S.reportOpen && r.selected != null) body = `<button class="linkish back" data-act="report-list">‹ 全部戰報</button><div class="card report-detail">${gaugeHtml(r.gauge)}${r.detail}</div>`;
      else if (!r.list.length) body = `<div class="card">${r.detail}</div>`;
      else body = `<div class="list">${r.list.map((x) => `<button data-act="report" data-id="${x.id}">${esc(x.label)}</button>`).join("")}</div>`;
    } else if (S.news === "trends") body = `<div class="card">${m.trends}</div>`;
    else if (S.news === "rumors") body = m.rumor_layers ? rumorLayersHtml(m.rumor_layers) : `<div class="card">${m.rumors}</div>`;
    else if (S.news === "chronicle") body = `<div class="card">${m.chronicle}</div>`;
    else body = `<div class="card">${m.latest || ""}${m.journal || ""}${m.older || ""}${!m.latest && !m.journal ? '<p class="muted">還沒有紀錄。</p>' : ""}</div>`;
    return seg + body;
  }

  // ── 設定抽屜 ──
  function sheetHtml() {
    const s = S.main.status;
    const a = S.admin;
    const opts = (list) => list.map((x) => `<option value="${esc(x.id)}">${esc(x.label)}</option>`).join("");
    // 「匿名行走」那一句是傳聞分層一新寫的說明（待 joy 潤）；測試只比對這一句（tests/test_rumor_layers.py）
    return `
      <div class="sheet-bg" data-act="sheet-close"></div>
      <div class="sheet" role="dialog" aria-label="設定">
        <div class="grip"></div>
        <div class="top-row"><h3 style="flex:1">設定</h3>${S.main.admin ? `<button class="btn small ghost" data-act="to-admin">管理者工具 ↓</button>` : ""}<button class="btn small ghost" data-act="sheet-close">關閉</button></div>
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
        ${S.main.admin ? `
          <section class="admin-zone stack" id="admin-zone" aria-label="管理者工具">
            <h4>管理者工具（只有你看得到）</h4>
            ${a && a.llm_queue ? `<p class="muted">模型佇列：處理中 ${a.llm_queue.running}、在排 ${a.llm_queue.waiting}</p>` : ""}
            <p class="muted">每一項按了都會先問一次才送出；做完會關掉設定、回到江湖頁。</p>
            <div class="row seasons"><button class="btn" data-act="admin" data-op="open_season">開季</button><button class="btn warn" data-act="admin" data-op="end_season">⚠ 立刻收季</button><button class="btn warn" data-act="admin" data-op="next_season">⚠ 開啟下一季</button></div>
            <p class="muted">時間快轉（全服一起快轉，只在測試時用；小時是現實小時，季曆會跳得更多）</p>
            <div class="row">${[1, 8, 24].map((h) => `<button class="btn small" data-act="admin" data-op="fast_forward" data-hours="${h}">+${h} 小時</button>`).join("")}</div>
            <p class="muted">賽季時鐘（停機維護前按「暫停」，開回來按「繼續」；暫停中全服不能行動，畫面照常可看）</p>
            <div class="row">${S.main.paused != null
              ? `<span class="muted">已暫停 ${S.main.paused} 分鐘</span><button class="btn" data-act="admin" data-op="resume_clock">▶ 繼續</button>`
              : `<button class="btn warn" data-act="admin" data-op="pause_clock">⏸ 暫停賽季時鐘</button>`}</div>
            ${a ? `
              <p class="muted">觸發（人少、大勢推不到門檻時用；效果跟自然發生一樣）</p>
              <div class="row ad-row"><span class="ad-tag">決戰</span><select class="input" id="ad-battle" aria-label="決戰">${opts(a.battles)}</select><button class="btn small" data-act="admin" data-op="start_battle">立刻開戰</button></div>
              <div class="row ad-row"><span class="ad-tag">事件</span><select class="input" id="ad-fire" aria-label="事件">${opts(a.events)}</select><button class="btn small" data-act="admin" data-op="fire">觸發</button></div>
              <div class="row ad-row"><span class="ad-tag">大勢</span><select class="input" id="ad-trend" aria-label="大勢">${opts(a.trends)}</select><input class="input" id="ad-amount" type="number" value="10" aria-label="推動量" style="max-width:76px"><button class="btn small" data-act="admin" data-op="push_trend">推動</button></div>
              ${a.season_one ? `
                <p class="muted">每週的事（照週一的做法立刻再做一次；下週一照常）</p>
                <div class="row wrap"><button class="btn small" data-act="admin" data-op="issue_orders">立刻發本週軍令</button><button class="btn small" data-act="admin" data-op="rotate_seats">立刻輪替第 4 階席次</button></div>` : ""}
              ${a.showdowns && a.showdowns.length ? `
                <p class="muted">三場大戲（照時刻表開集結；開過就算這一場開過了，排定的時間到了不會再開）</p>
                ${a.showdowns.map((s) => `<div class="row ad-row"><span class="ad-tag">${esc(s.label)}</span>${s.note ? `<span class="muted ad-note">${esc(s.note)}</span>` : ""}<button class="btn small" data-act="admin" data-op="start_showdown" data-id="${esc(s.id)}"${s.enabled ? "" : " disabled"}>立刻開這一場</button></div>`).join("")}` : ""}
              ${a.season_one ? `
                <p class="muted">玩家個人劇情（填名號查一次，再挑要給他的；效果跟自然發生一樣）</p>
                <form id="ad-player-form"><div class="row"><input class="input" name="name" placeholder="名號" aria-label="玩家名號" value="${esc(S.adPlayerName || "")}"><button class="btn small" type="submit">查</button></div><p class="form-msg" role="alert">${esc((S.adPlayer && S.adPlayer.refusal) || "")}</p></form>
                ${S.adPlayer && !S.adPlayer.refusal ? adminPlayerHtml(S.adPlayer) : ""}` : ""}
              ${a.timetable.length ? timetableHtml(a) : ""}
              <p class="muted">救場</p>
              <div class="row ad-row"><span class="ad-tag">戰況</span><select class="input" id="ad-front" aria-label="定戰況的線">${opts(a.trends)}</select><input class="input" id="ad-value" type="number" value="50" min="0" max="100" aria-label="戰況" style="max-width:76px"><button class="btn small" data-act="admin" data-op="set_trend">定戰況</button></div>
              ${a.results.length ? `<div class="row ad-row"><span class="ad-tag">結果</span><select class="input" id="ad-result" aria-label="定結果">${a.results.map((x) => `<option value="${esc(x.value)}">${esc(x.label)}</option>`).join("")}</select><button class="btn small" data-act="admin" data-op="resolve_event">定結果</button></div>` : ""}
              ${a.locks.length ? `<div class="row ad-row"><span class="ad-tag">鎖定</span><select class="input" id="ad-lock" aria-label="清鎖定">${opts(a.locks)}</select><button class="btn small" data-act="admin" data-op="clear_lock">清鎖定</button></div>` : ""}
              <div class="row"><button class="btn warn" data-act="admin" data-op="cancel_battle">⚠ 取消決戰</button></div>
              <p class="muted">重設密碼（朋友忘記密碼時用；臨時密碼私下告訴他）</p>
              <form id="reset-form"><div class="row"><input class="input" name="target" placeholder="帳號或名號"><input class="input" name="temp" placeholder="臨時密碼"><button class="btn small" type="submit">重設</button></div><p class="form-msg" role="alert"></p></form>` : ""}
          </section>` : ""}
      </div>`;
  }

  // 管理者區「玩家個人劇情」查到的那個人（/api/admin/player，Game.admin_player_choices）：他是誰、召見（發不了的灰掉、寫為什麼）、
  // 能給他的機緣與伏筆片段（沒有就寫一句）。按了照舊先問一次，送的是查到的那個名號（不是欄位裡後來改過的字）
  function adminPlayerHtml(p) {
    const opts = (list) => list.map((x) => `<option value="${esc(x.id)}">${esc(x.label)}</option>`).join("");
    return `
      <p class="muted">${esc(p.line)}</p>
      <div class="row ad-row"><span class="ad-tag">召見</span><span class="muted ad-note">${esc(p.summons.note)}</span><button class="btn small" data-act="admin" data-op="summon"${p.summons.ok ? "" : " disabled"}>立刻替他發召見</button></div>
      <div class="row ad-row"><span class="ad-tag">機緣</span>${p.opportunities.length
        ? `<select class="input" id="ad-opp" aria-label="給他的機緣">${opts(p.opportunities)}</select><button class="btn small" data-act="admin" data-op="give_opportunity">給他</button>`
        : '<span class="muted ad-note">沒有能給他的機緣</span>'}</div>
      <div class="row ad-row"><span class="ad-tag">伏筆</span>${p.fragments.length
        ? `<select class="input" id="ad-frag" aria-label="給他的伏筆片段">${opts(p.fragments)}</select><button class="btn small" data-act="admin" data-op="give_fragment">給他</button>`
        : '<span class="muted ad-note">沒有能給他的伏筆片段</span>'}</div>`;
  }

  // 設定頁的「時刻表」（計畫 T10）：十二件照順序、標狀態；三場決戰與季末還沒結算的有日期時間欄位與「排定」
  // （欄位是這台裝置的當地時間，送出時換成秒數）；最後是「跳到下一件大事」
  function localInput(sec) {
    const d = new Date(sec * 1000);
    const p = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
  }
  function timetableHtml(a) {
    return `
      <p class="muted">時刻表（三場大戲與季末可以排時間，時間欄是現實時間；時間到了自動開集結，季末就是收季）</p>
      <div class="tt-list">${a.timetable.map((r) => `
        <div class="tt-row">
          <div class="tt-head"><span class="tt-name">${esc(r.label)}</span><span class="tt-state">${esc(r.result ? `${r.state_text}・${r.result}` : r.state_text)}</span></div>
          ${r.schedulable ? `<div class="tt-real">現實時間（這台裝置的當地時間）</div><div class="row"><input class="input" type="datetime-local" id="tt-at-${esc(r.id)}" value="${localInput(r.at_real)}" aria-label="${esc(r.label)}的時間"><button class="btn small" data-act="admin" data-op="schedule" data-id="${esc(r.id)}">排定</button></div>` : ""}
        </div>`).join("")}</div>
      <div class="row"><button class="btn" data-act="admin" data-op="jump_next">跳到下一件大事</button></div>`;
  }

  // 管理者動作的確認框（G3）：每一項按了都先問一次、問句說出後果。疊在設定抽屜上面、不重畫抽屜，
  // 選好的下拉選單、填好的重設密碼欄位都留著；按「取消」或旁邊的暗處就關掉，什麼都不送
  let askGo = null;
  function ask(text, yes, go) {
    closeAsk();
    askGo = go;
    document.body.insertAdjacentHTML("beforeend", `
      <div class="ask-layer">
        <div class="ask-bg" data-act="ask-no"></div>
        <div class="ask" role="alertdialog" aria-modal="true" aria-labelledby="ask-text">
          <p id="ask-text">${esc(text)}</p>
          <div class="row"><button class="btn" data-act="ask-no">取消</button><button class="btn danger" data-act="ask-yes">${esc(yes)}</button></div>
        </div>
      </div>`);
    document.querySelector('.ask [data-act="ask-no"]').focus();
  }
  function closeAsk() {
    document.querySelector(".ask-layer")?.remove();
    askGo = null;
  }

  // 管理者動作的問句與確認鈕（照抽屜裡選好的下拉選單）
  function adminAsk(op, body) {
    const picked = (id) => { const el = document.getElementById(id); return el && el.selectedIndex >= 0 ? el.options[el.selectedIndex].text : ""; };
    const amount = `${body.amount >= 0 ? "+" : ""}${body.amount}`;
    return {
      open_season: ["開季：賽季從籌備中正式開始，全服玩家都能行動了。記得排三場大戲與季末的時間（預設在第 6、9、11 週中、第 12 週末），確定？", "確定開季"],
      // 照 Game.admin_end_season 實際做的事寫（只在進行中有效）
      end_season: ["立刻收季：這一季馬上結束、算出結局與武學榜，全服進入休季（之後再按「開啟下一季」）；沒打完的決戰直接收掉、不算結果，確定？", "確定收季"],
      // 照 SqliteWorldStore.next_season 實際做的事寫（只在休季有效）
      next_season: [`開啟下一季（休季才有效）：新的一季立刻開始，同伴全部重獲自由、武學與意境的名字全部釋出（絕學定的名也是）、合成與合併的配方清空、天機 +1，沒打完的決戰清掉。${
        S.admin && S.admin.next_has_timetable ? "記得排三場大戲與季末的時間（預設在第 6、9、11 週中、第 12 週末）。" : ""}確定？`, "確定開啟下一季"],  // FB-050
      fast_forward: [`時間快轉現實 ${body.hours} 小時的份（全服一起，季曆會跳得更多），確定？`, `快轉 ${body.hours} 小時`],
      // 公告停機時賽季時鐘暫停（Game.admin_pause_clock／admin_resume_clock）；問句待 S1／joy 潤
      pause_clock: ["暫停賽季時鐘（停機維護前按）：季的時間不走、決戰不推，全服暫時不能行動，畫面照常可看；做完記得按「繼續」，確定？", "確定暫停"],
      resume_clock: ["讓賽季時鐘繼續走：停的這一段照整個季曆鐘頭往下取整，扣掉的不算進賽季、季末往後延一樣長；停不到一個季曆鐘頭的話什麼都不扣、季末不動；排好的決戰照原本的時間開，時間在暫停裡過了的馬上開始集結，確定？", "確定繼續"],  // 待 joy 潤；跟 world.resume_skip_text 說的一致
      start_battle: [`立刻開戰「${picked("ad-battle")}」：全服一起進入集結，確定？`, "確定開戰"],
      fire: [`觸發「${picked("ad-fire")}」：效果跟自然發生一樣，全服都受影響，確定？`, "確定觸發"],
      push_trend: [`推動大勢「${picked("ad-trend")}」${amount}：全服一起，確定？`, "確定推動"],
      // 時刻表與救場（計畫 T10）
      schedule: [`把「${body.title}」排在現實 ${body.when}：時間到了自動開集結（季末就是收季），確定？`, "確定排定"],
      jump_next: ["跳到下一件大事：全服的季時間一起往前推，到了的大事立刻結算（決戰直接開集結），確定？", "確定跳過去"],
      set_trend: [`把「${picked("ad-front")}」定成 ${body.value}：全服一起，推過門檻照常觸發，確定？`, "確定定戰況"],
      resolve_event: [`定下「${picked("ad-result")}」：照時刻表結算、全服公告，之後不再擲骰，確定？`, "確定定結果"],
      clear_lock: [`清掉「${picked("ad-lock")}」的鎖定：結算時照沒人鎖定擲骰，確定？`, "確定清掉"],
      cancel_battle: ["取消正在集結或開打的決戰：不算勝負，參戰者都會收到通知；時刻表的決戰不會自己再開，要用「定結果」收尾，確定？", "確定取消"],
      // 管理者觸發鈕（企劃者 2026-10-07）：照 Game.admin_issue_orders／admin_rotate_seats 實際做的事寫
      issue_orders: ["立刻發本週軍令：這一週還沒達成的軍令照週一的做法重挑、換掉（它們的進度不算了），各陣營發一則軍情；已經達成的照舊留著、不會再達成一次；下週一照常發令，確定？", "確定重發"],
      rotate_seats: ["立刻輪替第 4 階席次：照上一週的貢獻重排各陣營在任的人、發一則名單軍情；下週一照常再排，確定？", "確定輪替"],
      start_showdown: [`立刻開「${body.title}」：照時刻表開集結（起點照此刻的戰況），這一場算開過了，排定的時間到了不會再開，確定？`, "確定開戰"],
      summon: [`立刻替 ${body.name} 發召見（${(S.adPlayer && S.adPlayer.summons && S.adPlayer.summons.note) || "下一階"}；不看貢獻與機緣的門檻，其餘照自然發召見的做法），確定？`, "確定發召見"],
      // 情誼型多一句（伺服器算好的 note：情誼補到幾、招募成算、其他話題、換季帶幾成，審查 M-5）
      give_opportunity: [`給 ${body.name} 機緣「${picked("ad-opp")}」：放到這個機緣自然送上門之後的樣子，下一步他就做得了。${
        body.note ? `${body.note}。` : ""}確定？`, "確定給他"],
      give_fragment: [`給 ${body.name} 伏筆片段「${picked("ad-frag")}」：跟自然聽到一樣，記進他的個人線索，確定？`, "確定給他"],
    }[op] || ["確定要這麼做？", "確定"];
  }

  // 確認過的管理者動作：做完關掉抽屜、回到江湖頁看結果，結果照舊用提示泡泡講（G4）。
  // 請求本身沒成（連不上、伺服器出錯）就留在抽屜裡，api() 已經提示過原因
  async function adminDo(op, body) {
    await busy(async () => {
      const r = await api(`/api/do/${op}`, body);
      S.sheet = false;
      setMain(r.main);
      await goTab("jianghu");
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      toast(text || "已完成。");
    });
  }

  // ── 載入各頁 ──
  async function loadMenxia() {
    S.menxia = await api(`/api/menxia${S.person ? `?person=${encodeURIComponent(S.person)}` : ""}`);
    trimPot();
    if (S.tab === "practice" || S.tab === "craft") renderPage();
    if (S.tab === "craft" && S.forgeSel.length) updateForgeLine(); // 爐裡那一樣的標記
  }

  async function loadMap(place) {
    const q = new URLSearchParams({ layer: S.layer });
    if (place) q.set("place", place);
    S.map = await api(`/api/map?${q}`);
    S.layer = S.map.layer;
    if (S.tab === "map") renderPage();
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

  async function loadReports(id) {
    S.reports = await api(`/api/reports${id != null ? `?id=${id}` : ""}`);
    if (S.tab === "news") renderPage();
  }

  async function goTab(tab) {
    S.tab = tab;
    S.message = "";
    S.artOpen = null;
    S.artInfo = null; S.insOpen = null; S.libAll = false; S.rackAll = false; // 攤開的詳情、意境、列完的庫也收起（篩選留著）
    S.artNote = null;
    S.legendTick = {}; // 破境丹的勾也一起收：回到修練頁時它是真的沒勾（預設不勾）
    S.forgeResult = null; // 上一爐的結果也收起（篩選留著）
    S.book = false; // 武學譜是疊在煉製頁上的一本書：換分頁就闔上
    S.mapNotice = "";
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
        // 打開輿圖本身可能完成新手引導的一步，所以先當一個動作做
        const r = await api("/api/do/view_map", {});
        setMain(r.main);
        renderTop();
        await loadMap(null);
      }
      if (tab === "news" && S.news === "reports") await loadReports(null);
    } catch (e) { /* api() 已經提示過 */ }
  }

  // ── 動作 ──
  async function busy(fn) {
    if (S.busy) return;
    S.busy = true;
    try { await fn(); } catch (e) { /* api() 已經提示過 */ } finally { S.busy = false; lastAction = Date.now(); }
  }

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

  // 感悟悟來的意境畫的那一筆（0～100 的點位）畫成小 SVG（同 journal.glyph_svg）
  function glyphSvg(points, cls) {
    const pts = (points || []).filter((p) => Array.isArray(p) && p.length >= 2);
    if (pts.length < 2) return "";
    const path = pts.map(([x, y]) => `${Number(x) | 0},${Number(y) | 0}`).join(" ");
    return `<svg class="${cls}" viewBox="-8 -8 116 116" aria-hidden="true"><polyline points="${path}" fill="none" stroke="currentColor" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
  }

  // ── 有所感的畫布（悟意境設計 0.2 第 3、4 步）──
  // 一筆畫到底：手指按下去開始一筆（之前畫的清掉），離開畫布就算畫完；不滿意清掉重畫。畫完問伺服器這一筆讀不讀得出來
  // （/api/sense_read，跟送出時讀的是同一套 glyph.read），畫布底下只寫成不成，不寫筆畫的幾何。送出帶點位與一張小 PNG（只轉交給模型看圖，不存）
  const SENSE_SIZE = 256;
  function sensePadHtml() {
    const ready = S.sensePts.length > 1;
    return `<div class="sense-pad" id="sense-pad">
        <div class="sense-hint">此刻心中有一個形——用手指一筆畫下來。</div>
        <canvas class="sense-canvas" id="sense-canvas" width="${SENSE_SIZE}" height="${SENSE_SIZE}" aria-label="畫布：一筆畫到底"></canvas>
        <div class="sense-note" id="sense-note">${esc(S.senseNote || (ready ? "" : "手指離開畫布，就算畫完。"))}</div>
        <div class="sense-acts">
          <button class="btn small" data-act="sense-clear" ${ready ? "" : "disabled"}>清掉重畫</button>
          <button class="btn primary small" data-act="sense-send" ${ready ? "" : "disabled"}>就是這個形</button>
        </div>
      </div>`;
  }

  function closeSense() {
    S.sensing = false;
    S.sensePts = [];
    S.senseNote = "";
    S.stroking = false;
  }

  function senseInk(ctx) {
    ctx.clearRect(0, 0, SENSE_SIZE, SENSE_SIZE);
    ctx.lineWidth = 7;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue("--ink").trim() || "#222";
    const pts = S.sensePts;
    if (pts.length < 2) return;
    ctx.beginPath();
    ctx.moveTo(pts[0][0], pts[0][1]);
    for (const [x, y] of pts.slice(1)) ctx.lineTo(x, y);
    ctx.stroke();
  }

  function sensePadReady() {
    const canvas = document.getElementById("sense-canvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    senseInk(ctx);
    let t0 = 0;
    const at = (ev) => {
      const r = canvas.getBoundingClientRect();
      return [
        Math.round(((ev.clientX - r.left) / r.width) * SENSE_SIZE),
        Math.round(((ev.clientY - r.top) / r.height) * SENSE_SIZE),
        Math.round(performance.now() - t0),
      ];
    };
    canvas.addEventListener("pointerdown", (ev) => {
      if (S.busy) return;
      ev.preventDefault();
      canvas.setPointerCapture(ev.pointerId);
      t0 = performance.now();
      S.stroking = true;
      S.sensePts = [at(ev)];
      S.senseNote = "";
      senseInk(ctx);
    });
    canvas.addEventListener("pointermove", (ev) => {
      if (!S.stroking) return;
      ev.preventDefault();
      if (S.sensePts.length < 600) S.sensePts.push(at(ev)); // 跟 glyph.MAX_POINTS 一樣多
      senseInk(ctx);
    });
    const end = async () => {
      if (!S.stroking) return;
      S.stroking = false;
      const pad = document.getElementById("sense-pad");
      const ready = S.sensePts.length > 1;
      if (pad) pad.querySelectorAll('[data-act="sense-clear"], [data-act="sense-send"]').forEach((b) => { b.disabled = !ready; });
      const pts = S.sensePts;
      try {
        const r = await api("/api/sense_read", { points: pts });
        if (S.sensePts !== pts) return; // 等回應時又畫了一筆
        S.senseNote = r.ok ? "心中的形已經落下。" : (r.problem || ""); // 不寫筆畫讀到什麼（企劃者 2026-10-06：留住驚喜）
      } catch (e) { S.senseNote = ""; }
      const note = document.getElementById("sense-note");
      if (note) note.textContent = S.senseNote;
    };
    canvas.addEventListener("pointerup", end);
    canvas.addEventListener("pointercancel", end);
  }

  async function senseSend() {
    const canvas = document.getElementById("sense-canvas");
    const pad = document.getElementById("sense-pad");
    if (!canvas || S.sensePts.length < 2) return;
    // 小 PNG：白底黑線（模型看圖用），跟畫面上的顏色無關
    const small = document.createElement("canvas");
    small.width = small.height = SENSE_SIZE;
    const sx = small.getContext("2d");
    sx.fillStyle = "#fff";
    sx.fillRect(0, 0, SENSE_SIZE, SENSE_SIZE);
    sx.lineWidth = 7;
    sx.lineCap = sx.lineJoin = "round";
    sx.strokeStyle = "#000";
    sx.beginPath();
    S.sensePts.forEach(([x, y], i) => (i ? sx.lineTo(x, y) : sx.moveTo(x, y)));
    sx.stroke();
    const png = small.toDataURL("image/png").split(",")[1] || "";
    await busy(async () => {
      pad.classList.add("brewing"); // 等模型取名：整塊畫布微微晃（同煉製的爐子）
      pad.querySelectorAll("button").forEach((b) => { b.disabled = true; });
      const send = pad.querySelector('[data-act="sense-send"]');
      send.textContent = "心念漸凝……";
      const stop = watchQueue(send, "心念漸凝……");
      try {
        const r = await api("/api/sense", { points: S.sensePts, png });
        closeSense();
        applyMain(r.main);
        window.scrollTo({ top: 0, behavior: "smooth" });
      } finally { stop(); }
    });
    if (document.querySelector("#sense-pad.brewing")) renderPage(); // 失敗了（伺服器擋下來、連不上）：畫布還原，那一筆留著
  }

  async function choose(btn, id, sure = false) {
    // 按下去之前要先問一次的選項（伺服器寫在 confirm，FB-095：必敗的遊歷）：問過、按了「照打」才送。問的當下輪詢可能重畫了頁面，
    // btn 已經不在頁面上：照 id 重找畫面上那一顆，「處理中」才標得到、擋下來時才還原得了（整合審查 M1）
    const ask0 = ((S.main && S.main.options) || []).find((o) => o.id === id);
    if (!sure && ask0 && ask0.confirm) {
      ask(ask0.confirm, "照打", () => choose(document.querySelector(`[data-act="choose"][data-id="${CSS.escape(id)}"]`) || btn, id, true));
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
    if (id === SAY_OPTION) { // 自己說：先叫出輸入框，寫好再送（見 sayLine）
      S.saying = true;
      renderPage();
      const input = document.querySelector("#say-form .input");
      if (input) input.focus();
      return;
    }
    await busy(async () => {
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
        const r = await api("/api/choose", { id });
        S.answering = false;
        S.saying = false;
        S.wheelSel = null; // 收起展開的移動
        applyMain(r.main);
        window.scrollTo({ top: 0, behavior: "smooth" });
        // 決戰選項（加入、趕到、出招）伺服器會回一句 message；大場面等模型判讀的時候選項沒了（人被別的分頁帶走），
        // 那一仗沒打成、不寫江湖紀錄，也只有這一句；一般選項的話在江湖紀錄裡，不回
        const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
        // 這一送剛好結算了回合時，回話是整段回合敘事（場景裡的戰況就是同一段）：提示只放得下幾秒，截短、指去場景
        if (text) toast(text.length > 40 ? `${text.slice(0, 40)}……（戰況見場景）` : text);
      } finally { stop(); }
    });
    // 失敗了（伺服器擋下來、連不上）：把按鈕還原。選單上的按鈕與閒著時行動列的格子（.act-ink：交友、求見、遊歷）都會標 busy、
    // 換上「對方沉吟中…」「兩人對峙……」，兩種都要還原（審查 I2）
    if (document.querySelector(".options .btn.busy, .act-ink.busy")) renderPage();
  }

  // 自己說：送出後要等人物答話（跟按選項一樣十來秒），按鈕先寫「對方沉吟中…」；排在佇列後面時補「前面還有 N 件」
  async function sayLine(form, text) {
    await busy(async () => {
      form.querySelectorAll("input, button").forEach((el) => { el.disabled = true; });
      const submitBtn = form.querySelector("[type=submit]");
      submitBtn.textContent = "對方沉吟中…";
      const stop = watchQueue(submitBtn, "對方沉吟中…");
      try {
        const r = await api("/api/say", { text });
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

  // 換走法：帶著新的走法重抓一次江湖畫面，「前往」的時間、體力與按不按得下去才會跟著換
  async function setMoveMode(mode) {
    if (mode === S.moveMode || S.busy) return;
    const before = S.moveMode;
    await busy(async () => {
      S.moveMode = mode;
      try {
        setMain(await api("/api/main"));
      } catch (e) {
        S.moveMode = before; // 沒拿到新走法的選單：留在原本的走法，切換鈕才跟按鈕上的字對得上
        throw e;
      }
      renderTop();
    });
    if (S.tab === "jianghu") renderPage();
  }

  // 修練（cultivate）不捲回頁首（W7）：反覆修練時，那一門的卡片留著、頁面留在原地，結果寫在那一門卡片裡、按鈕的底下（S.artNote），
  // 頁首的訊息照舊也有。重畫整頁會讓頁首的訊息與卡片的高度變動、把按鈕推走，所以重畫前記下「修練」鈕在螢幕上的位置，
  // 畫完捲回去補差——玩家的拇指底下永遠還是那顆鈕。例外：這一次練成了絕學、要定名——定名的表單在頁首，照舊捲上去；
  // 這一次做完了引導的一步（師父的下一句在頁首），也捲上去；改練、熔煉、練成、療傷會改變清單的結構，也照舊回頁首。
  function cultivateTop(id) {
    const btn = [...document.querySelectorAll('[data-act="cultivate"]')].find((el) => el.dataset.id === id);
    return btn ? btn.getBoundingClientRect().top : null;
  }

  async function mx(op, extra = {}) {
    await busy(async () => {
      const stay = op === "cultivate" && !!extra.art;
      const was = S.menxia, mark = stay ? cultivateTop(extra.art) : null;
      const step = guideKey(S.main && S.main.guide);
      const r = await api(`/api/menxia/${op}`, { person: S.person, kind: S.kind, ...extra });
      S.menxia = r.menxia;
      trimPot(); // 熔掉的若正放在爐裡，回煉製頁時不能還留著
      S.message = r.message;
      S.artNote = stay ? { id: extra.art, html: r.message } : null;
      setMain(r.main);
      renderTop();
      renderPage();
      const needsName = !!(r.menxia && r.menxia.naming) && !(was && was.naming);
      // 這一次修練做完了引導的一步（說書人的 key 換了、或框沒了）：師父的下一句在修練頁最上面（序章 p6→p7 「按打坐歇一歇」），
      // 不捲上去玩家看不到。比的是步驟，不特別認序章，所以以後任何被修練做完的引導步驟都一樣
      const guideMoved = guideKey(r.main && r.main.guide) !== step;
      const now = stay && !needsName && !guideMoved && mark !== null ? cultivateTop(extra.art) : null;
      if (now === null) window.scrollTo({ top: 0, behavior: "smooth" });
      else if (now !== mark) window.scrollBy({ top: now - mark, left: 0, behavior: "instant" });
    });
  }

  async function doMain(op, body = {}) {
    await busy(async () => {
      const r = await api(`/api/do/${op}`, body);
      applyMain(r.main);
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      if (text) toast(text);
    });
  }

  // 放東西、輪詢都會問說明，回應可能晚到：只用最後一次請求的回應，而且爐子要還是問的那一爐
  let forgeLineSeq = 0;
  async function updateForgeLine() {
    const seq = ++forgeLineSeq;
    const pot = JSON.stringify(S.forgeSel);
    try {
      const r = await api("/api/forge_line", forgeBody());
      if (seq !== forgeLineSeq || pot !== JSON.stringify(S.forgeSel)) return;
      S.forgeLine = r.line;
      const drawn = JSON.stringify(S.forgePicks);
      S.forgePicks = r.picks || null;
      if (S.tab === "craft" && JSON.stringify(S.forgePicks) !== drawn) { keepPlace(() => renderPage()); return; } // 清單上「合不了」的標記變了
      const el = document.getElementById("forge-line");
      if (el) el.innerHTML = r.line;
    } catch (e) { /* 提示過 */ }
  }

  // 開爐等結果的時候頁面上方寫的那一句（W10，待 joy 潤）：取名實際約 3～5 秒，不把等待說成好幾十秒，免得人以為壞了
  const FORGE_WAIT = "爐火正旺。若這是江湖上第一次合出來，要等它取名，請稍候。";

  // 重畫時畫面不跳：記下 anchor（預設是第一個看得到的「開爐」或點子清單）在螢幕上的位置，畫完捲回同一個位置
  function keepPlace(draw, anchor) {
    const sel = anchor || "#forge";
    const before = document.querySelector(sel)?.getBoundingClientRect().top;
    draw();
    const after = document.querySelector(sel)?.getBoundingClientRect().top;
    if (before !== undefined && after !== undefined && after !== before) window.scrollBy({ top: after - before, left: 0, behavior: "instant" });
  }

  // 開爐：結果寫在「開爐」底下，頁面不捲；爐裡的東西留著，拿掉一格換一樣就能再合（企劃者 2026-10-10）
  async function forge() {
    const btn = document.getElementById("forge");
    const step = guideKey(S.main && S.main.guide);
    let guideMoved = false;
    await busy(async () => {
      btn.disabled = true;
      btn.textContent = "爐火正旺…";
      btn.classList.add("forging");
      // 等結果的這段時間（首次發現的配方要等模型取名）整座爐子晃動、火舌竄高、太極快轉
      document.querySelector(".furnace .w-furnace")?.classList.add("forging");
      document.querySelector(".furnace .w-taichi")?.classList.add("hot");
      S.forgeResult = { html: esc(FORGE_WAIT) };
      const stop = watchQueue(btn, "爐火正旺…");
      try {
        const r = await api("/api/menxia/forge", forgeBody());
        S.menxia = r.menxia;
        S.message = "";
        S.forgeResult = { html: r.message };
        trimForgeSel(); // 爐裡的東西留著（合成、合併都不會用掉），只拿掉已經不在手上的
        S.forgeLine = "";
        S.forgePicks = null;
        setMain(r.main);
        renderTop();
        guideMoved = guideKey(r.main && r.main.guide) !== step;
      } catch (e) {
        // 被擋下來（另一個分頁的上一爐還沒出爐：400）或連不上：等的時候寫的「爐火正旺……請稍候」不能留著，換成這一句，
        // 爐裡放的東西不動；api() 已經用提示泡泡講過一次，結果那一格再留一份
        S.forgeResult = { html: esc(failText(e)) };
      } finally { stop(); }
    });
    // 引導的下一句在頁面最上面（序章師父說的話）：這時才捲上去，不然留在原位、可以馬上接著合下一爐
    if (guideMoved) { renderPage(); window.scrollTo({ top: 0, behavior: "smooth" }); } else keepPlace(() => renderPage());
    updateForgeLine(); // 心得、體力、「已經有了」都變了：重問一次說明
  }

  async function travel(mode) {
    await busy(async () => {
      const r = await api("/api/travel", { place: S.map.selected, layer: S.layer, mode });
      setMain(r.main);
      if (r.arrived) {
        S.tab = "jianghu";
        render();
        window.scrollTo(0, 0);
      } else {
        S.map = r.map;
        S.mapNotice = `沒能出發：${esc(r.reason)}`;
        render();
      }
    });
  }

  // ── 事件 ──
  // 輿圖上選地點不走 click：pointer capture 之後 click 的目標會變，選取只在 gripUp 判斷「點了一下」時做
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

  document.addEventListener("click", async (ev) => {
    const el = ev.target.closest("[data-act]");
    if (!el) return;
    const act = el.dataset.act;
    if (el.classList.contains("act-ink")) {
      const [key, x, y] = [el.dataset.key, ev.clientX, ev.clientY];
      if (act === "wheel") requestAnimationFrame(() => inkRipple(key, x, y)); // 展開移動會重畫整頁
      else inkRipple(key, x, y);
    }
    try {
      switch (act) {
        case "gate": S.gateMode = el.dataset.mode; renderGate(); break;
        case "tab": await goTab(el.dataset.tab); break;
        case "choose": await choose(el, el.dataset.id); break;
        case "sense-clear": S.sensePts = []; S.senseNote = ""; renderPage(); break;
        case "sense-send": await senseSend(); break;
        case "move-mode": await setMoveMode(el.dataset.mode); break;
        case "toggle-more": toggleMore(); break;
        case "now-more": {
          // 原地展開／收起，不重畫整頁（重畫會讓「剛剛」再播一次浮現動畫）
          const box = el.closest(".now");
          const open = !box.classList.contains("open");
          S.nowOpen = open ? S.main.now : null;
          box.classList.toggle("open", open);
          box.classList.toggle("clamp", !open);
          el.textContent = nowMore(open);
          el.setAttribute("aria-expanded", String(open));
          break;
        }
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
          loadRecap(); // 有序章的內容才有「重看序章」鈕；同一次載入只問一次
          if (S.main.admin) { // 每次打開都重抓：時刻表與可以定的結果會變；查過的玩家也重查（給過的機緣、片段就不再列）
            S.admin = await api("/api/admin");
            if (S.adPlayerName) S.adPlayer = await api("/api/admin/player", { name: S.adPlayerName });
            renderKeepingSheet(); // 等資料的時候人可能已經往下捲了
          }
          break;
        case "peer": await openPeer(el.dataset.name); break;
        case "peer-close": S.peer = null; render(); break;
        case "peer-act": await peerAct(Number(el.dataset.i)); break;
        case "peer-pick": await peerAct(Number(el.parentElement.querySelector("select").value)); break;
        case "here-more": S.hereOpen = true; renderPage(); break;
        case "party-leave": await leaveParty(); break;
        case "book-open": S.bookFrom = window.scrollY; S.book = true; render(); document.querySelector(".book-layer")?.scrollTo(0, 0); break;
        case "book-close": S.book = false; render(); window.scrollTo(0, S.bookFrom || 0); break;
        case "sheet-close": S.sheet = false; S.recapOpen = false; S.howtoOpen = false; render(); break;
        case "howto": // 玩法說明：攤開就再問一次（refreshHowto），收起只是收起
          S.howtoOpen = !S.howtoOpen;
          if (S.howtoOpen) await refreshHowto();
          else renderKeepingSheet();
          break;
        case "howto-retry": S.howtoFailed = false; await refreshHowto(); break; // 要不到時卡上的「再試一次」
        case "howto-open": // 江湖頁新手期的「玩法說明 ›」（explain-2）：打開設定抽屜、攤開玩法說明（跟齒輪＋「玩法說明」兩下一樣）
          S.sheet = true;
          S.howtoOpen = true;
          render();
          loadRecap();
          await refreshHowto();
          if (S.main.admin) { // 跟齒輪打開時一樣：管理者的時刻表與可以定的結果會變，重抓；查過的玩家也重查（審查 Nit）
            S.admin = await api("/api/admin");
            if (S.adPlayerName) S.adPlayer = await api("/api/admin/player", { name: S.adPlayerName });
            renderKeepingSheet();
          }
          break;
        case "to-admin": document.getElementById("admin-zone")?.scrollIntoView({ behavior: "smooth", block: "start" }); break; // 抽屜頂上那顆「管理者工具 ↓」
        case "recap": S.recapOpen = !S.recapOpen; render(); break;
        case "guide-shut": shutGuide(S.main.guide); renderPage(); break;
        case "guide-open": openGuide(S.main.guide); renderPage(); break;
        case "guide-more": S.guideFull = S.guideFull === (S.main.guide && S.main.guide.text) ? null : S.main.guide && S.main.guide.text; renderPage(); break;
        case "scene-more": S.sceneOpen = !S.sceneOpen; renderPage(); break;
        case "peek": peekTap(el.dataset.id); break; // 江湖頁最上面那一排小標：只換那一塊，「剛剛」不會重播
        case "hear-more": hearToggle(el); break; // 戰鬥卡片底下聽來的那一句：原地展開／收起，不重畫
        case "line-more": lineToggle(el); break; // FB-107 收成一行的補充（對手的描述）：原地展開／收起，不重畫
        case "own-more": ownOpen(); break; // FB-107：決戰時收成一行的所在地描述，原地攤開
        case "battle-open": battleOpen(); break; // FB-120：只能觀戰的人收成一行的開打中的戰場，攤開（記戰場的名字）
        case "battle-shut": battleShut(); break; // 攤開的戰場底下「收起戰場」
        case "hint-more": S.hintOpen = !S.hintOpen; renderTop(); break; // 狀態列只重畫它自己（江湖頁不動，「剛剛」不會重播）
        case "guide-next": nextGuidePage(S.main.guide); renderPage(); break;
        case "guide-below": scrollToGuideTarget(); break;
        case "guide-ack": await doMain("guide_ack"); break;
        case "stam-help": S.stamOpen = !S.stamOpen; renderTop(); break; // 點體力條：底下攤開／收起體力怎麼回（explain-1）；丹的鈕自己是一顆，點它不會走到這裡
        case "fronts-help": frontsTap(); break; // 點戰況圖卡：底下攤開／收起這一季在打什麼、亂局、怎麼推（explain-2）
        case "pill": await doMain("pill"); break; // 體力條上的「丹 N」：服一顆回體丹（測試期間一鍵補滿打開時同一顆鈕寫「補滿」，同一條路由）
        case "allocate": await doMain("allocate", { stat: el.dataset.stat }); break; // 升級的屬性點加到一項（狀態列展開後的「＋臂力」）
        case "do": S.sheet = false; await doMain(el.dataset.op); break;
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
          if (op === "start_showdown") {
            body.id = el.dataset.id;
            body.title = ((S.admin && S.admin.showdowns) || []).find((s) => s.id === body.id)?.label || body.id;
          }
          if (op === "summon" || op === "give_opportunity" || op === "give_fragment") {
            body.name = (S.adPlayer && S.adPlayer.name) || "";
            if (op === "give_opportunity") {
              body.id = document.getElementById("ad-opp").value;
              body.note = ((S.adPlayer && S.adPlayer.opportunities) || []).find((x) => x.id === body.id)?.note || "";
            }
            if (op === "give_fragment") body.id = document.getElementById("ad-frag").value;
          }
          const [text, yes] = adminAsk(op, body);
          ask(text, yes, () => adminDo(op, body)); // 先問一次（G3），按了確定才送
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
        case "ask-no": closeAsk(); break;
        case "logout": closeEvents(); await api("/api/logout", {}); resetOrdersWatch(); forgetHowto(); S.sheet = false; S.peer = null; S.adPlayer = null; S.adPlayerName = ""; S.stage = "gate"; S.main = null; render(); break;
        case "kind": S.kind = el.dataset.kind; renderPage(); break;
        case "mx": if (el.dataset.kind) S.kind = el.dataset.kind; await mx(el.dataset.op); break; // 卷軸卡上的練成鈕帶著是哪一欄
        case "art-info": S.artInfo = S.artInfo === el.dataset.id ? null : el.dataset.id; renderPage(); break;
        case "lib-filter": setLibFilter(el.dataset.filter); renderPage(); break;
        case "lib-all": S.libAll = true; renderPage(); break;
        case "rack-all": S.rackAll = true; renderPage(); break;
        case "ins-open": S.insOpen = S.insOpen === el.dataset.id ? null : el.dataset.id; renderPage(); break;
        case "person":
          S.person = S.person === el.dataset.key ? null : el.dataset.key;
          await loadMenxia();
          break;
        case "wield": await mx("wield", { weapon: el.dataset.id }); break; // 裝備庫上那一把換到手上
        case "dismantle": await mx("dismantle", { weapon: el.dataset.id }); break; // 裝備庫上那一把拆成一個素材（兵器設計 4.7.1）
        case "switch": {
          // 改練真的送出了（mx 換上伺服器回來的那一份 menxia）才收起卡片；還在忙（mx 直接返回）或請求失敗就照舊開著
          const was = S.menxia;
          await mx("switch", { art: el.dataset.id });
          if (S.menxia !== was) { S.artOpen = null; if (S.tab === "practice") renderPage(); }
          break;
        }
        case "art": S.artOpen = S.artOpen === el.dataset.id ? null : el.dataset.id; S.artNote = null; renderPage(); break;
        case "cultivate": {
          // 勾的是畫面上看到的那一份：這一門現在真有「服下破境丹」可勾才算（伺服器也只認真正的布林 true）。
          // 送出就把勾清掉（mx 回來重畫時已經是沒勾的）；還在忙或請求失敗（mx 沒換上伺服器回來的那一份 menxia）就把勾還回去
          const id = el.dataset.id;
          const row = (S.menxia?.owned_arts || []).find((a) => a.id === id);
          const ticked = !!(row && row.cultivate.legend && S.legendTick[id]);
          const was = S.menxia;
          delete S.legendTick[id];
          await mx("cultivate", { art: id, use_legend: ticked });
          if (ticked && S.menxia === was) S.legendTick[id] = true;
          break;
        }
        case "melt": askMelt(el); break;
        case "melt-insight": askMeltInsight(el); break;
        case "art-filter": setArtFilter(el.dataset.page, el.dataset.filter); renderPage(); break;
        case "pick": pick(el.dataset.type, el.dataset.id); break;
        case "unslot": if (S.busy) break; S.forgeSel.splice(Number(el.dataset.i), 1); S.forgePicks = null; renderPage(); updateForgeLine(); break;
        case "forge": await forge(); break;
        case "craft-all": craftView().all = true; renderPage(); break;
        case "craft-ok": craftView().okOnly = !craftView().okOnly; renderPage(); break;
        case "forge-hub":
          if (forgeReady()) await forge();
          else toast("放一門武學和一個意境，或兩門武學，或兩個意境。");
          break;
        case "wheel":
          S.wheelSel = S.wheelSel === el.dataset.key ? null : el.dataset.key;
          renderPage();
          if (S.wheelSel) revealMoveCard(); // 收起（再點一次）不捲
          break;
        case "layer": S.layer = el.dataset.layer; await loadMap(S.map?.selected); break;
        case "map-zoom": mapZoom(el.dataset.step); break;
        case "map-home": mapHome(); break;
        case "legend-toggle": legendToggle(el); break;
        case "travel": await travel(el.dataset.mode); break;
        case "news":
          S.news = el.dataset.news;
          S.reportOpen = false;
          if (S.tab !== "news") { await goTab("news"); break; }
          renderPage();
          if (S.news === "reports") await loadReports(null);
          break;
        case "report":
          S.news = "reports";
          S.reportOpen = true;
          if (S.tab !== "news") { S.tab = "news"; S.unseen = false; render(); }
          await loadReports(Number(el.dataset.id));
          window.scrollTo(0, 0);
          break;
        case "report-list": S.reportOpen = false; renderPage(); break;
      }
    } catch (e) { /* api() 已經提示過 */ }
  });

  document.addEventListener("change", async (ev) => {
    if (ev.target.id === "place") {
      const id = ev.target.value;
      S.mapNotice = "";
      await loadMap(id).then(() => { if (S.tab === "map") mapCenterOn(id); }, () => {});
    }
    if (ev.target.id === "anon") await doMain("anonymous", { value: ev.target.checked });
    if (ev.target.id === "hints-off") await doMain("hints_off", { value: ev.target.checked }); // 碰到才說的小提醒（新手引導計畫三）；打開時排著的清掉
    if (ev.target.dataset && ev.target.dataset.legend) onLegendTick(ev.target);
    if (ev.target.dataset && ev.target.dataset.act === "craft-view") { // 煉製頁的屬性、品質、排序
      const v = craftView();
      v[ev.target.dataset.key] = ev.target.value;
      v.all = false;
      renderPage();
    }
  });

  // 修練頁「服下破境丹」勾了或取消：記在 S.legendTick（輪詢重畫才不會悄悄取消），機率那一行當場換成勾了／沒勾的那一句。
  // 兩句都是伺服器算好放在 owned_arts 裡的，不再問伺服器
  function onLegendTick(box) {
    const id = box.dataset.legend;
    const row = (S.menxia?.owned_arts || []).find((a) => a.id === id);
    if (!row || !row.cultivate.legend) return;
    if (box.checked) S.legendTick[id] = true; else delete S.legendTick[id];
    const note = box.closest(".acard, .art-body")?.querySelector(".cnote");
    if (note) note.textContent = box.checked ? row.cultivate.legend.note : row.cultivate.note;
  }

  // 輿圖的手勢：按下在地圖框上（gripDown），移動、放開在這裡收
  document.addEventListener("pointermove", (ev) => {
    if (!grip.pts.has(ev.pointerId)) return;
    grip.pts.set(ev.pointerId, [ev.clientX, ev.clientY]);
    const t = grip.tap;
    if (t && Math.hypot(ev.clientX - t.x, ev.clientY - t.y) > TAP_SLOP) {
      grip.tap = null; // 超過 8px 就是拖移，放開時不選地點
      document.getElementById("map")?.classList.add("moving"); // 拖的時候才升成合成層
    }
    if (!grip.frame) grip.frame = requestAnimationFrame(gripStep);
  }, true);
  document.addEventListener("pointerup", gripUp, true);
  document.addEventListener("pointercancel", gripUp, true);
  window.addEventListener("blur", gripEnd); // 拖到一半切走視窗：放開可能收不到，手勢作廢

  // 狀態列點名號展開／收起更多數值（S1）。鍵盤也按得到（Enter、空白鍵）；狀態列整塊重畫，所以按完把焦點放回去
  function toggleMore(keyboard = false) {
    S.showMore = !S.showMore;
    renderTop();
    if (keyboard) document.querySelector(".who")?.focus();
  }
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && askGo) { closeAsk(); return; } // 管理者確認框：Esc 等於取消
    if ((ev.key === "Enter" || ev.key === " ") && ev.target instanceof Element && ev.target.matches('.who[data-act="toggle-more"]')) {
      ev.preventDefault();
      toggleMore(true);
    }
    if ((ev.key === "Enter" || ev.key === " ") && ev.target instanceof Element && ev.target.matches('.tx-hearsay[data-act="hear-more"]')) {
      ev.preventDefault();
      hearToggle(ev.target);
    }
    if ((ev.key === "Enter" || ev.key === " ") && ev.target instanceof Element && ev.target.matches('.tx-tight[data-act="line-more"]')) {
      ev.preventDefault();
      lineToggle(ev.target);
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
      } else if (form.id === "create-form") {
        submit.disabled = true;
        enter(await api("/api/character", data));
      } else if (form.id === "answer-form") {
        if (!data.text.trim()) return;
        await answer(form, data.text.trim());
      } else if (form.id === "say-form") {
        if (!data.text.trim()) return;
        await sayLine(form, data.text.trim());
      } else if (form.id === "free-form") {
        if (!data.text.trim()) return;
        await doMain(form.dataset.op === "duel_text" ? "duel_text" : "battle_text", { text: data.text }); // 決戰或頭目戰的放手一搏
      } else if (form.id === "name-art") {
        // 絕學定名：名字合不合格、有沒有人用過都由伺服器驗，結果寫在頁面上方那一行；定成了表單就不再畫
        if (!data.name.trim()) { toast("先取個名字。"); return; }
        await mx("name", { name: data.name });
        // 被拒了（表單還在，原因寫在頁面上方那一行）：mx 重畫的表單是空的，把剛打的字放回去，不用重打；定成了表單就不在
        const again = document.querySelector('#name-art input[name="name"]');
        if (again && S.menxia && S.menxia.naming) again.value = data.name;
      } else if (form.id === "seclude") {
        // 閉關（QA L9）：真的進了閉關（busy_hours 有值）才回江湖頁。引擎不讓閉關（在路上、打坐、事件進行中）
        // 也是 200 加一句原因，請求本身失敗也一樣：留在修練頁、原因寫在頁面上方。
        // 等回應時玩家換到別的分頁（#mx-msg 煉製頁也有），原因就只用提示泡泡講，不寫到別頁上
        const tab = S.tab;
        await busy(async () => {
          let r;
          try {
            r = await api("/api/do/seclude", { hours: Number(data.hours) });
          } catch (e) {
            if (S.stage === "game" && S.tab === tab) {
              S.message = esc(failText(e));
              const el = document.getElementById("mx-msg");
              if (el) { el.innerHTML = S.message; el.classList.remove("still"); } // 新的一句，照常浮現
              window.scrollTo({ top: 0, behavior: "smooth" });
            }
            return;
          }
          const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
          if (r.main.status.busy_hours != null) {
            S.tab = "jianghu";
            applyMain(r.main);
            window.scrollTo(0, 0);
            if (text) toast(text);
          } else if (S.tab === tab) {
            S.message = r.message || "";
            setMain(r.main);
            renderTop();
            redrawPage(); // 選好的時數、填到一半的功法名字照舊，改好原因再按一次就行
            window.scrollTo({ top: 0, behavior: "smooth" });
          } else if (text) {
            toast(text); // S.main 不動，換過去的那一頁交給下一輪輪詢照它自己的方式補上
          }
        });
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
        // 重設密碼也先問一次（G3）。結果照舊寫在表單那一行、抽屜不關（失敗時欄位留著改，跟改密碼一樣）
        const target = (data.target || "").trim();
        if (!target) { formMsg(form, "先填要重設的帳號或名號。"); return; }
        ask(`重設 ${target} 的密碼，確定？`, "確定重設", async () => {
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
            const now = say(r.message, ok);
            if (ok && now) now.reset();
          } catch (e) {
            say(failText(e));
          }
        });
      }
    } catch (e) {
      if (submit) submit.disabled = false;
      formMsg(form, failText(e)); // 沒有訊息行的表單（閉關…）不受影響
    }
  });

  // ── 計時器：體力、氣血跟著時間走；別人推動的大勢也會進來 ──
  // 上一次輪詢還沒回來就不再打（最終審查 Critical 1）：伺服器忙著的時候（等行動鎖、別人開爐取名），
  // 卡住的 /api/main 不能每 10 秒再疊一個，把伺服器的執行緒池用光
  let pollInFlight = false;
  async function poll() {
    if (pollInFlight || S.stage !== "game" || S.busy || document.hidden) return;
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
      if (!typing()) await refreshPage(was);
    } catch (e) { /* api() 提示過；下一輪再試 */ } finally { pollInFlight = false; }
  }

  // 輪詢拿到有變的 main 之後，照目前的分頁補上（QA L1）。江湖、見聞從 S.main 畫；修練、煉製、輿圖重抓自己那一份。
  // 重抓回來時玩家若已經切了分頁、按了別的（那份資料已經換過）、正在忙或正在打字，就不動畫面，下一輪再說。
  async function refreshPage(old) {
    const tab = S.tab;
    if (tab === "jianghu") {
      if (pageKey(old) !== pageKey(S.main)) renderPage(); // 只有狀態列變了（時鐘在走）：上面 renderTop 已經畫過
      return;
    }
    if (tab === "news") {
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
      for (const id of Object.keys(S.legendTick)) { // 丹用完了、或那一門已經不是衝絕學這一步：勾跟著作廢
        const row = x.owned_arts.find((a) => a.id === id);
        if (!row || !row.cultivate.legend) delete S.legendTick[id];
      }
      if (!S.forgeSel.length) S.forgeLine = ""; // 爐是空的：用伺服器剛給的那一行（心得是新的）
      const shown = (m) => JSON.stringify(MENXIA_SHOWN[tab].map((k) => m[k]));
      const changed = trimmed || shown(x) !== shown(was)
        || (tab === "practice" && old.status.injury !== S.main.status.injury) // 療傷鈕看的是內傷
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
      const was = S.map;
      if (!was) return;
      // 手指（滑鼠）還按在地圖上：重畫會換掉手指底下的地圖、pointer capture 跟著斷，這一輪不畫。
      // 清掉 mainKey，下一輪的 main 就算沒變也會再來補畫
      if (mapHeld()) { S.mainKey = ""; return; }
      const q = new URLSearchParams({ layer: S.layer });
      if (was.selected) q.set("place", was.selected);
      const m = await api(`/api/map?${q}`);
      if (S.stage !== "game" || S.tab !== tab || S.busy || S.map !== was || typing()) return;
      if (mapHeld()) { S.mainKey = ""; return; } // 等回應時開始了手勢
      S.map = m;
      S.layer = m.layer;
      if (JSON.stringify(m) !== JSON.stringify(was)) redrawPage(true);
    }
  }

  // 修練、煉製兩頁各自畫了 menxia 的哪幾欄（照 pagePractice／pageCraft）：輪詢只在這幾欄變了才重畫。
  // 不比整份，是因為本人卡上的氣血一直在回，整份 menxia 幾乎每分鐘都不一樣，煉製頁根本沒畫那張卡
  const MENXIA_SHOWN = {
    practice: ["rules", "heal_cost", "slot_cards", "owned_arts", "insights", "holdings", "naming", "player_card", "roster", "person", "person_card", "on_team", "heal", "weapons"],  // heal：療傷鈕能不能按（銀兩夠不夠、內傷）變了就要重畫
    craft: ["owned_arts", "insights", "holdings", "clue_items", "bag", "forge_line", "xinde"],
  };

  // 重畫這一頁但保留玩家正在做的事（輪詢、閉關被拒時用）：填到一半的欄位（閉關時數）、
  // 摺疊區的開合（輿圖的視圖本來就存在 S.mapView，重畫照舊套用）。
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

  // S.menxia 換成新的一份之後：爐裡放的若已經不在了（例如在修練頁熔掉），拿掉、說明那一行作廢；爐裡還有東西就重問一次說明。
  // 不修剪的話，爐子看起來是空的（畫的時候找不到它），forgeReady() 卻照 id 數、開爐亮著，說明也是舊的
  function trimPot() {
    if (!trimForgeSel()) return;
    S.forgeLine = "";
    if (S.forgeSel.length) updateForgeLine();
  }

  // 重抓之後，爐裡放的若已經不在了（熔掉、別處用掉）就拿掉；有拿掉回 true
  function trimForgeSel() {
    const arts = new Set((S.menxia?.owned_arts || []).map((a) => a.id));
    const held = new Set((S.menxia?.insights || []).map((i) => i.id));
    const keep = S.forgeSel.filter((p) => (p.type === "art" ? arts : held).has(p.id));
    const trimmed = keep.length !== S.forgeSel.length;
    S.forgeSel = keep;
    return trimmed;
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
    else if (box instanceof Element && box.matches("details.orders")) S.ordersShut = box.open ? null : Number(box.dataset.week);
    // 「此地還能做」：記玩家（或自動打開）之後的開合與地點（hereFold），重畫、輪詢、擋下來都照它補回（FB-087）
    else if (box instanceof Element && box.matches("details.here")) S.here = { at: (S.main && S.main.status && S.main.status.location) || "", open: box.open };
    // 摺疊開了或收了：發光的鈕在裡面的話，光在鈕與標題列之間換邊（glowTarget）
    if (S.stage === "game") applyGlow();
  }, true);

  // 視窗大小變了（轉向、拉視窗）：輿圖開著就重新夾住、套用；原本是整張就維持整張（applyMapView）
  let cueTimer = 0;
  window.addEventListener("resize", () => {
    if (S.stage === "game" && S.tab === "map") applyMapView();
    if (S.stage === "game" && S.tab === "jianghu") { fitFirstRound(); fitOnResize(); } // 寬度變了，第一回合佔幾行、第一屏放不放得下也跟著變（只有高度變了不重量，見 fitOnResize）
    // 序章裡師父框上的「在下面 ↓」只在畫面重畫時算；視窗大小變了（轉向、拉視窗）目標離第一屏多遠也跟著變，去抖後重算、不重畫（T7 走查 W-F）
    clearTimeout(cueTimer);
    cueTimer = setTimeout(() => { if (S.stage === "game") guideCue(); }, 150);
  });
  // 寬度跨過手機分界（轉向、拉視窗）：江湖頁的排列順序不同（pageJianghu 的輪盤），要重畫
  const onPhoneChange = () => { if (S.stage === "game" && S.tab === "jianghu") renderPage(); };
  if (PHONE) { if (PHONE.addEventListener) PHONE.addEventListener("change", onPhoneChange); else PHONE.addListener(onPhoneChange); }

  api("/api/me").then(enter).catch(() => { S.stage = "gate"; render(); });
})();
