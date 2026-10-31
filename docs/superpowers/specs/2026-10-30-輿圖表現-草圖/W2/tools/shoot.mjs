// node shoot.mjs <輸出資料夾> <密碼檔> <帳號> <鏡頭.json>：登入、打開輿圖、量數字、拍 PNG（兩倍像素、減少動態），measure.json 存在輸出資料夾。
// 鏡頭：[{ name, w, h, dark, mobile, tap: "<地點 id>"〔在那一處的地上真的按下放開〕, goto: true〔江湖頁本週那一張卡的「去輿圖」真的按〕,
//   drawer: "peek"|"row"|"full"〔把手：拉到那一格〕, sortie: true〔按底條的「可出陣 N ›」〕, zoom: 倍率是 Z0 的幾倍（以打開的中心）, wait }]
// 量：倍率、Z0、段、名字（真的字框 .nm）與小圖、徽、箭頭牌、浮著的那幾樣兩兩相交幾對（> 0.5px）、名字出畫面幾個、區名、小地圖、底條那一行的字
import { launch, newPage, sleep } from "./cdp.mjs";
import fs from "node:fs";
import path from "node:path";

const [, , outDir, pwFile, account, shotsFile] = process.argv;
const ORIGIN = "http://w2.localhost:8179";
const shots = JSON.parse(fs.readFileSync(shotsFile, "utf8"));
fs.mkdirSync(outDir, { recursive: true });
const { proc, cdp } = await launch({ port: 9479, dataDir: path.join(outDir, `prof-${Date.now()}`) });
const page = await newPage(cdp);
const MEASURE = `(() => {
  const g = mapGeom(document.getElementById("map")), z = S.mapCam.z, room = mapRoom(g), box = document.getElementById("map").getBoundingClientRect();
  const R = (e) => { const r = e.getBoundingClientRect(); return [r.left - box.left, r.top - box.top, r.right - box.left, r.bottom - box.top]; };
  const all = (sel) => [...document.querySelectorAll(sel)].filter((e) => e.offsetParent !== null || e.getClientRects().length);
  const vis = (r) => r[2] > 0 && r[0] < g.vw && r[3] > 0 && r[1] < room.bottom;
  const labs = all("#mkt .mv-lab .nm").map((e) => ({ id: e.closest(".mv-lab").dataset.id, r: R(e) })).filter((o) => vis(o.r));
  const iconEls = all("#mkt .mv-pin img, #mkt .mv-pin svg, #mkt .mv-dg, #mkt .mv-bd, #mkt .mv-flag").filter((e) => vis(R(e)));
  const icons = iconEls.map(R), iconWho = iconEls.map((e) => (e.closest(".mv-pin") ? e.closest(".mv-pin").dataset.id : e.className.baseVal || e.className) + "@" + R(e).map((v) => v.toFixed(1)).join(","));
  const pills = all("#mv-pills .mv-pill").map((e) => ({ id: e.dataset.id, r: R(e) }));
  const hud = all(".mv-area, .mv-q, .mv-mini, .mv-fab button").map(R);
  const x = (a, b) => Math.min(a[2], b[2]) - Math.max(a[0], b[0]) > 0.5 && Math.min(a[3], b[3]) - Math.max(a[1], b[1]) > 0.5;
  let ll = 0, li = 0, lp = 0, lh = 0, pi = 0, out = 0;
  labs.forEach((a, i) => { labs.slice(i + 1).forEach((b) => { ll += x(a.r, b.r); }); icons.forEach((b) => { li += x(a.r, b); }); pills.forEach((b) => { lp += x(a.r, b.r); }); hud.forEach((b) => { lh += x(a.r, b); });
    out += a.r[0] < -0.5 || a.r[1] < -0.5 || a.r[2] > g.vw + 0.5 || a.r[3] > room.bottom + 0.5; });
  const pairs = [];
  pills.forEach((a) => icons.forEach((b, i) => { if (x(a.r, b)) { pi += 1; pairs.push(a.id + "@" + a.r.map((v) => v.toFixed(1)).join(",") + " x " + iconWho[i]); } }));
  labs.forEach((a) => icons.forEach((b, i) => { if (x(a.r, b)) pairs.push(a.id + "@" + a.r.map((v) => v.toFixed(1)).join(",") + " x " + iconWho[i]); }));
  const tray = document.querySelector("#mbody .m-tray");
  return { z: +z.toFixed(3), z0: +mvZ0(g).toFixed(3), level: mvLevel(z, g), vw: g.vw, vh: g.vh, roomBottom: room.bottom, hscroll: document.documentElement.scrollWidth > innerWidth,
    labs: labs.map((o) => o.id), tiny: all("#mkt .mv-lab.tiny").length, leads: all("#mkt .mv-lead").length, pills: pills.map((o) => o.id),
    overlap: { labLab: ll, labIcon: li, labPill: lp, labHud: lh, pillIcon: pi, labOut: out }, pairs,
    area: (document.querySelector("#mv-area .t") || {}).textContent, mini: !!document.querySelector("#mv-mini .mv-mini"),
    tray: tray ? tray.textContent.replace(/\\s+/g, " ").trim() : null, drawer: S.mapDrawer, drawerPx: document.getElementById("mdrawer").offsetHeight,
    mode: S.mapMode, sel: S.mapSel, filter: S.mapFilter, week: S.mapState.week };
})()`;
const SPOT = (id) => `(() => {
  const g = mapGeom(document.getElementById("map")), c = S.mapCam, room = mapRoom(g);
  const pins = [...document.querySelectorAll("#mkt .mv-pin")].map((e) => { const r = e.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; });
  for (let y = g.y0 + room.top + 20; y < g.y0 + room.bottom - 20; y += 4) for (let x = g.x0 + 20; x < g.x0 + g.vw - 20; x += 4) {
    if (landAt(S.mapBase, S.mapState, (x - g.x0 - c.x) / c.z, (y - g.y0 - c.y) / c.z) !== ${JSON.stringify(id)}) continue;
    if (pins.some(([px, py]) => Math.hypot(px - x, py - y) < 26)) continue;
    const el = document.elementFromPoint(x, y);
    if (!el || el.closest("[data-act], button, .mdrawer, #mdrawer, .mv-hud .mv-area, .mv-q, .mv-mini, .mv-pill")) continue;
    return [x, y];
  }
  return null;
})()`;
const results = {};
const ready = async () => {
  for (let i = 0; i < 60; i++) {
    if (await page.eval(`!!(document.querySelector("#mvw .mv-base.on") && document.querySelector("#mkt .mv-pin, #mkt .mv-dot") && document.querySelector("#mk .ld-fill"))`)) break;
    await sleep(250);
  }
  await sleep(900);
};
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
    await page.send("Page.navigate", { url: ORIGIN + "/" });
    await sleep(1800);
    const r = {};
    // 蓋在畫面上的卡（「此事已了・入傳」這類）先按掉
    for (let i = 0; i < 4; i++) {
      const hit = await page.eval(`(() => { const b = [...document.querySelectorAll("button")].find((e) => /^(收下|知道了|好)$/.test(e.textContent.trim()) && e.getClientRects().length); if (b) b.click(); return !!b; })()`);
      if (!hit) break;
      await sleep(700);
    }
    if (s.goto === "escort") {
      // 江湖頁本週那一張卡翻到護糧那一件時的「去輿圖」（data-goto＝起點、data-then＝終點）：app.js 的那一顆按下去做的就是這兩行
      r.button = await page.eval(`(() => { const st = (S.main.week_card.steps || []).find((x) => x.then && x.target); if (!st) return null; mapGoto(st.target.location, st.then.location); goTab("map"); return { goto: st.target.location, then: st.then.location, text: st.text }; })()`);
    } else if (s.goto) {
      // 江湖頁：本週那一張卡（眼下要事）的「去輿圖」真的按（帶 data-goto；護糧多 data-then）
      await page.eval(`goTab("jianghu")`);
      await sleep(900);
      r.button = await page.eval(`(() => { const b = document.querySelector('#page [data-act="tab"][data-tab="map"][data-goto]'); if (!b) return null; const o = { goto: b.dataset.goto, then: b.dataset.then || null, text: b.textContent.trim() }; b.click(); return o; })()`);
    } else await page.eval(`goTab("map")`);
    await ready();
    if (s.zoom) {
      await page.eval(`(() => { const g = mapGeom(document.getElementById("map")), c = camOpen(g), r = mapRoom(g);
        camSet(camAt(g, (g.vw / 2 - c.x) / c.z, ((r.top + r.bottom) / 2 - c.y) / c.z, mvZ0(g) * ${s.zoom}), g); drawMarks(); return 1; })()`);
      await sleep(700);
    }
    if (s.tap) {
      const at = await page.eval(SPOT(s.tap));
      r.tapAt = at;
      if (at) {
        for (const type of ["mousePressed", "mouseReleased"]) {
          await page.send("Input.dispatchMouseEvent", { type, x: at[0], y: at[1], button: "left", buttons: type === "mousePressed" ? 1 : 0, clickCount: 1 });
        }
        await sleep(1400);
      }
    }
    if (s.sortie) { await page.eval(`(() => { const b = document.querySelector("#mbody .m-tray-go"); if (b) b.click(); return !!b; })()`); await sleep(900); }
    if (s.drawer) { await page.eval(`mapStop(${JSON.stringify(s.drawer)})`); await sleep(900); }
    if (s.wait) await sleep(s.wait);
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
