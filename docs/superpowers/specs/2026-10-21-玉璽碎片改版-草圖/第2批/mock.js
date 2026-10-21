// 注入在真的頁面上的原型（程式碼不動）：玉璽碎片第 2 批的入口三種畫法。資料一律讀伺服器真的給的 status.seal.act。
// 字待 joy 潤。class 用現有的（.wrow/.wbtns/.gear-bind、.shop-layer/.shop-row、.fold.here/.options、.ask-layer）。
window.__m = (() => {
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const M = { act: null };
  M.load = async () => {
    const r = await fetch("/api/main").then((x) => x.json());
    M.act = (r.main || r).status.seal.act;
    // 輪詢不再回來（不然注入的東西會被重畫掉）、轉場關掉（不拍到半透明）
    window.fetch = () => new Promise(() => {});
    document.head.insertAdjacentHTML("beforeend", "<style>*,*::before,*::after{transition:none!important;animation:none!important}</style>");
    return M.act;
  };
  const VERB = { yinjiang: "引來", chuanxi: "傳檄", shouxin: "收心" };
  const TITLE = { yinjiang: "指定一位大勢人物", chuanxi: "指定一條戰線", shouxin: "指定一位人物" };
  const label = (t) => `${t.name}${t.where ? `・${t.where}` : ""}`;
  M.confirm = (t, side) => M.act.confirm.replace("{target}", t ? t.name : "").replace("{side}", side || "");
  M.ask = (text) => {
    document.body.insertAdjacentHTML("beforeend", `
      <div class="ask-layer"><div class="ask-bg"></div>
        <div class="ask" role="alertdialog"><p id="ask-text">${esc(text)}</p>
          <div class="row"><button class="btn">取消</button><button class="btn danger">起用</button></div></div></div>`);
  };
  // 傳承那一列一顆鈕（甲、乙共用）
  M.rowButton = () => {
    const row = document.querySelector(".gear .wrow.heirloom");
    row.insertAdjacentHTML("beforeend", `<div class="wbtns"><button class="btn small primary" ${M.act.ok ? "" : "disabled"}>${esc(M.act.name)}・剩 ${M.act.left} 次</button></div>`);
    if (!M.act.ok) row.querySelector(".winfo").insertAdjacentHTML("beforeend", `<small class="rwhy">${esc(M.act.why)}</small>`);
    row.scrollIntoView({ block: "center" });
  };
  // 甲：列下展開一小塊（照神器的「以器配招」）：說明、下拉選單、「起用」
  M.inline = (pick) => {
    const row = document.querySelector(".gear .wrow.heirloom");
    const opts = M.act.targets.map((t) => `<option value="${esc(t.id)}"${t.why ? " disabled" : ""}${t.id === pick ? " selected" : ""}>${esc(label(t))}${t.why ? `（${esc(t.why)}）` : ""}</option>`).join("");
    const sides = M.act.sides.length ? `<div class="row"><select class="input">${M.act.sides.map((s) => `<option>這一次算${esc(s.name)}</option>`).join("")}</select></div>` : "";
    row.insertAdjacentHTML("afterend", `<div class="gear-bind seal-act">
      <small>${esc(M.act.text)}</small><small>${esc(M.act.rule)}</small>${sides}
      ${M.act.targets.length ? `<div class="row"><select class="input">${opts}</select><button class="btn small primary">起用</button></div>`
        : `<div class="row"><button class="btn small primary">起用</button></div>`}</div>`);
    row.scrollIntoView({ block: "center" });
  };
  // 乙：店面那一層（照酒肆、鐵匠鋪的框）：招牌、說明、一人一列、灰掉的寫原因
  M.drawer = (sidePick) => {
    const sides = M.act.sides.length ? `<div class="shop-pages">${M.act.sides.map((s, i) => `<button class="shop-page${s.id === sidePick ? " on" : ""}">這一次算${esc(s.name)}</button>`).join("")}</div>` : "";
    const rows = M.act.targets.map((t) => `<div class="shop-row"><div class="winfo"><b>${esc(t.name)}</b>${t.where ? `<span>此刻在${esc(t.where)}</span>` : ""}${t.why ? `<span>${esc(t.why)}</span>` : ""}</div>
      <div class="wbtns"><button class="btn small${t.why ? "" : " primary"}" ${t.why ? "disabled" : ""}>${VERB[M.act.kind] || "起用"}</button></div></div>`).join("");
    document.body.insertAdjacentHTML("beforeend", `<div class="shop-layer shop-tavern" role="dialog">
      <header class="shop-bar"><button class="shop-back">‹ 收起</button><span class="shop-sign">${esc(M.act.name)}</span><span class="shop-silver">剩 ${M.act.left} 次</span></header>
      <p class="shop-line">${esc(M.act.text)}</p>
      <div class="shop-body"><div class="shop-col">${sides}<p class="shop-cap">${esc(M.act.rule)}</p>
        ${M.act.targets.length ? `<h4 class="tav-h">${esc(TITLE[M.act.kind] || "")}</h4>${rows}` : `<button class="btn primary">起用${esc(M.act.name)}</button>`}</div></div></div>`);
  };
  // 丙：江湖頁的碎片卡裡（照「此地還能做」的摺疊）：一行說明、還剩幾次、摺疊裡一人一顆
  M.card = (open) => {
    const card = document.querySelector(".seal-card");
    const list = M.act.targets.map((t) => `<button class="btn" ${t.why ? "disabled" : ""}><span>${esc(VERB[M.act.kind] || "起用")}${esc(t.name)}${t.where ? `（${esc(t.where)}）` : ""}${t.why ? `・${esc(t.why)}` : ""}</span></button>`).join("");
    const sides = M.act.sides.length ? `<div class="seg">${M.act.sides.map((s, i) => `<button class="${i === 0 ? "on" : ""}">這一次算${esc(s.name)}</button>`).join("")}</div>` : "";
    card.insertAdjacentHTML("beforeend", `<div class="seal-act" style="border-top:1px solid var(--line);margin-top:10px;padding-top:10px">
      <p><b>獨門行動・${esc(M.act.name)}</b>　<span class="muted">這一季還能起用 ${M.act.left} 次</span></p>
      <p class="muted">${esc(M.act.text)}</p>${sides}
      ${M.act.targets.length ? `<details class="fold here"${open ? " open" : ""}><summary>${esc(TITLE[M.act.kind] || "")}（${M.act.targets.length} 位）</summary><div class="fold-body options">${list}</div></details>`
        : `<div class="options"><button class="btn"><span>起用${esc(M.act.name)}</span></button></div>`}</div>`);
    M.top(card);
  };
  // 把 el 的頂端捲到狀態列底下（狀態列約 210px 高）
  M.top = (el, below = 220) => {
    const top = el.getBoundingClientRect().top;
    (document.scrollingElement || document.documentElement).scrollBy(0, top - below);
  };
  return M;
})();
