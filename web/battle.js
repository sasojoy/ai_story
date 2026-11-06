/* 天下大勢的網頁前端：全服決戰的戰場面板（Joy 2026-11-06「大決戰優化：要更讓玩家投入在決戰中」，設計稿 JsNAYuqgMn3JJoTENCKza6 方案甲）。
 *
 * 伺服器給 main.battle_panel（tianxia/features/battle/panel.py）：一個倒數、兩邊上陣人物的血條、自己這一方的主將令、自己的陣中氣血、
 * 一回合一行的戰報、關鍵時刻（開打、主將重創、敗走）。這裡畫四樣：
 *   1. 江湖頁最上面那一塊面板（bpPanelHtml；main.js 的 pageJianghu 排在最前面，出招鈕緊接在面板底下）
 *   2. 場景卡裡跟面板重複的字拿掉（bpTrim：回合數與倒數、陣前那一行、主將令、「你上一回合」、最新一回合也收成一行）——同一件事一頁只寫一次
 *   3. 別的分頁上，分頁列上方一條戰場小條（bpMiniHtml；app.js 的 tabsHtml）
 *   4. 關鍵時刻蓋上來的那一層（bpAfter；app.js 的 afterPage 每次畫完頁面叫）：每件事只演一次（記在這台瀏覽器），好幾件沒演過只演最新的那一件；
 *      收場那一下照「剛剛」那張戰鬥卡片的戰局條（main.card_gauge）演
 * 狀態列的氣血在決戰裡換成陣中氣血（bpHpBar；app.js 的 topHtml）。倒數每秒自己跳（bpTick），歸零時集結那一段補抓一次畫面。
 * 字都待 joy 潤。
 */
"use strict";

  const BP_FACE = (fid) => `/static/img/figures/full/${encodeURIComponent(fid)}.webp`;
  const BP_BG = { muster: "/static/img/events/camp.webp", active: "/static/img/events/night.webp" };
  const BP_WORDS = { // 待 joy 潤
    muster: "開打", active: "這回合結算", settling: "結算中…", opening: "開打…", paused: "暫停中",
    mine: "我方", sent: "你這一回合", wait: (n) => (n > 0 ? `等還沒出招的 ${n} 人，到點就結算` : "大家都出完了，馬上結算"),
    out: "你的陣中氣血見底，倒下了，只能在一旁觀戰。", feed: "戰報", all: "完整戰報 ↓", merit: "本場戰功",
    hp: "陣中氣血", go: "去出招", noMove: "你還沒出招", moved: "已出招", tap: "點一下繼續",
    order: (o) => `${o.name}傳令：<b>${esc(o.move)}</b>　照令出招份量多 ${o.pct | 0}%`,
    hurt: (b) => `${b.name}　重創`, hurtSub: (b) => `氣血只剩 ${b.pct | 0}%`,
    fall: (b) => `${b.name}　敗走`, fallBy: (b) => (b.by ? `陣前擊退：${b.by}` : ""),
    open: (p) => `${p.name}　開打`, end: "收場", rank: (me) => `你的戰功 ${me.merit}・${me.rank <= 3 ? "名列前茅" : `排第 ${me.rank}／${me.of}`}`,
  };
  const bpOn = (m) => !!(m && m.battle_panel);
  const bpClock = (sec) => `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;
  const bpLeft = () => (S.bpDueAt == null ? null : Math.max(0, Math.ceil((S.bpDueAt - Date.now()) / 1000)));
  const bpPct = (a, b) => (b > 0 ? Math.max(0, Math.min(100, Math.round((100 * a) / b))) : 0);

  // 倒數那一格：數字、底下一條還剩幾成；最後 30 秒變紅（回合中），歸零寫「結算中…」／「開打…」
  function bpClockHtml(p) {
    const left = bpLeft() ?? p.due;
    const word = p.paused ? BP_WORDS.paused : left > 0 ? BP_WORDS[p.phase] || "" : p.phase === "muster" ? BP_WORDS.opening : BP_WORDS.settling;
    const hot = p.phase === "active" && left <= 30 && !p.paused;
    return `<div class="bp-clock${hot ? " hot" : ""}" role="timer" aria-live="off"><b class="bp-n">${left > 0 ? bpClock(left) : "—"}</b>`
      + `<small class="bp-w">${word}</small><i class="bp-ring"><i style="width:${bpPct(left, p.span)}%"></i></i></div>`;
  }
  function bpFace(c, cls = "") {
    return `<span class="bp-face${cls}"><img src="${BP_FACE(c.fid)}" alt="" loading="lazy" onerror="this.remove()"><em aria-hidden="true">${esc((c.name || "").slice(0, 1))}</em></span>`;
  }
  function bpChief(c) {
    const pct = bpPct(c.hp, c.cap);
    return `<div class="bp-gen${c.rank === "主將" ? " main" : ""}${c.fallen ? " down" : ""}${!c.fallen && pct <= 30 ? " low" : ""}">${bpFace(c)}`
      + `<div class="bp-gi"><p class="bp-gn">${esc(c.name)}<small>${esc(c.rank)}</small></p>`
      + `<i class="bp-hp" aria-label="${esc(`${c.name}氣血 ${c.hp}/${c.cap}`)}"><i style="width:${c.fallen ? 0 : pct}%"></i></i>`
      + `<small class="bp-hpn">${c.fallen ? "敗走" : `${c.hp}／${c.cap}`}</small></div></div>`;
  }
  function bpSide(w, rows, key) {
    if (!rows.length) return `<div class="bp-side ${key}"><p class="bp-sname side-${esc(w.id)}">${esc(w.name)}${w.mine ? `・${BP_WORDS.mine}` : ""}</p></div>`;
    return `<div class="bp-side ${key}"><p class="bp-sname side-${esc(w.id)}">${esc(w.name)}${w.mine ? `・${BP_WORDS.mine}` : ""}</p>${rows.map(bpChief).join("")}</div>`;
  }
  // 出招鈕：選單上 battle:act: 那幾顆（同 main.js 的 BATTLE_MOVE_LABEL：「說法（強攻・16 分・主將令）」），一顆一格三格一排
  function bpMovesHtml(m) {
    const acts = (m.options || []).filter((o) => o.id.startsWith("battle:act:"));
    if (!acts.length) return "";
    return `<div class="bp-moves" role="group" aria-label="出招">${acts.map((o) => {
      const hit = BATTLE_MOVE_LABEL.exec(o.label);
      const [say, tail] = hit ? [hit[1], hit[2]] : [o.label, ""];
      const parts = tail.split("・");
      const order = parts.includes("主將令");
      const off = !o.enabled;
      return `<button class="bp-mv${order ? " ord" : ""}" data-act="${off && o.note ? "opt-why" : "choose"}" data-id="${esc(o.id)}"${off ? ` aria-disabled="true"${o.note ? ` data-why="${esc(o.note)}"` : " disabled"}` : ""}>`
        + `<b>${esc(parts[0] || say)}</b><small>${esc(say)}</small><small>${esc(parts.filter((x, i) => i > 0 && x !== "主將令").join("・"))}${order ? ' <em>主將令</em>' : ""}</small></button>`;
    }).join("")}</div>`;
  }
  // 選單上那幾顆出招鈕面板已經畫了：選單裡的拿掉（同一顆不畫兩次）
  const bpDropMoves = (menu) => menu.replace(/\s*<button class="btn[^"]*" data-act="(?:choose|opt-why)" data-id="battle:act:[^"]*"[\s\S]*?<\/button>/g, "");

  function bpFeedHtml(p, g) {
    if (!p.feed.length) return "";
    const tint = (lead) => (lead === "tie" ? "" : (lead === "left" ? g.left : g.right));
    return `<div class="bp-feed"><p class="bp-fh">${BP_WORDS.feed}<button class="linkish" data-act="bp-log">${BP_WORDS.all}</button></p>${p.feed.map((r) => {
      const w = tint(r.lead);
      return `<div class="bp-fr"><b class="bp-rn">第${r.n}</b><div class="bp-ft">${w ? `<span class="bp-chip side-${esc(w.id)}">${esc(w.name)}</span>` : ""}${esc(r.text)}`
        + (r.hits.length ? `<p class="bp-hit"><span class="bp-chip k">主將</span>${r.hits.map((h) => `<span class="bp-dmg ${h.side}">${esc(h.name)} -${h.hp | 0}</span>`).join("")}</p>` : "")
        + `${(r.falls || []).map((t) => `<p class="bp-hit fall"><span class="bp-chip k">敗走</span>${esc(t)}</p>`).join("")}`
        + `${r.mine ? `<p class="bp-mine">你：${esc(r.mine)}</p>` : ""}</div></div>`;
    }).join("")}</div>`;
  }
  // 江湖頁最上面那一塊（moves：選單上的出招鈕；free：放手一搏的輸入框，接在出招鈕底下）
  function bpPanelHtml(m, free = "") {
    const p = m.battle_panel, g = m.battle_gauge;
    if (!p) return "";
    const head = p.phase === "muster" ? `集結中・集結期間照常行動` : `第 ${p.round}／${p.total} 回合${p.act ? `・${esc(p.act)}` : ""}<br>${BP_WORDS.moved} ${p.sent}／${p.present} 人`;
    const order = p.order ? `<p class="bp-order">${BP_WORDS.order(p.order)}</p>` : "";
    const panel = `<section class="bp" style="--bp-bg:url('${BP_BG[p.phase] || BP_BG.active}')" aria-label="${esc(p.name)}">`
      + `<div class="bp-top"><div class="bp-t"><h3>${esc(p.name)}</h3><p>${head}</p></div>${bpClockHtml(p)}</div>`
      + (p.chiefs.left.length || p.chiefs.right.length ? `<div class="bp-gens">${bpSide(p.left, p.chiefs.left, "left")}${bpSide(p.right, p.chiefs.right, "right")}</div>` : "")
      + `${order}</section>`;
    const gauge = g && p.me ? `<div class="bp-gauge">${gaugeHtml({ ...g, merit: null })}</div>` : "";
    const me = p.me;
    let act = bpMovesHtml(m);
    if (!act && me && me.out) act = `<p class="bp-sent out">${BP_WORDS.out}</p>`;
    else if (!act && me && me.sent) act = `<p class="bp-sent"><b>${BP_WORDS.sent}：${esc(me.sent)}</b><small>${BP_WORDS.wait(p.present - p.sent)}</small></p>`;
    const merit = g && g.merit && p.phase === "active" ? meritHtml(g, (w) => `side-${esc(w.id)}${w.mine ? " mine" : ""}`) : "";
    const fold = merit ? `<details class="bp-merit"${S.bpMeritOpen ? " open" : ""}><summary>${BP_WORDS.merit}${g.merit.me ? `<span>你排第 ${g.merit.me.rank}／${g.merit.me.of} ▸</span>` : ""}</summary>${merit}</details>` : "";
    return `<div class="bp-wrap">${panel}${gauge}${act}${act && !act.includes("bp-sent") ? free : ""}${bpFeedHtml(p, g || p)}${fold}</div>`;
  }

  // 場景卡裡跟面板重複的字（engine 的 battle_scene_text 寫的；寫法變了 tests/web/test_battle_panel_web.py 會紅）
  function bpTrim(html, m) {
    const p = m.battle_panel;
    if (!p) return html;
    if (!m.siege) html = html.replace(`<p><strong>${esc(p.name)}</strong></p>\n`, "").replace(`<p><strong>${esc(p.name)}</strong></p>`, "");
    return html
      .replace(/（第\s*\d+\s*／\s*\d+\s*回合・[\s\S]*?結算）/, "") // 回合數、已送出幾人、最遲幾分幾秒後結算：面板最上面那一塊
      .replace(/<p>[^<]{1,12}：(?:主將|副將)[^<]*(?:<br\s*\/?>\n?[^<]{1,12}：(?:主將|副將)[^<]*)*<\/p>\n?/, "") // 集結時兩邊的陣容
      .replace(/<p>〔[^〕<]+〕(?:主將|副將)[\s\S]*?<\/p>\n?/, "") // 開打後陣前那一行（血量）
      .replace(/<p>[^<]{1,12}傳令：<strong>[\s\S]*?<\/p>\n?/, "") // 主將令
      .replace(/<br\s*\/?>\n?你上一回合：[^<]*/, "").replace(/<blockquote>\n?<p>你上一回合：[^<]*<\/p>\n?<\/blockquote>\n?/, ""); // 戰報那一行寫了
  }

  // 狀態列的氣血：在決戰裡（自己在場上）換成陣中氣血，金框（設計稿第二版）
  function bpHpBar() {
    const me = S.main && S.main.battle_panel && S.main.battle_panel.me;
    if (!me) return "";
    return `<div class="bar hp bp-hpbar" title="${BP_WORDS.hp}"><i style="width:${bpPct(me.hp, me.cap)}%"></i><span><em class="lbl">${BP_WORDS.hp} </em>${me.hp}/${me.cap}</span></div>`;
  }

  // 別的分頁：分頁列上方一條戰場小條（點了回江湖頁）
  function bpMiniHtml() {
    const p = S.main && S.main.battle_panel;
    if (!p || S.tab === "jianghu" || S.stage !== "game") return "";
    const need = p.me && !p.me.out && !p.me.sent && p.phase === "active" && (S.main.options || []).some((o) => o.id.startsWith("battle:act:"));
    const left = bpLeft() ?? p.due;
    return `<button class="bp-mini" data-act="tab" data-tab="jianghu"><span class="bp-mi" aria-hidden="true">⚔</span>`
      + `<span class="bp-mt"><b>${esc(p.name)}</b><small>${p.phase === "muster" ? "集結中" : `第 ${p.round} 回合・${need ? BP_WORDS.noMove : BP_WORDS.moved}`}</small></span>`
      + `<b class="bp-n">${left > 0 ? bpClock(left) : "—"}</b>${need ? `<span class="bp-go">${BP_WORDS.go}</span>` : ""}</button>`;
  }

  // 每秒：面板與小條的數字、那一條；集結歸零補抓一次（回合歸零由 app.js 的 tickDue 補抓）
  function bpTick() {
    const p = S.main && S.main.battle_panel;
    if (!p || S.bpDueAt == null || p.paused) return;
    const left = bpLeft();
    for (const el of document.querySelectorAll(".bp-n")) el.textContent = left > 0 ? bpClock(left) : "—";
    for (const el of document.querySelectorAll(".bp-ring > i")) el.style.width = `${bpPct(left, p.span)}%`;
    const clock = document.querySelector(".bp-clock");
    if (clock) {
      clock.classList.toggle("hot", p.phase === "active" && left <= 30);
      const w = clock.querySelector(".bp-w");
      if (w && left <= 0) w.textContent = p.phase === "muster" ? BP_WORDS.opening : BP_WORDS.settling;
    }
    if (!left && p.phase === "muster" && !S.bpPolled && typeof poll === "function") { S.bpPolled = true; poll(); }
  }
  setInterval(bpTick, 1000);

  // ── 關鍵時刻蓋上來的那一層 ──
  const bpSeenKey = (k) => `tx-bp:${k}`;
  function bpSeen(key) {
    try { const raw = localStorage.getItem(bpSeenKey(key)); return raw == null ? null : new Set(JSON.parse(raw)); } catch (e) { return null; }
  }
  function bpMark(key, ids) {
    try { localStorage.setItem(bpSeenKey(key), JSON.stringify([...ids])); } catch (e) { /* 存不了就只是下次再演一次 */ }
  }
  function bpOverlayHtml(b, p) {
    const say = (who, text) => (text ? `<p class="bp-say"><b>${esc(who)}</b>「${esc(text)}」</p>` : "");
    if (b.kind === "open") {
      const duo = `<div class="bp-duo">${b.fid ? `<img src="${BP_FACE(b.fid)}" alt="" onerror="this.remove()">` : ""}<span class="bp-vs">對</span>${b.foe ? `<img class="r" src="${BP_FACE(b.foe.fid)}" alt="" onerror="this.remove()">` : ""}</div>`;
      return `${duo}<p class="bp-big">${esc(p.name)}　開打</p>${say(b.name || "", b.say)}`;
    }
    if (b.kind === "hurt") {
      return `<div class="bp-solo shake"><img src="${BP_FACE(b.fid)}" alt="" onerror="this.remove()"><i class="bp-slash"></i></div>`
        + `<p class="bp-big">${esc(BP_WORDS.hurt(b))}</p><i class="bp-hpbig"><i style="width:${b.pct | 0}%"></i></i><p class="bp-sub">${esc(BP_WORDS.hurtSub(b))}</p>`;
    }
    if (b.kind === "fall") {
      return `<div class="bp-solo gray"><img src="${BP_FACE(b.fid)}" alt="" onerror="this.remove()"></div><p class="bp-big">${esc(BP_WORDS.fall(b))}</p>`
        + `${say(b.name, b.say)}<p class="bp-sub${b.mine ? " mine" : ""}">${esc(BP_WORDS.fallBy(b))}</p>`;
    }
    if (b.kind === "end") {
      const g = b.gauge, me = g.merit && g.merit.me;
      const won = g.lean > 50 ? g.left : g.lean < 50 ? g.right : null;
      return `<p class="bp-res${won && won.mine ? " win" : won ? " lose" : ""}">${esc(g.caption || BP_WORDS.end)}</p><p class="bp-big small">${esc(g.name)}</p>`
        + (me ? `<p class="bp-card">${esc(BP_WORDS.rank(me))}${me.parts && me.parts.length ? `<small>${esc(me.parts.join("、"))}</small>` : ""}</p>` : "");
    }
    return "";
  }
  function bpShow(b, p) {
    if (typeof document === "undefined" || document.getElementById("bp-ov")) return;
    const label = esc(b.kind === "end" ? BP_WORDS.end : b.name || p.name);
    document.body.insertAdjacentHTML("beforeend", `<div id="bp-ov" class="bp-ov ${b.kind}" role="dialog" aria-label="${label}">`
      + `<div class="bp-ov-in">${bpOverlayHtml(b, p)}</div><p class="bp-tap">${BP_WORDS.tap}</p></div>`);
    const el = document.getElementById("bp-ov");
    if (!el) return;
    const close = () => { el.classList.add("gone"); setTimeout(() => el.remove(), 250); };
    el.addEventListener("click", close);
    setTimeout(close, b.kind === "end" ? 6000 : 4200);
  }
  // 畫完頁面叫（app.js 的 afterPage）：沒演過的關鍵時刻演最新的那一件。這一場第一次看到時（剛登入、剛換裝置）不補演舊的，
  // 只有剛開打（第 1、2 回合）才演開打那一下
  function bpAfter() {
    const m = S.main;
    if (!m || S.stage !== "game" || document.getElementById("mvp-pop") || document.querySelector(".vn-layer")) return;
    const g = m.card_gauge;
    if (g && g.phase === "ended" && m.card_id != null) {
      const key = `end:${m.card_id}`;
      if (bpSeen(key) == null) { bpMark(key, ["end"]); bpShow({ kind: "end", gauge: g }, { name: g.name }); return; }
    }
    const p = m.battle_panel;
    if (!p || !p.beats.length) return;
    const seen = bpSeen(p.key);
    const ids = p.beats.map((b) => b.id);
    if (seen == null) {
      bpMark(p.key, ids);
      const open = p.beats.find((b) => b.kind === "open");
      if (open && p.phase === "active" && p.round <= 2) bpShow(open, p);
      return;
    }
    const fresh = p.beats.filter((b) => !seen.has(b.id));
    if (!fresh.length) return;
    bpMark(p.key, new Set([...seen, ...ids]));
    bpShow(fresh[fresh.length - 1], p);
  }
