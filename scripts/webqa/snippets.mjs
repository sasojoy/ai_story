// Page-side snippets shared by driver.mjs (the walk) and replay.mjs (the corpus replay).
// Everything here runs the same on both sides; a difference in the output is a difference in the page.

export const CLOCK_MS = 1793937600 * 1000;

// name, width, height, mobile, colour scheme
export const SHOT_VIEWS = [["375-light", 375, 812, true, "light"], ["375-dark", 375, 812, true, "dark"], ["1280", 1280, 800, false, "light"]];
// the breakpoints the stylesheets ask about: min-width 641px and 900px. Styles only in the walk, pixels come from the replay.
export const STYLE_VIEWS = [["640", 640, 812, false, "light"], ["641", 641, 812, false, "light"], ["900", 900, 812, false, "light"]];
export const ALL_VIEWS = [...SHOT_VIEWS, ...STYLE_VIEWS];

// Randomness from the source: Math.random and crypto.getRandomValues share one seeded stream, __qaReseed() restarts it.
// The canvas loops eat from the stream every frame, so clicks reseed right before the handler runs.
// mask: canvases go transparent (opacity, not visibility: a stroke on #sense-canvas still has to hit it). The map ground stays.
export const freeze = ({ mask = true, still = true } = {}) => `(() => { const SEED = 20261106; let sd = SEED; const rnd = () => { sd |= 0; sd = (sd + 0x6d2b79f5) | 0; let x = Math.imul(sd ^ (sd >>> 15), 1 | sd); x = (x + Math.imul(x ^ (x >>> 7), 61 | x)) ^ x; return ((x ^ (x >>> 14)) >>> 0) / 4294967296; };
  Math.random = rnd; window.__qaReseed = () => { sd = SEED; };
  if (window.Crypto && Crypto.prototype.getRandomValues) { Crypto.prototype.getRandomValues = function (a) { for (let i = 0; i < a.length; i++) a[i] = Math.floor(rnd() * 4294967296); return a; }; }
  const T = ${CLOCK_MS}; const R = Date; class D extends R { constructor(...a) { a.length ? super(...a) : super(T); } static now() { return T; } } window.Date = D;
  let hold = true; try { hold = !sessionStorage.getItem("__qa_nohold"); } catch (e) { /* about:blank */ } window.__qaHold = hold; const ST0 = window.setTimeout; window.setTimeout = function (f, ms, ...r) { if (window.__qaHold && (ms === 4200 || ms === 6000)) return 0; return ST0.call(window, f, ms, ...r); };
  window.__inflight = 0; const F = window.fetch; window.fetch = function (...a) { window.__inflight++; return F.apply(this, a).finally(() => { window.__inflight--; }); };
  const add = () => { const s = document.createElement("style"); s.id = "__qa_freeze"; s.textContent = "${still ? "*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}" : ""}${mask ? "canvas:not(.mv-ground){opacity:0!important}" : ""}"; (document.head || document.documentElement).appendChild(s); };
  if (document.documentElement) add(); else document.addEventListener("readystatechange", add, { once: true }); })();`;

// the layout's signature: size of the page, where the shell sits, a hash of every class on the page. innerWidth tells whether the new width has landed at all.
export const STABLE_SIG = `(() => { const d = document.documentElement; const s = document.querySelector(".shell"); const r = s ? s.getBoundingClientRect() : null; let x = 2166136261; for (const e of document.querySelectorAll("*")) { const c = e.getAttribute("class") || ""; for (let i = 0; i < c.length; i++) { x ^= c.charCodeAt(i); x = Math.imul(x, 16777619); } x ^= 124; x = Math.imul(x, 16777619); } return innerWidth + "|" + d.scrollHeight + "|" + d.scrollWidth + "|" + (r ? [r.left, r.top, r.width, r.height].join() : "") + "|" + (x >>> 0); })()`;

// Has the new width landed? A phone's layout viewport widens to fit what overflows (the open move card at 375 measures 383, on both sides, with nothing moving):
// that counts. Only near a phone width, and every window the walk comes from is 640 or wider, so an old width cannot pass for it.
export const landed = (sig, width) => { const [w, , sw] = sig.split("|").map(Number); return w === width || (width <= 480 && w > width && w === sw && w - width < 100); };

// every element under body plus ::before and ::after that exist: property text deduplicated by hash inside one scene.
// The walk leaves #toast out: it drops its class 3.2 s after showing, on the wall clock, so it flips from side to side (wave D, 002_opening_event and 170_cr_pick2 at 640).
// The replay keeps it: there both sides get the same snapshot, and that is where a change to the toast's own styles shows.
const styleDump = (skipToast) => `(() => { const props = [...getComputedStyle(document.body)].filter((p) => !p.startsWith("--")); const host = location.host; const dict = {}; const els = [];
  const fnv = (s, x) => { for (let i = 0; i < s.length; i++) { x ^= s.charCodeAt(i); x = Math.imul(x, 16777619); } return (x >>> 0).toString(36); };
  const put = (cs) => { const vals = []; for (const p of props) vals.push(cs.getPropertyValue(p)); const t = vals.join("\\u0001").split(host).join("HOST").replace(/\\?v=[0-9a-zA-Z_-]+/g, "?v=X"); const k = fnv(t, 2166136261) + fnv(t, 33554467); dict[k] = t; return k; };
  for (const el of document.querySelectorAll("body, body *")) { if (/^(SCRIPT|STYLE|LINK)$/.test(el.tagName)${skipToast ? ` || el.id === "toast"` : ""}) continue; const cls = el.getAttribute("class") || ""; const row = [el.tagName + "." + cls.slice(0, 40), put(getComputedStyle(el))]; for (const ps of ["::before", "::after"]) { const c = getComputedStyle(el, ps); if (c.content !== "none" && c.content !== "normal") row.push(ps, put(c)); } els.push(row); }
  return { props, els, dict }; })()`;
export const STYLE_DUMP = styleDump(false);
export const WALK_STYLE_DUMP = styleDump(true);

export const LAYOUT = `(() => { const d = document.documentElement; const over = [...document.querySelectorAll("#app *")].filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.right > innerWidth + 1 && getComputedStyle(e).position !== "fixed"; }).length; return { sw: d.scrollWidth, cw: d.clientWidth, sh: d.scrollHeight, past: over }; })()`;

// the things that are allowed to change by themselves: the share row (a fresh code), the chronicle link (written when the writer gets to it). Rects on screen.
export const VOLATILE = `(() => { const out = []; const add = (kind, sel) => { for (const e of document.querySelectorAll(sel)) { const r = e.getBoundingClientRect(); if (r.width && r.height) out.push([kind, Math.floor(r.left), Math.floor(r.top), Math.ceil(r.right), Math.ceil(r.bottom)]); } }; add("share", ".zh-url"); add("tale", ".huaben-link"); return out; })()`;

// information only: does each canvas have anything on it
export const CANVASES = `(() => { const out = []; for (const c of document.querySelectorAll("canvas")) { let on = null; try { const o = document.createElement("canvas"); o.width = o.height = 16; const x = o.getContext("2d"); x.drawImage(c, 0, 0, 16, 16); on = x.getImageData(0, 0, 16, 16).data.some((v, i) => i % 4 === 3 && v > 0); } catch (e) { on = null; } out.push([c.id || c.className || "canvas", on]); } return out; })()`;

export const DOM_TEXT = `(() => { const c = document.body.cloneNode(true); c.querySelectorAll("script").forEach((x) => x.remove()); const attrs = {}; for (const a of document.documentElement.attributes) attrs[a.name] = a.value; return JSON.stringify({ html: attrs, body: c.outerHTML }); })()`;

export const CSS_RULES = `(() => { const out = []; for (const s of document.styleSheets) { if (s.ownerNode && /__qa_/.test(s.ownerNode.id || "")) continue; let r; try { r = s.cssRules; } catch (e) { continue; } for (const x of r) out.push(x.cssText); } return out; })()`;
