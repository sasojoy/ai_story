/* 天下大勢的網頁前端：結義（俠客頁同伴那一頁；tianxia/features/jieyi）。
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
  const JY_BOOK = "金蘭譜";
  // 金蘭譜（Joy 2026-11-09「新設計的頁面也都太陽春」→ 照介面設計規範重畫）：朱紅帖面、金邊，義名楷書大字；
  // 兄弟一人一枚直排的名帖、頂上一枚排行印；義譜收著，點了才攤；割袍斷義放最底下、要確認一次
  function jieyiHtml(m) {
    const j = m && m.jieyi;
    if (!j) return "";
    if (!j.name) return `<section class="jieyi jy-cool" aria-label="${JY_HEAD}"><span class="jy-cut" aria-hidden="true">斷</span><p>${esc(j.cooling || "")}</p></section>`;
    const tile = (x) => `<li class="jy-man${x.me ? " me" : ""}"><span class="jy-rank">${esc(x.rank)}</span><b>${esc(x.name)}</b>${x.me ? `<small>${JY_ME}</small>` : ""}</li>`;
    const open = !!S.jyLog;
    const log = j.log.length ? `<button class="jy-logbtn" data-act="jy-log" aria-expanded="${open}">${JY_LOG}<small>${j.log.length} 則</small><span aria-hidden="true">${open ? "▴" : "▾"}</span></button>
      ${open ? `<ol class="jy-log">${j.log.map((l) => `<li>${esc(l)}</li>`).join("")}</ol>` : ""}` : "";
    return `<section class="jieyi" aria-label="${JY_HEAD}"><div class="jy-paper">
      <div class="jy-hd"><small>${JY_BOOK}</small><h3>${esc(j.name)}</h3><span class="jy-me-rank">${JY_RANK.replace("{rank}", esc(j.rank))}</span></div>
      <ol class="jy-men">${j.members.map(tile).join("")}</ol></div>
      ${log}<button class="btn ghost jy-leave" data-act="jy-leave" data-confirm="${esc(j.leave_confirm)}">${JY_LEAVE}</button></section>`;
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
        case "jy-log": { const go = () => { S.jyLog = !S.jyLog; renderPage(); }; typeof heroStay === "function" ? heroStay(go) : go(); break; } // 不跳頂
    } // jieyiClick
  } // jieyiClick
  registerClicks(jieyiClick, ["jy-leave", "jy-log"]);
