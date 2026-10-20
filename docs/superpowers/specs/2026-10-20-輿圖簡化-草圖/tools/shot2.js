// 拍靜態網頁：node shot2.js <dbg埠> <網址> <out.png> [寬 高]
const fs = require("fs");
const [dbgPort, url, out, wArg, hArg] = process.argv.slice(2);
const W = Number(wArg || 375), H = Number(hArg || 812);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  const tab = await (await fetch(`http://127.0.0.1:${dbgPort}/json/new?about:blank`, { method: "PUT" })).json();
  const ws = new WebSocket(tab.webSocketDebuggerUrl);
  await new Promise((r) => (ws.onopen = r));
  let seq = 0; const waiting = new Map();
  ws.onmessage = (ev) => { const m = JSON.parse(ev.data); if (m.id && waiting.has(m.id)) { waiting.get(m.id)(m); waiting.delete(m.id); } };
  const send = (method, params = {}) => new Promise((r) => { const id = ++seq; waiting.set(id, r); ws.send(JSON.stringify({ id, method, params })); });
  await send("Page.enable");
  await send("Network.enable");
  await send("Network.setCacheDisabled", { cacheDisabled: true });
  await send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 2, mobile: W < 768 });
  await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] });
  await send("Page.navigate", { url });
  await sleep(1800);
  const shot = await send("Page.captureScreenshot", { format: "png" });
  fs.writeFileSync(out, Buffer.from(shot.result.data, "base64"));
  console.log("存了", out);
  ws.close();
  await fetch(`http://127.0.0.1:${dbgPort}/json/close/${tab.id}`).catch(() => {});
})().catch((e) => { console.error(e); process.exit(1); });
