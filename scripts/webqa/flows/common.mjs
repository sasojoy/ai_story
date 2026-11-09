// What every round of the wave B walk starts from.
export const CH = (id) => `[data-act="choose"][data-id="${id}"]`;
export const CHP = (pre) => `[data-act="choose"][data-id^="${pre}"]:not([disabled])`;
export const ACT = (a) => `[data-act="${a}"]:not([disabled])`;
export const place = (c, name, loc) => c.py(`out = stage.place(chars, '${name}', '${loc}')`);
export const UI = ["hero-tab", "hero-jump", "hero-node", "news", "board", "board-card", "report-list", "report", "sheet", "fronts-help", "front-more", "stam-help", "howto",
  "renown-toggle", "renown-dot", "renown-sanren", "renown-peer", "toggle-more", "line-more", "own-more", "hear-more", "scene-more", "now-more", "rounds-more", "here-more", "here-all",
  "opt-why", "calls-more", "guide-more", "guide-open", "guide-shut", "guide-below", "fig-open", "fig-log", "fig-log-more", "fig-log-season", "peer", "art", "art-info", "attr-help", "xinde-more",
  "ins-open", "ins-filter", "lib-all", "lib-filter", "melt-open", "melt-mode", "melt-view", "melt-shown", "mx", "person", "rack-all", "self-sec", "slot-pick", "art-filter", "book-open", "craft-view",
  "create-open", "forge-hub", "peek", "pot-open", "secret-book", "shop-tab", "shop-more", "dv-cell", "tav-tab", "tav-mode", "tav-tier", "arena-tab", "mall-tab", "mall-cat",
  "map-filter", "map-fit", "map-graph", "map-home", "map-more", "map-now", "map-pick", "map-place", "map-region", "map-report", "map-search", "map-timeline", "map-wash", "map-week", "map-mark", "map-jianghu", "map-back",
  "tale", "wk", "wk-next", "sides-first", "duty-open", "alloc-toggle", "move-mode", "rv-scene", "push-how", "zhuan-open", "letter-open", "seal-pick", "seal-side", "seal-act", "sortie-far", "sortie-open",
  "hero-move-show", "recap", "battle-open", "board-zoom", "drill-full"];

export const ACCOUNTS = [["admin", "qaadmin", "QAadmin", "男"], ["p1", "qaplayer1", "沈浪", "男"], ["p2", "qaplayer2", "白飛", "女"], ["p3", "qaplayer3", "新人甲", "女"], ["p4", "qaplayer4", "新人乙", "男"]];

export const accounts = ["accounts", async (c) => {
    for (const [w, l, n, s] of ACCOUNTS) c.log("account", w, await c.account(w, l, n, s));
    await c.py("content.config.admins = [*content.config.admins, 'QAadmin']; out = 1");
    for (const [w] of ACCOUNTS) await c.api(w, "/api/main");
    await c.log("open", (await c.api("admin", "/api/do/open_season", {})).status);
    for (const [w] of ACCOUNTS) await c.api(w, "/api/main");
  }];
export const rich = ["rich", async (c) => {
    for (const w of ["p1", "p2"]) {
      await c.api(w, "/api/choose", { id: "growth:balanced" });
      await c.api(w, "/api/choose", { id: "choice:2" });
    }
    await c.py("out = stage.rich(chars, content, '沈浪', 'wan_city', gear=True)");
    await c.py("out = stage.rich(chars, content, '白飛', 'nanyang_huangjin_camp', level=18, gear=True)");
    for (const [w, f] of [["p1", "guan"], ["p2", "huang"]]) {
      await c.api(w, "/api/choose", { id: `faction:${f}` });
      await c.api(w, "/api/choose", { id: "faction:confirm" });
    }
    await c.py("out = stage.place(chars, '白飛', 'wan_city')");
    await c.api("p2", "/api/main");
    await c.api("p1", "/api/main");
  }];
