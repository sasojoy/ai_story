import random

from tianxia import encounter
from tianxia.encounter import (
    EncounterResult,
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
