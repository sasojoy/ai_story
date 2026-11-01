// 無頭 Chromium＋DevTools Protocol（網頁.md「對比圖要存成 PNG 檔」）：開一個自己的 Chromium（自己的 --user-data-dir、自己的埠），
// 一個分頁一條 WebSocket；viewport、深淺色、截圖、在頁面裡跑 JS。不碰共用的瀏覽器窗格。
import { spawn } from "node:child_process";
import fs from "node:fs";

const CHROME = `${process.env.LOCALAPPDATA}\\ms-playwright\\chromium-1208\\chrome-win64\\chrome.exe`;
export const sleep = (ms) => new Promise((ok) => setTimeout(ok, ms));

export async function launch(dir, port) {
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir, { recursive: true });
  const proc = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${port}`, `--user-data-dir=${dir}`, "--no-first-run",
    "--no-default-browser-check", "--disable-gpu", "--hide-scrollbars", "about:blank"], { stdio: "ignore" });
  for (let i = 0; i < 100; i += 1) {
    try { const r = await fetch(`http://127.0.0.1:${port}/json/version`); if (r.ok) return proc; } catch { /* 還沒起來 */ }
    await sleep(200);
  }
  throw new Error("chrome 沒起來");
}

export async function newPage(port) {
  const t = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: "PUT" })).json();
  const ws = new WebSocket(t.webSocketDebuggerUrl);
  await new Promise((ok, no) => { ws.onopen = ok; ws.onerror = no; });
  let seq = 0;
  const pending = new Map();
  ws.onmessage = (m) => {
    const d = JSON.parse(m.data);
    if (d.id && pending.has(d.id)) { pending.get(d.id)(d); pending.delete(d.id); }
  };
  const send = (method, params = {}) => new Promise((ok, no) => {
    const id = ++seq;
    pending.set(id, (d) => (d.error ? no(new Error(`${method}: ${JSON.stringify(d.error)}`)) : ok(d.result)));
    ws.send(JSON.stringify({ id, method, params }));
  });
  await send("Page.enable");
  await send("Runtime.enable");
  await send("Network.enable");
  await send("Network.setCacheDisabled", { cacheDisabled: true });
  const page = {
    send,
    close: () => ws.close(),
    async viewport(width, height, dark = false) {
      await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 2, mobile: width < 641 });
      await send("Emulation.setEmulatedMedia", { features: [
        { name: "prefers-color-scheme", value: dark ? "dark" : "light" }, { name: "prefers-reduced-motion", value: "reduce" }] });
    },
    async eval(expression) {
      const r = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
      if (r.exceptionDetails) throw new Error(`eval: ${JSON.stringify(r.exceptionDetails).slice(0, 600)}`);
      return r.result.value;
    },
    async goto(url) {
      await send("Page.navigate", { url });
      for (let i = 0; i < 100; i += 1) {
        await sleep(150);
        try { if ((await page.eval("document.readyState")) === "complete") break; } catch { /* 換頁中 */ }
      }
    },
    async shot(file) {
      const r = await send("Page.captureScreenshot", { format: "png" });
      fs.writeFileSync(file, Buffer.from(r.data, "base64"));
    },
  };
  return page;
}
