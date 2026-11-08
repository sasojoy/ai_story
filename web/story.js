/* 天下大勢的網頁前端：特殊事件的跳顯框（全部拆包第 66 批從 app.js 切出來）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 */
"use strict";

  // 特殊事件的跳顯框（特殊事件設計稿）：一條線開頭、此事已了・入傳、此事未了，各跳一張蓋在畫面上；有圖放在上面，沒圖只有字。
  // 好幾張時照順序一張一張看（S.storyAt 記看到第幾張），看完最後一張才送 story_seen 清掉。破境卡在它上面（z-index 高一層）
  function storyCard() {
    const cards = (S.main && S.main.story_cards) || [];
    let box = document.getElementById("story-pop");
    if (!cards.length) { S.storyAt = 0; if (box) box.remove(); return; }
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
    const btn = opening ? "且看下去" : after ? "嗯" : retry ? "改日再來" : "收下";
    box.innerHTML = `<div class="story-card story-${esc(c.kind)}${c.failed ? " failed" : ""}${src ? " has-art" : ""}${dun ? " dun" : ""}" role="dialog" aria-label="${esc(c.title)}">
      ${src ? `<img class="story-art" src="${esc(src)}" alt="">` : ""}
      <div class="story-body"><p class="story-head">${tsealHtml(dun ? "悟" : opening || after || retry ? "奇" : "傳")}<b>${head}</b></p>${sub}
      <div class="story-text">${c.text}</div>
      ${cards.length > 1 ? `<p class="muted small story-count">${at + 1}／${cards.length}</p>` : ""}
      <button class="btn primary" data-act="story-ok" data-last="${last ? 1 : 0}">${btn}</button></div></div>`;
  }
  async function storyClick(act, el, ev) {
    switch (act) {
        case "story-ok": // 特殊事件的跳顯框：還有下一張就翻過去，最後一張才請伺服器清掉
          if (el.dataset.last === "1") { S.storyAt = 0; await doMain("story_seen", {}); } else { S.storyAt = (S.storyAt || 0) + 1; storyCard(); }
          break;
    } // storyClick
  } // storyClick
  registerClicks(storyClick, ["story-ok"]);
