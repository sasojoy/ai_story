"""人物心意的修正輪（減法季批 6 修正輪；PM 2026-10-26 定，交接第四節之十四）：
- FB-825：「你今天勸的」（my_stance_today）只看說話記的那一筆；辦成託付的心意 +1 不改它（行狀照舊兩樣都認）。
正式內容的 season21；模型一律是假的。"""
from __future__ import annotations

import pytest

from stances_kit import LUZHI, real_game
from tianxia import errands, stances

pytestmark = pytest.mark.slow  # 載正式內容、照伺服器開季


def _deliver(g, fid=LUZHI, eid="luzhi_letter"):
    """替他辦成一件送信（ErrandDef.stance：盧植的送信是持重）。"""
    s = g.state
    s.player.affinities[fid] = 50
    errands.give(s, g.content, fid, eid)
    e = s.player.errands[-1]
    s.player.location = e.target
    g.choose(f"errand:deliver:{e.id}")
    assert e.status == "done"


def test_an_errand_does_not_change_what_you_said_today():
    """FB-825：先說速戰、同一天辦成持重的託付——你今天勸的還是速戰；兩樣都記在這一週說過的（行狀用）。"""
    g = real_game()
    s, c = g.state, g.content
    assert stances.record(s, c, LUZHI, "suzhan")
    _deliver(g)
    assert s.world.stance_counts[LUZHI] == {"suzhan": 1, "chizhong": 1}
    assert stances.heard_today(s, c, LUZHI) == "suzhan"
    assert stances.view(s, c, LUZHI)["my_stance_today"] == "suzhan"
    assert s.player.stance_notes[LUZHI].said == ["suzhan", "chizhong"]


def test_an_errand_alone_is_not_what_you_said_and_you_can_still_speak():
    """只辦了託付、今天還沒跟他說話：你今天勸的是空的，說話照樣記得到一筆，記的就是說的那一個。"""
    g = real_game()
    s, c = g.state, g.content
    _deliver(g)
    assert stances.heard_today(s, c, LUZHI) is None
    assert stances.record(s, c, LUZHI, "xumin")
    assert stances.heard_today(s, c, LUZHI) == "xumin"
    assert not stances.record(s, c, LUZHI, "suzhan")  # 一人一天一筆照舊
