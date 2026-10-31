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
  // 託付的勸降（減法季批 6，主機側計畫 1.3）：此地的「勸降」按了不送 /api/choose，就地換成二十字的輸入框（S.persuading 記那一顆的 id），
  // 送 POST /api/do/persuade_text {id: 那一件託付, text}（persuadeSay）
  const PERSUADE_PREFIX = "errand:persuade:";
  const PERSUADE_HINT = "怎麼勸他？（20字內）"; // 待 joy 潤：輸入框的提示
  const PERSUADE_GO = "勸他"; // 待 joy 潤：送出鈕
  function persuadeForm(o) {
    return `<form class="free answer persuade" id="persuade-form" data-id="${esc(o.id.slice(PERSUADE_PREFIX.length))}"><input class="input" name="text" maxlength="20" placeholder="${esc(PERSUADE_HINT)}" aria-label="${esc(o.label)}"><button class="btn primary small" type="submit">${esc(PERSUADE_GO)}</button></form>`;
  }
  const persuadingNow = (o) => S.persuading === o.id && o.enabled;
  // 神品意境「自己取一個名字…」（epiphany.OPTION:OWN）：按了不送 /api/choose，就地換成輸入框（S.godNaming 記著），
  // 送出時帶 text（godName）。以前這一顆按下去只回一句「（寫下你替它取的名字。）」，沒有地方寫，等於按不動（FB-901）
  const OWN_NAME_ID = "dunwu:own";
  const OWN_NAME_HINT = "這個境界叫什麼？（2～6 字）"; // 待 joy 潤：輸入框的提示
  const OWN_NAME_GO = "就叫這個"; // 待 joy 潤：送出鈕
  function ownNameForm(o) {
    return `<form class="free answer own-name" id="own-name-form"><input class="input" name="text" maxlength="6" placeholder="${esc(OWN_NAME_HINT)}" aria-label="${esc(o.label)}"><button class="btn primary small" type="submit">${esc(OWN_NAME_GO)}</button></form>`;
  }
  const namingGodNow = (o) => S.godNaming && o.id === OWN_NAME_ID && o.enabled;
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
  const inkCell = (key, name, sub, icon, attrs, cls, note = "") => `<button class="act-ink${cls}" data-key="${key}" data-glow="act:${key}" ${attrs}>
      <svg class="ink-icon" viewBox="0 0 24 24" aria-hidden="true">${icon}</svg><b>${inkName(name)}</b><small>${esc(sub)}</small>${
      note ? `<small class="ink-note ${ODDS_TONE[note] || ""}">${esc(note)}</small>` : ""}</button>`;

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
  function withGauge(html, g) {
    if (!g || html.startsWith('<p class="battle-fold"')) return html;
    const muster = html.startsWith('<div class="muster-head">') ? html.indexOf("</div></div>\n") : -1;
    const cut = muster >= 0 ? muster + "</div></div>\n".length : html.startsWith("<p>") ? html.indexOf("</p>") + 4 : 0;
    return html.slice(0, cut) + gaugeHtml(g) + html.slice(cut);
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
      const attrs = duelCell ? `data-act="sortie-open" aria-expanded="${duelOpen}"`
        : wheel ? `data-act="wheel" data-key="explore" aria-expanded="${exploreOpen}"`
        : drillFull ? `data-act="drill-full" aria-expanded="${S.wheelSel === "move"}"` // 格子自己的 data-key 是 practice，不能再寫一個
        : o.enabled ? `data-act="choose" data-id="${esc(o.id)}"`
        : why ? `data-act="opt-why" data-why="${esc(why)}" aria-disabled="true"` : "disabled";
      return inkCell(d.key, name, sub, d.icon, attrs, (o.enabled || duelOpen ? "" : " off") + ((wheel && exploreOpen) || duelOpen ? " on" : ""), note);
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
    const here = extras.length ? `<details class="fold here"${hereFold(m, hotHere) ? " open" : ""}><summary>此地還能做 ${extras.length} 件事</summary><div class="fold-body options">${extras.map((o) => persuadingNow(o) ? persuadeForm(o) : peers[o.id] ? `
        <button class="btn" data-act="peer-answer" data-name="${esc(peers[o.id])}"><span>${esc(o.label)}</span></button>` : `
        <button class="btn" data-act="choose" data-id="${esc(o.id)}" ${o.enabled ? "" : "disabled"}><span>${dealHtml(o.label)}</span></button>`).join("")}</div></details>` : "";
    const drawn = cells.filter(Boolean); // 序章裡沒亮的格子是空字串；一格都沒有、也沒有「此地還能做」時整條不畫
    // 出陣約戰（丙）：出陣前那張卡（或應戰那一張）展開在行動列底下，約戰卡一張一行接在它下面（應戰時收起，同一張卡已經寫著那一場）
    const duelPanel = sortiePanelHtml(m);
    const duelList = sortieAnswering(m) ? "" : sortieDuelsHtml(m);
    // 以前行動列底下還有每一格的說明三行與「玩法說明 ›」（explain-1、2）：減法季批 1 拿掉了（整合設計 6.3；說明在本週卡的「為什麼」與設定裡）
    return `${sealRow}${summonsRow}${drawn.length ? `<div class="act-bar" role="group" aria-label="行動" style="--cells:${Math.max(4, drawn.length)}">${drawn.join("")}</div>` : ""}${moveCard}${exploreCard}${duelPanel}${duelList}${here}`;
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

  // 找素材分支（第 32 項，計畫 2.1 甲）：「找素材」那一顆是展開鈕（再點一次收起；入口灰著〔分支都按不下去〕時不展開），
  // 點開了在它底下攤一排分支（兩欄：名字一行、「體力 6・剛、慢」一行），最後一顆「自己說…」佔一整列；點了「自己說…」換成 20 字的
  // 輸入框（S.gatherSaying），送 /api/do/gather_text（gatherSay）。展開記在 S.gatherOpen，做完一件事不收（下次點探索就直接看到分支，
  // 少按一下）；換到沒有分支的地方就不畫。字待 joy 潤
  // 輸入框的提示照別的 20 字輸入框寫字數（隨口應對「…（20字內）」、對話「想對他說的話（20字內）」）。這一格縮在分支那一排裡，比那兩格窄：
  // 320 寬扣掉內距只剩 152 像素（16px 的字九個多），原本的「怎麼找？例：沿著獸徑找落羽」208 像素切在「沿著獸徑」，例句拿掉（FB-460）
  const GATHER_SAY_HINT = "怎麼找？（20字內）"; // 待 joy 潤：輸入框的提示
  const GATHER_SAY_GO = "去找"; // 待 joy 潤：送出鈕
  function gatherWheel(o, branches) {
    const open = !!S.gatherOpen && o.enabled;
    const head = `
          <button class="btn gather-head${open ? " on" : ""}" data-act="gather-wheel" aria-expanded="${open}" ${o.enabled ? "" : "disabled"}><span>${esc(o.label)}</span><span class="gather-caret" aria-hidden="true">${open ? "▴" : "▾"}</span></button>`;
    if (!open) return head;
    const say = branches.find((b) => b.id === GATHER_SAY_ID);
    const saying = !!(say && S.gatherSaying && say.enabled);
    // 兩欄排，分支是單數條時最後一條佔整列（.wide），旁邊不留一格空的（FB-461：嵩山深處挖礦、狩獵、深入，深入旁邊空著）
    const real = branches.filter((b) => b.id !== GATHER_SAY_ID);
    const wide = real.length % 2 ? real[real.length - 1].id : null;
    const cells = branches.filter((b) => !(saying && b.id === GATHER_SAY_ID)).map((b) => {
      const [name, detail] = optParts(b);
      return `<button class="btn gather-branch${b.id === GATHER_SAY_ID ? " say" : b.id === wide ? " wide" : ""}" data-act="choose" data-id="${esc(b.id)}" ${b.enabled ? "" : "disabled"}><span class="gb-text"><b>${esc(name)}</b>${detail ? `<small>${nbHtml(detail)}</small>` : ""}</span></button>`;
    }).join("");
    const form = saying ? `<form class="free answer gather-say" id="gather-say-form"><input class="input" name="text" maxlength="20" placeholder="${esc(GATHER_SAY_HINT)}" aria-label="${esc(say.label)}"><button class="btn primary small" type="submit">${esc(GATHER_SAY_GO)}</button></form>` : "";
    return `${head}<div class="gather-branches" role="group" aria-label="找素材">${cells}${form}</div>`;
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

  // 要發光的那一條路（FB-9001，QA 2026-10-28）：約戰卡別區那一行的「前往 N 分」、新手目標的「去做」展開移動之後，往那一處的那一條發光。
  // 記在 S.glowRoute（move:<地點>）：畫移動卡時直接寫進 class（routeGlowOn），applyGlow 清掉所有 .glow 之後也補回（routeGlowKey），
  // 所以重插的摺疊觸發 toggle、輪詢重畫都不會把光清掉（以前展開之後 .glow 直接加在畫好的元素上，24 毫秒內的 toggle 或下一次重畫就沒了）。
  // 什麼時候熄掉（都在重畫時判斷，不設計時器）：移動卡收起或換別格（S.wheelSel 不是 move；按了選項送出去之後 choose 也會收起移動卡）、
  // 換分頁、移動清單上沒有那一條了（走了、換了地方）
  const routeHit = (id, key) => id === key || id.startsWith(`${key}:`); // 疾行的 id 後面多接走法
  function routeGlowKey(m = S.main) {
    const key = S.glowRoute;
    if (!key) return "";
    const live = S.tab === "jianghu" && S.wheelSel === "move" && !!m && (m.options || []).some((o) => routeHit(o.id, key));
    if (!live) S.glowRoute = null;
    return live ? key : "";
  }
  function routeGlowOn(m, id) {
    const key = routeGlowKey(m);
    return !!key && routeHit(id, key);
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

  // 第一季濃縮版的「本週軍令」（計畫 T6；伺服器只送自己陣營的，散人沒有）：預設展開，收起來的狀態照週次記住
  function ordersHtml(list, week, convoy) {
    const done = list.filter((o) => o.done).length;
    const cart = convoy ? `<div class="order-cart">🛒 ${esc(convoy)}</div>` : "";  // 押著的糧車（那一道沒了也照樣寫）
    const rows = list.map((o) => `
      <div class="order${o.done ? " done" : ""}">
        <div class="order-head"><b>${esc(o.title)}</b><span>${o.done ? "已達成" : `陣營 ${o.progress}／${o.quota}`}</span></div>
        <div class="order-text">${esc(o.text)}</div>
        ${o.how ? `<div class="order-how">${esc(o.how)}</div>` : ""}
        <div class="order-bar" role="meter" aria-valuemin="0" aria-valuemax="${o.quota}" aria-valuenow="${o.progress}" aria-label="${esc(o.title)}"><i style="width:${pct(o.progress, o.quota)}%"></i></div>
        <div class="order-meta">你做了 ${o.mine} 次・截止 ${esc(o.deadline)}</div>
      </div>`).join("");
    return `<details class="fold orders" data-week="${week}" ${S.ordersShut === week ? "" : "open"}>
      <summary>📜 ${wkWord("order_this", "本週")}軍令（${list.length}${done ? `，已達成 ${done}` : ""}）</summary><div class="fold-body">${cart}${rows}</div></details>`;
  }

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

  // 人物的盤算（世界活起來，main.plan）：全服開著的盤算裡最切身的一件，行動列底下一張卡。誰打算做什麼、在哪、什麼時候見分曉、
  // 兩邊各幾人；人在那裡就有「助一臂」「壞他的事」（就是選單上的 plan: 選項，按了走 choose），不在那裡寫走過去幾分鐘、一顆去輿圖。字都是伺服器寫好的
  function planHtml(x) {
    if (!x) return "";
    const far = x.minutes ? `步行約 ${x.minutes} 分鐘` : x.minutes === 0 ? "就在這裡" : "";
    const mine = x.mine === "help" ? "你已經出過力了" : x.mine === "block" ? "你已經出過手了" : "";
    const acts = x.acts && x.acts.length
      ? x.acts.map((a) => `<button class="btn small${a.id.includes(":help:") ? " primary" : ""}" data-act="choose" data-id="${esc(a.id)}">${esc(a.label)}</button>`).join("")
      : !mine && x.minutes && shown("tab:map") ? `<button class="btn small" data-act="tab" data-tab="map"${gotoAttrs(x.location)}>去${esc(x.place)} ›</button>` : "";
    return `<section class="card plan-card"><div class="plan-k">${esc(x.head)}</div>
      <p class="plan-text">${esc(x.text)}</p>
      <div class="plan-meta"><span>${esc(x.place)}${far ? `・${esc(far)}` : ""}</span><span>${esc(x.when)} 見分曉</span></div>
      <div class="plan-meta"><span>助${esc(x.help_side)}一方 ${x.help | 0} 人</span><span>壞事 ${x.block | 0} 人</span></div>
      ${mine ? `<div class="plan-mine">${esc(mine)}</div>` : ""}${acts ? `<div class="row">${acts}</div>` : ""}</section>`;
  }

  // 此地舊事（世界活起來，main.place_deeds）：這裡最近的幾筆世界記事，一行一筆
  function placeDeedsHtml(list) {
    if (!list || !list.length) return "";
    return `<section class="card place-deeds"><div class="pd-k">此地舊事</div>${list.map((d) =>
      `<p><span class="pd-when">${esc(d.when)}</span>${esc(d.text)}</p>`).join("")}</section>`;
  }

  // 手上揭了的懸賞，加上身上有合用兵器的求兵（status.bounties，bounties.status；後者多一行 have）：一張一行，怎麼交差、賞什麼。懸賞榜在城鎮才看得到，
  // 選單上有 act:bounties 時卡底下一顆「看懸賞榜」（就是那個選項，按了走 choose），不在城鎮寫一句去哪裡看。
  // 預設展開，收起來的狀態照手上那幾張記住（S.bountyShut）：揭了新的、交了差，清單變了就重新展開
  // 21 天季的賞拆成小籤（企劃者挑第 5 批畫面第三組丙；bounties.reward_tags）：一樣一格，附的那一樣金框、重賞紅框。字與數字照伺服器給的
  function rewardChips(tags) {
    return `<div class="rtags">${tags.map((t) => `<span class="rtag${t.kind ? ` ${esc(t.kind)}` : ""}">${t.k ? `<em>${esc(t.k)}</em>` : ""}${esc(t.v)}</span>`).join("")}</div>`;
  }

  function bountiesHtml(list, options) {
    const key = list.map((b) => b.id).join(",");
    const board = (options || []).find((o) => o.id === "act:bounties");
    const level = (list.find((b) => b.level) || {}).level; // 21 天季：「賞照你第 N 級」寫在卡頭
    const rows = list.map((b) => `
      <div class="order">
        <div class="order-head"><b>${esc(b.title)}</b><span>${esc(b.issuer)}</span></div>
        <div class="order-how">${esc(b.how)}</div>
        ${b.tags ? `<div class="order-meta">${rewardChips(b.tags)}</div>` : `<div class="order-meta">${esc(b.reward)}</div>`}
        ${b.due ? `<div class="order-meta">${esc(b.due)}</div>` : ""}
        ${b.have ? `<div class="order-meta">${esc(b.have)}</div>` : ""}
      </div>`).join("");
    // 懸賞榜正開著（第二層「返回」或第三層「回到懸賞榜」，選單就是榜）：卡底下不再寫什麼
    const open = (options || []).some((o) => o.id === "bounty:back" || o.id === "bounty:unpick");
    const foot = open ? "" : board
      ? `<button class="btn small" data-act="choose" data-id="act:bounties" ${board.enabled ? "" : "disabled"}>看懸賞榜</button>`
      : '<div class="order-meta">到城鎮的懸賞榜前，可以揭新的、放棄，或交出合用的兵器。</div>';  // 待 joy 潤（2026-10-21 拿掉求藝：不再寫「功夫」）
    return `<details class="fold bounties" data-key="${esc(key)}" ${S.bountyShut === key ? "" : "open"}>
      <summary>🪧 懸賞（${list.length}）${level ? `<span class="order-level">${esc(level)}</span>` : ""}</summary><div class="fold-body">${rows}${foot ? `<div class="bounty-foot">${foot}</div>` : ""}</div></details>`;
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

  // 每日簽到（21 天季，正式季整合 6.2；畫面照 9.1 第 4 組丙）：收進這一排小標，還沒簽亮紅點、簽了寫「簽到 ✔」。攤開是這一週七格
  // （最後一週到季末為止）、今天的份與領的鈕；四階的日子是四顆挑屬性的鈕（點一種就領）。伺服器沒給 status.checkin（週末與 14 天的季、
  // 序章裡、休季）就不畫。CK_LAST 待 joy 潤
  const CK_ATTR = { 剛: "gang", 柔: "rou", 快: "kuai", 慢: "man" };
  const CK_LAST = "這一季最後一天";
  // 格子上的短字（FB-436）：兩樣的那一格（第 6 天「丹2＋四階」）375、360 寬放不下一行，照「＋」拆兩行；一樣的照舊一行
  function ckGift(label) {
    const parts = String(label).split("＋");
    return parts.length < 2 ? esc(label) : parts.map((p, i) => `<span class="gl">${i ? "＋" : ""}${esc(p)}</span>`).join("");
  }
  function checkinPeek(m) {
    const k = m.status && m.status.checkin;
    if (!k) return null;
    const cells = k.week.map((d) => `<div class="ck-day ${d.state}${d.got ? " got" : ""}${d.four ? " four" : ""}"><span class="d">${d.day}</span><span class="g">${ckGift(d.label)}</span></div>`).join("");
    const act = k.done ? "" : k.pick
      ? `<div class="ck-pick">${k.pick.map((x) => `<button class="ck-p4 ${CK_ATTR[x.attribute] || ""}" data-act="checkin" data-attr="${esc(x.attribute)}"><b>${esc(x.attribute)}</b>${esc(x.name)}<small>有 ${x.held}</small></button>`).join("")}</div>`
      : '<button class="ck-go" data-act="checkin">領取</button>';
    return {
      id: "checkin",
      label: `簽到：第 ${k.day} 天${k.done ? "已簽" : "還沒簽"}`,
      chip: `<span class="peek-name">簽到${k.done ? " ✔" : ""}</span>`,
      flag: !k.done,
      dotNote: "",
      panel: `<div class="ck-head"><b>第 ${k.day} 天</b><span>${k.next ? `下一份：${esc(k.next)}` : CK_LAST}</span></div>`
        + `<div class="ck-week">${cells}</div><p class="ck-step">${esc(k.step)}</p>${act}`,
    };
  }

  // 新手目標（新手引導重做；tianxia/newbie.py，status.newbie）：引導走完、新手期裡收進這一排小標，攤開一次三條、每一條有「去做」。
  // 「去做」：go.tab 切到那一頁；go.move 是最近的那一處，移動清單上有那一條就展開移動、讓它發光，沒有就打開輿圖。字待 joy 潤
  const NEWBIE_GO = "去做", NEWBIE_DRIFTER = "就當散人";
  function newbiePeek(m) {
    const n = m.status && m.status.newbie;
    if (!n || !n.rows.length) return null;
    const rows = n.rows.map((r, i) => `<li class="nb-goal"><div><b>${esc(r.text)}</b><small>${esc(r.reward)}${r.go.place ? `・最近在${esc(r.go.place)}` : ""}</small></div>`
      + `<span class="nb-btns"><button class="btn small" data-act="newbie-go" data-i="${i}">${NEWBIE_GO}</button>`
      + `${r.drifter ? `<button class="btn small" data-act="newbie-drifter">${NEWBIE_DRIFTER}</button>` : ""}</span></li>`).join("");
    return {
      id: "newbie",
      label: `${n.title}：做到 ${n.done}／${n.total}`,
      chip: `<span class="peek-name">新手</span><span class="peek-nums">${n.done}/${n.total}</span>`,
      flag: true,
      dotNote: "",
      panel: `<ol class="nb-goals">${rows}</ol>`,
    };
  }
  function newbieGo(i) {
    const r = S.main && S.main.status && S.main.status.newbie && S.main.status.newbie.rows[i];
    if (!r) return;
    if (r.go.tab) { if (r.go.tab !== S.tab) goTab(r.go.tab); else window.scrollTo({ top: 0, behavior: "smooth" }); return; }
    const id = `move:${r.go.move}`, hit = (x) => x === id || x.startsWith(`${id}:`); // 疾行的 id 後面多接走法
    if (!S.main.options.some((o) => hit(o.id))) { mapGoto(r.go.move); goTab("map"); return; }
    S.wheelSel = "move";
    S.glowRoute = id; // 往那一處的那一條發光：記在狀態裡，重畫、摺疊 toggle 都保得住（FB-9001）
    renderPage();
    revealMoveCard();
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
  const CK_PICK_TITLE = "簽到第 {day} 天";
  const CK_PICK_NOTE = "今天的份要挑一樣";
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
  function wkStepOf(w) {
    if (!w.steps.length) return null;
    if (!S.wkStep || S.wkStep.key !== wkKey(w)) S.wkStep = { key: wkKey(w), i: 0 };
    return w.steps[S.wkStep.i % w.steps.length];
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
    // 灰線（第 N 週、主題、兩軍態勢）整條是一顆鈕、點了攤開「為什麼」；右邊一顆 × 收到明天。灰線底下那一行小字跟著它收
    const hideStrip = wkHidden(m, "strip");
    const strip = hideStrip ? "" : `<div class="wk-stripbar"><button id="week" class="wk-strip${open === "why" ? " on" : ""}" data-act="wk" data-id="why" aria-expanded="${open === "why"}" aria-label="${esc(w.label)}${esc(w.when)}，點了看為什麼">`
      + `<b class="wk-seg">${esc(w.when)}</b>${w.theme ? `<span class="wk-th">${esc(w.theme)}</span>` : '<span class="wk-th"></span>'}${w.sides ? wkSidesHtml(w.sides) : ""}<i class="wk-chev" aria-hidden="true"></i></button>${x("strip")}</div>`;
    const panel = !hideStrip && open === "why" ? `<div class="card wk-panel why">${whyHtml(m)}</div>` : "";
    // 灰線底下一行小字（批 5，整合設計 6.8）：第 3 週「離贏還差多少」、第 2 週的功能剛開了那一句、45 級之後那一句；都沒有不畫
    const notes = [w.gap, w.unlock, w.cap].filter(Boolean);
    const note = !hideStrip && notes.length ? `<p class="wk-note">${notes.map(esc).join(" ")}</p>` : "";
    // 「眼下要事」（Joy 2026-10-26：以前叫「你這一步」）排在行動列底下，平常收成兩行：標題、做完拿什麼與去做；點標題才攤說明與「換一件」。
    // 沒有要做的事不畫；× 收到明天。做完的那一件伺服器下一次就不給了，這裡自然換到下一件
    const more = open === "step";
    const card = !step || wkHidden(m, "card") ? "" : `<section class="card wk-card${more ? " on" : ""}" aria-label="${WK_STEP}">
      <div class="wk-head"><button class="wk-tap" data-act="wk" data-id="step" aria-expanded="${more}"><span class="wk-lab">${WK_STEP}</span><b class="wk-title">${esc(title)}</b></button>${x("card")}</div>
      ${more && detail ? `<p class="wk-detail">${esc(detail)}</p>` : ""}
      <div class="wk-foot">${step.reward ? `<span class="wk-gain">${esc(step.reward)}</span>` : '<span class="wk-gain"></span>'}${more && w.steps.length > 1 ? `<button class="linkish wk-next" data-act="wk-next">↻ ${WK_NEXT}</button>` : ""}${go}</div></section>`;
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
  function chapterCardHtml(m) {
    const c = m.week_card && m.week_card.chapter;
    if (!c || !shown("quest")) return "";
    const t = c.target;
    // 說明裡已經寫了地名的（「出城看風（潁川郊野的草澤）」）不再補一次；回目就是那一件大事的（官軍第二回「長社火攻」）只寫時刻
    const far = !c.waiting && t && !c.here && !String(c.hint).includes(t.name) ? `（${esc(t.name)}${t.minutes ? `・${t.minutes | 0} 分` : ""}）` : "";
    const when = CH_LIVE[c.live] || c.at;
    const at = c.beat && c.beat !== c.title ? `${esc(c.beat)}・${esc(when)}` : esc(when);
    const go = c.waiting || c.scene ? "" : c.here ? `<button class="btn primary ch-go" data-act="choose" data-id="story:${esc(c.line)}">${CH_DO} ›</button>`
      : t && shown("tab:map") ? `<button class="btn primary ch-go" data-act="tab" data-tab="map"${gotoAttrs(t.location)}>${WK_MAP} ›</button>` : "";
    return `<section class="card ch-card side-${esc(c.side)}" aria-label="${esc(CH_NO.replace("{no}", c.no))}${esc(c.title)}">
      <div class="ch-head"><span class="ch-no">${esc(CH_NO.replace("{no}", c.no))}</span><b class="ch-title">${esc(c.title)}</b>${at ? `<span class="ch-at">${at}</span>` : ""}</div>
      <p class="ch-next">${c.waiting || c.scene ? "" : CH_NEXT}${esc(c.hint)}${far}</p>
      <div class="ch-foot"><span class="ch-sway">${esc(c.sway)}</span>${go}</div></section>`;
  }
  // 簽到要挑四階的日子（還沒挑）：本週卡底下一張小卡，四顆挑屬性的鈕（點一種就領，同以前簽到格裡的那四顆）
  function checkinPickHtml(m) {
    const k = m.status && m.status.checkin;
    if (!k || k.done || !k.pick) return "";
    return `<section class="card ck-card" aria-label="簽到"><h3>${CK_PICK_TITLE.replace("{day}", k.day)}<small>${CK_PICK_NOTE}</small></h3>
      <div class="ck-pick">${k.pick.map((x) => `<button class="ck-p4 ${CK_ATTR[x.attribute] || ""}" data-act="checkin" data-attr="${esc(x.attribute)}"><b>${esc(x.attribute)}</b>${esc(x.name)}<small>有 ${x.held}</small></button>`).join("")}</div></section>`;
  }
  const WK_HOWTO = '<p class="wk-howto"><button class="linkish" data-act="howto-open" aria-haspopup="dialog">玩法說明 ›</button>這一季在打什麼、名望怎麼來、投靠與軍令</p>';
  // 「為什麼」攤開的那一塊：三方卡、收季規則、下一件、主線（以前主線小標的內容）、新手目標（以前新手小標的內容）、簽到這一週七格（每天給什麼）
  function whyHtml(m) {
    const s = m.status || {};
    const nb = newbiePeek(m), ck = checkinPeek(m);
    const next = m.week_card && m.week_card.next ? `<p class="wk-nextev"><b>下一件</b>${esc(m.week_card.next)}</p>` : "";
    const locked = m.week_card && m.week_card.locked ? `<p class="wk-locked">${esc(m.week_card.locked)}</p>` : ""; // 第 2 週才開的功能（6.6，批 5）
    return `${m.sides_card ? sidesTableHtml(m.sides_card) : ""}${s.stance_rule ? `<p class="stance-rule">${esc(s.stance_rule)}</p>` : ""}${locked}${next}${warHelp(m, "stance")}`
      + `${nb ? `<h4 class="wk-sub">${esc(s.newbie.title)}</h4>${nb.panel}` : ""}${m.quest && m.quest.trim() && shown("quest") ? `<div class="wk-quest">${m.quest}${warHelp(m, "quest")}</div>` : ""}`
      + `${ck ? `<h4 class="wk-sub">簽到</h4>${ck.panel}` : ""}`
      + (s.renown ? WK_HOWTO.replace("名望怎麼來", "名聲怎麼來") : WK_HOWTO); // 以前在行動列底下（explain-2）；名聲開著時那一節叫「名聲」
  }
  // 三方卡（整合設計 3.4）：每一方一欄（手機上一欄一塊、上下排），要做到／現在／贏了給／投靠在哪。自己那一方框起來
  const SIDES_ROWS = [["goal", "要做到"], ["now", "現在"], ["gives", "贏了給"], ["where", "投靠在哪"]];
  function sidesTableHtml(sc) {
    return `<div class="sides">${sc.cols.map((c) => `<div class="side side-${esc(c.id)}${c.mine ? " mine" : ""}"><h4>${esc(c.name)}${c.mine ? "<small>你在這一方</small>" : ""}</h4>`
      + `<dl>${SIDES_ROWS.filter(([k]) => c[k] && c[k].length).map(([k, name]) => `<dt>${name}</dt><dd>${esc(Array.isArray(c[k]) ? c[k].join("、") : c[k])}</dd>`).join("")}</dl></div>`).join("")}</div>`;
  }
  // 還沒投靠的人：江湖頁最上面就是三方卡，加一句「先投一方」（整合設計 3.4）。平常收成一行（兩方投靠在哪），點了攤開三欄；
  // 攤開整張會把行動列推出第一屏，所以預設收著。攤開記在 S.sidesOpen（輪詢重畫照它畫）
  const SIDES_FIRST = "先投一方", SIDES_FIRST_NOTE = "到那一方的地點按「投靠」。誰都不投也行，當個散人，接懸賞一樣闖得出名號。"; // 待 joy 潤
  function sidesFirstHtml(m) {
    const sc = m.sides_card;
    if (!sc || sc.joined || !shown("quest")) return "";
    const where = sc.cols.filter((c) => c.where.length).map((c) => `${esc(c.name)}在${esc(c.where[0])}`).join("、");
    return `<details class="card sides-first"${S.sidesOpen ? " open" : ""}><summary data-act="sides-first">${SIDES_FIRST}<small>${where}</small></summary>`
      + `<p class="sides-note">${SIDES_FIRST_NOTE}</p>${sidesTableHtml(sc)}</details>`;
  }
  // 點「為什麼」「今日簽到」：原地換掉本週卡（不重畫整頁，「剛剛」不重播），焦點還給同一顆
  function wkTap(id) {
    const w = S.main.week_card;
    if (!w) return;
    S.wkOpen = S.wkOpen && S.wkOpen.key === wkKey(w) && S.wkOpen.id === id ? null : { key: wkKey(w), id };
    wkRepaint(`[data-act="wk"][data-id="${id}"]`);
  }
  function wkNext() {
    const w = S.main.week_card;
    if (!w || !w.steps.length) return;
    wkStepOf(w);
    S.wkStep.i = (S.wkStep.i + 1) % w.steps.length;
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

  // 態勢那一行（FB-065）：官軍、黃巾是幾條戰況合起來的，豪強是割據（有戰線在亂局就漸長）。說明由伺服器給（status.stance_notes），
  // 跟見聞→大勢的割據說明同一句，前端不自己數條數。狀態列展開時用它（江湖頁的三條在最上面那一排小標的態勢面板裡，正式版辛）
  function stancesHtml(stances, notes) {
    const n = notes || {};
    const side = (id) => `${STANCE_NAMES.find(([key]) => key === id)[1]} ${stances[id]}`;
    const note = (text) => (text ? `（${esc(text)}）` : "");
    const gentry = "haoqiang" in stances ? `<br>${side("haoqiang")}${note(n.haoqiang)}` : ""; // 豪強分屬兩軍的季沒有豪強那一行
    return `<div class="stances-line"><span>態勢</span><span>${side("guan")}・${side("huang")}${note(n.sum)}${gentry}</span></div>`;
  }

  // 第一季濃縮版的三條戰況（伺服器有送 fronts 才畫）：0 是官軍穩控、100 是黃巾控制，條上黃的那一截是黃巾佔的。
  // 條上淺色的一段是亂局帶（band＝status.chaos_band，兩端含在內；豪強趁亂割據的戰況區間），戰況落在裡面的圖卡標「亂局」（f.chaos）。
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

  // 說書人的對話框（引導重做設計 8.1、6.2）：行動列（或事件的選項）上方，框上寫說話的人（之後換成師父、引薦人）。
  // 做完一步先列「✔ 完成」與獎勵，再接下一步的話。可以收起成一行；記的是收起的那一句，換了下一句就自己展開。
  // 結語有「知道了」，按了就不再出現。在路上預設收成一行（FB-055）：框、走法與路上的五個選項擠不進第一屏，折返被分頁列蓋住；
  // 路上展開的記在 S.guideRoad（記的是那一句，下了路就清掉），輪詢重畫不會把它收回去（事件待處理的那一句也一樣，見 openGuide）
  const GUIDE_KEY = "tx-guide-shut";
  function guideShut() { try { return localStorage.getItem(GUIDE_KEY); } catch (e) { return null; } }
  function setGuideShut(text) { try { if (text) localStorage.setItem(GUIDE_KEY, text); else localStorage.removeItem(GUIDE_KEY); } catch (e) { /* 存不了就只在這一頁有效 */ } }
  // 收起記的是「哪一步」（伺服器給的 key：步驟的 id），不是那一句話（FB-076）：眼前有事件時框上的話換成「先把眼前的「…」了結」，
  // 每遇到新事件就換一句；記句子的話，收起的框每個新事件都會自己又展開，事件的最後一個選項就被擠出第一屏。
  // 換到下一步（新的 key）才照舊展開。舊版伺服器沒有 key 時退回認句子
  function guideKey(g) { return g && (g.key || g.text); }
  // 「先把眼前的「…」了結」那一句（伺服器標 pending）預設收成一行，玩家沒按過「收起」也一樣（FB-076，控制者裁示）：它只是重複底下
  // 事件卡片已經寫的話，展開時事件的最後一個選項被擠到分頁列底下。跟在路上一樣，點開的記在 S.guideRoad（記的是那一句，
  // 換成下一個事件的句子就又收著，了結之後清掉）；只有這一句，新的一步照舊展開
  function shutGuide(g) { setGuideShut(guideKey(g)); S.guideRoad = null; }
  function openGuide(g) { setGuideShut(null); S.guideRoad = g && g.text; }
  // 分頁的步驟（伺服器標 paged，T7 審查 I1）：師父的話照 \n\n 切成幾頁，一次一頁、按「下一段 ▸」往下，最後一頁帶著要做的事；
  // 每一頁都是整段，不切。記的是（哪一步, 第幾頁），換到下一步自己回到第一頁
  const guidePages = (g) => (g.paged ? g.text.split(/\n{2,}/) : [g.text]);
  const guidePage = (g) => (S.guidePage && S.guidePage.key === guideKey(g) ? Math.min(S.guidePage.n, guidePages(g).length - 1) : 0);
  function nextGuidePage(g) { S.guidePage = { key: guideKey(g), n: Math.min(guidePage(g) + 1, guidePages(g).length - 1) }; }
  // 但框上還有「✔ 引導完成」與獎勵（done）要讓玩家看到時不收：「剛剛」卡片依設計不放引導，收成一行那一列就沒地方看了
  // （新角色的第一次探索常常做完第一步又留下事件）；那時照舊展開。FB-076 量的那一場（遊歷打完接事件）done 是空的
  // 決戰集結的時候（場景裡有集結的倒數）入伍、步驟的框也預設收成一行（企劃者 2026-10-08，FB-107 修正輪）：場景多了戰場那一段、
  // 加入的鈕、此地還有，入伍段分頁攤開的框把行動列擠到分頁列底下（長社官軍量到 796）。點開的照在路上記在 S.guideRoad（那一句本身），
  // 輪詢時倒數在變也不收回去；自己按「收起」或集結結束才不算。序章裡師父的框不收（設計 6.2）。
  // 「知道了」的框（碰到才說、結語）集結時也收成一行，點開才有「知道了」：潁水河畔打完一場＋內傷框、別的大區在集結，控制者量到
  // 762～784，收了集結那一句還是放不下（裁示見交接報告）。在路上的「知道了」框照舊攤開（路上另有排法）
  const MUSTER_SCENE = /集結(中，)?還剩現實/; // engine._battle_scene_text 集結那一段的寫法（還沒加入、加入了、觀戰都有）
  const guideMuster = () => !!(S.main && MUSTER_SCENE.test(S.main.scene || "")) && !pro();
  function guideHtml(g, onRoad) {
    // 分頁記的是（哪一步, 第幾頁）：框換成別一步、或整個框不在了，就清掉。不然換季回草廬重走一遍，走到那一步又直接開在舊的那一頁（T7 審查 N3）
    if (S.guidePage && (!g || S.guidePage.key !== guideKey(g))) S.guidePage = null;
    const quiet = !!(g && g.pending && !g.done.length); // 事件待處理的那一句、而且沒有要看的完成列：預設收成一行
    const muster = !onRoad && guideMuster(); // 決戰集結中：框預設收成一行（「知道了」的框也是）
    if (!onRoad && !quiet && !muster) S.guideRoad = null; // 沒有框、也不是這三種預設收著的時候要清（FB-055）
    if (!g) return "";
    const folded = muster || ((onRoad || quiet) && !g.end); // 預設收著（點開的記在 S.guideRoad）
    if ((!g.end && guideShut() === guideKey(g)) || (folded && S.guideRoad !== g.text)) {
      // 收起來那一行：序章的步驟自己寫了短的一行（g.line，例：「回『江湖』按『探索』」，說話的人由這裡寫在前面、line 不重複）就用它，
      // 不然是這一句話；
      // 記著收起的是步驟的 key（guideKey，FB-076），換到下一步自己展開
      return `<button class="guide-line" data-act="guide-open" aria-label="展開${esc(g.speaker)}的話"><b>${esc(g.speaker)}</b>：${esc(g.line || g.text)}</button>`;
    }
    const done = g.done.length ? `<div class="guide-done">${g.done.map((d) => d.startsWith("✔")
      ? '<span class="ok">✔ 完成</span>' : `<span class="reward">${esc(d)}</span>`).join("")}</div>` : "";
    // 序章以外（Joy 2026-10-26：師父的話排在行動列底下）右上角一顆 ×：做的事同「知道了」（g.end）／「收起」
    const btn = !pro() ? `<button class="wk-x guide-x" data-act="${g.end ? "guide-ack" : "guide-shut"}" aria-label="${g.end ? "知道了" : "收起"}" title="${g.end ? "知道了" : "收起"}">×</button>`
      : g.end ? '<button class="btn small" data-act="guide-ack">知道了</button>'
      : '<button class="linkish" data-act="guide-shut">收起</button>';
    // 長的那幾步（軍令兩步一百多字）先露三行、點了看全文，不把行動與選項擠出第一屏（畫面批次審查 I3）
    // 序章裡師父的話不切（設計 6.2「話不會被切掉」，T7 審查 I1）：不收成三行；段落照 \n\n 排（樣式表 pre-line）。
    // 入伍段引薦人的話也一樣（設計 6.2 寫的就是「序章與入伍段」）：伺服器給 full，不收；兩段以上的那一步另外給 paged（照上面的分頁）
    const full = !!pro() || !!g.full || S.guideFull === g.text;
    const pages = guidePages(g), page = guidePage(g);
    const scene = g.scene && page === 0 ? `<p class="guide-scene">${esc(g.scene)}</p>` : ""; // 序章的旁白（「斷眉來了……」）排在話的前面（分頁的步驟只在第一頁）
    const next = page < pages.length - 1 ? '<button class="linkish guide-next" data-act="guide-next">下一段 ▸</button>' : "";
    return `<section class="card guide" aria-label="${esc(g.speaker)}的話"><div class="guide-head"><b>${esc(g.speaker)}</b>${btn}</div>${done}${scene}<p class="guide-text${full ? "" : " clamp"}" data-act="guide-more" role="button" tabindex="0" aria-expanded="${full}">${esc(pages[page])}</p>${next}</section>`;
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
    return `<figure class="scene-art ${esc(a.kind)}"><img src="${esc(a.src)}" alt="" decoding="async"><figcaption><b>${esc(a.title)}</b>${sub}${time}</figcaption></figure>`;
  }
  function sceneUnderArt(m) {
    if (!m.art || !m.art.head || !(m.scene || "").startsWith(m.art.head)) return m;
    return { ...m, scene: m.scene.slice(m.art.head.length).replace(/^\n/, "") };
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
        : `<section class="card scene${m.art ? " has-art" : ""}${tierClass(m)}">${m.art ? sceneArtHtml(m.art) : ""}${tierTag(m)}${siegeStrip(withGauge(musterScene(m, roundBlocks(battleScene(sceneUnderArt(m)), m.battle_gauge)), m.battle_gauge), m.siege)}${myTurn ? "" : people}</section>`;
    const peopleAfter = myTurn && people && !masterTalks && !m.on_road ? `<section class="card people-after">${people}</section>` : "";
    const week = peekWeek(m);
    // 本週卡（減法季批 1，整合設計 6.1）排在最上面、「剛剛」之前（在路上排到選項底下，FB-055）：吃掉以前那一排小標。來信到了換成來信（回了信或收起來才換回本週卡）；
    // 還沒投靠的人最上面先是三方卡（sidesFirstHtml）。戰況圖卡、軍備與小地圖從江湖頁拿掉（6.3），戰況與軍備在見聞・大事
    const letterCard = letterHtml(m.letter);
    const pushAsk = letterCard && typeof pushAskHtml === "function" ? pushAskHtml(m) : ""; // 第一次來信時信的小卡底下問一次手機通知（批 9；pushAskHtml 在 app.js，只切 main.js 的網頁測試沒有它）
    // 開局頭一刻（整合設計 6.7，批 7）：人物開口的那一封（letter.open）排在三方卡前面——先聽人說話，再看三方；其餘時候三方卡照舊在最上面
    // 本週卡：灰線（一行）照舊在最上面，「眼下要事」排在行動列底下（Joy 2026-10-26：四顆行動鈕一定在第一屏）；來信到了照舊換成來信
    const peek = letterCard && m.letter.open ? letterCard + pushAsk + sidesFirstHtml(m) : sidesFirstHtml(m) + (letterCard ? letterCard + pushAsk : weekCardHtml(m, "top") + chapterCardHtml(m));
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
    if (m.on_road) return `${resultCard}${letter}${letterCard}${pushAsk}${now}${scene}${links}${free}${menu}${guide}${sidesFirstHtml(m)}${weekCardHtml(m)}${orderCard}${bountyCard}${sealMine}${sealCard}`;
    // 決戰輪到你出招的回合（FB-136）：三招緊接在場景底下，放手一搏的輸入框與說書人的框排在三招後面（同在路上，這一刻要按的排前面）。
    // 開打那一刻場景多了戰局條、這一幕的開場、騎兵那一句，框與輸入框再排在上面的話三招整排落到分頁列底下（14 天、騎著馬、框還在：855～999）
    if (myTurn) {
      return `${resultCard}${peek}${letter}${now}${scene}${links}${menu}${peopleAfter}${free}${guide}${senseNotes}${weekCard}${skip}${orderCard}${bountyCard}${sealMine}${sealCard}`;
    }
    const planCard = planHtml(m.plan) + placeDeedsHtml(m.place_deeds); // 世界活起來：行動列與眼下要事底下（四顆行動鈕一定在第一屏）
    return `${resultCard}${peek}${letter}${now}${scene}${links}${guideUp}${free}${menu}${senseNotes}${weekCard}${planCard}${guideDown}${skip}${orderCard}${bountyCard}${sealMine}${sealCard}`;
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
      : `<div class="peer-head">${c.mingtie ? `<button class="peer-mt" data-act="mt-zoom-peer" aria-label="看${esc(c.name)}的名帖">${mtCardHtml(c.mingtie, c.name, "thumb")}</button>` : ""}<h3>${esc(c.name)}</h3><div class="peer-title">${[...c.affiliation.split("・"), `第${c.level}級`].map((t) => `<span class="peer-seg">${esc(t)}</span>`).join("・")}</div>${peerRenownHtml(c, P)}${c.record ? `<p class="peer-record">${esc(c.record)}</p>` : ""}${c.yuedan ? `<p class="peer-record peer-yuedan">${esc(c.yuedan)}</p>` : ""}</div>
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

  // 序章裡師父的話也放在修練頁、煉製頁最上面（序章的第 4～6、9、10 步在這兩頁做，不用切回江湖頁看要做什麼）；序章外不畫。
  // 碰到才說的提示（伺服器標 hint）也畫在這兩頁最上面：修練失敗、改練、合成、熔煉都是在這兩頁做的，提示在做完的那一下上框、記進紀錄，
  // 不畫的話玩家要切回江湖頁才看得到（新手引導計畫三，T1 審查 I-1）。同一個框、同一顆「知道了」；說書人的步驟、結語、入伍段的框仍只在江湖頁
  const proGuide = () => (pro() || (S.main.guide && S.main.guide.hint) ? guideHtml(S.main.guide, false) : "");

  // 武學屬性有什麼用（W2、FB-089：標題冠上「武學」，跟升級配點的「屬性」分開）：修練、煉製兩頁各摺一行，收著只多一行小字。說明的字是伺服器照程式的規則寫的（skillview.attribute_line），
  // 這裡只放進去；標題那四個字待 joy 潤。伺服器沒給（舊版）就不畫。
  const attrNoteHtml = (x) => (x.attribute_note ? `<details class="attr-note"><summary>武學屬性有什麼用</summary><p>${esc(x.attribute_note)}</p></details>` : "");

  // 熔煉的問句（W9、FB-081）：整句由伺服器寫好、放在按鈕的 data-confirm（library.melt_confirm：有心得就寫退回多少，沒有就直說
  // 只空出一格；基礎武學再接一句去哪裡重學，只說一次）。伺服器沒給（舊版）才用這句老問題
  // 批量熔煉（修練頁功法庫）：勾、勾選篩出來的全部（meltPickShown）、確認之後一次送出
  function meltToggle(key, id) {
    if (!S.meltSel || !id) return;
    const list = S.meltSel[key];
    S.meltSel = { ...S.meltSel, [key]: list.includes(id) ? list.filter((v) => v !== id) : [...list, id] };
    renderPage();
  }
  function askMeltMany(el) {
    const sel = S.meltSel;
    if (!sel || !(sel.arts.length + sel.ins.length)) return;
    const parts = [sel.arts.length ? `${sel.arts.length} 門武學` : "", sel.ins.length ? `${sel.ins.length} 個意境` : ""].filter(Boolean).join("、");
    const v = el.dataset.v | 0;
    const warn = sel.ins.length ? "靠這些意境修練的武學，熔了就不能再修練。" : "";
    ask(`把勾的 ${parts}一起熔掉？${v > 0 ? `心得 +${v}。` : ""}熔掉就沒了。${warn}`, "熔掉", async () => {
      const body = { arts: sel.arts, insights: sel.ins };
      S.meltSel = null;
      await mx("melt_many", body);
    });
  }
  const meltAskText = (el) => el.dataset.confirm || `把【${el.dataset.name}】熔成心得？熔掉就沒了。`;

  // 熔煉與意境化成心得都先問一次，用頁面自己的確認層（ask，管理者工具用的那一個；FB-085）：以前是瀏覽器內建的確認框，
  // 跟其他按鈕不一樣、手機上還會被擋掉。按「熔掉」才送，取消或點旁邊暗處什麼都不送
  function askMelt(el) {
    ask(meltAskText(el), "熔掉", () => mx("melt", { art: el.dataset.id }));
  }
  function askMeltInsight(el) {
    ask(`把「${el.dataset.name}」化成心得？靠它的武學從此不能修練。`, "化成心得", () => mx("melt_insight", { insight: el.dataset.id }));
  }

  // 功法清單的篩選（FB-085）：煉製頁一排四顆（全部／內功／武學／意境）；修練頁用卷軸卡自己的庫篩選（libFilter，也記在 localStorage）。
  // 選擇記在這個瀏覽器的 localStorage（存不了就只在這一頁有效，讀不到就當沒選過）。
  // 排序是伺服器排好的（skillview.art_rows：身上的先，再品質、成、名字），兩頁畫的是同一份，這裡只決定哪些要畫
  const ART_FILTERS = ["全部", "內功", "武學", "意境"];
  const filterKey = (page) => `tx-arts-filter-${page}`;
  function artFilter(page) {
    // 序章的煉製頁（第 4 步要放進爐子的基礎拳腳與剛悟到的意境）一律全列：瀏覽器記著的是上一個角色的篩選，不能把師父點名的藏起來
    if (page === "craft" && pro()) return "全部";
    S.artFilter = S.artFilter || {};
    if (!(page in S.artFilter)) {
      let saved = null;
      try { saved = localStorage.getItem(filterKey(page)); } catch (e) { /* 讀不到就當沒選過 */ }
      S.artFilter[page] = ART_FILTERS.includes(saved) ? saved : "全部";
    }
    return S.artFilter[page];
  }
  function setArtFilter(page, value) {
    if (!ART_FILTERS.includes(value)) return;
    S.artFilter = S.artFilter || {};
    S.artFilter[page] = value;
    try { localStorage.setItem(filterKey(page), value); } catch (e) { /* 存不了就只在這一頁有效 */ }
  }
  // 這一頁現在的篩選下，這一門武學要不要畫（選「意境」時武學一門都不畫）。煉製頁的意境一律畫：它是拿一門武學配一個意境的地方，
  // 「內功」「武學」篩選不把意境整排藏起來（沒有提示會讓人以為意境不見了）；修練頁的庫另有卷軸卡的篩選（libFilter）
  function showArts(page, art) {
    const f = artFilter(page);
    return f === "全部" || f === art.kind;
  }
  // 四顆小鈕排一行，併在煉製頁「功法」那一行標籤裡（第一屏不多一行）
  function filterChips(page) {
    if (page === "craft" && pro()) return ""; // 序章裡沒有篩選可選（artFilter 一律全列），不畫鈕
    const now = artFilter(page);
    return `<span class="fchips" role="group" aria-label="篩選">${ART_FILTERS.map((f) => `<button type="button" class="fchip${f === now ? " on" : ""}" data-act="art-filter" data-page="${page}" data-filter="${f}" aria-pressed="${f === now}">${f}</button>`).join("")}</span>`;
  }

