"""素材與經濟（docs/superpowers/specs/2026-10-15-素材與經濟-design.md）第四～六節的純規則（tianxia/economy.py）：
收購、升階、捐軍備的價錢、比例、每日上限、軍備的對應、捐軍備推哪一條線。正式內容、7 天季（week7；Config.economy 預設開）。
素材：一階 rou_1 柳絲綿、二階 rou_2 流雲絮、三階 rou_3 化水晶（柔）；慢 man_*。"""
from __future__ import annotations

import pytest

from conftest import real_content, third_party_gentry
from tianxia import economy, rules
from tianxia.state import new_game_state
from tianxia.world_state import fresh_season

DAY = 20000  # 回體丹的換日算出來的「第幾天」，測試直接給


def _state(faction="guan", at="changshe", silver=500, bag=None, profile="week7", same=None, third_party=False):
    c = real_content(profile)
    c.config.auto_open_first_season = True
    c.config.four_tiers.enabled = False  # 素材四階之前的規則（三階不收、二換三一天一個）；四階的規則在 test_four_tiers
    if third_party:
        third_party_gentry(c)  # 豪強是第三方、有割據的規則（豪強分屬兩軍之前）
    if same is not None:
        c.config.economy.upgrade_same_share = same  # 1＝一定照投入的屬性（量價錢、上限的測試不看擲骰）
    s = new_game_state(c, "沈浪")
    s.world = fresh_season(c)  # 照設定蓋章：week7 是第一季的規則
    p = s.player
    p.faction, p.location = faction, at
    p.stats["silver"] = silver
    p.materials = dict(bag or {})
    return s, c


# ── 收購（第五節）──────────────────────────────────────────


def test_the_smith_pays_two_for_tier_one_and_six_for_tier_two():
    s, c = _state(bag={"rou_1": 5, "rou_2": 2})
    assert economy.sell_price(c, 1) == 2 and economy.sell_price(c, 2) == 6 and economy.sell_price(c, 3) is None
    msgs = economy.sell(s, c, "rou_1", 3)
    assert s.player.materials["rou_1"] == 2 and s.player.stats["silver"] == 506 and "銀兩 +6" in msgs
    economy.sell(s, c, "rou_2", 2)
    assert "rou_2" not in s.player.materials and s.player.stats["silver"] == 518


def test_tier_three_is_not_bought_and_refusals_touch_nothing():
    s, c = _state(bag={"rou_1": 2, "rou_3": 1})
    assert economy.sell_problem(s, c, "rou_3", 1) == economy.SELL_TIER3
    assert economy.sell_problem(s, c, "rou_1", 3) is not None  # 手上只有 2 個
    assert economy.sell_problem(s, c, "man_1", 1) is not None  # 手上沒有
    before = (dict(s.player.materials), s.player.stats["silver"])
    assert economy.sell(s, c, "rou_3", 1) == [economy.SELL_TIER3]
    assert economy.sell(s, c, "rou_1", 3) and (dict(s.player.materials), s.player.stats["silver"]) == before


def test_selling_ignores_who_holds_the_ground():
    own, c = _state(at="changshe")
    enemy, _ = _state(at="huangjin_camp")
    assert economy.sell_price(c, 1) == 2  # 收購價只看階，不看地盤（第五節）
    own.player.materials, enemy.player.materials = {"rou_1": 1}, {"rou_1": 1}
    economy.sell(own, c, "rou_1", 1)
    economy.sell(enemy, c, "rou_1", 1)
    assert own.player.stats["silver"] == enemy.player.stats["silver"] == 502


# ── 升階（第四節）──────────────────────────────────────────


def test_three_tier_ones_make_a_tier_two_for_five_silver_with_the_ground_perk():
    s, c = _state(at="changshe", bag={"rou_1": 7}, same=1)  # 長社是官軍的大本營：自家地盤 ×0.9
    assert economy.upgrade_cost(s, c, 2) == 5 and economy.upgrade_cost(s, c, 3) == 45  # 4.5 → 5（四捨五入，同 smithing.price）
    msgs = economy.upgrade(s, c, "柔", 2, DAY)
    assert s.player.materials == {"rou_1": 4, "rou_2": 1} and s.player.stats["silver"] == 495 and "銀兩 -5" in msgs
    away, _ = _state(at="huangjin_camp")  # 黃巾的大本營：別家地盤 ×1.2
    assert economy.upgrade_cost(away, c, 2) == 6 and economy.upgrade_cost(away, c, 3) == 60


def test_ten_tier_twos_make_one_tier_three_once_a_day():
    s, c = _state(bag={"man_2": 25}, same=1)
    assert economy.upgrade_left(s, c, 3, DAY) == 1 and economy.upgrade_left(s, c, 2, DAY) is None
    economy.upgrade(s, c, "慢", 3, DAY)
    assert s.player.materials == {"man_2": 15, "man_3": 1}
    assert economy.upgrade_left(s, c, 3, DAY) == 0
    assert economy.upgrade_problem(s, c, "慢", 3, DAY) == economy.UPGRADE_DAY_FULL
    assert economy.upgrade(s, c, "慢", 3, DAY) == [economy.UPGRADE_DAY_FULL] and s.player.materials["man_2"] == 15
    assert economy.upgrade_problem(s, c, "慢", 3, DAY + 1) is None  # 換日（台灣 00:00）之後又可以
    economy.upgrade(s, c, "慢", 3, DAY + 1)
    assert s.player.materials == {"man_2": 5, "man_3": 2}


@pytest.mark.parametrize("bag,silver", [({"rou_1": 2}, 500), ({"rou_1": 3}, 4)])
def test_short_of_materials_or_silver_changes_nothing(bag, silver):
    s, c = _state(bag=bag, silver=silver)
    problem = economy.upgrade_problem(s, c, "柔", 2, DAY)
    assert problem is not None
    before = (dict(s.player.materials), s.player.stats["silver"], dict(s.player.upgrades_today))
    assert economy.upgrade(s, c, "柔", 2, DAY) == [problem]
    assert (dict(s.player.materials), s.player.stats["silver"], dict(s.player.upgrades_today)) == before


def test_tier_one_cannot_be_made_and_unknown_attributes_are_refused():
    s, c = _state(bag={"rou_1": 30})
    assert economy.upgrade_problem(s, c, "柔", 1, DAY) is not None
    assert economy.upgrade_problem(s, c, "陰", 2, DAY) is not None  # 沒有陰屬的二階


# ── 升階出來的屬性隨機（企劃者 2026-10-15「屬性隨機、偏向投入的」）──────────


def test_half_comes_out_as_what_went_in_and_the_rest_splits_three_ways():
    _, c = _state()
    outcomes = economy.upgrade_outcomes(c, "柔", 2)
    assert [(m.id, round(w, 4)) for m, w in outcomes] == [
        ("rou_2", 0.5), ("gang_2", round(1 / 6, 4)), ("kuai_2", round(1 / 6, 4)), ("man_2", round(1 / 6, 4))]
    assert [m.id for m, _ in economy.upgrade_outcomes(c, "慢", 3)] == ["man_3", "gang_3", "rou_3", "kuai_3"]
    assert economy.upgrade_odds(c, "柔", 2) == "五成出流雲絮，其餘隨機"
    c.config.economy.upgrade_same_share = 1
    assert economy.upgrade_outcomes(c, "柔", 2) == [(c.materials["rou_2"], 1.0)]
    assert economy.upgrade_odds(c, "柔", 2) == "出流雲絮"


def test_the_rolls_lean_to_what_went_in():
    s, c = _state(bag={"rou_1": 3 * 600}, silver=10 ** 6)
    for _ in range(600):
        economy.upgrade(s, c, "柔", 2, DAY)
    got = {mid: s.player.materials.get(mid, 0) for mid in ("rou_2", "gang_2", "kuai_2", "man_2")}
    assert sum(got.values()) == 600 and s.player.upgrade_seq == 600
    assert 0.42 < got["rou_2"] / 600 < 0.58
    for mid in ("gang_2", "kuai_2", "man_2"):
        assert 0.11 < got[mid] / 600 < 0.23, got


def test_the_roll_is_its_own_seeded_dice():
    first, c = _state(bag={"rou_1": 30})
    second, _ = _state(bag={"rou_1": 30})
    rolled = [economy.roll_upgrade(first, c, "柔", 2) for _ in range(3)]
    assert len({m.id for m in rolled}) == 1  # 沒換的時候擲幾次都一樣（種子只看季數、名號、第幾次、階）
    for _ in range(8):
        economy.upgrade(first, c, "柔", 2, DAY)
        economy.upgrade(second, c, "柔", 2, DAY)
    assert first.player.materials == second.player.materials  # 同一個人同一季同樣的第幾次，出一樣的東西
    assert economy.upgrade_rng(first, 2).random() != economy.upgrade_rng(first, 3).random()


def test_an_astray_roll_says_what_came_out_and_still_counts_for_the_day():
    s, c = _state(bag={"man_2": 25}, same=0)  # 0：一定落到別的屬性
    msgs = economy.upgrade(s, c, "慢", 3, DAY)
    got = [mid for mid in ("gang_3", "rou_3", "kuai_3") if s.player.materials.get(mid)]
    assert len(got) == 1 and "man_3" not in s.player.materials
    assert msgs[0] == economy.UPGRADE_ASTRAY.format(count=10, low="磐嶽土", high=c.materials[got[0]].name)
    assert economy.upgrade_problem(s, c, "慢", 3, DAY) == economy.UPGRADE_DAY_FULL  # 三階一天一個照換了幾次算


# ── 捐軍備（第六節）──────────────────────────────────────────


def test_points_follow_the_grain_weights_and_the_daily_cap_cuts_in_half_way():
    s, c = _state(bag={"rou_1": 50, "rou_2": 5, "rou_3": 1})
    assert [economy.donate_points(c, m) for m in ("rou_1", "rou_2", "rou_3")] == [1, 3, 9]
    assert economy.donate_room(s, c, DAY) == 100
    s.player.donate_day, s.player.donated_today = DAY, 95
    assert economy.donate_room(s, c, DAY) == 5
    assert economy.donate_take(s, c, "rou_1", 50, DAY) == 5  # 只收得下那 5 點的份量，其餘留在背包
    assert economy.donate_take(s, c, "rou_2", 5, DAY) == 1  # 一個二階 3 點
    assert economy.donate_take(s, c, "rou_3", 1, DAY) == 0  # 一個三階 9 點，收不下
    assert economy.donate_room(s, c, DAY + 1) == 100  # 換日


def test_armaments_are_named_by_attribute():
    _, c = _state()
    assert [economy.armament_of(c, a) for a in ("慢", "快", "剛", "柔", "陰")] == ["糧秣", "箭矢", "甲冑", "戰馬", None]


def test_donating_pushes_the_bases_own_front_toward_your_side():
    s, c = _state()
    w = s.world
    assert economy.donate_target(c, w, "guan", "changshe") == ("yingru", -1)
    assert economy.donate_target(c, w, "guan", "wan_city") == ("nanyang", -1)  # 宛城不在戰線上：照大區的戰線
    assert economy.donate_target(c, w, "huang", "julu_altar") == ("jizhou", 1)


def test_third_party_gentry_donations_push_the_hold():
    s, c = _state(third_party=True)
    assert economy.donate_target(c, s.world, "haoqiang", "cao_manor") == (rules.GEJU, 1)  # 豪強推割據


def test_donating_in_a_season_without_the_season_one_rules():
    s, c = _state(profile=None)  # 14 天的預設設定：三條戰線都算黃巾聲勢、沒有割據
    w = s.world
    huangjin = next(t.id for t in c.scenario.trends if t.derived)
    assert economy.donate_target(c, w, "guan", "changshe") == (huangjin, -1)
    assert economy.donate_target(c, w, "haoqiang", "cao_manor") is None


def test_the_push_is_a_twentieth_of_a_point_cut_like_an_event():
    _, c = _state()
    assert economy.donate_push(c, 10) == pytest.approx(10 * 0.05 * 0.5)
