/* 天下大勢的網頁前端：特殊事件的跳顯框（全部拆包第 66 批從 app.js 切出來）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 */
"use strict";

  // 特殊事件的跳顯框（特殊事件設計稿）：一條線開頭、此事已了・入傳、此事未了，各跳一張蓋在畫面上；有圖放在上面，沒圖只有字。
  // 好幾張時照順序一張一張看（S.storyAt 記看到第幾張），看完最後一張才送 story_seen 清掉。破境卡在它上面（z-index 高一層）
  // 一條線的事件剛選完（main.story_now）、又有卡等著跳（最後一幕的此事已了）：先讓玩家在「剛剛」讀完那一段後續，按「看結局」才跳（Joy 2026-11-13）
  const storyHeld = (m) => !!(m && m.story_now && m.now && (m.story_cards || []).length && S.storyRead !== m.now);
  const STORY_GO = (c) => (c.kind === "end" || c.kind === "unfinished" ? "看結局" : "往下看"); // 待 joy 潤
  function storyNowTail(m) {
    return storyHeld(m) ? `<button class="btn primary now-story-go" data-act="story-read">${STORY_GO(m.story_cards[0])} ›</button>` : "";
  }
  // 結局卡等著的時候，「剛剛」裡跟結局卡同一段的那一行先不放（不然讀完後續、按看結局又讀一次同一段）；卡看過了就照全文放回來
  const STORY_PLAIN = (h) => String(h || "").replace(/<[^>]*>/g, "").replace(/&[a-z#0-9]+;/gi, "").replace(/\s+/g, "");
  function storyNowText(m, html) {
    if (!storyHeld(m)) return html;
    const key = STORY_PLAIN(m.story_cards[0].text).slice(0, 16);
    return key ? html.replace(/<div class="tx-line[^"]*">([\s\S]*?)<\/div>/g, (all, inner) => (STORY_PLAIN(inner).startsWith(key) ? "" : all)) : html;
  }
  function storyCard() {
    // 剛選完的那一則捲到眼前（江湖頁上面還有本週卡，攤開的後續常在第一屏底下）：同一則只捲一次
    const now = document.querySelector("#page .now");
    if (now && S.main && S.main.story_now && S.main.now && S.storyShown !== S.main.now && S.tab === "jianghu" && now.getBoundingClientRect) {
      S.storyShown = S.main.now;
      const top = document.getElementById("top");
      const y = now.getBoundingClientRect().top + window.scrollY - (top ? top.getBoundingClientRect().height : 0) - 12; // 頂上的狀態列黏著，讓開它
      if (y > window.scrollY + 40) window.scrollTo({ top: y, behavior: "smooth" }); // 已經在眼前就不動
    }
    const cards = (S.main && S.main.story_cards) || [];
    let box = document.getElementById("story-pop");
    if (!cards.length || storyHeld(S.main)) { if (!cards.length) S.storyAt = 0; if (box) box.remove(); return; }
    const at = Math.min(S.storyAt || 0, cards.length - 1), c = cards[at];
    if (!box) { box = document.createElement("div"); box.id = "story-pop"; box.className = "story-wrap"; document.body.appendChild(box); }
    const opening = c.kind === "start" || c.kind === "stage"; // 段落卡（StoryStage.card，例：頓悟心魔那一關之前）跟開頭同一個寫法
    const after = c.kind === "after"; // 餘波（長篇奇事）：收了之後過幾天，走到某地聽到的那一段
    const retry = c.kind === "retry"; // 打輸了、還能再打（頓悟的心魔未破，Joy 2026-10-28）：標題就是那張卡自己的（「心魔未破」）
    const head = retry ? esc(c.title) : opening ? `${esc(c.sort)}・${esc(c.title)}`
      : after ? `後來・《${esc(c.title)}》` : c.kind === "end" ? `此事已了・入傳` : `此事未了・入傳`;
    const sub = opening || retry || (after && !c.ending) ? "" : after ? `<p class="story-sub">${esc(c.ending)}</p>` : `<p class="story-sub">《${esc(c.title)}》${c.ending ? `・${esc(c.ending)}` : ""}</p>`;
    const dun = c.sort === "頓悟"; // 特殊頓悟（Joy 2026-10-26「頓悟那邊也要有圖」）：圖照樣放上面，墨底與「悟」章分得出；沒圖就是墨底純字
    const src = c.src;
    const last = at >= cards.length - 1;
    // 這張卡後面接一場要打的（頓悟的心魔）：鈕就寫那一步，按了直接去打；旁邊一顆小的「先不打」（Joy 2026-11-14「要在事件發生時就讓玩家知道要打心魔」）
    const go = last0(cards, at) && c.go && ((S.main && S.main.options) || []).some((o) => o.id === c.go.id && o.enabled) ? c.go : null;
    const btn = go ? go.label : opening ? "且看下去" : after ? "嗯" : retry ? "改日再來" : "收下";
    box.innerHTML = `<div class="story-card story-${esc(c.kind)}${c.failed ? " failed" : ""}${src ? " has-art" : ""}${dun ? " dun" : ""}" role="dialog" aria-label="${esc(c.title)}">
      ${src ? `<img class="story-art" src="${esc(src)}" alt="">` : ""}
      <div class="story-body"><p class="story-head">${tsealHtml(dun ? "悟" : opening || after || retry ? "奇" : "傳")}<b>${head}</b></p>${sub}
      <div class="story-text">${c.text}</div>
      ${cards.length > 1 ? `<p class="muted small story-count">${at + 1}／${cards.length}</p>` : ""}
      <button class="btn primary" data-act="story-ok" data-last="${last ? 1 : 0}"${go ? ` data-go="${esc(go.id)}"` : ""}>${esc(btn)}</button>
      ${go ? `<button class="btn ghost story-later" data-act="story-ok" data-last="1">${STORY_LATER}</button>` : ""}</div></div>`;
  }
  const STORY_LATER = "先不打"; // 待 joy 潤
  const last0 = (cards, at) => at >= cards.length - 1;
  async function storyClick(act, el, ev) {
    switch (act) {
        case "story-ok": // 特殊事件的跳顯框：還有下一張就翻過去，最後一張才請伺服器清掉
          if (el.dataset.last === "1") {
            const go = el.dataset.go;
            S.storyAt = 0;
            await doMain("story_seen", {});
            if (go && ((S.main && S.main.options) || []).some((o) => o.id === go && o.enabled)) await choose(el, go);
          } else { S.storyAt = (S.storyAt || 0) + 1; storyCard(); }
          break;
        case "story-read": // 「剛剛」底下的「看結局」：後續讀完了，結局卡跳出來
          S.storyRead = S.main && S.main.now;
          el.remove();
          storyCard();
          break;
    } // storyClick
  } // storyClick
  registerClicks(storyClick, ["story-ok", "story-read"]);

  // 未了之事（story:；main.js 的 hereRowHtml 叫）不擠進圓章：此地可為上面一件一行，章回主線標「主線」、別的標「奇事」，寫線名與這一步（Joy 2026-11-11「這明明算是主線任務
  // 卻如此不起眼」）。做得了的按了就去做；時機未到的灰著，點了跳出還要等什麼
  const QUEST_TAG = (id) => (/^story:ch_/.test(id) ? "主線" : "奇事"); // 待 joy 潤
  function questRowsHtml(list) {
    const quests = list.filter((o) => /^story:/.test(o.id)).sort((a, b) => (b.enabled ? 1 : 0) - (a.enabled ? 1 : 0));
    return quests.map((o) => {
      const m = /^(.*?)（(.*)）$/.exec(o.label), title = m ? m[1] : o.label, detail = m ? m[2] : ""; // 同 main.js 的 optParts
      const step = detail.replace(/^未了之事[：:]?/, "");
      const attrs = o.enabled ? `data-act="choose" data-id="${esc(o.id)}"` : `data-act="opt-why" data-id="${esc(o.id)}" data-why="${esc(`${step || title}。`)}" aria-disabled="true"`;
      const main = QUEST_TAG(o.id) === "主線";
      return `<button class="quest-row${main ? " main" : ""}${o.enabled ? "" : " off"}" ${attrs}><span class="qr-tag">${QUEST_TAG(o.id)}</span>`
        + `<span class="qr-t"><b>${esc(title)}</b>${step ? `<small>${esc(step)}</small>` : ""}</span><span class="qr-go" aria-hidden="true">${o.enabled ? "›" : "…"}</span></button>`;
    }).join("");
  }
