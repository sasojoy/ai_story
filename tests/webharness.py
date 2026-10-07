"""前端測試共用的 node 執行器（測試整併第 5 區）。

web/app.js 沒有建置步驟、也沒有前端測試框架：各個測試檔寫一段 node 程式（「驅動程式」），把要測的函式從原始碼切出來
（切函式），或把整支 app.js 放進假瀏覽器，接上自己的假 DOM，餵它 JSON、讀它印出來的 JSON。

以前每個請求各開一個 node（一次約 50 毫秒，一輪三百多次）。現在整個工作階段只開一個常駐的 node，每個請求在一個全新的
vm context 裡跑：看得到的東西跟各開一個 node 時一樣——require（fs 讀 0 號檔讀到的是這個請求的輸入）、process.stdout／
stderr／exit／exitCode、console、計時器與其他 node 的全域；結束的條件也一樣：程式跑完、沒有還在等的計時器（node 自己結束
的時候），丟出沒接住的例外、沒人接的 Promise 拒絕、process.exit(非 0)、結束時 process.exitCode 不是 0 就是失敗。每個請求的
全域是新的；harness 自己的名字（runOne、pump……）不在請求裡。harness 自己出錯時那個請求馬上失敗、帶著錯誤回來，不會等到逾時。

已知跟各開一個 node 不一樣、目前的驅動程式都碰不到的地方（評審 2026-10-07，第 5 區 M1、M3、M6、M8）：
- node 自己的物件是常駐 node 的那一份、請求之間共用：Buffer、URL、TextEncoder 的 prototype，process.env／argv／on(...)，
  require 回來的模組（fs 以外）。改了它們，後面的請求看得到；Buffer、TextEncoder 做出來的東西在請求的 context 裡也不是
  那個 context 的 Uint8Array（instanceof 是 false）。
- harness 看不到的非同步工作（真的 I/O：child_process、真的 fetch……）晚到的錯誤會算在當時正在跑的下一個請求頭上；
  unref() 過的計時器不再追蹤，請求結束後照樣會在舊的 context 裡跑。
- performance 只有 now() 是這個請求自己的（mark()、timeOrigin 會丟例外）。
- process.stdout.write(Buffer) 每一次各自解成字：一個多位元組的字拆在兩次 write 裡，會變成 U+FFFD（各開一個 node 時是
  位元組照樣接起來）。
- 在計時器或 Promise 裡丟出連 describe 都寫不出來、而且寫它時丟出來的還是它自己的東西（讀任何屬性都丟出它自己的
  Proxy）：常駐的 node 整個結束，這邊馬上回報「常駐的 node 意外結束了」，下一個請求再開一個新的。在請求本身的程式裡丟的，
  那個請求照樣馬上失敗（「webharness: （寫不出來的例外）」）。
- _Resident.close() 不關 proc.stdout：用 python -X dev 跑時，結束會多印一行 ResourceWarning（unclosed file）。

環境變數 TIANXIA_WEB_HARNESS=process：改回每個請求各開一個 node（以前的做法），拿來對照兩種跑法的結果一不一樣。
它跟以前的指令差一點（第 5 區 M7）：有 stdin 的請求用 node -e（程式放在命令列），沒有 stdin 的（test_server 的那幾個）
用 node -（程式從標準輸入送進去），選哪一個只看 stdin 是不是空的；兩種都用文字模式（text=True、UTF-8）讀寫，Windows 上從
標準輸入送進去的 \n 會變成 \r\n、stdout 照通用換行讀回來（以前 test_server 是位元組進出；JS 會把樣板字串裡的 CRLF 統一成
\n，目前的結果一樣）。

驅動程式寫在各個測試檔裡（假 DOM 各檔不同）；開頭共用的幾樣在 PRELUDE：input（這個請求的 JSON）、src（app.js，換行統一成 \\n）、
slice、fn、konst（切 app.js）、wholeApp（整支 app.js 交出要測的名字）、finish（印結果）。"""
from __future__ import annotations

import atexit
import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).parent.parent
APP = ROOT / "web" / "app.js"
NODE = shutil.which("node")
MODE_ENV = "TIANXIA_WEB_HARNESS"  # "process"：每個請求各開一個 node

PRELUDE = r"""
// ── webharness.PRELUDE：輸入、app.js 原始碼、切函式的小工具、印結果 ──
const fs = require("fs");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const src = fs.readFileSync(input.app, "utf8").replace(/\r\n/g, "\n"); // Windows 的 checkout 是 CRLF
// IIFE 裡兩格縮排的一段：從寫著 head 的那一行（例："async function busy("）到下一個兩格縮排的收尾
const slice = (head) => {
  const a = src.indexOf(`\n  ${head}`);
  if (a < 0) throw new Error(`app.js 裡找不到 ${head}`);
  return src.slice(a, src.indexOf("\n  }\n", a) + 4);
};
// 照名字找函式（含 async）；一行寫完的函式（例：guideKey）只取那一行
const fn = (name) => {
  let a = src.indexOf(`\n  function ${name}(`);
  if (a < 0) a = src.indexOf(`\n  async function ${name}(`);
  if (a < 0) throw new Error(`app.js 裡找不到 function ${name}`);
  const header = src.slice(a + 1, src.indexOf("\n", a + 1));
  if (/\{.*\}\s*$/.test(header)) return "\n" + header;
  return src.slice(a, src.indexOf("\n  }\n", a) + 4);
};
// 一行寫完的 const 照名字抓
const konst = (name) => {
  const m = src.match(new RegExp(`^  const ${name} = .*;$`, "m"));
  if (!m) throw new Error(`app.js 裡找不到 const ${name}`);
  return m[0];
};
// 整支 app.js 放進假瀏覽器：最後一行啟動的呼叫（})();）前面插一行，把要測的名字交給 globalThis.__H
const wholeApp = (names) => {
  const end = src.lastIndexOf("\n})();");
  if (end < 0) throw new Error("app.js 的最後不是 })();");
  return src.slice(0, end) + `\n  globalThis.__H = { ${names.join(", ")} };\n` + src.slice(end);
};
// 印出結果（可以是 Promise）：JSON（undefined 印成 null）；出錯就把錯誤印到 stderr、以 1 結束
const finish = (value) => Promise.resolve(value).then(
  (out) => { process.stdout.write(JSON.stringify(out === undefined ? null : out)); },
  (e) => { process.stderr.write(String((e && e.stack) || e)); process.exit(1); },
);
"""

_MARK = "\u0000webharness\u0000"

# 常駐的 node：一行一個請求（{"code", "stdin"}），一行一個回覆（{"code", "stdout", "stderr"}，前面加 _MARK）
SERVER = r"""
"use strict";
(() => { // 全部包在一個函式裡：runOne、pump 這些名字不是全域，不會跑進請求的 context，驅動程式也可以用這些名字
const vm = require("vm");
const fs = require("fs");
const readline = require("readline");
const { Console } = require("console");
const { EventEmitter } = require("events");

const MARK = "\u0000webharness\u0000";
const EXIT = Symbol("process.exit");
const HOST_NAMES = Object.getOwnPropertyNames(globalThis);
const OWN = new Set(["global", "globalThis", "process", "console", "require", "module", "exports", "__filename", "__dirname",
  "setTimeout", "clearTimeout", "setInterval", "clearInterval", "setImmediate", "clearImmediate", "performance"]);
let active = null; // 正在跑的請求：沒人接的拒絕與例外算它的

// 錯誤寫成字：沒有 stack、連 String() 都轉不了的東西（例：Object.create(null)）也不能讓 harness 自己丟例外
const describe = (e) => {
  try { return String((e && e.stack) || e); } catch (_) { return Object.prototype.toString.call(e); }
};
// harness 自己出錯時的回覆一定要回得出去：連 describe 都寫不出來的東西（讀任何屬性都丟出它自己的 Proxy）也一樣
const broken = (e) => {
  let why;
  try { why = describe(e); } catch (_) { why = "（寫不出來的例外）"; }
  return { code: 1, stdout: "", stderr: `webharness: ${why}\n` };
};

process.on("unhandledRejection", (reason) => { if (reason !== EXIT && active) active.fail(reason); });
process.on("uncaughtException", (error) => { if (error !== EXIT && active) active.fail(error); });

function runOne(req) {
  return new Promise((resolve) => {
    const out = [], err = [];
    const timers = new Map(); // 這個請求排下、還沒跑也沒清掉的計時器 → 清掉它的函式
    const byId = new Map(); // 計時器的數字 id（+timeout）→ 計時器：clearTimeout(+t) 跟 node 一樣清得掉
    let code = null, wake = null;
    const poke = () => { if (wake) { const w = wake; wake = null; w(); } };
    const stop = (c) => {
      if (code !== null) return;
      code = c;
      for (const [handle, clear] of timers) clear(handle);
      timers.clear();
      poke();
    };
    const fail = (e) => { if (code === null) err.push(describe(e) + "\n"); stop(1); };
    active = { fail };
    try {
      const text = (s) => (typeof s === "string" ? s : Buffer.from(s).toString("utf8"));
      // console 會在 stream 上掛、拿掉 error 的監聽，所以要是 EventEmitter
      const sink = (buf) => Object.assign(new EventEmitter(), { write: (s) => { if (code === null) buf.push(text(s)); return true; } });
      const stdout = sink(out), stderr = sink(err);
      // process.exitCode 是這個請求自己的（每次從 undefined 開始，不碰常駐 node 的）：結束時不是 0 就算失敗，跟 node 一樣
      const exitCode = () => Number(fakeProcess.exitCode ?? 0) || 0;
      const fakeProcess = Object.create(process, {
        stdout: { value: stdout }, stderr: { value: stderr },
        exitCode: { value: undefined, writable: true, enumerable: true, configurable: true },
        exit: { value: (c) => { stop(c === undefined ? exitCode() : Number(c) || 0); throw EXIT; } },
      });
      const fakeFs = Object.create(fs, { readFileSync: { value: (p, o) => {
        if (p === 0 || p === "/dev/stdin") {
          const enc = typeof o === "string" ? o : o && o.encoding;
          return enc ? req.stdin : Buffer.from(req.stdin, "utf8");
        }
        return fs.readFileSync(p, o);
      } } });

      // 計時器：照常交給 node 排，但記著哪些還在等；請求結束（或 process.exit）時全部清掉
      const track = (handle, clear) => {
        timers.set(handle, clear);
        if (typeof handle[Symbol.toPrimitive] === "function") byId.set(+handle, handle);
        const unref = handle.unref;
        if (typeof unref === "function") handle.unref = function () { timers.delete(handle); poke(); return unref.call(this); };
        return handle;
      };
      const guard = (f, args, once, get) => () => {
        if (once) timers.delete(get());
        if (code !== null) return;
        try { f(...args); } catch (e) { if (e !== EXIT) fail(e); }
        poke();
      };
      const later = (f, ms, ...args) => { let h = null; h = setTimeout(guard(f, args, true, () => h), ms); return track(h, clearTimeout); };
      const every = (f, ms, ...args) => { let h = null; h = setInterval(guard(f, args, false, () => h), ms); return track(h, clearInterval); };
      const soon = (f, ...args) => { let h = null; h = setImmediate(guard(f, args, true, () => h)); return track(h, clearImmediate); };
      const unset = (hostClear) => (h) => {
        const handle = typeof h === "number" || typeof h === "string" ? byId.get(Number(h)) : h;
        if (handle && timers.delete(handle)) poke();
        hostClear(h);
      };

      // performance.now() 從這個請求開始算（各開一個 node 時是從那個 node 開始算；app.js 的轉盤角度讀它）
      const t0 = performance.now();
      const clock = Object.create(performance, { now: { value: () => performance.now() - t0 } });

      const ctx = vm.createContext({});
      const g = vm.runInContext("globalThis", ctx);
      for (const name of HOST_NAMES) { // node 自己的全域（Buffer、URL、TextEncoder、performance……）照樣看得到
        if (OWN.has(name) || Object.prototype.hasOwnProperty.call(g, name)) continue;
        try { Object.defineProperty(g, name, Object.getOwnPropertyDescriptor(globalThis, name)); } catch (e) { /* 定義不了的略過 */ }
      }
      Object.assign(g, {
        global: g, process: fakeProcess, console: new Console({ stdout, stderr }),
        require: (id) => (id === "fs" || id === "node:fs" ? fakeFs : require(id)),
        module: { exports: {} }, exports: {}, __filename: "[eval]", __dirname: ".",
        setTimeout: later, clearTimeout: unset(clearTimeout), setInterval: every, clearInterval: unset(clearInterval),
        setImmediate: soon, clearImmediate: unset(clearImmediate), performance: clock,
      });
      try { new vm.Script(req.code, { filename: "[eval]" }).runInContext(ctx); } catch (e) { if (e !== EXIT) fail(e); }
      (async () => { // 等到 node 自己會結束的時候：沒有還在等的計時器（Promise 的工作在每一輪之間跑完）
        for (;;) {
          await new Promise((r) => setImmediate(r));
          if (code !== null) break;
          if (timers.size === 0) {
            await new Promise((r) => setImmediate(r));
            if (code !== null || timers.size === 0) break;
            continue;
          }
          await new Promise((r) => { wake = r; });
        }
        active = null;
        resolve({ code: code === null ? exitCode() : code, stdout: out.join(""), stderr: err.join("") });
      })().catch((e) => { active = null; resolve(broken(e)); });
    } catch (e) { // harness 自己出錯：這一個請求馬上失敗、把錯誤交回去，不是等到逾時
      active = null;
      for (const [handle, clear] of timers) clear(handle);
      resolve(broken(e));
    }
  });
}

const lines = [];
let busy = false, closed = false;
async function pump() {
  if (busy) return;
  busy = true;
  while (lines.length) {
    let res;
    try { res = await runOne(JSON.parse(lines.shift())); } catch (e) { active = null; res = broken(e); }
    process.stdout.write(MARK + JSON.stringify(res) + "\n");
  }
  busy = false;
  if (closed) process.exit(0);
}
const rl = readline.createInterface({ input: process.stdin });
rl.on("line", (line) => { lines.push(line); pump(); });
rl.on("close", () => { closed = true; if (!busy) process.exit(0); });
})();
"""


class _Resident:
    """常駐的那一個 node（整個工作階段一個；pytest-xdist 的每個 worker 各一個）。"""

    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self.replies: queue.Queue | None = None
        self.errors = None

    def _start(self) -> None:
        self.errors = tempfile.TemporaryFile()
        self.proc = subprocess.Popen(
            [NODE, "-e", SERVER], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.errors, cwd=ROOT,
        )
        self.replies = queue.Queue()
        threading.Thread(target=self._read, args=(self.proc, self.replies), daemon=True).start()

    @staticmethod
    def _read(proc: subprocess.Popen, replies: queue.Queue) -> None:
        mark = _MARK.encode("utf-8")
        for line in proc.stdout:
            if line.startswith(mark):
                replies.put(line[len(mark):])
        replies.put(None)

    def ask(self, code: str, stdin: str, timeout: float) -> subprocess.CompletedProcess:
        if self.proc is None or self.proc.poll() is not None:
            self._start()
        self.proc.stdin.write(json.dumps({"code": code, "stdin": stdin}).encode("ascii") + b"\n")
        self.proc.stdin.flush()
        try:
            line = self.replies.get(timeout=timeout)
        except queue.Empty:
            self.close()
            raise subprocess.TimeoutExpired([NODE, "(webharness)"], timeout) from None
        if line is None:
            self.errors.seek(0)
            why = self.errors.read().decode("utf-8", "replace")
            self.close()
            raise RuntimeError(f"常駐的 node 意外結束了（設 {MODE_ENV}=process 改回每個請求各開一個 node 再看一次）：\n{why}")
        reply = json.loads(line.decode("utf-8"))
        return subprocess.CompletedProcess([NODE, "(webharness)"], reply["code"], reply["stdout"], reply["stderr"])

    def close(self) -> None:
        if self.proc is None:
            return
        proc, self.proc = self.proc, None
        try:
            proc.stdin.close()
            proc.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            proc.kill()
            proc.wait()
        self.errors.close()


_RESIDENT = _Resident()
atexit.register(_RESIDENT.close)


def node(code: str, stdin: str = "", timeout: float = 60) -> subprocess.CompletedProcess:
    """在 node 裡跑 code（stdin 是 fs.readFileSync(0) 讀到的東西）；回傳 returncode、stdout、stderr（都是字串）。
    預設在常駐的 node 裡一個新的 vm context 跑；TIANXIA_WEB_HARNESS=process 時跟以前一樣各開一個 node。"""
    if os.environ.get(MODE_ENV) == "process":
        if stdin:
            return subprocess.run([NODE, "-e", code], input=stdin, capture_output=True, text=True, encoding="utf-8", timeout=timeout)
        return subprocess.run([NODE, "-"], input=code, capture_output=True, text=True, encoding="utf-8", timeout=timeout)
    return _RESIDENT.ask(code, stdin, timeout)


def run(driver: str, payload: dict, timeout: float = 60):
    """跑 PRELUDE＋driver，輸入是 payload 加上 app（app.js 的路徑）；node 要成功結束，回傳它印出的 JSON。"""
    done = node(PRELUDE + driver, json.dumps({"app": str(APP), **payload}), timeout)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)
