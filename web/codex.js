/* 天下大勢的網頁前端：江湖錄（features/codex）。俠客頁「江湖錄」那一頁：奇遇（正在走、已了、往季、還沒遇上；點進去重讀每一幕）與圖鑑（人物、器物、意境、結局）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。伺服器沒給 main.codex（開關關著）就什麼都不畫、也不加分頁。
 * 整本另外拿（GET /api/codex），狀態列只帶紅點；攤到哪裡記在 S.cx*（重畫不收回去）。
 */
"use strict";

  // 待 joy 潤：江湖錄的字
  const CX_TAB = "江湖錄";
  const CX_SEGS = [["qy", "奇遇"], ["tj", "圖鑑"]];
  const CX_CATS = [["people", "人物"], ["things", "器物"], ["gods", "意境"], ["ends", "結局"]];
  const CX_ON = "正在走";
  const CX_DONE = "已了";
  const CX_PAST = "往季";
  const CX_GHOST = "還沒遇上";
  const CX_NEXT = "下一步";
  const CX_SCENES = "走過的幕";
  const CX_ENDS = "結局";
  const CX_REREAD = "重讀";
  const CX_MAP = "在輿圖上看";
  const CX_GO = "去{place}";
  const CX_YOU = "你";
  const CX_OTHERS = "也可以：";
  const CX_BACK = "‹ 江湖錄";
  const CX_LOADING = "翻開江湖錄……";
  const CX_EMPTY_QY = "還沒有遇上什麼奇事。到處走走、探索，江湖上的事會找上門來。";
  const CX_EMPTY_GOD = "悟出神品意境，會在這張表上寫下你替它取的名字。";
  const CX_SEEN = "位見過";
  const CX_HAVE = "件拿過";
  const CX_GODS = "種神品";
  const CX_ENDS_N = "種收法";
  const CX_SEAL = { 奇事: "奇事", 主線: "主線" };

  const cxDot = () => { const c = S.main && S.main.codex; return !!c && !!(c.q || c.p || c.t || c.g || c.e); };
  if (typeof registerDot === "function") registerDot({ id: "codex", at: "practice", sub: "codex", on: cxDot });
  const cxSegDot = (k) => { const c = (S.main && S.main.codex) || {}; return k === "qy" ? !!c.q : !!(c.p || c.t || c.g || c.e); };
  const CX_CAT_DOT = { people: "p", things: "t", gods: "g", ends: "e" };

  // 整本：沒有或紅點變了（有新的一幕、新點亮一格）才重拿
  function cxLoad(force) {
    const sig = JSON.stringify(((S.main && S.main.codex) || {}).fresh || []);
    if (!force && S.cx && S.cxSig === sig && Date.now() - (S.cxAt || 0) < 60000) return; // 剩幾天會走：拿了 60 秒以上的也重拿
    if (S.cxLoading) return;
    S.cxLoading = true;
    S.cxSig = sig;
    S.cxAt = Date.now();
    api("/api/codex").then((r) => { S.cx = r; }).catch(() => {}).finally(() => {
      S.cxLoading = false;
      if (S.heroTab === "codex" && typeof renderPage === "function") renderPage();
    });
  }

  async function cxSeen(keys) { // 看過了：紅點滅（伺服器回 main，殼重畫）
    const fresh = ((S.main && S.main.codex) || {}).fresh || [];
    const want = keys.filter((k) => (k.endsWith("*") ? fresh.some((f) => f.startsWith(k.slice(0, -1))) : fresh.includes(k)));
    if (!want.length) return;
    try {
      const r = await api("/api/codex/seen", { keys: want });
      if (r && r.main) { setMain(r.main); S.cxSig = JSON.stringify(((S.main && S.main.codex) || {}).fresh || []); if (typeof paintDots === "function") paintDots(); }
    } catch (e) { /* 下一次輪詢再說 */ }
  }

  const cxImg = (src, cls = "") => (src ? `<img class="${cls}" src="${esc(src)}" alt="" loading="lazy">` : "");
  const cxSeal = (word, solid) => `<span class="cx-seal${solid ? " solid" : ""}">${esc(word)}</span>`;
  const cxDots = (q) => { // 幕點：走過的實心墨、現在這一幕朱、後面空心（只寫看得到的那幾格，不露總數以外的事）
    const done = q.scenes.length, all = Math.max(q.stages || 0, done + (q.state === "on" ? 1 : 0));
    return `<span class="cx-pip" aria-hidden="true">${Array.from({ length: all }, (_, i) => `<i class="${i < done ? "f" : i === done && q.state === "on" ? "c" : ""}"></i>`).join("")}</span>`;
  };

  function cxRow(q) {
    if (q.state === "ghost") return `<div class="cx-ghost"><b>？</b><small>${esc(q.where || "")}</small></div>`; // 還沒遇上：剪影＋地名
    const sub = q.state === "on" && q.next
      ? `<small class="nx"><b>${esc(q.next.what)}</b></small><small class="lf">${esc([q.next.ready ? "" : q.next.when, q.next.left].filter(Boolean).join("，"))}${cxDots(q)}</small>`
      : `<small class="nx">${q.ending ? `${esc(q.ending.title)}` : ""}　${cxSeal(q.ending && q.ending.failed ? "未成" : "入傳")}</small>`;
    return `<button class="cx-qy${q.state === "done" ? " done" : ""}" data-act="cx-open" data-key="${esc(q.key)}">${dotHtml(q.dot)}`
      + `<span class="th">${cxImg(q.src) || `<span class="sil">${esc((q.title || "？")[0])}</span>`}</span>`
      + `<span class="bd"><b class="nm">${esc(q.title)}<em>${esc(q.who || q.kind)}</em></b>${sub}</span><span class="go" aria-hidden="true">›</span></button>`;
  }

  function cxList(d) {
    const sec = (name, rows, n = rows.length) => (rows.length ? `<h4 class="cx-sec">${name}<small>${n} 件</small></h4>${rows.map(cxRow).join("")}` : "");
    const any = d.on.length + d.done.length + d.past.length;
    return `${any ? "" : `<p class="cx-empty">${CX_EMPTY_QY}</p>`}${sec(CX_ON, d.on)}${sec(CX_DONE, d.done)}${sec(CX_PAST, d.past)}${d.ghosts.length ? `<h4 class="cx-sec">${CX_GHOST}<small>${d.ghosts.length} 件</small></h4><div class="cx-ghosts">${d.ghosts.map(cxRow).join("")}</div>` : ""}`;
  }

  function cxEnds(q) {
    return `<div class="cx-ends">${q.ends.map((e) => (e.got
      ? `<button class="cx-end" data-act="cx-end" data-line="${esc(q.line)}" data-end="${esc(e.id)}">${cxImg(e.src)}<span>${esc(e.title)}</span></button>`
      : `<div class="cx-end off"><span>？</span></div>`)).join("")}</div>`;
  }

  function cxQuest(q) {
    const art = `<div class="cx-hero">${cxImg(q.src)}<div class="cx-plaque">${esc(q.title)}</div>`
      + `<div class="cx-hero-l">${cxSeal(q.state === "done" ? CX_DONE : CX_SEAL[q.kind] || q.kind, q.state === "done")}<i>${esc(q.state === "done" && q.ending ? `${CX_ENDS}：${q.ending.title}` : q.intro || "")}</i></div></div>`;
    let now = "";
    if (q.state === "on" && q.next) {
      const n = q.next;
      now = `<div class="cx-now"><span class="k">${CX_NEXT}</span><b class="w">${esc(n.what)}${n.where && !n.what.includes(n.where) && n.what !== n.where && !n.hint ? `・${esc(n.where)}` : ""}</b>`
        + `<small class="t">${esc([n.when, n.left].filter(Boolean).join("，"))}</small>`
        + (n.loc ? `<button class="btn primary" data-act="cx-map" data-loc="${esc(n.loc)}">${CX_MAP}</button>` : "") + "</div>";
    }
    const stay = q.stay ? `<div class="cx-stay">${q.stay.face ? `<span class="por">${cxImg(q.stay.face)}</span>` : ""}<div><b>${esc(q.stay.name)}</b>`
      + `<p>${esc(q.stay.text)}</p>${q.stay.said ? `<small>${esc(q.stay.said)}</small>` : ""}</div></div>`
      + (q.stay.loc ? `<button class="btn primary" data-act="cx-map" data-loc="${esc(q.stay.loc)}">${esc(CX_GO.replace("{place}", q.stay.place))}</button>` : "") : "";
    // 江湖錄打開之前走過的那一幕（sc.i 是 null）：幕名＋「當時的選擇沒有留下」，不能重讀
    const acts = q.scenes.map((sc, i) => (sc.i == null
      ? `<div class="cx-act lost"><span class="n">第${"一二三四五六七八九十"[i] || i + 1}幕</span><span class="x"><b>${esc(sc.title)}</b><small>${esc(sc.lost || "")}</small></span></div>`
      : `<button class="cx-act" data-act="cx-read" data-i="${sc.i}"><span class="n">第${"一二三四五六七八九十"[i] || i + 1}幕</span>`
      + `<span class="x"><b>${esc(sc.title)}</b><small>${CX_YOU}：<q>${esc(sc.pick)}</q></small></span><span class="r">${CX_REREAD} ›</span></button>`)).join("");
    const cur = q.state === "on" ? `<div class="cx-act cur"><span class="n">第${"一二三四五六七八九十"[q.scenes.length] || q.scenes.length + 1}幕</span><span class="x"><b>？？</b><small>${esc(q.next ? q.next.when : "")}</small></span></div>` : "";
    const gotN = q.ends.filter((e) => e.got).length;
    return `<button class="cx-back linkish" data-act="cx-back">${CX_BACK}</button>${art}${now}${stay}`
      + (acts || cur ? `<h4 class="cx-sec">${CX_SCENES}</h4><div class="cx-acts">${acts}${cur}</div>` : "")
      + `<h4 class="cx-sec">${CX_ENDS}<small>${gotN}／${q.ends.length}</small></h4>${cxEnds(q)}`;
  }

  function cxReading(t) {
    if (!t) return `<button class="cx-back linkish" data-act="cx-back">${CX_BACK}</button><p class="cx-empty">${CX_LOADING}</p>`;
    const p = (xs) => xs.map((x) => `<p>${esc(x)}</p>`).join("");
    return `<button class="cx-back linkish" data-act="cx-back">‹ ${esc(t.story || CX_TAB)}</button>`
      + (t.src ? `<div class="cx-hero short">${cxImg(t.src)}</div>` : "")
      + `<article class="cx-paper"><h4>${esc(t.title)}${t.stamp ? cxSeal(t.stamp) : ""}</h4>${p(t.before || [])}`
      + (t.pick ? `<div class="cx-pick"><small>${CX_YOU}</small>${esc(t.pick)}</div>` : "") + p(t.after || [])
      + (t.others && t.others.length ? `<p class="cx-unpick">${CX_OTHERS}${t.others.map(esc).join("・")}</p>` : "") + "</article>";
  }

  function cxCount(n, all, word) {
    const pct = all ? Math.round((n / all) * 100) : 0;
    return `<div class="cx-count"><b>${n}</b><small>／ ${all} ${word}</small></div><div class="cx-bar"><i style="width:${pct}%"></i></div>`;
  }

  function cxPeople(d) {
    return cxCount(d.got, d.all, CX_SEEN) + `<div class="cx-grid">${d.rows.map((r) => `<div class="cx-cell${r.got ? "" : " off"}">${dotHtml(r.dot)}`
      + `<span class="im">${cxImg(r.face)}</span><b>${esc(r.name)}</b><small>${esc(r.place)}</small></div>`).join("")}</div>`;
  }

  function cxThings(d) {
    const g = d.groups.find((x) => x.id === S.cxThing) || d.groups[0];
    const chips = `<div class="cx-chips grp">${d.groups.map((x) => `<button class="${x.id === g.id ? "on" : ""}" data-act="cx-grp" data-id="${esc(x.id)}">${esc(x.name)}<small>${x.got}／${x.all}</small>${dotHtml(x.cells.some((c) => c.dot))}</button>`).join("")}</div>`;
    return chips + `<div class="cx-grid sq">${g.cells.map((c) => `<div class="cx-cell${c.got ? "" : " off"}">${dotHtml(c.dot)}`
      + `<span class="im">${cxImg(c.src) || (c.got ? `<span class="glyph">${esc(c.name[0])}</span>` : "")}</span><b>${esc(c.name)}</b><small>${esc(c.sub || "")}</small></div>`).join("")}</div>`;
  }

  function cxGods(d) {
    const head = `<span></span>${d.forms.map((f) => `<span class="h">${esc(f)}</span>`).join("")}`;
    const rows = d.paths.map((p) => `<span class="h">${esc(p)}</span>${d.forms.map((f) => {
      const c = d.cells[`${p}${f}`];
      return c && c.got ? `<span class="cx-yc on ${esc(c.tone)}" title="${esc(c.place)}">${dotHtml(c.dot)}${esc(c.name)}</span>` : `<span class="cx-yc"></span>`;
    }).join("")}`).join("");
    const mine = Object.values(d.cells).filter((c) => c.got);
    const list = mine.length ? mine.map((c) => `<div class="cx-kv">${cxSeal("神品")}<div><b>${esc(c.name)}</b><small>${c.season ? `第 ${c.season} 季・` : ""}${esc(c.place)}</small></div></div>`).join("")
      : `<p class="cx-empty">${CX_EMPTY_GOD}</p>`;
    return cxCount(d.got, d.all, CX_GODS) + `<div class="cx-ygrid">${head}${rows}</div>${list}`;
  }

  function cxEndings(d) {
    const met = d.rows.filter((r) => r.met), not = d.rows.filter((r) => !r.met);
    return cxCount(d.got, d.all, CX_ENDS_N) + met.map((r) => `<h4 class="cx-sec">${esc(r.title)}${dotHtml(r.dot)}</h4>${cxEnds({ line: r.line, ends: r.ends })}`).join("")
      + (not.length ? `<h4 class="cx-sec">${CX_GHOST}</h4>${not.map((r) => `<div class="cx-endrow"><b>${esc(r.title)}</b><span class="cx-pip">${r.ends.map(() => "<i></i>").join("")}</span></div>`).join("")}` : "");
  }

  // 俠客頁「江湖錄」那一頁（web/cultivation.js 叫）：main.codex 沒有（開關關著）是空字串、分頁也不加
  function codexHtml(main) {
    if (!main || !main.codex) return "";
    cxLoad(false);
    const d = S.cx;
    if (S.cxRead) return cxReading(S.cxText);
    const seg = S.cxSeg === "tj" ? "tj" : "qy";
    const segs = `<div class="cx-seg" role="tablist">${CX_SEGS.map(([k, n]) => `<button role="tab" class="${seg === k ? "on" : ""}" aria-selected="${seg === k}" data-act="cx-seg" data-seg="${k}">${n}${dotHtml(cxSegDot(k))}</button>`).join("")}</div>`;
    if (!d) return `${segs}<p class="cx-empty">${CX_LOADING}</p>`;
    if (seg === "qy") {
      const all = [...d.quests.on, ...d.quests.done, ...d.quests.past];
      const q = S.cxOpen && all.find((x) => x.key === S.cxOpen);
      return q ? cxQuest(q) : `${segs}${cxList(d.quests)}`;
    }
    const cat = CX_CATS.some(([k]) => k === S.cxCat) ? S.cxCat : "people";
    const c = (S.main && S.main.codex) || {};
    const chips = `<div class="cx-chips cats">${CX_CATS.map(([k, n]) => `<button class="${cat === k ? "on" : ""}" data-act="cx-cat" data-cat="${k}">${n}${dotHtml(!!c[CX_CAT_DOT[k]])}</button>`).join("")}</div>`;
    const body = cat === "people" ? cxPeople(d.people) : cat === "things" ? cxThings(d.things) : cat === "gods" ? cxGods(d.gods) : cxEndings(d.endings);
    if (c[CX_CAT_DOT[cat]]) setTimeout(() => cxSeen([`${CX_CAT_DOT[cat]}:*`]), 1200); // 這一類攤開看了：一會兒之後四層一起滅（這一次畫的格照樣亮著）
    return `${segs}${chips}${body}`;
  }

  function cxDraw(fn) {
    const go = () => { fn(); renderPage(); };
    if (typeof heroStay === "function") heroStay(go); else go();
  }


  // ── 江湖頁「進行中」（Joy 2026-11-13 設計稿 v2 選甲；Config.codex.tracker）──
  // 狀態列底下一行：平常只露正在追的那一件（自己挑的，沒挑就排最前面那一件），右邊一顆印記寫幾件，點了從底下拉起全部，每件一顆「去」。
  // 奇事、主線照伺服器的 codex.track；軍令、懸賞、盤算、本週、玉璽照 main.js 收成「要事」的那幾格（parts）；同伴有事等你照 main.guard。
  // 追哪一件、看過哪幾件記在這個瀏覽器（tianxia.cxTrack）：只是方便，讀不到照樣畫
  const TK_HEAD = "進行中"; // 待 joy 潤
  const TK_SEAL = "事"; // 待 joy 潤
  const TK_GO = "去"; // 待 joy 潤
  const TK_PIN = "追這一件"; // 待 joy 潤
  const TK_PINNED = "正在追"; // 待 joy 潤
  const TK_MATE = "同伴"; // 待 joy 潤
  const TK_MATE_LINE = "{name}有事等你"; // 待 joy 潤
  const TK_CLOSE = "關閉";
  const TK_STORE = "tianxia.cxTrack";
  const TK_PTS = "有 {n} 點屬性可配"; // 待 joy 潤
  const TK_ATTR = "屬性"; // 待 joy 潤
  const TK_SHIHAI = "識海"; // 待 joy 潤
  const TK_SHIHAI_PICK = "上一季的神品意境還沒挑"; // 待 joy 潤
  const TK_SEALED = "封著「{name}」"; // 待 joy 潤
  const TK_WAITS = "在等的 {n} 件"; // 待 joy 潤
  const TK_WAIT_SEAL = "在等"; // 待 joy 潤
  const TK_NONE = "眼下沒有推得動的事，四處走走。"; // 待 joy 潤
  const TK_WHY = "兩軍態勢・這一季在打什麼 ›"; // 待 joy 潤
  function tkMemo() {
    if (!S.cxTkMemo) {
      try { S.cxTkMemo = JSON.parse(localStorage.getItem(TK_STORE) || "null"); } catch (e) { S.cxTkMemo = null; }
      S.cxTkMemo = S.cxTkMemo && typeof S.cxTkMemo === "object" ? S.cxTkMemo : {};
      S.cxTkMemo.seen = Array.isArray(S.cxTkMemo.seen) ? S.cxTkMemo.seen : [];
    }
    return S.cxTkMemo;
  }
  function tkSave() { try { localStorage.setItem(TK_STORE, JSON.stringify(tkMemo())); } catch (e) { /* 私密視窗：這一次記著就好 */ } }
  // 這一件此刻按得下去嗎（此地可為裡有那一顆）：按了就去做；不然去輿圖那一處；都沒有就打開它在哪一頁
  function tkStoryGo(m, t) {
    const id = `story:${t.line}`;
    const opt = [...(m.options || []), ...(S.hereExtras || [])].find((o) => o.id === id && o.enabled);
    return opt ? { id } : t.loc ? { loc: t.loc } : { hero: "codex", open: t.key };
  }
  // 一件一格：wait 是現在推不動的（章回做完了等大事、多日段還沒到時候、時機未到的要事、識海還差什麼）——收在清單最底下「在等的 N 件」，
  // 不算進印上的數字、不會被挑成最上面那一行、沒有「去」（Joy 2026-11-13「還不能做的要顯示嗎？」）。「去」一定有地方去
  function tkItems(m, parts) {
    const c = (m && m.codex) || {};
    if (!Array.isArray(c.track)) return null;
    const items = c.track.map((t) => {
      if (t.wait) return { key: `q:${t.line}`, seal: t.kind, title: t.title, sub: [t.what, t.until].filter(Boolean).join("・"), wait: true };
      const go = tkStoryGo(m, t);
      return { key: `q:${t.line}`, seal: t.kind, title: t.title, sub: [t.what, t.left].filter(Boolean).join("・"), go, now: go.id ? 2 : 1 };
    });
    for (const p of parts || []) {
      if (p.html) items.push(p.now ? { key: `d:${p.key}`, seal: p.name, title: p.line || p.name, sub: "", go: { duty: 1 }, now: 1 }
        : { key: `d:${p.key}`, seal: p.name, title: p.line || p.name, sub: "", wait: true });
    }
    // 江湖頁頂上那幾條提示（main.js 的 jhHintsHtml：屬性點、識海）：瘦身時收進這裡，一件一行
    const slim = codexSlim(m);
    const st = m.status || {}, pts = slim && st.growth ? st.stat_points | 0 : 0;
    if (pts) items.push({ key: "h:pts", seal: TK_ATTR, title: TK_PTS.replace("{n}", pts), sub: "", go: { hero: "attrs" }, now: 1 });
    const sh = slim && m.legacy && m.legacy.shihai;
    if (sh && sh.offers && sh.offers.length) items.push({ key: "h:shihai", seal: TK_SHIHAI, title: TK_SHIHAI_PICK, sub: "", go: { legacy: "shihai" }, now: 1 });
    else if (sh && sh.sealed) {
      const left = (sh.need || []).filter((n) => !n.ok).map((n) => n.text), names = (sh.sealed.names || []).length;
      const ready = !left.length && !sh.held && !names;
      const why = names ? "要先換個名字" : ready ? "可以解封了" : sh.held && !left.length ? "身上已有一份神品" : `解封還差：${left.join("、")}`; // 待 joy 潤（同 main.js jhHintsHtml）
      const it = { key: "h:sealed", seal: TK_SHIHAI, title: TK_SEALED.replace("{name}", sh.sealed.name || ""), sub: why };
      items.push(ready || names ? { ...it, go: { legacy: "shihai" }, now: 1 } : { ...it, wait: true });
    }
    const g = m.guard;
    if (g && ((g.event && !g.event.shown) || (g.schools && g.schools.length))) {
      items.push({ key: "g", seal: TK_MATE, title: TK_MATE_LINE.replace("{name}", g.name || ""), sub: "", go: { hero: "mates" }, now: 1 });
    }
    const all = items.map((x, i) => ({ ...x, i }));
    return { on: all.filter((x) => !x.wait).sort((a, b) => (b.now - a.now) || (a.i - b.i)), wait: all.filter((x) => x.wait) };
  }
  const tkGoAttrs = (it) => `data-act="cx-tk-go"${it.go.id ? ` data-id="${esc(it.go.id)}"` : ""}${it.go.loc ? ` data-loc="${esc(it.go.loc)}"` : ""}`
    + `${it.go.duty ? ' data-duty="1"' : ""}${it.go.hero ? ` data-hero="${esc(it.go.hero)}"` : ""}${it.go.open ? ` data-open="${esc(it.go.open)}"` : ""}`
    + `${it.go.legacy ? ` data-legacy="${esc(it.go.legacy)}"` : ""}`;
  const tkText = (it) => `<span class="cx-tk-tag">${esc(it.seal)}</span><span class="cx-tk-t"><b>${esc(it.title)}</b>${it.sub ? `<small>${esc(it.sub)}</small>` : ""}</span>`;
  // 印記右上角的數字：現在推得動的幾件；有沒看過的那一件（拉開過就算看過）是朱紅的，都看過是墨色
  // main.js 的江湖頁叫（介面重整那一支）：開關關著、什麼都沒有回空字串，main.js 照舊畫「要事」那一張
  function codexTrackHtml(m, parts) {
    const got = tkItems(m, parts);
    if (!got || (!got.on.length && !got.wait.length)) return "";
    const memo = tkMemo();
    const top = got.on.find((x) => x.key === memo.pin) || got.on[0];
    const fresh = got.on.some((x) => !memo.seen.includes(x.key));
    const main = top ? `<button class="cx-tk-main" ${tkGoAttrs(top)}>${tkText(top)}</button>`
      : `<button class="cx-tk-main idle" data-act="cx-tk">${tkText({ ...got.wait[0], seal: TK_WAIT_SEAL })}</button>`; // 都在等：寫最前面那一件在等什麼，點了拉開
    const line = `<section class="cx-track" aria-label="${TK_HEAD}">${main}`
      + `<button class="cx-tk-all" data-act="cx-tk" aria-expanded="${!!S.cxTk}" aria-label="${TK_HEAD} ${got.on.length} 件">${TK_SEAL}${got.on.length ? `<em${fresh ? ' class="new"' : ""}>${got.on.length}</em>` : ""}</button></section>`;
    const tug = tkTugHtml(m);
    if (!S.cxTk) return tug + line + codexWhyHtml(m);
    const rows = got.on.map((it) => `<div class="cx-tk-row"><button class="cx-tk-pin${it.key === top.key ? " on" : ""}" data-act="cx-tk-pin" data-key="${esc(it.key)}" aria-pressed="${it.key === top.key}" aria-label="${it.key === top.key ? TK_PINNED : TK_PIN}" title="${it.key === top.key ? TK_PINNED : TK_PIN}">◆</button>`
      + `${tkText(it)}<button class="cx-tk-go" ${tkGoAttrs(it)}>${TK_GO}</button></div>`).join("");
    const waits = got.wait.length ? `<button class="cx-tk-waits" data-act="cx-tk-wait" aria-expanded="${!!S.cxTkWait}">${TK_WAITS.replace("{n}", got.wait.length)}<i aria-hidden="true">${S.cxTkWait ? "▴" : "▾"}</i></button>`
      + (S.cxTkWait ? got.wait.map((it) => `<div class="cx-tk-row wait">${tkText(it)}</div>`).join("") : "") : "";
    return `${tug}${line}<div class="sheet-bg" data-act="cx-tk"></div><div class="sheet cx-tk-sheet" role="dialog" aria-label="${TK_HEAD}"><div class="grip"></div>`
      + `<div class="top-row"><h3 style="flex:1">${TK_HEAD}</h3><button class="btn small ghost" data-act="cx-tk">${TK_CLOSE}</button></div>`
      + `${rows || `<p class="cx-tk-none">${TK_NONE}</p>`}${waits}`
      + `${codexSlim(m) && m.week_card ? `<p class="cx-tk-more"><button class="linkish" data-act="cx-tk-why">${TK_WHY}</button></p>` : ""}</div>`;
  }
  // 本週卡收起來的時候，「進行中」上面留一條細的兩軍態勢（Joy 2026-11-13「我還是想在首頁讓大家直觀地知道當前態勢 但是不想要像之前那樣佔那麼多版面」）：
  // 一行，兩頭寫兩軍的數字（Joy 11/13「兩軍相持加數字」），兩色一條加一句誰佔上風；點了拉起「這一季在打什麼」那一層（最上面是完整的拔河條）。本週卡露著、決戰面板開著時不畫（各自已有）
  const TK_TUG = "兩軍態勢"; // 待 joy 潤
  function tkTugHtml(m) {
    const w = m && m.week_card, s = w && w.sides;
    if (!s || !("guan" in s) || !("huang" in s) || !codexSlim(m) || codexWeekShow(m)) return "";
    if (typeof bpOn === "function" && bpOn(m)) return "";
    const g = s.guan | 0, h = s.huang | 0, at = g + h > 0 ? Math.round((g * 1000) / (g + h)) / 10 : 50, d = g - h;
    const cols = (m.sides_card && m.sides_card.cols) || [];
    const name = (k) => (cols.find((c) => c.id === k) || {}).name || (k === "guan" ? "官軍" : "黃巾");
    const side = Math.abs(d) < 10 ? "even" : d > 0 ? "guan" : "huang";
    const says = side === "even" ? "兩軍相持" : `${name(side)}${Math.abs(d) >= 30 ? "大佔上風" : "佔上風"}`; // 待 joy 潤（同本週卡那一句）
    return `<button class="cx-tug" data-act="cx-tk-why" aria-label="${TK_TUG}：${says}">`
      + `<span class="cx-tug-end side-guan" aria-hidden="true">${esc(name("guan").slice(0, 1))} ${g}</span><span class="cx-tug-bar" aria-hidden="true"><i style="width:${at}%"></i><u style="left:${at}%"></u></span><span class="cx-tug-end side-huang" aria-hidden="true">${h} ${esc(name("huang").slice(0, 1))}</span>`
      + `<b class="side-${side}">${says}</b><span class="cx-tug-go" aria-hidden="true">›</span></button>`;
  }
  // 江湖頁上面那一區瘦身（Joy 2026-11-13「上面這區還是很臃腫 而且是有必要一直一直出現在這裡嗎」；PM 的方向）：「進行中」開著、
  // 已經投靠了一方（沒投靠的人照舊看三方卡與投靠鈕）時，狀態列底下只留「進行中」那一行——屬性點、識海那幾條提示與章回收進「事」的清單，
  // 本週卡（第 N 週、主題、兩軍態勢）只在有事時露：換週的那一刻（這一週還沒看過）、這一回的大事在集結或開打；收起（×）或拉開過清單就算看過。
  // 「這一季在打什麼」是清單最底下一顆，攤開的那一層同本週卡的（main.js whyHtml）。main.js 介面重整那一支問這兩個
  function codexSlim(m) {
    return !!(m && m.codex && Array.isArray(m.codex.track)) && (!m.sides_card || !!m.sides_card.joined);
  }
  const tkWeekKey = (w) => `${w.label}${w.when}`;
  function codexWeekShow(m) {
    const w = m && m.week_card;
    if (!w) return false;
    const memo = tkMemo(), key = tkWeekKey(w);
    if (typeof wkHidden === "function" && wkHidden(m, "strip") && memo.week !== key) { memo.week = key; tkSave(); }
    return !!(w.chapter && w.chapter.live) || memo.week !== key;
  }
  // 「這一季在打什麼」那一層（清單最底下那一顆打開）：內容同本週卡拉起來的那一層
  const TK_SHEET = "這一季在打什麼"; // 待 joy 潤
  function codexWhyHtml(m) {
    if (!S.cxWhy || !m.week_card || typeof whyHtml !== "function") return "";
    const w = m.week_card;
    // 本週卡收起來的時候兩軍態勢還得看得到（Joy 11/13「哪邊還能看態勢」）：拔河條畫在這一層最上面
    const tug = typeof wkTugHtml === "function" && !(typeof bpOn === "function" && bpOn(m)) ? wkTugHtml(m, w) : "";
    return `<div class="sheet-bg" data-act="cx-why"></div><div class="sheet wk-sheet" role="dialog" aria-label="${TK_SHEET}"><div class="grip"></div>`
      + `<div class="top-row"><h3 style="flex:1">${TK_SHEET}</h3><button class="btn small ghost" data-act="cx-why">${TK_CLOSE}</button></div>`
      + `<p class="wk-sheet-th"><b>${esc(w.when)}</b>${esc(w.theme || "")}</p>${tug}${whyHtml(m, true)}</div>`;
  }
  function tkSeeAll() {
    const got = tkItems(S.main, null), items = got ? got.on : [];
    const memo = tkMemo();
    memo.seen = [...new Set([...memo.seen, ...items.map((x) => x.key), ...["orders", "bounty", "plan", "week", "seal"].map((k) => `d:${k}`)])].slice(-80);
    if (S.main && S.main.week_card) memo.week = tkWeekKey(S.main.week_card); // 拉開過清單：這一週的本週卡算看過
    tkSave();
  }

  async function codexClick(act, el, ev) {
    switch (act) {
        case "cx-seg": cxDraw(() => { S.cxSeg = el.dataset.seg; S.cxOpen = null; S.cxRead = null; }); break;
        case "cx-cat": cxDraw(() => { S.cxCat = el.dataset.cat; }); break;
        case "cx-grp": cxDraw(() => { S.cxThing = el.dataset.id; }); break;
        case "cx-open": {
          const key = el.dataset.key;
          cxDraw(() => { S.cxOpen = key; S.cxRead = null; });
          window.scrollTo && window.scrollTo(0, 0);
          const line = key.split(":").slice(1).join(":");
          cxSeen([`q:${line}`]);
          break;
        }
        case "cx-back": cxDraw(() => { if (S.cxRead) { S.cxRead = null; S.cxText = null; } else S.cxOpen = null; }); break;
        case "cx-read":
        case "cx-end": {
          const q = act === "cx-read" ? `i=${encodeURIComponent(el.dataset.i)}` : `line=${encodeURIComponent(el.dataset.line)}&end=${encodeURIComponent(el.dataset.end)}`;
          cxDraw(() => { S.cxRead = q; S.cxText = null; });
          window.scrollTo && window.scrollTo(0, 0);
          try { S.cxText = await api(`/api/codex/scene?${q}`); } catch (e) { S.cxRead = null; }
          renderPage();
          if (act === "cx-end") cxSeen([`e:${el.dataset.line}:${el.dataset.end}`]);
          break;
        }
        case "cx-map": mapGoto(el.dataset.loc); goTab("map"); break;
        case "cx-why": S.cxWhy = false; renderPage(); break;
        case "cx-tk-wait": S.cxTkWait = !S.cxTkWait; renderPage(); break;
        case "cx-tk-why": S.cxTk = false; S.cxWhy = true; renderPage(); break;
        case "cx-tk": S.cxTk = !S.cxTk; if (S.cxTk) tkSeeAll(); renderPage(); break;
        case "cx-tk-pin": { const memo = tkMemo(); memo.pin = memo.pin === el.dataset.key ? null : el.dataset.key; tkSave(); renderPage(); break; }
        case "cx-tk-go": {
          const d = el.dataset;
          S.cxTk = false;
          if (d.id) await choose(el, d.id);
          else if (d.loc) { mapGoto(d.loc); await goTab("map"); }
          else if (d.duty) { S.dutyOpen = true; renderPage(); }
          else if (d.legacy) { S.legacy = d.legacy; render(); }
          else if (d.hero) { S.heroTab = d.hero; if (d.open) { S.cxSeg = "qy"; S.cxOpen = d.open; S.cxRead = null; } await goTab("practice"); }
          else renderPage();
          break;
        }
    } // codexClick
  } // codexClick
  registerClicks(codexClick, ["cx-seg", "cx-cat", "cx-grp", "cx-open", "cx-back", "cx-read", "cx-end", "cx-map", "cx-why", "cx-tk-wait", "cx-tk-why", "cx-tk", "cx-tk-pin", "cx-tk-go"]);
