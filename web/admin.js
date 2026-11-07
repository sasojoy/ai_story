/* 天下大勢的網頁前端：管理頁（/admin）。說明見 app.js 檔頭。
 *
 * Joy 2026-11-01「把管理員工具獨立一個網址，現在擠在一起有夠難用」：以前收在設定抽屜最底下的管理者工具搬到自己一頁，照用途分成幾塊、
 * 每一塊可以摺起來（手機上一次只攤開要用的那一塊）；頂上一張「現在」卡寫此刻的季、時鐘、決戰、模型佇列，做完一件事留在這一頁、
 * 結果寫在畫面底下那一條（以前是關掉抽屜、回江湖頁看一個三秒就消失的泡泡）。設定抽屜只留一顆「管理者工具 ›」連過來。
 * 網址是 /admin 才畫這一頁（S.adminPage）；不是管理者的人打開，照常回到江湖、網址換回 /（資料在 /api/admin* 那幾條，那邊才擋人）。
 * 跟 main.js、mall.js 一樣是一般的 <script>：頂層的名字同在一個全域裡，index.html 排在 app.js 前面；點擊、表單、change 用 registerClicks、registerForms、registerChanges 登記在這支檔。
 */
"use strict";

  const ADMIN_PATH = /^\/admin\/?$/;
  const onAdminPath = () => typeof location !== "undefined" && !!location && ADMIN_PATH.test(location.pathname || "");

  // 管理頁的幾塊（照用途）：id、標題。沒東西的那一塊不畫（領地爭奪、玉璽、商城、形象、名帖照開關與有沒有資料）
  const AD_SECS = {
    season: "賽季與時鐘", battle: "決戰與時刻表", trend: "大勢與事件", conquest: "領地爭奪", seal: "玉璽",
    player: "玩家與帳號", mall: "商城", looks: "形象與招式訂單", mingtie: "名帖檢舉", mail: "書信檢舉",
  };


  // 整頁：頂上一列（回江湖、標題、重新整理）、「現在」卡、各塊、底下的結果條
  function renderAdmin() {
    if (typeof hideMapHost === "function") hideMapHost();
    $app.innerHTML = `<div class="ad-shell">${adminHtml()}</div>`;
    if (!S.admin && !S.adLoading) adminReload();
  }

  async function adminReload(said = false) {
    S.adLoading = true;
    try {
      S.admin = await api("/api/admin");
      S.adFailed = false;
      if (said) { // 「重新整理」：連江湖那一份一起重抓（暫停幾分鐘、狀態寫在那一份）
        const m = await api("/api/main");
        if (m && m.status) setMain(m);
      }
      if (S.adPlayerName) S.adPlayer = await api("/api/admin/player", { name: S.adPlayerName });
    } catch (e) {
      S.adFailed = !S.admin;
    } finally {
      S.adLoading = false;
    }
    renderKeepingSheet();
    if (said && !S.adFailed) toast("已重新整理。");
  }

  function adminHtml() {
    const a = S.admin;
    const head = `<header class="ad-head"><a class="btn small ghost" href="/">‹ 回江湖</a><h2>管理者工具</h2><button class="btn small" data-act="ad-refresh">重新整理</button></header>`;
    if (!a) return `${head}<p class="muted ad-wait">${S.adFailed ? "管理資料沒拿到（連不上、或伺服器出錯）。按「重新整理」再試一次。" : "正在讀……"}</p>`;
    // 介面重整（2026-11-05，設計稿 Admin）：四格狀態、常用的大鈕、分頁籤（一次只看一塊）、紅框的危險區（長按才算）
    const tabs = Object.keys(AD_SECS).filter((id) => adSecBody(a, id)); // 每一塊都畫（下拉選單、欄位都在，大鈕也找得到），只露選到的那一塊
    const tab = tabs.includes(S.adTab) ? S.adTab : tabs[0];
    return `${head}
      ${adTilesHtml(a)}
      ${adBigHtml(a)}
      <div class="ad-tabs" role="tablist">${tabs.map((id) => `<button role="tab" class="${id === tab ? "on" : ""}" aria-selected="${id === tab}" data-act="ad-tab" data-tab="${id}">${AD_SECS[id]}</button>`).join("")}</div>
      ${tabs.map((id) => `<section class="card ad-body stack" data-sec="${id}"${id === tab ? "" : " hidden"}>${adSecBody(a, id)}</section>`).join("")}
      ${adDangerHtml(a)}
      <p class="muted ad-hint">一般的鈕按了先問一次才送出；紅框裡的要長按一秒。做完留在這一頁，結果寫在畫面最底下那一條。</p>
      ${adResultHtml()}`;
  }

  function adSecBody(a, id) {
    return {
      season: adSeasonHtml(a, true), battle: adBattleHtml(a), trend: adTrendHtml(a),
      conquest: a.conquest ? conquestAdminHtml(a.conquest) : "", seal: a.seal ? sealAdminHtml(a.seal) : "", player: adPlayerSecHtml(a),
      mall: S.main.mall ? mallAdminHtml() : "", looks: S.main.mall && S.main.looks_admin ? looksAdminHtml() : "",
      mingtie: a.mingtie && a.mingtie.length ? mingtieAdminHtml(a.mingtie) : "",
      mail: a.mail && a.mail.length && typeof mailAdminHtml === "function" ? mailAdminHtml(a.mail) : "", // 帖友書信（web/mail.js）
    }[id] || "";
  }
  // 四格：季、決戰、在線、模型佇列
  function adTilesHtml(a) {
    const now = a.now || {}, fight = now.battle, q = a.llm_queue;
    const tile = (k, v, sub, hot) => `<div class="ad-tile${hot ? " hot" : ""}"><small>${k}</small><b>${v}</b><span>${sub}</span></div>`;
    return `<div class="ad-tiles">
      ${tile("季", now.season ? `第 ${now.season | 0} 季` : "本季", esc([now.phase_text, S.main.paused != null ? `暫停 ${S.main.paused} 分` : ""].filter(Boolean).join("・")), S.main.paused != null)}
      ${tile("決戰", fight ? esc(fight.phase) : "無", fight ? `${esc(fight.name)}・${fight.people | 0} 人` : "沒有在打的", !!fight)}
      ${tile("在線", `${now.online | 0} 人`, "10 分鐘內", false)}
      ${tile("模型", q ? `${q.running | 0}／${q.waiting | 0}` : "—", q ? "處理中／在排" : "佇列關著", q && q.waiting > 0)}
    </div>${now.when ? `<p class="muted ad-when">${esc(now.when)}</p>` : ""}
    ${S.main.paused != null ? `<p class="ad-alert">賽季時鐘暫停中（已 ${S.main.paused} 分鐘）：全服不能行動，記得按「繼續」。</p>` : ""}
    ${a.divine_out ? `<p class="muted">${esc(a.divine_out)}</p>` : ""}`;
  }
  // 常用的大鈕：快轉一小時、立刻開戰（去決戰那一頁挑）、推大勢（去大勢那一頁）、發軍令、天下形勢、跳到下一件
  function adBigHtml(a) {
    const go = (tab, name, sub) => `<button class="ad-big" data-act="ad-tab" data-tab="${tab}"><b>${name}</b><small>${sub}</small></button>`;
    const op = (o, name, sub, extra = "") => `<button class="ad-big" data-act="admin" data-op="${o}"${extra}><b>${name}</b><small>${sub}</small></button>`;
    return `<div class="ad-bigs">
      ${op("fast_forward", "快轉 1 小時", "全服一起", ' data-hours="1"')}
      ${go("battle", "立刻開戰", "挑一場")}
      ${go("trend", "推大勢", "挑一條")}
      ${a.season_one ? op("issue_orders", "發軍令", "立刻重發") : ""}
      ${a.timetable && a.timetable.length ? op("jump_next", "跳下一件", "時刻表") : ""}
      ${a.xingshi ? op("xingshi_now", "天下形勢", "現在開一篇") : ""}
    </div>`;
  }
  // 危險區：暫停／繼續時鐘、立刻收季、開下一季（長按一秒才送，data-act="ad-hold"；照階段灰掉不對的）
  function adDangerHtml(a) {
    const off = (want) => (a.phase && a.phase !== want ? " disabled" : "");
    const hold = (o, name, extra = "") => `<button class="ad-hold" data-act="ad-hold" data-op="${o}"${extra}><i></i><b>${name}</b><small>長按一秒</small></button>`;
    return `<section class="ad-danger" aria-label="危險區"><div class="ad-danger-hd">危險區</div><div class="ad-holds">
      ${S.main.paused != null ? hold("resume_clock", "▶ 繼續時鐘") : hold("pause_clock", "⏸ 暫停時鐘")}
      ${hold("end_season", "立刻收季", off("running"))}
      ${hold("next_season", "開下一季", off("resting"))}
    </div></section>`;
  }


  // 最近一件做完的事：釘在畫面底下，按「知道了」或做下一件才換掉。被拒的（括號開頭）紅字
  function adResultHtml() {
    const r = S.adResult;
    if (!r) return "";
    return `<div class="ad-result${r.ok ? " ok" : " bad"}" role="status"><p>${r.title ? `<span class="ad-result-title">${esc(r.title)}${r.ok ? "" : "・沒做成"}</span>` : ""}${esc(r.text)}</p><button class="btn small ghost" data-act="ad-result-close">知道了</button></div>`;
  }

  const adOpts = (list) => (list || []).map((x) => `<option value="${esc(x.id)}">${esc(x.label)}</option>`).join("");
  // 大勢線的選單：名字後面寫此刻的值（定戰況、推大勢之前先知道現在是多少）
  const adTrendNow = (id) => { const t = ((S.admin && S.admin.now && S.admin.now.trends) || []).find((x) => x.id === id); return t ? t.value : null; };
  const adTrendOpts = (list) => (list || []).map((x) => { const v = adTrendNow(x.id); return `<option value="${esc(x.id)}">${esc(x.label)}${v == null ? "" : `（${v}）`}</option>`; }).join("");

  function adSeasonHtml(a, tabbed = false) {
    // 開季、立刻收季、開啟下一季照賽季的階段（a.phase）灰掉不對的那幾顆（手機介面自檢 U-19）；舊伺服器沒給照舊都能按
    // 分頁籤的版面（tabbed）：收季、開下一季、暫停時鐘在底下的危險區，這裡只留開季
    const seasonOff = (want) => (a.phase && a.phase !== want ? " disabled" : "");
    return `
      <p class="muted">賽季（只有對的階段按得下去：籌備中開季${tabbed ? "；收季、開下一季在底下的危險區" : "、進行中收季、休季開下一季"}）</p>
      <div class="row wrap seasons"><button class="btn" data-act="admin" data-op="open_season"${seasonOff("preparing")}>開季</button>${tabbed ? "" : `<button class="btn warn" data-act="admin" data-op="end_season"${seasonOff("running")}>⚠ 立刻收季</button><button class="btn warn" data-act="admin" data-op="next_season"${seasonOff("resting")}>⚠ 開啟下一季</button>`}</div>
      ${tabbed ? "" : `<p class="muted">賽季時鐘（停機維護前按「暫停」，開回來按「繼續」；暫停中全服不能行動，畫面照常可看）</p>
      <div class="row">${S.main.paused != null
        ? `<span class="muted">已暫停 ${S.main.paused} 分鐘</span><button class="btn" data-act="admin" data-op="resume_clock">▶ 繼續</button>`
        : `<button class="btn warn" data-act="admin" data-op="pause_clock">⏸ 暫停賽季時鐘</button>`}</div>`}
      <p class="muted">時間快轉（全服一起快轉，只在測試時用；小時是現實小時，季曆會跳得更多）</p>
      <div class="row">${[1, 8, 24].map((h) => `<button class="btn small" data-act="admin" data-op="fast_forward" data-hours="${h}">+${h} 小時</button>`).join("")}</div>
      ${a.season_one ? `
        <p class="muted">${wk7() ? ADMIN_DAILY_WEEK7 : ordersDaily() ? ADMIN_DAILY_SEASON21 : "每週的事（照週一的做法立刻再做一次；下週一照常）"}</p>
        <div class="row wrap"><button class="btn small" data-act="admin" data-op="issue_orders">立刻發${wkWord("order_this", "本週")}軍令</button><button class="btn small" data-act="admin" data-op="rotate_seats">立刻輪替第 4 階席次</button></div>` : ""}
      ${a.xingshi ? `
        <p class="muted">天下形勢（每天 22:00 自動開一篇；測試時立刻照上一篇以來的事開一篇）</p>
        <div class="row wrap"><button class="btn small" data-act="admin" data-op="xingshi_now">現在就開一篇天下形勢</button></div>` : ""}`;
  }

  function adBattleHtml(a) {
    const fight = a.now && a.now.battle;
    return `
      <p class="muted">立刻開戰（人少、大勢推不到門檻時用；效果跟自然發生一樣）</p>
      ${a.battles.length
        ? `<div class="row ad-row"><span class="ad-tag">決戰</span><select class="input" id="ad-battle" aria-label="決戰">${adOpts(a.battles)}</select><button class="btn small" data-act="admin" data-op="start_battle"${fight ? " disabled" : ""}>立刻開戰</button></div>
          ${fight ? '<p class="muted ad-note">已經有一場在打，打完或取消了才能開下一場。</p>' : ""}`
        : '<p class="muted ad-note">這一季沒有能直接開的決戰。</p>'}
      ${a.showdowns && a.showdowns.length ? `
        <p class="muted">三場大戲（照時刻表開集結；開過就算這一場開過了，排定的時間到了不會再開）</p>
        ${a.showdowns.map((s) => `<div class="row ad-row"><span class="ad-tag">${esc(s.label)}</span>${s.note ? `<span class="muted ad-note">${esc(s.note)}</span>` : ""}<button class="btn small" data-act="admin" data-op="start_showdown" data-id="${esc(s.id)}"${s.enabled ? "" : " disabled"}>立刻開這一場</button></div>`).join("")}` : ""}
      ${a.timetable.length ? timetableHtml(a) : ""}
      <p class="muted">救場</p>
      ${a.results.length ? `<div class="row ad-row"><span class="ad-tag">結果</span><select class="input" id="ad-result" aria-label="定結果">${a.results.map((x) => `<option value="${esc(x.value)}">${esc(x.label)}</option>`).join("")}</select><button class="btn small" data-act="admin" data-op="resolve_event">定結果</button></div>` : ""}
      ${a.locks.length ? `<div class="row ad-row"><span class="ad-tag">鎖定</span><select class="input" id="ad-lock" aria-label="清鎖定">${adOpts(a.locks)}</select><button class="btn small" data-act="admin" data-op="clear_lock">清鎖定</button></div>` : ""}
      <div class="row ad-row"><span class="ad-tag">取消</span><span class="muted ad-note">${fight ? `正在打：${esc(fight.name)}（${esc(fight.phase)}）` : "沒有在打的決戰"}</span><button class="btn warn small" data-act="admin" data-op="cancel_battle"${fight || !a.now ? "" : " disabled"}>⚠ 取消決戰</button></div>`;
  }

  function adTrendHtml(a) {
    const rows = (a.now && a.now.trends) || [];
    const first = a.trends.length ? adTrendNow(a.trends[0].id) : null;
    return `
      ${rows.length ? `<p class="muted">各條大勢此刻（0～100）</p><div class="ad-trends">${rows.map((t) => `<div class="ad-trend"><span>${esc(t.label)}</span><b>${t.value | 0}</b><i style="width:${Math.max(0, Math.min(100, t.value | 0))}%"></i></div>`).join("")}</div>` : ""}
      <p class="muted">推動（往上推寫正數、往回推寫負數；推過門檻照常觸發）</p>
      <div class="row ad-row"><span class="ad-tag">大勢</span><select class="input" id="ad-trend" aria-label="大勢">${adTrendOpts(a.trends)}</select><input class="input" id="ad-amount" type="number" value="10" step="1" aria-label="推動量" style="max-width:76px"><button class="btn small" data-act="admin" data-op="push_trend">推動</button></div>
      <p class="muted">定戰況（直接定成一個數，0～100；欄位先填好現在的值）</p>
      <div class="row ad-row"><span class="ad-tag">戰況</span><select class="input" id="ad-front" aria-label="定戰況的線">${adTrendOpts(a.trends)}</select><input class="input" id="ad-value" type="number" value="${first == null ? 50 : first}" min="0" max="100" aria-label="戰況" style="max-width:76px"><button class="btn small" data-act="admin" data-op="set_trend">定戰況</button></div>
      <p class="muted">觸發事件（效果跟自然發生一樣，全服都受影響；已經發生過的會被拒絕）</p>
      ${a.events.length
        ? `<div class="row ad-row"><span class="ad-tag">事件</span><select class="input" id="ad-fire" aria-label="事件">${adOpts(a.events)}</select><button class="btn small" data-act="admin" data-op="fire">觸發</button></div>`
        : '<p class="muted ad-note">沒有能觸發的事件。</p>'}
      ${a.fallen && a.fallen.length ? `<p class="muted">叫回人物（這一季退場、重創的大勢人物）</p>
        <div class="row ad-row"><span class="ad-tag">人物</span><select class="input" id="ad-fallen" aria-label="叫回人物">${adOpts(a.fallen)}</select><button class="btn small" data-act="admin" data-op="revive_figure">叫他回來</button></div>` : ""}`;
  }

  // 玩家與帳號：個人劇情（第一季規則才有）、重設密碼（打幾個字「找」帳號，點一筆填進去；臨時密碼可以「產生」一組）
  function adPlayerSecHtml(a) {
    const found = S.adAccounts;
    return `${a.season_one ? `
      <p class="muted">玩家個人劇情（填名號查一次，再挑要給他的；效果跟自然發生一樣）</p>
      <form id="ad-player-form"><div class="row"><input class="input" name="name" placeholder="名號" aria-label="玩家名號" value="${esc(S.adPlayerName || "")}"><button class="btn small" type="submit">查</button></div><p class="form-msg" role="alert">${esc((S.adPlayer && S.adPlayer.refusal) || "")}</p></form>
      ${S.adPlayer && !S.adPlayer.refusal ? adminPlayerHtml(S.adPlayer) : ""}` : ""}
      <p class="muted">重設密碼（朋友忘記密碼時用：打帳號或名號的幾個字按「找」、點一筆；臨時密碼私下告訴他，他登入後到設定改掉）</p>
      <form id="reset-form" class="stack">
        <div class="row"><input class="input" name="target" id="ad-reset-target" placeholder="帳號或名號" aria-label="帳號或名號" autocomplete="off" value="${esc(S.adResetTarget || "")}"><button class="btn small" type="button" data-act="ad-find">找</button></div>
        ${found ? (found.length
          ? `<div class="row wrap ad-found">${found.map((x) => `<button class="btn small ghost" type="button" data-act="ad-pick" data-login="${esc(x.login)}">${esc(x.login)}${x.character ? `・${esc(x.character)}` : "・還沒建角色"}</button>`).join("")}</div>`
          : '<p class="muted ad-note">找不到含這幾個字的帳號或名號。</p>') : ""}
        <div class="row"><input class="input" name="temp" id="ad-reset-temp" placeholder="臨時密碼（至少 ${AD_PW_MIN} 字）" aria-label="臨時密碼" autocomplete="off"><button class="btn small" type="button" data-act="ad-gen">產生一組</button></div>
        <p class="form-msg" role="alert"></p>
        <div class="row"><button class="btn" type="submit">重設密碼</button></div>
      </form>`;
  }
  const AD_PW_MIN = 6; // 同 tianxia/accounts.py 的 PASSWORD_MIN

  async function adminFind() {
    const input = document.getElementById("ad-reset-target");
    const q = String((input && input.value) || "").trim();
    S.adResetTarget = q;
    if (!q) { S.adAccounts = null; renderKeepingSheet(); toast("先打幾個字。"); return; }
    const r = await api("/api/admin/accounts", { q });
    S.adAccounts = (r && r.rows) || [];
    renderKeepingSheet();
  }
  function adminPick(login) {
    S.adResetTarget = login;
    S.adAccounts = null;
    renderKeepingSheet();
    document.getElementById("ad-reset-temp")?.focus();
  }
  // 臨時密碼：8 個字，不用容易看錯的 0／o、1／l
  function adminGenTemp() {
    const chars = "abcdefghijkmnpqrstuvwxyz23456789";
    const pick = new Uint32Array(8);
    if (typeof crypto !== "undefined" && crypto.getRandomValues) crypto.getRandomValues(pick);
    else for (let i = 0; i < pick.length; i++) pick[i] = Math.floor(Math.random() * 4294967296);
    const temp = Array.from(pick, (n) => chars[n % chars.length]).join("");
    const input = document.getElementById("ad-reset-temp");
    if (input) input.value = temp;
  }

  // 管理者「每週的事」那一行在 7 天濃縮季的寫法（軍令每天、第 4 階席次每段；FB-501，待 joy 潤）
  const ADMIN_DAILY_WEEK7 = "每天、每段的事（照 00:00 的做法立刻再做一次；之後照常）";
  // 21 天季：軍令每天、第 4 階席次照舊每週一（FB-502，待 joy 潤）
  const ADMIN_DAILY_SEASON21 = "每天、每週的事（軍令照 00:00、席次照週一的做法立刻再做一次；之後照常）";
  // 管理者區「玩家個人劇情」查到的那個人（/api/admin/player，Game.admin_player_choices）：他是誰、召見（發不了的灰掉、寫為什麼）、
  // 能給他的機緣與伏筆片段（沒有就寫一句）。按了照舊先問一次，送的是查到的那個名號（不是欄位裡後來改過的字）
  // 管理者「玉璽」一組（玉璽碎片設計第十二節，admin_choices.seal；碎片關著是 null，不畫）：七片與狀態、強制現世與璽動（下一場）、
  // 指定持有者、強制開單挑（正式伺服器只能掛在剛收場的時刻表決戰上，QA 開關開著才不必）、定結果、取消、隱沒判斷。按了照舊先問一次。字待 joy 潤
  const SEAL_STATES = { held: "懷中", hidden: "未現世", sunk: "不知所蹤" };
  // 被檢舉的名帖（檢舉夠多次、大家都看不到的在前）：撤下＝畫與題字清掉、他再做一張；放回＝照舊給大家看。待 joy 潤
  function mingtieAdminHtml(rows) {
    return `<p class="muted">名帖檢舉</p><div class="mt-admin">${rows.map((x) => `<div class="mt-admin-row">${mtCardHtml(x.card, x.name, "thumb")}
      <div><b>${esc(x.name)}</b><p class="muted">第 ${x.version} 版・${x.count} 人檢舉</p>
      <div class="row wrap"><button class="btn warn small" data-act="admin" data-op="mingtie_remove" data-name="${esc(x.name)}" data-version="${x.version}">撤下</button><button class="btn small" data-act="admin" data-op="mingtie_restore" data-name="${esc(x.name)}" data-version="${x.version}">放回</button></div></div></div>`).join("")}</div>`;
  }

  // 管理者「領地爭奪」一組（打開領地爭奪，PM 2026-10-22；admin_choices.conquest，領地爭奪關著、季收了是 null，不畫）：一塊定給哪一軍或放回中立、
  // 定一軍在那一塊的進度（到 100 照推滿當場易手）、立刻替一軍下戰書、取消一場攻城。照 Game.admin_conquest_* 實際做的事；按了照舊先問一次。字待 joy 潤
  function conquestAdminHtml(q) {
    const opts = (list) => list.map((x) => `<option value="${esc(x.id)}">${esc(x.label)}</option>`).join("");
    return `<p class="muted">領地爭奪（救場；易手的天下大事照自然發生寫，不寫管理者）</p>
      <div class="row ad-row"><span class="ad-tag">區塊</span><select class="input" id="ad-cq-block" aria-label="區塊">${opts(q.blocks)}</select></div>
      <div class="row ad-row"><span class="ad-tag">陣營</span><select class="input" id="ad-cq-side" aria-label="陣營">${opts(q.sides)}</select><button class="btn small" data-act="admin" data-op="conquest_set">定歸這一邊</button><button class="btn small" data-act="admin" data-op="conquest_set" data-neutral="1">放回中立</button></div>
      <div class="row ad-row"><span class="ad-tag">進度</span><input class="input" id="ad-cq-value" type="number" value="60" min="0" max="100" aria-label="進度" style="max-width:76px"><button class="btn small" data-act="admin" data-op="conquest_progress">定進度</button><button class="btn small" data-act="admin" data-op="admin_conquest_letter">立刻下戰書</button></div>
      ${q.sieges.length ? `<div class="row ad-row"><span class="ad-tag">攻城</span><select class="input" id="ad-cq-siege" aria-label="攻城">${opts(q.sieges)}</select><button class="btn warn small" data-act="admin" data-op="conquest_cancel">⚠ 取消這一場</button></div>` : ""}`;
  }

  function sealAdminHtml(s) {
    const label = (x) => (x.state === "held" ? `${x.name}（${x.holder}懷中）` : `${x.name}（${SEAL_STATES[x.state] || x.state}）`);
    const canDuel = s.hung || s.qa;
    const off = s.duel ? "" : " disabled";
    return `<p class="muted">玉璽（效果跟自然發生一樣，公告不寫管理者）</p>
      <div class="row ad-row"><span class="ad-tag">碎片</span><select class="input" id="ad-seal" aria-label="碎片">${s.shards.map((x) => `<option value="${esc(x.id)}">${esc(label(x))}</option>`).join("")}</select></div>
      <div class="row wrap"><button class="btn small" data-act="admin" data-op="seal_emerge"${s.hide ? ' data-hide="1"' : ""}>${s.hide ? "現在藏一片" : "強制現世（下一場）"}</button><button class="btn small" data-act="admin" data-op="seal_stir">強制璽動（下一場）</button></div>
      <div class="row ad-row"><span class="ad-tag">名號</span><input class="input" id="ad-seal-name" placeholder="名號" aria-label="持有者名號"><select class="input" id="ad-seal-state" aria-label="狀態"><option value="held">有主</option><option value="hidden">未現世</option><option value="sunk">隱沒</option></select><button class="btn small" data-act="admin" data-op="seal_assign">指定持有者</button></div>
      <div class="row ad-row"><span class="ad-tag">單挑</span><input class="input" id="ad-seal-factor" type="number" value="1" step="0.1" min="0" max="1" aria-label="局勢係數" style="max-width:76px"><button class="btn small" data-act="admin" data-op="seal_duel"${canDuel ? "" : " disabled"}>強制開單挑</button>${
        !canDuel ? '<span class="muted ad-note">沒有剛收場的決戰可掛</span>' : s.hung ? `<span class="muted ad-note">掛在「${esc(s.where)}」</span>` : ""}</div>
      <div class="row wrap"><button class="btn small" data-act="admin" data-op="seal_fix" data-take="1"${off}>定結果：易主</button><button class="btn small" data-act="admin" data-op="seal_fix" data-take="0"${off}>定結果：不易主</button><button class="btn warn small" data-act="admin" data-op="seal_cancel"${off}>⚠ 取消單挑</button><button class="btn small" data-act="admin" data-op="seal_sink_check">隱沒判斷</button></div>
      ${s.mandate_ok ? `<div class="row wrap"><button class="btn small" data-act="admin" data-op="seal_mandate" data-when="next"${s.mandate ? " disabled" : ""}>蓋天命之季（下一季）</button><button class="btn warn small" data-act="admin" data-op="seal_mandate" data-when="now"${s.mandate === "now" ? " disabled" : ""}>⚠ 這一季立刻蓋章</button>${s.mandate === "next"
        ? '<button class="btn small" data-act="admin" data-op="seal_mandate" data-when="cancel">收回下一季的章</button>' : ""}${
        s.mandate === "now" ? '<span class="muted ad-note">這一季是天命之季</span>' : s.mandate === "next" ? '<span class="muted ad-note">下一季蓋章</span>' : ""}</div>` : ""}`;
  }

  function adminPlayerHtml(p) {
    const opts = (list) => list.map((x) => `<option value="${esc(x.id)}">${esc(x.label)}</option>`).join("");
    return `
      <p class="muted">${esc(p.line)}</p>
      <div class="row ad-row"><span class="ad-tag">召見</span><span class="muted ad-note">${esc(p.summons.note)}</span><button class="btn small" data-act="admin" data-op="summon"${p.summons.ok ? "" : " disabled"}>立刻替他發召見</button></div>
      <div class="row ad-row"><span class="ad-tag">機緣</span>${p.opportunities.length
        ? `<select class="input" id="ad-opp" aria-label="給他的機緣">${opts(p.opportunities)}</select><button class="btn small" data-act="admin" data-op="give_opportunity">給他</button>`
        : '<span class="muted ad-note">沒有能給他的機緣</span>'}</div>
      <div class="row ad-row"><span class="ad-tag">伏筆</span>${p.fragments.length
        ? `<select class="input" id="ad-frag" aria-label="給他的伏筆片段">${opts(p.fragments)}</select><button class="btn small" data-act="admin" data-op="give_fragment">給他</button>`
        : '<span class="muted ad-note">沒有能給他的伏筆片段</span>'}</div>`;
  }

  // 管理頁的「時刻表」（計畫 T10）：十二件照順序、標狀態；三場決戰與季末還沒結算的有日期時間欄位與「排定」
  // （欄位是這台裝置的當地時間，送出時換成秒數）；最後是「跳到下一件大事」
  function localInput(sec) {
    const d = new Date(sec * 1000);
    const p = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
  }
  function timetableHtml(a) {
    return `
      <p class="muted">時刻表（三場大戲與季末可以排時間，時間欄是現實時間；時間到了自動開集結，季末就是收季）</p>
      <div class="tt-list">${a.timetable.map((r) => `
        <div class="tt-row">
          <div class="tt-head"><span class="tt-name">${esc(r.label)}</span><span class="tt-state">${esc(r.result ? `${r.state_text}・${r.result}` : r.state_text)}</span></div>
          ${r.schedulable ? `<div class="tt-real">現實時間（這台裝置的當地時間）</div><div class="row"><input class="input" type="datetime-local" id="tt-at-${esc(r.id)}" value="${localInput(r.at_real)}" aria-label="${esc(r.label)}的時間"><button class="btn small" data-act="admin" data-op="schedule" data-id="${esc(r.id)}">排定</button></div>` : ""}
        </div>`).join("")}</div>
      <div class="row"><button class="btn" data-act="admin" data-op="jump_next">跳到下一件大事</button></div>`;
  }

  // 管理者動作的問句與確認鈕（照抽屜裡選好的下拉選單）
  function adminAsk(op, body) {
    const picked = (id) => { const el = document.getElementById(id); return el && el.selectedIndex >= 0 ? el.options[el.selectedIndex].text : ""; };
    const amount = `${body.amount >= 0 ? "+" : ""}${body.amount}`;
    // 大勢線的名字不帶「（現在 N）」（選單上多寫的那一段），問句另外寫現在多少、做完多少
    const trendName = (id) => picked(id).replace(/（-?\d+）$/, "");
    const was = (id) => adTrendNow(id);
    const fightName = (S.admin && S.admin.now && S.admin.now.battle && S.admin.now.battle.name) || "";
    // 21 天季的「繼續」（PM 2026-10-19，跟 world.RESUME_SKIP_REAL 一致）；待 joy 潤
    // 季長與對回什麼照季寫（S.admin.realign，同 world.realign_line；FB-501：7 天的季「對回現實的日子」），沒給照 21 天季那一句
    const R = (S.admin && S.admin.realign) || { days: "21", unit: "星期" };
    const RESUME_21 = `讓賽季時鐘繼續走：${R.days} 天的季的季曆對回現實的${R.unit}，暫停期間的大事在這一刻一起發生，季末照原本的日期；排好的決戰照原本的時間開，時間在暫停裡過了的馬上開始集結，確定？`;
    // 三場大戲與季末的預設時間：7 天濃縮季照時刻表寫（S.admin.default_dates，timetable.default_dates_note；FB-501），其他季照原本那一句
    const DATES = (S.admin && S.admin.default_dates) || "預設在第 6、9、11 週中、第 12 週末";
    const week7 = wk7(), daily = ordersDaily(); // 7 天濃縮季：第 4 階席次每段（FB-501）；21 天季、7 天季：軍令每天一道（FB-502）
    return {
      open_season: [`開季：賽季從籌備中正式開始，全服玩家都能行動了。記得排三場大戲與季末的時間（${DATES}），確定？`, "確定開季"],
      // 照 Game.admin_end_season 實際做的事寫（只在進行中有效）
      end_season: ["立刻收季：這一季馬上結束、算出結局與武學榜，全服進入休季（之後再按「開啟下一季」）；沒打完的決戰直接收掉、不算結果，確定？", "確定收季"],
      // 照 SqliteWorldStore.next_season 實際做的事寫（只在休季有效）
      next_season: [`開啟下一季（休季才有效）：新的一季立刻開始，同伴全部重獲自由、武學與意境的名字全部釋出（絕學定的名也是）、合成與合併的配方清空、鐵匠鋪的隱藏鑄法換一批、鑄譜與神器重來（神器譜留著）、天機 +1，沒打完的決戰清掉。${
        S.admin && S.admin.next_has_timetable ? `記得排三場大戲與季末的時間（${DATES}）。` : ""}確定？`, "確定開啟下一季"],  // FB-050
      fast_forward: [`時間快轉現實 ${body.hours} 小時的份（全服一起，季曆會跳得更多），確定？`, `快轉 ${body.hours} 小時`],
      // 公告停機時賽季時鐘暫停（Game.admin_pause_clock／admin_resume_clock）；問句待 S1／joy 潤
      // 21 天季（S.admin.season21）多一句、繼續換一句（PM 2026-10-19：季曆對回現實的星期，跟 world.RESUME_SKIP_REAL 一致）；待 joy 潤
      pause_clock: [`暫停賽季時鐘（停機維護前按）：季的時間不走、決戰不推，全服暫時不能行動，畫面照常可看；${
        S.admin && S.admin.season21 ? `${R.days} 天的季：繼續時季曆會對回現實的${R.unit}，暫停期間的大事在繼續那一刻一起發生。` : ""}做完記得按「繼續」，確定？`, "確定暫停"],
      resume_clock: [S.admin && S.admin.season21 ? RESUME_21 : "讓賽季時鐘繼續走：停的這一段照整個季曆鐘頭往下取整，扣掉的不算進賽季、季末往後延一樣長；停不到一個季曆鐘頭的話什麼都不扣、季末不動；排好的決戰照原本的時間開，時間在暫停裡過了的馬上開始集結，確定？", "確定繼續"],  // 待 joy 潤；跟 world.resume_skip_text 說的一致
      start_battle: [`立刻開戰「${picked("ad-battle")}」：全服一起進入集結，確定？`, "確定開戰"],
      fire: [`觸發「${picked("ad-fire")}」：效果跟自然發生一樣，全服都受影響，確定？`, "確定觸發"],
      push_trend: [`推動大勢「${trendName("ad-trend")}」${amount}${was(body.id) == null ? "" : `（現在 ${was(body.id)}，推完約 ${Math.max(0, Math.min(100, was(body.id) + body.amount))}）`}：全服一起，推過門檻照常觸發，確定？`, "確定推動"],
      // 時刻表與救場（計畫 T10）
      schedule: [`把「${body.title}」排在現實 ${body.when}：時間到了自動開集結（季末就是收季），確定？`, "確定排定"],
      jump_next: ["跳到下一件大事：全服的季時間一起往前推，到了的大事立刻結算（決戰直接開集結），確定？", "確定跳過去"],
      set_trend: [`把「${trendName("ad-front")}」${was(body.id) == null ? "" : `從 ${was(body.id)} `}定成 ${body.value}：全服一起，推過門檻照常觸發，確定？`, "確定定戰況"],
      resolve_event: [`定下「${picked("ad-result")}」：照時刻表結算、全服公告，之後不再擲骰，確定？`, "確定定結果"],
      clear_lock: [`清掉「${picked("ad-lock")}」的鎖定：結算時照沒人鎖定擲骰，確定？`, "確定清掉"],
      revive_figure: [`叫「${picked("ad-fallen")}」回來：以一半聲威回到原本的戰線，全服看得到一句天下大事，確定？`, "確定叫回"],
      cancel_battle: [`取消${fightName ? `「${fightName}」` : "正在集結或開打的決戰"}：不算勝負，參戰者都會收到通知；時刻表的決戰不會自己再開，要用「定結果」收尾，確定？`, "確定取消"],
      // 管理者觸發鈕（企劃者 2026-10-07）：照 Game.admin_issue_orders／admin_rotate_seats 實際做的事寫
      issue_orders: [daily // 軍令每天一道的季（21 天、7 天；FB-501、FB-502，待 joy 潤）
        ? "立刻發今日軍令：今天還沒達成的軍令照 00:00 的做法重挑、換掉（它們的進度不算了），各陣營發一則軍情；已經達成的照舊留著、不會再達成一次；明天 00:00 照常發令，確定？"
        : "立刻發本週軍令：這一週還沒達成的軍令照週一的做法重挑、換掉（它們的進度不算了），各陣營發一則軍情；已經達成的照舊留著、不會再達成一次；下週一照常發令，確定？", "確定重發"],
      rotate_seats: [week7 // 7 天濃縮季的席次每段輪替（FB-501，待 joy 潤）
        ? "立刻輪替第 4 階席次：照上一段的貢獻重排各陣營在任的人、發一則名單軍情；下一段第一天 00:00 照常再排，確定？"
        : "立刻輪替第 4 階席次：照上一週的貢獻重排各陣營在任的人、發一則名單軍情；下週一照常再排，確定？", "確定輪替"],
      // 照 Game.admin_xingshi_now 實際做的事寫（領地爭奪第三批 A；待 joy 潤）
      xingshi_now: ["現在就開一篇〈天下形勢〉：照上一篇以來的事開一張單，伺服器在背景請模型寫（寫不出來照固定段），收下那一刻發一則天下大事、記一筆江湖史；還在等的那一篇先照固定段收。每天 22:00 照常再開，確定？", "確定開一篇"],
      start_showdown: [`立刻開「${body.title}」：照時刻表開集結（起點照此刻的戰況），這一場算開過了，排定的時間到了不會再開，確定？`, "確定開戰"],
      // 領地爭奪救場（打開領地爭奪，PM 2026-10-22；照 Game.admin_conquest_set／progress／letter／cancel 實際做的事寫，待 joy 潤）
      conquest_set: body.side
        ? [`把「${body.place}」定給${body.sideName}：天下大事照易手寫一句（落入／收復）、記一筆江湖史，三條戰線當場重算；不分紅、不起冷卻，${body.sideName}在那裡的進度拿掉、別一邊的照留，確定？`, "確定定歸"]
        : [`把「${body.place}」放回中立（沒人佔）：不發天下大事，三條戰線當場重算，進度照留，確定？`, "確定放回中立"],
      conquest_progress: [`把「${body.place}」${body.sideName}那一條進度定成 ${body.value}：到 100 照推滿當場易手（這一輪推過的人分紅、冷卻起算、天下大事一句），定成 0 就拿掉那一條；不看推不推得動、不記是誰推的，確定？`, "確定定進度"],
      admin_conquest_letter: [`替${body.sideName}立刻對「${body.place}」下一張戰書：不看第 4 階、門檻與一天一張，集結馬上開、集結完就開打，那一塊凍結到打完或作罷；天下大事照戰書寫、不寫管理者，確定？`, "確定下戰書"],
      conquest_cancel: [`取消「${picked("ad-cq-siege")}」這一場攻城：照作罷處理，那一塊解凍、進度照留，天下大事一句（不寫管理者）；已經開了集結的照決戰的取消收兵（不算勝負、不發軍餉、不易手），確定？`, "確定取消"],
      summon: [`立刻替 ${body.name} 發召見（${(S.adPlayer && S.adPlayer.summons && S.adPlayer.summons.note) || "下一階"}；不看貢獻與機緣的門檻，其餘照自然發召見的做法），確定？`, "確定發召見"],
      // 情誼型多一句（伺服器算好的 note：情誼補到幾、招募成算、其他話題、換季帶幾成，審查 M-5）
      give_opportunity: [`給 ${body.name} 機緣「${picked("ad-opp")}」：放到這個機緣自然送上門之後的樣子，下一步他就做得了。${
        body.note ? `${body.note}。` : ""}確定？`, "確定給他"],
      give_fragment: [`給 ${body.name} 伏筆片段「${picked("ad-frag")}」：跟自然聽到一樣，記進他的個人線索，確定？`, "確定給他"],
      // 玉璽碎片（玉璽碎片設計第十二節；照 Game.admin_seal_* 實際做的事寫，待 joy 潤）
      seal_emerge: body.hide
        ? ["現在藏一片：略過開季的機率，把選的那一片（還沒現世才行，沒選的照亂數挑）藏進一塊開季中立的區塊；藏在哪裡不公開，要有人在那裡探索才撿得到。這一季已經藏著、或已經現世過一片就不藏，確定？", "確定藏"]
        : ["下一場標了現世的決戰，碎片必定現世（選的那一片還沒現世就是它，否則照亂數挑；得主照常從勝方抽），確定？", "確定"],
      seal_stir: [`下一場標了璽動的決戰，必定牽動「${picked("ad-seal")}」（略過機率、新主保護與次數上限；那一片要有主），確定？`, "確定"],
      seal_assign: [`把「${picked("ad-seal")}」改成${body.state === "held" ? `${body.name}懷中（這一季有新主保護）` : body.state === "sunk" ? "隱沒" : "未現世"}：只改登記，他回來同步時補給他，確定？`, "確定指定"],
      seal_duel: [`立刻對「${picked("ad-seal")}」開一場奪璽單挑，挑戰者 ${body.name}、局勢係數 ${body.factor}（上限照舊）：三分鐘後開打，確定？`, "確定開單挑"],
      seal_fix: [`正在打的奪璽單挑收場時${body.take ? "易主" : "懷璽不失"}（公告照常），確定？`, "確定"],
      seal_cancel: ["取消正在打（或下戰書中）的奪璽單挑：記成未分勝負，碎片留在原主，確定？", "確定取消"],
      mingtie_remove: [`撤下 ${body.name} 的第 ${body.version} 版名帖：畫與自題那一句清掉（頭銜照留），他的江湖紀錄會寫一句，收過這一張的人也看不到了，確定？`, "確定撤下"],
      mingtie_restore: [`放回 ${body.name} 的第 ${body.version} 版名帖：檢舉清掉、大家照舊看得到（檢舉過的人自己那裡照樣藏著），確定？`, "確定放回"],
      // 帖友書信的檢舉（web/mail.js 的 mailAdminHtml；待 joy 潤）
      mail_remove: ["撤下這一封信：寄的人與收的人都看不到了，確定？", "確定撤下"],
      mail_keep: ["這一封信看過沒事：檢舉清掉（檢舉的人那裡照樣收著），確定？", "確定"],
      mail_mute: body.days ? [`停 ${body.name} 寄信 ${body.days} 天：這段時間他寫不了信（收照收），確定？`, "確定停寄"] : [`解開 ${body.name} 的停寄，確定？`, "確定解開"],
      seal_sink_check: ["照隱沒的條件現在判一次：只列出下一次換季會沉哪幾片，不改，確定？", "確定"],
      // 蓋章的後果要寫明（審查 I2）：天命之季過後再換季，七片全部散去、每一位持有者都失去碎片
      seal_mandate: body.when === "cancel"
        ? ["收回下一季的天命之季章：七片這一輪都現世過的話，換季時照樣會蓋，確定？", "確定收回"]
        : [body.when === "now"
          // 天命之爭的時刻：7 天濃縮季照時刻表寫（S.admin.mandate_at，timetable.mandate_note；FB-503），其他季照原本那一句
          ? `這一季立刻蓋上天命之季的章：還沒打的標了璽動的決戰必定牽動碎片、不提前收季，天命之爭排在${(S.admin && S.admin.mandate_at) || "第 12 週週一 20:00"}（現實時間落在半夜會盡量挪開，前後的大事擋著挪不開就照原時間、蓋完會說；已經過了就馬上開集結）。這一季的章蓋了就收不回：收季之後再換季，七片全部散去、每一位持有者都失去碎片，確定？`
          : "下一季蓋天命之季的章（不看七片現世過沒）。那一季過後再換季，七片全部散去、每一位持有者都失去碎片；換季之前還收得回，確定？", "確定蓋章"],
    }[op] || ["確定要這麼做？", "確定"];
  }

  // 確認過的管理者動作：做完留在管理頁，重抓管理資料（時刻表、可以定的結果、此刻的值都會變；查過的玩家也重查），
  // 結果釘在畫面底下那一條（被拒的那一句都包在括號裡，紅字）。請求本身沒成（連不上、伺服器出錯）api() 已經提示過原因
  async function adminDo(op, body, title = "") {
    await busy(async () => {
      const r = await api(`/api/do/${op}`, body);
      if (r.main) setMain(r.main);
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      const ok = !text.startsWith("（");
      S.adResult = { title, text: text || "已完成。", ok };
      try {
        const fresh = await api("/api/admin");
        if (fresh && Array.isArray(fresh.trends)) S.admin = fresh; // 回來的不像一份管理資料（出錯、舊伺服器）：先照舊那一份
        if (S.adPlayerName) S.adPlayer = await api("/api/admin/player", { name: S.adPlayerName });
      } catch (e) { /* 沒抓到就先照舊那一份，按「重新整理」再抓 */ }
      // 推大勢、定戰況：結果後面補一句那一條此刻是多少（引擎回的是一句戰況的話，看不出數字）
      const v = ok && (op === "push_trend" || op === "set_trend") ? adTrendNow(body.id) : null;
      if (v != null) S.adResult.text += `（此刻 ${v}）`;
      renderKeepingSheet();
    });
  }

  // 危險區的長按（介面重整）：按住一秒、框裡的墨跑滿才送（不再另外問一次）；中途放開、滑出去就作罷。短按只說要長按
  const AD_HOLD_MS = 1000;
  let adHolding = null;
  function adHoldStop() {
    if (!adHolding) return;
    clearTimeout(adHolding.timer);
    adHolding.el.classList.remove("holding");
    adHolding = null;
  }
  if (typeof document !== "undefined" && document.addEventListener) {
    document.addEventListener("pointerdown", (ev) => {
      const el = ev && ev.target && ev.target.closest ? ev.target.closest(".ad-hold") : null;
      if (!el || el.disabled) return;
      adHoldStop();
      el.classList.add("holding");
      adHolding = { el, timer: setTimeout(() => {
        const op = el.dataset.op;
        adHolding.fired = true;
        adHoldStop();
        el.dataset.fired = "1";
        adminDo(op, { hours: 1 }, el.querySelector("b") ? el.querySelector("b").textContent : "");
      }, AD_HOLD_MS) };
    });
    ["pointerup", "pointercancel", "pointerleave"].forEach((type) => document.addEventListener(type, () => adHoldStop(), true));
  }
  function adHoldClick(el) {
    if (el.dataset.fired) { delete el.dataset.fired; return; } // 剛長按送出去的那一下放開也算一次點擊：不再提示
    toast("這一顆要長按一秒才算。"); // 待 joy 潤
  }
  function adTabPick(id) {
    S.adTab = id;
    if (id === "looks" && !S.adLooks && S.main && S.main.mall && S.main.looks_admin) looksAdminDo("load"); // 點開才抓訂單
    renderKeepingSheet();
  }
  async function adminClick(act, el, ev) {
    switch (act) {
        // 管理頁（admin.js；Joy 2026-11-01 管理者工具獨立一個網址）：設定抽屜頂上那顆「管理者工具 ›」是一般的連結（/admin），這幾顆是管理頁上的
        case "ad-refresh": await adminReload(true); break;
        case "ad-result-close": S.adResult = null; renderKeepingSheet(); break;
        case "ad-find": await adminFind(); break;
        case "ad-pick": adminPick(el.dataset.login); break;
        case "ad-gen": adminGenTemp(); break;
        case "ad-tab": adTabPick(el.dataset.tab); break; // 管理頁的分頁籤（介面重整）
        case "ad-hold": adHoldClick(el); break; // 危險區：短按只提示要長按（長按在 admin.js 的 pointerdown）
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
          if (op === "revive_figure") body.id = document.getElementById("ad-fallen").value;
          if (op === "start_showdown") {
            body.id = el.dataset.id;
            body.title = ((S.admin && S.admin.showdowns) || []).find((s) => s.id === body.id)?.label || body.id;
          }
          if (op.startsWith("seal_")) { // 玉璽一組：碎片、名號、狀態、局勢係數照欄位讀（假瀏覽器沒有這些欄位時是空的）
            const val = (id) => (document.getElementById(id) || {}).value || "";
            body.id = val("ad-seal");
            body.name = val("ad-seal-name").trim();
            body.state = val("ad-seal-state") || "held";
            body.factor = Number(val("ad-seal-factor") || 1);
            body.take = el.dataset.take === "1";
            body.when = el.dataset.when || ""; // 蓋天命之季：next／now（玉璽二）
            body.hide = el.dataset.hide === "1"; // 領地爭奪的季「強制現世」是「現在藏一片」（問句不同；送出去的欄位一樣）
          }
          if (op.startsWith("mail_")) { body.id = Number(el.dataset.id || 0); body.name = el.dataset.name || ""; body.days = Number(el.dataset.days || 0); }
          if (op.startsWith("mingtie_")) { body.name = el.dataset.name || ""; body.version = Number(el.dataset.version || 0); }
          if (op === "conquest_set" || op === "conquest_progress" || op === "admin_conquest_letter") { // 領地爭奪一組：區塊、陣營、進度照欄位讀
            const pick = (id) => document.getElementById(id) || {};
            const block = pick("ad-cq-block"), side = pick("ad-cq-side");
            body.id = block.value || "";
            // 問句寫地名：照伺服器給的 name（選單的字後面接了括號，地名自己也可能有括號，不從字切）
            body.place = ((((S.admin && S.admin.conquest) || {}).blocks || []).find((b) => b.id === body.id) || {}).name || body.id;
            body.side = op === "conquest_set" && el.dataset.neutral === "1" ? "" : side.value || "";
            body.sideName = (side.options && side.options[side.selectedIndex]) ? side.options[side.selectedIndex].text : body.side;
            if (op === "conquest_progress") body.value = Math.max(0, Math.min(100, Number(pick("ad-cq-value").value || 0)));
          }
          if (op === "conquest_cancel") body.id = (document.getElementById("ad-cq-siege") || {}).value || "";
          if (op === "summon" || op === "give_opportunity" || op === "give_fragment") {
            body.name = (S.adPlayer && S.adPlayer.name) || "";
            if (op === "give_opportunity") {
              body.id = document.getElementById("ad-opp").value;
              body.note = ((S.adPlayer && S.adPlayer.opportunities) || []).find((x) => x.id === body.id)?.note || "";
            }
            if (op === "give_fragment") body.id = document.getElementById("ad-frag").value;
          }
          const [text, yes] = adminAsk(op, body);
          ask(text, yes, () => adminDo(op, body, yes.replace(/^確定/, ""))); // 先問一次（G3），按了確定才送；結果條上寫做的是哪一件
          break;
        }
    } // adminClick
  } // adminClick
  registerClicks(adminClick, ["ad-refresh", "ad-result-close", "ad-find", "ad-pick", "ad-gen", "ad-tab", "ad-hold", "admin"]);
  async function adminForm(form, data) {
      if (form.id === "ad-player-form") {
        // 管理者查一個玩家（玩家個人劇情）：查到了畫他的召見、機緣、伏筆三列；查不到的原因寫在表單那一行。抽屜不關
        const name = (data.name || "").trim();
        S.adPlayerName = name;
        if (!name) { S.adPlayer = null; formMsg(form, "先填名號。"); return; }
        S.adPlayer = await api("/api/admin/player", { name });
        renderKeepingSheet(); // 查到的那個人就在表單底下：抽屜停在原地（審查 M-2）
      } else if (form.id === "reset-form") {
        // 重設密碼也先問一次（G3）。結果寫在表單那一行、也釘在管理頁底下（成了的那一條連臨時密碼一起寫，私下告訴他之前不必再找一次）；
        // 失敗時欄位留著改，跟改密碼一樣
        const target = (data.target || "").trim();
        const temp = String(data.temp || "");
        S.adResetTarget = target;
        if (!target) { formMsg(form, "先填要重設的帳號或名號。"); return; }
        if (temp.length < AD_PW_MIN) { formMsg(form, `臨時密碼至少 ${AD_PW_MIN} 個字（可以按「產生一組」）。`); return; }
        ask(`重設 ${target} 的密碼，臨時密碼是「${temp}」：他原本的密碼不能再用，確定？`, "確定重設", async () => {
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
            if (S.adminPage) {
              S.adResult = { text: ok ? `${r.message}臨時密碼：${temp}（私下告訴他，登入後到設定改掉）` : r.message, ok };
              if (ok) { S.adResetTarget = ""; S.adAccounts = null; }
              renderKeepingSheet();
            }
            const now = say(r.message, ok);
            if (ok && now) now.reset();
          } catch (e) {
            say(failText(e));
          }
        });
      } // adminForm
  } // adminForm
  registerForms(adminForm, ["ad-player-form", "reset-form"]);
  async function adminChange(ev) {
    if (ev.target.id === "ad-front") { // 管理頁定戰況：換了一條線，數字欄換成那一條此刻的值
      const v = adTrendNow(ev.target.value), box = document.getElementById("ad-value");
      if (box && v != null) box.value = v;
    }
  } // adminChange
  registerChanges(adminChange);
