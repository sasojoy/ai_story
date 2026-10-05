"""武學的功效（武學與成長設計第十三節）：資料與層數。"""
import pytest

from tianxia import traits
from tianxia.martial_arts import ATTRIBUTES, generate_from_name


def _art(name, attribute="快", traits_=(), special=None, kind="武學"):
    return generate_from_name(name, kind, name, attribute=attribute).model_copy(
        update={"origin": "fused", "traits": list(traits_), "special": special},
    )


def test_every_attribute_has_one_general_trait(content):
    assert sorted(t.attribute for t in content.traits.general) == sorted(ATTRIBUTES)
    assert traits.general(content, "快").name == "先手" and traits.general(content, "實").name == "厚"


def test_an_art_without_traits_has_its_own_attribute():
    """Review Focus 4：舊資料、內容寫的武學沒有 traits，當作只有自己屬性那一個。"""
    assert traits.traits_of(_art("舊拳", attribute="剛")) == ["剛"]
    assert traits.traits_of(_art("新拳", attribute="剛", traits_=["剛", "快", "實"])) == ["剛", "快", "實"]


def test_layers_add_up_both_arts_by_quality(state, content, world):
    """身上的武學是上品【破甲｜先手、破甲】、內功是下品【化勁｜破甲】：破甲＝2 層×2＋1 層×1＝5（設計 13.2 的算例）。"""
    outer = _art("裂石拳", attribute="剛", traits_=["剛", "快", "剛"])
    inner = _art("柔息功", attribute="柔", traits_=["柔", "剛"], kind="內功")
    world.claim_skill_name(outer)
    world.claim_skill_name(inner)
    state.player.member.wugong_id, state.player.member.neigong_id = outer.id, inner.id
    state.player.art_quality[outer.id], state.player.art_quality[inner.id] = "上品", "下品"
    lo = traits.loadout(state, content, world)
    assert lo.layers["difficulty_cut"] == 5 and lo.layers["big_win"] == 2 and lo.layers["toll_cut"] == 1
    assert traits.amount(content, lo, "difficulty_cut") == pytest.approx(0.2)  # 5×4% 剛好上限
    assert traits.amount(content, lo, "big_win") == pytest.approx(0.08)
    assert lo.source["破甲"] == "裂石拳"  # 層數多的那一門（演出句的 {art}）


def test_a_special_counts_once_even_on_both_arts(state, content, world):
    a = _art("甲拳", special="lianhuan")
    b = _art("乙功", attribute="柔", special="lianhuan", kind="內功")
    world.claim_skill_name(a)
    world.claim_skill_name(b)
    state.player.member.wugong_id, state.player.member.neigong_id = a.id, b.id
    lo = traits.loadout(state, content, world)
    assert list(lo.specials) == ["double_luck"]


def test_no_arts_no_traits(state, content, world):
    state.player.member.wugong_id = state.player.member.neigong_id = None
    lo = traits.loadout(state, content, world)
    assert lo.layers == {} and lo.specials == {} and traits.amount(content, lo, "big_win") == 0


def test_the_card_line_lists_the_traits_with_this_arts_numbers(content):
    art = _art("裂石拳", attribute="剛", traits_=["剛", "快", "剛"], special="lianhuan").model_copy(update={"quality": "中品"})
    line = traits.card_line(content, art)
    assert line.startswith("功效：")
    assert "〔破甲〕對手強度當作低 12%" in line  # 2 層 ×1.5 ×4%
    assert "〔先手〕大勝的門檻低 6%" in line and "〔連環〕每場擲兩次運氣" in line


def test_the_point_specials_print_points_not_percentages(content):
    """悟招（心得）與輕身（體力）的數字是點數，其他功效是比例。"""
    assert "〔悟招〕打贏多拿 5 心得" in traits.card_line(content, _art("悟拳", special="wuzhao"))
    assert "〔輕身〕遊歷少花 2 體力" in traits.card_line(content, _art("輕功", special="qingshen"))
    assert "〔回春〕不論勝負，打完回氣血上限的 3%" in traits.card_line(content, _art("春功", special="huichun"))


def test_the_card_line_is_empty_when_the_content_has_no_traits(content):
    content.traits.general.clear()
    content.traits.special.clear()
    assert traits.card_line(content, _art("裂石拳")) == ""


def test_an_art_stored_before_traits_existed_still_loads():
    """已經登記、沒有 traits／special 欄位的合成武學（存成 JSON）：欄位有預設值，當作只有自己屬性那一個、沒有特別功效。"""
    from tianxia.martial_arts import MartialArt

    old = generate_from_name("舊拳", "武學", "old", attribute="剛").model_dump()
    del old["traits"], old["special"]
    art = MartialArt.model_validate(old)
    assert art.traits == [] and art.special is None and traits.traits_of(art) == ["剛"]


def test_the_special_of_a_content_skill_reaches_the_art(content, world):
    """內容寫的武學（名將本命絕學）的獨特功效，經 team.resolve_art 帶到 MartialArt.special；沒寫就是 None。"""
    from tianxia import team

    first, second = list(content.skills)[:2]
    content.skills[first].special = "lianhuan"
    assert team.resolve_art(first, content, world).special == "lianhuan"
    assert team.resolve_art(second, content, world).special is None


def test_content_art_carries_the_special_on_both_branches():
    from tianxia.martial_arts import content_art

    assert content_art("a", "甲", "武學", "剛", "下品", special="lianhuan").special == "lianhuan"  # 基礎武學那一支
    assert content_art("b", "乙", "武學", "剛", "絕學", special="huming").special == "huming"  # 歷史武學那一支
    assert content_art("c", "丙", "武學", "剛", "上品").special is None


def test_an_unknown_special_id_is_ignored(state, content, world):
    """登記的武學帶了內容裡已經沒有的特別功效 id（內容改過）：不當機，也不算數。"""
    art = _art("怪拳", special="已經刪掉了")
    world.claim_skill_name(art)
    state.player.member.wugong_id = art.id
    lo = traits.loadout(state, content, world)
    assert lo.specials == {} and traits.special(content, "已經刪掉了") is None
    assert "已經刪掉了" not in traits.card_line(content, art)
