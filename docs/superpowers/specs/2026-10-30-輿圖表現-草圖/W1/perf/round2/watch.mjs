// node watch.mjs <輸出子資料夾> <秒>：打開輿圖、數地（#mk）重寫幾次、抓了幾次疊層，記下最後一次重寫之後長社那一塊的填色
// （外面在這段時間裡換長社的主人：看輪詢重抓之後地有沒有跟著換）
import { boot, login, openMap, close, sleep, SP, dismiss } from "./common.mjs";
import fs from "node:fs";
import path from "node:path";

const [, , sub = "watch", secs = "45", loc = "songshan_foot"] = process.argv;
const out = path.join(SP, "out", sub);
const { proc, cdp, page, log } = await boot(9584, out);
const res = {};
try {
  await login(page);
  res.opened = await openMap(page, { w: 375, h: 812 });
  await dismiss(page);
  const fill = `(document.querySelector('#mk .ld-fill[data-cell="${loc}"]') || {getAttribute: () => null}).getAttribute("fill")`;
  res.fill0 = await page.eval(fill);
  await page.eval(`(() => { window.__w = []; new MutationObserver((ms) => { for (const m of ms) if (m.addedNodes.length) { window.__w.push(Math.round(performance.now())); break; } }).observe(document.getElementById("mk"), { childList: true });
    window.__t0 = Math.round(performance.now()); return 1; })()`);
  fs.writeFileSync(path.join(out, "ready"), "1");
  await sleep(Number(secs) * 1000);
  res.after = await page.eval(`({ writes: window.__w.map((t) => t - window.__t0), fetches: performance.getEntriesByType("resource").filter((e) => e.name.includes("/api/map/state")).map((e) => Math.round(e.startTime) - window.__t0).filter((t) => t >= 0),
    control: S.mapState.places[${JSON.stringify(loc)}].control })`);
  res.fill1 = await page.eval(fill);
  res.log = log;
  fs.writeFileSync(path.join(out, "watch.json"), JSON.stringify(res, null, 1));
  console.log(JSON.stringify(res));
} finally {
  await close(cdp, proc);
}
