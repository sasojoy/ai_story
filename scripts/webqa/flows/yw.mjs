// Batch 256: the strange tales (yiwen package). Only this round's server turns them on (serve.py, QA_ROUND == "yw"; both rolls always hit),
// so a new character meets one on the first trip out in the 潁川 wilds (batch 256 measured: the town, the roads, the fords, the temple and
// the academy put an event or an insight first; the wilds do not). The model is the dead port: the storyteller fails twice and the stand-in
// lines are stored, so the pages are fixed. What the walk shoots, in order:
//   yw_out    the meeting card open; put away over the trip's card, on the 江湖 page and the hero page (the strip); back from the
//             strip (batch 272: no longer from the menu and the rules: see the end of yw_out);
//   yw_walk   自己說 with words typed and not sent, one the word list refuses, the 等說書人 page (held, see below), the first act,
//             自己說 held again and 停 on its waiting page, the second act it wrote, the line serve.py screens bad (once, then until
//             the box is spent), the third act with the closing card, back to the game;
//   yw_trail  the second account meets the same tale (a walked one: replayed, its 自己說 box greyed), its first act, put away.
// The waiting page is gone in an instant on the dead port: serve.py holds writer.write_scene while the walk has hold['armed'], and the walk
// releases it when the picture is taken (finally: a flow that throws must not leave a request hanging).
import { CH, ACT, place, ACCOUNTS, accounts } from "./common.mjs";

export { ACCOUNTS };
const BAD = "瞎說一通"; // serve.py YW_BAD_WORDS: the one line its fake screen calls bad
const arm = (c) => c.py("hold['armed'] = True; hold['event'].clear(); out = 1");
const release = (c) => c.py("hold['armed'] = False; hold['event'].set(); out = 1");
async function until(c, expr, ms = 20000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    if (await c.ev(expr).catch(() => false)) return true;
    await c.sleep(100);
  }
  c.report.steps.push(`yw: still waiting after ${ms} ms for ${expr.slice(0, 80)}`);
  return false;
}
// a step that writes a scene takes two calls to the dead port (about 4 s each here): wait until the page has its answer
const answered = (c) => until(c, `!document.querySelector(".yw-waiting") && !(window.__inflight || 0)`, 40000);
// outside the click helper, so nothing settles on the held request
const press = (c, sel) => c.ev(`(() => { const el = document.querySelector(${JSON.stringify(sel)}); if (!el || el.disabled) return "missing"; el.click(); return "ok"; })()`);
async function typeOnly(c, text) {
  const r = await c.ev(`(() => { const e = document.querySelector("#yw-say-form input"); if (!e) return "missing"; e.value = ${JSON.stringify(text)}; e.dispatchEvent(new Event("input", { bubbles: true })); return "ok"; })()`);
  c.report.steps.push(`yw: type ${text} -> ${r}`);
}
async function say(c, text) {
  const r = await c.fillAndSend("#yw-say-form input", text);
  c.report.steps.push(`yw: say ${text} -> ${r}`);
  await c.settle(300);
  await answered(c);
}
// one trip out from the explore wheel: one stretch, tapped through; the meeting card comes up over the trip's last card
async function tripOut(c) {
  await c.click('[data-act="wheel"][data-key="explore"]');
  await c.click('[data-act="outing-go"][data-n="1"]:not([disabled])', { wait: 1500 });
  if (await c.ev(`!!document.querySelector('[data-act="outing-tap"]:not([disabled])')`)) await c.click(ACT("outing-tap"), { wait: 800 });
}
const SIGN = '#yw-pop [data-act="yw-step"]:not([disabled])';

export const flows = [
  accounts,
  ["yw_out", async (c) => {
    for (const w of ["p1", "p2"]) {
      await c.api(w, "/api/choose", { id: "growth:balanced" });
      await c.api(w, "/api/choose", { id: "choice:2" });
    }
    await place(c, "沈浪", "yingchuan_wilds");
    await c.asPlayer("p1");
    await tripOut(c);
    await c.shoot("yw_meet", { who: "p1" });
    // put away over the trip: the trip's card offers the tale (yiwen:open) and 放下 as its menu
    // batch 273: hiding redraws the 江湖頁 under the trip's card with a new <img decoding="async"> for the place; wait until every picture
    // on the page is loaded and decoded before the scene (batch 272 f2 and batch 273 w1: 7724 px, 38 levels on the words over that picture)
    if ((await c.click(ACT("yw-hide"))) === "ok") {
      const IMGS = `[...document.querySelectorAll("img")]`;
      for (let i = 0; i < 50 && !(await c.ev(`${IMGS}.every((i) => i.complete)`)); i++) await c.sleep(100);
      await c.ev(`Promise.all(${IMGS}.filter((i) => i.naturalWidth > 0).map((i) => i.decode().catch(() => 0))).then(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r(1)))))`);
      await c.shoot("yw_hidden_trip", { who: "p1" });
    }
    await c.load("/");
    // put away on the 江湖 page: the strip at the top. There is no explore wheel while a tale waits (the menu is yiwen:open and yiwen:drop
    // only), so the strip is shot on the 江湖 page and on the hero page
    await c.step(ACT("yw-hide"), "yw_hidden", { who: "p1" });
    await c.tab("practice");
    await c.shoot("yw_track_hero", { who: "p1" });
    await c.step(ACT("yw-show"), "yw_shown", { who: "p1" });
    await c.step(ACT("yw-hide"), "", {});
    await c.tab("jianghu");
    // batch 272: yw_reopen (yiwen:open on the 江湖 page) and yw_help after it are not walked any more. On the new 江湖頁 an option that
    // is neither a place nor a duty is a row of the 軍務 list's 此地還能 (web/jianghu.js jhKinds), and 沈浪 here is a 散人: his third cell
    // is 投靠 (jhDutyCell -> jhJoinCell), so no cell pulls that list up. The strip on the hero page (yw_shown) is the way back here.
    // If the page gets a way to it for a 散人, walk it again with stepVia(c, CH("yiwen:open"), DUTY, ...) and yw-help after it.
    // batch 273: the options this 散人 has here, as a log line (nothing shot): what no cell of the new page pulls up
    const opts = await c.api("p1", "/api/main");
    c.log("sanren options", JSON.stringify(((opts.json && opts.json.options) || []).map((o) => o.id)));
  }],
  ["yw_walk", async (c) => {
    await c.load("/");
    await typeOnly(c, "他在等人");
    await c.shoot("yw_typed_draft", { who: "p1" });
    await say(c, "公告一則");
    await c.shoot("yw_typed_refused", { who: "p1" });
    try {
      await arm(c);
      c.report.steps.push(`yw: first sign -> ${await press(c, SIGN)}`);
      await until(c, `!!document.querySelector("#yw-pop .yw-waiting")`);
      await c.shoot("yw_wait", { who: "p1" });
    } finally { await release(c); }
    await answered(c);
    await c.shoot("yw_act1", { who: "p1" });
    // 停 on the second step (自己說, held): not on the last one. Held on the last step, the closing card's scene line 「名望 +5」 came
    // without its gap note on one side in one walk of three (batch 256 measured): the fame only comes with the last step
    try {
      await arm(c);
      const r = await c.fillAndSend("#yw-say-form input", "他在等人");
      c.report.steps.push(`yw: say 他在等人 (held) -> ${r}`);
      await until(c, `!!document.querySelector("#yw-pop .yw-waiting")`);
      await c.click(ACT("yw-stop"));
      await c.shoot("yw_wait_stop", { who: "p1" });
    } finally { await release(c); }
    await answered(c);
    await c.shoot("yw_act2", { who: "p1" });
    await say(c, BAD);
    await c.shoot("yw_typed_bad1", { who: "p1" });
    await say(c, BAD);
    await say(c, BAD);
    await c.shoot("yw_typed_spent", { who: "p1" });
    c.report.steps.push(`yw: last sign -> ${await press(c, SIGN)}`);
    await c.settle(300);
    await answered(c);
    await c.shoot("yw_close", { who: "p1" });
    await c.step(`#yw-pop ${CH("yiwen:drop")}`, "yw_back", { who: "p1", wait: 800 });
  }],
  ["yw_trail", async (c) => {
    await place(c, "白飛", "yingchuan_wilds");
    await c.asPlayer("p2");
    await tripOut(c);
    await c.shoot("yw_trail_meet", { who: "p2" });
    await c.step(SIGN, "yw_trail_act1", { who: "p2", wait: 600 });
    await c.step(ACT("yw-hide"), "yw_trail_hidden", { who: "p2" });
  }],
];
