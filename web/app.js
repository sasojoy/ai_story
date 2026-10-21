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
    { id: "xingshi", name: "形勢" }, // 領地爭奪第三批 A：每天一篇〈天下形勢〉（/api/xingshi）；只有開著的季（main.xingshi）才畫這一顆（newsSegHtml）
    { id: "rumors", name: "傳聞" },
    { id: "chronicle", name: "江湖史" },
    { id: "journal", name: "紀錄" },
    { id: "annals", name: "行狀" }, // 玩家傳第一批：這一季值得寫進傳裡的事（/api/annals）
    { id: "boards", name: "榜單" }, // 企劃者 2026-10-14：善人、惡人、名人、宗師榜與武學榜、內功榜（/api/boards）
    { id: "mingtie", name: "名帖匣" }, // Joy 2026-10-19：自己的名帖與收到的名帖（/api/mingtie）
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
    baseTitle: document.title || "天下大勢", // 原本的分頁標題：輪到奪璽出招時改掉、之後改回（玉璽碎片設計 5.5）
    stage: "boot",
    gateMode: "login",
    main: null,
    mainKey: "",
    tab: "jianghu",
    nowOpen: null, // 江湖頁「剛剛」展開的那一則（記內容本身）；換成新的一則就收回（A4）
    letterOpen: null, // 江湖頁書信小卡攤開的那一封（id）
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
    shopTab: "shelf", // 店面（店面獨立介面設計第二節）：鐵匠鋪停在哪一頁（shelf 架上／forge 打造／temper 淬煉與修／rack 裝備庫）；進門停在架上
    shopPot: null, // 打造頁爐裡放了什麼：{ slot, kind, main, aux }（素材 id 或 null）；換了兵器防具那一頁從頭來，開爐成了清掉主輔料
    shopLine: null, // 這一爐會怎樣（/api/smith_line 回的那一份）；null 時照 shop.forge.line（空爐）
    shopReveal: null, // 剛出爐的那一件（/api/do/smith_forge 回的 forged）：麻布包著，點開才看；關掉出爐卡清掉
    shopOpened: false, // 出爐卡打開了沒（點了麻布）
    shopFiring: false, // 開爐等回應的那一下爐火竄高（減少動態效果的人不跑）
    shopMore: false, // 裝備庫頁按了「再列 N 件」
    shopHorse: null, // 馬市點著的那一間（馬的 id；待售那匹是「架:馬」）；null 照伺服器的 focus（你騎的，沒有馬就待售的）
    shopNote: null, // 鐵匠鋪素材頁、軍需帳上一下的結果那一句（升階出了什麼、捐了多少；素材與經濟 B6）；換頁、出店清掉
    donatePick: {}, // 軍需帳挑好要捐的：素材 id → 個數（點一格挑、＋−改個數，「捐出」一起送）
    boardZoom: null, // 懸賞榜放大的那一張告示（懸賞 id）；第三層開著時照伺服器的 picked
    tavTab: "news", // 酒肆那一頁停在哪（news 聽消息／ask 打聽／wall 題壁／shade 暗處）；進門停在聽消息（企劃者 2026-10-18）
    tavAsk: "seek", // 打聽那一頁問的是下落（seek）還是交情（ties）
    tavTier: 1, // 買殺手挑哪一檔（預設中間那一檔）
    tavHush: false, // 買殺手上次勾了封口沒
    tavWatch: false, // 查人時上次勾了託酒家留意沒
    tavMat: "", // 打聽那一頁挑著的素材 id
    arenaTab: "floor", // 擂台那一頁停在哪（floor 台下／board 擂台榜）；進擂台停在台下（Joy 2026-10-14「擂台應該要是獨立的一頁」）
    arenaSeen: null, // 看過、收起來的那一場收場卡（ArenaResult.id）
    boardStamp: null, // 剛交差的那一張：{ id, note, at }（交出之前那一份告示與它排第幾），照原本的位置蓋「交差」、淡出之後清掉（boardHanded）
    divineWhy: {}, // 神器原品定名被拒的原因（FB-193）：裝備 id → 那一句；表單裡留一行，改字時看得到（修練頁與店面共用）
    sealShut: {}, // 兩張玉璽卡收起來的狀態（FB-182，照懸賞卡）：duel＝奪璽卡那一場的 id、card＝碎片卡的 sealCardKey；換了一場、被牽動了就重新展開
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
    heroNode: null, // 修練頁人物面板點著的那個光點（HERO_FIGURES 的 key）；沒點過是內功
    artInfo: null, // 修練頁哪一門攤開了「詳情」（完整的功法卡）
    libFilter: null, // 修練頁功法庫的篩選：all／武學／內功／ready（可修練）；武學多時才出現。null＝還沒讀過這個瀏覽器記的（libFilter()，FB-085）
    libAll: false, // 功法庫列完了沒（武學多時先只列 LIB_PAGE 門）
    meltSel: null, // 批量熔煉勾著的 { arts, ins }（id 串列）；null＝沒在勾
    meltView: null, // 批量熔煉的篩選與排序 { kind, attr, quality, gen, rank, weak, sort }（meltView()）；只記在這一頁
    meltOpen: null, // 批量熔煉攤開細節的那一列（「arts:id」「ins:id」）
    meltNote: null, // 批量熔煉的結果（伺服器的 message HTML），寫在功法庫標題底下；下一個修練頁動作就清掉
    rackAll: false, // 裝備庫列完了沒（兵器多時先只列 LIB_PAGE 件，同功法庫）
    insOpen: null, // 修練頁點開的那一個意境（攤開說明與「化成心得」）
    mxNote: null, // 修練頁其他動作（裝備、意境、門下、療傷）的結果：{ at, html }，寫在按的那一塊裡（mxPlace）；切分頁、做別的動作就清掉
    artNote: null, // 修練（衝品質）的結果：{ id, html }，寫在那一門卡片的按鈕底下（W7）；點別的卡片、切分頁、做別的動作就清掉
    legendTick: {}, // 修練頁每一門武學「服下破境丹」勾了沒（id → true）；預設不勾，輪詢重畫不會悄悄取消，修練送出之後清掉
    forgeSel: [], // 爐裡放的：{type: "art" | "ins", id}，最多兩樣、武學最多兩門（武學＋意境、武學＋武學＝合成，兩個意境＝合併）
    forgeLock: null, // 鎖在爐裡的那一樣（{type, id}，一次一樣；Joy 2026-10-19「尤其獲得新意境時會想要試他的所有組合」）：開爐成了它留在爐裡、只清另一格
    wheelSel: null, // 江湖頁行動列展開的那一格（move；探索三選一開著時也有 explore）
    gatherOpen: false, // 探索卡上「找素材」底下的分支攤開了沒（第 32 項；做完一件事不收，下次點探索就直接看到）
    gatherSaying: false, // 找素材的「自己說…」輸入框叫出來了沒
    sensing: false, // 有所感：畫布叫出來了沒（按了「把心中的形畫下來」）；感悟狀態結束（選單上沒有 SENSE_DRAW）就收起
    sensePts: [], // 畫布上那一筆的點位 [[x, y, 毫秒], …]（畫布座標 0～256）；輪詢重畫頁面之後照它補畫回去
    senseNote: "", // 畫布底下那一行：這一筆落下了沒（/api/sense_read；不寫筆畫的幾何）
    stroking: false, // 手指正按在畫布上：輪詢不重畫（重畫會換掉畫布、手指底下的那一筆就斷了）
    forgeLine: "",
    craftPick: false, // 煉製頁挑東西的抽屜開著沒（點爐子的空格打開；兩格放滿、關掉、換分頁就收）
    forgePreview: null, // 兩格都放好時的預覽卡（/api/forge_line 的 preview，合成即設計）；只放一樣、空爐是 null，畫 forgeLine 那一行
    mapBase: null, // 輿圖升級：底圖（/api/map/base：svg、地點、路、大區），一次載入只抓一次，疊層的 key 變了才重抓
    mapState: null, // 疊層（/api/map/state）
    mapStateAt: 0, // 上次抓疊層的時間（輪詢每 MAP_STATE_EVERY 毫秒重抓一次）
    mapSel: null, // 選了的地點
    mapMode: "overview", // 抽屜在畫什麼："overview"、"place"、"search"、"timeline"
    mapLayers: ["control", "order"], // 開著的濾鏡（勢力、軍令預設開，設計第一節）
    mapDrawer: "home", // 抽屜的高度："home"（總覽的那一格：收起或收著，照 homeDrawer）、"min"、"rest"、"peek"、"half"、"full"、"tl"
    mapWeek: null, // 版圖變化看的週次；null＝現在
    mapQuery: "", // 找地點的字
    mapFocus: null, // 江湖頁的小地圖點了某一處：輿圖畫好時對準它（mapReady）
    // 輿圖的哪一層（輿圖第三版第 3 批）："world" 天下圖（打開輿圖第一眼，固定取景）、"region" 區圖（第 4 批之前是可以拖縮的那一張）
    mapLayer: "world",
    worldView: null, // 天下圖此刻的取景（applyMapView 照 worldFit 算，不存進 mapView）
    marksS: 0, // 上次畫記號時的倍率：倍率變了一成上下才重畫（字與圓盤照倍率反算）
    // 輿圖的視圖（W16）：{ s 倍率, cx, cy 視窗中心對著的地圖座標 }。這次載入網頁後第一次打開輿圖才決定（mapReady：
    // 對準所在地，手機原尺寸、寬螢幕照框寬，都不給整張），之後切分頁、輪詢重畫、換圖層、點地點都留著
    mapView: null,
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
  // 序章之後的「初入江湖」那幾步：跟序章一樣照 reveal 露出東西。
  const onb = () => (S.main && S.main.onboard) || null;
  // 初入江湖（新手引導第四段）：出了草廬之後那幾步也一樣一樣亮（m.onboard，同一個形狀）；草廬裡才有的規矩（略過序章、師父的框）照舊只看 pro()
  const shown = (key) => { const p = pro() || (S.main && S.main.onboard); return !p || p.reveal.includes("all") || p.reveal.includes(key); };
  const prologueKey = () => { const p = pro() || (S.main && S.main.onboard); return p ? p.reveal.join(",") : ""; };
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
    if (S.stage === "game" && S.tab === "map") loadMap().catch(() => {}); // 停在輿圖分頁登入：這個人的疊層與底圖（輪詢在沒有疊層時不抓）
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
    // 店面開了、收了或換了一間（店面獨立介面設計 1.1）：從頭來——鐵匠鋪從架上那一頁、空爐，馬市點著你騎的，懸賞榜不放大；
    // 離開鐵匠鋪時出爐卡一起收（只動 S 的欄位：setMain 會被單獨切出去測）。比的是哪一間店（main.shop.shop），不是有沒有店：出了鐵匠鋪、兩次輪詢之間又走進馬市，有沒有店都是「有」，鐵匠鋪那幾個欄位卻得清掉
    const shopKind = (v) => (v && v.shop ? v.shop.shop : null);
    if (shopKind(main) !== shopKind(S.main)) {
      S.shopTab = "shelf"; S.shopPot = null; S.shopLine = null; S.shopMore = false;
      S.shopHorse = null; S.boardZoom = null; S.boardStamp = null; S.arenaTab = "floor";
      S.shopNote = null; S.donatePick = {}; // 素材頁、軍需帳上一下的結果與挑好要捐的（素材與經濟 B6）
      S.tavTab = "news"; S.tavAsk = "seek"; // 酒肆從聽消息那一頁來
      if (shopKind(main) !== "smith") { S.shopReveal = null; S.shopOpened = false; }
    }
    S.main = main;
    // 決戰這一回合幾時逾時（引擎給還剩幾秒，battle_gauge.due）：tickDue 照它每秒倒數（Joy 2026-10-13）
    S.dueAt = main.battle_gauge && main.battle_gauge.due != null ? Date.now() + main.battle_gauge.due * 1000 : null;
    S.duePolled = false;
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
    if (S.stage !== "game" || (!S.sheet && !S.peer)) closeAsk(); // 確認框疊在設定抽屜或玩家卡上；抽屜關了、被登出就一起收掉
    if (S.stage !== "game") hideMapHost(true); // 登出、換帳號：常駐的輿圖那一層整個清掉
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
      ${S.main && S.main.shop ? shopHtml(S.main.shop) : ""}
      ${S.book ? bookHtml() : ""}
      ${S.zhuan ? zhuanHtml(S.zhuan) : ""}
      ${S.mtEdit && S.mingtie ? mtEditHtml() : ""}
      ${S.mtZoom ? mtZoomHtml() : ""}`;
    renderPage();
    if (S.mtEdit) mtPadReady();
    fitBars(); // 狀態列的「體力」「氣血」放不放得下（FB-198）
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

  // 奪璽卡（玉璽碎片設計 5.10，status.seal_duel）：全服看得到、可以摺疊，排在懸賞卡下面（不擠 375×812 的第一屏）。
  // 雙方、哪一片、第幾回合、氣勢的字（持有者看的是倒過來的，伺服器算好）、最近兩三行、已出招幾手與倒數；代打那一邊的架勢只在對手的卡上（伺服器只給他）。
  // 字待 joy 潤
  // 收起來照那一場記住（S.sealShut.duel，FB-182）；時間那一行包在 .seal-when 裡，輪詢只換它的字（paintSealWhen）
  function sealDuelHtml(d) {
    return `<details class="card seal-duel" data-key="${esc(d.id)}" ${S.sealShut.duel === d.id ? "" : "open"}><summary>奪璽・『${esc(d.shard)}』</summary>
      <p><b>${esc(d.challenger)}</b> 對 懷璽的 <b>${esc(d.holder)}</b>　<span class="seal-when">${esc(sealWhen(d))}</span></p>
      ${d.phase === "active" ? `<p>${esc(d.edge)}</p>` : ""}
      ${d.tell ? `<p class="tell">對手的架勢：${esc(d.tell)}</p>` : ""}
      ${d.turn ? `<p class="turn">輪到你出招。</p>` : ""}
      ${(d.lines || []).map((l) => `<p class="muted">${esc(l)}</p>`).join("")}
      <p class="muted">${esc(d.note)}</p></details>`;
  }

  // 奪璽卡那一行時間：下戰書的倒數、回合的最遲結算（現實秒，伺服器算好的 left）
  function sealWhen(d) {
    const left = `${Math.floor(d.left / 60)} 分 ${d.left % 60} 秒`;
    return d.phase === "muster" ? `${left}後開打` : `第 ${d.round | 0}／${d.rounds | 0} 回合・已出招 ${d.sent | 0}／2，最遲 ${left}後結算`;
  }

  // 奪璽卡那一行時間照 setMain 記下的期限（S.sealDueAt）重寫：輪詢回來江湖頁不必重畫（pageKey 沒變）時、與每秒的 tickDue 都走這裡（FB-182）
  function paintSealWhen() {
    const d = S.main && S.main.status && S.main.status.seal_duel;
    const el = document.querySelector(".seal-duel .seal-when");
    if (!d || !el) return;
    const left = S.sealDueAt == null ? d.left : Math.max(0, Math.ceil((S.sealDueAt - Date.now()) / 1000));
    el.textContent = sealWhen({ ...d, left });
  }

  // tickDue 每秒叫：奪璽卡倒數一秒；到零補問一次（下戰書到期開打、回合逾時結算，換上新的那一回合）
  function tickSeal() {
    paintSealWhen();
    if (!S.sealDuePolled && Date.now() >= S.sealDueAt) { S.sealDuePolled = true; poll(); }
  }

  // 碎片卡收起來照「哪一片、此刻牽不牽動」記住（S.sealShut.card，FB-182）：換了一片、被牽動了重新展開
  const sealCardKey = (s) => `${s.name}|${s.stir || ""}`;

  // 持有者的碎片卡（玉璽碎片設計第十節，status.seal）：哪一片與效果、這一季動過沒、此刻被牽動時那一句、這一季幾個險關的時刻；不寫機率。字待 joy 潤
  function sealHtml(s) {
    const key = sealCardKey(s);
    return `<details class="card seal-card" data-key="${esc(key)}" ${S.sealShut.card === key ? "" : "open"}><summary>傳承・『${esc(s.name)}』</summary>
      <p>${esc(s.effect_text)}</p><p class="muted">${esc(s.state)}</p>
      ${s.stir ? `<p class="turn">${esc(s.stir)}</p>` : ""}
      ${(s.dates || []).length ? `<p class="muted">這一季的險關：${s.dates.map(esc).join("、")}</p>` : ""}</details>`;
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
    if (S.tab === "map") mapFrame(); // 狀態列變高變矮：輿圖那一層跟著夾
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
    // 煉製頁縮起來的太極爐（.kiln.compact）固定在狀態列底下：狀態列多高（展開名號、換寬度都會變）記在 --top-h
    const head = document.getElementById("top");
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
    const subs = [
      s.calendar && s.next_event ? `下一件：${esc(s.next_event.title)}${s.next_event.at ? `・${esc(s.next_event.at)}` : ""}（${countdown(s.next_event.in_seconds)}）` : "",
      s.busy_hours != null ? `🧘 閉關中，現實約 ${s.busy_hours} 小時後出關` : "",
      s.journey != null ? `🐎 ${esc(s.journey)}` : "",
    ].filter(Boolean).map((t) => `<div class="where sub">${t}</div>`).join("");
    const where = inPro ? `📍 ${esc(s.location)}` : `📍 ${esc(s.location)}　${s.calendar
      ? esc(s.calendar.text)
      : `第 ${s.day} 天 ${esc(s.clock)}<small>／共 ${dayCount(s.season_days)} 天</small>`}`;
    const vitals = [
      // 回體丹（企劃者 2026-10-07 內測贈送）：有丹時體力條右端多一顆「丹 N」，按了吃一顆；體力滿了是灰的。序章裡伺服器不給 pills。
      // 測試期間一鍵補滿打開時（pills.refill）：沒有丹也有這顆鈕、字改成「補滿」，按了直接補滿、不花丹
      // 一天的上限（企劃者 2026-10-12，pills.today＝今天還能服幾顆，不限是 null）：鈕上多寫「今N」，服滿了灰掉寫「明日」
      // 點體力條（丹／補滿那顆鈕以外的地方）在底下攤開體力怎麼回（explain-1；s.stamina_help 是伺服器照設定寫好的幾行）
      shown("stamina") ? `<div class="bar stam" title="體力" data-glow="stamina"${s.stamina_help && s.stamina_help.length
        ? ` data-act="stam-help" role="button" tabindex="0" aria-expanded="${!!S.stamOpen}" aria-controls="stam-help"` : ""}><i style="width:${pct(s.stamina, s.stamina_max)}%"></i><span><em class="lbl">體力 </em>${s.stamina}/${s.stamina_max}</span>${s.pills
        ? `<button class="pill-btn" data-act="pill" ${s.pills.full || (!s.pills.refill && s.pills.today === 0) ? "disabled" : ""} aria-label="${s.pills.refill
          // 測試期間一鍵補滿（伺服器給 pills.refill＝鈕上的字，沒有丹也給）：鈕寫「補滿」不寫丹數；關著時沒有這個鍵，照 joy 的寫法
          ? `${esc(s.pills.refill)}體力（測試期間免費，不花${esc(s.pills.name)}）`
          : `服下${esc(s.pills.name)}（剩 ${s.pills.count} 顆，回 ${s.pills.restore} 點體力${s.pills.today == null ? "" : s.pills.today
            ? `，今天還能服 ${s.pills.today} 顆` : "，今天已經服滿，明日 00:00 後再服"}）`}">${s.pills.refill ? esc(s.pills.refill)
          : `丹${s.pills.count}${s.pills.today == null ? "" : s.pills.today ? `<small>今${s.pills.today}</small>` : "<small>明日</small>"}`}</button>` : ""}</div>` : "",
      shown("hp") ? `<div class="bar hp" title="氣血" data-glow="hp"><i style="width:${pct(s.hp, s.hp_max)}%"></i>${s.injury >= 1
        // 內傷（FB-049）：斜紋是上限裡被內傷佔掉、回不來的那一截（寬＝內傷÷上限，回滿時紅條剛好接到它）；
        // 「傷 N」靠右另寫在斜紋那一頭，不再接在「氣血 N/M」後面跨過紅條的交界
        // 「氣血」兩個字包成一格：條窄、又有內傷時讓開給「傷 N」（style.css 的 @container，FB-135）
        ? `<b style="width:${pct(s.injury, s.hp_max)}%"></b>` : ""}<span><em class="lbl">氣血 </em>${s.hp}/${s.hp_max}</span>${s.injury >= 1
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
      ${S.showMore && S.renownOpen && s.renown ? renownStripHtml(s.renown) : ""}
      ${inPro ? "" : subs}
      ${vitals ? `<div class="vitals">${vitals}</div>` : ""}
      ${S.stamOpen && shown("stamina") && s.stamina_help && s.stamina_help.length
        ? `<div class="more-stats stam-help" id="stam-help">${s.stamina_help.map((t) => `<p>${esc(t)}</p>`).join("")}</div>` : ""}
      ${S.showMore ? `<div class="more-stats">
        ${s.renown ? "" : `${s.minor.map(([k, v]) => `${esc(k)} ${v}`).join("　")}　｜　`}${s.attrs.map(([k, v]) => `${esc(k)} ${v}`).join("　")}
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
  // 名聲（名聲設計十一之二）：收起時名號底下一行稱號（1B），第一屏放不下（FIT_STEPS 的 renown，S.renownTight）時這一行不畫、
  // 善惡稱號（沒有就名望稱號）接在頭銜後面（放不下先收名望稱號，同草圖 1A）；展開時經驗底下「名聲」那一行，點了攤開段落條（2C）
  function whoNameHtml(s) {
    const r = s.renown;
    const spans = r ? rnTitleSpans(r) : [];
    if (!S.showMore) {
      const tight = S.renownTight && S.tab === "jianghu"; // 只有江湖頁量第一屏（同 💡 的 hintTight）：別的分頁照整行畫
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
  // 閉關（只剩「提前出關」）照畫（審查 I2）：最長的空檔，修練、煉製照樣做得了，也沒有選項會被擠下去。
  // 師父「碰到才說」的框（伺服器標 guide.hint）在畫面上時也不畫（審查 M6）：一次只給一句指點——兩樣一起，打完一場之後行動列會被推到
  // 分頁列底下；框是比較專門的那一句，提示等它，按了「知道了」（或框不在了）就回來。在路上照舊（框排在選項底下，提示收成一行）
  const WAITING = new Set(["act:break"]);
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
    if (S.tab === "map" && showMapHost()) page.innerHTML = ""; // 輿圖畫在常駐的那一層（FB-324）
    else {
      hideMapHost();
      const fn = { jianghu: pageJianghu, practice: pagePractice, craft: pageCraft, map: pageMap, news: pageNews }[S.tab];
      page.innerHTML = fn();
    }
    S.guideDrawn = guideSig(); // 這一頁畫的是哪個對話框：修練、煉製頁的輪詢拿它比，框換了才重畫（見 refreshPage）
    afterPage();
    if (S.tab === "craft") fixedKiln();
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
  // 一組選項時鈕收緊了還放不下，最後一步（choices，企劃者 2026-10-16 選 (c)）收態勢那一排、「剛剛」的敘事、灰掉的鈕底下那一行原因。
  // 在路上（另有自己的排法，FB-055）、序章裡不收。收到最後還放不下（集結又有框的時候：場景裡「此地還有」、結伴那一行不歸這裡收；
  // 別人遞來的邀請歸 6b 收，FB-117）就是放不下，不再藏別的
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
    // 3b. 名聲（1B）：名號底下那一行稱號不畫，善惡稱號接在頭銜後面（whoNameHtml；記在 S.renownTight，輪詢重畫狀態列時照它畫）
    { key: "renown", run: () => {
      if (S.renownTight || !document.querySelector("#top .who-renown-line")) return false;
      S.renownTight = true;
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
    // 5b. 決戰的本場戰功（名聲 4B）：名字底下那一行稱號收掉（名字照舊；三招不能被擠出第一屏）
    { key: "merit", run: () => {
      const rows = document.querySelectorAll(".g-merit .rn-two small:not(.fit-hide)");
      rows.forEach((el) => el.classList.add("fit-hide"));
      return rows.length > 0;
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
    // 6b. 場景底下別人遞來的邀請（FB-117：最多畫兩份，socialHtml）：還放不下就從最後一份往前收，收到放得下為止，
    //     收掉的併進「還有 N 份邀請 ▾」那一行（沒有那一行就補一行），點了全部攤開（callsOpened：玩家點開過、還是點開那時的那幾份，就不再收）
    { key: "calls", run: () => {
      const box = document.querySelector("#page > .card.scene .calls");
      if (!box || callsOpened((S.main && S.main.calls) || [])) return false;
      const rows = [...box.querySelectorAll(":scope > .call")];
      if (!rows.length) return false;
      // 「還有 N 份」那一行先放好、每收一份就換字，再量：以前收完才補那一行，量的時候少算了它的高度，補上之後行動列又掉回分頁列底下
      // （375×812、兩份、師父的框在：只收了一份，行動列 679～777）
      let more = box.querySelector(":scope > .calls-more");
      if (!more) {
        box.insertAdjacentHTML("beforeend", '<button class="linkish calls-more" data-act="calls-more" data-fit="1"></button>');
        more = box.querySelector(":scope > .calls-more");
      } else if (more.dataset.text == null) more.dataset.text = more.textContent;
      const total = Number(box.dataset.total) || rows.length;
      let hidden = 0;
      do {
        rows[rows.length - 1 - hidden].classList.add("fit-hide");
        hidden += 1;
        more.textContent = callsMoreText(total - (rows.length - hidden), hidden === rows.length);
      } while (fitOver() > 0 && hidden < rows.length);
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
    // 10. 一組選項時鈕收緊了還放不下（名聲的俠寇選項讓事件多到六顆；企劃者 2026-10-16 從三張截圖挑 (c)）：態勢那一排（.peek）收起、
    //     「剛剛」只留時間與標題（得失照舊在，「展開全文」看全文）、灰掉的俠寇鈕底下那一行原因收掉（原因本來就寫在鈕的 title，點了說整句，
    //     見 data-act="opt-why"）。閒著（行動列）時不收；攤開了態勢那一排某一格、展開了「剛剛」的不收那一樣
    { key: "choices", run: () => {
      if (document.querySelector("#page > .act-bar") || !document.querySelector("#page > .options")) return false;
      let any = false;
      const peek = document.querySelector("#page > .peek");
      if (peek && !peek.querySelector(".peek-panel")) {
        peek.classList.add("fit-hide");
        any = true;
      }
      const now = document.querySelector("#page > .now:not(.open)");
      const body = now && now.querySelector(".tx-now");
      if (body && body.querySelector(".tx-line")) {
        if (!now.classList.contains("fit-short")) { // 第 6 步沒收過（不會發生，保險）：照它的記法記下原本的樣子，還原時一起回去
          now.dataset.fitWas = now.classList.contains("fits") ? "fits" : "clamp";
          now.classList.add("fit-short");
        }
        now.classList.replace("fits", "clamp"); // 字收掉了：「展開全文」要在（第 6 步三行放得下時換成了 fits、沒有那顆鈕）
        now.classList.add("fit-title");
        any = true;
      }
      document.querySelectorAll("#page > .options > .btn.off .opt-note").forEach((el) => { el.classList.add("fit-hide"); any = true; });
      return any;
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
    if (S.renownTight) { S.renownTight = false; renderTop(); } // 名聲（1B）：稱號那一行畫回來再量
    page.querySelectorAll(".g-merit small.fit-hide").forEach((el) => el.classList.remove("fit-hide")); // 本場戰功的稱號（4B）
    page.querySelectorAll(".tx-tight").forEach((el) => {
      el.classList.remove("tx-tight");
      ["data-act", "role", "tabindex", "aria-expanded"].forEach((a) => el.removeAttribute(a));
    });
    page.querySelectorAll(".fit-fold").forEach((el) => el.classList.remove("fit-fold"));
    page.querySelectorAll(".peek.fit-hide, .opt-note.fit-hide").forEach((el) => el.classList.remove("fit-hide")); // 第 10 步
    page.querySelectorAll(".now.fit-title").forEach((el) => el.classList.remove("fit-title")); // 第 10 步；fits／clamp 照下一段還原
    page.querySelectorAll(".now.fit-short").forEach((el) => {
      el.classList.remove("fit-short");
      if (el.dataset.fitWas && !el.classList.contains("open")) el.classList.replace(el.classList.contains("fits") ? "fits" : "clamp", el.dataset.fitWas);
      delete el.dataset.fitWas;
    });
    page.querySelectorAll(".fit-own, .fit-muster").forEach((el) => el.classList.remove("fit-own", "fit-muster"));
    page.querySelectorAll(".call.fit-hide").forEach((el) => el.classList.remove("fit-hide")); // 6b：收掉的邀請攤回來
    page.querySelectorAll(".calls-more").forEach((el) => {
      if (el.dataset.fit) el.remove();
      else if (el.dataset.text != null) { el.textContent = el.dataset.text; delete el.dataset.text; }
    });
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
      </div>`;
    if (playing) $app.querySelector(".gate .promo").replaceWith(playing);
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
      const locked = m && isLocked(S.forgeSel[i]);
      // 格子外角一顆小鎖（pot-lock）：鎖著的那一樣開爐成了也留在爐裡
      const pin = m ? `<g class="w-pin${locked ? " on" : ""}" data-act="pot-lock" data-i="${i}" role="button" aria-label="${locked ? "解開" : "鎖住"}${esc(m.name)}" aria-pressed="${locked}"><circle cx="${i ? x + 22 : x - 22}" cy="-16" r="6.5"/><text x="${i ? x + 22 : x - 22}" y="-13.6" class="w-pin-t">鎖</text></g>` : "";
      return m
        ? `<g class="w-slot full r${m.rank}${S.potFlash === i ? " flash" : ""}${locked ? " locked" : ""}" data-act="unslot" data-i="${i}" role="button" aria-label="拿出${esc(m.name)}">
            <rect x="${x - 23}" y="-14" width="46" height="28" rx="7"/><text x="${x}" y="-3" class="w-slot-name"${fit}>${esc(m.name)}</text><text x="${x}" y="8" class="w-slot-sub">${esc(m.sub)}</text></g>${pin}`
        : `<g class="w-slot" data-act="pot-open"${potGlow()} role="button" aria-label="放一樣進爐"><rect x="${x - 23}" y="-14" width="46" height="28" rx="7"/><text x="${x}" y="0" class="w-slot-sub">放入</text></g>`;
    };
    return `<g class="w-hub w-furnace${ready ? " ready" : ""}" data-act="forge-hub" role="button" aria-label="太極火爐，開爐">
      <g class="w-shake">
        <g class="w-flames${ready ? " hot" : ""}">${flames}</g>
        <circle r="${r + 3}" class="w-hub-rim"/>
        <g class="w-spin w-taichi${ready ? " hot" : ""}" style="${spinAt(ready ? 3 : 28)}">
          <circle r="${r}" class="w-yang"/>
          <path d="M0,${-r} A${r},${r} 0 0 1 0,${r} A${r / 2},${r / 2} 0 0 1 0,0 A${r / 2},${r / 2} 0 0 0 0,${-r} Z" class="w-yin"/>
          <circle cy="${-r / 2}" r="${r / 7}" class="w-yang"/><circle cy="${r / 2}" r="${r / 7}" class="w-yin"/>
          <circle r="${r}" class="w-seam"/>
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

  // ── 江湖頁的行動列（企劃者 2026-10-04：輪盤太大，改成一排五顆，樣式是她給的「水墨氣勁」；2026-10-12 拿掉打坐剩四顆）──
  // 選項標籤「探索（體力 5・…）」拆成名字與括號裡的說明
  const optParts = (o) => { const m = /^(.*?)（(.*)）$/.exec(o.label); return m ? [m[1], m[2]] : [o.label, ""]; };
  // 決戰三招的按鈕（決戰改版一）：引擎給「選項名（強攻・82 分）」，招與分數拆到按鈕右邊的小字、名字佔剩下的寬度——
  // 375px 上一顆按鈕的字只有約 285px，括號整句接在名字後面的話，十一、十二個字的名字會把一顆按鈕折成兩行（多 20px）
  // 「・主將令」：照令的那一顆（龍頭上陣）
  const BATTLE_MOVE_LABEL = /^(.*)（((?:強攻|固守|奇襲)・\d+ 分(?:・主將令)?)）$/;
  // 鐵匠鋪的選項標籤很長（開爐、主料、輔料、買修淬煉），375px 上瀏覽器會在字中間斷行（FB-132：「下｜品」「沒｜人」「壓｜得住」「屬｜實」）。
  // 照分隔的標點切成小段，每段不折行（.nb），段與段之間才換行；標籤的字一個都不改，只是多包幾層 span，每段各自跳脫。
  // 切在「・；、，＋→」後面（連同後面跟著的空白，「→ 」不留在行頭）與「（」前面；括號尾「）」、數字與單位（「下品 46%」「工錢 150 兩」）
  // 都留在原來那一段。一段超過 NB_MAX 個字就不包（寧可折行也不讓字衝出按鈕）
  const NB_AFTER = "・；、，＋→";
  const NB_MAX = 16;
  function nbChunks(text, after = NB_AFTER) {
    const s = String(text ?? ""), out = [];
    let cur = "";
    for (let i = 0; i < s.length; i++) {
      if (s[i] === "（" && cur) { out.push(cur); cur = ""; }
      cur += s[i];
      if (after.includes(s[i])) {
        while (s[i + 1] === " ") cur += s[++i];
        out.push(cur);
        cur = "";
      }
    }
    if (cur) out.push(cur);
    return out;
  }
  // 「→ 」後面那個空白放在 span 外面：行內區塊尾巴上的空白會被瀏覽器吃掉（「→這個配方」貼在一起），放外面它是普通空白，既看得到、也是一個換行機會，落在行尾或行頭時自己消失
  const nbHtml = (text, after = NB_AFTER, max = NB_MAX) => nbChunks(text, after).map((t) => (t.length <= max ? `<span class="nb">${esc(t.trimEnd())}</span>${esc(t.slice(t.trimEnd().length))}` : esc(t))).join("");
  // 打點帳簿的說明、旁註、去處（FB-411：375 寬一頁 176px，「最／多打點到 40」「今天還能／捐 1000 兩」斷在詞中間）：同一套小段，切在
  // 「，・；／：」後面與「（」前面；不切「→」（「情誼 0 → 5」是一件事）。一段最多 LEDGER_NB 個字（一頁 150px 上下，太長的照常折行）
  const LEDGER_AFTER = "，・；／：";
  const LEDGER_NB = 14;
  const ledgerText = (text) => nbHtml(text, LEDGER_AFTER, LEDGER_NB);
  // 打點店上面掮客那一句（FB-433：360、320 寬斷在「您／挑」「寫／著」中間）：同一套不折行的小段，切在「，。：；！？」後面，
  // 緊跟著的收引號「」』」併進前一段（不讓一個「」」落單到下一行）；一段超過 LEDGER_NB 個字照常折行
  const SAY_AFTER = "，。：；！？";
  function sayHtml(text) {
    const s = String(text ?? ""), out = [];
    let cur = "";
    for (let i = 0; i < s.length; i++) {
      cur += s[i];
      if (SAY_AFTER.includes(s[i])) {
        while (s[i + 1] && "」』".includes(s[i + 1])) cur += s[++i];
        out.push(cur);
        cur = "";
      }
    }
    if (cur) out.push(cur);
    return out.map((t) => (t.length <= LEDGER_NB ? `<span class="nb">${esc(t)}</span>` : esc(t))).join("");
  }
  // 價錢後面打折的原因（名聲 4.1：「威震州郡・九折」「自家地盤・貴兩成」，territory.price_parts、renown.clinic_part）：每一段包成同一種不折行的
  // 小段（.nb），375 寬才不會斷成「九／折」「八五／折」（FB-297）。緊貼的「（」與後面的「，」「）」一起包：Chrome 在括號與行內區塊之間照樣斷，
  // 不包的話一行收在「（」上、下一行從「，」起頭；段與段之間（「，」後面）照常換行。先跳脫再包，字一個不改。
  // 醫館療傷（選項與修練頁）、開爐鈕、馬市待售那一間、素材頁升階格子用它；smith:、market: 的選單鈕已經照 nbChunks 切過，不必再包
  const DEAL_RE = /（?[^（），、；\s・]+・(?:[一二三四五六七八九]+折|貴[^（），、；\s]+)[，）]*/g;
  const dealHtml = (text) => esc(text).replace(DEAL_RE, '<span class="nb">$&</span>');
  // 一行寫完：tests/test_battle_buttons.py、test_peek_row.py 的假瀏覽器照名字把這一行切出去（konst），smith:、market:（馬市的鈕一樣長，裝備四欄 5.5）才會用到 nbHtml
  // o.note（名聲 5B 俠寇選項）：標籤底下第二行小字；o.tag（「俠」「寇」）畫在編號那一格（選單那裡）。灰掉、帶原因的那一顆在選單那裡
  // 另外寫進 title、點了說整句（opt-why）；第一屏放不下時 FB-107 第 10 步收掉這一行
  const optLabelHtml = (o) => { const m = o.id.startsWith("battle:act:") ? BATTLE_MOVE_LABEL.exec(o.label) : null; return m ? `<span class="b-name">${esc(m[1])}</span><span class="b-move">${esc(m[2])}</span>` : `<span>${o.id.startsWith("smith:") || o.id.startsWith("market:") ? nbHtml(o.label) : dealHtml(o.label)}${o.note ? `<small class="opt-note">${esc(o.note)}</small>` : ""}</span>`; };
  // 這幾格對到選單上哪一顆、沒有時寫什麼；最後一格是移動（點了在下面展開走法與目的地）
  const ACT_CELLS = [
    { key: "explore", ids: ["act:explore"], name: "探索", none: "不能探索", icon: '<circle cx="12" cy="12" r="9"/><path d="M12 3v3m0 12v3M3 12h3m12 0h3M15 9l-4 2-2 4 4-2z"/>' },
    { key: "train", ids: ["act:train"], name: "遊歷", none: "沒有對手", icon: '<path d="M14.5 4h-5L7 7h10zM12 7v13M8 12h8"/>' },
    // 打坐 2026-10-12 拿掉了（企劃者）：這一格只在序章教體力那一步有選項（調息），沒有選項就不畫（平常是四顆）
    { key: "rest", ids: ["act:rest"], name: "調息", none: "", icon: '<circle cx="12" cy="7" r="2.5"/><path d="M8 20c0-3 3-4 4-4s4 1 4 4M5 15l3-2m11 2l-3-2"/>' },
    { key: "social", ids: ["act:socialize", "act:call"], name: "交友", none: "沒有人", icon: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>' },
  ];
  const MOVE_ICON = '<path d="M13 3l-3 7h5l-4 11 8-10h-5z"/>';
  const SHORT_SUB = { "act:rest": "回體力", "act:call": "挑一位" };  // 求見先打開名單挑人（FB-044：以前又寫一次「求見」；挑了人才花體力）
  const TALKED_OUT = "已經談滿", TALKED_OUT_SUB = "已談滿";  // 談滿了的求見（Game._talked_out_note 的開頭）在行動列格子裡的短說法（待 joy 潤）
  // 出陣（出陣探索與地盤設計第二節）：出陣開著時（m.sortie）遊歷那一格叫「出陣」，散人、不在戰線上的地點沒有出陣鈕時灰著寫「不在戰線」（待 joy 潤）
  const SORTIE_CELL = { name: "出陣", none: "不在戰線" };
  const SORTIE_LEFT = /今日還能 (\d+) 次/; // 鈕上的「今日還能 N 次」：格子小字寫「今日 N 次」
  const SORTIE_USED = /^今日已出陣/;
  const SORTIE_FULL_SUB = "今日已滿"; // 用完了：整句（什麼時候再來）在行動列底下那一行（待 joy 潤）
  const EXPLORE_PREFIX = "explore:"; // 探索三選一（出陣探索與地盤設計第三節）：探索那一格點了展開這三顆
  const EXPLORE_SUB = "三選一"; // 探索那一格是展開鈕時的小字（待 joy 潤）
  // 找素材分支（第 32 項，計畫 2.1 甲）：選單上有 explore:gather:<分支> 時「找素材」是展開鈕，點了在它底下再攤一排分支（S.gatherOpen）；
  // 最後一顆「自己說…」點了出 20 字的輸入框（S.gatherSaying），送 /api/do/gather_text（同事件的隨口應對那一個輸入框）
  const GATHER_ID = "explore:gather"; // engine：explore_modes.option_id(GATHER)
  const GATHER_BRANCH = "explore:gather:"; // 分支的前綴
  const GATHER_SAY_ID = "explore:gather:say"; // explore_modes.SAY_ID
  // 勝算的顏色（FB-044）：遊歷的小字第二行照風險上色
  const ODDS_TONE = { "穩勝": "good", "有把握": "good", "零風險": "good", "五五波": "even", "難分勝負": "even", "凶險": "bad", "必敗": "bad" };
  // 選單上有「探索」就是平常閒著的時候（以前認打坐，2026-10-12 拿掉了）：用行動列。事件、對話、路上、決戰的選項每次都不一樣，照舊排成一列按鈕
  // 序章裡閒著時選單只留這一步要的（打坐常常不在）：沒有事件的選項、不在路上，也當閒著的行動列來畫，沒亮的格子不畫（F12）
  // 籌備中、休季、暫停（season:）與閉關中（act:break）的選單只有一顆通知：那顆要畫成看得見的按鈕，不能掉進行動列的摺疊裡（M2）
  const NOTICE_MENU = /^(choice:|sense:|season:|act:break$)/;
  const idleMenu = (m) => m.options.some((o) => o.id === "act:explore") || (!!m.prologue && !m.on_road && !m.options.some((o) => NOTICE_MENU.test(o.id)));
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
  // 名下有同伴的人按了加入（或晚到、臨時投效）之後挑誰隨你出陣（battle:escort:*，歷史武將同行）：還沒加入，一樣畫在這裡（FB-360）
  const MUSTER_JOIN = /^battle:(join|enlist|escort):/;
  // 鈕旁邊那一小句（待 joy 潤）：加入的那一顆在名字右邊，這句夾在名字與鈕中間、指向它；散人的兩顆在名字底下另起一行，這句在名字右邊、往下指。
  // 放不下時省略號收尾（style.css 的 .muster-note），名字那一行不因此變高、不折行。箭頭另外放（MUSTER_ARROW），讀螢幕的軟體不唸它（aria-hidden）
  // 挑同伴那一步（escort，FB-360）：一顆一行（鈕上寫份量與氣血，四顆擠一排放不下），那一小句說挑了才算加入（待 joy 潤）
  const MUSTER_NOTE = { join: "報名在這裡", enlist: "挑一邊臨時投效，只算這一場", escort: "挑一位隨你出陣，挑了才算加入" };
  const MUSTER_ARROW = { join: "→", enlist: "↓", escort: "↓" };
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
  // 那一小句用 aria-describedby 接到那一排鈕上（一頁只有一張場景卡，id 不會重複）。
  // FB-553：同一州兩場以上自己這一邊的攻城一起集結，加入鈕一場一顆、鈕上寫是哪一場（字長），兩顆擠在名字那一行把整頁撐出橫捲
  // （375 寬 488px）：兩顆以上照挑同伴那一步，另起一行、一顆一行（.pick），那一小句往下指；一顆的照舊在名字右邊
  function musterScene(m, scene) {
    const joins = musterJoins(m);
    if (!joins.length) return scene;
    const kind = joins.some((o) => o.id.startsWith("battle:escort:")) ? "escort"
      : joins.some((o) => o.id.startsWith("battle:enlist:")) ? "enlist" : "join";
    const wide = kind === "enlist";
    const stacked = kind === "escort" || (kind === "join" && joins.length > 1);
    const note = `<span class="muster-note" id="muster-note">${esc(MUSTER_NOTE[kind])}<span aria-hidden="true"> ${stacked ? MUSTER_ARROW.escort : MUSTER_ARROW[kind]}</span></span>`;
    const cls = wide ? " wide" : stacked ? " pick" : "";
    const row = `<div class="options muster-join${cls}" role="group" aria-label="參戰" aria-describedby="muster-note">${joins.map((o) =>
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

  // ── 決戰的戰況一回合一段（Joy 2026-10-14「大決戰因為很多人，戰況文字沒有分回合，擠在一起玩家很難閱讀」）──
  // 引擎（engine._round_blocks）把最近五段戰況寫成「##### 第 N 回合」加一行一條的清單、新的在上。這裡把最新那一回合包成一塊整段攤開，
  // 舊的幾回合各收成一行（<details>：回合數＋那一回合誰佔上風那一句，點了攤開）；攤開了哪幾回合記在 S.roundsOpen，輪詢重畫照樣開著
  // 每一條是哪一軍的（Joy 2026-10-14「看不出誰是官軍誰是黃巾」）：引擎在開頭寫「〔官軍〕」（engine.SIDE_TAG），這裡換成那一軍顏色的
  // 小標籤、整條左邊一道那一軍的顏色（同戰局條的 side-<陣營 id>）；自己那一軍多標「我方」。認不出的名字照字留著。
  // 兩個式子寫在函式裡：測試的假瀏覽器照名字只抽函式出來
  // report：戰報頁那一場的流水號（決戰的完整戰況，Joy 2026-10-14）：每一回合都收成一行、照先後，展開了哪幾回合跟場景分開記（「r<流水號>:<回合>」）
  function roundBlocks(html, g, report) {
    const ROUND_HEAD = /<h5>第 (\d+) 回合<\/h5>\n<ul>\n([\s\S]*?)<\/ul>\n?/g;
    const SIDE_TAG = /<li>〔([^〕<]+)〕/g;
    let newest = report == null;
    const open = S.roundsOpen || (S.roundsOpen = new Set());
    const sides = {};
    if (g) for (const w of [g.left, g.right]) if (w) sides[w.name] = w;
    return html.replace(ROUND_HEAD, (all, n, rows) => {
      const items = rows.replace(SIDE_TAG, (tag, name) => {
        const w = sides[name];
        return w ? `<li class="b-side side-${esc(w.id)}${w.mine ? " mine" : ""}"><span class="b-tag">${name}${w.mine ? "・我方" : ""}</span>` : tag;
      });
      const list = `<ul class="b-lines">\n${items}</ul>`;
      if (newest) {
        newest = false;
        return `<div class="b-round latest"><p class="b-rhead">第 ${n} 回合</p>${list}</div>\n`;
      }
      const first = /<li>([\s\S]*?)<\/li>/.exec(items);
      const gist = first ? first[1].replace(/<[^>]*>/g, "") : "";
      const key = report == null ? n : `r${report}:${n}`;
      return `<details class="b-round" data-round="${key}"${open.has(key) ? " open" : ""}><summary><b>第 ${n} 回合</b>${gist ? `<span>${gist}</span>` : ""}</summary>${list}</details>\n`;
    });
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
  // 本場戰功的名字（名聲 4B）：加入決戰時快照的稱號（善惡第 1 段起、名望名動一方起，r.renown）寫在名字底下第二行；
  // 第一屏放不下時 FIT_STEPS 的 merit 把第二行收掉（.fit-hide）
  const meritName = (r) => (r.renown && r.renown.length
    ? `<span class="rn-two">${esc(r.name)}<small>${esc(r.renown.join("・"))}</small></span>` : `<span>${esc(r.name)}</span>`);
  // 戰局條底下的「本場戰功」（Joy 2026-10-10 個人戰功，battle_instance.merit_board）：兩軍各列前幾名，最後一行是自己排第幾、戰功怎麼來的。
  // 集結中、還沒有人出手時不畫
  function meritHtml(g, tint) {
    const b = g.merit;
    if (!b || g.phase === "muster" || (!b.left.length && !b.right.length && !(b.me && b.me.merit))) return "";
    const col = (w, rows) => `<div class="g-mcol ${tint(w)}"><b class="g-mside">${esc(w.name)}</b>${rows.length
      ? `<ol>${rows.map((r, i) => `<li${r.mine ? ' class="mine"' : ""}><i>${i + 1}</i>${meritName(r)}<b>${r.merit}</b></li>`).join("")}</ol>`
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
  // 攻城戰畫面（領地爭奪第三批 A，企劃者挑甲）：沿用決戰畫面，最上面那一行換成一條「攻城・地點｜守方：某某（或守將）」（main.siege，
  // engine.siege_banner；三方混戰、轉回單方、兩軍相爭的字是伺服器給的）。引擎場景第一行是 **攻城・地點**：把那一行換成這一條（不多佔一行；
  // 集結時這一條自己一行，「報名在這裡」與加入的鈕排在它底下，見 style.css）；找不到那一行就疊在最上面；收成一行的觀戰（battle-fold）不畫。
  // 每一段包成不折行的小段，只在「｜」那裡換行。
  // 排在 withGauge 之後：withGauge 認的是原本那一行 <p>，換掉之前先把戰局條插好
  function siegeStrip(html, s) {
    if (!s || html.startsWith('<p class="battle-fold"')) return html;
    const strip = `<p class="siege-strip" role="note"><span class="nb ss-title">${esc(s.title)}</span>${(s.parts || []).map((p) =>
      `<span class="ss-sep" aria-hidden="true">｜</span><span class="nb">${esc(p)}</span>`).join("")}</p>`;
    const head = `<p><strong>${esc(s.title)}</strong></p>`;
    const at = html.indexOf(head);
    return at >= 0 ? html.slice(0, at) + strip + html.slice(at + head.length) : strip + html;
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
    // 探索三選一（出陣探索與地盤設計第三節）：三顆畫在探索那一格點開的卡上，不掉進「此地還能做」
    // 找素材分支（第 32 項）畫在「找素材」底下那一排，不算進三選一的那幾顆
    const modes = m.options.filter((o) => o.id.startsWith(EXPLORE_PREFIX) && !o.id.startsWith(GATHER_BRANCH));
    const branches = m.options.filter((o) => o.id.startsWith(GATHER_BRANCH));
    modes.forEach((o) => used.add(o.id));
    branches.forEach((o) => used.add(o.id));
    // 入口灰著（體力不夠，三顆都按不下去）時就算記著展開也不畫：那一格是灰格子，不是展開鈕
    const exploreOpen = S.wheelSel === "explore" && modes.length > 0 && !!(byId["act:explore"] && byId["act:explore"].enabled);
    // 序章（新手引導計畫一）：還沒亮的格子不畫（act:explore、act:train、act:rest、act:social、act:move）；
    // 不畫的格子對到的選項照樣記成用過，不會掉進「此地還能做」那個摺疊裡
    const cells = ACT_CELLS.map((d0) => {
      const d = d0.key === "train" && m.sortie ? { ...d0, ...SORTIE_CELL } : d0;
      const o = d.ids.map((id) => byId[id]).find(Boolean) || (d.key === "social" ? loneCall : undefined);
      if (o) used.add(o.id);
      if (!shown(`act:${d.key}`) || (d.key === "rest" && !o)) return "";
      if (!o) return inkCell(d.key, d.name, d.none, d.icon, "disabled", " off");
      const lone = o.id.startsWith("call:");
      const [label, detail] = optParts(o);
      const name = lone ? "求見" : label;  // 格子窄：名字寫「求見」，人物的名字放在下面一行
      noted.push([name, o.id]);
      // 按不下去的原因：標籤括號裡寫的是體力就是「體力不夠」，寫別的就照寫；整句太長、格子裝不下（約 60 px、不換行）時只留
      // 最後一小句（例：挑戰本人打贏之後「剛吃了敗仗，閉門不見」只寫「閉門不見」，T4）
      // 談滿了的求見（「已經談滿 3 輪，第 1 週・週日 00:00 之後再來」）：最後一小句是換日的那一刻，格子裝不下會被切成碎片，
      // 格子只寫「已談滿」，整句在底下那一行（Game.action_notes，day-scale 審查 I1）
      // 出陣：小字寫今天還剩幾次（「今日 5 次」，體力在鈕上、說明那一行也有）；用完了寫「今日已滿」，什麼時候再來在底下那一行
      const left = SORTIE_LEFT.exec(detail);
      // 探索三選一開著：探索那一格是展開鈕（同移動），點了在下面就地展開三顆；入口灰著（三顆都按不下去）時照一般的灰格子
      const wheel = d.key === "explore" && modes.length > 0 && o.enabled;
      const sub = wheel ? EXPLORE_SUB
        : o.enabled ? (lone ? label.replace(/^求見/, "") : left ? `今日 ${left[1]} 次` : (SHORT_SUB[o.id] || detail.replace(/^體力 (\d+).*$/, "體力 $1")))
        : lone && detail.startsWith(TALKED_OUT) ? TALKED_OUT_SUB
        : SORTIE_USED.test(detail) ? SORTIE_FULL_SUB
        : (detail && !detail.startsWith("體力") ? detail.split("，").pop() : "體力不夠");
      // 體力之後還有說明（遊歷的「體力 10・2 路對手・必敗」）：挑出勝算那一段另起一行（FB-044；對手數放不下就不寫）。
      // 不一定是最後一段：有自己人也有敵人的地方後面還接「・或與自己人操練」（畫面批次審查 C1）
      const parts = detail.split("・");
      const note = o.enabled && !wheel && /^體力 \d+/.test(parts[0]) ? (parts.find((x) => x in ODDS_TONE) || "") : "";
      const attrs = wheel ? `data-act="wheel" data-key="explore" aria-expanded="${exploreOpen}"`
        : o.enabled ? `data-act="choose" data-id="${esc(o.id)}"` : "disabled";
      return inkCell(d.key, name, sub, d.icon, attrs, (o.enabled ? "" : " off") + (wheel && exploreOpen ? " on" : ""), note);
    });
    const moves = m.options.filter((o) => followsMode(o.id));
    moves.forEach((o) => used.add(o.id));
    // 奪璽單挑的三招（或灰的「已出招」「來不及了」）：自己是一方時伺服器排在選單最前面（玉璽碎片設計 5.5），
    // 畫在行動列上面一排，不掉進收起來的「此地還能做」（同 FB-105 的集結鈕）
    const sealMoves = m.options.filter((o) => o.id.startsWith("seal:"));
    sealMoves.forEach((o) => used.add(o.id));
    const sealRow = sealMoves.length ? `<div class="options seal-moves" role="group" aria-label="奪璽">${sealMoves.map((o) => `
        <button class="btn" data-act="choose" data-id="${esc(o.id)}" ${o.enabled ? "" : "disabled"}><span>${esc(o.label)}</span></button>`).join("")}</div>` : "";
    // 應召（一類一顆開著時，設計 9.1 第 1 組乙）：有召見時行動列上面一條金框橫幅，按了就去應召；沒有召見不畫，也不收進「此地還能做」
    const summons = m.precise ? byId["act:summons"] : null;
    if (summons) used.add(summons.id);
    const summonsRow = summons ? (() => {
      const [label, detail] = optParts(summons);
      return `<div class="summons-strip"><span>召見</span><button class="summons-go" data-act="choose" data-id="act:summons" ${summons.enabled ? "" : "disabled"}>
        <b>${esc(label)}</b>${detail ? `<small>${esc(detail)}</small>` : ""}</button></div>`;
    })() : "";
    const open = S.wheelSel === "move";
    if (shown("act:move")) {
      cells.push(inkCell("move", "移動", moves.length ? `${moves.length} 條路` : "沒有路", MOVE_ICON,
        moves.length ? `data-act="wheel" data-key="move" aria-expanded="${open}"` : "disabled", (open ? " on" : "") + (moves.length ? "" : " off")));
    }
    const moveCard = !open || !shown("act:move") ? "" : `<div class="card act-move"><div class="seg move-mode" role="group" aria-label="走法">${MOVE_MODES.map((x) => `
          <button class="${S.moveMode === x.id ? "on" : ""}" data-act="move-mode" data-mode="${x.id}" aria-pressed="${S.moveMode === x.id}">${x.name}</button>`).join("")}</div>
        <div class="options">${moves.map((o) => `<button class="btn go" data-act="choose" data-id="${esc(o.id)}" ${o.enabled ? "" : "disabled"}>
          <span class="k">→</span><span>${esc(o.label)}</span></button>`).join("")}</div></div>`;
    const exploreCard = !exploreOpen ? "" : `<div class="card act-explore"><div class="options">${modes.map((o) => o.id === GATHER_ID && branches.length
      ? gatherWheel(o, branches) : `
          <button class="btn" data-act="choose" data-id="${esc(o.id)}" ${o.enabled ? "" : "disabled"}><span>${esc(o.label)}</span></button>`).join("")}</div></div>`;
    // 其他只在此地才有的行動（招募、投靠、多出來的求見）收在摺疊裡，不佔行動列的高度。
    // 入伍段要你按的那一顆收在這裡（巡哨、傳道、保境安民、接糧車……，伺服器在框上帶的 guide.glow，FB-093）：那一步在這一處開頭摺疊先打開
    // 一次、那一顆發光（applyGlow）；其他時候收著。開合記在 S.here（hereFold，FB-087），重畫照它補回
    const extras = m.options.filter((o) => !used.has(o.id));
    const hotHere = extras.some((o) => guideGlow().includes(o.id));
    // 論武的「答應」（選單上那一顆引擎不收、是灰的）：場景底下那一列帶了 peer，這裡同一顆也畫成打開他的玩家卡（FB-117，callPeers）
    const peers = callPeers(m);
    const here = extras.length ? `<details class="fold here"${hereFold(m, hotHere) ? " open" : ""}><summary>此地還能做 ${extras.length} 件事</summary><div class="fold-body options">${extras.map((o) => peers[o.id] ? `
        <button class="btn" data-act="peer-answer" data-name="${esc(peers[o.id])}"><span>${esc(o.label)}</span></button>` : `
        <button class="btn" data-act="choose" data-id="${esc(o.id)}" ${o.enabled ? "" : "disabled"}><span>${dealHtml(o.label)}</span></button>`).join("")}</div></details>` : "";
    const drawn = cells.filter(Boolean); // 序章裡沒亮的格子是空字串；一格都沒有、也沒有「此地還能做」時整條不畫
    // 行動列底下那幾行（explain-1）排在行動列之後：不推動「剛剛」、場景與整排行動（375×812 第一屏）。展開移動時讓位（走法與目的地那張卡
    // 緊貼在行動列底下），入伍段要按的鈕在「此地還能做」裡時也讓位（不把發光的那一顆往下推）
    // 展開探索三選一時同樣讓位（三顆緊貼在行動列底下）
    const notes = open || exploreOpen || hotHere ? "" : actNotesHtml(m, noted);
    return `${sealRow}${summonsRow}${drawn.length ? `<div class="act-bar" role="group" aria-label="行動" style="--cells:${Math.max(4, drawn.length)}">${drawn.join("")}</div>` : ""}${notes}${moveCard}${exploreCard}${here}`;
  }

  // 找素材分支（第 32 項，計畫 2.1 甲）：「找素材」那一顆是展開鈕（再點一次收起；入口灰著〔分支都按不下去〕時不展開），
  // 點開了在它底下攤一排分支（兩欄：名字一行、「體力 6・剛、慢」一行），最後一顆「自己說…」佔一整列；點了「自己說…」換成 20 字的
  // 輸入框（S.gatherSaying），送 /api/do/gather_text（gatherSay）。展開記在 S.gatherOpen，做完一件事不收（下次點探索就直接看到分支，
  // 少按一下）；換到沒有分支的地方就不畫。字待 joy 潤
  // 輸入框的提示照別的 20 字輸入框寫字數（隨口應對「…（20字內）」、對話「想對他說的話（20字內）」）。這一格縮在分支那一排裡，比那兩格窄：
  // 320 寬扣掉內距只剩 152 像素（16px 的字九個多），原本的「怎麼找？例：沿著獸徑找落羽」208 像素切在「沿著獸徑」，例句拿掉（FB-460）
  const GATHER_SAY_HINT = "怎麼找？（20字內）"; // 待 joy 潤：輸入框的提示
  const GATHER_SAY_GO = "去找"; // 待 joy 潤：送出鈕
  function gatherWheel(o, branches) {
    const open = !!S.gatherOpen && o.enabled;
    const head = `
          <button class="btn gather-head${open ? " on" : ""}" data-act="gather-wheel" aria-expanded="${open}" ${o.enabled ? "" : "disabled"}><span>${esc(o.label)}</span><span class="gather-caret" aria-hidden="true">${open ? "▴" : "▾"}</span></button>`;
    if (!open) return head;
    const say = branches.find((b) => b.id === GATHER_SAY_ID);
    const saying = !!(say && S.gatherSaying && say.enabled);
    // 兩欄排，分支是單數條時最後一條佔整列（.wide），旁邊不留一格空的（FB-461：嵩山深處挖礦、狩獵、深入，深入旁邊空著）
    const real = branches.filter((b) => b.id !== GATHER_SAY_ID);
    const wide = real.length % 2 ? real[real.length - 1].id : null;
    const cells = branches.filter((b) => !(saying && b.id === GATHER_SAY_ID)).map((b) => {
      const [name, detail] = optParts(b);
      return `<button class="btn gather-branch${b.id === GATHER_SAY_ID ? " say" : b.id === wide ? " wide" : ""}" data-act="choose" data-id="${esc(b.id)}" ${b.enabled ? "" : "disabled"}><span class="gb-text"><b>${esc(name)}</b>${detail ? `<small>${nbHtml(detail)}</small>` : ""}</span></button>`;
    }).join("");
    const form = saying ? `<form class="free answer gather-say" id="gather-say-form"><input class="input" name="text" maxlength="20" placeholder="${esc(GATHER_SAY_HINT)}" aria-label="${esc(say.label)}"><button class="btn primary small" type="submit">${esc(GATHER_SAY_GO)}</button></form>` : "";
    return `${head}<div class="gather-branches" role="group" aria-label="找素材">${cells}${form}</div>`;
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
    if (m.status && m.status.howto_entry) rows.push(m.status.renown ? HOWTO_ENTRY.replace("名望怎麼來", "名聲怎麼來") : HOWTO_ENTRY);  // 名聲開著時那一節叫「名聲」
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

  // 展開移動（或探索三選一）之後，把展開的那張卡捲到剛好露出來（W18 的作法搬過來：狀態列有心得提示時整頁往下推，
  // 卡片下緣會落到底部分頁列底下）。block: "nearest"：本來就看得到就不動；離分頁列多遠由 CSS 的 scroll-margin-bottom 決定
  function revealMoveCard() {
    const card = document.querySelector("#page .act-move, #page .act-explore");
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

  // 書信（大勢人物擴充第二批）：「剛剛」上面一張小卡，收著只露一行（誰來信、開頭幾個字），點了攤開全文與委託；
  // 「收起」記成看過了（委託照樣在身上，懸賞卡上看得到），求援的「婉拒」讓委託作罷。字都是伺服器寫好的（letters.view）
  function letterHtml(x) {
    if (!x) return "";
    const open = S.letterOpen === x.id;
    const t = x.task;
    const task = t ? `<div class="letter-task"><div class="order-head"><b>${esc(t.title)}</b><span>${esc(t.state || "委託")}</span></div>
        <div class="order-how">${esc(t.how)}</div><div class="order-meta">${esc(t.reward)}</div><div class="order-meta">${esc(t.due)}</div></div>` : "";
    const decline = t && t.live ? `<button class="btn small ghost" data-act="letter-decline" data-id="${x.id}">婉拒</button>` : "";
    return `<section class="card letter${open ? " open" : ""}" data-letter="${x.id}">
      <button class="letter-head" data-act="letter-open" data-id="${x.id}" aria-expanded="${open}"><span class="letter-k">${esc(x.kind)}</span><b>${esc(x.sender)}來信</b>${open ? "" : `<span class="letter-peek">${esc(x.text)}</span>`}<span class="letter-arrow" aria-hidden="true">${open ? "▴" : "›"}</span></button>
      ${open ? `<div class="letter-body"><p>${esc(x.text)}</p><p class="letter-sign">${esc(x.sender)}</p>${task}<div class="row">${decline}<button class="btn small" data-act="letter-read" data-id="${x.id}">收起</button></div></div>` : ""}
    </section>`;
  }

  // 手上揭了的懸賞，加上身上有合用東西的求藝、求兵（status.bounties，bounties.status；後者多一行 have）：一張一行，怎麼交差、賞什麼。懸賞榜在城鎮才看得到，
  // 選單上有 act:bounties 時卡底下一顆「看懸賞榜」（就是那個選項，按了走 choose），不在城鎮寫一句去哪裡看。
  // 預設展開，收起來的狀態照手上那幾張記住（S.bountyShut）：揭了新的、交了差，清單變了就重新展開
  // 21 天季的賞拆成小籤（企劃者挑第 5 批畫面第三組丙；bounties.reward_tags）：一樣一格，附的那一樣金框、重賞紅框。字與數字照伺服器給的
  function rewardChips(tags) {
    return `<div class="rtags">${tags.map((t) => `<span class="rtag${t.kind ? ` ${esc(t.kind)}` : ""}">${t.k ? `<em>${esc(t.k)}</em>` : ""}${esc(t.v)}</span>`).join("")}</div>`;
  }

  function bountiesHtml(list, options) {
    const key = list.map((b) => b.id).join(",");
    const board = (options || []).find((o) => o.id === "act:bounties");
    const level = (list.find((b) => b.level) || {}).level; // 21 天季：「賞照你第 N 級」寫在卡頭
    const rows = list.map((b) => `
      <div class="order">
        <div class="order-head"><b>${esc(b.title)}</b><span>${esc(b.issuer)}</span></div>
        <div class="order-how">${esc(b.how)}</div>
        ${b.tags ? `<div class="order-meta">${rewardChips(b.tags)}</div>` : `<div class="order-meta">${esc(b.reward)}</div>`}
        ${b.due ? `<div class="order-meta">${esc(b.due)}</div>` : ""}
        ${b.have ? `<div class="order-meta">${esc(b.have)}</div>` : ""}
      </div>`).join("");
    // 懸賞榜正開著（第二層「返回」或第三層「回到懸賞榜」，選單就是榜）：卡底下不再寫什麼
    const open = (options || []).some((o) => o.id === "bounty:back" || o.id === "bounty:unpick");
    const foot = open ? "" : board
      ? `<button class="btn small" data-act="choose" data-id="act:bounties" ${board.enabled ? "" : "disabled"}>看懸賞榜</button>`
      : '<div class="order-meta">到城鎮的懸賞榜前，可以揭新的、放棄，或交出合用的功夫與兵器。</div>';  // 待 joy 潤
    return `<details class="fold bounties" data-key="${esc(key)}" ${S.bountyShut === key ? "" : "open"}>
      <summary>🪧 懸賞（${list.length}）${level ? `<span class="order-level">${esc(level)}</span>` : ""}</summary><div class="fold-body">${rows}${foot ? `<div class="bounty-foot">${foot}</div>` : ""}</div></details>`;
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
    // 豪強分屬兩軍的季 status.stances 只有官軍、黃巾：沒有的那一方不畫
    const rows = STANCE_NAMES.filter(([side]) => side in s.stances).map(([side, name]) => ({ side, name, value: s.stances[side] }));
    const title = rows.length > 2 ? "三方態勢" : "兩軍態勢";
    const n = s.stance_notes || {};
    const how = [n.sum ? `官軍、黃巾：${esc(n.sum)}` : "", n.haoqiang ? `豪強：${esc(n.haoqiang)}` : ""].filter(Boolean).join("；");
    return {
      id: "stance",
      label: `${title}：${rows.map((x) => `${x.name} ${x.value}`).join("、")}`,
      chip: `<span class="peek-name">態勢</span><span class="peek-nums">${rows.map((x) => `<b class="side-${esc(x.side)}">${x.value}</b>`).join("·")}</span>`,
      panel: `${stanceBars(rows, title)}${s.stance_rule ? `<p class="stance-rule">${esc(s.stance_rule)}</p>` : ""}${how ? `<p class="stance-how">${how}</p>` : ""}${warHelp(m, "stance")}`,
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

  // 每日簽到（21 天季，正式季整合 6.2；畫面照 9.1 第 4 組丙）：收進這一排小標，還沒簽亮紅點、簽了寫「簽到 ✔」。攤開是這一週七格
  // （最後一週到季末為止）、今天的份與領的鈕；四階的日子是四顆挑屬性的鈕（點一種就領）。伺服器沒給 status.checkin（週末與 14 天的季、
  // 序章裡、休季）就不畫。CK_LAST 待 joy 潤
  const CK_ATTR = { 剛: "gang", 柔: "rou", 快: "kuai", 慢: "man" };
  const CK_LAST = "這一季最後一天";
  // 格子上的短字（FB-436）：兩樣的那一格（第 6 天「丹2＋四階」）375、360 寬放不下一行，照「＋」拆兩行；一樣的照舊一行
  function ckGift(label) {
    const parts = String(label).split("＋");
    return parts.length < 2 ? esc(label) : parts.map((p, i) => `<span class="gl">${i ? "＋" : ""}${esc(p)}</span>`).join("");
  }
  function checkinPeek(m) {
    const k = m.status && m.status.checkin;
    if (!k) return null;
    const cells = k.week.map((d) => `<div class="ck-day ${d.state}${d.got ? " got" : ""}${d.four ? " four" : ""}"><span class="d">${d.day}</span><span class="g">${ckGift(d.label)}</span></div>`).join("");
    const act = k.done ? "" : k.pick
      ? `<div class="ck-pick">${k.pick.map((x) => `<button class="ck-p4 ${CK_ATTR[x.attribute] || ""}" data-act="checkin" data-attr="${esc(x.attribute)}"><b>${esc(x.attribute)}</b>${esc(x.name)}<small>有 ${x.held}</small></button>`).join("")}</div>`
      : '<button class="ck-go" data-act="checkin">領取</button>';
    return {
      id: "checkin",
      label: `簽到：第 ${k.day} 天${k.done ? "已簽" : "還沒簽"}`,
      chip: `<span class="peek-name">簽到${k.done ? " ✔" : ""}</span>`,
      flag: !k.done,
      dotNote: "",
      panel: `<div class="ck-head"><b>第 ${k.day} 天</b><span>${k.next ? `下一份：${esc(k.next)}` : CK_LAST}</span></div>`
        + `<div class="ck-week">${cells}</div><p class="ck-step">${esc(k.step)}</p>${act}`,
    };
  }

  const peekParts = (m) => [shown("stances") ? stancePeek(m) : null, shown("board") ? boardPeek(m, peekWeek(m)) : null, shown("quest") ? questPeek(m) : null, checkinPeek(m)];

  function peekHtml(parts, week) {
    const list = parts.filter(Boolean);
    if (!list.length) return "";
    const open = S.peekOpen && S.peekOpen.week === week ? list.find((p) => p.id === S.peekOpen.id) : null;
    const row = list.map((p) => {
      const on = p === open, dot = p.flag && !on; // 開著的時候就是正在看，不亮點
      // dotNote：亮點時讀給人聽的那一句（簽到的 label 已經寫「還沒簽」，給空字串）
      return `<button class="peek-chip ${p.id}${on ? " on" : ""}" data-act="peek" data-id="${p.id}" aria-expanded="${on}" aria-label="${esc(p.label)}${dot ? (p.dotNote ?? "，有還沒看過的") : ""}">${p.chip}${dot ? '<i class="peek-dot" aria-hidden="true"></i>' : ""}</button>`;
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
    const gentry = "haoqiang" in stances ? `<br>${side("haoqiang")}${note(n.haoqiang)}` : ""; // 豪強分屬兩軍的季沒有豪強那一行
    return `<div class="stances-line"><span>態勢</span><span>${side("guan")}・${side("huang")}${note(n.sum)}${gentry}</span></div>`;
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
  // 陣營軍備的存量（素材與經濟設計第六節；企劃者 2026-10-15 選草圖 C1）：戰況圖卡底下一行（規則關著的季沒有戰況卡，就排在那個位置）。
  // 伺服器在投靠了陣營、捐軍備開著時給 status.armament。在決戰怎麼起作用還沒定，這裡只寫存量。字待 joy 潤
  function armsLine(m) {
    const a = m.status && m.status.armament;
    if (!a || !shown("orders")) return "";
    return `<p class="arms-line"><span class="who">${esc(a.faction)}軍備</span>${a.stock.map((s) => `<span>${esc(s.name)} <b>${s.points | 0}</b></span>`).join("")}</p>`;
  }

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
        <button class="btn ${followsMode(o.id) ? "go" : ""}${!o.enabled && o.note ? " off" : ""}" data-act="${!o.enabled && o.note ? "opt-why" : "choose"}" data-id="${esc(o.id)}" ${!o.enabled && o.note ? `data-why="${esc(o.note)}" title="${esc(o.note)}" aria-disabled="true"` : o.enabled ? "" : "disabled"}>
          ${senseTag(o) ? `<span class="k sense">${esc(senseTag(o))}</span>` : o.tag ? `<span class="k rn-tag ${rnPathClass(o.tag)}">${esc(o.tag)}</span>` : `<span class="k">${o.id.startsWith("move:") ? "→" : o.id.startsWith("road:back") ? "↩" : i + 1}</span>`}${optLabelHtml(o)}
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
    // 「此地還有」與別人遞來的邀請、結伴那一行：平常畫在場景卡底下；決戰輪到你出招時（FB-117 第七件）挪到三招後面另一張卡——
    // 營地裡人多時名單有兩三行，排在三招上面就把第三招擠到分頁列底下（375×812：三招 647～791，分頁列頂 756）
    const myTurn = opts.some((o) => o.id.startsWith("battle:act:"));
    const people = (m.here && m.here.length ? hereHtml(m) : "") + (m.party || (m.calls && m.calls.length) ? socialHtml(m) : "");
    const scene = masterTalks ? ""
      : m.on_road
        ? `<section class="card scene road${S.sceneOpen ? "" : " clamp"}" data-act="scene-more" role="button" tabindex="0" aria-expanded="${!!S.sceneOpen}">${m.scene}</section>`
        : `<section class="card scene">${siegeStrip(withGauge(musterScene(m, roundBlocks(battleScene(m), m.battle_gauge)), m.battle_gauge), m.siege)}${myTurn ? "" : people}</section>`;
    const peopleAfter = myTurn && people && !masterTalks && !m.on_road ? `<section class="card people-after">${people}</section>` : "";
    // 序章：小地圖與江湖紀錄的連結要等「輿圖、見聞」亮了才畫（shown("minimap")）
    const tail = shown("minimap") ? `<div class="mini" data-act="tab" data-tab="map" role="button" aria-label="展開輿圖">${m.minimap}</div>
      <button class="linkish" data-act="news" data-news="journal">看江湖紀錄 ›</button>` : "";
    // 態勢｜大事｜主線 收成一排小標（正式版辛）：排在最上面、「剛剛」之前，不管是哪一種選單；在路上才排到選項底下（FB-055）。
    // 三張摺疊卡疊起來有 170px，打完一仗整排行動就被擠出第一屏；一排只有 44px。公告的展開、已看過都是小標自己記（見 peekHtml）
    const week = peekWeek(m);
    const peek = peekBlock(m);
    // 三條戰況排在行動列下面、小地圖上面，不擠掉第一屏的「剛剛」、場景與行動列
    // 點圖卡在底下攤開說明（explain-2，frontsBlock）
    const fronts = (m.fronts && shown("fronts") ? frontsBlock(m) : "") + armsLine(m);
    // 休季的結算卡排在最上面（計畫 T9）；季收了、有行狀時緊接一張「讀你的傳」（玩家傳第二批，m.zhuan）
    const resultCard = (m.season_result ? resultHtml(m.season_result) : "") + (m.zhuan ? zhuanEntry(m.zhuan, "這一季收了，史官替你立傳", "讀你的傳") : "");
    const letter = letterHtml(m.letter); // 書信小卡排在「剛剛」上面（大勢人物擴充第二批）
    // 本週軍令排在行動列（與路上捷徑）下面、三條戰況上面：不擠掉第一屏的「剛剛」、場景與行動列（計畫 T6）
    // 收起來照週記；21 天季的軍令每天一道，照季曆第幾天記（status.calendar.day），隔天的新軍令重新展開
    const orderKey = (m.status && m.status.calendar && m.status.calendar.day) || week;
    const orderCard = (m.orders || m.convoy) && shown("orders") ? ordersHtml(m.orders || [], orderKey, m.convoy) : "";
    // 懸賞卡跟軍令卡排在一起（散人沒有軍令，這張就是他的）：手上沒揭、也沒有合用的求藝求兵可以交時就不畫（status.bounties 兩種都收）
    const bountyCard = m.status && m.status.bounties && m.status.bounties.length && shown("orders") ? bountiesHtml(m.status.bounties, m.options) : "";
    const sealCard = m.status && m.status.seal_duel && shown("orders") ? sealDuelHtml(m.status.seal_duel) : "";
    const sealMine = m.status && m.status.seal && shown("orders") ? sealHtml(m.status.seal) : "";
    // 序章第一步（還沒遇到師父）：選項底下一行「略過序章」，不想走序章的人直接站到起點（設計 7.3）
    const skip = pro() && pro().skip ? '<button class="linkish skip-prologue" data-act="do" data-op="skip_tutorial">略過序章</button>' : "";
    // 劇情文字在上、行動在下（企劃者 2026-10-04）。行動列只有一排，375×812 上「剛剛」、場景與整排行動都在第一屏。
    // 路上的三個捷徑（links）緊接在場景（「也可以打開輿圖改去別處，或去修練、煉製」那一段）底下、選項上面：
    // 排在路上的五六顆選項底下時落在第一屏外，要捲才看得到（FB-048）。說書人的話緊貼在行動上方（引導重做設計 8.1）
    const guide = guideHtml(m.guide, m.on_road);
    // 在路上（FB-055）：路上的五個選項要全在第一屏（375×812），所以那一排小標與說書人的框都排在選項底下——
    // 不是這一刻要按的；捷徑還是緊接在場景底下（FB-048）
    if (m.on_road) return `${resultCard}${letter}${now}${scene}${links}${free}${menu}${guide}${peek}${orderCard}${bountyCard}${sealMine}${sealCard}${fronts}${tail}`;
    // 決戰輪到你出招的回合（FB-136）：三招緊接在場景底下，放手一搏的輸入框與說書人的框排在三招後面（同在路上，這一刻要按的排前面）。
    // 開打那一刻場景多了戰局條、這一幕的開場、騎兵那一句，框與輸入框再排在上面的話三招整排落到分頁列底下（14 天、騎著馬、框還在：855～999）
    if (myTurn) {
      return `${resultCard}${peek}${letter}${now}${scene}${links}${menu}${peopleAfter}${free}${guide}${senseNotes}${skip}${orderCard}${bountyCard}${sealMine}${sealCard}${fronts}${tail}`;
    }
    return `${resultCard}${peek}${letter}${now}${scene}${links}${guide}${free}${menu}${senseNotes}${skip}${orderCard}${bountyCard}${sealMine}${sealCard}${fronts}${tail}`;
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
  // 論武的答應要挑自己出哪一樣（FB-117）：那一顆帶 peer（他的名號），畫成「挑一樣答應」、按了打開他的玩家卡捲到答應那一格（peerAnswer，
  // 不送伺服器）；其餘照舊送選單上的 invite: 選項
  const callButton = (o) => (o.peer
    ? `<button class="btn small" data-act="peer-answer" data-name="${esc(o.peer)}">${esc(o.label)}</button>`
    : `<button class="btn small" data-act="choose" data-id="${esc(o.id)}" ${o.enabled ? "" : "disabled"}>${esc(o.label)}</button>`);
  // 場景那一列帶 peer 的回應鈕：選項 id → 他的名號（「此地還能做」裡同一顆也照它畫成打開玩家卡）
  function callPeers(m) {
    const out = {};
    (m.calls || []).forEach((c) => c.options.forEach((o) => { if (o.peer) out[o.id] = o.peer; }));
    return out;
  }
  // 別人遞來的邀請最多畫 CALLS_SHOW 列（FB-117：以前沒上限，一個人同時發四種就把整排行動擠出第一屏），其餘收成一行
  // 「還有 N 份邀請」、點了才攤開（openCalls、callsOpened）。舊的在前（伺服器排的，先逾時的先畫）
  // 第一屏還放不下時，畫好之後再從最後一份往前收（FIT_STEPS 的 calls），收掉的也併進那一行
  const CALLS_SHOW = 2;
  const callsMoreText = (n, all) => (all ? `有 ${n} 份邀請等你回應 ▾` : `還有 ${n} 份邀請 ▾`); // 待 joy 潤
  // 一份邀請的記號：它的編號（回應鈕的 id 最後那一段，invite:<回應>:<編號>）
  const callKey = (c) => String((c.options[0] && c.options[0].id) || c.text).split(":").pop();
  // 點了「還有 N 份／有 N 份邀請等你回應」：S.callsOpen 記點開那時的那幾份（callKey）。現在的每一份都還在裡面就算攤開著——
  // 其中幾份回了、逾時了照樣攤著，一份不剩才收回；來了新的一份就照平常收（不然它會把行動列推出第一屏）。
  // 以前記的是真假、邀請不超過 CALLS_SHOW 份就改回假：一、兩份被第一屏收法（6b）收成一行時，點了又被收回去、點不開（FB-241）
  function callsOpened(calls) {
    return Array.isArray(S.callsOpen) && calls.length > 0 && calls.every((c) => S.callsOpen.includes(callKey(c)));
  }
  function openCalls() {
    S.callsOpen = ((S.main && S.main.calls) || []).map(callKey);
    renderPage();
  }
  function socialHtml(m) {
    const all = m.calls || [];
    const open = callsOpened(all);
    if (!open) S.callsOpen = false;
    const list = open ? all : all.slice(0, CALLS_SHOW);
    const more = all.length - list.length;
    const calls = list.map((c) => `<div class="call"><span>${esc(c.text)}</span>${c.options.map(callButton).join("")}</div>`).join("")
      + (more ? `<button class="linkish calls-more" data-act="calls-more">${callsMoreText(more, false)}</button>` : "");
    const party = m.party ? `<div class="party"><span>${esc(m.party.text)}</span>${m.party.lead ? ""
      : '<button class="btn small ghost" data-act="party-leave">分道揚鑣</button>'}</div>` : "";
    return `<div class="calls" data-total="${all.length}">${calls}${party}</div>`;
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
  // still：輪詢換卡（applyPeer）時畫的那一張不再播一次滑上來、淡入（style.css 的 .still）
  function peerHtml(still = false) {
    const P = S.peer;
    const quiet = still ? " still" : "";
    const c = P.card;
    const body = P.loading ? '<p class="muted">……</p>'
      : !c ? `<p>${esc(P.gone || "對方已經不在這裡了。")}</p>${P.focus ? `<p class="muted">${esc(PEER_GONE_ANSWER)}</p>` : ""}`
      : `<div class="peer-head">${c.mingtie ? `<button class="peer-mt" data-act="mt-zoom-peer" aria-label="看${esc(c.name)}的名帖">${mtCardHtml(c.mingtie, c.name, "thumb")}</button>` : ""}<h3>${esc(c.name)}</h3><div class="peer-title">${[...c.affiliation.split("・"), `第${c.level}級`].map((t) => `<span class="peer-seg">${esc(t)}</span>`).join("・")}</div>${peerRenownHtml(c, P)}${c.record ? `<p class="peer-record">${esc(c.record)}</p>` : ""}${c.yuedan ? `<p class="peer-record peer-yuedan">${esc(c.yuedan)}</p>` : ""}</div>
        <div class="peer-arts">${c.arts.length ? c.arts.map((a) => `<div class="peer-art"><small>${esc(a.kind)}</small><b>${esc(a.name)}</b><span>${esc(a.quality)}</span></div>`).join("") : '<p class="muted">身上沒有功夫。</p>'}</div>
        ${P.amountFor != null && c.actions[P.amountFor] ? `<form class="free peer-amount" id="peer-amount">${choiceSelect(c.actions[P.amountFor])}<input class="input" name="amount" type="number" inputmode="numeric" min="${c.actions[P.amountFor].amount_min || 1}" max="${c.actions[P.amountFor].amount}" placeholder="${esc(c.actions[P.amountFor].label)}：${c.actions[P.amountFor].amount_min || 1}～${c.actions[P.amountFor].amount}" aria-label="數量"><button class="btn primary small" type="submit">送出</button></form>` : ""}
        ${P.textFor != null && c.actions[P.textFor] ? `<form class="free peer-amount peer-text" id="peer-text"><input class="input" name="text" maxlength="${c.actions[P.textFor].text}" value="${esc(P.textDraft || "")}" placeholder="附一句話（可以不寫，${c.actions[P.textFor].text} 字內）" aria-label="附一句話"><button class="btn primary small" type="submit">${esc(c.actions[P.textFor].label)}</button></form>` : ""}
        ${c.actions.length ? peerActsHtml(c.actions) : ""}`;
    return `<div class="sheet-bg${quiet}" data-act="peer-close"></div>
      <div class="sheet peer-card${quiet}" role="dialog" aria-label="${esc(P.name)}">
        <div class="grip"></div>
        ${P.msg ? `<div class="peer-msg">${P.msg}</div>` : ""}
        ${body}
        <div class="row"><button class="btn ghost" data-act="peer-close">關閉</button></div>
      </div>`;
  }
  // 玩家卡頭銜底下一排稱號小籤（名聲 3B，card.renown：只寫稱號、不寫數字）：名望金、善惡照 path 上色；點了在卡上攤開一段
  // 通用的說明（各段代表什麼，不寫他的數字；S.peer.renownOpen）。名聲關著、還沒有稱號不畫
  const RENOWN_PEER_HELP = "江湖上用兩個稱號認人：金色的看名望（小有名氣、名動一方、威震州郡、天下聞名，越後面越多人認得），"
    + "青色的是俠（善名比惡名高：江湖遊俠、一方豪俠、州郡大俠、天下名俠），赭色的是寇（惡名高：綠林好漢、江湖巨寇、州郡大盜、天下大盜）。";
  function peerRenownToggle(el) {
    if (!S.peer) return;
    S.peer.renownOpen = !S.peer.renownOpen;
    el.setAttribute("aria-expanded", String(S.peer.renownOpen));
    const ico = el.querySelector("i");
    if (ico) ico.textContent = S.peer.renownOpen ? "▴" : "›";
    const help = el.nextElementSibling;
    if (help && help.classList.contains("rn-peer-help")) help.remove();
    if (S.peer.renownOpen) el.insertAdjacentHTML("afterend", `<p class="rn-peer-help">${esc(RENOWN_PEER_HELP)}</p>`);
  }
  function peerRenownHtml(c, P) {
    const r = c.renown;
    if (!r || !r.titles.length) return "";
    const chips = r.titles.map((t, i) => `<span class="rn-chip ${i === r.titles.length - 1 && r.path ? rnPathClass(r.path) : "rn-fame"}">${esc(t)}</span>`).join("");
    return `<div class="rn-chips" data-act="renown-peer" role="button" tabindex="0" aria-expanded="${!!P.renownOpen}">${chips}<i aria-hidden="true">${P.renownOpen ? "▴" : "›"}</i></div>`
      + (P.renownOpen ? `<p class="rn-peer-help">${esc(RENOWN_PEER_HELP)}</p>` : "");
  }
  // 卡上的鈕：同一個 group 的（論武出哪一樣，每一樣一顆）收成一個下拉清單＋一顆鈕，按下去送清單上選的那一顆（照它在 actions 裡的索引）；
  // 只有一顆的 group 照常畫。下拉清單整排佔滿一列，其餘的鈕照舊兩欄
  // 合不成的那一樣（論武答應，伺服器灰掉、pick 後面寫兩三個字的原因，FB-117）也收進清單、但挑不了（<option disabled>），
  // 預設選第一樣挑得了的；整組都挑不了時那顆鈕灰掉。答應那幾顆（arg 是 yes 開頭）標 data-answer="<互動>"：
  // 從場景底下「挑一樣答應」打開卡時捲到它（openPeer 的 focus）
  function peerActsHtml(actions) {
    const groups = {};
    actions.forEach((b, i) => { if (b.group) (groups[`${b.action}|${b.group}`] ||= []).push(i); });
    const done = new Set();
    const answer = (b) => (/^yes(:|$)/.test(b.arg || "") ? ` data-answer="${esc(b.action)}"` : "");
    // 名字包一格不折行（.pa-name）；說明放得下就跟名字並排，放不下自己換到下一行再折（style.css 的 .peer-acts，FB-220）
    const one = (b, i) => `<button class="btn" data-act="peer-act" data-i="${i}"${answer(b)} ${b.enabled ? "" : "disabled"}><span class="pa-name">${esc(b.label)}</span>${b.note ? `<small>${esc(b.note)}</small>` : ""}</button>`;
    const html = actions.map((b, i) => {
      const members = b.group ? groups[`${b.action}|${b.group}`] : null;
      if (!members || members.length < 2) return one(b, i);
      if (done.has(members)) return "";
      done.add(members);
      const first = members.find((j) => actions[j].enabled);
      const live = first !== undefined;
      return `<div class="peer-pick"${answer(b)}><select class="input" aria-label="${esc(b.group)}">${members.map((j) => `<option value="${j}"${actions[j].enabled ? "" : " disabled"}${j === first ? " selected" : ""}>${esc(actions[j].pick || actions[j].label)}</option>`).join("")}</select>`
        + `<button class="btn" data-act="peer-pick"${live ? "" : " disabled"}><span class="pa-name">${esc(b.group)}</span>${b.note ? `<small>${esc(b.note)}</small>` : ""}</button></div>`;
    }).join("");
    return `<div class="peer-acts">${html}</div>`;
  }
  // 卡上的鈕要先挑一樣（贈素材）：一個下拉選單，每一樣寫身上有幾份
  const choiceSelect = (b) => (b.choices && b.choices.length
    ? `<select class="input" name="choice" aria-label="挑一樣">${b.choices.map((x) => `<option value="${esc(x.id)}">${esc(x.label)}（${x.max}）</option>`).join("")}</select>`
    : "");
  // focus：從場景底下「挑一樣答應」打開的（FB-117）——卡畫好之後捲到那一種互動答應的那一格（data-answer）、框一下金邊。
  // 他已經不在這裡（卡打不開）時照舊寫伺服器那一句，底下多一句這份邀請怎麼辦（邀請照現在的規則：放著等逾時，或在場景底下婉拒）
  const PEER_GONE_ANSWER = "這份邀請答不成了：在場景底下按「婉拒」收掉，或放著等它逾時作廢。"; // 待 joy 潤
  async function openPeer(name, focus = "") {
    S.peer = { name, loading: true, focus };
    render();
    try {
      const r = await api(`/api/peer?name=${encodeURIComponent(name)}`);
      if (!S.peer || S.peer.name !== name) return; // 等的時候關掉或換了人
      S.peer = { name, card: r.card, gone: r.gone, focus };
    } catch (e) {
      S.peer = null;
    }
    render();
    if (focus && S.peer && S.peer.card) peerFocus(focus);
  }
  function peerFocus(focus) {
    const el = document.querySelector(`.peer-card [data-answer="${focus}"]`);
    if (!el) return;
    el.classList.add("peer-focus");
    el.scrollIntoView({ block: "nearest", behavior: promoCalm() ? "auto" : "smooth" }); // promoCalm：偏好減少動態效果
  }

  // 玩家卡開著時跟著輪詢更新（FB-117）：對方發了邀請、收回、走了，卡上的鈕要跟著變，不然按了才知道。輪詢拿到有變的畫面時重抓這張卡
  // （/api/peer，只讀），內容變了才換掉那一張（只換卡，底下的頁面不動；捲到的地方、下拉清單挑的那一樣照放回去）。
  // 不換的時候：正在送動作（S.busy）、確認框開著（它記的是舊卡上第幾顆）、數量欄攤開、正在下拉清單或輸入框上（typing）。
  // 手指按著時先收著（peerNext），放開才換——S.peer 跟畫面上那一張要是同一份，按下去的索引才對得上（同江湖頁的 pointerHeld）
  let peerPolling = false;
  let peerNext = null; // { P, r }：按著的時候抓到的新卡
  async function refreshPeer() {
    const P = S.peer;
    if (!P || P.loading || peerPolling || S.busy) return;
    peerPolling = true;
    try {
      const r = await api(`/api/peer?name=${encodeURIComponent(P.name)}`);
      if (JSON.stringify(r.card) === JSON.stringify(P.card)) return;
      if (pointerHeld) peerNext = { P, r };
      else applyPeer(P, r);
    } catch (e) { /* 下一輪再說 */ } finally { peerPolling = false; }
  }
  function applyPeer(P, r) {
    peerNext = null;
    if (S.peer !== P || S.busy || P.amountFor != null || P.textFor != null || typing() || document.querySelector(".ask-layer")) return;
    S.peer = { name: P.name, card: r.card, gone: r.gone, focus: P.focus, msg: P.msg }; // 上一個動作回的那一句照留
    const old = document.querySelector(".peer-card");
    if (!old) return;
    // 下拉清單挑的那一樣（照它的 arg 認：新卡上的索引可能不一樣）
    const picked = new Set([...old.querySelectorAll(".peer-pick select")].map((x) => (P.card && P.card.actions[Number(x.value)] || {}).arg));
    const top = old.scrollTop;
    const bg = old.previousElementSibling;
    old.insertAdjacentHTML("afterend", peerHtml(true));
    old.remove();
    if (bg && bg.classList.contains("sheet-bg")) bg.remove();
    const now = document.querySelector(".peer-card");
    if (!now) return;
    now.scrollTop = top;
    const actions = (r.card && r.card.actions) || [];
    now.querySelectorAll(".peer-pick select").forEach((x) => {
      const j = [...x.options].map((o) => Number(o.value)).find((k) => picked.has(actions[k].arg) && actions[k].enabled);
      if (j !== undefined) x.value = String(j);
    });
  }
  // 按卡上的鈕：要填數量的先問數量（prompt 在 artifact 外照常可用，但這裡一律用頁內的輸入，見 peerAmount），有 confirm 的先問一次
  // 等回應的時候（論武答應時首創要等模型取名，FB-117）：照送出指令的回饋那一套（busy），論武答應另有一句等候的話（WAIT_LINES.discuss）。
  // 回來時卡已經關了、或換成別人的卡：不把剛才那張又彈出來，結果用提示泡泡講一句短的（伺服器給的 brief：論武合成了是
  // 「論武有結果了：合出【某某】。詳見江湖紀錄。」，其餘是回話的第一句；完整的在江湖紀錄，FB-242）
  async function peerAct(i, sure = false, amount = 0, choice = "", text = null) {
    const P = S.peer;
    const b = P && P.card && P.card.actions[i];
    if (!b) return;
    if (b.amount > 0 && !amount) { S.peer.amountFor = i; render(); return; }
    if (b.text > 0 && text == null) { S.peer.textFor = i; S.peer.textDraft = ""; render(); document.querySelector("#peer-text input")?.focus(); return; } // 挑釁：先攤開一格輸入框
    if (!sure && b.confirm) { ask(b.confirm, b.label, () => peerAct(i, true, amount, choice)); return; }
    const line = b.action === "discuss" && /^yes:/.test(b.arg || "") ? WAIT_LINES.discuss : SENT_WAITING;
    await busy(async () => {
      const r = await api("/api/peer/act", { name: P.name, action: b.action, arg: b.arg, amount, choice, text: text || "" });
      if (r.main) setMain(r.main);
      if (S.peer && S.peer.name === P.name) {
        S.peer = { name: P.name, card: r.card, gone: r.gone, msg: r.message };
        // 那一句被擋下（鈕還按得下去）：輸入框照開著、打的字留著，改一改再送
        const again = text && r.card ? r.card.actions.findIndex((x) => x.action === b.action && x.arg === b.arg && x.enabled && x.text > 0) : -1;
        if (again >= 0) { S.peer.textFor = again; S.peer.textDraft = text; }
      }
      else if (r.brief || r.message) toast(r.brief || r.message.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim());
      render();
    }, line);
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
  // 批量熔煉（修練頁功法庫）：勾、勾選篩出來的全部（meltPickShown）、確認之後一次送出
  function meltToggle(key, id) {
    if (!S.meltSel || !id) return;
    const list = S.meltSel[key];
    S.meltSel = { ...S.meltSel, [key]: list.includes(id) ? list.filter((v) => v !== id) : [...list, id] };
    renderPage();
  }
  function askMeltMany(el) {
    const sel = S.meltSel;
    if (!sel || !(sel.arts.length + sel.ins.length)) return;
    const parts = [sel.arts.length ? `${sel.arts.length} 門武學` : "", sel.ins.length ? `${sel.ins.length} 個意境` : ""].filter(Boolean).join("、");
    const v = el.dataset.v | 0;
    const warn = sel.ins.length ? "靠這些意境修練的武學，熔了就不能再修練。" : "";
    ask(`把勾的 ${parts}一起熔掉？${v > 0 ? `心得 +${v}。` : ""}熔掉就沒了。${warn}`, "熔掉", async () => {
      const body = { arts: sel.arts, insights: sel.ins };
      S.meltSel = null;
      await mx("melt_many", body);
    });
  }
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
  // 合成即設計（forge_fixed）：品級定了，不畫一格 100% 的條，寫「配「風」合出來是中品」帶品級印
  const forgeOdds = (a) => (a.forge_fixed ? `<div class="odds fixed"><span>${a.forge_with ? `配「${esc(a.forge_with)}」煉製` : "拿去煉製"}合出來是</span>${seal(a.forge_fixed)}<em>${esc(a.forge_fixed)}</em></div>`
    : Array.isArray(a.forge_odds) && a.forge_odds.length ? `<div class="odds"><span>${a.forge_with ? `配「${esc(a.forge_with)}」煉製會出` : "拿去煉製會出"}</span>${a.forge_odds
    .map((o) => `<b class="${(QUALITY_SEAL[o.quality] || [, "q1"])[1]}" style="flex-grow:${Math.max(1, Number(o.pct) || 0)}">${esc(String(o.quality).slice(0, 1))} ${Number(o.pct) || 0}%</b>`).join("")}</div>` : "");

  // 功法卡、人物卡（伺服器的 Markdown）裡的十成進度「●●●○○○○○○○」換成跟卷軸卡同一種格子（企劃者 10/6：不要圈圈）。
  // 只換剛好十個圈的那一串，換成的是固定的標記，不帶任何伺服器的字
  const tenCells = (html) => String(html || "").replace(/[●○]{10}/g, (run) =>
    `<span class="ten mini" role="img" aria-label="第${[...run].filter((c) => c === "●").length}成">${[...run].map((c) => `<i${c === "●" ? ' class="on"' : ""}></i>`).join("")}</span>`);

  // 療傷鈕（FB-082，卷軸卡的兩行版）：「療傷」加一行內傷與價錢。按不按得下去由伺服器說（x.heal：沒有內傷、銀兩不夠都灰掉，原因放在
  // title 與 aria-label）；價錢是 x.heal_cost（team.heal_cost），網頁不自己算。伺服器沒給 heal（舊版）就照內傷數畫
  function healButton(x, injury) {
    const h = x.heal, hurt = injury >= 1, cost = x.heal_cost || 0;
    // 不在醫館（企劃者 2026-10-12）：鈕灰掉，第二行寫伺服器給的那一句（「這裡沒有醫館，最近的在…」）
    // note：按得下去時伺服器寫好的價錢（銀兩只夠治一部分時是「治 N 點・M 兩（還剩 K 點）」，skillview.heal_note）
    const sub = !hurt ? "沒有內傷" : h && h.clinic ? h.clinic : h && h.note ? h.note : `內傷 ${Math.round(injury)}・銀 ${cost}${h && !h.ok ? " 不夠" : ""}`;
    const why = h && h.why ? ` title="${esc(h.why)}" aria-label="療傷：${esc(h.why)}"` : "";
    return `<button class="btn" data-act="mx" data-op="heal" ${(h ? h.ok : hurt) ? "" : "disabled"}${why}>療傷<small>${dealHtml(sub)}</small></button>`;
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

  // ── 批量熔煉的判斷資料、篩選與排序（企劃者 2026-10-16「批量分解的時候無法判斷武學或內功意境的好壞……甚至是能篩選條件」）──
  // 勾的時候武學、內功、意境排成同一張清單（meltItems）：每一列寫判斷好壞要的（威力、比身上強弱、境界、功效、絕招；意境寫幾重、圓融駁雜、正邪）
  // 與熔了退多少心得，點右邊的 ▾ 攤開細節。篩選與排序只記在這一頁（S.meltView），不存瀏覽器
  const MELT_SORTS = [["", "原本的順序"], ["power", "威力低的在前"], ["quality", "品質低的在前"], ["value", "心得多的在前"]];
  const MELT_RANKS = ["", "一重", "二重", "三重", "四重", "五重"];
  const MELT_NO_GEN = "未合成"; // 境界是空字串（基礎、內容寫的武學）時篩選上寫的字
  function meltView() {
    S.meltView = S.meltView || { kind: "", attr: "", quality: "", gen: "", rank: "", weak: false, sort: "" };
    return S.meltView;
  }
  // 功法庫（身上以外的）與意境排成一份；伺服器沒給 judge（舊版）時那幾欄空著
  function meltItems(x) {
    const arts = x.owned_arts.filter((a) => !a.worn).map((a) => {
      const j = a.judge || {};
      return { t: "arts", id: a.id, name: a.name, kind: a.kind, attr: a.attribute, quality: a.quality, gen: a.gen || "", rank: 0,
        ok: !!a.melt.ok, why: a.melt.ok ? "" : a.melt.note || "", value: a.melt.value | 0, power: typeof j.power === "number" ? j.power : null,
        diff: typeof j.worn_diff === "number" ? j.worn_diff : null, j, a };
    });
    const ins = x.insights.map((i) => ({ t: "ins", id: i.id, name: i.name, kind: "意境", attr: i.attribute, quality: "", gen: "",
      rank: i.rank | 0 || (MELT_RANKS.indexOf(String(i.depth || "").split("・")[0]) > 0 ? MELT_RANKS.indexOf(String(i.depth).split("・")[0]) : 0),
      ok: !i.blocked, why: i.blocked || "", value: i.melt | 0, power: null, diff: null, i }));
    return [...arts, ...ins];
  }
  function meltPass(it, v) {
    return (!v.kind || it.kind === v.kind) && (!v.attr || it.attr === v.attr) && (!v.quality || it.quality === v.quality)
      && (!v.gen || (it.t === "arts" && (it.gen || MELT_NO_GEN) === v.gen)) && (!v.rank || it.rank === Number(v.rank))
      && (!v.weak || (it.diff !== null && it.diff < 0));
  }
  // 篩出來的、照排序排好；沒有那一項的（意境沒有威力、品質）排在最後，其餘照原本的順序（伺服器排好的）
  function meltShown(x) {
    const v = meltView();
    const list = meltItems(x).filter((it) => meltPass(it, v));
    const key = v.sort === "power" ? (it) => it.power : v.sort === "quality" ? (it) => (it.quality ? QUALITY_RANK[it.quality] * 10 + (it.quality === "絕學" ? 1 : 0) : null)
      : v.sort === "value" ? (it) => -it.value : null;
    if (!key) return list;
    return list.map((it, n) => [it, key(it), n]).sort((p, q) => (p[1] === null) - (q[1] === null) || (p[1] === null ? 0 : p[1] - q[1]) || p[2] - q[2]).map((p) => p[0]);
  }
  // 「勾選篩出來的全部」：篩出來、熔得掉的全勾；都已經勾了再按一次全部取消
  function meltPickShown() {
    if (!S.meltSel || !S.menxia) return;
    const shown = meltShown(S.menxia).filter((it) => it.ok);
    const all = shown.length && shown.every((it) => S.meltSel[it.t].includes(it.id));
    const next = { ...S.meltSel };
    for (const t of ["arts", "ins"]) {
      const ids = shown.filter((it) => it.t === t).map((it) => it.id);
      next[t] = all ? next[t].filter((id) => !ids.includes(id)) : [...new Set([...next[t], ...ids])];
    }
    S.meltSel = next;
    renderPage();
  }
  // 篩選一格一個下拉（375 寬兩欄排）：只有兩種以上的值才畫；已經選了的那一格照畫，才改得回來
  function meltFilterHtml(x) {
    const v = meltView(), items = meltItems(x);
    const vals = (f) => [...new Set(items.map(f).filter((s) => s !== "" && s !== null))];
    const qrank = (q) => (QUALITY_RANK[q] || 0) * 10 + (q === "絕學" ? 1 : 0);
    const cells = [
      ["kind", "種類", vals((it) => it.kind).sort((a, b) => ["武學", "內功", "意境"].indexOf(a) - ["武學", "內功", "意境"].indexOf(b)).map((k) => [k, k])],
      ["attr", "屬性", vals((it) => it.attr).sort().map((a) => [a, `屬${a}`])],
      ["quality", "品質", vals((it) => it.quality).sort((a, b) => qrank(a) - qrank(b)).map((q) => [q, q])],
      ["gen", "境界", vals((it) => (it.t === "arts" ? it.gen || MELT_NO_GEN : "")).sort((a, b) => ["未合成", "初成", "精進", "化境"].indexOf(a) - ["未合成", "初成", "精進", "化境"].indexOf(b)).map((g) => [g, g])],
      ["rank", "重數", vals((it) => (it.t === "ins" && it.rank ? it.rank : "")).sort().map((r) => [String(r), MELT_RANKS[r] || `${r}重`])],
    ].filter(([key, , opts]) => opts.length > 1 || v[key]);
    const sel = (key, label, opts) => `<label><span>${label}</span><select class="input" data-act="melt-view" data-key="${key}" aria-label="${label}">
      <option value="">全部</option>${opts.map(([val, text]) => `<option value="${esc(val)}"${v[key] === val ? " selected" : ""}>${esc(text)}</option>`).join("")}</select></label>`;
    const weak = items.some((it) => it.diff !== null);
    return `<div class="melt-filter">${cells.map(([key, label, opts]) => sel(key, label, opts)).join("")}
      <label><span>排序</span><select class="input" data-act="melt-view" data-key="sort" aria-label="排序">${MELT_SORTS.map(([val, text]) =>
        `<option value="${val}"${v.sort === val ? " selected" : ""}>${text}</option>`).join("")}</select></label>
      ${weak || v.weak ? `<button type="button" class="fchip melt-weak${v.weak ? " on" : ""}" data-act="melt-weak" aria-pressed="${!!v.weak}">只看比身上弱的</button>` : ""}</div>`;
  }
  const meltNum = (n) => (n > 0 ? `+${n}` : String(n).replace("-", "−"));
  // 一列：左邊勾＋品質印＋名字、判斷的一行、幾個小籤；右邊心得與攤開鈕。熔不掉的灰掉、原因寫在籤那一行
  function meltRowHtml(it, on, open) {
    const act = it.t === "arts" ? "melt-pick" : "melt-pick-ins";
    const mark = it.t === "arts" ? seal(it.quality) : '<span class="qseal qi">意</span>';
    let sub, tags = [];
    if (it.t === "arts") {
      const j = it.j;
      sub = [it.kind, `屬${it.attr}`, it.gen, `${it.a.level}成`, it.power !== null ? `威力 ${it.power}` : ""].filter(Boolean);
      if (it.diff !== null) tags.push(it.diff > 0 ? `<i class="up">比身上強 ${meltNum(it.diff)}</i>` : it.diff < 0 ? `<i class="down">比身上弱 ${meltNum(it.diff)}</i>` : "<i>跟身上一樣</i>");
      if (j.tactic) tags.push(`<i class="hi">本命戰法</i>`);
      if (j.ultimate) tags.push(`<i class="hi">絕招</i>`);
      const tr = j.traits || [];
      tr.slice(0, 2).forEach((t) => tags.push(`<i>${esc(t.name)}${t.layers > 1 ? t.layers : ""}</i>`));
      if (tr.length > 2) tags.push(`<i>+${tr.length - 2}</i>`);
      if (j.special) tags.push(`<i class="hi">${esc(j.special)}</i>`);
    } else {
      const i = it.i;
      sub = ["意境", `屬${it.attr}`, ...String(i.depth || "").split("・"), i.lean && i.lean !== "無" ? i.lean : ""].filter(Boolean);
    }
    if (!it.ok) tags = [`<i class="why">${esc(it.why)}</i>`];
    const key = `${it.t}:${it.id}`;
    return `<div class="mrow${on ? " on" : ""}${it.ok ? "" : " off"}">
      <button class="mpick pick${on ? " on" : ""}" data-act="${act}" data-id="${esc(it.id)}" ${it.ok ? "" : "disabled"} aria-pressed="${on}">
        <i class="tick" aria-hidden="true"></i>${mark}<span class="txt"><b>${esc(it.name)}</b><small>${sub.map((w) => `<span>${esc(w)}</span>`).join("・")}</small>${tags.length ? `<span class="tags">${tags.join("")}</span>` : ""}</span>
        <span class="mval">${it.ok ? (it.value > 0 ? `心得<b>${it.value}</b>` : "沒有心得") : ""}</span></button>
      <button class="mmore${open ? " on" : ""}" data-act="melt-open" data-key="${esc(key)}" aria-expanded="${open}" aria-label="${esc(it.name)}的細節">${open ? "▾" : "›"}</button>
    </div>${open ? `<div class="mdetail">${meltDetailHtml(it)}</div>` : ""}`;
  }
  function meltDetailHtml(it) {
    const lines = [];
    if (it.t === "arts") {
      const j = it.j, a = it.a;
      lines.push(`第${a.level}成${it.power !== null ? `，威力 ${it.power}` : ""}${it.gen ? `・${esc(it.gen)}` : ""}${a.insight ? `・融「${esc(a.insight)}」` : ""}`);
      if ((j.traits || []).length) lines.push(`功效：${j.traits.map((t) => `〔${esc(t.name)}〕${t.layers > 1 ? `${t.layers} 層` : ""}`).join("")}`);
      if (j.special) lines.push(`特別功效〔${esc(j.special)}〕`);
      if (j.ultimate) lines.push(`絕招〔${esc(j.ultimate)}〕`);
      if (j.tactic) lines.push(`本命戰法〔${esc(j.tactic)}〕`);
      if (a.compare) lines.push(esc(a.compare));
      if (a.relearn) lines.push(esc(a.relearn));
    } else {
      const i = it.i;
      lines.push(["意境", `屬${esc(it.attr)}`, esc(i.depth || ""), i.lean && i.lean !== "無" ? esc(i.lean) : ""].filter(Boolean).join("・"));
      if (i.note) lines.push(esc(i.note));
      if (i.own) lines.push(`悟於${esc(i.place || "某處")}・只屬於你`);
    }
    lines.push(it.ok ? (it.value > 0 ? `熔了退回心得 ${it.value}` : "熔了沒有心得，只空出一格") : esc(it.why));
    return lines.map((l) => `<p>${l}</p>`).join("");
  }

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
      { key: "內功", kind: "art", x: 26.4, y: 38.7, side: "r" },
      { key: "武學", kind: "art", x: 50.0, y: 48.6, side: "r" },
      { key: "mount", kind: "gear", x: 51.8, y: 96.7, side: "r" },
    ] },
    女: { src: "/static/hero-f.webp", ratio: "693 / 900", nodes: [
      { key: "weapon", kind: "gear", x: 47.0, y: 17.5, side: "r" },
      { key: "armor", kind: "gear", x: 42.6, y: 23.6, side: "r" },
      { key: "武學", kind: "art", x: 47.2, y: 33.8, side: "r" },
      { key: "內功", kind: "art", x: 25.0, y: 38.1, side: "l" },
      { key: "treasure", kind: "gear", x: 35.8, y: 45.3, side: "r" },
      { key: "mount", kind: "gear", x: 50.1, y: 96.9, side: "r" },
    ] },
  };
  const heroFigure = (s) => HERO_FIGURES[s && s.gender === "女" ? "女" : "男"];
  const HERO_GEAR_NAMES = { weapon: "武器", armor: "防具", mount: "坐騎", treasure: "寶物" };
  // 一個光點此刻的樣子：標籤、有沒有東西（沒有的點暗著）、底下那一格的標題、說明、按鈕
  function heroInfo(n, x, s) {
    if (n.kind === "art") {
      const a = x.owned_arts.find((r) => r.worn && r.kind === n.key);
      if (!a) return { label: n.key, lit: false, title: n.key, desc: `你身上還沒有${n.key}。`, button: "" };
      return {
        label: n.key, lit: true,
        title: `${esc(a.name)}<small>${esc(a.quality)}</small>`,
        desc: `${n.key}・屬${a.attribute}・第${a.level | 0}成${a.insight ? `・意境「${a.insight}」` : ""}`,
        button: `<button class="btn small" data-act="hero-jump" data-to="worn" data-kind="${esc(n.key)}">看這一門</button>`,
      };
    }
    const g = x.gear && x.gear.slots.find((sl) => sl.slot === n.key);
    if (!g) return null; // 這一欄關著：不畫這個點
    const label = g.label || HERO_GEAR_NAMES[n.key];
    if (!g.worn) return { label, lit: false, title: label, desc: g.empty || "", button: "" };
    const w = g.worn;
    const desc = n.key === "weapon" ? `${w.noun || w.kind}・屬${w.attribute}${w.grade ? `・${w.grade}` : ""}・鋒利度 ${w.edge | 0}${w.bonus ? `・威力 ${w.bonus}` : "・用不上"}`
      : n.key === "armor" ? `屬${w.attribute}・${w.grade}・${w.wear_word} ${w.edge | 0}・少扣 ${w.cut} 氣血`
      : n.key === "mount" ? `${w.grade}・${w.wear_word} ${w.edge | 0}・疾行省 ${w.save} 體力・路上快 ${w.speed}`
      : w.effect_text || "";
    return {
      label, lit: true,
      title: `【${esc(w.name)}】<small>${esc(label)}</small>`,
      desc,
      button: `<button class="btn small" data-act="hero-jump" data-to="gear" data-kind="${esc(n.key)}">看這件</button>`,
    };
  }
  function heroFoot(n, info) {
    return `<div class="hero-ft-title">${info.title}</div>
      <div class="hero-ft-row"><p>${esc(info.desc)}</p>${info.button}</div>`;
  }
  function heroPanel(x, s) {
    const fig = heroFigure(s);
    const nodes = fig.nodes.map((n) => [n, heroInfo(n, x, s)]).filter(([, info]) => info);
    if (!nodes.length) return "";
    const pick = nodes.find(([n]) => n.key === S.heroNode) || nodes.find(([n]) => n.key === "內功") || nodes[0];
    return `<section class="hero" aria-label="人物">
      <div class="hero-hd">
        <div><div class="hero-name">${esc(s.name)}</div><div class="hero-tag">${esc(s.affiliation)}</div></div>
        <div class="hero-sub"><div>第 ${s.level | 0} 級</div><div>氣血 ${s.hp | 0}／${s.hp_max | 0}</div></div>
      </div>
      <div class="hero-stage">
        <div class="hero-halo" aria-hidden="true"></div>
        <div class="hero-fig" style="aspect-ratio:${fig.ratio}">
          <img src="${fig.src}" alt="" draggable="false">
          ${nodes.map(([n, info]) => `<button class="hero-node${n === pick[0] ? " on" : ""}${info.lit ? "" : " dim"} ${n.side}" style="left:${n.x}%;top:${n.y}%" data-act="hero-node" data-key="${esc(n.key)}" aria-label="${esc(info.label)}"><i class="pulse"></i><i class="dot"></i><span>${esc(info.label)}</span></button>`).join("")}
        </div>
      </div>
      <div class="hero-ft" id="hero-ft">${heroFoot(pick[0], pick[1])}</div>
    </section>`;
  }
  // 點光點：只換點的樣子與底下那一格、在點上散一圈朱砂（不重畫整頁，水墨的動畫才不會斷）
  function heroTap(el) {
    const key = el.dataset.key;
    const n = S.main && heroFigure(S.main.status).nodes.find((h) => h.key === key);
    const info = n && S.menxia && S.main && heroInfo(n, S.menxia, S.main.status);
    if (!info) return;
    S.heroNode = key;
    document.querySelectorAll(".hero-node.on").forEach((b) => b.classList.remove("on"));
    el.classList.add("on");
    const ft = document.getElementById("hero-ft");
    if (ft) ft.innerHTML = heroFoot(n, info);
    const ripple = document.createElement("i");
    ripple.className = "hero-ripple";
    ripple.style.left = el.style.left;
    ripple.style.top = el.style.top;
    el.parentNode.appendChild(ripple);
    setTimeout(() => ripple.remove(), 600);
  }
  function heroJump(el) {
    const target = el.dataset.to === "worn"
      ? document.querySelector(`.acard[data-worn="${el.dataset.kind}"]`)
      : document.querySelector(`.gear-slot[data-slot="${el.dataset.kind}"]`);
    if (target) target.scrollIntoView({ block: "start", behavior: "smooth" });
  }

  // 以心得換破境丹（Joy 2026-10-18）：衝絕學那一步的卡上一顆小鈕；換不了時灰掉、原因寫在後面（a.cultivate.buy 是伺服器算好的）
  function buyPill(a) {
    const xs = a.cultivate.xinde; // 以心得修練：付心得不付體力；換不了時灰掉、原因寫在後面
    const byX = xs ? `<div class="buy-pill"><button class="btn small" data-act="cultivate" data-xinde="1" data-id="${esc(a.id)}" ${xs.ok ? "" : "disabled"} title="${esc(xs.why)}">${esc(xs.label)}</button>${xs.ok ? "" : `<span class="why">${esc(xs.why)}</span>`}</div>` : "";
    const b = a.cultivate.buy;
    if (!b) return byX;
    return byX + `<div class="buy-pill"><button class="btn small" data-act="mx" data-op="buy_legend" ${b.ok ? "" : "disabled"} title="${esc(b.why)}">${esc(b.label)}</button>${b.ok ? "" : `<span class="why">${esc(b.why)}</span>`}</div>`;
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
        <div class="lvline"><b>第${level}成</b><span>${esc(a.kind)}・屬${esc(a.attribute)}${a.gen ? `・${esc(a.gen)}` : ""}${a.insight ? `・意境「${esc(a.insight)}」` : ""}</span></div>
        ${compare}
        <div class="acts">${first}${cult}</div>
        ${S.artNote && S.artNote.id === a.id ? `<div class="msg art-result">${S.artNote.html}</div>` : ""}
        ${lg ? `<label class="legend"><input type="checkbox" data-legend="${esc(a.id)}" ${ticked ? "checked" : ""}><span>${esc(lg.label)}</span></label>` : ""}
        ${buyPill(a)}
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
      return `<div class="acard ${(QUALITY_SEAL[a.quality] || [, "q1"])[1]}" data-worn="${esc(k)}">
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
    // 批量熔煉（企劃者 2026-10-14「合成越來越多，需要能快速熔煉的機制」）：S.meltSel 是勾著的 { arts, ins }（id 串列），null＝沒在勾。
    // 勾的時候功法庫整份列出（不分頁）、每一列一個勾，意境的籤也能勾；底下浮一條「熔掉 N 樣・心得 +X」。序章裡不給（照師父一門一門熔）
    const meltOn = !!S.meltSel;
    const showAll = meltOn || S.libAll || picked.length <= LIB_PAGE + 2; // 只多一兩門就直接列完，不必多按一次
    const first = picked.slice(0, LIB_PAGE);
    const openArt = picked.find((a) => a.id === S.artOpen);
    const rows = showAll ? picked : openArt && !first.includes(openArt) ? [...first, openArt] : first; // 展開著的那一門排在第 8 門之後時也要看得到
    // 序章指路：收著的這一列發光，要按的是它裡面的改練、修練、熔煉（要先點開它）。哪一列、哪幾個鍵由伺服器說（a.glow，只有序章裡才有；
    // art_rows 照序章的拒絕算過：改練只有師父點名的那一門、修練、熔煉只有按得下去的），網頁不猜（T7 走查 W-A）
    const libRow = (a) => {
      const todo = ["switch", "cultivate", "melt"].filter((key) => (a.glow || []).includes(key)).join(" ");
      const open = S.artOpen === a.id;
      return `<button class="art libr ${open ? "on" : ""}" data-act="art" data-id="${esc(a.id)}"${todo && !open ? ` data-glow="${todo}"` : ""}>${seal(a.quality)}<span class="txt"><b>${esc(a.name)}</b><small>${esc(a.kind)}・屬${esc(a.attribute)}${a.gen ? `・${esc(a.gen)}` : ""}・第${a.level}成${a.insight ? `・「${esc(a.insight)}」` : ""}</small></span></button>
        ${open ? `<div class="art-body ${(QUALITY_SEAL[a.quality] || [, "q1"])[1]}">${body(a, null)}</div>` : ""}`;
    };
    const tutorial = x.owned_arts.some((a) => a.glow) || x.insights.some((i) => i.blocked);
    const meltable = lib.filter((a) => a.melt.ok);
    const meltSwitch = !tutorial && meltable.length + x.insights.length >= 2
      ? `<button class="linkish melt-mode" data-act="melt-mode">${meltOn ? "收起" : "批量熔煉"}</button>` : "";
    // 勾著的照現在的功法庫過一遍：熔掉了、輪詢回來已經不在的、改成熔不掉的（換上身了）不算
    const sel = S.meltSel ? {
      arts: S.meltSel.arts.filter((id) => meltable.some((a) => a.id === id)),
      ins: S.meltSel.ins.filter((id) => x.insights.some((i) => i.id === id)),
    } : { arts: [], ins: [] };
    if (meltOn) S.meltSel = sel;
    // 勾的時候：篩選、排序（meltFilterHtml／meltShown）與「勾選篩出來的全部」；清單是武學、內功、意境同一張（meltRowHtml）
    const shown = meltOn ? meltShown(x) : [];
    const shownOk = shown.filter((it) => it.ok);
    const allShown = shownOk.length > 0 && shownOk.every((it) => sel[it.t].includes(it.id));
    const meltTools = meltOn ? `${meltFilterHtml(x)}<div class="melt-tools"><span>篩出 ${shown.length} 樣</span>
        ${shownOk.length ? `<button class="${allShown ? "on" : ""}" data-act="melt-shown">${allShown ? "✓ " : ""}勾選篩出來的全部 ${shownOk.length}</button>` : ""}
        <button data-act="melt-clear">全不勾</button></div>` : "";
    const meltList = meltOn ? (shown.length ? `<div class="lib mlist">${shown.map((it) => meltRowHtml(it, sel[it.t].includes(it.id), S.meltOpen === `${it.t}:${it.id}`)).join("")}</div>`
      : '<p class="muted">沒有合這些條件的功法與意境。</p>') : "";
    const meltValue = sel.arts.reduce((sum, id) => sum + ((lib.find((a) => a.id === id) || {}).melt?.value | 0), 0)
      + sel.ins.reduce((sum, id) => sum + ((x.insights.find((i) => i.id === id) || {}).melt | 0), 0);
    const meltCount = sel.arts.length + sel.ins.length;
    const meltGo = meltOn ? `<div class="melt-gap"></div><div class="melt-go"><span>已勾 <b>${meltCount}</b> 樣<small>心得 +${meltValue}</small></span>
        <button class="btn" data-act="melt-mode">取消</button>
        <button class="btn danger" data-act="melt-go" data-n="${meltCount}" data-v="${meltValue}" ${meltCount ? "" : "disabled"}>熔掉</button></div>` : "";
    const chips = lib.length > LIB_PAGE ? `<div class="lib-filter">${LIB_FILTERS.map(([f, label]) => {
      const n = lib.filter((a) => pass(a, f)).length;
      return `<button class="${filter === f ? "on" : ""}" data-act="lib-filter" data-filter="${f}">${label} ${n}</button>`;
    }).join("")}</div>` : "";
    // 意境：一顆一顆的籤，點一下攤開模型寫的那句說明與「化成心得」
    const insOpen = x.insights.find((i) => i.id === S.insOpen);
    const insChips = x.insights.map((i) => `<button class="${S.insOpen === i.id ? "on" : ""}" data-act="ins-open" data-id="${esc(i.id)}">${i.own ? glyphSvg(i.glyph, "glyph-mini") : ""}「${esc(i.name)}」<small>屬${esc(i.attribute)}${i.lean !== "無" ? `・${esc(i.lean)}` : ""}${i.depth ? `・${esc(i.depth)}` : ""}</small></button>`).join("");
    // 名冊只有本人一列（還沒有同伴）時跟上面的本人卡重複，不畫（C6）
    const mates = x.roster.length > 1;
    // 裝備（裝備四欄設計 2.5）：開著的欄位一段一段（武器、防具、坐騎、寶物），每段先列身上那件、再列裝備庫裡同一欄的。
    // 格數四欄合算（gear.used／gear.cap）。字都是伺服器給的資料，一律 esc。這一版畫不出的欄位（新伺服器多了一欄）整段略過。
    // FB-125（兵器第二批 Task 1）：名字與說明在左邊（.winfo，塞不下自己折行），「換上」「拆解」包在右邊一個不折行的 .wbtns 裡；拆解按了先問一次（data-confirm）
    const gear = x.gear;
    // 神器原品不能拆（打造隱藏配方設計 5.4）：伺服器給 keep（原因），拆解鈕灰掉寫它，不送、不問
    // 神器 15 級才穿得上（正式季整合 5.8）：伺服器給 wield_ok／wield_note（同坐騎那一列），「換上」灰掉、原因寫在說明底下與 title
    const rowButtons = (w) => `<div class="wbtns"><button class="btn small" data-act="wield" data-id="${esc(w.id)}"${w.wield_ok === false ? ` disabled title="${esc(w.wield_note || "")}"` : ""}>換上</button>${w.keep
      ? `<button class="btn small ghost" disabled>${esc(w.keep)}</button>`
      : `<button class="btn small ghost" data-act="dismantle" data-id="${esc(w.id)}" data-confirm="${esc(w.confirm || "")}">拆解</button>`}</div>`;
    // 神器原品定名（打造隱藏配方設計 5.2）：還沒定名的原品那一列底下一張表單——自己打一個名字，或「沿用譜名【…】」。
    // 一個人可以同時有好幾把，表單照裝備 id 各一張（data-op 認，id 不重複）。名字合不合格由伺服器驗；字一律 esc。整段待 joy 潤
    // 表單接在 .wrow 的外面、緊貼著它底下（.wrow 是橫排的 flex，放進去會被擠到鈕的右邊）
    const divineForm = (w) => divineFormHtml(w.id, w.divine.pattern, false, w.divine.unit); // 店面的出爐卡與裝備庫共用同一張（divineFormHtml）；量詞照伺服器給的（FB-197）
    // 以器配招（玩家武學追上本命定案 四）：自己手上還沒配招的神器原品那一列底下一小塊：挑一門有絕招的絕學、按「以器配招」（綁了不能改配）。
    // 沒有配得上的寫一句怎麼才有。select 的 id 帶裝備 id 的冒號，用 getElementById 找
    const bindForm = (w) => !w.bind ? "" : `<div class="gear-bind">${w.bind.options.length
      ? `<small>以器配招：把這件綁在你一門絕學上，那一招更強（綁了不能改配）</small>
        <div class="row"><select class="input" id="bind-art-${esc(w.id)}">${w.bind.options.map((o) => `<option value="${esc(o.id)}">【${esc(o.name)}】${esc(o.bond)}</option>`).join("")}</select>
        <button class="btn small primary" data-act="bind-art" data-id="${esc(w.id)}">以器配招</button></div>`
      : `<small class="muted">以器配招：自己合成的武學練成絕學、有了絕招，就能把這件神器綁在那一門上。</small>`}</div>`;
    // 武器：淬過的寫「淬煉 N/5」，自己打的寫配方（兵器第二批 Task 8）
    // 待 joy 潤：「淬煉 N/M」「配方 …」這兩段字
    const weaponRow = (w, wornNow) => `<div class="wrow${w.fits ? "" : " muted"}">
        <div class="winfo"><b>【${esc(w.name)}】</b><span>${esc(w.noun || w.kind)}・屬${esc(w.attribute)}${w.grade ? `・${esc(w.grade)}` : ""}${w.tempers ? `・淬煉 ${w.tempers | 0}/${w.temper_max | 0}` : ""}・鋒利度 ${w.edge | 0}${w.bonus ? `・威力 ${esc(w.bonus)}` : "・用不上"}</span>${w.recipe ? `<small class="muted">配方 ${esc(w.recipe)}</small>` : ""}${(w.tactic || []).map((t) => `<small class="gear-tactic">${esc(t)}</small>`).join("")}${w.wield_ok === false && !wornNow ? `<small class="rwhy">${esc(w.wield_note || "")}</small>` : ""}</div>
        ${wornNow ? "" : rowButtons(w)}
      </div>${w.divine ? divineForm(w) : ""}${bindForm(w)}`;
    // 防具：不分種類、沒有「配不上」；寫耐久度與這件一場少扣幾成氣血、對不對得上你的內功（裝備四欄設計 4.1、4.2）。
    // 磨損的叫法照伺服器給的 wear_word（equipment.WEAR_WORDS，2.5、3.1），不寫死。這一行的寫法待 joy 潤；淬過的寫「淬煉 N/M」、自己打的寫配方（防具打造，同武器列）
    const armorRow = (a, wornNow) => `<div class="wrow">
        <div class="winfo"><b>【${esc(a.name)}】</b><span>屬${esc(a.attribute)}・${esc(a.grade)}${a.tempers ? `・淬煉 ${a.tempers | 0}/${a.temper_max | 0}` : ""}・${esc(a.wear_word)} ${a.edge | 0}・少扣 ${esc(a.cut)} 氣血${a.fit ? `・${esc(a.fit)}` : ""}</span>${a.recipe ? `<small class="muted">配方 ${esc(a.recipe)}</small>` : ""}${(a.tactic || []).map((t) => `<small class="gear-tactic">${esc(t)}</small>`).join("")}${a.wield_ok === false && !wornNow ? `<small class="rwhy">${esc(a.wield_note || "")}</small>` : ""}</div>
        ${wornNow ? "" : rowButtons(a)}
      </div>${a.divine ? divineForm(a) : ""}${bindForm(a)}`;
    // 坐騎（裝備四欄設計第五節）：駑馬、良駒、名駒的階品，飽足度（照伺服器給的 wear_word）、疾行省幾成體力、路上快幾成、
    // 決戰強攻奇襲多幾成、落敗脫身的機會（2.5：後三項寫在修練頁這一列，不擠進角色卡）。
    // 身上那匹一顆「餵」（餵不了的灰掉、寫為什麼；餵得了寫用哪一種素材），裝備庫裡的只有「換上」：坐騎不能拆（4.8），不用 rowButtons；
    // 路上不能換坐騎（2.3），「換上」照伺服器給的 wield_ok 灰掉、寫 wield_note（同「餵」的灰掉做法）。
    // FB-137：灰掉的鈕上只寫動詞（原因寫在鈕上，會把左邊的說明擠成一行六、七個字、那一列變 4～6 行）；原因放鈕的 title，
    // 也寫在這一列自己的說明底下（.rwhy；手機沒有 title 可看）。能按的「餵」照舊寫用哪一種素材（短）。
    // 這一行的寫法待 joy 潤
    const mountRow = (h, wornNow) => {
      const why = wornNow ? (h.feed ? "" : h.feed_note || "") : (h.wield_ok ? "" : h.wield_note || "");
      return `<div class="wrow">${horseImg(h.art, "horse-thumb")}
        <div class="winfo"><b>【${esc(h.name)}】</b><span>${esc(h.grade)}・${esc(h.wear_word)} ${h.edge | 0}・疾行省 ${esc(h.save)} 體力・路上快 ${esc(h.speed)}・決戰強攻奇襲 +${esc(h.cavalry)}・落敗脫身 ${esc(h.escape)}</span>${why ? `<small class="rwhy">${esc(why)}</small>` : ""}</div>
        <div class="wbtns">${wornNow
          ? (h.feed ? `<button class="btn small" data-act="feed">餵${h.feed_note ? `（${esc(h.feed_note)}）` : ""}</button>` : `<button class="btn small" data-act="feed" disabled${why ? ` title="${esc(why)}"` : ""}>餵</button>`)
          : `<button class="btn small" data-act="wield" data-id="${esc(h.id)}"${h.wield_ok ? "" : ` disabled${why ? ` title="${esc(why)}"` : ""}`}>換上</button>`}</div>
      </div>`;
    };
    // 寶物（裝備四欄設計第六節）：一件一種效果、不分階品、不磨損；身上那件寫效果，裝備庫裡的只有「換上」（寶物不能拆，4.8，不用 rowButtons）。
    // 寶物隨時能換（2.3【定】，企劃者 2026-10-11），「換上」不灰掉。這一行的寫法待 joy 潤
    const treasureRow = (t, wornNow) => `<div class="wrow">
        <div class="winfo"><b>【${esc(t.name)}】</b><span>${esc(t.effect_text)}</span></div>
        ${wornNow ? "" : `<div class="wbtns"><button class="btn small" data-act="wield" data-id="${esc(t.id)}">換上</button></div>`}
      </div>`;
    // 修練頁其他動作的結果（mxPlace）：寫在按的那一塊裡，頁首那一行不寫
    const noteAt = (at) => S.mxNote && S.mxNote.at === at ? `<div class="msg mx-note">${S.mxNote.html}</div>` : "";
    const GEAR_ROWS = { weapon: weaponRow, armor: armorRow, mount: mountRow, treasure: treasureRow };
    const slotBlock = (g) => {
      const row = GEAR_ROWS[g.slot];
      if (!row) return "";
      const shown = S.rackAll || g.rack.length <= LIB_PAGE ? g.rack : g.rack.slice(0, LIB_PAGE);
      // 傳承那一列（玉璽碎片的抄本，玉璽碎片設計 7.3）：寶物段身上那件之前，沒有鈕；寶物的開關關著、只有傳承時不寫「身上沒有寶物」（待 joy 潤）
      return `<section class="gear-slot" data-slot="${esc(g.slot)}"><div class="sub">${esc(g.label)}</div>${noteAt("gear:" + g.slot)}
        ${g.fit_line ? `<p class="muted gear-fit">${esc(g.fit_line)}</p>` : ""}
        ${g.heirloom ? `<div class="wrow heirloom"><div class="winfo"><b>【${esc(g.heirloom.name)}】</b><span>傳承・${esc(g.heirloom.effect_text)}</span></div></div>` : ""}
        ${g.worn ? row(g.worn, true) : g.heirloom && !g.rack.length ? "" : `<p class="muted">${esc(g.empty)}</p>`}
        ${shown.map((w) => row(w, false)).join("")}
        ${shown.length < g.rack.length ? `<button class="btn ghost lib-more" data-act="rack-all">再列 ${g.rack.length - shown.length} 件</button>` : ""}
        <p class="muted">${esc(g.note)}</p>
      </section>`;
    };
    // 寄放著的東西（裝備四欄 6.5：懸賞的重賞、名將贈禮在裝備庫滿了時先寄放）寫在塊底下一行灰字；身上、裝備庫都空著也照樣畫這一塊
    const heldLine = gear && gear.held_note ? `<p class="muted">${esc(gear.held_note)}</p>` : "";
    // 塊名由「兵器」改成「裝備」（待 joy 潤）；段名（武器、防具）是伺服器給的 label
    const hasGear = gear && (heldLine || gear.slots.some((g) => g.worn || g.heirloom || g.rack.length)); // 傳承那一列（玉璽碎片）也算有東西
    // FB-138：開著的欄位都空著、也沒有寄放的（新角色）也畫一塊精簡的：每欄一行，欄名、空著的那一句、哪裡買得到（where，伺服器照內容的地點標籤給；
    // 內容裡沒有那種地點時是空字串，只寫空著的那一句）。沒有按鈕、沒有格數。這一版畫不出的欄位略過；四欄都關著（slots 空）整塊不畫。待 joy 潤
    const emptyLines = gear && !hasGear ? gear.slots.filter((g) => GEAR_ROWS[g.slot]).map((g) => `<p data-empty="${esc(g.slot)}"><b>${esc(g.label)}</b>　${esc(g.empty)}${g.where ? esc(g.where) : ""}</p>`) : [];
    const gearBlock = hasGear ? `<div class="gear"><div class="label">裝備 <small class="muted">裝備庫 ${gear.used | 0}/${gear.cap | 0}</small></div>
        ${gear.slots.map(slotBlock).join("")}
        ${heldLine}
      </div>` : emptyLines.length ? `<div class="gear gear-empty"><div class="label">裝備 <small class="muted">身上還沒有任何裝備</small></div>
        ${emptyLines.join("")}
      </div>` : "";
    return `
      ${proGuide()}
      ${heroPanel(x, s)}
      <div class="msg" id="mx-msg">${S.message}</div>
      ${naming}
      <div class="tune">
        ${healButton(x, s.injury)}
        <form id="seclude" class="seclude">
          <button class="btn" type="submit" ${x.seclude_blocked ? "disabled" : ""}>閉關<small>得心得，氣血回復加倍</small></button>
          <select class="input" name="hours" aria-label="閉關幾小時">${[1, 2, 4, 6, 8, 12].map((h) => `<option value="${h}" ${h === 8 ? "selected" : ""}>${h} 小時</option>`).join("")}</select>
        </form>
      </div>
      ${noteAt("heal")}
      ${x.seclude_blocked ? `<p class="muted">${esc(x.seclude_blocked)}</p>` : ""}
      ${attrNoteHtml(x)}
      <div class="label">身上的兩門</div>
      ${worn}
      ${gearBlock}
      <div class="label">功法庫 <small class="muted">武學與意境 ${x.holdings.count}/${x.holdings.cap}</small>${meltSwitch}</div>
      ${S.meltNote ? `<div class="msg melt-result">${S.meltNote}</div>` : ""}
      ${meltOn ? `<p class="muted melt-hint">點一列勾起來，再按底下的「熔掉」；點右邊的 › 看細節。身上正在練的與本命武學熔不掉。</p>
      ${meltTools}
      ${meltList}` : `${chips}
      ${lib.length ? (picked.length ? `<div class="lib">${rows.map(libRow).join("")}</div>` : '<p class="muted">這一類沒有功法。</p>')
        : '<p class="muted">功法庫是空的。合成出來的武學、學來的武學會放在這裡。</p>'}
      ${showAll ? "" : `<button class="btn ghost lib-more" data-act="lib-all">再列 ${picked.length - LIB_PAGE} 門</button>`}`}
      ${meltOn ? "" : `<div class="label">意境</div>
      ${x.insights.length ? `<div class="ins">${insChips}</div>${noteAt("ins")}
        ${insOpen && !meltOn ? `<div class="insight"><div>${insOpen.own ? glyphSvg(insOpen.glyph, "glyph-big") : ""}<b>「${esc(insOpen.name)}」</b>${insOpen.note ? `<p>${esc(insOpen.note)}</p>` : ""}${insOpen.own ? `<p class="glyph-from">悟於${esc(insOpen.place || "某處")}・只屬於你</p>` : ""}</div>
          <button class="btn small" data-act="melt-insight" data-id="${esc(insOpen.id)}" data-name="${esc(insOpen.name)}" ${insOpen.blocked ? "disabled" : ""}>化成心得 ${insOpen.melt}</button>${insOpen.blocked ? `<small class="muted">${esc(insOpen.blocked)}</small>` : ""}</div>` : ""}`
        : '<p class="muted">還沒悟到任何意境。去探索，荒郊野外最容易有所領悟。</p>'}`}
      <div class="label">門下</div>
      <details class="fold" open><summary>本人</summary><div class="fold-body">${tenCells(x.player_card)}</div></details>
      ${mates ? `<div class="list">${x.roster.map((r) => `<button class="${x.person === r.key ? "on" : ""}" data-act="person" data-key="${esc(r.key)}">${esc(r.label)}</button>`).join("")}</div>` : ""}
      ${mates && x.person ? `<div class="card person-card">${tenCells(x.person_card)}${noteAt("person")}
        ${x.person === "player" ? '<p class="muted">本人一直都在隊伍裡。</p>' // 本人不能加入、移出（引擎也會擋）
          : x.person.startsWith("follower:") ? "" // 部下（計畫 T5）也不能加入、移出；角色卡已經寫了
          : `<button class="btn ${x.on_team ? "" : "primary"}" data-act="mx" data-op="${x.on_team ? "leave" : "join"}">${x.on_team ? "移出隊伍" : "加入隊伍"}</button>`}
        ${x.release ? `<button class="btn ghost" data-act="release-mate" data-confirm="${esc(x.release.confirm)}">放他回江湖</button>` : ""}
        ${lessonsHtml(x.lessons)}</div>` : ""}
      <details class="fold"><summary>修練的規矩</summary><div class="fold-body">${x.rules}</div></details>
      ${meltGo}`;
  }

  // 傳功門下（Config.chuangong）：人物卡底下一排鈕，鈕上寫要練什麼與心得，底下一行寫效果；按不下去的灰掉、原因寫在效果那一行
  function lessonsHtml(rows) {
    if (!rows || !rows.length) return "";
    return `<div class="label">傳功</div><div class="lessons">${rows.map((r) =>
      `<button class="btn small" data-act="teach" data-what="${esc(r.what)}" ${r.problem ? "disabled" : ""}${r.problem ? ` title="${esc(r.problem)}"` : ""}>${esc(r.label)}<small>${esc(r.problem || r.effect)}</small></button>`).join("")}</div>`;
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
  // 鎖在爐裡（Joy 2026-10-19「弄一個鎖定的功能，尤其獲得新意境時會想要試他的所有組合」）：一次鎖一樣，開爐成了它留在爐裡、
  // 只清另一格，接著再放一樣就能試下一個組合；拿出來、熔掉、合掉就解開
  const isLocked = (p) => !!(p && S.forgeLock && S.forgeLock.type === p.type && S.forgeLock.id === p.id);
  function toggleLock(i) {
    const p = S.forgeSel[i];
    if (!p) return;
    S.forgeLock = isLocked(p) ? null : { type: p.type, id: p.id };
    renderPage();
  }
  let potFlashTimer = 0;
  function pick(type, id) {
    if (S.busy) return; // 開爐等結果的時候（首次取名要等模型）爐子不動
    if (S.forgeSel.length >= 2) { toast("爐裡已經放滿了，點上面的拿出來再換。"); return; }
    if (type === "art" && S.forgeSel.some((p) => p.type === "art" && p.id === id)) return; // 同一門不放兩次（下面那顆 chip 也是灰的）
    const no = pickMark(type, id);
    if (no) { toast(no.why); return; } // 跟爐裡那一樣合不了（伺服器照開爐時的判斷算好的）：說為什麼，不放進去
    if (type === "art") S.forgeSel.unshift({ type, id }); else S.forgeSel.push({ type, id }); // 武學放左邊
    if (forgeReady()) S.craftPick = false; // 兩格放滿：抽屜收起，看預覽
    S.potFlash = S.forgeSel.findIndex((p) => p.type === type && p.id === id); // 剛放進去的那一格閃一下（固定列上看得到，不必捲回爐子）
    renderPage();
    clearTimeout(potFlashTimer); // 說明那一行回來時會再畫一次：閃的那一格撐到動畫跑完才收
    potFlashTimer = setTimeout(() => { S.potFlash = null; }, 900);
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
  // 太極爐一直看得到（Joy 2026-10-17「合成的時候也會因為要把畫面拉到下面看不到爐子的內容」，之後「那個太極爐變得很多餘」）：
  // 爐子本身就是開爐的地方，沒有另一條列。往下捲去挑東西、大爐子捲出畫面時，同一座爐縮成一條黏在狀態列底下（.kiln.compact，fixedKiln）：
  // 左右兩格（點了拿出來）、中間小太極就是開爐鈕，開不了爐的原因寫在底下一行。大爐子那一格的高度由 .kiln-wrap 撐著，縮起來頁面不跳。
  // 剛放進去的那一格大小兩座都閃一下（S.potFlash：第幾格）
  // 開不了爐的原因（說明那一行 ⚠ 後面那一句）：縮起來的爐子底下一行；說明回來時只換這一格（updateForgeLine）
  function kilnWarn() {
    if (S.forgePreview) return kilnPeek(S.forgePreview); // 兩格放好：縮起來的爐子底下帶著預覽，不用滑回上面看
    const warn = String(S.forgeLine || (S.menxia && S.menxia.forge_line) || "").replace(/<[^>]+>/g, " ").split("⚠")[1];
    return warn && warn.trim() ? `<p class="kiln-warn">⚠ ${esc(warn.replace(/\s+/g, " ").trim())}</p>` : "";
  }
  // 縮起來的爐子底下的預覽（Joy 2026-10-19「玩家要先往下滑滑滑選選選，然後還要重新滑到最上面看可能出現什麼」）：
  // 預覽卡濃縮成兩行——品級印、會合出什麼、屬性、境界、第幾成；功效與亮幾格、離下一品的提示；開不了爐的原因照舊一行。
  // 點了捲回上面看整張卡。資料同 previewCardHtml（S.forgePreview）
  function kilnPeek(v) {
    const merge = v.kind === "合併";
    const badge = merge ? '<span class="qseal qi">意</span>' : v.quality ? seal(v.quality) : '<span class="qseal q1">？</span>';
    const head = [v.made, v.attribute ? `屬${v.attribute}` : "", merge ? v.depth : v.gen, v.level > 1 ? `第${v.level}成` : ""].filter(Boolean).map(esc).join("・");
    const tags = (v.traits || []).map((t) => `${esc(t.name)}${t.layers > 1 ? ` ×${t.layers}` : ""}`);
    const line2 = [tags.length ? `功效 ${tags.join("、")}` : "", v.slots, v.near].filter(Boolean).map(esc).join("・")
      || (!v.quality && v.odds ? `品質看造化：${esc(v.odds)}` : "");
    return `<button type="button" class="kiln-peek" data-act="peek" aria-label="看整張預覽卡">${badge}<span><b>${head}</b>${line2 ? `<small>${line2}</small>` : ""}</span></button>
      ${v.problem ? `<p class="kiln-warn">⚠ ${esc(v.problem)}</p>` : ""}`;
  }
  function kilnHtml(slots, ready) {
    // 放了東西的格子右下角一顆小鎖（同大爐子的 pot-lock），鎖著的那一格金邊；兩顆鈕不能套在一起，所以包一層 .kiln-cell
    const cell = (m, i) => m
      ? `<div class="kiln-cell"><button class="kiln-slot full r${m.rank}${S.potFlash === i ? " flash" : ""}${isLocked(S.forgeSel[i]) ? " locked" : ""}" data-act="unslot" data-i="${i}" aria-label="拿出${esc(m.name)}"><b>${esc(m.name)}</b><small>${esc(m.sub)}</small><i aria-hidden="true">×</i></button>
          <button type="button" class="kiln-pin${isLocked(S.forgeSel[i]) ? " on" : ""}" data-act="pot-lock" data-i="${i}" aria-pressed="${isLocked(S.forgeSel[i])}" aria-label="${isLocked(S.forgeSel[i]) ? "解開" : "鎖住"}${esc(m.name)}">鎖</button></div>`
      : `<button type="button" class="kiln-slot empty" data-act="pot-open"${potGlow()}><small>${i ? "再放一樣" : "放一樣"}</small></button>`;
    const r = 20;
    const taichi = `<svg class="kiln-taichi" viewBox="-24 -24 48 48" aria-hidden="true"><circle r="26.5" class="kiln-ember"/><circle r="24.2" class="kiln-ring"/><circle r="23" class="w-hub-rim"/><g class="w-spin" style="${spinAt(ready ? 3 : 28)}">
      <circle r="${r}" class="w-yang"/><path d="M0,${-r} A${r},${r} 0 0 1 0,${r} A${r / 2},${r / 2} 0 0 1 0,0 A${r / 2},${r / 2} 0 0 0 0,${-r} Z" class="w-yin"/>
      <circle cy="${-r / 2}" r="${r / 7}" class="w-yang"/><circle cy="${r / 2}" r="${r / 7}" class="w-yin"/><circle r="${r}" class="w-seam"/></g></svg>`;
    return `<div class="kiln-wrap" id="kiln-wrap"><div class="kiln" id="kiln">
      <div class="kiln-big">${furnaceSvg(slots, ready)}</div>
      <div class="kiln-mini">
        <div class="kiln-row">${cell(slots[0], 0)}
          <button class="kiln-hub${ready ? " ready" : ""}" id="forge" data-act="forge" data-glow="forge" ${ready ? "" : "disabled"}>${taichi}<span class="kiln-lab">開爐</span></button>
          ${cell(slots[1], 1)}</div>
        <div id="kiln-warn">${kilnWarn()}</div>
      </div></div></div>`;
  }
  // 大爐子捲出狀態列底下時縮成一條、捲回來時放大：捲動時與每次畫完煉製頁都量一次（renderPage 的 afterPage 之後）
  function fixedKiln() {
    const wrap = document.getElementById("kiln-wrap"), kiln = document.getElementById("kiln");
    if (!wrap || !kiln || typeof wrap.getBoundingClientRect !== "function" || !kiln.classList) return;
    const head = document.getElementById("top");
    const topH = head && !head.hidden ? head.offsetHeight : 0;
    const compact = wrap.getBoundingClientRect().bottom < topH + 90;
    if (compact === kiln.classList.contains("compact")) return;
    if (compact) wrap.style.minHeight = `${wrap.offsetHeight}px`; // 縮起來前先撐住原本的高度，頁面才不往上跳
    kiln.classList.toggle("compact", compact);
  }
  // 捲動時一幀量一次（只在煉製頁）
  let kilnFrame = 0;
  window.addEventListener("scroll", () => {
    if (kilnFrame || S.stage !== "game" || S.tab !== "craft") return;
    kilnFrame = requestAnimationFrame(() => { kilnFrame = 0; fixedKiln(); });
  }, { passive: true });

  // 開爐成了：結果底下直接畫合出來的那一樣（Joy 2026-10-17「玩家根本無法在一合成出武學時查看武學內容評估武學強弱，還需要切換到另一個分頁」）。
  // 武學寫品質、種類、屬性、境界、第幾成、威力、跟身上同一種比強弱、功效（帶檔次的寫檔次）、特別功效、絕招，底下摺著整張功法卡與「改練上身」；
  // 意境寫重數、圓融駁雜、正邪與說明。資料是 owned_arts 的 judge（skillview.melt_judge，同批量熔煉）與 insights
  // 技能的檔次（武學技能分檔：低階＝一般功效、中階＝特別功效、高階＝content/traits.json 的 high）；沒亮的寫「未開」，修練升品才亮
  const TRAIT_TIERS = { 1: "低", 2: "中", 3: "高", 4: "高" };
  function madeCardHtml(x, item) {
    if (!item) return "";
    if (item.type === "ins") {
      const i = (x.insights || []).find((r) => r.id === item.id);
      if (!i) return "";
      const sub = ["意境", `屬${i.attribute}`, ...String(i.depth || "").split("・"), i.lean && i.lean !== "無" ? i.lean : ""].filter(Boolean);
      return `<div class="made-card"><div class="mc-head"><span class="qseal qi big">意</span><div><b>「${esc(i.name)}」</b><small>${sub.map(esc).join("・")}</small></div></div>
        ${i.note ? `<p class="mc-note">${esc(i.note)}</p>` : ""}</div>`;
    }
    const a = (x.owned_arts || []).find((r) => r.id === item.id);
    if (!a) return "";
    const j = a.judge || {};
    const sub = [a.kind, `屬${a.attribute}`, a.gen, `第${a.level}成`].filter(Boolean);
    const diff = typeof j.worn_diff === "number" ? j.worn_diff : null;
    const verdict = diff === null ? ""
      : diff > 0 ? `<b class="up">比身上那門強 ${meltNum(diff)}</b>` : diff < 0 ? `<b class="down">比身上那門弱 ${meltNum(diff)}</b>` : "跟身上那門一樣";
    const tags = [];
    (j.traits || []).forEach((t) => tags.push(`<i class="tr${t.tier ? ` t${t.tier}` : ""}">${t.tier && TRAIT_TIERS[t.tier] ? `<em>${TRAIT_TIERS[t.tier]}</em>` : ""}${esc(t.name)}${t.layers > 1 ? `<small>${t.layers} 層</small>` : ""}</i>`));
    if (j.special) tags.push(`<i class="tr t2"><em>中</em>${esc(j.special)}</i>`); // 來路帶的特別功效：中階
    (j.dormant || []).forEach((n) => tags.push(`<i class="tr off"><em>未開</em>${esc(n)}</i>`));
    if (j.ultimate) tags.push(`<i class="hi">絕招〔${esc(j.ultimate)}〕</i>`);
    if (j.tactic) tags.push(`<i class="hi">本命戰法〔${esc(j.tactic)}〕</i>`);
    return `<div class="made-card">
      <div class="mc-head">${seal(a.quality, true)}<div><b>【${esc(a.name)}】</b><small>${sub.map(esc).join("・")}</small></div>
        ${typeof j.power === "number" ? `<span class="mc-power">威力<b>${j.power}</b></span>` : ""}</div>
      <p class="mc-verdict">${verdict}<span class="muted">${verdict ? "・" : ""}${a.worn ? "已配上身" : "放在功法庫"}</span></p>
      ${tags.length ? `<div class="mc-tags">${tags.join("")}</div>` : ""}
      <details class="fold"><summary>整張功法卡</summary><div class="fold-body">${tenCells(a.card)}</div></details>
      ${a.worn ? "" : `<button class="btn small" data-act="switch" data-id="${esc(a.id)}">改練上身<small>熟練度各自保留</small></button>`}
    </div>`;
  }
  // 預覽卡（合成即設計定案第三節；Joy 2026-10-19「這個UI不用跟著調整嗎」）：兩格都放好時爐子底下不再是一團字，
  // 而是跟出爐卡同一個形狀的一張卡——品級印、屬性、境界、一上手第幾成、功效籤、亮幾格、舊功效怎麼傳、為什麼是這個屬性、
  // 有沒有人合過、花多少；開不了爐的原因在最底下。資料全是伺服器算的（skillview.forge_preview），網頁一個字不算。
  // 擲骰的爐（fixed 關著）品級印是「？」、寫機率那一句；合併意境寫幾重、圓融駁雜。
  function previewCardHtml(v) {
    if (!v) return "";
    const merge = v.kind === "合併";
    const sub = [v.attribute ? `屬${v.attribute}` : "", merge ? "" : v.gen, v.level > 1 ? `第${v.level}成` : ""].filter(Boolean);
    const badge = merge ? '<span class="qseal qi big">意</span>' : v.quality ? seal(v.quality, true) : '<span class="qseal q1 big">？</span>';
    const verdict = merge ? esc(v.depth || "")
      : v.quality ? `<b>${esc(v.quality)}</b>${v.why && v.why.length ? `<span class="muted">・${v.why.map(esc).join("；")}</span>` : ""}${v.near ? `<span class="near">・${esc(v.near)}</span>` : ""}`
      : `品質看造化：${esc(v.odds || "")}`;
    const tags = (v.traits || []).map((t) => `<i class="tr">${esc(t.name)}${t.layers > 1 ? `<small>${t.layers} 層</small>` : ""}</i>`);
    if (v.slots) tags.push(`<i class="tr off">${esc(v.slots)}</i>`);
    const notes = [merge ? "" : v.depth, v.keep, v.attribute_why, v.known].filter(Boolean);
    return `<div class="made-card preview">
      <div class="mc-head">${badge}<div><b>${esc(v.made)}</b><small>${sub.map(esc).join("・")}</small></div>
        ${v.level > 1 ? `<span class="mc-power">一上手<b>${v.level}<small>成</small></b></span>` : ""}</div>
      <p class="mc-verdict">${verdict}</p>
      ${tags.length ? `<div class="mc-tags">${tags.join("")}</div>` : ""}
      ${notes.length ? `<p class="mc-note">${notes.map((n) => esc(n.replace(/。$/, ""))).join("。")}。</p>` : ""}
      <p class="mc-cost">${esc(v.cost)}</p>
      ${v.problem ? `<p class="kiln-warn">⚠ ${esc(v.problem)}</p>` : ""}
    </div>`;
  }
  // 爐子底下那一格：有預覽卡畫卡，否則畫說明那一行（空爐、只放一樣、不是你的東西）
  function forgeLineHtml(x) {
    return S.forgePreview ? previewCardHtml(S.forgePreview) : `<div class="card">${S.forgeLine || x.forge_line}</div>`;
  }
  // 序章裡點名的那一格（pick:art、pick:insight）：抽屜關著時亮在爐子的空格上（點了開抽屜，裡面那一顆再亮）
  function potGlow() {
    return S.craftPick ? "" : ' data-glow="pick:art pick:insight"';
  }
  // 挑東西放進爐的抽屜（Joy 2026-10-19 決策卡選「點格子開抽屜」：爐子、預覽卡、開爐永遠在第一屏，清單再長也不用捲頁）：
  // 點爐子的空格從底下升起，篩選、武學、意境都在裡面；點一樣就放進去，兩格放滿自動收起、預覽當場更新；放了一樣還缺一樣就留著接著挑。
  // 清單本身（craftChip、篩選、再列、合不了的灰掉）跟以前在頁面上的一模一樣
  function craftSheetHtml(x) {
    const inPot = (id) => S.forgeSel.some((p) => p.type === "art" && p.id === id);
    const v = craftView();
    const keep = (type, thing) => (!v.attr || thing.attribute === v.attr) && (!v.okOnly || !pickMark(type, thing.id));
    const order = (list) => v.sort === "name" ? [...list].sort((a, b) => a.name.localeCompare(b.name, "zh-Hant"))
      : v.sort === "attr" ? [...list].sort((a, b) => a.attribute.localeCompare(b.attribute, "zh-Hant")) : list; // 照品質＝伺服器的順序
    const arts = order(x.owned_arts.filter((a) => showArts("craft", a) && keep("art", a) && (!v.quality || a.quality === v.quality)));
    const ins = order(x.insights.filter((i) => keep("ins", i)));
    const artsShown = v.all || pro() ? arts : arts.slice(0, CRAFT_PAGE);
    const first = S.forgeSel[0];
    const held = first ? (first.type === "art" ? x.owned_arts.find((r) => r.id === first.id) : x.insights.find((r) => r.id === first.id)) : null;
    const title = !first ? "放一樣進爐" : held ? `爐裡${isLocked(first) ? "鎖著" : "有"}${first.type === "art" ? `【${esc(held.name)}】` : `「${esc(held.name)}」`}，再放一樣` : "再放一樣";
    return `<div class="sheet-bg" data-act="pot-close"></div>
      <div class="sheet craft-sheet" role="dialog" aria-label="挑東西放進爐">
        <div class="grip"></div>
        <div class="top-row"><h3 style="flex:1">${title}</h3><button type="button" class="btn small ghost" data-act="pot-close">關閉</button></div>
        <div class="label">功法${filterChips("craft")}</div>
        ${craftFilterRow(x)}
        ${artFilter("craft") === "意境" ? "" : `${arts.length ? `<div class="chips">${artsShown.map((a) => craftChip("art", a, `${a.quality}・屬${a.attribute}・第${a.level}成${a.gen ? `・${a.gen}` : ""}`, QUALITY_RANK[a.quality] || 1,
          (a.glow || []).includes("pick:art") ? ' data-glow="pick:art"' : "", inPot(a.id))).join("")}</div>` : '<p class="muted">沒有合這些條件的武學。</p>'}
        ${artsShown.length < arts.length ? `<button class="btn ghost lib-more" data-act="craft-all">再列 ${arts.length - artsShown.length} 門</button>` : ""}`}
        <div class="label">意境 <small class="muted">同一個也能放兩次</small></div>
        ${x.insights.length ? (ins.length ? `<div class="chips">${ins.map((i) => craftChip("ins", i, `屬${i.attribute}${i.lean !== "無" ? `・${i.lean}` : ""}${i.depth ? `・${i.depth}` : ""}`, 2,
          (i.glow || []).includes("pick:insight") && !S.forgeSel.some((p) => p.type === "ins" && p.id === i.id) ? ' data-glow="pick:insight"' : "")).join("")}</div>`
          : '<p class="muted">沒有合這些條件的意境。</p>')
          : '<p class="muted">還沒悟到任何意境。去探索，荒郊野外最容易有所領悟。</p>'}
      </div>`;
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
    const ready = forgeReady();
    // 合出來的那一樣的卡排在結果那段話前面：一開爐第一眼就看到它強不強（Joy 2026-10-17）
    const result = S.forgeResult ? `${madeCardHtml(x, S.forgeMade)}<div class="msg forge-result">${S.forgeResult.html}</div>` : "";
    // 爐子、預覽卡（或說明那一行）、結果都在第一屏；挑東西在抽屜裡（craftSheetHtml），頁面本身不長。
    // 爐裡還沒放滿時預覽那一行底下一顆「挑東西放進爐」（點爐子的空格也行）
    return `
      ${proGuide()}
      <div class="msg" id="mx-msg">${S.message}</div>
      ${kilnHtml([slotOf(S.forgeSel[0]), slotOf(S.forgeSel[1])], ready)}
      <div id="forge-line">${forgeLineHtml(x)}</div>
      ${ready ? "" : `<button type="button" class="btn pot-open" data-act="pot-open">${S.forgeSel.length ? "再放一樣進爐" : "挑東西放進爐"}<small>武學與意境的清單</small></button>`}
      ${result}
      ${attrNoteHtml(x)}
      ${x.clue_items?.length ? `<div class="label">伏筆物品</div>
      <div class="chips clues">${x.clue_items.map((i) => `<div class="clue"><b>${esc(i.name)}</b><span>×${i.count}</span></div>`).join("")}</div>` : ""}
      ${manualEntry("arts")}${manualEntry("forge")}
      <details class="fold"><summary>背包</summary><div class="fold-body">${x.bag}</div></details>
      ${S.craftPick ? craftSheetHtml(x) : ""}`;
  }

  // 武學譜（status.manual，secret_recipes.view；企劃者 2026-10-10「武學譜能不能獨立一頁，做得更豪華一些」）：
  // 煉製頁上只放入口（manualEntry），點了開全螢幕的一本書（bookHtml，S.book，疊在整個畫面上、左上返回）。
  // 鑄譜（status.forge_manual，打造隱藏配方設計 6.3）用同一本書，入口擺在武學譜旁邊（S.book 記開哪一本：false／"arts"／"forge"，true 當武學譜），打中過的另外寫配方（`recipe`）。
  // 一條秘方一頁，聽過的口訣直書大字，合中了蓋一方朱印寫它的名號。只列聽過的那幾句：不寫種類、配方、還差幾句（還沒拿到的線索一律不露）
  // 兩本書：武學譜（口訣與秘方）、鑄譜（打造的隱藏配方）。字待 joy 潤。一行寫完：tests/test_arts_pages.py、test_arts_pages_two.py 的假瀏覽器照名字把這一行切出去（webharness.konst 只認一行的 const）
  const BOOKS = { arts: { title: "武學譜", verb: "合出", unit: "口訣", empty: "江湖上流傳的老話，有時藏著合成的門道。" }, forge: { title: "鑄譜", verb: "打出", unit: "鑄訣", empty: "鐵匠的閒話、說書人的掌故，有時藏著失傳的鑄法。" } };
  function manualRows(which = "arts") {
    const st = S.main && S.main.status;
    return (st && (which === "forge" ? st.forge_manual : st.manual)) || [];
  }
  const CN_NUM = "〇一二三四五六七八九十";
  const cnNum = (n) => n <= 10 ? CN_NUM[n] : n < 20 ? `十${CN_NUM[n - 10]}` : `${CN_NUM[Math.floor(n / 10)]}十${n % 10 ? CN_NUM[n % 10] : ""}`;
  // 一卷線裝書（入口與封面共用）：書衣、題簽、四道線
  function bookIcon() {
    return `<svg class="book-icon" viewBox="0 0 48 56" aria-hidden="true"><rect x="4" y="3" width="40" height="50" rx="2" class="bk-cover"/>
    <rect x="22" y="9" width="12" height="32" class="bk-slip"/><path d="M28 13v24" class="bk-slip-ink"/>
    <path d="M10 3v50M4 12h6M4 24h6M4 36h6M4 48h6" class="bk-thread"/></svg>`;
  }
  function manualEntry(which) {
    const rows = manualRows(which), b = BOOKS[which];
    const solved = rows.filter((r) => r.solved).length;
    const sub = rows.length ? `收錄${b.unit} ${rows.length} 則${solved ? `・已參透 ${solved}` : ""}` : "卷中尚無一字";
    return `<button class="manual-entry" data-act="book-open" data-book="${which}">${bookIcon()}<span><b>${b.title}</b><small>${sub}</small></span><i class="go">翻閱 ›</i></button>`;
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
  // ── 店面（店面獨立介面設計第一、二節；第一批：鐵匠鋪）──
  // 伺服器在店開著、開關開著時給 main.shop（shopview.smith_view）：蓋住整個畫面（同武學譜那本書的蓋法），左上「出店」送現在的離開，
  // 兵器／防具切換、買、修、淬煉送現在的選項 id（choose），換上、拆解走修練頁的動作（shopMx），開爐是 /api/do/smith_forge。字待 joy 潤
  const SHOP_TABS = [["shelf", "架上"], ["forge", "打造"], ["temper", "淬煉與修"], ["rack", "裝備庫"]];
  const SHOP_ATTR = { 剛: "gang", 快: "kuai", 柔: "rou", 慢: "man" };
  const SHOP_RACK_LIST = 8;

  // 共用的店面框（1.2）：招牌、銀兩、掌櫃那一句、左上「出店」；底下照哪一間店畫。懸賞榜的第三層（替一張求藝、求兵挑東西）
  // 選單上沒有 bounty:back：出店先送回到懸賞榜（boardLeave）。三間店捲的那一層（.shop-body）裡面一律再包一層 .shop-col：
  // 電腦上整片寬的 .shop-body 照舊捲，內容照遊戲那一欄排（style.css 的 FB-225 那一段；手機上 .shop-col 沒有樣式）
  function shopHtml(shop) {
    const kind = shop.shop || "smith";
    const back = shop.picked
      ? '<button class="shop-back" data-act="shop-leave">‹ 出店</button>'
      : `<button class="shop-back" data-act="choose" data-id="${esc(shop.back)}">‹ 出店</button>`;
    // 鐵匠講神器的規矩（背包有四階時，shop.rule；設計 9.1 第 2 批甲）：就畫在平常那一句的位置、金框標出來；順口講配方線索那一下伺服器給空的
    const line = shop.rule ? `<p class="shop-line rule">${esc(shop.rule)}</p>`
      : `<p class="shop-line">${kind === "dadian" ? sayHtml(shop.line) : esc(shop.line)}</p>`; // 打點：掮客那一句不在詞中間斷（FB-433）
    // 鐵匠鋪的架上頁照草圖 A 把鐵匠那一句放在爐火底下（smithHtml 畫，企劃者 2026-10-14）；其他頁、馬市、懸賞榜緊接招牌
    const underForge = kind === "smith" && smithTab(shop) === "shelf";
    const body = kind === "market" ? marketHtml(shop) : kind === "board" ? boardHtml(shop) : kind === "arena" ? arenaHtml(shop)
      : kind === "donate" ? donateHtml(shop) : kind === "dadian" ? dadianHtml(shop) : kind === "tavern" ? tavernHtml(shop) : smithHtml(shop, underForge ? line : "");
    // 擂台打到一半：左上那一顆是認輸（先問一次），不是直接離開
    const leave = kind === "arena" && shop.fight
      ? `<button class="shop-back" data-act="shop-ask" data-id="${esc(shop.fight.yield.id)}" data-confirm="${esc(shop.fight.yield.confirm)}" data-yes="認輸">‹ 認輸</button>`
      : kind === "arena" ? back.replace("‹ 出店", "‹ 離開") : back;
    return `<div class="shop-layer shop-${esc(kind)}" role="dialog" aria-label="${esc(shop.sign)}">
      <header class="shop-bar">${leave}<span class="shop-sign">${esc(shop.sign)}</span><span class="shop-silver">${shop.purse ? esc(shop.purse) : `銀 ${shop.silver | 0}`}</span></header>
      ${underForge ? "" : line}
      ${body}
    </div>`;
  }

  // ── 擂台（擂台賽設計；Joy 2026-10-14「擂台應該要是獨立的一頁，你這樣太混雜了」）：跟三間店同一層。打到一半整頁是這一場（arenaFightHtml），
  // 不然底下兩頁：台下（你的分身與積分、守擂的人一人一張）、擂台榜；剛打完有收場卡。鈕都送現在的選項 id。字待 joy 潤 ──
  const ARENA_TABS = [["floor", "台下"], ["board", "擂台榜"]];
  function arenaHtml(shop) {
    // 捲的那一層裡面同三間店先包一層 .shop-col（FB-306：電腦上照遊戲那一欄排，台下那一格原本拉滿整個螢幕；手機上 .shop-col 沒有樣式）
    if (shop.fight) return `<div class="shop-body arena-body"><div class="shop-col">${arenaFightHtml(shop.fight)}</div></div>`;
    const tab = S.arenaTab === "board" ? "board" : "floor";
    const result = shop.result && shop.result.id !== S.arenaSeen ? arenaResultHtml(shop.result) : "";
    return `<div class="shop-body arena-body"><div class="shop-col">${tab === "board" ? arenaBoardHtml(shop) : arenaFloorHtml(shop)}</div></div>
      <nav class="shop-tabs">${ARENA_TABS.map(([k, name]) => `<button class="shop-tab${tab === k ? " on" : ""}" data-act="arena-tab" data-tab="${k}">${name}</button>`).join("")}</nav>
      ${result}`;
  }

  // 台下：上面是你自己那一張（名次、稱號、戰績、守擂用的武學、報名／更新分身），底下挑得到的人（排在你前面三名內）一人一張，挑不了的灰掉寫原因
  function arenaFloorHtml(shop) {
    const me = shop.me;
    const stand = me.joined
      ? `<div class="ring-score"><span>第</span><b>${me.rank | 0}</b><span>名</span></div>
         <div class="ring-meta">${me.title ? `<span class="ring-place">${esc(me.title)}</span>` : ""}<span>${esc(me.record)}</span>
           ${me.arts.length ? `<span>守擂：${esc(me.arts.join("、"))}</span>` : ""}</div>`
      : `<p class="ring-new">${esc(me.note)}</p>`;
    const join = `<button class="btn${me.joined ? "" : " primary"} ring-join" data-act="choose" data-id="${esc(me.join.id)}" ${me.join.enabled ? "" : "disabled"}><b>${esc(me.join.label)}</b>${me.join.why ? `<small>${esc(me.join.why)}</small>` : ""}</button>`;
    const mine = `<section class="ring-me">${stand}${join}${me.joined ? `<p class="ring-note">${esc(me.note)}</p>` : ""}</section>`;
    const card = (f) => `<article class="ring-foe${f.enabled ? "" : " dim"}">
        <div class="info"><div class="who"><span class="rt">第 ${f.rank | 0} 名</span><b>${esc(f.name)}</b>${f.title ? `<span class="ttl">${esc(f.title)}</span>` : ""}</div>
        <p>${esc(f.record)}・${esc(f.strength)}</p>${f.arts.length ? `<p class="arts">${esc(f.arts.join("、"))}</p>` : ""}${f.famed ? `<p class="arts famed">${esc(f.famed)}</p>` : ""}</div>
        <button class="btn${f.enabled ? " primary" : ""} small" data-act="choose" data-id="${esc(f.id)}" ${f.enabled ? "" : `disabled title="${esc(f.why || "")}"`}>${f.enabled ? "<b>挑戰</b>" : f.short ? `<b>${esc(f.short[0])}</b>${f.short[1] ? `<small>${esc(f.short[1])}</small>` : ""}` : esc(f.why)}</button>
      </article>`;
    if (!me.joined) return mine;
    const foes = shop.foes.length ? `<div class="ring-foes">${shop.foes.map(card).join("")}</div>` : `<p class="shop-empty">${esc(shop.nobody)}</p>`;
    return `${mine}<h4 class="ring-h">挑得到的人</h4>${foes}`;
  }

  // 擂台榜：照名次排，前三名有名次色、稱號一個小牌子，你自己那一列標出來；底下一行每天的俸
  function arenaBoardHtml(shop) {
    if (!shop.board.length) return `<p class="shop-empty">${esc(shop.board_empty)}</p>`;
    const row = (r) => `<li class="${r.me ? "me" : ""}${r.rank <= 3 ? ` top${r.rank | 0}` : ""}"><span class="rk">${r.rank | 0}</span>
        <div class="nm"><b>${esc(r.name)}</b><span class="wl">${r.wins | 0} 勝 ${r.losses | 0} 負${r.draws ? ` ${r.draws | 0} 和` : ""}${r.streak >= 2 ? `・連勝 ${r.streak | 0}` : ""}</span></div>
        ${r.title ? `<span class="ttl">${esc(r.title)}</span>` : ""}</li>`;
    return `<ol class="ring-board">${shop.board.map(row).join("")}</ol>${shop.wages ? `<p class="ring-note">${esc(shop.wages)}</p>` : ""}`;
  }

  // 打到一半：兩邊的氣血、中間一條氣勢（越往右越是你佔上風）、他的架勢、三招、放手一搏、這一場打過的回合
  // 擂台的場邊事件（tianxia/arena_crowd.py）：那一行以〔場邊〕開頭，另一種底色；剛發生的那一回合在雙方氣血底下多放一行
  const CROWD_MARK = "〔場邊〕";
  function ringLine(l) { return `<li${l.startsWith(CROWD_MARK) ? ' class="crowd"' : ""}>${esc(l)}</li>`; }

  function arenaFightHtml(f) {
    const pct = (a) => Math.max(0, Math.min(100, a.cap ? (a.hp / a.cap) * 100 : 0));
    const side = (a, cls) => `<div class="ring-side ${cls}"><b>${esc(a.name)}</b><div class="hp"><i style="width:${pct(a).toFixed(1)}%"></i></div><small>${a.hp | 0}／${a.cap | 0}</small></div>`;
    const moves = f.moves.map((m) => `<button class="btn ring-move"${m.enabled === false ? " disabled" : ` data-act="choose" data-id="${esc(m.id)}"`}><b>${esc(m.move)}</b><small>${esc(m.label.replace(m.move, ""))}</small></button>`).join("");
    const log = f.log.length ? `<ol class="ring-log">${f.log.slice().reverse().map(ringLine).join("")}</ol>` : "";
    const last = f.log.length ? f.log[f.log.length - 1] : "";
    const crowd = last.startsWith(CROWD_MARK) ? `<p class="ring-crowd">${esc(last)}</p>` : "";
    return `<div class="ring-round">第 ${f.round | 0}／${f.rounds | 0} 回合</div>
      <div class="ring-sides">${side(f.me, "mine")}<span class="vs">對</span>${side(f.foe_hp, "theirs")}</div>
      ${crowd}
      <div class="ring-edge"><span>${esc(f.edge_words)}</span><div class="bar"><i style="left:${Math.max(0, Math.min(100, f.edge | 0))}%"></i></div></div>
      ${f.arts.length ? `<p class="ring-arts">他守擂用的是${esc(f.arts.join("、"))}。</p>` : ""}
      ${f.status ? `<p class="ring-status">${esc(f.status)}</p>` : ""}
      <p class="ring-tell">${esc(f.tell)}<small>（${esc(f.tell_note)}）</small></p>
      <p class="ring-howto">${esc(f.howto)}</p>
      <div class="ring-moves">${moves}</div>
      ${f.gamble.locked ? `<p class="free-note">${esc(f.gamble.locked)}</p>` : `<form class="free ring-free" id="arena-free" data-op="${esc(f.gamble.op)}"><input class="input" name="text" maxlength="20" placeholder="${esc(f.gamble.prompt)}"><button class="btn primary small" type="submit">送出</button></form>
      <p class="free-note">${esc(f.gamble.note)}</p>`}
      ${log}`;
  }

  // 剛打完的那一場：一張卡蓋在台下上面（勝負大字、每回合一行、積分與名望），按「回台下」收起
  function arenaResultHtml(r) {
    const won = r.tier === "大勝" || r.tier === "險勝";
    const cls = won ? "win" : r.tier === "僵持" ? "draw" : "lose";
    return `<div class="board-sheet ring-sheet"><article class="paper ring-result ${cls}"><i class="stamp">${esc(r.tier)}</i>
        <h4>對${esc(r.foe)}的分身</h4><ol class="ring-log">${r.lines.map(ringLine).join("")}</ol>
        ${r.changes.length ? `<p class="reward">${esc(r.changes.join("・"))}</p>` : ""}
        <div class="btns one"><button class="btn primary" data-act="arena-seen" data-id="${r.id | 0}">回台下</button></div></article></div>`;
  }

  // 鐵匠鋪現在停在哪一頁（S.shopTab 不認得的當架上，同 smithHtml）。素材頁只在伺服器給了 shop.trade（收購或升階開著）時有
  function smithTab(shop) {
    if (S.shopTab === "trade") return shop && shop.trade ? "trade" : "shelf";
    return ["forge", "temper", "rack"].includes(S.shopTab) ? S.shopTab : "shelf";
  }
  // 鐵匠鋪的分頁：四頁，素材買賣開著時多第五頁「素材」（素材與經濟 B6，企劃者 2026-10-15 選草圖 A1）
  function smithTabs(shop) { return shop.trade ? [...SHOP_TABS, ["trade", "素材"]] : SHOP_TABS; }

  // 鐵匠鋪（第一批）：兵器防具切換、四頁、分頁列、出爐卡。架上頁最上面是爐火與鐵匠那一句（line，shopHtml 交過來），不跟著貨卡捲。
  // 素材頁不分兵器、防具：那一頁不畫上面的切換
  function smithHtml(shop, line = "") {
    const tab = smithTab(shop);
    const pages = shop.pages.length > 1 && tab !== "trade" ? `<div class="shop-pages">${shop.pages.map((p) => `<button class="shop-page${p.slot === shop.page ? " on" : ""}"${p.slot === shop.page ? " disabled" : ` data-act="choose" data-id="${esc(p.id)}"`}>${esc(p.label)}</button>`).join("")}</div>` : "";
    const body = { shelf: shelfHtml, forge: forgePageHtml, temper: temperHtml, rack: rackHtml, trade: tradeHtml }[tab];
    return `${tab === "shelf" ? SMITH_HERO + line : ""}${pages}
      <div class="shop-body"><div class="shop-col">${body(shop)}</div></div>
      <nav class="shop-tabs">${smithTabs(shop).map(([k, name]) => `<button class="shop-tab${tab === k ? " on" : ""}" data-act="shop-tab" data-tab="${k}">${name}</button>`).join("")}</nav>
      ${S.shopReveal ? revealHtml(S.shopReveal, shop) : ""}`;
  }

  // 上一下的結果那一句（素材頁、軍需帳）：升階出了什麼、賣了多少、捐了多少，或為什麼不成；換頁、出店清掉。
  // 那一格一直在、高度固定兩行（還沒做事時寫伺服器給的 hint）：結果冒出來不把底下的格子往下推，連點同一格升兩次不會點偏
  function shopNoteHtml(hint = "") {
    return S.shopNote ? `<p class="shop-done" role="status">${esc(S.shopNote)}</p>` : `<p class="shop-done hint" role="status">${esc(hint)}</p>`;
  }

  // 素材頁（素材與經濟設計第四、五節；企劃者 2026-10-15：上半升階、下半收購）。升階一屬性一列、二階三階各一格（拿什麼換、偏向出哪一種、
  // 幾成、工錢、今天還能換幾個；按不下去的灰掉、格子上寫短的原因，點了說整句）；收購一種一列（賣一個、全賣先問一次）。
  // 升階出來的屬性隨機（企劃者 2026-10-15「屬性隨機、偏向投入的」），格子上照伺服器寫「五成・其餘隨機」。字待 joy 潤
  function tradeHtml(shop) {
    const t = shop.trade;
    let ups = "";
    if (t.upgrade.length) {
      const rows = [];
      for (const r of t.upgrade) {
        const last = rows[rows.length - 1];
        if (last && last.attribute === r.attribute) last.cells.push(r);
        else rows.push({ attribute: r.attribute, cells: [r] });
      }
      const cell = (r) => `<button class="up-cell${r.problem ? " off" : ""}" data-act="trade-up" data-attr="${esc(r.attribute)}" data-tier="${r.tier | 0}" data-why="${esc(r.problem || "")}" title="${esc(r.odds)}">
          <span class="from">${esc(r.from)}×${r.need | 0} →</span><b>${esc(r.name)}</b>${r.lean ? `<small class="lean">${esc(r.lean)}・其餘隨機</small>` : ""}
          <small>${r.problem ? esc(r.short) : `<span class="nb">${r.cost | 0} 兩</span>${dealHtml(r.cost_note || "")}${r.left_text ? `・<span class="nb">${esc(r.left_text)}</span>` : ""}`}</small></button>`; // 上限字照伺服器給（FB-342：三換四是這一季的） // 價錢後面寫原因（名聲 4.1，FB-296）
      // 價錢與「這一季還能 N 個」各是不折行的小段（FB-410：375 寬一格約 103px，斷成「這一季還／能 2 個」），要斷只斷在「・」後面
      ups = `<p class="shop-cap">${esc(t.up_cap)}</p><div class="up-rows${shop.four ? " four" : ""}">${rows.map((row) => `<div class="up-row"><span class="row-attr ${SHOP_ATTR[row.attribute] || ""}">${esc(row.attribute)}</span>${row.cells.map(cell).join("")}</div>`).join("")}</div>`;
    }
    let sells = "";
    if (t.sell_cap) {
      const row = (r) => `<div class="sell-row"><span class="nm"><b><i class="dot ${SHOP_ATTR[r.attribute] || ""}"></i>${esc(r.name)}</b><small>${esc(r.tier_word)}・手上 ${r.have | 0}・一個 ${r.price | 0} 兩${r.dark ? esc(r.dark) : ""}</small></span>
          <span class="acts"><button class="btn small" data-act="trade-sell" data-id="${esc(r.id)}" data-n="1">賣 1 個</button>${r.have > 1
            ? `<button class="btn small ghost" data-act="trade-sell" data-id="${esc(r.id)}" data-n="${r.have | 0}" data-confirm="${esc(`把 ${r.have | 0} 個${r.name}都賣了，換 ${(r.have * r.price) | 0} 兩？`)}">全賣 ${(r.have * r.price) | 0} 兩</button>` : ""}</span></div>`;
      sells = `<p class="shop-cap">${esc(t.sell_cap)}</p>${t.sell.length ? `<div class="sell-rows">${t.sell.map(row).join("")}</div>` : `<p class="shop-empty">${esc(t.sell_empty)}</p>`}`;
    }
    return `${shopNoteHtml(t.hint)}${ups}${sells}`;
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

  // ── 軍需帳（素材與經濟設計第六節；企劃者 2026-10-15 選草圖 B3）：上面陣營四種軍備的存量、今天還能捐幾點，底下背包的素材一格一格
  // （同打造頁的素材格，照屬性一排、一階到三階）。點一格挑起來（預設今天收得下的全部）、挑好的列在底下可以＋−改個數，「捐出」一起送
  // （MAIN_ACTIONS donate 的 items，一則紀錄）。捐不了的格子灰掉寫原因。字待 joy 潤 ──
  function donatePicks(shop) {
    // 挑好的照現在的格子修：捐不了的、已經不在背包的拿掉，個數夾在今天收得下的以內
    const cells = new Map(shop.cells.map((c) => [c.id, c]));
    const out = {};
    for (const [id, n] of Object.entries(S.donatePick || {})) {
      const cell = cells.get(id);
      if (cell && !cell.problem && cell.take > 0) out[id] = Math.max(1, Math.min(n | 0, cell.take));
    }
    return out;
  }
  // ── 打點（21 天季的銀兩出口；企劃者挑第 9 批畫面乙：茶樓雅間的掮客，五樣記在一本攤開的帳簿上；shopview.dadian_view）──
  // 左頁「修為」、右頁「人情」。這裡做得了的一筆是一顆鈕，送原本的選項 id（choose）；做不了的墨線劃掉、朱筆批去哪做（或為什麼）。
  // 身上掛著還沒用掉的寫在帳底下。字與數字照伺服器給的
  function dadianHtml(shop) {
    const entry = (e) => {
      const head = `<b>${esc(e.name)}<em>${esc(e.price)}</em></b><span class="desc">${ledgerText(e.desc)}</span>`;
      return e.ok
        ? `<button class="entry" data-act="choose" data-id="${esc(e.id)}">${head}<span class="tick">${ledgerText(e.tick)}</span></button>`
        : `<div class="entry off">${head}<span class="note">${ledgerText(e.note)}</span></div>`;
    };
    const pages = shop.pages.map((p) => `<section class="ledger-page"><h3>${esc(p.head)}</h3>${p.entries.map(entry).join("")}</section>`).join("");
    return `<div class="shop-body"><div class="shop-col"><div class="ledger">${pages}</div>
      <div class="abacus" aria-hidden="true">${"<i></i>".repeat(9)}</div>
      ${shop.hang ? `<p class="ledger-hang">${esc(shop.hang)}</p>` : ""}</div></div>`;
  }

  function donateHtml(shop) {
    const picks = donatePicks(shop);
    const cells = new Map(shop.cells.map((c) => [c.id, c]));
    const used = Object.entries(picks).reduce((sum, [id, n]) => sum + n * cells.get(id).points, 0);
    const tiles = shop.stock.map((a) => `<div class="arm-tile"><span>${esc(a.name)}</span><b>${a.points | 0}</b></div>`).join("");
    const fill = shop.cap ? Math.max(0, Math.min(100, (shop.room / shop.cap) * 100)) : 0;
    const rows = [];
    for (const c of shop.cells) {
      const cell = `<button class="cell t${c.tier | 0}${picks[c.id] ? " used" : ""}${c.problem ? " off" : ""}" data-act="dn-cell" data-id="${esc(c.id)}" data-why="${esc(c.problem || "")}">
        <span class="n">${c.have | 0}</span><span class="nm"><i class="dot ${SHOP_ATTR[c.attribute] || ""}"></i>${esc(c.name)}</span><small>${esc(c.tier_word)}・${c.points | 0} 點</small>${picks[c.id] ? `<span class="pick">捐 ${picks[c.id]}</span>` : ""}</button>`;
      const last = rows[rows.length - 1];
      if (last && last.attribute === c.attribute) last.cells.push(cell);
      else rows.push({ attribute: c.attribute, cells: [cell] });
    }
    const grid = rows.map((r) => `<div class="cell-row"><span class="row-attr ${SHOP_ATTR[r.attribute] || ""}">${esc(r.attribute)}</span>${r.cells.join("")}</div>`).join("");
    const picked = Object.entries(picks).map(([id, n]) => {
      const c = cells.get(id);
      return `<div class="dn-pick"><span>${esc(c.name)} ×${n}<small>${n * c.points} 點・${esc(c.armament)}</small></span>
        <span class="dn-step"><button class="btn small ghost" data-act="dn-step" data-id="${esc(id)}" data-d="-1" ${n > 1 ? "" : "disabled"} aria-label="少捐一個">−</button><button class="btn small ghost" data-act="dn-step" data-id="${esc(id)}" data-d="1" ${n < c.take && used + c.points <= shop.room ? "" : "disabled"} aria-label="多捐一個">＋</button></span></div>`;
    }).join("");
    const over = used > shop.room;
    const go = `<button class="btn primary shop-go" data-act="dn-go" ${used > 0 && !over ? "" : "disabled"}>${used > 0 ? `捐出 ${used} 點` : "點素材挑要捐的"}</button>`;
    const tierOne = shop.cells.some((c) => c.tier === 1 && !c.problem) ? '<button class="btn small ghost" data-act="dn-tier1">全選一階</button>' : "";
    // 格子上面的東西挑了之後高度不變（捐出鈕只換字）：挑好的與＋−排在格子底下，點一格不會把下一格擠走、手指點偏
    return `<div class="shop-body"><div class="shop-col">${shopNoteHtml(shop.hint)}
      <div class="arm-tiles">${tiles}</div>
      <div class="dn-room"><span>${esc(shop.room_text)}</span><i><b style="width:${fill.toFixed(1)}%"></b></i></div>
      <div class="shop-gorow">${go}${tierOne}</div>
      ${over ? `<p class="shop-warn">${esc(`今天只收得下 ${shop.room | 0} 點，少挑一些。`)}</p>` : ""}
      <p class="shop-cap">${esc(shop.caption)}</p>
      <div class="cells">${grid || `<p class="shop-empty">${esc(shop.empty)}</p>`}</div>
      ${picked ? `<p class="shop-cap">挑好要捐的（＋−改個數）</p><div class="dn-picks">${picked}</div>` : ""}</div></div>`;
  }
  // 點一格：灰掉的只說原因；挑過的放回去；沒挑過的挑起來，個數是今天收得下的（扣掉已經挑的點數）
  function donateCell(id, why) {
    if (why) { toast(why); return; }
    const shop = S.main && S.main.shop;
    if (!shop || shop.shop !== "donate") return;
    const picks = donatePicks(shop);
    if (picks[id]) { delete picks[id]; S.donatePick = picks; renderShop(); return; }
    const cell = shop.cells.find((c) => c.id === id);
    if (!cell) return;
    const used = Object.entries(picks).reduce((sum, [k, n]) => sum + n * shop.cells.find((c) => c.id === k).points, 0);
    const fit = Math.min(cell.take, Math.floor((shop.room - used) / cell.points));
    if (fit <= 0) { toast(`今天只剩 ${Math.max(0, shop.room - used)} 點收得下，${cell.name}一個就 ${cell.points} 點。`); return; }
    picks[id] = fit;
    S.donatePick = picks;
    renderShop();
  }
  function donateStep(id, d) {
    const shop = S.main && S.main.shop;
    if (!shop || shop.shop !== "donate") return;
    const picks = donatePicks(shop);
    if (!picks[id]) return;
    picks[id] = picks[id] + d; // 夾在 1～今天收得下的，下一次畫照 donatePicks 修
    S.donatePick = picks;
    renderShop();
  }
  // 全選一階：每一種捐得了的一階都挑起來，照今天剩的點數依序填滿
  function donateTierOne() {
    const shop = S.main && S.main.shop;
    if (!shop || shop.shop !== "donate") return;
    const picks = donatePicks(shop);
    let used = Object.entries(picks).reduce((sum, [k, n]) => sum + n * shop.cells.find((c) => c.id === k).points, 0);
    for (const c of shop.cells) {
      if (c.tier !== 1 || c.problem || picks[c.id]) continue;
      const fit = Math.min(c.take, Math.floor((shop.room - used) / c.points));
      if (fit <= 0) break;
      picks[c.id] = fit;
      used += fit * c.points;
    }
    S.donatePick = picks;
    renderShop();
  }
  async function donateGo() {
    const shop = S.main && S.main.shop;
    if (!shop || shop.shop !== "donate") return;
    const items = Object.entries(donatePicks(shop)).map(([material, count]) => ({ material, count }));
    if (!items.length) return;
    await shopDo("donate", { items }, () => { S.donatePick = {}; });
  }

  // ── 酒肆（企劃者 2026-10-18「可以，做精緻一些，包含氛圍感」；草圖甲「夜燈酒肆」）：跟三間店同一層。四頁：聽消息（燈籠、酒罈、熱湯的場景，
  // 座上客、請酒、鄰桌閒談、聽消息）、打聽（下落、交情、素材）、題壁、暗處（風聲、藏行跡、反查）。打聽到的寫在每一頁「剛問到的」底下；
  // 動作走 MAIN_ACTIONS tavern（shopDo）。燈籠搖、熱氣冒，減少動態效果的人不動。字待 joy 潤 ──
  const TAV_TABS = [["news", "聽消息"], ["ask", "打聽"], ["wall", "題壁"], ["shade", "暗處"]];
  const TAV_LANTERN = (word) => `<svg class="tav-lantern" viewBox="0 0 46 96" aria-hidden="true"><line x1="23" y1="0" x2="23" y2="18" stroke="#2a170d" stroke-width="2"/><rect x="14" y="16" width="18" height="6" rx="1.5" fill="#c99a3a"/><ellipse cx="23" cy="46" rx="20" ry="25" fill="#c8321e"/><ellipse cx="23" cy="46" rx="12" ry="24" fill="#e2502e" opacity=".7"/><ellipse cx="23" cy="46" rx="5" ry="22" fill="#ffb15a" opacity=".55"/><path d="M5 38 Q23 34 41 38 M4 46 Q23 43 42 46 M5 54 Q23 51 41 54" stroke="#8c1f12" stroke-width="1" fill="none" opacity=".6"/>${word ? `<text x="23" y="52" text-anchor="middle" font-size="16" font-weight="700" fill="#2a0e06" opacity=".75">${word}</text>` : ""}<rect x="14" y="70" width="18" height="5" rx="1.5" fill="#c99a3a"/><path d="M19 75 L18 94 M23 75 L23 96 M27 75 L28 94" stroke="#d23a24" stroke-width="1.5"/></svg>`;
  const TAV_HERO = `<div class="tav-hero" aria-hidden="true"><i class="tav-glow l"></i><i class="tav-glow r"></i>
    <span class="tav-hang l">${TAV_LANTERN("")}</span><span class="tav-hang r">${TAV_LANTERN("酒")}</span>
    <svg class="tav-bowl" viewBox="0 0 70 40"><g class="tav-steam" stroke="#f6dcb0" stroke-width="1.6" fill="none" stroke-linecap="round"><path d="M24 18 q-4 -6 0 -10 q4 -4 0 -8"/><path d="M34 18 q-4 -6 0 -10 q4 -4 0 -8"/><path d="M44 18 q-4 -6 0 -10 q4 -4 0 -8"/></g><path d="M12 22 L58 22 Q56 36 35 37 Q14 36 12 22 Z" fill="#3a2414"/><path d="M12 22 L58 22" stroke="#c99a3a" stroke-width="1.5"/></svg>
    <svg class="tav-jars" viewBox="0 0 150 66"><g fill="#0e0805"><path d="M8 64 Q2 40 14 26 L14 18 L30 18 L30 26 Q42 40 36 64 Z"/><path d="M46 64 Q40 44 50 32 L50 26 L62 26 L62 32 Q72 44 66 64 Z"/><path d="M78 64 Q70 36 86 20 L86 10 L104 10 L104 20 Q120 36 112 64 Z"/><path d="M120 64 Q116 48 124 40 L124 34 L134 34 L134 40 Q142 48 138 64 Z"/></g><rect x="88" y="34" width="14" height="18" fill="#7a2014" opacity=".85"/><text x="95" y="47" text-anchor="middle" font-size="11" fill="#e8c27a">酒</text></svg>
    <i class="tav-table"></i></div>`;

  function tavTab() { return TAV_TABS.some(([k]) => k === S.tavTab) ? S.tavTab : "news"; }

  // 打聽到的一則（聽消息、下落、交情、素材、反查）：小標、時刻，一行一句
  function tavNoteHtml(n) {
    return `<article class="tav-note k-${esc(n.kind)}"><div class="tag"><b>${esc(n.title)}</b><span>${esc(n.when)}</span></div>${n.lines.map((l) => `<p>${esc(l)}</p>`).join("")}</article>`;
  }
  function tavNotes(shop, kinds, empty) {
    const rows = shop.notes.filter((n) => kinds.includes(n.kind));
    return rows.length ? rows.map(tavNoteHtml).join("") : (empty ? `<p class="shop-empty">${esc(empty)}</p>` : "");
  }
  function tavDone() { return S.shopNote ? shopNoteHtml("") : ""; } // 這一下的結果（只有有結果時才畫）
  function tavBtn(op, label, price, why) {
    return `<button class="tav-act" data-act="tav-do" data-op="${op}"${why ? ` disabled title="${esc(why)}"` : ""}><b>${esc(label)}</b><small>${why ? esc(why) : `${price | 0} 兩`}</small></button>`;
  }

  function tavNewsHtml(shop) {
    const guests = shop.guests.length
      ? `<div class="tav-guests"><span class="gl">座上客</span>${shop.guests.map((g) => `<span class="tav-chip">${esc(g)}</span>`).join("")}${shop.more_guests ? `<span class="more">還有 ${shop.more_guests | 0} 人</span>` : ""}</div>`
      : `<div class="tav-guests"><span class="gl">座上客</span><span class="more">今晚冷清，只有你一桌</span></div>`;
    const treat = shop.treat ? `<p class="tav-treat">${esc(shop.treat)}</p>` : "";
    const talk = shop.chatter.length
      ? `<h4 class="tav-h">鄰桌閒談<small>壓低了聲音</small></h4><ul class="tav-talk">${shop.chatter.map((c) => `<li>${c.who ? `<span class="who">${esc(c.who)}</span>` : ""}${esc(c.said)}</li>`).join("")}</ul>` : "";
    const board = shop.board ? `<button class="btn ghost small tav-board" data-act="choose" data-id="${esc(shop.board)}">看牆上的懸賞榜 ›</button>` : "";
    return `${guests}${treat}
      <button class="tav-listen" data-act="tav-do" data-op="news">聽消息<span>（${shop.prices.news | 0} 兩）</span></button>
      <div class="tav-row">${tavBtn("treat", "請全店喝一輪", shop.prices.treat, shop.problems.treat)}${board}</div>
      ${tavDone()}
      ${tavNotes(shop, ["news"], "")}
      ${talk}`; // 鈕都在聽到的消息上面：聽一則多一則，不把請酒那一顆往下推
  }

  function tavAskHtml(shop) {
    const mode = ["ties", "q"].includes(S.tavAsk) ? S.tavAsk : "seek";
    const modes = [["seek", "查人在哪", shop.prices.seek], ["ties", "打聽情誼", shop.prices.ties], ["q", "問酒家", shop.prices.ask]]
      .map(([k, name, price]) => `<button class="shop-page${mode === k ? " on" : ""}" data-act="tav-mode" data-mode="${k}">${name}・${price | 0} 兩</button>`).join("");
    const asked = shop.known.filter((n) => !shop.guests.includes(n)).slice(0, 8); // 問過的（座上客已經列了的不重寫）
    const known = asked.length ? `<div class="tav-known"><span class="gl">問過的</span>${asked.map((n) => `<button class="tav-chip" data-act="tav-name" data-name="${esc(n)}">${esc(n)}</button>`).join("")}</div>` : "";
    const guests = shop.guests.length ? `<div class="tav-known"><span class="gl">座上客</span>${shop.guests.map((n) => `<button class="tav-chip" data-act="tav-name" data-name="${esc(n)}">${esc(n)}</button>`).join("")}</div>` : "";
    const hint = mode === "seek" ? "報個名號（江湖人物或大勢人物都行）。越有名、離這裡越近，越問得準；問不到退一半。"
      : mode === "ties" ? "問誰跟他走得近、他身邊有誰、近來做了什麼。越有名越好打聽；問不到退一半。"
      : `隨口問一句（${shop.ask_chars | 0} 字內），酒家照他聽來的說。他答不上來不收錢。`;
    const box = mode === "q"
      ? `<form class="tav-form" id="tav-q"><input class="input" name="text" data-keep="q" maxlength="${shop.ask_chars | 0}" placeholder="例：最近哪裡最亂？" autocomplete="off"><button class="btn primary small" type="submit">問</button></form>`
      : `<form class="tav-form" id="tav-ask"><input class="input" name="target" data-keep="ask" maxlength="20" placeholder="名號" autocomplete="off"><button class="btn primary small" type="submit">打聽</button></form>`;
    const w = shop.watch || { price: 0, mine: [] };
    const watch = mode === "seek"
      ? `<label class="tav-hush"><input type="checkbox" name="watch" form="tav-ask"${S.tavWatch ? " checked" : ""}> 託酒家留意，多付 ${w.price | 0} 兩（問不清楚時，有了準信捎進你的江湖紀錄）</label>${w.mine.length ? `<ul class="tav-whispers">${w.mine.map((t) => `<li class="named">${esc(t)}</li>`).join("")}</ul>` : ""}` : "";
    const mats = shop.materials.map((m) => `<option value="${esc(m.id)}"${m.id === S.tavMat ? " selected" : ""}>${esc(m.name)}（${m.tier | 0} 階・${m.price | 0} 兩）</option>`).join("");
    return `<div class="shop-pages tav-modes">${modes}</div>
      ${box}${watch}
      <p class="shop-cap">${esc(hint)}</p>${mode === "q" ? "" : guests + known}
      <h4 class="tav-h">打聽素材<small>哪裡採得到</small></h4>
      <form class="tav-form" id="tav-mat"><select class="input" name="material">${mats}</select><button class="btn small" type="submit">打聽</button></form>
      ${tavDone()}
      ${tavNotes(shop, ["ask", "seek", "ties", "material"], "還沒打聽過什麼。")}`;
  }

  function tavWallHtml(shop) {
    const walls = shop.walls.length
      ? `<div class="tav-wall">${shop.walls.map((w) => `<p><span class="ink">${esc(w.text)}</span><small>${esc(w.who)}・${esc(w.when)}<i class="tav-seal">題</i></small></p>`).join("")}</div>`
      : '<p class="shop-empty">粉牆上還乾乾淨淨，等人來題第一句。</p>';
    return `<p class="shop-cap">借酒家的筆，在牆上留一句話（最多 ${shop.wall_chars | 0} 字，${shop.prices.wall | 0} 兩）。來這間酒肆的人都看得到。</p>
      <form class="tav-form" id="tav-wall"><input class="input" name="text" data-keep="wall" maxlength="${shop.wall_chars | 0}" placeholder="題一句" autocomplete="off"><button class="btn primary small" type="submit">題壁</button></form>
      ${tavDone()}${walls}`;
  }

  function tavShadeHtml(shop) {
    const heard = shop.whispers.length
      ? `<ul class="tav-whispers">${shop.whispers.map((w) => `<li class="${w.named ? "named" : ""}">${esc(w.text)}</li>`).join("")}</ul>`
      : '<p class="shop-empty">最近沒聽說有人打聽你。</p>';
    const h = shop.hits;
    const tier = h.tiers.some((t) => t.tier === S.tavTier) ? S.tavTier : 1;
    const tiers = h.tiers.map((t) => `<button type="button" class="tav-tier${t.tier === tier ? " on" : ""}" data-act="tav-tier" data-tier="${t.tier}"><b>${esc(t.name)}</b><small>${t.price | 0} 兩</small></button>`).join("");
    const names = shop.known.slice(0, 8).map((n) => `<button class="tav-chip" data-act="tav-hit-name" data-name="${esc(n)}">${esc(n)}</button>`).join("");
    const mine = h.mine.length ? `<ul class="tav-whispers">${h.mine.map((m) => `<li class="named">${esc(m)}</li>`).join("")}</ul>` : "";
    const hire = h.ended ? "" : `<h4 class="tav-h">買殺手<small>找上門的事，不說是誰</small></h4>
      <p class="shop-cap">報一個查到過的名號。殺手只在城外出手；找不到人，期限到了退一半。</p>
      <div class="tav-tiers">${tiers}</div>
      <form class="tav-form" id="tav-hit"><input class="input" name="target" data-keep="hit" maxlength="20" placeholder="名號" autocomplete="off"><button class="btn primary small" type="submit">雇</button></form>
      <label class="tav-hush"><input type="checkbox" name="hush" form="tav-hit"${S.tavHush ? " checked" : ""}> 加付封口錢 ${h.hush | 0} 兩（失手、被反查時不容易供出你）</label>
      ${names ? `<div class="tav-known"><span class="gl">查到過的</span>${names}</div>` : ""}${mine}`;
    return `<h4 class="tav-h">風聲<small>有人在打聽你</small></h4>${heard}
      <div class="tav-row">${tavBtn("trace", "反查是誰", shop.prices.trace, "")}${tavBtn("hide", "藏起行跡", shop.prices.hide, shop.problems.hide)}${tavBtn("guard", "雇保鏢", h.guard, h.guard_problem)}</div>
      ${shop.hidden ? `<p class="shop-cap">${esc(shop.hidden)}</p>` : '<p class="shop-cap">藏行跡：打點酒家與跑堂，接下來一天別人難打聽到你。保鏢：殺手找上時有人替你擋一擋。</p>'}
      ${tavDone()}${tavNotes(shop, ["trace", "guard"], "")}${hire}${tavNotes(shop, ["hit"], "")}`;
  }

  function tavernHtml(shop) {
    const tab = tavTab();
    const body = { news: tavNewsHtml, ask: tavAskHtml, wall: tavWallHtml, shade: tavShadeHtml }[tab](shop);
    // 燈籠那一幅畫在捲的那一層裡：四頁的框一樣高，換頁時底下的格子不上下跳（Joy 2026-10-19「視窗大小跳來跳去」）
    return `<div class="shop-body"><div class="shop-col">${tab === "news" ? TAV_HERO : ""}${body}</div></div>
      <nav class="shop-tabs">${TAV_TABS.map(([k, name]) => `<button class="shop-tab${tab === k ? " on" : ""}" data-act="tav-tab" data-tab="${k}">${name}</button>`).join("")}</nav>`;
  }

  // 打聽到了的寫成一則（每一頁「剛問到的」），那一句不再另外寫在上面；沒問到、被拒的那一句才寫
  async function tavDo(op, body = {}, route = "tavern") {
    const seen = S.main && S.main.shop && S.main.shop.notes ? S.main.shop.notes.length : 0;
    const top = S.main && S.main.shop && S.main.shop.notes && S.main.shop.notes[0] ? S.main.shop.notes[0].when + S.main.shop.notes[0].title : "";
    await shopDo(route, route === "tavern" ? { op, ...body } : body, (r) => {
      const notes = r.main && r.main.shop && r.main.shop.notes;
      if (notes && notes.length && (notes.length !== seen || notes[0].when + notes[0].title !== top)) S.shopNote = null;
    });
  }

  // ── 馬市（第三節）：一排馬廄（你騎的、待售、裝備庫裡的），點一匹看牠的卡；卡上那一顆送現在的選項 id
  // （market:feed、market:buy、market:wield:<id>）。字待 joy 潤 ──
  // 馬的圖（Joy 2026-10-17 要真的水墨畫，圖另外產）：伺服器列出 web/ 裡真的有的鍵（main.horse_art），有圖放圖，沒有回空字串、照舊畫色塊
  function horseImg(key, cls) {
    return key && ((S.main && S.main.horse_art) || []).includes(key)
      ? `<img class="${cls}" src="/static/horse-${encodeURIComponent(key)}.webp" alt="" loading="lazy">` : "";
  }
  function marketHtml(shop) {
    const live = shop.stalls.filter((h) => !h.empty);
    const pick = live.find((h) => h.id === S.shopHorse) || live.find((h) => h.id === shop.focus) || live[0];
    const stall = (h) => (h.empty
      ? `<div class="stall empty"><span class="who">${esc(h.who)}</span><i class="horse"></i><b>${esc(h.name)}</b></div>`
      : `<button class="stall r-${esc(h.role)}${pick && h.id === pick.id ? " on" : ""}" data-act="shop-horse" data-id="${esc(h.id)}">
          <span class="who">${esc(h.who)}</span>${horseImg(h.art, "horse-pic") || `<i class="horse ${h.coat >= 0 ? `c${h.coat | 0}` : "cx"}"></i>`}<b>${esc(h.name)}</b><small>${dealHtml(h.sub)}</small></button>`);
    return `<div class="shop-body"><div class="shop-col"><div class="stalls${shop.stalls.length > 3 ? " many" : ""}">${shop.stalls.map(stall).join("")}</div>
      ${pick ? horseCard(pick) : ""}</div></div>`;
  }

  // 點著那一匹的卡：名字、階品、跟你騎的比、四項本事的長條、你騎的那匹多飽足長條；底下一顆照伺服器給的（做不了寫原因）
  function horseCard(h) {
    const width = (v) => Math.max(0, Math.min(100, v | 0));
    const bars = h.bars.map((b) => `<div class="abil"><span class="l">${esc(b.label)}</span><span class="v"><i style="width:${width(b.value)}%"></i></span><span class="n">${esc(b.text)}</span></div>`).join("");
    const fed = h.fed ? `<div class="fed"><span class="l">${esc(h.fed.word)} ${h.fed.value | 0}</span><span class="v"><i style="width:${width(h.fed.value)}%"></i></span>${h.fed.note ? `<small>${esc(h.fed.note)}</small>` : ""}</div>` : "";
    const a = h.action;
    const sub = a.enabled ? a.use : a.why;
    return `<article class="horse-card">${horseImg(h.art, "horse-big")}<h4>${esc(h.name)} <small>${esc(h.grade)}</small></h4>
        ${h.compare ? `<p class="cmp">${esc(h.compare)}</p>` : ""}<div class="bars">${bars}</div>${fed}
        <button class="btn primary horse-act" data-act="choose" data-id="${esc(a.id)}" ${a.enabled ? "" : "disabled"}><b>${esc(a.label)}</b>${sub ? `<small>${esc(sub)}</small>` : ""}</button>
      </article>`;
  }

  // ── 懸賞榜（第四節）：上面一排手上揭著的格子，木板上釘告示（顏色分種類：討伐紅、打探藍、護送綠、求藝求兵金邊、通緝黑；
  // 揭了的蓋「已揭」），點一張放大成一張紙。揭下、交出…送現在的選項 id；放棄先問一次（shop-ask）。字待 joy 潤 ──
  function boardHtml(shop) {
    const zoomId = shop.picked || S.boardZoom; // 第三層開著（伺服器的 picked）：放大的一定是那一張
    const zoom = zoomId ? shop.notes.find((n) => n.id === zoomId) : null; // 被拿走了的告示跟著收
    const held = shop.held;
    const slots = held.rows.map((r) => `<button class="slot" data-act="board-zoom" data-id="${esc(r.id)}"><b>${esc(r.title)}</b><small>${esc(r.due)}</small></button>`).join("")
      + (held.left ? `<div class="slot empty">${esc(held.left_text)}</div>` : "");
    // 告示照草圖寫得很短（企劃者 2026-10-14 微調）：種類・哪一方（色塊小標籤）、目標、期限與名額，重賞、你有幾件合用各一個小字；
    // 要做什麼與賞寫在點開的紙上。期限名額寫短的（n.short，「期限 第 6 週・剩 2」，不折行）；完整的時刻與「名額還剩 N」在紙上（FB-196）
    // 21 天季：告示右上角一個小朱印寫銀兩（n.corner，第 5 批畫面第三組丙）
    // 21 天季（草圖丙，FB-391）：附贈與重賞一格一格（.extra，只排一行，放不下時重賞那一格藏起來，只留朱印與附贈）
    const extra = (n) => (n.gift || n.prize_chip
      ? `<span class="extra">${n.gift ? `<span class="gift">${esc(n.gift)}</span>` : ""}${n.prize_chip ? `<span class="prize">${esc(n.prize_chip)}</span>` : ""}</span>`
      : "");
    const face = (n) => `<span class="tag">${esc(n.kind_name)}・${esc(n.issuer)}</span>${n.corner ? `<i class="corner">${esc(n.corner)}</i>` : ""}<b>${esc(n.head)}</b>
        ${n.corner ? extra(n) : n.prize ? `<small class="prize">${esc(n.prize)}</small>` : ""}${n.have ? `<small class="prize">${esc(n.have)}</small>` : ""}
        <small class="due">${esc(n.short)}</small>`;
    const note = (n) => (n.done
      ? `<div class="note k-${esc(n.kind)} done">${face(n)}<i class="stamp">交差</i></div>`
      : `<button class="note k-${esc(n.kind)}${n.held ? " held" : ""}${!n.held && !n.action.enabled ? " dim" : ""}" data-act="board-zoom" data-id="${esc(n.id)}">
        ${face(n)}${n.held ? '<i class="stamp">已揭</i>' : ""}</button>`);
    // 剛交差的那一張（boardHanded）：伺服器那一份已經沒有它，照原本的位置再畫一下、蓋「交差」，跟著淡出（企劃者 2026-10-14 微調）
    const notes = shop.notes.slice();
    const done = S.boardStamp && !notes.some((n) => n.id === S.boardStamp.id) ? S.boardStamp : null;
    if (done) notes.splice(Math.min(done.at, notes.length), 0, { ...done.note, done: true });
    const board = notes.length ? `<div class="board">${notes.map(note).join("")}</div>` : `<p class="shop-empty board-empty">${esc(shop.empty)}</p>`;
    return `<div class="shop-body${zoom ? " zooming" : ""}"><div class="shop-col"><div class="held-row"><p>${esc(held.head)}</p><div class="slots">${slots}</div></div>${board}</div></div>
      ${zoom ? paperHtml(zoom, shop) : ""}`;
  }

  // 放大的那一張紙：完整的要求、賞、期限與名額，底下的鈕照那一張（第三層開著：合用的東西一件一顆，每顆照選單上的 confirm 先問一次）
  function paperHtml(n, shop) {
    const a = n.action;
    let btns;
    if (shop.picked === n.id) {
      btns = `<div class="hand-in">${shop.hand_in.map((o) => `<button class="btn${o.enabled ? "" : " ghost"}" data-act="choose" data-id="${esc(o.id)}" ${o.enabled ? "" : "disabled"}>${esc(o.label)}</button>`).join("")}</div>
        <div class="btns one"><button class="btn" data-act="board-close">收起</button></div>`;
    } else if (a.verb === "drop") {
      btns = `<div class="btns"><button class="btn danger" data-act="shop-ask" data-id="${esc(a.id)}" data-confirm="${esc(a.confirm)}" data-yes="放棄">放棄</button><button class="btn" data-act="board-close">收起</button></div>`;
    } else {
      btns = `${a.why ? `<p class="why">${esc(a.why)}</p>` : ""}<div class="btns"><button class="btn primary" data-act="choose" data-id="${esc(a.id)}" ${a.enabled ? "" : "disabled"}>${a.verb === "pick" ? "交出…" : "揭下"}</button><button class="btn" data-act="board-close">放回去</button></div>`;
    }
    // 紙貼在畫面下緣（企劃者 2026-10-14 微調，草圖那樣），不蓋住木板與招牌；紙太長（第三層交出清單）自己捲
    return `<div class="board-sheet"><article class="paper k-${esc(n.kind)}">${n.held ? '<i class="stamp">已揭</i>' : ""}
        <span class="tag">${esc(n.kind_name)}・${esc(n.issuer)}掛的</span><h4>${esc(n.title)}</h4>
        <p>${esc(n.how)}</p>${n.have ? `<p class="have">${esc(n.have)}</p>` : ""}${n.tags ? rewardChips(n.tags) : `<p class="reward">賞：${esc(n.reward)}</p>`}
        <p class="due">${n.level ? `${esc(n.level)}・` : ""}${esc(n.due)}</p>
        ${btns}</article></div>`;
  }

  // 第三層（替一張求藝、求兵挑東西）開著時選單上只有那一張的交出鈕與「回到懸賞榜」：放大別張、收起、出店之前先送 bounty:unpick
  // （不然按下去會被 Game.choose 擋成「榜上的情形變了」）
  async function boardUnpick(el) {
    const shop = S.main && S.main.shop;
    if (shop && shop.shop === "board" && shop.picked) await choose(el, shop.unpick);
  }
  async function boardZoom(el, id) {
    const shop = S.main && S.main.shop;
    if (shop && shop.picked && shop.picked !== id) await boardUnpick(el);
    S.boardZoom = id;
    renderShop();
  }
  async function boardClose(el) {
    S.boardZoom = null;
    await boardUnpick(el);
    renderShop();
  }
  async function boardLeave(el) {
    await boardUnpick(el);
    const shop = S.main && S.main.shop;
    if (shop && shop.shop === "board") await choose(el, shop.back);
  }
  // 交差之後（第四節；企劃者 2026-10-14 微調）：送了 bounty:give:<懸賞>:…、回來的木板上沒有那一張了（自己交過的不再列），
  // 那張告示照原本的位置再畫一下、本身蓋「交差」，停一下跟著淡出（減少動態效果的人不淡出，時間到直接拿掉）。被拒絕的（那一張還在）不蓋
  const STAMP_MS = 1400;
  function boardHanded(id, before) {
    const shop = S.main && S.main.shop;
    const bid = id.split(":")[2];
    const at = before && before.shop === "board" ? before.notes.findIndex((n) => n.id === bid) : -1;
    if (at < 0 || !shop || shop.shop !== "board" || shop.notes.some((n) => n.id === bid)) return;
    S.boardStamp = { id: bid, note: before.notes[at], at };
    S.boardZoom = null;
    renderShop();
    setTimeout(() => {
      if (!S.boardStamp || S.boardStamp.id !== bid) return;
      S.boardStamp = null;
      if (S.main && S.main.shop) renderShop();
    }, STAMP_MS);
  }

  // 架上（2.1）：一件一格；配得上的標出來，買不了的灰掉寫原因
  // 架上那一頁最上面的爐火與鐵砧（企劃者 2026-10-14，照草圖 container.html 的 A）：一大團發亮的橘色圓頂爐口、火光往外暈，底下鐵砧；
  // 純 CSS 畫（style.css 的 .forge-mouth、.forge-anvil）；Joy 之後有正式的圖可以換
  const SMITH_HERO = '<div class="smith-hero" aria-hidden="true"><div class="forge-mouth"><i class="flame"></i></div><div class="forge-anvil"></div></div>';

  function shelfHtml(shop) {
    // 這一段的變數不用單字母 x：tests/test_server.py 把修練頁到輿圖之間那個變數讀的欄位都當成 menxia_view 的欄位查
    return `<div class="shop-grid">${shop.shelf.map((ware) => `<button class="shop-item${ware.fit ? " fit" : ""}" data-act="choose" data-id="${esc(ware.id)}" ${ware.enabled ? "" : "disabled"}>
        <b>${esc(ware.name)}</b><span>${esc(ware.kind)}・屬${esc(ware.attribute)}・${esc(ware.tier)}</span>${ware.value ? `<span>${esc(ware.value)}</span>` : ""}
        ${ware.note ? `<span class="fit-note">${esc(ware.note)}</span>` : ""}<span class="price">${ware.enabled ? `${ware.price | 0} 兩` : esc(ware.why)}</span></button>`).join("")}</div>`;
  }

  // 淬煉與修（2.4）：身上那件的卡（鋒利度或耐久度的長條、淬煉五格），兩顆大鈕；做不了照伺服器的原因寫
  function temperHtml(shop) {
    const w = shop.worn;
    if (!w.item) return `<p class="shop-empty">${esc(w.empty)}</p>`;
    const it = w.item;
    const pips = Array.from({ length: it.temper_max | 0 }, (_, i) => `<i class="${i < it.tempers ? "on" : ""}"></i>`).join("");
    const big = (b, name) => `<button class="btn shop-big" data-act="choose" data-id="${esc(b.id)}" ${b.enabled ? "" : "disabled"}><b>${name}</b><small>${esc(b.enabled ? b.use : b.why)}</small></button>`;
    return `<div class="shop-worn"><b>【${esc(it.name)}】</b><span>${esc(it.grade)}</span>
        <div class="shop-wear"><span>${esc(it.wear_word)} ${it.wear | 0}</span><div class="wear-bar"><i style="width:${Math.max(0, Math.min(100, it.wear | 0))}%"></i></div></div>
        <div class="tempers"><span>淬煉</span>${pips}</div></div>
      <div class="shop-bigs">${big(w.repair, "修")}${big(w.temper, "淬煉")}</div>
      ${w.unfit ? `<p class="shop-note">${esc(w.unfit)}</p>` : ""}`;
  }

  // 裝備庫（2.5）：每件一列「換上」「拆解」（走修練頁的動作，不受店裡選單只列 8 顆的限制）；原品、本命兵器的拆解灰掉寫原因；
  // 等著定名的原品那一列底下一張定名表單；先列 8 件，其餘按「再列 N 件」
  function rackHtml(shop) {
    const rows = shop.rack.rows;
    if (!rows.length) return '<p class="shop-empty">裝備庫裡沒有這一欄的東西。</p>'; // 待 joy 潤
    const shown = S.shopMore ? rows : rows.slice(0, SHOP_RACK_LIST);
    const more = rows.length - shown.length;
    const line = (r) => (shop.page === "armor"
      ? `屬${r.attribute}・${r.grade}・${r.wear_word} ${r.edge | 0}・少扣 ${r.cut}`
      : `${r.noun || r.kind}・屬${r.attribute}・${r.grade}・鋒利度 ${r.edge | 0}${r.bonus ? `・威力 ${r.bonus}` : "・用不上"}`);
    return `<p class="shop-cap">裝備庫 ${shop.rack.used | 0}／${shop.rack.cap | 0}</p>${shown.map((r) => `<div class="shop-row">
        <div class="winfo"><b>【${esc(r.name)}】</b><span>${nbHtml(line(r))}</span>${r.wield_ok === false ? `<small class="rwhy">${esc(r.wield_note || "")}</small>` : ""}</div>
        <div class="wbtns"><button class="btn small" data-act="shop-wield" data-id="${esc(r.id)}"${r.wield_ok === false ? ` disabled title="${esc(r.wield_note || "")}"` : ""}>換上</button>${r.keep
          ? `<button class="btn small ghost" disabled>${esc(r.keep)}</button>`
          : `<button class="btn small ghost" data-act="shop-dismantle" data-id="${esc(r.id)}" data-confirm="${esc(r.confirm || "")}">拆解</button>`}</div>
      </div>${r.divine ? divineFormHtml(r.id, r.divine.pattern, true, r.divine.unit) : ""}`).join("")}
      ${more > 0 ? `<button class="btn small ghost shop-more" data-act="shop-more">再列 ${more} 件</button>` : ""}`;
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
  }

  // 輪詢拿到新的畫面（refreshPage 最前面叫）：店面開了或收了整個重畫；開著而且店裡的資料變了只重畫店面（手指按著時等放開，
  // 同江湖頁的規則）。回 true：店面開著，底下的頁面被蓋住、不必再畫
  function shopPolled(old) {
    const was = old && old.shop ? old.shop.shop : null, now = S.main && S.main.shop ? S.main.shop.shop : null;
    if (was !== now) { render(); return true; } // 開了、收了、換了一間：整個重畫
    if (!now) return false;
    if (JSON.stringify(old.shop) !== JSON.stringify(S.main.shop)) {
      if (pointerHeld) redrawHeld = true;
      else { renderShop(); if (now === "smith" && S.shopPot && (S.shopPot.main || S.shopPot.aux)) updateSmithLine(); }
    }
    return true;
  }

  // 店裡的換上、拆解、神器定名：走修練頁那幾條（/api/menxia/…），回來照新的畫面畫、話用提示泡泡講
  async function shopMx(op, body) {
    let said = "";
    await busy(async () => {
      const r = await api(`/api/menxia/${op}`, body);
      if (r.menxia) S.menxia = r.menxia;
      setMain(r.main);
      render();
      said = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      if (said) toast(said);
    });
    return said; // 店面上定名被拒時，表單裡留這一句（FB-193）
  }

  // 神器原品定名的表單（打造隱藏配方設計 5.2）：修練頁那一列底下、店面的出爐卡與裝備庫都用這一張。shop 為真時表單送店面的那一條
  // （data-op shop-name-divine、沿用譜名 shop-divine-keep），id 也分開，免得同一個畫面兩張撞 id。字待 joy 潤
  // unit：「這把／件／副神器」的量詞（FB-197），伺服器照 equipment.unit_for 給（修練頁與店面裝備庫那一列的 divine.unit、出爐卡的 unit），
  // 這裡不另寫一份對照；沒帶（舊的資料）照原本寫「把」
  function divineFormHtml(id, pattern, shop = false, unit = "") {
    const op = shop ? "shop-name-divine" : "name-divine";
    return `<form class="naming divine" id="${op}-${esc(id)}" data-op="${op}" data-id="${esc(id)}">
        <small>你打出了神器</small>
        <p>你是江湖上第一個打出這${esc(unit || "把")}神器的人，替它定一個名字（2～6 個字，全服不能重名）。</p>
        <div class="row"><input class="input" name="name" maxlength="6" placeholder="神器的名字"><button class="btn primary small" type="submit">定名</button></div>
        ${S.divineWhy[id] ? `<p class="form-why">${esc(S.divineWhy[id])}</p>` : ""}
        <button class="btn small ghost" type="button" data-act="${shop ? "shop-divine-keep" : "divine-keep"}" data-id="${esc(id)}">沿用譜名【${esc(pattern)}】</button>
      </form>`;
  }

  // 爐裡的東西（2.2）：換了兵器防具那一頁、或還沒放過，就從空爐、預設的種類開始
  function shopPotNow(shop) {
    const pot = S.shopPot;
    return pot && pot.slot === shop.page ? pot : { slot: shop.page, kind: shop.forge.kind, main: null, aux: null };
  }
  // 這一爐的說法：爐裡的東西問過伺服器了用那一份（同一頁、同一種類），不然是空爐那一份（shop.forge.line）。
  // 回應還沒回來（爐裡剛換了一樣）時手上那一份說的是上一爐：素材格照舊畫它的，「這一爐會怎樣」與開爐鈕當作還沒放好
  function shopLineNow(shop, pot) {
    const line = S.shopLine;
    const got = line && line.kind === pot.kind && pot.slot === shop.page ? line : shop.forge.line;
    return got.ready && (got.main !== pot.main || got.aux !== pot.aux) ? { ...got, ready: false } : got;
  }
  // 爐子中間的火（內嵌 SVG，水墨暖色；Joy 之後有正式的圖可以換）
  const FLAME_SVG = '<svg viewBox="0 0 60 60" aria-hidden="true"><path class="fl-out" d="M30 4 C40 18 50 26 46 40 C43 52 34 56 30 56 C24 56 14 50 14 38 C14 28 22 22 26 12 C28 20 31 24 34 26 C34 18 32 10 30 4Z"/><path class="fl-in" d="M30 24 C36 32 40 38 37 46 C35 51 32 52 30 52 C26 52 22 48 23 42 C24 36 28 32 30 24Z"/></svg>';

  // 打造頁（2.2）：上面一排種類（防具頁換成一行說明），中間爐子左右兩格（主料、輔料；點有東西的那一格拿出來），
  // 兩格放好時底下寫這一爐會怎樣（種類、屬性、階、工錢、三個機率、最多兩句原因、鑄譜上打中過的那一句）與開爐鈕，最底下是素材格。
  // 這一段的變數不用單字母 x（見 shelfHtml）
  function forgePageHtml(shop) {
    const f = shop.forge, pot = shopPotNow(shop), line = shopLineNow(shop, pot);
    const mats = new Map(f.materials.map((mat) => [mat.id, mat]));
    const slot = (role, id) => {
      const mat = id && mats.get(id);
      return `<button class="pot-slot ${role}" data-act="shop-slot" data-role="${role}" ${mat ? "" : "disabled"}><small>${role === "main" ? "主料" : "輔料"}</small>${mat
        ? `<b><i class="dot ${SHOP_ATTR[mat.attribute] || ""}"></i>${esc(mat.name)}</b><small>${esc(mat.tier_word)}</small>` : "<span>點素材放進來</span>"}</button>`;
    };
    const kinds = f.kinds.length
      ? `<div class="shop-kinds">${f.kinds.map((k) => `<button class="kind${k.kind === pot.kind ? " on" : ""}${k.fit ? " fit" : ""}" data-act="shop-kind" data-kind="${esc(k.kind)}">${esc(k.label)}${k.fit ? "<sup>配</sup>" : ""}</button>`).join("")}</div>`
      : `<p class="shop-note">${esc(f.note)}</p>`;
    const out = line.ready ? `<div class="pot-out"><b>${esc(line.kind_label)}・屬${esc(line.attribute)}・${esc(line.tier)}</b><span>工錢 ${line.price | 0} 兩</span>
        ${line.head ? `<p class="pot-head">${esc(line.head)}</p>` : ""}
        ${line.odds ? `<div class="odds">${line.odds.filter((o) => o.pct > 0).map((o) => `<i class="q-${esc(o.q)}" style="width:${o.pct | 0}%"><span>${esc(o.q.slice(0, 1))} ${o.pct | 0}%</span></i>`).join("")}</div>` : ""}
        ${line.reasons.length ? `<p class="pot-why">${line.reasons.map(esc).join("、")}</p>` : ""}
        ${line.named_hint ? `<p class="pot-why">${esc(line.named_hint)}</p>` : ""}</div>` : "";
    const can = line.ready && !line.problem;
    // 整段字包在一個 span 裡（FB-297 複驗）：.btn 是不換行的橫向 flex，字與每一段折扣原因的小段各成一個 flex 項目時排成一列，
    // 兩段原因就把鈕撐出 375、字擠成直排、「鑄譜」被推出畫面；只有一個項目時字照常換行
    const go = `<button class="btn primary shop-go" data-act="shop-go"${can ? "" : " disabled"}><span>${dealHtml(line.ready ? line.problem || line.go : "開爐")}</span></button>`;
    // 素材格一屬性一排（企劃者 2026-10-14 微調）：伺服器已經照剛柔快慢、再照階排好，這裡只照屬性分排、排頭寫屬性
    const rows = [];
    for (const c of line.cells || []) {
      const mat = mats.get(c.id);
      if (!mat) continue;
      const cell = `<button class="cell t${mat.tier | 0}${c.main || c.aux ? " used" : ""}${c.ok ? "" : " off"}" data-act="shop-cell" data-id="${esc(c.id)}" data-why="${esc(c.why || "")}">
        <span class="n">${mat.count | 0}</span><span class="nm"><i class="dot ${SHOP_ATTR[mat.attribute] || ""}"></i>${esc(mat.name)}</span><small>${esc(mat.tier_word)}</small>${c.ok ? "" : `<span class="why">${esc(c.why)}</span>`}</button>`;
      const last = rows[rows.length - 1];
      if (last && last.attribute === mat.attribute) last.cells.push(cell);
      else rows.push({ attribute: mat.attribute, cells: [cell] });
    }
    const cells = rows.map((r) => `<div class="cell-row"><span class="row-attr ${SHOP_ATTR[r.attribute] || ""}">${esc(r.attribute)}</span>${r.cells.join("")}</div>`).join("");
    return `${kinds}
      <div class="furnace${S.shopFiring ? " firing" : ""}">${slot("main", pot.main)}<div class="flame">${FLAME_SVG}</div>${slot("aux", pot.aux)}</div>
      ${out}<div class="shop-gorow">${go}<button class="btn small ghost shop-book" data-act="book-open" data-book="forge">鑄譜</button></div>
      ${line.rack_full ? `<p class="shop-warn">${esc(line.rack_full)}</p>` : ""}
      <p class="shop-cap">背包的素材（點一下放進爐裡）</p><div class="cells${shop.four ? " four" : ""}">${cells || '<p class="shop-empty">背包裡沒有素材。</p>'}</div>`;
  }

  // 爐裡換了東西：先照放的畫一次，再問這一爐會怎樣（/api/smith_line；只用最後一次請求的回應）
  async function setPot(change) {
    const shop = S.main && S.main.shop;
    if (!shop) return;
    S.shopPot = { ...shopPotNow(shop), ...change, slot: shop.page };
    renderShop();
    await updateSmithLine();
  }
  // 點一格素材（2.2）：灰掉的只說原因（不放進去）；能放的照伺服器說的去處（主料格空著先放主料，否則放輔料；兩格都滿了換掉輔料）
  function shopCell(id, why) {
    if (why) { toast(why); return; }
    const shop = S.main && S.main.shop;
    if (!shop) return;
    const pot = shopPotNow(shop);
    // 放到哪一格照爐裡現在的樣子（主料空著先放主料），不照手上那一份說法：連點兩格時回應還沒回來，那一份還寫著「放主料」
    if ((shopLineNow(shop, pot).cells || []).some((c) => c.id === id)) setPot(pot.main ? { aux: id } : { main: id });
  }
  let smithLineSeq = 0;
  async function updateSmithLine() {
    const seq = ++smithLineSeq;
    const shop = S.main && S.main.shop;
    if (!shop) return;
    const pot = shopPotNow(shop);
    try {
      const r = await api("/api/smith_line", { kind: pot.kind, main: pot.main, aux: pot.aux });
      if (seq !== smithLineSeq || !S.main || !S.main.shop) return;
      S.shopLine = r;
      S.shopPot = { ...pot, main: r.main, aux: r.aux }; // 伺服器照現在的背包把放不下的拿掉（例：料在另一個分頁用掉了）
      renderShop();
    } catch (e) { /* api() 提示過 */ }
  }
  // ── 開爐與出爐（2.3）：品質在按下開爐那一刻由規則擲好，爐火與光只是演出 ──
  const FIRE_MS = 900; // 爐火竄一下的長度（等回應的同時跑；減少動態效果的人不等）
  const reduceMotion = () => !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const GLOW_HINT = { none: "布縫裡沒透出光", cyan: "布縫裡透出青光", gold: "布縫裡透出金光", purple: "布縫裡透出紫光", red: "布縫裡透出紅光", redgold: "布縫裡透出赤金光" }; // 待 joy 潤

  async function smithForge() {
    const shop = S.main && S.main.shop;
    if (!shop) return;
    const pot = shopPotNow(shop);
    if (!pot.main || !pot.aux) return;
    await busy(async () => {
      S.shopFiring = !reduceMotion();
      if (S.shopFiring) renderShop();
      const fire = S.shopFiring ? new Promise((ok) => setTimeout(ok, FIRE_MS)) : null;
      try {
        const r = await api("/api/do/smith_forge", { kind: pot.kind, main: pot.main, aux: pot.aux });
        if (fire) await fire;
        if (r.forged) {
          S.shopReveal = r.forged; S.shopOpened = false; // 鐵匠遞出一包麻布（掌櫃那一句在伺服器換成遞布那一句）
          S.shopPot = { ...pot, main: null, aux: null }; S.shopLine = null;
        }
        S.shopFiring = false;
        setMain(r.main);
        render();
        if (!r.forged) { // 被拒絕（2.3）：不遞布，原因用提示泡泡講，兩格照放著，再問一次這一爐（料可能在另一個分頁用掉了）
          const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
          if (text) toast(text);
          updateSmithLine();
        }
      } finally { S.shopFiring = false; }
    }, WAIT_LINES.forge);
  }

  // 麻布與出爐卡（2.3）：先包著（光色照結果），點開是卡——名字、階品、種類屬性、加成或減損、配不配得上；首位發現多一個朱印；
  // 還等著定名的原品多一張定名表單（同修練頁那一張）；底下的鈕照那件去了哪裡：進了裝備庫是「換上」與「留在裝備庫」，在手上只有「收下」。
  // 名字照店面那一份（定了名之後是新名字）。這一段的變數不用單字母 x（見 shelfHtml）
  function revealHtml(card, shop) {
    if (!S.shopOpened) {
      return `<div class="reveal-layer"><button class="bundle g-${esc(card.glow)}" data-act="shop-unwrap" aria-label="點開麻布"><span>裹著麻布</span><small>${esc(GLOW_HINT[card.glow] || "")}</small></button><p class="tapme">點開看看</p></div>`;
    }
    const rows = [...(shop.rack.rows || []), ...(shop.worn.item ? [shop.worn.item] : [])];
    const now = rows.find((row) => row.id === card.id);
    const pending = (shop.pending || {})[card.id];
    const btns = card.where === "rack"
      ? `<button class="btn primary" data-act="shop-wield" data-id="${esc(card.id)}"${now && now.wield_ok === false ? ` disabled title="${esc(now.wield_note || "")}"` : ""}>換上</button><button class="btn" data-act="shop-keep">留在裝備庫</button>`
      : '<button class="btn primary" data-act="shop-keep">收下</button>';
    return `<div class="reveal-layer"><article class="forge-card g-${esc(card.glow)}">
        ${card.first ? '<span class="first-seal">首位發現</span>' : ""}
        <span class="q">${esc(card.grade)}</span><h4>${esc((now && now.name) || card.name)}</h4>
        <p class="meta">${esc(card.kind)}・屬${esc(card.attribute)}</p>
        ${card.value ? `<p class="stat">${esc(card.value)}</p>` : ""}${card.fit ? `<p class="fit">${esc(card.fit)}</p>` : ""}${(card.tactic || []).map((t) => `<p class="fit tactic">${esc(t)}</p>`).join("")}
        ${pending ? divineFormHtml(card.id, pending, true, card.unit) : ""}
        <div class="btns${card.where === "rack" ? "" : " one"}">${btns}</div></article></div>`;
  }

  function bookHtml(which = S.book === "forge" ? "forge" : "arts") {
    const rows = manualRows(which), b = BOOKS[which];
    const now = rows.filter((r) => !r.past); // 卷首只算這一季真的聽到、打中的：跨季記得的那幾行（past）照樣列在卷裡（FB-404）
    const solved = now.filter((r) => r.solved).length;
    const leaves = rows.length ? rows.map((r, k) => `<article class="leaf${r.solved ? " solved" : ""}">
        <header class="leaf-head"><span>第${cnNum(k + 1)}則</span><span class="leaf-state">${r.solved ? "已參透" : "未參透"}</span></header>
        <div class="leaf-text">${r.clues.map((c) => `<p>${clauses(c).map((t) => `<span>${esc(t)}</span>`).join("")}</p>`).join("")}</div>
        <footer class="leaf-foot">${r.solved ? `${sealSvg(r.solved)}<span class="leaf-sign">${b.verb}<b>【${esc(r.solved)}】</b></span>` : '<span class="leaf-sign muted">尚待參悟</span>'}${r.recipe ? `<p class="leaf-recipe">${esc(r.recipe)}</p>` : ""}</footer>
      </article>`).join("")
      : `<article class="leaf empty"><div class="leaf-text"><p>卷中尚無一字</p></div>
        <p class="leaf-hint">${b.empty}</p></article>`;
    return `<div class="book-layer" role="dialog" aria-label="${b.title}">
      <header class="book-bar"><button class="book-back" data-act="book-close" aria-label="返回">‹ 返回</button><span class="book-bar-title">${b.title}</span></header>
      <div class="book-cover">
        <svg class="book-hills" viewBox="0 0 375 120" preserveAspectRatio="none" aria-hidden="true">
          <path class="hill far" d="M0 86 C40 58 70 64 104 46 C134 30 160 52 190 40 C226 26 258 48 292 36 C326 24 352 40 375 34 V120 H0Z"/>
          <path class="hill near" d="M0 104 C36 86 72 96 110 80 C150 64 178 88 222 76 C262 66 300 86 340 74 C356 70 366 72 375 70 V120 H0Z"/>
        </svg>
        <i class="book-moon" aria-hidden="true"></i>
        <div class="book-title"><span>${b.title}</span></div>
        <p class="book-sub">本季所聞${b.unit} ${now.length} 則${solved ? `・已參透 ${solved} 則` : ""}</p>
      </div>
      <div class="leaves">${leaves}</div>
    </div>`;
  }

  // ── 玩家傳（第二批）：季末的《某某傳》，疊在整個畫面上（S.zhuan = { season, view }）──
  // view 是 /api/zhuan 回的（Game.biography_view＋writing、url）。還沒寫成：一顆「請史官落筆」；正在寫：每幾秒問一次（zhuanPoll）。
  // 寫成了：段落（評曰那一段另起）、直書切換（記在這個瀏覽器，跟公開頁同一個鍵）、公開分享的開關與網址、重寫一次。字一律跳脫。
  // 樣子是竹簡，在 web/zhuan.css（跟公開頁 zhuan_html.py 共用標記），不用武學譜那本書（企劃者 2026-10-12）
  const ZHUAN_VERTICAL = "tx-zhuan-vertical";
  const ZHUAN_POLL_MS = 4000;
  function zhuanVertical() {
    if (S.zhuanVertical === undefined) {
      try { S.zhuanVertical = localStorage.getItem(ZHUAN_VERTICAL) === "1"; } catch (e) { S.zhuanVertical = false; }
    }
    return S.zhuanVertical;
  }
  // 篇名那一塊（公開頁 zhuan_html.head 同一份標記）：裝飾、直書的篇名、底下一行季數
  function zhuanHead(title, sub) {
    return `<header class="zh-head"><div class="zh-orn" aria-hidden="true">${"<i></i>".repeat(6)}</div>
      <div class="zh-label" style="--slip-size:${slipSize(title)}px"><h1 class="zh-title">${esc(title)}</h1></div>
      <p class="zh-sub">${esc(sub)}</p></header>`;
  }
  // 名號的方印（陰刻）：四字兩行兩列、其餘一直行，右行先讀。zhuan_html.seal 同一條算法
  function zhuanSeal(name) {
    const chars = [...name].slice(0, 6);
    const n = chars.length, cols = n >= 4 ? 2 : 1, rows = Math.ceil(n / cols), cell = 40 / Math.max(rows, cols);
    const glyphs = chars.map((ch, k) => {
      const col = Math.floor(k / rows), row = k % rows;
      return `<text x="${(46 - (col + 0.5) * (40 / cols)).toFixed(1)}" y="${(6 + (row + 0.5) * (40 / rows)).toFixed(1)}" font-size="${(cell * 0.86).toFixed(1)}">${esc(ch)}</text>`;
    }).join("");
    return `<svg class="zh-seal" viewBox="0 0 52 52" role="img" aria-label="${esc(name)}"><rect x="2" y="2" width="48" height="48" rx="3"/><rect class="rim" x="5" y="5" width="42" height="42" rx="1.5"/>${glyphs}</svg>`;
  }
  function zhuanHtml(z) {
    const v = z.view;
    const head = v ? v.title : "列傳";
    const wait = (inner) => `<div class="zh-body"><section class="zh-panel zh-wait">${inner}</section></div>`;
    let body;
    if (!v) body = wait("<p>翻開史冊…</p>");
    else if (!v.written) {
      body = wait(v.writing
        ? '<p class="zh-ink" aria-hidden="true"><i></i><i></i><i></i></p><p>史官正在落筆，照你這一季的行狀寫一篇列傳。</p><p class="muted">大約一兩分鐘；可以先去別處，回來再翻。</p>'
        : v.can_write
          ? '<p>這一季的行狀已經收進史館。</p><button class="btn primary zhuan-go" data-act="zhuan-write">請史官落筆</button>'
          : "<p>這一季還不能寫傳。</p>");
    } else {
      const vertical = zhuanVertical();
      const paras = v.paragraphs.map((p) => `<p${p.startsWith("評曰") ? ' class="ping"' : ""}>${esc(p)}</p>`).join("");
      const share = v.public
        ? `<p class="zh-url"><span>${esc(v.url || "")}</span></p>
           <div class="row"><button class="btn primary" data-act="zhuan-send">分享給朋友</button><button class="btn" data-act="zhuan-share" data-public="0">收回</button></div>
           <p class="muted">拿到網址的人不用登入就能讀；收回之後網址就失效。</p>`
        : `<button class="btn" data-act="zhuan-share" data-public="1">公開分享</button>
           <p class="muted">預設只有你看得到。公開之後會有一個網址，可以貼到 LINE、FB，隨時能收回。</p>`;
      body = `<div class="zh-tools"><button data-act="zhuan-vertical" aria-pressed="${vertical}">直書</button></div>
        <div class="zh-body"><article class="zh-text${vertical ? " vertical" : ""}">${paras}</article><div class="zh-seals">${zhuanSeal(head.replace(/傳$/, ""))}</div>
        <section class="zh-panel">${share}</section>
        ${v.can_rewrite ? '<button class="zh-again" data-act="zhuan-rewrite">請史官重寫一次</button>' : ""}</div>`;
    }
    return `<div class="zhuan-layer zh zh-bamboo" role="dialog" aria-label="${esc(head)}">
      <div class="zh-bar"><button data-act="zhuan-close" aria-label="返回">‹ 返回</button><span>列傳</span></div>
      ${zhuanHead(head, `第 ${Number(z.season)} 季${v && v.scenario ? `・${esc(v.scenario)}` : ""}`)}
      ${body}
    </div>`;
  }
  // 篇名的字照字數縮：名號最長十來個字，一律直書排進一條（四字以內 30px）。zhuan_html.slip_size 同一條算法
  const slipSize = (title) => Math.min(30, Math.floor(176 / [...title].length / 1.3));
  // 入口（江湖頁休季的那一張、行狀頁的歷季列傳）的小圖：一捆竹簡
  function zhuanIcon() {
    return '<svg viewBox="0 0 42 46" aria-hidden="true"><g fill="#d9b878" stroke="#6e4f29" stroke-width=".8">' + [4, 11, 18, 25, 32].map((x) => `<rect x="${x}" y="3" width="6" height="40" rx="1.5"/>`).join("") + '</g><path d="M1 12h40M1 34h40" stroke="#5a3e1d" stroke-width="2.2"/></svg>';
  }
  function zhuanEntry(b, sub, go = b.written === false ? "立傳" : "翻閱") {
    return `<button class="zh-entry zh-bamboo" data-act="zhuan-open" data-season="${Number(b.season)}">${zhuanIcon()}<span><b>${esc(b.title)}</b><small>${esc(sub)}</small></span><i class="go">${go} ›</i></button>`;
  }
  let zhuanTimer = 0;
  async function loadZhuan() {
    const z = S.zhuan;
    if (!z) return;
    clearTimeout(zhuanTimer);
    try { z.view = await api(`/api/zhuan?season=${Number(z.season)}`); } catch (e) { return; }
    if (S.zhuan !== z) return; // 等的時候闔上了、換了一季
    render();
    if (z.view.writing) zhuanTimer = setTimeout(loadZhuan, ZHUAN_POLL_MS);
  }
  async function zhuanPost(path, body) {
    const z = S.zhuan;
    try { z.view = await api(path, { season: z.season, ...body }); } catch (e) { return; }
    if (S.zhuan !== z) return;
    render();
    if (z.view.writing) { clearTimeout(zhuanTimer); zhuanTimer = setTimeout(loadZhuan, ZHUAN_POLL_MS); }
  }
  // 分享：手機上叫系統的分享選單，沒有就複製網址，再不行就選起來讓人自己複製
  async function zhuanSend() {
    const v = S.zhuan && S.zhuan.view;
    if (!v || !v.url) return;
    if (navigator.share) {
      try { await navigator.share({ title: v.title, url: v.url }); } catch (e) { /* 取消了 */ }
      return;
    }
    try { await navigator.clipboard.writeText(v.url); toast("網址已複製"); return; } catch (e) { /* 退回選取 */ }
    const span = document.querySelector(".zh-url span");
    if (span) { const r = document.createRange(); r.selectNodeContents(span); const sel = getSelection(); sel.removeAllRanges(); sel.addRange(r); }
    toast("長按網址複製");
  }

  // ── 輿圖 ──
  // 輿圖升級設計（企劃者 10/15「A 優化版，先用這版試試」）。
  // 底圖（/api/map/base：只有紙、大區、山河、路的 SVG）一次載入只抓一次，疊層的 key 換了（劇情開放了新地點）才重抓；
  // 疊層（/api/map/state：誰佔著、勝算、分鐘……）打開輿圖、輪詢（MAP_STATE_EVERY）、做了動作之後重抓。
  // 地點、名字、小牌子、勢力的暈色、前線、你，都是這裡照疊層畫在底圖的 <g id="mk">（drawMarks）；倍率變了一成上下重畫一次，
  // 字與圓盤照倍率反算，螢幕上大小固定（設計第三節）。圖例拿掉了：濾鏡本身就是圖例（每顆前面一個色點）
  const MAP_SIDES = {
    guan: { name: "官軍", short: "官", color: "#3D5F8F", soft: "#9DB4D3", tint: "#DCE5F0" },
    huang: { name: "黃巾", short: "巾", color: "#B9821A", soft: "#E7C778", tint: "#F4E7C2" },
    haoqiang: { name: "豪強", short: "豪", color: "#4E7D59", soft: "#A5C6A6", tint: "#DFEBDD" },
  };
  const MAP_SIDE_ORDER = ["guan", "huang", "haoqiang"];
  const TONE_COLOR = { safe: "#3F7A3A", ok: "#8A6A1A", risk: "#A8322A", order: "#A8322A", bounty: "#C26A1E" };
  const FRONT_RED = "#A8322A";
  const MAP_INK = "#2B241B"; // 地圖上的字（紙色描邊）
  const MAP_HALO = "#F7F1E3";
  const NEUTRAL_INK = { ring: "#8F8B82", disc: "#ECE9E2", far: "#CFCBC2" }; // 領地爭奪：還沒人佔的中立地（甲：灰白圓盤＋虛線圈；待 joy 對色）
  const MAP_FAR = 0.62; // 倍率低於它換成「看大局」：只剩點、大區名、三色長條（設計第四節）
  const MAP_STATE_EVERY = 30000; // 輿圖開著時疊層多久重抓一次（毫秒）
  // ── 意境濾鏡（意境提示設計第四節）：照屬性上色（意境改名也不跑掉）。c 圓盤外框與小圓章、light 圓盤底、dark 深色主題上空心牌子的字
  const INSIGHT_INK = {
    快: { c: "#2B8A80", light: "#DDF0EC", dark: "#6CCBBE" }, 剛: { c: "#CF4F27", light: "#FBE3D8", dark: "#F08A63" },
    柔: { c: "#2C68B0", light: "#DCE8F6", dark: "#7FB0EA" }, 慢: { c: "#8A5A33", light: "#F0E3D6", dark: "#D2A57D" },
  };
  const INSIGHT_DOT = "conic-gradient(#2B8A80 0 25%, #CF4F27 0 50%, #2C68B0 0 75%, #8A5A33 0)"; // 濾鏡那一顆的色點：風火水山各一角
  const INSIGHT_ROW = "此地能悟"; // 抽屜那一行（補回輿圖升級漏掉的「這裡能悟」，設計第五節）
  const insightOn = (base, layers) => !!(base && base.insight_layer) && layers.has("insight"); // 開關關著時記著的 "insight" 不算
  function insightInk(base, id) {
    const kind = id && base && base.insight_kinds ? base.insight_kinds[id] : null;
    const ink = kind && INSIGHT_INK[kind.attribute];
    return ink ? { ...ink, name: kind.name } : null;
  }
  // 勢力與意境互斥（圓盤的顏色只給一樣）：開一顆，另一顆跟著關
  const MAP_EXCLUSIVE = { control: "insight", insight: "control" };
  function toggleLayer(layers, key) {
    if (layers.includes(key)) return layers.filter((x) => x !== key);
    return [...layers.filter((x) => x !== MAP_EXCLUSIVE[key]), key];
  }
  // 濾鏡（設計第一節）：鍵、名字、色點（勢力沒有點：它就是地圖的底色）。字待 joy 潤。意境不在這一排：六顆時 375 寬「劇情」超出畫面，
  // 挪到右上角那一欄版圖下面（FB-325，企劃者 10/17 從對比圖選丙；mapCtl）
  const MAP_CHIPS = [["control", "勢力", ""], ["order", "軍令", "#A8322A"], ["enemy", "敵情", "#8A6A1A"], ["route", "路程", "#7A6A55"], ["story", "劇情", "#6B4E8A"]];
  // 一方在輿圖上的樣子（輿圖第三版第 3 批；輿圖簡化設計 3.3：幾方、每一方的顏色從劇本讀）：照底圖的 world.sides（劇本的 FactionDef.ink）；
  // 舊的底圖沒有這一份時照上面那一張表（MAP_SIDES，只當退路）；都沒有的一方給一個中性的褐灰，名字照 id
  const SIDE_UNKNOWN = { color: "#8A7A62", soft: "#C9BFA9", tint: "#E6DFCF" };
  function sideInk(k) {
    const list = (S.mapBase && S.mapBase.world && S.mapBase.world.sides) || [];
    return list.find((x) => x.id === k) || MAP_SIDES[k] || { id: k, name: String(k), short: String(k).slice(0, 1), ...SIDE_UNKNOWN };
  }
  // 會出現在地圖上的幾方的先後：照劇本（底圖的 world.sides）；舊的底圖照 MAP_SIDE_ORDER
  function sideOrder(base) {
    const list = base && base.world && base.world.sides;
    return list ? list.map((x) => x.id) : MAP_SIDE_ORDER;
  }
  const sideName = (k) => (k ? sideInk(k).name : "無人控制");
  const f1 = (n) => Math.round(n * 10) / 10;
  const mapWeek = () => S.mapWeek || (S.mapState && S.mapState.now_week) || 1;

  // 那一週的控制方：現在照疊層；選了別的週照那一週的快照（還沒記到是空的）
  function controlAt(st, week) {
    if (!st) return {};
    if (!week || week === st.now_week) return Object.fromEntries(Object.entries(st.places).map(([id, p]) => [id, p.control]));
    const w = (st.weeks || []).find((x) => x.week === week);
    return (w && w.control) || {};
  }
  // 大區照「這一區最多地點歸誰」淡淡著色（設計第三節）；沒有控制方、或勢力關著，回空的（底圖原色）
  function regionTint(base, st, week, on) {
    if (!on || !st || !st.territory) return {};
    const ctrl = controlAt(st, week), count = {};
    for (const p of base.places) {
      const c = ctrl[p.id];
      if (c && p.region) (count[p.region] = count[p.region] || {})[c] = (count[p.region][c] || 0) + 1;
    }
    return Object.fromEntries(Object.entries(count).map(([rid, n]) => [rid, sideInk(Object.entries(n).sort((a, b) => b[1] - a[1])[0][0]).tint]));
  }
  // 一個地點名字底下的小牌子：一種濾鏡一個顏色（設計第三節）；你站的地方不掛
  function mapBadges(st, id, layers) {
    const p = st.places[id], out = [];
    if (!p || (id === st.here && !st.journey)) return out;
    if (layers.has("order") && p.order) out.push([`令 ${p.order}`, TONE_COLOR.order]);
    if (layers.has("order") && p.bounty) out.push([`賞 ${p.bounty}`, TONE_COLOR.bounty]);
    if (layers.has("enemy") && p.odds) out.push([p.odds.word, TONE_COLOR[p.odds.tone]]);
    if (layers.has("route") && p.minutes) out.push([`${p.minutes}分`, "#7A6A55"]);
    if (layers.has("story") && (p.goal || p.news)) out.push([p.goal ? "★主線" : "✦傳聞", "#6B4E8A"]);
    return out;
  }
  // 地圖上的記號（設計第三、四節）：o = { k: 1／倍率（字、圓盤、小牌子乘它，螢幕上大小固定）, far: 看大局, layers: 開著的濾鏡（Set）,
  // sel: 選了的地點, week: 看哪一週, tl: 正在看版圖變化 }。純函式：只讀傳進來的底圖與疊層
  function marksSvg(base, st, o) { return marksParts(base, st, o).join(""); }
  // 記號拆成兩段（FB-323）：第一個會跳的圈（class="pulse"，易手的地點、你）之前的畫在底圖的 SVG（#mk），從它起整段畫在疊在上面的那一張
  // （#mkt，pageMap 的 mk-top）。圈在底圖裡一跳，整張山水跟著重新整理（閒置五秒主執行緒忙一兩秒，手勢每幀貴兩三倍）。兩張同一個座標、
  // 同一個位移與倍率（applyMapView），照原本的先後疊。平常圈只有你的那一圈（最後畫），上面那一張只有那一圈、在路上的你、旗子。
  // 圈的跳法是整個圈放大、淡出（style.css 的 mk-pulse，企劃者 10/17 選丙）：合成器自己跑，線跟著變粗；跳的那一圈自成合成層，
  // 蓋在它上面的搜尋框、濾鏡、抽屜跟著被拉成合成層，字的邊緣有一點點不一樣（企劃者接受，試玩回饋 FB-323）
  function marksParts(base, st, o) {
    const k = o.k, far = o.far, hit = Math.round(2 * (hitRadius(1 / k) - 16)), ins = insightOn(base, o.layers), on = !!st.territory && o.layers.has("control") && !ins;
    const ctrl = controlAt(st, o.week), pos = Object.fromEntries(base.places.map((p) => [p.id, p]));
    const wk = (st.weeks || []).find((x) => x.week === o.week);
    const flash = new Set((o.tl || o.week !== st.now_week) && wk ? wk.changed.map((e) => e.id) : []); // 那一週易手的地點閃一圈
    let cut = -1; // 第一個會跳的圈在 out 的第幾格：從它起畫在上面那一張
    const pulse = (svg) => { if (cut < 0) cut = out.length; out.push(svg); };
    const out = [`<defs>${sideOrder(base).map((s) => `<radialGradient id="mk-halo-${s}"><stop offset="0" stop-color="${sideInk(s).soft}" stop-opacity=".7"/><stop offset=".55" stop-color="${sideInk(s).soft}" stop-opacity=".35"/><stop offset="1" stop-color="${sideInk(s).soft}" stop-opacity="0"/></radialGradient>`).join("")}</defs>`];
    if (on) {
      for (const p of base.places) if (ctrl[p.id]) out.push(`<circle cx="${p.x}" cy="${p.y}" r="80" fill="url(#mk-halo-${ctrl[p.id]})" pointer-events="none"/>`);
      for (const [a, b] of base.edges) { // 前線：兩頭歸不同的人的路畫紅色鋸齒（誰佔哪裡；能不能打看地點旁的 ⚔ 圓章）
        const ca = ctrl[a], cb = ctrl[b];
        if (!ca || !cb || ca === cb) continue;
        const A = pos[a], B = pos[b];
        out.push(`<path class="front" d="M${A.x} ${A.y}L${B.x} ${B.y}" stroke="${FRONT_RED}" stroke-width="${f1(3.6 * Math.max(1, k * 0.8))}" stroke-dasharray="${f1(2 * k)} ${f1(3 * k)}" fill="none" pointer-events="none"/>`);
      }
    }
    for (const p of base.places) {
      const c = on ? ctrl[p.id] : null, ink = ins ? insightInk(base, p.strong) : null; // 意境開著：圓盤是最濃那一種的顏色與字
      // 領地爭奪：還沒人佔的中立地畫灰白圓盤＋虛線圈（甲；乙「細金邊＋被佔之後外圈一圈淡色」等企劃者挑，草圖在
      // docs/superpowers/specs/2026-10-20-領地爭奪-草圖/中立地/；待 joy 對顏色）
      const nz = on && !c && !!st.places[p.id] && st.places[p.id].kind === "neutral";
      const col = ink ? ink.c : c ? sideInk(c).color : nz ? NEUTRAL_INK.ring : "#7A6A55";
      const r = (far ? 6 : 11) * k; // 圓盤半徑照螢幕固定（11px；看大局 6px），倍率變了地圖單位跟著反算（設計第三節，FB-260）
      if (flash.has(p.id)) pulse(`<circle class="pulse" cx="${p.x}" cy="${p.y}" r="16" fill="none" stroke="${FRONT_RED}" stroke-width="${f1(3 * k)}" pointer-events="none"/>`);
      if (o.sel === p.id) out.push(`<circle cx="${p.x}" cy="${p.y}" r="${f1(r + 9 * k)}" fill="none" stroke="${MAP_INK}" stroke-width="${f1(3 * k)}" pointer-events="none"/>`);
      // 點擊區：透明圓 r=16，透明外框寬 2×(R−16) 把它撐到半徑 R（R 照螢幕固定，hitRadius）。寬寫在每一個圓上、跟記號一起重畫，
      // 不寫成框上繼承的 CSS 變數：變數一改，整棵地圖約 1,500 個元素都要重算樣式（縮放每一下多 40ms 上下，Joy 2026-10-17）
      out.push(`<g data-loc="${esc(p.id)}" style="cursor:pointer"><circle cx="${p.x}" cy="${p.y}" r="16" fill="#000000" fill-opacity="0" stroke-width="${hit}"/>`);
      if (far) {
        const dash = nz ? ` stroke-dasharray="${f1(2 * k)} ${f1(1.6 * k)}"` : ""; // 看大局：中立地的小點也是虛線邊
        out.push(`<circle cx="${p.x}" cy="${p.y}" r="${f1(r)}" fill="${ink ? ink.c : c ? sideInk(c).color : nz ? NEUTRAL_INK.far : "#A99C84"}" stroke="${nz ? NEUTRAL_INK.ring : MAP_HALO}" stroke-width="${f1(1.5 * k)}"${dash}/></g>`);
        continue;
      }
      out.push(nz // 中立地：外圈換成虛線（「還沒人佔」），離圓盤遠一點、粗一點，375 寬也看得出是斷的
        ? `<circle cx="${p.x}" cy="${p.y}" r="${f1(r + 4 * k)}" fill="none" stroke="${col}" stroke-width="${f1(1.6 * k)}" stroke-dasharray="${f1(3.2 * k)} ${f1(2.4 * k)}"/>`
        : `<circle cx="${p.x}" cy="${p.y}" r="${f1(r + 2.5 * k)}" fill="none" stroke="${col}" stroke-width="${f1(1.2 * k)}" opacity=".7"/>`);
      out.push(`<circle cx="${p.x}" cy="${p.y}" r="${f1(r)}" fill="${ink ? ink.light : nz ? NEUTRAL_INK.disc : "#FBF6EA"}" stroke="${col}" stroke-width="${f1(2.6 * k)}"/>`);
      out.push(`<text x="${p.x}" y="${f1(p.y + r * 0.36)}" text-anchor="middle" font-size="${f1(r * 1.02)}" fill="${col}" font-weight="700" style="font-family:serif">${esc(ink ? ink.name : p.glyph)}</text></g>`);
      if (ink) (p.insights || []).filter((id) => id !== p.strong).forEach((id, i) => { // 同一處還悟得到的別種：圓盤右下沿著邊掛小圓章
        const other = insightInk(base, id);
        if (!other) return;
        const a = ((40 + i * 45) * Math.PI) / 180, sx = f1(p.x + (r + 2.5 * k) * Math.cos(a)), sy = f1(p.y + (r + 2.5 * k) * Math.sin(a));
        out.push(`<g class="ins-seal" pointer-events="none"><circle cx="${sx}" cy="${sy}" r="${f1(7.5 * k)}" fill="${other.c}" stroke="${MAP_HALO}" stroke-width="${f1(1.3 * k)}"/><text x="${sx}" y="${f1(sy + 3.4 * k)}" font-size="${f1(9.5 * k)}" font-weight="700" text-anchor="middle" fill="#FFFFFF" style="font-family:serif">${esc(other.name)}</text></g>`);
      });
      // ⚔：你此刻能出陣攻的地方（疊層的 armed，跟舊輿圖同一個判斷 FB-251），圓盤左上一個紅色小圓章；散人、豪強一處都沒有（企劃者 10/15 從對比圖選乙）
      if (st.places[p.id] && st.places[p.id].armed) {
        const sx = f1(p.x - r - 4 * k), sy = f1(p.y - r - 2 * k);
        out.push(`<g class="armed" pointer-events="none"><circle cx="${sx}" cy="${sy}" r="${f1(8.5 * k)}" fill="${FRONT_RED}" stroke="${MAP_HALO}" stroke-width="${f1(1.2 * k)}"/><text x="${sx}" y="${f1(p.y - r + 1.6 * k)}" font-size="${f1(10.5 * k)}" text-anchor="middle" fill="#FFFFFF">⚔</text></g>`);
      }
      const label = p.name + (p.id === st.here && !st.journey ? "（你）" : "");
      out.push(`<text x="${f1(p.x + r + 5 * k)}" y="${f1(p.y + 4.5 * k)}" font-size="${f1(13 * k)}" font-weight="${p.big ? 700 : 500}" fill="${MAP_INK}" stroke="${MAP_HALO}" stroke-width="${f1(3.4 * k)}" paint-order="stroke" pointer-events="none" style="font-family:serif">${esc(label)}</text>`);
      let bx = p.x + r + 5 * k;
      for (const [t, color] of mapBadges(st, p.id, o.layers)) {
        const wd = (t.length * 10.5 + 10) * k;
        out.push(`<rect x="${f1(bx - 2 * k)}" y="${f1(p.y + 9 * k)}" width="${f1(wd)}" height="${f1(15 * k)}" rx="${f1(7.5 * k)}" fill="${color}" pointer-events="none"/><text x="${f1(bx + 3 * k)}" y="${f1(p.y + 20 * k)}" font-size="${f1(10.5 * k)}" fill="#FFFFFF" pointer-events="none">${esc(t)}</text>`);
        bx += wd + 3 * k;
      }
    }
    if (far) for (const r of base.regions) { // 看大局：大區名、三色長條、各方幾處（畫在小點之後，字不被點蓋掉，FB-261）
      const n = {};
      if (on) for (const p of base.places) if (p.region === r.id && ctrl[p.id]) n[ctrl[p.id]] = (n[ctrl[p.id]] || 0) + 1;
      const total = Object.values(n).reduce((a, b) => a + b, 0);
      out.push(`<text x="${r.cx}" y="${f1(r.cy - 14 * k)}" text-anchor="middle" font-size="${f1(23 * k)}" font-weight="700" fill="${MAP_INK}" stroke="${MAP_HALO}" stroke-width="${f1(5 * k)}" paint-order="stroke" pointer-events="none" style="font-family:serif">${esc(r.name)}</text>`);
      if (total) {
        let x = r.cx - 40 * k;
        for (const sd of sideOrder(base)) {
          if (!n[sd]) continue;
          const wd = (80 * k * n[sd]) / total;
          out.push(`<rect x="${f1(x)}" y="${f1(r.cy - 4 * k)}" width="${f1(wd)}" height="${f1(9 * k)}" fill="${sideInk(sd).color}" pointer-events="none"/>`);
          x += wd;
        }
        out.push(`<text x="${r.cx}" y="${f1(r.cy + 20 * k)}" text-anchor="middle" font-size="${f1(12 * k)}" fill="#3A332A" stroke="${MAP_HALO}" stroke-width="${f1(3 * k)}" paint-order="stroke" pointer-events="none">${sideOrder(base).filter((sd) => n[sd]).map((sd) => `${sideInk(sd).short} ${n[sd]}`).join("・")}</text>`);
      }
    }
    // 你：在路上畫在路上（circle.tx-you），不然在所在地；插一面紅旗，外面一圈慢慢擴散
    const j = st.journey, h = pos[st.here];
    const hx = j ? j.x : h && h.x, hy = j ? j.y : h && h.y;
    if (hx !== undefined) {
      pulse(`<circle class="pulse" cx="${hx}" cy="${hy}" r="16" fill="none" stroke="${FRONT_RED}" stroke-width="${f1(2.5 * k)}" pointer-events="none"/>`);
      if (j) out.push(`<circle class="tx-you" cx="${hx}" cy="${hy}" r="${f1(7 * k)}" fill="#D85A30" stroke="#FFFFFF" stroke-width="${f1(2 * k)}" pointer-events="none"/>`);
      out.push(`<path d="M${f1(hx + 4 * k)} ${f1(hy - 12 * k)}V${f1(hy - 40 * k)}L${f1(hx + 22 * k)} ${f1(hy - 33 * k)}L${f1(hx + 4 * k)} ${f1(hy - 26 * k)}" fill="${FRONT_RED}" stroke="#7A1F18" stroke-width="${f1(1.5 * k)}" pointer-events="none"/>`);
    }
    return cut < 0 ? [out.join(""), ""] : [out.slice(0, cut).join(""), out.slice(cut).join("")];
  }
  // 各方佔幾處；跟開季那一刻比（疊層的 start，FB-264）；中途上線的季沒有開季的樣子，比第一筆記到的那一週、照實寫第幾週，
  // 看的就是那一週時不比。寫哪幾方照疊層的 sides（第一季豪強分屬兩軍的季只有官軍、黃巾；沒有這個鍵照 MAP_SIDE_ORDER）
  function tally(base, ctrl) {
    const n = Object.fromEntries(sideOrder(base).map((sd) => [sd, 0]));
    for (const p of base.places) if (ctrl[p.id]) n[ctrl[p.id]] = (n[ctrl[p.id]] || 0) + 1;
    return n;
  }
  function tallyFrom(base, st, week) {
    if (st.start) return { label: "比開季", n: tally(base, st.start) };
    const first = (st.weeks || []).find((x) => x.control);
    return first && first.week < week ? { label: `比第 ${first.week} 週`, n: tally(base, first.control) } : null;
  }
  const signed = (d) => (d > 0 ? `+${d}` : d < 0 ? `${d}` : "±0");
  // 地圖上方浮的那一條「天下」：看大局或版圖變化時，各方此刻佔幾處、比第一筆記到的那一週多幾處少幾處（設計第四節）
  function hudHtml(base, st, week) {
    const now = tally(base, controlAt(st, week)), from = tallyFrom(base, st, week);
    return `<b>天下</b>${(st.sides || sideOrder(base)).map((sd) => `<span style="color:${sideInk(sd).color}">${esc(sideInk(sd).short)} <b>${now[sd] || 0}</b>${from ? `<small>${signed((now[sd] || 0) - (from.n[sd] || 0))}</small>` : ""}</span>`).join("")}${from ? `<small>${from.label}</small>` : ""}`;
  }
  function chipsHtml() {
    const on = new Set(S.mapLayers);
    return MAP_CHIPS.map(([key, name, dot]) => `<button type="button" class="${on.has(key) ? "on" : ""}" data-act="map-layer" data-layer="${key}" aria-pressed="${on.has(key)}">${dot ? `<i style="background:${dot}"></i>` : ""}${name}</button>`).join("");
  }
  // 右上角那一欄的意境鈕（FB-325）：意境提示開著才有；開著時跟濾鏡一樣墨底
  function insightButton() {
    if (!(S.mapBase && S.mapBase.insight_layer)) return "";
    const on = S.mapLayers.includes("insight");
    return `<button type="button" class="ins${on ? " on" : ""}" data-act="map-layer" data-layer="insight" aria-pressed="${on}" aria-label="意境" title="意境"><i style="background:${INSIGHT_DOT}"></i><small>意境</small></button>`;
  }
  // 濾鏡開關換了（點了一顆、版圖變化把勢力打開）：濾鏡那一排與右上角的意境鈕一起換樣子（勢力與意境互斥）
  function syncLayerButtons() {
    const row = document.querySelector(".map-chips");
    if (row) row.innerHTML = chipsHtml();
    const ins = document.querySelector('.map-ctl [data-layer="insight"]');
    if (ins) {
      const on = S.mapLayers.includes("insight");
      ins.className = `ins${on ? " on" : ""}`;
      ins.setAttribute("aria-pressed", String(on));
    }
  }
  // 地圖右上角的按鈕（給不會手勢的人，像一般地圖 App）：我在哪、放大、縮小，第四顆是版圖變化
  // （企劃者 10/15 從對比圖選丙：375 寬時濾鏡一排放不下它，挪到這裡；濾鏡那一排只剩五顆）
  function mapCtl() {
    const tl = S.mapMode === "timeline";
    return `<div class="map-ctl">
    <button type="button" class="me" data-act="map-home" aria-label="我在哪" title="我在哪"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="6.5"/><path d="M12 2v4M12 18v4M2 12h4M18 12h4"/></svg></button>
    <button type="button" data-act="map-zoom" data-step="in" aria-label="放大" title="放大"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M12 5v14"/></svg></button>
    <button type="button" data-act="map-zoom" data-step="out" aria-label="縮小" title="縮小"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14"/></svg></button>
    <button type="button" class="tl${tl ? " on" : ""}" data-act="map-timeline" aria-label="版圖變化" aria-pressed="${tl}" title="版圖變化">⏱<small>版圖</small></button>
    ${insightButton()}
  </div>`;
  }
  // 整頁一層（設計第一節）：夾在頂上的狀態列與底部分頁列之間；上面是找地點與濾鏡，右上角三顆鈕，底下是抽屜（寬 900 以上是右欄）。
  // data-key 是底圖的 key：輿圖那一層常駐在 #map-host 時（showMapHost），同一張底圖只換外圍、底圖那一塊原地留著（FB-324）
  function pageMap() {
    if (!S.mapBase || !S.mapState) return '<p class="muted">展開輿圖…</p>';
    const svg = S.mapBase.svg.replace(/<\/svg>\s*$/, '<g id="mk"></g></svg>');
    // 疊在底圖上面的那一張（FB-323，marksParts）：跟底圖同一個根（viewBox、大小、字型），位移與倍率由 applyMapView 一起套
    const top = `<svg${(S.mapBase.svg.match(/^<svg\b([^>]*)>/) || ["", ""])[1]} class="mk-top" id="mkt"></svg>`;
    return `<div class="${mapxClass()}" id="mapx" data-key="${esc(S.mapBase.key)}">
      <div class="map-wrap" id="map"><div class="tx-world-map">${svg}${top}</div></div>${mapChrome()}
    </div>`;
  }
  function mapxClass() { return `mapx${S.mapLayer === "world" ? " world" : ""}${S.mapMode === "timeline" ? " tl-mode" : ""}`; }
  // 地圖框以外的那幾樣：天下圖上面那一排（天下・找地點・版圖）；區圖的找地點（左邊「‹ 天下」）與濾鏡、右上角的鈕、「天下」那一條；
  // 「正在看第幾週」、抽屜。兩層的鈕都畫，照 .mapx.world 藏另一層的（style.css）
  function mapChrome() {
    const seeing = S.mapMode === "timeline" && S.mapWeek && S.mapWeek !== S.mapState.now_week;
    const banner = `<div class="map-banner" id="map-banner"${seeing ? "" : " hidden"}>${seeing ? `正在看第 ${S.mapWeek} 週` : ""}</div>`;
    const tl = S.mapMode === "timeline";
    const wtop = `<div class="w-top"><button type="button" class="w-here" data-act="map-world" aria-current="page">${WORLD_WORD}</button><button type="button" class="map-search" data-act="map-search">🔍 找地點、找人物</button><button type="button" class="w-tl${tl ? " on" : ""}" data-act="map-timeline" aria-pressed="${tl}">⏱ 版圖</button></div>`;
    return `
      ${wtop}<div class="map-top"><div class="m-srow"><button type="button" class="w-back" data-act="map-world">‹ ${WORLD_WORD}</button><button type="button" class="map-search" data-act="map-search">🔍 找地點、找人物</button></div><div class="map-chips" role="group" aria-label="濾鏡">${chipsHtml()}</div></div>
      ${mapCtl()}<div class="map-hud" id="map-hud" hidden></div>${banner}
      <section class="mdrawer${S.mapMode === "overview" && drawerNow() === "min" && !deskMap() ? " min" : ""}" id="mdrawer" aria-label="輿圖抽屜"><div class="mgrab" id="mgrab" role="button" aria-label="拉高拉低"><i></i></div><div class="mbody" id="mbody">${drawerHtml()}</div></section>`;
  }
  // ── 輿圖那一層常駐（FB-324）：切到別的分頁、整頁重畫（render 換掉 #app 的 innerHTML）時，地圖不拆掉，只在 #map-host 藏起來
  // （visibility: hidden：樣式、排版、點陣化都留著）。以前每次回到輿圖都把 114 KB 的底圖字串塞回去、重新解析、重算樣式、重新排版、
  // 重畫（暖開那一下約 90 ms 的長任務）。#map-host 在 #app 外面、body 底下（點擊照舊由 document 收）；.mapx 本來就是 position: fixed
  // 的整頁一層，搬出 #page 位置一樣。沒有 #map-host（node 的假瀏覽器）時照舊畫在 #page
  function mapHost() {
    let host = document.getElementById("map-host");
    if (!host && document.body && document.body.insertAdjacentHTML) {
      document.body.insertAdjacentHTML("beforeend", '<div id="map-host" class="away"></div>');
      host = document.getElementById("map-host");
    }
    return host;
  }
  // 輿圖畫在常駐的那一層：同一張底圖（data-key 一樣）就只換外圍與 .mapx 的 class，底圖那一塊（底圖、記號、上面那一張）原地不動；
  // 底圖換了（劇情開了新地點）、第一次，整層重畫。畫不了（還沒有底圖、沒有 #map-host）回 false，照舊畫在 #page
  function showMapHost() {
    if (!S.mapBase || !S.mapState) return false;
    const host = mapHost();
    if (!host) return false;
    const box = document.getElementById("mapx");
    if (box && box.parentNode === host && box.dataset.key === String(S.mapBase.key) && box.querySelector(".tx-world-map")) {
      box.className = mapxClass();
      for (const el of [...box.children]) if (el.id !== "map") el.remove();
      box.insertAdjacentHTML("beforeend", mapChrome());
    } else host.innerHTML = pageMap();
    host.classList.remove("away");
    return true;
  }
  // 離開輿圖：藏起來（不拆）；登出、換帳號：整層清掉（上一個人的地圖不留）
  function hideMapHost(clear = false) {
    const host = document.getElementById("map-host");
    if (!host) return;
    host.classList.add("away");
    if (clear) host.innerHTML = "";
  }
  // 登出、登入（換帳號不重新整理、登入失效之後重新登入）：上一個人的輿圖全部清回開頭——底圖、疊層、視圖、選的地點、濾鏡、抽屜、
  // 版圖變化、找地點的字——常駐那一層整個清掉（FB-329：不清的話換人登入之後輿圖照舊畫上一個人的疊層、位置與勝算）
  function forgetMap() {
    stopPlay();
    Object.assign(S, {
      mapBase: null, mapState: null, mapStateAt: 0, mapSel: null, mapMode: "overview", mapLayers: ["control", "order"], mapDrawer: "home",
      mapWeek: null, mapQuery: "", mapFocus: null, mapLayer: "world", worldView: null, marksS: 0, mapView: null,
    });
    hideMapHost(true);
  }
  // ── 輿圖的抽屜（設計第五節）：總覽（今天去哪裡出陣、戰線、本週大事）、一個地點、找地點、版圖變化 ──
  const SORTIE_WORD = { attack: "攻", hold: "守", stir: "攪局" }; // 出陣是哪一種（sortie.mode），待 joy 潤
  const ODDS_TONE_WEB = { 穩勝: "safe", 有把握: "safe", 五五波: "ok", 難分勝負: "ok", 凶險: "risk", 必敗: "risk", 操練: "safe" };
  const placeOf = (base, id) => base.places.find((p) => p.id === id);
  const ctrlSeal = (c) => (c ? `<span class="m-seal" style="background:${sideInk(c).color}">${esc(sideInk(c).short)}</span>` : '<span class="m-seal none">—</span>');
  function drawerHtml() {
    const base = S.mapBase, st = S.mapState;
    if (S.mapMode === "search") return searchHtml(base, st, S.mapQuery);
    if (S.mapMode === "timeline") return timelineHtml(base, st, mapWeek());
    if (S.mapLayer === "world" && base.world) return worldDrawerHtml(base, st);
    if (S.mapMode === "place" && S.mapSel && st.places[S.mapSel]) return placeHtml(base, st, S.mapSel);
    if (drawerNow() === "min" && !deskMap()) return miniHtml(base, st);
    return overviewHtml(base, st);
  }
  // 抽屜第一行：在路上寫往哪裡、還有幾分鐘、喊停（喊停就是江湖頁那一顆，選單上有才畫）；有事擋著路時寫是哪一則、給「回江湖」
  function journeyHtml(st) {
    const j = st.journey, block = st.travel_block;
    const halt = ((S.main && S.main.options) || []).some((o) => o.id === "act:halt" && o.enabled !== false);
    const road = j ? `<div class="m-journey"><span>往 <b>${esc(j.to_name)}</b>・還有 ${Number(j.minutes)} 分鐘${j.next_name ? `・下一站${esc(j.next_name)}` : ""}</span>${halt ? '<button type="button" data-act="choose" data-id="act:halt">喊停</button>' : ""}</div>` : "";
    const held = block && block.to_jianghu ? `<div class="m-journey"><span>${esc(block.reason)}</span><button type="button" data-act="tab" data-tab="jianghu">回江湖</button></div>` : "";
    return road + held;
  }
  // 一根戰線（拔河）：左官軍、右黃巾，斜線是亂局（35～65），黑線是此刻的戰況；繩上的可易手地點是小方印（照誰佔著上色，
  // 擺在它易手的門檻上）；繩名旁寫比上一週往哪邊推了多少
  // 繩的兩頭是誰照疊層的 low／high（劇本的 goals；輿圖第三版第 3 批起不寫死官軍、黃巾），舊疊層沒有照官軍、黃巾
  const ropeEnds = (r) => [sideInk(r.low || "guan"), sideInk(r.high || "huang")];
  function ropeHtml(r) {
    const [lo, hi] = ropeEnds(r);
    const trend = r.delta > 0 ? `<small style="color:${hi.color}">▶ ${esc(hi.name)}推進 ${r.delta}</small>`
      : r.delta < 0 ? `<small style="color:${lo.color}">◀ ${esc(lo.name)}推進 ${-r.delta}</small>` : "<small>持平</small>";
    const beads = r.beads.map((b) => `<span class="bead" style="left:${b.threshold}%;background:${b.control ? sideInk(b.control).color : "#A2967F"}"></span>`).join("");
    return `<div class="m-rope"><div class="rl"><span>${esc(lo.name)}</span><b>${esc(r.name)} ${trend}</b><span>${esc(hi.name)}</span></div><div class="bar" style="background:linear-gradient(90deg, ${lo.tint}, ${hi.tint})"><span class="chaos"></span>${beads}<span class="knot" style="left:${Number(r.value)}%"></span></div></div>`;
  }
  function overviewHtml(base, st) {
    const here = placeOf(base, st.here), hc = st.places[st.here] && st.places[st.here].control;
    // 在路上：第一行（journeyHtml）已經寫了往哪裡，這裡不再寫「你在」
    const where = st.journey ? "" : `${esc(here ? here.name : "")}${hc ? `（${sideName(hc)}的地盤）` : ""}`;
    const goes = st.suggest.length && st.sorties_left !== null
      ? `<div class="m-head2"><b>今天去哪裡出陣</b><small>今日還能 ${Number(st.sorties_left)} 次${where ? `・你在 ${where}` : ""}</small></div>` +
        st.suggest.map((g, i) => `<div class="m-go${g.lose ? " lose" : ""}" data-act="map-pick" data-id="${esc(g.id)}" role="button"><span class="n">${i + 1}</span><span class="t"><b>${esc(placeOf(base, g.id).name)}</b>　出陣・${SORTIE_WORD[g.sortie] || ""}
          <span class="why">${g.why.map(([t, tone]) => `<span style="background:${TONE_COLOR[tone] || "#8A7A62"}">${esc(t)}</span>`).join("")}</span></span><span class="m">${g.minutes ? `${Number(g.minutes)} 分 ›` : "這裡 ›"}</span></div>`).join("")
      : where ? `<div class="m-head2"><b>你在 ${where}</b></div>` : "";
    const ropes = st.ropes.length ? `<div class="m-sec"><h4>${st.season_one ? "三條戰線" : "大勢"}</h4>${st.ropes.map(ropeHtml).join("")}${st.geju !== null ? `<div class="m-sub">豪強割據 ${Number(st.geju)}</div>` : ""}</div>` : "";
    const events = st.events.length ? `<div class="m-sec"><h4>本週大事</h4>${st.events.map((t) => `<div class="m-evt">📜 ${esc(t)}</div>`).join("")}</div>` : "";
    return journeyHtml(st) + goes + ropes + events;
  }
  // 抽屜「此地能悟」（意境提示設計第五節）：一種一顆牌子，最濃的實心、寫「最濃」；開關關著沒有最濃，全部空心
  function insightRow(base, b) {
    const pills = (b.insights || []).map((id) => {
      const ink = insightInk(base, id);
      if (!ink) return "";
      const strong = id === b.strong;
      return `<span class="ig${strong ? " strong" : ""}" style="--c:${ink.c};--d:${ink.dark}"><b>${esc(ink.name)}</b>${strong ? "<em>最濃</em>" : ""}</span>`;
    }).join("");
    return pills ? `<div class="m-ins"><small>${INSIGHT_ROW}</small>${pills}</div>` : "";
  }
  // 地利（武學隨地理環境計畫第六節）：拉高才看的細節裡、「站在這裡的」底下一段；字是伺服器照最濃的意境寫好的
  // （mapdata.base 的 terrain_arts，terrain.place_line），開關關著、這一處沒有最濃的是空字串、整段不畫。「地利」兩個字待 joy 潤。
  // 那一句 26 字，375 寬斷成「…施展不／開。」、360 與桌面「…施展／不開。」（FB-470）：照掮客那一句（sayHtml）切在「：」「，」
  // 後面包成不折行的小段，字一個不改
  function terrainArtsRow(b) {
    return b.terrain_arts ? `<div class="m-sec"><h4>地利</h4>${sayHtml(b.terrain_arts)}</div>` : "";
  }
  // 點一個地點（設計第五節）：第一行（印、名字、危險度）、三格（誰佔著、打得過嗎、多遠）、動作一排、拉高才看的細節
  function placeHtml(base, st, id) {
    const b = placeOf(base, id), p = st.places[id], here = id === st.here && !st.journey;
    const odds = p.odds ? `<b style="color:${TONE_COLOR[p.odds.tone]}">${esc(p.odds.word)}</b>` : "<b>沒有對手</b>";
    const block = st.travel_block;
    let acts;
    if (here) { // 就在這裡：出陣、探索都回江湖頁按（江湖頁照舊處理接下來的事）
      // 出陣・攻那一顆也寫勝算：要按之前最想看的就是它（FB-262）
      const risk = p.sortie === "attack" && p.odds ? `${esc(p.odds.word)}・` : "";
      const sortie = p.sortie && st.sorties_left !== null ? `<button type="button" class="main" data-act="map-jianghu" data-key="sortie">出陣・${SORTIE_WORD[p.sortie] || ""}<small>${risk}今日還能 ${Number(st.sorties_left)} 次</small></button>` : "";
      acts = `${sortie}<button type="button"${sortie ? "" : ' class="main"'} data-act="map-jianghu" data-key="explore">探索<small>回江湖頁挑一種</small></button>`;
    } else if (block) {
      acts = `<button type="button" disabled>${esc(block.reason)}</button>${block.to_jianghu ? '<button type="button" class="main" data-act="tab" data-tab="jianghu">回江湖</button>' : ""}`;
    } else if (p.minutes === null) {
      acts = '<button type="button" disabled>走不到</button>';
    } else {
      acts = `<button type="button" class="main" data-act="map-travel" data-mode="walk">步行 ${Number(p.minutes)} 分<small>沿路可以做小事</small></button><button type="button" data-act="map-travel" data-mode="dash"${st.stamina < p.stamina ? " disabled" : ""}>疾行<small>${st.stamina < p.stamina ? `體力不足，要 ${Number(p.stamina)}` : `立刻到・體力 ${Number(p.stamina)}`}</small></button>`;
    }
    const strip = p.kind === "line" || p.kind === "fixed" || p.kind === "neutral" ? `<div class="m-strip">${Array.from({ length: st.weeks_total }, (_, i) => {
      const w = i + 1, row = (st.weeks || []).find((x) => x.week === w), c = row && row.control ? row.control[id] : null;
      return `<span class="${w > st.now_week ? "future" : ""}${w === st.now_week ? " now" : ""}" style="background:${c ? sideInk(c).color : "#CDBF9F"}"></span>`;
    }).join("")}</div>` : "";
    const flips = p.flips.map((f) => `第 ${Number(f.week)} 週 ${sideName(f.from)}→${sideName(f.to)}`).join("；");
    const kind = p.kind === "base" ? "大本營" : p.kind === "fixed" ? "照大事易手" : p.kind === "neutral" ? "中立地" : p.kind ? "可易手" : ""; // 中立地：領地爭奪（待 joy 潤）
    const tone = (word) => TONE_COLOR[ODDS_TONE_WEB[word] || "ok"];
    return `<div class="m-h1">${ctrlSeal(p.control)}<span class="nm">${esc(b.name)}</span><span class="meta">${insightOn(base, new Set(S.mapLayers)) && b.terrain ? `<span class="terrain">${esc(b.terrain)}</span>` : ""}${"★".repeat(Number(p.danger) || 0)}</span><button type="button" class="m-x" data-act="map-back" aria-label="收起">✕</button></div>
      <div class="m-three"><div><small>誰佔著</small><b style="color:${p.control ? sideInk(p.control).color : "inherit"}">${p.control ? esc(sideInk(p.control).name) : "無人"}</b>${kind ? `<small>${kind}</small>` : ""}</div>
        <div><small>打得過嗎</small>${odds}${p.sortie ? `<small>出陣是${SORTIE_WORD[p.sortie] || ""}</small>` : ""}</div>
        <div><small>多遠</small><b>${here ? "這裡" : p.minutes === null ? "—" : `${Number(p.minutes)} 分`}</b>${here || p.stamina === null ? "" : `<small>疾行 體力 ${Number(p.stamina)}</small>`}</div></div>
      ${insightRow(base, b)}<div class="m-acts">${acts}</div>
      ${p.order || p.bounty ? `<div class="m-sec"><h4>軍令與懸賞</h4>${p.order ? `軍令「${esc(p.order)}」在這裡記功` : ""}${p.order && p.bounty ? "；" : ""}${p.bounty ? `懸賞「${esc(p.bounty)}」在這裡交差` : ""}</div>` : ""}
      ${st.territory ? `<div class="m-sec"><h4>地盤</h4>${p.control ? `${sideName(p.control)}${p.control === "haoqiang" ? "佔據" : "控制"}。${esc(p.price)}` : p.kind === "neutral" ? `中立地，還沒有人佔。${esc(p.price)}` : "不在戰線上，沒有控制方。"}${strip}${flips ? `<div class="m-sub">易手：${flips}</div>` : ""}</div>` : ""}
      <div class="m-sec"><h4>站在這裡的</h4>${p.squads.length ? p.squads.map((q) => `${esc(q.name)} <span style="color:${tone(q.odds)}">${esc(q.odds)}</span>`).join("、") : "沒有人在這裡滋事"}${p.people.length ? `<div class="m-sub">人物：${p.people.map(esc).join("、")}</div>` : ""}</div>
      ${terrainArtsRow(b)}
      ${p.services.length ? `<div class="m-sec"><h4>此地</h4>${p.services.map(esc).join("・")}</div>` : ""}
      <div class="m-sec"><h4>劇情</h4>${p.goal ? "★ 這一幕主線的目標　" : ""}${p.news ? "✦ 最近有大事與傳聞" : p.goal ? "" : "最近沒有大事"}</div>`;
  }
  // 找地點、找人物（設計第五節）：照大區分組，組裡近的在前；打地名、大區名、人物名都找得到。打字時只換結果那一塊（searchResults）
  function searchResults(base, st, q) {
    const want = (q || "").trim();
    const regions = Object.fromEntries(base.regions.map((r) => [r.id, r.name]));
    const hit = (b) => !want || b.name.includes(want) || (regions[b.region] || "").includes(want) || st.places[b.id].people.some((n) => n.includes(want));
    const html = base.regions.map((r) => {
      const items = base.places.filter((b) => b.region === r.id && hit(b)).sort((a, z) => (st.places[a.id].minutes || 0) - (st.places[z.id].minutes || 0));
      return items.length ? `<div class="m-grp">${esc(r.name)}</div>` + items.map((b) => {
        const p = st.places[b.id];
        const far = b.id === st.here && !st.journey ? "你在這裡" : p.minutes === null ? "" : `${Number(p.minutes)} 分`;
        return `<div class="m-item" data-act="map-pick" data-id="${esc(b.id)}" role="button">${ctrlSeal(p.control)}<span class="nm">${esc(b.name)}${p.people.length ? ` <small>${p.people.map(esc).join("、")}</small>` : ""}</span><span class="mn">${far}</span></div>`;
      }).join("") : "";
    }).join("");
    return html || '<div class="m-sub">找不到。</div>';
  }
  function searchHtml(base, st, q) {
    return `<div class="m-search"><input class="m-q" id="map-q" type="search" placeholder="地名、人物、大區…" value="${esc(q || "")}" autocomplete="off" aria-label="找地點、找人物"><button type="button" class="m-x" data-act="map-back" aria-label="收起">✕</button></div>
      <div class="m-results" id="map-results">${searchResults(base, st, q)}</div>`;
  }
  // ── 天下怎麼變（設計第六節）：上面一張曲線（三條戰線、割據、大事 📜、你在看的那一週），三方各佔幾處、比開季多少，
  // 年表（B 的：一列一個可易手的地點、一格一週，顏色是那一週誰佔著、白點是那一週易手），那一週的大事與易手。
  // 地圖同時照那一週畫：輿圖第三版第 3 批起在天下圖上播（worldParts 的 week；mapTimeline 換到天下圖、地圖框縮到抽屜上面）
  const ROPE_INK = ["#5A3E28", "#2E5E6B", "#7A2E52"]; // 曲線上三條戰線各自的顏色與虛線
  const ROPE_DASH = ["", "5 3", "1.5 3"];
  const GX0 = 30, GW = 300, GY0 = 12, GH = 92; // 曲線的左邊、寬、上邊、高（viewBox 單位）
  const PLAY_MS = 900; // 播放：一週停多久
  function graphSvg(st, week) {
    const total = Math.max(2, st.weeks_total);
    const gx = (w) => GX0 + ((w - 1) * GW) / (total - 1), gy = (v) => GY0 + ((100 - v) * GH) / 100;
    const out = [
      `<rect x="${GX0}" y="${gy(65)}" width="${GW}" height="${f1(gy(35) - gy(65))}" fill="#A8322A" opacity=".06"/>`,
      `<rect x="${f1(gx(st.now_week))}" y="${GY0}" width="${f1(gx(total) - gx(st.now_week))}" height="${GH}" fill="#EDE4CF" opacity=".7"/>`,
    ];
    const [lo, hi] = st.ropes.length ? ropeEnds(st.ropes[0]) : [sideInk("guan"), sideInk("huang")]; // 上面寫往 100 推的那一方、下面寫往 0 推的
    out.push(`<text x="2" y="${GY0 + 8}" font-size="10" fill="${hi.color}">${esc(hi.name)}</text><text x="2" y="${GY0 + GH}" font-size="10" fill="${lo.color}">${esc(lo.name)}</text>`);
    const known = (st.weeks || []).filter((x) => x.control);
    st.ropes.forEach((r, i) => {
      const pts = known.map((x) => [x.week, x.ropes[r.id]]).filter(([, v]) => v !== null && v !== undefined);
      if (!pts.length) return;
      out.push(`<polyline points="${pts.map(([w, v]) => `${f1(gx(w))},${f1(gy(v))}`).join(" ")}" fill="none" stroke="${ROPE_INK[i % 3]}" stroke-width="2.2" stroke-dasharray="${ROPE_DASH[i % 3]}"/>`);
      const [lw, lv] = pts[pts.length - 1];
      out.push(`<text x="${f1(gx(lw) + 4)}" y="${f1(gy(lv) + 3)}" font-size="10" fill="${ROPE_INK[i % 3]}">${esc(r.name.slice(0, 2))}</text>`);
    });
    const geju = known.filter((x) => x.geju !== null && x.geju !== undefined);
    if (geju.length) out.push(`<polyline points="${geju.map((x) => `${f1(gx(x.week))},${f1(gy(x.geju))}`).join(" ")}" fill="none" stroke="${sideInk(st.geju_side || "haoqiang").color}" stroke-width="1.6" opacity=".8"/>`);
    for (const x of st.weeks || []) if (x.events.length) out.push(`<text x="${f1(gx(x.week))}" y="${GY0 - 1}" font-size="9" text-anchor="middle">📜</text>`);
    out.push(`<line x1="${f1(gx(week))}" y1="${GY0}" x2="${f1(gx(week))}" y2="${GY0 + GH}" stroke="#A8322A" stroke-width="2"/>`);
    for (let w = 1; w <= st.weeks_total; w++) out.push(`<text x="${f1(gx(w))}" y="${GY0 + GH + 11}" font-size="9.5" text-anchor="middle" fill="${w === week ? "#A8322A" : w > st.now_week ? "#C2B699" : "#8A7A62"}">${w}</text>`);
    return `<svg class="m-graph" data-act="map-graph" viewBox="0 0 ${GX0 + GW + 34} ${GY0 + GH + 14}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="三條戰線這一季的走勢">${out.join("")}</svg>`;
  }
  // 年表：一列一個可易手的地點、一格一週；還沒到打斜線、還沒記到是空格（中途上線、舊存檔）
  function chartHtml(base, st, week) {
    const total = st.weeks_total, byWeek = Object.fromEntries((st.weeks || []).map((x) => [x.week, x]));
    const head = "<span></span>" + Array.from({ length: total }, (_, i) => {
      const w = i + 1;
      return `<span class="wk${w === week ? " on" : ""}${w > st.now_week ? " future" : ""}"${w <= st.now_week ? ` data-act="map-week" data-week="${w}"` : ""}>${w}</span>`;
    }).join("");
    const rows = st.chart.map((g) => `<span class="ln">${esc(g.name)}</span>` + g.spots.map((id) => {
      const b = placeOf(base, id);
      return `<span class="lab${S.mapSel === id ? " sel" : ""}" data-act="map-mark" data-id="${esc(id)}">${esc(b ? b.name : id)}</span>` + Array.from({ length: total }, (_, i) => {
        const w = i + 1, row = byWeek[w], prev = w === 1 && st.start ? { control: st.start } : byWeek[w - 1]; // 第 1 週跟開季比（FB-264）
        if (w > st.now_week) return '<span class="cell future"></span>';
        if (!row || !row.control) return `<span class="cell blank" data-act="map-week" data-week="${w}"></span>`;
        const c = row.control[id], flip = prev && prev.control && prev.control[id] && prev.control[id] !== c;
        return `<span class="cell${w === week ? " now" : ""}${flip ? " flip" : ""}" data-act="map-week" data-week="${w}" style="background:${c ? sideInk(c).color : "#CDBF9F"}"></span>`;
      }).join("");
    }).join("")).join("");
    return `<div class="m-chart" style="grid-template-columns: 62px repeat(${total}, 1fr)">${head}${rows}</div>`;
  }
  function timelineHtml(base, st, week) {
    const close = '<button type="button" class="m-x" data-act="map-timeline" aria-label="收起">✕</button>';
    if (!st.territory || !(st.weeks || []).length) return `<div class="m-tl-head"><b>天下怎麼變</b>${close}</div><div class="m-sub">這一季沒有地盤易手。</div>`;
    const row = (st.weeks || []).find((x) => x.week === week) || { events: [], changed: [] };
    const now = tally(base, controlAt(st, week)), from = tallyFrom(base, st, week);
    const sum = (st.sides || sideOrder(base)).map((sd) => `<div style="background:${sideInk(sd).color}"><b>${now[sd] || 0}</b>${esc(sideInk(sd).name)}${from ? `<small>　${signed((now[sd] || 0) - (from.n[sd] || 0))}</small>` : ""}</div>`).join("")
      + (from ? `<small class="m-sum-note">${from.label}</small>` : "");
    const name = (id) => esc((placeOf(base, id) || { name: id }).name);
    const side = (k) => `<span style="color:${k ? sideInk(k).color : "inherit"}">${esc(sideName(k))}</span>`;
    const list = [...row.events.map((t) => `<div class="m-evt">📜 <b>${esc(t)}</b></div>`),
      ...row.changed.map((e) => `<div class="m-evt">⇄ ${name(e.id)}：${side(e.from)} → ${side(e.to)}</div>`)].join("");
    return `<div class="m-tl-head"><b>天下怎麼變<small>第 ${Number(week)} 週週末</small></b><button type="button" data-act="map-play">▶ 播放</button><button type="button" data-act="map-now">回到現在</button>${close}</div>
      ${graphSvg(st, week)}<div class="m-sum">${sum}</div>${chartHtml(base, st, week)}
      <div class="m-sec"><h4>第 ${Number(week)} 週</h4>${list || '<div class="m-sub">沒有地點易手。</div>'}</div>`;
  }
  let mapPlaying = 0;
  const stopPlay = () => { if (mapPlaying) { clearInterval(mapPlaying); mapPlaying = 0; } }; // 沒在播放就什麼都不做（切分頁每次都叫）
  // 換看哪一週：抽屜、記號、上方那一條「正在看第 N 週」跟著換，不整頁重畫
  function mapWeekTo(w) {
    const st = S.mapState;
    S.mapWeek = Math.max(1, Math.min(st.now_week, w));
    redrawDrawer();
    drawMarks();
    const banner = document.getElementById("map-banner");
    if (banner) {
      banner.hidden = S.mapWeek === st.now_week;
      banner.textContent = `正在看第 ${S.mapWeek} 週`;
    }
  }
  // 打開、收起版圖變化（設計 4.1：在天下圖上播）：打開時換到天下圖（地圖框縮到抽屜上面，天下圖照那一塊重新取景）；收起時留在天下圖。
  // 區圖那一層原本的視圖（S.mapView）不動，之後再進一州照舊
  function mapTimeline(open) {
    stopPlay();
    if (!document.getElementById("mapx")) return;
    if (open) Object.assign(S, { mapLayer: "world", mapMode: "timeline", mapSel: null, mapWeek: S.mapState.now_week, mapDrawer: "tl" });
    else Object.assign(S, { mapMode: "overview", mapSel: null, mapWeek: null, mapDrawer: S.mapLayer === "world" ? "min" : "home" });
    remapChrome();
    applyMapView(true);
    drawMarks();
  }
  // 曲線上點一下：照點的位置換那一週
  function graphPick(el, ev) {
    const st = S.mapState, r = el.getBoundingClientRect();
    if (!st || !r.width) return;
    const x = ((ev.clientX - r.left) / r.width) * (GX0 + GW + 34);
    mapWeekTo(Math.round(((x - GX0) / GW) * (Math.max(2, st.weeks_total) - 1)) + 1);
  }

  // 找地點的輸入框：只換結果那一塊，輸入框本身不重畫（不然一打字就失焦）
  function mapQueryInput(ev) {
    if (!ev.target || ev.target.id !== "map-q" || !S.mapBase || !S.mapState) return;
    S.mapQuery = ev.target.value;
    const box = document.getElementById("map-results");
    if (box) box.innerHTML = searchResults(S.mapBase, S.mapState, S.mapQuery);
  }
  // 抽屜的把手：拖上拖下（放開時靠到最近的一格），點一下在收著、半開之間換
  function drawerGrab() {
    const grab = document.getElementById("mgrab"), drawer = document.getElementById("mdrawer");
    if (!grab || !drawer || (grab.dataset && grab.dataset.wired)) return; // 同一個把手只掛一次（換層時 remapChrome 換了新的把手才再掛）
    if (grab.dataset) grab.dataset.wired = "1";
    let drag = null;
    grab.addEventListener("pointerdown", (ev) => {
      try { grab.setPointerCapture(ev.pointerId); } catch (e) { /* 合成的事件抓不住 */ }
      drag = { y: ev.clientY, h: drawer.offsetHeight, moved: false };
      drawer.classList.add("dragging");
    });
    grab.addEventListener("pointermove", (ev) => {
      if (!drag) return;
      const dy = drag.y - ev.clientY;
      if (Math.abs(dy) > 5) drag.moved = true;
      if (drag.moved) drawer.style.height = `${Math.max(mapDrawerPx("min"), Math.min(mapDrawerPx("full"), drag.h + dy))}px`;
    });
    const end = () => {
      if (!drag) return;
      drawer.classList.remove("dragging");
      // 點一下：總覽在收起、收著之間換（拉高的放回收著）；一個地點在半開、拉高之間換。拖：放開時靠到最近的一格（總覽多一格收起）
      // 天下圖的總覽（world）：收著那一行與拉開的卡兩格之間換，拖照收著、半開、全開三格
      const now = drawerNow(), place = S.mapMode === "place", world = S.mapLayer === "world" && S.mapMode === "overview";
      if (!drag.moved) drawerTo(place ? (now === "peek" ? "half" : "peek") : world ? (now === "min" ? "half" : "min") : now === "rest" ? "min" : "rest");
      else {
        const h = drawer.offsetHeight, stops = place ? ["peek", "half", "full"] : world ? ["min", "half", "full"] : S.mapMode === "overview" ? ["min", "rest", "half", "full"] : ["rest", "half", "full"];
        drawerTo(stops.sort((a, z) => Math.abs(mapDrawerPx(a) - h) - Math.abs(mapDrawerPx(z) - h))[0]);
      }
      drag = null;
    };
    grab.addEventListener("pointerup", end);
    grab.addEventListener("pointercancel", end);
  }

  function redrawDrawer() {
    const body = document.getElementById("mbody");
    if (body) body.innerHTML = drawerHtml();
    // 總覽那一格照今天還能出陣幾次決定收起或收著：疊層換了（次數用完）就跟著換高度。只在高度真的變了才動（輪詢不重設）
    const d = document.getElementById("mdrawer");
    if (S.mapDrawer === "home" && d && d.style.height !== `${mapDrawerPx("home")}px`) setMapDrawer("home");
  }
  // ── 抽屜收起（Joy 2026-10-17「今天去哪裡出陣能不能真的縮起來，手機版受影響很大」）──
  // 總覽可以收成一條（把手＋一行「出陣 今日還能 N 次 ▴」），地圖拿回大部分畫面。收起或攤開是玩家自己選的，記在這個瀏覽器
  // （localStorage，換頁、輪詢、重新整理都照它）；沒選過時，今天的出陣次數用完了就收起，還有次數（或不出陣的散人）攤開。
  // S.mapDrawer 是 "home" 時照這裡現算，所以次數用完那一刻跟著收起
  const DRAWER_KEY = "tx-map-drawer";
  function drawerPref() {
    try { const v = localStorage.getItem(DRAWER_KEY); return v === "min" || v === "open" ? v : null; } catch (e) { return null; }
  }
  function homeDrawer() {
    const pref = drawerPref();
    if (pref) return pref === "min" ? "min" : "rest";
    return S.mapState && S.mapState.sorties_left === 0 ? "min" : "rest";
  }
  const drawerNow = () => (S.mapDrawer === "home" ? homeDrawer() : S.mapDrawer);
  // 桌機（寬 900 以上）抽屜是右欄、整欄攤開，沒有收起這回事
  const deskMap = () => !!(window.matchMedia && window.matchMedia("(min-width: 900px)").matches);
  // 玩家自己拉、點把手、點那一行：總覽收起或攤開記下來（之後回到總覽照它）；其餘照舊
  function drawerTo(h) {
    // 天下圖的抽屜不記（每次打開輿圖都是收著那一行，設計 4.1）；記的是區圖那一層總覽的收起或攤開
    if (S.mapLayer !== "world" && S.mapMode === "overview" && ["min", "rest", "half", "full"].includes(h)) {
      try { localStorage.setItem(DRAWER_KEY, h === "min" ? "min" : "open"); } catch (e) { /* 記不住就只管這一次 */ }
      if (h === "min" || h === "rest") h = "home";
    }
    setMapDrawer(h);
  }
  // 收起時那一行：在路上寫往哪裡、還有幾分；出陣寫今天還能幾次；其餘寫你在哪。整行一顆鈕，點了攤開
  function miniHtml(base, st) {
    const j = st.journey, here = placeOf(base, st.here);
    const text = j ? `往 <b>${esc(j.to_name)}</b>・還有 ${Number(j.minutes)} 分鐘`
      : st.sorties_left !== null && st.suggest.length ? `<b>出陣</b> 今日還能 ${Number(st.sorties_left)} 次${here ? `・你在 ${esc(here.name)}` : ""}`
      : `你在 <b>${esc(here ? here.name : "")}</b>`;
    return `<button type="button" class="m-mini" data-act="map-open" aria-label="攤開抽屜"><span>${text}</span><i>▴</i></button>`;
  }
  // 抽屜的高度（設計第一節）：收著 230、半開（點了地點）240、拉高六成、全開九成四、版圖變化 320；桌機是右欄（CSS 蓋掉高度）
  function mapDrawerPx(h) {
    const box = document.getElementById("mapx");
    const avail = (box && box.clientHeight) || 600;
    // 版圖變化 320 高（企劃者 10/15 從對比圖選乙）：地圖大一截，曲線與處數在一屏，年表往下捲
    if (h === "home") h = homeDrawer();
    // 收起 54：把手 22＋一行 32（Joy 2026-10-17）
    return { min: 54, rest: 230, peek: 240, half: Math.round(avail * 0.6), full: Math.round(avail * 0.94), tl: Math.min(320, Math.round(avail * 0.55)) }[h] || 230;
  }
  function setMapDrawer(h) {
    S.mapDrawer = h;
    const d = document.getElementById("mdrawer"), box = document.getElementById("mapx");
    if (!d || !box) return;
    const px = mapDrawerPx(h);
    d.style.height = `${px}px`;
    // 收起換成那一行（或從那一行攤開）：抽屜裡的內容跟著換
    const min = drawerNow() === "min" && S.mapMode === "overview" && !deskMap();
    if (d.classList && d.classList.contains("min") !== min) {
      d.classList.toggle("min", min);
      const body = document.getElementById("mbody");
      if (body && S.mapBase && S.mapState) body.innerHTML = drawerHtml();
    }
    // 攤開的總覽：把手右邊一個小字「收起 ▾」，看得出點把手就收（style.css 的 .can-fold）
    if (d.classList) d.classList.toggle("can-fold", S.mapMode === "overview" && drawerNow() === "rest" && !deskMap());
    const grab = document.getElementById("mgrab");
    if (grab && grab.setAttribute) grab.setAttribute("aria-label", min ? "攤開" : S.mapMode === "overview" && drawerNow() === "rest" ? "收起（拖動拉高拉低）" : "拉高拉低");
    // --md-h 只有版圖變化用得到（地圖框縮到抽屜上面，style.css 的 .mapx.tl-mode）：自訂屬性會一路繼承下去，平常點地點換抽屜高度時
    // 寫它會逼整棵地圖重算樣式（FB-322）。進版圖變化時 mapTimeline 先改 S.mapMode 再叫這裡，畫面重畫時 mapReady 也會叫
    if (S.mapMode === "timeline") box.style.setProperty("--md-h", `${px}px`);
    // pad 跟著抽屜變了：當下照新的 pad 夾住視圖。抽屜降低時不夾的話，地圖停在捲過頭的位置（下緣到抽屜之間露出空白），
    // 下一次拖動才夾回去、往手指反方向跳一截（FB-267）。天下圖的取景不看抽屜拉多高（只讓開收著那一行），不必重套
    if (S.mapView && S.mapLayer !== "world") applyMapView(true);
    keepSelVisible(); // 抽屜升高：選了的地點被蓋住就對準露出來的那一塊
  }
  // 抽屜蓋住地圖框底下多高（clampView 的 pad）：照抽屜要變成的高度算，不量 offsetHeight——抽屜換高度有 0.22 秒的動畫，
  // 那一刻量到的還是舊的高度（從找地點全開挑一處時會量到九成四，地圖被捲過頭）。桌機（右欄）與版圖變化（地圖框已經在抽屜上面）是 0
  function mapPad() {
    if (!document.getElementById("mdrawer") || S.mapMode === "timeline" || deskMap()) return 0;
    return mapDrawerPx(S.mapDrawer);
  }
  // 選了的地點被抽屜蓋住（或在露出來那一塊的外面）：對準露出來的那一塊。沒被蓋住就不動（點在地圖上的地點不從手指底下跑開）
  function keepSelVisible() {
    if (!S.mapSel || S.mapMode !== "place") return;
    const g = mapGeom(document.getElementById("map"));
    const p = g && placeXY(S.mapSel);
    if (!p || !S.mapView) return;
    const pad = mapPad(), v = S.mapView;
    const y = g.vh / 2 + (p[1] - v.cy) * v.s, x = g.vw / 2 + (p[0] - v.cx) * v.s;
    if (y < 12 || y > g.vh - pad - 28 || x < 12 || x > g.vw - 12) mapCenterOn(S.mapSel);
  }
  // 整頁那一層夾在狀態列與分頁列之間：狀態列展開收起、視窗換大小時重量
  function mapFrame() {
    const box = document.getElementById("mapx");
    if (!box) return;
    const top = document.getElementById("top"), tabs = document.querySelector(".tabs");
    // 變了才寫：自訂屬性會繼承到整張地圖，寫一次整棵約 1,600 個元素重算樣式（狀態列每次重畫都叫這裡，Joy 2026-10-17）
    setVar(box, "--map-top", `${top && !top.hidden ? Math.round(top.getBoundingClientRect().bottom) : 0}px`);
    setVar(box, "--map-bottom", `${tabs ? Math.round(window.innerHeight - tabs.getBoundingClientRect().top) : 0}px`);
  }
  let marksFrame = 0;
  // 照現在的倍率、濾鏡、選取、週次重畫記號、大區的顏色與上方那一條「天下」
  // 這一層此刻的視圖：天下圖是固定的取景（S.worldView，applyMapView 照 worldFit 算），區圖是可以拖縮的那一個（S.mapView）
  const curView = () => (S.mapLayer === "world" && S.mapBase && S.mapBase.world ? S.worldView : S.mapView);
  function drawMarks() {
    marksFrame = 0;
    const g = document.getElementById("mk"), v = curView();
    if (!g || !S.mapBase || !S.mapState || !v) return;
    const world = S.mapLayer === "world" && !!S.mapBase.world;
    const s = v.s, week = mapWeek(), layers = new Set(S.mapLayers);
    S.marksS = s;
    const wrap = document.getElementById("map");
    // 看大局（與天下圖）：底圖寫的大區名藏起來（記號那一層照大區另寫一份）。直接改那幾個字的 display，不在框上加 class：框上的 class 一變，
    // 整棵地圖約 1,500 個元素都要重算樣式（縮放跨過那一檔時一下 40ms 上下）
    const far = world || s < MAP_FAR;
    if (wrap && wrap.classList.contains("far") !== far) {
      wrap.classList.toggle("far", far); // 只留給測試與除錯看，style.css 不再照它藏字
      wrap.querySelectorAll(".tx-region-name").forEach((el) => { el.style.display = far ? "none" : ""; });
    }
    // 選了的那一圈不跟著記號畫（sel: null），另外畫在上面那一張最後（drawSel）：點一處只換那一圈，不必整批重建一千多個元素
    const [low, high] = world ? worldParts(S.mapBase, S.mapState, { k: 1 / s, week, tl: S.mapMode === "timeline", sel: null })
      : marksParts(S.mapBase, S.mapState, { k: 1 / s, far: s < MAP_FAR, layers, sel: null, week, tl: S.mapMode === "timeline" });
    g.innerHTML = low;
    const top = document.getElementById("mkt"); // 會跳的圈與之後畫的那一段（FB-323）
    if (top) top.innerHTML = `${high}<g id="msel" pointer-events="none"></g>`;
    drawSel();
    const ins = !world && insightOn(S.mapBase, layers);
    const tint = world ? {} : regionTint(S.mapBase, S.mapState, week, layers.has("control") && !ins); // 意境開著不畫勢力的大區底色
    // 天下圖：底圖的大區底色與點劃線州界讓位給地面與州的輪廓（地面蓋在上面，底下只留紙與山水）
    document.querySelectorAll("#map path[data-region]").forEach((el) => {
      if (world) { el.style.fill = "none"; el.style.stroke = "none"; return; }
      el.style.removeProperty("stroke");
      const t = tint[el.getAttribute("data-region")];
      if (t) el.style.fill = t; else el.style.removeProperty("fill");
    });
    const hud = document.getElementById("map-hud");
    if (hud) {
      hud.hidden = world || !(s < MAP_FAR || S.mapMode === "timeline") || !S.mapState.territory || ins; // 「天下」那一條是勢力的；天下圖寫在州名底下
      if (!hud.hidden) hud.innerHTML = hudHtml(S.mapBase, S.mapState, week);
    }
  }
  // 選了的地點那一圈（同 marksParts 的 sel 那一圈：圓盤外 9px、線寬 3px，照螢幕固定）。點地點、收起只叫這裡（Joy 2026-10-17
  // 「輿圖還是很 lag」：以前點一下整批記號重畫，節流到六倍要兩三百毫秒）
  function drawSel() {
    const box = document.getElementById("msel"), v = curView();
    if (!box || !v) return;
    const p = S.mapSel && placeXY(S.mapSel);
    if (!p) { if (box.firstChild) box.innerHTML = ""; return; }
    const k = 1 / v.s, r = (v.s < MAP_FAR ? 6 : 11) * k;
    box.innerHTML = `<circle cx="${p[0]}" cy="${p[1]}" r="${f1(r + 9 * k)}" fill="none" stroke="${MAP_INK}" stroke-width="${f1(3 * k)}"/>`;
  }
  const scheduleMarks = () => { if (!marksFrame) marksFrame = requestAnimationFrame(drawMarks); };

  // ── 天下圖（輿圖簡化設計 5.1、3.3、5.6；環形版 dev/map-2 寫的，輿圖第三版第 3 批搬回真實地形）──
  // 打開輿圖第一眼。不另開一張圖：同一張底圖（山水已經烤成點陣）換一個固定的取景（worldFit：取景框整張放進地圖框露出來的那一塊），
  // 不拖、不縮；記號那一層（#mk、#mkt）畫大區地面——每一區（程式裡叫「州」）的地面照「離哪個地點最近」分給那個地點此刻的控制方
  // （底圖的 world.cells，照那一區的輪廓裁），一方一色、沒人佔一色（顏色照劇本，sideInk）——、正在翻（攻方的斜紋照進度泛進來）、
  // 剛易手還在冷卻（新主人的淡色、一圈虛線）、
  // 紅線（任兩方的地面相接；真實地形的大區互不相接，前線都在同一區裡）、細墨線（有主與沒人佔相接）、激戰（那一格一圈紅光閃）、
  // 大區的輪廓、金點（高級資源地：實心＝有人佔）、大區名與各方幾處、你。點一區進那一區（enterRegion：第 4 批之前是現在這張可縮放的
  // 地圖、取景對準那一區的地點）。字待 joy 潤
  const WORLD_WORD = "天下", WORLD_ENTER = "進入此區", RICH_WORD = "寶";
  const WORLD_TOP = 58; // 上面那一排（天下・找地點・版圖）讓開多高（px）
  const WORLD_TL_TOP = 36; // 版圖變化時那一排收起，只讓開「正在看第 N 週」
  const WORLD_PAD = 54; // 抽屜收著時的高度：天下圖照它讓開底下（拉開的卡蓋在圖上，圖不跟著縮）
  const WORLD_EDGE = 8; // 取景框離地圖框的邊至少多少（px）
  const WORLD_GROUND = 0.8; // 地面的濃淡：底下的山水淡淡地透上來（設計 4.5）
  const WORLD_INK = "#3A3127", WORLD_RIM = "#5B4A38", WORLD_GOLD = "#C8961E";
  const WORLD_NAME_PX = 16, WORLD_LINE_PX = 11; // 大區名、大區名底下那一行，螢幕上的大小
  const WORLD_FULL_PX = 330, WORLD_SHRINK = 0.82; // 取景框在螢幕上不到這麼寬時字照比例縮，最多縮到這麼多（11px 的那一行縮到 9px）
  // 大區名的位置都會壓到時往哪裡挪（照框的寬、高的倍數）：左右最多一個半框、上下最多兩格半，近的先（框是橫的：左右挪一個框算兩格遠）
  const WORLD_NUDGE = worldNudge();
  function worldNudge() {
    const out = [];
    for (let dx = -1.5; dx <= 1.5; dx += 0.5) for (let dy = -2.5; dy <= 2.5; dy += 0.5) if (dx || dy) out.push([dx, dy]);
    return out.sort((a, z) => Math.hypot(2 * a[0], a[1]) - Math.hypot(2 * z[0], z[1]) || a[1] - z[1] || a[0] - z[0]);
  }
  // 正在翻（設計 4.1）：攻方的斜紋照進度泛進那一格，進度 100 時多濃（底下守方的地面照樣看得到）；斜紋的間距與線寬照螢幕（px）。
  // 資料是疊層的 places[id].tug（{攻方: 進度}，mapdata.flip_marks 照翻地那一份 conquest.block_view 的 bars 換的名字），沒有就不畫
  const WORLD_TUG_MAX = 0.75, WORLD_TUG_GAP = 5, WORLD_TUG_LINE = 2.2;
  // 剛易手、還在冷卻（疊層的 places[id].cool：還要幾分鐘；設計 4.1 兩邊都推不動、加成暫停）【開發定】：地面換成新主人那一方的淡色（tint）、
  // 那一格一圈新主人顏色的虛線（還沒站穩），不閃。虛線的長短照螢幕（px）
  const WORLD_COOL_DASH = 4, WORLD_COOL_GAP = 3, WORLD_COOL_LINE = 1.4;
  const f2 = (n) => Math.round(n * 100) / 100;
  // 估一段字在螢幕上多寬（px）：中日韓的字一個字寬、數字與英文約六成、空白約三成
  function textW(text, px) {
    let w = 0;
    for (const ch of String(text)) w += ch === " " ? 0.3 : ch.charCodeAt(0) < 0x2e80 ? 0.6 : 1;
    return w * px;
  }
  // 取景：frame [x, y, w, h] 放進地圖框（vw × vh）上面讓開 top、底下讓開 pad、四邊留 WORLD_EDGE 的那一塊，置中；給了地圖的大小
  // （W × H）時再夾住：露出來的那一塊不超出地圖（不然上面留一條空白的紙），地圖比那一塊小就置中——取景框照樣整個看得到
  function worldFit(vw, vh, frame, pad, top, W = 0, H = 0) {
    const [fx, fy, fw, fh] = frame;
    const aw = Math.max(1, vw - 2 * WORLD_EDGE), ah = Math.max(1, vh - pad - top - 2 * WORLD_EDGE);
    const s = Math.min(aw / fw, ah / fh);
    let cx = fx + fw / 2, cy = fy + fh / 2 - (top - pad) / 2 / s;
    const clamp = (c, size, lo, hi) => { // 露出來的是 [c − lo, c + hi]（地圖單位）
      if (lo + hi >= size) return size / 2 - (hi - lo) / 2;
      return Math.min(size - hi, Math.max(lo, c));
    };
    if (W > 0 && H > 0) {
      cx = clamp(cx, W, vw / 2 / s, vw / 2 / s);
      cy = clamp(cy, H, (vh / 2 - top) / s, (vh / 2 - pad) / s);
    }
    return { s, cx, cy };
  }
  // 每一州的地面各方幾處、高級資源地幾處（只算分地面的地點：底圖的 world.cells）
  function worldCounts(base, st, ctrl) {
    const out = {};
    for (const c of base.world.cells) {
      const n = out[c.region] || (out[c.region] = { rich: 0 });
      if (ctrl[c.id]) n[ctrl[c.id]] = (n[ctrl[c.id]] || 0) + 1;
      if (st.places[c.id] && st.places[c.id].rich) n.rich += 1;
    }
    return out;
  }
  // 大區名與底下那一行「官 N・巾 N・寶 N」（照疊層的 sides：會佔地的幾方；只寫不是 0 的，全是 0 就沒有那一行）：每一區一個框（地圖單位，k＝1／倍率）。
  // 底圖給每一區幾個可以擺的位置（好的在前）；小的大區先挑（底圖的 area），前一個會壓到已經擺好的（或你）就換下一個，都不行在第一個附近挪一挪
  // （WORLD_NUDGE），再不行用第一個；夾在取景框裡
  function worldLabels(base, st, ctrl, k) {
    const wd = base.world, n = worldCounts(base, st, ctrl), sides = st.sides || sideOrder(base);
    const [fx, fy, fw, fh] = wd.frame, placed = {};
    // 天下圖在螢幕上很小時（320 寬、版圖變化把框縮到抽屜上面）字跟著縮一點，最多縮到 WORLD_SHRINK
    const shrink = Math.max(WORLD_SHRINK, Math.min(1, fw / k / WORLD_FULL_PX));
    const np = WORLD_NAME_PX * shrink, lp = WORLD_LINE_PX * shrink;
    const order = [...wd.regions].sort((a, z) => (a.area || 0) - (z.area || 0));
    // 你（紅點、紅旗、外面那一圈；畫在上面那一張，會蓋住字）先佔一塊：大區名讓開它
    const me = st.journey || placeOf(base, st.here);
    if (me && me.x !== undefined) placed[""] = { x: me.x + 2 * k, y: me.y - 7 * k, w: 24 * k, h: 34 * k };
    for (const r of order) {
      const c = n[r.id] || { rich: 0 };
      // 只寫有的：是 0 的那一方、寶 0 都不寫；全是 0 那一行就不畫（企劃者 2026-10-20 從對比圖選乙）
      const line = [...sides.filter((sd) => c[sd]).map((sd) => `${sideInk(sd).short} ${c[sd]}`), ...(c.rich ? [`${RICH_WORD} ${c.rich}`] : [])].join("・");
      const w = Math.max(textW(r.name, np), textW(line, lp)) * k + 6 * k;
      const h = (line ? np + 3 + lp : np) * k + 4 * k;
      const fit = ([x, y]) => [Math.min(fx + fw - w / 2, Math.max(fx + w / 2, x)), Math.min(fy + fh - h / 2, Math.max(fy + h / 2, y))];
      const spots = (r.spots && r.spots.length ? r.spots : [[r.lx, r.ly]]).map(fit);
      const clash = ([x, y], me) => Object.entries(placed).some(([id, b]) => (me || id !== "") && Math.abs(b.x - x) * 2 < b.w + w && Math.abs(b.y - y) * 2 < b.h + h);
      // 底圖給的位置都會壓到（320 寬時天下圖只剩約 0.17 倍、大區名比大區還大）：在第一個位置附近挪一挪找不壓的；連你都讓開找不到時，
      // 只讓開別的大區名（大區名彼此不壓是硬規矩，蓋到你一角可以）；再不行才用第一個
      const free = (me) => spots.find((p) => !clash(p, me)) || WORLD_NUDGE.map(([dx, dy]) => fit([spots[0][0] + dx * w, spots[0][1] + dy * h])).find((p) => !clash(p, me));
      const [x, y] = free(true) || free(false) || spots[0];
      placed[r.id] = { id: r.id, x, y, w, h, name: r.name, line, np, lp };
    }
    return wd.regions.map((r) => placed[r.id]);
  }
  // 正在翻那一層的斜紋（每一個出現在 tug 裡的攻方一個 <pattern>，顏色照 sideInk；地圖單位，k＝1／倍率）
  function tugPattern(side, k) {
    const ink = sideInk(side), gap = f1(WORLD_TUG_GAP * k);
    return `<pattern id="wt-${esc(side)}" patternUnits="userSpaceOnUse" width="${gap}" height="${gap}" patternTransform="rotate(45)">`
      + `<rect width="${gap}" height="${gap}" fill="${ink.soft}" fill-opacity=".55"/><line x1="0" y1="0" x2="0" y2="${gap}" stroke="${ink.color}" stroke-width="${f1(WORLD_TUG_LINE * k)}"/></pattern>`;
  }
  // 這一格正在被誰翻、翻到幾成（疊層的 tug 裡進度最高的那一方；守方自己、進度 0 不算）；沒有是 null
  function tugOf(st, id, holder) {
    const t = st.places[id] && st.places[id].tug;
    if (!t) return null;
    const best = Object.entries(t).filter(([sd, v]) => sd !== holder && Number(v) > 0).sort((a, z) => Number(z[1]) - Number(a[1]))[0];
    return best ? { side: best[0], pct: Math.min(100, Number(best[1])) } : null;
  }
  // 天下圖的記號（純函式）：o = { k: 1／倍率, week: 看哪一週, tl: 正在看版圖變化, sel: 年表上圈起來的地點 }。回 [底下那一張, 上面那一張]
  // （同 marksParts：會跳的圈與你畫在上面那一張 #mkt）
  function worldParts(base, st, o) {
    const wd = base.world, k = o.k, ctrl = controlAt(st, o.week), pos = Object.fromEntries(base.places.map((p) => [p.id, p]));
    // 正在翻、激戰、冷卻是「此刻」的事：版圖變化看以前的週時不畫
    const live = o.week === st.now_week;
    const cooling = (id) => live && !!ctrl[id] && !!(st.places[id] && st.places[id].cool);
    const ground = (id) => (ctrl[id] ? sideInk(ctrl[id])[cooling(id) ? "tint" : "soft"] : wd.unheld);
    const tugs = live ? wd.cells.map((c) => [c, tugOf(st, c.id, ctrl[c.id] || null)]).filter(([, t]) => t) : [];
    const melee = live ? wd.cells.filter((c) => st.places[c.id] && st.places[c.id].melee) : [];
    const cools = wd.cells.filter((c) => cooling(c.id));
    const patterns = [...new Set(tugs.map(([, t]) => t.side))].map((sd) => tugPattern(sd, k)).join("");
    const out = [`<defs>${wd.regions.map((r) => `<clipPath id="wc-${esc(r.id)}"><path d="${r.d}"/></clipPath>`).join("")}${patterns}</defs>`];
    // 地面：整區先塗沒人佔（一區沒有分地面的地點就是一整片沒人佔），再一格一格塗誰佔著，照那一區的輪廓裁
    out.push(`<g class="w-ground" opacity="${WORLD_GROUND}" pointer-events="none">`);
    for (const r of wd.regions) {
      out.push(`<path d="${r.d}" fill="${wd.unheld}"/><g clip-path="url(#wc-${esc(r.id)})">`);
      for (const c of wd.cells) if (c.region === r.id) out.push(`<path data-cell="${esc(c.id)}" d="${c.d}" fill="${ground(c.id)}"/>`);
      out.push("</g>");
    }
    out.push("</g>");
    // 正在翻（兩色拔河）：守方的地面上疊攻方的斜紋，濃淡照進度（設計 4.1）
    for (const r of wd.regions) {
      const mine = tugs.filter(([c]) => c.region === r.id);
      if (mine.length) out.push(`<g clip-path="url(#wc-${esc(r.id)})">${mine.map(([c, t]) => `<path class="w-tug" data-cell="${esc(c.id)}" d="${c.d}" fill="url(#wt-${esc(t.side)})" opacity="${f2((t.pct / 100) * WORLD_TUG_MAX)}" pointer-events="none"/>`).join("")}</g>`);
    }
    out.push(`<g class="w-outline" fill="none" stroke="${WORLD_INK}" stroke-width="${f1(1.4 * k)}" stroke-linejoin="round" pointer-events="none">${wd.regions.map((r) => `<path d="${r.d}"/>`).join("")}</g>`);
    // 冷卻：那一格一圈新主人顏色的虛線（畫在紅線、細墨線底下：前線照樣看得清楚）
    for (const c of cools) out.push(`<path class="w-cool" data-cell="${esc(c.id)}" d="${c.d}" fill="none" stroke="${sideInk(ctrl[c.id]).color}" stroke-width="${f1(WORLD_COOL_LINE * k)}" stroke-dasharray="${f1(WORLD_COOL_DASH * k)} ${f1(WORLD_COOL_GAP * k)}" stroke-linejoin="round" clip-path="url(#wc-${esc(c.region)})" pointer-events="none"/>`);
    // 邊：兩邊是不同的兩方＝紅線（前線）、一邊有主一邊沒人佔＝細墨線、同一方或都沒人＝不畫（同一區裡的邊照那一區的輪廓裁）
    const front = [], rim = [];
    for (const e of wd.edges) {
      const a = (e.a && ctrl[e.a]) || null, b = (e.b && ctrl[e.b]) || null;
      if (a === b) continue;
      (a && b ? front : rim).push(`<path d="${e.d}"${e.clip ? ` clip-path="url(#wc-${esc(e.clip)})"` : ""}/>`);
    }
    out.push(`<g class="w-rim" fill="none" stroke="${WORLD_RIM}" stroke-width="${f1(1.1 * k)}" pointer-events="none">${rim.join("")}</g>`);
    out.push(`<g class="w-front" fill="none" stroke="${FRONT_RED}" stroke-width="${f1(3 * k)}" stroke-linecap="round" pointer-events="none">${front.join("")}</g>`);
    // 激戰：兩邊都有人正在推的那一格一圈紅光，一閃一閃（style.css 的 .w-melee；減少動態效果的人不閃）
    for (const c of melee) out.push(`<path class="w-melee" data-cell="${esc(c.id)}" d="${c.d}" fill="${FRONT_RED}" fill-opacity=".16" stroke="${FRONT_RED}" stroke-width="${f1(3.2 * k)}" stroke-linejoin="round" clip-path="url(#wc-${esc(c.region)})" pointer-events="none"/>`);
    // 點一區：整區一塊透明的點擊區
    for (const r of wd.regions) out.push(`<path data-act="world-region" data-id="${esc(r.id)}" d="${r.d}" fill="#000000" fill-opacity="0" style="cursor:pointer"><title>${esc(r.name)}</title></path>`);
    // 金點：高級資源地（開季中立的），實心＝此刻有人佔、空心＝沒人佔
    for (const p of base.places) {
      if (!st.places[p.id] || !st.places[p.id].rich) continue;
      const held = !!ctrl[p.id];
      out.push(`<circle class="w-rich${held ? " held" : ""}" cx="${p.x}" cy="${p.y}" r="${f1(4.2 * k)}" fill="${held ? WORLD_GOLD : MAP_HALO}" stroke="${WORLD_GOLD}" stroke-width="${f1(1.6 * k)}" pointer-events="none"/>`);
    }
    // 大區名、底下那一行
    for (const l of worldLabels(base, st, ctrl, k)) {
      const top = l.y - l.h / 2, nameY = f1(top + (2 + l.np * 0.88) * k), lineY = f1(top + (2 + l.np + 3 + l.lp * 0.88) * k);
      out.push(`<g class="w-label" pointer-events="none" style="font-family:serif"><text x="${f1(l.x)}" y="${nameY}" text-anchor="middle" font-size="${f1(l.np * k)}" font-weight="700" letter-spacing="${f1(2 * k)}" fill="${MAP_INK}" stroke="${MAP_HALO}" stroke-width="${f1(3.4 * k)}" paint-order="stroke">${esc(l.name)}</text>`
        + (l.line ? `<text x="${f1(l.x)}" y="${lineY}" text-anchor="middle" font-size="${f1(l.lp * k)}" font-weight="600" fill="#3A332A" stroke="${MAP_HALO}" stroke-width="${f1(3 * k)}" paint-order="stroke">${esc(l.line)}</text>` : "") + "</g>");
    }
    // 上面那一張：版圖變化看以前的週時易手的地點閃一圈、年表圈起來的地點、你（在路上畫在路上；紅點、一面紅旗、外面一圈慢慢擴散）
    const high = [];
    const wk = (st.weeks || []).find((x) => x.week === o.week);
    if ((o.tl || o.week !== st.now_week) && wk) for (const e of wk.changed) if (pos[e.id]) high.push(`<circle class="pulse" cx="${pos[e.id].x}" cy="${pos[e.id].y}" r="${f1(10 * k)}" fill="none" stroke="${FRONT_RED}" stroke-width="${f1(2.5 * k)}" pointer-events="none"/>`);
    if (o.sel && pos[o.sel]) high.push(`<circle cx="${pos[o.sel].x}" cy="${pos[o.sel].y}" r="${f1(11 * k)}" fill="none" stroke="${MAP_INK}" stroke-width="${f1(2.5 * k)}" pointer-events="none"/>`);
    const j = st.journey, h = pos[st.here];
    const hx = j ? j.x : h && h.x, hy = j ? j.y : h && h.y;
    if (hx !== undefined) {
      high.push(`<circle class="pulse" cx="${hx}" cy="${hy}" r="${f1(10 * k)}" fill="none" stroke="${FRONT_RED}" stroke-width="${f1(2.2 * k)}" pointer-events="none"/>`);
      high.push(`<circle class="w-you" cx="${hx}" cy="${hy}" r="${f1(5 * k)}" fill="${FRONT_RED}" stroke="#FFFFFF" stroke-width="${f1(1.6 * k)}" pointer-events="none"/>`);
      high.push(`<path d="M${f1(hx + 2 * k)} ${f1(hy - 5 * k)}V${f1(hy - 24 * k)}L${f1(hx + 14 * k)} ${f1(hy - 19.5 * k)}L${f1(hx + 2 * k)} ${f1(hy - 15 * k)}" fill="${FRONT_RED}" stroke="#7A1F18" stroke-width="${f1(1.2 * k)}" pointer-events="none"/>`);
    }
    return [out.join(""), high.join("")];
  }
  // 天下圖的抽屜：收著時一行「你在 大區・地點」（在路上「往 X・還有 N 分鐘」）＋「進入此區 ›」；拉開（或桌機的右欄）是你腳下這一處的卡
  // （設計 5.1、5.3；第 4 批之前用 placeHtml）。點那一行攤開
  function worldDrawerHtml(base, st) {
    const j = st.journey, here = placeOf(base, st.here);
    const region = here && base.regions.find((r) => r.id === here.region);
    const where = j ? `往 <b>${esc(j.to_name)}</b>・還有 ${Number(j.minutes)} 分鐘` : `你在 <b>${esc(region ? region.name : "")}</b>・${esc(here ? here.name : "")}`;
    const enter = `<button type="button" class="m-enter" data-act="world-enter">${WORLD_ENTER} ›</button>`;
    if (drawerNow() === "min" && !deskMap()) return `<div class="m-wline"><button type="button" class="m-mini" data-act="map-open" aria-label="攤開抽屜"><span>${where}</span></button>${enter}</div>`;
    if (j) return `${journeyHtml(st)}<div class="m-wline"><span></span>${enter}</div>`;
    return `<div class="m-wline"><span class="m-where">${where}</span>${enter}</div>${here ? placeHtml(base, st, st.here) : ""}`;
  }
  // 一區的取景（點一區進來時；區圖第 4 批之前用可縮放的地圖當替身）：那一區的地點外框加邊（右邊多留給地名），放進露出來的那一塊——
  // 上面讓開找地點與濾鏡（REGION_TOP）、右邊讓開那一欄鈕（REGION_RIGHT）、底下讓開抽屜（pad）
  const REGION_MARGIN = 60, REGION_TOP = 96, REGION_RIGHT = 60;
  function regionView(base, rid, vw, vh, W, H, pad) {
    const pts = base.places.filter((p) => p.region === rid);
    if (!pts.length) return clampView({ s: fitScale(vw, vh, W, H), cx: W / 2, cy: H / 2 }, vw, vh, W, H, pad);
    const xs = pts.map((p) => p.x), ys = pts.map((p) => p.y);
    const x0 = Math.min(...xs) - REGION_MARGIN, x1 = Math.max(...xs) + 2 * REGION_MARGIN, y0 = Math.min(...ys) - REGION_MARGIN, y1 = Math.max(...ys) + REGION_MARGIN;
    // 倍率不低於看大局那一檔（MAP_FAR）：真實地形的潁川汝南很寬，整區塞進 375 寬會只剩點與大區名；寬的大區兩邊各切掉一點
    const s = clampScale(Math.max(MAP_FAR, Math.min((vw - REGION_RIGHT) / (x1 - x0), (vh - pad - REGION_TOP) / (y1 - y0))), vw, vh, W, H);
    return clampView({ s, cx: (x0 + x1) / 2 + REGION_RIGHT / 2 / s, cy: (y0 + y1) / 2 - (REGION_TOP - pad) / 2 / s }, vw, vh, W, H, pad);
  }
  // 換層：天下圖 ↔ 區圖。外圍的鈕與抽屜整個換掉（同 showMapHost 的做法），地圖本身留著
  function remapChrome() {
    const box = document.getElementById("mapx");
    if (!box) return;
    box.className = mapxClass();
    for (const el of [...box.children]) if (el.id !== "map") el.remove();
    box.insertAdjacentHTML("beforeend", mapChrome());
    drawerGrab();
    setMapDrawer(S.mapDrawer);
  }
  // 從天下圖點一區、「進入此區」、找地點挑了一處：換到區圖那一層，取景對準那一區（focus：挑的那一處，抽屜開它的卡）
  function enterRegion(rid, focus = null) {
    stopPlay();
    Object.assign(S, { mapLayer: "region", mapMode: focus ? "place" : "overview", mapSel: focus, mapWeek: null, mapQuery: "", mapDrawer: focus ? "peek" : "home" });
    remapChrome();
    const g = mapGeom(document.getElementById("map"));
    if (g && S.mapBase) S.mapView = regionView(S.mapBase, rid, g.vw, g.vh, g.W, g.H, mapDrawerPx(S.mapDrawer));
    applyMapView(true);
    drawMarks();
    if (focus) mapCenterOn(focus);
  }
  // 回天下圖（區圖上面那一排的「‹ 天下」、天下圖的「天下」）
  function toWorld() {
    stopPlay();
    Object.assign(S, { mapLayer: "world", mapMode: "overview", mapSel: null, mapWeek: null, mapQuery: "", mapDrawer: "min" });
    remapChrome();
    applyMapView();
    drawMarks();
  }
  const hereRegion = () => {
    const p = S.mapBase && S.mapState && placeOf(S.mapBase, S.mapState.here);
    return p ? p.region : null;
  };
  const regionOfPlace = (id) => {
    const p = S.mapBase && placeOf(S.mapBase, id);
    return p ? p.region : null;
  };

  // ── 底圖烤成一張圖（Joy 2026-10-18「輿圖滑動的時候還是很卡」）──
  // 底圖約 1,200 個 SVG 元素（山頭、樹、河、路）加一層絹紋雜訊濾鏡（feTurbulence）：拖到新的一塊、捏合換倍率，Chrome 都要把這些
  // 元素連同雜訊重新點陣化（手機上一格 256px 要好幾毫秒，捏合一下重畫兩三百格），每一幀的屬性樹也要走過整棵。打開輿圖之後把不會變的
  // 那些畫成一張點陣圖（<image>），只留會變的：底色那一塊（最前面的 rect）、大區（path[data-region]，drawMarks 照勢力換 fill）、字、記號。
  // 手勢中只剩貼一張圖。圖的解析度照螢幕（最多 3 倍、一千兩百萬像素）：原尺寸看是清楚的，放到兩倍時山水略軟，字照舊是向量
  const BAKE_PX = 12e6;
  const baked = { key: null, url: null }; // 這一張底圖烤好的圖（同一張底圖整層重畫時不必再烤）
  let bakeTimer = 0;
  function bakeLater() {
    clearTimeout(bakeTimer);
    bakeTimer = setTimeout(bakeBase, 250);
  }
  // 要烤進圖裡的：最前面那一塊底色、大區、字、記號、defs 以外的（路也烤進去：天下圖上它從地面底下淡淡透上來，企劃者 2026-10-20 選乙）
  function bakeable(svg) {
    const first = svg.querySelector(":scope > rect");
    return [...svg.children].filter((el) => {
      const t = el.tagName.toLowerCase();
      return el !== first && t !== "defs" && t !== "text" && t !== "image" && el.id !== "mk" && !el.hasAttribute("data-region") && !(el.querySelector && el.querySelector("text"));
    });
  }
  async function bakeBase() {
    const wrap = document.getElementById("map");
    const svg = wrap && wrap.querySelector(".tx-world-map > svg");
    if (!svg || svg.dataset.baked || typeof Image === "undefined" || typeof Blob === "undefined" || !window.URL || !URL.createObjectURL) return;
    if (mapHeld()) { bakeLater(); return; } // 手勢中不烤（烤的那一下要佔主執行緒）
    const vb = svg.viewBox && svg.viewBox.baseVal;
    const parts = bakeable(svg);
    if (!vb || !vb.width || !parts.length) return;
    const key = S.mapBase && S.mapBase.key;
    svg.dataset.baked = "1";
    try {
      let url = baked.key === key ? baked.url : null;
      if (!url) {
        const f = Math.max(1, Math.min(3, window.devicePixelRatio || 1, Math.sqrt(BAKE_PX / (vb.width * vb.height))));
        const w = Math.round(vb.width * f), h = Math.round(vb.height * f);
        const defs = svg.querySelector(":scope > defs");
        const src = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${vb.width} ${vb.height}" width="${w}" height="${h}">${defs ? defs.outerHTML : ""}${parts.map((el) => el.outerHTML).join("")}</svg>`;
        const vec = URL.createObjectURL(new Blob([src], { type: "image/svg+xml" }));
        const img = new Image();
        img.src = vec;
        await img.decode();
        const cv = document.createElement("canvas");
        cv.width = w; cv.height = h;
        cv.getContext("2d").drawImage(img, 0, 0, w, h);
        URL.revokeObjectURL(vec);
        const blob = await new Promise((ok) => cv.toBlob(ok, "image/png"));
        cv.width = cv.height = 0;
        if (!blob) throw new Error("toBlob");
        url = URL.createObjectURL(blob);
        if (baked.url && baked.key !== key) URL.revokeObjectURL(baked.url);
        Object.assign(baked, { key, url });
        const pic = new Image();
        pic.src = url;
        await pic.decode(); // 先解好碼再換上，換的那一下不閃
      }
      // 等的時候底圖可能換掉了（劇情開了新地點、登出）
      if (!svg.isConnected || (S.mapBase && S.mapBase.key) !== key) return;
      const now = bakeable(svg);
      const im = document.createElementNS("http://www.w3.org/2000/svg", "image");
      for (const [k, v] of [["x", 0], ["y", 0], ["width", vb.width], ["height", vb.height], ["preserveAspectRatio", "none"], ["href", url]]) im.setAttribute(k, v);
      im.setAttribute("class", "map-baked");
      im.setAttribute("pointer-events", "none");
      // 圖放在最後一塊大區後面（絹紋本來在大區底下，現在疊在大區上面：只有一成的淡褐雜訊，看不出差別）
      const regions = svg.querySelectorAll(":scope > [data-region]");
      const after = regions.length ? regions[regions.length - 1] : svg.querySelector(":scope > rect");
      svg.insertBefore(im, after ? after.nextSibling : now[0]);
      now.forEach((el) => el.remove());
    } catch (e) {
      /* 畫不出來（舊瀏覽器、記憶體不夠）：照舊用向量的底圖 */
    }
  }

  // ── 輿圖的視圖（W16）：純數學，不碰 DOM ──
  // 視圖 v = { s 倍率, cx, cy 視窗中心對著的地圖座標 }，地圖座標＝原尺寸的 px。存中心不存位移：視窗寬高變了（轉向、拉視窗）還對得上。
  // vw、vh 是視窗（地圖框）的大小，W、H 是地圖的大小（svg 的 viewBox）。手勢、滾輪、按鈕都走這幾個函式
  const MAP_MAX = 2; // 最多放到原尺寸的兩倍
  const fitScale = (vw, vh, W, H) => Math.min(vw / W, vh / H); // 整張看得完的倍率（也是最小倍率）
  const clampScale = (s, vw, vh, W, H) => Math.min(MAP_MAX, Math.max(fitScale(vw, vh, W, H), s));
  // 夾住：某一軸的地圖比視窗小就置中；比視窗大就不能拖到露出地圖外面。pad：視窗底下被抽屜蓋住的高度（手機上抽屜從底下升起；
  // 桌機抽屜是右欄、版圖變化時地圖框已經縮到抽屜上面，都是 0）：地圖底下可以多捲 pad，最下緣的地點也拉得到抽屜上面；
  // 整張比露出來的那一塊還矮時，置中在露出來的那一塊（PM 2026-10-15：下緣的地點被抽屜蓋住）
  function clampView(v, vw, vh, W, H, pad = 0) {
    const s = clampScale(v.s, vw, vh, W, H);
    const half = (view) => view / 2 / s; // 視窗的一半，換成地圖單位
    const cx = W * s <= vw ? W / 2 : Math.min(W - half(vw), Math.max(half(vw), v.cx));
    const cy = H * s <= vh - pad ? H / 2 + pad / 2 / s : Math.min(H - half(vh) + pad / s, Math.max(half(vh), v.cy));
    return { s, cx, cy };
  }
  // 選了的地點對準抽屜上面露出來的那一塊的中間（倍率照舊），再夾住
  const focusView = (v, p, vw, vh, W, H, pad = 0) => clampView({ s: v.s, cx: p[0], cy: p[1] + pad / 2 / v.s }, vw, vh, W, H, pad);
  // 視窗裡 (px, py) 底下的地圖座標；反過來，倍率 s 時要讓地圖座標 m 落在 (px, py)，中心該在哪
  const mapPoint = (v, px, py, vw, vh) => [v.cx + (px - vw / 2) / v.s, v.cy + (py - vh / 2) / v.s];
  const pinView = (s, m, px, py, vw, vh) => ({ s, cx: m[0] - (px - vw / 2) / s, cy: m[1] - (py - vh / 2) / s });
  // 以視窗裡 (px, py) 為準縮放：縮放前後那一點底下的地圖座標不變（碰到地圖邊緣被夾住時例外）
  function zoomAt(v, factor, px, py, vw, vh, W, H, pad = 0) {
    const s = clampScale(v.s * factor, vw, vh, W, H);
    return clampView(pinView(s, mapPoint(v, px, py, vw, vh), px, py, vw, vh), vw, vh, W, H, pad);
  }
  // 地點點擊區的半徑（地圖單位）：螢幕上至少約 22px；上限 34，最近的兩個地點相距 68.6，再大會互相蓋住
  const hitRadius = (s) => Math.min(34, Math.max(22, 22 / s));

  // ── 輿圖的手勢（W16）──
  // 地圖照原本的像素大小放在固定高度的框裡，用 transform 平移、縮放（不改 viewBox：手勢中每一幀重描整張山水，手機會卡）。
  // 一指或滑鼠左鍵拖移、雙指縮放、滾輪縮放；按下到放開都沒移超過 8px、也從沒有第二指，才算點了一下（選地點）。
  // pointermove／up 掛在 document：重畫換掉了地圖框，手勢也接得下去（mapReady 會把指標抓回新的框）
  const TAP_SLOP = 8;
  const grip = { pts: new Map(), tap: null, ref: null, g: null, pad: 0, frame: 0 }; // 按著的指標（id → [x, y]）、點一下的候選、起點、排好的那一幀
  const mapHeld = () => grip.pts.size > 0;
  let mapBox = null; // 上次套用時的地圖框大小 [寬, 高]：大小變了而原本是整張，就維持整張
  let glideTimer = 0;

  // 地圖框與地圖的大小、框的內緣在畫面上的位置；地圖還沒畫出來（或框沒有大小）回 null
  function mapGeom(wrap) {
    const svg = wrap && wrap.querySelector(".tx-world-map > svg");
    const vb = svg && svg.viewBox && svg.viewBox.baseVal;
    if (!vb || !vb.width || !vb.height || !wrap.clientWidth || !wrap.clientHeight) return null;
    const r = wrap.getBoundingClientRect();
    return { wrap, svg, world: svg.parentNode && svg.parentNode.style ? svg.parentNode : svg, vw: wrap.clientWidth, vh: wrap.clientHeight, W: vb.width, H: vb.height,
      x0: r.left + wrap.clientLeft, y0: r.top + wrap.clientTop };
  }
  // 地點的中心：照底圖的清單（記號還沒畫出來也找得到）
  const placeXY = (id) => {
    const p = id && S.mapBase && S.mapBase.places.find((x) => x.id === id);
    return p ? [p.x, p.y] : null;
  };
  // 所在地：在路上用疊層給的「你」那一點，否則用所在的地點，都找不到就用地圖中心
  const herePoint = (g) => {
    const j = S.mapState && S.mapState.journey;
    return (j ? [j.x, j.y] : null) || placeXY(S.mapState && S.mapState.here) || [g.W / 2, g.H / 2];
  };

  // 把 S.mapView 夾住、套到地圖上；glide：按鈕、下拉選單的移動滑一下（≤150ms），手勢與滾輪中不滑
  function applyMapView(glide = false, g = mapGeom(document.getElementById("map"))) {
    if (!g) return;
    if (S.mapLayer === "world" && S.mapBase && S.mapBase.world) { applyWorldView(glide, g); return; }
    if (!S.mapView) return;
    const { wrap, vw, vh, W, H } = g;
    // 地圖框大小變了（轉向、拉視窗，也可能是在別的分頁時變的）而原本是整張：維持整張
    if (mapBox && (mapBox[0] !== vw || mapBox[1] !== vh) && S.mapView.s <= fitScale(mapBox[0], mapBox[1], W, H) + 1e-9) {
      S.mapView = { ...S.mapView, s: fitScale(vw, vh, W, H) };
    }
    mapBox = [vw, vh];
    const v = (S.mapView = clampView(S.mapView, vw, vh, W, H, mapHeld() && grip.g === g ? grip.pad : mapPad()));
    clearTimeout(glideTimer);
    wrap.classList.toggle("glide", glide);
    if (glide) glideTimer = setTimeout(() => wrap.classList.remove("glide"), 200);
    const shift = `translate(${vw / 2 - v.cx * v.s}px, ${vh / 2 - v.cy * v.s}px) scale(${v.s})`;
    // 位移與倍率套在兩張 svg 的外框（.tx-world-map）上，不套在 svg 本身：svg 根元素的 transform 一變，Chrome 要照新的倍率重排
    // 每一個 <text>（約 150 個地名、每一幀 Layout 150/1613），再重畫整張底圖；套在外框上拖移只動合成層（Joy 2026-10-17「輿圖還是很 lag」）
    g.world.style.transform = shift;
    // 到頂、到底那一顆按不下去（看得出已經到頭了）
    const zin = document.querySelector('.map-ctl [data-step="in"]'), zout = document.querySelector('.map-ctl [data-step="out"]');
    if (zin) zin.disabled = v.s >= MAP_MAX - 1e-9;
    if (zout) zout.disabled = v.s <= fitScale(vw, vh, W, H) + 1e-9;
    // 倍率變了一成上下：字與圓盤照新的倍率重畫（拖移不重畫）。手指還捏著時不重畫：重畫一次要重建三百個記號、重排整張（節流到六倍
    // 約 100ms），捏合中重畫就頓一下；字跟著圖一起放大縮小，放開時（gripEnd）照一成補畫
    if (!S.marksS || (!mapHeld() && Math.abs(v.s - S.marksS) / v.s > 0.08)) scheduleMarks();
  }

  // 天下圖的取景：每次照地圖框現在的大小重算（轉向、拉視窗、版圖變化把框縮到抽屜上面都跟著），不存進 S.mapView（那是區圖的）
  function applyWorldView(glide, g) {
    const tl = S.mapMode === "timeline", pad = deskMap() || tl ? 0 : WORLD_PAD;
    const v = (S.worldView = worldFit(g.vw, g.vh, S.mapBase.world.frame, pad, tl ? WORLD_TL_TOP : WORLD_TOP, g.W, g.H));
    clearTimeout(glideTimer);
    g.wrap.classList.toggle("glide", glide);
    if (glide) glideTimer = setTimeout(() => g.wrap.classList.remove("glide"), 200);
    g.world.style.transform = `translate(${g.vw / 2 - v.cx * v.s}px, ${g.vh / 2 - v.cy * v.s}px) scale(${v.s})`;
    if (!S.marksS || Math.abs(v.s - S.marksS) / v.s > 0.02) scheduleMarks();
  }
  // 這次載入網頁後第一次打開輿圖的倍率，對準所在地：手機照原尺寸；桌機照地圖區的寬讓地圖佔滿左邊整塊（FB-263：1920 寬時地圖區
  // 約 1545px，照原尺寸只畫 900px、旁邊空一大片），最多 MAP_MAX。都不給整張——整張只有約 0.37 倍，地名剩 5px 上下（E2／FB-012）
  const firstScale = (vw, vh, W, H, phone) => (phone ? 1 : Math.min(MAP_MAX, Math.max(fitScale(vw, vh, W, H), vw / W)));

  const mapWired = new WeakSet(); // 已經掛好手勢監聽的地圖框
  // 輿圖頁每次畫好（afterPage）：第一次打開就決定視圖，之後照舊套用；掛上這個框自己的監聽
  function mapReady() {
    const wrap = document.getElementById("map");
    if (!wrap) return;
    mapFrame();
    // 天下圖的總覽只有收著那一行與拉開的卡（區圖那一層的 "home" 換成收著）
    if (S.mapLayer === "world" && S.mapMode === "overview" && !["min", "half", "full"].includes(S.mapDrawer)) S.mapDrawer = "min";
    setMapDrawer(S.mapDrawer);
    // 手勢的監聽都掛在捕獲階段：不冒泡的事件（例如測試用 new PointerEvent 送的）也收得到。地圖框常駐（FB-324）：同一個框只掛一次
    if (!mapWired.has(wrap)) {
      mapWired.add(wrap);
      wrap.addEventListener("pointerdown", gripDown, true);
      wrap.addEventListener("wheel", mapWheel, { passive: false, capture: true });
      // 舊版 iOS Safari 的捏合手勢、拖到地圖上的字開始原生拖曳，都擋掉
      for (const t of ["gesturestart", "gesturechange", "dragstart"]) wrap.addEventListener(t, (ev) => ev.preventDefault());
    }
    for (const id of grip.pts.keys()) {
      try { wrap.setPointerCapture(id); } catch (e) { /* 那一指已經放開了 */ }
    }
    const g = mapGeom(wrap);
    if (g && !S.mapView) {
      const [cx, cy] = herePoint(g);
      S.mapView = { s: firstScale(g.vw, g.vh, g.W, g.H, !!(PHONE && PHONE.matches)), cx, cy };
    }
    applyMapView(false, g);
    drawMarks();
    bakeLater();
    drawerGrab();
    if (S.mapFocus) { mapCenterOn(S.mapFocus); S.mapFocus = null; } // 江湖頁的小地圖點了某一處（設計第八節）
  }

  function gripDown(ev) {
    if (ev.button !== 0 || ev.target.closest(".map-ctl")) return; // 只收滑鼠左鍵、觸控、筆；角落的按鈕照常按
    if (S.mapLayer === "world") return; // 天下圖不拖不縮（設計 4.1）：點一州照一般的點擊（data-act="world-region"）
    if (grip.pts.has(ev.pointerId)) gripEnd(); // 同一個指標又按下：上一次沒收到放開（例如在視窗外放開），重新來過
    if (grip.pts.size >= 2) return; // 第三指不管
    gripFlush();
    const wrap = ev.currentTarget;
    try { wrap.setPointerCapture(ev.pointerId); } catch (e) { /* 合成的事件抓不住；放開照樣由 document 收 */ }
    grip.pts.set(ev.pointerId, [ev.clientX, ev.clientY]);
    grip.tap = grip.pts.size === 1 ? { id: ev.pointerId, x: ev.clientX, y: ev.clientY, target: ev.target } : null;
    wrap.classList.remove("glide");
    // 拖著的手形游標只給滑鼠、筆（FB-322）：cursor 會一路繼承下去，換一次整棵地圖約 1,550 個元素重算樣式；觸控看不到游標，點一下不必付
    if (ev.pointerType !== "touch") wrap.classList.add("grabbing");
    if (!grip.tap) wrap.classList.add("moving");
    gripBase();
  }

  // 指標數變了（按下、放開一指）：從現在的位置與視圖重新記起點。一指記上一幀的位置（拖移）；
  // 兩指記開始時的視圖、兩指距離，以及兩指中點底下的地圖座標（之後要一直跟著中點走）
  function gripBase() {
    const pts = [...grip.pts.values()];
    const g = (grip.g = mapGeom(document.getElementById("map")));
    grip.pad = mapPad();
    grip.ref = null;
    if (!g || !S.mapView || !pts.length) return;
    if (pts.length === 1) { grip.ref = { at: pts[0] }; return; }
    const [[ax, ay], [bx, by]] = pts;
    grip.ref = { v: S.mapView, d: Math.max(1, Math.hypot(bx - ax, by - ay)), m: mapPoint(S.mapView, (ax + bx) / 2 - g.x0, (ay + by) / 2 - g.y0, g.vw, g.vh) };
  }

  // 一幀套用一次（同一幀的多次移動合併）
  function gripStep() {
    grip.frame = 0;
    // 地圖框的大小與位置在按下時量好（gripBase）：每一幀量一次會逼瀏覽器先把上一幀的位移排好版
    const g = grip.g && grip.g.wrap.isConnected ? grip.g : mapGeom(document.getElementById("map"));
    const ref = grip.ref;
    const pts = [...grip.pts.values()];
    if (!g || !ref || !S.mapView) return;
    if (pts.length === 1 && ref.at) {
      // 地圖跟著手指（游標）走
      const [x, y] = pts[0];
      const v = S.mapView;
      S.mapView = clampView({ s: v.s, cx: v.cx - (x - ref.at[0]) / v.s, cy: v.cy - (y - ref.at[1]) / v.s }, g.vw, g.vh, g.W, g.H, grip.pad);
      ref.at = [x, y];
    } else if (pts.length === 2 && ref.m) {
      const [[ax, ay], [bx, by]] = pts;
      const s = clampScale(ref.v.s * Math.hypot(bx - ax, by - ay) / ref.d, g.vw, g.vh, g.W, g.H);
      S.mapView = clampView(pinView(s, ref.m, (ax + bx) / 2 - g.x0, (ay + by) / 2 - g.y0, g.vw, g.vh), g.vw, g.vh, g.W, g.H, grip.pad);
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
    grip.tap = grip.ref = grip.g = null;
    grip.frame = 0;
    const wrap = document.getElementById("map");
    for (const c of ["grabbing", "moving"]) if (wrap && wrap.classList.contains(c)) wrap.classList.remove(c); // 有才拿（觸控點一下兩樣都沒有）
    if (S.mapView && S.marksS && Math.abs(S.mapView.s - S.marksS) / S.mapView.s > 0.08) scheduleMarks(); // 捏合中沒畫的那一截補上
  }

  // 在地圖上點了一下：選那個地點、抽屜換成它（不問伺服器，疊層裡都有），視圖不動；點到空白收起
  function mapPick(target) {
    const loc = target && target.closest && target.closest("[data-loc]");
    if (!loc) {
      if (S.mapMode === "place") { S.mapSel = null; S.mapMode = "overview"; setMapDrawer("home"); redrawDrawer(); drawSel(); }
      return;
    }
    S.mapSel = loc.getAttribute("data-loc");
    if (S.mapMode !== "timeline") {
      S.mapMode = "place";
      if (["home", "min", "rest"].includes(S.mapDrawer)) setMapDrawer("peek");
    }
    redrawDrawer();
    drawSel();
    keepSelVisible(); // 點的地點在抽屜會蓋住的地方（下緣）：對準露出來的那一塊；其餘照舊不動
  }

  // 滾輪以游標為準縮放；觸控板雙指捏合在 Chrome／Edge 是帶 ctrlKey 的 wheel，一樣處理（也因此擋掉瀏覽器自己的整頁放大）
  function mapWheel(ev) {
    ev.preventDefault();
    if (S.mapLayer === "world") return; // 天下圖不縮放
    const g = mapGeom(ev.currentTarget);
    if (!g || !S.mapView) return;
    const dy = ev.deltaY * (ev.deltaMode === 1 ? 16 : ev.deltaMode === 2 ? g.vh : 1);
    S.mapView = zoomAt(S.mapView, Math.exp(-dy * 0.0015), ev.clientX - g.x0, ev.clientY - g.y0, g.vw, g.vh, g.W, g.H, mapPad());
    applyMapView(false, g);
  }

  // 角落的按鈕：以視窗中心縮放 1.5 倍
  function mapZoom(step) {
    const g = mapGeom(document.getElementById("map"));
    if (!g || !S.mapView) return;
    S.mapView = zoomAt(S.mapView, step === "out" ? 1 / 1.5 : 1.5, g.vw / 2, g.vh / 2, g.vw, g.vh, g.W, g.H, mapPad());
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
  // 找地點、今天去哪裡出陣點了一個地點：倍率照舊，中心移到那個地點（它可能在視窗外）
  function mapCenterOn(id) {
    const g = mapGeom(document.getElementById("map"));
    const p = g && placeXY(id);
    if (!p || !S.mapView) return;
    S.mapView = focusView(S.mapView, p, g.vw, g.vh, g.W, g.H, mapPad()); // 對準抽屜上面露出來的那一塊
    applyMapView(true, g);
  }

  // ── 見聞 ──
  // 第一季的傳聞分四層（傳聞分層設計第二節）：天下大事、陣營軍情、所在大區、個人線索，各一張卡。
  // 標題是伺服器給的字（這裡跳脫），內容是伺服器轉好、跳脫過的 HTML；開關關著時沒有 rumor_layers，照舊畫一整張 rumors
  function rumorLayersHtml(layers) {
    return layers.map((l) => `<div class="card rumor-layer" data-layer="${esc(l.id)}"><h3>${esc(l.title)}</h3>${l.body}</div>`).join("");
  }

  // 見聞的「行狀」（玩家傳第一批，Game.annals_view）：新的在上；字都是伺服器存的原文，這裡跳脫。份量 4 以上的加一點朱紅
  function annalsHtml(a) {
    if (!a) return '<p class="muted">載入中…</p>';
    if (!a.on) return '<div class="card"><p class="muted">這一季不記行狀。</p></div>';
    const head = `<div class="card annals-head"><h3>${esc(a.name)}・行狀</h3><p class="muted">這一季值得寫進傳裡的事。季末收季時，會照這些寫成一篇《${esc(a.name)}傳》。</p></div>`;
    // 歷季列傳（第二批）：存著的每一季一本，排在這一季的行狀上面
    const books = (a.books || []).length ? `<div class="zh-books"><h3>歷季列傳</h3>${a.books.map((b) =>
      zhuanEntry(b, `第 ${Number(b.season)} 季・${b.written ? (b.public ? "已公開" : "已成篇") : "尚未成篇"}`)).join("")}</div>` : "";
    if (!a.rows.length) return head + books + '<div class="card"><p class="muted">還沒有記下什麼。上陣打一場大戰、跟英雄人物說幾句話，這裡就會有了。</p></div>';
    const row = (r) => `<li class="annal${r.weight >= 4 ? " heavy" : ""}">
        <div class="annal-meta"><span class="annal-kind">${esc(r.kind)}</span><span>${esc(r.when)}${r.place ? `・${esc(r.place)}` : ""}</span></div>
        <p class="annal-text">${esc(r.text)}</p>
        ${r.quote ? `<p class="annal-quote">你：「${esc(r.quote)}」</p>` : ""}
        ${r.reply ? `<p class="annal-reply">${r.figure ? `<b>${esc(r.figure)}</b>：` : ""}${esc(r.reply)}</p>` : ""}
      </li>`;
    return head + books + `<ol class="annals card">${a.rows.slice().reverse().map(row).join("")}</ol>`;
  }

  // 見聞的「榜單」（leaderboard.view）：上面一排六張榜的籤，一次看一張（S.board，預設第一張）；前十名，你在榜上標出來，
  // 不在前十名時底下多一行你排第幾。名號與那一段都是伺服器給的原文，這裡跳脫
  // 榜單的神器譜（Joy 2026-10-17 從江湖史搬過來）：不排名，照季分段、新的一季在前；一筆一列，名字一行、種類屬性與在誰手上一行
  function bookRows(book) {
    if (!book.length) return '<p class="muted">還沒有人打出神器。</p>';
    let out = "", season = null;
    for (const r of book) {
      if (r.season !== season) { out += `${season === null ? "" : "</ul>"}<p class="book-season">第 ${Number(r.season)} 季</p><ul class="board-book">`; season = r.season; }
      out += `<li><b>${esc(r.name)}</b><small>${esc(r.text)}</small></li>`;
    }
    return out + "</ul>";
  }
  function boardsHtml(b) {
    if (!b) return '<p class="muted">載入中…</p>';
    const list = b.boards || [];
    if (!list.length) return '<div class="card"><p class="muted">還沒有榜單。</p></div>';
    const cur = list.find((x) => x.id === S.board) || list[0];
    const tabs = `<div class="board-tabs">${list.map((x) => `<button class="${x.id === cur.id ? "on" : ""}" data-act="board" data-board="${esc(x.id)}">${esc(x.title)}</button>`).join("")}</div>`;
    const row = (r) => `<li class="board-row${r.rank <= 3 ? " podium" : ""}${r.you ? " you" : ""}"><span class="board-rank">${Number(r.rank)}</span><span class="board-name">${esc(r.name)}</span><span class="board-text">${esc(r.text)}${r.sub ? `<small>${esc(r.sub)}</small>` : ""}</span></li>`;
    if (cur.book) return tabs + `<div class="card board"><h3>${esc(cur.title)}</h3><p class="muted board-note">${esc(cur.note)}</p>${bookRows(cur.book)}</div>`;
    const rows = cur.rows.length ? `<ol class="board-list">${cur.rows.map(row).join("")}</ol>` : '<p class="muted">尚無人留名。</p>';
    const mine = cur.mine ? `<p class="board-mine">你：第 ${Number(cur.mine.rank)} 名・${esc(cur.mine.text)}</p>` : "";
    return tabs + `<div class="card board"><h3>${esc(cur.title)}</h3><p class="muted board-note">${esc(cur.note)}</p>${rows}${mine}</div>`;
  }

  // ── 名帖（Joy 2026-10-19：抱拳改成互贈名帖；一張畫布當自己的標籤，頭銜系統照存檔算、按一下刷新，再留一句自題）──
  // 名帖固定是紙色、不跟深淺色走（墨、朱砂、石青三色要在紙上看得清楚；跟 mingtie.INKS 同一份）。
  // 筆劃是 [墨色, 筆粗, x0, y0, x1, y1, …]，座標在 300×400 的畫布上（mingtie.WIDTH／HEIGHT）。字待 joy 潤
  const MT_INKS = ["#24211d", "#b23a2a", "#2f5d78"];
  const MT_PENS = [3, 10];
  const mtPolyline = (s) => (s.length >= 6
    ? `<polyline points="${s.slice(2).join(" ")}" stroke="${MT_INKS[s[0]] || MT_INKS[0]}" stroke-width="${MT_PENS[s[1]] || MT_PENS[0]}"/>`
    : `<circle cx="${s[2]}" cy="${s[3]}" r="${(MT_PENS[s[1]] || MT_PENS[0]) / 2}" fill="${MT_INKS[s[0]] || MT_INKS[0]}"/>`);
  const mtStrokesSvg = (strokes) => (strokes || []).map(mtPolyline).join("");
  // 一張名帖：畫在底下、右上直書名號、名號底下一方朱印（名號前三個字＋印）、下緣頭銜與自題。cls：thumb（玩家卡縮圖、名帖匣）、zoom、edit
  function mtSeal(name) {
    const chars = [...String(name || "")].slice(0, 3);
    if (chars.length < 3) chars.push("之"); // 兩個字的名號寫「某某之印」
    while (chars.length < 3) chars.push("");
    // 2×2 一格一字，照印文的讀法：右行由上而下、再左行
    return `<span class="mt-seal" aria-hidden="true">${[chars[2], chars[0], "印", chars[1]].map((ch) => `<i>${esc(ch)}</i>`).join("")}</span>`;
  }
  function mtCardHtml(card, name, cls = "", pad = false) {
    const c = card || { strokes: [], titles: [], motto: "" };
    return `<div class="mt-card ${cls}">
      <svg class="mt-ink${pad ? " mt-pad" : ""}" ${pad ? 'id="mt-pad" ' : ""}viewBox="0 0 300 400" preserveAspectRatio="none" fill="none" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${mtStrokesSvg(c.strokes)}</svg>
      <div class="mt-name">${esc(name)}</div>${mtSeal(name)}
      <div class="mt-foot">${c.titles && c.titles.length ? `<div class="mt-titles">${c.titles.map((t) => `<span>${esc(t)}</span>`).join("")}</div>` : ""}<p class="mt-motto">${c.motto ? `「${esc(c.motto)}」` : ""}</p></div>
      ${c.hidden ? '<p class="mt-hidden">這一張的畫與題字看不到了。</p>' : ""}
    </div>`;
  }

  // 放大看一張（玩家卡的縮圖、名帖匣裡收到的）：別人的那一張底下有「檢舉」；看不到的那一張不能再檢舉
  function mtZoomHtml() {
    const z = S.mtZoom;
    const me = S.main && S.main.status && S.main.status.name;
    const can = !z.card.hidden && z.name !== me;
    return `<div class="mt-zoom-layer" data-act="mt-unzoom" role="dialog" aria-label="${esc(z.name)}的名帖">
      <div class="mt-zoom-box">${mtCardHtml(z.card, z.name, "zoom")}${z.when ? `<p class="mt-when">${esc(z.when)}</p>` : ""}
        <div class="row"><button class="btn ghost small" data-act="mt-unzoom">收起</button>${can ? '<button class="btn ghost small mt-report" data-act="mt-report">檢舉這一張</button>' : ""}</div></div></div>`;
  }
  async function mtReport() {
    const z = S.mtZoom;
    if (!z) return;
    ask(`檢舉${z.name}的這一張名帖：你不會再看到它的畫與題字；被檢舉夠多次，大家都看不到，管理者會看。確定？`, "檢舉", async () => {
      await busy(async () => {
        const r = await api("/api/mingtie/report", { name: z.name, version: z.card.version });
        if (r.mingtie) S.mingtie = r.mingtie;
        S.mtZoom = null;
        toast((r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim() || "已檢舉。");
        render();
        if (S.peer && S.peer.name === z.name) refreshPeer();
      });
    });
  }

  async function loadMingtie() {
    S.mingtie = await api("/api/mingtie");
    if (S.tab === "news" && S.news === "mingtie") renderPage();
  }

  // 見聞「名帖匣」：自己那一張（製作或修改）、今天還能定稿幾次遞幾張、收到的那幾張（新的在前，點了放大）
  function mingtieBoxHtml(m) {
    if (!m) return '<p class="muted">載入中…</p>';
    const me = S.main.status.name;
    const mine = m.mine
      ? `<div class="mt-mine"><div data-act="mt-zoom-mine">${mtCardHtml(m.mine, me, "mine")}</div>`
      : `<div class="mt-mine empty"><p>你還沒有名帖。做一張，就能在玩家卡上跟人互換。</p>`;
    return `<div class="card mt-box-head">${mine}
        <div class="mt-mine-side"><button class="btn primary" data-act="mt-edit"${m.made_left ? "" : " disabled"}>${m.mine ? "修改名帖" : "製作名帖"}</button>
          <p class="muted">今天還能定稿 ${m.made_left} 次、遞出 ${m.sent_left} 張。不花銀兩。</p></div></div></div>
      <p class="report-group">收到的名帖（${m.box.length}）</p>
      ${m.box.length ? `<div class="mt-grid">${m.box.map((x, i) => `<button class="mt-cell" data-act="mt-zoom-box" data-i="${i}">${mtCardHtml(x.card, x.name, "thumb")}<small>${esc(x.name)}</small></button>`).join("")}</div>`
        : '<p class="muted">還沒收到誰的名帖。在「此地還有」點人的名字，玩家卡上可以遞名帖。</p>'}`;
  }

  // 製作名帖（全螢幕一層）：畫布、三色兩筆、上一筆、清空、現成的畫；頭銜從掙到的裡面挑（刷新＝隨機換一批）；自題一句；定稿
  function mtEditOpen() {
    const m = S.mingtie;
    if (!m) return;
    const pool = m.pool || [];
    const mine = m.mine || { strokes: [], titles: [], motto: "" };
    const titles = mine.titles.filter((t) => pool.includes(t));
    S.mtEdit = { strokes: mine.strokes.map((s) => s.slice()), titles: titles.length ? titles : pool.slice(0, m.limits.titles), motto: mine.motto, ink: 0, pen: 0, note: "" };
    render();
  }
  function mtPoints(strokes) { return strokes.reduce((n, s) => n + (s.length - 2) / 2, 0); }
  function mtEditHtml() {
    const E = S.mtEdit, m = S.mingtie, L = m.limits;
    const me = S.main.status.name;
    const pts = mtPoints(E.strokes);
    const chip = (t) => `<button class="mt-chip${E.titles.includes(t) ? " on" : ""}" data-act="mt-title" data-t="${esc(t)}">${esc(t)}</button>`;
    return `<div class="mt-layer" role="dialog" aria-label="製作名帖">
      <div class="mt-bar"><button class="book-back" data-act="mt-close">‹ 返回</button><b>製作名帖</b><span>今天還能定稿 ${m.made_left} 次</span></div>
      <div class="mt-edit-col">
        <div class="mt-stage">${mtCardHtml({ strokes: E.strokes, titles: E.titles, motto: E.motto }, me, "edit", true)}</div>
        <div class="mt-tools">
          ${MT_INKS.map((c, i) => `<button class="mt-ink-btn${E.ink === i ? " on" : ""}" data-act="mt-ink" data-i="${i}" style="--c:${c}" aria-label="${esc(L.ink_names[i] || "")}"><i></i>${esc(L.ink_names[i] || "")}</button>`).join("")}
          ${["細", "粗"].map((n, i) => `<button class="mt-pen-btn${E.pen === i ? " on" : ""}" data-act="mt-pen" data-i="${i}">${n}</button>`).join("")}
        </div>
        <div class="mt-tools"><button class="btn ghost small" data-act="mt-undo"${E.strokes.length ? "" : " disabled"}>上一筆</button><button class="btn ghost small" data-act="mt-clear"${E.strokes.length ? "" : " disabled"}>清空</button>
          <select class="input mt-preset" id="mt-preset" aria-label="現成的畫"><option value="">現成的畫…</option>${(m.presets || []).map((p) => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join("")}</select></div>
        <p class="muted mt-count" id="mt-count">${E.strokes.length}／${L.strokes} 筆・墨 ${pts}／${L.points}</p>
        <div class="mt-sec"><span>頭銜（挑 ${L.titles} 個以內）</span><button class="btn ghost small" data-act="mt-shuffle"${m.pool.length > L.titles ? "" : " disabled"}>刷新頭銜</button></div>
        <div class="mt-chips">${m.pool.length ? m.pool.map(chip).join("") : '<p class="muted">還沒掙到頭銜。名聲、陣營、榜單、絕學……江湖上做出點事，這裡就有。</p>'}</div>
        <div class="mt-sec"><span>自題一句（${L.motto} 字內，可以不寫）</span></div>
        <input class="input" id="mt-motto" maxlength="${L.motto}" value="${esc(E.motto)}" placeholder="例：一劍霜寒十四州" aria-label="自題一句">
        <p class="form-msg" id="mt-note" role="alert">${esc(E.note || "")}</p>
        <button class="btn primary mt-go" data-act="mt-save"${m.made_left ? "" : " disabled"}>定稿</button>
      </div></div>`;
  }
  // 工具列按了只換那一層（不重畫底下的頁面），畫布照 S.mtEdit 重新掛手勢
  function mtEditRedraw() {
    const old = document.querySelector(".mt-layer");
    if (!old || !S.mtEdit) return;
    const top = old.querySelector(".mt-edit-col")?.scrollTop || 0;
    old.insertAdjacentHTML("afterend", mtEditHtml());
    old.remove();
    const col = document.querySelector(".mt-layer .mt-edit-col");
    if (col) col.scrollTop = top;
    mtPadReady();
  }
  function mtPadReady() {
    const pad = document.getElementById("mt-pad");
    const E = S.mtEdit;
    if (!pad || !E) return;
    const L = S.mingtie.limits;
    let cur = null;
    const at = (ev) => {
      const r = pad.getBoundingClientRect();
      return [Math.max(0, Math.min(L.width, Math.round(((ev.clientX - r.left) / r.width) * L.width))),
        Math.max(0, Math.min(L.height, Math.round(((ev.clientY - r.top) / r.height) * L.height)))];
    };
    const paint = () => {
      pad.innerHTML = mtStrokesSvg(cur ? [...E.strokes, cur] : E.strokes);
      const n = document.getElementById("mt-count");
      if (n) n.textContent = `${E.strokes.length + (cur ? 1 : 0)}／${L.strokes} 筆・墨 ${mtPoints(cur ? [...E.strokes, cur] : E.strokes)}／${L.points}`;
    };
    pad.addEventListener("pointerdown", (ev) => {
      ev.preventDefault();
      if (E.strokes.length >= L.strokes || mtPoints(E.strokes) >= L.points) { E.note = "畫布上的墨已經滿了：按「上一筆」或「清空」再畫。"; const n = document.getElementById("mt-note"); if (n) n.textContent = E.note; return; }
      pad.setPointerCapture(ev.pointerId);
      cur = [E.ink, E.pen, ...at(ev)];
      paint();
    });
    pad.addEventListener("pointermove", (ev) => {
      if (!cur) return;
      ev.preventDefault();
      const [x, y] = at(ev);
      const lx = cur[cur.length - 2], ly = cur[cur.length - 1];
      if (Math.abs(x - lx) + Math.abs(y - ly) < 4) return; // 太密的點不收：一張名帖的墨有上限
      if (mtPoints(E.strokes) + (cur.length - 2) / 2 >= L.points) return;
      cur.push(x, y);
      paint();
    });
    const end = () => {
      if (!cur) return;
      E.strokes.push(cur);
      cur = null;
      mtEditRedraw();
    };
    pad.addEventListener("pointerup", end);
    pad.addEventListener("pointercancel", end);
  }
  async function mtSave() {
    const E = S.mtEdit;
    if (!E) return;
    const before = S.mingtie.mine ? S.mingtie.mine.version : 0;
    await busy(async () => {
      const r = await api("/api/mingtie/save", { strokes: E.strokes, titles: E.titles, motto: E.motto });
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      if (r.mingtie) S.mingtie = r.mingtie;
      if (r.mingtie && r.mingtie.mine && r.mingtie.mine.version > before) {
        S.mtEdit = null;
        toast(text || "名帖定稿了。");
        render();
      } else {
        E.note = text;
        mtEditRedraw();
      }
    });
  }

  // 見聞的籤（NEWS）：「形勢」只有〈天下形勢〉開著的季（main.xingshi）才畫。九顆在 375 寬一排放不下（每顆 13px 的字、四 px 的內距，九顆
  // 要約 362px，那一欄只有 343），排成兩排（.wrap：上五顆、下四顆各自撐滿，字照預設的大小，不橫捲、不藏；領地爭奪第三批 A，計畫 6.4）。
  // 關著的季照舊一排八顆，一個像素都不變
  function newsSegHtml(m) {
    const tabs = NEWS.filter((n) => n.id !== "xingshi" || (m && m.xingshi));
    return `<div class="seg news-seg${tabs.length > 8 ? " wrap" : ""}">${tabs.map((n) => `<button class="${S.news === n.id ? "on" : ""}" data-act="news" data-news="${n.id}">${n.name}</button>`).join("")}</div>`;
  }

  // 見聞「形勢」（領地爭奪第三批 A，企劃者挑乙）：一篇一行（「是日：…」＋時刻），最新一篇攤開、其餘點了攤開（<details>）；攤開、收起記在
  // S.xingshiOpen（篇次 → 開著沒），重畫照樣。文章是伺服器給的純文字（模型寫的或照固定段拼的，看不出差別），一段一個 <p>、照字跳脫。字待 joy 潤
  const XS_EMPTY = "天下尚無定論。";
  const XS_PENDING = "今日的形勢，史官還在落筆。";
  function xingshiParas(text) {
    return String(text || "").split(/\n+/).filter((p) => p.trim()).map((p) => `<p>${esc(p.trim())}</p>`).join("");
  }
  function xingshiHtml(x) {
    if (!x) return '<p class="muted">載入中…</p>';
    if (!x.on) return '<div class="card"><p class="muted">這一季沒有〈天下形勢〉。</p></div>';
    const open = S.xingshiOpen || (S.xingshiOpen = new Map());
    const pending = x.pending ? `<p class="muted xs-pending">${XS_PENDING}</p>` : "";
    if (!x.essays.length) return `<div class="card xs-card">${pending || `<p class="muted">${XS_EMPTY}</p>`}</div>`;
    const row = (e, i) => `<details class="xs-essay" data-n="${Number(e.n)}"${(open.has(e.n) ? open.get(e.n) : i === 0) ? " open" : ""}>
        <summary><span class="xs-line">${esc(e.line)}</span><span class="xs-time">${esc(e.time)}</span></summary>
        <div class="xs-body"><p class="xs-title">${esc(e.title)}</p>${xingshiParas(e.essay)}</div></details>`;
    return `<div class="card xs-card">${pending}${x.essays.map(row).join("")}</div>`;
  }

  function pageNews() {
    const seg = newsSegHtml(S.main);
    const m = S.main;
    let body = "";
    if (S.news === "reports") {
      const r = S.reports;
      if (!r) body = '<p class="muted">載入中…</p>';
      else if (S.reportOpen && r.selected != null) body = `<button class="linkish back" data-act="report-list">‹ 全部戰報</button><div class="card report-detail">${gaugeHtml(r.gauge)}${roundBlocks(r.detail, r.gauge, r.selected)}</div>`;
      else if (!r.list.length) body = `<div class="card">${r.detail}</div>`;
      else {
        // 決戰與奪璽單挑另外一組排在最上面，不跟遊歷野怪混在一起（Joy 2026-10-14「這種大事件的決戰不應該跟一般的放在一起被洗掉」）
        const item = (x) => `<button data-act="report" data-id="${x.id}">${esc(x.label)}</button>`;
        const big = r.list.filter((x) => x.big), rest = r.list.filter((x) => !x.big);
        body = (big.length ? `<p class="report-group">大戰</p><div class="list report-big">${big.map(item).join("")}</div>` : "")
          + (rest.length ? `${big.length ? '<p class="report-group">最近的仗</p>' : ""}<div class="list">${rest.map(item).join("")}</div>` : "");
      }
    } else if (S.news === "trends") body = `<div class="card">${m.trends}</div>`;
    else if (S.news === "xingshi") body = xingshiHtml(S.xingshi);
    else if (S.news === "rumors") body = m.rumor_layers ? rumorLayersHtml(m.rumor_layers) : `<div class="card">${m.rumors}</div>`;
    else if (S.news === "chronicle") body = `<div class="card">${m.chronicle}</div>`;
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
        ${genderRow(s)}
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
            ${a && a.divine_out ? `<p class="muted">${esc(a.divine_out)}</p>` : ""}
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
              ${a.xingshi ? `
                <p class="muted">天下形勢（每天 22:00 自動開一篇；測試時立刻照上一篇以來的事開一篇）</p>
                <div class="row wrap"><button class="btn small" data-act="admin" data-op="xingshi_now">現在就開一篇天下形勢</button></div>` : ""}
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
              ${a.fallen && a.fallen.length ? `<div class="row ad-row"><span class="ad-tag">人物</span><select class="input" id="ad-fallen" aria-label="叫回人物">${opts(a.fallen)}</select><button class="btn small" data-act="admin" data-op="revive_figure">叫他回來</button></div>` : ""}
              <div class="row"><button class="btn warn" data-act="admin" data-op="cancel_battle">⚠ 取消決戰</button></div>
              ${a.seal ? sealAdminHtml(a.seal) : ""}
              ${a.mingtie && a.mingtie.length ? mingtieAdminHtml(a.mingtie) : ""}
              <p class="muted">重設密碼（朋友忘記密碼時用；臨時密碼私下告訴他）</p>
              <form id="reset-form"><div class="row"><input class="input" name="target" placeholder="帳號或名號"><input class="input" name="temp" placeholder="臨時密碼"><button class="btn small" type="submit">重設</button></div><p class="form-msg" role="alert"></p></form>` : ""}
          </section>` : ""}
      </div>`;
  }

  // 管理者區「玩家個人劇情」查到的那個人（/api/admin/player，Game.admin_player_choices）：他是誰、召見（發不了的灰掉、寫為什麼）、
  // 能給他的機緣與伏筆片段（沒有就寫一句）。按了照舊先問一次，送的是查到的那個名號（不是欄位裡後來改過的字）
  // 管理者「玉璽」一組（玉璽碎片設計第十二節，admin_choices.seal；碎片關著是 null，不畫）：七片與狀態、強制現世與璽動（下一場）、
  // 指定持有者、強制開單挑（正式伺服器只能掛在剛收場的時刻表決戰上，QA 開關開著才不必）、定結果、取消、隱沒判斷。按了照舊先問一次。字待 joy 潤
  const SEAL_STATES = { held: "懷中", hidden: "未現世", sunk: "不知所蹤" };
  // 被檢舉的名帖（檢舉夠多次、大家都看不到的在前）：撤下＝畫與題字清掉、他再做一張；放回＝照舊給大家看。待 joy 潤
  function mingtieAdminHtml(rows) {
    return `<p class="muted">名帖檢舉</p><div class="mt-admin">${rows.map((x) => `<div class="mt-admin-row">${mtCardHtml(x.card, x.name, "thumb")}
      <div><b>${esc(x.name)}</b><p class="muted">第 ${x.version} 版・${x.count} 人檢舉</p>
      <div class="row wrap"><button class="btn warn small" data-act="admin" data-op="mingtie_remove" data-name="${esc(x.name)}" data-version="${x.version}">撤下</button><button class="btn small" data-act="admin" data-op="mingtie_restore" data-name="${esc(x.name)}" data-version="${x.version}">放回</button></div></div></div>`).join("")}</div>`;
  }

  function sealAdminHtml(s) {
    const label = (x) => (x.state === "held" ? `${x.name}（${x.holder}懷中）` : `${x.name}（${SEAL_STATES[x.state] || x.state}）`);
    const canDuel = s.hung || s.qa;
    const off = s.duel ? "" : " disabled";
    return `<p class="muted">玉璽（效果跟自然發生一樣，公告不寫管理者）</p>
      <div class="row ad-row"><span class="ad-tag">碎片</span><select class="input" id="ad-seal" aria-label="碎片">${s.shards.map((x) => `<option value="${esc(x.id)}">${esc(label(x))}</option>`).join("")}</select></div>
      <div class="row wrap"><button class="btn small" data-act="admin" data-op="seal_emerge"${s.hide ? ' data-hide="1"' : ""}>${s.hide ? "現在藏一片" : "強制現世（下一場）"}</button><button class="btn small" data-act="admin" data-op="seal_stir">強制璽動（下一場）</button></div>
      <div class="row ad-row"><span class="ad-tag">名號</span><input class="input" id="ad-seal-name" placeholder="名號" aria-label="持有者名號"><select class="input" id="ad-seal-state" aria-label="狀態"><option value="held">有主</option><option value="hidden">未現世</option><option value="sunk">隱沒</option></select><button class="btn small" data-act="admin" data-op="seal_assign">指定持有者</button></div>
      <div class="row ad-row"><span class="ad-tag">單挑</span><input class="input" id="ad-seal-factor" type="number" value="1" step="0.1" min="0" max="1" aria-label="局勢係數" style="max-width:76px"><button class="btn small" data-act="admin" data-op="seal_duel"${canDuel ? "" : " disabled"}>強制開單挑</button>${
        !canDuel ? '<span class="muted ad-note">沒有剛收場的決戰可掛</span>' : s.hung ? `<span class="muted ad-note">掛在「${esc(s.where)}」</span>` : ""}</div>
      <div class="row wrap"><button class="btn small" data-act="admin" data-op="seal_fix" data-take="1"${off}>定結果：易主</button><button class="btn small" data-act="admin" data-op="seal_fix" data-take="0"${off}>定結果：不易主</button><button class="btn warn small" data-act="admin" data-op="seal_cancel"${off}>⚠ 取消單挑</button><button class="btn small" data-act="admin" data-op="seal_sink_check">隱沒判斷</button></div>
      ${s.mandate_ok ? `<div class="row wrap"><button class="btn small" data-act="admin" data-op="seal_mandate" data-when="next"${s.mandate ? " disabled" : ""}>蓋天命之季（下一季）</button><button class="btn warn small" data-act="admin" data-op="seal_mandate" data-when="now"${s.mandate === "now" ? " disabled" : ""}>⚠ 這一季立刻蓋章</button>${s.mandate === "next"
        ? '<button class="btn small" data-act="admin" data-op="seal_mandate" data-when="cancel">收回下一季的章</button>' : ""}${
        s.mandate === "now" ? '<span class="muted ad-note">這一季是天命之季</span>' : s.mandate === "next" ? '<span class="muted ad-note">下一季蓋章</span>' : ""}</div>` : ""}`;
  }

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
    // 21 天季的「繼續」（PM 2026-10-19，跟 world.RESUME_SKIP_REAL 一致）；待 joy 潤
    const RESUME_21 = "讓賽季時鐘繼續走：21 天的季的季曆對回現實的星期，暫停期間的大事在這一刻一起發生，季末照原本的日期；排好的決戰照原本的時間開，時間在暫停裡過了的馬上開始集結，確定？";
    return {
      open_season: ["開季：賽季從籌備中正式開始，全服玩家都能行動了。記得排三場大戲與季末的時間（預設在第 6、9、11 週中、第 12 週末），確定？", "確定開季"],
      // 照 Game.admin_end_season 實際做的事寫（只在進行中有效）
      end_season: ["立刻收季：這一季馬上結束、算出結局與武學榜，全服進入休季（之後再按「開啟下一季」）；沒打完的決戰直接收掉、不算結果，確定？", "確定收季"],
      // 照 SqliteWorldStore.next_season 實際做的事寫（只在休季有效）
      next_season: [`開啟下一季（休季才有效）：新的一季立刻開始，同伴全部重獲自由、武學與意境的名字全部釋出（絕學定的名也是）、合成與合併的配方清空、鐵匠鋪的隱藏鑄法換一批、鑄譜與神器重來（神器譜留著）、天機 +1，沒打完的決戰清掉。${
        S.admin && S.admin.next_has_timetable ? "記得排三場大戲與季末的時間（預設在第 6、9、11 週中、第 12 週末）。" : ""}確定？`, "確定開啟下一季"],  // FB-050
      fast_forward: [`時間快轉現實 ${body.hours} 小時的份（全服一起，季曆會跳得更多），確定？`, `快轉 ${body.hours} 小時`],
      // 公告停機時賽季時鐘暫停（Game.admin_pause_clock／admin_resume_clock）；問句待 S1／joy 潤
      // 21 天季（S.admin.season21）多一句、繼續換一句（PM 2026-10-19：季曆對回現實的星期，跟 world.RESUME_SKIP_REAL 一致）；待 joy 潤
      pause_clock: [`暫停賽季時鐘（停機維護前按）：季的時間不走、決戰不推，全服暫時不能行動，畫面照常可看；${
        S.admin && S.admin.season21 ? "21 天的季：繼續時季曆會對回現實的星期，暫停期間的大事在繼續那一刻一起發生。" : ""}做完記得按「繼續」，確定？`, "確定暫停"],
      resume_clock: [S.admin && S.admin.season21 ? RESUME_21 : "讓賽季時鐘繼續走：停的這一段照整個季曆鐘頭往下取整，扣掉的不算進賽季、季末往後延一樣長；停不到一個季曆鐘頭的話什麼都不扣、季末不動；排好的決戰照原本的時間開，時間在暫停裡過了的馬上開始集結，確定？", "確定繼續"],  // 待 joy 潤；跟 world.resume_skip_text 說的一致
      start_battle: [`立刻開戰「${picked("ad-battle")}」：全服一起進入集結，確定？`, "確定開戰"],
      fire: [`觸發「${picked("ad-fire")}」：效果跟自然發生一樣，全服都受影響，確定？`, "確定觸發"],
      push_trend: [`推動大勢「${picked("ad-trend")}」${amount}：全服一起，確定？`, "確定推動"],
      // 時刻表與救場（計畫 T10）
      schedule: [`把「${body.title}」排在現實 ${body.when}：時間到了自動開集結（季末就是收季），確定？`, "確定排定"],
      jump_next: ["跳到下一件大事：全服的季時間一起往前推，到了的大事立刻結算（決戰直接開集結），確定？", "確定跳過去"],
      set_trend: [`把「${picked("ad-front")}」定成 ${body.value}：全服一起，推過門檻照常觸發，確定？`, "確定定戰況"],
      resolve_event: [`定下「${picked("ad-result")}」：照時刻表結算、全服公告，之後不再擲骰，確定？`, "確定定結果"],
      clear_lock: [`清掉「${picked("ad-lock")}」的鎖定：結算時照沒人鎖定擲骰，確定？`, "確定清掉"],
      revive_figure: [`叫「${picked("ad-fallen")}」回來：以一半聲威回到原本的戰線，全服看得到一句天下大事，確定？`, "確定叫回"],
      cancel_battle: ["取消正在集結或開打的決戰：不算勝負，參戰者都會收到通知；時刻表的決戰不會自己再開，要用「定結果」收尾，確定？", "確定取消"],
      // 管理者觸發鈕（企劃者 2026-10-07）：照 Game.admin_issue_orders／admin_rotate_seats 實際做的事寫
      issue_orders: ["立刻發本週軍令：這一週還沒達成的軍令照週一的做法重挑、換掉（它們的進度不算了），各陣營發一則軍情；已經達成的照舊留著、不會再達成一次；下週一照常發令，確定？", "確定重發"],
      rotate_seats: ["立刻輪替第 4 階席次：照上一週的貢獻重排各陣營在任的人、發一則名單軍情；下週一照常再排，確定？", "確定輪替"],
      // 照 Game.admin_xingshi_now 實際做的事寫（領地爭奪第三批 A；待 joy 潤）
      xingshi_now: ["現在就開一篇〈天下形勢〉：照上一篇以來的事開一張單，伺服器在背景請模型寫（寫不出來照固定段），收下那一刻發一則天下大事、記一筆江湖史；還在等的那一篇先照固定段收。每天 22:00 照常再開，確定？", "確定開一篇"],
      start_showdown: [`立刻開「${body.title}」：照時刻表開集結（起點照此刻的戰況），這一場算開過了，排定的時間到了不會再開，確定？`, "確定開戰"],
      summon: [`立刻替 ${body.name} 發召見（${(S.adPlayer && S.adPlayer.summons && S.adPlayer.summons.note) || "下一階"}；不看貢獻與機緣的門檻，其餘照自然發召見的做法），確定？`, "確定發召見"],
      // 情誼型多一句（伺服器算好的 note：情誼補到幾、招募成算、其他話題、換季帶幾成，審查 M-5）
      give_opportunity: [`給 ${body.name} 機緣「${picked("ad-opp")}」：放到這個機緣自然送上門之後的樣子，下一步他就做得了。${
        body.note ? `${body.note}。` : ""}確定？`, "確定給他"],
      give_fragment: [`給 ${body.name} 伏筆片段「${picked("ad-frag")}」：跟自然聽到一樣，記進他的個人線索，確定？`, "確定給他"],
      // 玉璽碎片（玉璽碎片設計第十二節；照 Game.admin_seal_* 實際做的事寫，待 joy 潤）
      seal_emerge: body.hide
        ? ["現在藏一片：略過開季的機率，把選的那一片（還沒現世才行，沒選的照亂數挑）藏進一塊開季中立的區塊；藏在哪裡不公開，要有人在那裡探索才撿得到。這一季已經藏著、或已經現世過一片就不藏，確定？", "確定藏"]
        : ["下一場標了現世的決戰，碎片必定現世（選的那一片還沒現世就是它，否則照亂數挑；得主照常從勝方抽），確定？", "確定"],
      seal_stir: [`下一場標了璽動的決戰，必定牽動「${picked("ad-seal")}」（略過機率、新主保護與次數上限；那一片要有主），確定？`, "確定"],
      seal_assign: [`把「${picked("ad-seal")}」改成${body.state === "held" ? `${body.name}懷中（這一季有新主保護）` : body.state === "sunk" ? "隱沒" : "未現世"}：只改登記，他回來同步時補給他，確定？`, "確定指定"],
      seal_duel: [`立刻對「${picked("ad-seal")}」開一場奪璽單挑，挑戰者 ${body.name}、局勢係數 ${body.factor}（上限照舊）：三分鐘後開打，確定？`, "確定開單挑"],
      seal_fix: [`正在打的奪璽單挑收場時${body.take ? "易主" : "懷璽不失"}（公告照常），確定？`, "確定"],
      seal_cancel: ["取消正在打（或下戰書中）的奪璽單挑：記成未分勝負，碎片留在原主，確定？", "確定取消"],
      mingtie_remove: [`撤下 ${body.name} 的第 ${body.version} 版名帖：畫與自題那一句清掉（頭銜照留），他的江湖紀錄會寫一句，收過這一張的人也看不到了，確定？`, "確定撤下"],
      mingtie_restore: [`放回 ${body.name} 的第 ${body.version} 版名帖：檢舉清掉、大家照舊看得到（檢舉過的人自己那裡照樣藏著），確定？`, "確定放回"],
      seal_sink_check: ["照隱沒的條件現在判一次：只列出下一次換季會沉哪幾片，不改，確定？", "確定"],
      // 蓋章的後果要寫明（審查 I2）：天命之季過後再換季，七片全部散去、每一位持有者都失去碎片
      seal_mandate: body.when === "cancel"
        ? ["收回下一季的天命之季章：七片這一輪都現世過的話，換季時照樣會蓋，確定？", "確定收回"]
        : [body.when === "now"
          ? "這一季立刻蓋上天命之季的章：還沒打的標了璽動的決戰必定牽動碎片、不提前收季，天命之爭排在第 12 週週一 20:00（現實時間落在半夜會盡量挪開，前後的大事擋著挪不開就照原時間、蓋完會說；已經過了就馬上開集結）。這一季的章蓋了就收不回：收季之後再換季，七片全部散去、每一位持有者都失去碎片，確定？"
          : "下一季蓋天命之季的章（不看七片現世過沒）。那一季過後再換季，七片全部散去、每一位持有者都失去碎片；換季之前還收得回，確定？", "確定蓋章"],
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
    if (!typing()) redrawDrawer();
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

  async function loadBoards() {
    S.boards = await api("/api/boards");
    if (S.tab === "news" && S.news === "boards") renderPage();
  }

  async function loadAnnals() {
    S.annals = await api("/api/annals");
    if (S.tab === "news") renderPage();
  }

  async function loadXingshi() {
    S.xingshi = await api("/api/xingshi");
    if (S.tab === "news" && S.news === "xingshi") renderPage();
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
    S.artNote = null; S.mxNote = null; S.meltNote = null;
    S.legendTick = {}; // 破境丹的勾也一起收：回到修練頁時它是真的沒勾（預設不勾）
    S.forgeResult = null; // 上一爐的結果也收起（篩選留著）
    S.forgeMade = null;
    S.book = false; // 武學譜是疊在煉製頁上的一本書：換分頁就闔上
    S.zhuan = null; clearTimeout(zhuanTimer); // 傳也一樣
    S.mtEdit = null; S.mtZoom = null; // 名帖的畫布與放大的那一張也收起
    if (tab !== "map") stopPlay(); // 版圖變化的播放也停
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
    // 探索三選一：字面寫 "explore:"、不讀 EXPLORE_PREFIX（tests/test_sending_web.py 只從 app.js 切等候那一段出來，切不到行動列那邊的常數）
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
    const sent = await busy(async () => {
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
    if (sent && document.querySelector("#sense-pad.brewing")) renderPage(); // 失敗了（伺服器擋下來、連不上）：畫布還原，那一筆留著
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
    if (id === SAY_OPTION) { // 自己說：先叫出輸入框，寫好再送（見 sayLine）
      S.saying = true;
      renderPage();
      const input = document.querySelector("#say-form .input");
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
        S.wheelSel = null; // 收起展開的移動
        applyMain(r.main);
        if (id.startsWith("bounty:give:")) boardHanded(id, shopBefore); // 店面的懸賞榜：交差了蓋朱印（第四節）
        window.scrollTo({ top: 0, behavior: "smooth" });
        // 決戰選項（加入、趕到、出招）伺服器會回一句 message；大場面等模型判讀的時候選項沒了（人被別的分頁帶走），
        // 那一仗沒打成、不寫江湖紀錄，也只有這一句；一般選項的話在江湖紀錄裡，不回
        const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
        // 這一送剛好結算了回合時，回話是整段回合敘事（場景裡的戰況就是同一段）：提示只放得下幾秒，截短、指去場景。
        // 只有決戰選項這樣（FB-162：懸賞選項的拒絕句是一句話，場景裡沒有它，不截、不指去場景）
        if (text) toast(text.length > 40 && id.startsWith("battle:") ? `${text.slice(0, 40)}……（戰況見場景）` : text);
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
      case "switch": { // 改練：從庫裡那一列換到身上那張卡，畫完讓那張卡停在剛才按的地方
        const a = arts.find((r) => r.id === extra.art);
        return a ? { from: ['[data-act="switch"]', extra.art], to: card(a.kind), note: "art:" + extra.art } : null;
      }
      case "melt": return { from: ['[data-act="melt"]', extra.art], to: null, note: "lib" }; // 那一列不在了：捲到功法庫標題底下那一句看得到為止
      case "melt_insight": return { from: [".ins", null], to: [".ins", null], note: "ins" };
      case "wield": case "dismantle": case "name_divine": case "bind_art": return gear((slot(extra.weapon) || {}).slot);
      case "feed": return gear("mount");
      case "chuangong": case "join": case "leave": return { from: [".person-card", null], to: [".person-card", null], note: "person" };
      case "heal": return { from: ['[data-op="heal"]', null], to: ['[data-op="heal"]', null], note: "heal" };
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
      const r = await api(`/api/menxia/${op}`, { person: S.person, kind: S.kind, ...extra });
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
    }, op === "battle_text" || op === "duel_text" ? WAIT_LINES.battle : SENT_WAITING);
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
      S.forgePreview = r.preview || null;
      const drawn = JSON.stringify(S.forgePicks);
      S.forgePicks = r.picks || null;
      if (S.tab === "craft" && JSON.stringify(S.forgePicks) !== drawn) { keepPlace(() => renderPage()); return; } // 清單上「合不了」的標記變了
      const el = document.getElementById("forge-line");
      if (el) el.innerHTML = forgeLineHtml(S.menxia || {});
      const warn = document.getElementById("kiln-warn");
      if (warn) warn.innerHTML = kilnWarn();
    } catch (e) { /* 提示過 */ }
  }

  // 開爐等結果的時候頁面上方寫的那一句（W10，待 joy 潤）：取名實際約 3～5 秒，不把等待說成好幾十秒，免得人以為壞了
  const FORGE_WAIT = "爐火正旺。若這是江湖上第一次合出來，要等它取名，請稍候。";

  // 重畫時畫面不跳：記下 anchor（預設是第一個看得到的「開爐」或點子清單）在螢幕上的位置，畫完捲回同一個位置
  function keepPlace(draw, anchor) {
    const sel = anchor || "#forge-line";
    const before = document.querySelector(sel)?.getBoundingClientRect().top;
    draw();
    const after = document.querySelector(sel)?.getBoundingClientRect().top;
    if (before !== undefined && after !== undefined && after !== before) window.scrollBy({ top: after - before, left: 0, behavior: "instant" });
  }

  // 開爐：結果寫在「開爐」底下，頁面不捲（企劃者 2026-10-10）；合成了爐子清空，被拒絕的東西留著（Joy 2026-10-12）
  async function forge() {
    const btn = document.getElementById("forge");
    const step = guideKey(S.main && S.main.guide);
    let guideMoved = false, made = false;
    await busy(async () => {
      const lab = (btn.querySelector && btn.querySelector(".kiln-lab")) || btn; // 小太極上那兩個字（大爐子縮起來時的開爐鈕）
      btn.disabled = true;
      lab.textContent = "爐火正旺…";
      btn.classList.add("forging");
      // 等結果的這段時間（首次發現的配方要等模型取名）整座爐子晃動、火舌竄高、太極快轉
      document.querySelector(".furnace .w-furnace")?.classList.add("forging");
      document.querySelector(".furnace .w-taichi")?.classList.add("hot");
      S.forgeResult = { html: esc(FORGE_WAIT) };
      const stop = watchQueue(lab, "爐火正旺…");
      try {
        const r = await api("/api/menxia/forge", forgeBody());
        S.menxia = r.menxia;
        S.message = "";
        S.forgeResult = { html: r.message };
        S.forgeMade = r.made ? r.made_item || null : null; // 合出來的那一樣：結果底下畫它的卡
        made = !!r.made;
        // 合成了：兩格清空，下一爐從頭放（Joy 2026-10-12「爐子合完應該要把上次放上去的東西自動卸下」）；
        // 被拒絕（沒合成、只回一句話）：東西留在爐裡，換一格就能再試——只拿掉已經不在手上的
        // 鎖著的那一樣留在爐裡（Joy 2026-10-19），下一爐只要再放一樣；它自己被合掉了（武學＋武學不會，意境不會用掉）就解開
        if (r.made) S.forgeSel = S.forgeLock ? S.forgeSel.filter(isLocked) : [];
        trimForgeSel();
        S.forgeLine = "";
        S.forgePreview = null;
        S.forgePicks = null;
        setMain(r.main);
        renderTop();
        guideMoved = guideKey(r.main && r.main.guide) !== step;
      } catch (e) {
        // 被擋下來（另一個分頁的上一爐還沒出爐：400）或連不上：等的時候寫的「爐火正旺……請稍候」不能留著，換成這一句，
        // 爐裡放的東西不動；api() 已經用提示泡泡講過一次，結果那一格再留一份
        S.forgeResult = { html: esc(failText(e)) };
      } finally { stop(); }
    }, WAIT_LINES.forge);
    // 引導的下一句在頁面最上面（序章師父說的話）：這時才捲上去，不然留在原位、可以馬上接著合下一爐
    if (guideMoved) { renderPage(); window.scrollTo({ top: 0, behavior: "smooth" }); } else {
      keepPlace(() => renderPage());
      if (made) kilnBurst();
      showMadeCard();
    }
    updateForgeLine(); // 心得、體力、「已經有了」都變了：重問一次說明
  }

  // 開爐成了：爐裡的太極猛轉兩圈（大小兩座都是），新武學的卡從爐裡冒出來；轉完回到平常的慢轉
  function kilnBurst() {
    document.querySelectorAll(".furnace .w-taichi, .kiln-taichi .w-spin").forEach((g) => {
      g.classList.add("burst");
      g.addEventListener("animationend", () => g.classList.remove("burst"), { once: true });
    });
    const card = document.querySelector(".made-card");
    if (card) card.classList.add("emerge");
  }

  // 新武學的卡被黏在上面的固定列蓋住了（往下捲著開爐時）：捲到卡頭剛好露在固定列底下；本來就看得到就不動
  function showMadeCard() {
    const card = document.querySelector(".made-card"), bar = document.querySelector(".kiln.compact");
    if (!card || !bar || typeof card.getBoundingClientRect !== "function") return;
    const under = bar.getBoundingClientRect().bottom + 8, top = card.getBoundingClientRect().top;
    if (top < under) window.scrollBy({ top: top - under, left: 0, behavior: "smooth" });
  }

  async function travel(mode) {
    await busy(async () => {
      const r = await api("/api/travel", { place: S.mapSel, mode });
      setMain(r.main);
      renderTop();
      if (r.arrived) { S.mapMode = "overview"; S.mapSel = null; S.mapDrawer = "home"; } // 出發了：留在輿圖，抽屜收回總覽
      else toast(`沒能出發：${r.reason}`);
      await loadMap();
      setMapDrawer(S.mapDrawer);
    }, WAIT_LINES.move);
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

  document.addEventListener("click", async (ev) => {
    const el = ev.target.closest("[data-act]");
    if (!el) return;
    pressed = { el, at: Date.now() };
    const act = el.dataset.act;
    if (el.classList.contains("act-ink")) {
      const [key, x, y] = [el.dataset.key, ev.clientX, ev.clientY];
      if (act === "wheel") requestAnimationFrame(() => inkRipple(key, x, y)); // 展開移動會重畫整頁
      else inkRipple(key, x, y);
    }
    try {
      switch (act) {
        case "gate": S.gateMode = el.dataset.mode; renderGate(); break;
        case "promo-sound": promoSound(el); break;
        case "tab": {
          S.craftPick = false; // 換分頁：煉製頁的抽屜收起
          const loc = el.classList.contains("mini") && ev.target.closest && ev.target.closest("[data-loc]");
          if (loc) { S.mapSel = S.mapFocus = loc.getAttribute("data-loc"); S.mapMode = "place"; S.mapDrawer = "peek"; S.mapLayer = "region"; }
          await goTab(el.dataset.tab);
          break;
        }
        case "opt-why": toast(el.dataset.why); break; // 灰掉的俠寇鈕（名聲 5B）：點了只說整句原因，不送選擇
        case "choose":
          await choose(el, el.dataset.id);
          if (S.tab === "map") await loadMap(); // 在輿圖上按的（抽屜裡的喊停）：疊層跟著換
          break;
        case "world-region": enterRegion(el.dataset.id); break; // 天下圖點一州
        case "world-enter": enterRegion(hereRegion()); break; // 天下圖抽屜的「進入此區」：你在的那一州
        case "map-world": if (S.mapLayer !== "world" || S.mapMode !== "overview") toWorld(); break; // 「‹ 天下」、天下圖的「天下」
        case "map-pick":
          if (S.mapLayer === "world") { enterRegion(regionOfPlace(el.dataset.id), el.dataset.id); break; } // 天下圖上找地點挑了一處：進那一州、開它的卡
          S.mapSel = el.dataset.id; S.mapMode = "place"; S.mapQuery = "";
          setMapDrawer("peek");
          redrawDrawer();
          mapCenterOn(S.mapSel);
          drawMarks();
          break;
        case "map-search":
          S.mapMode = "search"; S.mapSel = null;
          setMapDrawer("full");
          redrawDrawer();
          drawMarks();
          setTimeout(() => { const q = document.getElementById("map-q"); if (q) q.focus(); }, 230);
          break;
        case "map-open": drawerTo(S.mapLayer === "world" ? "half" : "rest"); break; // 收起的那一行點了：攤開（區圖那一層記下來；天下圖拉開你腳下的卡）
        case "map-back":
          S.mapMode = "overview"; S.mapSel = null; S.mapQuery = "";
          setMapDrawer(S.mapLayer === "world" ? "min" : "home");
          redrawDrawer();
          drawMarks();
          break;
        case "map-travel": await travel(el.dataset.mode); break;
        case "map-timeline": mapTimeline(S.mapMode !== "timeline"); break;
        case "map-week": stopPlay(); mapWeekTo(Number(el.dataset.week)); break;
        case "map-graph": stopPlay(); graphPick(el, ev); break;
        case "map-now": stopPlay(); mapWeekTo(S.mapState.now_week); break;
        case "map-mark": // 年表上點一個地點的名字：地圖上圈出它（再點一次取消）
          S.mapSel = S.mapSel === el.dataset.id ? null : el.dataset.id;
          redrawDrawer();
          drawMarks();
          break;
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
        case "map-jianghu": // 就在這裡：出陣、探索回江湖頁按（探索三選一開著時直接攤開那三種）
          S.wheelSel = el.dataset.key === "explore" ? "explore" : null;
          await goTab("jianghu");
          break;
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
        case "peer-answer": await openPeer(el.dataset.name, "discuss"); break; // 場景底下論武的「挑一樣答應」（FB-117）
        case "peer-act": await peerAct(Number(el.dataset.i)); break;
        case "peer-pick": await peerAct(Number(el.parentElement.querySelector("select").value)); break;
        case "here-more": S.hereOpen = true; renderPage(); break;
        case "calls-more": openCalls(); break; // 場景底下收起來的邀請（FB-117、FB-241）
        case "party-leave": await leaveParty(); break;
        case "book-open": S.bookFrom = window.scrollY; S.book = el.dataset.book === "forge" ? "forge" : "arts"; render(); document.querySelector(".book-layer")?.scrollTo(0, 0); break;
        case "book-close": S.book = false; render(); window.scrollTo(0, S.bookFrom || 0); break;
        case "zhuan-open":
          S.bookFrom = window.scrollY; S.zhuan = { season: Number(el.dataset.season), view: null }; render();
          await loadZhuan();
          break;
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
        // 名聲（名聲設計十一之二）：狀態列只重畫它自己
        case "renown-toggle": S.renownOpen = !S.renownOpen; S.renownDot = null; renderTop(); break; // 2C：展開時「名聲」那一行
        case "renown-dot": S.renownDot = S.renownDot === el.dataset.dot ? null : el.dataset.dot; renderTop(); break; // 點圓點看那一段
        case "renown-sanren": S.renownSanren = !S.renownSanren; renderTop(); break; // 散人另有的好處
        case "renown-open": S.showMore = true; S.renownOpen = true; S.renownDot = null; renderTop(); window.scrollTo(0, 0); break; // 6B：金色的「名號傳開」
        case "renown-peer": peerRenownToggle(el); break; // 3B：玩家卡的稱號小籤，原地攤開說明（不重畫整張卡）
        case "fronts-help": frontsTap(); break; // 點戰況圖卡：底下攤開／收起這一季在打什麼、亂局、怎麼推（explain-2）
        case "checkin": await doMain("checkin", el.dataset.attr ? { attribute: el.dataset.attr } : {}); break; // 「簽到」小標攤開的領取鈕（四階的日子帶屬性）
        case "pill": await doMain("pill"); break; // 體力條上的「丹 N」：服一顆回體丹（測試期間一鍵補滿打開時同一顆鈕寫「補滿」，同一條路由）
        case "hero-node": heroTap(el); break; // 修練頁人物面板的光點：只換那一格，不重畫
        case "hero-jump": heroJump(el); break; // 面板底下「看這一門／看這件」：捲到下面那張卡
        case "allocate": await doMain("allocate", { stat: el.dataset.stat }); break; // 升級的屬性點加到一項（狀態列展開後的「＋臂力」）
        case "do": S.sheet = false; await doMain(el.dataset.op); break;
        case "letter-open": S.letterOpen = S.letterOpen === Number(el.dataset.id) ? null : Number(el.dataset.id); renderPage(); break;
        case "letter-read": S.letterOpen = null; await doMain("letter_read", { id: Number(el.dataset.id) }); break;
        case "letter-decline": await doMain("letter_decline", { id: Number(el.dataset.id) }); break;
        case "gender-pick": S.genderPick = el.dataset.value || null; render(); break;
        case "gender-go": S.genderPick = null; await doMain("gender", { value: el.dataset.value }); break;
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
        case "logout": closeEvents(); await api("/api/logout", {}); resetOrdersWatch(); forgetHowto(); S.sheet = false; S.peer = null; S.adPlayer = null; S.adPlayerName = ""; S.stage = "gate"; S.main = null; forgetMap(); render(); break;
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
        case "ins-open": S.insOpen = S.insOpen === el.dataset.id ? null : el.dataset.id; renderPage(); break;
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
        case "bind-art": { // 以器配招：送挑好的那一門（select 的 id 帶冒號，用 getElementById）
          const pick = document.getElementById("bind-art-" + el.dataset.id);
          if (pick && pick.value) ask("綁了之後不能改配（那一門熔掉、交掉才能再配），確定嗎？", "綁上", () => mx("bind_art", { weapon: el.dataset.id, art: pick.value }));
          break;
        }
        // 店面（店面獨立介面設計第二節）：換頁只在網頁上；換上、拆解、定名走修練頁的動作（shopMx）
        case "shop-tab": S.shopTab = el.dataset.tab; S.shopMore = false; S.shopNote = null; renderShop(false); break;
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
        case "shop-slot": setPot(el.dataset.role === "main" ? { main: null, aux: null } : { aux: null }); break; // 拿掉主料，輔料跟著出來（伺服器也這樣修）
        case "shop-go": await smithForge(); break;
        case "shop-unwrap": S.shopOpened = true; renderShop(); break; // 點開麻布（2.3）
        case "shop-keep": S.shopReveal = null; S.shopOpened = false; renderShop(); break; // 收下、留在裝備庫：收起出爐卡
        case "shop-wield":
          await shopMx("wield", { weapon: el.dataset.id });
          if (S.shopReveal && S.shopReveal.id === el.dataset.id) { S.shopReveal = null; S.shopOpened = false; renderShop(); } // 出爐卡上的「換上」：換好了卡收起
          break;
        case "shop-dismantle": ask(el.dataset.confirm || "把這一件拆成素材？拆掉就沒了。", "拆掉", () => shopMx("dismantle", { weapon: el.dataset.id })); break;
        case "shop-divine-keep": await shopMx("name_divine", { weapon: el.dataset.id, keep: true }); break;
        case "dismantle": // 裝備庫上那一把拆成一個素材（兵器設計 4.7.1）：先問一次（FB-125），按「拆掉」才送
          ask(el.dataset.confirm || "把這一件拆成素材？拆掉就沒了。", "拆掉", () => mx("dismantle", { weapon: el.dataset.id }));
          break;
        case "switch": {
          // 改練真的送出了（mx 換上伺服器回來的那一份 menxia）才收起卡片；還在忙（mx 直接返回）或請求失敗就照舊開著
          await mx("switch", { art: el.dataset.id }); // 真的送出了才收起卡片（mx 換上伺服器回來的那一份才收）；還在忙或失敗就照舊開著
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
          // 以心得修練那一顆（data-xinde）：同一個修練，付心得不付體力（Joy 2026-10-18）
          await mx("cultivate", { art: id, use_legend: ticked, ...(el.dataset.xinde ? { by_xinde: true } : {}) });
          if (ticked && S.menxia === was) S.legendTick[id] = true;
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
          renderPage();
          if (S.wheelSel) revealMoveCard(); // 收起（再點一次）不捲
          break;
        case "gather-wheel": // 找素材分支（第 32 項）：「找素材」點了在它底下攤開（再點一次收起）；輸入框跟著收
          S.gatherOpen = !S.gatherOpen;
          S.gatherSaying = false;
          renderPage();
          if (S.gatherOpen) revealMoveCard();
          break;
        case "map-layer": { // 濾鏡：原地換開關與記號，不重畫整頁；勢力與意境互斥，整排鈕一起換樣子
          S.mapLayers = toggleLayer(S.mapLayers, el.dataset.layer);
          syncLayerButtons(); // 意境鈕在右上角那一欄（FB-325）：兩處一起換
          drawMarks();
          if (S.mapMode === "place") redrawDrawer(); // 抽屜名字旁的地形跟著意境開關
          break;
        }
        case "map-zoom": mapZoom(el.dataset.step); break;
        case "map-home": mapHome(); break;
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

  document.addEventListener("input", mapQueryInput);
  document.addEventListener("input", (ev) => { // 名帖的自題一句：只換畫布上那一行，不重畫（游標留著）
    if (ev.target.id !== "mt-motto" || !S.mtEdit) return;
    S.mtEdit.motto = ev.target.value;
    const line = document.querySelector(".mt-layer .mt-motto");
    if (line) line.textContent = S.mtEdit.motto ? `「${S.mtEdit.motto}」` : "";
  });

  document.addEventListener("change", async (ev) => {
    if (ev.target.id === "anon") await doMain("anonymous", { value: ev.target.checked });
    if (ev.target.id === "hints-off") await doMain("hints_off", { value: ev.target.checked }); // 碰到才說的小提醒（新手引導計畫三）；打開時排著的清掉
    if (ev.target.dataset && ev.target.dataset.legend) onLegendTick(ev.target);
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
      } else if (form.id === "answer-form") {
        if (!data.text.trim()) return;
        await answer(form, data.text.trim());
      } else if (form.id === "say-form") {
        if (!data.text.trim()) return;
        await sayLine(form, data.text.trim());
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
    if (pollInFlight || S.stage !== "game" || S.busy || (document.hidden && !sealWatched())) return; // 背景分頁不輪詢，奪璽例外（sealWatched）
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
    if (shopPolled(old)) return; // 店面開著（或剛開、剛收）：只管店面那一層（店面獨立介面設計 1.3）
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
      for (const id of Object.keys(S.legendTick)) { // 丹用完了、或那一門已經不是衝絕學這一步：勾跟著作廢
        const row = x.owned_arts.find((a) => a.id === id);
        if (!row || !row.cultivate.legend) delete S.legendTick[id];
      }
      if (!S.forgeSel.length) { S.forgeLine = ""; S.forgePreview = null; } // 爐是空的：用伺服器剛給的那一行（心得是新的）
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
      const was = S.mapState;
      if (!was) return;
      // 手指（滑鼠）還按在地圖上：換記號沒關係，但這一輪先不抓（放開之後下一輪再說）。清掉 mainKey，下一輪的 main 就算沒變也會再來
      if (mapHeld()) { S.mainKey = ""; return; }
      const moved = old.status.location !== S.main.status.location || !!old.on_road !== !!S.main.on_road; // 抵達、出發、喊停
      const every = S.main.on_road ? 0 : MAP_STATE_EVERY; // 在路上：每一輪都重抓，「還有幾分鐘」跟著走
      if (!moved && Date.now() - S.mapStateAt < every) return;
      await loadMap();
    }
  }

  // 修練、煉製兩頁各自畫了 menxia 的哪幾欄（照 pagePractice／pageCraft）：輪詢只在這幾欄變了才重畫。
  // 不比整份，是因為本人卡上的氣血一直在回，整份 menxia 幾乎每分鐘都不一樣，煉製頁根本沒畫那張卡
  const MENXIA_SHOWN = {
    practice: ["rules", "heal_cost", "slot_cards", "owned_arts", "insights", "holdings", "naming", "player_card", "roster", "person", "person_card", "on_team", "lessons", "heal", "gear"],  // heal：療傷鈕能不能按（銀兩夠不夠、內傷）變了就要重畫
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
    S.forgePreview = null;
    if (S.forgeSel.length) updateForgeLine();
  }

  // 重抓之後，爐裡放的若已經不在了（熔掉、別處用掉）就拿掉；有拿掉回 true
  function trimForgeSel() {
    const arts = new Set((S.menxia?.owned_arts || []).map((a) => a.id));
    const held = new Set((S.menxia?.insights || []).map((i) => i.id));
    const keep = S.forgeSel.filter((p) => (p.type === "art" ? arts : held).has(p.id));
    const trimmed = keep.length !== S.forgeSel.length;
    S.forgeSel = keep;
    if (S.forgeLock && !keep.some(isLocked)) S.forgeLock = null; // 鎖著的那一樣不在爐裡了：鎖也解開
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
    // 決戰攤開、收起舊的回合（roundBlocks）：只記下來，下一次輪詢重畫照樣
    else if (box instanceof Element && box.matches("details.b-round")) {
      const open = S.roundsOpen || (S.roundsOpen = new Set());
      if (box.open) open.add(box.dataset.round); else open.delete(box.dataset.round);
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
})();
