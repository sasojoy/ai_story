/* 天下大勢的網頁前端：結義（俠客頁同伴那一頁；tianxia/features/jieyi）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 * 畫在見聞「名帖匣」裡（結義第一批：要先互換名帖才能結義，所以跟名帖放一起；以前在俠客頁同伴那一頁）。
 * 結義開關開著時伺服器給 main.jieyi：沒結義是 { empty }、剛割袍是 { cooling }、有結義是名冊、義譜、義聚那一格。
 * 邀人在玩家卡上、回話在江湖頁的「結義之邀」；義聚在此地可為，也在這張帖上。
 */
"use strict";

  // 待 joy 潤：這一段的字
  const JY_HEAD = "結義";
  const JY_RANK = "排行第{rank}";
  const JY_LOG = "義譜";
  const JY_LEAVE = "割袍斷義";
  const JY_ME = "你";
  const JY_BOOK = "金蘭譜";
  const JY_EMPTY_HEAD = "金蘭帖";
  const JY_GATHER = "義聚";
  const JY_GATHER_SUB = "{names}也在此・體力 +{n}";
  const JY_HELP = "結義的規矩";
  const JY_RULES = [
    "義不相殘：兄弟之間不能截殺，也不揭兄弟的通緝。",
    "替兄出頭：兄弟被截殺打輸，一天之內在同一個地方遇到兇手，他的卡上能替兄出頭，不看陣營、不看他剛被截過；打贏了把兄弟被奪的銀兩追回給他。",
    "義聚：兄弟同在一個地方，每人每天能義聚一次，回體力（在場越多人回越多）。",
    "並肩作戰：同一場決戰站同一方的兄弟每多一位出手，戰功多算一點，最多兩位。",
    "名分：玩家卡、名帖上寫義名與排行；開義、入義、割袍寫進江湖史與列傳。結了義換季也不散。",
  ];
  // 金蘭譜（Joy 2026-11-09「新設計的頁面也都太陽春」→ 照介面設計規範重畫）：朱紅帖面、金邊，義名楷書大字；
  // 兄弟一人一枚直排的名帖、頂上一枚排行印；義譜收著，點了才攤；割袍斷義放最底下、要確認一次
  function jyRules() {
    const open = !!S.jyHelp;
    return `<button class="jy-help" data-act="jy-help" aria-expanded="${open}"><span class="jy-q" aria-hidden="true">？</span>${JY_HELP}<span aria-hidden="true">${open ? "▴" : "▾"}</span></button>
      ${open ? `<ul class="jy-rules">${JY_RULES.map((t) => `<li>${t}</li>`).join("")}</ul>` : ""}`;
  }
  // 義聚：兄弟在此、今天還沒聚過是一顆主鈕（同此地可為那一顆，送 choose）；不行的時候一行小字
  function jyGather(g) {
    if (!g) return "";
    if (!g.ready) return `<p class="jy-gather-note">${JY_GATHER}・${esc(g.note)}</p>`;
    return `<button class="btn primary jy-gather" data-act="choose" data-id="jieyi:gather"><b>${JY_GATHER}</b><small>${esc(JY_GATHER_SUB.replace("{names}", g.mates.join("、")).replace("{n}", g.n))}</small></button>`;
  }
  function jieyiHtml(m) {
    const j = m && m.jieyi;
    if (!j) return "";
    if (j.empty) return `<section class="jieyi" aria-label="${JY_HEAD}"><div class="jy-blank"><span class="jy-blank-seal" aria-hidden="true">義</span><div><h4>${JY_EMPTY_HEAD}</h4><p>${esc(j.empty)}</p></div></div>${jyRules()}</section>`;
    if (!j.name) return `<section class="jieyi" aria-label="${JY_HEAD}"><div class="jy-cool"><span class="jy-cut" aria-hidden="true">斷</span><p>${esc(j.cooling || "")}</p></div>${jyRules()}</section>`;
    const tile = (x) => `<li class="jy-man${x.me ? " me" : ""}"><span class="jy-rank">${esc(x.rank)}</span><b>${esc(x.name)}</b>${x.me ? `<small>${JY_ME}</small>` : ""}</li>`;
    const open = !!S.jyLog;
    const log = j.log.length ? `<button class="jy-logbtn" data-act="jy-log" aria-expanded="${open}">${JY_LOG}<small>${j.log.length} 則</small><span aria-hidden="true">${open ? "▴" : "▾"}</span></button>
      ${open ? `<ol class="jy-log">${j.log.map((l) => `<li>${esc(l)}</li>`).join("")}</ol>` : ""}` : "";
    return `<section class="jieyi" aria-label="${JY_HEAD}"><div class="jy-paper">
      <div class="jy-hd"><small>${JY_BOOK}</small><h3>${esc(j.name)}</h3><span class="jy-me-rank">${JY_RANK.replace("{rank}", esc(j.rank))}</span></div>
      <ol class="jy-men">${j.members.map(tile).join("")}</ol></div>
      ${jyGather(j.gather)}${log}${jyRules()}<button class="btn ghost jy-leave" data-act="jy-leave" data-confirm="${esc(j.leave_confirm)}">${JY_LEAVE}</button></section>`;
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
        case "jy-help": { const go = () => { S.jyHelp = !S.jyHelp; renderPage(); }; typeof heroStay === "function" ? heroStay(go) : go(); break; }
    } // jieyiClick
  } // jieyiClick
  registerClicks(jieyiClick, ["jy-leave", "jy-log", "jy-help"]);
