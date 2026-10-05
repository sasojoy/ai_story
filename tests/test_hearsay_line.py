"""戰鬥卡片底下「你聽到一件事：…」那一句（FB-074）：伺服器在那一行標 tx-hearsay（tests/test_journal.py），網頁把它收成一行、
放不下加「…」，點了看全文。這裡把網頁的兩個函式（decorateHearsay、hearToggle）從 web/app.js 切出來在 node 裡跑，
再檢查樣式。沒有 node 就略過（樣式的檢查照樣跑）。"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
NODE = shutil.which("node")

DRIVER = r"""
const fs = require("fs");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const src = fs.readFileSync(input.app, "utf8").replace(/\r\n/g, "\n");
const fn = (name) => {
  const a = src.indexOf(`\n  function ${name}(`);
  if (a < 0) throw new Error(`app.js 裡找不到 function ${name}`);
  return src.slice(a, src.indexOf("\n  }\n", a) + 4);
};
// 一行就是一個假的元素：classList 與屬性夠 decorateHearsay、hearToggle 用
const line = () => {
  const classes = new Set(["tx-line", "tx-new", "tx-hearsay"]), attrs = {};
  return { classes, attrs, classList: { contains: (c) => classes.has(c), toggle(c, on) { if (on) classes.add(c); else classes.delete(c); } },
    setAttribute(k, v) { attrs[k] = String(v); }, getAttribute: (k) => attrs[k] };
};
const lines = [line(), line()];
globalThis.document = { querySelectorAll: (sel) => (sel === ".battle-card .tx-hearsay" ? lines : []) };
const S = { hearOpen: null, main: { card_id: input.cardId } };
const H = new Function("S", [fn("decorateHearsay"), fn("hearToggle"), "return { decorateHearsay, hearToggle };"].join("\n"))(S);
const out = new Function("H", "S", "lines", input.script)(H, S, lines);
process.stdout.write(JSON.stringify(out === undefined ? null : out));
"""


def run(script, card_id=7):
    if NODE is None:
        pytest.skip("沒有 node")
    done = subprocess.run(
        [NODE, "-e", DRIVER], input=json.dumps({"app": str(ROOT / "web" / "app.js"), "script": script, "cardId": card_id}),
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_the_hearsay_line_becomes_a_button_that_starts_folded():
    got = run("H.decorateHearsay(); return lines.map((l) => ({ open: l.classes.has('open'), ...l.attrs }));")
    for row in got:
        assert row == {"open": False, "data-act": "hear-more", "role": "button", "tabindex": "0", "aria-expanded": "false"}


def test_a_tap_unfolds_it_and_another_tap_folds_it_again():
    got = run("""
      H.decorateHearsay();
      H.hearToggle(lines[0]);
      const opened = { open: lines[0].classes.has('open'), expanded: lines[0].attrs['aria-expanded'], remembered: S.hearOpen };
      H.hearToggle(lines[0]);
      return { opened, closed: { open: lines[0].classes.has('open'), expanded: lines[0].attrs['aria-expanded'], remembered: S.hearOpen } };
    """)
    assert got["opened"] == {"open": True, "expanded": "true", "remembered": 7}
    assert got["closed"] == {"open": False, "expanded": "false", "remembered": None}


def test_a_poll_redraw_keeps_it_open_for_the_same_fight_only():
    got = run("""
      H.hearToggle(lines[0]);                       // 展開：記的是這一場的卡片
      const fresh = line(); lines.splice(0, 2, fresh);
      H.decorateHearsay();                          // 輪詢重畫出來的新元素
      const same = fresh.classes.has('open');
      S.main.card_id = 8;                           // 換了下一場
      const another = line(); lines.splice(0, 1, another);
      H.decorateHearsay();
      return { same, next: another.classes.has('open') };
    """)
    assert got == {"same": True, "next": False}


def _css() -> str:
    return re.sub(r"/\*.*?\*/", "", (ROOT / "web" / "style.css").read_text(encoding="utf-8"), flags=re.S)


def test_the_folded_line_is_one_line_with_an_ellipsis_and_the_open_one_wraps():
    css = _css()
    folded = re.search(r"(?m)^\.battle-card \.tx-extra \.tx-hearsay \{([^}]*)\}", css).group(1)
    assert "white-space: nowrap" in folded and "overflow: hidden" in folded and "text-overflow: ellipsis" in folded
    opened = re.search(r"(?m)^\.battle-card \.tx-extra \.tx-hearsay\.open \{([^}]*)\}", css).group(1)
    assert "white-space: normal" in opened and "overflow: visible" in opened


def test_the_folded_line_leaves_the_left_padding_to_the_reduced_motion_bar():
    """Reduce Motion 開著時，journal 的 .tx-new 改成左邊一條 3px 的金色條加 padding-left: 8px（讓字離條遠一點）。
    折起來那一行的規則不能用 padding 簡寫（0,3,0 的權重會把左邊也歸零），條就蓋在「你」字上（輪三審查 Minor 2）：
    只寫上下的 padding；不管有沒有開 Reduce Motion，條都不會壓到字。"""
    from tianxia import journal

    css = _css()
    for selector in (r"\.battle-card \.tx-extra \.tx-hearsay", r"\.battle-card \.tx-extra \.tx-hearsay\.open"):
        rule = re.search(rf"(?m)^{selector} \{{([^}}]*)\}}", css).group(1)
        assert not re.search(r"(?<![-\w])padding\s*:", rule) and not re.search(r"padding-(left|right)", rule), selector
    folded = re.search(r"(?m)^\.battle-card \.tx-extra \.tx-hearsay \{([^}]*)\}", css).group(1)
    assert "padding-top: 7px" in folded and "padding-bottom: 7px" in folded and "margin: -5px 0" in folded
    reduced = re.search(r"@media \(prefers-reduced-motion: reduce\) \{(.*?)\n\}", journal.CSS, re.S).group(1)
    bar = re.search(r"\.tx-new \{[^}]*box-shadow: inset (\d+)px", reduced)
    gap = re.search(r"\.tx-new \{[^}]*padding-left: (\d+)px", reduced)
    assert bar and gap and int(gap.group(1)) > int(bar.group(1))  # 空出來的比條寬：條不壓字


def test_the_page_wires_the_tap_and_the_keyboard():
    js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    assert 'case "hear-more": hearToggle(el); break;' in js
    assert "decorateHearsay();" in js[js.index("function afterPage()"):js.index("// ── 登入與取名號")]
    keydown = js[js.index('document.addEventListener("keydown"'):]
    assert 'tx-hearsay[data-act="hear-more"]' in keydown[:keydown.index("});")]
    assert "你聽到一件事" not in js  # 網頁不去讀句子的字：標記是伺服器畫的
