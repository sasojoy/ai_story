/* 天下大勢的網頁前端：酒肆（功能包 tianxia/features/tavern/，開發規範手冊 3.7、G9）。
 *
 * 酒肆（tavernHtml）：聽消息、打聽、題壁、暗處四頁的畫法與表單（tavDo）；2026-11-10 照介面設計規範翻新（宣紙、楷書、色票、44px、說明收起來）。
 * 跟 mall.js 一樣是一般的 <script>：頂層的名字同在一個全域裡；/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 * 全部拆包第 65 批從 app.js 逐行切出來（計畫 docs/superpowers/plans/2026-11-06-網頁殼化-第65批.md）。點擊、表單用 registerClicks、registerForms 登記在這支檔；店面的框（shopHtml、renderShop）照舊在 app.js（殼）。
 */
"use strict";

  // ── 酒肆（企劃者 2026-10-18「可以，做精緻一些，包含氛圍感」；2026-11-10 翻新照介面設計規範，Joy「可以 按照建議」，翻新稿
  // https://claude.ai/artifact/DGvRR7PS1mk31dcv4s7jPP）：宣紙底、色票（深色跟著走），頁首是酒肆的畫＋直書匾額＋朱印城名，酒家那一句用楷書寫在畫底下。
  // 四頁：聽消息（座上客、一顆主鈕聽消息、請酒與懸賞榜、剛聽到的、鄰桌閒談）、打聽（三種問法、名號帶入、素材卡）、題壁（粉牆直書，跨季留著）、
  // 暗處（風聲、自保三張卡、買殺手）。動作走 MAIN_ACTIONS tavern（shopDo）。暖光呼吸，減少動態效果的人不動 ──
  const TAV_TABS = [["news", "聽消息"], ["ask", "打聽"], ["wall", "題壁"], ["shade", "暗處"]];
  const TAV_SEAL = { news: "聞", seek: "蹤", ties: "交", ask: "問", material: "料", trace: "查", guard: "護", hide: "藏", hit: "刺", treat: "請", wall: "題" }; // 紙條左上那顆小印
  const TAV_KIND = { "剛": "gang", "快": "kuai", "柔": "rou", "慢": "man" };
  const TAV_NUM = "零一二三四五六七八九十";
  const TAV_WALL_PAGE = 4; // 牆一面幾句

  function tavTab() { return TAV_TABS.some(([k]) => k === S.tavTab) ? S.tavTab : "news"; }
  function tavHelp() { return S.tavHelp || (S.tavHelp = {}); } // 「？」攤開了哪幾個（重畫不收回）
  function tavSeasonName(n) { return n <= 10 ? `第${TAV_NUM[n]}季` : n < 20 ? `第十${TAV_NUM[n - 10]}季` : `第 ${n | 0} 季`; }

  // 頁首：酒肆的畫（events/tavern.webp）、直書匾額、朱印寫城名、酒家那一句；聽消息那一頁再加座上客（點了去打聽他）
  function tavHeroHtml(shop, full) {
    const city = String(shop.sign || "").split("・")[0];
    const guests = !full ? "" : `<div class="tv-guests"><span class="gl">座上客</span>${shop.guests.length
      ? shop.guests.map((g) => `<button class="tv-chip" data-act="tav-guest" data-name="${esc(g)}">${esc(g)}</button>`).join("") + (shop.more_guests ? `<span class="gl">還有 ${shop.more_guests | 0} 人</span>` : "")
      : '<span class="gl">今晚冷清，只有你一桌</span>'}</div>`; // 待 joy 潤（原字）
    return `<div class="tav-hero${full ? "" : " slim"}"><div class="tv-art" aria-hidden="true"><i class="tv-glow a"></i><i class="tv-glow b"></i></div>
      <span class="tv-plaque" aria-hidden="true">酒肆</span>
      <div class="tv-text">${city ? `<span class="tv-seal">${esc(city)}</span>` : ""}<p class="tv-say">${esc(shop.line || "")}</p>${guests}</div></div>`;
  }

  // 打聽到的一則（聽消息、下落、交情、素材、反查）：一張紙條，左上一顆小印標是哪一種；一模一樣的合成一則、標 ×N
  function tavNoteHtml(n, times) {
    return `<article class="tav-note k-${esc(n.kind)}"><span class="tv-k">${esc(TAV_SEAL[n.kind] || "聞")}</span><div class="tag"><b>${esc(n.title)}${times > 1 ? `<span class="tv-x">×${times | 0}</span>` : ""}</b><span>${esc(n.when)}</span></div>${n.lines.map((l) => `<p>${esc(l)}</p>`).join("")}</article>`;
  }
  function tavNotes(shop, kinds, empty) {
    const rows = [], seen = new Map();
    for (const n of shop.notes.filter((x) => kinds.includes(x.kind))) {
      const key = n.kind + "\n" + n.title + "\n" + n.lines.join("\n");
      if (seen.has(key)) { rows[seen.get(key)].times += 1; continue; }
      seen.set(key, rows.length); rows.push({ n, times: 1 });
    }
    return rows.length ? rows.map((r) => tavNoteHtml(r.n, r.times)).join("") : (empty ? `<p class="tv-empty">${esc(empty)}</p>` : "");
  }
  function tavDone() { return S.shopNote ? shopNoteHtml("") : ""; } // 這一下的結果（只有有結果時才畫）
  function tavBtn(op, label, price, why, extra = "") {
    return `<button class="tav-act" data-act="tav-do" data-op="${op}"${why ? ` disabled title="${esc(why)}"` : ""}><b>${esc(label)}</b><small>${why ? esc(why) : `${price | 0} 兩`}</small>${extra}</button>`;
  }
  function tavSec(name, note) { return `<h4 class="tav-h">${esc(name)}${note ? `<small>${esc(note)}</small>` : ""}</h4>`; }
  function tavFold(key, label, lines) {
    const open = !!tavHelp()[key];
    return `<button class="tv-fold" data-act="tav-help" data-key="${esc(key)}" aria-expanded="${open}"><span><i class="q">？</i>${esc(label)}</span><span>${open ? "▴" : "▾"}</span></button>${open ? `<ul class="tv-rules">${lines.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>` : ""}`;
  }
  function tavToggle(flag, on, text, attrs = "") {
    return `<button type="button" class="tv-toggle${on ? " on" : ""}" data-act="tav-flag" data-flag="${flag}" aria-pressed="${on}"${attrs}><i>${on ? "✓" : ""}</i><span>${esc(text)}</span></button>`;
  }
  function tavNames(label, names, act) {
    return names.length ? `<div class="tv-names"><span class="gl">${esc(label)}</span>${names.map((n) => `<button class="tav-chip" data-act="${act}" data-name="${esc(n)}">${esc(n)}</button>`).join("")}</div>` : "";
  }

  function tavNewsHtml(shop) {
    const treat = shop.treat ? `<p class="tav-treat">${esc(shop.treat)}</p>` : "";
    const talk = shop.chatter.length
      ? `${tavSec("鄰桌閒談", "壓低了聲音")}<ul class="tav-talk">${shop.chatter.map((c) => `<li>${c.who ? `<span class="who">${esc(c.who)}</span>` : ""}${esc(c.said)}</li>`).join("")}</ul>` : "";
    const board = shop.board ? `<button class="tav-act" data-act="choose" data-id="${esc(shop.board)}"><b>看懸賞榜 ›</b><small>牆上貼的告示</small></button>` : ""; // 待 joy 潤
    const hire = typeof tavHireHtml === "function" ? tavHireHtml() : ""; // 招募（hire 包；親衛隊長第四批關掉後是空的）：收成最底下一行
    const hireRow = !hire ? "" : `<button class="tv-fold" data-act="tav-help" data-key="hire" aria-expanded="${!!tavHelp().hire}"><span>酒肆裡有人想跟你走</span><span>${tavHelp().hire ? "▴" : "▾"}</span></button>${tavHelp().hire ? hire : ""}`; // 待 joy 潤
    return `${tavHeroHtml(shop, true)}${treat}
      <div class="tv-card tv-listen"><button class="btn primary tav-listen" data-act="tav-do" data-op="news">聽消息<small>${shop.prices.news | 0} 兩</small></button><p>酒家收了錢，把這一帶最近的事說給你聽。</p></div>
      <div class="tav-row">${tavBtn("treat", "請全店喝一輪", shop.prices.treat, shop.problems.treat)}${board}</div>
      ${tavDone()}
      ${shop.notes.some((n) => n.kind === "news") ? tavSec("剛聽到的") : ""}${tavNotes(shop, ["news"], "")}
      ${talk}${hireRow}`; // 鈕都在聽到的消息上面：聽一則多一則，不把請酒那一顆往下推
  } // 待 joy 潤：「酒家收了錢…」

  function tavAskHtml(shop) {
    const mode = ["ties", "q"].includes(S.tavAsk) ? S.tavAsk : "seek";
    const modes = [["seek", "查下落", shop.prices.seek], ["ties", "問交情", shop.prices.ties], ["q", "問酒家", shop.prices.ask]]
      .map(([k, name, price]) => `<button class="tv-mode${mode === k ? " on" : ""}" data-act="tav-mode" data-mode="${k}" aria-pressed="${mode === k}"><b>${name}</b><small>${price | 0} 兩</small></button>`).join("");
    const w = shop.watch || { price: 0, mine: [] };
    const names = [...shop.guests, ...shop.known.filter((n) => !shop.guests.includes(n))].slice(0, 10); // 座上客在前、問過的在後，同一個名字只寫一次
    let box, rules;
    if (mode === "q") {
      const left = shop.asks_left == null ? "" : `<p class="tv-left">今天還能問<span class="tv-dots">${"<i></i>".repeat(Math.max(0, shop.asks_left | 0))}</span>${shop.asks_left ? "" : "（明天再來）"}</p>`; // 待 joy 潤
      box = `<form class="tav-form" id="tav-q"><input class="input" name="text" data-keep="q" maxlength="${shop.ask_chars | 0}" placeholder="例：最近哪裡最亂？" autocomplete="off"><button class="btn primary" type="submit">問</button></form>${left}`;
      rules = [`隨口問一句（${shop.ask_chars | 0} 字內），酒家照他聽來的說。`, "他答不上來不收錢。"];
    } else {
      box = `<form class="tav-form" id="tav-ask"><input class="input" name="target" data-keep="ask" maxlength="20" placeholder="報個名號" autocomplete="off"><button class="btn primary" type="submit">打聽</button></form>
        ${mode === "seek" ? tavToggle("watch", S.tavWatch, `問不清楚就託酒家留意，有準信捎進你的江湖紀錄（多付 ${w.price | 0} 兩）`) : ""}
        ${mode === "seek" && w.mine.length ? `<ul class="tav-whispers">${w.mine.map((t) => `<li class="named">${esc(t)}</li>`).join("")}</ul>` : ""}
        ${tavNames("點名號帶進去", names, "tav-name")}`;
      rules = mode === "seek" ? ["江湖人物、大勢人物都能問。", "越有名、離這裡越近，越問得準。", "問不到退一半。"]
        : ["問誰跟他走得近、他身邊有誰、近來做了什麼。", "越有名越好打聽；問不到退一半。"];
    }
    const tiers = [...new Set(shop.materials.map((m) => m.tier))].sort((a, b) => a - b);
    const tier = tiers.includes(S.tavMatTier) ? S.tavMatTier : tiers[0];
    const mats = shop.materials.filter((m) => m.tier === tier).map((m) => `<div class="tv-mat"><div class="tv-mat-hd"><b>${esc(m.name)}</b><span class="tv-kind ${TAV_KIND[m.attribute] || ""}">${esc(m.attribute)}</span></div>
      <button class="btn" data-act="tav-mat" data-id="${esc(m.id)}">打聽・${m.price | 0} 兩</button></div>`).join("");
    return `${tavHeroHtml(shop, false)}
      <div class="tv-modes">${modes}</div>
      <div class="tv-ask">${box}</div>
      ${tavFold("ask-" + mode, "打聽的規矩", rules)}
      ${tavDone()}
      ${shop.notes.some((n) => ["ask", "seek", "ties", "material"].includes(n.kind)) ? tavSec("剛問到的") : ""}${tavNotes(shop, ["ask", "seek", "ties", "material"], "")}
      ${tiers.length ? `${tavSec("打聽素材", "哪裡採得到")}<div class="tv-tiers">${tiers.map((t) => `<button class="${t === tier ? "on" : ""}" data-act="tav-mat-tier" data-tier="${t}">${TAV_NUM[t] || t}階</button>`).join("")}</div><div class="tv-mats">${mats}</div>` : ""}`;
  } // 待 joy 潤：三種問法的名字、規矩條列

  function tavWallHtml(shop) {
    const pages = Math.max(1, Math.ceil(shop.walls.length / TAV_WALL_PAGE));
    const page = Math.min(Math.max(0, S.tavWallPage | 0), pages - 1);
    const shown = shop.walls.slice(page * TAV_WALL_PAGE, page * TAV_WALL_PAGE + TAV_WALL_PAGE);
    const wall = shop.walls.length
      ? `<div class="tav-wall"><div class="cols">${shown.map((w) => `<p class="wcol"><span class="ink">${esc(w.text)}</span><small>${esc(w.who)}${w.season ? `<i class="tav-seal old">${tavSeasonName(w.season)}</i>` : '<i class="tav-seal">題</i>'}</small></p>`).join("")}</div>
        <div class="more"><span>這面牆題過 ${shop.walls.length | 0} 句</span>${pages > 1 ? (page + 1 < pages ? `<button data-act="tav-wall-page" data-page="${page + 1}">更早的 ›</button>` : '<button data-act="tav-wall-page" data-page="0">‹ 回最新</button>') : ""}</div></div>`
      : '<p class="tv-empty">粉牆上還乾乾淨淨，等人來題第一句。</p>';
    return `${tavHeroHtml(shop, false)}
      <div class="tv-card tv-wform"><form class="tav-form" id="tav-wall"><input class="input" name="text" data-keep="wall" maxlength="${shop.wall_chars | 0}" placeholder="借酒家的筆，題一句" autocomplete="off"><button class="btn primary" type="submit">題壁</button></form>
        <p class="tv-left">最多 ${shop.wall_chars | 0} 字・${shop.prices.wall | 0} 兩・來這間酒肆的人都看得到，換季也留著</p></div>
      ${tavDone()}${wall}`;
  } // 待 joy 潤：「換季也留著」「這面牆題過」

  function tavShadeHtml(shop) {
    const heard = shop.whispers.length
      ? `<ul class="tav-whispers">${shop.whispers.map((w) => `<li class="${w.named ? "named" : ""}">${esc(w.text)}</li>`).join("")}</ul>`
      : '<p class="tv-empty">最近沒聽說有人打聽你。</p>';
    const h = shop.hits;
    const tier = h.tiers.some((t) => t.tier === S.tavTier) ? S.tavTier : 1;
    const tiers = h.tiers.map((t, i) => `<button type="button" class="tav-tier${t.tier === tier ? " on" : ""}" data-act="tav-tier" data-tier="${t.tier}" aria-pressed="${t.tier === tier}"><b>${esc(t.name)}</b><span class="tv-dots red">${h.tiers.map((_, j) => `<i class="${j <= i ? "f" : ""}"></i>`).join("")}</span><small>${t.price | 0} 兩</small></button>`).join("");
    const mine = h.mine.length ? `${tavSec("我下的單")}<ul class="tav-whispers">${h.mine.map((m) => `<li class="named">${esc(m)}</li>`).join("")}</ul>` : "";
    const streaks = (h.streaks || []).length ? `<ul class="tav-whispers">${h.streaks.map((m) => `<li>${esc(m)}</li>`).join("")}</ul>` : "";
    const hire = h.ended ? "" : `${tavSec("買殺手", "找上門的事，不說是誰")}
      <div class="tav-tiers">${tiers}</div>
      <div class="tv-ask"><form class="tav-form" id="tav-hit"><input class="input" name="target" data-keep="hit" maxlength="20" placeholder="報一個查到過的名號" autocomplete="off"><button class="btn primary" type="submit">雇</button></form>
      ${tavToggle("hush", S.tavHush, `加付封口錢 ${h.hush | 0} 兩，失手、被反查時不容易供出你`)}
      ${tavNames("查到過的", shop.known.slice(0, 8), "tav-hit-name")}</div>${streaks}
      ${tavFold("hit", "殺手的規矩", ["報一個查到過的名號，同陣營也接。", "殺手只在城外出手，下線時人在城外也一樣；得手了對方氣血只剩 1。", "失手一次，下一張找同一人的單貴一半、殺手更狠，最多三次。", "找不到人，期限到了退一半。"])}`;
    return `${tavHeroHtml(shop, false)}
      ${tavSec("風聲", "有人在打聽你")}${heard}
      ${tavSec("自保")}
      <div class="tv-trio">${tavBtn("trace", "反查是誰", shop.prices.trace, "")}${tavBtn("hide", "藏起行跡", shop.prices.hide, shop.problems.hide)}${tavBtn("guard", "雇保鏢", h.guard, h.guard_problem)}</div>
      ${shop.hidden ? `<p class="tv-left">${esc(shop.hidden)}</p>` : ""}
      ${tavFold("guard", "藏行跡與保鏢", ["藏行跡：打點酒家與跑堂，接下來一天別人難打聽到你。", "保鏢：殺手找上時有人替你擋一擋。"])}
      ${tavDone()}${tavNotes(shop, ["trace", "guard"], "")}${hire}${tavNotes(shop, ["hit"], "")}${mine}`;
  }

  function tavernHtml(shop) {
    const tab = tavTab();
    const body = { news: tavNewsHtml, ask: tavAskHtml, wall: tavWallHtml, shade: tavShadeHtml }[tab](shop);
    // 頁首那一幅畫在捲的那一層裡（Joy 2026-10-19「視窗大小跳來跳去」：四頁的框一樣高，換頁時底下的格子不上下跳）
    return `<div class="shop-body"><div class="shop-col">${body}</div></div>
      <nav class="shop-tabs">${TAV_TABS.map(([k, name]) => `<button class="shop-tab${tab === k ? " on" : ""}" data-act="tav-tab" data-tab="${k}">${name}</button>`).join("")}</nav>`;
  }

  // 打聽到了的寫成一則（每一頁「剛問到的」），那一句不再另外寫在上面；沒問到、被拒的那一句才寫
  async function tavDo(op, body = {}, route = "tavern") {
    const seen = S.main && S.main.shop && S.main.shop.notes ? S.main.shop.notes.length : 0;
    const top = S.main && S.main.shop && S.main.shop.notes && S.main.shop.notes[0] ? S.main.shop.notes[0].when + S.main.shop.notes[0].title : "";
    await shopDo(route, route === "tavern" ? { op, ...body } : body, (r) => {
      const notes = r.main && r.main.shop && r.main.shop.notes;
      if (notes && notes.length && (notes.length !== seen || notes[0].when + notes[0].title !== top)) S.shopNote = null;
    });
  }
  async function tavernClick(act, el, ev) {
    switch (act) {
        case "tav-tab": S.tavTab = el.dataset.tab; S.shopNote = null; renderShop(false); break; // 酒肆：四頁
        case "tav-do": await tavDo(el.dataset.op); break;
        case "tav-mode": S.tavAsk = el.dataset.mode; renderShop(); break; // 打聽：查人在哪／打聽情誼
        case "tav-tier": S.tavTier = Number(el.dataset.tier); renderShop(); break; // 買殺手：三檔
        case "tav-hit-name": { const box = document.querySelector('#tav-hit input[name="target"]'); if (box) { box.value = el.dataset.name; box.focus(); } break; }
        case "tav-name": { const box = document.querySelector('#tav-ask input[name="target"]'); if (box) { box.value = el.dataset.name; box.focus(); } break; }
        case "tav-guest": { // 點座上客：去打聽頁查他的下落，名號帶進框裡（Joy 11/10 照建議）
          S.tavTab = "ask"; S.tavAsk = "seek"; S.shopNote = null; renderShop(false);
          const box = document.querySelector('#tav-ask input[name="target"]'); if (box) box.value = el.dataset.name; break;
        }
        case "tav-help": tavHelp()[el.dataset.key] = !tavHelp()[el.dataset.key]; renderShop(); break; // 「？」攤開、收起
        case "tav-flag": if (el.dataset.flag === "watch") S.tavWatch = !S.tavWatch; else S.tavHush = !S.tavHush; renderShop(); break; // 託留意、封口錢
        case "tav-mat-tier": S.tavMatTier = Number(el.dataset.tier); renderShop(); break; // 打聽素材：一階到四階
        case "tav-mat": S.tavMat = el.dataset.id; await tavDo("material", { target: el.dataset.id }); break;
        case "tav-wall-page": S.tavWallPage = Number(el.dataset.page); renderShop(); break; // 題壁：翻到前一面
    } // tavernClick
  } // tavernClick
  registerClicks(tavernClick, ["tav-tab", "tav-do", "tav-mode", "tav-tier", "tav-hit-name", "tav-name", "tav-guest", "tav-help", "tav-flag", "tav-mat-tier", "tav-mat", "tav-wall-page"]);
  async function tavernForm(form, data) {
      if (form.id === "tav-ask") {
        if (!data.target.trim()) return;
        const seek = S.tavAsk !== "ties";
        await tavDo(seek ? "seek" : "ties", { target: data.target.trim(), text: seek && S.tavWatch ? "watch" : "" }); // 託留意是頁上的開關（S.tavWatch）
      } else if (form.id === "tav-q") {
        if (!data.text.trim()) return;
        await tavDo("", { text: data.text.trim() }, "tavern_ask");
        const box = document.querySelector('#tav-q input[name="text"]');
        if (box && S.shopNote == null) box.value = "";
      } else if (form.id === "tav-hit") {
        if (!data.target.trim()) return;
        const hush = S.tavHush; // 封口錢是頁上的開關
        const tier = S.main.shop.hits.tiers.some((t) => t.tier === S.tavTier) ? S.tavTier : 1;
        const name = S.main.shop.hits.tiers.find((t) => t.tier === tier).name;
        ask(`雇${name}去找${data.target.trim()}？`, "雇", () => tavDo("hit", { target: data.target.trim(), text: `${tier}${hush ? ":hush" : ""}` }));
      } else if (form.id === "tav-wall") {
        if (!data.text.trim()) return;
        await tavDo("wall", { text: data.text.trim() });
        const box = document.querySelector('#tav-wall input[name="text"]');
        if (box && !(S.shopNote || "").startsWith("一句最多")) box.value = "";
      } // tavernForm
  } // tavernForm
  registerForms(tavernForm, ["tav-ask", "tav-q", "tav-hit", "tav-wall"]);
