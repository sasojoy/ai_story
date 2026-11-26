// Batch 272: the unfolding book (unfold package, on in week7 and season21 since 2026-11-25). Every other round's server turns it off
// (serve.py: their pages are the laid-out page an old character sees); only this round's leaves it on, so a new character at the 城門口
// opens a book and the page grows as it plays. What the walk shoots, in order:
//   uf_first      the 江湖 page just after the road is picked: the tabs not grown yet are not drawn, 輿圖 has just grown (its dot on)
//   uf_map_seen   back from the map: that dot is gone (/api/unfold/seen)
//   uf_attrs      a stat point on hand, synced: 俠客 has a dot
//   uf_hero       the hero page: the 屬性 sub-tab has its dot
//   uf_attrs_seen the 屬性 sub-tab open: its dot is gone
// A grow is written by a sync and a dot goes out when the page sends seen, so no picture waits a fixed time: each waits until what it
// shows is true in S.main.unfold (and no seen is on its way), and a wait that gives up is in the steps, the same on both sides.
import { CH, ACCOUNTS, accounts } from "./common.mjs";

export { ACCOUNTS };
async function until(c, expr, ms = 20000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    if (await c.ev(expr).catch(() => false)) return true;
    await c.sleep(100);
  }
  c.report.steps.push(`uf: still waiting after ${ms} ms for ${expr.slice(0, 80)}`);
  return false;
}
const BOOK = `(S.main && S.main.unfold)`;
const fresh = (k) => `!!${BOOK} && ${BOOK}.fresh.includes(${JSON.stringify(k)}) && !${BOOK}.hide.includes(${JSON.stringify(k)})`;
// nothing fresh is on the screen any more (web/unfold.js ufHere: what is open sends seen), and the answer is in
const quiet = `!!${BOOK} && !${BOOK}.fresh.some((k) => typeof ufHere === "function" && ufHere(k)) && !(window.__inflight || 0)`;
async function shootWhen(c, expr, name) {
  await until(c, expr);
  await c.settle(300);
  await c.shoot(name, { who: "p1" });
}
export const flows = [
  accounts,
  ["uf_open", async (c) => {
    await c.asPlayer("p1");
    // the 江湖新事 invite and the 改版資訊 sheet come over a new browser's first page: closed like a player, as main's prep does
    await c.load("/");
    if (await c.ev(`!!document.querySelector(".sheet.nx-invite")`)) {
      await c.click('.sheet.nx-invite [data-act="nx-open"]');
      await c.settle(600);
      await c.click('[data-act="nx-close"]');
      await c.settle(400);
      await c.load("/");
    }
    if (await c.ev(`!!document.querySelector(".sheet.patch-pop")`)) await c.load("/");
    if (await c.ev(`!!document.querySelector(".sheet.patch-pop")`)) {
      await c.click('.sheet.patch-pop [data-act="patch-close"]');
      await c.settle(260);
    }
    await c.step('[data-act="prep-pick"][data-preset="balanced"]', "");
    await c.step('[data-act="prep-growth"]', "");
    await c.step(CH("choice:2"), "");
    await c.load("/");
    await shootWhen(c, `${fresh("tab:map")} && !!document.querySelector('.tabs [data-tab="map"]')`, "uf_first");
    await c.tab("map");
    await until(c, quiet);
    await c.load("/");
    await shootWhen(c, `!!${BOOK} && !${BOOK}.fresh.includes("tab:map")`, "uf_map_seen");
  }],
  ["uf_grow", async (c) => {
    await c.py("st = chars.load('沈浪'); st.player.stat_points = max(1, st.player.stat_points); chars.save(st); out = 1");
    await c.api("p1", "/api/main");
    await c.load("/");
    await shootWhen(c, fresh("hero:attrs"), "uf_attrs");
    await c.tab("practice");
    await until(c, quiet);
    await shootWhen(c, `${quiet} && !!document.querySelector('[data-act="hero-tab"][data-tab="attrs"]')`, "uf_hero");
    await c.click('[data-act="hero-tab"][data-tab="attrs"]');
    await shootWhen(c, `${quiet} && !${BOOK}.fresh.includes("hero:attrs")`, "uf_attrs_seen");
  }],
];
