/* 天下大勢的網頁前端：本週軍令那張卡（全部拆包第 67 批從 main.js 切出來）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 */
"use strict";

  // 第一季濃縮版的「本週軍令」（計畫 T6；伺服器只送自己陣營的，散人沒有）：預設展開，收起來的狀態照週次記住
  function ordersHtml(list, week, convoy) {
    const done = list.filter((o) => o.done).length;
    const cart = convoy ? `<div class="order-cart">🛒 ${esc(convoy)}</div>` : "";  // 押著的糧車（那一道沒了也照樣寫）
    const rows = list.map((o) => `
      <div class="order${o.done ? " done" : ""}">
        <div class="order-head"><b>${esc(o.title)}</b><span>${o.done ? "已達成" : `陣營 ${o.progress}／${o.quota}`}</span></div>
        <div class="order-text">${esc(o.text)}</div>
        ${o.how ? `<div class="order-how">${esc(o.how)}</div>` : ""}
        <div class="order-bar" role="meter" aria-valuemin="0" aria-valuemax="${o.quota}" aria-valuenow="${o.progress}" aria-label="${esc(o.title)}"><i style="width:${pct(o.progress, o.quota)}%"></i></div>
        <div class="order-meta">你做了 ${o.mine} 次・截止 ${esc(o.deadline)}</div>
      </div>`).join("");
    return `<details class="fold orders" data-week="${week}" ${S.ordersShut === week ? "" : "open"}>
      <summary>📜 ${wkWord("order_this", "本週")}軍令（${list.length}${done ? `，已達成 ${done}` : ""}）</summary><div class="fold-body">${cart}${rows}</div></details>`;
  }
