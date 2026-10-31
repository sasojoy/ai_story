// node shoot.mjs <輸出資料夾> <密碼檔> <帳號> <鏡頭.json>：登入、打開輿圖、量數字、拍 PNG（兩倍像素、減少動態），measure.json 存在輸出資料夾
// 鏡頭：[{ name, w, h, dark, mobile, tap: "<地點 id>", bing: true〔丙的倍率：螢幕寬 250 單位、以你＋腳下幾站為中心〕, query: "?…" }]（tap：在那一處的地上找一點〔離每一顆小圖 26px 以上、底下不是按鈕〕真的按下放開）
import { launch, newPage, sleep } from "./cdp.mjs";
import fs from "node:fs";
import path from "node:path";

const [, , outDir, pwFile, account, shotsFile] = process.argv;
const ORIGIN = "http://w1b.localhost:8166";
const shots = JSON.parse(fs.readFileSync(shotsFile, "utf8"));
fs.mkdirSync(outDir, { recursive: true });
const { proc, cdp } = await launch({ port: 9468, dataDir: path.join(outDir, `prof-${Date.now()}`) });
const page = await newPage(cdp);
const MEASURE = `(() => {
  const q = (s) => document.querySelectorAll(s).length, z = S.mapCam.z, mk = document.getElementById("mk");
  const sw = (sel, half) => { const e = document.querySelector(sel); return e ? +(parseFloat(e.getAttribute("stroke-width")) * z / (half ? 2 : 1)).toFixed(2) : null; };
  return { z: +z.toFixed(3), level: mvLevel(z), vw: innerWidth, vh: innerHeight, hscroll: document.documentElement.scrollWidth > innerWidth, mk: mk.tagName.toLowerCase(),
    land: q("#mk .ld-fill"), front: q("#mk .ld-front"), sortie: q("#mk .ld-sortie"), here: q("#mk .ld-here"), cool: q("#mk .w-cool"), tug: q("#mk pattern"),
    tugRed: q('#mk .ld-rim[stroke="#C0392B"]'), tugRedIn: [...document.querySelectorAll('#mk .ld-rim[stroke="#C0392B"]')].filter((e) => { const r = e.getBoundingClientRect(); return r.right > 0 && r.left < innerWidth && r.bottom > 0 && r.top < innerHeight; }).map((e) => e.dataset.cell),
    tugRedPx: sw('#mk .ld-rim[stroke="#C0392B"]', true),
    pins: q("#mkt .mv-pin"), dg: q("#mkt .mv-dg"), sword: q("#mkt .mv-bd-x"), rich: q("#mkt .mv-bd-rich"), flag: q("#mkt .mv-flag"),
    side: q("#mkt .mv-side"), bar: q("#mkt .mv-bar"), ins: q("#mkt .ins"), small: q("#mkt .mv-lab small"), wash: q('[data-act="map-wash"]'),
    labs: q("#mkt .mv-lab"), sel: S.mapSel, mode: S.mapMode, drawer: S.mapDrawer, week: S.mapState.week, nearWeek: (nearWeek(S.mapState) || {}).id || null,
    rimPx: sw("#mk .ld-rim", true), framePx: sw("#mk .ld-sortie", true), frontPx: sw('#mk g[stroke="#FFF6E0"]', false) };
})()`;
const SPOT = (id) => `(() => {
  const g = mapGeom(document.getElementById("map")), c = S.mapCam, room = mapRoom(g);
  const pins = [...document.querySelectorAll("#mkt .mv-pin")].map((e) => { const r = e.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; });
  for (let y = g.y0 + room.top + 20; y < g.y0 + room.bottom - 20; y += 4) for (let x = g.x0 + 20; x < g.x0 + g.vw - 20; x += 4) {
    if (landAt(S.mapBase, S.mapState, (x - g.x0 - c.x) / c.z, (y - g.y0 - c.y) / c.z) !== ${JSON.stringify(id)}) continue;
    if (pins.some(([px, py]) => Math.hypot(px - x, py - y) < 26)) continue;
    const el = document.elementFromPoint(x, y);
    if (!el || el.closest("[data-act], button, .mdrawer, #mdrawer, .mv-top")) continue;
    return [x, y];
  }
  return null;
})()`;
const results = {};
try {
  await page.send("Page.enable");
  await page.send("Network.enable");
  await page.send("Network.setCacheDisabled", { cacheDisabled: true });
  await page.send("Emulation.setDeviceMetricsOverride", { width: 375, height: 812, deviceScaleFactor: 2, mobile: true });
  await page.send("Page.navigate", { url: ORIGIN + "/" });
  await sleep(1500);
  const pw = fs.readFileSync(pwFile, "utf8").trim();
  const login = await page.eval(`fetch("/api/login", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({login: ${JSON.stringify(account)}, password: ${JSON.stringify(pw)}})}).then((r) => r.status)`);
  const skip = await page.eval(`fetch("/api/do/skip_tutorial", {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"}).then((r) => r.status)`);
  console.log("login", login, "skip", skip);
  for (const s of shots) {
    await page.send("Emulation.setDeviceMetricsOverride", { width: s.w, height: s.h, deviceScaleFactor: 2, mobile: s.mobile !== false });
    await page.send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: s.dark ? "dark" : "light" }, { name: "prefers-reduced-motion", value: "reduce" }] });
    await page.send("Page.navigate", { url: ORIGIN + (s.query || "/") });
    await sleep(1800);
    await page.eval(`goTab("map")`);
    for (let i = 0; i < 60; i++) {
      if (await page.eval(`!!(document.querySelector("#mvw .mv-base.on") && document.querySelector("#mkt .mv-pin") && document.querySelector("#mk .ld-fill"))`)) break;
      await sleep(250);
    }
    await sleep(900);
    const r = {};
    if (s.bing) {
      await page.eval(`(() => {
        const g = mapGeom(document.getElementById("map")), b = S.mapBase, st = S.mapState, hp = placeOf(b, st.here);
        const nb = b.edges.filter((e) => e.includes(st.here)).map(([a, z]) => placeOf(b, a === st.here ? z : a)).filter(Boolean), n = nb.length + 2;
        const cx = (hp.x * 2 + nb.reduce((s, p) => s + p.x, 0)) / n, cy = (hp.y * 2 + nb.reduce((s, p) => s + p.y, 0)) / n;
        camSet(camAt(g, cx, cy, g.vw / 250), g); drawMarks(); return 1;
      })()`);
      await sleep(900);
    }
    if (s.tap) {
      const at = await page.eval(SPOT(s.tap));
      r.tapAt = at;
      if (at) {
        for (const type of ["mousePressed", "mouseReleased"]) {
          await page.send("Input.dispatchMouseEvent", { type, x: at[0], y: at[1], button: "left", buttons: type === "mousePressed" ? 1 : 0, clickCount: 1 });
        }
        r.right = await page.eval(`[S.mapMode, S.mapSel]`); // 剛放開：還在等 MV_TAP2
        await sleep(1200);
      }
    }
    Object.assign(r, await page.eval(MEASURE));
    const shot = await page.send("Page.captureScreenshot", { format: "png" });
    fs.writeFileSync(path.join(outDir, s.name + ".png"), Buffer.from(shot.data, "base64"));
    results[s.name] = r;
    console.log(s.name, JSON.stringify(r));
  }
  fs.writeFileSync(path.join(outDir, "measure.json"), JSON.stringify(results, null, 1));
} finally {
  cdp.close();
  try { proc.kill(); } catch (e) { /* */ }
  await sleep(400);
}
