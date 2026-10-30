"""走一趟的網頁（web/outing.js；企劃者 2026-10-29～30）：探索那一格點開的段數選單、結算卡的帳、一段的那一行。
動畫本身靠實機看（畫布在 node 裡畫不出來）；這裡只驗吐出來的字。"""
from __future__ import annotations

import pytest
import webharness

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node")

DRIVER = r"""
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const code = ["OUTING_CLOSE", "OUTING_AGAIN", "OUTING_SAY_HEAD", "OUTING_SAY_OWN", "OUTING_SAY_INK", "OUTING_SAY_BUY", "OUTING_SAID", "OUTING_HERE"].map(konst).join("\n")
  + fn("outingPickerHtml") + fn("outingSum") + fn("outingResultHtml") + fn("outingLedgerHtml") + fn("outingSayHtml") + fn("outingPeopleHtml");
const H = new Function("esc", code + "\nreturn { outingPickerHtml, outingSum, outingResultHtml, outingLedgerHtml };")(esc);
finish({ picker: H.outingPickerHtml(input.m), result: H.outingResultHtml(input.trip), ledger: H.outingLedgerHtml(input.ledger),
  extra: (input.more || []).map((t) => H.outingResultHtml(t)) });
"""

PICKER = {"picker": [{"n": 1, "stamina": 6, "ok": True}, {"n": 3, "stamina": 18, "ok": True}, {"n": 5, "stamina": 30, "ok": False}],
          "note": "走得越遠，越容易碰上稀有的東西。", "trip": None}
TRIP = {"place": "潁川郊野", "total": 3, "done": 3, "end": "done", "title": "走完一趟", "end_line": "", "beats": [
    {"kind": "material", "text": "撿到驚羽。", "ledger": "得：驚羽 ×1", "rare": False},
    {"kind": "encounter", "text": "打散了。", "ledger": "得：驚羽 ×1、銀兩 +5　失：氣血 -6", "rare": False},
    {"kind": "material", "text": "撿到玄鋼骨。", "ledger": "得：玄鋼骨 ×1　失：氣血 -6", "rare": True},
]}


def _run(ledger: str = "得：驚羽 ×1　失：氣血 -6", more=()):
    return webharness.run(DRIVER, {"m": {"outing": PICKER}, "trip": TRIP, "ledger": ledger, "more": list(more)})


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


SAY = {**TRIP, "can_say": True, "said": "", "presets": ["溪水可飲。", "後來者保重。"], "say_max": 20, "ink": 0, "ink_item": "inscribe_ink",
       "people": ["遠方客"]}


def test_the_result_card_offers_free_lines_and_ink():
    """預設句一按就留（免費）；沒有題壁墨給去萬寶閣的鈕，有就給輸入框；此地還有誰點名字開玩家卡。"""
    no_ink, ink, said = _run(more=[SAY, {**SAY, "ink": 2}, {**SAY, "can_say": False, "said": "溪水可飲。"}])["extra"]
    assert no_ink.count('data-act="outing-say"') == 2 and 'data-act="outing-mall" data-id="inscribe_ink"' in no_ink
    assert 'id="outing-own"' not in no_ink
    assert 'id="outing-own" maxlength="20"' in ink and "手上 2 張" in ink
    assert 'data-act="outing-peer" data-name="遠方客"' in no_ink
    assert "你留下：「溪水可飲。」" in said and 'data-act="outing-say"' not in said
