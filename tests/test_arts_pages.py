"""修練頁與煉製頁的畫面（arts-polish-1：W2、W5、W7、W9）。
web/app.js 沒有建置步驟、也沒有前端測試框架：這裡把兩頁的函式從原始碼切出來交給 node 跑（不相干的畫法換成一行的假貨），
檢查出來的 HTML 與按鈕按下去之後的動作。沒有 node 就略過。"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="沒有 node，前端畫面測試略過")

DRIVER = r"""
const fs = require("fs");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const src = fs.readFileSync(input.app, "utf8").replace(/\r\n/g, "\n"); // Windows 的 checkout 是 CRLF
// IIFE 裡兩格縮排的函式：從標頭到下一個兩格縮排的收尾（含 async）；一行寫完的 const 照名字抓
const fn = (name) => {
  let a = src.indexOf(`\n  function ${name}(`);
  if (a < 0) a = src.indexOf(`\n  async function ${name}(`);
  if (a < 0) throw new Error(`app.js 裡找不到 function ${name}`);
  return src.slice(a, src.indexOf("\n  }\n", a) + 4);
};
const konst = (name) => {
  const m = src.match(new RegExp(`^  const ${name} = .*;$`, "m"));
  if (!m) throw new Error(`app.js 裡找不到 const ${name}`);
  return m[0];
};
const calls = [];
const scrolls = [];
globalThis.window = { scrollTo: (...a) => scrolls.push(a), scrollY: input.scrollY || 0 };
globalThis.document = { getElementById: () => null, querySelector: () => null, querySelectorAll: () => [] };
const S = { stage: "game", tab: "practice", kind: "武學", artOpen: null, legendTick: {}, forgeSel: [], forgeLine: "", busy: false,
  message: "", person: null, main: { status: { injury: 0 } }, ...input.S };
const parts = [
  ...["KINDS", "QUALITY_RANK", "esc", "pro", "attrNoteHtml"].map(konst),
  ...input.consts.map(konst),
  ...["forgeBody", "forgeReady", "pagePractice", "pageCraft", ...input.fns].map(fn),
  `const guideHtml = () => "", furnaceSvg = () => '<div class="furnace"></div>', proGuide = () => "";`,
  input.stubs || "",
  "return { " + ["pagePractice", "pageCraft", ...input.fns].join(", ") + " };",
];
const H = new Function("S", "calls", parts.join("\n"))(S, calls);
H.S = S; H.calls = calls; H.scrolls = scrolls;
(async () => {
  const out = await new Function("H", "S", `return (async () => { ${input.script} })();`)(H, S);
  process.stdout.write(JSON.stringify(out === undefined ? null : out));
})().catch((e) => { process.stderr.write(String(e.stack || e)); process.exit(1); });
"""


def run(script: str, *, S=None, consts=(), fns=(), stubs=""):
    done = subprocess.run(
        [NODE, "-e", DRIVER],
        input=json.dumps({
            "app": str(ROOT / "web" / "app.js"), "script": script, "S": S or {}, "consts": list(consts), "fns": list(fns),
            "stubs": stubs,
        }),
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def art(id="basic_fist", name="基礎拳腳", kind="武學", worn=True, **over):
    row = {
        "id": id, "name": name, "kind": kind, "quality": "下品", "attribute": "剛", "level": 1, "worn": worn, "insight": None,
        "card": f"<p>【{name}】CARD</p>",
        "cultivate": {"ok": False, "note": "沒有融意境", "legend": None}, "melt": {"ok": not worn, "note": "退回心得 0"},
    }
    row.update(over)
    return row


def menxia(**over):
    x = {
        "xinde": 20, "rules": "<p>RULESLINE</p>", "attribute_note": "ATTRNOTE", "player_card": "<p>PLAYERCARD</p>",
        "roster": [{"label": "本人", "key": "player"}], "person": None, "person_card": None, "on_team": False, "bag": "<p>BAG</p>",
        "clue_items": [], "forge_line": "<p>FORGELINE</p>", "holdings": {"count": 2, "cap": 50}, "insights": [], "naming": None,
        "owned_arts": [art(), art("lake_kick", "湖邊腿法", worn=False)],
        "slot_cards": [
            {"kind": "武學", "card": "<p>WUGONG</p>", "learned": True, "level": 1, "maxed": False, "blocked": None, "price": 1},
            {"kind": "內功", "card": "<p>NEIGONG</p>", "learned": True, "level": 1, "maxed": False, "blocked": None, "price": 1},
        ],
    }
    x.update(over)
    return x


def page(name: str, x: dict, **S) -> str:
    return run(f"S.menxia = {json.dumps(x)}; return H.{name}();", S=S)


# ── W5：修練頁的武學清單叫「功法庫」 ───────────────────────────────────


def test_the_practice_pages_list_of_arts_is_titled_the_art_library_with_its_count():
    html = page("pagePractice", menxia(holdings={"count": 7, "cap": 56}))
    assert re.search(r'<div class="label">功法庫 <small class="muted">武學與意境 7/56</small></div>', html)
    assert '<div class="label">武學 <small' not in html  # 舊的標題（跟煉製頁的「武學」挑選區同名）不在了
    assert "湖邊腿法" in html.split("功法庫")[1]  # 清單就在這個標題底下


# ── W2：屬性有什麼用，收在一個摺起來的說明裡 ───────────────────────────


def test_the_practice_page_has_a_closed_attribute_fold_right_under_the_rules_line():
    html = page("pagePractice", menxia())
    fold = re.search(r"<details class=\"attr-note\"( open)?><summary>([^<]*)</summary>(.*?)</details>", html, re.S)
    assert fold and fold.group(1) is None  # 收著：第一屏只多一行字
    assert fold.group(2) == "屬性有什麼用" and "ATTRNOTE" in fold.group(3)
    assert html.index("RULESLINE") < html.index("attr-note") < html.index("身上的功法")  # 規則那一行底下、第一張卡片之前


def test_the_craft_page_has_the_same_fold_right_under_the_open_furnace_button():
    html = page("pageCraft", menxia(), tab="craft")
    assert html.count('<details class="attr-note">') == 1 and "ATTRNOTE" in html
    assert html.index("FORGELINE") < html.index('id="forge"') < html.index("attr-note") < html.index("<div class=\"label\">武學")


def test_the_attribute_note_is_escaped_and_a_missing_one_draws_nothing():
    html = page("pagePractice", menxia(attribute_note="<b>x</b>"))
    assert "<b>x</b>" not in html and "&lt;b&gt;x&lt;/b&gt;" in html
    assert "attr-note" not in page("pagePractice", menxia(attribute_note=""))  # 伺服器沒給（舊版）：不畫空的摺疊
