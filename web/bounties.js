/* 天下大勢的網頁前端：懸賞榜（功能包 tianxia/features/bounties/，開發規範手冊 3.7、G9）。
 *
 * 懸賞榜（boardHtml）：手上揭著的格子、木板上的告示（paperHtml）、放大一張紙、揭下、放棄、交差蓋朱印的畫法。
 * 跟 mall.js 一樣是一般的 <script>：頂層的名字同在一個全域裡；/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 * 全部拆包第 65 批從 app.js 逐行切出來（計畫 docs/superpowers/plans/2026-11-06-網頁殼化-第65批.md）。點擊分派的 case、店面的框（shopHtml、renderShop）照舊在 app.js（殼）。
 */
"use strict";

  // ── 懸賞榜（第四節）：上面一排手上揭著的格子，木板上釘告示（顏色分種類：討伐紅、打探藍、護送綠、求兵金邊、通緝黑；
  // 揭了的蓋「已揭」），點一張放大成一張紙。揭下、交出…送現在的選項 id；放棄先問一次（shop-ask）。字待 joy 潤 ──
  function boardHtml(shop) {
    const zoomId = shop.picked || S.boardZoom; // 第三層開著（伺服器的 picked）：放大的一定是那一張
    const zoom = zoomId ? shop.notes.find((n) => n.id === zoomId) : null; // 被拿走了的告示跟著收
    const held = shop.held;
    const slots = held.rows.map((r) => `<button class="slot" data-act="board-zoom" data-id="${esc(r.id)}"><b>${esc(r.title)}</b><small>${esc(r.due)}</small></button>`).join("")
      + (held.left ? `<div class="slot empty">${esc(held.left_text)}</div>` : "");
    // 告示照草圖寫得很短（企劃者 2026-10-14 微調）：種類・哪一方（色塊小標籤）、目標、期限與名額，重賞、你有幾件合用各一個小字；
    // 要做什麼與賞寫在點開的紙上。期限名額寫短的（n.short，「期限 第 6 週・剩 2」，不折行）；完整的時刻與「名額還剩 N」在紙上（FB-196）
    // 21 天季：告示右上角一個小朱印寫銀兩（n.corner，第 5 批畫面第三組丙）
    // 21 天季（草圖丙，FB-391）：附贈與重賞一格一格（.extra，只排一行，放不下時重賞那一格藏起來，只留朱印與附贈）
    const extra = (n) => (n.gift || n.prize_chip
      ? `<span class="extra">${n.gift ? `<span class="gift">${esc(n.gift)}</span>` : ""}${n.prize_chip ? `<span class="prize">${esc(n.prize_chip)}</span>` : ""}</span>`
      : "");
    const face = (n) => `<span class="tag">${esc(n.kind_name)}・${esc(n.issuer)}</span>${n.corner ? `<i class="corner">${esc(n.corner)}</i>` : ""}<b>${esc(n.head)}</b>
        ${n.corner ? extra(n) : n.prize ? `<small class="prize">${esc(n.prize)}</small>` : ""}${n.have ? `<small class="prize">${esc(n.have)}</small>` : ""}
        <small class="due">${esc(n.short)}</small>`;
    const note = (n) => (n.done
      ? `<div class="note k-${esc(n.kind)} done">${face(n)}<i class="stamp">交差</i></div>`
      : `<button class="note k-${esc(n.kind)}${n.held ? " held" : ""}${!n.held && !n.action.enabled ? " dim" : ""}" data-act="board-zoom" data-id="${esc(n.id)}">
        ${face(n)}${n.held ? '<i class="stamp">已揭</i>' : ""}</button>`);
    // 剛交差的那一張（boardHanded）：伺服器那一份已經沒有它，照原本的位置再畫一下、蓋「交差」，跟著淡出（企劃者 2026-10-14 微調）
    const notes = shop.notes.slice();
    const done = S.boardStamp && !notes.some((n) => n.id === S.boardStamp.id) ? S.boardStamp : null;
    if (done) notes.splice(Math.min(done.at, notes.length), 0, { ...done.note, done: true });
    const board = notes.length ? `<div class="board">${notes.map(note).join("")}</div>` : `<p class="shop-empty board-empty">${esc(shop.empty)}</p>`;
    return `<div class="shop-body${zoom ? " zooming" : ""}"><div class="shop-col"><div class="held-row"><p>${esc(held.head)}</p><div class="slots">${slots}</div></div>${board}</div></div>
      ${zoom ? paperHtml(zoom, shop) : ""}`;
  }

  // 放大的那一張紙：完整的要求、賞、期限與名額，底下的鈕照那一張（第三層開著：合用的東西一件一顆，每顆照選單上的 confirm 先問一次）
  function paperHtml(n, shop) {
    const a = n.action;
    let btns;
    if (shop.picked === n.id) {
      btns = `<div class="hand-in">${shop.hand_in.map((o) => `<button class="btn${o.enabled ? "" : " ghost"}" data-act="choose" data-id="${esc(o.id)}" ${o.enabled ? "" : "disabled"}>${esc(o.label)}</button>`).join("")}</div>
        <div class="btns one"><button class="btn" data-act="board-close">收起</button></div>`;
    } else if (a.verb === "drop") {
      btns = `<div class="btns"><button class="btn danger" data-act="shop-ask" data-id="${esc(a.id)}" data-confirm="${esc(a.confirm)}" data-yes="放棄">放棄</button><button class="btn" data-act="board-close">收起</button></div>`;
    } else {
      btns = `${a.why ? `<p class="why">${esc(a.why)}</p>` : ""}<div class="btns"><button class="btn primary" data-act="choose" data-id="${esc(a.id)}" ${a.enabled ? "" : "disabled"}>${a.verb === "pick" ? "交出…" : "揭下"}</button><button class="btn" data-act="board-close">放回去</button></div>`;
    }
    // 紙貼在畫面下緣（企劃者 2026-10-14 微調，草圖那樣），不蓋住木板與招牌；紙太長（第三層交出清單）自己捲
    return `<div class="board-sheet"><article class="paper k-${esc(n.kind)}">${n.held ? '<i class="stamp">已揭</i>' : ""}
        <span class="tag">${esc(n.kind_name)}・${esc(n.issuer)}掛的</span><h4>${esc(n.title)}</h4>
        <p>${esc(n.how)}</p>${n.have ? `<p class="have">${esc(n.have)}</p>` : ""}${n.tags ? rewardChips(n.tags) : `<p class="reward">賞：${esc(n.reward)}</p>`}
        <p class="due">${n.level ? `${esc(n.level)}・` : ""}${esc(n.due)}</p>
        ${btns}</article></div>`;
  }

  // 第三層（替一張求兵挑東西）開著時選單上只有那一張的交出鈕與「回到懸賞榜」：放大別張、收起、出店之前先送 bounty:unpick
  // （不然按下去會被 Game.choose 擋成「榜上的情形變了」）
  async function boardUnpick(el) {
    const shop = S.main && S.main.shop;
    if (shop && shop.shop === "board" && shop.picked) await choose(el, shop.unpick);
  }
  async function boardZoom(el, id) {
    const shop = S.main && S.main.shop;
    if (shop && shop.picked && shop.picked !== id) await boardUnpick(el);
    S.boardZoom = id;
    renderShop();
  }
  async function boardClose(el) {
    S.boardZoom = null;
    await boardUnpick(el);
    renderShop();
  }
  async function boardLeave(el) {
    await boardUnpick(el);
    const shop = S.main && S.main.shop;
    if (shop && shop.shop === "board") await choose(el, shop.back);
  }
  // 交差之後（第四節；企劃者 2026-10-14 微調）：送了 bounty:give:<懸賞>:…、回來的木板上沒有那一張了（自己交過的不再列），
  // 那張告示照原本的位置再畫一下、本身蓋「交差」，停一下跟著淡出（減少動態效果的人不淡出，時間到直接拿掉）。被拒絕的（那一張還在）不蓋
  const STAMP_MS = 1400;
  function boardHanded(id, before) {
    const shop = S.main && S.main.shop;
    const bid = id.split(":")[2];
    const at = before && before.shop === "board" ? before.notes.findIndex((n) => n.id === bid) : -1;
    if (at < 0 || !shop || shop.shop !== "board" || shop.notes.some((n) => n.id === bid)) return;
    S.boardStamp = { id: bid, note: before.notes[at], at };
    S.boardZoom = null;
    renderShop();
    setTimeout(() => {
      if (!S.boardStamp || S.boardStamp.id !== bid) return;
      S.boardStamp = null;
      if (S.main && S.main.shop) renderShop();
    }, STAMP_MS);
  }

  // 手上揭了的懸賞，加上身上有合用兵器的求兵（status.bounties，bounties.status；後者多一行 have）：一張一行，怎麼交差、賞什麼。懸賞榜在城鎮才看得到，
  // 選單上有 act:bounties 時卡底下一顆「看懸賞榜」（就是那個選項，按了走 choose），不在城鎮寫一句去哪裡看。
  // 預設展開，收起來的狀態照手上那幾張記住（S.bountyShut）：揭了新的、交了差，清單變了就重新展開
  // 21 天季的賞拆成小籤（企劃者挑第 5 批畫面第三組丙；bounties.reward_tags）：一樣一格，附的那一樣金框、重賞紅框。字與數字照伺服器給的
  function rewardChips(tags) {
    return `<div class="rtags">${tags.map((t) => `<span class="rtag${t.kind ? ` ${esc(t.kind)}` : ""}">${t.k ? `<em>${esc(t.k)}</em>` : ""}${esc(t.v)}</span>`).join("")}</div>`;
  }

  function bountiesHtml(list, options) {
    const key = list.map((b) => b.id).join(",");
    const board = (options || []).find((o) => o.id === "act:bounties");
    const level = (list.find((b) => b.level) || {}).level; // 21 天季：「賞照你第 N 級」寫在卡頭
    const rows = list.map((b) => `
      <div class="order">
        <div class="order-head"><b>${esc(b.title)}</b><span>${esc(b.issuer)}</span></div>
        <div class="order-how">${esc(b.how)}</div>
        ${b.tags ? `<div class="order-meta">${rewardChips(b.tags)}</div>` : `<div class="order-meta">${esc(b.reward)}</div>`}
        ${b.due ? `<div class="order-meta">${esc(b.due)}</div>` : ""}
        ${b.have ? `<div class="order-meta">${esc(b.have)}</div>` : ""}
      </div>`).join("");
    // 懸賞榜正開著（第二層「返回」或第三層「回到懸賞榜」，選單就是榜）：卡底下不再寫什麼
    const open = (options || []).some((o) => o.id === "bounty:back" || o.id === "bounty:unpick");
    const foot = open ? "" : board
      ? `<button class="btn small" data-act="choose" data-id="act:bounties" ${board.enabled ? "" : "disabled"}>看懸賞榜</button>`
      : '<div class="order-meta">到城鎮的懸賞榜前，可以揭新的、放棄，或交出合用的兵器。</div>';  // 待 joy 潤（2026-10-21 拿掉求藝：不再寫「功夫」）
    return `<details class="fold bounties" data-key="${esc(key)}" ${S.bountyShut === key ? "" : "open"}>
      <summary>🪧 懸賞（${list.length}）${level ? `<span class="order-level">${esc(level)}</span>` : ""}</summary><div class="fold-body">${rows}${foot ? `<div class="bounty-foot">${foot}</div>` : ""}</div></details>`;
  }
  async function bountiesClick(act, el, ev) {
    switch (act) {
        case "board-zoom": await boardZoom(el, el.dataset.id); break; // 懸賞榜點一張告示（第四節）：放大成一張紙
        case "board-close": await boardClose(el); break; // 放回去、收起
    } // bountiesClick
  } // bountiesClick
  registerClicks(bountiesClick, ["board-zoom", "board-close"]);
