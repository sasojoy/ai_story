/* 天下大勢的網頁前端：每日簽到的小卡與挑一樣（全部拆包第 67 批從 main.js 切出來）。
 *
 * 跟 app.js 一樣是一般的 <script>：頂層的名字同在一個全域裡。/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 */
"use strict";

  // 每日簽到（21 天季，正式季整合 6.2；畫面照 9.1 第 4 組丙）：收進這一排小標，還沒簽亮紅點、簽了寫「簽到 ✔」。攤開是這一週七格
  // （最後一週到季末為止）、今天的份與領的鈕；四階的日子是四顆挑屬性的鈕（點一種就領）。伺服器沒給 status.checkin（週末與 14 天的季、
  // 序章裡、休季）就不畫。CK_LAST 待 joy 潤
  const CK_ATTR = { 剛: "gang", 柔: "rou", 快: "kuai", 慢: "man" };
  const CK_LAST = "這一季最後一天";
  // 格子上的短字（FB-436）：兩樣的那一格（第 6 天「丹2＋四階」）375、360 寬放不下一行，照「＋」拆兩行；一樣的照舊一行
  function ckGift(label) {
    const parts = String(label).split("＋");
    return parts.length < 2 ? esc(label) : parts.map((p, i) => `<span class="gl">${i ? "＋" : ""}${esc(p)}</span>`).join("");
  }
  function checkinPeek(m) {
    const k = m.status && m.status.checkin;
    if (!k) return null;
    const cells = k.week.map((d) => `<div class="ck-day ${d.state}${d.got ? " got" : ""}${d.four ? " four" : ""}"><span class="d">${d.day}</span><span class="g">${ckGift(d.label)}</span></div>`).join("");
    const act = k.done ? "" : k.pick
      ? `<div class="ck-pick">${k.pick.map((x) => `<button class="ck-p4 ${CK_ATTR[x.attribute] || ""}" data-act="checkin" data-attr="${esc(x.attribute)}"><b>${esc(x.attribute)}</b>${esc(x.name)}<small>有 ${x.held}</small></button>`).join("")}</div>`
      : '<button class="ck-go" data-act="checkin">領取</button>';
    return {
      id: "checkin",
      label: `簽到：第 ${k.day} 天${k.done ? "已簽" : "還沒簽"}`,
      chip: `<span class="peek-name">簽到${k.done ? " ✔" : ""}</span>`,
      flag: !k.done,
      dotNote: "",
      panel: `<div class="ck-head"><b>第 ${k.day} 天</b><span>${k.next ? `下一份：${esc(k.next)}` : CK_LAST}</span></div>`
        + `<div class="ck-week">${cells}</div><p class="ck-step">${esc(k.step)}</p>${act}`,
    };
  }

  const CK_PICK_TITLE = "簽到第 {day} 天";
  const CK_PICK_NOTE = "今天的份要挑一樣";

  // 簽到要挑四階的日子（還沒挑）：本週卡底下一張小卡，四顆挑屬性的鈕（點一種就領，同以前簽到格裡的那四顆）
  function checkinPickHtml(m) {
    const k = m.status && m.status.checkin;
    if (!k || k.done || !k.pick) return "";
    return `<section class="card ck-card" aria-label="簽到"><h3>${CK_PICK_TITLE.replace("{day}", k.day)}<small>${CK_PICK_NOTE}</small></h3>
      <div class="ck-pick">${k.pick.map((x) => `<button class="ck-p4 ${CK_ATTR[x.attribute] || ""}" data-act="checkin" data-attr="${esc(x.attribute)}"><b>${esc(x.attribute)}</b>${esc(x.name)}<small>有 ${x.held}</small></button>`).join("")}</div></section>`;
  }

  // 每天第一次登入跳一個簽到小窗（Joy 2026-11-07「簽到在每天登入的時候跳出來簽就好？藏那麼裡面不好吧」）：引擎當天第一次同步已經自動領了
  // （_auto_checkin），這裡寫今天領到什麼、七天那一排標出今天；要挑四階的日子窗裡直接挑。挑完或按「收下」就關，同一天（照簽到的第幾天）
  // 這個瀏覽器不再跳；記不住（私密視窗）就這一次關了算數。窗是 .sheet：開著時底下鎖住不捲（syncScrollLock）
  const CK_SEEN = "tianxia.ckSeen";
  // 待 joy 潤：小窗底下那一顆
  const CK_POP_OK = "收下";
  const CK_POP_LATER = "等一下再挑";
  const ckDayKey = (k) => `${k.day}|${k.week.map((d) => d.label).join(",")}`;
  function ckSeen(k) {
    if (S.ckSeen === undefined) { try { S.ckSeen = localStorage.getItem(CK_SEEN) || ""; } catch (e) { S.ckSeen = ""; } }
    return S.ckSeen === ckDayKey(k);
  }
  function ckPopClose() {
    const k = S.main && S.main.status && S.main.status.checkin;
    if (!k) return;
    S.ckSeen = ckDayKey(k);
    try { localStorage.setItem(CK_SEEN, S.ckSeen); } catch (e) { /* 私密視窗：這一次關了算數 */ }
  }
  function ckPopHtml(m) {
    const k = m.status && m.status.checkin, peek = k && checkinPeek(m);
    if (!peek || ckSeen(k) || (m.story_cards || []).length) return ""; // 特殊事件的跳顯框還沒看完：先看那幾張，看完才跳簽到
    const close = `<button class="btn ${k.done ? "primary" : "ghost"} ck-pop-ok" data-act="ck-pop-close">${k.done ? CK_POP_OK : CK_POP_LATER}</button>`;
    return `<div class="sheet-bg" data-act="ck-pop-close"></div><div class="sheet ck-pop" role="dialog" aria-label="簽到"><div class="grip"></div>`
      + `<h3>簽到</h3>${peek.panel}${close}</div>`;
  }
  async function checkinClick(act, el, ev) {
    switch (act) {
        case "ck-pop-close": ckPopClose(); renderPage(); break; // 每天第一次登入的簽到小窗：收下或等一下再挑，同一天不再跳
        case "checkin": await doMain("checkin", el.dataset.attr ? { attribute: el.dataset.attr } : {}); break; // 「簽到」小標攤開的領取鈕（四階的日子帶屬性）
    } // checkinClick
  } // checkinClick
  registerClicks(checkinClick, ["ck-pop-close", "checkin"]);
