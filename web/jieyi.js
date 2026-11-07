/* 天下大勢的網頁前端：結義（俠客頁門下那一段；tianxia/features/jieyi）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 * 伺服器有結義（或剛割袍斷義還在冷卻）才給 main.jieyi；沒有就不畫。邀人在玩家卡上、回話在此地還能做，這裡只看名冊、義譜與割袍斷義。
 */
"use strict";

  // 待 joy 潤：這一段的字
  const JY_HEAD = "結義";
  const JY_RANK = "排行第{rank}";
  const JY_LOG = "義譜";
  const JY_LEAVE = "割袍斷義";
  const JY_ME = "你";
  function jieyiHtml(m) {
    const j = m && m.jieyi;
    if (!j) return "";
    if (!j.name) return `<section class="self-sec jieyi" aria-label="${JY_HEAD}"><div class="self-hd"><h3>${JY_HEAD}</h3></div><p class="muted">${esc(j.cooling || "")}</p></section>`;
    const rows = j.members.map((x) => `<li class="${x.me ? "me" : ""}"><span class="jy-rank">${esc(x.rank)}</span><b>${esc(x.name)}</b>${x.me ? `<small>${JY_ME}</small>` : ""}</li>`).join("");
    const log = j.log.length ? `<details class="jy-log"><summary>${JY_LOG}</summary><ul>${j.log.map((l) => `<li>${esc(l)}</li>`).join("")}</ul></details>` : "";
    return `<section class="self-sec jieyi" aria-label="${JY_HEAD}"><div class="self-hd"><h3>${JY_HEAD}・${esc(j.name)}</h3><small class="muted">${JY_RANK.replace("{rank}", esc(j.rank))}</small></div>
      <ol class="jy-members">${rows}</ol>${log}
      <button class="btn ghost small jy-leave" data-act="jy-leave" data-confirm="${esc(j.leave_confirm)}">${JY_LEAVE}</button></section>`;
  }
  // 有人邀你結義（江湖頁場景卡底下一張；main.js 的介面重整版面叫它）：選單上的 jieyi:yes / jieyi:no 兩兩一對，一位一行，按了照舊送 choose
  const JY_OFFER_HEAD = "結義之邀";
  function jieyiOfferHtml(m) {
    const opts = ((m && m.options) || []).filter((o) => /^jieyi:yes:/.test(o.id));
    if (!opts.length) return "";
    const row = (o) => {
      const no = (m.options || []).find((x) => x.id === o.id.replace(/^jieyi:yes:/, "jieyi:no:"));
      return `<div class="jy-offer-row"><span>${esc(o.label.replace(/：[^：]*$/, ""))}</span><span class="jy-offer-btns"><button class="btn small primary" data-act="choose" data-id="${esc(o.id)}">答應</button>`
        + `${no ? `<button class="btn small ghost" data-act="choose" data-id="${esc(no.id)}">婉拒</button>` : ""}</span></div>`;
    };
    return `<section class="card jy-offer" aria-label="${JY_OFFER_HEAD}"><h3>${JY_OFFER_HEAD}</h3>${opts.map(row).join("")}</section>`;
  }
  async function jieyiClick(act, el, ev) {
    switch (act) {
        case "jy-leave": ask(el.dataset.confirm, JY_LEAVE, () => doMain("jieyi_leave")); break;
    } // jieyiClick
  } // jieyiClick
  registerClicks(jieyiClick, ["jy-leave"]);
