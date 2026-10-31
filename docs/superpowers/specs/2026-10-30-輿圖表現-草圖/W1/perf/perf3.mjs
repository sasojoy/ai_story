// node perf3.mjs <輸出資料夾> <密碼檔> <帳號> <版本 V|R|S1> <像素比> <CPU 降速倍數> <第幾輪>
// W1 後續 Task 1：地用向量（V）還是點陣（R）在手機上誰比較輕。375×812、觸控模擬開著，降速之後才打開輿圖；
// 手勢都是在 #map 上用 dispatchEvent 送合成的 PointerEvent（pointerType touch，每一幀 rAF 送一次 pointermove），網頁照 mv 判斷「還在拖縮」（mvBusy）；
// isTrusted 是 false：走網頁自己的手勢處理，瀏覽器的輸入路由、命中測試、合成執行緒的輸入處理沒跑到（那要 CDP 的 Input.dispatchTouchEvent；W1 審查 10/31）。
// 每一次（三次）：一指拖 120 幀（緩起緩停，放手不滑）→ 兩指捏 160 幀 1.15 → 2.41 → 1.15 → 兩指捏 60 幀 1.15 → 2.41 停在那裡放手
// （放手那一下換級距，地要重寫或重烤）→ 先縮到整張、等地畫好，點 ◎（回到我）飛回來。
// 量：每一幀的間隔（p50／p95／最大、超過 33ms 與 50ms 的幀數）、放手到下一幀、放手到地換好之後的那一幀（穩下來）、
// 打開輿圖到地畫出來的那一幀、打開後與做完全部手勢後的 JS heap（先 GC）、DOM 節點數、canvas 像素數、每一段手勢的
// Performance.getMetrics 增量（LayoutDuration、RecalcStyleDuration、ScriptDuration、TaskDuration）。
import { launch, newPage, sleep } from "./cdp.mjs";
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

const [, , outDir, pwFile, account, variant, dprS, thrS, rnd] = process.argv;
const DPR = Number(dprS), THR = Number(thrS);
const ORIGIN = "http://w1b.localhost:8166";
const QUERY = variant === "R" ? "/?ground=raster" : "/";
const label = `${variant}-dpr${DPR}-x${THR}-r${rnd}`;
fs.mkdirSync(outDir, { recursive: true });
const prof = path.join(outDir, "prof", `${label}-${Date.now()}`);
const { proc, cdp } = await launch({ port: 9466, dataDir: prof, extra: ["--enable-precise-memory-info"] });
const page = await newPage(cdp);

// 頁面裡的工具：地換好的時間（SVG 看 childList、canvas 看 drawImage 到 #mk）、rAF 迴圈、統計
const HOOK = `(() => {
  const d = CanvasRenderingContext2D.prototype.drawImage;
  CanvasRenderingContext2D.prototype.drawImage = function (...a) {
    const r = d.apply(this, a);
    if (this.canvas && this.canvas.id === "mk") { window.__gd = performance.now(); window.__gdn = (window.__gdn || 0) + 1; }
    return r;
  };
  window.__mkObs = null;
  window.__gw = 0; window.__gwn = 0;
  window.__watch = () => {
    const mk = document.getElementById("mk");
    if (!mk || window.__mkObs) return;
    window.__mkObs = new MutationObserver((ms) => { if (ms.some((m) => m.type === "childList")) { window.__gw = performance.now(); window.__gwn++; } });
    window.__mkObs.observe(mk, { childList: true });
  };
  window.__last = () => Math.max(window.__gd || 0, window.__gw || 0);
  window.__count = () => (window.__gdn || 0) + (window.__gwn || 0);
  window.__stat = (fr) => {
    const s = fr.slice().sort((a, b) => a - b), n = s.length;
    if (!n) return { frames: 0 };
    const q = (p) => +s[Math.min(n - 1, Math.floor(n * p))].toFixed(1);
    return { frames: n, avg: +(s.reduce((a, b) => a + b, 0) / n).toFixed(1), p50: q(0.5), p95: q(0.95), max: +s[n - 1].toFixed(1),
      over33: s.filter((x) => x > 33.4).length, over50: s.filter((x) => x > 50).length };
  };
  window.__loop = (n, fn) => new Promise((ok) => { const fr = []; let i = 0, last = 0; const step = (t) => { if (last) fr.push(t - last); last = t; if (i <= n) { fn(i / n); i++; requestAnimationFrame(step); } else ok(fr); }; requestAnimationFrame(step); });
  // 放手之後看 win 毫秒：每一幀開始的時間 ts、這一支 rAF 跑到的時間 cb、地最後一次換好的時間 lastG。
  // release＝放手後第一幀畫完（第二個 rAF）；settle＝地換好之後開始的那一幀畫完（cb 晚於 lastG 的第一幀 j，取 ts[j+1]）；地沒換＝release
  window.__frameAfter = (ts, cb, lastG) => { const j = cb.findIndex((c) => c > lastG); return j >= 0 && j + 1 < ts.length ? ts[j + 1] : null; };
  window.__settle = (t0, win) => new Promise((ok) => {
    const ts = [], cb = []; const c0 = window.__count();
    const step = (t) => { ts.push(t); cb.push(performance.now()); if (t - t0 < win || ts.length < 3) requestAnimationFrame(step); else done(); };
    const done = () => {
      const wrote = window.__count() - c0, lastG = wrote ? window.__last() : 0;
      const release = ts[1] - t0, after = wrote ? window.__frameAfter(ts, cb, lastG) : ts[1];
      const fr = ts.map((t, i) => t - (i ? ts[i - 1] : t0));
      ok({ release: +release.toFixed(1), settle: after ? +(after - t0).toFixed(1) : null, groundDone: wrote ? +(lastG - t0).toFixed(1) : null, groundWrites: wrote,
        worst: +Math.max(...fr.slice(0, 12)).toFixed(1) });
    };
    requestAnimationFrame(step);
  });
  window.__ev = (type, id, x, y) => document.getElementById("map").dispatchEvent(new PointerEvent(type, { pointerId: id, pointerType: "touch", isPrimary: id === 1,
    clientX: x, clientY: y, button: 0, buttons: type === "pointerup" ? 0 : 1, bubbles: true, cancelable: true }));
  window.__center = () => { const w = document.getElementById("map"), r = w.getBoundingClientRect(); return [r.left + w.clientWidth / 2, r.top + w.clientHeight / 2 - 80]; };
})();`;

const PREP = `(async () => {
  const g = mapGeom(document.getElementById("map")); camSet(camFirst(g), g); drawMarks();
  await new Promise((r) => setTimeout(r, 1200));
  return +S.mapCam.z.toFixed(3);
})()`;
const PAN = `(async () => {
  const [cx, cy] = __center(), c0 = __count();
  __ev("pointerdown", 1, cx, cy);
  let x = cx, y = cy;
  const fr = await __loop(120, (t) => { const e = (1 - Math.cos(Math.PI * t)) / 2; x = cx - 160 * e; y = cy - 100 * e; __ev("pointermove", 1, x, y); });
  const during = __count() - c0, t0 = performance.now();
  __ev("pointerup", 1, x, y);
  const s = await __settle(t0, 1500);
  return { ...__stat(fr), during, ...s };
})()`;
const PINCH = `(async () => {
  const [cx, cy] = __center(), c0 = __count(), zs = [];
  __ev("pointerdown", 1, cx - 50, cy); __ev("pointerdown", 2, cx + 50, cy);
  const fr = await __loop(160, (t) => { const d = 50 * (1 + 1.1 * Math.sin(t * Math.PI)); __ev("pointermove", 1, cx - d, cy); __ev("pointermove", 2, cx + d, cy); zs.push(S.mapCam.z); });
  const during = __count() - c0, t0 = performance.now();
  __ev("pointerup", 1, cx - 50, cy); __ev("pointerup", 2, cx + 50, cy);
  const s = await __settle(t0, 1500);
  return { ...__stat(fr), during, zMax: +Math.max(...zs).toFixed(2), zEnd: +S.mapCam.z.toFixed(2), ...s };
})()`;
const ZOOM = `(async () => {
  const [cx, cy] = __center(), c0 = __count();
  __ev("pointerdown", 1, cx - 50, cy); __ev("pointerdown", 2, cx + 50, cy);
  let d = 50;
  const fr = await __loop(60, (t) => { d = 50 * (1 + 1.1 * (1 - Math.cos(Math.PI * t)) / 2); __ev("pointermove", 1, cx - d, cy); __ev("pointermove", 2, cx + d, cy); });
  const during = __count() - c0, t0 = performance.now();
  __ev("pointerup", 1, cx - d, cy); __ev("pointerup", 2, cx + d, cy);
  const s = await __settle(t0, 4000);
  return { ...__stat(fr), during, zEnd: +S.mapCam.z.toFixed(2), ...s };
})()`;
const FIT = `(async () => {
  const g = mapGeom(document.getElementById("map")); camSet(camFit(g), g); drawMarks();
  await new Promise((r) => setTimeout(r, 2500));
  return +S.mapCam.z.toFixed(3);
})()`;
const FLY = `(async () => {
  const c0 = __count(), t0 = performance.now(), cams = [], ts = [], cb = [];
  document.querySelector('[data-act="map-home"]').click();
  await new Promise((ok) => { const step = (t) => { ts.push(t); cb.push(performance.now()); cams.push(S.mapCam.z + "," + S.mapCam.x + "," + S.mapCam.y); if (t - t0 < 4000) requestAnimationFrame(step); else ok(); }; requestAnimationFrame(step); });
  // 飛完＝鏡頭最後一次動的那一幀（camFly 那一支 rAF 排在這一支前面：同一幀裡它先跑、先重寫地）
  let end = 0; for (let i = 1; i < cams.length; i++) if (cams[i] !== cams[i - 1]) end = i;
  const fr = ts.slice(1, end + 1).map((t, i) => t - ts[i]);
  const wrote = __count() - c0, lastG = wrote ? __last() : 0, after = wrote ? __frameAfter(ts, cb, lastG) : ts[end + 1];
  return { ...__stat(fr), flyMs: +(ts[end] - t0).toFixed(1), settleAfterFly: after ? +(after - ts[end]).toFixed(1) : null, groundWrites: wrote, zEnd: +S.mapCam.z.toFixed(2) };
})()`;
const KEYS = ["LayoutDuration", "RecalcStyleDuration", "ScriptDuration", "TaskDuration"];
async function metricsDelta(fn) {
  const a = await page.metrics();
  const r = await fn();
  const b = await page.metrics();
  r.cdp = Object.fromEntries(KEYS.map((k) => [k.replace("Duration", ""), +((b[k] - a[k]) * 1000).toFixed(1)]));
  return r;
}
async function memory() {
  await page.send("HeapProfiler.collectGarbage");
  await sleep(300);
  const h = await page.send("Runtime.getHeapUsage");
  const dc = await page.send("Memory.getDOMCounters");
  const dom = await page.eval(`(() => { const mk = document.getElementById("mk"); return { all: document.querySelectorAll("*").length, mkNodes: mk ? mk.querySelectorAll("*").length : 0,
    mk: mk ? mk.tagName.toLowerCase() : null, px: mk && mk.tagName === "CANVAS" ? mk.width * mk.height : 0, cw: mk && mk.tagName === "CANVAS" ? mk.width : null, ch: mk && mk.tagName === "CANVAS" ? mk.height : null,
    pmMB: performance.memory ? +(performance.memory.usedJSHeapSize / 1048576).toFixed(2) : null }; })()`);
  return { heapMB: +(h.usedSize / 1048576).toFixed(2), domNodes: dc.nodes, listeners: dc.jsEventListeners, ...dom, proc: procMem() };
}
// 整個瀏覽器（這一次開的 chrome 與它底下的行程）的私有記憶體（MB）：canvas 的像素、SVG 那一層的點陣不在 JS heap 裡，看這個
function procMem() {
  try {
    const ps = `$r = @(Get-CimInstance Win32_Process -Filter "ProcessId=${proc.pid} OR ParentProcessId=${proc.pid}"); ` +
      `$t = 0; $rd = 0; $gp = 0; foreach ($p in $r) { $m = [double]$p.PrivatePageCount; $t += $m; if ($p.CommandLine -like '*--type=renderer*') { $rd += $m } elseif ($p.CommandLine -like '*--type=gpu-process*') { $gp += $m } }; ` +
      `"{0:N1} {1:N1} {2:N1}" -f ($t / 1MB), ($rd / 1MB), ($gp / 1MB)`;
    const o = execFileSync("powershell.exe", ["-NoProfile", "-Command", ps], { encoding: "utf8" }).trim().replace(/,/g, "").split(/\s+/).map(Number);
    return { allMB: o[0], rendererMB: o[1], gpuMB: o[2] };
  } catch (e) { return null; }
}
const BUSY = `(() => { const t = performance.now(); let x = 0; for (let i = 0; i < 2e7; i++) x = (x + i * 7) % 1000003; return +(performance.now() - t).toFixed(1) + (x < 0 ? 1 : 0); })()`;
const out = { label, variant, dpr: DPR, throttle: THR, round: Number(rnd) };
try {
  await page.send("Page.enable");
  await page.send("Network.enable");
  await page.send("Network.setCacheDisabled", { cacheDisabled: true });
  await page.send("Performance.enable", { timeDomain: "timeTicks" });
  await page.send("Emulation.setDeviceMetricsOverride", { width: 375, height: 812, deviceScaleFactor: DPR, mobile: true });
  await page.send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 5 });
  await page.send("Page.addScriptToEvaluateOnNewDocument", { source: HOOK });
  await page.send("Page.navigate", { url: ORIGIN + "/" });
  await sleep(1500);
  const pw = fs.readFileSync(pwFile, "utf8").trim();
  out.login = await page.eval(`fetch("/api/login", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({login: ${JSON.stringify(account)}, password: ${JSON.stringify(pw)}})}).then((r) => r.status)`);
  await page.eval(`fetch("/api/do/skip_tutorial", {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"}).then((r) => r.status)`);
  await page.send("Page.navigate", { url: ORIGIN + QUERY });
  await sleep(2200);
  out.env = await page.eval(`({ dpr: devicePixelRatio, w: innerWidth, h: innerHeight, touch: navigator.maxTouchPoints, coarse: matchMedia("(pointer: coarse)").matches, search: location.search })`);
  // 降速：前後各跑一次同一段迴圈，比值就是生效的倍數（CDP 沒有讀回降速倍數的指令）
  await page.eval(BUSY);
  const b0 = await page.eval(BUSY);
  await page.send("Emulation.setCPUThrottlingRate", { rate: THR });
  await page.eval(BUSY);
  const b1 = await page.eval(BUSY);
  out.throttleCheck = { before: b0, after: b1, ratio: +(b1 / b0).toFixed(2) };
  // 打開輿圖：到地畫出來的那一幀（S1 預設在這個倍率不畫地：等 8 秒沒畫就記 null）
  out.open = await page.eval(`(async () => {
    const t0 = performance.now();
    goTab("map");
    let mkAt = 0;
    return await new Promise((ok) => {
      const step = (t) => {
        const mk = document.getElementById("mk");
        if (mk && !mkAt) { mkAt = t; __watch(); }
        const drawn = mk && (mk.tagName === "CANVAS" ? !!window.__gd : mk.childElementCount > 0);
        if (drawn) { requestAnimationFrame((t2) => ok({ open: +(t2 - t0).toFixed(1), fromFrame: +(t2 - mkAt).toFixed(1), kind: mk.tagName.toLowerCase() })); return; }
        if (t - t0 > 8000) { ok({ open: null, fromFrame: null, kind: mk ? mk.tagName.toLowerCase() : null }); return; }
        requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    });
  })()`);
  for (let i = 0; i < 80; i++) {
    if (await page.eval(`!!(document.querySelector("#mvw .mv-base.on") && document.querySelector("#mkt .mv-pin"))`)) break;
    await sleep(250);
  }
  await page.eval(`(__watch(), 1)`);
  await sleep(1500);
  out.memOpen = await memory();
  out.runs = [];
  for (let r = 0; r < 3; r++) {
    const run = { z0: await page.eval(PREP) };
    run.pan = await metricsDelta(() => page.eval(PAN));
    await sleep(500);
    run.pinch = await metricsDelta(() => page.eval(PINCH));
    await sleep(500);
    run.zoom = await metricsDelta(() => page.eval(ZOOM));
    await sleep(300);
    run.zFit = await page.eval(FIT);
    run.fly = await metricsDelta(() => page.eval(FLY));
    out.runs.push(run);
    await sleep(500);
  }
  out.memAfter = await memory();
  console.log(label, JSON.stringify({ open: out.open, throttle: out.throttleCheck, mem: [out.memOpen, out.memAfter], pinch: out.runs.map((r) => r.pinch.p95) }));
  fs.appendFileSync(path.join(outDir, "perf.jsonl"), JSON.stringify(out) + "\n");
} finally {
  cdp.close();
  try { proc.kill(); } catch (e) { /* */ }
  await sleep(500);
  try { fs.rmSync(prof, { recursive: true, force: true }); } catch (e) { /* */ }
}
