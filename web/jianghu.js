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

  // 整頁：parts 是 pageJianghu 已經算好的各塊（同一份資料，不重算）
  function jhPageHtml(m, p) {
    try { document.documentElement.classList.add("jh2"); } catch (e) { /* 測試裡沒有 document */ }
    const src = jhArtSrc(m);
    const seal = jhSealWord(m);
    const name = jhPlaceName(m);
    const hero = `<section class="jh-hero${m.art && m.art.mood ? ` mood-${esc(m.art.mood)}` : ""}">
        ${src ? `<img class="jh-art" src="${esc(src)}" alt="" decoding="async">` : '<div class="jh-art none"></div>'}
        ${jhStatusHtml(m)}
        <div class="jh-pl"><h1>${esc(name)}</h1>${seal ? `<span class="jh-seal">${esc(seal)}</span>` : ""}</div>
      </section>`;
    // 眼下（第二批換成一張不會長高的卡，排回行動牌上面）：這一批進行中、提示、結算、來信、本週卡照舊的樣子，先排在行動牌底下——
    // 來信攤開有一屏高，排在上面會把四顆行動牌擠出第一屏（Joy 2026-10-26「四顆行動鈕一定在第一屏」）
    const eye = `${p.track}${p.hints}${p.resultCard}${p.peek}${p.letter}`;
    return `<div class="jh-page">${hero}${jhProseHtml(m, jhNoSealTwice(p.inner, seal), p.now)}${p.social}${p.jieyi}${p.links}${p.free}<div class="jh-acts">${jhActs(p.menu)}</div>${eye}${p.duty}${p.sealCard}${p.senseNotes}${p.hereRow}${p.peopleRow}${p.guideDown}${p.skip}${p.layers}</div>`;
  }
