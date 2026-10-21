"""煉製頁的預覽卡（skillview.forge_preview；武學重構之後）：兩格都放好時，合成前就看得到合出來的樣子。
武學重構（Joy 2026-10-20，/mnt/project-files/plan/武學重構定案.md）拿掉了「合成即設計」那一批的東西——品質照投入定（fuse_quality.fixed）、
承底的成數（fusion_depth.inherit_share、art_free_levels）、重數境界挑屬性（depth.merge_attribute、pick_note）、代數挑屬性（blend_shape 的 gens）、
武學列的 forge_fixed／forge_odds——那些測試整批刪掉；這裡只留預覽卡。煉製只剩意境合成（Joy 2026-10-21）：合成（武學＋武學）與裝意境的預覽卡跟著拿掉，
只測合併、揣摩兩種。"""
import pytest

from tianxia import skillview


@pytest.fixture
def designed(state):
    state.player.member.wugong_id = "basic_fist"
    state.player.insights = ["feng", "huo"]
    state.player.stats["xinde"] = 100
    return state


def test_merging_two_different_insights_previews_a_new_insight(designed, content, world):
    card = skillview.forge_preview(designed, content, world, ["feng", "huo"])
    line = skillview.forge_line(designed, content, world, ["feng", "huo"])
    assert card["kind"] == "合併" and card["made"] == "一個新的意境" and card["quality"] == "中品"  # 兩份裡較好的品質
    assert f"屬{card['attribute']}" in line and card["known"] == "沒人合過。"
    assert card["depth"].startswith("擲一到兩個效果：")


def test_pondering_the_same_insight_previews_one_more_dot(designed, content, world):
    """同一種意境的兩份是揣摩：卡上寫揉完之後的層數與那一招的數字；同一份放兩次照樣是揣摩的卡、寫為什麼不成。"""
    designed.player.insights.append("feng~2")
    card = skillview.forge_preview(designed, content, world, ["feng", "feng~2"])
    assert card["kind"] == "揣摩" and card["made"] == "「風」先手二重" and card["problem"] is None
    assert card["traits"] == [{"name": "先手", "layers": 2, "grand": False}]
    assert "20%" in card["depth"]  # 先手一層 10%，兩層 20%
    same = skillview.forge_preview(designed, content, world, ["feng", "feng"])
    assert same["kind"] == "揣摩" and same["problem"].short == "要兩份"


def test_no_card_for_an_empty_pot_a_single_thing_or_what_is_not_yours(designed, content, world):
    assert skillview.forge_preview(designed, content, world, []) is None
    assert skillview.forge_preview(designed, content, world, ["feng"]) is None
    assert skillview.forge_preview(designed, content, world, ["feng", "shui"]) is None  # 不是你的：不露
