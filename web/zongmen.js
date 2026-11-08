/* 天下大勢的網頁前端：師門武譜（俠客頁門下那一段；tianxia/features/zongmen）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 * 伺服器在你是哪一門的人時才給 main.zongmen；沒有就不畫。試練在山門前的此地還能做，這裡看譜、學式、獻式。
 */
"use strict";

  // 待 joy 潤：這一段的字
  const ZM_HEAD = "師門武譜";
  const ZM_EMPTY = "譜上還沒有門人獻的式。在外面悟出、合出的意境，可以回山門獻上來。";
  const ZM_WAIT = "等同門試練";
  const ZM_TRIED = "{n}／{need} 人試過";
  const ZM_MINE = "你獻的";
  const ZM_DONE = "你試過了";
  const ZM_LEARN = "學這一式";
  const ZM_LEARNED = "已學";
  const ZM_OFFER = "獻上武譜";
  const ZM_OFFER_HEAD = "獻式";
  const ZM_OFFER_NOTE = "獻上去自己那一份不少；同門試練夠了就入譜，刻上你的名字，換季也在。";
  const ZM_GATE = "回{place}才能獻式、學式、試練";
  const ZM_COST = "學一式心得 {learn}・試練一次心得 {trial}";
  function zongmenHtml(m) {
    const z = m && m.zongmen;
    if (!z) return "";
    const row = (e) => {
      const btn = e.learned ? `<span class="zm-tag">${ZM_LEARNED}</span>`
        : e.problem ? `<small class="muted">${esc(e.problem)}</small>`
        : `<button class="btn small primary" data-act="zm-learn" data-id="${esc(e.id)}">${ZM_LEARN}</button>`;
      return `<li class="zm-entry"><div class="zm-line"><span class="zm-num">第${esc(e.num)}式</span><b>【${esc(e.name)}】</b><small class="muted">屬${esc(e.attr)}</small></div>
        <div class="zm-fx">${esc(e.fx)}</div>${(e.effects || []).map((t) => `<div class="zm-desc muted">${esc(t)}</div>`).join("")}${e.note ? `<div class="zm-note muted">${esc(e.note)}</div>` : ""}
        <div class="zm-foot"><small class="zm-carve">${esc(e.carve)}</small>${btn}</div></li>`;
    };
    const wait = (w) => `<li class="zm-wait"><span><b>【${esc(w.name)}】</b><small class="muted">${esc(w.giver)}獻</small></span>
      <small>${ZM_TRIED.replace("{n}", w.tried).replace("{need}", w.need)}${w.mine ? `・${ZM_MINE}` : w.done ? `・${ZM_DONE}` : ""}</small></li>`;
    const list = z.entries.length ? `<ol class="zm-list">${z.entries.map(row).join("")}</ol>` : `<p class="muted">${ZM_EMPTY}</p>`;
    const waiting = z.waiting.length ? `<div class="zm-sub">${ZM_WAIT}</div><ul class="zm-waits">${z.waiting.map(wait).join("")}</ul>` : "";
    const offer = z.offers.length ? `<div class="zm-sub">${ZM_OFFER_HEAD}</div><p class="muted zm-small">${ZM_OFFER_NOTE}</p>
      <div class="zm-offer"><select id="zm-pick">${z.offers.map((o) => `<option value="${esc(o.id)}">${esc(o.name)}</option>`).join("")}</select>
      <button class="btn small" data-act="zm-offer">${ZM_OFFER}</button></div>` : "";
    const gate = z.gate ? ZM_COST.replace("{learn}", z.learn_xinde).replace("{trial}", z.trial_xinde) : ZM_GATE.replace("{place}", esc(z.place));
    return `<section class="self-sec zongmen" aria-label="${ZM_HEAD}"><div class="self-hd"><h3>${ZM_HEAD}</h3><small class="muted">${esc(z.sect)}</small></div>
      <p class="muted zm-small">${gate}</p>${list}${waiting}${offer}</section>`;
  }
  async function zongmenClick(act, el, ev) {
    switch (act) {
        case "zm-learn": doMain("zongmen_learn", { id: el.dataset.id }); break;
        case "zm-offer": { const pick = document.getElementById("zm-pick"); if (pick) doMain("zongmen_offer", { id: pick.value }); break; }
    } // zongmenClick
  } // zongmenClick
  registerClicks(zongmenClick, ["zm-learn", "zm-offer"]);
