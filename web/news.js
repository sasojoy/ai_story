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
  function newsReportRow(x) {
    const bits = String(x.label || "").split("　").filter(Boolean);
    const result = bits[0] || "";
    const stamp = bits.find((b) => /^第\s*\d+\s*[天週]/.test(b)) || "";
    const foe = (bits.find((b) => /^vs\s/.test(b)) || "").replace(/^vs\s*/, "");
    const place = bits.filter((b) => b !== result && b !== stamp && !/^vs\s/.test(b) && !/^第\d+場$/.test(b)).join("・");
    const tone = NEWS_LOSE.test(result) ? "lose" : NEWS_WIN.test(result) ? "win" : "even";
    const clock = stamp.replace(/^.*\s(?=\d{1,2}:\d{2}$)/, "");
    if (!foe) return `<button class="nw-rep" data-act="report" data-id="${x.id}"><span class="nw-who">${esc(x.label)}</span><span class="nw-go" aria-hidden="true">›</span></button>`;
    return `<button class="nw-rep" data-act="report" data-id="${x.id}"><span class="nw-seal ${tone}">${esc(result)}</span>`
      + `<span class="nw-who">${esc(foe)}<small>${esc([x.big ? stamp : clock, place].filter(Boolean).join("・"))}</small></span><span class="nw-go" aria-hidden="true">›</span></button>`;
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
    if (!S.patchNotes) return ""; // 進遊戲那一刻（enter）才讀一次；還沒讀到不跳
    const [top, ...older] = patchUnseen();
    if (!top) return "";
    return `<div class="sheet-bg" data-act="patch-close"></div><div class="sheet patch-pop" role="dialog" aria-label="改版資訊"><div class="grip"></div>`
      + `<div class="patch-card"><h3>【天下大勢　改版資訊 ${esc(top.date)}】</h3>${patchLines(top)}`
      + `${(S.patchSeen ? older : []).map((p) => `<details class="patch-old"><summary>改版資訊 ${esc(p.date)}</summary>${patchLines(p)}</details>`).join("")}</div>`
      + `<button class="btn primary patch-ok" data-act="patch-close">${PATCH_OK}</button></div>`;
  }
  function patchPopClose() {
    const top = (S.patchNotes || [])[0];
    if (!top) return;
    S.patchSeen = patchKey(top);
    try { localStorage.setItem(PATCH_SEEN, S.patchSeen); } catch (e) { /* 私密視窗：這一次關了算數 */ }
  }
  async function newsClick(act) {
    switch (act) {
        case "patch-close": patchPopClose(); renderPage(); break; // 進遊戲後跳的改版資訊：看過了，下一次改版才再跳
    } // newsClick
  } // newsClick
  registerClicks(newsClick, ["patch-close"]);
