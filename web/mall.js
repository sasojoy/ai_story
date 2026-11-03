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
    look: "擂台上穿哪一套，在這兒換。買過的換季也帶著走。",
  };
  const MALL_NOTE = "封閉測試先發每個帳號 {n} 元寶，正式開服時清空重來。"; // 貨架底下那一句（封測有發才寫）；待 joy 潤
  const MALL_LOG_NOTE = "只記這個帳號的元寶進出。"; // 待 joy 潤
  // 購買確認：上一筆同一件送出去沒等到回音、貨架也還沒變（不知道成了沒），這一次照同一個編號再送（FB-491）；待 joy 潤
  const MALL_AGAIN = "上一筆「{name}」還沒等到回音：這一次照同一筆再送，已經買好了就不會扣兩次。";
  const MALL_TABS = [["shelf", "貨架"], ["look", "形象"], ["log", "紀錄"]]; // 形象那一頁：貨架上有形象（d.looks）才有這一格
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
    S.mallOpen = false; S.mallTab = "shelf"; S.mallData = null; S.mallLog = null; S.mallLooks = null; S.mallSay = null; S.mallPick = null; S.mallPending = null; S.mallFail = false;
    S.adMall = null; S.adMallName = ""; S.adMallNote = ""; S.adMallMsg = ""; S.adMallOk = false;
    S.lookShow = null; S.moveShow = null; S.movePreview = null; S.mallCat = "all"; S.lookSub = ""; lookReset();
  }

  // 交給 shopHtml 的那一份：招牌、掌櫃那一句（剛買成了的、買不了的原因蓋過平常那一句）、餘額（紀錄頁照紀錄那一份，其餘照貨架、還沒抓到照狀態列）
  function mallShop() {
    const tab = S.mallTab === "log" || S.mallTab === "look" ? S.mallTab : "shelf";
    const d = tab === "log" ? S.mallLog : tab === "look" ? S.mallLooks : S.mallData;
    const say = S.mallSay;
    const balance = d && d.balance != null ? d.balance : S.mallData ? S.mallData.balance : ((S.main && S.main.mall) || {}).balance; // 形象那一頁沒有餘額：照貨架
    return {
      shop: "mall", sign: MALL_SIGN, tab, balance,
      line: say ? say.text : !d && !S.mallFail ? MALL_SAY.loading : MALL_SAY[tab],
      said: say ? (say.ok ? "said ok" : "said no") : "",
    };
  }

  function mallHtml(shop) {
    const body = shop.tab === "log" ? mallLogHtml(S.mallLog) : shop.tab === "look" ? mallLooksHtml(S.mallLooks) : mallShelfHtml(S.mallData);
    const tabs = MALL_TABS.filter(([k]) => k !== "look" || (S.mallData && S.mallData.looks));
    return `<div class="shop-body mall-body"><div class="shop-col">${body}</div></div>
      <nav class="shop-tabs">${tabs.map(([k, name]) => `<button class="shop-tab${shop.tab === k ? " on" : ""}" data-act="mall-tab" data-tab="${k}">${name}</button>`).join("")}</nav>`;
  }

  // 沒拿到資料：還在抓什麼都不畫（掌櫃那一句寫翻帳中），連不上畫一句與「再試一次」
  function mallFailHtml() {
    return S.mallFail ? `<p class="shop-empty">${esc(MALL_SAY.fail)}</p><button class="btn small ghost" data-act="mall-retry">再試一次</button>` : "";
  }

  // 貨架（Joy 2026-11-03「很陽春沒有萬寶閣的感覺」，示意稿 https://claude.ai/artifact/RGK1XzqCJ31VM3U8SaAeok「新・貨架」）：
  // 上面一塊招牌（燈籠、匾額、一句），兩張小卡（手上幾顆丹、今天還能服幾顆；月卡到哪天、一天最多服幾顆），一排分類，
  // 底下照分類一段一段：月卡一張大卡、其餘兩件一排，每件上面一格圖（還沒有畫好的圖先用 MALL_ART 的線稿）。形象、絕招不擺貨架，
  // 擺在「形象」那一頁，貨架最底一張卡連過去。買不了的畫淡、照樣點得到（點了掌櫃講原因）
  const MALL_MOTTO = "奇珍異寶・童叟無欺"; // 招牌底下那一句；待 joy 潤
  const MALL_CATS = [["all", "全部"], ["card", "月卡"], ["dan", "丹藥"], ["tie", "江湖帖"], ["zhuan", "列傳"]];
  const MALL_CAT_NOTE = { dan: (p) => `一顆${esc(p.name)}回 ${p.restore | 0} 點體力`, zhuan: () => "休季時寫你這一季" };
  // 一件歸哪一類：照它給的東西（伺服器的 gives）。月卡是月卡；丹與破境丹是丹藥；列傳那幾樣（zhuan_ 開頭）是列傳；其餘（易名帖、
  // 重悟帖、題壁墨、藏經匣……）是江湖帖。形象（kind look）不在貨架
  function mallCat(it) {
    const keys = Object.keys(it.gives || {});
    if (it.kind === "card") return "card";
    if (keys.some((k) => k === "pills" || k === "legend")) return "dan";
    if (keys.some((k) => k.startsWith("zhuan"))) return "zhuan";
    return "tie";
  }
  // 每一件的圖：畫好的放 web/img/mall/<id>.webp、id 列進 MALL_PICS；還沒畫的用一張線稿（照 id，沒有就照分類）
  const MALL_PICS = new Set(["card_30", "pills_5", "pills_30", "legend_1", "rename", "reroll_1", "inscribe_ink", "holding_15", "rewrite_zhuan", "zhuan_art", "zhuan_seal", "zhuan_quote"]); // Joy 2026-11-03 畫的
  const MALL_ART = {
    card_30: '<rect x="14" y="8" width="52" height="64" rx="6" fill="#b8352a" stroke="#f0cf7a" stroke-width="3"/><rect x="20" y="14" width="40" height="52" rx="3" fill="none" stroke="#f0cf7a" stroke-width="1.2" stroke-dasharray="3 2"/><circle cx="40" cy="36" r="13" fill="#f6d77f"/><circle cx="46" cy="32" r="11" fill="#b8352a"/><path d="M26 58h28" stroke="#f0cf7a" stroke-width="2"/>',
    pills_5: '<path d="M40 10c-6 0-9 4-9 8 0 3 2 5 2 7-8 3-14 11-14 21 0 13 10 22 21 22s21-9 21-22c0-10-6-18-14-21 0-2 2-4 2-7 0-4-3-8-9-8z" fill="#c79a4a" stroke="#f0cf7a" stroke-width="2"/><rect x="34" y="6" width="12" height="6" rx="2" fill="#b8352a"/><circle cx="16" cy="66" r="6" fill="#e04b33" stroke="#f6d77f" stroke-width="1.5"/><circle cx="64" cy="66" r="6" fill="#e04b33" stroke="#f6d77f" stroke-width="1.5"/><circle cx="58" cy="72" r="5" fill="#e04b33" stroke="#f6d77f" stroke-width="1.5"/>',
    pills_30: '<path d="M10 34h60v34a4 4 0 0 1-4 4H14a4 4 0 0 1-4-4z" fill="#7a3a1c" stroke="#f0cf7a" stroke-width="2"/><path d="M6 26h68v10H6z" fill="#9a4a24" stroke="#f0cf7a" stroke-width="2"/><circle cx="24" cy="24" r="6" fill="#e04b33" stroke="#f6d77f" stroke-width="1.5"/><circle cx="36" cy="20" r="6" fill="#e04b33" stroke="#f6d77f" stroke-width="1.5"/><circle cx="48" cy="23" r="6" fill="#e04b33" stroke="#f6d77f" stroke-width="1.5"/><circle cx="58" cy="18" r="6" fill="#e04b33" stroke="#f6d77f" stroke-width="1.5"/><circle cx="42" cy="12" r="6" fill="#e04b33" stroke="#f6d77f" stroke-width="1.5"/><rect x="32" y="46" width="16" height="14" fill="#b8352a"/>',
    legend_1: '<circle cx="40" cy="42" r="26" fill="#f6d77f" opacity=".25"/><circle cx="40" cy="42" r="17" fill="#e8b84d" stroke="#fff3c4" stroke-width="2"/><path d="M30 34l8 6-4 6 10 6" fill="none" stroke="#7a3a0c" stroke-width="2.5" stroke-linecap="round"/><path d="M40 8v8M40 68v8M8 42h8M64 42h8M17 19l6 6M57 59l6 6M63 19l-6 6M23 59l-6 6" stroke="#f6d77f" stroke-width="2" stroke-linecap="round"/>',
    rename: '<rect x="16" y="10" width="48" height="60" rx="3" fill="#b8352a" stroke="#f0cf7a" stroke-width="2"/><rect x="22" y="16" width="36" height="48" fill="none" stroke="#f0cf7a" stroke-width="1"/><text x="40" y="49" text-anchor="middle" font-size="26" font-weight="900" fill="#f6d77f">名</text>',
    reroll_1: '<rect x="12" y="22" width="56" height="36" fill="#efdcb2" stroke="#8a5a14" stroke-width="2"/><rect x="6" y="18" width="8" height="44" rx="3" fill="#7a3a1c" stroke="#f0cf7a" stroke-width="1.5"/><rect x="66" y="18" width="8" height="44" rx="3" fill="#7a3a1c" stroke="#f0cf7a" stroke-width="1.5"/><path d="M22 32h36M22 40h28M22 48h32" stroke="#5a3a1c" stroke-width="2"/><path d="M50 10c6 4 6 10 0 14" fill="none" stroke="#f6d77f" stroke-width="2"/>',
    inscribe_ink: '<rect x="14" y="40" width="34" height="12" rx="2" transform="rotate(-20 31 46)" fill="#222" stroke="#f0cf7a" stroke-width="1.5"/><path d="M56 10l6 4-14 40-6-2z" fill="#7a3a1c" stroke="#f0cf7a" stroke-width="1.5"/><path d="M42 52c-2 6 0 12 4 14 2-4 2-10-4-14z" fill="#111"/><ellipse cx="34" cy="68" rx="20" ry="4" fill="#000" opacity=".4"/>',
    holding_15: '<path d="M10 30l30-12 30 12v34L40 76 10 64z" fill="#6a3a1c" stroke="#f0cf7a" stroke-width="2"/><path d="M10 30l30 12 30-12M40 42v34" fill="none" stroke="#f0cf7a" stroke-width="2"/><rect x="34" y="50" width="12" height="10" rx="2" fill="#d9a441"/>',
    rewrite_zhuan: '<path d="M8 18c10-4 22-4 32 2v48c-10-6-22-6-32-2z" fill="#efdcb2" stroke="#8a5a14" stroke-width="2"/><path d="M72 18c-10-4-22-4-32 2v48c10-6 22-6 32-2z" fill="#e5cf9f" stroke="#8a5a14" stroke-width="2"/><path d="M60 6l6 4-16 34-4-2z" fill="#3a1d08" stroke="#f0cf7a" stroke-width="1.2"/>',
    zhuan_art: '<rect x="10" y="14" width="60" height="52" fill="#efdcb2" stroke="#d9a441" stroke-width="3"/><path d="M14 60l16-24 10 12 8-10 18 22z" fill="#4a5a52"/><circle cx="56" cy="28" r="6" fill="#b8352a"/>',
    zhuan_seal: '<rect x="28" y="8" width="24" height="30" rx="6" fill="#9a6a3a" stroke="#f0cf7a" stroke-width="2"/><rect x="18" y="36" width="44" height="18" rx="3" fill="#7a4a2a" stroke="#f0cf7a" stroke-width="2"/><rect x="20" y="58" width="40" height="16" fill="#b8352a"/><path d="M28 62h8v8h-8zM44 62h8v8h-8z" fill="#f3e6cc"/>',
    zhuan_quote: '<rect x="10" y="22" width="60" height="40" fill="#efdcb2" stroke="#8a5a14" stroke-width="2"/><path d="M10 22l30 22 30-22" fill="none" stroke="#8a5a14" stroke-width="2"/><circle cx="40" cy="46" r="7" fill="#b8352a"/><path d="M20 70h40" stroke="#f0cf7a" stroke-width="2"/>',
  };
  const MALL_ART_CAT = { card: "card_30", dan: "pills_5", tie: "rename", zhuan: "rewrite_zhuan" };
  function mallPicHtml(it) {
    if (MALL_PICS.has(it.id)) return `<span class="mall-pic has-img"><img src="/static/img/mall/${esc(it.id)}.webp" alt="" loading="lazy"></span>`;
    const art = MALL_ART[it.id] || MALL_ART[MALL_ART_CAT[mallCat(it)]];
    return `<span class="mall-pic"><svg viewBox="0 0 80 80" aria-hidden="true">${art}</svg></span>`;
  }
  function mallHeroHtml() {
    return `<div class="mall-hero"><span class="lantern" aria-hidden="true"></span><span class="plaque">${esc(MALL_SIGN)}</span><span class="lantern" aria-hidden="true"></span>
      <p class="motto">${esc(MALL_MOTTO)}</p></div>`;
  }
  function mallShelfHtml(d) {
    if (!d) return mallFailHtml();
    const p = d.pills;
    const status = `<div class="mall-status">
        <div><b>${esc(p.name)} ${p.count | 0} 顆</b>${p.today == null ? "每天不限" : `今天還能服 ${p.today | 0} 顆`}</div>
        <div><b>月卡 ${d.card ? `到 ${esc(d.card.until)}` : "還沒開"}</b>${p.cap > 0 ? `每天最多服 ${p.cap | 0} 顆` : "每天不限"}${mallDailyHtml(d.card)}</div></div>`;
    const items = d.items.filter((it) => it.kind !== "look");
    const cats = MALL_CATS.filter(([k]) => k === "all" || items.some((it) => mallCat(it) === k));
    const cat = cats.some(([k]) => k === S.mallCat) ? S.mallCat : "all";
    const chips = cats.length > 2 ? `<div class="mall-cats" role="tablist">${cats.map(([k, name]) =>
      `<button class="mall-cat${cat === k ? " on" : ""}" role="tab" aria-selected="${cat === k}" data-act="mall-cat" data-cat="${k}">${name}</button>`).join("")}</div>` : "";
    const section = ([k, name]) => {
      const list = items.filter((it) => mallCat(it) === k);
      if (!list.length || (cat !== "all" && cat !== k)) return "";
      const note = MALL_CAT_NOTE[k] ? `<small>${MALL_CAT_NOTE[k](p)}</small>` : "";
      return `<div class="mall-sub">${name}${note}</div>${k === "card" ? list.map(mallCardHtml).join("") : `<div class="mall-grid">${list.map(mallTileHtml).join("")}</div>`}`;
    };
    const looks = d.looks && (cat === "all") ? `<button class="mall-to-look" data-act="mall-tab" data-tab="look">形象與絕招在「形象」那一頁 ›</button>` : "";
    const empty = items.length ? "" : `<p class="shop-empty">${esc(MALL_SAY.empty)}</p>`;
    const note = d.grant > 0 ? `<p class="mall-note">${nbHtml(MALL_NOTE.replace("{n}", String(d.grant | 0)), MALL_NB)}</p>` : "";
    return mallHeroHtml() + status + chips + MALL_CATS.slice(1).map(section).join("") + looks + empty + note;
  }

  // 一件一張卡：上面一格圖，底下名字、給什麼（伺服器的 effects）、限購，最底一條金色的價錢（整張是一顆鈕，價錢那一條只是長得像鈕）
  function mallTileHtml(it) {
    const cls = `mall-item${it.can ? "" : " off"}${S.mallPick === it.id ? " on" : ""}`;
    return `<button class="${cls}" data-act="mall-pick" data-id="${esc(it.id)}"${it.can ? "" : ' aria-disabled="true"'}>
        ${mallPicHtml(it)}<span class="mi"><b>${esc(it.name)}</b>${it.effects ? `<span class="gain">${nbHtml(it.effects, MALL_NB)}</span>` : ""}
        ${it.limit ? `<small>${nbHtml(it.limit, MALL_NB)}</small>` : ""}</span>
        <span class="price">${ingotSvg()}${it.price | 0}</span></button>`;
  }

  // 月卡：一張金框大卡，圖、名字、限購，好處一條一格（兩欄），最底一條價錢
  function mallCardHtml(it) {
    const cls = `mall-card${it.can ? "" : " off"}${S.mallPick === it.id ? " on" : ""}`;
    return `<button class="${cls}" data-act="mall-pick" data-id="${esc(it.id)}"${it.can ? "" : ' aria-disabled="true"'}>
        <span class="mc-head">${mallPicHtml(it)}<span class="mt"><b>${esc(it.name)}</b>${it.limit ? `<span>${nbHtml(it.limit, MALL_NB)}</span>` : ""}</span></span>
        ${perks(it)}${!(it.perks || []).length && it.note ? `<span class="mc-note">${nbHtml(it.note, MALL_NB)}</span>` : ""}
        <span class="price">${ingotSvg()}${it.price | 0}　買下${esc(it.name)}</span></button>`;
  }

  // 月卡的好處（萬寶閣販賣清單定案，Joy 2026-10-21；字是伺服器 mall.perks 寫的），一條一格。卡本身是一顆鈕，裡面不能再放鈕：用 span
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
        <span>${esc(line.time)}${line.season_time ? `（${esc(line.season_time)}）` : ""}${line.item ? `・${esc(line.reason)}` : ""}${line.note ? `・${esc(line.note)}` : ""}</span><span class="bal">餘 ${line.balance | 0}</span></div>`;
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
    S.mallTab = tab === "log" || tab === "look" ? tab : "shelf";
    S.mallSay = null; S.mallPick = null; S.mallFail = false; S.lookSub = "";
    closeAsk();
    renderMall(false);
    if (S.mallTab === "log") await loadMallLog(); // 紀錄每次切過去都重抓（別的分頁買的、管理者補的）
    if (S.mallTab === "look") await loadLooks();
  }

  // ── 擂台形象（功能包 tianxia/features/looks/；Joy 2026-10-31）：萬寶閣「形象」那一頁。每一套一張卡：站著的那一格當預覽、名字、
  // 說明；穿著的寫「穿著」，買了的一顆「換上」，沒買的一顆「買（價錢）」（點了跟貨架同一條購買確認）。預設的斗笠小子永遠在最前 ──
  // 官方的在 /static/img/looks/<id>/，自建的（u<數字>）由伺服器從資料庫旁邊送（/api/looks/img/<id>/<張>）
  const LOOK_VER = () => (window.LOOKS_VER ? `?v=${window.LOOKS_VER}` : "");
  const LOOK_IMG = (id) => (/^u\d+$/.test(id || "") ? `/api/looks/img/${id}/hero_bare_idle${LOOK_VER()}`
    : /^[a-z0-9_]+$/.test(id || "") ? `/static/img/looks/${id}/hero_bare_idle.webp` : "/static/img/arena/hero_bare_idle.webp");
  function lookFaceHtml(id) { // 站著那張的第一格（四格一張、880×220）裁成一個人
    return `<span class="look-face" aria-hidden="true" style="background-image:url('${LOOK_IMG(id)}')"></span>`;
  }
  // 形象那一頁（Joy 2026-11-03「形象頁那邊的排版也是亂七八糟」「建立了一大堆形象跟絕招…會變得很難用」，示意稿「新・形象頁」）：
  // 最上面一塊台子站著點了的那一套（沒點就是身上穿的），台子上「看動作」與換上／價錢；底下分三頁（我的／官方／市集），
  // 我的再用小標籤篩（官方、自建、市集買的）；每套一張小格、一排三格，一次最多 LOOK_PAGE 格，多的按「再看」。最底一張絕招連過去。
  // 自建形象、絕招各自一頁（S.lookSub），左上回形象
  const LOOKSUB_NAMES = { make: "自建形象", move: "絕招" };
  const LOOK_PAGE = 18;
  const LOOK_SEGS = [["mine", "我的"], ["shop", "官方"], ["market", "市集"]];
  const LOOK_FILTERS = [["all", "全部"], ["official", "官方"], ["made", "自建"], ["bought", "市集買的"]];
  const lookKind = (lk) => (lk.mine ? "made" : /^u\d+$/.test(lk.id) ? "bought" : "official");
  function mallLooksHtml(d) {
    if (!d) return mallFailHtml();
    if (S.lookSub === "make" && d.order) return lookSubHtml("make", lookShowHtml() + lookOrderHtml(d.order, d));
    if (S.lookSub === "move" && d.moves) return lookSubHtml("move", moveHtml(d.moves));
    const shelf = (S.mallData && S.mallData.items) || [];
    const market = (d.market && d.market.shelf) || [];
    const mine = d.looks.filter((lk) => lk.owned);
    const shop = d.looks.filter((lk) => !lk.owned);
    const lists = { mine, shop, market };
    const seg = LOOK_SEGS.some(([k]) => k === S.lookSeg) && (S.lookSeg !== "market" || d.market) ? S.lookSeg : "mine";
    // 台子：點了的那一套（三頁裡找），沒點就是身上穿的
    const pick = d.looks.find((lk) => lk.id === S.lookPick) || market.find((x) => x.look === S.lookPick) || d.looks.find((lk) => lk.id === d.worn) || d.looks[0];
    const stage = pick ? lookStageHtml(pick, d, shelf) : "";
    const filters = LOOK_FILTERS.filter(([k]) => k === "all" || mine.some((lk) => lookKind(lk) === k));
    const filter = seg === "mine" && filters.some(([k]) => k === S.lookFilter) ? S.lookFilter : "all";
    const shown = seg === "mine" ? mine.filter((lk) => filter === "all" || lookKind(lk) === filter) : lists[seg];
    const limit = Math.max(LOOK_PAGE, S.lookLimit | 0);
    const tile = (x) => {
      const id = x.look || x.id, on = id === d.worn, sel = pick && id === (pick.look || pick.id);
      const tag = x.look ? `<span class="look-tag2">${x.price | 0}</span>` : lookKind(x) === "made" ? `<span class="look-tag2">自建</span>`
        : lookKind(x) === "bought" ? `<span class="look-tag2">市集</span>` : !x.owned && x.item ? `<span class="look-tag2">${(shelf.find((one) => one.id === x.item) || {}).price | 0}</span>` : "";
      return `<button class="look-tile${on ? " on" : ""}${sel ? " sel" : ""}" data-act="look-pick" data-id="${esc(id)}" aria-pressed="${!!sel}">
          <span class="look-pad">${lookFaceHtml(id)}${on ? `<span class="look-tag">穿著</span>` : ""}${tag}</span><b>${esc(x.name)}</b></button>`;
    };
    const o = d.order;
    const make = seg === "mine" && o ? `<button class="look-tile look-make" data-act="look-sub" data-sub="make"><span class="look-pad"><span class="plus" aria-hidden="true">＋</span></span>
        <b>${o.open ? "有一套在畫" : "自建一套"}</b></button>` : "";
    const empty = !shown.length && !make ? `<p class="mall-note">${seg === "market" ? "別的玩家自建、上架的形象會擺在這裡。現在還沒有人上架。" : seg === "shop" ? "官方的形象你都有了。" : "這一類還沒有。"}</p>` : "";
    const more = shown.length > limit ? `<button class="btn ghost look-more" data-act="look-more">再看 ${Math.min(LOOK_PAGE, shown.length - limit)} 套（還有 ${shown.length - limit} 套）</button>` : "";
    const segs = `<div class="look-segs" role="tablist">${LOOK_SEGS.filter(([k]) => k !== "market" || d.market).map(([k, name]) =>
      `<button class="${seg === k ? "on" : ""}" role="tab" aria-selected="${seg === k}" data-act="look-seg" data-seg="${k}">${name} ${lists[k].length}</button>`).join("")}</div>`;
    const chips = seg === "mine" && filters.length > 2 ? `<div class="mall-cats">${filters.map(([k, name]) =>
      `<button class="mall-cat${filter === k ? " on" : ""}" data-act="look-filter" data-filter="${k}">${name}</button>`).join("")}</div>` : "";
    return `${stage}${lookShowHtml()}${segs}${chips}<div class="look-tiles">${make}${shown.slice(0, limit).map(tile).join("")}</div>${empty}${more}${moveEntryHtml(d.moves)}`;
  }
  // 台子：大的那一張、這一套是什麼（穿著中／官方／自建／市集買的／誰做的）、名字、看動作，與換上／穿著中／價錢（官方的走貨架同一條購買確認，市集的先問一次）
  function lookStageHtml(x, d, shelf) {
    const id = x.look || x.id, on = id === d.worn;
    const what = x.look ? `${esc(x.seller)}做的・市集` : { made: "自建", bought: "市集買的", official: "官方" }[lookKind(x)];
    const it = !x.look && !x.owned && x.item ? shelf.find((one) => one.id === x.item) : null;
    const act = on ? `<span class="look-on">穿著中</span>`
      : x.look ? `<button class="btn small buy" data-act="market-buy" data-id="${esc(id)}" data-name="${esc(x.name)}" data-price="${x.price | 0}">${ingotSvg()}${x.price | 0}</button>`
      : x.owned ? `<button class="btn small primary" data-act="look-wear" data-id="${esc(id)}">換上</button>`
      : it ? `<button class="btn small buy" data-act="mall-pick" data-id="${esc(it.id)}">${ingotSvg()}${it.price | 0}</button>` : "";
    return `<div class="look-stage">${lookFaceHtml(id)}<div class="look-stage-bar"><span><small>${what}</small><b>${esc(x.name)}</b></span>
        ${lookShowBtn(id, x.name)}${act}</div></div>${x.note ? `<p class="mall-note look-stage-note">${esc(x.note)}</p>` : ""}`;
  }
  // 自建形象、絕招那一頁的頂上：回形象一顆、標題；自建形象多一排四步（走到哪一步亮到哪）
  const LOOKSUB_STEPS = ["寫樣子", "畫坊作畫", "審核", "進「我的」"];
  function lookSubHtml(sub, body) {
    const o = S.mallLooks && S.mallLooks.order;
    const at = o && (o.list || []).some((x) => x.status === "review") ? 3 : o && o.open ? 2 : 1;
    const steps = sub === "make" ? `<ol class="look-steps">${LOOKSUB_STEPS.map((t, i) => `<li class="${i < at ? "on" : ""}"><span>${"一二三四"[i]}</span>${t}</li>`).join("")}</ol>` : "";
    return `<div class="look-subbar"><button class="btn small ghost" data-act="look-sub" data-sub="">‹ 形象</button><b>${LOOKSUB_NAMES[sub]}</b></div>${steps}${body}`;
  }
  // 形象頁最底那一張絕招：身上穿哪一招、招式庫幾招，按了進絕招那一頁
  function moveEntryHtml(m) {
    if (!m) return "";
    const n = (m.library || []).length;
    const say = !m.has_art && !n ? "先練一門自己合成或自創的武功，才能替它畫招式。" : "換招、寫新的一招都在這裡";
    return `<div class="mall-sub">絕招<small>${n ? `招式庫 ${n} 招` : "擂台上演出來"}</small></div>
      <button class="move-entry" data-act="look-sub" data-sub="move"><span class="move-ico" aria-hidden="true"></span>
        <span><b>${m.worn ? `身上穿著「${esc(m.worn)}」` : "身上沒穿絕招"}</b><small>${say}</small></span><span class="go" aria-hidden="true">›</span></button>`;
  }
  // 看動作（Joy 2026-11-01「已經做好的形象跟絕招也要能展示」）：按了在格子上面那塊畫布把這一套十張一張一張演（arena_scene.js 的 lookShow）
  const lookShowBtn = (id, name) => `<button class="btn small ghost look-show-btn" data-act="look-show" data-id="${esc(id)}" data-name="${esc(name)}">看動作</button>`;
  function lookShowHtml() {
    const v = S.lookShow;
    if (!v) return "";
    return `<div class="look-show"><canvas id="look-show" class="scene-preview" width="720" height="320" aria-label="「${esc(v.name)}」的動作"></canvas>
      <div class="row"><b>${esc(v.name)}</b><button class="btn small ghost" data-act="look-show" data-id="">收起</button></div></div>`;
  }
  function lookShowTo(id, name) {
    S.lookShow = id === "" || (S.lookShow && S.lookShow.id === id) ? null : { id, name };
    if (S.mallOpen) renderMall();
    if (S.lookShow && typeof lookShow === "function") lookShow(S.lookShow.id);
  }
  // 自建形象（第二批；Joy 2026-11-03 要完整流程、要裝得下很多，示意稿「自建形象」）：正在畫的那一張（一次一張，撤得回來）；
  // 沒有在畫才有「寫一套」（名字、一句樣子、想不到就點、下單）；做好的直接進形象頁「我的」，這裡只管市集上架（總共賣了幾份、
  // 入帳多少、押著多少；掛著的排前面，沒掛的摺起來，按「掛上去」才跳出定價）；退回的摺起來，留最新一張（改一改再送）
  const LOOK_ORDER_NOTE = "畫好、審過就放進「我的」。沒通過的話，元寶全部退回。"; // 待 joy 潤
  const LOOK_EXAMPLES = ["白衣書生，背著竹簍", "黑甲將軍，手持長槍", "紅衣女刀客"]; // 想不到就點；待 joy 潤
  const MOVE_EXAMPLES = ["一劍寒光九萬里", "背後出現一座大佛擊出一掌", "巨掌從天而降"];
  const exampleHtml = (list, target) => `<div class="look-ex"><span>想不到就點：</span>${list.map((t) =>
    `<button class="btn small ghost" data-act="prompt-ex" data-for="${target}" data-text="${esc(t)}">${esc(t)}</button>`).join("")}</div>`;
  const waitIcon = '<span class="look-wait" aria-hidden="true"></span>';
  function lookOrderHtml(o, d) {
    if (!o) return "";
    const list = o.list || [];
    const open = list.filter((x) => x.status === "pending" || x.status === "review");
    const drawing = open.map((x) => `<div class="look-line wait">${waitIcon}<span class="lo-main"><b>${esc(x.name)}</b>
        <small>${x.status === "review" ? "圖畫好了，等看過就放進「我的」。" : "畫好會通知你，可以先去忙。"}</small></span>
        <span class="look-st st-${esc(x.status)}">${esc(x.status_text)}</span>${withdrawBtn(x, "look", x.name)}</div>`).join("");
    const form = o.open ? "" : `<div class="mall-sub">寫一套</div><div class="look-order-form">
        <label for="look-name">名字（${o.name_max | 0} 字內）</label><input class="input" id="look-name" maxlength="${o.name_max | 0}" autocomplete="off" value="${esc(S.lookDraft ? S.lookDraft.name : "")}">
        <label for="look-prompt">長什麼樣子（${o.prompt_max | 0} 字內）</label><textarea class="input" id="look-prompt" maxlength="${o.prompt_max | 0}" rows="3">${esc(S.lookDraft ? S.lookDraft.prompt : "")}</textarea>
        ${exampleHtml(LOOK_EXAMPLES, "look-prompt")}
        <button class="btn primary buy" data-act="look-order">${ingotSvg()}${o.price | 0}　下單</button><p class="mall-note">${esc(LOOK_ORDER_NOTE)}</p></div>`;
    const rejected = list.filter((x) => x.status === "rejected").reverse();
    const rej = (x) => `<div class="look-line no"><span class="look-no" aria-hidden="true">✕</span><span class="lo-main"><b>${esc(x.name)}</b>
        <small>${x.reason ? `${esc(x.reason)}・` : ""}${o.price | 0} 元寶已退</small></span>
        ${o.open ? "" : `<button class="btn small ghost" data-act="look-redo" data-id="${x.id | 0}">改一改再送</button>`}</div>`;
    const rejs = rejected.length ? `<div class="mall-sub">退回的<small>${rejected.length} 張</small></div><div class="look-lines">${rejected.slice(0, S.lookRejAll ? rejected.length : 1).map(rej).join("")}
        ${rejected.length > 1 && !S.lookRejAll ? `<button class="look-fold" data-act="look-fold" data-what="rej">看更早的 ${rejected.length - 1} 張 ▾</button>` : ""}</div>` : "";
    return `${drawing ? `<div class="mall-sub">正在畫<small>一次一張</small></div><div class="look-lines">${drawing}</div>` : ""}${form}
      ${lookSellHtml(d && d.market, list.filter((x) => x.status === "made"))}${rejs}`;
  }
  // 市集上架：做好的那幾套一行一套，掛著的排前面、沒掛的摺起來；按「掛上去」那一行才跳出定價框
  function lookSellHtml(m, made) {
    if (!m || !made.length) return "";
    const price = (look) => ((m.mine || []).find((one) => one.look === look) || {}).price;
    const rows = made.map((x) => ({ x, look: `u${x.id | 0}`, p: price(`u${x.id | 0}`) })); // 自建的一套就是 u<購買 id>（orders.look_id）
    const on = rows.filter((r) => r.p != null), off = rows.filter((r) => r.p == null);
    const pct = Math.round((m.share || 0) * 100);
    const row = (r) => `<div class="look-line"><span class="look-pad">${lookFaceHtml(r.look)}</span><span class="lo-main"><b>${esc(r.x.name)}</b>
        <small>${r.p != null ? `掛著・一份 ${r.p | 0}` : "沒掛"}</small></span>
        ${r.p != null ? `<button class="btn small ghost" data-act="market-unlist" data-id="${esc(r.look)}">撤下</button>`
          : S.lookSell === r.look ? "" : `<button class="btn small" data-act="look-sell" data-id="${esc(r.look)}">掛上去</button>`}
        ${S.lookSell === r.look && r.p == null ? `<span class="market-set"><label for="market-price-${esc(r.look)}">定價</label>
          <input class="input" type="number" id="market-price-${esc(r.look)}" min="${m.min | 0}" max="${m.max | 0}" value="${m.default | 0}">
          <button class="btn small primary" data-act="market-list" data-id="${esc(r.look)}">掛上去</button></span>` : ""}</div>`;
    const shown = S.lookSellAll ? rows : on.concat(off.filter((r) => r.look === S.lookSell));
    const folded = off.length - (S.lookSellAll ? off.length : off.filter((r) => r.look === S.lookSell).length);
    return `<div class="mall-sub">市集上架<small>${made.length} 套做好的・${on.length} 套掛著</small></div>
      <div class="look-stats"><span><small>賣出</small><b>${m.sold | 0} 份</b></span><span><small>已入帳</small><b>${m.paid | 0}</b></span><span><small>押著</small><b>${m.held | 0}</b></span></div>
      <div class="look-lines">${(S.lookSellAll ? on.concat(off) : shown).map(row).join("")}
        ${folded > 0 ? `<button class="look-fold" data-act="look-fold" data-what="sell">還有 ${folded} 套沒掛　展開 ▾</button>` : ""}</div>
      <p class="mall-note">${m.min | 0}～${m.max | 0} 元寶。賣出一份你拿 ${pct}%，押 ${m.hold_days | 0} 天才入帳。</p>`;
  }
  // 撤回自己還沒上架的單（Joy 2026-11-02「審圖卡住，玩家也不能退回，會被卡死」）：等圖、審核中都能撤，元寶全退；先問一次
  const withdrawBtn = (x, kind, name) => (x.withdraw
    ? `<button class="btn small ghost" data-act="look-withdraw" data-kind="${kind}" data-id="${x.id | 0}" data-name="${esc(name)}">撤回</button>` : "");
  function lookWithdrawAsk(el) {
    const kind = el.dataset.kind === "move" ? "move" : "look", id = Number(el.dataset.id) || 0;
    ask(`撤回「${el.dataset.name || ""}」？元寶全退，已經畫好的圖不留。`, "撤回", () => lookWithdraw(id, kind));
  }
  async function lookWithdraw(id, kind) {
    await busy(async () => {
      const r = await api("/api/looks/withdraw", { id, kind });
      if (r.looks) S.mallLooks = r.looks;
      if (r.main) setMain(r.main);
      if (r.main && r.main.mall && S.mallData) S.mallData.balance = r.main.mall.balance;
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      S.mallSay = text ? { text, ok: !text.startsWith("（") } : null;
      renderTop();
      if (S.mallOpen) renderMall();
    });
  }
  function lookOrderAsk() {
    const name = (document.getElementById("look-name")?.value || "").trim();
    const prompt = (document.getElementById("look-prompt")?.value || "").trim();
    S.lookDraft = { name, prompt };
    if (!name || !prompt) { S.mallSay = { text: !name ? "先替這一套取個名字。" : "寫一句這一套長什麼樣子。", ok: false }; renderMall(); return; }
    const o = S.mallLooks && S.mallLooks.order;
    const ref = mallRef();
    ask(`花 ${o ? o.price | 0 : 0} 元寶下單自建形象「${name}」？審核沒過元寶全退。`, "下單", () => lookOrder(name, prompt, ref));
  }
  async function lookOrder(name, prompt, ref) {
    await busy(async () => {
      const r = await api("/api/looks/order", { name, prompt, ref });
      if (r.looks) S.mallLooks = r.looks;
      if (r.main) setMain(r.main);
      if (r.main && r.main.mall && S.mallData) S.mallData.balance = r.main.mall.balance; // 招牌旁的餘額照貨架那一份：當場換
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      const ok = !!(r.looks && r.looks.order && r.looks.order.open);
      if (ok) S.lookDraft = null;
      S.mallSay = text ? { text, ok } : null;
      renderTop();
      if (S.mallOpen) renderMall();
    });
  }
  // 招式動畫（第三批；Joy 2026-11-03 要完整流程、要裝得下很多，示意稿「絕招」）：最上面現在練哪一門、什麼打法、身上穿哪一招；
  // 正在畫的獨門一條（撤得回來）；招式庫照打法分頁（先開現在的打法），一招一行（演一次、換上／穿著）；「寫一招新的」平常收著
  // （招式庫空的就直接展開）：寫一句 → 先看看（伺服器把這一句變成導演稿，畫布照稿演，不扣元寶）→ 通用或獨門。
  // 每一季綁到一門武功上（同打法免費改綁）；擂台上出招時疊那一張光效。範例那一格是 /static/img/arena/fx_sample.webp 的第四格
  const MOVE_IMG = (id) => (/^m\d+$/.test(id || "") ? `/api/looks/img/${id}/fx${LOOK_VER()}` : "/static/img/arena/fx_sample.webp");
  const MOVE_STYLES = [["slash", "揮砍"], ["pole", "長兵"], ["fist", "拳腳"], ["shoot", "射"]];
  function moveFxHtml(id) { return `<span class="move-fx" aria-hidden="true" style="background-image:url('${MOVE_IMG(id)}')"></span>`; }
  function moveHtml(m) {
    if (!m) return "";
    const lib = m.library || [];
    const wornRow = lib.find((x) => x.worn);
    const now = !m.has_art ? `<p class="mall-note">先練一門自己合成或自創的武功，才能替它畫招式。</p>`
      : `<div class="move-now-card"><span><small>現在練的</small><b>${esc(m.art)}<em>・打法 ${esc(m.style_text)}</em></b><small>${m.worn ? `身上穿著「${esc(m.worn)}」` : "身上沒穿絕招"}</small></span>
          ${wornRow && wornRow.scene ? `<button class="btn small ghost" data-act="move-show" data-id="${esc(wornRow.move)}">${S.moveShow === wornRow.move ? "收起" : "演一次 ▶"}</button>` : ""}</div>`
        + (m.asleep_text ? `<p class="mall-note bad">${esc(m.asleep_text)}</p>` : "");
    const pending = (m.list || []).map((x) => `<div class="look-line ${x.status === "rejected" ? "no" : "wait"}">${x.status === "rejected" ? '<span class="look-no" aria-hidden="true">✕</span>' : waitIcon}
        <span class="lo-main"><b>${esc(x.prompt)}</b><small>${esc(x.art)}・${esc(x.style_text)}${moveArtsNote(x)}${x.reason ? `（${esc(x.reason)}）` : ""}</small></span>
        <span class="look-st st-${esc(x.status)}">${esc(x.status_text)}</span>${withdrawBtn(x, "move", x.art)}</div>`).join("");
    const show = S.moveShow ? `<canvas id="scene-preview" class="scene-preview" width="720" height="320" aria-label="絕招演一次"></canvas>` : "";
    // 招式庫：照打法分頁，先開現在的打法（沒有就開第一個有招的）；別的打法那一頁寫一句這一季演不出來
    const tabs = MOVE_STYLES.map(([k, name]) => [k, name, lib.filter((x) => x.style === k).length]);
    const tab = tabs.some(([k]) => k === S.moveTab) ? S.moveTab : (tabs.find(([k, , n]) => k === m.style && n) || tabs.find(([, , n]) => n) || [m.style])[0];
    const row = (x) => `<div class="look-line move-line${x.worn ? " on" : ""}"><span class="look-pad">${x.scene ? `<span class="move-fx move-seal" aria-hidden="true">絕</span>` : moveFxHtml(x.move)}</span>
        <span class="lo-main"><b>${esc(x.prompt)}</b><small>${esc(x.art)}</small></span>
        ${x.scene ? `<button class="btn small ghost play" data-act="move-show" data-id="${esc(x.move)}" aria-label="${S.moveShow === x.move ? "收起" : "演一次"}">${S.moveShow === x.move ? "■" : "▶"}</button>` : "<span></span>"}
        ${x.worn ? `<button class="btn small ghost" data-act="move-bind" data-id="0">脫下</button>`
          : x.wearable ? `<button class="btn small primary" data-act="move-bind" data-id="${x.id | 0}">換上</button>` : "<span></span>"}</div>`;
    const inTab = lib.filter((x) => x.style === tab);
    const library = lib.length ? `<div class="mall-sub">招式庫<small>共 ${lib.length} 招・換季也帶著走</small></div>
      <div class="look-segs" role="tablist">${tabs.map(([k, name, n]) => `<button class="${tab === k ? "on" : ""}" role="tab" aria-selected="${tab === k}" data-act="move-tab" data-tab="${k}">${name} ${n}</button>`).join("")}</div>
      ${tab !== m.style && m.has_art ? `<p class="mall-note">這一頁的招，這一季換回${esc((MOVE_STYLES.find(([k]) => k === tab) || [, ""])[1])}的兵器才演得出來。</p>` : ""}
      ${show}<div class="look-lines">${inTab.map(row).join("") || `<p class="mall-note">這一種打法還沒有招。</p>`}</div>` : show;
    // 寫一招新的：平常收著（招式庫空的直接展開）。獨門一次只能有一張在做（畫坊的量），那一格暫時灰掉，通用照樣買得到
    const formOpen = S.moveForm || !lib.length;
    const own = m.open ? `<span class="move-opt off"><b>獨門</b><small>還有一張獨門在畫：等它好了、或撤回，才能再下一張。</small></span>`
      : `<span class="move-opt own"><b>獨門</b><small>照你寫的另外畫，畫好審過才上身；沒過全退。</small>
          <button class="btn small primary buy" data-act="move-order">${ingotSvg()}${m.price | 0}</button></span>`;
    const form = !m.has_art || S.moveShow ? "" : !formOpen ? `<button class="btn primary buy move-new" data-act="move-form">＋ 寫一招新的</button>`
      : `<div class="move-form"><div class="mall-sub">寫一句<small>${m.prompt_max | 0} 字內・只能中文</small></div>
      <div class="look-order-form"><label for="move-prompt">這一招長什麼樣子</label><textarea class="input" id="move-prompt" maxlength="${m.prompt_max | 0}" rows="2">${esc(S.moveDraft || "")}</textarea>
        ${exampleHtml(MOVE_EXAMPLES, "move-prompt")}
        <button class="btn ghost" data-act="move-preview">先看看 ▶（不花錢）</button></div>${moveSceneHtml()}
      <div class="move-opts"><span class="move-opt"><b>通用</b><small>用現成的光效演，當場學成。</small>
          <button class="btn small buy" data-act="move-order" data-basic="1">${ingotSvg()}${m.price_basic | 0}</button></span>${own}</div>
      <p class="mall-note">${esc(m.order_style_note || "")}</p></div>`;
    return `${now}${pending ? `<div class="look-lines">${pending}</div>` : ""}${library}${form}`;
  }
  const moveArtsNote = (row) => { const need = row.arts || []; return need.length ? `・要畫「${esc(need.join("」「"))}」` : ""; }; // 一句話自創要畫的那幾樣
  // 先看看：伺服器把這一句變成導演稿（不扣元寶），在下面那塊畫布照稿演（arena_scene.js 的 scenePreview）
  function moveSceneHtml() {
    const p = S.movePreview;
    if (!p) return "";
    if (p.problem) return `<p class="mall-note bad">${esc(p.problem)}</p>`;
    const arts = (p.scene.arts || []).map((a) => a.label);
    const note = arts.length
      ? `獨門會畫「${arts.join("」「")}」：送出之後可以先去忙，畫好、審過才上身（這裡先用剪影演）。買通用的話這一樣改成一道光。`
      : "這一句沒有看得出形狀的東西：買通用的就好（獨門會退回來叫你換一句）。";
    return `<canvas id="scene-preview" class="scene-preview" width="720" height="320" aria-label="絕招預覽"></canvas><p class="mall-note">${esc(note)}</p>`;
  }
  // 招式庫裡做好了的那一招：照它的稿和畫好的圖演一次（同擂台；再按一次收起，回到下單的表單）
  async function moveShowTo(mid) {
    if (!mid || S.moveShow === mid) { S.moveShow = null; if (S.mallOpen) renderMall(); return; }
    const r = await api(`/api/looks/scene/${mid}`);
    if (!r || !r.scene) { S.mallSay = { text: "這一招演不出來，等一下再試。", ok: false }; if (S.mallOpen) renderMall(); return; }
    S.moveShow = mid; S.movePreview = null;
    if (S.mallOpen) renderMall();
    if (typeof scenePreview === "function") scenePreview(r.scene, mid);
  }
  async function movePreview() {
    const text = (document.getElementById("move-prompt")?.value || "").trim();
    S.moveDraft = text;
    const r = await api("/api/looks/scene", { text });
    S.movePreview = r && (r.scene || r.problem) ? r : { problem: "預覽不出來，等一下再試。" };
    // 預覽那一份要記住、下單時原樣帶回去（看到的＝做出來的）：不然伺服器會再問一次模型，
    // 兩次答案不同，玩家核准的跟真的畫出來的就不是同一份（#493：預覽說槍＋菊花，結果兩把槍）
    S.moveShown = r && r.draft ? { text, draft: r.draft } : null;
    if (S.mallOpen) renderMall();
    if (S.movePreview.scene && typeof scenePreview === "function") scenePreview(S.movePreview.scene);
  }
  function moveOrderAsk(basic) {
    const prompt = (document.getElementById("move-prompt")?.value || "").trim();
    S.moveDraft = prompt;
    const m = S.mallLooks && S.mallLooks.moves;
    if (!prompt) { S.mallSay = { text: "寫一句這一招長什麼樣子。", ok: false }; renderMall(); return; }
    const ref = mallRef();
    const price = (basic ? (m ? m.price_basic : 0) : (m ? m.price : 0)) | 0;
    const tail = basic ? "用現成的光效，當場學成。" : "照你寫的東西畫一張圖，送出之後可以先去忙；審核沒過元寶全退。";
    ask(`花 ${price} 元寶替「${m ? m.art : ""}」下單${basic ? "通用" : "獨門"}絕招？${tail}`, "下單", () => moveOrder(prompt, ref, basic));
  }
  async function moveOrder(prompt, ref, basic) {
    await busy(async () => {
      // 帶上預覽那一份（只有那一句一字沒改才算同一份；改過就讓伺服器重新問，不要拿舊的充數）
      const shown = S.moveShown && S.moveShown.text === prompt ? S.moveShown.draft : null;
      const r = await api("/api/looks/move", { prompt, ref, basic: !!basic, draft: shown });
      if (r.looks) S.mallLooks = r.looks;
      if (r.main) setMain(r.main);
      if (r.main && r.main.mall && S.mallData) S.mallData.balance = r.main.mall.balance;
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      const mv = r.looks && r.looks.moves;
      const ok = !!(mv && (mv.open || mv.bound)); // 要畫的在等圖、不用畫的當場學成（綁上了）
      if (ok) { S.moveDraft = null; S.movePreview = null; S.moveShown = null; }
      S.mallSay = text ? { text, ok } : null;
      renderTop();
      if (S.mallOpen) renderMall();
    });
  }
  async function moveBind(id) {
    await busy(async () => {
      const r = await api("/api/looks/bind", { id: Number(id) });
      if (r.looks) S.mallLooks = r.looks;
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      S.mallSay = text ? { text, ok: text.startsWith("換上") || text.startsWith("把「") } : null;
      if (S.mallOpen) renderMall();
    });
  }
  function lookMarketAsk(look, name, price) {
    const ref = mallRef();
    ask(`花 ${price | 0} 元寶買下市集上的「${name}」？`, "買", () => lookMarketDo({ op: "buy", look, ref }));
  }
  async function lookMarketList(look) { // 價錢照框裡寫的；讀不到框就照預設的
    const m = (S.mallLooks && S.mallLooks.market) || {};
    const price = Number((document.getElementById(`market-price-${look}`) || {}).value) || m.default || 0;
    await lookMarketDo({ op: "list", look, price });
  }
  async function lookMarketDo(body) {
    await busy(async () => {
      const r = await api("/api/looks/market", body);
      if (r.looks) S.mallLooks = r.looks;
      S.lookSell = null;
      if (r.main) setMain(r.main);
      if (r.main && r.main.mall && S.mallData) S.mallData.balance = r.main.mall.balance;
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      S.mallSay = text ? { text, ok: /^(買下了|「)/.test(text) } : null;
      renderTop();
      if (S.mallOpen) renderMall();
    });
  }
  async function loadLooks() {
    try {
      S.mallLooks = await api("/api/looks");
      S.mallFail = false;
    } catch (e) { S.mallFail = true; }
    if (S.mallOpen && S.mallTab === "look") renderMall();
  }
  async function lookWear(id) {
    await busy(async () => {
      const r = await api("/api/looks/wear", { look: id });
      if (r.looks) S.mallLooks = r.looks;
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      S.mallSay = text ? { text, ok: true } : null;
      if (S.mallOpen) renderMall();
    });
  }

  // 貨架的分類（全部／月卡／丹藥／江湖帖／列傳）：只換貨架、從頂上開始
  function mallCatTo(cat) {
    S.mallCat = MALL_CATS.some(([k]) => k === cat) ? cat : "all";
    S.mallPick = null; S.mallSay = null;
    renderMall(false);
  }
  // 從別的頁直接進萬寶閣的絕招那一頁（俠客頁武學卡「去綁招」）：style 給了就開那一種打法的招式庫分頁（slash/pole/fist/shoot）
  async function openMallMoves(style) {
    if (!S.main || !S.main.mall) return;
    S.mallOpen = true; S.mallTab = "look"; S.mallSay = null; S.mallPick = null; S.mallLog = null; S.mallFail = false;
    lookReset(); S.lookSub = "move"; S.lookShow = null; S.moveShow = null;
    if (MOVE_STYLES.some(([k]) => k === style)) S.moveTab = style;
    render();
    await Promise.all([loadMall(), loadLooks()]);
  }
  // 形象那一頁裡的自建形象、絕招那一頁（空字串回形象）：換頁時收起正在演的、從頂上開始
  function lookSubTo(sub) {
    S.lookSub = LOOKSUB_NAMES[sub] ? sub : "";
    S.lookShow = null; S.moveShow = null; S.mallSay = null;
    renderMall(false);
  }
  // 形象那一頁自己記的：點了哪一套、在哪一頁、篩哪一類、看了幾格、展開了什麼（換帳號、出店都清掉）
  function lookReset() {
    S.lookPick = null; S.lookSeg = "mine"; S.lookFilter = "all"; S.lookLimit = 0; S.lookSell = null; S.lookSellAll = false; S.lookRejAll = false;
    S.moveTab = null; S.moveForm = false;
  }
  function lookPickTo(id) { S.lookPick = id; S.lookShow = null; renderMall(); }
  function lookSegTo(seg) { S.lookSeg = seg; S.lookLimit = 0; S.lookShow = null; renderMall(); }
  function lookFilterTo(f) { S.lookFilter = f; S.lookLimit = 0; renderMall(); }
  function lookMore() { S.lookLimit = Math.max(LOOK_PAGE, S.lookLimit | 0) + LOOK_PAGE; renderMall(); }
  function lookFold(what) { if (what === "rej") S.lookRejAll = true; else S.lookSellAll = true; renderMall(); }
  function lookSellTo(look) { S.lookSell = S.lookSell === look ? null : look; renderMall(); }
  function moveTabTo(tab) { S.moveTab = tab; S.moveShow = null; renderMall(); }
  function moveFormOpen() { S.moveForm = true; renderMall(); }
  // 退回的那一張「改一改再送」：名字、樣子填回寫一套的框
  function lookRedo(id) {
    const o = S.mallLooks && S.mallLooks.order;
    const x = o && (o.list || []).find((one) => (one.id | 0) === (Number(id) | 0));
    if (x) S.lookDraft = { name: x.name, prompt: x.prompt };
    renderMall(false);
  }
  // 「想不到就點」：把那一句填進框裡（自建形象、絕招各一個框），草稿跟著記，重畫也還在
  function promptExample(target, text) {
    const box = document.getElementById(target);
    if (box) box.value = text;
    if (target === "move-prompt") S.moveDraft = text;
    else if (target === "look-prompt") S.lookDraft = { name: (document.getElementById("look-name")?.value || "").trim(), prompt: text };
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
    const inner = `
          <h4 id="ask-text">買下【${esc(it.name)}】${n > 1 ? `×${n}` : ""}？</h4>
          ${again ? `<p class="mall-ask-again">${nbHtml(MALL_AGAIN.replace("{name}", it.name), MALL_SAY_AFTER)}</p>` : ""}
          ${qtyRow}
          <dl class="mall-sum">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("")}</dl>
          ${note ? `<p class="mall-ask-note">${note}</p>` : ""}
          <div class="row"><button class="btn" data-act="ask-no">再想想</button><button class="btn primary" data-act="ask-yes">${again ? "再送一次" : "買下"}（${cost}）</button></div>`;
    // 按 −／＋ 換數量：同一張紙就地換內容，不拆掉整層再插一次（以前每按一下暗處淡入、紙從下緣滑上來的動畫都重播一次，看起來就是閃；
    // Joy 2026-11-03「點數量那邊畫面還是會閃爍」）。焦點留在剛按的那一顆（同一個 aria-label／字），最多那一顆灰掉了就落到「買下」
    const open = qty != null && S.mallAskNow && S.mallAskNow.id === it.id ? document.querySelector(".ask.mall-ask") : null;
    if (open) {
      const was = document.activeElement && document.activeElement.closest && document.activeElement.closest(".mall-qty [data-act]");
      const key = was ? was.getAttribute("aria-label") || was.textContent : null;
      open.innerHTML = inner;
      askGo = () => mallBuy(it.id, ref, n);
      S.mallAskNow = { id: it.id, ref };
      const back = key && [...open.querySelectorAll(".mall-qty [data-act]")].find((b) => (b.getAttribute("aria-label") || b.textContent) === key && !b.disabled);
      (back || open.querySelector('[data-act="ask-yes"]'))?.focus?.();
      return;
    }
    closeAsk();
    S.mallAskNow = { id: it.id, ref };
    askGo = () => mallBuy(it.id, ref, n);
    document.body.insertAdjacentHTML("beforeend", `
      <div class="ask-layer">
        <div class="ask-bg" data-act="ask-no"></div>
        <div class="ask mall-ask" role="alertdialog" aria-modal="true" aria-labelledby="ask-text">${inner}
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
      if (S.mallTab === "look") S.mallLooks = await api("/api/looks").catch(() => S.mallLooks); // 形象那一頁買的：當場變成「換上」
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

  // 管理者區「自建形象」（第二批）：還沒做完的訂單一張一格——下單的人、名字、樣子、十張到了幾張、給生圖工具的提示詞（展開才看）、
  // 上傳（一次選好幾張，檔名照十張的名字：hero_bare_idle.png……）、上架、退回（原因寫給下單的人看）。按「看訂單」才抓
  function looksAdminHtml() {
    const d = S.adLooks;
    const auto = S.adLooks && S.adLooks.gen === "api" ? "畫坊自動畫、自動審，畫好的會自己出現；" : "";
    const head = `<p class="muted">自建形象（玩家下的單：${auto}也可以照提示詞生圖、切成 220 格〔scripts/cut_look.py〕再上傳；十張齊了看過再上架）</p>
      <div class="row wrap"><button class="btn small" data-act="looks-admin" data-op="load">看訂單</button></div>
      <p class="form-msg${S.adLooksOk ? " ok" : ""}" role="alert">${esc(S.adLooksMsg || "")}</p>`;
    if (!d) return head;
    // 畫坊（run_studio.py）：自動畫了幾張；畫不好停手時寫原因、給一顆「再畫一次」
    const studio = (x) => !x.studio || (!x.studio.painted && !x.studio.failed) ? "" : `<p class="muted">畫坊：畫了 ${x.studio.painted | 0} 張${x.studio.failed ? `・停手了：${esc(x.studio.failed)}` : ""}</p>`
      + (x.studio.failed && (x.status === "pending") ? `<div class="row wrap"><button class="btn small" data-act="looks-admin" data-op="studio-retry" data-id="${x.id | 0}">再畫一次</button></div>` : "");
    const row = (o) => {
      const have = new Set(o.have || []);
      const sheets = Object.keys(d.sheets || {});
      const faces = sheets.map((s) => `<span class="${have.has(s) ? "ok" : ""}">${esc(s.replace("hero_", ""))}</span>`).join("");
      const prompts = Object.entries(o.prompts || {}).map(([s, text]) => `<details><summary>${esc(s)}</summary><pre class="look-gen">${esc(text)}</pre></details>`).join("");
      // 到了的那幾張畫成縮圖（點了開原圖）：上架前看得到畫成什麼樣子（管理頁獨立，Joy 2026-11-01）。網址帶抓訂單那一刻，重傳過的不吃舊快取
      const thumbs = o.look && have.size ? `<div class="look-thumbs">${sheets.filter((s) => have.has(s)).map((s) => {
        const src = `/api/looks/img/${encodeURIComponent(o.look)}/${encodeURIComponent(s)}?v=${S.adLooksAt | 0}`;
        return `<a href="${src}" target="_blank" rel="noopener" title="${esc(s)}"><img loading="lazy" src="${src}" alt="${esc(s)}"></a>`;
      }).join("")}</div>` : "";
      return `<div class="card look-admin"><b>#${o.id | 0}「${esc(o.name)}」</b>・${esc(o.owner)}・${esc(o.status_text)}${o.reason ? `（${esc(o.reason)}）` : ""}
        <p>${esc(o.prompt)}</p>${thumbs}${studio(o)}${o.prompts && Object.keys(o.prompts).length ? `<div class="look-sheets">${faces}</div>${prompts}
        <div class="row wrap"><input type="file" id="ad-looks-file-${o.id | 0}" accept="image/png,image/webp" multiple aria-label="上傳十張">
        <button class="btn small" data-act="looks-admin" data-op="upload" data-id="${o.id | 0}">上傳</button>
        <button class="btn small primary" data-act="looks-admin" data-op="release" data-id="${o.id | 0}" ${have.size === sheets.length ? "" : "disabled"}>上架</button></div>
        <div class="row"><input class="input" id="ad-looks-note-${o.id | 0}" placeholder="退回的原因（必填）" maxlength="100"><button class="btn warn small" data-act="looks-admin" data-op="reject" data-id="${o.id | 0}">退回</button></div>` : ""}</div>`;
    };
    // 一句話自創的絕招：導演稿要畫的那一兩樣（法相、巨物）一樣一格——提示詞、選一張上傳；到齊了才按得下上架
    const srow = (m) => `<div class="card look-admin"><b>#${m.id | 0}「${esc(m.art)}」</b>・${esc(m.style_text)}・${esc(m.owner)}・${esc(m.status_text)}${m.reason ? `（${esc(m.reason)}）` : ""}
        <p>${esc(m.prompt)}</p>${moveThumbs(m, (m.arts || []).filter((a) => a.have).map((a) => a.slot))}${studio(m)}${(m.arts || []).some((a) => a.prompt) ? (m.arts || []).map((a) => `<div class="look-sheets"><span class="${a.have ? "ok" : ""}">${esc(a.slot)}・${esc(a.label)}</span></div>
        <details><summary>提示詞</summary><pre class="look-gen">${esc(a.prompt)}</pre></details>
        <div class="row wrap"><input type="file" id="ad-moves-file-${m.id | 0}-${esc(a.slot)}" accept="image/png,image/webp" aria-label="上傳${esc(a.label)}">
        <button class="btn small" data-act="looks-admin" data-op="move-upload" data-id="${m.id | 0}" data-slot="${esc(a.slot)}">上傳</button></div>`).join("")
        + `<div class="row wrap"><button class="btn small primary" data-act="looks-admin" data-op="move-release" data-id="${m.id | 0}" ${m.have ? "" : "disabled"}>上架</button></div>
        <div class="row"><input class="input" id="ad-moves-note-${m.id | 0}" placeholder="退回的原因（必填）" maxlength="100"><button class="btn warn small" data-act="looks-admin" data-op="move-reject" data-id="${m.id | 0}">退回</button></div>` : ""}</div>`;
    const moveThumbs = (m, slots) => m.move && slots.length ? `<div class="look-thumbs">${slots.map((slot) => {
      const src = `/api/looks/img/${encodeURIComponent(m.move)}/${encodeURIComponent(slot)}?v=${S.adLooksAt | 0}`;
      return `<a href="${src}" target="_blank" rel="noopener" title="${esc(slot)}"><img loading="lazy" src="${src}" alt="${esc(slot)}"></a>`;
    }).join("")}</div>` : "";
    const mv = d.moves, mrow = (m) => m.scene ? srow(m) : `<div class="card look-admin"><b>#${m.id | 0}「${esc(m.art)}」</b>・${esc(m.style_text)}・${esc(m.owner)}・${esc(m.status_text)}${m.reason ? `（${esc(m.reason)}）` : ""}
        <p>${esc(m.prompt)}</p>${moveThumbs(m, m.have ? ["fx"] : [])}${m.gen_prompt ? `<div class="look-sheets"><span class="${m.have ? "ok" : ""}">fx</span></div>
        <details><summary>提示詞</summary><pre class="look-gen">${esc(m.gen_prompt)}</pre></details>
        <div class="row wrap"><input type="file" id="ad-moves-file-${m.id | 0}" accept="image/png,image/webp" aria-label="上傳光效">
        <button class="btn small" data-act="looks-admin" data-op="move-upload" data-id="${m.id | 0}">上傳</button>
        <button class="btn small primary" data-act="looks-admin" data-op="move-release" data-id="${m.id | 0}" ${m.have ? "" : "disabled"}>上架</button></div>
        <div class="row"><input class="input" id="ad-moves-note-${m.id | 0}" placeholder="退回的原因（必填）" maxlength="100"><button class="btn warn small" data-act="looks-admin" data-op="move-reject" data-id="${m.id | 0}">退回</button></div>` : ""}</div>`;
    const moves = !mv ? "" : `<p class="muted">絕招（一句話自創的：法相、巨物一樣一張去背圖，邊長最多 1024；舊的光效單一張 ${esc(mv.size)}、六格、透明底）</p>`
      + (mv.open.length ? mv.open.map(mrow).join("") : `<p class="muted">沒有等著做的招式。</p>`) + mv.done.map(mrow).join("");
    return head + (d.open.length ? d.open.map(row).join("") : `<p class="muted">沒有等著做的訂單。</p>`)
      + d.done.map(row).join("") + moves + galleryHtml(d.gallery);
  }
  // 全服成品動畫牆（企劃者 2026-11-03「我是管理員，我需要能看到所有玩家做的成品動畫」）：
  // 只列已上架的（零件到齊才演得出來），點了在上面那塊畫布演。播放器是現成的兩支（arena_scene.js）：
  // 形象用 lookShow（十六張一張一張演，畫布 id 要 look-show），招式用 scenePreview（照導演稿演，畫布 id 要 scene-preview）。
  function galleryHtml(g) {
    if (!g || (!(g.looks || []).length && !(g.moves || []).length)) return `<p class="muted">全服還沒有已上架的成品。</p>`;
    const stage = S.adShow && S.adShow.kind === "look"
      ? `<canvas id="look-show" class="look-show" width="${typeof RING_W === "number" ? RING_W : 720}" height="${typeof RING_H === "number" ? RING_H : 320}" aria-label="形象動作"></canvas>`
      : S.adShow && S.adShow.kind === "move"
        ? `<canvas id="scene-preview" class="scene-preview" width="720" height="320" aria-label="絕招動畫"></canvas>` : "";
    const on = (kind, id) => S.adShow && S.adShow.kind === kind && String(S.adShow.id) === String(id);
    const btn = (kind, id, label, who, look) => `<button class="btn small ${on(kind, id) ? "primary" : "ghost"}"
        data-act="ad-show" data-kind="${kind}" data-id="${esc(id)}"${look ? ` data-look="${esc(look)}"` : ""}>${esc(label)}<small>・${esc(who)}</small></button>`;
    const looks = (g.looks || []).map((x) => btn("look", x.look, x.name || x.look, x.owner)).join("");
    const mvs = (g.moves || []).map((x) => btn("move", x.move, x.name || x.move, x.owner, x.look)).join("");
    return `<p class="muted">全服成品（已上架）：形象 ${(g.looks || []).length} 套、絕招 ${(g.moves || []).length} 招。點一個就在這裡演。</p>
      ${S.adShow ? `<div class="hm-stage">${stage}</div>` : ""}
      ${looks ? `<div class="row wrap">${looks}</div>` : ""}
      ${mvs ? `<div class="row wrap">${mvs}</div>` : ""}`;
  }
  // 點一個成品：再點同一個就收起。形象直接演；招式要先抓它的導演稿（/api/looks/scene/<m…>，上架了的才有）
  async function adShow(kind, id, look) {
    if (!id || (S.adShow && S.adShow.kind === kind && String(S.adShow.id) === String(id))) {
      S.adShow = null; if (typeof renderAdmin === "function") renderAdmin(); return;
    }
    // 出招的人要是下單那位玩家的成品形象：sceneOnRing 的出招者是從擂台狀態讀的，管理頁沒有擂台、那是空的，
    // 不設的話演出來是預設斗笠小子（看起來就像「沒上圖片的 demo 版」）
    if (kind === "move" && typeof RA === "object" && RA && RA.looks) {
      RA.looks.me = look || ""; RA.looks.me_look = look || "";
      if (typeof ringWarmLook === "function" && look) ringWarmLook(look);
    }
    if (kind === "move") {
      const r = await api(`/api/looks/scene/${id}`).catch(() => null);
      if (!r || !r.scene) { S.adLooksMsg = "這一招演不出來，等一下再試。"; S.adLooksOk = false; if (typeof renderAdmin === "function") renderAdmin(); return; }
      S.adShow = { kind, id, scene: r.scene };
      if (typeof renderAdmin === "function") renderAdmin();
      if (typeof scenePreview === "function") scenePreview(r.scene, id);
      return;
    }
    S.adShow = { kind, id };
    if (typeof renderAdmin === "function") renderAdmin();
    if (typeof lookShow === "function") lookShow(id);
  }
  // 上架、退回先問一次（以前按了就送；退回會把元寶全退給下單的人）。退回沒寫原因照舊由伺服器回那一句，不必問
  function looksAdminAsk(op, id, slot) {
    const d = S.adLooks || {};
    const move = op.startsWith("move-");
    const list = move ? [...((d.moves && d.moves.open) || []), ...((d.moves && d.moves.done) || [])] : [...(d.open || []), ...(d.done || [])];
    const x = list.find((o) => String(o.id) === String(id));
    const what = x ? `#${x.id | 0}「${move ? x.art : x.name}」（${x.owner}）` : `#${id}`;
    const note = (document.getElementById(`ad-${move ? "moves" : "looks"}-note-${id}`)?.value || "").trim();
    if ((op === "release" || op === "move-release") && x) {
      ask(`上架${what}：${move ? "這一招的動畫照現在這幾張圖演" : "十張照現在這樣，下單的人就能換上"}，確定？`, "確定上架", () => looksAdminDo(op, id, slot));
      return;
    }
    if ((op === "reject" || op === "move-reject") && x && note) {
      ask(`退回${what}（原因：${note}）：元寶全退給下單的人、原因寫給他看，這一張單就結了，確定？`, "確定退回", () => looksAdminDo(op, id, slot));
      return;
    }
    return looksAdminDo(op, id, slot);
  }
  async function looksAdminDo(op, id, slot) {
    const done = async (r) => {
      const text = (r && r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      S.adLooksMsg = text; S.adLooksOk = !!text && !text.startsWith("（");
    };
    await busy(async () => {
      if (op === "upload") {
        const input = document.getElementById(`ad-looks-file-${id}`);
        const files = Array.from((input && input.files) || []);
        if (!files.length) { S.adLooksMsg = "先選圖（檔名照十張的名字）。"; S.adLooksOk = false; }
        const said = [];
        for (const f of files) {
          const data = await new Promise((ok, no) => { const fr = new FileReader(); fr.onload = () => ok(String(fr.result).split(",")[1] || ""); fr.onerror = no; fr.readAsDataURL(f); });
          const r = await api("/api/do/looks_upload", { id: Number(id), sheet: f.name.replace(/\.[^.]+$/, ""), data });
          said.push((r.message || "").replace(/<[^>]+>/g, " ").trim());
        }
        if (said.length) { S.adLooksMsg = said[said.length - 1]; S.adLooksOk = !said.some((t) => t.startsWith("（")); if (!S.adLooksOk) S.adLooksMsg = said.filter((t) => t.startsWith("（")).join(" "); }
      } else if (op === "move-upload") {
        const f = ((document.getElementById(slot ? `ad-moves-file-${id}-${slot}` : `ad-moves-file-${id}`) || {}).files || [])[0];
        if (!f) { S.adLooksMsg = "先選一張圖。"; S.adLooksOk = false; }
        else {
          const data = await new Promise((ok, no) => { const fr = new FileReader(); fr.onload = () => ok(String(fr.result).split(",")[1] || ""); fr.onerror = no; fr.readAsDataURL(f); });
          await done(await api("/api/do/moves_upload", { id: Number(id), data, ...(slot ? { sheet: slot } : {}) }));
        }
      } else if (op === "move-release") {
        await done(await api("/api/do/moves_release", { id: Number(id) }));
      } else if (op === "move-reject") {
        const note = (document.getElementById(`ad-moves-note-${id}`)?.value || "").trim();
        await done(await api("/api/do/moves_reject", { id: Number(id), note }));
      } else if (op === "studio-retry") {
        await done(await api("/api/do/looks_studio_retry", { id: Number(id) }));
      } else if (op === "release") {
        await done(await api("/api/do/looks_release", { id: Number(id) }));
      } else if (op === "reject") {
        const note = (document.getElementById(`ad-looks-note-${id}`)?.value || "").trim();
        await done(await api("/api/do/looks_reject", { id: Number(id), note }));
      }
      S.adLooks = await api("/api/admin/looks");
      S.adLooksAt = Math.floor(Date.now() / 1000);
      if (S.adminPage && op !== "load" && S.adLooksMsg) S.adResult = { text: S.adLooksMsg, ok: !!S.adLooksOk }; // 管理頁：結果也釘在底下
      renderKeepingSheet();
    });
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
      if (S.adminPage) S.adResult = { text: S.adMallMsg, ok: S.adMallOk }; // 管理頁：結果也釘在底下
      renderKeepingSheet();
    });
  }

