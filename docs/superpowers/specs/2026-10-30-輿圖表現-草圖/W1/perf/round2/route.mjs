// node route.mjs <輸出子資料夾> <road|idle>：照 QA 的 route.mjs（scratchpad qa-w1）。road＝真的出發走去洛陽官道（步行）；兩種都在輿圖上
// 閒著 65 秒，數地（#mk）整張重寫幾次（MutationObserver 數 childList 加了節點的次數），也數這 65 秒裡抓了幾次疊層（/api/map/state）
import { boot, login, openMap, shot, close, sleep, SP, dismiss } from "./common.mjs";
import fs from "node:fs";
import path from "node:path";

const [, , sub = "route", mode = "road"] = process.argv;
const out = path.join(SP, "out", sub);
const { proc, cdp, page, log } = await boot(9582, out);
const res = { mode };
try {
  await login(page);
  if (mode === "road") {
    res.travel = await page.eval(`fetch("/api/travel", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({place: "luoyang_road", mode: "walk"})}).then((r) => r.json()).then((j) => ({arrived: j.arrived, keys: Object.keys(j)}))`);
    await sleep(1500);
  }
  res.opened = await openMap(page, { w: 375, h: 812 });
  await dismiss(page);
  res.state = await page.eval(`({ journey: !!S.mapState.journey, here: S.mapState.here, z: S.mapCam.z, mkLen: document.getElementById("mk").innerHTML.length, mkNodes: document.getElementById("mk").querySelectorAll("*").length })`);
  await shot(page, path.join(out, `${mode}.png`));
  await page.eval(`(() => { window.__w = []; new MutationObserver((ms) => { for (const m of ms) if (m.addedNodes.length) { window.__w.push(Math.round(performance.now())); break; } }).observe(document.getElementById("mk"), { childList: true });
    window.__t0 = Math.round(performance.now()); window.__f0 = performance.getEntriesByType("resource").filter((e) => e.name.includes("/api/map/state")).length; return 1; })()`);
  await sleep(65000);
  res.idle = await page.eval(`({ t0: window.__t0, writes: window.__w.map((t) => t - window.__t0), fetches: performance.getEntriesByType("resource").filter((e) => e.name.includes("/api/map/state")).map((e) => Math.round(e.startTime) - window.__t0).filter((t) => t >= 0),
    bytes: document.getElementById("mk").innerHTML.length, journey: !!S.mapState.journey })`);
  res.log = log;
  fs.writeFileSync(path.join(out, `route-${mode}.json`), JSON.stringify(res, null, 1));
  console.log(JSON.stringify({ mode, opened: res.opened, state: res.state, travel: res.travel, idle: res.idle }));
  console.log("log", JSON.stringify(log));
} finally {
  await close(cdp, proc);
}
