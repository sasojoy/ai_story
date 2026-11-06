/* 天下大勢的網頁前端：全服決戰的集結、戰場與戰局條（全部拆包第 67 批從 main.js 切出來）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
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
