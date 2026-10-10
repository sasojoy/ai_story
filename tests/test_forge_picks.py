"""煉製頁好用一點（企劃者 2026-10-10「武學跟意境堆一大堆都懶得合……合過的意境不能合，常常丟上去按合成才知道」）：
爐裡放了一樣時，另一格每一樣合不合得了（skillview.forge_picks）。
照開爐時同一個判斷（fusion 的 *_problem）算，合不了的帶兩三個字的原因（fusion.Refusal.short）。"""
from __future__ import annotations

from unittest import mock

import pytest

from tianxia import fusion, naming, skillview


def named(name):
    client = mock.Mock()
    client.chat_structured.return_value = naming.NameReply(name=name, description="一句話說明。")
    return client


@pytest.fixture
def ready(state):
    state.player.member.wugong_id = "basic_fist"
    state.player.insights = ["feng", "huo"]
    state.player.stats["xinde"] = 100
    return state


def test_a_refusal_still_reads_as_the_same_sentence_and_carries_a_short_reason(ready, content, world):
    fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    problem = fusion.fuse_problem(ready, content, world, "basic_fist", "feng")
    assert problem == "這一爐合出來還是【旋風腿】，你已經有了——換一組試試吧。" and problem.short == "已經有了"
    ready.player.stats["xinde"] = 0
    assert fusion.fuse_problem(ready, content, world, "basic_fist", "huo").short == "心得不足"


def test_with_an_art_in_the_pot_each_insight_and_art_is_marked(ready, content, world):
    """爐裡放【旋風腿】（融過風）：風是「來歷裡融過」、火合得了；另一門武學（基礎拳腳）照兩門武學的判斷。"""
    art, _ = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    picks = skillview.forge_picks(ready, content, world, art.id, [])
    assert picks["insights"]["feng"]["short"] == "來歷裡融過" and "早已融過" in picks["insights"]["feng"]["why"]
    assert picks["insights"]["huo"] is None
    assert picks["arts"] == {"basic_fist": None}  # 兩門武學合得了；爐裡那一門自己不列


def test_with_an_insight_in_the_pot_each_art_and_insight_is_marked(ready, content, world):
    art, _ = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    picks = skillview.forge_picks(ready, content, world, None, ["feng"])
    assert picks["arts"]["basic_fist"]["short"] == "已經有了"  # 基礎拳腳＋風＝旋風腿，你已經有了
    assert picks["arts"][art.id]["short"] == "來歷裡融過"
    assert picks["insights"] == {"feng": None, "huo": None}  # 合併：同一個意境也能放兩次


def test_an_empty_full_or_foreign_pot_gives_no_marks(ready, content, world):
    assert skillview.forge_picks(ready, content, world, None, []) is None
    assert skillview.forge_picks(ready, content, world, "basic_fist", ["feng"]) is None
    assert skillview.forge_picks(ready, content, world, "not_mine", []) is None  # 不是你的東西：不拿它探別的

