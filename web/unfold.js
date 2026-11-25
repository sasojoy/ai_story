/* 天下大勢的網頁前端：慢慢長出來（features/unfold；Joy 2026-11-25）。新角色還用不到的分頁先不畫、玩到才長出來。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。伺服器沒給 main.unfold（開關關著、舊角色）就什麼都不做。
 * 藏的那一步在 app.js 的 shown()（main.unfold.hide 裡的鍵一律不畫）；這裡只管剛長出來的那一塊亮紅點、點開那一塊就滅。
 */
"use strict";

  // 剛長出來的鍵在畫面上的哪一處：底部分頁（at），俠客頁的子分頁（at＋sub），俠客頁人像卡上的那一顆連結（at，第三層由那一顆自己畫）
  const UF_PLACES = {
    "tab:map": { at: "map" },
    "tab:news": { at: "news" },
    "hero:attrs": { at: "practice", sub: "attrs" },
    "hero:gear": { at: "practice", sub: "gear" },
    "hero:mates": { at: "practice", sub: "mates" },
    "hero:codex": { at: "practice", sub: "codex" },
    "self:annals": { at: "practice" },
    "self:mingtie": { at: "practice" },
    "self:mail": { at: "practice" },
  };
  const ufFresh = () => ((S.main && S.main.unfold) || {}).fresh || [];
  // 這一塊此刻就在眼前（點開了）：紅點該滅
  function ufHere(key) {
    if (key === "tab:map") return S.tab === "map";
    if (key === "tab:news") return S.tab === "news" && !SELF_NEWS.some((n) => n.id === S.news);
    if (key.startsWith("hero:")) return S.tab === "practice" && S.heroTab === key.slice(5);
    if (key.startsWith("self:")) return S.tab === "news" && S.news === key.slice(5);
    return false;
  }
  let ufSending = false;
  async function ufSeen(keys) { // 看過了：紅點滅（伺服器回 main，殼重畫）
    if (ufSending || !keys.length) return;
    ufSending = true;
    try {
      const r = await api("/api/unfold/seen", { keys });
      if (r && r.main) { setMain(r.main); if (typeof paintDots === "function") paintDots(); }
    } catch (e) { /* 下一次輪詢再說 */ } finally { ufSending = false; }
  }
  // 這一塊亮不亮：剛長出來、還沒點開過。點開的那一刻（畫面正在畫它）就送「看過了」，這一次照樣亮著，回來的 main 才滅
  function unfoldDot(key) {
    if (!ufFresh().includes(key)) return false;
    if (ufHere(key)) setTimeout(() => ufSeen(ufFresh().filter(ufHere)), 0);
    return true;
  }
  if (typeof registerDot === "function") {
    for (const [key, place] of Object.entries(UF_PLACES)) {
      registerDot({ id: `unfold:${key}`, at: place.at, sub: place.sub, on: () => unfoldDot(key) });
    }
  }
