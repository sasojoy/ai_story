/* 天下大勢的網頁前端：輿圖（從 app.js 切出來，減法季批 0；說明見 app.js 檔頭）。 */
"use strict";

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

