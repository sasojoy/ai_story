// 輿圖風格草圖（第 9 輪）：企劃者看第 8 輪「還要再磨」（沒指哪裡）。第 8 輪再磨：山畫成山脈（有山腳、照前後排）、林大一點、
// 路畫成土路、山河寫名字、每一處的危險度寫成小數字徽（像 SLG 的地等級）、右上角一張小地圖（整個天下＋現在看的框）；
// 另外做一個六角格鋪地的版本對照（txSlg4('near', null, 'hex')）。底下是第 8 輪的註解。
// 輿圖風格草圖（第 8 輪）：企劃者看第 7 輪「這版看起來不錯，有辦法再優化嗎」。第 7 輪再磨四處：
// 1. 佔地改硬邊：每一處的地塊（Voronoi）裁到它所在的區界，不再切圓——同一區的地全有主、相鄰同色連成一片、邊是直的，像一塊塊地；
//    每一塊內側描一圈自己的顏色（內框），兩軍相接的那一段邊亮白＝戰線；
// 2. 打開不再照腳下一步去框（洛陽官道八分路把框拉得老遠）：固定一個近景倍率、以你為中心；框外還走得到的，在畫面邊緣掛箭頭牌（地名・幾分）；
// 3. 名字避讓：名字改在螢幕座標那一層擺，照下、上、右、左挑不壓到別的名字與圖示的位置；
// 4. 山水墊在地色底下透出來（SLG 的色塊是半透明的）。
// 用法：txSlg4('near'|'far', 點的地點 id)；txSlg4Off() 還原。只是草圖。
(() => {
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  let W = 375, H = 667; const TOPBAR = 64, BOTBAR = 70; // W、H 照現在的視窗量（txSlg4 裡設），320 寬也能看
  const RED = "#C0392B", ORANGE = "#F0A640", INK = "#1B1F17";
  const LAND = "#8F9B6C", LAND_LIGHT = "#A8B07F", LAND_DARK = "#66704D", WATER_EDGE = "#3F6D8C", WATER = "#78A9C4", YELLOW_R = "#C9A867", YELLOW_R2 = "#E2CB94";
  const MTN_LIGHT = "#9A9573", MTN_DARK = "#5E5A3F", TREE = "#55693F", TREE2 = "#7FA36A";
  const SANS = '-apple-system,"PingFang TC","Noto Sans TC","Microsoft JhengHei",sans-serif';
  const NEAR_UNITS = 250; // 打開時螢幕寬放幾個地圖單位（約三、四站路）

  async function data() {
    const [base, st] = await Promise.all([fetch("/api/map/base").then((r) => r.json()), fetch("/api/map/state").then((r) => r.json())]);
    const places = Object.values(base.places); const byId = Object.fromEntries(places.map((p) => [p.id, p]));
    const here = st.here, hp = byId[here], rid = hp.region;
    const toPts = (dstr) => { const n = dstr.replace(/[MLZ]/g, " ").trim().split(/\s+/).map(Number); const o = []; for (let i = 0; i < n.length; i += 2) o.push([n[i], n[i + 1]]); return o; };
    const sides = Object.fromEntries(base.world.sides.map((s) => [s.id, s]));
    const cells = base.world.cells.map((c) => ({ ...c, pts: toPts(c.d) })).filter((c) => byId[c.id]);
    const regions = base.world.regions.map((r) => ({ ...r, pts: toPts(r.d) }));
    const adj = {}; for (const [a, b] of base.edges) { (adj[a] = adj[a] || []).push(b); (adj[b] = adj[b] || []).push(a); }
    const hops = { [here]: 0 }; const q = [here]; while (q.length) { const u = q.shift(); for (const v of adj[u] || []) if (!(v in hops)) { hops[v] = hops[u] + 1; q.push(v); } }
    const doc = new DOMParser().parseFromString(base.svg, "image/svg+xml");
    const center = (el) => { const n = (el.getAttribute("d") || "").match(/-?\d+(\.\d+)?/g); if (!n || n.length < 4) return null; let sx = 0, sy = 0, k = 0; for (let i = 0; i + 1 < n.length; i += 2) { sx += +n[i]; sy += +n[i + 1]; k++; } return [sx / k, sy / k]; };
    const peaks = [...doc.querySelectorAll('[fill="#557D69"]')].map(center).filter(Boolean);
    const trees = [...doc.querySelectorAll('circle[fill="#7FA36A"]')].map((c) => [+c.getAttribute("cx"), +c.getAttribute("cy"), +c.getAttribute("r")]);
    const rivers = [...doc.querySelectorAll('path[stroke="#6FA0C2"]')].map((p) => p.getAttribute("d")).filter((d) => d && d.length > 20);
    const yellow = [...doc.querySelectorAll('path[stroke="#C9A867"]')].map((p) => p.getAttribute("d")).filter((d) => d && d.length > 20);
    const roadOf = {}; for (const [a, b, cx, cy] of base.roads) { roadOf[`${a}|${b}`] = [cx, cy]; roadOf[`${b}|${a}`] = [cx, cy]; }
    // 山、河的名字（底圖裡沒有 class 的 text；「北」是指北針）
    const terrainNames = [...doc.querySelectorAll("text")].filter((t) => !t.getAttribute("class") && t.textContent !== "北").map((t) => ({ t: t.textContent, x: +t.getAttribute("x"), y: +t.getAttribute("y") }));
    return { base, st, places, byId, here, hp, rid, sides, cells, regions, hops, peaks, trees, rivers, yellow, roadOf, terrainNames, S: st.places, week: st.week, frame: base.world.frame };
  }
  const inPoly = (pt, poly) => { let c = false; for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) { const [xi, yi] = poly[i], [xj, yj] = poly[j]; if ((yi > pt[1]) !== (yj > pt[1]) && pt[0] < ((xj - xi) * (pt[1] - yi)) / (yj - yi) + xi) c = !c; } return c; };

  function view(d, zoom, pickId) {
    const [fx0, fy0, fx1, fy1] = d.frame; let s, cx, cy;
    if (zoom === "far") { s = Math.min((W - 16) / (fx1 - fx0), (H - TOPBAR - BOTBAR) / (fy1 - fy0)); cx = (fx0 + fx1) / 2; cy = (fy0 + fy1) / 2; }
    else { s = W / NEAR_UNITS;
      // 以你為主、往腳下那幾站偏一點（你算兩票、每一站一票），免得一半畫面是沒人的地；在路上就以路上那一點與要去的那一站為中心
      const nb = Object.keys(d.hops).filter((id) => d.hops[id] === 1).map((id) => d.byId[id]); const n = nb.length + 2;
      cx = (d.hp.x * 2 + nb.reduce((a, p) => a + p.x, 0)) / n; cy = (d.hp.y * 2 + nb.reduce((a, p) => a + p.y, 0)) / n;
      const J = d.st.journey; if (J && J.x != null) { const to = d.byId[J.to]; cx = to ? J.x + (to.x - J.x) * 0.35 : J.x; cy = to ? J.y + (to.y - J.y) * 0.35 : J.y; }
      if (pickId && d.byId[pickId]) { cx = (d.hp.x + d.byId[pickId].x) / 2; cy = (d.hp.y + d.byId[pickId].y) / 2; } }
    const midY = zoom === "far" ? (TOPBAR + H - BOTBAR) / 2 : (TOPBAR + H - BOTBAR) / 2;
    let vx0 = cx - (W / 2) / s, vy0 = cy - midY / s;
    if (zoom !== "far") { vx0 = Math.max(fx0, Math.min(fx1 - W / s, vx0)); vy0 = Math.max(fy0, Math.min(fy1 - H / s, vy0)); }
    return { s, k: 1 / s, X: (x) => (x - vx0) * s, Y: (y) => (y - vy0) * s, tr: `translate(${(-vx0 * s).toFixed(2)},${(-vy0 * s).toFixed(2)}) scale(${s.toFixed(4)})` };
  }

  function mount(html) {
    txSlg4Off();
    const map = document.querySelector("#map"); const top = map.getBoundingClientRect().top; const tabsTop = document.querySelector(".tabs").getBoundingClientRect().top;
    const box = document.createElement("div"); box.id = "tx-mock";
    box.style.cssText = `position:fixed;left:0;right:0;top:${Math.round(top)}px;bottom:${Math.round(innerHeight - tabsTop)}px;z-index:950;overflow:hidden;background:${LAND};font-family:${SANS}`;
    box.innerHTML = html; document.body.appendChild(box);
    const rt = document.querySelector(".r-top"); if (rt) rt.style.visibility = "hidden";
  }
  window.txSlg4Off = () => { document.querySelector("#tx-mock")?.remove(); const rt = document.querySelector(".r-top"); if (rt) rt.style.visibility = ""; };

  const ownerOf = (d, id) => (d.S[id] || {}).control || null;
  const sideOf = (d, id) => { const o = ownerOf(d, id); return o && d.sides[o] ? d.sides[o] : null; };
  const poly = (pts) => pts.map((p) => p.join(",")).join(" ");

  function groundSvg(d, f, opts = {}) {
    const g = []; const k = f.k; const [fx0, fy0, fx1, fy1] = d.frame; const hexTiles = opts.tiles === "hex";
    g.push(`<defs><radialGradient id="landg" cx="50%" cy="45%" r="70%"><stop offset="0" stop-color="${LAND_LIGHT}"/><stop offset="1" stop-color="${LAND}"/></radialGradient><filter id="soft" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="${(4 * k).toFixed(2)}"/></filter><filter id="grain" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="1.3" numOctaves="1" seed="4"/><feColorMatrix values="0 0 0 0 0.1 0 0 0 0 0.12 0 0 0 0 0.05 0 0 0 0.06 0"/></filter>`);
    for (const r of d.regions) g.push(`<clipPath id="rg-${r.id}"><polygon points="${poly(r.pts)}"/></clipPath>`);
    for (const c of d.cells) g.push(`<clipPath id="cp-${c.id}"><polygon points="${poly(c.pts)}"/></clipPath>`);
    for (const c of d.cells) { const st = d.S[c.id] || {}; if (!st.tug) continue; const side = Object.keys(st.tug)[0]; const a = d.sides[side] ? d.sides[side].color : "#B9B49E", b = sideOf(d, c.id) ? sideOf(d, c.id).color : "#B9B49E";
      g.push(`<pattern id="stripe-${c.id}" patternUnits="userSpaceOnUse" width="${(10 * k).toFixed(2)}" height="${(10 * k).toFixed(2)}" patternTransform="rotate(45)"><rect width="${(5 * k).toFixed(2)}" height="${(10 * k).toFixed(2)}" fill="${a}"/><rect x="${(5 * k).toFixed(2)}" width="${(5 * k).toFixed(2)}" height="${(10 * k).toFixed(2)}" fill="${b}"/></pattern>`); }
    g.push(`</defs>`);
    g.push(`<rect x="${fx0 - 3000}" y="${fy0 - 3000}" width="${fx1 - fx0 + 6000}" height="${fy1 - fy0 + 6000}" fill="${LAND_DARK}"/><rect x="${fx0}" y="${fy0}" width="${fx1 - fx0}" height="${fy1 - fy0}" fill="url(#landg)"/>`);
    // 山水墊在底下：林大一點（兩層＋影子）；山畫成山脈（山腳一片暗、照 y 排讓前面的壓後面的、大小略有變化）
    for (const [x, y, r] of d.trees) { const R = r * 1.3; g.push(`<circle cx="${x + 0.8}" cy="${y + 1.6}" r="${R}" fill="${INK}" opacity=".2"/><circle cx="${x}" cy="${y}" r="${R}" fill="${TREE}"/><circle cx="${x - R * 0.28}" cy="${y - R * 0.3}" r="${R * 0.55}" fill="${TREE2}" opacity=".85"/>`); }
    const peaks = [...d.peaks].sort((a, b) => a[1] - b[1]);
    for (const [x, y] of peaks) g.push(`<ellipse cx="${x}" cy="${y + 6}" rx="24" ry="10" fill="${MTN_DARK}" opacity=".14" filter="url(#soft)"/>`);
    peaks.forEach(([x, y], i) => { const h = 11 + (i % 3) * 2.5, b = 13 + (i % 4) * 1.5;
      g.push(`<path d="M${x - b},${y + 7}L${x},${y - h}L${x + 1.5},${y + 7}Z" fill="${MTN_LIGHT}"/><path d="M${x},${y - h}L${x + b},${y + 7}L${x + 1.5},${y + 7}Z" fill="${MTN_DARK}"/><path d="M${x - 2.8},${y - h + 4}L${x},${y - h}L${x + 2.8},${y - h + 4}Z" fill="#F2F0E6" opacity=".85"/>`); });
    for (const dd of d.rivers) g.push(`<path d="${dd}" fill="none" stroke="${WATER_EDGE}" stroke-width="5.5" vector-effect="non-scaling-stroke" stroke-linejoin="round" stroke-linecap="round"/><path d="${dd}" fill="none" stroke="${WATER}" stroke-width="2.6" vector-effect="non-scaling-stroke" stroke-linejoin="round" stroke-linecap="round"/>`);
    for (const dd of d.yellow) g.push(`<path d="${dd}" fill="none" stroke="${YELLOW_R}" stroke-width="7" vector-effect="non-scaling-stroke" stroke-linejoin="round"/><path d="${dd}" fill="none" stroke="${YELLOW_R2}" stroke-width="3" vector-effect="non-scaling-stroke" stroke-linejoin="round"/>`);
    // 地（六角格版）：每一區裡鋪六角格，每一格照落在哪一處的地塊上色；格邊細、沒有內框與戰線（顏色一變就是戰線）
    if (hexTiles) { const R = 15, dx = R * Math.sqrt(3), dy = R * 1.5; const hexPts = (cx, cy) => { const o = []; for (let i = 0; i < 6; i++) { const a = Math.PI / 6 + (i * Math.PI) / 3; o.push(`${(cx + R * Math.cos(a)).toFixed(1)},${(cy + R * Math.sin(a)).toFixed(1)}`); } return o.join(" "); };
      for (const rg of d.regions) { const xs = rg.pts.map((p) => p[0]), ys = rg.pts.map((p) => p[1]); const x0 = Math.min(...xs) - R, x1 = Math.max(...xs) + R, y0 = Math.min(...ys) - R, y1 = Math.max(...ys) + R; const cellsHere = d.cells.filter((c) => c.region === rg.id);
        g.push(`<g clip-path="url(#rg-${rg.id})">`);
        for (let r = 0; r * dy < y1 - y0; r++) for (let c = 0; c * dx < x1 - x0; c++) { const cx = x0 + c * dx + (r % 2 ? dx / 2 : 0), cy = y0 + r * dy; if (!inPoly([cx, cy], rg.pts)) continue;
          const inside = cellsHere.filter((cc) => inPoly([cx, cy], cc.pts)); let cell = null, best = Infinity; for (const cc of inside) { const p = d.byId[cc.id]; const dd = Math.hypot(p.x - cx, p.y - cy); if (dd < best) { best = dd; cell = cc; } }
          if (!cell) { let b2 = Infinity; for (const cc of cellsHere) { const p = d.byId[cc.id]; const dd = Math.hypot(p.x - cx, p.y - cy); if (dd < b2) { b2 = dd; cell = cc; } } }
          const st = cell ? d.S[cell.id] || {} : {}; const sd = cell ? sideOf(d, cell.id) : null; const fill = st.tug ? `url(#stripe-${cell.id})` : sd ? sd.color : "#D8D3C2";
          g.push(`<polygon points="${hexPts(cx, cy)}" fill="${fill}" fill-opacity="${st.tug ? 0.55 : sd ? 0.42 : 0.16}" stroke="${INK}" stroke-opacity=".22" stroke-width="1" vector-effect="non-scaling-stroke"/>`); }
        g.push(`</g><polygon points="${poly(rg.pts)}" fill="none" stroke="${INK}" stroke-opacity=".45" stroke-width="1.2" vector-effect="non-scaling-stroke"/>`); } }
    // 地：每一塊裁到區界、半透明的主人色、內側一圈自己的色
    for (const c of d.cells) { if (hexTiles) break; const st = d.S[c.id] || {}; const sd = sideOf(d, c.id); const pp = poly(c.pts);
      const fill = st.tug ? `url(#stripe-${c.id})` : sd ? sd.color : "#D8D3C2"; const op = st.tug ? 0.5 : sd ? 0.36 : 0.16; const edge = sd ? sd.color : st.tug ? RED : "#8F8B82";
      g.push(`<g clip-path="url(#rg-${c.region})"><polygon points="${pp}" fill="${fill}" fill-opacity="${op}"/><g clip-path="url(#cp-${c.id})"><polygon points="${pp}" fill="none" stroke="${edge}" stroke-width="${sd || st.tug ? 5 : 2.5}" stroke-opacity="${sd || st.tug ? ".85" : ".5"}" vector-effect="non-scaling-stroke" stroke-linejoin="round"/></g><polygon points="${pp}" fill="none" stroke="${INK}" stroke-opacity=".35" stroke-width="1" vector-effect="non-scaling-stroke"/></g>`); }
    // 戰線：兩塊主人不同、相接的那一段邊
    const edges = {}; const key = (a, b) => { const p = `${a[0].toFixed(1)},${a[1].toFixed(1)}`, q2 = `${b[0].toFixed(1)},${b[1].toFixed(1)}`; return p < q2 ? `${p}|${q2}` : `${q2}|${p}`; };
    for (const c of d.cells) for (let i = 0; i < c.pts.length; i++) { const a = c.pts[i], b = c.pts[(i + 1) % c.pts.length]; const kk = key(a, b); (edges[kk] = edges[kk] || []).push({ c, a, b }); }
    for (const list of Object.values(edges)) if (list.length === 2 && !hexTiles) { const [u, v] = list; const ou = ownerOf(d, u.c.id), ov = ownerOf(d, v.c.id); if (ou && ov && ou !== ov)
      g.push(`<g clip-path="url(#rg-${u.c.region})"><path d="M${u.a[0]},${u.a[1]}L${u.b[0]},${u.b[1]}" stroke="#FFF6E0" stroke-width="3.2" vector-effect="non-scaling-stroke" stroke-linecap="round"/></g>`); }
    // 路：土路（深邊、淺心）
    for (const [a, b, cx, cy] of d.base.roads) { const pa = d.byId[a], pb = d.byId[b]; const dd = `M${pa.x},${pa.y}Q${cx},${cy} ${pb.x},${pb.y}`; g.push(`<path d="${dd}" fill="none" stroke="#4A4634" stroke-opacity=".55" stroke-width="3.2" vector-effect="non-scaling-stroke" stroke-linecap="round"/><path d="${dd}" fill="none" stroke="#D9C9A0" stroke-opacity=".9" stroke-width="1.3" vector-effect="non-scaling-stroke" stroke-linecap="round"/>`); }
    // 山、河的名字
    for (const t of d.terrainNames) g.push(`<text x="${t.x}" y="${t.y}" font-size="${(10.5 * k).toFixed(2)}" fill="#2A2E22" opacity=".7" font-weight="700" letter-spacing="${(1.5 * k).toFixed(2)}" style="font-family:${SANS}">${esc(t.t)}</text>`);
    // 可出陣：橘虛框（內側）；你的那一塊：紅框（內側）
    for (const c of d.cells) { const st = d.S[c.id] || {}; const pp = poly(c.pts);
      if (st.sortie) g.push(`<g clip-path="url(#rg-${c.region})"><g clip-path="url(#cp-${c.id})"><polygon points="${pp}" fill="none" stroke="${ORANGE}" stroke-width="6" stroke-dasharray="${(8 * k).toFixed(2)} ${(5 * k).toFixed(2)}" vector-effect="non-scaling-stroke" stroke-linejoin="round"/></g></g>`);
      if (c.id === d.here) g.push(`<g clip-path="url(#rg-${c.region})"><g clip-path="url(#cp-${c.id})"><polygon points="${pp}" fill="none" stroke="${RED}" stroke-width="6" vector-effect="non-scaling-stroke" stroke-linejoin="round"/></g></g>`); }
    return g.join("");
  }

  function iconPath(glyph) {
    switch (glyph) {
      case "城": return `<path d="M-7,5h14v-7h-2.5v-2.5h-2.5v2.5h-4v-2.5h-2.5v2.5h-2.5z" fill="${INK}"/><rect x="-1.5" y="1" width="3" height="4" fill="#fff"/>`;
      case "營": return `<path d="M-8,6L0,-6L8,6Z" fill="${INK}"/><path d="M0,-6v-3l4,1.2-4,1.3" fill="${RED}" stroke="${RED}" stroke-width=".6"/><path d="M-2,6l2,-4l2,4z" fill="#fff"/>`;
      case "山": return `<path d="M-9,6L-3,-3L0,1.5L3.5,-6L9,6Z" fill="${INK}"/><path d="M2.3,-3.5L3.5,-6L4.7,-3.5Z" fill="#fff"/>`;
      case "渡": return `<path d="M-8,1h16l-3.5,4.5h-9z" fill="${INK}"/><path d="M0,1v-7l5,5h-5" fill="${INK}"/><path d="M-9,7q2,-1.5 4,0t4,0t4,0t4,0" fill="none" stroke="${INK}" stroke-width="1.2"/>`;
      case "寺": return `<path d="M-9,-1L0,-8L9,-1Z" fill="${INK}"/><rect x="-5" y="-1" width="10" height="3" fill="${INK}"/><path d="M-7,3L0,-1.5L7,3Z" fill="${INK}"/><rect x="-4" y="3" width="8" height="3.5" fill="${INK}"/>`;
      default: return `<path d="M-6,6v-6M-2,6v-9M2,6v-7M6,6v-5" fill="none" stroke="${INK}" stroke-width="1.8" stroke-linecap="round"/><path d="M-8,6h16" stroke="${INK}" stroke-width="1.4" stroke-linecap="round"/>`;
    }
  }

  // 圖示在地圖座標那一層；名字在螢幕座標那一層（避讓用）
  function marksSvg(d, f, opts) {
    const g = [], labels = []; const k = f.k; const zoom = opts.zoom, pickId = opts.pick;
    const hot = (p, st) => (d.week && d.week.id === p.id) || st.rich || st.tug || p.id === pickId;
    const named = (p, st) => { const h = d.hops[p.id] ?? 99; return zoom === "far" ? false : h <= 2 || p.big || hot(p, st) || !!st.sortie; };
    const PS = pickId && d.S[pickId]; if (PS && PS.path) { const chain = [d.here, ...PS.path]; const segs = [];
      for (let i = 0; i + 1 < chain.length; i++) { const a = d.byId[chain[i]], b = d.byId[chain[i + 1]]; const c = d.roadOf[`${chain[i]}|${chain[i + 1]}`] || [(a.x + b.x) / 2, (a.y + b.y) / 2]; segs.push(`M${a.x},${a.y}Q${c[0]},${c[1]} ${b.x},${b.y}`); }
      g.push(`<path d="${segs.join("")}" fill="none" stroke="${INK}" stroke-width="6" stroke-opacity=".45" vector-effect="non-scaling-stroke" stroke-linecap="round"/><path d="${segs.join("")}" fill="none" stroke="#FFFFFF" stroke-width="3" vector-effect="non-scaling-stroke" stroke-linecap="round" stroke-dasharray="8 6"/>`); }
    const icons = [];
    for (const p of d.places) { const st = d.S[p.id] || {}; const isHere = p.id === d.here, isPick = p.id === pickId, isWeek = d.week && d.week.id === p.id;
      const px = f.X(p.x), py = f.Y(p.y); if (px < -40 || px > W + 40 || py < -40 || py > H + 40) continue;
      if (zoom === "far" && !p.big && !isHere && !hot(p, st)) { g.push(`<circle cx="${p.x}" cy="${p.y}" r="${(3 * k).toFixed(2)}" fill="#FFFDF7" stroke="${INK}" stroke-width="1" vector-effect="non-scaling-stroke"/>`); continue; }
      const sd = sideOf(d, p.id); const r = (zoom === "far" ? 7 : p.big ? 13 : 11) * (isPick ? 1.2 : 1); const sc = (r / 11) * k;
      icons.push({ x: px, y: py, r });
      g.push(`<g transform="translate(${p.x},${p.y}) scale(${sc.toFixed(4)})">`);
      g.push(`<circle r="12.5" fill="${INK}" opacity=".25" transform="translate(0,1.5)"/><circle r="11.5" fill="#FFFDF7" stroke="${isPick ? "#FFFFFF" : sd ? sd.color : "#8F8B82"}" stroke-width="${isPick ? 3 : 2.2}"/>`);
      g.push(iconPath(p.glyph));
      if (zoom !== "far" && !isHere) g.push(`<g transform="translate(9.5,9.5)"><circle r="5.8" fill="#2B2F25" stroke="#fff" stroke-width="1.1"/><text y="3" font-size="8.5" text-anchor="middle" fill="#fff" font-weight="700">${st.danger || 1}</text></g>`); // 危險度，像 SLG 的地等級
      if (st.tug || st.melee) g.push(`<g transform="translate(10,-9)"><circle r="6.5" fill="${RED}" stroke="#fff" stroke-width="1"/><path d="M-3,-3L3,3M3,-3L-3,3" stroke="#fff" stroke-width="1.6"/></g>`);
      if (st.rich) g.push(`<g transform="translate(-10,-9)"><path d="M-6,2l3,-4h6l3,4l-2,3h-8z" fill="#F2C94C" stroke="#7A5A14" stroke-width=".9"/></g>`);
      if (isWeek) g.push(`<path d="M0,-11v-20" stroke="${INK}" stroke-width="1.8"/><path d="M0,-31l15,5-15,5z" fill="${RED}" stroke="#7A1F18" stroke-width="1"/>`);
      if (isHere && !d.st.journey) g.push(`<circle r="18" fill="none" stroke="${RED}" stroke-width="2.2" opacity=".55"/><g transform="translate(0,-14)"><path d="M0,8C-9,-2 -9,-12 0,-12C9,-12 9,-2 0,8Z" fill="${RED}" stroke="#fff" stroke-width="1.6"/><text y="-2.5" font-size="10" text-anchor="middle" fill="#fff" font-weight="700">你</text></g>`);
      g.push(`</g>`);
      if (!named(p, st) && !isHere) continue;
      const near = (d.hops[p.id] ?? 99) <= 2 && !isHere; const name = p.name.replace(/（.*）/, "") + (near && st.minutes != null ? ` ${st.minutes}分` : "");
      const fs = zoom === "far" ? 11 : p.big ? 12.5 : 11.5;
      labels.push({ px, py, r, name, fs, w: name.length * fs * 0.92 + 6, h: fs + 4, isHere, pr: isHere ? 0 : (d.hops[p.id] ?? 99) <= 1 ? 1 : hot(p, st) ? 2 : 3 }); }
    // 名字避讓（螢幕座標）：下、上、右、左；不壓別的名字、圖示、邊上的箭頭牌，也不出畫面
    labels.sort((a, b) => a.pr - b.pr); const placed = [...(opts.blockers || [])];
    const hit = (rc) => rc.x - rc.w / 2 < 4 || rc.x + rc.w / 2 > W - 4 || rc.y - rc.h / 2 < TOPBAR || rc.y + rc.h / 2 > H - BOTBAR
      || placed.some((o) => Math.abs(o.x - rc.x) < (o.w + rc.w) / 2 && Math.abs(o.y - rc.y) < (o.h + rc.h) / 2) || icons.some((o) => Math.abs(o.x - rc.x) < (o.r + rc.w / 2) && Math.abs(o.y - rc.y) < (o.r + rc.h / 2));
    const L = [];
    for (const l of labels) { const c = [[0, l.r + l.h / 2 + 3], [0, -(l.r + l.h / 2 + 3) - (l.isHere ? 18 : 0)], [l.r + l.w / 2 + 4, 0], [-(l.r + l.w / 2 + 4), 0], [l.r + l.w / 2, l.r + 4], [-(l.r + l.w / 2), l.r + 4], [0, l.r + l.h * 1.5 + 5]];
      let ok = null; for (const [dx, dy] of c) { const rc = { x: l.px + dx, y: l.py + dy, w: l.w, h: l.h }; if (!hit(rc)) { ok = rc; break; } }
      if (!ok) { const rc = { x: Math.max(l.w / 2 + 4, Math.min(W - l.w / 2 - 4, l.px)), y: l.py + l.r + l.h / 2 + 3, w: l.w, h: l.h }; if (rc.y + rc.h / 2 > H - BOTBAR || rc.y - rc.h / 2 < TOPBAR) continue; ok = rc; } placed.push(ok);
      L.push(`<text x="${ok.x.toFixed(1)}" y="${(ok.y + l.fs * 0.36).toFixed(1)}" font-size="${l.fs}" text-anchor="middle" fill="${l.isHere ? "#FFE3DD" : "#FFFFFF"}" stroke="${INK}" stroke-width="3" paint-order="stroke" font-weight="700" stroke-linejoin="round">${esc(l.name)}</text>`); }
    // 在路上：紅釘畫在路上那一點，到要去的那一站畫一條虛線，釘子旁寫還有幾分
    const J = d.st.journey;
    if (J && J.x != null) { const to = d.byId[J.to]; const k2 = k;
      if (to) g.push(`<path d="M${J.x},${J.y}L${to.x},${to.y}" fill="none" stroke="#FFFFFF" stroke-width="3" vector-effect="non-scaling-stroke" stroke-linecap="round" stroke-dasharray="8 6" opacity=".9"/>`);
      g.push(`<g transform="translate(${J.x},${J.y}) scale(${k2.toFixed(4)})"><circle r="16" fill="none" stroke="${RED}" stroke-width="2.2" opacity=".55"/><circle r="5" fill="${RED}" stroke="#fff" stroke-width="1.5"/><g transform="translate(0,-14)"><path d="M0,8C-9,-2 -9,-12 0,-12C9,-12 9,-2 0,8Z" fill="${RED}" stroke="#fff" stroke-width="1.6"/><text y="-2.5" font-size="10" text-anchor="middle" fill="#fff" font-weight="700">你</text></g></g>`);
      if (zoom !== "far") L.push(`<text x="${(f.X(J.x) + 22).toFixed(1)}" y="${(f.Y(J.y) + 4).toFixed(1)}" font-size="11.5" fill="#FFE3DD" stroke="${INK}" stroke-width="3" paint-order="stroke" font-weight="700">→ ${esc(J.to_name || "")}・還有 ${J.minutes ?? "?"} 分</text>`); }
    if (zoom === "far") for (const r of d.base.regions) L.push(`<text x="${f.X(r.cx).toFixed(1)}" y="${(f.Y(r.cy) - 26).toFixed(1)}" font-size="18" text-anchor="middle" fill="#FFFFFF" stroke="${INK}" stroke-width="4" paint-order="stroke" font-weight="700" opacity=".92" letter-spacing="2">${esc(r.name)}</text>`);
    return { marks: g.join(""), labels: L.join("") };
  }

  // 框外還走得到的：畫面邊緣掛箭頭牌
  function edgePills(d, f) {
    const out = [], rects = []; const hx = f.X(d.hp.x), hy = f.Y(d.hp.y);
    // 框內的圖示當障礙：牌子沿著邊滑，別壓到
    const icons = d.places.map((p) => ({ x: f.X(p.x), y: f.Y(p.y), r: 16 })).filter((o) => o.x > -20 && o.x < W + 20 && o.y > 0 && o.y < H);
    for (const id of Object.keys(d.hops)) { if (d.hops[id] !== 1) continue; const p = d.byId[id]; const px = f.X(p.x), py = f.Y(p.y);
      if (px > -6 && px < W + 6 && py > TOPBAR - 6 && py < H - BOTBAR + 6) continue; // 圖示還看得到一半就不掛牌（名字會夾回畫面裡）
      const st = d.S[id] || {}; const dx = px - hx, dy = py - hy, L = Math.hypot(dx, dy) || 1, ux = dx / L, uy = dy / L;
      let t = Infinity; if (ux > 0) t = Math.min(t, (W - 16 - hx) / ux); if (ux < 0) t = Math.min(t, (16 - hx) / ux); if (uy > 0) t = Math.min(t, (H - BOTBAR - 16 - hy) / uy); if (uy < 0) t = Math.min(t, (TOPBAR + 16 - hy) / uy);
      const x = hx + ux * t, y = hy + uy * t; const label = `${p.name.replace(/（.*）/, "")} ${st.minutes ?? "?"}分`; const w = label.length * 11 + 22, h = 24;
      const horiz = Math.abs(ux) >= Math.abs(uy); // 貼左右邊的牌子上下滑，貼上下邊的左右滑
      let cx = Math.max(w / 2 + 6, Math.min(W - w / 2 - 6, x)), cy = Math.max(TOPBAR + 14, Math.min(H - BOTBAR - 14, y));
      const clash = () => rects.some((o) => Math.abs(o.x - cx) < (o.w + w) / 2 && Math.abs(o.y - cy) < (o.h + h) / 2) || icons.some((o) => Math.abs(o.x - cx) < o.r + w / 2 && Math.abs(o.y - cy) < o.r + h / 2);
      for (let i = 1; i <= 12 && clash(); i++) { const step = (i % 2 ? 1 : -1) * Math.ceil(i / 2) * 26; if (horiz) cy = Math.max(TOPBAR + 14, Math.min(H - BOTBAR - 14, y + step)); else cx = Math.max(w / 2 + 6, Math.min(W - w / 2 - 6, x + step)); }
      rects.push({ x: cx, y: cy, w, h });
      const arrow = horiz ? (ux > 0 ? "›" : "‹") : uy > 0 ? "⌄" : "⌃"; const left = horiz && ux < 0;
      out.push(`<div style="position:absolute;left:${(cx - w / 2).toFixed(0)}px;top:${(cy - 12).toFixed(0)}px;width:${w}px;height:${h}px;border-radius:12px;background:rgba(20,24,18,.82);border:1px solid rgba(255,255,255,.25);color:#F4F1E8;font-size:12px;font-weight:700;display:flex;align-items:center;justify-content:center;gap:4px">${left ? `<span style="color:${ORANGE}">${arrow}</span>` : ""}${esc(label)}${!left ? `<span style="color:${ORANGE}">${arrow}</span>` : ""}</div>`); }
    return { html: out.join(""), rects };
  }

  const chip = (txt) => `<div style="background:rgba(20,24,18,.80);color:#F4F1E8;border:1px solid rgba(255,255,255,.18);border-radius:6px;padding:6px 10px;font-size:14px;font-weight:600">${txt}</div>`;
  const roundBtn = (txt, on) => `<div style="width:44px;height:44px;border-radius:50%;background:rgba(20,24,18,.84);color:${on ? ORANGE : "#F4F1E8"};border:1px solid ${on ? ORANGE : "rgba(255,255,255,.22)"};display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;box-shadow:0 2px 6px rgba(0,0,0,.35)">${txt}</div>`;
  // 右上角的小地圖：整個天下，每一塊地照主人上色、區界、現在看的框、你
  function minimap(d, f) {
    const [fx0, fy0, fx1, fy1] = d.frame; const mw = W < 360 ? 64 : 100, mh = Math.round(mw * (fy1 - fy0) / (fx1 - fx0)); // 窄螢幕小地圖縮小
    const cells = [...d.cells].sort((a, b) => { const area = (c) => { let s = 0; for (let i = 0; i < c.pts.length; i++) { const [x1, y1] = c.pts[i], [x2, y2] = c.pts[(i + 1) % c.pts.length]; s += x1 * y2 - x2 * y1; } return Math.abs(s); }; return area(b) - area(a); });
    const body = cells.map((c) => { const sd = sideOf(d, c.id); return `<g clip-path="url(#rg-${c.region})"><polygon points="${poly(c.pts)}" fill="${sd ? sd.color : "#C9C2AE"}" fill-opacity="${sd ? ".85" : ".4"}"/></g>`; }).join("")
      + d.regions.map((r) => `<polygon points="${poly(r.pts)}" fill="none" stroke="#1B1F17" stroke-opacity=".6" stroke-width="${((fx1 - fx0) / mw).toFixed(1)}"/>`).join("");
    const vx = -parseFloat(f.tr.match(/translate\(([-\d.]+)/)[1]) / f.s, vy = -parseFloat(f.tr.match(/translate\([-\d.]+,([-\d.]+)/)[1]) / f.s;
    const frameRect = `<rect x="${vx}" y="${vy}" width="${W / f.s}" height="${H / f.s}" fill="#fff" fill-opacity=".12" stroke="#fff" stroke-width="${((fx1 - fx0) / mw * 1.5).toFixed(1)}"/>`;
    const you = `<circle cx="${d.hp.x}" cy="${d.hp.y}" r="${((fx1 - fx0) / mw * 4).toFixed(1)}" fill="${RED}" stroke="#fff" stroke-width="${((fx1 - fx0) / mw * 1.5).toFixed(1)}"/>`;
    return `<div style="position:absolute;right:10px;top:62px;width:${mw}px;height:${mh}px;border-radius:6px;overflow:hidden;border:1px solid rgba(255,255,255,.3);box-shadow:0 2px 6px rgba(0,0,0,.35);background:${LAND_DARK}"><svg width="${mw}" height="${mh}" viewBox="${fx0} ${fy0} ${fx1 - fx0} ${fy1 - fy0}" preserveAspectRatio="none"><rect x="${fx0}" y="${fy0}" width="${fx1 - fx0}" height="${fy1 - fy0}" fill="${LAND}"/>${body}${frameRect}${you}</svg></div>`;
  }
  function hud(d, zoom, f) {
    const sortieN = Object.values(d.S).filter((s) => s.sortie).length; const wk = d.week && d.byId[d.week.id]; const ws = wk && (d.S[wk.id] || {});
    return `<div style="position:absolute;left:10px;top:10px">${chip(`${esc(d.base.regions.find((r) => r.id === d.rid).name)} ▾`)}</div><div style="position:absolute;right:10px;top:10px">${roundBtn("🔍")}</div>${zoom === "near" ? minimap(d, f) : ""}
      <div style="position:absolute;right:10px;bottom:70px;display:flex;flex-direction:column;gap:8px">${roundBtn("⌖", zoom === "near")}${roundBtn("天下", zoom === "far")}</div>
      <div style="position:absolute;left:10px;right:10px;bottom:10px;background:rgba(20,24,18,.86);color:#F4F1E8;border:1px solid rgba(255,255,255,.16);border-radius:8px;padding:8px 12px;display:flex;justify-content:space-between;align-items:center;font-size:13px"><div>${d.st.journey ? `<span style="background:${ORANGE};color:${INK};border-radius:3px;padding:1px 5px;font-size:11px;margin-right:6px;font-weight:700">在路上</span><b style="font-size:15px">→ ${esc(d.st.journey.to_name || "")}</b> <span style="color:#C9C4B6">還有 ${d.st.journey.minutes ?? ""} 分${d.st.journey.next_name ? "・下一站 " + esc(d.st.journey.next_name) : ""}</span>` : wk ? `<span style="background:${RED};color:#fff;border-radius:3px;padding:1px 5px;font-size:11px;margin-right:6px">本週</span><b style="font-size:15px">${esc(wk.name.replace(/（.*）/, ""))}</b> <span style="color:#C9C4B6;font-size:${W < 360 ? 11.5 : 13}px">${esc(W < 360 ? ((d.week.why || "").split("・")[1] || "") : (d.week.why || "").split("・").slice(1).join("・"))}・${ws.minutes ?? ""} 分</span>` : "本週沒有軍令"}</div><div style="color:${ORANGE};font-weight:700;white-space:nowrap;font-size:${W < 360 ? 12 : 13}px">${d.st.journey ? "沿路做小事 ›" : `可出陣 ${sortieN} ›`}</div></div>`;
  }
  function card(d, id) {
    const p = d.byId[id], s = d.S[id] || {}; const sd = sideOf(d, id); const stars = "★".repeat(s.danger || 1) + "☆".repeat(3 - (s.danger || 1));
    const btn = (t, sub, bg, fg = "#fff") => `<div style="flex:1;background:${bg};color:${fg};border-radius:6px;padding:7px 4px;text-align:center"><div style="font-size:15px;font-weight:700">${t}</div><div style="font-size:11px;opacity:.85">${sub}</div></div>`;
    const squads = (s.squads || []).map((q) => `${esc(q.name)} <span style="color:#C9C4B6">${esc(q.odds)}</span>`).join("、") || "—";
    return `<div style="position:absolute;left:0;right:0;bottom:0;background:rgba(20,24,18,.92);color:#F4F1E8;border-top:1px solid rgba(255,255,255,.18);border-radius:12px 12px 0 0;padding:12px 14px 12px"><div style="position:absolute;right:12px;top:10px;color:#C9C4B6;font-size:16px">✕</div>
      <div style="font-size:19px;font-weight:700">${esc(p.name)}<span style="display:inline-block;background:${sd ? sd.color : s.tug ? RED : "#8F8B82"};color:#fff;border-radius:3px;padding:1px 6px;font-size:11px;margin-left:6px;vertical-align:2px">${sd ? sd.name + "地" : s.tug ? "正在翻" : "無主"}</span><span style="font-size:12px;color:${ORANGE};margin-left:8px">危 ${stars}</span></div>
      <div style="font-size:12.5px;color:#C9C4B6;margin-top:3px">${esc(p.terrain || "")}・${esc(p.mostly || "")}${s.odds ? "・勝算 " + esc(s.odds.word) : ""}${s.yield ? "・" + esc(s.yield) : ""}</div>
      <div style="display:flex;gap:8px;margin-top:10px">${btn(`步行 ${s.minutes ?? ""} 分`, "沿路可以做小事", ORANGE, INK)}${btn("疾行", `立刻到・體力 ${s.stamina ?? ""}`, "rgba(255,255,255,.12)")}${s.sortie ? btn("出陣", "攻這一塊", RED) : ""}</div>
      <div style="font-size:12.5px;margin-top:10px"><span style="color:#C9C4B6">守軍</span>　${squads}</div>${(s.people || []).length ? `<div style="font-size:12.5px;margin-top:3px"><span style="color:#C9C4B6">人物</span>　${s.people.map(esc).join("、")}</div>` : ""}</div>`;
  }

  function draw(d, zoom, pickId, tiles) {
    const f = view(d, zoom, pickId);
    const pills = zoom === "near" && !pickId && !d.st.journey ? edgePills(d, f) : { html: "", rects: [] }; // 在路上不掛箭頭牌
    const m = marksSvg(d, f, { zoom, pick: pickId, blockers: pills.rects });
    const svg = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" style="display:block;position:absolute;inset:0"><g transform="${f.tr}">${groundSvg(d, f, { tiles })}${m.marks}</g><g>${m.labels}</g><rect width="${W}" height="${H}" filter="url(#grain)" pointer-events="none"/></svg>`;
    return `<div style="position:relative;width:${W}px;height:${H}px">${svg}${pills.html}${pickId ? card(d, pickId) + `<div style="position:absolute;left:10px;top:10px">${chip(`${esc(d.base.regions.find((r) => r.id === d.rid).name)} ▾`)}</div>` : hud(d, zoom, f)}</div>`;
  }
  window.txSlg4 = async (zoom, pickId, tiles) => { W = document.documentElement.clientWidth; H = Math.round(document.querySelector(".tabs").getBoundingClientRect().top - document.querySelector("#map").getBoundingClientRect().top); const d = await data(); mount(draw(d, zoom || "near", pickId, tiles || "plate")); return { zoom, pickId, tiles, W, H }; };
})();
