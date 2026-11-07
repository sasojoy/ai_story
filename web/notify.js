/* 天下大勢的網頁前端：手機通知的畫面（設定頁那一塊、怎麼收到通知那一頁、信底下問一次）與訂閱（全部拆包第 66 批從 app.js 切出來）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 */
"use strict";

  // ── 手機通知（減法季批 9：回來的理由）──
  // 設定頁一顆「手機通知」，預設關；第一次來信時在信的小卡底下問一次（pushAskHtml，問過記在這個瀏覽器）。
  // 開了：向瀏覽器要通知權限 → 註冊 /sw.js → 拿伺服器的公鑰（/api/push）訂閱 → 交給 /api/push/subscribe（伺服器當場送一則「開了」）。
  // 伺服器關著（main.web_push 是 false）什麼都不畫。iPhone 要先「加入主畫面」、從主畫面打開才收得到（iOS 16.4 起）。字待 joy 潤
  const PUSH_ASKED_KEY = "tianxia-push-asked";
  const PUSH_KINDS = "來信、約戰、決戰集結、被截殺、被〈天下形勢〉提到";
  function pushSupported() {
    return !!(S.main && S.main.web_push) && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
  }
  function pushNeedsHome() { // iPhone、iPad 的 Safari：沒從主畫面打開就沒有 PushManager
    return !!(S.main && S.main.web_push) && /iP(hone|ad|od)/.test(navigator.userAgent || "")
      && !(navigator.standalone || (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches));
  }
  function pushAsked() { try { return localStorage.getItem(PUSH_ASKED_KEY) === "1"; } catch (e) { return true; } }
  function pushMarkAsked() { try { localStorage.setItem(PUSH_ASKED_KEY, "1"); } catch (e) { /* 存不了就只在這一頁不再問 */ } }
  function pushKey(text) { // base64url → Uint8Array（applicationServerKey）
    const raw = atob(text.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((text.length + 3) % 4));
    return Uint8Array.from(raw, (c) => c.charCodeAt(0));
  }
  // service worker 註冊好、啟用了才訂得了（第一次註冊時 register 回來的那一份還在安裝，直接 subscribe 會被拒：iPhone 上就是勾不起來）
  async function pushReg() {
    await navigator.serviceWorker.register("/sw.js");
    return navigator.serviceWorker.ready;
  }
  // 五種通知各一個開關（設定頁，預設全開；存在伺服器、這個帳號每一台一樣，/api/push 的 kinds）。字待 joy 潤
  const PUSH_KIND_NAMES = [["letter", "來信"], ["duel", "約戰"], ["rally", "決戰集結"], ["raid", "被截殺"], ["xingshi", "被〈天下形勢〉提到"]];
  const PUSH_TEST_OK = "送出去了：這一台應該馬上跳一則「通知設定好了」。沒跳的話看看手機有沒有開勿擾、專注模式。";
  function pushErrorText(e) { // 開不了的原因照實寫給玩家看（以前有錯就靜靜地沒勾起來）
    const name = (e && e.name) || "";
    if (name === "NotAllowedError") return pushDevice() === "ios"
      ? "iPhone 沒有給通知的權限：到 iPhone 的「設定」→「通知」→「天下大勢」打開「允許通知」，再回來勾一次。"
      : "瀏覽器沒有給通知的權限：到瀏覽器的網站設定裡把通知改成允許，再回來勾一次。";
    if (name === "AbortError" || name === "InvalidStateError") return `推送服務沒接通（${(e && e.message) || name}）：等一下再勾一次。`;
    return `開不了通知：${(e && e.message) || name || "不明的錯"}`;
  }
  function pushPaint() { // 只換設定頁「手機通知」那一塊（以前整個畫面重畫：iPhone 上一直閃）
    const box = typeof document !== "undefined" && document.querySelector(".push-box");
    if (box) box.innerHTML = pushBoxHtml();
    else if (S.sheet && S.pushHow) renderKeepingSheet(); // 「怎麼收到手機通知」那一頁按的「現在就開通知」：那一頁頂上那一句跟著換
  }

  async function pushRefresh() { // 打開設定時：這台裝置有沒有訂著；訂著就再交一次給伺服器（伺服器那份丟了也補得回來，不再送「開了」）
    if (!pushSupported()) return;
    try {
      const reg = await pushReg(); // 先註冊好、拿好公鑰：勾下去的那一下就能直接要權限、直接訂（iPhone 要在按下去的那一下做）
      const info = await api("/api/push");
      S.pushKey = info.key;
      S.pushKinds = info.kinds || null;
      const sub = await reg.pushManager.getSubscription();
      S.pushOn = !!sub && Notification.permission === "granted";
      if (S.pushOn) await api("/api/push/subscribe", { ...sub.toJSON(), quiet: true });
    } catch (e) { S.pushOn = false; }
    pushPaint();
  }

  async function pushEnable() {
    pushMarkAsked();
    if (!pushSupported()) return;
    S.pushBusy = true;
    S.pushError = "";
    S.pushTestNote = "";
    pushPaint();
    try {
      const perm = await Notification.requestPermission(); // 第一件事就問（前面不先等網路）：iPhone 只在按下去的那一下肯問
      if (perm !== "granted") {
        const err = new Error("");
        err.name = "NotAllowedError";
        throw err;
      }
      const reg = await pushReg();
      const key = S.pushKey || (S.pushKey = (await api("/api/push")).key);
      const sub = (await reg.pushManager.getSubscription()) || await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: pushKey(key) });
      await api("/api/push/subscribe", sub.toJSON());
      S.pushOn = true;
      toast("手機通知開了，馬上會跳一則試試。");
    } catch (e) {
      S.pushOn = false;
      S.pushError = pushErrorText(e);
    } finally { S.pushBusy = false; pushPaint(); }
  }

  async function pushDisable() {
    S.pushBusy = true;
    S.pushError = "";
    S.pushTestNote = "";
    pushPaint();
    try {
      const sub = await (await pushReg()).pushManager.getSubscription();
      if (sub) {
        await api("/api/push/unsubscribe", { endpoint: sub.endpoint }).catch(() => {});
        await sub.unsubscribe();
      }
      S.pushOn = false;
    } catch (e) { S.pushError = `關不掉：${(e && e.message) || "不明的錯"}`; } // 關不掉就照實留著勾
    finally { S.pushBusy = false; pushPaint(); }
  }

  async function pushTest() { // 「傳一則測試通知」：伺服器當場對這一台推一則，推不出去把原因寫在底下
    S.pushBusy = true;
    S.pushTestNote = "";
    pushPaint();
    try {
      const sub = await (await pushReg()).pushManager.getSubscription();
      if (!sub) throw new Error("這台裝置還沒開手機通知：先勾「手機通知」。");
      const res = await api("/api/push/test", { endpoint: sub.endpoint });
      S.pushTestNote = res.sent ? PUSH_TEST_OK : `沒送出去：${res.error || "不明的錯"}`;
    } catch (e) { S.pushTestNote = `沒送出去：${(e && e.message) || "不明的錯"}`; }
    finally { S.pushBusy = false; pushPaint(); }
  }

  async function pushKind(kind, on) { // 一種通知開或關
    try {
      const res = await api("/api/push/prefs", { kind, on });
      S.pushKinds = res.kinds;
    } catch (e) { /* api 已經跳了原因；照伺服器原本的畫回去 */ }
    pushPaint();
  }

  function pushBoxHtml() { // 設定頁「手機通知」那一塊的內容（pushPaint 只換這一塊）
    let note = "";
    if (pushNeedsHome()) note = "iPhone 要先在 Safari 按「分享 → 加入主畫面」，從主畫面打開遊戲，這裡才打得開。";
    else if (!pushSupported()) note = "這個瀏覽器收不到通知。";
    else if (Notification.permission === "denied") note = "通知被這個瀏覽器擋了：到瀏覽器的網站設定裡打開。";
    const off = !!note || S.pushBusy;
    const on = S.pushOn && !note;
    const kinds = S.pushKinds || {};
    const list = on ? `<div class="push-kinds">${PUSH_KIND_NAMES.map(([k, name]) =>
      `<label class="toggle"><input type="checkbox" class="push-kind" data-kind="${k}" ${kinds[k] !== false ? "checked" : ""} ${S.pushBusy ? "disabled" : ""}> ${name}</label>`).join("")}</div>
      <div class="row"><button class="btn small" data-act="push-test" ${S.pushBusy ? "disabled" : ""}>傳一則測試通知</button></div>` : "";
    return `<label class="toggle"><input type="checkbox" id="push-on" ${on ? "checked" : ""} ${off ? "disabled" : ""}> 手機通知${S.pushBusy ? "（處理中…）" : ""}</label>
      <p class="muted push-note">${note || (on ? "要跳哪幾種，底下一種一個開關（每一台裝置一樣）：" : `${PUSH_KINDS}時跳出來，遊戲關著也會。`)}</p>
      ${S.pushError ? `<p class="push-err">${esc(S.pushError)}</p>` : ""}
      ${list}
      ${S.pushTestNote ? `<p class="push-test-note">${esc(S.pushTestNote)}</p>` : ""}
      <div class="row push-help"><button class="btn small" data-act="push-how">${PUSH_HOW_TITLE} ›</button></div>`;
  }

  function pushRow() { // 設定頁那一顆
    if (!(S.main && S.main.web_push)) return "";
    return `<div class="push-box">${pushBoxHtml()}</div>`;
  }

  // ── 怎麼收到手機通知（Joy 2026-10-26：設定頁一顆鈕點開獨立的一步步說明，不跟玩法說明、新手引導混在一起；現階段很重要）──
  // 自己一頁（S.pushHow 時設定抽屜整個換成它，「← 回設定」回來）。照這台裝置排：iPhone／iPad（Safari 要先加入主畫面、從主畫面開，
  // iOS 16.4 起）、Android（Chrome 直接開，加到主畫面是建議）、電腦；偵測到的那一種攤開寫在最前面，其他兩種收在摺疊裡。
  // 頂上一句照此刻的狀況說下一步是什麼（還在瀏覽器裡、已經從主畫面開了、被擋了、已經開了）。字待 joy 潤
  const PUSH_HOW_TITLE = "怎麼收到手機通知";
  const PUSH_HOW_SITE = "tianxiadashi.com";
  function pushDevice() { // "ios"、"android"、"desktop"
    const ua = (typeof navigator !== "undefined" && navigator.userAgent) || "";
    return /iP(hone|ad|od)/.test(ua) ? "ios" : /Android/.test(ua) ? "android" : "desktop";
  }
  function pushStandalone() { // 從主畫面（安裝好的那一份）打開的
    return !!(typeof navigator !== "undefined" && navigator.standalone)
      || !!(typeof window !== "undefined" && window.matchMedia && window.matchMedia("(display-mode: standalone)").matches);
  }
  function pushPermission() { return typeof Notification !== "undefined" ? Notification.permission : "none"; }
  const PUSH_HOW_IOS = [
    `用 <b>Safari</b> 打開 <b>${PUSH_HOW_SITE}</b>（在 Chrome、LINE 裡打開的話先換到 Safari；要 iOS 16.4 以上）。`,
    "按畫面底下中間的<b>分享</b>鈕（一個方框、上面一支往上的箭頭）。",
    "選單往下捲，按<b>「加入主畫面」</b>，右上角按<b>「新增」</b>。",
    "回到手機的主畫面，點新出現的朱紅<b>「勢」</b>圖示打開遊戲（以後都從這裡進；在 Safari 裡開是收不到通知的）。",
    "遊戲裡右上角 <b>⚙ 設定</b> → 勾<b>「手機通知」</b> → 跳出來問的時候按<b>「允許」</b>。",
  ];
  const PUSH_HOW_IOS_DENIED = "之前按過「不允許」：到 iPhone 的<b>「設定」→「通知」</b>，找<b>「天下大勢」</b>，打開<b>「允許通知」</b>，再回遊戲勾「手機通知」。";
  const PUSH_HOW_ANDROID = [
    `用 <b>Chrome</b> 打開 <b>${PUSH_HOW_SITE}</b>。`,
    "遊戲裡右上角 <b>⚙ 設定</b> → 勾<b>「手機通知」</b> → 跳出來問的時候按<b>「允許」</b>。",
    "建議也加到主畫面：Chrome 右上角 <b>⋮</b> →<b>「加到主畫面」</b>（或「安裝應用程式」），以後點主畫面的朱紅<b>「勢」</b>圖示進來。",
  ];
  const PUSH_HOW_ANDROID_DENIED = "之前按過「封鎖」：按網址列左邊的<b>鎖頭（或設定）圖示</b> →<b>「權限」→「通知」</b>→ 改成允許；或到手機的<b>「設定」→「應用程式」→ Chrome →「通知」</b>打開，再回遊戲勾「手機通知」。";
  const PUSH_HOW_DESKTOP = [
    "右上角 <b>⚙ 設定</b> → 勾<b>「手機通知」</b> → 瀏覽器問的時候按<b>「允許」</b>（電腦也收得到，桌面會跳）。",
  ];
  const PUSH_HOW_DESKTOP_DENIED = "之前按過「封鎖」：按網址列左邊的<b>鎖頭圖示</b> →<b>「通知」</b>改成允許，再回來勾「手機通知」。";
  const PUSH_HOW_SECTIONS = {
    ios: { title: "iPhone、iPad", steps: PUSH_HOW_IOS, denied: PUSH_HOW_IOS_DENIED },
    android: { title: "Android 手機", steps: PUSH_HOW_ANDROID, denied: PUSH_HOW_ANDROID_DENIED },
    desktop: { title: "電腦", steps: PUSH_HOW_DESKTOP, denied: PUSH_HOW_DESKTOP_DENIED },
  };
  function pushHowStatus() { // 頂上那一句：此刻卡在哪、下一步做什麼
    const dev = pushDevice();
    if (S.pushOn && pushPermission() === "granted") return "這一台已經開了通知。想再開一台（另一支手機、電腦），在那一台照底下做一次。";
    if (pushPermission() === "denied") return "這一台的通知被擋著了：看底下「被擋了怎麼辦」那一段。";
    if (dev === "ios") return pushStandalone()
      ? "你已經是從主畫面打開的了：直接做第 5 步，勾「手機通知」就好。"
      : "你現在是在 iPhone 的瀏覽器裡：要先照第 1 到第 4 步把遊戲加到主畫面、從主畫面打開，才開得了通知。";
    if (dev === "android") return "Android 直接勾就好：照第 2 步。";
    return "電腦上直接勾就好；手機要收的話在手機上照底下做一次。";
  }
  function pushHowSection(key, open) {
    const sec = PUSH_HOW_SECTIONS[key];
    const body = `<ol class="push-steps">${sec.steps.map((t) => `<li>${t}</li>`).join("")}</ol>
      <h5>被擋了怎麼辦</h5><p>${sec.denied}</p>`;
    return open ? `<section class="push-how-sec"><h4>${sec.title}</h4>${body}</section>`
      : `<details class="fold push-how-sec"><summary>${sec.title}</summary><div class="fold-body">${body}</div></details>`;
  }
  function pushHowHtml() { // 設定抽屜整頁換成它
    const dev = pushDevice();
    const others = ["ios", "android", "desktop"].filter((k) => k !== dev);
    const canNow = pushSupported() && !pushNeedsHome() && pushPermission() === "default" && !S.pushOn;
    return `
      <div class="sheet-bg" data-act="sheet-close"></div>
      <div class="sheet push-how" role="dialog" aria-label="${PUSH_HOW_TITLE}">
        <div class="grip"></div>
        <div class="top-row"><button class="btn small ghost" data-act="push-how-back">← 回設定</button><h3 style="flex:1">${PUSH_HOW_TITLE}</h3><button class="btn small ghost" data-act="sheet-close">關閉</button></div>
        <p class="muted">開了之後，${PUSH_KINDS}時手機會跳出來告訴你，遊戲關著也會。不用裝 App、不收錢。</p>
        <p class="push-status">${pushHowStatus()}</p>
        ${canNow ? `<div class="row"><button class="btn primary" data-act="push-yes">現在就開通知</button></div>` : ""}
        ${pushHowSection(dev, true)}
        <p class="muted">用別的裝置？</p>
        ${others.map((k) => pushHowSection(k, false)).join("")}
      </div>`;
  }

  function pushAskHtml(m) { // 江湖頁信的小卡底下：第一次來信時問一次
    if (!m.letter || S.pushOn || pushAsked() || !pushSupported() || Notification.permission !== "default") return "";
    return `<section class="card push-ask"><p>以後有人來信、約戰、決戰集結時，要不要讓手機跳通知告訴你？</p>
      <div class="row"><button class="btn small primary" data-act="push-yes">開啟通知</button><button class="btn small ghost" data-act="push-no">不用</button></div></section>`;
  }
  async function notifyClick(act, el, ev) {
    switch (act) {
        case "push-how": S.pushHow = true; render(); break; // 設定頁「怎麼收到手機通知 ›」：抽屜整頁換成說明
        case "push-how-back": S.pushHow = false; render(); break;
        case "push-test": await pushTest(); break; // 設定頁「傳一則測試通知」
        case "push-yes": await pushEnable(); break; // 第一次來信時問的那一張（手機通知，減法季批 9）
        case "push-no": pushMarkAsked(); renderPage(); break;
    } // notifyClick
  } // notifyClick
  registerClicks(notifyClick, ["push-how", "push-how-back", "push-test", "push-yes", "push-no"]);
