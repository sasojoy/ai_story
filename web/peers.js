/* 天下大勢的網頁前端：名帖的畫法與畫布（全部拆包第 66 批從 app.js 切出來）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 */
"use strict";

  // ── 名帖（Joy 2026-10-19：抱拳改成互贈名帖；一張畫布當自己的標籤，頭銜系統照存檔算、按一下刷新，再留一句自題）──
  // 名帖固定是紙色、不跟深淺色走（墨、朱砂、石青三色要在紙上看得清楚；跟 mingtie.INKS 同一份）。
  // 筆劃是 [墨色, 筆粗, x0, y0, x1, y1, …]，座標在 300×400 的畫布上（mingtie.WIDTH／HEIGHT）。字待 joy 潤
  const MT_INKS = ["#24211d", "#b23a2a", "#2f5d78"];
  const MT_PENS = [3, 10];
  const mtPolyline = (s) => (s.length >= 6
    ? `<polyline points="${s.slice(2).join(" ")}" stroke="${MT_INKS[s[0]] || MT_INKS[0]}" stroke-width="${MT_PENS[s[1]] || MT_PENS[0]}"/>`
    : `<circle cx="${s[2]}" cy="${s[3]}" r="${(MT_PENS[s[1]] || MT_PENS[0]) / 2}" fill="${MT_INKS[s[0]] || MT_INKS[0]}"/>`);
  const mtStrokesSvg = (strokes) => (strokes || []).map(mtPolyline).join("");
  // 一張名帖：畫在底下、右上直書名號、名號底下一方朱印（名號前三個字＋印）、下緣頭銜與自題。cls：thumb（玩家卡縮圖、名帖匣）、zoom、edit
  function mtSeal(name) {
    const chars = [...String(name || "")].slice(0, 3);
    if (chars.length < 3) chars.push("之"); // 兩個字的名號寫「某某之印」
    while (chars.length < 3) chars.push("");
    // 2×2 一格一字，照印文的讀法：右行由上而下、再左行
    return `<span class="mt-seal" aria-hidden="true">${[chars[2], chars[0], "印", chars[1]].map((ch) => `<i>${esc(ch)}</i>`).join("")}</span>`;
  }
  function mtCardHtml(card, name, cls = "", pad = false) {
    const c = card || { strokes: [], titles: [], motto: "" };
    return `<div class="mt-card ${cls}">
      <svg class="mt-ink${pad ? " mt-pad" : ""}" ${pad ? 'id="mt-pad" ' : ""}viewBox="0 0 300 400" preserveAspectRatio="none" fill="none" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${mtStrokesSvg(c.strokes)}</svg>
      <div class="mt-name">${esc(name)}</div>${mtSeal(name)}
      <div class="mt-foot">${c.titles && c.titles.length ? `<div class="mt-titles">${c.titles.map((t) => `<span>${esc(t)}</span>`).join("")}</div>` : ""}<p class="mt-motto">${c.motto ? `「${esc(c.motto)}」` : ""}</p></div>
      ${c.hidden ? '<p class="mt-hidden">這一張的畫與題字看不到了。</p>' : ""}
    </div>`;
  }

  // 放大看一張（玩家卡的縮圖、名帖匣裡收到的）：別人的那一張底下有「檢舉」；看不到的那一張不能再檢舉
  function mtZoomHtml() {
    const z = S.mtZoom;
    const me = S.main && S.main.status && S.main.status.name;
    const can = !z.card.hidden && z.name !== me;
    return `<div class="mt-zoom-layer" data-act="mt-unzoom" role="dialog" aria-label="${esc(z.name)}的名帖">
      <div class="mt-zoom-box">${mtCardHtml(z.card, z.name, "zoom")}${z.when ? `<p class="mt-when">${esc(z.when)}</p>` : ""}
        <div class="row"><button class="btn ghost small" data-act="mt-unzoom">收起</button>${can ? '<button class="btn ghost small mt-report" data-act="mt-report">檢舉這一張</button>' : ""}</div></div></div>`;
  }
  async function mtReport() {
    const z = S.mtZoom;
    if (!z) return;
    ask(`檢舉${z.name}的這一張名帖：你不會再看到它的畫與題字；被檢舉夠多次，大家都看不到，管理者會看。確定？`, "檢舉", async () => {
      await busy(async () => {
        const r = await api("/api/mingtie/report", { name: z.name, version: z.card.version });
        if (r.mingtie) S.mingtie = r.mingtie;
        S.mtZoom = null;
        toast((r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim() || "已檢舉。");
        render();
        if (S.peer && S.peer.name === z.name) refreshPeer();
      });
    });
  }

  async function loadMingtie() {
    S.mingtie = await api("/api/mingtie");
    if (S.tab === "news" && S.news === "mingtie") renderPage();
  }

  // 見聞「名帖匣」：自己那一張（製作或修改）、今天還能定稿幾次遞幾張、收到的那幾張（新的在前，點了放大）
  function mingtieBoxHtml(m) {
    if (!m) return '<p class="muted">載入中…</p>';
    const me = S.main.status.name;
    const mine = m.mine
      ? `<div class="mt-mine"><div data-act="mt-zoom-mine">${mtCardHtml(m.mine, me, "mine")}</div>`
      : `<div class="mt-mine empty"><p>你還沒有名帖。做一張，就能在玩家卡上跟人互換。</p>`;
    return `<div class="card mt-box-head">${mine}
        <div class="mt-mine-side"><button class="btn primary" data-act="mt-edit"${m.made_left ? "" : " disabled"}>${m.mine ? "修改名帖" : "製作名帖"}</button>
          <p class="muted">今天還能定稿 ${m.made_left} 次、遞出 ${m.sent_left} 張。不花銀兩。</p></div></div></div>
      <p class="report-group">收到的名帖（${m.box.length}）</p>
      ${m.box.length ? `<div class="mt-grid">${m.box.map((x, i) => `<button class="mt-cell" data-act="mt-zoom-box" data-i="${i}">${mtCardHtml(x.card, x.name, "thumb")}<small>${esc(x.name)}</small></button>`).join("")}</div>`
        : '<p class="muted">還沒收到誰的名帖。在「此地還有」點人的名字，玩家卡上可以遞名帖。</p>'}`;
  }

  // 製作名帖（全螢幕一層）：畫布、三色兩筆、上一筆、清空、現成的畫；頭銜從掙到的裡面挑（刷新＝隨機換一批）；自題一句；定稿
  function mtEditOpen() {
    const m = S.mingtie;
    if (!m) return;
    const pool = m.pool || [];
    const mine = m.mine || { strokes: [], titles: [], motto: "" };
    const titles = mine.titles.filter((t) => pool.includes(t));
    S.mtEdit = { strokes: mine.strokes.map((s) => s.slice()), titles: titles.length ? titles : pool.slice(0, m.limits.titles), motto: mine.motto, ink: 0, pen: 0, note: "" };
    render();
  }
  function mtPoints(strokes) { return strokes.reduce((n, s) => n + (s.length - 2) / 2, 0); }
  function mtEditHtml() {
    const E = S.mtEdit, m = S.mingtie, L = m.limits;
    const me = S.main.status.name;
    const pts = mtPoints(E.strokes);
    const chip = (t) => `<button class="mt-chip${E.titles.includes(t) ? " on" : ""}" data-act="mt-title" data-t="${esc(t)}">${esc(t)}</button>`;
    return `<div class="mt-layer" role="dialog" aria-label="製作名帖">
      <div class="mt-bar"><button class="book-back" data-act="mt-close">‹ 返回</button><b>製作名帖</b><span>今天還能定稿 ${m.made_left} 次</span></div>
      <div class="mt-edit-col">
        <div class="mt-stage">${mtCardHtml({ strokes: E.strokes, titles: E.titles, motto: E.motto }, me, "edit", true)}</div>
        <div class="mt-tools">
          ${MT_INKS.map((c, i) => `<button class="mt-ink-btn${E.ink === i ? " on" : ""}" data-act="mt-ink" data-i="${i}" style="--c:${c}" aria-label="${esc(L.ink_names[i] || "")}"><i></i>${esc(L.ink_names[i] || "")}</button>`).join("")}
          ${["細", "粗"].map((n, i) => `<button class="mt-pen-btn${E.pen === i ? " on" : ""}" data-act="mt-pen" data-i="${i}">${n}</button>`).join("")}
        </div>
        <div class="mt-tools"><button class="btn ghost small" data-act="mt-undo"${E.strokes.length ? "" : " disabled"}>上一筆</button><button class="btn ghost small" data-act="mt-clear"${E.strokes.length ? "" : " disabled"}>清空</button>
          <select class="input mt-preset" id="mt-preset" aria-label="現成的畫"><option value="">現成的畫…</option>${(m.presets || []).map((p) => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join("")}</select></div>
        <p class="muted mt-count" id="mt-count">${E.strokes.length}／${L.strokes} 筆・墨 ${pts}／${L.points}</p>
        <div class="mt-sec"><span>頭銜（挑 ${L.titles} 個以內）</span><button class="btn ghost small" data-act="mt-shuffle"${m.pool.length > L.titles ? "" : " disabled"}>刷新頭銜</button></div>
        <div class="mt-chips">${m.pool.length ? m.pool.map(chip).join("") : '<p class="muted">還沒掙到頭銜。名聲、陣營、榜單、絕學……江湖上做出點事，這裡就有。</p>'}</div>
        <div class="mt-sec"><span>自題一句（${L.motto} 字內，可以不寫）</span></div>
        <input class="input" id="mt-motto" maxlength="${L.motto}" value="${esc(E.motto)}" placeholder="例：一劍霜寒十四州" aria-label="自題一句">
        <p class="form-msg" id="mt-note" role="alert">${esc(E.note || "")}</p>
        <button class="btn primary mt-go" data-act="mt-save"${m.made_left ? "" : " disabled"}>定稿</button>
      </div></div>`;
  }
  // 工具列按了只換那一層（不重畫底下的頁面），畫布照 S.mtEdit 重新掛手勢
  function mtEditRedraw() {
    const old = document.querySelector(".mt-layer");
    if (!old || !S.mtEdit) return;
    const top = old.querySelector(".mt-edit-col")?.scrollTop || 0;
    old.insertAdjacentHTML("afterend", mtEditHtml());
    old.remove();
    const col = document.querySelector(".mt-layer .mt-edit-col");
    if (col) col.scrollTop = top;
    mtPadReady();
  }
  function mtPadReady() {
    const pad = document.getElementById("mt-pad");
    const E = S.mtEdit;
    if (!pad || !E) return;
    const L = S.mingtie.limits;
    let cur = null;
    const at = (ev) => {
      const r = pad.getBoundingClientRect();
      return [Math.max(0, Math.min(L.width, Math.round(((ev.clientX - r.left) / r.width) * L.width))),
        Math.max(0, Math.min(L.height, Math.round(((ev.clientY - r.top) / r.height) * L.height)))];
    };
    const paint = () => {
      pad.innerHTML = mtStrokesSvg(cur ? [...E.strokes, cur] : E.strokes);
      const n = document.getElementById("mt-count");
      if (n) n.textContent = `${E.strokes.length + (cur ? 1 : 0)}／${L.strokes} 筆・墨 ${mtPoints(cur ? [...E.strokes, cur] : E.strokes)}／${L.points}`;
    };
    pad.addEventListener("pointerdown", (ev) => {
      ev.preventDefault();
      if (E.strokes.length >= L.strokes || mtPoints(E.strokes) >= L.points) { E.note = "畫布上的墨已經滿了：按「上一筆」或「清空」再畫。"; const n = document.getElementById("mt-note"); if (n) n.textContent = E.note; return; }
      pad.setPointerCapture(ev.pointerId);
      cur = [E.ink, E.pen, ...at(ev)];
      paint();
    });
    pad.addEventListener("pointermove", (ev) => {
      if (!cur) return;
      ev.preventDefault();
      const [x, y] = at(ev);
      const lx = cur[cur.length - 2], ly = cur[cur.length - 1];
      if (Math.abs(x - lx) + Math.abs(y - ly) < 4) return; // 太密的點不收：一張名帖的墨有上限
      if (mtPoints(E.strokes) + (cur.length - 2) / 2 >= L.points) return;
      cur.push(x, y);
      paint();
    });
    const end = () => {
      if (!cur) return;
      E.strokes.push(cur);
      cur = null;
      mtEditRedraw();
    };
    pad.addEventListener("pointerup", end);
    pad.addEventListener("pointercancel", end);
  }
  async function mtSave() {
    const E = S.mtEdit;
    if (!E) return;
    const before = S.mingtie.mine ? S.mingtie.mine.version : 0;
    await busy(async () => {
      const r = await api("/api/mingtie/save", { strokes: E.strokes, titles: E.titles, motto: E.motto });
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      if (r.mingtie) S.mingtie = r.mingtie;
      if (r.mingtie && r.mingtie.mine && r.mingtie.mine.version > before) {
        S.mtEdit = null;
        toast(text || "名帖定稿了。");
        render();
      } else {
        E.note = text;
        mtEditRedraw();
      }
    });
  }
