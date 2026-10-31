// node dbg.mjs <密碼檔> <帳號> <寬> <高> <地點,…>：打開輿圖、照打開的取景重排一次，印那幾處名字的每一個位置撞到什麼
import { launch, newPage, sleep } from "./cdp.mjs";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";

const [, , pwFile, account, w, h, ids] = process.argv;
const ORIGIN = "http://w2.localhost:8179";
const { proc, cdp } = await launch({ port: 9481, dataDir: fs.mkdtempSync(path.join(os.tmpdir(), "w2dbg-")) });
const page = await newPage(cdp);
try {
  await page.send("Page.enable");
  await page.send("Emulation.setDeviceMetricsOverride", { width: +w, height: +h, deviceScaleFactor: 2, mobile: true });
  await page.send("Page.navigate", { url: ORIGIN + "/" });
  await sleep(1500);
  const pw = fs.readFileSync(pwFile, "utf8").trim();
  await page.eval(`fetch("/api/login", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({login: ${JSON.stringify(account)}, password: ${JSON.stringify(pw)}})}).then((r) => r.status)`);
  await page.send("Page.navigate", { url: ORIGIN + "/" });
  await sleep(1800);
  await page.eval(`goTab("map")`);
  await sleep(2500);
  const out = await page.eval(`(() => { globalThis.__mvDebug = []; const g = mapGeom(document.getElementById("map")); mvLayout(S.mapBase, S.mapState, S.mapCam, g);
    const d = globalThis.__mvDebug; globalThis.__mvDebug = null; const want = ${JSON.stringify(ids.split(","))};
    return { cam: S.mapCam, room: mapRoom(g), g: [g.vw, g.vh], d: d.filter((x) => want.includes(x.id)) }; })()`);
  console.log(JSON.stringify(out, null, 1));
} finally {
  cdp.close();
  try { proc.kill(); } catch (e) { /* */ }
}
