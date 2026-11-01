"""武學加難（企劃者 2026-10-07 選 PR #28 的 A＋B＋C）剩下的那幾樣（武學重構，Joy 2026-10-20）：A 的 2N 練成價與絕學那一步的
成數門檻（cultivate_min_level 的「絕學」）、C 的契機（絕學要打贏硬仗）與服丹強行衝關。B（修練的機率看搭配）、
衝品的階梯、火候都跟著「品級不靠修練」一起拿掉了。

測試內容（tests/fixtures/content/config.json）把成數門檻與契機關著，這裡用 harden() 打開成程式的預設（＝正式內容寫的值）。"""

import pytest

from tianxia import cultivation, skillview, team
from tianxia.battlelog import new_record
from tianxia.models import Breakthrough, Config

from test_cultivation import BASICS, Fixed, LOSE, PILL, WIN, equip, kicker_art, ripen


def harden(content):
    """把練成價、成數門檻、契機打開成程式的預設。"""
    cfg, base = content.config, Config()
    cfg.practice_xinde_per_level = base.practice_xinde_per_level
    cfg.cultivate_min_level = base.cultivate_min_level
    cfg.breakthrough = Breakthrough()
    return content


@pytest.fixture
def hard(content):
    return harden(content)


@pytest.fixture
def kicker(state, world, hard):
    """功法庫裡一門旋風腿（上品、第十成、四個基本意境裝滿槽）、體力滿。"""
    world.claim_skill_name(kicker_art())
    return ripen(equip(state))


def at(state, level, quality="上品", slots=BASICS):
    return ripen(state, level=level, quality=quality, slots=slots)


# ── A：練成價與成數門檻 ──────────────────────────────


def test_practice_costs_twice_the_level_so_ten_levels_cost_ninety(hard):
    assert [team.practice_price(hard, n) for n in range(1, 10)] == [2, 4, 6, 8, 10, 12, 14, 16, 18]
    assert sum(team.practice_price(hard, n) for n in range(1, 10)) == 90


def test_the_last_step_waits_for_the_tenth_level_and_a_refusal_costs_nothing(kicker, hard, world):
    at(kicker, 9)
    kicker.player.legend_items = 1
    msgs = cultivation.cultivate(kicker, hard, world, "旋風腿", WIN, use_legend=True)
    assert msgs == [cultivation.NOT_RIPE_LINE.format(name="旋風腿", level=9, need=100, score=128)]
    assert kicker.player.stamina == 150 and kicker.player.art_quality["旋風腿"] == "上品" and kicker.player.legend_items == 1
    at(kicker, 10)
    assert cultivation.cultivate_problem(kicker, hard, world, "旋風腿", use_legend=True) is None


def test_the_level_gate_is_read_from_config(kicker, hard, world):
    """門檻寫在 cultivate_min_level 的「絕學」：改成 8，第八成就算到了極處。"""
    hard.config.cultivate_min_level = {"絕學": 8}
    at(kicker, 8)
    assert cultivation.ready(kicker, hard, world, "旋風腿") == (True, None)
    at(kicker, 7)
    assert not cultivation.ready(kicker, hard, world, "旋風腿")[0]


@pytest.mark.parametrize("quality", ["下品", "中品"])
def test_the_lower_grades_do_not_climb_by_cultivating_whatever_the_level(kicker, hard, world, quality):
    """武學重構：品級不靠修練衝——下品、中品練滿十成也沒有「修練」這一步（合成或自創才長品級）。"""
    at(kicker, 10, quality)
    kicker.player.legend_items = 1
    assert cultivation.cultivate(kicker, hard, world, "旋風腿", WIN, use_legend=True) == [cultivation.NO_RANK_LINE]
    assert kicker.player.art_quality["旋風腿"] == quality and kicker.player.stamina == 150


def test_the_old_gate_flag_no_longer_skips_the_level(kicker, hard, world):
    """gate 留著讓舊呼叫端不改，但不看：序章也沒有一定升品那一步了。"""
    at(kicker, 1)
    assert cultivation.cultivate_problem(kicker, hard, world, "旋風腿", gate=False, use_legend=True) is not None
    kicker.player.legend_items = 1
    assert cultivation.cultivate(kicker, hard, world, "旋風腿", WIN, gate=False, use_legend=True)[0].startswith("【旋風腿】還沒到極處")


# ── C：絕學要契機 ──────────────────────────────


def test_the_upper_grade_at_its_peak_waits_for_a_chance_and_costs_nothing_in_the_practice_room(kicker, hard, world):
    at(kicker, 10)
    stamina = kicker.player.stamina
    msgs = cultivation.cultivate(kicker, hard, world, "旋風腿", WIN)
    assert msgs == [cultivation.CHANCE_LINE.format(name="旋風腿", pill="破境丹")] and "不在練功房裡" in msgs[0]
    assert kicker.player.art_quality["旋風腿"] == "上品" and kicker.player.stamina == stamina  # 不收體力


def test_the_practice_row_shows_the_force_odds_not_a_climb(kicker, hard, world):
    at(kicker, 10)
    kicker.player.legend_items = 2
    row = next(r for r in skillview.art_rows(kicker, hard, world) if r["id"] == "旋風腿")
    assert row["cultivate"]["ok"] and row["cultivate"]["note"].endswith("體力 10")
    assert row["cultivate"]["legend"] == {
        "count": 2, "bonus": 15, "label": "服下破境丹強行衝關（剩 2 枚）", "note": "約 15% 衝開・體力 10",
    }


def _worn(state, level=10, slots=BASICS):
    """旋風腿穿在身上、上品、第十成、槽照 slots 裝。"""
    p = state.player
    p.arts, p.member.wugong_id = [], "旋風腿"
    return ripen(state, level=level, slots=slots)


def test_a_hard_win_at_the_peak_can_break_through(kicker, hard, world):
    _worn(kicker)
    msgs = cultivation.seize(kicker, hard, world, 0.5, WIN)
    assert msgs == ["這一戰打到最後，【旋風腿】忽然通了——從上品晉為絕學！"]
    assert kicker.player.art_quality["旋風腿"] == "絕學" and kicker.player.naming is None


def test_a_missed_chance_leaves_a_soft_hint(kicker, hard, world):
    _worn(kicker)
    assert cultivation.seize(kicker, hard, world, 0.5, LOSE) == ["打到緊處，【旋風腿】似乎摸到了什麼，轉眼又滑走了。"]
    assert kicker.player.art_quality["旋風腿"] == "上品"


def test_the_pill_forces_the_last_step_from_the_practice_room_only_when_ticked(kicker, hard, world):
    at(kicker, 10)
    kicker.player.legend_items = 2
    assert "不在練功房裡" in cultivation.cultivate(kicker, hard, world, "旋風腿", WIN)[0]  # 沒勾
    odds = cultivation.force_odds(kicker, hard, world, "旋風腿")
    assert odds == hard.config.legend_item_bonus  # 悟性 5：就是設定的那個數
    msgs = cultivation.cultivate(kicker, hard, world, "旋風腿", LOSE, use_legend=True)
    assert msgs[:2] == [PILL, f"【旋風腿】撞在那一層上，又彈了回來（約 {odds}% 的機會）。"]
    assert kicker.player.legend_items == 1 and kicker.player.art_quality["旋風腿"] == "上品"
    msgs = cultivation.cultivate(kicker, hard, world, "旋風腿", WIN, use_legend=True)
    assert "從上品晉為絕學" in msgs[1] and kicker.player.legend_items == 0


def test_a_won_fight_in_the_game_files_the_breakthrough_in_the_battle_report(game, hard):
    """Game 打贏一場硬仗（險勝以上）：契機那一句寫進回話，也寫進這一場戰報的敘事。"""
    game.content = hard
    state = game.state
    game.world.claim_skill_name(kicker_art())
    state.player.insights = list(BASICS)
    _worn(state)
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
    game.state.player.insights = list(BASICS)
    _worn(game.state)
    squad = next(iter(hard.squads.values()))
    from tianxia.encounter import EncounterResult
    result = EncounterResult(tier="僵持", our_power=100.0, difficulty=200.0, margin=-10.0)
    assert game._seize(new_record(game.state, hard, game.world, squad, result, "train")) == []
