/* 天下大勢的網頁前端：有所感的畫布、悟來的那一筆、神品意境取名（全部拆包第 66 批從 app.js 切出來）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 */
"use strict";

  const SENSE_DRAW = "sense:draw"; // 有所感進了感悟狀態：「把心中的形畫下來」叫出畫布（sensing.DRAW），畫好送 /api/sense

  // 感悟悟來的意境畫的那一筆（0～100 的點位）畫成小 SVG（同 journal.glyph_svg）
  function glyphSvg(points, cls) {
    const pts = (points || []).filter((p) => Array.isArray(p) && p.length >= 2);
    if (pts.length < 2) return "";
    const path = pts.map(([x, y]) => `${Number(x) | 0},${Number(y) | 0}`).join(" ");
    return `<svg class="${cls}" viewBox="-8 -8 116 116" aria-hidden="true"><polyline points="${path}" fill="none" stroke="currentColor" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
  }

  // ── 有所感的畫布（悟意境設計 0.2 第 3、4 步）──
  // 一筆畫到底：手指按下去開始一筆（之前畫的清掉），離開畫布就算畫完；不滿意清掉重畫。畫完問伺服器這一筆讀不讀得出來
  // （/api/sense_read，跟送出時讀的是同一套 glyph.read），畫布底下只寫成不成，不寫筆畫的幾何。送出帶點位與一張小 PNG（只轉交給模型看圖，不存）
  const SENSE_SIZE = 256;
  function sensePadHtml() {
    const ready = S.sensePts.length > 1;
    return `<div class="sense-pad" id="sense-pad">
        <div class="sense-hint">此刻心中有一個形——用手指一筆畫下來。</div>
        <canvas class="sense-canvas" id="sense-canvas" width="${SENSE_SIZE}" height="${SENSE_SIZE}" aria-label="畫布：一筆畫到底"></canvas>
        <div class="sense-note" id="sense-note">${esc(S.senseNote || (ready ? "" : "手指離開畫布，就算畫完。"))}</div>
        <div class="sense-acts">
          <button class="btn small" data-act="sense-clear" ${ready ? "" : "disabled"}>清掉重畫</button>
          <button class="btn primary small" data-act="sense-send" ${ready ? "" : "disabled"}>就是這個形</button>
        </div>
      </div>`;
  }

  function closeSense() {
    S.sensing = false;
    S.sensePts = [];
    S.senseNote = "";
    S.stroking = false;
  }

  function senseInk(ctx) {
    ctx.clearRect(0, 0, SENSE_SIZE, SENSE_SIZE);
    ctx.lineWidth = 7;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue("--ink").trim() || "#222";
    const pts = S.sensePts;
    if (pts.length < 2) return;
    ctx.beginPath();
    ctx.moveTo(pts[0][0], pts[0][1]);
    for (const [x, y] of pts.slice(1)) ctx.lineTo(x, y);
    ctx.stroke();
  }

  function sensePadReady() {
    const canvas = document.getElementById("sense-canvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    senseInk(ctx);
    let t0 = 0;
    const at = (ev) => {
      const r = canvas.getBoundingClientRect();
      return [
        Math.round(((ev.clientX - r.left) / r.width) * SENSE_SIZE),
        Math.round(((ev.clientY - r.top) / r.height) * SENSE_SIZE),
        Math.round(performance.now() - t0),
      ];
    };
    canvas.addEventListener("pointerdown", (ev) => {
      if (S.busy) return;
      ev.preventDefault();
      canvas.setPointerCapture(ev.pointerId);
      t0 = performance.now();
      S.stroking = true;
      S.sensePts = [at(ev)];
      S.senseNote = "";
      senseInk(ctx);
    });
    canvas.addEventListener("pointermove", (ev) => {
      if (!S.stroking) return;
      ev.preventDefault();
      if (S.sensePts.length < 600) S.sensePts.push(at(ev)); // 跟 glyph.MAX_POINTS 一樣多
      senseInk(ctx);
    });
    const end = async () => {
      if (!S.stroking) return;
      S.stroking = false;
      const pad = document.getElementById("sense-pad");
      const ready = S.sensePts.length > 1;
      if (pad) pad.querySelectorAll('[data-act="sense-clear"], [data-act="sense-send"]').forEach((b) => { b.disabled = !ready; });
      const pts = S.sensePts;
      try {
        const r = await api("/api/sense_read", { points: pts });
        if (S.sensePts !== pts) return; // 等回應時又畫了一筆
        S.senseNote = r.ok ? "心中的形已經落下。" : (r.problem || ""); // 不寫筆畫讀到什麼（企劃者 2026-10-06：留住驚喜）
      } catch (e) { S.senseNote = ""; }
      const note = document.getElementById("sense-note");
      if (note) note.textContent = S.senseNote;
    };
    canvas.addEventListener("pointerup", end);
    canvas.addEventListener("pointercancel", end);
  }

  async function senseSend() {
    const canvas = document.getElementById("sense-canvas");
    const pad = document.getElementById("sense-pad");
    if (!canvas || S.sensePts.length < 2) return;
    // 小 PNG：白底黑線（模型看圖用），跟畫面上的顏色無關
    const small = document.createElement("canvas");
    small.width = small.height = SENSE_SIZE;
    const sx = small.getContext("2d");
    sx.fillStyle = "#fff";
    sx.fillRect(0, 0, SENSE_SIZE, SENSE_SIZE);
    sx.lineWidth = 7;
    sx.lineCap = sx.lineJoin = "round";
    sx.strokeStyle = "#000";
    sx.beginPath();
    S.sensePts.forEach(([x, y], i) => (i ? sx.lineTo(x, y) : sx.moveTo(x, y)));
    sx.stroke();
    const png = small.toDataURL("image/png").split(",")[1] || "";
    const sent = await busy(async () => {
      pad.classList.add("brewing"); // 等模型取名：整塊畫布微微晃（同煉製的爐子）
      pad.querySelectorAll("button").forEach((b) => { b.disabled = true; });
      const send = pad.querySelector('[data-act="sense-send"]');
      send.textContent = "心念漸凝……";
      const stop = watchQueue(send, "心念漸凝……");
      try {
        const r = await api("/api/sense", { points: S.sensePts, png });
        closeSense();
        applyMain(r.main);
        window.scrollTo({ top: 0, behavior: "smooth" });
      } finally { stop(); }
    });
    if (sent && document.querySelector("#sense-pad.brewing")) renderPage(); // 失敗了（伺服器擋下來、連不上）：畫布還原，那一筆留著
  }

  // 神品意境自己取名（FB-901）：送 /api/choose 帶 text。名字不合格、這一季全服撞名時伺服器回一句話，
  // 表單留著、字也留著（同絕學定名那張），改一改再送；取成了選項就沒了，輸入框收起、回頁首看結果
  async function godName(form, text) {
    await busy(async () => {
      form.querySelectorAll("input, button").forEach((el) => { el.disabled = true; });
      try {
        const r = await api("/api/choose", { id: OWN_NAME_ID, text });
        const done = !((r.main && r.main.options) || []).some((o) => o.id === OWN_NAME_ID);
        if (done) S.godNaming = false;
        applyMain(r.main);
        const said = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
        if (said) toast(said);
        if (done) window.scrollTo({ top: 0, behavior: "smooth" });
        else {
          const again = document.querySelector("#own-name-form .input");
          if (again) { again.value = text; again.focus(); }
        }
      } finally {
        form.querySelectorAll("input, button").forEach((el) => { el.disabled = false; });
      }
    });
  }
