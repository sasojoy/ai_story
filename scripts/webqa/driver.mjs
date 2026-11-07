// One walk against one server. usage: node driver.mjs <label> <pageBase> <apiBase> <outDir> <chromePort>
// env: TIANXIA_WEBQA_CHROME (the browser), QA_ROUND (flows/<round>.mjs), QA_ONLY (flow names), QA_FAST (cap on crawl totals), QA_RESUME.
// Exit 0 walked; 2 could not walk (the report says why). A flow that throws is recorded in report.steps, gate.py turns it into exit 2.
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, writeFileSync, rmSync } from "node:fs";
import { join } from "node:path";
import { gzipSync } from "node:zlib";
import { freeze, landed, SHOT_VIEWS, STYLE_VIEWS, STABLE_SIG, WALK_STYLE_DUMP, LAYOUT, VOLATILE, CANVASES, DOM_TEXT, CSS_RULES } from "./snippets.mjs";

const [label, PAGE, API, OUT, CHROME_PORT] = process.argv.slice(2);
const ROUND = process.env.QA_ROUND || "c";
const { flows, ACCOUNTS } = await import(new URL(`./flows/${ROUND}.mjs`, import.meta.url));
const ONLY = (process.env.QA_ONLY || "").split(",").filter(Boolean);
const SHOTS = join(OUT, "shots"), DOM = join(OUT, "dom"), MAIN = join(OUT, "main"), STY = join(OUT, "style");
for (const d of [SHOTS, DOM, MAIN, STY]) mkdirSync(d, { recursive: true });
const CHROME = process.env.TIANXIA_WEBQA_CHROME;
const QUICK = !!process.env.QA_QUICK; // clicks, the DOM and /api/main only: no pictures, no styles
const PROFILE = join(OUT, "chrome-profile");
const PW = "qa-" + "test-only-" + "pw1"; // test value, only valid on the throwaway server
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const log = (...a) => console.log(`[${label}]`, ...a);
const sha = (b) => createHash("sha256").update(b).digest("hex").slice(0, 16);
// Nothing the walk asks takes this long. A page stuck in a loop or a dead browser never answers at all, and from then on nothing can be believed: the walk stops, exit 2.
const ANSWER_SECONDS = 120;
let dead = null;
function die(why) {
  if (dead) return;
  dead = new Error(why);
  for (const { no } of [...pending.values()]) no(dead);
  pending.clear();
}

// ---- plain API (node), cookie by hand ----
const jars = {};
async function api(who, path, body, method) {
  const headers = { "Content-Type": "application/json" };
  if (jars[who]) headers.Cookie = `tx_session=${jars[who]}`;
  const res = await fetch(API + path, { method: method || (body === undefined ? "GET" : "POST"), headers, body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(ANSWER_SECONDS * 1000) }).catch((e) => {
    if (e.name === "TimeoutError") die(`no answer from ${path} in ${ANSWER_SECONDS}s, at ${sceneNow}`);
    throw e;
  });
  const sc = res.headers.get("set-cookie");
  if (sc) { const m = /tx_session=([^;]+)/.exec(sc); if (m) jars[who] = m[1]; }
  const text = await res.text();
  let json = null;
  try { json = JSON.parse(text); } catch (e) { /* not json */ }
  report.apiCalls.push(`${who} ${path} ${res.status}`);
  return { status: res.status, json, text };
}
async function account(who, login, name, sex) {
  await api(who, "/api/register", { login, password: PW, again: PW });
  return (await api(who, "/api/character", { name, gender: sex })).status;
}
async function py(code) {
  const r = await api("_", "/__qa/py", { code });
  if (r.json && r.json.error) { log("PY ERROR", r.json.error); report.pyErrors.push(`${sceneNow}: ${code.slice(0, 80)} :: ${r.json.error.slice(-300)}`); }
  return r.json && r.json.out;
}

// ---- chrome / CDP ----
const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${CHROME_PORT}`, `--user-data-dir=${PROFILE}`, "--no-first-run", "--no-default-browser-check", "--disable-gpu", "--hide-scrollbars", "about:blank"], { stdio: "ignore" });
let ws, seq = 0, sceneNow = "(start)";
const pending = new Map();
const report = { label, round: ROUND, facts: {}, console: [], exceptions: [], http: [], failed: [], statics: {}, scenes: {}, steps: [], apiCalls: [], pyErrors: [] };
const cov = {};
async function connect() {
  for (let i = 0; i < 60; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${CHROME_PORT}/json/new?about:blank`, { method: "PUT" });
      const t = await r.json();
      ws = new WebSocket(t.webSocketDebuggerUrl);
      await new Promise((ok, no) => { ws.onopen = ok; ws.onerror = no; });
      break;
    } catch (e) { await sleep(500); }
  }
  if (!ws) throw new Error("no browser on port " + CHROME_PORT);
  ws.onclose = () => die(`the browser went away, at ${sceneNow}`);
  ws.onmessage = (m) => {
    const d = JSON.parse(m.data);
    if (d.id && pending.has(d.id)) { const { ok, no } = pending.get(d.id); pending.delete(d.id); d.error ? no(new Error(JSON.stringify(d.error))) : ok(d.result); return; }
    const p = d.params;
    if (d.method === "Page.javascriptDialogOpening") { // the page has none today; one on the head alone would hold every evaluate forever. Say so, and answer it.
      report.console.push(`${sceneNow}: dialog ${p.type}: ${p.message}`);
      cdp("Page.handleJavaScriptDialog", { accept: true }).catch(() => {});
    }
    if (d.method === "Runtime.exceptionThrown") report.exceptions.push(`${sceneNow}: ${(p.exceptionDetails.exception && p.exceptionDetails.exception.description) || p.exceptionDetails.text}`);
    if (d.method === "Runtime.consoleAPICalled" && (p.type === "error" || p.type === "warning")) report.console.push(`${sceneNow}: ${p.type}: ${p.args.map((a) => a.value || a.description || "").join(" ")}`);
    if (d.method === "Log.entryAdded" && (p.entry.level === "error" || p.entry.level === "warning")) report.console.push(`${sceneNow}: log ${p.entry.level}: ${p.entry.text} ${p.entry.url || ""}`);
    if (d.method === "Network.responseReceived") {
      const u = p.response.url;
      if (p.response.status >= 400) report.http.push(`${sceneNow}: ${p.response.status} ${u}`);
      if (u.includes("/static/") && /\.(js|css)(\?|$)/.test(u)) { const k = u.replace(PAGE, "").replace(/\?.*$/, ""); (report.statics[k] || (report.statics[k] = [])).push(p.response.status); }
    }
    if (d.method === "Network.loadingFailed" && !p.canceled) report.failed.push(`${sceneNow}: ${p.errorText} ${p.type}`);
    if (d.method === "Fetch.requestPaused") { // nothing leaves this machine: the web fonts come back empty
      const css = /\.googleapis\.com|\.gstatic\.com/.test(p.request.url);
      cdp("Fetch.fulfillRequest", { requestId: p.requestId, responseCode: 200, responseHeaders: [{ name: "Content-Type", value: css ? "text/css" : "font/woff2" }, { name: "Access-Control-Allow-Origin", value: "*" }], body: "" }).catch(() => {});
    }
  };
}
const cdp = (method, params = {}) => new Promise((ok, no) => {
  if (dead) return no(dead);
  const id = ++seq;
  const timer = setTimeout(() => die(`no answer to ${method} in ${ANSWER_SECONDS}s, at ${sceneNow}`), ANSWER_SECONDS * 1000);
  pending.set(id, { ok: (r) => { clearTimeout(timer); ok(r); }, no: (e) => { clearTimeout(timer); no(e); } });
  ws.send(JSON.stringify({ id, method, params }));
});
async function ev(expr) {
  const r = await cdp("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error("eval failed: " + ((r.exceptionDetails.exception && r.exceptionDetails.exception.description) || "").slice(0, 300) + " :: " + expr.slice(0, 80));
  return r.result.value;
}

const VIEWS = SHOT_VIEWS;
async function setView(v, dpr) {
  const [, w, h, mobile, scheme] = v;
  await cdp("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: dpr, mobile });
  await cdp("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: scheme }, { name: "prefers-reduced-motion", value: "reduce" }] });
}
// The page keeps working after a resize (fit.js measures, kiln folds): take nothing until four readings in a row agree and the new width has landed.
async function stable(width, max = 3000) {
  await sleep(120);
  const t0 = Date.now();
  let last = null, same = 0;
  while (Date.now() - t0 < max) {
    const s = await ev(STABLE_SIG).catch(() => null);
    if (s !== null && s === last) same++; else { same = 1; last = s; }
    if (same >= 4 && s !== null && landed(s, width)) return true;
    await sleep(100);
  }
  return false;
}
// A page taller than the window should have lost 15px to the scrollbar; when it did not, shrink and come back. A page that clips itself has no scrollbar to lose.
async function fixGutter(v, dpr, facts) {
  const Q = `(() => { const d = document.documentElement, b = document.body; const clip = (e) => /(hidden|clip)/.test(getComputedStyle(e).overflowY); return { sh: d.scrollHeight, ih: innerHeight, sw: d.scrollWidth, clip: clip(d) || clip(b) }; })()`;
  for (let i = 0; i < 3; i++) {
    const m = await ev(Q);
    if (m.clip || m.sh <= m.ih || m.sw !== v[1]) return;
    await setView(VIEWS[0], 1);
    await stable(VIEWS[0][1]);
    await setView(v, dpr);
    await stable(v[1]);
  }
  const m = await ev(Q);
  if (!m.clip && m.sh > m.ih && m.sw === v[1]) facts.gutterOdd = true;
}
const hashes = {};
async function grab(file) {
  const r = await cdp("Page.captureScreenshot", { format: "png", optimizeForSpeed: true });
  const buf = Buffer.from(r.data, "base64");
  hashes[file] = sha(buf);
  writeFileSync(join(SHOTS, file), buf);
}
async function dumpStyles(id, view, facts) {
  const d = await ev(WALK_STYLE_DUMP);
  facts.sty[view] = sha(d.els.map((r) => r.join(" ")).join("\n"));
  writeFileSync(join(STY, `${id}__${view}.json.gz`), gzipSync(JSON.stringify(d)));
}
// the biggest thing on screen that scrolls (the page itself, or a layer over it)
const SCROLLER = `(() => { window.__sc = null; let best = 0; const root = document.scrollingElement;
  const cand = [root, ...document.querySelectorAll("#app *")];
  for (const el of cand) { if (el.scrollHeight <= el.clientHeight + 2) continue; if (el !== root) { const cs = getComputedStyle(el); if (!/(auto|scroll)/.test(cs.overflowY) || cs.visibility === "hidden") continue; const r = el.getBoundingClientRect(); if (!r.width || !r.height || r.bottom < 0 || r.top > innerHeight) continue; const hit = document.elementFromPoint(r.left + r.width / 2, Math.max(r.top, 0) + Math.min(r.height, innerHeight) / 2); if (!hit || !(el === hit || el.contains(hit))) continue; }
    const area = el === root ? innerWidth * innerHeight * 0.5 : el.clientWidth * el.clientHeight; if (area > best) { best = area; window.__sc = el; } }
  const s = window.__sc; return s ? { sh: s.scrollHeight, ch: s.clientHeight, root: s === root } : null; })()`;
const volatileOn = async (file, facts, dpr) => { const r = await ev(VOLATILE); if (r.length) facts.vol[file] = r.map(([k, a, b, c, d]) => [k, a * dpr, b * dpr, c * dpr, d * dpr]); };
// The chronicle link greys out until the writer is done: give it a moment before the shot. A budget, so a page where it never finishes cannot eat the walk.
let taleBudget = 60000;
async function taleReady() {
  const t0 = Date.now();
  while (taleBudget > 0 && Date.now() - t0 < 5000) {
    const pendingNow = await ev(`!!document.querySelector(".huaben-link[disabled]")`).catch(() => false);
    if (!pendingNow) break;
    await sleep(200);
    taleBudget -= 200;
  }
}
let sceneN = 0;
// main scenes: dpr 2, more screens, styles on five widths; crawl scenes: dpr 1, fewer
async function shoot(name, { light = false, toast = false, who = null } = {}) {
  sceneN++;
  const id = `${String(sceneN).padStart(3, "0")}_${name}`;
  sceneNow = id;
  await settle();
  await taleReady();
  const toastText = await ev(`(() => { const t = document.querySelector("#toast"); return t && t.classList.contains("show") ? t.innerText : ""; })()`);
  if (!toast) await ev(`(() => { let s = document.getElementById("__qa_notoast"); if (!s) { s = document.createElement("style"); s.id = "__qa_notoast"; s.textContent = "#toast{visibility:hidden!important}"; document.head.appendChild(s); } })()`);
  const facts = { toast: toastText, layout: {}, shots: [], sty: {}, vol: {}, unstable: false };
  const dpr = light ? 1 : 2;
  for (const v of QUICK ? [] : VIEWS) {
    const d = v[1] > 1000 ? 1 : dpr;
    await setView(v, d);
    if (!(await stable(v[1]))) facts.unstable = true;
    if (v[1] === 1280) await fixGutter(v, d, facts);
    facts.layout[v[0]] = await ev(LAYOUT);
    const sc = await ev(SCROLLER);
    const maxScreens = v[1] > 1000 ? (light ? 2 : 3) : (light ? 3 : 6);
    if (sc) await ev(`window.__sc.scrollTop = 0; 0`); else await ev(`window.scrollTo(0, 0); 0`);
    await sleep(60);
    let f = `${id}__${v[0]}.png`;
    await grab(f); facts.shots.push(f); await volatileOn(f, facts, d);
    if (sc) {
      const step = Math.max(200, sc.ch - 90);
      for (let y = step, n = 1; y < sc.sh - sc.ch + step && n < maxScreens; y += step, n++) {
        await ev(`window.__sc.scrollTop = ${Math.min(y, sc.sh - sc.ch)}; 0`);
        await sleep(70);
        f = `${id}__${v[0]}__s${n}.png`;
        await grab(f); facts.shots.push(f); await volatileOn(f, facts, d);
      }
      await ev(`window.__sc.scrollTop = 0; 0`);
      // scrolling back folds and unfolds things (the kiln): same wait again before reading what the browser worked out
      if (facts.shots.length && facts.shots[facts.shots.length - 1].includes("__s") && !(await stable(v[1]))) facts.unstable = true;
    }
    if (v[0] === "375-light" || (!light && v[0] === "1280")) await dumpStyles(id, v[0], facts);
  }
  if (!light && !QUICK) {
    for (const v of STYLE_VIEWS) {
      await setView(v, 1);
      if (!(await stable(v[1]))) facts.unstable = true;
      facts.layout[v[0]] = await ev(LAYOUT);
      await dumpStyles(id, v[0], facts);
    }
    facts.canvas = await ev(CANVASES);
  }
  await setView(VIEWS[0], 1);
  if (!(await stable(VIEWS[0][1]))) facts.unstable = true;
  const snap = JSON.parse(await ev(DOM_TEXT));
  facts.domHash = sha(snap.body);
  writeFileSync(join(DOM, `${id}.html`), snap.body);
  writeFileSync(join(DOM, `${id}.attrs.json`), JSON.stringify(snap.html));
  facts.text = (await ev(`(document.getElementById("app") || document.body).innerText`) || "").slice(0, 600);
  facts.acts = await ev(`(() => { ${VISIBLE} const o = new Set(); for (const el of document.querySelectorAll("[data-act]")) { if (vis(el)) o.add(el.dataset.act + (el.dataset.id ? ":" + el.dataset.id : "") + (el.disabled ? "!" : "")); } return [...o]; })()`);
  if (who) {
    const m = await api(who, "/api/main");
    facts.mainHash = sha(m.text || "");
    writeFileSync(join(MAIN, `${id}.json`), m.text || "");
  }
  report.scenes[id] = facts;
  log(id, "shots", facts.shots.length, facts.unstable ? "UNSTABLE" : "", facts.gutterOdd ? "GUTTER" : "", JSON.stringify(Object.values(facts.layout).map((l) => l.cw)), "text", JSON.stringify(facts.text.slice(0, 30)));
  return facts;
}
async function settle(extra = 220) {
  for (let i = 0; i < 80; i++) {
    const n = await ev(`window.__inflight || 0`).catch(() => 0);
    if (!n) { await sleep(90); const m = await ev(`window.__inflight || 0`).catch(() => 0); if (!m) break; }
    await sleep(80);
  }
  await ev(`document.fonts ? document.fonts.ready.then(() => 1) : 1`).catch(() => 0);
  await sleep(extra);
}
async function takeCov() {
  try {
    const r = await cdp("Profiler.takePreciseCoverage");
    for (const s of r.result) {
      if (!s.url.includes("/static/")) continue;
      const k = s.url.replace(/^.*\/static\//, "").replace(/\?.*$/, "");
      const c = cov[k] || (cov[k] = {});
      for (const f of s.functions) { if (!f.functionName) continue; const hit = f.ranges.some((x) => x.count > 0); c[f.functionName] = c[f.functionName] || hit; }
    }
  } catch (e) { /* no profiler */ }
}
async function load(path = "/", { keepCards = false } = {}) {
  await takeCov();
  await cdp("Page.navigate", { url: PAGE + path });
  for (let i = 0; i < 48; i++) {
    await sleep(250);
    const ok = await ev(`document.readyState === "complete" && typeof S !== "undefined" && (S.stage !== "game" || !!S.main)`).catch(() => false);
    if (ok) break;
    if (i === 47) { log("page did not settle", path); report.steps.push(`${sceneNow} page did not settle ${path}`); }
  }
  await settle(350);
  for (let i = 0; i < 6 && !keepCards; i++) {
    const r = await ev(`(() => { const el = document.querySelector('[data-act="story-ok"]'); if (!el || el.disabled) return ""; el.click(); return "ok"; })()`);
    if (r !== "ok") break;
    report.steps.push(`${sceneNow} story-ok dismissed`);
    await settle(260);
  }
  // The daily check-in sheet opens after the story cards. Left open it locks the page and covers the lower half of a 375 shot (42cf09f90, 299 of 522 snapshots in wave E).
  if (!keepCards && await ev(`(() => { const el = document.querySelector('.ck-pop-ok'); if (!el || el.disabled) return ""; el.click(); return "ok"; })()`) === "ok") {
    report.steps.push(`${sceneNow} check-in sheet dismissed`);
    await settle(260);
  }
}
async function asPlayer(who) {
  await cdp("Network.setCookie", { name: "tx_session", value: jars[who], url: PAGE + "/", httpOnly: true, sameSite: "Lax" });
  await load();
}
async function dropCookie() { await cdp("Network.deleteCookies", { name: "tx_session", url: PAGE + "/" }); }

// ---- clicking ----
const VISIBLE = `const vis = (el) => { const r = el.getBoundingClientRect(); if (!r.width || !r.height) return false; const cs = getComputedStyle(el); return cs.visibility !== "hidden" && cs.display !== "none"; };`;
const RESEED = `if (window.__qaReseed) window.__qaReseed();`;
async function click(sel, opts = {}) {
  const out = await ev(`(() => { ${VISIBLE} const all = [...document.querySelectorAll(${JSON.stringify(sel)})]; const el = all.find(vis); if (!el) return all.length ? "hidden" : "missing"; if (el.disabled) return "disabled"; ${RESEED} if (el.click) el.click(); else el.dispatchEvent(new MouseEvent("click", { bubbles: true })); return "ok"; })()`);
  report.steps.push(`${sceneNow} click ${sel} -> ${out}`);
  if (out === "ok") await settle(opts.wait || 260);
  return out;
}
async function step(sel, name, opts = {}) { // click and shoot when it was there
  const r = await click(sel, opts);
  if (r === "ok" && name) await shoot(name, opts);
  else if (r !== "ok") log("skip", sel, r);
  return r;
}
const KEYS = (acts) => `(() => { ${VISIBLE} const acts = new Set(${JSON.stringify(acts)}); const seen = new Set(); const out = [];
  const root = document.querySelector(".shop-layer") || document; for (const el of root.querySelectorAll("[data-act]")) { const a = el.dataset.act; if (!acts.has(a) || !vis(el) || el.disabled) continue; const ds = JSON.stringify(el.dataset); const key = ds + "|" + (el.innerText || "").trim().slice(0, 16); if (seen.has(key)) continue; seen.add(key); out.push({ key, act: a }); } return out; })()`;
const clickKey = (key) => ev(`(() => { ${VISIBLE} for (const el of document.querySelectorAll("[data-act]")) { if (!vis(el) || el.disabled) continue; const ds = JSON.stringify(el.dataset); if (ds + "|" + (el.innerText || "").trim().slice(0, 16) === ${JSON.stringify(key)}) { ${RESEED} if (el.click) el.click(); else el.dispatchEvent(new MouseEvent("click", { bubbles: true })); return "ok"; } } return "missing"; })()`);
function capPerAct(list, cap) { const n = {}; return list.filter((k) => { n[k.act] = (n[k.act] || 0) + 1; return n[k.act] <= cap; }); }
async function crawl(prefix, enter, acts, { depth = 1, cap = 4, total = 40, who = null } = {}) {
  if (process.env.QA_FAST) total = Math.min(total, Number(process.env.QA_FAST));
  if (total <= 0) return;
  await enter();
  const base = await ev(KEYS(acts));
  const seen = new Set(base.map((k) => k.key));
  const queue = capPerAct(base, cap).map((k) => [k]);
  report.steps.push(`${prefix} crawl: ${base.length} keys`);
  let n = 0;
  while (queue.length && n < total) {
    const path = queue.shift();
    await enter();
    let ok = true;
    for (const s of path) {
      const r = await clickKey(s.key);
      if (r !== "ok") { ok = false; report.steps.push(`${prefix} ${s.key.slice(0, 60)} -> ${r}`); break; }
      await settle(240);
    }
    if (!ok) continue;
    n++;
    const f = await shoot(`${prefix}_c${String(n).padStart(2, "0")}_${path.map((s) => s.act).join("+")}`, { light: true, who });
    f.path = path.map((s) => s.key.slice(0, 140));
    if (path.length < depth) {
      const more = (await ev(KEYS(acts))).filter((k) => !seen.has(k.key));
      more.forEach((k) => seen.add(k.key));
      capPerAct(more, cap).forEach((k) => queue.push([...path, k]));
    }
  }
  if (queue.length) report.steps.push(`${prefix} crawl stopped with ${queue.length} left`);
}

async function loadRaw(path) {
  await takeCov();
  await cdp("Page.navigate", { url: PAGE + path });
  await sleep(1500);
  await settle(300);
}
async function drawOn(sel) { // one stroke with the mouse
  await ev(`document.querySelector(${JSON.stringify(sel)}).scrollIntoView({ block: "center" }); 0`);
  await sleep(120);
  const r = await ev(`(() => { const r = document.querySelector(${JSON.stringify(sel)}).getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; })()`);
  const at = (t) => ({ x: r.x + r.w * (0.2 + 0.6 * t), y: r.y + r.h * (0.3 + 0.4 * Math.sin(t * 6)) });
  await cdp("Input.dispatchMouseEvent", { type: "mousePressed", button: "left", clickCount: 1, buttons: 1, ...at(0) });
  for (let i = 1; i <= 24; i++) await cdp("Input.dispatchMouseEvent", { type: "mouseMoved", button: "left", buttons: 1, ...at(i / 24) });
  await cdp("Input.dispatchMouseEvent", { type: "mouseReleased", button: "left", clickCount: 1, buttons: 0, ...at(1) });
  await sleep(200);
}
async function shootRaw(name) { // a page that is not the game: no #app, no S
  sceneN++;
  const id = `${String(sceneN).padStart(3, "0")}_${name}`;
  sceneNow = id;
  const facts = { layout: {}, shots: [], sty: {}, vol: {}, unstable: false };
  for (const v of QUICK ? [] : VIEWS) {
    await setView(v, v[1] > 1000 ? 1 : 2);
    if (!(await stable(v[1]))) facts.unstable = true;
    facts.layout[v[0]] = await ev(`(() => { const d = document.documentElement; return { sw: d.scrollWidth, cw: d.clientWidth, sh: d.scrollHeight }; })()`);
    const f = `${id}__${v[0]}.png`;
    await grab(f); facts.shots.push(f);
  }
  await setView(VIEWS[0], 1);
  const html = await ev(`document.documentElement.outerHTML`);
  facts.domHash = sha(html);
  writeFileSync(join(DOM, `${id}.html`), html);
  facts.text = (await ev(`document.body.innerText`) || "").slice(0, 600);
  report.scenes[id] = facts;
  log(id, "raw shots", facts.shots.length, JSON.stringify(facts.text.slice(0, 40)));
}

// ---- what wave C learned the hard way, as tools ----
// An open page polls and plays the overlay away: leave before changing the world under it.
async function leave() { await cdp("Page.navigate", { url: "about:blank" }); await sleep(150); }
// The letter card covers the week strip: to look at the strip, decline the letters first.
async function declineLetters(who) {
  await click('[data-act="letter-open"]');
  await click('[data-act="letter-read"]');
  await click('[data-act="push-no"]');
  for (let i = 0; i < 5; i++) {
    const m = await api(who, "/api/main");
    const l = m.json && m.json.letter;
    if (!l) break;
    await api(who, "/api/do/letter_decline", { id: l.id });
    await api(who, "/api/do/letter_read", { id: l.id });
  }
  await load("/");
}
// Changing the window size redraws and clears inputs: fill right before sending.
async function fillAndSend(sel, text) {
  return ev(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); if (!e) return "missing"; e.value = ${JSON.stringify(text)}; e.dispatchEvent(new Event("input", { bubbles: true })); ${RESEED} const f = e.closest("form"); if (f) { f.requestSubmit(); return "sent"; } return "no form"; })()`);
}
// A letter of war sent while the world clock is still 0 falls through: move the clock first.
async function ffBeforeSiege() {
  await py("CLOCK['now'] += 3600; out = 1");
  await api("admin", "/api/do/fast_forward", { hours: 2 });
}
const ctx = { PAGE, shootRaw, loadRaw, drawOn, api, account, py, ev, cdp, load, asPlayer, dropCookie, shoot, step, click, crawl, settle, sleep, log, report, jars, setView, VIEWS, stable, leave, declineLetters, fillAndSend, ffBeforeSiege, tab: async (t) => { await click(`.tabs [data-act="tab"][data-tab="${t}"]`); await settle(t === "map" ? 1800 : 300); } };
let fatal = null;
try {
  await connect();
  for (const d of ["Page", "Runtime", "Log", "Network", "Profiler"]) await cdp(`${d}.enable`);
  await cdp("Profiler.startPreciseCoverage", { callCount: false, detailed: false });
  await cdp("Fetch.enable", { patterns: [{ urlPattern: "*fonts.googleapis.com*" }, { urlPattern: "*fonts.gstatic.com*" }] });
  await cdp("Page.addScriptToEvaluateOnNewDocument", { source: freeze({ mask: !process.env.QA_NO_MASK }) });
  await setView(VIEWS[0], 1);
  if (process.env.QA_RESUME) {
    for (const [w, l] of ACCOUNTS) await api(w, "/api/login", { login: l, password: PW });
    await asPlayer("p1");
  }
  for (const [name, fn] of flows) {
    if (ONLY.length && !ONLY.includes(name)) continue;
    log("== flow", name);
    sceneNow = `flow:${name}`;
    try { await fn(ctx); } catch (e) { if (dead) throw dead; report.steps.push(`FLOW ${name} threw: ${e && e.stack || e}`); log("FLOW THREW", name, String(e && e.stack || e).slice(0, 600)); }
  }
  // what the browser parsed, every stylesheet rule
  if (jars.p1) await asPlayer("p1"); else await load("/");
  writeFileSync(join(OUT, "cssrules.json"), JSON.stringify(await ev(CSS_RULES)));
  await takeCov();
} catch (e) {
  fatal = String(e && e.stack || e);
  report.fatal = fatal;
  log("FATAL", fatal);
} finally {
  report.hashes = hashes;
  writeFileSync(join(OUT, "report.json"), JSON.stringify(report, null, 1));
  writeFileSync(join(OUT, "coverage.json"), JSON.stringify(cov));
  log("scenes", Object.keys(report.scenes).length, "console", report.console.length, "exceptions", report.exceptions.length, "http4xx5xx", report.http.length, "failed", report.failed.length);
  try { ws.close(); } catch (e) { /* closing */ }
  chrome.kill();
  await sleep(1500);
  try { rmSync(PROFILE, { recursive: true, force: true, maxRetries: 5, retryDelay: 500 }); } catch (e) { log("profile left", String(e)); }
  process.exit(fatal ? 2 : 0);
}
