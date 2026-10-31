// node hud.mjs <tag> <帳號>：FB-9095 的實機證據（照 QA 的 hudhud.mjs）。375／360／320 × 沒點地點的三格（一行、一排卡、全開）× 點了一處的三格
// （真觸控按底條「本週」→ 長社的卡；一行、六成、全開）：看得到的那幾樣（區名、🔍、小地圖、◎、全）兩兩疊了幾 px、有沒有被抽屜蓋住；
// 收起來的是哪幾樣。點了一處拉到六成時，在 ◎ 原本的位置真觸控點一下，記點到了誰、鏡頭有沒有動。
import { start, stop, view, login, reload, openMap, shot, saveJson, sleep, SP, tapEl, tap } from "./lib.mjs";
import fs from "node:fs";
import path from "node:path";

const [, , tag = "hud", account = "w2qa"] = process.argv;
const out = path.join(SP, "out", tag);
fs.mkdirSync(out, { recursive: true });
const ctx = await start(9631, tag);
const { page } = ctx;
const R = [];
const M = `(() => { const sel = [["area", ".mv-area"], ["q", ".mv-q"], ["mini", "#mv-mini .mv-mini"], ["home", "#mv-fab .mv-me"], ["fit", '#mv-fab [data-act="map-fit"]']];
  const vis = (e) => !!e && !!e.getClientRects().length && getComputedStyle(e).visibility !== "hidden";
  const els = sel.map(([k, s]) => { const e = document.querySelector(s); if (!vis(e)) return null; const r = e.getBoundingClientRect(); return [k, [r.left, r.top, r.right, r.bottom]]; }).filter(Boolean);
  const hidden = sel.filter(([, s]) => { const e = document.querySelector(s); return e && e.getClientRects().length && !vis(e); }).map(([k]) => k);
  const X = (a, b) => Math.min(a[2], b[2]) - Math.max(a[0], b[0]) > 0.5 && Math.min(a[3], b[3]) - Math.max(a[1], b[1]) > 0.5;
  const hits = []; els.forEach(([k, a], i) => els.slice(i + 1).forEach(([k2, b]) => { if (X(a, b)) hits.push(k + "×" + k2 + " " + Math.round(Math.min(a[3], b[3]) - Math.max(a[1], b[1])) + "px"); }));
  const dr = document.getElementById("mdrawer").getBoundingClientRect(); const under = els.filter(([, r]) => r[3] > dr.top + 0.5).map(([k, r]) => k + " " + Math.round(r[3] - dr.top) + "px");
  return { mode: S.mapMode, sel: S.mapSel, drawer: S.mapDrawer, px: document.getElementById("mdrawer").offsetHeight, shown: els.map(([k]) => k), hidden, hits, underDrawer: under }; })()`;
try {
  console.log("login", await login(page, account));
  for (const [w, h] of [[375, 812], [360, 780], [320, 568]]) {
    await view(page, { w, h });
    await reload(page);
    await openMap(page);
    for (const st of ["peek", "row", "full"]) {
      await page.eval(`mapStop("${st}")`); await sleep(800);
      const m = await page.eval(M); R.push({ w, ...m }); console.log(w, "overview", st, JSON.stringify(m));
      if (st === "row" && w === 320) await shot(page, path.join(out, `${w}-overview-row.png`));
    }
    await page.eval(`mapStop("peek")`);
    await sleep(600);
    await tapEl(page, `document.querySelector("#mbody .m-tray-wk")`);
    await sleep(1500);
    for (const st of ["peek", "half", "full"]) {
      await page.eval(`setMapDrawer("${st}")`); await sleep(800);
      const m = await page.eval(M); R.push({ w, ...m }); console.log(w, "place", st, JSON.stringify(m));
      if (st === "half") {
        await shot(page, path.join(out, `${w}-place-half.png`));
        // ◎ 原本的位置（右 12、底下離抽屜 12＋全 46＋間隔 10、46 見方的正中）：真觸控點一下，看點到誰
        const at = await page.eval(`(() => { const mx = document.getElementById("mapx").getBoundingClientRect(), d = document.getElementById("mdrawer").getBoundingClientRect();
          const x = mx.right - 12 - 23, y = d.top - 12 - 46 - 10 - 23, e = document.elementFromPoint(x, y); return { x, y, hit: e ? (e.closest("[data-act]") ? e.closest("[data-act]").dataset.act : (e.id || String(e.className.baseVal ?? e.className))) : null, cam: { ...S.mapCam } }; })()`);
        await tap(page, at.x, at.y);
        await sleep(1200);
        const after = await page.eval(`({ cam: { ...S.mapCam }, mode: S.mapMode, sel: S.mapSel })`);
        const moved = Math.abs(after.cam.x - at.cam.x) > 0.5 || Math.abs(after.cam.y - at.cam.y) > 0.5 || Math.abs(after.cam.z - at.cam.z) > 1e-3;
        const row = { w, homeTap: { hit: at.hit, moved, z: [at.cam.z, after.cam.z], mode: after.mode, sel: after.sel } };
        R.push(row); console.log(w, "home-spot tap", JSON.stringify(row.homeTap));
        // 點完可能飛走了：回到長社的卡、六成，接著量全開
        await page.eval(`mapPick("changshe")`); await sleep(900); await page.eval(`setMapDrawer("half")`); await sleep(600);
      }
    }
  }
  saveJson(path.join(out, "hud.json"), { R, log: ctx.log });
  console.log("log", JSON.stringify(ctx.log));
} finally {
  await stop(ctx);
}
