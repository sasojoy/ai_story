/* 天下大勢的網頁前端：萬寶閣重排（功能包 tianxia/features/wanbao/；Joy 2026-11-28 看示意稿說「開始寫」）。說明見 app.js 檔頭。
 *
 * 只換商城那一層的畫法：開關（main.wanbao）開著時，殼的 shopHtml 把萬寶閣交給 wbShopHtml。進門是一頁——
 * 頂上出店與錢袋（元寶拆兩種時金錠元寶、銀錠五銖，點了看紀錄）、圖頭（櫃上三件鎮店之寶、兩盞燈籠、大字「萬寶閣」與朱印）、掌櫃那一句、
 * 眼下一張卡（月卡今天的份還沒領→領；丹用完了→買，鈕就在卡上）、五面牌（月卡是寬牌、畫還剩幾天的長條；丹藥、江湖帖、列傳、形象）。
 * 點一面牌從底下拉起那一塊。貨一件一張大卡、圖當主角，整張是一顆鈕，按下去照舊走 mall-pick（mall.js 的購買確認）；
 * 只收儲值元寶的蓋「儲」。形象、紀錄那兩塊沿用 looks.js、mall.js 畫的（S.mallTab 照舊是 look／log）。
 * 拉起的是哪一類記在 S.wbCat（月卡、丹藥、江湖帖、列傳）；出店（wb-out）一併收起。資料都是 /api/mall、/api/mall/records、/api/looks 原本就有的。
 */
"use strict";

  const wbOn = () => !!(S.main && S.main.wanbao && S.main.wanbao.on);

  const WB_SAYER = "掌櫃"; // 待 joy 潤：那一句底下的落款
  const WB_SEAL = "寶號"; // 待 joy 潤：大字旁的朱印（直排兩字）
  const WB_LATER = "知道了"; // 待 joy 潤
  const WB_CATS = { card: "月卡", dan: "丹藥", tie: "江湖帖", zhuan: "列傳" }; // 待 joy 潤
  const WB_PIC = { card: "card_30", dan: "pills_5", tie: "rename", zhuan: "rewrite_zhuan" }; // 牌上的圖（web/img/mall/）
  const WB_SHELF = ["pills_30", "card_30", "legend_1"]; // 圖頭櫃上那三件
  const WB_CARD_DAYS = 30; // 月卡一張幾天：寬牌那一條長條的分母（伺服器的 card.left 是連今天還剩幾天）
  const WB_LOOK_LINE = "擂台上穿哪一套"; // 待 joy 潤：形象那面牌的小字

  const wbImg = (id) => `/static/img/mall/${esc(id)}.webp`;

  // 這一件付哪一種：只收儲值的蓋「儲」、金錠；拆成兩種時其餘先扣五銖、畫銀錠；沒拆一律金錠
  function wbPrice(it, coins) {
    const ingot = it.paid || !coins ? ingotSvg() : giftSvg();
    return `${ingot}${it.price | 0}${paidSeal(it)}`;
  }

  // 頂上：出店（一併收起拉起的那一塊）、錢袋（點了看紀錄）
  function wbTopHtml(shop) {
    const c = shop.coins;
    const purse = c
      ? `<button class="mb-purse" data-act="mall-tab" data-tab="log" aria-label="元寶 ${c.paid | 0}，${esc(giftName(c))} ${c.gift | 0}，看紀錄"><span>${ingotSvg()}${c.paid | 0}<small>元寶</small></span><span>${giftSvg()}${c.gift | 0}<small>${esc(giftName(c))}</small></span></button>`
      : `<button class="mb-purse" data-act="mall-tab" data-tab="log" aria-label="元寶 ${shop.balance | 0}，看紀錄"><span>${ingotSvg()}${shop.balance | 0}<small>元寶</small></span></button>`;
    return `<div class="mb-top"><button class="mb-out" data-act="wb-out">‹ 出店</button>${purse}</div>`;
  }

  function wbHeroHtml(shop) {
    return `${wbTopHtml(shop)}<section class="mb-hero"><span class="lantern l" aria-hidden="true"></span><span class="lantern r" aria-hidden="true"></span>
      <div class="shelf" aria-hidden="true">${WB_SHELF.map((id) => `<img src="${wbImg(id)}" alt="">`).join("")}</div>
      <div class="mb-name"><h1>${esc(MALL_SIGN)}</h1><span class="seal" aria-hidden="true">${[...WB_SEAL].join("<br>")}</span><small>${esc(MALL_MOTTO)}</small></div></section>`;
  }

  // 掌櫃那一句：剛買成的、買不了的原因（S.mallSay）蓋過平常那一句
  function wbSayHtml(shop) {
    if (!shop.line) return "";
    return `<p class="mb-say${shop.said ? ` ${esc(shop.said)}` : ""}">「${nbHtml(shop.line, MALL_SAY_AFTER)}」<small>${WB_SAYER}</small></p>`;
  }

  // 眼下一張卡：月卡今天的份還沒領→領（鈕在卡上）；手上沒丹了→買最便宜的那一件丹
  function wbEye(d) {
    const today = d.card && d.card.daily;
    if (today && !today.claimed) {
      return { key: `daily:${d.card.until}`, k: "今天的", title: "月卡的份還沒領", pic: "card_30",
        text: `${dailyWhat(today)}，今天上線就能領；月卡還剩 ${d.card.left | 0} 天。`, btn: "領今天的份", attrs: 'data-act="mall-claim"' };
    }
    const p = d.pills;
    if (p && (p.count | 0) === 0) {
      const pill = d.items.filter((it) => it.can && mallCat(it) === "dan" && (it.gives || {}).pills).sort((a, b) => (a.price | 0) - (b.price | 0))[0];
      if (pill) {
        return { key: `pill:${d.balance}`, k: "手上沒丹", title: `${p.name}用完了`, pic: pill.id,
          text: `${pill.name}${pill.effects ? `：${pill.effects}` : ""}。`, btn: `買 ${pill.price | 0}`, attrs: `data-act="mall-pick" data-id="${esc(pill.id)}"`, price: pill };
      }
    }
    return null;
  }
  function wbEyeHtml(d, coins) {
    const e = wbEye(d);
    if (!e || S.wbLater === e.key) return "";
    const btn = e.price ? wbPrice(e.price, coins) : esc(e.btn);
    return `<section class="mb-eye" aria-label="眼下"><div class="mb-eye-hd"><span class="mb-k">${esc(e.k)}</span><h2>${esc(e.title)}</h2></div>
      <div class="mb-eye-obj"><img src="${wbImg(e.pic)}" alt=""><p>${esc(e.text)}</p></div>
      <div class="mb-go"><button class="mb-btn gold" ${e.attrs}>${btn}</button><button class="mb-btn" data-act="wb-later" data-key="${esc(e.key)}">${WB_LATER}</button></div></section>`;
  }

  // 五面牌底下那一行
  function wbPlaqueLine(k, d, list) {
    const p = d.pills;
    if (k === "dan") return `${p.name} ${p.count | 0} 顆・${p.today == null ? "每天不限" : `今天還能服 ${p.today | 0}`}`;
    if (k === "tie") return list.slice(0, 3).map((it) => it.name).join("・");
    if (k === "zhuan") return list[0] && list[0].limit ? list[0].limit : MALL_CAT_NOTE.zhuan();
    return "";
  }
  // 月卡寬牌：有效時還剩幾天的長條（不畫小圓圈），沒開寫價錢
  function wbCardPlaqueHtml(d, list, coins) {
    const card = d.card, it = list[0];
    const days = card
      ? `<div class="mb-days"><span><span>還剩 <b>${card.left | 0} 天</b></span><b>到 ${esc(card.until)}</b></span><i style="--w:${Math.max(4, Math.min(100, Math.round(((card.left | 0) / WB_CARD_DAYS) * 100)))}%"></i></div>`
      : `<div class="mb-days"><span>還沒開<b>${it ? wbPrice(it, coins) : ""}</b></span></div>`;
    return `<button class="mb-pl wide" data-act="wb-cat" data-cat="card"><img src="${wbImg(WB_PIC.card)}" alt=""><b>${WB_CATS.card}</b>${days}</button>`;
  }
  function wbPlaquesHtml(d, coins) {
    const items = d.items.filter((it) => it.kind !== "look");
    const by = (k) => items.filter((it) => mallCat(it) === k);
    const cells = ["dan", "tie", "zhuan"].filter((k) => by(k).length)
      .map((k) => `<button class="mb-pl" data-act="wb-cat" data-cat="${k}"><img src="${wbImg(WB_PIC[k])}" alt=""><b>${WB_CATS[k]}</b><small>${esc(wbPlaqueLine(k, d, by(k)))}</small></button>`).join("");
    const looks = d.looks ? `<button class="mb-pl" data-act="mall-tab" data-tab="look"><img class="sprite" src="${esc(LOOK_IMG((S.main && S.main.look) || ""))}" alt=""><b>形象</b><small>${WB_LOOK_LINE}</small></button>` : "";
    const empty = items.length || looks ? "" : `<p class="mb-note">${esc(MALL_SAY.empty)}</p>`;
    return `<nav class="mb-pls" aria-label="${esc(MALL_SIGN)}">${by("card").length ? wbCardPlaqueHtml(d, by("card"), coins) : ""}${cells}${looks}</nav>${empty}
      ${d.grant > 0 ? `<p class="mb-note">${nbHtml(MALL_NOTE.replace("{n}", String(d.grant | 0)), MALL_NB)}</p>` : ""}`;
  }

  // 一件一張大卡：圖當主角，名字、給什麼、限購，最底一條金色價錢（整張是一顆鈕，價錢那一條只是長得像鈕）；月卡多一排好處
  function wbWareHtml(it, coins) {
    const pic = MALL_PICS.has(it.id) ? `<img src="${wbImg(it.id)}" alt="" loading="lazy">` : `<span class="mb-art"><svg viewBox="0 0 80 80" aria-hidden="true">${MALL_ART[it.id] || MALL_ART[MALL_ART_CAT[mallCat(it)]]}</svg></span>`;
    const perks = (it.perks || []).length ? `<span class="mb-perks">${it.perks.map((t) => `<span>${nbHtml(t, MALL_NB)}</span>`).join("")}</span>` : "";
    const sub = [it.effects, it.limit].filter(Boolean).map((t) => nbHtml(t, MALL_NB)).join("<br>");
    return `<button class="mb-ware${it.kind === "card" ? " big" : ""}${it.can ? "" : " off"}${S.mallPick === it.id ? " on" : ""}" data-act="mall-pick" data-id="${esc(it.id)}"${it.can ? "" : ' aria-disabled="true"'}>
        ${pic}<span class="mb-wt"><b>${esc(it.name)}</b>${sub ? `<span class="mb-sub">${sub}</span>` : ""}${!perks && it.kind === "card" && it.note ? `<span class="mb-sub">${nbHtml(it.note, MALL_NB)}</span>` : ""}${perks}
        <span class="mb-btn gold">${wbPrice(it, coins)}</span></span></button>`;
  }

  // 拉起的那一塊小標底下那一句（丹藥：一顆回多少；月卡：到哪天）
  function wbSub(k, d) {
    if (k === "dan") return MALL_CAT_NOTE.dan(d.pills).replace(/<[^>]+>/g, "");
    if (k === "zhuan") return MALL_CAT_NOTE.zhuan();
    if (k === "card") return d.card ? `到 ${d.card.until}` : "還沒開";
    return "";
  }

  function wbSheetHtml(shop, k, title, sub, body) {
    const said = S.mallSay && shop.line ? `<p class="mb-said ${esc(shop.said)}" role="status">${nbHtml(shop.line, MALL_SAY_AFTER)}</p>` : "";
    return `<div class="mb-mini">${wbTopHtml(shop)}<button class="mb-dim" data-act="wb-close" aria-label="收起"></button></div>
      <section class="mb-sheet mb-sh-${esc(k)}"><div class="mb-grip"></div><div class="mb-sh"><h2>${esc(title)}</h2><span>${esc(sub)}</span><button class="mb-x" data-act="wb-close" aria-label="收起">✕</button></div>
      ${said}${body}</section>`;
  }

  function wbBodyHtml(shop) {
    const d = S.mallData, coins = shop.coins;
    if (shop.tab === "log") return wbSheetHtml(shop, "log", "紀錄", MALL_SAY.log, `<div class="mall-body">${mallLogHtml(S.mallLog)}</div>`);
    if (shop.tab === "look") return wbSheetHtml(shop, "look", "形象", MALL_SAY.look, `<div class="mall-body">${mallLooksHtml(S.mallLooks)}</div>`);
    const k = S.wbCat && d && WB_CATS[S.wbCat] ? S.wbCat : null;
    if (k) {
      const list = d.items.filter((it) => it.kind !== "look" && mallCat(it) === k);
      const pill = k === "dan" ? `<p class="mb-note">身上 ${d.pills.count | 0} 顆${d.pills.today == null ? "" : `，今天還能服 ${d.pills.today | 0} 顆`}。${mallDailyHtml(d.card)}</p>` : "";
      return wbSheetHtml(shop, k, WB_CATS[k], wbSub(k, d), pill + list.map((it) => wbWareHtml(it, coins)).join(""));
    }
    if (!d) return wbHeroHtml(shop) + wbSayHtml(shop) + mallFailHtml();
    return wbHeroHtml(shop) + wbSayHtml(shop) + wbEyeHtml(d, coins) + wbPlaquesHtml(d, coins);
  }

  // 殼的 shopHtml 開著時交過來：整層照舊是 .shop-layer.shop-mall、捲的那一層照舊是 .shop-body（renderMall、捲到哪裡照放回去都照舊）
  function wbShopHtml(shop) {
    return `<div class="shop-layer shop-mall wb" role="dialog" aria-label="${esc(shop.sign)}">
      <div class="shop-body wb-body"><div class="shop-col"><div class="mb">${wbBodyHtml(shop)}</div></div></div></div>`;
  }

  async function wanbaoClick(act, el, ev) {
    switch (act) {
        case "wb-cat": S.wbCat = el.dataset.cat; S.mallPick = null; S.mallSay = null; renderMall(false); break; // 拉起那一類
        case "wb-close": // 收回進門那一頁：形象、紀錄那兩塊照舊回貨架
          S.wbCat = null;
          if (S.mallTab !== "shelf") await mallTabTo("shelf");
          else { S.mallPick = null; S.mallSay = null; renderMall(false); }
          break;
        case "wb-out": S.wbCat = null; closeMall(); break; // 出店：一併忘掉拉起的那一類，下次進門從頭
        case "wb-later": S.wbLater = el.dataset.key; renderMall(); break; // 眼下卡的「知道了」
    } // wanbaoClick
  } // wanbaoClick
  registerClicks(wanbaoClick, ["wb-cat", "wb-close", "wb-out", "wb-later"]);
