"""決戰三招的按鈕（決戰改版 1 Task 4）：引擎給的標籤是「選項名（強攻・82 分）」，網頁把括號裡的招與分數拆到按鈕右邊的小字，
名字長（十一、十二個字）時才不會把一顆按鈕折成兩行（375px 上一顆按鈕的字只有約 285px）。
web/app.js 沒有建置步驟：這裡把那個小函式從原始碼切出來交給 node 跑，看出來的 HTML。沒有 node 就略過。"""
from __future__ import annotations

import json
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
const konst = (name) => {
  const m = src.match(new RegExp(`^  const ${name} = .*;$`, "m"));
  if (!m) throw new Error(`app.js 裡找不到 const ${name}`);
  return m[0];
};
const H = new Function(["esc", "BATTLE_MOVE_LABEL", "optLabelHtml"].map(konst).join("\n") + "\nreturn { optLabelHtml };")();
process.stdout.write(JSON.stringify(input.options.map((o) => H.optLabelHtml(o))));
"""


def label_html(*options):
    done = subprocess.run(
        [NODE, "-e", DRIVER], input=json.dumps({"app": str(ROOT / "web" / "app.js"), "options": list(options)}),
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def option(label, id="battle:act:guan_strong"):
    return {"id": id, "label": label, "enabled": True}


def test_a_move_label_splits_into_the_name_and_a_small_note():
    html, = label_html(option("聲東擊西，暗襲另一面城牆（奇襲・82 分）"))
    assert html == '<span class="b-name">聲東擊西，暗襲另一面城牆</span><span class="b-move">奇襲・82 分</span>'


def test_all_three_moves_and_three_digit_scores_split():
    htmls = label_html(option("甲（強攻・100 分）"), option("乙（固守・5 分）"), option("丙（奇襲・0 分）"))
    assert [h.count("b-move") for h in htmls] == [1, 1, 1]
    assert 'b-move">強攻・100 分<' in htmls[0] and 'b-move">固守・5 分<' in htmls[1]


def test_other_labels_stay_a_plain_span():
    """不是三招的選項：舊的穩守／猛攻、移動、加入戰局——一律照舊，連括號裡長得像的也不拆（只拆戰鬥出招）。"""
    htmls = label_html(
        option("穩紮穩打"), option("開門突擊（強攻・82 分）", id="move:lake"), option("加入【官軍】", id="battle:join:guan"),
        option("甲（別的說明）"),
    )
    assert htmls == ["<span>穩紮穩打</span>", "<span>開門突擊（強攻・82 分）</span>", "<span>加入【官軍】</span>", "<span>甲（別的說明）</span>"]


def test_the_name_is_escaped():
    html, = label_html(option("<b>衝</b>（強攻・82 分）"))
    assert "<b>衝</b>" not in html and "&lt;b&gt;" in html
