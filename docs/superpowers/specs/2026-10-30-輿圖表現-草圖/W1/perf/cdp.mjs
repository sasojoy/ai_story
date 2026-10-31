// Minimal Chrome DevTools Protocol client (Node 22: global WebSocket + fetch). Flat sessions.
import { spawn } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

export const CHROME = "C:/Users/ray61/AppData/Local/ms-playwright/chromium-1208/chrome-win64/chrome.exe";
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export async function launch({ port, dataDir, extra = [] }) {
  const args = [
    "--headless=new", `--remote-debugging-port=${port}`, `--user-data-dir=${dataDir}`,
    "--no-first-run", "--no-default-browser-check", "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding", "--disable-backgrounding-occluded-windows", "--disable-extensions",
    "--disable-component-update", "--disable-sync", "--metrics-recording-only", "--mute-audio",
    "--window-size=1920,1080", ...extra, "about:blank",
  ];
  const proc = spawn(CHROME, args, { stdio: "ignore", detached: false });
  let ws = null;
  for (let i = 0; i < 100; i++) {
    try {
      const v = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json();
      ws = v.webSocketDebuggerUrl; break;
    } catch (e) { await sleep(150); }
  }
  if (!ws) throw new Error("chrome did not start");
  const cdp = new CDP(ws);
  await cdp.ready;
  return { proc, cdp };
}

export class CDP {
  constructor(url) {
    this.ws = new WebSocket(url);
    this.id = 0; this.pending = new Map(); this.listeners = [];
    this.ready = new Promise((res, rej) => { this.ws.onopen = res; this.ws.onerror = rej; });
    this.ws.onmessage = (ev) => {
      const msg = JSON.parse(typeof ev.data === "string" ? ev.data : Buffer.from(ev.data).toString());
      if (msg.id !== undefined) {
        const p = this.pending.get(msg.id); this.pending.delete(msg.id);
        if (!p) return;
        if (msg.error) p.rej(new Error(`${p.method}: ${JSON.stringify(msg.error)}`)); else p.res(msg.result);
      } else {
        for (const l of this.listeners) l(msg);
      }
    };
  }
  send(method, params = {}, sessionId) {
    const id = ++this.id;
    const msg = { id, method, params };
    if (sessionId) msg.sessionId = sessionId;
    return new Promise((res, rej) => { this.pending.set(id, { res, rej, method }); this.ws.send(JSON.stringify(msg)); });
  }
  on(fn) { this.listeners.push(fn); return () => { this.listeners = this.listeners.filter((x) => x !== fn); }; }
  waitFor(pred, timeout = 30000) {
    return new Promise((res, rej) => {
      const t = setTimeout(() => { off(); rej(new Error("waitFor timeout")); }, timeout);
      const off = this.on((m) => { if (pred(m)) { clearTimeout(t); off(); res(m); } });
    });
  }
  close() { try { this.ws.close(); } catch (e) { /* */ } }
}

export class Page {
  constructor(cdp, sessionId) { this.cdp = cdp; this.sid = sessionId; }
  send(m, p) { return this.cdp.send(m, p, this.sid); }
  async eval(expr, awaitPromise = true) {
    const r = await this.send("Runtime.evaluate", { expression: expr, awaitPromise, returnByValue: true, timeout: 60000 });
    if (r.exceptionDetails) throw new Error("eval: " + JSON.stringify(r.exceptionDetails).slice(0, 800));
    return r.result.value;
  }
  async metrics() {
    const r = await this.send("Performance.getMetrics");
    return Object.fromEntries(r.metrics.map((m) => [m.name, m.value]));
  }
}

export async function newPage(cdp) {
  const { targetId } = await cdp.send("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await cdp.send("Target.attachToTarget", { targetId, flatten: true });
  return new Page(cdp, sessionId);
}

// Tracing over the browser connection (browser-wide). Returns the events array.
export async function startTrace(cdp, categories) {
  await cdp.send("Tracing.start", { traceConfig: { recordMode: "recordAsMuchAsPossible", includedCategories: categories }, transferMode: "ReturnAsStream" });
  return async () => {
    const done = cdp.waitFor((m) => m.method === "Tracing.tracingComplete", 120000);
    await cdp.send("Tracing.end");
    const c = await done;
    const parts = [];
    for (;;) {
      const r = await cdp.send("IO.read", { handle: c.params.stream, size: 1 << 23 });
      parts.push(r.base64Encoded ? Buffer.from(r.data, "base64").toString() : r.data);
      if (r.eof) break;
    }
    await cdp.send("IO.close", { handle: c.params.stream });
    const j = JSON.parse(parts.join(""));
    return j.traceEvents || j;
  };
}

export const TRACE_CATS = ["devtools.timeline", "disabled-by-default-devtools.timeline.frame", "benchmark"];

export function tmpProfile(prefix) { return mkdtempSync(path.join(tmpdir(), prefix)); }
export function rmProfile(dir) { try { rmSync(dir, { recursive: true, force: true }); } catch (e) { /* */ } }
