"""煉製頁好用一點（企劃者 2026-10-10「武學跟意境堆一大堆都懶得合……合過的意境不能合，常常丟上去按合成才知道」）：
爐裡放了一樣時，另一格每一樣合不合得了（skillview.forge_picks）；爐是空的時，現在合得出來、你還沒有的組合（skillview.forge_ideas）。
兩個都照開爐時同一個判斷（fusion 的 *_problem）算，合不了的帶兩三個字的原因（fusion.Refusal.short）。"""
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


def test_the_ideas_list_what_you_can_make_now_with_the_untried_first(ready, content, world):
    art, _ = fusion.fuse(ready, content, world, named("旋風腿"), "basic_fist", "feng")
    ideas = skillview.forge_ideas(ready, content, world)
    pots = [(i["art"], i["other_art"], tuple(i["insights"])) for i in ideas["items"]]
    assert ideas["total"] == len(pots)
    assert ("basic_fist", None, ("feng",)) not in pots  # 已經有了
    assert (art.id, None, ("feng",)) not in pots  # 來歷裡融過
    assert ("basic_fist", None, ("huo",)) in pots and (art.id, None, ("huo",)) in pots
    assert (None, None, ("feng", "huo")) in pots and (None, None, ("feng", "feng")) in pots  # 合併，同一個也行
    every = [fusion.fuse_problem, fusion.blend_problem, fusion.merge_problem]
    for item in ideas["items"]:  # 每一組都是開爐時那一套判斷說合得了的
        if item["kind"] == "fuse":
            assert every[0](ready, content, world, item["art"], item["insights"][0]) is None
        elif item["kind"] == "blend":
            assert every[1](ready, content, world, item["art"], item["other_art"]) is None
        else:
            assert every[2](ready, content, world, *item["insights"]) is None
    fresh = [i["fresh"] for i in ideas["items"]]
    assert fresh == sorted(fresh, reverse=True)  # 沒人合過的排前面
    assert all(i["fresh"] for i in ideas["items"])  # 這幾組都還沒人合過（旋風腿那一組你已經有了，不列）


def test_a_recipe_someone_else_made_is_listed_but_not_as_untried(ready, content, world, state):
    from tianxia.state import new_game_state

    other = new_game_state(content, "乙")
    other.player.member.wugong_id = "basic_fist"
    other.player.insights = ["huo"]
    other.player.stats["xinde"] = 100
    fusion.fuse(other, content, world, named("烈火拳"), "basic_fist", "huo")
    item = next(i for i in skillview.forge_ideas(ready, content, world)["items"] if i["art"] == "basic_fist" and i["insights"] == ["huo"])
    assert item["fresh"] is False and item["label"] == "【粗淺拳腳】＋「火」"


def test_nothing_is_listed_when_you_cannot_pay(ready, content, world):
    ready.player.stats["xinde"] = 0
    assert skillview.forge_ideas(ready, content, world) == {"items": [], "total": 0}


def test_the_ideas_are_capped_but_the_total_is_told(ready, content, world, monkeypatch):
    monkeypatch.setattr(skillview, "IDEAS_MAX", 2)
    ideas = skillview.forge_ideas(ready, content, world)
    assert len(ideas["items"]) == 2 and ideas["total"] > 2
