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
      <div class="mt-name">${esc(name)}</div>${c.jieyi ? `<div class="mt-jieyi">${esc(c.jieyi)}</div>` : ""}${mtSeal(name)}${c.seal && typeof titleSeal === "function" ? `<div class="ttl-mt">${titleSeal(c.seal, true)}</div>` : ""}
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
        <div class="row"><button class="btn ghost small" data-act="mt-unzoom">收起</button>${z.name !== me && typeof mailShown === "function" && mailShown() ? `<button class="btn small" data-act="mail-write" data-name="${esc(z.name)}">寫信</button>` : ""}${can ? '<button class="btn ghost small mt-report" data-act="mt-report">檢舉這一張</button>' : ""}</div></div></div>`;
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
      ${typeof jieyiHtml === "function" ? jieyiHtml(S.main) : ""}
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

  // 此地還有誰（玩家之間的互動第一層，企劃者 2026-10-08）：場景卡底下一行，名字點了打開玩家卡（peerHtml）。
  // 人多時先列 HERE_SHOW 個、其餘收在「還有 N 人」裡（點了全列，記在 S.hereOpen）。每個角色都在同一份名單裡（伺服器不分）
  const HERE_SHOW = 5;
  function hereHtml(m) {
    const all = m.here || [];
    if (!all.length) return "";
    const open = S.hereOpen || all.length <= HERE_SHOW + 1;
    const list = open ? all : all.slice(0, HERE_SHOW);
    return `<div class="here"><span class="here-k">此地還有</span>${list.map((p) =>
      `<button class="peer-name" data-act="peer" data-name="${esc(p.name)}">${esc(p.name)}<small>（${esc(p.side)}）</small></button>`).join("")}${
      open ? "" : `<button class="linkish here-more" data-act="here-more">還有 ${all.length - HERE_SHOW} 人 ▾</button>`}</div>`;
  }

  // 玩家互動第二層：別人遞給你、還沒回的打招呼、結伴、切磋邀請（一件一行，後面是回應鈕——就是選單上的 invite: 選項，按了走 choose），
  // 以及結伴同行的那一行（跟著別人的人有「分道揚鑣」）。字都是伺服器寫好的（social.calls、Game.party_view）
  // 論武的答應要挑自己出哪一樣（FB-117）：那一顆帶 peer（他的名號），畫成「挑一樣答應」、按了打開他的玩家卡捲到答應那一格（peerAnswer，
  // 不送伺服器）；其餘照舊送選單上的 invite: 選項
  const callButton = (o) => (o.peer
    ? `<button class="btn small" data-act="peer-answer" data-name="${esc(o.peer)}">${esc(o.label)}</button>`
    : `<button class="btn small" data-act="choose" data-id="${esc(o.id)}" ${o.enabled ? "" : "disabled"}>${esc(o.label)}</button>`);
  // 場景那一列帶 peer 的回應鈕：選項 id → 他的名號（「此地還能做」裡同一顆也照它畫成打開玩家卡）
  function callPeers(m) {
    const out = {};
    (m.calls || []).forEach((c) => c.options.forEach((o) => { if (o.peer) out[o.id] = o.peer; }));
    return out;
  }
  // 別人遞來的邀請最多畫 CALLS_SHOW 列（FB-117：以前沒上限，一個人同時發四種就把整排行動擠出第一屏），其餘收成一行
  // 「還有 N 份邀請」、點了才攤開（openCalls、callsOpened）。舊的在前（伺服器排的，先逾時的先畫）
  // 第一屏還放不下時，畫好之後再從最後一份往前收（FIT_STEPS 的 calls），收掉的也併進那一行
  const CALLS_SHOW = 2;
  const callsMoreText = (n, all) => (all ? `有 ${n} 份邀請等你回應 ▾` : `還有 ${n} 份邀請 ▾`); // 待 joy 潤
  // 一份邀請的記號：它的編號（回應鈕的 id 最後那一段，invite:<回應>:<編號>）
  const callKey = (c) => String((c.options[0] && c.options[0].id) || c.text).split(":").pop();
  // 點了「還有 N 份／有 N 份邀請等你回應」：S.callsOpen 記點開那時的那幾份（callKey）。現在的每一份都還在裡面就算攤開著——
  // 其中幾份回了、逾時了照樣攤著，一份不剩才收回；來了新的一份就照平常收（不然它會把行動列推出第一屏）。
  // 以前記的是真假、邀請不超過 CALLS_SHOW 份就改回假：一、兩份被第一屏收法（6b）收成一行時，點了又被收回去、點不開（FB-241）
  function callsOpened(calls) {
    return Array.isArray(S.callsOpen) && calls.length > 0 && calls.every((c) => S.callsOpen.includes(callKey(c)));
  }
  function openCalls() {
    S.callsOpen = ((S.main && S.main.calls) || []).map(callKey);
    renderPage();
  }
  function socialHtml(m) {
    const all = m.calls || [];
    const open = callsOpened(all);
    if (!open) S.callsOpen = false;
    const list = open ? all : all.slice(0, CALLS_SHOW);
    const more = all.length - list.length;
    const calls = list.map((c) => `<div class="call"><span>${esc(c.text)}</span>${c.options.map(callButton).join("")}</div>`).join("")
      + (more ? `<button class="linkish calls-more" data-act="calls-more">${callsMoreText(more, false)}</button>` : "");
    const party = m.party ? `<div class="party"><span>${esc(m.party.text)}</span>${m.party.lead ? ""
      : '<button class="btn small ghost" data-act="party-leave">分道揚鑣</button>'}</div>` : "";
    return `<div class="calls" data-total="${all.length}">${calls}${party}</div>`;
  }
  async function leaveParty() {
    await busy(async () => {
      const r = await api("/api/party/leave", {});
      if (r.main) setMain(r.main);
      renderPage();
    });
  }

  // 玩家卡（第一層）：點「此地還有」的名字疊上來的抽屜。名號、門派・陣營・頭銜、等級、身上兩門（名字與品質），底下是卡上的動作鈕
  // （伺服器照 social.ACTIONS 給，第二層的贈物、結伴、打招呼、切磋、論武都掛在這裡）。人走了（card 是 null）寫伺服器給的那一句
  // still：輪詢換卡（applyPeer）時畫的那一張不再播一次滑上來、淡入（style.css 的 .still）
  function peerHtml(still = false) {
    const P = S.peer;
    const quiet = still ? " still" : "";
    const c = P.card;
    const body = P.loading ? '<p class="muted">……</p>'
      : !c ? `<p>${esc(P.gone || "對方已經不在這裡了。")}</p>${P.focus ? `<p class="muted">${esc(PEER_GONE_ANSWER)}</p>` : ""}`
      : `<div class="peer-head">${c.mingtie ? `<button class="peer-mt" data-act="mt-zoom-peer" aria-label="看${esc(c.name)}的名帖">${mtCardHtml(c.mingtie, c.name, "thumb")}</button>` : ""}<h3>${esc(c.name)}${c.title && c.title.name && typeof titleSeal === "function" ? ` ${titleSeal(c.title)}` : ""}</h3>${c.jieyi ? `<span class="peer-jieyi">${esc(c.jieyi)}</span>` : ""}<div class="peer-title">${[...c.affiliation.split("・"), `第${c.level}級`].map((t) => `<span class="peer-seg">${esc(t)}</span>`).join("・")}</div>${peerRenownHtml(c, P)}${c.record ? `<p class="peer-record">${esc(c.record)}</p>` : ""}${c.yuedan ? `<p class="peer-record peer-yuedan">${esc(c.yuedan)}</p>` : ""}${c.guard ? `<p class="peer-record peer-guard">${esc(c.guard)}</p>` : ""}</div>
        <div class="peer-arts">${c.arts.length ? c.arts.map((a) => `<div class="peer-art"><small>${esc(a.kind)}</small><b>${esc(a.name)}</b><span>${esc(a.quality)}</span></div>`).join("") : '<p class="muted">身上沒有功夫。</p>'}</div>
        ${P.amountFor != null && c.actions[P.amountFor] ? `<form class="free peer-amount" id="peer-amount">${choiceSelect(c.actions[P.amountFor])}<input class="input" name="amount" type="number" inputmode="numeric" min="${c.actions[P.amountFor].amount_min || 1}" max="${c.actions[P.amountFor].amount}" placeholder="${esc(c.actions[P.amountFor].label)}：${c.actions[P.amountFor].amount_min || 1}～${c.actions[P.amountFor].amount}" aria-label="數量"><button class="btn primary small" type="submit">送出</button></form>` : ""}
        ${P.textFor != null && c.actions[P.textFor] ? `<form class="free peer-amount peer-text" id="peer-text"><input class="input" name="text" maxlength="${c.actions[P.textFor].text}" value="${esc(P.textDraft || "")}" placeholder="附一句話（可以不寫，${c.actions[P.textFor].text} 字內）" aria-label="附一句話"><button class="btn primary small" type="submit">${esc(c.actions[P.textFor].label)}</button></form>` : ""}
        ${c.actions.length ? peerActsHtml(c.actions) : ""}`;
    return `<div class="sheet-bg${quiet}" data-act="peer-close"></div>
      <div class="sheet peer-card${quiet}" role="dialog" aria-label="${esc(P.name)}">
        <div class="grip"></div>
        ${P.msg ? `<div class="peer-msg">${P.msg}</div>` : ""}
        ${body}
        <div class="row"><button class="btn ghost" data-act="peer-close">關閉</button></div>
      </div>`;
  }
  // 玩家卡頭銜底下一排稱號小籤（名聲 3B，card.renown：只寫稱號、不寫數字）：名望金、善惡照 path 上色；點了在卡上攤開一段
  // 通用的說明（各段代表什麼，不寫他的數字；S.peer.renownOpen）。名聲關著、還沒有稱號不畫
  const RENOWN_PEER_HELP = "江湖上用兩個稱號認人：金色的看名望（小有名氣、名動一方、威震州郡、天下聞名，越後面越多人認得），"
    + "青色的是俠（善名比惡名高：江湖遊俠、一方豪俠、州郡大俠、天下名俠），赭色的是寇（惡名高：綠林好漢、江湖巨寇、州郡大盜、天下大盜）。";
  function peerRenownToggle(el) {
    if (!S.peer) return;
    S.peer.renownOpen = !S.peer.renownOpen;
    el.setAttribute("aria-expanded", String(S.peer.renownOpen));
    const ico = el.querySelector("i");
    if (ico) ico.textContent = S.peer.renownOpen ? "▴" : "›";
    const help = el.nextElementSibling;
    if (help && help.classList.contains("rn-peer-help")) help.remove();
    if (S.peer.renownOpen) el.insertAdjacentHTML("afterend", `<p class="rn-peer-help">${esc(RENOWN_PEER_HELP)}</p>`);
  }
  function peerRenownHtml(c, P) {
    const r = c.renown;
    if (!r || !r.titles.length) return "";
    const chips = r.titles.map((t, i) => `<span class="rn-chip ${i === r.titles.length - 1 && r.path ? rnPathClass(r.path) : "rn-fame"}">${esc(t)}</span>`).join("");
    return `<div class="rn-chips" data-act="renown-peer" role="button" tabindex="0" aria-expanded="${!!P.renownOpen}">${chips}<i aria-hidden="true">${P.renownOpen ? "▴" : "›"}</i></div>`
      + (P.renownOpen ? `<p class="rn-peer-help">${esc(RENOWN_PEER_HELP)}</p>` : "");
  }
  // 卡上的鈕：同一個 group 的（論武出哪一樣，每一樣一顆）收成一個下拉清單＋一顆鈕，按下去送清單上選的那一顆（照它在 actions 裡的索引）；
  // 只有一顆的 group 照常畫。下拉清單整排佔滿一列，其餘的鈕照舊兩欄
  // 合不成的那一樣（論武答應，伺服器灰掉、pick 後面寫兩三個字的原因，FB-117）也收進清單、但挑不了（<option disabled>），
  // 預設選第一樣挑得了的；整組都挑不了時那顆鈕灰掉。答應那幾顆（arg 是 yes 開頭）標 data-answer="<互動>"：
  // 從場景底下「挑一樣答應」打開卡時捲到它（openPeer 的 focus）
  function peerActsHtml(actions) {
    const groups = {};
    actions.forEach((b, i) => { if (b.group) (groups[`${b.action}|${b.group}`] ||= []).push(i); });
    const done = new Set();
    const answer = (b) => (/^yes(:|$)/.test(b.arg || "") ? ` data-answer="${esc(b.action)}"` : "");
    // 名字包一格不折行（.pa-name）；說明放得下就跟名字並排，放不下自己換到下一行再折（style.css 的 .peer-acts，FB-220）
    const one = (b, i) => `<button class="btn" data-act="peer-act" data-i="${i}"${answer(b)} ${b.enabled ? "" : "disabled"}><span class="pa-name">${esc(b.label)}</span>${b.note ? `<small>${esc(b.note)}</small>` : ""}</button>`;
    const html = actions.map((b, i) => {
      const members = b.group ? groups[`${b.action}|${b.group}`] : null;
      if (!members || members.length < 2) return one(b, i);
      if (done.has(members)) return "";
      done.add(members);
      const first = members.find((j) => actions[j].enabled);
      const live = first !== undefined;
      return `<div class="peer-pick"${answer(b)}><select class="input" aria-label="${esc(b.group)}">${members.map((j) => `<option value="${j}"${actions[j].enabled ? "" : " disabled"}${j === first ? " selected" : ""}>${esc(actions[j].pick || actions[j].label)}</option>`).join("")}</select>`
        + `<button class="btn" data-act="peer-pick"${live ? "" : " disabled"}><span class="pa-name">${esc(b.group)}</span>${b.note ? `<small>${esc(b.note)}</small>` : ""}</button></div>`;
    }).join("");
    return `<div class="peer-acts">${html}</div>`;
  }
  // 卡上的鈕要先挑一樣（贈素材）：一個下拉選單，每一樣寫身上有幾份
  const choiceSelect = (b) => (b.choices && b.choices.length
    ? `<select class="input" name="choice" aria-label="挑一樣">${b.choices.map((x) => `<option value="${esc(x.id)}">${esc(x.label)}（${x.max}）</option>`).join("")}</select>`
    : "");
  // focus：從場景底下「挑一樣答應」打開的（FB-117）——卡畫好之後捲到那一種互動答應的那一格（data-answer）、框一下金邊。
  // 他已經不在這裡（卡打不開）時照舊寫伺服器那一句，底下多一句這份邀請怎麼辦（邀請照現在的規則：放著等逾時，或在場景底下婉拒）
  const PEER_GONE_ANSWER = "這份邀請答不成了：在場景底下按「婉拒」收掉，或放著等它逾時作廢。"; // 待 joy 潤
  async function openPeer(name, focus = "") {
    S.peer = { name, loading: true, focus };
    render();
    try {
      const r = await api(`/api/peer?name=${encodeURIComponent(name)}`);
      if (!S.peer || S.peer.name !== name) return; // 等的時候關掉或換了人
      S.peer = { name, card: r.card, gone: r.gone, focus };
    } catch (e) {
      S.peer = null;
    }
    render();
    if (focus && S.peer && S.peer.card) peerFocus(focus);
  }
  function peerFocus(focus) {
    const el = document.querySelector(`.peer-card [data-answer="${focus}"]`);
    if (!el) return;
    el.classList.add("peer-focus");
    el.scrollIntoView({ block: "nearest", behavior: promoCalm() ? "auto" : "smooth" }); // promoCalm：偏好減少動態效果
  }

  // 玩家卡開著時跟著輪詢更新（FB-117）：對方發了邀請、收回、走了，卡上的鈕要跟著變，不然按了才知道。輪詢拿到有變的畫面時重抓這張卡
  // （/api/peer，只讀），內容變了才換掉那一張（只換卡，底下的頁面不動；捲到的地方、下拉清單挑的那一樣照放回去）。
  // 不換的時候：正在送動作（S.busy）、確認框開著（它記的是舊卡上第幾顆）、數量欄攤開、正在下拉清單或輸入框上（typing）。
  // 手指按著時先收著（peerNext），放開才換——S.peer 跟畫面上那一張要是同一份，按下去的索引才對得上（同江湖頁的 pointerHeld）
  let peerPolling = false;
  let peerNext = null; // { P, r }：按著的時候抓到的新卡
  async function refreshPeer() {
    const P = S.peer;
    if (!P || P.loading || peerPolling || S.busy) return;
    peerPolling = true;
    try {
      const r = await api(`/api/peer?name=${encodeURIComponent(P.name)}`);
      if (JSON.stringify(r.card) === JSON.stringify(P.card)) return;
      if (pointerHeld) peerNext = { P, r };
      else applyPeer(P, r);
    } catch (e) { /* 下一輪再說 */ } finally { peerPolling = false; }
  }
  function applyPeer(P, r) {
    peerNext = null;
    if (S.peer !== P || S.busy || P.amountFor != null || P.textFor != null || typing() || document.querySelector(".ask-layer")) return;
    S.peer = { name: P.name, card: r.card, gone: r.gone, focus: P.focus, msg: P.msg }; // 上一個動作回的那一句照留
    const old = document.querySelector(".peer-card");
    if (!old) return;
    // 下拉清單挑的那一樣（照它的 arg 認：新卡上的索引可能不一樣）
    const picked = new Set([...old.querySelectorAll(".peer-pick select")].map((x) => (P.card && P.card.actions[Number(x.value)] || {}).arg));
    const top = old.scrollTop;
    const bg = old.previousElementSibling;
    old.insertAdjacentHTML("afterend", peerHtml(true));
    old.remove();
    if (bg && bg.classList.contains("sheet-bg")) bg.remove();
    const now = document.querySelector(".peer-card");
    if (!now) return;
    now.scrollTop = top;
    const actions = (r.card && r.card.actions) || [];
    now.querySelectorAll(".peer-pick select").forEach((x) => {
      const j = [...x.options].map((o) => Number(o.value)).find((k) => picked.has(actions[k].arg) && actions[k].enabled);
      if (j !== undefined) x.value = String(j);
    });
  }
  // 按卡上的鈕：要填數量的先問數量（prompt 在 artifact 外照常可用，但這裡一律用頁內的輸入，見 peerAmount），有 confirm 的先問一次
  // 等回應的時候（論武答應時首創要等模型取名，FB-117）：照送出指令的回饋那一套（busy），論武答應另有一句等候的話（WAIT_LINES.discuss）。
  // 回來時卡已經關了、或換成別人的卡：不把剛才那張又彈出來，結果用提示泡泡講一句短的（伺服器給的 brief：論武合成了是
  // 「論武有結果了：合出【某某】。詳見江湖紀錄。」，其餘是回話的第一句；完整的在江湖紀錄，FB-242）
  async function peerAct(i, sure = false, amount = 0, choice = "", text = null) {
    const P = S.peer;
    const b = P && P.card && P.card.actions[i];
    if (!b) return;
    if (b.amount > 0 && !amount) { S.peer.amountFor = i; render(); return; }
    if (b.text > 0 && text == null) { S.peer.textFor = i; S.peer.textDraft = ""; render(); document.querySelector("#peer-text input")?.focus(); return; } // 挑釁：先攤開一格輸入框
    if (!sure && b.confirm) { ask(b.confirm, b.label, () => peerAct(i, true, amount, choice)); return; }
    const line = b.action === "discuss" && /^yes:/.test(b.arg || "") ? WAIT_LINES.discuss : SENT_WAITING;
    await busy(async () => {
      const r = await api("/api/peer/act", { name: P.name, action: b.action, arg: b.arg, amount, choice, text: text || "" });
      if (r.main) setMain(r.main);
      if (S.peer && S.peer.name === P.name) {
        S.peer = { name: P.name, card: r.card, gone: r.gone, msg: r.message };
        // 那一句被擋下（鈕還按得下去）：輸入框照開著、打的字留著，改一改再送
        const again = text && r.card ? r.card.actions.findIndex((x) => x.action === b.action && x.arg === b.arg && x.enabled && x.text > 0) : -1;
        if (again >= 0) { S.peer.textFor = again; S.peer.textDraft = text; }
      }
      else if (r.brief || r.message) toast(r.brief || r.message.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim());
      render();
    }, line);
  }
  async function peersClick(act, el, ev) {
    switch (act) {
        case "peer": await openPeer(el.dataset.name); break;
        case "peer-close": S.peer = null; render(); break;
        case "peer-answer": await openPeer(el.dataset.name, "discuss"); break; // 場景底下論武的「挑一樣答應」（FB-117）
        case "peer-act": await peerAct(Number(el.dataset.i)); break;
        case "peer-pick": await peerAct(Number(el.parentElement.querySelector("select").value)); break;
        case "here-more": S.hereOpen = true; renderPage(); break;
        case "calls-more": openCalls(); break; // 場景底下收起來的邀請（FB-117、FB-241）
        case "party-leave": await leaveParty(); break;
        case "renown-peer": peerRenownToggle(el); break; // 3B：玩家卡的稱號小籤，原地攤開說明（不重畫整張卡）
        case "mt-edit": if (!S.mingtie) await loadMingtie(); mtEditOpen(); break;
        case "mt-close": S.mtEdit = null; render(); break;
        case "mt-ink": S.mtEdit.ink = Number(el.dataset.i); mtEditRedraw(); break;
        case "mt-pen": S.mtEdit.pen = Number(el.dataset.i); mtEditRedraw(); break;
        case "mt-undo": S.mtEdit.strokes.pop(); S.mtEdit.note = ""; mtEditRedraw(); break;
        case "mt-clear": S.mtEdit.strokes = []; S.mtEdit.note = ""; mtEditRedraw(); break;
        case "mt-title": {
          const E = S.mtEdit, t = el.dataset.t, cap = S.mingtie.limits.titles;
          if (E.titles.includes(t)) E.titles = E.titles.filter((x) => x !== t);
          else if (E.titles.length < cap) E.titles = [...E.titles, t];
          else { E.note = `頭銜最多 ${cap} 個：先點掉一個。`; }
          mtEditRedraw();
          break;
        }
        case "mt-shuffle": { // 刷新：從掙到的頭銜裡隨機換一批（只在這台裝置挑，定稿時伺服器再驗是不是你掙到的）
          const pool = S.mingtie.pool.slice();
          for (let k = pool.length - 1; k > 0; k--) { const j = Math.floor(Math.random() * (k + 1)); [pool[k], pool[j]] = [pool[j], pool[k]]; }
          S.mtEdit.titles = pool.slice(0, S.mingtie.limits.titles);
          mtEditRedraw();
          break;
        }
        case "mt-save": await mtSave(); break;
        case "mt-zoom-peer": if (S.peer && S.peer.card && S.peer.card.mingtie) { S.mtZoom = { name: S.peer.card.name, card: S.peer.card.mingtie }; render(); } break;
        case "mt-zoom-mine": if (S.mingtie && S.mingtie.mine) { S.mtZoom = { name: S.main.status.name, card: S.mingtie.mine }; render(); } break;
        case "mt-zoom-box": { const x = S.mingtie && S.mingtie.box[Number(el.dataset.i)]; if (x) { S.mtZoom = { name: x.name, card: x.card, when: [x.when, x.place].filter(Boolean).join("・") }; render(); } break; }
        case "mt-unzoom": if (ev.target.closest(".mt-zoom-box") && el.classList.contains("mt-zoom-layer")) break; S.mtZoom = null; render(); break;
        case "mt-report": await mtReport(); break;
    } // peersClick
  } // peersClick
  registerClicks(peersClick, ["peer", "peer-close", "peer-answer", "peer-act", "peer-pick", "here-more", "calls-more", "party-leave", "renown-peer", "mt-edit", "mt-close", "mt-ink", "mt-pen", "mt-undo", "mt-clear", "mt-title", "mt-shuffle", "mt-save", "mt-zoom-peer", "mt-zoom-mine", "mt-zoom-box", "mt-unzoom", "mt-report"]);
  async function peersForm(form, data) {
      if (form.id === "peer-amount") {
        const i = S.peer ? S.peer.amountFor : null;
        const n = Math.floor(Number(data.amount));
        if (i == null || !(n >= 1)) return;
        S.peer.amountFor = null;
        await peerAct(i, false, n, data.choice || "");
      } else if (form.id === "peer-text") {
        const i = S.peer ? S.peer.textFor : null;
        if (i == null) return;
        S.peer.textFor = null;
        await peerAct(i, false, 0, "", (data.text || "").trim());
      } // peersForm
  } // peersForm
  registerForms(peersForm, ["peer-amount", "peer-text"]);
  async function peersChange(ev) {
    if (ev.target.id === "mt-preset" && S.mtEdit && ev.target.value) { // 名帖：換成一張現成的畫（之後照樣能再畫幾筆）
      const art = (S.mingtie.presets || []).find((p) => p.id === ev.target.value);
      if (art) { S.mtEdit.strokes = art.strokes.map((x) => x.slice()); S.mtEdit.note = ""; mtEditRedraw(); }
    }
  } // peersChange
  registerChanges(peersChange);
