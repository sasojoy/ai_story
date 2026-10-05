import random
import re

import pytest

from tianxia import cultivation, fusion, journal, library, skillview, team
from tianxia.martial_arts import Insight, generate_from_name
from tianxia.state import new_game_state

LOW = {"下品": 100.0, "中品": 0.0, "上品": 0.0, "絕學": 0.0}


class Fixed(random.Random):
    """random() 永遠回傳固定值（同 conftest.FixedRandom）。"""

    def __init__(self, value):
        super().__init__(0)
        self.value = value

    def random(self):
        return self.value


WIN, LOSE = Fixed(0.0), Fixed(0.999)


def kicker_art():
    return generate_from_name("旋風腿", "武學", "旋風腿", weights=LOW, attribute="快").model_copy(
        update={"origin": "fused", "insight": "feng", "base": "basic_fist"},
    )


def equip(state, art_id="旋風腿", insight="feng"):
    state.player.arts = [art_id]
    state.player.insights = [insight]
    state.player.stamina = 150
    return state


@pytest.fixture
def kicker(state, world):
    world.claim_skill_name(kicker_art())
    return equip(state)


def test_chance_climbs_with_each_failure_to_a_sure_thing_for_the_lower_two_steps(content):
    assert [cultivation.chance(content, "中品", n) for n in (0, 1, 8)] == [20, 30, 100]
    assert [cultivation.chance(content, "上品", n) for n in (0, 1, 15)] == [10, 16, 100]


def test_the_climb_to_a_peerless_art_stops_at_half_and_a_pill_adds_on_top_of_the_cap(content):
    """企劃者 2026-10-05：絕學沒有保底，累積機率最多 50%；破境丹的加成加在上限之上，總和不超過 100。"""
    assert [cultivation.chance(content, "絕學", n) for n in (0, 1, 15, 16, 32, 100)] == [4, 7, 49, 50, 50, 50]
    assert cultivation.chance(content, "絕學", 100, 15) == 65
    assert cultivation.chance(content, "絕學", 0, 15) == 19
    assert cultivation.chance(content, "中品", 8) == 100 and cultivation.chance(content, "中品", 8, 99) == 100
    assert cultivation.chance(content, "中品", 100) == 100  # 沒寫上限的那一階（上限預設 100）照舊必成


def test_a_target_with_no_cap_entry_climbs_to_a_hundred_as_before(content):
    content.config.cultivate_cap = {}
    assert cultivation.chance(content, "絕學", 32) == 100 and cultivation.chance(content, "絕學", 100) == 100


def test_a_success_raises_only_this_players_quality(kicker, content, world):
    msgs = cultivation.cultivate(kicker, content, world, "旋風腿", WIN)
    assert kicker.player.art_quality["旋風腿"] == "中品"
    assert world.get_skill("旋風腿").quality == "下品"
    assert kicker.player.stamina == 140 and "中品" in msgs[0]


def test_a_failure_adds_mastery_and_the_next_try_is_likelier(kicker, content, world):
    msgs = cultivation.cultivate(kicker, content, world, "旋風腿", LOSE)
    assert kicker.player.art_mastery["旋風腿"] == 1 and "30%" in msgs[0]
    cultivation.cultivate(kicker, content, world, "旋風腿", WIN)
    assert "旋風腿" not in kicker.player.art_mastery  # 升品之後歸零


def test_the_level_does_not_change_on_a_quality_rise(kicker, content, world):
    kicker.player.art_levels["旋風腿"] = 7
    cultivation.cultivate(kicker, content, world, "旋風腿", WIN)
    assert kicker.player.art_levels["旋風腿"] == 7


@pytest.mark.parametrize(("start", "target", "tries"), [
    ("下品", "中品", 9), ("中品", "上品", 16),
])
def test_losing_every_roll_still_ends_in_a_sure_success_after_the_stated_number_of_tries(
    kicker, content, world, start, target, tries,
):
    """設計 3.5 的保底（下品→中品、中品→上品；上品→絕學沒有保底，見下一個測試）：骰子永遠擲輸（0.999），
    熟練度一次加一、顯示的下一次機率每次加一個級距，加到 100% 的那一次必成。
    釘在 cultivate() 上：熟練度要累加（不是每次都 1）、擲骰要用累積後的機率（不是永遠第一次的機率）。"""
    first, step = content.config.cultivate_odds[target]
    p = kicker.player
    p.art_quality["旋風腿"], p.stamina = start, 10 * tries
    shown = []
    for failure in range(1, tries):  # 前 tries - 1 次都輸
        msgs = cultivation.cultivate(kicker, content, world, "旋風腿", LOSE)
        assert "還差一點火候" in msgs[0] and p.art_mastery["旋風腿"] == failure
        assert p.art_quality["旋風腿"] == start
        shown.append(int(re.search(r"下一次約 (\d+)%", msgs[0]).group(1)))
    assert shown == [min(100, first + step * n) for n in range(1, tries)] and shown[-1] == 100
    msgs = cultivation.cultivate(kicker, content, world, "旋風腿", LOSE)  # 同一個輸的骰子：這一次機率已經是 100%
    assert f"從{start}晉為{target}" in msgs[0]
    assert p.art_quality["旋風腿"] == target and "旋風腿" not in p.art_mastery and p.stamina == 0


def test_losing_every_roll_never_promotes_a_peerless_art_and_the_shown_chance_stops_at_half(kicker, content, world):
    """企劃者 2026-10-05：上品→絕學沒有保底。擲 60 次都輸：一次都不晉品、每次都花體力、熟練度照加，
    顯示的下一次機率 7、10、13……爬到 50% 就停住（沒有第 33 次必成）。"""
    p = kicker.player
    p.art_quality["旋風腿"], p.stamina = "上品", 10 * 60
    shown = []
    for failure in range(1, 61):
        msgs = cultivation.cultivate(kicker, content, world, "旋風腿", LOSE)
        assert "還差一點火候" in msgs[0] and p.art_mastery["旋風腿"] == failure
        shown.append(int(re.search(r"下一次約 (\d+)%", msgs[0]).group(1)))
    assert shown == [min(50, 4 + 3 * n) for n in range(1, 61)] and shown[:3] == [7, 10, 13]
    assert shown[-1] == 50 and max(shown) == 50
    assert p.art_quality["旋風腿"] == "上品" and p.naming is None and p.stamina == 0


def test_a_peerless_try_wins_only_under_the_capped_chance(kicker, content, world):
    p = kicker.player
    p.art_quality["旋風腿"], p.art_mastery["旋風腿"] = "上品", 100
    assert "晉為絕學" in cultivation.cultivate(kicker, content, world, "旋風腿", Fixed(0.49))[0]  # 49 < 50
    p.art_quality["旋風腿"], p.art_mastery["旋風腿"], p.naming = "上品", 100, None
    assert "還差一點火候" in cultivation.cultivate(kicker, content, world, "旋風腿", Fixed(0.50))[0]  # 50 不小於 50


# ── 破境丹（企劃者 2026-10-05）：玩家自己勾了才服；衝絕學那一次多 15%，成不成都用掉 ──────────────────

PILL = "你服下一枚【破境丹】，心神一片澄明。"
NOT_TAKEN_NO_PILL = "你身上已經沒有破境丹了，這一回沒服。"
NOT_TAKEN_WRONG_STEP = "破境丹只在衝擊絕學時用得上，這一回沒服。"


def test_the_boost_needs_the_box_ticked_the_peerless_step_and_a_pill_in_hand(kicker, content):
    p = kicker.player
    assert cultivation.boost_for(kicker, content, "絕學", True) == 0  # 手上沒有丹
    p.legend_items = 1
    assert cultivation.boost_for(kicker, content, "絕學") == 0  # 沒勾（預設不服）
    assert cultivation.boost_for(kicker, content, "絕學", False) == 0
    assert cultivation.boost_for(kicker, content, "絕學", True) == 15
    assert cultivation.boost_for(kicker, content, "上品", True) == 0 and cultivation.boost_for(kicker, content, "中品", True) == 0
    content.config.legend_item_bonus = 20  # 數字從設定來
    assert cultivation.boost_for(kicker, content, "絕學", True) == 20


def test_an_unticked_try_keeps_the_pill_and_rolls_the_plain_chance(kicker, content, world):
    """擲 0.10：基本 4% 輸、加成後 19% 贏。沒勾：同一個骰子輸，丹原封不動，也不說服了什麼。"""
    p = kicker.player
    p.art_quality["旋風腿"], p.legend_items = "上品", 2
    msgs = cultivation.cultivate(kicker, content, world, "旋風腿", Fixed(0.10))
    assert PILL not in msgs and "還差一點火候" in msgs[0] and "沒服" not in msgs[0]
    assert p.legend_items == 2 and p.art_quality["旋風腿"] == "上品" and p.stamina == 140
    assert "下一次約 7% 的機會晉為絕學，服下破境丹可再 +15%" in msgs[0]  # 下一次的機率是不服丹的機率，另提醒還握著丹


def test_a_ticked_try_uses_exactly_one_pill_and_adds_the_bonus_to_the_roll(kicker, content, world):
    p = kicker.player
    p.art_quality["旋風腿"], p.legend_items = "上品", 2
    msgs = cultivation.cultivate(kicker, content, world, "旋風腿", Fixed(0.10), use_legend=True)  # 同一個骰子：這次贏
    assert msgs[0] == PILL and "從上品晉為絕學" in msgs[1]
    assert p.art_quality["旋風腿"] == "絕學" and p.legend_items == 1 and p.stamina == 140


def test_a_ticked_try_that_loses_still_uses_the_pill_and_shows_the_plain_next_chance(kicker, content, world):
    p = kicker.player
    p.art_quality["旋風腿"], p.legend_items = "上品", 2
    msgs = cultivation.cultivate(kicker, content, world, "旋風腿", LOSE, use_legend=True)
    assert msgs[0] == PILL and p.legend_items == 1 and p.art_mastery["旋風腿"] == 1
    assert "下一次約 7% 的機會晉為絕學，服下破境丹可再 +15%" in msgs[1]  # 不含丹的 7%，還握著一枚所以提醒
    msgs = cultivation.cultivate(kicker, content, world, "旋風腿", LOSE, use_legend=True)
    assert msgs[0] == PILL and p.legend_items == 0
    assert "下一次約 10% 的機會晉為絕學）" in msgs[1] and "服下" not in msgs[1]  # 沒有丹了：不再提醒
    msgs = cultivation.cultivate(kicker, content, world, "旋風腿", LOSE)
    assert PILL not in msgs and "下一次約 13%" in msgs[0]


def test_a_stale_page_ticking_a_pill_you_no_longer_hold_rolls_the_plain_chance_and_says_so(kicker, content, world):
    p = kicker.player
    p.art_quality["旋風腿"], p.legend_items = "上品", 0
    msgs = cultivation.cultivate(kicker, content, world, "旋風腿", Fixed(0.10), use_legend=True)  # 沒有丹：19% 的加成不算
    assert msgs[0] == NOT_TAKEN_NO_PILL and "還差一點火候" in msgs[1] and p.art_quality["旋風腿"] == "上品"
    assert p.legend_items == 0 and p.stamina == 140 and p.art_mastery["旋風腿"] == 1  # 照常修練、照常花體力


@pytest.mark.parametrize("start", ["下品", "中品"])
@pytest.mark.parametrize("roll", [WIN, LOSE])
def test_a_ticked_pill_is_kept_on_the_lower_two_steps(kicker, content, world, start, roll):
    p = kicker.player
    p.art_quality["旋風腿"], p.legend_items = start, 3
    msgs = cultivation.cultivate(kicker, content, world, "旋風腿", roll, use_legend=True)
    assert PILL not in msgs and msgs[0] == NOT_TAKEN_WRONG_STEP and p.legend_items == 3
    assert p.stamina == 140  # 這一回照常修練


def test_the_notes_use_the_configured_pill_name(kicker, content, world):
    content.config.legend_item_name = "天機丹"
    p = kicker.player
    p.art_quality["旋風腿"], p.legend_items = "上品", 1
    assert cultivation.cultivate(kicker, content, world, "旋風腿", LOSE, use_legend=True)[0] == "你服下一枚【天機丹】，心神一片澄明。"
    assert cultivation.cultivate(kicker, content, world, "旋風腿", LOSE, use_legend=True)[0] == "你身上已經沒有天機丹了，這一回沒服。"


@pytest.mark.parametrize("break_it", [
    lambda p: p.insights.clear(),                         # 意境熔掉了
    lambda p: setattr(p, "stamina", 5),                   # 體力不足
    lambda p: setattr(p, "naming", "別的絕學"),             # 還有一門絕學等著取名
    lambda p: setattr(p, "arts", []),                     # 沒有這門武學
])
def test_a_refused_try_with_the_box_ticked_keeps_the_pill(kicker, content, world, break_it):
    p = kicker.player
    p.art_quality["旋風腿"], p.legend_items = "上品", 1
    break_it(p)
    stamina = p.stamina
    assert cultivation.cultivate_problem(kicker, content, world, "旋風腿") is not None
    msgs = cultivation.cultivate(kicker, content, world, "旋風腿", WIN, use_legend=True)
    assert len(msgs) == 1 and p.legend_items == 1 and p.stamina == stamina and p.art_quality["旋風腿"] == "上品"


def test_a_save_from_before_the_pill_loads_with_none(state):
    from tianxia.state import PlayerState

    data = state.player.model_dump()
    data.pop("legend_items")
    assert PlayerState.model_validate(data).legend_items == 0 and state.player.legend_items == 0


def test_the_stated_chances_for_the_first_step_climb_thirty_to_a_hundred(kicker, content, world):
    shown = [
        int(re.search(r"下一次約 (\d+)%", cultivation.cultivate(kicker, content, world, "旋風腿", LOSE)[0]).group(1))
        for _ in range(8)
    ]
    assert shown == [30, 40, 50, 60, 70, 80, 90, 100] and kicker.player.art_mastery["旋風腿"] == 8


def test_a_worn_art_can_be_cultivated_too(state, content, world):
    """修練不看功法在庫裡還是配在身上（兩處都算擁有）；配在身上的成也不動。"""
    art = kicker_art()
    world.claim_skill_name(art)
    state.player.member.wugong_id, state.player.member.wugong_level = "旋風腿", 4
    equip(state)
    state.player.arts = []
    cultivation.cultivate(state, content, world, "旋風腿", WIN)
    assert state.player.art_quality["旋風腿"] == "中品" and state.player.member.wugong_level == 4


@pytest.mark.parametrize(("change", "reason"), [
    (lambda s: s.player.insights.clear(), "已經把它熔掉了"),
    (lambda s: setattr(s.player, "stamina", 5), "體力不足"),
    (lambda s: s.player.art_quality.update({"旋風腿": "絕學"}), "修無可修"),
    (lambda s: s.player.arts.clear(), "你沒有這門武學"),
])
def test_cultivation_explains_why_it_is_refused(kicker, content, world, change, reason):
    change(kicker)
    assert reason in cultivation.cultivate_problem(kicker, content, world, "旋風腿")


def test_a_basic_art_cannot_be_cultivated(state, content, world):
    state.player.member.wugong_id = "basic_fist"
    assert "沒有融過意境" in cultivation.cultivate_problem(state, content, world, "basic_fist")


def test_a_refused_cultivation_costs_and_changes_nothing(kicker, content, world):
    kicker.player.stamina = 5
    assert "體力不足" in cultivation.cultivate(kicker, content, world, "旋風腿", WIN)[0]
    assert kicker.player.stamina == 5 and kicker.player.art_quality == {} and kicker.player.art_mastery == {}


def test_a_melted_insight_says_so_by_name_and_does_not_cultivate(kicker, content, world):
    """審查重點 2：用來融的意境熔掉了：不崩潰、不悄悄修練（體力不扣、品質與熟練度不動），照實說出是哪個意境。"""
    kicker.player.insights = []
    msgs = cultivation.cultivate(kicker, content, world, "旋風腿", WIN)
    assert msgs == ["修練要用「風」，你已經把它熔掉了。"]
    assert kicker.player.stamina == 150 and kicker.player.art_quality == {} and kicker.player.art_mastery == {}


def test_a_melted_insight_nobody_can_look_up_still_does_not_crash(state, content, world):
    art = kicker_art().model_copy(update={"id": "怪腿", "name": "怪腿", "insight": "已經不存在的意境"})
    world.claim_skill_name(art)
    equip(state, "怪腿", "feng")
    msgs = cultivation.cultivate(state, content, world, "怪腿", WIN)
    assert "已經不存在的意境" in msgs[0] and "熔掉" in msgs[0] and state.player.stamina == 150


def test_the_first_to_reach_peerless_names_it_for_everyone(kicker, content, world):
    kicker.player.art_quality["旋風腿"] = "上品"
    msgs = cultivation.cultivate(kicker, content, world, "旋風腿", WIN)
    assert kicker.player.naming == "旋風腿" and any("取一個正式的名字" in m for m in msgs)
    cultivation.name_mastered(kicker, content, world, "風神腿")
    assert world.get_skill("旋風腿").name == "風神腿" and kicker.player.naming is None
    assert any("風神腿" in r.text for r in kicker.world.chronicle)


def test_the_chronicle_line_names_the_old_name_and_the_new_one(kicker, content, world):
    """F14：每一件各寫一行（換季那一行是另外一份總結，T10）。"""
    kicker.player.art_quality["旋風腿"] = "上品"
    cultivation.cultivate(kicker, content, world, "旋風腿", WIN)
    cultivation.name_mastered(kicker, content, world, "風神腿")
    assert [r.text for r in kicker.world.chronicle] == ["沈浪把【旋風腿】練成絕學，為之定名【風神腿】。"]


def test_the_second_to_reach_peerless_does_not_name_it(kicker, content, world):
    world.claim_master("旋風腿", "甲")
    kicker.player.art_quality["旋風腿"] = "上品"
    msgs = cultivation.cultivate(kicker, content, world, "旋風腿", WIN)
    assert kicker.player.naming is None and any("甲" in m for m in msgs)


def test_two_players_reaching_peerless_together_only_the_first_names_it(kicker, content, world):
    """兩個人這一刻都把同一門武學練成絕學：claim_master 是原子的，只有先登記的拿到取名權；
    後到的沒有 naming，也取不了名（沒有等著他取名的武學），全服的名字只被改一次。"""
    kicker.player.art_quality["旋風腿"] = "上品"
    other = equip(new_game_state(content, "乙"))
    other.player.art_quality["旋風腿"] = "上品"
    cultivation.cultivate(kicker, content, world, "旋風腿", WIN)
    msgs = cultivation.cultivate(other, content, world, "旋風腿", WIN)
    assert kicker.player.naming == "旋風腿" and other.player.naming is None
    assert any("沈浪" in m for m in msgs) and world.master_of("旋風腿") == "沈浪"
    assert cultivation.name_mastered(other, content, world, "裂地腿") == ["（沒有等著你取名的武學。）"]
    assert world.get_skill("旋風腿").name == "旋風腿"  # 後到的沒改成
    cultivation.name_mastered(kicker, content, world, "風神腿")
    assert world.get_skill("旋風腿").name == "風神腿"
    assert cultivation.name_mastered(kicker, content, world, "另一個名") == ["（沒有等著你取名的武學。）"]  # 一門只取一次


def test_the_last_step_to_peerless_waits_until_the_pending_naming_is_done(kicker, content, world):
    """取名的權利一人一次只留一門（PlayerState.naming）：還有一門練成了絕學沒定名時，不能再衝第二門的絕學——
    不然第二門成了、第一門的取名權被蓋掉，那門就永遠沒有人替它定名。別的品質照樣能修。"""
    world.claim_skill_name(generate_from_name("裂石拳", "武學", "裂石拳"))
    kicker.player.naming = "裂石拳"
    kicker.player.art_quality["旋風腿"] = "上品"
    assert "【裂石拳】還沒定名" in cultivation.cultivate(kicker, content, world, "旋風腿", WIN)[0]
    assert kicker.player.stamina == 150 and kicker.player.art_quality["旋風腿"] == "上品" and kicker.player.naming == "裂石拳"
    kicker.player.art_quality["旋風腿"] = "中品"
    assert cultivation.cultivate_problem(kicker, content, world, "旋風腿") is None


def test_a_bad_or_taken_name_is_refused(kicker, content, world):
    kicker.player.naming = "旋風腿"
    world.claim_master("旋風腿", kicker.player.name)
    assert "長度" in cultivation.name_mastered(kicker, content, world, "風")[0]
    world.claim_skill_name(generate_from_name("裂石拳", "武學", "裂石拳"))
    assert "有人用了" in cultivation.name_mastered(kicker, content, world, "裂石拳")[0]
    assert kicker.player.naming == "旋風腿"


def test_a_name_used_by_an_alias_or_an_insight_is_refused(kicker, content, world):
    """全服不能重名：別門武學改過的新名字、合併出來的意境名字，跟內容裡的意境名字（過濾那一關）一樣都不行。"""
    kicker.player.naming = "旋風腿"
    world.claim_skill_name(generate_from_name("裂石拳", "武學", "裂石拳"))
    assert world.rename_skill("裂石拳", "碎石拳")
    world.claim_insight_recipe("合|feng+huo", Insight(id="燎原", name="燎原", attribute="陽", creator="乙"))
    assert "有人用了" in cultivation.name_mastered(kicker, content, world, "碎石拳")[0]
    assert "有人用了" in cultivation.name_mastered(kicker, content, world, "燎原")[0]
    assert "意境同名" in cultivation.name_mastered(kicker, content, world, "浩然")[0]  # 內容裡的意境
    assert kicker.player.naming == "旋風腿" and world.get_skill("旋風腿").name == "旋風腿"


def test_naming_it_with_the_name_it_already_has_keeps_the_name(kicker, content, world):
    """第一個練成的人覺得模型取的名字就很好：這算定名（取名權用掉、江湖史記一筆），名字不變——
    不能說成「已經有人用了」，用的人就是這門武學自己。"""
    kicker.player.naming = "旋風腿"
    world.claim_master("旋風腿", kicker.player.name)
    msgs = cultivation.name_mastered(kicker, content, world, "旋風腿")
    assert msgs == ["從今以後，江湖上這門武學就叫【旋風腿】。"] and kicker.player.naming is None
    assert world.get_skill("旋風腿").name == "旋風腿" and not world.is_skill_name_taken("風神腿")
    assert [r.text for r in kicker.world.chronicle] == ["沈浪把【旋風腿】練成絕學，為之定名【旋風腿】。"]
    assert cultivation.name_mastered(kicker, content, world, "風神腿") == ["（沒有等著你取名的武學。）"]  # 取名權用掉了


def test_a_name_is_cleaned_before_it_is_checked(kicker, content, world):
    kicker.player.naming = "旋風腿"
    cultivation.name_mastered(kicker, content, world, "《風神腿》")
    assert world.get_skill("旋風腿").name == "風神腿"


def test_naming_an_art_that_has_gone_missing_says_so_and_changes_nothing(state, content, world):
    state.player.naming = "不存在的功法"
    assert "找不到" in cultivation.name_mastered(state, content, world, "風神腿")[0]
    assert state.player.naming == "不存在的功法" and state.world.chronicle == []


def test_after_a_rename_the_name_shows_everywhere_and_the_id_still_keys(state, content, world):
    """Task 1 的提醒：改名之後 id 跟顯示的名字不一樣。顯示的地方都要寫新名字（功法庫、功法卡、已經有了的訊息），
    認東西的地方都要照 id（擁有、品質、熟練度、登記）。"""
    world.claim_recipe(fusion.fuse_key("basic_fist", "feng"), kicker_art())  # 這個配方的功法就是旋風腿
    equip(state)
    state.player.member.wugong_id = "basic_fist"
    state.player.stats["xinde"] = 50
    state.player.art_quality["旋風腿"] = "上品"
    cultivation.cultivate(state, content, world, "旋風腿", WIN)
    cultivation.name_mastered(state, content, world, "風神腿")
    # 顯示：新名字
    assert team.resolve_art("旋風腿", content, world).name == "風神腿"
    assert team.player_art(state, content, world, "旋風腿").name == "風神腿"
    (row,) = [r for r in skillview.art_rows(state, content, world) if r["id"] == "旋風腿"]
    assert (row["name"], row["quality"], row["attribute"], row["level"]) == ("風神腿", "絕學", "快", 1)
    assert "【風神腿】" in fusion.fuse_problem(state, content, world, "basic_fist", "feng")  # 「已經有了」認 id、說新名字
    # 認東西：還是 id
    assert "旋風腿" in library.owned_arts(state) and state.player.art_quality == {"旋風腿": "絕學"}
    assert world.get_skill("旋風腿") is not None and world.get_skill("風神腿") is None
    assert "修無可修" in cultivation.cultivate_problem(state, content, world, "旋風腿")


def test_the_new_name_cannot_be_taken_by_anyone_else_afterwards(kicker, content, world):
    kicker.player.naming = "旋風腿"
    cultivation.name_mastered(kicker, content, world, "風神腿")
    assert world.is_skill_name_taken("風神腿")
    assert not world.claim_skill_name(generate_from_name("風神腿", "武學", "風神腿"))


def test_the_upgrade_line_gets_the_new_thing_shine_and_a_failed_try_does_not(kicker, content, world):
    won = cultivation.cultivate(kicker, content, world, "旋風腿", WIN)[0]
    assert won.startswith("【旋風腿】修練有成，從下品晉為中品") and journal._line_class(won) == "tx-line tx-new"
    lost = cultivation.cultivate(kicker, content, world, "旋風腿", LOSE)[0]
    assert journal._line_class(lost) == "tx-line"


# ── 引擎：修練與定名寫不寫江湖紀錄（F12：真的有事發生才寫）──────────────────


@pytest.fixture
def adept(game):
    """一個配好了旋風腿（庫裡）、意境與體力都夠的角色。擲骰預設全贏，要輸的測試自己換 game.rng。"""
    game.world.claim_skill_name(kicker_art())
    equip(game.state)
    game.rng = WIN
    return game


def test_cultivating_writes_one_journal_entry_with_the_xinde_untouched(adept):
    msgs = adept.cultivate("旋風腿")
    entry = adept.state.journal[0]
    assert "中品" in msgs[0] and entry.title == "修練" and entry.tag == msgs[0] and entry.changes == ["體力 -10"]
    assert adept.state.player.art_quality["旋風腿"] == "中品"


def test_a_failed_roll_is_something_that_happened_and_is_written(adept):
    adept.rng = LOSE
    msgs = adept.cultivate("旋風腿")
    assert "還差一點火候" in msgs[0] and adept.state.journal[0].tag == msgs[0]
    assert adept.state.journal[0].changes == ["體力 -10"]  # 輸了也花了體力，跟別的行動一樣寫在紀錄上


def test_a_ticked_pill_shows_in_the_journal_changes_next_to_the_stamina(adept):
    p = adept.state.player
    p.art_quality["旋風腿"], p.legend_items = "上品", 1
    adept.rng = LOSE
    msgs = adept.cultivate("旋風腿", use_legend=True)
    entry = adept.state.journal[0]
    assert msgs[0] == PILL and "還差一點火候" in msgs[1] and p.legend_items == 0
    assert entry.title == "修練" and entry.changes == ["體力 -10", "破境丹 -1"]
    assert entry.tag == msgs[1]  # 結果標記是擲骰的結果，不是服丹那一句


def test_a_success_with_the_pill_is_written_with_the_pill_too(adept):
    p = adept.state.player
    p.art_quality["旋風腿"], p.legend_items = "上品", 1
    msgs = adept.cultivate("旋風腿", use_legend=True)  # 擲骰預設全贏
    entry = adept.state.journal[0]
    assert "從上品晉為絕學" in msgs[1] and entry.tag == msgs[1] and entry.changes == ["體力 -10", "破境丹 -1"]


def test_an_unticked_try_writes_no_pill_change_and_keeps_the_pill(adept):
    p = adept.state.player
    p.art_quality["旋風腿"], p.legend_items = "上品", 2
    adept.rng = LOSE
    adept.cultivate("旋風腿")
    assert adept.state.journal[0].changes == ["體力 -10"] and p.legend_items == 2


def test_no_pill_is_written_when_none_was_taken(adept):
    adept.state.player.legend_items = 0
    adept.state.player.art_quality["旋風腿"] = "上品"
    msgs = adept.cultivate("旋風腿", use_legend=True)  # 頁面過期：丹已經沒有了
    assert msgs[0] == NOT_TAKEN_NO_PILL and adept.state.journal[0].changes == ["體力 -10"]
    assert adept.state.journal[0].tag == msgs[1] and "修練有成" in msgs[1]  # 標記仍是擲骰的結果，不是「沒服」那一句
    adept.state.player.legend_items, adept.state.player.art_quality["旋風腿"] = 2, "下品"
    adept.state.player.naming = None
    adept.cultivate("旋風腿", use_legend=True)  # 下品→中品那一步：丹留著、紀錄也不寫丹
    assert adept.state.player.legend_items == 2 and adept.state.journal[0].changes == ["體力 -20"]


def test_a_refused_try_with_the_box_ticked_keeps_the_pill_and_writes_no_entry(adept):
    p = adept.state.player
    p.art_quality["旋風腿"], p.legend_items, p.stamina = "上品", 1, 5
    before = list(adept.state.journal)
    assert "體力不足" in adept.cultivate("旋風腿", use_legend=True)[0]
    assert p.legend_items == 1 and adept.state.journal == before


def test_the_stamina_of_consecutive_rolls_adds_up_in_one_merged_entry(adept):
    adept.rng = LOSE
    adept.cultivate("旋風腿")
    adept.cultivate("旋風腿")
    entries = [e for e in adept.state.journal if e.title == "修練"]
    assert len(entries) == 1 and entries[0].changes == ["體力 -20"] and adept.state.player.stamina == 130


def test_the_stamina_change_is_not_written_for_a_naming(adept):
    adept.state.player.naming = "旋風腿"
    adept.name_mastered("風神腿")
    assert adept.state.journal[0].changes == [] and adept.state.player.stamina == 150


@pytest.mark.parametrize("break_it", [
    lambda p: p.insights.clear(),                      # 意境熔掉了
    lambda p: setattr(p, "arts", []),                  # 沒有這門武學
    lambda p: setattr(p, "stamina", 5),                # 體力不足
    lambda p: p.art_quality.update({"旋風腿": "絕學"}),  # 已經是絕學
])
def test_a_refused_cultivation_writes_no_journal_entry(adept, break_it):
    break_it(adept.state.player)
    before = list(adept.state.journal)
    msgs = adept.cultivate("旋風腿")
    assert len(msgs) == 1 and adept.state.journal == before
    assert any(msgs[0] in line for line in adept.state.log)  # 話還是照樣留在 log


def test_melting_the_art_waiting_for_its_name_is_refused_without_an_entry(adept):
    """練成絕學、還沒定名的那門不能熔：熔了，讀檔清理會把取名權連同已登記的第一人一起丟掉。"""
    adept.state.player.art_quality["旋風腿"] = "上品"
    adept.cultivate("旋風腿")
    assert adept.state.player.naming == "旋風腿"
    before = list(adept.state.journal)
    msgs = adept.melt_art("旋風腿")
    assert "先替它定名" in msgs[0] and "旋風腿" in adept.state.player.arts and adept.state.journal == before
    adept.name_mastered("風神腿")
    assert "熔成了心得" in adept.melt_art("旋風腿")[0] and adept.state.player.arts == []  # 定了名就能熔


def test_a_basic_art_is_refused_without_a_journal_entry(adept):
    adept.state.player.member.wugong_id = "basic_fist"
    before = list(adept.state.journal)
    assert "沒有融過意境" in adept.cultivate("basic_fist")[0] and adept.state.journal == before


def test_naming_writes_the_chronicle_the_journal_and_saves_the_season(adept):
    adept.state.player.art_quality["旋風腿"] = "上品"
    adept.cultivate("旋風腿")
    assert adept.state.player.naming == "旋風腿"
    msgs = adept.name_mastered("風神腿")
    assert "風神腿" in msgs[0] and adept.state.journal[0].tag == msgs[0]
    assert [r.text for r in adept.world.get_season().chronicle][-1] == "沈浪把【旋風腿】練成絕學，為之定名【風神腿】。"  # 存回共用賽季了


def test_a_refused_naming_writes_no_journal_entry(adept):
    before = list(adept.state.journal)
    assert adept.name_mastered("風神腿") == ["（沒有等著你取名的武學。）"]  # 沒有等著取名的武學
    adept.state.player.naming = "旋風腿"
    assert "長度" in adept.name_mastered("風")[0]                              # 名字不合格
    adept.world.claim_skill_name(generate_from_name("裂石拳", "武學", "裂石拳"))
    assert "有人用了" in adept.name_mastered("裂石拳")[0]                       # 名字被用掉了
    assert adept.state.journal == before and adept.state.player.naming == "旋風腿"


def test_cultivating_and_naming_wait_while_the_season_is_preparing(adept):
    from unittest import mock

    with mock.patch.object(adept.world, "season_phase", return_value="preparing"):
        assert "籌備中" in adept.cultivate("旋風腿")[0] and "籌備中" in adept.name_mastered("風神腿")[0]
    assert adept.state.player.stamina == 150 and adept.state.player.art_quality == {}
