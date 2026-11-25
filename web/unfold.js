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
    "self:annals": { at: "practice" },
    "self:mingtie": { at: "practice" },
    "self:mail": { at: "practice" },
  };
  const ufFresh = () => ((S.main && S.main.unfold) || {}).fresh || [];
  // 這一塊此刻就在眼前（點開了）：紅點該滅
  function ufHere(key) {
    if (key === "tab:map") return S.tab === "map";
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

  // ── 小事卡（第二批）：拿到那一本的新角色，碰到才說的提示（guideHtml 的 g.hint）一律畫成這一張：上面一張圖、師父一句話、一顆「去做」。
  // 「去做」先按掉這一張（同「知道了」），再帶到那一處；沒有去處的只有「知道了」。待 joy 潤：鈕上的字
  const UF_CARDS = {
    h_sect: { img: "events/temple" },
    h_mail: { img: "events/road", go: "news:mail", label: "看信匣" },
    h_jieyi: { img: "events/tavern", go: "news:mingtie", label: "看名帖匣" },
    h_title: { img: "events/town", go: "tab:practice", label: "去挑" },
    h_codex: { img: "events/tale", go: "hero:codex", label: "翻江湖錄" },
    h_merge: { img: "events/altar", go: "tab:craft", label: "去煉製" },
    h_points: { img: "events/academy", go: "hero:attrs", label: "去配點" },
    h_create: { img: "events/academy", go: "create", label: "去自創" },
    h_tavern: { img: "here/tavern" },
    h_feast: { img: "here/feast" },
    h_injury: { img: "here/clinic" },
    h_mount: { img: "here/horses", go: "hero:gear", label: "去看看" },
    h_treasure: { img: "events/treasure", go: "hero:gear", label: "去看看" },
    h_mall: { img: "mall/card_30", go: "mall", label: "去萬寶閣" },
    h_pills: { img: "mall/pills_5", go: "buy:pills_5", label: "去買回體丹" },
    h_looks: { img: "mall/legend_1", go: "mall", label: "去萬寶閣" },
    h_tale: { img: "events/tale", go: "news:reports", label: "看戰報" },
    h_lose: { img: "events/fight" },
    h_field_lose: { img: "events/fight" },
    h_road: { img: "events/road" },
  };
  function unfoldCardHtml(g) {
    const c = UF_CARDS[g.key] || {};
    const pic = c.img ? `<div class="uf-pic" style="background-image:url(/static/img/${c.img}.webp)"></div>` : "";
    const go = c.go ? `<button class="btn primary" data-act="unfold-go" data-go="${esc(c.go)}">${esc(c.label)}</button>` : "";
    const ack = `<button class="btn${go ? " ghost" : ""}" data-act="guide-ack">知道了</button>`;
    return `<section class="card uf-card${pic ? "" : " bare"}" aria-label="${esc(g.speaker)}的話">${pic}<div class="uf-in"><b class="uf-who">${esc(g.speaker)}</b>`
      + `<p class="uf-say">${esc(g.text)}</p><div class="uf-dos">${go}${ack}</div></div></section>`;
  }
  async function unfoldGo(go) { // 先按掉這一張，再帶過去
    await doMain("guide_ack");
    const [kind, arg] = go.split(":");
    if (kind === "tab") await goTab(arg);
    else if (kind === "hero") { S.heroTab = arg; await goTab("practice"); }
    else if (kind === "news") { S.news = arg; await goTab("news"); }
    else if (kind === "create") { S.createOpen = true; await goTab("practice"); }
    else if (kind === "mall" && typeof openMall === "function") await openMall();
    else if (kind === "buy" && typeof openMall === "function") { await openMall(); if (typeof mallPick === "function") mallPick(arg); } // 萬寶閣開在那一件
  }
  async function unfoldClick(act, el, ev) {
    switch (act) {
        case "unfold-go": await unfoldGo(el.dataset.go || ""); break;
    } // unfoldClick
  } // unfoldClick
  registerClicks(unfoldClick, ["unfold-go"]);
