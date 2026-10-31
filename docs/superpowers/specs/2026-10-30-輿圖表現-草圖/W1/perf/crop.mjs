// node crop.mjs <輸出資料夾> <密碼檔> <帳號> <V|R>：375×812、像素比 3，放到倍率 2.4、以潁川郡（你那一塊：紅框）為中心，
// 地畫好之後把字那一層（#mkt）藏起來，裁潁川郡與潁水河畔（黃巾的）相接那一段戰線附近 140×140 CSS px（三倍像素＝420×420）存 PNG。
import { launch, newPage, sleep } from "./cdp.mjs";
import fs from "node:fs";
import path from "node:path";

const [, , outDir, pwFile, account, variant] = process.argv;
const ORIGIN = "http://w1b.localhost:8166";
fs.mkdirSync(outDir, { recursive: true });
const prof = path.join(outDir, `prof-crop-${variant}-${Date.now()}`);
const { proc, cdp } = await launch({ port: 9467, dataDir: prof });
const page = await newPage(cdp);
try {
  await page.send("Page.enable");
  await page.send("Network.setCacheDisabled", { cacheDisabled: true });
  await page.send("Emulation.setDeviceMetricsOverride", { width: 375, height: 812, deviceScaleFactor: 3, mobile: true });
  await page.send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] });
  await page.send("Page.navigate", { url: ORIGIN + "/" });
  await sleep(1500);
  const pw = fs.readFileSync(pwFile, "utf8").trim();
  await page.eval(`fetch("/api/login", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({login: ${JSON.stringify(account)}, password: ${JSON.stringify(pw)}})}).then((r) => r.status)`);
  await page.send("Page.navigate", { url: ORIGIN + (variant === "R" ? "/?ground=raster" : "/") });
  await sleep(2000);
  await page.eval(`goTab("map")`);
  for (let i = 0; i < 80; i++) {
    if (await page.eval(`!!(document.querySelector("#mvw .mv-base.on") && document.querySelector("#mkt .mv-pin"))`)) break;
    await sleep(250);
  }
  // 季曆走到一半跳出來的「此事已了・入傳」那一張（收下）：蓋在地圖上，先收掉
  for (let i = 0; i < 3; i++) {
    const n = await page.eval(`(() => { const b = [...document.querySelectorAll("button")].find((x) => x.textContent.trim() === "收下" && x.offsetParent); if (b) b.click(); return !!b; })()`);
    if (!n) break;
    await sleep(1200);
  }
  const at = await page.eval(`(async () => {
    const g = mapGeom(document.getElementById("map")), p = placeXY("yingchuan");
    camSet(camAt(g, p[0], p[1], 2.4), g); drawMarks();
    await new Promise((r) => setTimeout(r, 2500));
    const st = S.mapState, ctrl = controlAt(st, st.now_week), c = S.mapCam;
    const e = S.mapBase.world.edges.find((e) => (e.a === "yingchuan" || e.b === "yingchuan") && ctrl[e.a] && ctrl[e.b] && ctrl[e.a] !== ctrl[e.b]);
    const n = (e.d.match(/-?\\d+(?:\\.\\d+)?/g) || []).map(Number), i = Math.floor(n.length / 4) * 2;
    document.getElementById("mkt").style.visibility = "hidden";
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    // 橘框：可出陣的一塊（不是你那一塊）在畫面裡的一個角（地圖單位裡往塊內收 12）
    const room = mapRoom(g);
    let o = null;
    for (const cell of S.mapBase.world.cells) {
      const q = st.places[cell.id];
      if (!q || !q.sortie || cell.id === st.here) continue;
      const v = (cell.d.match(/-?\\d+(?:\\.\\d+)?/g) || []).map(Number), pts = [];
      for (let k = 0; k + 1 < v.length; k += 2) pts.push([v[k], v[k + 1]]);
      const cx = pts.reduce((s, p) => s + p[0], 0) / pts.length, cy = pts.reduce((s, p) => s + p[1], 0) / pts.length;
      const along = [];
      for (let k = 0; k < pts.length; k++) { const a = pts[k], b = pts[(k + 1) % pts.length]; for (let f = 0; f < 1; f += 0.1) along.push([a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f]); }
      for (const [px, py] of along) {
        const L = Math.hypot(cx - px, cy - py) || 1, mx = px + (cx - px) * 12 / L, my = py + (cy - py) * 12 / L;
        const sx = c.x + mx * c.z + g.x0, sy = c.y + my * c.z + g.y0;
        if (sx > 80 && sx < g.vw - 80 && sy > g.y0 + room.top + 80 && sy < g.y0 + room.bottom - 80) { o = { id: cell.id, x: sx, y: sy }; break; }
      }
      if (o) break;
    }
    return { z: c.z, edge: [e.a, e.b], x: c.x + n[i] * c.z + g.x0, y: c.y + n[i + 1] * c.z + g.y0, orange: o, dbg: { sortie: Object.keys(st.places).filter((k) => st.places[k].sortie), room, y0: g.y0, vw: g.vw, cam: c }, mk: document.getElementById("mk").tagName,
      cw: document.getElementById("mk").width, ch: document.getElementById("mk").height };
  })()`);
  const clip = { x: Math.round(at.x - 70), y: Math.round(at.y - 70), width: 140, height: 140, scale: 1 };
  const shot = await page.send("Page.captureScreenshot", { format: "png", clip, captureBeyondViewport: false });
  fs.writeFileSync(path.join(outDir, `crop-${variant}.png`), Buffer.from(shot.data, "base64"));
  if (!at.orange) {
    // 畫面裡沒有可出陣的塊：鏡頭移到第一塊可出陣的地（倍率不變、同一級，地不重寫也不重烤）的一個角往內 12 單位
    at.orange = await page.eval(`(async () => {
      const g = mapGeom(document.getElementById("map")), st = S.mapState, c0 = S.mapCam;
      const cell = S.mapBase.world.cells.find((x) => st.places[x.id] && st.places[x.id].sortie && x.id !== st.here);
      const v = (cell.d.match(/-?\\d+(?:\\.\\d+)?/g) || []).map(Number), pts = [];
      for (let k = 0; k + 1 < v.length; k += 2) pts.push([v[k], v[k + 1]]);
      const cx = pts.reduce((s, p) => s + p[0], 0) / pts.length, cy = pts.reduce((s, p) => s + p[1], 0) / pts.length;
      const [px, py] = pts[0], L = Math.hypot(cx - px, cy - py) || 1, mx = px + (cx - px) * 12 / L, my = py + (cy - py) * 12 / L;
      camSet(camAt(g, mx, my, c0.z), g); drawMarks();
      document.getElementById("mkt").style.visibility = "hidden";
      await new Promise((r) => setTimeout(r, 2500));
      const c = S.mapCam;
      return { id: cell.id, x: c.x + mx * c.z + g.x0, y: c.y + my * c.z + g.y0, moved: true };
    })()`);
  }
  if (at.orange) {
    const clip2 = { x: Math.round(at.orange.x - 70), y: Math.round(at.orange.y - 70), width: 140, height: 140, scale: 1 };
    const s2 = await page.send("Page.captureScreenshot", { format: "png", clip: clip2, captureBeyondViewport: false });
    fs.writeFileSync(path.join(outDir, `crop-orange-${variant}.png`), Buffer.from(s2.data, "base64"));
    at.clip2 = clip2;
  }
  const full = await page.send("Page.captureScreenshot", { format: "png" });
  fs.writeFileSync(path.join(outDir, `full-${variant}.png`), Buffer.from(full.data, "base64"));
  console.log(variant, JSON.stringify({ ...at, clip }));
  fs.writeFileSync(path.join(outDir, `crop-${variant}.json`), JSON.stringify({ ...at, clip }));
} finally {
  cdp.close();
  try { proc.kill(); } catch (e) { /* */ }
  await sleep(500);
  try { fs.rmSync(prof, { recursive: true, force: true }); } catch (e) { /* */ }
}
