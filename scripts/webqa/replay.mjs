// Replay DOM snapshots against one candidate's stylesheets: no game server, no page scripts, six windows.
// usage: node replay.mjs <label> <origin> <outDir> <chromePort> <pages.json> [--no-freeze] [--styles-only]
// env: TIANXIA_WEBQA_CHROME. The output has the shape of a walk (report.json, style/, shots/), so compare.py reads it the same way.
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import { join } from "node:path";
import { gzipSync } from "node:zlib";
import { freeze, ALL_VIEWS, SHOT_VIEWS, STABLE_SIG, STYLE_DUMP, LAYOUT, CSS_RULES } from "./snippets.mjs";

const args = process.argv.slice(2);
const flags = new Set(args.filter((a) => a.startsWith("--")));
const [label, ORIGIN, OUT, CHROME_PORT, PAGES] = args.filter((a) => !a.startsWith("--"));
const FROZEN = !flags.has("--no-freeze");
const SHOOT = !flags.has("--styles-only");
const SHOTS = join(OUT, "shots"), STY = join(OUT, "style");
for (const d of [SHOTS, STY]) mkdirSync(d, { recursive: true });
const PROFILE = join(OUT, "chrome-profile");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const sha = (b) => createHash("sha256").update(b).digest("hex").slice(0, 16);
const ANSWER_SECONDS = 120; // same as the walk: a browser that stopped answering ends the replay, exit 2
let dead = null;
function die(why) {
  if (dead) return;
  dead = new Error(why);
  for (const { no } of [...pending.values()]) no(dead);
  pending.clear();
}
const report = { label, round: "replay", facts: {}, console: [], exceptions: [], http: [], failed: [], statics: {}, scenes: {}, steps: [], apiCalls: [], pyErrors: [], hashes: {} };

const chrome = spawn(process.env.TIANXIA_WEBQA_CHROME, ["--headless=new", `--remote-debugging-port=${CHROME_PORT}`, `--user-data-dir=${PROFILE}`, "--no-first-run", "--no-default-browser-check", "--disable-gpu", "--hide-scrollbars", "about:blank"], { stdio: "ignore" });
let ws, seq = 0, sceneNow = "(start)";
const pending = new Map();
const cdp = (method, params = {}) => new Promise((ok, no) => {
  if (dead) return no(dead);
  const id = ++seq;
  const timer = setTimeout(() => die(`no answer to ${method} in ${ANSWER_SECONDS}s, at ${sceneNow}`), ANSWER_SECONDS * 1000);
  pending.set(id, { ok: (r) => { clearTimeout(timer); ok(r); }, no: (e) => { clearTimeout(timer); no(e); } });
  ws.send(JSON.stringify({ id, method, params }));
});
async function connect() {
  for (let i = 0; i < 60; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${CHROME_PORT}/json/new?about:blank`, { method: "PUT" });
      const t = await r.json();
      ws = new WebSocket(t.webSocketDebuggerUrl);
      await new Promise((ok, no) => { ws.onopen = ok; ws.onerror = no; });
      break;
    } catch (e) { await sleep(300); }
  }
  if (!ws) throw new Error("no browser on port " + CHROME_PORT);
  ws.onclose = () => die(`the browser went away, at ${sceneNow}`);
  ws.onmessage = (m) => {
    const d = JSON.parse(m.data);
    if (d.id && pending.has(d.id)) { const { ok, no } = pending.get(d.id); pending.delete(d.id); d.error ? no(new Error(JSON.stringify(d.error))) : ok(d.result); return; }
    if (d.method === "Fetch.requestPaused") { // nothing leaves this machine
      const css = /\.googleapis\.com|\.gstatic\.com/.test(d.params.request.url);
      cdp("Fetch.fulfillRequest", { requestId: d.params.requestId, responseCode: 200, responseHeaders: [{ name: "Content-Type", value: css ? "text/css" : "font/woff2" }, { name: "Access-Control-Allow-Origin", value: "*" }], body: "" }).catch(() => {});
    }
  };
}
async function ev(expr) {
  const r = await cdp("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error("eval failed: " + expr.slice(0, 80));
  return r.result.value;
}
async function setView(v, dpr) {
  const [, w, h, mobile, scheme] = v;
  await cdp("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: dpr, mobile });
  await cdp("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: scheme }, { name: "prefers-reduced-motion", value: FROZEN ? "reduce" : "no-preference" }] });
}
// no scripts on the page, so the layout only moves once: two readings in a row and the width has landed
async function stable(width) {
  let last = null;
  for (let i = 0; i < 40; i++) {
    const s = await ev(STABLE_SIG).catch(() => null);
    if (s !== null && s === last && Number(s.split("|")[0]) === width) return true;
    last = s;
    await sleep(40);
  }
  return false;
}
let fatal = null;
try {
  await connect();
  for (const d of ["Page", "Runtime"]) await cdp(`${d}.enable`);
  await cdp("Fetch.enable", { patterns: [{ urlPattern: "*fonts.googleapis.com*" }, { urlPattern: "*fonts.gstatic.com*" }] });
  await cdp("Page.addScriptToEvaluateOnNewDocument", { source: freeze({ mask: FROZEN, still: FROZEN }) });
  const pages = JSON.parse(readFileSync(PAGES, "utf-8"));
  await setView(SHOT_VIEWS[0], 1);
  for (const id of pages) {
    sceneNow = id;
    await cdp("Page.navigate", { url: `${ORIGIN}/__page/${id}` });
    for (let i = 0; i < 100; i++) {
      await sleep(50);
      if (await ev(`document.readyState === "complete" && location.pathname.endsWith(${JSON.stringify(id)})`).catch(() => false)) break;
    }
    await ev(`document.fonts ? document.fonts.ready.then(() => 1) : 1`).catch(() => 0);
    const facts = { layout: {}, shots: [], sty: {}, vol: {}, unstable: false };
    const views = SHOOT ? ALL_VIEWS : ALL_VIEWS.filter((v) => v[0] !== "375-dark");
    for (const v of views) {
      await setView(v, 1);
      if (!(await stable(v[1]))) facts.unstable = true;
      facts.layout[v[0]] = await ev(LAYOUT);
      const d = await ev(STYLE_DUMP);
      facts.sty[v[0]] = sha(d.els.map((r) => r.join(" ")).join("\n"));
      writeFileSync(join(STY, `${id}__${v[0]}.json.gz`), gzipSync(JSON.stringify(d)));
      if (SHOOT) {
        const r = await cdp("Page.captureScreenshot", { format: "png", optimizeForSpeed: true });
        const buf = Buffer.from(r.data, "base64");
        const f = `${id}__${v[0]}.png`;
        report.hashes[f] = sha(buf);
        writeFileSync(join(SHOTS, f), buf);
        facts.shots.push(f);
      }
    }
    await setView(SHOT_VIEWS[0], 1);
    report.scenes[id] = facts;
  }
  writeFileSync(join(OUT, "cssrules.json"), JSON.stringify(await ev(CSS_RULES)));
} catch (e) {
  fatal = String(e && e.stack || e);
  report.fatal = `${sceneNow}: ${fatal}`;
} finally {
  writeFileSync(join(OUT, "report.json"), JSON.stringify(report));
  try { ws.close(); } catch (e) { /* closing */ }
  chrome.kill();
  await sleep(1000);
  try { rmSync(PROFILE, { recursive: true, force: true, maxRetries: 5, retryDelay: 400 }); } catch (e) { console.log("profile left", String(e)); }
  process.exit(fatal ? 2 : 0);
}
