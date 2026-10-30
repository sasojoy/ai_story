// 輿圖風格草圖（第 2 輪）：在本機真畫面上，拿真的 /api/map/base 與 /api/map/state，
// 把輿圖分頁的地圖區整個蓋掉、用三種不同的畫法重畫「打開第一眼」。只是草圖，不是程式。
// 用法：在頁面裡載入這個檔，然後 txMock('ink' | 'board' | 'text')；txMockOff() 還原。
(() => {
  const ZH = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"];
  const zh = (n) => (n <= 10 ? ZH[n] : String(n));
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const SIDE = { guan: { name: "官", color: "#3D5F8F", pale: "#C9D6E8" }, huang: { name: "黃", color: "#B9821A", pale: "#EADFB8" } };
  const RED = "#A8322A";
  const KAI = '"DFKai-SB","BiauKai","KaiTi","Noto Serif TC",serif';
  const SONG = '"Noto Serif TC","PMingLiU","Songti TC",serif';
  const INS = { huo: "火", shui: "水", feng: "風", shan: "山" };
  const REGION_ZH = { youzhou: "幽州", jizhou: "冀州", luoyang: "洛陽", yingru: "潁川汝南", nanyang: "南陽" };
  // 這一區附近的山水（手填，只為草圖；正式做要從 mapart 的資料拿）
  const MOUNTAINS = [
    { name: "嵩山", pts: [[300, 852], [330, 838], [362, 850], [346, 872], [314, 876]] },
    { name: "桐柏山", pts: [[330, 1200], [365, 1186], [400, 1192], [432, 1210], [392, 1222], [352, 1226]] },
    { name: "伏牛山", pts: [[150, 946], [180, 936], [205, 958], [170, 976]] },
  ];
  const RIVERS = [{ name: "潁水", pts: [[290, 840], [380, 922], [470, 998], [540, 1100], [600, 1210], [650, 1330]] }];
  const FORESTS = [{ pts: [[700, 1000], [722, 990], [745, 1004], [760, 1030], [735, 1046], [712, 1032]] }];

  const PIC_H = 430; // 圖的那一塊多高（px），底下是「你在…可去」那一條
  const W = 375;

  async function data() {
    const [base, st] = await Promise.all([fetch("/api/map/base").then((r) => r.json()), fetch("/api/map/state").then((r) => r.json())]);
    const places = Object.values(base.places);
    const byId = Object.fromEntries(places.map((p) => [p.id, p]));
    const here = st.here, hp = byId[here], rid = hp.region;
    const region = base.world.regions.find((r) => r.id === rid);
    const poly = region.d.replace(/[MLZ]/g, " ").trim().split(/\s+/).map(Number);
    const pts = []; for (let i = 0; i < poly.length; i += 2) pts.push([poly[i], poly[i + 1]]);
    const inR = places.filter((p) => p.region === rid);
    const exits = base.edges.filter((e) => e.includes(here)).map((e) => (e[0] === here ? e[1] : e[0])).map((id) => ({ p: byId[id], s: st.places[id] || {} }));
    exits.sort((a, b) => (a.s.minutes || 99) - (b.s.minutes || 99));
    return { base, st, places, byId, here, hp, rid, region, pts, inR, exits, S: st.places, week: st.week };
  }

  // 把這一區的多邊形塞進圖裡（上面留給題字與按鈕）
  function fitter(pts, top, bottom, pad) {
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
    const x0 = Math.min(...xs) - pad, x1 = Math.max(...xs) + pad, y0 = Math.min(...ys) - pad, y1 = Math.max(...ys) + pad;
    const availW = W - 16, availH = bottom - top;
    const s = Math.min(availW / (x1 - x0), availH / (y1 - y0));
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    const vx0 = cx - (W / 2) / s, vy0 = cy - ((top + bottom) / 2) / s;
    return { s, X: (x) => (x - vx0) * s, Y: (y) => (y - vy0) * s };
  }

  function relax(items, iters = 80) {
    for (let k = 0; k < iters; k++) {
      let moved = false;
      for (let i = 0; i < items.length; i++) for (let j = i + 1; j < items.length; j++) {
        const a = items[i], b = items[j];
        const dx = a.x - b.x, dy = a.y - b.y;
        const ox = (a.w + b.w) / 2 + 3 - Math.abs(dx), oy = (a.h + b.h) / 2 + 2 - Math.abs(dy);
        if (ox > 0 && oy > 0) {
          moved = true;
          if (ox < oy) { const sh = (ox / 2) * (dx < 0 ? -1 : 1); a.x += sh; b.x -= sh; }
          else { const sh = (oy / 2) * (dy < 0 ? -1 : 1); a.y += sh; b.y -= sh; }
        }
      }
      for (const a of items) {
        a.x += (a.ax - a.x) * 0.06; a.y += (a.ay - a.y) * 0.06;
        a.x = Math.max(a.w / 2 + 4, Math.min(W - a.w / 2 - 4, a.x));
        a.y = Math.max(a.h / 2 + 60, Math.min(PIC_H - a.h / 2 - 6, a.y));
      }
      if (!moved) break;
    }
  }

  function roadPath(d, X, Y, a, b, c) {
    const pa = d.byId[a], pb = d.byId[b];
    return `M${X(pa.x).toFixed(1)},${Y(pa.y).toFixed(1)}Q${X(c[0]).toFixed(1)},${Y(c[1]).toFixed(1)} ${X(pb.x).toFixed(1)},${Y(pb.y).toFixed(1)}`;
  }

  function roadsSvg(d, X, Y, stroke, extra) {
    const inSet = new Set(d.inR.map((p) => p.id));
    const out = [];
    for (const [a, b, cx, cy] of d.base.roads) {
      const ia = inSet.has(a), ib = inSet.has(b);
      if (!ia && !ib) continue;
      const path = roadPath(d, X, Y, a, b, [cx, cy]);
      if (ia && ib) out.push(`<path d="${path}" fill="none" stroke="${stroke}" ${extra}/>`);
      else {
        // 通到別區的路：只畫一小截，尾巴寫往哪一區
        const inside = ia ? a : b, outside = ia ? b : a;
        const pi = d.byId[inside], po = d.byId[outside];
        const t = 0.38, mx = pi.x + (po.x - pi.x) * t, my = pi.y + (po.y - pi.y) * t;
        out.push(`<path d="M${X(pi.x).toFixed(1)},${Y(pi.y).toFixed(1)}L${X(mx).toFixed(1)},${Y(my).toFixed(1)}" fill="none" stroke="${stroke}" ${extra} stroke-dasharray="3 4"/>`);
        const ddx = po.x - pi.x, ddy = po.y - pi.y;
        out.push({ exit: true, x: X(mx), y: Y(my), name: REGION_ZH[po.region] || po.region, dir: Math.abs(ddx) > Math.abs(ddy) ? (ddx < 0 ? "←" : "→") : ddy < 0 ? "↑" : "↓" });
      }
    }
    return out;
  }

  function mount(html) {
    txMockOff();
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
  window.txMockOff = () => { document.querySelector("#tx-mock")?.remove(); const rt = document.querySelector(".r-top"); if (rt) rt.style.visibility = ""; };

  const minsZh = (n) => (n == null ? "" : `${zh(n)}分`);
  const sideOf = (s) => (s && SIDE[s]) || null;

  // ───────────────────────── 甲 木刻古輿圖 ─────────────────────────
  function ink(d) {
    const { X, Y, s } = fitter(d.pts, 64, PIC_H - 10, 30);
    const INK = "#3B3127", PAPER = "#EFE5CD", PAPER2 = "#E6DBC0";
    const g = [];
    g.push(`<defs><filter id="grain" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="3"/><feColorMatrix values="0 0 0 0 0.35 0 0 0 0 0.28 0 0 0 0 0.18 0 0 0 0.09 0"/></filter></defs>`);
    g.push(`<rect width="${W}" height="${PIC_H}" fill="${PAPER2}"/><rect width="${W}" height="${PIC_H}" filter="url(#grain)"/>`);
    const polyPx = d.pts.map(([x, y]) => `${X(x).toFixed(1)},${Y(y).toFixed(1)}`).join(" ");
    g.push(`<polygon points="${polyPx}" fill="${PAPER}" stroke="${INK}" stroke-width="1.1" stroke-dasharray="5 3" opacity=".95"/>`);
    // 山：山形紋
    for (const m of MOUNTAINS) {
      for (const [x, y] of m.pts) {
        const px = X(x), py = Y(y);
        g.push(`<path d="M${px - 9},${py + 5}L${px},${py - 8}L${px + 9},${py + 5}" fill="${PAPER}" stroke="${INK}" stroke-width="1.1" stroke-linejoin="round"/><path d="M${px - 3},${py + 1}L${px},${py - 3}L${px + 3},${py + 1}" fill="none" stroke="${INK}" stroke-width=".8"/>`);
      }
      const lx = X(m.pts[0][0]), ly = Y(m.pts[0][1]);
      g.push(`<text x="${lx - 4}" y="${ly - 12}" font-size="10" fill="${INK}" opacity=".75" style="font-family:${KAI}">${m.name}</text>`);
    }
    // 水：雙線
    for (const r of RIVERS) {
      const pth = r.pts.map(([x, y], i) => `${i ? "L" : "M"}${X(x).toFixed(1)},${Y(y).toFixed(1)}`).join("");
      g.push(`<path d="${pth}" fill="none" stroke="${INK}" stroke-width="3.2" opacity=".55"/><path d="${pth}" fill="none" stroke="${PAPER}" stroke-width="1.6"/>`);
      const [lx, ly] = r.pts[2];
      g.push(`<text x="${X(lx) - 26}" y="${Y(ly) + 4}" font-size="10" fill="${INK}" opacity=".7" style="font-family:${KAI}">${r.name}</text>`);
    }
    // 林：小樹
    for (const f of FORESTS) for (const [x, y] of f.pts) { const px = X(x), py = Y(y); g.push(`<circle cx="${px}" cy="${py - 4}" r="3.2" fill="none" stroke="${INK}" stroke-width=".9"/><path d="M${px},${py - 1}v5" stroke="${INK}" stroke-width=".9"/>`); }
    // 路：點線
    const roads = roadsSvg(d, X, Y, INK, 'stroke-width="1.1" stroke-dasharray="1.5 3" opacity=".8"');
    for (const r of roads) if (typeof r === "string") g.push(r);
    for (const r of roads) if (r.exit) g.push(`<text x="${r.x + (r.dir === "←" ? -4 : 4)}" y="${r.y + 4}" font-size="10" fill="${INK}" opacity=".75" text-anchor="${r.dir === "←" ? "end" : "start"}" style="font-family:${KAI}">${r.dir}${r.name}</text>`);
    // 地名框
    const items = d.inR.map((p) => {
      const st = d.S[p.id] || {};
      const n = p.name.replace(/（.*）/, "");
      const fs = p.big ? 13 : 11.5;
      const w = n.length * fs + 14 + (st.rich ? 12 : 0) + (sideOf(st.control) ? 12 : 0);
      return { p, st, n, fs, w, h: p.big ? 22 : 19, ax: X(p.x), ay: Y(p.y), x: X(p.x), y: Y(p.y) };
    });
    relax(items);
    const seal = (x, y, ch, color) => `<rect x="${x}" y="${y}" width="11" height="11" rx="1" fill="${color}"/><text x="${x + 5.5}" y="${y + 9}" font-size="8.5" text-anchor="middle" fill="#fff" style="font-family:${SONG}">${ch}</text>`;
    for (const it of items) {
      const { p, st, n, fs, w, h, x, y, ax, ay } = it;
      const isHere = p.id === d.here, isWeek = d.week && d.week.id === p.id;
      if (Math.hypot(x - ax, y - ay) > 9) g.push(`<path d="M${ax},${ay}L${x},${y}" stroke="${INK}" stroke-width=".8" opacity=".7"/><circle cx="${ax}" cy="${ay}" r="2" fill="${INK}"/>`);
      const sd = sideOf(st.control);
      const stroke = isHere ? RED : INK;
      g.push(`<rect x="${x - w / 2}" y="${y - h / 2}" width="${w}" height="${h}" fill="${PAPER}" stroke="${stroke}" stroke-width="${isHere ? 1.8 : 1}"/>`);
      if (p.big) g.push(`<rect x="${x - w / 2 + 2}" y="${y - h / 2 + 2}" width="${w - 4}" height="${h - 4}" fill="none" stroke="${stroke}" stroke-width=".6"/>`);
      if (st.tug) { const side = Object.keys(st.tug)[0], v = st.tug[side]; g.push(`<rect x="${x - w / 2 + 2}" y="${y + h / 2 - 4}" width="${(w - 4) * v / 100}" height="2" fill="${SIDE[side].color}"/>`); }
      let tx = x - w / 2 + 7;
      if (st.rich) { g.push(seal(tx - 1, y - 5.5, "寶", RED)); tx += 12; }
      g.push(`<text x="${tx}" y="${y + fs * 0.36}" font-size="${fs}" fill="${isHere ? RED : INK}" style="font-family:${KAI}">${esc(n)}</text>`);
      if (sd) g.push(seal(x + w / 2 - 14, y - 5.5, sd.name, sd.color));
      if (isWeek) g.push(`<path d="M${x + w / 2 - 3},${y - h / 2 + 1}v-16l12 4-12 4" fill="${RED}" stroke="${RED}" stroke-width="1"/>`);
    }
    for (const it of items) if (it.p.id === d.here) g.push(`<rect x="${it.x - it.w / 2 - 1}" y="${it.y - it.h / 2 - 13}" width="24" height="12" fill="${RED}"/><text x="${it.x - it.w / 2 + 11}" y="${it.y - it.h / 2 - 3.5}" font-size="9.5" text-anchor="middle" fill="#fff" style="font-family:${SONG}">你在</text>`);
    // 指北、內框
    g.push(`<g transform="translate(${W - 26},${PIC_H - 30})"><path d="M0,-14L4,0L0,14L-4,0Z" fill="${INK}"/><text y="-17" font-size="9" text-anchor="middle" fill="${INK}" style="font-family:${KAI}">北</text></g>`);
    g.push(`<rect x="4.5" y="4.5" width="${W - 9}" height="${PIC_H - 9}" fill="none" stroke="${INK}" stroke-width="1.6"/><rect x="8.5" y="8.5" width="${W - 17}" height="${PIC_H - 17}" fill="none" stroke="${INK}" stroke-width=".6"/>`);
    // 題字與按鈕
    g.push(`<g style="font-family:${KAI}"><rect x="16" y="16" width="28" height="118" fill="${PAPER}" stroke="${INK}" stroke-width="1"/><text x="30" y="24" font-size="15" fill="${INK}" writing-mode="tb" style="text-orientation:upright;letter-spacing:2px">${esc(d.region.name)}輿圖</text>`);
    g.push(`<rect x="${W - 60}" y="18" width="44" height="24" fill="${PAPER}" stroke="${INK}"/><text x="${W - 38}" y="35" font-size="13" text-anchor="middle" fill="${INK}">天下</text>`);
    g.push(`<rect x="${W - 112}" y="18" width="46" height="24" fill="${PAPER}" stroke="${INK}"/><text x="${W - 89}" y="35" font-size="13" text-anchor="middle" fill="${INK}">換區▾</text></g>`);
    const svg = `<svg width="${W}" height="${PIC_H}" viewBox="0 0 ${W} ${PIC_H}" style="display:block">${g.join("")}</svg>`;
    // 底下：路引
    const rows = d.exits.map(({ p, s }) => {
      const sd = sideOf(s.control), isWeek = d.week && d.week.id === p.id;
      return `<div style="display:flex;justify-content:space-between;align-items:baseline;padding:6px 0;border-bottom:1px dotted #8C7F6A"><div><span style="font-size:17px;color:${isWeek ? RED : INK}">${esc(p.name.replace(/（.*）/, ""))}</span><span style="font-size:12px;color:#6F6353;margin-left:8px">${sd ? sd.name + "軍地・" : ""}${esc(p.mostly || "")}${isWeek ? '<span style="color:' + RED + '">・本週軍令</span>' : ""}</span></div><div style="font-size:14px;color:${INK}">步行${minsZh(s.minutes)}</div></div>`;
    }).join("");
    const strip = `<div style="height:${667 - PIC_H}px;background:${PAPER};border-top:2px solid ${INK};padding:8px 16px 0;font-family:${KAI};color:${INK};position:relative"><div style="display:flex;justify-content:space-between;align-items:baseline"><div style="font-size:13px;color:#6F6353">路引</div><div style="font-size:12px;color:#6F6353">你在 <b style="color:${RED};font-weight:400">${esc(d.hp.name)}</b>・${zh(d.exits.length)}條路</div></div>${rows}</div>`;
    return `<div style="background:${PAPER};height:100%">${svg}${strip}</div>`;
  }

  // ───────────────────────── 乙 兵棋沙盤 ─────────────────────────
  function board(d) {
    const { X, Y } = fitter(d.pts, 64, PIC_H - 10, 30);
    const SAND = "#D8C9A6", SAND2 = "#CBB98F", DARK = "#2E2620", CORD = "#8B7355";
    const g = [];
    g.push(`<defs><filter id="blur" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="7"/></filter><filter id="shadow" x="-50%" y="-50%" width="200%" height="200%"><feDropShadow dx="0" dy="1.5" stdDeviation="1.2" flood-color="#000" flood-opacity=".35"/></filter><filter id="press" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="1.5"/></filter></defs>`);
    g.push(`<rect width="${W}" height="${PIC_H}" fill="${SAND}"/>`);
    for (const m of MOUNTAINS) {
      const cx = m.pts.reduce((a, p) => a + p[0], 0) / m.pts.length, cy = m.pts.reduce((a, p) => a + p[1], 0) / m.pts.length;
      g.push(`<ellipse cx="${X(cx)}" cy="${Y(cy)}" rx="${m.pts.length * 7}" ry="${m.pts.length * 4}" fill="#A99266" opacity=".55" filter="url(#blur)"/>`);
      for (const [x, y] of m.pts) g.push(`<path d="M${X(x) - 8},${Y(y) + 4}L${X(x)},${Y(y) - 6}L${X(x) + 8},${Y(y) + 4}" fill="none" stroke="#7E6A47" stroke-width="1.2" opacity=".6"/>`);
      g.push(`<text x="${X(cx)}" y="${Y(cy) - 14}" font-size="10" fill="#6B5A3E" text-anchor="middle" style="font-family:${SONG}">${m.name}</text>`);
    }
    for (const r of RIVERS) {
      const pth = r.pts.map(([x, y], i) => `${i ? "L" : "M"}${X(x).toFixed(1)},${Y(y).toFixed(1)}`).join("");
      g.push(`<path d="${pth}" fill="none" stroke="#8E9A98" stroke-width="7" opacity=".55" filter="url(#press)"/><path d="${pth}" fill="none" stroke="#B9C7C4" stroke-width="3"/>`);
      const [lx, ly] = r.pts[2];
      g.push(`<text x="${X(lx) - 28}" y="${Y(ly) + 4}" font-size="10" fill="#5F6E6B" style="font-family:${SONG}">${r.name}</text>`);
    }
    for (const f of FORESTS) for (const [x, y] of f.pts) g.push(`<circle cx="${X(x)}" cy="${Y(y)}" r="4" fill="#7E8E5C" opacity=".7"/>`);
    const polyPx = d.pts.map(([x, y]) => `${X(x).toFixed(1)},${Y(y).toFixed(1)}`).join(" ");
    g.push(`<polygon points="${polyPx}" fill="none" stroke="#6B5A3E" stroke-width="1.5" opacity=".5"/>`);
    g.push(`<path d="M0,0H${W}V${PIC_H}H0Z M${polyPx.replace(/ /g, "L")}Z" fill="#3A2C1E" fill-rule="evenodd" opacity=".13"/>`);
    const roads = roadsSvg(d, X, Y, CORD, 'stroke-width="1.6" opacity=".8"');
    for (const r of roads) if (typeof r === "string") g.push(r);
    for (const r of roads) if (r.exit) g.push(`<text x="${r.x + (r.dir === "←" ? -4 : 4)}" y="${r.y + 4}" font-size="10" fill="#5A4A33" text-anchor="${r.dir === "←" ? "end" : "start"}" style="font-family:${SONG}">${r.dir}${r.name}</text>`);
    // 棋子
    const tokens = d.inR.map((p) => ({ p, st: d.S[p.id] || {}, r: p.id === d.here ? 18 : p.big ? 15 : 12, x: X(p.x), y: Y(p.y) }));
    const labels = tokens.map((t) => { const n = t.p.name.replace(/（.*）/, ""); const w = n.length * 11 + 10; return { t, n, w, h: 15, ax: t.x, ay: t.y + t.r + 11, x: t.x, y: t.y + t.r + 11 }; });
    // 標籤避開棋子：把棋子也當成不能壓的矩形
    const blockers = tokens.map((t) => ({ x: t.x, y: t.y, w: t.r * 2, h: t.r * 2, ax: t.x, ay: t.y, fixed: true }));
    const all = [...blockers, ...labels];
    for (let k = 0; k < 80; k++) {
      let moved = false;
      for (let i = 0; i < all.length; i++) for (let j = i + 1; j < all.length; j++) {
        const a = all[i], b = all[j]; if (a.fixed && b.fixed) continue;
        const dx = a.x - b.x, dy = a.y - b.y; const ox = (a.w + b.w) / 2 + 2 - Math.abs(dx), oy = (a.h + b.h) / 2 + 2 - Math.abs(dy);
        if (ox > 0 && oy > 0) { moved = true; const m = a.fixed ? b : b.fixed ? a : null; const sign = (v) => (v < 0 ? -1 : 1);
          if (m) { const other = m === a ? b : a; if (ox < oy) m.x += ox * sign(m.x - other.x); else m.y += oy * sign(m.y - other.y); }
          else if (ox < oy) { a.x += (ox / 2) * sign(dx); b.x -= (ox / 2) * sign(dx); } else { a.y += (oy / 2) * sign(dy); b.y -= (oy / 2) * sign(dy); } }
      }
      for (const a of labels) { a.x += (a.ax - a.x) * 0.05; a.y += (a.ay - a.y) * 0.05; a.x = Math.max(a.w / 2 + 3, Math.min(W - a.w / 2 - 3, a.x)); }
      if (!moved) break;
    }
    for (const t of tokens) {
      const { p, st, r, x, y } = t; const isHere = p.id === d.here, isWeek = d.week && d.week.id === p.id;
      const sd = sideOf(st.control); const fill = isHere ? RED : sd ? sd.color : "#9A9283";
      g.push(`<g filter="url(#shadow)">`);
      if (isHere) g.push(`<circle cx="${x}" cy="${y}" r="${r + 7}" fill="none" stroke="${RED}" stroke-width="2" opacity=".45"/>`);
      g.push(`<circle cx="${x}" cy="${y}" r="${r}" fill="${fill}" stroke="${DARK}" stroke-width="1.8"/>`);
      if (st.tug) { const side = Object.keys(st.tug)[0], v = st.tug[side]; g.push(`<clipPath id="c${p.id}"><rect x="${x - r}" y="${y - r}" width="${2 * r * v / 100}" height="${2 * r}"/></clipPath><circle cx="${x}" cy="${y}" r="${r - 1}" fill="${SIDE[side].color}" clip-path="url(#c${p.id})"/>`); }
      g.push(`<circle cx="${x}" cy="${y}" r="${r - 3.5}" fill="none" stroke="#fff" stroke-opacity=".35" stroke-width="1"/>`);
      g.push(`<text x="${x}" y="${y + (isHere ? 6 : 4.5)}" font-size="${isHere ? 16 : r * 0.9}" text-anchor="middle" fill="#fff" font-weight="700" style="font-family:${SONG}">${isHere ? "你" : esc(p.glyph)}</text>`);
      g.push(`</g>`);
      if (st.rich) g.push(`<path d="M${x + r - 6},${y - r + 1}l3,-4h6l3,4l-2,3h-8z" fill="#D9A93B" stroke="#7A5A14" stroke-width=".8"/>`);
      if (isWeek) g.push(`<path d="M${x},${y}v-${r + 22}" stroke="${DARK}" stroke-width="1.6"/><path d="M${x},${y - r - 22}l16,5-16,5z" fill="${RED}" stroke="#7A1F18" stroke-width="1"/>`);
    }
    for (const l of labels) {
      const { t, n, w, h, x, y } = l; const isHere = t.p.id === d.here;
      g.push(`<rect x="${x - w / 2}" y="${y - h / 2}" width="${w}" height="${h}" rx="2.5" fill="${isHere ? RED : DARK}" opacity=".92"/><text x="${x}" y="${y + 4}" font-size="11" text-anchor="middle" fill="#F4ECDC" style="font-family:${SONG}">${esc(n)}</text>`);
    }
    // 木牌按鈕
    const tag = (x, w, label) => `<g style="font-family:${SONG}" filter="url(#shadow)"><rect x="${x}" y="16" width="${w}" height="28" rx="3" fill="#5C4430" stroke="#3A2A1C"/><rect x="${x + 2}" y="18" width="${w - 4}" height="24" rx="2" fill="none" stroke="#8C6B4A" stroke-width=".8"/><text x="${x + w / 2}" y="35" font-size="14" text-anchor="middle" fill="#F1E6CF">${label}</text></g>`;
    g.push(tag(14, 118, `${esc(d.region.name)} ▾`)); g.push(tag(W - 72, 58, "天下"));
    const svg = `<svg width="${W}" height="${PIC_H}" viewBox="0 0 ${W} ${PIC_H}" style="display:block">${g.join("")}</svg>`;
    const rows = d.exits.map(({ p, s }) => {
      const sd = sideOf(s.control), isWeek = d.week && d.week.id === p.id;
      const dot = `<span style="display:inline-block;width:14px;height:14px;border-radius:50%;background:${sd ? sd.color : "#9A9283"};border:1.5px solid #1E1813;vertical-align:-2px;margin-right:8px"></span>`;
      return `<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid rgba(255,255,255,.08)"><div>${dot}<span style="font-size:16px;color:#F1E6CF">${esc(p.name.replace(/（.*）/, ""))}</span><span style="font-size:12px;color:#B8A98E;margin-left:8px">${esc(p.mostly || "")}${isWeek ? '<span style="color:#F0B4A8">・本週軍令</span>' : ""}</span></div><div style="font-size:13px;color:#E6D8BD">步行 ${s.minutes ?? ""} 分 ›</div></div>`;
    }).join("");
    const strip = `<div style="height:${667 - PIC_H}px;background:#3C2F25;border-top:3px solid #1E1813;padding:8px 16px 0;font-family:${SONG};color:#F1E6CF"><div style="display:flex;justify-content:space-between;align-items:baseline"><div style="font-size:12px;color:#B8A98E">令牌</div><div style="font-size:12px;color:#B8A98E">你在 <b style="color:#F0B4A8;font-weight:400">${esc(d.hp.name)}</b>・${d.exits.length} 條路</div></div>${rows}</div>`;
    return `<div style="background:#3C2F25;height:100%">${svg}${strip}</div>`;
  }

  // ───────────────────────── 丙 文字路引 ─────────────────────────
  function text(d) {
    const INK = "#2E261D", PAPER = "#F6EFDD", GREY = "#7A6E5E";
    const sideTxt = (s) => { const sd = sideOf(s.control); return sd ? sd.name : s.tug ? "爭" : "無主"; };
    const exits = d.exits.map(({ p, s }) => {
      const isWeek = d.week && d.week.id === p.id; const sd = sideOf(s.control);
      return `<div style="display:flex;justify-content:space-between;align-items:baseline;padding:9px 0;border-bottom:1px solid #D9CDB2"><div><div style="font-size:18px;color:${isWeek ? RED : INK}">${esc(p.name.replace(/（.*）/, ""))}<span style="font-size:12px;color:${sd ? sd.color : GREY};margin-left:8px;border:1px solid currentColor;padding:0 3px;border-radius:2px">${sd ? sd.name + "軍" : "無主"}</span></div><div style="font-size:12.5px;color:${GREY};margin-top:2px">${esc(p.mostly || "")}${s.odds ? "・" + esc(s.odds.word) : ""}${isWeek ? '<span style="color:' + RED + '">・本週軍令：' + esc(d.week.why.split("・").slice(1).join("・")) + "</span>" : ""}</div></div><div style="font-size:15px;color:${INK};white-space:nowrap">步行${minsZh(s.minutes)} <span style="color:${GREY}">›</span></div></div>`;
    }).join("");
    const exitIds = new Set(d.exits.map((e) => e.p.id));
    const rest = d.inR.filter((p) => p.id !== d.here && !exitIds.has(p.id)).sort((a, b) => ((d.S[a.id] || {}).minutes || 99) - ((d.S[b.id] || {}).minutes || 99)).map((p) => {
      const s = d.S[p.id] || {}; const sd = sideOf(s.control);
      return `<span style="display:inline-block;margin:0 10px 6px 0;font-size:13.5px;color:${INK}">${esc(p.name.replace(/（.*）/, ""))}<span style="color:${sd ? sd.color : s.tug ? RED : GREY};font-size:11px">〔${sideTxt(s)}${s.rich ? "・寶" : ""}〕</span><span style="color:${GREY};font-size:12px">${minsZh(s.minutes)}</span></span>`;
    }).join("");
    // 小略圖：只有點與線，認方位用
    const { X, Y } = (() => { const xs = d.pts.map((p) => p[0]), ys = d.pts.map((p) => p[1]); const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys); const s = Math.min(96 / (x1 - x0), 72 / (y1 - y0)); return { X: (x) => (x - x0) * s + (104 - (x1 - x0) * s) / 2, Y: (y) => (y - y0) * s + (80 - (y1 - y0) * s) / 2 }; })();
    const inSet = new Set(d.inR.map((p) => p.id));
    const mini = [`<polygon points="${d.pts.map(([x, y]) => `${X(x).toFixed(1)},${Y(y).toFixed(1)}`).join(" ")}" fill="#EDE3CB" stroke="#B9AB8C" stroke-width=".8"/>`];
    for (const [a, b] of d.base.edges) if (inSet.has(a) && inSet.has(b)) mini.push(`<path d="M${X(d.byId[a].x)},${Y(d.byId[a].y)}L${X(d.byId[b].x)},${Y(d.byId[b].y)}" stroke="#B9AB8C" stroke-width=".7"/>`);
    for (const p of d.inR) { const s = d.S[p.id] || {}; const sd = sideOf(s.control); mini.push(`<circle cx="${X(p.x)}" cy="${Y(p.y)}" r="${p.id === d.here ? 4 : 2.3}" fill="${p.id === d.here ? RED : sd ? sd.color : "#A09887"}"/>`); }
    const thumb = `<svg width="104" height="80" viewBox="0 0 104 80">${mini.join("")}</svg>`;
    return `<div style="height:100%;background:${PAPER};font-family:${KAI};color:${INK};padding:10px 16px 0;position:relative">
      <div style="display:flex;justify-content:space-between;align-items:center;font-size:14px;color:${GREY}"><span style="color:${INK};border-bottom:1px solid ${INK}">${esc(d.region.name)} ▾</span><span>天下形勢 ›</span></div>
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-top:8px"><div><div style="font-size:13px;color:${GREY}">你在</div><div style="font-size:24px;color:${RED};line-height:1.2">${esc(d.hp.name)}</div><div style="font-size:12.5px;color:${GREY};margin-top:4px">${sideOf((d.S[d.here] || {}).control) ? sideOf(d.S[d.here].control).name + "軍地・" : ""}${esc(d.hp.terrain || "")}・${INS[d.hp.strong] || ""}氣最濃</div></div>${thumb}</div>
      <div style="margin-top:8px;font-size:12px;color:${GREY};border-bottom:1.5px solid ${INK};padding-bottom:3px">出門可到・${zh(d.exits.length)}條路</div>
      ${exits}
      <div style="margin-top:10px;font-size:12px;color:${GREY};border-bottom:1.5px solid ${INK};padding-bottom:3px;margin-bottom:6px">此區其餘</div>
      <div style="line-height:1.35">${rest}</div>
    </div>`;
  }

  window.txMock = async (style) => {
    const d = await data();
    const html = style === "ink" ? ink(d) : style === "board" ? board(d) : text(d);
    mount(html);
    return { style, places: d.inR.length, exits: d.exits.map((e) => e.p.name) };
  };
})();
