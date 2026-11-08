/* 天下大勢的網頁前端：走法、路上的捷徑與往輿圖那一處（全部拆包第 66 批從 app.js 切出來）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 */
"use strict";

  const MOVE_MODES = [
    { id: "walk", name: "步行" },
    { id: "dash", name: "疾行" },
  ];
  // 照「走法」切換的選項：「前往」與路上的「折返」（路上設計 3.2）。切換鈕緊貼在第一個這種選項上面（A4／W6）
  const followsMode = (id) => id.startsWith("move:") || id.startsWith("road:back");
  const ROAD_TASKS = /^road:(think|ask|gather)$/; // 路上的三樣小事（engine.ROAD_TASKS），排成 2×2（FB-055）
  // 路上的江湖頁多三個捷徑（路上設計 3.3）：是頁面切換，不是引擎的行動
  const ROAD_LINKS = [
    { tab: "map", name: "打開輿圖改去別處" },
    { tab: "practice", name: "去修練" },
    { tab: "craft", name: "去煉製" },
  ];

  // 換走法：帶著新的走法重抓一次江湖畫面，「前往」的時間、體力與按不按得下去才會跟著換
  async function setMoveMode(mode) {
    if (mode === S.moveMode || S.busy) return;
    const before = S.moveMode;
    await busy(async () => {
      S.moveMode = mode;
      try {
        setMain(await api("/api/main"));
      } catch (e) {
        S.moveMode = before; // 沒拿到新走法的選單：留在原本的走法，切換鈕才跟按鈕上的字對得上
        throw e;
      }
      renderTop();
    });
    if (S.tab === "jianghu") renderPage();
  }

  async function travel(mode) {
    await busy(async () => {
      const r = await api("/api/travel", { place: S.mapSel, mode });
      setMain(r.main);
      renderTop();
      if (r.arrived) { S.mapMode = "overview"; S.mapSel = null; S.mapPreview = null; S.mapDrawer = "peek"; } // 出發了：留在輿圖，抽屜回附近那一排（在路上寫往哪裡）
      else toast(`沒能出發：${r.reason}`);
      await loadMap();
      setMapDrawer(S.mapDrawer);
      drawRoute();
      if (r.arrived) mapHome();
    }, WAIT_LINES.move);
  }
  async function travelClick(act, el, ev) {
    switch (act) {
        case "move-mode": await setMoveMode(el.dataset.mode); break;
    } // travelClick
  } // travelClick
  registerClicks(travelClick, ["move-mode"]);
