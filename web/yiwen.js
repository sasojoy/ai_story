// 異聞（tianxia/features/yiwen）：撞見卡、每一幕、等說書人寫、收尾卡（第 248 批照企劃者挑的乙版「頁邊朱批」）。
// 資料是 /api/main 的 main.yiwen.card（伺服器不先跳脫，玩家的原話一律經 esc() 才進 HTML；模板句先換空格、再放跳脫好的字，不會再換第二次）。
// 江湖頁沒有給包的格（殼不長）：卡畫成蓋在頁面上的一整頁紙（#yw-pop），頁面重畫時照 main.yiwen 補上或拿掉；
// 收起時只在頁上留一條「進行中」的細條（.yw-track，江湖錄那一行後面或頁面最上面）。
// 畫法：yiwenCard（撞見卡、每一幕、收尾卡）、yiwenScene（一頁書）、yiwenWait（等說書人寫）、yiwenClose、yiwenTrack、ywSigns（路牌）。
// 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡；script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
"use strict";

  const YW_MARK_FIRST = "異聞"; // 待 joy 潤
  const YW_MARK_TRAIL = "舊腳印"; // 待 joy 潤
  const YW_MARK_DONE = "完"; // 待 joy 潤
  const YW_WALKERS = "已有 {n} 人走過"; // 待 joy 潤
  const YW_PLACE_LINE = "{place}・異聞"; // 待 joy 潤
  const YW_HD_FIRST = "你看那是什麼"; // 待 joy 潤
  const YW_HD_NEXT = "接著怎麼做"; // 待 joy 潤
  const YW_HD_TIP = "點一塊路牌就走"; // 待 joy 潤
  const YW_ACTS = ["第一幕", "第二幕", "第三幕"]; // 待 joy 潤
  const YW_WALKED_BY = "{who}走過"; // 待 joy 潤
  const YW_FOOT = "足跡"; // 待 joy 潤
  const YW_TYPED_BY = "{who}說的"; // 待 joy 潤
  const YW_CHIP_FREE = "免費開"; // 待 joy 潤
  const YW_CHIP_MINE = "寫下這一步"; // 待 joy 潤
  const YW_CHIP_INCENSE = "問路香 1"; // 待 joy 潤
  const YW_CHIP_FULL = "開完了"; // 待 joy 潤
  const YW_NOBODY = "沒人走過"; // 待 joy 潤
  const YW_FULL_LINE = "這一則的岔路都開完了，只能走有人走過的路。"; // 待 joy 潤
  const YW_TYPED_OFF = "自己說⋯（說書人還沒到）"; // 待 joy 潤
  const YW_HELP = "異聞的規矩"; // 待 joy 潤
  const YW_RULES = [
    "一則三幕，每一幕挑一個做法往下走。", // 待 joy 潤
    "有人走過的路照當初的樣子重放，順逆也跟當初一樣。", // 待 joy 潤
    "沒人走過的路由你寫下，記在你名下，往後撞見的人都踩得到你的腳印。", // 待 joy 潤
  ];
  const YW_DROP = "放下"; // 待 joy 潤
  const YW_DROP_ASK = "放下這一則，就不再往下走了。"; // 待 joy 潤
  const YW_HIDE = "收起"; // 待 joy 潤
  const YW_TRACK = "異聞・〈{title}〉（{n}）"; // 待 joy 潤
  const YW_TRACK_END = "收尾"; // 待 joy 潤
  const YW_SEE = "看 ▸"; // 待 joy 潤
  const YW_FOLD = "收 ▴"; // 待 joy 潤
  const YW_ZP_THEIRS = "當初一口咬定，那是"; // 待 joy 潤
  const YW_ZP_MINE = "你說"; // 待 joy 潤
  const YW_WAIT = "說書人正接著往下寫⋯"; // 待 joy 潤
  const YW_WAIT_NOTE = "可能要等半分鐘，寫不成什麼都不扣。"; // 待 joy 潤
  const YW_WAIT_SEAL = "開路"; // 待 joy 潤
  const YW_TRAIL_NOTE = "朱字是你開的路，記進異聞錄，往後撞見的人都踩得到你的腳印。"; // 待 joy 潤
  const YW_BACK = "回江湖"; // 待 joy 潤

  function ywFill(text, slots) { // 一次換完：放進去的字不會再被當成空格換一次（玩家寫的 {who} 原樣留著）
    return String(text).replace(/\{(\w+)\}/g, (m, k) => (k in slots ? String(slots[k]) : m));
  }
  const ywChars = (s) => [...String(s || "")]; // 照碼點切，不切壞字
  const ywAct = (depth) => YW_ACTS[Math.min(Math.max((Number(depth) || 1) - 1, 0), YW_ACTS.length - 1)];

  // 朱批的長度（引子＋「」裡的字）：≤12 一行直書；13～22 折兩行；23 以上兩行再縮字。頁邊在 flex 裡，書跟著長，不出框
  function ywFit(intro, words) {
    const n = ywChars(intro).length + ywChars(words).length;
    return n <= 12 ? "" : n <= 22 ? " yw-zp-2" : " yw-zp-3";
  }

  // 頁邊：朱批直書＋名號小印（只放前兩字）＋全名小字橫排；伺服器那一句放在 aria-label（直書裡不再寫一次名號）
  function ywMargin(sc) {
    const intro = sc.replay ? YW_ZP_THEIRS : YW_ZP_MINE;
    const two = ywChars(sc.who).slice(0, 2).join("");
    return `<div class="yw-margin${ywFit(intro, sc.pick)}" aria-label="${esc(sc.zhupi_text || "")}">
      <p class="yw-zp-tx"><small>${intro}</small>「${esc(sc.pick)}」</p>
      <span class="yw-stamp">${esc(two)}</span><small class="yw-zp-name">${esc(sc.who)}</small></div>`;
  }

  // 一頁書：左直條（第幾幕）、中正文（順逆章蓋在末尾）、右頁邊朱批（只在發掘者那一步）；上面一行回聲句（發掘者那一步省掉，只留朱批）
  function yiwenScene(sc) {
    const echo = !sc.zhupi && sc.echo ? `<p class="yw-echo">${esc(sc.echo)}</p>` : "";
    const luck = sc.luck ? `<span class="yw-luck" aria-label="${esc(sc.luck)}">${esc(sc.luck)}</span>` : "";
    const body = (sc.text || []).map((t) => `<p>${esc(t)}</p>`).join("");
    return `${echo}<div class="yw-book" data-node="${Number(sc.node) || 0}"><div class="yw-num">${ywAct(sc.depth)}</div>
      <div class="yw-leaf${luck ? " yw-sealed" : ""}"><div class="yw-txt">${body}</div>${luck}</div>${sc.zhupi ? ywMargin(sc) : ""}</div>`;
  }

  function ywFirstLine(sc) {
    const t = String((sc.text || [])[0] || "");
    const m = t.match(/^[^。！？]*[。！？]?/);
    return (m ? m[0] : t).replace(/[。！？]$/, "") + "⋯";
  }

  // 較早的幕：收成一行，點了在原地攤開（記在 S.ywOpen，不用 <details>）
  function ywPrev(sc) {
    const node = Number(sc.node) || 0;
    const open = !!(S.ywOpen && S.ywOpen[node]);
    const row = `<button class="yw-prev" data-act="yw-open" data-node="${node}" aria-expanded="${open}"><span>${ywAct(sc.depth)}・${esc(ywFirstLine(sc))}</span>${open ? YW_FOLD : YW_SEE}</button>`;
    return open ? row + yiwenScene(sc) : row;
  }

  // 一塊路牌：左邊做法（楷書），右邊一欄狀態
  function ywSign(card, c) {
    const typed = c.typed === true || c.i === "zhupi";
    const label = typed ? `「${esc(c.label)}」<small>${ywFill(YW_TYPED_BY, { who: esc(c.by) })}</small>` : esc(c.label);
    let st, off = false;
    if (c.state === "walked") st = `<strong>${Number(c.steps) || 0}<small>${YW_FOOT}</small></strong>${ywFill(YW_WALKED_BY, { who: esc(c.by) })}`;
    else if (c.state === "free") st = `<span class="yw-chip free">${card.mark === "first" ? YW_CHIP_MINE : YW_CHIP_FREE}</span>${YW_NOBODY}`;
    else if (c.state === "incense") st = `<span class="yw-chip paid">${YW_CHIP_INCENSE}</span>${YW_NOBODY}`;
    else { off = true; st = `<span class="yw-chip off">${esc(c.note || "")}</span>`; }
    return `<button class="yw-sign${typed ? " yw-zp" : ""}${off ? " locked" : ""}" data-act="yw-step" data-i="${esc(String(c.i ?? 0))}"${off ? " disabled" : ""}>
      <b>${label}</b><span class="yw-st">${st}</span></button>`;
  }

  // 路牌：有人走過的排前面（足跡多到少），再沒人走過的、要香的、鎖著的；開滿的幾顆併成一列＋頁下一行灰字
  function ywSigns(card) {
    const order = { walked: 0, free: 1, incense: 2, locked: 3 };
    const list = (card.choices || []).map((c, k) => ({ c, k }));
    const full = list.filter(({ c }) => c.state === "full");
    const rest = list.filter(({ c }) => c.state !== "full").sort((a, b) => {
      const oa = order[a.c.state] ?? 3, ob = order[b.c.state] ?? 3;
      if (oa !== ob) return oa - ob;
      if (oa === 0 && (Number(b.c.steps) || 0) !== (Number(a.c.steps) || 0)) return (Number(b.c.steps) || 0) - (Number(a.c.steps) || 0);
      return a.k - b.k;
    });
    const signs = rest.map(({ c }) => ywSign(card, c)).join("");
    const merged = full.length ? `<div class="yw-sign locked yw-full"><b>${full.map(({ c }) => esc(c.label)).join("・")}</b><span class="yw-st"><span class="yw-chip off">${YW_CHIP_FULL}</span></span></div>` : "";
    return `<div class="yw-signs">${signs}${merged}</div>${full.length ? `<p class="yw-legend">${YW_FULL_LINE}</p>` : ""}`;
  }

  function ywSay() { // 自己說（這一批說書人還沒到：灰、虛線、按不下去）＋「？」規矩
    const rules = S.ywHelp ? `<ul class="yw-rules">${YW_RULES.map((t) => `<li>${t}</li>`).join("")}</ul>` : "";
    return `<div class="yw-cd"><div class="yw-say off" aria-disabled="true"><span>${YW_TYPED_OFF}</span></div>
      <button class="yw-help" data-act="yw-help" aria-expanded="${!!S.ywHelp}"><span class="yw-q">？</span>${YW_HELP} ${S.ywHelp ? "▴" : "▾"}</button>${rules}</div>
      <button class="btn ghost yw-btn" data-act="yw-drop">${YW_DROP}</button>`;
  }

  function ywHero(card) {
    const trail = card.mark === "trail";
    const art = S.main && S.main.art && S.main.art.kind === "place" && S.main.art.src ? `<img class="yw-art-img" src="${esc(S.main.art.src)}" alt="">` : "";
    return `<div class="yw-cd yw-flush yw-hero"><div class="yw-art">${art}</div>
      <span class="yw-seal${trail ? "" : " solid"}">${trail ? YW_MARK_TRAIL : YW_MARK_FIRST}</span>
      <div class="yw-hero-tx"><p class="yw-hook">${esc(card.hook)}</p>${card.frame ? `<p class="yw-frame">${esc(card.frame)}</p>` : ""}
        <div class="yw-meta"><b>${esc(card.place_name)}</b>${trail ? `<small>${ywFill(YW_WALKERS, { n: Number(card.walkers) || 0 })}</small>` : ""}</div></div></div>`;
  }

  function ywTop(card) {
    return `<div class="yw-top"><div class="yw-top-tx"><h3 class="yw-title">${esc(card.title)}</h3><small>${ywFill(YW_PLACE_LINE, { place: esc(card.place_name) })}</small></div>
      <button class="btn ghost yw-hide" data-act="yw-hide">${YW_HIDE}</button></div>`;
  }

  // 收尾卡：收場句、「完」、一路的做法（自己寫的朱字）、得失一行（剛按完那一下的回話扣掉收場句、回聲與正文）、回江湖
  function yiwenClose(card) {
    const scenes = card.scenes || [];
    const known = new Set([card.close]);
    for (const sc of scenes) { known.add(sc.echo); known.add(sc.zhupi_text); for (const t of sc.text || []) known.add(t); }
    const gains = (S.ywLast || []).filter((t) => t && !known.has(t));
    const trail = scenes.map((sc) => (sc.replay ? esc(sc.pick) : `<b>${esc(sc.pick)}</b>`)).join(" ／ ");
    return `<div class="yw-cd yw-done"><p class="yw-close">${esc(card.close || "")}</p>
      <div class="yw-fin"><span class="yw-seal solid">${YW_MARK_DONE}</span><b class="yw-fin-title">${esc(card.title)}</b></div>
      ${trail ? `<div class="yw-trail3"><span>${trail}</span><span class="yw-grey">${YW_TRAIL_NOTE}</span></div>` : ""}
      ${gains.length ? `<div class="yw-gain">${gains.map((t) => `<span>${esc(t)}</span>`).join("")}</div>` : ""}
      <button class="btn primary yw-btn" data-act="choose" data-id="yiwen:drop">${YW_BACK}</button></div>`;
  }

  // 一整頁：撞見卡（還沒有幕）、每一幕（最新那一幕攤開、較早的收成一行）、收尾卡
  function yiwenCard(card) {
    if (!card) return "";
    const scenes = card.scenes || [];
    let body;
    if (card.done) {
      body = scenes.slice(0, -1).map(ywPrev).join("") + (scenes.length ? yiwenScene(scenes[scenes.length - 1]) : "") + yiwenClose(card);
    } else if (!scenes.length) {
      body = `${ywHero(card)}<div class="yw-hd"><h4>${YW_HD_FIRST}</h4><small>${YW_HD_TIP}</small></div>${ywSigns(card)}${ywSay()}`;
    } else {
      body = scenes.slice(0, -1).map(ywPrev).join("") + yiwenScene(scenes[scenes.length - 1])
        + `<div class="yw-hd"><h4>${YW_HD_NEXT}</h4></div>${ywSigns(card)}${ywSay()}`;
    }
    return `<div class="yw-card" role="dialog" aria-label="${esc(card.title)}">${ywTop(card)}<div class="yw-scr">${body}</div></div>`;
  }

  // 等說書人寫的那一刻（按了沒人走過的那一顆、請求 250ms 還沒回）：上一幕收成一行、新的一頁是格線＋墨點；頁邊寫你說的那一句
  function yiwenWait(card, label) {
    if (!card) return "";
    const scenes = card.scenes || [];
    const book = `<div class="yw-book yw-waiting"><div class="yw-num">${ywAct(scenes.length + 1)}</div>
      <div class="yw-leaf"><div class="yw-ruled"><p class="yw-wait"><span class="yw-dots" aria-hidden="true"><i></i><i></i><i></i></span>${YW_WAIT}</p></div>
        <p class="yw-note">${YW_WAIT_NOTE}</p></div>
      <div class="yw-margin${ywFit(YW_ZP_MINE, label)}"><p class="yw-zp-tx"><small>${YW_ZP_MINE}</small>「${esc(label)}」</p><span class="yw-stamp solid">${YW_WAIT_SEAL}</span></div></div>`;
    return `<div class="yw-card" role="dialog" aria-label="${esc(card.title)}" aria-busy="true">${ywTop(card)}<div class="yw-scr">${scenes.map(ywPrev).join("")}${book}</div></div>`;
  }

  // 收起時頁上那一條「進行中」（設計 10.1）：第幾幕＝已寫的幕數＋1，最多三；走完寫「收尾」
  function yiwenTrack(card) {
    if (!card) return "";
    const n = card.done ? YW_TRACK_END : ywAct((card.scenes || []).length + 1);
    return `<button class="yw-track" data-act="yw-show">${ywFill(YW_TRACK, { title: esc(card.title), n })}<i>›</i></button>`;
  }

  function ywTrackSync(card) { // 細條：江湖錄的「進行中」後面，沒有就頁面最上面；一樣就不動（不會自己叫自己）
    const old = document.querySelector(".yw-track");
    const want = card && S.ywHide ? yiwenTrack(card) : "";
    const page = document.getElementById("page");
    if (!want || !page) { if (old) old.remove(); return; }
    const anchor = document.querySelector(".cx-track");
    const placed = old && (anchor ? old.previousElementSibling === anchor : old.parentNode === page && page.firstElementChild === old);
    if (placed && old.dataset.sig === want) return;
    if (old) old.remove();
    const tmp = document.createElement("div");
    tmp.innerHTML = want;
    const el = tmp.firstElementChild;
    el.dataset.sig = want;
    if (anchor) anchor.insertAdjacentElement("afterend", el); else page.insertAdjacentElement("afterbegin", el);
  }

  // 蓋在頁面上的那一頁：照 main.yiwen.card 補上或拿掉（同一個樣子不重畫）；自己按的那一下捲到最新那一頁的頂，其他原因重畫留著捲到哪
  function yiwenSync() {
    if (typeof document === "undefined" || !document.body) return;
    const card = S.stage === "game" && S.main && S.main.yiwen ? S.main.yiwen.card : null;
    if (!card) S.ywHide = false;
    ywTrackSync(card);
    let box = document.getElementById("yw-pop");
    if (!card || S.ywHide) { if (box) box.remove(); S.ywSig = ""; return; }
    const art = S.main.art && S.main.art.src ? S.main.art.src : "";
    const sig = [JSON.stringify(card), JSON.stringify(S.ywLast || []), S.ywWait || "", S.ywHelp ? 1 : 0, JSON.stringify(S.ywOpen || {}), art].join("|");
    if (box && S.ywSig === sig) return;
    S.ywSig = sig;
    if (!box) { box = document.createElement("div"); box.id = "yw-pop"; box.className = "yw-wrap"; document.body.appendChild(box); }
    const top = box.scrollTop;
    const said = box.querySelector(".yw-say input");
    const keep = said ? said.value : "";
    box.innerHTML = S.ywWait ? yiwenWait(card, S.ywWait) : yiwenCard(card);
    const again = box.querySelector(".yw-say input");
    if (again && keep) again.value = keep;
    const jump = S.ywJump || !!S.ywWait;
    S.ywJump = false;
    const books = box.querySelectorAll(".yw-book");
    const last = jump && books.length ? books[books.length - 1] : null;
    box.scrollTop = last ? Math.max(0, last.offsetTop - 56) : top;
  }

  async function ywStep(el) { // 路牌按一顆：打 /api/do/yiwen_step；沒人走過的那一顆 250ms 還沒回就畫等說書人那一頁；回話留著給收尾卡寫得失
    const card = S.main && S.main.yiwen ? S.main.yiwen.card : null;
    if (!card || el.disabled) return;
    const raw = el.dataset.i || "0";
    const pick = /^\d+$/.test(raw) ? Number(raw) : raw; // 發掘者自己填的那一句（"zhupi"）照字串送
    const c = (card.choices || []).find((x) => String(x.i) === raw);
    const slow = c && (c.state === "free" || c.state === "incense");
    const timer = slow ? setTimeout(() => { S.ywWait = c.label; yiwenSync(); }, 250) : null;
    const body = { tale: card["tale"], opening: card.opening, node: card.node, pick }; // 寫成 ["tale"]：test_server 掃「點 tale」這種寫法（戰記的 class 名不准撞）
    try {
      const r = await api("/api/do/yiwen_step", body);
      S.ywLast = (r.message || "").replace(/<br\s*\/?>/g, "\n").replace(/<[^>]+>/g, "").split("\n").map((t) => t.trim()).filter(Boolean);
      S.ywJump = true;
      if (timer) clearTimeout(timer);
      S.ywWait = "";
      applyMain(r.main);
    } catch (e) { /* 連線斷了：卡還在，再按一次 */ }
    if (timer) clearTimeout(timer);
    S.ywWait = "";
    yiwenSync();
  }

  if (typeof MutationObserver === "function" && typeof document !== "undefined" && document.body) {
    new MutationObserver(() => yiwenSync()).observe(document.body, { childList: true, subtree: true }); // 頁面重畫時補上或拿掉那一頁與細條（一樣就不動，不會自己叫自己）
  }
  if (typeof document !== "undefined" && document.addEventListener) { // 選單上的「〈標題〉」（yiwen:open，殼的 choose）：收起的那一頁叫回來；只清旗子，送選擇照舊走殼
    document.addEventListener("click", (ev) => {
      const t = ev.target && ev.target.closest ? ev.target.closest('[data-id="yiwen:open"]') : null;
      if (t) { S.ywHide = false; S.ywSig = ""; }
    }, true);
  }

  async function yiwenClick(act, el, ev) {
    switch (act) {
        case "yw-step": await ywStep(el); break;
        case "yw-hide": S.ywHide = true; yiwenSync(); break;
        case "yw-show": S.ywHide = false; yiwenSync(); break;
        case "yw-help": S.ywHelp = !S.ywHelp; yiwenSync(); break;
        case "yw-open": { const n = Number(el.dataset.node) || 0; S.ywOpen = { ...(S.ywOpen || {}), [n]: !(S.ywOpen && S.ywOpen[n]) }; yiwenSync(); break; }
        case "yw-drop": ask(YW_DROP_ASK, YW_DROP, () => choose(document.querySelector('[data-act="yw-drop"]') || el, "yiwen:drop")); break;
    } // yiwenClick
  } // yiwenClick
  registerClicks(yiwenClick, ["yw-step", "yw-hide", "yw-show", "yw-help", "yw-open", "yw-drop"]);
