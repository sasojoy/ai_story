// W2 QA 共用：開無頭 Chromium、登入、換視窗、打開輿圖、CDP 觸控（Input.dispatchTouchEvent）、量測。
import { launch, newPage, sleep } from "./cdp.mjs";
import fs from "node:fs";
import path from "node:path";

export const SP = "C:/Users/ray61/AppData/Local/Temp/claude/C--Ray--------/86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444/scratchpad/w2b";
export const ORIGIN = "http://w2b.localhost:8183";
export { sleep };

export async function start(port, tag) {
  const dataDir = path.join(SP, "out", `prof-${tag}-${Date.now()}`);
  const { proc, cdp } = await launch({ port, dataDir });
  const page = await newPage(cdp);
  const log = { console: [], exceptions: [], net: [], logEntries: [] };
  const reqs = new Map();
  cdp.on((m) => {
    if (m.sessionId !== page.sid) return;
    if (m.method === "Runtime.consoleAPICalled" && (m.params.type === "error" || m.params.type === "warning" || m.params.type === "assert")) {
      log.console.push({ type: m.params.type, text: (m.params.args || []).map((a) => a.value ?? a.description ?? "").join(" ").slice(0, 300) });
    }
    if (m.method === "Runtime.exceptionThrown") log.exceptions.push(JSON.stringify(m.params.exceptionDetails).slice(0, 400));
    if (m.method === "Log.entryAdded" && (m.params.entry.level === "error" || m.params.entry.level === "warning")) log.logEntries.push({ level: m.params.entry.level, src: m.params.entry.source, text: m.params.entry.text.slice(0, 300), url: m.params.entry.url || "" });
    if (m.method === "Network.requestWillBeSent") reqs.set(m.params.requestId, m.params.request.url);
    if (m.method === "Network.responseReceived" && m.params.response.status >= 400) log.net.push({ status: m.params.response.status, url: m.params.response.url });
    if (m.method === "Network.loadingFailed" && !m.params.canceled) log.net.push({ status: "failed", url: reqs.get(m.params.requestId) || "", err: m.params.errorText });
  });
  await page.send("Page.enable");
  await page.send("Runtime.enable");
  await page.send("Log.enable");
  await page.send("Network.enable");
  await page.send("Network.setCacheDisabled", { cacheDisabled: true });
  return { proc, cdp, page, log, dataDir };
}

export async function stop(ctx) {
  try { ctx.cdp.close(); } catch (e) { /* */ }
  try { ctx.proc.kill(); } catch (e) { /* */ }
  await sleep(500);
}

export async function view(page, { w, h, dark = false, mobile = true }) {
  await page.send("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: 2, mobile });
  await page.send("Emulation.setTouchEmulationEnabled", { enabled: mobile, maxTouchPoints: mobile ? 5 : 1 });
  await page.send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: dark ? "dark" : "light" }, { name: "prefers-reduced-motion", value: "reduce" }] });
}

export async function login(page, account) {
  await page.send("Page.navigate", { url: ORIGIN + "/" });
  await sleep(1500);
  const pw = fs.readFileSync(path.join(SP, "local", `${account}_password.txt`), "utf8").trim();
  const st = await page.eval(`fetch("/api/login", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({login: ${JSON.stringify(account)}, password: ${JSON.stringify(pw)}})}).then((r) => r.status)`);
  return st;
}

export async function dismiss(page) {
  for (let i = 0; i < 5; i++) {
    const hit = await page.eval(`(() => { const b = [...document.querySelectorAll("button")].find((e) => /^(收下|知道了|好)$/.test(e.textContent.trim()) && e.getClientRects().length); if (b) b.click(); return !!b; })()`);
    if (!hit) break;
    await sleep(700);
  }
}

export async function reload(page) {
  await page.send("Page.navigate", { url: ORIGIN + "/" });
  for (let i = 0; i < 40; i++) {
    await sleep(250);
    if (await page.eval(`!!(window.S && S.main && document.querySelector(".tabs"))`).catch(() => false)) break;
  }
  await sleep(500);
  await dismiss(page);
}

export async function mapReadyWait(page) {
  for (let i = 0; i < 80; i++) {
    if (await page.eval(`!!(S.tab === "map" && S.mapCam && document.querySelector("#mvw .mv-base.on") && document.querySelector("#mkt .mv-pin, #mkt .mv-dot") && document.querySelector("#mk .ld-fill"))`).catch(() => false)) break;
    await sleep(250);
  }
  await sleep(1200);
}

export async function openMap(page) {
  await page.eval(`goTab("map")`);
  await mapReadyWait(page);
}

// ── CDP 觸控 ──
export async function tap(page, x, y) {
  await page.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x, y, id: 1 }] });
  await sleep(50);
  await page.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
}
export async function click(page, x, y) {
  await page.send("Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
  await page.send("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", clickCount: 1 });
  await sleep(40);
  await page.send("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", clickCount: 1 });
}
export async function drag(page, [x0, y0], [x1, y1], steps = 20, frame = 16, onStep = null) {
  await page.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x: x0, y: y0, id: 1 }] });
  for (let i = 1; i <= steps; i++) {
    const t = i / steps;
    await page.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x: x0 + (x1 - x0) * t, y: y0 + (y1 - y0) * t, id: 1 }] });
    await sleep(frame);
    if (onStep) await onStep(i);
  }
  await sleep(60); // 停一下再放手：不要順著滑
  await page.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
}
export async function pinch(page, [cx, cy], d0, d1, steps = 24, frame = 16, onStep = null) {
  const pts = (d) => [{ x: cx - d / 2, y: cy, id: 1 }, { x: cx + d / 2, y: cy, id: 2 }];
  await page.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: pts(d0) });
  for (let i = 1; i <= steps; i++) {
    await page.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: pts(d0 + (d1 - d0) * (i / steps)) });
    await sleep(frame);
    if (onStep) await onStep(i);
  }
  await sleep(60);
  await page.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
}
// 觸控按一個元素（先確認 elementFromPoint 拿到的是它）
export async function tapEl(page, expr) {
  const at = await page.eval(`(() => { const b = ${expr}; if (!b) return null; const r = b.getBoundingClientRect(); if (!r.width) return { zero: true };
    const x = r.left + r.width / 2, y = r.top + r.height / 2, e = document.elementFromPoint(x, y); return { x, y, top: !!e && (e === b || b.contains(e)), hit: e ? (e.className && e.className.baseVal !== undefined ? e.className.baseVal : e.className) + "" : null, text: b.textContent.trim().slice(0, 60) }; })()`);
  if (!at || at.zero) return at;
  await tap(page, at.x, at.y);
  return at;
}

export async function shot(page, file) {
  const s = await page.send("Page.captureScreenshot", { format: "png" });
  fs.writeFileSync(file, Buffer.from(s.data, "base64"));
}

// ── 量測（頁面裡跑；步數、Z0、該寫的名字、區名都在這裡自己算，不叫 map.js 裡的同一支） ──
export const MEASURE = `(() => {
  const wrap = document.getElementById("map"), g = mapGeom(wrap), c = S.mapCam, base = S.mapBase, st = S.mapState;
  const box = wrap.getBoundingClientRect();
  const drawer = document.getElementById("mdrawer"), dr = drawer ? drawer.getBoundingClientRect() : null;
  const desk = matchMedia("(min-width: 900px)").matches;
  const bottom = desk || !dr ? g.vh : Math.max(0, Math.min(g.vh, dr.top - box.top));
  const room = mapRoom(g);
  const v = Object.assign({ open_units: 250, open_width_max: 480, zoom_max: 1.6, near_from: 0.8, mid_from: 0.45, named_hops_near: 2, named_hops_mid: 1, switch_zoom: 0.6 }, base.view || {});
  const Z0 = Math.min(g.vw, v.open_width_max) / v.open_units;
  const lvlExp = c.z < Z0 * v.mid_from - 1e-9 ? 0 : c.z < Z0 * v.near_from - 1e-9 ? 1 : 2;
  const adj = {};
  for (const [a, b] of base.edges || []) { (adj[a] = adj[a] || []).push(b); (adj[b] = adj[b] || []).push(a); }
  const from = st.journey ? null : st.here, hops = {};
  if (from) { hops[from] = 0; const q = [from]; for (let i = 0; i < q.length; i++) for (const n of adj[q[i]] || []) if (!(n in hops)) { hops[n] = hops[q[i]] + 1; q.push(n); } }
  const P = Object.fromEntries(base.places.map((b) => [b.id, b]));
  const scr = (x, y) => [c.x + x * c.z, c.y + y * c.z];
  const R = (e) => { const r = e.getBoundingClientRect(); return [r.left - box.left, r.top - box.top, r.right - box.left, r.bottom - box.top]; };
  const shownEl = (e) => e.getClientRects().length && getComputedStyle(e).visibility !== "hidden" && getComputedStyle(e).display !== "none";
  const all = (sel) => [...document.querySelectorAll(sel)].filter(shownEl);
  const X = (a, b) => Math.min(a[2], b[2]) - Math.max(a[0], b[0]) > 0.5 && Math.min(a[3], b[3]) - Math.max(a[1], b[1]) > 0.5;
  const rs = (r) => r.map((n) => Math.round(n * 10) / 10).join(",");
  const lvlDom = document.querySelector("#mkt .mv-dot") ? 0 : document.querySelector("#mkt .mv-dg") ? 2 : 1;
  const labs = all("#mkt .mv-lab").map((e) => { const nm = e.querySelector(".nm"); return { id: e.dataset.id, r: R(nm), tiny: e.classList.contains("tiny"), fs: getComputedStyle(nm).fontSize, text: nm.textContent }; });
  const iconEls = all("#mkt .mv-pin img, #mkt .mv-pin svg, #mkt .mv-dg, #mkt .mv-bd, #mkt .mv-flag");
  const icons = iconEls.map((e) => ({ who: (e.closest(".mv-pin") ? e.closest(".mv-pin").dataset.id : String(e.className.baseVal ?? e.className)), r: R(e) }));
  const rings = all("#mkt .mv-ring").map(R);
  const pills = all("#mv-pills .mv-pill").map((e) => ({ id: e.dataset.id, r: R(e), text: e.textContent }));
  const hudEls = all(".mv-area, .mv-q, .mv-mini, .mv-fab button");
  const hud = hudEls.map((e) => ({ who: e.className || e.dataset.act, r: R(e) }));
  const bad = [];
  labs.forEach((a, i) => {
    labs.slice(i + 1).forEach((b) => { if (X(a.r, b.r)) bad.push("lab×lab " + a.id + " " + b.id); });
    icons.forEach((b) => { if (X(a.r, b.r)) bad.push("lab×icon " + a.id + "@" + rs(a.r) + " " + b.who + "@" + rs(b.r)); });
    rings.forEach((b) => { if (X(a.r, b)) bad.push("lab×ring " + a.id); });
    pills.forEach((b) => { if (X(a.r, b.r)) bad.push("lab×pill " + a.id + " " + b.id); });
    hud.forEach((b) => { if (X(a.r, b.r)) bad.push("lab×hud " + a.id + " " + b.who); });
  });
  pills.forEach((a, i) => {
    pills.slice(i + 1).forEach((b) => { if (X(a.r, b.r)) bad.push("pill×pill " + a.id + " " + b.id); });
    icons.forEach((b) => { if (X(a.r, b.r)) bad.push("pill×icon " + a.id + " " + b.who); });
    hud.forEach((b) => { if (X(a.r, b.r)) bad.push("pill×hud " + a.id + " " + b.who); });
    if (a.r[0] < -0.5 || a.r[1] < -0.5 || a.r[2] > g.vw + 0.5 || a.r[3] > bottom + 0.5) bad.push("pill-out " + a.id + "@" + rs(a.r));
  });
  // 名字出畫面：小圖錨點在露出來那一塊裡的，名字要整個在裡面
  const inVis = (id) => { const p = P[id]; if (!p) return false; const [sx, sy] = scr(p.x, p.y); return sx >= 0 && sx <= g.vw && sy >= 0 && sy <= bottom; };
  for (const a of labs) if (inVis(a.id) && (a.r[0] < -0.5 || a.r[1] < -0.5 || a.r[2] > g.vw + 0.5 || a.r[3] > bottom + 0.5)) bad.push("lab-out " + a.id + "@" + rs(a.r));
  // 該寫、可以寫的名字
  const lvl = lvlExp, filt = (S.mapFilter || "all") !== "all";
  const week = st.week && st.places[st.week.id] ? st.week.id : null, here = st.journey ? null : st.here;
  const sel = S.mapSel, prev = S.mapMode === "overview" ? S.mapPreview : null;
  const leg = S.mapThen && S.mapMode === "place" && S.mapSel === S.mapThen.from ? S.mapThen : null, end = leg && leg.to;
  const live = (S.mapWeek || st.now_week) === st.now_week;
  const ctrlOf = (id) => (st.places[id] && st.places[id].control) || null;
  const tugBy = (id) => { const t = st.places[id] && st.places[id].tug; if (!t) return false; return Object.entries(t).some(([sd, val]) => sd !== ctrlOf(id) && Number(val) > 0); };
  const reach = lvl === 2 ? Number(v.named_hops_near) : Number(v.named_hops_mid);
  const must = [], allow = new Set();
  for (const b of base.places) {
    const q = st.places[b.id];
    if (!q) continue;
    const h = hops[b.id];
    const special = b.id === here || b.id === sel || b.id === prev || b.id === end || b.id === week;
    const hopOk = h !== undefined && h <= reach;
    if (special || (!filt && hopOk)) { if (inVis(b.id) && lvl > 0) must.push(b.id); }
    if (special || hopOk || b.big || q.rich || (live && tugBy(b.id)) || (lvl === 2 && q.sortie)) allow.add(b.id);
  }
  const drawn = new Set(labs.map((a) => a.id));
  const missing = lvl > 0 ? must.filter((id) => !drawn.has(id)) : [];
  const extra = lvl > 0 && !filt ? [...drawn].filter((id) => !allow.has(id)) : [];
  // 兩步內接「N 分」（近景）；中景不接
  const minBad = [];
  for (const a of labs) { const h = hops[a.id]; const has = /\\d+\\s*分/.test(a.text);
    if (lvl === 2 && a.id !== here && h !== undefined && h >= 1 && h <= Number(v.named_hops_near) && st.places[a.id].minutes != null && !has) minBad.push("no-min " + a.id);
    if (lvl === 1 && has) minBad.push("mid-min " + a.id); }
  // 危險度徽：近景＝畫出來的小圖數減你；中景 0
  const pinsDom = all("#mkt .mv-pin").length, dg = all("#mkt .mv-dg").length, herePin = here && document.querySelector('#mkt .mv-pin[data-id="' + here + '"]') ? 1 : 0;
  // 區名：畫面中心（露出來那一塊的正中）落在哪一區的多邊形（Path2D 自己判）
  const cxm = (g.vw / 2 - c.x) / c.z, cym = ((room.top + room.bottom) / 2 - c.y) / c.z;
  const ctx = document.createElement("canvas").getContext("2d");
  const inReg = ((base.world && base.world.regions) || []).filter((r) => r.d && ctx.isPointInPath(new Path2D(r.d), cxm, cym)).map((r) => r.id);
  let areaExp = null;
  if (lvl === 0) areaExp = "天下";
  else {
    let rid = inReg[0] || null;
    if (!rid) { let best = Infinity; for (const b of base.places) { const d = (b.x - cxm) ** 2 + (b.y - cym) ** 2; if (st.places[b.id] && b.region && d < best) { best = d; rid = b.region; } } }
    const r = base.regions.find((x) => x.id === rid); areaExp = r ? r.name : "天下";
  }
  const areaEl = document.querySelector("#mv-area .t"), area = areaEl ? areaEl.textContent : null;
  // 小地圖白框
  const mv = document.getElementById("mv-mini-view"), miniEl = document.querySelector("#mv-mini .mv-mini");
  const miniGot = mv ? ["x", "y", "width", "height"].map((k) => Number(mv.getAttribute(k))) : null;
  const miniExp = [-c.x / c.z, -c.y / c.z, g.vw / c.z, g.vh / c.z];
  const miniErr = miniGot ? Math.max(...miniGot.map((n, i) => Math.abs(n - miniExp[i]))) : null;
  // 箭頭牌：近景、沒點地點、不在路上；腳下一步、小圖整個在露出來那一塊外面的
  const nbs = base.places.filter((b) => hops[b.id] === 1 && st.places[b.id]).map((b) => b.id);
  const pinRect = (id) => { const e = document.querySelector('#mkt .mv-pin[data-id="' + id + '"]'); if (!e) return null; const k = e.querySelector("img, svg"); return k ? R(k) : R(e); };
  const visBox = [0, 0, g.vw, bottom];
  const pillExp = lvl === 2 && S.mapMode === "overview" && !st.journey && here ? nbs.filter((id) => { const r = pinRect(id); return !r || !X(r, visBox); }) : [];
  // 底條
  const tray = document.querySelector("#mbody .m-tray");
  // 你、選的在不在露出來那一塊（上面讓開區名那一排）
  const me = st.journey ? [st.journey.x, st.journey.y] : P[st.here] ? [P[st.here].x, P[st.here].y] : null;
  const onScreen = (p, top = room.top) => { if (!p) return null; const [sx, sy] = scr(p[0], p[1]); return sx >= 0 && sx <= g.vw && sy >= top && sy <= bottom; };
  const scrOf = (p) => (p ? scr(p[0], p[1]).map((n) => Math.round(n)) : null);
  const card = document.querySelector("#mbody .m-h1 .nm");
  const route = document.getElementById("mkr");
  return {
    vw: g.vw, vh: g.vh, bottom: Math.round(bottom), roomTop: room.top, roomBottom: room.bottom, desk,
    z: +c.z.toFixed(4), Z0: +Z0.toFixed(4), zMax: +(Z0 * v.zoom_max).toFixed(4), zMin: +zMin(g).toFixed(4), lvl: lvlExp, lvlDom, lvlFn: mvLevel(c.z, g), view: v,
    center: [+cxm.toFixed(1), +cym.toFixed(1)], cam: [+c.x.toFixed(1), +c.y.toFixed(1)],
    labs: labs.map((a) => a.id), labTexts: labs.map((a) => a.id + ":" + a.text + (a.tiny ? "(11)" : "")), tiny: labs.filter((a) => a.tiny).map((a) => a.id), leads: all("#mkt .mv-lead").length,
    bad, missing, extra, minBad, must,
    pins: pinsDom, dg, herePin, dgOk: lvl === 2 ? dg === pinsDom - herePin : dg === 0,
    area, areaExp, inReg,
    mini: !!miniEl, miniW: miniEl ? Math.round(miniEl.getBoundingClientRect().width) : 0, miniGot: miniGot && miniGot.map((n) => +n.toFixed(1)), miniExp: miniExp.map((n) => +n.toFixed(1)), miniErr,
    pills: pills.map((p) => p.id), pillTexts: pills.map((p) => p.text), pillExp,
    tray: tray ? tray.textContent.replace(/\\s+/g, " ").trim() : null, drawer: S.mapDrawer, drawerPx: drawer ? drawer.offsetHeight : null,
    mode: S.mapMode, sel: S.mapSel, then: S.mapThen, filter: S.mapFilter, week: st.week, here: st.here, journey: !!st.journey,
    card: card ? card.textContent : null, route: route ? route.querySelectorAll("path").length : 0, dash: route ? route.innerHTML.includes("stroke-dasharray") : false,
    meOn: onScreen(me), selOn: sel ? onScreen(P[sel] && [P[sel].x, P[sel].y]) : null, endOn: end ? onScreen(P[end] && [P[end].x, P[end].y]) : null,
    meScr: scrOf(me), selScr: sel && P[sel] ? scrOf([P[sel].x, P[sel].y]) : null, endScr: end && P[end] ? scrOf([P[end].x, P[end].y]) : null,
    legs: all("#mkt .mv-wk.leg").map((e) => e.closest(".mv-lab").dataset.id + ":" + e.textContent), rings: rings.length,
    fabVis: (() => { const f = document.getElementById("mv-fab"); return f ? getComputedStyle(f).visibility : null; })(),
    hscroll: document.documentElement.scrollWidth > innerWidth, sw: document.documentElement.scrollWidth, iw: innerWidth,
  };
})()`;

export function saveJson(file, obj) { fs.writeFileSync(file, JSON.stringify(obj, null, 1)); }
