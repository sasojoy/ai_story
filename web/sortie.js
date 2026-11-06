/* 天下大勢的網頁前端：出陣約戰的封招與前往（全部拆包第 66 批從 app.js 切出來）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 */
"use strict";

  // ── 出陣約戰（丙；畫的部分在 main.js 的 sortiePanelHtml）──
  // 封三招挑一招（再點同一招取消）：只換那一張卡（#sortie-panel 的 outerHTML），不重畫整頁（「剛剛」的浮現動畫不重播）
  function sortieMove(round, move) {
    const pick = (S.sortiePick || []).slice(0, SX_ROUNDS.length);
    pick[round] = pick[round] === move ? null : move;
    S.sortiePick = pick;
    const panel = document.getElementById("sortie-panel");
    if (panel) panel.outerHTML = sortiePanelHtml(S.main);
    else renderPage();
  }
  // 封好三招的那一顆：應戰那一張送 sortie_answer（{id, moves}），出陣送 sortie_go（{moves}）；三招沒挑滿不送（鈕本來就灰著）
  async function sortieSend() {
    const moves = (S.sortiePick || []).slice(0, SX_ROUNDS.length);
    if (moves.length < SX_ROUNDS.length || !moves.every(Boolean)) return;
    const d = sortieAnswering(S.main);
    if (d) await sortieDo("sortie_answer", { id: d.id, moves });
    else if (sortieCardOn(S.main) && !S.main.sortie_card.why_not) await sortieDo("sortie_go", { moves });
  }
  // 貼、應、同去：伺服器回來之後卡收起、挑的招清掉，「剛剛」照伺服器寫的那一則（被擋下來是一句提示），捲回最上面看結果（同 choose）
  async function sortieDo(op, body) {
    await busy(async () => {
      const r = await api(`/api/do/${op}`, body);
      S.wheelSel = null;
      S.sortieAnswer = null;
      S.sortiePick = [];
      applyMain(r.main);
      window.scrollTo({ top: 0, behavior: "smooth" });
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      if (text) toast(text);
    });
  }
  // 別區那一張的「前往 N 分」：照現有的移動走（同新手目標的「去做」）——移動清單上有往那一塊的路就展開移動、讓那一條發光，
  // 沒有（不相鄰）就開輿圖那一處的卡（步行、疾行的鈕在卡上，同江湖頁小地圖點一處）
  function sortieTravel(loc) {
    const id = `move:${loc}`, hit = (x) => x === id || x.startsWith(`${id}:`); // 疾行的 id 後面多接走法
    if ((S.main.options || []).some((o) => hit(o.id))) {
      S.sortieAnswer = null;
      S.wheelSel = "move";
      S.glowRoute = id; // 往那一處的那一條發光：記在狀態裡，重畫、摺疊 toggle 都保得住（FB-9001）
      renderPage();
      revealMoveCard();
      return;
    }
    mapGoto(loc);
    return goTab("map");
  }
