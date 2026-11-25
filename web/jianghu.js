/* 江湖頁重排（功能包 jianghu；Joy 2026-11-25「方向對」、決定卡「開始做，先不上線」；施工單 2026-11-25）。
 *
 * 開關 Config.jianghu.enabled（預設關，三種設定都不開）：伺服器送 main.jianghu 時，江湖頁閒著的那一刻（revampOn：不在序章、
 * 初入江湖、路上、決戰出招、事件與對話）改用這裡的排法；其餘時刻與開關關著照舊（web/main.js 的 pageJianghu）。
 *
 * 由上到下（第一批：骨架）：
 *   1. 場景圖滿版、往下暈進紙色；地名楷書大字題在畫上，旁邊一枚直書小印（戰火、荒……）
 *   2. 狀態一行疊在圖上：名號印、名號、等級與陣營、體力與氣血兩條細條加數字、時刻、右上設定鈕
 *   3. 旁白不裝框：場景描述一兩行、剛發生的事一行
 *   4. 眼下（第二批換成一張卡）：這一批先照舊放進行中、來信、本週卡
 *   5. 四顆行動牌：同一種元件（第一批先套在原本的行動列上；軍務、行路的清單在第四批）
 *   6～7. 這裡的人、這裡的去處：第三、四批；這一批照舊畫原本那兩排
 * 銀兩、心神、元寶這一版不在狀態行（Joy 還沒回要不要放回來）：JH_PURSE 改 true 就畫回去。
 */
"use strict";

  const JH_PURSE = false; // 銀兩、心神放回狀態行：改 true（施工單「先做成容易加回去」）

  // 開著、又是閒著的那一刻才換排法（決戰面板開著、師父在說話的序章也不換）
  const jhOn = (m) => !!(m && m.jianghu && m.jianghu.on) && typeof revampOn === "function" && revampOn(m) && !(typeof bpOn === "function" && bpOn(m));

  // 地名旁那一枚直書小印：地點變樣（戰火、淪陷、饑荒、重建）優先，沒有就照危險幾顆星寫一個詞（不畫星星）
  const JH_MOOD = { war: "戰火", fallen: "淪陷", famine: "饑荒", rebuild: "重建" }; // 待 joy 潤
  const JH_DANGER = ["", "小險", "險地", "兇地", "絕地"]; // 待 joy 潤：危險一到四顆星
  function jhSealWord(m) {
    const a = m.art || {};
    if (a.mood && JH_MOOD[a.mood]) return JH_MOOD[a.mood];
    const stars = (String(a.sub || "").match(/★/g) || []).length;
    return JH_DANGER[Math.min(stars, JH_DANGER.length - 1)] || "";
  }

  // 地名：圖上的標題（「宛城」）；沒有圖時照狀態的所在（括號裡的城名拿掉，例「潁川郡（陽翟）」寫「潁川郡」）
  function jhPlaceName(m) {
    const a = m.art && m.art.kind === "place" ? m.art : null;
    const name = (a && a.title) || (m.status && m.status.location) || "";
    return String(name).replace(/（.*?）/g, "").trim();
  }

  // 一條細條：名字一個字、條、數字（數字寫在條右邊，不壓在條上）
  const jhBar = (cls, word, now, max) => `<div class="jh-bar ${cls}"><em>${word}</em><i style="--w:${pct(now, max)}%"></i><b>${now | 0}</b></div>`;

  // 狀態一行：疊在圖最上面
  function jhStatusHtml(m) {
    const s = m.status || {};
    const vit = [
      shown("stamina") ? jhBar("stam", "體", s.stamina, s.stamina_max) : "",
      shown("hp") ? jhBar("hp", "血", s.hp, s.hp_max) : "",
    ].join("");
    const pill = s.pills && shown("stamina")
      ? `<button class="jh-pill" data-act="pill" ${s.pills.full || (!s.pills.refill && s.pills.today === 0) ? "disabled" : ""} aria-label="${esc(s.pills.refill ? `${s.pills.refill}體力` : `服下${s.pills.name}（剩 ${s.pills.count} 顆）`)}">${esc(s.pills.refill || `丹${s.pills.count}`)}</button>`
      : "";
    const purse = JH_PURSE && shown("silver") ? `<div class="jh-purse"><span><em>銀</em>${s.silver | 0}</span>${s.xinshen ? `<span><em>${esc(s.xinshen.name)}</em>${s.xinshen.now | 0}</span>` : ""}</div>` : "";
    const when = s.calendar ? s.calendar.text : `第${s.day}天 ${s.clock}`;
    const help = S.stamOpen && s.stamina_help && s.stamina_help.length
      ? `<div class="jh-help" id="stam-help">${s.stamina_help.map((t) => `<p>${esc(t)}</p>`).join("")}</div>` : "";
    return `<header class="jh-st">
        <button class="jh-me" data-act="hero-attrs" aria-label="看屬性">${esc((s.name || "").slice(0, 1))}${s.stat_points ? dotHtml(true) : ""}</button>
        <div class="jh-nm"><b>${esc(s.name || "")}</b><small>${s.level | 0} 級・${esc(s.affiliation || "")}${s.anonymous ? "・匿名" : ""}</small></div>
        <div class="jh-vit"${s.stamina_help && s.stamina_help.length ? ` data-act="stam-help" role="button" tabindex="0" aria-expanded="${!!S.stamOpen}" aria-controls="stam-help"` : ""}>${vit}<span class="jh-tm">${esc(when)}</span></div>${pill}
        <button class="jh-gear" data-act="sheet" aria-label="設定">⚙${dotHtml(dotAt("sheet"))}</button>
      </header>${purse}${help}`;
  }

  // 場景圖：閒著時是地點的圖；眼前不是地點（少見：伺服器給的是別的圖）時用上一張地點的圖，都沒有就只有紙
  function jhArtSrc(m) {
    if (m.art && m.art.kind === "place") return m.art.src;
    return S.lastPlaceArt || "";
  }

  // 旁白：場景描述（地名那一行已經題在畫上，不寫兩次）收成兩行，點了攤開；剛發生的事一行（照舊點了攤開整則）
  function jhProseHtml(m, inner, now) {
    const open = !!S.sceneRvOpen;
    const tappable = !/<button|<form/.test(inner);
    return `<div class="jh-prose">${inner ? `<div class="jh-desc${open || !tappable ? "" : " clamp"}"${tappable ? ` data-act="rv-scene" role="button" tabindex="0" aria-expanded="${open}"` : ""}>${inner}</div>` : ""}${now ? `<div class="jh-now">${now}</div>` : ""}</div>`;
  }

  // 旁白開頭的「〔戰火〕」：小印已經寫了，不寫兩次（一件事一頁只出現一次）
  function jhNoSealTwice(inner, seal) {
    return seal ? String(inner || "").replace(new RegExp(`^(\\s*<p[^>]*>)\\s*〔${seal}〕\\s*`), "$1") : inner;
  }

  // 四顆行動牌：先沿用原本行動列的格子（按的東西、灰著的原因、點開的卡都照舊），樣子換成牌子；「移動」改叫「行路」
  function jhActs(menu) {
    return String(menu || "").replace(/<b>移動<\/b>/, "<b>行路</b>"); // 待 joy 潤：行路（施工單第 5 條）
  }

  // ── 4. 眼下（第二批）：一張卡只放現在最該理的一件，一顆主要的鈕加「稍後」；其餘收成右上「另有 N 件 ›」，點了從底下拉起清單 ──
  // 一件：{ key, seal（小印的字）, title, sub, btn（主鈕的字）, attrs（主鈕的 data-act…）}；wait 的是現在推不動的（收在清單最底下）
  const JH_LATER = "稍後"; // 待 joy 潤
  const JH_MORE = "另有 {n} 件"; // 待 joy 潤
  const JH_LIST = "眼下的事"; // 待 joy 潤
  const JH_WAITS = "在等的 {n} 件"; // 待 joy 潤
  const JH_CLOSE = "關閉";
  const JH_NONE = "眼下沒有別的事。"; // 待 joy 潤
  const JH_READ = "看信"; // 待 joy 潤
  const JH_LOOK = "看看"; // 待 joy 潤
  const JH_GO = { id: "去做", loc: "前往", duty: "去辦", hero: "去看", legacy: "去看" }; // 待 joy 潤：主鈕的字（照「去」到哪裡）
  const JH_RENOWN = "江湖上稱你「{t}」"; // 待 joy 潤
  const JH_PTS = "有 {n} 點屬性可配"; // 待 joy 潤（同進行中那一行）
  const JH_SIDES = "還沒投靠哪一方"; // 待 joy 潤
  const JH_SIDES_SUB = "官軍、黃巾，或做個散人"; // 待 joy 潤
  const JH_WEEK_SEAL = "本週"; // 待 joy 潤
  const JH_WEEK_LIVE = "大事"; // 待 joy 潤：這一回的大事在集結或開打
  // 兩軍態勢一句話（同 codex.js tkTugHtml、本週卡那一句）
  function jhTugWords(m) {
    const w = m.week_card, sd = w && w.sides;
    if (!sd || !("guan" in sd) || !("huang" in sd)) return "";
    const d = (sd.guan | 0) - (sd.huang | 0);
    const cols = (m.sides_card && m.sides_card.cols) || [];
    const name = (k) => (cols.find((c) => c.id === k) || {}).name || (k === "guan" ? "官軍" : "黃巾");
    return Math.abs(d) < 10 ? "兩軍相持" : `${name(d > 0 ? "guan" : "huang")}${Math.abs(d) >= 30 ? "大佔上風" : "佔上風"}`; // 待 joy 潤（同本週卡那一句）
  }
  const JH_DAILY = "月卡・今日份"; // 待 joy 潤（同 mall.js 那一張）
  const JH_TUG_LINK = "兩軍態勢・這一季在打什麼"; // 待 joy 潤

  // 剛剛那一則裡的「名號傳開・某某 ›」：從那一行拿出來，變成眼下的一件（PM 2026-11-25：方框連結有網頁味）
  const JH_RENOWN_CHIP = /<span class="tx-chg tx-renown"[^>]*>名號傳開・([^<]*?)\s*›<\/span>/g;
  const jhRenowns = (m) => [...String(m.now || "").matchAll(JH_RENOWN_CHIP)].map((x) => x[1]);
  const jhNoRenown = (html) => String(html || "").replace(JH_RENOWN_CHIP, "");

  // 進行中（web/codex.js 的 tkItems）的一件換成眼下的一件：主鈕照 codex 的「去」那一套（cx-tk-go），字照去哪裡
  function jhFromTrack(m, it) {
    const o = it.go && it.go.id ? (m.options || []).find((x) => x.id === it.go.id) : null;
    const name = o ? optParts(o)[0].split("・")[0] : "";
    const kind = Object.keys(JH_GO).find((k) => it.go && it.go[k]) || "id";
    let { title, sub } = it;
    if (it.seal === JH_EPIPHANY && sub) [title, sub] = [sub.split("・")[0], sub.split("・").slice(1).join("・")]; // 「特殊頓悟」是線的代稱：標題寫這一步本身（靜心自問、去面對心魔）
    if (it.key === "d:bounty") ({ title, sub } = jhBountyWords(m) || { title, sub });
    return { key: it.key, seal: it.seal, title, sub, wait: !!it.wait, btn: name && name.length <= 4 && !title.includes(name) ? name : JH_GO[kind], attrs: it.go ? tkGoAttrs(it) : "" };
  }

  // 懸賞那一件的字：卡頭那一行（「懸賞（2）賞照你第 30 級」）像代號，換成手上的事（PM 2026-11-25）
  const JH_EPIPHANY = "頓悟";
  const JH_BOUNTY_MANY = "手上有 {n} 件懸賞"; // 待 joy 潤
  const JH_BOUNTY_GIVE = "身上有懸賞要的東西"; // 待 joy 潤（求兵：還沒揭、身上有合用的）
  function jhBountyWords(m) {
    const rows = (m.status && m.status.bounties) || [];
    if (!rows.length) return null;
    const first = rows[0];
    if (rows.length > 1) return { title: JH_BOUNTY_MANY.replace("{n}", rows.length), sub: jhPlain(first.title) };
    return first.have ? { title: JH_BOUNTY_GIVE, sub: jhPlain(first.title) } : { title: jhPlain(first.title), sub: first.how || "" };
  }

  // 別人遞來的邀請（切磋、論武、結伴……）：一則一件，排最前面（邀請半小時就作廢）。主鈕是答應，第二顆是婉拒（不是稍後）
  const JH_CALL_WHO = "{side}・人就在此地"; // 待 joy 潤：眼下卡那一行副題（他是誰），卡高不變
  const JH_CALL_SOON = "邀約不久就作廢"; // 待 joy 潤（找不到人時）
  const JH_CALL_SEAL = [[/切磋/, "邀戰"], [/論武/, "論武"], [/結伴/, "結伴"], [/結義/, "結義"]]; // 待 joy 潤
  const jhBtnAttrs = (o) => (o.peer ? `data-act="peer-answer" data-name="${esc(o.peer)}"` : `data-act="choose" data-id="${esc(o.id)}"${o.enabled === false ? " disabled" : ""}`);
  function jhCalls(m) {
    return (m.calls || []).map((c, i) => {
      const [yes, no] = c.options || [];
      const seal = (JH_CALL_SEAL.find(([re]) => re.test(c.text)) || [null, "邀約"])[1];
      const who = (m.here || []).find((x) => x.name && String(c.text).includes(x.name));
      return { key: `c:${yes ? yes.id : i}`, seal, title: c.text, sub: who && who.side ? JH_CALL_WHO.replace("{side}", who.side) : JH_CALL_SOON, btn: yes ? yes.label : JH_LOOK, attrs: yes ? jhBtnAttrs(yes) : "", alt: no ? { label: no.label, attrs: jhBtnAttrs(no) } : null };
    });
  }

  function jhEyeItems(m, p) {
    const on = [], wait = [];
    const s = m.status || {};
    const slim = typeof codexSlim === "function" && codexSlim(m);
    const w = m.week_card;
    // 換週那一刻、這一回的大事在集結或開打：兩軍態勢自己變成眼下的一件，排最前（PM 2026-11-25；平常只在清單裡）
    if (w && slim && typeof codexWeekShow === "function" && codexWeekShow(m)) {
      const live = !!(w.chapter && w.chapter.live);
      on.push({ key: `w:${w.when}`, seal: live ? JH_WEEK_LIVE : JH_WEEK_SEAL, title: w.theme || w.when, sub: [jhTugWords(m), w.when].filter(Boolean).join("・"), btn: JH_LOOK, attrs: 'data-act="cx-tk-why"' });
    }
    on.push(...jhCalls(m));
    if (m.letter) { // 來信：主鈕拉起整封信（婉拒、收起都在信上）
      const x = m.letter;
      on.push({ key: `l:${x.id}`, seal: x.kind || "來信", title: `${x.sender}來信`, sub: x.task ? x.task.how : x.errand ? x.errand.text : x.text, btn: JH_READ, attrs: 'data-act="jh-sheet" data-sheet="letter"' });
    }
    if (p.daily) { // 月卡今天的份：主鈕直接領
      const today = m.mall && m.mall.daily;
      on.push({ key: "daily", seal: "月卡", title: JH_DAILY, sub: today && typeof dailyWhat === "function" ? dailyWhat(today) : "", btn: "領取", attrs: 'data-act="mall-claim"' });
    }
    for (const t of jhRenowns(m)) on.push({ key: `r:${t}`, seal: "名聲", title: JH_RENOWN.replace("{t}", t), sub: "", btn: JH_LOOK, attrs: 'data-act="renown-open" role="button"' });
    const joined = !m.sides_card || !!m.sides_card.joined;
    if (!joined && m.sides_card) on.push({ key: "sides", seal: "投靠", title: JH_SIDES, sub: JH_SIDES_SUB, btn: JH_LOOK, attrs: 'data-act="jh-sheet" data-sheet="sides"' });
    const got = typeof tkItems === "function" ? tkItems(m, p.parts) : null;
    if (got) {
      for (const it of got.on) on.push(jhFromTrack(m, it));
      for (const it of got.wait) wait.push(jhFromTrack(m, it));
    } else {
      for (const d of p.parts || []) if (d.html) (d.now ? on : wait).push({ key: `d:${d.key}`, seal: d.name, title: d.line || d.name, sub: "", btn: JH_GO.duty, attrs: 'data-act="duty-open"', wait: !d.now });
    }
    // 屬性點、識海：進行中瘦身時已經在 tkItems 裡；沒瘦身（還沒投靠、進行中關著）這裡補
    if (!slim) {
      const pts = s.growth ? s.stat_points | 0 : 0;
      if (pts) on.push({ key: "h:pts", seal: "屬性", title: JH_PTS.replace("{n}", pts), sub: "", btn: "去配", attrs: 'data-act="hero-attrs"' });
      const sh = m.legacy && m.legacy.shihai;
      if (sh && sh.offers && sh.offers.length) on.push({ key: "h:shihai", seal: "識海", title: "上一季的神品意境還沒挑", sub: "", btn: JH_LOOK, attrs: 'data-act="legacy-view" data-v="shihai"' }); // 待 joy 潤
    }
    return { on, wait };
  }

  // 眼下已經有的（邀請的答應、婉拒）、收進人物卡的（護衛、犒軍、挑戰：aid 那幾顆）不再排進此地可為（施工單第 6 條「aid:* 不再散在此地可為」）
  function jhNotInEye(m, extras) {
    const ids = new Set((m.calls || []).flatMap((c) => (c.options || []).map((o) => o.id)));
    for (const f of m.figures_here || []) for (const id of f.aid || []) ids.add(id);
    return extras.filter((o) => !ids.has(o.id) && !o.id.startsWith("invite:"));
  }
  // 標題前面的小圖示（「🪧 懸賞」）拿掉：小印已經說了是哪一類
  const jhPlain = (t) => String(t || "").replace(/^[^\p{L}\p{N}（「]+/u, "");

  const jhSealHtml = (t) => `<span class="jh-k">${esc(t)}</span>`;
  // 眼下那一張：挑第一件不在「稍後」裡的（都稍後了就從頭再來）
  function jhEyeHtml(m, p) {
    const { on, wait } = jhEyeItems(m, p);
    if (!on.length && !wait.length) return "";
    const later = S.jhLater || [];
    const top = on.find((x) => !later.includes(x.key)) || on[0];
    const rest = on.length - (top ? 1 : 0);
    const more = rest || wait.length ? `<button class="jh-more" data-act="jh-sheet" data-sheet="eye" aria-label="${esc(JH_MORE.replace("{n}", rest))}">${rest ? esc(JH_MORE.replace("{n}", rest)) : esc(JH_WAITS.replace("{n}", wait.length))}<i aria-hidden="true">›</i></button>` : "";
    if (!top) { // 都在等：一行就好，點了拉起清單
      return `<section class="jh-eye idle"><div class="jh-eye-hd">${jhSealHtml(wait[0].seal)}<b>${esc(jhPlain(wait[0].title))}</b>${more}</div></section>`;
    }
    return `<section class="jh-eye" aria-label="眼下">
        <div class="jh-eye-hd">${jhSealHtml(top.seal)}<b>${esc(jhPlain(top.title))}</b>${more}</div>
        <p class="jh-eye-sub">${esc(top.sub || "")}</p>
        <div class="jh-eye-row"><button class="btn jh-eye-go" ${top.attrs}>${esc(top.btn)}</button>${top.alt ? `<button class="btn jh-eye-later" ${top.alt.attrs}>${esc(top.alt.label)}</button>` : on.length > 1 ? `<button class="btn jh-eye-later" data-act="jh-later" data-key="${esc(top.key)}">${JH_LATER}</button>` : ""}</div>
      </section>`;
  }

  // 拉起來的那一層：眼下的事（全部）、一封信、投靠的三方卡
  function jhSheetHtml(m, p) {
    const which = S.jhSheet;
    if (!which) return "";
    const wrap = (label, inner) => `<div class="sheet-bg" data-act="jh-sheet"></div><div class="sheet jh-sheet" role="dialog" aria-label="${esc(label)}"><div class="grip"></div>`
      + `<div class="top-row"><h3 style="flex:1">${esc(label)}</h3><button class="btn small ghost" data-act="jh-sheet">${JH_CLOSE}</button></div>${inner}</div>`;
    if (which === "letter") {
      if (!m.letter || typeof letterHtml !== "function") { S.jhSheet = null; return ""; }
      S.letterOpen = m.letter.id;
      return wrap(`${m.letter.sender}來信`, letterHtml(m.letter) + (p.pushAsk || ""));
    }
    if (which === "people") return wrap(JH_PEERS_HEAD, jhPeersSheetBody(m));
    if (which === "sides") {
      const html = typeof sidesFirstHtml === "function" ? sidesFirstHtml(m) : "";
      if (!html) { S.jhSheet = null; return ""; }
      return wrap(JH_SIDES, html);
    }
    const { on, wait } = jhEyeItems(m, p);
    const row = (it, go) => `<div class="jh-row${go ? "" : " wait"}">${jhSealHtml(it.seal)}<span class="jh-row-t"><b>${esc(jhPlain(it.title))}</b>${it.sub ? `<small>${esc(it.sub)}</small>` : ""}</span>${go ? `<button class="btn small jh-row-go" ${it.attrs}>${esc(it.btn)}</button>` : ""}</div>`;
    const tug = typeof tkTugHtml === "function" ? tkTugHtml(m) : "";
    const why = m.week_card ? `<button class="jh-why" data-act="cx-tk-why">${JH_TUG_LINK}<i aria-hidden="true">›</i></button>` : "";
    const waits = wait.length ? `<button class="jh-waits" data-act="jh-wait" aria-expanded="${!!S.jhWait}">${esc(JH_WAITS.replace("{n}", wait.length))}<i aria-hidden="true">${S.jhWait ? "▴" : "▾"}</i></button>${S.jhWait ? wait.map((it) => row(it, false)).join("") : ""}` : "";
    return wrap(JH_LIST, `${tug}${on.length ? on.map((it) => row(it, true)).join("") : `<p class="jh-none">${JH_NONE}</p>`}${waits}${why}`);
  }

  async function jianghuClick(act, el, ev) {
    switch (act) {
        case "jh-later": S.jhLater = [...(S.jhLater || []).filter((k) => k !== el.dataset.key), el.dataset.key]; renderPage(); break;
        case "jh-sheet": S.jhSheet = el.dataset.sheet || null; S.jhWait = false; renderPage(); break;
        case "jh-wait": S.jhWait = !S.jhWait; renderPage(); break;
    } // jianghuClick
  } // jianghuClick
  registerClicks(jianghuClick, ["jh-later", "jh-sheet", "jh-wait"]);

  // ── 6. 這裡的人（第三批）：一排方格。大勢人物全放（立繪），俠客只放跟你有關的（邀你的、義兄弟、敵方），最後一格「＋N 俠客」拉起全部。
  // 有事找你的人頭上一枚小印（軍令、託付、邀戰……）。人是入口：點人物拉起他的卡（他交代的事、交談、護衛、犒軍、挑戰），點俠客照舊開玩家卡
  const JH_PEOPLE = "這裡的人"; // 待 joy 潤
  const JH_PEOPLE_F = "{n} 位人物", JH_PEOPLE_P = "{n} 位俠客"; // 待 joy 潤（沒有的那一半不寫）
  const JH_PEERS_ALL = "俠客"; // 待 joy 潤：「＋N 俠客」那一格
  const JH_PEERS_HEAD = "此地的俠客"; // 待 joy 潤
  const JH_BROTHER = "義"; // 待 joy 潤：義兄弟頭上的小印
  const JH_FOE = "敵"; // 待 joy 潤：敵方頭上的小印
  const JH_ROW_MAX = 6; // 一排六格（390 寬），人再多也是一排
  const JH_SIDES2 = ["官軍", "黃巾"];
  function jhMySide(m) {
    return String((m.status && m.status.affiliation) || "").split("・").find((x) => JH_SIDES2.includes(x)) || "";
  }
  // 誰頭上掛什麼印：大勢人物（id → 印）與俠客（名號 → 印）
  function jhMarks(m) {
    const fig = {}, peer = {};
    for (const f of m.figures_here || []) {
      if ((m.orders || []).some((o) => !o.done && String(o.text || "").startsWith(f.name))) fig[f.id] = "軍令";
      else if (m.letter && m.letter.sender === f.name && (m.letter.task || m.letter.errand)) fig[f.id] = m.letter.kind || "託付";
    }
    for (const c of m.calls || []) {
      const who = (m.here || []).find((x) => String(c.text).startsWith(x.name));
      if (who) peer[who.name] = (JH_CALL_SEAL.find(([re]) => re.test(c.text)) || [null, "邀約"])[1];
    }
    const j = m.jieyi;
    for (const x of (j && j.members) || []) if (!x.me && !peer[x.name]) peer[x.name] = JH_BROTHER;
    const mine = jhMySide(m);
    for (const x of m.here || []) if (!peer[x.name] && mine && JH_SIDES2.includes(x.side) && x.side !== mine) peer[x.name] = JH_FOE;
    return { fig, peer };
  }
  const jhMk = (t) => (t ? `<i class="jh-mk">${esc(t)}</i>` : "");
  function jhPeopleHtml(m) {
    const figs = m.figures_here || [], peers = m.here || [];
    if (!figs.length && !peers.length) return "";
    const { fig, peer } = jhMarks(m);
    const order = { 邀戰: 0, 論武: 0, 結伴: 0, 結義: 0, 邀約: 0, [JH_BROTHER]: 1, [JH_FOE]: 2 };
    const near = peers.filter((x) => peer[x.name]).sort((a, b) => order[peer[a.name]] - order[peer[b.name]]);
    const room = Math.max(0, JH_ROW_MAX - figs.length - (peers.length ? 1 : 0));
    const shown = near.slice(0, room), rest = peers.length - shown.length;
    const tiles = figs.map((f) => `<button class="jh-ic fig" data-act="fig-open" data-id="${esc(f.id)}"><span${f.face ? ` style="background-image:url('${esc(f.face)}')"` : ""}>${f.face ? "" : esc(f.name.slice(0, 1))}</span>${esc(f.name)}${jhMk(fig[f.id])}</button>`)
      .concat(shown.map((x) => `<button class="jh-ic pc${peer[x.name] === JH_FOE ? " foe" : ""}" data-act="peer" data-name="${esc(x.name)}"><span>${esc(x.name.slice(0, 1))}</span>${esc(x.name)}${jhMk(peer[x.name] === JH_FOE ? "" : peer[x.name])}</button>`))
      .concat(rest > 0 ? [`<button class="jh-ic all" data-act="jh-sheet" data-sheet="people"><span>＋${rest}</span>${JH_PEERS_ALL}</button>`] : []);
    const n = [figs.length ? JH_PEOPLE_F.replace("{n}", figs.length) : "", peers.length ? JH_PEOPLE_P.replace("{n}", peers.length) : ""].filter(Boolean).join("・");
    return `<section class="jh-blk jh-people"><h3>${JH_PEOPLE}<small>${esc(n)}</small></h3><div class="jh-ppl">${tiles.join("")}</div></section>`;
  }
  // 「＋N 俠客」拉起來那一層：此地全部的俠客，跟你有關的排前面
  function jhPeersSheetBody(m) {
    const { peer } = jhMarks(m);
    const list = (m.here || []).slice().sort((a, b) => (peer[a.name] ? 0 : 1) - (peer[b.name] ? 0 : 1));
    return `<div class="jh-peers">${list.map((x) => `<button class="jh-prow${peer[x.name] === JH_FOE ? " foe" : ""}" data-act="peer" data-name="${esc(x.name)}"><span class="jh-pface">${esc(x.name.slice(0, 1))}</span><span class="jh-row-t"><b>${esc(x.name)}</b><small>${esc(x.side || "")}</small></span>${peer[x.name] ? jhSealHtml(peer[x.name]) : ""}<i aria-hidden="true">›</i></button>`).join("")}</div>`;
  }

  // 點人物：拉起他的卡。立繪、名字與身分、一句他是誰；他交代你的事（有的話，鈕在最上面）；其餘能對他做的兩欄排（不能做的變淡、寫原因）
  const JH_FIG_TALK = "交談", JH_FIG_LOG = "往來紀錄"; // 待 joy 潤（同 companions.js）
  const JH_FIG_ORDER = "他點了你的名：{t}"; // 待 joy 潤
  const JH_FIG_GO = "去辦"; // 待 joy 潤
  function jhFigHtml(m) {
    const f = (m.figures_here || []).find((x) => x.id === S.fig);
    if (!f) return "";
    const byId = Object.fromEntries((m.options || []).map((o) => [o.id, o]));
    const btn = (label, small, attrs, off) => `<button class="btn jh-do${off ? " off" : ""}" ${attrs}>${esc(label)}${small ? `<small>${esc(small)}</small>` : ""}</button>`;
    const why = (t) => `data-act="opt-why" data-why="${esc(t ? `${t}。` : "")}" aria-disabled="true"`;
    const dos = [f.talk.via ? btn(JH_FIG_TALK, f.affinity ? `情誼 ${f.affinity}` : "", `data-act="fig-talk" data-id="${esc(f.id)}"`) : btn(JH_FIG_TALK, f.talk.why || "", why(f.talk.why), true)];
    for (const id of f.aid || []) {
      const o = byId[id];
      if (!o) continue;
      const [label, detail] = optParts(o);
      const name = label.replace(/^(護衛|犒軍|挑戰).*$/, "$1").replace(/・.*$/, "");
      const note = String(detail || "").split("）（").pop();
      dos.push(o.enabled ? btn(name, note, `data-act="fig-act" data-id="${esc(o.id)}"`) : btn(name, note, why(note), true));
    }
    dos.push(btn(JH_FIG_LOG, "", `data-act="fig-log" data-id="${esc(f.id)}"`));
    const order = (m.orders || []).find((o) => !o.done && String(o.text || "").startsWith(f.name));
    const letter = m.letter && m.letter.sender === f.name && (m.letter.task || m.letter.errand) ? m.letter : null;
    const say = order ? `<div class="jh-say"><b>${esc(JH_FIG_ORDER.replace("{t}", order.title))}</b><small>${esc(order.how || "")}</small></div>${btn(JH_FIG_GO, "", 'data-act="duty-open"').replace("jh-do", "jh-do wide primary")}`
      : letter ? `<div class="jh-say"><b>${esc(letter.task ? letter.task.title : letter.errand.text)}</b><small>${esc(letter.task ? letter.task.how : "")}</small></div>${btn(JH_READ, "", 'data-act="jh-sheet" data-sheet="letter"').replace("jh-do", "jh-do wide primary")}` : "";
    const i = f.intro || {};
    const role = i.role || f.side || "";
    return `<div class="sheet-bg" data-act="fig-close"></div><div class="sheet jh-card jh-fig" role="dialog" aria-label="${esc(f.name)}">
        <div class="jh-pt"${f.face ? ` style="background-image:url('${esc(f.face)}')"` : ""}><button class="jh-x" data-act="fig-close" aria-label="${JH_CLOSE}">×</button></div>
        <div class="jh-in"><h2>${esc(f.name)}<small>${esc(role)}</small></h2>${i.who ? `<p>${esc(i.who)}</p>` : ""}${say}<div class="jh-dos">${dos.join("")}</div></div></div>`;
  }

  // 整頁：parts 是 pageJianghu 已經算好的各塊（同一份資料，不重算）
  // 畫壞了（新排法哪一格丟例外）不能讓整頁掉回登入頁（app.js 的 enter 接到例外就回登入）：回空字串，main.js 照舊畫原本的江湖頁
  function jhPageHtml(m, p) {
    try { return jhPage(m, p); } catch (e) { if (typeof console !== "undefined") console.error(e); return ""; }
  }
  function jhPage(m, p) {
    try { document.documentElement.classList.add("jh2"); } catch (e) { /* 測試裡沒有 document */ }
    const src = jhArtSrc(m);
    const seal = jhSealWord(m);
    const name = jhPlaceName(m);
    const hero = `<section class="jh-hero${m.art && m.art.mood ? ` mood-${esc(m.art.mood)}` : ""}">
        ${src ? `<img class="jh-art" src="${esc(src)}" alt="" decoding="async">` : '<div class="jh-art none"></div>'}
        ${jhStatusHtml(m)}
        <div class="jh-pl"><h1>${esc(name)}</h1>${seal ? `<span class="jh-seal">${esc(seal)}</span>` : ""}</div>
      </section>`;
    // 眼下一張卡排在旁白底下、行動牌上面（高度固定：事再多也只多「另有 N 件」那幾個字）
    const sheetOpen = !!S.jhSheet || !!S.cxWhy || !!S.dutyOpen || !!S.fig;
    const extras = jhNotInEye(m, p.extras || []);
    let base = p.layers || "";
    // 點人物那一層換成人物卡（舊的對話式那一層 figPickHtml 拿掉）；「全部」那一層也不列收進人物卡的
    if (S.fig && !S.figLog && typeof figPickHtml === "function") base = base.replace(figPickHtml(m), () => jhFigHtml(m));
    if (S.hereAll && typeof hereAllHtml === "function") base = base.replace(hereAllHtml(m, p.extras || []), () => hereAllHtml(m, extras));
    const layers = `${base}${jhSheetHtml(m, p)}${typeof codexWhyHtml === "function" ? codexWhyHtml(m) : ""}`;
    return `<div class="jh-page${sheetOpen ? " sheet-on" : ""}">${p.ckPop || ""}${hero}${jhProseHtml(m, jhNoSealTwice(p.inner, seal), jhNoRenown(p.now))}${p.resultCard}${jhEyeHtml(m, p)}${m.party && typeof socialHtml === "function" ? socialHtml({ ...m, calls: [] }) : ""}${p.jieyi}${p.links}${p.free}<div class="jh-acts">${jhActs(p.menu)}</div>${p.sealCard}${p.senseNotes}${jhPeopleHtml(m)}${typeof hereRowHtml === "function" ? hereRowHtml(m, extras) : ""}${p.guideDown}${p.skip}${layers}</div>`;
  }
