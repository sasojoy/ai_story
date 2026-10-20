"""煉製頁好用一點（企劃者 2026-10-10「武學跟意境堆一大堆都懶得合……合過的意境不能合，常常丟上去按合成才知道」）：
爐裡放了一樣時，另一格每一樣合不合得了（skillview.forge_picks）。
照開爐時同一個判斷（fusion 的 *_problem、arts.slot_problem）算，合不了的帶兩三個字的原因（fusion.Refusal.short）。
武學重構：武學＋意境是裝槽、不是合成；融過的意境（來歷裡融過）那一套拿掉了。"""
from __future__ import annotations

from unittest import mock

import pytest

from tianxia import arts as arts_mod
from tianxia import fusion, naming, skillview


def named(name):
    client = mock.Mock()
    client.chat_structured.return_value = naming.NameReply(name=name, description="一句話說明。")
    return client


@pytest.fixture
def ready(state):
    state.player.member.wugong_id = "basic_fist"
    state.player.arts = ["lake_kick"]  # 武學重構：武學＋意境是裝槽，合成只剩武學＋武學，要第二門
    state.player.insights = ["feng", "huo"]
    state.player.stats["xinde"] = 100
    return state


def test_a_refusal_still_reads_as_the_same_sentence_and_carries_a_short_reason(ready, content, world):
    """武學重構：武學＋意境不再合成，改測武學＋武學（blend_problem）。"""
    art, _ = fusion.blend(ready, content, world, named("旋風腿"), "basic_fist", "lake_kick")
    problem = fusion.blend_problem(ready, content, world, "basic_fist", "lake_kick")
    assert problem == f"這兩門合出來還是【{art.name}】，你已經有了——換一門吧。" and problem.short == "已經有了"
    assert fusion.fuse_problem(ready, content, world, "basic_fist", "feng").short == "改裝槽"  # 武學＋意境：去裝槽
    ready.player.stats["xinde"] = 0
    assert fusion.merge_problem(ready, content, world, "feng", "huo").short == "心得不足"


def test_with_an_art_in_the_pot_each_insight_and_art_is_marked(ready, content, world):
    """爐裡放基礎拳腳：意境照裝槽的判斷（arts.slot_problem），另一門武學照兩門武學的判斷（blend_problem）。"""
    picks = skillview.forge_picks(ready, content, world, "basic_fist", [])
    assert picks["insights"] == {"feng": None, "huo": None} and picks["arts"] == {"lake_kick": None}  # 爐裡那一門自己不列
    arts_mod.slot(ready, content, world, "basic_fist", "feng")
    picks = skillview.forge_picks(ready, content, world, "basic_fist", [])
    assert picks["insights"]["feng"]["why"] == arts_mod.DUP_LINE.format(name="粗淺拳腳", insight="風")
    assert picks["insights"]["huo"] is None


def test_with_an_insight_in_the_pot_each_art_and_insight_is_marked(ready, content, world):
    picks = skillview.forge_picks(ready, content, world, None, ["feng"])
    assert picks["arts"] == {"basic_fist": None, "lake_kick": None}  # 兩門都裝得下
    assert picks["insights"]["huo"] is None and picks["insights"]["feng"]["short"] == "要兩份"  # 同一份放兩次不成（揣摩要兩份）
    ready.player.insights.append("feng~2")
    assert skillview.forge_picks(ready, content, world, None, ["feng"])["insights"]["feng~2"] is None  # 同一種的另一份：揣摩
    ready.player.insights.remove("feng~2")
    arts_mod.slot(ready, content, world, "basic_fist", "feng")
    picks = skillview.forge_picks(ready, content, world, None, ["feng"])
    assert picks["arts"]["lake_kick"]["why"] == arts_mod.ELSEWHERE_LINE.format(insight="風", other="粗淺拳腳")  # 一個意境只裝一門


def test_an_empty_full_or_foreign_pot_gives_no_marks(ready, content, world):
    assert skillview.forge_picks(ready, content, world, None, []) is None
    assert skillview.forge_picks(ready, content, world, "basic_fist", ["feng"]) is None
    assert skillview.forge_picks(ready, content, world, "not_mine", []) is None  # 不是你的東西：不拿它探別的

