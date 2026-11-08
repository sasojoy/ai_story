/* 天下大勢的網頁前端：女子與隱線的設定畫面（架構收尾第 105 批從 app.js 切出來）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 */
"use strict";

  // 成人內容（features/heroines；設計稿「三位女子出場」第三節，Joy 2026-11-06）：預設關；打開之前先跳確認卡，按了確認才送出。
  // 這一季的內容沒有女子時伺服器不給 main.heroines，這一格不出現。字句待 joy 潤
  function adultRow() {
    const h = S.main && S.main.heroines;
    if (!h) return "";
    if (S.adultAsk) {
      return `<div class="card adult-ask"><p>成人內容是成年角色之間、彼此情願的親密情節，只有你自己看得到，不會寫進傳聞、江湖史或列傳。</p>
        <p><b>我已年滿十八歲，願意看到成人內容。</b></p>
        <div class="row"><button class="btn small primary" data-act="adult-yes">確認</button><button class="btn small ghost" data-act="adult-no">取消</button></div></div>`;
    }
    return `<label class="toggle"><input type="checkbox" id="adult" ${h.adult ? "checked" : ""}><span><b>成人內容</b><small>預設關；打開要確認年滿十八歲</small></span></label>`;
  }

  async function adultSet(value) {
    await busy(async () => {
      const r = await api("/api/heroines/adult", { value });
      applyMain(r.main);
      const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      if (text) toast(text);
    }, SENT_WAITING);
  }
  async function heroinesClick(act, el, ev) {
    switch (act) {
        case "adult-yes": S.adultAsk = null; await adultSet(true); break;
        case "adult-no": S.adultAsk = null; render(); break;
    } // heroinesClick
  } // heroinesClick
  registerClicks(heroinesClick, ["adult-yes", "adult-no"]);
