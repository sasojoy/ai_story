/* 天下大勢的網頁前端：畫面的狀態 S（點開了什麼、停在哪一頁）（全部拆包第 66 批從 app.js 切出來）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。殼的檔，/ 的 script 標籤由伺服器照 WEB_ORDER 生成。
 */
"use strict";

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
    shopTab: "shelf", // 店面（店面獨立介面設計第二節）：鐵匠鋪停在哪一頁（shelf 架上／forge 打造／rack 裝備庫〔淬煉與修 3.4 併進來；舊的 temper 當它〕／trade 素材）；進門停在架上
    shopPot: null, // 打造頁爐裡放了什麼：{ slot, kind, main, aux }（素材 id 或 null）；換了兵器防具那一頁從頭來，開爐成了清掉主輔料
    shopLine: null, // 這一爐會怎樣（/api/smith_line 回的那一份）；null 時照 shop.forge.line（空爐）
    shopReveal: null, // 剛出爐的那一件（/api/do/smith_forge 回的 forged）：麻布包著，點開才看；關掉出爐卡清掉
    shopOpened: false, // 出爐卡打開了沒（點了麻布）
    shopFiring: false, // 開爐等回應的那一下爐火竄高（減少動態效果的人不跑）
    shopMore: false, // 裝備庫頁按了「再列 N 件」
    shopHorse: null, // 馬市點著的那一間（馬的 id；待售那匹是「架:馬」）；null 照伺服器的 focus（你騎的，沒有馬就待售的）
    shopNote: null, // 鐵匠鋪素材頁、軍需帳上一下的結果那一句（升階出了什麼、捐了多少；素材與經濟 B6）；換頁、出店清掉
    shopBrew: null, // 打造頁點開的那一格灰格（鐵匠鋪與合成流程 3.3）：{ attr, tier }，那一排底下彈熬的小單；熬了、取消、出店清掉
    rackPick: {}, // 裝備庫勾了要拆的（3.4）：裝備 id → true；送出、出店清掉，畫的時候只認現在列上拆得了的
    divinePick: null, // 神器頁收藏冊點著的那一格（3.8，配方 id）：底下翻出神器譜那一行；再點、換頁、出店收起
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
    mallTab: "shelf", // 停在哪一頁（shelf 貨架／look 形象／log 紀錄）；每次打開從貨架來
    mallLooks: null, // 形象那一頁（/api/looks）
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
    adminPage: onAdminPath(), // 網址是 /admin：畫管理頁（admin.js）；不是管理者就回江湖、網址換回 /
    adResult: null, // 管理頁最近一件做完的事 {text, ok}（釘在畫面底下）
    adAccounts: null, // 管理頁重設密碼「找」到的帳號 [{login, character}]；null 是還沒找
    adResetTarget: "", // 重設密碼那一格填的（找、點選之後重畫照樣在）
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
