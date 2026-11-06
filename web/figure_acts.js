/* 天下大勢的網頁前端：人物的盤算與此地舊事（全部拆包第 67 批從 main.js 切出來）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 */
"use strict";

  // 人物的盤算（世界活起來，main.plan）：全服開著的盤算裡最切身的一件，行動列底下一張卡。誰打算做什麼、在哪、什麼時候見分曉、
  // 兩邊各幾人；人在那裡就有「助一臂」「壞他的事」（就是選單上的 plan: 選項，按了走 choose），不在那裡寫走過去幾分鐘、一顆去輿圖。字都是伺服器寫好的
  function planHtml(x) {
    if (!x) return "";
    const far = x.minutes ? `步行約 ${x.minutes} 分鐘` : x.minutes === 0 ? "就在這裡" : "";
    const mine = x.mine === "help" ? "你已經出過力了" : x.mine === "block" ? "你已經出過手了" : "";
    const acts = x.acts && x.acts.length
      ? x.acts.map((a) => `<button class="btn small${a.id.includes(":help:") ? " primary" : ""}" data-act="choose" data-id="${esc(a.id)}">${esc(a.label)}</button>`).join("")
      : !mine && x.minutes && shown("tab:map") ? `<button class="btn small" data-act="tab" data-tab="map"${gotoAttrs(x.location)}>去${esc(x.place)} ›</button>` : "";
    return `<section class="card plan-card"><div class="plan-k">${esc(x.head)}</div>
      <p class="plan-text">${esc(x.text)}</p>
      <div class="plan-meta"><span>${esc(x.place)}${far ? `・${esc(far)}` : ""}</span><span>${esc(x.when)} 見分曉</span></div>
      <div class="plan-meta"><span>助${esc(x.help_side)}一方 ${x.help | 0} 人</span><span>壞事 ${x.block | 0} 人</span></div>
      ${mine ? `<div class="plan-mine">${esc(mine)}</div>` : ""}${acts ? `<div class="row">${acts}</div>` : ""}</section>`;
  }

  // 此地舊事（世界活起來，main.place_deeds）：這裡最近的幾筆世界記事，一行一筆
  function placeDeedsHtml(list) {
    if (!list || !list.length) return "";
    return `<section class="card place-deeds"><div class="pd-k">此地舊事</div>${list.map((d) =>
      `<p><span class="pd-when">${esc(d.when)}</span>${esc(d.text)}</p>`).join("")}</section>`;
  }
