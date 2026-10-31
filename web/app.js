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
  const KINDS = ["武學", "內功"];
  // 江湖頁「前往」的走法（跟 atlas.MODES 同一份）。選的走法只放在 S.moveMode：不寫進 localStorage、cookie，
  // 重新整理頁面就回到步行；每個請求都帶著它（見 api()），伺服器照它排選單上的「前往」
  const FREE_TEXT_OPTION = "choice:free"; // 事件的隨口應對（engine.FREE_TEXT_OPTION）
  const SAY_OPTION = "talk:say"; // 跟人物對話時的「自己說」（engine.SAY_OPTION）：按了叫出輸入框，送出走 /api/say
  // 同一個輸入框的另外兩顆（NPC 智能 2.1，engine.TEXT_TALKS）：跟答應陪你出陣的人商量打法、他帶路的路上跟他說一句。
  // S.saying 記著是哪一顆（true 是舊的寫法＝自己說），送出時連 option 一起給 /api/say
  const SAY_OPTIONS = [SAY_OPTION, "talk:plan", "parley:road"];
  const SAY_HINTS = { "talk:plan": "跟他說你想好的打法", "parley:road": "路上想跟他說的話，也可以開口求他" };
  const sayingId = () => (S.saying === true ? SAY_OPTION : S.saying);
  const SENSE_DRAW = "sense:draw"; // 有所感進了感悟狀態：「把心中的形畫下來」叫出畫布（sensing.DRAW），畫好送 /api/sense
  const MOVE_MODES = [
    { id: "walk", name: "步行" },
    { id: "dash", name: "疾行" },
  ];
  // 照「走法」切換的選項：「前往」與路上的「折返」（路上設計 3.2）。切換鈕緊貼在第一個這種選項上面（A4／W6）
  const followsMode = (id) => id.startsWith("move:") || id.startsWith("road:back");
  const ROAD_TASKS = /^road:(think|ask|gather)$/; // 路上的三樣小事（engine.ROAD_TASKS），排成 2×2（FB-055）
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
    frontOpen: "", // 江湖頁「剛剛」底下那塊出陣回報，第一屏放不下收起來之後玩家點開的那一則（frontKey）：重畫時不再收
    nowOpen: null, // 江湖頁「剛剛」展開的那一則（記內容本身）；換成新的一則就收回（A4）
    letterOpen: null, // 江湖頁書信小卡攤開的那一封（id）
    letterShut: null, // 伺服器說一到就攤開的那一封（開局的託付，letter.open）被玩家收攏了（id）：下一次重畫不再自己攤開
    pushOn: false, // 手機通知：這台裝置訂著沒有（打開設定時問瀏覽器，pushRefresh）
    pushBusy: false, // 正在開、關手機通知（那一顆先灰掉）
    pushError: "", // 手機通知開不了、關不掉的原因（寫在那一顆底下）
    pushTestNote: "", // 「傳一則測試通知」送出去了沒
    pushKey: null, // 伺服器的公鑰（打開設定時先拿好，勾下去的那一下不必再等網路）
    pushKinds: null, // 五種通知各開著沒（/api/push 的 kinds）
    roundsOpen: null, // 江湖頁戰鬥卡片「過程」展開的那一場（戰報流水號）；換成新的一場就收回（計畫三 G6）
    peekOpen: null, // 江湖頁那一排小標（態勢｜大事｜主線）展開著的那一塊：{ id, week }；點同一個收起，換週就不再對得上（FB-039、正式版辛）
    hearOpen: null, // 戰鬥卡片底下聽來的那一句展開著的那一場（卡片的戰報流水號）；換成下一場就收回（FB-074）
    // 第一屏放不下時一步一步收（FB-107 的 fitFirstScreen）：
    fitted: [], // 這一次收了哪幾步（FIT_STEPS 的 key），給測試與除錯看
    fitWidth: 0, // 上一次量的是哪個寬度：視窗只有高度變了（手機網址列收合）不重量（fitOnResize）
    fitBase: null, // 量的基準：{ width, top } 這個寬度量到過最小的分頁列頂（網址列跑出來時），不跟著網址列跑（fitTabsTop，FB-123）
    fitting: false, // fitFirstScreen 正在收：它自己重畫狀態列（收 💡、還原）時不再重量（fitTopMoved，FB-123）
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
    wheelSel: null, // 江湖頁行動列展開的那一格（move；探索三選一開著時也有 explore；出陣約戰開著時 sortie＝出陣前那張卡）
    glowRoute: null, // 展開移動之後要發光的那一條路（move:<地點>）：約戰卡的「前往」、新手目標的「去做」記下，什麼時候熄掉見 routeGlowKey（FB-9001）
    sortieAnswer: null, // 出陣約戰：約戰卡上按了「應戰」的那一張（id），同一張封三招的卡寫應戰；別人先應、窗過了就收起（setMain）
    sortiePick: [], // 出陣約戰：封三招挑到一半的（一回合一招，沒挑的是 null）；打開別的、送出去就清掉
    sortieFold: {}, // 出陣約戰的卡上「這一塊」「贏了」「守住了」攤開了哪幾段（{block: true, …}）：輪詢重畫照它補回
    gatherOpen: false, // 探索卡上「找素材」底下的分支攤開了沒（第 32 項；做完一件事不收，下次點探索就直接看到）
    gatherSaying: false, // 找素材的「自己說…」輸入框叫出來了沒
    persuading: false, // 託付的勸降：輸入框叫出來的那一顆（errand:persuade:<id>），沒有是 false
    godNaming: false, // 神品意境自己取名：輸入框叫出來了沒（那一顆只有一種，OWN_NAME_ID；FB-901）
    sensing: false, // 有所感：畫布叫出來了沒（按了「把心中的形畫下來」）；感悟狀態結束（選單上沒有 SENSE_DRAW）就收起
    sensePts: [], // 畫布上那一筆的點位 [[x, y, 毫秒], …]（畫布座標 0～256）；輪詢重畫頁面之後照它補畫回去
    senseNote: "", // 畫布底下那一行：這一筆落下了沒（/api/sense_read；不寫筆畫的幾何）
    stroking: false, // 手指正按在畫布上：輪詢不重畫（重畫會換掉畫布、手指底下的那一筆就斷了）
    forgeLine: "",
    craftPick: false, // 煉製頁挑東西的抽屜開著沒（點爐子的空格打開；兩格放滿、關掉、換分頁就收）
    pdrawer: null, // 修練頁的抽屜開著哪一個光點（{t: "worn"|"gear", key}；false 是剛關上，序章不再自己攤開）
    selfOpen: {}, // 俠客頁底下的摺疊（功法庫、裝備、門下、規矩）哪幾個攤著（{lib: true, …}）：玩家開關的記下來，輪詢重畫照它補回
    insFilter: "all", // 修練頁意境列的篩選：all／free（沒裝的）／used（裝著的）
    forgeReveal: false, // 剛出爐：意境卡演一次排場
    forgePreview: null, // 兩格都放好時的預覽卡（/api/forge_line 的 preview，合成即設計）；只放一樣、空爐是 null，畫 forgeLine 那一行
    mapBase: null, // 輿圖升級：底圖（/api/map/base：svg、地點、路、大區），一次載入只抓一次，疊層的 key 變了才重抓
    mapState: null, // 疊層（/api/map/state）
    mapStateAt: 0, // 上次抓疊層的時間（輪詢每 MAP_STATE_EVERY 毫秒重抓一次）
    mapSel: null, // 選了的地點
    mapMode: "overview", // 在看什麼："overview"（抽屜是附近那一排）、"place"（一處的卡）、"search"（找地點那一整頁）、"timeline"（版圖變化）
    mapDrawer: "peek", // 抽屜的高度："peek"（半開：附近那一排、卡的第一屏）、"half"、"full"、"tl"（版圖變化）
    mapWeek: null, // 版圖變化看的週次；null＝現在
    mapQuery: "", // 找地點的字
    // 一張到底（企劃者 2026-10-30）：看哪裡 { z 倍率, x, y }（地圖上 (mx, my) 在地圖框裡的 (x + mx·z, y + my·z)）；null＝還沒定，打開時以你為中心
    mapCam: null,
    mapFilter: "all", // 上面那一排標籤篩的是哪一種（all、most:多敵、rich、people、ins:<意境>）
    mapPreview: null, // 附近那一排滑到的那一處（地圖飛過去、畫路線，還沒開卡）
    news: "reports",
    reports: null,
    reportOpen: false,
    tales: {}, // 戰記（玩家看到的名字；程式裡叫 tale、huaben）：流水號 → /api/tale 回的那一份（ready、pending、none）
    taleOpen: null, // 打開的那一篇（流水號）；null 是沒開
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
    if (typeof storyCard === "function") setTimeout(storyCard, 0); // 特殊事件的跳顯框：同上
    if (typeof outingSync === "function") setTimeout(outingSync, 0); // 走一趟停在要選的事上、選完了：接著走（outing.js）
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
    const list = TABS.filter((t) => [t.id, ...(t.also || [])].some((id) => shown(`tab:${id}`)));
    if (!list.length) return "";
    const mall = mallShown();
    // 「俠客」那一格：在修練或煉製頁都亮著；序章要你去煉製（glow 有 tab:craft）而你不在「俠客」時，這一格也替煉製發光（data-glow 兩個鍵），
    // 人已經在修練頁時改由頁底「煉製」那一顆發光
    const on = (t) => S.tab === t.id || (t.also || []).includes(S.tab) ? !(S.tab === "news" && selfNews(S.news))
      : t.id === "practice" && S.tab === "news" && !!selfNews(S.news); // 從「俠客」進去的行狀、榜單、名帖匣：亮「俠客」
    const glow = (t) => [t.id, ...(on(t) ? [] : t.also || [])].map((id) => `tab:${id}`).join(" ");
    return `<nav class="tabs"><div class="tabs-inner" style="grid-template-columns:repeat(${list.length + (mall ? 1 : 0)}, 1fr)">${list.map((t) => `
        <button class="tab ${on(t) ? "on" : ""}" data-act="tab" data-tab="${t.id}" data-glow="${glow(t)}">
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
      shown("hp") ? `<div class="bar hp" title="氣血" data-glow="hp"><i style="width:${pct(s.hp, s.hp_max)}%"></i>${s.injury >= 1
        // 內傷（FB-049）：斜紋是上限裡被內傷佔掉、回不來的那一截（寬＝內傷÷上限，回滿時紅條剛好接到它）；
        // 「傷 N」靠右另寫在斜紋那一頭，不再接在「氣血 N/M」後面跨過紅條的交界
        // 「氣血」兩個字包成一格：條窄、又有內傷時讓開給「傷 N」（style.css 的 @container，FB-135）
        ? `<b style="width:${pct(s.injury, s.hp_max)}%"></b>` : ""}<span><em class="lbl">氣血 </em>${s.hp}/${s.hp_max}</span>${s.injury >= 1
        ? `<span class="inj">傷 ${s.injury}</span>` : ""}</div>` : "",
      shown("silver") ? `<div class="num" data-glow="silver"><em>銀</em>${s.silver}</div>` : "",
      // 心得、名望、善惡、五項屬性搬到「俠客」頁（整合設計 6.2）；序章裡心得亮了、銀兩還沒亮時照舊寫在這裡（序章的話要你看它）
      shown("xinde") && !shown("silver") ? `<div class="num" data-glow="xinde"><em>心得</em>${s.xinde}</div>` : "",
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
  // 要放進第一屏的那一塊：平常閒著是行動列；事件、有所感、對話、決戰這種一組選項時是選單最後一顆。
  // 約戰卡緊接在行動列底下、第一張是應得了或同去得了的（FB-9006，企劃者 2026-10-28「要露出來」；sxRank 把可按的排在最前面）時，要擠進第一屏的
  // 是那一行（連右邊的鈕）：它在行動列底下，量它就連整排行動列一起照顧到了，只是多縮場景的畫（收法 5a）；約戰卡本身的版面不動、也不搬到行動列上面。
  // 沒有可按的約戰（只有自己貼的、結算完的、別區的、約戰關著），或行動列與約戰卡之間展開了移動、探索、出陣前那張卡（玩家自己攤開的），
  // 量的還是行動列，第一屏一個像素都不變。量的是約戰那一行、前面的步驟都收完還放不下時，再多收一步 desc（6c，企劃者 2026-10-28「擠完再上」）：
  // 閒著的場景卡把所在地的描述每段收成一行；目標是行動列、一組選項時那一步不做
  const FIT_DUEL_BTN = '#page > .act-bar + #sortie-duels > .sx-drow:first-of-type > [data-act="sortie-answer"], '
    + '#page > .act-bar + #sortie-duels > .sx-drow:first-of-type > [data-act="sortie-join"]';
  function fitDuelRow() {
    const btn = document.querySelector(FIT_DUEL_BTN);
    return btn ? btn.parentElement : null;
  }
  const fitTarget = () => fitDuelRow() || document.querySelector("#page > .act-bar") || document.querySelector("#page > .options > :last-child");
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
    // 5a. 場景的畫（減法季批 8）縮成一條橫幅（地名、時刻照舊壓在上面）：畫在行動列上面最佔高度（375×812 約 270px），
    //     「剛剛」的戰鬥卡長一點就把整排行動推出第一屏（2026-10-27 回報：以前沒有畫，行動鈕一直在第一屏）
    { key: "art", run: () => {
      const art = document.querySelector("#page > .card.scene > .scene-art:not(.fit-art)");
      if (art) art.classList.add("fit-art");
      return !!art;
    } },
    // 5c. 戰鬥卡片底下的補充（得了什麼、地盤多撿一份、鑄譜的那一句……）只留第一行，其餘收起來；點那一塊整塊攤開（S.extraOpen 記這一場）。
    //     得失那一段（數字）照舊在卡片上
    { key: "extra", run: () => {
      if (S.extraOpen != null && S.extraOpen === S.main.card_id) return false; // 玩家點開過：不收回去
      const box = document.querySelector("#page .battle-card .tx-extra:not(.fit-extra)");
      if (!box || box.querySelectorAll(":scope > .tx-line").length < 2) return false;
      box.classList.add("fit-extra");
      box.setAttribute("data-act", "extra-more");
      box.setAttribute("role", "button");
      box.setAttribute("tabindex", "0");
      box.setAttribute("aria-expanded", "false");
      return true;
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
    // 6a. 出陣回報（frontReportHtml）：那一句收掉、小籤收成一行（放不下淡出），進度條照留；點了整塊攤開（S.frontOpen 記這一則，重畫時不再收）
    { key: "front", run: () => {
      const el = document.querySelector("#page .sfront");
      if (!el || S.frontOpen === frontKey(S.main.front)) return false;
      el.classList.add("fit-tight");
      el.setAttribute("data-act", "front-more");
      el.setAttribute("role", "button");
      el.setAttribute("tabindex", "0");
      el.setAttribute("aria-expanded", "false");
      return true;
    } },
    // 6a'. 還放不下：出陣回報標題那一行與其餘的條也收掉，只留第一條（自己那一條；守是對面最高的那一條）與一行小籤
    { key: "front2", run: () => {
      const el = document.querySelector("#page .sfront.fit-tight");
      if (!el) return false;
      el.classList.add("fit-min");
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
    // 6c. 量的目標是約戰卡第一張可按的那一行（fitDuelRow，FB-9006）、前面的步驟都收了還放不下（矮手機：375×667、360×700 被分頁列蓋了 4～10 px）：
    //     閒著（沒有分隔線：不是集結、觀戰）的場景卡把所在地的描述每段收成一行、放不下加「…」，點了整張場景卡攤開（同第 7 步：fitClip、
    //     ownOpen，S.ownOpen 記著玩家攤開過就不再收）。企劃者 2026-10-28「擠完再上」。排在 7 之前：先收不少字的步驟，還不夠才收描述。
    //     只在量約戰那一行時做：目標是行動列、一組選項時一個像素都不動。「此地還有」、結伴、別人遞來的邀請（.calls）、地名與時刻那一條
    //     （有畫時疊在畫上；沒有畫時是場景卡第一段）都不是描述，不收
    { key: "desc", run: () => {
      if (!fitDuelRow()) return false;
      const scene = document.querySelector("#page > .card.scene:not(.road)");
      if (!scene || scene.querySelector(":scope > hr") || !idleMenu(S.main) || S.ownOpen === fitOwnKey()) return false;
      const paras = [...scene.querySelectorAll(":scope > p:not([class])")];
      if (!scene.querySelector(":scope > .scene-art")) paras.shift(); // 沒有畫：第一段是「【地名】危險 ★★」那一條，不是描述
      const any = fitClip(paras);
      if (any) scene.classList.add("fit-own"); // 跟第 7 步同一個記號（ownOpen、fitReset 照樣拿掉）
      return any;
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
    //     （減法季批 1 起是本週卡）「剛剛」只留時間與標題（得失照舊在，「展開全文」看全文）、灰掉的俠寇鈕底下那一行原因收掉（原因本來就寫在鈕的 title，點了說整句，
    //     見 data-act="opt-why"）。閒著（行動列）時不收；攤開了態勢那一排某一格、展開了「剛剛」的不收那一樣
    { key: "choices", run: () => {
      if (document.querySelector("#page > .act-bar") || !document.querySelector("#page > .options")) return false;
      let any = false;
      const peek = document.querySelector("#page > .wk-card");
      if (peek && !peek.querySelector(".wk-panel")) {
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
    if (S.renownTight) { S.renownTight = false; renderTop(); } // 名聲（1B）：稱號那一行畫回來再量
    page.querySelectorAll(".g-merit small.fit-hide").forEach((el) => el.classList.remove("fit-hide")); // 本場戰功的稱號（4B）
    page.querySelectorAll(".tx-tight").forEach((el) => {
      el.classList.remove("tx-tight");
      ["data-act", "role", "tabindex", "aria-expanded"].forEach((a) => el.removeAttribute(a));
    });
    page.querySelectorAll(".fit-fold").forEach((el) => el.classList.remove("fit-fold"));
    page.querySelectorAll(".fit-art").forEach((el) => el.classList.remove("fit-art")); // 5a
    page.querySelectorAll(".fit-extra").forEach((el) => { // 5c
      el.classList.remove("fit-extra");
      ["data-act", "role", "tabindex", "aria-expanded"].forEach((a) => el.removeAttribute(a));
    });
    page.querySelectorAll(".wk-card.fit-hide, .opt-note.fit-hide").forEach((el) => el.classList.remove("fit-hide")); // 第 10 步
    page.querySelectorAll(".now.fit-title").forEach((el) => el.classList.remove("fit-title")); // 第 10 步；fits／clamp 照下一段還原
    page.querySelectorAll(".now.fit-short").forEach((el) => {
      el.classList.remove("fit-short");
      if (el.dataset.fitWas && !el.classList.contains("open")) el.classList.replace(el.classList.contains("fits") ? "fits" : "clamp", el.dataset.fitWas);
      delete el.dataset.fitWas;
    });
    page.querySelectorAll(".fit-own, .fit-muster").forEach((el) => el.classList.remove("fit-own", "fit-muster")); // 第 6c、7、8 步（收成一行的段落由下面的 fitUnclip 攤回來）
    page.querySelectorAll(".call.fit-hide").forEach((el) => el.classList.remove("fit-hide")); // 6b：收掉的邀請攤回來
    page.querySelectorAll(".calls-more").forEach((el) => {
      if (el.dataset.fit) el.remove();
      else if (el.dataset.text != null) { el.textContent = el.dataset.text; delete el.dataset.text; }
    });
    fitUnclip(page);
    page.querySelectorAll(".fit-tight").forEach((el) => el.classList.remove("fit-tight"));
    page.querySelectorAll(".sfront.fit-min").forEach((el) => el.classList.remove("fit-min"));
    page.querySelectorAll('.sfront[data-act="front-more"]').forEach((el) => {
      ["data-act", "role", "tabindex", "aria-expanded"].forEach((a) => el.removeAttribute(a));
    });
  }
  // 場景卡裡收成一行的段落（第 6c、7、8 步）：一行、放不下加「…」（style.css 的 p.fit-clip），點了整張場景卡攤開（ownOpen）。
  // 收了之後數字（倒數、戰局）會藏到「…」後面的那一段不收
  function fitClip(paras) {
    let any = false;
    paras.forEach((p) => {
      p.classList.add("fit-clip");
      if (!fitDigitsShown(p)) { dropClip(p); return; }
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
  // 拿掉收成一行的記號。classList 拿光 class 之後，真的瀏覽器留下空的 class=""，而第 6c 步（desc）用 :scope > p:not([class]) 挑沒有 class 的描述段落——
  // 空屬性還在就再也選不到：沒有重畫的重量（轉向、拉視窗、點名號展開再收起）之後折疊消失、約戰鈕又掉回分頁列底下（FB-9010）。空了就把屬性整個拿掉
  function dropClip(p) {
    p.classList.remove("fit-clip");
    if (!p.getAttribute("class")) p.removeAttribute("class");
  }
  function fitUnclip(root) {
    root.querySelectorAll(".fit-clip").forEach((p) => {
      dropClip(p);
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
    // 「俠客」頁（減法季批 1，圖解版第 33 頁）：四欄裝備畫在人像的四個角（selfCorners），身上只留兩門的光點
    const nodes = fig.nodes.filter((n) => n.kind === "art").map((n) => [n, heroInfo(n, x, s)]).filter(([, info]) => info);
    const corners = selfCorners(x, s);
    if (!nodes.length && !corners) return "";
    // 點了開抽屜（practiceDrawer）；抽屜開著的那一個亮著
    const open = S.pdrawer && (S.pdrawer.t === "worn" || S.pdrawer.t === "gear") ? S.pdrawer.key : null;
    return `<section class="hero" aria-label="人物">
      <div class="hero-hd">
        <div><div class="hero-name">${esc(s.name)}</div><div class="hero-tag">${esc(s.affiliation)}</div></div>
        <div class="hero-sub"><div>第 ${s.level | 0} 級</div><div>氣血 ${s.hp | 0}／${s.hp_max | 0}</div>${typeof x.might === "number" ? `<div class="hero-might">戰力 <b>${x.might | 0}</b></div>` : ""}${heroAnnalsHtml()}</div>
      </div>
      <div class="hero-stage">
        <div class="hero-halo" aria-hidden="true"></div>
        <div class="hero-fig" style="aspect-ratio:${fig.ratio}">
          <img src="${fig.src}" alt="" draggable="false">
          ${nodes.map(([n, info]) => `<button class="hero-node${n.key === open ? " on" : ""}${info.lit ? "" : " dim"} ${n.side}" style="left:${n.x}%;top:${n.y}%" data-act="hero-node" data-kind="${n.kind}" data-key="${esc(n.key)}"${info.glow && info.glow.length && n.key !== open ? ` data-glow="${info.glow.join(" ")}"` : ""} aria-label="${esc(info.label)}"><i class="pulse"></i><i class="dot"></i><span>${info.move ? `${esc(info.name)}<small>〔${esc(info.move)}〕</small>` : esc(info.label)}</span></button>`).join("")}
        </div>
        ${corners}
      </div>
    </section>`;
  }
  // ── 「俠客」頁（減法季批 1，整合設計 6.5；圖解版第 33、34 頁）：修練頁的上半換成人像四角的四欄裝備、身上兩門的成數條（絕學金框、朱印「絕」）、
  // 心得名望善惡與五項屬性（以前在狀態列，6.2 搬來）、底下三個入口（煉製、自創武學、榜單；行狀、名帖匣是一行小字）。規則一個字都沒改：
  // 點什麼都是原本那一格（抽屜、煉製頁、自創頁、見聞那一段）。字待 joy 潤
  const SELF_CORNERS = [["weapon", "tl"], ["mount", "tr"], ["armor", "bl"], ["treasure", "br"]];
  const GEAR_ICONS = {
    weapon: '<path d="M14.5 17.5L3 6V3h3l11.5 11.5M13 19l6-6M16 16l4 4M19 21l2-2"/>',
    armor: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/>',
    mount: '<path d="M4 18c1-4 3-6 6-7l2-5 3 2 3-1-1 4 3 3-2 1-2-2c-2 1-3 3-3 6M8 18v3m8-4v4"/>',
    treasure: '<path d="M12 2l3 6.5 7 .8-5.2 4.8 1.5 7-6.3-3.6-6.3 3.6 1.5-7L2 9.3l7-.8z"/>',
  };
  // 「裝備」那一段的一格（gearBlock）：圖示、欄名、階品；裝了什麼、一句效果；武器、防具、坐騎多一條還剩幾成（鋒利、耐久、飽足）；
  // 裝備庫裡同一欄還有幾件。空的那一格虛線框，寫空著的那一句與哪裡拿得到。點了開那一欄的抽屜（hero-node，同人像四角）
  function gearEffect(slot, w) {
    if (slot === "weapon") return w.bonus ? `威力 ${w.bonus}` : "用不上你身上的武學";
    if (slot === "armor") return `一場少扣 ${w.cut} 氣血${w.fit ? `・${w.fit}` : ""}`;
    if (slot === "mount") return `疾行省 ${w.save} 體力・路上快 ${w.speed}`;
    return w.effect_text || "";
  }
  function gearCell(g) {
    const w = g.worn, label = g.label || HERO_GEAR_NAMES[g.slot];
    // 傳承（玉璽碎片的抄本，寶物那一欄）：沒帶寶物時那一格寫它；帶著寶物時底下多一行
    const heir = g.heirloom ? `<small class="gc-more">傳承【${esc(g.heirloom.name)}】</small>` : "";
    const more = (g.rack.length ? `<small class="gc-more">裝備庫還有 ${g.rack.length} 件</small>` : "") + (w ? heir : "");
    const icon = `<svg viewBox="0 0 24 24" aria-hidden="true">${GEAR_ICONS[g.slot] || ""}</svg>`;
    if (!w && g.heirloom) {
      return `<button class="gear-cell ${esc(g.slot)}" data-act="hero-node" data-kind="gear" data-key="${esc(g.slot)}" aria-label="${esc(label)}：${esc(g.heirloom.name)}">
        <span class="gc-hd"><svg viewBox="0 0 24 24" aria-hidden="true">${GEAR_ICONS[g.slot] || ""}</svg><em>${esc(label)}</em><small>傳承</small></span><b class="gc-name">【${esc(g.heirloom.name)}】</b><small class="gc-fx">${esc(g.heirloom.effect_text || "")}</small>${more}</button>`;
    }
    if (!w) {
      return `<button class="gear-cell empty" data-act="hero-node" data-kind="gear" data-key="${esc(g.slot)}" aria-label="${esc(label)}：空著">
        <span class="gc-hd">${icon}<em>${esc(label)}</em></span><b class="gc-name">空著</b><small class="gc-fx">${esc(g.where || g.empty || "")}</small>${more}</button>`;
    }
    const edge = g.slot === "treasure" ? "" : `<span class="gc-edge" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${w.edge | 0}" aria-label="${esc(w.wear_word || "鋒利度")}"><i style="width:${Math.max(0, Math.min(100, w.edge | 0))}%"></i></span><small class="gc-edgen">${esc(w.wear_word || "鋒利度")} ${w.edge | 0}</small>`;
    const off = g.slot === "weapon" && !w.bonus;
    return `<button class="gear-cell ${esc(g.slot)}${off ? " off" : ""}" data-act="hero-node" data-kind="gear" data-key="${esc(g.slot)}" aria-label="${esc(label)}：${esc(w.name)}">
        <span class="gc-hd">${icon}<em>${esc(label)}</em>${w.grade ? `<small>${esc(w.grade)}</small>` : ""}</span><b class="gc-name">【${esc(w.name)}】</b><small class="gc-fx">${esc(gearEffect(g.slot, w))}</small>${edge}${more}</button>`;
  }
  // 門下卡攤開那一塊：角色卡（member_card）拿掉卡頭已經寫了的（名字、等級氣血、內功、武學；本人的四欄裝備在「裝備」那一段），
  // 只留本命戰法、傳功、加成那幾行；都拿掉了就不畫
  const MATE_DUP = /^(第 \d+ 級|內功|武學|兵器|防具|坐騎|寶物|部下：|威力)/;
  function mateExtra(html) {
    const body = String(html || "").replace(/<h3>[\s\S]*?<\/h3>/, "").replace(/<\/?p>/g, "");
    const lines = body.split(/<br\s*\/?>/).map((t) => t.trim()).filter((t) => t && !MATE_DUP.test(t.replace(/<[^>]+>/g, "")));
    return lines.length ? `<p class="mate-lines">${lines.join("<br>")}</p>` : "";
  }
  const MATE_ROLES = { 本人: "self", 出戰: "fight", 在門下: "home", 部下: "follow" }; // 門下卡左邊那枚印的顏色
  function selfCorners(x, s) {
    if (!x.gear) return "";
    const cells = SELF_CORNERS.map(([key, at]) => {
      const g = x.gear.slots.find((sl) => sl.slot === key);
      if (!g) return "";
      const name = g.worn ? g.worn.name : (g.label || HERO_GEAR_NAMES[key]);
      return `<button class="self-gear ${at}${g.worn ? "" : " empty"}" data-act="hero-node" data-kind="gear" data-key="${key}" aria-label="${esc(g.label || HERO_GEAR_NAMES[key])}：${esc(g.worn ? g.worn.name : "空著")}">`
        + `<svg viewBox="0 0 24 24" aria-hidden="true">${GEAR_ICONS[key]}</svg><span>${esc(name)}</span></button>`;
    }).join("");
    return cells ? `<div class="self-gears">${cells}</div>` : "";
  }
  const CN_TENTHS = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"];
  // 「武學」那一段（俠客頁重排，Joy 2026-10-24）：小標題右邊一顆「功法庫 N/M・意境 K ›」（攤開底下的功法庫摺疊、捲過去），
  // 底下身上兩門的成數條：點了開那一門的抽屜（同人像上的光點）。絕學金框、左邊一枚朱印「絕」，底下一句破境那一行的話
  function selfArtsHtml(x) {
    const worn = KINDS.map((k) => x.owned_arts.find((a) => a.worn && a.kind === k)).filter(Boolean);
    const lib = x.holdings ? `<button class="linkish" data-act="self-sec" data-sec="lib">功法庫 ${x.holdings.count | 0}/${x.holdings.cap | 0}・意境 ${(x.insights || []).length} ›</button>` : "";
    const head = `<div class="self-hd"><h3>武學</h3>${lib}</div>`;
    if (!worn.length) return `<section class="self-sec" aria-label="武學">${head}<p class="muted">你身上還沒有武學。</p></section>`;
    return `<section class="self-sec" aria-label="武學">${head}<div class="self-arts">${worn.map((a) => {
      const lv = Math.max(0, Math.min(10, a.level | 0)), top = a.quality === "絕學";
      const note = top ? (a.cultivate && (a.cultivate.legend ? a.cultivate.legend.note : a.cultivate.note)) || "" : "";
      return `<button class="self-art${top ? " q4" : ""}" data-act="hero-node" data-kind="art" data-key="${esc(a.kind)}">${top ? '<span class="qseal q4 big">絕</span>' : ""}`
        + `<span class="sa-body"><span class="sa-hd"><b>${esc(a.name)}</b><small>${top ? "絕學" : esc(a.kind)}・第${CN_TENTHS[lv]}成</small></span>`
        + `${note ? `<small class="sa-note">${esc(note)}</small>` : ""}<i class="sa-ten" role="meter" aria-valuemin="0" aria-valuemax="10" aria-valuenow="${lv}" aria-label="${esc(a.name)}第${lv}成">${Array.from({ length: 10 }, (_, k) => `<i${k < lv ? ' class="on"' : ""}></i>`).join("")}</i></span></button>`;
    }).join("")}</div></section>`;
  }
  // 「屬性」那一段（以前在狀態列與點名號攤開的那一塊，整合設計 6.2）：五項一格一欄（名字、數字），有點可配時每格底下一顆「＋」、
  // 小標題右邊寫「可配 N 點」、格子底下一行五項各管什麼（statUsesHtml）；再一行名望、善名、惡名；心得一行在最底下（序章照舊點名號配）
  function selfStatsHtml(s) {
    if (!s || !s.attrs || (!shown("stats") && !shown("xinde"))) return "";
    const pts = s.stat_points | 0;
    const cols = s.attrs.map(([k, v, key]) => `<div class="attr"><em>${esc(k)}</em><b>${v}</b>${pts
      ? `<button class="btn small alloc" data-act="allocate" data-stat="${esc(key)}" aria-label="${esc(k)}加一點" ${v >= s.stat_cap ? "disabled" : ""}>＋</button>` : ""}</div>`).join("");
    const minor = (s.minor || []).map(([k, v]) => `<span><em>${esc(k)}</em>${v}</span>`).join("");
    const stats = shown("stats") ? `<div class="self-hd"><h3>屬性</h3>${pts ? `<b class="pts">可配 ${pts} 點</b>` : ""}</div><div class="self-attrs">${cols}</div>${pts ? statUsesHtml(s) : ""}${minor ? `<div class="self-nums">${minor}</div>` : ""}` : "";
    const xinde = shown("xinde") ? `<p class="self-xinde"><em>心得</em><b>${s.xinde | 0}</b>${s.hint ? `<small>${esc(s.hint)}</small>` : ""}</p>` : "";
    return `<section class="self-stats self-sec" aria-label="心得與屬性">${stats}${xinde}</section>`;
  }
  // 「去做」那一段：兩格——煉製（煉製頁）、自創武學（自創頁）。療傷與閉關 Joy 2026-10-25 拿掉：療傷只在醫館做得了，
  // 入口就是江湖頁「此地還能做」的「醫館療傷」（act:heal），這裡再放一顆多半是灰的；閉關現在的玩法用不到。兩個都沒有時整段不畫
  function selfEntriesHtml(x) {
    const c = S.main && S.main.status && S.main.status.create;
    const craft = shown("tab:craft") ? '<button class="btn self-go" data-act="tab" data-tab="craft" data-glow="tab:craft">煉製<small>意境合成、看爐</small></button>' : "";
    const create = c && c.on ? `<button class="btn self-go" data-act="create-open">${c.draft ? "接著自創" : "自創武學"}<small>${createSub(c)}</small></button>` : "";
    if (!craft && !create) return "";
    return `<section class="self-sec" aria-label="去做"><div class="self-hd"><h3>去做</h3></div><div class="self-goes">${craft}${create}</div></section>`;
  }
  // 行狀（自己的傳，見聞那一頁的一段，SELF_NEWS）：人像那張卡右上角一顆「行狀 ›」（Joy 2026-10-24：榜單、名帖匣回見聞；榜單是籤、名帖匣在紀錄底下）
  const heroAnnalsHtml = () => (shown("tab:news") ? SELF_NEWS.map((n) => `<button class="linkish hero-annals" data-act="news" data-news="${n.id}">${n.name} ›</button>`).join("") : "");

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
  // 修練頁卡上的評分；槽裡有不發動的秘方特效時底下一行小字（skillview.score_note，Joy 2026-10-28「要讓玩家能清楚知道」）
  const scoreHtml = (a) => (typeof a.score === "number" ? `<span class="score">評 ${a.score}${a.score_note ? `<small>${esc(a.score_note)}</small>` : ""}</span>` : "");
  const fxOne = (e) => e.grand ? `<i class="fx grand${e.maybe ? " maybe" : ""}">${esc(e.name)}</i>`
    : e.special ? `<i class="fx sp${e.idle ? " idle" : ""}"${e.idle ? ' title="不發動"' : ""}>${e.idle ? `<s>${esc(e.name)}</s><small>不發動</small>` : esc(e.name)}</i>`
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
    const fx = (i.effects || []).map((e) => `<li class="${e.grand ? "grand" : e.special ? `sp${e.idle ? " idle" : ""}` : ""}"><b>${esc(e.name)}${e.grand || e.special ? "" : esc(FX_LAYERS[e.layers] || "")}</b>${e.desc ? `<span>${esc(e.desc)}</span>` : ""}${e.idle && i.idle ? `<em class="idle-why">${esc(i.idle)}</em>` : ""}</li>`).join("");
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
  // 自創撞到稀有路數的招，伺服器在招那一行後面補「（稀有路數）」（moves.RARE_WORD）：畫成一枚小章（Joy 2026-10-23「玩家要怎樣才知道自己的是」）
  function tacticHtml(text) {
    const RARE_MARK = "（稀有路數）";
    const m = /^([^〔]{1,2})〔/.exec(String(text || ""));
    const body = (s) => esc(s).split(esc(RARE_MARK)).join(`<span class="rare-tag">${esc(RARE_MARK.slice(1, -1))}</span>`);
    return m ? `${tsealHtml(m[1])}${body(String(text).slice(m[1].length))}` : body(text || "");
  }
  // 純文字版（清單的小字、title）：「掠影二重・流光」
  const fxText = (fx) => (Array.isArray(fx) ? fx.map((e) => (e.idle ? `${e.name}（不發動）` : e.grand || e.special ? e.name : `${e.name}${FX_LAYERS[e.layers] || ""}`)).join("・") : "");

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
    // 勢（create.stance_of 的同一套：提腿先看，再看收手或寬馬步，再看手伸遠或前傾）
    const stance = lift ? "變勢" : tucked || (spread > 1.1 && reach < 0.95) ? "守勢" : reach >= 1.0 || lean <= -10 ? "攻勢" : "起勢";
    return { attrs, why, stance };
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
    // 每一格裝的那一招寫出來（Joy 2026-10-25「武學裡面槽裡面擺的，他效果好像不會顯示」）：玉環上只放得下兩個字與效果名，
    // 做什麼原本只在 title（手機上看不到）；底下一格一行：第幾格、意境、效果、這一招做什麼。字待 joy 潤
    const notes = a.slots.map((s, i) => (s ? `<li><b>第 ${i + 1} 格「${esc(s.name)}」</b>${lookSeal(s.look)}<span class="jdn-fx">${esc(fxText(s.fx) || s.skill || "")}</span>${s.desc ? `<span class="jdn-desc">${esc(String(s.desc).replace(/^〔[^〕]*〕/, ""))}</span>` : ""}${stkHtml(s.stack)}${s.idle ? `<em class="idle-why">${esc(s.idle)}</em>` : ""}</li>` : "")).join("");
    return `<div class="jade">${cells}${fifth}</div>${notes ? `<ul class="jd-notes">${notes}</ul>` : ""}${picker}`;
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
          <div class="tr-meter"><div class="tr-lv"><b>第${level}成</b>${scoreHtml(a)}</div>${pips}</div>
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
    // FB-138：空著的那一格寫空著的那一句與哪裡拿得到（where，伺服器照內容的地點標籤給；內容裡沒有那種地點時是空字串）
    // 「裝備」那一段（Joy 2026-10-26「裝備跟門下顯示優化，裝備可以類似意境那樣，要直覺好看懂」）：四欄一欄一格（2×2），
    // 空的也畫（虛線框、寫哪裡拿得到）；格子裡寫裝了什麼、一句效果、還剩幾成（鋒利、耐久、飽足）。點一格開那一欄的抽屜（slotBlock：
    // 換上、拆解、修、餵都在那裡，同人像四角）。這一版畫不出的欄位略過；四欄都關著（slots 空）整段不畫。字待 joy 潤
    const gearBlock = gear && gear.slots.some((g) => GEAR_ROWS[g.slot]) ? `<section class="self-sec gear-sec" aria-label="裝備"><div class="self-hd"><h3>裝備</h3>${hasGear ? `<small class="muted">裝備庫 ${gear.used | 0}/${gear.cap | 0}</small>` : ""}</div>
      <div class="gear-grid">${gear.slots.filter((g) => GEAR_ROWS[g.slot]).map(gearCell).join("")}</div>
      ${heldLine}</section>` : "";
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
      drawerTitle = g ? g.label : ""; drawerBody = g ? `<div class="gear">${slotBlock(g)}${heldLine}</div>` : ""; // .gear：一件一行、鈕靠右（同以前的摺疊）
    }
    const drawerHtml = drawerBody ? `<div class="sheet-bg" data-act="drawer-close"></div>
      <div class="sheet pr-sheet" role="dialog" aria-label="${esc(drawerTitle)}"><div class="grip"></div>
        <div class="top-row"><h3 style="flex:1">${esc(drawerTitle)}</h3><button type="button" class="btn small ghost" data-act="drawer-close">關閉</button></div>
        ${drawerBody}</div>` : "";
    // 俠客頁的排法（Joy 2026-10-24「這頁既然都要重做了，為什麼不整體重新規劃」；草圖 https://claude.ai/artifact/DcuRiGjo9CtcBJoY87wu9m）：
    // 人像與四欄裝備 → 武學（身上兩門；功法庫、意境是右上那一顆）→ 屬性五格 → 去做四格 → 記錄清單（行狀、榜單、名帖匣）→
    // 四個收著的摺疊：功法庫（武學、意境、批量熔煉）、裝備、門下、修練的規矩。開合記在 S.selfOpen（toggle 事件）；勾著批量熔煉時功法庫一定攤開
    const fold = (sec, title, body) => `<details class="fold self-fold" data-sec="${sec}"${(S.selfOpen && S.selfOpen[sec]) || (sec === "lib" && meltOn) ? " open" : ""}><summary>${title}</summary><div class="fold-body">${body}</div></details>`;
    const libBody = `${meltSwitch}${S.meltNote ? `<div class="msg melt-result">${S.meltNote}</div>` : ""}
      ${meltOn ? `<p class="muted melt-hint">點一列勾起來，再按底下的「熔掉」；點右邊的 › 看細節。身上正在練的與本命武學熔不掉。</p>
      ${meltTools}
      ${meltList}` : `${chips}
      ${lib.length ? (picked.length ? libGroups(rows) : '<p class="muted">這一類沒有功法。</p>')
        : '<p class="muted">功法庫是空的。合成出來的武學、學來的武學會放在這裡。</p>'}
      ${showAll ? "" : `<button class="btn ghost lib-more" data-act="lib-all">再列 ${picked.length - LIB_PAGE} 門</button>`}`}
      ${meltOn ? "" : `<div class="label">意境</div>
      ${x.insights.length ? `${insFilterRow}${insList.length ? `<div class="lib insl">${insList.map(insRow).join("")}</div>` : '<p class="muted">這一類沒有意境。</p>'}`
        : '<p class="muted">還沒悟到任何意境。去探索，荒郊野外最容易有所領悟。</p>'}`}`;
    const rosterBody = `<details class="fold" open><summary>本人</summary><div class="fold-body">${tenCells(x.player_card)}</div></details>
      ${mates ? `<div class="list">${x.roster.map((r) => `<button class="${x.person === r.key ? "on" : ""}" data-act="person" data-key="${esc(r.key)}">${esc(r.label)}</button>`).join("")}</div>` : ""}
      ${mates && x.person ? `<div class="card person-card">${tenCells(x.person_card)}${noteAt("person")}
        ${x.person === "player" ? '<p class="muted">本人一直都在隊伍裡。</p>' // 本人不能加入、移出（引擎也會擋）
          : x.person.startsWith("follower:") ? "" // 部下（計畫 T5）也不能加入、移出；角色卡已經寫了
          : `<button class="btn ${x.on_team ? "" : "primary"}" data-act="mx" data-op="${x.on_team ? "leave" : "join"}">${x.on_team ? "移出隊伍" : "加入隊伍"}</button>`}
        ${x.release ? `<button class="btn ghost" data-act="release-mate" data-confirm="${esc(x.release.confirm)}">放他回江湖</button>` : ""}
        ${lessonsHtml(x.lessons)}</div>` : ""}`;
    // 「門下」那一段（Joy 2026-10-26「門下顯示優化」）：一人一張卡（server 的 roster_cards）——名字、本人／出戰／在門下／部下的印、等級、
    // 氣血一條、身上兩門各一行（名字、品質、成數十格）。點一張在它底下攤開角色卡與加入、移出、放回江湖、傳功（同以前名冊點人）；再點收起。
    // 舊伺服器沒有 roster_cards 時照舊畫摺疊裡的名冊
    const mateCard = (c) => {
      const on = x.person === c.key;
      const hp = c.hp_max ? `<span class="mate-hp" role="meter" aria-valuemin="0" aria-valuemax="${c.hp_max}" aria-valuenow="${c.hp}" aria-label="氣血"><i style="width:${Math.max(0, Math.min(100, Math.round((c.hp / c.hp_max) * 100)))}%"></i></span><small class="mate-hpn">氣血 ${c.hp}／${c.hp_max}</small>` : "";
      const arts = c.arts.map((a) => `<span class="mate-art"><em>${esc(a.kind)}</em>${a.name ? `<b>${esc(a.name)}</b><small>${esc(a.quality)}${a.attribute ? `・屬${esc(a.attribute)}` : ""}</small>`
        + `<i class="sa-ten" role="meter" aria-valuemin="0" aria-valuemax="10" aria-valuenow="${a.level | 0}" aria-label="${esc(a.name)}第${a.level | 0}成">${Array.from({ length: 10 }, (_, k) => `<i${k < (a.level | 0) ? ' class="on"' : ""}></i>`).join("")}</i>` : '<small class="muted">尚未習得</small>'}</span>`).join("");
      const detail = on && x.person_card ? `<div class="mate-detail">${mateExtra(x.person_card)}${noteAt("person")}
        ${x.person === "player" || x.person.startsWith("follower:") ? ""
          : `<button class="btn ${x.on_team ? "" : "primary"}" data-act="mx" data-op="${x.on_team ? "leave" : "join"}">${x.on_team ? "移出隊伍" : "加入隊伍"}</button>`}
        ${x.release ? `<button class="btn ghost" data-act="release-mate" data-confirm="${esc(x.release.confirm)}">放他回江湖</button>` : ""}
        ${lessonsHtml(x.lessons)}</div>` : "";
      return `<div class="mate${on ? " on" : ""} role-${MATE_ROLES[c.role] || "home"}"><button class="mate-hd" data-act="person" data-key="${esc(c.key)}" aria-expanded="${on}">
        <span class="mate-seal" aria-hidden="true">${esc(c.role.slice(0, 1))}</span>
        <span class="mate-body"><span class="mate-name"><b>${esc(c.name)}</b>${c.level != null ? `<small>第 ${c.level | 0} 級</small>` : ""}<em>${esc(c.role)}</em></span>${hp}${arts}</span>
        <span class="mate-arrow" aria-hidden="true">${on ? "▴" : "›"}</span></button>${detail}</div>`;
    };
    const cards = x.roster_cards;
    const fighting = cards ? cards.filter((c) => c.role === "出戰" || c.role === "部下").length : 0;
    const rosterBlock = cards ? `<section class="self-sec mates-sec" aria-label="門下"><div class="self-hd"><h3>門下</h3><small class="muted">${cards.length > 1 ? `${cards.length - 1} 人・出戰 ${fighting} 人` : "還沒有同伴"}</small></div>
      <div class="mates">${cards.map(mateCard).join("")}</div>
      ${cards.length > 1 ? "" : '<p class="muted mates-none">交友、結識大勢人物，情誼夠了就有人願意追隨你。</p>'}</section>`
      : fold("roster", `門下${mates ? ` <small class="muted">${x.roster.length} 人</small>` : ""}`, rosterBody);
    // 紀念物（長篇奇事，企劃者 2026-10-27）：故事裡收下的小東西，沒有效果、不能賣，跨季跟著角色；一件都沒有不畫
    const keepItems = (S.main && S.main.keepsakes) || [];
    const keeps = keepItems.length ? `<section class="self-sec keepsakes" aria-label="紀念"><div class="self-hd"><h3>紀念</h3><small class="muted">故事裡收下的，留著</small></div>
      <p class="keep-list">${keepItems.map((k) => `<span class="keep">${esc(k)}</span>`).join("")}</p></section>` : "";
    return `
      ${proGuide()}
      ${heroPanel(x, s)}
      ${selfArtsHtml(x)}
      ${gearBlock}
      ${rosterBlock}
      ${keeps}
      ${selfStatsHtml(s)}
      ${selfEntriesHtml(x)}
      <div class="msg" id="mx-msg">${S.message}</div>
      ${naming}
      ${attrNoteHtml(x)}
      ${fold("lib", `功法庫 <small class="muted">武學與意境 ${x.holdings.count}/${x.holdings.cap}</small>`, libBody)}
      ${fold("rules", "修練的規矩", x.rules)}
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
    // 煉製頁是從「俠客」頁進來的（減法季批 1：分頁列上沒有它自己一格）：最上面一行「‹ 俠客」回去
    return `
      <div class="self-sub"><button class="linkish back" data-act="tab" data-tab="practice">‹ 俠客</button><h3>煉製</h3></div>
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
  // 擺式時即時算主屬性（create.top_of 的同一套）：伺服器給不含姿勢的權重，這裡加上姿勢讀出的兩路，取最高（同分照屬性的先後）
  function createMain(c, draft, attrs) {
    const w = { ...(draft.base_weights || {}) };
    attrs.forEach((a, i) => { w[a] = (w[a] || 0) + (Number((c.pose_weights || [])[i]) || 0); });
    const order = c.attributes || [];
    return order.reduce((best, a) => (best === null || (w[a] || 0) > (w[best] || 0) ? a : best), null);
  }
  // 勢與稀有路數（Joy 2026-10-22「要加」）：四個勢怎麼擺、對應哪個時機，現在擺的那一個亮；底下一行「每一格都有機會撞到稀有路數」
  // （表上每一格都有稀有的才寫，伺服器給 rare_line）。擺式時拖一下就重畫（rigRedraw），立意那一步照伺服器讀的。字待 joy 潤
  function stanceBoxHtml(c, kind, stance, main) {
    const rows = ((c.stances || {})[kind] || []);
    const now = rows.find((r) => r.stance === stance) || {};
    const list = rows.map((r) => `<li class="${r.stance === stance ? "on" : ""}"><span><b>${esc(r.stance)}</b>・${esc(r.timing)}</span><small>${esc(r.how)}</small></li>`).join("");
    return `<p class="cr-now">此式是<b>${esc(stance || "")}</b>・${esc(now.timing || "")}${main ? `<span class="muted small">（連兵器、意一起算，主屬性現在偏${esc(main)}）</span>` : ""}</p>
      <ul class="cr-stances">${list}</ul>
      ${c.rare_line ? `<p class="muted small">${esc(c.rare_line)}</p>` : ""}`;
  }
  const biasHtml = (bias) => Object.entries(bias || {}).sort((p, q) => q[1] - p[1]).map(([k]) => ringHtml([k], esc(k), "jchip")).join("");
  function createHtml() {
    const c = S.main && S.main.status && S.main.status.create;
    if (!c || !c.on) return "";
    const step = c.step, at = CREATE_STEPS.findIndex((p) => p[0] === step);
    const head = c.left == null ? "" : `<p class="muted small cr-left">本季還可自創 ${c.left | 0} 門</p>`;
    const steps = `<ol class="cr-steps">${CREATE_STEPS.map(([k, w], i) => `<li class="${i === at ? "on" : i < at ? "done" : ""}">${w}</li>`).join("")}</ol>`;
    const draft = c.draft;
    if (step !== "pose") S.createPose = null;
    if (step !== "name") S.createReread = null; // 重讀這句意那一格打到一半的字只留在這一門的成形那一步
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
        <div class="cr-stance-box" id="create-stance">${stanceBoxHtml(c, draft.kind, read.stance, createMain(c, draft, read.attrs))}</div>
        <div class="acts"><button class="btn primary" data-act="create-pose">擺定<small>下一步：立意</small></button>${quit}</div>
      </div>`;
    }
    if (step === "intent") {
      return `${head}<div class="card create">${steps}${sum}
        <div class="cr-mini">${figSvg(draft.pose, weapon, "cr-fig")}<p>${esc(draft.pose_read)}</p></div>
        <div class="cr-stance-box">${stanceBoxHtml(c, draft.kind, draft.stance, draft.main)}</div>
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
      ${draft.rare_hit ? `<p class="cr-rare">${esc(draft.rare_hit)}</p>` : ""}
      ${draft.tactic ? `<p class="art-tactic cr-move">${tacticHtml(draft.tactic)}</p>` : ""}
      ${draft.say ? `<p class="muted small">出手時：「${esc(draft.say)}」</p>` : ""}
      <p class="muted small">招剛創時還生，練到第四成才使得順。</p>
      ${draft.redo > 0 ? `<p class="muted small">不滿意這個形，可以免費重來一次（重擺或重立意）。</p>` : ""}
      <div class="cr-reroll">${(draft.reroll_left | 0) <= 0 ? `<button class="btn" disabled>重骰<small>這一門已骰滿 ${c.reroll_cap | 0} 次</small></button><span class="muted small">一門最多重骰 ${c.reroll_cap | 0} 次：留下這個形，或回頭重來。</span>`
        : c.rerolls > 0 ? `<button class="btn" data-act="create-reroll">重骰<small>重悟帖 剩 ${c.rerolls | 0} 張</small></button><span class="muted small">同一個架式與意，三格顏色與變招再擲一次。這一門還能重骰 ${draft.reroll_left | 0} 次。</span>`
        // 手上沒帖：引去萬寶閣，停在重悟帖那一件（Joy 2026-10-22「沒有重悟丹不會自動提示玩家去商城購買」；同修練頁沒丹時的破境丹）
        : c.shop ? `<button class="btn" data-act="mall-goto" data-id="${esc(c.shop)}">去萬寶閣<small>買重悟帖</small></button><span class="muted small">重悟帖可以直接重骰這個形，不必重來（一門最多 ${draft.reroll_left | 0} 次）。</span>`
        : `<span class="muted small">萬寶閣的重悟帖可以直接重骰這個形，不必重來（一門最多 ${draft.reroll_left | 0} 次）。</span>`}</div>
      ${(draft.reroll_left | 0) > 0 && c.rerolls > 0 ? `<div class="cr-reread">
        <div class="crow"><span>意</span><input class="input" id="create-reread" maxlength="${c.intent_max | 0}" value="${esc(S.createReread != null ? S.createReread : draft.intent || "")}"></div>
        <div class="cr-reroll"><button class="btn" data-act="create-reread">重讀這句意<small>重悟帖 剩 ${c.rerolls | 0} 張</small></button><span class="muted small">同一句意（也可以改寫）再讀一次：意分、火候、屬性重來，形也跟著重擲。跟重骰共用這一門的次數；沒讀成不扣帖。</span></div>
      </div>` : ""}
      <div class="crow"><span>名字</span><input class="input" id="create-name" maxlength="6" placeholder="2～6 個字，全服不能重名"></div>
      <div class="crow"><span>招名</span><input class="input" id="create-move" maxlength="4" value="${esc(draft.move || "")}" placeholder="2～4 個字"></div>
      <div class="acts"><button class="btn primary" data-act="create-name">立名<small>${draft.paid ? "心得已在立意時付了" : `心得 ${c.price | 0}`}</small></button>${redo}${quit}</div>
    </div>`;
  }
  // 自創單獨一頁（Joy 2026-10-21「創造武學不要卡在煉成的中間」）：入口在「俠客」頁底下那三顆的中間（減法季批 1；以前在修練頁功法庫的頂上），
  // 點了整頁換成自創（S.createOpen），左上「返回自己」。立好或作罷就回修練頁、結果寫在上面。字待 joy 潤
  const CREATE_STEP_WORD = Object.fromEntries(CREATE_STEPS);
  // 「俠客」頁底下「自創武學」那一顆的小字：起了意的寫停在哪一步，沒起意寫價錢（或這一季還能創幾門、做不了的原因）
  function createSub(c) {
    const d = c.draft;
    return d ? `${esc(d.kind)}・${esc(d.form)}，停在「${esc(CREATE_STEP_WORD[c.step] || "")}」`
      : c.problem ? esc(c.problem) : (c.left == null ? `心得 ${c.price | 0}` : `本季還可自創 ${c.left | 0} 門・心得 ${c.price | 0}`);
  }
  function createPageHtml() {
    return `<div class="cr-page">
      <header class="cr-bar"><button class="book-back" data-act="create-close" aria-label="返回自己">‹ 返回自己</button><span class="cr-bar-title">自創武學</span></header>
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
  // 重悟帖：重讀這句意（Joy 2026-10-22「立意那邊好像也要可以重骰」）：同 createIntent 走三段式，模型在鎖外重讀；讀成了留在成形那一步
  async function createReread() {
    const box = document.getElementById("create-reread");
    if (box) S.createReread = box.value;
    await busy(async () => {
      const r = await api("/api/do/create_reread", { text: S.createReread != null ? S.createReread : "" });
      applyMain(r.main);
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      if (text) toast(text);
      const c = r.main && r.main.status && r.main.status.create;
      if (!c || !c.draft || c.step !== "name") S.createReread = null;
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
    const box = document.getElementById("create-stance"), c = S.main && S.main.status && S.main.status.create;
    if (box && c && c.draft) box.innerHTML = stanceBoxHtml(c, c.draft.kind, read.stance, createMain(c, c.draft, read.attrs));
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
  // 兩本書：武學譜（口訣與秘方）、鑄譜（打造的隱藏配方）。字待 joy 潤。一行寫完：tests/web/test_arts_pages.py、test_arts_pages_two.py 的假瀏覽器照名字把這一行切出去（webharness.konst 只認一行的 const）
  const BOOKS = { arts: { title: "武學譜", verb: "合出", unit: "口訣", empty: "江湖上流傳的老話，有時藏著合成的門道。" }, forge: { title: "鑄譜", verb: "打出", unit: "鑄訣", empty: "鐵匠的閒話、說書人的掌故，有時藏著失傳的鑄法。" } };
  // 武學譜兩段的段名與一句說明（字待 joy 潤）；秘方的種類：fuse 裝滿武學的意境槽、merge 兩個意境合成（secret_recipes.view 的 kind）
  const MANUAL_PARTS = [["fuse", "武學篇", "武學的意境槽裝滿了，暗合口訣"], ["merge", "意境篇", "兩個意境放進爐裡合成"]];
  const MANUAL_VERB = { fuse: "使出", merge: "合出" };
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
    // 武學譜的分母是這一季全服共有幾條（status.manual_total；玩家回報 2026-10-25：以前寫「你聽過的」，參透完了也看不出還剩幾條）
    const total = which === "arts" ? (S.main?.status?.manual_total | 0) : 0;
    const sub = total ? `本季已參透 ${solved}／${total}${rows.length > solved ? `・線索 ${rows.length - solved} 條` : ""}`
      : rows.length ? `收錄${b.unit} ${rows.length} 則${solved ? `・已參透 ${solved}` : ""}` : "卷中尚無一字";
    return `<button class="manual-entry" data-act="book-open" data-book="${which}">${bookIcon()}<span><b>${b.title}</b><small>${sub}</small></span><i class="go">翻閱 ›</i></button>`;
  }
  // 參透一條秘方的那一下跳的視窗（企劃者 2026-10-25「應該是跳顯出個視窗比較明顯」；伺服器的 secret，secret_recipes.solved_card）：
  // 朱印蓋下來（同破境衝關的印）、參透的是哪一條、聽過的口訣、這一季的進度，「翻開武學譜」直接進那一頁。點外面或「收起」關掉。字待 joy 潤
  function secretPop(c) {
    if (!c) return;
    document.getElementById("sp-pop")?.remove();
    const box = document.createElement("div");
    box.id = "sp-pop";
    box.className = "sp-wrap";
    const pct = c.total ? Math.round((c.solved / c.total) * 100) : 0;
    const clues = (c.clues || []).map((t) => `<p class="sp-clue">「${esc(t)}」</p>`).join("");
    box.innerHTML = `<div class="sp-card" role="dialog" aria-label="${esc(c.title)}">
      <div class="sp-seal">${sealSvg(c.name)}</div>
      <p class="sp-title">${esc(c.title)}</p>
      <p class="sp-name">【${esc(c.name)}】</p>${clues}
      <div class="sp-bar" aria-hidden="true"><i style="width:${pct}%"></i></div>
      <p class="sp-note">${esc(c.note || `這一季的秘方，你已參透 ${c.solved}／${c.total}。`)}</p>
      <div class="sp-btns"><button class="btn primary" data-act="secret-book">翻開武學譜</button><button class="btn ghost" data-act="secret-close">收起</button></div>
    </div>`;
    box.addEventListener("click", (ev) => { if (ev.target === box) box.remove(); });
    document.body.appendChild(box);
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
    const streaks = (h.streaks || []).length ? `<ul class="tav-whispers">${h.streaks.map((m) => `<li>${esc(m)}</li>`).join("")}</ul>` : "";
    const hire = h.ended ? "" : `<h4 class="tav-h">買殺手<small>找上門的事，不說是誰</small></h4>
      <p class="shop-cap">報一個查到過的名號，同陣營也接。殺手只在城外出手（下線時人在城外也一樣）；得手了對方氣血只剩 1。失手一次，下一張找同一人的單貴一半、殺手更狠，最多三次。找不到人，期限到了退一半。</p>
      <div class="tav-tiers">${tiers}</div>
      <form class="tav-form" id="tav-hit"><input class="input" name="target" data-keep="hit" maxlength="20" placeholder="名號" autocomplete="off"><button class="btn primary small" type="submit">雇</button></form>
      <label class="tav-hush"><input type="checkbox" name="hush" form="tav-hit"${S.tavHush ? " checked" : ""}> 加付封口錢 ${h.hush | 0} 兩（失手、被反查時不容易供出你）</label>
      ${names ? `<div class="tav-known"><span class="gl">查到過的</span>${names}</div>` : ""}${streaks}${mine}`;
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
    // 這一段的變數不用單字母 x：tests/server/test_server.py 把修練頁到輿圖之間那個變數讀的欄位都當成 menxia_view 的欄位查
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
    // 參透了卻一句口訣都沒聽過的那一頁寫一句（Joy 2026-10-26 卡上選「補一句」；以前直書區是空的）。寫在行內：有測試只抽這一支。待 joy 潤
    const rows = manualRows(which), b = BOOKS[which];
    const now = rows.filter((r) => !r.past); // 卷首只算這一季真的聽到、打中的：跨季記得的那幾行（past）照樣列在卷裡（FB-404）
    const solved = now.filter((r) => r.solved).length;
    const leaf = (r, k) => `<article class="leaf${r.solved ? " solved" : ""}">
        <header class="leaf-head"><span>第${cnNum(k + 1)}則</span><span class="leaf-state">${r.solved ? "已參透" : "未參透"}</span></header>
        <div class="leaf-text">${r.clues.length ? r.clues.map((c) => `<p>${clauses(c).map((t) => `<span>${esc(t)}</span>`).join("")}</p>`).join("") : r.solved ? `<p class="leaf-blank"><span>未聞口訣，誤打誤撞${which === "forge" ? "打" : "合"}了出來。</span></p>` : ""}</div>
        <footer class="leaf-foot">${r.solved ? `${sealSvg(r.solved)}<span class="leaf-sign">${MANUAL_VERB[r.kind] || b.verb}<b>【${esc(r.solved)}】</b></span>` : '<span class="leaf-sign muted">尚待參悟</span>'}${r.recipe ? `<p class="leaf-recipe">${esc(r.recipe)}</p>` : ""}</footer>
      </article>`;
    // 武學譜分兩段（Joy 2026-10-25「武學跟意境合成兩個應該分開放」）：裝滿武學意境槽的（fuse）、兩個意境合成的（merge），各自從第一則數起
    const parts = which === "arts" ? MANUAL_PARTS.map(([kind, head, hint]) => [head, hint, rows.filter((r) => r.kind === kind)]).filter(([, , rs]) => rs.length) : [];
    const leaves = !rows.length ? null : parts.length
      ? parts.map(([head, hint, rs]) => `<h3 class="leaf-part"><b>${head}</b><small>${hint}</small></h3>${rs.map(leaf).join("")}`).join("")
      : rows.map(leaf).join("");
    const body = leaves || `<article class="leaf empty"><div class="leaf-text"><p>卷中尚無一字</p></div>
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
        <p class="book-sub">${which === "arts" && S.main?.status?.manual_total ? `本季秘方 ${S.main.status.manual_total} 條・已參透 ${solved}・所聞${b.unit} ${now.length} 則` : `本季所聞${b.unit} ${now.length} 則${solved ? `・已參透 ${solved} 則` : ""}`}</p>
      </div>
      <div class="leaves">${body}</div>
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
      <div class="train"><div class="tr-meter"><div class="tr-lv"><b>第${level}成</b>${scoreHtml(a)}</div>
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

  // 戰記（Joy 2026-10-29 先叫「戰役話本」，同日改名「戰記」；版面照主機那份 長社火攻話本）：戰報頁「‹ 全部戰報」那一行右邊一顆「戰記 ›」。
  // 寫好了（ready）才按得下去；還在寫（pending）灰掉寫「史官還在落筆」；沒有（none、還沒問到、不是決戰）不畫。標題一律「<戰名>戰記」
  const taleName = (name) => (name && !String(name).endsWith("戰記") ? `${name}戰記` : String(name || ""));
  function taleLink(id) {
    const t = id == null ? null : S.tales[id];
    if (!t || t.status === "none") return "";
    if (t.status === "pending") return '<button class="linkish huaben-link" disabled>史官還在落筆</button>';
    return `<button class="linkish huaben-link" data-act="tale" data-id="${id}">戰記 ›</button>`;
  }
  // 戰記頁：抬頭（季、戰名、結果）→ 一幕一段（幕名、那一幕的時辰，再一回一回：小標、正文、玩家原話）→ 尾段名錄（三四個人各一句）
  function taleHtml(t) {
    const back = `<button class="linkish back" data-act="tale-back">‹ ${S.news === "chronicle" ? "江湖史" : "戰報"}</button>`;
    if (!t) return `${back}<p class="muted">載入中…</p>`;
    if (t.status !== "ready") return `${back}<div class="card"><p class="muted">${t.status === "pending" ? "史官還在落筆，過一會兒再來。" : "這一場沒有戰記。"}</p></div>`;
    const paras = (text) => String(text || "").split(/\n+/).filter((x) => x.trim()).map((x) => `<p>${esc(x)}</p>`).join("");
    const said = (x) => (x ? `<div class="huaben-said"><span class="who">${esc(x.who || "")}${x.side ? `・${esc(x.side)}` : ""}</span><span class="line">「${esc(x.line || "")}」</span></div>` : "");
    const scene = (x) => `${x.head ? `<h4>${esc(x.head)}</h4>` : ""}${paras(x.text)}${said(x.said)}`;
    const acts = (t.acts || []).map((a, i) => `<section class="huaben-act"><h3><span class="no">${esc(a.no || `第${cnNum(i + 1)}回`)}</span>${esc(a.title || "")}</h3>`
      + `${a.banner ? `<p class="huaben-banner">${esc(a.banner)}</p>` : ""}${(a.scenes || []).map(scene).join("")}</section>`).join("");
    const cast = (t.cast || []).length
      ? `<section class="huaben-cast"><h3><span class="no">名錄</span>這一場在場的人</h3><ul>${t.cast.map((c) => `<li><b>${esc(c.name || "")}</b>${c.side ? `<span class="cast-side">${esc(c.side)}</span>` : ""}<span class="say">${esc(c.line || "")}</span></li>`).join("")}</ul></section>`
      : "";
    const meta = [t.season ? `第 ${t.season | 0} 季` : "", t.result || ""].filter(Boolean).join("・");
    return `${back}<article class="card huaben-page"><h2>${esc(taleName(t.battle_name || t.title))}</h2>`
      + `${meta ? `<p class="huaben-meta">${esc(meta)}</p>` : ""}${acts}${cast}</article>`;
  }
  // 江湖史最上面的戰記目錄（main.tales，伺服器的開關關著是空的、不畫）
  function taleIndexHtml(list) {
    if (!list || !list.length) return "";
    return `<p class="report-group">戰記</p><div class="list huaben-index">${list.map((x) => `<button data-act="tale" data-id="${x.battle_id}">${esc(taleName(x.title))}<span class="muted small">${x.season ? `第 ${x.season | 0} 季` : ""}${x.result ? `・${esc(x.result)}` : ""}</span></button>`).join("")}</div>`;
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

  // ── 手機通知（減法季批 9：回來的理由）──
  // 設定頁一顆「手機通知」，預設關；第一次來信時在信的小卡底下問一次（pushAskHtml，問過記在這個瀏覽器）。
  // 開了：向瀏覽器要通知權限 → 註冊 /sw.js → 拿伺服器的公鑰（/api/push）訂閱 → 交給 /api/push/subscribe（伺服器當場送一則「開了」）。
  // 伺服器關著（main.web_push 是 false）什麼都不畫。iPhone 要先「加入主畫面」、從主畫面打開才收得到（iOS 16.4 起）。字待 joy 潤
  const PUSH_ASKED_KEY = "tianxia-push-asked";
  const PUSH_KINDS = "來信、約戰、決戰集結、被截殺、被〈天下形勢〉提到";
  function pushSupported() {
    return !!(S.main && S.main.web_push) && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
  }
  function pushNeedsHome() { // iPhone、iPad 的 Safari：沒從主畫面打開就沒有 PushManager
    return !!(S.main && S.main.web_push) && /iP(hone|ad|od)/.test(navigator.userAgent || "")
      && !(navigator.standalone || (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches));
  }
  function pushAsked() { try { return localStorage.getItem(PUSH_ASKED_KEY) === "1"; } catch (e) { return true; } }
  function pushMarkAsked() { try { localStorage.setItem(PUSH_ASKED_KEY, "1"); } catch (e) { /* 存不了就只在這一頁不再問 */ } }
  function pushKey(text) { // base64url → Uint8Array（applicationServerKey）
    const raw = atob(text.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((text.length + 3) % 4));
    return Uint8Array.from(raw, (c) => c.charCodeAt(0));
  }
  // service worker 註冊好、啟用了才訂得了（第一次註冊時 register 回來的那一份還在安裝，直接 subscribe 會被拒：iPhone 上就是勾不起來）
  async function pushReg() {
    await navigator.serviceWorker.register("/sw.js");
    return navigator.serviceWorker.ready;
  }
  // 五種通知各一個開關（設定頁，預設全開；存在伺服器、這個帳號每一台一樣，/api/push 的 kinds）。字待 joy 潤
  const PUSH_KIND_NAMES = [["letter", "來信"], ["duel", "約戰"], ["rally", "決戰集結"], ["raid", "被截殺"], ["xingshi", "被〈天下形勢〉提到"]];
  const PUSH_TEST_OK = "送出去了：這一台應該馬上跳一則「通知設定好了」。沒跳的話看看手機有沒有開勿擾、專注模式。";
  function pushErrorText(e) { // 開不了的原因照實寫給玩家看（以前有錯就靜靜地沒勾起來）
    const name = (e && e.name) || "";
    if (name === "NotAllowedError") return pushDevice() === "ios"
      ? "iPhone 沒有給通知的權限：到 iPhone 的「設定」→「通知」→「天下大勢」打開「允許通知」，再回來勾一次。"
      : "瀏覽器沒有給通知的權限：到瀏覽器的網站設定裡把通知改成允許，再回來勾一次。";
    if (name === "AbortError" || name === "InvalidStateError") return `推送服務沒接通（${(e && e.message) || name}）：等一下再勾一次。`;
    return `開不了通知：${(e && e.message) || name || "不明的錯"}`;
  }
  function pushPaint() { // 只換設定頁「手機通知」那一塊（以前整個畫面重畫：iPhone 上一直閃）
    const box = typeof document !== "undefined" && document.querySelector(".push-box");
    if (box) box.innerHTML = pushBoxHtml();
    else if (S.sheet && S.pushHow) renderKeepingSheet(); // 「怎麼收到手機通知」那一頁按的「現在就開通知」：那一頁頂上那一句跟著換
  }

  async function pushRefresh() { // 打開設定時：這台裝置有沒有訂著；訂著就再交一次給伺服器（伺服器那份丟了也補得回來，不再送「開了」）
    if (!pushSupported()) return;
    try {
      const reg = await pushReg(); // 先註冊好、拿好公鑰：勾下去的那一下就能直接要權限、直接訂（iPhone 要在按下去的那一下做）
      const info = await api("/api/push");
      S.pushKey = info.key;
      S.pushKinds = info.kinds || null;
      const sub = await reg.pushManager.getSubscription();
      S.pushOn = !!sub && Notification.permission === "granted";
      if (S.pushOn) await api("/api/push/subscribe", { ...sub.toJSON(), quiet: true });
    } catch (e) { S.pushOn = false; }
    pushPaint();
  }

  async function pushEnable() {
    pushMarkAsked();
    if (!pushSupported()) return;
    S.pushBusy = true;
    S.pushError = "";
    S.pushTestNote = "";
    pushPaint();
    try {
      const perm = await Notification.requestPermission(); // 第一件事就問（前面不先等網路）：iPhone 只在按下去的那一下肯問
      if (perm !== "granted") {
        const err = new Error("");
        err.name = "NotAllowedError";
        throw err;
      }
      const reg = await pushReg();
      const key = S.pushKey || (S.pushKey = (await api("/api/push")).key);
      const sub = (await reg.pushManager.getSubscription()) || await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: pushKey(key) });
      await api("/api/push/subscribe", sub.toJSON());
      S.pushOn = true;
      toast("手機通知開了，馬上會跳一則試試。");
    } catch (e) {
      S.pushOn = false;
      S.pushError = pushErrorText(e);
    } finally { S.pushBusy = false; pushPaint(); }
  }

  async function pushDisable() {
    S.pushBusy = true;
    S.pushError = "";
    S.pushTestNote = "";
    pushPaint();
    try {
      const sub = await (await pushReg()).pushManager.getSubscription();
      if (sub) {
        await api("/api/push/unsubscribe", { endpoint: sub.endpoint }).catch(() => {});
        await sub.unsubscribe();
      }
      S.pushOn = false;
    } catch (e) { S.pushError = `關不掉：${(e && e.message) || "不明的錯"}`; } // 關不掉就照實留著勾
    finally { S.pushBusy = false; pushPaint(); }
  }

  async function pushTest() { // 「傳一則測試通知」：伺服器當場對這一台推一則，推不出去把原因寫在底下
    S.pushBusy = true;
    S.pushTestNote = "";
    pushPaint();
    try {
      const sub = await (await pushReg()).pushManager.getSubscription();
      if (!sub) throw new Error("這台裝置還沒開手機通知：先勾「手機通知」。");
      const res = await api("/api/push/test", { endpoint: sub.endpoint });
      S.pushTestNote = res.sent ? PUSH_TEST_OK : `沒送出去：${res.error || "不明的錯"}`;
    } catch (e) { S.pushTestNote = `沒送出去：${(e && e.message) || "不明的錯"}`; }
    finally { S.pushBusy = false; pushPaint(); }
  }

  async function pushKind(kind, on) { // 一種通知開或關
    try {
      const res = await api("/api/push/prefs", { kind, on });
      S.pushKinds = res.kinds;
    } catch (e) { /* api 已經跳了原因；照伺服器原本的畫回去 */ }
    pushPaint();
  }

  function pushBoxHtml() { // 設定頁「手機通知」那一塊的內容（pushPaint 只換這一塊）
    let note = "";
    if (pushNeedsHome()) note = "iPhone 要先在 Safari 按「分享 → 加入主畫面」，從主畫面打開遊戲，這裡才打得開。";
    else if (!pushSupported()) note = "這個瀏覽器收不到通知。";
    else if (Notification.permission === "denied") note = "通知被這個瀏覽器擋了：到瀏覽器的網站設定裡打開。";
    const off = !!note || S.pushBusy;
    const on = S.pushOn && !note;
    const kinds = S.pushKinds || {};
    const list = on ? `<div class="push-kinds">${PUSH_KIND_NAMES.map(([k, name]) =>
      `<label class="toggle"><input type="checkbox" class="push-kind" data-kind="${k}" ${kinds[k] !== false ? "checked" : ""} ${S.pushBusy ? "disabled" : ""}> ${name}</label>`).join("")}</div>
      <div class="row"><button class="btn small" data-act="push-test" ${S.pushBusy ? "disabled" : ""}>傳一則測試通知</button></div>` : "";
    return `<label class="toggle"><input type="checkbox" id="push-on" ${on ? "checked" : ""} ${off ? "disabled" : ""}> 手機通知${S.pushBusy ? "（處理中…）" : ""}</label>
      <p class="muted push-note">${note || (on ? "要跳哪幾種，底下一種一個開關（每一台裝置一樣）：" : `${PUSH_KINDS}時跳出來，遊戲關著也會。`)}</p>
      ${S.pushError ? `<p class="push-err">${esc(S.pushError)}</p>` : ""}
      ${list}
      ${S.pushTestNote ? `<p class="push-test-note">${esc(S.pushTestNote)}</p>` : ""}
      <div class="row push-help"><button class="btn small" data-act="push-how">${PUSH_HOW_TITLE} ›</button></div>`;
  }

  function pushRow() { // 設定頁那一顆
    if (!(S.main && S.main.web_push)) return "";
    return `<div class="push-box">${pushBoxHtml()}</div>`;
  }

  // ── 怎麼收到手機通知（Joy 2026-10-26：設定頁一顆鈕點開獨立的一步步說明，不跟玩法說明、新手引導混在一起；現階段很重要）──
  // 自己一頁（S.pushHow 時設定抽屜整個換成它，「← 回設定」回來）。照這台裝置排：iPhone／iPad（Safari 要先加入主畫面、從主畫面開，
  // iOS 16.4 起）、Android（Chrome 直接開，加到主畫面是建議）、電腦；偵測到的那一種攤開寫在最前面，其他兩種收在摺疊裡。
  // 頂上一句照此刻的狀況說下一步是什麼（還在瀏覽器裡、已經從主畫面開了、被擋了、已經開了）。字待 joy 潤
  const PUSH_HOW_TITLE = "怎麼收到手機通知";
  const PUSH_HOW_SITE = "tianxiadashi.com";
  function pushDevice() { // "ios"、"android"、"desktop"
    const ua = (typeof navigator !== "undefined" && navigator.userAgent) || "";
    return /iP(hone|ad|od)/.test(ua) ? "ios" : /Android/.test(ua) ? "android" : "desktop";
  }
  function pushStandalone() { // 從主畫面（安裝好的那一份）打開的
    return !!(typeof navigator !== "undefined" && navigator.standalone)
      || !!(typeof window !== "undefined" && window.matchMedia && window.matchMedia("(display-mode: standalone)").matches);
  }
  function pushPermission() { return typeof Notification !== "undefined" ? Notification.permission : "none"; }
  const PUSH_HOW_IOS = [
    `用 <b>Safari</b> 打開 <b>${PUSH_HOW_SITE}</b>（在 Chrome、LINE 裡打開的話先換到 Safari；要 iOS 16.4 以上）。`,
    "按畫面底下中間的<b>分享</b>鈕（一個方框、上面一支往上的箭頭）。",
    "選單往下捲，按<b>「加入主畫面」</b>，右上角按<b>「新增」</b>。",
    "回到手機的主畫面，點新出現的朱紅<b>「勢」</b>圖示打開遊戲（以後都從這裡進；在 Safari 裡開是收不到通知的）。",
    "遊戲裡右上角 <b>⚙ 設定</b> → 勾<b>「手機通知」</b> → 跳出來問的時候按<b>「允許」</b>。",
  ];
  const PUSH_HOW_IOS_DENIED = "之前按過「不允許」：到 iPhone 的<b>「設定」→「通知」</b>，找<b>「天下大勢」</b>，打開<b>「允許通知」</b>，再回遊戲勾「手機通知」。";
  const PUSH_HOW_ANDROID = [
    `用 <b>Chrome</b> 打開 <b>${PUSH_HOW_SITE}</b>。`,
    "遊戲裡右上角 <b>⚙ 設定</b> → 勾<b>「手機通知」</b> → 跳出來問的時候按<b>「允許」</b>。",
    "建議也加到主畫面：Chrome 右上角 <b>⋮</b> →<b>「加到主畫面」</b>（或「安裝應用程式」），以後點主畫面的朱紅<b>「勢」</b>圖示進來。",
  ];
  const PUSH_HOW_ANDROID_DENIED = "之前按過「封鎖」：按網址列左邊的<b>鎖頭（或設定）圖示</b> →<b>「權限」→「通知」</b>→ 改成允許；或到手機的<b>「設定」→「應用程式」→ Chrome →「通知」</b>打開，再回遊戲勾「手機通知」。";
  const PUSH_HOW_DESKTOP = [
    "右上角 <b>⚙ 設定</b> → 勾<b>「手機通知」</b> → 瀏覽器問的時候按<b>「允許」</b>（電腦也收得到，桌面會跳）。",
  ];
  const PUSH_HOW_DESKTOP_DENIED = "之前按過「封鎖」：按網址列左邊的<b>鎖頭圖示</b> →<b>「通知」</b>改成允許，再回來勾「手機通知」。";
  const PUSH_HOW_SECTIONS = {
    ios: { title: "iPhone、iPad", steps: PUSH_HOW_IOS, denied: PUSH_HOW_IOS_DENIED },
    android: { title: "Android 手機", steps: PUSH_HOW_ANDROID, denied: PUSH_HOW_ANDROID_DENIED },
    desktop: { title: "電腦", steps: PUSH_HOW_DESKTOP, denied: PUSH_HOW_DESKTOP_DENIED },
  };
  function pushHowStatus() { // 頂上那一句：此刻卡在哪、下一步做什麼
    const dev = pushDevice();
    if (S.pushOn && pushPermission() === "granted") return "這一台已經開了通知。想再開一台（另一支手機、電腦），在那一台照底下做一次。";
    if (pushPermission() === "denied") return "這一台的通知被擋著了：看底下「被擋了怎麼辦」那一段。";
    if (dev === "ios") return pushStandalone()
      ? "你已經是從主畫面打開的了：直接做第 5 步，勾「手機通知」就好。"
      : "你現在是在 iPhone 的瀏覽器裡：要先照第 1 到第 4 步把遊戲加到主畫面、從主畫面打開，才開得了通知。";
    if (dev === "android") return "Android 直接勾就好：照第 2 步。";
    return "電腦上直接勾就好；手機要收的話在手機上照底下做一次。";
  }
  function pushHowSection(key, open) {
    const sec = PUSH_HOW_SECTIONS[key];
    const body = `<ol class="push-steps">${sec.steps.map((t) => `<li>${t}</li>`).join("")}</ol>
      <h5>被擋了怎麼辦</h5><p>${sec.denied}</p>`;
    return open ? `<section class="push-how-sec"><h4>${sec.title}</h4>${body}</section>`
      : `<details class="fold push-how-sec"><summary>${sec.title}</summary><div class="fold-body">${body}</div></details>`;
  }
  function pushHowHtml() { // 設定抽屜整頁換成它
    const dev = pushDevice();
    const others = ["ios", "android", "desktop"].filter((k) => k !== dev);
    const canNow = pushSupported() && !pushNeedsHome() && pushPermission() === "default" && !S.pushOn;
    return `
      <div class="sheet-bg" data-act="sheet-close"></div>
      <div class="sheet push-how" role="dialog" aria-label="${PUSH_HOW_TITLE}">
        <div class="grip"></div>
        <div class="top-row"><button class="btn small ghost" data-act="push-how-back">← 回設定</button><h3 style="flex:1">${PUSH_HOW_TITLE}</h3><button class="btn small ghost" data-act="sheet-close">關閉</button></div>
        <p class="muted">開了之後，${PUSH_KINDS}時手機會跳出來告訴你，遊戲關著也會。不用裝 App、不收錢。</p>
        <p class="push-status">${pushHowStatus()}</p>
        ${canNow ? `<div class="row"><button class="btn primary" data-act="push-yes">現在就開通知</button></div>` : ""}
        ${pushHowSection(dev, true)}
        <p class="muted">用別的裝置？</p>
        ${others.map((k) => pushHowSection(k, false)).join("")}
      </div>`;
  }

  function pushAskHtml(m) { // 江湖頁信的小卡底下：第一次來信時問一次
    if (!m.letter || S.pushOn || pushAsked() || !pushSupported() || Notification.permission !== "default") return "";
    return `<section class="card push-ask"><p>以後有人來信、約戰、決戰集結時，要不要讓手機跳通知告訴你？</p>
      <div class="row"><button class="btn small primary" data-act="push-yes">開啟通知</button><button class="btn small ghost" data-act="push-no">不用</button></div></section>`;
  }

  // 管理者「每週的事」那一行在 7 天濃縮季的寫法（軍令每天、第 4 階席次每段；FB-501，待 joy 潤）
  const ADMIN_DAILY_WEEK7 = "每天、每段的事（照 00:00 的做法立刻再做一次；之後照常）";
  // 21 天季：軍令每天、第 4 階席次照舊每週一（FB-502，待 joy 潤）
  const ADMIN_DAILY_SEASON21 = "每天、每週的事（軍令照 00:00、席次照週一的做法立刻再做一次；之後照常）";
  function sheetHtml() {
    if (S.pushHow) return pushHowHtml(); // 「怎麼收到手機通知」自己一頁
    const s = S.main.status;
    const a = S.admin;
    const opts = (list) => list.map((x) => `<option value="${esc(x.id)}">${esc(x.label)}</option>`).join("");
    // 「匿名行走」那一句是傳聞分層一新寫的說明（待 joy 潤）；測試只比對這一句（tests/figures/test_rumor_layers.py）
    return `
      <div class="sheet-bg" data-act="sheet-close"></div>
      <div class="sheet" role="dialog" aria-label="設定">
        <div class="grip"></div>
        <div class="top-row"><h3 style="flex:1">設定</h3>${S.main.admin ? `<button class="btn small ghost" data-act="to-admin">管理者工具 ↓</button>` : ""}<button class="btn small ghost" data-act="sheet-close">關閉</button></div>
        ${genderRow(s)}
        ${renameRow()}
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
    drawRoute();
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
    if (S.reportOpen && S.reports.tale_id != null) await loadTale(S.reports.tale_id);
  }
  // 戰記（/api/tale/<流水號>）：寫好了（ready）留著不再問；還在寫（pending）每次打開戰報都再問一次
  async function loadTale(id) {
    const had = S.tales[id];
    if (had && had.status === "ready") return;
    S.tales[id] = await api(`/api/tale/${id}`);
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

  // 特殊事件的跳顯框（特殊事件設計稿）：一條線開頭、此事已了・入傳、此事未了，各跳一張蓋在畫面上；有圖放在上面，沒圖只有字。
  // 好幾張時照順序一張一張看（S.storyAt 記看到第幾張），看完最後一張才送 story_seen 清掉。破境卡在它上面（z-index 高一層）
  function storyCard() {
    const cards = (S.main && S.main.story_cards) || [];
    let box = document.getElementById("story-pop");
    if (!cards.length) { S.storyAt = 0; if (box) box.remove(); return; }
    const at = Math.min(S.storyAt || 0, cards.length - 1), c = cards[at];
    if (!box) { box = document.createElement("div"); box.id = "story-pop"; box.className = "story-wrap"; document.body.appendChild(box); }
    const opening = c.kind === "start" || c.kind === "stage"; // 段落卡（StoryStage.card，例：頓悟心魔那一關之前）跟開頭同一個寫法
    const after = c.kind === "after"; // 餘波（長篇奇事）：收了之後過幾天，走到某地聽到的那一段
    const retry = c.kind === "retry"; // 打輸了、還能再打（頓悟的心魔未破，Joy 2026-10-28）：標題就是那張卡自己的（「心魔未破」）
    const head = retry ? esc(c.title) : opening ? `${esc(c.sort)}・${esc(c.title)}`
      : after ? `後來・《${esc(c.title)}》` : c.kind === "end" ? `此事已了・入傳` : `此事未了・入傳`;
    const sub = opening || retry || (after && !c.ending) ? "" : after ? `<p class="story-sub">${esc(c.ending)}</p>` : `<p class="story-sub">《${esc(c.title)}》${c.ending ? `・${esc(c.ending)}` : ""}</p>`;
    const dun = c.sort === "頓悟"; // 特殊頓悟（Joy 2026-10-26「頓悟那邊也要有圖」）：圖照樣放上面，墨底與「悟」章分得出；沒圖就是墨底純字
    const src = c.src;
    const last = at >= cards.length - 1;
    const btn = opening ? "且看下去" : after ? "嗯" : retry ? "改日再來" : "收下";
    box.innerHTML = `<div class="story-card story-${esc(c.kind)}${c.failed ? " failed" : ""}${src ? " has-art" : ""}${dun ? " dun" : ""}" role="dialog" aria-label="${esc(c.title)}">
      ${src ? `<img class="story-art" src="${esc(src)}" alt="">` : ""}
      <div class="story-body"><p class="story-head">${tsealHtml(dun ? "悟" : opening || after || retry ? "奇" : "傳")}<b>${head}</b></p>${sub}
      <div class="story-text">${c.text}</div>
      ${cards.length > 1 ? `<p class="muted small story-count">${at + 1}／${cards.length}</p>` : ""}
      <button class="btn primary" data-act="story-ok" data-last="${last ? 1 : 0}">${btn}</button></div></div>`;
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

  // 神品意境自己取名（FB-901）：送 /api/choose 帶 text。名字不合格、這一季全服撞名時伺服器回一句話，
  // 表單留著、字也留著（同絕學定名那張），改一改再送；取成了選項就沒了，輸入框收起、回頁首看結果
  async function godName(form, text) {
    await busy(async () => {
      form.querySelectorAll("input, button").forEach((el) => { el.disabled = true; });
      try {
        const r = await api("/api/choose", { id: OWN_NAME_ID, text });
        const done = !((r.main && r.main.options) || []).some((o) => o.id === OWN_NAME_ID);
        if (done) S.godNaming = false;
        applyMain(r.main);
        const said = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
        if (said) toast(said);
        if (done) window.scrollTo({ top: 0, behavior: "smooth" });
        else {
          const again = document.querySelector("#own-name-form .input");
          if (again) { again.value = text; again.focus(); }
        }
      } finally {
        form.querySelectorAll("input, button").forEach((el) => { el.disabled = false; });
      }
    });
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

  // 託付的勸降（減法季批 6，FB-829）：送出後要等模型評這一句（同隨口應對），按鈕先寫「斟酌中……」；
  // 被擋下來的那一句（字數不對、人不在那裡）在江湖紀錄裡沒有，用提示泡泡講，輸入框留著；送成了（勸成、打起來、對方不置可否）收起
  const PERSUADE_WAIT = "斟酌中……"; // 待 joy 潤
  async function persuadeSay(form, text) {
    await busy(async () => {
      form.querySelectorAll("input, button").forEach((el) => { el.disabled = true; });
      const submitBtn = form.querySelector("[type=submit]");
      submitBtn.textContent = PERSUADE_WAIT;
      const stop = watchQueue(submitBtn, PERSUADE_WAIT);
      try {
        const r = await api("/api/do/persuade_text", { id: form.dataset.id, text });
        const said = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
        const done = said.startsWith("你：") || !((r.main && r.main.options) || []).some((o) => o.id === S.persuading);
        if (done) S.persuading = false;
        applyMain(r.main);
        if (said && !done) toast(said);
        if (done) window.scrollTo({ top: 0, behavior: "smooth" });
      } finally {
        stop();
        form.querySelectorAll("input, button").forEach((el) => { el.disabled = false; });
        submitBtn.textContent = PERSUADE_GO;
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

  // ── 出陣約戰（丙；畫的部分在 main.js 的 sortiePanelHtml）──
  // 封三招挑一招（再點同一招取消）：只換那一張卡（#sortie-panel 的 outerHTML），不重畫整頁（「剛剛」的浮現動畫不重播）
  function sortieMove(round, move) {
    const pick = (S.sortiePick || []).slice(0, SX_ROUNDS.length);
    pick[round] = pick[round] === move ? null : move;
    S.sortiePick = pick;
    const panel = document.getElementById("sortie-panel");
    if (panel) panel.outerHTML = sortiePanelHtml(S.main);
    else renderPage();
  }
  // 封好三招的那一顆：應戰那一張送 sortie_answer（{id, moves}），出陣送 sortie_go（{moves}）；三招沒挑滿不送（鈕本來就灰著）
  async function sortieSend() {
    const moves = (S.sortiePick || []).slice(0, SX_ROUNDS.length);
    if (moves.length < SX_ROUNDS.length || !moves.every(Boolean)) return;
    const d = sortieAnswering(S.main);
    if (d) await sortieDo("sortie_answer", { id: d.id, moves });
    else if (sortieCardOn(S.main) && !S.main.sortie_card.why_not) await sortieDo("sortie_go", { moves });
  }
  // 貼、應、同去：伺服器回來之後卡收起、挑的招清掉，「剛剛」照伺服器寫的那一則（被擋下來是一句提示），捲回最上面看結果（同 choose）
  async function sortieDo(op, body) {
    await busy(async () => {
      const r = await api(`/api/do/${op}`, body);
      S.wheelSel = null;
      S.sortieAnswer = null;
      S.sortiePick = [];
      applyMain(r.main);
      window.scrollTo({ top: 0, behavior: "smooth" });
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      if (text) toast(text);
    });
  }
  // 別區那一張的「前往 N 分」：照現有的移動走（同新手目標的「去做」）——移動清單上有往那一塊的路就展開移動、讓那一條發光，
  // 沒有（不相鄰）就開輿圖那一處的卡（步行、疾行的鈕在卡上，同江湖頁小地圖點一處）
  function sortieTravel(loc) {
    const id = `move:${loc}`, hit = (x) => x === id || x.startsWith(`${id}:`); // 疾行的 id 後面多接走法
    if ((S.main.options || []).some((o) => hit(o.id))) {
      S.sortieAnswer = null;
      S.wheelSel = "move";
      S.glowRoute = id; // 往那一處的那一條發光：記在狀態裡，重畫、摺疊 toggle 都保得住（FB-9001）
      renderPage();
      revealMoveCard();
      return;
    }
    mapGoto(loc);
    return goTab("map");
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
    let guideMoved = false, made = false, secret = null;
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
        secret = r.secret || null; // 這一季第一次參透一條秘方：出爐之後跳視窗（secretPop）
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
    secretPop(secret);
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
      if (r.arrived) { S.mapMode = "overview"; S.mapSel = null; S.mapPreview = null; S.mapDrawer = "peek"; } // 出發了：留在輿圖，抽屜回附近那一排（在路上寫往哪裡）
      else toast(`沒能出發：${r.reason}`);
      await loadMap();
      setMapDrawer(S.mapDrawer);
      drawRoute();
      if (r.arrived) mapHome();
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
      if (act === "wheel" || act === "sortie-open") requestAnimationFrame(() => inkRipple(key, x, y)); // 展開移動（出陣卡）會重畫整頁
      else inkRipple(key, x, y);
    }
    try {
      if (act.startsWith("outing-") && typeof outingClick === "function" && await outingClick(act, el)) return; // 走一趟那一層（outing.js）
      switch (act) {
        case "gate": S.gateMode = el.dataset.mode; renderGate(); break;
        case "promo-sound": promoSound(el); break;
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
        case "secret-close": document.getElementById("sp-pop")?.remove(); break;
        case "secret-book": document.getElementById("sp-pop")?.remove(); S.bookFrom = window.scrollY; S.book = "arts"; render(); document.querySelector(".book-layer")?.scrollTo(0, 0); break;
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
        case "renown-toggle": S.renownOpen = !S.renownOpen; S.renownDot = null; renderTop(); break; // 2C：展開時「名聲」那一行
        case "renown-dot": S.renownDot = S.renownDot === el.dataset.dot ? null : el.dataset.dot; renderTop(); break; // 點圓點看那一段
        case "renown-sanren": S.renownSanren = !S.renownSanren; renderTop(); break; // 散人另有的好處
        case "renown-open": S.showMore = true; S.renownOpen = true; S.renownDot = null; renderTop(); window.scrollTo(0, 0); break; // 6B：金色的「名號傳開」
        case "renown-peer": peerRenownToggle(el); break; // 3B：玩家卡的稱號小籤，原地攤開說明（不重畫整張卡）
        case "fronts-help": frontsTap(); break; // 點戰況圖卡：底下攤開／收起這一季在打什麼、亂局、怎麼推（explain-2）
        case "checkin": await doMain("checkin", el.dataset.attr ? { attribute: el.dataset.attr } : {}); break; // 「簽到」小標攤開的領取鈕（四階的日子帶屬性）
        case "pill": await doMain("pill"); break; // 體力條上的「丹 N」：服一顆回體丹（測試期間一鍵補滿打開時同一顆鈕寫「補滿」，同一條路由）
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
        case "story-ok": // 特殊事件的跳顯框：還有下一張就翻過去，最後一張才請伺服器清掉
          if (el.dataset.last === "1") { S.storyAt = 0; await doMain("story_seen", {}); } else { S.storyAt = (S.storyAt || 0) + 1; storyCard(); }
          break;
        case "create-name": {
          const n = document.getElementById("create-name"), m = document.getElementById("create-move");
          document.activeElement?.blur?.(); // 手機的鍵盤先在這一下收起，不要等換頁那一刻才收、整頁再跳一次
          await mx("create_name", { name: n ? n.value.trim() : "", move: m ? m.value.trim() : "" }); break; // 立好了 mx 直接回修練頁
        }
        case "create-cancel": await mx("create_cancel"); break;
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
      formMsg(form, failText(e)); // 沒有訊息行的表單不受影響
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
