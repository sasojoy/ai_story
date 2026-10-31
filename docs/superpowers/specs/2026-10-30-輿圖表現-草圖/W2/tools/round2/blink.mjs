// node blink.mjs <tag> <帳號>：FB-9092 的實機證據。375×812，CDP 真觸控兩指捏（Input.dispatchTouchEvent，40 步、每步 16ms），四種：捏開 90→240、
// 捏回 240→90（先捏開放手再捏回）、捏到遠景 300→40、選了一處（點潁水河畔的地）再捏開 90→220。頁面裡 rAF 每一幀記箭頭牌露不露（visibility 不是 hidden、
// 而且有牌），手勢途中（touchStart 到 touchEnd）露出來幾幀；同時數途中重排了幾次字（#mkt 的 childList 換了幾次）。
import { start, stop, view, login, reload, openMap, saveJson, sleep, SP, tap } from "./lib.mjs";
import fs from "node:fs";
import path from "node:path";

const [, , tag = "blink", account = "w2qa"] = process.argv;
const out = path.join(SP, "out", tag);
fs.mkdirSync(out, { recursive: true });
const ctx = await start(9621, tag);
const { page } = ctx;
const R = {};
let Y = 380; // 兩指的高：捏回那一種起手在 2.4 倍，左邊 380 那一帶是洛陽官道的箭頭牌（按在牌上不是捏），改在 470
const pts = (d) => [{ x: 188 - d / 2, y: Y, id: 1 }, { x: 188 + d / 2, y: Y, id: 2 }];
const REC = `(() => { window.__seq = []; window.__phase = 0; window.__relaid = 0; const p = document.getElementById("mv-pills");
  if (!window.__mo) { window.__mo = new MutationObserver(() => { if (window.__phase === 1) window.__relaid++; }); window.__mo.observe(document.getElementById("mkt"), { childList: true }); }
  const f = () => { window.__seq.push([window.__phase, p.style.visibility === "hidden" ? 0 : p.querySelectorAll(".mv-pill").length]); if (window.__seq.length < 3000) requestAnimationFrame(f); };
  requestAnimationFrame(f); return 1; })()`;
async function pinch(d0, d1) {
  await page.eval(`window.__phase = 1`);
  await page.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: pts(d0) });
  for (let i = 1; i <= 40; i++) {
    await page.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: pts(d0 + ((d1 - d0) * i) / 40) });
    await sleep(16);
  }
  await page.eval(`window.__phase = 2`);
  await page.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await sleep(900);
}
try {
  await view(page, { w: 375, h: 812 });
  console.log("login", await login(page, account));
  for (const kind of ["open", "close", "far", "picked"]) {
    await reload(page);
    await openMap(page);
    if (kind === "close") { await pinch(90, 240); }
    if (kind === "picked") {
      const at = await page.eval(`(() => { const g = mapGeom(document.getElementById("map")), c = S.mapCam, b = S.mapBase.places.find((p) => p.id === "yingshui");
        return [g.x0 + c.x + b.x * c.z + 30, g.y0 + c.y + b.y * c.z + 28]; })()`);
      await tap(page, at[0], at[1]);
      await sleep(1200);
    }
    const before = await page.eval(`({ mode: S.mapMode, sel: S.mapSel, pills: document.querySelectorAll("#mv-pills .mv-pill").length, z: S.mapCam.z,
      under: [${kind === "far" ? 240 : kind === "close" ? 240 : 90}].flatMap((d) => [188 - d / 2, 188 + d / 2]).map((x) => { const e = document.elementFromPoint(x, ${kind === "close" ? 470 : 380}); return e ? (e.id || String(e.className.baseVal ?? e.className)) : null; }) })`);
    await page.eval(REC);
    if (kind === "open") await pinch(90, 240);
    if (kind === "close") {
      // 兩指按下去的那一高：兩點底下都是地圖本身（不是箭頭牌、名字、浮著的鈕）
      Y = await page.eval(`(() => { const ok = (x, y) => { const e = document.elementFromPoint(x, y); return !!e && !!e.closest("#map") && !e.closest("button"); };
        for (let y = 300; y < 600; y += 6) if (ok(68, y) && ok(308, y)) return y; return 470; })()`);
      R.closeY = Y;
      await pinch(240, 90); Y = 380;
    }
    if (kind === "far") await pinch(240, 30);
    if (kind === "picked") await pinch(90, 220);
    const seq = await page.eval(`window.__seq`), relaid = await page.eval(`window.__relaid`);
    // 途中露出來：手勢開始動了（牌第一次藏起來）之後、放手之前，又露出來的幀（按下去到開始動之前那幾幀牌本來就在，不算）
    const during = seq.filter(([ph]) => ph === 1), first = during.findIndex(([, n]) => n === 0);
    const shown = first < 0 ? 0 : during.slice(first).filter(([, n]) => n > 0).length;
    const afterShown = seq.filter(([ph, n]) => ph === 2 && n > 0).length;
    const st = await page.eval(`({ z: S.mapCam.z, mode: S.mapMode, pills: document.querySelectorAll("#mv-pills .mv-pill").length, vis: document.getElementById("mv-pills").style.visibility })`);
    R[kind] = { before, frames: during.length, shownDuring: shown, relaidDuring: relaid, afterFramesShown: afterShown, end: st };
    console.log(kind, JSON.stringify(R[kind]));
  }
  saveJson(path.join(out, "blink.json"), { R, log: ctx.log });
  console.log("log", JSON.stringify(ctx.log));
} finally {
  await stop(ctx);
}
