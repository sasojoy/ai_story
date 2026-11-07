/* 天下大勢的網頁前端：擂台（功能包 tianxia/features/bout/，開發規範手冊 3.7、G9）。
 *
 * 擂台（arenaHtml）：台下、擂台榜、打到一半、收場卡的畫法；動畫與場景在 arena_anim.js、arena_scene.js。
 * 跟 mall.js 一樣是一般的 <script>：頂層的名字同在一個全域裡；/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 * 全部拆包第 65 批從 app.js 逐行切出來（計畫 docs/superpowers/plans/2026-11-06-網頁殼化-第65批.md）。點擊用 registerClicks 登記在這支檔；店面的框（shopHtml、renderShop）照舊在 app.js（殼）。
 */
"use strict";

  // ── 擂台（擂台賽設計；Joy 2026-10-14「擂台應該要是獨立的一頁，你這樣太混雜了」）：跟三間店同一層。打到一半整頁是這一場（arenaFightHtml），
  // 不然底下兩頁：台下（你的分身與積分、守擂的人一人一張）、擂台榜；剛打完有收場卡。鈕都送現在的選項 id。字待 joy 潤 ──
  const ARENA_TABS = [["floor", "台下"], ["board", "擂台榜"]];
  function arenaHtml(shop) {
    // 捲的那一層裡面同三間店先包一層 .shop-col（FB-306：電腦上照遊戲那一欄排，台下那一格原本拉滿整個螢幕；手機上 .shop-col 沒有樣式）
    if (shop.fight) return `<div class="shop-body arena-body"><div class="shop-col">${arenaFightHtml(shop.fight)}</div></div>`;
    const tab = S.arenaTab === "board" ? "board" : "floor";
    const result = shop.result && shop.result.id !== S.arenaSeen ? arenaResultHtml(shop.result) : "";
    return `<div class="shop-body arena-body"><div class="shop-col">${tab === "board" ? arenaBoardHtml(shop) : arenaFloorHtml(shop)}</div></div>
      <nav class="shop-tabs">${ARENA_TABS.map(([k, name]) => `<button class="shop-tab${tab === k ? " on" : ""}" data-act="arena-tab" data-tab="${k}">${name}</button>`).join("")}</nav>
      ${result}`;
  }

  // 台下：上面是你自己那一張（名次、稱號、戰績、守擂用的武學、報名／更新分身），底下挑得到的人（排在你前面三名內）一人一張，挑不了的灰掉寫原因
  function arenaFloorHtml(shop) {
    const me = shop.me;
    const stand = me.joined
      ? `<div class="ring-score"><span>第</span><b>${me.rank | 0}</b><span>名</span></div>
         <div class="ring-meta">${me.title ? `<span class="ring-place">${esc(me.title)}</span>` : ""}<span>${esc(me.record)}</span>
           ${me.arts.length ? `<span>守擂：${esc(me.arts.join("、"))}</span>` : ""}</div>`
      : `<p class="ring-new">${esc(me.note)}</p>`;
    const join = `<button class="btn${me.joined ? "" : " primary"} ring-join" data-act="choose" data-id="${esc(me.join.id)}" ${me.join.enabled ? "" : "disabled"}><b>${esc(me.join.label)}</b>${me.join.why ? `<small>${esc(me.join.why)}</small>` : ""}</button>`;
    const mine = `<section class="ring-me">${stand}${join}${me.joined ? `<p class="ring-note">${esc(me.note)}</p>` : ""}</section>`;
    const card = (f) => `<article class="ring-foe${f.enabled ? "" : " dim"}">
        <div class="info"><div class="who"><span class="rt">第 ${f.rank | 0} 名</span><b>${esc(f.name)}</b>${f.title ? `<span class="ttl">${esc(f.title)}</span>` : ""}</div>
        <p>${esc(f.record)}・${esc(f.strength)}</p>${f.arts.length ? `<p class="arts">${esc(f.arts.join("、"))}</p>` : ""}${f.famed ? `<p class="arts famed">${esc(f.famed)}</p>` : ""}</div>
        <button class="btn${f.enabled ? " primary" : ""} small" data-act="choose" data-id="${esc(f.id)}" ${f.enabled ? "" : `disabled title="${esc(f.why || "")}"`}>${f.enabled ? "<b>挑戰</b>" : f.short ? `<b>${esc(f.short[0])}</b>${f.short[1] ? `<small>${esc(f.short[1])}</small>` : ""}` : esc(f.why)}</button>
      </article>`;
    if (!me.joined) return mine;
    const foes = shop.foes.length ? `<div class="ring-foes">${shop.foes.map(card).join("")}</div>` : `<p class="shop-empty">${esc(shop.nobody)}</p>`;
    return `${mine}<h4 class="ring-h">挑得到的人</h4>${foes}`;
  }

  // 擂台榜：照名次排，前三名有名次色、稱號一個小牌子，你自己那一列標出來；底下一行每天的俸
  function arenaBoardHtml(shop) {
    if (!shop.board.length) return `<p class="shop-empty">${esc(shop.board_empty)}</p>`;
    const row = (r) => `<li class="${r.me ? "me" : ""}${r.rank <= 3 ? ` top${r.rank | 0}` : ""}"><span class="rk">${r.rank | 0}</span>
        <div class="nm"><b>${esc(r.name)}</b><span class="wl">${r.wins | 0} 勝 ${r.losses | 0} 負${r.draws ? ` ${r.draws | 0} 和` : ""}${r.streak >= 2 ? `・連勝 ${r.streak | 0}` : ""}</span></div>
        ${r.title ? `<span class="ttl">${esc(r.title)}</span>` : ""}</li>`;
    return `<ol class="ring-board">${shop.board.map(row).join("")}</ol>${shop.wages ? `<p class="ring-note">${esc(shop.wages)}</p>` : ""}`;
  }

  // 打到一半：兩邊的氣血、中間一條氣勢（越往右越是你佔上風）、他的架勢、三招、放手一搏、這一場打過的回合
  // 擂台的場邊事件（tianxia/arena_crowd.py）：那一行以〔場邊〕開頭，另一種底色；剛發生的那一回合在雙方氣血底下多放一行
  const CROWD_MARK = "〔場邊〕";
  function ringLine(l) { return `<li${l.startsWith(CROWD_MARK) ? ' class="crowd"' : ""}>${esc(l)}</li>`; }

  function arenaFightHtml(f) {
    const pct = (a) => Math.max(0, Math.min(100, a.cap ? (a.hp / a.cap) * 100 : 0));
    const side = (a, cls) => `<div class="ring-side ${cls}"><b>${esc(a.name)}</b><div class="hp"><i style="width:${pct(a).toFixed(1)}%"></i></div><small>${a.hp | 0}／${a.cap | 0}</small></div>`;
    const moves = f.moves.map((m) => `<button class="btn ring-move"${m.enabled === false ? " disabled" : ` data-act="choose" data-id="${esc(m.id)}"`}><b>${esc(m.move)}</b><small>${esc(m.label.replace(m.move, ""))}</small></button>`).join("");
    const log = f.log.length ? `<ol class="ring-log">${f.log.slice().reverse().map(ringLine).join("")}</ol>` : "";
    const last = f.log.length ? f.log[f.log.length - 1] : "";
    const crowd = last.startsWith(CROWD_MARK) ? `<p class="ring-crowd">${esc(last)}</p>` : "";
    return `<canvas id="ring-stage" class="ring-stage" width="720" height="320" aria-hidden="true"></canvas>
      <div class="ring-round">第 ${f.round | 0}／${f.rounds | 0} 回合</div>
      <div class="ring-sides">${side(f.me, "mine")}<span class="vs">對</span>${side(f.foe_hp, "theirs")}</div>
      ${crowd}
      <div class="ring-edge"><span>${esc(f.edge_words)}</span><div class="bar"><i style="left:${Math.max(0, Math.min(100, f.edge | 0))}%"></i></div></div>
      ${f.arts.length ? `<p class="ring-arts">他守擂用的是${esc(f.arts.join("、"))}。</p>` : ""}
      ${f.status ? `<p class="ring-status">${esc(f.status)}</p>` : ""}
      <p class="ring-tell">${esc(f.tell)}<small>（${esc(f.tell_note)}）</small></p>
      <p class="ring-howto">${esc(f.howto)}</p>
      <div class="ring-moves">${moves}</div>
      ${f.gamble.locked ? `<p class="free-note">${esc(f.gamble.locked)}</p>` : `<form class="free ring-free" id="arena-free" data-op="${esc(f.gamble.op)}"><input class="input" name="text" maxlength="20" placeholder="${esc(f.gamble.prompt)}"><button class="btn primary small" type="submit">送出</button></form>
      <p class="free-note">${esc(f.gamble.note)}</p>`}
      ${log}`;
  }

  // 剛打完的那一場：一張卡蓋在台下上面（勝負大字、每回合一行、積分與名望），按「回台下」收起
  function arenaResultHtml(r) {
    const won = r.tier === "大勝" || r.tier === "險勝";
    const cls = won ? "win" : r.tier === "僵持" ? "draw" : "lose";
    return `<div class="board-sheet ring-sheet"><article class="paper ring-result ${cls}"><i class="stamp">${esc(r.tier)}</i>
        <canvas id="ring-stage" class="ring-stage" width="720" height="320" aria-hidden="true"></canvas>
        <h4>對${esc(r.foe)}的分身</h4><ol class="ring-log">${r.lines.map(ringLine).join("")}</ol>
        ${r.changes.length ? `<p class="reward">${esc(r.changes.join("・"))}</p>` : ""}
        <div class="btns one"><button class="btn primary" data-act="arena-seen" data-id="${r.id | 0}">回台下</button></div></article></div>`;
  }
  async function boutClick(act, el, ev) {
    switch (act) {
        case "arena-tab": S.arenaTab = el.dataset.tab; renderShop(false); break; // 擂台：台下／擂台榜
        case "arena-seen": S.arenaSeen = Number(el.dataset.id); renderShop(); break; // 收起收場卡
    } // boutClick
  } // boutClick
  registerClicks(boutClick, ["arena-tab", "arena-seen"]);
