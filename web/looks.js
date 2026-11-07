/* 天下大勢的網頁前端：擂台形象、自建形象、形象市集、絕招與管理者區的自建形象（功能包 tianxia/features/looks/；第二輪第 94 批從 mall.js 切出來）。
 *
 * 跟 mall.js 一樣是一般的 <script>：頂層的名字同在一個全域裡；/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 * 樣式的 look 那一段還在 mall.css。貨架、紀錄、購買確認、易名帖、查帳是商城包的，在 mall.js。
 */
"use strict";

  // ── 擂台形象（功能包 tianxia/features/looks/；Joy 2026-10-31）：萬寶閣「形象」那一頁。每一套一張卡：站著的那一格當預覽、名字、
  // 說明；穿著的寫「穿著」，買了的一顆「換上」，沒買的一顆「買（價錢）」（點了跟貨架同一條購買確認）。預設的斗笠小子永遠在最前 ──
  // 官方的在 /static/img/looks/<id>/，自建的（u<數字>）由伺服器從資料庫旁邊送（/api/looks/img/<id>/<張>）
  const LOOK_VER = () => (window.LOOKS_VER ? `?v=${window.LOOKS_VER}` : "");
  const LOOK_IMG = (id) => (/^u\d+$/.test(id || "") ? `/api/looks/img/${id}/hero_bare_idle${LOOK_VER()}`
    : /^[a-z0-9_]+$/.test(id || "") ? `/static/img/looks/${id}/hero_bare_idle.webp` : "/static/img/arena/hero_bare_idle.webp");
  function lookFaceHtml(id) { // 站著那張的第一格（四格一張、880×220）裁成一個人
    return `<span class="look-face" aria-hidden="true" style="background-image:url('${LOOK_IMG(id)}')"></span>`;
  }
  // 形象那一頁（Joy 2026-11-03「形象頁那邊的排版也是亂七八糟」「建立了一大堆形象跟絕招…會變得很難用」，示意稿「新・形象頁」）：
  // 最上面一塊台子站著點了的那一套（沒點就是身上穿的），台子上「看動作」與換上／價錢；底下分三頁（我的／官方／市集），
  // 我的再用小標籤篩（官方、自建、市集買的）；每套一張小格、一排三格，一次最多 LOOK_PAGE 格，多的按「再看」。最底一張絕招連過去。
  // 自建形象、絕招各自一頁（S.lookSub），左上回形象
  const LOOKSUB_NAMES = { make: "自建形象", move: "絕招" };
  const LOOK_PAGE = 18;
  const LOOK_SEGS = [["mine", "我的"], ["shop", "官方"], ["market", "市集"]];
  const LOOK_FILTERS = [["all", "全部"], ["official", "官方"], ["made", "自建"], ["bought", "市集買的"]];
  const lookKind = (lk) => (lk.mine ? "made" : /^u\d+$/.test(lk.id) ? "bought" : "official");
  function mallLooksHtml(d) {
    if (!d) return mallFailHtml();
    if (S.lookSub === "make" && d.order) return lookSubHtml("make", lookShowHtml() + lookOrderHtml(d.order, d));
    if (S.lookSub === "move" && d.moves) return lookSubHtml("move", moveHtml(d.moves));
    const shelf = (S.mallData && S.mallData.items) || [];
    const market = (d.market && d.market.shelf) || [];
    const mine = d.looks.filter((lk) => lk.owned);
    const shop = d.looks.filter((lk) => !lk.owned);
    const lists = { mine, shop, market };
    const seg = LOOK_SEGS.some(([k]) => k === S.lookSeg) && (S.lookSeg !== "market" || d.market) ? S.lookSeg : "mine";
    // 台子：點了的那一套（三頁裡找），沒點就是身上穿的
    const pick = d.looks.find((lk) => lk.id === S.lookPick) || market.find((x) => x.look === S.lookPick) || d.looks.find((lk) => lk.id === d.worn) || d.looks[0];
    const stage = pick ? lookStageHtml(pick, d, shelf) : "";
    const filters = LOOK_FILTERS.filter(([k]) => k === "all" || mine.some((lk) => lookKind(lk) === k));
    const filter = seg === "mine" && filters.some(([k]) => k === S.lookFilter) ? S.lookFilter : "all";
    const shown = seg === "mine" ? mine.filter((lk) => filter === "all" || lookKind(lk) === filter) : lists[seg];
    const limit = Math.max(LOOK_PAGE, S.lookLimit | 0);
    const tile = (x) => {
      const id = x.look || x.id, on = id === d.worn, sel = pick && id === (pick.look || pick.id);
      const tag = x.look ? `<span class="look-tag2">${x.price | 0}</span>` : lookKind(x) === "made" ? `<span class="look-tag2">自建</span>`
        : lookKind(x) === "bought" ? `<span class="look-tag2">市集</span>` : !x.owned && x.item ? `<span class="look-tag2">${(shelf.find((one) => one.id === x.item) || {}).price | 0}</span>` : "";
      return `<button class="look-tile${on ? " on" : ""}${sel ? " sel" : ""}" data-act="look-pick" data-id="${esc(id)}" aria-pressed="${!!sel}">
          <span class="look-pad">${lookFaceHtml(id)}${on ? `<span class="look-tag">穿著</span>` : ""}${tag}</span><b>${esc(x.name)}</b></button>`;
    };
    const o = d.order;
    const make = seg === "mine" && o ? `<button class="look-tile look-make" data-act="look-sub" data-sub="make"><span class="look-pad"><span class="plus" aria-hidden="true">＋</span></span>
        <b>${o.open ? "有一套在畫" : "自建一套"}</b></button>` : "";
    const empty = !shown.length && !make ? `<p class="mall-note">${seg === "market" ? "別的玩家自建、上架的形象會擺在這裡。現在還沒有人上架。" : seg === "shop" ? "官方的形象你都有了。" : "這一類還沒有。"}</p>` : "";
    const more = shown.length > limit ? `<button class="btn ghost look-more" data-act="look-more">再看 ${Math.min(LOOK_PAGE, shown.length - limit)} 套（還有 ${shown.length - limit} 套）</button>` : "";
    const segs = `<div class="look-segs" role="tablist">${LOOK_SEGS.filter(([k]) => k !== "market" || d.market).map(([k, name]) =>
      `<button class="${seg === k ? "on" : ""}" role="tab" aria-selected="${seg === k}" data-act="look-seg" data-seg="${k}">${name} ${lists[k].length}</button>`).join("")}</div>`;
    const chips = seg === "mine" && filters.length > 2 ? `<div class="mall-cats">${filters.map(([k, name]) =>
      `<button class="mall-cat${filter === k ? " on" : ""}" data-act="look-filter" data-filter="${k}">${name}</button>`).join("")}</div>` : "";
    return `${stage}${lookShowHtml()}${segs}${chips}<div class="look-tiles">${make}${shown.slice(0, limit).map(tile).join("")}</div>${empty}${more}${moveEntryHtml(d.moves)}`;
  }
  // 台子：大的那一張、這一套是什麼（穿著中／官方／自建／市集買的／誰做的）、名字、看動作，與換上／穿著中／價錢（官方的走貨架同一條購買確認，市集的先問一次）
  function lookStageHtml(x, d, shelf) {
    const id = x.look || x.id, on = id === d.worn;
    const what = x.look ? `${esc(x.seller)}做的・市集` : { made: "自建", bought: "市集買的", official: "官方" }[lookKind(x)];
    const it = !x.look && !x.owned && x.item ? shelf.find((one) => one.id === x.item) : null;
    const act = on ? `<span class="look-on">穿著中</span>`
      : x.look ? `<button class="btn small buy" data-act="market-buy" data-id="${esc(id)}" data-name="${esc(x.name)}" data-price="${x.price | 0}">${ingotSvg()}${x.price | 0}</button>`
      : x.owned ? `<button class="btn small primary" data-act="look-wear" data-id="${esc(id)}">換上</button>`
      : it ? `<button class="btn small buy" data-act="mall-pick" data-id="${esc(it.id)}">${ingotSvg()}${it.price | 0}</button>` : "";
    return `<div class="look-stage">${lookFaceHtml(id)}<div class="look-stage-bar"><span><small>${what}</small><b>${esc(x.name)}</b></span>
        ${lookShowBtn(id, x.name)}${act}</div></div>${x.note ? `<p class="mall-note look-stage-note">${esc(x.note)}</p>` : ""}`;
  }
  // 自建形象、絕招那一頁的頂上：回形象一顆、標題；自建形象多一排四步（走到哪一步亮到哪）
  const LOOKSUB_STEPS = ["寫樣子", "畫坊作畫", "審核", "進「我的」"];
  function lookSubHtml(sub, body) {
    const o = S.mallLooks && S.mallLooks.order;
    const at = o && (o.list || []).some((x) => x.status === "review") ? 3 : o && o.open ? 2 : 1;
    const steps = sub === "make" ? `<ol class="look-steps">${LOOKSUB_STEPS.map((t, i) => `<li class="${i < at ? "on" : ""}"><span>${"一二三四"[i]}</span>${t}</li>`).join("")}</ol>` : "";
    return `<div class="look-subbar"><button class="btn small ghost" data-act="look-sub" data-sub="">‹ 形象</button><b>${LOOKSUB_NAMES[sub]}</b></div>${steps}${body}`;
  }
  // 形象頁最底那一張絕招：身上穿哪一招、招式庫幾招，按了進絕招那一頁
  function moveEntryHtml(m) {
    if (!m) return "";
    const n = (m.library || []).length;
    const say = !m.has_art && !n ? "先練一門自己合成或自創的武功，才能替它畫招式。" : "換招、寫新的一招都在這裡";
    return `<div class="mall-sub">絕招<small>${n ? `招式庫 ${n} 招` : "擂台上演出來"}</small></div>
      <button class="move-entry" data-act="look-sub" data-sub="move"><span class="move-ico" aria-hidden="true"></span>
        <span><b>${m.worn ? `身上穿著「${esc(m.worn)}」` : "身上沒穿絕招"}</b><small>${say}</small></span><span class="go" aria-hidden="true">›</span></button>`;
  }
  // 看動作（Joy 2026-11-01「已經做好的形象跟絕招也要能展示」）：按了在格子上面那塊畫布把這一套十張一張一張演（arena_scene.js 的 lookShow）
  const lookShowBtn = (id, name) => `<button class="btn small ghost look-show-btn" data-act="look-show" data-id="${esc(id)}" data-name="${esc(name)}">看動作</button>`;
  function lookShowHtml() {
    const v = S.lookShow;
    if (!v) return "";
    return `<div class="look-show"><canvas id="look-show" class="scene-preview" width="720" height="320" aria-label="「${esc(v.name)}」的動作"></canvas>
      <div class="row"><b>${esc(v.name)}</b><button class="btn small ghost" data-act="look-show" data-id="">收起</button></div></div>`;
  }
  function lookShowTo(id, name) {
    S.lookShow = id === "" || (S.lookShow && S.lookShow.id === id) ? null : { id, name };
    if (S.mallOpen) renderMall();
    if (S.lookShow && typeof lookShow === "function") lookShow(S.lookShow.id);
  }
  // 自建形象（第二批；Joy 2026-11-03 要完整流程、要裝得下很多，示意稿「自建形象」）：正在畫的那一張（一次一張，撤得回來）；
  // 沒有在畫才有「寫一套」（名字、一句樣子、想不到就點、下單）；做好的直接進形象頁「我的」，這裡只管市集上架（總共賣了幾份、
  // 入帳多少、押著多少；掛著的排前面，沒掛的摺起來，按「掛上去」才跳出定價）；退回的摺起來，留最新一張（改一改再送）
  const LOOK_ORDER_NOTE = "畫好、審過就放進「我的」。沒通過的話，元寶全部退回。"; // 待 joy 潤
  const LOOK_EXAMPLES = ["白衣書生，背著竹簍", "黑甲將軍，手持長槍", "紅衣女刀客"]; // 想不到就點；待 joy 潤
  // 絕招的例句（Joy 2026-11-05「現在的demo提示詞沒辦法完美展示我們的多種招式施放」）：每一句演得出不同的法相出場、主攻路線、對手異狀
  // （scenes.py 的 MOTIONS／PATHS／MARKS）。一次擺三句，「換一批」換下一組三句（S.moveExAt），重畫時不會自己亂跳
  const MOVE_EXAMPLES = [
    "一劍寒光九萬里",
    "夜色驟暗，萬劍環成劍輪，絞向對手將其冰封",
    "背後浮現明王法相緩緩旋轉，一道金光平推而出",
    "火鳳自天降臨，挾漫天火星撞向對手，烈焰焚身",
    "背後幻出三尊羅漢分身，地底雷光轟然湧上",
    "雪落無聲，一道寒光自對手背後襲來，將他擊飛",
    "落花滿天，劍雨傾盆而下，中者身染劇毒",
    "大地震動，一隻巨石拳迴旋砸出，轟然爆炸",
    "紫氣漫天，神龍自雲端降臨，龍口吐出一道紫光盤旋而出",
    "秋葉蕭瑟，一道碧色劍氣迴旋連斬九道",
    "大佛法相脈動金光，佛掌從天壓下，對手被震飛又遭雷殛",
  ];
  const MOVE_EX_SHOWN = 3;
  const exampleHtml = (list, target) => {
    const many = list.length > MOVE_EX_SHOWN && list === MOVE_EXAMPLES;
    const at = many ? ((S.moveExAt | 0) % list.length + list.length) % list.length : 0;
    const shown = many ? Array.from({ length: MOVE_EX_SHOWN }, (_, k) => list[(at + k) % list.length]) : list;
    return `<div class="look-ex"><span>想不到就點：</span>${shown.map((t) =>
      `<button class="btn small ghost" data-act="prompt-ex" data-for="${target}" data-text="${esc(t)}">${esc(t)}</button>`).join("")}${many
      ? '<button class="btn small ghost ex-more" data-act="prompt-ex-more">換一批 ↻</button>' : ""}</div>`;
  };
  function moveExMore() {
    const box = document.getElementById("move-prompt");
    if (box) S.moveDraft = box.value; // 框裡打到一半的字跟著重畫留著
    S.moveExAt = ((S.moveExAt | 0) + MOVE_EX_SHOWN) % MOVE_EXAMPLES.length;
    renderMall();
  }
  const waitIcon = '<span class="look-wait" aria-hidden="true"></span>';
  function lookOrderHtml(o, d) {
    if (!o) return "";
    const list = o.list || [];
    const open = list.filter((x) => x.status === "pending" || x.status === "review");
    const drawing = open.map((x) => `<div class="look-line wait">${waitIcon}<span class="lo-main"><b>${esc(x.name)}</b>
        <small>${x.status === "review" ? "圖畫好了，等看過就放進「我的」。" : "畫好會通知你，可以先去忙。"}</small></span>
        <span class="look-st st-${esc(x.status)}">${esc(x.status_text)}</span>${withdrawBtn(x, "look", x.name)}</div>`).join("");
    const form = o.open ? "" : `<div class="mall-sub">寫一套</div><div class="look-order-form">
        <label for="look-name">名字（${o.name_max | 0} 字內）</label><input class="input" id="look-name" maxlength="${o.name_max | 0}" autocomplete="off" value="${esc(S.lookDraft ? S.lookDraft.name : "")}">
        <label for="look-prompt">長什麼樣子（${o.prompt_max | 0} 字內）</label><textarea class="input" id="look-prompt" maxlength="${o.prompt_max | 0}" rows="3">${esc(S.lookDraft ? S.lookDraft.prompt : "")}</textarea>
        ${exampleHtml(LOOK_EXAMPLES, "look-prompt")}
        <button class="btn primary buy" data-act="look-order">${ingotSvg()}${o.price | 0}　下單</button><p class="mall-note">${esc(LOOK_ORDER_NOTE)}</p></div>`;
    const rejected = list.filter((x) => x.status === "rejected").reverse();
    const rej = (x) => `<div class="look-line no"><span class="look-no" aria-hidden="true">✕</span><span class="lo-main"><b>${esc(x.name)}</b>
        <small>${x.reason ? `${esc(x.reason)}・` : ""}${o.price | 0} 元寶已退</small></span>
        ${o.open ? "" : `<button class="btn small ghost" data-act="look-redo" data-id="${x.id | 0}">改一改再送</button>`}</div>`;
    const rejs = rejected.length ? `<div class="mall-sub">退回的<small>${rejected.length} 張</small></div><div class="look-lines">${rejected.slice(0, S.lookRejAll ? rejected.length : 1).map(rej).join("")}
        ${rejected.length > 1 && !S.lookRejAll ? `<button class="look-fold" data-act="look-fold" data-what="rej">看更早的 ${rejected.length - 1} 張 ▾</button>` : ""}</div>` : "";
    return `${drawing ? `<div class="mall-sub">正在畫<small>一次一張</small></div><div class="look-lines">${drawing}</div>` : ""}${form}
      ${lookSellHtml(d && d.market, list.filter((x) => x.status === "made"))}${rejs}`;
  }
  // 市集上架：做好的那幾套一行一套，掛著的排前面、沒掛的摺起來；按「掛上去」那一行才跳出定價框
  function lookSellHtml(m, made) {
    if (!m || !made.length) return "";
    const price = (look) => ((m.mine || []).find((one) => one.look === look) || {}).price;
    const rows = made.map((x) => ({ x, look: `u${x.id | 0}`, p: price(`u${x.id | 0}`) })); // 自建的一套就是 u<購買 id>（orders.look_id）
    const on = rows.filter((r) => r.p != null), off = rows.filter((r) => r.p == null);
    const pct = Math.round((m.share || 0) * 100);
    const row = (r) => `<div class="look-line"><span class="look-pad">${lookFaceHtml(r.look)}</span><span class="lo-main"><b>${esc(r.x.name)}</b>
        <small>${r.p != null ? `掛著・一份 ${r.p | 0}` : "沒掛"}</small></span>
        ${r.p != null ? `<button class="btn small ghost" data-act="market-unlist" data-id="${esc(r.look)}">撤下</button>`
          : S.lookSell === r.look ? "" : `<button class="btn small" data-act="look-sell" data-id="${esc(r.look)}">掛上去</button>`}
        ${S.lookSell === r.look && r.p == null ? `<span class="market-set"><label for="market-price-${esc(r.look)}">定價</label>
          <input class="input" type="number" id="market-price-${esc(r.look)}" min="${m.min | 0}" max="${m.max | 0}" value="${m.default | 0}">
          <button class="btn small primary" data-act="market-list" data-id="${esc(r.look)}">掛上去</button></span>` : ""}</div>`;
    const shown = S.lookSellAll ? rows : on.concat(off.filter((r) => r.look === S.lookSell));
    const folded = off.length - (S.lookSellAll ? off.length : off.filter((r) => r.look === S.lookSell).length);
    return `<div class="mall-sub">市集上架<small>${made.length} 套做好的・${on.length} 套掛著</small></div>
      <div class="look-stats"><span><small>賣出</small><b>${m.sold | 0} 份</b></span><span><small>已入帳</small><b>${m.paid | 0}</b></span><span><small>押著</small><b>${m.held | 0}</b></span></div>
      <div class="look-lines">${(S.lookSellAll ? on.concat(off) : shown).map(row).join("")}
        ${folded > 0 ? `<button class="look-fold" data-act="look-fold" data-what="sell">還有 ${folded} 套沒掛　展開 ▾</button>` : ""}</div>
      <p class="mall-note">${m.min | 0}～${m.max | 0} 元寶。賣出一份你拿 ${pct}%，押 ${m.hold_days | 0} 天才入帳。</p>`;
  }
  // 撤回自己還沒上架的單（Joy 2026-11-02「審圖卡住，玩家也不能退回，會被卡死」）：等圖、審核中都能撤，元寶全退；先問一次
  const withdrawBtn = (x, kind, name) => (x.withdraw
    ? `<button class="btn small ghost" data-act="look-withdraw" data-kind="${kind}" data-id="${x.id | 0}" data-name="${esc(name)}">撤回</button>` : "");
  function lookWithdrawAsk(el) {
    const kind = el.dataset.kind === "move" ? "move" : "look", id = Number(el.dataset.id) || 0;
    ask(`撤回「${el.dataset.name || ""}」？元寶全退，已經畫好的圖不留。`, "撤回", () => lookWithdraw(id, kind));
  }
  async function lookWithdraw(id, kind) {
    await busy(async () => {
      const r = await api("/api/looks/withdraw", { id, kind });
      if (r.looks) S.mallLooks = r.looks;
      if (r.main) setMain(r.main);
      if (r.main && r.main.mall && S.mallData) S.mallData.balance = r.main.mall.balance;
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      S.mallSay = text ? { text, ok: !text.startsWith("（") } : null;
      renderTop();
      if (S.mallOpen) renderMall();
    });
  }
  function lookOrderAsk() {
    const name = (document.getElementById("look-name")?.value || "").trim();
    const prompt = (document.getElementById("look-prompt")?.value || "").trim();
    S.lookDraft = { name, prompt };
    if (!name || !prompt) { S.mallSay = { text: !name ? "先替這一套取個名字。" : "寫一句這一套長什麼樣子。", ok: false }; renderMall(); return; }
    const o = S.mallLooks && S.mallLooks.order;
    const ref = mallRef();
    ask(`花 ${o ? o.price | 0 : 0} 元寶下單自建形象「${name}」？審核沒過元寶全退。`, "下單", () => lookOrder(name, prompt, ref));
  }
  async function lookOrder(name, prompt, ref) {
    await busy(async () => {
      const r = await api("/api/looks/order", { name, prompt, ref });
      if (r.looks) S.mallLooks = r.looks;
      if (r.main) setMain(r.main);
      if (r.main && r.main.mall && S.mallData) S.mallData.balance = r.main.mall.balance; // 招牌旁的餘額照貨架那一份：當場換
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      const ok = !!(r.looks && r.looks.order && r.looks.order.open);
      if (ok) S.lookDraft = null;
      S.mallSay = text ? { text, ok } : null;
      renderTop();
      if (S.mallOpen) renderMall();
    });
  }
  // 招式動畫（第三批；Joy 2026-11-03 要完整流程、要裝得下很多，示意稿「絕招」）：最上面現在練哪一門、什麼打法、身上穿哪一招；
  // 正在畫的獨門一條（撤得回來）；招式庫照打法分頁（先開現在的打法），一招一行（演一次、換上／穿著）；「寫一招新的」平常收著
  // （招式庫空的就直接展開）：寫一句 → 先看看（伺服器把這一句變成導演稿，畫布照稿演，不扣元寶）→ 通用或獨門。
  // 每一季綁到一門武功上（同打法免費改綁）；擂台上出招時疊那一張光效。範例那一格是 /static/img/arena/fx_sample.webp 的第四格
  const MOVE_IMG = (id) => (/^m\d+$/.test(id || "") ? `/api/looks/img/${id}/fx${LOOK_VER()}` : "/static/img/arena/fx_sample.webp");
  const MOVE_STYLES = [["slash", "揮砍"], ["pole", "長兵"], ["fist", "拳腳"], ["shoot", "射"]];
  function moveFxHtml(id) { return `<span class="move-fx" aria-hidden="true" style="background-image:url('${MOVE_IMG(id)}')"></span>`; }
  function moveHtml(m) {
    if (!m) return "";
    const lib = m.library || [];
    const wornRow = lib.find((x) => x.worn);
    const now = !m.has_art ? `<p class="mall-note">先練一門自己合成或自創的武功，才能替它畫招式。</p>`
      : `<div class="move-now-card"><span><small>現在練的</small><b>${esc(m.art)}<em>・打法 ${esc(m.style_text)}</em></b><small>${m.worn ? `身上穿著「${esc(m.worn)}」` : "身上沒穿絕招"}</small></span>
          ${wornRow && wornRow.scene ? `<button class="btn small ghost" data-act="move-show" data-id="${esc(wornRow.move)}">${S.moveShow === wornRow.move ? "收起" : "演一次 ▶"}</button>` : ""}</div>`
        + (m.asleep_text ? `<p class="mall-note bad">${esc(m.asleep_text)}</p>` : "");
    const pending = (m.list || []).map((x) => `<div class="look-line ${x.status === "rejected" ? "no" : "wait"}">${x.status === "rejected" ? '<span class="look-no" aria-hidden="true">✕</span>' : waitIcon}
        <span class="lo-main"><b>${esc(x.prompt)}</b><small>${esc(x.art)}・${esc(x.style_text)}${moveArtsNote(x)}${x.reason ? `（${esc(x.reason)}）` : ""}</small></span>
        <span class="look-st st-${esc(x.status)}">${esc(x.status_text)}</span>${withdrawBtn(x, "move", x.art)}</div>`).join("");
    const show = S.moveShow ? `<canvas id="scene-preview" class="scene-preview" width="720" height="320" aria-label="絕招演一次"></canvas>` : "";
    // 招式庫：照打法分頁，先開現在的打法（沒有就開第一個有招的）；別的打法那一頁寫一句這一季演不出來
    const tabs = MOVE_STYLES.map(([k, name]) => [k, name, lib.filter((x) => x.style === k).length]);
    const tab = tabs.some(([k]) => k === S.moveTab) ? S.moveTab : (tabs.find(([k, , n]) => k === m.style && n) || tabs.find(([, , n]) => n) || [m.style])[0];
    const row = (x) => `<div class="look-line move-line${x.worn ? " on" : ""}"><span class="look-pad">${x.scene ? `<span class="move-fx move-seal" aria-hidden="true">絕</span>` : moveFxHtml(x.move)}</span>
        <span class="lo-main"><b>${esc(x.prompt)}</b><small>${esc(x.art)}</small></span>
        ${x.scene ? `<button class="btn small ghost play" data-act="move-show" data-id="${esc(x.move)}" aria-label="${S.moveShow === x.move ? "收起" : "演一次"}">${S.moveShow === x.move ? "■" : "▶"}</button>` : "<span></span>"}
        ${x.worn ? `<button class="btn small ghost" data-act="move-bind" data-id="0">脫下</button>`
          : x.wearable ? `<button class="btn small primary" data-act="move-bind" data-id="${x.id | 0}">換上</button>` : "<span></span>"}</div>`;
    const inTab = lib.filter((x) => x.style === tab);
    const library = lib.length ? `<div class="mall-sub">招式庫<small>共 ${lib.length} 招・換季也帶著走</small></div>
      <div class="look-segs" role="tablist">${tabs.map(([k, name, n]) => `<button class="${tab === k ? "on" : ""}" role="tab" aria-selected="${tab === k}" data-act="move-tab" data-tab="${k}">${name} ${n}</button>`).join("")}</div>
      ${tab !== m.style && m.has_art ? `<p class="mall-note">這一頁的招，這一季換回${esc((MOVE_STYLES.find(([k]) => k === tab) || [, ""])[1])}的兵器才演得出來。</p>` : ""}
      ${show}<div class="look-lines">${inTab.map(row).join("") || `<p class="mall-note">這一種打法還沒有招。</p>`}</div>` : show;
    // 寫一招新的：平常收著（招式庫空的直接展開）。獨門一次只能有一張在做（畫坊的量），那一格暫時灰掉，通用照樣買得到
    const formOpen = S.moveForm || !lib.length;
    const own = m.open ? `<span class="move-opt off"><b>獨門</b><small>還有一張獨門在畫：等它好了、或撤回，才能再下一張。</small></span>`
      : `<span class="move-opt own"><b>獨門</b><small>照你寫的另外畫，畫好審過才上身；沒過全退。</small>
          <button class="btn small primary buy" data-act="move-order">${ingotSvg()}${m.price | 0}</button></span>`;
    const form = !m.has_art || S.moveShow ? "" : !formOpen ? `<button class="btn primary buy move-new" data-act="move-form">＋ 寫一招新的</button>`
      : `<div class="move-form"><div class="mall-sub">寫一句<small>${m.prompt_max | 0} 字內・只能中文</small></div>
      <div class="look-order-form"><label for="move-prompt">這一招長什麼樣子</label><textarea class="input" id="move-prompt" maxlength="${m.prompt_max | 0}" rows="2">${esc(S.moveDraft || "")}</textarea>
        ${exampleHtml(MOVE_EXAMPLES, "move-prompt")}
        <button class="btn ghost" data-act="move-preview">先看看 ▶（不花錢）</button></div>${moveSceneHtml()}
      <div class="move-opts"><span class="move-opt"><b>通用</b><small>用現成的光效演，當場學成。</small>
          <button class="btn small buy" data-act="move-order" data-basic="1">${ingotSvg()}${m.price_basic | 0}</button></span>${own}</div>
      <p class="mall-note">${esc(m.order_style_note || "")}</p></div>`;
    return `${now}${pending ? `<div class="look-lines">${pending}</div>` : ""}${library}${form}`;
  }
  const moveArtsNote = (row) => { const need = row.arts || []; return need.length ? `・要畫「${esc(need.join("」「"))}」` : ""; }; // 一句話自創要畫的那幾樣
  // 先看看：伺服器把這一句變成導演稿（不扣元寶），在下面那塊畫布照稿演（arena_scene.js 的 scenePreview）
  function moveSceneHtml() {
    const p = S.movePreview;
    if (!p) return "";
    if (p.problem) return `<p class="mall-note bad">${esc(p.problem)}</p>`;
    const arts = (p.scene.arts || []).map((a) => a.label);
    const note = arts.length
      ? `獨門會畫「${arts.join("」「")}」：送出之後可以先去忙，畫好、審過才上身（這裡先用剪影演）。買通用的話這一樣改成一道光。`
      : "這一句沒有看得出形狀的東西：買通用的就好（獨門會退回來叫你換一句）。";
    return `<canvas id="scene-preview" class="scene-preview" width="720" height="320" aria-label="絕招預覽"></canvas><p class="mall-note">${esc(note)}</p>`;
  }
  // 預覽台上站的是自己（Joy 11/5 例句影片驗出來：以前一律是斗笠小子）：穿的那一套、拿那一種打法的兵器。
  // 擂台開打時 arena_anim 會照那一場重設。俠客頁武學卡的「演一次」也叫它（app.js heroMoveShow）
  function sceneAsMe(style) {
    const look = (S.main && S.main.look) || "";
    const kind = { slash: "劍", pole: "槍", fist: "拳腳", shoot: "弓弩" }[style || ""] || "";
    if (typeof RA !== "undefined") RA.looks = { ...RA.looks, me: kind, me_look: look };
    if (typeof ringLoad === "function") ringLoad();
    if (look && typeof ringWarmLook === "function") ringWarmLook(look);
  }
  const looksMoves = () => (S.mallLooks && S.mallLooks.moves) || null;
  // 招式庫裡做好了的那一招：照它的稿和畫好的圖演一次（同擂台；再按一次收起，回到下單的表單）
  async function moveShowTo(mid) {
    if (!mid || S.moveShow === mid) { S.moveShow = null; if (S.mallOpen) renderMall(); return; }
    const r = await api(`/api/looks/scene/${mid}`);
    if (!r || !r.scene) { S.mallSay = { text: "這一招演不出來，等一下再試。", ok: false }; if (S.mallOpen) renderMall(); return; }
    S.moveShow = mid; S.movePreview = null;
    if (S.mallOpen) renderMall();
    const row = ((looksMoves() || {}).library || []).find((x) => x.move === mid);
    sceneAsMe(row ? row.style : (looksMoves() || {}).style);
    if (typeof scenePreview === "function") scenePreview(r.scene, mid);
  }
  async function movePreview() {
    const text = (document.getElementById("move-prompt")?.value || "").trim();
    S.moveDraft = text;
    const r = await api("/api/looks/scene", { text });
    S.movePreview = r && (r.scene || r.problem) ? r : { problem: "預覽不出來，等一下再試。" };
    // 預覽那一份要記住、下單時原樣帶回去（看到的＝做出來的）：不然伺服器會再問一次模型，
    // 兩次答案不同，玩家核准的跟真的畫出來的就不是同一份（#493：預覽說槍＋菊花，結果兩把槍）
    S.moveShown = r && r.draft ? { text, draft: r.draft } : null;
    if (S.mallOpen) renderMall();
    if (S.movePreview.scene) sceneAsMe((looksMoves() || {}).style);
    if (S.movePreview.scene && typeof scenePreview === "function") scenePreview(S.movePreview.scene);
  }
  function moveOrderAsk(basic) {
    const prompt = (document.getElementById("move-prompt")?.value || "").trim();
    S.moveDraft = prompt;
    const m = S.mallLooks && S.mallLooks.moves;
    if (!prompt) { S.mallSay = { text: "寫一句這一招長什麼樣子。", ok: false }; renderMall(); return; }
    const ref = mallRef();
    const price = (basic ? (m ? m.price_basic : 0) : (m ? m.price : 0)) | 0;
    const tail = basic ? "用現成的光效，當場學成。" : "照你寫的東西畫一張圖，送出之後可以先去忙；審核沒過元寶全退。";
    ask(`花 ${price} 元寶替「${m ? m.art : ""}」下單${basic ? "通用" : "獨門"}絕招？${tail}`, "下單", () => moveOrder(prompt, ref, basic));
  }
  async function moveOrder(prompt, ref, basic) {
    await busy(async () => {
      // 帶上預覽那一份（只有那一句一字沒改才算同一份；改過就讓伺服器重新問，不要拿舊的充數）
      const shown = S.moveShown && S.moveShown.text === prompt ? S.moveShown.draft : null;
      const r = await api("/api/looks/move", { prompt, ref, basic: !!basic, draft: shown });
      if (r.looks) S.mallLooks = r.looks;
      if (r.main) setMain(r.main);
      if (r.main && r.main.mall && S.mallData) S.mallData.balance = r.main.mall.balance;
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      const mv = r.looks && r.looks.moves;
      const ok = !!(mv && (mv.open || mv.bound)); // 要畫的在等圖、不用畫的當場學成（綁上了）
      if (ok) { S.moveDraft = null; S.movePreview = null; S.moveShown = null; }
      S.mallSay = text ? { text, ok } : null;
      renderTop();
      if (S.mallOpen) renderMall();
    });
  }
  async function moveBind(id) {
    await busy(async () => {
      const r = await api("/api/looks/bind", { id: Number(id) });
      if (r.looks) S.mallLooks = r.looks;
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      S.mallSay = text ? { text, ok: text.startsWith("換上") || text.startsWith("把「") } : null;
      if (S.mallOpen) renderMall();
    });
  }
  function lookMarketAsk(look, name, price) {
    const ref = mallRef();
    ask(`花 ${price | 0} 元寶買下市集上的「${name}」？`, "買", () => lookMarketDo({ op: "buy", look, ref }));
  }
  async function lookMarketList(look) { // 價錢照框裡寫的；讀不到框就照預設的
    const m = (S.mallLooks && S.mallLooks.market) || {};
    const price = Number((document.getElementById(`market-price-${look}`) || {}).value) || m.default || 0;
    await lookMarketDo({ op: "list", look, price });
  }
  async function lookMarketDo(body) {
    await busy(async () => {
      const r = await api("/api/looks/market", body);
      if (r.looks) S.mallLooks = r.looks;
      S.lookSell = null;
      if (r.main) setMain(r.main);
      if (r.main && r.main.mall && S.mallData) S.mallData.balance = r.main.mall.balance;
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      S.mallSay = text ? { text, ok: /^(買下了|「)/.test(text) } : null;
      renderTop();
      if (S.mallOpen) renderMall();
    });
  }
  async function loadLooks() {
    try {
      S.mallLooks = await api("/api/looks");
      S.mallFail = false;
    } catch (e) { S.mallFail = true; }
    if (S.mallOpen && S.mallTab === "look") renderMall();
  }
  async function lookWear(id) {
    await busy(async () => {
      const r = await api("/api/looks/wear", { look: id });
      if (r.looks) S.mallLooks = r.looks;
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      S.mallSay = text ? { text, ok: true } : null;
      if (S.mallOpen) renderMall();
    });
  }

  // 從別的頁直接進萬寶閣的絕招那一頁（俠客頁武學卡「去綁招」）：style 給了就開那一種打法的招式庫分頁（slash/pole/fist/shoot）
  async function openMallMoves(style) {
    if (!S.main || !S.main.mall) return;
    S.mallOpen = true; S.mallTab = "look"; S.mallSay = null; S.mallPick = null; S.mallLog = null; S.mallFail = false;
    lookReset(); S.lookSub = "move"; S.lookShow = null; S.moveShow = null;
    if (MOVE_STYLES.some(([k]) => k === style)) S.moveTab = style;
    render();
    await Promise.all([loadMall(), loadLooks()]);
  }
  // 形象那一頁裡的自建形象、絕招那一頁（空字串回形象）：換頁時收起正在演的、從頂上開始
  function lookSubTo(sub) {
    S.lookSub = LOOKSUB_NAMES[sub] ? sub : "";
    S.lookShow = null; S.moveShow = null; S.mallSay = null;
    renderMall(false);
  }
  // 形象那一頁自己記的：點了哪一套、在哪一頁、篩哪一類、看了幾格、展開了什麼（換帳號、出店都清掉）
  function lookReset() {
    S.lookPick = null; S.lookSeg = "mine"; S.lookFilter = "all"; S.lookLimit = 0; S.lookSell = null; S.lookSellAll = false; S.lookRejAll = false;
    S.moveTab = null; S.moveForm = false;
  }
  function lookPickTo(id) { S.lookPick = id; S.lookShow = null; renderMall(); }
  function lookSegTo(seg) { S.lookSeg = seg; S.lookLimit = 0; S.lookShow = null; renderMall(); }
  function lookFilterTo(f) { S.lookFilter = f; S.lookLimit = 0; renderMall(); }
  function lookMore() { S.lookLimit = Math.max(LOOK_PAGE, S.lookLimit | 0) + LOOK_PAGE; renderMall(); }
  function lookFold(what) { if (what === "rej") S.lookRejAll = true; else S.lookSellAll = true; renderMall(); }
  function lookSellTo(look) { S.lookSell = S.lookSell === look ? null : look; renderMall(); }
  function moveTabTo(tab) { S.moveTab = tab; S.moveShow = null; renderMall(); }
  function moveFormOpen() { S.moveForm = true; renderMall(); }
  // 退回的那一張「改一改再送」：名字、樣子填回寫一套的框
  function lookRedo(id) {
    const o = S.mallLooks && S.mallLooks.order;
    const x = o && (o.list || []).find((one) => (one.id | 0) === (Number(id) | 0));
    if (x) S.lookDraft = { name: x.name, prompt: x.prompt };
    renderMall(false);
  }
  // 「想不到就點」：把那一句填進框裡（自建形象、絕招各一個框），草稿跟著記，重畫也還在
  function promptExample(target, text) {
    const box = document.getElementById(target);
    if (box) box.value = text;
    if (target === "move-prompt") S.moveDraft = text;
    else if (target === "look-prompt") S.lookDraft = { name: (document.getElementById("look-name")?.value || "").trim(), prompt: text };
  }

  // 管理者區「自建形象」（第二批）：還沒做完的訂單一張一格——下單的人、名字、樣子、十張到了幾張、給生圖工具的提示詞（展開才看）、
  // 上傳（一次選好幾張，檔名照十張的名字：hero_bare_idle.png……）、上架、退回（原因寫給下單的人看）。按「看訂單」才抓
  function looksAdminHtml() {
    const d = S.adLooks;
    const auto = S.adLooks && S.adLooks.gen === "api" ? "畫坊自動畫、自動審，畫好的會自己出現；" : "";
    const head = `<p class="muted">自建形象（玩家下的單：${auto}也可以照提示詞生圖、切成 220 格〔scripts/cut_look.py〕再上傳；十張齊了看過再上架）</p>
      <div class="row wrap"><button class="btn small" data-act="looks-admin" data-op="load">看訂單</button></div>
      <p class="form-msg${S.adLooksOk ? " ok" : ""}" role="alert">${esc(S.adLooksMsg || "")}</p>`;
    if (!d) return head;
    // 畫坊（run_studio.py）：自動畫了幾張；畫不好停手時寫原因、給一顆「再畫一次」
    const studio = (x) => !x.studio || (!x.studio.painted && !x.studio.failed) ? "" : `<p class="muted">畫坊：畫了 ${x.studio.painted | 0} 張${x.studio.failed ? `・停手了：${esc(x.studio.failed)}` : ""}</p>`
      + (x.studio.failed && (x.status === "pending") ? `<div class="row wrap"><button class="btn small" data-act="looks-admin" data-op="studio-retry" data-id="${x.id | 0}">再畫一次</button></div>` : "");
    const row = (o) => {
      const have = new Set(o.have || []);
      const sheets = Object.keys(d.sheets || {});
      const faces = sheets.map((s) => `<span class="${have.has(s) ? "ok" : ""}">${esc(s.replace("hero_", ""))}</span>`).join("");
      const prompts = Object.entries(o.prompts || {}).map(([s, text]) => `<details><summary>${esc(s)}</summary><pre class="look-gen">${esc(text)}</pre></details>`).join("");
      // 到了的那幾張畫成縮圖（點了開原圖）：上架前看得到畫成什麼樣子（管理頁獨立，Joy 2026-11-01）。網址帶抓訂單那一刻，重傳過的不吃舊快取
      const thumbs = o.look && have.size ? `<div class="look-thumbs">${sheets.filter((s) => have.has(s)).map((s) => {
        const src = `/api/looks/img/${encodeURIComponent(o.look)}/${encodeURIComponent(s)}?v=${S.adLooksAt | 0}`;
        return `<a href="${src}" target="_blank" rel="noopener" title="${esc(s)}"><img loading="lazy" src="${src}" alt="${esc(s)}"></a>`;
      }).join("")}</div>` : "";
      return `<div class="card look-admin"><b>#${o.id | 0}「${esc(o.name)}」</b>・${esc(o.owner)}・${esc(o.status_text)}${o.reason ? `（${esc(o.reason)}）` : ""}
        <p>${esc(o.prompt)}</p>${thumbs}${studio(o)}${o.prompts && Object.keys(o.prompts).length ? `<div class="look-sheets">${faces}</div>${prompts}
        <div class="row wrap"><input type="file" id="ad-looks-file-${o.id | 0}" accept="image/png,image/webp" multiple aria-label="上傳十張">
        <button class="btn small" data-act="looks-admin" data-op="upload" data-id="${o.id | 0}">上傳</button>
        <button class="btn small primary" data-act="looks-admin" data-op="release" data-id="${o.id | 0}" ${have.size === sheets.length ? "" : "disabled"}>上架</button></div>
        <div class="row"><input class="input" id="ad-looks-note-${o.id | 0}" placeholder="退回的原因（必填）" maxlength="100"><button class="btn warn small" data-act="looks-admin" data-op="reject" data-id="${o.id | 0}">退回</button></div>` : ""}</div>`;
    };
    // 一句話自創的絕招：導演稿要畫的那一兩樣（法相、巨物）一樣一格——提示詞、選一張上傳；到齊了才按得下上架
    const srow = (m) => `<div class="card look-admin"><b>#${m.id | 0}「${esc(m.art)}」</b>・${esc(m.style_text)}・${esc(m.owner)}・${esc(m.status_text)}${m.reason ? `（${esc(m.reason)}）` : ""}
        <p>${esc(m.prompt)}</p>${moveThumbs(m, (m.arts || []).filter((a) => a.have).map((a) => a.slot))}${studio(m)}${(m.arts || []).some((a) => a.prompt) ? (m.arts || []).map((a) => `<div class="look-sheets"><span class="${a.have ? "ok" : ""}">${esc(a.slot)}・${esc(a.label)}</span></div>
        <details><summary>提示詞</summary><pre class="look-gen">${esc(a.prompt)}</pre></details>
        <div class="row wrap"><input type="file" id="ad-moves-file-${m.id | 0}-${esc(a.slot)}" accept="image/png,image/webp" aria-label="上傳${esc(a.label)}">
        <button class="btn small" data-act="looks-admin" data-op="move-upload" data-id="${m.id | 0}" data-slot="${esc(a.slot)}">上傳</button></div>`).join("")
        + `<div class="row wrap"><button class="btn small primary" data-act="looks-admin" data-op="move-release" data-id="${m.id | 0}" ${m.have ? "" : "disabled"}>上架</button></div>
        <div class="row"><input class="input" id="ad-moves-note-${m.id | 0}" placeholder="退回的原因（必填）" maxlength="100"><button class="btn warn small" data-act="looks-admin" data-op="move-reject" data-id="${m.id | 0}">退回</button></div>` : ""}</div>`;
    const moveThumbs = (m, slots) => m.move && slots.length ? `<div class="look-thumbs">${slots.map((slot) => {
      const src = `/api/looks/img/${encodeURIComponent(m.move)}/${encodeURIComponent(slot)}?v=${S.adLooksAt | 0}`;
      return `<a href="${src}" target="_blank" rel="noopener" title="${esc(slot)}"><img loading="lazy" src="${src}" alt="${esc(slot)}"></a>`;
    }).join("")}</div>` : "";
    const mv = d.moves, mrow = (m) => m.scene ? srow(m) : `<div class="card look-admin"><b>#${m.id | 0}「${esc(m.art)}」</b>・${esc(m.style_text)}・${esc(m.owner)}・${esc(m.status_text)}${m.reason ? `（${esc(m.reason)}）` : ""}
        <p>${esc(m.prompt)}</p>${moveThumbs(m, m.have ? ["fx"] : [])}${m.gen_prompt ? `<div class="look-sheets"><span class="${m.have ? "ok" : ""}">fx</span></div>
        <details><summary>提示詞</summary><pre class="look-gen">${esc(m.gen_prompt)}</pre></details>
        <div class="row wrap"><input type="file" id="ad-moves-file-${m.id | 0}" accept="image/png,image/webp" aria-label="上傳光效">
        <button class="btn small" data-act="looks-admin" data-op="move-upload" data-id="${m.id | 0}">上傳</button>
        <button class="btn small primary" data-act="looks-admin" data-op="move-release" data-id="${m.id | 0}" ${m.have ? "" : "disabled"}>上架</button></div>
        <div class="row"><input class="input" id="ad-moves-note-${m.id | 0}" placeholder="退回的原因（必填）" maxlength="100"><button class="btn warn small" data-act="looks-admin" data-op="move-reject" data-id="${m.id | 0}">退回</button></div>` : ""}</div>`;
    const moves = !mv ? "" : `<p class="muted">絕招（一句話自創的：法相、巨物一樣一張去背圖，邊長最多 1024；舊的光效單一張 ${esc(mv.size)}、六格、透明底）</p>`
      + (mv.open.length ? mv.open.map(mrow).join("") : `<p class="muted">沒有等著做的招式。</p>`) + mv.done.map(mrow).join("");
    return head + (d.open.length ? d.open.map(row).join("") : `<p class="muted">沒有等著做的訂單。</p>`)
      + d.done.map(row).join("") + moves + galleryHtml(d.gallery);
  }
  // 全服成品動畫牆（企劃者 2026-11-03「我是管理員，我需要能看到所有玩家做的成品動畫」）：
  // 只列已上架的（零件到齊才演得出來），點了在上面那塊畫布演。播放器是現成的兩支（arena_scene.js）：
  // 形象用 lookShow（十六張一張一張演，畫布 id 要 look-show），招式用 scenePreview（照導演稿演，畫布 id 要 scene-preview）。
  function galleryHtml(g) {
    if (!g || (!(g.looks || []).length && !(g.moves || []).length)) return `<p class="muted">全服還沒有已上架的成品。</p>`;
    const stage = S.adShow && S.adShow.kind === "look"
      ? `<canvas id="look-show" class="look-show" width="${typeof RING_W === "number" ? RING_W : 720}" height="${typeof RING_H === "number" ? RING_H : 320}" aria-label="形象動作"></canvas>`
      : S.adShow && S.adShow.kind === "move"
        ? `<canvas id="scene-preview" class="scene-preview" width="720" height="320" aria-label="絕招動畫"></canvas>` : "";
    const on = (kind, id) => S.adShow && S.adShow.kind === kind && String(S.adShow.id) === String(id);
    const btn = (kind, id, label, who) => `<button class="btn small ${on(kind, id) ? "primary" : "ghost"}"
        data-act="ad-show" data-kind="${kind}" data-id="${esc(id)}">${esc(label)}<small>・${esc(who)}</small></button>`;
    const looks = (g.looks || []).map((x) => btn("look", x.look, x.name || x.look, x.owner)).join("");
    const mvs = (g.moves || []).map((x) => btn("move", x.move, x.name || x.move, x.owner)).join("");
    return `<p class="muted">全服成品（已上架）：形象 ${(g.looks || []).length} 套、絕招 ${(g.moves || []).length} 招。點一個就在這裡演。</p>
      ${S.adShow ? `<div class="hm-stage">${stage}</div>` : ""}
      ${looks ? `<div class="row wrap">${looks}</div>` : ""}
      ${mvs ? `<div class="row wrap">${mvs}</div>` : ""}`;
  }
  // 點一個成品：再點同一個就收起。形象直接演；招式要先抓它的導演稿（/api/looks/scene/<m…>，上架了的才有）
  async function adShow(kind, id) {
    if (!id || (S.adShow && S.adShow.kind === kind && String(S.adShow.id) === String(id))) {
      S.adShow = null; if (typeof renderAdmin === "function") renderAdmin(); return;
    }
    if (kind === "move") {
      const r = await api(`/api/looks/scene/${id}`).catch(() => null);
      if (!r || !r.scene) { S.adLooksMsg = "這一招演不出來，等一下再試。"; S.adLooksOk = false; if (typeof renderAdmin === "function") renderAdmin(); return; }
      S.adShow = { kind, id, scene: r.scene };
      if (typeof renderAdmin === "function") renderAdmin();
      if (typeof scenePreview === "function") scenePreview(r.scene, id);
      return;
    }
    S.adShow = { kind, id };
    if (typeof renderAdmin === "function") renderAdmin();
    if (typeof lookShow === "function") lookShow(id);
  }
  // 上架、退回先問一次（以前按了就送；退回會把元寶全退給下單的人）。退回沒寫原因照舊由伺服器回那一句，不必問
  function looksAdminAsk(op, id, slot) {
    const d = S.adLooks || {};
    const move = op.startsWith("move-");
    const list = move ? [...((d.moves && d.moves.open) || []), ...((d.moves && d.moves.done) || [])] : [...(d.open || []), ...(d.done || [])];
    const x = list.find((o) => String(o.id) === String(id));
    const what = x ? `#${x.id | 0}「${move ? x.art : x.name}」（${x.owner}）` : `#${id}`;
    const note = (document.getElementById(`ad-${move ? "moves" : "looks"}-note-${id}`)?.value || "").trim();
    if ((op === "release" || op === "move-release") && x) {
      ask(`上架${what}：${move ? "這一招的動畫照現在這幾張圖演" : "十張照現在這樣，下單的人就能換上"}，確定？`, "確定上架", () => looksAdminDo(op, id, slot));
      return;
    }
    if ((op === "reject" || op === "move-reject") && x && note) {
      ask(`退回${what}（原因：${note}）：元寶全退給下單的人、原因寫給他看，這一張單就結了，確定？`, "確定退回", () => looksAdminDo(op, id, slot));
      return;
    }
    return looksAdminDo(op, id, slot);
  }
  async function looksAdminDo(op, id, slot) {
    const done = async (r) => {
      const text = (r && r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      S.adLooksMsg = text; S.adLooksOk = !!text && !text.startsWith("（");
    };
    await busy(async () => {
      if (op === "upload") {
        const input = document.getElementById(`ad-looks-file-${id}`);
        const files = Array.from((input && input.files) || []);
        if (!files.length) { S.adLooksMsg = "先選圖（檔名照十張的名字）。"; S.adLooksOk = false; }
        const said = [];
        for (const f of files) {
          const data = await new Promise((ok, no) => { const fr = new FileReader(); fr.onload = () => ok(String(fr.result).split(",")[1] || ""); fr.onerror = no; fr.readAsDataURL(f); });
          const r = await api("/api/do/looks_upload", { id: Number(id), sheet: f.name.replace(/\.[^.]+$/, ""), data });
          said.push((r.message || "").replace(/<[^>]+>/g, " ").trim());
        }
        if (said.length) { S.adLooksMsg = said[said.length - 1]; S.adLooksOk = !said.some((t) => t.startsWith("（")); if (!S.adLooksOk) S.adLooksMsg = said.filter((t) => t.startsWith("（")).join(" "); }
      } else if (op === "move-upload") {
        const f = ((document.getElementById(slot ? `ad-moves-file-${id}-${slot}` : `ad-moves-file-${id}`) || {}).files || [])[0];
        if (!f) { S.adLooksMsg = "先選一張圖。"; S.adLooksOk = false; }
        else {
          const data = await new Promise((ok, no) => { const fr = new FileReader(); fr.onload = () => ok(String(fr.result).split(",")[1] || ""); fr.onerror = no; fr.readAsDataURL(f); });
          await done(await api("/api/do/moves_upload", { id: Number(id), data, ...(slot ? { sheet: slot } : {}) }));
        }
      } else if (op === "move-release") {
        await done(await api("/api/do/moves_release", { id: Number(id) }));
      } else if (op === "move-reject") {
        const note = (document.getElementById(`ad-moves-note-${id}`)?.value || "").trim();
        await done(await api("/api/do/moves_reject", { id: Number(id), note }));
      } else if (op === "studio-retry") {
        await done(await api("/api/do/looks_studio_retry", { id: Number(id) }));
      } else if (op === "release") {
        await done(await api("/api/do/looks_release", { id: Number(id) }));
      } else if (op === "reject") {
        const note = (document.getElementById(`ad-looks-note-${id}`)?.value || "").trim();
        await done(await api("/api/do/looks_reject", { id: Number(id), note }));
      }
      S.adLooks = await api("/api/admin/looks");
      S.adLooksAt = Math.floor(Date.now() / 1000);
      if (S.adminPage && op !== "load" && S.adLooksMsg) S.adResult = { text: S.adLooksMsg, ok: !!S.adLooksOk }; // 管理頁：結果也釘在底下
      renderKeepingSheet();
    });
  }

  async function looksClick(act, el, ev) {
    switch (act) {
        case "mall-moves": await openMallMoves(el.dataset.style || ""); break; // 直接進萬寶閣的絕招那一頁（data-style 開那一種打法）
        case "look-sub": lookSubTo(el.dataset.sub || ""); break; // 形象那一頁裡的自建形象、絕招那一頁（空的回形象）
        case "prompt-ex-more": moveExMore(); break; // 絕招例句換下一批三句
        case "prompt-ex": promptExample(el.dataset.for || "", el.dataset.text || ""); break; // 想不到就點：把例句填進框裡
        case "look-pick": lookPickTo(el.dataset.id || ""); break; // 形象那一頁點一套：台子上換成它
        case "look-seg": lookSegTo(el.dataset.seg || "mine"); break; // 我的／官方／市集
        case "look-filter": lookFilterTo(el.dataset.filter || "all"); break; // 我的那一頁篩哪一類
        case "look-more": lookMore(); break; // 再看一頁
        case "look-fold": lookFold(el.dataset.what); break; // 摺起來的展開（沒掛的、更早退回的）
        case "look-sell": lookSellTo(el.dataset.id || ""); break; // 那一套跳出定價框
        case "look-redo": lookRedo(el.dataset.id); break; // 退回的改一改再送
        case "move-tab": moveTabTo(el.dataset.tab || ""); break; // 招式庫的打法分頁
        case "move-form": moveFormOpen(); break; // 寫一招新的（展開）
        case "look-wear": await lookWear(el.dataset.id || ""); break; // 萬寶閣「形象」那一頁換上一套
        case "look-order": lookOrderAsk(); break; // 自建形象下單（先問一次）
        case "look-withdraw": lookWithdrawAsk(el); break; // 撤回還沒上架的單（先問一次，元寶全退）
        case "move-order": moveOrderAsk(el.dataset.basic === "1"); break; // 絕招下單（先問一次）：通用 60 不畫圖、獨門 300 畫圖等審核
        case "move-preview": await movePreview(); break; // 一句話自創的絕招：先看看（不扣元寶）
        case "move-show": await moveShowTo(el.dataset.id || ""); break; // 招式庫做好了的那一招演一次
        case "look-show": lookShowTo(el.dataset.id || "", el.dataset.name || ""); break; // 一套形象看動作（再按一次收起）
        case "market-buy": lookMarketAsk(el.dataset.id, el.dataset.name || "", Number(el.dataset.price) || 0); break; // 形象市集買一套（先問一次）
        case "market-list": await lookMarketList(el.dataset.id); break; // 自己做的一套掛上市集（照框裡的價錢）
        case "market-unlist": await lookMarketDo({ op: "unlist", look: el.dataset.id }); break;
        case "move-bind": await moveBind(el.dataset.id); break; // 招式庫的一招換上身（id 0 是脫下來）
        case "looks-admin": await looksAdminAsk(el.dataset.op, el.dataset.id, el.dataset.slot); break; // 管理頁「自建形象」：上架、退回先問一次
        case "ad-show": await adShow(el.dataset.kind, el.dataset.id); break; // 管理頁的全服成品動畫牆：點一個就演（再點收起）
    } // looksClick
  } // looksClick
  registerClicks(looksClick, ["mall-moves", "look-sub", "prompt-ex-more", "prompt-ex", "look-pick", "look-seg", "look-filter", "look-more", "look-fold", "look-sell", "look-redo", "move-tab", "move-form", "look-wear", "look-order", "look-withdraw", "move-order", "move-preview", "move-show", "look-show", "market-buy", "market-list", "market-unlist", "move-bind", "looks-admin", "ad-show"]);
