// node shots.mjs <版本名>：375×812、像素比 2、減少動態；打開輿圖（Joy 的取景：倍率 1.15、以你為中心）拍一張，再照 VIEWS 對準幾處拍
// （倍率 1.15 與 1.5）。每一張量：倍率、#mk 的字數與節點數、框的數目，以及每一處「區界落在塊內的那一段」（FB-9070 修前沒有框的那一截）
// 在螢幕上的外框（給拼圖時圈出來）。PNG 與 measure.json 存在 out/shots/<版本名>/
import { boot, login, openMap, shot, close, sleep, SP, dismiss } from "./common.mjs";
import fs from "node:fs";
import path from "node:path";

const label = process.argv[2];
const out = path.join(SP, "out", "shots", label);
const TARGETS = ["yingchuan", "nanyang_road", "juma_river", "xiaquyang", "yu_river", "nanyang_wilds", "baima_ford", "yingchuan_academy", "hilltop_wilds", "runan_wilds"];
const VIEWS = [
  { name: "open", z: null },
  { name: "here-1.5", at: "yingchuan", z: 1.5 },
  { name: "nanyang-1.15", at: "nanyang_road", z: 1.15 },
  { name: "nanyang-1.5", at: "nanyang_road", z: 1.5 },
  { name: "north-1.15", at: [505, 330], z: 1.15 },
  { name: "xiaquyang-1.5", at: "xiaquyang", z: 1.5 },
  { name: "juma-1.5", at: "juma_river", z: 1.5 },
];
const MEASURE = `(() => {
  const b = S.mapBase, st = S.mapState, c = S.mapCam, g = mapGeom(document.getElementById("map")), room = mapRoom(g), mk = document.getElementById("mk");
  const pts = (d) => { const n = (String(d).match(/-?\\d+(?:\\.\\d+)?/g) || []).map(Number), o = []; for (let i = 0; i + 1 < n.length; i += 2) o.push([n[i], n[i + 1]]); return o; };
  const inside = (x, y, pg) => { let r = false; for (let i = 0, j = pg.length - 1; i < pg.length; j = i++) { const a = pg[i], e = pg[j]; if ((a[1] > y) !== (e[1] > y) && x < ((e[0] - a[0]) * (y - a[1])) / (e[1] - a[1]) + a[0]) r = !r; } return r; };
  const scr = (x, y) => [g.x0 + c.x + x * c.z, g.y0 + c.y + y * c.z];
  const cells = Object.fromEntries(b.world.cells.map((x) => [x.id, x])), regs = Object.fromEntries(b.world.regions.map((r) => [r.id, pts(r.d)]));
  const border = {};
  for (const id of ${JSON.stringify(TARGETS)}) {
    const cell = cells[id];
    if (!cell) continue;
    const cp = pts(cell.d), rp = regs[cell.region], on = [];
    for (let i = 0; i < rp.length; i++) {
      const a = rp[i], e = rp[(i + 1) % rp.length], L = Math.hypot(e[0] - a[0], e[1] - a[1]), n = Math.max(1, Math.round(L / 2));
      for (let k = 0; k <= n; k++) { const x = a[0] + (e[0] - a[0]) * k / n, y = a[1] + (e[1] - a[1]) * k / n; if (inside(x, y, cp)) on.push(scr(x, y)); }
    }
    const vis = on.filter(([x, y]) => x >= 0 && x <= innerWidth && y >= g.y0 + room.top && y <= g.y0 + room.bottom);
    if (vis.length < 3) continue;
    const xs = vis.map((p) => p[0]), ys = vis.map((p) => p[1]);
    const p = placeOf(b, id);
    border[id] = { box: [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)].map((v) => Math.round(v)), n: vis.length, pin: scr(p.x, p.y).map(Math.round), name: p.name };
  }
  const q = (s) => document.querySelectorAll(s).length;
  return { z: +c.z.toFixed(3), room: [g.y0 + room.top, g.y0 + room.bottom].map(Math.round), mkLen: mk.innerHTML.length, mkNodes: mk.querySelectorAll("*").length,
    rim: q("#mk .ld-rim") + q("#mk .w-cool"), sortie: q("#mk .ld-sortie"), faint: q('#mk .ld-sortie[stroke-opacity]'), here: q("#mk .ld-here"), letter: q("#mk .w-letter"),
    clock: (document.querySelector("#top .where") || {}).textContent || "", border };
})()`;
const { proc, cdp, page, log } = await boot(9583, out);
const res = {};
try {
  await login(page);
  res.opened = await openMap(page, { w: 375, h: 812 });
  for (const v of VIEWS) {
    if (v.z) {
      const at = Array.isArray(v.at) ? v.at : await page.eval(`(() => { const p = placeOf(S.mapBase, ${JSON.stringify(v.at)}); return [p.x, p.y]; })()`);
      await page.eval(`(() => { const g = mapGeom(document.getElementById("map")); camSet(camAt(g, ${at[0]}, ${at[1]}, ${v.z}), g); drawMarks(); return 1; })()`);
    }
    await sleep(900);
    if (await dismiss(page)) await sleep(600);
    res[v.name] = await page.eval(MEASURE);
    await shot(page, path.join(out, `${v.name}.png`));
    console.log(v.name, JSON.stringify({ ...res[v.name], border: Object.keys(res[v.name].border) }));
  }
  res.log = log;
  fs.writeFileSync(path.join(out, "measure.json"), JSON.stringify(res, null, 1));
  console.log("log", JSON.stringify(log));
} finally {
  await close(cdp, proc);
}
