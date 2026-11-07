/* 天下大勢的網頁前端：找素材的分支（探索那一格展開的輪）（全部拆包第 67 批從 main.js 切出來）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 */
"use strict";

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
  async function exploreClick(act, el, ev) {
    switch (act) {
        case "gather-wheel": // 找素材分支（第 32 項）：「找素材」點了在它底下攤開（再點一次收起）；輸入框跟著收
          S.gatherOpen = !S.gatherOpen;
          S.gatherSaying = false;
          renderPage();
          if (S.gatherOpen) revealMoveCard();
          break;
    } // exploreClick
  } // exploreClick
  registerClicks(exploreClick, ["gather-wheel"]);
