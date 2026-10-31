// node dragstop.mjs <tag> <帳號> <寬…>：FB-9093 的實機證據。CDP 真觸控拖把手：從一行往上拖「剛好到一排卡」（一排卡的高 − 一行的高）、拖到頂（全開），
// 另外拖 100、140、300px（放手不是剛好那一格）；放手後等一秒，量名字、小圖、箭頭牌、浮著的那幾樣兩兩相交（lib 的 MEASURE，只算看得到的）、
// 名字出畫面、箭頭牌在不在抽屜底下，以及字那一層是不是照新的底邊重排（跟 mvLayout 此刻算的一模一樣）。
import { start, stop, view, login, reload, openMap, shot, saveJson, sleep, SP, drag, MEASURE } from "./lib.mjs";
import fs from "node:fs";
import path from "node:path";

const [, , tag = "dragstop", account = "w2qa", ...widths] = process.argv;
const H = { 375: 812, 360: 780, 320: 568 };
const out = path.join(SP, "out", tag);
fs.mkdirSync(out, { recursive: true });
const ctx = await start(9611, tag);
const { page } = ctx;
const R = [];
const GRAB = `(() => { const r = document.getElementById("mgrab").getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })()`;
const FRESH = `(() => { const g = mapGeom(document.getElementById("map")), lay = mvLayout(S.mapBase, S.mapState, S.mapCam, g);
  const pillsBelow = [...document.querySelectorAll("#mv-pills .mv-pill")].filter((e) => getComputedStyle(document.getElementById("mv-pills")).visibility !== "hidden"
    && e.getBoundingClientRect().bottom > document.getElementById("mdrawer").getBoundingClientRect().top + 0.5).length;
  const norm = (h) => { const t = document.createElement("template"); t.innerHTML = h; return t.innerHTML; };
  return { relaid: document.getElementById("mkt").innerHTML === norm(lay.html), pillsRelaid: document.getElementById("mv-pills").innerHTML === norm(lay.pills.map((p) => p.html).join("")), pillsBelow }; })()`;
try {
  console.log("login", await login(page, account));
  for (const W of widths.length ? widths : ["375", "360", "320"]) {
    await view(page, { w: Number(W), h: H[W] });
    for (const kind of ["exact", "top", "d100", "d140", "d300"]) {
      await reload(page);
      await openMap(page);
      const rowH = await page.eval(`mapDrawerPx("row") - mapDrawerPx("peek")`);
      const dy = kind === "exact" ? rowH : kind === "top" ? 1000 : Number(kind.slice(1));
      const [x, y] = await page.eval(GRAB);
      await drag(page, [x, y], [x, y - dy], 16, 16);
      await sleep(1000);
      const m = await page.eval(MEASURE);
      const f = await page.eval(FRESH);
      const row = { W, kind, dy, drawer: m.drawer, px: m.drawerPx, mode: m.mode, ...f, bad: m.bad, pills: m.pills, labs: m.labs.length, fabVis: m.fabVis };
      R.push(row);
      console.log(JSON.stringify(row));
      if (kind === "exact") await shot(page, path.join(out, `${W}-exact.png`));
    }
  }
  saveJson(path.join(out, "dragstop.json"), { R, log: ctx.log });
  console.log("log", JSON.stringify(ctx.log));
} finally {
  await stop(ctx);
}
