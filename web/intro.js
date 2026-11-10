/* 天下大勢的網頁前端：開局前導畫本（功能包 tianxia/features/intro/；Joy 2026-11-10「這種形式可以 想壓在60秒內」）。
 *
 * 新角色取完名號、站到潁川城門口之前（status.intro.pending），整頁蓋一層水墨畫本：圖慢慢推、人物淡入、字一句一句出來，
 * 右上角隨時「跳過」，點畫面換下一幕，最後一顆「進城」。跳過、看完、按進城都記看過（POST /api/intro/seen），之後不再自動播；
 * 設定裡多一顆「重看開場」。不改 app.js：跟 terms.js 一樣看 #app 畫了什麼（MutationObserver）。層掛在 body 上，輪詢重畫碰不到它。
 * 偏好減少動態效果的人：不推圖、不淡入，一樣一幕一幕點。字在 tianxia/features/intro/content/intro.json（待 joy 潤）。
 */
"use strict";

  let introBook = null; // GET /api/intro 拿到的畫本（一頁只拿一次）
  let introAsk = null; // 拿畫本的 Promise
  let introShown = false; // 這一次登入自動播過了（記看過送不出去也不再跳）
  let introTimer = 0;
  const introCalm = () => !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const introEsc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function introLoad() {
    if (!introAsk) {
      introAsk = fetch("/api/intro", { credentials: "same-origin" })
        .then((res) => (res.ok ? res.json() : null))
        .then((book) => { introBook = book; return book; })
        .catch(() => { introAsk = null; return null; }); // 斷線：下一次重畫再問
    }
    return introAsk;
  }

  function introSceneHtml(s) {
    const figs = (s.figures || []).map((f, k) => `<div class="intro-fig ${f.side === "l" ? "l" : "r"}${k ? " late" : ""}">`
      + `<img src="${introEsc(f.image)}" alt="${introEsc(f.name)}"><span class="intro-tag">${introEsc(f.name)}<small>${introEsc(f.tag)}</small></span></div>`).join("");
    const cry = (s.cry || []).map((t, k) => `<div class="intro-cry${k ? " b" : ""}">${introEsc(t)}</div>`).join("");
    const lines = (s.lines || []).map((t, k) => `<span style="transition-delay:${(0.4 + 1.8 * k).toFixed(1)}s">${introEsc(t)}</span>`).join("");
    const pan = s.pan || [-50, -50];
    return `<div class="intro-scene" data-ms="${Math.round((s.seconds || 8) * 1000)}">`
      + `<div class="intro-art"><img src="${introEsc(s.image)}" alt="" style="--x0:${pan[0]}%;--x1:${pan[1]}%;--dur:${(s.seconds || 8) + 1.2}s"></div>`
      + `${cry}${figs}<div class="intro-text"><p>${lines}</p></div></div>`;
  }

  function introClose() {
    clearTimeout(introTimer);
    const el = document.querySelector(".intro-layer");
    if (el) el.remove();
  }

  async function introSeen() {
    try {
      const res = await fetch("/api/intro/seen", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: "{}" });
      const data = res.ok ? await res.json() : null;
      if (data && data.main && typeof applyMain === "function") applyMain(data.main);
    } catch (e) { /* 斷線：這一次登入不再跳，下次登入再播一次 */ }
  }

  function introPlay(book, record) {
    introClose();
    if (!book || !(book.scenes || []).length) return;
    const dots = book.scenes.map(() => "<i></i>").join("");
    document.body.insertAdjacentHTML("beforeend", `<div class="intro-layer${introCalm() ? " calm" : ""}" role="dialog" aria-modal="true" aria-label="開場">`
      + `<div class="intro-stage" tabindex="0">${book.scenes.map(introSceneHtml).join("")}`
      + `<button class="intro-skip" type="button" data-intro="skip">${introEsc(book.skip)} ›</button>`
      + `<div class="intro-end"><button class="intro-go" type="button" data-intro="go">${introEsc(book.go)}</button>`
      + `<button class="intro-again" type="button" data-intro="again">${introEsc(book.again)}</button></div>`
      + `<div class="intro-dots">${dots}</div></div></div>`);
    const layer = document.querySelector(".intro-layer");
    const stage = layer.querySelector(".intro-stage");
    const scenes = [...layer.querySelectorAll(".intro-scene")];
    const marks = [...layer.querySelectorAll(".intro-dots i")];
    const end = layer.querySelector(".intro-end");
    let at = -1;
    let done = false;
    const finish = () => {
      clearTimeout(introTimer);
      end.classList.add("on");
      if (record && !done) { done = true; introSeen(); }
    };
    const show = (n) => {
      clearTimeout(introTimer);
      at = n;
      scenes.forEach((s, k) => s.classList.toggle("on", k === n));
      marks.forEach((d, k) => d.classList.toggle("on", k === n));
      end.classList.remove("on");
      introTimer = setTimeout(next, +scenes[n].dataset.ms || 8000);
    };
    const next = () => (at < scenes.length - 1 ? show(at + 1) : finish());
    layer.addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-intro]");
      if (!btn) { if (!end.classList.contains("on")) next(); return; }
      const what = btn.dataset.intro;
      if (what === "skip") { scenes.forEach((s, k) => s.classList.toggle("on", k === scenes.length - 1)); finish(); introClose(); }
      else if (what === "go") introClose();
      else if (what === "again") show(0);
    });
    stage.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); if (!end.classList.contains("on")) next(); } });
    stage.focus({ preventScroll: true });
    show(0);
  }

  // 設定頁底下的「重看開場」：有 status.intro（開關開著）才放
  function introAddReplay() {
    const st = typeof S !== "undefined" && S.main && S.main.status && S.main.status.intro;
    if (!st) return;
    for (const box of document.querySelectorAll('.sheet[aria-label="設定"]')) {
      if (box.querySelector(".intro-replay")) continue;
      box.insertAdjacentHTML("beforeend", `<button class="btn ghost intro-replay" type="button">${introEsc((introBook && introBook.replay) || "重看開場")}</button>`);
      box.querySelector(".intro-replay").addEventListener("click", async () => { introPlay(await introLoad(), false); });
    }
  }

  function introWatch() {
    const inGame = typeof S !== "undefined" && S.stage === "game";
    if (!inGame) { introShown = false; introClose(); return; }
    introAddReplay();
    const st = S.main && S.main.status && S.main.status.intro;
    if (!st || !st.pending || introShown) return;
    introShown = true;
    introLoad().then((book) => { if (book) introPlay(book, true); else introShown = false; });
  }

  let introQueued = false;
  if (typeof MutationObserver !== "undefined" && typeof document !== "undefined" && document.getElementById) { // 網頁測試的 node 沒有 DOM：不看
    const target = document.getElementById("app");
    if (target) {
      new MutationObserver(() => {
        if (introQueued) return;
        introQueued = true;
        setTimeout(() => { introQueued = false; introWatch(); }, 0);
      }).observe(target, { childList: true, subtree: true });
    }
  }
