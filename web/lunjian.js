/* 門派論劍（功能包 lunjian；Joy 2026-11-28「機制這樣可以 開始做」，門派論劍設計稿第三版）。
 *
 * 伺服器送 main.lunjian（拜了門的人才有；手上還有沒用完的賞也送）。畫兩樣：
 *   1. 江湖頁眼下的一件（lunjianEyeItem，web/jianghu.js 的 jhEyeItems 問）：「論劍」小印、這一週到哪一步、鈕「去看」
 *   2. 點開的那一層（lunjianSheetHtml，jianghu.js 的 jhSheetHtml 問 sheet "lunjian"）：頁首、這一週的三個時刻、報名鈕、
 *      對陣的兩排（先鋒、中堅、大將）、三場的勝負與戰報（收起來）、禮匣與素材、收起來的規矩
 * 按鈕全走殼的 choose（lunjian:sign、lunjian:claim:<素材>、lunjian:open、lunjian:open_top）；這一包只登記收放的那兩顆。
 */
"use strict";

  const LJ_SEAL = "論劍"; // 待 joy 潤：眼下那一件的小印
  const LJ_GO = "去看"; // 待 joy 潤
  const LJ_KIND = "門派論劍"; // 待 joy 潤：頁首的朱印
  const LJ_WEEK = "第 {n} 週"; // 待 joy 潤
  const LJ_SUB_SIGN = "{draw} 截止報名"; // 待 joy 潤
  const LJ_SUB_SIGNED = "你報了名，{draw}抽籤"; // 待 joy 潤
  const LJ_SUB_DRAWN = "對上{them}，{fight}開打"; // 待 joy 潤
  const LJ_SUB_WON = "{us}勝了{them}"; // 待 joy 潤
  const LJ_SUB_LOST = "{us}輸給了{them}"; // 待 joy 潤
  const LJ_SUB_TIE = "{us}與{them}打成平手"; // 待 joy 潤
  const LJ_SUB_LOOT = "有賞還沒拿"; // 待 joy 潤
  const LJ_STEPS = ["報名", "抽籤", "開打"]; // 待 joy 潤
  const LJ_UNTIL = "到 {draw}"; // 待 joy 潤：報名那一格的小字
  const LJ_SIGN = "替本門報名"; // 待 joy 潤
  const LJ_RESIGN = "換成此刻的身手"; // 待 joy 潤
  const LJ_SIGN_SUB = "分身照你此刻的身手；截止前隨時能換"; // 待 joy 潤
  const LJ_COUNT = "本門已有 {n} 人報名，取身手最高的 {seats} 位上台"; // 待 joy 潤
  const LJ_NOBODY = "本門還沒有人報名；沒人報名這一週就不出場"; // 待 joy 潤
  const LJ_CLOSED = "這一週報名截止了"; // 待 joy 潤
  const LJ_SEATS = ["先鋒", "中堅", "大將"]; // 待 joy 潤
  const LJ_ELDER = "補位"; // 待 joy 潤：師兄那一格的小字
  const LJ_ME = "你"; // 待 joy 潤
  const LJ_WON = "勝"; // 待 joy 潤：收場的大印
  const LJ_LOST = "負"; // 待 joy 潤
  const LJ_TIE = "和"; // 待 joy 潤
  const LJ_LINES = "看這一場"; // 待 joy 潤
  const LJ_LOOT = "論劍的賞"; // 待 joy 潤
  const LJ_PICK = "挑一份四階素材（還有 {n} 份）"; // 待 joy 潤
  const LJ_BOX = "開論劍禮匣"; // 待 joy 潤
  const LJ_TOP = "開上等論劍禮匣"; // 待 joy 潤
  const LJ_MOVES = "免費製作絕招動畫 {n} 次，畫坊接上之後就能用"; // 待 joy 潤
  const LJ_SEALED = "你戴著朱印「{t}」"; // 待 joy 潤
  const LJ_HELP = "門派論劍的規矩"; // 待 joy 潤
  const LJ_RULES = [ // 待 joy 潤
    "一週一場。拜了門就能替本門報名，最後一天晚上八點截止、抽籤，九點開打，全自動，分身對分身。",
    "每一門取身手最高的三位上台，照身手由弱到強排成先鋒、中堅、大將；不夠三位由本門師兄補上。沒人報名的門派這一週不出場。",
    "三場贏兩場的那一門勝；一勝一負一和看大將那一場。",
    "上台贏一場單挑，一份四階素材自己挑；門派贏了，上台的人各得一個論劍禮匣、戴朱印「論劍三傑」到下一場；三場全勝換上等禮匣。",
  ];

  const ljData = (m) => (m && m.lunjian) || null;
  const ljFill = (t, o) => String(t).replace(/\{(\w+)\}/g, (_, k) => (o[k] ?? ""));
  const ljLoot = (c) => !!(c.picks || c.boxes || c.top_boxes);

  // 江湖頁眼下的一件：能報名、抽過籤、打完了、有賞沒拿才排
  function lunjianEyeItem(m) {
    const c = ljData(m);
    if (!c) return null;
    const base = { seal: LJ_SEAL, title: `${LJ_KIND}・${ljFill(LJ_WEEK, { n: c.week })}`, btn: LJ_GO, attrs: 'data-act="jh-sheet" data-sheet="lunjian"' };
    if (ljLoot(c)) return { ...base, key: `lj:loot:${c.picks}:${c.boxes}:${c.top_boxes}`, sub: LJ_SUB_LOOT };
    const x = c.match;
    if (x && c.phase === "fought") {
      const t = x.won === "us" ? LJ_SUB_WON : x.won === "them" ? LJ_SUB_LOST : LJ_SUB_TIE;
      return { ...base, key: `lj:${c.week}:fought`, sub: ljFill(t, x) };
    }
    if (x && c.phase === "drawn") return { ...base, key: `lj:${c.week}:drawn`, sub: ljFill(LJ_SUB_DRAWN, { ...x, fight: c.fight }) };
    if (c.can_sign && !c.signed) return { ...base, key: `lj:${c.week}:sign`, sub: ljFill(LJ_SUB_SIGN, c) };
    return null;
  }

  function ljSteps(c) { // 三個時刻：報名、抽籤、開打（直接寫字，不畫小圓點）
    const at = [c.draw, c.draw, c.fight];
    const now = c.phase === "fought" ? 3 : c.phase === "drawn" ? 2 : 0;
    return `<ol class="lj-steps">${LJ_STEPS.map((s, i) => `<li class="${i < now ? "done" : i === now ? "now" : ""}"><b>${s}</b><small>${esc(i === 0 ? ljFill(LJ_UNTIL, c) : at[i])}</small></li>`).join("")}</ol>`;
  }

  function ljSignHtml(m, c) {
    if (c.phase !== "sign") return "";
    const o = ((m && m.options) || []).find((x) => x.id === "lunjian:sign");
    const count = c.count ? ljFill(LJ_COUNT, { n: c.count, seats: c.seats }) : LJ_NOBODY;
    const btn = o
      ? `<button class="btn lj-go" data-act="choose" data-id="lunjian:sign">${c.signed ? LJ_RESIGN : LJ_SIGN}<small>${LJ_SIGN_SUB}</small></button>`
      : `<button class="btn lj-go" disabled>${LJ_CLOSED}</button>`;
    return `<p class="lj-how">${esc(count)}</p>${btn}`;
  }

  function ljSeat(s, side) {
    if (!s) return `<span class="lj-seat empty"></span>`;
    const tag = s.me ? `<em class="me">${LJ_ME}</em>` : s.elder ? `<em>${LJ_ELDER}</em>` : "";
    return `<span class="lj-seat ${side}${s.me ? " me" : ""}"><b>${esc(s.name)}</b>${tag}</span>`;
  }

  function ljBoard(c) {
    const x = c.match;
    if (!x) return "";
    const rows = LJ_SEATS.map((name, i) => {
      const b = (x.bouts || [])[i];
      const mark = b ? `<span class="lj-tier t-${b.tier === "大勝" || b.tier === "險勝" ? "win" : b.tier === "落敗" ? "lose" : "tie"}">${esc(b.tier)}</span>` : `<span class="lj-tier"></span>`;
      const open = S.ljBout === i;
      const lines = b && open ? `<div class="lj-lines">${(b.lines || []).map((t) => `<p>${esc(t)}</p>`).join("")}</div>` : "";
      const more = b ? `<button class="lj-more" data-act="lj-bout" data-i="${i}" aria-expanded="${open}">${LJ_LINES}<i aria-hidden="true">${open ? "▴" : "▾"}</i></button>` : "";
      return `<li class="lj-row"><span class="lj-pos">${name}</span><div class="lj-vs">${ljSeat((x.seats_us || [])[i], "us")}${mark}${ljSeat((x.seats_them || [])[i], "them")}</div>${more}${lines}</li>`;
    }).join("");
    const end = c.phase === "fought" ? `<span class="lj-stamp">${x.won === "us" ? LJ_WON : x.won === "them" ? LJ_LOST : LJ_TIE}</span>` : "";
    return `<div class="lj-board"><div class="lj-sides"><b>${esc(x.us)}</b><span>${esc((x.score || []).join("　比　"))}</span><b>${esc(x.them)}</b>${end}</div><ol class="lj-rows">${rows}</ol></div>`;
  }

  function ljLootHtml(c) {
    const parts = [];
    if (c.seal) parts.push(`<p class="lj-sealed"><span class="lj-mark">${esc(c.seal)}</span>${esc(ljFill(LJ_SEALED, { t: c.seal }))}</p>`);
    if (c.top_boxes) parts.push(`<button class="btn lj-box top" data-act="choose" data-id="lunjian:open_top">${LJ_TOP}<small>×${c.top_boxes}</small></button>`);
    if (c.boxes) parts.push(`<button class="btn lj-box" data-act="choose" data-id="lunjian:open">${LJ_BOX}<small>×${c.boxes}</small></button>`);
    if (c.claim && c.claim.length) parts.push(`<div class="lj-claim"><b>${esc(ljFill(LJ_PICK, { n: c.picks }))}</b><div class="lj-ways">${c.claim.map((o) => `<button class="lj-way" data-act="choose" data-id="${esc(o.id)}">${esc(o.name)}</button>`).join("")}</div></div>`);
    if (c.moves) parts.push(`<p class="lj-how">${esc(ljFill(LJ_MOVES, { n: c.moves }))}</p>`);
    if (c.opened && c.opened.length) parts.push(`<div class="lj-told">${c.opened.slice(0, 3).map((t) => `<p>${esc(t)}</p>`).join("")}</div>`);
    return parts.length ? `<section class="lj-loot"><h4>${LJ_LOOT}</h4>${parts.join("")}</section>` : "";
  }

  function lunjianSheetHtml(m) {
    const c = ljData(m);
    if (!c) return "";
    const head = c.sect ? `${esc(c.sect)}・${esc(ljFill(LJ_WEEK, { n: c.week }))}` : esc(ljFill(LJ_WEEK, { n: c.week }));
    return `<div class="lj">
        <div class="lj-hero"><span class="lj-seal">${LJ_KIND}</span><p class="lj-where">${head}</p></div>
        ${c.sect ? ljSteps(c) : ""}
        ${ljSignHtml(m, c)}
        ${ljBoard(c)}
        ${ljLootHtml(c)}
        <button class="lj-help" data-act="lj-help" aria-expanded="${!!S.ljHelp}">？ ${LJ_HELP}<i aria-hidden="true">${S.ljHelp ? "▴" : "▾"}</i></button>
        ${S.ljHelp ? `<ul class="lj-rules">${LJ_RULES.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>` : ""}
      </div>`;
  }

  async function lunjianClick(act, el, ev) {
    switch (act) {
        case "lj-help": S.ljHelp = !S.ljHelp; renderPage(); break;
        case "lj-bout": { const i = Number(el.dataset.i); S.ljBout = S.ljBout === i ? null : i; renderPage(); break; }
    } // lunjianClick
  } // lunjianClick
  registerClicks(lunjianClick, ["lj-help", "lj-bout"]);
