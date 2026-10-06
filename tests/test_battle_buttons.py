"""決戰三招的按鈕（決戰改版 1 Task 4）：引擎給的標籤是「選項名（強攻・82 分）」，網頁把括號裡的招與分數拆到按鈕右邊的小字，
名字長（十一、十二個字）時才不會把一顆按鈕折成兩行（375px 上一顆按鈕的字只有約 285px）。
web/app.js 沒有建置步驟：這裡把那個小函式從原始碼切出來交給 node 跑，看出來的 HTML。沒有 node 就略過。"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="沒有 node，前端畫面測試略過")

DRIVER = r"""
const fs = require("fs");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const src = fs.readFileSync(input.app, "utf8").replace(/\r\n/g, "\n"); // Windows 的 checkout 是 CRLF
const konst = (name) => {
  const m = src.match(new RegExp(`^  const ${name} = .*;$`, "m"));
  if (!m) throw new Error(`app.js 裡找不到 const ${name}`);
  return m[0];
};
const H = new Function(["esc", "BATTLE_MOVE_LABEL", "optLabelHtml", "sceneHtml"].map(konst).join("\n") + "\nreturn { optLabelHtml, sceneHtml };")();
process.stdout.write(JSON.stringify(input.scenes ? input.scenes.map((s) => H.sceneHtml(s)) : (input.options || []).map((o) => H.optLabelHtml(o))));
"""


def _node(**payload):
    done = subprocess.run(
        [NODE, "-e", DRIVER], input=json.dumps({"app": str(ROOT / "web" / "app.js"), **payload}),
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def label_html(*options):
    return _node(options=list(options))


def scene_html(*scenes):
    return _node(scenes=list(scenes))


def option(label, id="battle:act:guan_strong"):
    return {"id": id, "label": label, "enabled": True}


@needs_node
def test_a_move_label_splits_into_the_name_and_a_small_note():
    html, = label_html(option("聲東擊西，暗襲另一面城牆（奇襲・82 分）"))
    assert html == '<span class="b-name">聲東擊西，暗襲另一面城牆</span><span class="b-move">奇襲・82 分</span>'


@needs_node
def test_all_three_moves_and_three_digit_scores_split():
    htmls = label_html(option("甲（強攻・100 分）"), option("乙（固守・5 分）"), option("丙（奇襲・0 分）"))
    assert [h.count("b-move") for h in htmls] == [1, 1, 1]
    assert 'b-move">強攻・100 分<' in htmls[0] and 'b-move">固守・5 分<' in htmls[1]


@needs_node
def test_other_labels_stay_a_plain_span():
    """不是三招的選項：舊的穩守／猛攻、移動、加入戰局——一律照舊，連括號裡長得像的也不拆（只拆戰鬥出招）。"""
    htmls = label_html(
        option("穩紮穩打"), option("開門突擊（強攻・82 分）", id="move:lake"), option("加入【官軍】", id="battle:join:guan"),
        option("甲（別的說明）"), option("甲（強攻）"),  # 最後一個：還沒有份量快照的人，引擎只寫招、不寫分數
    )
    assert htmls == [
        "<span>穩紮穩打</span>", "<span>開門突擊（強攻・82 分）</span>", "<span>加入【官軍】</span>", "<span>甲（別的說明）</span>",
        "<span>甲（強攻）</span>",
    ]


@needs_node
def test_the_name_is_escaped():
    html, = label_html(option("<b>衝</b>（強攻・82 分）"))
    assert "<b>衝</b>" not in html and "&lt;b&gt;" in html


# ── 戰局那一段小字：對面上一回合與自己的結果（PM 2026-10-06：併成一段、13px、淡色）──


@needs_node
def test_the_last_round_paragraph_gets_its_own_class_and_nothing_else_does():
    both, own, other = scene_html(
        "<p><strong>三招決戰</strong></p>\n<p>【對陣】兩軍對陣。</p>\n<p>對面上一回合（黃巾）：強攻 20%・固守 50%・奇襲 30%<br>\n你上一回合：固守（剋制 ×1.3）</p>",
        "<p>【對陣】兩軍對陣。</p>\n<p>你上一回合：固守（剋制 ×1.0）</p>",
        "<p>黃巾說：對面上一回合的事。</p>\n<p>【對陣】你上一回合沒有人。</p>",
    )
    assert both.count('<p class="b-last">') == 1 and '<p class="b-last">對面上一回合（黃巾）' in both
    assert own.count('<p class="b-last">') == 1 and '<p class="b-last">你上一回合：固守' in own
    assert 'b-last' not in other  # 只認一段開頭的那兩個詞，句子中間提到的不算


def _css_rule(selector):
    css = (ROOT / "web" / "style.css").read_text(encoding="utf-8")
    found = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert found, f"style.css 裡找不到 {selector}"
    return dict(part.strip().split(":", 1) for part in found.group(1).split(";") if ":" in part)


def test_the_last_round_paragraph_is_small_muted_and_tight():
    """13px、淡色、行距 1.5 以內、上下各 2px：375px 上這一段（兩行對面比例加一行自己的結果）約 58px，不是兩段 15.5px 的 95px。"""
    rule = {k.strip(): v.strip() for k, v in _css_rule(".scene p.b-last").items()}
    assert rule["font-size"] == "13px" and rule["color"] == "var(--ink-2)"
    assert float(rule["line-height"]) <= 1.5
    assert rule["margin"] == "2px 0"
