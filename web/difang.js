/* 地方大事（功能包 difang；Joy 2026-11-26「做」，玩家一起玩設計稿第一節）。
 *
 * 伺服器送 main.difang.card（全服這一週的那一件；人不在那一區 away、看得到出不上力；湊滿了還沒領謝禮的先送那一件）。畫兩樣：
 *   1. 江湖頁眼下的一件（difangEyeItem，web/jianghu.js 的 jhEyeItems 問）：「大事」小印、標題、這一幕、鈕「去看」
 *   2. 點開的那一層（difangSheetHtml，jianghu.js 的 jhSheetHtml 問 sheet "difang"）：頁首圖、懸念一句、三幕直條、
 *      這一幕的墨痕（不寫數字）、這一幕能做的（第二幕三張做法卡、第三幕一顆上前）、出過力的人數、收起來的規矩
 * 按鈕全走殼的 choose（difang:way:<i>、difang:strike、difang:claim:<素材>；第一幕的「去探索」是 act:explore）；這一包只登記「？ 規矩」那一顆（df-help）。
 */
"use strict";

  const DF_SEAL = "大事"; // 待 joy 潤：眼下那一件的小印
  const DF_GO = "去看"; // 待 joy 潤
  const DF_NUM = ["第一幕", "第二幕", "第三幕"]; // 待 joy 潤
  const DF_KIND = "地方大事"; // 待 joy 潤：頁首的朱印
  const DF_EXPLORE = "去探索"; // 待 joy 潤
  const DF_WAY_DONE = "這一幕你已經出過手了，等大家湊齊。"; // 待 joy 潤
  const DF_STRIKE = "上前對付{foe}"; // 待 joy 潤
  const DF_STRIKE_DONE = "今天上去過了，明天再來"; // 待 joy 潤
  const DF_HEADS = "已有 {n} 人出力"; // 待 joy 潤
  const DF_NOBODY = "還沒有人出力"; // 待 joy 潤
  const DF_MINE = "你也在其中"; // 待 joy 潤
  const DF_DONE = "湊滿"; // 待 joy 潤：收場的大印
  const DF_FAILED = "未成"; // 待 joy 潤
  const DF_LAST = "最後一下：{who}"; // 待 joy 潤
  const DF_HELP = "地方大事的規矩"; // 待 joy 潤
  const DF_WHO = "也在出力"; // 待 joy 潤：這一幕那一排名號印上面的小字
  const DF_MORE = "等 {n} 位"; // 待 joy 潤：n 是這一幕出過力的總人數（寫在列出來的名字後面）
  const DF_ME = "你"; // 待 joy 潤：自己那一枚印上寫的字
  const DF_AWAY = "這件事在{region}。人到了那一帶，才出得上力。"; // 待 joy 潤
  const DF_GO_CLAIM = "去領"; // 待 joy 潤：眼下那一件（湊滿了、謝禮還沒領）
  const DF_CLAIM_SUB = "湊滿了，挑一份謝禮"; // 待 joy 潤
  const DF_CLAIM_HEAD = "挑一份謝禮"; // 待 joy 潤
  const DF_CLAIMED = "謝禮領過了"; // 待 joy 潤
  const DF_RULES = [ // 待 joy 潤
    "全天下一週一件，輪著換地方；誰都看得到，人到了那一帶才出得上力。不分官軍、黃巾、散人。",
    "三幕照順序來，前一幕湊齊了才換下一幕；這一週過完沒湊滿，地方就會出事。",
    "湊滿了，出過力的人各挑一份上等素材，還有名聲與心得；出力最多的十位多一份、戴「義士」，最後一下戴「中流砥柱」。",
  ];

  const dfCard = (m) => (m && m.difang && m.difang.card) || null;
  const dfOpt = (m, id) => ((m && m.options) || []).find((o) => o.id === id);

  // 江湖頁眼下的一件（還在湊的那一件才排；收場之後結果寫在江湖紀錄裡）
  function difangEyeItem(m) {
    const c = dfCard(m);
    if (c && c.claim && c.claim.length) return { key: `df:${c.affair}:claim`, seal: DF_SEAL, title: c.title, sub: DF_CLAIM_SUB, btn: DF_GO_CLAIM, attrs: 'data-act="jh-sheet" data-sheet="difang"' };
    if (!c || c.status !== "open") return null;
    const now = c.acts[c.act - 1] || {};
    return { key: `df:${c.affair}:${c.act}`, seal: DF_SEAL, title: c.title, sub: `${DF_NUM[c.act - 1] || ""}・${now.name || ""}`, btn: DF_GO, attrs: 'data-act="jh-sheet" data-sheet="difang"' };
  }

  function dfInk(fill) { // 一條墨痕：照這一幕湊了多少往右暈開，不寫數字
    const w = Math.max(0, Math.min(1, Number(fill) || 0));
    return `<div class="df-ink" role="img" aria-label="進度"><i style="--w:${Math.round(w * 100)}%"></i></div>`;
  }

  function dfMe(m) { return String((m && m.status && m.status.name) || ""); }
  function dfWhoRow(m, a) { // 這一幕誰也在出力：名號墨印一小排（同江湖頁「這裡的人」），放不下寫「等 N 位」；不寫份數、不排名次
    const who = a.who || [];
    if (!who.length) return "";
    const me = dfMe(m);
    const seals = who.map((n) => `<span class="df-pc${n === me ? " me" : ""}"><i>${esc(n === me ? DF_ME : n.slice(0, 1))}</i>${esc(n)}</span>`);
    if (a.more) seals.push(`<span class="df-pc all"><i>＋${a.more}</i>${esc(DF_MORE.replace("{n}", who.length + a.more))}</span>`);
    return `<div class="df-who"><small>${DF_WHO}</small><div class="df-pcs">${seals.join("")}</div></div>`;
  }
  function dfWhoLine(a) { // 湊齊的那一幕：齊字印旁一行名字
    const who = a.who || [];
    if (!who.length) return "";
    return `<small class="df-names">${esc(who.join("、"))}${a.more ? ` <span>${esc(DF_MORE.replace("{n}", who.length + a.more))}</span>` : ""}</small>`;
  }

  function dfDoHtml(m, c) { // 這一幕能做的
    if (c.status !== "open") return "";
    if (c.away) return `<p class="df-how">${esc(DF_AWAY.replace("{region}", c.region))}</p>`;
    if (c.act === 1) {
      const o = dfOpt(m, "act:explore");
      return o && o.enabled ? `<button class="btn df-go" data-act="choose" data-id="act:explore">${DF_EXPLORE}</button>` : ""; // 怎麼出力寫在這一幕那一句（內容檔），不另寫一次
    }
    const opts = c.options || [];
    if (c.act === 2) {
      if (opts.length && opts.every((o) => !o.enabled)) return `<p class="df-how">${DF_WAY_DONE}</p>`;
      return `<div class="df-ways">${opts.map((o) => `<button class="df-way" data-act="choose" data-id="${esc(o.id)}"${o.enabled ? "" : " disabled"}>${esc(String(o.label).split("・").slice(1).join("・") || o.label)}</button>`).join("")}</div>`;
    }
    const o = opts.find((x) => x.id === "difang:strike");
    if (!o) return "";
    return o.enabled
      ? `<button class="btn df-go" data-act="choose" data-id="difang:strike">${esc(DF_STRIKE.replace("{foe}", c.foe))}</button>`
      : `<button class="btn df-go" disabled>${DF_STRIKE_DONE}</button>`;
  }

  function difangSheetHtml(m) {
    const c = dfCard(m);
    if (!c) return "";
    const art = c.art ? `/static/img/events/${esc(c.art)}.webp` : "";
    const end = c.status === "done" ? DF_DONE : c.status === "failed" ? DF_FAILED : "";
    const acts = (c.acts || []).map((a, i) => `<li class="df-act ${esc(a.state)}">
        <span class="df-num">${DF_NUM[i] || ""}</span>
        <div class="df-act-b"><b>${esc(a.name)}</b>${a.state === "now" ? `<p>${esc(a.line)}</p>${dfInk(c.fill)}${dfWhoRow(m, a)}${dfDoHtml(m, c)}` : a.state === "done" ? dfWhoLine(a) : ""}</div>
        ${a.state === "done" ? '<span class="df-tick" aria-label="湊齊了">齊</span>' : ""}
      </li>`).join("");
    const heads = c.heads ? DF_HEADS.replace("{n}", c.heads) : DF_NOBODY;
    const marks = (c.marks || []).map((t) => `<span class="df-mark">${esc(t)}</span>`).join("");
    const claim = c.claim && c.claim.length
      ? `<div class="df-claim"><b>${DF_CLAIM_HEAD}</b><div class="df-ways">${c.claim.map((o) => `<button class="df-way" data-act="choose" data-id="${esc(o.id)}">${esc(o.name)}</button>`).join("")}</div></div>`
      : c.claimed ? `<small class="df-claimed">${DF_CLAIMED}</small>` : "";
    return `<div class="df${c.status !== "open" ? ` df-${esc(c.status)}` : ""}">
        <div class="df-hero">${art ? `<img src="${art}" alt="" decoding="async">` : ""}<span class="df-seal">${DF_KIND}</span><p class="df-where">${esc(c.region)}・${esc(c.place)}</p></div>
        <p class="df-hook">${esc(c.hook)}</p>
        ${end ? `<div class="df-end"><span class="df-stamp">${end}</span><p>${esc(c.result)}</p>${c.last ? `<small>${esc(DF_LAST.replace("{who}", c.last))}</small>` : ""}${marks ? `<div class="df-marks">${marks}</div>` : ""}${claim}</div>` : ""}
        <ol class="df-acts">${acts}</ol>
        <p class="df-foot">${esc(heads)}${c.mine ? `<span class="df-mine">${DF_MINE}</span>` : ""}</p>
        <button class="df-help" data-act="df-help" aria-expanded="${!!S.dfHelp}">？ ${DF_HELP}<i aria-hidden="true">${S.dfHelp ? "▴" : "▾"}</i></button>
        ${S.dfHelp ? `<ul class="df-rules">${DF_RULES.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>` : ""}
      </div>`;
  }

  async function difangClick(act, el, ev) {
    switch (act) {
        case "df-help": S.dfHelp = !S.dfHelp; renderPage(); break;
    } // difangClick
  } // difangClick
  registerClicks(difangClick, ["df-help"]);
