/* 天下大勢的網頁前端：傳承（功能包 tianxia/features/legacy/，開發規範手冊 3.7 第 1 層）。
 *
 * 展開屬性裡的入口一行、傳承頁（legacyPageHtml）、識海頁、開季準備卡上的傳承入口（legacyOfferOpen）的畫法。
 * 跟 mall.js 一樣是一般的 <script>：頂層的名字同在一個全域裡，index.html 排在 mall.js 之後、app.js 之前。
 * 呼叫處與 prepShihaiHtml 照舊在 app.js（殼）；四個點擊（legacy-open／close／view／slip）用 registerClicks 登記在這支檔。
 */
"use strict";

  async function legacyClick(act, el, ev) {
    switch (act) {
        case "legacy-open": S.legacy = "main"; S.legacySlip = null; render(); break; // 傳承頁（features/legacy）
        case "legacy-close": S.legacy = null; render(); break;
        case "legacy-view": S.legacy = el.dataset.v === "shihai" ? "shihai" : "main"; render(); { const L = document.querySelector(".lg-layer"); if (L) L.scrollTop = 0; } break;
        case "legacy-slip": S.legacySlip = S.legacySlip === el.dataset.k ? null : el.dataset.k; render(); break;
    } // legacyClick
  } // legacyClick
  registerClicks(legacyClick, ["legacy-open", "legacy-close", "legacy-view", "legacy-slip"]);
  // 傳承（features/legacy；main.legacy）：展開的屬性裡一行入口，按了打開傳承頁（S.legacy = "main"）；識海頁是 S.legacy = "shihai"。
  // 兩頁的樣子在 web/legacy.css（企劃者 2026-11-04「要有真的傳承、識海的感覺」，示意 BsEscEEXvy8BVgw9hM89Si）
  const LG_AXES = [["zheng", "正氣"], ["xie", "邪氣"], ["luck", "機緣"]];
  const LG_NUM = ["", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"];
  const lgNum = (n) => { // 竹簡上的小字：5 → 五、10 → 十、20 → 二十、差 8 → 八
    n = Math.max(0, Math.floor(n));
    if (n <= 10) return n ? LG_NUM[n] : "〇";
    if (n < 20) return `十${LG_NUM[n - 10]}`;
    if (n < 100) return `${LG_NUM[Math.floor(n / 10)]}十${LG_NUM[n % 10]}`;
    return String(n);
  };
  function legacyHtml(g) {
    const vals = LG_AXES.map(([k, n]) => `<b class="lg-v-${k}">${n} ${g.values[k]}</b>`).join("　");
    const sealed = g.sealed ? `<span class="lg-entry-sub">識海封著：${esc(g.sealed)}</span>` : "";
    return `<button class="lg-entry" data-act="legacy-open"><span class="lg-entry-main">傳承　${vals}</span>${sealed}<span class="lg-entry-go" aria-hidden="true">›</span></button>`;
  }
  // 三卷（圖 web/img/legacy/scroll.webp，企劃者 2026-11-04 給）：墨水漲到這一項的值，到了那一道門就蓋朱印。
  // 座標照圖的原尺寸 280×800：紙面 x 43～238、y 30～770。卷的刻度照最後一道門的 1.25 倍（至少 25）
  const LG_IMG = "/static/img/legacy/";
  function lgScrollSvg(k, value, track) {
    const top = 30, bottom = 770, h = bottom - top;
    const max = Math.max(25, ...track.map((t) => t.at * 1.25), value * 1.1);
    const y = (v) => bottom - Math.min(v, max) / max * h;
    const fy = y(value).toFixed(1);
    const marks = track.map((t) => {
      const ty = y(t.at).toFixed(1);
      return `<line x1="43" y1="${ty}" x2="238" y2="${ty}" class="lg-tick"/>`
        + `<circle cx="214" cy="${ty}" r="19" class="${t.open ? "lg-seal-on" : "lg-seal-off"}"/><text x="214" y="${(+ty + 8).toFixed(1)}" class="lg-seal-t${t.open ? " on" : ""}">${lgNum(t.at)}</text>`;
    }).join("");
    const ink = value > 0 ? `<rect x="43" y="${fy}" width="195" height="${(bottom - fy).toFixed(1)}" fill="url(#lg-ink-${k})" class="lg-ink"/>
      <path d="M43 ${fy} C90 ${(fy - 14).toFixed(1)} 140 ${(+fy + 14).toFixed(1)} 190 ${(fy - 4).toFixed(1)} S238 ${fy} 238 ${fy}" class="lg-ink-top lg-ink-top-${k}"/>` : "";
    return `<svg class="lg-scroll" viewBox="0 0 280 800" aria-hidden="true">
      <defs><linearGradient id="lg-ink-${k}" x1="0" y1="1" x2="0" y2="0"><stop offset="0" class="lg-ink-a-${k}"/><stop offset="1" class="lg-ink-b-${k}"/></linearGradient></defs>
      <image href="${LG_IMG}scroll.webp" x="0" y="0" width="280" height="800"/>${ink}${marks}</svg>`;
  }
  function legacyMainHtml(g) {
    const cols = LG_AXES.map(([k, n]) => {
      const track = (g.tracks && g.tracks[k]) || [];
      const slips = track.map((t, i) => {
        const on = S.legacySlip === `${k}:${i}`;
        const tail = t.open ? `${n.slice(0, 1)}${lgNum(t.at)}` : `差${lgNum(t.at - g.values[k])}`;
        return `<button class="lg-slip${t.open ? " open" : ""}" data-act="legacy-slip" data-k="${k}:${i}" aria-pressed="${on}" aria-label="${esc(n)} ${t.at}：${esc(t.text)}"><span>${esc(t.short)}</span><small>${tail}</small></button>`;
      }).join("");
      return `<div class="lg-col">${lgScrollSvg(k, g.values[k], track)}
        <div class="lg-name lg-c-${k}">${n}</div><div class="lg-val">${g.values[k]}</div>
        <div class="lg-gain">${g.gains[k] > 0 ? `上一季 +${g.gains[k]}` : "上一季 —"}</div>
        <div class="lg-slips">${slips}</div></div>`;
    }).join("");
    let note = "按一片竹簡，看那一道門路開了什麼";
    if (S.legacySlip) {
      const [k, i] = S.legacySlip.split(":");
      const t = ((g.tracks || {})[k] || [])[+i];
      const n = (LG_AXES.find((x) => x[0] === k) || ["", ""])[1];
      if (t) note = `<b class="lg-c-${k}">${n} ${t.at}</b>　${esc(t.text)}<span class="lg-note-st">${t.open ? "這一季開著" : `還差 ${t.at - g.values[k]}`}</span>`;
    }
    const sh = g.shihai || {};
    const sealed = sh.sealed;
    const left = (sh.need || []).filter((x) => !x.ok).length;
    const portal = `<button class="lg-portal" data-act="legacy-view" data-v="shihai">
      <svg viewBox="0 0 350 150" preserveAspectRatio="xMaxYMid slice" aria-hidden="true"><defs><radialGradient id="lg-orb" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#e8f4ff"/><stop offset=".35" stop-color="#7fb4e0" stop-opacity=".8"/><stop offset="1" stop-color="#2a5a86" stop-opacity="0"/></radialGradient></defs>
      <path d="M0 104 C40 94 70 112 110 102 S190 92 230 104 S310 112 350 100 L350 150 L0 150 Z" fill="#12263a"/><path d="M0 122 C50 112 90 130 140 120 S240 110 290 124 S340 126 350 120 L350 150 L0 150 Z" fill="#183450"/>
      ${sealed ? '<circle cx="280" cy="64" r="44" fill="url(#lg-orb)" class="lg-breathe"/><circle cx="280" cy="64" r="10" fill="#f2f8ff"/>' : ""}</svg>
      <span class="lg-portal-t">入識海</span>
      <span class="lg-portal-s">${sealed ? "前世封著一縷神品意境" : (sh.offers || []).length ? "上一季的神品意境，挑一份封進來" : "每一季開季時，可以把上一季的神品意境封一份進來"}</span>
      ${sealed ? `<span class="lg-portal-n">${esc(sealed.name)}・三道封印${left ? `還有 ${left} 道` : "都破了"}</span>` : ""}
    </button>`;
    return `<div class="lg-head"><div class="lg-title"><h2>傳承</h2><p>前塵七分入骨，今生再添一筆</p></div></div>
      <div class="lg-cols">${cols}</div>
      <p class="lg-note" aria-live="polite">${note}</p>
      ${portal}
      <p class="lg-foot">每一季收季時，正氣看善名、邪氣看惡名、機緣看懸賞託付、戰功、名望與人物情誼；舊的留七成再加上去。只開門路，不加屬性。</p>`;
  }
  function legacyShihaiHtml(g) {
    const sh = g.shihai || {};
    const s = sh.sealed;
    const need = sh.need || [];
    const offers = sh.offers || []; // 開季的候選（企劃者 2026-11-05：開季、做第一件事之前挑；一動身就收掉）
    const SEAL_CH = { time: "時", level: "境", xinde: "悟" };
    const orb = s ? `<div class="lg-orb-wrap lg-drift"><svg viewBox="0 0 240 300" aria-hidden="true">
        <defs><radialGradient id="lg-halo" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#cfe6ff" stop-opacity=".9"/><stop offset=".3" stop-color="#6aa6dc" stop-opacity=".45"/><stop offset="1" stop-color="#1b3c5e" stop-opacity="0"/></radialGradient>
        <radialGradient id="lg-core" cx=".42" cy=".38" r=".6"><stop offset="0" stop-color="#fff"/><stop offset=".5" stop-color="#bcdcf6"/><stop offset="1" stop-color="#4b85b8"/></radialGradient></defs>
        <circle cx="120" cy="150" r="118" fill="url(#lg-halo)" class="lg-breathe"/><circle cx="120" cy="150" r="80" fill="url(#lg-halo)"/><circle cx="120" cy="150" r="52" fill="url(#lg-core)"/>
        <path d="M84 140 C100 128 120 160 156 140" stroke="#fff" stroke-opacity=".6" stroke-width="2" fill="none"/></svg>
        <div class="lg-talisman"><span>敕令鎮心</span><b>封</b><span>第${lgNum(s.season)}季</span></div></div>
      <div class="lg-insight"><small>神品意境・屬${esc(s.attribute)}</small><b>${esc(s.name)}</b></div>`
      : `<div class="lg-insight empty"><b>識海空空</b><small>${offers.length ? "還沒封進任何一份" : "這一季沒有封著的意境"}</small></div>`;
    let unseal = "";
    if (s) {
      const seals = need.map((x) => `<div class="lg-seal${x.ok ? " broken" : ""}"><i>${SEAL_CH[x.key] || ""}</i><span>${esc(x.text)}</span><small>${x.ok ? "已破" : esc(x.now || "未破")}</small></div>`).join("");
      const ready = need.every((x) => x.ok) && !sh.held;
      const names = (s.names || []).length
        ? `<div class="lg-rename"><p>「${esc(s.name)}」這一季江湖上已經有人取了，先取的人優先。替它換一個名字：</p>
            <div class="row">${s.names.map((n, i) => `<button class="lg-btn" data-act="choose" data-id="legacy:name:${i}">${esc(n)}</button>`).join("")}</div></div>` : "";
      unseal = `<div class="lg-sep"><span>三道封印</span></div><div class="lg-seals">${seals}</div>
        ${sh.held ? '<p class="lg-warn">你身上已經有一份神品意境：神品一人最多一份，先放掉那一份才解得開。</p>' : ""}
        ${names || `<button class="lg-break" data-act="choose" data-id="legacy:open" ${ready ? "" : "disabled"}>破封　撈起意境</button>
        <p class="lg-hint">封印全破才按得下；破封要付心得，名號照這一季登記</p>`}`;
    }
    const offer = offers.length ? `<div class="lg-sep"><span>前世帶來的神品</span></div>
        <p class="lg-hint">挑一份封進識海帶進這一季。做第一件事之前都能選，一動身就來不及了。</p>
        ${offers.map((o, i) => `<div class="lg-keep"><div><b>${esc(o.name)}</b><small>神品意境・屬${esc(o.attribute)}・第${lgNum(o.season)}季</small></div><button class="lg-btn" data-act="choose" data-id="legacy:seal:${i}">封進識海</button></div>`).join("")}
        <button class="lg-btn lg-skip" data-act="choose" data-id="legacy:skip">這一季不帶</button>` : "";
    return `<div class="lg-sea${s ? "" : " bare"}">
        <div class="lg-sea-title"><h2>識海</h2><p>前世所悟，沉於心底。<br>今生境到，方能撈起。</p></div>
        ${orb}
      </div>
      <div class="lg-sea-body">${offer}${unseal}${offers.length || s ? "" : '<p class="lg-hint">每一季開季時，上一季身上的神品意境可以挑一份封進識海，解封之後就是你的。</p>'}</div>`;
  }
  // 開季還沒挑識海（main.legacy.shihai.offers）：進遊戲第一個畫面就打開識海頁，一次（關掉之後不再自己跳；選單裡照舊有）
  function legacyOfferOpen() {
    const g = S.main && S.main.legacy;
    const n = g && g.shihai && g.shihai.offers ? g.shihai.offers.length : 0;
    if (!n || (S.main && S.main.prep)) { S.legacyOffered = false; return; } // 開季準備卡在畫識海那一步：不另外跳識海頁
    if (S.legacyOffered) return;
    S.legacyOffered = true;
    S.legacy = "shihai";
  }
  function legacyPageHtml() {
    const g = S.main && S.main.legacy;
    if (!g) return "";
    const v = S.legacy === "shihai" ? "shihai" : "main";
    return `<div class="lg-layer lg-${v}" role="dialog" aria-label="${v === "shihai" ? "識海" : "傳承"}">
      <div class="lg-bar"><button data-act="legacy-close" aria-label="返回">‹ 返回</button>
        <span class="seg-lite"><button data-act="legacy-view" data-v="main" aria-pressed="${v === "main"}">傳承</button><button data-act="legacy-view" data-v="shihai" aria-pressed="${v === "shihai"}">識海</button></span></div>
      ${v === "shihai" ? legacyShihaiHtml(g) : legacyMainHtml(g)}
    </div>`;
  }
