"""氣血對戰力的影響與內傷（第五層：把「氣血門戶名冊」spec §1.1／§1.3 沒實作的那一半補上）。

改之前：遭遇戰完全不扣氣血 → 內傷不存在 → 療傷只是花錢跳過兩小時的等待 → 等級的氣血上限
毫無意義（實測整季療傷 0 次、季末滿血、等級只到第 2~3 級）。
"""
import random

import pytest

from tianxia import encounter, team


class Dummy:
    """encounter.HasMartialArts 的最小形狀。"""

    def __init__(self, wugong_id=None, wugong_level=1, neigong_id=None, neigong_level=1):
        self.wugong_id, self.wugong_level = wugong_id, wugong_level
        self.neigong_id, self.neigong_level = neigong_id, neigong_level


@pytest.fixture
def art(content, world):
    from tianxia.martial_arts import historical_art

    return historical_art("fist", "長拳", "武學", "剛")


# ── 氣血狀態係數（spec §1.1：0.5 + 0.5 × 剩餘／上限）────────


@pytest.mark.parametrize(("now", "cap", "expected"), [(100, 100, 1.0), (50, 100, 0.75), (0, 100, 0.5)])
def test_condition_runs_from_one_down_to_a_half(now, cap, expected):
    assert encounter.condition_of(now, cap) == pytest.approx(expected)


def test_condition_is_safe_with_a_zero_cap():
    assert encounter.condition_of(0, 0) == 1.0


def test_a_wounded_fighter_hits_weaker(art):
    full = encounter.member_power(Dummy("fist", 10), {"fist": art})
    half = encounter.member_power(Dummy("fist", 10), {"fist": art}, None, 0.75)
    assert half == pytest.approx(full * 0.75)


def test_team_power_without_conditions_assumes_everyone_is_fresh(art):
    members = [Dummy("fist", 10), Dummy("fist", 10)]
    assert encounter.team_power(members, {"fist": art}) == pytest.approx(
        encounter.team_power(members, {"fist": art}, None, [1.0, 1.0])
    )


# ── 內傷 ──────────────────────────────────────────────────


def test_injury_lowers_the_ceiling_that_regeneration_can_reach(state, content):
    member = state.player.member
    cap = team.neili_cap(content, member.level)
    assert team.neili_ceiling(content, member) == cap
    member.injury = 100.0
    assert team.neili_ceiling(content, member) == cap - 100


def test_the_ceiling_never_drops_below_a_tenth_of_the_cap(state, content):
    """氣血設計 §1.3：再低也照樣能出戰。"""
    member = state.player.member
    member.injury = 10_000.0
    cap = team.neili_cap(content, member.level)
    assert team.neili_ceiling(content, member) == pytest.approx(cap * team.MIN_CEILING_RATIO)


def test_regeneration_stops_at_the_ceiling_not_the_cap(state, content):
    member = state.player.member
    member.injury = 100.0
    member.neili = 10.0
    team.regen_neili(content, member, 1.0)  # 一次回滿上限的量
    now, cap = team.member_neili(content, member)
    assert member.neili is None  # 回到上蓋就算「滿」
    assert now == pytest.approx(cap - 100)


def test_healing_is_priced_by_injury_not_by_missing_blood(state, content):
    member = state.player.member
    member.neili = 1.0  # 全是輕傷：自己會回，不該收錢
    assert team.heal_cost(content, member) == 0
    member.injury = 40.0
    assert team.heal_cost(content, member) == 20  # 預設每 2 點內傷 1 兩


def test_healing_clears_the_injury(state, content):
    member = state.player.member
    member.injury, member.neili = 40.0, 10.0
    state.player.stats["silver"] = 999
    msgs = team.heal(state, content, member)
    assert "內傷 -40" in msgs[0]
    assert member.injury == 0.0 and member.neili is None


def test_practising_now_accrues_real_injury(state, content, world):
    """練功受傷的訊息一直寫著「累積內傷，需要療傷」，但改之前它只是扣氣血、兩小時就自己回來了。"""
    state.player.member.wugong_id = "fist"
    state.player.stats["xinde"] = 1  # 練成要花心得：第 1 成升第 2 成花 1 點
    always_hurt = random.Random()
    always_hurt.random = lambda: 0.0  # type: ignore[method-assign]
    team.practice(state, content, world, "武學", always_hurt)
    assert state.player.member.injury == content.config.practice_injury_amount


# ── 一場打完的代價 ────────────────────────────────────────


def test_a_fight_costs_blood_and_leaves_some_of_it_as_injury(state, content, world):
    msgs = team.take_encounter_toll(state, content, world, "落敗")
    member = state.player.member
    cap = team.neili_cap(content, member.level)
    expected_loss = cap * content.config.encounter_neili_loss["落敗"]
    assert member.injury == pytest.approx(expected_loss * content.config.injury_share)
    assert msgs[0] == f"氣血 -{expected_loss:.0f}" and msgs[1].startswith("內傷 +")


def test_a_fight_at_zero_blood_writes_no_zero_blood_line_but_still_the_injury(state, content, world):
    """一滴氣血都沒得扣（本來就見底）時不寫「氣血 -0」；內傷是照上限算的，照樣累積、照樣寫。"""
    state.player.member.neili = 0.0
    msgs = team.take_encounter_toll(state, content, world, "落敗")
    assert msgs and msgs[0].startswith("內傷 +") and not any(m.startswith("氣血") for m in msgs)
    assert state.player.member.injury > 0


def test_winning_big_costs_much_less_than_losing(state, content, world):
    from copy import deepcopy

    win_state = deepcopy(state)
    team.take_encounter_toll(win_state, content, world, "大勝")
    lose_state = deepcopy(state)
    team.take_encounter_toll(lose_state, content, world, "落敗")
    assert win_state.player.member.injury < lose_state.player.member.injury


def test_a_wild_fight_costs_half_the_blood_and_half_the_injury(state, content, world):
    """探索時撞上的野怪只扣遊歷的一半（wild_neili_loss_factor），內傷照同一個比例（探索三選一設計 4.2）。"""
    from copy import deepcopy

    trained, ambushed = deepcopy(state), deepcopy(state)
    team.take_encounter_toll(trained, content, world, "落敗")
    msgs = team.take_encounter_toll(ambushed, content, world, "落敗", wild=True)
    cap = team.neili_cap(content, state.player.member.level)
    half = cap * content.config.encounter_neili_loss["落敗"] * content.config.wild_neili_loss_factor
    assert msgs[0] == f"氣血 -{half:.0f}"
    assert ambushed.player.member.injury == pytest.approx(trained.player.member.injury * 0.5)
    assert ambushed.player.member.injury == pytest.approx(half * content.config.injury_share)


def test_an_unknown_result_costs_nothing(state, content, world):
    assert team.take_encounter_toll(state, content, world, "莫名其妙") == []
    assert state.player.member.injury == 0.0


def test_the_toll_also_hits_the_companions(state, content, world):
    state.player.team.append("mate")
    team.take_encounter_toll(state, content, world, "落敗")
    assert world.get_companion("mate").injury > 0


def test_fighting_while_wounded_really_lowers_the_odds(state, content, world):
    """等級的意義是續戰力：帶傷上陣的威力會掉，所以打不打下一場變成真的有取捨。"""
    from tianxia import rules

    rules.learn_skill(state, content, "fist")
    fresh = encounter.team_power(
        team.team_participants(state, world), team.team_arts(state, content, world), None,
        team.team_conditions(state, content, world),
    )
    state.player.member.neili = 1.0
    wounded = encounter.team_power(
        team.team_participants(state, world), team.team_arts(state, content, world), None,
        team.team_conditions(state, content, world),
    )
    assert wounded < fresh * 0.6  # 幾乎見底時約是滿血的一半
