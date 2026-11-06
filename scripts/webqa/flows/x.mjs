// What the main walk did not reach: seals, gear, sorties, crafting from the panel, the push prompts. Wave B's round 3.
import { CH, CHP, ACT, place, UI, ACCOUNTS, accounts, rich } from "./common.mjs";

export { ACCOUNTS };
export const x_week2 = ["x_week2", async (c) => {
    c.log("ff", (await c.api("admin", "/api/do/fast_forward", { hours: 200 })).status);
    for (const [w] of ACCOUNTS) await c.api(w, "/api/main");
    for (let i = 0; i < 8; i++) await c.api("admin", "/api/do/cancel_battle", {});
    await place(c, "沈浪", "wan_city");
    await place(c, "白飛", "wan_city");
    await c.api("p2", "/api/main");
    await c.asPlayer("p1");
    await c.shoot("x_j", { who: "p1" });
  }];
export const flows = [
  accounts,
  rich,
  x_week2,
  ["x_jianghu", async (c) => {
    await c.load("/");
    await c.step('[data-act="wk"][data-id="why"]', "x_wk_why", { who: "p1" });
    await c.step(ACT("sides-first"), "x_sides_first", {});
    await c.step(ACT("wk-next"), "x_wk_next", {});
    await c.load("/");
    await c.step('[data-act="wk"][data-id="step"]', "x_wk_step", {});
    await c.step(ACT("wk-next"), "x_wk_next2", {});
    await c.load("/");
    await c.step(ACT("wk-hide"), "x_wk_hide", { who: "p1" });
    await c.load("/");
    await c.step(ACT("calls-more"), "x_calls", { who: "p1" });
    await c.crawl("xc", async () => { await c.load("/"); await c.click(ACT("calls-more")); }, ["opt-why", "fronts-help", "front-more"], { total: 4, cap: 2 });
    await c.load("/");
    await c.step(ACT("guide-more"), "x_guide_more", {});
    await c.step(ACT("guide-next"), "x_guide_next", { who: "p1" });
    await c.step(ACT("guide-shut"), "x_guide_shut", { who: "p1" });
    await c.step(ACT("guide-open"), "x_guide_open", { who: "p1" });
    await c.step(ACT("guide-ack"), "x_guide_ack", { who: "p1" });
  }],
  ["x_news", async (c) => {
    const news = async () => { await c.load("/"); await c.tab("news"); };
    await news();
    await c.shoot("x_news", { who: "p1" });
    await c.crawl("xn", news, ["news", "board", "board-card", "report-list", "report"], { depth: 3, total: 26, cap: 8 });
    await c.load("/");
    await c.tab("practice");
    await c.step('[data-act="news"]', "x_self_news", { who: "p1" });
  }],
  ["x_seal", async (c) => {
    await c.py(`
from tianxia import seal
name = '沈浪'
def _give(shared):
    reg = seal.filled(shared.seal, content)
    shard = reg.shards[next(iter(content.seal))]
    shard.state, shard.holder, shard.since_season = 'held', name, shared.season_number
    seal.log(reg, shared.season_number, 'assign', shard=shard.id, holder=name)
world.mutate(_give)
out = 1`);
    await c.api("p1", "/api/main");
    await c.load("/");
    const m = await c.api("p1", "/api/main");
    c.log("seal status", JSON.stringify(m.json.status.seal || null).slice(0, 300));
    await c.ev(`(() => { const e = document.querySelector(".seal-card"); if (e) e.scrollIntoView({ block: "center" }); return !!e; })()`);
    await c.shoot("x_seal_card", { who: "p1" });
    await c.step(ACT("seal-act-go"), "x_seal_go", { who: "p1", wait: 800 });
    await c.step(ACT("seal-act"), "x_seal_act", {});
    await c.step(ACT("seal-side"), "x_seal_side", {});
    await c.step(ACT("seal-pick"), "x_seal_pick", {});
    await c.step('[data-act="ask-no"]', "x_seal_pick_no", { light: true });
    await c.step(ACT("seal-act-close"), "x_seal_act_close", { light: true });
    await c.py(`
from tianxia.world_state import SealDuel, SealSide
def side(name):
    return SealSide(name=name, power=80.0, scores={'強攻': 60.0, '固守': 60.0, '奇襲': 60.0}, role='', hp=300.0, hp_cap=300.0, last_seen=CLOCK['now'])
def fn(shared):
    shared.seal_duels = [SealDuel(id='7:chishou', shard=next(iter(content.seal)), record=7, where='長社火攻', phase='active', starts_real=CLOCK['now'], opened_real=CLOCK['now'], challenger=side('白飛'), holder=side('沈浪'), cap=0.25)]
world.mutate(fn)
out = 1`);
    const d = await c.api("p1", "/api/main");
    c.log("seal_duel", JSON.stringify(d.json.status.seal_duel || null).slice(0, 300), JSON.stringify(d.json.options.map((o) => o.id).filter((x) => x.startsWith("seal:"))));
    await c.load("/");
    await c.ev(`(() => { const e = document.querySelector(".seal-duel"); if (e) e.scrollIntoView({ block: "center" }); return !!e; })()`);
    await c.shoot("x_seal_duel", { who: "p1" });
    await c.step(CHP("seal:"), "x_seal_duel_move", { who: "p1" });
    await c.api("p2", "/api/main");
    await c.asPlayer("p2");
    await c.shoot("x_seal_duel_p2", { who: "p2" });
    await c.asPlayer("p1");
    await c.py("def fn(shared):\n    shared.seal_duels = []\nworld.mutate(fn)\nout = 1");
    await c.api("p1", "/api/main");
  }],
  ["x_gear", async (c) => {
    const gear = async (key) => { await c.load("/"); await c.tab("practice"); await c.click('[data-act="hero-tab"][data-tab="gear"]'); await c.click(`[data-act="hero-node"][data-kind="gear"][data-key="${key}"]`); };
    for (const key of ["weapon", "armor", "mount", "treasure"]) {
      await gear(key);
      await c.shoot(`x_gear_${key}`, { who: "p1" });
      await c.step(ACT("rack-all"), `x_gear_${key}_all`, { light: true });
    }
    await gear("weapon");
    await c.step(ACT("wield"), "x_gear_wield", { who: "p1" });
    await gear("armor");
    await c.step(ACT("wield"), "x_gear_wield_armor", { who: "p1" });
    await gear("treasure");
    await c.step(ACT("seal-act"), "x_gear_seal_act", {});
    await c.step(ACT("seal-side"), "x_gear_seal_side", {});
    await c.step(ACT("seal-pick"), "x_gear_seal_pick", {});
    await c.step('[data-act="ask-no"]', "x_gear_seal_no", { light: true });
    await gear("weapon");
    await c.step(ACT("dismantle"), "x_gear_dismantle", {});
    await c.step('[data-act="ask-no"]', "x_gear_dismantle_no", { light: true });
    await c.load("/");
  }],
  ["x_sortie", async (c) => {
    await c.py(`
from tianxia import conquest
with world.db.transaction():
    world.mutate_season(lambda s: conquest.flip(s, content, 'yingshui', 'huang'))
st = chars.load('沈浪'); st.player.stamina = 240; st.player.sortie_cooldown_until = 0; st.player.sorties_today = 0; chars.save(st); out = 1`);
    await place(c, "沈浪", "yingshui");
    await place(c, "白飛", "yingshui");
    await c.api("p2", "/api/main");
    await c.load("/");
    await c.shoot("x_so_here", { who: "p1" });
    await c.step(ACT("sortie-open"), "x_so_open", { who: "p1" });
    for (const r of [0, 1, 2]) await c.step(`[data-act="sortie-move"][data-round="${r}"]:not([disabled])`, `x_so_move${r}`, { light: true });
    await c.step(ACT("sortie-send"), "x_so_send", { who: "p1", wait: 700 });
    await c.load("/");
    await c.shoot("x_so_sent", { who: "p1" });
    await c.asPlayer("p2");
    await c.shoot("x_so_p2", { who: "p2" });
    await c.step(ACT("sortie-answer"), "x_so_p2_answer", { who: "p2" });
    await c.step(ACT("sortie-join"), "x_so_p2_join", { who: "p2" });
    for (const r of [0, 1, 2]) await c.step(`[data-act="sortie-move"][data-round="${r}"]:not([disabled])`, `x_so_p2_move${r}`, { light: true });
    await c.step(ACT("sortie-send"), "x_so_p2_send", { who: "p2", wait: 700 });
    await c.asPlayer("p1");
    await c.py("CLOCK['now'] += 900; out = 1");
    await c.api("admin", "/api/do/fast_forward", { hours: 1 });
    await c.api("p1", "/api/main");
    await c.load("/");
    await c.shoot("x_so_result", { who: "p1" });
    await c.step(ACT("rounds-more"), "x_so_rounds", {});
    await c.load("/");
    await c.step(ACT("sortie-far"), "x_so_far", { who: "p1" });
    await place(c, "沈浪", "yingchuan_wilds");
    await c.load("/");
    await c.step(CH("act:duty"), "x_so_duty", { who: "p1" });
    await c.load("/");
    await c.step(ACT("duty-open"), "x_so_duty_open", {});
    await place(c, "沈浪", "wan_city");
  }],
  ["x_craft", async (c) => {
    const craft = async () => { await c.load("/"); await c.tab("practice"); await c.click('[data-act="tab"][data-tab="craft"]'); };
    await craft();
    await c.step(ACT("pot-open"), "x_cr_pot", {});
    await c.step('[data-act="pick"][data-id="feng"]', "x_cr_pick1", {});
    await c.step('[data-act="pick"][data-id="huo"]', "x_cr_pick2", {});
    await c.step(ACT("art-filter"), "x_cr_filter", { light: true });
    await c.step(ACT("craft-ok"), "x_cr_ok", { who: "p1" });
    await c.step(ACT("forge"), "x_cr_forge", { who: "p1", wait: 3000 });
    await c.step(ACT("switch"), "x_cr_switch", { who: "p1" });
    await c.step(ACT("craft-ok"), "x_cr_ok2", { who: "p1" });
    await craft();
    await c.step(ACT("secret-book"), "x_cr_secret", {});
    await c.step(ACT("secret-close"), "x_cr_secret_close", { light: true });
    await c.load("/");
    await c.tab("practice");
    await c.step(ACT("create-open"), "x_ct_open", { who: "p1" });
    await c.step('[data-act="create-kind"]:not(.on)', "x_ct_kind", {});
    await c.step(ACT("create-pick"), "x_ct_pick", {});
    await c.step(ACT("create-begin"), "x_ct_begin", { who: "p1", wait: 1200 });
    await c.load("/");
    await c.shoot("x_ct_form", { who: "p1" });
    await c.step(ACT("create-preset"), "x_ct_preset", {});
    await c.step(ACT("create-pose"), "x_ct_pose", {});
    await c.ev(`(() => { for (const i of document.querySelectorAll("textarea, .cr-intent input, input[type=text]")) { const r = i.getBoundingClientRect(); if (r.width) { i.value = "一招破萬軍，不留後手"; i.dispatchEvent(new Event("input", { bubbles: true })); } } return 1; })()`);
    await c.step(ACT("create-intent"), "x_ct_intent", { who: "p1", wait: 3000 });
    await c.load("/");
    await c.shoot("x_ct_after_intent", { who: "p1" });
    await c.step(ACT("create-reread"), "x_ct_reread", { wait: 2500 });
    await c.step(ACT("create-name"), "x_ct_name", { who: "p1", wait: 2500 });
    await c.step(ACT("create-reroll"), "x_ct_reroll", { who: "p1", wait: 2500 });
    await c.step(ACT("create-back"), "x_ct_back", { who: "p1" });
    await c.step(ACT("create-cancel"), "x_ct_cancel", { who: "p1" });
    await c.step('[data-act="ask-yes"]', "x_ct_cancel_yes", { who: "p1" });
    await c.step(ACT("create-close"), "x_ct_close", { who: "p1" });
    await c.load("/");
  }],
  ["x_smith", async (c) => {
    await c.py("out = stage.place(chars, '沈浪', 'wan_city')");
    await c.load("/");
    await c.click(CH("act:smith"));
    await c.step('[data-act="shop-tab"][data-tab="forge"]', "x_sm_forge", {});
    await c.step('[data-act="shop-brew"]', "x_sm_brew", {});
    await c.step(".shop-brew-go, [data-act=\"shop-brew-go\"]", "x_sm_brew_go", { who: "p1" });
    await c.load("/");
    await c.step('[data-act="shop-tab"][data-tab="divine"]', "x_sm_divine", {});
    await c.step('[data-act="dv-cell"]', "x_sm_dv1", {});
    await c.ev(`(() => { const s = [...document.querySelectorAll('[data-act="dv-cell"]')]; if (s[3]) s[3].click(); return s.length; })()`);
    await c.settle(300);
    await c.shoot("x_sm_dv2", {});
    await c.step('[data-act="book-open"]', "x_sm_book", {});
    await c.load("/");
    await c.step('.shop-layer .shop-back', "x_sm_left", { who: "p1" });
    await c.load("/");
  }],
  ["x_push", async (c) => {
    await c.cdp("Browser.grantPermissions", { permissions: ["notifications"], origin: c.PAGE });
    await c.load("/");
    await c.click(ACT("sheet"));
    await c.shoot("x_push_sheet", {});
    await c.step("#push-on", "x_push_on", { wait: 2500 });
    await c.step(ACT("push-test"), "x_push_test", { wait: 1200 });
    await c.step("#push-on", "x_push_off", { wait: 1500 });
    await c.load("/");
    await c.click(ACT("sheet"));
    await c.step(ACT("push-how"), "x_push_how", {});
    await c.step(ACT("push-yes"), "x_push_how_yes", { wait: 2500 });
    await c.step(ACT("push-how-back"), "x_push_how_back", { light: true });
    await c.step(ACT("sheet-close"), "x_push_close", { light: true });
    await c.load("/");
  }],
  ["x_peer", async (c) => {
    await place(c, "白飛", "wan_city");
    await c.api("p2", "/api/main");
    await c.load("/");
    const open = async () => { await c.load("/"); await c.click(ACT("peer")); };
    await open();
    await c.shoot("x_peer", { who: "p1" });
    await c.step(ACT("renown-peer"), "x_peer_renown", {});
    await c.crawl("xp", open, ["peer-pick", "peer-act", "peer-answer", "mt-zoom-peer", "renown-peer"], { total: 10, cap: 6, who: "p1" });
    await c.asPlayer("p2");
    await c.shoot("x_peer_p2", { who: "p2" });
    await c.step(ACT("peer-answer"), "x_peer_answer", { who: "p2" });
    await c.asPlayer("p1");
  }],
];
