// Wave C's walk: the battle panel, the craft preview with two copies, one smoke each for 江湖 and 修練.
const CH = (id) => `[data-act="choose"][data-id="${id}"]`;
const ACT = (a) => `[data-act="${a}"]:not([disabled])`;
const place = (c, name, loc) => c.py(`out = stage.place(chars, '${name}', '${loc}')`);
export const ACCOUNTS = [["admin", "qaadmin", "QAadmin", "男"], ["p1", "qaplayer1", "沈浪", "男"], ["p2", "qaplayer2", "白飛", "女"], ["p3", "qaplayer3", "新人甲", "女"]];

// what each panel scene must say, compared between the two sides afterwards
const PANEL = `(() => { const q = (s) => document.querySelector(s); const t = (s) => { const e = q(s); return e ? e.innerText.replace(/\\s+/g, " ").trim() : null; };
  return { bp: !!q(".bp"), phase: q(".bp") ? q(".bp").style.getPropertyValue("--bp-bg") : null, title: t(".bp-t"), clock: t(".bp-clock"), hot: !!q(".bp-clock.hot"), ring: q(".bp-ring > i") ? q(".bp-ring > i").style.width : null,
    gens: [...document.querySelectorAll(".bp-gen")].map((e) => [e.className, e.innerText.replace(/\\s+/g, " ").trim(), e.querySelector(".bp-hp > i") ? e.querySelector(".bp-hp > i").style.width : null]),
    order: t(".bp-order"), moves: [...document.querySelectorAll(".bp-mv")].map((e) => [e.className, e.innerText.replace(/\\s+/g, " ").trim(), e.dataset.id]),
    free: q("#free-form") ? [q("#free-form").dataset.op, q("#free-form input").placeholder, q("#free-form").closest(".bp-wrap") ? "in-panel" : "outside"] : null,
    sent: t(".bp-sent"), feed: [...document.querySelectorAll(".bp-fr")].map((e) => e.innerText.replace(/\\s+/g, " ").trim()), hpbar: t(".bp-hpbar"), mini: t(".bp-mini"),
    wkStrip: !!q(".wk-strip"), wkSides: !!q(".wk-sides"), overlay: q("#bp-ov") ? [q("#bp-ov").className, q("#bp-ov").innerText.replace(/\\s+/g, " ").trim()] : null,
    waiting: !!q('[data-id="battle:waiting"]'), toast: (() => { const e = q("#toast"); return e && e.classList.contains("show") ? e.innerText : ""; })(),
    imgs: [...document.querySelectorAll(".bp-face img, #bp-ov img")].map((i) => [i.getAttribute("src"), i.complete && i.naturalWidth > 0]) }; })()`;

const fact = async (c, name) => { const f = await c.ev(PANEL); c.report.facts[name] = f; return f; };
const shot = async (c, name, opts = { who: "p1" }) => { const f = await fact(c, name); await c.shoot(name, opts); return f; };
const closeOv = async (c) => { const had = await c.ev(`(() => { const e = document.getElementById("bp-ov"); if (!e) return false; e.click(); return true; })()`); await c.sleep(420); return had; };

const moveOf = (m, i = 0) => { const acts = (m.json.options || []).filter((o) => o.enabled && o.id.startsWith("battle:act:")); return acts.length ? acts[Math.min(i, acts.length - 1)].id : null; };
// p2 moves by API so the round settles
async function p2Moves(c, i = 0) {
  const q = await c.api("p2", "/api/main");
  const id = moveOf(q, i);
  if (id) await c.api("p2", "/api/choose", { id });
  return id;
}
const brief = (c) => c.py("out = stage.battle_brief(world)");
const blank = (c) => c.leave();
const readLetter = (c, who) => c.declineLetters(who);
async function bothMove(c, a, b) {
  await blank(c);
  const m = await c.api("p1", "/api/main");
  const id = moveOf(m, a);
  if (id) await c.api("p1", "/api/choose", { id });
  await p2Moves(c, b);
  await c.api("p1", "/api/main");
  return id;
}

const ALL = [
  ["accounts", async (c) => {
    for (const [w, l, n, s] of ACCOUNTS) c.log("account", w, await c.account(w, l, n, s));
    await c.py("content.config.admins = [*content.config.admins, 'QAadmin']; out = 1");
    for (const [w] of ACCOUNTS) await c.api(w, "/api/main");
    c.log("open", (await c.api("admin", "/api/do/open_season", {})).status);
    for (const [w] of ACCOUNTS) await c.api(w, "/api/main");
    for (const w of ["p1", "p2", "p3"]) {
      await c.api(w, "/api/choose", { id: "growth:balanced" });
      await c.api(w, "/api/choose", { id: "choice:2" });
    }
    c.log("rich", JSON.stringify(await c.py("out = stage.rich(chars, content, '沈浪', 'wan_city')")));
    await c.py("out = stage.rich(chars, content, '白飛', 'nanyang_huangjin_camp', level=18)");
    await c.py("out = stage.rich(chars, content, '新人甲', 'wan_city', level=10)");
    for (const [w, f] of [["p1", "guan"], ["p2", "huang"]]) {
      await c.api(w, "/api/choose", { id: `faction:${f}` });
      await c.api(w, "/api/choose", { id: "faction:confirm" });
    }
    await place(c, "白飛", "wan_city");
    for (const w of ["p2", "p1", "p3"]) await c.api(w, "/api/main");
  }],
  ["smoke", async (c) => {
    await c.asPlayer("p1");
    await shot(c, "smoke_jianghu");
    await readLetter(c, "p1");
    await shot(c, "smoke_jianghu_strip");
    await c.tab("practice");
    await shot(c, "smoke_practice");
  }],
  ["craft", async (c) => {
    c.log("two", JSON.stringify(await c.py("out = stage.two_copies(chars, content, world, '沈浪')")));
    const craft = async () => { await c.load("/"); await c.tab("practice"); await c.click('[data-act="tab"][data-tab="craft"]'); };
    const lv = async (name) => {
      const r = await c.ev(`(() => { const out = []; for (const i of document.querySelectorAll(".lv i")) { const s = getComputedStyle(i); const tag = i.closest(".mc-tags") ? "card" : "other"; out.push([tag, i.className, s.backgroundColor, s.borderRadius, s.width, s.height, s.paddingLeft, s.borderTopWidth, s.boxShadow]); } return { n: out.length, cells: out.slice(0, 14), tags: [...document.querySelectorAll(".made-card.preview .mc-tags i.tr")].map((e) => e.innerText.trim()) }; })()`);
      c.report.facts[name] = r;
      c.log(name, JSON.stringify(r).slice(0, 300));
    };
    await craft();
    await c.shoot("cr_main", { who: "p1" });
    await c.step(ACT("pot-open"), "cr_pot");
    await c.step('[data-act="pick"][data-id="feng"]', "cr_pick1");
    const r2 = await c.click('[data-act="pick"][data-id="feng~2"]');
    c.log("pick feng~2", r2);
    await c.settle(600);
    await c.shoot("cr_two_copies", { who: "p1" });
    await lv("lv_light");
    for (const [n, v] of [["lv_dark", c.VIEWS[1]], ["lv_1280", c.VIEWS[2]]]) { await c.setView(v, 1); await c.sleep(300); await lv(n); }
    await c.setView(c.VIEWS[0], 1);
    await c.ev(`(() => { const e = document.querySelector(".made-card.preview"); if (e) e.scrollIntoView({ block: "center" }); return !!e; })()`);
    await c.sleep(150);
    await c.shoot("cr_two_copies_card");
    // other pair: a merge, the tags are "maybe" so no cells
    await c.step('[data-act="unslot"][data-i="1"]', "cr_unslot");
    await c.step(ACT("pot-open"), "cr_pot2");
    await c.step('[data-act="pick"][data-id="huo"]', "cr_merge_pair");
    await c.step('[data-act="unslot"][data-i="1"]');
    await c.step(ACT("pot-open"));
    await c.click('[data-act="pick"][data-id="feng~2"]');
    await c.settle(500);
    // really do it: the made card has the same cells
    const go = await c.step(ACT("forge-hub"), "cr_forged", { who: "p1", wait: 2500 });
    if (go !== "ok") await c.step(ACT("forge"), "cr_forged", { who: "p1", wait: 2500 });
    await lv("lv_made");
    await c.load("/");
    await c.tab("practice");
    await c.shoot("cr_practice_after", { who: "p1" });
  }],
  ["siege", async (c) => {
    const adm = await c.api("admin", "/api/admin");
    const blocks = (adm.json && adm.json.conquest && adm.json.conquest.blocks) || [];
    c.log("blocks", blocks.length, JSON.stringify(blocks.slice(0, 3)).slice(0, 300));
    const pick = blocks.find((b) => b.label.includes("黃巾")) || blocks[0];
    c.log("pick", JSON.stringify(pick));
    if (!pick) { c.log("no blocks"); return; }
    await place(c, "沈浪", pick.id);
    await place(c, "白飛", pick.id);
    await c.ffBeforeSiege();
    for (const w of ["p1", "p2"]) await c.api(w, "/api/main");
    const r = await c.api("admin", "/api/do/admin_conquest_letter", { id: pick.id, side: "guan" });
    await c.py("CLOCK['now'] += 5; out = 1");
    c.log("msg", JSON.stringify(r.json && r.json.message).slice(0, 200), JSON.stringify(await c.py("s = world.get_season(); out = [[x.id, x.status, x.at, x.muster_at] for x in s.conquest.schedule] + [s.time]")));
    c.log("letter", r.status, (r.text || "").slice(0, 200));
    await c.api("p1", "/api/main");
    await c.api("p2", "/api/main");
    c.log("brief", JSON.stringify(await brief(c)));
    await c.asPlayer("p1");
    await closeOv(c);
    await shot(c, "sg_muster");
    const m = await c.api("p1", "/api/main");
    c.log("opts", JSON.stringify((m.json.options || []).map((o) => o.id)).slice(0, 300));
    const join = (m.json.options || []).find((o) => o.id.startsWith("battle:join:") || o.id.startsWith("battle:enlist:") || o.id.startsWith("battle:siege"));
    if (join) { await c.click(CH(join.id)); await c.settle(300); await shot(c, "sg_joined"); }
    const q = await c.api("p2", "/api/main");
    const j2 = (q.json.options || []).find((o) => o.id.startsWith("battle:join:") || o.id.startsWith("battle:enlist:") || o.id.startsWith("battle:siege"));
    if (j2) await c.api("p2", "/api/choose", { id: j2.id });
    for (let hop = 0; hop < 6; hop++) {
      await c.py("CLOCK['now'] += 900; out = 1");
      await c.api("admin", "/api/do/fast_forward", { hours: 1 });
      const n = await c.api("p1", "/api/main");
      await c.api("p2", "/api/main");
      if (n.json && n.json.battle_gauge && n.json.battle_gauge.phase === "active") break;
    }
    c.log("brief2", JSON.stringify(await brief(c)));
    await c.load("/");
    await shot(c, "sg_open_overlay");
    await closeOv(c);
    await shot(c, "sg_active");
    await bothMove(c, 0, 0);
    await c.load("/");
    await closeOv(c);
    await shot(c, "sg_round2");
    await blank(c);
    await c.py("out = stage.place(chars, '沈浪', 'wan_city')");
    await c.api("p1", "/api/main");
    await c.load("/");
    await closeOv(c);
    await shot(c, "sg_left_region");
    await blank(c);
    for (let i = 0; i < 3; i++) c.log("cancel", (await c.api("admin", "/api/do/cancel_battle", {})).status);
    for (const w of ["p1", "p2", "p3"]) await c.api(w, "/api/main");
    c.log("brief after cancel", JSON.stringify(await brief(c)));
  }],
  ["muster", async (c) => {
    await place(c, "沈浪", "wan_city");
    await place(c, "白飛", "wan_city");
    await place(c, "新人甲", "wan_city");
    c.log("start", (await c.api("admin", "/api/do/start_battle", { id: "wancheng_yi" })).status);
    c.log("brief", JSON.stringify(await brief(c)));
    await c.api("p2", "/api/main");
    await c.asPlayer("p1");
    await shot(c, "bt_muster");
    await c.step(CH("battle:join:guan"), null);
    await c.settle(400);
    await shot(c, "bt_joined");
    await c.api("p2", "/api/choose", { id: "battle:join:huang" });
    await c.api("p3", "/api/main");
    await c.load("/");
    await shot(c, "bt_muster2");
    await c.tab("practice");
    await shot(c, "bt_muster_mini");
    await c.asPlayer("p2");
    await readLetter(c, "p2");
    await shot(c, "bt_muster_p2", { who: "p2" });
    await c.asPlayer("p3");
    await shot(c, "bt_muster_p3", { who: "p3" });
    // options a free agent gets
    const m3 = await c.api("p3", "/api/main");
    c.log("p3 opts", JSON.stringify((m3.json.options || []).map((o) => o.id)).slice(0, 300));
  }],
  ["active", async (c) => {
    for (let hop = 0; hop < 6; hop++) {
      await c.py("CLOCK['now'] += 600; out = 1");
      await c.api("admin", "/api/do/fast_forward", { hours: 1 });
      const m = await c.api("p1", "/api/main");
      await c.api("p2", "/api/main");
      if (m.json && m.json.battle_gauge && m.json.battle_gauge.phase === "active") break;
    }
    c.log("brief", JSON.stringify(await brief(c)), JSON.stringify(await c.py("out = stage.chiefs(world)")));
    await c.asPlayer("p1");
    await shot(c, "bt_open_overlay");
    c.log("closed", await closeOv(c));
    await shot(c, "bt_active");
    // reload: the overlay does not come back
    await c.load("/");
    await shot(c, "bt_active_reload");
    await c.tab("practice");
    await shot(c, "bt_mini_nomove");
    await c.load("/");
    // no toast after a move
    const m = await c.api("p1", "/api/main");
    const id = moveOf(m, 0);
    c.log("moves", JSON.stringify((m.json.options || []).map((o) => o.id)).slice(0, 300));
    await c.click(CH(id));
    await c.sleep(120);
    await shot(c, "bt_sent");
    c.report.facts.toast_after_move = c.report.facts.bt_sent.toast;
    await c.tab("practice");
    await shot(c, "bt_mini_sent");
    await c.asPlayer("p3");
    await shot(c, "bt_spectator", { who: "p3" });
    await place(c, "新人甲", "yingchuan");
    await c.api("p3", "/api/main");
    await c.load("/");
    await shot(c, "bt_watch_far", { who: "p3" });
    await c.step(ACT("battle-open"), "bt_watch_open", { light: true });
    await c.step(ACT("battle-shut"), "bt_watch_shut", { light: true });
    await c.asPlayer("p2");
    await shot(c, "bt_active_p2", { who: "p2" });
    await blank(c);
    await p2Moves(c, 1);
    c.log("brief r2", JSON.stringify(await brief(c)));
    await c.api("p1", "/api/main");
    await c.asPlayer("p1");
    await shot(c, "bt_round2");
    await closeOv(c);
    // the free text box, real typing through the form
    await c.ev(`(() => { const e = document.querySelector("#free-form input"); if (e) { e.scrollIntoView({ block: "center" }); e.value = "奮力搏殺"; } return !!e; })()`);
    await c.shoot("bt_free_typed");
    await c.ev(`(() => { const e = document.querySelector("#free-form input"); e.value = "奮力搏殺"; document.querySelector("#free-form").requestSubmit(); return 1; })()`);
    await c.settle(1500);
    await shot(c, "bt_free_sent");
    await blank(c);
    await p2Moves(c, 2);
    await c.api("p1", "/api/main");
    c.log("brief r3", JSON.stringify(await brief(c)), JSON.stringify(await c.py("out = stage.chiefs(world)")));
    await c.load("/");
    await shot(c, "bt_round3");
    await closeOv(c);
    await bothMove(c, 1, 0);
    await c.load("/");
    await shot(c, "bt_round4");
    await closeOv(c);
    await blank(c);
    c.log("to fall", JSON.stringify(await c.py("out = stage.chief_pct(world, 'huang', 1, 1)")));
    await bothMove(c, 0, 1);
    c.log("after", JSON.stringify(await brief(c)), JSON.stringify(await c.py("out = stage.chiefs(world)")));
    await c.load("/");
    await shot(c, "bt_fall_natural");
    await closeOv(c);
    await shot(c, "bt_feed_fall");
    // the report and the folds
    await c.step(ACT("bp-log"), "bt_log", { who: "p1" });
    await c.load("/");
    await closeOv(c);
    const merit = await c.click(".bp-merit summary");
    c.log("merit", merit);
    await c.settle(200);
    await c.shoot("bt_merit");
    await c.load("/");
    await closeOv(c);
    await c.step(ACT("battle-shut"), "bt_shut", { light: true });
    await c.step(ACT("battle-open"), "bt_open", { light: true });
    // the clock ticking in the page: move the deadline, wait for the one second timer
    await c.load("/");
    await closeOv(c);
    const tick = await c.ev(`(async () => { const before = document.querySelector(".bp-n").textContent; S.bpDueAt -= 100000; await new Promise((r) => setTimeout(r, 1200)); return { before, after: document.querySelector(".bp-n").textContent, ring: document.querySelector(".bp-ring > i").style.width, hot: !!document.querySelector(".bp-clock.hot") }; })()`);
    c.report.facts.tick = tick;
    c.log("tick", JSON.stringify(tick));
    await c.load("/");
    await closeOv(c);
  }],
  ["hot_and_beats", async (c) => {
    // red clock: 20 seconds left in this round
    const b = await brief(c);
    await c.py(`CLOCK['now'] = ${b.opened} + 160; out = 1`);
    await c.load("/");
    await closeOv(c);
    await shot(c, "bt_hot");
    await c.tab("practice");
    await c.shoot("bt_hot_mini", { light: true });
    await c.load("/");
    await closeOv(c);
    // at zero, in the page only
    await c.ev(`(() => { S.bpDueAt = Date.now(); bpTick(); return 1; })()`);
    await c.sleep(60);
    await fact(c, "bt_zero");
    await c.py(`CLOCK['now'] = ${b.opened} + 30; out = 1`);
    // paused by the admin
    await blank(c);
    c.log("pause", (await c.api("admin", "/api/do/pause_clock", {})).status);
    await c.load("/");
    await closeOv(c);
    await shot(c, "bt_paused");
    await blank(c);
    c.log("resume", (await c.api("admin", "/api/do/resume_clock", {})).status);
    await c.load("/");
    await closeOv(c);
    // main general hurt: 45, then 25 percent
    await blank(c);
    c.log("chiefs", JSON.stringify(await c.py("out = stage.chief_pct(world, 'huang', 0, 45)")));
    await c.load("/");
    await shot(c, "bt_hurt50");
    await closeOv(c);
    await blank(c);
    await c.py("out = stage.chief_pct(world, 'huang', 0, 25)");
    await c.load("/");
    await shot(c, "bt_hurt30");
    await closeOv(c);
    await shot(c, "bt_low_panel");
    // a real auto close, no hold: 4.2 seconds and it is gone
    await blank(c);
    await c.py("out = stage.chief_pct(world, 'guan', 0, 40)");
    await c.ev(`window.__qaHold = false; 0`);
    await c.load("/");
    const held = await c.ev(`window.__qaHold`);
    const inner = await c.ev(`(() => !!document.getElementById("bp-ov"))()`);
    c.report.facts.auto_close = { hold: held, shown: inner };
    await closeOv(c);
    await blank(c);
    await c.py("out = stage.chief_fall(world, 'huang', 1, '沈浪')");
    await c.load("/");
    await shot(c, "bt_fall_mine");
    await closeOv(c);
    await shot(c, "bt_fall_panel");
    await blank(c);
    await c.py("out = stage.chief_fall(world, 'guan', 1, '白飛')");
    await c.load("/");
    await shot(c, "bt_fall_ours");
    await closeOv(c);
    // the auto close for real: drop the hold in the page, show it again
    const auto = await c.ev(`(async () => { window.__qaHold = false; const k = "tx-bp:" + S.main.battle_panel.key; const seen = JSON.parse(localStorage.getItem(k) || "[]"); localStorage.setItem(k, JSON.stringify(seen.filter((x) => !x.startsWith("fall:")))); bpAfter(); const shown = !!document.getElementById("bp-ov"); await new Promise((r) => setTimeout(r, 4900)); const gone = !document.getElementById("bp-ov"); window.__qaHold = true; return { shown, gone }; })()`);
    c.report.facts.auto_close_real = auto;
    c.log("auto", JSON.stringify(auto));
    // knocked out: p2 sees the "only watching" line
    await blank(c);
    await c.py("out = stage.knock_out(world, '白飛')");
    await c.asPlayer("p2");
    await closeOv(c);
    await shot(c, "bt_out_p2", { who: "p2" });
    await c.asPlayer("p1");
    await closeOv(c);
    await shot(c, "bt_p1_after_ko");
  }],
  ["finish", async (c) => {
    await blank(c);
    for (let hop = 0; hop < 16; hop++) {
      const m = await c.api("p1", "/api/main");
      if (!m.json || !m.json.battle_gauge) break;
      const id = moveOf(m, hop % 3);
      if (id) await c.api("p1", "/api/choose", { id });
      await p2Moves(c, 0);
      await c.py("CLOCK['now'] += 200; out = 1");
    }
    await c.api("p1", "/api/main");
    c.log("brief end", JSON.stringify(await brief(c)));
    await c.load("/", { keepCards: true });
    await shot(c, "bt_end_first");
    c.log("closed", await closeOv(c));
    await shot(c, "bt_end_closed");
    await c.load("/", { keepCards: true });
    await shot(c, "bt_end_reload");
    await c.step(ACT("mvp-replay"), "bt_mvp", { light: true });
    await c.step(ACT("mvp-close"), "bt_mvp_close", { light: true });
    await c.step(ACT("story-ok"), "bt_end_ok", { who: "p1" });
    await c.load("/");
    await shot(c, "bt_after");
    await c.tab("news");
    await c.shoot("bt_news", { who: "p1", light: true });
    await c.asPlayer("p2");
    await closeOv(c);
    await shot(c, "bt_after_p2", { who: "p2" });
  }],
];

// One world, one war: the siege holds the field the muster needs, so it walks in its own round (flows/cs.mjs).
export const flows = ALL.filter(([name]) => name !== "siege");
export const siegeFlows = ALL.filter(([name]) => name === "accounts" || name === "siege");
