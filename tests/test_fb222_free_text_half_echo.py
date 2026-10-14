"""FB-222（回饋單丙批 QA，2026-10-14，模型 gemma4:26b）：隨口應對的潤色只寫進結果句的頭半句時，那半句寫兩次。

官軍大營「轅門盤查」寫「掏出糖葫蘆請軍侯吃」成功：模型那一段收在結果句的頭半句（「……試圖化解嚴峻的氣氛，軍侯聽完你說的，」），
引擎照接整句（「軍侯聽完你說的，臉色鬆了些……」），「軍侯聽完你說的，」寫了兩次。FB-124 只認整句（event_llm.tells_the_outcome）。

修法：潤色插回紀錄時（Game.add_gamble_narration），潤色的結尾跟結果句的開頭重疊（空白、標點不算）至少 ECHO_MIN 個字、而且
重疊的那一截在結果句裡收在一個子句的尾巴（到 ECHO_SURE 個字就不看子句），就把潤色尾巴的那一截切掉（event_llm.trim_echo），
結果句照接整句。一兩個字、或收在子句中間的主詞巧合不切。"""
from __future__ import annotations

import pytest

from conftest import FixedRandom
from tianxia import event_llm
from tianxia.models import Effect, FreeTextChoice

# QA 看到的那一則（轅門盤查，成功）
GATE_OUTCOME = "軍侯聽完你說的，臉色鬆了些，放你在營邊轉了一圈，還提點了你幾句長社那邊的動靜。"
GATE_PARAGRAPH = "你從懷中取出甜香的糖葫蘆，緩緩遞至軍侯面前試圖化解嚴峻的氣氛，軍侯聽完你說的，"
GATE_TRIMMED = "你從懷中取出甜香的糖葫蘆，緩緩遞至軍侯面前試圖化解嚴峻的氣氛。"

GAMBLE = FreeTextChoice(
    prompt="另想法子過轅門", stat="wis", by="self",
    effect=Effect(text=GATE_OUTCOME, stats={"fame": 1}), fail_effect=Effect(text="軍侯把你轟了出去。", stamina=-10),
)


def _bare(text):
    return "".join(ch for ch in text if ch.isalnum())


@pytest.fixture
def gate(game):
    """測試內容的「醉漢」事件掛上這個隨口應對，玩家寫了一句、成功了（江湖紀錄有了那一則，還沒有潤色）。"""
    game.content.events["drunk"].free_text = GAMBLE
    game.state.pending_event = "drunk"
    game.rng = FixedRandom(0.0)
    game.answer_event(game.free_text_request("掏出糖葫蘆請軍侯吃"), 30)
    assert game.last_gamble is not None and game.last_gamble.success is True
    game.before = list(game.state.journal[0].lines)
    return game


def _polish(game, paragraph):
    game.add_gamble_narration(game.last_gamble, paragraph)
    return list(game.state.journal[0].lines)


# ── 整則紀錄 ─────────────────────────────────────────────


def test_the_qa_case_writes_the_half_sentence_once(gate):
    lines = _polish(gate, GATE_PARAGRAPH)
    said = next(i for i, line in enumerate(lines) if line.startswith("你：「掏出糖葫蘆請軍侯吃」"))
    assert lines[said + 1] == GATE_TRIMMED and lines[said + 2] == GATE_OUTCOME  # 潤色切掉尾巴，結果句一字不少照接
    assert "".join(lines).count("軍侯聽完你說的") == 1
    assert [x for x in lines if x != GATE_TRIMMED] == gate.before  # 其他行一行不少


def test_the_whole_outcome_written_still_drops_the_engine_line(gate):
    """整句都寫進去（FB-124 那一種）：照舊拿掉引擎那一行，模型那一段不切。"""
    paragraph = "你遞上糖葫蘆，" + GATE_OUTCOME
    lines = _polish(gate, paragraph)
    assert paragraph in lines and GATE_OUTCOME not in lines
    assert _bare("".join(lines)).count(_bare(GATE_OUTCOME)) == 1


def test_a_paragraph_without_the_outcome_is_followed_by_it_as_before(gate):
    paragraph = "你從懷中掏出糖葫蘆，笑嘻嘻地遞了過去。"
    lines = _polish(gate, paragraph)
    assert lines.index(paragraph) == lines.index(GATE_OUTCOME) - 1


@pytest.mark.parametrize("paragraph", [
    "你把糖葫蘆遞給軍侯",  # 「軍侯」兩個字
    "你嚼著糖葫蘆，把話說給軍侯聽完你",  # 「軍侯聽完你」五個字，可是在結果句裡收在子句中間（後面是「說的」）
], ids=["two-chars", "mid-clause"])
def test_a_short_coincidence_is_left_alone(gate, paragraph):
    lines = _polish(gate, paragraph)
    assert lines.index(paragraph) == lines.index(GATE_OUTCOME) - 1


def test_a_paragraph_that_is_nothing_but_the_echo_is_not_inserted(gate):
    lines = _polish(gate, "軍侯聽完你說的，")
    assert lines == gate.before


# ── event_llm.trim_echo ─────────────────────────────────────


def test_trim_echo_cuts_the_overlap_and_ends_the_sentence():
    assert event_llm.trim_echo(GATE_PARAGRAPH, GATE_OUTCOME) == GATE_TRIMMED
    # 標點、空白不同也算；切完收在逗號上的補成句號，沒有標點的也補
    assert event_llm.trim_echo("你遞上糖葫蘆  軍侯聽完你說的", GATE_OUTCOME) == "你遞上糖葫蘆。"
    assert event_llm.trim_echo("你遞上糖葫蘆——軍侯聽完你說的……", GATE_OUTCOME) == "你遞上糖葫蘆。"
    assert event_llm.trim_echo("你遞上糖葫蘆……「軍侯聽完你說的，", GATE_OUTCOME) == "你遞上糖葫蘆……"
    # 寫過了第一個子句、停在第二個子句中間：重疊夠長（ECHO_SURE）也切
    assert event_llm.trim_echo("你遞上糖葫蘆。軍侯聽完你說的，臉色鬆", GATE_OUTCOME) == "你遞上糖葫蘆。"
    assert event_llm.trim_echo("軍侯聽完你說的，臉色鬆了些", GATE_OUTCOME) == ""  # 整段都是重疊的


@pytest.mark.parametrize("narration, outcome", [
    ("你遞上糖葫蘆。", GATE_OUTCOME),  # 沒寫
    ("你把水遞給你", "你總算喘過氣來。"),  # 一個字
    ("你轉身走向軍侯", GATE_OUTCOME),  # 兩個字
    ("你把乾糧交給那郡兵", "那郡兵總算有了著落，他啞著嗓子說，這條命是你給的。"),  # 三個字
    ("你把乾糧交給那名郡兵", "那名郡兵總算有了著落，他啞著嗓子說，這條命是你給的。"),  # 四個字的主詞，可是收在子句中間
    ("你遞上糖葫蘆，軍侯聽完你說的", "軍侯聽完你說的"),  # 整句都寫了：是 tells_the_outcome 的事，這裡不動
    ("隨便一段話。", ""),  # 沒有結果句
], ids=["none", "one-char", "two-chars", "three-chars", "subject-mid-clause", "whole-outcome", "empty-outcome"])
def test_trim_echo_leaves_everything_else_alone(narration, outcome):
    assert event_llm.trim_echo(narration, outcome) == narration
