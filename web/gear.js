/* 天下大勢的網頁前端：裝備（功能包 tianxia/features/gear/，開發規範手冊 3.7、G9）。
 *
 * 裝備的一格（gearEffect、gearCell）與馬市（marketHtml）的畫法。
 * 跟 mall.js 一樣是一般的 <script>：頂層的名字同在一個全域裡；/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 * 全部拆包第 65 批從 app.js 逐行切出來（計畫 docs/superpowers/plans/2026-11-06-網頁殼化-第65批.md）。點擊用 registerClicks 登記在這支檔；店面的框（shopHtml、renderShop）照舊在 app.js（殼）。
 */
"use strict";

  // 「裝備」那一段的一格（gearBlock）：圖示、欄名、階品；裝了什麼、一句效果；武器、防具、坐騎多一條還剩幾成（鋒利、耐久、飽足）；
  // 裝備庫裡同一欄還有幾件。空的那一格虛線框，寫空著的那一句與哪裡拿得到。點了開那一欄的抽屜（hero-node，同人像四角）
  function gearEffect(slot, w) {
    if (slot === "weapon") return w.bonus ? `威力 ${w.bonus}` : "用不上你身上的武學";
    if (slot === "armor") return `一場少扣 ${w.cut} 氣血${w.fit ? `・${w.fit}` : ""}`;
    if (slot === "mount") return `疾行省 ${w.save} 體力・路上快 ${w.speed}`;
    return w.effect_text || "";
  }
  function gearCell(g) {
    const w = g.worn, label = g.label || HERO_GEAR_NAMES[g.slot];
    // 傳承（玉璽碎片的抄本，寶物那一欄）：沒帶寶物時那一格寫它；帶著寶物時底下多一行
    const heir = g.heirloom ? `<small class="gc-more">傳承【${esc(g.heirloom.name)}】</small>` : "";
    const more = (g.rack.length ? `<small class="gc-more">裝備庫還有 ${g.rack.length} 件</small>` : "") + (w ? heir : "");
    const icon = `<svg viewBox="0 0 24 24" aria-hidden="true">${GEAR_ICONS[g.slot] || ""}</svg>`;
    if (!w && g.heirloom) {
      return `<button class="gear-cell ${esc(g.slot)}" data-act="hero-node" data-kind="gear" data-key="${esc(g.slot)}" aria-label="${esc(label)}：${esc(g.heirloom.name)}">
        <span class="gc-hd"><svg viewBox="0 0 24 24" aria-hidden="true">${GEAR_ICONS[g.slot] || ""}</svg><em>${esc(label)}</em><small>傳承</small></span><b class="gc-name">【${esc(g.heirloom.name)}】</b><small class="gc-fx">${esc(g.heirloom.effect_text || "")}</small>${more}</button>`;
    }
    if (!w) {
      return `<button class="gear-cell empty" data-act="hero-node" data-kind="gear" data-key="${esc(g.slot)}" aria-label="${esc(label)}：空著">
        <span class="gc-hd">${icon}<em>${esc(label)}</em></span><b class="gc-name">空著</b><small class="gc-fx">${esc(g.where || g.empty || "")}</small>${more}</button>`;
    }
    const edge = g.slot === "treasure" ? "" : `<span class="gc-edge" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${w.edge | 0}" aria-label="${esc(w.wear_word || "鋒利度")}"><i style="width:${Math.max(0, Math.min(100, w.edge | 0))}%"></i></span><small class="gc-edgen">${esc(w.wear_word || "鋒利度")} ${w.edge | 0}</small>`;
    const off = g.slot === "weapon" && !w.bonus;
    return `<button class="gear-cell ${esc(g.slot)}${off ? " off" : ""}" data-act="hero-node" data-kind="gear" data-key="${esc(g.slot)}" aria-label="${esc(label)}：${esc(w.name)}">
        <span class="gc-hd">${icon}<em>${esc(label)}</em>${w.grade ? `<small>${esc(w.grade)}</small>` : ""}</span><b class="gc-name">【${esc(w.name)}】</b><small class="gc-fx">${esc(gearEffect(g.slot, w))}</small>${edge}${more}</button>`;
  }

  // ── 馬市（第三節）：一排馬廄（你騎的、待售、裝備庫裡的），點一匹看牠的卡；卡上那一顆送現在的選項 id
  // （market:feed、market:buy、market:wield:<id>）。字待 joy 潤 ──
  // 馬的圖（Joy 2026-10-17 要真的水墨畫，圖另外產）：伺服器列出 web/ 裡真的有的鍵（main.horse_art），有圖放圖，沒有回空字串、照舊畫色塊
  function horseImg(key, cls) {
    return key && ((S.main && S.main.horse_art) || []).includes(key)
      ? `<img class="${cls}" src="/static/horse-${encodeURIComponent(key)}.webp" alt="" loading="lazy">` : "";
  }
  function marketHtml(shop) {
    const live = shop.stalls.filter((h) => !h.empty);
    const pick = live.find((h) => h.id === S.shopHorse) || live.find((h) => h.id === shop.focus) || live[0];
    const stall = (h) => (h.empty
      ? `<div class="stall empty"><span class="who">${esc(h.who)}</span><i class="horse"></i><b>${esc(h.name)}</b></div>`
      : `<button class="stall r-${esc(h.role)}${pick && h.id === pick.id ? " on" : ""}" data-act="shop-horse" data-id="${esc(h.id)}">
          <span class="who">${esc(h.who)}</span>${horseImg(h.art, "horse-pic") || `<i class="horse ${h.coat >= 0 ? `c${h.coat | 0}` : "cx"}"></i>`}<b>${esc(h.name)}</b><small>${dealHtml(h.sub)}</small></button>`);
    return `<div class="shop-body"><div class="shop-col"><div class="stalls${shop.stalls.length > 3 ? " many" : ""}">${shop.stalls.map(stall).join("")}</div>
      ${pick ? horseCard(pick) : ""}</div></div>`;
  }

  // 點著那一匹的卡：名字、階品、跟你騎的比、四項本事的長條、你騎的那匹多飽足長條；底下一顆照伺服器給的（做不了寫原因）
  function horseCard(h) {
    const width = (v) => Math.max(0, Math.min(100, v | 0));
    const bars = h.bars.map((b) => `<div class="abil"><span class="l">${esc(b.label)}</span><span class="v"><i style="width:${width(b.value)}%"></i></span><span class="n">${esc(b.text)}</span></div>`).join("");
    const fed = h.fed ? `<div class="fed"><span class="l">${esc(h.fed.word)} ${h.fed.value | 0}</span><span class="v"><i style="width:${width(h.fed.value)}%"></i></span>${h.fed.note ? `<small>${esc(h.fed.note)}</small>` : ""}</div>` : "";
    const a = h.action;
    const sub = a.enabled ? a.use : a.why;
    return `<article class="horse-card">${horseImg(h.art, "horse-big")}<h4>${esc(h.name)} <small>${esc(h.grade)}</small></h4>
        ${h.compare ? `<p class="cmp">${esc(h.compare)}</p>` : ""}<div class="bars">${bars}</div>${fed}
        <button class="btn primary horse-act" data-act="choose" data-id="${esc(a.id)}" ${a.enabled ? "" : "disabled"}><b>${esc(a.label)}</b>${sub ? `<small>${esc(sub)}</small>` : ""}</button>
      </article>`;
  }
  async function gearClick(act, el, ev) {
    switch (act) {
        case "shop-horse": S.shopHorse = el.dataset.id; renderShop(); break; // 馬市點一匹（第三節）：只換底下那張卡
    } // gearClick
  } // gearClick
  registerClicks(gearClick, ["shop-horse"]);
