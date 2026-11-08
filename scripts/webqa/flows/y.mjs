// The last gaps of wave B: the duel, the sortie, the craft and smith corners, figures. Round 4.
import { CH, CHP, ACT, place, ACCOUNTS, accounts, rich } from "./common.mjs";
import { x_week2 } from "./x.mjs";

export { ACCOUNTS };
export const flows = [
  accounts,
  rich,
  x_week2,
  ["y_duel", async (c) => {
    await c.py(`
from tianxia.features.seal import seal
from tianxia.world_state import SealDuel, SealSide
name = '沈浪'
def side(n):
    return SealSide(name=n, power=80.0, scores={'強攻': 60.0, '固守': 60.0, '奇襲': 60.0}, role='', hp=300.0, hp_cap=300.0, last_seen=CLOCK['now'])
def fn(shared):
    reg = seal.filled(shared.seal, content)
    sid = next(iter(content.seal))
    shard = reg.shards[sid]
    shard.state, shard.holder, shard.since_season = 'held', name, shared.season_number
    seal.log(reg, shared.season_number, 'assign', shard=shard.id, holder=name)
    shared.seal_duels = [SealDuel(id='7:' + sid, shard=sid, record=7, where='長社火攻', phase='active', starts_real=CLOCK['now'], opened_real=CLOCK['now'], challenger=side('白飛'), holder=side(name), cap=0.25)]
world.mutate(fn)
out = 1`);
    const d = await c.api("p1", "/api/main");
    c.log("seal_duel", JSON.stringify(d.json.status.seal_duel || null).slice(0, 200), JSON.stringify(d.json.options.map((o) => o.id).filter((x) => x.startsWith("seal:"))));
    await c.asPlayer("p1");
    await c.ev(`(() => { const e = document.querySelector(".seal-duel"); if (e) e.scrollIntoView({ block: "center" }); return !!e; })()`);
    await c.shoot("y_seal_duel", { who: "p1" });
    await c.step(CHP("seal:"), "y_seal_duel_move", { who: "p1" });
    await c.asPlayer("p2");
    await c.shoot("y_seal_duel_p2", { who: "p2" });
    await c.step(CHP("seal:"), "y_seal_duel_move_p2", { who: "p2", wait: 700 });
    await c.asPlayer("p1");
    await c.shoot("y_seal_duel_after", { who: "p1" });
    await c.py("def fn(shared):\n    shared.seal_duels = []\nworld.mutate(fn)\nout = 1");
    await c.api("p1", "/api/main");
  }],
  ["y_sortie", async (c) => {
    await c.py(`
from tianxia import conquest
with world.db.transaction():
    world.mutate_season(lambda s: conquest.flip(s, content, 'yingshui', 'huang'))
out = 1`);
    await c.api("admin", "/api/do/fast_forward", { hours: 2 });
    await c.py("st = chars.load('沈浪'); st.player.stamina = 240; st.player.sortie_cooldown_until = 0; st.player.sorties_today = 0; chars.save(st); out = 1");
    await place(c, "沈浪", "yingshui");
    await place(c, "白飛", "yingshui");
    await c.api("p2", "/api/main");
    await c.asPlayer("p1");
    await c.step(ACT("sortie-open"), "y_so_open", { who: "p1" });
    for (const r of [0, 1, 2]) await c.step(`[data-act="sortie-move"][data-round="${r}"]:not([disabled])`, `y_so_move${r}`, { light: true });
    await c.step(ACT("sortie-send"), "y_so_send", { who: "p1", wait: 700 });
    await c.load("/");
    await c.shoot("y_so_sent", { who: "p1" });
    await c.asPlayer("p2");
    await c.shoot("y_so_p2", { who: "p2" });
    await c.step(ACT("sortie-answer"), "y_so_p2_answer", { who: "p2" });
    await c.step(ACT("sortie-join"), "y_so_p2_join", { who: "p2" });
    for (const r of [0, 1, 2]) await c.step(`[data-act="sortie-move"][data-round="${r}"]:not([disabled])`, `y_so_p2_move${r}`, { light: true });
    await c.step(ACT("sortie-send"), "y_so_p2_send", { who: "p2", wait: 700 });
    await c.asPlayer("p1");
    await c.py("CLOCK['now'] += 900; out = 1");
    await c.api("admin", "/api/do/fast_forward", { hours: 1 });
    await c.api("p1", "/api/main");
    await c.load("/");
    await c.shoot("y_so_result", { who: "p1" });
    await c.step(ACT("rounds-more"), "y_so_rounds", {});
    await c.load("/");
    await c.tab("news");
    await c.shoot("y_so_news", { who: "p1" });
    await place(c, "沈浪", "wan_city");
    await place(c, "白飛", "wan_city");
    await c.api("p2", "/api/main");
  }],
  ["y_craft", async (c) => {
    const craft = async () => { await c.load("/"); await c.tab("practice"); await c.click('[data-act="tab"][data-tab="craft"]'); };
    await craft();
    await c.step(ACT("pot-open"), "y_cr_pot", {});
    await c.step('[data-act="pick"][data-id="feng"]', "y_cr_pick1", {});
    await c.step('[data-act="pick"][data-id="huo"]', "y_cr_pick2", {});
    await c.step(ACT("forge-hub"), "y_cr_forge", { who: "p1", wait: 3000 });
    await c.step(ACT("craft-ok"), "y_cr_ok", { who: "p1" });
    await c.step(ACT("switch"), "y_cr_switch", { who: "p1" });
    await c.load("/");
    await c.tab("practice");
    await c.step(ACT("create-open"), "y_ct_open", { who: "p1" });
    await c.step('[data-act="create-kind"]:not(.on)', "y_ct_kind", {});
    await c.step(ACT("create-pick"), "y_ct_pick", {});
    await c.step(ACT("create-begin"), "y_ct_begin", { who: "p1", wait: 1200 });
    await c.step(ACT("create-preset"), "y_ct_preset", {});
    await c.step(ACT("create-pose"), "y_ct_pose", {});
    await c.ev(`(() => { for (const i of document.querySelectorAll("textarea, input[type=text]")) { const r = i.getBoundingClientRect(); if (r.width) { i.value = "一招破萬軍，不留後手"; i.dispatchEvent(new Event("input", { bubbles: true })); } } return 1; })()`);
    await c.settle(200);
    await c.shoot("y_ct_typed", { light: true });
    await c.step(ACT("create-intent"), "y_ct_intent", { who: "p1", wait: 3000 });
    await c.step(ACT("create-reread"), "y_ct_reread", { wait: 2500 });
    await c.step(ACT("create-name"), "y_ct_name", { who: "p1", wait: 2500 });
    await c.step(ACT("create-reroll"), "y_ct_reroll", { who: "p1", wait: 2500 });
    await c.step(ACT("create-back"), "y_ct_back", { who: "p1" });
    await c.step(ACT("create-cancel"), "y_ct_cancel", { who: "p1" });
    await c.step('[data-act="ask-yes"]', "y_ct_cancel_yes", { who: "p1" });
    await c.step(ACT("create-close"), "y_ct_close", { who: "p1" });
    await c.load("/");
  }],
  ["y_smith", async (c) => {
    await c.py("st = chars.load('沈浪'); p = st.player; p.location = 'wan_city'; p.journey = None; p.materials = {k: v for k, v in p.materials.items() if k not in ('gang_2', 'rou_3', 'kuai_1')}; chars.save(st); out = 1");
    await c.load("/");
    await c.click(CH("act:smith"));
    await c.step('[data-act="shop-tab"][data-tab="forge"]', "y_sm_forge", { who: "p1" });
    await c.step('[data-act="shop-brew"]', "y_sm_brew", {});
    await c.step('.shop-layer [data-act="shop-brew"].on', "y_sm_brew_off", { light: true });
    await c.load("/");
    await c.step('[data-act="shop-tab"][data-tab="rack"]', "y_sm_rack", {});
    await c.step(ACT("rack-pick"), "y_sm_rack_pick", {});
    await c.load("/");
    await c.step(".shop-layer .shop-back", "y_sm_left", { who: "p1" });
  }],
  ["y_fig", async (c) => {
    await place(c, "沈浪", "wan_city");
    const fig = async () => { await c.load("/"); await c.click('[data-act="fig-open"][data-id="zhujun"]'); };
    await fig();
    await c.shoot("y_fig", { who: "p1" });
    await c.step(ACT("fig-log"), "y_fig_log", {});
    await c.step(ACT("fig-log-more"), "y_fig_log_more", { light: true });
    await c.step(ACT("fig-log-season"), "y_fig_log_season", { light: true });
    await c.step(ACT("fig-log-close"), "y_fig_log_close", { light: true });
    await fig();
    await c.step(ACT("fig-talk"), "y_fig_talk", { who: "p1", wait: 2500 });
    await c.crawl("yfg", () => c.load("/"), ["opt-why", "fig-log", "fig-close"], { total: 4, cap: 2 });
    await c.load("/");
    await c.step(ACT("fig-close"), "y_fig_close", { who: "p1" });
    await fig();
    await c.step(ACT("fig-act"), "y_fig_act", { who: "p1", wait: 1200 });
    await c.load("/");
    await c.shoot("y_fig_after", { who: "p1" });
  }],
];
