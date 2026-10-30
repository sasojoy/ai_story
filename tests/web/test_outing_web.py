"""走一趟的網頁（web/outing.js；企劃者 2026-10-29～30）：探索那一格點開的段數選單、結算卡的帳、一段的那一行。
動畫本身靠實機看（畫布在 node 裡畫不出來）；這裡只驗吐出來的字。"""
from __future__ import annotations

import pytest
import webharness

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node")

DRIVER = r"""
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const code = ["OUTING_CLOSE", "OUTING_AGAIN"].map(konst).join("\n") + fn("outingPickerHtml") + fn("outingSum") + fn("outingResultHtml") + fn("outingLedgerHtml");
const H = new Function("esc", code + "\nreturn { outingPickerHtml, outingSum, outingResultHtml, outingLedgerHtml };")(esc);
finish({ picker: H.outingPickerHtml(input.m), result: H.outingResultHtml(input.trip), ledger: H.outingLedgerHtml(input.ledger) });
"""

PICKER = {"picker": [{"n": 1, "stamina": 6, "ok": True}, {"n": 3, "stamina": 18, "ok": True}, {"n": 5, "stamina": 30, "ok": False}],
          "note": "走得越遠，越容易碰上稀有的東西。", "trip": None}
TRIP = {"place": "潁川郊野", "total": 3, "done": 3, "end": "done", "title": "走完一趟", "end_line": "", "beats": [
    {"kind": "material", "text": "撿到驚羽。", "ledger": "得：驚羽 ×1", "rare": False},
    {"kind": "encounter", "text": "打散了。", "ledger": "得：驚羽 ×1、銀兩 +5　失：氣血 -6", "rare": False},
    {"kind": "material", "text": "撿到玄鋼骨。", "ledger": "得：玄鋼骨 ×1　失：氣血 -6", "rare": True},
]}


def _run(ledger: str = "得：驚羽 ×1　失：氣血 -6"):
    return webharness.run(DRIVER, {"m": {"outing": PICKER}, "trip": TRIP, "ledger": ledger})


def test_the_picker_offers_one_three_five_without_the_multiplier():
    """Joy 10/30「不用顯示倍率，有顯示多段的時候越容易獲得更好獎勵的資訊就夠了」：一、三、五段，體力不夠的那一顆灰，不寫倍數。"""
    html = _run()["picker"]
    assert html.count('data-act="outing-go"') == 3
    assert 'data-n="5" disabled' in html and 'data-n="3" ' in html
    assert "走得越遠，越容易碰上稀有的東西。" in html
    assert "×1.2" not in html and "×1.5" not in html and "倍" not in html


def test_the_result_adds_up_the_segments():
    html = _run()["result"]
    assert "驚羽 ×2" in html and "銀兩 +5" in html and "氣血 -12" in html
    assert '<span class="oc rare">玄鋼骨 ×1</span>' in html  # 稀有的素材亮金
    assert "走完一趟</b>・3 段" in html


def test_a_segment_ledger_colours_gains_and_losses():
    html = _run()["ledger"]
    assert '<small class="up">得：驚羽 ×1</small>' in html and '<small class="down">失：氣血 -6</small>' in html
