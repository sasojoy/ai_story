// QA 的截圖：無頭 Chromium＋CDP，動畫關掉。視窗與配色看環境變數 QA_W、QA_H、QA_SCHEME（預設 375、812、light）；回應 4xx、5xx 與 /api/sense* 記進 notes。
// boss、ring、titles 是第 12 批的場景，canvas 是第 24 批畫一筆（**沒有實際跑過**，第一次跑要驗）。換成你這一批的。
// node shots.mjs <網址> <標籤 head|base> <boss|ring|titles> <輸出資料夾> <CDP 埠> <帳號>
//   boss：江湖頁的頭目戰場景卡（打到一半）；ring：擂台那一層（打到一半）；titles：見聞 → 榜單，捲到擂台榜
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const [URL, tag, phase, outDir, cdpPort, login] = process.argv.slice(2);
const QA = process.env.QA_DIR;
const CHROME = process.env.QA_CHROME || path.join(process.env.LOCALAPPDATA || "", "ms-playwright", "chromium-1208", "chrome-win64", "chrome.exe");  // 別的系統設 QA_CHROME
const CDP = Number(cdpPort);
const W = Number(process.env.QA_W || 375), H = Number(process.env.QA_H || 812), SCHEME = process.env.QA_SCHEME || "light";
fs.mkdirSync(outDir, { recursive: true });
const profileDir = path.join(QA, "chrome", `${tag}-${phase}`);
fs.rmSync(profileDir, { recursive: true, force: true });
const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${CDP}`, `--user-data-dir=${profileDir}`, "--no-first-run", "--disable-gpu",
  "--hide-scrollbars", "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const NOTES = [];
let senseId = null;  // 第 24 批：/api/sense 那個回應的 requestId，送出之後拿內容來比
let ws;
try {
  for (let i = 0; i < 80 && !ws; i++) {
    await sleep(250);
    try {
      const list = await (await fetch(`http://127.0.0.1:${CDP}/json/list`)).json();
      const page = list.find((t) => t.type === "page");
      if (page) ws = new WebSocket(page.webSocketDebuggerUrl);
    } catch (e) { /* 還沒起來 */ }
  }
  await new Promise((r) => ws.addEventListener("open", r));
  let seq = 0;
  const waiting = new Map();
  ws.addEventListener("message", (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && waiting.has(msg.id)) { waiting.get(msg.id)(msg); waiting.delete(msg.id); return; }
    if (msg.method === "Network.responseReceived") {
      const { status, url } = msg.params.response;
      if (status >= 400) NOTES.push({ httpError: status, url: url.slice(0, 200) });
      if (url.includes("/api/sense")) NOTES.push({ route: new globalThis.URL(url).pathname, status });
      if (new globalThis.URL(url).pathname === "/api/sense") senseId = msg.params.requestId;
    }
    if (msg.method === "Runtime.exceptionThrown") NOTES.push({ exception: ((msg.params.exceptionDetails.exception || {}).description || "").slice(0, 300) });
    if (msg.method === "Runtime.consoleAPICalled" && msg.params.type === "error") NOTES.push({ consoleError: (msg.params.args || []).map((a) => a.value ?? a.description).join(" ").slice(0, 300) });
  });
  const send = (method, params = {}) => new Promise((resolve) => { const id = ++seq; waiting.set(id, resolve); ws.send(JSON.stringify({ id, method, params })); });
  const run = async (expression) => {
    const r = await send("Runtime.evaluate", { expression: `(async () => { ${expression} })()`, awaitPromise: true, returnByValue: true });
    if (r.result && r.result.exceptionDetails) return { __error: JSON.stringify(r.result.exceptionDetails).slice(0, 300) };
    return r.result && r.result.result ? r.result.result.value : undefined;
  };
  await send("Page.enable");
  await send("Runtime.enable");
  await send("Network.enable");
  await send("Network.setCacheDisabled", { cacheDisabled: true });
  // 畫一筆的點位帶 performance.now() 的毫秒，外殼凍不住；兩台換成同一顆計數，不然 /api/sense 的回應比不了
  if (phase === "canvas") await send("Page.addScriptToEvaluateOnNewDocument", { source: "(() => { let t = 1000; performance.now = () => (t += 16); })();" });
  await send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 2, mobile: W < 768 });
  await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: SCHEME }, { name: "prefers-reduced-motion", value: "reduce" }] });
  const NO_MOTION = `if (!document.getElementById("qa-nomotion")) { const st = document.createElement("style"); st.id = "qa-nomotion"; st.textContent = "*,*::before,*::after{transition:none!important;animation:none!important;caret-color:transparent!important}"; document.head.appendChild(st); } return 1;`;
  const waitFor = async (js, ms = 10000) => {
    const t0 = Date.now();
    while (Date.now() - t0 < ms) { if ((await run(`return !!(${js});`)) === true) return true; await sleep(150); }
    NOTES.push({ waitTimeout: js });
    return false;
  };
  const scrollToText = async (text) => run(`const els = [...document.querySelectorAll("#page h2, #page h3, #page h4, #page .board-title, #page summary, #page b, #page strong, #page div, #page span")].filter((e) => e.childElementCount === 0 && e.textContent.includes(${JSON.stringify(text)}) && e.getBoundingClientRect().height > 0); if (!els.length) return null; const el = els[0]; const top = document.querySelector("#top"); const head = top ? top.getBoundingClientRect().bottom : 0; scrollTo(0, Math.max(0, el.getBoundingClientRect().top + scrollY - head - 8)); return { y: Math.round(scrollY), tag: el.tagName, text: el.textContent.slice(0, 40) };`);
  const shot = async (name, sel = null, text = null) => {
    await run(NO_MOTION);
    await run(`scrollTo(0, 0); return 1;`);
    if (sel) NOTES.push({ scrollTo: sel, y: await run(`const el = document.querySelector(${JSON.stringify(sel)}); if (!el) return null; const top = document.querySelector("#top"); const head = top ? top.getBoundingClientRect().bottom : 0; scrollTo(0, Math.max(0, el.getBoundingClientRect().top + scrollY - head - 8)); return Math.round(scrollY);`) });
    if (text) NOTES.push({ scrollToText: text, at: await scrollToText(text) });
    await sleep(1500);
    const s = await send("Page.captureScreenshot", { format: "png" });
    const file = path.join(outDir, `${tag}-${name}.png`);
    fs.writeFileSync(file, Buffer.from(s.result.data, "base64"));
    const info = await run(`return { text: document.body.innerText, wide: document.documentElement.scrollWidth, inner: innerWidth };`);
    fs.writeFileSync(path.join(outDir, `${tag}-${name}.json`), JSON.stringify(info));
    NOTES.push({ shot: name, hscroll: info.wide > info.inner, bot: /假人|機器人|(^|[^a-z])bot([^a-z]|$)/i.test(info.text) });
  };
  const clickSel = async (sel) => run(`const el = [...document.querySelectorAll(${JSON.stringify(sel)})].find((e) => { const b = e.getBoundingClientRect(); return b.width > 0 && b.height > 0; }); if (!el) return false; el.click(); return true;`);

  await send("Page.navigate", { url: URL });
  await sleep(1200);
  const pw = fs.readFileSync(path.join(QA, "local", `${login}.pw`), "utf8").trim();
  const st = await run(`const r = await fetch("/api/login", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ login: ${JSON.stringify(login)}, password: ${JSON.stringify(pw)} }) }); return r.status;`);
  NOTES.push({ login: st });
  await send("Page.navigate", { url: URL });
  await sleep(1500);
  await waitFor(`document.querySelector("#top") && document.querySelector(".tabs")`, 15000);
  await sleep(1200);
  for (let k = 0; k < 6; k++) {  // 「此事已了・入傳」那幾張：按「收下」收掉（兩台一樣按），底下的畫面才看得到
    const hit = await run(`const el = [...document.querySelectorAll("button")].find((e) => e.textContent.trim() === "收下" && e.getBoundingClientRect().width > 0); if (!el) return false; el.click(); return true;`);
    NOTES.push({ dismiss: hit });
    if (!hit) break;
    await sleep(1500);
  }
  if (phase === "canvas") {
    // 第 24 批：進了感悟狀態（快照停在那一刻）。canvas 用 setPointerCapture，合成的 PointerEvent 會丟錯，一定要用 CDP 的真事件。
    NOTES.push({ open: await clickSel('[data-act="choose"][data-id="sense:draw"]') });  // 打 /api/sense_warm
    await waitFor(`document.querySelector("#sense-canvas")`);
    // 頂上的狀態列是 sticky 的，捲的時候要扣掉（同 shot()），不然第一點會按在狀態列上、整筆畫空又不報錯
    const r = await run(`const el = document.querySelector("#sense-canvas"); const top = document.querySelector("#top"); const head = top ? top.getBoundingClientRect().bottom : 0; scrollTo(0, Math.max(0, el.getBoundingClientRect().top + scrollY - head - 8)); const b = el.getBoundingClientRect(); return { x: b.x, y: b.y, w: b.width, h: b.height };`);
    const mouse = (type, x, y, buttons) => send("Input.dispatchMouseEvent", { type, x, y, button: "left", buttons, clickCount: 1 });
    // 一筆：左上到右下再折回來（讀不出來就照 tianxia/features/sense/glyph.py 的 SAMPLES 換點位，兩台要同一組）
    const pts = Array.from({ length: 24 }, (_, i) => { const t = i / 23; return [r.x + r.w * (0.2 + 0.6 * (t < 0.5 ? t * 2 : 2 - t * 2)), r.y + r.h * (0.2 + 0.6 * t)]; });
    NOTES.push({ hit: await run(`return document.elementFromPoint(${pts[0][0]}, ${pts[0][1]})?.id;`) });  // 要是 sense-canvas
    await mouse("mousePressed", pts[0][0], pts[0][1], 1);
    for (const [x, y] of pts.slice(1)) { await mouse("mouseMoved", x, y, 1); await sleep(30); }
    await mouse("mouseReleased", pts[23][0], pts[23][1], 0);  // pointerup 打 /api/sense_read
    await sleep(1500);
    await shot("canvas", "#sense-canvas");
    NOTES.push({ sendDisabled: await run(`return document.querySelector('[data-act="sense-send"]')?.disabled;`) });  // 要是 false（disabled 的鈕 click 不會有事，clickSel 照樣回 true）
    NOTES.push({ send: await clickSel('[data-act="sense-send"]') });  // 打 /api/sense
    await waitFor(`!document.querySelector("#sense-canvas")`, 30000);  // 要取名那一支要連兩趟死埠才回
    if (senseId) {
      const body = await send("Network.getResponseBody", { requestId: senseId });
      fs.writeFileSync(path.join(outDir, `${tag}-sense.json`), body.result ? body.result.body : "");
    } else NOTES.push({ noSenseResponse: true });
    await shot("after");
  } else if (phase === "boss") {
    await shot("1-boss", "#page section.card.scene");
  } else if (phase === "ring") {
    NOTES.push({ arenaLayer: await run(`return !!document.querySelector(".shop-layer.shop-arena");`) });
    await shot("2-arena");
  } else {
    NOTES.push({ tab: await clickSel('.tabs [data-tab="news"]') });
    await sleep(1500);
    NOTES.push({ boards: await clickSel('#page [data-act="news"][data-news="boards"]') });
    await sleep(2000);
    NOTES.push({ arenaBoard: await run(`const el = [...document.querySelectorAll("#page button")].find((e) => e.textContent.trim() === "擂台榜" && e.getBoundingClientRect().width > 0); if (!el) return false; el.click(); return true;`) });
    await sleep(1500);
    await shot("3-board");
  }
} finally {
  fs.writeFileSync(path.join(outDir, `${tag}-${phase}-notes.json`), JSON.stringify(NOTES, null, 1));
  try { ws && ws.close(); } catch (e) { /* */ }
  chrome.kill();
  if (process.platform === "win32") spawn("taskkill", ["/PID", String(chrome.pid), "/T", "/F"], { stdio: "ignore" });
  await sleep(800);
}
console.log(JSON.stringify(NOTES));
process.exit(0);
