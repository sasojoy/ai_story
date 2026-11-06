/* 天下大勢的網頁前端：第一屏放不下時一步一步收（全部拆包第 66 批從 app.js 切出來）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。殼的檔，/ 的 script 標籤由伺服器照 WEB_ORDER 生成。
 */
"use strict";

  // ── 第一屏放不下時一步一步收（FB-107）──
  // 企劃者：375×812 上「剛剛」、場景與整排行動都在第一屏（按完不用捲就看得到結果）。打完一場又跳出師父「碰到才說」的框、💡 兩行、
  // 決戰集結（場景多一段戰場、「此地還有」、結伴那幾行）時，行動列會掉到分頁列底下。框照企劃者 10/5 的決定留在行動列上面、話不切；
  // 這裡畫好之後量一次：行動列（事件、有所感這種一組選項時是最後一顆）的下緣離分頁列不到 FIT_MARGIN，就照 FIT_STEPS 的順序一步一步收，
  // 收到放得下就停——放得下的畫面一點都不動。先收不少任何字的（間距、框的行高），再收 💡 與看一眼就夠的（對手的描述、第一回合、
  // 剛剛的後半、決戰時所在地的描述、集結那一句的後半），每一樣都點得開、看得到全文；得失與結果那幾行（數字）、框裡的話都不收。
  // 一組選項時鈕收緊了還放不下，最後一步（choices，企劃者 2026-10-16 選 (c)）收態勢那一排、「剛剛」的敘事、灰掉的鈕底下那一行原因。
  // 在路上（另有自己的排法，FB-055）、序章裡不收。收到最後還放不下（集結又有框的時候：場景裡「此地還有」、結伴那一行不歸這裡收；
  // 別人遞來的邀請歸 6b 收，FB-117）就是放不下，不再藏別的
  // 量的是畫面本身（字體、寬度、狀態列幾行都算進去），所以手機高一點、字少一點就少收或不收。重畫、轉向、拉視窗之後重量（先全部還原）
  const FIT_MARGIN = 16;
  const fitPage = () => document.getElementById("page");
  // 要放進第一屏的那一塊：平常閒著是行動列；事件、有所感、對話、決戰這種一組選項時是選單最後一顆。
  // 約戰卡緊接在行動列底下、第一張是應得了或同去得了的（FB-9006，企劃者 2026-10-28「要露出來」；sxRank 把可按的排在最前面）時，要擠進第一屏的
  // 是那一行（連右邊的鈕）：它在行動列底下，量它就連整排行動列一起照顧到了，只是多縮場景的畫（收法 5a）；約戰卡本身的版面不動、也不搬到行動列上面。
  // 沒有可按的約戰（只有自己貼的、結算完的、別區的、約戰關著），或行動列與約戰卡之間展開了移動、探索、出陣前那張卡（玩家自己攤開的），
  // 量的還是行動列，第一屏一個像素都不變。量的是約戰那一行、前面的步驟都收完還放不下時，再多收一步 desc（6c，企劃者 2026-10-28「擠完再上」）：
  // 閒著的場景卡把所在地的描述每段收成一行；目標是行動列、一組選項時那一步不做
  const FIT_DUEL_BTN = '#page > .act-bar + #sortie-duels > .sx-drow:first-of-type > [data-act="sortie-answer"], '
    + '#page > .act-bar + #sortie-duels > .sx-drow:first-of-type > [data-act="sortie-join"]';
  function fitDuelRow() {
    const btn = document.querySelector(FIT_DUEL_BTN);
    return btn ? btn.parentElement : null;
  }
  const fitTarget = () => fitDuelRow() || document.querySelector("#page > .act-bar") || document.querySelector("#page > .options > :last-child");
  function fitOver() {
    const target = fitTarget(), tabs = document.querySelector(".tabs");
    if (!target || !tabs) return 0;
    return target.getBoundingClientRect().bottom + (window.scrollY || 0) - (fitTabsTop(tabs) - FIT_MARGIN);
  }
  // 分頁列頂的基準（FB-123）：分頁列固定在畫面底下，手機捲動時網址列收起、跑出來，它跟著上下移幾十 px。集結時倒數每一輪都整頁重畫、
  // 重量，拿當下的位置量的話，網址列每換一次狀態就多收或少收一步、畫面跟著跳。同一個寬度記住量到過最小的那個（網址列跑出來的時候：
  // 一開頁面、捲回頂端都是），寬度變了（轉向、拉視窗）重記。輸入框有焦點時不記：舊的 Android 開鍵盤會把視窗縮小，記下來的話
  // 收起鍵盤之後整頁還收到底
  function fitTabsTop(tabs) {
    const top = tabs.getBoundingClientRect().top, width = window.innerWidth;
    const typing = /^(INPUT|TEXTAREA)$/.test((document.activeElement && document.activeElement.tagName) || "");
    if (!S.fitBase || S.fitBase.width !== width) {
      if (typing) return top;
      S.fitBase = { width, top };
    } else if (!typing) {
      S.fitBase.top = Math.min(S.fitBase.top, top);
    }
    return S.fitBase.top;
  }
  const FIT_STEPS = [
    // 1. 間距：卡與卡之間、卡的內距收緊一點（style.css 的 .page.fit-space），一個字都不少
    { key: "space", run: () => {
      fitPage().classList.add("fit-space");
      const card = document.querySelector("#page > .battle-card");
      if (card) card.classList.add("fit-space"); // 戰鬥卡片的內距寫在 .battle-card 底下（style.css 的 .battle-card.fit-space）
      return true;
    } },
    // 1a. 開局一到就攤開的那封信（letter.open：託付的信，FB-9110）把約戰那一行擠出第一屏：量的是約戰那一行（fitDuelRow）時，信收成標題一行
    //     （誰來信，同玩家按標題收攏的樣子），緊接在底下問手機通知的那一張也先不畫（信攤開時照舊問）。點標題照樣攤開（letter-open 記 S.letterOpen，
    //     重畫時不再收）。玩家自己攤開的不收；目標是行動列、一組選項時一個像素都不動
    { key: "letter", run: () => {
      if (!fitDuelRow()) return false;
      const card = document.querySelector("#page > .card.letter.open:not(.fit-letter)");
      if (!card || S.letterOpen === Number(card.dataset.letter)) return false;
      card.classList.add("fit-letter");
      const head = card.querySelector(":scope > .letter-head"), arrow = card.querySelector(".letter-arrow");
      if (head) head.setAttribute("aria-expanded", "false"); // 點標題走 letter-open 的「沒攤開 → 攤開」
      if (arrow) arrow.textContent = "›";
      return true;
    } },
    // 2. 師父的框收緊：「知道了」不再撐高標題那一行、話的行高小一點；框裡的話一個字都不切（設計 6.2）
    { key: "box", run: () => {
      const box = document.querySelector("#page > .card.guide");
      if (box) box.classList.add("fit-box");
      return !!box;
    } },
    // 3b. 名聲（1B）：名號底下那一行稱號不畫，善惡稱號接在頭銜後面（whoNameHtml；記在 S.renownTight，輪詢重畫狀態列時照它畫）
    { key: "renown", run: () => {
      if (S.renownTight || !document.querySelector("#top .who-renown-line")) return false;
      S.renownTight = true;
      renderTop();
      return true;
    } },
    // 4. 戰鬥卡片底下的補充（對手的描述「（偷網賊：……）」這種）每一行收成一行、放不下加「…」，點了看全文（同伴聽來的那一句的做法，FB-074）。
    //    點開記在 S.linesOpen（這一場的卡片），跟聽來的那一句（S.hearOpen）各記各的（審查 M5）；數字收不進一行的那一行不收
    { key: "lines", run: () => {
      if (S.linesOpen != null && S.linesOpen === S.main.card_id) return false; // 玩家點開過：不收回去
      let any = false;
      document.querySelectorAll(".battle-card .tx-extra .tx-line:not(.tx-hearsay)").forEach((el) => {
        el.classList.add("tx-tight");
        if (!fitDigitsShown(el)) { el.classList.remove("tx-tight"); return; }
        el.setAttribute("data-act", "line-more");
        el.setAttribute("role", "button");
        el.setAttribute("tabindex", "0");
        el.setAttribute("aria-expanded", "false");
        any = true;
      });
      return any;
    } },
    // 5. 戰鬥卡片的第一回合也收進「展開過程」（那一行與按鈕照舊在；得失照舊在）
    { key: "rounds", run: () => {
      const list = document.querySelector(".battle-card ul.rounds:not(.open), .battle-card p.rounds-tale:not(.open)");
      if (list) list.classList.add("fit-fold");
      return !!list;
    } },
    // 5a. 場景的畫（減法季批 8）縮成一條橫幅（地名、時刻照舊壓在上面）：畫在行動列上面最佔高度（375×812 約 270px），
    //     「剛剛」的戰鬥卡長一點就把整排行動推出第一屏（2026-10-27 回報：以前沒有畫，行動鈕一直在第一屏）
    { key: "art", run: () => {
      const art = document.querySelector("#page > .card.scene > .scene-art:not(.fit-art)");
      if (art) art.classList.add("fit-art");
      return !!art;
    } },
    // 5c. 戰鬥卡片底下的補充（得了什麼、地盤多撿一份、鑄譜的那一句……）只留第一行，其餘收起來；點那一塊整塊攤開（S.extraOpen 記這一場）。
    //     得失那一段（數字）照舊在卡片上
    { key: "extra", run: () => {
      if (S.extraOpen != null && S.extraOpen === S.main.card_id) return false; // 玩家點開過：不收回去
      const box = document.querySelector("#page .battle-card .tx-extra:not(.fit-extra)");
      if (!box || box.querySelectorAll(":scope > .tx-line").length < 2) return false;
      box.classList.add("fit-extra");
      box.setAttribute("data-act", "extra-more");
      box.setAttribute("role", "button");
      box.setAttribute("tabindex", "0");
      box.setAttribute("aria-expanded", "false");
      return true;
    } },
    // 5b. 決戰的本場戰功（名聲 4B）：名字底下那一行稱號收掉（名字照舊；三招不能被擠出第一屏）
    { key: "merit", run: () => {
      const rows = document.querySelectorAll(".g-merit .rn-two small:not(.fit-hide)");
      rows.forEach((el) => el.classList.add("fit-hide"));
      return rows.length > 0;
    } },
    // 6. 「剛剛」（不是戰鬥卡片的那種）收著時只露三行（同在路上，FB-060），「展開全文」照舊
    { key: "now", run: () => {
      const now = document.querySelector("#page > .now:not(.open)");
      const body = now && now.querySelector(".tx-now");
      if (!body) return false;
      now.dataset.fitWas = now.classList.contains("fits") ? "fits" : "clamp";
      now.classList.replace("fits", "clamp");
      now.classList.add("fit-short");
      if (body.scrollHeight <= body.clientHeight + 1) now.classList.replace("clamp", "fits"); // 三行就放得下：不要淡出與「展開全文」
      return true;
    } },
    // 6a. 出陣回報（frontReportHtml）：那一句收掉、小籤收成一行（放不下淡出），進度條照留；點了整塊攤開（S.frontOpen 記這一則，重畫時不再收）
    { key: "front", run: () => {
      const el = document.querySelector("#page .sfront");
      if (!el || S.frontOpen === frontKey(S.main.front)) return false;
      el.classList.add("fit-tight");
      el.setAttribute("data-act", "front-more");
      el.setAttribute("role", "button");
      el.setAttribute("tabindex", "0");
      el.setAttribute("aria-expanded", "false");
      return true;
    } },
    // 6a'. 還放不下：出陣回報標題那一行與其餘的條也收掉，只留第一條（自己那一條；守是對面最高的那一條）與一行小籤
    { key: "front2", run: () => {
      const el = document.querySelector("#page .sfront.fit-tight");
      if (!el) return false;
      el.classList.add("fit-min");
      return true;
    } },
    // 6b. 場景底下別人遞來的邀請（FB-117：最多畫兩份，socialHtml）：還放不下就從最後一份往前收，收到放得下為止，
    //     收掉的併進「還有 N 份邀請 ▾」那一行（沒有那一行就補一行），點了全部攤開（callsOpened：玩家點開過、還是點開那時的那幾份，就不再收）
    { key: "calls", run: () => {
      const box = document.querySelector("#page > .card.scene .calls");
      if (!box || callsOpened((S.main && S.main.calls) || [])) return false;
      const rows = [...box.querySelectorAll(":scope > .call")];
      if (!rows.length) return false;
      // 「還有 N 份」那一行先放好、每收一份就換字，再量：以前收完才補那一行，量的時候少算了它的高度，補上之後行動列又掉回分頁列底下
      // （375×812、兩份、師父的框在：只收了一份，行動列 679～777）
      let more = box.querySelector(":scope > .calls-more");
      if (!more) {
        box.insertAdjacentHTML("beforeend", '<button class="linkish calls-more" data-act="calls-more" data-fit="1"></button>');
        more = box.querySelector(":scope > .calls-more");
      } else if (more.dataset.text == null) more.dataset.text = more.textContent;
      const total = Number(box.dataset.total) || rows.length;
      let hidden = 0;
      do {
        rows[rows.length - 1 - hidden].classList.add("fit-hide");
        hidden += 1;
        more.textContent = callsMoreText(total - (rows.length - hidden), hidden === rows.length);
      } while (fitOver() > 0 && hidden < rows.length);
      return true;
    } },
    // 6c. 量的目標是約戰卡第一張可按的那一行（fitDuelRow，FB-9006）、前面的步驟都收了還放不下（矮手機：375×667、360×700 被分頁列蓋了 4～10 px）：
    //     閒著（沒有分隔線：不是集結、觀戰）的場景卡把所在地的描述每段收成一行、放不下加「…」，點了整張場景卡攤開（同第 7 步：fitClip、
    //     ownOpen，S.ownOpen 記著玩家攤開過就不再收）。企劃者 2026-10-28「擠完再上」。排在 7 之前：先收不少字的步驟，還不夠才收描述。
    //     只在量約戰那一行時做：目標是行動列、一組選項時一個像素都不動。「此地還有」、結伴、別人遞來的邀請（.calls）、地名與時刻那一條
    //     （有畫時疊在畫上；沒有畫時是場景卡第一段）都不是描述，不收
    { key: "desc", run: () => {
      if (!fitDuelRow()) return false;
      const scene = sceneBody();
      if (!scene || scene.querySelector(":scope > hr") || !idleMenu(S.main) || S.ownOpen === fitOwnKey()) return false;
      const paras = [...scene.querySelectorAll(":scope > p:not([class])")];
      if (!document.querySelector("#page > .card.scene:not(.road)").querySelector(":scope > .scene-art")) paras.shift(); // 沒有畫：第一段是「【地名】危險 ★★」那一條，不是描述
      const any = fitClip(paras);
      if (any) scene.classList.add("fit-own"); // 跟第 7 步同一個記號（ownOpen、fitReset 照樣拿掉）
      return any;
    } },
    // 7. 決戰集結、只能觀戰時，場景卡在戰場底下接著所在地（分隔線之後）：閒著時那是地點的描述，每段收成一行、點了攤開（S.ownOpen）。
    //    有事件、有所感、對話時分隔線之後是那件事本身（joy 的字），不收
    { key: "own", run: () => {
      const scene = sceneBody();
      if (!scene || !scene.querySelector(":scope > hr") || !idleMenu(S.main) || S.ownOpen === fitOwnKey()) return false;
      scene.classList.add("fit-own");
      return fitClip(scene.querySelectorAll(":scope > hr ~ p"));
    } },
    // 8. 戰場名字底下、分隔線之前那幾句（集結、開打的消息，開頭是「集結中，還剩現實 N 分 N 秒」）收成一行，點了攤開（同上）。
    //    加入的鈕在名字那一行（FB-105 的 musterScene）時從那一行底下算起，後半（「選擇陣營加入…」）名字旁那一小句已經說了；
    //    沒有鈕（人不在那個大區、加入過了、觀戰）時從名字底下算起——別的大區集結時那一句「…這場決戰在南陽，人要到了那裡…」兩行高，
    //    以前沒有鈕就從來不收（走查）。數字收不進一行的那一句不收（fitClip）
    { key: "muster", run: () => {
      const scene = sceneBody();
      if (!scene || !scene.querySelector(":scope > hr") || S.ownOpen === fitOwnKey()) return false;
      if (scene.querySelector(":scope > .battle-shut")) return false; // 只能觀戰的人自己攤開的開打中的戰場（FB-120）：不收
      const head = scene.querySelector(":scope > .muster-head") || scene.querySelector(":scope > p");
      const lines = [];
      for (let p = head && head.nextElementSibling; p && p.tagName !== "HR"; p = p.nextElementSibling) if (p.tagName === "P") lines.push(p);
      scene.classList.add("fit-muster");
      return fitClip(lines);
    } },
    // 9. 一組選項（事件、有所感的做法）時，鈕與鈕之間收緊、鈕矮一點（44px，觸控照樣按得到）
    { key: "options", run: () => {
      const menu = document.querySelector("#page > .options");
      if (menu) menu.classList.add("fit-tight");
      return !!menu;
    } },
    // 10. 一組選項時鈕收緊了還放不下（名聲的俠寇選項讓事件多到六顆；企劃者 2026-10-16 從三張截圖挑 (c)）：態勢那一排（.peek）收起、
    //     （減法季批 1 起是本週卡）「剛剛」只留時間與標題（得失照舊在，「展開全文」看全文）、灰掉的俠寇鈕底下那一行原因收掉（原因本來就寫在鈕的 title，點了說整句，
    //     見 data-act="opt-why"）。閒著（行動列）時不收；攤開了態勢那一排某一格、展開了「剛剛」的不收那一樣
    { key: "choices", run: () => {
      if (document.querySelector("#page > .act-bar") || !document.querySelector("#page > .options")) return false;
      let any = false;
      const peek = document.querySelector("#page > .wk-card");
      if (peek && !peek.querySelector(".wk-panel")) {
        peek.classList.add("fit-hide");
        any = true;
      }
      const now = document.querySelector("#page > .now:not(.open)");
      const body = now && now.querySelector(".tx-now");
      if (body && body.querySelector(".tx-line")) {
        if (!now.classList.contains("fit-short")) { // 第 6 步沒收過（不會發生，保險）：照它的記法記下原本的樣子，還原時一起回去
          now.dataset.fitWas = now.classList.contains("fits") ? "fits" : "clamp";
          now.classList.add("fit-short");
        }
        now.classList.replace("fits", "clamp"); // 字收掉了：「展開全文」要在（第 6 步三行放得下時換成了 fits、沒有那顆鈕）
        now.classList.add("fit-title");
        any = true;
      }
      document.querySelectorAll("#page > .options > .btn.off .opt-note").forEach((el) => { el.classList.add("fit-hide"); any = true; });
      return any;
    } },
  ];
  // 還原（重量之前）：只拿掉 fitFirstScreen 自己加的東西
  function fitReset() {
    const page = fitPage();
    if (!page) return;
    page.classList.remove("fit-space");
    page.querySelectorAll(".fit-space").forEach((el) => el.classList.remove("fit-space"));
    page.querySelectorAll(".fit-box").forEach((el) => el.classList.remove("fit-box"));
    page.querySelectorAll(".card.letter.fit-letter").forEach((el) => { // 1a：信攤回來
      el.classList.remove("fit-letter");
      const head = el.querySelector(":scope > .letter-head"), arrow = el.querySelector(".letter-arrow");
      if (head) head.setAttribute("aria-expanded", "true");
      if (arrow) arrow.textContent = "▴";
    });
    if (S.renownTight) { S.renownTight = false; renderTop(); } // 名聲（1B）：稱號那一行畫回來再量
    page.querySelectorAll(".g-merit small.fit-hide").forEach((el) => el.classList.remove("fit-hide")); // 本場戰功的稱號（4B）
    page.querySelectorAll(".tx-tight").forEach((el) => {
      el.classList.remove("tx-tight");
      ["data-act", "role", "tabindex", "aria-expanded"].forEach((a) => el.removeAttribute(a));
    });
    page.querySelectorAll(".fit-fold").forEach((el) => el.classList.remove("fit-fold"));
    page.querySelectorAll(".fit-art").forEach((el) => el.classList.remove("fit-art")); // 5a
    page.querySelectorAll(".fit-extra").forEach((el) => { // 5c
      el.classList.remove("fit-extra");
      ["data-act", "role", "tabindex", "aria-expanded"].forEach((a) => el.removeAttribute(a));
    });
    page.querySelectorAll(".wk-card.fit-hide, .opt-note.fit-hide").forEach((el) => el.classList.remove("fit-hide")); // 第 10 步
    page.querySelectorAll(".now.fit-title").forEach((el) => el.classList.remove("fit-title")); // 第 10 步；fits／clamp 照下一段還原
    page.querySelectorAll(".now.fit-short").forEach((el) => {
      el.classList.remove("fit-short");
      if (el.dataset.fitWas && !el.classList.contains("open")) el.classList.replace(el.classList.contains("fits") ? "fits" : "clamp", el.dataset.fitWas);
      delete el.dataset.fitWas;
    });
    page.querySelectorAll(".fit-own, .fit-muster").forEach((el) => el.classList.remove("fit-own", "fit-muster")); // 第 6c、7、8 步（收成一行的段落由下面的 fitUnclip 攤回來）
    page.querySelectorAll(".call.fit-hide").forEach((el) => el.classList.remove("fit-hide")); // 6b：收掉的邀請攤回來
    page.querySelectorAll(".calls-more").forEach((el) => {
      if (el.dataset.fit) el.remove();
      else if (el.dataset.text != null) { el.textContent = el.dataset.text; delete el.dataset.text; }
    });
    fitUnclip(page);
    page.querySelectorAll(".fit-tight").forEach((el) => el.classList.remove("fit-tight"));
    page.querySelectorAll(".sfront.fit-min").forEach((el) => el.classList.remove("fit-min"));
    page.querySelectorAll('.sfront[data-act="front-more"]').forEach((el) => {
      ["data-act", "role", "tabindex", "aria-expanded"].forEach((a) => el.removeAttribute(a));
    });
  }
  // 場景卡裡收成一行的段落（第 6c、7、8 步）：一行、放不下加「…」（style.css 的 p.fit-clip），點了整張場景卡攤開（ownOpen）。
  // 收了之後數字（倒數、戰局）會藏到「…」後面的那一段不收
  function fitClip(paras) {
    let any = false;
    paras.forEach((p) => {
      p.classList.add("fit-clip");
      if (!fitDigitsShown(p)) { dropClip(p); return; }
      p.setAttribute("data-act", "own-more");
      p.setAttribute("role", "button");
      p.setAttribute("tabindex", "0");
      p.setAttribute("aria-expanded", "false");
      any = true;
    });
    return any;
  }
  // 收成一行之後，裡面的數字還整個看得到嗎：最後一個數字的右緣要在那一行右緣往內 1em 以內（「…」佔的位置）。
  // 收成一行的字照樣排在框外面（只是畫不出來），所以量得到它在哪。量不了（瀏覽器沒有 Range）就當看得到
  function fitDigitsShown(el) {
    if (!document.createRange || !document.createTreeWalker) return true;
    const walk = document.createTreeWalker(el, 4); // NodeFilter.SHOW_TEXT
    let node = null, at = -1;
    for (let n = walk.nextNode(); n; n = walk.nextNode()) {
      const i = n.data.search(/[0-9０-９][^0-9０-９]*$/);
      if (i >= 0) { node = n; at = i; }
    }
    if (!node) return true;
    const range = document.createRange();
    range.setStart(node, at);
    range.setEnd(node, at + 1);
    const em = parseFloat(getComputedStyle(el).fontSize) || 16;
    return range.getBoundingClientRect().right <= el.getBoundingClientRect().right - em;
  }
  // 攤開過的是哪一處的哪一場（審查 I2）：所在地＋場景第一段（戰場名字），數字拿掉。集結、開打時場景裡的倒數與回合每一次輪詢都在變，
  // 拿整個場景當記號的話，玩家剛攤開的那幾段下一輪就又收回去
  function fitOwnKey() {
    const m = S.main || {};
    const first = String(m.scene || "").split("</p>")[0].replace(/[0-9０-９]+/g, "#");
    return `${(m.status && m.status.location) || ""}|${first}`;
  }
  // 拿掉收成一行的記號。classList 拿光 class 之後，真的瀏覽器留下空的 class=""，而第 6c 步（desc）用 :scope > p:not([class]) 挑沒有 class 的描述段落——
  // 空屬性還在就再也選不到：沒有重畫的重量（轉向、拉視窗、點名號展開再收起）之後折疊消失、約戰鈕又掉回分頁列底下（FB-9010）。空了就把屬性整個拿掉
  function dropClip(p) {
    p.classList.remove("fit-clip");
    if (!p.getAttribute("class")) p.removeAttribute("class");
  }
  function fitUnclip(root) {
    root.querySelectorAll(".fit-clip").forEach((p) => {
      dropClip(p);
      ["data-act", "role", "tabindex", "aria-expanded"].forEach((a) => p.removeAttribute(a));
    });
  }
  // 收了哪幾步（記在 S.fitted，給測試與除錯看）
  function fitFirstScreen() {
    S.fitted = [];
    S.fitWidth = window.innerWidth; // 這一次量的是哪個寬度（fitOnResize 看它）
    if (S.stage !== "game" || S.tab !== "jianghu" || !S.main || S.main.on_road || pro() || !fitPage()) return;
    S.fitting = true; // 收 💡、還原時會重畫狀態列：那不是「狀態列變了」（fitTopMoved）
    try {
      fitReset();
      for (const step of FIT_STEPS) {
        if (fitOver() <= 0) break;
        if (step.run()) S.fitted.push(step.key);
      }
    } finally {
      S.fitting = false;
    }
  }
  // 狀態列變高變矮（FB-123）：點名號展開配點、收起，💡 冒出來或變兩行，攤開體力說明——行動列跟著上下移，重量一次（從還原開始：
  // 收起名號之後收著的那幾樣攤回來）。renderTop 把重畫之前的高度交過來；高度沒變（只是數字換了）不量。fitFirstScreen 自己收 💡、
  // 還原 💡 時重畫狀態列不算（S.fitting），不會一直重量
  function fitTopMoved(before) {
    const top = document.getElementById("top");
    if (!top || S.fitting || top.offsetHeight === before) return;
    fitFirstScreen();
  }
  // 視窗大小變了（檔案最後的 resize 監聽）：寬度變了（轉向、拉視窗）才重量。手機捲動時網址列收起、跑出來只改高度，也會觸發 resize——
  // 那時重量的話，第一屏外的那幾段會邊捲邊收、邊攤開（審查 M6）。平常的重畫（afterPage）照樣每次都量
  function fitOnResize() {
    if (window.innerWidth === S.fitWidth) return;
    fitFirstScreen();
  }
  // 戰鬥卡片底下收成一行的補充（第 4 步）：點了原地攤開、再點收起，不重畫；攤開記在 S.linesOpen（這一場的卡片），重畫時不再收
  function lineToggle(el) {
    const open = !el.classList.contains("open");
    S.linesOpen = open ? S.main.card_id : null;
    el.classList.toggle("open", open);
    el.setAttribute("aria-expanded", String(open));
  }
  // 場景卡裡放場景文字的那一層：介面重整的場景卡把文字包在 .rv-scene 裡（上面疊「剛剛」、底下結伴與邀請），舊的場景卡就是卡本身
  function sceneBody() {
    const card = document.querySelector("#page > .card.scene:not(.road)");
    return card && (card.querySelector(":scope > .rv-scene") || card);
  }
  // 決戰時收成一行的那幾段（所在地、集結那一句）：點了攤開（原地，不重畫）；記住這一處的這一場攤開過（fitOwnKey），重畫時不再收
  function ownOpen() {
    S.ownOpen = fitOwnKey();
    const scene = sceneBody();
    if (!scene) return;
    scene.classList.remove("fit-own", "fit-muster");
    fitUnclip(scene);
  }
