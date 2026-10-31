// node goto.mjs <tag> <帳號> <名號> [寬]：江湖頁「去輿圖」四種鈕（眼下要事、人物打算、章回卡、新手目標）＋護糧（下一站、終點）＋江湖頁小地圖，
// 每一顆都 CDP 觸控真的按；量輿圖開在哪、卡、路、你與目標在不在露出來那一塊。
import { start, stop, view, login, reload, mapReadyWait, shot, MEASURE, saveJson, sleep, SP, tap, click } from "./lib.mjs";
import { DatabaseSync } from "node:sqlite";
import fs from "node:fs";
import path from "node:path";

const [, , tag = "goto", account = "w2qb", who = "聽雨", W = "375"] = process.argv;
const H = { 375: 812, 360: 780, 320: 568, 1280: 800 };
const DESK = W === "1280";
const out = path.join(SP, "out", tag);
fs.mkdirSync(out, { recursive: true });
const db = new DatabaseSync(path.join(SP, "live.db").replace(/\//g, "\\"));
db.exec("PRAGMA busy_timeout=30000");
const put = db.prepare(`UPDATE characters SET data = json_set(data, '$.player.location', ?, '$.player.journey', json('null'), '$.player.stamina', 250) WHERE name = ?`);
const ctx = await start(9640 + (W === "375" ? 0 : W === "360" ? 10 : W === "320" ? 20 : 30), tag);
const { page } = ctx;
const R = {};
// 江湖頁本週卡：攤開「眼下要事」、按「換一件」直到 pred 的那一顆出現（只改畫面上的 S.wkStep，不送 /api）
const cycleTo = async (sel) => {
  for (let i = 0; i < 8; i++) {
    if (await page.eval(`!!document.querySelector(${JSON.stringify(sel)})`)) return true;
    await page.eval(`(() => { let b = document.querySelector('#page [data-act="wk-next"]'); if (!b) { const t = document.querySelector('#page [data-act="wk"][data-id="step"]'); if (t) t.click(); b = document.querySelector('#page [data-act="wk-next"]'); } if (b) b.click(); return !!b; })()`);
    await sleep(500);
  }
  return !!(await page.eval(`!!document.querySelector(${JSON.stringify(sel)})`));
};
const tapSel = async (sel) => {
  const info = await page.eval(`(() => { const b = document.querySelector(${JSON.stringify(sel)}); if (!b) return null; b.scrollIntoView({ block: "center" });
    return { goto: b.dataset.goto || null, then: b.dataset.then || null, i: b.dataset.i ?? null, text: b.textContent.trim(), act: b.dataset.act }; })()`);
  if (!info) return null;
  await sleep(400);
  const xy = await page.eval(`(() => { const b = document.querySelector(${JSON.stringify(sel)}); const r = b.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2, e = document.elementFromPoint(x, y);
    return { x, y, top: !!e && (e === b || b.contains(e)) }; })()`);
  if (DESK) await click(page, xy.x, xy.y); else await tap(page, xy.x, xy.y);
  return { ...info, ...xy };
};
const CASES = [
  { name: "章回卡", loc: "yingchuan", sel: "#page .ch-go[data-goto]" },
  { name: "眼下要事-章回", loc: "yingchuan", sel: "#page .wk-go[data-goto]:not([data-then])", cycle: true },
  { name: "眼下要事-護糧", loc: "yingchuan", sel: "#page .wk-go[data-then]", cycle: true },
  { name: "人物打算", loc: "yingchuan", sel: "#page .plan-card [data-goto]" },
  { name: "新手目標-眼下要事", loc: "luoyang_road", sel: '#page .wk-go[data-act="newbie-go"]', cycle: true, newbie: true },
  { name: "新手目標-為什麼", loc: "luoyang_road", sel: '#page .nb-goals [data-act="newbie-go"][data-i="0"]', why: true, newbie: true },
  { name: "新手目標-遠", loc: "runan", sel: '#page .nb-goals [data-act="newbie-go"][data-i="2"]', why: true, newbie: true },
  { name: "江湖頁小地圖", loc: "yingchuan", sel: '#page .mini [data-loc="changshe"]', mini: true },
];
try {
  await view(page, { w: Number(W), h: H[W], mobile: !DESK });
  console.log("login", await login(page, account));
  for (const k of CASES) {
    put.run(k.loc, who);
    await reload(page);
    await page.eval(`goTab("jianghu")`);
    await sleep(1200);
    if (k.cycle) await cycleTo(k.sel);
    if (k.why) {
      await page.eval(`(() => { const b = document.querySelector('#page [data-act="wk"][data-id="why"]'); if (b && b.getAttribute("aria-expanded") !== "true") b.click(); return !!b; })()`);
      await sleep(700);
    }
    const nb = k.newbie ? await page.eval(`(() => { const n = S.main.status.newbie; const opts = S.main.options.map((o) => o.id); return n ? n.rows.map((r) => ({ key: r.key, go: r.go, adjacent: !!(r.go.move && opts.some((x) => x === "move:" + r.go.move || x.startsWith("move:" + r.go.move + ":"))) })) : null; })()`) : null;
    const before = await page.eval(`(() => { const m = document.querySelector(${JSON.stringify(k.sel)}); return { tab: S.tab, found: !!m }; })()`);
    const t = await tapSel(k.sel);
    if (!t) { R[k.name] = { error: "沒有那一顆", before, nb }; console.log(k.name, JSON.stringify(R[k.name])); continue; }
    await sleep(300);
    await mapReadyWait(page);
    const m = await page.eval(MEASURE);
    const cover = await page.eval(`(() => { const vis = (e) => !!e && !!e.getClientRects().length && getComputedStyle(e).visibility !== "hidden";
      const hud = [".mv-area", ".mv-q", "#mv-mini .mv-mini", "#mv-fab .mv-me", '#mv-fab [data-act="map-fit"]'].map((s) => document.querySelector(s)).filter(vis).map((e) => [e.className || e.dataset.act, e.getBoundingClientRect()]);
      const g = mapGeom(document.getElementById("map")), c = S.mapCam, P = Object.fromEntries(S.mapBase.places.map((b) => [b.id, b]));
      const ids = [S.mapState.here, S.mapSel, S.mapThen && S.mapThen.to].filter(Boolean), out = [];
      for (const id of ids) { const x = g.x0 + c.x + P[id].x * c.z, y = g.y0 + c.y + P[id].y * c.z;
        for (const [k, r] of hud) if (x + 12 > r.left && x - 12 < r.right && y + 12 > r.top && y - 12 < r.bottom) out.push(id + "×" + k); }
      return out; })()`);
    const target = k.mini ? "changshe" : k.newbie ? (nb && nb[Number(t.i)] && nb[Number(t.i)].go.move) : t.goto;
    const name = await page.eval(`(() => { const p = S.mapBase.places.find((b) => b.id === ${JSON.stringify(target)}); return p ? p.name : null; })()`);
    const res = { button: t, nb, target, tab: await page.eval(`S.tab`), mode: m.mode, sel: m.sel, then: m.then, card: m.card, cardOk: m.card === name, route: m.route, dash: m.dash, legs: m.legs, rings: m.rings,
      z: m.z, Z0: m.Z0, lvl: m.lvl, meOn: m.meOn, selOn: m.selOn, endOn: m.endOn, meScr: m.meScr, selScr: m.selScr, endScr: m.endScr, roomTop: m.roomTop, bottom: m.bottom,
      drawer: m.drawer, drawerPx: m.drawerPx, bad: m.bad, missing: m.missing, labTexts: m.labTexts.filter((s) => /下一站|終點/.test(s) || s.startsWith(target + ":")), hscroll: m.hscroll, hudCover: cover };
    res.ok = !cover.length && res.tab === "map" && res.mode === "place" && res.sel === target && res.cardOk && res.route >= 1 && res.meOn && res.selOn && (!t.then || (res.endOn && res.dash && res.legs.length === 2));
    R[k.name] = res;
    console.log(k.name, JSON.stringify(res));
    await shot(page, path.join(out, `${k.name}.png`));
  }
  put.run("yingchuan", who);
  R.log = ctx.log;
  saveJson(path.join(out, "goto.json"), R);
  console.log("log", JSON.stringify(ctx.log));
} finally {
  await stop(ctx);
}
