"""異聞第 264 批：替身那一幕接得上（純函式）。替身的做法（stand_in_options）、替身之後的帳（ledger_of）與前情（_head 的 STAND_IN_SCENE）、
自己說要等級要數值先擋（typed_problem 的 ask）、提示補的兩句（④）。"""
from tianxia.features.yiwen import rules

OP = {"id": "x", "title": "霧裡的身影", "hook": "霧裡有個身影一動不動⋯", "guesses": ["官軍", "黃巾", "迷路的老人"]}
FALLBACK = ["走近看清楚", "開口問身影的來歷", "轉身就走"]
WRITTEN = {"pick": "官軍", "typed": 0, "fallback": 0, "text": ["你撥開霧，看清那是一隊官軍。", "隊尾有個小兵朝你招手。"],
           "options": ["接過那封信", "瞪回去", "學鵝叫"], "ledger": ["在場：你、官軍", "你手上：無", "未了：那封信"]}
STAND_IN = {"pick": "接過那封信", "typed": 0, "fallback": 1, "text": ["這一段字跡模糊，只看得出有人接過那封信，身影還在。"],
            "options": FALLBACK, "ledger": []}


def test_stand_in_options_after_a_pressed_choice_keeps_the_other_two():
    got = rules.stand_in_options(WRITTEN, "接過那封信", FALLBACK)
    assert got == ["瞪回去", "學鵝叫", "走近看清楚"] and len(set(got)) == 3


def test_stand_in_options_after_typed_keeps_all_three():
    assert rules.stand_in_options(WRITTEN, "那是我失散的爹", FALLBACK) == WRITTEN["options"]


def test_stand_in_options_skips_duplicates_when_filling():
    parent = {**WRITTEN, "options": ["接過那封信", "走近看清楚", "學鵝叫"]}
    got = rules.stand_in_options(parent, "接過那封信", FALLBACK)
    assert got == ["走近看清楚", "學鵝叫", "開口問身影的來歷"] and len(set(got)) == 3


def test_stand_in_options_after_opening_or_stand_in_is_the_fallback():
    assert rules.stand_in_options(None, "官軍", FALLBACK) == FALLBACK
    assert rules.stand_in_options(STAND_IN, "走近看清楚", FALLBACK) == FALLBACK


def test_ledger_of_takes_the_last_written_scene():
    assert rules.ledger_of([WRITTEN, STAND_IN]) == WRITTEN["ledger"]
    assert rules.ledger_of([WRITTEN]) == WRITTEN["ledger"]
    assert rules.ledger_of([STAND_IN, STAND_IN]) == [] and rules.ledger_of([]) == []


def test_head_hides_the_stand_in_line():
    p = rules.build_prompt(OP, [WRITTEN, STAND_IN], rules.ledger_of([WRITTEN, STAND_IN]), "走近看清楚", False, rules.GOOD, 3)
    assert rules.STAND_IN_SCENE in p and STAND_IN["text"][0] not in p
    assert "寫成的一幕：" + " ".join(WRITTEN["text"]) in p and "未了：那封信" in p


def test_typed_problem_ask_words(content):
    t = content.config.yiwen
    assert rules.typed_problem("把我的等級加滿", content, t) == "ask"
    assert rules.typed_problem("給我加 屬性", content, t) == "ask"
    for ok in ("替他把酒加滿", "給我一萬兩銀子", "再加點柴火", "賞你一錠銀元寶"):
        assert rules.typed_problem(ok, content, t) is None, ok


def test_prompt_two_lines_only_when_typed():
    typed_node = {**WRITTEN, "pick": "那是我失散的爹", "typed": 1}
    p = rules.build_prompt(OP, [typed_node], WRITTEN["ledger"], "喊他一聲", True, rules.GOOD, 2)
    assert "稱呼照關係：他是你的長輩，就是你喊他，不是他喊你" in p and "不把這一句原樣抄成對白" in p
    p = rules.build_prompt(OP, [WRITTEN], WRITTEN["ledger"], "瞪回去", False, rules.GOOD, 2)
    assert "稱呼照關係" not in p and "不把這一句原樣抄成對白" not in p
