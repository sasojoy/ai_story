/* 天下大勢的網頁前端：慢慢長出來（features/unfold；Joy 2026-11-25）。新角色還用不到的分頁先不畫、玩到才長出來。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。伺服器沒給 main.unfold（開關關著、舊角色）就什麼都不做。
 * 藏的那一步在 app.js 的 shown()（main.unfold.hide 裡的鍵一律不畫）；這裡只管剛長出來的那一塊亮紅點、點開那一塊就滅。
 */
"use strict";

  // 剛長出來的鍵在畫面上的哪一處：底部分頁（at），俠客頁的子分頁（at＋sub），俠客頁人像卡上的那一顆連結（at，第三層由那一顆自己畫）
  const UF_PLACES = {
    "tab:map": { at: "map" },
    "tab:news": { at: "news" },
    "hero:attrs": { at: "practice", sub: "attrs" },
    "hero:gear": { at: "practice", sub: "gear" },
    "hero:mates": { at: "practice", sub: "mates" },
    "hero:codex": { at: "practice", sub: "codex" },
    "tab:craft": { at: "practice", sub: "arts" },
    "self:create": { at: "practice", sub: "arts" },
    "self:annals": { at: "practice" },
    "self:mingtie": { at: "practice" },
    "self:mail": { at: "practice" },
  };
  const ufFresh = () => ((S.main && S.main.unfold) || {}).fresh || [];
  // 這一塊此刻就在眼前（點開了）：紅點該滅
  function ufHere(key) {
    if (key === "tab:map") return S.tab === "map";
    if (key === "tab:craft") return S.tab === "craft";
    if (key === "self:create") return !!S.createOpen;
    if (key === "tab:news") return S.tab === "news" && !SELF_NEWS.some((n) => n.id === S.news);
    if (key.startsWith("hero:")) return S.tab === "practice" && S.heroTab === key.slice(5);
    if (key.startsWith("self:")) return S.tab === "news" && S.news === key.slice(5);
    return false;
  }
  let ufSending = false;
  async function ufSeen(keys) { // 看過了：紅點滅（伺服器回 main，殼重畫）
    if (ufSending || !keys.length) return;
    ufSending = true;
    try {
      const r = await api("/api/unfold/seen", { keys });
      if (r && r.main) { setMain(r.main); if (typeof paintDots === "function") paintDots(); }
    } catch (e) { /* 下一次輪詢再說 */ } finally { ufSending = false; }
  }
  // 這一塊亮不亮：剛長出來、還沒點開過。點開的那一刻（畫面正在畫它）就送「看過了」，這一次照樣亮著，回來的 main 才滅
  function unfoldDot(key) {
    if (!ufFresh().includes(key)) return false;
    if (ufHere(key)) setTimeout(() => ufSeen(ufFresh().filter(ufHere)), 0);
    return true;
  }
  if (typeof registerDot === "function") {
    for (const [key, place] of Object.entries(UF_PLACES)) {
      registerDot({ id: `unfold:${key}`, at: place.at, sub: place.sub, on: () => unfoldDot(key) });
    }
  }

  // ── 小事卡（提案表「七個系統第一次碰到的小事」，Joy 2026-11-25）：一張圖、一兩句話、一顆真的做第一步的鈕、一顆「改天」。
  // 兩種來源同一個樣子：①這一包自己的六張（main.unfold.card：門派、結義、書信、稱號、江湖錄、合成，帶著對象）；②碰到才說的提示（main.guide 的
  // g.hint），新角色一律畫成這一張，話是伺服器換好的一兩句（guide 包 short.py）。同一時間只畫一張，自己那張先。
  // 位置：江湖頁的場景卡底下、行動列上面（main.js 的 unfoldNowHtml；Joy 11/14「下一步的鈕要在玩家眼前」）。
  // 待 joy 潤：鈕上的字（提示那一種；自己那六張的字在伺服器 features/unfold/cards.py）
  const UF_IMG = { sect: "events/temple", mail: "gear/treasure-mendi_mingtie", jieyi: "events/tavern", title: "events/office", codex: "events/tale",
    fuse: "events/altar", gift: "events/market" };
  // 買了之後那一張（main.unfold.card.kind 是 buy，arg 是種類）：圖與鈕帶去哪
  const UF_BUY = { pills: ["mall/pills_5", "pill"], xinshen: ["events/night", "opt:act:socialize"], inscribe: ["mall/inscribe_ink", "opt:act:explore"],
    move_basic: ["events/academy", "moves"], legend: ["mall/legend_1", "hero:arts"], card_days: ["mall/card_30", "mall"], rename: ["mall/rename", "mall"] };
  // 提示 id → 圖、鈕（go 的寫法見 unfoldGo）。沒有鈕的那幾條是事情已經擺在眼前（放手一搏的輸入框、路上的選項）或只是一句話
  const UF_HINTS = {
    h_merge: { img: "events/altar", go: "tab:craft", label: "去煉製" },
    h_clash: { img: "events/academy", go: "hero:arts", label: "去看看" },
    h_lose: { img: "events/fight", go: "hero:arts", label: "回去練" },
    h_injury: { img: "here/clinic", go: "opt:act:heal", label: "去療傷" },
    h_drill_done: { img: "events/road", go: "opt:act:explore", label: "出門走走" },
    h_field_lose: { img: "events/fight", go: "tab:map", label: "看輿圖" },
    h_create: { img: "events/academy", go: "create", label: "去自創" },
    h_tavern: { img: "here/tavern", go: "opt:act:tavern", label: "進酒肆" },
    h_points: { img: "events/academy", go: "hero:attrs", label: "去配點" },
    h_basic_art: { img: "events/academy", go: "opt:learn:", label: "去學" },
    h_snubbed: { img: "events/office" },
    h_recruit: { img: "here/tavern", go: "opt:act:tavern", label: "進酒肆" },
    h_free_text: { img: "events/road" },
    h_road: { img: "events/road" },
    h_cap: { img: "events/academy", go: "hero:arts", label: "去整理" },
    h_spectator: { img: "events/camp" },
    h_foreshadow: { img: "events/night" },
    h_event_reveal: { img: "events/town" },
    h_promotion: { img: "events/office", go: "opt:act:summons", label: "去見他" },
    h_showdown: { img: "events/camp" },
    h_figure: { img: "events/camp" },
    h_mandate: { img: "events/altar" },
    h_bond: { img: "here/tavern" },
    h_raid_guard: { img: "events/forest" },
    h_checkin: { img: "events/village" },
    h_mall: { img: "mall/card_30", go: "mall", label: "進去看看" },
    h_pills: { img: "mall/pills_5", go: "buy:pills_5", label: "去買回體丹" },
    h_looks: { img: "mall/legend_1", go: "mall", label: "去換一身" },
    h_seal: { img: "events/treasure", go: "hero:gear", label: "看看它" },
    h_feast: { img: "here/feast", go: "opt:feast:join:", label: "入席" },
    h_chuangong: { img: "events/academy", go: "hero:mates", label: "去分" },
    h_mount: { img: "here/horses", go: "hero:gear", label: "騎上" },
    h_treasure: { img: "events/treasure", go: "hero:gear", label: "帶上" },
    h_place: { img: "events/refugees" },
    h_tale: { img: "events/tale", go: "news:reports", label: "去讀" },
    h_lilian: { img: "events/road" },
  };
  // 「opt:」開頭的鈕只有那個選項此刻在選單上才畫（「opt:learn:」這種結尾是冒號的，認開頭）
  const ufOpt = (m, want) => ((m && m.options) || []).find((o) => o.enabled !== false && (want.endsWith(":") ? o.id.startsWith(want) : o.id === want));
  function ufCardHtml(img, who, say, goBtn, laterAct) {
    const pic = img ? `<div class="uf-pic" style="background-image:url(/static/img/${img}.webp)"></div>` : "";
    const later = `<button class="btn${goBtn ? " ghost" : " primary"}" data-act="${laterAct}">${goBtn ? "改天" : "知道了"}</button>`;
    return `<section class="card uf-card${pic ? "" : " bare"}" aria-label="${esc(who)}">${pic}<div class="uf-in"><b class="uf-who">${esc(who)}</b>`
      + `<p class="uf-say">${esc(say)}</p><div class="uf-dos">${goBtn}${later}</div></div></section>`;
  }
  // 提示那一種（guideHtml 交過來的；也是 unfoldNowHtml 畫的那一張）
  function unfoldCardHtml(g) {
    const c = UF_HINTS[g.key] || {};
    let go = c.go || "";
    if (go.startsWith("opt:")) { const o = ufOpt(S.main, go.slice(4)); go = o ? `opt:${o.id}` : ""; }
    const btn = go ? `<button class="btn primary" data-act="unfold-go" data-go="${esc(go)}">${esc(c.label)}</button>` : "";
    return ufCardHtml(c.img, g.speaker, g.text, btn, "guide-ack");
  }
  // 這一包自己的那六張
  const UF_GO = { sect: (a) => `opt:zongmen:join:${a}`, mail: (a) => `mail:${a}`, jieyi: (a) => `peer:${a}`, title: (a) => `title:${a}`,
    codex: (a) => `codex:${a}`, fuse: (a) => `forge:${a}`, gift: () => "mall", buy: (a) => (UF_BUY[a] || [])[1] || "" };
  function ufOwnHtml(k) {
    let go = UF_GO[k.kind] ? UF_GO[k.kind](k.arg) : "";
    if (k.kind === "buy" && go.startsWith("opt:")) { const o = ufOpt(S.main, go.slice(4)); go = o ? `opt:${o.id}` : ""; } // 交友、探索此刻按不按得下去
    const pills = (S.main && S.main.status && S.main.status.pills) || null;
    if (go === "pill" && (!pills || pills.full || pills.today === 0)) go = ""; // 體力滿著、今天服滿了：只說一句，不給一顆按了被唸的鈕
    const btn = go ? `<button class="btn primary" data-act="unfold-card-go" data-go="${esc(go)}">${esc(k.go)}</button>` : "";
    const img = k.kind === "buy" ? (UF_BUY[k.arg] || [])[0] : UF_IMG[k.kind];
    return ufCardHtml(img, k.who, k.say, btn, "unfold-card-later");
  }
  // 江湖頁場景卡底下那一格（main.js）：舊角色（沒有那一本）回 null，照舊畫師父的框
  function unfoldNowHtml(m) {
    if (!m || !m.unfold) return null;
    if (m.unfold.card) return ufOwnHtml(m.unfold.card);
    if (m.unfold.old) return null; // 舊角色那一本（帶著做一次）：提示照舊畫師父的框
    return m.guide && m.guide.hint ? unfoldCardHtml(m.guide) : "";
  }
  async function unfoldGo(go) { // 帶過去：go 是「種類:對象」
    const i = go.indexOf(":"), kind = i < 0 ? go : go.slice(0, i), arg = i < 0 ? "" : go.slice(i + 1);
    if (kind === "tab") await goTab(arg);
    else if (kind === "hero") { S.heroTab = arg; await goTab("practice"); }
    else if (kind === "news") { S.news = arg; await goTab("news"); }
    else if (kind === "create") { S.createOpen = true; await goTab("practice"); }
    else if (kind === "mall" && typeof openMall === "function") await openMall();
    else if (kind === "buy" && typeof openMall === "function") { await openMall(); if (typeof mallPick === "function") mallPick(arg); } // 萬寶閣開在那一件
    else if (kind === "opt") await choose(document.querySelector(`[data-act="choose"][data-id="${CSS.escape(arg)}"]`) || document.createElement("button"), arg);
    else if (kind === "mail" && typeof mailOpen === "function") await mailOpen(arg);
    else if (kind === "peer" && typeof openPeer === "function") await openPeer(arg);
    else if (kind === "title" && typeof titlesWear === "function") await titlesWear(arg);
    else if (kind === "codex") { S.heroTab = "codex"; S.cxSeg = "qy"; S.cxOpen = arg; S.cxRead = null; await goTab("practice"); }
    else if (kind === "pill") await doMain("pill"); // 體力條上那一顆同一條路
    else if (kind === "moves" && typeof openMallMoves === "function") await openMallMoves("");
    else if (kind === "forge") { S.forgeSel = arg.split("+").map((id) => ({ type: "ins", id })); await goTab("craft"); } // 兩個已經放進爐裡
  }
  async function unfoldCardDone(go) { // go：按了卡上的鈕（有帶法的開始帶著做）；沒有＝改天
    const r = await api("/api/unfold/card", go ? { go: true } : {});
    if (r && r.main) setMain(r.main);
  }
  async function unfoldClick(act, el, ev) {
    switch (act) {
        case "unfold-go": await doMain("guide_ack"); await unfoldGo(el.dataset.go || ""); break; // 提示那一種：先按掉，再帶過去
        case "unfold-card-go": await unfoldCardDone(true); await unfoldGo(el.dataset.go || ""); ufLeadPaint(); break; // 自己那幾張：收起、開始帶，再帶過去
        case "unfold-card-later": await unfoldCardDone(false); renderPage(); break;
        case "uf-lead-go": { const l = ufLead(), st = l && ufStep(l); if (st && st.go) await unfoldGo(st.go(l)); ufLeadPaint(); break; }
        case "uf-lead-stop": await ufLeadPost({ stop: true }); break;
        case "uf-lead-end": { const l = ufLead(); if (l) await ufLeadPost({ kind: l.kind, step: "end" }); break; }
        case "uf-starter": ufStarterPick(el.dataset.text || ""); break;
    } // unfoldClick
  } // unfoldClick
  registerClicks(unfoldClick, ["unfold-go", "unfold-card-go", "unfold-card-later", "uf-lead-go", "uf-lead-stop", "uf-lead-end", "uf-starter"]);

  // ── 帶著做一次（Joy 2026-11-26「照建議」；設計稿 https://claude.ai/artifact/JGmeBcjLtjU1HWPYjhfwkD）──
  // 伺服器給 main.unfold.lead = {kind, arg, step, who, say, end, learn?, seal?}：這一步要按的那一顆亮一圈墨暈（.uf-lead），畫面底下一條
  // 「說話的人＋一句＋改天」（.uf-bar，那一顆不在這一頁時多一顆「帶我去」）；走到 end 拉起「做成了」那一張（.uf-done），按「好」收。
  // 哪一顆：UF_STEPS[種類][這一步].sel；不在眼前時帶去哪：.go（寫法同 unfoldGo）。存檔看不出來的那幾步（.web）在按下那一顆之後回報。
  const ufLead = () => (S.main && S.main.unfold && S.main.unfold.lead) || null;
  const UF_STEPS = {
    sect: {
      join: { sel: (l) => `.ask-layer [data-act="ask-yes"], [data-act="choose"][data-id="zongmen:join:${CSS.escape(l.arg)}"]`, go: (l) => `opt:zongmen:join:${l.arg}` },
      learn: { sel: (l) => (l.learn ? `[data-act="choose"][data-id="${CSS.escape(l.learn)}"], [data-act="here-all"][data-ids~="${CSS.escape(l.learn)}"]` : ""), go: () => "tab:jianghu" }, // 學藝那塊牌子（同類收一塊，點了拉起清單）
    },
    mail: { write: { sel: () => (ufDraft() ? '[data-act="mail-send"]' : ".uf-starter"), go: (l) => `mail:${l.arg}` } },
    jieyi: { invite: { sel: () => '[data-act="peer-act"][data-action="jieyi"]', go: (l) => `peer:${l.arg}` } },
    guard: { pick: { sel: () => '[data-act="choose"][data-id="guard:open"], [data-act="choose"][data-id^="guard:pick:"]', go: () => "hero:mates" } },
    codex: {
      read: { sel: () => '[data-act="cx-end"]', go: (l) => `codex:${l.arg}`, web: true },
      gallery: { sel: () => '[data-act="cx-seg"][data-seg="tj"]', go: () => "hero:codex", web: true },
    },
    fuse: { fire: { sel: () => '[data-act="forge"], .w-furnace.ready[data-act="forge-hub"]', go: (l) => `forge:${l.arg}` } }, // 開爐鈕，或太極火爐（點爐開火）
  };
  // 做成了那一張的印（待 joy 潤）
  const UF_STAMP = { sect: "已學", mail: "已寄", jieyi: "已遞", title: "", guard: "記下", codex: "記下", fuse: "合成" };
  const ufStep = (l) => (UF_STEPS[l.kind] || {})[l.step] || null;
  // 寫信那一步：信紙底下三句開頭，點了填進去（可以改）。待 joy 潤
  const UF_STARTERS = ["前日一別，近來可好？", "那一場打得痛快，改日再來。", "路過此地，想起你，寫幾個字。"];
  const ufDraft = () => { const box = typeof document !== "undefined" && document.getElementById ? document.getElementById("mail-text") : null; return !!(box && box.value.trim()); };
  function ufMailStarters(name) { // mail.js 的信紙底下叫（typeof 擋）：正在帶寫第一封給這個人、信紙還空著才畫
    const l = ufLead();
    if (!l || l.kind !== "mail" || l.step !== "write" || l.arg !== name || ufDraft()) return "";
    return `<div class="uf-starters">${UF_STARTERS.map((t) => `<button class="uf-starter" data-act="uf-starter" data-text="${esc(t)}">${esc(t)}</button>`).join("")}</div>`;
  }
  function ufStarterPick(text) {
    const box = document.getElementById("mail-text");
    if (!box) return;
    box.value = text;
    if (S.mailWith) S.mailDraft = { name: S.mailWith, text };
    renderPage();
  }
  function ufLeadDone(kind) { // mail.js 寄出成功那一下叫（typeof 擋）
    const l = ufLead();
    if (l && l.kind === kind && ufStep(l)) ufLeadPost({ kind, step: l.step });
  }
  async function ufLeadPost(body) {
    try {
      const r = await api("/api/unfold/lead", body);
      if (r && r.main) setMain(r.main);
    } catch (e) { /* 下一次輪詢再說 */ }
    if (typeof renderPage === "function") renderPage();
    ufLeadPaint();
  }
  function ufDoneHtml(l) {
    const stamp = UF_STAMP[l.kind] ? `<span class="uf-stamp" aria-hidden="true">${esc(UF_STAMP[l.kind])}</span>` : "";
    const seal = l.kind === "title" && l.seal ? `<div class="uf-mt"><span class="uf-mt-seal">${esc(l.seal)}</span><span class="uf-mt-name">${esc((S.main && S.main.status && S.main.status.name) || "")}</span></div>` : "";
    return `<div class="uf-done-in"><b class="uf-who">${esc(l.who)}</b>${seal}<p class="uf-say">${stamp}${esc(l.say)}</p>
      <button class="btn primary" data-act="uf-lead-end">好</button></div>`;
  }
  let ufPainted = "";
  function ufLeadPaint() { // 每次畫面變了照 main.unfold.lead 畫：墨暈、底下那一條、做成了那一張（只在有變時才動 DOM）
    if (typeof document === "undefined" || !document.body || typeof document.querySelectorAll !== "function") return;
    const l = S.stage === "game" ? ufLead() : null, st = l && !l.end ? ufStep(l) : null;
    const sel = st ? st.sel(l) : "";
    const want = new Set(sel ? Array.from(document.querySelectorAll(sel)).filter((x) => !x.disabled && (!x.getClientRects || x.getClientRects().length > 0)) : []); // 藏著的（收在牌子裡的清單）不算
    for (const x of document.querySelectorAll(".uf-lead")) if (!want.has(x)) x.classList.remove("uf-lead");
    for (const x of want) if (!x.classList.contains("uf-lead")) x.classList.add("uf-lead");
    const key = l ? `${l.kind}|${l.step}|${want.size ? 1 : 0}|${l.say}` : "";
    if (key === ufPainted) return;
    if (want.size && !ufPainted.startsWith(`${l.kind}|${l.step}|1`)) { // 這一步第一次看到要按的那一顆：捲到畫面中間（不被底下那一條蓋住），一步只捲一次
      const first = want.values().next().value;
      if (first && first.scrollIntoView) first.scrollIntoView({ block: "center", behavior: "smooth" });
    }
    ufPainted = key;
    for (const x of document.querySelectorAll(".uf-bar, .uf-done")) x.remove();
    if (!l) return;
    if (l.end) { document.body.insertAdjacentHTML("beforeend", `<section class="uf-done" role="dialog" aria-label="${esc(l.who)}">${ufDoneHtml(l)}</section>`); return; }
    const goBtn = !want.size && st && st.go ? '<button class="btn primary uf-bar-go" data-act="uf-lead-go">帶我去</button>' : "";
    document.body.insertAdjacentHTML("beforeend", `<aside class="uf-bar" aria-label="${esc(l.who)}"><div class="uf-bar-in"><p><b>${esc(l.who)}</b>${esc(l.say)}</p>${goBtn}
      <button class="uf-bar-stop" data-act="uf-lead-stop">改天</button></div></aside>`);
  }
  if (typeof document !== "undefined" && document.addEventListener && typeof MutationObserver === "function") {
    let queued = false;
    new MutationObserver(() => {
      if (queued) return;
      queued = true;
      requestAnimationFrame(() => { queued = false; ufLeadPaint(); });
    }).observe(document.body, { childList: true, subtree: true });
    // 存檔看不出來的那幾步（讀了結局、翻到圖鑑）：按下亮著的那一顆，那一下的事做完之後回報
    document.addEventListener("click", (ev) => {
      const l = ufLead(), st = l && ufStep(l);
      if (!st || !st.web || !ev.target || !ev.target.closest) return;
      if (ev.target.closest(".uf-lead")) setTimeout(() => ufLeadPost({ kind: l.kind, step: l.step }), 400);
    }, true);
  }
