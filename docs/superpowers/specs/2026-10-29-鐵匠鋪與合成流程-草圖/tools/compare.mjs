// 設計稿沒定、先替企劃者選的畫面（第九節「留給開發的」）：每一組甲是做進程式的那一種，乙、丙是在真的頁面上注入樣式或搬動節點的原型
// （程式碼不動；注入前先停掉輪詢，免得十秒一次的重畫把注入的東西蓋掉）。375 淺各拍一張：node compare.mjs <輸出根>
import fs from "node:fs";
import { launch, newPage, sleep } from "./cdp.mjs";

const HERE = new URL(".", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
const ROOT = process.argv[2];
const BASE = "http://smithweb.localhost:8154";
const PW = fs.readFileSync(`${HERE}live/smithjia_password.txt`, "utf8").trim();
const proc = await launch(`${HERE}chrome-compare`, 9357);
const page = await newPage(9357);
const ev = (js) => page.eval(js);
const click = (sel) => ev(`(() => { const el = document.querySelector(${JSON.stringify(sel)}); if (!el) return false; el.click(); return true; })()`);
const freeze = () => ev(`(() => { window.fetch = () => new Promise(() => {}); const s = document.createElement("style");
  s.textContent = "*,*::before,*::after{transition:none!important;animation:none!important} #toast{display:none!important}"; document.head.appendChild(s); return true; })()`);
const css = (text) => ev(`(() => { const s = document.createElement("style"); s.textContent = ${JSON.stringify(text)}; document.head.appendChild(s); return true; })()`);
async function open(tab) {
  await page.goto(`${BASE}/`);
  await sleep(1200);
  await click(`.shop-tabs [data-tab="${tab}"]`);
  await sleep(500);
}
const shot = async (dir, name) => { await sleep(300); await page.shot(`${ROOT}/${dir}/對比-${name}.png`); };

try {
  await page.viewport(375, 812, false);
  await page.goto(`${BASE}/`);
  await ev(`fetch("/api/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ login: "smithjia", password: ${JSON.stringify(PW)} }) })`);
  const inShop = await ev(`fetch("/api/main").then((r) => r.json()).then((m) => !!m.shop)`);
  if (!inShop) await ev(`fetch("/api/choose", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: "act:smith" }) })`);

  // ── 一、爐火那一行（C，3.2）：甲 爐子底下一行；乙 換掉頂上鐵匠那一句；丙 火上掛一枚小籤 ──
  await open("forge"); await freeze();
  await shot("C", "爐火那一行-甲-爐子底下一行");
  await open("forge"); await freeze();
  await ev(`(() => { const say = document.querySelector(".fu-say"); const line = document.querySelector(".shop-layer > .shop-line");
    line.innerHTML = say.innerHTML; line.style.display = "flex"; line.style.alignItems = "center"; line.style.gap = "8px"; line.style.justifyContent = "space-between";
    line.querySelector(".fu-look").style.cssText = "width:auto;min-height:30px;padding:2px 16px"; say.remove(); return true; })()`);
  await shot("C", "爐火那一行-乙-換掉鐵匠那一句");
  await open("forge"); await freeze();
  await ev(`(() => { const say = document.querySelector(".fu-say"); const fire = document.querySelector(".fu-fire");
    fire.style.position = "relative"; const tag = document.createElement("span"); tag.textContent = "看火候 50 兩";
    tag.style.cssText = "position:absolute;left:50%;bottom:-14px;transform:translateX(-50%);white-space:nowrap;padding:2px 8px;border-radius:10px;background:#f2c46a;color:#1e1510;font:600 11px var(--sans)";
    fire.appendChild(tag); say.remove(); return true; })()`);
  await shot("C", "爐火那一行-丙-火上一枚小籤");

  // ── 二、灰格與小單（A，3.3）：甲 那一排底下展開；乙 從畫面底下浮一張小單（同確認框的樣子） ──
  await open("forge");
  await click('[data-act="shop-brew"][data-attr="柔"][data-tier="2"]'); await sleep(400);
  await freeze();
  await shot("A", "灰格小單-甲-那一排底下展開");
  await ev(`(() => { const sheet = document.querySelector(".brew-sheet"); const layer = document.createElement("div"); layer.className = "ask-layer";
    layer.innerHTML = '<div class="ask-bg"></div><div class="ask" role="alertdialog"></div>'; const box = layer.querySelector(".ask");
    box.innerHTML = '<p>' + sheet.querySelector(".brew-ask").innerHTML + '</p><p class="muted" style="margin-top:-8px">' + sheet.querySelector(".brew-odds").innerHTML + '</p>'
      + '<div class="row"><button class="btn">取消</button><button class="btn danger">熬</button></div>';
    sheet.remove(); document.body.appendChild(layer); return true; })()`);
  await shot("A", "灰格小單-乙-底下浮一張");

  // ── 三、裝備庫一列的折法（C，3.4）：甲 名字一行、四顆鈕一整行；乙 名字在左、四顆鈕 2×2 在右；丙 一行四顆不帶小字（小字收進鈕的 title） ──
  await open("rack"); await freeze();
  await ev(`document.querySelector(".rk-cap").scrollIntoView({ block: "start" })`);
  await shot("C", "裝備庫一列-甲-鈕另起一行");
  await open("rack"); await freeze();
  await css(".shop-layer .rk-row { grid-template-columns: auto minmax(0, 1fr) 46%; } .shop-layer .rk-btns { grid-column: 3; grid-row: 1; grid-template-columns: repeat(2, minmax(0, 1fr)); }");
  await ev(`document.querySelector(".rk-cap").scrollIntoView({ block: "start" })`);
  await shot("C", "裝備庫一列-乙-右邊二乘二");
  await open("rack"); await freeze();
  await css(".shop-layer .rk-btn small { display: none; } .shop-layer .rk-btn { min-height: 2.4em; }");
  await ev(`document.querySelector(".rk-cap").scrollIntoView({ block: "start" })`);
  await shot("C", "裝備庫一列-丙-鈕不帶小字");

  // ── 四、收藏冊的格子（E，3.8）：甲 寫名字的方格（一排四格）；乙 圓形的印（一排五枚）；丙 一件一行的清單 ──
  await open("divine"); await freeze();
  await ev(`document.querySelector(".dv-album").scrollIntoView({ block: "center" })`);
  await shot("E", "收藏冊-甲-方格");
  await open("divine"); await freeze();
  await css(".shop-layer .dv-album { grid-template-columns: repeat(5, minmax(0, 1fr)); justify-items: center; } .shop-layer .dv-cell { width: 3.9em; height: 3.9em; min-height: 0; border-radius: 50%; padding: 2px; font-size: 0.73em; }");
  await ev(`document.querySelector(".dv-album").scrollIntoView({ block: "center" })`);
  await shot("E", "收藏冊-乙-圓印");
  await open("divine"); await freeze();
  await css(".shop-layer .dv-album { grid-template-columns: 1fr; gap: 4px; } .shop-layer .dv-cell { min-height: 2.2em; justify-content: flex-start; padding: 4px 10px; }");
  await ev(`document.querySelector(".dv-album").scrollIntoView({ block: "start" })`);
  await shot("E", "收藏冊-丙-一件一行");
} finally {
  page.close();
  proc.kill();
}
