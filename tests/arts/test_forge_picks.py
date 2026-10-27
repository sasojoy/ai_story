"""煉製頁好用一點（企劃者 2026-10-10「武學跟意境堆一大堆都懶得合……合過的意境不能合，常常丟上去按合成才知道」）：
爐裡放了一個意境時，另一格每一個合不合得了（skillview.forge_picks）。
照開爐時同一個判斷（fusion.merge_problem）算，合不了的帶兩三個字的原因（fusion.Refusal.short）。
煉製只剩意境＋意境（Joy 2026-10-21）：武學＋武學、武學＋意境拿掉了，裝槽到修練頁。"""
from __future__ import annotations

import pytest

from tianxia import fusion, skillview


@pytest.fixture
def ready(state):
    state.player.member.wugong_id = "basic_fist"
    state.player.insights = ["feng", "huo"]
    state.player.stats["xinde"] = 100
    return state


def test_a_refusal_carries_a_short_reason(ready, content, world):
    ready.player.stats["xinde"] = 0
    assert fusion.merge_problem(ready, content, world, "feng", "huo").short == "心得不足"


def test_with_an_insight_in_the_pot_each_insight_is_marked(ready, content, world):
    picks = skillview.forge_picks(ready, content, world, ["feng"])
    assert set(picks) == {"insights"}  # 爐裡只合意境：武學不列
    assert picks["insights"]["huo"] is None and picks["insights"]["feng"]["short"] == "要兩份"  # 同一份放兩次不成（揣摩要兩份）
    ready.player.insights.append("feng~2")
    assert skillview.forge_picks(ready, content, world, ["feng"])["insights"]["feng~2"] is None  # 同一種的另一份：揣摩


def test_an_empty_full_or_foreign_pot_gives_no_marks(ready, content, world):
    assert skillview.forge_picks(ready, content, world, []) is None
    assert skillview.forge_picks(ready, content, world, ["feng", "huo"]) is None
    assert skillview.forge_picks(ready, content, world, ["not_mine"]) is None  # 不是你的東西：不拿它探別的

