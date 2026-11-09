/* 天下大勢的網頁前端：親衛隊長的養成冊（俠客頁「同伴」最上面；tianxia/features/guard）。
 *
 * 設計稿 https://claude.ai/artifact/7Sra7sBo7njyH34B2Nr7Su（Joy 2026-11-09「其他都按照建議」）。照 docs/superpowers/specs/2026-11-09-介面設計規範.md 畫：
 * 頂上院子一張圖淡進卡色、右上直書「養成冊」的匾、他的直排名帖與心性的朱印；一條情分墨線（不露數字）；眼前那一件事（三個做法、自己寫）；
 * 底下撕紙的紀事。第二批：求學時寫他在哪、哪時回來（信也是眼前那一件），出師以後名帖旁寫出路與稱號、多一段只有你看得到的生平。
 * 伺服器收養了才給 main.guard；沒有就不畫。
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 */
"use strict";

  // 待 joy 潤：這一段的字
  const GD_PLAQUE = "養成冊";
  const GD_METER = "{pron}看你的眼神";
  const GD_HATE = "恨";
  const GD_LOVE = "恩";
  const GD_NOW = "眼前這件事";
  const GD_OPEN = "看看{name}怎麼了";
  const GD_OWN = "或者，你自己寫要怎麼做⋯⋯";
  const GD_SAY = "就這麼辦";
  const GD_WAIT = "{name}還在等你⋯⋯";
  const GD_QUIET = "這會兒沒什麼事。每天總有一兩件家裡的事；帶{pron}出門，路上也會有。";
  const GD_LOG = "紀事";
  const GD_LOG_SUB = "{pron}記得的事";
  const GD_LOG_EMPTY = "還沒有。";
  const GD_ALONG_ON = "出門帶著{pron}";
  const GD_ALONG_OFF = "出門讓{pron}留下";
  const GD_RENAME = "替{pron}改名";
  const GD_RENAME_GO = "就叫這個";
  const GD_RENAME_NOTE = "名字只能改一次。";
  const GD_STUDY = "送{pron}去求學";
  const GD_AWAY = "{name}在{school}求學，{until}學成回來。這幾天{pron}會寫信給你。";
  const GD_SETTLING = "{name}學成回來了，站在你面前。{pron}會成為什麼樣的人，過一會兒就知道。";
  const GD_SWORN = "{name}站在你身後。";
  const GD_BIO = "生平";
  const GD_BIO_SUB = "只有你看得到";
  const GD_KIND = { letter: "來信", trial: "出師考驗", oath: "立誓" };

  const gdFill = (s, g) => s.replace(/\{name\}/g, g.name).replace(/\{pron\}/g, g.pron)
    .replace(/\{school\}/g, g.school || "").replace(/\{until\}/g, g.study_until || "");

  function guardHtml(m) {
    const g = m && m.guard;
    if (!g) return "";
    const pct = Math.max(0, Math.min(1, Number(g.meter) || 0.5)) * 100;
    const hero = `<header class="gd-hero">
      <div class="gd-hero-art" style="background-image:url('/static/img/events/village.webp')" role="img" aria-label="${esc(g.name)}"></div>
      <h3 class="gd-plaque">${GD_PLAQUE}</h3>
      <div class="gd-tie"><span class="gd-name">${esc(g.name)}</span><span class="gd-tie-side">
        <span class="gd-stage">${esc(g.stage_text || "")}${g.path ? `・${esc(g.path)}「${esc(g.title)}」` : ""}</span>
        <span class="gd-seal">${esc(g.band)}</span></span></div>
    </header>`;
    const meter = `<div class="gd-meter" role="img" aria-label="${esc(gdFill(GD_METER, g))}：${esc(g.band)}">
      <div class="gd-bar"><i style="left:${pct.toFixed(1)}%"></i></div>
      <div class="gd-lbl"><span>${GD_HATE}</span><span>${esc(gdFill(GD_METER, g))}</span><span>${GD_LOVE}</span></div></div>`;
    const ev = g.event;
    let now;
    const idle = g.stage === "study" ? GD_AWAY : g.stage === "settle" || g.stage === "trial" ? GD_SETTLING : g.stage === "sworn" ? GD_SWORN : GD_QUIET;
    const kind = ev && GD_KIND[ev.kind] ? `<small>${GD_KIND[ev.kind]}</small>` : "";
    if (!ev) now = `<p class="gd-quiet">${esc(gdFill(idle, g))}</p>`
      + (g.can_study ? `<button class="btn primary gd-open" data-act="choose" data-id="guard:study">${esc(gdFill(GD_STUDY, g))}</button>` : "");
    else if (!ev.shown) now = `<button class="btn primary gd-open" data-act="choose" data-id="guard:open">${esc(gdFill(GD_OPEN, g))}</button>`;
    else {
      const picks = ev.choices.map((c, i) => `<button class="gd-opt" data-act="choose" data-id="guard:pick:${i}"><span class="gd-dot t${i}" aria-hidden="true"></span>${esc(c)}</button>`).join("");
      now = `<p class="gd-scene">${esc(ev.text)}</p><div class="gd-opts">${picks}</div>
        <div class="gd-own"><input class="input" id="gd-say" maxlength="${g.say_max | 0}" placeholder="${esc(GD_OWN)}" aria-label="${esc(GD_OWN)}">
        <button class="btn primary" data-act="gd-say">${GD_SAY}</button></div>`;
    }
    const nowSec = `<section class="gd-sec" aria-label="${GD_NOW}"><div class="gd-sec-hd"><h4>${GD_NOW}</h4>${kind}</div>${now}</section>`;
    const bioSec = g.bio ? `<section class="gd-sec" aria-label="${GD_BIO}"><div class="gd-sec-hd"><h4>${GD_BIO}</h4><small>${GD_BIO_SUB}</small></div>
      <p class="gd-bio">${esc(g.bio)}</p></section>` : "";
    const log = g.log.length
      ? `<div class="gd-log">${g.log.map((e) => `<p class="gd-scrap tone${e.tone}"><small>${esc(e.stamp)}</small>${esc(e.text)}</p>`).join("")}</div>`
      : `<p class="gd-quiet">${GD_LOG_EMPTY}</p>`;
    const logSec = `<section class="gd-sec" aria-label="${GD_LOG}"><div class="gd-sec-hd"><h4>${GD_LOG}</h4><small>${esc(gdFill(GD_LOG_SUB, g))}</small></div>${log}</section>`;
    const along = g.stage !== "grow" && g.stage !== "sworn" ? "" : `<button class="btn ghost gd-along" data-act="gd-along" data-on="${g.along ? 0 : 1}" aria-pressed="${!!g.along}">${esc(gdFill(g.along ? GD_ALONG_ON : GD_ALONG_OFF, g))}</button>`;
    const rename = !g.can_rename ? "" : S.gdRename
      ? `<div class="gd-own"><input class="input" id="gd-name" maxlength="6" value="${esc(g.name)}" aria-label="${esc(gdFill(GD_RENAME, g))}"><button class="btn primary" data-act="gd-rename-go">${GD_RENAME_GO}</button></div><p class="gd-note">${GD_RENAME_NOTE}</p>`
      : `<button class="btn ghost" data-act="gd-rename">${esc(gdFill(GD_RENAME, g))}</button>`;
    return `<div class="guard">${hero}${meter}${nowSec}${bioSec}<div class="gd-tools">${along}${rename}</div>${logSec}</div>`;
  }

  async function guardClick(act, el, ev) {
    switch (act) {
        case "gd-say": {
          const box = document.getElementById("gd-say");
          const text = box ? box.value.trim() : "";
          if (text) await doMain("guard_say", { text });
          break;
        }
        case "gd-along": await doMain("guard_along", { on: el.dataset.on === "1" }); break;
        case "gd-rename": { const go = () => { S.gdRename = true; renderPage(); }; typeof heroStay === "function" ? heroStay(go) : go(); break; } // 按完不跳頂（Joy 11/7）
        case "gd-rename-go": {
          const box = document.getElementById("gd-name");
          const name = box ? box.value.trim() : "";
          if (name) { S.gdRename = false; await doMain("guard_rename", { name }); }
          break;
        }
    } // guardClick
  } // guardClick
  registerClicks(guardClick, ["gd-say", "gd-along", "gd-rename", "gd-rename-go"]);
