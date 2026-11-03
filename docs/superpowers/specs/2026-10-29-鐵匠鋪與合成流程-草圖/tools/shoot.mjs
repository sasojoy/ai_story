// 鐵匠鋪網頁 A、C、E 的真實畫面：375 淺、375 深、1280 淺各拍一輪（node shoot.mjs <輸出根>），量裝備庫一列的幾何寫進 measure.json。
// 局面是 prep.py 擺好的（鐵衣客）；會改狀態的（看火候、熬一個）排在最後，三種寬度各拍一次「之後」。
import fs from "node:fs";
import { launch, newPage, sleep } from "./cdp.mjs";

const HERE = new URL(".", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
const ROOT = process.argv[2];
const BASE = "http://smithweb.localhost:8154";
const PW = fs.readFileSync(`${HERE}live/smithjia_password.txt`, "utf8").trim();
const VPS = [["375淺", 375, 812, false], ["375深", 375, 812, true], ["1280", 1280, 900, false]];
const measure = {};
for (const b of ["A", "C", "E"]) fs.mkdirSync(`${ROOT}/${b}`, { recursive: true });

const proc = await launch(`${HERE}chrome-shoot`, 9355);
const page = await newPage(9355);
const ev = (js) => page.eval(js);
const click = (sel) => ev(`(() => { const el = document.querySelector(${JSON.stringify(sel)}); if (!el) return false;
  if (typeof el.click === "function") el.click(); else el.dispatchEvent(new MouseEvent("click", { bubbles: true })); return true; })()`);
const still = () => ev(`(() => { if (!document.getElementById("no-motion")) { const s = document.createElement("style"); s.id = "no-motion";
  s.textContent = "*,*::before,*::after{transition:none!important;animation:none!important}"; document.head.appendChild(s); } return true; })()`);
const post = (url, body) => ev(`fetch(${JSON.stringify(url)}, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(${JSON.stringify(body)}) }).then((r) => r.status)`);
const into = (sel, block = "center") => ev(`(() => { const el = document.querySelector(${JSON.stringify(sel)}); if (el) el.scrollIntoView({ block: "${block}" }); return !!el; })()`);
async function reload() { await page.goto(`${BASE}/`); await sleep(1200); await still(); }
async function shop(tab) {
  const m = await ev(`fetch("/api/main").then((r) => r.json()).then((m) => !!m.shop)`);
  if (!m) { await post("/api/choose", { id: "act:smith" }); }
  await reload();
  if (tab) { await click(`.shop-tabs [data-tab="${tab}"]`); await sleep(400); }
}
async function leave() {
  const m = await ev(`fetch("/api/main").then((r) => r.json()).then((m) => m.shop ? m.shop.back : null)`);
  if (m) await post("/api/choose", { id: m });
  await reload();
}
const shot = async (batch, name, vp) => { await sleep(250); await page.shot(`${ROOT}/${batch}/${name}-${vp}.png`); };

// 裝備庫一列量到的：每一個不折行的小段有沒有被拆、四顆鈕同一行、鈕裡的字有沒有被切、有沒有橫向捲軸
const RACK_GEOM = `(() => {
  const rows = [...document.querySelectorAll(".rk-row")].map((row) => {
    const nb = [...row.querySelectorAll(".nb")];
    const btns = [...row.querySelectorAll(".rk-btns > .btn")];
    const tops = new Set(btns.map((b) => Math.round(b.getBoundingClientRect().top)));
    return { name: row.querySelector(".winfo b").textContent, nb: nb.length, nbSplit: nb.filter((s) => s.getClientRects().length !== 1).map((s) => s.textContent),
      btnRows: tops.size, clipped: btns.filter((b) => b.scrollWidth > b.clientWidth + 0.5).map((b) => b.textContent.trim()),
      btnW: btns.map((b) => Math.round(b.getBoundingClientRect().width)), rowH: Math.round(row.getBoundingClientRect().height) };
  });
  const body = document.querySelector(".shop-layer .shop-body");
  return { scroll: document.documentElement.scrollWidth <= innerWidth && (!body || body.scrollWidth <= body.clientWidth), width: innerWidth,
    docW: document.documentElement.scrollWidth, bodyW: body ? [body.scrollWidth, body.clientWidth] : null, rows };
})()`;

try {
  for (const [vp, w, h, dark] of VPS) {
    await page.viewport(w, h, dark);
    await page.goto(`${BASE}/`);
    console.log(vp, "login", await post("/api/login", { login: "smithjia", password: PW }));
    // ── E：架上那一行、神器頁（點一格翻出神器譜那一行）──
    await shop("shelf");
    await shot("E", "架上那一行", vp);
    await click('.shop-tabs [data-tab="divine"]'); await sleep(300);
    await shot("E", "神器頁", vp);
    await click('[data-act="dv-cell"]'); await sleep(900); await into(".dv-line");
    await shot("E", "神器頁-點一格", vp);
    // ── A：打造頁的灰格、點開熬的小單；C：爐火那一行 ──
    await click('.shop-tabs [data-tab="forge"]'); await sleep(400);
    await shot("C", "打造頁-爐火還沒看", vp);
    await click('[data-act="shop-brew"][data-attr="柔"][data-tier="2"]'); await sleep(300); await into(".brew-sheet", "end");
    await shot("A", "打造頁-灰格與小單", vp);
    await click('[data-act="shop-brew-close"]'); await sleep(300);
    // ── C、E：裝備庫（身上那件、每列四顆鈕、淬煉 N/M、磨得慢；勾兩件、確認框）──
    await click('.shop-tabs [data-tab="rack"]'); await sleep(400);
    await shot("C", "裝備庫-最上面", vp);
    measure[vp] = await ev(RACK_GEOM);
    await into(".rk-row:nth-of-type(3)", "start");
    await shot("E", "裝備庫-淬煉上限與磨得慢", vp);
    await click('[data-act="rack-pick"][data-id="兵:91"]'); await sleep(200);
    await click('[data-act="rack-pick"][data-id="兵:93"]'); await sleep(300);
    await into('[data-id="兵:93"]', "center");
    await shot("C", "裝備庫-勾了兩件", vp);
    await click('[data-act="rack-melt"]'); await sleep(400);
    await shot("C", "裝備庫-批量拆解確認", vp);
    await click('.ask [data-act="ask-no"]'); await sleep(200);
    if (w === 375) { // 360、320 也量一次（只量、不拍）
      for (const nw of [360, 320]) {
        await page.viewport(nw, 740, dark); await sleep(400);
        measure[`${vp}-${nw}`] = await ev(RACK_GEOM);
      }
      await page.viewport(w, h, dark); await sleep(300);
    }
    // ── 出店：A 作罷先問、C 預覽卡真意、E 修練頁那一列 ──
    await leave();
    await click('.tab[data-tab="practice"]'); await sleep(600); await still();
    await click('[data-act="hero-node"][data-key="weapon"]'); await sleep(600);
    await into(".wrow", "center");
    await shot("E", "修練頁-兵器那一列", vp);
    await reload();
    await click('.tab[data-tab="practice"]'); await sleep(500);
    await click('[data-act="create-open"]'); await sleep(500);
    await click('[data-act="create-cancel"]'); await sleep(500);
    await shot("A", "自創作罷先問", vp);
    await click('.ask [data-act="ask-no"]'); await sleep(200);
    await reload();
    await click('.tab[data-tab="practice"]'); await sleep(500);
    await click('[data-act="tab"][data-tab="craft"]'); await sleep(800);
    for (const id of ["feng", "haoran"]) {
      const chip = `[data-act="pick"][data-type="ins"][data-id="${id}"]`;
      if (!(await ev(`!!document.querySelector(${JSON.stringify(chip)})`))) { await click('[data-act="pot-open"]'); await sleep(600); }
      await click(chip); await sleep(1000);
    }
    await click('[data-act="pot-close"]'); await sleep(400);
    await into(".made-card.preview", "center");
    await shot("C", "煉製預覽卡-真意", vp);
  }
  // ── 會改狀態的排最後：看火候（爐火旺）、熬一個（鐵匠那一句換成結果）──
  for (const [vp, w, h, dark] of VPS) {
    await page.viewport(w, h, dark);
    await shop("forge");
    if (vp === "375淺") { await click('[data-act="shop-furnace"]'); await sleep(1200); await still(); }
    await shot("C", "打造頁-看過火候", vp);
  }
  await page.viewport(375, 812, false);
  await shop("forge");
  await click('[data-act="shop-brew"][data-attr="柔"][data-tier="2"]'); await sleep(300);
  await click('[data-act="shop-brew-go"]'); await sleep(1500);
  await shot("A", "打造頁-熬成了", "375淺");
  fs.writeFileSync(`${HERE}measure.json`, JSON.stringify(measure, null, 1));
  console.log(JSON.stringify(Object.fromEntries(Object.entries(measure).map(([k, m]) => [k, { scroll: m.scroll,
    split: m.rows.flatMap((r) => r.nbSplit), rows2: m.rows.filter((r) => r.btnRows !== 1).map((r) => r.name), clipped: m.rows.flatMap((r) => r.clipped) }]))));
} finally {
  page.close();
  proc.kill();
}
