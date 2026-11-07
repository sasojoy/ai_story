/* 天下大勢的網頁前端：託付的勸降那一句（全部拆包第 66 批從 app.js 切出來）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 */
"use strict";

  // 託付的勸降（減法季批 6，FB-829）：送出後要等模型評這一句（同隨口應對），按鈕先寫「斟酌中……」；
  // 被擋下來的那一句（字數不對、人不在那裡）在江湖紀錄裡沒有，用提示泡泡講，輸入框留著；送成了（勸成、打起來、對方不置可否）收起
  const PERSUADE_WAIT = "斟酌中……"; // 待 joy 潤
  async function persuadeSay(form, text) {
    await busy(async () => {
      form.querySelectorAll("input, button").forEach((el) => { el.disabled = true; });
      const submitBtn = form.querySelector("[type=submit]");
      submitBtn.textContent = PERSUADE_WAIT;
      const stop = watchQueue(submitBtn, PERSUADE_WAIT);
      try {
        const r = await api("/api/do/persuade_text", { id: form.dataset.id, text });
        const said = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
        const done = said.startsWith("你：") || !((r.main && r.main.options) || []).some((o) => o.id === S.persuading);
        if (done) S.persuading = false;
        applyMain(r.main);
        if (said && !done) toast(said);
        if (done) window.scrollTo({ top: 0, behavior: "smooth" });
      } finally {
        stop();
        form.querySelectorAll("input, button").forEach((el) => { el.disabled = false; });
        submitBtn.textContent = PERSUADE_GO;
      }
    });
  }

  // 託付的勸降（減法季批 6，主機側計畫 1.3）：此地的「勸降」按了不送 /api/choose，就地換成二十字的輸入框（S.persuading 記那一顆的 id），
  // 送 POST /api/do/persuade_text {id: 那一件託付, text}（persuadeSay）
  const PERSUADE_PREFIX = "errand:persuade:";
  const PERSUADE_HINT = "怎麼勸他？（20字內）"; // 待 joy 潤：輸入框的提示
  const PERSUADE_GO = "勸他"; // 待 joy 潤：送出鈕
  function persuadeForm(o) {
    return `<form class="free answer persuade" id="persuade-form" data-id="${esc(o.id.slice(PERSUADE_PREFIX.length))}"><input class="input" name="text" maxlength="20" placeholder="${esc(PERSUADE_HINT)}" aria-label="${esc(o.label)}"><button class="btn primary small" type="submit">${esc(PERSUADE_GO)}</button></form>`;
  }
  const persuadingNow = (o) => S.persuading === o.id && o.enabled;

  // 書信（大勢人物擴充第二批）：「剛剛」上面一張小卡，收著只露一行（誰來信、開頭幾個字），點了攤開全文與委託；
  // 「收起」記成看過了（委託照樣在身上，懸賞卡上看得到），求援的「婉拒」讓委託作罷。字都是伺服器寫好的（letters.view）
  const ERRAND_STATE = { open: "託付", done: "辦成了", lapsed: "作罷了", declined: "婉拒了", failed: "沒談成" }; // errands.card 的 status
  function letterHtml(x) {
    if (!x) return "";
    const open = S.letterOpen === x.id || (!!x.open && S.letterShut !== x.id); // 開局的託付一到就攤開（letters.view 的 open），收攏過才收著

    const t = x.task;
    const task = t ? `<div class="letter-task"><div class="order-head"><b>${esc(t.title)}</b><span>${esc(t.state || "委託")}</span></div>
        <div class="order-how">${esc(t.how)}</div><div class="order-meta">${esc(t.reward)}</div><div class="order-meta">${esc(t.due)}</div></div>` : "";
    // 人物每週託的那一件（減法季批 6，letter.errand：同 main.errands 的一筆）：做什麼、到哪裡、期限，還在辦（open）時一樣能婉拒（letters.decline）
    const e = x.errand;
    const errand = e ? `<div class="letter-task"><div class="order-head"><b>${esc(e.text)}</b><span>${esc(ERRAND_STATE[e.status] || "託付")}</span></div>
        ${e.target && e.target.name ? `<div class="order-how">到${esc(e.target.name)}${e.target.minutes ? `（步行約 ${e.target.minutes} 分鐘）` : e.target.minutes === 0 ? "（就在這裡）" : ""}</div>` : ""}<div class="order-meta">期限 ${esc(e.deadline)}</div></div>` : "";
    const decline = (t && t.live) || (e && e.status === "open") ? `<button class="btn small ghost" data-act="letter-decline" data-id="${x.id}">婉拒</button>` : "";
    return `<section class="card letter${open ? " open" : ""}" data-letter="${x.id}">
      <button class="letter-head" data-act="letter-open" data-id="${x.id}" aria-expanded="${open}"><span class="letter-k">${esc(x.kind)}</span><b>${esc(x.sender)}來信</b>${open ? "" : `<span class="letter-peek">${esc(x.text)}</span>`}<span class="letter-arrow" aria-hidden="true">${open ? "▴" : "›"}</span></button>
      ${open ? `<div class="letter-body"><p>${esc(x.text)}</p><p class="letter-sign">${esc(x.sender)}</p>${task}${errand}<div class="row">${decline}<button class="btn small" data-act="letter-read" data-id="${x.id}">收起</button></div></div>` : ""}
    </section>`;
  }

  // ── 點人物之後（設計稿 Talk-Pick）：浮在最上層，立繪在左下、右邊三顆大鈕（交談／護衛／往來紀錄），底下宣紙框寫他是誰 ──
  const FIG_TALK = "交談", FIG_LOG = "往來紀錄"; // 待 joy 潤
  function figOf(id) { return ((S.main && S.main.figures_here) || []).find((f) => f.id === id); }
  function figPickHtml(m) {
    const f = figOf(S.fig);
    if (!f) { S.fig = null; return ""; }
    const byId = Object.fromEntries(m.options.map((o) => [o.id, o]));
    const acts = f.aid.map((id) => byId[id]).filter(Boolean).map((o) => {
      let [label, detail] = optParts(o); // eslint-disable-line prefer-const
      const name = label.replace(/^(護衛|犒軍|挑戰).*$/, "$1").replace(/・.*$/, "");
      detail = detail.split("）（").pop(); // 「聲威 60/60・20 兩）（聲威已滿」只留最後那一句
      return `<button class="vn-act${o.id.startsWith("act:challenge:") ? " red" : o.id.startsWith("aid:guard:") ? " red" : ""}" ${o.enabled ? `data-act="fig-act" data-id="${esc(o.id)}"` : `data-act="opt-why" data-why="${esc(detail ? `${detail}。` : "")}" aria-disabled="true"`}${o.enabled ? "" : ' data-off="1"'}><b>${esc(name)}</b><small>${esc(detail)}</small></button>`;
    }).join("");
    const talk = f.talk.via
      ? `<button class="vn-act dark" data-act="fig-talk" data-id="${esc(f.id)}"><b>${FIG_TALK}</b><small>情誼 ${f.affinity}</small></button>`
      : `<button class="vn-act dark" data-act="opt-why" data-why="${esc(`${f.talk.why || ""}。`)}" aria-disabled="true" data-off="1"><b>${FIG_TALK}</b><small>${esc(f.talk.why || "")}</small></button>`;
    return `<div class="vn-layer pick" role="dialog" aria-label="${esc(f.name)}">${vnBack(m)}${f.face ? `<img class="vn-fig" src="${esc(f.face)}" alt="">` : ""}
      <button class="vn-x" data-act="fig-close" aria-label="關閉">×</button>
      <div class="vn-acts">${talk}${acts}<button class="vn-act paper" data-act="fig-log" data-id="${esc(f.id)}"><b>${FIG_LOG}</b></button></div>
      ${vnBox(f.name, f.side, `${figIntroHtml(f.intro, f.side)}<p class="vn-say muted">${f.talk.via ? "他看了你一眼，等你開口。" : esc(f.talk.why || "")}</p>`)}</div>`; // 待 joy 潤：他看了你一眼，等你開口。
  }
  // 人物簡介（Joy 11/6「不是所有玩家都那麼了解三國裡面的角色」；server.figure_intro）：身分、是誰、本性；性子隨互動變了（設計稿「人物性子會變」，
  // 另一串做）時多「如今」一格與變化紀錄，沒變之前不畫這兩格
  const INTRO_NATURE = "本性", INTRO_NOW = "如今"; // 待 joy 潤
  // 每樣只寫一次（PM 11/6）：陣營看名牌旁的籤，身分那一行去掉開頭同一個陣營；情誼在「交談」鈕底下，框底不再寫
  function figIntroHtml(i, side = "") {
    if (!i) return "";
    const role = side && i.role ? i.role.replace(new RegExp(`^${side}・`), "") : i.role;
    const row = (cls, k, v) => `<p class="${cls}"><b>${k}</b><span>${esc(v)}</span></p>`;
    const hist = (i.history || []).length ? `<ul class="vi-hist">${i.history.map((h) => `<li>${esc(h)}</li>`).join("")}</ul>` : "";
    return `<div class="vn-intro">${role ? `<p class="vi-role">${esc(role)}</p>` : ""}${i.who ? `<p class="vi-who">${esc(i.who)}</p>` : ""}${i.nature
      ? row("vi-nature", INTRO_NATURE, i.nature) : ""}${i.now ? row("vi-now", INTRO_NOW, i.now) : ""}${hist}</div>`;
  }
  // 對話底下那一塊：場景照片暗下來（最後一次站在地點時的那張圖，S.lastPlaceArt），沒有就是墨色
  function vnBack(m) {
    if (m.art && m.art.kind === "place") S.lastPlaceArt = m.art.src;
    return `<div class="vn-bg"${S.lastPlaceArt ? ` style="background-image:url('${esc(S.lastPlaceArt)}')"` : ""}></div>`;
  }
  function vnBox(name, side, body, foot) {
    return `<div class="vn-box"><div class="vn-plate"><svg viewBox="0 0 140 40" aria-hidden="true"><path d="M3 22 C20 8 70 6 110 9 C124 10 134 13 138 18 C132 28 112 33 84 33 C56 34 22 36 6 31 C2 29 1 25 3 22 Z"/></svg><b>${esc(name)}</b></span>${side ? `<i>${esc(side)}</i>` : ""}</div>
      <div class="vn-paper">${body}${foot ? `<div class="vn-foot">${foot}</div>` : ""}</div></div>`;
  }
  // ── 人物對話（設計稿 Talk，Joy 11/5「講話的頁面是浮在最上面…有點像是文字向的戀愛遊戲對話」）：正在跟大勢人物說話（m.talk）時整頁換成這一層。
  // 選項照舊是同一串（menu：talk:N、自己說、告辭、開口求他做事），排在右上；他說的話（場景）在宣紙框裡，這一輪的得失（情誼 +N）疊在框頂
  function vnTalkHtml(m, menu) {
    const t = m.talk;
    // 場景的第一段是「**名字**（情誼 N）」：名字在名牌上、情誼在框底，不寫第二次
    const scene = (sceneUnderArt(m).scene || "").replace(new RegExp(`^<p><strong>${t.name}</strong>[^<]*</p>\\s*`), "");
    const [, chips] = m.now ? splitChips(m.now) : ["", ""];
    // 「告辭」拿出選項那一串、釘在右上角（Joy 2026-11-07「句子長被卡到沒辦法按告辭離開而卡在這個頁面」）：他的話一長，宣紙框蓋住選項的下半截，
    // 排在最後的告辭被壓在框底下按不到。選項那一串的底邊也停在宣紙框的上面（style.css .vn-menu），自己捲
    const leaveRe = /<button\b[^>]*data-id="talk:leave"[^>]*>[\s\S]*?<\/button>/;
    const leave = (String(menu).match(leaveRe) || [""])[0];
    return `<div class="vn-layer talk" role="dialog" aria-label="與${esc(t.name)}說話">${vnBack(m)}${t.face ? `<img class="vn-fig" src="${esc(t.face)}" alt="">` : ""}
      ${leave ? `<div class="vn-leave">${leave}</div>` : ""}<div class="vn-menu">${leave ? String(menu).replace(leaveRe, "") : menu}</div>
      ${vnBox(t.name, t.side, `${chips ? `<div class="vn-chips">${chips}</div>` : ""}<div class="vn-say">${scene}</div>`, `情誼 ${t.affinity}`)}</div>`;
  }

  // ── 往來紀錄（設計稿 Talk-Log）：你跟這位人物說過的話，照日子分段；這一季／上一季。資料在伺服器旁邊的小檔（/api/talk_log）──
  async function openFigLog(id, season = "now") {
    await busy(async () => {
      const r = await api(`/api/talk_log?id=${encodeURIComponent(id)}&season=${season}`);
      S.figLog = { ...r, season };
      renderPage();
    });
  }
  async function moreFigLog() {
    const L = S.figLog;
    if (!L || !L.more || !L.lines.length) return;
    await busy(async () => {
      const r = await api(`/api/talk_log?id=${encodeURIComponent(L.id)}&season=${L.season}&before=${L.lines[L.lines.length - 1].id}`);
      S.figLog = { ...L, lines: L.lines.concat(r.lines), more: r.more };
      renderPage();
    });
  }
  function figLogHtml() {
    const L = S.figLog;
    const face = L.face ? `<span class="pc-face big"><img src="${esc(L.face)}" alt=""></span>` : `<span class="pc-face big pc-ch">${esc((L.name || "").slice(0, 1))}</span>`;
    // 一天一段、新的那天在上面；同一天裡照說話的先後（伺服器給的是新的在前，這裡每段倒回來）
    const groups = [];
    for (const x of L.lines || []) {
      const head = `${x.stamp.replace(/\s\d\d:\d\d$/, "")}・${x.place}`;
      if (!groups.length || groups[groups.length - 1].head !== head) groups.push({ head, lines: [] });
      groups[groups.length - 1].lines.unshift(x);
    }
    const rows = groups.map((g) => `<div class="tl-day"><span></span>${esc(g.head)}<span></span></div>${g.lines.map((x) => {
      const gain = x.gain ? `<div class="tl-gain${x.gain < 0 ? " down" : ""}">情誼 ${x.gain > 0 ? "+" : ""}${x.gain}</div>` : "";
      return `<div class="tl-line ${x.role === "user" ? "me" : "them"}"><div class="tl-bubble">${esc(x.text)}</div></div>${gain}`;
    }).join("")}`);
    return `<div class="vn-layer log" role="dialog" aria-label="與${esc(L.name)}的往來"><div class="tl-sheet">
      <div class="tl-head">${face}<div class="tl-title"><b>與${esc(L.name)}的往來</b><small>見過 ${L.meets | 0} 次・情誼 ${L.affinity | 0}</small></div><button class="btn small ghost" data-act="fig-log-close">返回</button></div>
      <div class="tl-tabs"><button class="${L.season === "now" ? "on" : ""}" data-act="fig-log-season" data-s="now">這一季</button><button class="${L.season === "prev" ? "on" : ""}" data-act="fig-log-season" data-s="prev">上一季</button></div>
      <div class="tl-list">${rows.length ? rows.join("") : `<p class="muted tl-empty">${L.season === "prev" ? "上一季沒有跟他說過話。" : "這一季還沒跟他說過話。"}</p>`}
      ${L.more ? '<button class="linkish tl-more" data-act="fig-log-more">更早的 ▾</button>' : ""}</div></div></div>`; // 待 joy 潤：兩句空的
  }
  // 交談：照伺服器寫的順序按（一類一顆的交友直接開口是一下；名單是「交友」再「指名」兩下），一路不停，最後一下等人物回話

  async function figTalk(id) {
    const f = figOf(id);
    if (!f || !f.talk.via) return;
    S.fig = null;
    const via = f.talk.via.slice();
    const last = via.pop();
    for (const step of via) {
      let ok = false;
      await busy(async () => { const r = await api("/api/choose", { id: step }); applyMain(r.main); ok = true; });
      if (!ok || !(S.main.options || []).some((o) => o.id === last)) { renderPage(); return; }
    }
    renderPage();
    await choose(document.querySelector(`[data-id="${CSS.escape(last)}"]`) || document.body, last);
  }
