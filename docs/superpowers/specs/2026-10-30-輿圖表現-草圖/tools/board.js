// 輿圖風格草圖（第 3 輪）：企劃者 2026-10-30 挑了「乙 兵棋沙盤」，用這一套畫三個畫面：
// 打開第一眼（名字牌改成挑空位擺）、點一處（棋子抬起、路點亮、底下換成卡）、天下（整張沙盤）。
// 真資料：/api/map/base、/api/map/state；山、林、河直接從底圖 svg 裡挑出來（顏色認的），不再手填。
// 用法：載入後 txBoard('region') | txBoard('region', '<地點 id>') | txBoard('world')；txBoardOff() 還原。只是草圖。
(() => {
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const SIDE = { guan: { name: "官", color: "#3D5F8F" }, huang: { name: "黃", color: "#B9821A" } };
  const RED = "#A8322A", DARK = "#2E2620", SAND = "#D8C9A6", CORD = "#8B7355", WOOD = "#5C4430", WOOD2 = "#3A2A1C", CREAM = "#F1E6CF", MUTE = "#B8A98E";
  const SONG = '"Noto Serif TC","PMingLiU","Songti TC",serif';
  const REGION_ZH = { youzhou: "幽州", jizhou: "冀州", luoyang: "洛陽", yingru: "潁川汝南", nanyang: "南陽" };
  const PIC_H = 430, W = 375, TOP = 58, TRAY = 7;

  async function data() {
    const [base, st] = await Promise.all([fetch("/api/map/base").then((r) => r.json()), fetch("/api/map/state").then((r) => r.json())]);
    const places = Object.values(base.places);
    const byId = Object.fromEntries(places.map((p) => [p.id, p]));
    const here = st.here, hp = byId[here], rid = hp.region;
    const region = base.world.regions.find((r) => r.id === rid);
    const toPts = (dstr) => { const n = dstr.replace(/[MLZ]/g, " ").trim().split(/\s+/).map(Number); const o = []; for (let i = 0; i < n.length; i += 2) o.push([n[i], n[i + 1]]); return o; };
    const pts = toPts(region.d);
    const inR = places.filter((p) => p.region === rid);
    const exits = base.edges.filter((e) => e.includes(here)).map((e) => (e[0] === here ? e[1] : e[0])).map((id) => ({ p: byId[id], s: st.places[id] || {} }));
    exits.sort((a, b) => (a.s.minutes || 99) - (b.s.minutes || 99));
    const roadOf = {}; for (const [a, b, cx, cy] of base.roads) { roadOf[`${a}|${b}`] = [cx, cy]; roadOf[`${b}|${a}`] = [cx, cy]; }
    // 底圖裡的山水：照顏色挑
    const doc = new DOMParser().parseFromString(base.svg, "image/svg+xml");
    const center = (el) => { const n = (el.getAttribute("d") || el.getAttribute("points") || "").match(/-?\d+(\.\d+)?/g); if (!n || n.length < 4) return null; let sx = 0, sy = 0, k = 0; for (let i = 0; i + 1 < n.length; i += 2) { sx += +n[i]; sy += +n[i + 1]; k++; } return [sx / k, sy / k]; };
    const pick = (sel) => [...doc.querySelectorAll(sel)].map(center).filter(Boolean);
    const peaks = pick('[fill="#557D69"]'), woods = pick('[fill="#8FA877"]');
    const rivers = [...doc.querySelectorAll('path[stroke="#6FA0C2"], path[stroke="#C9A867"]')].map((p) => p.getAttribute("d")).filter((d) => d && d.length > 20);
    // 離你幾步路（照路網算）
    const adj = {}; for (const [a, b] of base.edges) { (adj[a] = adj[a] || []).push(b); (adj[b] = adj[b] || []).push(a); }
    const hops = { [here]: 0 }; const q = [here];
    while (q.length) { const u = q.shift(); for (const v of adj[u] || []) if (!(v in hops)) { hops[v] = hops[u] + 1; q.push(v); } }
    return { base, st, places, byId, here, hp, rid, region, pts, inR, exits, S: st.places, week: st.week, roadOf, peaks, woods, rivers, toPts, hops };
  }

  function fitter(pts, top, bottom, pad) {
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
    const x0 = Math.min(...xs) - pad, x1 = Math.max(...xs) + pad, y0 = Math.min(...ys) - pad, y1 = Math.max(...ys) + pad;
    const s = Math.min((W - 2 * TRAY - 10) / (x1 - x0), (bottom - top) / (y1 - y0));
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    const vx0 = cx - (W / 2) / s, vy0 = cy - ((top + bottom) / 2) / s;
    return { s, vx0, vy0, X: (x) => (x - vx0) * s, Y: (y) => (y - vy0) * s, tr: `translate(${(-vx0 * s).toFixed(2)},${(-vy0 * s).toFixed(2)}) scale(${s.toFixed(4)})` };
  }

  function mount(html) {
    txBoardOff();
    const map = document.querySelector("#map");
    const top = map.getBoundingClientRect().top;
    const tabsTop = document.querySelector(".tabs").getBoundingClientRect().top;
    const box = document.createElement("div");
    box.id = "tx-mock";
    box.style.cssText = `position:fixed;left:0;right:0;top:${Math.round(top)}px;bottom:${Math.round(innerHeight - tabsTop)}px;z-index:950;overflow:hidden;`;
    box.innerHTML = html;
    document.body.appendChild(box);
    const rt = document.querySelector(".r-top"); if (rt) rt.style.visibility = "hidden";
  }
  window.txBoardOff = () => { document.querySelector("#tx-mock")?.remove(); const rt = document.querySelector(".r-top"); if (rt) rt.style.visibility = ""; };

  const sideOf = (s) => (s && SIDE[s]) || null;
  const defs = `<defs><filter id="blur" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="6"/></filter><filter id="shadow" x="-50%" y="-50%" width="200%" height="200%"><feDropShadow dx="0" dy="1.5" stdDeviation="1.2" flood-color="#000" flood-opacity=".38"/></filter><filter id="lift" x="-50%" y="-50%" width="200%" height="200%"><feDropShadow dx="0" dy="4" stdDeviation="2.4" flood-color="#000" flood-opacity=".45"/></filter><filter id="press" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="1.4"/></filter><filter id="grain" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="1.1" numOctaves="1" seed="5"/><feColorMatrix values="0 0 0 0 0.3 0 0 0 0 0.22 0 0 0 0 0.1 0 0 0 0.07 0"/></filter></defs>`;

  // 山水：在底圖座標裡畫，整組用 transform 縮進來
  function terrainSvg(d, f, scale) {
    const g = [];
    const k = 1 / f.s; // 1px 在底圖座標裡是多少
    for (const [x, y] of d.peaks) g.push(`<ellipse cx="${x}" cy="${y}" rx="${26 * scale}" ry="${16 * scale}" fill="#A99266" opacity=".5" filter="url(#blur)"/>`);
    for (const [x, y] of d.peaks) g.push(`<path d="M${x - 11 * scale},${y + 6 * scale}L${x},${y - 9 * scale}L${x + 11 * scale},${y + 6 * scale}" fill="none" stroke="#7E6A47" stroke-width="${1.2 * k}" opacity=".6"/>`);
    for (const dd of d.rivers) g.push(`<path d="${dd}" fill="none" stroke="#8E9A98" stroke-width="${7 * k}" opacity=".55" filter="url(#press)"/><path d="${dd}" fill="none" stroke="#B9C7C4" stroke-width="${3 * k}"/>`);
    for (const [x, y] of d.woods) g.push(`<circle cx="${x}" cy="${y}" r="${4.5 * scale}" fill="#7E8E5C" opacity=".7"/>`);
    return `<g transform="${f.tr}">${g.join("")}</g>`;
  }

  function roadsSvg(d, f, ids, extra) {
    const inSet = new Set(ids); const out = [], exits = [];
    for (const [a, b, cx, cy] of d.base.roads) {
      const ia = inSet.has(a), ib = inSet.has(b); if (!ia && !ib) continue;
      const pa = d.byId[a], pb = d.byId[b];
      if (ia && ib) out.push(`<path d="M${pa.x},${pa.y}Q${cx},${cy} ${pb.x},${pb.y}" fill="none" ${extra}/>`);
      else { const pi = ia ? pa : pb, po = ia ? pb : pa; const t = 0.38; const mx = pi.x + (po.x - pi.x) * t, my = pi.y + (po.y - pi.y) * t;
        out.push(`<path d="M${pi.x},${pi.y}L${mx},${my}" fill="none" ${extra} stroke-dasharray="${3 / f.s} ${4 / f.s}"/>`);
        const ddx = po.x - pi.x, ddy = po.y - pi.y; exits.push({ x: f.X(mx), y: f.Y(my), name: REGION_ZH[po.region] || po.region, dir: Math.abs(ddx) > Math.abs(ddy) ? (ddx < 0 ? "←" : "→") : ddy < 0 ? "↑" : "↓" }); }
    }
    return { svg: `<g transform="${f.tr}">${out.join("")}</g>`, exits };
  }

  // 名字牌：照重要度排隊，每一塊挑一個不壓到棋子、不壓到別的牌的位置（下、上、右、左、四個斜角）
  function placeLabels(tokens, want) {
    const placed = []; const blockers = tokens.map((t) => ({ x: t.x, y: t.y, w: 2 * t.r + 3, h: 2 * t.r + 3 }));
    const hit = (r) => [...blockers, ...placed].some((o) => Math.abs(o.x - r.x) < (o.w + r.w) / 2 && Math.abs(o.y - r.y) < (o.h + r.h) / 2) || r.x - r.w / 2 < TRAY + 3 || r.x + r.w / 2 > W - TRAY - 3 || r.y - r.h / 2 < TOP - 4 || r.y + r.h / 2 > PIC_H - TRAY - 3;
    for (const l of want) {
      const t = l.t, hw = l.w / 2, dy0 = t.r + l.h / 2 + 3, dx0 = t.r + hw + 4;
      const cands = [[0, dy0], [0, -dy0], [dx0, 0], [-dx0, 0], [dx0 - 2, dy0 - 3], [-(dx0 - 2), dy0 - 3], [dx0 - 2, -(dy0 - 3)], [-(dx0 - 2), -(dy0 - 3)], [0, dy0 + l.h + 2], [0, -(dy0 + l.h + 2)]];
      let ok = null;
      for (const [dx, dy] of cands) { const r = { x: t.x + dx, y: t.y + dy, w: l.w, h: l.h }; if (!hit(r)) { ok = r; break; } }
      // 八個位置都被佔了：往外一圈一圈找，找到了就拉一條細線回棋子
      if (!ok) outer: for (let rad = dy0 + 10; rad < dy0 + 70; rad += 9) for (let a = 0; a < 360; a += 30) {
        const r = { x: t.x + rad * Math.cos((a * Math.PI) / 180), y: t.y + rad * Math.sin((a * Math.PI) / 180), w: l.w, h: l.h };
        if (!hit(r)) { ok = r; l.lead = true; break outer; }
      }
      l.forced = !ok; if (!ok) ok = { x: t.x, y: t.y + dy0, w: l.w, h: l.h };
      l.x = ok.x; l.y = ok.y; placed.push(ok);
    }
  }

  function tag(x, w, label, on) { return `<g style="font-family:${SONG}" filter="url(#shadow)"><rect x="${x}" y="14" width="${w}" height="28" rx="3" fill="${on ? "#8C6B4A" : WOOD}" stroke="${WOOD2}"/><rect x="${x + 2}" y="16" width="${w - 4}" height="24" rx="2" fill="none" stroke="${on ? "#C9A97F" : "#8C6B4A"}" stroke-width=".8"/><text x="${x + w / 2}" y="33" font-size="14" text-anchor="middle" fill="${CREAM}">${label}</text></g>`; }
  const tray = () => `<rect x="0" y="0" width="${W}" height="${PIC_H}" fill="none" stroke="${WOOD}" stroke-width="${TRAY * 2}"/><rect x="${TRAY}" y="${TRAY}" width="${W - 2 * TRAY}" height="${PIC_H - 2 * TRAY}" fill="none" stroke="${WOOD2}" stroke-width="1"/><rect x="${TRAY + 1.5}" y="${TRAY + 1.5}" width="${W - 2 * TRAY - 3}" height="${PIC_H - 2 * TRAY - 3}" fill="none" stroke="#8C6B4A" stroke-width=".7" opacity=".8"/>`;
  const ingot = (x, y, k = 1) => `<path d="M${x - 6 * k},${y}l${3 * k},${-4 * k}h${6 * k}l${3 * k},${4 * k}l${-2 * k},${3 * k}h${-8 * k}z" fill="#D9A93B" stroke="#7A5A14" stroke-width=".8"/>`;
  const flag = (x, y, h, k = 1) => `<path d="M${x},${y}v-${h}" stroke="${DARK}" stroke-width="${1.6 * k}"/><path d="M${x},${y - h}l${16 * k},${5 * k}-${16 * k},${5 * k}z" fill="${RED}" stroke="#7A1F18" stroke-width="1"/>`;

  function tokenSvg(t, d, opts = {}) {
    const { p, st, r, x, y } = t; const isHere = p.id === d.here, isWeek = d.week && d.week.id === p.id, picked = opts.pick === p.id;
    const sd = sideOf(st.control); const fill = isHere ? RED : sd ? sd.color : "#9A9283"; const g = [];
    g.push(`<g filter="url(#${picked ? "lift" : "shadow"})"${opts.dim && !isHere && !picked ? ' opacity=".72"' : ""}>`);
    if (isHere) g.push(`<circle cx="${x}" cy="${y}" r="${r + 7}" fill="none" stroke="${RED}" stroke-width="2" opacity=".45"/>`);
    if (picked) g.push(`<circle cx="${x}" cy="${y}" r="${r + 6}" fill="none" stroke="${CREAM}" stroke-width="2.5"/>`);
    g.push(`<circle cx="${x}" cy="${y}" r="${r}" fill="${fill}" stroke="${DARK}" stroke-width="1.8"/>`);
    if (st.tug) { const side = Object.keys(st.tug)[0], v = st.tug[side]; g.push(`<clipPath id="c${p.id}"><rect x="${x - r}" y="${y - r}" width="${2 * r * v / 100}" height="${2 * r}"/></clipPath><circle cx="${x}" cy="${y}" r="${r - 1}" fill="${SIDE[side].color}" clip-path="url(#c${p.id})"/>`); }
    g.push(`<circle cx="${x}" cy="${y}" r="${r - 3.5}" fill="none" stroke="#fff" stroke-opacity=".35" stroke-width="1"/>`);
    if (r >= 9) g.push(`<text x="${x}" y="${y + (isHere ? 6 : r * 0.36)}" font-size="${isHere ? 16 : r * 0.95}" text-anchor="middle" fill="#fff" font-weight="700" style="font-family:${SONG}">${isHere ? "你" : esc(p.glyph)}</text>`);
    g.push(`</g>`);
    if (st.rich) g.push(ingot(x + r - 3, y - r + 2, r >= 9 ? 1 : 0.7));
    if (isWeek) g.push(flag(x, y, r + 22, 1));
    return g.join("");
  }

  // ─────────── 區圖（第一眼／點一處） ───────────
  function region(d, pickId) {
    const f = fitter(d.pts, TOP + 6, PIC_H - TRAY - 6, 30);
    const g = [defs, `<rect width="${W}" height="${PIC_H}" fill="${SAND}"/><rect width="${W}" height="${PIC_H}" filter="url(#grain)"/>`];
    g.push(terrainSvg(d, f, 1));
    const polyPx = d.pts.map(([x, y]) => `${f.X(x).toFixed(1)},${f.Y(y).toFixed(1)}`).join(" ");
    g.push(`<path d="M0,0H${W}V${PIC_H}H0Z M${polyPx.replace(/ /g, "L")}Z" fill="#3A2C1E" fill-rule="evenodd" opacity=".14"/><polygon points="${polyPx}" fill="none" stroke="#6B5A3E" stroke-width="1.5" opacity=".5"/>`);
    const ids = d.inR.map((p) => p.id);
    const roads = roadsSvg(d, f, ids, `stroke="${CORD}" stroke-width="${(1.6 / f.s).toFixed(2)}" opacity=".8"`);
    g.push(roads.svg);
    for (const e of roads.exits) g.push(`<text x="${e.x + (e.dir === "←" ? -4 : 4)}" y="${e.y + 4}" font-size="10" fill="#5A4A33" text-anchor="${e.dir === "←" ? "end" : "start"}" style="font-family:${SONG}">${e.dir}${e.name}</text>`);
    // 點了一處：從你到那裡的路點亮
    const S = d.S[pickId];
    if (pickId && S && S.path) {
      const chain = [d.here, ...S.path]; const segs = [];
      for (let i = 0; i + 1 < chain.length; i++) { const a = d.byId[chain[i]], b = d.byId[chain[i + 1]]; const c = d.roadOf[`${chain[i]}|${chain[i + 1]}`] || [(a.x + b.x) / 2, (a.y + b.y) / 2]; segs.push(`M${a.x},${a.y}Q${c[0]},${c[1]} ${b.x},${b.y}`); }
      g.push(`<g transform="${f.tr}"><path d="${segs.join("")}" fill="none" stroke="${DARK}" stroke-width="${(6 / f.s).toFixed(2)}" opacity=".5" stroke-linecap="round"/><path d="${segs.join("")}" fill="none" stroke="${CREAM}" stroke-width="${(3.2 / f.s).toFixed(2)}" stroke-linecap="round"/></g>`);
    }
    const tokens = d.inR.map((p) => ({ p, st: d.S[p.id] || {}, r: p.id === d.here ? 17 : p.big ? 14 : 11, x: f.X(p.x), y: f.Y(p.y) }));
    const exitIds = new Set(d.exits.map((e) => e.p.id));
    const prio = (t) => (t.p.id === d.here ? 0 : t.p.id === pickId ? 0 : exitIds.has(t.p.id) || (d.week && d.week.id === t.p.id) ? 1 : t.p.big || t.st.rich || t.st.tug ? 2 : 3);
    const want = tokens.map((t) => { const n = t.p.name.replace(/（.*）/, ""); return { t, n, w: n.length * 10.5 + 9, h: 15, pr: prio(t) }; }).sort((a, b) => a.pr - b.pr);
    placeLabels(tokens, want);
    for (const t of tokens) if (t.p.id !== pickId) g.push(tokenSvg(t, d, { pick: pickId, dim: !!pickId }));
    for (const l of want) { const { t, n, w, h, x, y } = l; const isHere = t.p.id === d.here, isPick = t.p.id === pickId;
      if (l.lead) g.push(`<path d="M${t.x},${t.y}L${x},${y}" stroke="${DARK}" stroke-width="1" opacity=".55"/>`);
      g.push(`<rect x="${x - w / 2}" y="${y - h / 2}" width="${w}" height="${h}" rx="2.5" fill="${isHere ? RED : isPick ? CREAM : DARK}" opacity="${pickId && !isHere && !isPick ? ".72" : ".92"}"/><text x="${x}" y="${y + 4}" font-size="11" text-anchor="middle" fill="${isPick ? DARK : "#F4ECDC"}" font-weight="${isPick ? 700 : 400}" style="font-family:${SONG}">${esc(n)}</text>`); }
    const pt = tokens.find((t) => t.p.id === pickId); if (pt) g.push(tokenSvg({ ...pt, r: pt.r + 3 }, d, { pick: pickId }));
    g.push(tray());
    g.push(tag(14, 118, `${esc(d.region.name)} ▾`, false)); g.push(tag(W - 72, 58, "天下", false));
    const svg = `<svg width="${W}" height="${PIC_H}" viewBox="0 0 ${W} ${PIC_H}" style="display:block">${g.join("")}</svg>`;
    return `<div style="background:#3C2F25;height:100%">${svg}${pickId ? cardPanel(d, pickId) : listPanel(d)}</div>`;
  }

  const dot = (sd, big) => `<span style="display:inline-block;width:${big ? 18 : 14}px;height:${big ? 18 : 14}px;border-radius:50%;background:${sd ? sd.color : "#9A9283"};border:1.5px solid #1E1813;vertical-align:-3px;margin-right:8px"></span>`;
  function listPanel(d) {
    const rows = d.exits.map(({ p, s }) => { const sd = sideOf(s.control), isWeek = d.week && d.week.id === p.id;
      return `<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid rgba(255,255,255,.08)"><div>${dot(sd)}<span style="font-size:16px;color:${CREAM}">${esc(p.name.replace(/（.*）/, ""))}</span><span style="font-size:12px;color:${MUTE};margin-left:8px">${esc(p.mostly || "")}${isWeek ? '<span style="color:#F0B4A8">・本週軍令</span>' : ""}</span></div><div style="font-size:13px;color:#E6D8BD">步行 ${s.minutes ?? ""} 分 ›</div></div>`; }).join("");
    return `<div style="height:${667 - PIC_H}px;background:#3C2F25;border-top:3px solid #1E1813;padding:8px 16px 0;font-family:${SONG};color:${CREAM}"><div style="display:flex;justify-content:space-between;align-items:baseline"><div style="font-size:12px;color:${MUTE}">令牌</div><div style="font-size:12px;color:${MUTE}">你在 <b style="color:#F0B4A8;font-weight:400">${esc(d.hp.name)}</b>・${d.exits.length} 條路</div></div>${rows}</div>`;
  }
  function cardPanel(d, id) {
    const p = d.byId[id], s = d.S[id] || {}; const sd = sideOf(s.control);
    const squads = (s.squads || []).map((q) => `${esc(q.name)} <span style="color:${MUTE}">${esc(q.odds)}</span>`).join("、");
    const btn = (label, sub, primary) => `<div style="flex:1;border-radius:4px;padding:7px 6px;text-align:center;background:${primary ? "#8C6B4A" : "#2A211B"};border:1px solid ${primary ? "#C9A97F" : "#5C4430"};box-shadow:0 2px 0 #1E1813"><div style="font-size:15px;color:${CREAM}">${label}</div><div style="font-size:11px;color:${primary ? "#F1E6CF" : MUTE};opacity:.9">${sub}</div></div>`;
    return `<div style="height:${667 - PIC_H}px;background:#3C2F25;border-top:3px solid #1E1813;padding:8px 16px 0;font-family:${SONG};color:${CREAM};position:relative">
      <div style="position:absolute;right:12px;top:6px;font-size:16px;color:${MUTE}">✕</div>
      <div style="display:flex;align-items:center">${dot(sd, true)}<span style="font-size:19px;color:${CREAM}">${esc(p.name)}</span><span style="font-size:12px;color:${MUTE};margin-left:8px">${sd ? sd.name + "軍地" : s.tug ? "正在翻" : "無主"}・${esc(p.terrain || "")}</span></div>
      <div style="font-size:12.5px;color:${MUTE};margin:4px 0 8px 26px">${esc(p.mostly || "")}${s.odds ? "・勝算 " + esc(s.odds.word) : ""}${s.yield ? "・" + esc(s.yield) : ""}</div>
      <div style="display:flex;gap:10px">${btn(`步行 ${s.minutes ?? ""} 分`, "沿路可以做小事", true)}${btn("疾行", `立刻到・體力 ${s.stamina ?? ""}`, false)}</div>
      <div style="font-size:12.5px;color:${CREAM};margin-top:10px;line-height:1.5"><span style="color:${MUTE}">此地的對手</span>　${squads || "—"}</div>
      <div style="font-size:12px;color:${MUTE};margin-top:2px">${esc(s.fierce || "")} ${esc(s.price || "")}</div>
    </div>`;
  }

  // ─────────── 燈下（第 4 輪）：第一眼只亮跟你有關的 ───────────
  // n＝亮幾步路：1 是你＋腳下走得到的，2 再多一圈。其餘的只剩暗暗的小釘，沒有名字；
  // 遠的但跟你有關的（本週、正在翻、有寶、有賞）掛在托盤邊上當指針，寫名字與幾分。
  function lamp(d, n, pickId) {
    // 點了一處：亮的照舊；點的是暗釘就把那一枚點亮（名字、棋子都出來），圖框也把它包進來
    const lit = d.places.filter((p) => (d.hops[p.id] ?? 99) <= n || p.id === pickId);
    const litSet = new Set(lit.map((p) => p.id));
    const f = fitter(lit.map((p) => [p.x, p.y]), TOP + 26, PIC_H - TRAY - 30, 46);
    const g = [defs, `<rect width="${W}" height="${PIC_H}" fill="${SAND}"/><rect width="${W}" height="${PIC_H}" filter="url(#grain)"/>`];
    g.push(terrainSvg(d, f, 0.8));
    const polyPx = d.pts.map(([x, y]) => `${f.X(x).toFixed(1)},${f.Y(y).toFixed(1)}`).join(" ");
    g.push(`<path d="M-200,-200H${W + 200}V${PIC_H + 200}H-200Z M${polyPx.replace(/ /g, "L")}Z" fill="#3A2C1E" fill-rule="evenodd" opacity=".12"/>`);
    // 路：亮的那幾條粗、其餘細且淡
    const near = d.places.filter((p) => Math.abs(f.X(p.x) - W / 2) < W && Math.abs(f.Y(p.y) - PIC_H / 2) < PIC_H).map((p) => p.id);
    g.push(roadsSvg(d, f, near, `stroke="${CORD}" stroke-width="${(1.2 / f.s).toFixed(2)}" opacity=".45"`).svg);
    const litRoads = []; for (const [a, b, cx, cy] of d.base.roads) if (litSet.has(a) && litSet.has(b) && (a === d.here || b === d.here || n > 1)) { const pa = d.byId[a], pb = d.byId[b]; litRoads.push(`M${pa.x},${pa.y}Q${cx},${cy} ${pb.x},${pb.y}`); }
    g.push(`<g transform="${f.tr}"><path d="${litRoads.join("")}" fill="none" stroke="${CORD}" stroke-width="${(2.6 / f.s).toFixed(2)}" stroke-linecap="round"/></g>`);
    // 燈：你腳下一圈亮，外面暗下去
    const hx = f.X(d.hp.x), hy = f.Y(d.hp.y);
    const reach = Math.max(...lit.map((p) => Math.hypot(f.X(p.x) - hx, f.Y(p.y) - hy))) + 58;
    g.push(`<defs><radialGradient id="lampg" gradientUnits="userSpaceOnUse" cx="${hx}" cy="${hy}" r="${reach * 1.35}"><stop offset="${(reach / (reach * 1.35)).toFixed(3)}" stop-color="#3A2C1E" stop-opacity="0"/><stop offset="1" stop-color="#3A2C1E" stop-opacity=".30"/></radialGradient></defs><rect width="${W}" height="${PIC_H}" fill="url(#lampg)"/>`);
    // 暗處的小釘
    for (const p of d.places) if (!litSet.has(p.id)) { const x = f.X(p.x), y = f.Y(p.y); if (x < TRAY + 8 || x > W - TRAY - 8 || y < TOP || y > PIC_H - TRAY - 8) continue; const st = d.S[p.id] || {}; const sd = sideOf(st.control);
      g.push(`<circle cx="${x}" cy="${y}" r="${p.big ? 6 : 5}" fill="${sd ? sd.color : "#9A9283"}" stroke="${DARK}" stroke-width="1" opacity=".55"/>`); }
    // 點了一處：從你到那裡的路點亮
    const PS = pickId && d.S[pickId];
    if (PS && PS.path) {
      const chain = [d.here, ...PS.path]; const segs = [];
      for (let i = 0; i + 1 < chain.length; i++) { const a = d.byId[chain[i]], b = d.byId[chain[i + 1]]; const c = d.roadOf[`${chain[i]}|${chain[i + 1]}`] || [(a.x + b.x) / 2, (a.y + b.y) / 2]; segs.push(`M${a.x},${a.y}Q${c[0]},${c[1]} ${b.x},${b.y}`); }
      g.push(`<g transform="${f.tr}"><path d="${segs.join("")}" fill="none" stroke="${DARK}" stroke-width="${(6 / f.s).toFixed(2)}" opacity=".5" stroke-linecap="round"/><path d="${segs.join("")}" fill="none" stroke="${CREAM}" stroke-width="${(3.2 / f.s).toFixed(2)}" stroke-linecap="round"/></g>`);
    }
    // 亮的棋子與名字牌（名字後面帶幾分）
    const tokens = lit.map((p) => ({ p, st: d.S[p.id] || {}, r: p.id === d.here ? 19 : p.big ? 16 : 13, x: f.X(p.x), y: f.Y(p.y) }));
    const prio = (t) => (t.p.id === d.here || t.p.id === pickId ? 0 : (d.hops[t.p.id] === 1 ? 1 : 2));
    const want = tokens.map((t) => { const m = t.st.minutes; const n2 = t.p.name.replace(/（.*）/, "") + (t.p.id === d.here ? "" : `・${m ?? "?"}分`); return { t, n: n2, w: n2.length * 10.5 + 9, h: 16, pr: prio(t) }; }).sort((a, b) => a.pr - b.pr);
    placeLabels(tokens, want);
    for (const t of tokens) if (t.p.id !== pickId) g.push(tokenSvg(t, d, { pick: pickId, dim: !!pickId }));
    for (const l of want) { const { t, n, w, h, x, y } = l; const isHere = t.p.id === d.here, isPick = t.p.id === pickId;
      if (l.lead) g.push(`<path d="M${t.x},${t.y}L${x},${y}" stroke="${DARK}" stroke-width="1" opacity=".55"/>`);
      g.push(`<rect x="${x - w / 2}" y="${y - h / 2}" width="${w}" height="${h}" rx="2.5" fill="${isHere ? RED : isPick ? CREAM : DARK}" opacity="${pickId && !isHere && !isPick ? ".72" : ".92"}"/><text x="${x}" y="${y + 4}" font-size="11" text-anchor="middle" fill="${isPick ? DARK : "#F4ECDC"}" font-weight="${isPick ? 700 : 400}" style="font-family:${SONG}">${esc(n)}</text>`); }
    const pt = tokens.find((t) => t.p.id === pickId); if (pt) g.push(tokenSvg({ ...pt, r: pt.r + 3 }, d, { pick: pickId }));
    // 托盤邊上的指針：遠的但跟你有關的
    // 只掛走得到的（15 分內）、最多三個；本週的不管多遠都掛
    const far = d.places.filter((p) => !litSet.has(p.id)).map((p) => ({ p, st: d.S[p.id] || {} })).filter(({ p, st }) => (d.week && d.week.id === p.id) || ((st.rich || st.tug || st.melee || st.bounty) && (st.minutes ?? 99) <= 15)).sort((a, b) => (a.st.minutes || 99) - (b.st.minutes || 99)).slice(0, 3);
    const pills = [];
    for (const { p, st } of far) {
      const dx = f.X(p.x) - hx, dy = f.Y(p.y) - hy, L = Math.hypot(dx, dy) || 1; const ux = dx / L, uy = dy / L;
      const inset = 24; let t = Infinity;
      if (ux > 0) t = Math.min(t, (W - TRAY - inset - hx) / ux); if (ux < 0) t = Math.min(t, (TRAY + inset - hx) / ux);
      if (uy > 0) t = Math.min(t, (PIC_H - TRAY - inset - hy) / uy); if (uy < 0) t = Math.min(t, (TOP + 10 - hy) / uy);
      const x = hx + ux * t, y = hy + uy * t;
      const why = d.week && d.week.id === p.id ? "本週" : st.tug || st.melee ? "正在翻" : st.rich ? "有寶" : "有賞";
      const label = `${why}・${p.name.replace(/（.*）/, "")}・${st.minutes ?? "?"}分`; const w = label.length * 10.5 + 14;
      const cx = Math.max(TRAY + w / 2 + 4, Math.min(W - TRAY - w / 2 - 4, x)); let cy = Math.max(TOP + 8, Math.min(PIC_H - TRAY - 12, y));
      for (let k = 0; k < 6; k++) { const clash = pills.find((o) => Math.abs(o.x - cx) < (o.w + w) / 2 && Math.abs(o.y - cy) < 20); if (!clash) break; cy = clash.y + (uy >= 0 ? -22 : 22); }
      pills.push({ x: cx, y: cy, w });
      g.push(`<g filter="url(#shadow)"><rect x="${cx - w / 2}" y="${cy - 9}" width="${w}" height="18" rx="9" fill="${why === "本週" ? RED : "#4A3B2E"}" stroke="${DARK}"/><text x="${cx}" y="${cy + 4}" font-size="11" text-anchor="middle" fill="${CREAM}" style="font-family:${SONG}">${esc(label)}</text><path d="M${cx + ux * (w / 2 + 2)},${cy + uy * 11}l${ux * 7},${uy * 7}" stroke="${CREAM}" stroke-width="2.2" stroke-linecap="round"/></g>`);
    }
    g.push(tray());
    g.push(tag(14, 118, `${esc(d.region.name)} ▾`, false)); g.push(tag(W - 134, 56, "全區", false)); g.push(tag(W - 72, 58, "天下", false));
    const svg = `<svg width="${W}" height="${PIC_H}" viewBox="0 0 ${W} ${PIC_H}" style="display:block">${g.join("")}</svg>`;
    return `<div style="background:#3C2F25;height:100%">${svg}${pickId ? cardPanel(d, pickId) : nowPanel(d)}</div>`;
  }
  function nowPanel(d) {
    const wk = d.week && d.byId[d.week.id]; const ws = wk && (d.S[wk.id] || {});
    const weekRow = wk ? `<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 8px;margin:4px -8px 2px;border-radius:4px;background:rgba(168,50,42,.22);border:1px solid rgba(240,180,168,.35)"><div><span style="font-size:11px;color:#F0B4A8;border:1px solid #F0B4A8;border-radius:2px;padding:0 4px;margin-right:8px">本週</span><span style="font-size:16px;color:${CREAM}">${esc(wk.name.replace(/（.*）/, ""))}</span><span style="font-size:12px;color:#F0B4A8;margin-left:8px">${esc((d.week.why || "").split("・").slice(1).join("・"))}</span></div><div style="font-size:13px;color:#E6D8BD">步行 ${ws.minutes ?? ""} 分 ›</div></div>` : "";
    const rows = d.exits.filter(({ p }) => !(wk && wk.id === p.id)).map(({ p, s }) => { const sd = sideOf(s.control);
      return `<div style="display:flex;justify-content:space-between;align-items:center;padding:4px 0;border-bottom:1px solid rgba(255,255,255,.08)"><div>${dot(sd)}<span style="font-size:15px;color:${CREAM}">${esc(p.name.replace(/（.*）/, ""))}</span><span style="font-size:12px;color:${MUTE};margin-left:8px">${esc(p.mostly || "")}${s.odds ? "・" + esc(s.odds.word) : ""}</span></div><div style="font-size:13px;color:#E6D8BD">步行 ${s.minutes ?? ""} 分 ›</div></div>`; }).join("");
    return `<div style="height:${667 - PIC_H}px;background:#3C2F25;border-top:3px solid #1E1813;padding:6px 16px 0;font-family:${SONG};color:${CREAM}"><div style="display:flex;justify-content:space-between;align-items:baseline"><div style="font-size:12px;color:${MUTE}">當下</div><div style="font-size:12px;color:${MUTE}">你在 <b style="color:#F0B4A8;font-weight:400">${esc(d.hp.name)}</b></div></div>${weekRow}${rows}</div>`;
  }

  // ─────────── 天下 ───────────
  function world(d) {
    const [fx0, fy0, fx1, fy1] = d.base.world.frame;
    const f = fitter([[fx0, fy0], [fx1, fy1]], TOP + 4, PIC_H - TRAY - 6, 10);
    const g = [defs, `<rect width="${W}" height="${PIC_H}" fill="${SAND}"/><rect width="${W}" height="${PIC_H}" filter="url(#grain)"/>`];
    // 五個區各是一塊壓出來的盤
    for (const r of d.base.world.regions) { const pp = d.toPts(r.d).map(([x, y]) => `${f.X(x).toFixed(1)},${f.Y(y).toFixed(1)}`).join(" "); const mine = r.id === d.rid;
      g.push(`<polygon points="${pp}" fill="${mine ? "#E6DAB8" : "#DCCDA8"}" stroke="#6B5A3E" stroke-width="1.4" opacity=".95"/><polygon points="${pp}" fill="none" stroke="#F3EAD2" stroke-width=".8" opacity=".7" transform="translate(0,-1)"/>`); }
    g.push(terrainSvg(d, f, 1.6));
    g.push(roadsSvg(d, f, d.places.map((p) => p.id), `stroke="${CORD}" stroke-width="${(0.9 / f.s).toFixed(2)}" opacity=".75"`).svg);
    const tokens = d.places.map((p) => ({ p, st: d.S[p.id] || {}, r: p.id === d.here ? 9 : p.big ? 5.5 : 4.2, x: f.X(p.x), y: f.Y(p.y) }));
    for (const t of tokens) if (t.p.id !== d.here) g.push(tokenSvg(t, d, {}));
    g.push(tokenSvg(tokens.find((t) => t.p.id === d.here), d, {}));
    for (const r of d.base.regions) { const x = f.X(r.cx), y = f.Y(r.cy), w = r.name.length * 12 + 12; g.push(`<g filter="url(#shadow)"><rect x="${x - w / 2}" y="${y - 10}" width="${w}" height="20" rx="2.5" fill="${WOOD}" stroke="${WOOD2}"/><text x="${x}" y="${y + 4.5}" font-size="12" text-anchor="middle" fill="${CREAM}" style="font-family:${SONG}">${esc(r.name)}</text></g>`); }
    g.push(`<g transform="translate(${W - 30},${PIC_H - 34})"><path d="M0,-12L3.5,0L0,12L-3.5,0Z" fill="${DARK}"/><text y="-15" font-size="9" text-anchor="middle" fill="${DARK}" style="font-family:${SONG}">北</text></g>`);
    g.push(tray());
    g.push(tag(14, 118, `${esc(d.region.name)} ▾`, false)); g.push(tag(W - 72, 58, "天下", true));
    const svg = `<svg width="${W}" height="${PIC_H}" viewBox="0 0 ${W} ${PIC_H}" style="display:block">${g.join("")}</svg>`;
    // 底下：三條戰線的繩，加上天下的寶在哪
    const ropes = (d.st.ropes || []).map((r) => { const lo = SIDE[r.low], hi = SIDE[r.high]; const v = Math.max(0, Math.min(100, r.value));
      return `<div style="padding:4px 0;border-bottom:1px solid rgba(255,255,255,.08)"><div style="display:flex;justify-content:space-between;font-size:12px;color:${MUTE}"><span style="color:${CREAM};font-size:14px">${esc(r.name)}</span><span>${r.delta ? (r.delta > 0 ? "▲" : "▼") + Math.abs(r.delta) : "持平"}</span></div><div style="display:flex;align-items:center;gap:8px;margin-top:4px"><span style="font-size:12px;color:${lo.color};background:#F1E6CF;border-radius:2px;padding:0 4px">${lo.name}</span><div style="flex:1;height:6px;border-radius:3px;background:linear-gradient(90deg,${lo.color},${hi.color});position:relative"><div style="position:absolute;left:calc(${v}% - 6px);top:-4px;width:12px;height:14px;border-radius:3px;background:${CREAM};border:1.5px solid #1E1813"></div></div><span style="font-size:12px;color:${hi.color};background:#F1E6CF;border-radius:2px;padding:0 4px">${hi.name}</span></div></div>`; }).join("");
    const rich = d.places.filter((p) => (d.S[p.id] || {}).rich).map((p) => esc(p.name.replace(/（.*）/, ""))).join("、");
    return `<div style="background:#3C2F25;height:100%">${svg}<div style="height:${667 - PIC_H}px;background:#3C2F25;border-top:3px solid #1E1813;padding:8px 16px 0;font-family:${SONG};color:${CREAM}"><div style="display:flex;justify-content:space-between;align-items:baseline"><div style="font-size:12px;color:${MUTE}">三條戰線</div><div style="font-size:12px;color:${MUTE}">第 ${d.st.now_week} 週／${d.st.weeks_total}</div></div>${ropes}<div style="font-size:11.5px;color:${MUTE};margin-top:5px;line-height:1.35">寶在 <span style="color:${CREAM}">${rich || "—"}</span></div></div></div>`;
  }

  // txBoard('lamp', 亮幾步, 點的地點 id)
  window.txBoard = async (mode, a, b) => { const d = await data(); mount(mode === "world" ? world(d) : mode === "lamp" ? lamp(d, a || 2, b) : region(d, a)); return { mode, a, b }; };
})();
