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
  // 決戰集結中照常行動（第六批）：閒著的頁照畫，集結那一條在頁上；開打了換決戰面板
  const jhBpMuster = (m) => typeof bpOn === "function" && bpOn(m) && m.battle_panel.phase === "muster";
  // 新角色慢慢長出來（新角色那一包 web/unfold.js，Joy 2026-11-25；這一頁的鍵 jh:*）：還沒長出來的不畫；剛長出來的那一格亮紅點，點開就滅
  const jhShown = (k) => typeof shown !== "function" || shown(k);
  const jhUfDot = (k) => (typeof unfoldDot === "function" && unfoldDot(k) ? '<i class="jh-uf" aria-hidden="true"></i>' : "");
  const JH_UF_SIGN = { "act:bounties": "jh:sign:bounties", "act:smith": "jh:sign:smith", "act:arena": "jh:sign:arena", "act:dadian": "jh:sign:dadian", "act:market": "jh:sign:market" };
  const JH_UF_ACTS = { train: "jh:sortie", duty: "jh:duty" };
  const JH_UF_KEYS = ["jh:peers", ...Object.values(JH_UF_ACTS), ...Object.values(JH_UF_SIGN)];
  if (typeof registerDot === "function") registerDot({ id: "jh-unfold", at: "jianghu", on: () => !!(S.main && S.main.jianghu) && JH_UF_KEYS.some((k) => typeof unfoldDot === "function" && unfoldDot(k)) });
  let jhUfHooked = false;
  function jhUfHook() { // 第一次畫新排法時才掛（排在殼的點擊之後；開關關著一個監聽都不多）
    if (jhUfHooked || typeof document === "undefined" || !document.addEventListener) return;
    jhUfHooked = true;
    document.addEventListener("click", (ev) => { // 點開那一格（行動牌、招牌、這裡的人）：那一個鍵看過了
      try {
        const el = ev.target && typeof ev.target.closest === "function" ? ev.target.closest("[data-uf]") : null;
        if (el && el.dataset && el.dataset.uf && typeof ufSeen === "function") ufSeen([el.dataset.uf]);
      } catch (e) { /* 不擋其他的點擊 */ }
    });
  }
  const jhOn = (m) => !!(m && m.jianghu && m.jianghu.on) && typeof revampOn === "function" && revampOn(m) && !(typeof bpOn === "function" && bpOn(m) && !jhBpMuster(m));

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
    // 「丹 N」不在這一行（Joy 2026-11-25「可以」）：點體力那一條拉起體力的小卡，在那裡服；體力不夠被擋下來時提示上直接有「服一顆」
    const pill = "";
    const purse = JH_PURSE && shown("silver") ? `<div class="jh-purse"><span><em>銀</em>${s.silver | 0}</span>${s.xinshen ? `<span><em>${esc(s.xinshen.name)}</em>${s.xinshen.now | 0}</span>` : ""}</div>` : "";
    const when = s.calendar ? s.calendar.text : `第${s.day}天 ${s.clock}`;
    const help = S.stamOpen && s.stamina_help && s.stamina_help.length
      ? `<div class="jh-help" id="stam-help">${s.stamina_help.map((t) => `<p>${esc(t)}</p>`).join("")}</div>` : "";
    return `<header class="jh-st">
        <button class="jh-me" data-act="hero-attrs" aria-label="看屬性">${esc((s.name || "").slice(0, 1))}${s.stat_points ? dotHtml(true) : ""}</button>
        <div class="jh-nm"><b>${esc(s.name || "")}</b><small>${s.level | 0} 級・${esc(jhMySide(m) || JH_FREE)}${s.anonymous ? "・匿名" : ""}</small></div>
        <div class="jh-vit"${shown("stamina") ? ` data-act="jh-sheet" data-sheet="stam" role="button" tabindex="0" aria-label="${JH_STAM}"` : ""}>${vit}<span class="jh-tm">${esc(when)}</span></div>${pill}
        <button class="jh-gear" data-act="sheet" aria-label="設定">⚙${dotHtml(dotAt("sheet"))}</button>
      </header>${purse}${help}`;
  }

  // 場景圖：閒著時是地點的圖；眼前不是地點（少見：伺服器給的是別的圖）時用上一張地點的圖，都沒有就只有紙
  function jhArtSrc(m) {
    if (m.art && m.art.kind === "place") return m.art.src;
    return S.lastPlaceArt || "";
  }

  // 旁白：場景描述（地名那一行已經題在畫上，不寫兩次）收成兩行，點了攤開；剛發生的事一行（照舊點了攤開整則）
  function jhProseHtml(m, inner, now, one = false) { // one：有眼下卡時描述收成一行（點了展開），讓整排招牌留在第一屏
    const open = !!S.sceneRvOpen;
    const tappable = !/<button|<form/.test(inner);
    return `<div class="jh-prose">${inner ? `<div class="jh-desc${open || !tappable ? "" : ` clamp${one ? " one" : ""}`}"${tappable ? ` data-act="rv-scene" role="button" tabindex="0" aria-expanded="${open}"` : ""}>${inner}</div>` : ""}${now ? `<div class="jh-now">${now}</div>` : ""}</div>`;
  }

  // 地名底下那一行「剛剛」：前面的標題（「特殊頓悟」「打點・宛城」）不印，只留那一句話；只有標題、沒有句子的不畫（PM 11/25）
  function jhNowClean(html) {
    // 標題拿掉、結果小章（成功、失敗……）留著：收成一行時照舊排在最右邊（Joy 2026-10-27「看不出是成功還是失敗」）
    const out = String(html || "").replace(/<div class="tx-head">([\s\S]*?)<\/div>/, (all, inner) => { const tag = inner.match(/<span class="tx-tag">[\s\S]*?<\/span>/); return tag ? `<div class="tx-head">${tag[0]}</div>` : ""; }).replace(/<div class="tx-line[^"]*">\s*【[^】<]*】\s*<\/div>/g, "");
    return /<div class="tx-line/.test(out) && out.replace(/<div class="tx-when">[\s\S]*?<\/div>/, "").replace(/<[^>]+>/g, "").trim() ? out : "";
  }
  const jhNowLine = (m) => { const now = jhNowClean(m.now); return now && typeof nowBlock === "function" ? nowBlock({ ...m, card: null, now }) : ""; };

  // 旁白開頭的「〔戰火〕」：小印已經寫了，不寫兩次（一件事一頁只出現一次）
  function jhNoSealTwice(inner, seal) {
    return seal ? String(inner || "").replace(new RegExp(`^(\\s*<p[^>]*>)\\s*〔${seal}〕\\s*`), "$1") : inner;
  }

  // 四顆行動牌：先沿用原本行動列的格子（按的東西、灰著的原因、點開的卡都照舊），樣子換成牌子；「移動」改叫「行路」
  // 第四批：第三格「交友」換成「軍務」（點人就是交友），「行路」點了拉起行路清單（不在行動牌底下攤一排）
  function jhActs(menu, m, kinds) {
    const duty = jhDutyCell(m, kinds);
    let html = String(menu || "").replace(/<b>移動<\/b>/, "<b>行路</b>") // 待 joy 潤：行路（施工單第 5 條）
      .replace(/<button class="act-ink[^"]*" data-key="social"[\s\S]*?<\/button>/, () => duty)
      .replace(/data-act="wheel" data-key="move" aria-expanded="[^"]*"/, 'data-act="jh-sheet" data-sheet="road"');
    for (const [key, uf] of Object.entries(JH_UF_ACTS)) { // 出陣、軍務：新角色還沒長出來的不畫；剛長出來的亮一顆紅點
      const cell = new RegExp(`<button class="act-ink[^"]*" data-key="${key}"[\\s\\S]*?<\\/button>`);
      html = jhShown(uf) ? html.replace(cell, (b) => b.replace(/^<button /, `<button data-uf="${uf}" `).replace(/<\/button>$/, `${jhUfDot(uf)}</button>`)) : html.replace(cell, "");
    }
    return html;
  }

  const jhActsWrap = (html) => { const n = (html.match(/<button class="act-ink|<button data-uf="[^"]*" class="act-ink/g) || []).length; return `<div class="jh-acts${n && n < 4 ? ` n${n}` : ""}">${html}</div>`; };

  // ── 4. 眼下（第二批）：一張卡只放現在最該理的一件，一顆主要的鈕加「稍後」；其餘收成右上「另有 N 件 ›」，點了從底下拉起清單 ──
  // 一件：{ key, seal（小印的字）, title, sub, btn（主鈕的字）, attrs（主鈕的 data-act…）}；wait 的是現在推不動的（收在清單最底下）
  const JH_LATER = "稍後"; // 待 joy 潤
  const JH_GUIDE_OK = "知道了"; // 待 joy 潤
  // 老石那一句說的去處 → 卡上的主鈕（[認的字, 鈕上的字, 選項 id, 或拉起哪一層]）
  // 第五格是「此地做得了嗎」看哪一顆選項（暗著就是做不了）；第六格是做不了時說去哪裡做的那一句（PM 11/25：做不了的不排第一則，只剩它就說去哪裡）
  const JH_GUIDE_GO = [[/今日軍令|軍令/, "看今日軍令", "", 'data-act="jh-sheet" data-sheet="duty"', "act:duty", "回到自家的地盤，就看得到今日軍令。"], [/探索/, "去探索", "act:explore", "", "", "到了城外，再去探索。"], [/出陣/, "去出陣", "act:train", "", "", "到了能出陣的地方，再去出陣。"],
    [/行路|前往|動身/, "看去處", "", 'data-act="jh-sheet" data-sheet="road"']]; // 待 joy 潤
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
    return { key: it.key, seal: it.seal, title, sub, wait: !!it.wait, btn: name && name.length <= 4 && !title.includes(name) && !it.title.includes(name) ? name : JH_GO[kind], attrs: it.go ? tkGoAttrs(it) : "" };
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
    let guideFar = null; // 老石說的那件此地做不了：排到最後（別的都沒有時才是第一則）
    const s = m.status || {};
    const slim = typeof codexSlim === "function" && codexSlim(m);
    const w = m.week_card;
    // 換週那一刻、這一回的大事在集結或開打：兩軍態勢自己變成眼下的一件，排最前（PM 2026-11-25；平常只在清單裡）
    if (w && slim && typeof codexWeekShow === "function" && codexWeekShow(m)) {
      const live = !!(w.chapter && w.chapter.live);
      on.push({ key: `w:${w.when}`, seal: live ? JH_WEEK_LIVE : JH_WEEK_SEAL, title: w.theme || w.when, sub: [jhTugWords(m), w.when].filter(Boolean).join("・"), btn: JH_LOOK, attrs: 'data-act="cx-tk-why"', alt: { label: JH_GUIDE_OK, attrs: `data-act="jh-later" data-key="w:${esc(w.when)}"` } }); // 第二顆「知道了」（PM 11/25）
    }
    const g = m.guide; // 說書人、老石的話（新角色那一包說好：開場那幾句排在眼下最前面，不另畫一個框）
    if (g && g.text && !g.pending && !(typeof pro === "function" && pro()) && (g.end || typeof guideShut !== "function" || typeof guideKey !== "function" || guideShut() !== guideKey(g))) {
      const first = String(g.text).split(/(?<=[。！？])/)[0];
      const rest = g.line ? g.text : String(g.text).slice(first.length);
      // 主鈕是那件事本身（PM 11/25：下一步的鈕在卡上）：伺服器標了要亮的那一顆（guide.glow、初入江湖的鍵）就按它；旁邊一顆「知道了」
      const ids = [...(g.glow || []), ...(((m.onboard && m.onboard.glow) || []).map((k) => `act:${k}`))];
      let go = (m.options || []).find((o) => o.enabled && ids.includes(o.id));
      const ok = `data-act="${g.end ? "guide-ack" : "guide-shut"}"`;
      let btn = "", attrs = "", where = "";
      if (go) { const name = optParts(go)[0]; btn = /^[去看]/.test(name) ? name : `去${name}`; attrs = `data-act="choose" data-id="${esc(go.id)}"`; }
      else { // 沒標要亮哪一顆：照那一句說的去處認（「看看『今日軍令』」→ 拉起軍務）
        const said = `${g.line || ""}${first}`;
        const hit = JH_GUIDE_GO.find(([re]) => re.test(said));
        const opt = hit && hit[2] && (m.options || []).find((o) => o.enabled && o.id === hit[2]);
        const gate = hit && hit[4] && (m.options || []).find((o) => o.id === hit[4]);
        if (hit && (!hit[2] || opt) && !(gate && !gate.enabled)) { btn = hit[1]; attrs = hit[3] || `data-act="choose" data-id="${esc(hit[2])}"`; go = true; }
        else if (hit && hit[5]) where = hit[5];
      }
      const item = { key: `g:${typeof guideKey === "function" ? guideKey(g) : g.text}`, seal: g.speaker || "", title: g.line || first,
        sub: [where, rest.trim(), ...(g.done || []).filter((d) => !d.startsWith("✔"))].filter(Boolean).join("　"),
        btn: go ? btn : JH_GUIDE_OK, attrs: go ? attrs : ok, alt: go ? { label: JH_GUIDE_OK, attrs: ok } : null, guide: true, far: !!where };
      if (where) guideFar = item; else on.unshift(item);
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
    if (guideFar) on.push(guideFar);
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
    // 開場的話說完之後，新角色那一包的「剛長出來」卡先排（unfoldNowHtml，web/unfold.js）：它在就只畫它，不算進「另有 N 件」
    const uf = !(on[0] && on[0].guide) && typeof unfoldNowHtml === "function" ? unfoldNowHtml(m) : "";
    if (uf) return uf;
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
        <div class="jh-eye-row"><button class="btn jh-eye-go" ${top.attrs}>${esc(top.btn)}</button>${top.alt ? `<button class="btn jh-eye-later" ${top.alt.attrs}>${esc(top.alt.label)}</button>` : on.length > 1 && !top.guide ? `<button class="btn jh-eye-later" data-act="jh-later" data-key="${esc(top.key)}">${JH_LATER}</button>` : ""}</div>
      </section>`;
  }

  // 體力的小卡（點狀態行的體力條；體力不夠被擋下來的那一刻也拉起它，最上面寫被擋的那一句）：還有幾顆、今天還能服幾顆、服一顆
  const JH_STAM = "體力"; // 待 joy 潤
  const JH_PILL_LEFT = "{name}還有 {n} 顆"; // 待 joy 潤
  const JH_PILL_TODAY = "今天還能服 {n} 顆"; // 待 joy 潤
  const JH_PILL_TAKE = "服一顆"; // 待 joy 潤
  const JH_PILL_FULL = "體力是滿的"; // 待 joy 潤
  const JH_PILL_DONE = "今天服夠了"; // 待 joy 潤
  const JH_PILL_NONE = "身上沒有回體丹了"; // 待 joy 潤
  function jhStamBody(m) {
    const s = m.status || {}, pl = s.pills;
    const why = S.jhStamWhy ? `<div class="jh-say"><b>${esc(S.jhStamWhy)}</b></div>` : "";
    const bar = `<div class="jh-stam">${jhBar("stam", "體", s.stamina, s.stamina_max)}</div>`;
    if (!pl) return `${why}${bar}<p class="jh-none">${JH_PILL_NONE}</p>`;
    const lines = [pl.refill ? "" : JH_PILL_LEFT.replace("{name}", pl.name || "").replace("{n}", pl.count | 0), "today" in pl && !pl.refill ? JH_PILL_TODAY.replace("{n}", pl.today | 0) : ""].filter(Boolean);
    const off = pl.full ? JH_PILL_FULL : !pl.refill && pl.today === 0 ? JH_PILL_DONE : "";
    const go = off ? `<button class="btn jh-do off wide" data-act="opt-why" data-why="${esc(off)}。" aria-disabled="true">${esc(pl.refill || JH_PILL_TAKE)}<small>${esc(off)}</small></button>`
      : `<button class="btn jh-do wide primary" data-act="pill">${esc(pl.refill || JH_PILL_TAKE)}</button>`;
    return `${why}${bar}${lines.length ? `<p class="jh-pills">${lines.map(esc).join("<br>")}</p>` : ""}${go}`;
  }
  // 灰著的鈕上寫的原因是體力不夠、身上又有丹：點了拉起體力的小卡（不是只跳一句），卡上就能服
  const JH_STAM_WHY = /data-act="opt-why"((?: data-id="[^"]*")?) data-why="([^"]*體力[^"]*)"/g;
  const JH_STAM_LOW = "體力不夠{name}"; // 待 joy 潤：行動牌灰著、牌上寫「體力不夠」時，小卡最上面那一句
  const jhStamWhy = (m, html) => (m.status && m.status.pills
    ? String(html || "").replace(/<button class="act-ink[^"]*"[^>]*>[\s\S]*?<\/button>/g, (cell) => (/<small>體力不夠<\/small>/.test(cell)
      ? cell.replace(/data-act="opt-why" data-why="[^"]*"/, `data-act="jh-stam" data-why="${esc(JH_STAM_LOW.replace("{name}", (cell.match(/<b>([^<]*)<\/b>/) || [, ""])[1]))}"`) : cell))
      .replace(JH_STAM_WHY, 'data-act="jh-stam"$1 data-why="$2"') : html);

  // ── 7. 這裡的去處與軍務（第四批）：此地可為拆成兩半——進得去的地方（直書木牌一排）與差事（收進「軍務」那一格，點了拉起清單）。
  // 選項只認前綴（伺服器沒有「這一顆是哪一類」的欄位）；兩類都不是的（義聚、探望……）排在軍務清單的「此地還能」。
  const JH_PLACE = /^(act:(bounties|smith|tavern|arena|heal|market|dadian|feast|donate|silver_donate)$|feast:join:|learn:|sect:)/;
  const JH_DUTY = /^(act:duty$|act:convoy$|act:works|fs:|ambush:|opp:|plan:(help|block):|battle:|defect:|works:|seal:)/;
  const JH_SKIP = /^(aid:guard:|aid:rally:|act:challenge:|jieyi:(?:yes|no):|hire:|invite:|faction:|act:call$|call:|act:socialize$)/; // 人物卡、眼下、投靠卡已經有的
  const JH_SIGN_GROUP = [[/^learn:/, "學藝"], [/^feast:join:/, "赴宴"], [/^sect:/, "拜師"]]; // 待 joy 潤：同類一塊牌子
  const JH_PLACES_HEAD = "這裡的去處"; // 待 joy 潤
  const JH_NO_SHOP = "荒郊野外，沒有店家。"; // 待 joy 潤
  const JH_DUTY_NAME = "軍務"; // 待 joy 潤
  const JH_DUTY_SEAL = "令"; // 待 joy 潤：軍務那一格沒有圖，寫一個字
  const JH_DUTY_N = "{n} 件"; // 待 joy 潤
  const JH_DUTY_FREE = "投靠後才有"; // 待 joy 潤：散人沒有軍務（提案：點了拉起投靠的三方卡）
  const JH_DUTY_NONE = "眼下沒有"; // 待 joy 潤
  const JH_MORE_HERE = "此地還能"; // 待 joy 潤
  const JH_GO_DO = "去做"; // 待 joy 潤
  function jhKinds(m, extras) {
    const places = [], duties = [], others = [];
    const slim = typeof codexSlim === "function" && codexSlim(m); // 進行中開著時未了之事都在眼下的清單裡
    for (const o of extras) {
      if (JH_SKIP.test(o.id) || (slim && o.id.startsWith("story:")) || o.id.startsWith("move:") || /^act:(explore|train|rest|move|practice)$/.test(o.id) || o.id.startsWith("explore:")) continue;
      (JH_PLACE.test(o.id) ? places : JH_DUTY.test(o.id) ? duties : others).push(o);
    }
    return { places, duties, others };
  }
  const jhBase = (o) => optParts(o)[0].replace(/（.*$/, "").trim();
  function jhSignsHtml(m, kinds) {
    const signs = [];
    for (const o of kinds.places) {
      const uf = JH_UF_SIGN[o.id];
      if (uf && !jhShown(uf)) continue;
      const g = JH_SIGN_GROUP.find(([re]) => re.test(o.id));
      if (g) {
        const same = kinds.places.filter((x) => g[0].test(x.id));
        if (same[0] !== o) continue;
        if (same.length > 1) {
          const on = same.filter((x) => x.enabled).length;
          signs.push(`<button class="jh-sign${on ? "" : " off"}" data-act="here-all" data-ids="${esc(same.map((x) => x.id).join(" "))}" data-title="${esc(g[1])}"><b>${esc(g[1])}</b><u>${on || same.length}</u></button>`);
          continue;
        }
      }
      const [, detail] = optParts(o);
      const n = /^(\d+) 張$/.exec(detail || "");
      const name = g && kinds.places.filter((x) => g[0].test(x.id)).length === 1 ? g[1] : jhBase(o);
      const attrs = o.enabled ? `data-act="choose" data-id="${esc(o.id)}"` : `data-act="opt-why" data-id="${esc(o.id)}" data-why="${esc(o.note || (detail ? `${detail}。` : ""))}" aria-disabled="true"`;
      signs.push(`<button class="jh-sign${o.enabled ? "" : " off"}" ${attrs}${uf ? ` data-uf="${uf}"` : ""} aria-label="${esc(optParts(o).join("・"))}"><b>${esc(name)}</b>${n ? `<u>${n[1]}</u>` : ""}${uf ? jhUfDot(uf) : ""}</button>`);
    }
    return `<section class="jh-blk jh-places"><h3>${JH_PLACES_HEAD}</h3>${signs.length ? `<div class="jh-signs">${signs.join("")}</div>` : `<p class="jh-noshop">${JH_NO_SHOP}</p>`}</section>`;
  }
  // 軍務那一格：自己陣營的差事（巡哨、請纓……）幾件做得了；散人沒有軍務時灰著寫「投靠後才有」，點了拉起投靠的三方卡（提案）
  // 還沒投靠的人（有陣營的季）：這一格是「投靠」牌（Joy 11/25「可以改」）。此地投得了就亮、按了走原本的投靠確認；投不了就暗著，按了說去哪裡投
  const JH_JOIN_NAME = "投靠"; // 待 joy 潤
  const JH_JOIN_SEAL = "投"; // 待 joy 潤：牌面的圖還沒畫，先寫一個字
  const JH_JOIN_HERE = "此地可投{side}"; // 待 joy 潤
  const JH_JOIN_AWAY = "不在此地"; // 待 joy 潤
  const JH_JOIN_WHERE = "投靠要到那一方的地方：{where}。"; // 待 joy 潤
  function jhJoinCell(m) {
    const sc = m.sides_card;
    const here = (m.options || []).filter((o) => o.enabled && /^faction:(?!ally:|lean:|confirm$|cancel$)/.test(o.id));
    const name = (o) => { const c = sc.cols.find((x) => `faction:${x.id}` === o.id); return c ? c.name : optParts(o)[0].replace(/^投靠/, ""); };
    if (here.length) {
      const attrs = here.length === 1 ? `data-act="choose" data-id="${esc(here[0].id)}"` : 'data-act="jh-sheet" data-sheet="join"';
      return `<button class="act-ink" data-key="duty" ${attrs}><span class="jh-ink-ch" aria-hidden="true">${JH_JOIN_SEAL}</span><b>${JH_JOIN_NAME}</b><small>${esc(JH_JOIN_HERE.replace("{side}", here.map(name).join("、")))}</small></button>`;
    }
    const near = (c) => { const j = (c.join_at || []).slice().sort((a, b) => (a.minutes | 0) - (b.minutes | 0))[0]; return j ? j.name : (c.where || [])[0]; }; // 最近的那一處
    const where = sc.cols.filter((c) => near(c)).map((c) => `${c.name}最近在${near(c)}`).join("、");
    const why = where ? JH_JOIN_WHERE.replace("{where}", where) : "";
    return `<button class="act-ink off" data-key="duty" data-act="opt-why" data-why="${esc(why)}" aria-disabled="true"><span class="jh-ink-ch" aria-hidden="true">${JH_JOIN_SEAL}</span><b>${JH_JOIN_NAME}</b><small>${JH_JOIN_AWAY}</small></button>`;
  }
  function jhDutyCell(m, kinds) {
    if (!jhMySide(m) && m.sides_card && !m.sides_card.joined && (m.sides_card.cols || []).length) return jhJoinCell(m);
    const all = [...kinds.duties, ...kinds.others], on = all.filter((o) => o.enabled).length;
    const free = !jhMySide(m);
    const sub = all.length ? JH_DUTY_N.replace("{n}", on || all.length) : free ? JH_DUTY_FREE : JH_DUTY_NONE;
    const attrs = all.length ? 'data-act="jh-sheet" data-sheet="duty"' : free && m.sides_card ? 'data-act="jh-sheet" data-sheet="sides"' : `data-act="opt-why" data-why="${esc(sub)}。" aria-disabled="true"`;
    return `<button class="act-ink${on ? "" : " off"}" data-key="duty" ${attrs}><span class="jh-ink-ch" aria-hidden="true">${JH_DUTY_SEAL}</span><b>${JH_DUTY_NAME}</b><small>${esc(sub)}</small>${on ? `<i class="jh-ink-n">${on}</i>` : ""}</button>`;
  }
  function jhOptRow(o, btn = JH_GO_DO) {
    const [label, detail] = optParts(o);
    return `<div class="jh-row${o.enabled ? "" : " wait"}"><span class="jh-row-t"><b>${esc(label)}</b>${detail ? `<small>${esc(detail)}</small>` : ""}</span>${o.enabled
      ? `<button class="btn small jh-row-go" data-act="choose" data-id="${esc(o.id)}">${esc(btn)}</button>`
      : `<button class="btn small jh-row-go off" data-act="opt-why" data-why="${esc(o.note || (detail ? `${detail}。` : ""))}" aria-disabled="true">${esc(btn)}</button>`}</div>`;
  }
  // 同一類一個目標一顆的（設伏每條路一顆）收成一列，點開才挑哪一條（Joy 2026-11-10「同類型的 例如設伏 應該只有一個按鈕，點開才選設伏在哪」）
  const JH_DUTY_GROUP = [[/^ambush:set:/, "設伏"]]; // 待 joy 潤
  const JH_DUTY_PICK = "挑一處"; // 待 joy 潤
  function jhDutyRows(list) {
    const out = [];
    for (const o of list) {
      const g = JH_DUTY_GROUP.find(([re]) => re.test(o.id));
      const same = g ? list.filter((x) => g[0].test(x.id)) : [];
      if (same.length > 1) {
        if (same[0] !== o) continue;
        const on = same.filter((x) => x.enabled).length;
        out.push(`<details class="jh-group"><summary class="jh-row${on ? "" : " wait"}"><span class="jh-row-t"><b>${esc(g[1])}</b><small>${esc(JH_DUTY_N.replace("{n}", on || same.length))}</small></span><span class="btn small jh-row-go">${JH_DUTY_PICK}</span></summary>`
          + `${same.map((x) => jhOptRow({ ...x, label: optParts(x)[0].replace(new RegExp(`^${g[1]}[・：:]?`), "") || optParts(x)[0] })).join("")}</details>`);
        continue;
      }
      out.push(jhOptRow(o));
    }
    return out.join("");
  }
  function jhDutyBody(m, kinds) {
    const d = jhDutyRows(kinds.duties), x = jhDutyRows(kinds.others);
    return `${d}${x ? `${d ? `<h4 class="jh-sub">${JH_MORE_HERE}</h4>` : ""}${x}` : ""}` || `<p class="jh-none">${JH_DUTY_NONE}</p>`;
  }
  // 行路清單：有事要辦的地方排最上面、標是哪一件；其餘是鄰近；最底下打開輿圖
  const JH_ROAD = "行路"; // 待 joy 潤
  const JH_ROAD_GO = "前往"; // 待 joy 潤
  const JH_ROAD_MAP = "打開輿圖"; // 待 joy 潤
  const JH_ROAD_NONE = "四下沒有路。"; // 待 joy 潤
  const JH_GO_FAIL = "沒能出發："; // 待 joy 潤
  function jhRoadBody(m) {
    const moves = (m.options || []).filter((o) => o.id.startsWith("move:"));
    const marks = {};
    for (const t of (m.codex && m.codex.track) || []) if (t.loc && !marks[t.loc]) marks[t.loc] = { seal: t.kind, what: t.title, name: t.where };
    for (const e of m.errands || []) if (e.target && e.target.id && !marks[e.target.id]) marks[e.target.id] = { seal: "託付", what: e.text, name: e.target.name };
    const row = (mk, name, detail, go) => `<div class="jh-row">${mk ? jhSealHtml(mk.seal) : ""}<span class="jh-row-t"><b>${esc(name)}</b><small>${esc([mk ? mk.what : "", detail].filter(Boolean).join("・"))}</small></span>${go}</div>`;
    const rows = moves.map((o) => {
      const loc = o.id.slice(5), mk = marks[loc];
      const [label, detail] = optParts(o);
      return { mk, html: row(mk, label.replace(/^前往\s*/, ""), detail, o.enabled
        ? `<button class="btn small jh-row-go" data-act="choose" data-id="${esc(o.id)}">${JH_ROAD_GO}</button>`
        : `<button class="btn small jh-row-go off" data-act="opt-why" data-why="${esc(o.note || (detail ? `${detail}。` : ""))}" aria-disabled="true">${JH_ROAD_GO}</button>`) };
    });
    // 有事要去、卻不在鄰近的地方（例：人在宛城，主線要去長社）：也列上來、排最上面，按了照輿圖的出發走（步行）
    const near = new Set(moves.map((o) => o.id.slice(5)));
    const ways = (m.jianghu && m.jianghu.ways) || {};
    for (const [loc, mk] of Object.entries(marks)) {
      if (near.has(loc) || !ways[loc]) continue;
      rows.push({ mk, html: row(mk, mk.name || loc, `${JH_WALK}${ways[loc]}`, `<button class="btn small jh-row-go" data-act="jh-go" data-dest="${esc(loc)}" data-mode="walk">${JH_ROAD_GO}</button>`) });
    }
    rows.sort((a, b) => (a.mk ? 0 : 1) - (b.mk ? 0 : 1));
    return `${rows.length ? rows.map((r) => r.html).join("") : `<p class="jh-none">${JH_ROAD_NONE}</p>`}<button class="jh-why" data-act="jh-map">${JH_ROAD_MAP}<i aria-hidden="true">›</i></button>`;
  }

  // ── 第五批：其他時刻。事件選擇中、趕路中整頁換掉（設計稿 k、l）；行動、人、去處都收起來，選完、到了才回來 ──
  const JH_WALK = "步行"; // 待 joy 潤
  const JH_EV_SEAL = "遭遇"; // 待 joy 潤：事件標題旁那一枚直書小印（伺服器沒帶種類時）
  const JH_EV_MORE = "前文"; // 待 joy 潤
  const JH_ON_ROAD = "往{to}的路上"; // 待 joy 潤
  const JH_ROAD_LEFT = "{mode}・還有 {n} 分鐘"; // 待 joy 潤
  const JH_ROAD_NEXT = "下一站{name}"; // 待 joy 潤
  const JH_DASH = "疾行"; // 待 joy 潤
  const JH_BACK = "折返"; // 待 joy 潤
  const JH_ROAD_DO = "路上順手"; // 待 joy 潤
  const jhEvNow = (m) => (m.options || []).some((o) => /^choice:/.test(o.id));
  // 這一刻要不要整頁換掉：開關開著、介面第二版、不在序章與新手教學、不在決戰面板與戰鬥卡
  function jhMomentHtml(m, p) {
    if (!(m && m.jianghu && m.jianghu.on)) return "";
    if (!(typeof uiV2 === "function" && uiV2()) || (typeof pro === "function" && pro()) || (typeof onb === "function" && onb())) return "";
    if (typeof bpOn === "function" && bpOn(m) && !jhBpMuster(m)) return "";
    try {
      const take = m.jianghu.take;
      if (jhCardOn(m)) return jhCardPage(m, p);
      const ids = (m.options || []).map((o) => o.id);
      if (ids.includes("season:preparing")) return jhPrepPage(m, p);
      if (ids.some((i) => i === "season:resting")) return jhRestPage(m, p);
      if (jhBpMuster(m) && !m.on_road && typeof musterJoins === "function" && musterJoins(m).length && S.jhMusterSkip !== m.battle_panel.name && !take && !jhEvNow(m)) return jhMusterPage(m, p);
      if (ids.includes("act:break") && m.status && m.status.busy_hours != null) return jhBusyPage(m, p);
      // 戰報看過了（往下看）：「剛剛」換回一行，戰報收進見聞
      const q = m.card ? { ...p, now: "", nowRaw: m.now || "" } : { ...p, nowRaw: m.now || "" };
      if (m.on_road && m.jianghu.road) return jhRoadPage(m, q);
      if (m.on_road || m.shop) return "";
      if (jhEvNow(m)) return jhEvPage(m, q);
      if (take && !m.talk) return jhTakePage(m, m.card && take.slot === "duel" ? p : q, take);
    } catch (e) { if (typeof console !== "undefined") console.error(e); }
    return "";
  }
  function jhMomentHero(m, title, seal, src) {
    try { document.documentElement.classList.add("jh2"); } catch (e) { /* 測試裡沒有 document */ }
    return `<section class="jh-hero">${src ? `<img class="jh-art" src="${esc(src)}" alt="" decoding="async">` : '<div class="jh-art none"></div>'}
        ${jhStatusHtml(m)}
        <div class="jh-pl">${seal ? `<span class="jh-seal">${esc(seal)}</span>` : ""}<h1>${esc(title)}</h1></div>
      </section>`;
  }
  // 選項底下那一句把屬性與數字拿掉、只留話（「統御 108：這點苦頭，你吃得消。」→「這點苦頭，你吃得消。」；Joy 11/10 不把數字寫給玩家讀）
  const jhNoOdds = (menu) => String(menu || "").replace(/(<small class="opt-note ev-odds[^"]*">)[^<：]*\d[^<：]*：/g, "$1");
  // 一幕的頁（事件、接管選單的每一種共用，第六批 PM「不另畫新樣子」）：圖、小印與標題、最後一段字；前文收起來，點了攤開；選項照原本那一排（含自己說）
  function jhStagePage(m, p, x) {
    const more = x.before ? `<button class="jh-ev-more" data-act="jh-ev-more" aria-expanded="${!!S.jhEvMore}">${JH_EV_MORE}<i aria-hidden="true">${S.jhEvMore ? "︿" : "﹀"}</i></button>${S.jhEvMore ? `<div class="jh-ev-before">${x.before}</div>` : ""}` : "";
    return `<div class="jh-page jh-ev${x.cls ? ` ${x.cls}` : ""}">${p.ckPop || ""}${jhMomentHero(m, x.title, x.seal, x.src)}<div class="jh-ev-txt">${more}${x.last}</div>${x.extra || ""}<div class="jh-ev-opts">${jhNoOdds(p.menu)}${p.senseNotes || ""}${p.free || ""}</div></div>`; // 感悟的做法底下兩行小字（同舊頁）
  }
  // 場景卡的段落：第一段只有粗體標題的拿掉（標題在圖上）
  function jhParas(m, noQuote) { // noQuote：接管選單那一頁不收引言框裡的提點（感悟的「選錯了做法……」那一句不當正文）
    const paras = String(m.scene || "").replace(noQuote ? /<blockquote>[\s\S]*?<\/blockquote>/g : /$^/, "").match(/<p>[\s\S]*?<\/p>/g) || [];
    // 標題段後面跟著地形（「<strong>有所感・鐵匠鋪</strong>（城鎮）」）：地形接在標題後面，這一段不當正文
    const head = (paras[0] || "").trim().match(/^<p><strong>([^<]*)<\/strong>(（[^<）]*）)?<\/p>$/);
    const title = head ? `${head[1]}${head[2] || ""}` : ((paras[0] || "").match(/<strong>(.*?)<\/strong>/) || [])[1] || "";
    return { title, body: paras.filter((x, i) => !(i === 0 && head) && !/^<p><strong>[^<]*<\/strong><\/p>$/.test(x.trim())) };
  }
  // 事件：最後一段字；前文是剛剛那一則與這一幕前面的段落
  function jhEvPage(m, p) {
    const { title, body } = jhParas(m);
    const last = body.pop() || "";
    const src = m.art && m.art.kind === "event" && m.art.src ? m.art.src : jhArtSrc(m);
    return jhStagePage(m, p, { title: (m.art && m.art.title) || title, seal: m.jianghu.event || JH_EV_SEAL, src, last, before: `${p.now || ""}${body.join("")}` });
  }
  // 接管選單的那一刻（撞見、感悟、同伴、投靠、求見、伏筆、單挑、章回與奇事的答題……）：同一種頁。
  // 場景卡是這一幕自己的（感悟、答題、談著……）就照事件取最後一段；場景卡只是地點（撞見孩子、異聞）時，這一幕的話在「剛剛」最後一行
  const jhTxLines = (html) => String(html || "").match(/<div class="tx-line[^"]*">[\s\S]*?<\/div>/g) || [];
  const jhTxP = (line) => `<p>${line.replace(/^<div[^>]*>/, "").replace(/<\/div>$/, "")}</p>`;
  function jhTakePage(m, p, take) {
    // 場景卡只是地點（撞見孩子、異聞）：沒有 art 時看場景的標題是不是地名（感悟的「有所感・鐵匠鋪」是這一幕自己的）
    const placeOnly = m.art ? m.art.kind === "place" : (() => { const t = jhParas(m).title.replace(/（.*?）/g, "").trim(); return !t || t === jhPlaceName(m); })();
    const plain = (h) => String(h).replace(/<[^>]+>/g, "").trim();
    // 得失那一行（數字）與「獲得…」不收進前文：完整的在戰報與江湖紀錄
    const lines = jhTxLines(p.nowRaw).filter((l) => !/tx-new/.test(l) && !/^得：|^失：|　失：/.test(plain(l))).map(jhTxP);
    const { title: t2, body } = jhParas(m, true);
    let last, rest;
    if (take.slot === "duel" && m.card) {
      // 卡頭已經寫了「第 N 回合」，底下那一句句首的同一個「第 N 回合」拿掉（PM 11/25）
      const n = (String(m.card).replace(/<li[\s\S]*$/, "").match(/第\s*(\d+)\s*(?:／\s*\d+\s*)?回合/) || [])[1];
      const card = n ? String(m.card).replace(new RegExp(`(<li[^>]*>)第\\s*${n}\\s*回合[：:　\\s]*`, "g"), "$1") : m.card;
      last = `${body.pop() || ""}<div class="card battle-card">${fightCard(card, m.card_id)}</div>`; rest = body;
    }
    else if (placeOnly) { last = lines.pop() || body.pop() || ""; rest = lines; }
    else { last = body.pop() || ""; rest = [...lines, ...body]; }
    const title = take.title || (placeOnly ? "" : t2) || (m.art && m.art.title) || t2 || "";
    // 前文：跟這一段、標題重複的與只有【標題】的那一行不收
    const seen = new Set([plain(last), title, `【${title}】`]);
    const before = rest.filter((h) => { const x = plain(h); if (!x || seen.has(x) || /^【[^】]*】$/.test(x)) return false; seen.add(x); return true; }).join("");
    const src = take.art || (m.art && m.art.src) || take.place || jhArtSrc(m);
    return jhStagePage(m, p, { title, seal: take.seal, src, last, before, cls: `jh-tk jh-tk-${take.slot}` });
  }

  // ── 第六批：全服的時刻與閉關（設計稿 q、r、s）──
  const JH_PREP_SEAL = "籌備"; // 待 joy 潤
  const JH_PREP_TITLE = "江湖未開"; // 待 joy 潤
  const JH_PREP_TEXT = "天下還沒亂起來。開季的那一刻，江湖就動起來了。"; // 待 joy 潤
  const JH_PREP_GO = "先看看你的武學"; // 待 joy 潤
  const JH_REST_SEAL = "休季"; // 待 joy 潤
  const JH_REST_TITLE = "這一季收了"; // 待 joy 潤
  const JH_REST_TEXT = "下一季開季之前，江湖暫歇。武學、裝備、商城照常看得到。"; // 待 joy 潤
  const JH_REST_ZHUAN = "讀你的傳"; // 待 joy 潤
  const JH_REST_ALL = "這一季的始末"; // 待 joy 潤
  const JH_BUSY_SEAL = "閉關"; // 待 joy 潤
  const JH_BUSY_TITLE = "閉關中"; // 待 joy 潤
  const JH_BUSY_LEFT = "還要約 {h} 小時出關"; // 待 joy 潤
  const JH_WAR_SEAL = "決戰"; // 待 joy 潤
  const JH_WAR_SKIP = "先不去"; // 待 joy 潤
  const JH_WAR_IN = "已投入"; // 待 joy 潤
  const JH_WAR_OPEN = "後開打"; // 待 joy 潤
  const JH_WAR_GO = "去看看"; // 待 joy 潤
  const jhChoiceCells = (opts) => opts.map((o) => { const [name, sub] = optParts(o); return `<button class="btn jh-do${o.enabled ? "" : " off"}" ${o.enabled ? `data-act="choose" data-id="${esc(o.id)}"` : `data-act="opt-why" data-why="${esc(o.note || sub)}" aria-disabled="true"`}>${esc(name)}${sub ? `<small>${esc(sub)}</small>` : ""}</button>`; }).join("");
  function jhPrepPage(m, p) {
    return `<div class="jh-page jh-ev jh-season">${p.ckPop || ""}${jhMomentHero(m, JH_PREP_TITLE, JH_PREP_SEAL, "/static/img/places/world.webp")}<div class="jh-ev-txt"><p>${JH_PREP_TEXT}</p></div>`
      + `<div class="jh-dos one"><button class="btn jh-do wide primary" data-act="tab" data-tab="hero">${JH_PREP_GO}</button></div></div>`;
  }
  // 休季：圖褪成灰、這一季的結局一張（結局的圖、標題、第一段），讀你的傳、這一季的始末（原本那張結算卡拉起來看）；列傳的票照選單
  function jhRestPage(m, p) {
    const r = m.season_result;
    const side = r && r.stances && r.stances.length ? r.stances.reduce((a, b) => (b.value > a.value ? b : a)).side : "";
    const first = r ? (String(r.text || "").match(/<p>[\s\S]*?<\/p>/) || [r.text || ""])[0] : "";
    const btns = `${m.zhuan ? `<button class="btn jh-do primary" data-act="zhuan-open" data-season="${Number(m.zhuan.season)}">${JH_REST_ZHUAN}</button>` : ""}${r ? `<button class="btn jh-do" data-act="jh-sheet" data-sheet="result">${JH_REST_ALL}</button>` : ""}`;
    const box = r ? `<section class="jh-box">${side ? `<div class="jh-box-img" style="background-image:url('/static/img/zhuan/${esc(side)}_win.webp')"></div>` : ""}<h3>${esc(r.title)}</h3><div class="jh-box-txt">${first}</div><div class="jh-dos">${btns}</div></section>` : "";
    const rest = (m.options || []).filter((o) => o.id !== "season:resting");
    const sheet = S.jhSheet === "result" && r ? `<div class="sheet-bg" data-act="jh-sheet"></div><div class="sheet jh-sheet" role="dialog" aria-label="${JH_REST_ALL}"><div class="grip"></div><div class="top-row"><h3 style="flex:1">${JH_REST_ALL}</h3><button class="btn small ghost" data-act="jh-sheet">${JH_CLOSE}</button></div>${resultHtml(r)}</div>` : "";
    return `<div class="jh-page jh-ev jh-season jh-rest">${p.ckPop || ""}${jhMomentHero(m, JH_REST_TITLE, JH_REST_SEAL, jhArtSrc(m) || "/static/img/places/world.webp")}${box}`
      + `${rest.length ? `<div class="jh-dos">${jhChoiceCells(rest)}</div>` : ""}<p class="jh-quiet">${JH_REST_TEXT}</p>${sheet}</div>`;
  }
  // 閉關：圖、還要多久、提前出關（擂台那一格照選單）
  function jhBusyPage(m, p) {
    const h = m.status.busy_hours;
    return `<div class="jh-page jh-ev jh-busy">${p.ckPop || ""}${jhMomentHero(m, JH_BUSY_TITLE, JH_BUSY_SEAL, jhArtSrc(m))}`
      + `<div class="jh-ev-txt"><p>${esc(JH_BUSY_LEFT.replace("{h}", h < 1 ? "不到 1" : String(Math.round(h))))}</p></div><div class="jh-dos">${jhChoiceCells(m.options || [])}</div></div>`;
  }
  // 決戰集結（設計稿 q）：還沒投入時整頁是這一場：倒數、兩邊的主將、投入的鈕與先不去；投入了（或先不去）回到閒著的頁，集結那一條在眼下上面
  function jhMusterPage(m, p) {
    const bp = m.battle_panel;
    const txt = typeof bpTrim === "function" ? (String(bpTrim(m.scene || "", m)).match(/<p>(?!<strong>)[\s\S]*?<\/p>/) || [""])[0] : "";
    const gens = bp.chiefs && (bp.chiefs.left.length || bp.chiefs.right.length) && typeof bpSide === "function" ? `<div class="bp-gens">${bpSide(bp.left, bp.chiefs.left, "left")}${bpSide(bp.right, bp.chiefs.right, "right")}</div>` : "";
    const joins = musterJoins(m);
    return `<div class="jh-page jh-ev jh-war">${p.ckPop || ""}${jhMomentHero(m, bp.name, JH_WAR_SEAL, BP_BG.muster)}<div class="jh-ev-txt">${txt}</div>`
      + `<section class="jh-box">${typeof bpClockHtml === "function" ? bpClockHtml(bp) : ""}${gens}<div class="jh-dos">${jhChoiceCells(joins)}<button class="btn jh-do" data-act="jh-muster-skip" data-name="${esc(bp.name)}">${JH_WAR_SKIP}</button></div></section></div>`;
  }
  // 閒著的頁上集結那一條：名字、倒數、投入的鈕（沒投入）或「已投入」
  function jhMusterStrip(m) {
    if (!jhBpMuster(m)) return "";
    const bp = m.battle_panel;
    const joins = typeof musterJoins === "function" ? musterJoins(m) : [];
    const mine = bp.me && !joins.length;
    const left = typeof bpLeft === "function" && bpLeft() != null ? bpLeft() : bp.due;
    const when = left > 0 && typeof bpClock === "function" ? `${bpClock(left)} ${JH_WAR_OPEN}` : "";
    return `<section class="jh-war-strip">${jhSealHtml(JH_WAR_SEAL)}<span class="jh-row-t"><b>${esc(bp.name)}</b><small>${[mine ? JH_WAR_IN : "", when].filter(Boolean).join("・")}</small></span>`
      + `${joins.length ? `<button class="btn small jh-row-go" data-act="jh-muster-skip" data-name="">${esc(JH_WAR_GO)}</button>` : ""}</section>`;
  }


  // ── 第六批：戰報（設計稿 o）：圖、勝負一枚大印、對手、一句話、得失用字（數字留在完整戰報）、看完整戰報、往下看 ──
  const JH_FIGHT_SEAL = "對陣"; // 待 joy 潤
  const JH_FULL_REPORT = "看完整戰報"; // 待 joy 潤
  const JH_READ_ON = "往下看"; // 待 joy 潤
  const JH_REPORT = "戰報"; // 待 joy 潤：拉起來那一層的標題
  const JH_FIGHT_ART = "/static/img/events/fight.webp";
  // 單挑打到一半每一回合都是一張戰報：那一刻戰報畫在出招的頁上，不另擋一頁
  const jhCardOn = (m) => !!m.card && S.jhCardSeen !== m.card_id && !(m.jianghu.take && m.jianghu.take.slot === "duel");
  // 得失的一樣換成一句話（PM 11/25：數字留在完整戰報）
  function jhGainWord(raw, loss) {
    const t = String(raw).replace(/<[^>]+>/g, "").replace(/（[^）]*）/g, "").trim();
    let x;
    if ((x = t.match(/^【(.+?)】熟練/))) return [`${x[1]} 熟了些`, false];
    if (/^氣血/.test(t)) return /[-－]/.test(t) ? ["氣血少了一截", true] : ["氣血回了些", false];
    if (/^內傷/.test(t)) return /[+＋]/.test(t) ? ["內傷加重", true] : ["內傷輕了些", false];
    if (/^經驗/.test(t)) return ["多了些歷練", false];
    if (/^體力/.test(t)) return /[-－]/.test(t) ? ["耗了些體力", true] : ["體力回了些", false];
    if ((x = t.match(/^(.+?)\s*[×x]\s*\d+$/))) return [loss ? `少了${x[1]}` : `得了${x[1]}`, loss];
    if ((x = t.match(/^(.+?)\s*([+＋\-－])\s*\d+/))) { const up = /[+＋]/.test(x[2]); return [`${x[1].replace(/[【】]/g, "")}${up ? "多了些" : "少了些"}`, !up]; }
    return [t.replace(/[+＋\-－]?\d+/g, "").trim(), loss];
  } // 待 joy 潤：上面每一句
  function jhGains(m) {
    const line = jhTxLines(m.now).map((l) => l.replace(/<[^>]+>/g, "")).find((l) => /^得：|^失：|　失：/.test(l));
    const out = [];
    if (line) {
      for (const part of line.split("　")) {
        const loss = /^失：/.test(part);
        const body = part.replace(/^[得失]：/, "");
        if (body === part && !/^[得失]：/.test(part)) continue;
        for (const it of body.split("、")) if (it.trim()) out.push(jhGainWord(it, loss));
      }
    } else {
      const p = (String(m.card).match(/<p>(?:(?!<\/p>)[\s\S])*?<strong>得失<\/strong>([\s\S]*?)<\/p>/) || [])[1] || "";
      for (const it of p.replace(/<[^>]+>/g, "").split(/[　\n]+/)) if (it.trim()) out.push(jhGainWord(it, /[-－]\d/.test(it) && !/^內傷/.test(it)));
    }
    const seen = new Set();
    return out.filter(([w]) => w && !seen.has(w) && seen.add(w));
  }
  function jhCardPage(m, p) {
    const card = String(m.card || "");
    const head = ((card.match(/<h3>([\s\S]*?)<\/h3>/) || [])[1] || "").replace(/<[^>]+>/g, "").replace(/^[^\u4e00-\u9fff]+/, "").trim();
    const seg = head.split("・").pop() || "";
    const sx = seg.match(/^(\S{1,4})\s+(.+)$/);
    const seal = sx ? sx[1] : JH_FIGHT_SEAL, title = sx ? sx[2] : seg;
    const stamp = (card.match(/<strong>(?!過程|得失|結果)([^<]{1,4})<\/strong>/) || [])[1] || "";
    const words = jhTxLines(m.now).map((l) => l.replace(/<[^>]+>/g, "").trim()).filter((l) => l && !/^得：|^失：|　失：/.test(l));
    const say = words[0] || "";
    const gains = jhGains(m);
    const chips = gains.length ? `<div class="jh-gains">${gains.map(([w, bad]) => `<span${bad ? ' class="bad"' : ""}>${esc(w)}</span>`).join("")}</div>` : "";
    const sheet = S.jhSheet === "fight"
      ? `<div class="sheet-bg" data-act="jh-sheet"></div><div class="sheet jh-sheet" role="dialog" aria-label="${JH_REPORT}"><div class="grip"></div><div class="top-row"><h3 style="flex:1">${JH_REPORT}</h3><button class="btn small ghost" data-act="jh-sheet">${JH_CLOSE}</button></div>`
        + `<div class="card battle-card">${fightCard(card, m.card_id)}${typeof gaugeHtml === "function" ? gaugeHtml(m.card_gauge) : ""}${m.now || ""}${typeof frontReportHtml === "function" ? frontReportHtml(m.front) : ""}</div></div>`
      : "";
    return `<div class="jh-page jh-ev jh-fight">${p.ckPop || ""}${jhMomentHero(m, title, seal, JH_FIGHT_ART)}${stamp ? `<div class="jh-stamp${stamp.length > 2 ? " long" : ""}">${esc(stamp)}</div>` : ""}`
      + `<div class="jh-ev-txt">${say ? `<p>${esc(say)}</p>` : ""}</div>${chips}`
      + `<button class="jh-why" data-act="jh-sheet" data-sheet="fight">${JH_FULL_REPORT}<i aria-hidden="true">›</i></button>`
      + `<div class="jh-dos"><button class="btn jh-do wide primary" data-act="jh-card-on" data-id="${esc(m.card_id)}">${JH_READ_ON}</button></div>${sheet}</div>`;
  }

  // 趕路：圖、「往某地的路上」、剛剛那一則、一條路的墨條（中間各站是細的刻痕，不畫圓圈）、疾行與折返；路上的小事收在底下
  function jhRoadPage(m, p) {
    const r = m.jianghu.road;
    const opts = m.options || [];
    // 剛剛那一則：剛出發那一則（「前往 長社（途經…）」）跟墨條說的是同一件事，不寫兩次；路上小事的結果照寫
    const now = /tx-title">前往 /.test(p.now || "") ? "" : p.now;
    const back = opts.find((o) => o.id.startsWith("road:back"));
    const halt = opts.find((o) => o.id === "act:halt");
    const rest = opts.filter((o) => o !== back && o !== halt && o.id !== "act:on_road");
    const pct = (x) => `${Math.round(Math.min(1, Math.max(0, x)) * 1000) / 10}%`;
    const me = ((m.status && m.status.name) || "").slice(0, 1);
    const ticks = (r.stops || []).map((t) => `<i class="jh-tick" style="left:${pct(t.at)}"></i>`).join("");
    const next = r.stops && r.stops.length && r.stops[0].at > r.done ? r.stops[0].name : "";
    const dash = r.dash
      ? `<button class="btn jh-do wide primary${r.dash.enabled ? "" : " off"}" ${r.dash.enabled ? `data-act="jh-go" data-dest="${esc(r.dest)}" data-mode="dash"` : `data-act="opt-why" data-why="${esc(optParts({ label: r.dash.label })[1])}" aria-disabled="true"`}>${JH_DASH}<small>${esc(optParts({ label: r.dash.label })[1])}</small></button>` : "";
    const backBtn = back ? `<button class="btn jh-do wide" data-act="choose" data-id="${esc(back.id)}"${back.enabled ? "" : " disabled"}>${JH_BACK}<small>${esc(optParts(back)[0].replace(/^折返\s*/, ""))}</small></button>` : "";
    const haltBtn = halt ? `<button class="jh-why" data-act="choose" data-id="${esc(halt.id)}"${halt.enabled ? "" : " disabled"}>${esc(optParts(halt)[1].replace(/^到(.*)就停下$/, "停在$1") || optParts(halt)[0])}<i aria-hidden="true">›</i></button>` : "";
    const cell = (o) => { const [name, sub] = optParts(o); return `<button class="btn jh-do${o.enabled ? "" : " off"}" ${o.enabled ? `data-act="choose" data-id="${esc(o.id)}"` : `data-act="opt-why" data-why="${esc(o.note || sub)}" aria-disabled="true"`}>${esc(name)}${sub ? `<small>${esc(sub)}</small>` : ""}</button>`; };
    const card = `<section class="jh-road">
        <div class="jh-road-ln"><b>${esc(r.from)}</b><b>${esc(r.to)}</b></div>
        <div class="jh-road-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(r.done * 100)}"><span style="width:${pct(r.done)}"></span>${ticks}<em style="left:${pct(r.done)}">${esc(me)}</em></div>
        <div class="jh-road-tm">${esc(JH_ROAD_LEFT.replace("{mode}", r.mode).replace("{n}", r.left))}${next ? `・${esc(JH_ROAD_NEXT.replace("{name}", next))}` : ""}</div>
        <div class="jh-dos">${dash}${backBtn}</div>${haltBtn}
      </section>`;
    const tasks = rest.length ? `<div class="jh-blk"><h3>${JH_ROAD_DO}</h3><div class="jh-dos">${rest.map(cell).join("")}</div></div>` : "";
    return `<div class="jh-page jh-rd">${p.ckPop || ""}${jhMomentHero(m, JH_ON_ROAD.replace("{to}", r.to), "", r.art || jhArtSrc(m))}${now ? jhProseHtml(m, "", now) : ""}${card}${tasks}</div>`;
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
    if (which === "stam") return wrap(JH_STAM, jhStamBody(m));
    if (which === "road") return wrap(JH_ROAD, jhRoadBody(m));
    if (which === "duty") return wrap(JH_DUTY_NAME, jhDutyBody(m, jhKinds(m, jhNotInEye(m, p.extras || []))));
    if (which === "join") { // 此地投得了兩方以上：兩顆投靠鈕（同江湖頁原本那兩顆）
      const html = typeof factionJoinHtml === "function" ? factionJoinHtml(m) : "";
      if (!html) { S.jhSheet = null; return ""; }
      return wrap(JH_JOIN_NAME, html);
    }
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
        case "jh-sheet": S.jhSheet = el.dataset.sheet || null; S.jhWait = false; S.jhStamWhy = ""; renderPage(); break;
        case "jh-stam": S.jhSheet = "stam"; S.jhStamWhy = el.dataset.why || ""; renderPage(); break;
        case "jh-map": S.jhSheet = null; await goTab("map"); break;
        case "jh-wait": S.jhWait = !S.jhWait; renderPage(); break;
        case "jh-peer-pick": S.jhPeerPick = { name: S.peer && S.peer.name, key: el.dataset.key }; render(); break;
        case "jh-peer-back": S.jhPeerPick = null; S.jhPeerChoice = null; if (S.peer) { S.peer.amountFor = null; S.peer.textFor = null; } render(); break;
        case "jh-peer-choice": S.jhPeerChoice = el.dataset.c; render(); break;
        case "jh-peer-go": S.jhPeerPick = null; await peerAct(Number(el.dataset.i)); break;
        case "jh-ev-more": S.jhEvMore = !S.jhEvMore; renderPage(); break;
        case "jh-muster-skip": S.jhMusterSkip = el.dataset.name || null; renderPage(); break;
        case "jh-card-on": S.jhCardSeen = S.main && S.main.card_id; S.jhSheet = null; S.jhEvMore = false; renderPage(); try { window.scrollTo(0, 0); } catch (e) { /* 測試 */ } break;
        case "jh-go": { // 遠路（行路清單裡不在鄰近的）與路上疾行：照輿圖的出發走同一條路（/api/travel）
          const place = el.dataset.dest, mode = el.dataset.mode || "walk";
          S.jhSheet = null;
          await busy(async () => {
            const r = await api("/api/travel", { place, mode });
            setMain(r.main);
            renderTop();
            if (!r.arrived) toast(`${JH_GO_FAIL}${r.reason}`);
          }, WAIT_LINES.move);
          renderPage();
          break;
        }
    } // jianghuClick
  } // jianghuClick
  registerClicks(jianghuClick, ["jh-later", "jh-sheet", "jh-stam", "jh-map", "jh-wait", "jh-peer-pick", "jh-peer-back", "jh-peer-choice", "jh-peer-go", "jh-ev-more", "jh-muster-skip", "jh-card-on", "jh-go"]);

  // ── 6. 這裡的人（第三批）：一排方格。大勢人物全放（立繪），俠客只放跟你有關的（邀你的、義兄弟、敵方），最後一格「＋N 俠客」拉起全部。
  // 有事找你的人頭上一枚小印（軍令、託付、邀戰……）。人是入口：點人物拉起他的卡（他交代的事、交談、護衛、犒軍、挑戰），點俠客照舊開玩家卡
  const JH_PEOPLE = "這裡的人"; // 待 joy 潤
  const JH_PEOPLE_F = "{n} 位人物", JH_PEOPLE_P = "{n} 位俠客"; // 待 joy 潤（沒有的那一半不寫）
  const JH_PEERS_ALL = "俠客"; // 待 joy 潤：「＋N 俠客」那一格
  const JH_PEERS_HEAD = "此地的俠客"; // 待 joy 潤
  const JH_BROTHER = "義"; // 待 joy 潤：義兄弟頭上的小印
  const JH_FOE = "敵"; // 待 joy 潤：敵方頭上的小印
  const JH_KIN = "同門"; // 待 joy 潤
  const JH_ROW_MAX = 6; // 一排六格（390 寬），人再多也是一排
  const JH_SIDES2 = ["官軍", "黃巾"];
  const JH_FREE = "散人"; // 狀態行只寫等級・陣營（PM 2026-11-25）：門派與頭銜在點名號印拉起的卡上
  function jhMySide(m) {
    return String((m.status && m.status.affiliation) || "").split("・").find((x) => JH_SIDES2.includes(x)) || "";
  }
  // 誰頭上掛什麼印：大勢人物（id → 印）與俠客（名號 → 印）
  // 主線、章回、奇事這一步要你「見他」、而且現在就做得了（人就在此地）：那一步（PM 2026-11-25 第三批）
  function jhFigStep(m, f) {
    const got = typeof tkItems === "function" ? tkItems(m, []) : null;
    return got ? got.on.find((it) => it.go && it.go.id && String(it.sub || "").includes(`見${f.name}`)) || null : null;
  }
  function jhMarks(m) {
    const fig = {}, peer = {};
    for (const f of m.figures_here || []) {
      const step = jhFigStep(m, f);
      if (step) fig[f.id] = step.seal;
      else if ((m.orders || []).some((o) => !o.done && String(o.text || "").startsWith(f.name))) fig[f.id] = "軍令";
      else if (m.letter && m.letter.sender === f.name && (m.letter.task || m.letter.errand)) fig[f.id] = m.letter.kind || "託付";
    }
    for (const c of m.calls || []) {
      const who = (m.here || []).find((x) => String(c.text).startsWith(x.name));
      if (who) peer[who.name] = (JH_CALL_SEAL.find(([re]) => re.test(c.text)) || [null, "邀約"])[1];
    }
    const j = m.jieyi;
    for (const x of (j && j.members) || []) if (!x.me && !peer[x.name]) peer[x.name] = JH_BROTHER;
    for (const x of m.here || []) if (x.kin && !peer[x.name]) peer[x.name] = JH_KIN;
    const mine = jhMySide(m);
    for (const x of m.here || []) if (!peer[x.name] && mine && JH_SIDES2.includes(x.side) && x.side !== mine) peer[x.name] = JH_FOE;
    return { fig, peer };
  }
  const jhMk = (t) => (t ? `<i class="jh-mk">${esc(t)}</i>` : "");
  function jhPeopleHtml(m) {
    const figs = m.figures_here || [], peers = jhShown("jh:peers") ? m.here || [] : []; // 俠客那一半：新角色交過名帖、有同門或到 5 級才長出來
    if (!figs.length && !peers.length) return "";
    const { fig, peer } = jhMarks(m);
    const order = { 邀戰: 0, 論武: 0, 結伴: 0, 結義: 0, 邀約: 0, [JH_BROTHER]: 1, [JH_KIN]: 1, [JH_FOE]: 2 };
    const near = peers.filter((x) => peer[x.name]).sort((a, b) => order[peer[a.name]] - order[peer[b.name]]);
    const room = Math.max(0, JH_ROW_MAX - figs.length - (peers.length ? 1 : 0));
    const shown = near.slice(0, room), rest = peers.length - shown.length;
    const tiles = figs.map((f) => `<button class="jh-ic fig" data-act="fig-open" data-id="${esc(f.id)}"><span${f.face ? ` style="background-image:url('${esc(f.face)}')"` : ""}>${f.face ? "" : esc(f.name.slice(0, 1))}</span>${esc(f.name)}${jhMk(fig[f.id])}</button>`)
      .concat(shown.map((x) => `<button class="jh-ic pc${peer[x.name] === JH_FOE ? " foe" : ""}" data-act="peer" data-name="${esc(x.name)}"><span>${esc(x.name.slice(0, 1))}</span>${esc(x.name)}${jhMk(peer[x.name] === JH_FOE ? "" : peer[x.name])}</button>`))
      .concat(rest > 0 ? [`<button class="jh-ic all" data-act="jh-sheet" data-sheet="people"><span>＋${rest}</span>${JH_PEERS_ALL}</button>`] : []);
    const n = [figs.length ? JH_PEOPLE_F.replace("{n}", figs.length) : "", peers.length ? JH_PEOPLE_P.replace("{n}", peers.length) : ""].filter(Boolean).join("・");
    return `<section class="jh-blk jh-people"${peers.length ? ' data-uf="jh:peers"' : ""}><h3>${JH_PEOPLE}${peers.length ? jhUfDot("jh:peers") : ""}<small>${esc(n)}</small></h3><div class="jh-ppl">${tiles.join("")}</div></section>`;
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
  const JH_FIG_MEET = "見他"; // 待 joy 潤：主線這一步要你見他
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
    const step = jhFigStep(m, f);
    const order = (m.orders || []).find((o) => !o.done && String(o.text || "").startsWith(f.name));
    const letter = m.letter && m.letter.sender === f.name && (m.letter.task || m.letter.errand) ? m.letter : null;
    const st = step ? jhFromTrack(m, step) : null;
    const say = st ? `<div class="jh-say"><b>${esc(`${st.seal}・${jhPlain(st.title)}`)}</b><small>${esc(st.sub || "")}</small></div><button class="btn jh-do wide primary" ${st.attrs}>${JH_FIG_MEET}</button>`
      : order ? `<div class="jh-say"><b>${esc(JH_FIG_ORDER.replace("{t}", order.title))}</b><small>${esc(order.how || "")}</small></div>${btn(JH_FIG_GO, "", 'data-act="duty-open"').replace("jh-do", "jh-do wide primary")}`
      : letter ? `<div class="jh-say"><b>${esc(letter.task ? letter.task.title : letter.errand.text)}</b><small>${esc(letter.task ? letter.task.how : "")}</small></div>${btn(JH_READ, "", 'data-act="jh-sheet" data-sheet="letter"').replace("jh-do", "jh-do wide primary")}` : "";
    const i = f.intro || {};
    const role = i.role || f.side || "";
    return `<div class="sheet-bg" data-act="fig-close"></div><div class="sheet jh-card jh-fig" role="dialog" aria-label="${esc(f.name)}">
        <div class="jh-pt"${f.face ? ` style="background-image:url('${esc(f.face)}')"` : ""}><button class="jh-x" data-act="fig-close" aria-label="${JH_CLOSE}">×</button></div>
        <div class="jh-in"><h2>${esc(f.name)}<small>${esc(role)}</small></h2>${i.who ? `<p>${esc(i.who)}</p>` : ""}${jhFigNature(i)}${say}<div class="jh-dos">${dos.join("")}</div></div></div>`;
  }

  // 人物卡上的本性、如今與變化紀錄（同舊的點人物那一層：Joy 11/6「不是所有玩家都那麼了解三國裡面的角色」；性子還沒變的不畫如今）
  const JH_FIG_NATURE = "本性", JH_FIG_NOW = "如今"; // 待 joy 潤
  function jhFigNature(i) {
    const row = (cls, k, v) => `<p class="jh-fig-row ${cls}"><b>${k}</b><span>${esc(v)}</span></p>`;
    return `${i.nature ? row("vi-nature", JH_FIG_NATURE, i.nature) : ""}${i.now ? row("vi-now", JH_FIG_NOW, i.now) : ""}`
      + `${(i.history || []).length ? `<ul class="jh-fig-hist vi-hist">${i.history.map((h) => `<li>${esc(h)}</li>`).join("")}</ul>` : ""}`;
  }
  // 點俠客：跟人物卡同一種卡（設計稿 j；PM 2026-11-25 第三批）。名號印、名號、陣營門派等級一行、頭銜小印；他邀你的那一件墨底排最上面；
  // 其餘一類一格、兩欄排，同類收一顆（論武挑哪一樣、贈哪一樣，點了再拉出來挑）；不能做的變淡、寫原因。
  // 卡上的鈕照舊送玩家卡那一套（peers.js 的 peer-act、#peer-amount、#peer-text；伺服器給的 actions 照索引），只換畫法。
  // 只在新排法開著的那一刻換（jhOn）；舊的玩家卡（peers.js 的 peerHtml）別處照舊
  const JH_PEER_KIND = { spar: "切磋", discuss: "論武", gift: "贈物", mingtie: "名帖", raid: "截殺", greet: "挑釁", jieyi: "結義", party: "結伴" }; // 待 joy 潤：一格的名字
  const JH_PEER_ORDER = ["spar", "discuss", "gift", "mingtie", "raid", "greet", "jieyi", "party"];
  const JH_PEER_ANSWER = "挑一樣應他"; // 待 joy 潤：論武要挑自己出哪一樣
  const JH_PEER_PICK = "挑一樣"; // 待 joy 潤
  const JH_PEER_BACK = "返回";
  const JH_PEER_TWIN = "・另一份"; // 待 joy 潤：同名的兩份意境（第二份）
  const JH_PEER_GIFT = "{label}・挑一樣、給幾份"; // 待 joy 潤
  const JH_PEER_SAY = "想對他說的話（可以不寫）"; // 待 joy 潤
  const JH_PEER_HOW_MANY = "給幾份"; // 待 joy 潤
  const JH_PEER_SEND = "送出";
  const JH_PEER_GONE = "對方已經不在這裡了。";
  // 原因的人話（伺服器的字像規則的，這裡換掉；其餘照伺服器的字）
  const JH_PEER_WHY = [[/^要先跟他互換過名帖$/, "還沒跟他換過名帖"], [/^先做一張名帖$/, "你還沒有名帖"], [/^他出「.+?」・/, "跟他出的一樣"]]; // 待 joy 潤
  const jhPeerWhy = (t) => (JH_PEER_WHY.find(([re]) => re.test(t || "")) || [null, t || ""])[1];
  const jhIsAnswer = (b) => /^yes(:|$)/.test(b.arg || "");
  const jhIsNo = (b) => /^no$/.test(b.arg || "");
  function jhPeerHtml(still) {
    const P = S.peer, c = P && P.card, m = S.main || {};
    const quiet = still ? " still" : "";
    const shell = (inner, name) => `<div class="sheet-bg${quiet}" data-act="peer-close"></div><div class="sheet jh-card jh-pcard peer-card${quiet}" role="dialog" aria-label="${esc(name)}">${inner}</div>`;
    const x = `<button class="jh-x" data-act="peer-close" aria-label="${JH_CLOSE}">×</button>`;
    if (!P || P.loading) S.jhPeerPick = S.jhPeerChoice = null; // 剛打開（或換人）：從頭看
    if (!P || P.loading) return shell(`<div class="jh-pt"><span>${esc(((P && P.name) || "").slice(0, 1))}</span>${x}</div><div class="jh-in"><p>……</p></div>`, (P && P.name) || "");
    if (!c) return shell(`<div class="jh-pt"><span>${esc(P.name.slice(0, 1))}</span>${x}</div><div class="jh-in"><h2>${esc(P.name)}</h2><p>${esc(P.gone || JH_PEER_GONE)}</p></div>`, P.name);
    const acts = c.actions.map((b, i) => ({ ...b, i }));
    const head = `<h2>${esc(c.name)}<small>${esc([...String(c.affiliation || "").split("・").filter(Boolean), `${c.level | 0} 級`].join("・"))}</small></h2>`
      + `${(c.title && c.title.name && typeof titleSeal === "function") || c.jieyi ? `<div class="jh-ptags">${c.title && c.title.name && typeof titleSeal === "function" ? titleSeal(c.title) : ""}${c.jieyi ? `<span class="jh-k">${esc(c.jieyi)}</span>` : ""}</div>` : ""}`
      + (typeof peerRenownHtml === "function" ? peerRenownHtml(c, P) : ""); // 稱號小籤（名聲 3B，同舊的玩家卡）
    const face = c.mingtie && typeof mtCardHtml === "function" ? `<button class="jh-pmt" data-act="mt-zoom-peer" aria-label="看${esc(c.name)}的名帖">${mtCardHtml(c.mingtie, c.name, "thumb")}</button>` : `<span>${esc(c.name.slice(0, 1))}</span>`;
    const msg = P.msg ? `<div class="jh-pmsg">${P.msg}</div>` : "";
    const btn = (b, label, cls = "") => (b.enabled
      ? `<button class="btn jh-do${cls}" data-act="peer-act" data-i="${b.i}"${jhIsAnswer(b) ? ` data-answer="${esc(b.action)}"` : ""}>${esc(label)}</button>`
      : `<button class="btn jh-do off${cls}" data-act="opt-why" data-why="${esc(jhPeerWhy(b.note))}" aria-disabled="true">${esc(label)}<small>${esc(jhPeerWhy(b.note))}</small></button>`);
    const pick = S.jhPeerPick && S.jhPeerPick.name === c.name ? S.jhPeerPick.key : "";
    // 正在填的：贈物（挑一樣、給幾份）、挑釁（附一句話）
    if (P.amountFor != null && c.actions[P.amountFor]) {
      const b = c.actions[P.amountFor];
      const ch = b.choices || [];
      const chosen = ch.find((o) => o.id === S.jhPeerChoice) || ch[0];
      const chips = ch.length > 1 ? `<div class="jh-chips">${ch.map((o) => `<button class="jh-chip${o === chosen ? " on" : ""}" data-act="jh-peer-choice" data-c="${esc(o.id)}">${esc(o.label)}<small>${o.max | 0}</small></button>`).join("")}</div>` : "";
      const max = chosen ? Math.min(chosen.max, b.amount) : b.amount;
      return shell(`<div class="jh-pt">${face}${x}</div><div class="jh-in">${head}<h3 class="jh-sub">${esc(JH_PEER_GIFT.replace("{label}", b.label))}</h3>${chips}<form class="jh-form" id="peer-amount">${chosen ? `<input type="hidden" name="choice" value="${esc(chosen.id)}">` : ""}<input class="input" name="amount" type="number" inputmode="numeric" min="${b.amount_min || 1}" max="${max}" value="1" aria-label="${JH_PEER_HOW_MANY}"><button class="btn jh-do wide primary" type="submit">${JH_PEER_SEND}</button></form><button class="btn jh-do" data-act="jh-peer-back">${JH_PEER_BACK}</button></div>`, c.name);
    }
    if (P.textFor != null && c.actions[P.textFor]) {
      const b = c.actions[P.textFor];
      return shell(`<div class="jh-pt">${face}${x}</div><div class="jh-in">${head}${msg}<form class="jh-form" id="peer-text"><input class="input" name="text" maxlength="${b.text}" value="${esc(P.textDraft || "")}" placeholder="${JH_PEER_SAY}" aria-label="${JH_PEER_SAY}"><button class="btn jh-do wide primary" type="submit">${esc(b.label)}</button></form><button class="btn jh-do" data-act="jh-peer-back">${JH_PEER_BACK}</button></div>`, c.name);
    }
    // 拉出來挑的那一層：同一類裡的每一樣（論武出哪一樣、應論武出哪一樣）
    if (pick) {
      const list = acts.filter((b) => (b.group || b.action) === pick && !jhIsNo(b));
      return shell(`<div class="jh-pt">${face}${x}</div><div class="jh-in">${head}<h3 class="jh-sub">${esc(JH_PEER_KIND[list[0] && list[0].action] || pick)}・${JH_PEER_PICK}</h3><div class="jh-picks">${list.map((b, k) => btn(b, `${b.pick || b.label}${list.slice(0, k).some((y) => (y.pick || y.label) === (b.pick || b.label)) ? JH_PEER_TWIN : ""}`).replace('data-act="peer-act"', 'data-act="jh-peer-go"')).join("")}</div><button class="btn jh-do" data-act="jh-peer-back">${JH_PEER_BACK}</button></div>`, c.name);
    }
    // 他邀你的：說的那一句、應他（論武要先挑一樣）、婉拒
    const ans = acts.filter(jhIsAnswer);
    let say = "";
    if (ans.length) {
      const kind = ans[0].action;
      const call = (m.calls || []).find((k) => String(k.text).startsWith(c.name) && (kind !== "spar" || /切磋/.test(k.text)) && (kind !== "discuss" || /論武/.test(k.text)));
      const no = acts.find((b) => b.action === kind && jhIsNo(b));
      const grouped = ans.length > 1 || ans[0].group;
      const go = grouped ? `<button class="btn jh-do wide primary" data-act="jh-peer-pick" data-key="${esc(ans[0].group || kind)}" data-answer="${esc(kind)}">${JH_PEER_ANSWER}</button>` : btn(ans[0], ans[0].label, " wide primary");
      say = `${call ? `<div class="jh-say"><b>${esc(call.text)}</b></div>` : ""}<div class="jh-ans">${go}${no ? btn(no, no.label) : ""}</div>`;
    }
    // 其餘：一類一格（應答、婉拒不算）
    const rest = acts.filter((b) => !jhIsAnswer(b) && !jhIsNo(b));
    const kinds = [...new Set(rest.map((b) => b.action))].sort((a, b) => ((JH_PEER_ORDER.indexOf(a) + 99) % 99) - ((JH_PEER_ORDER.indexOf(b) + 99) % 99));
    const cells = kinds.map((k) => {
      const list = rest.filter((b) => b.action === k);
      const name = JH_PEER_KIND[k] || list[0].label;
      const live = list.filter((b) => b.enabled);
      if (!live.length) return btn(list[0], name);
      if (live.length === 1) return btn(live[0], name);
      return `<button class="btn jh-do" data-act="jh-peer-pick" data-key="${esc(list[0].group || k)}">${esc(name)}</button>`;
    });
    return shell(`<div class="jh-pt">${face}${x}</div><div class="jh-in">${head}${msg}${say}<div class="jh-dos">${cells.join("")}</div></div>`, c.name);
  }
  // 玩家卡的畫法換掉（只在新排法那一刻）：peers.js 的 peerHtml 由殼 app.js 與輪詢換卡叫，這裡包一層
  if (typeof peerHtml === "function") {
    const jhOldPeerHtml = peerHtml;
    peerHtml = (still = false) => (jhOn(S.main) ? jhPeerHtml(still) : jhOldPeerHtml(still)); // eslint-disable-line no-func-assign
  }

  // 整頁：parts 是 pageJianghu 已經算好的各塊（同一份資料，不重算）
  // 畫壞了（新排法哪一格丟例外）不能讓整頁掉回登入頁（app.js 的 enter 接到例外就回登入）：回空字串，main.js 照舊畫原本的江湖頁
  function jhPageHtml(m, p) {
    jhUfHook();
    try { return jhPage(m, p); } catch (e) { if (typeof console !== "undefined") console.error(e); return ""; }
  }
  function jhPage(m, p) {
    const eyeH = jhEyeHtml(m, p);
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
    const kinds = jhKinds(m, extras);
    let base = p.layers || "";
    // 點人物那一層換成人物卡（舊的對話式那一層 figPickHtml 拿掉）；「全部」那一層也不列收進人物卡的
    if (S.fig && !S.figLog && typeof figPickHtml === "function") base = base.replace(figPickHtml(m), () => jhFigHtml(m));
    if (S.hereAll && typeof hereAllHtml === "function") base = base.replace(hereAllHtml(m, p.extras || []), () => hereAllHtml(m, extras));
    const layers = `${base}${jhSheetHtml(m, p)}${typeof codexWhyHtml === "function" ? codexWhyHtml(m) : ""}`;
    return `<div class="jh-page${sheetOpen ? " sheet-on" : ""}${eyeH && jhBpMuster(m) ? " jh-tight" : ""}">${p.ckPop || ""}${hero}${jhProseHtml(m, jhBpMuster(m) ? "" : jhNoSealTwice(p.inner, seal), jhNoRenown(jhNowLine(m)), !!eyeH)}${p.resultCard}${jhMusterStrip(m)}${eyeH}${m.party && typeof socialHtml === "function" ? socialHtml({ ...m, calls: [] }) : ""}${p.jieyi}${p.links}${p.free}${jhActsWrap(jhStamWhy(m, jhActs(p.menu, m, kinds)))}${p.sealCard}${p.senseNotes}${jhPeopleHtml(m)}${jhStamWhy(m, jhSignsHtml(m, kinds))}${p.skip}${layers}</div>`;
  }
