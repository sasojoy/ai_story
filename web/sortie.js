/* 天下大勢的網頁前端：出陣約戰的封招與前往（全部拆包第 66 批從 app.js 切出來）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 */
"use strict";

  // ── 出陣約戰（丙；畫的部分在 main.js 的 sortiePanelHtml）──
  // 封三招挑一招（再點同一招取消）：只換那一張卡（#sortie-panel 的 outerHTML），不重畫整頁（「剛剛」的浮現動畫不重播）
  function sortieMove(round, move) {
    const pick = (S.sortiePick || []).slice(0, SX_ROUNDS.length);
    pick[round] = pick[round] === move ? null : move;
    S.sortiePick = pick;
    const panel = document.getElementById("sortie-panel");
    if (panel) panel.outerHTML = sortiePanelHtml(S.main);
    else renderPage();
  }
  // 封好三招的那一顆：應戰那一張送 sortie_answer（{id, moves}），出陣送 sortie_go（{moves}）；三招沒挑滿不送（鈕本來就灰著）
  async function sortieSend() {
    const moves = (S.sortiePick || []).slice(0, SX_ROUNDS.length);
    if (moves.length < SX_ROUNDS.length || !moves.every(Boolean)) return;
    const d = sortieAnswering(S.main);
    if (d) await sortieDo("sortie_answer", { id: d.id, moves });
    else if (sortieCardOn(S.main) && !S.main.sortie_card.why_not) await sortieDo("sortie_go", { moves });
  }
  // 貼、應、同去：伺服器回來之後卡收起、挑的招清掉，「剛剛」照伺服器寫的那一則（被擋下來是一句提示），捲回最上面看結果（同 choose）
  async function sortieDo(op, body) {
    await busy(async () => {
      const r = await api(`/api/do/${op}`, body);
      S.wheelSel = null;
      S.sortieAnswer = null;
      S.sortiePick = [];
      applyMain(r.main);
      window.scrollTo({ top: 0, behavior: "smooth" });
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      if (text) toast(text);
    });
  }
  // 別區那一張的「前往 N 分」：照現有的移動走（同新手目標的「去做」）——移動清單上有往那一塊的路就展開移動、讓那一條發光，
  // 沒有（不相鄰）就開輿圖那一處的卡（步行、疾行的鈕在卡上，同江湖頁小地圖點一處）
  function sortieTravel(loc) {
    const id = `move:${loc}`, hit = (x) => x === id || x.startsWith(`${id}:`); // 疾行的 id 後面多接走法
    if ((S.main.options || []).some((o) => hit(o.id))) {
      S.sortieAnswer = null;
      S.wheelSel = "move";
      S.glowRoute = id; // 往那一處的那一條發光：記在狀態裡，重畫、摺疊 toggle 都保得住（FB-9001）
      renderPage();
      revealMoveCard();
      return;
    }
    mapGoto(loc);
    return goTab("map");
  }

  // ── 出陣約戰（減法季批 3b，整合設計 4.3；畫面照企劃者 2026-10-28 在對比圖裡選的丙：docs/superpowers/specs/2026-10-28-出陣約戰網頁-草圖/）──
  // 約戰開著時（m.sortie_card）行動列「出陣」那一格（選項 id 照留 act:train）按了伺服器只回一句「封好三招再出陣」：網頁不送它，點了在行動列底下
  // 原地展開「出陣前那張卡」（同探索三選一：S.wheelSel 記 SX_OPEN，再點收起）。灰著也點得開，卡底那顆鈕寫為什麼（等對面來約、冷卻、次數、體力）。
  // 例外照舊：截糧的運糧隊正經過（convoy_at）時直接打運糧隊；散人、不在爭奪之列照舊點了說整句。
  // 卡上「這一塊」「贏了」各收成一行（點了攤開，開合記在 S.sortieFold），封三招三排各四招（S.sortiePick），三招都挑了底鈕才亮、送 sortie_go。
  // 約戰卡（m.sorties）一張一行：應戰（打開同一張封三招的卡，S.sortieAnswer 記那一張，送 sortie_answer）、同去（sortie_join）、
  // 別區的「前往 N 分」（照現有的移動：移動清單上有那一條就展開移動，沒有就開輿圖那一處的卡）。
  // 陣營名、窗幾分鐘、體力都照伺服器給的（sortie_card.sides、window_minutes、cost、answer_stamina；約戰卡自己也帶 sides、answer_stamina，
  // 站的地方不是區塊時沒有出陣卡，FB-9003），不寫死。新寫的字都待 joy 潤
  // （一行一個 const：測試的 konst 照「const 名字」切）
  const SX_OPEN = "sortie";
  const SX_ROUNDS = ["一", "二", "三"];
  const SX_RETREAT = "撤退"; // sortie_duel.RETREAT：那一招的字淡一點
  const SX_MOVES = ["強攻", "固守", "奇襲", "撤退"]; // 伺服器沒給出陣卡（站的地方不是區塊）時應戰用的招：Config.sortie.moves 的預設
  const SX_COUNTER = "固守剋強攻・強攻剋奇襲・奇襲剋固守"; // tactics.counter
  const SX_RETREAT_NOTE = "撤退：這一回合認輸，少扣七成氣血。"; // Config.sortie.retreat_toll 0.3
  const SX_ALLY = "同袍", SX_SELF = "自己", SX_FOE = "對面"; // 約戰卡的小章：同一邊的、自己貼的；卡上沒有陣營名時的對面
  const SX_MINE_WAIT = "等人應戰", SX_VOID = "沒打成";
  const SX_YOU = "你已應戰", SX_JOINED = "已經同去了"; // sortie_duel.WHY_YOU、WHY_JOINED：不是灰的原因，是這一場你已經在裡面了
  const sxMins = (sec) => Math.max(1, Math.ceil((Number(sec) || 0) / 60));
  const sxLive = (d) => d.status === "open" || d.status === "answered";
  // 出陣那一格是不是打開出陣卡的鈕：約戰開著（伺服器給了卡）、運糧隊沒在經過
  function sortieCardOn(m) {
    return !!(m.sortie_card && !m.sortie_card.convoy_at);
  }
  // 正在應的那一張（還應得了才算；別人先應了、窗過了、走開了就收起，見 setMain）
  function sortieAnswering(m) {
    return S.sortieAnswer ? (m.sorties || []).find((d) => d.id === S.sortieAnswer && d.can_answer) || null : null;
  }
  // 看的人這一邊：卡上給的是對面那一條是哪一軍（交戰兩軍只有兩邊，另一個就是自己）
  function sxMine(c) {
    return Object.keys(c.sides || {}).find((k) => k !== c.bars.theirs_side) || "";
  }
  // 陣營的名字：約戰卡自己帶的 sides（站的地方不是區塊就沒有出陣卡，豪族塢堡、南華觀……，FB-9003），再來是出陣卡的 sides（都是劇本的陣營名）；
  // 兩邊都沒有（在路上）才寫「對面」
  function sxSide(m, side, d) {
    const c = m.sortie_card;
    return ((d && d.sides) || (c && c.sides) || {})[side] || SX_FOE;
  }
  // 「這一塊」收起來的那一行：歸誰・兩條・還差多少易手；自家的地方寫對面推到多少
  function sxBlockLine(c) {
    const sides = c.sides || {}, me = sxMine(c), them = c.bars.theirs_side;
    const first = (s) => String(sides[s] || "").slice(0, 1);
    if (!c.gain) return `${sides[me] || ""}的地方・${sides[them] || ""}推到 ${c.bars.theirs}／100`;
    return `${c.holder ? `${first(c.holder)}佔` : "中立"}・${first(me)} ${c.bars.mine}／${first(them)} ${c.bars.theirs}・還差 ${c.to_flip} 易手`;
  }
  // 「這一塊」攤開：兩條（自己那一條疊上這一程推得到的地方）與幾顆小籤
  function sxBars(c) {
    const sides = c.sides || {}, me = sxMine(c), them = c.bars.theirs_side;
    const gain = c.gain && !c.why_not ? Math.max(0, Math.min(Number(c.gain.push), 100 - c.bars.mine)) : 0;
    const row = (side, v, mine) => `<div class="sf-row side-${esc(side)}${mine ? " mine" : ""}"><span class="sf-name">${esc(sides[side] || "")}</span>`
      + `<span class="sf-bar"><i class="sf-fill" style="width:${pct(v, 100)}%"></i>${mine && gain ? `<i class="sf-gain" style="left:${pct(v, 100)}%;width:${pct(gain, 100)}%"></i>` : ""}</span>`
      + `<span class="sf-num">${Number(v)}</span></div>`;
    const foes = c.foe_pushing ? `對面 ${c.foe_pushing} 人在推` : "對面沒人在推";
    const chips = !c.gain ? [`${sides[them] || ""}推滿 100 才翻走這裡・還差 ${c.to_flip}`, foes]
      : [`推滿 100 易手・還差 ${c.to_flip}`, foes, c.allies ? `同袍 ${c.allies} 人・集火 +${Math.round(c.focus_bonus * 100)}%` : "同袍還沒人來",
        c.convoy_at ? `運糧隊「${c.convoy_at}」正經過` : ""].filter(Boolean);
    return row(me, c.bars.mine, true) + row(them, c.bars.theirs, false) + `<div class="sf-chips">${chips.map((t) => `<span class="sf-chip">${esc(t)}</span>`).join("")}</div>`;
  }
  // 應戰卡的「這一塊」（FB-9004）：寫這一場牽動什麼——約戰那一軍在那一塊推到幾、離翻走（沒人佔的寫拿下）還差多少，守住了拉回它。
  // 資料是約戰卡自己帶的（d.bars：mine 看的人這一邊、theirs 約戰那一軍；d.to_flip、d.foe_pushing、d.holder），不是看的人自己推這一塊
  // （以前借出陣卡的 sxBars，小籤寫的是自己「推滿 100 易手・還差 75」「同袍還沒人來」，跟這一場無關）。新寫的字待 joy 潤
  const sxWin = (d) => (d.holder ? "翻走" : "拿下");
  function sxDutyLine(m, d) {
    return `${sxSide(m, d.attacker_side, d)} ${d.bars.theirs}／100・還差 ${d.to_flip} ${sxWin(d)}`;
  }
  function sxDutyBars(m, d) {
    const them = d.attacker_side, me = Object.keys(d.sides || {}).find((k) => k !== them) || "";
    const row = (side, v, mine) => `<div class="sf-row side-${esc(side)}${mine ? " mine" : ""}"><span class="sf-name">${esc(sxSide(m, side, d))}</span>`
      + `<span class="sf-bar"><i class="sf-fill" style="width:${pct(v, 100)}%"></i></span><span class="sf-num">${Number(v)}</span></div>`;
    const chips = [`${sxSide(m, them, d)}推滿 100 才${sxWin(d)}・還差 ${d.to_flip}`, d.foe_pushing ? `對面 ${d.foe_pushing} 人在推` : "對面沒人在推", "守住了能拉回它的進度"];
    return row(me, d.bars.mine, true) + row(them, d.bars.theirs, false) + `<div class="sf-chips">${chips.map((t) => `<span class="sf-chip">${esc(t)}</span>`).join("")}</div>`;
  }
  // 「贏了」攤開：推一程、貢獻、戰利、易手分紅、軍令、戰書（照險勝估，伺服器算好的數字）
  function sxGain(c) {
    const g = c.gain, after = c.bars.mine + g.push, left = Math.max(0, c.to_flip - g.push);
    const rows = [
      ["推一程", `<b>+${Number(g.push)}</b><small>${left > 0 ? `→ ${after}，離易手還差 ${left}` : "推滿易手"}</small>`, "up"],
      ["貢獻", `<b>+${Number(g.contribution)}</b>${g.rank_next != null ? `<small>離下一階還差 ${Number(g.rank_next)}</small>` : ""}`, "up"],
      g.loot ? ["戰利", `<b>${esc(g.loot)}</b>`, ""] : null,
      ["易手分紅", `<b>約 ${Number(g.dividend)} 銀兩</b><small>推滿那一刻照推的份分</small>`, ""],
      ["軍令", g.order_match ? "<b>正是本週攻城軍令</b>" : '<small class="sx-only">不是本週軍令要的地方</small>', ""],
      ["戰書", g.letter_gap > 0 ? `<b>還差 ${Number(g.letter_gap)}</b><small>推到 ${c.bars.mine + g.letter_gap} 可下戰書</small>` : "<b>已可下戰書</b>", ""],
    ].filter(Boolean);
    return `<dl class="sx-gl">${rows.map(([k, v, cls]) => `<dt>${k}</dt><dd${cls ? ` class="${cls}"` : ""}>${v}</dd>`).join("")}</dl>`;
  }
  // 應戰那一張「守住了」攤開：伺服器沒給數字（應戰前看得到的獎勵是之後的事），照設計寫幾句
  function sxKeep(m, d) {
    const rows = [["這一塊", `<b>${esc(sxSide(m, d.attacker_side, d))}的進度被拉回</b>`], ["貢獻", "<b>記一筆守城功</b>"],
      ["經驗心得", "<b>同出陣打贏的那一份</b>"], ["輸了", '<small class="sx-only">內傷加重，出陣與應戰要多等一陣</small>']];
    return `<dl class="sx-gl">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("")}</dl>`;
  }
  // 收成一行、點了攤開的那一段（<details>；開合記在 S.sortieFold，輪詢重畫照它補回）
  function sxFold(sec, head, line, body) {
    const open = !!(S.sortieFold && S.sortieFold[sec]);
    return `<details class="sx-det" data-sec="${sec}"${open ? " open" : ""}><summary><b>${head}</b><span>${esc(line)}</span></summary><div class="sx-sec">${body}</div></details>`;
  }
  // 卡底那顆鈕：灰著寫為什麼（冷卻寫「冷卻中・還要 N 分」），沒挑滿寫還要挑幾招，挑滿了寫封的三招
  function sxGo(c, d) {
    const picked = (S.sortiePick || []).filter(Boolean);
    const need = SX_ROUNDS.length - picked.length;
    const stamina = d ? (d.answer_stamina != null ? d.answer_stamina : c && c.answer_stamina) : null; // 約戰卡自己帶的（站的地方不是區塊沒有出陣卡，FB-9003）
    const sub = d ? `${stamina != null ? `體力 ${stamina}・` : ""}今日還能應戰 ${d.answers_left} 次`
      : `體力 ${c.cost}・今日還能 ${c.left_today} 次`;
    const why = d || !c.why_not ? "" : c.cooldown_until && /^還要/.test(c.why_not) ? `冷卻中・${c.why_not}` : c.why_not;
    const ready = !why && need <= 0;
    const head = why || (need > 0 ? `還要挑 ${need} 招` : d ? "封好三招，應戰" : "封好三招，出陣");
    return `<button class="btn primary sx-go" data-act="sortie-send"${ready ? "" : " disabled"}><b>${esc(head)}</b><small>${esc(ready ? `${picked.join("・")}・${sub}` : sub)}</small></button>`;
  }
  // 封三招：一回合一排四招（.seg），貼不了時淡掉、按不下去；自家的地方不貼約戰，寫一句守就是應戰
  function sxSeal(m, c, d) {
    if (!d && !c.gain) {
      return `<div class="sx-sec"><p class="sx-h"><b>封三招</b><span>這裡不貼約戰</span></p>`
        + `<p class="sx-own">這裡是${esc((c.sides || {})[sxMine(c)] || "")}的地方：守就是應戰。對面在這一區約戰時，約戰卡上按「應戰」、封三招守住它。</p>${sxGo(c, d)}</div>`;
    }
    const moves = (c && c.moves) || SX_MOVES, picked = S.sortiePick || [];
    const shut = !d && !!c.why_not;
    const rounds = SX_ROUNDS.map((n, i) => `<div class="sx-round"><span class="sx-n">第${n}回合</span><div class="seg" role="group" aria-label="第${n}回合">${moves.map((mv) =>
      `<button class="${picked[i] === mv ? "on" : ""}${mv === SX_RETREAT ? " sx-back" : ""}" data-act="sortie-move" data-round="${i}" data-move="${esc(mv)}" aria-pressed="${picked[i] === mv}"${shut ? " disabled" : ""}>${esc(mv)}</button>`).join("")}</div></div>`).join("");
    const when = d ? `${sxMins(d.expires_in)} 分後開打` : `${c.window_minutes} 分鐘後開打`;
    return `<div class="sx-sec${shut ? " sx-dim" : ""}"><p class="sx-h"><b>封三招</b><span>${SX_COUNTER}</span></p>${rounds}`
      + `<p class="sx-note">${SX_RETREAT_NOTE}封了就不能改，${when}，戰報送到。</p>${sxGo(c, d)}</div>`;
  }
  // 出陣前那張卡（出陣那一格點開的，S.wheelSel）或應戰那一張（約戰卡上按「應戰」，S.sortieAnswer）；都沒開是空字串
  function sortiePanelHtml(m) {
    const c = m.sortie_card || null, d = sortieAnswering(m);
    if (!d && !(sortieCardOn(m) && S.wheelSel === SX_OPEN)) return "";
    let top, body;
    if (d) {
      top = `<p class="sx-top"><b>應戰・${esc(d.place)}</b><span>${esc(d.attacker)}約戰・還有 ${sxMins(d.expires_in)} 分</span></p>`;
      // 「這一塊」寫的是這一場牽動的那一塊（約戰卡自己帶的 bars、to_flip，站在哪裡都一樣，FB-9004）；沒帶（舊資料）就只寫地名
      body = (d.bars ? sxFold("block", "這一塊", sxDutyLine(m, d), sxDutyBars(m, d)) : `<p class="sx-flat"><b>這一塊</b><span>${esc(d.place)}</span></p>`)
        + sxFold("keep", "守住了", "拉回對面的進度・記貢獻・經驗心得", sxKeep(m, d));
    } else {
      const g = c.gain;
      top = `<p class="sx-top"><b>出陣・${esc(c.place)}</b><span>今日還能 ${Number(c.left_today)} 次・體力 ${Number(c.cost)}</span></p>`;
      body = sxFold("block", "這一塊", sxBlockLine(c), sxBars(c))
        + (g ? sxFold("gain", "贏了", `進度 +${g.push}・貢獻 +${g.contribution}・分紅約 ${g.dividend}`, sxGain(c)) : "");
    }
    return `<div class="card act-sortie" id="sortie-panel">${top}${body}${sxSeal(m, c, d)}</div>`;
  }
  // 約戰卡排的先後（伺服器照新的在前）：應得了的、同去得了的、自己貼的、其他還沒打的、結算完的
  function sxRank(d) {
    return !sxLive(d) ? 4 : d.can_answer ? 0 : d.can_join ? 1 : d.role === "mine" ? 2 : 3;
  }
  // 約戰卡一張一行：小章（陣營／同袍／自己）、誰約戰哪裡、還有幾分、右邊一顆鈕（或這一場的狀態）；灰的原因放不進鈕，寫在那一行底下
  function sxRow(m, d) {
    const live = sxLive(d), join = d.role === "join";
    const tag = join ? SX_ALLY : d.role === "mine" ? SX_SELF : sxSide(m, d.attacker_side, d);
    const far = live && d.role !== "mine" && !d.same_region && d.travel_minutes != null && !d.can_answer && !d.can_join;
    const state = (t) => `<span class="sx-state">${esc(t)}</span>`;
    let right, why = "";
    if (!live) right = state(d.status === "void" ? SX_VOID : d.result || "");
    else if (d.role === "mine") right = state(`${d.defender ? `${d.defender}應戰` : SX_MINE_WAIT}・剩 ${sxMins(d.expires_in)} 分`);
    else if (d.can_answer) right = `<button class="btn small primary" data-act="sortie-answer" data-id="${esc(d.id)}">應戰</button>`;
    else if (d.can_join) right = `<button class="btn small primary" data-act="sortie-join" data-id="${esc(d.id)}">同去</button>`;
    else if (far) right = `<button class="btn small ghost" data-act="sortie-far" data-id="${esc(d.block)}">前往 ${Number(d.travel_minutes)} 分</button>`;
    else if (d.why_not === SX_YOU || d.why_not === SX_JOINED) right = state(d.why_not);
    else { right = `<button class="btn small" disabled>${join ? "同去" : "應戰"}</button>`; why = d.why_not; }
    const left = live && d.role !== "mine" ? `<span class="sx-left">${sxMins(d.expires_in)} 分</span>` : "";
    return `<div class="sx-drow${far ? " sx-far" : ""}${live ? "" : " sx-done"}"><span class="sx-tag side-${esc(d.attacker_side)}">${esc(tag)}</span>`
      + `<span class="sx-dt"><b>${esc(d.attacker)}</b>約戰<span class="sx-pl">${esc(d.place)}</span></span>${left}${right}</div>${why ? `<p class="sx-why">${esc(why)}</p>` : ""}`;
  }
  // 約戰卡（m.sorties）：一張一行排在行動列底下，標題寫幾張、幾張在別區
  function sortieDuelsHtml(m) {
    const list = (m.sorties || []).slice().sort((a, b) => sxRank(a) - sxRank(b));
    if (!list.length) return "";
    const live = list.filter(sxLive);
    const far = live.filter((d) => d.role !== "mine" && !d.same_region).length;
    const head = `${list.length} 張${far ? `・${far} 張在別區` : ""}${live.length ? "・窗滿就開打" : ""}`;
    return `<div class="card sx-duels" id="sortie-duels"><p class="sx-h"><b>約戰</b><span>${esc(head)}</span></p>${list.map((d) => sxRow(m, d)).join("")}</div>`;
  }
