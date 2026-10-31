// W1 QA 共用：開無頭 Chromium、收主控台錯誤與 4xx/5xx、登入、打開輿圖
import { launch, newPage, sleep } from "./cdp.mjs";
import fs from "node:fs";
import path from "node:path";

export const ORIGIN = "http://w1c.localhost:8171";
export const SP = "C:/Users/ray61/AppData/Local/Temp/claude/C--Ray--------/86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444/scratchpad/w1c";
export { sleep };

export async function boot(port, outDir) {
  fs.mkdirSync(outDir, { recursive: true });
  const { proc, cdp } = await launch({ port, dataDir: path.join(outDir, `prof-${port}-${Date.now()}`) });
  const page = await newPage(cdp);
  const log = { console: [], exceptions: [], http: [], failed: [] };
  cdp.on((m) => {
    if (m.sessionId !== page.sid) return;
    const p = m.params || {};
    if (m.method === "Runtime.consoleAPICalled" && (p.type === "error" || p.type === "warning" || p.type === "assert")) {
      log.console.push(`${p.type}: ${(p.args || []).map((a) => a.value ?? a.description ?? a.type).join(" ").slice(0, 300)}`);
    }
    if (m.method === "Runtime.exceptionThrown") {
      const d = p.exceptionDetails || {};
      log.exceptions.push(`${d.text || ""} ${(d.exception && d.exception.description) || ""}`.slice(0, 500));
    }
    if (m.method === "Log.entryAdded" && p.entry && (p.entry.level === "error" || p.entry.level === "warning")) {
      log.console.push(`log-${p.entry.level}: ${p.entry.source} ${p.entry.text} ${p.entry.url || ""}`.slice(0, 300));
    }
    if (m.method === "Network.responseReceived" && p.response && p.response.status >= 400) {
      log.http.push(`${p.response.status} ${p.response.url}`);
    }
    if (m.method === "Network.loadingFailed" && !p.canceled) log.failed.push(`${p.errorText} ${p.type}`);
  });
  await page.send("Page.enable");
  await page.send("Runtime.enable");
  await page.send("Log.enable");
  await page.send("Network.enable");
  await page.send("Network.setCacheDisabled", { cacheDisabled: true });
  return { proc, cdp, page, log };
}

export async function login(page, account = "w1c") {
  await page.send("Emulation.setDeviceMetricsOverride", { width: 375, height: 812, deviceScaleFactor: 2, mobile: true });
  await page.send("Page.navigate", { url: ORIGIN + "/" });
  await sleep(1500);
  const pw = fs.readFileSync(path.join(SP, "local", `${account}_password.txt`), "utf8").trim();
  const st = await page.eval(`fetch("/api/login", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({login: ${JSON.stringify(account)}, password: ${JSON.stringify(pw)}})}).then((r) => r.status)`);
  return st;
}

// 設視窗、配色，重載、打開輿圖，等底圖、小圖、地都畫好
export async function openMap(page, { w, h, dark = false, mobile = true, touch = false, dpr = 2, reduce = true }) {
  await page.send("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: dpr, mobile });
  await page.send("Emulation.setTouchEmulationEnabled", { enabled: !!touch, maxTouchPoints: touch ? 5 : 1 });
  await page.send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: dark ? "dark" : "light" }, { name: "prefers-reduced-motion", value: reduce ? "reduce" : "no-preference" }] });
  await page.send("Page.navigate", { url: ORIGIN + "/" });
  await sleep(1800);
  await dismiss(page);
  await page.eval(`goTab("map")`);
  let ok = false;
  for (let i = 0; i < 80; i++) {
    if (await page.eval(`!!(document.querySelector("#mvw .mv-base.on") && document.querySelector("#mkt .mv-pin") && document.querySelector("#mk .ld-fill"))`)) { ok = true; break; }
    await sleep(250);
  }
  await sleep(900);
  if (await dismiss(page)) await sleep(600);
  return ok;
}

// 蓋在畫面上的「此事已了・入傳」這類卡（按「收下」／「知道了」）：一張一張按掉，回按了幾張
export async function dismiss(page) {
  let n = 0;
  for (let i = 0; i < 6; i++) {
    const hit = await page.eval(`(() => { const b = [...document.querySelectorAll("button")].find((x) => /^(收下|知道了)$/.test(x.textContent.trim()) && x.offsetParent && x.getBoundingClientRect().width > 0); if (!b) return false; b.click(); return true; })()`);
    if (!hit) break;
    n += 1;
    await sleep(1200);
  }
  return n;
}

export async function shot(page, file) {
  const s = await page.send("Page.captureScreenshot", { format: "png" });
  fs.writeFileSync(file, Buffer.from(s.data, "base64"));
}

export async function close(cdp, proc) {
  try { cdp.close(); } catch (e) { /* */ }
  try { proc.kill(); } catch (e) { /* */ }
  await sleep(400);
}
