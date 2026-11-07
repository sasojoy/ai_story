/* 天下大勢的網頁前端：全服決戰的集結、戰場與戰局條（全部拆包第 67 批從 main.js 切出來）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 */
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

  // 決戰集結時還沒參戰的人（FB-105）：加入（自己陣營那一邊）、散人的臨時投效。以前跟求見、拜師一起收在「此地還能做」的摺疊裡，
  // 不打開摺疊的人整場不在名單上（集結只有現實 30 分鐘）。現在畫在場景卡戰場名字那一行（musterScene），摺疊與選項列都不再列一次；
  // 鈕旁邊一小句說在這裡報名（MUSTER_NOTE），每一場決戰都看得到，不靠只說一次的提示。集結那一句（「選擇陣營加入；集結期間照常行動。」）
  // 是戰鬥引擎寫的，另一條線正在改那一段，這裡不動它（fix-1008 裁示）。
  // 只認「全都按得下去」的時候：已經加入或投效過的人有一顆是灰的「已加入」，照舊收在摺疊裡，畫面跟以前一樣；打不了這場仗的人
  // （不是交戰的一方、不在決戰的大區）選單上本來就沒有這幾顆。開打了才到的散人還能投效，也一樣畫在名字那一行（開打後的「加入戰局」
  // battle:join_late 是選單上唯一的一顆，本來就看得到，不在這裡：所以 MUSTER_JOIN 結尾要有冒號）。
  // 場景卡沒畫的時候不搬，照舊留在選單上（摺疊或選項列），鈕永遠不會不見：在路上（在路上的人加入不了，選單上本來就沒有這幾顆；
  // 萬一有，路上的場景卡收成兩行、不畫名字那一行），以及序章師父說話、草廬的場景卡不畫的那幾步（masterTalks）
  // 名下有同伴的人按了加入（或晚到、臨時投效）之後挑誰隨你出陣（battle:escort:*，歷史武將同行）：還沒加入，一樣畫在這裡（FB-360）
  const MUSTER_JOIN = /^battle:(join|enlist|escort):/;
  // 鈕旁邊那一小句（待 joy 潤）：加入的那一顆在名字右邊，這句夾在名字與鈕中間、指向它；散人的兩顆在名字底下另起一行，這句在名字右邊、往下指。
  // 放不下時省略號收尾（style.css 的 .muster-note），名字那一行不因此變高、不折行。箭頭另外放（MUSTER_ARROW），讀螢幕的軟體不唸它（aria-hidden）
  // 挑同伴那一步（escort，FB-360）：一顆一行（鈕上寫份量與氣血，四顆擠一排放不下），那一小句說挑了才算加入（待 joy 潤）
  const MUSTER_NOTE = { join: "報名在這裡", enlist: "挑一邊臨時投效，只算這一場", escort: "挑一位隨你出陣，挑了才算加入" };
  const MUSTER_ARROW = { join: "→", enlist: "↓", escort: "↓" };
  // 序章：師父在說話（框顯示著）、眼前又沒有事件時，草廬那張地點描寫卡不畫——它是靜態的，而師父的整段話要用這塊地方（T7 審查 I1）
  // 出師那一段路（在路上）不算：第一條路的說明卡要留著（T7 審查 N2）。pageJianghu 照它決定畫不畫場景卡，musterJoins 照它決定搬不搬加入的鈕
  const masterTalksOf = (m) => !!pro() && !!m.guide && !m.on_road && !m.options.some((o) => o.id.startsWith("choice:"));
  function musterJoins(m) {
    if (m.on_road || masterTalksOf(m)) return [];
    const joins = m.options.filter((o) => MUSTER_JOIN.test(o.id));
    return joins.length && joins.every((o) => o.enabled) ? joins : [];
  }
  // 場景卡（伺服器的 Markdown）第一段是戰場名字（「**廣宗決戰**」）：包成一行，名字、那一小句、加入的鈕排在同一行；散人臨時投效的
  // 兩顆字多，另起一行排在名字底下（.wide，鈕上只寫「臨時投效【官軍】」，「只算這一場」寫在那一小句裡）。認不出第一段就排在卡片最上面。
  // 那一小句用 aria-describedby 接到那一排鈕上（一頁只有一張場景卡，id 不會重複）。
  // FB-553：同一州兩場以上自己這一邊的攻城一起集結，加入鈕一場一顆、鈕上寫是哪一場（字長），兩顆擠在名字那一行把整頁撐出橫捲
  // （375 寬 488px）：兩顆以上照挑同伴那一步，另起一行、一顆一行（.pick），那一小句往下指；一顆的照舊在名字右邊
  function musterScene(m, scene) {
    const joins = musterJoins(m);
    if (!joins.length) return scene;
    const kind = joins.some((o) => o.id.startsWith("battle:escort:")) ? "escort"
      : joins.some((o) => o.id.startsWith("battle:enlist:")) ? "enlist" : "join";
    const wide = kind === "enlist";
    const stacked = kind === "escort" || (kind === "join" && joins.length > 1);
    const note = `<span class="muster-note" id="muster-note">${esc(MUSTER_NOTE[kind])}<span aria-hidden="true"> ${stacked ? MUSTER_ARROW.escort : MUSTER_ARROW[kind]}</span></span>`;
    const cls = wide ? " wide" : stacked ? " pick" : "";
    const row = `<div class="options muster-join${cls}" role="group" aria-label="參戰" aria-describedby="muster-note">${joins.map((o) =>
      `<button class="btn small primary" data-act="choose" data-id="${esc(o.id)}"><span>${esc(wide ? optParts(o)[0] : o.label)}</span></button>`).join("")}</div>`;
    const head = /^<p>([\s\S]*?)<\/p>\n?/.exec(scene);
    return head ? `<div class="muster-head"><p>${head[1]}</p>${note}${row}</div>\n${scene.slice(head[0].length)}` : `<div class="muster-head">${note}${row}</div>\n${scene}`;
  }

  // ── 只能觀戰的人：開打中的全服決戰收成一行（FB-120）──
  // 開打後 Game.scene_text 給只能觀戰的人的是「戰場＋分隔線＋自己眼前的事」，戰場那一塊有名字、「【幕】（第 N／M 回合・…）」、最近五段
  // 戰報（放手一搏的原文、模型的故事）與觀戰的原因，QA 量到師父的框被擠到 1130、行動列 1226 以下（分頁列頂 756）。沒在打這一場的人
  // （人不在決戰的大區、沒加入、沒臨時投效：伺服器才會在戰場底下接分隔線）那一塊收成一行，點了攤開、底下一顆「收起戰場」。
  // 人在決戰的大區、還沒投效的散人也有分隔線（FB-109），可是名字那一行有投效的鈕（musterJoins），不收；
  // 攤開記的是戰場的名字（S.battleOpen：回合每輪都在變，記名字輪詢才不會收回去），自己收起或這一場打完（場景裡沒有開打中的回合）才清掉。
  // 參戰的人照舊：在場時整個畫面就是戰場（沒有分隔線）；離開大區、倒下的人最後一句是 BATTLE_MINE。集結時沒有回合數，歸 FB-107 收
  // 集結那一句；序章裡引擎不畫戰場（FB-113）。只認伺服器給的字（戰鬥引擎 _battle_scene_text 的寫法）：兩個正規式的測試在
  // tests/web/test_jianghu_page_web.py，用真的戰場驗，寫法變了那裡就紅
  // BATTLE_ROUND：開打後的回合數（「【圍城日久】（第 4／9 回合・已送出…）」），集結時沒有；
  // BATTLE_MINE：參戰者看戰場的那一句（離開了大區、倒下了），他是這一場的人，不收
  const BATTLE_ROUND = /（第\s*(\d+)\s*／\s*\d+\s*回合/;
  const BATTLE_MINE = /這回合不出手|你已經倒下/;
  // 收成一行時接在回合數後面的那兩三個字、攤開之後戰場底下那一顆（都待 joy 潤）
  const BATTLE_PEEK = "點開看";
  const BATTLE_SHUT = "收起戰場";
  // 只能觀戰、正在開打：{ block 分隔線之前的戰場那一塊, rest 分隔線起的其餘, name 戰場名字, round 第幾回合 }；不是就 null
  function battleWatch(m) {
    const scene = (m && m.scene) || "";
    const cut = scene.search(/<hr\s*\/?>/);
    if (cut < 0 || m.on_road) return null;
    const block = scene.slice(0, cut);
    const round = BATTLE_ROUND.exec(block), head = /^<p>([\s\S]*?)<\/p>/.exec(block);
    // 參戰者那一句只看戰場那一塊的最後一段：引擎把看戰場的原因（觀戰、離開大區、倒下）寫在最後；中間的戰報有放手一搏的原文與
    // 模型的故事，有人寫「你已經倒下」也不能讓每個觀戰的人的戰場整段攤開（審查 M1）
    const last = block.slice(block.lastIndexOf("<p>"));
    if (!round || !head || BATTLE_MINE.test(last)) return null;
    return { block, rest: scene.slice(cut), name: head[1].replace(/<[^>]*>/g, "").trim(), round: Number(round[1]) };
  }
  function battleScene(m) {
    if (!BATTLE_ROUND.test(m.scene || "")) S.battleOpen = null; // 這一場打完了（或還在集結、沒有決戰）：下一場照舊先收著
    const w = battleWatch(m);
    if (!w || musterJoins(m).length) return m.scene;
    if (S.battleOpen === w.name) {
      return `${w.block}<p class="battle-shut"><button class="linkish" data-act="battle-shut" aria-expanded="true">${BATTLE_SHUT}</button></p>\n${w.rest}`;
    }
    // 名字是伺服器 Markdown 轉好的 HTML 拿掉標籤：已經跳脫過，不再跳脫一次
    return `<p class="battle-fold" data-act="battle-open" role="button" tabindex="0" aria-expanded="false">${w.name}　第 ${w.round} 回合・${BATTLE_PEEK}</p>\n${w.rest}`;
  }

  // ── 決戰的戰況一回合一段（Joy 2026-10-14「大決戰因為很多人，戰況文字沒有分回合，擠在一起玩家很難閱讀」）──
  // 引擎（engine._round_blocks）把最近五段戰況寫成「##### 第 N 回合」加一行一條的清單、新的在上。這裡把最新那一回合包成一塊整段攤開，
  // 舊的幾回合各收成一行（<details>：回合數＋那一回合誰佔上風那一句，點了攤開）；攤開了哪幾回合記在 S.roundsOpen，輪詢重畫照樣開著
  // 每一條是哪一軍的（Joy 2026-10-14「看不出誰是官軍誰是黃巾」）：引擎在開頭寫「〔官軍〕」（engine.SIDE_TAG），這裡換成那一軍顏色的
  // 小標籤、整條左邊一道那一軍的顏色（同戰局條的 side-<陣營 id>）；自己那一軍多標「我方」。認不出的名字照字留著。
  // 兩個式子寫在函式裡：測試的假瀏覽器照名字只抽函式出來
  // report：戰報頁那一場的流水號（決戰的完整戰況，Joy 2026-10-14）：每一回合都收成一行、照先後，展開了哪幾回合跟場景分開記（「r<流水號>:<回合>」）
  // 一軍這一回合發動武學的那幾句，引擎摺成一列摘要、逐人那幾句縮在它底下一層（engine._fold_war_lines，Joy 2026-10-30）：
  // 那一層畫成點開才看的 <details class="b-fold">；裡面換成 <ol>，底下 ROUND_HEAD 認回合結尾的 </ul> 才不會停在裡面那一層。開合記在 S.foldOpen
  const WAR_FOLD = /<li>(〔[^〕<]+〕)?([^\n<]*)\n<ul>\n([\s\S]*?)<\/ul>\n<\/li>/g;
  function warFolds(html, roundKey) {
    const open = S.foldOpen || (S.foldOpen = new Set());
    return html.replace(WAR_FOLD, (all, tag, head, rows) => {
      const key = `${roundKey}:${tag || head}`;
      return `<li>${tag || ""}<details class="b-fold" data-fold="${esc(key)}"${open.has(key) ? " open" : ""}><summary>${head}</summary><ol class="b-fold-lines">\n${rows}</ol></details></li>`;
    });
  }
  function roundBlocks(html, g, report) {
    const ROUND_HEAD = /<h5>第 (\d+) 回合<\/h5>\n<ul>\n([\s\S]*?)<\/ul>\n?/g;
    const SIDE_TAG = /<li>〔([^〕<]+)〕/g;
    let newest = report == null;
    const open = S.roundsOpen || (S.roundsOpen = new Set());
    const sides = {};
    if (g) for (const w of [g.left, g.right]) if (w) sides[w.name] = w;
    html = html.replace(/<h5>第 (\d+) 回合<\/h5>\n<ul>\n[\s\S]*?(?=<h5>|$)/g, (block, n) => warFolds(block, report == null ? n : `r${report}:${n}`));
    return html.replace(ROUND_HEAD, (all, n, rows) => {
      const items = rows.replace(SIDE_TAG, (tag, name) => {
        const w = sides[name];
        return w ? `<li class="b-side side-${esc(w.id)}${w.mine ? " mine" : ""}"><span class="b-tag">${name}${w.mine ? "・我方" : ""}</span>` : tag;
      });
      const list = `<ul class="b-lines">\n${trailMoves(items)}</ul>`;
      if (newest) {
        newest = false;
        return `<div class="b-round latest"><p class="b-rhead">第 ${n} 回合</p>${list}</div>\n`;
      }
      const first = /<li>([\s\S]*?)<\/li>/.exec(items);
      const gist = first ? first[1].replace(/<[^>]*>/g, "") : "";
      const key = report == null ? n : `r${report}:${n}`;
      return `<details class="b-round" data-round="${key}"${open.has(key) ? " open" : ""}><summary><b>第 ${n} 回合</b>${gist ? `<span>${gist}</span>` : ""}</summary>${list}</details>\n`;
    });
  }

  // ── 決戰的即時戰局條（Joy 2026-10-10 轉玩家反饋：「有辦法看即時戰局？那個推進多少我都不知道是啥意思」）──
  // 資料是引擎的 battle_instance.gauge：拔河，左邊是看的人那一邊；lean 是往左邊那一方偏多少（0～100）。旗子畫在 100−lean：
  // 誰佔上風，旗子就被拉到誰那一頭。淺色的兩截是分勝負的那一段（大勝），兩道細線是當場分出勝負的線（偏離中線 decisive），
  // 條上那一道色帶是上一回合旗子從哪裡移到哪裡；底下一格一回合，塗上那一回合佔上風那一邊的顏色。數字只寫在條的兩端（幾比幾）。
  function gaugeHtml(g) {
    if (!g) return "";
    const x = (lean) => 100 - lean;
    const who = (s) => (s === "left" ? g.left : g.right);
    const tint = (w) => `side-${esc(w.id)}${w.mine ? " mine" : ""}`;
    const zones = g.zones.map((z) => `<i class="g-zone ${z.side} ${tint(who(z.side))}" style="left:${x(z.to)}%;width:${z.to - z.from}%"><span>${esc(z.label)}</span></i>`).join("");
    const ticks = [50 - g.decisive, 50 + g.decisive].map((v) => `<i class="g-tick" style="left:${v}%"></i>`).join("");
    const last = g.rounds.length ? g.rounds[g.rounds.length - 1] : null;
    const trail = last && last.from !== last.to
      ? `<i class="g-trail ${tint(who(last.side))}" style="left:${Math.min(x(last.from), x(last.to))}%;width:${Math.abs(last.to - last.from)}%"></i>` : "";
    const chips = Array.from({ length: g.total }, (_, i) => {
      const r = g.rounds[i];
      const now = !r && g.phase === "active" && i + 1 === g.round;
      const cls = r ? (r.side === "tie" ? "tie" : tint(who(r.side))) : now ? "g-now" : "";
      const tip = r ? `第 ${r.n} 回合：${r.side === "tie" ? "相持" : `${who(r.side).name}佔上風`}` : now ? `第 ${i + 1} 回合：正在打` : `第 ${i + 1} 回合`;
      return `<li class="g-r ${cls}" title="${esc(tip)}">${i + 1}</li>`;
    }).join("");
    const end = (w, n, right) => `<span class="g-side ${tint(w)}">${right ? `<b>${n}</b> ` : ""}${esc(w.name)}${w.mine ? "（我方）" : ""}${right ? "" : ` <b>${n}</b>`}</span>`;
    return `<div class="gauge" role="img" aria-label="${esc(`戰局：${g.left.name} ${g.lean} 比 ${100 - g.lean} ${g.right.name}，${g.caption}`)}">`
      + `<div class="g-head">${end(g.left, g.lean, false)}${end(g.right, 100 - g.lean, true)}</div>`
      + `<div class="g-bar">${zones}${ticks}<i class="g-mid"></i>${trail}<b class="g-flag" style="left:${x(g.lean)}%"></b></div>`
      + `<ol class="g-rounds">${chips}</ol><p class="g-cap">${esc(g.caption)}</p>${meritHtml(g, tint)}</div>`;
  }
  // 本場戰功的名字（名聲 4B）：加入決戰時快照的稱號（善惡第 1 段起、名望名動一方起，r.renown）寫在名字底下第二行；
  // 第一屏放不下時 FIT_STEPS 的 merit 把第二行收掉（.fit-hide）
  const meritName = (r) => (r.renown && r.renown.length
    ? `<span class="rn-two">${esc(r.name)}<small>${esc(r.renown.join("・"))}</small></span>` : `<span>${esc(r.name)}</span>`);
  // 戰局條底下的「本場戰功」（Joy 2026-10-10 個人戰功，battle_instance.merit_board）：兩軍各列前幾名，最後一行是自己排第幾、戰功怎麼來的。
  // 集結中、還沒有人出手時不畫
  function meritHtml(g, tint) {
    const b = g.merit;
    if (!b || g.phase === "muster" || (!b.left.length && !b.right.length && !(b.me && b.me.merit))) return "";
    const col = (w, rows) => `<div class="g-mcol ${tint(w)}"><b class="g-mside">${esc(w.name)}</b>${rows.length
      ? `<ol>${rows.map((r, i) => `<li${r.mine ? ' class="mine"' : ""}><i>${i + 1}</i>${meritName(r)}<b>${r.merit}</b></li>`).join("")}</ol>`
      : '<p class="muted">還沒有人立功</p>'}</div>`;
    const me = b.me ? `<p class="g-me">你排第 ${b.me.rank}／${b.me.of}・戰功 ${b.me.merit}${b.me.parts.length ? `：${esc(b.me.parts.join("、"))}` : "（還沒出手）"}</p>` : "";
    return `<div class="g-merit"><p class="g-mtitle">本場戰功</p><div class="g-mcols">${col(g.left, b.left)}${col(g.right, b.right)}</div>${me}</div>`;
  }
  // 場景卡裡把戰局條放在戰場名字那一行底下（集結時名字那一行連著投效的鈕，見 musterScene）；收成一行的觀戰（battleScene）不放
  function withGauge(html, g, extra = "") {
    if (!g || html.startsWith('<p class="battle-fold"')) return html;
    const muster = html.startsWith('<div class="muster-head">') ? html.indexOf("</div></div>\n") : -1;
    const cut = muster >= 0 ? muster + "</div></div>\n".length : html.startsWith("<p>") ? html.indexOf("</p>") + 4 : 0;
    return html.slice(0, cut) + gaugeHtml(g) + extra + html.slice(cut);
  }
  // 決戰的回合 MVP（Joy 2026-11-03「每當一回合結束時，結算時有一個跳顯視窗華麗的展示絕招」）：伺服器挑好的 main.battle_mvp
  // （剛結算完的那一回合才有）。新的一位第一次看到時跳出視窗演他的絕招（arena_scene.js 的 mvpPlay；看過的不再自己跳），
  // 戰局條底下留一行：誰、哪一軍、絕招的名字，加一顆「再看一次」。只切 main.js 的網頁測試沒有 mvpPlay：照樣畫字、不跳
  function battleMvpHtml(m) {
    const v = m.battle_mvp, g = m.battle_gauge;
    if (!v || !g) return "";
    const names = {};
    for (const w of [g.left, g.right]) if (w && w.id) names[w.id] = { name: w.name, mine: !!w.mine };
    const side = names[v.faction];
    const who = side ? `（${esc(side.name)}${side.mine ? "・我方" : ""}）` : "";
    const move = v.move_name ? `・絕招「${esc(v.move_name)}」` : "";
    if (typeof mvpPlay === "function") setTimeout(() => mvpPlay(v, names), 0); // 整頁畫完再跳（視窗掛在 body 上）
    return `<div class="battle-mvp${side && side.mine ? " mine" : ""}"><span class="mvp-head">★ 第 ${v.round | 0} 回合首功　<b>${esc(v.name)}</b>${who}${move}</span>`
      + `<button class="btn small ghost" data-act="mvp-replay">再看一次</button></div>`;
  }
  // 攻城戰畫面（領地爭奪第三批 A，企劃者挑甲）：沿用決戰畫面，最上面那一行換成一條「攻城・地點｜守方：某某（或守將）」（main.siege，
  // engine.siege_banner；三方混戰、轉回單方、兩軍相爭的字是伺服器給的）。引擎場景第一行是 **攻城・地點**：把那一行換成這一條（不多佔一行；
  // 集結時這一條自己一行，「報名在這裡」與加入的鈕排在它底下，見 style.css）；找不到那一行就疊在最上面；收成一行的觀戰（battle-fold）不畫。
  // 每一段包成不折行的小段，只在「｜」那裡換行。
  // 排在 withGauge 之後：withGauge 認的是原本那一行 <p>，換掉之前先把戰局條插好
  function siegeStrip(html, s) {
    if (!s || html.startsWith('<p class="battle-fold"')) return html;
    const strip = `<p class="siege-strip" role="note"><span class="nb ss-title">${esc(s.title)}</span>${(s.parts || []).map((p) =>
      `<span class="ss-sep" aria-hidden="true">｜</span><span class="nb">${esc(p)}</span>`).join("")}</p>`;
    const head = `<p><strong>${esc(s.title)}</strong></p>`;
    const at = html.indexOf(head);
    return at >= 0 ? html.slice(0, at) + strip + html.slice(at + head.length) : strip + html;
  }
  // 場景卡裡的戰場那一塊。戰場面板開著（main.battle_panel，battle.js；Joy 2026-11-06 大決戰優化）時戰局條畫在面板裡，
  // 場景卡只留面板沒寫的（這一幕的字、點名、職位、完整戰報），重複的拿掉（bpTrim）
  function battleInner(m) {
    const base = musterScene(m, roundBlocks(battleScene(sceneUnderArt(m)), m.battle_gauge));
    // 自己在場上：戰局條、陣容、主將令、回合數都在面板上，場景卡只留戰報；還沒加入（要按加入、投效）的照舊整段（面板不畫戰局條）
    if (bpOn(m) && m.battle_panel.me && !base.startsWith('<p class="battle-fold"')) return bpTrim(siegeStrip(battleMvpHtml(m) + base, m.siege), m);
    return siegeStrip(withGauge(base, m.battle_gauge, battleMvpHtml(m)), m.siege);
  }
  // 攤開、收起都整頁重畫，原本有焦點的那一行（那一顆）跟著不見：焦點放回新畫出來的開關，鍵盤再按一次就收起、再攤開
  // （同戰況圖卡的 frontsTap，審查 M4）
  function battleOpen() {
    const w = battleWatch(S.main);
    S.battleOpen = w ? w.name : null;
    renderPage();
    document.querySelector("#page .battle-shut button")?.focus();
  }
  function battleShut() {
    S.battleOpen = null;
    renderPage();
    document.querySelector("#page .battle-fold")?.focus();
  }

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
  // 選單上那幾顆出招鈕面板已經畫了：選單裡的拿掉（同一顆不畫兩次）；出完招那一顆灰的「（已選擇，等其他人…）」也拿掉——面板寫了「你這一回合」
  const bpDropMoves = (menu) => menu.replace(/\s*<button class="btn[^"]*" data-act="(?:choose|opt-why)" data-id="battle:(?:act:[^"]*|waiting)"[\s\S]*?<\/button>/g, "");

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
  async function battleClick(act, el, ev) {
    switch (act) {
        case "bp-log": document.querySelector("#page .b-round")?.scrollIntoView({ behavior: "smooth", block: "center" }); break; // 戰場面板「完整戰報」：捲到場景卡的戰報
        case "battle-open": battleOpen(); break; // FB-120：只能觀戰的人收成一行的開打中的戰場，攤開（記戰場的名字）
        case "battle-shut": battleShut(); break; // 攤開的戰場底下「收起戰場」
        case "mvp-replay": if (typeof mvpReopen === "function") mvpReopen(); break; // 決戰的回合 MVP：戰場底下那一行「再看一次」重新跳出視窗
        case "mvp-again": if (typeof mvpAgain === "function") mvpAgain(); break; // MVP 視窗裡：絕招從頭再演一次
        case "mvp-close": if (typeof mvpClose === "function") mvpClose(); break; // MVP 視窗收起
    } // battleClick
  } // battleClick
  registerClicks(battleClick, ["bp-log", "battle-open", "battle-shut", "mvp-replay", "mvp-again", "mvp-close"]);
