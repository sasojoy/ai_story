/* 天下大勢的網頁前端：鐵匠鋪（功能包 tianxia/features/smithy/，開發規範手冊 3.7、G9）。
 *
 * 鐵匠鋪（smithHtml）：架上、打造（看火候、就地熬、放料、開爐與出爐卡、神器定名）、裝備庫、素材頁、神器頁的畫法。
 * 跟 mall.js 一樣是一般的 <script>：頂層的名字同在一個全域裡；/ 的 script 標籤由伺服器照 FEATURES 生成、排在 app.js 前面。
 * 全部拆包第 65 批從 app.js 逐行切出來（計畫 docs/superpowers/plans/2026-11-06-網頁殼化-第65批.md）。點擊、表單用 registerClicks、registerForms 登記在這支檔；店面的框（SHOP_ATTR、shopHtml、shopNoteHtml、renderShop）照舊在 app.js（殼）。
 */
"use strict";

  // ── 店面（店面獨立介面設計第一、二節；第一批：鐵匠鋪）──
  // 伺服器在店開著、開關開著時給 main.shop（shopview.smith_view）：蓋住整個畫面（同武學譜那本書的蓋法），左上「出店」送現在的離開，
  // 兵器／防具切換、買、修、淬煉送現在的選項 id（choose），換上、拆解走修練頁的動作（shopMx），開爐是 /api/do/smith_forge。字待 joy 潤
  // 鐵匠鋪與合成流程 3.4（企劃者 2026-10-29 選「乙 併成一頁」）：「淬煉與修」併進裝備庫，五頁變四頁（素材、神器照舊另外接在後面）
  const SHOP_TABS = [["shelf", "架上"], ["forge", "打造"], ["rack", "裝備庫"]];

  const SHOP_RACK_LIST = 8;

  // 鐵匠鋪現在停在哪一頁（S.shopTab 不認得的當架上，同 smithHtml）。素材頁只在伺服器給了 shop.trade（收購或升階開著）時有
  // 舊的「淬煉與修」（temper；網頁沒重新載入、手上還記著那一頁）當裝備庫：那一頁併進去了（3.4）。神器頁只在輪替季（shop.divine）有
  function smithTab(shop) {
    if (S.shopTab === "trade") return shop && shop.trade ? "trade" : "shelf";
    if (S.shopTab === "divine") return shop && shop.divine ? "divine" : "shelf";
    if (S.shopTab === "temper") return "rack";
    return ["forge", "rack"].includes(S.shopTab) ? S.shopTab : "shelf";
  }
  // 鐵匠鋪的分頁：三頁，素材買賣開著時多一頁「素材」（素材與經濟 B6，企劃者 2026-10-15 選草圖 A1），神器輪替的季最後多一頁「神器」
  // （鐵匠鋪與合成流程 3.8；沒蓋章的季照舊）
  function smithTabs(shop) {
    const tabs = shop.trade ? [...SHOP_TABS, ["trade", "素材"]] : SHOP_TABS;
    return shop.divine ? [...tabs, ["divine", "神器"]] : tabs;
  }

  // 鐵匠鋪（第一批）：兵器防具切換、四頁、分頁列、出爐卡。架上頁最上面是爐火與鐵匠那一句（line，shopHtml 交過來），不跟著貨卡捲。
  // 素材頁不分兵器、防具：那一頁不畫上面的切換
  function smithHtml(shop, line = "") {
    const tab = smithTab(shop);
    const pages = shop.pages.length > 1 && tab !== "trade" && tab !== "divine" ? `<div class="shop-pages">${shop.pages.map((p) => `<button class="shop-page${p.slot === shop.page ? " on" : ""}"${p.slot === shop.page ? " disabled" : ` data-act="choose" data-id="${esc(p.id)}"`}>${esc(p.label)}</button>`).join("")}</div>` : "";
    const body = { shelf: shelfHtml, forge: forgePageHtml, rack: rackHtml, trade: tradeHtml, divine: divineHtml }[tab];
    // 架上頁鐵匠那一句底下一行連到神器頁（3.8：輪替季才有）
    return `${tab === "shelf" ? smithHeroHtml(line) + (shop.divine ? divineLinkHtml(shop.divine) : "") : ""}${pages}
      <div class="shop-body"><div class="shop-col">${body(shop)}</div></div>
      <nav class="shop-tabs">${smithTabs(shop).map(([k, name]) => `<button class="shop-tab${tab === k ? " on" : ""}" data-act="shop-tab" data-tab="${k}">${name}</button>`).join("")}</nav>
      ${S.shopReveal ? revealHtml(S.shopReveal, shop) : ""}`;
  }

  // 素材頁（素材與經濟設計第四、五節；企劃者 2026-10-15：上半升階、下半收購）。升階一屬性一列、二階三階各一格（拿什麼換、偏向出哪一種、
  // 幾成、工錢、今天還能換幾個；按不下去的灰掉、格子上寫短的原因，點了說整句）；收購一種一列（賣一個、全賣先問一次）。
  // 升階出來的屬性隨機（企劃者 2026-10-15「屬性隨機、偏向投入的」），格子上照伺服器寫「五成・其餘隨機」。字待 joy 潤
  const UP_ALL = "全熬 ×{n}"; // 待 joy 潤
  const UP_ONE = "熬一個"; // 待 joy 潤
  const UP_USE = "{need} 個{from}・{cost} 兩"; // 待 joy 潤：熬一個那一顆的小字
  const UP_ALL_USE = "{n} 個{from}・{cost} 兩"; // 待 joy 潤：全熬那一顆的小字（一次用掉幾個、幾兩）
  const UP_LINK_COUNT = "{n}"; // 熬煉鏈一格底下的件數
  const TRADE_RULES = "熬煉的規矩"; // 待 joy 潤：「？」摺疊的那一行
  // 熬煉鏈（Joy 2026-11-10 翻新，翻新稿 9RrHPAD6）：一屬性一張卡，一階到最高階排成一條「精鐵砂 › 玄鋼骨 › 隕鐵膽 › 熔星髓」，每一格底下手上幾個；
  // 熬得出來的那一格描金、點了選它（S.tradePick[屬性]＝階，預設第一個熬得出來的），卡底下「全熬 ×N」（主鈕，連換得了兩個以上才有）與「熬一個」；
  // 一格都熬不了寫最近那一格的短原因（「手上 2／3」）。規矩（升階比例、隨機、四階上限）收進「？」。按鈕照舊送 trade-up（attr、tier、n）
  function tradeCounts(shop) {
    const have = new Map();
    for (const m of (shop.forge && shop.forge.materials) || []) have.set(m.id, m.count | 0);
    for (const r of shop.trade.upgrade) if (!have.has(r.from_id)) have.set(r.from_id, r.have | 0);
    return have;
  }
  function tradeChainHtml(attribute, cells, have) {
    const can = cells.filter((r) => !r.problem);
    const pickTier = (S.tradePick || {})[attribute];
    const pick = can.find((r) => r.tier === pickTier) || can[0] || null;
    const first = cells[0];
    const link = (id, name, tier, row) => {
      const n = have.get(id) || 0;
      const ok = row && !row.problem;
      const tag = ok ? "button" : "span";
      return `<${tag} class="lk${n ? "" : " zero"}${ok ? " can" : ""}${pick && row === pick ? " pick" : ""}"${ok ? ` data-act="trade-pick" data-attr="${esc(attribute)}" data-tier="${tier}"` : ""}>${gearImg("mat", id, "lk-pic")}<b>${esc(name)}</b><small>${UP_LINK_COUNT.replace("{n}", n)}</small></${tag}>`;
    };
    const links = [link(first.from_id, first.from, first.tier - 1, null), ...cells.map((r) => link(r.id, r.name, r.tier, r))].join('<span class="arw" aria-hidden="true">›</span>');
    let acts;
    if (!pick) {
      const near = cells[0];
      acts = `<p class="up-short">${esc(near.short || near.problem || "")}</p>`;
    } else {
      const r = pick;
      const oneBtn = `<button class="btn up-cell${r.batch >= 2 ? "" : " primary"}" data-act="trade-up" data-attr="${esc(r.attribute)}" data-tier="${r.tier | 0}" data-why=""><b>${UP_ONE}${esc(r.name)}</b><small>${UP_USE.replace("{need}", r.need | 0).replace("{from}", esc(r.from)).replace("{cost} 兩", `<span class="nb">${r.cost | 0} 兩</span>`)}${dealHtml(r.cost_note || "")}${r.left_text ? `・<span class="nb">${esc(r.left_text)}</span>` : ""}</small></button>`;
      const all = r.batch >= 2
        ? `<button class="btn primary up-all" data-act="trade-up" data-attr="${esc(r.attribute)}" data-tier="${r.tier | 0}" data-n="${r.batch | 0}"><b>${UP_ALL.replace("{n}", r.batch | 0)}</b><small>${UP_ALL_USE.replace("{n}", (r.batch * r.need) | 0).replace("{from}", esc(r.from)).replace("{cost}", (r.batch * r.cost) | 0)}</small></button>` : "";
      acts = `<div class="ups${all ? "" : " one"}">${oneBtn}${all}</div>${r.lean ? `<p class="up-odds">${esc(r.odds || "")}</p>` : ""}`;
    }
    return `<div class="chain"><div class="ch-hd"><span class="row-attr ${SHOP_ATTR[attribute] || ""}">${esc(attribute)}</span></div><div class="links">${links}</div>${acts}</div>`;
  }
  function tradeHtml(shop) {
    const t = shop.trade;
    let ups = "";
    if (t.upgrade.length) {
      const rows = [];
      for (const r of t.upgrade) {
        const last = rows[rows.length - 1];
        if (last && last.attribute === r.attribute) last.cells.push(r);
        else rows.push({ attribute: r.attribute, cells: [r] });
      }
      const have = tradeCounts(shop);
      const help = `<button class="sm-help" data-act="trade-help" aria-expanded="${!!S.tradeHelp}"><span class="q" aria-hidden="true">？</span>${TRADE_RULES} ${S.tradeHelp ? "▴" : "▾"}</button>${S.tradeHelp ? `<ul class="sm-rules"><li>${esc(t.up_cap)}</li><li>${esc(t.hint || "")}</li></ul>` : ""}`;
      ups = `<div class="up-rows${shop.four ? " four" : ""}">${rows.map((row) => tradeChainHtml(row.attribute, row.cells.sort((a, b) => a.tier - b.tier), have)).join("")}</div>${help}`;
    }
    let sells = "";
    if (t.sell_cap) {
      const row = (r) => `<div class="sell-row"><span class="nm"><b>${matIcon(r.id, r.attribute)}${esc(r.name)}</b><small>${esc(r.tier_word)}・手上 ${r.have | 0}・一個 ${r.price | 0} 兩${r.dark ? esc(r.dark) : ""}</small></span>
          <span class="acts"><button class="btn small" data-act="trade-sell" data-id="${esc(r.id)}" data-n="1">賣 1 個</button>${r.have > 1
            ? `<button class="btn small ghost" data-act="trade-sell" data-id="${esc(r.id)}" data-n="${r.have | 0}" data-confirm="${esc(`把 ${r.have | 0} 個${r.name}都賣了，換 ${(r.have * r.price) | 0} 兩？`)}">全賣 ${(r.have * r.price) | 0} 兩</button>` : ""}</span></div>`;
      sells = `<p class="shop-cap">${esc(t.sell_cap)}</p>${t.sell.length ? `<div class="sell-rows">${t.sell.map(row).join("")}</div>` : `<p class="shop-empty">${esc(t.sell_empty)}</p>`}`;
    }
    return `${shopNoteHtml(t.upgrade.length ? "" : t.hint)}${ups}${sells}`;
  }

  // 架上（2.1）：一件一格；配得上的標出來，買不了的灰掉寫原因
  // 架上那一頁最上面的爐火與鐵砧（企劃者 2026-10-14，照草圖 container.html 的 A）：一大團發亮的橘色圓頂爐口、火光往外暈，底下鐵砧；
  // 純 CSS 畫（style.css 的 .forge-mouth、.forge-anvil）；Joy 之後有正式的圖可以換
  const SMITH_HERO = '<div class="forge-mouth"><i class="flame"></i></div><div class="forge-anvil"></div>';
  // 鐵匠鋪內景的水墨圖畫好了（web/img/gear/scene-smithy.webp，gear.js 的 gearImg）就換成頁首圖：圖往下淡進店面的底色、右上直書的匾額
  // （介面設計規範第五節「頁首圖」；Joy 2026-11-10）。還沒有圖照舊畫上面那座純 CSS 的爐子
  const SMITH_PLAQUE = "鐵匠鋪"; // 待 joy 潤
  // 鐵匠鋪翻新（Joy 2026-11-10「整個鐵匠鋪的介面可以翻新嗎」，翻新稿 9RrHPAD6）：頁首一張卡——上面是圖（還沒有圖是 CSS 的爐子），
  // 右上直書匾額，底下朱印「鐵匠」＋鐵匠那一句（line，殼交過來的 .shop-line）；介面設計規範第五節「頁首圖」
  const SMITH_SEAL = "鐵匠"; // 待 joy 潤
  function smithHeroHtml(line = "") {
    const pic = gearImg("scene", "smithy", "smith-scene");
    return `<div class="smith-hero"><div class="sh-art" aria-hidden="true">${pic || SMITH_HERO}</div><span class="smith-plaque" aria-hidden="true">${SMITH_PLAQUE}</span>
      <div class="sh-text"><span class="sh-seal">${SMITH_SEAL}</span>${line}</div></div>`;
  }
  // 器物沒有圖之前的那一枚器名印（劍、刀、拳……照種類的第一個字）；防具一律「甲」
  function wareMark(kind) {
    return `<span class="si-mark" aria-hidden="true">${esc([...String(kind || "甲")][0])}</span>`;
  }
  // 淬煉幾層（淬煉衝階）：名字旁邊的「+N」；沒淬過不寫
  function plusHtml(n) {
    return n > 0 ? `<em class="plus">+${n | 0}</em>` : "";
  }
  // 素材的小圖（web/img/gear/mat-<id>.webp）：有圖放圖，沒有照舊一顆屬性色點
  function matIcon(id, attribute) {
    return gearImg("mat", id, "mat-pic") || `<i class="dot ${SHOP_ATTR[attribute] || ""}"></i>`;
  }

  const SHELF_BUY = "買"; // 待 joy 潤
  function shelfHtml(shop) {
    // 這一段的變數不用單字母 x：tests/server/test_server.py 把修練頁到輿圖之間那個變數讀的欄位都當成 menxia_view 的欄位查
    // 翻新（Joy 2026-11-10）：一件一張橫卡——左邊器名印，中間名字（楷書）與「種類・屬性・階」、效果、配得上那一句，右邊價錢與一顆「買」。
    // 整張卡就是那一顆鈕（一張卡一顆主鈕）；配得上的左上角蓋一枚「配」
    return `<div class="shop-grid">${shop.shelf.map((ware) => `<button class="shop-item${ware.fit ? " fit" : ""}" data-act="choose" data-id="${esc(ware.id)}" ${ware.enabled ? "" : "disabled"}>
        ${ware.fit ? '<span class="si-stamp" aria-hidden="true">配</span>' : ""}${wareMark(ware.kind)}<span class="si-info">
        <b>${esc(ware.name)}</b><span>${esc(ware.kind)}・屬${esc(ware.attribute)}・${esc(ware.tier)}</span>${ware.value ? `<span>${esc(ware.value)}</span>` : ""}
        ${ware.note ? `<span class="fit-note">${esc(ware.note)}</span>` : ""}</span><span class="si-buy"><span class="price">${ware.enabled ? `${ware.price | 0} 兩` : esc(ware.why)}</span>${ware.enabled ? `<span class="si-go">${SHELF_BUY}</span>` : ""}</span></button>`).join("")}</div>`;
  }

  // 裝備庫頁最上面身上那件的卡（原本「淬煉與修」那一頁，2.4；鐵匠鋪與合成流程 3.4 搬到這裡）：鋒利度或耐久度的長條、淬煉幾格，
  // 「修」「淬煉」兩顆大鈕送原本的選項 id（smith:repair、smith:temper、smith:armor-repair、smith:armor-temper）；做不了照伺服器的原因寫
  const WORN_SPINE = "身上"; // 待 joy 潤
  const TEMPER_PCT = "・成功 {pct}%"; // 待 joy 潤：過了安全線，淬煉鈕的小字多寫這一下幾成
  function smithWornHtml(shop) {
    const w = shop.worn;
    if (!w.item) return `<p class="shop-empty">${esc(w.empty)}</p>`;
    const it = w.item;
    // 淬煉衝階（Joy 2026-11-10）：安全線以內的格子金框，過了安全線的朱框（淬那幾格會失敗、退一層）；淬煉鈕的小字多寫這一下幾成
    const safe = it.temper_safe == null ? it.temper_max | 0 : it.temper_safe | 0;
    const pips = Array.from({ length: it.temper_max | 0 }, (_, i) => `<i class="${i < it.tempers ? "on" : ""}${i >= safe ? " risk" : ""}"></i>`).join("");
    const odds = (b) => (b.enabled && it.temper_pct != null && it.temper_pct < 100 ? TEMPER_PCT.replace("{pct}", it.temper_pct | 0) : "");
    // 一張卡一顆主鈕：要修（鋒利度掉到一半以下）時「修」是主鈕，不然是「淬煉」
    const lead = w.repair.enabled && (it.wear | 0) < 50 ? "repair" : "temper";
    const big = (b, name, key) => `<button class="btn shop-big${lead === key && b.enabled ? " primary" : ""}" data-act="choose" data-id="${esc(b.id)}" ${b.enabled ? "" : "disabled"}><b>${name}</b><small>${esc(b.enabled ? b.use : b.why)}${key === "temper" ? odds(b) : ""}</small></button>`;
    // 淬煉幾格照這一件的上限（3.6：上品 7 格；衝階開著一律 10 格），旁邊寫「N/M」；上品多一句磨得慢（wear_note）。待 joy 潤
    return `<div class="shop-worn"><span class="sw-spine" aria-hidden="true">${WORN_SPINE}</span><div class="sw-in">
        <div class="sw-hd"><b>【${esc(it.name)}】</b>${plusHtml(it.tempers)}<span>${esc(it.grade)}${it.wear_note ? `・${esc(it.wear_note)}` : ""}</span></div>
        <div class="shop-wear"><span>${esc(it.wear_word)} ${it.wear | 0}</span><div class="wear-bar"><i class="${(it.wear | 0) < 50 ? "low" : ""}" style="width:${Math.max(0, Math.min(100, it.wear | 0))}%"></i></div></div>
        <div class="tempers"><span>淬煉 ${it.tempers | 0}/${it.temper_max | 0}</span>${pips}</div>
      <div class="shop-bigs">${big(w.repair, "修", "repair")}${big(w.temper, "淬煉", "temper")}</div>
      ${w.unfit ? `<p class="shop-note">${esc(w.unfit)}</p>` : ""}</div></div>`;
  }

  // 裝備庫（2.5；鐵匠鋪與合成流程 3.4 併進淬煉與修）：最上面身上那件的卡，底下「裝備庫 N／100」每件一列——勾選框、名字、一行數字、
  // 「換上」「修」「淬煉」「拆解」四顆（換上、拆解走修練頁的動作，修、淬煉走 /api/menxia/repair_item、temper_item，都不受店裡選單只列 8 顆的限制；
  // 修、淬煉這一件做不了時鈕灰掉、原因寫在鈕的小字，做得了寫用什麼料多少錢，全照伺服器那一列的 repair／temper）。原品、本命兵器的拆解灰掉寫原因、
  // 不給勾；等著定名的原品那一列底下一張定名表單；先列 8 件，其餘按「再列 N 件」。最底下「拆解勾選的 N 件」先問一次（一件一行拆成什麼）。
  // 四顆鈕在名字右邊排成二乘二（企劃者 2026-11-03 挑「乙 右邊二乘二」；320 寬放不下改排在名字底下，style.css）；小字都切成不折行的小段。字待 joy 潤
  const RACK_MELT_GO = "拆解勾選的 {n} 件"; // 待 joy 潤
  const RACK_PICK_ON = "挑幾件拆成素材"; // 待 joy 潤
  const RACK_PICK_OFF = "不拆了"; // 待 joy 潤
  const RACK_MELT_ASK = "拆掉這 {n} 件？拆了就沒了。"; // 待 joy 潤
  const RACK_MELT_LINE = "【{name}】→ {into} ×{count}"; // 待 joy 潤：確認框一件一行（素材與件數照伺服器那一列的 into）
  const RACK_MELT_TEMPERED = "（淬過 {n} 次一起沒了）"; // 待 joy 潤
  // 畫面上列得出來的那幾件：先列 8 件，按了「再列 N 件」才全列（換頁回來又收成 8 件）
  function rackShown(shop) {
    return S.shopMore ? shop.rack.rows : shop.rack.rows.slice(0, SHOP_RACK_LIST);
  }
  function rackPicks(shop) {
    const picked = S.rackPick || {};
    // 只送現在畫面上列著、拆得了的（輪詢之後不見了、成了原品的自動拿掉；收起「再列」、淬煉之後重排擠到 8 件以後的不算，件數跟畫面對得上）
    return rackShown(shop).filter((r) => r.into && picked[r.id]);
  }
  function rackRowHtml(shop, r) {
    const on = !!r.into && !!(S.rackPick || {})[r.id];
    // 那一行數字：這一頁就是淬煉的地方，淬煉幾次一律寫（「淬煉 0/7」看得出還能淬幾次；上限照這一件的品質，3.6），上品接「磨得慢」
    const temper = `・淬煉 ${r.tempers | 0}/${r.temper_max | 0}`, slow = r.wear_note ? `・${r.wear_note}` : "";
    const line = shop.page === "armor"
      ? `屬${r.attribute}・${r.grade}${temper}・${r.wear_word} ${r.edge | 0}${slow}・少扣 ${r.cut}`
      : `${r.noun || r.kind}・屬${r.attribute}・${r.grade}${temper}・鋒利度 ${r.edge | 0}${slow}${r.bonus ? `・威力 ${r.bonus}` : "・用不上"}`;
    const box = `<button type="button" class="rk-pick${on ? " on" : ""}" role="checkbox" aria-checked="${on}" aria-label="勾選【${esc(r.name)}】"${r.into ? ` data-act="rack-pick" data-id="${esc(r.id)}"` : " disabled"}></button>`;
    const note = (text) => (text ? `<small>${nbHtml(text)}</small>` : "");
    const work = (act, b, name) => `<button class="btn small rk-btn" data-act="${act}" data-id="${esc(r.id)}"${b.ok ? "" : ` disabled title="${esc(b.why || "")}"`}><b>${name}</b>${note(b.ok ? b.use : b.why)}</button>`;
    const wield = `<button class="btn small rk-btn" data-act="shop-wield" data-id="${esc(r.id)}"${r.wield_ok === false ? ` disabled title="${esc(r.wield_note || "")}"` : ""}><b>換上</b></button>`;
    const melt = r.keep
      ? `<button class="btn small ghost rk-btn" disabled><b>拆解</b>${note(r.keep)}</button>`
      : `<button class="btn small ghost rk-btn" data-act="shop-dismantle" data-id="${esc(r.id)}" data-confirm="${esc(r.confirm || "")}"><b>拆解</b></button>`;
    // 翻新（Joy 2026-11-10）：一件一張卡，平常只露名字與那一行數字，點了才攤開「換上／修／淬煉／拆解」（S.rackOpen，輪詢重畫不收）；
    // 勾選框只在「挑幾件拆」的時候露出來（S.rackPicking）。四顆鈕與勾選框都照舊畫在列上，攤不攤開、露不露由 class 決定
    const open = !S.rackPicking && S.rackOpen === r.id;
    const pct = r.temper && r.temper.ok && r.temper_pct != null && r.temper_pct < 100 ? TEMPER_PCT.replace("{pct}", r.temper_pct | 0) : "";
    const workT = pct ? work("rack-temper", { ...r.temper, use: `${r.temper.use || ""}${pct}` }, "淬煉") : work("rack-temper", r.temper, "淬煉");
    return `<div class="shop-row rk-row${on ? " on" : ""}${open ? " open" : ""}">${box}
        <button type="button" class="winfo" data-act="rack-open" data-id="${esc(r.id)}" aria-expanded="${open}">${wareMark(r.noun || r.kind)}<span class="wi-txt"><b>【${esc(r.name)}】${plusHtml(r.tempers)}</b><span>${nbHtml(line)}</span>${r.wield_ok === false ? `<small class="rwhy">${esc(r.wield_note || "")}</small>` : ""}</span><span class="wi-chev" aria-hidden="true">${open ? "▴" : "▾"}</span></button>
        <div class="rk-btns">${wield}${work("rack-repair", r.repair, "修")}${workT}${melt}</div>
      </div>${r.divine ? divineFormHtml(r.id, r.divine.pattern, true, r.divine.unit) : ""}`;
  }
  function rackHtml(shop) {
    const rows = shop.rack.rows;
    const worn = smithWornHtml(shop);
    if (!rows.length) return `${worn}<p class="shop-empty">裝備庫裡沒有這一欄的東西。</p>`; // 待 joy 潤
    const shown = rackShown(shop);
    const more = rows.length - shown.length;
    const n = rackPicks(shop).length;
    // 拆解改成「挑幾件」：平常最底下一顆淡框鈕，按了才露出勾選框與「拆解勾選的 N 件」（旁邊一顆取消）
    const go = !rows.some((r) => r.into) ? ""
      : S.rackPicking
        ? `<div class="rk-go${n ? " live" : ""}"><button class="btn ghost" data-act="rack-picking" data-on="">${RACK_PICK_OFF}</button><button class="btn primary" data-act="rack-melt"${n ? "" : " disabled"}>${RACK_MELT_GO.replace("{n}", n)}</button></div>`
        : `<div class="rk-go"><button class="btn ghost" data-act="rack-picking" data-on="1">${RACK_PICK_ON}</button></div>`;
    return `${worn}<h4 class="sm-sec rk-cap">裝備庫<small>${shop.rack.used | 0}／${shop.rack.cap | 0}</small></h4><div class="rk-list${S.rackPicking ? " picking" : ""}">${shown.map((r) => rackRowHtml(shop, r)).join("")}</div>
      ${more > 0 ? `<button class="btn small ghost shop-more" data-act="shop-more">再列 ${more} 件</button>` : ""}${go}`;
  }
  // 拆解勾選的：先問一次（ask），一件一行「【名字】→ 素材 ×1」、淬過的多寫幾次一起沒了（素材與淬煉次數照伺服器那一列，網頁不剖確認句）；
  // 確認鈕「拆掉」，送 dismantle_many（拆不了的伺服器跳過寫原因，回話是那一句總結）
  function rackMelt() {
    const shop = S.main && S.main.shop;
    if (!shop || shop.shop !== "smith") return;
    const picks = rackPicks(shop);
    if (!picks.length) return;
    const lines = picks.map((r) => RACK_MELT_LINE.replace("{name}", r.name).replace("{into}", r.into.name).replace("{count}", r.into.count | 0)
      + (r.tempers ? RACK_MELT_TEMPERED.replace("{n}", r.tempers | 0) : ""));
    ask(RACK_MELT_ASK.replace("{n}", picks.length), "拆掉", () => {
      S.rackPick = {}; S.rackPicking = false;
      return shopMx("dismantle_many", { items: picks.map((r) => r.id) });
    }, { lines });
  }
  function rackPick(id) {
    const picked = { ...(S.rackPick || {}) };
    if (picked[id]) delete picked[id];
    else picked[id] = true;
    S.rackPick = picked;
    renderShop();
  }

  // ── 神器頁（鐵匠鋪與合成流程 3.8，企劃者 2026-10-29 三張對比圖選丙；守正式季整合 5.10，企劃者「乙 守 5.10」）：輪替季才有（shop.divine）。
  // 上半「江湖已見」：這一季已經有人打出原品的一件一列（名字、原品在誰手上、全服仿品幾件、你有沒有），加上只有自己看得到的「鑄譜上有・尚無人打出」；
  // 一件都沒有時寫一句，不寫件數。下半收藏冊：內容裡每一件一格，有人打出過的寫名字（你有的亮、這一季打出的框粗），點了底下翻出神器譜那一行；
  // 從來沒人打出過的畫「？」、不可點、不帶任何資料（伺服器那一格的 id、name 本來就是 null）。網頁只畫伺服器給的，名單與件數一個字都不推。字待 joy 潤
  const DV_SEEN = "江湖已見"; // 待 joy 潤
  const DV_NONE = "這一季江湖上還沒有人打出神器的原品。"; // 待 joy 潤
  const DV_OWNER = "原品在{owner}手上・全服仿品 {copies} 件"; // 待 joy 潤（owner 是名號，原品在你手上時伺服器給「你」）
  const DV_MINE = { original: "原品在手", copy: "仿品在手" }; // 待 joy 潤
  const DV_NOT_MINE = "未有"; // 待 joy 潤
  const DV_SOLVED = "鑄譜上有・尚無人打出"; // 待 joy 潤
  const DV_ALBUM = "收藏 {have}／{total}"; // 待 joy 潤
  const DV_UNKNOWN = "？"; // 待 joy 潤
  const DV_LINK = "神器 江湖已見 {k} 件・收藏 {have}／{total} ›"; // 待 joy 潤：架上頁那一行（K 是這一季已打出原品的件數）
  const DV_LINK_ZERO = "神器 收藏 {have}／{total} ›"; // 待 joy 潤：K 是 0
  const DV_REF = "鑄|"; // 神器譜那一筆的 ref 是「鑄|配方 id」（伺服器的 GearFind.id）；tests/web/test_smith_divine_web.py 拿真的神器譜鎖著
  function divineAlbum(dv, tpl) {
    return tpl.replace("{have}", dv.collected.have | 0).replace("{total}", dv.collected.total | 0);
  }
  function divineLinkHtml(dv) {
    const k = dv.seen.filter((r) => !r.solved_only).length;
    return `<button class="dv-link" data-act="shop-tab" data-tab="divine">${divineAlbum(dv, k ? DV_LINK.replace("{k}", k) : DV_LINK_ZERO)}</button>`;
  }
  function divineSeenRow(r) {
    if (r.solved_only) return `<div class="dv-row solved"><b>【${esc(r.name)}】</b><small>${DV_SOLVED}</small></div>`;
    const owner = DV_OWNER.replace("{owner}", r.owner || "").replace("{copies}", r.copies | 0);
    return `<div class="dv-row${r.mine ? " mine" : ""}"><div class="dv-who"><b>【${esc(r.name)}】</b><small>${esc(owner)}</small></div><span class="dv-tag${r.mine ? " on" : ""}">${DV_MINE[r.mine] || DV_NOT_MINE}</span></div>`;
  }
  // 收藏冊一件一枚圓印（企劃者 2026-11-03 從三張對比圖挑「乙 圓印」，原本是寫名字的方格）。圓裡一行放三個字：四個字以上的名字
  // （玩家定名最多六個字）折成兩行、前一行多一個字，不縮字（店面字級下限 12px）；三個字以內一行
  function divineSealHtml(name) {
    const chars = [...String(name)];
    if (chars.length <= 3) return esc(name);
    const cut = Math.ceil(chars.length / 2);
    return `${esc(chars.slice(0, cut).join(""))}<br>${esc(chars.slice(cut).join(""))}`;
  }
  // 這一季打出的那一格是 dv-now，不是 now：江湖頁「剛剛」那張卡的 .now 沒加範圍、帶淡入動畫，格子掛上它每次重畫都淡入一次
  function divineCellHtml(cell) {
    if (!cell.forged || !cell.id || !cell.name) return `<span class="dv-cell unknown">${DV_UNKNOWN}</span>`;
    return `<button class="dv-cell${cell.have ? " have" : ""}${cell.now ? " dv-now" : ""}${S.divinePick === cell.id ? " on" : ""}" data-act="dv-cell" data-id="${esc(cell.id)}">${divineSealHtml(cell.name)}</button>`;
  }
  // 點著那一格在神器譜（見聞・榜單的那一張，/api/boards）裡的那一行：「第 N 季・劍・屬快・原品在甲手上」；還沒抓到、找不到是 null
  function divineBookLine(id) {
    const book = ((S.boards && S.boards.boards) || []).find((b) => b.id === "神器");
    const row = book && (book.book || []).find((r) => r.ref === DV_REF + id);
    return row ? `第 ${Number(row.season)} 季・${row.text}` : null;
  }
  function divineHtml(shop) {
    const dv = shop.divine;
    const seen = dv.seen.length ? `<div class="dv-seen">${dv.seen.map(divineSeenRow).join("")}</div>` : `<p class="shop-empty">${DV_NONE}</p>`;
    const line = S.divinePick ? divineBookLine(S.divinePick) : null;
    return `<h4 class="dv-h">${DV_SEEN}</h4>${seen}
      <h4 class="dv-h">${divineAlbum(dv, DV_ALBUM)}</h4><div class="dv-album">${dv.collected.cells.map(divineCellHtml).join("")}</div>
      ${line ? `<p class="dv-line">${esc(line)}</p>` : ""}`;
  }
  // 翻出的那一行畫在整本收藏冊底下：小螢幕（320×700、375×667）或江湖已見的列多了，那一行落在捲的那一層的底邊（分頁列頂上）以下，
  // 看起來點了沒反應。畫完量那一行的底跟捲的那一層的底，差多少往下捲多少、底下留一點空；本來就看得到的不動（審查 2026-11-01）
  const DV_LINE_ROOM = 8;
  function divineLineShow() {
    const body = document.querySelector(".shop-layer .shop-body");
    const line = body && body.querySelector ? body.querySelector(".dv-line") : null;
    if (!line) return;
    const below = line.getBoundingClientRect().bottom + DV_LINE_ROOM - body.getBoundingClientRect().bottom;
    if (below > 0) body.scrollTop += below;
  }
  // 點收藏冊的一格：翻出（再點收起）神器譜那一行。手上的榜單有那一筆先照它畫，再一律重抓一次神器譜照新的畫（伺服器那一張不快取）：
  // 手上那一份可能是之前在見聞→榜單抓的，之後別人又打了仿品，那一行的「仿品 N 把」就跟上面江湖已見那一列（輪詢的）對不上
  async function divinePick(id) {
    S.divinePick = S.divinePick === id ? null : id;
    renderShop();
    divineLineShow();
    if (!S.divinePick) return;
    try { await loadBoards(); } catch (e) { return; } // api() 提示過
    if (S.divinePick === id) { renderShop(); divineLineShow(); }
  }

  // 神器原品定名的表單（打造隱藏配方設計 5.2）：修練頁那一列底下、店面的出爐卡與裝備庫都用這一張。shop 為真時表單送店面的那一條
  // （data-op shop-name-divine、沿用譜名 shop-divine-keep），id 也分開，免得同一個畫面兩張撞 id。字待 joy 潤
  // unit：「這把／件／副神器」的量詞（FB-197），伺服器照 equipment.unit_for 給（修練頁與店面裝備庫那一列的 divine.unit、出爐卡的 unit），
  // 這裡不另寫一份對照；沒帶（舊的資料）照原本寫「把」
  function divineFormHtml(id, pattern, shop = false, unit = "") {
    const op = shop ? "shop-name-divine" : "name-divine";
    return `<form class="naming divine" id="${op}-${esc(id)}" data-op="${op}" data-id="${esc(id)}">
        <small>你打出了神器</small>
        <p>你是江湖上第一個打出這${esc(unit || "把")}神器的人，替它定一個名字（2～6 個字，全服不能重名）。</p>
        <div class="row"><input class="input" name="name" maxlength="6" placeholder="神器的名字"><button class="btn primary small" type="submit">定名</button></div>
        ${S.divineWhy[id] ? `<p class="form-why">${esc(S.divineWhy[id])}</p>` : ""}
        <button class="btn small ghost" type="button" data-act="${shop ? "shop-divine-keep" : "divine-keep"}" data-id="${esc(id)}">沿用譜名【${esc(pattern)}】</button>
      </form>`;
  }

  // 爐裡的東西（2.2）：換了兵器防具那一頁、或還沒放過，就從空爐、預設的種類開始
  function shopPotNow(shop) {
    const pot = S.shopPot;
    return pot && pot.slot === shop.page ? pot : { slot: shop.page, kind: shop.forge.kind, main: null, aux: null };
  }
  // 這一爐的說法：爐裡的東西問過伺服器了用那一份（同一頁、同一種類），不然是空爐那一份（shop.forge.line）。
  // 回應還沒回來（爐裡剛換了一樣）時手上那一份說的是上一爐：素材格照舊畫它的，「這一爐會怎樣」與開爐鈕當作還沒放好
  function shopLineNow(shop, pot) {
    const line = S.shopLine;
    const got = line && line.kind === pot.kind && pot.slot === shop.page ? line : shop.forge.line;
    return got.ready && (got.main !== pot.main || got.aux !== pot.aux) ? { ...got, ready: false } : got;
  }
  // 爐子中間的火（內嵌 SVG，水墨暖色；Joy 之後有正式的圖可以換）
  const FLAME_SVG = '<svg viewBox="0 0 60 60" aria-hidden="true"><path class="fl-out" d="M30 4 C40 18 50 26 46 40 C43 52 34 56 30 56 C24 56 14 50 14 38 C14 28 22 22 26 12 C28 20 31 24 34 26 C34 18 32 10 30 4Z"/><path class="fl-in" d="M30 24 C36 32 40 38 37 46 C35 51 32 52 30 52 C26 52 22 48 23 42 C24 36 28 32 30 24Z"/></svg>';
  // 看火候搬進打造頁（鐵匠鋪與合成流程 3.2，企劃者 2026-10-29 選「乙 點爐火、就地熬」）：爐子中間的火可以點，火上掛一枚小籤照
  // forge.furnace 寫（企劃者 2026-11-03 從三張對比圖挑「丙 火上一枚小籤」，原本是爐子底下一行＋「看」鈕）——還沒看寫價錢（金籤）、
  // 看過了還沒開爐（火畫旺）、今天用掉了、看不了（錢不夠、序章：照 silver.furnace_problem 的原因）。小籤放不下長原因：看不了的那幾種
  // 只寫幾個字、灰掉，點那一團火用提示泡泡講整句（同打造頁的灰格），讀螢幕的人聽整句（aria-label）。
  // 價錢、一天一次、下一爐用掉全照伺服器；跟打點帳簿那一格是同一個狀態。銀兩出口關著（furnace 是 None）小籤不畫、火不可點。字待 joy 潤
  const FURNACE_SAY = {
    open: "看火候 {price} 兩，今天還沒看。", // 待 joy 潤
    ready: "火候看過了，下一爐照新基準。", // 待 joy 潤
    used: "今天看過了，明日再來。", // 待 joy 潤
    no: "看火候 {price} 兩・{why}", // 待 joy 潤：看不了（原因照伺服器）
  };
  const FURNACE_TAG = { open: "看火候 {price} 兩", ready: "火候看過了", used: "明日再來" }; // 待 joy 潤：火上的小籤（看不了的寫 open 那幾個字、灰掉）
  function furnaceOk(fu) { return !!fu && !fu.ready && !fu.used_today && !fu.problem; }
  // 這一刻爐火的整句（點不下去時的提示泡泡、讀螢幕的人聽的）與小籤：[整句, 小籤的字, 小籤的 class]
  function furnaceWords(fu) {
    const price = String(fu.price | 0);
    if (fu.ready) return [FURNACE_SAY.ready, FURNACE_TAG.ready, " hot"];
    if (fu.used_today) return [FURNACE_SAY.used, FURNACE_TAG.used, " off"];
    const tag = FURNACE_TAG.open.replace("{price}", price);
    if (fu.problem) return [FURNACE_SAY.no.replace("{price}", price).replace("{why}", fu.problem), tag, " off"];
    return [FURNACE_SAY.open.replace("{price}", price), tag, ""];
  }
  function furnaceFireHtml(fu) {
    const [say, tag, cls] = furnaceWords(fu);
    return `<button class="flame fu-fire" data-act="shop-furnace" aria-label="${esc(say)}"${furnaceOk(fu) ? "" : ' aria-disabled="true"'} title="${esc(say)}">${FLAME_SVG}<span class="fu-tag${cls}">${esc(tag)}</span></button>`;
  }
  // 看（/api/do/<furnace.id>，MAIN_ACTIONS smith_furnace）：回來照新的畫面畫、話用提示泡泡講，再問一次這一爐（機率那一行換成新基準）。
  // 熬過的結果那一句收起：鐵匠那一句伺服器這一下換了新的，不能還被上一下的結果蓋著。看不了的只講整句、不送
  async function smithFurnace() {
    const shop = S.main && S.main.shop;
    const fu = shop && shop.forge ? shop.forge.furnace : null;
    if (!fu) return;
    if (!furnaceOk(fu)) { toast(furnaceWords(fu)[0]); return; }
    await busy(async () => {
      const r = await api(`/api/do/${fu.id}`, {});
      setMain(r.main);
      S.shopNote = null;
      renderKeepingShop();
      const said = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      if (said) toast(said);
    });
    await updateSmithLine();
  }

  // 打造頁（2.2）：上面一排種類（防具頁換成一行說明），中間爐子左右兩格（主料、輔料；點有東西的那一格拿出來），
  // 兩格放好時底下寫這一爐會怎樣（種類、屬性、階、工錢、三個機率、最多兩句原因、鑄譜上打中過的那一句）與開爐鈕，最底下是素材格。
  // 這一段的變數不用單字母 x（見 shelfHtml）
  function forgePageHtml(shop) {
    const f = shop.forge, pot = shopPotNow(shop), line = shopLineNow(shop, pot);
    const mats = new Map(f.materials.map((mat) => [mat.id, mat]));
    const slot = (role, id) => {
      const mat = id && mats.get(id);
      return `<button class="pot-slot ${role}" data-act="shop-slot" data-role="${role}" ${mat ? "" : "disabled"}><small>${role === "main" ? "主料" : "輔料"}</small>${mat
        ? `<b>${matIcon(mat.id, mat.attribute)}${esc(mat.name)}</b><small>${esc(mat.tier_word)}</small>` : "<span>點素材放進來</span>"}</button>`;
    };
    const kinds = f.kinds.length
      ? `<div class="shop-kinds">${f.kinds.map((k) => `<button class="kind${k.kind === pot.kind ? " on" : ""}${k.fit ? " fit" : ""}" data-act="shop-kind" data-kind="${esc(k.kind)}">${esc(k.label)}${k.fit ? "<sup>配</sup>" : ""}</button>`).join("")}</div>`
      : `<p class="shop-note">${esc(f.note)}</p>`;
    const out = line.ready ? `<div class="pot-out"><b>${esc(line.kind_label)}・屬${esc(line.attribute)}・${esc(line.tier)}</b><span>工錢 ${line.price | 0} 兩</span>
        ${line.head ? `<p class="pot-head">${esc(line.head)}</p>` : ""}
        ${line.odds ? `<div class="odds">${line.odds.filter((o) => o.pct > 0).map((o) => `<i class="q-${esc(o.q)}" style="width:${o.pct | 0}%"><span>${esc(o.q.slice(0, 1))} ${o.pct | 0}%</span></i>`).join("")}</div>` : ""}
        ${line.reasons.length ? `<p class="pot-why">${line.reasons.map(esc).join("、")}</p>` : ""}
        ${line.named_hint ? `<p class="pot-why">${esc(line.named_hint)}</p>` : ""}</div>` : "";
    const can = line.ready && !line.problem;
    // 整段字包在一個 span 裡（FB-297 複驗）：.btn 是不換行的橫向 flex，字與每一段折扣原因的小段各成一個 flex 項目時排成一列，
    // 兩段原因就把鈕撐出 375、字擠成直排、「鑄譜」被推出畫面；只有一個項目時字照常換行
    const go = `<button class="btn primary shop-go" data-act="shop-go"${can ? "" : " disabled"}><span>${dealHtml(line.ready ? line.problem || line.go : "開爐")}</span></button>`;
    // 素材格一屬性一排（企劃者 2026-10-14 微調）：伺服器已經照剛柔快慢、再照階排好，這裡只照屬性分排、排頭寫屬性。
    // 格子照背包現在的那一份（forge.materials）畫，這一爐的說法（line.cells）只拿來查放不放得進去：熬完、回應還沒回來時新的那一格照樣畫出來
    const rows = [], fits = new Map((line.cells || []).map((c) => [c.id, c]));
    for (const mat of f.materials) {
      const c = fits.get(mat.id) || { id: mat.id, ok: true, why: "" };
      const cell = `<button class="cell t${mat.tier | 0}${c.main || c.aux ? " used" : ""}${c.ok ? "" : " off"}" data-act="shop-cell" data-id="${esc(c.id)}" data-why="${esc(c.why || "")}">
        <span class="n">${mat.count | 0}</span><span class="nm">${matIcon(mat.id, mat.attribute)}${esc(mat.name)}</span><small>${esc(mat.tier_word)}</small>${c.ok ? "" : `<span class="why">${esc(c.why)}</span>`}</button>`;
      const last = rows[rows.length - 1];
      if (last && last.attribute === mat.attribute) last.cells.push([mat.tier | 0, cell]);
      else rows.push({ attribute: mat.attribute, cells: [[mat.tier | 0, cell]] });
    }
    const cells = rows.map((r) => brewRowHtml(shop, r)).join("");
    // 爐火（3.2）：銀兩出口開著（forge.furnace 有東西）時中間的火是一顆鈕、上面掛一枚小籤，看過了還沒開爐火畫旺；關著照舊是畫
    const fu = f.furnace;
    const fire = fu ? furnaceFireHtml(fu) : `<div class="flame">${FLAME_SVG}</div>`;
    return `${kinds}
      <div class="furnace${S.shopFiring ? " firing" : ""}${fu && fu.ready ? " hot" : ""}">${slot("main", pot.main)}${fire}${slot("aux", pot.aux)}</div>
      ${out}<div class="shop-gorow">${go}<button class="btn small ghost shop-book" data-act="book-open" data-book="forge">鑄譜</button></div>
      ${line.rack_full ? `<p class="shop-warn">${esc(line.rack_full)}</p>` : ""}
      <p class="shop-cap">背包的素材（點一下放進爐裡）</p><div class="cells${shop.four ? " four" : ""}">${cells || '<p class="shop-empty">背包裡沒有素材。</p>'}</div>`;
  }

  // 缺料的灰格（鐵匠鋪與合成流程 3.3，企劃者 2026-10-29 選「乙 點爐火、就地熬」）：素材格每一排補齊一階到三階（四階開著到四階）。背包沒有的
  // 那一階：一階畫「無」（沒有零換一，不可點）；二階以上照素材頁那一筆（shop.trade.upgrade，同屬性同階）畫「熬」＋要幾個低一階，按不下去的
  // 灰掉、格上寫素材頁同一句短原因（點了只說整句），按得下去的點了從畫面底下浮一張小單，熬送現成的 smith_upgrade（需求、工錢、上限、屬性機率
  // 全照素材頁）。升階關著（shop.trade 是 None，或只開收購、upgrade 是空的）一格都不畫，打造頁照舊；內容裡沒有那一階的素材（換不出來）不畫。
  // 灰格只說「這一格你沒有、怎麼熬」，不說熬了會打中什麼（企劃者 2026-10-10「不替玩家列出合得出來的組合」）。字待 joy 潤
  const SHOP_TIER = ["", "一階", "二階", "三階", "四階"];
  const BREW_NONE = "無"; // 待 joy 潤
  const BREW_WORD = "熬"; // 待 joy 潤
  function brewUps(shop) {
    const t = shop.trade;
    return t && (t.upgrade || []).length ? t.upgrade : null;
  }
  function brewOpen(attr, tier) { return !!S.shopBrew && S.shopBrew.attr === attr && S.shopBrew.tier === tier; }
  function brewCellHtml(up, attr, tier) {
    if (tier === 1) return `<div class="cell t1 brew none" aria-hidden="true"><span class="nm">${BREW_NONE}</span></div>`;
    if (!up) return "";
    return `<button class="cell t${tier} brew${up.problem ? " off" : ""}${brewOpen(attr, tier) ? " on" : ""}" data-act="shop-brew" data-attr="${esc(attr)}" data-tier="${tier}" data-why="${esc(up.problem || "")}">
        <span class="nm">${BREW_WORD}</span><small>${up.need | 0} 個${SHOP_TIER[tier - 1]}</small>${up.problem ? `<span class="why">${esc(up.short || up.problem)}</span>` : ""}</button>`; // 待 joy 潤：「3 個一階」
  }
  // 小單（企劃者 2026-11-03 從兩張對比圖挑「乙 從畫面底下浮一張」，原本是那一排底下展開）：同確認框那一層（ask）從畫面底下浮上來——
  // 「用 3 個一階剛熬一個二階剛，5 兩？」（工錢後面的折扣原因切成小段）、底下一行素材頁那一句機率（「五成出流雲絮，其餘隨機」）與
  // 上限字（二換三今天、三換四這一季）、「取消」「熬」
  function brewAskHtml(up) {
    return `用 ${up.need | 0} 個${SHOP_TIER[up.tier - 1]}${esc(up.attribute)}熬一個${SHOP_TIER[up.tier]}${esc(up.attribute)}，${up.cost | 0} 兩${dealHtml(up.cost_note || "")}？`; // 待 joy 潤
  }
  function brewOddsHtml(up) {
    return `${esc(up.odds || "")}${up.left_text ? `・<span class="nb">${esc(up.left_text)}</span>` : ""}`;
  }
  // 一排素材格（forgePageHtml 交過來的 {attribute, cells: [[階, 標記]]}）：升階開著時補齊灰格
  function brewRowHtml(shop, row) {
    const ups = brewUps(shop);
    let list = row.cells;
    if (ups) {
      const have = new Set(list.map(([t]) => t));
      for (let t = 1; t <= (shop.four ? 4 : 3); t += 1) {
        if (have.has(t)) continue;
        const up = t > 1 ? ups.find((u) => u.attribute === row.attribute && u.tier === t) : null;
        const html = brewCellHtml(up, row.attribute, t);
        if (html) list = [...list, [t, html]];
      }
      list = list.slice().sort((p, q) => p[0] - q[0]);
    }
    return `<div class="cell-row"><span class="row-attr ${SHOP_ATTR[row.attribute] || ""}">${esc(row.attribute)}</span>${list.map((pair) => pair[1]).join("")}</div>`;
  }
  // 點灰格：按不下去的只說原因；按得下去的那一格框起來、小單從畫面底下浮上來（按「熬」送小單問的那一筆），鐵匠那一句換回平常的
  function shopBrew(attr, tier, why) {
    if (why) { toast(why); return; }
    const shop = S.main && S.main.shop;
    const up = shop && (brewUps(shop) || []).find((u) => u.attribute === attr && u.tier === tier);
    if (!up || up.problem) return;
    S.shopBrew = { attr, tier };
    S.shopNote = null;
    renderShop();
    ask(brewAskHtml(up), BREW_WORD, () => smithBrew(up.attribute, up.tier), { rich: true, sub: brewOddsHtml(up) });
    brewCellShow();
  }
  // 小單蓋住點的那一格時（矮的螢幕點底下幾排：320×700 點柔的二階，那一格底 567、小單頂 521）：把捲的那一層往上推到那一格露在小單上面
  // （底下留一點空；推到底推不動就算了）。小單照它最後停的位置算（視窗高 − 小單高）：浮上來的動畫還在半路，量到的頂會偏低
  const BREW_ROOM = 8;
  function brewCellShow() {
    const body = document.querySelector(".shop-layer .shop-body");
    const cell = body && body.querySelector ? body.querySelector(".cell.brew.on") : null;
    const sheet = document.querySelector(".ask");
    if (!cell || !sheet) return;
    const below = cell.getBoundingClientRect().bottom + BREW_ROOM - (window.innerHeight - sheet.offsetHeight);
    if (below > 0) body.scrollTop += below;
  }
  // 小單收起（「取消」、旁邊的暗處、Esc）：那一格不再框著
  function brewShut() {
    if (!S.shopBrew) return;
    S.shopBrew = null;
    renderShop();
  }
  // 熬（同素材頁的升階，MAIN_ACTIONS smith_upgrade）：結果那一句（S.shopNote）在打造頁換掉鐵匠那一句，再問一次這一爐（素材格跟著變）。
  // 被拒（api() 提示過原因，shopDo 不重畫）：小單已經收了，那一格也收起框
  async function smithBrew(attribute, tier) {
    await shopDo("smith_upgrade", { attribute, tier }, () => { S.shopBrew = null; });
    brewShut();
    await updateSmithLine();
  }

  // 爐裡換了東西：先照放的畫一次，再問這一爐會怎樣（/api/smith_line；只用最後一次請求的回應）。熬過的結果那一句收起（鐵匠那一句換回來）
  async function setPot(change) {
    const shop = S.main && S.main.shop;
    if (!shop) return;
    S.shopNote = null;
    S.shopPot = { ...shopPotNow(shop), ...change, slot: shop.page };
    renderShop();
    await updateSmithLine();
  }
  // 點一格素材（2.2）：灰掉的只說原因（不放進去）；能放的照伺服器說的去處（主料格空著先放主料，否則放輔料；兩格都滿了換掉輔料）
  function shopCell(id, why) {
    if (why) { toast(why); return; }
    const shop = S.main && S.main.shop;
    if (!shop) return;
    const pot = shopPotNow(shop);
    // 放到哪一格照爐裡現在的樣子（主料空著先放主料），不照手上那一份說法：連點兩格時回應還沒回來，那一份還寫著「放主料」
    if ((shopLineNow(shop, pot).cells || []).some((c) => c.id === id)) setPot(pot.main ? { aux: id } : { main: id });
  }
  let smithLineSeq = 0;
  async function updateSmithLine() {
    const seq = ++smithLineSeq;
    const shop = S.main && S.main.shop;
    if (!shop) return;
    const pot = shopPotNow(shop);
    try {
      const r = await api("/api/smith_line", { kind: pot.kind, main: pot.main, aux: pot.aux });
      if (seq !== smithLineSeq || !S.main || !S.main.shop) return;
      S.shopLine = r;
      S.shopPot = { ...pot, main: r.main, aux: r.aux }; // 伺服器照現在的背包把放不下的拿掉（例：料在另一個分頁用掉了）
      renderShop();
    } catch (e) { /* api() 提示過 */ }
  }
  // ── 開爐與出爐（2.3）：品質在按下開爐那一刻由規則擲好，爐火與光只是演出 ──
  const FIRE_MS = 900; // 爐火竄一下的長度（等回應的同時跑；減少動態效果的人不等）

  const GLOW_HINT = { none: "布縫裡沒透出光", cyan: "布縫裡透出青光", gold: "布縫裡透出金光", purple: "布縫裡透出紫光", red: "布縫裡透出紅光", redgold: "布縫裡透出赤金光" }; // 待 joy 潤

  async function smithForge() {
    const shop = S.main && S.main.shop;
    if (!shop) return;
    const pot = shopPotNow(shop);
    if (!pot.main || !pot.aux) return;
    await busy(async () => {
      S.shopFiring = !reduceMotion();
      if (S.shopFiring) renderShop();
      const fire = S.shopFiring ? new Promise((ok) => setTimeout(ok, FIRE_MS)) : null;
      try {
        const r = await api("/api/do/smith_forge", { kind: pot.kind, main: pot.main, aux: pot.aux });
        if (fire) await fire;
        if (r.forged) {
          S.shopReveal = r.forged; S.shopOpened = false; // 鐵匠遞出一包麻布（掌櫃那一句在伺服器換成遞布那一句）
          S.shopPot = { ...pot, main: null, aux: null }; S.shopLine = null;
        }
        S.shopFiring = false;
        setMain(r.main);
        render();
        if (!r.forged) { // 被拒絕（2.3）：不遞布，原因用提示泡泡講，兩格照放著，再問一次這一爐（料可能在另一個分頁用掉了）
          const text = (r.message || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
          if (text) toast(text);
          updateSmithLine();
        }
      } finally { S.shopFiring = false; }
    }, WAIT_LINES.forge);
  }

  // 麻布與出爐卡（2.3）：先包著（光色照結果），點開是卡——名字、階品、種類屬性、加成或減損、配不配得上；首位發現多一個朱印；
  // 還等著定名的原品多一張定名表單（同修練頁那一張）；底下的鈕照那件去了哪裡：進了裝備庫是「換上」與「留在裝備庫」，在手上只有「收下」。
  // 名字照店面那一份（定了名之後是新名字）；淬煉上限與「磨得慢」也照那一列（鐵匠鋪與合成流程 3.6：上品 7 次、磨得慢）。這一段的變數不用單字母 x（見 shelfHtml）
  function revealHtml(card, shop) {
    if (!S.shopOpened) {
      return `<div class="reveal-layer"><button class="bundle g-${esc(card.glow)}" data-act="shop-unwrap" aria-label="點開麻布"><span>裹著麻布</span><small>${esc(GLOW_HINT[card.glow] || "")}</small></button><p class="tapme">點開看看</p></div>`;
    }
    const rows = [...(shop.rack.rows || []), ...(shop.worn.item ? [shop.worn.item] : [])];
    const now = rows.find((row) => row.id === card.id);
    const pending = (shop.pending || {})[card.id];
    const btns = card.where === "rack"
      ? `<button class="btn primary" data-act="shop-wield" data-id="${esc(card.id)}"${now && now.wield_ok === false ? ` disabled title="${esc(now.wield_note || "")}"` : ""}>換上</button><button class="btn" data-act="shop-keep">留在裝備庫</button>`
      : '<button class="btn primary" data-act="shop-keep">收下</button>';
    return `<div class="reveal-layer"><article class="forge-card g-${esc(card.glow)}">
        ${card.first ? '<span class="first-seal">首位發現</span>' : ""}
        <span class="q">${esc(card.grade)}</span><h4>${esc((now && now.name) || card.name)}</h4>
        <p class="meta">${esc(card.kind)}・屬${esc(card.attribute)}</p>
        ${now && now.temper_max ? `<p class="meta">淬煉 ${now.tempers | 0}/${now.temper_max | 0}${now.wear_note ? `・${esc(now.wear_note)}` : ""}</p>` : ""}
        ${card.value ? `<p class="stat">${esc(card.value)}</p>` : ""}${card.fit ? `<p class="fit">${esc(card.fit)}</p>` : ""}${(card.tactic || []).map((t) => `<p class="fit tactic">${esc(t)}</p>`).join("")}
        ${pending ? divineFormHtml(card.id, pending, true, card.unit) : ""}
        <div class="btns${card.where === "rack" ? "" : " one"}">${btns}</div></article></div>`;
  }
  async function smithyClick(act, el, ev) {
    switch (act) {
        case "divine-keep": await mx("name_divine", { weapon: el.dataset.id, keep: true }); break; // 神器原品沿用譜名（5.2）
        // 店面（店面獨立介面設計第二節）：換頁只在網頁上；換上、拆解、定名走修練頁的動作（shopMx）
        case "shop-tab": S.shopTab = el.dataset.tab; S.shopMore = false; S.shopNote = null; S.shopBrew = null; S.divinePick = null; renderShop(false); break;
        // 鐵匠鋪素材頁（素材與經濟 B6）：升一個（灰掉的只說原因）、賣一個、全賣（先問一次）
        case "trade-up": // 「全熬 ×N」多送 count（伺服器再夾一次，Config.economy.upgrade_batch）
          if (el.dataset.why) toast(el.dataset.why);
          else await shopDo("smith_upgrade", { attribute: el.dataset.attr, tier: Number(el.dataset.tier), ...(Number(el.dataset.n) > 1 ? { count: Number(el.dataset.n) } : {}) });
          break;
        case "trade-sell":
          if (el.dataset.confirm) ask(el.dataset.confirm, "賣掉", () => shopDo("smith_sell", { material: el.dataset.id, count: Number(el.dataset.n) }));
          else await shopDo("smith_sell", { material: el.dataset.id, count: Number(el.dataset.n) || 1 });
          break;
        case "shop-more": S.shopMore = true; renderShop(); break;
        case "trade-pick": S.tradePick = { ...(S.tradePick || {}), [el.dataset.attr]: Number(el.dataset.tier) }; renderShop(); break;
        case "trade-help": S.tradeHelp = !S.tradeHelp; renderShop(); break;
        case "shop-kind": setPot({ kind: el.dataset.kind }); break;
        case "shop-cell": shopCell(el.dataset.id, el.dataset.why); break;
        case "shop-brew": shopBrew(el.dataset.attr, Number(el.dataset.tier), el.dataset.why); break; // 打造頁的灰格（3.3）：點了從底下浮小單
        case "shop-slot": setPot(el.dataset.role === "main" ? { main: null, aux: null } : { aux: null }); break; // 拿掉主料，輔料跟著出來（伺服器也這樣修）
        case "shop-go": await smithForge(); break;
        case "shop-furnace": await smithFurnace(); break; // 打造頁的爐火（3.2）：看火候
        case "shop-unwrap": S.shopOpened = true; renderShop(); break; // 點開麻布（2.3）
        case "shop-keep": S.shopReveal = null; S.shopOpened = false; renderShop(); break; // 收下、留在裝備庫：收起出爐卡
        case "shop-wield":
          await shopMx("wield", { weapon: el.dataset.id });
          if (S.shopReveal && S.shopReveal.id === el.dataset.id) { S.shopReveal = null; S.shopOpened = false; renderShop(); } // 出爐卡上的「換上」：換好了卡收起
          break;
        case "shop-dismantle": ask(el.dataset.confirm || "把這一件拆成素材？拆掉就沒了。", "拆掉", () => shopMx("dismantle", { weapon: el.dataset.id })); break;
        // 裝備庫那一列的修、淬煉、勾選與批量拆解（鐵匠鋪與合成流程 3.4）：id 是裝備庫的「兵:N」「甲:N」，修淬完照舊留在裝備庫
        case "rack-repair": await shopMx("repair_item", { item: el.dataset.id }); break;
        case "rack-temper": await shopMx("temper_item", { item: el.dataset.id }); break;
        case "rack-pick": rackPick(el.dataset.id); break;
        case "rack-open": // 點一件：挑著拆的時候是勾選，平常是攤開／收起那一件的四顆鈕
          if (S.rackPicking) { const row = (S.main.shop.rack.rows || []).find((r) => r.id === el.dataset.id); if (row && row.into) rackPick(el.dataset.id); }
          else { S.rackOpen = S.rackOpen === el.dataset.id ? null : el.dataset.id; renderShop(); }
          break;
        case "rack-picking": S.rackPicking = !!el.dataset.on; S.rackPick = {}; renderShop(); break;
        case "rack-melt": rackMelt(); break;
        case "dv-cell": await divinePick(el.dataset.id); break; // 神器頁收藏冊的一格（3.8）：翻出神器譜那一行
        case "shop-divine-keep": await shopMx("name_divine", { weapon: el.dataset.id, keep: true }); break;
    } // smithyClick
  } // smithyClick
  registerClicks(smithyClick, ["divine-keep", "shop-tab", "trade-up", "trade-sell", "shop-more", "trade-pick", "trade-help", "shop-kind", "shop-cell", "shop-brew", "shop-slot", "shop-go", "shop-furnace", "shop-unwrap", "shop-keep", "shop-wield", "shop-dismantle", "rack-repair", "rack-temper", "rack-pick", "rack-open", "rack-picking", "rack-melt", "dv-cell", "shop-divine-keep"]);
  async function smithyForm(form, data) {
      if (form.dataset && form.dataset.op === "shop-name-divine") {
        // 店面上替神器原品定名（店面獨立介面設計 2.3、2.5）：同修練頁那一張；被拒了剛打的字放回去（id 帶冒號，用 getElementById）
        if (!data.name.trim()) { toast("先取個名字。"); return; }
        const said = await shopMx("name_divine", { weapon: form.dataset.id, name: data.name.trim() });
        if (document.getElementById("shop-name-divine-" + form.dataset.id)) { S.divineWhy[form.dataset.id] = said; renderShop(); } // 被拒的原因留在表單裡（FB-193）
        const again = document.getElementById("shop-name-divine-" + form.dataset.id)?.querySelector('input[name="name"]');
        if (again) again.value = data.name;
      } // smithyForm
  } // smithyForm
  registerForms(smithyForm, ["op:shop-name-divine"]);
