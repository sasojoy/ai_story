/* 天下大勢的網頁前端：三方卡的表與先投一方（全部拆包第 67 批從 main.js 切出來）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 */
"use strict";

  // 三方卡（整合設計 3.4）：每一方一欄（手機上一欄一塊、上下排），要做到／現在／贏了給／投靠在哪。自己那一方框起來
  const SIDES_ROWS = [["goal", "要做到"], ["now", "現在"], ["gives", "贏了給"], ["where", "投靠在哪"]];
  function sidesTableHtml(sc) {
    return `<div class="sides">${sc.cols.map((c) => `<div class="side side-${esc(c.id)}${c.mine ? " mine" : ""}"><h4>${esc(c.name)}${c.mine ? "<small>你在這一方</small>" : ""}</h4>`
      + `<dl>${SIDES_ROWS.filter(([k]) => c[k] && c[k].length).map(([k, name]) => `<dt>${name}</dt><dd>${esc(Array.isArray(c[k]) ? c[k].join("、") : c[k])}</dd>`).join("")}</dl></div>`).join("")}</div>`;
  }
  // 還沒投靠的人：江湖頁最上面就是三方卡，加一句「先投一方」（整合設計 3.4）。平常收成一行（兩方投靠在哪），點了攤開三欄；
  // 攤開整張會把行動列推出第一屏，所以預設收著。攤開記在 S.sidesOpen（輪詢重畫照它畫）
  const SIDES_FIRST = "先投一方", SIDES_FIRST_NOTE = "到那一方的地點按「投靠」。誰都不投也行，當個散人，接懸賞一樣闖得出名號。"; // 待 joy 潤
  function sidesFirstHtml(m) {
    const sc = m.sides_card;
    if (!sc || sc.joined || !shown("quest")) return "";
    const where = sc.cols.filter((c) => c.where.length).map((c) => `${esc(c.name)}在${esc(c.where[0])}`).join("、");
    return `<details class="card sides-first"${S.sidesOpen ? " open" : ""}><summary data-act="sides-first">${SIDES_FIRST}<small>${where}</small></summary>`
      + `<p class="sides-note">${SIDES_FIRST_NOTE}</p>${sidesTableHtml(sc)}</details>`;
  }
