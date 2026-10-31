// node cover.mjs <tag> <帳號> <名號>：FB-9094 的量法（照 QA 的 hudcover.mjs，同一個指標）。每一處站一次 × 375／360／320 打開輿圖（第一眼、抽屜一行），
// 量兩步內（含腳下）的小圖（不含徽：img／svg 那一塊）被看得到的浮著的那幾樣（區名、🔍、小地圖〔收成一顆時是那一顆〕、右下的圓鈕）各蓋住幾成；
// 同一輪也記：被蓋一半以上的那一處有沒有掛箭頭牌（丙）、名字在畫面裡的有幾個、縮到 11px 的有幾個（讓步比例）、倍率與中心（甲會挪中心）。
// 伺服器的 web/ 換成哪一版由外面的 swap_web.py 決定；每一處的站位直接寫進資料庫（伺服器每次拿鎖都重讀）。
import { start, stop, view, login, reload, openMap, saveJson, sleep, SP } from "./lib.mjs";
import { DatabaseSync } from "node:sqlite";
import fs from "node:fs";
import path from "node:path";

const [, , tag = "cover", account = "w2qb", who = "聽雨", only = ""] = process.argv;
const H = { 375: 812, 360: 780, 320: 568 };
const out = path.join(SP, "out", tag);
fs.mkdirSync(out, { recursive: true });
const db = new DatabaseSync(path.join(SP, "live.db").replace(/\//g, "\\"));
db.exec("PRAGMA busy_timeout=30000");
const put = db.prepare(`UPDATE characters SET data = json_set(data, '$.player.location', ?, '$.player.journey', json('null'), '$.player.stamina', 250) WHERE name = ?`);
const COVER = `(() => { const box = document.getElementById("map").getBoundingClientRect(), g = mapGeom(document.getElementById("map")), st = S.mapState, base = S.mapBase;
  const dr = document.getElementById("mdrawer").getBoundingClientRect(), bottom = Math.min(g.vh, dr.top - box.top);
  const adj = {}; for (const [a, b] of base.edges) { (adj[a] = adj[a] || []).push(b); (adj[b] = adj[b] || []).push(a); }
  const hops = { [st.here]: 0 }, q = [st.here]; for (let i = 0; i < q.length; i++) for (const n of adj[q[i]] || []) if (!(n in hops)) { hops[n] = hops[q[i]] + 1; q.push(n); }
  const R = (e) => { const r = e.getBoundingClientRect(); return [r.left - box.left, r.top - box.top, r.right - box.left, r.bottom - box.top]; };
  const shown = (e) => e.getClientRects().length && getComputedStyle(e).visibility !== "hidden" && getComputedStyle(e).display !== "none";
  const hud = [...document.querySelectorAll(".mv-area, .mv-q, .mv-mini, .mv-mini-c, .mv-fab button")].filter(shown).map((e) => ({ who: e.dataset.act || e.className, r: R(e) }));
  const pills = new Set([...document.querySelectorAll("#mv-pills .mv-pill")].filter(shown).map((e) => e.dataset.id));
  const out = [];
  for (const e of document.querySelectorAll("#mkt .mv-pin")) {
    const k = e.querySelector("img, svg") || e, r = R(k), area = (r[2] - r[0]) * (r[3] - r[1]);
    if (!(r[2] > 0 && r[0] < g.vw && r[3] > 0 && r[1] < bottom)) continue;
    for (const h of hud) { const w = Math.min(r[2], h.r[2]) - Math.max(r[0], h.r[0]), hh = Math.min(r[3], h.r[3]) - Math.max(r[1], h.r[1]);
      if (w > 0 && hh > 0) { const f = (w * hh) / area; if (f >= 0.25) out.push({ id: e.dataset.id, hop: hops[e.dataset.id] ?? null, by: h.who, f: +f.toFixed(2), pill: pills.has(e.dataset.id) }); } }
  }
  const P = Object.fromEntries(base.places.map((b) => [b.id, b])), c = S.mapCam;
  const inView = (id) => { const p = P[id]; if (!p) return false; const x = c.x + p.x * c.z, y = c.y + p.y * c.z; return x >= 0 && x <= g.vw && y >= 0 && y <= bottom; };
  const labs = [...document.querySelectorAll("#mkt .mv-lab")].filter((e) => inView(e.dataset.id));
  const near2 = Object.entries(hops).filter(([id, h]) => h <= 2 && st.places[id]).map(([id]) => id);
  return { here: st.here, out, z: +c.z.toFixed(4), cam: [+c.x.toFixed(1), +c.y.toFixed(1)], labs: labs.length, tiny: labs.filter((e) => e.classList.contains("tiny")).length,
    leads: document.querySelectorAll("#mkt .mv-lead").length, pills: [...pills], near2In: near2.filter(inView).length, near2: near2.length }; })()`;
const ctx = await start(9650, tag);
const { page } = ctx;
const rows = [];
try {
  await view(page, { w: 375, h: 812 });
  console.log("login", await login(page, account));
  await reload(page);
  let ids = await page.eval(`fetch("/api/map/base").then((r) => r.json()).then((b) => b.places.map((p) => p.id))`);
  if (only) ids = ids.filter((x) => only.split(",").includes(x));
  for (const id of ids) {
    put.run(id, who);
    for (const w of [375, 360, 320]) {
      await view(page, { w, h: H[w] });
      await reload(page);
      await openMap(page);
      const c = await page.eval(COVER);
      rows.push({ id, w, ...c });
    }
    console.log(id, JSON.stringify(rows.filter((r) => r.id === id).map((r) => [r.w, r.out.filter((o) => o.f >= 0.5).map((o) => `${o.id}(${o.hop})<${o.by}:${o.f}${o.pill ? "+pill" : ""}`).join(" ")])));
  }
  put.run("yingchuan", who);
  saveJson(path.join(out, "cover.json"), { rows, log: ctx.log });
  console.log("log", JSON.stringify(ctx.log));
} finally {
  await stop(ctx);
}
