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
  const FREE_TEXT_OPTION = "choice:free"; // 事件的隨口應對（engine.FREE_TEXT_OPTION）
  const MOVE_MODES = [
    { id: "walk", name: "步行" },
    { id: "hurry", name: "趕路" },
    { id: "dash", name: "疾行" },
  ];
  // 照「走法」切換的選項：「前往」與路上的「折返」（路上設計 3.2）。切換鈕緊貼在第一個這種選項上面（A4／W6）
  const followsMode = (id) => id.startsWith("move:") || id.startsWith("road:back");
  // 路上的江湖頁多三個捷徑（路上設計 3.3）：是頁面切換，不是引擎的行動
  const ROAD_LINKS = [
    { tab: "map", name: "打開輿圖改去別處" },
    { tab: "practice", name: "去修練" },
    { tab: "craft", name: "去煉製" },
  ];
  // 三方態勢（第一季設計 4.4，status.stances 的鍵）：狀態列展開時那一行；第一季濃縮版才有
  const STANCE_NAMES = [["guan", "官軍"], ["huang", "黃巾"], ["haoqiang", "豪強"]];
  // 手機寬度：第一次打開輿圖時，手機照原尺寸，寬螢幕照框寬（最多原尺寸），都對準所在地（見 mapReady）
  const PHONE = window.matchMedia ? window.matchMedia("(max-width: 767px)") : null;

  const S = {
    stage: "boot",
    gateMode: "login",
    main: null,
    mainKey: "",
    tab: "jianghu",
    nowOpen: null, // 江湖頁「剛剛」展開的那一則（記內容本身）；換成新的一則就收回（A4）
    boardOpen: null, // 江湖頁公告卡展開著的那一週（週次）；收起或換週就不再對得上（FB-039）
    ordersShut: null, // 江湖頁「本週軍令」收起來的那一週；換週就重新展開（計畫 T6）
    busy: false,
    menxia: null,
    message: "",
    person: null,
    kind: "武學",
    artOpen: null, // 修練頁功法庫裡點開的那一門（id）；切分頁、改練成功之後收起
    craftSel: [],
    wheelSel: null, // 江湖頁行動列展開的那一格（目前只有 move）
    craftLine: "",
    map: null,
    layer: "situation",
    // 輿圖的視圖（W16）：{ s 倍率, cx, cy 視窗中心對著的地圖座標 }。這次載入網頁後第一次打開輿圖才決定（mapReady：
    // 對準所在地，手機原尺寸、寬螢幕照框寬，都不給整張），之後切分頁、輪詢重畫、換圖層、點地點都留著
    mapView: null,
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
  // 第一季的季曆（計畫 T2）：狀態列寫「第 3 週・週二 21:40」，旁邊是下一件大事的倒數（現實時間）
  const WEEKDAYS = "一二三四五六日";
  const countdown = (sec) => {
    const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60);
    if (sec < 60) return "就在眼前";
    return h > 0 ? `約 ${h} 小時 ${m} 分後` : `約 ${m} 分後`;
  };
  // 江湖頁畫的東西有沒有變：狀態列（時鐘、季曆每次輪詢都在走）另外重畫，不讓「剛剛」一直重播浮現
  const pageKey = (m) => JSON.stringify({ ...m, status: null });
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
    if (main.event_free_text == null) S.answering = false; // 事件過去了，輸入框跟著收起
    const key = JSON.stringify(main);
    const changed = key !== S.mainKey;
    S.main = main;
    S.mainKey = key;
    return changed;
  }

  // ── 整體 ──
  function render() {
    if (S.stage !== "game" || !S.sheet) closeAsk(); // 管理者確認框只疊在設定抽屜上；抽屜關了、被登出就一起收掉
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
          <div class="where">📍 ${esc(s.location)}　${s.calendar
            ? `第 ${s.calendar.week} 週・週${WEEKDAYS[s.calendar.weekday]} ${esc(s.calendar.clock)}`
            : `第 ${s.day} 天 ${esc(s.clock)}<small>／共 ${dayCount(s.season_days)} 天</small>`}${s.resting != null ? "　🧘 打坐中" : ""}</div>
          ${s.calendar && s.next_event ? `<div class="where sub">下一件：${esc(s.next_event.title)}，${countdown(s.next_event.in_seconds)}</div>` : ""}
          ${s.busy_hours != null ? `<div class="where sub">🧘 閉關中，約 ${s.busy_hours} 小時後出關</div>` : ""}
          ${s.journey != null ? `<div class="where sub">🐎 ${esc(s.journey)}</div>` : ""}
        </div>
        <button class="icon-btn" data-act="sheet" aria-label="設定">⚙</button>
      </div>
      <div class="vitals">
        <div class="bar stam" title="體力"><i style="width:${pct(s.stamina, s.stamina_max)}%"></i><span>體力 ${s.stamina}/${s.stamina_max}</span></div>
        <div class="bar hp" title="氣血"><i style="width:${pct(s.hp, s.hp_max)}%"></i>${s.injury >= 1
          // 內傷（FB-049）：斜紋是上限裡被內傷佔掉、回不來的那一截（寬＝內傷÷上限，回滿時紅條剛好接到它）；
          // 「傷 N」靠右另寫在斜紋那一頭，不再接在「氣血 N/M」後面跨過紅條的交界
          ? `<b style="width:${pct(s.injury, s.hp_max)}%"></b>` : ""}<span>氣血 ${s.hp}/${s.hp_max}</span>${s.injury >= 1
          ? `<span class="inj">傷 ${s.injury}</span>` : ""}</div>
        <div class="num"><em>銀</em>${s.silver}</div>
        <div class="num"><em>心得</em>${s.xinde}</div>
      </div>
      ${S.showMore ? `<div class="more-stats">
        ${s.minor.map(([k, v]) => `${esc(k)} ${v}`).join("　")}　｜　${s.attrs.map(([k, v]) => `${esc(k)} ${v}`).join("　")}
        ${team ? `<br>${team}` : ""}
        ${s.stances ? `<br>態勢　${STANCE_NAMES.map(([id, name]) => `${name} ${s.stances[id]}`).join("・")}` : ""}
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
    if (S.tab === "jianghu") {
      // 「剛剛」收著卻其實放得下：拿掉底下的淡出與「展開全文」（A4）
      const now = document.querySelector(".now.clamp");
      const body = now && now.querySelector(".tx-now");
      if (body && body.scrollHeight <= body.clientHeight + 1) now.classList.replace("clamp", "fits");
    }
    if (S.tab === "map") mapReady();
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
  const nowMore = (open) => (open ? "收起 ▴" : "展開全文 ▾");

  // 「剛剛」那一則拆成敘事與數值變化（氣血 -96、黃巾聲勢 -2…，journal.card_html 放在 .tx-now 最後）：
  // 收合只收敘事，數值變化排在收合範圍外面，收著也看得到（W6 review Minor 2）
  function splitChips(html) {
    const t = document.createElement("template");
    t.innerHTML = html;
    const chips = t.content.querySelector(".tx-now > .tx-chgs");
    if (chips) chips.remove();
    return [t.innerHTML, chips ? chips.outerHTML : ""];
  }

  // ── 太極火爐（煉製頁）──
  // 每次重畫都是新的 SVG，所以轉動用負的 animation-delay 接上時鐘，重畫不會讓圖案跳回原位
  const wpt = (r, deg) => { const a = (deg - 90) * Math.PI / 180; return [+(r * Math.cos(a)).toFixed(2), +(r * Math.sin(a)).toFixed(2)]; };
  const spinAt = (secs) => `animation-delay:-${((performance.now() / 1000) % secs).toFixed(2)}s`;
  // 煉製頁的太極火爐（企劃者 2026-10-04）。太極在爐裡慢慢轉，外圈是一圈火舌；左右兩個是放素材的位置，
  // 點有東西的那一格拿出來，點爐身開爐。開爐後等結果的這段時間整座爐子晃動（見 forge()）
  function furnaceHub(slots, ready) {
    const r = 54;
    const flames = Array.from({ length: 16 }, (_, k) => {
      const a = k * 22.5, [x0, y0] = wpt(r + 3, a - 7), [x1, y1] = wpt(r + 10, a), [x2, y2] = wpt(r + 3, a + 7);
      return `<path d="M${x0},${y0} Q${x1},${y1} ${x2},${y2}" style="animation-delay:-${(k % 4) * 0.23}s"/>`;
    }).join("");
    const slot = (m, i) => {
      const x = i ? 26 : -26;
      return m
        ? `<g class="w-slot full r${m.rank}" data-act="unslot" data-i="${i}" role="button" aria-label="拿出${esc(m.name)}">
            <rect x="${x - 23}" y="-14" width="46" height="28" rx="7"/><text x="${x}" y="-3" class="w-slot-name">${esc(m.name)}</text><text x="${x}" y="8" class="w-slot-sub">${esc(m.tier)}・${esc(m.attribute)}</text></g>`
        : `<g class="w-slot"><rect x="${x - 23}" y="-14" width="46" height="28" rx="7"/><text x="${x}" y="0" class="w-slot-sub">放入素材</text></g>`;
    };
    return `<g class="w-hub w-furnace${ready ? " ready" : ""}" data-act="forge-hub" role="button" aria-label="太極火爐，開爐">
      <g class="w-shake">
        <g class="w-flames${ready ? " hot" : ""}">${flames}</g>
        <circle r="${r + 3}" class="w-hub-rim"/>
        <g class="w-spin w-taichi${ready ? " hot" : ""}" style="${spinAt(ready ? 3 : 28)}">
          <circle r="${r}" class="w-yang"/>
          <path d="M0,${-r} A${r},${r} 0 0 1 0,${r} A${r / 2},${r / 2} 0 0 1 0,0 A${r / 2},${r / 2} 0 0 0 0,${-r} Z" class="w-yin"/>
          <circle cy="${-r / 2}" r="${r / 7}" class="w-yang"/><circle cy="${r / 2}" r="${r / 7}" class="w-yin"/>
        </g>
        ${slot(slots[0], 0)}${slot(slots[1], 1)}
        <text y="${r - 12}" class="w-furnace-lab">${ready ? "點爐開火" : "太極火爐"}</text>
      </g></g>`;
  }
  // 煉製頁的太極火爐自己一張圖：外面不再圍四格屬性（挑素材回到下面的素材列表）
  function furnaceSvg(slots, ready) {
    return `<div class="furnace-wrap"><svg class="wheel furnace" viewBox="-74 -74 148 148" role="group" aria-label="太極火爐">
      <defs><radialGradient id="wg-disk"><stop offset="0" style="stop-color:var(--disk-2)"/><stop offset="1" style="stop-color:var(--disk)"/></radialGradient></defs>
      <circle r="72" fill="url(#wg-disk)"/><circle r="70" class="w-rim"/>${furnaceHub(slots, ready)}</svg></div>`;
  }

  // ── 江湖頁的行動列（企劃者 2026-10-04：輪盤太大，改成一排五顆，樣式是她給的「水墨氣勁」）──
  // 選項標籤「探索（體力 5・…）」拆成名字與括號裡的說明
  const optParts = (o) => { const m = /^(.*?)（(.*)）$/.exec(o.label); return m ? [m[1], m[2]] : [o.label, ""]; };
  // 前四顆對到選單上哪一顆、沒有時寫什麼；第五顆是移動（點了在下面展開走法與目的地）
  const ACT_CELLS = [
    { key: "explore", ids: ["act:explore"], name: "探索", none: "不能探索", icon: '<circle cx="12" cy="12" r="9"/><path d="M12 3v3m0 12v3M3 12h3m12 0h3M15 9l-4 2-2 4 4-2z"/>' },
    { key: "train", ids: ["act:train"], name: "遊歷", none: "沒有對手", icon: '<path d="M14.5 4h-5L7 7h10zM12 7v13M8 12h8"/>' },
    { key: "rest", ids: ["act:rest"], name: "打坐", none: "不能打坐", icon: '<circle cx="12" cy="7" r="2.5"/><path d="M8 20c0-3 3-4 4-4s4 1 4 4M5 15l3-2m11 2l-3-2"/>' },
    { key: "social", ids: ["act:socialize", "act:call"], name: "交友", none: "沒有人", icon: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>' },
  ];
  const MOVE_ICON = '<path d="M13 3l-3 7h5l-4 11 8-10h-5z"/>';
  const SHORT_SUB = { "act:rest": "回體力", "act:call": "挑一位" };  // 求見先打開名單挑人（FB-044：以前又寫一次「求見」；挑了人才花體力）
  // 勝算的顏色（FB-044）：遊歷的小字第二行照風險上色
  const ODDS_TONE = { "穩勝": "good", "有把握": "good", "零風險": "good", "五五波": "even", "難分勝負": "even", "凶險": "bad", "必敗": "bad" };
  // 選單上有「打坐」就是平常閒著的時候：用行動列。事件、對話、路上、決戰的選項每次都不一樣，照舊排成一列按鈕
  const idleMenu = (m) => m.options.some((o) => o.id === "act:rest");
  const inkCell = (key, name, sub, icon, attrs, cls, note = "") => `<button class="act-ink${cls}" data-key="${key}" ${attrs}>
      <svg class="ink-icon" viewBox="0 0 24 24" aria-hidden="true">${icon}</svg><b>${esc(name)}</b><small>${esc(sub)}</small>${
      note ? `<small class="ink-note ${ODDS_TONE[note] || ""}">${esc(note)}</small>` : ""}</button>`;

  function actionBar(m) {
    const byId = Object.fromEntries(m.options.map((o) => [o.id, o]));
    const used = new Set();
    const cells = ACT_CELLS.map((d) => {
      const o = d.ids.map((id) => byId[id]).find(Boolean);
      if (!o) return inkCell(d.key, d.name, d.none, d.icon, "disabled", " off");
      used.add(o.id);
      const [name, detail] = optParts(o);
      // 按不下去的原因：標籤括號裡寫的是體力就是「體力不夠」，寫別的就照寫；整句太長、格子裝不下（約 60 px、不換行）時只留
      // 最後一小句（例：挑戰本人打贏之後「剛吃了敗仗，閉門不見」只寫「閉門不見」，T4）
      const sub = o.enabled ? (SHORT_SUB[o.id] || detail.replace(/^體力 (\d+).*$/, "體力 $1"))
        : (detail && !detail.startsWith("體力") ? detail.split("，").pop() : "體力不夠");
      // 體力之後還有說明（遊歷的「體力 10・2 路對手・必敗」）：挑出勝算那一段另起一行（FB-044；對手數放不下就不寫）。
      // 不一定是最後一段：有自己人也有敵人的地方後面還接「・或與自己人操練」（畫面批次審查 C1）
      const parts = detail.split("・");
      const note = o.enabled && /^體力 \d+/.test(parts[0]) ? (parts.find((x) => x in ODDS_TONE) || "") : "";
      return inkCell(d.key, name, sub, d.icon, o.enabled ? `data-act="choose" data-id="${esc(o.id)}"` : "disabled", o.enabled ? "" : " off", note);
    });
    const moves = m.options.filter((o) => followsMode(o.id));
    moves.forEach((o) => used.add(o.id));
    const open = S.wheelSel === "move";
    cells.push(inkCell("move", "移動", moves.length ? `${moves.length} 條路` : "沒有路", MOVE_ICON,
      moves.length ? `data-act="wheel" data-key="move" aria-expanded="${open}"` : "disabled", (open ? " on" : "") + (moves.length ? "" : " off")));
    const moveCard = !open ? "" : `<div class="card act-move"><div class="seg move-mode" role="group" aria-label="走法">${MOVE_MODES.map((x) => `
          <button class="${S.moveMode === x.id ? "on" : ""}" data-act="move-mode" data-mode="${x.id}" aria-pressed="${S.moveMode === x.id}">${x.name}</button>`).join("")}</div>
        <div class="options">${moves.map((o) => `<button class="btn go" data-act="choose" data-id="${esc(o.id)}" ${o.enabled ? "" : "disabled"}>
          <span class="k">→</span><span>${esc(o.label)}</span></button>`).join("")}</div></div>`;
    // 其他只在此地才有的行動（招募、投靠、多出來的求見）收在摺疊裡，不佔行動列的高度
    const extras = m.options.filter((o) => !used.has(o.id));
    const here = extras.length ? `<details class="fold here"><summary>此地還能做 ${extras.length} 件事</summary><div class="fold-body options">${extras.map((o) => `
        <button class="btn" data-act="choose" data-id="${esc(o.id)}" ${o.enabled ? "" : "disabled"}><span>${esc(o.label)}</span></button>`).join("")}</div></details>` : "";
    return `<div class="act-bar" role="group" aria-label="行動">${cells.join("")}</div>${moveCard}${here}`;
  }

  // 展開移動之後，把走法與目的地那張卡捲到剛好露出來（W18 的作法搬過來：狀態列有心得提示時整頁往下推，
  // 卡片下緣會落到底部分頁列底下）。block: "nearest"：本來就看得到就不動；離分頁列多遠由 CSS 的 scroll-margin-bottom 決定
  function revealMoveCard() {
    const card = document.querySelector("#page .act-move");
    if (!card) return;
    const calm = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    card.scrollIntoView({ block: "nearest", behavior: calm ? "auto" : "smooth" });
  }

  // 公告的標題：伺服器給的每則是「**標題**＋空行＋全文」轉成的 HTML，標題在第一個 <strong> 裡（Game.bulletin）
  function bulletinTitle(html) {
    const box = document.createElement("template");
    box.innerHTML = html;
    const strong = box.content.querySelector("strong");
    return (strong || box.content).textContent.trim();
  }

  // 第一季濃縮版的「本週軍令」（計畫 T6；伺服器只送自己陣營的，散人沒有）：預設展開，收起來的狀態照週次記住（同公告卡）
  function ordersHtml(list, week, convoy) {
    const done = list.filter((o) => o.done).length;
    const cart = convoy ? `<div class="order-cart">🛒 ${esc(convoy)}</div>` : "";  // 押著的糧車（那一道沒了也照樣寫）
    const rows = list.map((o) => `
      <div class="order${o.done ? " done" : ""}">
        <div class="order-head"><b>${esc(o.title)}</b><span>${o.done ? "已達成" : `陣營 ${o.progress}／${o.quota}`}</span></div>
        <div class="order-text">${esc(o.text)}</div>
        <div class="order-bar" role="meter" aria-valuemin="0" aria-valuemax="${o.quota}" aria-valuenow="${o.progress}" aria-label="${esc(o.title)}"><i style="width:${pct(o.progress, o.quota)}%"></i></div>
        <div class="order-meta">你做了 ${o.mine} 次・截止 ${esc(o.deadline)}</div>
      </div>`).join("");
    return `<details class="fold orders" data-week="${week}" ${S.ordersShut === week ? "" : "open"}>
      <summary>📜 本週軍令（${list.length}${done ? `，已達成 ${done}` : ""}）</summary><div class="fold-body">${cart}${rows}</div></details>`;
  }

  // 第一季的結算卡（休季才有，計畫 T9）：結局與季末公告、最終態勢與三條戰況；十二件大事與各陣營出力前五收在摺疊裡
  function resultHtml(r) {
    // 態勢三條各用自己陣營的顏色、底色中性（T9 審查 M3）；戰況照江湖頁標兩端（FB-041）
    const bars = (rows, label, stance) => `<div class="fronts" role="group" aria-label="${label}">${rows.map((x) => `
      <div class="front"><div class="front-head"><span>${esc(x.name)}</span><b>${x.value}</b></div>
        <div class="front-bar${stance ? ` stance side-${esc(x.side)}` : ""}" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${x.value}" aria-label="${esc(x.name)}"><i style="width:${pct(x.value, 100)}%"></i></div>${stance ? "" : FRONT_ENDS}</div>`).join("")}</div>`;
    const events = r.timeline.map((e) => `<div class="result-event"><b>第 ${e.week} 週・${esc(e.title)}</b>${
      e.locked_by ? `<small>${esc(e.locked_by)} 改寫</small>` : ""}${e.text}</div>`).join("");
    const ranks = r.rankings.map((f) => `<div class="result-rank"><b>${esc(f.name)}</b>${f.rows.length
      ? `<ol>${f.rows.map(([n, v]) => `<li><span>${esc(n)}</span><i>${v}</i></li>`).join("")}</ol>`
      : "<p>（沒有人出力）</p>"}</div>`).join("");
    return `<section class="card result"><h2>賽季落幕：${esc(r.title)}</h2><div class="result-text">${r.text}</div>
      <h3>最終態勢</h3>${bars(r.stances, "最終態勢", true)}<h3>最終戰況</h3>${bars(r.fronts, "最終戰況", false)}
      <details class="fold"><summary>這一季的十二件大事</summary><div class="fold-body">${events}</div></details>
      <details class="fold"><summary>各陣營出力前五</summary><div class="fold-body result-ranks">${ranks}</div></details></section>`;
  }

  // 戰況條兩端標陣營（FB-041）：條上左邊金色那一截是黃巾佔的、右邊藍色是官軍，字的顏色跟那一截一樣
  const FRONT_ENDS = '<div class="front-ends" aria-hidden="true"><span class="huang">黃巾</span><span class="guan">官軍</span></div>';

  // 第一季濃縮版的三條戰況（伺服器有送 fronts 才畫）：0 是官軍穩控、100 是黃巾控制，條上黃的那一截是黃巾佔的。
  // 下面一行是三方態勢（S1：以前只有點開狀態列才看得到，結局提示講的就是它）
  function frontsHtml(fronts, stances) {
    return `<div class="fronts" role="group" aria-label="戰況：0 官軍穩控，100 黃巾控制">${fronts.map((f) => `
      <div class="front"><div class="front-head"><span>${esc(f.name)}</span><b>${f.value}</b></div>
        <div class="front-bar" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${f.value}" aria-label="${esc(f.name)}"><i style="width:${pct(f.value, 100)}%"></i></div>${FRONT_ENDS}</div>`).join("")}</div>${
      stances ? `<p class="stances-line">態勢　${STANCE_NAMES.map(([id, name]) => `${name} ${stances[id]}`).join("・")}</p>` : ""}`;
  }

  // 說書人的對話框（引導重做設計 8.1、6.2）：行動列（或事件的選項）上方，框上寫說話的人（之後換成師父、引薦人）。
  // 做完一步先列「✔ 完成」與獎勵，再接下一步的話。可以收起成一行；記的是收起的那一句，換了下一句就自己展開。
  // 結語有「知道了」，按了就不再出現
  const GUIDE_KEY = "tx-guide-shut";
  function guideShut() { try { return localStorage.getItem(GUIDE_KEY); } catch (e) { return null; } }
  function setGuideShut(text) { try { if (text) localStorage.setItem(GUIDE_KEY, text); else localStorage.removeItem(GUIDE_KEY); } catch (e) { /* 存不了就只在這一頁有效 */ } }
  function guideHtml(g) {
    if (!g) return "";
    if (!g.end && guideShut() === g.text) {
      return `<button class="guide-line" data-act="guide-open" aria-label="展開${esc(g.speaker)}的話"><b>${esc(g.speaker)}</b>：${esc(g.text)}</button>`;
    }
    const done = g.done.length ? `<div class="guide-done">${g.done.map((d) => d.startsWith("✔")
      ? '<span class="ok">✔ 完成</span>' : `<span class="reward">${esc(d)}</span>`).join("")}</div>` : "";
    const btn = g.end ? '<button class="btn small" data-act="guide-ack">知道了</button>'
      : '<button class="linkish" data-act="guide-shut">收起</button>';
    // 長的那幾步（軍令兩步一百多字）先露三行、點了看全文，不把行動與選項擠出第一屏（畫面批次審查 I3）
    const full = S.guideFull === g.text;
    return `<section class="card guide" aria-label="${esc(g.speaker)}的話"><div class="guide-head"><b>${esc(g.speaker)}</b>${btn}</div>${done}<p class="guide-text${full ? "" : " clamp"}" data-act="guide-more" role="button" tabindex="0" aria-expanded="${full}">${esc(g.text)}</p></section>`;
  }

  function pageJianghu() {
    const m = S.main;
    // 「剛剛」（A4）：預設只露出開頭幾行，太長的（例如新角色的開場故事）收著、點「展開全文」看完，不在卡片裡捲。
    // 展開記在 S.nowOpen（記的是那一則本身），換成新的一則就自動收回；其實放得下的話 afterPage() 會拿掉收合。
    // 畫的是 m.now：最新一則只是公告卡上已經有全文的大事時，伺服器改給再前面那一則（FB-046）；江湖紀錄頁照舊用 m.latest
    const expanded = S.nowOpen === m.now;
    const [text, chips] = !m.card && m.now ? splitChips(m.now) : ["", ""];
    const now = m.card
      ? `<div class="card battle-card">${m.card}${m.now || ""}
           ${m.card_id != null ? `<button class="linkish" data-act="report" data-id="${m.card_id}">看完整戰報 ›</button>` : ""}</div>`
      : m.now ? `<div class="now ${expanded ? "open" : "clamp"}"><div class="now-text">${text}<button class="linkish now-more" data-act="now-more" aria-expanded="${expanded}">${nowMore(expanded)}</button></div>${chips}</div>` : "";
    const free = m.free_text != null
      ? `<form class="free" id="free-form"><input class="input" name="text" maxlength="20" placeholder="${esc(m.free_text || "輸入你想做的事（20字內）")}"><button class="btn primary small" type="submit">送出</button></form>`
      : "";
    // 路上那顆灰的「（在路上，幾時抵達）」不畫：往哪、幾時到狀態列已經寫著（FB-046），少一顆也讓路上的捷徑回到第一屏（FB-048）
    const opts = m.options.filter((o) => o.id !== "act:on_road");
    // 走法切換：選單上有「前往」或路上的「折返」才出現（對話、事件、戰鬥的選單沒有），緊貼在第一個這種選項上面——
    // 它只管這兩種，放在整排選項最上面的話，第一屏就被它擠掉一個選項（A4）
    const firstMove = opts.findIndex((o) => followsMode(o.id));
    const links = m.on_road
      ? `<div class="road-links" role="group" aria-label="路上可以去的地方">${ROAD_LINKS.map((x) =>
        `<button class="btn ghost small" data-act="tab" data-tab="${x.tab}">${x.name}</button>`).join("")}</div>`
      : "";
    const modes = firstMove >= 0
      ? `<div class="seg move-mode" role="group" aria-label="走法"><span aria-hidden="true">走法</span>${MOVE_MODES.map((x) => `
          <button class="${S.moveMode === x.id ? "on" : ""}" data-act="move-mode" data-mode="${x.id}" aria-pressed="${S.moveMode === x.id}">${x.name}</button>`).join("")}
        </div>`
      : "";
    const menu = idleMenu(m) ? actionBar(m) : `<div class="options">${opts.map((o, i) => o.id === FREE_TEXT_OPTION && S.answering && o.enabled ? `
        <form class="free answer" id="answer-form"><input class="input" name="text" maxlength="20" placeholder="${esc(o.label)}（20字內）" aria-label="${esc(o.label)}"><button class="btn primary small" type="submit">說出口</button></form>` : `${i === firstMove ? modes : ""}
        <button class="btn ${followsMode(o.id) ? "go" : ""}" data-act="choose" data-id="${esc(o.id)}" ${o.enabled ? "" : "disabled"}>
          <span class="k">${o.id.startsWith("move:") ? "→" : o.id.startsWith("road:back") ? "↩" : i + 1}</span><span>${esc(o.label)}</span>
        </button>`).join("")}
      </div>`;
    const scene = `<section class="card scene">${m.scene}</section>`;
    const tail = `<div class="mini" data-act="tab" data-tab="map" role="button" aria-label="展開輿圖">${m.minimap}</div>
      <button class="linkish" data-act="news" data-news="journal">看江湖紀錄 ›</button>`;
    // 第一季把 beta 的主線關掉、其他也都沒有東西時，quest 是空的：這一塊不畫，由本週大事卡與倒數撐著（計畫 T8）
    const quest = m.quest && m.quest.trim()
      ? `<details class="fold quest"><summary>📜 主線與目標</summary><div class="fold-body">${m.quest}</div></details>`
      : "";
    // 公告卡（第一季）：這一週已經發生的大事，新的在前；排在最上面、「剛剛」之前。沒有就不畫。
    // 預設縮成一行「📣 本週江湖大事（2）：標題、標題」（放不下截斷加「…」），點了才展開全文（FB-039）：兩件大事的全文
    // 加上戰鬥卡片，會把整排行動擠到分頁列底下。展開與否記在 S.boardOpen（鍵是週次，toggle 監聽見下面），
    // 輪詢重畫不會把它關掉，換週就回到收起
    const week = m.status && m.status.calendar ? m.status.calendar.week : 0;
    const board = m.bulletin && m.bulletin.length
      ? `<details class="fold bulletin" data-week="${week}" ${S.boardOpen === week ? "open" : ""}>
          <summary><span class="bulletin-head">📣 本週江湖大事（${m.bulletin.length}）</span><span class="bulletin-titles">${esc(m.bulletin.map(bulletinTitle).join("、"))}</span></summary>
          <div class="fold-body">${m.bulletin.map((b) => `<div class="bulletin-item">${b}</div>`).join("")}</div></details>`
      : "";
    // 三條戰況排在行動列下面、小地圖上面，不擠掉第一屏的公告卡、「剛剛」、場景與行動列
    const fronts = m.fronts ? frontsHtml(m.fronts, m.status && m.status.stances) : "";
    const resultCard = m.season_result ? resultHtml(m.season_result) : "";  // 休季的結算卡排在最上面（計畫 T9）
    // 本週軍令排在行動列（與路上捷徑）下面、三條戰況上面：不擠掉第一屏的公告、「剛剛」、場景與行動列（計畫 T6）
    const orderCard = m.orders || m.convoy ? ordersHtml(m.orders || [], week, m.convoy) : "";
    // 劇情文字在上、行動在下（企劃者 2026-10-04）。行動列只有一排，375×812 上「剛剛」、場景與整排行動都在第一屏。
    // 路上的三個捷徑（links）緊接在場景（「也可以打開輿圖改去別處，或去修練、煉製」那一段）底下、選項上面：
    // 排在路上的五六顆選項底下時落在第一屏外，要捲才看得到（FB-048）。說書人的話緊貼在行動上方（引導重做設計 8.1）
    const guide = guideHtml(m.guide);
    return `${resultCard}${board}${quest}${now}${scene}${links}${guide}${free}${menu}${orderCard}${fronts}${tail}`;
  }

  // ── 修練 ──
  function pagePractice() {
    const x = S.menxia;
    if (!x) return '<p class="muted">載入中…</p>';
    const s = S.main.status;
    // 身上的功法卡（FB-006）：目前切到的那一門放前面
    const slots = x.slot_cards.filter((c) => c.kind === S.kind).concat(x.slot_cards.filter((c) => c.kind !== S.kind));
    // 目前這一門有沒有功法、練滿了沒（伺服器照 team.MAX_LEVEL 說）：沒有或練滿就不能鍛鍊（C5），有了就不能再自創（C4）
    const cur = x.slot_cards.find((c) => c.kind === S.kind) || { learned: false, level: 0, maxed: false };
    const train = !cur.learned ? `還沒有${esc(S.kind)}` : cur.maxed ? "已練到第十成" : "";
    // 名冊只有本人一列（還沒有同伴）時跟上面的本人卡重複，不畫（C6）
    const mates = x.roster.length > 1;
    return `
      <div class="msg" id="mx-msg">${S.message}</div>
      <div class="card">
        <div class="seg">${KINDS.map((k) => `<button class="${S.kind === k ? "on" : ""}" data-act="kind" data-kind="${k}">${k}</button>`).join("")}</div>
        <div class="row">
          <button class="btn ${train ? "" : "primary"}" data-act="mx" data-op="practice" ${train ? "disabled" : ""}>${train || `鍛鍊${esc(S.kind)}`}</button>
          <button class="btn" data-act="mx" data-op="heal" ${s.injury >= 1 ? "" : "disabled"}>療傷</button>
        </div>
        <p class="muted">${x.rules.replace(/<\/?p>/g, "")}</p>
      </div>
      <div class="label">身上的功法</div>
      ${slots.map((c) => `<div class="card">${c.card}</div>`).join("")}
      <div class="label">自創功法</div>
      ${cur.learned
        ? `<div class="card"><p class="muted">你已經有一門${esc(S.kind)}了。想換別的，可以去煉製，或在功法庫改練。</p></div>`
        : `<form class="card" id="create-skill">
        <p class="muted">取名就決定了屬性、威力與成長，全服不能重名。你還沒有${esc(S.kind)}，這一欄空著，可以自創一門。</p>
        <div class="row"><input class="input" name="name" maxlength="12" placeholder="幫你的${esc(S.kind)}取個名字" style="flex:2"><button class="btn" type="submit">自創</button></div>
      </form>`}
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
      ${mates ? `<div class="list">${x.roster.map((r) => `<button class="${x.person === r.key ? "on" : ""}" data-act="person" data-key="${esc(r.key)}">${esc(r.label)}</button>`).join("")}</div>` : ""}
      ${mates && x.person ? `<div class="card">${x.person_card}
        ${x.person === "player" ? '<p class="muted">本人一直都在隊伍裡。</p>' // 本人不能加入、移出（引擎也會擋）
          : x.person.startsWith("follower:") ? "" // 部下（計畫 T5）也不能加入、移出；角色卡已經寫了
          : `<button class="btn ${x.on_team ? "" : "primary"}" data-act="mx" data-op="${x.on_team ? "leave" : "join"}">${x.on_team ? "移出隊伍" : "加入隊伍"}</button>`}</div>` : ""}`;
  }

  // ── 煉製 ──
  function pageCraft() {
    const x = S.menxia;
    if (!x) return '<p class="muted">載入中…</p>';
    const name = (id) => x.materials.find((m) => m.id === id);
    const used = (id) => S.craftSel.filter((s) => s === id).length;
    const ready = S.craftSel.length === x.per_craft;
    // 素材列表只列手上還剩的：全放進爐裡的那一樣不留一顆灰的「×0」（FB-049），點爐裡那一格拿出來就回到列表
    const left = x.materials.filter((m) => m.count - used(m.id) > 0);
    // 太極火爐只管放素材與開爐；挑素材在下面的素材列表（企劃者 2026-10-04：「選素材不要也在那邊，用舊的模式來顯示素材」）。
    // 「開爐煉製」緊接在成本那一行下面、不黏在底部（FB-048）：黏著時會蓋住素材列表、開爐後那一行字與「素材說明」
    return `
      <div class="msg" id="mx-msg">${S.message}</div>
      ${furnaceSvg([name(S.craftSel[0]), name(S.craftSel[1])], ready)}
      <div class="card" id="craft-line">${S.craftLine || x.craft_line}</div>
      <div class="act-row"><button class="btn primary" id="forge" data-act="forge" ${ready ? "" : "disabled"}>開爐煉製</button></div>
      <div class="label">素材 <small class="muted">點一樣放進爐裡</small></div>
      ${left.length ? `<div class="chips">${left.map((m) => `
        <button class="chip r${m.rank}" data-act="slot" data-id="${esc(m.id)}">
          <span class="n">×${m.count - used(m.id)}</span><b>${esc(m.name)}</b><small>${esc(m.tier)}・屬${esc(m.attribute)}</small>
        </button>`).join("")}</div>`
        : x.materials.length ? '<p class="muted">素材都放進爐裡了。</p>'
        : '<p class="muted">背包裡還沒有素材。去探索、遊歷打贏，或是碰上奇遇都拿得到。</p>'}
      ${x.clue_items?.length ? `<div class="label">伏筆物品</div>
      <div class="chips clues">${x.clue_items.map((i) => `<div class="clue"><b>${esc(i.name)}</b><span>×${i.count}</span></div>`).join("")}</div>` : ""}
      <details class="fold"><summary>素材說明</summary><div class="fold-body">${x.bag}</div></details>`;
  }

  // ── 輿圖 ──
  function pageMap() {
    const m = S.map;
    if (!m) return '<p class="muted">展開輿圖…</p>';
    // 步行／趕路／疾行緊接在地圖下面、不黏在底部（FB-048）：黏著時會蓋住地點詳情「局勢」那一行以下。按了的結果寫在它下面那一行
    // 步行／趕路／疾行緊接在選地點底下、地圖上面：排在地圖下面時落在底部分頁列底下，要捲才按得到（FB-045～052 審查 I2）
    return `
      <div class="card">${m.header}</div>
      <div class="seg">${m.layers.map((l) => `<button class="${m.layer === l.id ? "on" : ""}" data-act="layer" data-layer="${esc(l.id)}">${esc(l.name)}</button>`).join("")}</div>
      <div class="map-tools">
        <select class="input" id="place">${m.places.map((p) => `<option value="${esc(p.id)}" ${p.id === m.selected ? "selected" : ""}>${esc(p.label)}</option>`).join("")}</select>
      </div>
      ${m.travel ? `<div class="travel-row">${m.travel.map((t) =>
        `<button class="btn ${t.mode === "walk" ? "primary" : ""}" data-act="travel" data-mode="${esc(t.mode)}" ${t.enabled ? "" : "disabled"}>${esc(t.label)}</button>`).join("")}</div>` : ""}
      <div class="map-wrap" id="map">${m.svg}${MAP_CTL}</div>
      <div class="msg">${S.mapNotice || ""}</div>
      <div class="card">${m.detail}</div>`;
  }

  // 地圖框右上角的按鈕（給不會手勢的人，像一般地圖 App）：回到所在地、放大、縮小
  const MAP_CTL = `<div class="map-ctl">
    <button type="button" data-act="map-home" aria-label="回到所在地" title="回到所在地"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="6.5"/><path d="M12 2v4M12 18v4M2 12h4M18 12h4"/></svg></button>
    <button type="button" data-act="map-zoom" data-step="in" aria-label="放大" title="放大"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M12 5v14"/></svg></button>
    <button type="button" data-act="map-zoom" data-step="out" aria-label="縮小" title="縮小"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14"/></svg></button>
  </div>`;

  // ── 輿圖的視圖（W16）：純數學，不碰 DOM ──
  // 視圖 v = { s 倍率, cx, cy 視窗中心對著的地圖座標 }，地圖座標＝原尺寸的 px。存中心不存位移：視窗寬高變了（轉向、拉視窗）還對得上。
  // vw、vh 是視窗（地圖框）的大小，W、H 是地圖的大小（svg 的 viewBox）。手勢、滾輪、按鈕都走這幾個函式
  const MAP_MAX = 2; // 最多放到原尺寸的兩倍
  const fitScale = (vw, vh, W, H) => Math.min(vw / W, vh / H); // 整張看得完的倍率（也是最小倍率）
  const clampScale = (s, vw, vh, W, H) => Math.min(MAP_MAX, Math.max(fitScale(vw, vh, W, H), s));
  // 夾住：某一軸的地圖比視窗小就置中；比視窗大就不能拖到露出地圖外面
  function clampView(v, vw, vh, W, H) {
    const s = clampScale(v.s, vw, vh, W, H);
    const axis = (c, view, size) => {
      const half = view / 2 / s; // 視窗的一半，換成地圖單位
      return size * s <= view ? size / 2 : Math.min(size - half, Math.max(half, c));
    };
    return { s, cx: axis(v.cx, vw, W), cy: axis(v.cy, vh, H) };
  }
  // 視窗裡 (px, py) 底下的地圖座標；反過來，倍率 s 時要讓地圖座標 m 落在 (px, py)，中心該在哪
  const mapPoint = (v, px, py, vw, vh) => [v.cx + (px - vw / 2) / v.s, v.cy + (py - vh / 2) / v.s];
  const pinView = (s, m, px, py, vw, vh) => ({ s, cx: m[0] - (px - vw / 2) / s, cy: m[1] - (py - vh / 2) / s });
  // 以視窗裡 (px, py) 為準縮放：縮放前後那一點底下的地圖座標不變（碰到地圖邊緣被夾住時例外）
  function zoomAt(v, factor, px, py, vw, vh, W, H) {
    const s = clampScale(v.s * factor, vw, vh, W, H);
    return clampView(pinView(s, mapPoint(v, px, py, vw, vh), px, py, vw, vh), vw, vh, W, H);
  }
  // 地點點擊區的半徑（地圖單位）：螢幕上至少約 22px；上限 34，最近的兩個地點相距 68.6，再大會互相蓋住
  const hitRadius = (s) => Math.min(34, Math.max(22, 22 / s));

  // ── 輿圖的手勢（W16）──
  // 地圖照原本的像素大小放在固定高度的框裡，用 transform 平移、縮放（不改 viewBox：手勢中每一幀重描整張山水，手機會卡）。
  // 一指或滑鼠左鍵拖移、雙指縮放、滾輪縮放；按下到放開都沒移超過 8px、也從沒有第二指，才算點了一下（選地點）。
  // pointermove／up 掛在 document：重畫換掉了地圖框，手勢也接得下去（mapReady 會把指標抓回新的框）
  const TAP_SLOP = 8;
  const grip = { pts: new Map(), tap: null, ref: null, frame: 0 }; // 按著的指標（id → [x, y]）、點一下的候選、起點、排好的那一幀
  const mapHeld = () => grip.pts.size > 0;
  let mapBox = null; // 上次套用時的地圖框大小 [寬, 高]：大小變了而原本是整張，就維持整張
  let glideTimer = 0;

  // 地圖框與地圖的大小、框的內緣在畫面上的位置；地圖還沒畫出來（或框沒有大小）回 null
  function mapGeom(wrap) {
    const svg = wrap && wrap.querySelector(".tx-world-map > svg");
    const vb = svg && svg.viewBox && svg.viewBox.baseVal;
    if (!vb || !vb.width || !vb.height || !wrap.clientWidth || !wrap.clientHeight) return null;
    const r = wrap.getBoundingClientRect();
    return { wrap, svg, vw: wrap.clientWidth, vh: wrap.clientHeight, W: vb.width, H: vb.height, x0: r.left + wrap.clientLeft, y0: r.top + wrap.clientTop };
  }
  const circleAt = (c) => {
    const p = c && [Number(c.getAttribute("cx")), Number(c.getAttribute("cy"))];
    return p && p.every(Number.isFinite) ? p : null;
  };
  // 地點的中心：它那一組裡第一個透明的點擊圓
  const placePoint = (svg, id) => (id ? circleAt(svg.querySelector(`g[data-loc="${CSS.escape(id)}"] > circle[fill-opacity="0"]`)) : null);
  // 所在地：在路上用「你」那個點，否則用所在的地點，都找不到就用地圖中心
  const herePoint = (g) => circleAt(g.svg.querySelector("circle.tx-you")) || placePoint(g.svg, S.map && S.map.here) || [g.W / 2, g.H / 2];

  // 把 S.mapView 夾住、套到地圖上；glide：按鈕、下拉選單的移動滑一下（≤150ms），手勢與滾輪中不滑
  function applyMapView(glide = false, g = mapGeom(document.getElementById("map"))) {
    if (!g || !S.mapView) return;
    const { wrap, vw, vh, W, H } = g;
    // 地圖框大小變了（轉向、拉視窗，也可能是在別的分頁時變的）而原本是整張：維持整張
    if (mapBox && (mapBox[0] !== vw || mapBox[1] !== vh) && S.mapView.s <= fitScale(mapBox[0], mapBox[1], W, H) + 1e-9) {
      S.mapView = { ...S.mapView, s: fitScale(vw, vh, W, H) };
    }
    mapBox = [vw, vh];
    const v = (S.mapView = clampView(S.mapView, vw, vh, W, H));
    clearTimeout(glideTimer);
    wrap.classList.toggle("glide", glide);
    if (glide) glideTimer = setTimeout(() => wrap.classList.remove("glide"), 200);
    g.svg.style.transform = `translate(${vw / 2 - v.cx * v.s}px, ${vh / 2 - v.cy * v.s}px) scale(${v.s})`;
    // 點擊區跟著縮放：透明圓 r=16，外框寬 2×(R−16) 把它撐到半徑 R（style.css 的 --hit）
    const hit = `${Math.round(2 * (hitRadius(v.s) - 16))}px`;
    if (wrap.style.getPropertyValue("--hit") !== hit) wrap.style.setProperty("--hit", hit);
    // 到頂、到底那一顆按不下去（看得出已經到頭了）
    wrap.querySelector('[data-step="in"]').disabled = v.s >= MAP_MAX - 1e-9;
    wrap.querySelector('[data-step="out"]').disabled = v.s <= fitScale(vw, vh, W, H) + 1e-9;
  }

  // 輿圖頁每次畫好（afterPage）：第一次打開就決定視圖，之後照舊套用；掛上這個框自己的監聽
  function mapReady() {
    const wrap = document.getElementById("map");
    if (!wrap) return;
    // 手勢的監聽都掛在捕獲階段：不冒泡的事件（例如測試用 new PointerEvent 送的）也收得到
    wrap.addEventListener("pointerdown", gripDown, true);
    wrap.addEventListener("wheel", mapWheel, { passive: false, capture: true });
    // 舊版 iOS Safari 的捏合手勢、拖到地圖上的字開始原生拖曳，都擋掉
    for (const t of ["gesturestart", "gesturechange", "dragstart"]) wrap.addEventListener(t, (ev) => ev.preventDefault());
    for (const id of grip.pts.keys()) {
      try { wrap.setPointerCapture(id); } catch (e) { /* 那一指已經放開了 */ }
    }
    const g = mapGeom(wrap);
    if (g && !S.mapView) {
      // 這次載入網頁後第一次打開，對準所在地：手機照原尺寸；寬螢幕照框寬（最多原尺寸）。都不給整張——
      // 整張只有約 0.37 倍，地名剩 5px 上下（E2／FB-012），寬螢幕的橫框也一樣
      const phone = !!(PHONE && PHONE.matches);
      const [cx, cy] = herePoint(g);
      S.mapView = { s: phone ? 1 : Math.min(1, g.vw / g.W), cx, cy };
    }
    applyMapView(false, g);
  }

  function gripDown(ev) {
    if (ev.button !== 0 || ev.target.closest(".map-ctl")) return; // 只收滑鼠左鍵、觸控、筆；角落的按鈕照常按
    if (grip.pts.has(ev.pointerId)) gripEnd(); // 同一個指標又按下：上一次沒收到放開（例如在視窗外放開），重新來過
    if (grip.pts.size >= 2) return; // 第三指不管
    gripFlush();
    const wrap = ev.currentTarget;
    try { wrap.setPointerCapture(ev.pointerId); } catch (e) { /* 合成的事件抓不住；放開照樣由 document 收 */ }
    grip.pts.set(ev.pointerId, [ev.clientX, ev.clientY]);
    grip.tap = grip.pts.size === 1 ? { id: ev.pointerId, x: ev.clientX, y: ev.clientY, target: ev.target } : null;
    wrap.classList.remove("glide");
    wrap.classList.add("grabbing");
    if (!grip.tap) wrap.classList.add("moving");
    gripBase();
  }

  // 指標數變了（按下、放開一指）：從現在的位置與視圖重新記起點。一指記上一幀的位置（拖移）；
  // 兩指記開始時的視圖、兩指距離，以及兩指中點底下的地圖座標（之後要一直跟著中點走）
  function gripBase() {
    const pts = [...grip.pts.values()];
    const g = mapGeom(document.getElementById("map"));
    grip.ref = null;
    if (!g || !S.mapView || !pts.length) return;
    if (pts.length === 1) { grip.ref = { at: pts[0] }; return; }
    const [[ax, ay], [bx, by]] = pts;
    grip.ref = { v: S.mapView, d: Math.max(1, Math.hypot(bx - ax, by - ay)), m: mapPoint(S.mapView, (ax + bx) / 2 - g.x0, (ay + by) / 2 - g.y0, g.vw, g.vh) };
  }

  // 一幀套用一次（同一幀的多次移動合併）
  function gripStep() {
    grip.frame = 0;
    const g = mapGeom(document.getElementById("map"));
    const ref = grip.ref;
    const pts = [...grip.pts.values()];
    if (!g || !ref || !S.mapView) return;
    if (pts.length === 1 && ref.at) {
      // 地圖跟著手指（游標）走
      const [x, y] = pts[0];
      const v = S.mapView;
      S.mapView = clampView({ s: v.s, cx: v.cx - (x - ref.at[0]) / v.s, cy: v.cy - (y - ref.at[1]) / v.s }, g.vw, g.vh, g.W, g.H);
      ref.at = [x, y];
    } else if (pts.length === 2 && ref.m) {
      const [[ax, ay], [bx, by]] = pts;
      const s = clampScale(ref.v.s * Math.hypot(bx - ax, by - ay) / ref.d, g.vw, g.vh, g.W, g.H);
      S.mapView = clampView(pinView(s, ref.m, (ax + bx) / 2 - g.x0, (ay + by) / 2 - g.y0, g.vw, g.vh), g.vw, g.vh, g.W, g.H);
    } else return;
    applyMapView(false, g);
  }
  // 還沒套用的那一幀先套上（指標數要變了、或要放開了）
  function gripFlush() {
    if (!grip.frame) return;
    cancelAnimationFrame(grip.frame);
    gripStep();
  }

  function gripUp(ev) {
    if (!grip.pts.has(ev.pointerId)) return;
    gripFlush();
    grip.pts.delete(ev.pointerId);
    const tap = grip.tap;
    if (grip.pts.size) { grip.tap = null; gripBase(); return; } // 雙指放開一指：剩下那一指接著拖，不算點選
    gripEnd();
    if (ev.type === "pointerup" && tap && tap.id === ev.pointerId) mapPick(tap.target);
  }
  function gripEnd() {
    if (grip.frame) cancelAnimationFrame(grip.frame);
    grip.pts.clear();
    grip.tap = grip.ref = null;
    grip.frame = 0;
    document.getElementById("map")?.classList.remove("grabbing", "moving");
  }

  // 在地圖上點了一下：選那個地點，視圖不動
  async function mapPick(target) {
    const loc = target && target.closest && target.closest("[data-loc]");
    if (!loc) return;
    S.mapNotice = "";
    try { await loadMap(loc.getAttribute("data-loc")); } catch (e) { /* 提示過 */ }
  }

  // 滾輪以游標為準縮放；觸控板雙指捏合在 Chrome／Edge 是帶 ctrlKey 的 wheel，一樣處理（也因此擋掉瀏覽器自己的整頁放大）
  function mapWheel(ev) {
    ev.preventDefault();
    const g = mapGeom(ev.currentTarget);
    if (!g || !S.mapView) return;
    const dy = ev.deltaY * (ev.deltaMode === 1 ? 16 : ev.deltaMode === 2 ? g.vh : 1);
    S.mapView = zoomAt(S.mapView, Math.exp(-dy * 0.0015), ev.clientX - g.x0, ev.clientY - g.y0, g.vw, g.vh, g.W, g.H);
    applyMapView(false, g);
  }

  // 角落的按鈕：以視窗中心縮放 1.5 倍
  function mapZoom(step) {
    const g = mapGeom(document.getElementById("map"));
    if (!g || !S.mapView) return;
    S.mapView = zoomAt(S.mapView, step === "out" ? 1 / 1.5 : 1.5, g.vw / 2, g.vh / 2, g.vw, g.vh, g.W, g.H);
    applyMapView(true, g);
  }
  // 回到所在地：倍率照舊（比原尺寸小就拉到原尺寸），中心移到所在地
  function mapHome() {
    const g = mapGeom(document.getElementById("map"));
    if (!g || !S.mapView) return;
    const [cx, cy] = herePoint(g);
    S.mapView = { s: Math.max(1, S.mapView.s), cx, cy };
    applyMapView(true, g);
  }
  // 下拉選單選了地點：倍率照舊，中心移到那個地點（它可能在視窗外）
  function mapCenterOn(id) {
    const g = mapGeom(document.getElementById("map"));
    const p = g && placePoint(g.svg, id);
    if (!p || !S.mapView) return;
    S.mapView = { ...S.mapView, cx: p[0], cy: p[1] };
    applyMapView(true, g);
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
        <div class="label">帳號</div>
        <button class="btn ghost" data-act="logout">登出</button>
        ${S.main.admin ? `
          <section class="admin-zone stack" aria-label="管理者工具">
            <h4>管理者工具（只有你看得到）</h4>
            <p class="muted">每一項按了都會先問一次才送出；做完會關掉設定、回到江湖頁。</p>
            <div class="row seasons"><button class="btn" data-act="admin" data-op="open_season">開季</button><button class="btn warn" data-act="admin" data-op="end_season">⚠ 立刻收季</button><button class="btn warn" data-act="admin" data-op="next_season">⚠ 開啟下一季</button></div>
            <p class="muted">時間快轉（全服一起快轉，只在測試時用）</p>
            <div class="row">${[1, 8, 24].map((h) => `<button class="btn small" data-act="admin" data-op="fast_forward" data-hours="${h}">+${h} 小時</button>`).join("")}</div>
            ${a ? `
              <p class="muted">觸發（人少、大勢推不到門檻時用；效果跟自然發生一樣）</p>
              <div class="row ad-row"><span class="ad-tag">決戰</span><select class="input" id="ad-battle" aria-label="決戰">${opts(a.battles)}</select><button class="btn small" data-act="admin" data-op="start_battle">立刻開戰</button></div>
              <div class="row ad-row"><span class="ad-tag">事件</span><select class="input" id="ad-fire" aria-label="事件">${opts(a.events)}</select><button class="btn small" data-act="admin" data-op="fire">觸發</button></div>
              <div class="row ad-row"><span class="ad-tag">大勢</span><select class="input" id="ad-trend" aria-label="大勢">${opts(a.trends)}</select><input class="input" id="ad-amount" type="number" value="10" aria-label="推動量" style="max-width:76px"><button class="btn small" data-act="admin" data-op="push_trend">推動</button></div>
              ${a.timetable.length ? timetableHtml(a) : ""}
              <p class="muted">救場</p>
              <div class="row ad-row"><span class="ad-tag">戰況</span><select class="input" id="ad-front" aria-label="定戰況的線">${opts(a.trends)}</select><input class="input" id="ad-value" type="number" value="50" min="0" max="100" aria-label="戰況" style="max-width:76px"><button class="btn small" data-act="admin" data-op="set_trend">定戰況</button></div>
              ${a.results.length ? `<div class="row ad-row"><span class="ad-tag">結果</span><select class="input" id="ad-result" aria-label="定結果">${a.results.map((x) => `<option value="${esc(x.value)}">${esc(x.label)}</option>`).join("")}</select><button class="btn small" data-act="admin" data-op="resolve_event">定結果</button></div>` : ""}
              ${a.locks.length ? `<div class="row ad-row"><span class="ad-tag">鎖定</span><select class="input" id="ad-lock" aria-label="清鎖定">${opts(a.locks)}</select><button class="btn small" data-act="admin" data-op="clear_lock">清鎖定</button></div>` : ""}
              <div class="row"><button class="btn warn" data-act="admin" data-op="cancel_battle">⚠ 取消決戰</button></div>
              <p class="muted">重設密碼（朋友忘記密碼時用；臨時密碼私下告訴他）</p>
              <form id="reset-form"><div class="row"><input class="input" name="target" placeholder="帳號或名號"><input class="input" name="temp" placeholder="臨時密碼"><button class="btn small" type="submit">重設</button></div><p class="form-msg" role="alert"></p></form>` : ""}
          </section>` : ""}
      </div>`;
  }

  // 設定頁的「時刻表」（計畫 T10）：十二件照順序、標狀態；三場決戰與季末還沒結算的有日期時間欄位與「排定」
  // （欄位是這台裝置的當地時間，送出時換成秒數）；最後是「跳到下一件大事」
  function localInput(sec) {
    const d = new Date(sec * 1000);
    const p = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
  }
  function timetableHtml(a) {
    return `
      <p class="muted">時刻表（三場大戲與季末可以排時間；時間到了自動開集結，季末就是收季）</p>
      <div class="tt-list">${a.timetable.map((r) => `
        <div class="tt-row">
          <div class="tt-head"><span class="tt-name">${esc(r.label)}</span><span class="tt-state">${esc(r.result ? `${r.state_text}・${r.result}` : r.state_text)}</span></div>
          ${r.schedulable ? `<div class="row"><input class="input" type="datetime-local" id="tt-at-${esc(r.id)}" value="${localInput(r.at_real)}" aria-label="${esc(r.label)}的時間"><button class="btn small" data-act="admin" data-op="schedule" data-id="${esc(r.id)}">排定</button></div>` : ""}
        </div>`).join("")}</div>
      <div class="row"><button class="btn" data-act="admin" data-op="jump_next">跳到下一件大事</button></div>`;
  }

  // 管理者動作的確認框（G3）：每一項按了都先問一次、問句說出後果。疊在設定抽屜上面、不重畫抽屜，
  // 選好的下拉選單、填好的重設密碼欄位都留著；按「取消」或旁邊的暗處就關掉，什麼都不送
  let askGo = null;
  function ask(text, yes, go) {
    closeAsk();
    askGo = go;
    document.body.insertAdjacentHTML("beforeend", `
      <div class="ask-layer">
        <div class="ask-bg" data-act="ask-no"></div>
        <div class="ask" role="alertdialog" aria-modal="true" aria-labelledby="ask-text">
          <p id="ask-text">${esc(text)}</p>
          <div class="row"><button class="btn" data-act="ask-no">取消</button><button class="btn danger" data-act="ask-yes">${esc(yes)}</button></div>
        </div>
      </div>`);
    document.querySelector('.ask [data-act="ask-no"]').focus();
  }
  function closeAsk() {
    document.querySelector(".ask-layer")?.remove();
    askGo = null;
  }

  // 管理者動作的問句與確認鈕（照抽屜裡選好的下拉選單）
  function adminAsk(op, body) {
    const picked = (id) => { const el = document.getElementById(id); return el && el.selectedIndex >= 0 ? el.options[el.selectedIndex].text : ""; };
    const amount = `${body.amount >= 0 ? "+" : ""}${body.amount}`;
    return {
      open_season: ["開季：賽季從籌備中正式開始，全服玩家都能行動了。記得排三場大戲與季末的時間（預設在第 6、9、11 週中、第 12 週末），確定？", "確定開季"],
      // 照 Game.admin_end_season 實際做的事寫（只在進行中有效）
      end_season: ["立刻收季：這一季馬上結束、算出結局與武學榜，全服進入休季（之後再按「開啟下一季」）；沒打完的決戰直接收掉、不算結果，確定？", "確定收季"],
      // 照 SqliteWorldStore.next_season 實際做的事寫（只在休季有效）
      next_season: [`開啟下一季（休季才有效）：新的一季立刻開始，同伴全部重獲自由、自創武學名字釋出、煉製配方清空、天機 +1，沒打完的決戰清掉。${
        S.admin && S.admin.next_has_timetable ? "記得排三場大戲與季末的時間（預設在第 6、9、11 週中、第 12 週末）。" : ""}確定？`, "確定開啟下一季"],  // FB-050
      fast_forward: [`時間快轉 ${body.hours} 小時（全服一起），確定？`, `快轉 ${body.hours} 小時`],
      start_battle: [`立刻開戰「${picked("ad-battle")}」：全服一起進入集結，確定？`, "確定開戰"],
      fire: [`觸發「${picked("ad-fire")}」：效果跟自然發生一樣，全服都受影響，確定？`, "確定觸發"],
      push_trend: [`推動大勢「${picked("ad-trend")}」${amount}：全服一起，確定？`, "確定推動"],
      // 時刻表與救場（計畫 T10）
      schedule: [`把「${body.title}」排在 ${body.when}：時間到了自動開集結（季末就是收季），確定？`, "確定排定"],
      jump_next: ["跳到下一件大事：全服的季時間一起往前推，到了的大事立刻結算（決戰直接開集結），確定？", "確定跳過去"],
      set_trend: [`把「${picked("ad-front")}」定成 ${body.value}：全服一起，推過門檻照常觸發，確定？`, "確定定戰況"],
      resolve_event: [`定下「${picked("ad-result")}」：照時刻表結算、全服公告，之後不再擲骰，確定？`, "確定定結果"],
      clear_lock: [`清掉「${picked("ad-lock")}」的鎖定：結算時照沒人鎖定擲骰，確定？`, "確定清掉"],
      cancel_battle: ["取消正在集結或開打的決戰：不算勝負，參戰者都會收到通知；時刻表的決戰不會自己再開，要用「定結果」收尾，確定？", "確定取消"],
    }[op] || ["確定要這麼做？", "確定"];
  }

  // 確認過的管理者動作：做完關掉抽屜、回到江湖頁看結果，結果照舊用提示泡泡講（G4）。
  // 請求本身沒成（連不上、伺服器出錯）就留在抽屜裡，api() 已經提示過原因
  async function adminDo(op, body) {
    await busy(async () => {
      const r = await api(`/api/do/${op}`, body);
      S.sheet = false;
      setMain(r.main);
      await goTab("jianghu");
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      toast(text || "已完成。");
    });
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
    if (id === FREE_TEXT_OPTION) { // 隨口應對：先叫出輸入框，寫好再送（見 answer）
      S.answering = true;
      renderPage();
      const input = document.querySelector("#answer-form .input");
      if (input) input.focus();
      return;
    }
    await busy(async () => {
      document.querySelectorAll(".options .btn").forEach((b) => { b.disabled = true; });
      btn.classList.add("busy");
      // 跟 server.py 的 may_generate_dialogue 同一個判斷：這些選項要等模型回話
      const talking = id === "act:socialize" || ((id.startsWith("talk:") || id.startsWith("call:")) && id !== "talk:leave" && id !== "call:back");
      if (talking) btn.lastElementChild.textContent = "對方沉吟中…";
      const r = await api("/api/choose", { id });
      S.answering = false;
      S.wheelSel = null; // 收起展開的移動
      applyMain(r.main);
      window.scrollTo({ top: 0, behavior: "smooth" });
      // 決戰選項（加入、趕到、出招）伺服器會回一句 message；一般選項的話在江湖紀錄裡，不回
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      // 這一送剛好結算了回合時，回話是整段回合敘事（場景裡的戰況就是同一段）：提示只放得下幾秒，截短、指去場景
      if (text) toast(text.length > 40 ? `${text.slice(0, 40)}……（戰況見場景）` : text);
    });
    if (document.querySelector(".options .btn.busy")) renderPage(); // 失敗了：把按鈕還原
  }

  // 隨口應對：送出後要等模型評這個做法，首次常要好幾秒，按鈕先寫「思量中……」
  async function answer(form, text) {
    await busy(async () => {
      form.querySelectorAll("input, button").forEach((el) => { el.disabled = true; });
      form.querySelector("[type=submit]").textContent = "思量中……";
      try {
        const r = await api("/api/answer", { text });
        S.answering = false;
        applyMain(r.main);
        window.scrollTo({ top: 0, behavior: "smooth" });
      } finally {
        form.querySelectorAll("input, button").forEach((el) => { el.disabled = false; });
        form.querySelector("[type=submit]").textContent = "說出口";
      }
    });
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

  async function doMain(op, body = {}) {
    await busy(async () => {
      const r = await api(`/api/do/${op}`, body);
      applyMain(r.main);
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      if (text) toast(text);
    });
  }

  // 放素材、換種類與輪詢都會問成本說明，回應可能晚到：只用最後一次請求的回應，而且爐子要還是問的那一爐
  let craftLineSeq = 0;
  async function updateCraftLine() {
    const seq = ++craftLineSeq;
    const pot = JSON.stringify(S.craftSel);
    try {
      const r = await api("/api/craft_line", { materials: S.craftSel });
      if (seq !== craftLineSeq || pot !== JSON.stringify(S.craftSel)) return;
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
      // 等結果的這段時間（首次發現的配方要等模型取名）整座爐子晃動、火舌竄高、太極快轉
      document.querySelector(".furnace .w-furnace")?.classList.add("forging");
      document.querySelector(".furnace .w-taichi")?.classList.add("hot");
      S.message = "爐火正旺。若這個配方是江湖上第一次煉成，取名要花上一分鐘，請稍候。";
      document.getElementById("mx-msg").textContent = S.message;
      const r = await api("/api/menxia/craft", { materials: S.craftSel });
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
  // 輿圖上選地點不走 click：pointer capture 之後 click 的目標會變，選取只在 gripUp 判斷「點了一下」時做
  // 行動列點下去的水墨漣漪：記下位置，重畫之後（例如展開移動）畫在新的那一顆上
  function inkRipple(key, x, y) {
    const cell = document.querySelector(`.act-ink[data-key="${key}"]`);
    if (!cell) return;
    const r = cell.getBoundingClientRect();
    const drop = document.createElement("span");
    drop.className = "ink-drop";
    drop.style.left = `${x - r.left}px`;
    drop.style.top = `${y - r.top}px`;
    cell.appendChild(drop);
    setTimeout(() => drop.remove(), 650);
  }

  document.addEventListener("click", async (ev) => {
    const el = ev.target.closest("[data-act]");
    if (!el) return;
    const act = el.dataset.act;
    if (el.classList.contains("act-ink")) {
      const [key, x, y] = [el.dataset.key, ev.clientX, ev.clientY];
      if (act === "wheel") requestAnimationFrame(() => inkRipple(key, x, y)); // 展開移動會重畫整頁
      else inkRipple(key, x, y);
    }
    try {
      switch (act) {
        case "gate": S.gateMode = el.dataset.mode; renderGate(); break;
        case "tab": await goTab(el.dataset.tab); break;
        case "choose": await choose(el, el.dataset.id); break;
        case "move-mode": await setMoveMode(el.dataset.mode); break;
        case "toggle-more": toggleMore(); break;
        case "now-more": {
          // 原地展開／收起，不重畫整頁（重畫會讓「剛剛」再播一次浮現動畫）
          const box = el.closest(".now");
          const open = !box.classList.contains("open");
          S.nowOpen = open ? S.main.now : null;
          box.classList.toggle("open", open);
          box.classList.toggle("clamp", !open);
          el.textContent = nowMore(open);
          el.setAttribute("aria-expanded", String(open));
          break;
        }
        case "sheet":
          S.sheet = true;
          render();
          if (S.main.admin) { S.admin = await api("/api/admin"); render(); } // 每次打開都重抓：時刻表與可以定的結果會變
          break;
        case "sheet-close": S.sheet = false; render(); break;
        case "guide-shut": setGuideShut(S.main.guide && S.main.guide.text); renderPage(); break;
        case "guide-open": setGuideShut(null); renderPage(); break;
        case "guide-more": S.guideFull = S.guideFull === (S.main.guide && S.main.guide.text) ? null : S.main.guide && S.main.guide.text; renderPage(); break;
        case "guide-ack": await doMain("guide_ack"); break;
        case "do": S.sheet = false; await doMain(el.dataset.op); break;
        case "admin": {
          const op = el.dataset.op;
          const body = { hours: Number(el.dataset.hours || 1) };
          if (op === "start_battle") body.id = document.getElementById("ad-battle").value;
          if (op === "fire") body.id = document.getElementById("ad-fire").value;
          if (op === "push_trend") { body.id = document.getElementById("ad-trend").value; body.amount = Number(document.getElementById("ad-amount").value || 0); }
          if (op === "schedule") {
            const input = document.getElementById(`tt-at-${el.dataset.id}`);
            if (!input || !input.value) { toast("先選一個時間。"); break; }
            body.id = el.dataset.id;
            body.at = new Date(input.value).getTime() / 1000;
            body.title = (S.admin.timetable.find((r) => r.id === body.id) || {}).label || body.id;
            body.when = input.value.replace("T", " ");
          }
          if (op === "set_trend") { body.id = document.getElementById("ad-front").value; body.value = Number(document.getElementById("ad-value").value || 0); }
          if (op === "resolve_event") { const [id, key] = document.getElementById("ad-result").value.split("|"); body.id = id; body.key = key; }
          if (op === "clear_lock") body.id = document.getElementById("ad-lock").value;
          const [text, yes] = adminAsk(op, body);
          ask(text, yes, () => adminDo(op, body)); // 先問一次（G3），按了確定才送
          break;
        }
        case "ask-yes": {
          // 上一個動作（例如等模型回話的對話）還沒回來：送了也會被 busy() 丟掉，所以先講一聲、確認框留著再按一次
          if (S.busy) { toast("正在處理上一個動作，請稍候再按一次。"); break; }
          const go = askGo;
          closeAsk();
          if (go) await go();
          break;
        }
        case "ask-no": closeAsk(); break;
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
        case "unslot": if (S.busy) break; S.craftSel.splice(Number(el.dataset.i), 1); renderPage(); updateCraftLine(); break;
        case "forge": await forge(); break;
        case "forge-hub":
          if (S.craftSel.length === (S.menxia?.per_craft || 2)) await forge();
          else toast("先挑兩樣素材放進爐裡。");
          break;
        case "wheel":
          S.wheelSel = S.wheelSel === el.dataset.key ? null : el.dataset.key;
          renderPage();
          if (S.wheelSel) revealMoveCard(); // 收起（再點一次）不捲
          break;
        case "layer": S.layer = el.dataset.layer; await loadMap(S.map?.selected); break;
        case "map-zoom": mapZoom(el.dataset.step); break;
        case "map-home": mapHome(); break;
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
    if (ev.target.id === "place") {
      const id = ev.target.value;
      S.mapNotice = "";
      await loadMap(id).then(() => { if (S.tab === "map") mapCenterOn(id); }, () => {});
    }
    if (ev.target.id === "anon") await doMain("anonymous", { value: ev.target.checked });
  });

  // 輿圖的手勢：按下在地圖框上（gripDown），移動、放開在這裡收
  document.addEventListener("pointermove", (ev) => {
    if (!grip.pts.has(ev.pointerId)) return;
    grip.pts.set(ev.pointerId, [ev.clientX, ev.clientY]);
    const t = grip.tap;
    if (t && Math.hypot(ev.clientX - t.x, ev.clientY - t.y) > TAP_SLOP) {
      grip.tap = null; // 超過 8px 就是拖移，放開時不選地點
      document.getElementById("map")?.classList.add("moving"); // 拖的時候才升成合成層
    }
    if (!grip.frame) grip.frame = requestAnimationFrame(gripStep);
  }, true);
  document.addEventListener("pointerup", gripUp, true);
  document.addEventListener("pointercancel", gripUp, true);
  window.addEventListener("blur", gripEnd); // 拖到一半切走視窗：放開可能收不到，手勢作廢

  // 狀態列點名號展開／收起更多數值（S1）。鍵盤也按得到（Enter、空白鍵）；狀態列整塊重畫，所以按完把焦點放回去
  function toggleMore(keyboard = false) {
    S.showMore = !S.showMore;
    renderTop();
    if (keyboard) document.querySelector(".who")?.focus();
  }
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && askGo) { closeAsk(); return; } // 管理者確認框：Esc 等於取消
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
      } else if (form.id === "answer-form") {
        if (!data.text.trim()) return;
        await answer(form, data.text.trim());
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
        // 重設密碼也先問一次（G3）。結果照舊寫在表單那一行、抽屜不關（失敗時欄位留著改，跟改密碼一樣）
        const target = (data.target || "").trim();
        if (!target) { formMsg(form, "先填要重設的帳號或名號。"); return; }
        ask(`重設 ${target} 的密碼，確定？`, "確定重設", async () => {
          // 結果寫進「那時候」畫面上的表單：問的期間抽屜可能被重畫過（例如前一個動作剛回來），按下時抓到的那個已經不在了；
          // 抽屜整個關了就改用提示泡泡講
          const say = (text, ok = false) => {
            const now = document.getElementById("reset-form");
            if (now) formMsg(now, text, ok);
            else if (text) toast(text);
            return now;
          };
          say("");
          try {
            const r = await api("/api/admin/reset_password", data);
            const ok = /^已重設 .+ 的密碼。$/.test(r.message || "");
            const now = say(r.message, ok);
            if (ok && now) now.reset();
          } catch (e) {
            say(failText(e));
          }
        });
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
    if (tab === "jianghu") {
      if (pageKey(old) !== pageKey(S.main)) renderPage(); // 只有狀態列變了（時鐘在走）：上面 renderTop 已經畫過
      return;
    }
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
      // 手指（滑鼠）還按在地圖上：重畫會換掉手指底下的地圖、pointer capture 跟著斷，這一輪不畫。
      // 清掉 mainKey，下一輪的 main 就算沒變也會再來補畫
      if (mapHeld()) { S.mainKey = ""; return; }
      const q = new URLSearchParams({ layer: S.layer });
      if (was.selected) q.set("place", was.selected);
      const m = await api(`/api/map?${q}`);
      if (S.stage !== "game" || S.tab !== tab || S.busy || S.map !== was || typing()) return;
      if (mapHeld()) { S.mainKey = ""; return; } // 等回應時開始了手勢
      S.map = m;
      S.layer = m.layer;
      if (JSON.stringify(m) !== JSON.stringify(was)) redrawPage(true);
    }
  }

  // 修練、煉製兩頁各自畫了 menxia 的哪幾欄（照 pagePractice／pageCraft）：輪詢只在這幾欄變了才重畫。
  // 不比整份，是因為本人卡上的氣血一直在回，整份 menxia 幾乎每分鐘都不一樣，煉製頁根本沒畫那張卡
  const MENXIA_SHOWN = {
    practice: ["rules", "slot_cards", "arts", "player_card", "roster", "person", "person_card", "on_team"],
    craft: ["materials", "clue_items", "per_craft", "bag", "craft_line", "xinde"],
  };

  // 重畫這一頁但保留玩家正在做的事（輪詢、閉關被拒時用）：填到一半的欄位（自創功法的名字、閉關時數）、
  // 摺疊區的開合（輿圖的視圖本來就存在 S.mapView，重畫照舊套用）。
  // quiet：輪詢的重畫，頁面上方那一行訊息沒有變，不要再播一次浮現動畫
  function redrawPage(quiet = false) {
    const page = document.getElementById("page");
    if (!page) return;
    const fields = [...page.querySelectorAll("form[id] input[name], form[id] select[name], form[id] textarea[name]")]
      .map((el) => [el.form.id, el.name, el.value]);
    const folds = [...page.querySelectorAll("details > summary")].map((s) => [s.textContent, s.parentElement.open]);
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

  // 公告卡的展開與否（FB-039）：toggle 不冒泡，用捕獲階段接。記的是週次：換週之後新畫的卡週次對不上，自然收起；
  // 重畫（輪詢、換分頁回來）時照 S.boardOpen 補回 open，那一下補出來的 toggle 記下的還是同一週，不會繞圈
  document.addEventListener("toggle", (ev) => {
    const box = ev.target;
    if (box instanceof Element && box.matches("details.bulletin")) S.boardOpen = box.open ? Number(box.dataset.week) : null;
    if (box instanceof Element && box.matches("details.orders")) S.ordersShut = box.open ? null : Number(box.dataset.week);
  }, true);

  // 視窗大小變了（轉向、拉視窗）：輿圖開著就重新夾住、套用；原本是整張就維持整張（applyMapView）
  window.addEventListener("resize", () => { if (S.stage === "game" && S.tab === "map") applyMapView(); });
  // 寬度跨過手機分界（轉向、拉視窗）：江湖頁的排列順序不同（pageJianghu 的輪盤），要重畫
  const onPhoneChange = () => { if (S.stage === "game" && S.tab === "jianghu") renderPage(); };
  if (PHONE) { if (PHONE.addEventListener) PHONE.addEventListener("change", onPhoneChange); else PHONE.addListener(onPhoneChange); }

  api("/api/me").then(enter).catch(() => { S.stage = "gate"; render(); });
})();
