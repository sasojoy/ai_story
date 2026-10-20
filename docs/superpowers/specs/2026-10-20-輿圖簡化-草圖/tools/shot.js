// 無頭 Chromium（DevTools Protocol）拍輿圖：node shot.js <dbg埠> <網址> <out.png> <淺色|深色> <mapv> <pick地點|-> <縮放步數> [寬 高]
// 照 .claude/skills/tianxia-dev/網頁.md「對比圖要存成 PNG 檔」那一節的做法；登入在頁面裡 fetch /api/login。
const fs = require("fs");
const [dbgPort, base, out, scheme, mapv, pick, zoomArg, wArg, hArg] = process.argv.slice(2);
const zoomSteps = Number(zoomArg || 0), W = Number(wArg || 375), H = Number(hArg || 812);
const [login, password] = fs.readFileSync(__dirname + "/login.txt", "utf8").split(/\r?\n/);

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const res = await fetch(`http://127.0.0.1:${dbgPort}/json/new?about:blank`, { method: "PUT" });
  const tab = await res.json();
  const ws = new WebSocket(tab.webSocketDebuggerUrl);
  await new Promise((r) => (ws.onopen = r));
  let seq = 0;
  const waiting = new Map();
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.id && waiting.has(m.id)) { waiting.get(m.id)(m); waiting.delete(m.id); }
  };
  const send = (method, params = {}) => new Promise((r) => { const id = ++seq; waiting.set(id, r); ws.send(JSON.stringify({ id, method, params })); });
  const evaluate = async (expression) => {
    const m = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (m.result && m.result.exceptionDetails) throw new Error(JSON.stringify(m.result.exceptionDetails));
    return m.result && m.result.result ? m.result.result.value : undefined;
  };
  const settle = async () => { for (let i = 0; i < 100; i++) { if ((await evaluate("document.readyState")) === "complete") break; await sleep(100); } };
  const waitFor = async (sel, ms = 15000) => {
    const t0 = Date.now();
    while (Date.now() - t0 < ms) { if (await evaluate(`!!document.querySelector(${JSON.stringify(sel)})`)) return true; await sleep(150); }
    throw new Error("等不到 " + sel);
  };

  await send("Page.enable");
  await send("Network.enable");
  await send("Network.setCacheDisabled", { cacheDisabled: true });
  await send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 2, mobile: W < 768 });
  await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: scheme === "深色" ? "dark" : "light" }, { name: "prefers-reduced-motion", value: "reduce" }] });
  await send("Page.navigate", { url: base + "/" });
  await settle();
  const ok = await evaluate(`fetch("/api/login", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({login: ${JSON.stringify(login)}, password: ${JSON.stringify(password)}})}).then(r => r.status)`);
  if (ok !== 200) throw new Error("登入失敗 " + ok);
  await send("Page.navigate", { url: `${base}/?mapv=${encodeURIComponent(mapv || "")}` });
  await settle();
  await waitFor('[data-act="tab"][data-tab="map"]');
  await evaluate(`document.querySelector('[data-act="tab"][data-tab="map"]').click()`);
  await waitFor("#mkt");
  await sleep(1200);
  if (pick && pick !== "-") {
    await evaluate(`(() => { const b = document.createElement("button"); b.dataset.act = "map-pick"; b.dataset.id = ${JSON.stringify(pick)}; b.style.position = "absolute"; b.style.opacity = "0"; document.getElementById("mapx").appendChild(b); b.click(); b.remove(); })()`);
    await sleep(500);
  }
  for (let i = 0; i < Math.abs(zoomSteps); i++) {
    await evaluate(`document.querySelector('[data-act="map-zoom"][data-step="${zoomSteps > 0 ? "in" : "out"}"]').click()`);
    await sleep(250);
  }
  await sleep(1500);
  const shot = await send("Page.captureScreenshot", { format: "png" });
  fs.writeFileSync(out, Buffer.from(shot.result.data, "base64"));
  console.log("存了", out);
  ws.close();
  await fetch(`http://127.0.0.1:${dbgPort}/json/close/${tab.id}`).catch(() => {});
}

main().catch((e) => { console.error(e); process.exit(1); });
