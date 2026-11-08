/* 天下大勢的網頁前端：江湖頁（從 app.js 切出來，減法季批 0；說明見 app.js 檔頭）。 */
"use strict";

  // ── 江湖 ──
  const nowMore = (open) => (open ? "收起 ▴" : "展開全文 ▾");
  const roundsMore = (open) => (open ? "收起過程 ▴" : "展開過程 ▾");

  // 戰鬥卡片的「過程」（計畫三 Task 1、G6 暫定）：「剛剛」那張只露第一回合，按「展開過程」才攤開（其餘回合一回合一回合浮現，
  // style.css 的 .rounds），第一屏要留給剛剛、場景與整排行動（企劃者 2026-10-04）；按鈕放在「過程」那一行的右邊，不多佔一行。
  // 戰報頁照樣整段列出，不經過這裡。認的是伺服器把「**過程**」轉成的那段 HTML（server.md）；認不出來就整段照原樣
  // （tests/server/test_server.py 擋住兩邊對不上）。展開記在 S.roundsOpen（記的是那一場的流水號），換成新的一場就自動收回
  const ROUNDS_MARK = "<p><strong>過程</strong></p>\n<ul>";
  // 大場面模型寫的過程是一段話（battlelog._rounds_block 的「**過程**＋換行＋一段話」，最多 200 字）：同一顆「展開過程」，
  // 收著只露前兩行（style.css 的 .battle-card p.rounds-tale，PM 2026-10-05）
  const TALE_MARK = "<p><strong>過程</strong><br />\n";
  // 「看完整戰報 ›」放在「過程」那一行的中間（PM 2026-10-05，戰鬥卡片壓縮第二輪）：那一行中間本來就是空的，不再接在「結果／得失」
  // 句尾多撐一行。點擊範圍上下各多 8px、不撐高那一行（style.css 的 .rounds-head .report-link）
  const reportLink = (id) => `<button class="linkish report-link" data-act="report" data-id="${id}">看完整戰報 ›</button>`;
  // 功效的演出句（計畫六 Task 4，引擎的 battlelog.trait_line）一律以「〔功效名〕」開頭：收著的卡片先把它們藏起來，第一回合照舊帶頭
  // （Task 4 審查 I-1：不然功效句頂掉第一回合的數字行，多佔一行、也藏了第一回合的數字）；展開之後照引擎寫的順序全部列出，戰報頁不經過這裡。
  // 認的是行首的〔（引擎擁有這段文字，tests/server/test_server.py 擋住兩邊對不上）；整段都是功效句（沒有回合）時不藏，免得收著的過程是空的
  const TRAIT_LEAD = "〔";
  function foldTraitItems(rest) {
    const end = rest.indexOf("</ul>");
    const list = end < 0 ? rest : rest.slice(0, end);
    const items = list.match(/<li>[\s\S]*?<\/li>/g) || [];
    if (!items.some((li) => !li.startsWith(`<li>${TRAIT_LEAD}`))) return rest;
    return list.split(`<li>${TRAIT_LEAD}`).join(`<li class="trait">${TRAIT_LEAD}`) + (end < 0 ? "" : rest.slice(end));
  }
  // 大場面的一段話：每一行以 <br /> 分開，功效句連同它後面的換行包進 <span class="trait">（收著時整個藏起來，兩行的截斷就看到模型的話）
  function foldTraitText(rest) {
    const end = rest.indexOf("</p>");
    const lines = (end < 0 ? rest : rest.slice(0, end)).split("<br />\n");
    if (lines.every((line) => line.startsWith(TRAIT_LEAD))) return rest;
    const last = lines.length - 1;
    const marked = lines.map((line, i) => {
      const text = i < last ? `${line}<br />\n` : line;
      return line.startsWith(TRAIT_LEAD) ? `<span class="trait">${text}</span>` : text;
    });
    return marked.join("") + (end < 0 ? "" : rest.slice(end));
  }
  function roundsFold(card, id) {
    const open = S.roundsOpen === id;
    const more = `<button class="linkish rounds-more" data-act="rounds-more" aria-expanded="${open}">${roundsMore(open)}</button>`;
    const head = `<p class="rounds-head"><strong>過程</strong>${id == null ? "" : reportLink(id)}${more}</p>\n`;
    let at = card.indexOf(ROUNDS_MARK);
    if (at >= 0) return card.slice(0, at) + head + `<ul class="rounds${open ? " open" : ""}">` + foldTraitItems(card.slice(at + ROUNDS_MARK.length));
    at = card.indexOf(TALE_MARK);
    if (at >= 0) return card.slice(0, at) + head + `<p class="rounds-tale${open ? " open" : ""}">` + foldTraitText(card.slice(at + TALE_MARK.length));
    return card;
  }

  // 沒有「過程」那一行的卡片（全服決戰、舊戰報）才把「看完整戰報 ›」接在卡片最後一段（「結果　…　得失　…」那一句）的句尾，
  // 不另佔一行（PM 2026-10-05，戰鬥卡片壓縮）；卡片最後不是 <p>（認不出來）時照舊放在卡片最後。
  // 伺服器的 Markdown 一律以 "</p>\n" 收尾，所以認最後一個 </p>
  function withReportLink(card, id) {
    if (id == null) return card;
    const end = card.lastIndexOf("</p>");
    return end >= 0 && !card.slice(end + 4).trim() ? `${card.slice(0, end)}${reportLink(id)}${card.slice(end)}` : card + reportLink(id);
  }
  // 「剛剛」的戰鬥卡片：有「過程」那一行（roundsFold 認得出來，卡片因此變了）連結就在那一行裡，沒有才接在最後一段的句尾
  function fightCard(card, id) {
    card = keepGainsWhole(card);
    const folded = roundsFold(card, id);
    return trailMoves(folded !== card ? folded : withReportLink(card, id));
  }
  // 「結果　…　得失　經驗 +5　氣血 -11…」那一段：每一樣以全形空白分開，各包成一顆 <span class="nb">（不換行），
  // 換行只落在兩樣之間，不會把「氣血」和「-11」拆到兩行（2026-10-27 跑版回報）。只動含「得失」的那一段、不帶標籤的那幾樣。
  // 超過 16 個字的不包（那是「結果」裡的整句，例：約戰輸了「這一場輸了：內傷加重，下一次出陣與應戰多等 30 分。」24 個字）：包了就不能換行，
  // 375 寬整頁被撐成 397 寬、分頁列落到畫面外（出陣約戰網頁實機，2026-10-28）
  function keepGainsWhole(card) {
    return String(card).replace(/<p>(?:(?!<\/p>)[\s\S])*?<strong>得失<\/strong>(?:(?!<\/p>)[\s\S])*?<\/p>/g, (p) => p.replace(/(<\/strong>|　)([^　<\n]+)(?=　|<\/p>|<br)/g, (all, lead, item) => (item.length > 16 ? all : `${lead}<span class="nb">${item}</span>`)));
  }
  // 戰報裡招、功效、狀態那一句引擎寫成「〔疾風追影〕某某腳下一錯……」；畫面上人在前、招在後（招式與絕學稿案第一節）：
  // 「某某腳下一錯……〔疾風追影〕」，招名畫成一枚小籤。只動清單的一條（<li>），決戰那一條前面的陣營小標籤留在最前面
  function trailMoves(html) {
    const MOVE_LEAD = /(<li[^>]*>(?:<span class="b-tag">[^<]*<\/span>)?)〔([^〕<\n]{1,12})〕([^<\n]+)/g;
    return String(html).replace(MOVE_LEAD, (all, head, name, rest) => `${head}${rest}<span class="t-move">〔${name}〕</span>`);
  }

  // 收著的「過程」第一回合最多兩行、而且不藏任何數字（PM 2026-10-05）：句子放得進兩行就照原樣；放不進就整句省略，只留數字
  // 「第1回合　你氣血 -13，對手氣勢 -10……」。數字就是 battlelog.round_lines 寫的那幾種結尾：「對手氣勢 -N」「你氣血 -N」，
  // 沒打中的「被對方架開」「被你閃開了」（照句子裡出現的先後）。認不出來（沒有「第N回合」、一個結尾也沒找到、扣掉認得的之後
  // 還剩任何數字）就回 null——呼叫端照原樣整句顯示，寧可多佔一行也不讓一個數字被藏起來。展開之後每一回合照舊整句列出
  const ROUND_BITS = /對手氣勢 -\d+|你氣血 -\d+|被對方架開|被你閃開了/g;
  function compactRound(text) {
    const line = String(text).trim();
    const head = /^第\d+回合/.exec(line);
    if (!head) return null;
    const rest = line.slice(head[0].length);
    const bits = rest.match(ROUND_BITS);
    if (!bits || /\d/.test(rest.replace(ROUND_BITS, ""))) return null;
    return `${head[0]}　${bits.join("，")}……`;
  }
  // 畫好之後量第一回合：高過兩行半（三行是三倍行高；兩行混著拉丁數字與漢字量出來會多一兩 px，不能算成三行）、又拼得出數字行，
  // 就把它換成數字行（.r-full 整句、.r-short 數字行，style.css 的 .tight 決定露哪個；展開時一律露整句）。
  // 每次都先拿掉 .tight 再量，轉向、拉視窗之後重量也一樣
  function fitFirstRound() {
    const list = document.querySelector(".battle-card ul.rounds");
    const first = list && list.querySelector(":scope > li:not(.trait)"); // 收著時露出的那一個：功效句藏起來，第一回合帶頭（foldTraitItems）
    if (!first) return;
    list.classList.remove("tight");
    let full = first.querySelector(":scope > .r-full");
    const lineHeight = parseFloat(getComputedStyle(first).lineHeight);
    if (!first.offsetHeight || !(lineHeight > 0) || first.offsetHeight <= 2.5 * lineHeight) return;
    const short = compactRound(full ? full.textContent : first.textContent);
    if (short == null) return;
    if (!full) {
      full = document.createElement("span");
      full.className = "r-full";
      full.append(...first.childNodes);
      const tail = document.createElement("span");
      tail.className = "r-short";
      first.append(full, tail);
    }
    first.querySelector(":scope > .r-short").textContent = short;
    list.classList.add("tight");
  }

  // 出陣回報（企劃者 2026-10-23 選「寫數字」；sortie.report）：「剛剛」那一則是領地爭奪的出陣時，卡片底下多一塊——那一塊每個攻方一條進度
  // （0～100，到 100 易手；深的是推完的、淡的是這一下推上去的，被拉回的那一截畫成虛的）、一句話、幾顆小籤（今天自己推了多少、全軍、軍令）
  const frontKey = (f) => (f ? `${f.title}|${f.count}|${f.text}` : "");
  // 收著的出陣回報（FIT_STEPS 的 front）：點了原地攤開，記在 S.frontOpen（這一則），重畫時不再收
  function frontOpen(el) {
    S.frontOpen = frontKey(S.main && S.main.front);
    el.classList.remove("fit-tight", "fit-min");
    ["data-act", "role", "tabindex", "aria-expanded"].forEach((a) => el.removeAttribute(a));
  }
  function frontReportHtml(f) {
    if (!f) return "";
    const pct = (v) => Math.max(0, Math.min(100, v | 0));
    const rows = f.rows.map((r) => {
      const lo = pct(Math.min(r.value, r.before)), hi = pct(Math.max(r.value, r.before));
      const moved = hi > lo ? `<i class="${r.value >= r.before ? "sf-gain" : "sf-lost"}" style="left:${lo}%;width:${hi - lo}%"></i>` : "";
      const tip = r.value === r.before ? `${r.name}進度 ${r.value}／100` : `${r.name}進度 ${r.before} → ${r.value}／100`;
      return `<div class="sf-row side-${esc(r.side)}${r.mine ? " mine" : ""}" role="img" aria-label="${esc(tip)}"><span class="sf-name">${esc(r.name)}</span>`
        + `<span class="sf-bar"><i class="sf-fill" style="width:${lo}%"></i>${moved}</span><b class="sf-num">${r.value | 0}</b></div>`;
    }).join("");
    const chips = f.chips.map((c) => `<span class="sf-chip${c.kind === "flip" ? ` flip side-${esc(f.side)}` : ""}">${esc(c.text)}</span>`).join("");
    return `<div class="sfront"><div class="sf-head"><b>${esc(f.title)}</b><span>${esc(f.count)}</span></div>${rows}`
      + `<p class="sf-text">${esc(f.text)}</p>${chips ? `<div class="sf-chips">${chips}</div>` : ""}</div>`;
  }

  // 「剛剛」那一則拆成敘事與數值變化（氣血 -96、黃巾聲勢 -2…，journal.card_html 放在 .tx-now 最後）：
  // 收合只收敘事，數值變化排在收合範圍外面，收著也看得到（W6 review Minor 2）
  function splitChips(html) {
    const t = document.createElement("template");
    t.innerHTML = html;
    const chips = t.content.querySelector(".tx-now > .tx-chgs");
    if (chips) chips.remove();
    return [t.innerHTML, chips ? chips.outerHTML : ""];
  }

  // ── 江湖頁的行動列（企劃者 2026-10-04：輪盤太大，改成一排五顆，樣式是她給的「水墨氣勁」；2026-10-12 拿掉打坐剩四顆）──
  // 選項標籤「探索（體力 5・…）」拆成名字與括號裡的說明
  const optParts = (o) => { const m = /^(.*?)（(.*)）$/.exec(o.label); return m ? [m[1], m[2]] : [o.label, ""]; };
  // 決戰三招的按鈕（決戰改版一）：引擎給「選項名（強攻・82 分）」，招與分數拆到按鈕右邊的小字、名字佔剩下的寬度——
  // 375px 上一顆按鈕的字只有約 285px，括號整句接在名字後面的話，十一、十二個字的名字會把一顆按鈕折成兩行（多 20px）
  // 「・主將令」：照令的那一顆（龍頭上陣）
  const BATTLE_MOVE_LABEL = /^(.*)（((?:強攻|固守|奇襲)・\d+ 分(?:・主將令)?)）$/;
  // 鐵匠鋪的選項標籤很長（開爐、主料、輔料、買修淬煉），375px 上瀏覽器會在字中間斷行（FB-132：「下｜品」「沒｜人」「壓｜得住」「屬｜實」）。
  // 照分隔的標點切成小段，每段不折行（.nb），段與段之間才換行；標籤的字一個都不改，只是多包幾層 span，每段各自跳脫。
  // 切在「・；、，＋→」後面（連同後面跟著的空白，「→ 」不留在行頭）與「（」前面；括號尾「）」、數字與單位（「下品 46%」「工錢 150 兩」）
  // 都留在原來那一段。一段超過 NB_MAX 個字就不包（寧可折行也不讓字衝出按鈕）
  const NB_AFTER = "・；、，＋→";
  const NB_MAX = 16;
  function nbChunks(text, after = NB_AFTER) {
    const s = String(text ?? ""), out = [];
    let cur = "";
    for (let i = 0; i < s.length; i++) {
      if (s[i] === "（" && cur) { out.push(cur); cur = ""; }
      cur += s[i];
      if (after.includes(s[i])) {
        while (s[i + 1] === " ") cur += s[++i];
        out.push(cur);
        cur = "";
      }
    }
    if (cur) out.push(cur);
    return out;
  }
  // 「→ 」後面那個空白放在 span 外面：行內區塊尾巴上的空白會被瀏覽器吃掉（「→這個配方」貼在一起），放外面它是普通空白，既看得到、也是一個換行機會，落在行尾或行頭時自己消失
  const nbHtml = (text, after = NB_AFTER, max = NB_MAX) => nbChunks(text, after).map((t) => (t.length <= max ? `<span class="nb">${esc(t.trimEnd())}</span>${esc(t.slice(t.trimEnd().length))}` : esc(t))).join("");
  // 打點帳簿的說明、旁註、去處（FB-411：375 寬一頁 176px，「最／多打點到 40」「今天還能／捐 1000 兩」斷在詞中間）：同一套小段，切在
  // 「，・；／：」後面與「（」前面；不切「→」（「情誼 0 → 5」是一件事）。一段最多 LEDGER_NB 個字（一頁 150px 上下，太長的照常折行）
  const LEDGER_AFTER = "，・；／：";
  const LEDGER_NB = 14;
  const ledgerText = (text) => nbHtml(text, LEDGER_AFTER, LEDGER_NB);
  // 打點店上面掮客那一句（FB-433：360、320 寬斷在「您／挑」「寫／著」中間）：同一套不折行的小段，切在「，。：；！？」後面，
  // 緊跟著的收引號「」』」併進前一段（不讓一個「」」落單到下一行）；一段超過 LEDGER_NB 個字照常折行
  const SAY_AFTER = "，。：；！？";
  function sayHtml(text) {
    const s = String(text ?? ""), out = [];
    let cur = "";
    for (let i = 0; i < s.length; i++) {
      cur += s[i];
      if (SAY_AFTER.includes(s[i])) {
        while (s[i + 1] && "」』".includes(s[i + 1])) cur += s[++i];
        out.push(cur);
        cur = "";
      }
    }
    if (cur) out.push(cur);
    return out.map((t) => (t.length <= LEDGER_NB ? `<span class="nb">${esc(t)}</span>` : esc(t))).join("");
  }
  // 價錢後面打折的原因（名聲 4.1：「威震州郡・九折」「自家地盤・貴兩成」，territory.price_parts、renown.clinic_part）：每一段包成同一種不折行的
  // 小段（.nb），375 寬才不會斷成「九／折」「八五／折」（FB-297）。緊貼的「（」與後面的「，」「）」一起包：Chrome 在括號與行內區塊之間照樣斷，
  // 不包的話一行收在「（」上、下一行從「，」起頭；段與段之間（「，」後面）照常換行。先跳脫再包，字一個不改。
  // 醫館療傷（選項與修練頁）、開爐鈕、馬市待售那一間、素材頁升階格子用它；smith:、market: 的選單鈕已經照 nbChunks 切過，不必再包
  const DEAL_RE = /（?[^（），、；\s・]+・(?:[一二三四五六七八九]+折|貴[^（），、；\s]+)[，）]*/g;
  const dealHtml = (text) => esc(text).replace(DEAL_RE, '<span class="nb">$&</span>');
  // 一行寫完：tests/core/test_battle_buttons.py、test_peek_row.py 的假瀏覽器照名字把這一行切出去（konst），smith:、market:（馬市的鈕一樣長，裝備四欄 5.5）才會用到 nbHtml
  // o.note（名聲 5B 俠寇選項）：標籤底下第二行小字；o.tag（「俠」「寇」）畫在編號那一格（選單那裡）。灰掉、帶原因的那一顆在選單那裡
  // 另外寫進 title、點了說整句（opt-why）；第一屏放不下時 FB-107 第 10 步收掉這一行
  const optLabelHtml = (o) => { const m = o.id.startsWith("battle:act:") ? BATTLE_MOVE_LABEL.exec(o.label) : null; return m ? `<span class="b-name">${esc(m[1])}</span><span class="b-move">${esc(m[2])}</span>` : `<span>${o.id.startsWith("smith:") || o.id.startsWith("market:") ? nbHtml(o.label) : dealHtml(o.label)}${o.note ? `<small class="opt-note">${esc(o.note)}</small>` : ""}</span>`; };
  // 這幾格對到選單上哪一顆、沒有時寫什麼；最後一格是移動（點了在下面展開走法與目的地）
  const ACT_CELLS = [
    { key: "explore", ids: ["act:explore"], name: "探索", none: "不能探索", icon: '<circle cx="12" cy="12" r="9"/><path d="M12 3v3m0 12v3M3 12h3m12 0h3M15 9l-4 2-2 4 4-2z"/>' },
    // 練功（FB-670，企劃者 2026-10-22 選練功入口「丙」）：以前是探索卡上的第四顆，現在行動列自己一格、排在探索右邊（五格）。
    // 選項 id 照舊 explore:practice（選單、模擬腳本都不受影響）；一類一顆沒開、選單上沒有練功時不畫（同調息），序章照 act:practice 的鍵亮。
    // 城裡操練開著時（新手引導重做，Config.training；m.training）城裡這一格是「操練」（act:drill），城外照舊是練功
    { key: "practice", ids: ["act:drill", "explore:practice"], name: "尋敵", none: "", icon: '<path d="M14.5 17.5L3 6V3h3l11.5 11.5M13 19l6-6M16 16l4 4M19 21l2-2M9.5 14.5L21 3h-3L6.5 14.5M11 19l-6-6M8 16l-4 4M3 19l2 2"/>' },
    { key: "train", ids: ["act:train"], name: "遊歷", none: "沒有對手", icon: '<path d="M14.5 4h-5L7 7h10zM12 7v13M8 12h8"/>' },
    // 打坐 2026-10-12 拿掉了（企劃者）：這一格只在序章教體力那一步有選項（調息），沒有選項就不畫（平常是四顆）
    { key: "rest", ids: ["act:rest"], name: "調息", none: "", icon: '<circle cx="12" cy="7" r="2.5"/><path d="M8 20c0-3 3-4 4-4s4 1 4 4M5 15l3-2m11 2l-3-2"/>' },
    { key: "social", ids: ["act:socialize", "act:call"], name: "交友", none: "沒有人", icon: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>' },
  ];
  const MOVE_ICON = '<path d="M13 3l-3 7h5l-4 11 8-10h-5z"/>';
  const SHORT_SUB = { "act:rest": "回體力", "act:call": "挑一位" };  // 求見先打開名單挑人（FB-044：以前又寫一次「求見」；挑了人才花體力）
  const TALKED_OUT = "已經談滿", TALKED_OUT_SUB = "已談滿";  // 談滿了的求見（Game._talked_out_note 的開頭）在行動列格子裡的短說法（待 joy 潤）
  // 灰格小字最多四個字（FB-670：練功多一格、五格之後每格約 62 px，320 寬約 51 px，扣掉內距與框約 45 px、10 px 的字不換行；四格時是六個字）。
  // 原因比這長的：格子寫短的，整句放行動列底下那一行（伺服器那一行本來就寫了整句的，例：散人不能出陣、不在爭奪之列；沒寫的帶在
  // 點了灰格子說的那一句，見 actionBar 的 why）。FB-664：交友灰著、這裡沒有人時（engine.SOCIAL_NO_ONE），10 個字的整句在 375 寬兩頭被切掉
  const SOCIAL_NO_ONE = "這裡沒有能說上話的人", SOCIAL_NO_ONE_SUB = "沒有人";  // 待 joy 潤
  const FAME_GAP = /^名望還差 \d+$/, FAME_GAP_SUB = "名望不夠";  // 交友見不到人（engine._why_not_talk）：還差多少寫在底下那一行（FB-670；待 joy 潤）
  // 出陣灰著的兩種長原因（sortie.RANGER_NOTE、sortie.OUT_NOTE，六個字）：格子寫短的；整句是伺服器寫的出陣那一行（RANGER_LINE、OUT_LINE）（FB-670；待 joy 潤）
  const SORTIE_LONG_SUB = { "散人不能出陣": "未投靠", "不在爭奪之列": "不在爭奪" };
  // 練功那一格的小字（FB-670；待 joy 潤）：亮著寫「不限次數」（第二行照勝算上色，同遊歷），這裡只有頭目時寫「對上頭目」（頭目有冷卻與次數，
  // 不是不限次數；鈕上那一段是 explore_modes.BOSS_NOTE）；灰著：沒有對手（explore_modes.NO_FOE）寫伺服器在鈕上帶的那一個字（o.note：
  // 城鎮「城外才有」、城外沒有對手的地方「這裡沒有」，PM 2026-10-22；舊版伺服器沒帶照寫「城外才有」）、頭目冷卻中或次數用完
  // （鈕上寫「…再現身」）寫「頭目不在」、體力不夠照別格。整句（最近的在哪、步行多久；頭目還要等多久）是伺服器的 action_notes，網頁不另算。
  // 不帶路：灰著就是按不下去（企劃者 2026-10-22 選丙、不選丙帶路）
  const PRACTICE_ID = "explore:practice"; // engine：explore_modes.option_id(PRACTICE)
  const PRACTICE_SUB = "不限次數", PRACTICE_BOSS_SUB = "對上頭目", PRACTICE_BOSS = "頭目";
  const PRACTICE_NO_FOE = "這裡沒有可以練手的對手", PRACTICE_OUT = "城外才有", PRACTICE_AWAY = /現身/, PRACTICE_AWAY_SUB = "頭目不在";
  // 出陣（出陣探索與地盤設計第二節）：出陣開著時（m.sortie）遊歷那一格叫「出陣」，散人、不在戰線上的地點沒有出陣鈕時灰著寫「不在戰線」（待 joy 潤）
  const SORTIE_CELL = { name: "出陣", none: "不在戰線" };
  const SORTIE_LEFT = /今日還能 (\d+) 次/; // 鈕上的「今日還能 N 次」：格子小字寫「今日 N 次」
  const SORTIE_USED = /^今日已出陣/;
  const SORTIE_FULL_SUB = "今日已滿"; // 用完了：整句（什麼時候再來）在行動列底下那一行（待 joy 潤）
  const EXPLORE_PREFIX = "explore:"; // 探索三選一（出陣探索與地盤設計第三節）：探索那一格點了展開這三顆
  const EXPLORE_SUB = "三選一"; // 探索那一格是展開鈕時的小字（待 joy 潤）
  const OUTING_SUB = "走一趟"; // 走一趟開著、伺服器沒給「多半給什麼」時探索那一格的小字（待 joy 潤）
  const TIER_WORDS = ["宵小出沒", "匪寇橫行", "兇徒盤據"]; // training.TIER_WORDS：尋敵那一格的小字寫這一帶多兇（不寫幾級，Joy 2026-10-22）
  const DRILL_FULL = "今日已練滿", DRILL_FULL_SUB = "今日已滿"; // training.DRILL_FULL：用完了，格子寫短的、整句在底下那一行，點了打開移動
  // 找素材分支（第 32 項，計畫 2.1 甲）：選單上有 explore:gather:<分支> 時「找素材」是展開鈕，點了在它底下再攤一排分支（S.gatherOpen）；
  // 最後一顆「自己說…」點了出 20 字的輸入框（S.gatherSaying），送 /api/do/gather_text（同事件的隨口應對那一個輸入框）
  const GATHER_ID = "explore:gather"; // engine：explore_modes.option_id(GATHER)
  const GATHER_BRANCH = "explore:gather:"; // 分支的前綴
  const GATHER_SAY_ID = "explore:gather:say"; // explore_modes.SAY_ID
  // 勝算的顏色（FB-044）：遊歷的小字第二行照風險上色
  const ODDS_TONE = { "穩勝": "good", "有把握": "good", "零風險": "good", "五五波": "even", "難分勝負": "even", "凶險": "bad", "必敗": "bad" };
  // 選單上有「探索」就是平常閒著的時候（以前認打坐，2026-10-12 拿掉了）：用行動列。事件、對話、路上、決戰的選項每次都不一樣，照舊排成一列按鈕
  // 序章裡閒著時選單只留這一步要的（打坐常常不在）：沒有事件的選項、不在路上，也當閒著的行動列來畫，沒亮的格子不畫（F12）
  // 籌備中、休季、暫停（season:）與閉關中（act:break）的選單只有一顆通知：那顆要畫成看得見的按鈕，不能掉進行動列的摺疊裡（M2）
  const NOTICE_MENU = /^(choice:|sense:|season:|act:break$)/;
  const idleMenu = (m) => m.options.some((o) => o.id === "act:explore") || (!!m.prologue && !m.on_road && !m.options.some((o) => NOTICE_MENU.test(o.id)));
  // 格子上的名字（FB-670）：五格時「出陣・守」（320 寬）、「出陣・攪局」（375 寬）一行放不下，瀏覽器會斷在「攪／局」中間：
  // 照「・」切成不折行的小段（.nb），只在「・」後面換行；沒有「・」的照舊
  function inkName(name) {
    return name.includes("・") ? name.split(/(?<=・)/).map((t) => `<span class="nb">${esc(t)}</span>`).join("") : esc(name);
  }
  const inkCell = (key, name, sub, icon, attrs, cls, note = "") => `<button class="act-ink${cls}" data-key="${key}" data-glow="act:${key}" ${attrs}>${ink(key)}
      <svg class="ink-icon" viewBox="0 0 24 24" aria-hidden="true">${icon}</svg><b>${inkName(name)}</b><small>${esc(sub)}</small>${
      note ? `<small class="ink-note ${ODDS_TONE[note] || ""}">${esc(note)}</small>` : ""}</button>`;


  function actionBar(m) {
    const byId = Object.fromEntries(m.options.map((o) => [o.id, o]));
    const used = new Set(musterJoins(m).map((o) => o.id)); // 畫在場景卡上了（FB-105），不掉進「此地還能做」
    // 這裡只有一位大勢人物、沒有交友事件、他又見不到（名望不夠、閉門不見、這個遊戲日談滿）、福緣也沒到時，引擎不給交友
    // （只會花體力換同一句打發，Game._brush_off），選單上只剩直接列的「求見某某」（設計 9.1）：社交那一格改放它。
    // 交友或求見名單（兩位以上）在選單上時照舊，這顆收在摺疊裡
    const loneCall = m.options.find((o) => o.id.startsWith("call:") && o.id !== "call:back");
    // 探索三選一（出陣探索與地盤設計第三節）：三顆畫在探索那一格點開的卡上，不掉進「此地還能做」
    // 找素材分支（第 32 項）畫在「找素材」底下那一排，不算進三選一的那幾顆；練功（explore:practice）在行動列自己一格（FB-670），不在卡上
    const modes = m.options.filter((o) => o.id.startsWith(EXPLORE_PREFIX) && !o.id.startsWith(GATHER_BRANCH) && o.id !== PRACTICE_ID);
    const branches = m.options.filter((o) => o.id.startsWith(GATHER_BRANCH));
    modes.forEach((o) => used.add(o.id));
    branches.forEach((o) => used.add(o.id));
    // 入口灰著（體力不夠，三顆都按不下去）時就算記著展開也不畫：那一格是灰格子，不是展開鈕
    // 走一趟（outing.js；企劃者 2026-10-29～30）：探索那一格點了在底下展開一、三、五段，挑了才出發；關著（m.outing 是 null）照舊一按就探索
    const outingOn = !!m.outing && !m.prologue;
    const exploreOpen = S.wheelSel === "explore" && (modes.length > 0 || outingOn) && !!(byId["act:explore"] && byId["act:explore"].enabled);
    // 序章（新手引導計畫一）：還沒亮的格子不畫（act:explore、act:practice、act:train、act:rest、act:social、act:move）；
    // 不畫的格子對到的選項照樣記成用過，不會掉進「此地還能做」那個摺疊裡。練功的鍵教學內容還沒寫：草廬與初入江湖那四步都不畫（FB-670）
    // 四格（減法季批 1，整合設計 6.3）：探索、出陣、交友、移動。尋敵、操練那一格只在新手引導（序章、初入江湖）時還在——引導的話叫你按它
    // （content/tutorial.json）；平常收進「此地還能做」（不加進 used），批 2 的探索一顆接手之前照樣按得到
    const guiding = !!(pro() || onb());
    // 交友先挑人（Joy 2026-11-08 UI 手感乙批 6-1 選「先跳出名單挑人」）：此地有兩個人以上（大勢人物＋江湖人）時，交友那一格是展開鈕，
    // 點了在底下列出此地的人：人物說得上話的直接開口（fig-talk，照伺服器的 talk.via），說不上的打開人物卡寫原因；江湖人打開他的玩家卡。
    // 只有一個人時照舊一按就交友。交友這一下本來會走別的（福緣的同伴、一次性事件、結識事件：沒有哪一位的 talk.via 是交友本身）時，
    // 名單最上面多一顆照舊的「交友」
    const figsHere = (m.figures_here || []), peersHere = (m.here || []);
    const socialPick = !guiding && figsHere.length + peersHere.length >= 2 && !!(byId["act:socialize"] || byId["act:call"]);
    const socialAsIs = !figsHere.some((f) => f.talk.via && /^act:(socialize|call)$/.test(f.talk.via[0]));
    const socialCard = !(socialPick && S.wheelSel === "social") ? "" : `<div class="card act-move"><div class="options">${socialAsIs
      ? `<button class="btn go" data-act="choose" data-id="${esc((byId["act:socialize"] || byId["act:call"]).id)}"><span class="k">→</span><span>四處結交，看會遇上誰</span></button>` : ""}${figsHere.map((f) => `
          <button class="btn go" data-act="${f.talk.via ? "fig-talk" : "fig-open"}" data-id="${esc(f.id)}"><span class="k">→</span><span>${esc(f.name)}<small class="opt-note">${esc(f.intro && f.intro.role ? f.intro.role : f.side || "")}${f.talk.via ? "" : `・${esc(f.talk.why || "")}`}</small></span></button>`).join("")}${peersHere.map((p) => `
          <button class="btn go" data-act="peer" data-name="${esc(p.name)}"><span class="k">→</span><span>${esc(p.name)}<small class="opt-note">江湖人・${esc(p.side || "")}</small></span></button>`).join("")}</div></div>`; // 待 joy 潤：四處結交，看會遇上誰
    const cells = ACT_CELLS.map((d0) => {
      const d = d0.key === "train" && m.sortie ? { ...d0, ...SORTIE_CELL } : d0;
      if (d.key === "practice" && !guiding) return "";
      const o = d.ids.map((id) => byId[id]).find(Boolean) || (d.key === "social" ? loneCall : undefined);
      if (o) used.add(o.id);
      if (!shown(`act:${d.key}`) || ((d.key === "rest" || d.key === "practice") && !o)) return "";
      if (!o) return inkCell(d.key, d.name, d.none, d.icon, "disabled", " off");
      const lone = o.id.startsWith("call:");
      const [label, detail] = optParts(o);
      // 格子窄：名字寫「求見」，人物的名字放在下面一行。鈕名只留動詞（6.3）：「出陣・攻」寫「出陣」，攻守照小字與點開之後的卡
      const name = lone ? "求見" : label.split("・")[0];
      // 灰著的格子寫短的（FB-664、FB-670），整句原因點了才說（toast，同灰掉的俠寇鈕 opt-why）：伺服器那一行（action_notes：散人不能出陣、
      // 談滿了幾時再來、最近的練功點……）優先，沒有就是標籤括號裡那一整句。以前整句排在行動列底下（explain-1），減法季批 1 拿掉了那幾行
      const drillFull = !o.enabled && detail.startsWith(DRILL_FULL); // 操練用完了：點了打開移動（最近的練功點寫在點了說的那一句）
      // 交友沒有人、談滿了、名望還差幾點、操練用完了：伺服器那一行寫的是按得下去時的說明（FB-665），這幾種照標籤括號裡那一整句
      const longWhy = !lone && (detail === SOCIAL_NO_ONE || detail.startsWith(TALKED_OUT) || FAME_GAP.test(detail) || drillFull);
      const why = longWhy ? `${detail}。` : (m.action_notes || {})[o.id] || (detail ? `${detail}。` : "");
      // 按不下去的原因：標籤括號裡寫的是體力就是「體力不夠」，寫別的就照寫；整句太長、格子裝不下（約 60 px、不換行）時只留
      // 最後一小句（例：挑戰本人打贏之後「剛吃了敗仗，閉門不見」只寫「閉門不見」，T4）
      // 談滿了的求見（「已經談滿 3 輪，第 1 週・週日 00:00 之後再來」）：最後一小句是換日的那一刻，格子裝不下會被切成碎片，
      // 格子只寫「已談滿」，整句在底下那一行（Game.action_notes，day-scale 審查 I1）
      // 出陣：小字寫今天還剩幾次（「今日 5 次」，體力在鈕上、說明那一行也有）；用完了寫「今日已滿」，什麼時候再來在底下那一行
      const left = SORTIE_LEFT.exec(detail);
      // 探索三選一開著：探索那一格是展開鈕（同移動），點了在下面就地展開三顆；入口灰著（三顆都按不下去）時照一般的灰格子
      const wheel = d.key === "explore" && (modes.length > 0 || outingOn) && o.enabled;
      // 練功（FB-670）：亮著「不限次數」（只有頭目時「對上頭目」）；灰著沒有對手照鈕的 note（城外才有／這裡沒有）、頭目不在「頭目不在」，體力不夠照別格。
      // 城外練功分級（Config.training）：亮著寫級數（一級／二級／三級）；城裡的操練照出陣寫「今日 N 次」，用完了「今日已滿」
      const practice = d.key === "practice" && o.id === PRACTICE_ID && (o.enabled || !detail.startsWith("體力"))
        ? (o.enabled ? (detail.split("・").includes(PRACTICE_BOSS) ? PRACTICE_BOSS_SUB : PRACTICE_SUB)
          : detail.startsWith(PRACTICE_NO_FOE) ? (o.note || PRACTICE_OUT) : PRACTICE_AWAY.test(detail) ? PRACTICE_AWAY_SUB : "")
        : "";
      const tier = d.key === "practice" && o.enabled ? detail.split("・").find((x) => TIER_WORDS.includes(x)) : "";
      // 探索那一格亮著時小字寫這裡多半給什麼（「城裡多事」「野外多敵」，整合設計 6.3；伺服器的 m.mostly，在路上沒有）
      const mostly = d.key === "explore" && o.enabled && m.mostly ? m.mostly : "";
      const sub = mostly ? mostly
        : wheel ? (outingOn ? OUTING_SUB : EXPLORE_SUB)
        : tier ? tier
        : drillFull ? DRILL_FULL_SUB
        : practice ? practice
        : o.enabled ? (lone ? label.replace(/^求見/, "") : left ? `今日 ${left[1]} 次` : (SHORT_SUB[o.id] || detail.replace(/^體力 (\d+).*$/, "體力 $1")))
        : detail === SOCIAL_NO_ONE ? SOCIAL_NO_ONE_SUB
        : detail.startsWith(TALKED_OUT) ? TALKED_OUT_SUB
        : FAME_GAP.test(detail) ? FAME_GAP_SUB
        : SORTIE_USED.test(detail) ? SORTIE_FULL_SUB
        : SORTIE_LONG_SUB[detail] ? SORTIE_LONG_SUB[detail]
        : (detail && !detail.startsWith("體力") ? detail.split("，").pop() : "體力不夠");
      // 體力之後還有說明（遊歷的「體力 10・2 路對手・必敗」）：挑出勝算那一段另起一行（FB-044；對手數放不下就不寫）。
      // 不一定是最後一段：有自己人也有敵人的地方後面還接「・或與自己人操練」（畫面批次審查 C1）
      const parts = detail.split("・");
      const note = o.enabled && !wheel && /^體力 \d+/.test(parts[0]) ? (parts.find((x) => x in ODDS_TONE) || "") : "";
      // 出陣約戰（丙，見 sortiePanelHtml）：約戰開著時出陣那一格是展開鈕，點了在底下攤開出陣前那張卡、不送 act:train；灰著也點得開
      // （卡底那顆鈕寫為什麼）。截糧的運糧隊經過（照舊直接打）、散人與不在爭奪之列（照舊點了說整句）不算
      const duelCell = d.key === "train" && sortieCardOn(m) && !SORTIE_LONG_SUB[detail];
      const duelOpen = duelCell && S.wheelSel === SX_OPEN;
      const pickOpen = d.key === "social" && socialPick && S.wheelSel === "social";
      const attrs = duelCell ? `data-act="sortie-open" aria-expanded="${duelOpen}"`
        : d.key === "social" && socialPick && o.enabled ? `data-act="wheel" data-key="social" aria-expanded="${pickOpen}"`
        : wheel ? `data-act="wheel" data-key="explore" aria-expanded="${exploreOpen}"`
        : drillFull ? `data-act="drill-full" aria-expanded="${S.wheelSel === "move"}"` // 格子自己的 data-key 是 practice，不能再寫一個
        : o.enabled ? `data-act="choose" data-id="${esc(o.id)}"`
        : why ? `data-act="opt-why" data-why="${esc(why)}" aria-disabled="true"` : "disabled";
      return inkCell(d.key, name, sub, d.icon, attrs, (o.enabled || duelOpen ? "" : " off") + ((wheel && exploreOpen) || duelOpen || pickOpen ? " on" : ""), note);
    });
    const moves = m.options.filter((o) => followsMode(o.id));
    moves.forEach((o) => used.add(o.id));
    // 奪璽單挑的三招（或灰的「已出招」「來不及了」）：自己是一方時伺服器排在選單最前面（玉璽碎片設計 5.5），
    // 畫在行動列上面一排，不掉進收起來的「此地還能做」（同 FB-105 的集結鈕）
    const sealMoves = m.options.filter((o) => o.id.startsWith("seal:"));
    sealMoves.forEach((o) => used.add(o.id));
    const sealRow = sealMoves.length ? `<div class="options seal-moves" role="group" aria-label="奪璽">${sealMoves.map((o) => `
        <button class="btn" data-act="choose" data-id="${esc(o.id)}" ${o.enabled ? "" : "disabled"}><span>${esc(o.label)}</span></button>`).join("")}</div>` : "";
    // 應召（一類一顆開著時，設計 9.1 第 1 組乙）：有召見時行動列上面一條金框橫幅，按了就去應召；沒有召見不畫，也不收進「此地還能做」
    const summons = m.precise ? byId["act:summons"] : null;
    if (summons) used.add(summons.id);
    const summonsRow = summons ? (() => {
      const [label, detail] = optParts(summons);
      return `<div class="summons-strip"><span>召見</span><button class="summons-go" data-act="choose" data-id="act:summons" ${summons.enabled ? "" : "disabled"}>
        <b>${esc(label)}</b>${detail ? `<small>${esc(detail)}</small>` : ""}</button></div>`;
    })() : "";
    const open = S.wheelSel === "move";
    if (shown("act:move")) {
      cells.push(inkCell("move", "移動", moves.length ? `${moves.length} 條路` : "沒有路", MOVE_ICON,
        moves.length ? `data-act="wheel" data-key="move" aria-expanded="${open}"` : "disabled", (open ? " on" : "") + (moves.length ? "" : " off")));
    }
    const moveCard = !open || !shown("act:move") ? "" : `<div class="card act-move"><div class="seg move-mode" role="group" aria-label="走法">${MOVE_MODES.map((x) => `
          <button class="${S.moveMode === x.id ? "on" : ""}" data-act="move-mode" data-mode="${x.id}" aria-pressed="${S.moveMode === x.id}">${x.name}</button>`).join("")}</div>
        <div class="options">${moves.map((o) => `<button class="btn go${routeGlowOn(m, o.id) ? " glow" : ""}" data-act="choose" data-id="${esc(o.id)}" ${o.enabled ? "" : "disabled"}>
          <span class="k">→</span><span>${esc(o.label)}${o.note ? `<small class="opt-note">${esc(o.note)}</small>` : ""}</span></button>`).join("")}</div></div>`;
    const exploreCard = !exploreOpen ? "" : outingOn ? outingPickerHtml(m) : `<div class="card act-explore"><div class="options">${modes.map((o) => o.id === GATHER_ID && branches.length
      ? gatherWheel(o, branches) : `
          <button class="btn" data-act="choose" data-id="${esc(o.id)}" ${o.enabled ? "" : "disabled"}><span>${esc(o.label)}</span></button>`).join("")}</div></div>`;
    // 其他只在此地才有的行動（招募、投靠、多出來的求見）收在摺疊裡，不佔行動列的高度。
    // 入伍段要你按的那一顆收在這裡（巡哨、傳道、保境安民、接糧車……，伺服器在框上帶的 guide.glow，FB-093）：那一步在這一處開頭摺疊先打開
    // 一次、那一顆發光（applyGlow）；其他時候收著。開合記在 S.here（hereFold，FB-087），重畫照它補回
    const extras = m.options.filter((o) => !used.has(o.id));
    const hotHere = extras.some((o) => guideGlow().includes(o.id)) || extras.some(persuadingNow); // 勸降的輸入框叫出來了：摺疊要開著
    // 論武的「答應」（選單上那一顆引擎不收、是灰的）：場景底下那一列帶了 peer，這裡同一顆也畫成打開他的玩家卡（FB-117，callPeers）
    const peers = callPeers(m);
    S.hereExtras = extras;
    if (typeof revampOn === "function" && revampOn(m) && !hotHere && !guiding) return `${sealRow}${summonsRow}${drawn0(cells)}${moveCard}${socialCard}${exploreCard}${sortiePanelHtml(m)}${sortieAnswering(m) ? "" : sortieDuelsHtml(m)}`; // 介面重整：摺疊換成此地可為那一排
    const here = extras.length ? `<details class="fold here"${hereFold(m, hotHere) ? " open" : ""}><summary>此地還能做 ${extras.length} 件事</summary><div class="fold-body options">${extras.map((o) => persuadingNow(o) ? persuadeForm(o) : peers[o.id] ? `
        <button class="btn" data-act="peer-answer" data-name="${esc(peers[o.id])}"><span>${esc(o.label)}</span></button>` : `
        <button class="btn" data-act="choose" data-id="${esc(o.id)}" ${o.enabled ? "" : "disabled"}><span>${dealHtml(o.label)}</span></button>`).join("")}</div></details>` : "";
    const drawn = cells.filter(Boolean); // 序章裡沒亮的格子是空字串；一格都沒有、也沒有「此地還能做」時整條不畫
    function drawn0(cs) { const d = cs.filter(Boolean); return d.length ? `<div class="act-bar" role="group" aria-label="行動" style="--cells:${Math.max(4, d.length)}">${d.join("")}</div>` : ""; }
    // 出陣約戰（丙）：出陣前那張卡（或應戰那一張）展開在行動列底下，約戰卡一張一行接在它下面（應戰時收起，同一張卡已經寫著那一場）
    const duelPanel = sortiePanelHtml(m);
    const duelList = sortieAnswering(m) ? "" : sortieDuelsHtml(m);
    // 以前行動列底下還有每一格的說明三行與「玩法說明 ›」（explain-1、2）：減法季批 1 拿掉了（整合設計 6.3；說明在本週卡的「為什麼」與設定裡）
    return `${sealRow}${summonsRow}${drawn.length ? `<div class="act-bar" role="group" aria-label="行動" style="--cells:${Math.max(4, drawn.length)}">${drawn.join("")}</div>` : ""}${moveCard}${socialCard}${exploreCard}${duelPanel}${duelList}${here}`;
  }



  // 「此地還能做」摺疊畫成開著還是收著（FB-087）。摺疊裡的鈕（例：求見盧植）被擋下來、或輪詢帶來新畫面，整頁重畫、摺疊是新畫的 DOM，
  // 不記的話就收起來——玩家要再點開才看得到剛按的那一顆。所以開合記在 S.here（跟軍令卡記 S.ordersShut 同一個做法）：玩家點開、收起時 toggle
  // 事件記下（檔案最後的 toggle 監聽），重畫照它補回；補畫出來的那一下 toggle 記下的還是同一個值，不會繞圈。
  // 記的是這一處（S.here.at 對上目前的地點）：換了地方就沒有記，從收著開始，不然開過一次，每個城鎮都攤著一排按鈕；回到原處、中間沒在別處開關過，還是原樣。
  // 發光的那一步（guide-3b 審查 Minor 11）：hot＝摺疊裡有框上 guide.glow 點名的鈕。收著就看不到，所以那一步在這一處**開頭**自動打開一次
  // （hereAuto 記打開過了，同一步換一處、或換下一步各算一次）；打開之後就是玩家的——收起來的不再每次重畫都被打開
  function hereFold(m, hot) {
    const at = (m.status && m.status.location) || "";
    const auto = `${guideKey(m.guide) || ""}@${at}`;
    if (hot && !S.hereAuto[auto]) {
      S.hereAuto[auto] = true;
      S.here = { at, open: true };
    }
    return !!(S.here && S.here.at === at && S.here.open);
  }


  // 展開移動（或探索三選一、找素材分支）之後，把展開的那張卡整張捲到底部分頁列上方看得到（FB-663，PM 2026-10-21 給號）。
  // 以前用 scrollIntoView({ block: "nearest" }) 加 CSS 的 scroll-margin-bottom：卡本身還在視窗裡、只是落在分頁列底下時，瀏覽器認為
  // 「已經看得到」不捲，scroll-margin 不算數（量到：375×812 站潁川郡，探索卡底 797、分頁列頂 756，最後一顆〔練功〕下半截被蓋住，
  // scrollY 一直 0；野外也蓋住約 13 px）。改成自己量：卡底離分頁列頂（含底部安全區：量的是分頁列真正的頂）至少 REVEAL_GAP，
  // 只往下捲、不往回捲；卡比分頁列上方看得到的地方還高時，最多捲到卡頂貼在狀態列底下 REVEAL_TOP（第一顆一定看得到）
  const REVEAL_GAP = 12;
  const REVEAL_TOP = 8;
  // card：展開的卡的位置（getBoundingClientRect）；回傳要往下捲幾 px（0＝不捲）
  function revealShift(card, tabsTop, topEdge) {
    const over = card.bottom - (tabsTop - REVEAL_GAP);
    if (over <= 0) return 0;
    return Math.max(0, Math.min(over, card.top - (topEdge + REVEAL_TOP)));
  }
  function revealMoveCard() {
    const card = document.querySelector("#page .act-move, #page .act-explore") || document.querySelector("#page .act-sortie"); // 出陣約戰的卡（丙）同一個做法
    const tabs = document.querySelector(".tabs");
    if (!card || !tabs) return;
    const head = document.getElementById("top");
    const topEdge = head && !head.hidden ? head.getBoundingClientRect().bottom : 0;
    const shift = revealShift(card.getBoundingClientRect(), tabs.getBoundingClientRect().top, topEdge);
    if (shift < 1) return;
    const calm = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.scrollBy({ top: Math.ceil(shift), behavior: calm ? "auto" : "smooth" });
  }





  // 三方態勢的三條（結算卡與江湖頁態勢小標的面板共用）：各用自己陣營的顏色、底色中性（T9 審查 M3）
  function stanceBars(rows, label) {
    return `<div class="fronts" role="group" aria-label="${label}">${rows.map((x) => `
      <div class="front"><div class="front-head"><span>${esc(x.name)}</span><b>${x.value}</b></div>
        <div class="front-bar stance side-${esc(x.side)}" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${x.value}" aria-label="${esc(x.name)}"><i style="width:${pct(x.value, 100)}%"></i></div></div>`).join("")}</div>`;
  }

  // 這一週是第幾週（軍令卡收起來照週記、本週卡）
  const peekWeek = (m) => (m.status && m.status.calendar ? m.status.calendar.week : 0);

  // 點開說明的那幾行（explain-2：戰況圖卡、態勢、大事、主線各一小段；伺服器照規則寫好的 status.war_help[鍵]，一行一段，跳脫）。
  // 伺服器沒給（開關關著、舊版）就是空字串
  function warHelp(m, key, id = "") {
    const lines = m.status && m.status.war_help && m.status.war_help[key];
    return lines && lines.length
      ? `<div class="war-help ${key}-help"${id ? ` id="${id}"` : ""}>${lines.map((t) => `<p>${esc(t)}</p>`).join("")}</div>` : "";
  }



  // ── 本週卡與三方卡（減法季批 1，整合設計 6.1、3.4；Joy 2026-10-24 挑了乙案；2026-10-26 改：排到行動列底下、可以收起）──
  // 本週卡吃掉以前那一排小標（新手、態勢、主線、簽到）、狀態列的「下一件」與黃底提示句。Joy 2026-10-26：四顆行動鈕一定在第一屏，
  // 所以整塊排在行動列底下；「眼下要事」（以前叫「你這一步」）收成兩行——標題（文字冒號前那一截，點了攤說明與「換一件」）、做完拿什麼
  // （伺服器的 step.reward：託付、懸賞、新手目標原本的賞，軍令寫記功幾次；卡本身不另給）與一顆去輿圖（新手目標是「去做」）；
  // 一條灰線寫第 N 週、主題一句、兩軍態勢（整條是一顆鈕，點了在它底下攤開「為什麼」：三方卡、主線、收季規則、下一件、新手目標、簽到七格）。
  // 灰線與「眼下要事」各有一顆 ×，收到換日（wkHidden，記在這個瀏覽器）。「換一件」照伺服器排好的 steps（託付→軍令→懸賞→伏筆→新手目標→去投靠，
  // S.wkStep 記第幾個、換週歸零）；做完的那一件伺服器下一次就不給，自然換到下一件。簽到不放鈕：每天第一次同步引擎自動領，
  // 要挑四階的日子卡底下冒一張挑屬性的小卡（status.checkin.pick）。攤開記在 S.wkOpen（"why"／"step"／null，帶週次）。來信到了本週卡換成來信（pageJianghu）。
  // 序章裡、休季伺服器不給 week_card：不畫。字待 joy 潤
  // （一行一個 const：測試的 konst 照「const 名字」切）
  const WK_STEP = "眼下要事";
  // 跳到輿圖的那幾顆帶上目標地點（data-goto；護糧多一個終點 data-then）：輿圖開在那一處（mapGoto，Joy 2026-10-31）
  const gotoAttrs = (loc, then) => (loc ? ` data-goto="${esc(loc)}"${then ? ` data-then="${esc(then)}"` : ""}` : "");
  const WK_HIDE = "收起，明天再出現";
  const WK_WHY = "為什麼";
  const WK_NEXT = "換一件";
  const WK_GO = "去做";
  const WK_MAP = "去輿圖";
  const WK_IDLE = "這一週沒有特別要做的事，四處走走、接幾個懸賞。";
  const wkKey = (w) => `${w.label}${w.when}`;
  // 「×收起」（Joy 2026-10-26）：灰線與「眼下要事」各一顆，收到換日為止（照季曆第幾天、沒有季曆照第幾天）；記在這個瀏覽器（重整、重登照舊收著）
  const WK_HIDE_STORE = "tianxia.wkHide";
  const wkDay = (m) => String((m.status && m.status.calendar && m.status.calendar.day) || (m.status && m.status.day) || (m.week_card && m.week_card.when) || "");
  function wkHidden(m, part) {
    if (!S.wkHide) {
      try { S.wkHide = JSON.parse(localStorage.getItem(WK_HIDE_STORE) || "null"); } catch (e) { S.wkHide = null; }
      S.wkHide = S.wkHide || { day: "", parts: [] };
    }
    return S.wkHide.day === wkDay(m) && S.wkHide.parts.includes(part);
  }
  function wkHideOne(part) {
    const day = wkDay(S.main);
    wkHidden(S.main, part);
    if (S.wkHide.day !== day) S.wkHide = { day, parts: [] };
    if (!S.wkHide.parts.includes(part)) S.wkHide.parts.push(part);
    try { localStorage.setItem(WK_HIDE_STORE, JSON.stringify(S.wkHide)); } catch (e) { /* 私密視窗：這一次收著就好 */ }
    if (part === "strip" && S.wkOpen && S.wkOpen.id === "why") S.wkOpen = null;
    wkRepaint("");
  }
  // 已經有自己一張卡的不再列進「眼下要事」（Joy 2026-11-07 截圖「第三回 宛城城下」出現兩次）：章回在本週卡裡、軍令與懸賞各有一張
  function wkSteps(w) {
    const m = S.main || {}, st = m.status || {};
    const own = { chapter: !!w.chapter, order: !!((m.orders || []).length && shown("orders")), bounty: !!((st.bounties || []).length && shown("orders")) };
    return w.steps.filter((x) => !own[x.kind]);
  }
  function wkStepOf(w) {
    const steps = wkSteps(w);
    if (!steps.length) return null;
    if (!S.wkStep || S.wkStep.key !== wkKey(w)) S.wkStep = { key: wkKey(w), i: 0 };
    return steps[S.wkStep.i % steps.length];
  }
  // 「態勢」那幾個字：灰線上寫短的（官 58・黃 42），攤開的三方卡裡才是全名
  function wkSidesHtml(sides) {
    if (!sides) return "";
    return `<span class="wk-sides">${STANCE_NAMES.filter(([k]) => k in sides).map(([k, name]) => `${name.slice(0, 1)} <b class="side-${k}">${sides[k] | 0}</b>`).join("・")}</span>`;
  }
  // 「你這一步」拆成標題與說明：文字第一個全形冒號前是標題（軍令、懸賞、託付都是「標題：怎麼做」），沒有冒號整句當標題
  function wkSplit(text) {
    const at = String(text || "").indexOf("：");
    return at > 0 ? [text.slice(0, at), text.slice(at + 1)] : [text, ""];
  }
  // 兩軍態勢的拔河條（Joy 2026-11-07「勢力比拼值還是滿有顯示的意義」「能知道是哪一方佔上風」）：藍是官軍、金是黃巾，白槓是現在打到哪，
  // 兩端細線是一方壓到就收季的那一線（sides_card 的 bar）；右上一句照差距寫：差不到 10「兩軍相持」，10 以上「某軍佔上風」，30 以上「大佔上風」
  const WK_TUG = "兩軍態勢", WK_EVEN = "兩軍相持", WK_LEAD = "{side}佔上風", WK_LEAD_BIG = "{side}大佔上風"; // 待 joy 潤
  const WK_BAR_GAP = "{side}{verb}到 {bar} 就是「{title}」，還差 {gap}", WK_BAR_DONE = "{side}已到 {bar}，「{title}」就在眼前"; // 待 joy 潤
  function wkTugHtml(m, w) {
    const s = w.sides;
    if (!s || !("guan" in s) || !("huang" in s)) return w.sides ? wkSidesHtml(w.sides) : "";
    const g = s.guan | 0, h = s.huang | 0, at = g + h > 0 ? (g * 100) / (g + h) : 50, d = g - h;
    const name = (k) => (STANCE_NAMES.find(([x]) => x === k) || [k, k])[1];
    const lead = Math.abs(d) < 10 ? ["even", WK_EVEN] : [d > 0 ? "guan" : "huang", (Math.abs(d) >= 30 ? WK_LEAD_BIG : WK_LEAD).replace("{side}", name(d > 0 ? "guan" : "huang"))];
    const cols = (m.sides_card && m.sides_card.cols) || [];
    const col = (k) => cols.find((c) => c.id === k) || {};
    const ticks = ["guan", "huang"].map((k) => (col(k).bar ? `<s style="left:${k === "guan" ? col(k).bar : 100 - col(k).bar}%"></s>` : "")).join("");
    // 自己那一方（豪強看此刻幫的那一軍）離收季那一線還差多少；散人不寫（兩邊都寫在「這一季在打什麼」）
    const sc = m.sides_card || {}, mine = (cols.find((c) => c.mine && (c.id === "guan" || c.id === "huang")) || {}).id || sc.lean;
    const mc = mine ? col(mine) : null, now = mine === "guan" ? g : h;
    const gap = mc && mc.bar ? (mc.bar - now > 0 ? WK_BAR_GAP : WK_BAR_DONE).replace("{side}", name(mine)).replace("{verb}", mine === "guan" ? "壓" : "推")
      .replace("{bar}", mc.bar).replace("{title}", esc(mc.bar_title || "")).replace("{gap}", mc.bar - now) : "";
    return `<div class="wk-tug"><div class="wk-tug-row"><span>${WK_TUG}</span><b class="wk-lead side-${lead[0]}">${lead[1]}</b></div>`
      + `<div class="wk-bar" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${g}" aria-label="${WK_TUG}：官軍 ${g}，黃巾 ${h}">`
      + `<b class="side-guan">官 ${g}</b><span class="wk-track"><i style="width:${at}%"></i>${ticks}<u style="left:${at}%"></u></span><b class="side-huang">${h} 黃</b></div>`
      + `${gap ? `<p class="wk-gap">${gap}</p>` : ""}</div>`;
  }
  const WK_MORE = "這一季在打什麼・下一件", WK_MORE_FREE = "兩邊各要做什麼・贏了給什麼"; // 待 joy 潤
  function wkBoxHtml(m, w, open) {
    const bp = bpOn(m);
    const notes = [m.sides_card && m.sides_card.joined ? "" : w.gap, w.unlock, w.cap].filter(Boolean);
    const ch = chapterCardHtml(m, true), join = ch ? "" : factionJoinHtml(m);
    const free = m.sides_card && !m.sides_card.joined;
    return `<section id="week" class="card wk-box" aria-label="${esc(w.label)}${esc(w.when)}">`
      + `<div class="wk-top"><p class="wk-head"><b class="wk-seg">${esc(w.when)}</b><span class="wk-th">${esc(w.theme || "")}</span></p>`
      + `${bp ? "" : wkTugHtml(m, w)}${notes.length ? `<p class="wk-note">${notes.map(esc).join(" ")}</p>` : ""}</div>`
      + `${ch}${join}<div class="wk-morebar"><button class="wk-more" data-act="wk" data-id="why" aria-expanded="${open}" aria-haspopup="dialog">${free ? WK_MORE_FREE : WK_MORE} ›</button>`
      + `<button class="wk-x" data-act="wk-hide" data-id="strip" aria-label="${WK_HIDE}" title="${WK_HIDE}">×</button></div></section>`;
  }
  // 點最下面那一行拉起來的那一層：自己那一方攤開、別方收成一行（點了攤開）；投靠在哪只給還沒投靠的人。其餘照以前「為什麼」那一塊
  const WK_SHEET = "這一季在打什麼", WK_RULES = "玩法說明・可能的結局"; // 待 joy 潤
  function wkSheetHtml(m, w) {
    return `<div class="sheet-bg" data-act="wk" data-id="why"></div><div class="sheet wk-sheet" role="dialog" aria-label="${WK_SHEET}"><div class="grip"></div>`
      + `<div class="top-row"><h3 style="flex:1">${WK_SHEET}</h3><button class="btn small ghost" data-act="wk" data-id="why">關閉</button></div>`
      + `<p class="wk-sheet-th"><b>${esc(w.when)}</b>${esc(w.theme || "")}</p>${whyHtml(m, true)}</div>`;
  }
  // 決戰期間（戰場面板開著）本週條不寫兩軍態勢的兩個數字：面板底下的戰局條也是兩個數字，玩家分不清（PM 2026-11-06 看截圖）；
  // 點開「為什麼」照舊看得到大勢
  function weekCardHtml(m, part) {
    const w = m.week_card;
    if (!w || !shown("quest")) return "";
    const open = S.wkOpen && S.wkOpen.key === wkKey(w) ? S.wkOpen.id : null;
    const step = wkStepOf(w);
    const [title, detail] = wkSplit(step ? step.text : "");
    // 本週要去的那一處畫在輿圖第一層（批 3：/api/map/state 的 week，金路、紅旗、「本週」朱印）：這裡不另算，只給一顆去輿圖看的
    const go = step && step.kind === "newbie" ? `<button class="btn primary wk-go" data-act="newbie-go" data-i="${step.i | 0}">${WK_GO} ›</button>`
      : step && shown("tab:map") ? `<button class="btn primary wk-go" data-act="tab" data-tab="map"${gotoAttrs(step.target && step.target.location, step.then && step.then.location)}>${WK_MAP} ›</button>` : "";
    const x = (part) => `<button class="wk-x" data-act="wk-hide" data-id="${part}" aria-label="${WK_HIDE}" title="${WK_HIDE}">×</button>`;
    // 本週與章回併成一張卡（Joy 2026-11-07 說好，設計稿 2GNxNC7…）：上一格第 N 週、主題（最多兩行）、兩軍態勢拔河條與「誰佔上風」一句；
    // 中一格是你那一方這一回的下一步（沒投靠的人換成兩顆投靠鈕）；最下一行點了從底下拉起「這一季在打什麼」那一層，右邊 × 收到明天
    // （收起來只剩章回卡）。決戰期間（戰場面板開著）不畫拔河條：面板底下的戰局條也是兩軍的數字，玩家分不清（PM 2026-11-06）
    const hideStrip = wkHidden(m, "strip");
    const strip = hideStrip ? chapterCardHtml(m) : wkBoxHtml(m, w, open === "why");
    const panel = !hideStrip && open === "why" ? `<div class="wk-layer">${wkSheetHtml(m, w)}</div>` : "";
    // 灰線底下一行小字（批 5，整合設計 6.8）：第 3 週「離贏還差多少」、第 2 週的功能剛開了那一句、45 級之後那一句；都沒有不畫
    const notes = [m.sides_card && m.sides_card.joined ? "" : w.gap, w.unlock, w.cap].filter(Boolean); // 投靠了的人：自己那一方還差多少寫在拔河條底下
    const note = ""; // 那一行小字畫在合併的卡裡（wkBoxHtml）
    // 「眼下要事」（Joy 2026-10-26：以前叫「你這一步」）排在行動列底下，平常收成兩行：標題、做完拿什麼與去做；點標題才攤說明與「換一件」。
    // 沒有要做的事不畫；× 收到明天。做完的那一件伺服器下一次就不給了，這裡自然換到下一件
    const more = open === "step";
    const card = !step || wkHidden(m, "card") ? "" : `<section class="card wk-card${more ? " on" : ""}" aria-label="${WK_STEP}">
      <div class="wk-head"><button class="wk-tap" data-act="wk" data-id="step" aria-expanded="${more}"><span class="wk-lab">${WK_STEP}</span><b class="wk-title">${esc(title)}</b></button>${x("card")}</div>
      ${more && detail ? `<p class="wk-detail">${esc(detail)}</p>` : ""}
      <div class="wk-foot">${step.reward ? `<span class="wk-gain">${esc(step.reward)}</span>` : '<span class="wk-gain"></span>'}${more && wkSteps(w).length > 1 ? `<button class="linkish wk-next" data-act="wk-next">↻ ${WK_NEXT}</button>` : ""}${go}</div></section>`;
    // 幾塊是江湖頁的兄弟元素、不包一層：每塊帶 data-wk，wkRepaint 一起換掉；什麼都沒畫時留一個空的記號，收起之後原地還找得到位置
    // 兩組：灰線那一組（灰線、小字、為什麼）排在行動列上面（data-wk="top"），「眼下要事」與簽到小卡排在行動列底下（data-wk="low"）；
    // part 不給是兩組接在一起（在路上整塊排在選項底下）。一組什麼都沒畫時留一個空記號，收起之後 wkRepaint 原地還找得到位置
    const tag = (group, parts) => (parts.length ? parts : ['<i class="wk-none" hidden></i>']).map((h) => h.replace(/^<(\w+) /, `<$1 data-wk="${group}" `)).join("\n      ");
    const top = tag("top", [strip, note, panel].filter(Boolean)), low = tag("low", [card, checkinPickHtml(m)].filter(Boolean));
    return part === "top" ? top : part === "low" ? low : `${top}\n      ${low}`;
  }
  // 章回卡（章回主線，企劃者 2026-10-29）：江湖頁最上面一張，你那一方此刻的那一回——第幾回、回目、哪一件大事什麼時候結算、
  // 下一步去哪做什麼、這一方做完了幾個人推了多少；人就在那裡是一顆「去做」（按「未了之事」那一顆），不在是一顆去輿圖。
  // 伺服器沒給（沒投靠、開關關著、這一季的回都收了）不畫。整張壓成三行，四顆行動鈕還在第一屏
  const CH_NO = "第{no}回";
  const CH_NEXT = "下一步：";
  const CH_DO = "去做";
  // 那一件大事的決戰已經在集結、開打了（管理者提早開，手機介面自檢 U-17）：右上角不再寫排定的時刻，改寫此刻的狀態
  const CH_LIVE = { muster: "集結中", active: "開打了" };
  function chapterCardHtml(m, inner) {
    const c = m.week_card && m.week_card.chapter;
    if (!c || !shown("quest")) return "";
    const t = c.target;
    // 說明裡已經寫了地名的（「出城看風（潁川郊野的草澤）」）不再補一次；回目就是那一件大事的（官軍第二回「長社火攻」）只寫時刻
    const far = !c.waiting && t && !c.here && !String(c.hint).includes(t.name) ? `（${esc(t.name)}${t.minutes ? `・${t.minutes | 0} 分` : ""}）` : "";
    const when = CH_LIVE[c.live] || c.at;
    const at = c.beat && c.beat !== c.title ? `${esc(c.beat)}・${esc(when)}` : esc(when);
    const go = c.waiting || c.scene ? "" : c.here ? `<button class="btn primary ch-go" data-act="choose" data-id="story:${esc(c.line)}">${CH_DO} ›</button>`
      : t && shown("tab:map") ? `<button class="btn primary ch-go" data-act="tab" data-tab="map"${gotoAttrs(t.location)}>${WK_MAP} ›</button>` : "";
    return `<${inner ? "div" : "section"} class="${inner ? "wk-mid ch-in" : "card ch-card"} side-${esc(c.side)}" aria-label="${esc(CH_NO.replace("{no}", c.no))}${esc(c.title)}">
      <div class="ch-head"><span class="ch-no">${esc(CH_NO.replace("{no}", c.no))}</span><b class="ch-title">${esc(c.title)}</b>${at ? `<span class="ch-at">${at}</span>` : ""}</div>
      <p class="ch-next">${c.waiting || c.scene ? "" : CH_NEXT}${esc(c.hint)}${far}</p>
      <div class="ch-foot"><span class="ch-sway">${esc(c.sway)}</span>${go}</div></${inner ? "div" : "section"}>`;
  }
  const WK_HOWTO = '<p class="wk-howto"><button class="linkish" data-act="howto-open" aria-haspopup="dialog">玩法說明 ›</button>這一季在打什麼、名望怎麼來、投靠與軍令</p>';
  // 「為什麼」攤開的那一塊：三方卡、收季規則、下一件、主線（以前主線小標的內容）、新手目標（以前新手小標的內容）、簽到這一週七格（每天給什麼）
  function whyHtml(m, sheet) {
    const s = m.status || {};
    const nb = newbiePeek(m), ck = checkinPeek(m);
    const next = m.week_card && m.week_card.next ? `<p class="wk-nextev"><b>下一件</b>${esc(m.week_card.next)}</p>` : "";
    const locked = m.week_card && m.week_card.locked ? `<p class="wk-locked">${esc(m.week_card.locked)}</p>` : ""; // 第 2 週才開的功能（6.6，批 5）
    const howto = s.renown ? WK_HOWTO.replace("名望怎麼來", "名聲怎麼來") : WK_HOWTO; // 以前在行動列底下（explain-2）；名聲開著時那一節叫「名聲」
    if (sheet) { // 拉起來的那一層（PM 2026-11-07：別又是一大片字）：三方、下一件、新手、簽到各一小塊；收季規則、這一季在打什麼、可能的結局收進最底「玩法說明」
      const rules = `${s.stance_rule ? `<p class="stance-rule">${esc(s.stance_rule)}</p>` : ""}${warHelp(m, "stance")}${m.quest && m.quest.trim() && shown("quest") ? `<div class="wk-quest">${m.quest}${warHelp(m, "quest")}</div>` : ""}`;
      return `${m.sides_card ? factionSidesSheetHtml(m.sides_card) : ""}${locked}${next}${nb ? `<h4 class="wk-sub">${esc(s.newbie.title)}</h4>${nb.panel}` : ""}` // 簽到改成每天第一次登入跳小窗（ckPopHtml），這裡不重複
        + `<details class="wk-rules"><summary>${WK_RULES}</summary>${rules}${howto}</details>`;
    }
    return `${m.sides_card ? sidesTableHtml(m.sides_card) : ""}${s.stance_rule ? `<p class="stance-rule">${esc(s.stance_rule)}</p>` : ""}${locked}${next}${warHelp(m, "stance")}`
      + `${nb ? `<h4 class="wk-sub">${esc(s.newbie.title)}</h4>${nb.panel}` : ""}${m.quest && m.quest.trim() && shown("quest") ? `<div class="wk-quest">${m.quest}${warHelp(m, "quest")}</div>` : ""}`
      + `${ck ? `<h4 class="wk-sub">簽到</h4>${ck.panel}` : ""}`
      + howto;
  }
  // 點「為什麼」「今日簽到」：原地換掉本週卡（不重畫整頁，「剛剛」不重播），焦點還給同一顆
  function wkTap(id) {
    const w = S.main.week_card;
    if (!w) return;
    S.wkOpen = S.wkOpen && S.wkOpen.key === wkKey(w) && S.wkOpen.id === id ? null : { key: wkKey(w), id };
    // 「這一季在打什麼」那一層蓋在上面：不把焦點還給卡上那一顆（程式設的焦點 iOS 會畫一圈框，Joy 2026-11-07 截圖的藍框就是它）
    wkRepaint(id === "why" ? "" : `[data-act="wk"][data-id="${id}"]`);
  }
  function wkNext() {
    const w = S.main.week_card;
    if (!w || !wkSteps(w).length) return;
    wkStepOf(w);
    S.wkStep.i = (S.wkStep.i + 1) % wkSteps(w).length;
    wkRepaint('[data-act="wk-next"]');
  }
  // 只換本週卡那幾塊（灰線、為什麼、你這一步、簽到小卡都帶 data-wk）：新的插在第一塊的位置、舊的拿掉；整頁不重畫，「剛剛」不重播
  function wkRepaint(focus) {
    for (const group of ["top", "low"]) { // 灰線那一組在行動列上面、「眼下要事」在底下：各自原地換
      const old = [...document.querySelectorAll(`#page [data-wk="${group}"]`)];
      if (!old.length) continue;
      old[0].insertAdjacentHTML("beforebegin", weekCardHtml(S.main, group));
      old.forEach((el) => el.remove());
    }
    document.querySelector(`#page [data-wk]${focus}, #page [data-wk] ${focus}`)?.focus();
  }

  // 第一季的結算卡（休季才有，計畫 T9）：結局與季末公告、最終態勢與三條戰況；十二件大事與各陣營出力前五收在摺疊裡
  function resultHtml(r) {
    // 戰況照江湖頁標兩端（FB-041）；態勢三條走 stanceBars
    const bars = (rows, label) => `<div class="fronts" role="group" aria-label="${label}">${rows.map((x) => `
      <div class="front"><div class="front-head"><span>${esc(x.name)}</span><b>${x.value}</b></div>
        <div class="front-bar" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${x.value}" aria-label="${esc(x.name)}"><i style="width:${pct(x.value, 100)}%"></i></div>${FRONT_ENDS}</div>`).join("")}</div>`;
    const events = r.timeline.map((e) => `<div class="result-event"><b>${esc(wkName(e.week, `第 ${e.week} 週`))}・${esc(e.title)}</b>${
      e.locked_by ? `<small>${esc(e.locked_by)} 改寫</small>` : ""}${e.text}</div>`).join("");
    const ranks = r.rankings.map((f) => `<div class="result-rank"><b>${esc(f.name)}</b>${f.rows.length
      ? `<ol>${f.rows.map(([n, v]) => `<li><span>${esc(n)}</span><i>${v}</i></li>`).join("")}</ol>`
      : "<p>（沒有人出力）</p>"}</div>`).join("");
    return `<section class="card result"><h2>賽季落幕：${esc(r.title)}</h2><div class="result-text">${r.text}</div>
      <h3>最終態勢</h3>${stanceBars(r.stances, "最終態勢")}<h3>最終戰況</h3>${bars(r.fronts, "最終戰況")}
      <details class="fold"><summary>這一季的十二件大事</summary><div class="fold-body">${events}</div></details>
      <details class="fold"><summary>各陣營出力前五</summary><div class="fold-body result-ranks">${ranks}</div></details></section>`;
  }

  // 戰況條兩端標陣營（FB-041）：條上左邊金色那一截是黃巾佔的、右邊藍色是官軍，字的顏色跟那一截一樣。
  // 戰線在亂局裡時（FB-065）正中間多一個小小的「亂局」標，剛好在亂局帶下面：豪強的地盤，中性的顏色，不佔多一行
  const frontEnds = (chaos) => `<div class="front-ends" aria-hidden="true"><span class="huang">黃巾</span>${
    chaos ? '<span class="chaos-tag">亂局</span>' : ""}<span class="guan">官軍</span></div>`;
  const FRONT_ENDS = frontEnds(false);

  // 態勢那一行（FB-065）：官軍、黃巾是幾條戰況合起來的。說明由伺服器給（status.stance_notes），前端不自己數條數。
  // 狀態列展開時用它（江湖頁的三條在最上面那一排小標的態勢面板裡，正式版辛）
  function stancesHtml(stances, notes) {
    const n = notes || {};
    const side = (id) => `${STANCE_NAMES.find(([key]) => key === id)[1]} ${stances[id]}`;
    const note = (text) => (text ? `（${esc(text)}）` : "");
    return `<div class="stances-line"><span>態勢</span><span>${side("guan")}・${side("huang")}${note(n.sum)}</span></div>`;
  }

  // 第一季濃縮版的三條戰況（伺服器有送 fronts 才畫）：0 是官軍穩控、100 是黃巾控制，條上黃的那一截是黃巾佔的。
  // 條上淺色的一段是亂局帶（band＝status.chaos_band，兩端含在內；兩軍拉鋸的戰況區間），戰況落在裡面的圖卡標「亂局」（f.chaos）。
  // 三方態勢在江湖頁最上面那一排小標的態勢面板裡（正式版辛），不在這一排底下重複
  // tap：伺服器有給戰況的說明（status.war_help.fronts，explain-2）時整排圖卡是一顆按鈕，點了在底下攤開說明（跟點體力條同一個做法）。
  // 變成按鈕之後裡面的 meter 不再念得出來（審查 Minor 4）：鈕的名字自己帶三條戰線的值，用的是同一份資料，畫面不變
  function frontsHtml(fronts, band, tap = false) {
    const shade = band ? `<span class="chaos-band" aria-hidden="true" title="亂局帶" style="left:${pct(band.low, 100)}%;width:${pct(band.high - band.low, 100)}%"></span>` : "";
    const act = tap ? ` data-act="fronts-help" role="button" tabindex="0" aria-expanded="${!!S.frontsOpen}" aria-controls="fronts-help"` : ' role="group"';
    const values = fronts.map((f) => `${f.name} ${f.value}${f.chaos ? "（亂局）" : ""}`).join("、");
    const label = tap ? `戰況：${values}（0 官軍穩控，100 黃巾控制；點開看說明）` : "戰況：0 官軍穩控，100 黃巾控制";
    return `<div class="fronts"${act} aria-label="${esc(label)}">${fronts.map((f) => `
      <div class="front${f.chaos ? " chaos" : ""}"><div class="front-head"><span>${esc(f.name)}</span><b>${f.value}</b></div>
        <div class="front-bar" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${f.value}" aria-label="${esc(f.name)}${f.chaos ? "，在亂局" : ""}"><i style="width:${pct(f.value, 100)}%"></i>${shade}</div>${frontEnds(f.chaos)}</div>`).join("")}</div>`;
  }

  // 江湖頁那一排戰況圖卡＋點開的說明（explain-2）：包在 #war 裡，點圖卡原地換掉這一塊（同 peekTap：不重畫整頁，「剛剛」不再播浮現動畫），
  // 說明排在圖卡底下，只推動它底下的小地圖。伺服器沒給說明（開關關著、舊版）就照舊只是一排圖卡、不能點
  // 陣營軍備的存量（素材與經濟設計第六節；企劃者 2026-10-15 選草圖 C1）：戰況圖卡底下一行（規則關著的季沒有戰況卡，就排在那個位置）。
  // 伺服器在投靠了陣營、捐軍備開著時給 status.armament。在決戰怎麼起作用還沒定，這裡只寫存量。字待 joy 潤
  function armsLine(m) {
    const a = m.status && m.status.armament;
    if (!a || !shown("orders")) return "";
    return `<p class="arms-line"><span class="who">${esc(a.faction)}軍備</span>${a.stock.map((s) => `<span>${esc(s.name)} <b>${s.points | 0}</b></span>`).join("")}</p>`;
  }

  function frontsBlock(m) {
    const help = !!(m.status && m.status.war_help && m.status.war_help.fronts && m.status.war_help.fronts.length);
    return `<div class="war" id="war">${frontsHtml(m.fronts, m.status && m.status.chaos_band, help)}${
      help && S.frontsOpen ? warHelp(m, "fronts", "fronts-help") : ""}</div>`;
  }

  function frontsTap() {
    S.frontsOpen = !S.frontsOpen;
    const box = document.getElementById("war");
    if (box && S.main && S.main.fronts) box.outerHTML = frontsBlock(S.main);
    document.querySelector('.fronts[data-act="fronts-help"]')?.focus(); // 換掉之後焦點放回圖卡，鍵盤可以再按一次收起
  }


  // 事件選項（減法季批 1，整合設計 6.4）：鈕上只留動作（伺服器給的 event_opts[id].act），心裡話只在沒把握（「難說」以下）時寫在底下一行小字，
  // 失手的代價不寫在鈕上（選單上的標籤一個字不改，照舊給別處讀）。鈕前的小圖示照這一下看哪一樣：力、身、骨、悟、博、戰（動手），
  // 不擲骰的「行」，隨口應對「言」。隨口應對的標籤是伺服器的字，只拿掉後面體力的那個括號
  const EV_ICON = { str: "力", agi: "身", con: "骨", wis: "悟", lore: "博", fight: "戰", "": "行", say: "言" };
  const EV_COST = /（(?:體力 -\d+，?)?(?:(?:失手|輸了)多耗體力 \d+)?）$/;
  function evOf(m, o) {
    if (o.id === FREE_TEXT_OPTION && m.event_opts) return { act: o.label.replace(EV_COST, ""), kind: "say", worry: "" };
    return (m.event_opts || {})[o.id] || null;
  }
  const evIconHtml = (ev) => `<span class="k ev ev-${ev.kind || "plain"}" aria-hidden="true">${EV_ICON[ev.kind] || EV_ICON[""]}</span>`;
  // 成算每一顆都寫（Joy 2026-10-27）：「臂力 9：有把握」「對手：河灘潑皮・穩勝」；沒把握（ev.sure 是 false）的那一行標成擔心的顏色
  const evLabelHtml = (o, ev) => `<span>${esc(ev.act)}${ev.worry ? `<small class="opt-note ev-odds${ev.sure === false ? " ev-worry" : ""}">${esc(ev.worry)}</small>` : ""}${o.note ? `<small class="opt-note">${esc(o.note)}</small>` : ""}</span>`;

  // 「剛剛」收著時一行（整合設計 6.3）：時間一小行，底下標題接第一句，放不下加「…」；點了攤開全文（S.nowOpen，同以前的「展開全文」）。
  // 在路上照舊三行（FB-060 的排法沒動）
  // 只拿字（不靠 DOM）：時刻那一格（.tx-when）另外拿出來，其餘的標籤換成空白、實體還原，連成一行
  const NOW_WHEN = /<div class="tx-when">([\s\S]*?)<\/div>/;
  const plainText = (html) => String(html).replace(/<(br|\/(div|p|li|h\d))\b[^>]*>/gi, "　").replace(/<[^>]*>/g, "")
    .replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, "&")
    .replace(/[\s　]+/g, (w) => (w.includes("　") ? "　" : " ")).replace(/^[\s　]+|[\s　]+$/g, "");
  // 結果標記（.tx-tag：成功、失敗、得料、遇事……）收成一行時不跟著被「…」切掉（Joy 2026-10-27「看不出是成功還是失敗」）：
  // 拿出來排在那一行最右邊的小章，成功綠、失敗紅（「韓鐵出手・失敗」這種照結尾），其餘照一般的字色
  const NOW_TAG = /<span class="tx-tag">([\s\S]*?)<\/span>/;
  const nowTagTone = (tag) => (/成功$/.test(tag) ? " ok" : /失敗$/.test(tag) ? " bad" : "");
  function nowOneHtml(html) {
    const hit = NOW_WHEN.exec(html);
    const when = hit ? plainText(hit[1]) : "";
    let body = hit ? html.replace(hit[0], "") : html;
    const tagHit = NOW_TAG.exec(body);
    const tag = tagHit ? plainText(tagHit[1]) : "";
    if (tagHit) body = body.replace(tagHit[0], "");
    const stamp = tag ? `<span class="now-stamp${nowTagTone(tag)}">${esc(tag)}</span>` : "";
    return `<button class="now-one" data-act="now-more" aria-expanded="false">${when ? `<span class="tx-when">${esc(when)}</span>` : ""}<span class="now-line"><span class="now-text-one">${esc(plainText(body))}</span>${stamp}</span></button>`;
  }
  // 收著時拿到的東西也看得到（Joy 2026-10-27「材料事件…顯示獲得的物品跟數量，不用展開」）：敘事裡「得：驚羽 ×2、銀兩 +5」那一行的
  // 物品（帶「×」的）排成綠色小籤，接在得失那一排；沒有「得：」那一行時照「獲得 X ×N」那幾行（同一樣加總）。銀兩、心得這些
  // 數值得失那一排本來就有（entry.changes），不重複
  const NOW_LINE = /<div class="tx-line[^"]*">([\s\S]*?)<\/div>/g;
  function nowGains(html) {
    const lines = [...String(html).matchAll(NOW_LINE)].map((x) => plainText(x[1]));
    const got = lines.find((l) => l.startsWith("得："));
    const items = got
      ? got.slice(2).split(/　失：/)[0].split("、").filter((x) => / ×\d+$/.test(x))
      : lines.filter((l) => /^獲得 \S+ ×\d+$/.test(l)).map((l) => l.slice(3));
    const sum = new Map();
    for (const it of items) {
      const [, name, n] = /^(.*) ×(\d+)$/.exec(it.trim());
      sum.set(name, (sum.get(name) || 0) + Number(n));
    }
    return [...sum].map(([name, n]) => `<span class="tx-chg tx-up now-item">${esc(name)} ×${n}</span>`).join("");
  }
  // 物品籤併進得失那一排（splitChips 拆出來的 .tx-chgs）；那一排沒有時自己開一排
  function withGains(chips, html) {
    const gains = nowGains(html);
    if (!gains) return chips;
    return chips ? chips.replace(/(<div class="tx-chgs">)/, `$1${gains}`) : `<div class="tx-chgs">${gains}</div>`;
  }

  // 「剛剛」那一張（不是戰鬥卡片的那種）：收著是一行（nowOneHtml，整合設計 6.3），點開整則攤開、底下「收起 ▴」；在路上照舊收成三行（FB-060）
  function nowBlock(m) {
    if (!m.now) return "";
    const expanded = S.nowOpen === m.now;
    const [text, chips] = splitChips(m.now);
    return expanded || m.on_road
      ? `<div class="now ${expanded ? "open" : "clamp"}${m.on_road ? " road" : ""}"><div class="now-text">${text}<button class="linkish now-more" data-act="now-more" aria-expanded="${expanded}">${nowMore(expanded)}</button></div>${chips}${frontReportHtml(m.front)}</div>`
      : `<div class="now one">${nowOneHtml(text)}${withGains(chips, text)}${frontReportHtml(m.front)}</div>`;
  }
  // 點「剛剛」：在路上原地換 class（同以前，不重播浮現動畫）；平常一行與整則之間原地換掉那一張
  function nowToggle(el) {
    const box = el.closest(".now");
    const open = !box.classList.contains("open");
    S.nowOpen = open ? S.main.now : null;
    if (S.main.on_road) {
      box.classList.toggle("open", open);
      box.classList.toggle("clamp", !open);
      el.textContent = nowMore(open);
      el.setAttribute("aria-expanded", String(open));
      return;
    }
    box.outerHTML = nowBlock(S.main);
    document.querySelector("#page > .now [data-act=\"now-more\"]")?.focus();
  }

  // 事件分級（事件分級設計稿）：眼前是第二、三階的事件時，場景卡頂上一行小字（州郡大事、天下大事），第三階的框描金；第一階一字不變
  const tierClass = (m) => (m.event_tier ? ` tier-${m.event_tier.tier | 0}` : "");
  const tierTag = (m) => (m.event_tier ? `<p class="tier-tag">${esc(m.event_tier.name)}</p>` : "");

  // 場景卡上面那張圖（減法季批 8 圖像版）：伺服器真的有圖檔才給 m.art（事件插圖、人物像、地點的圖，server.scene_art）。圖佔卡片上方約三分之一，
  // 地名／危險／時刻（事件標題；人名與情誼）疊在圖的下緣，所以場景文字裡原本寫那一行的第一段（m.art.head）拿掉、不寫兩次。沒圖（null）一字不變。
  function sceneArtHtml(a) {
    const sub = a.sub ? `<span class="sub">${esc(a.sub)}</span>` : "";
    const time = a.time ? `<span class="time">${esc(a.time)}</span>` : "";
    // 地點會變樣（世界活起來第二批）：戰火、淪陷、饑荒、重建的地點多一個 mood-<kind>，畫換色調（太平沒有 mood，一字不變）
    return `<figure class="scene-art ${esc(a.kind)}${a.mood ? ` mood-${esc(a.mood)}` : ""}"><img src="${esc(a.src)}" alt="" decoding="async"><figcaption><b>${esc(a.title)}</b>${sub}${time}</figcaption></figure>`;
  }
  function sceneUnderArt(m) {
    if (!m.art || !m.art.head || !(m.scene || "").startsWith(m.art.head)) return m;
    return { ...m, scene: m.scene.slice(m.art.head.length).replace(/^\n/, "") };
  }
  // 江湖頁頂上的常駐提示條（企劃者 2026-11-05「舊玩家根本不會知道要去哪邊點點數」「識海入口藏在現在那個位子…至少需要導引」）：
  // 五項屬性的季有沒配的送點：「有 N 點可配」，點了在原地攤開＋鈕；識海（main.legacy.shihai）封著一份：寫解封還差什麼，解得開時發光，
  // 點了進識海頁。舊的季（沒有 status.growth）、傳承關著（沒有 main.legacy）一顆都不畫
  function jhHintsHtml(m) {
    const s = m.status || {}, out = [];
    const pts = s.growth ? s.stat_points | 0 : 0;
    if (pts) {
      const open = !!S.allocOpen;
      out.push(`<button class="jh-hint ready" data-act="alloc-toggle" aria-expanded="${open}"><span>有 <b>${pts}</b> 點屬性可配</span><i>${open ? "收起 ▴" : "去配 ▾"}</i></button>`);
      if (open) out.push(`<div class="jh-alloc">${(s.attrs || []).map(([k, v, key]) =>
        `<button class="btn small" data-act="allocate" data-stat="${esc(key)}">＋${esc(k)}<small>${esc(String(v))}</small></button>`).join("")}</div>`);
    }
    const sh = m.legacy && m.legacy.shihai;
    if (sh && sh.offers && sh.offers.length) {
      out.push(`<button class="jh-hint ready" data-act="legacy-view" data-v="shihai"><span>識海：上一季的神品意境還沒挑</span><i>去看 ›</i></button>`);
    } else if (sh && sh.sealed) {
      const left = (sh.need || []).filter((n) => !n.ok).map((n) => n.text);
      const ready = !left.length && !sh.held && !(sh.sealed.names || []).length;
      const why = sh.sealed.names && sh.sealed.names.length ? "要先換個名字" : ready ? "可以解封了" : sh.held && !left.length ? "身上已有一份神品" : `解封還差：${left.join("、")}`;
      out.push(`<button class="jh-hint${ready || (sh.sealed.names || []).length ? " ready" : ""}" data-act="legacy-view" data-v="shihai"><span>識海封著「${esc(sh.sealed.name)}」・${esc(why)}</span><i>›</i></button>`);
    }
    return out.length ? `<div class="jh-hints">${out.join("")}</div>` : "";
  }

  function pageJianghu() {
    const m = S.main;
    // 「剛剛」（A4）：預設只露出開頭幾行，太長的（例如新角色的開場故事）收著、點「展開全文」看完，不在卡片裡捲。
    // 展開記在 S.nowOpen（記的是那一則本身），換成新的一則就自動收回；其實放得下的話 afterPage() 會拿掉收合。
    // 畫的是 m.now：最新一則只是本週大事（小標點開的面板）上已經有全文的大事時，伺服器改給再前面那一則（FB-046）；江湖紀錄頁照舊用 m.latest
    const now = m.card
      ? `<div class="card battle-card">${fightCard(m.card, m.card_id)}${gaugeHtml(m.card_gauge)}${m.now || ""}${frontReportHtml(m.front)}</div>`
      : nowBlock(m);
    const free = m.free_text != null
      ? `<form class="free" id="free-form" data-op="${esc(m.free_op || "battle_text")}"><input class="input" name="text" maxlength="20" placeholder="${esc(m.free_text || "輸入你想做的事（20字內）")}"><button class="btn primary small" type="submit">送出</button></form>${m.free_text_note ? `<p class="free-note">${esc(m.free_text_note)}</p>` : ""}`
      : "";
    // 路上那顆灰的「（在路上，幾時抵達）」不畫：往哪、幾時到狀態列已經寫著（FB-046），少一顆也讓路上的捷徑回到第一屏（FB-048）。
    // 決戰集結時還沒參戰的加入鈕畫在場景卡戰場名字那一行（FB-105，musterScene）：事件、對話開著時也是，選項列不再列一次
    const joined = new Set(musterJoins(m).map((o) => o.id));
    const opts = m.options.filter((o) => o.id !== "act:on_road" && !joined.has(o.id));
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
    // 在路上，走法排在整排選項底下（FB-055）：路上的五個選項要全在第一屏，走法那一列（54 px）排在前面會把最後一個擠到分頁列底下
    const modesLast = m.on_road;
    // 路上的四樣小事排成 2×2（FB-055）：四樣小事共兩列，狀態列多一行提示，最後一顆也不會掉到分頁列底下
    // （折返、喊停見下面 FB-060）。標籤「名（補充）」拆成兩行：名字一行、補充小字一行
    const isTask = (o) => m.on_road && ROAD_TASKS.test(o.id);
    const firstTask = opts.findIndex(isTask);
    const lastTask = opts.length - 1 - [...opts].reverse().findIndex(isTask);
    const taskButton = (o, name, note) => {
      if (name === undefined) [, name, note] = o.label.match(/^(.*?)（(.*)）$/) || [null, o.label, ""];
      return `<button class="btn task" data-act="choose" data-id="${esc(o.id)}" ${o.enabled ? "" : "disabled"}><span class="t-name">${esc(name)}</span>${note ? `<span class="t-note">${esc(note)}</span>` : ""}</button>`;
    };
    // 多段路的「折返」與「喊停」併成一列兩格（FB-060）：各佔一整列的話，再加上狀態列的心得提示，最底下的「走法」會落到分頁列底下。
    // 只有兩個都在時才併；標籤照伺服器給的字拆成「名字／補充小字」：「折返 潁川郡（陽翟）（趕路約 2 分鐘・體力 4）」
    // →「↩ 折返 潁川郡（陽翟）」「趕路約 2 分鐘・體力 4」，「喊停（到洛陽官道就停下）」→「喊停」「到洛陽官道就停下」
    // （地名放名字那一行：補充放地名的話，趕路、疾行的字多、會折成兩行，整列又長高 16 px）
    const isWay = (o) => m.on_road && (o.id.startsWith("road:back") || o.id === "act:halt");
    const paired = opts.filter(isWay).length === 2;
    const firstWay = opts.findIndex(isWay);
    const lastWay = opts.length - 1 - [...opts].reverse().findIndex(isWay);
    const wayButton = (o) => {
      if (o.id === "act:halt") { // 「到潁川郡（陽翟）就停下」在窄的那一格折成兩行：換成同一個意思的短說法
        const [, name, note] = o.label.match(/^(.*?)（(.*)）$/) || [null, o.label, ""];
        return taskButton(o, name, note.replace(/^到(.*)就停下$/, "停在$1"));
      }
      const [, dest, note] = o.label.match(/^折返\s*(.*?)（([^（）]*)）$/) || [null, o.label.replace(/^折返\s*/, ""), ""];
      return taskButton(o, `↩ 折返 ${dest}`.trim(), note);
    };
    // 有所感選做法（explain-2）：伺服器給了 sense_help.tags 才把鈕上原本寫 1～4 的那一格改寫這個做法是哪一種心意（不多佔寬度）。
    // 審查 I1 起伺服器預設不給（sensing.SHOW_KINDS）：鈕上照舊 1～4；企劃者要恢復時伺服器那邊改一行，這裡照畫
    const senseTag = (o) => (m.sense_help && m.sense_help.tags && m.sense_help.tags[o.id]) || "";
    const menu = idleMenu(m) ? actionBar(m) : `<div class="options">${opts.map((o, i) => S.sensing && o.id === SENSE_DRAW ? sensePadHtml() : persuadingNow(o) ? persuadeForm(o) : namingGodNow(o) ? ownNameForm(o) : o.id === FREE_TEXT_OPTION && S.answering && o.enabled ? `
        <form class="free answer" id="answer-form"><input class="input" name="text" maxlength="20" placeholder="${esc(o.label)}（20字內）" aria-label="${esc(o.label)}"><button class="btn primary small" type="submit">說出口</button></form>` : SAY_OPTIONS.includes(o.id) && S.saying && o.id === sayingId() && o.enabled ? `
        <form class="free answer" id="say-form"><input class="input" name="text" maxlength="${m.say_max || 20}" placeholder="${SAY_HINTS[o.id] ? `${SAY_HINTS[o.id]}（${m.say_max || 20}字內）` : (m.say_max || 20) > 20 ? `想對他說的話，也可以開口求他做事（${m.say_max}字內）` : "想對他說的話（20字內）"}" aria-label="${esc(o.label)}"><button class="btn primary small" type="submit">說出口</button></form>` : isTask(o) ? `${i === firstTask ? '<div class="road-tasks">' : ""}${taskButton(o)}${i === lastTask ? "</div>" : ""}` : paired && isWay(o) ? `${i === firstWay ? '<div class="road-tasks road-ways">' : ""}${wayButton(o)}${i === lastWay ? "</div>" : ""}` : `${i === firstMove && !modesLast ? modes : ""}
        <button class="btn ${followsMode(o.id) ? "go" : ""}${!o.enabled && o.note ? " off" : ""}" data-act="${!o.enabled && o.note ? "opt-why" : "choose"}" data-id="${esc(o.id)}" ${!o.enabled && o.note ? `data-why="${esc(o.note)}" title="${esc(o.note)}" aria-disabled="true"` : o.enabled ? "" : "disabled"}>
          ${senseTag(o) ? `<span class="k sense">${esc(senseTag(o))}</span>` : o.tag ? `<span class="k rn-tag ${rnPathClass(o.tag)}">${esc(o.tag)}</span>` : evOf(m, o) ? evIconHtml(evOf(m, o)) : `<span class="k">${o.id.startsWith("move:") ? "→" : o.id.startsWith("road:back") ? "↩" : i + 1}</span>`}${evOf(m, o) ? evLabelHtml(o, evOf(m, o)) : optLabelHtml(o)}
        </button>`).join("")}${modesLast ? modes : ""}
      </div>`;
    // 有所感選做法（explain-2）：鈕底下兩行小字（做法跟此地的關係、意境拿來做什麼），排在做法後面，不把做法往下推
    const senseNotes = !idleMenu(m) && m.sense_help && m.sense_help.lines && m.sense_help.lines.length
      ? `<div class="act-notes sense-notes">${m.sense_help.lines.map((t) => `<p>${esc(t)}</p>`).join("")}</div>` : "";
    // 在路上，那段固定的說明只露兩行、點了看全文（FB-055）：剛按完路上小事時「剛剛」的結果卡會長高，狀態列又有提示的話，
    // 最後一排小事會掉到分頁列底下；說明的內容路上的選項與捷徑本來就寫著。展開記在 S.sceneOpen，下了路就清掉
    if (!m.on_road) S.sceneOpen = false;
    // 序章：師父在說話時草廬那張地點描寫卡不畫（masterTalksOf，那裡寫著為什麼）
    const masterTalks = masterTalksOf(m);
    // 「此地還有」與別人遞來的邀請、結伴那一行：平常畫在場景卡底下；決戰輪到你出招時（FB-117 第七件）挪到三招後面另一張卡——
    // 營地裡人多時名單有兩三行，排在三招上面就把第三招擠到分頁列底下（375×812：三招 647～791，分頁列頂 756）
    const myTurn = opts.some((o) => o.id.startsWith("battle:act:"));
    const people = (m.here && m.here.length ? hereHtml(m) : "") + (m.party || (m.calls && m.calls.length) ? socialHtml(m) : "");
    const scene = masterTalks ? ""
      : m.on_road
        ? `<section class="card scene road${S.sceneOpen ? "" : " clamp"}" data-act="scene-more" role="button" tabindex="0" aria-expanded="${!!S.sceneOpen}">${m.scene}</section>`
        : `<section class="card scene${m.art ? " has-art" : ""}${tierClass(m)}">${m.art ? sceneArtHtml(m.art) : ""}${tierTag(m)}${battleInner(m)}${myTurn ? "" : people}</section>`;
    const peopleAfter = myTurn && people && !masterTalks && !m.on_road ? `<section class="card people-after">${people}</section>` : "";
    const week = peekWeek(m);
    // 本週卡（減法季批 1，整合設計 6.1）排在最上面、「剛剛」之前（在路上排到選項底下，FB-055）：吃掉以前那一排小標。來信到了換成來信（回了信或收起來才換回本週卡）；
    // 還沒投靠的人最上面先是三方卡（sidesFirstHtml）。戰況圖卡、軍備與小地圖從江湖頁拿掉（6.3），戰況與軍備在見聞・大事
    const letterCard = letterHtml(m.letter);
    const pushAsk = letterCard && typeof pushAskHtml === "function" ? pushAskHtml(m) : ""; // 第一次來信時信的小卡底下問一次手機通知（批 9；pushAskHtml 在 app.js，只切 main.js 的網頁測試沒有它）
    // 開局頭一刻（整合設計 6.7，批 7）：人物開口的那一封（letter.open）排在三方卡前面——先聽人說話，再看三方；其餘時候三方卡照舊在最上面
    // 本週卡：灰線（一行）照舊在最上面，「眼下要事」排在行動列底下（Joy 2026-10-26：四顆行動鈕一定在第一屏）；來信到了照舊換成來信
    // 合併的本週卡（2026-11-07）裡已經有章回與投靠鈕：卡在的時候不另畫章回卡與三方卡；收起來（×）只剩章回卡、三方卡照舊
    const box = !letterCard && m.week_card && shown("quest") && !wkHidden(m, "strip");
    const sidesFirst = box || (m.on_road && m.week_card && shown("quest") && !wkHidden(m, "strip")) ? "" : sidesFirstHtml(m);
    const ckPop = typeof ckPopHtml === "function" && !pro() ? ckPopHtml(m) : ""; // 每天第一次登入的簽到小窗（checkin.js）
    const peek = ckPop + (letterCard && m.letter.open ? letterCard + pushAsk + sidesFirstHtml(m) : sidesFirst + (letterCard ? letterCard + pushAsk : weekCardHtml(m, "top")));
    const weekCard = letterCard ? "" : weekCardHtml(m, "low");
    // 休季的結算卡排在最上面（計畫 T9）；季收了、有行狀時緊接一張「讀你的傳」（玩家傳第二批，m.zhuan）
    const resultCard = (m.season_result ? resultHtml(m.season_result) : "") + (m.zhuan ? zhuanEntry(m.zhuan, "這一季收了，史官替你立傳", "讀你的傳") : "");
    const letter = dailyCardHtml(m); // 月卡今天的份還沒領時「剛剛」上面一張（書信小卡在本週卡的位置，見上面）
    // 本週軍令排在行動列（與路上捷徑）下面、三條戰況上面：不擠掉第一屏的「剛剛」、場景與行動列（計畫 T6）
    // 收起來照週記；21 天季的軍令每天一道，照季曆第幾天記（status.calendar.day），隔天的新軍令重新展開
    const orderKey = (m.status && m.status.calendar && m.status.calendar.day) || week;
    const orderCard = (m.orders || m.convoy) && shown("orders") ? ordersHtml(m.orders || [], orderKey, m.convoy) : "";
    // 懸賞卡跟軍令卡排在一起（散人沒有軍令，這張就是他的）：手上沒揭、也沒有合用的求兵可以交時就不畫（status.bounties 兩種都收）
    const bountyCard = m.status && m.status.bounties && m.status.bounties.length && shown("orders") ? bountiesHtml(m.status.bounties, m.options) : "";
    const sealCard = m.status && m.status.seal_duel && shown("orders") ? sealDuelHtml(m.status.seal_duel) : "";
    const sealMine = m.status && m.status.seal && shown("orders") ? sealHtml(m.status.seal) : "";
    // 序章第一步（還沒遇到師父）：選項底下一行「略過序章」，不想走序章的人直接站到起點（設計 7.3）
    const skip = pro() && pro().skip ? '<button class="linkish skip-prologue" data-act="do" data-op="skip_tutorial">略過序章</button>' : "";
    // 劇情文字在上、行動在下（企劃者 2026-10-04）。行動列只有一排，375×812 上「剛剛」、場景與整排行動都在第一屏。
    // 路上的三個捷徑（links）緊接在場景（「也可以打開輿圖改去別處，或去修練、煉製」那一段）底下、選項上面：
    // 排在路上的五六顆選項底下時落在第一屏外，要捲才看得到（FB-048）。說書人的話緊貼在行動上方（引導重做設計 8.1）
    const guide = guideHtml(m.guide, m.on_road);
    // 說書人、師父的話：序章裡緊貼在行動上方（引導重做設計 8.1）；序章以外排在行動列與「眼下要事」底下（Joy 2026-10-26「至少要在行動鈕下面」）
    const guideUp = pro() ? guide : "", guideDown = pro() ? "" : guide;
    // 在路上（FB-055）：路上的五個選項要全在第一屏（375×812），所以那一排小標與說書人的框都排在選項底下——
    // 不是這一刻要按的；捷徑還是緊接在場景底下（FB-048）
    const hints = jhHintsHtml(m);
    if (m.on_road) return `${ckPop}${hints}${resultCard}${letter}${letterCard}${pushAsk}${now}${scene}${links}${free}${menu}${guide}${sidesFirst}${weekCardHtml(m)}${orderCard}${bountyCard}${sealMine}${sealCard}`;
    // 決戰輪到你出招的回合（FB-136）：三招緊接在場景底下，放手一搏的輸入框與說書人的框排在三招後面（同在路上，這一刻要按的排前面）。
    // 開打那一刻場景多了戰局條、這一幕的開場、騎兵那一句，框與輸入框再排在上面的話三招整排落到分頁列底下（14 天、騎著馬、框還在：855～999）
    // 戰場面板（battle.js，Joy 2026-11-06 大決戰優化，設計稿方案甲）：開打、集結時排在最上面，出招鈕與放手一搏的輸入框緊接在面板裡；
    // 本週卡、「剛剛」與場景卡排到面板底下（第一屏是倒數、主將、出招）
    const bp = bpOn(m) ? bpPanelHtml(m, myTurn ? free : "") : "";
    if (bp && myTurn) {
      return `${hints}${resultCard}${bp}${bpDropMoves(menu)}${scene}${peopleAfter}${guide}${letter}${peek}${now}${links}${senseNotes}${weekCard}${skip}${orderCard}${bountyCard}${sealMine}${sealCard}`;
    }
    if (myTurn) {
      return `${hints}${resultCard}${peek}${letter}${now}${scene}${links}${menu}${peopleAfter}${free}${guide}${senseNotes}${weekCard}${skip}${orderCard}${bountyCard}${sealMine}${sealCard}`;
    }
    const planCard = planHtml(m.plan) + placeDeedsHtml(m.place_deeds); // 世界活起來：行動列與眼下要事底下（四顆行動鈕一定在第一屏）
    if (m.art && m.art.kind === "place") S.lastPlaceArt = m.art.src; // 對話那一層的底圖（vnBack）
    if (typeof revampOn === "function" && revampOn(m) && !masterTalks) { // 介面重整（見檔尾「介面重整」那一段）
      const parts = dutyParts(m, { orderCard, bountyCard, planCard, weekCard, sealMine, sealCard });
      const inner = battleInner(m);
      const clamp = !S.sceneRvOpen && !/<button|<form/.test(inner);
      const social = m.party || (m.calls && m.calls.length) ? socialHtml(m) : "";
      const sceneR = `<section class="card scene rv${m.art ? " has-art" : ""}${tierClass(m)}">${m.art ? sceneArtHtml(m.art) : ""}${now ? `<div class="rv-now">${now}</div>` : ""}${tierTag(m)}<div class="rv-scene${clamp ? " clamp" : ""}"${clamp || S.sceneRvOpen ? ' data-act="rv-scene" role="button" tabindex="0"' : ""}>${inner}</div>${social}</section>`;
      const extras = S.hereExtras || [];
      const layers = (S.dutyOpen ? dutySheetHtml(parts) : "") + (S.hereAll ? hereAllHtml(m, extras) : "") + (S.figLog ? figLogHtml() : S.fig ? figPickHtml(m) : "");
      return `${hints}${resultCard}${bp}${peek}${letter}${sceneR}${links}${free}${dutyCardHtml(m, parts)}${bp ? bpDropMoves(menu) : menu}${sealCard}${senseNotes}${hereRowHtml(m, extras)}${peopleRowHtml(m)}${guideDown}${skip}${layers}`;
    }
    if (typeof uiV2 === "function" && uiV2() && m.talk && !m.card) return `${hints}${resultCard}${vnTalkHtml(m, menu)}${free}${guide}`; // 跟大勢人物說話：浮在最上層的對話框
    return `${hints}${resultCard}${bp}${peek}${letter}${now}${scene}${links}${guideUp}${free}${bp ? bpDropMoves(menu) : menu}${senseNotes}${weekCard}${planCard}${guideDown}${skip}${orderCard}${bountyCard}${sealMine}${sealCard}`;
  }



  // 武學屬性有什麼用（W2、FB-089：標題冠上「武學」，跟升級配點的「屬性」分開）：修練、煉製兩頁各摺一行，收著只多一行小字。說明的字是伺服器照程式的規則寫的（skillview.attribute_line），
  // 這裡只放進去；標題那四個字待 joy 潤。伺服器沒給（舊版）就不畫。
  const attrNoteHtml = (x) => (x.attribute_note ? `<details class="attr-note"><summary>武學屬性有什麼用</summary><p>${esc(x.attribute_note)}</p></details>` : "");




  // ── 介面重整（2026-11-05；Joy「操作簡單 回饋直覺 畫面有質感」，設計稿 DteufxiW32frkMzxaJHWo5，Joy 挑「四塊一次做」）──
  // 江湖頁閒著的時候：場景卡（「剛剛」疊在圖底下）、要事一張卡（點了往上拉一張清單）、四顆行動、此地可為一排圓章、此地人物一排。
  // 以前排在底下的軍令、懸賞、盤算、玉璽、本週卡低的那一半都收進要事清單；「此地還能做 N 件事」的摺疊換成圓章與「全部」。
  // 序章、初入江湖（要你按的鈕在摺疊裡）、路上、決戰出招、事件與對話都照舊（revampOn 是假）。
  // uiV2()：介面重整之後一律是新版面（2026-11-06 合進 develop、舊測試搬完）。序章、初入江湖、路上、決戰出招、事件照舊（revampOn 是假）。
  // 只切幾個函式出來測的舊測試沒有這一段，所以用到的地方寫 typeof uiV2 === "function"，切出來時照舊版面
  const uiV2 = () => true; // 介面重整之後只有新版面；舊版面的分支（序章、初入江湖照舊）之後一起清
  const revampOn = (m) => uiV2() && idleMenu(m) && !pro() && !onb() && !m.on_road;
  // 此地可為的圓章圖（web/img/here/，第一批圖）：選項 id 或開頭 → 圖名；沒有圖的畫一個墨圈寫第一個字
  const HERE_ART = [["act:bounties", "bounty"], ["act:arena", "arena"], ["act:dadian", "bribe"], ["act:tavern", "tavern"], ["act:heal", "clinic"],
    ["act:market", "horses"], ["act:smith", "smith"], ["feast:", "feast"], ["act:feast", "feast"], ["faction:", "faction"], ["defect:", "faction"]];
  const hereArt = (id) => (HERE_ART.find(([k]) => id === k || (k.endsWith(":") && id.startsWith(k))) || [])[1] || "";
  const HERE_ROW = 5; // 一屏放得下幾個圓章：多過這個數（或名字寫不完）時標題旁多一個「全部」列整串的全名
  const HERE_ALL = "全部"; // 待 joy 潤
  const PEOPLE_HEAD = "此地人物"; // 待 joy 潤
  const HERE_HEAD = "此地可為"; // 待 joy 潤
  // 點了人物才畫的那幾顆（護衛、犒軍、挑戰本人），與搬去酒肆的招募：不進此地可為
  const FIG_ACT = /^(aid:guard:|aid:rally:|act:challenge:)/;
  const HIRE = /^hire:/;
  // 行動列四格的墨圖（web/img/acts/，金色水墨）：格子的 key → 圖名
  const ACT_ART = { explore: "explore", train: "sortie", social: "social", move: "move" };
  const ink = (key) => (ACT_ART[key] ? `<img class="ink-img" src="/static/img/acts/${ACT_ART[key]}.webp" alt="" aria-hidden="true">` : "");

  // 此地可為的先後（Joy 2026-11-06「未了之事如果是可以做的時候優先級應該做高，如果時機未到可以放在後面」）：
  // 發光的（序章指路）、論武的答應、做得了的未了之事（story:）排最前；再來是按得下去的；按不下去的在後；時機未到的未了之事最後。
  // 同一級照伺服器的順序（sort 是穩定的）
  const STORY = /^story:/;
  function hereSort(list, glow, peers) {
    const rank = (o) => (glow.includes(o.id) || peers[o.id] || (o.enabled && STORY.test(o.id)) ? 0 : o.enabled ? 1 : STORY.test(o.id) ? 3 : 2);
    return [...list].sort((a, b) => rank(a) - rank(b));
  }
  // 此地可為：圓章一排（照伺服器的順序，發光的、按得下去的排前面），「全部 N ›」打開整串（S.hereAll）
  function hereRowHtml(m, extras) {
    const list = extras.filter((o) => !FIG_ACT.test(o.id) && !HIRE.test(o.id));
    if (!list.length) return "";
    const glow = guideGlow();
    const peers = callPeers(m); // 論武的「答應」：引擎不收那一顆，點了打開對方的玩家卡（同「全部」那一串，FB-117）
    const row = hereSort(list, glow, peers); // 一排橫滑（Joy 11/6「應該是要可以滑動的」）：全部畫出來，「全部」照舊列整串的全名
    const seal = (o) => {
      const [label, detail] = optParts(o);
      const art = hereArt(o.id);
      const n = /^(\d+) 張$/.exec(detail);
      const attrs = peers[o.id] ? `data-act="peer-answer" data-name="${esc(peers[o.id])}"` : o.enabled ? `data-act="choose" data-id="${esc(o.id)}"` : o.note || detail ? `data-act="opt-why" data-id="${esc(o.id)}" data-why="${esc(o.note || `${detail}。`)}" aria-disabled="true"` : "disabled";
      return `<button class="here-seal${o.enabled || peers[o.id] ? "" : " off"}" ${attrs}><span class="hs-tile${art ? "" : " ink"}">${art ? `<img src="/static/img/here/${art}.webp" alt="">` : `<i>${esc(label.slice(0, 1))}</i>`}${n ? `<b class="hs-n">${n[1]}</b>` : ""}</span><span class="hs-name">${esc(label.replace(/^(.{0,5}).*$/, "$1"))}</span></button>`;
    };
    return `<section class="here-row"><div class="hr-head"><span>${HERE_HEAD}</span>${list.length > HERE_ROW || list.some((o) => optParts(o)[0].length > 5)
      ? `<button class="linkish" data-act="here-all">${HERE_ALL} ${list.length} ›</button>` : ""}</div><div class="hr-seals">${row.map(seal).join("")}</div></section>`;
  }
  function hereAllHtml(m, extras) {
    const tavernHere = extras.some((o) => o.id === "act:tavern"); // 此地沒有酒肆（或酒肆關著）時招募留在全部裡，不會找不到
    const list = extras.filter((o) => !FIG_ACT.test(o.id) && (!HIRE.test(o.id) || !tavernHere));
    const peers = callPeers(m);
    return `<div class="sheet-bg" data-act="here-all-close"></div><div class="sheet here-all" role="dialog" aria-label="${HERE_HEAD}"><div class="grip"></div>
      <div class="top-row"><h3 style="flex:1">${HERE_HEAD}</h3><button class="btn small ghost" data-act="here-all-close">關閉</button></div>
      <div class="options">${hereSort(list, guideGlow(), peers).map((o) => persuadingNow(o) ? persuadeForm(o) : peers[o.id]
        ? `<button class="btn" data-act="peer-answer" data-name="${esc(peers[o.id])}"><span>${esc(o.label)}</span></button>`
        : `<button class="btn" data-act="choose" data-id="${esc(o.id)}" ${o.enabled ? "" : "disabled"}><span>${dealHtml(o.label)}</span></button>`).join("")}</div></div>`;
  }

  // 此地人物：大勢人物（藍）與江湖人（綠）一排小籤，一籤一個頭像、名字、身分那一行。點大勢人物打開「點人物之後」（S.fig），
  // 點江湖人照舊打開玩家卡。人多時同「此地還有」先列 HERE_SHOW 個
  function peopleRowHtml(m) {
    const figs = m.figures_here || [];
    const all = m.here || [];
    if (!figs.length && !all.length) return "";
    const open = true; // 一排橫滑（Joy 11/6）：此地的人全部畫出來，滑著看
    const players = all;
    const face = (src, name) => (src ? `<span class="pc-face"><img src="${esc(src)}" alt=""></span>` : `<span class="pc-face pc-ch">${esc(name.slice(0, 1))}</span>`);
    const chips = figs.map((f) => `<button class="person fig" data-act="fig-open" data-id="${esc(f.id)}">${face(f.face, f.name)}<span class="pc-t"><b>${esc(f.name)}</b><small>大勢人物・${esc(f.talk.via ? "可交談" : f.talk.why || "")}</small></span></button>`)
      .concat(players.map((p) => `<button class="person peer" data-act="peer" data-name="${esc(p.name)}">${face(null, p.name)}<span class="pc-t"><b>${esc(p.name)}</b><small>江湖人・${esc(p.side)}</small></span></button>`));
    return `<section class="people-row"><div class="hr-head"><span>${PEOPLE_HEAD}</span>${open ? "" : `<button class="linkish" data-act="here-more">還有 ${all.length - HERE_SHOW} 人 ›</button>`}</div><div class="pr-chips">${chips.join("")}</div></section>`;
  }

  // 要事：軍令、懸賞、盤算、本週卡、玉璽、託付……收成一張卡（第一行是最要緊的那一件），點了往上拉一張清單（S.dutyOpen），清單裡照舊是原本那幾張卡
  const DUTY_HEAD = "要事"; // 待 joy 潤
  const DUTY_NOTE = "此地舊事、人物閒話在「見聞」"; // 待 joy 潤
  function dutyCardHtml(m, parts) {
    const got = parts.filter((p) => p.html);
    if (!got.length) return "";
    const chips = got.map((p) => `<span class="dc-chip">${esc(p.name)}${p.n ? ` ${p.n}` : ""}</span>`).join("");
    const first = got[0];
    return `<button class="card duty-card" data-act="duty-open" aria-expanded="${!!S.dutyOpen}"><span class="dc-head"><b>${DUTY_HEAD} <i>${got.length}</i></b><span>全部 ›</span></span>
      <span class="dc-first"><span class="dc-seal">${esc(first.seal)}</span><span class="dc-line">${esc(first.line || first.name)}</span></span><span class="dc-chips">${chips}</span></button>`;
  }
  function dutySheetHtml(parts) {
    return `<div class="sheet-bg" data-act="duty-close"></div><div class="sheet duty-sheet" role="dialog" aria-label="${DUTY_HEAD}"><div class="grip"></div>
      <div class="top-row"><h3 style="flex:1">${DUTY_HEAD}</h3><button class="btn small ghost" data-act="duty-close">關閉</button></div>
      ${parts.filter((p) => p.html).map((p) => p.html).join("")}<p class="muted duty-note">${DUTY_NOTE}</p></div>`;
  }
  const firstText = (html) => { const t = document.createElement("template"); t.innerHTML = html; const el = t.content.querySelector("h3, summary, b, strong, p"); return el ? el.textContent.trim().slice(0, 24) : ""; };
  function dutyParts(m, blocks) {
    const orders = (m.orders || []).length, bounties = (m.status && m.status.bounties || []).length;
    return [
      { key: "orders", name: "軍令", seal: "令", n: orders || "", html: blocks.orderCard, line: (m.orders && m.orders[0] && (m.orders[0].title || m.orders[0].text)) || "" },
      { key: "bounty", name: "懸賞", seal: "賞", n: bounties || "", html: blocks.bountyCard, line: "" },
      { key: "plan", name: "盤算", seal: "謀", n: "", html: blocks.planCard, line: "" },
      { key: "week", name: "本週", seal: "週", n: "", html: /class="wk-none"/.test(blocks.weekCard || "") ? "" : blocks.weekCard, line: "" }, // 只剩空記號（要做的都有自己一張卡）不算一件
      { key: "seal", name: "玉璽", seal: "璽", n: "", html: blocks.sealMine, line: "" }, // 正在打的奪璽（sealCard）有倒數、要你出招：不收，畫在行動列底下
    ].map((p, i) => ({ ...p, line: p.line || (p.html ? firstText(p.html) : ""), now: dutyNow(p.html), i }))
      .sort((a, b) => (b.now - a.now) || (a.i - b.i)); // 現在做得了的（卡上有一顆按得下去的鈕）排前面，時機未到的在後面；同一級照原本的順序
  }
  // 要事那一張卡此刻做得了嗎：卡裡有一顆按得下去、會真的去做的鈕（choose、去輿圖、出招），收合、說明那種不算
  const DUTY_GO = /data-act="(choose|tab)"|class="[^"]*\bprimary\b/;
  function dutyNow(html) {
    return (String(html || "").match(/<button\b[^>]*>/g) || []).some((b) => DUTY_GO.test(b) && !/\sdisabled\b/.test(b)) ? 1 : 0;
  }


