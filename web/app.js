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
  // 江湖頁「前往」的走法（跟 atlas.MODES 同一份）。選的走法只放在 S.moveMode：不寫進 localStorage、cookie，
  // 重新整理頁面就回到步行；每個請求都帶著它（見 api()），伺服器照它排選單上的「前往」
  const MOVE_MODES = [
    { id: "walk", name: "步行" },
    { id: "hurry", name: "趕路" },
    { id: "dash", name: "疾行" },
  ];

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
    artOpen: null, // 修練頁功法庫裡點開的那一門（id）；切分頁、改練成功之後收起
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
    moveMode: "walk",
  };

  const $app = document.getElementById("app");
  const $toast = document.getElementById("toast");

  // ── 工具 ──
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pct = (a, b) => (b > 0 ? Math.max(0, Math.min(100, (a / b) * 100)) : 0);
  // 本季天數：整數不帶小數點（14.0 → 14），不是整數照原樣（14.5）
  const dayCount = (n) => String(Number(n));
  // 焦點在輸入框、下拉選單：玩家正在填東西，輪詢不動畫面
  const typing = () => !!document.activeElement && ["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName);

  // 表單的結果訊息（QA L3）：寫在表單裡那一行，留到下一次送出；錯誤醒目、成功用一般文字色
  function formMsg(form, text, ok = false) {
    const el = form.querySelector(".form-msg");
    if (!el) return;
    el.textContent = text || "";
    el.classList.toggle("ok", ok);
  }
  // 請求的錯誤寫成玩家看得懂的一句：連不上（api() 已經標成離線）另外講；api() 自己丟的 Error 帶著伺服器的原因，照登；
  // 其他錯誤（程式出錯，例如 TypeError）不要說成網路問題，也不要把英文的錯誤訊息丟給玩家
  const failText = (e) => (S.offline ? "連不上伺服器，請稍後再試。"
    : e && e.constructor === Error && e.message ? e.message : "出了點問題，請再試一次。");

  let toastTimer = 0;
  function toast(text) {
    $toast.textContent = text;
    $toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => $toast.classList.remove("show"), 3200);
  }

  async function api(path, body) {
    const headers = { "X-Move-Mode": S.moveMode }; // 走法跟著每個請求走，兩個分頁各走各的（見 MOVE_MODES）
    const opts = body === undefined
      ? { credentials: "same-origin", headers }
      : { method: "POST", credentials: "same-origin", headers: { ...headers, "Content-Type": "application/json" }, body: JSON.stringify(body) };
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
    S.moveMode = "walk"; // 登入、重新登入、建角的畫面都是伺服器照步行排的（_entry 不看走法），切換鈕跟著回到步行
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
        <div class="who" data-act="toggle-more" role="button" tabindex="0" aria-expanded="${S.showMore}">
          <div class="who-name"><span>${esc(s.name)}<small>${esc(s.affiliation)}${s.anonymous ? "・匿名" : ""}・第${s.level}級</small></span><i class="more-ico" aria-hidden="true">${S.showMore ? "▴" : "▾"}</i></div>
          <div class="where">📍 ${esc(s.location)}　第 ${s.day} 天 ${esc(s.clock)}<small>／共 ${dayCount(s.season_days)} 天</small>${s.resting != null ? "　🧘 打坐中" : ""}</div>
          ${s.busy_hours != null ? `<div class="where sub">🧘 閉關中，約 ${s.busy_hours} 小時後出關</div>` : ""}
          ${s.journey != null ? `<div class="where sub">🐎 ${esc(s.journey)}</div>` : ""}
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
          <p class="form-msg" role="alert"></p>
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
          <p class="form-msg" role="alert"></p>
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
    // 走法切換：選單上有「前往」才出現（對話、事件、戰鬥的選單沒有）
    const modes = m.options.some((o) => o.id.startsWith("move:"))
      ? `<div class="seg move-mode" role="group" aria-label="走法"><span aria-hidden="true">走法</span>${MOVE_MODES.map((x) => `
          <button class="${S.moveMode === x.id ? "on" : ""}" data-act="move-mode" data-mode="${x.id}" aria-pressed="${S.moveMode === x.id}">${x.name}</button>`).join("")}
        </div>`
      : "";
    return `
      <details class="fold quest"><summary>📜 主線與目標</summary><div class="fold-body">${m.quest}</div></details>
      ${now}
      <section class="card scene">${m.scene}</section>
      ${free}
      ${modes}
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
    // 身上的功法卡（FB-006）：目前切到的那一門放前面
    const slots = x.slot_cards.filter((c) => c.kind === S.kind).concat(x.slot_cards.filter((c) => c.kind !== S.kind));
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
      <div class="label">身上的功法</div>
      ${slots.map((c) => `<div class="card">${c.card}</div>`).join("")}
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
      ${x.arts.length ? `<div class="list">${x.arts.map((a) => `
        <button class="art ${S.artOpen === a.id ? "on" : ""}" data-act="art" data-id="${esc(a.id)}">${esc(a.label)}</button>
        ${S.artOpen === a.id ? `<div class="art-body">${a.card}<button class="btn primary" data-act="switch" data-id="${esc(a.id)}">改練這一門</button></div>` : ""}`).join("")}</div>`
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
          <p class="form-msg" role="alert"></p>
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
              <form id="reset-form"><div class="row"><input class="input" name="target" placeholder="帳號或名號"><input class="input" name="temp" placeholder="臨時密碼"><button class="btn small" type="submit">重設</button></div><p class="form-msg" role="alert"></p></form>` : ""}
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
    S.artOpen = null;
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
      // 跟 server.py 的 may_generate_dialogue 同一個判斷：這些選項要等模型回話
      const talking = id === "act:socialize" || ((id.startsWith("talk:") || id.startsWith("call:")) && id !== "talk:leave" && id !== "call:back");
      if (talking) btn.lastElementChild.textContent = "對方沉吟中…";
      const r = await api("/api/choose", { id });
      applyMain(r.main);
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
    if (document.querySelector(".options .btn.busy")) renderPage(); // 失敗了：把按鈕還原
  }

  // 換走法：帶著新的走法重抓一次江湖畫面，「前往」的時間、體力與按不按得下去才會跟著換
  async function setMoveMode(mode) {
    if (mode === S.moveMode || S.busy) return;
    const before = S.moveMode;
    await busy(async () => {
      S.moveMode = mode;
      try {
        setMain(await api("/api/main"));
      } catch (e) {
        S.moveMode = before; // 沒拿到新走法的選單：留在原本的走法，切換鈕才跟按鈕上的字對得上
        throw e;
      }
      renderTop();
    });
    if (S.tab === "jianghu") renderPage();
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

  // 放素材、換種類與輪詢都會問成本說明，回應可能晚到：只用最後一次請求的回應，而且爐子要還是問的那一爐
  let craftLineSeq = 0;
  async function updateCraftLine() {
    const seq = ++craftLineSeq;
    const pot = JSON.stringify([S.craftSel, S.craftKind]);
    try {
      const r = await api("/api/craft_line", { materials: S.craftSel, kind: S.craftKind });
      if (seq !== craftLineSeq || pot !== JSON.stringify([S.craftSel, S.craftKind])) return;
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
        case "move-mode": await setMoveMode(el.dataset.mode); break;
        case "toggle-more": toggleMore(); break;
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
        case "switch": {
          // 改練真的送出了（mx 換上伺服器回來的那一份 menxia）才收起卡片；還在忙（mx 直接返回）或請求失敗就照舊開著
          const was = S.menxia;
          await mx("switch", { art: el.dataset.id });
          if (S.menxia !== was) { S.artOpen = null; if (S.tab === "practice") renderPage(); }
          break;
        }
        case "art": S.artOpen = S.artOpen === el.dataset.id ? null : el.dataset.id; renderPage(); break;
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

  // 狀態列點名號展開／收起更多數值（S1）。鍵盤也按得到（Enter、空白鍵）；狀態列整塊重畫，所以按完把焦點放回去
  function toggleMore(keyboard = false) {
    S.showMore = !S.showMore;
    renderTop();
    if (keyboard) document.querySelector(".who")?.focus();
  }
  document.addEventListener("keydown", (ev) => {
    if ((ev.key === "Enter" || ev.key === " ") && ev.target instanceof Element && ev.target.matches('.who[data-act="toggle-more"]')) {
      ev.preventDefault();
      toggleMore(true);
    }
  });

  document.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const form = ev.target;
    const data = Object.fromEntries(new FormData(form));
    const submit = form.querySelector("[type=submit]");
    formMsg(form, ""); // 上一次的結果訊息留到這次送出為止
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
        // 閉關（QA L9）：真的進了閉關（busy_hours 有值）才回江湖頁。引擎不讓閉關（在路上、打坐、事件進行中）
        // 也是 200 加一句原因，請求本身失敗也一樣：留在修練頁、原因寫在頁面上方。
        // 等回應時玩家換到別的分頁（#mx-msg 煉製頁也有），原因就只用提示泡泡講，不寫到別頁上
        const tab = S.tab;
        await busy(async () => {
          let r;
          try {
            r = await api("/api/do/seclude", { hours: Number(data.hours) });
          } catch (e) {
            if (S.stage === "game" && S.tab === tab) {
              S.message = esc(failText(e));
              const el = document.getElementById("mx-msg");
              if (el) { el.innerHTML = S.message; el.classList.remove("still"); } // 新的一句，照常浮現
              window.scrollTo({ top: 0, behavior: "smooth" });
            }
            return;
          }
          const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
          if (r.main.status.busy_hours != null) {
            S.tab = "jianghu";
            applyMain(r.main);
            window.scrollTo(0, 0);
            if (text) toast(text);
          } else if (S.tab === tab) {
            S.message = r.message || "";
            setMain(r.main);
            renderTop();
            redrawPage(); // 選好的時數、填到一半的功法名字照舊，改好原因再按一次就行
            window.scrollTo({ top: 0, behavior: "smooth" });
          } else if (text) {
            toast(text); // S.main 不動，換過去的那一頁交給下一輪輪詢照它自己的方式補上
          }
        });
      } else if (form.id === "pw-form") {
        // 改密碼、重設密碼一律回 200，訊息就是結果（失敗時寫原因）；成功才清空欄位，失敗留著讓人改
        const r = await api("/api/password", data);
        const ok = r.message === "密碼已更新。";
        formMsg(form, r.message, ok);
        if (ok) form.reset();
      } else if (form.id === "reset-form") {
        const r = await api("/api/admin/reset_password", data);
        const ok = /^已重設 .+ 的密碼。$/.test(r.message || "");
        formMsg(form, r.message, ok);
        if (ok) form.reset();
      }
    } catch (e) {
      if (submit) submit.disabled = false;
      formMsg(form, failText(e)); // 沒有訊息行的表單（自創、閉關…）不受影響
    }
  });

  // ── 計時器：體力、氣血跟著時間走；別人推動的大勢也會進來 ──
  async function poll() {
    if (S.stage !== "game" || S.busy || document.hidden) return;
    const was = S.main;
    try {
      const mode = S.moveMode;
      const main = await api("/api/main");
      if (mode !== S.moveMode) return; // 等回應的時候換了走法：這份是舊走法的選單，不用
      // 等回應時玩家做了動作：S.main 已經換成動作回來的那一份（比這份新），這一輪作廢
      if (S.stage !== "game" || S.busy || S.main !== was) return;
      if (!setMain(main)) return;
      renderTop();
      if (!typing()) await refreshPage(was);
    } catch (e) { /* api() 提示過；下一輪再試 */ }
  }

  // 輪詢拿到有變的 main 之後，照目前的分頁補上（QA L1）。江湖、見聞從 S.main 畫；修練、煉製、輿圖重抓自己那一份。
  // 重抓回來時玩家若已經切了分頁、按了別的（那份資料已經換過）、正在忙或正在打字，就不動畫面，下一輪再說。
  async function refreshPage(old) {
    const tab = S.tab;
    if (tab === "jianghu") return renderPage();
    if (tab === "news") {
      // 戰報子分頁畫的是 S.reports，不用重抓；其他子分頁只在它畫的那幾欄真的變了才重畫
      const fields = { trends: ["trends"], rumors: ["rumors"], chronicle: ["chronicle"], journal: ["latest", "journal", "older"] }[S.news] || [];
      if (fields.some((k) => old[k] !== S.main[k])) redrawPage(true);
      return;
    }
    if (tab === "practice" || tab === "craft") {
      const was = S.menxia;
      if (!was) return; // 還在載入，goTab 會畫
      const x = await api(`/api/menxia${S.person ? `?person=${encodeURIComponent(S.person)}` : ""}`);
      if (S.stage !== "game" || S.tab !== tab || S.busy || S.menxia !== was || typing()) return;
      S.menxia = x;
      const trimmed = trimCraftSel();
      if (S.artOpen && !x.arts.some((a) => a.id === S.artOpen)) S.artOpen = null; // 那一門已經不在庫裡
      if (!S.craftSel.length) S.craftLine = ""; // 爐是空的：用伺服器剛給的那一行（心得是新的）
      const shown = (m) => JSON.stringify(MENXIA_SHOWN[tab].map((k) => m[k]));
      const changed = trimmed || shown(x) !== shown(was)
        || (tab === "practice" && old.status.injury !== S.main.status.injury); // 療傷鈕看的是內傷
      if (!changed) return;
      redrawPage(true);
      // 爐裡有東西：成本說明裡的心得、能不能開爐也跟著更新
      if (S.craftSel.length && (trimmed || tab === "craft")) updateCraftLine();
      return;
    }
    if (tab === "map") {
      const was = S.map;
      if (!was) return;
      const q = new URLSearchParams({ layer: S.layer });
      if (was.selected) q.set("place", was.selected);
      const m = await api(`/api/map?${q}`);
      if (S.stage !== "game" || S.tab !== tab || S.busy || S.map !== was || typing()) return;
      S.map = m;
      S.layer = m.layer;
      if (JSON.stringify(m) !== JSON.stringify(was)) redrawPage(true);
    }
  }

  // 修練、煉製兩頁各自畫了 menxia 的哪幾欄（照 pagePractice／pageCraft）：輪詢只在這幾欄變了才重畫。
  // 不比整份，是因為本人卡上的氣血一直在回，整份 menxia 幾乎每分鐘都不一樣，煉製頁根本沒畫那張卡
  const MENXIA_SHOWN = {
    practice: ["rules", "slot_cards", "arts", "player_card", "roster", "person", "person_card", "on_team"],
    craft: ["materials", "per_craft", "bag", "craft_line", "xinde"],
  };

  // 重畫這一頁但保留玩家正在做的事（輪詢、閉關被拒時用）：填到一半的欄位（自創功法的名字、閉關時數）、
  // 摺疊區的開合，以及輿圖捲到的位置（afterPage() 每次重畫都會把選取的地點置中，這裡再捲回原處）。
  // quiet：輪詢的重畫，頁面上方那一行訊息沒有變，不要再播一次浮現動畫
  function redrawPage(quiet = false) {
    const page = document.getElementById("page");
    if (!page) return;
    const fields = [...page.querySelectorAll("form[id] input[name], form[id] select[name], form[id] textarea[name]")]
      .map((el) => [el.form.id, el.name, el.value]);
    const folds = [...page.querySelectorAll("details > summary")].map((s) => [s.textContent, s.parentElement.open]);
    const wrap = page.querySelector(".map-wrap");
    const scroll = wrap && [wrap.scrollLeft, wrap.scrollTop];
    renderPage();
    if (quiet) page.querySelectorAll(".msg").forEach((el) => el.classList.add("still"));
    for (const [form, name, value] of fields) {
      const el = page.querySelector(`#${CSS.escape(form)} [name="${CSS.escape(name)}"]`);
      if (el) el.value = value;
    }
    for (const [text, open] of folds) {
      const s = [...page.querySelectorAll("details > summary")].find((x) => x.textContent === text);
      if (s) s.parentElement.open = open;
    }
    const now = page.querySelector(".map-wrap");
    if (scroll && now) [now.scrollLeft, now.scrollTop] = scroll;
  }

  // 重抓素材之後，爐裡放的若已經不夠（別處用掉了）就拿掉多的那幾個；有拿掉回 true
  function trimCraftSel() {
    const left = Object.fromEntries((S.menxia?.materials || []).map((m) => [m.id, m.count]));
    const keep = [];
    for (const id of S.craftSel) {
      if ((left[id] || 0) > 0) { left[id] -= 1; keep.push(id); }
    }
    const trimmed = keep.length !== S.craftSel.length;
    S.craftSel = keep;
    return trimmed;
  }
  setInterval(poll, POLL_MS);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) poll(); });

  api("/api/me").then(enter).catch(() => { S.stage = "gate"; render(); });
})();
