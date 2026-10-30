// 輿圖風格草圖（第 7 輪）：企劃者看了第 6 輪戰略圖說「有接近了一點再改」。第 6 輪的甲（勢力色塊）再磨：
// 1. 地塊不再是整塊 Voronoi（邊上的一塊大到半個天下）：每一處只佔地點周圍一片（地塊 ∩ 半徑 R 的圓），同一方相鄰的片連成一片、不同方相接就是戰線；
// 2. 地點不再是白圓＋一個字：畫成小圖示（城牆、營帳、山、渡船、寺、草），白圓底、邊圈是歸屬色；
// 3. 山水畫扣一點：山有陰陽面、林是真的樹（底圖的 161 棵）、河有深邊淺心、黃河土黃；地有明暗；
// 4. 打開拉近：只框腳下一步＋你，兩步的在邊上露一點；名字照縮放露。
// 用法：txSlg2('near'|'far', 點的地點 id)；txSlg2Off() 還原。只是草圖。
(() => {
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const W = 375, H = 667;
  const RED = "#C0392B", ORANGE = "#F0A640", INK = "#1B1F17";
  const LAND = "#8F9B6C", LAND_LIGHT = "#A8B07F", LAND_DARK = "#66704D", WATER_EDGE = "#3F6D8C", WATER = "#78A9C4", YELLOW_R = "#C9A867", YELLOW_R2 = "#E2CB94";
  const MTN_LIGHT = "#9A9573", MTN_DARK = "#5E5A3F", TREE = "#55693F", TREE2 = "#7FA36A";
  const SANS = '-apple-system,"PingFang TC","Noto Sans TC","Microsoft JhengHei",sans-serif';
  const R_PATCH = 78, R_BIG = 92; // 每一處佔地的半徑（地圖單位）

  async function data() {
    const [base, st] = await Promise.all([fetch("/api/map/base").then((r) => r.json()), fetch("/api/map/state").then((r) => r.json())]);
    const places = Object.values(base.places); const byId = Object.fromEntries(places.map((p) => [p.id, p]));
    const here = st.here, hp = byId[here], rid = hp.region;
    const toPts = (dstr) => { const n = dstr.replace(/[MLZ]/g, " ").trim().split(/\s+/).map(Number); const o = []; for (let i = 0; i < n.length; i += 2) o.push([n[i], n[i + 1]]); return o; };
    const sides = Object.fromEntries(base.world.sides.map((s) => [s.id, s]));
    const cells = base.world.cells.map((c) => ({ ...c, pts: toPts(c.d) })).filter((c) => byId[c.id]);
    const adj = {}; for (const [a, b] of base.edges) { (adj[a] = adj[a] || []).push(b); (adj[b] = adj[b] || []).push(a); }
    const hops = { [here]: 0 }; const q = [here]; while (q.length) { const u = q.shift(); for (const v of adj[u] || []) if (!(v in hops)) { hops[v] = hops[u] + 1; q.push(v); } }
    const doc = new DOMParser().parseFromString(base.svg, "image/svg+xml");
    const center = (el) => { const n = (el.getAttribute("d") || "").match(/-?\d+(\.\d+)?/g); if (!n || n.length < 4) return null; let sx = 0, sy = 0, k = 0; for (let i = 0; i + 1 < n.length; i += 2) { sx += +n[i]; sy += +n[i + 1]; k++; } return [sx / k, sy / k]; };
    const peaks = [...doc.querySelectorAll('[fill="#557D69"]')].map(center).filter(Boolean);
    const trees = [...doc.querySelectorAll('circle[fill="#7FA36A"]')].map((c) => [+c.getAttribute("cx"), +c.getAttribute("cy"), +c.getAttribute("r")]);
    const rivers = [...doc.querySelectorAll('path[stroke="#6FA0C2"]')].map((p) => p.getAttribute("d")).filter((d) => d && d.length > 20);
    const yellow = [...doc.querySelectorAll('path[stroke="#C9A867"]')].map((p) => p.getAttribute("d")).filter((d) => d && d.length > 20);
    const roadOf = {}; for (const [a, b, cx, cy] of base.roads) { roadOf[`${a}|${b}`] = [cx, cy]; roadOf[`${b}|${a}`] = [cx, cy]; }
    return { base, st, places, byId, here, hp, rid, sides, cells, hops, peaks, trees, rivers, yellow, roadOf, S: st.places, week: st.week, frame: base.world.frame };
  }

  function fitter(pts, pad, top, bottom, frame) {
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
    const x0 = Math.min(...xs) - pad, x1 = Math.max(...xs) + pad, y0 = Math.min(...ys) - pad, y1 = Math.max(...ys) + pad;
    let s = Math.min((W - 16) / (x1 - x0), (bottom - top) / (y1 - y0));
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2; let vx0 = cx - (W / 2) / s, vy0 = cy - ((top + bottom) / 2) / s;
    if (frame) { const [fx0, fy0, fx1, fy1] = frame; s = Math.max(s, W / (fx1 - fx0), H / (fy1 - fy0)); vx0 = cx - (W / 2) / s; vy0 = cy - ((top + bottom) / 2) / s; vx0 = Math.max(fx0, Math.min(fx1 - W / s, vx0)); vy0 = Math.max(fy0, Math.min(fy1 - H / s, vy0)); }
    return { s, k: 1 / s, X: (x) => (x - vx0) * s, Y: (y) => (y - vy0) * s, tr: `translate(${(-vx0 * s).toFixed(2)},${(-vy0 * s).toFixed(2)}) scale(${s.toFixed(4)})` };
  }

  function mount(html) {
    txSlg2Off();
    const map = document.querySelector("#map"); const top = map.getBoundingClientRect().top; const tabsTop = document.querySelector(".tabs").getBoundingClientRect().top;
    const box = document.createElement("div"); box.id = "tx-mock";
    box.style.cssText = `position:fixed;left:0;right:0;top:${Math.round(top)}px;bottom:${Math.round(innerHeight - tabsTop)}px;z-index:950;overflow:hidden;background:${LAND};font-family:${SANS}`;
    box.innerHTML = html; document.body.appendChild(box);
    const rt = document.querySelector(".r-top"); if (rt) rt.style.visibility = "hidden";
  }
  window.txSlg2Off = () => { document.querySelector("#tx-mock")?.remove(); const rt = document.querySelector(".r-top"); if (rt) rt.style.visibility = ""; };

  const ownerOf = (d, id) => (d.S[id] || {}).control || null;
  const sideOf = (d, id) => { const o = ownerOf(d, id); return o && d.sides[o] ? d.sides[o] : null; };

  // 地：明暗、山（陰陽面）、林、河；每一處一片佔地
  function groundSvg(d, f) {
    const g = []; const k = f.k; const [fx0, fy0, fx1, fy1] = d.frame;
    g.push(`<defs><radialGradient id="landg" cx="50%" cy="45%" r="70%"><stop offset="0" stop-color="${LAND_LIGHT}"/><stop offset="1" stop-color="${LAND}"/></radialGradient><filter id="soft" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="${(4 * k).toFixed(2)}"/></filter><filter id="grain" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="1.3" numOctaves="1" seed="4"/><feColorMatrix values="0 0 0 0 0.1 0 0 0 0 0.12 0 0 0 0 0.05 0 0 0 0.06 0"/></filter>`);
    for (const c of d.cells) g.push(`<clipPath id="cp-${c.id}"><polygon points="${c.pts.map((p) => p.join(",")).join(" ")}"/></clipPath>`);
    for (const c of d.cells) { const st = d.S[c.id] || {}; if (!st.tug) continue; const side = Object.keys(st.tug)[0]; const a = d.sides[side] ? d.sides[side].color : "#B9B49E", b = sideOf(d, c.id) ? sideOf(d, c.id).color : "#B9B49E";
      g.push(`<pattern id="stripe-${c.id}" patternUnits="userSpaceOnUse" width="${(10 * k).toFixed(2)}" height="${(10 * k).toFixed(2)}" patternTransform="rotate(45)"><rect width="${(5 * k).toFixed(2)}" height="${(10 * k).toFixed(2)}" fill="${a}"/><rect x="${(5 * k).toFixed(2)}" width="${(5 * k).toFixed(2)}" height="${(10 * k).toFixed(2)}" fill="${b}"/></pattern>`); }
    g.push(`</defs>`);
    g.push(`<rect x="${fx0 - 3000}" y="${fy0 - 3000}" width="${fx1 - fx0 + 6000}" height="${fy1 - fy0 + 6000}" fill="${LAND_DARK}"/><rect x="${fx0}" y="${fy0}" width="${fx1 - fx0}" height="${fy1 - fy0}" fill="url(#landg)"/>`);
    // 林：底圖的樹，兩層
    for (const [x, y, r] of d.trees) g.push(`<circle cx="${x}" cy="${y + 1.2}" r="${r}" fill="${INK}" opacity=".18"/><circle cx="${x}" cy="${y}" r="${r}" fill="${TREE}"/><circle cx="${x - r * 0.25}" cy="${y - r * 0.3}" r="${r * 0.55}" fill="${TREE2}" opacity=".8"/>`);
    // 山：陰陽面
    for (const [x, y] of d.peaks) g.push(`<ellipse cx="${x}" cy="${y + 4}" rx="16" ry="7" fill="${INK}" opacity=".16" filter="url(#soft)"/>`);
    for (const [x, y] of d.peaks) g.push(`<path d="M${x - 11},${y + 6}L${x},${y - 9}L${x + 1.5},${y + 6}Z" fill="${MTN_LIGHT}"/><path d="M${x},${y - 9}L${x + 11},${y + 6}L${x + 1.5},${y + 6}Z" fill="${MTN_DARK}"/><path d="M${x - 2.5},${y - 5.5}L${x},${y - 9}L${x + 2.5},${y - 5.5}Z" fill="#F2F0E6" opacity=".8"/>`);
    // 河：深邊淺心；黃河土黃
    for (const dd of d.rivers) g.push(`<path d="${dd}" fill="none" stroke="${WATER_EDGE}" stroke-width="5.5" vector-effect="non-scaling-stroke" stroke-linejoin="round" stroke-linecap="round"/><path d="${dd}" fill="none" stroke="${WATER}" stroke-width="2.6" vector-effect="non-scaling-stroke" stroke-linejoin="round" stroke-linecap="round"/>`);
    for (const dd of d.yellow) g.push(`<path d="${dd}" fill="none" stroke="${YELLOW_R}" stroke-width="7" vector-effect="non-scaling-stroke" stroke-linejoin="round"/><path d="${dd}" fill="none" stroke="${YELLOW_R2}" stroke-width="3" vector-effect="non-scaling-stroke" stroke-linejoin="round"/>`);
    // 佔地：每一處一片（地塊 ∩ 圓），同一方相鄰自然連成一片
    for (const c of d.cells) { const p = d.byId[c.id]; const st = d.S[c.id] || {}; const sd = sideOf(d, c.id); const R = p.big ? R_BIG : R_PATCH;
      if (!sd && !st.tug) { g.push(`<circle cx="${p.x}" cy="${p.y}" r="${R * 0.8}" fill="#D8D3C2" fill-opacity=".22" clip-path="url(#cp-${c.id})"/>`); continue; }
      const fill = st.tug ? `url(#stripe-${c.id})` : sd.color;
      g.push(`<circle cx="${p.x}" cy="${p.y}" r="${R}" fill="${fill}" fill-opacity="${st.tug ? ".55" : ".40"}" clip-path="url(#cp-${c.id})"/>`);
      g.push(`<circle cx="${p.x}" cy="${p.y}" r="${R - 1}" fill="none" stroke="${sd ? sd.color : RED}" stroke-width="2" vector-effect="non-scaling-stroke" opacity=".9" clip-path="url(#cp-${c.id})"/>`); }
    // 兩塊佔地相接、主人不同：那一條邊畫亮（戰線）
    const edges = {}; const key = (a, b) => { const p = `${a[0].toFixed(1)},${a[1].toFixed(1)}`, q2 = `${b[0].toFixed(1)},${b[1].toFixed(1)}`; return p < q2 ? `${p}|${q2}` : `${q2}|${p}`; };
    for (const c of d.cells) for (let i = 0; i < c.pts.length; i++) { const a = c.pts[i], b = c.pts[(i + 1) % c.pts.length]; const kk = key(a, b); (edges[kk] = edges[kk] || []).push({ c, a, b }); }
    for (const list of Object.values(edges)) if (list.length === 2) { const [u, v] = list; const ou = ownerOf(d, u.c.id), ov = ownerOf(d, v.c.id); if (ou && ov && ou !== ov) { const pu = d.byId[u.c.id], pv = d.byId[v.c.id];
      // 只畫兩片佔地都碰得到的那一段：用兩個圓的 clip 疊
      g.push(`<g clip-path="url(#cpc-${u.c.id})"><g clip-path="url(#cpc-${v.c.id})"><path d="M${u.a[0]},${u.a[1]}L${u.b[0]},${u.b[1]}" stroke="#FFF6E0" stroke-width="3" vector-effect="non-scaling-stroke" stroke-linecap="round"/></g></g>`); } }
    // 路：淡
    for (const [a, b, cx, cy] of d.base.roads) { const pa = d.byId[a], pb = d.byId[b]; g.push(`<path d="M${pa.x},${pa.y}Q${cx},${cy} ${pb.x},${pb.y}" fill="none" stroke="#5A5440" stroke-opacity=".45" stroke-width="1.2" vector-effect="non-scaling-stroke" stroke-dasharray="${(4 * k).toFixed(2)} ${(3 * k).toFixed(2)}"/>`); }
    // 可出陣：橘虛框（照佔地那一片）；你的那一片：紅框
    for (const c of d.cells) { const p = d.byId[c.id]; const st = d.S[c.id] || {}; const R = p.big ? R_BIG : R_PATCH;
      if (st.sortie) g.push(`<circle cx="${p.x}" cy="${p.y}" r="${R - 2}" fill="none" stroke="${ORANGE}" stroke-width="2.6" stroke-dasharray="${(7 * k).toFixed(2)} ${(5 * k).toFixed(2)}" vector-effect="non-scaling-stroke" clip-path="url(#cp-${c.id})"/><polygon points="${c.pts.map((q) => q.join(",")).join(" ")}" fill="none" stroke="${ORANGE}" stroke-width="2.6" stroke-dasharray="${(7 * k).toFixed(2)} ${(5 * k).toFixed(2)}" vector-effect="non-scaling-stroke" clip-path="url(#cpc-${c.id})"/>`);
      if (c.id === d.here) g.push(`<circle cx="${p.x}" cy="${p.y}" r="${R - 2}" fill="none" stroke="${RED}" stroke-width="2.6" vector-effect="non-scaling-stroke" clip-path="url(#cp-${c.id})"/>`); }
    return g.join("");
  }

  // 圖示：城牆、營帳、山、渡船、寺、草
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

  function marksSvg(d, f, opts) {
    const g = []; const k = f.k; const zoom = opts.zoom, pickId = opts.pick;
    const hot = (p, st) => (d.week && d.week.id === p.id) || st.rich || st.tug || p.id === pickId;
    const named = (p, st) => { const h = d.hops[p.id] ?? 99; return zoom === "far" ? false : h <= 2 || p.big || hot(p, st) || !!st.sortie; };
    const PS = pickId && d.S[pickId]; if (PS && PS.path) { const chain = [d.here, ...PS.path]; const segs = [];
      for (let i = 0; i + 1 < chain.length; i++) { const a = d.byId[chain[i]], b = d.byId[chain[i + 1]]; const c = d.roadOf[`${chain[i]}|${chain[i + 1]}`] || [(a.x + b.x) / 2, (a.y + b.y) / 2]; segs.push(`M${a.x},${a.y}Q${c[0]},${c[1]} ${b.x},${b.y}`); }
      g.push(`<path d="${segs.join("")}" fill="none" stroke="${INK}" stroke-width="6" stroke-opacity=".45" vector-effect="non-scaling-stroke" stroke-linecap="round"/><path d="${segs.join("")}" fill="none" stroke="#FFFFFF" stroke-width="3" vector-effect="non-scaling-stroke" stroke-linecap="round" stroke-dasharray="8 6"/>`); }
    for (const p of d.places) { const st = d.S[p.id] || {}; const isHere = p.id === d.here, isPick = p.id === pickId, isWeek = d.week && d.week.id === p.id;
      if (zoom === "far" && !p.big && !isHere && !hot(p, st)) { g.push(`<circle cx="${p.x}" cy="${p.y}" r="${(3 * k).toFixed(2)}" fill="#FFFDF7" stroke="${INK}" stroke-width="1" vector-effect="non-scaling-stroke"/>`); continue; }
      const sd = sideOf(d, p.id); const r = (zoom === "far" ? 7 : p.big ? 13 : 11) * (isPick ? 1.2 : 1); const sc = (r / 11) * k;
      g.push(`<g transform="translate(${p.x},${p.y}) scale(${sc.toFixed(4)})">`);
      g.push(`<circle r="12.5" fill="${INK}" opacity=".25" transform="translate(0,1.5)"/><circle r="11.5" fill="#FFFDF7" stroke="${isPick ? "#FFFFFF" : sd ? sd.color : "#8F8B82"}" stroke-width="${isPick ? 3 : 2.2}"/>`);
      g.push(iconPath(p.glyph));
      if (st.tug || st.melee) g.push(`<g transform="translate(10,-9)"><circle r="6.5" fill="${RED}" stroke="#fff" stroke-width="1"/><path d="M-3,-3L3,3M3,-3L-3,3" stroke="#fff" stroke-width="1.6"/></g>`);
      if (st.rich) g.push(`<g transform="translate(-10,-9)"><path d="M-6,2l3,-4h6l3,4l-2,3h-8z" fill="#F2C94C" stroke="#7A5A14" stroke-width=".9"/></g>`);
      if (isWeek) g.push(`<path d="M0,-11v-20" stroke="${INK}" stroke-width="1.8"/><path d="M0,-31l15,5-15,5z" fill="${RED}" stroke="#7A1F18" stroke-width="1"/>`);
      if (isHere) g.push(`<circle r="18" fill="none" stroke="${RED}" stroke-width="2.2" opacity=".55"/><g transform="translate(0,-14)"><path d="M0,8C-9,-2 -9,-12 0,-12C9,-12 9,-2 0,8Z" fill="${RED}" stroke="#fff" stroke-width="1.6"/><text y="-2.5" font-size="10" text-anchor="middle" fill="#fff" font-weight="700">你</text></g>`);
      g.push(`</g>`);
      if (!named(p, st) && !isHere) continue;
      const near = (d.hops[p.id] ?? 99) <= 2 && !isHere; const name = p.name.replace(/（.*）/, "") + (near && st.minutes != null ? ` ${st.minutes}分` : "");
      const fs = (zoom === "far" ? 11 : p.big ? 12.5 : 11.5) * k;
      g.push(`<text x="${p.x}" y="${p.y + r * k + fs * 1.1}" font-size="${fs.toFixed(2)}" text-anchor="middle" fill="${isHere ? "#FFE3DD" : "#FFFFFF"}" stroke="${INK}" stroke-width="${(3 * k).toFixed(2)}" paint-order="stroke" font-weight="700" stroke-linejoin="round">${esc(name)}</text>`); }
    if (zoom === "far") for (const r of d.base.regions) g.push(`<text x="${r.cx}" y="${r.cy - 30}" font-size="${(18 * k).toFixed(2)}" text-anchor="middle" fill="#FFFFFF" stroke="${INK}" stroke-width="${(4 * k).toFixed(2)}" paint-order="stroke" font-weight="700" opacity=".92" letter-spacing="${(2 * k).toFixed(2)}">${esc(r.name)}</text>`);
    return g.join("");
  }

  const chip = (txt) => `<div style="background:rgba(20,24,18,.80);color:#F4F1E8;border:1px solid rgba(255,255,255,.18);border-radius:6px;padding:6px 10px;font-size:14px;font-weight:600">${txt}</div>`;
  const roundBtn = (txt, on) => `<div style="width:44px;height:44px;border-radius:50%;background:rgba(20,24,18,.84);color:${on ? ORANGE : "#F4F1E8"};border:1px solid ${on ? ORANGE : "rgba(255,255,255,.22)"};display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;box-shadow:0 2px 6px rgba(0,0,0,.35)">${txt}</div>`;
  function hud(d, zoom) {
    const sortieN = Object.values(d.S).filter((s) => s.sortie).length; const wk = d.week && d.byId[d.week.id]; const ws = wk && (d.S[wk.id] || {});
    return `<div style="position:absolute;left:10px;top:10px">${chip(`${esc(d.base.regions.find((r) => r.id === d.rid).name)} ▾`)}</div><div style="position:absolute;right:10px;top:10px">${roundBtn("🔍")}</div>
      <div style="position:absolute;right:10px;bottom:70px;display:flex;flex-direction:column;gap:8px">${roundBtn("⌖", zoom === "near")}${roundBtn("天下", zoom === "far")}</div>
      <div style="position:absolute;left:10px;right:10px;bottom:10px;background:rgba(20,24,18,.86);color:#F4F1E8;border:1px solid rgba(255,255,255,.16);border-radius:8px;padding:8px 12px;display:flex;justify-content:space-between;align-items:center;font-size:13px"><div>${wk ? `<span style="background:${RED};color:#fff;border-radius:3px;padding:1px 5px;font-size:11px;margin-right:6px">本週</span><b style="font-size:15px">${esc(wk.name.replace(/（.*）/, ""))}</b> <span style="color:#C9C4B6">${esc((d.week.why || "").split("・").slice(1).join("・"))}・步行 ${ws.minutes ?? ""} 分</span>` : "本週沒有軍令"}</div><div style="color:${ORANGE};font-weight:700;white-space:nowrap">可出陣 ${sortieN} ›</div></div>`;
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

  function draw(d, zoom, pickId) {
    let f;
    if (zoom === "far") f = fitter([[d.frame[0], d.frame[1]], [d.frame[2], d.frame[3]]], 20, 64, H - 70, null);
    else { const pts = d.places.filter((p) => (d.hops[p.id] ?? 99) <= 1 || p.id === pickId).map((p) => [p.x, p.y]); f = fitter(pts, 95, 64, H - 70, d.frame); }
    // 圓的 clip（可出陣的框要地塊邊也描：地塊 ∩ 圓）
    const cpc = d.cells.map((c) => { const p = d.byId[c.id]; return `<clipPath id="cpc-${c.id}"><circle cx="${p.x}" cy="${p.y}" r="${(p.big ? R_BIG : R_PATCH) - 2}"/></clipPath>`; }).join("");
    const inner = `<defs>${cpc}</defs>` + groundSvg(d, f) + marksSvg(d, f, { zoom, pick: pickId });
    const svg = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" style="display:block;position:absolute;inset:0"><g transform="${f.tr}">${inner}</g><rect width="${W}" height="${H}" filter="url(#grain)" pointer-events="none"/></svg>`;
    return `<div style="position:relative;width:${W}px;height:${H}px">${svg}${pickId ? card(d, pickId) + `<div style="position:absolute;left:10px;top:10px">${chip(`${esc(d.base.regions.find((r) => r.id === d.rid).name)} ▾`)}</div>` : hud(d, zoom)}</div>`;
  }
  window.txSlg2 = async (zoom, pickId) => { const d = await data(); mount(draw(d, zoom || "near", pickId)); return { zoom, pickId, trees: d.trees.length, peaks: d.peaks.length }; };
})();
