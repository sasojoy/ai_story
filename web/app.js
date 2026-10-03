/* 天下大勢的網頁前端：沒有建置步驟、不靠外部函式庫。
 *
 * 畫面只有三種：登入、取名號、遊戲。遊戲畫面 = 頂上的狀態列 + 一頁內容 + 底部五個分頁：
 *   江湖（場景與選項）、修練（練功、閉關、功法庫、名冊）、煉製、輿圖、見聞（戰報、大勢、傳聞、江湖史、紀錄）。
 * 設定與管理者工具收在右上角的抽屜裡。
 *
 * 伺服器給的 HTML（場景、角色卡、戰報、江湖紀錄、地圖）已經在伺服器端跳脫過；
 * 這裡自己組的字串一律經過 esc()。
 */
(() => {
  "use strict";

  const TABS = [
    { id: "jianghu", ico: "江", name: "江湖" },
    { id: "practice", ico: "修", name: "修練" },
    { id: "craft", ico: "煉", name: "煉製" },
    { id: "map", ico: "圖", name: "輿圖" },
    { id: "news", ico: "聞", name: "見聞" },
  ];
  const NEWS = [
    { id: "reports", name: "戰報" },
    { id: "trends", name: "大勢" },
    { id: "rumors", name: "傳聞" },
    { id: "chronicle", name: "江湖史" },
    { id: "journal", name: "紀錄" },
  ];
  const POLL_MS = 10000;
  const KINDS = ["武學", "內功"];

  const S = {
    stage: "boot",
    gateMode: "login",
    main: null,
    mainKey: "",
    tab: "jianghu",
    busy: false,
    menxia: null,
    message: "",
    person: null,
    kind: "武學",
    craftKind: "武學",
    craftSel: [],
    craftLine: "",
    map: null,
    layer: "situation",
    fitMap: true,
    news: "reports",
    reports: null,
    reportOpen: false,
    showMore: false,
    sheet: false,
    admin: null,
    unseen: false,
    offline: false,
  };

  const $app = document.getElementById("app");
  const $toast = document.getElementById("toast");

  // ── 工具 ──
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pct = (a, b) => (b > 0 ? Math.max(0, Math.min(100, (a / b) * 100)) : 0);

  let toastTimer = 0;
  function toast(text) {
    $toast.textContent = text;
    $toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => $toast.classList.remove("show"), 3200);
  }

  async function api(path, body) {
    const opts = body === undefined
      ? { credentials: "same-origin" }
      : { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
    let res;
    try {
      res = await fetch(path, opts);
    } catch (e) {
      setOffline(true);
      throw e;
    }
    setOffline(false);
    if (res.status === 401) {
      S.stage = "gate";
      render();
      throw new Error("請先登入。");
    }
    if (res.status === 409) {
      S.stage = "create";
      render();
      throw new Error("這個帳號還沒有角色。");
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = data.error || data.detail || "出了點問題，請再試一次。";
      toast(msg);
      throw new Error(msg);
    }
    return data;
  }

  function setOffline(v) {
    if (S.offline === v) return;
    S.offline = v;
    const el = document.querySelector(".offline");
    if (v && !el) document.body.insertAdjacentHTML("beforeend", '<div class="offline">連不上伺服器，重試中…</div>');
    if (!v && el) el.remove();
  }

  function enter(data) {
    if (data.stage === "game") {
      S.stage = "game";
      setMain(data.main);
    } else {
      S.stage = data.stage === "create" ? "create" : "gate";
    }
    render();
  }

  function setMain(main) {
    const key = JSON.stringify(main);
    const changed = key !== S.mainKey;
    S.main = main;
    S.mainKey = key;
    return changed;
  }

  // ── 整體 ──
  function render() {
    if (S.stage === "gate") return renderGate();
    if (S.stage === "create") return renderCreate();
    if (S.stage !== "game") return;
    $app.innerHTML = `
      <div class="shell">
        <header class="top" id="top">${topHtml()}</header>
        <main class="page" id="page"></main>
      </div>
      <nav class="tabs"><div class="tabs-inner">${TABS.map((t) => `
        <button class="tab ${S.tab === t.id ? "on" : ""}" data-act="tab" data-tab="${t.id}">
          <span class="ico">${t.ico}</span>${t.name}${t.id === "news" && S.unseen && S.tab !== "news" ? '<i class="dot"></i>' : ""}
        </button>`).join("")}</div></nav>
      ${S.sheet ? sheetHtml() : ""}`;
    renderPage();
  }

  function renderTop() {
    const el = document.getElementById("top");
    if (el) el.innerHTML = topHtml();
  }

  function topHtml() {
    const s = S.main.status;
    const team = s.team.map((m) => `🧍 ${esc(m.name)} 第${m.level}級 氣血 ${m.hp}/${m.hp_max}`).join("　");
    return `
      <div class="top-row">
        <div class="who" data-act="toggle-more">
          <div class="who-name">${esc(s.name)}<small>${esc(s.affiliation)}${s.anonymous ? "・匿名" : ""}・第${s.level}級</small></div>
          <div class="where">📍 ${esc(s.location)}　第 ${s.day} 天 ${esc(s.clock)}${s.busy_hours != null ? `　🧘 閉關中，約 ${s.busy_hours} 小時後出關` : ""}</div>
        </div>
        <button class="icon-btn" data-act="sheet" aria-label="設定">⚙</button>
      </div>
      <div class="vitals">
        <div class="bar stam" title="體力"><i style="width:${pct(s.stamina, s.stamina_max)}%"></i><span>體力 ${s.stamina}/${s.stamina_max}</span></div>
        <div class="bar hp" title="氣血"><i style="width:${pct(s.hp, s.hp_max)}%"></i>${s.injury >= 1 ? `<b style="width:${pct(s.injury, s.hp_max + s.injury)}%"></b>` : ""}<span>氣血 ${s.hp}/${s.hp_max}${s.injury >= 1 ? `・傷 ${s.injury}` : ""}</span></div>
        <div class="num"><em>銀</em>${s.silver}</div>
        <div class="num"><em>心得</em>${s.xinde}</div>
      </div>
      ${S.showMore ? `<div class="more-stats">
        ${s.minor.map(([k, v]) => `${esc(k)} ${v}`).join("　")}　｜　${s.attrs.map(([k, v]) => `${esc(k)} ${v}`).join("　")}
        ${team ? `<br>${team}` : ""}
      </div>` : ""}
      ${s.hint ? `<div class="more-stats"><span class="hint">${esc(s.hint)}</span></div>` : ""}`;
  }

  function renderPage() {
    const page = document.getElementById("page");
    if (!page) return;
    const fn = { jianghu: pageJianghu, practice: pagePractice, craft: pageCraft, map: pageMap, news: pageNews }[S.tab];
    page.innerHTML = fn();
    afterPage();
  }

  function afterPage() {
    if (S.tab === "map") {
      const wrap = document.querySelector(".map-wrap");
      const here = wrap && wrap.querySelector(`[data-loc="${CSS.escape(S.map?.selected || "")}"]`);
      if (wrap && here && !S.fitMap) {
        const box = here.getBoundingClientRect();
        const outer = wrap.getBoundingClientRect();
        wrap.scrollLeft += box.left - outer.left - outer.width / 2;
        wrap.scrollTop += box.top - outer.top - outer.height / 2;
      }
    }
  }

  // ── 登入與取名號 ──
  function renderGate() {
    const reg = S.gateMode === "register";
    $app.innerHTML = `
      <div class="gate">
        <div class="brand"><div class="seal">勢</div><h1>天下大勢</h1><p>亂世江湖，從潁川城門口開始</p></div>
        <div class="seg">
          <button class="${reg ? "" : "on"}" data-act="gate" data-mode="login">登入</button>
          <button class="${reg ? "on" : ""}" data-act="gate" data-mode="register">註冊</button>
        </div>
        <form id="gate-form" class="card">
          <label class="field"><span>帳號</span><input class="input" name="login" autocomplete="username" autocapitalize="off" ${reg ? 'placeholder="英文字母、數字、底線，3～20 字"' : ""} required></label>
          <label class="field"><span>密碼</span><input class="input" type="password" name="password" autocomplete="${reg ? "new-password" : "current-password"}" ${reg ? 'placeholder="至少 6 字"' : ""} required></label>
          ${reg ? '<label class="field"><span>再輸入一次密碼</span><input class="input" type="password" name="again" autocomplete="new-password" required></label>' : ""}
          <button class="btn primary" type="submit">${reg ? "註冊" : "登入"}</button>
        </form>
      </div>`;
  }

  function renderCreate() {
    $app.innerHTML = `
      <div class="gate">
        <div class="brand"><div class="seal">勢</div><h1>天下大勢</h1><p>這個帳號還沒有角色</p></div>
        <form id="create-form" class="card">
          <label class="field"><span>取一個名號，踏入江湖</span><input class="input" name="name" maxlength="16" placeholder="例如：沈青衫" required></label>
          <button class="btn primary" type="submit">建立角色</button>
        </form>
        <button class="linkish" data-act="logout">換一個帳號</button>
      </div>`;
  }

  // ── 江湖 ──
  function pageJianghu() {
    const m = S.main;
    const now = m.card
      ? `<div class="card battle-card">${m.card}${m.latest || ""}
           ${m.card_id != null ? `<button class="linkish" data-act="report" data-id="${m.card_id}">看完整戰報 ›</button>` : ""}</div>`
      : m.latest ? `<div class="now">${m.latest}</div>` : "";
    const free = m.free_text != null
      ? `<form class="free" id="free-form"><input class="input" name="text" maxlength="20" placeholder="${esc(m.free_text || "輸入你想做的事（20字內）")}"><button class="btn primary small" type="submit">送出</button></form>`
      : "";
    return `
      <details class="fold quest"><summary>📜 主線與目標</summary><div class="fold-body">${m.quest}</div></details>
      ${now}
      <section class="card scene">${m.scene}</section>
      ${free}
      <div class="options">${m.options.map((o, i) => `
        <button class="btn ${o.id.startsWith("move:") ? "go" : ""}" data-act="choose" data-id="${esc(o.id)}" ${o.enabled ? "" : "disabled"}>
          <span class="k">${o.id.startsWith("move:") ? "→" : i + 1}</span><span>${esc(o.label)}</span>
        </button>`).join("")}
      </div>
      <div class="mini" data-act="tab" data-tab="map" role="button" aria-label="展開輿圖">${m.minimap}</div>
      <button class="linkish" data-act="news" data-news="journal">看江湖紀錄 ›</button>`;
  }

  // ── 修練 ──
  function pagePractice() {
    const x = S.menxia;
    if (!x) return '<p class="muted">載入中…</p>';
    const s = S.main.status;
    return `
      <div class="msg" id="mx-msg">${S.message}</div>
      <div class="card">
        <div class="seg">${KINDS.map((k) => `<button class="${S.kind === k ? "on" : ""}" data-act="kind" data-kind="${k}">${k}</button>`).join("")}</div>
        <div class="row">
          <button class="btn primary" data-act="mx" data-op="practice">鍛鍊${esc(S.kind)}</button>
          <button class="btn" data-act="mx" data-op="heal" ${s.injury >= 1 ? "" : "disabled"}>療傷</button>
        </div>
        <p class="muted">${x.rules.replace(/<\/?p>/g, "")}</p>
      </div>
      <div class="label">自創功法</div>
      <form class="card" id="create-skill">
        <p class="muted">取名就決定了屬性、威力與成長，全服不能重名。目前這一門${esc(S.kind)}的欄位空著才能自創。</p>
        <div class="row"><input class="input" name="name" maxlength="12" placeholder="幫你的${esc(S.kind)}取個名字" style="flex:2"><button class="btn" type="submit">自創</button></div>
      </form>
      <div class="label">閉關</div>
      <form class="card" id="seclude">
        <p class="muted">閉關可以得到心得，期間氣血回復加倍；閉關中不能做別的事。</p>
        <div class="row">
          <select class="input" name="hours">${[1, 2, 4, 6, 8, 12].map((h) => `<option value="${h}" ${h === 8 ? "selected" : ""}>${h} 小時</option>`).join("")}</select>
          <button class="btn small" type="submit">開始閉關</button>
        </div>
      </form>
      <div class="label">功法庫</div>
      ${x.arts.length ? `<div class="list">${x.arts.map((a) => `<button data-act="switch" data-id="${esc(a.id)}">改練：${esc(a.label)}</button>`).join("")}</div>`
        : '<p class="muted">煉出來還沒配上身的功法會放在這裡。改練會把目前那一門收回庫裡，熟練度各自保留。</p>'}
      <div class="label">門下</div>
      <details class="fold" open><summary>本人</summary><div class="fold-body">${x.player_card}</div></details>
      <div class="list">${x.roster.map((r) => `<button class="${x.person === r.key ? "on" : ""}" data-act="person" data-key="${esc(r.key)}">${esc(r.label)}</button>`).join("")}</div>
      ${x.person ? `<div class="card">${x.person_card}
        <button class="btn ${x.on_team ? "" : "primary"}" data-act="mx" data-op="${x.on_team ? "leave" : "join"}">${x.on_team ? "移出隊伍" : "加入隊伍"}</button></div>` : ""}`;
  }

  // ── 煉製 ──
  function pageCraft() {
    const x = S.menxia;
    if (!x) return '<p class="muted">載入中…</p>';
    const name = (id) => x.materials.find((m) => m.id === id);
    const used = (id) => S.craftSel.filter((s) => s === id).length;
    const slot = (i) => {
      const m = name(S.craftSel[i]);
      return m ? `<div class="slot full" data-act="unslot" data-i="${i}">${esc(m.name)}<small>${esc(m.tier)}・屬${esc(m.attribute)}　點一下拿出</small></div>`
        : `<div class="slot muted">放入素材</div>`;
    };
    const ready = S.craftSel.length === x.per_craft;
    return `
      <div class="msg" id="mx-msg">${S.message}</div>
      <div class="slots">${slot(0)}<span class="plus">＋</span>${slot(1)}</div>
      <div class="seg">${KINDS.map((k) => `<button class="${S.craftKind === k ? "on" : ""}" data-act="craft-kind" data-kind="${k}">煉${k}</button>`).join("")}</div>
      <div class="card" id="craft-line">${S.craftLine || x.craft_line}</div>
      ${x.materials.length ? `<div class="chips">${x.materials.map((m) => `
        <button class="chip r${m.rank} ${used(m.id) >= m.count ? "used" : ""}" data-act="slot" data-id="${esc(m.id)}" ${used(m.id) >= m.count ? "disabled" : ""}>
          <span class="n">×${m.count - used(m.id)}</span><b>${esc(m.name)}</b><small>${esc(m.tier)}・屬${esc(m.attribute)}</small>
        </button>`).join("")}</div>`
        : '<p class="muted">背包裡還沒有素材。去探索、歷練打贏，或是碰上奇遇都拿得到。</p>'}
      <details class="fold"><summary>素材說明</summary><div class="fold-body">${x.bag}</div></details>
      <div class="sticky-act"><button class="btn primary" id="forge" data-act="forge" ${ready ? "" : "disabled"}>開爐煉製</button></div>`;
  }

  // ── 輿圖 ──
  function pageMap() {
    const m = S.map;
    if (!m) return '<p class="muted">展開輿圖…</p>';
    return `
      <div class="card">${m.header}</div>
      <div class="seg">${m.layers.map((l) => `<button class="${m.layer === l.id ? "on" : ""}" data-act="layer" data-layer="${esc(l.id)}">${esc(l.name)}</button>`).join("")}</div>
      <div class="map-tools">
        <select class="input" id="place">${m.places.map((p) => `<option value="${esc(p.id)}" ${p.id === m.selected ? "selected" : ""}>${esc(p.label)}</option>`).join("")}</select>
        <button class="btn small" data-act="fit">${S.fitMap ? "放大" : "縮小"}</button>
      </div>
      <div class="map-wrap ${S.fitMap ? "fit" : ""}" id="map">${m.svg}</div>
      <div class="msg">${S.mapNotice || ""}</div>
      <div class="card">${m.detail}</div>
      ${m.travel ? `<div class="sticky-act travel-row">${m.travel.map((t) =>
        `<button class="btn ${t.mode === "walk" ? "primary" : ""}" data-act="travel" data-mode="${esc(t.mode)}" ${t.enabled ? "" : "disabled"}>${esc(t.label)}</button>`).join("")}</div>` : ""}`;
  }

  // ── 見聞 ──
  function pageNews() {
    const seg = `<div class="seg">${NEWS.map((n) => `<button class="${S.news === n.id ? "on" : ""}" data-act="news" data-news="${n.id}">${n.name}</button>`).join("")}</div>`;
    const m = S.main;
    let body = "";
    if (S.news === "reports") {
      const r = S.reports;
      if (!r) body = '<p class="muted">載入中…</p>';
      else if (S.reportOpen && r.selected != null) body = `<button class="linkish back" data-act="report-list">‹ 全部戰報</button><div class="card report-detail">${r.detail}</div>`;
      else if (!r.list.length) body = `<div class="card">${r.detail}</div>`;
      else body = `<div class="list">${r.list.map((x) => `<button data-act="report" data-id="${x.id}">${esc(x.label)}</button>`).join("")}</div>`;
    } else if (S.news === "trends") body = `<div class="card">${m.trends}</div>`;
    else if (S.news === "rumors") body = `<div class="card">${m.rumors}</div>`;
    else if (S.news === "chronicle") body = `<div class="card">${m.chronicle}</div>`;
    else body = `<div class="card">${m.latest || ""}${m.journal || ""}${m.older || ""}${!m.latest && !m.journal ? '<p class="muted">還沒有紀錄。</p>' : ""}</div>`;
    return seg + body;
  }

  // ── 設定抽屜 ──
  function sheetHtml() {
    const s = S.main.status;
    const a = S.admin;
    const opts = (list) => list.map((x) => `<option value="${esc(x.id)}">${esc(x.label)}</option>`).join("");
    return `
      <div class="sheet-bg" data-act="sheet-close"></div>
      <div class="sheet" role="dialog" aria-label="設定">
        <div class="grip"></div>
        <div class="top-row"><h3 style="flex:1">設定</h3><button class="btn small ghost" data-act="sheet-close">關閉</button></div>
        <label class="toggle"><input type="checkbox" id="anon" ${s.anonymous ? "checked" : ""}> 匿名行走（江湖傳聞中不顯示名號）</label>
        <div class="stack">
          <button class="btn" data-act="do" data-op="skip_tutorial">略過新手引導</button>
        </div>
        <details class="fold"><summary>修改密碼</summary><form class="fold-body" id="pw-form">
          <label class="field"><span>舊密碼</span><input class="input" type="password" name="old" autocomplete="current-password"></label>
          <label class="field"><span>新密碼</span><input class="input" type="password" name="new" autocomplete="new-password"></label>
          <label class="field"><span>再輸入一次新密碼</span><input class="input" type="password" name="again" autocomplete="new-password"></label>
          <button class="btn" type="submit">修改密碼</button>
        </form></details>
        ${S.main.admin ? `
          <div class="label">管理者</div>
          <div class="card stack">
            <div class="row"><button class="btn" data-act="admin" data-op="open_season">開季</button><button class="btn" data-act="admin" data-op="next_season">開啟下一季</button></div>
            <p class="muted">時間快轉（全服一起快轉，只在測試時用）</p>
            <div class="row">${[1, 8, 24].map((h) => `<button class="btn small" data-act="admin" data-op="fast_forward" data-hours="${h}">+${h} 小時</button>`).join("")}</div>
            ${a ? `
              <p class="muted">觸發（人少、大勢推不到門檻時用；效果跟自然發生一樣）</p>
              <div class="row"><select class="input" id="ad-battle">${opts(a.battles)}</select><button class="btn small" data-act="admin" data-op="start_battle">立刻開戰</button></div>
              <div class="row"><select class="input" id="ad-fire">${opts(a.events)}</select><button class="btn small" data-act="admin" data-op="fire">觸發</button></div>
              <div class="row"><select class="input" id="ad-trend">${opts(a.trends)}</select><input class="input" id="ad-amount" type="number" value="10" style="max-width:90px"><button class="btn small" data-act="admin" data-op="push_trend">推動</button></div>
              <p class="muted">重設密碼（朋友忘記密碼時用；臨時密碼私下告訴他）</p>
              <form class="row" id="reset-form"><input class="input" name="target" placeholder="帳號或名號"><input class="input" name="temp" placeholder="臨時密碼"><button class="btn small" type="submit">重設</button></form>` : ""}
          </div>` : ""}
        <div class="label">帳號</div>
        <button class="btn ghost" data-act="logout">登出</button>
      </div>`;
  }

  // ── 載入各頁 ──
  async function loadMenxia() {
    S.menxia = await api(`/api/menxia${S.person ? `?person=${encodeURIComponent(S.person)}` : ""}`);
    if (S.tab === "practice" || S.tab === "craft") renderPage();
  }

  async function loadMap(place) {
    const q = new URLSearchParams({ layer: S.layer });
    if (place) q.set("place", place);
    S.map = await api(`/api/map?${q}`);
    S.layer = S.map.layer;
    if (S.tab === "map") renderPage();
  }

  async function loadReports(id) {
    S.reports = await api(`/api/reports${id != null ? `?id=${id}` : ""}`);
    if (S.tab === "news") renderPage();
  }

  async function goTab(tab) {
    S.tab = tab;
    S.message = "";
    S.mapNotice = "";
    if (tab === "news") S.unseen = false;
    render();
    window.scrollTo(0, 0);
    try {
      if (tab === "practice" || tab === "craft") await loadMenxia();
      if (tab === "map") {
        // 打開輿圖本身可能完成新手引導的一步，所以先當一個動作做
        const r = await api("/api/do/view_map", {});
        setMain(r.main);
        renderTop();
        await loadMap(null);
      }
      if (tab === "news" && S.news === "reports") await loadReports(null);
    } catch (e) { /* api() 已經提示過 */ }
  }

  // ── 動作 ──
  async function busy(fn) {
    if (S.busy) return;
    S.busy = true;
    try { await fn(); } catch (e) { /* api() 已經提示過 */ } finally { S.busy = false; }
  }

  function applyMain(main) {
    const before = S.main ? S.main.status : null;
    setMain(main);
    if (main.card) S.unseen = true;
    render();
    const top = document.getElementById("top");
    if (before && top && (before.hp !== main.status.hp || before.stamina !== main.status.stamina || before.silver !== main.status.silver || before.xinde !== main.status.xinde)) {
      top.classList.add("flash");
      setTimeout(() => top.classList.remove("flash"), 900);
    }
  }

  async function choose(btn, id) {
    await busy(async () => {
      document.querySelectorAll(".options .btn").forEach((b) => { b.disabled = true; });
      btn.classList.add("busy");
      const talking = (id.startsWith("talk:") && id !== "talk:leave") || id === "act:socialize";
      if (talking) btn.lastElementChild.textContent = "對方沉吟中…";
      const r = await api("/api/choose", { id });
      applyMain(r.main);
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
    if (document.querySelector(".options .btn.busy")) renderPage(); // 失敗了：把按鈕還原
  }

  async function mx(op, extra = {}) {
    await busy(async () => {
      const r = await api(`/api/menxia/${op}`, { person: S.person, kind: S.kind, ...extra });
      S.menxia = r.menxia;
      S.message = r.message;
      setMain(r.main);
      renderTop();
      renderPage();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  }

  async function doMain(op, body = {}, confirm = false) {
    await busy(async () => {
      const r = await api(`/api/do/${op}`, body);
      applyMain(r.main);
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      if (text || confirm) toast(text || "已完成。");
    });
  }

  async function updateCraftLine() {
    try {
      const r = await api("/api/craft_line", { materials: S.craftSel, kind: S.craftKind });
      S.craftLine = r.line;
      const el = document.getElementById("craft-line");
      if (el) el.innerHTML = r.line;
    } catch (e) { /* 提示過 */ }
  }

  async function forge() {
    const btn = document.getElementById("forge");
    await busy(async () => {
      btn.disabled = true;
      btn.textContent = "爐火正旺…";
      btn.classList.add("forging");
      S.message = "爐火正旺。若這個配方是江湖上第一次煉成，取名要花上一分鐘，請稍候。";
      document.getElementById("mx-msg").textContent = S.message;
      const r = await api("/api/menxia/craft", { materials: S.craftSel, kind: S.craftKind });
      S.menxia = r.menxia;
      S.message = r.message;
      S.craftSel = [];
      S.craftLine = "";
      setMain(r.main);
      renderTop();
    });
    renderPage();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function travel(mode) {
    await busy(async () => {
      const r = await api("/api/travel", { place: S.map.selected, layer: S.layer, mode });
      setMain(r.main);
      if (r.arrived) {
        S.tab = "jianghu";
        render();
        window.scrollTo(0, 0);
      } else {
        S.map = r.map;
        S.mapNotice = `沒能出發：${esc(r.reason)}`;
        render();
      }
    });
  }

  // ── 事件 ──
  document.addEventListener("click", async (ev) => {
    const loc = ev.target.closest("#map [data-loc]");
    if (loc) {
      S.mapNotice = "";
      try { await loadMap(loc.getAttribute("data-loc")); } catch (e) { /* 提示過 */ }
      return;
    }
    const el = ev.target.closest("[data-act]");
    if (!el) return;
    const act = el.dataset.act;
    try {
      switch (act) {
        case "gate": S.gateMode = el.dataset.mode; renderGate(); break;
        case "tab": await goTab(el.dataset.tab); break;
        case "choose": await choose(el, el.dataset.id); break;
        case "toggle-more": S.showMore = !S.showMore; renderTop(); break;
        case "sheet":
          S.sheet = true;
          render();
          if (S.main.admin && !S.admin) { S.admin = await api("/api/admin"); render(); }
          break;
        case "sheet-close": S.sheet = false; render(); break;
        case "do": S.sheet = false; await doMain(el.dataset.op); break;
        case "admin": {
          const op = el.dataset.op;
          const body = { hours: Number(el.dataset.hours || 1) };
          if (op === "start_battle") body.id = document.getElementById("ad-battle").value;
          if (op === "fire") body.id = document.getElementById("ad-fire").value;
          if (op === "push_trend") { body.id = document.getElementById("ad-trend").value; body.amount = Number(document.getElementById("ad-amount").value || 0); }
          await doMain(op, body, true);
          break;
        }
        case "logout": await api("/api/logout", {}); S.sheet = false; S.stage = "gate"; S.main = null; render(); break;
        case "kind": S.kind = el.dataset.kind; renderPage(); break;
        case "mx": await mx(el.dataset.op); break;
        case "person":
          S.person = S.person === el.dataset.key ? null : el.dataset.key;
          await loadMenxia();
          break;
        case "switch": await mx("switch", { art: el.dataset.id }); break;
        case "slot":
          if (S.craftSel.length < (S.menxia?.per_craft || 2)) { S.craftSel.push(el.dataset.id); renderPage(); updateCraftLine(); }
          else toast("爐裡已經放滿了，點上面的素材拿出來再換。");
          break;
        case "unslot": S.craftSel.splice(Number(el.dataset.i), 1); renderPage(); updateCraftLine(); break;
        case "craft-kind": S.craftKind = el.dataset.kind; renderPage(); updateCraftLine(); break;
        case "forge": await forge(); break;
        case "layer": S.layer = el.dataset.layer; await loadMap(S.map?.selected); break;
        case "fit": S.fitMap = !S.fitMap; renderPage(); break;
        case "travel": await travel(el.dataset.mode); break;
        case "news":
          S.news = el.dataset.news;
          S.reportOpen = false;
          if (S.tab !== "news") { await goTab("news"); break; }
          renderPage();
          if (S.news === "reports") await loadReports(null);
          break;
        case "report":
          S.news = "reports";
          S.reportOpen = true;
          if (S.tab !== "news") { S.tab = "news"; S.unseen = false; render(); }
          await loadReports(Number(el.dataset.id));
          window.scrollTo(0, 0);
          break;
        case "report-list": S.reportOpen = false; renderPage(); break;
      }
    } catch (e) { /* api() 已經提示過 */ }
  });

  document.addEventListener("change", async (ev) => {
    if (ev.target.id === "place") { S.mapNotice = ""; await loadMap(ev.target.value).catch(() => {}); }
    if (ev.target.id === "anon") await doMain("anonymous", { value: ev.target.checked });
  });

  document.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const form = ev.target;
    const data = Object.fromEntries(new FormData(form));
    const submit = form.querySelector("[type=submit]");
    try {
      if (form.id === "gate-form") {
        submit.disabled = true;
        enter(await api(S.gateMode === "register" ? "/api/register" : "/api/login", data));
      } else if (form.id === "create-form") {
        submit.disabled = true;
        enter(await api("/api/character", data));
      } else if (form.id === "free-form") {
        if (!data.text.trim()) return;
        await doMain("battle_text", { text: data.text });
      } else if (form.id === "create-skill") {
        if (!data.name.trim()) { toast("先幫你的功法取個名字。"); return; }
        await mx("create", { name: data.name });
      } else if (form.id === "seclude") {
        await doMain("seclude", { hours: Number(data.hours) });
        S.tab = "jianghu";
        render();
      } else if (form.id === "pw-form") {
        const r = await api("/api/password", data);
        form.reset();
        toast(r.message);
      } else if (form.id === "reset-form") {
        const r = await api("/api/admin/reset_password", data);
        form.reset();
        toast(r.message);
      }
    } catch (e) {
      if (submit) submit.disabled = false;
    }
  });

  // ── 計時器：體力、氣血跟著時間走；別人推動的大勢也會進來 ──
  async function poll() {
    if (S.stage !== "game" || S.busy || document.hidden) return;
    const typing = document.activeElement && ["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName);
    try {
      const main = await api("/api/main");
      if (!setMain(main)) return;
      renderTop();
      if (S.tab === "jianghu" && !typing) renderPage();
    } catch (e) { /* 下一輪再試 */ }
  }
  setInterval(poll, POLL_MS);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) poll(); });

  api("/api/me").then(enter).catch(() => { S.stage = "gate"; render(); });
})();
