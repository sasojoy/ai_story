/* 天下大勢的網頁前端：託付的勸降那一句（全部拆包第 66 批從 app.js 切出來）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 */
"use strict";

  // 託付的勸降（減法季批 6，FB-829）：送出後要等模型評這一句（同隨口應對），按鈕先寫「斟酌中……」；
  // 被擋下來的那一句（字數不對、人不在那裡）在江湖紀錄裡沒有，用提示泡泡講，輸入框留著；送成了（勸成、打起來、對方不置可否）收起
  const PERSUADE_WAIT = "斟酌中……"; // 待 joy 潤
  async function persuadeSay(form, text) {
    await busy(async () => {
      form.querySelectorAll("input, button").forEach((el) => { el.disabled = true; });
      const submitBtn = form.querySelector("[type=submit]");
      submitBtn.textContent = PERSUADE_WAIT;
      const stop = watchQueue(submitBtn, PERSUADE_WAIT);
      try {
        const r = await api("/api/do/persuade_text", { id: form.dataset.id, text });
        const said = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
        const done = said.startsWith("你：") || !((r.main && r.main.options) || []).some((o) => o.id === S.persuading);
        if (done) S.persuading = false;
        applyMain(r.main);
        if (said && !done) toast(said);
        if (done) window.scrollTo({ top: 0, behavior: "smooth" });
      } finally {
        stop();
        form.querySelectorAll("input, button").forEach((el) => { el.disabled = false; });
        submitBtn.textContent = PERSUADE_GO;
      }
    });
  }
