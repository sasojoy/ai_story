/* 天下大勢的網頁前端：商城（萬寶閣；功能包 tianxia/features/mall/，開發規範手冊 3.7 第 1 階切出來的示範）。說明見 app.js 檔頭。
 *
 * 那一層（貨架、紀錄、購買確認）、入口（齒輪旁的錠子鈕、底部第六格）、江湖頁的「月卡・今日份」、設定頁的易名帖、管理者區的查帳與補發扣回退款。
 * 跟 main.js、map.js、outing.js 一樣是一般的 <script>：頂層的名字同在一個全域裡，index.html 排在 app.js 前面；
 * 開合、輪詢、點擊的分派與店面的框（shopHtml）照舊在 app.js（殼），這裡只有商城自己的畫面與動作。
 */
"use strict";

  // 商城的兩個入口（齒輪旁的錠子鈕、底部第六格）：出師後才出現（FB-490，docs/guide/商城.md）。草廬裡照序章的 reveal 藏著（tab:mall 或 all 才出來）；
  // 出了草廬、初入江湖那四步就在：m.onboard 的 reveal 是前幾步的聯集、不會有 all，照 shown() 會等到四步走完才出現
  const mallShown = () => { const p = pro(); return !!(S.main && S.main.mall) && (!p || p.reveal.includes("all") || p.reveal.includes("tab:mall")); };

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
    // （這一段在修練頁到輿圖之間：不用單字母 x，tests/server/test_server.py 會把 x 讀的欄位當成 menxia_view 的欄位查）
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

