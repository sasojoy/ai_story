/* 天下大勢的網頁前端：玉璽碎片的奪璽卡、碎片卡與獨門行動（全部拆包第 66 批從 app.js 切出來）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 */
"use strict";

  // 奪璽卡（玉璽碎片設計 5.10，status.seal_duel）：全服看得到、可以摺疊，排在懸賞卡下面（不擠 375×812 的第一屏）。
  // 雙方、哪一片、第幾回合、氣勢的字（持有者看的是倒過來的，伺服器算好）、最近兩三行、已出招幾手與倒數；代打那一邊的架勢只在對手的卡上（伺服器只給他）。
  // 字待 joy 潤
  // 收起來照那一場記住（S.sealShut.duel，FB-182）；時間那一行包在 .seal-when 裡，輪詢只換它的字（paintSealWhen）
  function sealDuelHtml(d) {
    return `<details class="card seal-duel" data-key="${esc(d.id)}" ${S.sealShut.duel === d.id ? "" : "open"}><summary>奪璽・『${esc(d.shard)}』</summary>
      <p><b>${esc(d.challenger)}</b> 對 懷璽的 <b>${esc(d.holder)}</b>　<span class="seal-when">${esc(sealWhen(d))}</span></p>
      ${d.phase === "active" ? `<p>${esc(d.edge)}</p>` : ""}
      ${d.tell ? `<p class="tell">對手的架勢：${esc(d.tell)}</p>` : ""}
      ${d.turn ? `<p class="turn">輪到你出招。</p>` : ""}
      ${(d.lines || []).map((l) => `<p class="muted">${esc(l)}</p>`).join("")}
      <p class="muted">${esc(d.note)}</p></details>`;
  }

  // 奪璽卡那一行時間：下戰書的倒數、回合的最遲結算（現實秒，伺服器算好的 left）
  function sealWhen(d) {
    const left = `${Math.floor(d.left / 60)} 分 ${d.left % 60} 秒`;
    return d.phase === "muster" ? `${left}後開打` : `第 ${d.round | 0}／${d.rounds | 0} 回合・已出招 ${d.sent | 0}／2，最遲 ${left}後結算`;
  }

  // 奪璽卡那一行時間照 setMain 記下的期限（S.sealDueAt）重寫：輪詢回來江湖頁不必重畫（pageKey 沒變）時、與每秒的 tickDue 都走這裡（FB-182）
  function paintSealWhen() {
    const d = S.main && S.main.status && S.main.status.seal_duel;
    const el = document.querySelector(".seal-duel .seal-when");
    if (!d || !el) return;
    const left = S.sealDueAt == null ? d.left : Math.max(0, Math.ceil((S.sealDueAt - Date.now()) / 1000));
    el.textContent = sealWhen({ ...d, left });
  }

  // tickDue 每秒叫：奪璽卡倒數一秒；到零補問一次（下戰書到期開打、回合逾時結算，換上新的那一回合）
  function tickSeal() {
    paintSealWhen();
    if (!S.sealDuePolled && Date.now() >= S.sealDueAt) { S.sealDuePolled = true; poll(); }
  }

  // 碎片卡收起來照「哪一片、此刻牽不牽動」記住（S.sealShut.card，FB-182）：換了一片、被牽動了重新展開
  const sealCardKey = (s) => `${s.name}|${s.stir || ""}`;

  // 持有者的碎片卡（玉璽碎片設計第十節，status.seal）：哪一片與效果、這一季動過沒、此刻被牽動時那一句、這一季幾個險關的時刻；不寫機率。字待 joy 潤
  function sealHtml(s) {
    const key = sealCardKey(s);
    return `<details class="card seal-card" data-key="${esc(key)}" ${S.sealShut.card === key ? "" : "open"}><summary>傳承・『${esc(s.name)}』</summary>
      ${gearImg("seal", s.art, "seal-pic")}<p>${esc(s.effect_text)}</p><p class="muted">${esc(s.state)}</p>
      ${s.stir ? `<p class="turn">${esc(s.stir)}</p>` : ""}
      ${(s.dates || []).length ? `<p class="muted">這一季的險關：${s.dates.map(esc).join("、")}</p>` : ""}${sealActLine(s.act)}</details>`;
  }

  // ── 玉璽碎片的獨門行動（改版第 2 批，status.seal.act；企劃者 2026-10-21 挑了乙：草圖 docs/superpowers/specs/2026-10-21-玉璽碎片改版-草圖/第2批/）──
  // 入口是修練頁傳承那一列的一顆鈕（heirloomRow）；要指定目標的三種（引將、傳檄、收心）開一層店面樣式的（sealActHtml：招牌寫行動名、右上剩幾次、
  // 一人一列寫此刻在哪與灰掉的原因、每列一顆；散人傳檄先照店面頁籤挑一邊），頒詔、承露按了直接問。問句、說明、原因全是伺服器的字（seal_acts.view）；
  // 這裡只有鈕上的動詞、名單的標題與江湖頁那一行（待 joy 潤）。碎片卡與這一份本來就只給持有者自己，改版關著沒有 act（鈕與那一行都不畫）
  // 第 3 批多鎮地、補缺（目標是區塊、分軍：每一列多 side 與底下那一小行 info；散人挑了哪一軍只列那一軍的）
  const SEAL_VERB = { yinjiang: "引來", chuanxi: "傳檄", shouxin: "收心", zhendi: "鎮住", bujue: "補回" }; // 要指定目標的：鈕上的動詞（待 joy 潤）
  const SEAL_PICK = { yinjiang: "指定一位大勢人物", chuanxi: "指定一條戰線", shouxin: "指定一位人物",
    zhendi: "指定一塊此刻佔著的地", bujue: "指定一塊剛被翻走的地" }; // 名單的標題（待 joy 潤）
  const SEAL_NONE = "這一邊此刻沒有能指定的地方。"; // 散人挑了一邊、那一軍沒有能鎮（補）的地（待 joy 潤）
  // 按不下去、可是有一列列的地可看（FB-645：鎮地、補缺每一塊都灰著，伺服器照樣給 targets）：鈕打得開那一層、各列灰著寫原因
  const sealBrowse = (a) => !!a && !a.ok && a.kind in SEAL_VERB && (a.targets || []).length > 0;
  function sealActNow() {
    const s = S.main && S.main.status && S.main.status.seal;
    return s && s.act ? s.act : null;
  }

  // 江湖頁碎片卡底下那一行提醒（企劃者 2026-10-21：只是字，按了跳到修練頁傳承那一列那一顆）；這一片沒有行動不畫。
  // 這一季整季都用不上（idle：鎮地、補缺在領地爭奪關著的季）寫原因，不寫「還能起用 N 次」（FB-626 那種一句說能用、一句說不能用）
  function sealActLine(a) {
    if (!a) return "";
    const left = a.idle ? a.why : a.left > 0 ? `這一季還能起用 ${a.left | 0} 次` : "這一季的次數用完了";
    return `<p class="seal-act-line"><button class="seal-act-go" data-act="seal-act-go">獨門行動・${esc(a.name)}：${left}</button></p>`;
  }

  // 修練頁傳承那一列（玉璽碎片的抄本，玉璽碎片設計 7.3）：沒有行動的碎片照舊沒有鈕；有的多一顆「X・剩 N 次」，按不下去灰掉、原因寫在這一列底下
  // （.rwhy，手機沒有 title 可看），這一片的行動此刻還在生效的那一句也寫在底下
  function heirloomRow(h, a) {
    const notes = a ? [a.ok ? "" : a.why, a.live].filter(Boolean) : [];
    const look = sealBrowse(a); // FB-645：只能看、按不下去：不是 primary，打得開那一層
    const btn = a ? `<div class="wbtns"><button class="btn small${look ? "" : " primary"}" data-act="seal-act"${a.ok || look ? "" : ` disabled title="${esc(a.why)}"`}>${esc(a.name)}・剩 ${a.left | 0} 次</button></div>` : "";
    return `<div class="wrow heirloom">${gearImg("seal", h.art, "gear-thumb")}<div class="winfo"><b>【${esc(h.name)}】</b><span>傳承・${esc(h.effect_text)}</span>${notes.map((t) => `<small class="rwhy">${esc(t)}</small>`).join("")}</div>${btn}</div>`;
  }

  // 選目標的那一層：店面的框（招牌、收起、右上剩幾次、說明那一句），捲的那一層一人一列。散人還沒挑邊時：不分軍的（傳檄的戰線）每一列都灰著、
  // 分軍的（鎮地、補缺的地，t.side）先不列，上面寫要先挑；挑了只列那一軍的，那一軍一塊都沒有寫 SEAL_NONE
  function sealActHtml(a) {
    const sides = a.sides || [];
    const needSide = sides.length > 0 && !sides.some((s) => s.id === S.sealSide);
    const tabs = sides.length ? `<div class="shop-pages seal-sides" role="group" aria-label="這一次算哪一軍">${sides.map((s) => `
        <button class="shop-page${S.sealSide === s.id ? " on" : ""}" data-act="seal-side" data-side="${esc(s.id)}" aria-pressed="${S.sealSide === s.id}">這一次算${esc(s.name)}</button>`).join("")}</div>` : "";
    const shown = (a.targets || []).filter((t) => !t.side || !sides.length || (!needSide && t.side === S.sealSide));
    const rows = shown.map((t) => {
      const why = t.why || (needSide ? a.side_note : "");
      return `<div class="shop-row seal-row"><div class="winfo"><b>${esc(t.name)}</b>${t.where ? `<span>此刻在${esc(t.where)}</span>` : ""}${t.info ? `<span>${esc(t.info)}</span>` : ""}${t.why ? `<span class="seal-why">${esc(t.why)}</span>` : ""}</div>
        <div class="wbtns"><button class="btn small${why ? "" : " primary"}" data-act="seal-pick" data-id="${esc(t.id)}"${why ? ` disabled title="${esc(why)}"` : ""}>${SEAL_VERB[a.kind] || "起用"}</button></div></div>`;
    }).join("");
    const none = a.ok && !rows && sides.length && !needSide ? `<p class="shop-cap">${SEAL_NONE}</p>` : "";
    return `<div class="shop-layer shop-seal" role="dialog" aria-label="${esc(a.name)}">
      <header class="shop-bar"><button class="shop-back" data-act="seal-act-close">‹ 收起</button><span class="shop-sign">${esc(a.name)}</span><span class="shop-silver">剩 ${a.left | 0} 次</span></header>
      <p class="shop-line">${esc(a.text)}</p>
      <div class="shop-body"><div class="shop-col">${tabs}${needSide ? `<p class="shop-warn">${esc(a.side_note)}</p>` : ""}
        <p class="shop-cap">${esc(a.rule)}</p>${a.live ? `<p class="shop-cap seal-live">${esc(a.live)}</p>` : ""}${a.ok ? "" : `<p class="shop-warn">${esc(a.why)}</p>`}
        ${rows ? `<h4 class="seal-h">${SEAL_PICK[a.kind] || ""}</h4>${rows}` : ""}${none}</div></div>
    </div>`;
  }

  // 問句（伺服器的 confirm，{target} 換目標的名字、{side} 換挑的那一軍），按「起用」才送；送出時那一層收起，結果照一般動作寫在提示裡
  function sealAsk(a, target) {
    const side = (a.sides || []).find((s) => s.id === S.sealSide);
    const text = a.confirm.replace("{target}", target ? target.name : "").replace("{side}", side ? side.name : "");
    const body = { target: target ? target.id : "", side: side ? side.id : "" };
    ask(text, "起用", async () => { S.sealAct = false; S.sealSide = null; await keepScroll(() => doMain("seal_use", body)); });
  }

  // 開、收那一層與送出都整個重畫：底下的修練頁停在原處（拇指底下還是傳承那一列）
  async function keepScroll(draw) {
    const y = window.scrollY;
    await draw();
    window.scrollTo(0, y);
  }

  // 輪詢（refreshPage 最前面叫）：那一層開著而且資料變了，只換那一層（捲到哪裡留著）；碎片沒了、這一片沒有行動了就收起
  function sealActPolled(old) {
    if (!S.sealAct) return;
    const a = sealActNow();
    const layer = document.querySelector(".shop-seal");
    if (!a || !layer) { S.sealAct = false; S.sealSide = null; layer?.remove(); return; }
    const was = old && old.status && old.status.seal ? old.status.seal.act : null;
    if (JSON.stringify(was) !== JSON.stringify(a)) redrawSealAct(a);
  }

  // 只換那一層（挑了一邊、輪詢的資料變了）：捲到哪裡留著，不重畫底下的頁面
  function redrawSealAct(a) {
    const layer = document.querySelector(".shop-seal");
    if (!layer) return;
    const top = layer.querySelector(".shop-body")?.scrollTop || 0;
    layer.outerHTML = sealActHtml(a);
    const body = document.querySelector(".shop-seal .shop-body");
    if (body) body.scrollTop = top;
  }
  async function sealClick(act, el, ev) {
    switch (act) {
        // 玉璽碎片的獨門行動（改版第 2 批）：傳承那一列的鈕——要指定目標的開那一層，頒詔、承露直接問；那一層裡挑一邊、挑一個人（先問一次）、收起；
        // 江湖頁碎片卡那一行跳到修練頁那一顆
        case "seal-act": {
          const a = sealActNow();
          if (!a || (!a.ok && !sealBrowse(a))) { if (a && a.why) toast(a.why); break; }
          if (a.kind in SEAL_VERB) { S.sealAct = true; S.sealSide = null; await keepScroll(render); } else sealAsk(a, null);
          break;
        }
        case "seal-side": { S.sealSide = el.dataset.side; const a = sealActNow(); if (a) redrawSealAct(a); break; }
        case "seal-pick": { // 灰著的那一列不問（FB-645 起整顆按不下去時也列得出灰的）
          const a = sealActNow(); const t = a && (a.targets || []).find((r) => r.id === el.dataset.id);
          if (t && a.ok && !t.why) sealAsk(a, t);
          break;
        }
        case "seal-act-close": S.sealAct = false; S.sealSide = null; await keepScroll(render); break;
        case "seal-act-go": await goTab("practice"); document.querySelector(".gear .wrow.heirloom")?.scrollIntoView({ block: "center" }); break;
    } // sealClick
  } // sealClick
  registerClicks(sealClick, ["seal-act", "seal-side", "seal-pick", "seal-act-close", "seal-act-go"]);
