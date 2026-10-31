// node optshot.mjs <tag> <帳號> <名號>：FB-9094 選項的三張（照派工）：375×812 站潁水河畔打開、375×812 站豪族塢堡打開、320×568 站潁川郡打開。
// 伺服器的 web/ 換成哪一版由外面的 swap_web.py 決定；站位直接寫進資料庫。每一張也量兩步內被蓋 ≥50% 的（同 cover.mjs）與名字縮字。
import { start, stop, view, login, reload, openMap, shot, saveJson, sleep, SP } from "./lib.mjs";
import { DatabaseSync } from "node:sqlite";
import fs from "node:fs";
import path from "node:path";

const [, , tag = "opt", account = "w2qa", who = "映雪"] = process.argv;
const out = path.join(SP, "out", tag);
fs.mkdirSync(out, { recursive: true });
const db = new DatabaseSync(path.join(SP, "live.db").replace(/\//g, "\\"));
db.exec("PRAGMA busy_timeout=30000");
const put = db.prepare(`UPDATE characters SET data = json_set(data, '$.player.location', ?, '$.player.journey', json('null'), '$.player.stamina', 250) WHERE name = ?`);
const COVER = fs.readFileSync(path.join(SP, "cover.mjs"), "utf8").match(/const COVER = `([\s\S]*?)`;\n/)[1];
const SHOTS = [["yingshui", 375, 812], ["haozu_fort", 375, 812], ["yingchuan", 320, 568]];
const ctx = await start(9660, tag);
const { page } = ctx;
const R = [];
try {
  await view(page, { w: 375, h: 812 });
  console.log("login", await login(page, account));
  for (const [loc, w, h] of SHOTS) {
    put.run(loc, who);
    await view(page, { w, h });
    await reload(page);
    await openMap(page);
    await sleep(600);
    const c = await page.eval(COVER);
    const home = await page.eval(`(() => { const b = document.querySelector("#mv-fab .mv-me"); return b ? b.textContent : null; })()`);
    R.push({ loc, w, home, ...c });
    console.log(loc, w, JSON.stringify({ home, z: c.z, cam: c.cam, half: c.out.filter((o) => o.hop !== null && o.hop <= 2 && o.f >= 0.5).map((o) => `${o.id}(${o.hop})<${o.by}:${o.f}${o.pill ? "+pill" : ""}`), labs: c.labs, tiny: c.tiny, pills: c.pills }));
    await shot(page, path.join(out, `${loc}-${w}.png`));
  }
  put.run("yingchuan", who);
  saveJson(path.join(out, "optshot.json"), { R, log: ctx.log });
  console.log("log", JSON.stringify(ctx.log));
} finally {
  await stop(ctx);
}
