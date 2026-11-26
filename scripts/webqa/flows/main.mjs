// The main walk: the gate, the opening, week 1 and 2, every shop, the fight, the season's end. Wave B's first round.
import { CH, CHP, ACT, place, UI, ACCOUNTS, accounts, rich, SHEET, EYE, DUTY, stepVia, openLetter } from "./common.mjs";

export { ACCOUNTS };
async function enterShop(c, pre, loc, act) {
  await place(c, "沈浪", loc);
  await c.load("/");
  const r = await c.step(CH(act), pre, { who: "p1" });
  if (r !== "ok") { await c.api("p1", "/api/choose", { id: act }); await c.load("/"); await c.shoot(pre, { who: "p1" }); }
}
async function leave(c, pre, backId) {
  const r = await c.step(".shop-layer .shop-back", `${pre}_left`, { light: true });
  if (r !== "ok") { await c.api("p1", "/api/choose", { id: backId }); await c.load("/"); }
}
const SHOP_UI = [...UI, "shop-kind", "shop-slot", "shop-cell", "dn-cell", "tav-name", "rack-pick", "shop-horse", "arena-seen", "board-close"];
export const flows = [
  ["gate", async (c) => {
    await c.dropCookie();
    await c.load("/");
    await c.shoot("gate");
    await c.crawl("gate", () => c.load("/"), ["gate"], { total: 4 });
  }],
  accounts,
  ["prep", async (c) => {
    await c.asPlayer("p3");
    // batch 113: the first page in the game carries Joy's 改版資訊 sheet (.sheet.patch-pop, web/news.js patchPopHtml). driver load() closes
    // only story-ok and the check-in sheet, so the pop stayed over the lower half of every page until the sense pad closed it (128 of 237
    // main scenes in batch 113's walk), and its .sheet kept body.layer-open on under the figure layer. Take it once, then close it like a
    // player: 知道了 remembers it in this browser's localStorage, so it stays closed for the rest of the round
    // It is also the browser's first page in the game: the web fonts' glyph subsets (fonts.googleapis.com, unicode-range) were still
    // arriving for one of four walks' 1280 picture (a 36-level difference along one line). Load the page once more, from cache, before it
    // batch 233: since #247 the 江湖新事 invite (.sheet.nx-invite, web/news.js) comes first, over the 改版資訊 sheet. A player opens it
    // (去看看 remembers it in localStorage, nxMarkSeen), reads the page and closes it; then the patch sheet shows as before
    // batch 260: that put the invite before the reload above, and batch 113's trouble came back on nx_invite: both 1280 pictures, 456 px,
    // 36 levels, in the scene card behind the invite. Not the fonts (the same glyphs): 潁川 drawn with LCD anti-aliasing on one load and
    // grayscale on another, which the page's compositing layers decide when it loads, and no repaint changes it after. Load once more,
    // from cache, before the invite too (it stays until 去看看): A against A went from red 5 runs in 16 to 0 in 11.
    await c.load("/");
    if (await c.ev(`!!document.querySelector(".sheet.nx-invite")`)) {
      await c.settle(600);
      await c.shoot("nx_invite", { who: "p3" });
      await c.click('.sheet.nx-invite [data-act="nx-open"]');
      await c.settle(600);
      await c.shoot("nx_page", { who: "p3" });
      await c.click('[data-act="nx-close"]');
      await c.settle(400);
      await c.load("/");
    }
    if (await c.ev(`!!document.querySelector(".sheet.patch-pop")`)) await c.load("/");
    if (await c.ev(`!!document.querySelector(".sheet.patch-pop")`)) {
      await c.settle(600);
      await c.shoot("patch_pop", { who: "p3" });
      await c.click('.sheet.patch-pop [data-act="patch-close"]');
      await c.settle(260);
    }
    await c.shoot("prep_growth", { who: "p3" });
    await c.crawl("prep", () => c.load("/"), ["prep-pick", "growth-custom", "growth-step"], { total: 6 });
  }],
  ["opening", async (c) => {
    await c.asPlayer("p4");
    await c.step('[data-act="prep-pick"][data-preset="balanced"]', "opening_picked");
    await c.step('[data-act="prep-growth"]', "opening_event", { who: "p4" });
    await c.step('[data-act="choose"][data-id="choice:2"]', "opening_after", { who: "p4" });
    await c.crawl("newbie", () => c.load("/"), UI, { total: 16, cap: 2 });
    await c.load("/");
    await c.step('[data-act="newbie-go"]', "newbie_go", { who: "p4" });
    await c.load("/");
    await c.step('[data-act="guide-ack"]', "newbie_guide_ack");
  }],
  rich,
  ["week1", async (c) => {
    await c.asPlayer("p1");
    await c.shoot("j_week1", { who: "p1" });
    await c.crawl("j1", () => c.load("/"), UI, { total: 30, cap: 3 });
    await c.load("/");
    // batch 272: the new 江湖頁 pulls the whole letter up (jh-sheet letter, web/jianghu.js jhSheetHtml) and asks about phone
    // notices only there, under the letter. 收起 (letter-read) is not pressed here: on the old page this click only folded the letter
    // that comes open (letter-read was never there), so the letter stayed for call's letter_open and notify's ask; it still has to
    await openLetter(c, "j1_letter_toggle", { light: true });
    await c.step('[data-act="push-no"]', "j1_push_no", { who: "p1" });
    await c.load("/");
    await c.shoot("j1_clean", { who: "p1" });
    const prac = async () => { await c.load("/"); await c.tab("practice"); };
    await prac();
    await c.shoot("practice", { who: "p1" });
    await c.crawl("pr", prac, UI, { depth: 2, total: 60, cap: 3 });
    const craft = async () => { await prac(); await c.click('[data-act="tab"][data-tab="craft"]'); };
    await craft();
    await c.shoot("craft", { who: "p1" });
    await c.crawl("cr", craft, UI, { depth: 2, total: 30, cap: 3 });
    const map = async () => { await c.load("/"); await c.tab("map"); };
    await map();
    await c.shoot("map", { who: "p1" });
    await c.crawl("map", map, UI, { depth: 2, total: 40, cap: 3 });
    const news = async () => { await c.load("/"); await c.tab("news"); };
    await news();
    await c.shoot("news", { who: "p1" });
    await c.crawl("news", news, UI, { depth: 2, total: 40, cap: 3 });
  }],
    ["battle", async (c) => {
      await place(c, "沈浪", "wan_city");
      await place(c, "白飛", "wan_city");
      c.log("start", (await c.api("admin", "/api/do/start_battle", { id: "wancheng_yi" })).status);
      await c.api("p2", "/api/main");
      await c.asPlayer("p1");
      await c.shoot("bt_muster", { who: "p1" });
      await c.step(CH("battle:join:guan"), "bt_joined", { who: "p1" });
      await c.api("p2", "/api/choose", { id: "battle:join:huang" });
      await c.load("/");
      await c.shoot("bt_muster2", { who: "p1" });
      await c.crawl("bt", () => c.load("/"), [...UI, "battle-shut"], { total: 8, cap: 2 });
      // batch 234: the page left open polls /api/main while the clock is pushed; on one walk it saw the battle start and played 開打
      // (#bp-ov, web/battle.js bpShow) and marked it seen, on the other it played it on the load below (15 REAL on bt_active, 7f816cb5e).
      // Leave the page first so the start is always seen on the load, then tap the layer away as a player does (it closes on a tap)
      await c.leave();
      for (let hop = 0; hop < 6; hop++) {
        await c.py("CLOCK['now'] += 600; out = 1");
        await c.api("admin", "/api/do/fast_forward", { hours: 1 });
        const m = await c.api("p1", "/api/main");
        await c.api("p2", "/api/main");
        if (m.json && m.json.battle_gauge && m.json.battle_gauge.phase === "active") break;
      }
      await c.load("/");
      for (let i = 0; i < 10 && !(await c.ev(`!!document.getElementById("bp-ov")`)); i++) await c.sleep(150);
      if (await c.ev(`!!document.getElementById("bp-ov")`)) { await c.click("#bp-ov"); await c.settle(450); }
      await c.shoot("bt_active", { who: "p1" });
      await c.crawl("bta", () => c.load("/"), [...UI, "battle-shut", "battle-open"], { total: 8, cap: 2 });
      for (let r = 0; r < 3; r++) {
        await c.load("/");
        const m = await c.api("p1", "/api/main");
        const pick = m.json && m.json.options.filter((o) => o.enabled && o.id.startsWith("battle:") && !o.id.includes("leave"));
        c.log("battle options", JSON.stringify((m.json.options || []).map((o) => o.id)).slice(0, 300));
        if (!pick || !pick.length) break;
        await c.step(CH(pick[Math.min(r, pick.length - 1)].id), `bt_round${r}`, { who: "p1", wait: 700 });
        const q = await c.api("p2", "/api/main");
        const qp = q.json && q.json.options.filter((o) => o.enabled && o.id.startsWith("battle:") && !o.id.includes("leave"));
        if (qp && qp.length) await c.api("p2", "/api/choose", { id: qp[0].id });
        await c.load("/");
        await c.shoot(`bt_after_round${r}`, { who: "p1" });
      }
      await c.step(ACT("battle-shut"), "bt_shut", { light: true });
      await c.step(ACT("battle-open"), "bt_open", { light: true });
      await c.leave(); // the page would see the end first and play the overlay away (wave D: on one side only, 17 rows on 025_bt_end)
      for (let hop = 0; hop < 14; hop++) {
        const m = await c.api("p1", "/api/main");
        if (!m.json || !m.json.battle_gauge) break;
        const pick = m.json.options.filter((o) => o.enabled && o.id.startsWith("battle:") && !o.id.includes("leave"));
        if (pick.length) await c.api("p1", "/api/choose", { id: pick[0].id });
        const q = await c.api("p2", "/api/main");
        const qp = q.json && q.json.options.filter((o) => o.enabled && o.id.startsWith("battle:") && !o.id.includes("leave"));
        if (qp && qp.length) await c.api("p2", "/api/choose", { id: qp[0].id });
        await c.py("CLOCK['now'] += 300; out = 1");
      }
      await c.api("p1", "/api/main");
      await c.load("/", { keepCards: true });
      await c.shoot("bt_end", { who: "p1" });
      await c.step(ACT("mvp-replay"), "bt_mvp", { light: true });
      await c.step(ACT("mvp-close"), "bt_mvp_close", { light: true });
      await c.load("/");
      await c.shoot("bt_end2", { who: "p1" });
      await c.crawl("bte", () => c.load("/"), UI, { total: 8, cap: 2 });
    }],
    ["week2", async (c) => {
      // batch 233: the first sync after the week turns settles 名號 (titles, features/titles actions.settle) and writes its rumor at the same
      // minute as 天下形勢; the open page polls /api/main by itself and raced the calls below, so the two rumors' order differed between walks.
      // Leave the page first: the five accounts then sync in this order only
      await c.leave();
      c.log("ff", (await c.api("admin", "/api/do/fast_forward", { hours: 200 })).status);
      for (const [w] of ACCOUNTS) await c.api(w, "/api/main");
      await place(c, "沈浪", "wan_city");
      await place(c, "白飛", "wan_city");
      await c.api("p2", "/api/main");
      await c.asPlayer("p1");
      await c.load("/", { keepCards: true });
      await c.shoot("w2_story_card", { who: "p1" });
      await c.step(ACT("story-ok"), "w2_story_ok", { who: "p1" });
      await c.load("/");
      await c.shoot("w2_j", { who: "p1" });
      await c.crawl("w2", () => c.load("/"), UI, { total: 26, cap: 2 });
      for (let i = 0; i < 8; i++) await c.api("admin", "/api/do/cancel_battle", {});
      await c.api("p1", "/api/main");
      await c.load("/");
      await c.shoot("w2_after_cancel", { who: "p1" });
    }],
    ["news2", async (c) => {
      // finished battles by now: reports, the 戰記 page once the thread has written it
      let ready = null;
      for (let t = 0; t < 40 && ready === null; t++) {
        const seen = [];
        for (let id = 1; id < 12; id++) { const r = await c.api("p1", `/api/tale/${id}`); seen.push(r.json && r.json.status); if (r.json && r.json.status === "ready") { ready = { id, page: r.json.page }; break; } }
        if (t === 0 || t === 39) c.log("tale statuses", JSON.stringify(seen));
        if (ready === null) await c.sleep(1500);
      }
      c.log("tale", JSON.stringify(ready));
      const news = async () => { await c.load("/"); await c.tab("news"); };
      await news();
      await c.shoot("w2_news", { who: "p1" });
      await c.crawl("w2n", news, UI, { depth: 3, total: 44, cap: 3 });
      await news();
      await c.step('[data-act="report"]', "report_page", { who: "p1" });
      await c.step('[data-act="tale"]', "tale_layer", { wait: 1500 });
      await news();
      await c.click('[data-act="report"]');
      await c.step('[data-act="report-list"]', "report_list", {});
      if (ready && ready.page) {
        await c.loadRaw(ready.page.replace("?in=1", ""));
        await c.shootRaw("tale_public");
        await c.loadRaw(ready.page);
        await c.shootRaw("tale_in_game");
      }
      await c.load("/");
    }],
    ["smith", async (c) => {
      await c.py("st = chars.load('沈浪'); st.player.furnace_ready = True; st.player.furnace_day = st.player.furnace_day; chars.save(st); out = 1");
      await enterShop(c, "smith", "wan_city", "act:smith");
      await c.crawl("sm", () => c.load("/"), SHOP_UI, { depth: 2, total: 30, cap: 2 });
      await c.load("/");
      await c.step(CH("smith:buy:劍"), "sm_buy", { who: "p1" });
      await c.step(ACT("shop-unwrap"), "sm_unwrap", {});
      await c.step(ACT("shop-wield"), "sm_wield", { who: "p1" });
      await c.step(ACT("shop-keep"), "sm_keep", { who: "p1" });
      // batch 111: the shop covers #page (web/shop.css), so 修 and 淬煉 are the two big buttons on the 裝備庫 tab (web/smithy.js smithWornHtml)
      // batch 233: the two big buttons are inside the 身上 card now (.shop-worn .sw-in .shop-bigs), and a bought blade is sharp (修 grey:
      // 劍鋒還利); blunt the one in hand like a few fights would, then 修
      await c.py("st = chars.load('沈浪')\nif st.player.weapon: st.player.weapon.edge = 30\nchars.save(st); out = 1");
      await c.load("/");
      await c.click('[data-act="shop-tab"][data-tab="rack"]');
      await c.step(`.shop-layer .shop-worn .shop-bigs ${CH("smith:repair")}`, "sm_repair", { who: "p1" });
      await c.load("/");
      await c.click('[data-act="shop-tab"][data-tab="rack"]');
      await c.step(`.shop-layer .shop-worn .shop-bigs ${CH("smith:temper")}`, "sm_temper", { who: "p1" });
      await c.load("/");
      await c.step('[data-act="shop-tab"][data-tab="forge"]', "sm_forge");
      await c.step(ACT("shop-kind"), "sm_forge_kind");
      await c.step(ACT("shop-slot"), "sm_forge_slot");
      await c.step(ACT("shop-cell"), "sm_forge_cell");
      await c.step('[data-act="shop-cell"]:not([disabled]):not(.on):not(.picked)', "sm_forge_cell2");
      await c.ev(`(() => { const s = [...document.querySelectorAll('[data-act="shop-cell"]:not([disabled])')]; if (s[5]) s[5].click(); return s.length; })()`);
      await c.settle(300);
      await c.shoot("sm_forge_cell3", { light: true });
      await c.step(ACT("shop-go"), "sm_forge_go", { who: "p1", wait: 800 });
      await c.step(ACT("shop-unwrap"), "sm_forge_unwrap", {});
      await c.step(ACT("shop-keep"), "sm_forge_keep", { who: "p1" });
      await c.load("/");
      await c.step('[data-act="shop-tab"][data-tab="forge"]');
      await c.step(ACT("shop-furnace"), "sm_furnace", {});
      await c.step(ACT("shop-brew"), "sm_brew", {});
      await c.load("/");
      await c.step('[data-act="shop-tab"][data-tab="rack"]', "sm_rack");
      // batch 233: the 裝備庫 check boxes only take a click after 挑著拆 (rack-picking, web/smithy.js rackHtml); 拆解 is one of the four
      // buttons a row shows once it is opened (rack-open)
      await c.click('[data-act="rack-picking"][data-on="1"]');
      await c.step(ACT("rack-pick"), "sm_rack_pick");
      await c.step(ACT("rack-melt"), "sm_rack_melt", { who: "p1" });
      await c.load("/");
      await c.step('[data-act="shop-tab"][data-tab="rack"]');
      await c.click(ACT("rack-open"));
      await c.step(ACT("shop-dismantle"), "sm_dismantle", { who: "p1" });
      await c.step('[data-act="ask-yes"]', "sm_dismantle_yes", { who: "p1" });
      await c.step(ACT("trade-sell"), "sm_sell", { who: "p1" });
      await c.step(ACT("trade-up"), "sm_up", { who: "p1" });
      await c.load("/");
      await c.step('[data-act="shop-tab"][data-tab="trade"]', "sm_trade");
      await c.step(ACT("trade-sell"), "sm_trade_sell", { who: "p1" });
      await c.step(ACT("trade-up"), "sm_trade_up", { who: "p1" });
      await c.load("/");
      await c.step('[data-act="shop-tab"][data-tab="divine"]', "sm_divine");
      await c.step(ACT("dv-cell"), "sm_divine_cell", {});
      await c.load("/");
      await c.step(CH("smith:page:armor"), "sm_armor", { who: "p1" });
      await c.load("/");
      // batch 111: the shop draws no smith:page:material button (only the hidden menu under it has one): the way enterShop falls back
      if (await c.step(CH("smith:page:material"), "sm_material", { who: "p1" }) !== "ok") { await c.api("p1", "/api/choose", { id: "smith:page:material" }); await c.load("/"); await c.shoot("sm_material", { who: "p1" }); }
      await c.load("/");
      await leave(c, "smith", "smith:back");
    }],
    ["market", async (c) => {
      await enterShop(c, "market", "zhuo_county", "act:market");
      await c.crawl("mk", () => c.load("/"), SHOP_UI, { total: 12, cap: 2 });
      await c.load("/");
      // batch 111: the market is a row of stalls; a stall shows its card and the card's one button (web/gear.js marketHtml, horseCard).
      // A bare CHP("market:") hits the shop's own "‹ 出店" first (data-id market:back), so every button here is looked up inside .horse-card
      await c.click('[data-act="shop-horse"][data-id="騎:8"]');
      await c.step(`.horse-card ${CH("market:wield:騎:8")}`, "mk_wield", { who: "p1" });
      await c.load("/");
      await c.step(CH("market:feed"), "mk_feed", { who: "p1" });
      await c.load("/");
      await c.click('.stall.r-sale[data-act="shop-horse"]');
      await c.step(`.horse-card ${CH("market:buy")}`, "mk_buy", { who: "p1" });
      await c.step(ACT("shop-horse"), "mk_horse", { who: "p1" });
      // the first stall's button can be grey (just fed): take the first stall whose card has a button that presses
      const card = `.horse-card ${CHP("market:")}`;
      const stalls = await c.ev(`document.querySelectorAll('.stalls > button.stall').length`);
      for (let i = 1; i <= stalls && !(await c.ev(`!!document.querySelector(${JSON.stringify(card)})`)); i++) await c.click(`.stalls > button.stall:nth-of-type(${i})`);
      await c.step(card, "mk_buy2", { who: "p1" });
      await c.load("/");
      await leave(c, "market", "market:back");
    }],
    ["outlets", async (c) => {
      await enterShop(c, "dadian", "wan_city", "act:dadian");
      await c.crawl("dd", () => c.load("/"), SHOP_UI, { total: 10, cap: 2 });
      // batch 233: 捐軍備 is off in week7 and season21 (#241, economy.donate false): no 捐銀兩 on the ledger and no donate shop, so both left the walk
      for (const [id, n] of [["act:mentor", "mentor"], ["act:buy_legend", "legend"], ["act:bribe:zhujun", "bribe"], ["act:furnace", "furnace"]]) {
        await c.load("/");
        await c.step(CH(id), `dd_${n}`, { who: "p1" });
      }
      await c.load("/");
      await leave(c, "dadian", "dadian:back");
    }],
    ["tavern", async (c) => {
      await enterShop(c, "tavern", "wan_city", "act:tavern");
      await c.crawl("tv", () => c.load("/"), SHOP_UI, { depth: 2, total: 24, cap: 3 });
      // batch 112: 打聽 and 題壁 have no tav-do button, they are forms (web/tavern.js #tav-ask, #tav-wall); 暗處's 查到過的 names (tav-hit-name)
      // only fill the box, and 招募 (tav-hire, web/hire.js) walks out of the tavern first, so the name chip and 出店 come before it
      const SEND = { ask: [["seek", "#tav-ask", "朱儁"], ["ties", "#tav-ask", "白飛"]], wall: [[null, "#tav-wall", "酒好，下回再來"], [null, "#tav-wall", "再飲一杯"]] };
      for (const tab of ["news", "ask", "wall", "shade"]) {
        await c.load("/");
        await c.click(`[data-act="tav-tab"][data-tab="${tab}"]`);
        for (let i = 0; i < 2; i++) {
          if (!SEND[tab]) { await c.step(ACT("tav-do"), `tv_${tab}_do${i}`, { who: "p1" }); continue; }
          const [mode, form, text] = SEND[tab][i];
          if (mode) await c.click(`[data-act="tav-mode"][data-mode="${mode}"]`);
          const sent = await c.fillAndSend(`${form} input`, text);
          if (sent !== "sent") { c.log("skip", form, sent); continue; }
          await c.settle(600);
          await c.shoot(`tv_${tab}_do${i}`, { who: "p1" });
        }
      }
      await c.step(ACT("tav-hit-name"), "tv_hit", {});
      await c.load("/");
      // batch 233: a season stamped guard_on (親衛隊長, #212) hires nobody at the tavern (features/hire actions.on), so 招募 left the walk
      await leave(c, "tavern", "tavern:back");
    }],
    ["bounties", async (c) => {
      await enterShop(c, "board", "wan_city", "act:bounties");
      await c.crawl("bd", () => c.load("/"), SHOP_UI, { total: 12, cap: 3 });
      await c.load("/");
      await c.step(ACT("board-zoom"), "bd_zoom");
      // batch 111: 揭下, 交出 and 放棄 are on the paper a note opens (web/bounties.js paperHtml); 放棄 asks once (shop-ask, then ask-yes)
      await c.load("/");
      await c.click('.shop-layer .note:not(.dim):not(.held)[data-act="board-zoom"]');
      await c.step(`.board-sheet ${CHP("bounty:take:")}`, "bd_take", { who: "p1" });
      // batch 112: 交出… is only on a 求兵 paper (k-arms, nothing to 揭), lit when something on you fits: stage one that fits the first 求兵 here
      if (await c.py("out = stage.arms_fit(chars, content, world, '沈浪')")) {
        await c.load("/");
        await c.click('.shop-layer .note.k-arms:not(.dim)[data-act="board-zoom"]');
        await c.step(`.board-sheet ${CHP("bounty:pick")}`, "bd_pick", { who: "p1" });
        // batch 113: the paper handed in is drawn again with a 交差 stamp and taken away by a 1400 ms wall-clock timer (web/bounties.js
        // boardHanded, STAMP_MS); base = head showed it on one side and not the other in two of four walks. Wait it out, then take the board
        if (await c.step(`.board-sheet ${CHP("bounty:give:")}`, "bd_give", { who: "p1" }) === "ok") await c.step('[data-act="ask-yes"]', "bd_given", { who: "p1", wait: 1900 });
      }
      await c.load("/");
      await c.click('.shop-layer .slot[data-act="board-zoom"]');
      await c.step('.board-sheet [data-act="shop-ask"][data-id^="bounty:drop"]', "bd_drop_ask", { light: true });
      await c.step('[data-act="ask-yes"]', "bd_drop", { who: "p1" });
      await c.load("/");
      await leave(c, "board", "bounty:back");
    }],
    ["arena", async (c) => {
      await place(c, "白飛", "wan_city");
      await c.api("p2", "/api/choose", { id: "act:arena" });
      await c.api("p2", "/api/choose", { id: "arena:join" });
      await c.api("p2", "/api/choose", { id: "arena:back" });
      await enterShop(c, "arena", "wan_city", "act:arena");
      await c.crawl("ar", () => c.load("/"), SHOP_UI, { total: 8, cap: 3 });
      await c.load("/");
      await c.step(CH("arena:join"), "ar_join", { who: "p1" });
      await c.step(CHP("arena:fight"), "ar_fight", { who: "p1" });
      for (let i = 0; i < 3; i++) await c.step(CH("arena:強攻"), `ar_round${i}`, { who: "p1", wait: 700 });
      await c.step('[data-act="shop-ask"]', "ar_yield_ask", { light: true });
      await c.load("/");
      for (let i = 0; i < 30; i++) {
        const m = await c.api("p1", "/api/main");
        if (!m.json || !m.json.options.some((o) => o.id === "arena:強攻")) break;
        await c.api("p1", "/api/choose", { id: "arena:強攻" });
      }
      await c.load("/");
      await c.shoot("ar_result", { who: "p1" });
      await c.step(ACT("arena-seen"), "ar_seen", { who: "p1" });
      await c.load("/");
      await c.shoot("ar_after", { who: "p1" });
      await c.step('[data-act="arena-tab"][data-tab="board"]', "ar_board");
      await c.load("/");
      await leave(c, "arena", "arena:back");
    }],
    ["peers", async (c) => {
      await place(c, "白飛", "wan_city");
      await place(c, "沈浪", "wan_city");
      await c.api("p2", "/api/main");
      await c.load("/");
      await c.step(ACT("peer"), "peer_card", { who: "p1" });
      await c.crawl("pe", async () => { await c.load("/"); await c.click(ACT("peer")); }, [...UI, "peer-pick", "peer-act", "peer-close", "renown-peer", "mt-zoom-peer"], { total: 10, cap: 3 });
      await c.load("/");
      await c.click(ACT("peer"));
      await c.step(ACT("peer-act"), "peer_act", { who: "p1" });
      // batch 272: on the new 江湖頁 the 俠客's card groups what you can do (web/jianghu.js jhPeerHtml): pick a kind, a choice, back.
      // 去 (jh-peer-go) is not walked: it sends the act and changes 沈浪 and 白飛 for the flows after (peer_act above already sends one)
      await c.load("/");
      await c.click(ACT("peer"));
      await c.step(ACT("jh-peer-pick"), "jh_peer_pick", { who: "p1" });
      await c.step(ACT("jh-peer-choice"), "jh_peer_choice", { light: true });
      await c.step(ACT("jh-peer-back"), "jh_peer_back", { light: true });
      // batch 272: the new 江湖頁 has no 全部 N › line; here-all is a sign that gathers two places of one kind or more (學藝, 赴宴,
      // 拜師: web/jianghu.js jhSignsHtml JH_SIGN_GROUP). 宛城 teaches 沈浪 nothing he lacks; the deep mountains teach two arts (learn.at)
      await place(c, "沈浪", "deep_mountain");
      await c.load("/");
      await c.step(ACT("here-all"), "here_all");
      await c.step(ACT("here-all-close"), "here_all_close");
      await place(c, "沈浪", "wan_city");
      // the mingtie editor (名帖)
      // batch 233: with the titles package on (#243) the pool only has 官職 from rank 2, 親傳, 本命兵器, 神器 and the title book
      // (features/peers mingtie._earned_titles), too few for 刷新頭銜 (pool > 3); stage last seasons' book like a player who has played some
      await c.py("st = chars.load('沈浪'); st.player.title_book = [*st.player.title_book, '第1季 擂台魁首', '第1季 懸賞榜首', '第1季 決戰首功', '第1季 練成絕學']; chars.save(st); out = 1");
      await c.load("/");
      // batch 111: the mingtie box moved to the 俠客 page (SELF_NEWS: the portrait card's "名帖 ›", web/cultivation.js heroAnnalsHtml)
      await c.tab("practice");
      await c.click('[data-act="news"][data-news="mingtie"]');
      await c.settle(300);
      await c.shoot("mingtie_box", { light: true });
      await c.step(ACT("mt-edit"), "mt_edit", {});
      await c.step(ACT("mt-shuffle"), "mt_shuffle", { light: true });
      await c.step(ACT("mt-close"), "mt_close", { light: true });
      await c.load("/");
    }],
    ["call", async (c) => {
      await place(c, "沈浪", "wan_city");
      // batch 111: 宛城 has four figures, so 交友 picks the person first (web/main.js socialPick): the cell opens a list (call_list) and
      // 朱儁's line talks to him straight away (fig-talk, his talk.via is act:call, call:zhujun). The old one-tap 交友 only when the list has it
      // batch 272: the new 江湖頁 has no 交友 cell (its third cell is 軍務: web/jianghu.js jhActs, "點人就是交友"), so no call_list;
      // a player taps 朱儁 in 這裡的人 (.jh-ic.fig, fig-open) and talks to him from his card (.jh-fig, fig-talk)
      const FIG = '.jh-ic.fig[data-act="fig-open"][data-id="zhujun"]';
      await c.load("/");
      await c.click(FIG);
      await c.step('.jh-fig [data-act="fig-talk"][data-id="zhujun"]', "call_zhujun", { who: "p1", wait: 1800 });
      await c.crawl("cl", () => c.load("/"), [...UI, "fig-close", "fig-log-close", "letter-read"], { total: 10, cap: 2 });
      // batch 112: 往來紀錄, 交談, 護衛 and × are on the figure's own layer (web/companions.js figPickHtml, .vn-layer.pick), which the 此地人物
      // chip opens (fig-open); a reload closes it, so open it again before each. fig-act closes the layer itself, so × comes before it.
      // batch 112 stopped walking × (call_close) and 護衛 (call_act): base = head came out different in two of four main rounds
      // (BODY.layer-open 1280px vs 1265px). The lock that was left on was the 改版資訊 sheet's (still open here then); batch 113 closes
      // that sheet in "prep", so after × or 護衛 no layer is left and the page has its scrollbar like any other
      // batch 272: on the new 江湖頁 that layer is the figure's card (.jh-fig, web/jianghu.js jhFigHtml), opened from his tile
      const PICK = ".jh-fig";
      const pick = async () => { await c.load("/"); await c.click(FIG); };
      await pick();
      await c.step(`${PICK} ${ACT("fig-log")}`, "call_log");
      await pick();
      await c.step(`${PICK} ${ACT("fig-talk")}`, "call_talk", { wait: 1800 });
      await pick();
      await c.step(`${PICK} ${ACT("fig-close")}`, "call_close", { who: "p1" });
      await pick();
      await c.step(`${PICK} ${ACT("fig-act")}`, "call_act", { who: "p1" });
      await c.api("p1", "/api/choose", { id: "call:back" });
      await c.load("/");
      // batch 272: open only; reading or declining it here would take the letter away from notify's ask (they moved to notify's end)
      await openLetter(c, "letter_open", {});
      await c.load("/");
      await c.step(ACT("checkin"), "checkin", { who: "p1" });
      await c.step(ACT("story-ok"), "story_ok", { who: "p1" });
      await c.step(ACT("guide-ack"), "guide_ack", { who: "p1" });
      await c.step(ACT("guide-next"), "guide_next", { who: "p1" });
      await c.step(ACT("push-no"), "push_no", { who: "p1" });
    }],
    ["explore", async (c) => {
      await place(c, "沈浪", "yingchuan_wilds");
      await c.load("/");
      await c.shoot("ex_wilds", { who: "p1" });
      await c.step('[data-act="wheel"][data-key="explore"]', "ex_open", { who: "p1" });
      await c.step(ACT("outing-go"), "ex_go", { who: "p1", wait: 1500 });
      await c.crawl("ex", () => c.load("/"), [...UI, "outing-speed", "gather-wheel", "outing-tap", "outing-stele"], { total: 8, cap: 2 });
      await c.load("/");
      for (const a of ["outing-speed", "outing-tap", "outing-skip", "outing-choose"]) await c.step(ACT(a), `ex_${a}`, { who: "p1", wait: 800 });
      // batch 233: since 親衛隊長's fifth batch (#217-#220) the first trip out at level 10 or more runs into the child: 救 (outing-choose
      // above) asks once more, 收養他／收養她／不帶走. A player answers it (the first, 收養他) and the trip ends on its result card as before
      if (await c.ev(`!!document.querySelector('[data-act="outing-choose"][data-id^="guard:"]')`)) await c.step(ACT("outing-choose"), "ex_guard_adopt", { who: "p1", wait: 800 });
      // batch 234: the adoption leaves its 果 card up (「你替他取名…」) with the 接著走 bar still filling; a player taps 接著走 (outing-tap,
      // web/outing.js outingNowHtml → outingHurry) and the trip's result card, with 留一句 and 收起, comes up as before
      if (await c.ev(`!!document.querySelector('#outing-pop .outing-now-go')`)) await c.step("#outing-pop .outing-now-go", "ex_guard_on", { who: "p1", wait: 800 });
      for (const a of ["outing-say", "outing-close"]) await c.step(ACT(a), `ex_${a}`, { who: "p1", wait: 800 });
      for (const [i, loc] of ["yingshui", "songshan_foot", "runan_wilds", "deep_mountain"].entries()) {
        await place(c, "沈浪", loc);
        await c.load("/");
        await c.click('[data-act="wheel"][data-key="explore"]');
        await c.step(`[data-act="outing-go"][data-n="${i % 2 ? 3 : 1}"]`, `ex_${i}_outing`, { who: "p1", wait: 1500 });
        await c.step(ACT("outing-skip"), `ex_${i}_skip`, { who: "p1" });
        await c.step(ACT("outing-choose"), `ex_${i}_choose`, { who: "p1", wait: 800 });
        await c.step(ACT("outing-close"), `ex_${i}_close`, { who: "p1" });
        await c.step(CHP("choice:"), `ex_${i}_choice`, { who: "p1" });
        await c.step(ACT("rounds-more"), `ex_${i}_rounds`, {});
        await c.step(ACT("hear-more"), `ex_${i}_hear`, { light: true });
      }
    }],
    ["sense", async (c) => {
      await c.py(`
from tianxia.state import Sensing
st = chars.load('沈浪'); p = st.player; p.location, p.journey = 'yingchuan_wilds', None; st.pending_event = None; p.outing = None
sc = content.insight_scenes['anywhere_still']
p.sense_serial += 1
p.sensing = Sensing(location=p.location, scene=sc.id, order=list(range(len(sc.methods))), serial=p.sense_serial)
chars.save(st); out = len(sc.methods)`);
      await c.load("/");
      await c.shoot("sense_card", { who: "p1" });
      await c.crawl("se", () => c.load("/"), UI, { total: 6, cap: 2 });
      await c.py(`
from tianxia.state import Sensing
st = chars.load('沈浪'); p = st.player
sc = content.insight_scenes['anywhere_still']
p.sensing = Sensing(location=p.location, scene=sc.id, order=list(range(len(sc.methods))), stage='draw', method=sc.methods[0].attribute if hasattr(sc.methods[0], 'attribute') else '剛', serial=p.sense_serial)
chars.save(st); out = 1`);
      await c.load("/");
      await c.shoot("sense_draw_card", { who: "p1" });
      await c.step(CH("sense:draw"), "sense_pad", {});
      // batch 112: the sheets that pop on entering the game (改版資訊 .patch-pop, news.js, Joy 11/09; 簽到 .ck-pop, checkin.js) sit over the
      // canvas until closed, so the mouse stroke never reached it; a player closes them first
      for (let i = 0; i < 4 && await c.click(".sheet-bg[data-act]") === "ok"; i++);
      await c.drawOn("#sense-canvas");
      await c.shoot("sense_pad_drawn", {});
      await c.step(ACT("sense-clear"), "sense_pad_clear", {});
      await c.drawOn("#sense-canvas");
      await c.step(ACT("sense-send"), "sense_sent", { who: "p1", wait: 2500 });
      await c.load("/");
      await c.shoot("sense_after", { who: "p1" });
      await c.step(CHP("sense:"), "sense_after_choice", { who: "p1" });
      await c.py(`st = chars.load('沈浪'); st.player.sensing = None; st.player.naming = None; chars.save(st); out = 1`);
    }],
    ["seal", async (c) => {
      await c.py(`
from tianxia.features.seal import seal
name = '沈浪'
def _give(shared):
    reg = seal.filled(shared.seal, content)
    shard = reg.shards[next(iter(content.seal))]
    shard.state, shard.holder, shard.since_season = 'held', name, shared.season_number
    seal.log(reg, shared.season_number, 'assign', shard=shard.id, holder=name)
world.mutate(_give)
st = chars.load(name); st.player.location, st.player.journey = 'wan_city', None; st.pending_event = None; chars.save(st); out = 1`);
      await c.api("p1", "/api/main");
      await c.load("/");
      await c.shoot("seal_card", { who: "p1" });
      await c.crawl("sl", () => c.load("/"), [...UI, "seal-act-close"], { total: 8, cap: 2 });
      await c.load("/");
      await c.step(ACT("seal-act-go"), "seal_go", { who: "p1", wait: 600 });
      await c.step(ACT("seal-act"), "seal_act", {});
      await c.step(ACT("seal-side"), "seal_side", {});
      await c.step(ACT("seal-pick"), "seal_pick", {});
      await c.step('[data-act="ask-no"]', "seal_pick_no", { light: true });
      await c.step(ACT("seal-act-close"), "seal_act_close", { light: true });
      await c.py(`
from tianxia.world_state import SealDuel, SealSide
def side(name, role=''):
    return SealSide(name=name, power=80.0, scores={'強攻': 60.0, '固守': 60.0, '奇襲': 60.0}, role=role, hp=300.0, hp_cap=300.0, last_seen=None)
def fn(shared):
    shared.seal_duels = [SealDuel(id='7:chishou', shard=next(iter(content.seal)), record=7, where='長社火攻', phase='active', starts_real=CLOCK['now'], challenger=side('白飛'), holder=side('沈浪'), cap=0.25)]
world.mutate(fn)
out = 1`);
      await c.api("p1", "/api/main");
      await c.load("/");
      await c.shoot("seal_duel_card", { who: "p1" });
      await c.step(CHP("seal:"), "seal_duel_move", { who: "p1" });
      await c.step('.seal-duel [data-act]', "seal_duel_tap", { light: true });
      await c.py("def fn(shared):\n    shared.seal_duels = []\nworld.mutate(fn)\nout = 1");
      await c.api("p1", "/api/main");
      await c.load("/");
      await c.tab("practice");
      await c.click('[data-act="hero-tab"][data-tab="gear"]');
      await c.shoot("seal_hero_gear", { light: true });
      await c.load("/");
    }],
    ["practice2", async (c) => {
      await place(c, "沈浪", "wan_city");
      const prac = async (tab) => { await c.load("/"); await c.tab("practice"); if (tab) await c.click(`[data-act="hero-tab"][data-tab="${tab}"]`); };
      await prac("attrs");
      await c.shoot("pr_attrs", { who: "p1" });
      await c.step(ACT("attr-help"), "pr_attr_help", { light: true });
      await prac("attrs");
      await c.step(ACT("alloc-toggle"), "pr_alloc", { light: true });
      await c.step(ACT("allocate"), "pr_allocate", { who: "p1" });
      await c.step(ACT("allocate"), "pr_allocate2", { who: "p1" });
      await prac("arts");
      await c.shoot("pr_arts", { who: "p1" });
      const drawer = async () => { await prac("arts"); await c.click(ACT("art")); };
      await drawer();
      await c.shoot("pr_art_drawer", { who: "p1" });
      await c.step(ACT("art-info"), "pr_art_info", {});
      await drawer();
      await c.step(ACT("slot-pick"), "pr_slot_pick", {});
      await c.step(ACT("slot-in"), "pr_slot_in", { who: "p1" });
      await c.step(ACT("slot-out"), "pr_slot_out", { who: "p1" });
      await c.step(ACT("drawer-close"), "pr_drawer_close", { light: true });
      await drawer();
      await c.step(ACT("switch"), "pr_switch", { who: "p1" });
      await c.step('[data-act="ask-yes"]', "pr_switch_yes", { who: "p1" });
      await drawer();
      await c.step(ACT("cultivate"), "pr_cultivate", { who: "p1" });
      await c.step(ACT("bind-art"), "pr_bind", { who: "p1" });
      await c.step(ACT("teach"), "pr_teach", { who: "p1" });
      await prac("arts");
      await c.step(ACT("lib-all"), "pr_lib", {});
      await c.step(ACT("lib-filter"), "pr_lib_filter", { light: true });
      await prac("arts");
      await c.step(ACT("ins-open"), "pr_ins", {});
      await c.step(ACT("melt-insight"), "pr_melt_insight_ask", {});
      await c.step('[data-act="ask-no"]', "pr_melt_insight_no", { light: true });
      await c.step(ACT("feed"), "pr_feed", { who: "p1" });
      await prac("arts");
      await c.step(ACT("ins-filter"), "pr_ins_filter", { light: true });
      await prac("arts");
      await c.step(ACT("melt-mode"), "pr_melt_mode", {});
      await c.step(ACT("melt-view"), "pr_melt_view", { light: true });
      await c.step(ACT("melt-shown"), "pr_melt_shown", { light: true });
      await c.step(ACT("melt-weak"), "pr_melt_weak", {});
      await c.step(ACT("melt-clear"), "pr_melt_clear", {});
      await c.step(ACT("melt"), "pr_melt_pick", {});
      await c.step(ACT("melt-go"), "pr_melt_go", { who: "p1" });
      await c.step('[data-act="ask-yes"]', "pr_melt_yes", { who: "p1" });
      await drawer();
      await c.step(ACT("melt"), "pr_melt_one", {});
      await c.step('[data-act="ask-no"]', "pr_melt_one_no", { light: true });
      const gear = async () => { await prac("gear"); };
      await gear();
      await c.shoot("pr_gear", { who: "p1" });
      await c.crawl("prg", gear, [...UI, "drawer-close"], { depth: 2, total: 16, cap: 2 });
      await gear();
      await c.click(ACT("hero-node"));
      await c.step(ACT("rack-all"), "pr_rack_all", {});
      await c.step(ACT("wield"), "pr_wield", { who: "p1" });
      await gear();
      await c.click(ACT("hero-node"));
      await c.step(ACT("dismantle"), "pr_dismantle", { who: "p1" });
      await c.step('[data-act="ask-no"]', "pr_dismantle_no", { light: true });
      await prac("mates");
      await c.shoot("pr_mates", { who: "p1" });
      await c.crawl("prm", async () => { await prac("mates"); }, [...UI, "drawer-close"], { depth: 2, total: 8, cap: 2 });
      await prac("mates");
      await c.click(ACT("person"));
      await c.step(ACT("release-mate"), "pr_release", { who: "p1" });
      await c.step('[data-act="ask-no"]', "pr_release_no", { light: true });
      await prac();
      await c.step(ACT("hero-move-go"), "pr_move_go", {});
      await prac();
      await c.step(ACT("self-sec"), "pr_self_sec", {});
      await prac("attrs");
      await c.step(ACT("xinde-more"), "pr_xinde", { light: true });
      // batch 233: 江湖錄 (codex, on in week7 and season21 since 11/13) is the 俠客 page's last tab: 奇遇 first, then 圖鑑
      await prac();
      await c.step('[data-act="hero-tab"][data-tab="codex"]', "pr_codex", { who: "p1", wait: 800 });
      await c.step('[data-act="cx-seg"][data-seg="tj"]:not(.on)', "pr_codex_seg", { who: "p1", wait: 800 });
      await c.load("/");
    }],
    ["craft2", async (c) => {
      const craft = async () => { await c.load("/"); await c.tab("practice"); await c.click('[data-act="tab"][data-tab="craft"]'); };
      await craft();
      await c.shoot("cr_main", { who: "p1" });
      await c.crawl("cr2", craft, [...UI, "pick", "pot-close", "book-close", "secret-close", "unslot"], { depth: 2, total: 16, cap: 2 });
      await craft();
      await c.step(ACT("pot-open"), "cr_pot", {});
      await c.step(ACT("pick"), "cr_pick1", {});
      await c.step(ACT("pick"), "cr_pick2", {});
      await c.step(ACT("pot-lock"), "cr_lock", {});
      await c.step(ACT("craft-ok"), "cr_ok", { who: "p1" });
      await c.step(ACT("forge"), "cr_forge", { who: "p1", wait: 2500 });
      await c.step(ACT("craft-ok"), "cr_ok2", { who: "p1" });
      await craft();
      await c.step(ACT("art-filter"), "cr_filter", { light: true });
      await c.step(ACT("book-open"), "cr_book", {});
      await c.step(ACT("book-close"), "cr_book_close", { light: true });
      await c.step(ACT("secret-book"), "cr_secret", {});
      await c.step(ACT("secret-close"), "cr_secret_close", { light: true });
      // 自創
      await c.load("/");
      await c.tab("practice");
      await c.step(ACT("create-open"), "cr_create_open", { who: "p1" });
      await c.crawl("crc", async () => { await c.load("/"); }, ["create-kind", "create-preset", "create-pose", "create-intent", "create-pick"], { total: 10, cap: 2 });
      await c.load("/");
      await c.step(ACT("create-kind"), "cr_create_kind", {});
      await c.step(ACT("create-pose"), "cr_create_pose", {});
      await c.step(ACT("create-preset"), "cr_create_preset", {});
      await c.step(ACT("create-pick"), "cr_create_pick", {});
      await c.step(ACT("create-intent"), "cr_create_intent", {});
      await c.step(ACT("create-begin"), "cr_create_begin", { who: "p1", wait: 2500 });
      await c.step(ACT("create-name"), "cr_create_name", { who: "p1", wait: 1500 });
      await c.step(ACT("create-reroll"), "cr_create_reroll", { who: "p1", wait: 1500 });
      await c.step(ACT("create-cancel"), "cr_create_cancel", { who: "p1" });
      await c.step('[data-act="ask-yes"]', "cr_create_cancel_yes", { who: "p1" });
      await c.step(ACT("create-close"), "cr_create_close", { who: "p1" });
      await c.step(ACT("create-back"), "cr_create_back", { who: "p1" });
      await c.load("/");
    }],
    ["map2", async (c) => {
      await place(c, "沈浪", "yingchuan_wilds");
      const map = async () => { await c.load("/"); await c.tab("map"); };
      await map();
      await c.shoot("map_wilds", { who: "p1" });
      await c.crawl("map2", map, UI, { depth: 3, total: 40, cap: 3 });
      await c.py(`
from tianxia import conquest
def fn(s):
    conquest.push(s, content, 'yingshui', 'huang', '敵將', 40.0, 'attack')
    conquest.push(s, content, 'yingchuan_wilds', 'huang', '敵將', 20.0, 'attack')
    conquest.push(s, content, 'changshe', 'guan', '沈浪', 70.0, 'attack')
    conquest.push(s, content, 'runan_wilds', 'guan', '沈浪', 100.0, 'attack')
with world.db.transaction():
    world.mutate_season(fn)
st = chars.load('沈浪'); st.player.rank = 4; chars.save(st); out = 1`);
      await c.api("p1", "/api/main");
      await map();
      await c.shoot("terr_map", { who: "p1" });
      for (const id of ["yingshui", "changshe", "runan_wilds", "yingchuan_wilds", "huangjin_camp"]) {
        await map();
        await c.step(`[data-act="map-place"][data-id="${id}"]`, `terr_card_${id}`, {});
        await c.step(ACT("map-more"), `terr_more_${id}`, {});
        await c.step(ACT("map-letter"), `terr_letter_${id}`, {});
        await c.step('[data-act="ask-no"]', `terr_letter_no_${id}`, { light: true });
      }
      await map();
      await c.click('[data-act="map-place"][data-id="yingshui"]');
      await c.step(ACT("map-travel"), "map_travel", { who: "p1", wait: 800 });
      await c.load("/");
      await c.shoot("map_after_travel", { who: "p1" });
      await c.api("admin", "/api/do/fast_forward", { hours: 2 });
      await c.api("p1", "/api/main");
    }],
    ["travel", async (c) => {
      await place(c, "沈浪", "wan_city");
      await c.load("/");
      // batch 272: 行路 pulls up the road list (jh-sheet road, web/jianghu.js jhActs, jhRoadBody); the list has no 步行/疾行 switch
      // (疾行 is only on the road page), so no tr_mode: the step stays for a page that draws move-mode again
      await c.step(SHEET("road"), "tr_wheel", { who: "p1" });
      await c.step(ACT("move-mode"), "tr_mode", {});
      await c.step(CH("move:xinye"), "tr_leave", { who: "p1" });
      await c.crawl("tr", () => c.load("/"), UI, { total: 6, cap: 2 });
      await c.load("/");
      await c.tab("map");
      await c.shoot("tr_on_road_map", { who: "p1" });
      await c.load("/");
      await c.step(CHP("act:halt"), "tr_halt", { who: "p1" });
      await c.step(CHP("act:on_road"), "tr_on_road", { who: "p1" });
      await c.api("admin", "/api/do/fast_forward", { hours: 6 });
      await c.api("p1", "/api/main");
      await c.load("/");
      await c.shoot("tr_arrived", { who: "p1" });
    }],
    ["sortie", async (c) => {
      const ms = await c.api("p1", "/api/map/state");
      const held = Object.entries(ms.json.places).filter(([, v]) => v.control === "huang" && v.kind === "line").map(([k]) => k);
      const spot = held[0] || "runan_wilds";
      c.log("sortie at", spot, JSON.stringify(held).slice(0, 200));
      await c.py("st = chars.load('沈浪'); st.player.stamina = 240; st.player.sortie_cooldown_until = 0; st.player.sorties_today = 0; chars.save(st); out = 1");
      await place(c, "沈浪", spot);
      await place(c, "白飛", spot);
      await c.api("p2", "/api/main");
      await c.load("/");
      await c.shoot("so_here", { who: "p1" });
      await c.step(ACT("sortie-open"), "so_open", { who: "p1" });
      if ((await c.click(CH("act:train"))) === "ok") await c.shoot("so_cell", { who: "p1" });
      for (const r of [0, 1, 2]) await c.step(`[data-act="sortie-move"][data-round="${r}"]`, `so_move${r}`, { light: true });
      await c.step(ACT("sortie-send"), "so_send", { who: "p1", wait: 700 });
      await c.crawl("so", () => c.load("/"), [...UI, "sortie-far"], { total: 8, cap: 2 });
      await c.asPlayer("p2");
      await c.shoot("so_p2", { who: "p2" });
      await c.step(ACT("sortie-join"), "so_p2_join", { who: "p2" });
      await c.step(ACT("sortie-answer"), "so_p2_answer", { who: "p2" });
      for (const r of [0, 1, 2]) await c.step(`[data-act="sortie-move"][data-round="${r}"]`, `so_p2_move${r}`, { light: true });
      await c.step(ACT("sortie-send"), "so_p2_send", { who: "p2", wait: 700 });
      await c.asPlayer("p1");
      await c.api("admin", "/api/do/fast_forward", { hours: 1 });
      await c.api("p1", "/api/main");
      await c.load("/");
      await c.shoot("so_result", { who: "p1" });
      await stepVia(c, ACT("rounds-more"), SHEET("fight"), "so_rounds", {}); // batch 272: in 全部戰報 on the new page's fight page
      await c.load("/");
      await c.step(ACT("drill-full"), "so_drill", {});
      // batch 272: 巡哨 (act:duty) is a row of the 軍務 list on the new 江湖頁 (web/jianghu.js jhKinds JH_DUTY, jh-sheet duty)
      await stepVia(c, CH("act:duty"), DUTY, "so_duty", { who: "p1" });
      await c.load("/");
      await place(c, "沈浪", "wan_city");
      await c.load("/");
      // batch 233: with 江湖錄's 進行中 on (#267) the 要事 card is not drawn; a player opens the 事 seal of the 進行中 line (web/codex.js codexTrackHtml)
      // batch 272: the new 江湖頁 draws no 進行中 line; the same list (tkItems) is the 眼下 card's 另有 N 件 (jh-sheet eye)
      await c.step(EYE, "so_tk_open", {});
    }],
    ["notify", async (c) => {
      await c.load("/");
      await c.ev(`localStorage.removeItem("tianxia-push-asked"); 0`);
      await c.load("/");
      // batch 272: the new 江湖頁 asks only under the letter it pulls up (web/jianghu.js jhSheetHtml, p.pushAsk)
      await openLetter(c, "", {});
      await c.shoot("nf_prompt", { who: "p1" });
      await c.step(ACT("push-yes"), "nf_prompt_yes", { who: "p1", wait: 1500 });
      await c.load("/");
      await c.step(ACT("sheet"), "nf_sheet", {});
      await c.step(ACT("push-how"), "nf_how", {});
      await c.step(ACT("push-how-back"), "nf_how_back", { light: true });
      await c.step(ACT("push-yes"), "nf_yes", { who: "p1", wait: 1500 });
      await c.step(ACT("push-test"), "nf_test", { wait: 800 });
      await c.step(ACT("push-no"), "nf_no", { who: "p1", wait: 800 });
      await c.step(ACT("howto"), "nf_howto", {});
      await c.step(ACT("howto-retry"), "nf_howto_retry", { light: true });
      await c.step(ACT("sheet-close"), "nf_close", { light: true });
      await c.load("/");
      await c.click(ACT("sheet"));
      await c.crawl("sh", async () => { await c.load("/"); await c.click(ACT("sheet")); }, [...UI, "recap", "howto"], { total: 8, cap: 2 });
      await c.load("/");
      // batch 272 (from call): the letter read and, when it is a task, declined, on the new 江湖頁's letter layer
      await openLetter(c, "", {});
      await c.step(ACT("letter-read"), "letter_read", { who: "p1" });
      await openLetter(c, "", {});
      await c.step(ACT("letter-decline"), "letter_decline", { who: "p1" });
      await c.load("/");
    }],
    // batch 236: support is on in week7 and season21. A player opens 客服 › in the sheet, writes a text ticket (no picture);
    // a non-admin account on the support list (only in this server process's memory, put back at the end) answers it on /admin;
    // the player sees the dot and reads the answer, so the dot is gone for the flows after this one.
    ["support", async (c) => {
      // the lists come in after the click (supportLoad, supportDeskReload): wait for them before the picture, not a fixed sleep
      const until = async (js) => { for (let i = 0; i < 40; i++) { if (await c.ev(js).catch(() => false)) return true; await c.sleep(100); } c.log("support wait gave up", js); return false; };
      const shootWhen = async (sel, name, js, opts) => { const r = await c.click(sel, opts); if (r !== "ok") { c.log("skip", sel, r); return r; } await until(js); await c.settle(200); await c.shoot(name, opts); return r; };
      // batch 238: a 24x16 two-colour PNG (97 bytes), always the same bytes, for the ticket with a picture below
      const QA_PNG = "iVBORw0KGgoAAAANSUhEUgAAABgAAAAQCAIAAACDRijCAAAAKElEQVR42mO4c2IBGtKwiUJDxKhhGMYGkacNU81wNmg0HY2mIyoYBADFO0GfviIV1gAAAABJRU5ErkJggg==";
      await c.asPlayer("p1");
      await c.click(ACT("sheet"));
      await shootWhen(ACT("support-open"), "sup_mine", `!!S.supportMine`, { who: "p1", wait: 700 });
      await c.step('[data-act="support-tab"][data-tab="new"]', "sup_new", {});
      c.log("support send", await c.fillAndSend('#support-new-form textarea[name="body"]', "QA test ticket: the map does not open."));
      await until(`S.supportTicket != null`);
      await c.settle(600);
      await c.shoot("sup_sent", { who: "p1" });
      // a non-admin account on the support list, only in this server's memory (Config.support.staff; put back below), logged in again
      // with the password so the desk's staff_session_ok holds after the clock moved
      // batch 238: anything that throws between putting a name on the list and taking it off (click, ev) must not leave it there
      await c.py("content.config.support.staff = [*content.config.support.staff, 'qaplayer4']; out = 1");
      try {
        c.log("support relogin", await c.relogin("p4"));
        await c.asPlayer("p4");
        await c.load("/admin");
        await until(`!!S.supportDesk && !S.supportDeskLoading`);
        await c.settle(300);
        await c.shoot("sup_desk", { who: "p4" });
        await shootWhen('[data-act="support-desk-pick"]', "sup_desk_pick", `!!document.getElementById("support-answer-body")`, { who: "p4", wait: 700 });
        await c.ev(`(() => { const e = document.getElementById("support-answer-body"); if (e) e.value = "QA test answer: try reloading the page."; return e ? 1 : 0; })()`);
        await shootWhen('[data-act="support-answer"][data-then="wait"]', "sup_desk_answered", `!S.supportDeskLoading`, { who: "p4", wait: 900 });
      } finally {
        await c.py("content.config.support.staff = [s for s in content.config.support.staff if s != 'qaplayer4']; out = 1");
      }
      await c.asPlayer("p1");
      await c.shoot("sup_dot", { who: "p1" });
      await c.step(ACT("sheet"), "sup_dot_sheet", {});
      await shootWhen(ACT("support-open"), "sup_mine_answered", `!!document.querySelector('[data-act="support-ticket"]')`, { wait: 700 });
      await c.step('[data-act="support-ticket"]', "sup_ticket_read", {});
      // batch 238: a ticket with a picture. The picture is a fixed 24x16 PNG made in the page (DataTransfer), not a file on disk. The
      // preview url would be a fresh blob: url on every run (and the dom compare reads it), so only for the change event that picks it
      // URL.createObjectURL hands back a data: url of the same picture; the game's code runs as it is, and the original comes back after.
      await c.load("/");
      await c.click(ACT("sheet"));
      await c.click(ACT("support-open"));
      await until(`!!S.supportMine`);
      await c.click('[data-act="support-tab"][data-tab="new"]');
      await until(`!!document.getElementById("support-new-files")`);
      c.log("support picks", await c.ev(`(() => {
        const b64 = "${QA_PNG}";
        const raw = atob(b64), bytes = new Uint8Array(raw.length);
        for (let k = 0; k < raw.length; k++) bytes[k] = raw.charCodeAt(k);
        const i = document.getElementById("support-new-files");
        if (!i) return "missing";
        const dt = new DataTransfer();
        dt.items.add(new File([bytes], "qa-shot.png", { type: "image/png" }));
        i.files = dt.files;
        const was = URL.createObjectURL;
        URL.createObjectURL = () => "data:image/png;base64," + b64;
        try { i.dispatchEvent(new Event("change", { bubbles: true })); } finally { URL.createObjectURL = was; }
        return (S.supportPicks || []).length;
      })()`));
      await c.settle(300);
      await c.shoot("sup_pick", { who: "p1" });
      // the text after the pictures: a new window size redraws and clears the textarea (the picks stay in S.supportPicks)
      const before = await c.ev(`S.supportTicket == null ? 0 : S.supportTicket`);
      c.log("support send shot", await c.fillAndSend('#support-new-form textarea[name="body"]', "QA test ticket: a picture of the screen."));
      await until(`(() => { const id = S.supportTicket; if (id == null || id === ${JSON.stringify(before)}) return false;
        const t = ((S.supportMine && S.supportMine.tickets) || []).find((x) => x.id === Number(id));
        const imgs = [...document.querySelectorAll(".sup-shots img")];
        return !!t && Array.isArray(t.files) && t.files.length === 1 && imgs.length > 0 && imgs.every((m) => m.complete && m.naturalWidth > 0); })()`);
      await c.settle(400);
      await c.shoot("sup_sent_shot", { who: "p1" });
      const tid = await c.ev(`S.supportTicket`);
      // batch 238: the admin on the support list (only in this server's memory, put back below) comes in from /admin's top row
      // (客服單 ›, batch 228; at 375 wide web/support.css keeps 管理者工具 on one line only on this page) and sees the picture
      await c.py("content.config.support.staff = [*content.config.support.staff, 'qaadmin']; out = 1");
      try {
        c.log("support relogin admin", await c.relogin("admin"));
        await c.asPlayer("admin");
        await c.load("/admin");
        await until(`!!document.querySelector('[data-act="support-desk-enter"]')`);
        await c.settle(300);
        await c.shoot("sup_admin", { who: "admin" });
        await shootWhen('[data-act="support-desk-enter"]', "sup_admin_desk", `location.hash === "#support" && !!S.supportDesk && !S.supportDeskLoading`, { who: "admin", wait: 700 });
        await shootWhen(`[data-act="support-desk-pick"][data-id="${tid}"]`, "sup_admin_desk_shot", `!!document.getElementById("support-answer-body") && [...document.querySelectorAll(".sup-shots img")].length > 0 && [...document.querySelectorAll(".sup-shots img")].every((m) => m.complete && m.naturalWidth > 0)`, { who: "admin", wait: 700 });
        await shootWhen('[data-act="support-desk-leave"]', "sup_admin_back", `location.hash === "" && !!document.querySelector('[data-act="support-desk-enter"]')`, { who: "admin", wait: 700 });
      } finally {
        await c.py("content.config.support.staff = [s for s in content.config.support.staff if s != 'qaadmin']; out = 1");
      }
      await c.asPlayer("p1");
      await c.load("/");
    }],
    ["mall", async (c) => {
      await c.load("/");
      await c.step(ACT("mall-open"), "mall", { who: "p1" });
      await c.crawl("ml", async () => { await c.load("/"); await c.click(ACT("mall-open")); }, ["mall-tab", "mall-cat", "mall-pick", "look-seg", "look-sub", "look-filter", "look-pick", "look-show", "look-fold", "look-more", "move-tab", "move-show", "mall-close"], { depth: 2, total: 18, cap: 2 });
      await c.load("/");
    }],
    ["admin", async (c) => {
      await c.asPlayer("admin");
      const ad = async () => { await c.load("/admin"); };
      await ad();
      await c.shoot("admin", { who: "admin" });
      await c.crawl("ad", ad, ["ad-tab", "ad-pick", "ad-refresh", "ad-result-close", "mall-admin", "looks-admin"], { depth: 2, total: 26, cap: 8 });
      await ad();
      await c.ev(`(() => { const i = document.querySelector('.ad-find input, input[data-role="find"], #ad-find, input'); if (i) { i.value = "沈"; i.dispatchEvent(new Event("input", { bubbles: true })); } return !!i; })()`);
      await c.step(ACT("ad-find"), "admin_find", {});
      await c.step(ACT("ad-pick"), "admin_pick", {});
      await c.load("/");
      await c.shoot("admin_game_page", { who: "admin" });
      await c.step(ACT("sheet"), "admin_sheet", {});
      await c.step(ACT("admin"), "admin_entry", {});
    }],
    ["seasonend", async (c) => {
      await c.asPlayer("p1");
      c.log("end", (await c.api("admin", "/api/do/end_season", {})).status);
      for (const w of ["p1", "p2", "admin"]) await c.api(w, "/api/main");
      await c.load("/");
      await c.shoot("end_j", { who: "p1" });
      await c.crawl("end", () => c.load("/"), [...UI, "zhuan-vertical", "zhuan-write", "zhuan-close"], { depth: 2, total: 12, cap: 2 });
      await c.load("/");
      await c.step(ACT("zhuan-open"), "zh_open", { who: "p1", wait: 800 });
      // batch 113: zh_write is the first scene with the finished 傳, and its ink picture is <img loading="lazy"> (web/zhuan.js .zh-art):
      // whether it had loaded and decoded by the time of each picture was timing, so base = head now and then came out a REAL pixel
      // difference. Bring the pictures into view, wait until they are loaded, decode them, then take the scene (the DOM is not touched)
      if (await c.click(ACT("zhuan-write"), { wait: 800 }) === "ok") {
        const IMGS = `[...document.querySelectorAll(".zhuan-layer img")]`;
        await c.ev(`(() => { for (const i of ${IMGS}) i.scrollIntoView({ block: "center" }); return 1; })()`);
        for (let i = 0; i < 50 && !(await c.ev(`${IMGS}.every((i) => i.complete && i.naturalWidth > 0)`)); i++) await c.sleep(100);
        await c.ev(`Promise.all(${IMGS}.map((i) => i.decode().catch(() => 0))).then(() => 1)`);
        await c.shoot("zh_write", {});
      } else c.log("skip", ACT("zhuan-write"));
      await c.step(ACT("zhuan-vertical"), "zh_vertical", {});
      await c.step(ACT("zhuan-share"), "zh_share", {});
      await c.step(ACT("zhuan-send"), "zh_send", { who: "p1", wait: 2000 }); // the send button only shows once it is public
      await c.step(ACT("zhuan-rewrite"), "zh_rewrite", {});
      await c.step(ACT("zhuan-close"), "zh_close", { light: true });
      const news = async () => { await c.load("/"); await c.tab("news"); };
      await news();
      await c.shoot("end_news", { who: "p1" });
      await c.crawl("endn", news, UI, { depth: 2, total: 16, cap: 3 });
      c.log("next", (await c.api("admin", "/api/do/next_season", {})).status);
      for (const w of ["p1", "p2", "admin"]) await c.api(w, "/api/main");
      await c.load("/");
      await c.shoot("next_prep", { who: "p1" });
      await c.step('[data-act="prep-pick"][data-preset="warrior"]', "next_pick", { light: true });
      await c.step('[data-act="prep-growth"]', "next_growth", { who: "p1" });
      await c.load("/");
      await c.shoot("next_j", { who: "p1" });
      await c.load("/");
      await c.tab("practice");
      await c.shoot("next_practice", { who: "p1" });
      await c.tab("news");
      await c.shoot("next_news", { who: "p1" });
      await c.crawl("nxn", async () => { await c.load("/"); await c.tab("news"); }, ["news", "zhuan-open"], { depth: 2, total: 10, cap: 3 });
      await c.load("/");
      await c.step(ACT("zhuan-open"), "next_zhuan", { who: "p1" });
    }],
];
