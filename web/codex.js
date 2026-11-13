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
    const acts = q.scenes.map((sc, i) => `<button class="cx-act" data-act="cx-read" data-i="${sc.i}"><span class="n">第${"一二三四五六七八九十"[i] || i + 1}幕</span>`
      + `<span class="x"><b>${esc(sc.title)}</b><small>${CX_YOU}：<q>${esc(sc.pick)}</q></small></span><span class="r">${CX_REREAD} ›</span></button>`).join("");
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
    } // codexClick
  } // codexClick
  registerClicks(codexClick, ["cx-seg", "cx-cat", "cx-grp", "cx-open", "cx-back", "cx-read", "cx-end", "cx-map"]);
