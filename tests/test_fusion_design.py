"""合成即設計（Joy 2026-10-19「戰力應該更重要」「試試看這樣吧」；/mnt/project-files/plan/合成即設計定案.md）：
品質由投入決定、承底的成數、功效預覽、相剋不相干時照重數境界挑屬性。測試內容關著，這裡自己打開。"""
from unittest import mock

import pytest

from tianxia import depth, fusion, insights, library, naming, skillview, team
from tianxia.martial_arts import Insight


def named(name, description="一句話說明。"):
    client = mock.Mock()
    client.chat_structured.return_value = naming.NameReply(name=name, description=description)
    return client


@pytest.fixture
def designed(state, content):
    content.config.fuse_quality.fixed = True
    content.config.fusion_depth.inherit_share = 0.5
    state.player.member.wugong_id = "basic_fist"
    state.player.insights = ["feng", "huo"]
    state.player.stats["xinde"] = 100
    return state


def _odds(state, content, world, art_id, insight_id):
    return fusion.fuse_odds(
        state, content, art_id, team.player_art(state, content, world, art_id), insights.resolve(insight_id, content, world),
    )


def test_quality_follows_the_score_not_the_dice(content):
    content.config.fuse_quality.fixed = True
    low = fusion._points(content, [("quality", -5), ("level", -6)])
    mid = fusion._points(content, [("quality", 5), ("level", 1.5)])
    high = fusion._points(content, [("quality", 12), ("level", 3), ("attribute", 8), ("insight", 6)])
    assert (low.fixed, mid.fixed, high.fixed) == ("下品", "中品", "上品")
    assert low.odds == {"下品": 100.0, "中品": 0.0, "上品": 0.0}
    assert mid.short_of == pytest.approx(24 - 6.5) and high.short_of is None
    # 擲骰的函式照 fixed 回，不碰亂數
    rng = mock.Mock()
    assert fusion.roll_quality(high, rng) == "上品" and not rng.choices.called


def test_the_same_inputs_always_fuse_into_the_same_quality(designed, content, world):
    """同樣的底、同樣的意境，合十次都是同一品（換季天機不同另算）。"""
    designed.player.art_quality["basic_fist"] = "上品"
    designed.player.member.wugong_level = 8
    designed.player.insights.append("feng")
    odds = _odds(designed, content, world, "basic_fist", "feng")
    assert odds.fixed == "中品"  # 上品的底八成（12＋4.5）、基本意境、實對快不相干：16.5 分，過 6 不到 24
    art, _ = fusion.fuse(designed, content, world, named("旋風腿"), "basic_fist", "feng")
    assert team.player_art(designed, content, world, art.id).quality == "中品"
    assert designed.player.art_rolled[art.id] == "中品"


def test_preview_writes_the_quality_and_a_hint_when_the_next_grade_is_near(designed, content, world):
    designed.player.art_quality["basic_fist"] = "上品"
    designed.player.member.wugong_level = 10
    line = skillview.forge_line(designed, content, world, "basic_fist", ["feng"])
    assert "合出來是中品（" in line and "再講究些便是上品" in line  # 12＋7.5＝19.5，離 24 不到 8
    assert "品質看造化" not in line
    assert "功效：先手 ×1、厚 ×" in line or "功效：先手 ×1" in line  # 合出來的功效先寫出來
    assert "承底子的火候，一上手便是第5成" in line


def test_a_fused_art_inherits_half_the_base_level_and_those_levels_do_not_melt_back(designed, content, world):
    designed.player.member.wugong_level = 7
    art, msgs = fusion.fuse(designed, content, world, named("旋風腿"), "basic_fist", "feng")
    assert designed.player.art_levels[art.id] == 3 and designed.player.art_free_levels[art.id] == 3
    assert any("一上手便是第3成" in m for m in msgs)
    assert library.level_of(designed, art.id) == 3
    # 白送的三成熔了不退：照第三成起算，等於只退基本值
    value = library.melt_value(designed, content, world, art.id)
    assert value == content.config.melt_min_refund
    library.remove_art(designed, art.id)
    assert art.id not in designed.player.art_free_levels


def test_a_first_level_base_inherits_nothing_and_says_nothing(designed, content, world):
    art, msgs = fusion.fuse(designed, content, world, named("旋風腿"), "basic_fist", "feng")
    assert library.level_of(designed, art.id) == 1 and art.id not in designed.player.art_free_levels
    assert not any("一上手" in m for m in msgs)


def test_inheritance_lands_on_the_worn_slot_when_the_art_goes_straight_on(designed, content, world):
    designed.player.member.neigong_id = "basic_breath"
    designed.player.member.neigong_level = 9
    designed.player.member.wugong_level = 5
    art, _ = fusion.blend(designed, content, world, named("混元功"), "basic_breath", "basic_fist")
    assert library.level_of(designed, art.id) == 3  # (9＋5)/2 × 0.5 ＝ 3.5 → 3
    assert designed.player.art_free_levels[art.id] == 3


def test_clashing_insights_merge_into_the_deeper_side(content, world):
    """相剋、不相干時照重數高的那一邊；一樣高時複合的意（陰陽虛實）為主；再一樣才照配方挑。"""
    a = Insight(id="甲", name="甲", attribute="剛", rank=1)
    b = Insight(id="乙", name="乙", attribute="柔", rank=3)
    assert depth.merge_attribute(a, b, "種子", (1, 3)) == "柔"
    assert depth.merge_attribute(b, a, "種子", (3, 1)) == "柔"
    c = Insight(id="丙", name="丙", attribute="虛", rank=1)
    assert depth.merge_attribute(a, c, "種子", (1, 1)) == "虛"  # 不相干、一樣深：複合的意
    assert depth.merge_attribute(a, b, "種子") in ("剛", "柔")  # 沒給重數：舊規則照雜湊
    assert depth.pick_note(a, b, 1, 3, "種子", "重數") == "兩股意相剋，照重數高的那一邊的「柔」"
    assert depth.pick_note(a, Insight(id="丁", name="丁", attribute="剛"), 1, 1, "x", "重數") is None  # 同屬性不寫


def test_blend_picks_the_attribute_of_the_higher_generation(content, world):
    fist = team.resolve_art("basic_fist", content, world)  # 實
    windy = fist.model_copy(update={"id": "風拳", "name": "風拳", "attribute": "快", "gen": 2, "origin": "fused", "base": "basic_fist"})
    gens = (0, 2)
    assert fusion.blend_shape(fist, windy, "0|兼|x", gens).attribute == "快"
    assert fusion.blend_shape(windy, fist, "0|兼|x", (2, 0)).attribute == "快"
