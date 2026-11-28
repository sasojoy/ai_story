/* 見聞頁重排（功能包 jianwen；Joy 2026-11-27 看示意稿說「好」；示意稿 https://claude.ai/artifact/GCMDJegGkmJWVHfpLFeeg7）。
 *
 * 開關 Config.jianwen.enabled（預設關）：伺服器送 main.jianwen 時，見聞頁（web/app.js 的 pageNews，行狀、名帖匣、信匣以外）改用這裡的排法；
 * 關著照舊是那一排五顆籤。
 *
 * 由上到下（照江湖頁、俠客頁重排的元件：場景圖滿版、狀態一行、眼下一張卡、墨底的牌、點了從底下拉起）：
 *   1. 天下的圖滿版，題「見聞」、一方「邸報」印；狀態一行疊在圖上
 *   2. 一句天下形勢（最新一篇的頭一句，沒有就是本週的主題）
 *   3. 眼下一張卡：最新、跟你最有關的一件（剛打完的一場、有人在說你、你上了榜、本週大事），鈕就在卡上；其餘收成「另有 N 件」
 *   4. 五面牌（戰況、傳聞、江湖史、榜單、紀錄）：戰況那一面最大，三路戰況畫成三條墨痕；點一面拉起那一塊
 * 拉起的那一塊記在 S.jwSec；別處跳過來（S.news 變了、點開一場戰報、戰記）就拉起那一塊。點開一場戰報、戰記時，那一塊裡畫原本那一頁（old）。
 * 一顆紅點的來源照舊（web/news.js 的 report），第三層畫在那一行。
 */
"use strict";

  const jwOn = (m) => !!(m && m.jianwen && m.jianwen.on);

  const JW_ART = "/static/img/places/world.webp";
  const JW_SEAL = "邸報"; // 待 joy 潤
  const JW_GLYPH = { reports: "戰", rumors: "聞", chronicle: "史", boards: "榜", journal: "記" };
  const JW_CLOSE = "關閉"; // 待 joy 潤
  const JW_MORE = "另有 {n} 件"; // 待 joy 潤
  const JW_LATER = "知道了"; // 待 joy 潤
  const JW_IDLE = "還沒有新消息"; // 待 joy 潤
  const JW_IDLE_SUB = "打一場、聽一回酒肆的閒談，這裡就會有東西。"; // 待 joy 潤
  const JW_NO_FIGHT = "還沒有戰報"; // 待 joy 潤
  const JW_NO_FIGHT_SUB = "出陣、上擂台，或在路上遇事打一場，每一場都記在這裡。"; // 待 joy 潤
  const JW_GO_FIGHT = "回江湖打一場"; // 待 joy 潤
  const JW_OPEN_DAYS = 2; // 照日子分段的清單只攤開最近幾天
  const JW_LAYER_OPEN = 2; // 傳聞每一層只攤開最新的幾則

  const jwText = (html) => (typeof plainText === "function" ? plainText(html) : String(html || "").replace(/<[^>]*>/g, ""));
  const jwToggle = (key) => !!(S.jwMore && S.jwMore[key]);
  const jwMoreBtn = (key, label) => `<button class="jw-fold" data-act="jw-more" data-key="${esc(key)}" aria-expanded="${jwToggle(key)}">${esc(label)}</button>`;

  // 一條戰線的一句話（不寫數字）：0 是官軍穩控、100 是黃巾控制；亂局照伺服器給的 chaos（rules.chaos_fronts 那一份）
  function jwFrontSay(f) {
    const v = f.value | 0;
    if (f.chaos) return "亂局"; // 待 joy 潤
    if (v >= 85) return "黃巾控制"; // 待 joy 潤
    if (v > 50) return "黃巾佔上風"; // 待 joy 潤
    if (v <= 15) return "官軍穩控"; // 待 joy 潤
    if (v < 50) return "官軍佔上風"; // 待 joy 潤
    return "相持"; // 待 joy 潤
  }
  const jwFronts = (m) => (m.fronts && m.fronts.length && shown("fronts") ? m.fronts : []);
  const jwBar = (f) => `<span class="jw-bar" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${f.value | 0}" aria-label="${esc(f.name)}：${esc(jwFrontSay(f))}" style="--h:${Math.max(0, Math.min(100, f.value | 0))}%"></span>`;

  // 戰報那一行的料（web/news.js 同一套切法）：結果、對手、日子、時刻、地點
  function jwRep(x) {
    const bits = String(x.label || "").split("　").filter(Boolean);
    const result = bits[0] || "";
    const stamp = bits.find((b) => /^第\s*\d+\s*[天週]/.test(b)) || "";
    const foe = (bits.find((b) => /^vs\s/.test(b)) || "").replace(/^vs\s*/, "");
    const place = bits.filter((b) => b !== result && b !== stamp && !/^vs\s/.test(b) && !/^第\d+場$/.test(b)).join("・");
    const tone = /敗|負/.test(result) ? "lose" : /勝/.test(result) ? "win" : "even";
    const day = stamp.replace(/\s+\d{1,2}:\d{2}$/, "") || "更早";
    const clock = (stamp.match(/(\d{1,2}:\d{2})$/) || ["", ""])[1];
    return { result, foe, place, tone, day, clock, stamp };
  }
  const jwSealWord = (r) => (r.tone === "win" ? "勝" : r.tone === "lose" ? "敗" : "和");

  // ── 眼下：最新、跟你最有關的一件 ──
  function jwRumorParas(m, id) {
    const l = (m.rumor_layers || []).find((x) => x.id === id);
    if (!l) return [];
    return (String(l.body).match(/<p>[\s\S]*?<\/p>/g) || []).map(jwText).filter((t) => t && !/^（/.test(t));
  }
  const jwStrip = (t) => String(t).replace(/^第\s*\d+\s*[天週][^　]*　/, "");
  function jwEyeItems(m) {
    const out = [];
    const r = S.reports;
    if (S.unseen) {
      const x = r && r.list && r.list.find((y) => y.id === S.unseen);
      if (x) { const d = jwRep(x); out.push({ key: `rep:${x.id}`, seal: "戰報", title: d.foe || d.result || "新的一場", sub: [d.result, d.place].filter(Boolean).join("・"), btn: "看這一場", attrs: `data-act="report" data-id="${esc(x.id)}"` }); } // 待 joy 潤
      else out.push({ key: "rep:new", seal: "戰報", title: "新的一場打完了", sub: "", btn: "看戰報", attrs: 'data-act="jw-open" data-news="reports"' }); // 待 joy 潤
    }
    const mine = jwRumorParas(m, "personal");
    if (mine.length) out.push({ key: `rum:${mine[0].slice(0, 24)}`, seal: "傳聞", title: "有人在說你", sub: jwStrip(mine[0]), btn: "去聽聽", attrs: 'data-act="jw-open" data-news="rumors"' }); // 待 joy 潤
    const top = jwMyTop();
    if (top) out.push({ key: `bd:${top.board.id}:${top.row.rank}`, seal: "榜單", title: `你在${top.board.title}第 ${top.row.rank | 0}`, sub: top.row.text || "", btn: "看榜", attrs: `data-act="jw-open" data-news="boards" data-board="${esc(top.board.id)}"` }); // 待 joy 潤
    const bul = (m.bulletin || [])[0];
    if (bul && shown("board")) {
      const head = jwText((bul.match(/<strong>([\s\S]*?)<\/strong>/) || ["", ""])[1]);
      const body = jwText(bul.replace(/<p><strong>[\s\S]*?<\/strong><\/p>/, ""));
      if (head) out.push({ key: `bul:${head}`, seal: "大事", title: head, sub: body, btn: "看戰況", attrs: 'data-act="jw-open" data-news="reports"' }); // 待 joy 潤
    }
    return out.filter((it) => !(S.jwLater || []).includes(it.key));
  }
  // 你在哪張榜上排得最前（前三名才算；一樣看榜的先後）
  function jwMyTop() {
    const list = (S.boards && S.boards.boards) || [];
    let best = null;
    for (const b of list) {
      const row = (b.rows || []).find((x) => x.you);
      if (row && row.rank <= 3 && (!best || row.rank < best.row.rank)) best = { board: b, row };
    }
    return best;
  }
  function jwEyeHtml(m) {
    const items = jwEyeItems(m);
    if (!items.length) return `<section class="jw-eye idle" aria-label="眼下"><div class="jw-eye-hd"><span class="jw-k">眼下</span><b>${JW_IDLE}</b></div><p class="jw-eye-sub">${JW_IDLE_SUB}</p></section>`;
    const [top, ...rest] = items;
    const more = rest.length ? `<button class="jw-more" data-act="jw-eye-all" aria-expanded="${!!S.jwEyeAll}">${esc(JW_MORE.replace("{n}", rest.length))}<i aria-hidden="true">${S.jwEyeAll ? "▴" : "›"}</i></button>` : "";
    const rows = S.jwEyeAll ? rest.map((it) => `<div class="jw-row"><span class="jw-k">${esc(it.seal)}</span><b>${esc(it.title)}</b><button class="btn small" ${it.attrs}>${esc(it.btn)}</button></div>`).join("") : "";
    return `<section class="jw-eye" aria-label="眼下"><div class="jw-eye-hd"><span class="jw-k">${esc(top.seal)}</span><b>${esc(top.title)}</b>${more}</div>
      <p class="jw-eye-sub">${esc(top.sub || "")}</p>
      <div class="jw-eye-row"><button class="btn jw-eye-go" ${top.attrs}>${esc(top.btn)}</button><button class="btn jw-eye-later" data-act="jw-later" data-key="${esc(top.key)}">${JW_LATER}</button></div>${rows}</section>`;
  }

  // ── 五面牌 ──
  function jwSealCount(m) {
    const block = String(m.chronicle || "").split(/<hr\s*\/?>/)[0];
    if (!/傳國玉璽/.test(block)) return null;
    const items = block.match(/<li>[\s\S]*?<\/li>/g) || [];
    return items.length ? items.filter((li) => !/未現世/.test(li)).length : null;
  }
  function jwPlaqueLine(id, m) {
    if (id === "rumors") {
      const mine = jwRumorParas(m, "personal").length, here = jwRumorParas(m, "local").length;
      return mine ? `${mine} 則跟你有關${here ? `・這一帶 ${here} 則` : ""}` : here ? `這一帶 ${here} 則` : "還沒聽到什麼"; // 待 joy 潤
    }
    if (id === "chronicle") {
      const n = jwSealCount(m);
      const seal = n == null ? "" : n ? `玉璽現世 ${n} 片` : "七片玉璽都沒現世"; // 待 joy 潤
      return [seal, m.lingyan ? "凌煙閣" : ""].filter(Boolean).join("・") || "這一季的大事"; // 待 joy 潤
    }
    if (id === "boards") {
      const top = jwMyTop();
      if (top) return `你在${top.board.title}第 ${top.row.rank | 0}`; // 待 joy 潤
      const list = (S.boards && S.boards.boards) || [];
      return list.length && list.every((b) => !(b.rows || []).length) ? "這一季還沒人上榜" : "善惡名望、武學、擂台"; // 待 joy 潤
    }
    if (id === "journal") {
      const line = m.latest ? jwText((m.latest.match(/<div class="tx-line">([\s\S]*?)<\/div>/) || ["", m.latest])[1]) : "";
      return line ? `剛剛　${line}` : "還沒有紀錄"; // 待 joy 潤
    }
    return "";
  }
  function jwPlaques(m) {
    const fronts = jwFronts(m);
    const quiet = (id) => (/^還沒|七片玉璽都沒/.test(jwPlaqueLine(id, m)) ? " quiet" : "");
    const war = fronts.length
      ? `<button class="jw-pl wide" data-act="jw-open" data-news="reports"><i aria-hidden="true">${JW_GLYPH.reports}</i><b>戰況</b>${dotHtml(dotAt("news", "reports"))}<span class="jw-tugs">${fronts.map((f) => `<span class="jw-tug"><span>${esc(f.name)}</span>${jwBar(f)}<em class="${f.value > 50 && !f.chaos ? "hot" : ""}">${esc(jwFrontSay(f))}</em></span>`).join("")}</span></button>`
      : `<button class="jw-pl" data-act="jw-open" data-news="reports"><i aria-hidden="true">${JW_GLYPH.reports}</i><b>戰況</b><small>戰報與天下大勢</small>${dotHtml(dotAt("news", "reports"))}</button>`; // 待 joy 潤
    const rest = NEWS.slice(1).map((n) => `<button class="jw-pl${quiet(n.id)}" data-act="jw-open" data-news="${esc(n.id)}"><i aria-hidden="true">${JW_GLYPH[n.id] || esc(n.name.slice(0, 1))}</i><b>${esc(n.name)}</b><small>${esc(jwPlaqueLine(n.id, m))}</small>${dotHtml(dotAt("news", n.id))}</button>`).join("");
    return `<nav class="jw-pls" aria-label="見聞">${war}${rest}</nav>`;
  }

  // ── 頁首 ──
  function jwHero(m, mini) {
    const st = typeof jhStatusHtml === "function" ? jhStatusHtml(m) : "";
    const art = `<img class="jw-art" src="${JW_ART}" alt="" decoding="async">`;
    if (mini) return `<section class="jw-hero mini${st ? " st" : ""}">${art}${st}<button class="jw-dim" data-act="jw-close" aria-label="${JW_CLOSE}"></button></section>`;
    return `<section class="jw-hero${st ? " st" : ""}">${art}${st}<div class="jw-pl-hd"><h1>見聞</h1><span class="jw-seal" aria-hidden="true">${JW_SEAL.split("").join("<br>")}</span></div></section>`;
  }
  // 圖下一句：天下形勢最新一篇的頭一句；沒有就是本週的主題
  function jwProse(m) {
    const x = S.xingshi && S.xingshi.essays && S.xingshi.essays[0];
    const wc = m.week_card || {};
    const line = x ? String(x.line || x.essay || "").split(/[。！？]/)[0] : String(wc.theme || "").split(/[。！？]/)[0];
    if (!line) return "";
    const sub = x ? `天下形勢・${x.time || ""}` : wc.when ? `${wc.label || "本週"}・${wc.when}` : ""; // 待 joy 潤
    return `<div class="jw-prose"><p>${esc(line)}。</p>${sub ? `<small>${esc(sub)}</small>` : ""}</div>`;
  }

  // ── 拉起的那一塊 ──
  function jwSheetReports(m, p) {
    const r = S.reports;
    if (S.taleOpen != null || S.reportOpen) return p.old; // 點開一場、戰記：原本那一頁
    let out = "";
    if (!r) out += '<p class="jw-muted">載入中…</p>';
    else if (!r.list.length) out += `<div class="jw-empty"><b>${JW_NO_FIGHT}</b>${JW_NO_FIGHT_SUB}<button class="btn jw-empty-go" data-act="tab" data-tab="jianghu">${JW_GO_FIGHT}</button></div>`;
    else {
      const row = (x) => {
        const d = jwRep(x);
        const title = d.foe ? `${d.foe}` : x.label;
        const sub = [x.big ? d.stamp : d.clock, d.place].filter(Boolean).join("・");
        return `<button class="jw-rep" data-act="report" data-id="${esc(x.id)}"><span class="jw-rs ${d.tone}">${jwSealWord(d)}</span><span class="jw-rep-t"><b>${esc(title)}${dotHtml(S.unseen && x.id === S.unseen)}</b><small>${esc(sub)}</small></span><i aria-hidden="true">›</i></button>`;
      };
      const big = r.list.filter((x) => x.big), rest = r.list.filter((x) => !x.big);
      out += big.map((x) => {
        const d = jwRep(x);
        return `<div class="jw-big"><img src="/static/img/events/fight.webp" alt=""><span class="jw-stamp ${d.tone}">${esc(d.result || jwSealWord(d))}</span><div class="bd"><h4>${esc(d.foe || x.label)}${dotHtml(S.unseen && x.id === S.unseen)}</h4><p>${esc([d.stamp, d.place].filter(Boolean).join("・"))}</p><button class="btn primary" data-act="report" data-id="${esc(x.id)}">看這一場</button></div></div>`; // 待 joy 潤
      }).join("");
      const days = [];
      for (const x of rest) {
        const d = jwRep(x).day;
        if (!days.length || days[days.length - 1].day !== d) days.push({ day: d, rows: [] });
        days[days.length - 1].rows.push(x);
      }
      out += jwDays(days.map((d) => ({ day: d.day, html: d.rows.map(row).join("") })), "rep");
      if (r.list.some((x) => x.id === S.unseen)) S.unseenShown = S.unseen;
    }
    const fronts = jwFronts(m);
    if (fronts.length || (typeof armsLine === "function" && armsLine(m))) {
      out += `<div class="jw-sec"><h3>三路戰況</h3><small>越往黃巾那頭偏越糟</small></div>`; // 待 joy 潤
      out += fronts.map((f) => `<div class="jw-front"><div class="hd"><b>${esc(f.name)}</b>${f.chaos ? '<span class="jw-k">亂局</span>' : ""}<span>${esc(jwFrontSay(f))}</span></div>${jwBar(f)}<div class="ends"><span>黃巾</span><span>官軍</span></div></div>`).join("");
      out += typeof armsLine === "function" ? armsLine(m) : "";
      if (m.trends) out += `${jwMoreBtn("help", "？ 說明與可能的結局")}${jwToggle("help") ? `<div class="jw-rules">${m.trends}</div>` : ""}`; // 待 joy 潤
    } else if (m.trends) out += `<div class="jw-sec"><h3>天下大勢</h3></div><div class="jw-rules">${m.trends}</div>`;
    if (m.bulletin && m.bulletin.length && shown("board")) {
      out += `<div class="jw-sec"><h3>${esc(typeof wkWord === "function" ? wkWord("this", "本週") : "本週")}江湖大事</h3></div>`;
      out += m.bulletin.map((b) => {
        const head = jwText((b.match(/<strong>([\s\S]*?)<\/strong>/) || ["", ""])[1]);
        const body = jwText(b.replace(/<p><strong>[\s\S]*?<\/strong><\/p>/, ""));
        return `<div class="jw-ev big"><span>${head ? `<span class="jw-tag">大事</span><b>${esc(head)}</b>　` : ""}${esc(body)}</span></div>`;
      }).join("");
    }
    const xs = S.xingshi;
    if (m.xingshi && xs && xs.on && xs.essays && xs.essays.length) {
      const [top, ...old] = xs.essays;
      const essay = (e) => `<p class="jw-xs-t">${esc(e.title)}<small>${esc(e.time || "")}</small></p>${typeof xingshiParas === "function" ? xingshiParas(e.essay) : esc(e.essay)}`;
      out += `<div class="jw-sec"><h3>天下形勢</h3><small>${esc(top.time || "")}</small></div><div class="jw-xs${jwToggle("xs") ? " open" : ""}">${jwToggle("xs") ? essay(top) : `<p>${esc(String(top.essay || top.line).replace(/\s+/g, ""))}</p>`}</div>${jwMoreBtn("xs", jwToggle("xs") ? "收起" : "讀全篇")}`; // 待 joy 潤
      if (old.length) out += `${jwMoreBtn("xsold", `往日 ${old.length} 篇`)}${jwToggle("xsold") ? old.map((e) => `<div class="jw-xs open">${essay(e)}</div>`).join("") : ""}`; // 待 joy 潤
    }
    return out;
  }

  // 照日子分段：前 JW_OPEN_DAYS 天攤開，更早的收成一顆「更早 N 天」
  function jwDays(days, key) {
    const head = (d) => `<div class="jw-day">${esc(d.day)}</div>`;
    const open = days.slice(0, JW_OPEN_DAYS).map((d) => head(d) + d.html).join("");
    const rest = days.slice(JW_OPEN_DAYS);
    if (!rest.length) return open;
    return open + jwMoreBtn(`days:${key}`, jwToggle(`days:${key}`) ? "收起" : `更早 ${rest.length} 天`) + (jwToggle(`days:${key}`) ? rest.map((d) => head(d) + d.html).join("") : ""); // 待 joy 潤
  }
  // 「12:00　某某事」這種一段：拆成時刻與字
  function jwEvRow(p) {
    const t = jwText(p);
    const hit = t.match(/^(?:第\s*\d+\s*[天週][^　]*\s)?(\d{1,2}:\d{2})　([\s\S]*)$/);
    return hit ? `<div class="jw-ev"><time>${esc(hit[1])}</time><span>${esc(hit[2])}</span></div>` : `<div class="jw-ev"><time></time><span>${p.replace(/^<p>|<\/p>$/g, "")}</span></div>`;
  }

  function jwSheetRumors(m) {
    const order = [["personal", "跟你有關"], ["local", null], ["faction", null]]; // 待 joy 潤
    const by = Object.fromEntries((m.rumor_layers || []).map((l) => [l.id, l]));
    const secs = order.filter(([id]) => by[id]).map(([id, name]) => {
      const l = by[id];
      const paras = String(l.body).match(/<p>[\s\S]*?<\/p>/g) || [];
      const real = paras.filter((pp) => !/^（/.test(jwText(pp)));
      const body = real.length
        ? real.slice(0, jwToggle(`rum:${id}`) ? real.length : JW_LAYER_OPEN).map(jwEvRow).join("") + (real.length > JW_LAYER_OPEN ? jwMoreBtn(`rum:${id}`, jwToggle(`rum:${id}`) ? "收起" : `再聽 ${real.length - JW_LAYER_OPEN} 則`) : "") // 待 joy 潤
        : `<p class="jw-muted">${esc(jwText(paras[0] || "").replace(/^（|）$/g, "")) || "還沒聽到什麼。"}</p>`;
      return `<div class="jw-sec"><h3>${esc(name || l.title)}</h3></div>${body}`;
    });
    return secs.length ? secs.join("") : `<div class="jw-card">${m.rumors || ""}</div>`;
  }

  function jwSheetChronicle(m, p) {
    if (S.taleOpen != null) return p.old;
    let parts = String(m.chronicle || "").split(/<hr\s*\/?>/);
    let shards = "";
    if (/傳國玉璽/.test(parts[0]) && parts.length > 1) {
      const block = parts.shift();
      const items = (block.match(/<li>[\s\S]*?<\/li>/g) || []).map((li) => jwText(li));
      const lit = items.filter((t) => !/未現世/.test(t)).length;
      shards = `<div class="jw-sec"><h3>傳國玉璽</h3><small>現世 ${lit}／${items.length}</small></div>
        <button class="jw-seal7" data-act="jw-more" data-key="seal" aria-expanded="${jwToggle("seal")}" aria-label="傳國玉璽，現世 ${lit} 片">${items.map((t) => {
          const name = t.split(/[：（(]/)[0].trim();
          return `<span class="jw-shard${/未現世/.test(t) ? "" : " got"}">${esc(name.slice(0, 2))}</span>`;
        }).join("")}</button>${jwToggle("seal") ? `<div class="jw-rules">${block.replace(/<h3>[\s\S]*?<\/h3>/, "")}</div>` : ""}`; // 待 joy 潤
    }
    let now = "", past = "";
    for (const sec of parts.join("<hr />").split(/(?=<h3>)/)) {
      if (!/<h3>/.test(sec) || /本季/.test(sec)) now += sec.replace(/<h3>[\s\S]*?<\/h3>/, "");
      else past += sec;
    }
    const chunks = now.split(/(?=<h4>)/).filter((c) => /<h4>/.test(c));
    const days = chunks.map((c) => ({ day: jwText((c.match(/<h4>([\s\S]*?)<\/h4>/) || ["", ""])[1]), html: (c.replace(/<h4>[\s\S]*?<\/h4>/, "").match(/<p>[\s\S]*?<\/p>/g) || []).map(jwEvRow).join("") }));
    const halls = [typeof lingyanEntryHtml === "function" && m.lingyan ? `<a class="jw-hall" href="/lingyan"><img src="/static/img/events/academy.webp" alt=""><span class="plq">凌煙閣</span><span class="bd"><small>一季一卷，冠絕當世者名垂於此</small></span></a>` : "", // 待 joy 潤
      typeof lunjianHallHtml === "function" ? lunjianHallHtml(m) : ""].filter(Boolean); // 門派論劍的論劍壁：那一包做好了自己給一塊
    const tales = typeof taleIndexHtml === "function" ? taleIndexHtml(m.tales) : "";
    return `${halls.length ? `<div class="jw-halls${halls.length === 1 ? " one" : ""}">${halls.join("")}</div>` : ""}${shards}${tales ? `<div class="jw-tales">${tales}</div>` : ""}`
      + `${days.length ? `<div class="jw-sec"><h3>這一季</h3></div>${jwDays(days, "hist")}` : now ? `<div class="jw-card">${now}</div>` : ""}`
      + `${past ? `${jwMoreBtn("past", jwToggle("past") ? "收起往季" : "往季的江湖史・歷屆擂主")}${jwToggle("past") ? `<div class="jw-card jw-past">${past}</div>` : ""}` : ""}`; // 待 joy 潤
  }

  function jwSheetBoards(m, p) {
    const b = S.boards;
    if (!b) return '<p class="jw-muted">載入中…</p>';
    const list = b.boards || [];
    if (!list.length) return `<div class="jw-empty"><b>還沒有榜單</b></div>`; // 待 joy 潤
    const cur = list.find((x) => x.id === S.board) || list[0];
    const short = (t) => String(t).replace(/^天下/, "").replace(/榜$|譜$/, "");
    const tabs = `<div class="jw-boards">${list.map((x) => `<button class="jw-bd${x.id === cur.id ? " on" : ""}" data-act="board" data-board="${esc(x.id)}" aria-pressed="${x.id === cur.id}">${esc(short(x.title))}</button>`).join("")}</div>`;
    const note = `<p class="jw-note">${esc(cur.note || "")}</p>`;
    if (cur.book) return tabs + note + `<div class="jw-card">${typeof bookRows === "function" ? bookRows(cur.book) : ""}</div>`;
    const open = typeof BOARD_CARDS !== "undefined" && BOARD_CARDS.includes(cur.id);
    const wrap = (r, inner, cls) => (open
      ? `<button class="${cls}" data-act="board-card" data-board="${esc(cur.id)}" data-name="${esc(r.name)}" aria-label="看${esc(r.name)}的${esc(r.text)}">${inner}</button>`
      : `<div class="${cls}">${inner}</div>`);
    const seal = (r) => (r.title && typeof titleSeal === "function" ? ` ${titleSeal(r.title)}` : "");
    const rows = cur.rows || [];
    if (!rows.length) return tabs + `<div class="jw-empty"><b>這一季還沒人上${esc(cur.title)}</b>${esc(cur.note || "")}</div>`; // 待 joy 潤
    const RK = ["一", "二", "三"];
    const top = rows.filter((r) => r.rank <= 3).slice(0, 3);
    const order = top.length === 3 ? [top[1], top[0], top[2]] : top;
    const pod = `<div class="jw-pod n${order.length}">${order.map((r) => wrap(r, `<span class="rk">${RK[(r.rank | 0) - 1] || r.rank}</span><b>${esc(r.name)}</b>${seal(r)}<small>${esc(r.text)}${r.sub ? `<br>${esc(r.sub)}` : ""}</small>`, `jw-p r${r.rank | 0}${r.you ? " you" : ""}`)).join("")}</div>`;
    const more = rows.filter((r) => !top.includes(r)).map((r) => wrap(r, `<i>${r.rank | 0}</i><b>${esc(r.name)}${seal(r)}</b><span>${esc(r.text)}</span>`, `jw-brow${r.you ? " you" : ""}`)).join("");
    const meRow = rows.find((r) => r.you);
    const mine = cur.mine ? `<div class="jw-brow me"><i>你</i><b>${esc((S.main.status || {}).name || "")}</b><span>第 ${cur.mine.rank | 0} 名・${esc(cur.mine.text)}</span></div>`
      : meRow ? `<div class="jw-brow me"><i>你</i><b>${esc(meRow.name)}</b><span>第 ${meRow.rank | 0} 名</span></div>` : ""; // 待 joy 潤
    return tabs + note + pod + more + mine;
  }

  function jwSheetJournal(m) {
    const now = m.latest ? `<div class="jw-just">${m.latest}</div>` : "";
    const rows = typeof newsJournalHtml === "function" ? newsJournalHtml((m.journal || "") + (m.older || "")) : "";
    if (!now && !rows) return `<div class="jw-empty"><b>還沒有紀錄</b>你在江湖上做的每一件事，都會記在這裡。</div>`; // 待 joy 潤
    return `${now}<div class="jw-journal">${rows}</div>`;
  }

  function jwSheetHtml(m, p, id) {
    const n = NEWS.find((x) => x.id === id) || NEWS[0];
    const sub = id === "boards" || id === "chronicle" ? "這一季" : id === "reports" && m.week_card && m.week_card.when ? m.week_card.when : ""; // 待 joy 潤
    const body = id === "reports" ? jwSheetReports(m, p) : id === "rumors" ? jwSheetRumors(m) : id === "chronicle" ? jwSheetChronicle(m, p) : id === "boards" ? jwSheetBoards(m, p) : jwSheetJournal(m);
    return `<section class="jw-sheet sec-${esc(id)}" aria-label="${esc(n.name)}"><div class="jw-grip" aria-hidden="true"></div>
      <div class="jw-sh"><h2>${esc(n.name)}</h2>${dotHtml(dotAt("news", id))}${sub ? `<small class="jw-sh-sub">${esc(sub)}</small>` : ""}<button class="jw-x" data-act="jw-close" aria-label="${JW_CLOSE}">✕</button></div>
      <div class="jw-sb">${body}</div></section>`;
  }

  // 底一次的資料：戰報（新的一場的卡要它）、榜單（牌上「你在某榜第幾」）、天下形勢（圖下那一句）。各要一次，抓到了殼自己會重畫
  function jwLoadOnce(m) {
    S.jwAsked = S.jwAsked || {};
    const ask = (k, fn) => { if (!S.jwAsked[k] && typeof fn === "function") { S.jwAsked[k] = true; setTimeout(() => { Promise.resolve(fn()).catch(() => { S.jwAsked[k] = false; }); }, 0); } };
    if (!S.reports) ask("reports", () => loadReports(null));
    if (!S.boards) ask("boards", () => loadBoards().then(() => { if (S.tab === "news" && !S.jwSec) renderPage(); }));
    if (m.xingshi && !S.xingshi) ask("xingshi", () => (typeof loadXingshi === "function" ? loadXingshi().then(() => { if (S.tab === "news") renderPage(); }) : null));
  }

  function jwPageHtml(m, p) {
    try { return jwPage(m, p); } catch (e) { if (typeof console !== "undefined") console.error(e); return p.seg + p.old; }
  }
  function jwPage(m, p) {
    try { document.documentElement.classList.add("jh2"); } catch (e) { /* 測試裡沒有 document */ }
    // 別處跳過來（S.news 變了、點開一場戰報或戰記）：拉起那一塊；頭一次進來只記下，不拉
    const part = (typeof newsPart === "function" && newsPart(S.news)) || NEWS[0];
    if (S.jwSeen === undefined) S.jwSeen = S.news;
    else if (S.news !== S.jwSeen) { S.jwSec = part.id; S.jwSeen = S.news; }
    if ((S.reportOpen || S.taleOpen != null) && !S.jwSec) S.jwSec = part.id;
    if (S.jwSec) return `<div class="jw-page open">${jwHero(m, true)}${jwSheetHtml(m, p, S.jwSec)}</div>`;
    jwLoadOnce(m);
    return `<div class="jw-page">${jwHero(m, false)}${jwProse(m)}${jwEyeHtml(m)}${jwPlaques(m)}</div>`;
  }

  function jwClose() {
    if (S.unseenShown && S.unseenShown === S.unseen) S.unseen = false; // 戰況那一塊看過了才滅（同換籤）
    S.unseenShown = false;
    S.jwSec = null; S.reportOpen = false; S.taleOpen = null; S.jwMore = {};
    renderPage();
    if (typeof window !== "undefined" && window.scrollTo) window.scrollTo(0, 0);
  }

  async function jianwenClick(act, el, ev) {
    switch (act) {
        case "jw-open": {
          const id = el.dataset.news;
          if (el.dataset.board) S.board = el.dataset.board;
          S.news = id; S.jwSec = id; S.jwSeen = id; S.newsBack = id;
          S.taleOpen = null; S.reportOpen = false; S.jwEyeAll = false;
          if (S.tab !== "news") { await goTab("news"); break; }
          renderPage();
          if (window.scrollTo) window.scrollTo(0, 0);
          if (id === "reports") { await loadReports(null); if (S.main && S.main.xingshi && typeof loadXingshi === "function") { await loadXingshi(); renderPage(); } }
          if (id === "boards") await loadBoards();
          break;
        }
        case "jw-close": jwClose(); break;
        case "jw-later": S.jwLater = [...(S.jwLater || []), el.dataset.key]; S.jwEyeAll = false; renderPage(); break;
        case "jw-eye-all": S.jwEyeAll = !S.jwEyeAll; renderPage(); break;
        case "jw-more": S.jwMore = { ...(S.jwMore || {}), [el.dataset.key]: !jwToggle(el.dataset.key) }; renderPage(); break;
    } // jianwenClick
  } // jianwenClick
  registerClicks(jianwenClick, ["jw-open", "jw-close", "jw-later", "jw-eye-all", "jw-more"]);
