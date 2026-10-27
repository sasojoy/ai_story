"""FB-610（QA 驗輿圖第三版第 1 批）：〈天下形勢〉把當天已經打完、作罷的那一場戰書排在最後，讀起來像還有下一仗。

xingshi.facts 把沒有結果的 day_log（戰書）一律當「下一仗打哪裡」排在三條線後面，不看同一場是不是已經收場或作罷。修法（PM 2026-10-21）：
照時間順序排，那一場已經打完（收場、作罷、或正在打）的戰書寫成已經發生的事（letter_done：「某某替某軍下戰書攻某地」），排在它的結果前面；
只有還沒開打的才是「下一仗」、排在三條線後面。

順帶（同一輪 QA）：管理者白天按「現在就開一篇」時，正在打的那一場不寫「一仗打到入夜」（fighting_day）。

輿圖第三版第 5 批：原本還有一條「舊季（第二批投票那一版）的眾議、主將定奪照舊是下一仗」，那兩種 day_log 收掉了（領地爭奪從沒合進
develop／main，沒有那一版的存檔），那一條拿掉；舊資料讀得進來、略過不寫，改在 tests/test_conquest_rules.py 守。"""
from __future__ import annotations

import calendar as pycal
from datetime import datetime

import pytest

from conquest_kit import announce, conquest_game, join
from tianxia import conquest_day, xingshi
from tianxia.state import DayNote

pytestmark = pytest.mark.slow  # 建 Game、載正式內容


def _tw(y, mo, d, h, mi=0) -> float:
    """台灣時間 → 現實 epoch 秒（同 test_xingshi._tw）。"""
    return float(pycal.timegm(datetime(y, mo, d, h, mi).timetuple())) - 8 * 3600


def _world():
    game = conquest_game("season21", xingshi=True)
    return game, game.state.world, game.content


def _letter(side, loc, who=""):
    return DayNote(key=1, side=side, loc=loc, minute=12 * 60, by=conquest_day.LETTER, reason=who)


def _words(c):
    return xingshi.lines(c)["fact"]


def _names(c):
    return c.scenario.faction_name("guan", "guan"), c.scenario.faction_name("huang", "huang")


def _first_line_fact(c, facts) -> int:
    lines = [t.name for t in c.scenario.trends]
    return next(i for i, f in enumerate(facts) if any(f.startswith(f"{name}一帶") for name in lines))


def test_a_letter_whose_siege_was_won_comes_before_the_result_as_a_past_fact():
    """QA 的第一個例子：週三官帥下戰書攻汝南荒野、官甲推滿荒丘、12:00 攻城戰打贏。修前那一篇最後是「官帥替官軍下了戰書，約戰汝南荒野。」"""
    game, w, c = _world()
    guan, _ = _names(c)
    notes = [
        _letter("guan", "runan_wilds", "官帥"),
        DayNote(key=1, side="guan", loc="hilltop_wilds", minute=0, by=conquest_day.FLIP, reason="官甲"),
        DayNote(key=1, side="guan", loc="runan_wilds", minute=12 * 60, by=conquest_day.LETTER, reason="官帥", result="taken",
                taken="guan", margin="大勝", keeper="guard", attackers=["guan"]),
    ]
    facts = xingshi.facts(w, c, notes, {})
    words = _words(c)
    done = words["letter_done"].format(who="官帥", side=guan, place="汝南荒野")
    taken = words["taken"].format(side=guan, margin="大勝", place="汝南荒野")
    flip = words["flip"].format(who="官甲", side=guan, place="荒丘")
    assert words["letter"].format(who="官帥", side=guan, place="汝南荒野") not in facts  # 修前排在最後，像還有下一仗
    assert facts.index(done) < facts.index(flip) < facts.index(taken) < _first_line_fact(c, facts)  # 照時間順序


def test_an_admin_letter_that_was_called_off_is_a_past_fact_before_the_void():
    """QA 的第二個例子：管理者立刻下戰書攻荒丘（沒有名號）、沒人到作罷。修前最後一條「黃巾軍下了戰書，約戰荒丘。」"""
    game, w, c = _world()
    _, huang = _names(c)
    notes = [_letter("huang", "hilltop_wilds"),
             DayNote(key=1, side="huang", loc="hilltop_wilds", minute=12 * 60, by=conquest_day.LETTER, void="absent")]
    facts = xingshi.facts(w, c, notes, {})
    words = _words(c)
    done = words["letter_done_plain"].format(side=huang, place="荒丘")
    void = words["void"].format(side=huang, place="荒丘")
    assert words["letter_plain"].format(side=huang, place="荒丘") not in facts
    assert facts.index(done) < facts.index(void) < _first_line_fact(c, facts)


def test_a_letter_still_to_be_fought_stays_the_next_battle_after_the_lines():
    game, w, c = _world()
    _, huang = _names(c)
    announce(game, "nanyang_road", "huang")  # 那一場還在時程表上、還沒開集結
    facts = xingshi.facts(w, c, [_letter("huang", "nanyang_road", "沈浪")], {})
    pending = _words(c)["letter"].format(who="沈浪", side=huang, place="南陽官道")
    assert facts.index(pending) > _first_line_fact(c, facts)


def test_after_a_held_siege_a_new_letter_on_the_same_block_is_the_next_one():
    game, w, c = _world()
    guan, _ = _names(c)
    announce(game, "runan_wilds", "guan")  # 第二張戰書排的那一場
    notes = [
        _letter("guan", "runan_wilds", "官帥"),
        DayNote(key=1, side="guan", loc="runan_wilds", minute=12 * 60, by=conquest_day.LETTER, reason="官帥", result="held",
                keeper="guard", attackers=["guan"]),
        _letter("guan", "runan_wilds", "官帥"),
    ]
    facts = xingshi.facts(w, c, notes, {})
    words = _words(c)
    done = words["letter_done"].format(who="官帥", side=guan, place="汝南荒野")
    pending = words["letter"].format(who="官帥", side=guan, place="汝南荒野")
    held = words["held"].format(keeper="守軍", place="汝南荒野", attackers=guan)
    assert facts.index(done) < facts.index(held) < _first_line_fact(c, facts) < facts.index(pending)


def test_a_letter_whose_siege_is_being_fought_is_not_the_next_battle():
    game, w, c = _world()
    guan, _ = _names(c)
    slot = announce(game, "runan_wilds", "guan")
    slot.status = "open"  # 開了集結、正在打
    facts = xingshi.facts(w, c, [_letter("guan", "runan_wilds", "官帥")], {})
    words = _words(c)
    done = words["letter_done"].format(who="官帥", side=guan, place="汝南荒野")
    fighting = words["fighting"].format(place="汝南荒野")
    assert facts.index(done) < facts.index(fighting) < _first_line_fact(c, facts)


def test_fighting_in_daytime_does_not_say_nightfall():
    """順帶：管理者白天開單，正在打的那一場不寫「打到入夜」；每天 22:00 那一篇照舊。"""
    game, w, c = _world()
    slot = announce(game, "runan_wilds", "guan")
    slot.status = "open"
    words = _words(c)
    day = xingshi.facts(w, c, [], {}, night=False)
    night = xingshi.facts(w, c, [], {})
    assert words["fighting_day"].format(place="汝南荒野") in day and not any("入夜" in f for f in day)
    assert words["fighting"].format(place="汝南荒野") in night


def test_admin_opens_one_at_noon_without_nightfall():
    game = join(conquest_game("season21", name="Rayal", xingshi=True), "guan")
    game.now = _tw(2026, 10, 20, 10)
    game._conquest_tick()
    game.state.world = game.world.get_season()
    slot = announce(game, "runan_wilds", "guan")
    slot.status = "open"
    game._save_season()
    game.now = _tw(2026, 10, 20, 13)
    game.admin_xingshi_now()
    facts = game.world.get_season().xingshi_ticket.facts
    assert any("汝南荒野" in f and "還沒分出勝負" in f for f in facts)
    assert not any("入夜" in f for f in facts)  # 修前「汝南荒野一仗打到入夜，還沒分出勝負。」
