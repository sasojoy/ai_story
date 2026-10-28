// 出陣約戰網頁的草圖原型（2026-10-28）：只注入在拍照的那一頁裡，web/ 一個字不動。
// 用法（無頭 Chromium 的 Runtime.evaluate）：先把這支整段送進頁面，再 `await SX.boot("A"|"B"|"C")`，之後 SX.open()、SX.seal([...])、SX.duels()。
// 規矩（tianxia-dev 的 網頁.md「只注入原型、不改程式時」）：boot 先 fetch("/api/main") 與 fetch("/api/map/state") 拿伺服器真的給的資料，
// 再把 window.fetch 換成永遠不回（十秒一次的輪詢不會把注入的東西重畫掉），關掉轉場與動畫。class 盡量用現有的
// （.card、.btn、.btn.primary、.btn.small、.btn.ghost、.seg、.sheet／.sheet-bg／.grip、.sf-row／.sf-bar／.sf-chip、.wk-x），
// 版面多出來的幾樣用 sx- 開頭（做進程式時照 style.css 的變數改名）。
// 畫面上新寫的字全部待 joy 潤（index.html 列了一張表）。
(() => {
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  // 卡上只有陣營 id（attacker_side、map 的 control）：名字照劇本寫死在這裡（做進程式時讀伺服器給的名字；見 index.html「資料不夠的地方」）
  const SIDE = { guan: "官軍", huang: "黃巾", haoqiang: "豪強" };
  const ROUNDS = ["一", "二", "三"];
  const mins = (sec) => Math.max(1, Math.ceil(sec / 60));

  const CSS = `
*,*::before,*::after{transition:none!important;animation:none!important}
.act-sortie{margin-bottom:12px;padding:10px 12px 12px}
.sx-top{display:flex;align-items:baseline;gap:8px;margin:0}
.sx-top b{flex:none;font:700 17px var(--serif)}
.sx-top span{flex:1 1 auto;min-width:0;text-align:right;font-size:12px;color:var(--ink-2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sx-sec{margin-top:8px;padding-top:7px;border-top:1px dashed var(--line)}
.sx-h{display:flex;align-items:baseline;gap:8px;margin:0 0 4px}
.sx-h b{flex:none;font:700 14px var(--serif);color:var(--accent);letter-spacing:.12em}
.sx-h span{flex:1 1 auto;min-width:0;font-size:12px;color:var(--ink-2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sx-sec .sf-row{margin:3px 0}
.sx-sec .sf-chips{margin-top:5px}
.sx-gl{display:grid;grid-template-columns:4.4em minmax(0,1fr);column-gap:8px;row-gap:2px;margin:0;font-size:13px;line-height:1.5}
.sx-gl dt{color:var(--ink-2);white-space:nowrap}
.sx-gl dd{margin:0;min-width:0}
.sx-gl dd b{font-weight:700}
.sx-gl dd small{margin-left:4px;font-size:12px;color:var(--ink-2)}
.sx-gl dd.up b{color:var(--ok)}
.sx-note{margin:4px 0 0;font-size:12px;line-height:1.5;color:var(--ink-2)}
.sx-round{display:grid;grid-template-columns:3.2em minmax(0,1fr);align-items:center;column-gap:6px;margin:4px 0}
.sx-round .sx-n{font:600 12px var(--serif);color:var(--ink-2);white-space:nowrap}
.sx-round .seg{margin:0;padding:2px;gap:2px;overflow:visible}
.sx-round .seg button{flex:1 1 0;min-width:0;padding:7px 0;font-size:14px}
.sx-round .seg button.on{color:var(--accent);font-weight:700}
.sx-round .seg button.sx-back{color:var(--ink-2)}
.sx-round .seg button.sx-back.on{color:var(--ink)}
.sx-dim .sx-round{opacity:.55}
.btn.sx-go{flex-direction:column;gap:0;margin-top:8px;min-height:52px}
.btn.sx-go b{font-size:15px}
.btn.sx-go small{font-size:12px;font-weight:400;opacity:.92}
.sx-own{margin:6px 0 0;padding:8px 10px;border-left:3px solid var(--kuai);background:var(--card-2);border-radius:8px;font-size:13px;line-height:1.6}
.sx-duels{padding:8px 12px}
.sx-duel{padding:8px 0}
.sx-duel+.sx-duel{border-top:1px solid var(--line)}
.sx-dhead{display:flex;align-items:baseline;gap:6px;font-size:14px;line-height:1.4}
.sx-dhead b{font-weight:700}
.sx-dhead .sx-at{min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sx-left{margin-left:auto;flex:none;font-size:12px;color:var(--accent);font-variant-numeric:tabular-nums;white-space:nowrap}
.sx-tag{--c:var(--ink-2);flex:none;align-self:center;padding:0 6px;border-radius:999px;background:var(--c);color:#fff;font:700 11px/18px var(--sans)}
.sx-tag.side-guan{--c:var(--kuai)}
.sx-tag.side-huang{--c:var(--gold);color:#2a241d}
.sx-dact{display:flex;align-items:center;gap:8px;margin-top:6px}
.sx-dact small{flex:1 1 auto;min-width:0;font-size:12px;line-height:1.4;color:var(--ink-2)}
.sx-dact .btn.small{flex:none;min-width:64px;min-height:36px}
.sx-dact .btn.ghost{padding:6px 10px}
.sx-far .sx-dhead,.sx-drow.sx-far>:not(.btn){opacity:.6}
.sx-badge{position:absolute;top:5px;right:5px;min-width:17px;height:17px;padding:0 4px;border-radius:9px;background:var(--accent);color:#fff;font:700 11px/17px var(--sans);font-style:normal}
.sx-sheet{padding-bottom:0;max-height:88vh}
.sx-shead{display:flex;align-items:center;gap:8px;margin:0 0 8px}
.sx-shead b{flex:1 1 auto;font:700 18px var(--serif)}
.sx-shead span{font-size:12px;color:var(--ink-2)}
.sx-shead .wk-x{margin:0 -8px 0 0}
.sx-sheet .seg.sx-tabs{margin:0 0 4px}
.sx-sheet .seg.sx-tabs b{margin-left:4px;padding:0 6px;border-radius:9px;background:var(--accent);color:#fff;font-size:11px}
.sx-sheet .sx-sec:first-of-type{border-top:0;margin-top:2px}
.sx-sheet .sx-duels{margin-top:6px}
.sx-foot{position:sticky;bottom:0;margin:8px -16px 0;padding:0 16px calc(14px + var(--bottom));background:var(--paper);border-top:1px solid var(--line)}
.sx-det{border-top:1px dashed var(--line);margin-top:6px}
.sx-det>summary{list-style:none;display:flex;align-items:baseline;gap:8px;padding:7px 0 5px;cursor:pointer}
.sx-det>summary::-webkit-details-marker{display:none}
.sx-det>summary b{flex:none;font:700 14px var(--serif);color:var(--accent);letter-spacing:.12em}
.sx-det>summary span{flex:1 1 auto;min-width:0;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sx-det>summary::after{content:"▸";flex:none;color:var(--ink-2);font-size:12px}
.sx-det[open]>summary::after{content:"▾"}
.sx-det>.sx-sec{margin-top:0;padding-top:0;border-top:0}
.sx-drow{display:flex;align-items:center;gap:6px;padding:6px 0;font-size:13px;line-height:1.4}
.sx-drow+.sx-drow{border-top:1px solid var(--line)}
.sx-drow .sx-dt{flex:1 1 auto;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sx-drow .sx-left{margin-left:0}
.sx-drow .btn.small{flex:none;min-width:58px;min-height:34px;padding:4px 10px}
`;

  // ── 共用的幾塊 ──
  function blockSec(st, opts = {}) {
    const c = st.card, mine = st.side, them = mine === "guan" ? "huang" : "guan";
    const place = st.place || {};
    const holder = place.control ? `${SIDE[place.control]}的地方` : "中立地・還沒人佔"; // 歸誰：卡上沒有，這裡讀 /api/map/state 的 control
    const can = !c.why_not && !opts.noGain;
    const gain = can ? Math.min(c.gain.push, 100 - c.bars.mine) : 0;
    const row = (side, v, isMine) => `<div class="sf-row side-${side}${isMine ? " mine" : ""}"><span class="sf-name">${esc(SIDE[side])}</span>`
      + `<span class="sf-bar"><i class="sf-fill" style="width:${v}%"></i>${isMine && gain ? `<i class="sf-gain" style="left:${v}%;width:${gain}%"></i>` : ""}</span>`
      + `<span class="sf-num">${v}</span></div>`;
    // 自家的地方：卡上的 to_flip 算的是自己那一條（自家的地方用不著推），改寫對面離翻走這裡還差多少（見 index.html「資料不夠的地方」）
    const own = !st.answer && c.why_not === "等對面來約";
    const chips = own ? [
      `${SIDE[them]}推滿 100 才翻走這裡・還差 ${100 - c.bars.theirs}`,
      c.foe_pushing ? `對面 ${c.foe_pushing} 人在推` : "對面沒人在推",
    ] : [
      `推滿 100 易手・還差 ${c.to_flip}`,
      c.foe_pushing ? `對面 ${c.foe_pushing} 人在推` : "對面沒人在推",
      c.allies ? `同袍 ${c.allies} 人・集火 +${Math.round(c.focus_bonus * 100)}%` : "同袍還沒人來",
      c.convoy_at ? `運糧隊「${c.convoy_at}」正經過` : "",
    ].filter(Boolean);
    return `<div class="sx-sec">${opts.head === false ? "" : `<p class="sx-h"><b>這一塊</b><span>${esc(c.place)}・${esc(holder)}</span></p>`}`
      + row(mine, c.bars.mine, true) + row(them, c.bars.theirs, false)
      + `<div class="sf-chips">${chips.map((t) => `<span class="sf-chip">${esc(t)}</span>`).join("")}</div></div>`;
  }
  function gainSec(st, opts = {}) {
    const c = st.card, g = c.gain;
    const after = c.bars.mine + g.push, left = Math.max(0, c.to_flip - g.push);
    const rows = [
      ["推一程", `<b>+${g.push}</b><small>${left > 0 ? `→ ${after}，離易手還差 ${left}` : "推滿易手"}</small>`, "up"],
      ["貢獻", `<b>+${g.contribution}</b>${g.rank_next != null ? `<small>離下一階還差 ${g.rank_next}</small>` : ""}`, "up"],
      ["戰利", `<b>${esc(g.loot)}</b>`, ""],
      ["易手分紅", `<b>約 ${g.dividend} 銀兩</b><small>推滿那一刻照推的份分</small>`, ""],
      ["軍令", g.order_match ? "<b>正是本週攻城軍令</b>" : "<small style=\"margin:0\">不是本週軍令要的地方</small>", ""],
      ["戰書", g.letter_gap > 0 ? `<b>還差 ${g.letter_gap}</b><small>推到 ${c.bars.mine + g.letter_gap} 可下戰書</small>` : "<b>已可下戰書</b>", ""],
    ];
    return `<div class="sx-sec">${opts.head === false ? "" : `<p class="sx-h"><b>贏了</b><span>照險勝估；大勝多推五成、僵持只推四成</span></p>`}`
      + `<dl class="sx-gl">${rows.map(([k, v, cls]) => `<dt>${k}</dt><dd class="${cls}">${v}</dd>`).join("")}</dl></div>`;
  }
  // 封三招：四招一排（.seg），一回合一排；三招都挑了才亮
  function sealSec(st, opts = {}) {
    const c = st.card, picked = st.picked || [], d = st.answer;
    const own = !d && c.why_not === "等對面來約";
    if (own) {
      return `<div class="sx-sec"><p class="sx-h"><b>封三招</b><span>這裡不貼約戰</span></p>`
        + `<p class="sx-own">這裡是${esc(SIDE[st.side])}的地方：守就是應戰。對面在這一區約戰時，約戰卡上按「應戰」、封三招守住它。</p>`
        + (opts.noButton ? "" : goButton(st)) + `</div>`;
    }
    const rounds = ROUNDS.map((n, i) => `<div class="sx-round"><span class="sx-n">第${n}回合</span><div class="seg" role="group" aria-label="第${n}回合">${c.moves.map((mv) =>
      `<button class="${picked[i] === mv ? "on" : ""}${mv === "撤退" ? " sx-back" : ""}" aria-pressed="${picked[i] === mv}">${esc(mv)}</button>`).join("")}</div></div>`).join("");
    const when = d ? `${mins(d.expires_in)} 分後開打` : "10 分鐘後開打"; // 窗幾分鐘卡上沒有（Config.sortie.window_minutes），這裡寫死 10
    return `<div class="sx-sec${c.why_not && !d ? " sx-dim" : ""}">${opts.head === false ? "" : `<p class="sx-h"><b>封三招</b><span>固守剋強攻・強攻剋奇襲・奇襲剋固守</span></p>`}${rounds}`
      + `<p class="sx-note">撤退：這一回合認輸，少扣七成氣血。封了就不能改，${when}，戰報送到。</p>`
      + (opts.noButton ? "" : goButton(st)) + `</div>`;
  }
  // 應戰那一刻：這一塊（約戰的那一塊就是腳下這一塊時才有兩條的數字）＋守住了得什麼（伺服器沒給數字，照設計寫一句）＋同一個封三招
  function answerSecs(st, summary) {
    const c = st.card, d = st.answer;
    const same = c && d.block === c.block;
    const rows = [
      ["這一塊", `<b>${esc(SIDE[d.attacker_side])}的進度被拉回</b>`],
      ["貢獻", "<b>記一筆守城功</b>"],
      ["經驗心得", "<b>同出陣打贏的那一份</b>"],
      ["輸了", "<small style=\"margin:0\">內傷加重・出陣與應戰多等 30 分</small>"],
    ];
    const keep = `<div class="sx-sec"><p class="sx-h"><b>守住了</b><span>數字等伺服器給</span></p><dl class="sx-gl">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("")}</dl></div>`;
    if (summary) {
      const line = same ? `${SIDE[st.side].slice(0, 1)} ${c.bars.mine}／${SIDE[d.attacker_side].slice(0, 1)} ${c.bars.theirs}・對面 ${c.foe_pushing} 人在推` : `${d.place}`;
      return `<details class="sx-det"><summary><b>這一塊</b><span>${esc(line)}</span></summary>${same ? blockSec(st, { head: false, noGain: true }) : ""}</details>`
        + `<details class="sx-det"><summary><b>守住了</b><span>拉回對面的進度・記貢獻・經驗心得</span></summary>${keep.replace(/<p class="sx-h">.*?<\/p>/, "")}</details>`;
    }
    return (same ? blockSec(st, { noGain: true }) : "") + keep;
  }
  function goButton(st) {
    const c = st.card, picked = (st.picked || []).filter(Boolean), d = st.answer;
    if (d) {
      const sub = `體力 12・今日還能應戰 ${d.answers_left} 次`; // 應戰的體力卡上沒有（answer_stamina），寫死 12
      return picked.length < 3 ? `<button class="btn primary sx-go" disabled><b>還要挑 ${3 - picked.length} 招</b><small>${esc(sub)}</small></button>`
        : `<button class="btn primary sx-go"><b>封好三招，應戰</b><small>${esc(picked.join("・"))}・${esc(sub)}</small></button>`;
    }
    const sub = `體力 ${c.cost}・今日還能 ${c.left_today} 次`;
    if (c.why_not) {
      const why = c.cooldown_until ? `冷卻中・還要 ${mins(c.cooldown_until - st.now)} 分` : c.why_not;
      return `<button class="btn primary sx-go" disabled><b>${esc(why)}</b><small>${esc(sub)}</small></button>`;
    }
    if (picked.length < 3) return `<button class="btn primary sx-go" disabled><b>還要挑 ${3 - picked.length} 招</b><small>${esc(sub)}</small></button>`;
    return `<button class="btn primary sx-go"><b>封好三招，出陣</b><small>${esc(picked.join("・"))}・${esc(sub)}</small></button>`;
  }
  // 約戰卡（main.sorties 一張一塊）：對面同一區（應戰）、對面不同一區（應戰灰著＋前往）、同袍（同去）
  function duelCard(d, st) {
    const ally = d.role === "join";
    const tag = ally ? `<span class="sx-tag side-${esc(d.attacker_side)}">同袍</span>` : `<span class="sx-tag side-${esc(d.attacker_side)}">${esc(SIDE[d.attacker_side] || d.attacker_side)}</span>`;
    const head = `<div class="sx-dhead">${tag}<b>${esc(d.attacker)}</b><span class="sx-at">約戰${esc(d.place)}</span><span class="sx-left">還有 ${mins(d.expires_in)} 分</span></div>`;
    let act;
    if (ally) {
      act = d.can_join
        ? `<button class="btn small primary">同去</button><small>算一次出陣・體力 ${st.card ? st.card.cost : 12}・集火加成</small>`
        : `<button class="btn small" disabled>同去</button><small>${esc(d.why_not)}</small>`;
    } else if (d.can_answer) {
      act = `<button class="btn small primary">應戰</button><small>今日還能應戰 ${d.answers_left} 次・體力 12・封三招</small>`;
    } else if (!d.same_region) { // 灰著：整張淡一點，應戰鈕不畫（按不下去），原因一句＋前往（點了開輿圖、選那一處）
      act = `<small>${esc(d.why_not)}</small><button class="btn small ghost">前往・步行約 ${d.travel_minutes} 分</button>`;
      return `<div class="sx-duel sx-far">${head}<div class="sx-dact">${act}</div></div>`;
    } else {
      act = `<button class="btn small" disabled>應戰</button><small>${esc(d.why_not)}</small>`;
    }
    return `<div class="sx-duel">${head}<div class="sx-dact">${act}</div></div>`;
  }
  // 排的先後：應得了的、同去得了的、其餘（伺服器照新的在前）
  const rank = (d) => (d.can_answer ? 0 : d.can_join ? 1 : d.role === "mine" ? 2 : 3);
  // 丙：一張一行
  function duelRow(d) {
    const ally = d.role === "join";
    const tag = `<span class="sx-tag side-${esc(d.attacker_side)}">${ally ? "同袍" : esc(SIDE[d.attacker_side] || "")}</span>`;
    const btn = ally ? `<button class="btn small${d.can_join ? " primary" : ""}" ${d.can_join ? "" : "disabled"}>同去</button>`
      : d.can_answer ? `<button class="btn small primary">應戰</button>`
        : !d.same_region ? `<button class="btn small ghost">前往 ${d.travel_minutes} 分</button>` : `<button class="btn small" disabled>應戰</button>`;
    return `<div class="sx-drow${!ally && !d.can_answer && !d.same_region ? " sx-far" : ""}">${tag}<span class="sx-dt"><b>${esc(d.attacker)}</b>約戰${esc(d.place)}</span><span class="sx-left">${mins(d.expires_in)} 分</span>${btn}</div>`;
  }
  function duelsCard(st, rows) {
    const list = st.duels.filter((d) => d.status === "open" || d.status === "answered").sort((a, b) => rank(a) - rank(b));
    if (!list.length) return "";
    const far = list.filter((d) => d.role === "answer" && !d.same_region).length;
    return `<div class="card sx-duels" id="sx-duels"><p class="sx-h"><b>約戰</b><span>${list.length} 張${far ? `・${far} 張在別區` : ""}・窗滿就開打</span></p>`
      + list.map((d) => (rows ? duelRow(d) : duelCard(d, st))).join("") + `</div>`;
  }

  // ── 行動列那一格：點了打開（灰著也點得開，卡上寫為什麼；格子小字照伺服器）──
  function cell() { return document.querySelector('#page .act-ink[data-key="train"]'); }
  function cellOpen(on) {
    const el = cell();
    if (!el) return;
    el.classList.remove("off");
    el.removeAttribute("disabled");
    el.classList.toggle("on", !!on);
  }
  function reveal(el) { // 同 main.js 的 revealMoveCard：卡底離分頁列頂 12 px、最多捲到卡頂貼在狀態列底下 8 px
    const tabs = document.querySelector(".tabs"), head = document.getElementById("top");
    const r = el.getBoundingClientRect(), tabsTop = tabs.getBoundingClientRect().top, topEdge = head && !head.hidden ? head.getBoundingClientRect().bottom : 0;
    const over = r.bottom - (tabsTop - 12);
    if (over > 0) window.scrollBy(0, Math.ceil(Math.max(0, Math.min(over, r.top - (topEdge + 8)))));
  }

  // ── 三版 ──
  // 卡頂那一行：出陣（或應戰）・地點，右邊今天還能幾次
  function topLine(st) {
    const c = st.card, d = st.answer;
    return d ? `<p class="sx-top"><b>應戰・${esc(d.place)}</b><span>${esc(d.attacker)}約戰・還有 ${mins(d.expires_in)} 分</span></p>`
      : `<p class="sx-top"><b>出陣・${esc(c.place)}</b><span>今日還能 ${c.left_today} 次・體力 ${c.cost}</span></p>`;
  }
  const isOwn = (st) => !st.answer && st.card.why_not === "等對面來約";
  const V = {
    // 甲：行動列底下原地展開（同探索三選一），三段全攤開；約戰卡一張一塊，排在行動列底下
    A: {
      page(st) { cellOpen(false); insertAfterBar(duelsCard(st, false)); },
      open(st) {
        cellOpen(!st.answer);
        const body = st.answer ? answerSecs(st, false) : `${blockSec(st)}${isOwn(st) ? "" : gainSec(st)}`;
        insertAfterBar(`<div class="card act-sortie" id="sx-panel">${topLine(st)}${body}${sealSec(st)}</div>` + (st.answer ? "" : duelsCard(st, false)));
        reveal(document.getElementById("sx-panel"));
      },
      duels(st) { cellOpen(false); insertAfterBar(duelsCard(st, false)); reveal(document.getElementById("sx-duels")); },
    },
    // 乙：半屏抽屜（.sheet），上面兩個頁籤：「我來約戰」（三段＋封三招，出陣鈕釘在抽屜底）、「應戰・同去」（約戰卡）；頁面上只在格子角上一個數字
    B: {
      page(st) { cellOpen(false); badge(st); },
      open(st, tab) {
        tab = tab || (st.answer ? "answer" : "go");
        document.querySelectorAll("#sx-panel, #sx-bg").forEach((e) => e.remove());
        cellOpen(true); badge(st);
        const c = st.card, n = openCount(st);
        const body = tab === "go" ? `${blockSec(st)}${isOwn(st) ? "" : gainSec(st)}${sealSec(st, { noButton: true })}`
          : tab === "answer" ? `${answerSecs(st, false)}${sealSec(st, { noButton: true })}`
            : duelsCard(st, false).replace('class="card sx-duels"', 'class="sx-duels"');
        const foot = tab !== "duels" ? `<div class="sx-foot">${goButton(st)}</div>` : "";
        const head = tab === "answer" ? `<div class="sx-shead"><b>應戰・${esc(st.answer.place)}</b><span>${esc(st.answer.attacker)}約戰・還有 ${mins(st.answer.expires_in)} 分</span><button class="wk-x" aria-label="收起">×</button></div>`
          : `<div class="sx-shead"><b>出陣・${esc(c.place)}</b><span>今日還能 ${c.left_today} 次</span><button class="wk-x" aria-label="收起">×</button></div>`;
        document.body.insertAdjacentHTML("beforeend", `<div class="sheet-bg" id="sx-bg"></div><div class="sheet sx-sheet" id="sx-panel" role="dialog" aria-label="出陣"><div class="grip"></div>`
          + head
          + `<div class="seg sx-tabs" role="tablist"><button class="${tab === "go" ? "on" : ""}">我來約戰</button><button class="${tab !== "go" ? "on" : ""}">應戰・同去${n ? `<b>${n}</b>` : ""}</button></div>`
          + `${body}${foot}</div>`);
        const sh = document.getElementById("sx-panel");
        if (st.scrollEnd) sh.scrollTop = sh.scrollHeight;
      },
      duels(st) { this.open(st, "duels"); },
    },
    // 丙：原地展開，但「這一塊」「贏了」各收成一行（點了攤開），封三招與出陣鈕排在第一屏；約戰卡一張一行
    C: {
      page(st) { cellOpen(false); insertAfterBar(duelsCard(st, true)); },
      open(st) {
        cellOpen(!st.answer);
        const c = st.card, g = c.gain;
        const place = st.place || {};
        const holder = place.control ? `${SIDE[place.control].slice(0, 1)}佔` : "中立";
        const them = st.side === "guan" ? "huang" : "guan";
        const blockLine = isOwn(st) ? `${SIDE[st.side]}的地方・${SIDE[them]}推到 ${c.bars.theirs}／100`
          : `${holder}・${SIDE[st.side].slice(0, 1)} ${c.bars.mine}／${SIDE[them].slice(0, 1)} ${c.bars.theirs}・還差 ${c.to_flip} 易手`;
        const gainLine = `進度 +${g.push}・貢獻 +${g.contribution}・分紅約 ${g.dividend}`;
        const open = st.openAll ? " open" : "";
        const body = st.answer ? answerSecs(st, true)
          : `<details class="sx-det"${open}><summary><b>這一塊</b><span>${esc(blockLine)}</span></summary>${blockSec(st, { head: false })}</details>`
            + (isOwn(st) ? "" : `<details class="sx-det"${open}><summary><b>贏了</b><span>${esc(gainLine)}</span></summary>${gainSec(st, { head: false })}</details>`);
        insertAfterBar(`<div class="card act-sortie" id="sx-panel">${topLine(st)}${body}${sealSec(st)}</div>` + (st.answer ? "" : duelsCard(st, true)));
        reveal(document.getElementById("sx-panel"));
      },
      duels(st) { cellOpen(false); insertAfterBar(duelsCard(st, true)); reveal(document.getElementById("sx-duels")); },
    },
  };
  const openCount = (st) => st.duels.filter((d) => d.status === "open" || d.status === "answered").length;
  function insertAfterBar(html) {
    document.querySelectorAll("#sx-panel, #sx-duels, #sx-bg").forEach((e) => e.remove());
    const bar = document.querySelector("#page > .act-bar");
    bar.insertAdjacentHTML("afterend", html);
  }
  function badge(st) {
    const n = openCount(st);
    const el = cell();
    if (el && n && !el.querySelector(".sx-badge")) el.insertAdjacentHTML("beforeend", `<i class="sx-badge" aria-label="${n} 張約戰">${n}</i>`);
  }

  const SX = {
    st: null,
    async boot(version) {
      const m = await fetch("/api/main").then((r) => r.json());
      const ms = await fetch("/api/map/state").then((r) => r.json());
      window.fetch = () => new Promise(() => {}); // 輪詢不回：注入的東西不會被重畫掉
      document.head.insertAdjacentHTML("beforeend", `<style id="sx-css">${CSS}</style>`);
      const card = m.sortie_card;
      const places = ms.places || {};
      const place = card ? (Array.isArray(places) ? places.find((p) => p.id === card.block) : places[card.block]) : null;
      this.st = { v: version, m, card, duels: m.sorties || [], side: ms.faction, place, now: Date.now() / 1000, picked: [] };
      this.v = V[version];
      this.v.page(this.st);
      return { card: !!card, duels: this.st.duels.length, side: ms.faction, why: card && card.why_not };
    },
    open(extra = {}) { Object.assign(this.st, extra); this.v.open(this.st); return this.measure(); },
    seal(moves, extra = {}) { Object.assign(this.st, extra, { picked: moves }); this.v.open(this.st); return this.measure(); },
    duels() { this.v.duels(this.st); return this.measure(); },
    // 按了約戰卡上的「應戰」：同一個封三招，卡頂換成應戰・那一塊
    answer(moves = [], extra = {}) {
      const d = this.st.duels.find((x) => x.can_answer);
      if (!d) return { answer: null };
      Object.assign(this.st, extra, { answer: d, picked: moves });
      this.v.open(this.st);
      return this.measure();
    },
    measure() {
      const p = document.getElementById("sx-panel") || document.getElementById("sx-duels");
      const tabs = document.querySelector(".tabs").getBoundingClientRect().top;
      const r = p ? p.getBoundingClientRect() : null;
      const go = document.querySelector("#sx-panel .sx-go");
      const g = go ? go.getBoundingClientRect() : null;
      const clipped = [...document.querySelectorAll("#sx-panel button, #sx-duels button, #sx-panel .sx-h span, #sx-duels .sx-at")]
        .filter((e) => e.scrollWidth > e.clientWidth + 0.5).map((e) => e.textContent.trim());
      return { scrollY, hscroll: document.documentElement.scrollWidth - innerWidth, panelTop: r && Math.round(r.top), panelBottom: r && Math.round(r.bottom),
               panelHeight: r && Math.round(r.height), tabsTop: Math.round(tabs), goTop: g && Math.round(g.top), goBottom: g && Math.round(g.bottom), clipped };
    },
  };
  window.SX = SX;
})();
