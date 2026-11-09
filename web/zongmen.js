/* 天下大勢的網頁前端：師門（俠客頁的「師門」分頁；tianxia/features/zongmen）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 * 伺服器在你是哪一門的人（或手上有別門的殘頁）時才給 main.zongmen；沒有就沒有這一頁。
 * Joy 2026-11-09「新設計的頁面也都太陽春…水墨風格 操作友善 有質感的UI」：照 docs/superpowers/specs/2026-11-09-介面設計規範.md 畫——
 * 頂上山門一張圖、匾額直書門名、朱印（門人／親傳）；武譜一式一頁，左邊朱紅直條寫第幾式、名字楷書、屬性一枚小色籤、底下落款；
 * 試練中的墨點數人頭；獻式一張一張卡、各自一顆鈕（不用下拉選單）；殘頁是撕過的紙。規矩收在「？」後面。
 */
"use strict";

  // 待 joy 潤：這一段的字
  const ZM_BOOK = "師門武譜";
  const ZM_BOOK_N = "{n} 式入譜";
  const ZM_EMPTY = "譜上還是空的。在外面悟出的意境、自創合出的武學，回山門獻上來，就是這本譜的第一式。";
  const ZM_WAIT = "同門試練中";
  const ZM_TRIED = "{n}／{need} 人試過";
  const ZM_MINE = "你獻的";
  const ZM_DONE = "你試過了";
  const ZM_LEARN = "學這一式";
  const ZM_LEARNED = "已學";
  const ZM_OFFER_HEAD = "獻式";
  const ZM_OFFER = "獻上";
  const ZM_HOME = "身在山門";
  const ZM_AWAY = "回{place}才能獻式、學式、試練";
  const ZM_HALF = "重學・心得 {n}";
  const ZM_OFFER_SUB = "獻上去自己那一份不少";
  const ZM_MEMBER = "門人";
  const ZM_INNER = "親傳";
  const ZM_PAGES = "殘頁";
  const ZM_PAGES_SUB = "截殺打贏別門親傳撿來的";
  const ZM_PAGE_LEARN = "照殘頁學";
  const ZM_HELP = "師門的規矩";
  const ZM_RULES = [
    "學譜上一式：心得 {learn}；換季重學打五折。學到的比原本低一品。",
    "試練同門獻的式：心得 {trial}。試過的人夠了就入譜，刻上獻的人的名字，換季也在。",
    "獻式：意境或自創合出的武學都能獻，獻上去自己那一份不少。",
    "學過兩式、或譜上有你獻的式，就是親傳；親傳被截殺打輸，會掉一張殘頁。",
    "照殘頁偷學：只學得到入門（下品），心得 {page}，學了殘頁就沒了。",
  ];
  // 山門的圖（web/img/events/）：門派 id → 圖名；沒有對到的用 town
  const ZM_ART = { baima: "temple", nanhua: "altar", songyang: "forest", lulin: "camp", xiangshe: "village", yingchuan_academy: "academy", cao_manor: "town" };
  const ZM_ATTR = { 剛: "gang", 快: "kuai", 柔: "rou", 慢: "man" };

  const zmKind = (e) => {
    const attr = ZM_ATTR[e.attr];
    return `<span class="zm-kind${attr ? ` ${attr}` : ""}">${esc(e.kind || "意境")}${e.attr ? `・${esc(e.attr)}` : ""}</span>`;
  };
  const zmDots = (n, need) => `<span class="zm-dots" role="meter" aria-valuemin="0" aria-valuemax="${need}" aria-valuenow="${n}" aria-label="${ZM_TRIED.replace("{n}", n).replace("{need}", need)}">${
    Array.from({ length: need }, (_, i) => `<i class="${i < n ? "on" : ""}"></i>`).join("")}</span>`;

  function zmPage(e, gate) {
    const act = e.learned ? `<span class="zm-stamp" aria-label="${ZM_LEARNED}">${ZM_LEARNED}</span>`
      : !gate ? ""
      : e.problem ? `<small class="zm-why">${esc(e.problem)}</small>`
      : `<button class="btn primary zm-go" data-act="zm-learn" data-id="${esc(e.id)}">${e.price ? ZM_HALF.replace("{n}", e.price) : ZM_LEARN}</button>`;
    return `<li class="zm-pg${e.learned ? " learned" : ""}">
      <span class="zm-num" aria-hidden="true">第${esc(e.num)}式</span>
      <div class="zm-pg-body">
        <div class="zm-pg-hd"><b class="zm-pg-name">${esc(e.name)}</b>${zmKind(e)}</div>
        <p class="zm-fx">${esc(e.fx)}</p>
        ${(e.effects || []).length ? `<ul class="zm-effects">${e.effects.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>` : ""}
        ${e.note ? `<p class="zm-note">${esc(e.note)}</p>` : ""}
        <div class="zm-pg-foot"><span class="zm-by">${esc(e.by)}</span>${act}</div>
      </div></li>`;
  }

  function zmScrap(e) {
    const act = e.learned ? `<span class="zm-stamp">${ZM_LEARNED}</span>`
      : e.problem ? `<small class="zm-why">${esc(e.problem)}</small>`
      : `<button class="btn zm-go" data-act="zm-page" data-sect="${esc(e.sect_id)}" data-id="${esc(e.id)}">${ZM_PAGE_LEARN}</button>`;
    return `<li class="zm-scrap"><div class="zm-scrap-hd"><small>${esc(e.sect)}・第${esc(e.num)}式</small>${zmKind(e)}</div>
      <b class="zm-pg-name">${esc(e.name)}</b><p class="zm-fx">${esc(e.fx)}</p>
      <div class="zm-pg-foot"><span class="zm-by">${esc(e.by)}</span>${act}</div></li>`;
  }

  function zmRules(z) {
    const open = !!S.zmHelp;
    const body = open ? `<ul class="zm-rules">${ZM_RULES.map((t) => `<li>${t.replace("{learn}", z.learn_xinde).replace("{trial}", z.trial_xinde).replace("{page}", z.page_xinde)}</li>`).join("")}</ul>` : "";
    return `<button class="zm-help" data-act="zm-help" aria-expanded="${open}"><span class="zm-q" aria-hidden="true">？</span>${ZM_HELP}<span aria-hidden="true">${open ? "▴" : "▾"}</span></button>${body}`;
  }

  function zmPagesSec(z) {
    if (!(z.pages || []).length) return "";
    return `<section class="zm-sec" aria-label="${ZM_PAGES}"><div class="zm-sec-hd"><h4>${ZM_PAGES}</h4><small>${ZM_PAGES_SUB}・心得 ${z.page_xinde}</small></div>
      <ol class="zm-scraps">${z.pages.map(zmScrap).join("")}</ol></section>`;
  }

  // 俠客頁「師門」分頁的整頁（cultivation.js 照 main.zongmen 有沒有決定要不要這一頁）
  function zongmenHtml(m) {
    const z = m && m.zongmen;
    if (!z) return "";
    if (!z.sect) return `<div class="zongmen">${zmPagesSec(z)}${zmRules(z)}</div>`;
    const art = ZM_ART[z.sect_id] || "town";
    const hero = `<header class="zm-hero">
      <div class="zm-hero-art" style="background-image:url('/static/img/events/${art}.webp')" role="img" aria-label="${esc(z.sect)}"></div>
      <h3 class="zm-plaque">${esc(z.sect)}</h3>
      <div class="zm-hero-text">
        <span class="zm-seal${z.inner ? " inner" : ""}">${z.inner ? ZM_INNER : ZM_MEMBER}</span>
        ${z.desc ? `<p class="zm-desc">${esc(z.desc)}</p>` : ""}
        <p class="zm-where${z.gate ? " home" : ""}"><i aria-hidden="true"></i>${z.gate ? ZM_HOME : ZM_AWAY.replace("{place}", esc(z.place))}</p>
      </div></header>`;
    const book = `<section class="zm-sec zm-book" aria-label="${ZM_BOOK}"><div class="zm-sec-hd"><h4>${ZM_BOOK}</h4>${z.entries.length ? `<small>${ZM_BOOK_N.replace("{n}", z.entries.length)}</small>` : ""}</div>
      ${z.entries.length ? `<ol class="zm-pages">${z.entries.map((e) => zmPage(e, z.gate)).join("")}</ol>` : `<p class="zm-empty">${ZM_EMPTY}</p>`}</section>`;
    const wait = (w) => `<li class="zm-wait"><div><b>${esc(w.name)}</b><small>${esc(w.kind || "意境")}・${esc(w.giver)}獻${w.mine ? `・${ZM_MINE}` : w.done ? `・${ZM_DONE}` : ""}</small></div>
      <div class="zm-wait-n">${zmDots(w.tried, w.need)}<small>${ZM_TRIED.replace("{n}", w.tried).replace("{need}", w.need)}</small></div></li>`;
    const waiting = z.waiting.length ? `<section class="zm-sec" aria-label="${ZM_WAIT}"><div class="zm-sec-hd"><h4>${ZM_WAIT}</h4></div>
      <ul class="zm-waits">${z.waiting.map(wait).join("")}</ul></section>` : "";
    const offer = (o) => {
      const [kind, ...rest] = o.name.split("・");
      return `<li class="zm-offer"><div><small>${esc(rest.length ? kind : "")}</small><b>${esc(rest.length ? rest.join("・") : o.name)}</b></div>
        <button class="btn zm-go" data-act="zm-offer" data-id="${esc(o.id)}">${ZM_OFFER}</button></li>`;
    };
    const offers = z.offers.length ? `<section class="zm-sec" aria-label="${ZM_OFFER_HEAD}"><div class="zm-sec-hd"><h4>${ZM_OFFER_HEAD}</h4><small>${ZM_OFFER_SUB}</small></div>
      <ul class="zm-offers">${z.offers.map(offer).join("")}</ul></section>` : "";
    // 能做的排前面：在山門時試練與獻式在武譜上面；不在山門時武譜先（看得到、做不了）
    const acts = `${waiting}${offers}`;
    return `<div class="zongmen">${hero}${z.gate ? `${acts}${book}` : `${book}${acts}`}${zmPagesSec(z)}${zmRules(z)}</div>`;
  }

  async function zongmenClick(act, el, ev) {
    switch (act) {
        case "zm-learn": doMain("zongmen_learn", { id: el.dataset.id }); break;
        case "zm-offer": doMain("zongmen_offer", { id: el.dataset.id }); break;
        case "zm-page": doMain("zongmen_page", { sect: el.dataset.sect, id: el.dataset.id }); break;
        case "zm-help": { const go = () => { S.zmHelp = !S.zmHelp; renderPage(); }; typeof heroStay === "function" ? heroStay(go) : go(); break; } // 不跳頂
    } // zongmenClick
  } // zongmenClick
  registerClicks(zongmenClick, ["zm-learn", "zm-offer", "zm-page", "zm-help"]);
