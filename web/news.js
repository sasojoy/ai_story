/* 天下大勢的網頁前端：見聞頁的畫法小工具（見聞改版，Joy 2026-11-08 對設計稿說「好」；設計稿 https://claude.ai/artifact/9VhnyRHvSUWWST6iDgYtEx）。
 *
 * 五顆籤一排：戰況、傳聞、江湖史、榜單、紀錄。同一件事只放一處、說明收起來、能點的排前面、長清單照日子分段只攤開最近兩天。
 * 頁面本身（pageNews、籤）照舊在殼 app.js，這裡只放它叫的小工具。跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。
 */
"use strict";

  const NEWS_OPEN_DAYS = 2; // 照日子分段的清單只攤開最近幾天，更早的收成一行
  const NEWS_LAYER_OPEN = 2; // 傳聞每一層只攤開最新的幾則

  // 一串分好日子的 [{day, html}]：前 NEWS_OPEN_DAYS 天攤開，其餘收進一個 <details>（「第 1～5 天」）
  function newsDaysHtml(days, cls = "") {
    const head = (d) => `<p class="nw-day">${esc(d.day)}</p>`;
    const shown = days.slice(0, NEWS_OPEN_DAYS).map((d) => head(d) + d.html).join("");
    const rest = days.slice(NEWS_OPEN_DAYS);
    if (!rest.length) return `<div class="nw-days ${cls}">${shown}</div>`;
    const span = rest.length === 1 ? rest[0].day : `${rest[rest.length - 1].day}～${rest[0].day.replace(/^第\s*/, "")}`;
    return `<div class="nw-days ${cls}">${shown}<details class="nw-more"><summary>${esc(span)}</summary>${rest.map((d) => head(d) + d.html).join("")}</details></div>`;
  }

  // 戰報（/api/reports 的 list）：標籤是「結果　第N場　時刻　地點　vs 對手」用全形空白接起來的一行。大戰固定在頂；其餘照日子分段，
  // 結果改成一顆小印（大勝、險勝綠；落敗紅；僵持灰），對手寫大，場次、時刻、地點寫小
  const NEWS_WIN = /勝/;
  const NEWS_LOSE = /敗|負/;
  // 見聞的紅點：新的一場（S.unseen 是那一場的戰報 id）——見聞分頁、戰況那一段、那一行三層（web/shell.js registerDot）
  if (typeof registerDot === "function") registerDot({ id: "report", at: "news", sub: "reports", on: () => !!S.unseen });

  function newsReportRow(x) {
    const dot = dotHtml(S.unseen && x.id === S.unseen);
    const bits = String(x.label || "").split("　").filter(Boolean);
    const result = bits[0] || "";
    const stamp = bits.find((b) => /^第\s*\d+\s*[天週]/.test(b)) || "";
    const foe = (bits.find((b) => /^vs\s/.test(b)) || "").replace(/^vs\s*/, "");
    const place = bits.filter((b) => b !== result && b !== stamp && !/^vs\s/.test(b) && !/^第\d+場$/.test(b)).join("・");
    const tone = NEWS_LOSE.test(result) ? "lose" : NEWS_WIN.test(result) ? "win" : "even";
    const clock = stamp.replace(/^.*\s(?=\d{1,2}:\d{2}$)/, "");
    if (!foe) return `<button class="nw-rep" data-act="report" data-id="${x.id}"><span class="nw-who">${esc(x.label)}</span>${dot}<span class="nw-go" aria-hidden="true">›</span></button>`;
    return `<button class="nw-rep" data-act="report" data-id="${x.id}"><span class="nw-seal ${tone}">${esc(result)}</span>`
      + `<span class="nw-who">${esc(foe)}<small>${esc([x.big ? stamp : clock, place].filter(Boolean).join("・"))}</small></span>${dot}<span class="nw-go" aria-hidden="true">›</span></button>`;
  }
  const NEWS_GO_FIGHT = "回江湖，出陣或上擂台打一場 ›"; // 待 joy 潤
  function newsReportsHtml(r) {
    if (!r) return '<div class="card"><p class="muted">載入中…</p></div>';
    // 還沒打過：底下一顆回江湖頁（出陣、遊歷、擂台都在那裡），不只一句「還沒打過仗」（UI 手感丙批 3-2）
    if (!r.list.length) return `<div class="card">${r.detail}<button class="linkish nw-go-fight" data-act="tab" data-tab="jianghu">${NEWS_GO_FIGHT}</button></div>`;
    const big = r.list.filter((x) => x.big), rest = r.list.filter((x) => !x.big);
    const days = [];
    for (const x of rest) {
      const stamp = String(x.label || "").split("　").find((b) => /^第\s*\d+\s*[天週]/.test(b)) || "";
      const day = stamp.replace(/\s+\d{1,2}:\d{2}$/, "") || "更早";
      if (!days.length || days[days.length - 1].day !== day) days.push({ day, rows: [] });
      days[days.length - 1].rows.push(x);
    }
    const bigHtml = big.length ? `<div class="nw-big">${big.map(newsReportRow).join("")}</div>` : "";
    return `<section class="card nw-card"><h3 class="nw-title">戰報<small>點開看過程</small></h3>${bigHtml}${
      newsDaysHtml(days.map((d) => ({ day: d.day, html: d.rows.map(newsReportRow).join("") })))}</section>`;
  }

  // 三路戰況（殼的 frontsBlock：點圖卡攤開說明）＋軍備一行；每一條的長說明、黃巾聲勢、可能的結局（伺服器的 trends）收在底下一行
  function newsFrontsHtml(m) {
    const bars = m.fronts && shown("fronts") ? frontsBlock(m) : "";
    if (!bars && !armsLine(m)) return m.trends ? `<section class="card nw-card">${m.trends}</section>` : "";
    const more = m.trends ? `<details class="nw-more"><summary>說明與可能的結局</summary><div class="nw-rm">${m.trends}</div></details>` : ""; // 待 joy 潤
    return `<section class="card nw-card"><h3 class="nw-title">三路戰況<small>藍官軍・金黃巾</small></h3>${bars}${armsLine(m)}${more}</section>`;
  }

  // 天下形勢（/api/xingshi）：只攤最新一篇的兩行，點開讀全篇；往日的收成一行（篇是殼 xingshiHtml 同一份料）
  function newsXingshiHtml(x) {
    if (!x || !x.on || !x.essays || !x.essays.length) return "";
    const [top, ...old] = x.essays;
    const essay = (e) => `<p class="xs-title">${esc(e.title)}</p>${xingshiParas(e.essay)}`;
    return `<section class="card nw-card nw-xs"><h3 class="nw-title">天下形勢<small>${esc(top.time)}</small></h3>
      <details class="nw-xs-top"><summary><span class="nw-clamp">${esc(String(top.essay || top.line).replace(/\s+/g, ""))}</span></summary>${essay(top)}</details>${
      old.length ? `<details class="nw-more"><summary>往日 ${old.length} 篇</summary>${old.map((e) => `<details class="xs-essay"><summary><span class="xs-line">${esc(e.line)}</span><span class="xs-time">${esc(e.time)}</span></summary><div class="xs-body">${essay(e)}</div></details>`).join("")}</details>` : ""}</section>`;
  }

  // 傳聞分層（伺服器的 rumor_layers）：天下大事搬去江湖史，這裡只放口耳相傳的；離你越近排越前面（跟你有關、所在那一帶、陣營軍情）。
  // 每一層只攤開最新的 NEWS_LAYER_OPEN 則，其餘收成「再看 N 則」
  const NEWS_LAYER_ORDER = ["personal", "local", "faction"];
  const NEWS_LAYER_NAME = { personal: "跟你有關" }; // 待 joy 潤
  function newsRumorLayersHtml(layers) {
    const by = Object.fromEntries((layers || []).map((l) => [l.id, l]));
    return NEWS_LAYER_ORDER.filter((id) => by[id]).map((id) => {
      const l = by[id];
      const paras = String(l.body).match(/<p>[\s\S]*?<\/p>/g) || [];
      const body = paras.length > NEWS_LAYER_OPEN
        ? paras.slice(0, NEWS_LAYER_OPEN).join("") + `<details class="nw-more"><summary>再看 ${paras.length - NEWS_LAYER_OPEN} 則</summary>${paras.slice(NEWS_LAYER_OPEN).join("")}</details>`
        : l.body;
      return `<section class="card nw-card rumor-layer" data-layer="${esc(l.id)}"><h3 class="nw-title">${esc(NEWS_LAYER_NAME[l.id] || l.title)}</h3><div class="nw-rm">${body}</div></section>`;
    }).join("");
  }

  // 傳國玉璽裂成七塊（Joy 11/08 嫌七個小方格陽春）：一方印面照裂紋分成七片，現世的那幾片是玉色、看得到刻的字，還沒現世的只留裂紋的虛線
  const NEWS_SEAL_SHARDS = ["0,0 45,0 38,35 0,42", "45,0 100,0 100,30 62,40 38,35", "0,42 38,35 50,62 0,70", "38,35 62,40 70,65 50,62",
    "62,40 100,30 100,72 70,65", "0,70 50,62 42,100 0,100", "50,62 70,65 100,72 100,100 42,100"];
  function newsSealSvg(lit) {
    const all = lit.every(Boolean);
    const shards = NEWS_SEAL_SHARDS.map((pts, i) => `<polygon points="${pts}" class="${lit[i] ? "on" : ""}"/>`).join("");
    return `<svg class="nw-seal-svg" viewBox="-8 -30 116 140" aria-hidden="true"><defs>`
      + `<linearGradient id="nwJade" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#9fd3b8"/><stop offset=".45" stop-color="#4f9a7a"/><stop offset="1" stop-color="#245c47"/></linearGradient>`
      + `<clipPath id="nwLit">${NEWS_SEAL_SHARDS.filter((_, i) => lit[i]).map((pts) => `<polygon points="${pts}"/>`).join("")}</clipPath></defs>`
      + `<path class="knob${all ? " on" : ""}" d="M18 -2 C16 -14 26 -24 36 -20 C40 -28 60 -28 64 -20 C74 -24 84 -14 82 -2 Z"/>`
      + `<g class="face">${shards}</g><g class="carve" clip-path="url(#nwLit)"><text x="72" y="44">受</text><text x="72" y="84">命</text><text x="28" y="44">於</text><text x="28" y="84">天</text></g><rect class="rim" x="9" y="9" width="82" height="82" rx="2"/></svg>`;
  }

  // 江湖史（伺服器的 chronicle，Markdown 轉好的 HTML）：最上面的傳國玉璽那一段收成一行七格（點開照舊是那一段）；這一季照日子分段
  // （伺服器寫好的 <h4>），只攤開最近兩天；往季（<h3>第 N 季）、歷屆擂主照舊排在後面
  function newsChronicleHtml(html) {
    let parts = String(html || "").split(/<hr\s*\/?>/);
    let seal = "";
    if (/傳國玉璽/.test(parts[0]) && parts.length > 1) {
      const block = parts.shift();
      const items = block.match(/<li>[\s\S]*?<\/li>/g) || [];
      const lit = items.length ? items.map((li) => !/未現世/.test(li)) : Array(7).fill(false);
      const out = lit.filter(Boolean).length;
      seal = `<details class="nw-row nw-seal-row"><summary>${newsSealSvg(lit)}<span class="nw-seal-name">傳國玉璽<small>${out === lit.length ? "七片都已現世" : out ? `${out} 片已現世，還有 ${lit.length - out} 片下落不明` : "七片碎片都還沒現世"}</small></span><span class="nw-go" aria-hidden="true">›</span></summary>${block}</details>`; // 待 joy 潤
    }
    // 這一季（沒有往季時沒有標題；有往季時標「第 N 季（本季）」）攤開，往季那幾段（<h3>第 N 季）與歷屆擂主收進「往季的江湖史」
    let now = "", past = "";
    for (const sec of parts.join("<hr />").split(/(?=<h3>)/)) {
      if (!/<h3>/.test(sec) || /本季/.test(sec)) now += sec.replace(/<h3>[\s\S]*?<\/h3>/, "");
      else past += sec;
    }
    const chunks = now.split(/(?=<h4>)/).filter((c) => /<h4>/.test(c));
    const days = chunks.map((c) => ({ day: (c.match(/<h4>([\s\S]*?)<\/h4>/) || ["", ""])[1].replace(/<[^>]+>/g, ""), html: c.replace(/<h4>[\s\S]*?<\/h4>/, "") }));
    const current = days.length ? newsDaysHtml(days, "nw-hist") : now;
    return { seal, body: `<div class="card nw-card">${current}${past ? `<details class="nw-more"><summary>往季的江湖史</summary>${past}</details>` : ""}</div>` };
  }

  // 紀錄（伺服器的 journal、older：已經只剩自己的事、連著的前往併成一行）：照日子分段，時間欄只寫時刻；只攤開最近兩天
  function newsJournalHtml(html) {
    const rows = String(html || "").replace(/<\/?div class="tx-journal">/g, "").split(/(?=<(?:div|details) class="tx-row")/).filter((r) => /tx-row/.test(r));
    const days = [];
    for (const row of rows) {
      const stamp = ((row.match(/<span class="tx-time">([\s\S]*?)<\/span>/) || ["", ""])[1]);
      const m = stamp.match(/^(.*\S)\s+(\d{1,2}:\d{2})$/);
      const day = m ? m[1] : stamp;
      const cut = m ? row.replace(`<span class="tx-time">${stamp}</span>`, `<span class="tx-time">${m[2]}</span>`) : row;
      if (!days.length || days[days.length - 1].day !== day) days.push({ day, html: "" });
      days[days.length - 1].html += cut;
    }
    return days.length ? newsDaysHtml(days.map((d) => ({ day: d.day, html: `<div class="tx-journal">${d.html}</div>` })), "nw-journal") : "";
  }

  // 進遊戲後跳一次的改版資訊（Joy 2026-11-07「以前改版資訊是在登入那邊 但是現在幾乎不會到那頁 因為會記錄session」）：
  // 有這支手機還沒看過的新版就從底下跳一張，照給玩家的格式【天下大勢　改版資訊 M/D】、新功能／調整／修正一項一行；按「知道了」就關、
  // 記下最新那一次，下一次改版才再跳。好幾次沒看的：最新那次攤開，其餘各收成一行。序章裡、特殊事件的跳顯框還沒看完先不跳；
  // 這支手機從沒看過任何一次的只給最新那一次。簽到小窗排在它後面（同一刻只跳一張）。記不住（私密視窗）就這一次關了算數
  const PATCH_SEEN = "tianxia.patchSeen";
  const PATCH_OK = "知道了";
  // 認一次改版：日期加三段各幾條（同一天補發一次也算新的）
  const patchKey = (p) => `${p.date}|${["new", "tweak", "fix"].map((k) => (p[k] || []).length).join(",")}`;
  function patchUnseen() {
    const notes = S.patchNotes || [];
    if (S.patchSeen === undefined) { try { S.patchSeen = localStorage.getItem(PATCH_SEEN) || ""; } catch (e) { S.patchSeen = ""; } }
    const at = notes.findIndex((p) => patchKey(p) === S.patchSeen);
    return at < 0 ? notes : notes.slice(0, at);
  }
  function patchPopHtml(m) {
    if (pro() || (m.story_cards || []).length) return "";
    if (S.nxAfter) { const id = S.nxAfter; S.nxAfter = null; setTimeout(() => nxGo(id), 0); return ""; } // 登入頁按了「去看看」：登入進來就帶過去
    if (!nxSeen()) return nxInviteHtml(); // 江湖新事：這一批新功能每支手機跳一次，排在改版資訊前面
    if (!S.patchNotes) return ""; // 進遊戲那一刻（enter）才讀一次；還沒讀到不跳
    const [top, ...older] = patchUnseen();
    if (!top) return "";
    return `<div class="sheet-bg" data-act="patch-close"></div><div class="sheet patch-pop" role="dialog" aria-label="改版資訊"><div class="grip"></div>`
      + `<div class="patch-card"><h3>【天下大勢　改版資訊 ${esc(top.date)}】</h3>${nxLinkHtml()}${patchLines(top)}`
      + `${(S.patchSeen ? older : []).map((p) => `<details class="patch-old"><summary>改版資訊 ${esc(p.date)}</summary>${patchLines(p)}</details>`).join("")}</div>`
      + `<button class="btn primary patch-ok" data-act="patch-close">${PATCH_OK}</button></div>`;
  }
  function patchPopClose() {
    const top = (S.patchNotes || [])[0];
    if (!top) return;
    S.patchSeen = patchKey(top);
    try { localStorage.setItem(PATCH_SEEN, S.patchSeen); } catch (e) { /* 私密視窗：這一次關了算數 */ }
  }
  // 江湖新事（Joy 2026-11-12「做一個這批新功能的專屬介紹頁面」；畫稿 v2 Joy 選親衛的說法 B、後面四樣都放）：一頁九樣新功能，
  // 一樣一張圖一句話一顆「去看看」，按了帶到那個功能的最後一層（Joy 11/12「事情不要只做一半」）。字與圖都在這支檔裡，登入頁也畫得出來，
  // 不用新開不用登入的路由。三個入口：登入頁「改版資訊」上面一條橫幅、進遊戲後每支手機跳一次（看過不再跳；之後在改版資訊小窗頂上、
  // 設定「新手與說明」裡點得到）。整頁是疊在最上面的一層（#nx-layer，掛在 body 上，跟殼的重畫無關）
  const NX_KEY = "2026-11-12"; // 這一批的版號：下一批新功能換一個字串，每支手機再跳一次
  const NX_SEEN = "tianxia.introSeen";
  const NX_HEAD = "江湖新事"; // 待 joy 潤
  const NX_SAY = "這一季，江湖多了幾條路可走。"; // 待 joy 潤
  const NX_GO = "去看看 ›"; // 待 joy 潤
  const NX_LATER = "之後再看"; // 待 joy 潤
  const NX_OPEN = "去看看"; // 待 joy 潤
  const NX_DONE = "入江湖"; // 待 joy 潤
  const NX_END = "其餘的，留給你自己去江湖上撞見。"; // 待 joy 潤
  const NX_LOGIN = "登入之後就帶你過去"; // 待 joy 潤
  const NX_NUMS = "壹貳參肆伍陸柒捌玖";
  // 一樣一筆：art 是 /static/ 底下的圖；show 是不放圖、畫成實物的那幾樣（金蘭帖、信箋、親衛長大、名駒去背、圖上蓋印）
  const NX_ITEMS = [
    { id: "zongmen", name: "門　派", line: "拜進山門，同門把各自悟到的招式，寫進同一本武譜。", art: "img/events/temple.webp" }, // 待 joy 潤
    { id: "jieyi", name: "結　義", line: "兄弟在路上被人截了，這筆帳，你替他討回來。", show: "jieyi" }, // 待 joy 潤
    { id: "guard", name: "拾孤成衛", line: "你救下的那個孩子，有一天會替你擋下一刀。", show: "grow" }, // 待 joy 潤（Joy 11/12 選 B）
    { id: "mail", name: "帖友書信", line: "換過名帖的人，相隔千里也能寫信問候。", show: "letter" }, // 待 joy 潤
    { id: "titles", name: "稱號與官職", line: "立了功，名號旁就多一方印，走到哪都有人認得。", art: "img/events/office.webp", show: "seals" }, // 待 joy 潤
    { id: "craft", name: "合璧成神", line: "兩股意念擰成一線，合璧成神，悟出真意。", art: "img/stories/dunwu_done.webp" }, // 待 joy 潤
    { id: "horses", name: "天下名駒", line: "野馬能馴，敵馬能奪；四匹名駒，一季只認一個主人。", show: "horse" }, // 待 joy 潤
    { id: "temper", name: "回爐淬煉", line: "兵器回爐，一階一階往上衝，越往上越險。", art: "img/gear/scene-smithy.webp" }, // 待 joy 潤
    { id: "tavern", name: "酒肆題壁", line: "酒過三巡，在牆上題一句，往來的人都看得到。", art: "img/events/tavern.webp" }, // 待 joy 潤
  ];
  // 實物：金蘭帖上的三個名字、信箋上的字、圖上那三方印都是示意（印是遊戲裡真有的名號與官職）
  const NX_SHOW = {
    jieyi: '<div class="nx-jy" aria-hidden="true"><small>金蘭譜</small><b class="nx-jy-hd">義結金蘭</b><span class="nx-jy-men"><i><u>大</u><b>你</b></i><i><u>二</u><b>石青</b></i><i><u>三</u><b>阿遠</b></i></span></div>', // 待 joy 潤
    grow: '<div class="nx-grow" aria-hidden="true"><img class="kid" src="/static/img/guard/child/m-saved.webp" alt=""><span>⋯</span><img src="/static/img/guard/grown/m-xia-jing.webp" alt=""></div>',
    letter: '<div class="nx-letter" aria-hidden="true"><p>兄台台鑒：<br>　聞君已到潁川，<br>　改日酒肆再會。</p><span>石青</span></div>', // 待 joy 潤
    seals: '<span class="nx-seals" aria-hidden="true"><i class="s1">破陣首功</i><i class="s2">擂台三甲</i><i class="s3">校尉</i></span>',
    horse: '<div class="nx-horse" aria-hidden="true"><img src="/static/horse-liyun.webp" alt=""></div>',
  };
  function nxSeen() {
    if (S.nxSeen === undefined) { try { S.nxSeen = localStorage.getItem(NX_SEEN) || ""; } catch (e) { S.nxSeen = ""; } }
    return S.nxSeen === NX_KEY;
  }
  function nxMarkSeen() {
    S.nxSeen = NX_KEY;
    try { localStorage.setItem(NX_SEEN, NX_KEY); } catch (e) { /* 私密視窗：這一次看過就算 */ }
  }
  function nxCardHtml(it, i) {
    const art = it.art ? `<div class="nx-art" style="background-image:url('/static/${it.art}')"></div>` : "";
    const show = it.show ? NX_SHOW[it.show] : "";
    return `<article class="nx-card nx-${it.id}">${it.show === "seals" ? `<div class="nx-artwrap">${art}${show}</div>` : art + show}`
      + `<b class="nx-num" aria-hidden="true">${NX_NUMS[i]}</b>`
      + `<div class="nx-body"><h3>${it.name}</h3><p>${it.line}</p><button class="nx-go" data-act="nx-go" data-id="${it.id}">${NX_GO}</button></div></article>`;
  }
  // 整頁：頁首（官道的圖、直書的匾、朱印、一句）→ 九張卡 → 收尾一句與「入江湖」
  function nxPageHtml() {
    return `<div class="nx-page"><button class="nx-x" data-act="nx-close" aria-label="關閉">×</button>`
      + `<header class="nx-hero"><div class="nx-hero-art" role="img" aria-label="官道"></div><h2 class="nx-plaque">${NX_HEAD}</h2>`
      + `<div class="nx-hero-text"><span class="nx-seal">新　章</span><p>${NX_SAY}</p></div></header>`
      + `<div class="nx-list">${NX_ITEMS.map(nxCardHtml).join("")}</div>`
      + `<p class="nx-end">${NX_END}</p><button class="nx-done" data-act="nx-close">${NX_DONE}</button></div>`;
  }
  // 登入頁那一條、改版資訊小窗頂上那一行、設定裡那一顆：都只是「打開這一頁」
  function nxBannerHtml() {
    return `<button class="nx-ban" data-act="nx-open"><span class="nx-th" aria-hidden="true"></span><span class="nx-ban-t"><b>${NX_HEAD}</b><small>${NX_SAY}</small></span><span class="nx-chev" aria-hidden="true">›</span></button>`;
  }
  const nxLinkHtml = () => `<button class="nx-link" data-act="nx-open">${NX_HEAD}<span aria-hidden="true">›</span></button>`;
  const nxEntryHtml = () => `<button class="btn" data-act="nx-open">${NX_HEAD}</button>`;
  // 進遊戲後跳一次的小窗（排在改版資訊前面，同一刻只一張）：之後再看＝今天先不看（改版資訊小窗與設定裡還點得到）
  function nxInviteHtml() {
    return `<div class="sheet-bg" data-act="nx-later"></div><div class="sheet nx-invite" role="dialog" aria-label="${NX_HEAD}"><div class="grip"></div>${nxBannerHtml()}`
      + `<div class="nx-row"><button class="btn ghost" data-act="nx-later">${NX_LATER}</button><button class="btn primary" data-act="nx-open">${NX_OPEN}</button></div></div>`;
  }
  function nxOpen() {
    nxClose();
    const layer = document.createElement("div");
    layer.id = "nx-layer";
    layer.className = "nx-layer";
    layer.setAttribute("role", "dialog");
    layer.setAttribute("aria-label", NX_HEAD);
    layer.innerHTML = nxPageHtml();
    document.body.appendChild(layer);
    if (document.body.classList) document.body.classList.add("nx-lock"); // 底下的頁不跟著捲
  }
  function nxClose() {
    const old = document.getElementById("nx-layer");
    if (old) old.remove();
    if (document.body.classList) document.body.classList.remove("nx-lock");
  }
  // 按完把那一塊捲到眼前、描一下邊（最後一層：那一張卡、那一顆鈕本身）
  function nxFlash(sel) {
    requestAnimationFrame(() => {
      const el = document.querySelector(sel);
      if (!el) return;
      if (el.scrollIntoView) el.scrollIntoView({ block: "center", behavior: "smooth" });
      el.classList.add("nx-flash");
      setTimeout(() => el.classList.remove("nx-flash"), 2400);
    });
  }
  // 這一刻按得下去的那一個選項（江湖頁的那一顆、或店門）
  const nxOpt = (pred) => ((S.main && S.main.options) || []).find((o) => o.enabled !== false && pred(o.id));
  // 店在這裡就進店、翻到那一頁；不在城裡就開輿圖（去最近的城）
  async function nxShop(optId, then, sel) {
    const o = nxOpt((id) => id === optId);
    if (!o) { await goTab("map"); return; }
    if (S.tab !== "jianghu") await goTab("jianghu");
    await choose(document.querySelector(`[data-act="choose"][data-id="${CSS.escape(optId)}"]`) || document.createElement("button"), optId);
    then(); // 店門一開會回到第一頁：進了店再翻到那一頁
    if (typeof renderShop === "function" && S.main && S.main.shop) renderShop(false);
    nxFlash(sel);
  }
  // 「去看看」：九樣各帶到哪裡。沒登入（登入頁）先記著，登入進來的第一畫再帶過去
  async function nxGo(id) {
    nxClose();
    if (S.stage !== "game" || !S.main) {
      S.nxAfter = id;
      toast(NX_LOGIN);
      const input = document.querySelector("#gate-form input");
      if (input) input.focus();
      return;
    }
    const m = S.main;
    switch (id) {
      case "zongmen": {
        if (m.zongmen) { S.heroTab = "sect"; await goTab("practice"); nxFlash(".zongmen"); break; } // 是哪一門的人：師門那一頁
        const o = nxOpt((x) => x.startsWith("zongmen:")); // 此地就是山門：拜師那一顆
        if (o) { await goTab("jianghu"); nxFlash(`[data-id="${CSS.escape(o.id)}"]`); } else await goTab("map");
        break;
      }
      case "jieyi": S.newsBack = S.news; S.news = "mingtie"; await goTab("news"); nxFlash(".jieyi"); break; // 名帖匣裡的金蘭譜
      case "guard":
        if (m.guard) { S.heroTab = "mates"; await goTab("practice"); nxFlash(".guard"); } // 同伴那一頁最上面
        else { await goTab("jianghu"); nxFlash(".act-bar"); } // 還沒撞見：那個孩子是探索時遇上的
        break;
      case "mail": S.newsBack = S.news; S.news = m.mail ? "mail" : "mingtie"; await goTab("news"); break; // 信匣（沒開的季：先換名帖）
      case "titles":
        if (m.titles) { S.titlesOpen = true; render(); nxFlash(".ttl-sheet"); } // 名號旁的頭銜印攤開的那一張
        else { S.heroTab = "attrs"; await goTab("practice"); }
        break;
      case "craft": await goTab("craft"); nxFlash("#kiln-wrap"); break; // 煉製頁的爐
      case "horses": await nxShop("act:market", () => {}, ".stalls"); break; // 馬市的槽頭
      case "temper": await nxShop("act:smith", () => { S.shopTab = "rack"; }, ".shop-worn"); break; // 鐵匠鋪身上那件的淬煉
      case "tavern": await nxShop("act:tavern", () => { S.tavTab = "wall"; }, "#tav-wall"); break; // 酒肆的題壁
    }
  }

  async function newsClick(act, el, ev) {
    switch (act) {
        case "patch-close": patchPopClose(); renderPage(); break; // 進遊戲後跳的改版資訊：看過了，下一次改版才再跳
        case "nx-open": nxMarkSeen(); nxOpen(); if (S.stage === "game" && S.main) renderPage(); break; // 江湖新事：小窗按了「去看看」也就不再跳
        case "nx-later": nxMarkSeen(); renderPage(); break;
        case "nx-close": nxClose(); break;
        case "nx-go": await nxGo(el.dataset.id); break;
    } // newsClick
  } // newsClick
  registerClicks(newsClick, ["patch-close", "nx-open", "nx-later", "nx-close", "nx-go"]);
