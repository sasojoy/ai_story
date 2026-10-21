"""煉製頁的預覽卡（skillview.forge_preview；武學重構之後）：兩格都放好時，合成前就看得到合出來的樣子。
武學重構（Joy 2026-10-20，/mnt/project-files/plan/武學重構定案.md）拿掉了「合成即設計」那一批的東西——品質照投入定（fuse_quality.fixed）、
承底的成數（fusion_depth.inherit_share、art_free_levels）、重數境界挑屬性（depth.merge_attribute、pick_note）、代數挑屬性（blend_shape 的 gens）、
武學列的 forge_fixed／forge_odds——那些測試整批刪掉；這裡只留預覽卡，改測新的四種：合成、裝意境、合併、揣摩。"""
import pytest

from tianxia import arts as arts_mod
from tianxia import skillview


@pytest.fixture
def designed(state):
    state.player.member.wugong_id = "basic_fist"
    state.player.arts = ["lake_kick"]
    state.player.insights = ["feng", "huo"]
    state.player.stats["xinde"] = 100
    return state


def test_slotting_previews_the_slot_and_the_skill_and_costs_nothing(designed, content, world):
    """武學＋意境：不是合成，是裝進第一個空槽；卡上寫第幾格、這一招與強度，不花錢。"""
    card = skillview.forge_preview(designed, content, world, "basic_fist", ["feng"])
    line = skillview.forge_line(designed, content, world, "basic_fist", ["feng"])
    assert card["kind"] == "裝意境" and card["problem"] is None and card["quality"] == "中品"  # 意境效果池：那一份的品質
    assert card["made"] == "【粗淺拳腳】第 1 格" and "第 1 格" in line
    assert card["attribute"] == "快" and card["traits"] == [{"name": "先手", "layers": 1, "grand": False}]
    assert card["depth"].startswith("〔先手〕剋中對手後") and "這一份是中品：〔先手〕" in line
    assert card["cost"] == "不花心得體力" and "不花心得體力" in line


def test_a_full_slot_is_named_on_the_card(designed, content, world):
    """槽滿了：卡上寫「槽滿了」，problem 是 arts.slot_problem 那一句。"""
    arts_mod.slot(designed, content, world, "basic_fist", "huo")
    designed.player.insights.append("shui")
    arts_mod.slot(designed, content, world, "basic_fist", "shui")
    card = skillview.forge_preview(designed, content, world, "basic_fist", ["feng"])
    assert card["made"].endswith("（槽滿了）")
    assert card["problem"] == arts_mod.slot_problem(designed, content, world, "basic_fist", "feng")


def test_blending_previews_a_new_art_with_its_grade_and_empty_slots(designed, content, world):
    """武學＋武學：一門新武學，品級兩門取高，從第一成起練，槽是空的。"""
    card = skillview.forge_preview(designed, content, world, "basic_fist", [], other_art="lake_kick")
    line = skillview.forge_line(designed, content, world, "basic_fist", [], "lake_kick")
    assert card["kind"] == "合成" and card["problem"] is None
    assert card["made"] == "一門新武學" and card["quality"] == "下品" and card["level"] == 1
    assert card["slots"] == "意境槽 2 格（空的）" and "意境槽 2 格" in line
    assert card["known"] == "沒人合過。" and "心得" in card["cost"]


def test_merging_two_different_insights_previews_a_new_insight(designed, content, world):
    card = skillview.forge_preview(designed, content, world, None, ["feng", "huo"])
    line = skillview.forge_line(designed, content, world, None, ["feng", "huo"])
    assert card["kind"] == "合併" and card["made"] == "一個新的意境" and card["quality"] == "中品"  # 兩份裡較好的品質
    assert f"屬{card['attribute']}" in line and card["known"] == "沒人合過。"
    assert card["depth"].startswith("擲一到兩個效果：")


def test_pondering_the_same_insight_previews_one_more_dot(designed, content, world):
    """同一種意境的兩份是揣摩：卡上寫揉完之後的層數與那一招的數字；同一份放兩次照樣是揣摩的卡、寫為什麼不成。"""
    designed.player.insights.append("feng~2")
    card = skillview.forge_preview(designed, content, world, None, ["feng", "feng~2"])
    assert card["kind"] == "揣摩" and card["made"] == "「風」先手二重" and card["problem"] is None
    assert card["traits"] == [{"name": "先手", "layers": 2, "grand": False}]
    assert "20%" in card["depth"]  # 先手一層 10%，兩層 20%
    same = skillview.forge_preview(designed, content, world, None, ["feng", "feng"])
    assert same["kind"] == "揣摩" and same["problem"].short == "要兩份"


def test_no_card_for_an_empty_pot_a_single_thing_or_what_is_not_yours(designed, content, world):
    assert skillview.forge_preview(designed, content, world, None, []) is None
    assert skillview.forge_preview(designed, content, world, "basic_fist", []) is None
    assert skillview.forge_preview(designed, content, world, "caocao_wugong", ["feng"]) is None  # 不是你的：不露
