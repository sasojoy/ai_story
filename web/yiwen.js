// 異聞（tianxia/features/yiwen）：撞見卡、每一幕、收尾卡（第 247 批：走得通的最小樣子；照對比圖細修是第 248 批）。
// 資料是 /api/main 的 main.yiwen.card（伺服器不先跳脫，玩家的原話一律經 esc() 才進 HTML）。
// 江湖頁沒有給包的格（殼不長）：卡畫在蓋在頁面上的一層（同 story.js 的跳顯框），頁面重畫時照 main.yiwen 補上或拿掉。
// 畫法集中在 yiwenCard、yiwenScene、yiwenClose 三個函式，下一批好換。
// 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡；script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
"use strict";

  const YW_MARK_FIRST = "異聞"; // 待 joy 潤
  const YW_MARK_TRAIL = "舊腳印"; // 待 joy 潤
  const YW_WALKERS = "已有 {n} 人走過"; // 待 joy 潤
  const YW_STEP = "第 {n} 步"; // 待 joy 潤
  const YW_WALKED = "{who}走過・足跡 {n}"; // 待 joy 潤
  const YW_FREE = "沒人走過・寫下你的路"; // 待 joy 潤
  const YW_TYPED_OFF = "自己說…（說書人還沒到）"; // 待 joy 潤
  const YW_DROP = "放下"; // 待 joy 潤
  const YW_CLOSE = "收起"; // 待 joy 潤
  const YW_DONE_LINE = "這一則已經記進異聞錄，往後撞見的人都踩得到你的腳印。"; // 待 joy 潤
  const YW_GAINS = "這一趟拿到的"; // 待 joy 潤

  function ywFill(text, slots) {
    return String(text).replace(/\{(\w+)\}/g, (m, k) => (k in slots ? String(slots[k]) : m));
  }

  // 一幕：朱批（發掘者那一步）或回聲、兩段字、順逆的圓章
  function yiwenScene(sc) {
    const head = sc.zhupi && sc.zhupi_text ? `<p class="yw-zhupi">${esc(sc.zhupi_text)}</p>` : sc.echo ? `<p class="yw-echo">${esc(sc.echo)}</p>` : "";
    const seal = sc.luck ? `<span class="yw-luck" aria-label="${esc(sc.luck)}">${esc(sc.luck)}</span>` : "";
    const body = (sc.text || []).map((t) => `<p class="yw-text">${esc(t)}</p>`).join("");
    return `<div class="yw-scene" data-node="${Number(sc.node) || 0}">${head}<div class="yw-scene-body">${seal}${body}</div></div>`;
  }

  // 收尾卡：收場句、這一趟拿到的（剛按完那一下的回話）、一顆收起
  function yiwenClose(card) {
    const gains = (S.ywLast || []).filter((t) => t && t !== card.close);
    return `<div class="yw-close"><p class="yw-close-line">${esc(card.close || "")}</p>
      ${gains.length ? `<p class="yw-gains-hd">${YW_GAINS}</p><ul class="yw-gains">${gains.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>` : ""}
      <p class="yw-note">${YW_DONE_LINE}</p>
      <button class="btn primary yw-btn" data-act="choose" data-id="yiwen:drop">${YW_CLOSE}</button></div>`;
  }

  function ywChoice(card, c) {
    const note = c.state === "walked" ? ywFill(YW_WALKED, { who: esc(c.by), n: Number(c.steps) || 0 })
      : c.state === "free" ? YW_FREE : esc(c.note || "");
    const off = c.state === "locked";
    return `<button class="yw-pick${off ? " off" : ""}" data-act="yw-step" data-i="${Number(c.i) || 0}"${off ? " disabled" : ""}>
      <span class="yw-pick-label">${esc(c.label)}</span><small class="yw-pick-note">${note}</small></button>`;
  }

  // 撞見卡：朱印、地點、一句懸念、已寫的幾幕、這一步的三顆
  function yiwenCard(card) {
    if (!card) return "";
    const trail = card.mark === "trail";
    const head = `<p class="yw-head"><span class="yw-seal">${trail ? YW_MARK_TRAIL : YW_MARK_FIRST}</span><b class="yw-place">${esc(card.place_name)}</b>
      ${trail ? `<small class="yw-walkers">${ywFill(YW_WALKERS, { n: Number(card.walkers) || 0 })}</small>` : ""}</p>`;
    const frame = card.frame ? `<p class="yw-frame">${esc(card.frame)}</p>` : "";
    const scenes = (card.scenes || []).map(yiwenScene).join("");
    const tail = card.done ? yiwenClose(card) : `<p class="yw-step">${ywFill(YW_STEP, { n: Number(card.depth) || 1 })}</p>
      <div class="yw-picks">${(card.choices || []).map((c) => ywChoice(card, c)).join("")}
      <button class="yw-pick off" disabled><span class="yw-pick-label">${YW_TYPED_OFF}</span></button></div>
      <button class="btn ghost yw-btn" data-act="choose" data-id="yiwen:drop">${YW_DROP}</button>`;
    return `<div class="yw-card" role="dialog" aria-label="${esc(card.title)}"><h3 class="yw-title">${esc(card.title)}</h3>${head}${frame}
      <p class="yw-hook">${esc(card.hook)}</p>${scenes}${tail}</div>`;
  }

  // 蓋在頁面上的那一層：照 main.yiwen.card 補上或拿掉（同一張卡不重畫，自己畫的不會再叫自己）
  function yiwenSync() {
    if (typeof document === "undefined" || !document.body) return;
    const card = S.stage === "game" && S.main && S.main.yiwen ? S.main.yiwen.card : null;
    let box = document.getElementById("yw-pop");
    if (!card) { if (box) box.remove(); S.ywSig = ""; return; }
    const sig = JSON.stringify(card) + JSON.stringify(S.ywLast || []);
    if (box && S.ywSig === sig) return;
    S.ywSig = sig;
    if (!box) { box = document.createElement("div"); box.id = "yw-pop"; box.className = "yw-wrap"; document.body.appendChild(box); }
    box.innerHTML = yiwenCard(card);
  }

  async function ywStep(el) { // 撞見卡上按一顆：打 /api/do/yiwen_step，回話留著給收尾卡寫「這一趟拿到的」，接著照新的 main 重畫
    const card = S.main && S.main.yiwen ? S.main.yiwen.card : null;
    if (!card) return;
    const body = { tale: card["tale"], opening: card.opening, node: card.node, pick: Number(el.dataset.i) || 0 }; // 寫成 ["tale"]：test_server 掃「點 tale」這種寫法（戰記的 class 名不准撞）
    try {
      const r = await api("/api/do/yiwen_step", body);
      S.ywLast = (r.message || "").replace(/<br\s*\/?>/g, "\n").replace(/<[^>]+>/g, "").split("\n").map((t) => t.trim()).filter(Boolean);
      applyMain(r.main);
    } catch (e) { /* 連線斷了：卡還在，再按一次 */ }
    yiwenSync();
  }

  if (typeof MutationObserver === "function" && typeof document !== "undefined" && document.body) {
    new MutationObserver(() => yiwenSync()).observe(document.body, { childList: true, subtree: true }); // 頁面重畫時補上或拿掉那一層（同一張卡不重畫，不會自己叫自己）
  }

  async function yiwenClick(act, el, ev) {
    switch (act) {
        case "yw-step": await ywStep(el); break;
    } // yiwenClick
  } // yiwenClick
  registerClicks(yiwenClick, ["yw-step"]);
