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
  // 外面浮著區名與 🔍、小地圖、箭頭牌（輿圖表現第二版 W2）、右下兩顆圓鈕、底下一張抽屜（寬 900 以上是右欄）。data-key 是底圖的 key：輿圖那一層常駐在 #map-host 時
  // （showMapHost），同一張底圖只換外圍、地圖那一塊原地留著（FB-324）
  function pageMap() {
    if (!S.mapBase || !S.mapState) return '<p class="muted">展開輿圖…</p>';
    const b = S.mapBase;
    return `<div class="${mapxClass()}" id="mapx" data-key="${esc(b.key)}">
      <div class="map-wrap" id="map"><div class="mv-world" id="mvw" style="width:${Number(b.w)}px;height:${Number(b.h)}px">`
      + `<svg class="mv-ground" id="mk" width="${Number(b.w)}" height="${Number(b.h)}" viewBox="0 0 ${Number(b.w)} ${Number(b.h)}" aria-hidden="true"></svg>`
      + `<svg class="mv-route" id="mkr" width="${Number(b.w)}" height="${Number(b.h)}" viewBox="0 0 ${Number(b.w)} ${Number(b.h)}"></svg></div>`
      + `<div class="mv-marks" id="mkt"></div></div>${mapChrome()}
    </div>`;
  }
  function mapxClass() { return `mapx${S.mapMode === "timeline" ? " tl-mode" : ""}${S.mapMode === "search" ? " find-mode" : ""}`; }
  // 地圖框以外的那幾樣：上面的區名 chip 與 🔍、右上小地圖、框外一步的箭頭牌（輿圖表現第二版 W2：Joy 的搜尋列與篩選那一排 .mv-top 不畫了）、
  // 「正在看第幾週」、右下兩顆圓鈕（回到打開的取景、看整張）、抽屜、找地點那一整頁（開著才畫）。區名、小地圖、箭頭牌照此刻看哪裡，hudDraw 填
  function mapChrome() {
    const seeing = S.mapMode === "timeline" && S.mapWeek && S.mapWeek !== S.mapState.now_week;
    const banner = `<div class="map-banner" id="map-banner"${seeing ? "" : " hidden"}>${seeing ? `正在看${wkName(S.mapWeek, `第 ${S.mapWeek} 週`)}` : ""}</div>`;
    const here = placeOf(S.mapBase, S.mapState.here), reg = here && S.mapBase.regions.find((r) => r.id === here.region);
    const top = `<div class="mv-hud" id="mv-hud"><button type="button" class="mv-area" id="mv-area" data-act="map-area" aria-label="${MV_LOOK.area}">`
      + `<span class="t">${esc(reg ? reg.name : MV_LOOK.world)}</span><i aria-hidden="true">▾</i></button>`
      + `<button type="button" class="mv-q map-search" id="mv-q" data-act="map-search" aria-label="${MV_LOOK.search}"><span aria-hidden="true">🔍</span></button>`
      + `<div class="mv-minibox" id="mv-mini"></div><div class="mv-pills" id="mv-pills"></div></div>`;
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
  // ── 天下怎麼變（設計第六節）：上面一張曲線（三條戰線、割據、大事 📜、你在看的那一週），三方各佔幾處、比開季多少，
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
  // 抽屜的把手：拖上拖下（放開時靠到最近的一格），點一下在第一格與最後一格之間換。
  // 點一下在把手的 click 換格，不在 pointerup（FB-9090，W2 第二輪 2026-10-31）：觸控的 click 是放手之後瀏覽器才照那一點命中的，pointerup 就換了格的話，
  // 一行換到一排卡那一下，click 落到滑到手指底下的那張卡、開了那一處的卡。拖照舊在 pointer 事件裡；拖完（滑鼠按放都在把手上）瀏覽器多送的那一個
  // click 不算點一下（下一次按下去就清掉，不會吃掉玩家真正的下一下）
  function drawerGrab() {
    const grab = document.getElementById("mgrab"), drawer = document.getElementById("mdrawer");
    if (!grab || !drawer || (grab.dataset && grab.dataset.wired)) return; // 同一個把手只掛一次（remapChrome 換了新的把手才再掛）
    if (grab.dataset) grab.dataset.wired = "1";
    let drag = null, dragged = 0;
    grab.addEventListener("pointerdown", (ev) => {
      try { grab.setPointerCapture(ev.pointerId); } catch (e) { /* 合成的事件抓不住 */ }
      drag = { y: ev.clientY, h: drawer.offsetHeight, moved: false };
      dragged = 0;
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
      if (drag.moved) {
        const stops = drawerStops(), h = drawer.offsetHeight;
        mapStop(stops.slice().sort((a, z) => Math.abs(mapDrawerPx(a) - h) - Math.abs(mapDrawerPx(z) - h))[0], drag.h);
        dragged = Date.now();
      }
      drag = null;
    };
    grab.addEventListener("pointerup", end);
    grab.addEventListener("pointercancel", end);
    grab.addEventListener("click", () => {
      if (dragged && Date.now() - dragged < MV_CLICK) { dragged = 0; return; }
      dragged = 0;
      mapStop(drawerTap(drawerStops()));
    });
  }
  // 抽屜此刻可以停的幾格（拖動放開時靠到最近的一格）。沒點地點時三格（輿圖表現第二版 2.1 底條，W2）：peek 一行（底條）、row 一排卡（Joy 原本量
  // .m-peek-end 的那一高：滑卡片預覽時地圖還看得到）、full 全開。在路上照 Joy 的兩格（在路上的底條是 W3 的事）
  function drawerStops() {
    if (S.mapMode === "place") return ["peek", "half", "full"];
    if (S.mapMode === "timeline") return ["tl", "half", "full"];
    return S.mapState && S.mapState.journey ? ["peek", "full"] : ["peek", "row", "full"];
  }
  // 把手點一下換到哪一格：沒點地點時在一行與一排卡之間換（再拉才到全開）；其餘在第一格與最後一格之間換
  function drawerTap(stops) {
    if (stops.includes("row")) return S.mapDrawer === "peek" ? "row" : "peek";
    return S.mapDrawer === stops[0] ? stops[stops.length - 1] : stops[0];
  }
  // 拉把手停在哪一格：收回那一行時，底條「可出陣 N ›」開的那個內部篩選一起清掉（那一行又寫著「可出陣 N ›」）。from：拖的時候是拖動開始那一刻的高（px），
  // 照它判有沒有換格（setMapDrawer）
  function mapStop(h, from) {
    if (h === "peek" && S.mapMode !== "place" && S.mapFilter === "sortie") {
      S.mapFilter = "all";
      redrawDrawer();
      drawMarks();
    }
    setMapDrawer(h, from);
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
  // 沒點地點、不在路上時最低那一格是底條那一行（量到 .m-tray-end，W2），一排卡（row）才是 Joy 原本量到 .m-peek-end 的半開。
  // 量不到（還沒排版）照預設。桌機是右欄（CSS 蓋掉高度）
  // MV_TRAY：量不到時底條那一行多高＝實機量到的（375 寬：把手 22＋那一行 40＋下緣 2＋4；W2 審查 2026-10-31 那一行改 40 高之後是 68，以前寫 58、實機 63）
  const MV_PEEK_MIN = 120, MV_PEEK_NEAR = 196, MV_PEEK_PLACE = 200, MV_TRAY = 68;
  function mapDrawerPx(h) {
    const box = document.getElementById("mapx");
    const avail = (box && box.clientHeight) || 600;
    if (h === "peek" && drawerStops().includes("row")) return trayPx();
    // 版圖變化 320 高（企劃者 10/15 從對比圖選乙）：地圖大一截，曲線與處數在一屏，年表往下捲
    return { half: Math.round(avail * 0.6), full: Math.round(avail * 0.94), tl: Math.min(320, Math.round(avail * 0.55)) }[h] || peekPx(avail);
  }
  function peekPx(avail) {
    const end = document.querySelector("#mbody .m-peek-end");
    const at = end && end.offsetTop ? end.offsetTop + 10 : 0;
    const fall = S.mapMode === "place" ? Math.max(MV_PEEK_PLACE, Math.round(avail / 3)) : MV_PEEK_NEAR;
    return Math.round(Math.min(avail * 0.6, Math.max(MV_PEEK_MIN, at || fall)));
  }
  // 底條那一行（把手＋一行）：量到 .m-tray-end，量不到照 MV_TRAY
  function trayPx() {
    const end = document.querySelector("#mbody .m-tray-end");
    return end && end.offsetTop ? Math.round(end.offsetTop + 4) : MV_TRAY;
  }
  // from：拖把手放手時是拖動開始那一刻的高（px）——拖動中 pointermove 一路把高寫進 style，放手剛好停在那一格（拖上剛好到一排卡、拖到頂一定被夾在全開）
  // 拿 style 比會判成沒換格、名字與箭頭牌照舊的底邊排著（FB-9093，W2 第二輪 2026-10-31）
  function setMapDrawer(h, from) {
    S.mapDrawer = h;
    const d = document.getElementById("mdrawer"), box = document.getElementById("mapx");
    if (!d || !box) return;
    const px = mapDrawerPx(h), was = from !== undefined && from !== null ? `${Math.round(from)}px` : d.style.height;
    d.style.height = `${px}px`;
    // 收回底條那一行（或一排卡那一格）：抽屜捲回頂上，底條（本週、可出陣）才露得出來（W2 審查 2026-10-31：全開捲到下面再收回、點了一處往下捲卡
    // 再收回〔mapBack 整塊換掉〕，scrollTop 照留，那一行露的是底下那一段）。一行那一格一律回頂；一排卡那一格是換過來的才回（停在那一格往下捲的照留）
    const body = document.getElementById("mbody");
    if (body && drawerStops().includes("row") && (h === "peek" || (h === "row" && was !== d.style.height))) body.scrollTop = 0;
    // 露出來的那一塊變了：箭頭牌、名字照新的底邊重排（拖縮中不排，停下來那一次會排）
    if (was && was !== d.style.height && S.mapCam && !mvBusy()) marksSoon();
    // 右下兩顆圓鈕跟著抽屜上下（直接寫在那一塊上：寫在框上的自訂屬性會一路繼承，整棵地圖重算樣式，FB-322）
    const fab = document.getElementById("mv-fab");
    if (fab && fab.style) fab.style.bottom = deskMap() ? "" : `${px + 12}px`;
    // 抽屜全開時地圖只剩上面一條：兩顆圓鈕收起來（不然疊在 🔍 上；輿圖表現第二版 W2）；會疊到小地圖、被抽屜蓋住的也收（FB-9095，hudShow）
    const mg = mapGeom(document.getElementById("map"));
    hudShow(mg, S.mapCam && mg ? mvLevel(S.mapCam.z, mg) : 2);
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
  // 雙擊放大，從看得到整張天下縮到約 3 倍。字照倍率分三段（drawMarks）：遠看大區名與各方幾處、地點是一顆照誰佔著上色的點；中間、近看
  // 每一處的小圖與名字，小圖角上掛⚔、寶、本週旗、近看再加危險度（輿圖表現第二版 W1：誰佔著看地的顏色，名字旁的小印、字條、底下那一行、悟字拿掉）。
  // 地（戰略圖的地塊，groundSvg）三段都畫、常駐。名字撞在一起時讓開，讓不開的先收（選的、你在的、本週要去的、篩到的、要地、近的先畫）。
  // 底圖不再用伺服器畫好的那一張：主機畫的淡彩水墨（web/img/map/base.webp）疊上州界與路，烤成一張圖（bakeBase）；抓不到那一張時
  // 網頁照內容（底圖的 paint：大區、河、山、林）自己畫。山河名照 paint 寫在字那一層；
  // 城與營用畫的小圖（web/img/map）。拖縮的每一幀只換兩層的 transform（底圖那一層、字那一層照上一次排字的倍率先跟著縮放），
  // 縮放差過一截、跨了一段、停下來才重排字（地點多也不卡）。字待 joy 潤
  const MV_WORDS = {
    search: "要去哪？地點、人物、店面", all: "全部", sense: "能悟", tl: "⏱ 版圖", me: "回到我", fit: "看整張天下",
    from: "從{place}出發", road: "沿路能去", swipe: "由近到遠，左右滑", none: "附近沒有。拉遠一點看看，或換個標籤。", week: "本週", here: "你在這裡", next: "下一站", end: "終點",
    weekHead: "本週要事", figures: "附近的人物", jump: "跳到大區", places: "地點", people: "人物",
    notFound: "找不到「{q}」。地名、大區、人物、店面（醫館、鐵匠鋪、馬市）都找得到。",
  };
  // 輿圖表現第二版（企劃者 2026-10-30「照丙定」）新寫給玩家看的字都放這一張（待 joy 潤）：W1 小圖角上的徽；W2 的底條、箭頭牌、區名、近景名字後的幾分；
  // W3 的篩選籤接著加在這裡
  const MV_LOOK = {
    rich: "寶", fight: "⚔",
    week: "本週", noWeek: "本週沒有軍令", sortie: "可出陣 {n} ›", sortieHead: "可出陣", walk: "步行 {n} 分", min: "{n} 分", pill: "{name} {n}分",
    world: "天下", area: "換大區：找地點那一頁的跳到大區", search: "找地點、找人物", mini: "小地圖：點一下看那一帶",
  };
  const MV_CHIP_PEOPLE = "有人物";
  const NEAR_WORDS = { weekGo: "本週要去", bounty: "有賞" }; // 待 joy 潤
  const NEAR_PULL = "往上拉：能悟、對手、人物、今日產出"; // 待 joy 潤
  const RICH_WORD = "寶", LETTER_SEAL_WORD = "戰";
  // 取景與密度（輿圖表現第二版第四章）：數字照底圖的 view（Config.map_view，S1 送的九個數字）；底圖沒送（舊的快取）照預設。
  // 打開倍率 Z0 ＝ min(地圖框寬, open_width_max) ／ open_units（地圖 1 單位＝螢幕 1px 是 1 倍）：手機照框寬，桌機、平板、橫向手機不再放大、只多看一圈；
  // 其餘倍率都是 Z0 的幾倍——最大 zoom_max、近 ≥ near_from、中 ≥ mid_from（再小是遠）、換區 switch_zoom。取代 Joy 寫死的 MV_OPEN_Z 1.15、
  // MV_PICK_Z 1.4、MV_HOME_Z 1.2、MV_PREVIEW_Z 1.1（都＝Z0）、MV_ZMAX 3.2、MV_LV1 0.72、MV_LV2 1.35；最小照舊是整張天下放得下
  const MV_VIEW = { open_units: 250, open_width_max: 480, zoom_max: 1.6, near_from: 0.8, mid_from: 0.45, named_hops_near: 2, named_hops_mid: 1, switch_zoom: 0.6, patch_radius: 60 };
  function mvView() {
    return Object.assign({}, MV_VIEW, (S.mapBase && S.mapBase.view) || {});
  }
  function mvZ0(g) {
    const v = mvView();
    return Math.min(g.vw, Number(v.open_width_max)) / Number(v.open_units);
  }
  function mvZMax(g) {
    return mvZ0(g) * Number(mvView().zoom_max);
  }
  // 字分三段（2.2）：0 遠、1 中、2 近；門檻是 Z0 的幾倍
  function mvLevel(z, g) {
    const z0 = mvZ0(g), v = mvView();
    return z < z0 * Number(v.mid_from) ? 0 : z < z0 * Number(v.near_from) ? 1 : 2;
  }
  // 上面浮著的那一排（區名 chip＋🔍）讓開多高（px）；版圖變化時只讓開「正在看第 N 週」
  const MV_TOP = 56, MV_TL_TOP = 36;
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
  // 從 from 走幾步到每一處（底圖的路網 edges，畫面自己 BFS；設計第五章「路網（算步數）」）：{ 地點: 步數 }，走不到的不在裡面。照底圖記一份
  const hopMemo = new WeakMap();
  function mvHops(base, from) {
    let m = hopMemo.get(base);
    if (!m) hopMemo.set(base, (m = {}));
    if (!from) return {};
    if (m[from]) return m[from];
    const adj = {};
    for (const [a, b] of base.edges || []) { (adj[a] = adj[a] || []).push(b); (adj[b] = adj[b] || []).push(a); }
    const h = { [from]: 0 }, q = [from];
    for (let i = 0; i < q.length; i++) for (const v of adj[q[i]] || []) if (!(v in h)) { h[v] = h[q[i]] + 1; q.push(v); }
    return (m[from] = h);
  }
  // 腳下一步的那幾處（疊層有的）：打開的取景與箭頭牌用
  function mvNeighbors(base, st) {
    const h = mvHops(base, st.here);
    return base.places.filter((b) => h[b.id] === 1 && st.places[b.id]);
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
  // 這一格正在被誰翻、翻到幾成（疊層的 tug 裡進度最高的那一方；守方自己、進度 0 不算）；沒有是 null。名字底下的進度條也照它
  function tugOf(st, id, holder) {
    const t = st.places[id] && st.places[id].tug;
    if (!t) return null;
    const best = Object.entries(t).filter(([sd, v]) => sd !== holder && Number(v) > 0).sort((a, z) => Number(z[1]) - Number(a[1]))[0];
    return best ? { side: best[0], pct: Math.min(100, Number(best[1])) } : null;
  }
  // ── 篩選（上面那一排標籤）：全部、多半什麼（照底圖的 mostly，多的在前）、寶、有人物、能悟哪一種；再加版圖（「塗層」拿掉了：地常駐，
  // 輿圖表現第二版第三章）。
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
    const f = S.mapFilter || "all";
    return chipList(base, st).map(([k, t]) => `<button type="button" class="mv-chip${f === k ? " on" : ""}" data-act="map-filter" data-id="${esc(k)}" aria-pressed="${f === k}">${t}</button>`).join("")
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
    if (f === "sortie") return !!q.sortie; // 底條的「可出陣 N ›」（設計 2.1 底條：內部篩選，不是 🔍 頁的籤）
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
  // 底條（輿圖表現第二版 2.1「底條」，W2）：抽屜收著的那一行——「本週」章＋地名＋軍令內容＋步行 N 分（按了＝點那一處，map-pick），右邊朱字
  // 「可出陣 N ›」（按了＝抽屜拉到一排卡那一格、那一排只列可出陣的，mapSortie）。沒有本週寫「本週沒有軍令」；一處都不能出陣不寫右邊那一顆。
  // 窄螢幕（< 360）軍令只留第一個詞（其餘包在 .m-tray-more，style.css 藏起來）、字縮。在路上那一行（在路上 → 地名、沿路做小事）是 W3 的：
  // 在路上照 Joy 的（往哪裡、喊停＋沿路能去那一排），不畫底條
  // N＝按下去那一排的張數：那一排（nearList）不列你腳下那一處（腳下的卡接在後面），N 也不算它（W2 審查 2026-10-31：站在自己也能出陣的地方，
  // 以前寫「可出陣 8 ›」、按下去只有 7 張）
  function trayHtml(base, st) {
    const wk = nearWeek(st), wp = wk && placeOf(base, wk.id), here = st.journey ? null : st.here;
    const n = Object.entries(st.places).filter(([id, q]) => q.sortie && id !== here && q.minutes !== null && q.minutes !== undefined).length;
    let left = `<span class="m-tray-none">${MV_LOOK.noWeek}</span>`;
    if (wp) {
      const parts = String(wk.why || "").split("・").filter(Boolean), body = parts.length > 1 ? parts.slice(1) : parts;
      const far = wk.id === st.here ? MV_WORDS.here : MV_LOOK.walk.replace("{n}", Number(wk.minutes) || 0);
      const what = body.length ? `${esc(body[0])}<span class="m-tray-more">${body.slice(1).map((x) => `・${esc(x)}`).join("")}</span>・` : "";
      left = `<button type="button" class="m-tray-wk" data-act="map-pick" data-id="${esc(wk.id)}"><span class="m-tray-tag">${MV_LOOK.week}</span>`
        + `<b>${esc(mapLabel(wp))}</b><span class="m-tray-sub">${what}${esc(far)}</span></button>`;
    }
    const go = n ? `<button type="button" class="m-tray-go" data-act="map-sortie">${MV_LOOK.sortie.replace("{n}", n)}</button>` : "";
    return `<div class="m-tray">${left}${go}</div><i class="m-tray-end"></i>`;
  }
  // 底條的「可出陣 N ›」：抽屜拉到一排卡那一格，那一排只列可出陣的（內部篩選 sortie：地圖上合的照寫名字、不合的淡掉）。抽屜收回那一行就清掉（mapStop）
  function mapSortie() {
    S.mapFilter = "sortie";
    redrawDrawer();
    setMapDrawer("row");
    drawMarks();
  }
  function nearHtml(base, st) {
    const here = placeOf(base, st.here), list = nearList(base, st), f = S.mapFilter || "all";
    const from = st.journey ? MV_WORDS.road : MV_WORDS.from.replace("{place}", here ? here.name : "");
    const label = f === "all" ? from : `${f === "sortie" ? MV_LOOK.sortieHead : chipName(base, st, f)}・${list.length} 處`;
    const head = `<div class="m-nhead"><b>${esc(label)}</b><small>${MV_WORDS.swipe}</small></div>`;
    const cards = list.length ? `<div class="m-cards">${list.map((b) => nearCard(base, st, b)).join("")}</div>` : `<p class="m-sub m-none">${MV_WORDS.none}</p>`;
    // 第 3 週「離贏還差多少」（減法季整合設計 6.8）
    const gap = st.gap ? `<p class="m-gap">${esc(st.gap)}</p>` : "";
    const mine = here && !st.journey ? `<div class="m-mine">${placeCard(base, st, st.here)}</div>` : cardExtras(base, st);
    return `${st.journey ? journeyHtml(st) : trayHtml(base, st)}${head}${cards}<i class="m-peek-end"></i>${gap}${mine}`;
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
    const p = placeXY(id), c = S.mapCam, g = mapGeom(document.getElementById("map"));
    if (p && c && g) mapFlyTo(p, Math.max(c.z, mvZ0(g))); // 至少放到打開的倍率（輿圖表現第二版：MV_PREVIEW_Z 換成 Z0）
    else drawMarks();
  }

  // ── 地（輿圖表現第二版 2.1，企劃者 2026-10-30「照丙定」：Joy 的身子、戰略圖的衣服）：每一處的地塊（底圖的 world.cells）裁到它所在的區界，
  // 填主人色（劇本的 world.sides）34%、沒人佔淡灰 10%（底圖透上來）；塊內一圈自己的色（沒人佔而正在翻的是紅，照丙）、塊與塊之間一條暗線；兩方的地相接那一段亮白
  // （world.edges）；正在翻的斜紋兩色（推的那一方＋現在的主人）；下了戰書內側朱紅虛框（w-letter）、剛易手內框改成虛線（w-cool）；
  // 可出陣內側橘虛框（引擎說必敗的淡一半）；你的那一塊內側紅框（在路上不畫）。沒有地塊、或座標落在所屬區外的地點（官軍大營、綠林山寨）
  // 拿半徑 view.patch_radius 的圓當它的地：一樣填色上框、不裁區界、不算戰線。常駐（「塗層」開關拿掉了）、不混色、沒有濾鏡。
  // 線寬寫的是螢幕上看得到的寬（照丙畫出來的：內框 2.5、橘框紅框 3）：裁到塊內的那幾條畫兩倍寬，被裁掉外面那一半。
  // 框（內框、冷卻虛內框、可出陣、戰書、你）沿著看得到的那一塊描一整圈（FB-9070，W1 第二輪 2026-10-31）：看得到的是塊 ∩ 區，邊界是塊的邊落在區內
  // 的那幾段＋區界落在塊內的那幾段。框的路徑是塊的多邊形再接一條所在區的多邊形（同一個 d 兩段子路徑），裁到塊內（lc-）再裁到區界（lr-）：
  // 塊那一段留下塊在區內的內側，區那一段留下區界在塊內的內側，合起來剛好是塊 ∩ 區內側一圈。以前只描塊，伸出區界的那一截被裁掉、區界上沒有框
  // （36 塊有 30 塊缺 5% 以上，下曲陽缺七成）。不多一個節點，每一條框多一段區界的字（區的多邊形四到八個點、潁汝最多；開季平均每條多五十來個字）
  const LAND_UNHELD = "#B9B2A0", LAND_UNHELD_RIM = "#8F8B82", LAND_SEAM = "#1B1F17", LAND_FRONT = "#FFF6E0";
  const LAND_SORTIE = "#F0A640", LAND_HERE = "#C0392B";
  // 正在翻的中立地（沒人佔、有人在推）的內框：照丙是紅（企劃者 2026-10-31「照丙用紅框」；草圖 tools/slg5.js 的 txGround：有主人是主人色、
  // 沒主人而正在翻是紅）。跟有主的內框一樣粗（可見 2.5px）、0.85、實線；「你的那一塊」是可見 3px、不透明——丙就是這樣分的
  const LAND_TUG_RIM = "#C0392B";
  const LAND_FILL = 0.34, LAND_FILL_UNHELD = 0.1, LAND_FILL_TUG = 0.5, LAND_RIM_OP = 0.85, LAND_RIM_OP_UNHELD = 0.45, LAND_LOSE_OP = 0.5;
  const LAND_RIM_W = 2.5, LAND_RIM_W_UNHELD = 1.25, LAND_FRAME_W = 3, LAND_FRONT_W = 3.2, LAND_SEAM_W = 1; // 螢幕 px
  const LAND_DASH = [8, 5], LAND_COOL_DASH = [5, 4], LAND_STRIPE = 10, LAND_PATCH_R = 60; // 虛線與斜紋（螢幕 px）；圓的半徑（地圖單位，view 沒寫時）
  const SORTIE_LOSE = "必敗"; // 引擎判必敗的那一個字（mapdata 的 LOSE_WORD：suggest 的 lose 照它判；不在 suggest 裡的可出陣照同一個字）
  // 多邊形（world.cells、world.regions 的 d 只有 M、L、Z）：[[x, y], …]
  function polyOf(d) {
    const n = String(d).match(/-?\d+(?:\.\d+)?/g) || [], out = [];
    for (let i = 0; i + 1 < n.length; i += 2) out.push([Number(n[i]), Number(n[i + 1])]);
    return out;
  }
  function inPoly(x, y, pg) {
    let ins = false;
    for (let i = 0, j = pg.length - 1; i < pg.length; j = i++) {
      const a = pg[i], b = pg[j];
      if ((a[1] > y) !== (b[1] > y) && x < ((b[0] - a[0]) * (y - a[1])) / (b[1] - a[1]) + a[0]) ins = !ins;
    }
    return ins;
  }
  // 每一處的地（照底圖記一份）：地塊 { id, region, d, rd（所在區的多邊形，框沿著區界那一段用）, poly, rpoly }，或圓 { id, patch: true, x, y, r }
  // （地塊在前、圓在後：圓蓋在上面）
  const landMemo = new WeakMap();
  function landUnits(base) {
    let m = landMemo.get(base);
    if (m) return m;
    const wd = base.world || {}, r = Number(base.view && base.view.patch_radius) || LAND_PATCH_R;
    const regions = Object.fromEntries((wd.regions || []).map((g) => [g.id, { d: g.d, poly: polyOf(g.d) }]));
    const cells = Object.fromEntries((wd.cells || []).map((c) => [c.id, c]));
    const blocks = [], patches = [];
    for (const b of base.places) {
      const c = cells[b.id], rg = c && regions[c.region], rp = rg && rg.poly;
      if (rp && inPoly(b.x, b.y, rp)) blocks.push({ id: b.id, region: c.region, d: c.d, rd: rg.d, poly: polyOf(c.d), rpoly: rp });
      else patches.push({ id: b.id, patch: true, x: b.x, y: b.y, r });
    }
    m = { units: [...blocks, ...patches], patch: new Set(patches.map((u) => u.id)), regions: (wd.regions || []).map((g) => ({ id: g.id, poly: regions[g.id].poly })) };
    landMemo.set(base, m);
    return m;
  }
  // 地圖上 (mx, my) 是哪一處的地（整塊地都是那一處的熱區，設計 2.3）：照畫出來的那一塊——圓蓋在上面先問、地塊要在區界裡；都不是回 null
  function landAt(base, st, mx, my) {
    const { units } = landUnits(base);
    for (let i = units.length - 1; i >= 0; i--) {
      const u = units[i];
      if (!st.places[u.id]) continue;
      if (u.patch ? (mx - u.x) * (mx - u.x) + (my - u.y) * (my - u.y) <= u.r * u.r : inPoly(mx, my, u.rpoly) && inPoly(mx, my, u.poly)) return u.id;
    }
    return null;
  }
  // 地上畫的每一處長什麼樣子（groundSvg 只讀這一份，不再自己讀疊層）：疊層有沒有這一處、那一週的主人、正在翻的那一方（推得最多、不是主人）、
  // 冷卻中、戰書、可出陣與淡不淡（必敗）、是不是你那一塊（在路上沒有）。以前的週（版圖變化）只有主人與你，不畫翻、冷卻、戰書、可出陣。
  // groundShow 拿它當 key（FB-9071，W1 第二輪 2026-10-31）：以前 key 是抓疊層的時間（S.mapStateAt），輪詢重抓一次（在路上每 10 秒、平常每 30 秒）
  // #mk 就整張重寫一次，疊層一個字都沒變也一樣。會一直變、地上又不畫的（冷卻還剩幾分鐘、翻到幾成、必敗以外的勝算字、在路上還剩幾分鐘）不在裡面
  function groundLook(base, st, week) {
    const ctrl = controlAt(st, week), live = week === st.now_week, here = st.journey ? null : st.here;
    const lose = new Set((st.suggest || []).filter((g) => g.lose).map((g) => g.id)), out = {};
    for (const u of landUnits(base).units) {
      const q = st.places[u.id];
      if (!q) continue;
      const sd = ctrl[u.id] || null, t = live ? tugOf(st, u.id, sd) : null, sortie = live && !!q.sortie;
      out[u.id] = { sd, tug: t ? t.side : null, cool: live && !!sd && !!q.cool, letter: live && q.siege === "letter", sortie,
        faint: sortie && (lose.has(u.id) || (q.sortie === "attack" && !q.convoy && !!q.odds && q.odds.word === SORTIE_LOSE)), here: u.id === here };
    }
    return out;
  }
  // 純函式：k＝1／倍率（線寬照螢幕）、week 看哪一週（版圖變化：以前的週只畫顏色與你，不畫正在翻、冷卻、戰書、可出陣）；look 是 groundLook 那一份
  // （groundShow 算 key 時已經算好的，沒給就照疊層算）
  function groundSvg(base, st, k, week, look) {
    const wd = base.world;
    if (!wd) return "";
    const ls = look || groundLook(base, st, week), { units, patch } = landUnits(base);
    const w = (px) => f2(px * k), dash = (d) => `${w(d[0])} ${w(d[1])}`;
    const defs = wd.regions.map((r) => `<clipPath id="lr-${esc(r.id)}"><path d="${r.d}"/></clipPath>`), body = [], front = [], frames = [];
    for (const u of units) {
      const g = ls[u.id];
      if (!g) continue;
      const id = esc(u.id), sd = g.sd, t = g.tug, cool = g.cool;
      const tag = u.patch ? "circle" : "path", geo = u.patch ? `cx="${u.x}" cy="${u.y}" r="${u.r}"` : `d="${u.d}"`, inner = `clip-path="url(#lc-${id})"`;
      const ring = u.patch ? geo : `d="${u.d} ${u.rd}"`; // 框描的：塊＋所在區兩段子路徑，裁到塊內與區界裡＝塊 ∩ 區內側一圈（FB-9070）；圓不裁區界、照舊描圓
      const own = sd ? sideInk(sd).color : LAND_UNHELD;
      defs.push(`<clipPath id="lc-${id}"><${tag} ${geo}/></clipPath>`);
      if (t) {
        defs.push(`<pattern id="ls-${id}" patternUnits="userSpaceOnUse" width="${w(LAND_STRIPE)}" height="${w(LAND_STRIPE)}" patternTransform="rotate(45)">`
          + `<rect width="${w(LAND_STRIPE / 2)}" height="${w(LAND_STRIPE)}" fill="${sideInk(t).color}"/><rect x="${w(LAND_STRIPE / 2)}" width="${w(LAND_STRIPE / 2)}" height="${w(LAND_STRIPE)}" fill="${own}"/></pattern>`);
      }
      const rimInk = sd ? own : t ? LAND_TUG_RIM : null; // 主人色；沒主人而正在翻是紅（照丙）；都不是淡灰細線
      const rim = rimInk ? `stroke="${rimInk}" stroke-width="${w(LAND_RIM_W * 2)}" stroke-opacity="${LAND_RIM_OP}"`
        : `stroke="${LAND_UNHELD_RIM}" stroke-width="${w(LAND_RIM_W_UNHELD * 2)}" stroke-opacity="${LAND_RIM_OP_UNHELD}"`;
      const land = `<${tag} class="ld-fill" data-cell="${id}" ${geo} fill="${t ? `url(#ls-${id})` : own}" fill-opacity="${t ? LAND_FILL_TUG : sd ? LAND_FILL : LAND_FILL_UNHELD}"/>`
        + `<${tag} class="${cool ? "w-cool" : "ld-rim"}" data-cell="${id}" ${ring} fill="none" ${rim}${cool ? ` stroke-dasharray="${dash(LAND_COOL_DASH)}"` : ""} stroke-linejoin="round" ${inner}/>`
        + `<${tag} class="ld-seam" ${geo} fill="none" stroke="${LAND_SEAM}" stroke-opacity=".3" stroke-width="${w(LAND_SEAM_W)}"/>`;
      body.push(u.patch ? land : `<g clip-path="url(#lr-${esc(u.region)})">${land}</g>`);
      // 框畫在戰線上面、都裁到塊內：可出陣（必敗的淡一半）、戰書（凍結：出陣要知道的事，蓋在可出陣上面）、你
      const frame = (cls, color, more) => `<${tag} class="${cls}" data-cell="${id}" ${ring} fill="none" stroke="${color}" stroke-width="${w(LAND_FRAME_W * 2)}"${more} stroke-linejoin="round" ${inner}/>`;
      const box = (g.sortie ? frame("ld-sortie", LAND_SORTIE, ` stroke-dasharray="${dash(LAND_DASH)}"${g.faint ? ` stroke-opacity="${LAND_LOSE_OP}"` : ""}`) : "")
        + (g.letter ? frame("w-letter", FRONT_RED, ` stroke-dasharray="${dash(LAND_DASH)}"`) : "")
        + (g.here ? frame("ld-here", LAND_HERE, "") : "");
      if (box) frames.push(u.patch ? box : `<g clip-path="url(#lr-${esc(u.region)})">${box}</g>`);
    }
    for (const e of wd.edges || []) {
      if (patch.has(e.a) || patch.has(e.b) || !ls[e.a] || !ls[e.b]) continue;
      const a = ls[e.a].sd, b = ls[e.b].sd;
      if (a && b && a !== b) front.push(`<path class="ld-front" data-a="${esc(e.a)}" data-b="${esc(e.b)}" d="${e.d}"${e.clip ? ` clip-path="url(#lr-${esc(e.clip)})"` : ""}/>`);
    }
    return `<defs>${defs.join("")}</defs>${body.join("")}<g fill="none" stroke="${LAND_FRONT}" stroke-width="${w(LAND_FRONT_W)}" stroke-linecap="round">${front.join("")}</g>${frames.join("")}`;
  }
  // 地常駐（不看倍率、沒有塗層開關）。#mk 是一張向量的 SVG：Joy 10/30 把它畫成點陣是為了水暈的濾鏡與混色（拖縮每一幀重算、Safari 破圖），
  // 第二版兩樣都拿掉了；向量近看線才不糊。拖縮只換 #mvw 的 transform：手勢、慣性滑、滾輪、飛過去的途中（mvBusy）一次都不重寫，地跟著
  // transform 縮放（線寬暫時跟著粗細）；停下來的那一次 drawMarks，地上畫的變了（groundLook：疊層重抓了而地上畫的沒變不算，FB-9071）、換了週次而
  // 那一週畫的不一樣、倍率差過三分之一級（log2 的 1/3，線寬差不到一成二）才重寫一次（設計 2.2「key 含 log2(z)×3」、第七章「拖縮中只換
  // transform」；W1 審查 2026-10-30：以前捏、滾輪、飛的途中會整張重寫好幾次）
  const ground = { key: "", el: null };
  function groundK(z) {
    return Math.min(4, Math.max(0.25, 2 ** (-Math.round(Math.log2(z) * 3) / 3)));
  }
  function groundShow(c) {
    const svg = document.getElementById("mk");
    if (!svg || !S.mapBase || !S.mapState || !c || mvBusy()) return;
    const k = groundK(c.z), week = mapWeek(), look = groundLook(S.mapBase, S.mapState, week);
    const key = `${S.mapBase.key}|${f2(k)}|${JSON.stringify(look)}`;
    if (ground.el === svg && ground.key === key) return;
    Object.assign(ground, { el: svg, key });
    svg.innerHTML = groundSvg(S.mapBase, S.mapState, k, week, look);
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
  function regionSpot(base, r) {
    const w = base.world && base.world.regions.find((x) => x.id === r.id);
    return w && w.spots && w.spots.length ? w.spots[0] : [r.cx, r.cy];
  }
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
  // 畫的小圖多寬：近景照 MV_PAINT、中景八成
  function paintW(k, lvl) {
    return Math.round(MV_PAINT[k] * (lvl === 1 ? 0.8 : 1));
  }
  function pinHtml(b, x, y, dim, lvl) {
    const k = paintKey(b), at = `left:${f1(x)}px;top:${f1(y)}px`, id = esc(b.id), name = esc(b.name);
    if (k) {
      const w = paintW(k, lvl);
      return `<button type="button" class="mv-pin paint${dim}" style="${at};width:${w}px" data-act="map-place" data-id="${id}" aria-label="${name}"><img src="${mvImg(k)}" width="${w}" alt="" draggable="false"></button>`;
    }
    return `<button type="button" class="mv-pin ink${dim}" style="${at}" data-act="map-place" data-id="${id}" aria-label="${name}"><svg width="30" height="30" viewBox="-15 -17 30 30" aria-hidden="true"><circle r="9" cy="-2" fill="${MAP_HALO}" opacity=".7"/>${inkIcon(b.glyph, MV_INK, "none")}</svg></button>`;
  }
  // 小圖角上的徽（輿圖表現第二版 2.1「地點」「徽」；近、中景）：右下一顆危險度 1～3（像 SLG 的地等級；只在近景、你腳下那一處不掛：設計 2.2
  // 「中：沒有危險度徽」、第七章「危險度徽只在近」）、右上 ⚔（正在翻、激戰）、左上「寶」、頂上本週的紅旗。名字前不再蓋官／巾小印（誰的看地的
  // 顏色）、名字後不再接「寶」「戰」「本週」字條（都變成徽；戰書看地上的朱紅虛框）。o：near 近景、here 你腳下、week 本週要去、fight 正在翻或
  // 激戰、dim 篩選淡掉
  const MV_FLAG = '<path d="M3 24V2" stroke="#1B1F17" stroke-width="1.8"/><path d="M4 2l11 4.5-11 4.5z" fill="#C0392B" stroke="#7A1F18" stroke-width=".8"/>';
  function badgesHtml(q, x, y, o) {
    const at = (dx, dy) => `left:${f1(x + dx)}px;top:${f1(y + dy)}px`, dim = o.dim || "";
    return (o.week ? `<svg class="mv-flag${dim}" width="16" height="24" viewBox="0 0 16 24" style="${at(0, -12)}" aria-hidden="true">${MV_FLAG}</svg>` : "")
      + (o.near && !o.here ? `<i class="mv-dg${dim}" style="${at(10, 9)}">${Number(q.danger) || 1}</i>` : "")
      + (o.fight ? `<i class="mv-bd mv-bd-x${dim}" style="${at(11, -10)}">${MV_LOOK.fight}</i>` : "")
      + (q.rich ? `<i class="mv-bd mv-bd-rich${dim}" style="${at(-11, -10)}">${MV_LOOK.rich}</i>` : "");
  }
  // 小圖在螢幕上佔的框（名字、箭頭牌讓開它；設計第七章「名字不壓小圖」）：畫的城營照圖的長寬比（web/img/map 的圖；.mv-pin.paint 往上挪 62%）、
  // 墨筆小圖照 30 見方的那一張 svg；給了 o（badgesHtml 那一份）連角上的徽（危險度 15px、⚔ 與寶 16px、旗 16×24）。[左, 上, 右, 下]
  const MV_PAINT_H = { city: 0.6, city2: 0.664, outpost: 0.8, tents: 1.1, camp: 0.6 };
  function pinBox(b, q, x, y, lvl, o) {
    const k = paintKey(b);
    let bx;
    if (k) {
      const w = paintW(k, lvl), h = w * MV_PAINT_H[k];
      bx = [x - w / 2, y - 0.62 * h, x + w / 2, y + 0.38 * h];
    } else bx = [x - 15, y - 19, x + 15, y + 15]; // 墨筆那一張 svg 是行內的，底下多一截字的下緣，實機畫出來比錨點高 3～4px：上緣多留 4px
    if (!o) return bx;
    const add = (r) => { bx = [Math.min(bx[0], x + r[0]), Math.min(bx[1], y + r[1]), Math.max(bx[2], x + r[2]), Math.max(bx[3], y + r[3])]; };
    if (o.near && !o.here) add([2.5, 1.5, 17.5, 16.5]);
    if (o.fight) add([3, -18, 19, -2]);
    if (q.rich) add([-19, -18, -3, -2]);
    if (o.week) add([-3, -36, 13, -12]);
    return bx;
  }
  // 名字框（設計第七章：照估的字寬加 15% 餘裕）：名字（大地方 16px、其餘 14px、一定要寫而讓不開時縮到 11px）＋近景兩步內的「N 分」（11px，
  // 跟名字隔 3px）＋護糧的「下一站」「終點」字條（46px）。[寬, 高]
  const MV_LAB_ROOM = 1.15, MV_LAB_SMALL = 11, MV_LEG_W = 46, MV_RING_R = 22;
  // 地圖上（近、中景的名字、箭頭牌、底條）寫的地名：括號裡那一段不寫（照丙：「潁川郡（陽翟）」寫「潁川郡」；卡、找地點、遠看照舊寫全名）
  function mapLabel(b) {
    return String(b.name).replace(/（[^）]*）/g, "") || b.name;
  }
  function labSize(name, fs, min, leg) {
    return [MV_LAB_ROOM * (textW(name, fs) + (min ? 3 + textW(min, MV_LAB_SMALL) : 0)) + (leg ? MV_LEG_W : 0), fs * 1.2 + 2];
  }
  // 浮在地圖上的那幾樣佔的框（地圖框的座標；名字、箭頭牌都讓開）：左上區名 chip、右上 🔍、其下小地圖（近中景）、右下兩顆圓鈕（跟著抽屜，
  // 桌機貼底）。版圖變化時這一排收起（只剩「正在看第 N 週」，不算）
  const MV_MINI_TOP = 62;
  function miniSize(base, g) {
    const fr = (base.world && base.world.frame) || [0, 0, base.w, base.h], mw = g.vw < 360 ? 64 : 100;
    return [mw, Math.round((mw * fr[3]) / fr[2])];
  }
  // 每一樣兩個框：look 畫出來的那一塊（照 style.css：chip 上 10、高 34；🔍 上 8、46 見方；小地圖上 62、連 1px 的框；右下兩顆 46 見方、間隔 10、
  // 底下離抽屜 12），room 名字、箭頭牌讓開的那一塊（多留 2px；chip 連撐開的點擊範圍，上下各 4px：style.css 的 .mv-area::before，W2 審查 2026-10-31）。
  // hide：收起來（FB-9095，W2 第二輪 2026-10-31）——被抽屜蓋住（哪怕一截）的區名、🔍、小地圖收起；右下兩顆在全開、或會疊到任何一樣還露著的
  // 浮著的時收起（跟全開一樣，不挪位置：卡拉到六成時 ◎ 整顆在小地圖底下、點下去點到的是小地圖；320 寬一排卡那一格也是）。桌機抽屜是右欄，不蓋
  function hudParts(base, g, lvl, area) {
    if (S.mapMode === "timeline") return {};
    const desk = deskMap(), top = desk ? g.vh : g.vh - mapDrawerPx(S.mapDrawer), fb = desk ? g.vh - 16 : top - 12, cw = 10 + 40 + MV_LAB_ROOM * textW(area, 14);
    const parts = {
      area: { look: [10, 10, cw, 44], room: [8, 4, cw, 50] },
      q: { look: [g.vw - 58, 8, g.vw - 12, 54], room: [g.vw - 60, 6, g.vw - 10, 56] },
      fab: { look: [g.vw - 58, fb - 102, g.vw - 12, fb], room: [g.vw - 60, fb - 104, g.vw - 10, fb + 2] },
    };
    if (lvl > 0) {
      const [mw, mh] = miniSize(base, g);
      parts.mini = { look: [g.vw - 14 - mw, MV_MINI_TOP, g.vw - 12, MV_MINI_TOP + mh + 2], room: [g.vw - 14 - mw, MV_MINI_TOP - 2, g.vw - 10, MV_MINI_TOP + mh + 2] };
    }
    const up = ["area", "q", "mini"].filter((k) => parts[k]);
    for (const k of up) parts[k].hide = parts[k].look[3] > top;
    parts.fab.hide = !desk && (S.mapDrawer === "full" || up.some((k) => !parts[k].hide && boxCross(parts.fab.look, parts[k].look)));
    return parts;
  }
  function hudBoxes(base, g, lvl, area) {
    const parts = hudParts(base, g, lvl, area);
    return ["area", "q", "fab", "mini"].filter((k) => parts[k] && !parts[k].hide).map((k) => parts[k].room);
  }
  // 照 hudParts 把收起來的那幾樣藏起來（visibility：藏起來的也點不到）。沒有地圖框（還沒排版）時只照全開收右下兩顆
  const MV_HUD_IDS = { area: "mv-area", q: "mv-q", mini: "mv-mini", fab: "mv-fab" };
  function hudShow(g, lvl, area) {
    const parts = g && S.mapBase && S.mapState ? hudParts(S.mapBase, g, lvl, area !== undefined ? area : mvArea(S.mapBase, S.mapState, S.mapCam, g)) : null;
    for (const [k, id] of Object.entries(MV_HUD_IDS)) {
      const el = document.getElementById(id);
      if (!el || !el.style) continue;
      const hide = parts ? !!(parts[k] && parts[k].hide) : k === "fab" && S.mapDrawer === "full" && !deskMap();
      el.style.visibility = hide ? "hidden" : "";
    }
  }
  // 區名 chip 寫的（設計 2.1 HUD）：畫面中心（露出來那一塊的正中）此刻在哪一區；落在每一區的多邊形外就看最近的那一處在哪一區；遠看寫「天下」
  function mvArea(base, st, c, g) {
    if (!c || !g || mvLevel(c.z, g) === 0) return MV_LOOK.world;
    const room = mapRoom(g), mx = (g.vw / 2 - c.x) / c.z, my = ((room.top + room.bottom) / 2 - c.y) / c.z;
    const inside = landUnits(base).regions.find((r) => inPoly(mx, my, r.poly));
    let id = inside ? inside.id : null, best = Infinity;
    if (!id) for (const b of base.places) {
      const d = (b.x - mx) * (b.x - mx) + (b.y - my) * (b.y - my);
      if (st.places[b.id] && b.region && d < best) { best = d; id = b.region; }
    }
    const r = base.regions.find((x) => x.id === id);
    return r ? r.name : MV_LOOK.world;
  }
  const boxCross = (a, b) => a[0] < b[2] && a[2] > b[0] && a[1] < b[3] && a[3] > b[1];
  // 箭頭牌（設計 2.1「箭頭牌」）：近景、沒點地點、不在路上時，腳下一步、小圖整個在露出來那一塊外面的，畫面邊上掛一顆墨色膠囊「‹ 洛陽官道 8分」：
  // 從你畫一條線到它、交在邊上那一圈的那一點，沿那一邊滑開到不壓小圖、別的牌、浮著的那幾樣（那一邊都擺不下才換別的邊）。按了＝點那一處。
  // blocked：已經佔掉的框（小圖、浮著的那幾樣）。回 [{ id, box, html }]
  // 牌畫出來 24 高，點擊範圍上下各撐開 8px（style.css 的 .mv-pill::before，40 高；W2 審查 2026-10-31「觸控熱區不到 40px」）：排的時候照撐開的那一塊
  // （MV_PILL_HIT）讓開別的牌、小圖、浮著的那幾樣，名字也讓開它，點下去不會點到隔壁
  const MV_PILL_H = 24, MV_PILL_HIT = 40, MV_PILL_STEP = 4;
  function pillsLayout(base, st, c, g, lvl, blocked) {
    if (lvl !== 2 || S.mapMode !== "overview" || st.journey || !st.here) return [];
    const me = placeOf(base, st.here);
    if (!me) return [];
    const room = mapRoom(g), z = c.z, vis = [0, 0, g.vw, room.bottom], E = [8, room.top + 4, g.vw - 8, room.bottom - 8];
    if (E[3] - E[1] < 120) return []; // 抽屜拉到快全開、地圖只剩一條：不掛
    const hx = Math.min(E[2], Math.max(E[0], c.x + me.x * z)), hy = Math.min(E[3], Math.max(E[1], c.y + me.y * z));
    const taken = blocked.slice(), out = [];
    for (const b of mvNeighbors(base, st)) {
      const q = st.places[b.id], px = c.x + b.x * z, py = c.y + b.y * z;
      if (boxCross(pinBox(b, q, px, py, lvl, null), vis)) continue; // 小圖還露著一點：不掛
      const text = MV_LOOK.pill.replace("{name}", mapLabel(b)).replace("{n}", q.minutes !== null && q.minutes !== undefined ? Number(q.minutes) : "?");
      const w = Math.ceil(MV_LAB_ROOM * textW(text, 12) + 30), h = MV_PILL_HIT;
      const dx = px - hx, dy = py - hy, L = Math.hypot(dx, dy) || 1, ux = dx / L, uy = dy / L;
      let t = Infinity;
      if (ux > 0) t = Math.min(t, (E[2] - hx) / ux);
      if (ux < 0) t = Math.min(t, (E[0] - hx) / ux);
      if (uy > 0) t = Math.min(t, (E[3] - hy) / uy);
      if (uy < 0) t = Math.min(t, (E[1] - hy) / uy);
      const ex = hx + ux * t, ey = hy + uy * t;
      const first = Math.abs(ex - E[0]) < 0.5 ? "l" : Math.abs(ex - E[2]) < 0.5 ? "r" : Math.abs(ey - E[1]) < 0.5 ? "t" : "b";
      // 一條邊上的位置：貼著那一邊，離理想的那一點由近到遠
      const along = (side) => {
        const vert = side === "l" || side === "r", lo = vert ? E[1] + h / 2 : E[0] + w / 2, hi = vert ? E[3] - h / 2 : E[2] - w / 2;
        if (hi < lo) return [];
        const want = Math.min(hi, Math.max(lo, vert ? ey : ex)), list = [];
        for (let d = 0; d <= hi - lo + MV_PILL_STEP; d += MV_PILL_STEP) for (const s of d ? [want + d, want - d] : [want]) {
          if (s < lo - 0.01 || s > hi + 0.01) continue;
          const cx = side === "l" ? E[0] + w / 2 : side === "r" ? E[2] - w / 2 : s, cy = side === "t" ? E[1] + h / 2 : side === "b" ? E[3] - h / 2 : s;
          list.push([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]);
        }
        return list;
      };
      let box = null, side = first;
      for (const sd of [first, ...["l", "r", "t", "b"].filter((x) => x !== first)]) {
        box = along(sd).find((bx) => !taken.some((o) => boxCross(bx, o)));
        if (box) { side = sd; break; }
      }
      if (!box) continue;
      taken.push(box);
      const arrow = side === "l" ? "‹" : side === "r" ? "›" : side === "t" ? "︿" : "﹀", pre = side === "r" ? "" : `<b aria-hidden="true">${arrow}</b>`;
      out.push({ id: b.id, box, html: `<button type="button" class="mv-pill" style="left:${f1(box[0])}px;top:${f1(box[1] + (MV_PILL_HIT - MV_PILL_H) / 2)}px;width:${w}px" data-act="map-place" data-id="${esc(b.id)}" aria-label="${esc(b.name)}">`
        + `${pre}<span>${esc(text)}</span>${side === "r" ? `<b aria-hidden="true">${arrow}</b>` : ""}</button>` });
    }
    return out;
  }
  // 選了一處：路線中間掛的那一顆「幾分」擺在哪（{ x, y, n }；沒有是 null）
  function etaOf(base, st, scr) {
    const tgt = S.mapMode !== "timeline" && (S.mapSel || (S.mapMode === "overview" ? S.mapPreview : null)), tq = tgt && st.places[tgt], me = youXY(base, st);
    if (!tq || !me || !tq.path || !tq.path.length || !tq.minutes) return null;
    const pts = [me, ...tq.path.map((id) => placeXY(id)).filter(Boolean)], i = Math.floor(pts.length / 2);
    const a = pts[i - 1] || pts[0], bb = pts[i] || pts[0], [x, y] = scr((a[0] + bb[0]) / 2, (a[1] + bb[1]) / 2);
    return { x, y, n: Number(tq.minutes) };
  }
  // 照此刻的倍率排好一整層（純函式：c 是 { z, x, y }，g 是地圖框）。遠看照 Joy 的（marksFar）；近、中景（marksNear）照輿圖表現第二版 2.2：
  // 名字只寫跟我有關的。回 { html（#mkt 那一層）, pills（箭頭牌）, area（區名 chip 寫什麼）, lvl }
  function mvLayout(base, st, c, g) {
    const z = c.z, tl = S.mapMode === "timeline", lvl = tl ? 0 : mvLevel(z, g);
    const week = mapWeek(), ctrl = controlAt(st, week), live = week === st.now_week;
    const scr = (x, y) => [c.x + x * z, c.y + y * z];
    const area = mvArea(base, st, c, g), eta = etaOf(base, st, scr);
    const lay = lvl === 0 ? { out: marksFar(base, st, c, g, scr, ctrl, live), pills: [] } : marksNear(base, st, c, g, lvl, scr, ctrl, live, area, eta);
    const out = lay.out;
    // 版圖變化：那一週易手的地點閃一圈
    const row = (st.weeks || []).find((x) => x.week === week);
    if ((tl || !live) && row) for (const e of row.changed || []) {
      const b = placeOf(base, e.id);
      if (b) { const [x, y] = scr(b.x, b.y); out.push(`<i class="mv-pulse" style="left:${f1(x)}px;top:${f1(y)}px"></i>`); }
    }
    // 你：紅點（在路上畫在路上那一點）；選了一處：路線中間掛一顆「幾分」
    const me = youXY(base, st);
    if (me) { const [x, y] = scr(me[0], me[1]); out.push(`<i class="mv-you" style="left:${f1(x)}px;top:${f1(y)}px"></i>`); }
    if (eta) out.push(`<i class="mv-eta" style="left:${f1(eta.x)}px;top:${f1(eta.y)}px">${eta.n} 分</i>`);
    return { html: out.join(""), pills: lay.pills, area, lvl };
  }
  function marksHtml(base, st, c, g) {
    return mvLayout(base, st, c, g).html;
  }
  // 遠看（照 Joy 的）：大區名＋各方幾處（地面已經照歸屬上色）、地點是一顆照誰佔著上色的點；你在的、選的、本週要去的（篩選開著時篩到的）
  // 寫名字，底下一行；戰書、本週是名字後的字條。名字撞在一起時優先序：選的、滑到的、你在的、本週要去的、篩到的、要地、近的；位置試四個
  // （下、右、左、上），都壓到就不寫（選的、你在的照寫）。比 Joy 的多一樣（W2 Task 0 合 Joy 的「去輿圖帶終點」3d9b6161 時加的）：護糧的終點
  // 照寫名字（後面接「終點」；Joy 的遠景只掛圈、不寫名字）——Joy 的那一條測試在大框裡畫，W2 的門檻照 Z0 算之後落在遠景；遠景寫不寫終點請 PM 定
  // （W2 審查 2026-10-31）
  function marksFar(base, st, c, g, scr, ctrl, live) {
    const out = [], boxes = [];
    const sel = S.mapSel, prev = S.mapMode === "overview" ? S.mapPreview : null, wk = nearWeek(st), here = st.journey ? null : st.here;
    const leg = mapLeg(), end = leg && leg.to;
    const filt = (S.mapFilter || "all") !== "all";
    const padX = g.vw * 0.8, padY = g.vh * 0.8;
    const near = ([x, y]) => x > -padX && y > -padY && x < g.vw + padX && y < g.vh + padY;
    const shown = base.places.filter((b) => st.places[b.id]);
    const rank = (b) => (b.id === sel || b.id === prev || b.id === end ? 0 : b.id === here ? 1 : wk && wk.id === b.id ? 1.5
      : (mvMatch(st, b) ? 2 : 6) + (b.big ? 0 : 1) + (st.places[b.id].minutes ?? 500) / 1000);
    const order = shown.slice().sort((a, b) => rank(a) - rank(b));
    const hit = (bx) => boxes.some((o) => bx[0] < o[2] && bx[2] > o[0] && bx[1] < o[3] && bx[3] > o[1]);
    for (const b of order) { const [x, y] = scr(b.x, b.y), r = 6; boxes.push([x - r, y - r, x + r, y + r]); }
    const n = regionCounts(base, st, ctrl), sides = st.sides || sideOrder(base);
    for (const r of base.regions) {
      const [sx, sy] = regionSpot(base, r), [x, y0] = scr(sx, sy), y = y0 - 18, cnt = n[r.id] || { rich: 0 };
      const line = [...sides.filter((sd) => cnt[sd]).map((sd) => `${sideInk(sd).short} ${cnt[sd]}`), ...(cnt.rich ? [`${RICH_WORD} ${cnt.rich}`] : [])].join("・");
      const w = textW(r.name, 24) * 1.35;
      boxes.push([x - w / 2, y - 14, x + w / 2, y + (line ? 32 : 14)]);
      out.push(`<div class="mv-reg" style="left:${f1(x)}px;top:${f1(y)}px">${esc(r.name)}</div>`);
      if (line) out.push(`<div class="mv-cnt" style="left:${f1(x)}px;top:${f1(y + 15)}px">${esc(line)}</div>`);
    }
    for (const b of order) {
      const q = st.places[b.id], xy = scr(b.x, b.y);
      if (!near(xy)) continue;
      const [x, y] = xy, isHere = b.id === here, isSel = b.id === sel || b.id === prev, isWk = !!wk && wk.id === b.id, isEnd = b.id === end;
      // 篩選開著時不合的淡掉、不寫名字（選的、你的、本週的、終點除外；輿圖表現第二版 2.2）
      const on = isSel || isHere || isWk || isEnd || mvMatch(st, b), dim = on ? "" : " dim", ctl = ctrl[b.id] || null;
      out.push(`<button type="button" class="mv-dot${dim}${q.rich ? " rich" : ""}" style="left:${f1(x)}px;top:${f1(y)}px;--c:${ctl ? sideInk(ctl).color : MV_UNHELD}" data-act="map-place" data-id="${esc(b.id)}" aria-label="${esc(b.name)}"></button>`);
      if (isSel || isEnd) out.push(`<i class="mv-ring" style="left:${f1(x)}px;top:${f1(y)}px;--r:12px"></i>`);
      if (live && (q.melee || q.siege === "fight")) out.push(`<i class="mv-fight" style="left:${f1(x)}px;top:${f1(y)}px"></i>`);
      if (!on || (!isSel && !isHere && !isWk && !isEnd && !filt)) continue;
      // 護糧那種兩點（Joy 2026-10-31）：選了的那一處標「下一站」、終點標「終點」
      const leg1 = leg && b.id === sel ? MV_WORDS.next : leg && isEnd ? MV_WORDS.end : "";
      const legTag = leg1 ? `<span class="mv-wk leg">${leg1}</span>` : "", legW = leg1 ? MV_LEG_W : 0;
      const fs = b.big ? 16 : 14;
      const sub = isHere ? MV_WORDS.here : isSel || isWk ? nearSub(base, st, b.id, wk) : "";
      const odds = !isHere && isSel && q.odds ? `・<b style="color:${TONE_COLOR[q.odds.tone] || MAP_INK}">${esc(q.odds.word)}</b>` : "";
      const seals = (live && q.siege === "letter" ? `<span class="mv-rich">${LETTER_SEAL_WORD}</span>` : "") + (isWk ? `<span class="mv-wk">${MV_WORDS.week}</span>` : "") + legTag;
      const w = textW(b.name, fs) + (q.siege === "letter" ? 21 : 0) + (isWk ? 34 : 0) + legW + 8;
      const wsub = sub ? textW(sub, 11) + (odds ? 40 : 0) + 8 : 0;
      const W = Math.max(w, wsub), H = fs * 1.2 + 4 + (sub ? 15 : 0);
      // 選了的、終點：寧可擺上面也不擺左邊（貼著地圖左緣時擺左邊會出畫面；Joy 2026-10-31）；硬擺的那一個是最後一個
      const tries0 = [[-W / 2, 9], [12, -H / 2], [-12 - W, -H / 2], [-W / 2, -9 - H]];
      const tries = isSel || isEnd ? [tries0[0], tries0[1], tries0[3], tries0[2]] : tries0;
      for (const [i, [dx, dy]] of tries.entries()) {
        const bx = [x + dx, y + dy, x + dx + W, y + dy + H];
        if (hit(bx) && !((isSel || isHere || isEnd) && i === tries.length - 1)) continue;
        boxes.push(bx);
        out.push(`<button type="button" class="mv-lab${b.big ? " big" : ""}${isHere ? " here" : ""}${isSel ? " sel" : ""}" style="left:${f1(bx[0])}px;top:${f1(bx[1])}px" data-act="map-place" data-id="${esc(b.id)}">`
          + `<span class="t"><span class="nm">${esc(b.name)}${seals}</span>${sub ? `<small>${esc(sub)}${odds}</small>` : ""}</span></button>`);
        break;
      }
    }
    return out;
  }
  // 近、中景（輿圖表現第二版 2.2，W2）：每一處的小圖與角上的徽、山河名；名字只寫跟我有關的——
  //   近：兩步內（named_hops_near，名字後接「N 分」）、大地方、本週、寶、正在翻、可出陣；中：一步內（named_hops_mid）、大地方、本週、寶、正在翻；
  //   選的、滑到的、你、護糧的下一站與終點照寫；篩選開著時只寫合的（照 Joy 的：不管在不在上面那個集合裡），不合的淡掉。
  // 兩步內（中景一步內）、本週、選的、你、終點一定要寫：四個位置（下、右、左、上；選的與終點下、右、上、左，再加底下、上面靠左緣右緣的四個）都撞到
  // 就縮到 11px 再試一輪，還是不行就往外一圈圈找、拉一條細線回小圖；其餘撞了不寫。優先序：選的／滑到的／終點、你、本週、兩步內（近的先）、篩到的、要地、其餘。
  // 名字不壓小圖（連徽）、別的名字、箭頭牌、浮著的那幾樣（區名、🔍、小地圖、右下兩顆）、路線上的「幾分」，小圖露在露出來那一塊（左右是地圖框、
  // 上面到框頂、底下到抽屜）裡的名字整個在裡面，小圖在外面的名字整個在外面（拖進來的時候才看得到，不會切一半）
  function marksNear(base, st, c, g, lvl, scr, ctrl, live, area, eta) {
    const out = [], boxes = [], v = mvView();
    const sel = S.mapSel, prev = S.mapMode === "overview" ? S.mapPreview : null, wk = nearWeek(st), here = st.journey ? null : st.here;
    const leg = mapLeg(), end = leg && leg.to, filt = (S.mapFilter || "all") !== "all";
    const hops = mvHops(base, st.here), reach = Number(lvl === 2 ? v.named_hops_near : v.named_hops_mid), minHops = Number(v.named_hops_near);
    const room = mapRoom(g), B = room.bottom;
    const padX = g.vw * 0.8, padY = g.vh * 0.8;
    const near = ([x, y]) => x > -padX && y > -padY && x < g.vw + padX && y < g.vh + padY;
    const hit = (bx) => boxes.some((o) => boxCross(bx, o));
    const inVis = (x, y) => x >= 0 && x <= g.vw && y >= 0 && y <= B;
    const fits = (bx, inside) => (inside ? bx[0] >= 0 && bx[1] >= 0 && bx[2] <= g.vw && bx[3] <= B : bx[2] <= 0 || bx[0] >= g.vw || bx[3] <= 0 || bx[1] >= B);
    for (const l of paintLabels(base)) {
      const xy = scr(l.x, l.y);
      if (near(xy)) out.push(`<div class="mv-geo${l.v ? " v" : ""}" style="left:${f1(xy[0])}px;top:${f1(xy[1])}px">${esc(l.text)}</div>`);
    }
    // 小圖、徽、圈：先畫、先佔位
    const items = [];
    for (const b of base.places) {
      const q = st.places[b.id];
      if (!q) continue;
      const [x, y] = scr(b.x, b.y);
      if (!near([x, y])) continue;
      const ctl = ctrl[b.id] || null, isHere = b.id === here, isSel = b.id === sel || b.id === prev, isWk = !!wk && wk.id === b.id, isEnd = b.id === end;
      const on = isSel || isHere || isWk || isEnd || mvMatch(st, b), dim = on ? "" : " dim";
      const o = { near: lvl === 2, here: isHere, week: isWk, fight: live && (!!tugOf(st, b.id, ctl) || !!q.melee || q.siege === "fight"), dim };
      out.push(pinHtml(b, x, y, dim, lvl));
      out.push(badgesHtml(q, x, y, o));
      let box = pinBox(b, q, x, y, lvl, o);
      boxes.push(box);
      // 選的、終點那一圈也佔位（別的名字讓開它），它自己的名字從圈外擺起：名字的位置貼著小圖連圈的外框（W2 審查 2026-10-31：以前貼著小圖擺、
      // 八個位置全落在自己那一圈裡，選中的名字每一次都縮成 11px、多半還拉線）
      if (isSel || isEnd) {
        const R = MV_RING_R, ring = [x - R, y - R, x + R, y + R];
        out.push(`<i class="mv-ring" style="left:${f1(x)}px;top:${f1(y)}px;--r:${R}px"></i>`);
        boxes.push(ring);
        box = [Math.min(box[0], ring[0]), Math.min(box[1], ring[1]), Math.max(box[2], ring[2]), Math.max(box[3], ring[3])];
      }
      if (live && (q.melee || q.siege === "fight")) { out.push(`<i class="mv-fight" style="left:${f1(x)}px;top:${f1(y)}px"></i>`); boxes.push([x - 20, y - 20, x + 20, y + 20]); }
      items.push({ b, q, x, y, ctl, isHere, isSel, isWk, isEnd, on, box });
    }
    const me = youXY(base, st);
    if (me && st.journey) { const [x, y] = scr(me[0], me[1]); boxes.push([x - 10, y - 10, x + 10, y + 10]); }
    if (eta) { const w = textW(`${eta.n} 分`, 13) + 18; boxes.push([eta.x - w / 2, eta.y - 11, eta.x + w / 2, eta.y + 11]); }
    // 浮著的那幾樣、箭頭牌：名字讓開它們
    const hud = hudBoxes(base, g, lvl, area);
    const pills = pillsLayout(base, st, c, g, lvl, [...boxes, ...hud]);
    boxes.push(...hud, ...pills.map((p) => p.box));
    // 寫不寫名字：2 一定要寫、1 擠得下才寫、0 不寫
    const want = (it) => {
      const h = hops[it.b.id];
      if (it.isSel || it.isEnd || it.isHere || it.isWk) return 2;
      if (filt) return mvMatch(st, it.b) ? 1 : 0;
      if (h !== undefined && h <= reach) return 2;
      return it.b.big || it.q.rich || (live && !!tugOf(st, it.b.id, it.ctl)) || (lvl === 2 && !!it.q.sortie) ? 1 : 0;
    };
    const rank = (it) => {
      const h = hops[it.b.id], m = (it.q.minutes ?? 500) / 1000;
      return it.isSel || it.isEnd ? 0 : it.isHere ? 1 : it.isWk ? 1.5 : filt ? 2.5 + m : h !== undefined && h <= reach ? 2 + h / 10 + m : it.b.big ? 3 + m : 4 + m;
    };
    const named = items.map((it) => [it, want(it)]).filter(([, w]) => w).sort((a, z) => rank(a[0]) - rank(z[0]));
    const labs = [], leads = [];
    for (const [it, w] of named) {
      const { b, q, x, y, box } = it, inside = inVis(x, y), h = hops[b.id];
      const min = lvl === 2 && !it.isHere && h !== undefined && h <= minHops && q.minutes !== null && q.minutes !== undefined ? MV_LOOK.min.replace("{n}", Number(q.minutes)) : "";
      const leg1 = leg && b.id === sel ? MV_WORDS.next : leg && it.isEnd ? MV_WORDS.end : "";
      const fs0 = b.big ? 16 : 14, cy = (box[1] + box[3]) / 2, name = mapLabel(b);
      // 擺的位置：Joy 的四個（下、右、左、上；選的與終點下、右、上、左），再加四個靠邊對齊的（底下、上面靠小圖的左緣或右緣），都撞到才縮字
      const tries = (fs) => {
        const [W, H] = labSize(name, fs, min, leg1);
        const below = [x - W / 2, box[3] + 1, " c"], right = [box[2] + 2, cy - H / 2, ""], left = [box[0] - 2 - W, cy - H / 2, " r"], above = [x - W / 2, box[1] - 1 - H, " c"];
        const more = [[box[0], box[3] + 1, ""], [box[2] - W, box[3] + 1, " r"], [box[0], box[1] - 1 - H, ""], [box[2] - W, box[1] - 1 - H, " r"]];
        return [...(it.isSel || it.isEnd ? [below, right, above, left] : [below, right, left, above]), ...more].map(([l, t, a]) => [l, t, l + W, t + H, a]);
      };
      let spot = null, fs = fs0;
      for (const f of w === 2 ? [fs0, MV_LAB_SMALL] : [fs0]) {
        spot = tries(f).find((bx) => fits(bx, inside) && !hit(bx));
        if (spot) { fs = f; break; }
      }
      if (!spot && w === 2) { // 往外一圈圈找（11px），拉一條細線回小圖
        fs = MV_LAB_SMALL;
        const [W, H] = labSize(name, fs, min, leg1), cx = (box[0] + box[2]) / 2;
        for (let r = 1; r <= 14 && !spot; r++) {
          const d = 22 + r * 14, n = 8 + r * 2;
          for (let i = 0; i < n && !spot; i++) {
            const a = (i / n) * 2 * Math.PI, l = cx + d * Math.cos(a) - W / 2, t = cy + d * Math.sin(a) - H / 2, bx = [l, t, l + W, t + H, " c"];
            if (fits(bx, inside) && !hit(bx)) spot = bx;
          }
        }
        if (spot) {
          const px = Math.min(spot[2], Math.max(spot[0], x)), py = Math.min(spot[3], Math.max(spot[1], y)), len = Math.hypot(px - x, py - y);
          leads.push(`<i class="mv-lead" style="left:${f1(x)}px;top:${f1(y)}px;width:${f1(len)}px;transform:rotate(${f2(Math.atan2(py - y, px - x))}rad)"></i>`);
        }
      }
      if (!spot) continue;
      boxes.push(spot.slice(0, 4));
      const cls = `mv-lab${b.big ? " big" : ""}${it.isHere ? " here" : ""}${it.isSel ? " sel" : ""}${fs === MV_LAB_SMALL ? " tiny" : ""}${spot[4]}`;
      const tag = leg1 ? `<span class="mv-wk leg">${leg1}</span>` : "";
      labs.push(`<button type="button" class="${cls}" style="left:${f1(spot[0])}px;top:${f1(spot[1])}px;width:${f1(spot[2] - spot[0])}px" data-act="map-place" data-id="${esc(b.id)}">`
        + `<span class="t"><span class="nm">${esc(name)}${min ? `<small class="mv-min">${esc(min)}</small>` : ""}${tag}</span></span></button>`);
    }
    out.push(...leads, ...labs);
    return { out, pills };
  }
  let marksFrame = 0;
  const marksSoon = () => { if (!marksFrame) marksFrame = requestAnimationFrame(drawMarks); };
  // 照此刻的倍率重排字與小圖、地面、浮著的那幾樣（loadMap 換了疊層、篩選、選了一處、拖縮停下來、跨了一段倍率、抽屜換了高都叫這裡）
  function drawMarks() {
    if (marksFrame) { cancelAnimationFrame(marksFrame); marksFrame = 0; }
    const box = document.getElementById("mkt"), g = mapGeom(document.getElementById("map")), c = S.mapCam;
    if (!box || !S.mapBase || !S.mapState || !c || !g) return;
    const lay = mvLayout(S.mapBase, S.mapState, c, g);
    box.innerHTML = lay.html;
    box.style.transform = "";
    mv.laid = { ...c, vw: g.vw, vh: g.vh };
    hudDraw(g, c, lay);
    groundShow(c);
  }
  // ── 浮在地圖上的那幾樣（輿圖表現第二版 2.1「HUD」「小地圖」「箭頭牌」，W2）：區名 chip 寫畫面中心在哪一區、小地圖（近中景）、箭頭牌（mvLayout 排好的）。
  // 小地圖：整個天下，每一塊地照主人上色 85%（沒人佔淡）、區界、現在看的那一塊白框、你紅點；寬 100、窄螢幕（< 360）64；拿圓當地的不畫。
  // 地與你沒變就不重寫（白框跟著 camSet 換，miniFrame）
  function miniHtml(base, st, c, g) {
    const wd = base.world;
    if (!wd) return "";
    const [fx, fy, fw, fh] = wd.frame, [mw, mh] = miniSize(base, g), k = fw / mw, ctrl = controlAt(st, mapWeek()), me = youXY(base, st);
    const { units, regions } = landUnits(base);
    const defs = regions.map((r) => `<clipPath id="mm-${esc(r.id)}"><path d="${(wd.regions.find((x) => x.id === r.id) || {}).d || ""}"/></clipPath>`).join("");
    const cells = units.filter((u) => !u.patch && st.places[u.id]).map((u) => {
      const sd = ctrl[u.id];
      return `<path clip-path="url(#mm-${esc(u.region)})" d="${u.d}" fill="${sd ? sideInk(sd).color : MINI_UNHELD}" fill-opacity="${sd ? 0.85 : 0.35}"/>`;
    }).join("");
    const regs = wd.regions.map((r) => `<path d="${r.d}" fill="none" stroke="${LAND_SEAM}" stroke-opacity=".6" stroke-width="${f2(k)}"/>`).join("");
    const you = me ? `<circle cx="${f1(me[0])}" cy="${f1(me[1])}" r="${f2(k * 4)}" fill="${LAND_HERE}" stroke="#fff" stroke-width="${f2(k * 1.5)}"/>` : "";
    const [vx, vy, vw, vh] = miniView(c, g);
    return `<button type="button" class="mv-mini" data-act="map-mini" style="width:${mw}px;height:${mh}px" aria-label="${MV_LOOK.mini}">`
      + `<svg width="${mw}" height="${mh}" viewBox="${fx} ${fy} ${fw} ${fh}" preserveAspectRatio="none" aria-hidden="true"><defs>${defs}</defs>${cells}${regs}`
      + `<rect id="mv-mini-view" x="${f1(vx)}" y="${f1(vy)}" width="${f1(vw)}" height="${f1(vh)}" fill="#fff" fill-opacity=".15" stroke="#fff" stroke-width="${f2(k * 1.5)}"/>${you}</svg></button>`;
  }
  const MINI_UNHELD = "#C9C2AE";
  // 小地圖上的白框：此刻地圖框看到的那一塊（地圖座標的 [x, y, 寬, 高]）
  function miniView(c, g) {
    return [-c.x / c.z, -c.y / c.z, g.vw / c.z, g.vh / c.z];
  }
  function miniFrame(c, g) {
    const r = document.getElementById("mv-mini-view");
    if (!r || !r.setAttribute) return;
    const v = miniView(c, g);
    r.setAttribute("x", f1(v[0])); r.setAttribute("y", f1(v[1])); r.setAttribute("width", f1(v[2])); r.setAttribute("height", f1(v[3]));
  }
  function hudDraw(g, c, lay) {
    const base = S.mapBase, st = S.mapState, area = document.getElementById("mv-area"), mini = document.getElementById("mv-mini"), pills = document.getElementById("mv-pills");
    const t = area && area.querySelector && area.querySelector(".t");
    if (t && t.textContent !== lay.area) t.textContent = lay.area;
    if (mini) {
      const show = lay.lvl > 0 && S.mapMode !== "timeline", me = youXY(base, st);
      const key = show ? `${base.key}|${miniSize(base, g).join("x")}|${me ? me.join(",") : ""}|${JSON.stringify(controlAt(st, mapWeek()))}` : "";
      if (!mini.dataset || mini.dataset.key !== key) {
        mini.innerHTML = show ? miniHtml(base, st, c, g) : "";
        if (mini.dataset) mini.dataset.key = key;
      } else miniFrame(c, g);
    }
    // 箭頭牌：拖縮、飛的途中照舊藏著（camSet 藏的），停下來那一次 drawMarks 才露——途中倍率差過 MV_RELAYOUT 也會重排字（drawMarks），
    // 那一次不把它設回來，不然捏的途中牌一閃一閃（FB-9092，W2 第二輪 2026-10-31）
    if (pills) {
      pills.innerHTML = lay.pills.map((p) => p.html).join("");
      if (pills.style) pills.style.visibility = mvBusy() ? "hidden" : "";
    }
    hudShow(g, lay.lvl, lay.area);
  }
  // 點小地圖（設計 2.3）：中心移到點的那一帶、倍率不變
  function mapMini(el, ev) {
    const g = mapGeom(document.getElementById("map")), c = S.mapCam, wd = S.mapBase && S.mapBase.world;
    if (!g || !c || !wd || !el || !el.getBoundingClientRect) return;
    const r = el.getBoundingClientRect(), [fx, fy, fw, fh] = wd.frame;
    if (!r.width || !r.height) return;
    camFly(camAt(g, fx + ((ev.clientX - r.left) / r.width) * fw, fy + ((ev.clientY - r.top) / r.height) * fh, c.z));
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
  const mv = { pts: new Map(), start: null, moved: false, frame: 0, g: null, anim: 0, vel: [0, 0], last: null, lastTap: 0, tapTimer: 0, pickAt: 0, eatUntil: 0, wheelTimer: 0, laid: null };
  // 鏡頭還在動：手指按著又動過（拖、捏）、慣性滑或飛過去（mv.anim）、滾輪還沒停（mv.g 留著、沒有手指）。放手、滑停、飛完、滾輪停都會把它們
  // 清掉再叫一次 drawMarks（地在那一次才換級距，groundShow）
  const mvBusy = () => (mv.moved && mv.pts.size > 0) || !!mv.anim || (!!mv.g && !mv.pts.size);
  // 地圖框與它的內緣在畫面上的位置；框還沒有大小回 null
  function mapGeom(wrap) {
    if (!wrap || !wrap.clientWidth || !wrap.clientHeight) return null;
    const r = wrap.getBoundingClientRect();
    return { wrap, vw: wrap.clientWidth, vh: wrap.clientHeight, x0: r.left + wrap.clientLeft, y0: r.top + wrap.clientTop };
  }
  // 露出來的那一塊（上面讓開區名與 🔍 那一排、底下讓開抽屜；桌機右欄、版圖變化時地圖框本來就在抽屜外）：{ top, bottom }（px）
  function mapRoom(g) {
    const top = S.mapMode === "timeline" ? MV_TL_TOP : MV_TOP;
    const sheet = deskMap() || S.mapMode === "timeline" ? 0 : mapDrawerPx(S.mapDrawer);
    return { top, bottom: Math.max(top + 60, g.vh - sheet) };
  }
  // 整張天下的框：整張底圖（主機畫的那一張畫滿整張；拖到邊不露出圖外，Joy 2026-10-30「滑到邊邊會破圖」）
  const mapBox = (base) => [0, 0, base.w, base.h];
  function zMin(g) {
    const [, , fw, fh] = mapBox(S.mapBase), room = mapRoom(g);
    return Math.min(mvZMax(g), Math.max(0.05, Math.min((g.vw - 16) / fw, (room.bottom - room.top - 16) / fh)));
  }
  // 夾住：倍率在整張放得下到 Z0 × zoom_max 之間；圖比畫面大時邊不准拖進畫面（左右貼著框、上下貼著露出來那一塊），比畫面小時置中
  function camClamp(c, g) {
    const [fx, fy, fw, fh] = mapBox(S.mapBase), room = mapRoom(g);
    const z = Math.min(mvZMax(g), Math.max(zMin(g), c.z)), rh = room.bottom - room.top;
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
    miniFrame(q, g); // 小地圖的白框跟著每一幀（只改四個屬性）
    // 箭頭牌是照停下來那一刻排的、貼著畫面邊：拖縮、飛的途中先藏起來，停下來那一次 drawMarks 重排再出來（hudDraw）
    const pills = mvBusy() && document.getElementById("mv-pills");
    if (pills && pills.style) pills.style.visibility = "hidden";
    const m = document.getElementById("mkt"), L = mv.laid;
    if (!m || !L) return;
    const r = q.z / L.z, dx = q.x - L.x * r, dy = q.y - L.y * r;
    m.style.transform = Math.abs(r - 1) < 1e-4 && Math.abs(dx) < 0.01 && Math.abs(dy) < 0.01 ? "" : `translate(${f2(dx)}px, ${f2(dy)}px) scale(${r})`;
    if (Math.abs(Math.log(r)) > MV_RELAYOUT || mvLevel(q.z, g) !== mvLevel(L.z, g) || Math.abs(dx) > g.vw * 0.6 || Math.abs(dy) > g.vh * 0.6) marksSoon();
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
    if (g && p) camFly(camAt(g, p[0], p[1], Math.min(mvZMax(g), z)));
  }
  // 以地圖框裡 (px, py) 為中心縮放到 nz
  function zoomAt(nz, px, py, glide = false) {
    const g = mapGeom(document.getElementById("map")), c = S.mapCam;
    if (!g || !c) return;
    nz = Math.min(mvZMax(g), Math.max(zMin(g), nz));
    const t = { z: nz, x: px - ((px - c.x) / c.z) * nz, y: py - ((py - c.y) / c.z) * nz };
    if (glide) camFly(t);
    else camSet(t, g);
  }
  // 右下兩顆：◎ 回到打開的取景（輿圖表現第二版 2.2：camOpen，不再是「以你為中心、至少 1.2 倍」）、全 看整張天下
  function mapHome() {
    const g = mapGeom(document.getElementById("map"));
    if (g && S.mapBase && S.mapState) camFly(camOpen(g));
  }
  function mapFit() {
    const g = mapGeom(document.getElementById("map"));
    if (g) camFly(camFit(g));
  }
  // 找地點那一頁的「跳到大區」（換區，設計 2.2）：中心移到那一區的中心、倍率 Z0 × switch_zoom（中景）；以前是「整區放進來、最多兩倍」
  function mapRegionFly(rid) {
    const g = mapGeom(document.getElementById("map")), r = S.mapBase && S.mapBase.regions.find((x) => x.id === rid);
    if (!g || !r) return;
    camFly(camAt(g, r.cx, r.cy, mvZ0(g) * Number(mvView().switch_zoom)));
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
  // 點了一處（地圖上的小圖、名字、地、箭頭牌，附近那一排的卡、找地點的結果、今天去哪裡出陣、底條的本週）：抽屜開那一處的卡、畫路線。
  // 飛不飛（輿圖表現第二版 2.2，三種地方一條規則）：此刻倍率 < Z0（中、遠）飛到那一處、倍率到 Z0；≥ Z0（近、再放大）倍率不動、只在被擋住時
  // 挪一下（mvNudge）。fly 以前分「找地點、出陣建議飛過去」，現在不分了（留著參數：叫的地方照舊傳）。版圖變化時：年表上圈起來（同 map-mark）
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
    const p = placeXY(id), g = mapGeom(document.getElementById("map")), c = S.mapCam;
    if (p && g && c && c.z < mvZ0(g) - 1e-6) mapFlyTo(p, mvZ0(g));
    else { drawMarks(); mvNudge(id); }
  }
  // 收回（卡上的 ✕、找地點的 ←、點地圖的空白、再點同一處）：回底條那一行（輿圖表現第二版 2.3「收卡回底條」；底條「可出陣 N ›」開的內部篩選一起清掉）
  function mapBack() {
    const wasFind = S.mapMode === "search";
    Object.assign(S, { mapMode: "overview", mapSel: null, mapPreview: null, mapQuery: "", mapDrawer: "peek" });
    if (S.mapFilter === "sortie") S.mapFilter = "all";
    if (wasFind) remapChrome();
    else { redrawDrawer(); setMapDrawer("peek"); }
    drawRoute();
    drawMarks();
  }
  // 找地點：整頁一張清單，蓋在地圖上（🔍）。jump：左上的區名 chip 按的（設計 2.1 HUD「點了＝開 🔍 頁、捲到跳到大區那一排」，不另做選單）——
  // 捲到「跳到大區」、不叫鍵盤出來
  function mapFind(jump = false) {
    Object.assign(S, { mapMode: "search", mapQuery: "" });
    remapChrome();
    setTimeout(() => {
      if (!jump) { const q = document.getElementById("map-q"); if (q) q.focus(); return; }
      const box = document.getElementById("map-results"), regs = box && box.querySelector && box.querySelector(".m-regs");
      const head = regs && (regs.previousElementSibling || regs);
      if (box && head) box.scrollTop = Math.max(0, head.offsetTop - box.offsetTop - 8);
    }, 60);
  }
  function mapBlank() {
    if (S.mapMode === "place" || (S.mapMode === "overview" && S.mapPreview)) mapBack();
    else if (S.mapMode === "timeline" && S.mapSel) { S.mapSel = null; redrawDrawer(); drawMarks(); }
  }
  // 地圖上點了一處（輿圖表現第二版 2.3：小圖、名字、遠看的小點、那一塊地都是這一條；附近那一排的卡也走這裡）：開那一處的卡；再點同一處收回
  // （地鋪滿了，空地幾乎沒有了）。小圖、名字的雙擊照 Joy 的只開卡（那裡不放大）：第二下落在 MV_TAP2 之內，不算再點一次（W1 審查 2026-10-30）
  function mapLand(id) {
    if (S.mapMode === "place" && S.mapSel === id) {
      if (Date.now() - mv.pickAt >= MV_TAP2) mapBack();
      return;
    }
    mapPick(id);
    mv.pickAt = Date.now();
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
  // 點到地等 MV_TAP2 確定不是雙擊才開那一處的卡，點空白收回），拖過、捏過放開的那一下 click 吃掉。拖的指標動了才抓住（按下就抓的話，
  // Chrome 會把 click 送到抓住的地圖框）──
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
      const z = Math.min(mvZMax(g), Math.max(zMin(g), (s.cam.z * d) / s.d));
      camSet({ z, x: mx - g.x0 - wx * z, y: my - g.y0 - wy * z }, g);
    }
  }
  const mvSoon = () => { if (!mv.frame) mv.frame = requestAnimationFrame(mvFrame); };
  // 點了地、還在等 MV_TAP2 看有沒有第二下的那一下（mvUp）：又按下去了（雙擊的第二下、拖、捏）就作罷
  function mvTapDrop() {
    if (mv.tapTimer) { clearTimeout(mv.tapTimer); mv.tapTimer = 0; }
  }
  function mvDown(ev) {
    if ((ev.pointerType === "mouse" && ev.button !== 0) || !S.mapBase || !S.mapCam) return;
    mvTapDrop();
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
    const now = Date.now(), g = mapGeom(document.getElementById("map")), c = S.mapCam;
    if (g && now - mv.lastTap < MV_TAP2) { mv.lastTap = 0; zoomAt(S.mapCam.z * 2, ev.clientX - g.x0, ev.clientY - g.y0, true); return; }
    mv.lastTap = now;
    // 點到地（輿圖表現第二版 2.3：整塊地都是那一處的熱區）：照畫出來的那一塊算是哪一處（landAt），地圖上的字與小圖照舊由 click 開卡。
    // 等 MV_TAP2 過了、確定沒有第二下才開卡：雙擊照 Joy 的只放大（上面那一行），不開卡、不畫路線、不先為了露出小圖挪鏡頭（W1 審查 2026-10-30）
    const land = g && c && S.mapBase && S.mapState ? landAt(S.mapBase, S.mapState, (ev.clientX - g.x0 - c.x) / c.z, (ev.clientY - g.y0 - c.y) / c.z) : null;
    if (land) mv.tapTimer = setTimeout(() => { mv.tapTimer = 0; mapLand(land); }, MV_TAP2);
    else mapBlank();
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
  // 第一次（每一次打開輿圖）看哪裡：沒帶目標照打開的取景（camOpen）；帶了目標（江湖頁「去輿圖」、小地圖點了某一處、約戰卡「前往」：mapGoto）
  // 照 Joy 的（2026-10-31）——連另一頭（護糧的終點，不然是你）一起框進露出來的那一塊（留邊給字），最多放到 Z0（輿圖表現第二版：Joy 的 MV_PICK_Z
  // 換成 Z0）；兩頭太遠、框進來就成了遠景（< Z0 × mid_from，字只剩大區；Joy 的 MV_LV1）才只看選了的那一處、倍率 Z0
  function camFirst(g) {
    const st = S.mapState, base = S.mapBase, z0 = mvZ0(g);
    const leg = mapLeg(), a = S.mapSel && placeXY(S.mapSel), b = leg ? placeXY(leg.to) : st && !st.journey && youXY(base, st);
    if (a && b) {
      const room = mapRoom(g), w = Math.abs(a[0] - b[0]) + 320, h = Math.abs(a[1] - b[1]) + 160;
      const z = Math.min(z0, (g.vw - 16) / w, (room.bottom - room.top - 16) / h);
      if (z >= z0 * Number(mvView().mid_from)) return camAt(g, (a[0] + b[0]) / 2, (a[1] + b[1]) / 2, z);
    }
    return a ? camAt(g, a[0], a[1], z0) : camOpen(g);
  }
  // 打開的取景（輿圖表現第二版 2.2）：倍率 Z0（螢幕寬放 open_units 個地圖單位）、中心＝你（算兩票）＋腳下每一站（各一票）的平均，夾在天下的框裡。
  // 每次打開輿圖分頁、◎ 都回到這裡。在路上照你此刻那一點（往要去的那一站偏的那一截是 W3 的事）
  function camOpen(g) {
    const st = S.mapState, base = S.mapBase, me = st && youXY(base, st);
    if (!me) return camFit(g);
    let sx = me[0] * 2, sy = me[1] * 2, n = 2;
    if (!st.journey) for (const b of mvNeighbors(base, st)) { sx += b.x; sy += b.y; n += 1; }
    return camAt(g, sx / n, sy / n, mvZ0(g));
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
    if (S.mapFilter === "sortie") S.mapFilter = "all"; // 底條「可出陣 N ›」開的內部篩選不帶到下一次打開（🔍 的籤照舊留著）
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
