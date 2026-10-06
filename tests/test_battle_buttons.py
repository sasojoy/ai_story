"""決戰三招的按鈕（決戰改版 1 Task 4）：引擎給的標籤是「選項名（強攻・82 分）」，網頁把括號裡的招與分數拆到按鈕右邊的小字，
名字長（十一、十二個字）時才不會把一顆按鈕折成兩行（375px 上一顆按鈕的字只有約 285px）。
web/app.js 沒有建置步驟：這裡把那個小函式從原始碼切出來交給 node 跑（tests/webharness.py），看出來的 HTML。沒有 node 就略過。"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import webharness

ROOT = Path(__file__).parent.parent
needs_node = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")

DRIVER = r"""
const H = new Function(["esc", "BATTLE_MOVE_LABEL", "optLabelHtml"].map(konst).join("\n") + "\nreturn { optLabelHtml };")();
finish((input.options || []).map((o) => H.optLabelHtml(o)));
"""


def _node(**payload):
    return webharness.run(DRIVER, payload)


def label_html(*options):
    return _node(options=list(options))


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
# 做法：引擎把兩句寫成一段 markdown 引用（「> 」），伺服器的 markdown 轉成 <blockquote>，樣式在 .scene blockquote——
# 不靠網頁去認字、不另外開 /api/main 的欄位；伺服器照舊跳脫原始 HTML。


def test_the_server_renders_the_last_round_lines_as_one_blockquote_paragraph():
    import server

    html = server.md("【對陣】兩軍對陣。\n\n> 對面上一回合（黃巾）：強攻 20%・固守 50%・奇襲 30%\n> 你上一回合：固守（剋制 ×1.3）")
    assert html.count("<blockquote>") == 1 and html.count("<p>") == 2  # 場景一段、引用裡一段（兩句用 <br> 接）
    assert html.split("<blockquote>")[1].count("<br") == 1 and html.count("</blockquote>") == 1
    assert "<blockquote>\n<p>對面上一回合（黃巾）" in html


def test_a_raw_html_tag_in_a_quoted_line_is_still_escaped():
    import server

    html = server.md("> 對面上一回合（<b>黃巾</b>）：強攻 100%")
    assert "<b>" not in html and "&lt;b&gt;" in html


def _css_rule(selector):
    css = (ROOT / "web" / "style.css").read_text(encoding="utf-8")
    found = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert found, f"style.css 裡找不到 {selector}"
    return {k.strip(): v.strip() for k, v in (part.split(":", 1) for part in found.group(1).split(";") if ":" in part)}


def test_the_last_round_paragraph_is_small_muted_and_tight():
    """13px、淡色、行距 1.5 以內、上下各 2px、沒有瀏覽器預設的引用縮排與邊線：375px 上這一段（兩行對面比例加一行自己的結果）
    約 65px（含上面一段的間距），不是兩段 15.5px 的 95px。"""
    rule = _css_rule(".scene blockquote")
    assert rule["font-size"] == "13px" and rule["color"] == "var(--ink-2)"
    assert float(rule["line-height"]) <= 1.5
    assert rule["margin"] == "2px 0" and rule["padding"] == "0" and rule["border"] == "0"
    inner = _css_rule(".scene blockquote p")
    assert inner["margin"] == "0"
