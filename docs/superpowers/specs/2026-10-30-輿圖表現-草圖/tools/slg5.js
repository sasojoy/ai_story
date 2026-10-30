// 輿圖風格草圖（第 11 輪）：企劃者 2026-10-30「看一下現在最新的跟我們討論的～我覺得可以結合一下」。
// 在 Joy 10/30「一張到底」（develop 的 web/map.js：淡彩水墨底圖、畫的小圖、一指拖兩指捏、搜尋、篩選、抽屜、卡）的真頁面上，
// 把戰略圖設計稿的衣服套上去，Joy 的程式一行不改、只蓋掉幾個函式：
// 地＝每一處的地塊裁到區界、主人色、內框、兩軍相接白邊、正在翻斜紋、可出陣橘虛框、你紅框（常駐，不是「塗層」開關）；
// 地點＝Joy 畫的小圖＋危險度數字徽（⚔、寶、本週旗掛在小圖角上），名字只寫兩步內／要地／本週／寶／正在翻，兩步內的接幾分；
// 上面的搜尋列與篩選收成「區名 ▾」＋🔍，右上一張小地圖；框外一步的掛箭頭牌；
// 抽屜平常收成一行（本週要去＋可出陣幾處），往上拉才是 Joy 的「從某處出發」一排卡與腳下這一處的卡；點一處照 Joy 的卡。
// 用法（登入後在輿圖分頁）：txSlg5({blend:'normal'|'multiply'}) 打開＝近景；txSlg5Far() 縮到天下；txSlg5Pick(id) 點一處；重新整理還原。只是草圖。
(() => {
  const esc5 = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const RED = "#C0392B", ORANGE = "#F0A640", INK = "#1B1F17", UNHELD = "#B9B2A0";
  const NEAR_UNITS = 250, TOP = 56, STRIP = 58; // 打開時螢幕寬放幾個地圖單位；上面讓開區名那一排；抽屜收成一行多高（含把手）
  let blend = "normal";
  const f1 = (n) => Math.round(n * 10) / 10;
  const CSS = `
.mv-top{display:none!important}
.mdrawer{min-height:0!important}
.mv-ground{opacity:1!important;transition:none!important}
#tx-hud{position:absolute;inset:0;pointer-events:none;z-index:4;font-family:var(--sans)}
.tx-chip{position:absolute;left:10px;top:10px;background:rgb(244 236 220 / .94);border:1px solid rgb(42 35 28 / .55);border-radius:8px;padding:6px 10px;font:700 14px var(--kai);color:var(--mv-ink);box-shadow:0 1px 4px rgb(0 0 0 / .18)}
.tx-rb{position:absolute;right:12px;top:8px;width:44px;height:44px;border-radius:50%;background:rgb(244 236 220 / .94);border:1px solid rgb(42 35 28 / .55);display:flex;align-items:center;justify-content:center;font-size:18px;box-shadow:0 1px 4px rgb(0 0 0 / .18)}
.tx-mini{position:absolute;right:12px;top:60px;border-radius:6px;overflow:hidden;border:1px solid rgb(42 35 28 / .55);box-shadow:0 2px 6px rgb(0 0 0 / .3);background:#EFE6D2}
.tx-mini svg{display:block}
.tx-dg{position:absolute;transform:translate(-50%,-50%);width:15px;height:15px;border-radius:50%;background:#2B2F25;color:#fff;font:700 9.5px/14px var(--sans);text-align:center;border:1px solid #fff;box-sizing:border-box}
.tx-bd{position:absolute;transform:translate(-50%,-50%);width:16px;height:16px;border-radius:50%;color:#fff;font:700 10px/15px var(--kai);text-align:center;border:1px solid #fff;box-sizing:border-box}
.tx-x{background:#C0392B}
.tx-rich{background:#E0B23A;color:#2B2F25}
.tx-flag{position:absolute;transform:translate(-3px,-100%)}
.tx-pill{position:absolute;height:24px;border-radius:12px;background:rgb(42 35 28 / .86);border:1px solid rgb(255 255 255 / .25);color:#F4F1E8;font:700 12px/22px var(--sans);padding:0 10px;white-space:nowrap;box-sizing:border-box;text-align:center}
.tx-strip{display:flex;align-items:center;gap:6px;padding:0 14px 8px;font:500 13px var(--sans);color:var(--ink);min-height:30px}
.tx-strip b{font:700 15px var(--serif)}
.tx-strip .tx-tag{background:#C0392B;color:#fff;border-radius:3px;padding:1px 5px;font-size:11px;font-weight:700}
.tx-strip .tx-right{margin-left:auto;color:#A8322A;font-weight:700;white-space:nowrap}
.tx-strip .tx-sub{color:var(--ink-2,#6E5E49)}
.tx-min{font:500 11px/1.3 var(--sans);color:var(--mv-ink2);margin-left:3px;letter-spacing:0}
`;

  function hopsFrom(base, here) {
    const adj = {};
    for (const [a, b] of base.edges || []) { (adj[a] = adj[a] || []).push(b); (adj[b] = adj[b] || []).push(a); }
    const h = { [here]: 0 }, q = [here];
    while (q.length) { const u = q.shift(); for (const v of adj[u] || []) if (!(v in h)) { h[v] = h[u] + 1; q.push(v); } }
    return h;
  }

  // 地（戰略圖設計稿 2.1）：畫進 Joy 的 #mk（地圖座標，跟著拖縮）；k＝1／倍率，線寬照螢幕
  function txGround(base, st, k) {
    const wd = base.world, ctrl = controlAt(st, st.now_week), out = [];
    const col = (sd) => sideInk(sd).color;
    const tug = (id) => tugOf(st, id, ctrl[id] || null);
    out.push("<defs>");
    for (const r of wd.regions) out.push(`<clipPath id="rg5-${r.id}"><path d="${r.d}"/></clipPath>`);
    for (const c of wd.cells) out.push(`<clipPath id="cp5-${c.id}"><path d="${c.d}"/></clipPath>`);
    for (const c of wd.cells) {
      const t = tug(c.id); if (!t) continue;
      const a = col(t.side), b = ctrl[c.id] ? col(ctrl[c.id]) : UNHELD;
      out.push(`<pattern id="st5-${c.id}" patternUnits="userSpaceOnUse" width="${f1(10 * k)}" height="${f1(10 * k)}" patternTransform="rotate(45)"><rect width="${f1(5 * k)}" height="${f1(10 * k)}" fill="${a}"/><rect x="${f1(5 * k)}" width="${f1(5 * k)}" height="${f1(10 * k)}" fill="${b}"/></pattern>`);
    }
    out.push("</defs>");
    for (const c of wd.cells) {
      const sd = ctrl[c.id] || null, t = tug(c.id);
      const fill = t ? `url(#st5-${c.id})` : sd ? col(sd) : UNHELD, op = t ? 0.5 : sd ? 0.34 : 0.1, edge = sd ? col(sd) : t ? RED : "#8F8B82";
      out.push(`<g clip-path="url(#rg5-${c.region})"><path d="${c.d}" fill="${fill}" fill-opacity="${op}"/><g clip-path="url(#cp5-${c.id})"><path d="${c.d}" fill="none" stroke="${edge}" stroke-width="${f1((sd || t ? 5 : 2.5) * k)}" stroke-opacity="${sd || t ? 0.85 : 0.45}" stroke-linejoin="round"/></g><path d="${c.d}" fill="none" stroke="${INK}" stroke-opacity=".3" stroke-width="${f1(1 * k)}"/></g>`);
    }
    for (const e of wd.edges) {
      const a = e.a && ctrl[e.a], b = e.b && ctrl[e.b];
      if (a && b && a !== b) out.push(`<path d="${e.d}" fill="none" stroke="#FFF6E0" stroke-width="${f1(3.2 * k)}" stroke-linecap="round"${e.clip ? ` clip-path="url(#rg5-${e.clip})"` : ""}/>`);
    }
    for (const c of wd.cells) {
      const q = st.places[c.id] || {};
      if (q.sortie) out.push(`<g clip-path="url(#rg5-${c.region})"><g clip-path="url(#cp5-${c.id})"><path d="${c.d}" fill="none" stroke="${ORANGE}" stroke-width="${f1(6 * k)}" stroke-dasharray="${f1(8 * k)} ${f1(5 * k)}" stroke-linejoin="round"/></g></g>`);
      if (c.id === st.here && !st.journey) out.push(`<g clip-path="url(#rg5-${c.region})"><g clip-path="url(#cp5-${c.id})"><path d="${c.d}" fill="none" stroke="${RED}" stroke-width="${f1(6 * k)}" stroke-linejoin="round"/></g></g>`);
    }
    return out.join("");
  }
  function txGroundShow() {
    const svg = document.getElementById("mk");
    if (!svg || !S.mapCam || !S.mapBase || !S.mapState) return;
    svg.style.opacity = "1";
    svg.style.mixBlendMode = blend;
    svg.innerHTML = txGround(S.mapBase, S.mapState, 1 / S.mapCam.z);
  }

  // 字與小圖（近、中景）：Joy 的小圖＋危險度徽；名字只寫兩步內／要地／本週／寶／正在翻／可出陣，兩步內的接幾分；避讓照 Joy 的四個位置
  const origMarks = marksHtml;
  function txMarks(base, st, c, g) {
    const z = c.z, out = [], boxes = [];
    const sel = S.mapSel, prev = S.mapMode === "overview" ? S.mapPreview : null, wk = nearWeek(st), here = st.journey ? null : st.here;
    const hops = hopsFrom(base, st.here);
    const scr = (x, y) => [c.x + x * z, c.y + y * z];
    const padX = g.vw * 0.8, padY = g.vh * 0.8, near = ([x, y]) => x > -padX && y > -padY && x < g.vw + padX && y < g.vh + padY;
    const shown = base.places.filter((b) => st.places[b.id]);
    const hot = (b, q) => (wk && wk.id === b.id) || q.rich || !!q.tug || q.melee || b.id === sel || b.id === prev;
    const named = (b, q) => b.id === here || (hops[b.id] ?? 99) <= 2 || b.big || hot(b, q) || !!q.sortie;
    const rank = (b) => (b.id === sel || b.id === prev ? 0 : b.id === here ? 1 : wk && wk.id === b.id ? 1.5 : 2 + (hops[b.id] ?? 9) + (b.big ? 0 : 0.5));
    const order = shown.slice().sort((a, b) => rank(a) - rank(b));
    const hit = (bx) => boxes.some((o) => bx[0] < o[2] && bx[2] > o[0] && bx[1] < o[3] && bx[3] > o[1]);
    for (const b of order) { const [x, y] = scr(b.x, b.y); boxes.push([x - 14, y - 14, x + 14, y + 14]); }
    for (const l of paintLabels(base)) { const xy = scr(l.x, l.y); if (near(xy)) out.push(`<div class="mv-geo${l.v ? " v" : ""}" style="left:${f1(xy[0])}px;top:${f1(xy[1])}px">${esc5(l.text)}</div>`); }
    for (const b of order) {
      const q = st.places[b.id], xy = scr(b.x, b.y);
      if (!near(xy)) continue;
      const [x, y] = xy, isHere = b.id === here, isSel = b.id === sel || b.id === prev, isWk = !!wk && wk.id === b.id;
      out.push(pinHtml(b, x, y, "", z));
      if (isSel) out.push(`<i class="mv-ring" style="left:${f1(x)}px;top:${f1(y)}px;--r:22px"></i>`);
      if (!isHere) out.push(`<i class="tx-dg" style="left:${f1(x + 10)}px;top:${f1(y + 9)}px">${q.danger || 1}</i>`);
      if (q.tug || q.melee) out.push(`<i class="tx-bd tx-x" style="left:${f1(x + 11)}px;top:${f1(y - 10)}px">⚔</i>`);
      if (q.rich) out.push(`<i class="tx-bd tx-rich" style="left:${f1(x - 11)}px;top:${f1(y - 10)}px">寶</i>`);
      if (isWk) out.push(`<svg class="tx-flag" width="16" height="24" viewBox="0 0 16 24" style="left:${f1(x)}px;top:${f1(y - 12)}px"><path d="M3 24V2" stroke="${INK}" stroke-width="1.8"/><path d="M4 2l11 4.5-11 4.5z" fill="${RED}" stroke="#7A1F18" stroke-width=".8"/></svg>`);
      if (!named(b, q)) continue;
      const nm = b.name.replace(/（.*）/, ""), sub = isHere ? "" : (hops[b.id] ?? 99) <= 2 && q.minutes != null ? `${q.minutes} 分` : "";
      const fs = b.big ? 16 : 14, W = textW(nm, fs) + (sub ? textW(sub, 11) + 6 : 0) + 8, H = fs * 1.2 + 4;
      const tries = [[-W / 2, 15], [20, -10], [-20 - W, -10], [-W / 2, -30 - H]];
      for (const [i, [dx, dy]] of tries.entries()) {
        const bx = [x + dx, y + dy, x + dx + W, y + dy + H];
        if (hit(bx) && !((isSel || isHere) && i === tries.length - 1)) continue;
        boxes.push(bx);
        out.push(`<button type="button" class="mv-lab${b.big ? " big" : ""}${isHere ? " here" : ""}${isSel ? " sel" : ""}" style="left:${f1(bx[0])}px;top:${f1(bx[1])}px" data-act="map-place" data-id="${esc5(b.id)}"><span class="t"><span class="nm">${esc5(nm)}${sub ? `<small class="tx-min">${esc5(sub)}</small>` : ""}</span></span></button>`);
        break;
      }
    }
    const me = youXY(base, st);
    if (me) { const [x, y] = scr(me[0], me[1]); out.push(`<i class="mv-you" style="left:${f1(x)}px;top:${f1(y)}px"></i>`); }
    const tgt = sel || prev, tq = tgt && st.places[tgt];
    if (tq && me && tq.path && tq.path.length && tq.minutes) {
      const pts = [me, ...tq.path.map((id) => placeXY(id)).filter(Boolean)], i = Math.floor(pts.length / 2);
      const a = pts[i - 1] || pts[0], bb = pts[i] || pts[0], [x, y] = scr((a[0] + bb[0]) / 2, (a[1] + bb[1]) / 2);
      out.push(`<i class="mv-eta" style="left:${f1(x)}px;top:${f1(y)}px">${Number(tq.minutes)} 分</i>`);
    }
    return out.join("");
  }

  // 浮在圖上的：區名、🔍、小地圖、框外一步的箭頭牌（放在 #map 裡，不吃點擊）
  function txMini(base, st, c, g) {
    const [fx, fy, fw, fh] = base.world.frame, mw = g.vw < 360 ? 64 : 100, mh = Math.round(mw * fh / fw), ctrl = controlAt(st, st.now_week), sw = fw / mw;
    const defs = base.world.regions.map((r) => `<clipPath id="rg5m-${r.id}"><path d="${r.d}"/></clipPath>`).join("");
    const cells = base.world.cells.map((cc) => `<g clip-path="url(#rg5m-${cc.region})"><path d="${cc.d}" fill="${ctrl[cc.id] ? sideInk(ctrl[cc.id]).color : "#C9C2AE"}" fill-opacity="${ctrl[cc.id] ? 0.85 : 0.35}"/></g>`).join("");
    const regs = base.world.regions.map((r) => `<path d="${r.d}" fill="none" stroke="#1B1F17" stroke-opacity=".6" stroke-width="${f1(sw)}"/>`).join("");
    const hp = placeOf(base, st.here);
    return `<div class="tx-mini" style="width:${mw}px;height:${mh}px"><svg width="${mw}" height="${mh}" viewBox="${fx} ${fy} ${fw} ${fh}" preserveAspectRatio="none"><defs>${defs}</defs>${cells}${regs}<rect x="${f1(-c.x / c.z)}" y="${f1(-c.y / c.z)}" width="${f1(g.vw / c.z)}" height="${f1(g.vh / c.z)}" fill="#fff" fill-opacity=".15" stroke="#fff" stroke-width="${f1(sw * 1.5)}"/><circle cx="${hp.x}" cy="${hp.y}" r="${f1(sw * 4)}" fill="${RED}" stroke="#fff" stroke-width="${f1(sw * 1.5)}"/></svg></div>`;
  }
  function txPills(base, st, c, g) {
    const hp = placeOf(base, st.here), hops = hopsFrom(base, st.here), W = g.vw, H = g.vh, BOT = mapDrawerPx(S.mapDrawer);
    const scr = (x, y) => [c.x + x * c.z, c.y + y * c.z], [hx, hy] = scr(hp.x, hp.y), out = [], rects = [];
    const icons = base.places.map((p) => { const [x, y] = scr(p.x, p.y); return { x, y, r: 18 }; }).filter((o) => o.x > -20 && o.x < W + 20 && o.y > 0 && o.y < H);
    for (const id of Object.keys(hops)) {
      if (hops[id] !== 1) continue;
      const p = placeOf(base, id), q = st.places[id];
      if (!p || !q) continue;
      const [px, py] = scr(p.x, p.y);
      if (px > -6 && px < W + 6 && py > TOP - 6 && py < H - BOT + 6) continue;
      const dx = px - hx, dy = py - hy, L = Math.hypot(dx, dy) || 1, ux = dx / L, uy = dy / L;
      let t = Infinity;
      if (ux > 0) t = Math.min(t, (W - 16 - hx) / ux); if (ux < 0) t = Math.min(t, (16 - hx) / ux);
      if (uy > 0) t = Math.min(t, (H - BOT - 16 - hy) / uy); if (uy < 0) t = Math.min(t, (TOP + 16 - hy) / uy);
      const x = hx + ux * t, y = hy + uy * t, label = `${p.name.replace(/（.*）/, "")} ${q.minutes ?? "?"}分`, w = textW(label, 12) + 30, h = 24, horiz = Math.abs(ux) >= Math.abs(uy);
      let cx = Math.max(w / 2 + 6, Math.min(W - w / 2 - 6, x)), cy = Math.max(TOP + 14, Math.min(H - BOT - 14, y));
      const clash = () => rects.some((o) => Math.abs(o.x - cx) < (o.w + w) / 2 && Math.abs(o.y - cy) < (o.h + h) / 2) || icons.some((o) => Math.abs(o.x - cx) < o.r + w / 2 && Math.abs(o.y - cy) < o.r + h / 2);
      for (let i = 1; i <= 12 && clash(); i++) { const step = (i % 2 ? 1 : -1) * Math.ceil(i / 2) * 26; if (horiz) cy = Math.max(TOP + 14, Math.min(H - BOT - 14, y + step)); else cx = Math.max(w / 2 + 6, Math.min(W - w / 2 - 6, x + step)); }
      rects.push({ x: cx, y: cy, w, h });
      const arrow = horiz ? (ux > 0 ? "›" : "‹") : uy > 0 ? "⌄" : "⌃", left = horiz && ux < 0;
      out.push(`<div class="tx-pill" style="left:${f1(cx - w / 2)}px;top:${f1(cy - 12)}px;width:${f1(w)}px">${left ? `<span style="color:${ORANGE}">${arrow}</span> ` : ""}${esc5(label)}${!left ? ` <span style="color:${ORANGE}">${arrow}</span>` : ""}</div>`);
    }
    return out.join("");
  }
  function txHud() {
    const map = document.getElementById("map");
    if (!map) return;
    let hud = document.getElementById("tx-hud");
    if (!hud) { hud = document.createElement("div"); hud.id = "tx-hud"; map.appendChild(hud); }
    const base = S.mapBase, st = S.mapState, c = S.mapCam, g = mapGeom(map);
    if (!base || !st || !c || !g) return;
    const lvl = mvLevel(c.z), hp = placeOf(base, st.here), rg = base.regions.find((r) => r.id === hp.region);
    let h = `<div class="tx-chip">${esc5(rg ? rg.name : "")} ▾</div><div class="tx-rb">🔍</div>`;
    if (lvl > 0) h += txMini(base, st, c, g);
    if (lvl > 0 && !S.mapSel && !st.journey) h += txPills(base, st, c, g);
    hud.innerHTML = h;
  }
  // 抽屜收著那一行（設計稿的底條）：本週要去／在路上＋可出陣幾處；往上拉才是 Joy 的那一排卡
  function txStrip(base, st) {
    const wk = nearWeek(st), wp = wk && placeOf(base, wk.id), n = Object.values(st.places).filter((q) => q.sortie).length;
    const left = st.journey ? `<span class="tx-tag" style="background:${ORANGE};color:${INK}">在路上</span><b>→ ${esc5(st.journey.to_name || "")}</b><span class="tx-sub">還有 ${Number(st.journey.minutes)} 分</span>`
      : wp ? `<span class="tx-tag">本週</span><b>${esc5(wp.name.replace(/（.*）/, ""))}</b><span class="tx-sub">${esc5((wk.why || "").split("・").slice(1).join("・") || wk.why || "")}・${st.places[wk.id].minutes ?? ""} 分</span>` : `<span class="tx-sub">本週沒有軍令</span>`;
    return `<div class="tx-strip">${left}<span class="tx-right">${st.journey ? "沿路做小事 ›" : `可出陣 ${n} ›`}</span></div>`;
  }

  let installed = false;
  const origNear = nearHtml, origPx = mapDrawerPx, origDraw = drawMarks;
  function install() {
    if (installed) return;
    installed = true;
    const s = document.createElement("style"); s.id = "tx-mock-css"; s.textContent = CSS; document.head.appendChild(s);
    groundShow = () => txGroundShow();
    marksHtml = function (base, st, c, g) { return mvLevel(c.z) === 0 || S.mapMode === "timeline" ? origMarks(base, st, c, g) : txMarks(base, st, c, g); };
    drawMarks = function () { origDraw(); txHud(); };
    mapRoom = (g) => ({ top: TOP, bottom: Math.max(TOP + 60, g.vh - (deskMap() ? 0 : mapDrawerPx(S.mapDrawer))) });
    mapDrawerPx = (h) => ((h === "peek" || !h) && S.mapMode !== "place" ? STRIP : origPx(h));
    nearHtml = function (base, st) { return txStrip(base, st) + origNear(base, st); };
  }
  function txNear() {
    const g = mapGeom(document.getElementById("map")), base = S.mapBase, st = S.mapState, hp = placeOf(base, st.here), hops = hopsFrom(base, st.here);
    const nb = Object.keys(hops).filter((id) => hops[id] === 1).map((id) => placeOf(base, id)).filter(Boolean), n = nb.length + 2;
    const cx = (hp.x * 2 + nb.reduce((a, p) => a + p.x, 0)) / n, cy = (hp.y * 2 + nb.reduce((a, p) => a + p.y, 0)) / n;
    camSet(camAt(g, cx, cy, g.vw / NEAR_UNITS), g);
    drawMarks();
  }
  window.txSlg5 = (opts = {}) => {
    install();
    blend = opts.blend || "normal";
    Object.assign(S, { mapMode: "overview", mapSel: null, mapPreview: null, mapDrawer: "peek", mapFilter: "all" });
    redrawDrawer(); setMapDrawer("peek"); drawRoute();
    txNear();
    return { blend, cam: S.mapCam };
  };
  window.txSlg5Far = () => { mapFit(); return "far"; };
  window.txSlg5Pick = (id) => { mapPick(id); return id; };
})();
