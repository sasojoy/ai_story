// node shoot_fix.mjs <輸出資料夾> <密碼檔> <帳號> <鏡頭.json>：W2 修正輪重拍（照 W2 的 shoot.mjs）。登入、打開輿圖、量數字、拍 PNG（兩倍像素、減少動態），
// measure.json 存在輸出資料夾。跟 W2 那一支不同的：觸控模擬開著，江湖頁「去輿圖」兩件（章回、護糧）都是 CDP 觸控真的按（護糧那一件先攤開「眼下要事」、
// 按「↻ 換一件」翻到它〔只改畫面上的 S.wkStep，不送 /api〕再按）；每一張另外量點擊範圍（區名 chip、箭頭牌、底條兩塊：elementFromPoint 往外幾 px 還點不點得到）
// 與選中的名字字級。鏡頭：[{ name, w, h, dark, mobile, tap, goto: true|"escort", drawer, sortie, zoom, fold: true〔全開捲到下面再收回一行〕, wait }]
import { launch, newPage, sleep } from "./cdp.mjs";
import fs from "node:fs";
import path from "node:path";

const [, , outDir, pwFile, account, shotsFile] = process.argv;
const ORIGIN = "http://w2fix.localhost:8181";
const shots = JSON.parse(fs.readFileSync(shotsFile, "utf8"));
fs.mkdirSync(outDir, { recursive: true });
const { proc, cdp } = await launch({ port: 9481, dataDir: path.join(outDir, `prof-${Date.now()}`) });
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
  // 點擊範圍：從那一顆的上緣、下緣往外 d px 的那一點，elementFromPoint 還是不是它（d 一路加到點不到為止）＝點得到的高
  const reach = (el) => {
    if (!el) return null;
    const r = el.getBoundingClientRect(), cx = r.left + r.width / 2;
    const hits = (y) => { const e = document.elementFromPoint(cx, y); return !!e && (e === el || el.contains(e)); };
    let up = 0, dn = 0;
    while (up < 30 && hits(r.top - up - 0.5)) up += 1;
    while (dn < 30 && hits(r.bottom + dn + 0.5)) dn += 1;
    return { h: +r.height.toFixed(1), w: +r.width.toFixed(1), tap: +(r.height + up + dn).toFixed(1) };
  };
  const mbody = document.getElementById("mbody"), trayEl = document.querySelector("#mbody .m-tray");
  const sel = S.mapSel || (S.mapMode === "overview" ? S.mapPreview : null), selLab = sel && document.querySelector('#mkt .mv-lab[data-id="' + sel + '"]');
  return { z: +z.toFixed(3), z0: +mvZ0(g).toFixed(3), level: mvLevel(z, g), vw: g.vw, vh: g.vh, roomBottom: room.bottom, hscroll: document.documentElement.scrollWidth > innerWidth,
    labs: labs.map((o) => o.id), tiny: all("#mkt .mv-lab.tiny").map((e) => e.dataset.id), leads: all("#mkt .mv-lead").length, pills: pills.map((o) => o.id),
    overlap: { labLab: ll, labIcon: li, labPill: lp, labHud: lh, pillIcon: pi, labOut: out }, pairs,
    area: (document.querySelector("#mv-area .t") || {}).textContent, mini: !!document.querySelector("#mv-mini .mv-mini"),
    tray: trayEl ? trayEl.textContent.replace(/\\s+/g, " ").trim() : null, drawer: S.mapDrawer, drawerPx: document.getElementById("mdrawer").offsetHeight,
    scrollTop: mbody ? mbody.scrollTop : null, trayShown: trayEl ? (() => { const a = trayEl.getBoundingClientRect(), b = mbody.getBoundingClientRect(); return a.top >= b.top - 0.5 && a.bottom <= b.bottom + 0.5; })() : null,
    reach: { area: reach(document.querySelector("#mv-area")), pills: all("#mv-pills .mv-pill").map(reach), wk: reach(document.querySelector("#mbody .m-tray-wk")), go: reach(document.querySelector("#mbody .m-tray-go")) },
    selLab: selLab ? { id: sel, tiny: selLab.classList.contains("tiny"), px: getComputedStyle(selLab.querySelector(".nm")).fontSize } : null,
    legs: [...document.querySelectorAll("#mkt .mv-wk.leg")].map((e) => e.textContent), rings: document.querySelectorAll("#mkt .mv-ring").length,
    dash: document.getElementById("mkr").innerHTML.includes("stroke-dasharray"),
    mode: S.mapMode, sel: S.mapSel, then: S.mapThen, filter: S.mapFilter, week: S.mapState.week };
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
const tap = async (x, y) => {
  await page.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x, y, id: 1 }] });
  await sleep(60);
  await page.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
};
// 捲到看得到、量中心、真的觸控按一下（回按的是哪一顆）
const tapSel = async (expr) => {
  const at = await page.eval(`(() => { const b = ${expr}; if (!b) return null; b.scrollIntoView({ block: "center" }); return { goto: b.dataset.goto || null, then: b.dataset.then || null, text: b.textContent.trim(), cls: b.className }; })()`);
  if (!at) return null;
  await sleep(350);
  const xy = await page.eval(`(() => { const b = ${expr}; const r = b.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2, e = document.elementFromPoint(x, y); return { x, y, top: e === b || b.contains(e) }; })()`);
  await tap(xy.x, xy.y);
  return { ...at, ...xy };
};
const results = {};
const ready = async () => {
  for (let i = 0; i < 60; i++) {
    if (await page.eval(`!!(S.tab === "map" && document.querySelector("#mvw .mv-base.on") && document.querySelector("#mkt .mv-pin, #mkt .mv-dot") && document.querySelector("#mk .ld-fill"))`)) break;
    await sleep(250);
  }
  await sleep(1100);
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
    const mobile = s.mobile !== false;
    await page.send("Emulation.setDeviceMetricsOverride", { width: s.w, height: s.h, deviceScaleFactor: 2, mobile });
    await page.send("Emulation.setTouchEmulationEnabled", { enabled: mobile, maxTouchPoints: mobile ? 5 : 1 });
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
    if (s.goto) {
      await page.eval(`goTab("jianghu")`);
      await sleep(1100);
      if (s.goto === "escort") {
        // 本週卡翻到護糧那一件（「↻ 換一件」只改畫面上的 S.wkStep、重畫本週卡，不送 /api）
        for (let i = 0; i < 6; i++) {
          if (await page.eval(`!!document.querySelector('#page .wk-go[data-then]')`)) break;
          await page.eval(`(() => { let b = document.querySelector('#page [data-act="wk-next"]'); if (!b) { const t = document.querySelector('#page [data-act="wk"][data-id="step"]'); if (t) t.click(); b = document.querySelector('#page [data-act="wk-next"]'); } if (b) b.click(); return !!b; })()`);
          await sleep(500);
        }
        r.button = await tapSel(`document.querySelector('#page .wk-go[data-then]')`);
      } else r.button = await tapSel(`document.querySelector('#page .wk-go[data-goto]:not([data-then])') || document.querySelector('#page [data-act="tab"][data-tab="map"][data-goto]:not([data-then])')`);
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
      if (at) { await tap(at[0], at[1]); await sleep(1400); }
    }
    if (s.sortie) { r.sortieTap = await tapSel(`document.querySelector("#mbody .m-tray-go")`); await sleep(900); }
    if (s.drawer) { await page.eval(`mapStop(${JSON.stringify(s.drawer)})`); await sleep(900); }
    if (s.fold) {
      // 全開、往下捲，再收回一行（W2 審查：以前收回之後 scrollTop 照留、底條被捲走）；再點一處、拉高、往下捲卡、按卡上的 ✕
      await page.eval(`mapStop("full")`); await sleep(700);
      r.foldFull = await page.eval(`(() => { const b = document.getElementById("mbody"); b.scrollTop = 420; return b.scrollTop; })()`);
      await page.eval(`mapStop("peek")`); await sleep(900);
      r.foldPeek = await page.eval(`document.getElementById("mbody").scrollTop`);
      await page.eval(`mapPick("changshe")`); await sleep(1300);
      r.cardScroll = await page.eval(`(() => { const b = document.getElementById("mbody"); b.scrollTop = 160; return b.scrollTop; })()`);
      // 再點同一處（長社的小圖，真的觸控）：收卡回底條
      const pin = await page.eval(`(() => { const e = document.querySelector('#mkt .mv-pin[data-id="changshe"]'); if (!e) return null; const r = e.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
        const t = document.elementFromPoint(x, y); return [x, y, !!t && !!t.closest('[data-id="changshe"]')]; })()`);
      r.backTap = pin;
      if (pin) await tap(pin[0], pin[1]);
      await sleep(1400);
    }
    if (s.wait) await sleep(s.wait);
    Object.assign(r, await page.eval(MEASURE));
    const shot = await page.send("Page.captureScreenshot", { format: "png" });
    fs.writeFileSync(path.join(outDir, s.name + ".png"), Buffer.from(shot.data, "base64"));
    results[s.name] = r;
    console.log(s.name, JSON.stringify({ z: r.z, level: r.level, tiny: r.tiny, leads: r.leads, overlap: r.overlap, selLab: r.selLab, reach: r.reach, tray: r.tray, drawerPx: r.drawerPx, scroll: [r.foldPeek, r.scrollTop, r.trayShown], button: r.button && r.button.goto + ">" + r.button.then, legs: r.legs, rings: r.rings, dash: r.dash }));
  }
  fs.writeFileSync(path.join(outDir, "measure.json"), JSON.stringify(results, null, 1));
} finally {
  cdp.close();
  try { proc.kill(); } catch (e) { /* */ }
  await sleep(400);
}
