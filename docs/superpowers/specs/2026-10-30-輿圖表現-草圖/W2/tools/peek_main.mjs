// node peek_main.mjs <密碼檔> <帳號>：登入、印 /api/main 的 week_card 與江湖頁上帶 data-goto 的鈕
import { launch, newPage, sleep } from "./cdp.mjs";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";

const [, , pwFile, account] = process.argv;
const ORIGIN = "http://w2.localhost:8179";
const { proc, cdp } = await launch({ port: 9482, dataDir: fs.mkdtempSync(path.join(os.tmpdir(), "w2peek-")) });
const page = await newPage(cdp);
try {
  await page.send("Page.enable");
  await page.send("Emulation.setDeviceMetricsOverride", { width: 375, height: 812, deviceScaleFactor: 1, mobile: true });
  await page.send("Page.navigate", { url: ORIGIN + "/" });
  await sleep(1500);
  const pw = fs.readFileSync(pwFile, "utf8").trim();
  await page.eval(`fetch("/api/login", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({login: ${JSON.stringify(account)}, password: ${JSON.stringify(pw)}})}).then((r) => r.status)`);
  await page.send("Page.navigate", { url: ORIGIN + "/" });
  await sleep(2000);
  const out = await page.eval(`(async () => { const m = await (await fetch("/api/main")).json();
    const btns = [...document.querySelectorAll('[data-goto]')].map((b) => ({ goto: b.dataset.goto, then: b.dataset.then || null, text: b.textContent.trim(), card: (b.closest("section") || {}).className }));
    return { week_card: m.week_card, btns }; })()`);
  console.log(JSON.stringify(out, null, 1).slice(0, 4000));
} finally {
  cdp.close();
  try { proc.kill(); } catch (e) { /* */ }
}
