// node grab.mjs <tag> <帳號> <寬…>：FB-9090 的實機證據。抽屜在一行（底條）時，CDP 真觸控（Input.dispatchTouchEvent）點把手的中、左 15%、右 85%，
// 每個位置連點三次（一行 → 一排卡 → 一行 → 一排卡），記下 click 落在誰身上（document 捕獲階段）、點完之後 mapMode／mapSel／抽屜在哪一格與多高。
import { start, stop, view, login, reload, openMap, shot, saveJson, sleep, SP, tap } from "./lib.mjs";
import fs from "node:fs";
import path from "node:path";

const [, , tag = "grab", account = "w2qa", ...widths] = process.argv;
const H = { 375: 812, 360: 780, 320: 568 };
const out = path.join(SP, "out", tag);
fs.mkdirSync(out, { recursive: true });
const ctx = await start(9601, tag);
const { page } = ctx;
const R = [];
const STATE = `(() => ({ mode: S.mapMode, sel: S.mapSel, drawer: S.mapDrawer, px: document.getElementById("mdrawer").offsetHeight,
  cards: document.querySelectorAll("#mbody .m-cards .m-pc").length, clicks: window.__clicks.slice() }))()`;
const HOOK = `(() => { window.__clicks = []; if (!window.__hooked) { window.__hooked = 1;
  document.addEventListener("click", (e) => { const t = e.target, a = t.closest && t.closest("[data-act]"); window.__clicks.push((t.id || String(t.className.baseVal ?? t.className) || t.tagName) + "|" + (a ? a.dataset.act + ":" + (a.dataset.id || "") : "-")); }, true); } return 1; })()`;
const GRAB = `(() => { const r = document.getElementById("mgrab").getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; })()`;
try {
  console.log("login", await login(page, account));
  for (const W of widths.length ? widths : ["375", "360", "320"]) {
    await view(page, { w: Number(W), h: H[W] });
    for (const fx of [0.5, 0.15, 0.85]) {
      await reload(page);
      await openMap(page);
      await page.eval(HOOK);
      const row = { W, fx, taps: [] };
      for (let i = 0; i < 3; i++) {
        await page.eval(`(() => { window.__clicks = []; return 1; })()`);
        const g = await page.eval(GRAB), x = g[0] + g[2] * fx, y = g[1] + g[3] / 2;
        const under = await page.eval(`(() => { const e = document.elementFromPoint(${x}, ${y}); return e ? (e.id || e.className) : null; })()`);
        await tap(page, x, y);
        await sleep(900);
        const s = await page.eval(STATE);
        row.taps.push({ at: [Math.round(x), Math.round(y)], under, ...s });
        if (fx === 0.5 && i === 0) await shot(page, path.join(out, `${W}-tap1.png`));
      }
      R.push(row);
      console.log(JSON.stringify(row));
    }
  }
  saveJson(path.join(out, "grab.json"), { R, log: ctx.log });
  console.log("log", JSON.stringify(ctx.log));
} finally {
  await stop(ctx);
}
