// 第一次登入、略過序章（之後才擺人與局面）
import { boot, login, close, ORIGIN, SP } from "./common.mjs";
import path from "node:path";

const { proc, cdp, page, log } = await boot(9581, path.join(SP, "out", "prep"));
try {
  console.log("login", await login(page));
  console.log("skip", await page.eval(`fetch("/api/do/skip_tutorial", {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"}).then((r) => r.status)`));
  const m = await page.eval(`fetch("/api/main").then((r) => r.json()).then((j) => ({loc: j.status && (j.status.location || j.status.place), keys: Object.keys(j.status || {}).slice(0, 40)}))`);
  console.log(JSON.stringify(m));
  console.log("log", JSON.stringify(log));
} finally {
  await close(cdp, proc);
}
