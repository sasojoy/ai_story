"""武學的功效（武學與成長設計第十三節）：資料與層數。
武學重構（Joy 2026-10-20）之後玩家自己武學的功效照槽裡的意境填（arts.apply），全服那一份寫的 traits 會被蓋掉：
算層數的測試改成把意境裝進槽、強度就是層數。depth.py（合成時疊層、打散、三種走向）整個拿掉，那幾條測試一併刪除。"""
import pytest

from tianxia import traits
from tianxia.martial_arts import ATTRIBUTES, Insight, generate_from_name


def _art(name, attribute="快", traits_=(), special=None, kind="武學"):
    return generate_from_name(name, kind, name, attribute=attribute).model_copy(
        update={"origin": "fused", "traits": list(traits_), "special": special},
    )


def test_every_attribute_has_one_general_trait(content):
    primary = [t for t in content.traits.general if not t.id]  # 意境效果池：每一路第一個（鍵是屬性），第二個寫 id
    assert sorted(t.attribute for t in primary) == sorted(ATTRIBUTES)
    assert sorted(t.attribute for t in content.traits.general if t.id) == sorted(ATTRIBUTES)
    assert traits.general(content, "快").name == "先手" and traits.general(content, "實").name == "厚"


def _own(state, n, attribute, special=None):
    """一個自己悟的意境（私有 id「悟:N」），可以帶秘方的特別功效。基本意境一種屬性只有一個、又只能裝在一門上，
    兩門都要同屬性的功效時用它補。"""
    ins = Insight(id=f"悟:{n}", name=f"悟{n}", attribute=attribute, secret_special=special)
    state.player.own_insights[ins.id] = ins
    return ins.id


def _wear(state, world, art, quality, slots):
    """把 art 登記、穿上身、照 slots〔(意境 id, 強度)〕裝滿它的槽（武學重構：功效＝槽裡的意境，強度＝層數）。"""
    world.claim_skill_name(art)
    if art.kind == "內功":
        state.player.member.neigong_id = art.id
    else:
        state.player.member.wugong_id = art.id
    state.player.art_quality[art.id] = quality
    state.player.art_slots[art.id] = [i for i, _ in slots]
    for i, strength in slots:
        if i not in state.player.insights:
            state.player.insights.append(i)
        if strength > 1:
            state.player.insight_strength[i] = strength


def test_an_art_without_traits_has_nothing_unless_it_is_written_in_the_content():
    """武學重構：自己的武學槽空著就沒有功效（以前當作有自己屬性那一個）；內容寫死的武學沒寫 traits 時照舊當作只有自己的屬性。"""
    assert traits.traits_of(_art("舊拳", attribute="剛")) == []
    assert traits.traits_of(_art("新拳", attribute="剛", traits_=["剛", "快", "實"])) == ["剛", "快", "實"]
    assert traits.traits_of(_art("名拳", attribute="剛").model_copy(update={"origin": "historical"})) == ["剛"]


def test_layers_add_up_both_arts_by_quality(state, content, world):
    """身上的武學是上品【破甲●●、先手●】、內功是下品【化勁●、破甲●】：破甲＝2 層×2＋1 層×1＝5（設計 13.2 的算例，改照槽裝）。"""
    outer = _art("裂石拳", attribute="剛")
    inner = _art("柔息功", attribute="柔", kind="內功")
    _wear(state, world, outer, "上品", [("huo", 2), ("feng", 1)])
    _wear(state, world, inner, "下品", [("shui", 1), (_own(state, 1, "剛"), 1)])
    lo = traits.loadout(state, content, world)
    assert lo.layers["difficulty_cut"] == 5 and lo.layers["big_win"] == 2 and lo.layers["toll_cut"] == 1
    assert traits.amount(content, lo, "difficulty_cut") == pytest.approx(0.5)  # 5×10% 剛好上限
    assert traits.amount(content, lo, "big_win") == pytest.approx(0.2)
    assert lo.source["破甲"] == "裂石拳"  # 層數多的那一門（演出句的 {art}）


def test_a_special_counts_once_even_on_both_arts(state, content, world):
    """兩門槽裡各裝一個帶「連環」的秘方意境：特別功效只算一次。"""
    _wear(state, world, _art("甲拳"), "下品", [(_own(state, 1, "快", "lianhuan"), 1)])
    _wear(state, world, _art("乙功", attribute="柔", kind="內功"), "下品", [(_own(state, 2, "柔", "lianhuan"), 1)])
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
    assert "〔破甲〕強攻剋中對手時，有 30% 的機會讓他下一回合的固守與借力落空" in line  # 2 層 ×1.5 ×10%
    assert "〔先手〕剋中對手後有 15% 的機會連環" in line and "〔連環〕每回合有 20% 的機會連環" in line


def test_the_special_descriptions_read_as_written(content):
    """特別功效的說明照內容寫死（本命戰法第三批：都換成回合裡的戰法）。"""
    assert "〔悟招〕每被對手剋中一次就看破一分" in traits.card_line(content, _art("悟拳", special="wuzhao"))
    assert "〔輕身〕前 2 回合有 15% 的機會化影" in traits.card_line(content, _art("輕功", special="qingshen"))
    assert "〔回春〕每回合開始回氣血 3%" in traits.card_line(content, _art("春功", special="huichun"))


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
    assert art.traits == [] and art.special is None and traits.traits_of(art) == []  # 武學重構：槽空著沒有功效


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
    """槽裡的意境帶了內容裡已經沒有的特別功效 id（內容改過）：不當機，也不算數。"""
    art = _art("怪拳", special="已經刪掉了")
    _wear(state, world, art, "下品", [(_own(state, 1, "快", "已經刪掉了"), 1)])
    lo = traits.loadout(state, content, world)
    assert lo.specials == {} and traits.special(content, "已經刪掉了") is None
    assert "已經刪掉了" not in traits.card_line(content, art)
