/* 天下大勢的網頁前端：銀兩出口（功能包 tianxia/features/outlets/，開發規範手冊 3.7、G9）。
 *
 * 軍需帳（donateHtml）與打點帳簿（dadianHtml）的畫法。
 * 跟 mall.js 一樣是一般的 <script>：頂層的名字同在一個全域裡；/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 * 全部拆包第 65 批從 app.js 逐行切出來（計畫 docs/superpowers/plans/2026-11-06-網頁殼化-第65批.md）。點擊用 registerClicks 登記在這支檔；店面的框（shopHtml、renderShop）照舊在 app.js（殼）。
 */
"use strict";

  // ── 軍需帳（素材與經濟設計第六節；企劃者 2026-10-15 選草圖 B3）：上面陣營四種軍備的存量、今天還能捐幾點，底下背包的素材一格一格
  // （同打造頁的素材格，照屬性一排、一階到三階）。點一格挑起來（預設今天收得下的全部）、挑好的列在底下可以＋−改個數，「捐出」一起送
  // （MAIN_ACTIONS donate 的 items，一則紀錄）。捐不了的格子灰掉寫原因。字待 joy 潤 ──
  function donatePicks(shop) {
    // 挑好的照現在的格子修：捐不了的、已經不在背包的拿掉，個數夾在今天收得下的以內
    const cells = new Map(shop.cells.map((c) => [c.id, c]));
    const out = {};
    for (const [id, n] of Object.entries(S.donatePick || {})) {
      const cell = cells.get(id);
      if (cell && !cell.problem && cell.take > 0) out[id] = Math.max(1, Math.min(n | 0, cell.take));
    }
    return out;
  }
  // ── 打點（21 天季的銀兩出口；企劃者挑第 9 批畫面乙：茶樓雅間的掮客，五樣記在一本攤開的帳簿上；shopview.dadian_view）──
  // 左頁「修為」、右頁「人情」。這裡做得了的一筆是一顆鈕，送原本的選項 id（choose）；做不了的墨線劃掉、朱筆批去哪做（或為什麼）。
  // 身上掛著還沒用掉的寫在帳底下。字與數字照伺服器給的
  function dadianHtml(shop) {
    const entry = (e) => {
      const head = `<b>${esc(e.name)}<em>${esc(e.price)}</em></b><span class="desc">${ledgerText(e.desc)}</span>`;
      return e.ok
        ? `<button class="entry" data-act="choose" data-id="${esc(e.id)}">${head}<span class="tick">${ledgerText(e.tick)}</span></button>`
        : `<div class="entry off">${head}<span class="note">${ledgerText(e.note)}</span></div>`;
    };
    const pages = shop.pages.map((p) => `<section class="ledger-page"><h3>${esc(p.head)}</h3>${p.entries.map(entry).join("")}</section>`).join("");
    return `<div class="shop-body"><div class="shop-col"><div class="ledger">${pages}</div>
      <div class="abacus" aria-hidden="true">${"<i></i>".repeat(9)}</div>
      ${shop.hang ? `<p class="ledger-hang">${esc(shop.hang)}</p>` : ""}</div></div>`;
  }

  function donateHtml(shop) {
    const picks = donatePicks(shop);
    const cells = new Map(shop.cells.map((c) => [c.id, c]));
    const used = Object.entries(picks).reduce((sum, [id, n]) => sum + n * cells.get(id).points, 0);
    const tiles = shop.stock.map((a) => `<div class="arm-tile"><span>${esc(a.name)}</span><b>${a.points | 0}</b></div>`).join("");
    const fill = shop.cap ? Math.max(0, Math.min(100, (shop.room / shop.cap) * 100)) : 0;
    const rows = [];
    for (const c of shop.cells) {
      const cell = `<button class="cell t${c.tier | 0}${picks[c.id] ? " used" : ""}${c.problem ? " off" : ""}" data-act="dn-cell" data-id="${esc(c.id)}" data-why="${esc(c.problem || "")}">
        <span class="n">${c.have | 0}</span><span class="nm"><i class="dot ${SHOP_ATTR[c.attribute] || ""}"></i>${esc(c.name)}</span><small>${esc(c.tier_word)}・${c.points | 0} 點</small>${picks[c.id] ? `<span class="pick">捐 ${picks[c.id]}</span>` : ""}</button>`;
      const last = rows[rows.length - 1];
      if (last && last.attribute === c.attribute) last.cells.push(cell);
      else rows.push({ attribute: c.attribute, cells: [cell] });
    }
    const grid = rows.map((r) => `<div class="cell-row"><span class="row-attr ${SHOP_ATTR[r.attribute] || ""}">${esc(r.attribute)}</span>${r.cells.join("")}</div>`).join("");
    const picked = Object.entries(picks).map(([id, n]) => {
      const c = cells.get(id);
      return `<div class="dn-pick"><span>${esc(c.name)} ×${n}<small>${n * c.points} 點・${esc(c.armament)}</small></span>
        <span class="dn-step"><button class="btn small ghost" data-act="dn-step" data-id="${esc(id)}" data-d="-1" ${n > 1 ? "" : "disabled"} aria-label="少捐一個">−</button><button class="btn small ghost" data-act="dn-step" data-id="${esc(id)}" data-d="1" ${n < c.take && used + c.points <= shop.room ? "" : "disabled"} aria-label="多捐一個">＋</button></span></div>`;
    }).join("");
    const over = used > shop.room;
    const go = `<button class="btn primary shop-go" data-act="dn-go" ${used > 0 && !over ? "" : "disabled"}>${used > 0 ? `捐出 ${used} 點` : "點素材挑要捐的"}</button>`;
    const tierOne = shop.cells.some((c) => c.tier === 1 && !c.problem) ? '<button class="btn small ghost" data-act="dn-tier1">全選一階</button>' : "";
    // 格子上面的東西挑了之後高度不變（捐出鈕只換字）：挑好的與＋−排在格子底下，點一格不會把下一格擠走、手指點偏
    return `<div class="shop-body"><div class="shop-col">${shopNoteHtml(shop.hint)}
      <div class="arm-tiles">${tiles}</div>
      <div class="dn-room"><span>${esc(shop.room_text)}</span><i><b style="width:${fill.toFixed(1)}%"></b></i></div>
      <div class="shop-gorow">${go}${tierOne}</div>
      ${over ? `<p class="shop-warn">${esc(`今天只收得下 ${shop.room | 0} 點，少挑一些。`)}</p>` : ""}
      <p class="shop-cap">${esc(shop.caption)}</p>
      <div class="cells">${grid || `<p class="shop-empty">${esc(shop.empty)}</p>`}</div>
      ${picked ? `<p class="shop-cap">挑好要捐的（＋−改個數）</p><div class="dn-picks">${picked}</div>` : ""}</div></div>`;
  }
  // 點一格：灰掉的只說原因；挑過的放回去；沒挑過的挑起來，個數是今天收得下的（扣掉已經挑的點數）
  function donateCell(id, why) {
    if (why) { toast(why); return; }
    const shop = S.main && S.main.shop;
    if (!shop || shop.shop !== "donate") return;
    const picks = donatePicks(shop);
    if (picks[id]) { delete picks[id]; S.donatePick = picks; renderShop(); return; }
    const cell = shop.cells.find((c) => c.id === id);
    if (!cell) return;
    const used = Object.entries(picks).reduce((sum, [k, n]) => sum + n * shop.cells.find((c) => c.id === k).points, 0);
    const fit = Math.min(cell.take, Math.floor((shop.room - used) / cell.points));
    if (fit <= 0) { toast(`今天只剩 ${Math.max(0, shop.room - used)} 點收得下，${cell.name}一個就 ${cell.points} 點。`); return; }
    picks[id] = fit;
    S.donatePick = picks;
    renderShop();
  }
  function donateStep(id, d) {
    const shop = S.main && S.main.shop;
    if (!shop || shop.shop !== "donate") return;
    const picks = donatePicks(shop);
    if (!picks[id]) return;
    picks[id] = picks[id] + d; // 夾在 1～今天收得下的，下一次畫照 donatePicks 修
    S.donatePick = picks;
    renderShop();
  }
  // 全選一階：每一種捐得了的一階都挑起來，照今天剩的點數依序填滿
  function donateTierOne() {
    const shop = S.main && S.main.shop;
    if (!shop || shop.shop !== "donate") return;
    const picks = donatePicks(shop);
    let used = Object.entries(picks).reduce((sum, [k, n]) => sum + n * shop.cells.find((c) => c.id === k).points, 0);
    for (const c of shop.cells) {
      if (c.tier !== 1 || c.problem || picks[c.id]) continue;
      const fit = Math.min(c.take, Math.floor((shop.room - used) / c.points));
      if (fit <= 0) break;
      picks[c.id] = fit;
      used += fit * c.points;
    }
    S.donatePick = picks;
    renderShop();
  }
  async function donateGo() {
    const shop = S.main && S.main.shop;
    if (!shop || shop.shop !== "donate") return;
    const items = Object.entries(donatePicks(shop)).map(([material, count]) => ({ material, count }));
    if (!items.length) return;
    await shopDo("donate", { items }, () => { S.donatePick = {}; });
  }
  async function outletsClick(act, el, ev) {
    switch (act) {
        // 軍需帳（素材與經濟 B6）：挑一格、＋−個數、全選一階、捐出
        case "dn-cell": donateCell(el.dataset.id, el.dataset.why); break;
        case "dn-step": donateStep(el.dataset.id, Number(el.dataset.d)); break;
        case "dn-tier1": donateTierOne(); break;
        case "dn-go": await donateGo(); break;
    } // outletsClick
  } // outletsClick
  registerClicks(outletsClick, ["dn-cell", "dn-step", "dn-tier1", "dn-go"]);
