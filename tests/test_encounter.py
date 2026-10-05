import random

import pytest

from tianxia import encounter
from tianxia.encounter import (
    Boost,
    EncounterResult,
    Mods,
    describe_result,
    member_power,
    resolve_encounter,
    team_power,
)
from tianxia.martial_arts import historical_art
from tianxia.state import Member


class FixedRandom(random.Random):
    """跟 tests/conftest.py 同一個模式：random() 永遠回傳固定值。"""

    def __init__(self, value: float):
        super().__init__(0)
        self.value = value

    def random(self) -> float:
        return self.value


NO_LUCK = FixedRandom(0.5)  # uniform(-15, 15) -> 0，測試邊界時排除隨機干擾


def test_member_power_zero_without_wugong():
    member = Member()
    assert member_power(member, {}) == 0.0


def test_member_power_uses_wugong_level():
    art = historical_art("id", "測試武學", "武學", "陽")
    arts = {"id": art}
    low = Member(wugong_id="id", wugong_level=1)
    high = Member(wugong_id="id", wugong_level=10)
    assert member_power(low, arts) == art.base_power
    assert member_power(high, arts) == art.top_power
    assert member_power(high, arts) > member_power(low, arts)


def test_member_power_gets_neigong_bonus():
    wugong = historical_art("wg", "測試武學", "武學", "陽")
    neigong = historical_art("ng", "測試內功", "內功", "陽")
    arts = {"wg": wugong, "ng": neigong}
    without = Member(wugong_id="wg", wugong_level=10)
    with_neigong = Member(wugong_id="wg", wugong_level=10, neigong_id="ng", neigong_level=10)
    assert member_power(with_neigong, arts) > member_power(without, arts)


def test_member_power_gets_counter_bonus_against_matching_attribute():
    art = historical_art("id", "測試武學", "武學", "陽")  # 陽克陰
    arts = {"id": art}
    member = Member(wugong_id="id", wugong_level=10)
    plain = member_power(member, arts, opponent_attribute=None)
    countered = member_power(member, arts, opponent_attribute="陰")
    no_bonus = member_power(member, arts, opponent_attribute="剛")  # 不相剋
    assert countered > plain
    assert no_bonus == plain


def test_team_power_sums_all_members_and_skips_empty_ones():
    art = historical_art("id", "測試武學", "武學", "陽")
    arts = {"id": art}
    team = [Member(wugong_id="id", wugong_level=10), Member(), Member(wugong_id="id", wugong_level=5)]
    total = team_power(team, arts)
    assert total == member_power(team[0], arts) + member_power(team[2], arts)


def test_a_boost_raises_the_outer_and_inner_arts(state, content, world):
    """臂力乘在武學（外功）上、根骨乘在內功上，factor 乘在整個人上（武學與成長設計 6.1）。"""
    from tianxia import team
    state.player.member.wugong_id = "basic_fist"
    state.player.member.neigong_id = "basic_breath"
    arts = team.team_arts(state, content, world)
    plain = member_power(state.player.member, arts)
    outer = member_power(state.player.member, arts, boost=Boost(outer=0.3))
    inner = member_power(state.player.member, arts, boost=Boost(inner=0.3))
    assert outer == pytest.approx(plain * 1.3)
    assert plain < inner < outer  # 內功只是放大倍數裡的一項，加三成不會讓整體多三成
    assert member_power(state.player.member, arts, boost=Boost(factor=1.2)) == pytest.approx(plain * 1.2)


def test_a_boost_never_turns_power_negative():
    """加成再負（屬性被事件扣到很低），1 + 加成也夾在 0.1 以上。"""
    art = historical_art("id", "測試武學", "武學", "陽")
    member = Member(wugong_id="id", wugong_level=10)
    assert member_power(member, {"id": art}, boost=Boost(outer=-5.0)) == pytest.approx(art.top_power * 0.1)


def test_team_power_refuses_lists_of_different_lengths():
    """氣血係數、加成跟陣容要一樣長：少一個就默默少算一個人（部下就是這樣掉的，計畫二 G1）。"""
    art = historical_art("id", "測試武學", "武學", "陽")
    members = [Member(wugong_id="id", wugong_level=10)] * 3
    with pytest.raises(ValueError):
        team_power(members, {"id": art}, conditions=[1.0, 1.0])
    with pytest.raises(ValueError):
        team_power(members, {"id": art}, boosts=[Boost(), Boost()])


def test_resolve_encounter_tiers_by_margin_without_luck():
    """門檻是難度的比例（大勝 50%、險勝 15%、僵持 -50%），難度 100 時剛好是 50／15／-50。"""
    assert resolve_encounter(our_power=150, difficulty=100, rng=NO_LUCK).tier == "大勝"  # margin 50
    assert resolve_encounter(our_power=115, difficulty=100, rng=NO_LUCK).tier == "險勝"  # margin 15
    assert resolve_encounter(our_power=90, difficulty=100, rng=NO_LUCK).tier == "僵持"  # margin -10
    assert resolve_encounter(our_power=40, difficulty=100, rng=NO_LUCK).tier == "落敗"  # margin -60


def test_the_thresholds_scale_with_how_big_the_fight_is():
    """同樣的「威力多 10 點」，打小角色是大勝、打強敵只是僵持——運氣與門檻都按難度的比例算。"""
    assert resolve_encounter(our_power=20, difficulty=10, rng=NO_LUCK).tier == "大勝"  # 多 10 點，門檻 5
    assert resolve_encounter(our_power=160, difficulty=150, rng=NO_LUCK).tier == "僵持"  # 多 10 點，門檻 22.5


def test_resolve_encounter_luck_can_swing_a_close_match():
    good_luck = FixedRandom(1.0)  # 難度 100 → uniform(-30,30) 取 30，margin 30 >= 險勝門檻 15
    bad_luck = FixedRandom(0.0)  # -30，margin -30 >= 僵持門檻 -50
    assert resolve_encounter(our_power=100, difficulty=100, rng=good_luck).tier == "險勝"
    assert resolve_encounter(our_power=100, difficulty=100, rng=bad_luck).tier == "僵持"


def test_luck_never_vanishes_even_for_a_trivial_fight():
    assert encounter.luck_half(0) == encounter.LUCK_MIN


def test_describe_result_fills_in_names_for_every_tier():
    for tier in ("大勝", "險勝", "僵持", "落敗"):
        result = EncounterResult(tier=tier, margin=0, our_power=0, difficulty=0)
        text = describe_result(result, ours="我方", theirs="黑風寨賊人")
        assert "我方" in text
        assert "黑風寨賊人" in text


def test_a_shift_moves_the_margin_by_the_advantage():
    from tianxia.encounter import advantage_shift, luck_half, resolve_encounter
    assert advantage_shift(100, 15) == pytest.approx(0.15 * 2 * luck_half(100))
    plain = resolve_encounter(100, 100, random.Random(3))
    shifted = resolve_encounter(100, 100, random.Random(3), shift=advantage_shift(100, 15))
    assert shifted.margin == pytest.approx(plain.margin + advantage_shift(100, 15))


def test_a_shift_of_p_points_moves_the_win_line_by_p_points_of_luck():
    """優勢 p 個百分點＝運氣全幅的 p%：運氣是均勻分佈，所以越過門檻的那一段剛好多（少）p 個百分點。難度 100、威力 100：
    運氣 ±30、險勝門檻 +15，運氣要 ≥ +15 才贏（25%）；優勢 +15 平移 9 點，運氣 ≥ +6 就贏（40%）——剛好多 15 個百分點。"""
    from tianxia.encounter import advantage_shift, luck_half

    half = luck_half(100)
    for advantage in (15, -15, 0):
        shift = advantage_shift(100, advantage)
        need = 15 - shift  # 運氣至少要這麼多才是險勝以上
        assert (half - need) / (2 * half) == pytest.approx(0.25 + advantage / 100)


def _result(tier):
    return encounter.EncounterResult(tier=tier, margin=-50.0, our_power=10.0, difficulty=60.0)


def test_a_dodge_turns_only_a_loss_into_a_draw():
    """人物資質設計 14.4：只有落敗會被閃成僵持；別的結果原封不動。"""
    dodged = encounter.dodge(_result("落敗"), 1.0, random.Random(0))
    assert (dodged.tier, dodged.dodged) == ("僵持", True)
    for tier in ("大勝", "險勝", "僵持"):
        assert encounter.dodge(_result(tier), 1.0, random.Random(0)) == _result(tier)
    assert encounter.dodge(_result("落敗"), 0.0, random.Random(0)) == _result("落敗")


def test_dodge_draws_from_the_rng_only_on_a_loss_with_a_chance():
    """Review Focus 3：沒落敗、或機會是 0，不碰亂數——同一個種子的整季模擬不會因為這一條整個變樣。"""
    rng = random.Random(0)
    state = rng.getstate()
    encounter.dodge(_result("險勝"), 1.0, rng)
    encounter.dodge(_result("落敗"), 0.0, rng)
    assert rng.getstate() == state
    encounter.dodge(_result("落敗"), 0.5, rng)
    assert rng.getstate() != state


def test_a_missed_dodge_roll_leaves_the_loss_alone():
    """最終審查 M2：擲到的數大於等於機會就沒閃中，還是落敗、dodged 是 False（剛好等於機會也算沒中，擲到比機會小才中）。"""
    for roll in (0.9, 0.5):
        missed = encounter.dodge(_result("落敗"), 0.5, FixedRandom(roll))
        assert missed == _result("落敗") and not missed.dodged
    hit = encounter.dodge(_result("落敗"), 0.5, FixedRandom(0.49))
    assert (hit.tier, hit.dodged) == ("僵持", True)


# ── 武學的功效（武學與成長設計 13.2、13.4；計畫六 Task 3）：Mods 進單次判定 ──────────────


class _Luck:
    """固定的運氣：uniform 依序吐 values（吐完重複最後一個）；記下被叫了幾次。"""

    def __init__(self, *values):
        self.values, self.calls = list(values), 0

    def uniform(self, low, high):
        self.calls += 1
        return self.values[min(self.calls, len(self.values)) - 1]


def test_no_mods_rolls_exactly_as_before():
    """Review Focus 1：沒有功效（mods 是空的）時，結果與亂數用法跟以前一模一樣。"""
    for seed in range(20):
        a, b = random.Random(seed), random.Random(seed)
        assert resolve_encounter(80, 100, a) == resolve_encounter(80, 100, b, mods=Mods())
        assert a.getstate() == b.getstate()


def _resolve_before_traits(our_power, difficulty, rng, shift=0.0):
    """計畫六之前的單次判定（逐字照抄當時的算法）：拿來證明預設的 Mods 一個浮點數都沒改。"""
    half = encounter.luck_half(difficulty)
    luck = rng.uniform(-half, half)
    margin = our_power - difficulty + luck + shift
    for tier, threshold in encounter.tier_thresholds(difficulty):
        if margin >= threshold:
            return EncounterResult(tier=tier, margin=margin, our_power=our_power, difficulty=difficulty)
    return EncounterResult(tier=encounter.FALLBACK_TIER, margin=margin, our_power=our_power, difficulty=difficulty)


def test_default_mods_are_the_identity_against_the_pre_traits_formula():
    """預設的 Mods 是恆等：換算過程（難度 × (1 − 0)、運氣 × 1、威力 + 0、門檻 − 0）一個浮點數都不改，
    跟計畫六之前的算法逐位相同（不只是兩邊都走新程式的自己跟自己比）。"""
    for difficulty in (0, 5, 37.5, 100, 150, 220):
        for power in (0, 12.3, 80, 160):
            for shift in (0.0, 7.5, -12.0):
                for seed in range(5):
                    old = _resolve_before_traits(power, difficulty, random.Random(seed), shift=shift)
                    assert resolve_encounter(power, difficulty, random.Random(seed), shift=shift) == old
                    assert resolve_encounter(power, difficulty, random.Random(seed), shift=shift, mods=Mods()) == old


def test_each_mod_moves_the_result_the_way_the_design_says():
    """運氣固定為 0：威力 − 難度就是差距。門檻是難度的 50%／15%／−50%。"""
    assert resolve_encounter(95, 100, _Luck(0)).tier == "僵持"
    assert resolve_encounter(95, 100, _Luck(0), mods=Mods(difficulty_cut=0.2)).tier == "險勝"  # 破甲：當作 80
    assert resolve_encounter(140, 100, _Luck(0)).tier == "險勝"
    assert resolve_encounter(140, 100, _Luck(0), mods=Mods(big_win_cut=0.2)).tier == "大勝"  # 先手：大勝門檻 30
    assert resolve_encounter(112, 100, _Luck(0)).tier == "僵持"
    assert resolve_encounter(112, 100, _Luck(0), mods=Mods(power_add=0.05)).tier == "險勝"  # 借力：+5


def test_the_first_hand_lowers_only_the_big_win_line():
    """先手只動大勝的門檻：險勝與僵持的線不變。"""
    assert resolve_encounter(115, 100, _Luck(0), mods=Mods(big_win_cut=0.2)).tier == "險勝"
    assert resolve_encounter(90, 100, _Luck(0), mods=Mods(big_win_cut=0.2)).tier == "僵持"


def test_double_luck_takes_the_better_roll_and_rolls_twice():
    rng = _Luck(-20, 20)
    assert resolve_encounter(100, 100, rng, mods=Mods(double_luck=True)).margin == pytest.approx(20)
    assert rng.calls == 2
    rng = _Luck(20, -20)  # 第二次比較差：還是取好的那一次
    assert resolve_encounter(100, 100, rng, mods=Mods(double_luck=True)).margin == pytest.approx(20)


def test_without_double_luck_the_luck_is_rolled_once():
    rng = _Luck(5)
    resolve_encounter(100, 100, rng, mods=Mods())
    assert rng.calls == 1


def test_luck_scale_narrows_or_widens_the_swing():
    seen = []

    class Spy:
        def uniform(self, low, high):
            seen.append(high)
            return 0.0

    resolve_encounter(80, 100, Spy(), mods=Mods(luck_scale=0.4))
    resolve_encounter(80, 100, Spy(), mods=Mods(luck_scale=1.6))
    assert seen == [pytest.approx(12.0), pytest.approx(48.0)]  # 難度 100 的運氣半幅 30，×0.4、×1.6


def test_a_negative_luck_scale_never_flips_the_swing():
    """運氣的起伏再怎麼縮也不會變成負的（uniform(-h, h) 的 h 不能是負）。"""
    seen = []

    class Spy:
        def uniform(self, low, high):
            seen.append((low, high))
            return 0.0

    resolve_encounter(80, 100, Spy(), mods=Mods(luck_scale=-0.5))
    assert seen == [(0.0, 0.0)]  # -0.0 == 0.0


def test_the_cut_difficulty_also_sets_the_luck_and_the_thresholds():
    """破甲讓對手「當作」弱一點：運氣半幅與門檻都照當作的強度算（難度 100 破甲 20% → 當作 80，運氣半幅 24）。"""
    seen = []

    class Spy:
        def uniform(self, low, high):
            seen.append(high)
            return 0.0

    result = resolve_encounter(100, 100, Spy(), mods=Mods(difficulty_cut=0.2))
    assert seen == [pytest.approx(24.0)]
    assert result.margin == pytest.approx(20.0) and result.difficulty == 100  # 戰報寫的難度還是原來的


def test_the_condition_floor_can_be_raised():
    assert encounter.condition_of(0, 300) == encounter.CONDITION_FLOOR
    assert encounter.condition_of(0, 300, floor=0.75) == pytest.approx(0.75)
    assert encounter.condition_of(300, 300, floor=0.75) == 1.0


def test_a_result_is_not_guarded_unless_someone_says_so():
    assert resolve_encounter(40, 100, _Luck(0)).guarded is False
