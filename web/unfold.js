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
    fuse: "events/altar" };
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
    codex: (a) => `codex:${a}`, fuse: (a) => `forge:${a}` };
  function ufOwnHtml(k) {
    const go = UF_GO[k.kind] ? UF_GO[k.kind](k.arg) : "";
    const btn = go ? `<button class="btn primary" data-act="unfold-card-go" data-go="${esc(go)}">${esc(k.go)}</button>` : "";
    return ufCardHtml(UF_IMG[k.kind], k.who, k.say, btn, "unfold-card-later");
  }
  // 江湖頁場景卡底下那一格（main.js）：舊角色（沒有那一本）回 null，照舊畫師父的框
  function unfoldNowHtml(m) {
    if (!m || !m.unfold) return null;
    if (m.unfold.card) return ufOwnHtml(m.unfold.card);
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
    else if (kind === "forge") { S.forgeSel = arg.split("+").map((id) => ({ type: "ins", id })); await goTab("craft"); } // 兩個已經放進爐裡
  }
  async function unfoldCardDone() {
    const r = await api("/api/unfold/card", {});
    if (r && r.main) setMain(r.main);
  }
  async function unfoldClick(act, el, ev) {
    switch (act) {
        case "unfold-go": await doMain("guide_ack"); await unfoldGo(el.dataset.go || ""); break; // 提示那一種：先按掉，再帶過去
        case "unfold-card-go": await unfoldCardDone(); await unfoldGo(el.dataset.go || ""); break; // 自己那六張：收起，再帶過去
        case "unfold-card-later": await unfoldCardDone(); renderPage(); break;
    } // unfoldClick
  } // unfoldClick
  registerClicks(unfoldClick, ["unfold-go", "unfold-card-go", "unfold-card-later"]);
