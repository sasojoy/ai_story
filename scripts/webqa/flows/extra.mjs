// What waves B and C did not reach: the prologue (staged), the map's away state, the divine form, the brew, figure talk and the persuade form,
// the MVP overlay, the ring, buying and selling in the mall, the admin buttons behind a held press or a picked player, the week card, the folded battlefield.
import { CH, ACT, place, ACCOUNTS as COMMON, accounts, rich } from "./common.mjs";
import { x_week2 } from "./x.mjs";

export const ACCOUNTS = COMMON;
const OP = (op) => `[data-act="admin"][data-op="${op}"]:not([disabled])`;
const YES = '.ask [data-act="ask-yes"]';
const closeOv = async (c) => { const had = await c.ev(`(() => { const e = document.getElementById("bp-ov"); if (!e) return false; e.click(); return true; })()`); await c.sleep(420); return had; };
const moveOf = (m, i = 0) => { const acts = (m.json.options || []).filter((o) => o.enabled && o.id.startsWith("battle:act:")); return acts.length ? acts[Math.min(i, acts.length - 1)].id : null; };
// the shop buttons on the wheel are not plain choices: go in the way the server sees it
async function enterShop(c, who, act) { await c.leave(); await c.api(who, "/api/choose", { id: act }); await c.asPlayer(who); }
// the press on an ad-hold button: pointer down, a second of ink, pointer up
async function hold(c, sel) {
  const r = await c.ev(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); if (!e) return null; e.scrollIntoView({ block: "center" }); const b = e.getBoundingClientRect(); return { x: b.left + b.width / 2, y: b.top + b.height / 2 }; })()`);
  c.report.steps.push(`hold ${sel} -> ${r ? "ok" : "missing"}`);
  if (!r) return false;
  await c.cdp("Input.dispatchMouseEvent", { type: "mousePressed", button: "left", clickCount: 1, buttons: 1, ...r });
  await c.sleep(1250);
  await c.cdp("Input.dispatchMouseEvent", { type: "mouseReleased", button: "left", clickCount: 1, buttons: 0, ...r });
  await c.settle(500);
  return true;
}
const visible = (c, sel) => c.ev(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); if (!e) return false; const r = e.getBoundingClientRect(); return !!(r.width && r.height); })()`);

export const flows = [
  accounts,
  rich,
  ["prologue", async (c) => {
    // season21 and week7 characters start in the first-minute opening and never see the hut: this one is put there, it is staged, not walked into.
    c.log("hut", JSON.stringify(await c.py("from tianxia import prologue as pr\nst = chars.load('新人乙'); pr.begin(st, content); chars.save(st); out = st.player.location")));
    await c.asPlayer("p4");
    const walked = [];
    for (let i = 0; i < 24; i++) {
      const m = await c.api("p4", "/api/main");
      const pro = m.json && m.json.prologue;
      if (!pro) break;
      await c.shoot(`pro_${String(i).padStart(2, "0")}`, { who: "p4" });
      // the glowing thing first (a tab already open does not count), then a question being asked, then the first thing the scene offers
      const pressed = await c.ev(`(() => { const vis = (el) => { const r = el.getBoundingClientRect(); return r.width && r.height; };
        const glow = [...document.querySelectorAll(".glow")].find((e) => vis(e) && !e.disabled && !(e.dataset.act === "tab" && e.dataset.tab === S.tab));
        const slotIn = [...document.querySelectorAll('[data-act="slot-in"]')].find(vis);
        const hub = [...document.querySelectorAll('[data-act="forge-hub"]:not([disabled]), [data-act="forge"]:not([disabled])')].find(vis);
        const pick = slotIn || glow || hub || document.querySelector('[data-act="ask-yes"]') || [...document.querySelectorAll('[data-act="choose"]:not([disabled])')].find(vis);
        if (!pick) return ""; if (window.__qaReseed) window.__qaReseed(); if (pick.click) pick.click(); else pick.dispatchEvent(new MouseEvent("click", { bubbles: true })); return (pick.dataset.act || "") + ":" + (pick.dataset.id || pick.dataset.tab || pick.dataset.op || ""); })()`);
      walked.push(pressed);
      if (!pressed || (walked.length >= 3 && walked.slice(-3).every((x) => x === pressed))) break;  // stuck: how far it got is in the facts
      await c.settle(500);
    }
    c.report.facts.prologue_walk = walked;
    c.log("prologue walked", JSON.stringify(walked));
  }],
  ["map_away", async (c) => {
    await c.asPlayer("p1");
    await c.tab("map");
    await c.shoot("map_there", { who: "p1" });
    await c.tab("jianghu");
    await c.shoot("map_away", { who: "p1" });
  }],
  ["divine_form", async (c) => {
    const forge = async () => {
      const pot = await c.py(`out = stage.divine_recipe(chars, content, world, '沈浪')`);
      if (!pot) return null;
      const r = await c.api("p1", "/api/do/smith_forge", pot);
      return { pattern: pot.pattern, status: r.status };
    };
    await c.leave();
    await place(c, "沈浪", "wan_city");
    await c.api("p1", "/api/main");
    await c.api("p1", "/api/choose", { id: "act:smith" });
    const got = await forge();
    c.log("divine", JSON.stringify(got));
    c.report.facts.divine_staged = !!got;
    const rack = async () => { await c.asPlayer("p1"); await c.click('[data-act="shop-tab"][data-tab="rack"]'); };
    await rack();
    const form = await c.ev(`!!document.querySelector("form.naming.divine")`);
    c.report.facts.divine_form = form;
    if (form) {
      await c.shoot("dv_form", { who: "p1" });
      c.log("sent name", await c.fillAndSend("form.naming.divine input[name=name]", "試鋒"));
      await c.settle(800);
      await c.shoot("dv_named", { who: "p1" });
    }
    await c.leave();
    c.log("divine again", JSON.stringify(await forge()));
    await rack();
    await c.step(ACT("shop-divine-keep"), "dv_keep", { who: "p1" });
    await c.leave();
    await c.api("p1", "/api/choose", { id: "smith:back" });
  }],
  ["brew", async (c) => {
    // the brew cell only sits where the rack has none of that tier
    await c.py(`st = chars.load('沈浪'); st.player.furnace_ready = True; st.player.materials.pop('gang_2', None); chars.save(st); out = 1`);
    await place(c, "沈浪", "wan_city");
    await enterShop(c, "p1", "act:smith");
    await c.click('[data-act="shop-tab"][data-tab="forge"]');
    await c.shoot("br_forge", { who: "p1" });
    const mainNow = await c.api("p1", "/api/main");
    c.log("trade", JSON.stringify(((mainNow.json && mainNow.json.shop && mainNow.json.shop.trade) || {}).upgrade || []).slice(0, 400));
    const r = await c.step('[data-act="shop-brew"]:not(.off)', "br_ask", {});
    c.report.facts.brew = r;
    if (r === "ok") await c.step(YES, "br_done", { who: "p1", wait: 800 });
    await c.leave();
    await c.api("p1", "/api/choose", { id: "smith:back" });
  }],
  ["figure_talk", async (c) => {
    await c.leave();
    const given = await c.py(`out = stage.persuade_errand(chars, content, '沈浪', 'luzhi', 'luzhi_persuade')`);
    c.log("errand", JSON.stringify(given));
    c.report.facts.persuade_staged = !!given;
    await c.load("/");
    await c.shoot("fg_at_target", { who: "p1" });
    if (given) {
      const r = await c.step(CH(`errand:persuade:${given.id}`), "fg_persuade_form", {});
      c.report.facts.persuade_button = r;
      if (await c.ev(`!!document.querySelector("#persuade-form")`)) {
        c.log("persuade", await c.fillAndSend("#persuade-form input[name=text]", "放下刀槍回家吧"));
        await c.settle(1500);
        await c.shoot("fg_persuaded", { who: "p1" });
      }
    }
    // talking with a figure, the model on a dead port: the fallback line
    await c.leave();
    await place(c, "沈浪", "luzhi_camp");
    await c.load("/");
    const fig = await c.click('[data-act="fig-open"]');
    c.report.facts.figure_open = fig;
    if (fig === "ok") {
      await c.shoot("fg_open", { who: "p1" });
      const talk = await c.step(ACT("fig-talk"), "fg_talk", { who: "p1", wait: 1500 });
      c.report.facts.figure_talk = talk;
      if (await c.ev(`!!document.querySelector("#free-form input")`)) {
        c.log("said", await c.fillAndSend("#free-form input", "近來可好"));
        await c.settle(2500);
        await c.shoot("fg_talk_fallback", { who: "p1" });
      }
    }
    await c.load("/");
    await c.leave();
    await place(c, "沈浪", "wan_city");
    await c.load("/");
  }],
  ["mall_buy", async (c) => {
    await c.leave();
    await c.py(`out = stage.give_ingots(world, CLOCK['now'], ['沈浪', '白飛'], 50000)`);
    await c.py(`out = stage.look_order(world, content, '沈浪', '待撤青衫', CLOCK['now'])`);
    await c.asPlayer("p1");
    const open = async () => { await c.load("/"); await c.click(ACT("mall-open")); };
    await open();
    await c.shoot("ml_shop", { who: "p1" });
    const items = await c.ev(`[...document.querySelectorAll('[data-act="mall-pick"]:not([disabled])')].map((e) => e.dataset.id)`);
    c.report.facts.mall_items = (items || []).length;
    const r = await c.step(ACT("mall-pick"), "ml_ask", {});
    if (r === "ok") await c.step(YES, "ml_bought", { who: "p1", wait: 800 });
    await open();
    await c.step(ACT("mall-claim"), "ml_claim", { who: "p1", wait: 600 });
    const look = async () => { await open(); await c.click('[data-act="mall-tab"][data-tab="look"]'); };
    await look();
    await c.shoot("ml_look", { who: "p1" });
    // the order still waiting for its pictures can be taken back
    const make = async () => { await look(); await c.click('[data-act="look-seg"][data-seg="mine"]'); await c.click('[data-act="look-sub"][data-sub="make"]'); };
    await make();
    await c.shoot("ml_make", { who: "p1" });
    const w = await c.step(ACT("look-withdraw"), "ml_withdraw_ask", {});
    c.report.facts.look_withdraw = w;
    if (w === "ok") await c.step(YES, "ml_withdrawn", { who: "p1", wait: 700 });
    // one that is made: on the market, sold to the other one
    await c.leave();
    const made = await c.py(`out = stage.look_order(world, content, '沈浪', '上架青衫', CLOCK['now'], made=True)`);
    c.log("made", JSON.stringify(made));
    await make();
    await c.click('[data-act="look-fold"][data-what="sell"]');  // what is not listed yet is folded away
    const sell = await c.step(ACT("look-sell"), "ml_sell_form", {});
    c.report.facts.look_sell = sell;
    if (sell === "ok") await c.step(ACT("market-list"), "ml_listed", { who: "p1", wait: 700 });
    await c.leave();
    await c.asPlayer("p2");
    await c.click(ACT("mall-open"));
    await c.click('[data-act="mall-tab"][data-tab="look"]');
    await c.step('[data-act="look-seg"][data-seg="market"]', "ml_p2_market", { who: "p2" });
    await c.click('[data-act="look-pick"]');
    const buy = await c.step(ACT("market-buy"), "ml_market_ask", {});
    c.report.facts.market_buy = buy;
    if (buy === "ok") await c.step(YES, "ml_market_bought", { who: "p2", wait: 700 });
    await c.load("/");
    await c.click(ACT("mall-open"));
    await c.click('[data-act="mall-tab"][data-tab="look"]');
    await c.click('[data-act="look-seg"][data-seg="mine"]');
    await c.click(`[data-act="look-pick"][data-id="${made && made.look}"]`);
    const wear = await c.step(ACT("look-wear"), "ml_look_wear", { who: "p2" });
    c.report.facts.look_wear = wear;
    await c.asPlayer("p1");
  }],
  ["admin_six", async (c) => {
    await c.asPlayer("admin");
    const ad = async (tab) => { await c.load("/admin"); if (tab) await c.click(`[data-act="ad-tab"][data-tab="${tab}"]`); };
    await ad();
    const tabs = [...new Set(await c.ev(`[...document.querySelectorAll('[data-act="ad-tab"]')].map((b) => b.dataset.tab)`))];
    // the two that need a press held for a second
    for (const op of ["pause_clock", "resume_clock"]) {
      let found = false;
      for (const t of tabs) {
        await ad(t);
        if (await visible(c, `[data-act="ad-hold"][data-op="${op}"]`)) {
          found = await hold(c, `[data-act="ad-hold"][data-op="${op}"]`);
          if (found) await c.shoot(`ad_hold_${op}`, { who: "admin" });
          break;
        }
      }
      c.report.facts[`admin_${op}`] = found;
    }
    // fire: needs the select with an event in it
    for (const t of tabs) {
      await ad(t);
      if (await visible(c, "#ad-fire")) {
        const r = await c.click(OP("fire"));
        c.report.facts.admin_fire = r;
        if (r === "ok") {
          await c.shoot("ad_fire", { who: "admin" });
          if ((await c.click(YES)) === "ok") { await c.settle(700); await c.shoot("ad_fire_yes", { who: "admin" }); }
        }
        break;
      }
    }
    // the three in the panel of a player looked up by name
    for (const op of ["summon", "give_opportunity", "give_fragment"]) {
      let got = "no panel";
      for (const t of tabs) {
        await ad(t);
        if (!(await visible(c, "#ad-player-form input[name=name]"))) continue;
        c.log("lookup", await c.fillAndSend("#ad-player-form input[name=name]", "沈浪"));
        await c.settle(700);
        got = await c.click(OP(op));
        if (got === "ok") {
          await c.shoot(`ad_${op}`, { who: "admin" });
          if ((await c.click(YES)) === "ok") { await c.settle(700); await c.shoot(`ad_${op}_yes`, { who: "admin" }); }
        }
        break;
      }
      c.report.facts[`admin_${op}`] = got;
    }
    await c.load("/");
  }],
  ["fold_mvp", async (c) => {
    await c.leave();
    await c.api("p3", "/api/choose", { id: "growth:balanced" });
    await c.api("p3", "/api/choose", { id: "choice:2" });
    await c.py("out = stage.rich(chars, content, '新人甲', 'yingchuan', level=10)");
    await place(c, "沈浪", "wan_city");
    await place(c, "白飛", "wan_city");
    c.log("start", (await c.api("admin", "/api/do/start_battle", { id: "wancheng_yi" })).status);
    await c.api("p1", "/api/choose", { id: "battle:join:guan" });
    await c.api("p2", "/api/main");
    await c.api("p2", "/api/choose", { id: "battle:join:huang" });
    for (let hop = 0; hop < 6; hop++) {
      await c.py("CLOCK['now'] += 600; out = 1");
      await c.api("admin", "/api/do/fast_forward", { hours: 1 });
      const m = await c.api("p1", "/api/main");
      await c.api("p2", "/api/main");
      if (m.json && m.json.battle_gauge && m.json.battle_gauge.phase === "active") break;
    }
    // far away and not in it: the battlefield folds into one line
    await place(c, "新人甲", "zhuo_county");
    await c.api("p3", "/api/main");
    await c.asPlayer("p3");
    const fold = await c.ev(`!!document.querySelector('[data-act="battle-open"]')`);
    c.report.facts.battle_fold = fold;
    await c.shoot("fold_shut", { who: "p3" });
    if (fold) await c.step('[data-act="battle-open"]', "fold_open", { who: "p3" });
    // the main general of the army badly hurt, shot before the overlay is closed; then a second general falls
    await c.leave();
    await c.py("out = stage.chief_pct(world, 'guan', 0, 25)");
    await c.asPlayer("p1");
    await c.shoot("chief_hurt_guan", { who: "p1" });
    await closeOv(c);
    await c.shoot("chief_hurt_guan_panel", { who: "p1" });
    await c.leave();
    await c.py("out = stage.chief_fall(world, 'guan', 1, '白飛')");
    await c.load("/");
    await c.shoot("chief_fall_guan", { who: "p1" });
    await closeOv(c);
    // the round that just settled has its best: only that round's /api/main says so
    await c.leave();
    const m1 = await c.api("p1", "/api/main");
    const id1 = moveOf(m1, 0);
    if (id1) await c.api("p1", "/api/choose", { id: id1 });
    const m2 = await c.api("p2", "/api/main");
    const id2 = moveOf(m2, 0);
    if (id2) await c.api("p2", "/api/choose", { id: id2 });
    await c.py("CLOCK['now'] += 200; out = 1");
    await c.api("p1", "/api/main");
    await c.py("out = stage.mvp_now(world, '沈浪')");
    const after = await c.api("p1", "/api/main");
    c.report.facts.mvp_round = after.json && after.json.battle_mvp ? after.json.battle_mvp.round : null;
    if (after.json && after.json.battle_mvp) {
      await c.load("/", { keepCards: true });
      await c.shoot("mvp_first", { who: "p1" });
      await c.step(ACT("mvp-close"), "mvp_closed", { who: "p1" });
      await c.step(ACT("mvp-replay"), "mvp_replay", {});
      await c.step(ACT("mvp-again"), "mvp_again", { light: true });
      await c.step(ACT("mvp-close"), null);
    }
    // the closing overlay: six seconds and it is gone, for real this once
    await c.ev(`sessionStorage.setItem("__qa_nohold", "1"); 0`);
    await c.leave();
    for (let hop = 0; hop < 16; hop++) {
      const m = await c.api("p1", "/api/main");
      if (!m.json || !m.json.battle_gauge) break;
      const id = moveOf(m, hop % 3);
      if (id) await c.api("p1", "/api/choose", { id });
      const q = await c.api("p2", "/api/main");
      const idq = moveOf(q, 0);
      if (idq) await c.api("p2", "/api/choose", { id: idq });
      await c.py("CLOCK['now'] += 200; out = 1");
    }
    await c.api("p1", "/api/main");
    await c.load("/", { keepCards: true });
    const auto = await c.ev(`(async () => { const had = !!document.getElementById("bp-ov"); await new Promise((r) => setTimeout(r, 6600)); return { had, after: !!document.getElementById("bp-ov"), hold: window.__qaHold }; })()`);
    c.report.facts.close_overlay = auto;
    await c.ev(`sessionStorage.removeItem("__qa_nohold"); 0`);
    await c.load("/");
  }],
  x_week2,
  ["week_card", async (c) => {
    // the letter card covers the strip; the step card only shows for someone with a step to take
    let who = "p1";
    for (const w of ["p1", "p2", "p3", "p4"]) {
      const m = await c.api(w, "/api/main");
      const steps = m.json && m.json.week_card && m.json.week_card.steps;
      c.log("week steps", w, JSON.stringify((steps || []).map((s) => s.kind)));
      if (steps && steps.length) { who = w; break; }
    }
    await c.asPlayer(who);
    await c.declineLetters(who);
    await c.shoot("wk_clean", { who });
    // on a phone the first-screen fit folds the card away; on a wide window it stays
    const wide = async () => { await c.setView(c.VIEWS[2], 1); await c.stable(c.VIEWS[2][1]); };
    await wide();
    await c.step('[data-act="wk"][data-id="step"]', "wk_step_open", { who });
    await wide();
    const next = await c.step(ACT("wk-next"), "wk_next", { who });
    c.report.facts.wk_next = next;
    await wide();
    const hide = await c.step('[data-act="wk-hide"][data-id="card"]', "wk_hide_card", { who });
    c.report.facts.wk_hide_card = hide;
    await c.load("/");
    await c.step('[data-act="wk-hide"][data-id="strip"]', "wk_hide_strip", { who });
    await c.load("/");
  }],
  ["ring", async (c) => {
    await c.leave();
    await place(c, "白飛", "wan_city");
    await c.api("p2", "/api/main");
    await c.api("p2", "/api/choose", { id: "act:arena" });
    await c.api("p2", "/api/choose", { id: "arena:join" });
    await c.api("p2", "/api/choose", { id: "arena:back" });
    await place(c, "沈浪", "wan_city");
    await enterShop(c, "p1", "act:arena");
    await c.step(CH("arena:join"), "ring_joined", { who: "p1" });
    const opts = await c.api("p1", "/api/main");
    c.log("arena options", JSON.stringify((opts.json.options || []).map((o) => o.id + (o.enabled ? "" : "!"))).slice(0, 300));
    await c.step('[data-act="choose"][data-id^="arena:fight"]:not([disabled])', "ring_fight", { who: "p1" });
    // the canvas does not compare by pixels: the DOM, and whether it drew anything (facts.canvas on each scene)
    const drew = await c.ev(`(() => { const e = document.getElementById("ring-stage"); return e ? [e.width, e.height] : null; })()`);
    c.report.facts.ring_stage = drew;
    await c.step(CH("arena:強攻"), "ring_round", { who: "p1", wait: 900 });
    await c.load("/");
  }],
];
