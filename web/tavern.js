/* 天下大勢的網頁前端：酒肆（功能包 tianxia/features/tavern/，開發規範手冊 3.7、G9）。
 *
 * 酒肆（tavernHtml）：聽消息、題壁、暗處、打聽四頁的畫法與表單（tavDo）。
 * 跟 mall.js 一樣是一般的 <script>：頂層的名字同在一個全域裡；/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 * 全部拆包第 65 批從 app.js 逐行切出來（計畫 docs/superpowers/plans/2026-11-06-網頁殼化-第65批.md）。點擊、表單用 registerClicks、registerForms 登記在這支檔；店面的框（shopHtml、renderShop）照舊在 app.js（殼）。
 */
"use strict";

  // ── 酒肆（企劃者 2026-10-18「可以，做精緻一些，包含氛圍感」；草圖甲「夜燈酒肆」）：跟三間店同一層。四頁：聽消息（燈籠、酒罈、熱湯的場景，
  // 座上客、請酒、鄰桌閒談、聽消息）、打聽（下落、交情、素材）、題壁、暗處（風聲、藏行跡、反查）。打聽到的寫在每一頁「剛問到的」底下；
  // 動作走 MAIN_ACTIONS tavern（shopDo）。燈籠搖、熱氣冒，減少動態效果的人不動。字待 joy 潤 ──
  const TAV_TABS = [["news", "聽消息"], ["ask", "打聽"], ["wall", "題壁"], ["shade", "暗處"]];
  const TAV_LANTERN = (word) => `<svg class="tav-lantern" viewBox="0 0 46 96" aria-hidden="true"><line x1="23" y1="0" x2="23" y2="18" stroke="#2a170d" stroke-width="2"/><rect x="14" y="16" width="18" height="6" rx="1.5" fill="#c99a3a"/><ellipse cx="23" cy="46" rx="20" ry="25" fill="#c8321e"/><ellipse cx="23" cy="46" rx="12" ry="24" fill="#e2502e" opacity=".7"/><ellipse cx="23" cy="46" rx="5" ry="22" fill="#ffb15a" opacity=".55"/><path d="M5 38 Q23 34 41 38 M4 46 Q23 43 42 46 M5 54 Q23 51 41 54" stroke="#8c1f12" stroke-width="1" fill="none" opacity=".6"/>${word ? `<text x="23" y="52" text-anchor="middle" font-size="16" font-weight="700" fill="#2a0e06" opacity=".75">${word}</text>` : ""}<rect x="14" y="70" width="18" height="5" rx="1.5" fill="#c99a3a"/><path d="M19 75 L18 94 M23 75 L23 96 M27 75 L28 94" stroke="#d23a24" stroke-width="1.5"/></svg>`;
  const TAV_HERO = `<div class="tav-hero" aria-hidden="true"><i class="tav-glow l"></i><i class="tav-glow r"></i>
    <span class="tav-hang l">${TAV_LANTERN("")}</span><span class="tav-hang r">${TAV_LANTERN("酒")}</span>
    <svg class="tav-bowl" viewBox="0 0 70 40"><g class="tav-steam" stroke="#f6dcb0" stroke-width="1.6" fill="none" stroke-linecap="round"><path d="M24 18 q-4 -6 0 -10 q4 -4 0 -8"/><path d="M34 18 q-4 -6 0 -10 q4 -4 0 -8"/><path d="M44 18 q-4 -6 0 -10 q4 -4 0 -8"/></g><path d="M12 22 L58 22 Q56 36 35 37 Q14 36 12 22 Z" fill="#3a2414"/><path d="M12 22 L58 22" stroke="#c99a3a" stroke-width="1.5"/></svg>
    <svg class="tav-jars" viewBox="0 0 150 66"><g fill="#0e0805"><path d="M8 64 Q2 40 14 26 L14 18 L30 18 L30 26 Q42 40 36 64 Z"/><path d="M46 64 Q40 44 50 32 L50 26 L62 26 L62 32 Q72 44 66 64 Z"/><path d="M78 64 Q70 36 86 20 L86 10 L104 10 L104 20 Q120 36 112 64 Z"/><path d="M120 64 Q116 48 124 40 L124 34 L134 34 L134 40 Q142 48 138 64 Z"/></g><rect x="88" y="34" width="14" height="18" fill="#7a2014" opacity=".85"/><text x="95" y="47" text-anchor="middle" font-size="11" fill="#e8c27a">酒</text></svg>
    <i class="tav-table"></i></div>`;

  function tavTab() { return TAV_TABS.some(([k]) => k === S.tavTab) ? S.tavTab : "news"; }

  // 打聽到的一則（聽消息、下落、交情、素材、反查）：小標、時刻，一行一句
  function tavNoteHtml(n) {
    return `<article class="tav-note k-${esc(n.kind)}"><div class="tag"><b>${esc(n.title)}</b><span>${esc(n.when)}</span></div>${n.lines.map((l) => `<p>${esc(l)}</p>`).join("")}</article>`;
  }
  function tavNotes(shop, kinds, empty) {
    const rows = shop.notes.filter((n) => kinds.includes(n.kind));
    return rows.length ? rows.map(tavNoteHtml).join("") : (empty ? `<p class="shop-empty">${esc(empty)}</p>` : "");
  }
  function tavDone() { return S.shopNote ? shopNoteHtml("") : ""; } // 這一下的結果（只有有結果時才畫）
  function tavBtn(op, label, price, why) {
    return `<button class="tav-act" data-act="tav-do" data-op="${op}"${why ? ` disabled title="${esc(why)}"` : ""}><b>${esc(label)}</b><small>${why ? esc(why) : `${price | 0} 兩`}</small></button>`;
  }

  function tavNewsHtml(shop) {
    const guests = shop.guests.length
      ? `<div class="tav-guests"><span class="gl">座上客</span>${shop.guests.map((g) => `<span class="tav-chip">${esc(g)}</span>`).join("")}${shop.more_guests ? `<span class="more">還有 ${shop.more_guests | 0} 人</span>` : ""}</div>`
      : `<div class="tav-guests"><span class="gl">座上客</span><span class="more">今晚冷清，只有你一桌</span></div>`;
    const treat = shop.treat ? `<p class="tav-treat">${esc(shop.treat)}</p>` : "";
    const talk = shop.chatter.length
      ? `<h4 class="tav-h">鄰桌閒談<small>壓低了聲音</small></h4><ul class="tav-talk">${shop.chatter.map((c) => `<li>${c.who ? `<span class="who">${esc(c.who)}</span>` : ""}${esc(c.said)}</li>`).join("")}</ul>` : "";
    const board = shop.board ? `<button class="btn ghost small tav-board" data-act="choose" data-id="${esc(shop.board)}">看牆上的懸賞榜 ›</button>` : "";
    return `${guests}${treat}
      <button class="tav-listen" data-act="tav-do" data-op="news">聽消息<span>（${shop.prices.news | 0} 兩）</span></button>
      <div class="tav-row">${tavBtn("treat", "請全店喝一輪", shop.prices.treat, shop.problems.treat)}${board}</div>
      ${tavDone()}
      ${tavNotes(shop, ["news"], "")}
      ${tavHireHtml()}${talk}`; // 鈕都在聽到的消息上面：聽一則多一則，不把請酒那一顆往下推
  }

  function tavAskHtml(shop) {
    const mode = ["ties", "q"].includes(S.tavAsk) ? S.tavAsk : "seek";
    const modes = [["seek", "查人在哪", shop.prices.seek], ["ties", "打聽情誼", shop.prices.ties], ["q", "問酒家", shop.prices.ask]]
      .map(([k, name, price]) => `<button class="shop-page${mode === k ? " on" : ""}" data-act="tav-mode" data-mode="${k}">${name}・${price | 0} 兩</button>`).join("");
    const asked = shop.known.filter((n) => !shop.guests.includes(n)).slice(0, 8); // 問過的（座上客已經列了的不重寫）
    const known = asked.length ? `<div class="tav-known"><span class="gl">問過的</span>${asked.map((n) => `<button class="tav-chip" data-act="tav-name" data-name="${esc(n)}">${esc(n)}</button>`).join("")}</div>` : "";
    const guests = shop.guests.length ? `<div class="tav-known"><span class="gl">座上客</span>${shop.guests.map((n) => `<button class="tav-chip" data-act="tav-name" data-name="${esc(n)}">${esc(n)}</button>`).join("")}</div>` : "";
    const hint = mode === "seek" ? "報個名號（江湖人物或大勢人物都行）。越有名、離這裡越近，越問得準；問不到退一半。"
      : mode === "ties" ? "問誰跟他走得近、他身邊有誰、近來做了什麼。越有名越好打聽；問不到退一半。"
      : `隨口問一句（${shop.ask_chars | 0} 字內），酒家照他聽來的說。他答不上來不收錢。${shop.asks_left == null ? "" : `今天還能問 ${shop.asks_left | 0} 次。`}`; // 待 joy 潤：一天的次數（心神開著才有）
    const box = mode === "q"
      ? `<form class="tav-form" id="tav-q"><input class="input" name="text" data-keep="q" maxlength="${shop.ask_chars | 0}" placeholder="例：最近哪裡最亂？" autocomplete="off"><button class="btn primary small" type="submit">問</button></form>`
      : `<form class="tav-form" id="tav-ask"><input class="input" name="target" data-keep="ask" maxlength="20" placeholder="名號" autocomplete="off"><button class="btn primary small" type="submit">打聽</button></form>`;
    const w = shop.watch || { price: 0, mine: [] };
    const watch = mode === "seek"
      ? `<label class="tav-hush"><input type="checkbox" name="watch" form="tav-ask"${S.tavWatch ? " checked" : ""}> 託酒家留意，多付 ${w.price | 0} 兩（問不清楚時，有了準信捎進你的江湖紀錄）</label>${w.mine.length ? `<ul class="tav-whispers">${w.mine.map((t) => `<li class="named">${esc(t)}</li>`).join("")}</ul>` : ""}` : "";
    const mats = shop.materials.map((m) => `<option value="${esc(m.id)}"${m.id === S.tavMat ? " selected" : ""}>${esc(m.name)}（${m.tier | 0} 階・${m.price | 0} 兩）</option>`).join("");
    return `<div class="shop-pages tav-modes">${modes}</div>
      ${box}${watch}
      <p class="shop-cap">${esc(hint)}</p>${mode === "q" ? "" : guests + known}
      <h4 class="tav-h">打聽素材<small>哪裡採得到</small></h4>
      <form class="tav-form" id="tav-mat"><select class="input" name="material">${mats}</select><button class="btn small" type="submit">打聽</button></form>
      ${tavDone()}
      ${tavNotes(shop, ["ask", "seek", "ties", "material"], "還沒打聽過什麼。")}`;
  }

  function tavWallHtml(shop) {
    const walls = shop.walls.length
      ? `<div class="tav-wall">${shop.walls.map((w) => `<p><span class="ink">${esc(w.text)}</span><small>${esc(w.who)}・${esc(w.when)}<i class="tav-seal">題</i></small></p>`).join("")}</div>`
      : '<p class="shop-empty">粉牆上還乾乾淨淨，等人來題第一句。</p>';
    return `<p class="shop-cap">借酒家的筆，在牆上留一句話（最多 ${shop.wall_chars | 0} 字，${shop.prices.wall | 0} 兩）。來這間酒肆的人都看得到。</p>
      <form class="tav-form" id="tav-wall"><input class="input" name="text" data-keep="wall" maxlength="${shop.wall_chars | 0}" placeholder="題一句" autocomplete="off"><button class="btn primary small" type="submit">題壁</button></form>
      ${tavDone()}${walls}`;
  }

  function tavShadeHtml(shop) {
    const heard = shop.whispers.length
      ? `<ul class="tav-whispers">${shop.whispers.map((w) => `<li class="${w.named ? "named" : ""}">${esc(w.text)}</li>`).join("")}</ul>`
      : '<p class="shop-empty">最近沒聽說有人打聽你。</p>';
    const h = shop.hits;
    const tier = h.tiers.some((t) => t.tier === S.tavTier) ? S.tavTier : 1;
    const tiers = h.tiers.map((t) => `<button type="button" class="tav-tier${t.tier === tier ? " on" : ""}" data-act="tav-tier" data-tier="${t.tier}"><b>${esc(t.name)}</b><small>${t.price | 0} 兩</small></button>`).join("");
    const names = shop.known.slice(0, 8).map((n) => `<button class="tav-chip" data-act="tav-hit-name" data-name="${esc(n)}">${esc(n)}</button>`).join("");
    const mine = h.mine.length ? `<ul class="tav-whispers">${h.mine.map((m) => `<li class="named">${esc(m)}</li>`).join("")}</ul>` : "";
    const streaks = (h.streaks || []).length ? `<ul class="tav-whispers">${h.streaks.map((m) => `<li>${esc(m)}</li>`).join("")}</ul>` : "";
    const hire = h.ended ? "" : `<h4 class="tav-h">買殺手<small>找上門的事，不說是誰</small></h4>
      <p class="shop-cap">報一個查到過的名號，同陣營也接。殺手只在城外出手（下線時人在城外也一樣）；得手了對方氣血只剩 1。失手一次，下一張找同一人的單貴一半、殺手更狠，最多三次。找不到人，期限到了退一半。</p>
      <div class="tav-tiers">${tiers}</div>
      <form class="tav-form" id="tav-hit"><input class="input" name="target" data-keep="hit" maxlength="20" placeholder="名號" autocomplete="off"><button class="btn primary small" type="submit">雇</button></form>
      <label class="tav-hush"><input type="checkbox" name="hush" form="tav-hit"${S.tavHush ? " checked" : ""}> 加付封口錢 ${h.hush | 0} 兩（失手、被反查時不容易供出你）</label>
      ${names ? `<div class="tav-known"><span class="gl">查到過的</span>${names}</div>` : ""}${streaks}${mine}`;
    return `<h4 class="tav-h">風聲<small>有人在打聽你</small></h4>${heard}
      <div class="tav-row">${tavBtn("trace", "反查是誰", shop.prices.trace, "")}${tavBtn("hide", "藏起行跡", shop.prices.hide, shop.problems.hide)}${tavBtn("guard", "雇保鏢", h.guard, h.guard_problem)}</div>
      ${shop.hidden ? `<p class="shop-cap">${esc(shop.hidden)}</p>` : '<p class="shop-cap">藏行跡：打點酒家與跑堂，接下來一天別人難打聽到你。保鏢：殺手找上時有人替你擋一擋。</p>'}
      ${tavDone()}${tavNotes(shop, ["trace", "guard"], "")}${hire}${tavNotes(shop, ["hit"], "")}`;
  }

  function tavernHtml(shop) {
    const tab = tavTab();
    const body = { news: tavNewsHtml, ask: tavAskHtml, wall: tavWallHtml, shade: tavShadeHtml }[tab](shop);
    // 燈籠那一幅畫在捲的那一層裡：四頁的框一樣高，換頁時底下的格子不上下跳（Joy 2026-10-19「視窗大小跳來跳去」）
    return `<div class="shop-body"><div class="shop-col">${tab === "news" ? TAV_HERO : ""}${body}</div></div>
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
    } // tavernClick
  } // tavernClick
  registerClicks(tavernClick, ["tav-tab", "tav-do", "tav-mode", "tav-tier", "tav-hit-name", "tav-name"]);
  async function tavernForm(form, data) {
      if (form.id === "tav-ask") {
        if (!data.target.trim()) return;
        const seek = S.tavAsk !== "ties";
        if (seek) S.tavWatch = !!data.watch;
        await tavDo(seek ? "seek" : "ties", { target: data.target.trim(), text: seek && data.watch ? "watch" : "" });
      } else if (form.id === "tav-q") {
        if (!data.text.trim()) return;
        await tavDo("", { text: data.text.trim() }, "tavern_ask");
        const box = document.querySelector('#tav-q input[name="text"]');
        if (box && S.shopNote == null) box.value = "";
      } else if (form.id === "tav-mat") {
        if (!data.material) return;
        S.tavMat = data.material;
        await tavDo("material", { target: data.material });
      } else if (form.id === "tav-hit") {
        if (!data.target.trim()) return;
        S.tavHush = !!data.hush;
        const tier = S.main.shop.hits.tiers.some((t) => t.tier === S.tavTier) ? S.tavTier : 1;
        const name = S.main.shop.hits.tiers.find((t) => t.tier === tier).name;
        ask(`雇${name}去找${data.target.trim()}？`, "雇", () => tavDo("hit", { target: data.target.trim(), text: `${tier}${data.hush ? ":hush" : ""}` }));
      } else if (form.id === "tav-wall") {
        if (!data.text.trim()) return;
        await tavDo("wall", { text: data.text.trim() });
        const box = document.querySelector('#tav-wall input[name="text"]');
        if (box && !(S.shopNote || "").startsWith("一句最多")) box.value = "";
      } // tavernForm
  } // tavernForm
  registerForms(tavernForm, ["tav-ask", "tav-q", "tav-mat", "tav-hit", "tav-wall"]);
