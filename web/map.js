/* 天下大勢的網頁前端：輿圖（從 app.js 切出來，減法季批 0；說明見 app.js 檔頭）。 */
"use strict";

  // ── 輿圖 ──
  // 一張到底（企劃者 2026-10-30）：整個天下一張能自由拖、縮的圖，加一張抽屜。底圖的資料（/api/map/base：地點、路、大區、天下圖的地面、
  // 畫底圖用的 paint）一次載入只抓一次，疊層的 key 換了（劇情開放了新地點）才重抓；疊層（/api/map/state：誰佔著、勝算、分鐘……）
  // 打開輿圖、輪詢（MAP_STATE_EVERY）、做了動作之後重抓。底圖網頁自己畫成淡彩水墨、烤成一張圖（bakeBase）；字與小圖照螢幕大小寫在上面那一層（drawMarks）
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
  // 整頁一層（設計第一節）：夾在頂上的狀態列與底部分頁列之間。一張到底（企劃者 2026-10-30）：地圖框裡是一張能自由拖、縮的天下
  // （#mvw：畫好的底圖、地面、路線，照 S.mapCam 一起移動縮放）與疊在上面、照螢幕大小寫的字與小圖（#mkt，drawMarks）；
  // 外面浮著搜尋列與篩選、右下兩顆圓鈕、底下一張抽屜（寬 900 以上是右欄）。data-key 是底圖的 key：輿圖那一層常駐在 #map-host 時
  // （showMapHost），同一張底圖只換外圍、地圖那一塊原地留著（FB-324）
  function pageMap() {
    if (!S.mapBase || !S.mapState) return '<p class="muted">展開輿圖…</p>';
    const b = S.mapBase;
    return `<div class="${mapxClass()}" id="mapx" data-key="${esc(b.key)}">
      <div class="map-wrap" id="map"><div class="mv-world" id="mvw" style="width:${Number(b.w)}px;height:${Number(b.h)}px">`
      + `<canvas class="mv-ground" id="mk" style="width:${Number(b.w)}px;height:${Number(b.h)}px"></canvas>`
      + `<svg class="mv-route" id="mkr" width="${Number(b.w)}" height="${Number(b.h)}" viewBox="0 0 ${Number(b.w)} ${Number(b.h)}"></svg></div>`
      + `<div class="mv-marks" id="mkt"></div></div>${mapChrome()}
    </div>`;
  }
  function mapxClass() { return `mapx${S.mapMode === "timeline" ? " tl-mode" : ""}${S.mapMode === "search" ? " find-mode" : ""}`; }
  // 地圖框以外的那幾樣：上面的搜尋列與篩選、「正在看第幾週」、右下兩顆圓鈕（回到我、看整張）、抽屜、找地點那一整頁（開著才畫）
  function mapChrome() {
    const seeing = S.mapMode === "timeline" && S.mapWeek && S.mapWeek !== S.mapState.now_week;
    const banner = `<div class="map-banner" id="map-banner"${seeing ? "" : " hidden"}>${seeing ? `正在看${wkName(S.mapWeek, `第 ${S.mapWeek} 週`)}` : ""}</div>`;
    const top = `<div class="mv-top"><button type="button" class="mv-q map-search" data-act="map-search"><span aria-hidden="true">🔍</span><span>${MV_WORDS.search}</span></button>`
      + `<div class="mv-chips" id="mv-chips">${chipsHtml(S.mapBase, S.mapState)}</div></div>`;
    const fab = `<div class="mv-fab" id="mv-fab"><button type="button" class="mv-me" data-act="map-home" aria-label="${MV_WORDS.me}">◎</button><button type="button" data-act="map-fit" aria-label="${MV_WORDS.fit}">全</button></div>`;
    const find = S.mapMode === "search" ? `<div class="mv-find" id="mv-find">${searchHtml(S.mapBase, S.mapState, S.mapQuery)}</div>` : "";
    return `
      ${top}${banner}${fab}
      <section class="mdrawer" id="mdrawer" aria-label="輿圖抽屜"><div class="mgrab" id="mgrab" role="button" aria-label="拉高拉低"><i></i></div><div class="mbody" id="mbody">${drawerHtml()}</div></section>${find}`;
  }
  // ── 輿圖那一層常駐（FB-324）：切到別的分頁、整頁重畫（render 換掉 #app 的 innerHTML）時，地圖不拆掉，只在 #map-host 藏起來
  // （visibility: hidden：樣式、排版、點陣化都留著）。#map-host 在 #app 外面、body 底下（點擊照舊由 document 收）；.mapx 本來就是
  // position: fixed 的整頁一層，搬出 #page 位置一樣。沒有 #map-host（node 的假瀏覽器）時照舊畫在 #page
  function mapHost() {
    let host = document.getElementById("map-host");
    if (!host && document.body && document.body.insertAdjacentHTML) {
      document.body.insertAdjacentHTML("beforeend", '<div id="map-host" class="away"></div>');
      host = document.getElementById("map-host");
    }
    return host;
  }
  // 輿圖畫在常駐的那一層：同一張底圖（data-key 一樣）就只換外圍與 .mapx 的 class，地圖那一塊（底圖、地面、字）原地不動；
  // 底圖換了（劇情開了新地點）、第一次，整層重畫。畫不了（還沒有底圖、沒有 #map-host）回 false，照舊畫在 #page
  function showMapHost() {
    if (!S.mapBase || !S.mapState) return false;
    const host = mapHost();
    if (!host) return false;
    const box = document.getElementById("mapx");
    if (box && box.parentNode === host && box.dataset.key === String(S.mapBase.key) && box.querySelector(".mv-world")) {
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
  // 登出、登入（換帳號不重新整理、登入失效之後重新登入）：上一個人的輿圖全部清回開頭——底圖、疊層、看哪裡、選的地點、抽屜、
  // 版圖變化、找地點的字、篩選——常駐那一層整個清掉（FB-329）
  function forgetMap() {
    stopPlay();
    mvStop();
    Object.assign(S, {
      mapBase: null, mapState: null, mapStateAt: 0, mapSel: null, mapMode: "overview", mapDrawer: "peek",
      mapWeek: null, mapQuery: "", mapCam: null, mapFilter: "all", mapPreview: null,
    });
    hideMapHost(true);
  }
  // ── 輿圖的抽屜（設計 5.3）：一張卡（點一個地點、天下圖拉開你腳下這一處）、找地點、版圖變化；收著時一行 ──
  const SORTIE_WORD = { attack: "攻", hold: "守", stir: "攪局" }; // 出陣是哪一種（sortie.mode），待 joy 潤
  const SORTIE_CONVOY = "截糧"; // 運糧隊正打這裡經過（place.convoy，FB-9005）：跟行動列那一格一樣寫「出陣・截糧」（sortie_duel.CONVOY_NAME），不掛攻的勝算
  const ODDS_TONE_WEB = { 穩勝: "safe", 有把握: "safe", 五五波: "ok", 難分勝負: "ok", 凶險: "risk", 必敗: "risk", 操練: "safe" };
  const placeOf = (base, id) => base.places.find((p) => p.id === id);
  const ctrlSeal = (c) => (c ? `<span class="m-seal" style="background:${sideInk(c).color}">${esc(sideInk(c).short)}</span>` : '<span class="m-seal none">—</span>');
  // 抽屜裡畫什麼：版圖變化；點了一處是那一處的卡；平常（找地點那一整頁開著時也是）是「附近能去」一排卡片，往上拉是你腳下這一處的卡
  function drawerHtml() {
    const base = S.mapBase, st = S.mapState;
    if (S.mapMode === "timeline") return timelineHtml(base, st, mapWeek());
    if (S.mapMode === "place" && S.mapSel && st.places[S.mapSel]) return placeCard(base, st, S.mapSel);
    return nearHtml(base, st);
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
    const ropes = st.ropes.length ? `<div class="m-sec"><h4>${st.season_one ? "三條戰線" : "大勢"}</h4>${st.ropes.map(ropeHtml).join("")}</div>` : "";
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
      const risk = p.sortie === "attack" && p.odds && !p.convoy ? `${esc(p.odds.word)}・` : ""; // 截糧：按了打運糧隊，不是攻，不寫攻的勝算（FB-9005）
      const sortie = p.sortie && st.sorties_left !== null ? `<button type="button" class="main" data-act="map-jianghu" data-key="sortie">出陣・${p.convoy ? SORTIE_CONVOY : SORTIE_WORD[p.sortie] || ""}<small>${risk}今日還能 ${Number(st.sorties_left)} 次</small></button>` : "";
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
    // 本週要去的那一處（疊層的 week，減法季整合設計第七章）：名字後面一個字條
    const week = st.week && st.week.id === id ? `<b class="m-week">${NEAR_WORDS.weekGo}</b>` : "";
    // 由上往下（減法季整合設計第七章第 2 條：卡只佔三分之一）：名字、誰的、幾分、步行與疾行（動作）在第一屏；往上拉才有能悟、對手、人物、
    // 今日產出、出陣的那一份資料（攻城、正在翻、軍令懸賞……）。
    // 在路上：第一行照舊是往哪裡、還有幾分鐘、喊停（計畫 1.2、設計 5.3；FB-649）。擋路的那一則寫在動作那一排，這裡不重複
    return `${st.journey ? journeyHtml(st, false) : ""}<div class="m-h1">${ctrlSeal(p.control)}<span class="nm">${esc(b.name)}${here ? "（你）" : ""}</span>${week}<span class="meta">${p.rich ? `<b class="m-rich">${CARD_RICH}</b>` : ""}${far ? `<span>${far}</span>` : ""}</span><button type="button" class="m-x" data-act="map-back" aria-label="收起">✕</button></div>
      <div class="m-line"${lineInk}>${esc(placeLine(st, id))}</div>
      <div class="m-acts">${acts}${letter.button}</div>${letter.why}<i class="m-peek-end"></i>
      ${deskMap() ? "" : `<button type="button" class="m-pull" data-act="map-more">${NEAR_PULL}</button>`}
      ${siegeSection(id)}${flipSection(id)}${insightRow(base, b)}
      <div class="m-foes"><small>此地的對手</small><span>${foes}</span>${p.fierce ? `<div class="m-sub">${esc(p.fierce)}</div>` : ""}${p.people.length ? `<div class="m-sub">人物：${p.people.map(esc).join("、")}</div>` : ""}</div>
      ${p.yield ? `<div class="m-yield">${esc(p.yield)}</div>` : ""}
      ${p.order || p.bounty ? `<div class="m-sec"><h4>軍令與懸賞</h4>${p.order ? `軍令「${esc(p.order)}」在這裡記功` : ""}${p.order && p.bounty ? "；" : ""}${p.bounty ? `懸賞「${esc(p.bounty)}」在這裡交差` : ""}</div>` : ""}
      ${held}${terrainArtsRow(b)}
      ${p.services.length ? `<div class="m-sec"><h4>此地</h4>${p.services.map(esc).join("・")}</div>` : ""}
      <div class="m-sec"><h4>劇情</h4>${p.goal ? "★ 這一幕主線的目標　" : ""}${p.news ? "✦ 最近有大事與傳聞" : p.goal ? "" : "最近沒有大事"}</div>
      ${cardExtras(base, st)}`;
  }
  // 找地點（一張到底，企劃者 2026-10-30）：整頁一張清單。沒打字是捷徑——本週要事、附近的人物、跳到大區；打字找地點（地名、大區名、
  // 多半什麼、店面）與人物，近的在前。挑了一處：地圖飛過去、抽屜開那一處的卡（map-pick）。打字時只換結果那一塊（searchResults）
  const SEARCH_ROWS = 12; // 地點最多列幾處
  function searchRow(id, icon, title, small, right) {
    return `<button type="button" class="m-sr" data-act="map-pick" data-id="${esc(id)}"><span class="ic">${icon}</span><span class="tx"><b>${title}</b>${small ? `<small>${small}</small>` : ""}</span><span class="r">${right}</span></button>`;
  }
  function searchFar(st, id) {
    const p = st.places[id];
    if (id === st.here && !st.journey) return MV_WORDS.here;
    return p && p.minutes !== null && p.minutes !== undefined ? `${Number(p.minutes)} 分` : "";
  }
  const byMinutes = (st) => (a, z) => (st.places[a.id].minutes ?? 1e9) - (st.places[z.id].minutes ?? 1e9);
  function searchResults(base, st, q) {
    const want = (q || "").trim();
    const regions = Object.fromEntries(base.regions.map((r) => [r.id, r.name]));
    const shown = base.places.filter((b) => st.places[b.id]);
    const who = (filter) => shown.flatMap((b) => st.places[b.id].people.filter(filter).map((n) => [n, b])).sort((a, z) => byMinutes(st)(a[1], z[1]));
    const person = ([n, b]) => searchRow(b.id, `<i class="m-who1">${esc(n.slice(0, 1))}</i>`, esc(n), `在${esc(b.name)}`, searchFar(st, b.id));
    if (!want) {
      const wk = st.week && placeOf(base, st.week.id) && st.places[st.week.id] ? st.week : null;
      const week = wk ? `<h4>${MV_WORDS.weekHead}</h4>${searchRow(wk.id, "★", esc(placeOf(base, wk.id).name), esc(wk.why || ""), searchFar(st, wk.id))}` : "";
      const figs = who(() => true).slice(0, 8);
      return `${week}${figs.length ? `<h4>${MV_WORDS.figures}</h4>${figs.map(person).join("")}` : ""}`
        + `<h4>${MV_WORDS.jump}</h4><div class="m-regs">${base.regions.map((r) => `<button type="button" class="mv-chip" data-act="map-region" data-id="${esc(r.id)}">${esc(r.name)}</button>`).join("")}</div>`;
    }
    const hit = (b) => {
      const p = st.places[b.id];
      return b.name.includes(want) || (regions[b.region] || "").includes(want) || (b.mostly || "").includes(want) || p.services.some((s) => s.includes(want));
    };
    const places = shown.filter(hit).sort(byMinutes(st)).slice(0, SEARCH_ROWS);
    const people = who((n) => n.includes(want));
    let html = "";
    if (places.length) {
      html += `<h4>${MV_WORDS.places}</h4>` + places.map((b) => {
        const p = st.places[b.id];
        const small = [regions[b.region], b.mostly, ...p.services].filter(Boolean).map(esc).join("・");
        return searchRow(b.id, iconHtml(b, 26), esc(b.name), small, searchFar(st, b.id));
      }).join("");
    }
    if (people.length) html += `<h4>${MV_WORDS.people}</h4>` + people.map(person).join("");
    return html || `<p class="m-sub m-none">${esc(MV_WORDS.notFound.replace("{q}", want))}</p>`;
  }
  function searchHtml(base, st, q) {
    return `<div class="m-search"><button type="button" class="m-x" data-act="map-back" aria-label="返回">←</button><input class="m-q" id="map-q" type="search" placeholder="${MV_WORDS.search}" value="${esc(q || "")}" autocomplete="off" aria-label="找地點、找人物"></div>
      <div class="m-results" id="map-results">${searchResults(base, st, q)}</div>`;
  }
  // ── 天下怎麼變（設計第六節）：上面一張曲線（三條戰線、大事 📜、你在看的那一週），三方各佔幾處、比開季多少，
  // 年表（B 的：一列一個可易手的地點、一格一週，顏色是那一週誰佔著、白點是那一週易手），那一週的大事與易手。
  // 地圖同時照那一週畫（地面照那一週上色、易手的地點閃一圈；mapTimeline 把地圖框縮到抽屜上面、整張放進來）
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
  // 打開、收起版圖變化：打開時地圖框縮到抽屜上面、整張天下放進那一塊（字退到最遠那一段：大區、各方幾處、地面照那一週上色）；
  // 收起時回附近那一排、看整張。看的時候與播放中照樣能拖縮（播放只換記號）
  function mapTimeline(open) {
    stopPlay();
    if (!document.getElementById("mapx")) return;
    if (open) Object.assign(S, { mapMode: "timeline", mapSel: null, mapPreview: null, mapWeek: S.mapState.now_week, mapDrawer: "tl" });
    else Object.assign(S, { mapMode: "overview", mapSel: null, mapPreview: null, mapWeek: null, mapDrawer: "peek" });
    remapChrome();
    const g = mapGeom(document.getElementById("map"));
    if (g) camFly(camFit(g));
    drawRoute();
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
  // 抽屜的把手：拖上拖下（放開時靠到最近的一格），點一下在第一格與最後一格之間換
  function drawerGrab() {
    const grab = document.getElementById("mgrab"), drawer = document.getElementById("mdrawer");
    if (!grab || !drawer || (grab.dataset && grab.dataset.wired)) return; // 同一個把手只掛一次（remapChrome 換了新的把手才再掛）
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
      if (drag.moved) drawer.style.height = `${Math.max(MV_PEEK_MIN, Math.min(mapDrawerPx("full"), drag.h + dy))}px`;
    });
    const end = () => {
      if (!drag) return;
      drawer.classList.remove("dragging");
      const stops = drawerStops();
      if (!drag.moved) setMapDrawer(S.mapDrawer === stops[0] ? stops[stops.length - 1] : stops[0]);
      else {
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
    return ["peek", "full"];
  }
  // 卡上「往上拉：能悟、對手……」、附近那一排往上拉
  function mapOpen() { setMapDrawer(S.mapMode === "place" ? "half" : "full"); }

  // 重畫抽屜（輪詢換了疊層、篩選、版圖換週）：附近那一排滑到哪、抽屜捲到哪照留
  function redrawDrawer() {
    const body = document.getElementById("mbody");
    if (!body) return;
    const what = `${S.mapMode}|${S.mapSel || ""}`, same = !!body.dataset && body.dataset.what === what;
    const row = same && body.querySelector && body.querySelector(".m-cards"), left = row ? row.scrollLeft : 0, top = same ? body.scrollTop || 0 : 0;
    body.innerHTML = drawerHtml();
    if (body.dataset) body.dataset.what = what;
    const row2 = body.querySelector && body.querySelector(".m-cards");
    if (row2 && left) row2.scrollLeft = left;
    if (top) body.scrollTop = top;
    cardsWire();
  }
  // 桌機（寬 900 以上）抽屜是右欄、整欄攤開，沒有收起這回事
  const deskMap = () => !!(window.matchMedia && window.matchMedia("(min-width: 900px)").matches);
  // 抽屜的高度：半開（量到內容裡 .m-peek-end 那一點：附近那一排卡片底下、卡的動作那一排底下）、拉高六成、全開九成四、版圖變化 320；
  // 量不到（還沒排版）照預設。桌機是右欄（CSS 蓋掉高度）
  const MV_PEEK_MIN = 120, MV_PEEK_NEAR = 196, MV_PEEK_PLACE = 200;
  function mapDrawerPx(h) {
    const box = document.getElementById("mapx");
    const avail = (box && box.clientHeight) || 600;
    // 版圖變化 320 高（企劃者 10/15 從對比圖選乙）：地圖大一截，曲線與處數在一屏，年表往下捲
    return { half: Math.round(avail * 0.6), full: Math.round(avail * 0.94), tl: Math.min(320, Math.round(avail * 0.55)) }[h] || peekPx(avail);
  }
  function peekPx(avail) {
    const end = document.querySelector("#mbody .m-peek-end");
    const at = end && end.offsetTop ? end.offsetTop + 10 : 0;
    const fall = S.mapMode === "place" ? Math.max(MV_PEEK_PLACE, Math.round(avail / 3)) : MV_PEEK_NEAR;
    return Math.round(Math.min(avail * 0.6, Math.max(MV_PEEK_MIN, at || fall)));
  }
  function setMapDrawer(h) {
    S.mapDrawer = h;
    const d = document.getElementById("mdrawer"), box = document.getElementById("mapx");
    if (!d || !box) return;
    const px = mapDrawerPx(h);
    d.style.height = `${px}px`;
    // 右下兩顆圓鈕跟著抽屜上下（直接寫在那一塊上：寫在框上的自訂屬性會一路繼承，整棵地圖重算樣式，FB-322）
    const fab = document.getElementById("mv-fab");
    if (fab && fab.style) fab.style.bottom = deskMap() ? "" : `${px + 12}px`;
    // --md-h 只有版圖變化用得到（地圖框縮到抽屜上面，style.css 的 .mapx.tl-mode）
    if (S.mapMode === "timeline") box.style.setProperty("--md-h", `${px}px`);
  }
  // 整頁那一層夾在狀態列與分頁列之間：狀態列展開收起、視窗換大小時重量。回傳兩條邊有沒有變（變了地圖框就換了高，要重夾：FB-710）
  function mapFrame() {
    const box = document.getElementById("mapx");
    if (!box) return false;
    const top = document.getElementById("top"), tabs = document.querySelector(".tabs");
    const t = `${top && !top.hidden ? Math.round(top.getBoundingClientRect().bottom) : 0}px`;
    const b = `${tabs ? Math.round(window.innerHeight - tabs.getBoundingClientRect().top) : 0}px`;
    const was = typeof box.style.getPropertyValue === "function" ? [box.style.getPropertyValue("--map-top"), box.style.getPropertyValue("--map-bottom")] : null;
    // 變了才寫：自訂屬性會繼承到整張地圖，寫一次整棵重算樣式（狀態列每次重畫都叫這裡，Joy 2026-10-17）
    setVar(box, "--map-top", t);
    setVar(box, "--map-bottom", b);
    return !was || was[0] !== t || was[1] !== b;
  }

  // ── 一張到底（企劃者 2026-10-30「可以 這樣改」，示意稿第四版：讓地圖能自由滑動縮放、搜尋）──
  // 以前是三張固定取景的圖（第一層、全區、天下），從 A 到 B 要切好幾次地區。現在整個天下一張：一指拖（放手會順著滑）、兩指捏、滾輪、
  // 雙擊放大，從看得到整張天下縮到約 3 倍。字照倍率分三段（drawMarks）：遠看大區名與各方幾處、地點是一顆照誰佔著上色的點、地面照歸屬上色
  // （以前的天下圖）；中間每一處的小圖與名字、誰佔著的小印、寶；近看再加此地能悟、幾分・多什麼・勝算。名字撞在一起時讓開，讓不開的先收
  // （選的、你在的、本週要去的、篩到的、要地、近的先畫）。
  // 底圖不再用伺服器畫好的那一張：主機畫的淡彩水墨（web/img/map/base.webp）疊上州界與路，烤成一張圖（bakeBase）；抓不到那一張時
  // 網頁照內容（底圖的 paint：大區、河、山、林）自己畫。山河名照 paint 寫在字那一層；
  // 城與營用畫的小圖（web/img/map）。拖縮的每一幀只換兩層的 transform（底圖那一層、字那一層照上一次排字的倍率先跟著縮放），
  // 縮放差過一截、跨了一段、停下來才重排字（地點多也不卡）。字待 joy 潤
  const MV_WORDS = {
    search: "要去哪？地點、人物、店面", all: "全部", sense: "能悟", tl: "⏱ 版圖", me: "回到我", fit: "看整張天下",
    from: "從{place}出發", road: "沿路能去", swipe: "由近到遠，左右滑", swipeWk: "本週要去的排第一，其餘由近到遠", none: "附近沒有。拉遠一點看看，或換個標籤。", week: "本週", here: "你在這裡", next: "下一站", end: "終點",
    weekHead: "本週要事", figures: "附近的人物", jump: "跳到大區", places: "地點", people: "人物",
    notFound: "找不到「{q}」。地名、大區、人物、店面（醫館、鐵匠鋪、馬市）都找得到。",
  };
  const MV_CHIP_PEOPLE = "有人物";
  const NEAR_WORDS = { weekGo: "本週要去", bounty: "有賞" }; // 待 joy 潤
  const NEAR_PULL = "往上拉：能悟、對手、人物、今日產出"; // 待 joy 潤
  const RICH_WORD = "寶", LETTER_SEAL_WORD = "戰";
  const MV_ZMAX = 3.2; // 最多放大幾倍（地圖 1 單位＝螢幕 1px 是 1 倍）；最小是整張天下放得下
  const MV_LV1 = 0.72, MV_LV2 = 1.35; // 字分三段的倍率
  const MV_TOP = 100, MV_TL_TOP = 36; // 上面浮著的搜尋列與篩選讓開多高（px）；版圖變化時只讓開「正在看第 N 週」
  const MV_OPEN_Z = 1.15, MV_PICK_Z = 1.4, MV_HOME_Z = 1.2, MV_PREVIEW_Z = 1.1; // 打開輿圖、搜到一處、回到我、滑卡片時至少放到多大
  const MV_SLOP = 6; // 按下之後移過幾 px 才算拖
  const MV_CLICK = 400; // 拖完放開之後，多久內落在地圖上的 click 吃掉（ms）
  const MV_WHEEL = 0.0015; // 滾輪每 1px 的 deltaY 縮放多少（exp）
  const MV_TAP2 = 300; // 兩下點在多久之內算雙擊（ms）
  const MV_FRICTION = 0.92, MV_COAST = 0.15; // 放手後每 16ms 剩幾成速度；放手時至少多快（px/ms）才順著滑
  const MV_RELAYOUT = 0.18; // 拖縮中字那一層先跟著縮放，倍率差過這麼多（log）才重排
  const MV_FLY = 520, MV_FLY_FAR = 800; // 飛過去多久（ms）；遠的先拉遠一點再拉近
  const MV_PAINT = { city: 62, city2: 62, outpost: 40, tents: 46, camp: 46 }; // 畫的小圖多寬（px，近看那一段；中間那一段八成）
  const MV_MOUNTS = ["m2", "m3", "m4", "m5", "m6"]; // 底圖上一座一座蓋上去的山
  const MV_INK = "#2F2821", MV_SUB_INK = "#6E5E49", MV_UNHELD = "#8C7F68";
  const MV_NEAR_MAX = 24; // 附近那一排最多幾張
  const mvImg = (k) => `/static/img/map/${k}.webp`;
  const mvLevel = (z) => (z < MV_LV1 ? 0 : z < MV_LV2 ? 1 : 2);

  // ── 小工具：位置、路、名字旁那一行 ──
  const placeXY = (id) => {
    const p = id && S.mapBase && S.mapBase.places.find((x) => x.id === id);
    return p ? [p.x, p.y] : null;
  };
  // 你此刻在哪（在路上是路上那一點）
  function youXY(base, st) {
    if (st.journey) return [st.journey.x, st.journey.y];
    const h = placeOf(base, st.here);
    return h ? [h.x, h.y] : null;
  }
  // 本週要去的那一處（疊層的 week；那一處不在疊層裡就不算）
  function nearWeek(st) {
    return st.week && st.places[st.week.id] ? st.week : null;
  }
  // 一條路畫成哪一條曲線（底圖的 roads：跟底圖同一條二次曲線）；沒有那一份（舊的底圖）照直線
  const roadMemo = new WeakMap();
  function roadBend(base, a, b) {
    let m = roadMemo.get(base);
    if (!m) {
      m = {};
      for (const [x, y, qx, qy] of base.roads || []) m[`${x}|${y}`] = [qx, qy];
      roadMemo.set(base, m);
    }
    return m[a < b ? `${a}|${b}` : `${b}|${a}`] || null;
  }
  // 從你走到 id 那一處的路（疊層的 path：依序經過的站）：SVG 的 d；就在這裡、走不到是空字串
  function routeD(base, st, id) {
    const q = st.places[id], me = youXY(base, st);
    if (!q || !me || !q.path || !q.path.length) return "";
    let d = `M${f1(me[0])},${f1(me[1])}`, from = st.journey ? null : st.here;
    for (const step of q.path) {
      const p = placeOf(base, step);
      if (!p) return "";
      const c = from ? roadBend(base, from, step) : null;
      d += c ? `Q${c[0]},${c[1]} ${p.x},${p.y}` : `L${p.x},${p.y}`;
      from = step;
    }
    return d;
  }
  // 名字旁那一行：分鐘數＋多半（城多事、野多敵……；接了討伐懸賞寫「有賞」）；本週那一處寫分鐘數＋一句為什麼
  // 底圖帶 viewer_mostly（減法季探索一顆開著，伺服器照你站過去之後鈕上的小字給）時，兩個字整個照底圖：「有賞」也是伺服器給的；
  // 沒帶（關著的季、序章）照舊，疊層的 bounty 含「討伐」就寫「有賞」
  function nearSub(base, st, id, week) {
    const q = st.places[id], b = placeOf(base, id);
    const far = q.minutes !== null && q.minutes !== undefined ? `${Number(q.minutes)} 分` : "";
    if (week && week.id === id) return [far, week.why].filter(Boolean).join("・");
    const tag = !base.viewer_mostly && q.bounty && q.bounty.includes("討伐") ? NEAR_WORDS.bounty : b.mostly || "";
    return [far, tag].filter(Boolean).join("・");
  }
  // 估一段字在螢幕上多寬（px）：中日韓的字一個字寬、數字與英文約六成、空白約三成
  function textW(text, px) {
    let w = 0;
    for (const ch of String(text)) w += ch === " " ? 0.3 : ch.charCodeAt(0) < 0x2e80 ? 0.6 : 1;
    return w * px;
  }
  // 墨筆小圖（城、營、寺、渡、山、野；底圖給的 glyph）：20×20、中心在 (0, 0)
  function inkIcon(glyph, ink, paper) {
    const sw = `stroke="${ink}" stroke-width="1.3" fill="${paper}" stroke-linejoin="round" stroke-linecap="round"`;
    if (glyph === "城") return `<rect x="-10" y="-5" width="20" height="11" ${sw}/><path d="M-10 -5V-9H-6V-5M-3 -5V-9H3V-5M6 -5V-9H10V-5" ${sw}/><path d="M-3 6V1A3 3 0 0 1 3 1V6" fill="${ink}"/>`;
    if (glyph === "營") return `<path d="M-10 8L0 -8L10 8Z" ${sw}/><path d="M-3 8L0 2L3 8" fill="${ink}"/><path d="M0 -8V-15L7 -13L0 -10" fill="${ink}" stroke="${ink}" stroke-width="1"/>`;
    if (glyph === "寺") return `<path d="M-11 -1L0 -11L11 -1Z" ${sw}/><path d="M-7 -11L0 -17L7 -11Z" ${sw}/><rect x="-5" y="-1" width="10" height="8" ${sw}/>`;
    if (glyph === "渡") return `<path d="M-11 2Q0 11 11 2Z" ${sw}/><line x1="0" y1="2" x2="0" y2="-11" stroke="${ink}" stroke-width="1.4"/><path d="M0 -11L9 -5L0 -1Z" ${sw}/>`;
    if (glyph === "山") return `<path d="M-12 7L-5 -5L-1 1L4 -9L12 7Z" ${sw}/><path d="M4 -9l3 7" stroke="${ink}" stroke-width=".9"/>`;
    return `<path d="M-9 6V-1M-5 6V-5M-1 6V0M3 6V-5M7 6V-1" stroke="${ink}" stroke-width="1.5" fill="none" stroke-linecap="round"/><circle cx="-7" cy="-3" r="1.2" fill="${ink}"/>`;
  }
  // 城與營用畫的小圖（大城、小城、大營、小營）；其餘是 null（用墨筆小圖）。兩張大城照 id 錯開
  function paintKey(b) {
    if (b.glyph === "城") return b.big ? ([...String(b.id)].reduce((n, ch) => n + ch.charCodeAt(0), 0) % 2 ? "city2" : "city") : "outpost";
    if (b.glyph === "營") return b.big ? "tents" : "camp";
    return null;
  }
  // 卡片、搜尋結果裡的小圖
  function iconHtml(b, s = 30) {
    const k = paintKey(b);
    return k ? `<img src="${mvImg(k)}" width="${s + 6}" alt="" draggable="false">`
      : `<svg width="${s}" height="${s}" viewBox="-15 -17 30 30" aria-hidden="true">${inkIcon(b.glyph, MV_INK, "none")}</svg>`;
  }
  // 正在翻那一層的斜紋（每一個出現在 tug 裡的攻方一個 <pattern>，顏色照 sideInk；地圖單位，k＝1／倍率）
  const WORLD_TUG_MAX = 0.75, WORLD_TUG_GAP = 5, WORLD_TUG_LINE = 2.2;
  const WORLD_COOL_DASH = 4, WORLD_COOL_GAP = 3, WORLD_COOL_LINE = 1.4;
  const WORLD_LETTER_DASH = 6, WORLD_LETTER_GAP = 3.5, WORLD_LETTER_LINE = 2.6;
  const WORLD_GROUND = 0.62; // 地面那一層多濃（淡彩：底下的山河要透得上來）
  function tugPattern(side, k) {
    const ink = sideInk(side), gap = f1(WORLD_TUG_GAP * k);
    return `<pattern id="wt-${esc(side)}" patternUnits="userSpaceOnUse" width="${gap}" height="${gap}" patternTransform="rotate(45)">`
      + `<rect width="${gap}" height="${gap}" fill="${ink.soft}" fill-opacity=".55"/><line x1="0" y1="0" x2="0" y2="${gap}" stroke="${ink.color}" stroke-width="${f1(WORLD_TUG_LINE * k)}"/></pattern>`;
  }
  // 這一格正在被誰翻、翻到幾成（疊層的 tug 裡進度最高的那一方；守方自己、進度 0 不算）；沒有是 null。名字底下的進度條也照它
  function tugOf(st, id, holder) {
    const t = st.places[id] && st.places[id].tug;
    if (!t) return null;
    const best = Object.entries(t).filter(([sd, v]) => sd !== holder && Number(v) > 0).sort((a, z) => Number(z[1]) - Number(a[1]))[0];
    return best ? { side: best[0], pct: Math.min(100, Number(best[1])) } : null;
  }
  // 塗層（地面照歸屬上色）：遠看那一段本來就有；開著時近看也有。記在這個瀏覽器（平常關著）
  const WASH_WORD = "塗層"; // 待 joy 潤
  const WASH_KEY = "tx-map-wash";
  function washOn() {
    if (S.mapWash === undefined) { try { S.mapWash = localStorage.getItem(WASH_KEY) === "1"; } catch (e) { S.mapWash = false; } }
    return !!S.mapWash;
  }
  function washToggle() {
    S.mapWash = !washOn();
    try { localStorage.setItem(WASH_KEY, S.mapWash ? "1" : "0"); } catch (e) { /* 記不住就只管這一次 */ }
    chipsRedraw();
    drawMarks();
  }

  // ── 篩選（上面那一排標籤）：全部、多半什麼（照底圖的 mostly，多的在前）、寶、有人物、能悟哪一種；再加塗層、版圖。
  // 篩到的照舊畫、名字先畫，其餘淡掉；附近那一排只列篩到的 ──
  const MV_KINDS_MAX = 6;
  function chipList(base, st) {
    const shown = base.places.filter((b) => st.places[b.id]);
    const most = {}, kinds = {};
    for (const b of shown) {
      if (b.mostly) most[b.mostly] = (most[b.mostly] || 0) + 1;
      for (const id of b.insights || []) kinds[id] = (kinds[id] || 0) + 1;
    }
    const out = [["all", MV_WORDS.all]];
    for (const [m] of Object.entries(most).sort((a, z) => z[1] - a[1]).slice(0, 4)) out.push([`most:${m}`, esc(m)]);
    if (shown.some((b) => st.places[b.id].rich)) out.push(["rich", `<i class="mv-red">${RICH_WORD}</i>`]);
    if (shown.some((b) => st.places[b.id].people.length)) out.push(["people", MV_CHIP_PEOPLE]);
    for (const [id] of Object.entries(kinds).sort((a, z) => z[1] - a[1]).slice(0, MV_KINDS_MAX)) {
      const ink = insightInk(base, id);
      if (ink) out.push([`ins:${id}`, `${MV_WORDS.sense}<i style="color:${ink.c}">${esc(ink.name)}</i>`]);
    }
    return out;
  }
  function chipsHtml(base, st) {
    if (!base || !st) return "";
    const f = S.mapFilter || "all", wash = washOn();
    return chipList(base, st).map(([k, t]) => `<button type="button" class="mv-chip${f === k ? " on" : ""}" data-act="map-filter" data-id="${esc(k)}" aria-pressed="${f === k}">${t}</button>`).join("")
      + `<button type="button" class="mv-chip${wash ? " on" : ""}" data-act="map-wash" aria-pressed="${wash}">${WASH_WORD}</button>`
      + `<button type="button" class="mv-chip w-tl" data-act="map-timeline" aria-pressed="false">${MV_WORDS.tl}</button>`;
  }
  function chipsRedraw() {
    const box = document.getElementById("mv-chips");
    if (box) box.innerHTML = chipsHtml(S.mapBase, S.mapState);
  }
  const chipName = (base, st, f) => ((chipList(base, st).find(([k]) => k === f) || ["", ""])[1]).replace(/<[^>]+>/g, "");
  function mvMatch(st, b) {
    const f = S.mapFilter || "all", q = st.places[b.id];
    if (f === "all" || !q) return true;
    if (f === "rich") return !!q.rich;
    if (f === "people") return q.people.length > 0;
    if (f.startsWith("most:")) return b.mostly === f.slice(5);
    if (f.startsWith("ins:")) return (b.insights || []).includes(f.slice(4));
    return true;
  }
  function mapFilter(f) {
    S.mapFilter = !f || S.mapFilter === f ? "all" : f;
    chipsRedraw();
    if (S.mapMode === "overview" || S.mapMode === "search") { redrawDrawer(); setMapDrawer(S.mapDrawer); }
    drawMarks();
  }

  // ── 抽屜平常那一張：「從某處出發」一排卡片（近的在前、本週要去的排第一，左右滑；滑停在哪一張地圖就飛過去、畫出路線），
  // 往上拉是你腳下這一處的卡（出陣、探索、今天去哪裡出陣、戰線、本週大事）；在路上是往哪裡、喊停，往上拉是那三段 ──
  function nearList(base, st) {
    const here = st.journey ? null : st.here, wk = nearWeek(st);
    const list = base.places.filter((b) => {
      const q = st.places[b.id];
      return b.id !== here && q && q.minutes !== null && q.minutes !== undefined && mvMatch(st, b);
    }).sort(byMinutes(st));
    const i = wk ? list.findIndex((b) => b.id === wk.id) : -1;
    if (i > 0) list.unshift(list.splice(i, 1)[0]);
    return list.slice(0, MV_NEAR_MAX);
  }
  function nearCard(base, st, b) {
    const q = st.places[b.id], wk = nearWeek(st), isWk = !!wk && wk.id === b.id;
    const odds = q.odds ? `・<b style="color:${TONE_COLOR[q.odds.tone] || MAP_INK}">${esc(q.odds.word)}</b>` : "";
    const ins = (b.insights || []).map((id) => insightInk(base, id)).filter(Boolean).slice(0, 2).map((k) => `<i style="color:${k.c}">${esc(k.name)}</i>`).join("");
    return `<button type="button" class="m-pc${S.mapPreview === b.id ? " on" : ""}" data-act="map-place" data-id="${esc(b.id)}">${iconHtml(b, 30)}`
      + `<b>${esc(b.name)}${q.rich ? `<em>${RICH_WORD}</em>` : ""}${isWk ? `<em class="wk">${MV_WORDS.week}</em>` : ""}</b>`
      + `<span>${esc(nearSub(base, st, b.id, wk))}${odds}${ins ? `・${ins}` : ""}</span></button>`;
  }
  function nearHtml(base, st) {
    const here = placeOf(base, st.here), list = nearList(base, st), f = S.mapFilter || "all";
    const from = st.journey ? MV_WORDS.road : MV_WORDS.from.replace("{place}", here ? here.name : "");
    const label = f === "all" ? from : `${chipName(base, st, f)}・${list.length} 處`;
    // 本週那一處排在第一張（不管多遠）：小字照實說，不寫成「由近到遠」（全面自檢 U-16）
    const wk = nearWeek(st), wkFirst = !!wk && list.length > 1 && list[0].id === wk.id;
    const head = `<div class="m-nhead"><b>${esc(label)}</b><small>${wkFirst ? MV_WORDS.swipeWk : MV_WORDS.swipe}</small></div>`;
    const cards = list.length ? `<div class="m-cards">${list.map((b) => nearCard(base, st, b)).join("")}</div>` : `<p class="m-sub m-none">${MV_WORDS.none}</p>`;
    // 第 3 週「離贏還差多少」（減法季整合設計 6.8）
    const gap = st.gap ? `<p class="m-gap">${esc(st.gap)}</p>` : "";
    const mine = here && !st.journey ? `<div class="m-mine">${placeCard(base, st, st.here)}</div>` : cardExtras(base, st);
    return `${st.journey ? journeyHtml(st) : ""}${head}${cards}<i class="m-peek-end"></i>${gap}${mine}`;
  }
  // 附近那一排左右滑：停在哪一張（照中線最近的那一張），地圖就飛過去、畫出路線（不開卡；點一下才開）
  let cardsTimer = 0;
  function cardsWire() {
    const row = document.querySelector("#mbody .m-cards");
    if (!row || !row.addEventListener || (row.dataset && row.dataset.wired)) return;
    if (row.dataset) row.dataset.wired = "1";
    row.addEventListener("scroll", () => {
      clearTimeout(cardsTimer);
      cardsTimer = setTimeout(() => {
        const mid = row.scrollLeft + row.clientWidth / 2;
        let best = null, d = 1e9;
        for (const el of row.children) {
          const c = el.offsetLeft + el.offsetWidth / 2;
          if (Math.abs(c - mid) < d) { d = Math.abs(c - mid); best = el; }
        }
        if (!best || !best.dataset.id || best.dataset.id === S.mapPreview) return;
        for (const el of row.children) el.classList.toggle("on", el === best);
        mapPreviewTo(best.dataset.id);
      }, 120);
    }, { passive: true });
  }
  function mapPreviewTo(id) {
    S.mapPreview = id;
    drawRoute();
    const p = placeXY(id), c = S.mapCam;
    if (p && c) mapFlyTo(p, Math.max(c.z, MV_PREVIEW_Z));
    else drawMarks();
  }

  // ── 地面（以前的天下圖，輿圖簡化設計 5.1、4.1～4.4）：每一區的地面照「離哪個地點最近」分給那個地點此刻（或版圖變化看的那一週）的控制方
  // （底圖的 world.cells，照那一區的輪廓裁），一方一色、沒人佔一色（顏色照劇本）；正在翻（攻方的斜紋照進度泛進來）、剛易手還在冷卻
  // （新主人的淡色、一圈虛線）、紅線（兩方的地面相接）、細墨線（有主與沒人佔相接）、激戰（那一格一圈紅光閃）、下了戰書（朱紅虛線框）。
  // 遠看那一段、塗層開著、版圖變化時才畫（#mk；底下的山水淡淡透上來）。純函式：k＝1／倍率（線寬照螢幕）、week 看哪一週
  function groundSvg(base, st, k, week) {
    const wd = base.world;
    if (!wd) return "";
    const ctrl = controlAt(st, week), live = week === st.now_week;
    const cooling = (id) => live && !!ctrl[id] && !!(st.places[id] && st.places[id].cool);
    const ground = (id) => sideInk(ctrl[id])[cooling(id) ? "tint" : "soft"];
    const tugs = live ? wd.cells.map((c) => [c, tugOf(st, c.id, ctrl[c.id] || null)]).filter(([, t]) => t) : [];
    const melee = live ? wd.cells.filter((c) => st.places[c.id] && (st.places[c.id].melee || st.places[c.id].siege === "fight")) : [];
    const letters = live ? wd.cells.filter((c) => st.places[c.id] && st.places[c.id].siege === "letter") : [];
    const cools = wd.cells.filter((c) => cooling(c.id));
    const patterns = [...new Set(tugs.map(([, t]) => t.side))].map((sd) => tugPattern(sd, k)).join("");
    // 淡彩水暈（企劃者 2026-10-30「勢力範圍的多邊形還是一定只能那麼醜嗎」）：每一格照控制方的淡色平塗，整層用水暈的濾鏡把邊揉開、
    // 往外滲一點、邊上積一圈稍濃的顏料（像水彩乾掉的邊），乘在底圖上（.mv-ground 的 mix-blend-mode）；沒人佔的不上色，露出底圖。
    // 大區的墨線外框、有主與沒人佔之間的細墨線拿掉了（州界在底圖上）；兩方相接的紅線改成一筆淡一點的朱砂
    const out = [`<defs>${wd.regions.map((r) => `<clipPath id="wc-${esc(r.id)}"><path d="${r.d}"/></clipPath>`).join("")}${patterns}`
      + '<filter id="mv-wash" x="-15%" y="-15%" width="130%" height="130%"><feTurbulence type="fractalNoise" baseFrequency=".022" numOctaves="3" seed="11" result="n"/>'
      + '<feDisplacementMap in="SourceGraphic" in2="n" scale="26" result="d"/><feGaussianBlur in="d" stdDeviation="4.5" result="b"/>'
      + '<feMorphology in="d" operator="erode" radius="3" result="e"/><feGaussianBlur in="e" stdDeviation="2" result="eb"/>'
      + '<feComposite in="b" in2="eb" operator="out" result="rim"/><feComponentTransfer in="rim" result="rim2"><feFuncA type="linear" slope=".55"/></feComponentTransfer>'
      + '<feMerge><feMergeNode in="b"/><feMergeNode in="rim2"/></feMerge></filter>'
      + '<filter id="mv-stroke" x="-5%" y="-5%" width="110%" height="110%"><feTurbulence type="fractalNoise" baseFrequency=".08" numOctaves="2" seed="4"/><feDisplacementMap in="SourceGraphic" scale="5"/><feGaussianBlur stdDeviation=".6"/></filter></defs>'];
    out.push(`<g class="w-ground" opacity="${WORLD_GROUND}" filter="url(#mv-wash)">`);
    for (const r of wd.regions) {
      const held = wd.cells.filter((c) => c.region === r.id && ctrl[c.id]);
      if (held.length) out.push(`<g clip-path="url(#wc-${esc(r.id)})">${held.map((c) => `<path data-cell="${esc(c.id)}" d="${c.d}" fill="${ground(c.id)}" stroke="${ground(c.id)}" stroke-width="2"/>`).join("")}</g>`);
    }
    out.push("</g>");
    for (const r of wd.regions) {
      const mine = tugs.filter(([c]) => c.region === r.id);
      if (mine.length) out.push(`<g clip-path="url(#wc-${esc(r.id)})">${mine.map(([c, t]) => `<path class="w-tug" data-cell="${esc(c.id)}" d="${c.d}" fill="url(#wt-${esc(t.side)})" opacity="${f2((t.pct / 100) * WORLD_TUG_MAX)}"/>`).join("")}</g>`);
    }
    for (const c of cools) out.push(`<path class="w-cool" data-cell="${esc(c.id)}" d="${c.d}" fill="none" stroke="${sideInk(ctrl[c.id]).color}" stroke-width="${f1(WORLD_COOL_LINE * k)}" stroke-dasharray="${f1(WORLD_COOL_DASH * k)} ${f1(WORLD_COOL_GAP * k)}" stroke-linejoin="round" clip-path="url(#wc-${esc(c.region)})"/>`);
    const front = [];
    for (const e of wd.edges) {
      const a = (e.a && ctrl[e.a]) || null, b = (e.b && ctrl[e.b]) || null;
      if (a && b && a !== b) front.push(`<path d="${e.d}"${e.clip ? ` clip-path="url(#wc-${esc(e.clip)})"` : ""}/>`);
    }
    out.push(`<g class="w-front" fill="none" stroke="${FRONT_RED}" stroke-width="${f1(2.6 * k)}" stroke-linecap="round" stroke-linejoin="round" opacity=".7" filter="url(#mv-stroke)">${front.join("")}</g>`);
    for (const c of melee) out.push(`<path class="w-melee" data-cell="${esc(c.id)}" d="${c.d}" fill="${FRONT_RED}" fill-opacity=".16" stroke="${FRONT_RED}" stroke-width="${f1(3.2 * k)}" stroke-linejoin="round" clip-path="url(#wc-${esc(c.region)})"/>`);
    for (const c of letters) out.push(`<path class="w-letter" data-cell="${esc(c.id)}" d="${c.d}" fill="none" stroke="${FRONT_RED}" stroke-width="${f1(WORLD_LETTER_LINE * k)}" stroke-dasharray="${f1(WORLD_LETTER_DASH * k)} ${f1(WORLD_LETTER_GAP * k)}" stroke-linejoin="round" clip-path="url(#wc-${esc(c.region)})"/>`);
    return out.join("");
  }
  // 地面要不要畫、照哪一個倍率與週次畫（一樣就不重畫）
  const ground = { key: "" };
  // 畫成點陣（#mk 是一張 canvas）：水暈的濾鏡很重，留成向量的話拖縮的每一幀手機都要重算一次（Joy 2026-10-30「效能有點太差」）；
  // 點陣只在換了疊層、週次、倍率差一大段時重畫一次，拖縮只是移動一張圖
  const GROUND_SCALE = 2; // 點陣是地圖的幾倍大（遠看那一段倍率在 0.72 以下，2 倍夠清楚）
  function groundShow(c) {
    const cv = document.getElementById("mk");
    if (!cv || !S.mapBase || !S.mapState) return;
    const on = S.mapMode === "timeline" || mvLevel(c.z) === 0 || washOn();
    if (cv.style) cv.style.opacity = on ? "1" : "0";
    if (!on || !cv.getContext || typeof Image === "undefined" || !window.URL || !URL.createObjectURL) return;
    const k = Math.min(2, Math.max(0.5, 2 ** Math.round(Math.log2(1 / c.z))));
    const week = mapWeek(), key = `${S.mapBase.key}|${S.mapStateAt}|${week}|${k}`;
    if (ground.key === key) return;
    ground.key = key;
    const b = S.mapBase, W = Math.round(b.w * GROUND_SCALE), H = Math.round(b.h * GROUND_SCALE);
    const url = URL.createObjectURL(new Blob([`<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${b.w} ${b.h}">${groundSvg(b, S.mapState, k, week)}</svg>`], { type: "image/svg+xml" }));
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      if (ground.key !== key) return; // 等的時候又換了
      if (cv.width !== W) { cv.width = W; cv.height = H; }
      const g = cv.getContext("2d");
      g.clearRect(0, 0, W, H);
      g.drawImage(img, 0, 0, W, H);
    };
    img.onerror = () => { URL.revokeObjectURL(url); ground.key = ""; };
    img.src = url;
  }

  // ── 字與小圖（#mkt：照螢幕大小寫，位置照此刻的倍率算）──
  // 每一處各方幾處、寶幾處（遠看那一段大區名底下那一行：照疊層的 sides，只寫不是 0 的）
  function regionCounts(base, st, ctrl) {
    const out = {};
    for (const b of base.places) {
      if (!st.places[b.id] || !b.region) continue;
      const n = out[b.region] || (out[b.region] = { rich: 0 });
      if (ctrl[b.id]) n[ctrl[b.id]] = (n[ctrl[b.id]] || 0) + 1;
      if (st.places[b.id].rich) n.rich += 1;
    }
    return out;
  }
  // 大區名擺哪：天下圖給的第一個位置（底圖的 world.regions[].spots），沒有照大區的中心
  function regionSpots(base, r) {
    const w = base.world && base.world.regions.find((x) => x.id === r.id);
    return w && w.spots && w.spots.length ? w.spots : [[r.cx, r.cy]];
  }
  const REG_NUDGE = [[0, 0], [0, -22], [0, 22], [-30, 0], [30, 0], [-26, -22], [26, -22], [-26, 22], [26, 22]]; // 只挪一小步：字不離開那一州
  // 山河名（底圖的 paint：河名照 labels，山名照地形的 name、直寫在山脊中間旁邊）
  function paintLabels(base) {
    const p = base.paint;
    if (!p) return [];
    const mounts = (p.terrain || []).filter((t) => t.name && t.spine && t.spine.length).map((t) => {
      const m = t.spine[Math.floor(t.spine.length / 2)];
      return { text: t.name, x: m[0] + (t.size || 20) * 1.6, y: m[1], v: true };
    });
    return [...(p.labels || []), ...mounts];
  }
  function pinHtml(b, x, y, dim, z) {
    const k = paintKey(b), at = `left:${f1(x)}px;top:${f1(y)}px`, id = esc(b.id), name = esc(b.name);
    if (k) {
      const w = Math.round(MV_PAINT[k] * (z < MV_LV2 ? 0.8 : 1));
      return `<button type="button" class="mv-pin paint${dim}" style="${at};width:${w}px" data-act="map-place" data-id="${id}" aria-label="${name}"><img src="${mvImg(k)}" width="${w}" alt="" draggable="false"></button>`;
    }
    return `<button type="button" class="mv-pin ink${dim}" style="${at}" data-act="map-place" data-id="${id}" aria-label="${name}"><svg width="30" height="30" viewBox="-15 -17 30 30" aria-hidden="true"><circle r="9" cy="-2" fill="${MAP_HALO}" opacity=".7"/>${inkIcon(b.glyph, MV_INK, "none")}</svg></button>`;
  }
  const mvSeal = (c) => (c ? `<span class="mv-side" style="background:${sideInk(c).color}">${esc(sideInk(c).short)}</span>` : "");
  // 照此刻的倍率排好一整層（純函式：c 是 { z, x, y }，g 是地圖框）。只排畫面附近（一個畫面寬的邊）的；名字撞在一起時優先序：
  // 選的、滑到的、你在的、本週要去的、篩到的、要地、近的。名字的位置試四個（下、右、左、上），都壓到就不寫（選的、你在的照寫）
  // 右下 ◎／全 兩顆圓鈕在地圖框裡佔的那一塊（style.css 的 .mv-fab：46px 兩顆、間隔 10，手機貼著抽屜上緣 12px、桌機在右欄左邊）；
  // 字擺位當它是佔用的（留 6px）。框量不到（測試）不算
  function fabBox(g) {
    if (!g || !g.vw || !g.vh) return null;
    const right = deskMap() ? 372 : 12, bottom = deskMap() ? 16 : mapDrawerPx(S.mapDrawer) + 12, w = 46, h = 46 * 2 + 10, m = 6;
    return [g.vw - right - w - m, g.vh - bottom - h - m, g.vw - right + m, g.vh - bottom + m];
  }
  function marksHtml(base, st, c, g) {
    const z = c.z, tl = S.mapMode === "timeline", lvl = tl ? 0 : mvLevel(z), out = [], boxes = [];
    const week = mapWeek(), ctrl = controlAt(st, week), live = week === st.now_week;
    const sel = S.mapSel, prev = S.mapMode === "overview" ? S.mapPreview : null, wk = nearWeek(st), here = st.journey ? null : st.here;
    const leg = mapLeg(), end = leg && leg.to;
    const filt = (S.mapFilter || "all") !== "all";
    const scr = (x, y) => [c.x + x * z, c.y + y * z];
    const padX = g.vw * 0.8, padY = g.vh * 0.8;
    const near = ([x, y]) => x > -padX && y > -padY && x < g.vw + padX && y < g.vh + padY;
    const shown = base.places.filter((b) => st.places[b.id]);
    const rank = (b) => (b.id === sel || b.id === prev || b.id === end ? 0 : b.id === here ? 1 : wk && wk.id === b.id ? 1.5
      : (mvMatch(st, b) ? 2 : 6) + (b.big ? 0 : 1) + (st.places[b.id].minutes ?? 500) / 1000);
    const order = shown.slice().sort((a, b) => rank(a) - rank(b));
    const hit = (bx) => boxes.some((o) => bx[0] < o[2] && bx[2] > o[0] && bx[1] < o[3] && bx[3] > o[1]);
    for (const b of order) { const [x, y] = scr(b.x, b.y), r = lvl ? 13 : 6; boxes.push([x - r, y - r, x + r, y + r]); }
    const fab = tl ? null : fabBox(g);
    if (fab) boxes.push(fab); // 右下兩顆圓鈕那一塊：名字不擺在底下（全面自檢 U-10）
    // 遠看：大區名＋各方幾處（地面已經照歸屬上色）
    if (lvl === 0) {
      const n = regionCounts(base, st, ctrl), sides = st.sides || sideOrder(base);
      for (const r of base.regions) {
        const cnt = n[r.id] || { rich: 0 };
        const line = [...sides.filter((sd) => cnt[sd]).map((sd) => `${sideInk(sd).short} ${cnt[sd]}`), ...(cnt.rich ? [`${RICH_WORD} ${cnt.rich}`] : [])].join("・");
        const w = Math.max(textW(r.name, 24) * 1.35, line ? textW(line, 13) : 0);
        // 州名＋統計那一塊避開圓點與別州的字（全面自檢 U-11）：伺服器給的幾個擺位、每個再四周挪一挪，挑壓到最少的那一個
        const at = (x, y) => [x - w / 2, y - 14, x + w / 2, y + (line ? 32 : 14)];
        const room = mapRoom(g), off = (bx) => bx[0] < Math.max(4, c.x) || bx[2] > Math.min(g.vw - 4, c.x + base.w * z) || bx[1] < Math.max(room.top + 4, c.y) || bx[3] > Math.min(room.bottom - 4, c.y + base.h * z); // 出了露出來那一塊或出了圖（跑到搜尋列底下、紙外）最不要
        const cover = (bx) => (off(bx) ? 100 : 0) + boxes.reduce((k, o) => k + (bx[0] < o[2] && bx[2] > o[0] && bx[1] < o[3] && bx[3] > o[1] ? 1 : 0), 0);
        let best = null;
        for (const [sx, sy] of regionSpots(base, r)) {
          const [x0, y0] = scr(sx, sy);
          for (const [dx, dy] of REG_NUDGE) {
            const x = x0 + dx, y = y0 - 18 + dy, k = cover(at(x, y));
            if (!best || k < best.k) best = { x, y, k };
            if (!k) break;
          }
          if (!best.k) break;
        }
        const { x, y } = best;
        boxes.push(at(x, y));
        out.push(`<div class="mv-reg" style="left:${f1(x)}px;top:${f1(y)}px">${esc(r.name)}</div>`);
        if (line) out.push(`<div class="mv-cnt" style="left:${f1(x)}px;top:${f1(y + 15)}px">${esc(line)}</div>`);
      }
    } else {
      for (const l of paintLabels(base)) {
        const xy = scr(l.x, l.y);
        if (near(xy)) out.push(`<div class="mv-geo${l.v ? " v" : ""}" style="left:${f1(xy[0])}px;top:${f1(xy[1])}px">${esc(l.text)}</div>`);
      }
    }
    for (const b of order) {
      const q = st.places[b.id], xy = scr(b.x, b.y);
      if (!near(xy)) continue;
      const [x, y] = xy, isHere = b.id === here, isSel = b.id === sel || b.id === prev, isWk = !!wk && wk.id === b.id;
      const on = isSel || isHere || mvMatch(st, b), dim = on ? "" : " dim", ctl = ctrl[b.id] || null;
      if (lvl === 0) {
        out.push(`<button type="button" class="mv-dot${dim}${q.rich ? " rich" : ""}" style="left:${f1(x)}px;top:${f1(y)}px;--c:${ctl ? sideInk(ctl).color : MV_UNHELD}" data-act="map-place" data-id="${esc(b.id)}" aria-label="${esc(b.name)}"></button>`);
      } else out.push(pinHtml(b, x, y, dim, z));
      if (isSel || b.id === end) out.push(`<i class="mv-ring" style="left:${f1(x)}px;top:${f1(y)}px;--r:${lvl ? 22 : 12}px"></i>`);
      if (live && (q.melee || q.siege === "fight")) out.push(`<i class="mv-fight" style="left:${f1(x)}px;top:${f1(y)}px"></i>`);
      if (!on || (lvl === 0 && !isSel && !isHere && !isWk && !filt)) continue;
      const sub = isHere ? MV_WORDS.here : (lvl === 2 || isSel || isWk) ? nearSub(base, st, b.id, wk) : "";
      const odds = !isHere && (lvl === 2 || isSel) && q.odds ? `・<b style="color:${TONE_COLOR[q.odds.tone] || MAP_INK}">${esc(q.odds.word)}</b>` : "";
      const inks = lvl > 1 ? (b.insights || []).map((id) => insightInk(base, id)).filter(Boolean).slice(0, 3) : [];
      const ins = inks.length ? `<span class="ins">${inks.map((k) => `<i style="color:${k.c}">${esc(k.name)}</i>`).join("")}</span>` : "";
      const t = lvl > 0 && live ? tugOf(st, b.id, ctl) : null;
      const bar = t ? `<span class="mv-bar"><i style="width:${t.pct}%;background:${sideInk(t.side).color}"></i></span>` : "";
      const seals = (lvl > 0 && q.rich ? `<span class="mv-rich">${RICH_WORD}</span>` : "")
        + (live && q.siege === "letter" ? `<span class="mv-rich">${LETTER_SEAL_WORD}</span>` : "")
        + (isWk ? `<span class="mv-wk">${MV_WORDS.week}</span>` : "")
        + (leg && b.id === sel ? `<span class="mv-wk leg">${MV_WORDS.next}</span>` : leg && b.id === end ? `<span class="mv-wk leg">${MV_WORDS.end}</span>` : "");
      const fs = b.big ? 16 : 14, side = lvl > 0 && ctl ? 21 : 0;
      const w = side + textW(b.name, fs) + inks.length * 13 + (sub ? 0 : 0) + (lvl > 0 && q.rich ? 21 : 0) + (q.siege === "letter" ? 21 : 0) + (isWk ? 34 : 0) + (leg && (b.id === sel || b.id === end) ? 46 : 0) + 8;
      const wsub = sub ? side + textW(sub, 11) + (odds ? 40 : 0) + 8 : 0;
      const W = Math.max(w, wsub), H = fs * 1.2 + 4 + (sub ? 15 : 0) + (bar ? 5 : 0);
      const tries0 = lvl === 0 ? [[-W / 2, 9], [12, -H / 2], [-12 - W, -H / 2], [-W / 2, -9 - H]] : [[-W / 2, 15], [20, -10], [-20 - W, -10], [-W / 2, -30 - H]];
      // 選了的、終點：寧可擺上面也不擺左邊（貼著地圖左緣時擺左邊會出畫面）；硬擺的那一個是最後一個
      const tries1 = isSel || b.id === end ? [tries0[0], tries0[1], tries0[3], tries0[2]] : tries0;
      // 都擺不下（多半是貼著畫面邊）：下面、上面兩個擺法往畫面裡推一點再試；硬擺的那一個還是最後一個
      const inside = ([dx, dy]) => [Math.min(g.vw - 2 - x - W, Math.max(2 - x, dx)), dy];
      const tries = [...tries1.slice(0, -1), inside(tries0[0]), inside(tries0[3]), tries1[tries1.length - 1]];
      for (const [i, [dx, dy]] of tries.entries()) {
        const bx = [x + dx, y + dy, x + dx + W, y + dy + H];
        // 點在畫面裡的，名字也不擺到畫面外（被切一半看不出是哪裡）；點本來就在畫面外的照舊（拖過去時字已經在那裡）
        const cut = x > 0 && x < g.vw && (bx[0] < 2 || bx[2] > g.vw - 2);
        if ((hit(bx) || cut) && !((isSel || isHere || b.id === end) && i === tries.length - 1)) continue;
        boxes.push(bx);
        out.push(`<button type="button" class="mv-lab${b.big ? " big" : ""}${isHere ? " here" : ""}${isSel ? " sel" : ""}" style="left:${f1(bx[0])}px;top:${f1(bx[1])}px" data-act="map-place" data-id="${esc(b.id)}">`
          + `${lvl > 0 ? mvSeal(ctl) : ""}<span class="t"><span class="nm">${esc(b.name)}${ins}${seals}</span>${sub ? `<small>${esc(sub)}${odds}</small>` : ""}${bar}</span></button>`);
        break;
      }
    }
    // 版圖變化：那一週易手的地點閃一圈
    const row = (st.weeks || []).find((x) => x.week === week);
    if ((tl || !live) && row) for (const e of row.changed || []) {
      const b = placeOf(base, e.id);
      if (b) { const [x, y] = scr(b.x, b.y); out.push(`<i class="mv-pulse" style="left:${f1(x)}px;top:${f1(y)}px"></i>`); }
    }
    // 你：紅點（在路上畫在路上那一點）；選了一處：路線中間掛一顆「幾分」
    const me = youXY(base, st);
    if (me) { const [x, y] = scr(me[0], me[1]); out.push(`<i class="mv-you" style="left:${f1(x)}px;top:${f1(y)}px"></i>`); }
    const tgt = !tl && (sel || prev);
    const tq = tgt && st.places[tgt];
    if (tq && me && tq.path && tq.path.length && tq.minutes) {
      const pts = [me, ...tq.path.map((id) => placeXY(id)).filter(Boolean)], i = Math.floor(pts.length / 2);
      const a = pts[i - 1] || pts[0], bb = pts[i] || pts[0], [x, y] = scr((a[0] + bb[0]) / 2, (a[1] + bb[1]) / 2);
      out.push(`<i class="mv-eta" style="left:${f1(x)}px;top:${f1(y)}px">${Number(tq.minutes)} 分</i>`);
    }
    return out.join("");
  }
  let marksFrame = 0;
  const marksSoon = () => { if (!marksFrame) marksFrame = requestAnimationFrame(drawMarks); };
  // 照此刻的倍率重排字與小圖、地面（loadMap 換了疊層、篩選、選了一處、拖縮停下來、跨了一段倍率都叫這裡）
  function drawMarks() {
    if (marksFrame) { cancelAnimationFrame(marksFrame); marksFrame = 0; }
    const box = document.getElementById("mkt"), g = mapGeom(document.getElementById("map")), c = S.mapCam;
    if (!box || !S.mapBase || !S.mapState || !c || !g) return;
    box.innerHTML = marksHtml(S.mapBase, S.mapState, c, g);
    box.style.transform = "";
    mv.laid = { ...c, vw: g.vw, vh: g.vh };
    groundShow(c);
  }
  // 選了的（或附近那一排滑到的）那一處：從你到那裡的路（朱紅，底下墊一道紙色）。畫在地圖那一層（跟著拖縮，線寬不變）
  function drawRoute() {
    const svg = document.getElementById("mkr"), st = S.mapState;
    if (!svg || !st || !S.mapBase) return;
    const id = S.mapMode === "timeline" ? null : S.mapSel || (S.mapMode === "overview" ? S.mapPreview : null);
    const d = id ? routeD(S.mapBase, st, id) : "";
    const line = (ink, w) => `<path d="${d}" fill="none" stroke="${ink}" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>`;
    const leg = mapLeg(), a = leg && placeXY(leg.from), b = leg && placeXY(leg.to);
    const dash = a && b ? `<path d="M${f1(a[0])},${f1(a[1])}L${f1(b[0])},${f1(b[1])}" fill="none" stroke="${FRONT_RED}" stroke-width="3" stroke-dasharray="2 7" stroke-linecap="round" vector-effect="non-scaling-stroke"/>` : "";
    svg.innerHTML = (d ? line(MAP_HALO, 9) + line(FRONT_RED, 4.5) : "") + dash;
  }

  // ── 看哪裡：S.mapCam = { z 倍率, x, y }，地圖上 (mx, my) 在地圖框裡的 (x + mx·z, y + my·z) ──
  const mv = { pts: new Map(), start: null, moved: false, frame: 0, g: null, anim: 0, vel: [0, 0], last: null, lastTap: 0, eatUntil: 0, wheelTimer: 0, laid: null };
  // 地圖框與它的內緣在畫面上的位置；框還沒有大小回 null
  function mapGeom(wrap) {
    if (!wrap || !wrap.clientWidth || !wrap.clientHeight) return null;
    const r = wrap.getBoundingClientRect();
    return { wrap, vw: wrap.clientWidth, vh: wrap.clientHeight, x0: r.left + wrap.clientLeft, y0: r.top + wrap.clientTop };
  }
  // 露出來的那一塊（上面讓開搜尋列與篩選、底下讓開抽屜；桌機右欄、版圖變化時地圖框本來就在抽屜外）：{ top, bottom }（px）
  function mapRoom(g) {
    const top = S.mapMode === "timeline" ? MV_TL_TOP : MV_TOP;
    const sheet = deskMap() || S.mapMode === "timeline" ? 0 : mapDrawerPx(S.mapDrawer);
    return { top, bottom: Math.max(top + 60, g.vh - sheet) };
  }
  // 整張天下的框：整張底圖（主機畫的那一張畫滿整張；拖到邊不露出圖外，Joy 2026-10-30「滑到邊邊會破圖」）
  const mapBox = (base) => [0, 0, base.w, base.h];
  function zMin(g) {
    const [, , fw, fh] = mapBox(S.mapBase), room = mapRoom(g);
    return Math.min(MV_ZMAX, Math.max(0.05, Math.min((g.vw - 16) / fw, (room.bottom - room.top - 16) / fh)));
  }
  // 夾住：倍率在整張放得下到 MV_ZMAX 之間；圖比畫面大時邊不准拖進畫面（左右貼著框、上下貼著露出來那一塊），比畫面小時置中
  function camClamp(c, g) {
    const [fx, fy, fw, fh] = mapBox(S.mapBase), room = mapRoom(g);
    const z = Math.min(MV_ZMAX, Math.max(zMin(g), c.z)), rh = room.bottom - room.top;
    const L = fw * z <= g.vw ? (g.vw - fw * z) / 2 : Math.min(0, Math.max(g.vw - fw * z, c.x + fx * z));
    const T = fh * z <= rh ? room.top + (rh - fh * z) / 2 : Math.min(room.top, Math.max(room.bottom - fh * z, c.y + fy * z));
    return { z, x: L - fx * z, y: T - fy * z };
  }
  // 整張天下放進露出來的那一塊、置中
  function camFit(g) {
    const [fx, fy, fw, fh] = mapBox(S.mapBase), room = mapRoom(g), z = zMin(g);
    return { z, x: (g.vw - fw * z) / 2 - fx * z, y: room.top + (room.bottom - room.top - fh * z) / 2 - fy * z };
  }
  // 地圖上 (mx, my) 放在露出來那一塊的正中、倍率 z
  function camAt(g, mx, my, z) {
    const room = mapRoom(g);
    return camClamp({ z, x: g.vw / 2 - mx * z, y: (room.top + room.bottom) / 2 - my * z }, g);
  }
  // 套上：底圖那一層照新的倍率與位置；字那一層照上一次排字的倍率先跟著縮放（同一個仿射），差過一截、跨了一段、拖出一個畫面才重排
  function camSet(c, g = mv.g || mapGeom(document.getElementById("map"))) {
    if (!g || !S.mapBase || !c) return;
    const q = camClamp(c, g);
    S.mapCam = q;
    const w = document.getElementById("mvw");
    if (w) w.style.transform = `translate(${f2(q.x)}px, ${f2(q.y)}px) scale(${q.z})`;
    const m = document.getElementById("mkt"), L = mv.laid;
    if (!m || !L) return;
    const r = q.z / L.z, dx = q.x - L.x * r, dy = q.y - L.y * r;
    m.style.transform = Math.abs(r - 1) < 1e-4 && Math.abs(dx) < 0.01 && Math.abs(dy) < 0.01 ? "" : `translate(${f2(dx)}px, ${f2(dy)}px) scale(${r})`;
    if (Math.abs(Math.log(r)) > MV_RELAYOUT || mvLevel(q.z) !== mvLevel(L.z) || Math.abs(dx) > g.vw * 0.6 || Math.abs(dy) > g.vh * 0.6) marksSoon();
  }
  function mvStop() {
    if (mv.anim) { cancelAnimationFrame(mv.anim); mv.anim = 0; }
  }
  // 飛過去：遠的先拉遠一點再拉近（像從天上掠過去）；地圖上的中心點線性移、倍率照拋物線。飛完重排字
  function camFly(t, dur = MV_FLY) {
    mvStop();
    const g = mapGeom(document.getElementById("map"));
    if (!g || !S.mapCam) { if (g) { camSet(t, g); drawMarks(); } return; }
    mv.g = null;
    const s = { ...S.mapCam }, room = mapRoom(g), cy = (room.top + room.bottom) / 2;
    t = camClamp(t, g);
    const far = Math.hypot((t.x - s.x) / s.z, (t.y - s.y) / s.z) > 400 / Math.min(s.z, t.z);
    const dip = far ? Math.max(zMin(g), Math.min(s.z, t.z) * 0.6) : null;
    if (far) dur = MV_FLY_FAR;
    if (reduceMotion() || typeof requestAnimationFrame !== "function") { camSet(t, g); drawMarks(); return; }
    const cx0 = (g.vw / 2 - s.x) / s.z, cy0 = (cy - s.y) / s.z, cx1 = (g.vw / 2 - t.x) / t.z, cy1 = (cy - t.y) / t.z, t0 = performance.now();
    const step = (now) => {
      const k = Math.min(1, (now - t0) / dur), e = k < 0.5 ? 4 * k * k * k : 1 - (-2 * k + 2) ** 3 / 2;
      let zz = s.z + (t.z - s.z) * e;
      if (dip) zz = Math.min(zz, dip + (Math.max(s.z, t.z) - dip) * (2 * e - 1) ** 2);
      const mx = cx0 + (cx1 - cx0) * e, my = cy0 + (cy1 - cy0) * e;
      camSet({ z: zz, x: g.vw / 2 - mx * zz, y: cy - my * zz }, g);
      if (k < 1) mv.anim = requestAnimationFrame(step);
      else { mv.anim = 0; drawMarks(); }
    };
    mv.anim = requestAnimationFrame(step);
  }
  function mapFlyTo(p, z) {
    const g = mapGeom(document.getElementById("map"));
    if (g && p) camFly(camAt(g, p[0], p[1], Math.min(MV_ZMAX, z)));
  }
  // 以地圖框裡 (px, py) 為中心縮放到 nz
  function zoomAt(nz, px, py, glide = false) {
    const g = mapGeom(document.getElementById("map")), c = S.mapCam;
    if (!g || !c) return;
    nz = Math.min(MV_ZMAX, Math.max(zMin(g), nz));
    const t = { z: nz, x: px - ((px - c.x) / c.z) * nz, y: py - ((py - c.y) / c.z) * nz };
    if (glide) camFly(t);
    else camSet(t, g);
  }
  // 右下兩顆：回到我（以你為中心，至少放到 MV_HOME_Z）、看整張天下
  function mapHome() {
    const me = S.mapBase && S.mapState && youXY(S.mapBase, S.mapState);
    if (me) mapFlyTo(me, Math.max(S.mapCam ? S.mapCam.z : 0, MV_HOME_Z));
  }
  function mapFit() {
    const g = mapGeom(document.getElementById("map"));
    if (g) camFly(camFit(g));
  }
  // 找地點那一頁的「跳到大區」：那一區的地點整個放進來（最多兩倍）
  function mapRegionFly(rid) {
    const g = mapGeom(document.getElementById("map")), pts = S.mapBase ? S.mapBase.places.filter((p) => p.region === rid) : [];
    if (!g || !pts.length) return;
    const xs = pts.map((p) => p.x), ys = pts.map((p) => p.y), room = mapRoom(g);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    const z = Math.min(2, (g.vw - 120) / Math.max(1, x1 - x0), (room.bottom - room.top - 90) / Math.max(1, y1 - y0));
    camFly(camAt(g, (x0 + x1) / 2, (y0 + y1) / 2, z));
  }
  // 點了的那一處要露在抽屜上面、搜尋列底下：露著就不動，不然滑過去（倍率不變）
  function mvNudge(id) {
    const g = mapGeom(document.getElementById("map")), p = placeXY(id), c = S.mapCam;
    if (!g || !p || !c) return;
    const room = mapRoom(g), x = c.x + p[0] * c.z, y = c.y + p[1] * c.z;
    if (x > 30 && x < g.vw - 30 && y > room.top + 30 && y < room.bottom - 40) return;
    camFly(camAt(g, p[0], p[1], c.z));
  }

  // ── 點一處、收回 ──
  // 點了一處（地圖上的小圖或名字、附近那一排的卡、找地點的結果、今天去哪裡出陣）：抽屜開那一處的卡、畫路線；fly：飛過去（找地點、出陣建議），
  // 不然只在被擋住時挪一下。版圖變化時：年表上圈起來（同 map-mark）
  function mapPick(id, fly = false) {
    const st = S.mapState;
    if (!id || !st || !st.places[id]) return;
    if (S.mapMode === "timeline") {
      S.mapSel = S.mapSel === id ? null : id;
      redrawDrawer();
      drawMarks();
      return;
    }
    const wasFind = S.mapMode === "search";
    Object.assign(S, { mapSel: id, mapMode: "place", mapPreview: null, mapQuery: "", mapDrawer: "peek" });
    if (wasFind) remapChrome();
    else { redrawDrawer(); setMapDrawer("peek"); }
    drawRoute();
    const p = placeXY(id);
    if (fly && p) mapFlyTo(p, Math.max(S.mapCam ? S.mapCam.z : 0, MV_PICK_Z));
    else { drawMarks(); mvNudge(id); }
  }
  // 收回（卡上的 ✕、找地點的 ←、點地圖的空白）：回附近那一排
  function mapBack() {
    const wasFind = S.mapMode === "search";
    Object.assign(S, { mapMode: "overview", mapSel: null, mapPreview: null, mapQuery: "", mapDrawer: "peek" });
    if (wasFind) remapChrome();
    else { redrawDrawer(); setMapDrawer("peek"); }
    drawRoute();
    drawMarks();
  }
  // 找地點：整頁一張清單，蓋在地圖上
  function mapFind() {
    Object.assign(S, { mapMode: "search", mapQuery: "" });
    remapChrome();
    setTimeout(() => { const q = document.getElementById("map-q"); if (q) q.focus(); }, 60);
  }
  function mapBlank() {
    if (S.mapMode === "place" || (S.mapMode === "overview" && S.mapPreview)) mapBack();
    else if (S.mapMode === "timeline" && S.mapSel) { S.mapSel = null; redrawDrawer(); drawMarks(); }
  }

  // ── 底圖：照底圖的 paint（content/map.json）畫成淡彩水墨——紙紋、赭黃暈染、毛筆畫的河（一道淡青的暈＋一筆濃淡的墨線）、州界墨點線、
  // 細赭墨的路、一座一座蓋上去的山（web/img/map 的 m2～m6，照山脊從後往前、大小錯落）、墨綠點的林、四角暗一點——烤成一張圖
  // （Joy 2026-10-18「輿圖滑動的時候還是很卡」：拖縮時只動這張圖）。同一張底圖整層重畫時不必再烤 ──
  function mvRand(seed) { let s = seed; return () => (s = (s * 16807) % 2147483647) / 2147483647; }
  // Catmull-Rom → 貝茲（河、州界畫成順的曲線）
  function smoothD(pts) {
    let d = `M${pts[0][0]},${pts[0][1]}`;
    for (let i = 0; i < pts.length - 1; i++) {
      const p0 = pts[i - 1] || pts[i], p1 = pts[i], p2 = pts[i + 1], p3 = pts[i + 2] || p2;
      d += ` C${f1(p1[0] + (p2[0] - p0[0]) / 6)},${f1(p1[1] + (p2[1] - p0[1]) / 6)} ${f1(p2[0] - (p3[0] - p1[0]) / 6)},${f1(p2[1] - (p3[1] - p1[1]) / 6)} ${p2[0]},${p2[1]}`;
    }
    return d;
  }
  // 州界（墨點線）與路（二次曲線）的 path；extra 是每一條 path 多掛的屬性
  function lineworkSvg(base, extra = "") {
    const pos = Object.fromEntries(base.places.map((p) => [p.id, p]));
    const borders = `<g fill="none" stroke="#5E4E3A" stroke-width="1.2" stroke-dasharray="1 7" stroke-linecap="round" opacity=".55">${((base.paint && base.paint.regions) || []).map((r) => `<path d="${smoothD([...r.points, r.points[0]])}"${extra}/>`).join("")}</g>`;
    const roads = `<g fill="none" stroke="#7B6247" stroke-width="1.1" stroke-linecap="round" opacity=".7">${(base.roads || []).map(([a, b, cx, cy]) => (pos[a] && pos[b] ? `<path d="M${pos[a].x},${pos[a].y} Q${cx},${cy} ${pos[b].x},${pos[b].y}"${extra}/>` : "")).join("")}</g>`;
    return borders + roads;
  }
  function paintSvg(base, mounts, PW, PH) {
    const M = base.paint, R = mvRand(7), W = base.w, H = base.h, out = [];
    const pos = Object.fromEntries(base.places.map((p) => [p.id, p]));
    const borders = `<g fill="none" stroke="#5E4E3A" stroke-width="1.2" stroke-dasharray="1 7" stroke-linecap="round" opacity=".55">${(M.regions || []).map((r) => `<path d="${smoothD([...r.points, r.points[0]])}"/>`).join("")}</g>`;
    const roads = (o) => `<g fill="none" stroke="#7B6247" stroke-width="1.1" stroke-linecap="round" opacity="${o}" filter="url(#brush)">${(base.roads || []).map(([a, b, cx, cy]) => (pos[a] && pos[b] ? `<path d="M${pos[a].x},${pos[a].y} Q${cx},${cy} ${pos[b].x},${pos[b].y}"/>` : "")).join("")}</g>`;
    out.push(`<svg xmlns="http://www.w3.org/2000/svg" width="${PW}" height="${PH}" viewBox="0 0 ${W} ${H}"><defs>`
      + '<filter id="grain" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency=".9" numOctaves="2" seed="3"/><feColorMatrix values="0 0 0 0 .45  0 0 0 0 .36  0 0 0 0 .25  0 0 0 .09 0"/></filter>'
      + '<filter id="fiber" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency=".012 .2" numOctaves="2" seed="9"/><feColorMatrix values="0 0 0 0 .5  0 0 0 0 .42  0 0 0 0 .3  0 0 0 .06 0"/></filter>'
      + '<filter id="bleed" x="-20%" y="-20%" width="140%" height="140%"><feTurbulence type="fractalNoise" baseFrequency=".035" numOctaves="3" seed="5"/><feDisplacementMap in="SourceGraphic" scale="26"/><feGaussianBlur stdDeviation="7"/></filter>'
      + '<filter id="edge" x="-20%" y="-20%" width="140%" height="140%"><feTurbulence type="fractalNoise" baseFrequency=".05" numOctaves="2" seed="11"/><feDisplacementMap in="SourceGraphic" scale="14"/><feGaussianBlur stdDeviation="2.2"/></filter>'
      + '<filter id="brush" x="-5%" y="-5%" width="110%" height="110%"><feTurbulence type="fractalNoise" baseFrequency=".25" numOctaves="2" seed="2"/><feDisplacementMap in="SourceGraphic" scale="2.4"/></filter>'
      + '<radialGradient id="vig" cx=".5" cy=".5" r=".72"><stop offset=".6" stop-color="#6B5236" stop-opacity="0"/><stop offset="1" stop-color="#6B5236" stop-opacity=".28"/></radialGradient></defs>');
    out.push(`<rect width="${W}" height="${H}" fill="#F1E8D6"/>`);
    out.push('<g filter="url(#bleed)" opacity=".55">');
    for (const r of M.regions || []) {
      const n = r.points.length, c = r.points.reduce((a, p) => [a[0] + p[0] / n, a[1] + p[1] / n], [0, 0]);
      out.push(`<ellipse cx="${f1(c[0])}" cy="${f1(c[1])}" rx="${f1(140 + R() * 60)}" ry="${f1(90 + R() * 50)}" fill="#E7C996"/>`);
      out.push(`<ellipse cx="${f1(c[0] + (R() - 0.5) * 120)}" cy="${f1(c[1] + (R() - 0.5) * 90)}" rx="${f1(60 + R() * 40)}" ry="${f1(40 + R() * 30)}" fill="#E6AE92" opacity=".5"/>`);
    }
    out.push("</g>");
    for (const f of (M.terrain || []).filter((t) => t.kind === "forest" && t.points && t.points.length)) {
      const xs = f.points.map((p) => p[0]), ys = f.points.map((p) => p[1]);
      const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
      out.push('<g opacity=".55">');
      for (let i = 0; i < 26; i++) {
        const x = x0 + R() * (x1 - x0), y = y0 + R() * (y1 - y0), r = 3 + R() * 4;
        out.push(`<ellipse cx="${f1(x)}" cy="${f1(y)}" rx="${f1(r)}" ry="${f1(r * 0.8)}" fill="#6E8466" opacity="${f2(0.35 + R() * 0.4)}"/><path d="M${f1(x)},${f1(y + r)} v${f1(r * 0.9)}" stroke="#3E4A38" stroke-width=".8"/>`);
      }
      out.push("</g>");
    }
    for (const r of M.rivers || []) {
      if (!r.points || r.points.length < 2) continue;
      const d = smoothD(r.points), yel = r.color === "yellow", w = r.width || [4, 8];
      out.push(`<path d="${d}" fill="none" stroke="${yel ? "#D8B47A" : "#A9C0CF"}" stroke-width="${f1(w[1] * 1.6)}" stroke-linecap="round" opacity=".55" filter="url(#edge)"/>`);
      out.push(`<path d="${d}" fill="none" stroke="#3B3530" stroke-width="${yel ? 2.4 : 1.5}" stroke-linecap="round" opacity=".85" filter="url(#brush)"/>`);
      out.push(`<path d="${d}" fill="none" stroke="#3B3530" stroke-width=".7" stroke-linecap="round" opacity=".5" transform="translate(${f1(w[0] * 0.5)},${f1(w[0] * 0.4)})" filter="url(#brush)"/>`);
    }
    out.push(borders, roads(".6"));
    const stamps = [];
    for (const t of (M.terrain || []).filter((x) => x.kind !== "forest" && x.spine && x.spine.length > 1)) {
      const hills = t.kind === "hills", sp = t.spine, size = t.size || 20;
      for (let i = 0; i < sp.length - 1; i++) {
        const [ax, ay] = sp[i], [bx, by] = sp[i + 1], L = Math.hypot(bx - ax, by - ay), n = Math.max(2, Math.round(L / (size * 1.15)));
        for (let j = 0; j < n; j++) {
          const f = (j + R() * 0.6) / n, w = size * (hills ? 2.2 : 3.1) * (0.75 + R() * 0.5);
          stamps.push([ax + (bx - ax) * f + (R() - 0.5) * size * 0.8, ay + (by - ay) * f + (R() - 0.5) * size * 0.6, w, MV_MOUNTS[Math.floor(R() * MV_MOUNTS.length)], hills ? 0.6 : 0.95]);
        }
      }
    }
    stamps.sort((a, b) => a[1] - b[1]);
    for (const [x, y, w, k, o] of stamps) {
      const im = mounts[k];
      if (im) out.push(`<image href="${im.url}" x="${f1(x - w / 2)}" y="${f1(y - w * im.r / 2)}" width="${f1(w)}" height="${f1(w * im.r)}" opacity="${o}"/>`);
    }
    out.push(`<rect width="${W}" height="${H}" filter="url(#fiber)"/><rect width="${W}" height="${H}" filter="url(#grain)"/><rect width="${W}" height="${H}" fill="url(#vig)"/></svg>`);
    return out.join("");
  }
  // 主機畫的底圖（design/輿圖底圖，2026-10-30；照 content/map.json 的山河位置畫、900×1340 的三倍）：直接當一張圖鋪著，
  // 州界與路是一張很輕的向量（線寬照螢幕）疊在上面；抓不到才照內容自己畫、烤成一張
  const MV_ART = "/static/img/map/base.webp";
  async function dataUrl(path) {
    const blob = await (await fetch(path)).blob();
    return new Promise((ok, no) => { const fr = new FileReader(); fr.onload = () => ok(fr.result); fr.onerror = no; fr.readAsDataURL(blob); });
  }
  // 山的小圖（照 data: 塞進底圖：烤的時候 SVG 當圖片畫，外連的圖不會載）與高寬比；一次載入只抓一次
  let mountMemo = null;
  function mountImgs() {
    if (!mountMemo) {
      mountMemo = Promise.all(MV_MOUNTS.map(async (k) => {
        const url = await dataUrl(mvImg(k));
        const im = new Image();
        im.src = url;
        await im.decode();
        return [k, { url, r: im.height / im.width }];
      })).then(Object.fromEntries).catch((e) => { mountMemo = null; throw e; });
    }
    return mountMemo;
  }
  const BAKE_PX = 5e6; // 烤成的圖最多幾個像素（約 2 倍）
  const baked = { key: null, url: null };
  let bakeTimer = 0;
  function bakeLater() {
    clearTimeout(bakeTimer);
    bakeTimer = setTimeout(bakeBase, 60);
  }
  // 烤好的圖記在這個瀏覽器（Cache Storage，照底圖的 key）：下一次打開輿圖不必再烤（烤一次在手機上要一兩秒）。記不住、讀不到照烤
  const BAKE_CACHE = "tx-map-bake", BAKE_VER = 1;
  const bakeReq = (key) => `/__map-bake/${BAKE_VER}/${encodeURIComponent(key)}`;
  async function bakeCached(key) {
    try {
      if (!window.caches) return null;
      const hit = await (await caches.open(BAKE_CACHE)).match(bakeReq(key));
      return hit ? URL.createObjectURL(await hit.blob()) : null;
    } catch (e) { return null; }
  }
  async function bakeKeep(key, blob) {
    try {
      if (!window.caches) return;
      const box = await caches.open(BAKE_CACHE);
      for (const r of await box.keys()) await box.delete(r); // 只留這一張（劇情開了新地點換一張）
      await box.put(bakeReq(key), new Response(blob, { headers: { "Content-Type": "image/jpeg" } }));
    } catch (e) { /* 記不住就下次再烤 */ }
  }
  async function bakeBase() {
    const base = S.mapBase, w0 = document.getElementById("mvw");
    if (!base || !base.paint || !w0 || w0.querySelector(".mv-base") || typeof Image === "undefined" || typeof Blob === "undefined" || !window.URL || !URL.createObjectURL) return;
    const key = base.key;
    try {
      const art = new Image();
      art.src = MV_ART;
      const ok = await art.decode().then(() => true, () => false);
      if (ok) {
        const w = document.getElementById("mvw");
        if (!w || !w.isConnected || (S.mapBase && S.mapBase.key) !== key || w.querySelector(".mv-base")) return;
        Object.assign(art, { className: "mv-base", alt: "", draggable: false });
        art.width = base.w; art.height = base.h;
        w.insertAdjacentHTML("afterbegin", `<svg class="mv-lines" width="${base.w}" height="${base.h}" viewBox="0 0 ${base.w} ${base.h}" aria-hidden="true">${lineworkSvg(base, ' vector-effect="non-scaling-stroke"')}</svg>`);
        w.prepend(art);
        requestAnimationFrame(() => art.classList.add("on"));
        return;
      }
      let url = baked.key === key ? baked.url : null;
      if (!url) url = await bakeCached(key);
      if (!url) {
        const mounts = await mountImgs();
        const f = Math.max(1, Math.min(2, Math.sqrt(BAKE_PX / (base.w * base.h))));
        const PW = Math.round(base.w * f), PH = Math.round(base.h * f);
        const vec = URL.createObjectURL(new Blob([paintSvg(base, mounts, PW, PH)], { type: "image/svg+xml" }));
        const img = new Image();
        img.src = vec;
        await img.decode();
        try {
          const cv = document.createElement("canvas");
          cv.width = PW; cv.height = PH;
          cv.getContext("2d").drawImage(img, 0, 0, PW, PH);
          const blob = await new Promise((ok) => cv.toBlob(ok, "image/jpeg", 0.9));
          cv.width = cv.height = 0;
          if (!blob) throw new Error("toBlob");
          url = URL.createObjectURL(blob);
          bakeKeep(key, blob);
          URL.revokeObjectURL(vec);
        } catch (e) {
          url = vec; // 畫不進畫布（舊瀏覽器）：直接用那一張 SVG
        }
        if (baked.url && baked.key !== key) URL.revokeObjectURL(baked.url);
        Object.assign(baked, { key, url });
      }
      const pic = new Image();
      pic.src = url;
      await pic.decode().catch(() => {});
      // 等的時候底圖可能換掉了（劇情開了新地點、登出）
      const w = document.getElementById("mvw");
      if (!w || !w.isConnected || (S.mapBase && S.mapBase.key) !== key || w.querySelector(".mv-base")) return;
      Object.assign(pic, { className: "mv-base", alt: "", draggable: false });
      pic.width = base.w; pic.height = base.h;
      w.prepend(pic);
      requestAnimationFrame(() => pic.classList.add("on"));
    } catch (e) {
      /* 畫不出來（記憶體不夠、圖抓不到）：照舊是一張紙色 */
    }
  }

  // ── 手勢：一指拖（放手會順著滑）、兩指捏、滾輪（觸控板捏合同）、雙擊放大；按下之後不到 MV_SLOP 放開是點一下（點地點照舊由 click 開卡，
  // 點空白收回），拖過、捏過放開的那一下 click 吃掉。拖的指標動了才抓住（按下就抓的話，Chrome 會把 click 送到抓住的地圖框）──
  function mvBase() {
    const a = [...mv.pts.values()];
    mv.start = {
      mx: a.reduce((s, p) => s + p[0], 0) / a.length, my: a.reduce((s, p) => s + p[1], 0) / a.length, cam: { ...S.mapCam },
      d: a.length > 1 ? Math.max(1, Math.hypot(a[1][0] - a[0][0], a[1][1] - a[0][1])) : 1,
    };
  }
  function mvBegin() {
    mv.moved = true;
    const g = mv.g;
    if (!g) return;
    for (const id of mv.pts.keys()) { try { g.wrap.setPointerCapture(id); } catch (e) { /* 合成的事件、已經放開的指標抓不住 */ } }
  }
  function mvFrame() {
    mv.frame = 0;
    const a = [...mv.pts.values()], s = mv.start, g = mv.g;
    if (!s || !g || !mv.moved) return;
    if (a.length === 1) camSet({ z: s.cam.z, x: s.cam.x + a[0][0] - s.mx, y: s.cam.y + a[0][1] - s.my }, g);
    else if (a.length >= 2) {
      const mx = (a[0][0] + a[1][0]) / 2, my = (a[0][1] + a[1][1]) / 2, d = Math.hypot(a[1][0] - a[0][0], a[1][1] - a[0][1]);
      const wx = (s.mx - g.x0 - s.cam.x) / s.cam.z, wy = (s.my - g.y0 - s.cam.y) / s.cam.z;
      const z = Math.min(MV_ZMAX, Math.max(zMin(g), (s.cam.z * d) / s.d));
      camSet({ z, x: mx - g.x0 - wx * z, y: my - g.y0 - wy * z }, g);
    }
  }
  const mvSoon = () => { if (!mv.frame) mv.frame = requestAnimationFrame(mvFrame); };
  function mvDown(ev) {
    if ((ev.pointerType === "mouse" && ev.button !== 0) || !S.mapBase || !S.mapCam) return;
    if (mv.pts.has(ev.pointerId)) mv.pts.clear(); // 同一個指標又按下：上一次沒收到放開（在視窗外放開），重新來過
    if (mv.pts.size >= 2) return;
    mv.eatUntil = 0;
    mvStop();
    if (!mv.pts.size) { mv.moved = false; mv.g = mapGeom(document.getElementById("map")); mv.vel = [0, 0]; }
    mv.pts.set(ev.pointerId, [ev.clientX, ev.clientY]);
    mv.last = [ev.clientX, ev.clientY, performance.now()];
    mvBase();
    if (mv.pts.size === 2) mvBegin(); // 第二指按下就是捏合：不再算點一下
  }
  function mvMove(ev) {
    if (!mv.pts.has(ev.pointerId)) return;
    mv.pts.set(ev.pointerId, [ev.clientX, ev.clientY]);
    if (!mv.moved) {
      if (Math.hypot(ev.clientX - mv.start.mx, ev.clientY - mv.start.my) <= MV_SLOP) return; // 還不到：可能是點一下
      mvBegin();
    }
    if (mv.pts.size === 1 && mv.last) {
      const now = performance.now(), dt = Math.max(1, now - mv.last[2]);
      mv.vel = [0.8 * (ev.clientX - mv.last[0]) / dt + 0.2 * mv.vel[0], 0.8 * (ev.clientY - mv.last[1]) / dt + 0.2 * mv.vel[1]];
      mv.last = [ev.clientX, ev.clientY, now];
    }
    mvSoon();
  }
  // 放手之後順著滑一段、慢慢停
  function mvCoast() {
    let v = mv.vel.map((x) => x * 16), last = performance.now();
    const g = mv.g;
    const step = (now) => {
      const k = Math.min(3, (now - last) / 16);
      last = now;
      const c = S.mapCam;
      camSet({ z: c.z, x: c.x + v[0] * k, y: c.y + v[1] * k }, g);
      v = v.map((x) => x * MV_FRICTION ** k);
      if (Math.hypot(...v) > 0.3) mv.anim = requestAnimationFrame(step);
      else { mv.anim = 0; mv.g = null; drawMarks(); }
    };
    mv.anim = requestAnimationFrame(step);
  }
  function mvUp(ev) {
    if (!mv.pts.has(ev.pointerId)) return;
    if (mv.frame) { cancelAnimationFrame(mv.frame); mvFrame(); }
    mv.pts.delete(ev.pointerId);
    if (mv.pts.size) { mvBase(); mv.vel = [0, 0]; mv.last = null; return; } // 雙指放開一指：剩下那一指接著拖
    if (mv.moved) {
      if (ev.type === "pointerup") mv.eatUntil = Date.now() + MV_CLICK;
      if (mv.last && performance.now() - mv.last[2] < 80 && Math.hypot(...mv.vel) > MV_COAST && !reduceMotion()) { mvCoast(); return; }
      mv.g = null;
      drawMarks();
      return;
    }
    mv.g = null;
    if (ev.type !== "pointerup" || (ev.target && ev.target.closest && ev.target.closest("[data-act]"))) return; // 點到地點：click 開卡
    const now = Date.now(), g = mapGeom(document.getElementById("map"));
    if (g && now - mv.lastTap < MV_TAP2) { mv.lastTap = 0; zoomAt(S.mapCam.z * 2, ev.clientX - g.x0, ev.clientY - g.y0, true); return; }
    mv.lastTap = now;
    mapBlank();
  }
  function mvWheel(ev) {
    if (ev.preventDefault) ev.preventDefault();
    if (mv.pts.size || !S.mapCam) return;
    mvStop();
    const g = mv.g || (mv.g = mapGeom(document.getElementById("map")));
    if (!g) return;
    const dy = ev.deltaY * (ev.deltaMode === 1 ? 16 : ev.deltaMode === 2 ? g.vh : 1);
    zoomAt(S.mapCam.z * Math.exp(-dy * MV_WHEEL), ev.clientX - g.x0, ev.clientY - g.y0);
    clearTimeout(mv.wheelTimer);
    mv.wheelTimer = setTimeout(() => { mv.g = null; drawMarks(); }, 160);
  }
  // 拖過、捏過放開的那一下 click（捕獲階段、在 document 分派之前）吃掉：不誤開卡
  function mvEat(ev) {
    if (!mv.eatUntil) return;
    const late = Date.now() > mv.eatUntil;
    mv.eatUntil = 0;
    if (late) return;
    ev.stopPropagation();
    if (ev.preventDefault) ev.preventDefault();
  }
  // 地圖框的監聽：掛一次（地圖框常駐 FB-324；底圖換了整層重畫才是新的框）
  const mvWired = new WeakSet();
  function mvWire(wrap) {
    if (!wrap || !wrap.addEventListener || mvWired.has(wrap)) return;
    mvWired.add(wrap);
    wrap.addEventListener("pointerdown", mvDown);
    wrap.addEventListener("pointermove", mvMove);
    wrap.addEventListener("pointerup", mvUp);
    wrap.addEventListener("pointercancel", mvUp);
    wrap.addEventListener("wheel", mvWheel, { passive: false });
    wrap.addEventListener("click", mvEat, true);
    // 舊版 iOS Safari 的捏合（新的瀏覽器由 touch-action: none 擋）、拖到地圖上的字開始原生拖曳，都擋掉
    for (const t of ["gesturestart", "gesturechange", "dragstart"]) wrap.addEventListener(t, (ev) => ev.preventDefault());
  }

  // ── 打開、換外圍 ──
  // 第一次（每一次打開輿圖）看哪裡：選了一處以它為中心、放到 MV_PICK_Z；不然以你為中心、MV_OPEN_Z
  function camFirst(g) {
    const st = S.mapState, base = S.mapBase;
    // 選了一處：連另一頭（護糧的終點，不然是你）一起框進露出來的那一塊（留邊給字），最多放到 MV_PICK_Z；
    // 兩頭太遠、框進來字就看不到了（拉遠到只剩大區）才只看選了的那一處
    const leg = mapLeg(), a = S.mapSel && placeXY(S.mapSel), b = leg ? placeXY(leg.to) : st && !st.journey && youXY(base, st);
    if (a && b) {
      const room = mapRoom(g), w = Math.abs(a[0] - b[0]) + 320, h = Math.abs(a[1] - b[1]) + 160;
      const z = Math.min(MV_PICK_Z, (g.vw - 16) / w, (room.bottom - room.top - 16) / h);
      if (z >= MV_LV1) return camAt(g, (a[0] + b[0]) / 2, (a[1] + b[1]) / 2, z);
    }
    const p = (S.mapSel && placeXY(S.mapSel)) || (st && youXY(base, st));
    return p ? camAt(g, p[0], p[1], S.mapSel ? MV_PICK_Z : MV_OPEN_Z) : camFit(g);
  }
  // 視窗換了大小、地圖框換了高（狀態列變高變矮，FB-710）：照新的框重夾、重排
  function applyMapView() {
    const g = mapGeom(document.getElementById("map"));
    if (!g || !S.mapBase) return;
    camSet(S.mapCam || camFirst(g), g);
    drawMarks();
  }
  // 換外圍（找地點開關、版圖變化開關）：外圍的鈕與抽屜整個換掉（同 showMapHost 的做法），地圖本身留著
  function remapChrome() {
    const box = document.getElementById("mapx");
    if (!box) return;
    box.className = mapxClass();
    for (const el of [...box.children]) if (el.id !== "map") el.remove();
    box.insertAdjacentHTML("beforeend", mapChrome());
    drawerGrab();
    cardsWire();
    setMapDrawer(S.mapDrawer);
  }
  // 每一次打開輿圖（goTab）：以你為中心、附近那一排。江湖頁的小地圖點了某一處、別區那一張的「前往」：以那一處為中心、開它的卡
  // then：有起終點的（護糧）那一件的終點——兩點都框進畫面，選了的那一處標「下一站」、終點標「終點」（Joy 2026-10-31）
  function mapFirst(sel = null, then = null) {
    mvStop();
    Object.assign(S, { mapMode: sel ? "place" : "overview", mapSel: sel, mapPreview: null, mapDrawer: "peek", mapWeek: null, mapQuery: "", mapCam: null,
      mapThen: sel && then && then !== sel ? { from: sel, to: then } : null });
  }
  // 江湖頁「去輿圖」「去宛城」那幾顆（Joy 2026-10-31「應該直接點到目標地點，讓玩家不用在地圖還要一直找」）：輿圖開在那一處、抽屜開它的卡、畫出路
  function mapGoto(loc, then = null) {
    mapFirst(loc || null, then);
    S.mapKeep = !!loc;
  }
  // 「下一站→終點」那一段：只在還選著那一處的時候算數（點了別處、回附近那一排就不畫）
  const mapLeg = () => (S.mapThen && S.mapMode === "place" && S.mapSel === S.mapThen.from ? S.mapThen : null);
  // 輿圖頁每次畫好（afterPage）：量框、抽屜、看哪裡、字、路線、底圖、手勢
  function mapReady() {
    const wrap = document.getElementById("map");
    if (!wrap) return;
    mapFrame();
    if (!drawerStops().includes(S.mapDrawer)) S.mapDrawer = drawerStops()[0];
    setMapDrawer(S.mapDrawer);
    const g = mapGeom(wrap);
    if (g && S.mapBase) camSet(S.mapCam || camFirst(g), g);
    drawMarks();
    drawRoute();
    bakeLater();
    drawerGrab();
    cardsWire();
    mvWire(wrap);
  }
