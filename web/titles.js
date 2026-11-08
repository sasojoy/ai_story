/* 天下大勢的網頁前端：稱號與官職（features/titles）。名字旁的頭銜印、換戴的小窗、別處共用的印（名帖、玩家卡、決戰、榜單）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。伺服器沒給 main.titles（開關關著）就什麼都不畫。
 */
"use strict";

  // 待 joy 潤：換戴小窗的字
  const TT_HEAD = "頭銜";
  const TT_NOTE = "一次戴一個；名號每週結算一次，有效到下一次結算。";
  const TT_AUTO = "自動（戴最高檔的）";
  const TT_WORN = "戴著";
  const TT_WEAR = "戴上";
  const TT_GOAL = "還沒拿到";
  const TT_NONE = "還沒有頭銜";
  const TT_GRADE = { gold: "金印", zhu: "朱印", ink: "墨印" };

  // 一個印（grade 是 gold／zhu／ink）：名帖、玩家卡、決戰、榜單都照這一個畫
  function titleSeal(t, big) {
    if (!t || !t.name) return "";
    return `<span class="tt-seal tt-${esc(t.grade || "ink")}${big ? " big" : ""}">${esc(t.name)}</span>`;
  }

  // 狀態列名字旁：戴著的名號（官職本來就寫在底下那一行，不重複）；點了開換戴（小窗畫在 app.js render 的疊層那一格）
  function titlesChipHtml() {
    const t = S.main && S.main.titles;
    if (!t) return "";
    const w = t.worn || {};
    const chip = w.name && w.grade !== "ink" ? titleSeal(w) : "";
    return `<button class="tt-chip linkish" data-act="titles-open" aria-label="${TT_HEAD}">${chip || `<span class="tt-empty">${TT_HEAD}</span>`}</button>`;
  }

  function titlesSheetHtml(t) {
    const mine = t.rows.filter((r) => r.mine), goals = t.rows.filter((r) => !r.mine);
    const row = (r) => `<li class="tt-row${r.worn ? " on" : ""}">${titleSeal(r)}<small>${esc(TT_GRADE[r.grade] || "")}・${esc(r.how)}</small>`
      + (r.worn ? `<b class="tt-on">${TT_WORN}</b>` : `<button class="btn ghost" data-act="titles-wear" data-id="${esc(r.id)}">${TT_WEAR}</button>`) + "</li>";
    const auto = `<li class="tt-row${t.pin ? "" : " on"}"><span>${TT_AUTO}</span>${t.pin ? `<button class="btn ghost" data-act="titles-wear" data-id="">${TT_WEAR}</button>` : `<b class="tt-on">${TT_WORN}</b>`}</li>`;
    const goal = goals.length ? `<h4>${TT_GOAL}</h4><ul class="tt-list goals">${goals.map((r) => `<li class="tt-row">${titleSeal(r)}<small>${esc(r.how)}</small></li>`).join("")}</ul>` : "";
    return `<div class="sheet-bg" data-act="titles-close"></div><div class="sheet tt-sheet" role="dialog" aria-label="${TT_HEAD}"><div class="grip"></div>`
      + `<h3>${TT_HEAD}</h3><p class="tt-note">${TT_NOTE}</p>`
      + `<ul class="tt-list">${mine.length ? auto + mine.map(row).join("") : `<li class="tt-row"><span>${TT_NONE}</span></li>`}</ul>${goal}</div>`;
  }

  async function titlesWear(id) {
    await busy(async () => {
      const r = await api("/api/titles/wear", { id });
      applyMain(r.main);
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      if (text) toast(text);
    }, SENT_WAITING);
  }

  async function titlesClick(act, el, ev) {
    switch (act) {
        case "titles-open": if (ev && ev.stopPropagation) ev.stopPropagation(); S.titlesOpen = true; render(); break;
        case "titles-close": S.titlesOpen = false; render(); break;
        case "titles-wear": S.titlesOpen = false; await titlesWear(el.dataset.id || ""); break;
    } // titlesClick
  } // titlesClick
  registerClicks(titlesClick, ["titles-open", "titles-close", "titles-wear"]);
