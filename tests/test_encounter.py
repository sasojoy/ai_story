import math
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
    """先手只動大勝的門檻：難度 100 時大勝線從 50 降到 30（先手 20%）；險勝線（15）與僵持線（-50）不動。
    每一條線都用剛好在線上與差一點的兩個差距量，兩邊都量到才知道線真的在那裡。"""
    cut = Mods(big_win_cut=0.2)

    def tier(margin, mods=None):
        return resolve_encounter(100 + margin, 100, _Luck(0), mods=mods).tier

    assert (tier(29), tier(30), tier(49), tier(50)) == ("險勝", "險勝", "險勝", "大勝")  # 沒有先手：大勝線在 50
    assert (tier(29, cut), tier(30, cut), tier(49, cut), tier(50, cut)) == ("險勝", "大勝", "大勝", "大勝")  # 先手：降到 30
    for mods in (None, cut):  # 其他兩條線不受影響
        assert (tier(14.9, mods), tier(15, mods)) == ("僵持", "險勝")
        assert (tier(-50.1, mods), tier(-50, mods)) == ("落敗", "僵持")


def test_the_cut_difficulty_decides_the_thresholds_not_the_original():
    """破甲（難度 100 破甲 20% → 當作 80）：門檻照當作的強度算（大勝 40、險勝 12、僵持 -40）。同一個差距，
    照原本的難度（50／15／-50）會判成差一級——這條擋住「只改了差距、門檻還是看原來的難度」。"""
    cut = Mods(difficulty_cut=0.2)
    assert resolve_encounter(94, 100, _Luck(0), mods=cut).tier == "險勝"  # 差距 14：過當作的 12，沒到原本的 15
    assert resolve_encounter(125, 100, _Luck(0), mods=cut).tier == "大勝"  # 差距 45：過當作的 40，沒到原本的 50
    assert resolve_encounter(39, 100, _Luck(0), mods=cut).tier == "落敗"  # 差距 -41：沒到當作的 -40；照原本的 -50 會是僵持


def test_the_first_hands_big_win_cut_is_a_share_of_the_cut_difficulty():
    """Task 4 審查 M5：先手降的是「當作的強度」的比例（跟門檻本身同一個基準）。難度 100、破甲 20%（當作 80）、先手 20%：
    大勝線是 0.5×80 − 0.2×80 ＝ 24（不是照原本的難度 0.5×80 − 0.2×100 ＝ 20）。差距 23 還是險勝、24 才是大勝。"""
    both = Mods(difficulty_cut=0.2, big_win_cut=0.2)
    assert resolve_encounter(80 + 23, 100, _Luck(0), mods=both).tier == "險勝"
    assert resolve_encounter(80 + 24, 100, _Luck(0), mods=both).tier == "大勝"
    assert resolve_encounter(80 + 20, 100, _Luck(0), mods=both).tier == "險勝"  # 照原本的難度算的 20 不是線


def test_borrowed_force_is_a_share_of_the_real_strength_even_when_it_is_cut():
    """借力（威力加上對手強度的 5%）看對手真正的強度：破甲只是讓判定「當作」弱一點，兇猛的對手借得到的力沒有變少
    （S1 的句子：對手越兇猛，越借得上力）。難度 100、破甲 20%：借力 +5（不是照當作的 80 算的 +4）。險勝線在當作的 12：
    威力 87 → 差距 87 + 5 − 80 = 12 剛好過線；照 +4 算是 11，會差一級。"""
    both = Mods(difficulty_cut=0.2, power_add=0.05)
    assert resolve_encounter(87, 100, _Luck(0), mods=both).tier == "險勝"
    assert resolve_encounter(86.9, 100, _Luck(0), mods=both).tier == "僵持"
    assert resolve_encounter(87, 100, _Luck(0), mods=Mods(difficulty_cut=0.2)).tier == "僵持"  # 沒有借力：差距 7


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


def _win_rate(power, difficulty, shift, mods, steps=4000):
    """運氣是均勻分佈：把 0～1 切成 steps 等分、每一份的中點當那一次的亂數，算贏（大勝、險勝）的比例——沒有抽樣的誤差，只有 1/steps 的格子誤差。"""
    wins = 0
    for i in range(steps):
        result = resolve_encounter(power, difficulty, FixedRandom((i + 0.5) / steps), shift=shift, mods=mods)
        wins += result.tier in ("大勝", "險勝")
    return wins / steps


# 每一組都挑成「沒有優勢時剛好五成贏」：運氣要到 0 才過險勝線（難度 100 時線在 15、破甲 20% 後當作 80 線在 12）
LUCK_MOD_CASES = {
    "沒有功效": (115, Mods()),
    "穩（疊到上限）": (115, Mods(luck_scale=0.4)),
    "險（疊到上限）": (115, Mods(luck_scale=1.6)),
    "破甲（疊到上限）": (92, Mods(difficulty_cut=0.2)),
    "穩加破甲": (92, Mods(difficulty_cut=0.2, luck_scale=0.4)),
    "險加破甲": (92, Mods(difficulty_cut=0.2, luck_scale=1.6)),
}


@pytest.mark.parametrize("label", list(LUCK_MOD_CASES))
def test_the_models_push_moves_the_win_chance_by_the_same_points_whatever_traits_are_worn(label):
    """計畫三 §8：模型的優勢最多把勝算推 big_fight_swing 個百分點，不能決定勝負。功效改了運氣的範圍（穩縮小、險放大、
    破甲讓難度當作低），平移若還照沒有功效的範圍算，同一個 ±15 就變成穩 ±37、穩加破甲 ±47、險 ±9.5（Task 3 審查 I1）。
    現在 shift 在 resolve_encounter 裡跟著運氣範圍等比例變，每一組都剛好是 ±15 個百分點。"""
    power, mods = LUCK_MOD_CASES[label]
    base = _win_rate(power, 100, 0.0, mods)
    assert base == pytest.approx(0.5, abs=0.001), label
    for advantage in (15, -15, 7):
        shifted = _win_rate(power, 100, encounter.advantage_shift(100, advantage), mods)
        assert shifted - base == pytest.approx(advantage / 100, abs=0.002), (label, advantage)


def test_a_push_of_zero_changes_nothing_under_any_mods():
    for power, mods in LUCK_MOD_CASES.values():
        assert resolve_encounter(power, 100, FixedRandom(0.3), shift=0.0, mods=mods) == resolve_encounter(
            power, 100, FixedRandom(0.3), mods=mods,
        )


def _double_win_rate(power, difficulty, shift, mods, steps=2000):
    """連環（兩次運氣取好的）贏的機會：贏只看兩次裡較大的那個，所以把第一次的格子編號 i、第二次 j，較大的是 max(i, j)；
    max 剛好是 m 的 (i, j) 有 2m+1 組。逐格丟進 resolve_encounter（兩次都給同一個值），再照組數加權——精確的格子算法，沒有抽樣誤差。"""
    half = encounter.luck_half(difficulty * (1 - mods.difficulty_cut)) * mods.luck_scale
    wins = 0
    for m in range(steps):
        luck = -half + 2 * half * (m + 0.5) / steps
        tier = resolve_encounter(power, difficulty, _Luck(luck, luck), shift=shift, mods=mods).tier
        wins += (2 * m + 1) * (tier in ("大勝", "險勝"))
    return wins / steps**2


def _double_power_for(target, mods):
    """讓連環加其他功效「沒有優勢時贏的機會」剛好是 target 的威力（二分法；贏面隨威力單調上升）。"""
    low, high = 0.0, 300.0
    for _ in range(40):
        mid = (low + high) / 2
        if _double_win_rate(mid, 100, 0.0, mods, steps=400) < target:
            low = mid
        else:
            high = mid
    return (low + high) / 2


# 沒有優勢時贏的機會：0%（尾巴，威力低到連兩次最好的運氣都贏不了）、約 28%、75%
DOUBLE_LUCK_BASES = {"贏面 0%": 0.0, "贏面約 28%": 0.28, "贏面 75%": 0.75}


@pytest.mark.parametrize("label", list(DOUBLE_LUCK_BASES))
@pytest.mark.parametrize(
    "extra", [{}, {"luck_scale": 0.4}, {"luck_scale": 1.6}, {"difficulty_cut": 0.2}], ids=["連環", "連環加穩", "連環加險", "連環加破甲"],
)
def test_the_models_push_is_exact_under_double_luck_too_including_the_tails(label, extra):
    """Task 4 審查 M1：兩次運氣取好的，贏的機會是 1 − u²（u 是需要的運氣佔全幅的比例），平移 15% 的全幅在尾巴只推 2、在中間推 28
    個百分點。現在 resolve_encounter 在機率空間裡反解平移，每一組都剛好 ±15 個百分點，到 0%、100% 為止（夾住，不會推到負的）。"""
    mods = Mods(double_luck=True, **extra)
    target = DOUBLE_LUCK_BASES[label]
    power = 0.0 if target == 0 else _double_power_for(target, mods)
    base = _double_win_rate(power, 100, 0.0, mods)
    assert base == pytest.approx(target, abs=0.01), label  # 起點真的是想測的那個贏面
    for advantage in (15, -15, 7, -7):
        pushed = _double_win_rate(power, 100, encounter.advantage_shift(100, advantage), mods)
        if target == 0.0:
            # 贏的那一線在運氣範圍之外（最終審查 I-1）：優勢最多推到那一線上，跟單次運氣一樣「推不動就推不動」：
            # 往上推最多推出 advantage 那麼多（到不了就少一點），往下推還是 0；不會為了湊滿 15 個百分點把差距整個搬過去
            expected_max = max(0.0, advantage / 100)
            assert 0.0 <= pushed <= expected_max + 0.003, (label, advantage, pushed)
        else:
            assert pushed == pytest.approx(min(1.0, max(0.0, base + advantage / 100)), abs=0.003), (label, advantage, base, pushed)


def test_a_hopeless_fight_under_double_luck_moves_no_more_than_a_single_roll_does():
    """最終審查 I-1：贏的那一線遠在運氣範圍之外（威力 10 打難度 220）時，連環不能因為「要推出 15 個百分點的贏面」就把差距整個搬到
    187（單次運氣推的是 19.8）：落敗一直落敗，只有那 15% 運氣範圍的平移。"""
    advantage_shift = encounter.advantage_shift(220, 15)
    single = resolve_encounter(10, 220, _Luck(0), shift=advantage_shift, mods=Mods()).margin - resolve_encounter(
        10, 220, _Luck(0), mods=Mods(),
    ).margin
    double_mods = Mods(double_luck=True)
    double = resolve_encounter(10, 220, _Luck(0, 0), shift=advantage_shift, mods=double_mods).margin - resolve_encounter(
        10, 220, _Luck(0, 0), mods=double_mods,
    ).margin
    assert single == pytest.approx(advantage_shift)
    assert 0 < double <= single  # 跟其他功效同一個量級（約 10～20），不是 187
    # 整個運氣範圍掃過去：落敗還是落敗（沒有一格被推成僵持或贏）
    half = encounter.luck_half(220)
    for m in range(0, 400):
        luck = -half + 2 * half * (m + 0.5) / 400
        result = resolve_encounter(10, 220, _Luck(luck, luck), shift=advantage_shift, mods=double_mods)
        assert result.tier == "落敗", (m, result)
    # 對稱的另一頭：穩贏的仗往下推（威力 400 打難度 100，−15）也從運氣範圍的邊緣算起：贏面從 100% 掉到 85%，兩次取好的要的平移是
    # 2·√0.15·半幅（≈ 23.2），比單次的 9 多是機率空間的斜率（兩次取好的在 100% 附近很平），不是被威力與難度的差拉到幾百
    low = encounter.advantage_shift(100, -15)
    moved = resolve_encounter(400, 100, _Luck(0, 0), shift=low, mods=double_mods).margin - resolve_encounter(
        400, 100, _Luck(0, 0), mods=double_mods,
    ).margin
    assert moved == pytest.approx(-2 * math.sqrt(0.15) * encounter.luck_half(100))


def test_the_double_luck_push_without_a_push_changes_nothing():
    mods = Mods(double_luck=True)
    for power in (70, 94.1, 115):
        assert resolve_encounter(power, 100, _Luck(3, -7), shift=0.0, mods=mods) == resolve_encounter(
            power, 100, _Luck(3, -7), mods=mods,
        )


def test_the_condition_floor_can_be_raised():
    assert encounter.condition_of(0, 300) == encounter.CONDITION_FLOOR
    assert encounter.condition_of(0, 300, floor=0.75) == pytest.approx(0.75)
    assert encounter.condition_of(300, 300, floor=0.75) == 1.0


def test_a_result_is_not_guarded_unless_someone_says_so():
    assert resolve_encounter(40, 100, _Luck(0)).guarded is False
