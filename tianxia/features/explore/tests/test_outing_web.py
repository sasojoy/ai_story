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


def test_the_result_counts_the_settled_events_and_the_stamina():
    """Joy 10/31：選完那件事的得失（after）與一路走掉的體力也加進結算卡。"""
    trip = dict(TRIP, beats=[dict(b, spent=6) for b in TRIP["beats"]])
    trip["beats"][1] = dict(trip["beats"][1], after="得：銀兩 +30　失：體力 -5")
    html = _run(more=[trip])["extra"][0]
    assert "銀兩 +35" in html and "體力 -23" in html


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


def test_the_result_card_shows_the_tale_without_a_keep_button():
    """Joy 10/30：每一趟都能收進行狀太多、沒價值。沒有「收進行狀」鈕；撿到稀世的東西、以弱勝強才寫一行「記進了行狀」。"""
    plain, feat = _run(more=[{**TRIP, "diary": "你在潁川郊野走了一程。"}, {**TRIP, "diary": "你在潁川郊野走了一程。", "feat_note": "這一趟記進了行狀。"}])["extra"]
    assert '<p class="outing-diary">你在潁川郊野走了一程。</p>' in plain
    assert "行狀" not in plain and "outing-keep" not in plain
    assert '<p class="outing-feat">這一趟記進了行狀。</p>' in feat


STELE_DRIVER = r"""
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const code = ["OUTING_STELE", "OUTING_STELE_N", "OUTING_STELE_ALL", "OUTING_INK_SEAL", "OUTING_INK_SEAL_LABEL"].map(konst).join("\n") + fn("outingSteleHtml") + fn("outingSteleAllHtml");
const H = new Function("esc", code + "\nreturn { outingSteleHtml, outingSteleAllHtml };")(esc);
finish({ signs: input.st.map((x) => H.outingSteleHtml(x)), all: H.outingSteleAllHtml(input.st[0]) });
"""


def test_the_stele_reads_the_ink_line_or_how_many_left_the_preset():
    """畫面上方那塊路碑（Joy 10/30）：題壁墨寫的掛名號、蓋一枚「墨」字印（要更顯眼）；預設句寫幾人留過；
    點開全部列出，題壁墨的排在最前面、蓋印。"""
    every = [{"text": "溪水可飲。", "author": "甲", "ink": False}, {"text": "橋下有魚", "author": "戊", "ink": True}]
    out = webharness.run(STELE_DRIVER, {"st": [{"text": "橋下有魚", "author": "戊", "n": 0, "ink": True, "all": every},
                                              {"text": "溪水可飲。", "author": "", "n": 3, "ink": False, "all": every}]})
    ink, preset = out["signs"]
    assert "「橋下有魚」" in ink and "——戊" in ink and 'class="ink-seal"' in ink
    assert "「溪水可飲。」" in preset and "3 人留過" in preset and "ink-seal" not in preset
    assert "此處留過的話" in out["all"]
    assert out["all"].index("橋下有魚") < out["all"].index("溪水可飲。") and '<p class="ink"><em class="ink-seal"' in out["all"]


CHOICE_DRIVER = r"""
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const code = konst("OUTING_WAIT") + fn("outingChoiceHtml");
const H = new Function("esc", code + "\nreturn { outingChoiceHtml };")(esc);
finish({ html: H.outingChoiceHtml(input.m) });
"""


def test_a_stop_puts_the_choice_on_the_card():
    """Joy 10/30「選項應該就要在浮起來那邊吧，幹嘛多此一舉弄什麼去看看」：停下來要選的事與選項畫在走一趟的卡上，沒有「去看看」。"""
    m = {"scene": "<p><strong>狼群</strong></p><p>林中傳來一聲狼嚎。</p>", "options": [
        {"id": "choice:0", "label": "拔出兵器迎戰", "enabled": True},
        {"id": "choice:1", "label": "爬上大樹躲避", "enabled": False}]}
    html = webharness.run(CHOICE_DRIVER, {"m": m})["html"]
    assert "林中傳來一聲狼嚎。" in html
    assert 'data-act="outing-choose" data-id="choice:0" >' in html and 'data-id="choice:1" disabled' in html
    assert "去看看" not in html and 'data-act="choose"' not in html
