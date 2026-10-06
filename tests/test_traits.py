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
    assert "〔破甲〕對手的強度等於低了 12%，更容易贏" in line  # 2 層 ×1.5 ×4%
    assert "〔先手〕比較容易打出大勝（大勝要贏的幅度少對手強度的 6%）" in line and "〔連環〕每場打鬥碰兩次運氣" in line


def test_the_point_specials_print_points_not_percentages(content):
    """悟招（心得）與輕身（體力）的數字是點數，其他功效是比例。"""
    assert "〔悟招〕打贏多得 5 點心得" in traits.card_line(content, _art("悟拳", special="wuzhao"))
    assert "〔輕身〕遊歷少花 2 點體力" in traits.card_line(content, _art("輕功", special="qingshen"))
    assert "〔回春〕不論輸贏，打完都回復氣血上限的 3%" in traits.card_line(content, _art("春功", special="huichun"))


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


def test_a_fuse_puts_the_insight_first_and_pushes_out_the_oldest():
    """設計 13.3 的例子：粗淺拳腳（實）→ 融風【先手｜厚】→ 融火【破甲｜先手、厚】→ 融山【穩｜破甲、先手】。"""
    fist = _art("粗淺拳腳", attribute="實")
    step1 = fist.model_copy(update={"traits": traits.inherit_fuse(fist, "快"), "attribute": "快"})
    assert step1.traits == ["快", "實"]
    step2 = step1.model_copy(update={"traits": traits.inherit_fuse(step1, "剛"), "attribute": "剛"})
    assert step2.traits == ["剛", "快", "實"]
    assert traits.inherit_fuse(step2, "慢") == ["慢", "剛", "快"]


def test_fusing_the_same_insight_over_and_over_stacks_one_trait():
    """設計 13.3：一路只融風是【先手｜先手、先手】，專精一條路。"""
    art = _art("粗淺拳腳", attribute="快", traits_=["快", "快", "快"])
    assert traits.inherit_fuse(art, "快") == ["快", "快", "快"]


def test_a_blend_takes_each_parents_own_trait():
    """旋風腿【先手｜厚】＋烈火掌【破甲｜…】→ 屬陽【乘勝｜先手、破甲】；不分先後。"""
    wind = _art("旋風腿", attribute="快", traits_=["快", "實"])
    fire = _art("烈火掌", attribute="剛", traits_=["剛", "快", "實"])
    assert sorted(traits.inherit_blend(wind, fire, "陽")[1:]) == sorted(["快", "剛"])
    assert traits.inherit_blend(wind, fire, "陽") == traits.inherit_blend(fire, wind, "陽")
    assert traits.inherit_blend(wind, fire, "陽")[0] == "陽"


def test_a_blend_of_arts_without_a_trait_list_still_takes_their_attributes():
    """內容寫的武學（基礎武學）沒有 traits 欄位：各傳自己的屬性。"""
    fist, kick = _art("粗淺拳腳", attribute="實"), _art("湖邊腿法", attribute="快")
    got = traits.inherit_blend(fist, kick, "陽")
    assert got[0] == "陽" and sorted(got[1:]) == sorted(["實", "快"])


def test_specials_come_from_the_pool_about_one_in_twenty(content):
    content.traits.special.append(content.traits.special[0].model_copy(update={"id": "only", "name": "獨門", "pool": False}))
    rolled = [traits.roll_special(content, f"融|{i}", 1) for i in range(4000)]
    hits = [r for r in rolled if r is not None]
    assert 0.04 < len(hits) / 4000 < 0.06 and "only" not in hits
    assert traits.roll_special(content, "融|x", 1) == traits.roll_special(content, "融|x", 1)  # 同一個配方同一季一樣


def test_the_special_roll_follows_the_configured_chance(content):
    content.config.special_trait_chance = 0.0
    assert all(traits.roll_special(content, f"融|{i}", 1) is None for i in range(200))
    content.config.special_trait_chance = 1.0
    pool = {t.id for t in content.traits.special if t.pool}
    rolled = {traits.roll_special(content, f"融|{i}", 1) for i in range(400)}
    assert None not in rolled and rolled <= pool and len(rolled) > 1  # 每一爐都有，而且不是永遠同一個


def test_the_special_roll_changes_with_the_season(content):
    """配方加這一季的天機：同一個配方換季可以換成別的結果（跟武學的雜湊一樣）。"""
    content.config.special_trait_chance = 0.5
    seasons = [traits.roll_special(content, "融|basic_fist+feng", tianji) for tianji in range(40)]
    assert len(set(seasons)) > 2


def test_no_pool_or_no_traits_means_no_special(content):
    content.config.special_trait_chance = 1.0
    for t in content.traits.special:
        t.pool = False
    assert traits.roll_special(content, "融|x", 1) is None


def test_the_naming_note_names_the_traits_and_never_numbers(content):
    note = traits.naming_note(content, ["快", "實"], None)
    assert "先手" in note and "厚" in note and "罕見" not in note and note.endswith("\n")
    with_special = traits.naming_note(content, ["剛", "快", "實"], "lianhuan")
    assert "破甲、先手、厚" in with_special and "罕見的「連環」" in with_special
    assert not any(ch.isdigit() for ch in with_special)


def test_the_naming_note_is_empty_when_the_content_has_no_traits(content):
    content.traits.general.clear()
    content.traits.special.clear()
    assert traits.naming_note(content, ["快"], None) == ""


def test_an_unknown_special_id_is_ignored(state, content, world):
    """登記的武學帶了內容裡已經沒有的特別功效 id（內容改過）：不當機，也不算數。"""
    art = _art("怪拳", special="已經刪掉了")
    world.claim_skill_name(art)
    state.player.member.wugong_id = art.id
    lo = traits.loadout(state, content, world)
    assert lo.specials == {} and traits.special(content, "已經刪掉了") is None
    assert "已經刪掉了" not in traits.card_line(content, art)
