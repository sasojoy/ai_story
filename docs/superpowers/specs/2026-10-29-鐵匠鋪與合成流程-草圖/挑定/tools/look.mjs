// 拍與量：node look.mjs <輸出資料夾> <鏡頭檔.json>
// 鏡頭檔：[{name, w, h, dark, tab, pre (頁面裡跑的 JS，可 await), measure (回傳要記的值的 JS 運算式), wait}]
import fs from "node:fs";
import { launch, newPage, sleep } from "../../tools/cdp.mjs"; // 拍的時候跟 cdp.mjs 放在同一個 scratch 資料夾；收進這裡改指上一層的那一份

const OUT = process.argv[2];
const SHOTS = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const BASE = "http://smithpicks.localhost:8161";
const PWDIR = "C:\\Users\\ray61\\AppData\\Local\\Temp\\claude\\C--Ray--------\\86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444\\scratchpad\\smithpicks";
const PW = fs.readFileSync(`${PWDIR}\\smithjia_password.txt`, "utf8").trim();
fs.mkdirSync(OUT, { recursive: true });
const proc = await launch(`${OUT}\\chrome-profile`, 9371);
const page = await newPage(9371);
const ev = (js) => page.eval(js);
const results = {};
try {
  await page.viewport(375, 812, false);
  await page.goto(`${BASE}/`);
  const login = await ev(`fetch("/api/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ login: "smithjia", password: ${JSON.stringify(PW)} }) }).then((r) => r.status)`);
  const inShop = await ev(`fetch("/api/main").then((r) => r.json()).then((m) => !!m.shop)`);
  if (!inShop) await ev(`fetch("/api/choose", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: "act:smith" }) }).then((r) => r.status)`);
  console.log("login", login, "inShop", inShop);
  for (const s of SHOTS) {
    await page.viewport(s.w, s.h, !!s.dark);
    await page.goto(`${BASE}/`);
    await sleep(1300);
    if (s.tab) {
      await ev(`(() => { const el = document.querySelector('.shop-tabs [data-tab="${s.tab}"]'); if (el) el.click(); return !!el; })()`);
      await sleep(500);
    }
    if (s.css) await ev(`(() => { const st = document.createElement("style"); st.textContent = ${JSON.stringify(s.css)}; document.head.appendChild(st); return true; })()`);
    if (s.pre) { await ev(`(async () => { ${s.pre} })()`); await sleep(s.wait || 500); }
    if (s.measure) results[s.name] = await ev(`(async () => { ${s.measure} })()`);
    if (s.measureFile) results[s.name] = await ev(fs.readFileSync(s.measureFile, "utf8"));
    await sleep(250);
    await page.shot(`${OUT}\\${s.name}.png`);
    console.log("shot", s.name);
  }
} finally {
  fs.writeFileSync(`${OUT}\\measure.json`, JSON.stringify(results, null, 1));
  page.close();
  proc.kill();
  await sleep(800);
  fs.rmSync(`${OUT}\\chrome-profile`, { recursive: true, force: true });
}
