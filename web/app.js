/* 天下大勢的網頁前端：沒有建置步驟、不靠外部函式庫。
 *
 * 畫面只有三種：登入、取名號、遊戲。遊戲畫面 = 頂上的狀態列 + 一頁內容 + 底部五個分頁：
 *   江湖（場景與選項）、修練（練成、閉關、武學與意境、修練與熔煉、名冊）、煉製（太極火爐：武學＋意境、武學＋武學合成，意境＋意境合併）、
 *   輿圖、見聞（戰報、大勢、傳聞、江湖史、紀錄）。商城開著時多第六格「商城」與齒輪旁的錠子鈕，都打開商城那一層（不是一頁）。
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
    // 商城（商城第二批，企劃者 2026-10-20 挑的入口乙＋丙、那一層子）：跟三間店不同，開不開只在網頁這一邊（伺服器沒有「人在店裡」這件事）
    mallOpen: false, // 商城那一層開著沒（齒輪旁的錠子鈕、底部第六格打開，左上「出店」收起）
    mallTab: "shelf", // 停在哪一頁（shelf 貨架／log 紀錄）；每次打開從貨架來
    mallData: null, // /api/mall 那一份（餘額、月卡、回體丹、上架的商品）：打開時重抓、買完換成回來的那一份
    mallLog: null, // /api/mall/records 那一份（紀錄頁）：切到紀錄頁就重抓
    mallSay: null, // 掌櫃那一句換成什麼：{ text, ok }（買成了的那一句、買不了的原因）；換頁、出店清掉
    mallPick: null, // 正在問要不要買的那一件（商品 id）：貨架上那一格框起來
    mallPending: null, // 送出去還沒拿到回應的那一筆 { id, ref }：逾時、斷線時留著，再按同一件用同一個編號（伺服器照編號不會扣兩次）
    mallFail: false, // 這一頁的資料沒拿到（連不上）：畫一句與「再試一次」
    adMall: null, // 管理者區商城那一組查到的帳（/api/admin/mall）
    adMallName: "", // 管理者區商城那一組查的名號或帳號
    adMallNote: "", // 管理者區商城那一組填的原因（抽屜重畫時放回去；成了就清掉）
    adMallMsg: "", // 管理者區商城那一組上一下的結果（補發、扣回、退一筆、要寫原因），寫在查帳那一行
    adMallOk: false, // 那一句是做成了的（帶 ok、不是紅字，FB-492）；被拒的、要先填的是 false
    sealAct: false, // 玉璽碎片的獨門行動（改版第 2 批，企劃者挑了乙）：選目標的那一層（店面樣式）開著沒；送出、收起、碎片沒了就關
    sealSide: null, // 散人起用傳檄挑的那一軍（status.seal.act.sides 的 id）；關掉那一層就清掉，每次重挑
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
    slotPick: null, // 修練頁點開的那一個空槽（{ art, i }）：底下攤開手上空著的意境挑一個裝進去
    createPick: null, // 自創第一步挑到一半的種類與兵器：{ kind, form }，輪詢重畫不會清掉
    createPose: null, // 擺式那一步拖到一半的姿勢（各關節角度），送出前只在這裡
    createText: null, // 立意那一步打到一半的那一句
    mxNote: null, // 修練頁其他動作（裝備、意境、門下、療傷）的結果：{ at, html }，寫在按的那一塊裡（mxPlace）；切分頁、做別的動作就清掉
    artNote: null, // 修練（衝品質）的結果：{ id, html }，寫在那一門卡片的按鈕底下（W7）；點別的卡片、切分頁、做別的動作就清掉
    forgeSel: [], // 爐裡放的：{type: "ins", id}，最多兩個（爐裡只合意境，Joy 2026-10-21）
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
    pdrawer: null, // 修練頁的抽屜開著哪一個光點（{t: "worn"|"gear", key}；false 是剛關上，序章不再自己攤開）
    insFilter: "all", // 修練頁意境列的篩選：all／free（沒裝的）／used（裝著的）
    forgeReveal: false, // 剛出爐：意境卡演一次排場
    forgePreview: null, // 兩格都放好時的預覽卡（/api/forge_line 的 preview，合成即設計）；只放一樣、空爐是 null，畫 forgeLine 那一行
    mapBase: null, // 輿圖升級：底圖（/api/map/base：svg、地點、路、大區），一次載入只抓一次，疊層的 key 變了才重抓
    mapState: null, // 疊層（/api/map/state）
    mapStateAt: 0, // 上次抓疊層的時間（輪詢每 MAP_STATE_EVERY 毫秒重抓一次）
    mapSel: null, // 選了的地點
    mapMode: "overview", // 抽屜在畫什麼："overview"（天下圖收著那一行、區圖沒點地點）、"place"（一處的卡）、"search"、"timeline"
    mapDrawer: "min", // 抽屜的高度："min"（收著那一行）、"peek"（卡半開）、"half"、"full"、"tl"（版圖變化）
    mapWeek: null, // 版圖變化看的週次；null＝現在
    mapQuery: "", // 找地點的字
    // 輿圖的哪一層（輿圖第三版）："world" 天下圖（打開輿圖第一眼）、"region" 區圖（第 4 批）；兩張都是固定取景，
    // 上面再疊一層拖與縮放（企劃者 2026-10-22，mapPan）
    mapLayer: "world",
    mapRegion: null, // 區圖畫哪一區（大區 id）
    worldView: null, // 天下圖此刻的取景（applyMapView 照 worldFit 算）
    regionView: null, // 區圖此刻的取景（applyMapView 照 regionFit 算：{ s, cx, cy, frame, bottom }）
    marksKey: "", // 記號照哪一個取景畫的（viewKey）：一樣就不必重畫
    mapPan: null, // 取景上面的拖與縮放 { z 倍率 1～PAN_MAX, x, y 螢幕上的位移 }；null＝1 倍（企劃者 2026-10-22）
    panKey: "", // 拖縮是照哪一個取景（viewKey）疊上去的：取景換了（換區、換層、地圖框換寬）回 1 倍；同一層同一區只換框高帶過去（FB-710）
    panFrom: null, // 上一次套上去的取景與地圖框 { layer, region, vw, vh, s, cx, cy }（panCarry 照它換算）；明講回 1 倍時清掉
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
  // 商城的兩個入口（齒輪旁的錠子鈕、底部第六格）：出師後才出現（FB-490，docs/guide/商城.md）。草廬裡照序章的 reveal 藏著（tab:mall 或 all 才出來）；
  // 出了草廬、初入江湖那四步就在：m.onboard 的 reveal 是前幾步的聯集、不會有 all，照 shown() 會等到四步走完才出現
  const mallShown = () => { const p = pro(); return !!(S.main && S.main.mall) && (!p || p.reveal.includes("all") || p.reveal.includes("tab:mall")); };
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
    } else {
      S.stage = data.stage === "create" ? "create" : "gate";
      closeEvents();
    }
    render();
    if (S.stage === "game" && S.tab === "map") loadMap().catch(() => {}); // 停在輿圖分頁登入：這個人的疊層與底圖（輪詢在沒有疊層時不抓）
  }

  function setMain(main) {
    // 破境卡：動作回來的與輪詢拿到的都走這裡（S.main 換好之後才畫）。測試只抽 setMain 出來跑，沒有 ascendCard 就不畫
    if (typeof ascendCard === "function") setTimeout(ascendCard, 0);
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
    if (S.mallOpen && !(S.main && S.main.mall)) S.mallOpen = false; // 商城關了（主機關掉開關）：那一層跟著收
    if (S.stage !== "game" || (!S.sheet && !S.peer && !S.mallOpen)) closeAsk(); // 確認框疊在設定抽屜、玩家卡或商城上；抽屜關了、被登出就一起收掉
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
      ${S.sheet ? sheetHtml() : S.peer ? peerHtml() : S.boardCard ? boardCardHtml() : ""}
      ${S.main && S.main.shop ? shopHtml(S.main.shop) : S.mallOpen ? shopHtml(mallShop()) : ""}
      ${S.sealAct && sealActNow() ? sealActHtml(sealActNow()) : ""}
      ${S.book ? bookHtml() : ""}
      ${S.zhuan ? zhuanHtml(S.zhuan) : ""}
      ${S.mtEdit && S.mingtie ? mtEditHtml() : ""}
      ${S.mtZoom ? mtZoomHtml() : ""}`;
    fitBars(); // 先量狀態列：所在那一行放不下會折成兩行、狀態列高一截（FB-493），第一屏（renderPage 裡的 fitFirstScreen）照折好的高度收
    renderPage();
    if (S.mtEdit) mtPadReady();
    fitBars(); // 狀態列的「體力」「氣血」放不放得下（FB-198）；頁面畫上去之後再量一次（電腦上捲軸出來，狀態列跟著窄）
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
  // 商城開著（main.mall）時多第六格「商城」（商城第二批，企劃者 2026-10-20 挑的入口丙）：點了打開商城那一層、不換頁（出店回到原本那一頁）。
  // 序章裡跟其他還沒開放的分頁一樣藏著，出了草廬就在（mallShown，FB-490；齒輪旁的錠子鈕同一條）
  function tabsHtml() {
    const list = TABS.filter((t) => shown(`tab:${t.id}`));
    if (!list.length) return "";
    const mall = mallShown();
    return `<nav class="tabs"><div class="tabs-inner" style="grid-template-columns:repeat(${list.length + (mall ? 1 : 0)}, 1fr)">${list.map((t) => `
        <button class="tab ${S.tab === t.id ? "on" : ""}" data-act="tab" data-tab="${t.id}" data-glow="tab:${t.id}">
          <span class="ico">${t.ico}</span>${t.name}${t.id === "news" && S.unseen && S.tab !== "news" ? '<i class="dot"></i>' : ""}
        </button>`).join("")}${mall ? `
        <button class="tab tab-mall" data-act="mall-open" data-tab="mall" data-glow="tab:mall" aria-label="商城，元寶 ${S.main.mall.balance | 0}"><span class="ico">寶</span>商城</button>` : ""}</div></nav>`;
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
      ${(s.dates || []).length ? `<p class="muted">這一季的險關：${s.dates.map(esc).join("、")}</p>` : ""}${sealActLine(s.act)}</details>`;
  }

  // ── 玉璽碎片的獨門行動（改版第 2 批，status.seal.act；企劃者 2026-10-21 挑了乙：草圖 docs/superpowers/specs/2026-10-21-玉璽碎片改版-草圖/第2批/）──
  // 入口是修練頁傳承那一列的一顆鈕（heirloomRow）；要指定目標的三種（引將、傳檄、收心）開一層店面樣式的（sealActHtml：招牌寫行動名、右上剩幾次、
  // 一人一列寫此刻在哪與灰掉的原因、每列一顆；散人傳檄先照店面頁籤挑一邊），頒詔、承露按了直接問。問句、說明、原因全是伺服器的字（seal_acts.view）；
  // 這裡只有鈕上的動詞、名單的標題與江湖頁那一行（待 joy 潤）。碎片卡與這一份本來就只給持有者自己，改版關著沒有 act（鈕與那一行都不畫）
  // 第 3 批多鎮地、補缺（目標是區塊、分軍：每一列多 side 與底下那一小行 info；散人挑了哪一軍只列那一軍的）
  const SEAL_VERB = { yinjiang: "引來", chuanxi: "傳檄", shouxin: "收心", zhendi: "鎮住", bujue: "補回" }; // 要指定目標的：鈕上的動詞（待 joy 潤）
  const SEAL_PICK = { yinjiang: "指定一位大勢人物", chuanxi: "指定一條戰線", shouxin: "指定一位人物",
    zhendi: "指定一塊此刻佔著的地", bujue: "指定一塊剛被翻走的地" }; // 名單的標題（待 joy 潤）
  const SEAL_NONE = "這一邊此刻沒有能指定的地方。"; // 散人挑了一邊、那一軍沒有能鎮（補）的地（待 joy 潤）
  // 按不下去、可是有一列列的地可看（FB-645：鎮地、補缺每一塊都灰著，伺服器照樣給 targets）：鈕打得開那一層、各列灰著寫原因
  const sealBrowse = (a) => !!a && !a.ok && a.kind in SEAL_VERB && (a.targets || []).length > 0;
  function sealActNow() {
    const s = S.main && S.main.status && S.main.status.seal;
    return s && s.act ? s.act : null;
  }

  // 江湖頁碎片卡底下那一行提醒（企劃者 2026-10-21：只是字，按了跳到修練頁傳承那一列那一顆）；這一片沒有行動不畫。
  // 這一季整季都用不上（idle：鎮地、補缺在領地爭奪關著的季）寫原因，不寫「還能起用 N 次」（FB-626 那種一句說能用、一句說不能用）
  function sealActLine(a) {
    if (!a) return "";
    const left = a.idle ? a.why : a.left > 0 ? `這一季還能起用 ${a.left | 0} 次` : "這一季的次數用完了";
    return `<p class="seal-act-line"><button class="seal-act-go" data-act="seal-act-go">獨門行動・${esc(a.name)}：${left}</button></p>`;
  }

  // 修練頁傳承那一列（玉璽碎片的抄本，玉璽碎片設計 7.3）：沒有行動的碎片照舊沒有鈕；有的多一顆「X・剩 N 次」，按不下去灰掉、原因寫在這一列底下
  // （.rwhy，手機沒有 title 可看），這一片的行動此刻還在生效的那一句也寫在底下
  function heirloomRow(h, a) {
    const notes = a ? [a.ok ? "" : a.why, a.live].filter(Boolean) : [];
    const look = sealBrowse(a); // FB-645：只能看、按不下去：不是 primary，打得開那一層
    const btn = a ? `<div class="wbtns"><button class="btn small${look ? "" : " primary"}" data-act="seal-act"${a.ok || look ? "" : ` disabled title="${esc(a.why)}"`}>${esc(a.name)}・剩 ${a.left | 0} 次</button></div>` : "";
    return `<div class="wrow heirloom"><div class="winfo"><b>【${esc(h.name)}】</b><span>傳承・${esc(h.effect_text)}</span>${notes.map((t) => `<small class="rwhy">${esc(t)}</small>`).join("")}</div>${btn}</div>`;
  }

  // 選目標的那一層：店面的框（招牌、收起、右上剩幾次、說明那一句），捲的那一層一人一列。散人還沒挑邊時：不分軍的（傳檄的戰線）每一列都灰著、
  // 分軍的（鎮地、補缺的地，t.side）先不列，上面寫要先挑；挑了只列那一軍的，那一軍一塊都沒有寫 SEAL_NONE
  function sealActHtml(a) {
    const sides = a.sides || [];
    const needSide = sides.length > 0 && !sides.some((s) => s.id === S.sealSide);
    const tabs = sides.length ? `<div class="shop-pages seal-sides" role="group" aria-label="這一次算哪一軍">${sides.map((s) => `
        <button class="shop-page${S.sealSide === s.id ? " on" : ""}" data-act="seal-side" data-side="${esc(s.id)}" aria-pressed="${S.sealSide === s.id}">這一次算${esc(s.name)}</button>`).join("")}</div>` : "";
    const shown = (a.targets || []).filter((t) => !t.side || !sides.length || (!needSide && t.side === S.sealSide));
    const rows = shown.map((t) => {
      const why = t.why || (needSide ? a.side_note : "");
      return `<div class="shop-row seal-row"><div class="winfo"><b>${esc(t.name)}</b>${t.where ? `<span>此刻在${esc(t.where)}</span>` : ""}${t.info ? `<span>${esc(t.info)}</span>` : ""}${t.why ? `<span class="seal-why">${esc(t.why)}</span>` : ""}</div>
        <div class="wbtns"><button class="btn small${why ? "" : " primary"}" data-act="seal-pick" data-id="${esc(t.id)}"${why ? ` disabled title="${esc(why)}"` : ""}>${SEAL_VERB[a.kind] || "起用"}</button></div></div>`;
    }).join("");
    const none = a.ok && !rows && sides.length && !needSide ? `<p class="shop-cap">${SEAL_NONE}</p>` : "";
    return `<div class="shop-layer shop-seal" role="dialog" aria-label="${esc(a.name)}">
      <header class="shop-bar"><button class="shop-back" data-act="seal-act-close">‹ 收起</button><span class="shop-sign">${esc(a.name)}</span><span class="shop-silver">剩 ${a.left | 0} 次</span></header>
      <p class="shop-line">${esc(a.text)}</p>
      <div class="shop-body"><div class="shop-col">${tabs}${needSide ? `<p class="shop-warn">${esc(a.side_note)}</p>` : ""}
        <p class="shop-cap">${esc(a.rule)}</p>${a.live ? `<p class="shop-cap seal-live">${esc(a.live)}</p>` : ""}${a.ok ? "" : `<p class="shop-warn">${esc(a.why)}</p>`}
        ${rows ? `<h4 class="seal-h">${SEAL_PICK[a.kind] || ""}</h4>${rows}` : ""}${none}</div></div>
    </div>`;
  }

  // 問句（伺服器的 confirm，{target} 換目標的名字、{side} 換挑的那一軍），按「起用」才送；送出時那一層收起，結果照一般動作寫在提示裡
  function sealAsk(a, target) {
    const side = (a.sides || []).find((s) => s.id === S.sealSide);
    const text = a.confirm.replace("{target}", target ? target.name : "").replace("{side}", side ? side.name : "");
    const body = { target: target ? target.id : "", side: side ? side.id : "" };
    ask(text, "起用", async () => { S.sealAct = false; S.sealSide = null; await keepScroll(() => doMain("seal_use", body)); });
  }

  // 開、收那一層與送出都整個重畫：底下的修練頁停在原處（拇指底下還是傳承那一列）
  async function keepScroll(draw) {
    const y = window.scrollY;
    await draw();
    window.scrollTo(0, y);
  }

  // 輪詢（refreshPage 最前面叫）：那一層開著而且資料變了，只換那一層（捲到哪裡留著）；碎片沒了、這一片沒有行動了就收起
  function sealActPolled(old) {
    if (!S.sealAct) return;
    const a = sealActNow();
    const layer = document.querySelector(".shop-seal");
    if (!a || !layer) { S.sealAct = false; S.sealSide = null; layer?.remove(); return; }
    const was = old && old.status && old.status.seal ? old.status.seal.act : null;
    if (JSON.stringify(was) !== JSON.stringify(a)) redrawSealAct(a);
  }

  // 只換那一層（挑了一邊、輪詢的資料變了）：捲到哪裡留著，不重畫底下的頁面
  function redrawSealAct(a) {
    const layer = document.querySelector(".shop-seal");
    if (!layer) return;
    const top = layer.querySelector(".shop-body")?.scrollTop || 0;
    layer.outerHTML = sealActHtml(a);
    const body = document.querySelector(".shop-seal .shop-body");
    if (body) body.scrollTop = top;
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
    const where = typeof document.createRange === "function" && head && typeof head.querySelector === "function" ? head.querySelector(".who > .where") : null;
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
    const subs = [
      s.calendar && s.next_event ? `下一件：${esc(s.next_event.title)}${s.next_event.at ? `・${esc(s.next_event.at)}` : ""}（${countdown(s.next_event.in_seconds)}）` : "",
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
    let kilnWas = false; // 重畫前爐子已經縮成一條：畫完照樣縮著，不再從上面掉下來一次
    if (S.tab === "map" && showMapHost()) page.innerHTML = ""; // 輿圖畫在常駐的那一層（FB-324）
    else {
      hideMapHost();
      const fn = { jianghu: pageJianghu, practice: pagePractice, craft: pageCraft, map: pageMap, news: pageNews }[S.tab];
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
    return trailMoves(folded !== card ? folded : withReportLink(card, id));
  }
  // 戰報裡招、功效、狀態那一句引擎寫成「〔疾風追影〕某某腳下一錯……」；畫面上人在前、招在後（招式與絕學稿案第一節）：
  // 「某某腳下一錯……〔疾風追影〕」，招名畫成一枚小籤。只動清單的一條（<li>），決戰那一條前面的陣營小標籤留在最前面
  function trailMoves(html) {
    const MOVE_LEAD = /(<li[^>]*>(?:<span class="b-tag">[^<]*<\/span>)?)〔([^〕<\n]{1,12})〕([^<\n]+)/g;
    return String(html).replace(MOVE_LEAD, (all, head, name, rest) => `${head}${rest}<span class="t-move">〔${name}〕</span>`);
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
      return `<path d="M${x0},${y0} Q${x1},${y1} ${x2},${y2}" style="animation-delay:-${((performance.now() / 1000 + (k % 4) * 0.23) % 1.8).toFixed(2)}s"/>`; // 照同一個鐘起跳（同 spinAt）：重畫時火舌不從頭竄一次
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
    // 練功（FB-670，企劃者 2026-10-22 選練功入口「丙」）：以前是探索卡上的第四顆，現在行動列自己一格、排在探索右邊（五格）。
    // 選項 id 照舊 explore:practice（選單、模擬腳本都不受影響）；一類一顆沒開、選單上沒有練功時不畫（同調息），序章照 act:practice 的鍵亮。
    // 城裡操練開著時（新手引導重做，Config.training；m.training）城裡這一格是「操練」（act:drill），城外照舊是練功
    { key: "practice", ids: ["act:drill", "explore:practice"], name: "尋敵", none: "", icon: '<path d="M14.5 17.5L3 6V3h3l11.5 11.5M13 19l6-6M16 16l4 4M19 21l2-2M9.5 14.5L21 3h-3L6.5 14.5M11 19l-6-6M8 16l-4 4M3 19l2 2"/>' },
    { key: "train", ids: ["act:train"], name: "遊歷", none: "沒有對手", icon: '<path d="M14.5 4h-5L7 7h10zM12 7v13M8 12h8"/>' },
    // 打坐 2026-10-12 拿掉了（企劃者）：這一格只在序章教體力那一步有選項（調息），沒有選項就不畫（平常是四顆）
    { key: "rest", ids: ["act:rest"], name: "調息", none: "", icon: '<circle cx="12" cy="7" r="2.5"/><path d="M8 20c0-3 3-4 4-4s4 1 4 4M5 15l3-2m11 2l-3-2"/>' },
    { key: "social", ids: ["act:socialize", "act:call"], name: "交友", none: "沒有人", icon: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>' },
  ];
  const MOVE_ICON = '<path d="M13 3l-3 7h5l-4 11 8-10h-5z"/>';
  const SHORT_SUB = { "act:rest": "回體力", "act:call": "挑一位" };  // 求見先打開名單挑人（FB-044：以前又寫一次「求見」；挑了人才花體力）
  const TALKED_OUT = "已經談滿", TALKED_OUT_SUB = "已談滿";  // 談滿了的求見（Game._talked_out_note 的開頭）在行動列格子裡的短說法（待 joy 潤）
  // 灰格小字最多四個字（FB-670：練功多一格、五格之後每格約 62 px，320 寬約 51 px，扣掉內距與框約 45 px、10 px 的字不換行；四格時是六個字）。
  // 原因比這長的：格子寫短的，整句放行動列底下那一行（伺服器那一行本來就寫了整句的，例：散人不能出陣、不在爭奪之列；沒寫的帶在
  // actionBar 的 noted 第三項 → actNotesHtml）。FB-664：交友灰著、這裡沒有人時（engine.SOCIAL_NO_ONE），10 個字的整句在 375 寬兩頭被切掉
  const SOCIAL_NO_ONE = "這裡沒有能說上話的人", SOCIAL_NO_ONE_SUB = "沒有人";  // 待 joy 潤
  const FAME_GAP = /^名望還差 \d+$/, FAME_GAP_SUB = "名望不夠";  // 交友見不到人（engine._why_not_talk）：還差多少寫在底下那一行（FB-670；待 joy 潤）
  // 出陣灰著的兩種長原因（sortie.RANGER_NOTE、sortie.OUT_NOTE，六個字）：格子寫短的；整句是伺服器寫的出陣那一行（RANGER_LINE、OUT_LINE）（FB-670；待 joy 潤）
  const SORTIE_LONG_SUB = { "散人不能出陣": "未投靠", "不在爭奪之列": "不在爭奪" };
  // 練功那一格的小字（FB-670；待 joy 潤）：亮著寫「不限次數」（第二行照勝算上色，同遊歷），這裡只有頭目時寫「對上頭目」（頭目有冷卻與次數，
  // 不是不限次數；鈕上那一段是 explore_modes.BOSS_NOTE）；灰著：沒有對手（explore_modes.NO_FOE）寫伺服器在鈕上帶的那一個字（o.note：
  // 城鎮「城外才有」、城外沒有對手的地方「這裡沒有」，PM 2026-10-22；舊版伺服器沒帶照寫「城外才有」）、頭目冷卻中或次數用完
  // （鈕上寫「…再現身」）寫「頭目不在」、體力不夠照別格。整句（最近的在哪、步行多久；頭目還要等多久）是伺服器的 action_notes，網頁不另算。
  // 不帶路：灰著就是按不下去（企劃者 2026-10-22 選丙、不選丙帶路）
  const PRACTICE_ID = "explore:practice"; // engine：explore_modes.option_id(PRACTICE)
  const PRACTICE_SUB = "不限次數", PRACTICE_BOSS_SUB = "對上頭目", PRACTICE_BOSS = "頭目";
  const PRACTICE_NO_FOE = "這裡沒有可以練手的對手", PRACTICE_OUT = "城外才有", PRACTICE_AWAY = /現身/, PRACTICE_AWAY_SUB = "頭目不在";
  // 出陣（出陣探索與地盤設計第二節）：出陣開著時（m.sortie）遊歷那一格叫「出陣」，散人、不在戰線上的地點沒有出陣鈕時灰著寫「不在戰線」（待 joy 潤）
  const SORTIE_CELL = { name: "出陣", none: "不在戰線" };
  const SORTIE_LEFT = /今日還能 (\d+) 次/; // 鈕上的「今日還能 N 次」：格子小字寫「今日 N 次」
  const SORTIE_USED = /^今日已出陣/;
  const SORTIE_FULL_SUB = "今日已滿"; // 用完了：整句（什麼時候再來）在行動列底下那一行（待 joy 潤）
  const EXPLORE_PREFIX = "explore:"; // 探索三選一（出陣探索與地盤設計第三節）：探索那一格點了展開這三顆
  const EXPLORE_SUB = "三選一"; // 探索那一格是展開鈕時的小字（待 joy 潤）
  const TIER_WORDS = ["宵小出沒", "匪寇橫行", "兇徒盤據"]; // training.TIER_WORDS：尋敵那一格的小字寫這一帶多兇（不寫幾級，Joy 2026-10-22）
  const DRILL_FULL = "今日已練滿", DRILL_FULL_SUB = "今日已滿"; // training.DRILL_FULL：用完了，格子寫短的、整句在底下那一行，點了打開移動
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
  // 格子上的名字（FB-670）：五格時「出陣・守」（320 寬）、「出陣・攪局」（375 寬）一行放不下，瀏覽器會斷在「攪／局」中間：
  // 照「・」切成不折行的小段（.nb），只在「・」後面換行；沒有「・」的照舊
  function inkName(name) {
    return name.includes("・") ? name.split(/(?<=・)/).map((t) => `<span class="nb">${esc(t)}</span>`).join("") : esc(name);
  }
  const inkCell = (key, name, sub, icon, attrs, cls, note = "") => `<button class="act-ink${cls}" data-key="${key}" data-glow="act:${key}" ${attrs}>
      <svg class="ink-icon" viewBox="0 0 24 24" aria-hidden="true">${icon}</svg><b>${inkName(name)}</b><small>${esc(sub)}</small>${
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
      const list = `<ul class="b-lines">\n${trailMoves(items)}</ul>`;
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
    const noted = []; // 畫出來、伺服器又寫了說明的格子：[格子上的名字, 選項 id（, 整句）]（行動列底下那幾行，見 actNotesHtml）
    // 探索三選一（出陣探索與地盤設計第三節）：三顆畫在探索那一格點開的卡上，不掉進「此地還能做」
    // 找素材分支（第 32 項）畫在「找素材」底下那一排，不算進三選一的那幾顆；練功（explore:practice）在行動列自己一格（FB-670），不在卡上
    const modes = m.options.filter((o) => o.id.startsWith(EXPLORE_PREFIX) && !o.id.startsWith(GATHER_BRANCH) && o.id !== PRACTICE_ID);
    const branches = m.options.filter((o) => o.id.startsWith(GATHER_BRANCH));
    modes.forEach((o) => used.add(o.id));
    branches.forEach((o) => used.add(o.id));
    // 入口灰著（體力不夠，三顆都按不下去）時就算記著展開也不畫：那一格是灰格子，不是展開鈕
    const exploreOpen = S.wheelSel === "explore" && modes.length > 0 && !!(byId["act:explore"] && byId["act:explore"].enabled);
    // 序章（新手引導計畫一）：還沒亮的格子不畫（act:explore、act:practice、act:train、act:rest、act:social、act:move）；
    // 不畫的格子對到的選項照樣記成用過，不會掉進「此地還能做」那個摺疊裡。練功的鍵教學內容還沒寫：草廬與初入江湖那四步都不畫（FB-670）
    const cells = ACT_CELLS.map((d0) => {
      const d = d0.key === "train" && m.sortie ? { ...d0, ...SORTIE_CELL } : d0;
      const o = d.ids.map((id) => byId[id]).find(Boolean) || (d.key === "social" ? loneCall : undefined);
      if (o) used.add(o.id);
      if (!shown(`act:${d.key}`) || ((d.key === "rest" || d.key === "practice") && !o)) return "";
      if (!o) return inkCell(d.key, d.name, d.none, d.icon, "disabled", " off");
      const lone = o.id.startsWith("call:");
      const [label, detail] = optParts(o);
      const name = lone ? "求見" : label;  // 格子窄：名字寫「求見」，人物的名字放在下面一行
      // 灰著、原因太長的交友（一類一顆開著時單人地點的交友是 act:socialize，不是 call:）：格子寫短的，整句帶句號放底下那一行（FB-664）。
      // 名望還差幾點（FB-670：五格時四個字以上會被切）同樣。單人的求見（lone）伺服器自己寫了同一句（action_notes），不動
      const drillFull = !o.enabled && detail.startsWith(DRILL_FULL); // 操練用完了：點了打開移動（最近的練功點在底下那一行）
      const longWhy = !o.enabled && !lone && (detail === SOCIAL_NO_ONE || detail.startsWith(TALKED_OUT) || FAME_GAP.test(detail) || drillFull);
      noted.push(longWhy ? [name, o.id, `${detail}。`] : [name, o.id]);
      // 按不下去的原因：標籤括號裡寫的是體力就是「體力不夠」，寫別的就照寫；整句太長、格子裝不下（約 60 px、不換行）時只留
      // 最後一小句（例：挑戰本人打贏之後「剛吃了敗仗，閉門不見」只寫「閉門不見」，T4）
      // 談滿了的求見（「已經談滿 3 輪，第 1 週・週日 00:00 之後再來」）：最後一小句是換日的那一刻，格子裝不下會被切成碎片，
      // 格子只寫「已談滿」，整句在底下那一行（Game.action_notes，day-scale 審查 I1）
      // 出陣：小字寫今天還剩幾次（「今日 5 次」，體力在鈕上、說明那一行也有）；用完了寫「今日已滿」，什麼時候再來在底下那一行
      const left = SORTIE_LEFT.exec(detail);
      // 探索三選一開著：探索那一格是展開鈕（同移動），點了在下面就地展開三顆；入口灰著（三顆都按不下去）時照一般的灰格子
      const wheel = d.key === "explore" && modes.length > 0 && o.enabled;
      // 練功（FB-670）：亮著「不限次數」（只有頭目時「對上頭目」）；灰著沒有對手照鈕的 note（城外才有／這裡沒有）、頭目不在「頭目不在」，體力不夠照別格。
      // 城外練功分級（Config.training）：亮著寫級數（一級／二級／三級）；城裡的操練照出陣寫「今日 N 次」，用完了「今日已滿」
      const practice = d.key === "practice" && o.id === PRACTICE_ID && (o.enabled || !detail.startsWith("體力"))
        ? (o.enabled ? (detail.split("・").includes(PRACTICE_BOSS) ? PRACTICE_BOSS_SUB : PRACTICE_SUB)
          : detail.startsWith(PRACTICE_NO_FOE) ? (o.note || PRACTICE_OUT) : PRACTICE_AWAY.test(detail) ? PRACTICE_AWAY_SUB : "")
        : "";
      const tier = d.key === "practice" && o.enabled ? detail.split("・").find((x) => TIER_WORDS.includes(x)) : "";
      const sub = wheel ? EXPLORE_SUB
        : tier ? tier
        : drillFull ? DRILL_FULL_SUB
        : practice ? practice
        : o.enabled ? (lone ? label.replace(/^求見/, "") : left ? `今日 ${left[1]} 次` : (SHORT_SUB[o.id] || detail.replace(/^體力 (\d+).*$/, "體力 $1")))
        : detail === SOCIAL_NO_ONE ? SOCIAL_NO_ONE_SUB
        : detail.startsWith(TALKED_OUT) ? TALKED_OUT_SUB
        : FAME_GAP.test(detail) ? FAME_GAP_SUB
        : SORTIE_USED.test(detail) ? SORTIE_FULL_SUB
        : SORTIE_LONG_SUB[detail] ? SORTIE_LONG_SUB[detail]
        : (detail && !detail.startsWith("體力") ? detail.split("，").pop() : "體力不夠");
      // 體力之後還有說明（遊歷的「體力 10・2 路對手・必敗」）：挑出勝算那一段另起一行（FB-044；對手數放不下就不寫）。
      // 不一定是最後一段：有自己人也有敵人的地方後面還接「・或與自己人操練」（畫面批次審查 C1）
      const parts = detail.split("・");
      const note = o.enabled && !wheel && /^體力 \d+/.test(parts[0]) ? (parts.find((x) => x in ODDS_TONE) || "") : "";
      const attrs = wheel ? `data-act="wheel" data-key="explore" aria-expanded="${exploreOpen}"`
        : drillFull ? `data-act="drill-full" aria-expanded="${S.wheelSel === "move"}"` // 格子自己的 data-key 是 practice，不能再寫一個
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
          <span class="k">→</span><span>${esc(o.label)}${o.note ? `<small class="opt-note">${esc(o.note)}</small>` : ""}</span></button>`).join("")}</div></div>`;
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
    // full（可有可無）：格子裡寫了短說法的灰格自己帶整句（FB-664），蓋過伺服器那一句——伺服器的「結識這裡的人」說的是按得下去的時候。
    // 伺服器沒給這一格的說明（舊版、序章裡是空的）就照舊不畫：有沒有這一行由伺服器說了算，這裡只換句子
    // 操練用完了（新手引導重做）：伺服器沒給操練說明，整句（最近的練功點）照鈕上的寫
    const rows = noted.filter(([, id, full]) => notes[id] || (full && id === "act:drill")).map(([name, id, full]) => `<p><b>${esc(name)}</b>${esc(full || notes[id])}</p>`);
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

  // 展開移動（或探索三選一、找素材分支）之後，把展開的那張卡整張捲到底部分頁列上方看得到（FB-663，PM 2026-10-21 給號）。
  // 以前用 scrollIntoView({ block: "nearest" }) 加 CSS 的 scroll-margin-bottom：卡本身還在視窗裡、只是落在分頁列底下時，瀏覽器認為
  // 「已經看得到」不捲，scroll-margin 不算數（量到：375×812 站潁川郡，探索卡底 797、分頁列頂 756，最後一顆〔練功〕下半截被蓋住，
  // scrollY 一直 0；野外也蓋住約 13 px）。改成自己量：卡底離分頁列頂（含底部安全區：量的是分頁列真正的頂）至少 REVEAL_GAP，
  // 只往下捲、不往回捲；卡比分頁列上方看得到的地方還高時，最多捲到卡頂貼在狀態列底下 REVEAL_TOP（第一顆一定看得到）
  const REVEAL_GAP = 12;
  const REVEAL_TOP = 8;
  // card：展開的卡的位置（getBoundingClientRect）；回傳要往下捲幾 px（0＝不捲）
  function revealShift(card, tabsTop, topEdge) {
    const over = card.bottom - (tabsTop - REVEAL_GAP);
    if (over <= 0) return 0;
    return Math.max(0, Math.min(over, card.top - (topEdge + REVEAL_TOP)));
  }
  function revealMoveCard() {
    const card = document.querySelector("#page .act-move, #page .act-explore");
    const tabs = document.querySelector(".tabs");
    if (!card || !tabs) return;
    const head = document.getElementById("top");
    const topEdge = head && !head.hidden ? head.getBoundingClientRect().bottom : 0;
    const shift = revealShift(card.getBoundingClientRect(), tabs.getBoundingClientRect().top, topEdge);
    if (shift < 1) return;
    const calm = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.scrollBy({ top: Math.ceil(shift), behavior: calm ? "auto" : "smooth" });
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
      <summary>📜 ${wkWord("order_this", "本週")}軍令（${list.length}${done ? `，已達成 ${done}` : ""}）</summary><div class="fold-body">${cart}${rows}</div></details>`;
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

  // 手上揭了的懸賞，加上身上有合用兵器的求兵（status.bounties，bounties.status；後者多一行 have）：一張一行，怎麼交差、賞什麼。懸賞榜在城鎮才看得到，
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
      : '<div class="order-meta">到城鎮的懸賞榜前，可以揭新的、放棄，或交出合用的兵器。</div>';  // 待 joy 潤（2026-10-21 拿掉求藝：不再寫「功夫」）
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
      label: `${wkWord("this", "本週")}江湖大事 ${m.bulletin.length} 則`,
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
    if (!S.main.options.some((o) => hit(o.id))) { goTab("map"); return; }
    S.wheelSel = "move";
    renderPage();
    revealMoveCard();
    document.querySelectorAll("#page .act-move [data-id]").forEach((el) => { if (hit(el.dataset.id)) el.classList.add("glow"); });
  }

  const peekParts = (m) => [newbiePeek(m), shown("stances") ? stancePeek(m) : null, shown("board") ? boardPeek(m, peekWeek(m)) : null, shown("quest") ? questPeek(m) : null, checkinPeek(m)];

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
    const events = r.timeline.map((e) => `<div class="result-event"><b>${esc(wkName(e.week, `第 ${e.week} 週`))}・${esc(e.title)}</b>${
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
    const letter = dailyCardHtml(m) + letterHtml(m.letter); // 書信小卡排在「剛剛」上面（大勢人物擴充第二批）；月卡今天的份還沒領時更上面一張
    // 本週軍令排在行動列（與路上捷徑）下面、三條戰況上面：不擠掉第一屏的「剛剛」、場景與行動列（計畫 T6）
    // 收起來照週記；21 天季的軍令每天一道，照季曆第幾天記（status.calendar.day），隔天的新軍令重新展開
    const orderKey = (m.status && m.status.calendar && m.status.calendar.day) || week;
    const orderCard = (m.orders || m.convoy) && shown("orders") ? ordersHtml(m.orders || [], orderKey, m.convoy) : "";
    // 懸賞卡跟軍令卡排在一起（散人沒有軍令，這張就是他的）：手上沒揭、也沒有合用的求兵可以交時就不畫（status.bounties 兩種都收）
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
  // 人多時先列 HERE_SHOW 個、其餘收在「還有 N 人」裡（點了全列，記在 S.hereOpen）。每個角色都在同一份名單裡（伺服器不分）
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
  // 武學重構：品級是武學本身的（合出來、自創時就定了），沒有「修練衝品」的機率條了；意境裝進槽裡是技能（slotsHtml）

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
  const MELT_RANKS = ["", "一重", "二重", "三重"]; // 意境（技能）的強度：揣摩一次加一重（Joy 2026-10-20「●好醜」）
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
      ["rank", "強度", vals((it) => (it.t === "ins" && it.rank ? it.rank : "")).sort().map((r) => [String(r), MELT_RANKS[r] || `${r}重`])],
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
      if (j.tactic) tags.push(`<i class="hi">${tsealHtml(j.tactic_title || "本命")}${esc(j.tactic)}</i>`);
      if (j.ultimate) tags.push(`<i class="hi">${tsealHtml("絕")}${esc(j.ultimate)}</i>`);
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
      lines.push(`第${a.level}成${it.power !== null ? `，威力 ${it.power}` : ""}${a.affinity ? `・收${esc(a.affinity)}` : ""}${scoreText(a)}`);
      if ((a.slots || []).length) lines.push(`意境槽 ${a.slots.length} 格：${a.slots.map((t) => (t ? `「${esc(t.name)}」〔${esc(t.skill)}〕${esc(t.mark)}` : "空")).join("、")}`);
      if ((j.traits || []).length) lines.push(`功效：${j.traits.map((t) => `〔${esc(t.name)}〕${t.layers > 1 ? `${t.layers} 層` : ""}`).join("")}`);
      if (j.special) lines.push(`特別功效〔${esc(j.special)}〕`);
      if (j.ultimate) lines.push(`${tsealHtml("絕")}〔${esc(j.ultimate)}〕`);
      if (j.tactic) lines.push(`${tsealHtml(j.tactic_title || "本命")}〔${esc(j.tactic)}〕`);
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
  const heroFigure = (s) => HERO_FIGURES[s && s.gender === "女" ? "女" : "男"];
  const HERO_GEAR_NAMES = { weapon: "武器", armor: "防具", mount: "坐騎", treasure: "寶物" };
  // 一個光點此刻的樣子：標籤、有沒有東西（沒有的點暗著）、底下那一格的標題、說明、按鈕
  function heroInfo(n, x, s) {
    if (n.kind === "art") {
      const a = x.owned_arts.find((r) => r.worn && r.kind === n.key);
      if (!a) return { label: n.key, lit: false, title: n.key, desc: `你身上還沒有${n.key}。`, button: "" };
      const move = moveOf(a.tactic);
      return {
        // 招式與絕學稿案第四輪：亮點旁邊直接寫名字，武學與內功多寫那一招；成數、階數、屬性都不寫
        // 序章指路：卡裡的鈕收進抽屜了，光點自己也帶那幾個鍵（練成看那一欄按不按得下去；applyGlow 只亮這一步的）
        label: `${a.name}${move ? `〔${move}〕` : ""}`, name: a.name, move, lit: true, glow: [...["switch", "cultivate", "melt", "slot"].filter((k) => (a.glow || []).includes(k)), ...(practiceOk(x, n.key) ? ["practice"] : [])],
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
      label: w.name, lit: true,
      title: `【${esc(w.name)}】<small>${esc(label)}</small>`,
      desc,
      button: `<button class="btn small" data-act="hero-jump" data-to="gear" data-kind="${esc(n.key)}">看這件</button>`,
    };
  }
  const practiceOk = (x, kind) => { const c = (x.slot_cards || []).find((sl) => sl.kind === kind); return !!c && c.learned !== false && !c.blocked && !c.maxed; };
  function heroPanel(x, s) {
    const fig = heroFigure(s);
    const nodes = fig.nodes.map((n) => [n, heroInfo(n, x, s)]).filter(([, info]) => info);
    if (!nodes.length) return "";
    // 點了開抽屜（practiceDrawer）；抽屜開著的那一個亮著
    const open = S.pdrawer && (S.pdrawer.t === "worn" || S.pdrawer.t === "gear") ? S.pdrawer.key : null;
    return `<section class="hero" aria-label="人物">
      <div class="hero-hd">
        <div><div class="hero-name">${esc(s.name)}</div><div class="hero-tag">${esc(s.affiliation)}</div></div>
        <div class="hero-sub"><div>第 ${s.level | 0} 級</div><div>氣血 ${s.hp | 0}／${s.hp_max | 0}</div>${typeof x.might === "number" ? `<div class="hero-might">戰力 <b>${x.might | 0}</b></div>` : ""}</div>
      </div>
      <div class="hero-stage">
        <div class="hero-halo" aria-hidden="true"></div>
        <div class="hero-fig" style="aspect-ratio:${fig.ratio}">
          <img src="${fig.src}" alt="" draggable="false">
          ${nodes.map(([n, info]) => `<button class="hero-node${n.key === open ? " on" : ""}${info.lit ? "" : " dim"} ${n.side}" style="left:${n.x}%;top:${n.y}%" data-act="hero-node" data-kind="${n.kind}" data-key="${esc(n.key)}"${info.glow && info.glow.length && n.key !== open ? ` data-glow="${info.glow.join(" ")}"` : ""} aria-label="${esc(info.label)}"><i class="pulse"></i><i class="dot"></i><span>${info.move ? `${esc(info.name)}<small>〔${esc(info.move)}〕</small>` : esc(info.label)}</span></button>`).join("")}
        </div>
      </div>
    </section>`;
  }
  // 點光點（招式與絕學稿案第四輪）：從底下升起那一樣的抽屜——武學、內功是那一門的卡（練、槽、改練），裝備是那一欄的裝備庫
  function heroTap(el) {
    S.pdrawer = { t: el.dataset.kind === "art" ? "worn" : "gear", key: el.dataset.key };
    S.artOpen = null; S.insOpen = null;
    renderPage();
  }
  // 卡上那一行「沈〔追風影〕出招・…」裡的招名
  const moveOf = (tactic) => ((/〔([^〕]+)〕/.exec(String(tactic || "")) || [])[1] || "");
  // 那一行開頭的印（看家、本命、絕、私印）
  const sealOf = (tactic) => ((/^([^〔]{1,2})〔/.exec(String(tactic || "")) || [])[1] || "");

  // ── 玉環與火柴人（Joy 2026-10-20：槽分顏色、自創擺式當圖示；草案 https://claude.ai/artifact/54XJZ7jutrsND8YLnyCC4x）──
  // 每一格是一枚玉環：單色一種屬性、雙色斜分兩種、任色八色一圈。顏色照屬性（--at-*，style.css）。
  const ATTR_VAR = { 剛: "gang", 柔: "rou", 快: "kuai", 慢: "man", 陽: "yang", 陰: "yin", 虛: "xu", 實: "shi" };
  function ringHtml(colors, inner, cls) {
    const c = (colors || []).filter((k) => ATTR_VAR[k]);
    const kind = c.length === 0 ? "any" : c.length === 1 ? "one" : "two";
    const style = c.length ? ` style="--a:var(--at-${ATTR_VAR[c[0]]});--b:var(--at-${ATTR_VAR[c[c.length > 1 ? 1 : 0]]})"` : "";
    return `<span class="jring ${kind}${cls ? ` ${cls}` : ""}"${style}><span class="jin">${inner || ""}</span></span>`;
  }
  const ringWord = (colors) => ((colors || []).length ? `收${colors.join("")}` : "任意皆收"); // 待 joy 潤
  // 意境的強度（一重～三重）畫成三節玉
  const lvHtml = (n) => `<span class="lv" role="img" aria-label="${["", "一重", "二重", "三重"][Math.max(1, Math.min(3, n | 0))]}">${[1, 2, 3].map((k) => `<i${k <= (n | 0) ? ' class="on"' : ""}></i>`).join("")}</span>`;
  // 意境效果池（第二批）：一份意境的品質（下中上，玉環右上角一枚小印）與一到兩個效果——一般功效寫名字加三節玉，大獎金底，秘方的特別功效朱底。
  // 資料是伺服器給的 fx（skillview.fx_traits：name、layers、grand、special）
  const Q_SHORT = { 下品: "下", 中品: "中", 上品: "上" };
  const qMark = (q) => (Q_SHORT[q] ? `<em class="iq q-${Q_SHORT[q] === "上" ? 3 : Q_SHORT[q] === "中" ? 2 : 1}" title="${esc(q)}">${Q_SHORT[q]}</em>` : "");
  const FX_LAYERS = ["", "一重", "二重", "三重"];
  // 評分（第三批）：「・評 87」；上品還沒成絕學的寫門檻「・評 87／100」
  const scoreText = (a) => (typeof a.score === "number" ? `・評 ${a.score}` : ""); // 評分沒有上限、不是門檻（Joy 2026-10-20）
  const fxOne = (e) => e.grand ? `<i class="fx grand${e.maybe ? " maybe" : ""}">${esc(e.name)}</i>`
    : e.special ? `<i class="fx sp">${esc(e.name)}</i>`
    : `<i class="fx${e.maybe ? " maybe" : ""}">${esc(e.name)}${e.maybe ? "" : lvHtml(e.layers)}</i>`;
  const fxHtml = (fx, cls) => (Array.isArray(fx) && fx.length ? `<span class="fxs${cls ? ` ${cls}` : ""}">${fx.map(fxOne).join("")}</span>` : "");
  // 意境的品相（招式與絕學稿案第五輪）：凡不蓋印，佳藍、珍紫、神金；修練頁的列、抽屜、出爐卡同一枚。底子（下中上）不給玩家看
  const LOOK_CLS = { 凡: "l1", 佳: "l2", 珍: "l3", 神: "l4" };
  const lookSeal = (look, big) => (LOOK_CLS[look] ? `<em class="look ${LOOK_CLS[look]}${big ? " big" : ""}" title="${esc(look)}品">${esc(look)}</em>` : "");
  // 品相的四級一眼看懂（Joy 2026-10-21「合出來我根本看不懂這是不是好的」「沒有直接把珍品還是什麼顯示在剛合好那邊」）：
  // 凡佳珍神排成一條，這一份那一級亮著，底下一句這一級是什麼、再往上要什麼（insight_fx.look 的條件）。字待 joy 潤
  const LOOK_STEPS = [["凡", "一個效果、只有一重"], ["佳", "二重，或兩個效果"], ["珍", "三重，或悟出真意"], ["神", "真意再加三重：最好的一級"]];
  // 自創武學也走同一條梯子（Joy 2026-10-21「那武學呢 有分？」）：撞到幾樣稀有（create.marks_of：純或渾、招已透、稀有路數）
  const ART_LOOK_STEPS = [["凡", "三樣稀有一樣都沒撞到"], ["佳", "撞到一樣：三格同是單色或任色、招已透、稀有路數"], ["珍", "撞到兩樣"], ["神", "三樣全撞到：最好的一級"]];
  function lookLadder(look, steps = LOOK_STEPS) {
    const at = steps.findIndex(([k]) => k === look);
    if (at < 0) return "";
    const up = steps[at + 1];
    return `<div class="look-ladder"><div class="ll-steps">${steps.map(([k], n) => `<i class="${LOOK_CLS[k]}${n === at ? " on" : n < at ? " past" : ""}">${k}</i>`).join("")}</div>
      <p><b class="${LOOK_CLS[look]}">${esc(look)}品</b>・四品裡第 ${at + 1} 級：${esc(steps[at][1])}。${up ? `再往上是${up[0]}品：${esc(up[1])}。` : ""}</p></div>`;
  }
  // 裝在身上哪一格最強（伺服器 i.best，might.best_place）：會更強寫綠字的戰力，不會寫一句灰字。字待 joy 潤
  function bestLine(i) {
    const b = i.best, now = S.menxia && typeof S.menxia.might === "number" ? S.menxia.might : null;
    if (i.slotted) return "";
    if (!b || now == null || b.might <= now) return '<p class="ic-best">身上兩門裝在哪一格都不會更強。</p>';
    return `<p class="ic-best up">裝進【${esc(b.name)}】第 ${(b.i | 0) + 1} 格${b.swap ? `（換下「${esc(b.swap)}」）` : ""}最強：戰力 ${now | 0} → <b>${b.might | 0}</b></p>`;
  }
  // 意境卡（第五輪第三節）：名字、屬性玉環、品相印；功效籤當摘要，底下每個功效一句白話（大獎金底）；
  // o.fits：「裝進【某門】第 N 格」的鈕（伺服器算好裝得進哪裡，skillview._fits）；o.melt：化成心得；o.reveal：出爐的排場；o.cmp：跟舊的比
  function insightCardHtml(i, o = {}) {
    if (!i) return "";
    const fx = (i.effects || []).map((e) => `<li class="${e.grand ? "grand" : e.special ? "sp" : ""}"><b>${esc(e.name)}${e.grand || e.special ? "" : esc(FX_LAYERS[e.layers] || "")}</b>${e.desc ? `<span>${esc(e.desc)}</span>` : ""}</li>`).join("");
    const fits = o.fits ? (i.fits || []).map((f) => `<button class="btn small" data-act="slot-in" data-id="${esc(f.art)}" data-i="${f.i | 0}" data-ins="${esc(i.id)}">裝進【${esc(f.name)}】第 ${(f.i | 0) + 1} 格</button>${f.stack ? `<small class="stk">${esc(f.stack)}</small>` : ""}`).join("") : "";
    const where = i.slotted ? `裝在【${esc(i.slotted)}】` : o.fits && !fits ? "身上的武學沒有空格收得下它。" : ""; // 待 joy 潤
    const rare = i.look === "珍" || i.look === "神";
    return `<div class="ins-card${o.reveal ? " reveal" : ""}${o.reveal && rare ? " rare" : ""}">
      <div class="ic-head">${ringHtml([i.attribute], i.own && i.glyph ? glyphSvg(i.glyph, "glyph-mini") : `<b>${esc(String(i.name).slice(0, 1))}</b>`)}<div><b>「${esc(i.name)}」</b><small>屬${esc(i.attribute)}${i.lean && i.lean !== "無" ? `・${esc(i.lean)}` : ""}</small></div>${lookSeal(i.look, true)}</div>
      ${lookLadder(i.look)}
      ${fx ? `<ul class="ic-fx">${fx}</ul>` : fxHtml(i.fx)}
      ${bestLine(i)}
      ${o.cmp ? `<p class="ic-cmp">${esc(o.cmp)}</p>` : ""}
      ${i.note ? `<p class="ic-note">${esc(i.note)}</p>` : ""}
      ${i.own ? `<p class="glyph-from">悟於${esc(i.place || "某處")}・只屬於你</p>` : ""}
      ${where ? `<p class="muted small">${where}</p>` : ""}
      ${fits ? `<div class="ic-fits">${fits}</div>` : ""}
      ${o.melt ? `<div class="ic-melt"><button class="btn small" data-act="melt-insight" data-id="${esc(i.id)}" data-name="${esc(i.name)}" ${i.blocked ? "disabled" : ""}>化成心得 ${i.melt | 0}</button>${i.blocked ? `<small class="muted">${esc(i.blocked)}</small>` : ""}</div>` : ""}
    </div>`;
  }
  // 招的印記（招式與絕學稿案第一節）：伺服器寫「看家〔拄棍守村〕應招・…」「本命〔…〕」「絕〔…〕」「沈〔…〕」（自創：創的人名號第一個字），
  // 開頭那幾個字畫成一枚印——看家墨印、本命朱印、絕金印、其餘是私印；後面照字寫
  const TSEAL = { 看家: "ink", 本命: "red", 絕: "gold", 後勁: "gold" };
  const tsealHtml = (word) => `<b class="tseal ${TSEAL[word] || "own"}">${esc(word)}</b>`;
  function tacticHtml(text) {
    const m = /^([^〔]{1,2})〔/.exec(String(text || ""));
    return m ? `${tsealHtml(m[1])}${esc(String(text).slice(m[1].length))}` : esc(text || "");
  }
  // 純文字版（清單的小字、title）：「掠影二重・流光」
  const fxText = (fx) => (Array.isArray(fx) ? fx.map((e) => (e.grand || e.special ? e.name : `${e.name}${FX_LAYERS[e.layers] || ""}`)).join("・") : "");

  // 火柴人：九個角度（create.POSE_KEYS，度；0 朝下、正的往右），骨架跟 tianxia/create.py 同一組數字（伺服器照同一個幾何讀偏向）
  const RIG = { CX: 110, SY: 96, HIPY: 146, UA: 27, FA: 25, TH: 31, SH: 29 };
  const POSE_KEYS = ["t", "lS", "lE", "rS", "rE", "lH", "lK", "rH", "rK"];
  const WEAPON_LEN = { 劍: 40, 刀: 32, 槍: 70, 棍: 60 };
  function rigJoints(P) {
    const d2r = (d) => (d * Math.PI) / 180, g = (k) => Number(P && P[k]) || 0;
    const { CX, SY, HIPY, UA, FA, TH, SH } = RIG, t = d2r(g("t"));
    const chain = (x, y, a1, l1, a2, l2) => { const e = { x: x + Math.sin(a1) * l1, y: y + Math.cos(a1) * l1 }; return [e, { x: e.x + Math.sin(a1 + a2) * l2, y: e.y + Math.cos(a1 + a2) * l2 }]; };
    const J = { neck: { x: CX - Math.sin(t) * 10, y: SY - Math.cos(t) * 10 }, head: { x: CX - Math.sin(t) * 24, y: SY - Math.cos(t) * 24 },
      lSh: { x: CX - 9, y: SY }, rSh: { x: CX + 9, y: SY }, lHip: { x: CX - 7, y: HIPY }, rHip: { x: CX + 7, y: HIPY }, root: { x: CX, y: SY } };
    [J.lEl, J.lHa] = chain(J.lSh.x, J.lSh.y, d2r(g("lS")) + t, UA, d2r(g("lE")), FA);
    [J.rEl, J.rHa] = chain(J.rSh.x, J.rSh.y, d2r(g("rS")) + t, UA, d2r(g("rE")), FA);
    [J.lKn, J.lFt] = chain(J.lHip.x, J.lHip.y, d2r(g("lH")), TH, d2r(g("lK")), SH);
    [J.rKn, J.rFt] = chain(J.rHip.x, J.rHip.y, d2r(g("rH")), TH, d2r(g("rK")), SH);
    J.hand = d2r(g("rS")) + t + d2r(g("rE"));
    return J;
  }
  // 姿勢讀出的偏向（create.pose_scores 的同一套規則；伺服器在擺定那一下再讀一次，以伺服器為準）
  function poseRead(P) {
    const J = rigJoints(P), { CX, SY, HIPY, UA, FA, TH, SH } = RIG;
    const reach = Math.max(Math.abs(J.rHa.x - CX), Math.abs(J.lHa.x - CX)) / (UA + FA);
    const high = Math.max(SY - J.rHa.y, SY - J.lHa.y) / (UA + FA);
    const tucked = Math.hypot(J.rHa.x - CX, J.rHa.y - (SY + 20)) < 30 && Math.hypot(J.lHa.x - CX, J.lHa.y - (SY + 20)) < 30;
    const spread = Math.abs(J.lFt.x - J.rFt.x) / (TH + SH), lift = Math.min(J.lFt.y, J.rFt.y) < HIPY + TH * 1.3, lean = Number(P.t) || 0;
    const s = { 剛: 0, 柔: 0, 快: 0, 慢: 0, 虛: 0, 實: 0 };
    s.剛 += Math.max(0, reach - 0.95) * 8 + Math.max(0, high - 0.15) * 2;
    if (tucked) s.柔 += 1.6;
    s.實 += Math.max(0, spread - 0.9) * 3; s.慢 += Math.max(0, spread - 1.1) * 2;
    if (lift) { s.虛 += 2; s.快 += 1; }
    if (lean < -12) s.快 += (-lean - 12) / 15;
    if (lean > 10) s.慢 += (lean - 10) / 15;
    const order = ["陰", "陽", "剛", "柔", "快", "慢", "虛", "實"];
    const top = Object.entries(s).sort((p, q) => q[1] - p[1] || order.indexOf(p[0]) - order.indexOf(q[0]));
    const attrs = top[0][1] < 0.35 ? [] : [top[0][0], ...(top[1][1] > 0.35 && top[1][1] > top[0][1] * 0.6 ? [top[1][0]] : [])];
    const why = [];
    if (reach > 0.95) why.push("手伸得遠"); if (high > 0.15) why.push("手抬得高"); if (tucked) why.push("雙手收在胸前");
    if (spread > 0.9) why.push("馬步寬"); if (lift) why.push("單腳提起"); if (lean < -12) why.push("身子前傾"); if (lean > 10) why.push("身子後仰");
    return { attrs, why };
  }
  const poseReadText = (attrs) => (attrs.length ? `此式偏${attrs[0]}${attrs[1] ? `、兼${attrs[1]}` : ""}` : "此式平正，不偏一路"); // 待 joy 潤
  // 骨頭與兵器（拖曳的大圖與功法卡的小圖共用）；joints 為真時多畫可拖的關節點
  function figBody(P, weapon, joints) {
    const J = rigJoints(P || {}), f = (v) => v.toFixed(1);
    const L = (p, q, cls) => `<line class="${cls || "bone"}" x1="${f(p.x)}" y1="${f(p.y)}" x2="${f(q.x)}" y2="${f(q.y)}"/>`;
    let arm = "";
    const len = WEAPON_LEN[weapon];
    if (len) {
      const tip = { x: J.rHa.x + Math.sin(J.hand) * len, y: J.rHa.y + Math.cos(J.hand) * len };
      const back = weapon === "棍" || weapon === "槍" ? { x: J.rHa.x - Math.sin(J.hand) * 14, y: J.rHa.y - Math.cos(J.hand) * 14 } : J.rHa;
      arm = L(back, tip, `blade${weapon === "刀" || weapon === "棍" ? " thick" : ""}`);
    } else if (weapon === "弓弩") {
      const n = { x: Math.cos(J.hand), y: -Math.sin(J.hand) }, h = J.rHa;
      arm = `<path class="blade bow" d="M${f(h.x + n.x * 18)} ${f(h.y + n.y * 18)} Q${f(h.x + Math.sin(J.hand) * 14)} ${f(h.y + Math.cos(J.hand) * 14)} ${f(h.x - n.x * 18)} ${f(h.y - n.y * 18)}"/>`;
    }
    const bones = L(J.neck, { x: RIG.CX, y: RIG.HIPY }) + L(J.lSh, J.lEl) + L(J.lEl, J.lHa) + L(J.rSh, J.rEl) + L(J.rEl, J.rHa)
      + L(J.lHip, J.lKn) + L(J.lKn, J.lFt) + L(J.rHip, J.rKn) + L(J.rKn, J.rFt) + L(J.lSh, J.rSh);
    const head = `<circle class="bone" cx="${f(J.head.x)}" cy="${f(J.head.y)}" r="13"/>`;
    const dots = joints ? ["head", "lEl", "lHa", "rEl", "rHa", "lKn", "lFt", "rKn", "rFt"].map((k) =>
      `<circle class="jt" data-j="${k}" cx="${f(J[k].x)}" cy="${f(J[k].y)}" r="${k === "head" ? 7 : 8}"/><circle class="jhit" data-j="${k}" cx="${f(J[k].x)}" cy="${f(J[k].y)}" r="18"/>`).join("") : "";
    return arm + bones + head + dots;
  }
  // 功法卡上的小圖（一門武學的圖示）：裁到人形那一塊
  const figSvg = (P, weapon, cls) => `<svg class="fig${cls ? ` ${cls}` : ""}" viewBox="30 40 160 200" aria-hidden="true">${figBody(P, weapon, false)}</svg>`;

  // 意境槽：一門武學一排玉環。裝著的環心寫意境的名字、底下〔技能〕與三節玉，點了拆下；空的環照它的顏色畫、底下寫收什麼，
  // 點了在底下攤開手上空著的意境，顏色收得下的點了裝進「這一格」（送 index），收不下的灰掉寫原因。裝、拆都不花東西。
  // 寫死的武學（本命、部下的上品）slots 是空清單，不畫。字待 joy 潤
  // ro：別人的卡（榜單點開的，Joy 2026-10-22）：一樣畫，但格子點不了、不攤意境
  // 同效果好幾份（Joy 2026-10-22「第二份算半」）：格子上那一份算了幾成（skillview.slot_stack_marks，伺服器寫好的字）
  const stkHtml = (t) => (t ? `<small class="stk">${esc(t)}</small>` : "");
  function slotsHtml(a, x, ro = false) {
    if (!Array.isArray(a.slots) || !a.slots.length) return "";
    const colors = Array.isArray(a.colors) ? a.colors : [];
    const pick = !ro && S.slotPick && S.slotPick.art === a.id ? S.slotPick.i : null;
    // 序章裝意境那一步（prologue.art_glow 給師父點名的那一門 "slot"）：空格與可裝的意境亮
    const glowSlot = (a.glow || []).includes("slot") ? ' data-glow="slot"' : "";
    const cells = a.slots.map((s, i) => {
      const c = colors[i] || [];
      if (ro) return s
        ? `<span class="jd full" title="${esc(`「${s.name}」${s.look || ""}・${fxText(s.fx) || s.skill}${s.desc ? `：${s.desc}` : ""}`)}">${ringHtml(c, `<b>${esc(String(s.name).slice(0, 2))}</b>`)}${lookSeal(s.look)}${fxHtml(s.fx, "col") || `<small>〔${esc(s.skill)}〕</small>${lvHtml(s.strength)}`}${stkHtml(s.stack)}</span>`
        : `<span class="jd empty">${ringHtml(c, "", "vacant")}<small class="dim">空著</small></span>`;
      return s
        ? `<button type="button" class="jd full" data-act="slot-out" data-id="${esc(a.id)}" data-ins="${esc(s.id)}" title="${esc(`「${s.name}」${s.look || ""}・${fxText(s.fx) || s.skill}${s.desc ? `：${s.desc}` : ""}（點了拆下）`)}">${ringHtml(c, `<b>${esc(String(s.name).slice(0, 2))}</b>`)}${lookSeal(s.look)}${fxHtml(s.fx, "col") || `<small>〔${esc(s.skill)}〕</small>${lvHtml(s.strength)}`}${stkHtml(s.stack)}</button>`
        : `<button type="button" class="jd empty${pick === i ? " on" : ""}" data-act="slot-pick" data-id="${esc(a.id)}" data-i="${i}"${glowSlot} title="${esc(ringWord(c))}">${ringHtml(c, "<i>＋</i>", "vacant")}<small class="dim">${esc(ringWord(c))}</small></button>`;
    }).join("");
    let picker = "";
    if (pick !== null) {
      const c = colors[pick] || [];
      const fits = (i) => !c.length || c.includes(i.attribute);
      const free = (x.insights || []).filter((i) => !i.slotted);
      picker = `<div class="slot-pick">${a.stack_rule ? `<p class="stk-rule">${esc(a.stack_rule)}</p>` : ""}${free.length ? free.map((i) => `<button type="button" class="${fits(i) ? "" : "no"}" data-act="slot-in" data-id="${esc(a.id)}" data-i="${pick}" data-ins="${esc(i.id)}"${glowSlot} ${fits(i) ? "" : "disabled"} title="${esc(fits(i) ? i.skill_desc || "" : `這一格${ringWord(c)}`)}">${ringHtml([i.attribute], "", "jmini")}<span>「${esc(i.name)}」${lookSeal(i.look)}<small>${fxHtml(i.fx) || `〔${esc(i.skill || "")}〕${lvHtml(i.strength)}`}${fits(i) ? "" : "・顏色不合"}</small>${a.stack && a.stack[i.id] ? `<em class="stk">${esc(a.stack[i.id])}</em>` : ""}</span></button>`).join("")
        : '<span class="muted">手上沒有空著的意境——去探索悟一個，或從別門武學上拆下來。</span>'}</div>`;
    }
    // 第五個玉環（自創的才有，招式與絕學稿案第三節）：破境了亮金色寫絕招，還沒破境是暗的
    const f = a.fifth;
    const fifth = !f ? "" : f.on
      ? `<span class="jd fifth on" title="絕招〔${esc(f.name)}〕">${ringHtml([], `<b>絕</b>`, "gold")}<small>〔${esc(f.name)}〕</small></span>`
      : `<span class="jd fifth" title="${esc(f.note)}">${ringHtml([], "<i>絕</i>", "vacant")}<small class="dim">${esc(f.note)}</small></span>`;
    return `<div class="jade">${cells}${fifth}</div>${picker}`;
  }

  // 衝關鈕（Joy 2026-10-21「把破境丹也加入商城，取消可以用心得衝」）：只剩服丹衝關，手上有丹、到了極處才亮；
  // 沒丹時這一格只寫等契機（丹從探索、醫館與萬寶閣來）。序章點名的那一顆照舊發光。字待 joy 潤
  function breakBtns(a, has) {
    const lg = a.cultivate.legend;
    const glow = has("cultivate") ? ' data-glow="cultivate"' : "";
    if (lg) return `<div class="pk-btns"><button class="btn small primary" data-act="cultivate" data-by="pill"${glow} data-id="${esc(a.id)}">服丹衝關<small>剩 ${lg.count | 0} 枚</small></button></div>`;
    // 到了極處、手上沒丹：一顆去萬寶閣的鈕，打開就停在破境丹那一件（Joy 2026-10-21「破境丹沒有可以引導他去商城」）。字待 joy 潤
    if (a.cultivate.shop) return `<div class="pk-btns"><button class="btn small" data-act="mall-goto" data-id="${esc(a.cultivate.shop)}">去萬寶閣<small>買破境丹</small></button></div>`;
    return has("cultivate") ? `<div class="pk-btns"><button class="btn small" data-act="cultivate"${glow} data-id="${esc(a.id)}" disabled>衝關</button></div>` : "";
  }

  // 衝關的小動畫（Joy 2026-10-21「衝關那邊做一個小動畫，可以運用到玩家畫的火柴人武學，分成功跟失敗」）：
  // 那一門的火柴人（自創的是玩家自己擺的式，學來的照兵器挑的架式）運氣、衝向一道「關」。衝開了關碎成幾塊、金光、蓋「破境」；
  // 沒衝開撞上去、關裂一道縫、人被彈回來、蓋「彈回」。點一下或播完就收掉；破境卡（ascendCard）在它底下，收掉就看得到。
  // 減少動態的人不播（結果那一句照樣寫在修練頁）。字待 joy 潤
  function breakAnim(a, won) {
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const old = document.getElementById("cg-anim");
    if (old) old.remove();
    const box = document.createElement("div");
    box.id = "cg-anim";
    box.className = `cg-wrap ${won ? "won" : "lost"}`;
    const bricks = [0, 1, 2, 3, 4].map((k) => `<g class="cg-brick b${k}"><rect x="262" y="${28 + k * 38}" width="34" height="36" rx="3"/><line x1="268" y1="${40 + k * 38}" x2="290" y2="${40 + k * 38}"/></g>`).join("");
    box.innerHTML = `<div class="cg-stage" role="img" aria-label="${won ? "衝關成功" : "衝關失敗"}">
      <svg class="cg-scene" viewBox="0 0 360 240" aria-hidden="true">
        <line class="cg-ground" x1="0" y1="222" x2="360" y2="222"/>
        <circle class="cg-burst" cx="279" cy="122" r="20"/>
        <g class="cg-gate">${bricks}<text class="cg-guan" x="279" y="132">關</text></g>
        <path class="cg-crack" d="M279 40 L272 82 L286 110 L270 150 L284 196"/>
        <g class="cg-man"><circle class="cg-aura a1" cx="90" cy="130" r="46"/><circle class="cg-aura a2" cx="90" cy="130" r="46"/>
          <svg class="fig cg-fig" x="20" y="22" width="140" height="200" viewBox="30 40 160 200">${figBody(a.pose || {}, a.weapon, false)}</svg></g>
      </svg>
      <p class="cg-stamp">${won ? "破境" : "彈回"}</p>
      <p class="cg-line">${won ? `【${esc(a.name)}】衝開了那一層` : `【${esc(a.name)}】撞在那一層上，又彈了回來`}</p>
    </div>`;
    const close = () => { clearTimeout(timer); box.remove(); };
    const timer = setTimeout(close, 3600);
    box.addEventListener("click", close);
    document.body.appendChild(box);
  }

  function pagePractice() {
    const x = S.menxia;
    if (!x) return '<p class="muted">載入中…</p>';
    // 自創武學從煉製搬到修練（招式與絕學稿案第四輪）：自創本身還是整頁
    if (S.createOpen && S.main && S.main.status && S.main.status.create && S.main.status.create.on) return createPageHtml();
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
      const level = Math.max(0, Math.min(10, a.level | 0));
      // 序章指路（T7 走查 W-A）：卡裡哪幾顆鈕發光由伺服器說（a.glow，只有序章裡才有；art_rows 照序章的拒絕算過），網頁不猜。
      // data-glow 的鍵寫成字面（test_content 掃 app.js 對照 models.GLOW_KEYS，內容才叫得動它們）
      const has = (key) => (a.glow || []).includes(key);
      // 練成（Joy 2026-10-20「練成第x成這邊介面按鈕超醜」）：十成的格子旁邊一顆朱印「練」，下一格會亮；按不下去時印是灰的、原因寫在底下一行
      let train = "", why = "";
      if (slot) {
        why = slot.blocked || "";
        const off = !!slot.blocked || slot.maxed;
        const label = slot.maxed ? "已到第十成" : `練成第${level + 1}成（心得 ${slot.price}）`;
        train = `<button class="train-go${off ? "" : " hot"}" data-act="mx" data-op="practice" data-glow="practice" data-kind="${esc(a.kind)}" aria-label="${esc(slot.blocked || label)}" title="${esc(slot.blocked || label)}" ${off ? "disabled" : ""}><b>${slot.maxed ? "滿" : "練"}</b><small>${slot.maxed ? "十成" : `心得 ${slot.price}`}</small></button>`;
      }
      const next = slot && !slot.blocked && !slot.maxed ? level : -1; // 練下去會亮的那一格
      const pips = `<div class="ten">${Array.from({ length: 10 }, (_, k) => `<i${k < level ? ' class="on"' : k === next ? ' class="next"' : ""}></i>`).join("")}</div>`;
      const switchBtn = slot ? "" : `<div class="acts"><button class="btn" data-act="switch"${has("switch") ? ' data-glow="switch"' : ""} data-id="${esc(a.id)}">改練這一門<small>換上身，熟練度各自保留</small></button></div>`;
      // 衝絕學（武學重構）：只有上品還沒成絕學的才有這一塊；到了極處才有「衝關」與破境丹，沒到只寫還差什麼。不寫下一品是哪一品（企劃者 2026-10-06）
      const ripe = a.cultivate.ok;
      const peakOn = ripe || has("cultivate") || (a.quality === "上品" && (a.slots || []).length > 0);
      const peak = !peakOn ? "" : `<div class="peak${ripe ? " ready" : ""}">
          <div class="pk-txt"><b>破境</b><small class="cnote">${esc(a.cultivate.legend ? a.cultivate.legend.note : a.cultivate.note)}</small></div>
          ${breakBtns(a, has)}
        </div>`;
      const info = S.artInfo === a.id;
      // 功法庫的卡：跟身上同一種那門的比較（W6）直接寫在鈕的上面，改練之前看得到，不必先點「詳情」；點開詳情時功法卡裡也有，這裡就不重複
      const compare = !slot && a.compare && !info ? `<p class="cmp">${esc(a.compare)}</p>` : "";
      return `<div class="train">
          <div class="tr-meter"><div class="tr-lv"><b>第${level}成</b>${typeof a.score === "number" ? `<span class="score">評 ${a.score}</span>` : ""}</div>${pips}</div>
          ${train}
        </div>
        ${why ? `<p class="train-why">${esc(why)}</p>` : ""}
        <div class="lvline"><span>${esc(a.kind)}${a.attribute ? `・屬${esc(a.attribute)}` : ""}・收${esc(a.affinity || "")}</span></div>
        ${slotsHtml(a, x)}
        ${a.tactic && !info ? `<p class="art-tactic">${tacticHtml(a.tactic)}</p>` : ""}
        ${compare}
        ${switchBtn}
        ${S.artNote && S.artNote.id === a.id ? `<div class="msg art-result">${S.artNote.html}</div>` : ""}
        ${peak}
        <div class="more">
          ${a.melt.ok ? "" : `<span class="why">${esc(a.melt.note)}</span>`}
          <button class="linkish" data-act="melt"${has("melt") ? ' data-glow="melt"' : ""} data-id="${esc(a.id)}" data-name="${esc(a.name)}" data-confirm="${esc(a.melt.confirm)}" ${a.melt.ok ? "" : "disabled"} title="${esc(a.melt.note)}">熔煉${a.melt.ok ? `（${/^退回/.test(a.melt.note) ? esc(a.melt.note.replace(/^退回/, "")) : "只空出一格"}）` : ""}</button>
          <button class="linkish" data-act="art-info" data-id="${esc(a.id)}" aria-expanded="${info}">詳情 ${info ? "▴" : "›"}</button>
        </div>
        ${info ? `<div class="art-card">${tenCells(a.card)}</div>` : ""}`;
    };
    // 一門武學在抽屜裡的樣子（招式與絕學稿案第四輪：身上的兩門、庫裡的都進同一個抽屜）：印記、名字、品相，底下是卡的本體
    const artSheet = (a, slot) => `<div class="acard${a.quality === "絕學" ? " q4" : ""}"${a.worn ? ` data-worn="${esc(a.kind)}"` : ""}>
        <div class="hd">${a.quality === "絕學" ? '<span class="qseal q4 big">絕</span>' : ""}<div><h3>${esc(a.name)}</h3><div class="sub">${[a.kind, a.look].filter(Boolean).map(esc).join("・")}</div></div>${a.pose ? figSvg(a.pose, a.weapon, "card-fig") : ""}${a.worn ? '<span class="worn">身上</span>' : ""}</div>
        ${a.tier && a.quality !== "絕學" ? lookLadder(a.tier, ART_LOOK_STEPS) : ""}
        ${body(a, slot)}</div>`;
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
    // 功法庫一列（招式與絕學稿案第四輪）：印記、名字、招、品相、換上後的戰力；點了開抽屜（詳情、改練、熔煉都在裡面）
    const libRow = (a) => {
      const todo = ["switch", "cultivate", "melt"].filter((key) => (a.glow || []).includes(key)).join(" ");
      const open = S.artOpen === a.id;
      const mark = sealOf(a.tactic), move = moveOf(a.tactic);
      const diff = typeof a.might === "number" && typeof x.might === "number" ? a.might - x.might : 0;
      return `<button class="art libr ${open ? "on" : ""}" data-act="art" data-id="${esc(a.id)}"${todo && !open ? ` data-glow="${todo}"` : ""}>${mark ? tsealHtml(mark) : ""}<span class="txt"><b>${esc(a.name)}</b><small>${[move ? `〔${move}〕` : "", a.tier || ""].filter(Boolean).map(esc).join("・")}</small></span>${typeof a.might === "number" ? `<span class="lib-might${diff > 0 ? " up" : diff < 0 ? " down" : ""}">戰力 ${x.might | 0} → ${a.might | 0}</span>` : ""}</button>`;
    };
    const libGroups = (list) => KINDS.map((k) => {
      const rows = list.filter((a) => a.kind === k);
      return rows.length ? `<div class="sub lib-kind">${k}</div><div class="lib">${rows.map(libRow).join("")}</div>` : "";
    }).join("");
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
    // 意境（招式與絕學稿案第四輪）：籤改成列——玉環、名字、品相、效果一行、裝在哪；沒裝的排前面。點了開抽屜（意境卡）
    const insOpen = x.insights.find((i) => i.id === S.insOpen);
    const insF = S.insFilter || "all";
    const insPass = (i) => insF === "all" || (insF === "free" ? !i.slotted : !!i.slotted);
    const insList = x.insights.filter(insPass).sort((p, q) => Number(!!p.slotted) - Number(!!q.slotted));
    const insRow = (i) => `<button class="insr${S.insOpen === i.id ? " on" : ""}" data-act="ins-open" data-id="${esc(i.id)}">${ringHtml([i.attribute], i.own && i.glyph ? glyphSvg(i.glyph, "glyph-mini") : `<b>${esc(String(i.name).slice(0, 1))}</b>`, "jmini")}<span class="txt"><b>「${esc(i.name)}」${lookSeal(i.look)}</b><small>${esc(fxText(i.fx) || i.depth || "")}${i.slotted ? `・裝在【${esc(i.slotted)}】` : ""}</small></span></button>`;
    const INS_FILTERS = [["all", "全部"], ["free", "沒裝的"], ["used", "裝著的"]]; // 待 joy 潤
    const insFilterRow = x.insights.length > 3 ? `<div class="lib-filter">${INS_FILTERS.map(([f, label]) => `<button class="${insF === f ? "on" : ""}" data-act="ins-filter" data-filter="${f}">${label} ${x.insights.filter((i) => f === "all" || (f === "free" ? !i.slotted : !!i.slotted)).length}</button>`).join("")}</div>` : "";
    // 名冊只有本人一列（還沒有同伴）時跟上面的本人卡重複，不畫（C6）
    const mates = x.roster.length > 1;
    // 裝備（裝備四欄設計 2.5）：開著的欄位一段一段（武器、防具、坐騎、寶物），每段先列身上那件、再列裝備庫裡同一欄的。
    // 格數四欄合算（gear.used／gear.cap）。字都是伺服器給的資料，一律 esc。這一版畫不出的欄位（新伺服器多了一欄）整段略過。
    // FB-125（兵器第二批 Task 1）：名字與說明在左邊（.winfo，塞不下自己折行），「換上」「拆解」包在右邊一個不折行的 .wbtns 裡；拆解按了先問一次（data-confirm）
    const gear = x.gear;
    // 換上後的戰力（招式與絕學稿案第四輪）：跟人形圖上那個數比，強了綠、弱了紅
    const mightTag = (w) => (typeof w.might === "number" && typeof x.might === "number"
      ? `<small class="lib-might${w.might > x.might ? " up" : w.might < x.might ? " down" : ""}">換上後戰力 ${x.might | 0} → ${w.might | 0}</small>` : "");
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
        <div class="winfo"><b>【${esc(w.name)}】</b><span>${esc(w.noun || w.kind)}・屬${esc(w.attribute)}${w.grade ? `・${esc(w.grade)}` : ""}${w.tempers ? `・淬煉 ${w.tempers | 0}/${w.temper_max | 0}` : ""}・鋒利度 ${w.edge | 0}${w.bonus ? `・威力 ${esc(w.bonus)}` : "・用不上"}</span>${w.recipe ? `<small class="muted">配方 ${esc(w.recipe)}</small>` : ""}${(w.tactic || []).map((t) => `<small class="gear-tactic">${esc(t)}</small>`).join("")}${w.wield_ok === false && !wornNow ? `<small class="rwhy">${esc(w.wield_note || "")}</small>` : ""}${wornNow ? "" : mightTag(w)}</div>
        ${wornNow ? "" : rowButtons(w)}
      </div>${w.divine ? divineForm(w) : ""}${bindForm(w)}`;
    // 防具：不分種類、沒有「配不上」；寫耐久度與這件一場少扣幾成氣血、對不對得上你的內功（裝備四欄設計 4.1、4.2）。
    // 磨損的叫法照伺服器給的 wear_word（equipment.WEAR_WORDS，2.5、3.1），不寫死。這一行的寫法待 joy 潤；淬過的寫「淬煉 N/M」、自己打的寫配方（防具打造，同武器列）
    const armorRow = (a, wornNow) => `<div class="wrow">
        <div class="winfo"><b>【${esc(a.name)}】</b><span>屬${esc(a.attribute)}・${esc(a.grade)}${a.tempers ? `・淬煉 ${a.tempers | 0}/${a.temper_max | 0}` : ""}・${esc(a.wear_word)} ${a.edge | 0}・少扣 ${esc(a.cut)} 氣血${a.fit ? `・${esc(a.fit)}` : ""}</span>${a.recipe ? `<small class="muted">配方 ${esc(a.recipe)}</small>` : ""}${(a.tactic || []).map((t) => `<small class="gear-tactic">${esc(t)}</small>`).join("")}${a.wield_ok === false && !wornNow ? `<small class="rwhy">${esc(a.wield_note || "")}</small>` : ""}${wornNow ? "" : mightTag(a)}</div>
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
        <div class="winfo"><b>【${esc(h.name)}】</b><span>${esc(h.grade)}・${esc(h.wear_word)} ${h.edge | 0}・疾行省 ${esc(h.save)} 體力・路上快 ${esc(h.speed)}・決戰強攻奇襲 +${esc(h.cavalry)}・落敗脫身 ${esc(h.escape)}</span>${why ? `<small class="rwhy">${esc(why)}</small>` : ""}${wornNow ? "" : mightTag(h)}</div>
        <div class="wbtns">${wornNow
          ? (h.feed ? `<button class="btn small" data-act="feed">餵${h.feed_note ? `（${esc(h.feed_note)}）` : ""}</button>` : `<button class="btn small" data-act="feed" disabled${why ? ` title="${esc(why)}"` : ""}>餵</button>`)
          : `<button class="btn small" data-act="wield" data-id="${esc(h.id)}"${h.wield_ok ? "" : ` disabled${why ? ` title="${esc(why)}"` : ""}`}>換上</button>`}</div>
      </div>`;
    };
    // 寶物（裝備四欄設計第六節）：一件一種效果、不分階品、不磨損；身上那件寫效果，裝備庫裡的只有「換上」（寶物不能拆，4.8，不用 rowButtons）。
    // 寶物隨時能換（2.3【定】，企劃者 2026-10-11），「換上」不灰掉。這一行的寫法待 joy 潤
    const treasureRow = (t, wornNow) => `<div class="wrow">
        <div class="winfo"><b>【${esc(t.name)}】</b><span>${esc(t.effect_text)}</span>${wornNow ? "" : mightTag(t)}</div>
        ${wornNow ? "" : `<div class="wbtns"><button class="btn small" data-act="wield" data-id="${esc(t.id)}">換上</button></div>`}
      </div>`;
    // 修練頁其他動作的結果（mxPlace）：寫在按的那一塊裡，頁首那一行不寫
    const noteAt = (at) => S.mxNote && S.mxNote.at === at ? `<div class="msg mx-note">${S.mxNote.html}</div>` : "";
    const GEAR_ROWS = { weapon: weaponRow, armor: armorRow, mount: mountRow, treasure: treasureRow };
    const slotBlock = (g) => {
      const row = GEAR_ROWS[g.slot];
      if (!row) return "";
      const shown = S.rackAll || g.rack.length <= LIB_PAGE ? g.rack : g.rack.slice(0, LIB_PAGE);
      // 傳承那一列（玉璽碎片的抄本，玉璽碎片設計 7.3）：寶物段身上那件之前；有獨門行動的碎片多一顆鈕（heirloomRow，改版第 2 批）；
      // 寶物的開關關著、只有傳承時不寫「身上沒有寶物」（待 joy 潤）
      return `<section class="gear-slot" data-slot="${esc(g.slot)}"><div class="sub">${esc(g.label)}</div>${noteAt("gear:" + g.slot)}
        ${g.fit_line ? `<p class="muted gear-fit">${esc(g.fit_line)}</p>` : ""}
        ${g.heirloom ? heirloomRow(g.heirloom, sealActNow()) : ""}
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
    // 抽屜（招式與絕學稿案第四輪：點什麼，內容就從底下升起；整頁只用這一個）：庫裡的一門、意境、身上的一門、一欄裝備。
    // S.pdrawer 是點了哪個光點（false 是剛關上）；序章裡師父點名要按的鈕在身上那一門時，沒點過也先攤開那一門
    const stepGlow = (S.main && S.main.prologue && S.main.prologue.glow) || [];
    const tutorWorn = S.pdrawer == null && !S.artOpen && !S.insOpen && (
      x.owned_arts.find((a) => a.worn && ["slot", "cultivate", "melt"].some((k) => stepGlow.includes(k) && (a.glow || []).includes(k)))
      || (stepGlow.includes("practice") && x.owned_arts.find((a) => a.worn && practiceOk(x, a.kind))));
    const pd = S.pdrawer || (tutorWorn ? { t: "worn", key: tutorWorn.kind } : null);
    let drawerTitle = "", drawerBody = "";
    const openLib = S.artOpen && lib.find((a) => a.id === S.artOpen);
    if (openLib) {
      drawerTitle = `功法庫・${openLib.kind}`; drawerBody = artSheet(openLib, null); // 抽屜的標題寫是哪一類，名字在卡上
    } else if (insOpen) {
      drawerTitle = "意境"; drawerBody = insightCardHtml(insOpen, { fits: true, melt: true }) + noteAt("ins");
    } else if (pd && pd.t === "worn") {
      const slot = x.slot_cards.find((c) => c.kind === pd.key) || { learned: false };
      const a = x.owned_arts.find((r) => r.worn && r.kind === pd.key);
      drawerTitle = `身上的${pd.key}`;
      drawerBody = a ? artSheet(a, slot) : `<div class="acard empty">${slot.card || `你還沒有${esc(pd.key)}。`}</div>`;
    } else if (pd && pd.t === "gear" && gear) {
      const g = gear.slots.find((sl) => sl.slot === pd.key);
      drawerTitle = g ? g.label : ""; drawerBody = g ? slotBlock(g) : "";
    }
    const drawerHtml = drawerBody ? `<div class="sheet-bg" data-act="drawer-close"></div>
      <div class="sheet pr-sheet" role="dialog" aria-label="${esc(drawerTitle)}"><div class="grip"></div>
        <div class="top-row"><h3 style="flex:1">${esc(drawerTitle)}</h3><button type="button" class="btn small ghost" data-act="drawer-close">關閉</button></div>
        ${drawerBody}</div>` : "";
    return `
      ${proGuide()}
      ${heroPanel(x, s)}
      <div class="msg" id="mx-msg">${S.message}</div>
      ${naming}
      ${attrNoteHtml(x)}
      ${createEntry()}
      <div class="label">功法庫 <small class="muted">武學與意境 ${x.holdings.count}/${x.holdings.cap}</small>${meltSwitch}</div>
      ${S.meltNote ? `<div class="msg melt-result">${S.meltNote}</div>` : ""}
      ${meltOn ? `<p class="muted melt-hint">點一列勾起來，再按底下的「熔掉」；點右邊的 › 看細節。身上正在練的與本命武學熔不掉。</p>
      ${meltTools}
      ${meltList}` : `${chips}
      ${lib.length ? (picked.length ? libGroups(rows) : '<p class="muted">這一類沒有功法。</p>')
        : '<p class="muted">功法庫是空的。合成出來的武學、學來的武學會放在這裡。</p>'}
      ${showAll ? "" : `<button class="btn ghost lib-more" data-act="lib-all">再列 ${picked.length - LIB_PAGE} 門</button>`}`}
      ${meltOn ? "" : `<div class="label">意境</div>
      ${x.insights.length ? `${insFilterRow}${insList.length ? `<div class="lib insl">${insList.map(insRow).join("")}</div>` : '<p class="muted">這一類沒有意境。</p>'}`
        : '<p class="muted">還沒悟到任何意境。去探索，荒郊野外最容易有所領悟。</p>'}`}
      ${gearBlock}
      <div class="label">門下</div>
      <details class="fold" open><summary>本人</summary><div class="fold-body">${tenCells(x.player_card)}</div></details>
      ${mates ? `<div class="list">${x.roster.map((r) => `<button class="${x.person === r.key ? "on" : ""}" data-act="person" data-key="${esc(r.key)}">${esc(r.label)}</button>`).join("")}</div>` : ""}
      ${mates && x.person ? `<div class="card person-card">${tenCells(x.person_card)}${noteAt("person")}
        ${x.person === "player" ? '<p class="muted">本人一直都在隊伍裡。</p>' // 本人不能加入、移出（引擎也會擋）
          : x.person.startsWith("follower:") ? "" // 部下（計畫 T5）也不能加入、移出；角色卡已經寫了
          : `<button class="btn ${x.on_team ? "" : "primary"}" data-act="mx" data-op="${x.on_team ? "leave" : "join"}">${x.on_team ? "移出隊伍" : "加入隊伍"}</button>`}
        ${x.release ? `<button class="btn ghost" data-act="release-mate" data-confirm="${esc(x.release.confirm)}">放他回江湖</button>` : ""}
        ${lessonsHtml(x.lessons)}</div>` : ""}
      <div class="tune">
        ${healButton(x, s.injury)}
        <form id="seclude" class="seclude">
          <button class="btn" type="submit" ${x.seclude_blocked ? "disabled" : ""}>閉關<small>得心得，氣血回復加倍</small></button>
          <select class="input" name="hours" aria-label="閉關幾小時">${[1, 2, 4, 6, 8, 12].map((h) => `<option value="${h}" ${h === 8 ? "selected" : ""}>${h} 小時</option>`).join("")}</select>
        </form>
      </div>
      ${noteAt("heal")}
      ${x.seclude_blocked ? `<p class="muted">${esc(x.seclude_blocked)}</p>` : ""}
      <details class="fold"><summary>修練的規矩</summary><div class="fold-body">${x.rules}</div></details>
      ${meltGo}
      ${meltOn ? "" : drawerHtml}`;
  }

  // 傳功門下（Config.chuangong）：人物卡底下一排鈕，鈕上寫要練什麼與心得，底下一行寫效果；按不下去的灰掉、原因寫在效果那一行
  function lessonsHtml(rows) {
    if (!rows || !rows.length) return "";
    return `<div class="label">傳功</div><div class="lessons">${rows.map((r) =>
      `<button class="btn small" data-act="teach" data-what="${esc(r.what)}" ${r.problem ? "disabled" : ""}${r.problem ? ` title="${esc(r.problem)}"` : ""}>${esc(r.label)}<small>${esc(r.problem || r.effect)}</small></button>`).join("")}</div>`;
  }

  // ── 煉製 ──
  const QUALITY_RANK = { 下品: 1, 中品: 2, 上品: 3, 絕學: 3 };
  // 爐裡放的東西 → 送給伺服器的 body：只有意境（武學不再拿來合，Joy 2026-10-21）
  function forgeBody() {
    return { insights: S.forgeSel.filter((p) => p.type === "ins").map((p) => p.id) };
  }
  // 兩個意境才放得滿（不同的合併、同一種的兩份揣摩）
  function forgeReady() {
    return forgeBody().insights.length === 2;
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
    if (type !== "ins") return; // 爐裡只合意境
    const no = pickMark(type, id);
    if (no) { toast(no.why); return; } // 跟爐裡那一樣合不了（伺服器照開爐時的判斷算好的）：說為什麼，不放進去
    S.forgeSel.push({ type, id });
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
    return (type === "ins" && p.insights[id]) || null;
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
    const attrs = [...new Set(x.insights.map((i) => i.attribute))].sort();
    const quals = [...new Set(x.insights.map((i) => i.look).filter(Boolean))].sort((a, b) => "凡佳珍神".indexOf(a) - "凡佳珍神".indexOf(b));  // 意境的品相（凡佳珍神，新手引導重做：不再寫底子的中品）
    const sel = (key, label, opts) => `<select class="input" data-act="craft-view" data-key="${key}" aria-label="${label}">${opts.map(([val, text]) =>
      `<option value="${esc(val)}"${v[key] === val ? " selected" : ""}>${esc(text)}</option>`).join("")}</select>`;
    const pot = S.forgeSel.length === 1 && S.forgePicks;
    return `<div class="craft-filter">
      ${sel("attr", "屬性", [["", "屬性"], ...attrs.map((a) => [a, `屬${a}`])])}
      ${sel("quality", "品相", [["", "品相"], ...quals.map((q) => [q, `${q}品`])])}
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
  // 爐火（招式與絕學稿案第五輪，Joy 2026-10-21「火候用文字加爐火圖」）：四段，火苗一到四簇、越旺越亮；不寫品級、不寫機率
  const FLAME = "M6 0C7 4 11 6 11 11a5 5 0 0 1-10 0C1 8 3 7 3 4c1 2 2 3 3 3C6 5 5 3 6 0Z";
  function fireHtml(f, small) {
    if (!f) return "";
    const lv = Math.max(0, Math.min(3, f.level | 0));
    const flames = Array.from({ length: lv + 1 }, (_, k) => `<path d="${FLAME}" transform="translate(${k * 9},${k % 2 ? 2 : 0})"/>`).join("");
    return `<span class="fire f${lv}${small ? " small" : ""}"><svg viewBox="0 -1 ${12 + lv * 9} 18" aria-hidden="true">${flames}</svg><b>${esc(f.word)}</b>${small ? "" : `<span>${esc(f.line)}</span>`}</span>`;
  }
  function kilnPeek(v) {
    const merge = v.kind === "合併";
    const badge = merge ? '<span class="qseal qi">意</span>' : v.quality ? seal(v.quality) : '<span class="qseal q1">？</span>';
    const head = [v.made, v.attribute ? `屬${v.attribute}` : "", merge ? v.depth : v.gen, v.level > 1 ? `第${v.level}成` : ""].filter(Boolean).map(esc).join("・");
    const tags = (v.traits || []).map((t) => `${esc(t.name)}${t.layers > 1 ? ` ×${t.layers}` : ""}`);
    const line2 = [tags.length ? `功效 ${tags.join("、")}` : "", v.slots, v.near].filter(Boolean).map(esc).join("・");
    return `<button type="button" class="kiln-peek" data-act="peek" aria-label="看整張預覽卡">${badge}<span><b>${head}</b>${line2 ? `<small>${line2}</small>` : ""}</span>${fireHtml(v.fire, true)}</button>
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
  function fixedKiln(quiet) {
    const wrap = document.getElementById("kiln-wrap"), kiln = document.getElementById("kiln");
    if (!wrap || !kiln || typeof wrap.getBoundingClientRect !== "function" || !kiln.classList) return;
    const head = document.getElementById("top");
    const topH = head && !head.hidden ? head.offsetHeight : 0;
    const compact = wrap.getBoundingClientRect().bottom < topH + 90;
    if (compact === kiln.classList.contains("compact")) return;
    if (compact) wrap.style.minHeight = `${wrap.offsetHeight}px`; // 縮起來前先撐住原本的高度，頁面才不往上跳
    kiln.classList.toggle("compact", compact);
    kiln.classList.toggle("still", compact && !!quiet);
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
    if (item.type === "ins") { // 出爐卡（第五輪）：跟修練頁抽屜同一張意境卡；剛出爐那一下有排場（S.forgeReveal：爐火一閃、卡翻面、品相印最後蓋上）
      const i = (x.insights || []).find((r) => r.id === item.id);
      return i ? `<div class="made-card ins-made">${insightCardHtml(i, { fits: true, reveal: !!S.forgeReveal })}</div>` : "";
    }
    const a = (x.owned_arts || []).find((r) => r.id === item.id);
    if (!a) return "";
    const j = a.judge || {};
    const sub = [a.kind, a.attribute ? `屬${a.attribute}` : "", a.affinity ? `收${a.affinity}` : "", `第${a.level}成`].filter(Boolean);
    const diff = typeof j.worn_diff === "number" ? j.worn_diff : null;
    const verdict = diff === null ? ""
      : diff > 0 ? `<b class="up">比身上那門強 ${meltNum(diff)}</b>` : diff < 0 ? `<b class="down">比身上那門弱 ${meltNum(diff)}</b>` : "跟身上那門一樣";
    const tags = [];
    (j.traits || []).forEach((t) => tags.push(`<i class="tr${t.tier ? ` t${t.tier}` : ""}">${t.tier && TRAIT_TIERS[t.tier] ? `<em>${TRAIT_TIERS[t.tier]}</em>` : ""}${esc(t.name)}${t.layers > 1 ? `<small>${t.layers} 層</small>` : ""}</i>`));
    if (j.special) tags.push(`<i class="tr t2"><em>中</em>${esc(j.special)}</i>`); // 來路帶的特別功效：中階
    (j.dormant || []).forEach((n) => tags.push(`<i class="tr off"><em>未開</em>${esc(n)}</i>`));
    if (j.ultimate) tags.push(`<i class="hi">${tsealHtml("絕")}〔${esc(j.ultimate)}〕</i>`);
    if (j.tactic) tags.push(`<i class="hi">${tsealHtml(j.tactic_title || "本命")}〔${esc(j.tactic)}〕</i>`);
    (a.slots || []).forEach((t) => tags.push(t ? `<i class="tr t2"><em>槽</em>「${esc(t.name)}」〔${esc(t.skill)}〕${esc(t.mark)}</i>` : `<i class="tr off">空槽</i>`));
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
    const pair = merge || v.kind === "揣摩"; // 意境＋意境：品質照兩份裡好的，另寫真意機會
    const verdict = pair ? `${fireHtml(v.fire)}${merge && v.depth ? `<span class="muted">${esc(v.depth)}</span>` : ""}`
      : v.quality ? `<b>${esc(v.quality)}</b>${v.why && v.why.length ? `<span class="muted">・${v.why.map(esc).join("；")}</span>` : ""}${v.near ? `<span class="near">・${esc(v.near)}</span>` : ""}`
      : `品質看造化：${esc(v.odds || "")}`;
    const tags = (v.traits || []).map((t) => t.grand ? `<i class="tr grand${t.maybe ? " maybe" : ""}">${esc(t.name)}<small>真意</small></i>`
      : t.special ? `<i class="tr sp">${esc(t.name)}</i>`
      : `<i class="tr${t.maybe ? " maybe" : ""}">${esc(t.name)}${t.maybe ? "" : lvHtml(t.layers)}</i>`); // 待 joy 潤
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
  // 序章裡點名的那一格（pick:insight）：抽屜關著時亮在爐子的空格上（點了開抽屜，裡面那一顆再亮）
  function potGlow() {
    return S.craftPick ? "" : ' data-glow="pick:insight"';
  }
  // 挑東西放進爐的抽屜（Joy 2026-10-19 決策卡選「點格子開抽屜」：爐子、預覽卡、開爐永遠在第一屏，清單再長也不用捲頁）：
  // 點爐子的空格從底下升起，篩選、武學、意境都在裡面；點一樣就放進去，兩格放滿自動收起、預覽當場更新；放了一樣還缺一樣就留著接著挑。
  // 清單本身（craftChip、篩選、再列、合不了的灰掉）跟以前在頁面上的一模一樣
  function craftSheetHtml(x) {
    // 抽屜本來就開著（放了一樣、篩選、再列時重畫）：不再從底下升上來一次（Joy 2026-10-22「合成前點第一個素材時畫面也會閃一下」）
    const still = document.querySelector(".craft-sheet") ? " still" : "";
    return `<div class="sheet-bg${still}" data-act="pot-close"></div>
      <div class="sheet craft-sheet${still}" role="dialog" aria-label="挑東西放進爐">${craftSheetInner(x)}</div>`;
  }
  function craftSheetInner(x) {
    const v = craftView();
    const keep = (type, thing) => (!v.attr || thing.attribute === v.attr) && (!v.quality || thing.look === v.quality) && (!v.okOnly || !pickMark(type, thing.id));
    const order = (list) => v.sort === "name" ? [...list].sort((a, b) => a.name.localeCompare(b.name, "zh-Hant"))
      : v.sort === "attr" ? [...list].sort((a, b) => a.attribute.localeCompare(b.attribute, "zh-Hant")) : list; // 照品質＝伺服器的順序
    const ins = order(x.insights.filter((i) => keep("ins", i)));
    const first = S.forgeSel[0];
    const held = first ? x.insights.find((r) => r.id === first.id) : null;
    const title = !first ? "放一個意境進爐" : held ? `爐裡${isLocked(first) ? "鎖著" : "有"}「${esc(held.name)}」，再放一個` : "再放一個";
    return `
        <div class="grip"></div>
        <div class="top-row"><h3 style="flex:1">${title}</h3><button type="button" class="btn small ghost" data-act="pot-close">關閉</button></div>
        ${craftFilterRow(x)}
        <div class="label">意境 <small class="muted">不同的合出新的意境，同一種的兩份是揣摩</small></div>
        ${x.insights.length ? (ins.length ? `<div class="chips">${ins.map((i) => craftChip("ins", i, `${i.look ? `${i.look}品` : ""}・屬${i.attribute}${i.lean !== "無" ? `・${i.lean}` : ""}・${fxText(i.fx) || i.depth || ""}`, i.grand ? 3 : 2,
          (i.glow || []).includes("pick:insight") && !S.forgeSel.some((p) => p.type === "ins" && p.id === i.id) ? ' data-glow="pick:insight"' : "")).join("")}</div>`
          : '<p class="muted">沒有合這些條件的意境。</p>')
          : '<p class="muted">還沒悟到任何意境。去探索，荒郊野外最容易有所領悟。</p>'}`;
  }
  function pageCraft() {
    const x = S.menxia;
    if (!x) return '<p class="muted">載入中…</p>';
    // 爐子兩格要畫的：意境寫「意境」與屬性（找不到就當空格）
    const slotOf = (p) => {
      if (!p) return null;
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
      ${ready ? "" : `<button type="button" class="btn pot-open" data-act="pot-open">${S.forgeSel.length ? "再放一樣進爐" : "挑東西放進爐"}<small>意境的清單</small></button>`}
      ${result}
      ${attrNoteHtml(x)}
      ${x.clue_items?.length ? `<div class="label">伏筆物品</div>
      <div class="chips clues">${x.clue_items.map((i) => `<div class="clue"><b>${esc(i.name)}</b><span>×${i.count}</span></div>`).join("")}</div>` : ""}
      ${manualEntry("arts")}${manualEntry("forge")}
      <details class="fold"><summary>背包</summary><div class="fold-body">${x.bag}</div></details>
      ${S.craftPick ? craftSheetHtml(x) : ""}`;
  }

  // 自創武學（Joy 2026-10-20：先選兵器、擺姿勢當圖示、寫一句意，槽分顏色）：煉製頁爐子底下一塊，五步——
  // 執器（內功／武學、兵器或行功之法，menxia create_begin）→ 擺式（拖火柴人，menxia create_pose）→ 立意（一句 2～20 字的意，
  // /api/do/create_intent 請模型讀）→ 成形（伺服器擲好四格顏色，這裡畫成玉環）→ 立名（menxia create_name；重來 create_back、作罷 create_cancel）。
  // 資料全是伺服器給的 status.create（create.view）；擺式時讀出的偏向網頁先照同一套規則算給人看，擺定那一下以伺服器為準。字待 joy 潤
  const CREATE_STEPS = [["form", "執器"], ["pose", "擺式"], ["intent", "立意"], ["name", "成形・立名"]];
  const biasHtml = (bias) => Object.entries(bias || {}).sort((p, q) => q[1] - p[1]).map(([k]) => ringHtml([k], esc(k), "jchip")).join("");
  function createHtml() {
    const c = S.main && S.main.status && S.main.status.create;
    if (!c || !c.on) return "";
    const step = c.step, at = CREATE_STEPS.findIndex((p) => p[0] === step);
    const head = c.left == null ? "" : `<p class="muted small cr-left">本季還可自創 ${c.left | 0} 門</p>`;
    const steps = `<ol class="cr-steps">${CREATE_STEPS.map(([k, w], i) => `<li class="${i === at ? "on" : i < at ? "done" : ""}">${w}</li>`).join("")}</ol>`;
    const draft = c.draft;
    if (step !== "pose") S.createPose = null;
    if (!draft) {
      if (c.problem) return `${head}<div class="card create"><p class="muted">${esc(c.problem)}</p></div>`;
      const f = S.createPick || (S.createPick = { kind: c.kinds.includes("武學") ? "武學" : c.kinds[0], form: "" });
      const forms = (c.forms && c.forms[f.kind]) || [];
      const kinds = c.kinds.map((k) => `<button type="button" class="fchip${f.kind === k ? " on" : ""}" data-act="create-kind" data-val="${esc(k)}">${esc(k)}</button>`).join("");
      const tiles = forms.map((o) => `<button type="button" class="cr-form${f.form === o.key ? " on" : ""}" data-act="create-pick" data-val="${esc(o.key)}">
          ${f.kind === "武學" ? figSvg((c.presets.find((p) => p.name === ({ 拳腳: "起手", 棍: "守禦", 弓弩: "奇變" }[o.key] || "進擊")) || {}).angles, o.key, "tile-fig") : ""}
          <b>${esc(o.key)}</b><span class="cr-bias">${biasHtml(o.bias)}</span><small>${esc(o.blurb)}</small></button>`).join("");
      return `${head}<div class="card create">${steps}
        <p class="muted">花心得立一門自己的功夫。手裡拿什麼、擺什麼架式、心裡存什麼意，都會讓它偏向不同的路數。</p>
        <div class="crow"><span>要立</span><div class="fchips">${kinds}</div></div>
        <div class="cr-forms">${tiles}</div>
        <p class="mc-cost">心得 ${c.price | 0}（你有 ${c.xinde | 0} 點）・按下立意那一刻收，之後擱下不退</p>
        <button class="btn primary" data-act="create-begin" ${f.form ? "" : "disabled"}>${f.form ? `握起${esc(f.form)}` : "先挑一樣"}<small>下一步：擺個架式</small></button>
      </div>`;
    }
    const weapon = draft.kind === "武學" ? draft.form : null;
    const sum = `<p class="create-sum"><b>${esc(draft.kind)}</b>・${esc(draft.form)}${draft.intent ? `・意「${esc(draft.intent)}」` : ""}</p>`;
    // 付過心得（立意那一刻收，Joy 2026-10-21）之後作罷不退：鈕上寫明。字待 joy 潤
    const quit = `<button class="btn ghost" data-act="create-cancel">${draft.paid ? "作罷<small>心得不退</small>" : "作罷"}</button>`;
    if (step === "pose") {
      const P = S.createPose || (S.createPose = { ...draft.pose });
      const read = poseRead(P);
      const presets = c.presets.map((p) => `<button type="button" class="fchip" data-act="create-preset" data-val="${esc(p.name)}">${esc(p.name)}</button>`).join("");
      return `${head}<div class="card create">${steps}${sum}
        <div class="cr-rig"><svg id="create-rig" class="fig" viewBox="0 0 220 240" data-weapon="${esc(weapon || "")}"><line class="ground" x1="20" y1="226" x2="200" y2="226"/>${figBody(P, weapon, true)}</svg>
          <div class="cr-side"><p class="muted">拖金色的關節擺出這一門的架式，它會成為這門功夫的圖示。也可以從這幾個起手：</p>
            <div class="fchips wrap">${presets}</div>
            <p class="cr-read" id="create-read">${esc(poseReadText(read.attrs))}</p>
            <p class="muted small" id="create-why">${esc(read.why.length ? `看的是：${read.why.join("、")}。` : "手伸出去、馬步放寬、提腿或前傾，都會讓它偏向一路。")}</p></div></div>
        <div class="acts"><button class="btn primary" data-act="create-pose">擺定<small>下一步：立意</small></button>${quit}</div>
      </div>`;
    }
    if (step === "intent") {
      return `${head}<div class="card create">${steps}${sum}
        <div class="cr-mini">${figSvg(draft.pose, weapon, "cr-fig")}<p>${esc(draft.pose_read)}</p></div>
        <div class="crow"><span>意</span><input class="input" id="create-text" maxlength="${c.intent_max | 0}" placeholder="一句話說這門功夫的神，2～${c.intent_max | 0} 字" value="${esc(S.createText || "")}"></div>
        <p class="muted small">寫得有神有象，底子越厚；意裡帶出的神韻也會讓它偏向那一路。${draft.paid ? "" : `立意那一刻就成形、收心得 ${c.price | 0}，之後擱下不退。`}</p>
        <div class="acts"><button class="btn primary" data-act="create-intent">立意<small>${draft.paid ? "已付過心得" : `心得 ${c.price | 0}`}・下一步：成形</small></button><button class="btn ghost" data-act="create-back" data-to="pose">重擺架式</button>${quit}</div>
      </div>`;
    }
    const rings = (draft.colors || []).map((cc, i) => `<div class="cr-ring">${ringHtml(cc, `<b>${i + 1}</b>`)}<small>${esc(ringWord(cc))}</small></div>`).join("");
    const grade = c.grade || "上品";
    const stance = draft.stance ? `<p class="cr-stance"><b>${esc(draft.stance)}</b>・${esc(draft.timing || "")}${draft.fire ? `・火候 <b class="fire-${esc(draft.fire)}">${esc(draft.fire)}</b>` : ""}</p>` : "";
    const look = draft.tier ? `${lookLadder(draft.tier, ART_LOOK_STEPS)}${(draft.marks || []).length ? `<p class="cr-look tier-${esc(draft.tier)}">${esc(draft.look)}</p>` : ""}` : "";
    const redo = draft.redo > 0 ? `<button class="btn ghost" data-act="create-back" data-to="pose">重擺</button><button class="btn ghost" data-act="create-back" data-to="intent">重立意</button>` : "";
    return `${head}<div class="card create">${steps}
      <div class="cr-made">${figSvg(draft.pose, weapon, "cr-fig big")}<div><p class="create-sum"><b>${esc(draft.kind)}</b>・${esc(draft.form)}</p><p>意「${esc(draft.intent)}」</p><p class="muted small">${esc(draft.pose_read)}・${esc(draft.read_text)}</p></div></div>
      <div class="cr-rings">${rings}</div>
      <p class="muted small">${c.slots[grade] | 0} 格全開。每一格只收自己顏色的意境，八色一圈的什麼都收。</p>
      ${look}
      ${draft.power ? `<p class="muted small">${esc(draft.power)}</p>` : ""}
      ${stance}
      ${draft.tactic ? `<p class="art-tactic cr-move">${tacticHtml(draft.tactic)}</p>` : ""}
      ${draft.say ? `<p class="muted small">出手時：「${esc(draft.say)}」</p>` : ""}
      <p class="muted small">招剛創時還生，練到第四成才使得順。</p>
      ${draft.redo > 0 ? `<p class="muted small">不滿意這個形，可以免費重來一次（重擺或重立意）。</p>` : ""}
      <div class="cr-reroll">${(draft.reroll_left | 0) <= 0 ? `<button class="btn" disabled>重骰<small>這一門已骰滿 ${c.reroll_cap | 0} 次</small></button><span class="muted small">一門最多重骰 ${c.reroll_cap | 0} 次：留下這個形，或回頭重來。</span>`
        : c.rerolls > 0 ? `<button class="btn" data-act="create-reroll">重骰<small>重悟帖 剩 ${c.rerolls | 0} 張</small></button><span class="muted small">同一個架式與意，三格顏色與變招再擲一次。這一門還能重骰 ${draft.reroll_left | 0} 次。</span>`
        // 手上沒帖：引去萬寶閣，停在重悟帖那一件（Joy 2026-10-22「沒有重悟丹不會自動提示玩家去商城購買」；同修練頁沒丹時的破境丹）
        : c.shop ? `<button class="btn" data-act="mall-goto" data-id="${esc(c.shop)}">去萬寶閣<small>買重悟帖</small></button><span class="muted small">重悟帖可以直接重骰這個形，不必重來（一門最多 ${draft.reroll_left | 0} 次）。</span>`
        : `<span class="muted small">萬寶閣的重悟帖可以直接重骰這個形，不必重來（一門最多 ${draft.reroll_left | 0} 次）。</span>`}</div>
      <div class="crow"><span>名字</span><input class="input" id="create-name" maxlength="6" placeholder="2～6 個字，全服不能重名"></div>
      <div class="crow"><span>招名</span><input class="input" id="create-move" maxlength="4" value="${esc(draft.move || "")}" placeholder="2～4 個字"></div>
      <div class="acts"><button class="btn primary" data-act="create-name">立名<small>${draft.paid ? "心得已在立意時付了" : `心得 ${c.price | 0}`}</small></button>${redo}${quit}</div>
    </div>`;
  }
  // 自創單獨一頁（Joy 2026-10-21「創造武學不要卡在煉成的中間」）：入口在修練頁功法庫的頂上（招式與絕學稿案第四輪從煉製搬來），
  // 點了整頁換成自創（S.createOpen），左上「返回修練」。立好或作罷就回修練頁、結果寫在上面。字待 joy 潤
  const CREATE_STEP_WORD = Object.fromEntries(CREATE_STEPS);
  function createEntry() {
    const c = S.main && S.main.status && S.main.status.create;
    if (!c || !c.on) return "";
    const d = c.draft;
    const pose = d ? d.pose : ((c.presets || []).find((p) => p.name === "進擊") || {}).angles;
    const sub = d ? `${esc(d.kind)}・${esc(d.form)}，停在「${esc(CREATE_STEP_WORD[c.step] || "")}」`
      : c.problem ? esc(c.problem) : (c.left == null ? `心得 ${c.price | 0}` : `本季還可自創 ${c.left | 0} 門・心得 ${c.price | 0}`);
    return `<button class="create-entry" data-act="create-open">${pose ? figSvg(pose, d && d.kind === "武學" ? d.form : null, "ce-fig") : ""}<span><b>自創武學</b><small>${sub}</small></span><i class="go">${d ? "接著立 ›" : "開宗立派 ›"}</i></button>`;
  }
  function createPageHtml() {
    return `<div class="cr-page">
      <header class="cr-bar"><button class="book-back" data-act="create-close" aria-label="返回修練">‹ 返回修練</button><span class="cr-bar-title">自創武學</span></header>
      <div class="msg" id="mx-msg">${S.message || ""}</div>
      ${createHtml()}
    </div>`;
  }
  async function createIntent() {
    const box = document.getElementById("create-text");
    if (box) S.createText = box.value;
    await busy(async () => {
      const r = await api("/api/do/create_intent", { text: S.createText || "" });
      applyMain(r.main);
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      if (text) toast(text);
      if (r.main && r.main.status && r.main.status.create && r.main.status.create.step === "name") S.createText = "";
    }, WAIT_LINES.forge || SENT_WAITING);
  }
  // 擺式的拖曳：按在關節上開始，指頭移到哪、那一節就轉向哪裡。只重畫那張圖與讀出來的那兩句，不重畫整頁
  const RIG_DRAG = { head: null, lEl: ["lSh", "lS", []], lHa: ["lEl", "lE", ["lS"]], rEl: ["rSh", "rS", []], rHa: ["rEl", "rE", ["rS"]],
    lKn: ["lHip", "lH", null], lFt: ["lKn", "lK", ["lH"]], rKn: ["rHip", "rH", null], rFt: ["rKn", "rK", ["rH"]] };
  let rigDrag = null;
  const rigNorm = (d) => { while (d > 180) d -= 360; while (d < -180) d += 360; return Math.round(d * 10) / 10; };
  function rigRedraw(svg) {
    const P = S.createPose;
    svg.innerHTML = `<line class="ground" x1="20" y1="226" x2="200" y2="226"/>${figBody(P, svg.dataset.weapon || null, true)}`;
    const read = poseRead(P), out = document.getElementById("create-read"), why = document.getElementById("create-why");
    if (out) out.textContent = poseReadText(read.attrs);
    if (why) why.textContent = read.why.length ? `看的是：${read.why.join("、")}。` : "手伸出去、馬步放寬、提腿或前傾，都會讓它偏向一路。";
  }
  function rigMove(ev) {
    if (!rigDrag || !S.createPose) return;
    const { svg, j } = rigDrag, P = S.createPose;
    const pt = svg.createSVGPoint(); pt.x = ev.clientX; pt.y = ev.clientY;
    const m = pt.matrixTransform(svg.getScreenCTM().inverse()), J = rigJoints(P), r2d = (r) => (r * 180) / Math.PI;
    const spec = RIG_DRAG[j];
    if (!spec) P.t = Math.max(-35, Math.min(35, Math.round(r2d(Math.atan2(-(m.x - RIG.CX), -(m.y - RIG.SY))))));
    else {
      const from = J[spec[0]], a = r2d(Math.atan2(m.x - from.x, m.y - from.y));
      const minus = (spec[2] === null ? 0 : P.t || 0) + (spec[2] || []).reduce((acc, k) => acc + (P[k] || 0), 0);
      P[spec[1]] = rigNorm(a - minus);
    }
    rigRedraw(svg);
  }
  document.addEventListener("pointerdown", (ev) => {
    const t = ev && ev.target, svg = t && t.closest ? t.closest("#create-rig") : null;
    if (!svg || !t.dataset || !t.dataset.j || !S.createPose) return;
    rigDrag = { svg, j: t.dataset.j };
    try { svg.setPointerCapture(ev.pointerId); } catch (e) { /* 舊瀏覽器 */ }
    ev.preventDefault();
  });
  document.addEventListener("pointermove", (ev) => { if (rigDrag) { ev.preventDefault(); rigMove(ev); } }, { passive: false });
  const rigEnd = () => { rigDrag = null; };
  document.addEventListener("pointerup", rigEnd);
  document.addEventListener("pointercancel", rigEnd);

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
    const line = shop.rule ? `<p class="shop-line rule">${esc(shop.rule)}</p>`
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

  // ── 懸賞榜（第四節）：上面一排手上揭著的格子，木板上釘告示（顏色分種類：討伐紅、打探藍、護送綠、求兵金邊、通緝黑；
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

  // 第三層（替一張求兵挑東西）開著時選單上只有那一張的交出鈕與「回到懸賞榜」：放大別張、收起、出店之前先送 bounty:unpick
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

  // ── 商城（商城第二批，docs/superpowers/specs/2026-10-20-商城架構-design.md 4.6；企劃者 2026-10-20 從對比圖挑「子」）：
  // 沿用店面那一層（shopHtml 多一間「mall」）：招牌、掌櫃那一句、左上出店，底下貨架、紀錄兩頁。跟三間店不同，伺服器沒有「人在店裡」
  // 這件事：開不開只在網頁這一邊（S.mallOpen），資料自己抓（/api/mall、/api/mall/records），買是 /api/mall/buy（編號在按下確認那一刻產）。
  // 錢一律寫「元寶」，不寫儲值、付款（這一版沒有金流）。店名、掌櫃的話都是佔位，待 joy 潤 ──
  const MALL_SIGN = "萬寶閣"; // 待 joy
  const MALL_SAY = { // 掌櫃那一句（照停在哪一頁）；待 joy 潤
    shelf: "客官看看。丹藥照顆算，月卡照天數算。",
    log: "帳都在這兒，一筆不差。",
    loading: "掌櫃翻帳中……",
    fail: "帳簿沒拿到，連不上伺服器。",
    empty: "架上這會兒空著，過些時候再來。",
    nolog: "還沒有進出。",
  };
  const MALL_NOTE = "封閉測試先發每個帳號 {n} 元寶，正式開服時清空重來。"; // 貨架底下那一句（封測有發才寫）；待 joy 潤
  const MALL_LOG_NOTE = "只記這個帳號的元寶進出。"; // 待 joy 潤
  // 購買確認：上一筆同一件送出去沒等到回音、貨架也還沒變（不知道成了沒），這一次照同一個編號再送（FB-491）；待 joy 潤
  const MALL_AGAIN = "上一筆「{name}」還沒等到回音：這一次照同一筆再送，已經買好了就不會扣兩次。";
  const MALL_TABS = [["shelf", "貨架"], ["log", "紀錄"]];
  const MALL_NB = "，。、；"; // 貨架上的說明、限購切成不折行的小段（同 nbHtml 的做法，多切「。」）
  // 掌櫃那一句（買成了的、買不了的原因）：切在「，。：；！？」後面與「（」前面，375 寬「元／寶 -600」「（還剩／4300）」不在詞中間斷
  // （打點的 sayHtml 一段超過 14 字就不包，「元寶 -600（還剩 4300）。」整段 18 字照常折行，所以不用它）
  const MALL_SAY_AFTER = "，。：；！？";

  // 元寶的錠子圖示（草圖 mall-mock 的 #ingot）：狀態列的鈕、商城招牌旁的元寶、貨架上的價錢共用；顏色照外面的 class（style.css）
  function ingotSvg() { return '<svg class="ingot" viewBox="0 0 24 16" aria-hidden="true"><path d="M1.5 6.2c1 5.4 5 7.6 10.5 7.6s9.5-2.2 10.5-7.6c-2.2 1.3-4.3 1.6-6 1.1C16 4 14.3 2.2 12 2.2S8 4 7.5 7.3c-1.7.5-3.8.2-6-1.1z"/><path class="shine" d="M8.6 8.4c.6-3.3 1.8-4.8 3.4-4.8s2.8 1.5 3.4 4.8c-2.2.6-4.6.6-6.8 0z"/></svg>'; }

  // 入口乙（企劃者 2026-10-20 挑的）：齒輪左邊一顆錠子鈕寫元寶餘額（main.mall.balance），點了打開商城那一層
  function mallBtnHtml(mall) {
    const n = mall.balance | 0;
    return `<button class="mall-btn" data-act="mall-open" aria-label="商城，元寶 ${n}">${ingotSvg()}<span>${n}</span></button>`;
  }

  // 換了帳號、登出：那一層收起、抓過的帳丟掉（另一個錢包）
  function forgetMall() {
    S.mallOpen = false; S.mallTab = "shelf"; S.mallData = null; S.mallLog = null; S.mallSay = null; S.mallPick = null; S.mallPending = null; S.mallFail = false;
    S.adMall = null; S.adMallName = ""; S.adMallNote = ""; S.adMallMsg = ""; S.adMallOk = false;
  }

  // 交給 shopHtml 的那一份：招牌、掌櫃那一句（剛買成了的、買不了的原因蓋過平常那一句）、餘額（紀錄頁照紀錄那一份，其餘照貨架、還沒抓到照狀態列）
  function mallShop() {
    const tab = S.mallTab === "log" ? "log" : "shelf";
    const d = tab === "log" ? S.mallLog : S.mallData;
    const say = S.mallSay;
    const balance = d ? d.balance : S.mallData ? S.mallData.balance : ((S.main && S.main.mall) || {}).balance;
    return {
      shop: "mall", sign: MALL_SIGN, tab, balance,
      line: say ? say.text : !d && !S.mallFail ? MALL_SAY.loading : MALL_SAY[tab],
      said: say ? (say.ok ? "said ok" : "said no") : "",
    };
  }

  function mallHtml(shop) {
    const body = shop.tab === "log" ? mallLogHtml(S.mallLog) : mallShelfHtml(S.mallData);
    return `<div class="shop-body mall-body"><div class="shop-col">${body}</div></div>
      <nav class="shop-tabs">${MALL_TABS.map(([k, name]) => `<button class="shop-tab${shop.tab === k ? " on" : ""}" data-act="mall-tab" data-tab="${k}">${name}</button>`).join("")}</nav>`;
  }

  // 沒拿到資料：還在抓什麼都不畫（掌櫃那一句寫翻帳中），連不上畫一句與「再試一次」
  function mallFailHtml() {
    return S.mallFail ? `<p class="shop-empty">${esc(MALL_SAY.fail)}</p><button class="btn small ghost" data-act="mall-retry">再試一次</button>` : "";
  }

  // 貨架：上面兩張小卡（手上幾顆丹、今天還能服幾顆；月卡到哪天、一天最多服幾顆），底下照種類分（照 content/mall.json 的順序，
  // 種類第一次出現的排前面）：消耗品一格一件（三欄），月卡一張寬卡。買不了的畫淡、照樣點得到（點了掌櫃講原因）
  function mallShelfHtml(d) {
    if (!d) return mallFailHtml();
    const p = d.pills;
    const status = `<div class="mall-status">
        <div><b>${esc(p.name)} ${p.count | 0} 顆</b>${p.today == null ? "每天不限" : `今天還能服 ${p.today | 0} 顆`}</div>
        <div><b>月卡 ${d.card ? `到 ${esc(d.card.until)}` : "還沒開"}</b>${p.cap > 0 ? `每天最多服 ${p.cap | 0} 顆` : "每天不限"}${mallDailyHtml(d.card)}</div></div>`;
    const groups = [];
    for (const it of d.items) {
      let g = groups.find((one) => one.kind === it.kind);
      if (!g) groups.push((g = { kind: it.kind, name: it.kind_name, items: [] }));
      g.items.push(it);
    }
    const section = (g) => (g.kind === "card"
      ? `<div class="mall-sub">${esc(g.name)}</div>${g.items.map(mallCardHtml).join("")}`
      : `<div class="mall-sub">${esc(g.name)}${g.kind === "consumable" ? `<small>一顆${esc(p.name)}回 ${p.restore | 0} 點體力</small>` : ""}</div>
        <div class="mall-grid">${g.items.map(mallTileHtml).join("")}</div>`);
    const empty = d.items.length ? "" : `<p class="shop-empty">${esc(MALL_SAY.empty)}</p>`;
    const note = d.grant > 0 ? `<p class="mall-note">${nbHtml(MALL_NOTE.replace("{n}", String(d.grant | 0)), MALL_NB)}</p>` : "";
    return status + groups.map(section).join("") + empty + note;
  }

  function mallTileHtml(it) {
    const cls = `mall-item${it.can ? "" : " off"}${S.mallPick === it.id ? " on" : ""}`;
    return `<button class="${cls}" data-act="mall-pick" data-id="${esc(it.id)}"${it.can ? "" : ' aria-disabled="true"'}>
        <span class="dan" aria-hidden="true">${(it.gives || {}).pills ? "丹" : "寶"}</span><b>${esc(it.name)}</b>
        <span class="price">${ingotSvg()}${it.price | 0}</span>${it.limit ? `<small>${nbHtml(it.limit, MALL_NB)}</small>` : ""}</button>`;
  }

  function mallCardHtml(it) {
    const cls = `mall-card${it.can ? "" : " off"}${S.mallPick === it.id ? " on" : ""}`;
    return `<button class="${cls}" data-act="mall-pick" data-id="${esc(it.id)}"${it.can ? "" : ' aria-disabled="true"'}>
        <span class="moon" aria-hidden="true">月</span>
        <span class="mt"><b>${esc(it.name)}</b>${perks(it)}${!(it.perks || []).length && it.note ? `<span>${nbHtml(it.note, MALL_NB)}</span>` : ""}${it.limit ? `<span>${nbHtml(it.limit, MALL_NB)}</span>` : ""}</span>
        <span class="price">${ingotSvg()}${it.price | 0}</span></button>`;
  }

  // 月卡的好處逐條列在卡上（萬寶閣販賣清單定案，Joy 2026-10-21；字是伺服器 mall.perks 寫的）。卡本身是一顆鈕，裡面不能再放鈕：
  // 用 span 排成一條一條（不用 ul，button 裡只准放 phrasing content）
  function perks(it) {
    const list = it.perks || [];
    return list.length ? `<span class="mall-perks">${list.map((t) => `<span class="perk">${nbHtml(t, MALL_NB)}</span>`).join("")}</span>` : "";
  }

  // 月卡今天的份（定案甲・每日領）：貨架上面那張月卡小卡裡一顆「領取」，領過了寫「今天已領」。card.daily 是 None（沒有這一份）不畫
  function mallDailyHtml(card) {
    const today = card && card.daily;
    if (!today) return "";
    return today.claimed ? `<small class="mall-daily done">今天的份已領</small>`
      : `<button class="btn small primary mall-daily" data-act="mall-claim">領今天的份</button>`;
  }

  function dailyWhat(today) {
    const pill = (S.mallData && S.mallData.pills && S.mallData.pills.name) || "回體丹";
    return [today.ingots ? `${today.ingots | 0} 元寶` : "", today.pills ? `${pill} ${today.pills | 0} 顆` : ""].filter(Boolean).join("＋");
  }

  // 江湖頁「月卡・今日份」小卡（定案：月卡生效、今天還沒領時，「剛剛」上面一張；領完收起）。資料是狀態列那一份 main.mall.daily
  function dailyCardHtml(m) {
    const today = m.mall && m.mall.daily;
    if (!today || today.claimed || !mallShown()) return "";
    return `<section class="card mall-today"><span class="moon" aria-hidden="true">月</span>
      <span class="mt"><b>月卡・今日份</b><span>${esc(dailyWhat(today))}，沒上線那天不補</span></span>
      <button class="btn small primary" data-act="mall-claim">領取</button></section>`;
  }

  // 領月卡今天的份：回來的 mall 換貨架、main 換狀態列與江湖頁那張小卡（領了就收起），話用提示泡泡講（商城開著時掌櫃講）
  async function mallClaim() {
    await busy(async () => {
      const r = await api("/api/mall/claim", {});
      if (r.mall) mallGot(r.mall);
      if (r.main) setMain(r.main);
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      renderTop();
      if (S.mallOpen) { S.mallSay = text ? { text, ok: /領了/.test(text) } : null; renderMall(); }
      else { render(); if (text) toast(text); }
    });
  }

  // 紀錄：元寶的每一筆進出（新的在前）；連著一筆購買的寫商品名、退了的掛「已退」，右邊增減與那一筆之後的餘額
  function mallLogHtml(r) {
    if (!r) return mallFailHtml();
    // （這一段在修練頁到輿圖之間：不用單字母 x，tests/test_server.py 會把 x 讀的欄位當成 menxia_view 的欄位查）
    const row = (line) => `<div class="mall-log-row"><b>${esc(line.item || line.reason)}${line.refunded ? '<span class="mall-tag">已退</span>' : ""}</b>
        <span class="amt${line.delta > 0 ? " in" : ""}">${line.delta > 0 ? "+" : "−"}${Math.abs(line.delta | 0)}</span>
        <span>${esc(line.time)}${line.item ? `・${esc(line.reason)}` : ""}${line.note ? `・${esc(line.note)}` : ""}</span><span class="bal">餘 ${line.balance | 0}</span></div>`;
    const rows = r.ledger.map(row).join("");
    return `<div class="mall-log-head"><span>元寶餘額</span><b>${r.balance | 0}</b></div>
      ${rows ? `<div class="mall-log">${rows}</div>` : `<p class="shop-empty">${esc(MALL_SAY.nolog)}</p>`}<p class="mall-note">${esc(MALL_LOG_NOTE)}</p>`;
  }

  // 只重畫商城那一層（換頁、點一件、買完、輪詢重抓）；畫面上還沒有那一層就整個重畫。捲到哪裡照放回去，換頁（keep 為假）從頂上開始
  function renderMall(keep = true) {
    const layer = document.querySelector(".shop-layer.shop-mall");
    if (!layer || !S.mallOpen) { render(); return; }
    const spot = shopSpot();
    if (spot && !keep) spot.top = 0;
    layer.outerHTML = shopHtml(mallShop());
    putShopSpot(spot);
  }

  async function openMall() {
    if (!S.main || !S.main.mall) return;
    S.mallOpen = true; S.mallTab = "shelf"; S.mallSay = null; S.mallPick = null; S.mallLog = null; S.mallFail = false;
    render();
    await loadMall();
  }

  function closeMall() {
    S.mallOpen = false; S.mallSay = null; S.mallPick = null;
    closeAsk();
    render(); // 底下那一頁與狀態列照最新的 main 畫（開著的時候輪詢不畫被蓋住的頁面）
  }

  // 貨架的指紋：買成一件一定會動到其中一樣（元寶、手上的丹、月卡到哪天）
  function mallMark(d) { return d ? `${d.balance}|${d.pills ? d.pills.count : ""}|${d.card ? d.card.until : ""}|${d.card && d.card.daily ? d.card.daily.claimed : ""}` : ""; }

  // 換上新抓到的貨架。上一筆沒等到回音（S.mallPending）、貨架卻變了：那一筆其實成了（或別處動了帳），下一次點是新的一筆、
  // 用新的編號，確認框照新的貨架算；不然照舊編號送出去，伺服器回「已經買好了」，確認框講的卻是再買一件（FB-491）
  function mallGot(d) {
    S.mallData = d;
    if (S.mallPending && d && mallMark(d) !== S.mallPending.mark) S.mallPending = null;
  }

  async function loadMall() {
    try {
      mallGot(await api("/api/mall"));
      S.mallFail = false;
    } catch (e) { S.mallFail = true; }
    if (S.mallOpen) renderMall();
  }

  async function loadMallLog() {
    try {
      S.mallLog = await api("/api/mall/records");
      S.mallFail = false;
    } catch (e) { S.mallFail = true; }
    if (S.mallOpen && S.mallTab === "log") renderMall();
  }

  async function mallTabTo(tab) {
    S.mallTab = tab === "log" ? "log" : "shelf";
    S.mallSay = null; S.mallPick = null; S.mallFail = false;
    closeAsk();
    renderMall(false);
    if (S.mallTab === "log") await loadMallLog(); // 紀錄每次切過去都重抓（別的分頁買的、管理者補的）
  }

  // 點一件：買不了（元寶不夠、限購）掌櫃講原因、不問；買得了框起來、問一次
  function mallPick(id) {
    const d = S.mallData;
    const it = d && d.items.find((one) => one.id === id);
    if (!it) return;
    if (!it.can) { S.mallPick = null; S.mallSay = { text: it.why || "", ok: false }; renderMall(); return; }
    S.mallPick = id; S.mallSay = null;
    renderMall();
    mallAsk(it, d);
  }

  // 這一筆購買的編號（伺服器照用 8～64 個英數字；同一個編號送兩次只算一次）
  function mallRef() {
    const abc = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
    const buf = new Uint8Array(16);
    if (typeof crypto !== "undefined" && crypto.getRandomValues) crypto.getRandomValues(buf);
    else for (let i = 0; i < buf.length; i++) buf[i] = Math.floor(Math.random() * 256);
    return `m${Array.from(buf, (b) => abc[b % abc.length]).join("")}`;
  }

  // 購買確認（設計 4.6；草圖子的「點了十顆」）：貼在下緣的紙，寫花多少、元寶剩多少、丹或月卡變成多少（還沒有月卡時多寫一天最多服幾顆），
  // 底下照商品的說明與限購。編號在這一刻產；上一次同一件送出去沒拿到回應（逾時、斷線）、貨架也還沒變，用回那一個（伺服器回「已經買好了」、
  // 不扣兩次），這時標題底下寫明是上一筆再送一次、鈕寫「再送一次」，不假裝是新的一筆（FB-491）
  // 一次買好幾件（Joy 2026-10-22「應該可以一次買多個」）：it.max > 1 時多一排數量（−、＋、最多），花的、剩的、變成多少照件數算；
  // 最多幾件是伺服器算的（限購剩的、元寶買得起的；月卡一次一張）。qty、ref 是按 −／＋ 重畫這張紙時帶回來的（編號不換）
  function mallAsk(it, d, qty = null, keepRef = null) {
    const p = d.pills, g = it.gives || {};
    const most = Math.max(1, it.max | 0);
    const again = !!(S.mallPending && S.mallPending.id === it.id);
    const n = Math.max(1, Math.min(most, qty == null ? (again ? S.mallPending.qty || 1 : 1) : qty | 0));
    const cost = (it.price | 0) * n, after = (d.balance | 0) - ((d.balance | 0) - (it.after | 0)) * n;
    const rows = [["花", `<b>${cost} 元寶</b>`], ["元寶", `<s>${d.balance | 0} →</s> <b>${after}</b>`]];
    if (g.pills) rows.push([esc(p.name), `<s>${p.count | 0} →</s> <b>${(p.count | 0) + (g.pills | 0) * n} 顆</b>`]);
    if (g.card_days) {
      rows.push(["月卡", `<s>${d.card ? `到 ${esc(d.card.until)}` : "還沒開"} →</s> <b>到 ${esc(it.card_to || "")}</b>`]);
      if (!d.card && p.cap > 0) rows.push(["每天最多服", `<s>${p.cap | 0} →</s> <b>${(p.cap | 0) + (p.bonus | 0)} 顆</b>`]);
      if (g.card_rebate) rows.push(["當場回", `<b>${g.card_rebate | 0} 元寶</b>（已算進上面的元寶）`]);
      const daily = d.daily;
      if (daily) rows.push(["每天領", `<b>${esc(dailyWhat(daily))}</b>（沒上線那天不補）`]);
    }
    if (g.zhuan_rewrite) rows.push(["列傳", `<b>多重寫 ${(g.zhuan_rewrite | 0) * n} 次</b>`]);
    const note = [it.note, it.limit].filter(Boolean).map(esc).join("<br>"); // 說明一行、限購一行（說明自己帶句號，接在一起讀起來是「。；」）
    const ref = keepRef || (again ? S.mallPending.ref : mallRef());
    const qtyRow = most > 1 && !again ? `<div class="mall-qty" role="group" aria-label="數量">
        <button class="btn small" data-act="mall-qty" data-n="${n - 1}" ${n <= 1 ? "disabled" : ""} aria-label="少一件">−</button>
        <b aria-live="polite">${n}</b><span>件</span>
        <button class="btn small" data-act="mall-qty" data-n="${n + 1}" ${n >= most ? "disabled" : ""} aria-label="多一件">＋</button>
        <button class="btn small ghost" data-act="mall-qty" data-n="${most}" ${n >= most ? "disabled" : ""}>最多 ${most}</button></div>` : "";
    closeAsk();
    S.mallAskNow = { id: it.id, ref };
    askGo = () => mallBuy(it.id, ref, n);
    document.body.insertAdjacentHTML("beforeend", `
      <div class="ask-layer">
        <div class="ask-bg" data-act="ask-no"></div>
        <div class="ask mall-ask" role="alertdialog" aria-modal="true" aria-labelledby="ask-text">
          <h4 id="ask-text">買下【${esc(it.name)}】${n > 1 ? `×${n}` : ""}？</h4>
          ${again ? `<p class="mall-ask-again">${nbHtml(MALL_AGAIN.replace("{name}", it.name), MALL_SAY_AFTER)}</p>` : ""}
          ${qtyRow}
          <dl class="mall-sum">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("")}</dl>
          ${note ? `<p class="mall-ask-note">${note}</p>` : ""}
          <div class="row"><button class="btn" data-act="ask-no">再想想</button><button class="btn primary" data-act="ask-yes">${again ? "再送一次" : "買下"}（${cost}）</button></div>
        </div>
      </div>`);
    document.querySelector('.ask [data-act="ask-no"]')?.focus?.();
  }

  // 買：回來的 mall 換掉貨架、main 換掉狀態列（錠子鈕的餘額、丹鈕當場換），掌櫃那一句換成伺服器回的那一句（bought 有值是成了；
  // already 有值是同一個編號早就買好了〔逾時重送〕，也是成了的樣子，FB-491）。送出去之前記下貨架的指紋（mallGot 拿來比）
  async function mallBuy(id, ref, qty = 1) {
    await busy(async () => {
      S.mallPending = { id, ref, qty, mark: mallMark(S.mallData) };
      const r = await api("/api/mall/buy", { item: id, ref, qty });
      S.mallPending = null;
      if (r.mall) S.mallData = r.mall;
      if (r.main) setMain(r.main);
      S.mallPick = null;
      S.mallLog = null;
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      S.mallSay = text ? { text, ok: !!(r.bought || r.already) } : null;
      renderTop();
      if (S.mallOpen) renderMall(); else render();
    });
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
  // 輿圖第三版（輿圖簡化設計第五章）：兩張固定取景、能拖能捏合縮放（企劃者 2026-10-22）的圖——天下圖（打開輿圖第一眼，S.mapLayer "world"）與區圖（點一區，"region"）——
  // 加一張卡（抽屜，設計 5.3）。底圖（/api/map/base：紙、大區、山河、路的 SVG）一次載入只抓一次，疊層的 key 換了（劇情開放了新地點）才重抓；
  // 疊層（/api/map/state：誰佔著、勝算、分鐘……）打開輿圖、輪詢（MAP_STATE_EVERY）、做了動作之後重抓。記號照疊層畫在底圖的 <g id="mk">
  // 與疊在上面的 #mkt（drawMarks）；兩張圖都是固定取景（worldFit、regionFit），字與記號照倍率反算、螢幕上大小固定。
  // 輿圖升級（10/15）那一張可以拖縮的地圖、濾鏡、名字底下的小牌子、⚔、看大局都拿掉了（設計 5.4，輿圖第三版第 4 批）：資訊都收進卡
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
  const MAP_PAPER = "#E9E2CC"; // 底圖的紙色（content/map.json 的 background）：區圖取景框外蓋的那一層
  const MAP_STATE_EVERY = 30000; // 輿圖開著時疊層多久重抓一次（毫秒）
  // 意境照屬性上色（意境提示設計第四節；意境改名也不跑掉）：c 區圖名字底下的字與卡上牌子的顏色、dark 深色主題上空心牌子的字
  const INSIGHT_INK = {
    快: { c: "#2B8A80", light: "#DDF0EC", dark: "#6CCBBE" }, 剛: { c: "#CF4F27", light: "#FBE3D8", dark: "#F08A63" },
    柔: { c: "#2C68B0", light: "#DCE8F6", dark: "#7FB0EA" }, 慢: { c: "#8A5A33", light: "#F0E3D6", dark: "#D2A57D" },
  };
  const INSIGHT_ROW = "此地能悟"; // 卡上那一行（意境提示設計第五節）
  function insightInk(base, id) {
    const kind = id && base && base.insight_kinds ? base.insight_kinds[id] : null;
    const ink = kind && INSIGHT_INK[kind.attribute];
    return ink ? { ...ink, name: kind.name } : null;
  }
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
  // 沒人佔的那一頭（版圖變化的「⇄ 某地：中立 → 官軍」、卡上的易手；FB-632：中立地第一次被佔下也算易手）。待 joy 潤
  const NEUTRAL_WORD = "中立";
  const flipSide = (k) => (k ? sideInk(k).name : NEUTRAL_WORD);
  const f1 = (n) => Math.round(n * 10) / 10;
  const f2 = (n) => Math.round(n * 100) / 100;
  const mapWeek = () => S.mapWeek || (S.mapState && S.mapState.now_week) || 1;
  // 兩個 #RRGGBB 照比例混（t＝0 是 a、1 是 b）：區圖沒人佔的框照底圖的 unheld 往墨色、紙色調（顏色從劇本讀，不寫死灰）
  function mixHex(a, b, t) {
    const rgb = (h) => [1, 3, 5].map((i) => parseInt(String(h).slice(i, i + 2), 16) || 0);
    const [A, B] = [rgb(a), rgb(b)];
    return `#${A.map((x, i) => Math.round(x + (B[i] - x) * t).toString(16).padStart(2, "0")).join("").toUpperCase()}`;
  }
  // 兩個 #RRGGBB 的對比（WCAG 的算法，1～21）
  function hexContrast(a, b) {
    const lum = (h) => {
      const [r, g, bl] = [1, 3, 5].map((i) => { const c = (parseInt(String(h).slice(i, i + 2), 16) || 0) / 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; });
      return 0.2126 * r + 0.7152 * g + 0.0722 * bl;
    };
    const [x, y] = [lum(a), lum(b)];
    return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
  }
  // 抽屜裡照陣營上色的字：從劇本的 color 起算，對比不到 4.5:1 的調到夠，本來就夠的不動。回 style 裡的兩個變數（--sc 淺色、--sd 深色；
  // style.css 照主題挑）。深色（FB-650）：在深色抽屜最亮的底 --card-2 #2B251E 上，往那一方的 soft 調亮（soft 都不夠再往白）；
  // 淺色（FB-652）：在淺色抽屜最深的底 --card-2 #EFE6D5 上，往墨色 --ink 調深（黃巾的 #B9821A 在卡底只有 3.13:1）。
  // k 是陣營 id（或 sideInk 給的那一份）；顏色照劇本讀，不寫死哪一方
  const DARK_TEXT_BG = "#2B251E", LIGHT_TEXT_BG = "#EFE6D5", LIGHT_TEXT_INK = "#2A241D", DARK_TEXT_MIN = 4.5;
  const sideDarkMemo = {}, sideLightMemo = {};
  function sideText(k) {
    const ink = k && typeof k === "object" ? k : sideInk(k), key = `${ink.color}|${ink.soft}`;
    if (!(key in sideDarkMemo)) {
      const ok = (c) => hexContrast(c, DARK_TEXT_BG) >= DARK_TEXT_MIN;
      let c = ink.color;
      for (let i = 1; i <= 20 && !ok(c); i++) c = mixHex(ink.color, ink.soft || "#FFFFFF", i / 20);
      for (let i = 1; i <= 20 && !ok(c); i++) c = mixHex(ink.soft || ink.color, "#FFFFFF", i / 20);
      sideDarkMemo[key] = c;
    }
    if (!(ink.color in sideLightMemo)) {
      let c = ink.color;
      for (let i = 1; i <= 20 && hexContrast(c, LIGHT_TEXT_BG) < DARK_TEXT_MIN; i++) c = mixHex(ink.color, LIGHT_TEXT_INK, i / 20);
      sideLightMemo[ink.color] = c;
    }
    return `--sc:${sideLightMemo[ink.color]};--sd:${sideDarkMemo[key]}`;
  }

  // 那一週的控制方：現在照疊層；選了別的週照那一週的快照（還沒記到是空的）
  function controlAt(st, week) {
    if (!st) return {};
    if (!week || week === st.now_week) return Object.fromEntries(Object.entries(st.places).map(([id, p]) => [id, p.control]));
    const w = (st.weeks || []).find((x) => x.week === week);
    return (w && w.control) || {};
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
    return first && first.week < week ? { label: `比${wkName(first.week, `第 ${first.week} 週`)}`, n: tally(base, first.control) } : null;
  }
  const signed = (d) => (d > 0 ? `+${d}` : d < 0 ? `${d}` : "±0");
  // 整頁一層（設計第一節）：夾在頂上的狀態列與底部分頁列之間；上面一排（天下圖：天下・找地點・版圖；區圖：‹ 天下・大區・版圖、塗層），
  // 底下是抽屜（寬 900 以上是右欄）。data-key 是底圖的 key：輿圖那一層常駐在 #map-host 時（showMapHost），同一張底圖只換外圍、底圖那一塊原地留著（FB-324）
  function pageMap() {
    if (!S.mapBase || !S.mapState) return '<p class="muted">展開輿圖…</p>';
    const svg = S.mapBase.svg.replace(/<\/svg>\s*$/, '<g id="mk"></g></svg>');
    // 疊在底圖上面的那一張（FB-323）：跟底圖同一個根（viewBox、大小、字型），位移與倍率由 applyMapView 一起套
    const top = `<svg${(S.mapBase.svg.match(/^<svg\b([^>]*)>/) || ["", ""])[1]} class="mk-top" id="mkt"></svg>`;
    return `<div class="${mapxClass()}" id="mapx" data-key="${esc(S.mapBase.key)}">
      <div class="map-wrap" id="map"><div class="tx-world-map">${svg}${top}</div></div>${mapChrome()}
    </div>`;
  }
  function mapxClass() { return `mapx ${S.mapLayer === "world" ? "world" : "region"}${S.mapMode === "timeline" ? " tl-mode" : ""}`; }
  // 地圖框以外的那幾樣：天下圖上面那一排（天下・找地點・版圖）、區圖上面那一排（regionTopHtml）、「正在看第幾週」、抽屜。
  // 兩層的都畫，照 .mapx.world／.mapx.region 藏另一層的（style.css）
  function mapChrome() {
    const seeing = S.mapMode === "timeline" && S.mapWeek && S.mapWeek !== S.mapState.now_week;
    const banner = `<div class="map-banner" id="map-banner"${seeing ? "" : " hidden"}>${seeing ? `正在看${wkName(S.mapWeek, `第 ${S.mapWeek} 週`)}` : ""}</div>`;
    const tl = S.mapMode === "timeline";
    const wtop = `<div class="w-top"><button type="button" class="w-here" data-act="map-world" aria-current="page">${WORLD_WORD}</button><button type="button" class="map-search" data-act="map-search">🔍 找地點、找人物</button><button type="button" class="w-tl${tl ? " on" : ""}" data-act="map-timeline" aria-pressed="${tl}">⏱ 版圖</button></div>`;
    return `
      ${wtop}${regionTopHtml()}${banner}
      <section class="mdrawer${S.mapDrawer === "min" && !deskMap() ? " min" : ""}" id="mdrawer" aria-label="輿圖抽屜"><div class="mgrab" id="mgrab" role="button" aria-label="拉高拉低"><i></i></div><div class="mbody" id="mbody">${drawerHtml()}</div></section>`;
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
  // 登出、登入（換帳號不重新整理、登入失效之後重新登入）：上一個人的輿圖全部清回開頭——底圖、疊層、哪一層哪一區、選的地點、抽屜、
  // 版圖變化、找地點的字——常駐那一層整個清掉（FB-329：不清的話換人登入之後輿圖照舊畫上一個人的疊層、位置與勝算）
  function forgetMap() {
    stopPlay();
    Object.assign(S, {
      mapBase: null, mapState: null, mapStateAt: 0, mapSel: null, mapMode: "overview", mapDrawer: "min",
      mapWeek: null, mapQuery: "", mapLayer: "world", mapRegion: null, worldView: null, regionView: null, marksKey: "", mapPan: null, panKey: "", panFrom: null,
    });
    hideMapHost(true);
  }
  // ── 輿圖的抽屜（設計 5.3）：一張卡（點一個地點、天下圖拉開你腳下這一處）、找地點、版圖變化；收著時一行 ──
  const SORTIE_WORD = { attack: "攻", hold: "守", stir: "攪局" }; // 出陣是哪一種（sortie.mode），待 joy 潤
  const ODDS_TONE_WEB = { 穩勝: "safe", 有把握: "safe", 五五波: "ok", 難分勝負: "ok", 凶險: "risk", 必敗: "risk", 操練: "safe" };
  const placeOf = (base, id) => base.places.find((p) => p.id === id);
  const ctrlSeal = (c) => (c ? `<span class="m-seal" style="background:${sideInk(c).color}">${esc(sideInk(c).short)}</span>` : '<span class="m-seal none">—</span>');
  function drawerHtml() {
    const base = S.mapBase, st = S.mapState;
    if (S.mapMode === "search") return searchHtml(base, st, S.mapQuery);
    if (S.mapMode === "timeline") return timelineHtml(base, st, mapWeek());
    if (S.mapLayer === "world" && base.world) return worldDrawerHtml(base, st);
    if (S.mapMode === "place" && S.mapSel && st.places[S.mapSel]) return placeCard(base, st, S.mapSel);
    return regionLineHtml(base, st);
  }
  // 抽屜第一行：在路上寫往哪裡、還有幾分鐘、喊停（喊停就是江湖頁那一顆，選單上有才畫）；有事擋著路時寫是哪一則、給「回江湖」
  // （withBlock 是 false 時不寫擋路那一行：卡的動作那一排自己會寫）
  function journeyHtml(st, withBlock = true) {
    const j = st.journey, block = withBlock ? st.travel_block : null;
    const halt = ((S.main && S.main.options) || []).some((o) => o.id === "act:halt" && o.enabled !== false);
    const road = j ? `<div class="m-journey"><span>往 <b>${esc(j.to_name)}</b>・還有 ${Number(j.minutes)} 分鐘${j.next_name ? `・下一站${esc(j.next_name)}` : ""}</span>${halt ? '<button type="button" data-act="choose" data-id="act:halt">喊停</button>' : ""}</div>` : "";
    const held = block && block.to_jianghu ? `<div class="m-journey"><span>${esc(block.reason)}</span><button type="button" data-act="tab" data-tab="jianghu">回江湖</button></div>` : "";
    return road + held;
  }
  // 區圖沒點地點時抽屜收著的那一行：在路上照 journeyHtml；你在這一區寫你在哪（點了攤開你腳下這一處的卡）；不然一句提示
  const REGION_HINT = "點一處地點，看那裡的詳情"; // 待 joy 潤
  function regionLineHtml(base, st) {
    if (st.journey) return journeyHtml(st);
    const here = placeOf(base, st.here), mine = !!here && here.region === S.mapRegion;
    const text = mine ? `你在 <b>${esc(here.name)}</b>` : esc(REGION_HINT);
    return `<div class="m-wline"><button type="button" class="m-mini" data-act="map-open" aria-label="攤開抽屜"><span>${text}</span>${mine ? "<i>▴</i>" : ""}</button></div>`;
  }
  // 一根戰線（拔河）：左官軍、右黃巾，斜線是亂局（35～65），黑線是此刻的戰況；繩上的可易手地點是小方印（照誰佔著上色，
  // 擺在它易手的門檻上）；繩名旁寫比上一週往哪邊推了多少
  // 繩的兩頭是誰照疊層的 low／high（劇本的 goals；輿圖第三版第 3 批起不寫死官軍、黃巾），舊疊層沒有照官軍、黃巾
  const ropeEnds = (r) => [sideInk(r.low || "guan"), sideInk(r.high || "huang")];
  function ropeHtml(r) {
    const [lo, hi] = ropeEnds(r);
    const trend = r.delta > 0 ? `<small class="m-sc" style="${sideText(hi)}">▶ ${esc(hi.name)}推進 ${r.delta}</small>`
      : r.delta < 0 ? `<small class="m-sc" style="${sideText(lo)}">◀ ${esc(lo.name)}推進 ${-r.delta}</small>` : "<small>持平</small>";
    const beads = r.beads.map((b) => `<span class="bead" style="left:${b.threshold}%;background:${b.control ? sideInk(b.control).color : "#A2967F"}"></span>`).join("");
    return `<div class="m-rope"><div class="rl"><span>${esc(lo.name)}</span><b>${esc(r.name)} ${trend}</b><span>${esc(hi.name)}</span></div><div class="bar" style="background:linear-gradient(90deg, ${lo.tint}, ${hi.tint})"><span class="chaos"></span>${beads}<span class="knot" style="left:${Number(r.value)}%"></span></div></div>`;
  }
  // 卡底下、拉高才看的最後三段（輿圖升級設計第五節那三樣挪到這裡，輿圖簡化設計 5.3、第九章第 6 條）：今天去哪裡出陣、戰線的繩、本週大事
  function cardExtras(base, st) {
    const goes = st.suggest.length && st.sorties_left !== null
      ? `<div class="m-sec"><h4>今天去哪裡出陣<small>今日還能 ${Number(st.sorties_left)} 次</small></h4>` +
        st.suggest.map((g, i) => `<div class="m-go${g.lose ? " lose" : ""}" data-act="map-pick" data-id="${esc(g.id)}" role="button"><span class="n">${i + 1}</span><span class="t"><b>${esc(placeOf(base, g.id).name)}</b>　出陣・${SORTIE_WORD[g.sortie] || ""}
          <span class="why">${g.why.map(([t, tone]) => `<span style="background:${TONE_COLOR[tone] || "#8A7A62"}">${esc(t)}</span>`).join("")}</span></span><span class="m">${g.minutes ? `${Number(g.minutes)} 分 ›` : "這裡 ›"}</span></div>`).join("") + "</div>"
      : "";
    const ropes = st.ropes.length ? `<div class="m-sec"><h4>${st.season_one ? "三條戰線" : "大勢"}</h4>${st.ropes.map(ropeHtml).join("")}${st.geju !== null ? `<div class="m-sub">豪強割據 ${Number(st.geju)}</div>` : ""}</div>` : "";
    const events = st.events.length ? `<div class="m-sec"><h4>${wkWord("this", "本週")}大事</h4>${st.events.map((t) => `<div class="m-evt">📜 ${esc(t)}</div>`).join("")}</div>` : "";
    return goes + ropes + events;
  }
  // 卡上「此地能悟」（意境提示設計第五節）：一種一顆牌子，最濃的實心、寫「最濃」；開關關著沒有最濃，全部空心
  function insightRow(base, b) {
    const pills = (b.insights || []).map((id) => {
      const ink = insightInk(base, id);
      if (!ink) return "";
      const strong = id === b.strong;
      return `<span class="ig${strong ? " strong" : ""}" style="--c:${ink.c};--d:${ink.dark}"><b>${esc(ink.name)}</b>${strong ? "<em>最濃</em>" : ""}</span>`;
    }).join("");
    return pills ? `<div class="m-ins"><small>${INSIGHT_ROW}</small>${pills}</div>` : "";
  }
  // 地利（武學隨地理環境計畫第六節）：拉高才看的細節裡一段；字是伺服器照最濃的意境寫好的
  // （mapdata.base 的 terrain_arts，terrain.place_line），開關關著、這一處沒有最濃的是空字串、整段不畫。「地利」兩個字待 joy 潤。
  // 那一句 26 字，375 寬斷成「…施展不／開。」、360 與桌面「…施展／不開。」（FB-470）：照掮客那一句（sayHtml）切在「：」「，」
  // 後面包成不折行的小段，字一個不改
  function terrainArtsRow(b) {
    return b.terrain_arts ? `<div class="m-sec"><h4>地利</h4>${sayHtml(b.terrain_arts)}</div>` : "";
  }
  // ── 卡（輿圖簡化設計 5.3）：一打開是你腳下這一處、點別處是同一張。由上往下：1 印、名字、★高級、距離；2 一句話；3 正在翻；4 此地能悟；
  // 5 此地的對手；6 今日產出；7 動作一排（下戰書）；8 拉高才看（軍令懸賞、這一季誰佔過、地利、此地、劇情；今天去哪裡出陣、戰線、本週大事）。字待 joy 潤
  const CARD_RICH = "★高級";
  const LINE_BASE = "{side}大本營", LINE_HOME = "{side}的基礎資源領地", LINE_RICH_FREE = "中立・高級資源領地，還沒有人佔";
  const LINE_RICH_HELD = "{side}佔下的高級資源領地", LINE_FREE = "還沒有人佔", LINE_OFF = "不在戰線上", LINE_FIXED = "只照大事易手";
  const LINE_HELD = "{side}控制", LINE_TUG = "{side}控制，照戰線易手", LINE_COOL = "剛易手，{n} 分後才能再推、加成暫停";
  const FLIP_TITLE = "正在翻", CLASH_WORD = "激戰", FLIP_IDLE = "還沒有人推，進度 0／100", FLIP_ATTACK = "正在攻", FLIP_HOLD = "在守";
  const FOCUS_WORD = "{side}集火 +{pct}%";
  // 攻城戰的三種時刻（輿圖第三版第 5 批，企劃者 2026-10-22 從對比圖挑 A 乙、B 甲、C 甲）：卡上第 2 段底下一段——戰書下了到開集結（A）、
  // 集結・交戰中（B）、打完到換天（C）；讀 main_view["conquest"]["today"]（Game.conquest_view：攻方、時刻、狀態字、看的人站哪一格 you、
  // 打完的大勝／險勝 margin）與 muster（開打前幾分鐘開集結）。字待 joy 潤
  const SIEGE_HEAD = { letter: "戰書", fight: "攻城", done: "攻城戰果" };
  const SIEGE_JOIN = { attack: "去加入攻城", defend: "去守城", help: "去助陣" }, SIEGE_REPORT = "看戰報";
  const SIEGE_LETTER_LINE = "{who}約戰 <b>{time}</b>；開打前 {muster} 分鐘在這一帶集結，{join}這一塊的進度凍結到打完。";
  const SIEGE_FIGHT_LINE = "{who}攻{place}：<b>{status}</b>（{time} 開打）。{join}", SIEGE_DONE_LINE = "{time} 那一仗：<b>{status}</b>{margin}。";
  // 看的人站不站得進這一場（you 是空的＝另一軍，siege.slots）：戰書那一句寫「人要在某區才加得進去」；集結・交戰中照伺服器的 join
  // （FB-690：同江湖頁的加入鈕 Game._joinable——人在那一區、不在路上、還沒在任何一場的名單上才加得進去）：go 才畫「去…」那一顆，
  // in 畫「看戰況」，far 寫要到哪一區、走到這裡幾分（步行、疾行的鈕在卡的動作那一排），busy 寫已經在別的一場
  const SIEGE_IN_LETTER = "人要在{region}才加得進去。", SIEGE_OUT = "這一場你這一邊站不進去。", SIEGE_WALK = "（走到這裡步行 {n} 分）";
  const SIEGE_JOIN_WORD = { go: "你在{region}，加得進去。", in: "你已經在這一場的名單上。", busy: "你已經在另一場的名單上，加不進這一場。",
    far: "人要在{region}才加得進去{walk}。" };
  const SIEGE_WATCH = "看戰況";
  const LETTER_WORD = "下戰書", LETTER_ASK = "對{place}下戰書？當晚的攻城時段打一場，那一塊的進度凍結到打完；今天一邊只能下一張。";
  // 這一塊翻地那一份畫面資料（server.main_view 的 conquest.blocks，conquest.block_view：進度、冷卻、戰書、正在推的人、激戰、集火、看的人推不推得動）；
  // 領地爭奪關著、不是區塊是 null
  const conquestBlock = (id) => (S.main && S.main.conquest && S.main.conquest.blocks && S.main.conquest.blocks[id]) || null;
  // 第 2 段那一句：誰的、哪一種（基礎、高級資源領地是領地爭奪的區塊；關著的季照控制方寫）；剛易手接冷卻
  function placeLine(st, id) {
    const q = st.places[id] || {}, c = q.control, sd = c ? sideName(c) : "";
    const blk = conquestBlock(id), on = !!blk || q.kind === "neutral";
    let line;
    if (q.kind === "base") line = c ? LINE_BASE.replace("{side}", sd) : LINE_OFF;
    else if (q.kind === "fixed") line = c ? `${LINE_FIXED}・${LINE_HELD.replace("{side}", sd)}` : LINE_FIXED;
    else if (on && q.rich) line = c ? LINE_RICH_HELD.replace("{side}", sd) : LINE_RICH_FREE;
    else if (on && q.kind === "line") line = c ? LINE_HOME.replace("{side}", sd) : LINE_FREE;
    else if (q.kind === "line") line = c ? LINE_TUG.replace("{side}", sd) : LINE_FREE;
    else line = c ? LINE_HELD.replace("{side}", sd) : LINE_OFF;
    return q.cool && c ? `${line}；${LINE_COOL.replace("{n}", Number(q.cool))}` : line;
  }
  // 第 3 段「正在翻」（設計 4.1、4.2）：領地爭奪開著、搶得下來的區塊，看的人此刻推得動（攻）、或此刻有人在推、或被戰書凍結時才有
  // 【開發定：自家的塊被對面推著也列，守的人才知道誰在推】。每一個攻方一條進度、誰在推（照邊、攻守分，名字最多三個）、集火、激戰、戰書
  function flipSection(id) {
    const blk = conquestBlock(id);
    if (!blk || !blk.capturable) return "";
    const bars = (blk.bars || []).filter((b) => Number(b.value) > 0);
    if (!bars.length && !blk.frozen && !(blk.how === "attack" && !blk.why)) return "";
    const rows = bars.map((b) => {
      const ink = sideInk(b.side), v = Math.min(100, Number(b.value));
      return `<div class="m-fbar"><span class="nm" style="${sideText(ink)}">${esc(ink.name)}</span><span class="tr"><i style="width:${v}%;background:${ink.color}"></i></span><b>${v}</b><small>／100</small></div>`;
    }).join("") || `<div class="m-sub">${FLIP_IDLE}</div>`;
    const by = {};
    for (const r of blk.pushers || []) (by[r.side] = by[r.side] || []).push(r);
    const order = [...sideOrder(S.mapBase), ...Object.keys(by).filter((sd) => !sideOrder(S.mapBase).includes(sd))];
    const who = order.filter((sd) => by[sd]).map((sd) => {
      const list = by[sd].slice().sort((a, z) => Number(z.moved) - Number(a.moved));
      const names = list.slice(0, 3).map((r) => `${esc(r.name)} +${Number(r.moved)}`).join("、") + (list.length > 3 ? "…" : "");
      const how = list.some((r) => r.how === "attack") ? FLIP_ATTACK : FLIP_HOLD;
      return `<span class="m-sc" style="${sideText(sd)}">${esc(sideInk(sd).name)}</span> ${list.length} 人${how}（${names}）`;
    }).join("、");
    const focus = Object.entries(blk.focus || {}).filter(([, pct]) => Number(pct) > 0)
      .map(([sd, pct]) => FOCUS_WORD.replace("{side}", esc(sideInk(sd).name)).replace("{pct}", Number(pct))).join("、");
    // 被戰書凍結：第 5 批以前這裡多一行「已下戰書：…」，現在寫在上面那一段（siegeSection），這裡不重複
    return `<div class="m-sec m-flip"><h4>${FLIP_TITLE}${blk.clash ? `<span class="m-clash">${CLASH_WORD}</span>` : ""}</h4>${rows}${who ? `<div class="m-who">${who}</div>` : ""}${focus ? `<div class="m-sub">${focus}</div>` : ""}</div>`;
  }
  // 這一處時程表上的那一場（同一處一天可能有兩場：還沒打完的在前，其次是最晚那一場打完的；作罷的不寫）。回 [那一場, 哪一種時刻]
  function siegeOf(id) {
    const rows = ((S.main && S.main.conquest && S.main.conquest.today) || []).filter((r) => r.loc === id);
    const live = rows.find((r) => r.status === "planned" || r.status === "waiting" || r.status === "open");
    if (live) return [live, live.status === "open" ? "fight" : "letter"];
    const done = rows.filter((r) => r.status === "done").pop();
    return done ? [done, "done"] : [null, ""];
  }
  // 卡上第 2 段底下那一段（三種時刻；字待 joy 潤）：戰書（誰約戰、幾點、開打前幾分鐘集結、要在哪一區、凍結）、攻城（狀態字、幾點開打；
  // 此刻加得進去〔join 是 go〕才畫一顆鈕回江湖頁按，字照看的人站哪一格：攻方「去加入攻城」、被打的那一方「去守城」、散人與不是兩軍的人「去助陣」；
  // 已經在這一場畫「看戰況」；人不在那一區寫要到哪一區、走到這裡幾分，已經在別的一場、另一軍站不進去都只寫一句，FB-690）、
  // 攻城戰果（那一仗誰拿下或守住、大勝險勝，「看戰報」開見聞的戰報）
  function siegeSection(id) {
    const [row, kind] = siegeOf(id);
    if (!row) return "";
    const who = esc((row.attackers || []).join("、")), time = esc(row.time || ""), you = row.you || "", join = row.join || "";
    const region = esc(row.region || "這一區"), q = (S.mapState && S.mapState.places && S.mapState.places[id]) || {};
    let say = "", btn = "";
    if (kind === "letter") {
      say = SIEGE_LETTER_LINE.replace("{who}", who).replace("{time}", time).replace("{muster}", Number(S.main.conquest.muster) || 0)
        .replace("{join}", you ? SIEGE_IN_LETTER.replace("{region}", region) : SIEGE_OUT);
    }
    if (kind === "fight") {
      const walk = typeof q.minutes === "number" && q.minutes > 0 ? SIEGE_WALK.replace("{n}", Number(q.minutes)) : "";
      const word = !you ? SIEGE_OUT : (SIEGE_JOIN_WORD[join] || SIEGE_JOIN_WORD.far).replace("{region}", region).replace("{walk}", join === "far" ? walk : "");
      say = SIEGE_FIGHT_LINE.replace("{who}", who).replace("{place}", esc(row.place)).replace("{status}", esc(row.status_text)).replace("{time}", time)
        .replace("{join}", word);
      if (join === "go" && SIEGE_JOIN[you]) btn = `<button type="button" class="main" data-act="tab" data-tab="jianghu">${SIEGE_JOIN[you]}<small>回江湖頁</small></button>`;
      if (join === "in") btn = `<button type="button" class="main" data-act="tab" data-tab="jianghu">${SIEGE_WATCH}<small>回江湖頁</small></button>`;
    }
    if (kind === "done") {
      say = SIEGE_DONE_LINE.replace("{time}", time).replace("{status}", esc(row.status_text)).replace("{margin}", row.margin ? `（${esc(row.margin)}）` : "");
      btn = `<button type="button" data-act="map-report">${SIEGE_REPORT}<small>見聞</small></button>`;
    }
    return `<div class="m-sec m-siege" data-siege="${kind}"><h4>${SIEGE_HEAD[kind]}</h4><div class="m-say">${say}</div>${btn ? `<div class="m-acts">${btn}</div>` : ""}</div>`;
  }
  // 第 7 段的「下戰書」（設計 4.4）：照伺服器的入口條件（Game.letter_problem；conquest_view 的 letter 只給這一週在任的第 4 階、只列自己那一邊
  // 進度到門檻的塊，why 空字串＝下得了），不另寫判斷。下不了的灰著、原因寫在動作底下
  function letterRow(id) {
    const L = S.main && S.main.conquest && S.main.conquest.letter;
    const row = L && (L.ready || []).find((r) => r.id === id);
    if (!row) return { button: "", why: "" };
    if (row.why) return { button: `<button type="button" disabled>${LETTER_WORD}<small>下不了</small></button>`, why: `<div class="m-sub m-why">${LETTER_WORD}：${esc(row.why)}</div>` };
    return { button: `<button type="button" class="m-letter" data-act="map-letter" data-id="${esc(id)}">${LETTER_WORD}<small>進度到 ${Number(L.at)} 了</small></button>`, why: "" };
  }
  function placeCard(base, st, id) {
    const b = placeOf(base, id), p = st.places[id], here = id === st.here && !st.journey;
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
    const letter = letterRow(id);
    const tone = (word) => TONE_COLOR[ODDS_TONE_WEB[word] || "ok"];
    const foes = p.squads.length ? p.squads.map((q) => `${esc(q.name)} <b style="color:${tone(q.odds)}">${esc(q.odds)}</b>`).join("、") : "<b>沒有對手</b>";
    const strip = p.kind === "line" || p.kind === "fixed" || p.kind === "neutral" ? `<div class="m-strip">${Array.from({ length: st.weeks_total }, (_, i) => {
      const w = i + 1, row = (st.weeks || []).find((x) => x.week === w), c = row && row.control ? row.control[id] : null;
      return `<span class="${w > st.now_week ? "future" : ""}${w === st.now_week ? " now" : ""}" style="background:${c ? sideInk(c).color : "#CDBF9F"}"></span>`;
    }).join("")}</div>` : "";
    const flips = p.flips.map((f) => `${wkName(Number(f.week), `第 ${Number(f.week)} 週`)} ${flipSide(f.from)}→${flipSide(f.to)}`).join("；");
    const held = st.territory && (p.price || strip || flips) ? `<div class="m-sec"><h4>這一季誰佔過</h4>${p.price ? esc(p.price) : ""}${strip}${flips ? `<div class="m-sub">易手：${flips}</div>` : ""}</div>` : "";
    const far = here ? "" : p.minutes !== null && p.minutes !== undefined ? `步行 ${Number(p.minutes)} 分` : "";
    // 第 2 段照控制方上色（--sc／--sd，FB-650 深色換夠亮的那一版）；沒人佔照 style.css 的 --ink-2
    const lineInk = p.control ? ` style="${sideText(p.control)}"` : "";
    // 在路上：第一行照舊是往哪裡、還有幾分鐘、喊停（計畫 1.2、設計 5.3；FB-649）。擋路的那一則寫在動作那一排，這裡不重複
    return `${st.journey ? journeyHtml(st, false) : ""}<div class="m-h1">${ctrlSeal(p.control)}<span class="nm">${esc(b.name)}${here ? "（你）" : ""}</span><span class="meta">${p.rich ? `<b class="m-rich">${CARD_RICH}</b>` : ""}${far ? `<span>${far}</span>` : ""}</span><button type="button" class="m-x" data-act="map-back" aria-label="收起">✕</button></div>
      <div class="m-line"${lineInk}>${esc(placeLine(st, id))}</div>
      ${siegeSection(id)}${flipSection(id)}${insightRow(base, b)}
      <div class="m-foes"><small>此地的對手</small><span>${foes}</span>${p.fierce ? `<div class="m-sub">${esc(p.fierce)}</div>` : ""}${p.people.length ? `<div class="m-sub">人物：${p.people.map(esc).join("、")}</div>` : ""}</div>
      ${p.yield ? `<div class="m-yield">${esc(p.yield)}</div>` : ""}
      <div class="m-acts">${acts}${letter.button}</div>${letter.why}
      ${p.order || p.bounty ? `<div class="m-sec"><h4>軍令與懸賞</h4>${p.order ? `軍令「${esc(p.order)}」在這裡記功` : ""}${p.order && p.bounty ? "；" : ""}${p.bounty ? `懸賞「${esc(p.bounty)}」在這裡交差` : ""}</div>` : ""}
      ${held}${terrainArtsRow(b)}
      ${p.services.length ? `<div class="m-sec"><h4>此地</h4>${p.services.map(esc).join("・")}</div>` : ""}
      <div class="m-sec"><h4>劇情</h4>${p.goal ? "★ 這一幕主線的目標　" : ""}${p.news ? "✦ 最近有大事與傳聞" : p.goal ? "" : "最近沒有大事"}</div>
      ${cardExtras(base, st)}`;
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
  // 年表：一列一個可易手的地點、一格一週；還沒到打斜線、還沒記到是空格（中途上線、舊存檔）。沒人佔↔有人佔也打白點（FB-632）
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
        const c = row.control[id], flip = prev && prev.control && (prev.control[id] || null) !== (c || null);
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
    const side = (k) => `<span${k ? ` class="m-sc" style="${sideText(k)}"` : ""}>${esc(flipSide(k))}</span>`;
    const list = [...row.events.map((t) => `<div class="m-evt">📜 <b>${esc(t)}</b></div>`),
      ...row.changed.map((e) => `<div class="m-evt">⇄ ${name(e.id)}：${side(e.from)} → ${side(e.to)}</div>`)].join("");
    const wk = Number(week); // 7 天濃縮季寫段（wkName，FB-501）
    return `<div class="m-tl-head"><b>天下怎麼變<small>${wkName(wk, `第 ${wk} 週週末`, true)}</small></b><button type="button" data-act="map-play">▶ 播放</button><button type="button" data-act="map-now">回到現在</button>${close}</div>
      ${graphSvg(st, week)}<div class="m-sum">${sum}</div>${chartHtml(base, st, week)}
      <div class="m-sec"><h4>${wkName(wk, `第 ${wk} 週`)}</h4>${list || '<div class="m-sub">沒有地點易手。</div>'}</div>`;
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
      banner.textContent = `正在看${wkName(S.mapWeek, `第 ${S.mapWeek} 週`)}`;
    }
  }
  // 打開、收起版圖變化（設計 5.1：在天下圖上播）：打開時換到天下圖（地圖框縮到抽屜上面，天下圖照那一塊重新取景）；收起時留在天下圖。
  // 開、收都回 1 倍（地圖框換了大小）；看的時候與播放中照樣能拖縮（播放只換記號，企劃者 2026-10-22 的拖縮計畫 3.1）
  function mapTimeline(open) {
    stopPlay();
    if (!document.getElementById("mapx")) return;
    if (open) Object.assign(S, { mapLayer: "world", mapMode: "timeline", mapSel: null, mapWeek: S.mapState.now_week, mapDrawer: "tl", mapPan: null, panFrom: null });
    else Object.assign(S, { mapMode: "overview", mapSel: null, mapWeek: null, mapDrawer: "min", mapPan: null, panFrom: null });
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
  // 抽屜的把手：拖上拖下（放開時靠到最近的一格），點一下在兩格之間換：卡在半開、全開之間；天下圖收著那一行與拉開的卡之間；
  // 區圖收著那一行點了照「攤開」（map-open）
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
      const stops = drawerStops();
      if (!drag.moved) {
        if (S.mapLayer !== "world" && S.mapMode === "overview") mapOpen();
        else setMapDrawer(S.mapDrawer === stops[0] ? stops[stops.length - 1] : stops[0]);
      } else {
        const h = drawer.offsetHeight;
        setMapDrawer(stops.slice().sort((a, z) => Math.abs(mapDrawerPx(a) - h) - Math.abs(mapDrawerPx(z) - h))[0]);
      }
      drag = null;
    };
    grab.addEventListener("pointerup", end);
    grab.addEventListener("pointercancel", end);
  }
  // 抽屜此刻可以停的幾格（拖動放開時靠到最近的一格）
  function drawerStops() {
    if (S.mapMode === "place") return ["peek", "half", "full"];
    if (S.mapMode === "timeline") return ["tl", "half", "full"];
    if (S.mapMode === "search") return ["half", "full"];
    return S.mapLayer === "world" ? ["min", "half", "full"] : ["min"];
  }
  // 收著那一行點了（或區圖點了把手）：天下圖拉開你腳下這一處的卡；區圖你在這一區時開你腳下這一處的卡
  function mapOpen() {
    if (S.mapLayer === "world") { setMapDrawer("half"); return; }
    const st = S.mapState, here = st && !st.journey && placeOf(S.mapBase, st.here);
    if (!here || here.region !== S.mapRegion) return;
    S.mapSel = here.id;
    S.mapMode = "place";
    setMapDrawer("peek");
    redrawDrawer();
    drawSel();
  }

  function redrawDrawer() {
    const body = document.getElementById("mbody");
    if (body) body.innerHTML = drawerHtml();
  }
  // 桌機（寬 900 以上）抽屜是右欄、整欄攤開，沒有收起這回事
  const deskMap = () => !!(window.matchMedia && window.matchMedia("(min-width: 900px)").matches);
  // 抽屜的高度：收著 54（把手 22＋一行 32）、卡半開（區圖照取景框底下還空著多少，peekPx）、拉高六成、全開九成四、版圖變化 320；
  // 桌機是右欄（CSS 蓋掉高度）
  function mapDrawerPx(h) {
    const box = document.getElementById("mapx");
    const avail = (box && box.clientHeight) || 600;
    // 版圖變化 320 高（企劃者 10/15 從對比圖選乙）：地圖大一截，曲線與處數在一屏，年表往下捲
    return { min: 54, peek: peekPx(avail), half: Math.round(avail * 0.6), full: Math.round(avail * 0.94), tl: Math.min(320, Math.round(avail * 0.55)) }[h] || 54;
  }
  // 卡半開多高：區圖照取景框底下還空著多少（卡不蓋到地點，地圖不動；設計 5.2），最矮 REGION_PEEK_MIN、最高六成；沒有區圖的取景照 240
  function peekPx(avail) {
    const v = S.mapLayer !== "world" ? S.regionView : null;
    const room = v && v.bottom ? Math.round(avail - v.bottom - 4) : 240;
    return Math.max(REGION_PEEK_MIN, Math.min(Math.round(avail * 0.6), room));
  }
  function setMapDrawer(h) {
    S.mapDrawer = h;
    const d = document.getElementById("mdrawer"), box = document.getElementById("mapx");
    if (!d || !box) return;
    const px = mapDrawerPx(h);
    d.style.height = `${px}px`;
    // 收著換成那一行（或從那一行攤開）：抽屜裡的內容跟著換
    const min = h === "min" && !deskMap();
    if (d.classList && d.classList.contains("min") !== min) {
      d.classList.toggle("min", min);
      const body = document.getElementById("mbody");
      if (body && S.mapBase && S.mapState) body.innerHTML = drawerHtml();
    }
    const grab = document.getElementById("mgrab");
    if (grab && grab.setAttribute) grab.setAttribute("aria-label", min ? "攤開" : "拉高拉低");
    // --md-h 只有版圖變化用得到（地圖框縮到抽屜上面，style.css 的 .mapx.tl-mode）：自訂屬性會一路繼承下去，平常點地點換抽屜高度時
    // 寫它會逼整棵地圖重算樣式（FB-322）
    if (S.mapMode === "timeline") box.style.setProperty("--md-h", `${px}px`);
  }
  // 整頁那一層夾在狀態列與分頁列之間：狀態列展開收起、視窗換大小時重量。回傳兩條邊有沒有變（變了地圖框就換了高，取景要重套：FB-710）
  function mapFrame() {
    const box = document.getElementById("mapx");
    if (!box) return false;
    const top = document.getElementById("top"), tabs = document.querySelector(".tabs");
    const t = `${top && !top.hidden ? Math.round(top.getBoundingClientRect().bottom) : 0}px`;
    const b = `${tabs ? Math.round(window.innerHeight - tabs.getBoundingClientRect().top) : 0}px`;
    const was = typeof box.style.getPropertyValue === "function" ? [box.style.getPropertyValue("--map-top"), box.style.getPropertyValue("--map-bottom")] : null;
    // 變了才寫：自訂屬性會繼承到整張地圖，寫一次整棵約 1,600 個元素重算樣式（狀態列每次重畫都叫這裡，Joy 2026-10-17）
    setVar(box, "--map-top", t);
    setVar(box, "--map-bottom", b);
    return !was || was[0] !== t || was[1] !== b;
  }
  let marksFrame = 0;
  // 這一層此刻的取景：天下圖 S.worldView（worldFit）、區圖 S.regionView（regionFit）；都由 applyMapView 照地圖框現在的大小算
  const curView = () => (S.mapLayer === "world" && S.mapBase && S.mapBase.world ? S.worldView : S.regionView);
  // 記號照哪一個取景畫的（層、區、倍率、地圖框大小）：一樣就不必重畫
  const viewKey = (v, g) => (v && g ? `${S.mapLayer}|${S.mapRegion}|${f2(v.s)}|${g.vw}x${g.vh}` : "");
  // 照現在的取景、週次重畫記號（天下圖 worldParts、區圖 regionParts），底圖的州界與大區名照這一層收
  function drawMarks() {
    marksFrame = 0;
    const g = document.getElementById("mk"), v = curView(), geo = mapGeom(document.getElementById("map"));
    if (!g || !S.mapBase || !S.mapState || !v) return;
    const world = S.mapLayer === "world" && !!S.mapBase.world;
    S.marksKey = viewKey(v, geo);
    // 兩張圖都自己寫大區名：底圖寫的那一份藏起來（直接改那幾個字的 display，不在框上加 class：框上的 class 一變，整棵地圖都要重算樣式）
    const wrap = document.getElementById("map");
    if (wrap && !wrap.dataset.names) {
      wrap.dataset.names = "1";
      wrap.querySelectorAll(".tx-region-name").forEach((el) => { el.style.display = "none"; });
    }
    // 天下圖：底圖的大區底色與點劃線州界讓位給地面與州的輪廓；區圖：州界的點劃線收掉、大區的淡色留著（設計 5.2）
    document.querySelectorAll("#map path[data-region]").forEach((el) => {
      el.style.stroke = "none";
      if (world) el.style.fill = "none"; else el.style.removeProperty("fill");
    });
    const [low, high] = world ? worldParts(S.mapBase, S.mapState, { k: 1 / v.s, week: mapWeek(), tl: S.mapMode === "timeline", sel: null, area: v.area || null })
      : regionParts(S.mapBase, S.mapState, { v, vw: geo ? geo.vw : 375, vh: geo ? geo.vh : 600, rid: S.mapRegion, wash: washOn() });
    g.innerHTML = low;
    const top = document.getElementById("mkt"); // 會跳的圈、你、旗子（FB-323）
    if (top) top.innerHTML = `${high}<g id="msel" pointer-events="none"></g>`;
    drawSel();
  }
  // 選了的地點那一圈（畫在上面那一張最後）：點一處只換那一圈，不必整批重建記號。天下圖是年表上圈起來的地點（map-mark）
  function drawSel() {
    const box = document.getElementById("msel"), v = curView();
    if (!box || !v) return;
    const p = S.mapSel && placeXY(S.mapSel);
    if (!p) { if (box.firstChild) box.innerHTML = ""; return; }
    const k = 1 / v.s, world = S.mapLayer === "world";
    box.innerHTML = `<circle cx="${p[0]}" cy="${p[1]}" r="${f1((world ? 11 : 21) * k)}" fill="none" stroke="${MAP_INK}" stroke-width="${f1((world ? 2.5 : 2.8) * k)}"/>`;
  }
  const scheduleMarks = () => { if (!marksFrame) marksFrame = requestAnimationFrame(drawMarks); };

  // ── 天下圖（輿圖簡化設計 5.1、3.3、5.6；環形版 dev/map-2 寫的，輿圖第三版第 3 批搬回真實地形）──
  // 打開輿圖第一眼。不另開一張圖：同一張底圖（山水已經烤成點陣）換一個固定的取景（worldFit：取景框整張放進地圖框露出來的那一塊），
  // 上面疊一層拖與縮放（企劃者 2026-10-22，「輿圖的拖與縮放」那一段：整張連字一起動，不重畫）；記號那一層（#mk、#mkt）畫大區地面——每一區（程式裡叫「州」）的地面照「離哪個地點最近」分給那個地點此刻的控制方
  // （底圖的 world.cells，照那一區的輪廓裁），一方一色、沒人佔一色（顏色照劇本，sideInk）——、正在翻（攻方的斜紋照進度泛進來）、
  // 剛易手還在冷卻（新主人的淡色、一圈虛線）、
  // 紅線（任兩方的地面相接；真實地形的大區互不相接，前線都在同一區裡）、細墨線（有主與沒人佔相接）、激戰（那一格一圈紅光閃）、
  // 大區的輪廓、金點（高級資源地：實心＝有人佔）、大區名與各方幾處、你。點一區進那一區的區圖（enterRegion）。字待 joy 潤
  const WORLD_WORD = "天下", WORLD_ENTER = "進入此區", RICH_WORD = "寶";
  const WORLD_TOP = 58; // 上面那一排（天下・找地點・版圖）讓開多高（px）
  const WORLD_TL_TOP = 36; // 版圖變化時那一排收起，只讓開「正在看第 N 週」
  const WORLD_PAD = 54; // 抽屜收著時的高度：天下圖照它讓開底下（拉開的卡蓋在圖上，圖不跟著縮）
  const WORLD_EDGE = 8; // 取景框離地圖框的邊至少多少（px）
  const WORLD_GROUND = 0.8; // 地面的濃淡：底下的山水淡淡地透上來（設計 4.5）
  const WORLD_INK = "#3A3127", WORLD_RIM = "#5B4A38", WORLD_GOLD = "#C8961E";
  const WORLD_NAME_PX = 16, WORLD_LINE_PX = 11; // 大區名、大區名底下那一行，螢幕上的大小
  const WORLD_FULL_PX = 330, WORLD_SHRINK = 0.82; // 取景框在螢幕上不到這麼寬時字照比例縮，最多縮到這麼多（11px 的那一行縮到 9px）
  const WORLD_DOT_PX = 13; // 大區名讓開金點的框（px；金點半徑 4.2、線寬 1.6，四周再留一點，FB-630）
  // 大區名的位置都會壓到時往哪裡挪（照框的寬、高的倍數）：左右最多三個框、上下最多五格，近的先（框是橫的：左右挪一個框算兩格遠）。
  // 版圖變化、320 寬、橫放的天下圖在螢幕上很小（FB-631），名字要能挪到取景框外面露出來的那一塊（worldLabels 的 area）
  const WORLD_NUDGE = worldNudge();
  function worldNudge() {
    const out = [];
    for (let dx = -3; dx <= 3; dx += 0.5) for (let dy = -5; dy <= 5; dy += 0.5) if (dx || dy) out.push([dx, dy]);
    return out.sort((a, z) => Math.hypot(2 * a[0], a[1]) - Math.hypot(2 * z[0], z[1]) || a[1] - z[1] || a[0] - z[0]);
  }
  // 正在翻（設計 4.1）：攻方的斜紋照進度泛進那一格，進度 100 時多濃（底下守方的地面照樣看得到）；斜紋的間距與線寬照螢幕（px）。
  // 資料是疊層的 places[id].tug（{攻方: 進度}，mapdata.flip_marks 照翻地那一份 conquest.block_view 的 bars 換的名字），沒有就不畫
  const WORLD_TUG_MAX = 0.75, WORLD_TUG_GAP = 5, WORLD_TUG_LINE = 2.2;
  // 剛易手、還在冷卻（疊層的 places[id].cool：還要幾分鐘；設計 4.1 兩邊都推不動、加成暫停）【開發定】：地面換成新主人那一方的淡色（tint）、
  // 那一格一圈新主人顏色的虛線（還沒站穩），不閃。虛線的長短照螢幕（px）
  const WORLD_COOL_DASH = 4, WORLD_COOL_GAP = 3, WORLD_COOL_LINE = 1.4;
  // 下了戰書、還沒開集結（疊層的 siege 是 letter）：那一格一圈朱紅虛線框（輿圖第三版第 5 批，企劃者 2026-10-22 挑 A 乙）；比冷卻那一圈粗、
  // 線段長，顏色是前線那一種朱紅（不是哪一方的顏色），不閃
  const WORLD_LETTER_DASH = 6, WORLD_LETTER_GAP = 3.5, WORLD_LETTER_LINE = 2.6;
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
  // 地圖框露出來的那一塊（上面讓開 top、底下讓開 pad、四邊留 WORLD_EDGE），換成地圖單位 [x0, y0, x1, y1]：大區名可以擺到這裡（FB-631）
  function worldArea(v, vw, vh, top, pad) {
    const k = 1 / v.s;
    return [v.cx + (WORLD_EDGE - vw / 2) * k, v.cy + (top + WORLD_EDGE - vh / 2) * k, v.cx + (vw / 2 - WORLD_EDGE) * k, v.cy + (vh / 2 - pad - WORLD_EDGE) * k];
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
  // 底圖給每一區幾個可以擺的位置（好的在前），每一個位置附近再挪一挪（WORLD_NUDGE）；小的大區先挑（底圖的 area）。
  // 挑的先後：不壓別的大區名、你（紅點、紅旗；畫在上面那一張，會蓋住字）、高級資源地的金點（FB-630）的第一個；不行就只讓別的大區名與你；
  // 都不行就收掉底下那一行再找一次（FB-631：版圖變化、320 寬、橫放、四方劇本的天下圖在螢幕上很小，大區名彼此不壓是硬規矩，數字在年表看得到）；
  // 再不行（只讓別的大區名）用第一個位置。夾在 area 裡（地圖單位 [x0, y0, x1, y1]：地圖框露出來的那一塊，applyMapView 照取景算；
  // 沒給照取景框）——取景框在螢幕上很窄時（橫放、版圖變化）名字可以擺到框外面的空處
  function worldLabels(base, st, ctrl, k, area = null) {
    const wd = base.world, n = worldCounts(base, st, ctrl), sides = st.sides || sideOrder(base);
    const [fx, fy, fw, fh] = wd.frame, placed = {};
    const [ax0, ay0, ax1, ay1] = area || [fx, fy, fx + fw, fy + fh];
    // 天下圖在螢幕上很小時（320 寬、版圖變化把框縮到抽屜上面）字跟著縮一點，最多縮到 WORLD_SHRINK
    const shrink = Math.max(WORLD_SHRINK, Math.min(1, fw / k / WORLD_FULL_PX));
    const np = WORLD_NAME_PX * shrink, lp = WORLD_LINE_PX * shrink;
    const order = [...wd.regions].sort((a, z) => (a.area || 0) - (z.area || 0));
    const me = st.journey || placeOf(base, st.here);
    const you = me && me.x !== undefined ? [{ x: me.x + 2 * k, y: me.y - 7 * k, w: 24 * k, h: 34 * k }] : [];
    const dots = base.places.filter((p) => st.places[p.id] && st.places[p.id].rich).map((p) => ({ x: p.x, y: p.y, w: WORLD_DOT_PX * k, h: WORLD_DOT_PX * k }));
    const hits = (b, x, y, w, h) => Math.abs(b.x - x) * 2 < b.w + w && Math.abs(b.y - y) * 2 < b.h + h;
    for (const r of order) {
      const c = n[r.id] || { rich: 0 };
      // 只寫有的：是 0 的那一方、寶 0 都不寫；全是 0 那一行就不畫（企劃者 2026-10-20 從對比圖選乙）
      const full = [...sides.filter((sd) => c[sd]).map((sd) => `${sideInk(sd).short} ${c[sd]}`), ...(c.rich ? [`${RICH_WORD} ${c.rich}`] : [])].join("・");
      const box = (line) => {
        const w = Math.max(textW(r.name, np), textW(line, lp)) * k + 6 * k, h = (line ? np + 3 + lp : np) * k + 4 * k;
        const fit = ([x, y]) => [Math.min(ax1 - w / 2, Math.max(ax0 + w / 2, x)), Math.min(ay1 - h / 2, Math.max(ay0 + h / 2, y))];
        const spots = (r.spots && r.spots.length ? r.spots : [[r.lx, r.ly]]).map(fit);
        const cands = [...spots, ...spots.flatMap(([sx, sy]) => WORLD_NUDGE.map(([dx, dy]) => fit([sx + dx * w, sy + dy * h])))];
        return { line, w, h, cands };
      };
      const tries = full ? [box(full), box("")] : [box("")];
      const free = (b, avoid) => b.cands.find(([x, y]) => !Object.values(placed).some((o) => hits(o, x, y, b.w, b.h)) && !avoid.some((o) => hits(o, x, y, b.w, b.h)));
      let got = null;
      for (const [b, avoid] of [[tries[0], [...you, ...dots]], [tries[0], you], ...(tries[1] ? [[tries[1], [...you, ...dots]], [tries[1], you]] : []), [tries[0], []], ...(tries[1] ? [[tries[1], []]] : [])]) {
        const at = free(b, avoid);
        if (at) { got = { ...b, x: at[0], y: at[1] }; break; }
      }
      if (!got) got = { ...tries[0], x: tries[0].cands[0][0], y: tries[0].cands[0][1] };
      placed[r.id] = { id: r.id, x: got.x, y: got.y, w: got.w, h: got.h, name: r.name, line: got.line, np, lp };
    }
    return wd.regions.map((r) => placed[r.id]);
  }
  // 正在翻那一層的斜紋（每一個出現在 tug 裡的攻方一個 <pattern>，顏色照 sideInk；地圖單位，k＝1／倍率）
  function tugPattern(side, k) {
    const ink = sideInk(side), gap = f1(WORLD_TUG_GAP * k);
    return `<pattern id="wt-${esc(side)}" patternUnits="userSpaceOnUse" width="${gap}" height="${gap}" patternTransform="rotate(45)">`
      + `<rect width="${gap}" height="${gap}" fill="${ink.soft}" fill-opacity=".55"/><line x1="0" y1="0" x2="0" y2="${gap}" stroke="${ink.color}" stroke-width="${f1(WORLD_TUG_LINE * k)}"/></pattern>`;
  }
  // 這一格正在被誰翻、翻到幾成（疊層的 tug 裡進度最高的那一方；守方自己、進度 0 不算）；沒有是 null。區圖的進度條也照它
  function tugOf(st, id, holder) {
    const t = st.places[id] && st.places[id].tug;
    if (!t) return null;
    const best = Object.entries(t).filter(([sd, v]) => sd !== holder && Number(v) > 0).sort((a, z) => Number(z[1]) - Number(a[1]))[0];
    return best ? { side: best[0], pct: Math.min(100, Number(best[1])) } : null;
  }
  // 天下圖的記號（純函式）：o = { k: 1／倍率, week: 看哪一週, tl: 正在看版圖變化, sel: 年表上圈起來的地點, area: 露出來的那一塊（地圖單位，
  // 大區名可以擺到哪；沒給照取景框） }。回 [底下那一張, 上面那一張]
  // （同區圖 regionParts：會跳的圈與你畫在上面那一張 #mkt）
  function worldParts(base, st, o) {
    const wd = base.world, k = o.k, ctrl = controlAt(st, o.week), pos = Object.fromEntries(base.places.map((p) => [p.id, p]));
    // 正在翻、激戰、冷卻是「此刻」的事：版圖變化看以前的週時不畫
    const live = o.week === st.now_week;
    const cooling = (id) => live && !!ctrl[id] && !!(st.places[id] && st.places[id].cool);
    const ground = (id) => (ctrl[id] ? sideInk(ctrl[id])[cooling(id) ? "tint" : "soft"] : wd.unheld);
    const tugs = live ? wd.cells.map((c) => [c, tugOf(st, c.id, ctrl[c.id] || null)]).filter(([, t]) => t) : [];
    // 激戰：兩邊都有人在推（melee）；攻城集結・交戰中（siege 是 fight）借同一種紅光（輿圖第三版第 5 批，企劃者 2026-10-22 挑 B 甲）
    const melee = live ? wd.cells.filter((c) => st.places[c.id] && (st.places[c.id].melee || st.places[c.id].siege === "fight")) : [];
    // 下了戰書、還沒開集結：那一格一圈朱紅虛線框（企劃者挑 A 乙）
    const letters = live ? wd.cells.filter((c) => st.places[c.id] && st.places[c.id].siege === "letter") : [];
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
    for (const c of letters) out.push(`<path class="w-letter" data-cell="${esc(c.id)}" d="${c.d}" fill="none" stroke="${FRONT_RED}" stroke-width="${f1(WORLD_LETTER_LINE * k)}" stroke-dasharray="${f1(WORLD_LETTER_DASH * k)} ${f1(WORLD_LETTER_GAP * k)}" stroke-linejoin="round" clip-path="url(#wc-${esc(c.region)})" pointer-events="none"/>`);
    // 點一區：整區一塊透明的點擊區
    for (const r of wd.regions) out.push(`<path data-act="world-region" data-id="${esc(r.id)}" d="${r.d}" fill="#000000" fill-opacity="0" style="cursor:pointer"><title>${esc(r.name)}</title></path>`);
    // 金點：高級資源地（開季中立的），實心＝此刻有人佔、空心＝沒人佔
    for (const p of base.places) {
      if (!st.places[p.id] || !st.places[p.id].rich) continue;
      const held = !!ctrl[p.id];
      out.push(`<circle class="w-rich${held ? " held" : ""}" cx="${p.x}" cy="${p.y}" r="${f1(4.2 * k)}" fill="${held ? WORLD_GOLD : MAP_HALO}" stroke="${WORLD_GOLD}" stroke-width="${f1(1.6 * k)}" pointer-events="none"/>`);
    }
    // 大區名、底下那一行
    for (const l of worldLabels(base, st, ctrl, k, o.area || null)) {
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
  // （設計 5.1、5.3：placeCard）。點那一行攤開
  function worldDrawerHtml(base, st) {
    const j = st.journey, here = placeOf(base, st.here);
    const region = here && base.regions.find((r) => r.id === here.region);
    const where = j ? `往 <b>${esc(j.to_name)}</b>・還有 ${Number(j.minutes)} 分鐘` : `你在 <b>${esc(region ? region.name : "")}</b>・${esc(here ? here.name : "")}`;
    const enter = `<button type="button" class="m-enter" data-act="world-enter">${WORLD_ENTER} ›</button>`;
    if (S.mapDrawer === "min" && !deskMap()) return `<div class="m-wline"><button type="button" class="m-mini" data-act="map-open" aria-label="攤開抽屜"><span>${where}</span></button>${enter}</div>`;
    if (j) return `${journeyHtml(st)}<div class="m-wline"><span></span>${enter}</div>`;
    return `<div class="m-wline"><span class="m-where">${where}</span>${enter}</div>${here ? placeCard(base, st, st.here) : ""}`;
  }

  // ── 區圖（輿圖簡化設計 5.2、5.5、5.6；輿圖第三版第 4 批）──
  // 點一區（或「進入此區」、找地點挑一處）：同一張底圖換一個固定的取景（regionFit：這一區地點的外框加邊），上面疊一層拖與縮放
  // （企劃者 2026-10-22：整張連字一起動，擺法不重算）。只畫這一區的地點：
  // 墨筆小圖（線色＝誰佔著）、名字裝在印章框裡（框色＝誰的，顏色照劇本 sideInk、沒人佔照底圖的 unheld；大城框粗）、框裡的下緣一條細進度條
  // （攻方的顏色；剛易手整條灰、不寫字，FB-648 第二段乙）、朱印「寶」、名字底下最多兩個意境字（最濃的在前）、你的朱圈與旗、通到鄰區的路在取景框邊寫「→ 南陽」
  // （點了換到那一區）、取景框外蓋一層半透明的紙。底圖的州界點劃線收掉、大區名藏起來，路照 CSS 換成一種淡實線（style.css 的
  // .mapx.region .tx-roads）。「塗層」開了多一層照歸屬融成一片的淡彩（草圖清甲）。名字框的位置照螢幕大小挑（regionLabels）：不壓別的名字框、
  // 小圖、你的旗、鄰區出口；擠不下時這一區的名字縮一號。點一處：抽屜半開那一處的卡，地圖不動（取景先替半開的卡留位子，peekPx）。字待 joy 潤
  const REGION_TOP = 58; // 上面那一排（‹ 天下・大區・版圖）讓開多高（px）
  const REGION_PAD = 54; // 抽屜收著那一行
  // 取景框四邊留多少（px）：旗在上面、意境字在下面；左右只留一點（名字框靠邊的往裡擺），寬的大區（潁川汝南）倍率才拉得上去
  const REGION_EDGE = { l: 8, r: 8, t: 40, b: 30 };
  // 優先替半開的卡留多高（px）：留了倍率還不低於 REGION_READ 才照留，不然整塊照放（短的螢幕：卡拉開時會蓋到下緣）
  const REGION_CARD = 270, REGION_READ = 0.9, REGION_MAX = 2, REGION_PEEK_MIN = 200;
  const R_PADX = 5, R_PADY = 3.5, R_GAP = 3; // 印章框的內距、框離小圖多遠（px）
  // 進度條收在印章框裡的下緣（FB-648 第二段，企劃者 2026-10-22 選乙）：高 R_BAR、貼著框線內側（框線一般 R_LINE、大城 R_LINE_BIG），
  // 名字的字腳碰不到（框底的內距 R_PADY 夠放）
  const R_BAR = 2.5, R_LINE = 1, R_LINE_BIG = 1.7, R_INS_GAP = 1, R_SEAL = 15, R_SEAL_GAP = 3, R_EXIT = 11.5;
  // 攻城戰（輿圖第三版第 5 批，企劃者 2026-10-22 挑 A 乙、B 甲）：「戰」字印紙底朱框朱字（字待 joy 潤），找位置時四周多留 R_LETTER_PAD；
  // 交戰中名字框外那一圈紅離框多遠、多粗
  const LETTER_SEAL_WORD = "戰", LETTER_SEAL_PAPER = "#FFF8EC", R_LETTER_PAD = 1, R_FIGHT_OUT = 2, R_FIGHT_LINE = 1.6;
  // 不同地點的兩列（印章框＋寶那一列、意境字那一列）之間至少隔多少 px（FB-651：南陽官道的意境字貼著南陽郊野的「寶」只隔 1.3px，
  // 意境字的紙色描邊再往外 1.3px，讀起來像「南陽郊野 寶 風火」）：x、y 兩個方向都不到這麼遠就算貼著。照不相交擺好之後再試著讓開
  // （regionLabelsAt 的 spaced：名字不准因此離自己的小圖更遠 R_NEAR 以上），讓不開照原本的；擠不下（縮一號）照舊只看相交，不為了留空縮字
  const R_ROW_GAP = 3;
  const rowGrow = (r) => [r[0] - R_ROW_GAP, r[1] - R_ROW_GAP, r[2] + R_ROW_GAP, r[3] + R_ROW_GAP];
  // 區圖記號在螢幕上多大（px）：放得大的區（倍率 1 以上）小圖與字大一號；擠的區（潁川汝南在手機上約 0.68 倍）照小的那一號才擺得開
  // （設計第十二章：375 寬互相不壓）。icon 是墨筆小圖照草圖（20px 見方）放大幾倍，hw、hh 是小圖在螢幕上佔的半寬、半高
  function regionSizes(s) {
    return s >= 1 ? { icon: 1.2, hw: 12.5, hh: 11.5, name: 14, nameBig: 15, ins: 11.5 } : { icon: 1, hw: 10.5, hh: 10, name: 12, nameBig: 13, ins: 10 };
  }
  // 擠不下時這一區的名字縮一號（FB-648 第二段乙，企劃者 2026-10-22）：小圖不變，名字與底下的意境字換小一號——大一號的那一區（倍率 1 以上：
  // 14／15、意境字 11.5）換回平常那一號（12／13、10），平常那一號再小一點（R_SMALL：11／12、9）。只縮名字、意境字不縮的話，360 寬你站嵩山深處、
  // 南陽 375×624 你站宛城等幾處還是擠不下（量過）
  const R_SMALL = { name: 11, nameBig: 12, ins: 9 };
  function regionSmaller(z) {
    const plain = regionSizes(0);
    return z.name > plain.name ? { ...z, name: plain.name, nameBig: plain.nameBig, ins: plain.ins } : { ...z, ...R_SMALL };
  }
  const RICH_SEAL = "#B03A2E", BAR_TRACK = "#D8CDB4", COOL_GREY = "#B3AA98";
  const R_WASH = { r: 64, blur: 8, warp: 20, freq: 0.024, op: 0.42 }; // 塗層（草圖清甲）：每一處一團多大、暈開、邊緣扭幾分（px）、整層多濃
  const R_MASK = 3, R_MASK_STEP = 7, R_MASK_OP = 0.35; // 取景框外的紙：三層、每層往外推 7px、每層多濃（最外面約七成三）
  const WASH_WORD = "塗層"; // 待 joy 潤
  const WASH_KEY = "tx-map-wash"; // 塗層開關記在這個瀏覽器（平常關著）
  function washOn() {
    if (S.mapWash === undefined) { try { S.mapWash = localStorage.getItem(WASH_KEY) === "1"; } catch (e) { S.mapWash = false; } }
    return !!S.mapWash;
  }
  function washToggle() {
    S.mapWash = !washOn();
    try { localStorage.setItem(WASH_KEY, S.mapWash ? "1" : "0"); } catch (e) { /* 記不住就只管這一次 */ }
    const btn = document.querySelector(".r-wash");
    if (btn) { btn.classList.toggle("on", S.mapWash); btn.setAttribute("aria-pressed", String(S.mapWash)); }
    drawMarks();
  }
  // 左下角的羅盤（裝飾，企劃者挑的「一乙」）：螢幕上固定，不跟地圖
  function compassSvg() {
    const pts = [];
    for (let a = 0; a < 360; a += 45) { const r = a % 90 ? 4.5 : 15, t = ((a - 90) * Math.PI) / 180; pts.push(`${f1(22 + r * Math.cos(t))},${f1(30 + r * Math.sin(t))}`); }
    return `<svg viewBox="0 0 44 54" width="40" height="49" aria-hidden="true"><circle cx="22" cy="30" r="19" fill="${MAP_HALO}" fill-opacity=".85" stroke="${MAP_INK}" stroke-width="1"/>`
      + `<polygon points="${pts.join(" ")}" fill="${MAP_INK}" opacity=".75"/><path d="M22 15L25.5 30H18.5Z" fill="${FRONT_RED}"/>`
      + `<text x="22" y="9" font-size="9" text-anchor="middle" fill="${FRONT_RED}" style="font-family:serif">北</text></svg>`;
  }
  // 區圖上面那一排：‹ 天下、大區名下拉（換一區）、塗層、⏱ 版圖（塗層排在這一排：浮在圖上會蓋到右上角的名字框）；左下角羅盤
  function regionTopHtml() {
    const base = S.mapBase, regions = base ? base.regions : [];
    const opts = regions.map((r) => `<option value="${esc(r.id)}"${r.id === S.mapRegion ? " selected" : ""}>${esc(r.name)}</option>`).join("");
    const tl = S.mapMode === "timeline", wash = washOn();
    return `<div class="r-top"><button type="button" class="w-back" data-act="map-world">‹ ${WORLD_WORD}</button>`
      + `<label class="r-pick-box"><select class="r-pick" data-act="region-pick" aria-label="換一區">${opts}</select></label>`
      + `<button type="button" class="r-wash${wash ? " on" : ""}" data-act="map-wash" aria-pressed="${wash}">${WASH_WORD}</button>`
      + `<button type="button" class="w-tl${tl ? " on" : ""}" data-act="map-timeline" aria-pressed="${tl}">⏱ 版圖</button></div>`
      + `<div class="r-compass">${compassSvg()}</div>`;
  }
  const regionPlaces = (base, rid) => base.places.filter((p) => p.region === rid);
  // 一區的取景（螢幕 vw × vh；上面讓開 top、底下讓開收著的抽屜 pad，card＞0 時優先替半開的卡留位子）：這一區地點的外框四邊照螢幕留邊，
  // 手機靠上（底下給卡）、桌機（card 0）置中。回 { s, cx, cy, frame: 取景框（地圖單位：外框加邊）, bottom: 取景框下緣在螢幕上的 y }
  function regionFit(base, rid, vw, vh, top = REGION_TOP, pad = REGION_PAD, card = REGION_CARD) {
    const pts = regionPlaces(base, rid);
    if (!pts.length) return null;
    const xs = pts.map((p) => p.x), ys = pts.map((p) => p.y);
    const x0 = Math.min(...xs), y0 = Math.min(...ys), x1 = Math.max(...xs), y1 = Math.max(...ys);
    const E = REGION_EDGE, bw = Math.max(1, x1 - x0), bh = Math.max(1, y1 - y0);
    const aw = Math.max(1, vw - E.l - E.r), ah = Math.max(1, vh - top - pad - E.t - E.b);
    let s = Math.min(aw / bw, ah / bh, REGION_MAX);
    const leave = Math.max(0, ah - card) / bh; // 替半開的卡留了位子還能多大
    if (card > 0 && leave < s && leave >= REGION_READ) s = leave;
    const left = E.l + (aw - bw * s) / 2, upper = top + E.t + (card > 0 ? 0 : (ah - bh * s) / 2);
    const k = 1 / s;
    return { s, cx: x0 + (vw / 2 - left) * k, cy: y0 + (vh / 2 - upper) * k, frame: [x0 - E.l * k, y0 - E.t * k, x1 + E.r * k, y1 + E.b * k], bottom: upper + bh * s + E.b };
  }
  // 通到鄰區的路（一頭在這一區、一頭在別區）：從這一頭往那一頭的直線碰到取景框邊的那一點（螢幕 px）、貼著哪一邊、寫什麼
  // （「→ 南陽」，箭頭照出去的方向）；那一頭的地點就在框裡（碰不到框邊）時是那一點、edge 是 null
  function regionExitAnchors(base, rid, v, vw, vh) {
    const pos = Object.fromEntries(base.places.map((p) => [p.id, p])), names = Object.fromEntries(base.regions.map((r) => [r.id, r.name]));
    const [fx0, fy0, fx1, fy1] = v.frame, scr = (x, y) => [vw / 2 + (x - v.cx) * v.s, vh / 2 + (y - v.cy) * v.s];
    const out = [];
    for (const [a, b] of base.edges) {
      const A = pos[a], B = pos[b];
      if (!A || !B || (A.region === rid) === (B.region === rid)) continue;
      const [P, Q] = A.region === rid ? [A, B] : [B, A];
      const dx = Q.x - P.x, dy = Q.y - P.y;
      let t = 1, edge = null;
      if (dx && ((dx > 0 ? fx1 : fx0) - P.x) / dx < t) { t = ((dx > 0 ? fx1 : fx0) - P.x) / dx; edge = dx > 0 ? "r" : "l"; }
      if (dy && ((dy > 0 ? fy1 : fy0) - P.y) / dy < t) { t = ((dy > 0 ? fy1 : fy0) - P.y) / dy; edge = dy > 0 ? "b" : "t"; }
      const [X, Y] = scr(P.x + dx * t, P.y + dy * t);
      const arrow = Math.abs(dx) >= Math.abs(dy) ? (dx > 0 ? "→" : "←") : dy > 0 ? "↓" : "↑";
      const text = `${arrow} ${names[Q.region] || Q.region}`;
      if (out.some((e) => e.to === Q.region && Math.hypot(e.X - X, e.Y - Y) < 36)) continue; // 同一區、相距很近的只寫一個
      out.push({ to: Q.region, from: P.id, text, w: textW(text, R_EXIT) + 6, h: R_EXIT + 5, X, Y, edge });
    }
    return out;
  }
  // 鄰區出口的字擺哪（名字框擺好之後）：貼著出去的那一邊、往框裡收 3px，壓到名字框或小圖就沿著那一邊滑開（近的先，最多 120px），
  // 都不行挑壓得最少的。回 [{ to, text, box: [左, 上, 右, 下]（螢幕 px） }]
  const R_EXIT_SLIDE = [0, ...Array.from({ length: 20 }, (_, i) => (i % 2 ? -1 : 1) * 6 * (Math.floor(i / 2) + 1) * 2)];
  // 鄰區出口的字能擺的那一塊（螢幕 px：取景框與上面那一排、地圖框的交集）與沿著邊滑 d px 的那一格
  function regionExitRoom(v, vw, vh) {
    const scr = (x, y) => [vw / 2 + (x - v.cx) * v.s, vh / 2 + (y - v.cy) * v.s];
    const [bx0, by0] = scr(v.frame[0], v.frame[1]), [bx1, by1] = scr(v.frame[2], v.frame[3]);
    return { top: Math.max(REGION_TOP + 2, by0), bottom: Math.min(vh - 2, by1), left: Math.max(2, bx0), right: Math.min(vw - 2, bx1) };
  }
  function regionExitBox(e, d, room) {
    const along = e.edge === "l" || e.edge === "r" ? [0, 1] : [1, 0]; // 沿著那一邊滑：左右兩邊上下滑、上下兩邊左右滑
    let l = e.edge === "r" ? e.X - e.w - 3 : e.edge === "l" ? e.X + 3 : e.X - e.w / 2;
    let t = e.edge === "b" ? e.Y - e.h - 3 : e.edge === "t" ? e.Y + 3 : e.Y - e.h / 2;
    l = Math.max(room.left, Math.min(room.right - e.w, l + along[0] * d));
    t = Math.max(room.top, Math.min(room.bottom - e.h, t + along[1] * d));
    return [l, t, l + e.w, t + e.h];
  }
  function regionExits(base, rid, v, vw, vh, labels = []) {
    const room = regionExitRoom(v, vw, vh);
    const z = regionSizes(v.s);
    const taken = [...labels.flatMap((l) => l.rows), ...labels.map((l) => [l.X - z.hw, l.Y - z.hh, l.X + z.hw, l.Y + z.hh])];
    const inter = (a, b) => Math.max(0, Math.min(a[2], b[2]) - Math.max(a[0], b[0])) * Math.max(0, Math.min(a[3], b[3]) - Math.max(a[1], b[1]));
    const out = [];
    for (const e of regionExitAnchors(base, rid, v, vw, vh)) {
      let best = null;
      for (const d of R_EXIT_SLIDE) {
        const box = regionExitBox(e, d, room), cost = [...taken, ...out.map((x) => x.box)].reduce((n, b) => n + inter(box, b), 0);
        if (!best || cost < best.cost - 1e-6) best = { cost, box };
        if (cost <= 0) break;
      }
      out.push({ to: e.to, from: e.from, text: e.text, box: best.box, cost: best.cost });
    }
    return out;
  }
  // 一處的名字框有多大（px）：上一列是印章框（＋朱印寶），下一列是意境字。進度條收在印章框裡、剛易手不寫「冷卻幾分」（幾分鐘寫在卡上，
  // placeLine）——FB-648 第二段乙（企劃者 2026-10-22）：框的大小翻不翻地都一樣，名字擺的位置跟沒翻地時一樣，翻地的那一刻名字不跳
  function regionLabelSize(base, st, p, z) {
    const q = st.places[p.id] || {};
    const fs = p.big ? z.nameBig : z.name, fw = textW(p.name, fs) + 2 * R_PADX, fh = fs + 2 * R_PADY;
    const tug = tugOf(st, p.id, q.control || null), cool = !!q.control && !!q.cool;
    const ins = (p.insights || []).map((id) => insightInk(base, id)).filter(Boolean).slice(0, 2);
    // 下了戰書、還沒開集結（疊層的 siege 是 letter）：名字框旁一枚「戰」字印（輿圖第三版第 5 批，企劃者 2026-10-22 挑 A 乙）。字印不算進名字框
    // （框的大小下不下戰書都一樣，名字不跳：同 FB-648 第二段乙），名字擺好之後才找空位（regionLetterSeals）
    const letter = q.siege === "letter";
    const w1 = fw + (q.rich ? R_SEAL_GAP + R_SEAL : 0), w2 = ins.length * (z.ins + 2);
    const low = ins.length ? R_INS_GAP + z.ins + 2 : 0;
    return { fs, fw, fh, w1, w2, low, W: Math.max(w1, w2), H: fh + low, tug, cool, ins, insPx: z.ins, bar: !!(tug || cool), rich: !!q.rich, big: !!p.big,
      letter, fight: q.siege === "fight" };
  }
  // 名字框可以擺的位置（框左上角離地點中心多遠，px），好的在前：右、左、下、上，再往上下（左右）錯開，再隔一層。
  // 只貼著小圖擺、不拉線（企劃者 2026-10-21 從對比圖選乙：潁川汝南擠的地方不拉細點線回小圖）
  function regionLabelSpots(L, z) {
    const hw = z.hw + R_GAP, hh = z.hh + R_GAP, mid = -L.fh / 2, W = L.W, H = L.H;
    const out = [[hw, mid], [-hw - W, mid], [-W / 2, hh], [-W / 2, -hh - H]];
    for (const f of [0.35, 0.7, 1.05, 1.4, 1.8]) out.push([hw, mid - H * f], [hw, mid + H * f], [-hw - W, mid - H * f], [-hw - W, mid + H * f]);
    for (const f of [0.25, 0.5, 0.75, 1]) out.push([-W / 2 + W * f, hh], [-W / 2 - W * f, hh], [-W / 2 + W * f, -hh - H], [-W / 2 - W * f, -hh - H]);
    for (const f of [0, 0.5, -0.5]) out.push([-W / 2 + W * f, hh + H * 0.9], [-W / 2 + W * f, -hh - H * 1.9]);
    return out;
  }
  const REGION_SEARCH = 20000; // 第一輪一起找名字框的位置最多試幾次，再多就換第二輪
  // 第二輪（FB-648）：位置每 R_SLIDE px 一格；一起找最多試 R_SEARCH_WIDE 次；還找不到（真的放不下）時反覆換位置最多 R_SETTLE 次
  const R_SLIDE = 3, R_SEARCH_WIDE = 3000, R_SETTLE = 400;
  const R_RING = [[19, 8], [17, 11], [14, 14], [11, 17], [8, 19]]; // 你的朱圈在第二輪照圓的算：五塊框的半寬、半高疊成一個半徑約 19 的圓
  const R_YOU = 18; // 你的朱圈的外緣（半徑 17、線寬 2.4 的一半，少一點點）：「擠不下」照真的那一圈量
  // 第二輪的名字框位置：第一輪那幾個在前，再補沿著小圖四邊滑的（離小圖由近到遠），範圍不比第一輪遠（照樣貼著小圖、不拉線，企劃者選的乙）。
  // 每一個位置的第三格是「往前挪」時的先後：照離小圖多遠（每 R_NEAR px 一級，同一級照上面的先後），擺好之後名字才挪得回自己的小圖旁邊、
  // 不會留在別處的小圖旁邊（一起找與擺不開時的換位置照上面的先後）
  const R_NEAR = 8;
  function regionLabelSpotsWide(L, z) {
    const hw = z.hw + R_GAP, hh = z.hh + R_GAP, mid = -L.fh / 2, W = L.W, H = L.H, extra = [];
    for (let d = R_SLIDE; d <= 1.8 * H; d += R_SLIDE) for (const s of [1, -1]) extra.push([hw, mid + s * d], [-hw - W, mid + s * d]);
    for (let d = R_SLIDE; d <= W; d += R_SLIDE) for (const s of [1, -1]) extra.push([-W / 2 + s * d, hh], [-W / 2 + s * d, -hh - H]);
    for (let d = 0; d <= W / 2; d += R_SLIDE) for (const s of d ? [1, -1] : [1]) extra.push([-W / 2 + s * d, hh + H * 0.9], [-W / 2 + s * d, -hh - H * 1.9]);
    const gap = ([dx, dy]) => Math.hypot(Math.max(dx, 0, -(dx + W)), Math.max(dy, 0, -(dy + H))); // 小圖中心到名字框最近那一點
    const all = [...regionLabelSpots(L, z), ...extra.sort((a, b) => gap(a) - gap(b))];
    return all.map((o, i) => [o[0], o[1], Math.floor(gap(o) / R_NEAR) * all.length + i]);
  }
  // 名字框擺哪（設計第十二章：375 寬互相不壓）。每一處先列出不壓小圖（每一處的）、你的旗與朱圈、也不出取景框的位置；
  // 再一起找「彼此也不壓」的擺法（同 mapview._place_labels：每次挑剩下位置最少的先擺，擺不下回頭改前面的），找到之後再一處一處往前挪
  // （離小圖近的位置）。第一輪只用 regionLabelSpots 那幾個位置；找不到、或擺好之後鄰區出口沿著邊滑也讓不開名字框（FB-648：翻地中
  // 名字框多了進度條、「冷卻 N 分」，你站的那一處多朱圈與旗），第二輪換 regionLabelSpotsWide、鄰區出口原本的位置也讓開，再找一次。
  // 第一輪擺得下（出口也讓得開）的畫面跟以前一樣。第二輪也找不到（照這種畫法真的放不下）：先一個一個擺，再反覆把壓到東西的那幾處換位置
  // （settle），壓到的只留在擠的那一角。擺好了還互壓（名字框兩兩相交、壓到別處的小圖、你的旗與朱圈、鄰區出口，或出了取景框）＝擠不下：
  // 這一區的名字縮一號（regionSmaller）重擺一次（FB-648 第二段乙，企劃者 2026-10-22）。名字框的大小不看翻地（regionLabelSize），
  // 擺法與縮不縮只看這一區、你站哪、地圖框多大：翻地的那一刻名字不跳。
  // 回每一處（照這一區的地點順序）：大小、框左上角（螢幕 px）、佔的兩列、壓到多少（0＝不壓）
  function regionLabels(base, st, rid, v, vw, vh) {
    const z = regionSizes(v.s), [out, tight] = regionLabelsAt(base, st, rid, v, vw, vh, z);
    return tight ? regionLabelsAt(base, st, rid, v, vw, vh, regionSmaller(z))[0] : out;
  }
  // 照名字的字級 z 擺一次：回 [每一處, 擠不下（還互壓）]
  function regionLabelsAt(base, st, rid, v, vw, vh, z) {
    const pts = regionPlaces(base, rid), scr = (x, y) => [vw / 2 + (x - v.cx) * v.s, vh / 2 + (y - v.cy) * v.s];
    const [bx0, by0] = scr(v.frame[0], v.frame[1]), [bx1, by1] = scr(v.frame[2], v.frame[3]);
    const bounds = [Math.max(2, bx0), Math.max(REGION_TOP + 2, by0), Math.min(vw - 2, bx1), Math.min(vh - 2, by1)];
    const at = Object.fromEntries(pts.map((p) => [p.id, scr(p.x, p.y)]));
    const fixed = pts.map((p) => [at[p.id][0] - z.hw, at[p.id][1] - z.hh, at[p.id][0] + z.hw, at[p.id][1] + z.hh]);
    const me = !st.journey && pts.find((p) => p.id === st.here);
    if (me) { const [X, Y] = at[me.id]; fixed.push([X + 10, Y - 40, X + 34, Y - 12], [X - 19, Y - 19, X + 19, Y + 19]); }
    // 你的朱圈（半徑 17、線寬 2.4）照圓的算：五塊疊成一個圓（第二輪的牆與「擠不下」都照它）
    const ring = me ? R_RING.map(([a, b]) => [at[me.id][0] - a, at[me.id][1] - b, at[me.id][0] + a, at[me.id][1] + b]) : [];
    const inter = (a, b) => { // 兩個框相交的面積（第二輪的位置多，這一段最常跑：不碰 Math）
      const w = (a[2] < b[2] ? a[2] : b[2]) - (a[0] > b[0] ? a[0] : b[0]);
      if (w <= 0) return 0;
      const h = (a[3] < b[3] ? a[3] : b[3]) - (a[1] > b[1] ? a[1] : b[1]);
      return h > 0 ? w * h : 0;
    };
    const outside = (r) => (r[2] - r[0]) * (r[3] - r[1]) - inter(r, bounds);
    const against = (rows, boxes) => rows.reduce((n, r) => n + boxes.reduce((m, b) => m + inter(r, b), 0) + 4 * outside(r), 0);
    const sizes = pts.map((p) => regionLabelSize(base, st, p, z));
    const lay = (spots, walls) => pts.map((p, i) => {
      const L = sizes[i], [X, Y] = at[p.id];
      const opts = spots(L, z).map(([dx, dy, rank], j) => {
        const l = X + dx, t = Y + dy, rows = [[l, t, l + L.w1, t + L.fh]];
        if (L.low) rows.push([l, t + L.fh, l + L.w2, t + L.H]);
        const bb = [l, t, l + L.W, t + L.H];
        // pad、bp：每一列、外框各往外撐 R_ROW_GAP（FB-651：跟別處的列比的時候用，兩列之間不到 R_ROW_GAP 就算壓到）
        return { l, t, rows, bb, pad: rows.map(rowGrow), bp: rowGrow(bb), cost: against(rows, walls), rank: rank === undefined ? j : rank };
      });
      return { p, i, L, X, Y, opts };
    });
    const meet = (a, b) => a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3]; // 兩個框的外框碰不碰得到（先擋掉遠的，省時間）
    // 兩處的名字框壓不壓：gapOn 時不同地點的兩列之間不到 R_ROW_GAP 也算（FB-651，spaced 那一下）
    let gapOn = false;
    const clash = (a, b) => (gapOn ? meet(a.bp, b.bb) && a.pad.some((r) => b.rows.some((q) => inter(r, q) > 0))
      : meet(a.bb, b.bb) && a.rows.some((r) => b.rows.some((q) => inter(r, q) > 0)));
    // 再一處一處往前挪——換成更前面（rank 小：離小圖更近）、不壓牆也不壓別人的位置，挪到挪不動為止
    const forward = (items, pick) => {
      for (let round = 0, moved = true; moved && round < 6; round++) {
        moved = false;
        for (const it of items) {
          const now = pick[it.i].rank;
          const better = it.opts.reduce((b, o) => (o.rank < now && (!b || o.rank < b.rank) && o.cost <= 0 && items.every((x) => x === it || !clash(o, pick[x.i])) ? o : b), null);
          if (better) { pick[it.i] = better; moved = true; }
        }
      }
      return pick;
    };
    // 一起找：每次挑剩下位置最少的先擺，擺不下回頭改前面的；試了 budget 次還沒找到回 null
    const solve = (items, budget) => {
      const free = items.map((it) => it.opts.filter((o) => o.cost <= 0));
      // 每一處所有位置合起來的外框：碰不到的那幾處不必一個一個比
      const reach = free.map((r) => r.reduce((b, o) => [Math.min(b[0], o.bb[0]), Math.min(b[1], o.bb[1]), Math.max(b[2], o.bb[2]), Math.max(b[3], o.bb[3])], [Infinity, Infinity, -Infinity, -Infinity]));
      const search = (todo, room) => {
        if (!todo.length) return {};
        const i = todo.reduce((a, z) => (room[z].length < room[a].length ? z : a));
        const rest = todo.filter((x) => x !== i);
        for (const o of room[i]) {
          if (--budget < 0) return null;
          const after = room.slice();
          if (rest.some((j) => meet(gapOn ? o.bp : o.bb, reach[j]) && !(after[j] = room[j].filter((q) => !clash(o, q))).length)) continue;
          const found = search(rest, after);
          if (found) return { ...found, [i]: o };
          if (budget < 0) return null;
        }
        return null;
      };
      const pick = free.every((r) => r.length) ? search(items.map((it) => it.i), free) : null;
      return pick && forward(items, pick);
    };
    // 一個一個擺（你那一處先、附近地點多的先），每一個挑壓得最少的；再反覆把壓到東西的那幾處之一換到壓得最少的位置（同分挑前面的；
    // 偶爾隨便換一格，免得來回打轉；種子固定，同樣的畫面擺出來一樣），記住壓得最少的那一次
    const settle = (items, steps) => {
      const pick = {};
      const over = (o, i) => items.reduce((n, x) => (x.i === i || !pick[x.i] || !meet(o.bb, pick[x.i].bb) ? n : n + o.rows.reduce((m, r) => m + pick[x.i].rows.reduce((k, q) => k + inter(r, q), 0), 0)), o.cost);
      const best = (it) => it.opts.reduce((b, o) => { const c = over(o, it.i); return c < b.c - 1e-6 ? { o, c } : b; }, { o: null, c: Infinity }).o;
      const crowd = (it) => items.filter((o) => o !== it && Math.hypot(o.X - it.X, o.Y - it.Y) < 110).length;
      const order = items.slice().sort((a, z) => (z.p === me) - (a.p === me) || crowd(z) - crowd(a) || (z.p.big ? 1 : 0) - (a.p.big ? 1 : 0) || a.i - z.i);
      for (const it of order) pick[it.i] = best(it);
      let seed = 20261021, keep = { ...pick }, low = Infinity;
      const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
      for (let step = 0; step <= steps; step++) {
        const hurt = items.filter((it) => over(pick[it.i], it.i) > 0);
        const total = hurt.reduce((n, it) => n + over(pick[it.i], it.i), 0);
        if (total < low - 1e-6) { low = total; keep = { ...pick }; }
        if (!hurt.length || step === steps) break;
        const it = hurt[Math.floor(rnd() * hurt.length)];
        pick[it.i] = rnd() < 0.1 ? it.opts[Math.floor(rnd() * it.opts.length)] : best(it);
      }
      return forward(items, keep);
    };
    // 鄰區出口（regionExits 在名字框擺好之後沿著邊滑開）：第一輪擺好之後還壓到名字框，就當作沒找到
    const exits = regionExitAnchors(base, rid, v, vw, vh), room = regionExitRoom(v, vw, vh);
    const exitHit = (items, pick) => regionExits(base, rid, v, vw, vh, items.map((it) => ({ X: it.X, Y: it.Y, rows: pick[it.i].rows })))
      .some((e) => items.some((it) => pick[it.i].rows.some((r) => inter(r, e.box) > 0.5)));
    // 名字框離自己的小圖多遠（小圖中心到印章框最近那一點）
    const hugOf = (it, o) => { const f = o.rows[0]; return Math.hypot(Math.max(f[0] - it.X, 0, it.X - f[2]), Math.max(f[1] - it.Y, 0, it.Y - f[3])); };
    // FB-651：照不相交擺好之後，再找一次「不同地點的兩列都隔得開 R_ROW_GAP」的擺法——每一處只准用離自己的小圖不比剛才遠 R_NEAR 的位置
    // （留空是寧可：不為了它把名字擺得離小圖更遠、不為了它縮字），找不到照剛才的
    const spaced = (items, pick, budget) => {
      gapOn = true;
      const lim = items.map((it) => ({ ...it, opts: it.opts.filter((o) => hugOf(it, o) <= hugOf(it, pick[it.i]) + R_NEAR) }));
      const got = solve(lim, budget);
      gapOn = false;
      return got && !(exits.length && exitHit(items, got)) ? got : pick;
    };
    gapOn = false;
    let items = lay(regionLabelSpots, fixed);
    let pick = solve(items, REGION_SEARCH);
    if (pick && exits.length && exitHit(items, pick)) pick = null;
    if (pick) pick = spaced(items, pick, REGION_SEARCH);
    else {
      // 第二輪：你的朱圈照圓的算（圓外那四個角讓名字框擺得進去），鄰區出口原本的位置也讓開
      items = lay(regionLabelSpotsWide, [...(me ? fixed.slice(0, -1) : fixed), ...ring, ...exits.map((e) => regionExitBox(e, 0, room))]);
      // 先照「離自己的小圖多近」的先後一起找（找得到名字就都在自己的小圖旁邊），找不到再照原本的先後找一次，再找不到才換位置
      const near = items.map((it) => ({ ...it, opts: it.opts.slice().sort((a, b) => a.rank - b.rank) }));
      pick = solve(near, R_SEARCH_WIDE) || solve(items, R_SEARCH_WIDE);
      pick = pick ? spaced(near, pick, R_SEARCH_WIDE) : settle(items, R_SETTLE);
    }
    const out = items.map((it) => {
      const o = pick[it.i], others = items.filter((x) => x !== it).map((x) => pick[x.i]);
      return { ...it.L, id: it.p.id, X: it.X, Y: it.Y, l: o.l, t: o.t, rows: o.rows,
        cost: against(o.rows, fixed) + others.reduce((n, q) => n + (clash(o, q) ? 1 : 0), 0) };
    });
    const exitBoxes = regionExits(base, rid, v, vw, vh, out).map((e) => e.box);
    regionLetterSeals(out, fixed.slice(0, pts.length), me ? fixed[pts.length] : null, me ? at[me.id] : null, exitBoxes, bounds);
    return [out, regionCrowded(out, fixed.slice(0, pts.length), me ? fixed[pts.length] : null, me ? at[me.id] : null, exitBoxes, bounds)];
  }
  // 「戰」字印擺在哪（輿圖第三版第 5 批，企劃者 2026-10-22 挑 A 乙：名字框旁一枚）：名字都擺好之後才找，不挪任何名字、不讓這一區縮字。
  // 照先後試：寶（或名字框）的右邊、左邊、框上面靠右、框上面靠左、意境字那一列的右邊、下面，再往上下錯開、四個斜角——第一個不碰任何一處的名字框與意境字、
  // 小圖、你的旗與朱圈、鄰區出口、別的「戰」字印，也沒出取景框的：先要四周留 R_ROW_GAP（同 FB-651 兩列之間），找不到再只留 R_LETTER_PAD，
  // 再找不到准碰自己的小圖；而且每一個空位都要離自己的名字框（印章框與意境字）比離任何別處的名字框近（FB-691：不然讀起來像別處下了戰書）。
  // 都不行才蓋在自己名字框的一角（fit 是假）。寫進那一處的 seal（螢幕上的 [左, 上, 右, 下]）與 sealFit
  function regionLetterSeals(labels, icons, flag, you, exits, bounds) {
    const inter = (a, b) => Math.max(0, Math.min(a[2], b[2]) - Math.max(a[0], b[0])) * Math.max(0, Math.min(a[3], b[3]) - Math.max(a[1], b[1]));
    const s = R_SEAL, g = R_SEAL_GAP, placed = [];
    const clean = (b, pad, own = null) => {
      const p = [b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad];
      if (p[0] < bounds[0] || p[1] < bounds[1] || p[2] > bounds[2] || p[3] > bounds[3]) return false;
      if (you && Math.hypot(Math.max(p[0] - you[0], 0, you[0] - p[2]), Math.max(p[1] - you[1], 0, you[1] - p[3])) < R_YOU) return false;
      return ![...labels.flatMap((l) => l.rows), ...icons.filter((q) => q !== own), ...(flag ? [flag] : []), ...exits, ...placed].some((q) => inter(p, q) > 0);
    };
    const dist = (a, b) => Math.hypot(Math.max(0, b[0] - a[2], a[0] - b[2]), Math.max(0, b[1] - a[3], a[1] - b[3]));
    const nearest = (b, rows) => rows.reduce((m, r) => Math.min(m, dist(b, r)), Infinity);
    labels.forEach((l, i) => {
      if (!l.letter) return;
      const others = labels.filter((m) => m !== l).flatMap((m) => m.rows);
      const mine = (b) => nearest(b, l.rows) < nearest(b, others); // FB-691：離自己比離別處近
      const [a0, a1, a2, a3] = l.rows[0], my = a1 + (l.fh - s) / 2, under = l.rows[1] ? l.rows[1][3] : a3, up = a1 - g - s;
      const spots = [[a2 + g, my], [a0 - g - s, my], [a2 - s, up], [a0, up], ...(l.rows[1] ? [[l.rows[1][2] + g, l.rows[1][1]]] : []),
        [a2 - s, under + g], [a0, under + g], [a2 + g, a1 - s / 2], [a2 + g, a3 - s / 2], [a0 - g - s, a1 - s / 2], [a0 - g - s, a3 - s / 2],
        [(a0 + a2 - s) / 2, up], [(a0 + a2 - s) / 2, under + g], [a2 + g, up], [a0 - g - s, up], [a2 + g, under + g], [a0 - g - s, under + g]];
      const boxes = spots.map(([x, y]) => [x, y, x + s, y + s]);
      // 第三輪：可以碰到自己的小圖（字印貼著自己那一處，還是「旁」）
      const hit = boxes.find((b) => mine(b) && clean(b, R_ROW_GAP)) || boxes.find((b) => mine(b) && clean(b, R_LETTER_PAD))
        || boxes.find((b) => mine(b) && clean(b, R_LETTER_PAD, icons[i]));
      // 都不行：蓋在自己名字框的一角（右上、左上、右下、左下），挑第一個離自己比離別處近的（蓋在框上，離自己是 0；別處的框也碰到就換一角）
      const corners = [[a2 - s * 0.55, a1 - s * 0.55], [a0 - s * 0.45, a1 - s * 0.55], [a2 - s * 0.55, a3 - s * 0.45], [a0 - s * 0.45, a3 - s * 0.45]]
        .map(([x, y]) => [x, y, x + s, y + s]);
      l.seal = hit || corners.find(mine) || corners[0];
      l.sealFit = !!hit;
      placed.push(l.seal);
    });
  }
  // 擠不下（FB-648 第二段乙）＝擺好的名字框 labels 還互壓：兩兩相交、壓到別處的小圖 icons（照地點順序）或你的旗 flag、碰到你的朱圈
  // （圓心 you；真的那一圈：圓心到框最近那一點不到外緣 R_YOU）、鄰區出口 exits（照 regionExits 滑好的位置；出口的框四周有留白，
  // 同測試的量法多過 2px² 才算），或出了 bounds（取景框與上面那一排底下）。沒有旗、朱圈（不在這一區、在路上）給 null
  function regionCrowded(labels, icons, flag, you, exits, bounds) {
    const inter = (a, b) => Math.max(0, Math.min(a[2], b[2]) - Math.max(a[0], b[0])) * Math.max(0, Math.min(a[3], b[3]) - Math.max(a[1], b[1]));
    const outside = (r) => (r[2] - r[0]) * (r[3] - r[1]) - inter(r, bounds);
    const ring = (r) => !!you && Math.hypot(Math.max(r[0] - you[0], 0, you[0] - r[2]), Math.max(r[1] - you[1], 0, you[1] - r[3])) < R_YOU;
    return labels.some((l, i) => l.rows.some((r) => outside(r) > 0.5 || ring(r) || (!!flag && inter(r, flag) > 0.5)
      || icons.some((b, j) => j !== i && inter(r, b) > 0.5) || exits.some((b) => inter(r, b) > 2)
      || labels.some((m, j) => j !== i && m.rows.some((q) => inter(r, q) > 0.5))));
  }
  // 墨筆小圖（草圖「一乙」的城、營、寺、渡、山、野；底圖給的 glyph）：線色＝誰佔著，底是紙色；20×20、中心在 (0, 0)
  function inkIcon(glyph, ink, paper) {
    const sw = `stroke="${ink}" stroke-width="1.5" fill="${paper}" stroke-linejoin="round"`;
    if (glyph === "城") return `<rect x="-10" y="-5" width="20" height="11" ${sw}/><path d="M-10 -5V-9H-6V-5M-3 -5V-9H3V-5M6 -5V-9H10V-5" ${sw}/><path d="M-3 6V1A3 3 0 0 1 3 1V6" fill="${ink}"/>`;
    if (glyph === "營") return `<path d="M-10 8L0 -8L10 8Z" ${sw}/><path d="M-3 8L0 2L3 8" fill="${ink}"/><path d="M0 -8V-15L7 -13L0 -10" fill="${ink}" stroke="${ink}" stroke-width="1"/>`;
    if (glyph === "寺") return `<path d="M-11 -1L0 -11L11 -1Z" ${sw}/><path d="M-7 -11L0 -17L7 -11Z" ${sw}/><rect x="-5" y="-1" width="10" height="8" ${sw}/>`;
    if (glyph === "渡") return `<path d="M-11 2Q0 11 11 2Z" ${sw}/><line x1="0" y1="2" x2="0" y2="-11" stroke="${ink}" stroke-width="1.4"/><path d="M0 -11L9 -5L0 -1Z" ${sw}/>`;
    if (glyph === "山") return `<path d="M-12 7L-5 -5L-1 1L4 -9L12 7Z" ${sw}/><path d="M4 -9l3 7" stroke="${ink}" stroke-width=".9"/>`;
    return `<path d="M-9 6V-1M-5 6V-5M-1 6V0M3 6V-5M7 6V-1" stroke="${ink}" stroke-width="1.5" fill="none" stroke-linecap="round"/><circle cx="-7" cy="-3" r="1.2" fill="${ink}"/>`;
  }
  // 沒人佔的框與小圖：照底圖的 unheld（劇本的沒人佔一色）往墨色、紙色調
  function noneInk(base) {
    const u = (base.world && base.world.unheld) || SIDE_UNKNOWN.soft;
    return { color: mixHex(u, MAP_INK, 0.42), tint: mixHex(u, MAP_HALO, 0.6) };
  }
  // 區圖的記號（純函式）：o = { v: regionFit 的取景, vw, vh: 地圖框, rid: 哪一區, wash: 塗層開著 }。回 [底下那一張, 上面那一張]
  // （同天下圖：會跳的圈、你、旗子畫在上面那一張 #mkt）
  function regionParts(base, st, o) {
    const v = o.v, k = 1 / v.s, rid = o.rid, pts = regionPlaces(base, rid), pos = Object.fromEntries(pts.map((p) => [p.id, p])), z = regionSizes(v.s);
    const mp = (X, Y) => [v.cx + (X - o.vw / 2) * k, v.cy + (Y - o.vh / 2) * k]; // 螢幕 → 地圖
    const [fx0, fy0, fx1, fy1] = v.frame, W = base.w || 900, H = base.h || 1340;
    const labels = regionLabels(base, st, rid, v, o.vw, o.vh), exits = regionExits(base, rid, v, o.vw, o.vh, labels);
    const none = noneInk(base), inkOf = (id) => (st.places[id] && st.places[id].control ? sideInk(st.places[id].control) : none);
    const out = [];
    if (o.wash) {
      out.push(`<defs><filter id="r-wash" x="-30%" y="-30%" width="160%" height="160%"><feTurbulence type="fractalNoise" baseFrequency="${f2(R_WASH.freq / k)}" numOctaves="2" seed="3" result="n"/><feDisplacementMap in="SourceGraphic" in2="n" scale="${f1(R_WASH.warp * k)}"/><feGaussianBlur stdDeviation="${f1(R_WASH.blur * k)}"/></filter></defs>`);
      const dots = pts.filter((p) => st.places[p.id] && st.places[p.id].control).map((p) => `<circle cx="${p.x}" cy="${p.y}" r="${f1(R_WASH.r * k)}" fill="${sideInk(st.places[p.id].control).soft}"/>`).join("");
      out.push(`<g class="r-wash-layer" filter="url(#r-wash)" opacity="${R_WASH.op}" pointer-events="none">${dots}</g>`);
    }
    // 點空白：收起卡（取景框一塊透明的點擊區，畫在記號最底下）
    out.push(`<rect data-act="region-blank" x="${f1(fx0)}" y="${f1(fy0)}" width="${f1(fx1 - fx0)}" height="${f1(fy1 - fy0)}" fill="#000000" fill-opacity="0"/>`);
    // 取景框外的紙：三層由內往外漸濃（邊緣不是一刀切）
    const ring = Array.from({ length: R_MASK }, (_, i) => {
      const g = i * R_MASK_STEP * k;
      return `<path d="M${-W},${-H}H${2 * W}V${2 * H}H${-W}ZM${f1(fx0 - g)},${f1(fy0 - g)}V${f1(fy1 + g)}H${f1(fx1 + g)}V${f1(fy0 - g)}Z" fill-rule="evenodd"/>`;
    }).join("");
    out.push(`<g class="r-mask" fill="${MAP_PAPER}" fill-opacity="${R_MASK_OP}" pointer-events="none">${ring}</g>`);
    // 鄰區出口
    for (const e of exits) {
      const [x, y] = mp(e.box[0], e.box[1]), w = (e.box[2] - e.box[0]) * k, h = (e.box[3] - e.box[1]) * k;
      out.push(`<g class="r-exit" data-act="region-go" data-id="${esc(e.to)}" style="cursor:pointer"><rect x="${f1(x)}" y="${f1(y)}" width="${f1(w)}" height="${f1(h)}" fill="#000000" fill-opacity="0"/>`
        + `<text x="${f1(x + 3 * k)}" y="${f1(y + (R_EXIT + 0.5) * k)}" font-size="${f1(R_EXIT * k)}" fill="#6B5A44" stroke="${MAP_HALO}" stroke-width="${f1(3 * k)}" paint-order="stroke" style="font-family:serif">${esc(e.text)}</text></g>`);
    }
    // 墨筆小圖（點擊區跟著小圖）
    for (const p of pts) {
      out.push(`<g class="r-icon" data-act="region-place" data-id="${esc(p.id)}" transform="translate(${p.x},${p.y}) scale(${f2(z.icon * k)})" style="cursor:pointer">`
        + `<rect x="-14" y="-14" width="28" height="28" fill="#000000" fill-opacity="0"/>${inkIcon(p.glyph, inkOf(p.id).color, MAP_HALO)}</g>`);
    }
    // 名字框：印章框（框色＝誰的）、框裡下緣的進度條（冷卻整條灰、不寫字）、名字、朱印寶、意境字
    for (const L of labels) {
      const p = pos[L.id], ink = inkOf(L.id), [x, y] = mp(L.l, L.t), fw = L.fw * k, fh = L.fh * k, line = L.big ? R_LINE_BIG : R_LINE;
      const parts = [`<g class="r-label" data-act="region-place" data-id="${esc(L.id)}" style="cursor:pointer;font-family:serif">`,
        `<rect class="r-frame" x="${f1(x)}" y="${f1(y)}" width="${f1(fw)}" height="${f1(fh)}" fill="${ink.tint}" fill-opacity=".95" stroke="${ink.color}" stroke-width="${f2(line * k)}"/>`];
      if (L.bar) { // 貼著框線內側：左右下各讓半條框線
        const i = (line / 2) * k, bx = x + i, bw = fw - 2 * i, bh = R_BAR * k, by = y + fh - i - bh;
        parts.push(`<rect class="r-bar" x="${f1(bx)}" y="${f1(by)}" width="${f1(bw)}" height="${f1(bh)}" fill="${L.cool ? COOL_GREY : BAR_TRACK}"/>`);
        if (!L.cool && L.tug) parts.push(`<rect class="r-bar-fill" data-side="${esc(L.tug.side)}" x="${f1(bx)}" y="${f1(by)}" width="${f1((bw * L.tug.pct) / 100)}" height="${f1(bh)}" fill="${sideInk(L.tug.side).color}"/>`);
      }
      parts.push(`<text x="${f1(x + R_PADX * k)}" y="${f1(y + (R_PADY + L.fs * 0.86) * k)}" font-size="${f1(L.fs * k)}" font-weight="${L.big ? 700 : 500}" fill="${MAP_INK}">${esc(p.name)}</text>`);
      if (L.rich) {
        const sx = x + fw + R_SEAL_GAP * k, sy = y + ((L.fh - R_SEAL) / 2) * k;
        parts.push(`<g class="r-seal"><rect x="${f1(sx)}" y="${f1(sy)}" width="${f1(R_SEAL * k)}" height="${f1(R_SEAL * k)}" rx="${f1(2 * k)}" fill="${RICH_SEAL}"/><text x="${f1(sx + (R_SEAL / 2) * k)}" y="${f1(sy + 11.3 * k)}" font-size="${f1(11 * k)}" text-anchor="middle" fill="#FFFFFF">${RICH_WORD}</text></g>`);
      }
      if (L.letter && L.seal) { // 戰書下了、還沒開集結：名字框旁一枚「戰」字印——紙底朱框朱字，跟實心的「寶」分得開（企劃者挑 A 乙）；
        // 位置是 regionLetterSeals 找的空位（多半在寶或名字框的右邊）
        const [sx, sy] = mp(L.seal[0], L.seal[1]);
        parts.push(`<g class="r-letter"><rect x="${f1(sx)}" y="${f1(sy)}" width="${f1(R_SEAL * k)}" height="${f1(R_SEAL * k)}" rx="${f1(2 * k)}" fill="${LETTER_SEAL_PAPER}" stroke="${FRONT_RED}" stroke-width="${f1(1.5 * k)}"/><text x="${f1(sx + (R_SEAL / 2) * k)}" y="${f1(sy + 11.3 * k)}" font-size="${f1(11 * k)}" text-anchor="middle" font-weight="700" fill="${FRONT_RED}">${LETTER_SEAL_WORD}</text></g>`);
      }
      if (L.fight) { // 攻城集結・交戰中：名字框外一圈紅、一閃一閃（借天下圖激戰的 .w-melee；企劃者挑 B 甲）。畫在印章框底下（框與字照舊清楚），
        // 圈的外緣離框 R_FIGHT_OUT＋半條線，落在 FB-651 那一圈 R_ROW_GAP 的留白裡
        const d = R_FIGHT_OUT * k;
        parts.splice(1, 0, `<rect class="r-fight w-melee" x="${f1(x - d)}" y="${f1(y - d)}" width="${f1(fw + 2 * d)}" height="${f1(fh + 2 * d)}" rx="${f1(2 * k)}" fill="${FRONT_RED}" fill-opacity=".16" stroke="${FRONT_RED}" stroke-width="${f1(R_FIGHT_LINE * k)}"/>`);
      }
      const base0 = y + fh + (R_INS_GAP + L.insPx * 0.9) * k;
      L.ins.forEach((ins, i) => parts.push(`<text class="r-ins" x="${f1(x + i * (L.insPx + 2) * k)}" y="${f1(base0)}" font-size="${f1(L.insPx * k)}" font-weight="700" fill="${ins.c}" stroke="${MAP_HALO}" stroke-width="${f1(2.6 * k)}" paint-order="stroke">${esc(ins.name)}</text>`));
      out.push(parts.join("") + "</g>");
    }
    // 上面那一張：你（朱圈與旗；在路上畫在路上，在取景框裡才畫）
    const high = [], j = st.journey, h = pos[st.here];
    const hx = j ? j.x : h && h.x, hy = j ? j.y : h && h.y;
    if (hx !== undefined && hx >= fx0 && hx <= fx1 && hy >= fy0 && hy <= fy1) {
      high.push(`<circle class="pulse" cx="${hx}" cy="${hy}" r="${f1(14 * k)}" fill="none" stroke="${FRONT_RED}" stroke-width="${f1(2.2 * k)}" pointer-events="none"/>`);
      high.push(j ? `<circle class="r-you" cx="${hx}" cy="${hy}" r="${f1(6 * k)}" fill="${FRONT_RED}" stroke="#FFFFFF" stroke-width="${f1(1.6 * k)}" pointer-events="none"/>`
        : `<circle class="r-you" cx="${hx}" cy="${hy}" r="${f1(17 * k)}" fill="none" stroke="${FRONT_RED}" stroke-width="${f1(2.4 * k)}" pointer-events="none"/>`);
      high.push(`<path d="M${f1(hx + 13 * k)} ${f1(hy - 13 * k)}V${f1(hy - 38 * k)}L${f1(hx + 31 * k)} ${f1(hy - 32 * k)}L${f1(hx + 13 * k)} ${f1(hy - 26 * k)}" fill="${FRONT_RED}" stroke="#7A1F18" stroke-width="${f1(1.2 * k)}" pointer-events="none"/>`);
    }
    return [out.join(""), high.join("")];
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
  // 從天下圖點一區、「進入此區」、找地點挑了一處、鄰區出口、上面那一排換一區：換到那一區的區圖。focus：挑的那一處（抽屜半開它的卡）；
  // 沒給而且你就在這一區：開你腳下這一處的卡（設計 5.1：拉開是你腳下這一處的卡）。進區圖回 1 倍（企劃者 2026-10-22）
  function enterRegion(rid, focus = null) {
    stopPlay();
    if (!rid || !S.mapBase || !regionPlaces(S.mapBase, rid).length) return;
    const st = S.mapState, mine = !focus && st && !st.journey && hereRegion() === rid ? st.here : null, sel = focus || mine;
    Object.assign(S, { mapLayer: "region", mapRegion: rid, mapMode: sel ? "place" : "overview", mapSel: sel, mapWeek: null, mapQuery: "", mapDrawer: sel ? "peek" : "min", mapPan: null, panFrom: null });
    applyMapView(true);
    remapChrome();
    drawMarks();
  }
  // 回天下圖（區圖上面那一排的「‹ 天下」、天下圖的「天下」）：回 1 倍（企劃者 2026-10-22）
  function toWorld() {
    stopPlay();
    Object.assign(S, { mapLayer: "world", mapMode: "overview", mapSel: null, mapWeek: null, mapQuery: "", mapDrawer: "min", mapPan: null, panFrom: null });
    remapChrome();
    applyMapView();
    drawMarks();
  }
  // 區圖上點了一處（小圖或名字框）：抽屜半開那一處的卡，地圖不動（設計 5.2）；點空白收回那一行
  function regionPick(id) {
    if (!id) {
      if (S.mapMode !== "place") return;
      Object.assign(S, { mapSel: null, mapMode: "overview" });
      setMapDrawer("min");
    } else {
      Object.assign(S, { mapSel: id, mapMode: "place", mapQuery: "" });
      if (S.mapDrawer === "min" || S.mapDrawer === "tl") setMapDrawer("peek");
    }
    redrawDrawer();
    drawSel();
  }
  const hereRegion = () => {
    const p = S.mapBase && S.mapState && placeOf(S.mapBase, S.mapState.here);
    return p ? p.region : null;
  };
  const regionOfPlace = (id) => {
    const p = id && S.mapBase && placeOf(S.mapBase, id);
    return p ? p.region : null;
  };

  // ── 底圖烤成一張圖（Joy 2026-10-18「輿圖滑動的時候還是很卡」）──
  // 底圖約 1,200 個 SVG 元素（山頭、樹、河）加一層絹紋雜訊濾鏡（feTurbulence）：打開輿圖之後把不會變的那些畫成一張點陣圖（<image>），
  // 只留會變的：底色那一塊（最前面的 rect）、大區（path[data-region]，drawMarks 照這一層換 fill、收州界）、字、路（.tx-roads：區圖照 CSS
  // 換成一種淡實線，輿圖第三版第 4 批）、記號。圖的解析度照螢幕（最多 3 倍、一千兩百萬像素）
  const BAKE_PX = 12e6;
  const baked = { key: null, url: null }; // 這一張底圖烤好的圖（同一張底圖整層重畫時不必再烤）
  let bakeTimer = 0;
  function bakeLater() {
    clearTimeout(bakeTimer);
    bakeTimer = setTimeout(bakeBase, 250);
  }
  // 要烤進圖裡的：最前面那一塊底色、大區、字、路、記號、defs 以外的
  function bakeable(svg) {
    const first = svg.querySelector(":scope > rect");
    return [...svg.children].filter((el) => {
      const t = el.tagName.toLowerCase(), cls = (el.getAttribute && el.getAttribute("class")) || "";
      return el !== first && t !== "defs" && t !== "text" && t !== "image" && el.id !== "mk" && !cls.includes("tx-roads") && !el.hasAttribute("data-region") && !(el.querySelector && el.querySelector("text"));
    });
  }
  async function bakeBase() {
    const wrap = document.getElementById("map");
    const svg = wrap && wrap.querySelector(".tx-world-map > svg");
    if (!svg || svg.dataset.baked || typeof Image === "undefined" || typeof Blob === "undefined" || !window.URL || !URL.createObjectURL) return;
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

  // ── 輿圖的取景：兩張圖的取景是固定的（設計第五章），每次照地圖框現在的大小重算（轉向、拉視窗、版圖變化把框縮到抽屜上面都跟著）；
  // 取景上面再疊一層拖與縮放（企劃者 2026-10-22，下面「輿圖的拖與縮放」那一段）──
  // 視圖 v = { s 倍率, cx, cy 視窗中心對著的地圖座標 }；地圖照原本的像素大小放在框裡，位移與倍率套在兩張 svg 的外框（.tx-world-map）上
  // （svg 根元素的 transform 一變，Chrome 要照新的倍率重排每一個 <text>）
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
  // 照這一層算取景、套到地圖上（連同拖縮）；glide：換層、換區時滑一下（≤150ms）。取景或地圖框變了才重畫記號（viewKey）。
  // 拖縮：同一個取景再套一次（切分頁回來、輿圖頁重畫）照留；同一層、同一區只換了地圖框的高（狀態列變高變矮，FB-710）帶過去
  // （panCarry：畫面上一個像素不動，照新的可見區夾一次；soft：手勢一開始才發現框換了，只准不再往外、不挪）；換層、換區、換寬回 1 倍
  function applyMapView(glide = false, g = mapGeom(document.getElementById("map")), soft = false) {
    if (!g || !S.mapBase) return;
    let v = null;
    if (S.mapLayer !== "world" || !S.mapBase.world) {
      if (!S.mapRegion || !regionPlaces(S.mapBase, S.mapRegion).length) S.mapRegion = hereRegion() || ((S.mapBase.regions || [])[0] || {}).id || null;
      const desk = deskMap();
      v = S.regionView = S.mapRegion ? regionFit(S.mapBase, S.mapRegion, g.vw, g.vh, REGION_TOP, desk ? 0 : REGION_PAD, desk ? 0 : REGION_CARD) : null;
    }
    if (!v && S.mapBase.world) {
      const tl = S.mapMode === "timeline", pad = deskMap() || tl ? 0 : WORLD_PAD, top = tl ? WORLD_TL_TOP : WORLD_TOP;
      v = S.worldView = worldFit(g.vw, g.vh, S.mapBase.world.frame, pad, top, g.W, g.H);
      v.area = worldArea(v, g.vw, g.vh, top, pad); // 大區名可以擺到哪（FB-631）
    }
    if (!v) return;
    clearTimeout(glideTimer);
    g.wrap.classList.toggle("glide", glide);
    if (glide) glideTimer = setTimeout(() => g.wrap.classList.remove("glide"), 200);
    const key = viewKey(v, g), was = S.panFrom;
    if (key !== S.panKey) {
      const same = !!was && was.layer === S.mapLayer && was.region === S.mapRegion && was.vw === g.vw && was.vh !== g.vh;
      Object.assign(S, { mapPan: same ? panCarry(panOf(), was, v, g.vw, g.vh, soft) : null, panKey: key });
    }
    S.panFrom = { layer: S.mapLayer, region: S.mapRegion, vw: g.vw, vh: g.vh, s: v.s, cx: v.cx, cy: v.cy };
    g.world.style.transform = mapTransform(v, g.vw, g.vh, panOf());
    if (key !== S.marksKey) scheduleMarks();
  }

  // ── 輿圖的拖與縮放（企劃者 2026-10-22「輿圖沒辦法拖曳移動了」「不順手」，選「兩張都能拖、能捏合縮放」；
  // 推翻設計第五章「不自由縮放」那一半，兩層照舊；計畫 docs/superpowers/plans/2026-10-22-輿圖拖曳縮放.md）──
  // 取景 v 上面疊一層螢幕座標的仿射 S.mapPan = { z, x, y }：螢幕上的點＝z ×（取景的螢幕座標）＋(x, y)。整張圖連字一起放大、移動：
  // 記號都畫在地圖座標裡、大小照取景的倍率反算（regionParts、worldParts），所以名字框、印章、進度條、戰字印、你的旗、出口的擺法
  // 不重算、記號不重畫（viewKey 不含 z）；拖縮中每一幀只換 .tx-world-map 的 transform，那一層掛著 will-change（合成層，不重畫），
  // 收尾才拿掉（照最後的倍率重畫一次，字是清楚的）。拖的時候不換游標、不在框上加 class（FB-322：游標會一路繼承、整棵重算樣式）。
  // 手機一指拖、兩指捏合；電腦滑鼠拖、滾輪（ctrl＋滾輪、觸控板捏合同）以游標為中心縮放；按下之後不到 PAN_SLOP 放開是點一下（照舊開卡），
  // 拖過、捏過放開的那一下 click 吃掉（不誤開卡）。1 倍（現在的取景）到 PAN_MAX，不准更小；夾邊（panBox、panClamp）
  const PAN_SLOP = 6; // 按下之後移過幾 px 才算拖
  const PAN_MAX = { world: 4, region: 3 }; // 最多放大幾倍（企劃者 2026-10-22：區圖約 3 倍、天下圖約 4 倍）
  const PAN_WHEEL = 0.0015; // 滾輪每 1px 的 deltaY 縮放多少（exp；一格約 100px 是 0.86 倍）
  const PAN_IDLE = 200; // 滾輪停多久算收尾（ms）
  const PAN_CLICK = 400; // 拖完放開之後，多久內落在地圖上的 click 吃掉（ms；下一次按下就作廢）
  const PAN_ONE = { z: 1, x: 0, y: 0 };
  const panOf = () => S.mapPan || PAN_ONE;
  const panMax = () => (S.mapLayer === "world" && S.mapBase && S.mapBase.world ? PAN_MAX.world : PAN_MAX.region);
  // 取景加上拖縮，寫成 .tx-world-map 的 transform（1 倍時跟固定取景的寫法一字不差）
  function mapTransform(v, vw, vh, p = PAN_ONE) {
    return `translate(${p.z * (vw / 2 - v.cx * v.s) + p.x}px, ${p.z * (vh / 2 - v.cy * v.s) + p.y}px) scale(${p.z * v.s})`;
  }
  // 夾邊用的兩個框（取景的螢幕座標 [x0, y0, x1, y1]）：b＝內容框（區圖：取景框 v.frame，這一區的地點與名字框都在裡面；天下圖：底圖的
  // world.frame），a＝露出來的那一塊（左右整個地圖框，上面讓開那一排，底下讓開抽屜此刻的高度；桌機右欄、版圖變化時地圖框本來就在抽屜外）
  function panBox(v, vw, vh) {
    const world = S.mapLayer === "world" && S.mapBase && S.mapBase.world, f = world ? S.mapBase.world.frame : v.frame;
    if (!f) return null;
    const [x0, y0, x1, y1] = world ? [f[0], f[1], f[0] + f[2], f[1] + f[3]] : f;
    const scr = (x, y) => [vw / 2 + (x - v.cx) * v.s, vh / 2 + (y - v.cy) * v.s];
    const tl = S.mapMode === "timeline", top = world ? (tl ? WORLD_TL_TOP : WORLD_TOP) : REGION_TOP;
    const bottom = deskMap() || tl ? 0 : mapDrawerPx(S.mapDrawer);
    return { b: [...scr(x0, y0), ...scr(x1, y1)], a: [0, top, vw, Math.max(top + 1, vh - bottom)] };
  }
  // 夾邊（企劃者「圖不能完全拖出框外」）：每一軸，內容框比露出來的那一塊大就要蓋滿它（拖到底，最邊上的地點剛好露在那一排底下、抽屜上面），
  // 比它小就不能出它——兩種都是位移夾在 a0 − z·b0 與 a1 − z·b1 之間。軟夾：from（上一幀）在它自己的倍率已經超出多少（例：天下圖 1 倍時
  // 取景框離上面那一排多留 8px，卡拉高之後照規則要貼齊）就照樣准超出多少，不硬跳回來、也不准再往外；縮回 1 倍時照新的倍率夾回框裡
  function panClamp(p, box, from = p) {
    if (!box || (p.z === 1 && !p.x && !p.y)) return p; // 1 倍的取景本身一定可以
    const lim = (t, t0, b0, b1, a0, a1) => {
      const lo = (z) => Math.min(a0 - z * b0, a1 - z * b1), hi = (z) => Math.max(a0 - z * b0, a1 - z * b1);
      const under = Math.max(0, lo(from.z) - t0), over = Math.max(0, t0 - hi(from.z));
      return Math.min(hi(p.z) + over, Math.max(lo(p.z) - under, t));
    };
    return { z: p.z, x: lim(p.x, from.x, box.b[0], box.b[2], box.a[0], box.a[2]), y: lim(p.y, from.y, box.b[1], box.b[3], box.a[1], box.a[3]) };
  }
  // 縮小時位移照倍率收回去（從 z0 縮到 z：位移乘 (z − 1)／(z0 − 1)），縮到 1 倍剛好回到現在的取景（像看照片：縮回最小就置中）；
  // 放大不收（手指、游標底下那一點不動）
  const panShrink = (q, z0) => (q.z < z0 && z0 > 1 ? { z: q.z, x: (q.x * (q.z - 1)) / (z0 - 1), y: (q.y * (q.z - 1)) / (z0 - 1) } : q);
  // 以地圖框裡 (px, py) 為中心縮放到 z（夾在 1～max）：那一點底下的地圖不動；縮到 1 倍（或更小）就是 1 倍的取景
  // （panCarry 帶過去的倍率可能比 max 多一點點：放大時不把它往下拉，免得一放大反而縮一下）
  function panZoom(p, z, px, py, max) {
    if (z <= 1) return PAN_ONE;
    const nz = Math.min(Math.max(max, p.z), z), f = nz / p.z;
    return panShrink({ z: nz, x: px - f * (px - p.x), y: py - f * (py - p.y) }, p.z);
  }
  // 地圖框換了高、取景照新的框重算（FB-710：狀態列變高變矮）：把拖縮帶過去——合起來的倍率與位移（畫面上的地圖）照舊，換算成新取景上的
  // z、x、y；新的取景比畫面上的還大（z 不到 1）就照新的框回 1 倍。再照新的可見區夾一次（soft：只准不再往外）。1 倍的取景本身
  // （寬度定倍率的區，取景不看框高）換算完還是 1 倍
  function panCarry(p, was, v, vw, vh, soft = false) {
    const Z = p.z * was.s, tx = p.z * (was.vw / 2 - was.cx * was.s) + p.x, ty = p.z * (was.vh / 2 - was.cy * was.s) + p.y;
    const z = Z / v.s;
    if (z < 1 - 1e-6) return null;
    let q = { z: Math.max(1, z), x: tx - z * (vw / 2 - v.cx * v.s), y: ty - z * (vh / 2 - v.cy * v.s) };
    q = panClamp(q, panBox(v, vw, vh), soft ? q : PAN_ONE);
    return Math.abs(q.z - 1) < 1e-6 && Math.abs(q.x) < 0.01 && Math.abs(q.y) < 0.01 ? null : q;
  }
  // 兩指：開始時（start：拖縮、中點、兩指距離）中點底下的那一點，跟著現在的中點走；倍率照兩指距離的比
  function panPinch(start, mx, my, d, max) {
    const p = start.p, z = Math.min(Math.max(max, p.z), (p.z * d) / start.d);
    if (z <= 1) return PAN_ONE;
    return panShrink({ z, x: mx - (z * (start.mx - p.x)) / p.z, y: my - (z * (start.my - p.y)) / p.z }, p.z);
  }
  // 手勢的狀態：按著的指標（id → [clientX, clientY]）、起點、拖過了沒、排好的那一幀、這一次手勢量好的地圖框與夾邊的框、滾輪、吃掉 click 的期限
  const pan = { pts: new Map(), start: null, moved: false, frame: 0, next: null, g: null, box: null, wheel: false, wheelTimer: 0, eatUntil: 0 };
  // 量好這一次手勢要用的地圖框（按下、滾輪第一下量一次：每一幀量會逼瀏覽器先排版）
  function panMeasure() {
    const g = mapGeom(document.getElementById("map")), f = S.panFrom;
    // 地圖框換了大小、取景還沒重套（FB-710 的保險：不經 renderTop 的路也一樣）：先照新的框帶過去，這一次手勢不跳、也不挪
    if (g && f && (f.vw !== g.vw || f.vh !== g.vh)) applyMapView(false, g, true);
    const v = curView();
    pan.g = g && v ? g : null;
    pan.box = g && v ? panBox(v, g.vw, g.vh) : null;
    return pan.g;
  }
  // 指標數變了（按下、放開一指）：從現在的位置與拖縮重新記起點。一指記上一幀的位置；兩指記開始時的拖縮、中點、兩指距離
  function panBase() {
    const pts = [...pan.pts.values()], g = pan.g;
    pan.start = null;
    if (!g || !pts.length) return;
    if (pts.length === 1) { pan.start = { at: pts[0] }; return; }
    const [[ax, ay], [bx, by]] = pts;
    pan.start = { p: panOf(), mx: (ax + bx) / 2 - g.x0, my: (ay + by) / 2 - g.y0, d: Math.max(1, Math.hypot(bx - ax, by - ay)) };
  }
  // 開始動了（拖過 PAN_SLOP、第二指按下、滾輪第一下）：那一層掛 will-change（之後每一幀只動合成層）、換層的滑動停掉；
  // 拖的指標這時才抓住（按下就抓的話，Chrome 會把 click 送到抓住的地圖框，點一下就點不到地點）
  function panBegin() {
    pan.moved = true;
    const g = pan.g;
    if (!g) return;
    for (const id of pan.pts.keys()) { try { g.wrap.setPointerCapture(id); } catch (e) { /* 合成的事件、已經放開的指標抓不住 */ } }
    clearTimeout(glideTimer);
    if (g.wrap.classList.contains("glide")) g.wrap.classList.remove("glide");
    g.world.style.willChange = "transform";
  }
  // 收尾：拿掉 will-change（照最後的倍率重畫一次）
  function panFinish() {
    if (pan.frame) { cancelAnimationFrame(pan.frame); panFrame(); }
    if (pan.g) pan.g.world.style.willChange = "";
    Object.assign(pan, { start: null, g: null, box: null, next: null, wheel: false });
  }
  // 一幀套一次（同一幀的多次移動合併）：滾輪給的是算好的拖縮（pan.next），指標照最新的位置算
  function panFrame() {
    pan.frame = 0;
    let p = pan.next;
    pan.next = null;
    const pts = [...pan.pts.values()], st = pan.start, cur = panOf();
    if (!p && st && pan.moved && pan.g) {
      if (pts.length === 1 && st.at) {
        p = { z: cur.z, x: cur.x + pts[0][0] - st.at[0], y: cur.y + pts[0][1] - st.at[1] };
        st.at = pts[0];
      } else if (pts.length === 2 && st.d) {
        const [[ax, ay], [bx, by]] = pts;
        p = panPinch(st, (ax + bx) / 2 - pan.g.x0, (ay + by) / 2 - pan.g.y0, Math.hypot(bx - ax, by - ay), panMax());
      }
      if (p) p = panClamp(p, pan.box, cur);
    }
    if (p) panSet(p);
  }
  const panSoon = () => { if (!pan.frame) pan.frame = requestAnimationFrame(panFrame); };
  // 套上一個拖縮：只寫 transform（記號、擺字都不動）
  function panSet(p) {
    S.mapPan = p.z === 1 && !p.x && !p.y ? null : p;
    const g = pan.g || mapGeom(document.getElementById("map")), v = curView();
    if (g && v) g.world.style.transform = mapTransform(v, g.vw, g.vh, panOf());
  }
  // 回 1 倍（天下圖已經在總覽時再按「天下」）：滑一下
  function panReset() {
    Object.assign(S, { mapPan: null, panFrom: null });
    applyMapView(true);
  }
  function panDown(ev) {
    if ((ev.pointerType === "mouse" && ev.button !== 0) || !S.mapBase || !curView()) return; // 滑鼠只收左鍵
    if (pan.pts.has(ev.pointerId)) { pan.pts.clear(); panFinish(); } // 同一個指標又按下：上一次沒收到放開（在視窗外放開），重新來過
    if (pan.pts.size >= 2) return; // 第三指不管
    pan.eatUntil = 0; // 新的一次按下：上一次拖完沒送出的 click 不再等
    if (pan.wheel) { clearTimeout(pan.wheelTimer); panFinish(); }
    if (!pan.pts.size) { pan.moved = false; panMeasure(); }
    if (pan.frame) { cancelAnimationFrame(pan.frame); panFrame(); }
    pan.pts.set(ev.pointerId, [ev.clientX, ev.clientY]);
    panBase();
    if (pan.pts.size === 2 && !pan.moved) panBegin(); // 第二指按下就是捏合：不再算點一下
    else if (pan.pts.size === 2) { try { pan.g && pan.g.wrap.setPointerCapture(ev.pointerId); } catch (e) { /* 抓不住照樣收得到 */ } }
  }
  function panMove(ev) {
    if (!pan.pts.has(ev.pointerId)) return;
    pan.pts.set(ev.pointerId, [ev.clientX, ev.clientY]);
    if (!pan.moved) {
      const at = pan.start && pan.start.at;
      if (!at || Math.hypot(ev.clientX - at[0], ev.clientY - at[1]) <= PAN_SLOP) return; // 還不到：可能是點一下
      panBegin();
    }
    panSoon();
  }
  function panUp(ev) {
    if (!pan.pts.has(ev.pointerId)) return;
    if (pan.frame) { cancelAnimationFrame(pan.frame); panFrame(); } // 還沒套的那一幀先套上
    pan.pts.delete(ev.pointerId);
    if (pan.pts.size) { panBase(); return; } // 雙指放開一指：剩下那一指接著拖
    if (pan.moved && ev.type === "pointerup") pan.eatUntil = Date.now() + PAN_CLICK; // 拖過、捏過：放開那一下的 click 不開卡
    panFinish();
  }
  // 滾輪以游標為中心縮放；觸控板雙指捏合在 Chrome／Edge 是帶 ctrlKey 的 wheel，一樣處理（也因此擋掉瀏覽器自己的整頁放大）
  function panWheel(ev) {
    if (ev.preventDefault) ev.preventDefault();
    if (pan.pts.size || !S.mapBase || !curView()) return; // 手指按著時不收
    if (!pan.wheel) {
      if (!panMeasure()) return;
      pan.wheel = true;
      panBegin();
    }
    clearTimeout(pan.wheelTimer);
    pan.wheelTimer = setTimeout(() => { pan.moved = false; panFinish(); }, PAN_IDLE);
    const g = pan.g, cur = pan.next || panOf();
    const dy = ev.deltaY * (ev.deltaMode === 1 ? 16 : ev.deltaMode === 2 ? g.vh : 1);
    pan.next = panClamp(panZoom(cur, cur.z * Math.exp(-dy * PAN_WHEEL), ev.clientX - g.x0, ev.clientY - g.y0, panMax()), pan.box, cur);
    panSoon();
  }
  // 拖過、捏過放開的那一下 click（捕獲階段、在 document 分派之前）吃掉：不誤開卡、不誤進一區
  function panEat(ev) {
    if (!pan.eatUntil) return;
    const late = Date.now() > pan.eatUntil;
    pan.eatUntil = 0;
    if (late) return;
    ev.stopPropagation();
    if (ev.preventDefault) ev.preventDefault();
  }
  // 地圖框的監聽：掛一次（地圖框常駐 FB-324；底圖換了整層重畫才是新的框）
  const panWired = new WeakSet();
  function panWire(wrap) {
    if (!wrap || !wrap.addEventListener || panWired.has(wrap)) return;
    panWired.add(wrap);
    wrap.addEventListener("pointerdown", panDown);
    wrap.addEventListener("pointermove", panMove);
    wrap.addEventListener("pointerup", panUp);
    wrap.addEventListener("pointercancel", panUp);
    wrap.addEventListener("wheel", panWheel, { passive: false });
    wrap.addEventListener("click", panEat, true);
    // 舊版 iOS Safari 的捏合（新的瀏覽器由 touch-action: none 擋）、拖到地圖上的字開始原生拖曳，都擋掉
    for (const t of ["gesturestart", "gesturechange", "dragstart"]) wrap.addEventListener(t, (ev) => ev.preventDefault());
  }

  // 輿圖頁每次畫好（afterPage）：區圖的那一區（江湖頁小地圖點進來的、上次停的）、取景、抽屜、記號
  function mapReady() {
    const wrap = document.getElementById("map");
    if (!wrap) return;
    mapFrame();
    // 天下圖的總覽只有收著那一行與拉開的卡
    if (S.mapLayer === "world" && S.mapMode === "overview" && !["min", "half", "full"].includes(S.mapDrawer)) S.mapDrawer = "min";
    if (S.mapLayer !== "world" && S.mapSel && regionOfPlace(S.mapSel)) S.mapRegion = regionOfPlace(S.mapSel); // 江湖頁的小地圖點了某一處（設計第八節）
    applyMapView(false); // 先算區圖的取景：卡半開多高照它（peekPx）
    setMapDrawer(S.mapDrawer);
    drawMarks();
    bakeLater();
    drawerGrab();
    panWire(wrap); // 拖與縮放（企劃者 2026-10-22）
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
      <div class="train"><div class="tr-meter"><div class="tr-lv"><b>第${level}成</b>${typeof a.score === "number" ? `<span class="score">評 ${a.score}</span>` : ""}</div>
        <div class="ten">${Array.from({ length: 10 }, (_, k) => `<i${k < level ? ' class="on"' : ""}></i>`).join("")}</div></div></div>
      <div class="lvline"><span>${esc(a.kind)}${a.attribute ? `・屬${esc(a.attribute)}` : ""}・收${esc(a.affinity || "")}</span></div>
      ${slotsHtml(a, null, true)}
      <div class="art-card">${tenCells(a.card)}</div>
    </div>`;
  }
  function boardGearHtml(g) {
    const bits = [g.what, `屬${g.attribute}`, g.grade, g.tempers ? `淬煉 ${g.tempers | 0}/${g.temper_max | 0}` : "", g.edge != null && g.wear_word ? `${g.wear_word} ${g.edge | 0}` : ""];
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
      else if (S.reportOpen && r.selected != null) body = `<button class="linkish back" data-act="report-list">‹ 全部戰報</button><div class="card report-detail">${gaugeHtml(r.gauge)}${trailMoves(roundBlocks(r.detail, r.gauge, r.selected))}</div>`;
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

  // 易名帖（萬寶閣；Joy 2026-10-21 當場生效）：手上有帖（main.mall.rename）才畫一格：輸入新名號 →「改名」先問一次（S.renameAsk）→ 確定才送
  function renameRow() {
    const n = S.main && S.main.mall && S.main.mall.rename;
    if (!n) return "";
    if (S.renameAsk) {
      return `<div class="rename-row card"><p>從此改名「${esc(S.renameAsk)}」？用掉一張易名帖，當場生效；江湖史會記一行。</p>
        <div class="row"><button class="btn small primary" data-act="rename-go">確定改名</button><button class="btn small ghost" data-act="rename-back">再想想</button></div></div>`;
    }
    return `<div class="rename-row card"><p>易名帖 ${n | 0} 張：改你的名號，當場生效。</p>
      <div class="row"><input class="input" id="rename-name" maxlength="16" placeholder="新的名號" autocomplete="off"><button class="btn small" data-act="rename-ask">改名</button></div></div>`;
  }

  async function renameGo() {
    const name = S.renameAsk;
    S.renameAsk = null;
    await busy(async () => {
      const r = await api("/api/mall/rename", { name });
      if (r.main) applyMain(r.main);
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      if (text) toast(text);
      render();
    });
  }

  // 管理者「每週的事」那一行在 7 天濃縮季的寫法（軍令每天、第 4 階席次每段；FB-501，待 joy 潤）
  const ADMIN_DAILY_WEEK7 = "每天、每段的事（照 00:00 的做法立刻再做一次；之後照常）";
  // 21 天季：軍令每天、第 4 階席次照舊每週一（FB-502，待 joy 潤）
  const ADMIN_DAILY_SEASON21 = "每天、每週的事（軍令照 00:00、席次照週一的做法立刻再做一次；之後照常）";
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
        ${renameRow()}
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
                <p class="muted">${wk7() ? ADMIN_DAILY_WEEK7 : ordersDaily() ? ADMIN_DAILY_SEASON21 : "每週的事（照週一的做法立刻再做一次；下週一照常）"}</p>
                <div class="row wrap"><button class="btn small" data-act="admin" data-op="issue_orders">立刻發${wkWord("order_this", "本週")}軍令</button><button class="btn small" data-act="admin" data-op="rotate_seats">立刻輪替第 4 階席次</button></div>` : ""}
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
              ${a.conquest ? conquestAdminHtml(a.conquest) : ""}
              ${a.seal ? sealAdminHtml(a.seal) : ""}
              ${a.mingtie && a.mingtie.length ? mingtieAdminHtml(a.mingtie) : ""}
              <p class="muted">重設密碼（朋友忘記密碼時用；臨時密碼私下告訴他）</p>
              <form id="reset-form"><div class="row"><input class="input" name="target" placeholder="帳號或名號"><input class="input" name="temp" placeholder="臨時密碼"><button class="btn small" type="submit">重設</button></div><p class="form-msg" role="alert"></p></form>` : ""}
            ${S.main.mall ? mallAdminHtml() : ""}
          </section>` : ""}
      </div>`;
  }

  // 管理者區「商城」一組（商城架構設計 4.7；計畫第二節第 5 條：設定頁的表單放第二批）：查帳、補發、扣回、退一筆。商城開著（main.mall）才畫，
  // 不靠 /api/admin 那一份（那一份沒拿到也查得了帳）。原因必填，每一筆寫進帳（誰、何時、為什麼）；按了照舊先問一次，結果寫在查帳那一行、
  // 抽屜不關，做完重查一次那個人的帳。補發、扣回的編號在問的那一刻產（同一個確認框重送不會記兩次）。字待 joy 潤
  const MALL_NEED_NOTE = "先填原因：每一筆都會記進帳。"; // 待 joy 潤
  function mallAdminHtml() {
    const r = S.adMall;
    return `<p class="muted">商城（元寶的帳；補發、扣回、退一筆都要寫原因，每一筆都記進帳）</p>
      <form id="ad-mall-form"><div class="row"><input class="input" id="ad-mall-name" name="name" placeholder="名號或帳號" aria-label="商城查帳的名號或帳號" value="${esc(S.adMallName || "")}"><button class="btn small" type="submit">查帳</button></div><p class="form-msg${S.adMallMsg && S.adMallOk ? " ok" : ""}" role="alert">${esc(S.adMallMsg || (r && r.refusal) || "")}</p></form>
      <div class="row ad-row"><span class="ad-tag">元寶</span><input class="input" id="ad-mall-amount" type="number" min="1" step="1" value="100" aria-label="元寶數" style="max-width:96px"><input class="input" id="ad-mall-note" placeholder="原因（必填）" aria-label="原因" maxlength="100" value="${esc(S.adMallNote || "")}"></div>
      <div class="row wrap"><button class="btn small" data-act="mall-admin" data-op="mall_reissue">補發</button><button class="btn warn small" data-act="mall-admin" data-op="mall_revoke">扣回</button></div>
      ${r && !r.refusal ? mallBookHtml(r) : ""}`;
  }

  // 查到的那個人的帳：餘額與月卡、購買（沒退的一筆一顆「退這一筆」）、帳（新的在前；寫原因與經手的管理者）
  function mallBookHtml(r) {
    const buy = (x) => `<div class="mall-ad-buy"><span class="muted">#${x.id | 0}・${esc(x.time)}</span><span>${esc(x.item)}・${x.price | 0} 元寶</span>${x.refunded
      ? '<span class="muted">已退</span>' : `<button class="btn small" data-act="mall-admin" data-op="mall_refund" data-id="${x.id | 0}">退這一筆</button>`}</div>`;
    const line = (x) => `<li>${esc(x.time)} ${esc(x.reason)}${x.item ? `「${esc(x.item)}」` : ""} <b>${x.delta > 0 ? "+" : "−"}${Math.abs(x.delta | 0)}</b>（餘 ${x.balance | 0}）${
      x.note ? `・${esc(x.note)}` : ""}${x.admin ? `・經手 ${esc(x.admin)}` : ""}</li>`;
    return `<div class="mall-ad"><p><b>${esc(r.name)}</b>：元寶 ${r.balance | 0}${r.card ? `・月卡到 ${esc(r.card.until)}` : ""}</p>
      ${r.purchases.length ? `<p class="muted">購買（新的在前）</p>${r.purchases.map(buy).join("")}` : ""}
      ${r.ledger.length ? `<p class="muted">帳（新的在前）</p><ol class="mall-ad-log">${r.ledger.map(line).join("")}</ol>` : ""}</div>`;
  }

  function mallAdminAsk(op, id) {
    const val = (k) => String((document.getElementById(k) || {}).value || "").trim();
    const note = val("ad-mall-note");
    S.adMallNote = note;
    const say = (text) => {
      S.adMallMsg = text;
      S.adMallOk = false;
      const form = document.getElementById("ad-mall-form");
      if (form) formMsg(form, text);
    };
    if (op === "mall_refund") {
      const r = S.adMall, x = r && (r.purchases || []).find((p) => String(p.id) === String(id));
      if (!x) return;
      if (!note) { say(MALL_NEED_NOTE); return; }
      const body = { name: r.name, id: x.id | 0, note };
      ask(`退${r.name}的「${x.item}」（#${x.id | 0}）：元寶 +${x.price | 0} 全退；回體丹收回手上還有的、用掉的不追；月卡扣回那一張的天數。寫進帳（原因：${note}），確定？`,
        "確定退這一筆", () => mallAdminDo(op, body));
      return;
    }
    const name = val("ad-mall-name"), amount = Math.floor(Number(val("ad-mall-amount")));
    if (!name) { say("先填名號或帳號。"); return; }
    if (!(amount >= 1)) { say("元寶要寫正整數。"); return; }
    if (!note) { say(MALL_NEED_NOTE); return; }
    const body = { name, amount, note, ref: mallRef() };
    const reissue = op === "mall_reissue";
    ask(reissue ? `替${name}補發 ${amount} 元寶（原因：${note}），寫進帳，確定？` : `從${name}扣回 ${amount} 元寶（原因：${note}；餘額不能扣成負的），寫進帳，確定？`,
      reissue ? "確定補發" : "確定扣回", () => mallAdminDo(op, body));
  }

  async function mallAdminDo(op, body) {
    await busy(async () => {
      const r = await api(`/api/do/${op}`, body);
      if (r.main) setMain(r.main);
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      S.adMallMsg = text || "已完成。";
      S.adMallOk = !text.startsWith("（"); // 被拒的那一句都包在括號裡（見 tianxia/mall.py）；成了的帶 ok、不是紅字（FB-492）
      if (S.adMallOk) S.adMallNote = ""; // 成了：原因欄清掉，免得同一句誤送第二次
      S.adMallName = body.name;
      S.adMall = await api("/api/admin/mall", { name: body.name }); // 補完、退完重查一次那個人的帳
      renderKeepingSheet();
    });
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

  // 管理者「領地爭奪」一組（打開領地爭奪，PM 2026-10-22；admin_choices.conquest，領地爭奪關著、季收了是 null，不畫）：一塊定給哪一軍或放回中立、
  // 定一軍在那一塊的進度（到 100 照推滿當場易手）、立刻替一軍下戰書、取消一場攻城。照 Game.admin_conquest_* 實際做的事；按了照舊先問一次。字待 joy 潤
  function conquestAdminHtml(q) {
    const opts = (list) => list.map((x) => `<option value="${esc(x.id)}">${esc(x.label)}</option>`).join("");
    return `<p class="muted">領地爭奪（救場；易手的天下大事照自然發生寫，不寫管理者）</p>
      <div class="row ad-row"><span class="ad-tag">區塊</span><select class="input" id="ad-cq-block" aria-label="區塊">${opts(q.blocks)}</select></div>
      <div class="row ad-row"><span class="ad-tag">陣營</span><select class="input" id="ad-cq-side" aria-label="陣營">${opts(q.sides)}</select><button class="btn small" data-act="admin" data-op="conquest_set">定歸這一邊</button><button class="btn small" data-act="admin" data-op="conquest_set" data-neutral="1">放回中立</button></div>
      <div class="row ad-row"><span class="ad-tag">進度</span><input class="input" id="ad-cq-value" type="number" value="60" min="0" max="100" aria-label="進度" style="max-width:76px"><button class="btn small" data-act="admin" data-op="conquest_progress">定進度</button><button class="btn small" data-act="admin" data-op="admin_conquest_letter">立刻下戰書</button></div>
      ${q.sieges.length ? `<div class="row ad-row"><span class="ad-tag">攻城</span><select class="input" id="ad-cq-siege" aria-label="攻城">${opts(q.sieges)}</select><button class="btn warn small" data-act="admin" data-op="conquest_cancel">⚠ 取消這一場</button></div>` : ""}`;
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
    // 季長與對回什麼照季寫（S.admin.realign，同 world.realign_line；FB-501：7 天的季「對回現實的日子」），沒給照 21 天季那一句
    const R = (S.admin && S.admin.realign) || { days: "21", unit: "星期" };
    const RESUME_21 = `讓賽季時鐘繼續走：${R.days} 天的季的季曆對回現實的${R.unit}，暫停期間的大事在這一刻一起發生，季末照原本的日期；排好的決戰照原本的時間開，時間在暫停裡過了的馬上開始集結，確定？`;
    // 三場大戲與季末的預設時間：7 天濃縮季照時刻表寫（S.admin.default_dates，timetable.default_dates_note；FB-501），其他季照原本那一句
    const DATES = (S.admin && S.admin.default_dates) || "預設在第 6、9、11 週中、第 12 週末";
    const week7 = wk7(), daily = ordersDaily(); // 7 天濃縮季：第 4 階席次每段（FB-501）；21 天季、7 天季：軍令每天一道（FB-502）
    return {
      open_season: [`開季：賽季從籌備中正式開始，全服玩家都能行動了。記得排三場大戲與季末的時間（${DATES}），確定？`, "確定開季"],
      // 照 Game.admin_end_season 實際做的事寫（只在進行中有效）
      end_season: ["立刻收季：這一季馬上結束、算出結局與武學榜，全服進入休季（之後再按「開啟下一季」）；沒打完的決戰直接收掉、不算結果，確定？", "確定收季"],
      // 照 SqliteWorldStore.next_season 實際做的事寫（只在休季有效）
      next_season: [`開啟下一季（休季才有效）：新的一季立刻開始，同伴全部重獲自由、武學與意境的名字全部釋出（絕學定的名也是）、合成與合併的配方清空、鐵匠鋪的隱藏鑄法換一批、鑄譜與神器重來（神器譜留著）、天機 +1，沒打完的決戰清掉。${
        S.admin && S.admin.next_has_timetable ? `記得排三場大戲與季末的時間（${DATES}）。` : ""}確定？`, "確定開啟下一季"],  // FB-050
      fast_forward: [`時間快轉現實 ${body.hours} 小時的份（全服一起，季曆會跳得更多），確定？`, `快轉 ${body.hours} 小時`],
      // 公告停機時賽季時鐘暫停（Game.admin_pause_clock／admin_resume_clock）；問句待 S1／joy 潤
      // 21 天季（S.admin.season21）多一句、繼續換一句（PM 2026-10-19：季曆對回現實的星期，跟 world.RESUME_SKIP_REAL 一致）；待 joy 潤
      pause_clock: [`暫停賽季時鐘（停機維護前按）：季的時間不走、決戰不推，全服暫時不能行動，畫面照常可看；${
        S.admin && S.admin.season21 ? `${R.days} 天的季：繼續時季曆會對回現實的${R.unit}，暫停期間的大事在繼續那一刻一起發生。` : ""}做完記得按「繼續」，確定？`, "確定暫停"],
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
      issue_orders: [daily // 軍令每天一道的季（21 天、7 天；FB-501、FB-502，待 joy 潤）
        ? "立刻發今日軍令：今天還沒達成的軍令照 00:00 的做法重挑、換掉（它們的進度不算了），各陣營發一則軍情；已經達成的照舊留著、不會再達成一次；明天 00:00 照常發令，確定？"
        : "立刻發本週軍令：這一週還沒達成的軍令照週一的做法重挑、換掉（它們的進度不算了），各陣營發一則軍情；已經達成的照舊留著、不會再達成一次；下週一照常發令，確定？", "確定重發"],
      rotate_seats: [week7 // 7 天濃縮季的席次每段輪替（FB-501，待 joy 潤）
        ? "立刻輪替第 4 階席次：照上一段的貢獻重排各陣營在任的人、發一則名單軍情；下一段第一天 00:00 照常再排，確定？"
        : "立刻輪替第 4 階席次：照上一週的貢獻重排各陣營在任的人、發一則名單軍情；下週一照常再排，確定？", "確定輪替"],
      // 照 Game.admin_xingshi_now 實際做的事寫（領地爭奪第三批 A；待 joy 潤）
      xingshi_now: ["現在就開一篇〈天下形勢〉：照上一篇以來的事開一張單，伺服器在背景請模型寫（寫不出來照固定段），收下那一刻發一則天下大事、記一筆江湖史；還在等的那一篇先照固定段收。每天 22:00 照常再開，確定？", "確定開一篇"],
      start_showdown: [`立刻開「${body.title}」：照時刻表開集結（起點照此刻的戰況），這一場算開過了，排定的時間到了不會再開，確定？`, "確定開戰"],
      // 領地爭奪救場（打開領地爭奪，PM 2026-10-22；照 Game.admin_conquest_set／progress／letter／cancel 實際做的事寫，待 joy 潤）
      conquest_set: body.side
        ? [`把「${body.place}」定給${body.sideName}：天下大事照易手寫一句（落入／收復）、記一筆江湖史，三條戰線當場重算；不分紅、不起冷卻，${body.sideName}在那裡的進度拿掉、別一邊的照留，確定？`, "確定定歸"]
        : [`把「${body.place}」放回中立（沒人佔）：不發天下大事，三條戰線當場重算，進度照留，確定？`, "確定放回中立"],
      conquest_progress: [`把「${body.place}」${body.sideName}那一條進度定成 ${body.value}：到 100 照推滿當場易手（這一輪推過的人分紅、冷卻起算、天下大事一句），定成 0 就拿掉那一條；不看推不推得動、不記是誰推的，確定？`, "確定定進度"],
      admin_conquest_letter: [`替${body.sideName}立刻對「${body.place}」下一張戰書：不看第 4 階、門檻與一天一張，集結馬上開、集結完就開打，那一塊凍結到打完或作罷；天下大事照戰書寫、不寫管理者，確定？`, "確定下戰書"],
      conquest_cancel: [`取消「${picked("ad-cq-siege")}」這一場攻城：照作罷處理，那一塊解凍、進度照留，天下大事一句（不寫管理者）；已經開了集結的照決戰的取消收兵（不算勝負、不發軍餉、不易手），確定？`, "確定取消"],
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
          // 天命之爭的時刻：7 天濃縮季照時刻表寫（S.admin.mandate_at，timetable.mandate_note；FB-503），其他季照原本那一句
          ? `這一季立刻蓋上天命之季的章：還沒打的標了璽動的決戰必定牽動碎片、不提前收季，天命之爭排在${(S.admin && S.admin.mandate_at) || "第 12 週週一 20:00"}（現實時間落在半夜會盡量挪開，前後的大事擋著挪不開就照原時間、蓋完會說；已經過了就馬上開集結）。這一季的章蓋了就收不回：收季之後再換季，七片全部散去、每一位持有者都失去碎片，確定？`
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
    S.forgeResult = null; // 上一爐的結果也收起（篩選留著）
    S.forgeMade = null;
    S.book = false; // 武學譜是疊在煉製頁上的一本書：換分頁就闔上
    S.zhuan = null; clearTimeout(zhuanTimer); // 傳也一樣
    S.mtEdit = null; S.mtZoom = null; S.boardCard = null; // 名帖的畫布與放大的那一張、榜單點開的卡也收起
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

  // 破境卡（tianxia/ascend.py；招式與絕學稿案第三節）：剛破境就蓋一張在畫面上——左邊破境前的招、右邊絕招、中間模型寫的一句、
  // 戰力從多少到多少、底下江湖史那一行。那一句還沒寫就請伺服器寫一次（/api/do/ascend_line，三段式）；收下了才收掉。字待 joy 潤
  let ascendAsked = "";
  function ascendCard() {
    const card = S.main && S.main.status && S.main.status.ascension;
    let box = document.getElementById("ascend");
    if (!card) { if (box) box.remove(); return; }
    if (!box) { box = document.createElement("div"); box.id = "ascend"; box.className = "asc-wrap"; document.body.appendChild(box); }
    const [was, now] = card.power || [];
    box.innerHTML = `<div class="asc-card" role="dialog" aria-label="破境">
      <p class="asc-head">${tsealHtml("絕")}<b>【${esc(card.name)}】破境</b></p>
      <div class="asc-moves"><div class="asc-was"><small>破境前</small><p>${tacticHtml(card.before)}</p></div>
        <div class="asc-arrow">›</div><div class="asc-now"><small>絕招</small><p>${tacticHtml(card.after)}</p>${card.after_tail ? `<p>${tacticHtml(card.after_tail)}</p>` : ""}</div></div>
      <p class="asc-line">${card.line ? `「${esc(card.line)}」` : `<span class="muted">……</span>`}</p>
      ${was != null && now != null ? `<p class="asc-power">戰力 ${was | 0} → <b>${now | 0}</b></p>` : ""}
      <p class="muted small asc-chron">江湖史：${esc(card.chronicle || "")}</p>
      <button class="btn primary" data-act="ascend-ok">收下</button></div>`;
    if (!card.line && ascendAsked !== card.art) {
      ascendAsked = card.art;
      api("/api/do/ascend_line", {}).then((r) => { if (r && r.main) applyMain(r.main); }).catch(() => {});
    }
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
      // 自創武學立好、作罷：草稿沒了就在這一次重畫裡直接回修練頁、一下回頂，不先畫一張空的自創頁、
      // 捲到一半再換一次（Joy 2026-10-22「自創武學完畢那個畫面會閃爍」）
      const cr = S.main && S.main.status && S.main.status.create;
      if (S.createOpen && !(cr && cr.draft)) { S.createOpen = false; renderPage(); window.scrollTo(0, 0); return; }
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
      // 清單上「合不了」的標記變了：只換抽屜裡那一張清單（捲到哪留在哪），爐子與頁面不重畫——整頁重畫的話火舌、剛放進去那一格的閃光都從頭來一次
      const sheet = S.tab === "craft" && JSON.stringify(S.forgePicks) !== drawn && document.querySelector(".craft-sheet");
      if (sheet) { const top = sheet.scrollTop; sheet.innerHTML = craftSheetInner(S.menxia || {}); sheet.scrollTop = top; applyGlow(); }
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
        // 出爐的排場只演一次（一秒半，不擋操作）：畫完這一次就收，之後輪詢重畫不再翻一次
        S.forgeReveal = made;
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
    if (guideMoved) { renderPage(); S.forgeReveal = false; window.scrollTo({ top: 0, behavior: "smooth" }); } else {
      keepPlace(() => renderPage());
      S.forgeReveal = false;
      if (made) kilnBurst();
      showMadeCard();
    }
    updateForgeLine(); // 心得、體力、「已經有了」都變了：重問一次說明
  }

  // 開爐成了：爐裡的太極猛轉兩圈（大小兩座都是），新武學的卡從爐裡冒出來；轉完回到平常的慢轉
  function kilnBurst() {
    document.querySelectorAll(".furnace .w-taichi, .kiln-taichi .w-spin").forEach((g) => {
      g.classList.add("burst");
      g.addEventListener("animationend", () => { // 轉完接回平常的慢轉：照同一個鐘起跳（spinAt），不從頭轉、不頓一下
        g.classList.remove("burst");
        const secs = parseFloat(getComputedStyle(g).animationDuration) || 28;
        g.style.animationDelay = `-${((performance.now() / 1000) % secs).toFixed(2)}s`;
      }, { once: true });
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
      if (r.arrived) { S.mapMode = "overview"; S.mapSel = null; S.mapDrawer = "min"; } // 出發了：留在輿圖，抽屜收回那一行（在路上寫往哪裡）
      else toast(`沒能出發：${r.reason}`);
      await loadMap();
      setMapDrawer(S.mapDrawer);
    }, WAIT_LINES.move);
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
          // 江湖頁的小地圖點了某一處（設計第八節）：輿圖開在那一處所在的區圖、抽屜半開它的卡（那一區照它算：mapReady）
          if (loc) { S.mapSel = loc.getAttribute("data-loc"); S.mapMode = "place"; S.mapDrawer = "peek"; S.mapLayer = "region"; S.mapRegion = regionOfPlace(S.mapSel); }
          await goTab(el.dataset.tab);
          break;
        }
        case "opt-why": toast(el.dataset.why); break; // 灰掉的俠寇鈕（名聲 5B）：點了只說整句原因，不送選擇
        case "choose":
          await choose(el, el.dataset.id);
          if (S.tab === "map") await loadMap(); // 在輿圖上按的（抽屜裡的喊停）：疊層跟著換
          break;
        case "map-report": S.news = "reports"; await goTab("news"); break; // 卡上「攻城戰果」那一段的「看戰報」：開見聞的戰報
        case "world-region": enterRegion(el.dataset.id); break; // 天下圖點一州
        case "world-enter": enterRegion(hereRegion()); break; // 天下圖抽屜的「進入此區」：你在的那一州
        case "map-world": // 「‹ 天下」、天下圖的「天下」（已經在天下圖、放大了：滑回 1 倍）
          if (S.mapLayer !== "world" || S.mapMode !== "overview") toWorld();
          else if (S.mapPan) panReset();
          break;
        case "region-place": regionPick(el.dataset.id); break; // 區圖點了一處（小圖或名字框）：抽屜半開它的卡，地圖不動
        case "region-blank": regionPick(null); break; // 區圖點空白：收回那一行
        case "region-go": enterRegion(el.dataset.id); break; // 區圖的鄰區出口「→ 南陽」
        case "map-wash": washToggle(); break; // 區圖的「塗層」
        case "map-pick": { // 找地點、今天去哪裡出陣挑了一處：在別區（或在天下圖）就進那一區，抽屜半開它的卡
          const id = el.dataset.id, rid = regionOfPlace(id);
          if (S.mapLayer === "world" || rid !== S.mapRegion) { enterRegion(rid, id); break; }
          regionPick(id);
          break;
        }
        case "map-search":
          S.mapMode = "search"; S.mapSel = null;
          setMapDrawer("full");
          redrawDrawer();
          drawSel();
          setTimeout(() => { const q = document.getElementById("map-q"); if (q) q.focus(); }, 230);
          break;
        case "map-open": mapOpen(); break; // 收著的那一行點了：天下圖拉開你腳下的卡；區圖你在這一區時開你腳下這一處的卡
        case "map-back":
          S.mapMode = "overview"; S.mapSel = null; S.mapQuery = "";
          setMapDrawer("min");
          redrawDrawer();
          drawSel();
          break;
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
        case "newbie-go": newbieGo(Number(el.dataset.i)); break; // 新手目標的「去做」
        case "newbie-drifter": await doMain("newbie_drifter"); break; // 新手目標的「就當散人」
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
        case "hero-node": heroTap(el); break; // 修練頁人物面板的光點：開那一樣的抽屜
        case "drawer-close": S.pdrawer = false; S.artOpen = null; S.insOpen = null; S.slotPick = null; renderPage(); break;
        case "ins-filter": S.insFilter = el.dataset.filter; renderPage(); break;
        case "allocate": await doMain("allocate", { stat: el.dataset.stat }); break; // 升級的屬性點加到一項（狀態列展開後的「＋臂力」）
        case "do": S.sheet = false; await doMain(el.dataset.op); break;
        case "letter-open": S.letterOpen = S.letterOpen === Number(el.dataset.id) ? null : Number(el.dataset.id); renderPage(); break;
        case "letter-read": S.letterOpen = null; await doMain("letter_read", { id: Number(el.dataset.id) }); break;
        case "letter-decline": await doMain("letter_decline", { id: Number(el.dataset.id) }); break;
        case "gender-pick": S.genderPick = el.dataset.value || null; render(); break;
        case "rename-ask": { const v = (document.getElementById("rename-name") || {}).value || ""; if (v.trim()) { S.renameAsk = v.trim(); render(); } break; }
        case "rename-back": S.renameAsk = null; render(); break;
        case "rename-go": await renameGo(); break;
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
        case "ask-no":
          closeAsk();
          if (S.mallOpen && S.mallPick) { S.mallPick = null; renderMall(); } // 商城的購買確認按了再想想：那一格不再框著
          break;
        // 商城（商城第二批）：齒輪旁的錠子鈕與底部第六格都打開那一層（不換頁）
        case "mall-open": await openMall(); break;
        case "mall-goto": await openMall(); mallPick(el.dataset.id); break; // 別頁引過來買某一件（修練頁沒丹時的破境丹）
        case "mall-close": closeMall(); break;
        case "mall-tab": await mallTabTo(el.dataset.tab); break;
        case "mall-pick": mallPick(el.dataset.id); break;
        case "mall-qty": { // 購買確認那張紙的數量：同一件、同一個編號重畫
          const now = S.mallAskNow, it = now && S.mallData && S.mallData.items.find((one) => one.id === now.id);
          if (it) mallAsk(it, S.mallData, Number(el.dataset.n), now.ref);
          break;
        }
        case "mall-claim": await mallClaim(); break;
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
        case "create-name": {
          const n = document.getElementById("create-name"), m = document.getElementById("create-move");
          document.activeElement?.blur?.(); // 手機的鍵盤先在這一下收起，不要等換頁那一刻才收、整頁再跳一次
          await mx("create_name", { name: n ? n.value.trim() : "", move: m ? m.value.trim() : "" }); break; // 立好了 mx 直接回修練頁
        }
        case "create-cancel": await mx("create_cancel"); break;
        case "create-reroll": await mx("create_reroll"); break; // 重悟帖：留在成形那一步，三格換了
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
          renderPage();
          if (S.wheelSel) revealMoveCard(); // 收起（再點一次）不捲
          break;
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
    if (ev.target.dataset && ev.target.dataset.act === "region-pick") enterRegion(ev.target.value); // 區圖上面那一排換一區
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
    sealActPolled(old); // 獨門行動選目標的那一層（改版第 2 批）：開著而且資料變了只換那一層；底下的頁面照常補
    if (shopPolled(old)) return; // 店面開著（或剛開、剛收）：只管店面那一層（店面獨立介面設計 1.3）
    if (S.mallOpen) { // 商城那一層開著：底下的頁面被蓋住、不畫（出店時整個重畫）；餘額變了（管理者補發、別的分頁買了）才重抓這一頁
      if (!S.main.mall) { closeMall(); return; }
      if ((old && old.mall ? old.mall.balance : null) !== S.main.mall.balance) {
        await loadMall();
        if (S.mallTab === "log") await loadMallLog();
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
      const shown = (m) => JSON.stringify(MENXIA_SHOWN[tab].map((k) => m[k]));
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
    practice: ["rules", "heal_cost", "slot_cards", "owned_arts", "insights", "holdings", "naming", "player_card", "roster", "person", "person_card", "on_team", "lessons", "heal", "gear"],  // heal：療傷鈕能不能按（銀兩夠不夠、內傷）變了就要重畫
    craft: ["owned_arts", "insights", "holdings", "clue_items", "bag", "forge_line", "xinde"],
  };

  // 重畫這一頁但保留玩家正在做的事（輪詢、閉關被拒時用）：填到一半的欄位（閉關時數）、
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
