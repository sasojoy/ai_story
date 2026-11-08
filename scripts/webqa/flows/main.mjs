// The main walk: the gate, the opening, week 1 and 2, every shop, the fight, the season's end. Wave B's first round.
import { CH, CHP, ACT, place, UI, ACCOUNTS, accounts, rich } from "./common.mjs";

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
    await c.step('[data-act="letter-open"]', "j1_letter_toggle", { light: true });
    await c.step('[data-act="letter-read"]', "j1_letter_read", { who: "p1" });
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
      for (let hop = 0; hop < 6; hop++) {
        await c.py("CLOCK['now'] += 600; out = 1");
        await c.api("admin", "/api/do/fast_forward", { hours: 1 });
        const m = await c.api("p1", "/api/main");
        await c.api("p2", "/api/main");
        if (m.json && m.json.battle_gauge && m.json.battle_gauge.phase === "active") break;
      }
      await c.load("/");
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
      await c.load("/");
      await c.click('[data-act="shop-tab"][data-tab="rack"]');
      await c.step(`.shop-layer .shop-worn ~ .shop-bigs ${CH("smith:repair")}`, "sm_repair", { who: "p1" });
      await c.load("/");
      await c.click('[data-act="shop-tab"][data-tab="rack"]');
      await c.step(`.shop-layer .shop-worn ~ .shop-bigs ${CH("smith:temper")}`, "sm_temper", { who: "p1" });
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
      await c.step(ACT("rack-pick"), "sm_rack_pick");
      await c.step(ACT("rack-melt"), "sm_rack_melt", { who: "p1" });
      await c.load("/");
      await c.step('[data-act="shop-tab"][data-tab="rack"]');
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
      for (const [id, n] of [["act:silver_donate", "silver"], ["act:mentor", "mentor"], ["act:buy_legend", "legend"], ["act:bribe:zhujun", "bribe"], ["act:furnace", "furnace"]]) {
        await c.load("/");
        await c.step(CH(id), `dd_${n}`, { who: "p1" });
      }
      await c.load("/");
      await leave(c, "dadian", "dadian:back");
      await enterShop(c, "donate", "wan_city", "act:donate");
      await c.crawl("dn", () => c.load("/"), SHOP_UI, { total: 8, cap: 2 });
      await c.load("/");
      await c.step(ACT("dn-tier1"), "dn_tier1");
      await c.step(ACT("dn-cell"), "dn_cell");
      await c.step(ACT("dn-step"), "dn_step");
      await c.step(ACT("dn-go"), "dn_go", { who: "p1" });
      await c.load("/");
      await leave(c, "donate", "donate:back");
    }],
    ["tavern", async (c) => {
      await enterShop(c, "tavern", "wan_city", "act:tavern");
      await c.crawl("tv", () => c.load("/"), SHOP_UI, { depth: 2, total: 24, cap: 3 });
      for (const tab of ["news", "ask", "wall", "shade"]) {
        await c.load("/");
        await c.click(`[data-act="tav-tab"][data-tab="${tab}"]`);
        for (let i = 0; i < 2; i++) await c.step(ACT("tav-do"), `tv_${tab}_do${i}`, { who: "p1" });
      }
      await c.load("/");
      await c.step(ACT("tav-hire"), "tv_hire", { who: "p1" });
      await c.step(ACT("tav-hit-name"), "tv_hit", {});
      await c.load("/");
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
      await c.step(`.board-sheet ${CHP("bounty:pick")}`, "bd_pick", { who: "p1" });
      await c.step(`.board-sheet ${CHP("bounty:give:")}`, "bd_give", { who: "p1" });
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
      await c.load("/");
      await c.step(ACT("here-all"), "here_all");
      await c.step(ACT("here-all-close"), "here_all_close");
      // the mingtie editor (名帖)
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
      await c.load("/");
      await c.step('[data-act="wheel"][data-key="social"]', "call_list", {});
      if (await c.click(`.act-move ${CH("act:call")}`) === "ok") await c.step(CH("call:zhujun"), "call_zhujun", { who: "p1" });
      else await c.step('.act-move [data-act="fig-talk"][data-id="zhujun"]', "call_zhujun", { who: "p1", wait: 1800 });
      await c.crawl("cl", () => c.load("/"), [...UI, "fig-close", "fig-log-close", "letter-read"], { total: 10, cap: 2 });
      await c.load("/");
      await c.step(ACT("fig-log"), "call_log");
      await c.load("/");
      await c.step(ACT("fig-talk"), "call_talk", { wait: 1800 });
      await c.load("/");
      await c.step(ACT("fig-act"), "call_act", { who: "p1" });
      await c.step(ACT("fig-close"), "call_close", { who: "p1" });
      await c.api("p1", "/api/choose", { id: "call:back" });
      await c.load("/");
      await c.step(ACT("letter-open"), "letter_open", {});
      await c.step(ACT("letter-read"), "letter_read", { who: "p1" });
      await c.step(ACT("letter-decline"), "letter_decline", { who: "p1" });
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
      for (const a of ["outing-speed", "outing-tap", "outing-skip", "outing-choose", "outing-say", "outing-close"]) await c.step(ACT(a), `ex_${a}`, { who: "p1", wait: 800 });
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
      await c.step('[data-act="wheel"][data-key="move"]', "tr_wheel", { who: "p1" });
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
      await c.step(ACT("rounds-more"), "so_rounds", {});
      await c.load("/");
      await c.step(ACT("drill-full"), "so_drill", {});
      await c.step(CH("act:duty"), "so_duty", { who: "p1" });
      await c.load("/");
      await place(c, "沈浪", "wan_city");
      await c.load("/");
      await c.step(ACT("duty-open"), "so_duty_open", {});
    }],
    ["notify", async (c) => {
      await c.load("/");
      await c.ev(`localStorage.removeItem("tianxia-push-asked"); 0`);
      await c.load("/");
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
      await c.step(ACT("zhuan-write"), "zh_write", { wait: 800 });
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
