// The admin page pressed for real. Wave B's round 5.
import { ACT, ACCOUNTS, accounts, rich } from "./common.mjs";
import { x_week2 } from "./x.mjs";

export { ACCOUNTS };
const OP = (op) => `[data-act="admin"][data-op="${op}"]:not([disabled])`;
export const flows = [
  accounts,
  rich,
  x_week2,
  ["z_admin", async (c) => {
    await c.asPlayer("admin");
    const ad = async (tab) => { await c.load("/admin"); if (tab) await c.click(`[data-act="ad-tab"][data-tab="${tab}"]`); };
    await ad();
    const tabs = await c.ev(`[...document.querySelectorAll('[data-act="ad-tab"]')].map((b) => b.dataset.tab)`);
    const uniq = [...new Set(tabs)];
    c.log("admin tabs", JSON.stringify(uniq));
    const ops = {};
    for (const t of uniq) {
      await ad(t);
      await c.shoot(`z_ad_${t}`, { who: "admin" });
      ops[t] = await c.ev(`[...document.querySelectorAll('[data-act="admin"]:not([disabled])')].filter((b) => b.getBoundingClientRect().width).map((b) => b.dataset.op)`);
      if (await c.ev(`!!document.querySelector('[data-act="ad-find"]')`)) {
        await c.ev(`(() => { for (const i of document.querySelectorAll("input.input")) { if (i.getBoundingClientRect().width) { i.value = "沈浪"; i.dispatchEvent(new Event("input", { bubbles: true })); } } return 1; })()`);
        await c.step(ACT("ad-find"), `z_ad_${t}_find`, { who: "admin", wait: 700 });
        await c.step(ACT("ad-pick"), `z_ad_${t}_pick`, { who: "admin", wait: 700 });
        await c.step(ACT("ad-result-close"), `z_ad_${t}_close`, { light: true });
      }
      await ad(t);
      await c.step('[data-act="ad-hold"]:not([disabled])', `z_ad_${t}_hold`, { light: true });
      await c.step('[data-act="ad-gen"]:not([disabled])', `z_ad_${t}_gen`, { light: true });
    }
    c.log("admin ops", JSON.stringify(ops).slice(0, 600));
    // the safe ones, for real; the answer is drawn the same way a click draws it
    const tabOf = (op) => uniq.find((t) => (ops[t] || []).includes(op));
    for (const op of ["pause_clock", "resume_clock", "push_trend", "set_trend", "xingshi_now", "fire", "issue_orders", "rotate_seats", "summon", "give_fragment", "give_opportunity", "conquest_progress", "seal_stir", "fast_forward"]) {
      const t = tabOf(op);
      if (!t) { c.log("no button for", op); continue; }
      await ad(t);
      const r = await c.click(OP(op));
      if (r !== "ok") { c.log("op", op, r); continue; }
      await c.settle(500);
      await c.shoot(`z_op_${op}`, { who: "admin" });
      const y = await c.click('[data-act="ask-yes"]');
      if (y === "ok") { await c.settle(700); await c.shoot(`z_op_${op}_yes`, { who: "admin" }); }
      await c.step(ACT("ad-result-close"), `z_op_${op}_close`, { light: true });
    }
    await c.load("/");
    await c.shoot("z_admin_game", { who: "admin" });
    await c.asPlayer("p1");
    await c.shoot("z_p1_after_admin", { who: "p1" });
    await c.tab("news");
    await c.shoot("z_p1_news", { who: "p1" });
    await c.crawl("zn", async () => { await c.load("/"); await c.tab("news"); }, ["news"], { depth: 2, total: 10, cap: 8 });
  }],
];
