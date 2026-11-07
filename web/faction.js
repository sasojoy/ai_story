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
  // 中間那一格：投靠了的人是這一回（章回卡的內容），沒投靠的人是兩顆投靠鈕（最近的投靠點、走多久；就在那裡直接按投靠）
  const FACTION_JOIN = "先投一方", FACTION_JOIN_NOTE = "，才有章回、軍令和戰功", FACTION_JOIN_BTN = "投{side}", FACTION_HERE = "就在這"; // 待 joy 潤
  function factionJoinHtml(m) {
    const sc = m.sides_card;
    if (!sc || sc.joined) return "";
    const btn = (c) => {
      const near = (c.join_at || []).slice().sort((a, b) => (a.minutes | 0) - (b.minutes | 0))[0];
      const sub = near ? `${esc(near.name)}・${near.minutes | 0 ? `${near.minutes | 0} 分` : FACTION_HERE}` : esc(c.where[0] || "");
      const here = near && !(near.minutes | 0) && (m.options || []).some((o) => o.id === `faction:${c.id}`);
      const act = here ? `data-act="choose" data-id="faction:${esc(c.id)}"` : `data-act="tab" data-tab="map"${gotoAttrs(near && near.location)}`;
      return `<button class="btn wk-join-btn side-${esc(c.id)}" ${act}>${FACTION_JOIN_BTN.replace("{side}", esc(c.name))}<small>${sub}</small></button>`;
    };
    const two = sc.cols.filter((c) => c.id === "guan" || c.id === "huang");
    return `<div class="wk-mid"><p class="ch-next"><b>${FACTION_JOIN}</b>${FACTION_JOIN_NOTE}</p><div class="wk-join">${two.map(btn).join("")}</div></div>`;
  }
  const FACTION_SIDE_BAR = "{verb}到 {bar} 就是「{title}」"; // 待 joy 潤
  function factionSidesSheetHtml(sc) {
    if (!sc) return "";
    const rows = SIDES_ROWS.filter(([k]) => sc.joined ? k !== "where" : true);
    const dl = (c) => `<dl>${rows.filter(([k]) => c[k] && c[k].length).map(([k, name]) => `<dt>${name}</dt><dd>${esc(Array.isArray(c[k]) ? c[k].join("、") : c[k])}</dd>`).join("")}</dl>`;
    return `<div class="sides">${sc.cols.map((c) => (!sc.joined || c.mine
      ? `<div class="side side-${esc(c.id)}${c.mine ? " mine" : ""}"><h4>${esc(c.name)}${c.mine ? "<small>你在這一方</small>" : ""}</h4>${dl(c)}</div>`
      : `<details class="side side-${esc(c.id)}"><summary><h4>${esc(c.name)}<small>${esc([c.now, c.bar ? FACTION_SIDE_BAR.replace("{verb}", c.id === "guan" ? "壓" : "推").replace("{bar}", c.bar).replace("{title}", c.bar_title || "") : ""].filter(Boolean).join("・"))}</small></h4></summary>${dl(c)}</details>`)).join("")}</div>`;
  }
  async function factionClick(act, el, ev) {
    switch (act) {
        case "sides-first": S.sidesOpen = !el.parentElement.open; break; // 摺疊照瀏覽器自己開合；記下來，輪詢重畫時照舊
    } // factionClick
  } // factionClick
  registerClicks(factionClick, ["sides-first"]);
