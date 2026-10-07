"""武學加難（企劃者 2026-10-07 選 PR #28 的 A＋B＋C）：成數門檻與 2N 的練成價、修練的機率看搭配、絕學要契機。

測試內容（tests/fixtures/content/config.json）把三樣都關著，好讓舊的測試照舊量修練的階梯；這裡用 harden() 打開成程式的預設
（＝正式內容寫的值，test_cultivation.test_the_real_content_carries_the_new_first_step_numbers 鎖住兩邊一樣）。"""
import random

import pytest

from tianxia import cultivation, skillview, team
from tianxia.battlelog import new_record
from tianxia.models import Breakthrough, Config, CultivateFit

from test_cultivation import Fixed, LOSE, WIN, kicker_art


def harden(content):
    """把三樣都打開成程式的預設。"""
    cfg, base = content.config, Config()
    cfg.practice_xinde_per_level = base.practice_xinde_per_level
    cfg.cultivate_odds = base.cultivate_odds
    cfg.cultivate_min_level = base.cultivate_min_level
    cfg.cultivate_fit = CultivateFit()
    cfg.breakthrough = Breakthrough()
    return content


@pytest.fixture
def hard(content):
    return harden(content)


@pytest.fixture
def kicker(state, world, hard):
    """功法庫裡一門融了風（快）的旋風腿、手上有風、體力滿，人在山洞（悟得到的是山，不對味）。"""
    world.claim_skill_name(kicker_art())
    p = state.player
    p.arts, p.insights, p.stamina, p.location = ["旋風腿"], ["feng"], 150, "cave"
    return state


def at(state, level, quality="下品", heat=0):
    state.player.art_levels["旋風腿"] = level
    state.player.art_quality["旋風腿"] = quality
    if heat:
        state.player.art_mastery["旋風腿"] = heat
    return state


# ── A：成數門檻與練成價 ──────────────────────────────


def test_practice_costs_twice_the_level_so_ten_levels_cost_ninety(hard):
    assert [team.practice_price(hard, n) for n in range(1, 10)] == [2, 4, 6, 8, 10, 12, 14, 16, 18]
    assert sum(team.practice_price(hard, n) for n in range(1, 10)) == 90


@pytest.mark.parametrize(("quality", "target", "need"), [("下品", "中品", 4), ("中品", "上品", 7), ("上品", "絕學", 10)])
def test_each_grade_waits_for_its_level_and_a_refusal_costs_nothing(kicker, hard, world, quality, target, need):
    at(kicker, need - 1, quality)
    msgs = cultivation.cultivate(kicker, hard, world, "旋風腿", WIN)
    assert msgs == [f"【旋風腿】才練到第{need - 1}成，火候不到——先練到第{need}成，才談得上{target}。"]
    assert kicker.player.stamina == 150 and kicker.player.art_quality["旋風腿"] == quality
    at(kicker, need, quality)
    assert cultivation.cultivate_problem(kicker, hard, world, "旋風腿") is None


def test_the_prologue_sure_step_skips_the_level_gate(kicker, hard, world):
    at(kicker, 1)
    assert "火候不到" in cultivation.cultivate_problem(kicker, hard, world, "旋風腿")
    assert cultivation.cultivate_problem(kicker, hard, world, "旋風腿", gate=False) is None
    assert cultivation.cultivate(kicker, hard, world, "旋風腿", WIN, gate=False)[0].endswith("晉為中品！")


# ── B：修練的機率看搭配 ──────────────────────────────


def test_the_level_scales_the_odds_from_half_at_nothing_to_whole_at_ten(kicker, hard, world):
    at(kicker, 7, "中品")
    assert cultivation.fit(kicker, hard, world, "旋風腿").factor == pytest.approx(0.85)
    assert cultivation.odds_for(kicker, hard, "上品", 0, 0, world, "旋風腿") == round(6 * 0.85)
    at(kicker, 10, "中品")
    assert cultivation.fit(kicker, hard, world, "旋風腿") == cultivation.Fit(1.0, [])
    assert cultivation.odds_for(kicker, hard, "上品", 4, 0, world, "旋風腿") == 6 + 3 * 4


def test_cultivating_where_the_land_matches_the_art_goes_better_and_says_so_softly(kicker, hard, world):
    at(kicker, 10, "中品")
    kicker.player.location = "lake"  # 湖邊悟得到風（快），跟旋風腿相投
    matched = cultivation.fit(kicker, hard, world, "旋風腿")
    assert matched.factor == pytest.approx(1.5) and matched.lines == [hard.config.cultivate_fit.lines["home_ground"]]
    assert cultivation.odds_for(kicker, hard, "上品", 0, 0, world, "旋風腿") == 9
    assert not any(ch.isdigit() for ch in matched.lines[0])  # 含蓄：不寫倍數


def test_a_substitute_insight_of_the_same_attribute_is_a_step_removed(kicker, hard, world):
    from tianxia.martial_arts import Insight
    at(kicker, 10, "中品")
    world.claim_insight_recipe("feng+feng", Insight(id="旋風意", name="旋風意", attribute="快"))
    kicker.player.insights = ["旋風意"]  # 原本的風熔掉了，拿別的屬快的意境代用
    matched = cultivation.fit(kicker, hard, world, "旋風腿")
    assert matched.factor == pytest.approx(0.7) and hard.config.cultivate_fit.lines["substitute"] in matched.lines


def test_the_first_step_ignores_the_fit_because_w8_just_eased_it(kicker, hard, world):
    at(kicker, 4)  # 4 成：成數那一項 0.7，但第一階不看搭配
    assert cultivation.odds_for(kicker, hard, "中品", 0, 0, world, "旋風腿") == 40


def test_the_practice_row_says_the_fitted_odds_and_the_soft_line(kicker, hard, world):
    at(kicker, 10, "中品")
    kicker.player.location = "lake"
    row = next(r for r in skillview.art_rows(kicker, hard, world) if r["id"] == "旋風腿")
    assert row["cultivate"]["note"].startswith("9% 晉為上品・體力 10")
    assert hard.config.cultivate_fit.lines["home_ground"] in row["cultivate"]["note"]


# ── C：絕學要契機 ──────────────────────────────


def test_cultivating_an_upper_grade_art_only_tempers_it_until_the_heat_is_full(kicker, hard, world):
    at(kicker, 10, "上品")
    need = hard.config.breakthrough.heat
    for n in range(1, need):
        msgs = cultivation.cultivate(kicker, hard, world, "旋風腿", WIN)
        assert msgs == [f"【旋風腿】又添了一分火候（{n}／{need}）。", "體力 -10"]
    assert cultivation.cultivate(kicker, hard, world, "旋風腿", WIN)[0] == "【旋風腿】的火候已足。你隱約覺得，剩下那一步不在練功房裡。"
    assert kicker.player.art_quality["旋風腿"] == "上品" and kicker.player.art_mastery["旋風腿"] == need
    stamina = kicker.player.stamina
    assert "不在練功房裡" in cultivation.cultivate(kicker, hard, world, "旋風腿", WIN)[0]  # 滿了：不收體力
    assert kicker.player.stamina == stamina


def test_the_practice_row_shows_the_heat_not_a_chance(kicker, hard, world):
    at(kicker, 10, "上品", heat=3)
    row = next(r for r in skillview.art_rows(kicker, hard, world) if r["id"] == "旋風腿")
    assert row["cultivate"]["note"] == "火候 3／8・體力 10" and row["cultivate"]["legend"] is None


def _worn(state, world, content, heat):
    """旋風腿穿在身上、上品、第十成、火候 heat。"""
    p = state.player
    p.arts, p.member.wugong_id, p.member.wugong_level = [], "旋風腿", 10
    p.art_quality["旋風腿"] = "上品"
    p.art_mastery["旋風腿"] = heat
    return state


def test_a_hard_win_with_full_heat_can_break_through_and_names_the_first(kicker, hard, world):
    _worn(kicker, world, hard, 8)
    msgs = cultivation.seize(kicker, hard, world, 0.5, WIN)
    assert msgs[0] == "這一戰打到最後，【旋風腿】忽然通了——從上品晉為絕學！"
    assert kicker.player.art_quality["旋風腿"] == "絕學" and kicker.player.naming == "旋風腿"


def test_a_missed_chance_leaves_a_soft_hint_and_keeps_the_heat(kicker, hard, world):
    _worn(kicker, world, hard, 8)
    assert cultivation.seize(kicker, hard, world, 0.5, LOSE) == ["打到緊處，【旋風腿】似乎摸到了什麼，轉眼又滑走了。"]
    assert kicker.player.art_quality["旋風腿"] == "上品" and kicker.player.art_mastery["旋風腿"] == 8


@pytest.mark.parametrize(("ratio", "heat", "level"), [(0.29, 8, 10), (0.5, 7, 10), (0.5, 8, 9)])
def test_no_chance_without_a_hard_enough_fight_full_heat_and_ten_levels(kicker, hard, world, ratio, heat, level):
    _worn(kicker, world, hard, heat)
    kicker.player.member.wugong_level = level
    assert cultivation.seize(kicker, hard, world, ratio, WIN) == []
    assert kicker.player.art_quality["旋風腿"] == "上品"


def test_the_breakthrough_chance_grows_with_how_hard_the_fight_was(kicker, hard, world):
    """機會＝25% ×（難度比 ÷ 0.5）× 搭配 × 悟性，夾在 1～60：難度比 0.3 是 15%、0.5 是 25%、1.0 是 50%。"""
    _worn(kicker, world, hard, 8)
    for ratio, odds in ((0.3, 15), (0.5, 25), (1.0, 50), (3.0, 60)):
        assert cultivation.seize(kicker, hard, world, ratio, Fixed((odds - 0.01) / 100))[0].startswith("這一戰")
        _worn(kicker, world, hard, 8)
        kicker.player.naming = None
        assert cultivation.seize(kicker, hard, world, ratio, Fixed((odds + 0.01) / 100))[0].startswith("打到緊處")


def test_the_pill_forces_the_last_step_from_the_practice_room_only_when_ticked(kicker, hard, world):
    at(kicker, 10, "上品", heat=8)
    kicker.player.legend_items = 2
    assert "不在練功房裡" in cultivation.cultivate(kicker, hard, world, "旋風腿", WIN)[0]  # 沒勾
    odds = cultivation.force_odds(kicker, hard, world, "旋風腿")
    assert odds == hard.config.legend_item_bonus  # 第十成、原本的意境、不對味的地方、悟性 5
    msgs = cultivation.cultivate(kicker, hard, world, "旋風腿", LOSE, use_legend=True)
    assert msgs[:2] == ["你服下一枚【破境丹】，關起門來強行衝關。", f"【旋風腿】撞在那一層上，又彈了回來（約 {odds}% 的機會）。"]
    assert kicker.player.legend_items == 1 and kicker.player.art_quality["旋風腿"] == "上品"
    msgs = cultivation.cultivate(kicker, hard, world, "旋風腿", WIN, use_legend=True)
    assert "從上品晉為絕學" in msgs[1] and kicker.player.legend_items == 0


def test_a_won_fight_in_the_game_files_the_breakthrough_in_the_battle_report(game, hard):
    """Game 打贏一場硬仗（險勝以上）：契機那一句寫進回話，也寫進這一場戰報的敘事。"""
    game.content = hard
    state = game.state
    game.world.claim_skill_name(kicker_art())
    _worn(state, game.world, hard, 8)
    game.rng = Fixed(0.0)
    squad = next(iter(hard.squads.values()))
    from tianxia.encounter import EncounterResult
    result = EncounterResult(tier="險勝", our_power=100.0, difficulty=80.0, margin=10.0)
    record = new_record(state, hard, game.world, squad, result, "train")
    msgs = game._seize(record)
    assert msgs and "晉為絕學" in msgs[0] and msgs[0] in record.notes


def test_a_lost_fight_is_no_chance(game, hard):
    game.content = hard
    game.world.claim_skill_name(kicker_art())
    _worn(game.state, game.world, hard, 8)
    squad = next(iter(hard.squads.values()))
    from tianxia.encounter import EncounterResult
    result = EncounterResult(tier="僵持", our_power=100.0, difficulty=200.0, margin=-10.0)
    assert game._seize(new_record(game.state, hard, game.world, squad, result, "train")) == []
