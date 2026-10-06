"""網頁的 choose()：請求被擋下來（佇列排太久、重複的對話或大場面，伺服器回 400）之後，每一種「等待中」的樣子都要還原（審查 I2）。
把 web/app.js 的 busy 與 choose 兩個函式切出來，接上假的 document、api 在 node 裡跑；沒有 node 就略過。

選單上的按鈕（`.options .btn`）以前就會還原；閒著時那一排行動列的格子（`.act-ink`：交友、單獨的求見、遊歷）按下去也會換上
「對方沉吟中…」「兩人對峙……」並標 busy，失敗之後沒有人把它還原，拒絕的提示三秒後消失，格子還寫著對方在回話。"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
APP = Path(__file__).parent.parent / "web" / "app.js"

DRIVER = r"""
const fs = require("fs");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const src = fs.readFileSync(input.app, "utf8").replace(/\r\n/g, "\n");
const slice = (head) => {
  const a = src.indexOf(`\n  ${head}`);
  if (a < 0) throw new Error(`app.js 裡找不到 ${head}`);
  return src.slice(a, src.indexOf("\n  }\n", a) + 4);
};
// 假的元素：class 與一個放文字的最後一個子元素；inOptions 表示它在選單（.options）裡，不然就是行動列的格子
const cell = (cls, inOptions, label) => {
  const classes = new Set(cls.split(" "));
  const last = { textContent: label };
  return { inOptions, disabled: false, lastElementChild: last, label: () => last.textContent,
    classList: { add: (c) => classes.add(c), remove: (c) => classes.delete(c), contains: (c) => classes.has(c) } };
};
const els = [];
const part = (el, sel) => {
  const want = sel.trim();
  if (want === ".options .btn.busy") return el.inOptions && el.classList.contains("btn") && el.classList.contains("busy");
  if (want === ".options .btn") return el.inOptions && el.classList.contains("btn");
  if (want === ".act-ink.busy") return el.classList.contains("act-ink") && el.classList.contains("busy");
  throw new Error(`假的 document 不認得 ${want}`);
};
const matches = (el, sel) => sel.split(",").some((s) => part(el, s));
const document = {
  querySelector: (sel) => els.find((el) => matches(el, sel)) || null,
  querySelectorAll: (sel) => els.filter((el) => matches(el, sel)),
};
let renders = 0;
const S = { busy: false, answering: false, wheelSel: null, main: { options: input.options } };
const calls = { applied: 0, toasts: [] };
const redraw = () => { // 重畫：全部元素換成新的（沒有 busy、字回到原本）
  for (const el of els) { el.classList.remove("busy"); el.disabled = false; el.lastElementChild.textContent = el.orig; }
};
const renderPage = () => { renders += 1; redraw(); };
const fns = new Function(
  "S", "document", "renderPage", "api", "watchQueue", "applyMain", "toast", "window", "FREE_TEXT_OPTION",
  `let lastAction = 0;${slice("async function busy(")}${slice("async function choose(")}\nreturn { choose };`,
)(S, document, renderPage,
  async () => { if (input.refuse) throw new Error("refused"); return { main: {}, message: "" }; },
  () => () => {}, () => { calls.applied += 1; redraw(); }, (t) => calls.toasts.push(t), { scrollTo() {} }, "choice:free");  // applyMain 也是整頁重畫
(async () => {
  const mk = (cls, inOptions, label) => { const el = cell(cls, inOptions, label); el.orig = label; els.push(el); return el; };
  const target = mk(input.cls, input.inOptions, "名字");
  mk("btn", true, "別的選項"); // 同一排的其他按鈕：choose 會先把它們都 disabled
  await fns.choose(target, input.id);
  process.stdout.write(JSON.stringify({
    renders, applied: calls.applied, busy: target.classList.contains("busy"), label: target.label(),
    others: els.slice(1).map((el) => el.disabled),
  }));
})();
"""


def run(**kw):
    if NODE is None:
        pytest.skip("沒有 node")
    done = subprocess.run(
        [NODE, "-e", DRIVER], input=json.dumps({"app": str(APP), "options": [], "refuse": True, **kw}),
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@pytest.mark.parametrize(
    ("what", "cls", "in_options", "option_id", "options"),
    [
        ("the 交友 cell of the action bar", "act-ink", False, "act:socialize", []),
        ("a lone 求見 cell", "act-ink", False, "call:zhangliang", []),
        ("the 遊歷 cell with a big fight waiting", "act-ink", False, "act:train", [{"id": "act:train", "wait": "兩人對峙……"}]),
        ("a button in the menu", "btn", True, "talk:0", []),
    ],
)
def test_a_refused_request_restores_every_busy_state(what, cls, in_options, option_id, options):
    got = run(cls=cls, inOptions=in_options, id=option_id, options=options, refuse=True)
    assert got["renders"] == 1, what  # 重畫了：「等待中」的字與 busy 都還原
    assert got["busy"] is False and got["label"] == "名字", what
    assert got["others"] == [False], what


def test_a_request_that_went_through_is_left_to_the_normal_render():
    """成功的路徑不由 choose 重畫（applyMain 會畫），也不多畫一次。"""
    got = run(cls="act-ink", inOptions=False, id="act:socialize", refuse=False)
    assert got["renders"] == 0 and got["applied"] == 1
