/* 門派論劍（功能包 lunjian；Joy 2026-11-28「機制這樣可以 開始做」，門派論劍設計稿第三版）。
 *
 * 伺服器送 main.lunjian（拜了門的人才有；手上還有沒用完的賞也送）。畫兩樣：
 *   1. 江湖頁眼下的一件（lunjianEyeItem，web/jianghu.js 的 jhEyeItems 問）：「論劍」小印、這一週到哪一步、鈕「去看」
 *   2. 點開的那一層（lunjianSheetHtml，jianghu.js 的 jhSheetHtml 問 sheet "lunjian"）：頁首、這一週的三個時刻、報名鈕、
 *      對陣的兩排（先鋒、中堅、大將）、三場的勝負與戰報（收起來）、禮匣與素材、收起來的規矩
 * 按鈕全走殼的 choose（lunjian:sign、lunjian:claim:<素材>、lunjian:open、lunjian:open_top、lunjian:preset:<n>、lunjian:swap:<i>）；
 * 自己寫的戰策是表單 lj-plan（送 /api/lunjian/plan）；這一包另登記收放的那兩顆。
 * 打法第四版（Joy 2026-11-28「可以」）：抽籤之後、開打之前，上了台的人定一句戰策（自己寫或挑老法子），帶隊的人排陣；
 * 對面三位看得到武學與最拿手的招，誰對上誰開打才知道。戰報先寫兩邊的戰策，再寫那一場的過程。
 */
"use strict";

  const LJ_SEAL = "論劍"; // 待 joy 潤：眼下那一件的小印
  const LJ_GO = "去看"; // 待 joy 潤
  const LJ_KIND = "門派論劍"; // 待 joy 潤：眼下那一件的標題
  const LJ_STAMP = "論劍"; // 待 joy 潤：頁首的朱印
  const LJ_WEEK = "第 {n} 週"; // 待 joy 潤
  const LJ_SUB_SIGN = "{draw} 截止報名"; // 待 joy 潤
  const LJ_SUB_SIGNED = "你報了名，{draw}抽籤"; // 待 joy 潤
  const LJ_SUB_DRAWN = "對上{them}，{fight}開打"; // 待 joy 潤
  const LJ_SUB_WON = "{us}勝了{them}"; // 待 joy 潤
  const LJ_SUB_LOST = "{us}輸給了{them}"; // 待 joy 潤
  const LJ_SUB_TIE = "{us}與{them}打成平手"; // 待 joy 潤
  const LJ_SUB_LOOT = "有賞還沒拿"; // 待 joy 潤
  const LJ_STEPS = ["報名", "抽籤", "開打"]; // 待 joy 潤
  const LJ_UNTIL = "{draw} 前"; // 待 joy 潤：報名那一格的小字
  const LJ_SIGN = "替本門報名"; // 待 joy 潤
  const LJ_RESIGN = "換成此刻的身手"; // 待 joy 潤
  const LJ_SIGNED = "你已經替本門報了名。"; // 待 joy 潤
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
  const LJ_SUB_PLAN = "抽好籤了，{fight}前定戰策"; // 待 joy 潤
  const LJ_PLAN = "你的戰策"; // 待 joy 潤
  const LJ_PLAN_SEAT = "你這一週當{seat}，{until} 前定好；對面看不到"; // 待 joy 潤
  const LJ_PLAN_NOW = "此刻定的是：{text}"; // 待 joy 潤
  const LJ_PLAN_NONE = "還沒定。不定也打，只是不佔這個便宜"; // 待 joy 潤
  const LJ_PLAN_PH = "寫一句，例如：以靜制動"; // 待 joy 潤
  const LJ_PLAN_GO = "定下"; // 待 joy 潤
  const LJ_PRESET = "或照門派的老法子"; // 待 joy 潤
  const LJ_ORDER = "排陣（你帶隊）"; // 待 joy 潤
  const LJ_SWAP = "{a} ⇄ {b}"; // 待 joy 潤
  const LJ_HIDDEN = "對面怎麼排，開打才知道"; // 待 joy 潤
  const LJ_LEAN = "長於{m}"; // 待 joy 潤
  const LJ_BARE = "赤手空拳"; // 待 joy 潤
  const LJ_SAID = "{who}的戰策：{plan}"; // 待 joy 潤
  const LJ_NOPLAN = "{who}沒定戰策"; // 待 joy 潤
  const LJ_HELP = "門派論劍的規矩"; // 待 joy 潤
  const LJ_RULES = [ // 待 joy 潤
    "一週一場。拜了門就能替本門報名，最後一天晚上八點截止、抽籤，九點開打，全自動，分身對分身。",
    "每一門取身手最高的三位上台，照身手由弱到強排成先鋒、中堅、大將；不夠三位由本門師兄補上。沒人報名的門派這一週不出場。",
    "抽籤之後、開打之前，上台的人定一句戰策：看對面三位的武學與拿手的招，寫怎麼打。戰策對路的那一邊起手就佔上風，悟性越高佔得越多；身手還是最要緊，弱一些的人靠戰策也贏得了。",
    "帶隊的人（本門上台的人裡身手最高的那一位）可以重排先鋒、中堅、大將；對面怎麼排，開打才知道。",
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
    if (x && c.phase === "drawn" && c.plan && !c.plan.text) return { ...base, key: `lj:${c.week}:plan`, sub: ljFill(LJ_SUB_PLAN, { fight: c.fight }) };
    if (x && c.phase === "drawn") return { ...base, key: `lj:${c.week}:drawn`, sub: ljFill(LJ_SUB_DRAWN, { ...x, fight: c.fight }) };
    if (c.can_sign && !c.signed) return { ...base, key: `lj:${c.week}:sign`, sub: ljFill(LJ_SUB_SIGN, c) };
    return null;
  }

  function ljSteps(c) { // 三個時刻：報名、抽籤、開打（直接寫字，不畫小圓點）
    const day = (t) => String(t || "").replace(/^第\s*\d+\s*週・/, ""); // 頁首已經寫了第幾週：格子裡只寫星期幾幾點
    const at = [c.draw, c.draw, c.fight].map(day);
    const now = c.phase === "fought" ? 3 : c.phase === "drawn" ? 2 : 0;
    return `<ol class="lj-steps">${LJ_STEPS.map((s, i) => `<li class="${i < now ? "done" : i === now ? "now" : ""}"><b>${s}</b><small>${esc(i === 0 ? ljFill(LJ_UNTIL, { draw: at[0] }) : at[i])}</small></li>`).join("")}</ol>`;
  }

  function ljSignHtml(m, c) {
    if (c.phase !== "sign") return "";
    const o = ((m && m.options) || []).find((x) => x.id === "lunjian:sign");
    const count = (c.signed ? LJ_SIGNED : "") + (c.count ? ljFill(LJ_COUNT, { n: c.count, seats: c.seats }) : LJ_NOBODY);
    const btn = o
      ? `<button class="btn lj-go" data-act="choose" data-id="lunjian:sign">${c.signed ? LJ_RESIGN : LJ_SIGN}<small>${LJ_SIGN_SUB}</small></button>`
      : `<button class="btn lj-go" disabled>${LJ_CLOSED}</button>`;
    return `<p class="lj-how">${esc(count)}</p>${btn}`;
  }

  function ljSeat(s, side, about) {
    if (!s) return `<span class="lj-seat empty"></span>`;
    const tag = s.me ? `<em class="me">${LJ_ME}</em>` : s.elder ? `<em>${LJ_ELDER}</em>` : "";
    // 開打之前的對面：寫兩門武學與拿手的招（寫戰策用）
    const kit = about ? `<small class="lj-kit">${esc((s.arts || []).length ? s.arts.join("、") : LJ_BARE)}${s.lean ? `・${esc(ljFill(LJ_LEAN, { m: s.lean }))}` : ""}</small>` : "";
    return `<span class="lj-seat ${side}${s.me ? " me" : ""}"><b>${esc(s.name)}</b>${tag}${kit}</span>`;
  }

  function ljPlanHtml(c) { // 定戰策那一塊：抽了籤、我上了台、還沒開打
    const p = c.plan;
    if (!p) return "";
    const now = p.text ? ljFill(LJ_PLAN_NOW, { text: p.text }) : LJ_PLAN_NONE;
    const presets = (p.presets || []).map((o) => `<button class="lj-way${o.text === p.text ? " on" : ""}" data-act="choose" data-id="${esc(o.id)}">${esc(o.text)}</button>`).join("");
    const swaps = (p.swaps || []).length
      ? `<div class="lj-order"><b>${LJ_ORDER}</b><div class="lj-ways">${p.swaps.map((o) => `<button class="lj-way" data-act="choose" data-id="${esc(o.id)}">${esc(ljFill(LJ_SWAP, o))}</button>`).join("")}</div></div>`
      : "";
    return `<section class="lj-plan"><h4>${LJ_PLAN}</h4>
        <p class="lj-how">${esc(ljFill(LJ_PLAN_SEAT, { ...p, until: String(p.until || "").replace(/^第\s*\d+\s*週・/, "") }))}</p>
        <p class="lj-now${p.text ? "" : " none"}">${esc(now)}</p>
        <form id="lj-plan" class="lj-form"><input name="text" maxlength="${p.chars}" placeholder="${esc(LJ_PLAN_PH)}" autocomplete="off"><button class="btn" type="submit">${LJ_PLAN_GO}</button></form>
        <p class="lj-sub">${LJ_PRESET}</p><div class="lj-ways">${presets}</div>
        ${swaps}
      </section>`;
  }

  function ljBoard(c) {
    const x = c.match;
    if (!x) return "";
    const rows = LJ_SEATS.map((name, i) => {
      const b = (x.bouts || [])[i];
      const mark = b ? `<span class="lj-tier t-${b.tier === "大勝" || b.tier === "險勝" ? "win" : b.tier === "落敗" ? "lose" : "tie"}">${esc(b.tier)}</span>` : `<span class="lj-tier"></span>`;
      const open = S.ljBout === i;
      const us = ((x.seats_us || [])[i] || {}).name || "", them = ((x.seats_them || [])[i] || {}).name || "";
      const said = b ? [[us, (b.plans || [])[0]], [them, (b.plans || [])[1]]].map(([who, plan]) => `<p class="lj-said">${esc(plan ? ljFill(LJ_SAID, { who, plan }) : ljFill(LJ_NOPLAN, { who }))}</p>`).join("") : "";
      const body = b && b.story ? `<p>${esc(b.story)}</p>` : (b ? (b.lines || []).map((t) => `<p>${esc(t)}</p>`).join("") : "");
      const lines = b && open ? `<div class="lj-lines">${said}${b.crowd ? `<p class="lj-crowd">${esc(b.crowd)}</p>` : ""}${body}</div>` : "";
      const more = b ? `<button class="lj-more" data-act="lj-bout" data-i="${i}" aria-expanded="${open}">${LJ_LINES}<i aria-hidden="true">${open ? "▴" : "▾"}</i></button>` : "";
      // 開打之前：對面照名號排、不對位（另列在底下），這一列只寫我這一邊的位子
      const foe = x.hidden ? "" : ljSeat((x.seats_them || [])[i], "them");
      return `<li class="lj-row"><span class="lj-pos">${name}</span><div class="lj-vs${x.hidden ? " solo" : ""}">${ljSeat((x.seats_us || [])[i], "us")}${mark}${foe}</div>${more}${lines}</li>`;
    }).join("");
    const hidden = x.hidden ? `<div class="lj-foes"><p class="lj-sub">${LJ_HIDDEN}</p>${(x.seats_them || []).map((s) => ljSeat(s, "them", true)).join("")}</div>` : "";
    const end = c.phase === "fought" ? `<span class="lj-stamp">${x.won === "us" ? LJ_WON : x.won === "them" ? LJ_LOST : LJ_TIE}</span>` : "";
    return `<div class="lj-board"><div class="lj-sides"><b>${esc(x.us)}</b><span>${esc((x.score || []).join("　比　"))}</span><b>${esc(x.them)}</b>${end}</div><ol class="lj-rows">${rows}</ol>${hidden}</div>`;
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
        <div class="lj-hero"><span class="lj-seal">${LJ_STAMP}</span><p class="lj-where">${head}</p></div>
        ${c.sect ? ljSteps(c) : ""}
        ${ljSignHtml(m, c)}
        ${ljBoard(c)}
        ${ljPlanHtml(c)}
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

  async function lunjianForm(form, data) {
      if (form.id === "lj-plan") {
        const text = String(data.text || "").trim();
        if (!text) return;
        await busy(async () => {
          const r = await api("/api/lunjian/plan", { text });
          applyMain(r.main);
          if (r.message) toast(r.message);
        });
      } // lunjianForm
  } // lunjianForm
  registerForms(lunjianForm, ["lj-plan"]);
