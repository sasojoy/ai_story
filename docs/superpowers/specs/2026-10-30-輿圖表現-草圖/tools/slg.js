// 輿圖風格草圖（第 6 輪）：企劃者 2026-10-30「還沒達到理想，參考一下三國志戰略版」。
// 往 SLG 戰略圖走：一張連續的地圖（捏放大縮小、不分層），地是「勢力色塊」（每一處一塊地、顏色＝誰的），
// 兩軍交界是亮線、正在翻的斜紋、可出陣的橘虛框、你是紅釘；HUD 浮在圖上，底下一條細條，點了才有卡。
// 真資料：/api/map/base（places、roads、world.cells＝每一處的地塊、world.sides 的顏色）、/api/map/state。
// 用法：載入後 txSlg('near'|'mid'|'far'|'hex', 點的地點 id)；txSlgOff() 還原。只是草圖。
(() => {
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const W = 375, H = 667;
  const RED = "#C0392B", ORANGE = "#E8A33D", INK = "#1B1F17";
  const LAND = "#8A946A", LAND_DARK = "#6E7752", WATER = "#5C8FB0", WATER2 = "#9CC3DA", RIDGE = "#5E5A3C", TREE = "#55693F";
  const SANS = '-apple-system,"PingFang TC","Noto Sans TC","Microsoft JhengHei",sans-serif';

  async function data() {
    const [base, st] = await Promise.all([fetch("/api/map/base").then((r) => r.json()), fetch("/api/map/state").then((r) => r.json())]);
    const places = Object.values(base.places); const byId = Object.fromEntries(places.map((p) => [p.id, p]));
    const here = st.here, hp = byId[here], rid = hp.region;
    const toPts = (dstr) => { const n = dstr.replace(/[MLZ]/g, " ").trim().split(/\s+/).map(Number); const o = []; for (let i = 0; i < n.length; i += 2) o.push([n[i], n[i + 1]]); return o; };
    const sides = Object.fromEntries(base.world.sides.map((s) => [s.id, s]));
    const cells = base.world.cells.map((c) => ({ ...c, pts: toPts(c.d) }));
    const regions = base.world.regions.map((r) => ({ ...r, pts: toPts(r.d) }));
    const adj = {}; for (const [a, b] of base.edges) { (adj[a] = adj[a] || []).push(b); (adj[b] = adj[b] || []).push(a); }
    const hops = { [here]: 0 }; const q = [here]; while (q.length) { const u = q.shift(); for (const v of adj[u] || []) if (!(v in hops)) { hops[v] = hops[u] + 1; q.push(v); } }
    const doc = new DOMParser().parseFromString(base.svg, "image/svg+xml");
    const center = (el) => { const n = (el.getAttribute("d") || "").match(/-?\d+(\.\d+)?/g); if (!n || n.length < 4) return null; let sx = 0, sy = 0, k = 0; for (let i = 0; i + 1 < n.length; i += 2) { sx += +n[i]; sy += +n[i + 1]; k++; } return [sx / k, sy / k]; };
    const peaks = [...doc.querySelectorAll('[fill="#557D69"]')].map(center).filter(Boolean);
    const trees = [...doc.querySelectorAll('[fill="#A9BE8F"]')].map(center).filter(Boolean);
    const rivers = [...doc.querySelectorAll('path[stroke="#6FA0C2"], path[stroke="#C9A867"]')].map((p) => p.getAttribute("d")).filter((d) => d && d.length > 20);
    const exits = (adj[here] || []).map((id) => ({ p: byId[id], s: st.places[id] || {} })).sort((a, b) => (a.s.minutes || 99) - (b.s.minutes || 99));
    const roadOf = {}; for (const [a, b, cx, cy] of base.roads) { roadOf[`${a}|${b}`] = [cx, cy]; roadOf[`${b}|${a}`] = [cx, cy]; }
    return { base, st, places, byId, here, hp, rid, sides, cells, regions, hops, peaks, trees, rivers, exits, roadOf, S: st.places, week: st.week, frame: base.world.frame };
  }

  // 取景：把 pts 塞進畫面；但視窗不准比天下的框還大（會看到框外），也不准滑出框外（像 SLG 的地圖夾邊）
  function fitter(pts, pad, top = 0, bottom = H, frame = null) {
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
    const x0 = Math.min(...xs) - pad, x1 = Math.max(...xs) + pad, y0 = Math.min(...ys) - pad, y1 = Math.max(...ys) + pad;
    let s = Math.min((W - 16) / (x1 - x0), (bottom - top) / (y1 - y0));
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2; let vx0 = cx - (W / 2) / s, vy0 = cy - ((top + bottom) / 2) / s;
    if (frame) { const [fx0, fy0, fx1, fy1] = frame; s = Math.max(s, W / (fx1 - fx0), H / (fy1 - fy0)); vx0 = cx - (W / 2) / s; vy0 = cy - ((top + bottom) / 2) / s;
      vx0 = Math.max(fx0, Math.min(fx1 - W / s, vx0)); vy0 = Math.max(fy0, Math.min(fy1 - H / s, vy0)); }
    return { s, k: 1 / s, X: (x) => (x - vx0) * s, Y: (y) => (y - vy0) * s, tr: `translate(${(-vx0 * s).toFixed(2)},${(-vy0 * s).toFixed(2)}) scale(${s.toFixed(4)})` };
  }
  const inPoly = (pt, poly) => { let c = false; for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) { const [xi, yi] = poly[i], [xj, yj] = poly[j]; if ((yi > pt[1]) !== (yj > pt[1]) && pt[0] < ((xj - xi) * (pt[1] - yi)) / (yj - yi) + xi) c = !c; } return c; };

  function mount(html) {
    txSlgOff();
    const map = document.querySelector("#map"); const top = map.getBoundingClientRect().top; const tabsTop = document.querySelector(".tabs").getBoundingClientRect().top;
    const box = document.createElement("div"); box.id = "tx-mock";
    box.style.cssText = `position:fixed;left:0;right:0;top:${Math.round(top)}px;bottom:${Math.round(innerHeight - tabsTop)}px;z-index:950;overflow:hidden;background:${LAND};font-family:${SANS}`;
    box.innerHTML = html; document.body.appendChild(box);
    const rt = document.querySelector(".r-top"); if (rt) rt.style.visibility = "hidden";
  }
  window.txSlgOff = () => { document.querySelector("#tx-mock")?.remove(); const rt = document.querySelector(".r-top"); if (rt) rt.style.visibility = ""; };

  const ownerOf = (d, id) => { const st = d.S[id] || {}; return st.control || null; };
  const fillOf = (d, id) => { const o = ownerOf(d, id); return o && d.sides[o] ? d.sides[o].soft : "#C9C2AE"; };
  const strongOf = (d, id) => { const o = ownerOf(d, id); return o && d.sides[o] ? d.sides[o].color : "#8F8B82"; };

  // 地：色塊、交界亮線、正在翻的斜紋、可出陣的橘虛框
  function groundSvg(d, f, opts) {
    const g = [];
    const k = f.k;
    g.push(`<defs><filter id="blur" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="${(5 * k).toFixed(2)}"/></filter><filter id="grain" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="1.2" numOctaves="1" seed="9"/><feColorMatrix values="0 0 0 0 0.1 0 0 0 0 0.12 0 0 0 0 0.05 0 0 0 0.07 0"/></filter>`);
    for (const c of d.cells) { const st = d.S[c.id] || {}; if (!st.tug) continue; const side = Object.keys(st.tug)[0]; const a = d.sides[side] ? d.sides[side].soft : "#C9C2AE", b = fillOf(d, c.id);
      g.push(`<pattern id="stripe-${c.id}" patternUnits="userSpaceOnUse" width="${(10 * k).toFixed(2)}" height="${(10 * k).toFixed(2)}" patternTransform="rotate(45)"><rect width="${(5 * k).toFixed(2)}" height="${(10 * k).toFixed(2)}" fill="${a}"/><rect x="${(5 * k).toFixed(2)}" width="${(5 * k).toFixed(2)}" height="${(10 * k).toFixed(2)}" fill="${b}"/></pattern>`); }
    g.push(`</defs>`);
    // 框外壓暗
    const [fx0, fy0, fx1, fy1] = d.frame;
    g.push(`<rect x="${fx0 - 2000}" y="${fy0 - 2000}" width="${fx1 - fx0 + 4000}" height="${fy1 - fy0 + 4000}" fill="${LAND_DARK}"/><rect x="${fx0}" y="${fy0}" width="${fx1 - fx0}" height="${fy1 - fy0}" fill="${LAND}"/>`);
    // 地塊
    for (const c of d.cells) { const st = d.S[c.id] || {}; const pts = c.pts.map((p) => p.join(",")).join(" ");
      const fill = st.tug ? `url(#stripe-${c.id})` : fillOf(d, c.id); const op = ownerOf(d, c.id) || st.tug ? (opts.hex ? 0 : 0.62) : 0.22;
      g.push(`<polygon points="${pts}" fill="${fill}" fill-opacity="${op}" stroke="${INK}" stroke-opacity=".28" stroke-width="1" vector-effect="non-scaling-stroke"/>`); }
    // 山、林、河（框內的裝飾，壓在色塊上面但很淡）
    for (const [x, y] of d.peaks) g.push(`<ellipse cx="${x}" cy="${y}" rx="22" ry="13" fill="${RIDGE}" opacity=".28" filter="url(#blur)"/>`);
    for (const [x, y] of d.peaks) g.push(`<path d="M${x - 9},${y + 5}L${x},${y - 7}L${x + 9},${y + 5}" fill="none" stroke="${RIDGE}" stroke-width="1.3" vector-effect="non-scaling-stroke" opacity=".7"/>`);
    for (const [x, y] of d.trees) g.push(`<circle cx="${x}" cy="${y}" r="3.2" fill="${TREE}" opacity=".55"/>`);
    for (const dd of d.rivers) g.push(`<path d="${dd}" fill="none" stroke="${WATER}" stroke-width="4" vector-effect="non-scaling-stroke" stroke-linejoin="round"/><path d="${dd}" fill="none" stroke="${WATER2}" stroke-width="1.2" vector-effect="non-scaling-stroke"/>`);
    // 交界：兩塊地主人不同的那一條邊畫亮
    const edges = {}; const key = (a, b) => { const p = `${a[0].toFixed(1)},${a[1].toFixed(1)}`, q2 = `${b[0].toFixed(1)},${b[1].toFixed(1)}`; return p < q2 ? `${p}|${q2}` : `${q2}|${p}`; };
    for (const c of d.cells) for (let i = 0; i < c.pts.length; i++) { const a = c.pts[i], b = c.pts[(i + 1) % c.pts.length]; const kk = key(a, b); (edges[kk] = edges[kk] || []).push({ c, a, b }); }
    for (const list of Object.values(edges)) if (list.length === 2) { const [u, v] = list; const ou = ownerOf(d, u.c.id) || "x", ov = ownerOf(d, v.c.id) || "x"; if (ou !== ov && (ou !== "x" || ov !== "x"))
      g.push(`<path d="M${u.a[0]},${u.a[1]}L${u.b[0]},${u.b[1]}" stroke="#F7F2E6" stroke-width="2.2" vector-effect="non-scaling-stroke" stroke-linecap="round" opacity=".9"/>`); }
    return g.join("");
  }
  // 壓在地上面的線：可出陣的橘虛框、你那一塊的紅框、很淡的路
  function outlineSvg(d) {
    const g = [];
    for (const c of d.cells) { const st = d.S[c.id] || {}; if (st.sortie) g.push(`<polygon points="${c.pts.map((p) => p.join(",")).join(" ")}" fill="none" stroke="${ORANGE}" stroke-width="2.4" stroke-dasharray="7 5" vector-effect="non-scaling-stroke"/>`); }
    const mine = d.cells.find((c) => c.id === d.here); if (mine) g.push(`<polygon points="${mine.pts.map((p) => p.join(",")).join(" ")}" fill="none" stroke="${RED}" stroke-width="2.6" vector-effect="non-scaling-stroke"/>`);
    for (const [a, b, cx, cy] of d.base.roads) { const pa = d.byId[a], pb = d.byId[b]; g.push(`<path d="M${pa.x},${pa.y}Q${cx},${cy} ${pb.x},${pb.y}" fill="none" stroke="${INK}" stroke-opacity=".35" stroke-width="1" vector-effect="non-scaling-stroke"/>`); }
    return g.join("");
  }

  // 格子版的地：六角格照它落在哪一塊地上色
  function hexSvg(d, f) {
    const g = []; const R = 20; const dx = R * Math.sqrt(3), dy = R * 1.5;
    const [fx0, fy0, fx1, fy1] = d.frame; const cols = Math.ceil((fx1 - fx0) / dx) + 2, rows = Math.ceil((fy1 - fy0) / dy) + 2;
    const hexPts = (cx, cy) => { const o = []; for (let i = 0; i < 6; i++) { const a = Math.PI / 6 + (i * Math.PI) / 3; o.push(`${(cx + R * Math.cos(a)).toFixed(1)},${(cy + R * Math.sin(a)).toFixed(1)}`); } return o.join(" "); };
    const own = {}; // 每一格落在哪一塊地
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) { const cx = fx0 + c * dx + (r % 2 ? dx / 2 : 0), cy = fy0 + r * dy; if (cx < fx0 || cx > fx1 || cy < fy0 || cy > fy1) continue;
      // 地塊會互相疊（幽州那幾塊沒有裁到區界）：落在好幾塊裡就挑地點最近的那一塊
      const inside = d.cells.filter((cc) => inPoly([cx, cy], cc.pts)); let cell = null, best = Infinity;
      for (const cc of inside) { const p = d.byId[cc.id]; if (!p) continue; const dd = Math.hypot(p.x - cx, p.y - cy); if (dd < best) { best = dd; cell = cc; } }
      const id = cell ? cell.id : null; own[`${r},${c}`] = { cx, cy, id };
      const st = id ? d.S[id] || {} : {}; const o = id ? ownerOf(d, id) : null; const fill = st.tug ? `url(#stripe-${id})` : o ? d.sides[o].color : "#B9B49E";
      g.push(`<polygon points="${hexPts(cx, cy)}" fill="${fill}" fill-opacity="${o ? 0.5 : st.tug ? 0.9 : 0.35}" stroke="${INK}" stroke-opacity=".32" stroke-width="1" vector-effect="non-scaling-stroke"/>`); }
    return g.join("");
  }

  // 地點：白底小圓＋種類字、名字白字黑邊、旗、金、⚔、紅釘
  function marksSvg(d, f, opts) {
    const g = []; const k = f.k; const zoom = opts.zoom; const pickId = opts.pick;
    const show = (p) => (zoom === "far" ? p.big || p.id === d.here : true);
    // 名字照縮放層級露（SLG 的做法：拉遠了名字先收）：近＝兩步內、大地方、本週、寶、翻、可出陣；中＝大地方、一步內、本週、寶、翻；遠＝只剩區名
    const named = (p, st) => { const h = d.hops[p.id] ?? 99, hot = (d.week && d.week.id === p.id) || st.rich || st.tug || p.id === pickId;
      return zoom === "far" ? false : zoom === "mid" ? p.big || h <= 1 || hot : h <= 2 || p.big || hot || !!st.sortie; };
    for (const p of d.places) { if (!show(p)) continue; const st = d.S[p.id] || {}; const isHere = p.id === d.here, isPick = p.id === pickId, isWeek = d.week && d.week.id === p.id;
      let { x, y } = p; if (opts.snap) { const h = opts.snap(p); x = h[0]; y = h[1]; }
      const r = (p.big ? 11 : 9) * k * (isPick ? 1.25 : 1);
      if (!isHere) g.push(`<circle cx="${x}" cy="${y}" r="${r.toFixed(2)}" fill="#FFFDF7" stroke="${isPick ? "#FFFFFF" : strongOf(d, p.id)}" stroke-width="${isPick ? 3 : 2}" vector-effect="non-scaling-stroke"/><text x="${x}" y="${y}" dy="${(r * 0.38).toFixed(2)}" font-size="${(r * 1.05).toFixed(2)}" text-anchor="middle" fill="${INK}" font-weight="700">${esc(p.glyph)}</text>`);
      if (st.tug || st.melee) g.push(`<g transform="translate(${x + r * 0.9},${y - r * 0.9}) scale(${k})"><circle r="7" fill="${RED}"/><path d="M-3.5,-3.5L3.5,3.5M3.5,-3.5L-3.5,3.5" stroke="#fff" stroke-width="1.6"/></g>`);
      if (st.rich) g.push(`<g transform="translate(${x - r * 0.95},${y - r * 0.9}) scale(${k})"><path d="M-6,2l3,-4h6l3,4l-2,3h-8z" fill="#F2C94C" stroke="#7A5A14" stroke-width=".9"/></g>`);
      if (isWeek) g.push(`<g transform="translate(${x},${y - r}) scale(${k})"><path d="M0,0v-22" stroke="${INK}" stroke-width="1.6"/><path d="M0,-22l14,4.5-14,4.5z" fill="${RED}" stroke="#7A1F18" stroke-width="1"/></g>`);
      if (isHere) g.push(`<g transform="translate(${x},${y}) scale(${k})"><circle r="16" fill="none" stroke="${RED}" stroke-width="2" opacity=".45"/><path d="M0,6C-9,-4 -9,-14 0,-14C9,-14 9,-4 0,6Z" fill="${RED}" stroke="#fff" stroke-width="1.6"/><text y="-5" font-size="10" text-anchor="middle" fill="#fff" font-weight="700">你</text></g>`);
      // 名字：白字黑邊；近看的在名字後帶幾分
      if (!named(p, st) && !isHere) continue;
      const near = zoom !== "far" && (d.hops[p.id] ?? 99) <= 2 && !isHere; const name = p.name.replace(/（.*）/, "") + (near && st.minutes != null ? ` ${st.minutes}分` : "");
      const fs = (zoom === "far" ? 11 : p.big ? 12 : 11) * k;
      g.push(`<text x="${x}" y="${y + r + fs * 1.05}" font-size="${fs.toFixed(2)}" text-anchor="middle" fill="${isHere ? "#FFE3DD" : "#FFFFFF"}" stroke="${INK}" stroke-width="${(3 * k).toFixed(2)}" paint-order="stroke" font-weight="700" stroke-linejoin="round">${esc(name)}</text>`);
    }
    if (zoom === "far") for (const r of d.base.regions) g.push(`<text x="${r.cx}" y="${r.cy - 26}" font-size="${(17 * k).toFixed(2)}" text-anchor="middle" fill="#FFFFFF" stroke="${INK}" stroke-width="${(4 * k).toFixed(2)}" paint-order="stroke" font-weight="700" opacity=".92" letter-spacing="${(2 * k).toFixed(2)}">${esc(r.name)}</text>`);
    // 點了一處：從你到那裡的路
    const PS = pickId && d.S[pickId]; if (PS && PS.path) { const chain = [d.here, ...PS.path]; const segs = [];
      for (let i = 0; i + 1 < chain.length; i++) { const a = d.byId[chain[i]], b = d.byId[chain[i + 1]]; const c = d.roadOf[`${chain[i]}|${chain[i + 1]}`] || [(a.x + b.x) / 2, (a.y + b.y) / 2]; segs.push(`M${a.x},${a.y}Q${c[0]},${c[1]} ${b.x},${b.y}`); }
      g.unshift(`<path d="${segs.join("")}" fill="none" stroke="${INK}" stroke-width="6" stroke-opacity=".45" vector-effect="non-scaling-stroke" stroke-linecap="round"/><path d="${segs.join("")}" fill="none" stroke="#FFFFFF" stroke-width="3" vector-effect="non-scaling-stroke" stroke-linecap="round" stroke-dasharray="8 6"/>`); }
    return g.join("");
  }

  const chip = (txt, extra = "") => `<div style="background:rgba(20,24,18,.80);color:#F4F1E8;border:1px solid rgba(255,255,255,.18);border-radius:6px;padding:6px 10px;font-size:14px;font-weight:600;backdrop-filter:blur(2px);${extra}">${txt}</div>`;
  const roundBtn = (txt, extra = "") => `<div style="width:44px;height:44px;border-radius:50%;background:rgba(20,24,18,.82);color:#F4F1E8;border:1px solid rgba(255,255,255,.22);display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;box-shadow:0 2px 6px rgba(0,0,0,.35);${extra}">${txt}</div>`;
  function hud(d, zoom) {
    const sortieN = Object.values(d.S).filter((s) => s.sortie).length;
    const wk = d.week && d.byId[d.week.id]; const ws = wk && (d.S[wk.id] || {});
    const bar = `<div style="position:absolute;left:10px;right:10px;bottom:10px;background:rgba(20,24,18,.86);color:#F4F1E8;border:1px solid rgba(255,255,255,.16);border-radius:8px;padding:8px 12px;display:flex;justify-content:space-between;align-items:center;font-size:13px">
      <div>${wk ? `<span style="background:${RED};color:#fff;border-radius:3px;padding:1px 5px;font-size:11px;margin-right:6px">本週</span><b style="font-size:15px">${esc(wk.name.replace(/（.*）/, ""))}</b> <span style="color:#C9C4B6">${esc((d.week.why || "").split("・").slice(1).join("・"))}・步行 ${ws.minutes ?? ""} 分</span>` : "本週沒有軍令"}</div>
      <div style="color:${ORANGE};font-weight:700;white-space:nowrap">可出陣 ${sortieN} ›</div></div>`;
    return `<div style="position:absolute;left:10px;top:10px">${chip(`${esc(d.base.regions.find((r) => r.id === d.rid).name)} ▾`)}</div>
      <div style="position:absolute;right:10px;top:10px;display:flex;gap:8px">${roundBtn("🔍")}</div>
      <div style="position:absolute;right:10px;bottom:70px;display:flex;flex-direction:column;gap:8px">${roundBtn("⌖", zoom === "near" ? `border-color:${ORANGE};color:${ORANGE}` : "")}${roundBtn("天下", zoom === "far" ? `border-color:${ORANGE};color:${ORANGE}` : "")}</div>${bar}`;
  }
  function card(d, id) {
    const p = d.byId[id], s = d.S[id] || {}; const o = ownerOf(d, id); const side = o && d.sides[o];
    const stars = "★".repeat(s.danger || 1) + "☆".repeat(3 - (s.danger || 1));
    const tagStyle = (bg) => `display:inline-block;background:${bg};color:#fff;border-radius:3px;padding:1px 6px;font-size:11px;margin-left:6px;vertical-align:2px`;
    const btn = (t, sub, bg, fg = "#fff") => `<div style="flex:1;background:${bg};color:${fg};border-radius:6px;padding:7px 4px;text-align:center"><div style="font-size:15px;font-weight:700">${t}</div><div style="font-size:11px;opacity:.85">${sub}</div></div>`;
    const squads = (s.squads || []).map((q) => `${esc(q.name)} <span style="color:#C9C4B6">${esc(q.odds)}</span>`).join("、") || "—";
    return `<div style="position:absolute;left:0;right:0;bottom:0;background:rgba(20,24,18,.92);color:#F4F1E8;border-top:1px solid rgba(255,255,255,.18);border-radius:12px 12px 0 0;padding:12px 14px 12px">
      <div style="position:absolute;right:12px;top:10px;color:#C9C4B6;font-size:16px">✕</div>
      <div style="font-size:19px;font-weight:700">${esc(p.name)}<span style="${tagStyle(side ? side.color : s.tug ? RED : "#8F8B82")}">${side ? side.name + "地" : s.tug ? "正在翻" : "無主"}</span><span style="font-size:12px;color:${ORANGE};margin-left:8px">危 ${stars}</span></div>
      <div style="font-size:12.5px;color:#C9C4B6;margin-top:3px">${esc(p.terrain || "")}・${esc(p.mostly || "")}${s.odds ? "・勝算 " + esc(s.odds.word) : ""}${s.yield ? "・" + esc(s.yield) : ""}</div>
      <div style="display:flex;gap:8px;margin-top:10px">${btn(`步行 ${s.minutes ?? ""} 分`, "沿路可以做小事", ORANGE, INK)}${btn("疾行", `立刻到・體力 ${s.stamina ?? ""}`, "rgba(255,255,255,.12)")}${s.sortie ? btn("出陣", "攻這一塊", RED) : ""}</div>
      <div style="font-size:12.5px;margin-top:10px"><span style="color:#C9C4B6">守軍</span>　${squads}</div>
      ${(s.people || []).length ? `<div style="font-size:12.5px;margin-top:3px"><span style="color:#C9C4B6">人物</span>　${s.people.map(esc).join("、")}</div>` : ""}
    </div>`;
  }

  function draw(d, zoom, pickId) {
    let f, snap = null;
    const nearPts = d.places.filter((p) => (d.hops[p.id] ?? 99) <= 2).map((p) => [p.x, p.y]);
    if (zoom === "near" || zoom === "hex") f = fitter(nearPts, 70, 64, H - 70, d.frame);
    else if (zoom === "mid") f = fitter(d.regions.find((r) => r.id === d.rid).pts, 40, 64, H - 70, d.frame);
    else f = fitter([[d.frame[0], d.frame[1]], [d.frame[2], d.frame[3]]], 20, 64, H - 70);
    const hex = zoom === "hex";
    if (hex) { const R = 20, dx = R * Math.sqrt(3), dy = R * 1.5; snap = (p) => { const r = Math.round((p.y - d.frame[1]) / dy); const c = Math.round((p.x - d.frame[0] - (r % 2 ? dx / 2 : 0)) / dx); return [d.frame[0] + c * dx + (r % 2 ? dx / 2 : 0), d.frame[1] + r * dy]; }; }
    const inner = groundSvg(d, f, { hex }) + (hex ? hexSvg(d, f) : "") + outlineSvg(d) + marksSvg(d, f, { zoom: hex ? "near" : zoom, pick: pickId, snap });
    const svg = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" style="display:block;position:absolute;inset:0"><g transform="${f.tr}">${inner}</g><rect width="${W}" height="${H}" filter="url(#grain)" pointer-events="none"/></svg>`;
    return `<div style="position:relative;width:${W}px;height:${H}px">${svg}${pickId ? card(d, pickId) : hud(d, hex ? "near" : zoom)}${pickId ? `<div style="position:absolute;left:10px;top:10px">${chip(`${esc(d.base.regions.find((r) => r.id === d.rid).name)} ▾`)}</div>` : ""}</div>`;
  }
  window.txSlg = async (zoom, pickId) => { const d = await data(); mount(draw(d, zoom || "near", pickId)); return { zoom, pickId, cells: d.cells.length, sortie: Object.values(d.S).filter((s) => s.sortie).length }; };
})();
