/* 天下大勢的網頁前端：鐵匠鋪重排（功能包 tianxia/features/tiepu/；Joy 2026-11-28 看示意稿說「開始寫」）。說明見 app.js 檔頭。
 *
 * 只換鐵匠鋪那一層的畫法：開關（main.tiepu）開著時，殼的 shopHtml 把鐵匠鋪交給 tpShopHtml。進門是一頁——
 * 圖頭（鋪子內景滿版、出店、銀兩、大字「鐵匠鋪」與朱印）、鐵匠那一句、眼下一張卡（該修了／配得上的那一件／能淬煉，鈕就在卡上）、
 * 五面牌（打造是寬牌、畫著爐口兩格；架上、裝備庫、素材、神器）。點一面牌從底下拉起那一塊，上面縮成一條圖。
 * 那一塊裡按的都是原本的鈕（choose、shop-slot、shop-go、rack-*、trade-*、dv-*……，smithy.js 認）：打造、素材、神器、裝備庫的列沿用 smithy.js 畫的，
 * 這裡只換外框與架上的貨卡、身上那件的卡（耐久、淬煉都畫長條，不畫小格子）。
 * 停在哪一塊沿用 S.shopTab（殼進出店時設回 "shelf"）：還是 "shelf" 就是進門那一頁，架上那一塊寫 "tp-shelf"（smithTab 不認得、當架上）。
 */
"use strict";

  const tpOn = () => !!(S.main && S.main.tiepu && S.main.tiepu.on);

  const TP_SIGN = "鐵匠鋪"; // 待 joy 潤
  const TP_SEAL = "鐵匠"; // 待 joy 潤：大字旁的朱印（直排兩字）
  const TP_SAYER = "老鐵匠"; // 待 joy 潤：那一句底下的落款
  const TP_LATER = "知道了"; // 待 joy 潤
  const TP_NAMES = { shelf: "架上", forge: "打造", rack: "裝備庫", trade: "素材", divine: "神器" }; // 待 joy 潤
  const TP_GLYPH = { shelf: "架", forge: "爐", rack: "庫", trade: "熬", divine: "神" }; // 牌上墨色大字
  const TP_CN = "〇一二三四五六七八九十";

  // 拉起的是哪一塊：null＝進門那一頁
  function tpSheetOf(shop) {
    if (!S.shopTab || S.shopTab === "shelf") return null;
    if (S.shopTab === "tp-shelf") return "shelf";
    const tab = smithTab(shop);
    return tab === "shelf" ? null : tab;
  }

  const tpPlace = (shop) => String(shop.sign || "").replace(TP_SIGN, "");
  const tpGlyph = (kind) => `<span class="tp-glyph" aria-hidden="true">${esc([...String(kind || "甲")][0])}</span>`;
  const tpSilver = (n) => `<span class="tp-silver"><em>銀</em>${(n | 0).toLocaleString("en-US")}</span>`;
  function tpMeter(label, now, max, low) {
    const w = max > 0 ? Math.max(0, Math.min(100, Math.round((now / max) * 100))) : 0;
    return `<div class="tp-meter"><span>${esc(label)}<b>${now | 0}／${max | 0}</b></span><i class="${low ? "low" : ""}" style="--w:${w}%"></i></div>`;
  }
  const tpTenths = (n) => (n >= 100 ? "滿的" : n < 10 ? "不到一成" : `${TP_CN[Math.floor(n / 10)]}成`);

  // 頁首：鋪子內景的圖；進門那一頁大，拉起一塊時縮成一條（點那一條也收起來）
  function tpHeroHtml(shop, mini) {
    const art = `<img class="xk-art" src="${GEAR_ART_DIR}scene-smithy.webp" alt="">`; // 圖就在 web/img/gear/（不等 gearArt 試載：圖頭第一次畫就要有圖）
    const top = `<div class="tp-top"><button class="tp-out" data-act="choose" data-id="${esc(shop.back)}">‹ 出店</button>${tpSilver(shop.silver)}</div>`;
    if (mini) return `<section class="xk-hero tp-hero mini">${art}${top}<button class="xk-dim" data-act="shop-tab" data-tab="shelf" aria-label="收起"></button></section>`;
    return `<section class="xk-hero tp-hero">${art}${top}
      <div class="tp-pl"><h1>${TP_SIGN}</h1><span class="tp-seal" aria-hidden="true">${[...TP_SEAL].join("<br>")}</span><small>${esc(tpPlace(shop))}</small></div></section>`;
  }

  // 鐵匠那一句：神器的規矩（金框）照舊畫在這裡；剛買成、修好的那一句也是伺服器換在 shop.line
  function tpSayHtml(shop) {
    if (shop.rule) return `<p class="tp-say rule">${esc(shop.rule)}<small>${TP_SAYER}</small></p>`;
    return shop.line ? `<p class="tp-say">${esc(shop.line)}<small>${TP_SAYER}</small></p>` : "";
  }

  // 眼下一張卡：只挑最要緊的一件，鈕在卡上。身上那件磨到一半以下→修；身上空著→架上配得上的那一件（買）或去架上挑；還能淬煉→淬煉
  function tpEye(shop) {
    const w = shop.worn || {}, it = w.item;
    if (it && w.repair && w.repair.enabled && (it.wear | 0) < 50) {
      return { key: `fix:${it.id}:${it.wear | 0}`, seal: "該修了", title: `${it.name}只剩${tpTenths(it.wear | 0)}`,
        obj: `${tpGlyph(it.name.slice(-1))}${tpMeter(it.wear_word, it.wear, 100, true)}`,
        btn: `修（${w.repair.use}）`, attrs: `data-act="choose" data-id="${esc(w.repair.id)}"` };
    }
    if (!it) {
      const fit = (shop.shelf || []).find((one) => one.fit && one.enabled);
      if (fit) {
        return { key: `buy:${fit.id}`, seal: "身上空著", title: `${fit.name}配得上你`,
          text: `${fit.kind}・屬${fit.attribute}・${fit.tier}${fit.value ? `，${fit.value}` : ""}。`,
          btn: `買 ${fit.price | 0} 兩`, attrs: `data-act="choose" data-id="${esc(fit.id)}"` };
      }
      if ((shop.shelf || []).length) {
        return { key: "shelf", seal: "身上空著", title: "先挑一件趁手的", text: w.empty || "",
          btn: "看架上", attrs: 'data-act="shop-tab" data-tab="tp-shelf"' };
      }
      return null;
    }
    if (w.temper && w.temper.enabled && (it.tempers | 0) < (it.temper_max | 0)) {
      const pct = it.temper_pct != null && it.temper_pct < 100 ? `・成功 ${it.temper_pct | 0}%` : "";
      return { key: `temper:${it.id}:${it.tempers | 0}`, seal: "能淬煉", title: `${it.name}還能再淬`,
        obj: `${tpGlyph(it.name.slice(-1))}${tpMeter("淬煉", it.tempers, it.temper_max, false)}`,
        btn: `淬煉（${w.temper.use}${pct}）`, attrs: `data-act="choose" data-id="${esc(w.temper.id)}"` };
    }
    return null;
  }
  function tpEyeHtml(shop) {
    const e = tpEye(shop);
    if (!e || S.tpLater === e.key) return "";
    return `<section class="xk-eye tp-eye" aria-label="眼下"><div class="xk-eye-hd"><span class="xk-seal">${esc(e.seal)}</span><h2>${esc(e.title)}</h2></div>
      ${e.obj ? `<div class="tp-eye-obj">${e.obj}</div>` : ""}${e.text ? `<p>${esc(e.text)}</p>` : ""}
      <div class="xk-eye-go"><button class="btn primary" ${e.attrs}>${esc(e.btn)}</button><button class="btn ghost" data-act="tp-later" data-key="${esc(e.key)}">${TP_LATER}</button></div></section>`;
  }

  // 五面牌底下那一行小字
  function tpPlaqueLine(k, shop) {
    if (k === "shelf") {
      const fit = (shop.shelf || []).filter((one) => one.fit).length;
      const low = Math.min(...(shop.shelf || []).map((one) => one.price | 0));
      const page = (shop.pages.find((p) => p.slot === shop.page) || {}).label || "";
      return [`${page} ${(shop.shelf || []).length} 件`, fit ? `${fit} 件配你的武學` : Number.isFinite(low) ? `${low} 兩起` : ""].filter(Boolean).join("・");
    }
    if (k === "rack") {
      const it = shop.worn && shop.worn.item;
      return `${it ? `身上${it.name}` : "身上空著"}・庫裡 ${shop.rack.used | 0}／${shop.rack.cap | 0}`;
    }
    if (k === "trade") {
      const ups = (shop.trade.upgrade || []).filter((r) => !r.problem);
      return ups.length ? `能熬 ${ups.length} 種` : "還沒有能熬的";
    }
    if (k === "divine") {
      const dv = shop.divine, seen = dv.seen.filter((r) => !r.solved_only).length;
      return `收藏 ${dv.collected.have | 0}／${dv.collected.total | 0}・${seen ? `江湖已見 ${seen} 件` : "江湖還沒人打出"}`;
    }
    return "";
  }

  // 打造那一面寬牌：兩格爐口（點著的主料、輔料；沒點寫怎麼放），右上背包裡幾個素材
  function tpForgePlaqueHtml(shop) {
    const f = shop.forge, pot = shopPotNow(shop);
    const mats = new Map(f.materials.map((m) => [m.id, m]));
    const total = f.materials.reduce((n, m) => n + (m.count | 0), 0);
    const cell = (id, empty) => {
      const m = id && mats.get(id);
      return m ? `<span class="on"><img class="mat-pic" src="${GEAR_ART_DIR}mat-${esc(m.id)}.webp" alt=""><b>${esc(m.name)}</b></span>` : `<span>${esc(empty)}</span>`;
    };
    return `<button class="xk-pl wide tp-forge-pl" data-act="shop-tab" data-tab="forge"><i aria-hidden="true">${TP_GLYPH.forge}</i><b>${TP_NAMES.forge}</b>
      <small class="tp-pltop">${total ? `背包素材 ${total} 個` : "背包還沒有素材"}</small>
      <span class="tp-fur">${cell(pot.main, total ? "主料・點素材放進來" : "主料・出門探索撿得到")}<em aria-hidden="true">🔥</em>${cell(pot.aux, "輔料")}</span></button>`;
  }

  function tpPlaquesHtml(shop) {
    const keys = ["shelf", "rack", ...(shop.trade ? ["trade"] : []), ...(shop.divine ? ["divine"] : [])];
    const tab = (k) => (k === "shelf" ? "tp-shelf" : k);
    const cells = keys.map((k) => `<button class="xk-pl" data-act="shop-tab" data-tab="${tab(k)}"><i aria-hidden="true">${TP_GLYPH[k]}</i><b>${TP_NAMES[k]}</b><small>${esc(tpPlaqueLine(k, shop))}</small></button>`).join("");
    return `<nav class="xk-pls two tp-pls" aria-label="${TP_SIGN}">${tpForgePlaqueHtml(shop)}${cells}</nav>`;
  }

  // 兵器／防具兩顆大印（架上、打造、裝備庫才有）：送原本的 smith:page:*
  function tpKindsHtml(shop) {
    if (shop.pages.length < 2) return "";
    return `<div class="tp-kinds">${shop.pages.map((p) => `<button class="tp-kind${p.slot === shop.page ? " on" : ""}"${p.slot === shop.page ? ' aria-pressed="true"' : ` data-act="choose" data-id="${esc(p.id)}"`}>${esc(p.label)}</button>`).join("")}</div>`;
  }

  // 架上：貨卡兩欄，一張卡一顆鈕（配得上的蓋「配」、朱框）
  function tpShelfHtml(shop) {
    if (!shop.shelf.length) return `<p class="tp-empty">架上這會兒空著。</p>`; // 待 joy 潤
    return `<div class="tp-wares">${shop.shelf.map((w) => `<button class="tp-ware${w.fit ? " hot" : ""}" data-act="choose" data-id="${esc(w.id)}"${w.enabled ? "" : " disabled"}>
        ${w.fit ? '<span class="xk-seal">配</span>' : ""}${tpGlyph(w.kind)}<b>${esc(w.name)}</b><small>${esc(w.kind)}・屬${esc(w.attribute)}・${esc(w.tier)}</small>
        ${w.value || w.note ? `<span class="fit">${esc([w.value, w.note].filter(Boolean).join("・"))}</span>` : ""}
        <span class="btn${w.fit && w.enabled ? " primary" : ""}">${w.enabled ? `買 ${w.price | 0} 兩` : esc(w.why)}</span></button>`).join("")}</div>`;
  }

  // 裝備庫最上面身上那件：耐久（鋒利）與淬煉都是長條；修、淬煉兩顆鈕送原本的選項 id
  function tpWornHtml(shop) {
    const w = shop.worn;
    if (!w.item) return `<p class="tp-empty">${esc(w.empty)}</p>`;
    const it = w.item;
    const lead = w.repair.enabled && (it.wear | 0) < 50 ? "repair" : "temper";
    const pct = w.temper.enabled && it.temper_pct != null && it.temper_pct < 100 ? `・成功 ${it.temper_pct | 0}%` : "";
    const big = (b, name, key) => `<button class="btn${lead === key && b.enabled ? " primary" : ""}" data-act="choose" data-id="${esc(b.id)}"${b.enabled ? "" : " disabled"}>${name}<small>${esc(b.enabled ? b.use : b.why)}${key === "temper" ? pct : ""}</small></button>`;
    return `<div class="tp-wcard${(it.wear | 0) < 50 ? " hot" : ""}"><h4><span class="xk-seal">身上</span>${esc(it.name)}${plusHtml(it.tempers)}<small>${esc(it.grade)}${it.wear_note ? `・${esc(it.wear_note)}` : ""}</small></h4>
      <div class="tp-eye-obj">${tpGlyph(it.name.slice(-1))}<div class="tp-meters">${tpMeter(it.wear_word, it.wear, 100, (it.wear | 0) < 50)}${tpMeter("淬煉", it.tempers, it.temper_max, false)}</div></div>
      <div class="tp-wgo">${big(w.repair, "修", "repair")}${big(w.temper, "淬煉", "temper")}</div>
      ${w.unfit ? `<p class="tp-note">${esc(w.unfit)}</p>` : ""}</div>`;
  }

  function tpSheetSub(k, shop) {
    const page = (shop.pages.find((p) => p.slot === shop.page) || {}).label || "";
    if (k === "rack") return `庫裡 ${shop.rack.used | 0}／${shop.rack.cap | 0}`;
    if (k === "divine") return `收藏 ${shop.divine.collected.have | 0}／${shop.divine.collected.total | 0}`;
    if (k === "trade") return "三個換一個高一階的"; // 待 joy 潤
    return k === "shelf" ? tpPlace(shop) + TP_SIGN : page;
  }

  function tpSheetHtml(shop, k) {
    // 打造那一塊就地熬了一個：那一句換成結果句（同 shopHtml 的 brewed）
    const said = k === "forge" && S.shopNote ? `<p class="tp-said brewed" role="status">${esc(S.shopNote)}</p>`
      : shop.line && shop.line !== S.tpLine ? `<p class="tp-said">${esc(shop.line)}</p>` : ""; // 只寫鐵匠回的話（買成、修好、為什麼不成）：進門那一句不再寫一次
    const kinds = k === "trade" || k === "divine" ? "" : tpKindsHtml(shop);
    const body = k === "shelf" ? tpShelfHtml(shop)
      : k === "rack" ? rackHtml(shop).replace(smithWornHtml(shop), tpWornHtml(shop))
      : k === "forge" ? forgePageHtml(shop) : k === "trade" ? tradeHtml(shop) : divineHtml(shop);
    return `<section class="xk-sheet tp-sheet tp-sh-${k}"><div class="xk-grip"></div>
      <div class="xk-sh"><h2>${TP_NAMES[k]}</h2><span class="xk-sh-sub">${esc(tpSheetSub(k, shop))}</span><button class="xk-x" data-act="shop-tab" data-tab="shelf" aria-label="收起">✕</button></div>
      ${said}${kinds}${body}</section>`;
  }

  // 殼的 shopHtml 開著時交過來：整層照舊是 .shop-layer.shop-smith、捲的那一層照舊是 .shop-body（renderShop、捲到哪裡照放回去都照舊）
  function tpShopHtml(shop) {
    const k = tpSheetOf(shop);
    if (!k) S.tpLine = shop.line; // 進門那一頁那一句：拉起的那一塊只寫跟它不一樣的（剛做完的事）
    const inner = k ? tpHeroHtml(shop, true) + tpSheetHtml(shop, k)
      : tpHeroHtml(shop, false) + tpSayHtml(shop) + tpEyeHtml(shop) + tpPlaquesHtml(shop);
    return `<div class="shop-layer shop-smith tp" role="dialog" aria-label="${esc(shop.sign)}">
      <div class="shop-body tp-body"><div class="shop-col"><div class="tp-page">${inner}</div></div></div>
      ${S.shopReveal ? revealHtml(S.shopReveal, shop) : ""}</div>`;
  }

  async function tiepuClick(act, el, ev) {
    switch (act) {
        case "tp-later": S.tpLater = el.dataset.key; renderShop(); break; // 眼下卡的「知道了」：這一件這個數字先不提
    } // tiepuClick
  } // tiepuClick
  registerClicks(tiepuClick, ["tp-later"]);
