// Melting for real, walking for real. Wave B's round 6.
import { CH, ACT, place, ACCOUNTS, accounts, rich } from "./common.mjs";
import { x_week2 } from "./x.mjs";

export { ACCOUNTS };
export const flows = [
  accounts,
  rich,
  x_week2,
  ["v_melt", async (c) => {
    await place(c, "沈浪", "wan_city");
    const prac = async () => { await c.load("/"); await c.tab("practice"); await c.click('[data-act="hero-tab"][data-tab="arts"]'); };
    await prac();
    await c.step('[data-act="mx"][data-op="practice"]:not([disabled])', "v_practice_go", { who: "p1", wait: 800 });
    await prac();
    await c.step(ACT("melt-mode"), "v_melt_mode", {});
    await c.step('[data-act="melt-pick"]:not([disabled])', "v_melt_pick", {});
    await c.step('[data-act="melt-pick-ins"]:not([disabled])', "v_melt_pick_ins", {});
    await c.step(ACT("melt-open"), "v_melt_open", {});
    await c.step(ACT("melt-go"), "v_melt_go", {});
    await c.step('[data-act="ask-yes"]', "v_melt_yes", { who: "p1", wait: 800 });
    await c.load("/");
    await c.tab("practice");
    await c.shoot("v_melt_after", { who: "p1" });
  }],
  ["v_move", async (c) => {
    await place(c, "沈浪", "wan_city");
    await c.load("/");
    await c.step('[data-act="wheel"][data-key="move"]', "v_wheel", { who: "p1" });
    await c.step('[data-act="move-mode"][data-mode="dash"]', "v_mode_dash", { who: "p1" });
    await c.step('[data-act="move-mode"][data-mode="walk"]', "v_mode_walk", { who: "p1" });
    await c.step(CH("move:yu_river"), "v_leave", { who: "p1", wait: 700 });
    await c.load("/");
    await c.shoot("v_on_road", { who: "p1" });
    await c.step('[data-act="choose"][data-id^="act:"]:not([disabled])', "v_on_road_act", { who: "p1" });
    await c.load("/");
    await c.tab("map");
    await c.shoot("v_on_road_map", { who: "p1" });
    await c.api("admin", "/api/do/fast_forward", { hours: 6 });
    await c.api("p1", "/api/main");
    await c.load("/");
    await c.shoot("v_arrived", { who: "p1" });
    // and the quick way from the map card
    await c.tab("map");
    await c.step('[data-act="map-place"][data-id="xinye"]', "v_map_card", {});
    await c.step('[data-act="map-travel"][data-mode="dash"]', "v_map_dash", { who: "p1", wait: 800 });
    await c.load("/");
    await c.shoot("v_map_dash_after", { who: "p1" });
  }],
];
