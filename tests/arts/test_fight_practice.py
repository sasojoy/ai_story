"""武學打了才升（Config.arts.fight_practice；Joy 2026-11-09「甲方案」「369成不卡手動用心得解 可以一路到10成」「悟性不加熟練」）。"""

import random

from tianxia import team
from tianxia.state import BattleRecord


def _on(game, cap=40):
    cfg = game.content.config.arts.fight_practice
    cfg.enabled, cfg.daily_cap = True, cap
    game.state.world.fight_practice = True
    m = game.state.player.member
    m.wugong_id, m.neigong_id = "fist", "breath"
    m.wugong_level = m.neigong_level = 1
    return m


def _fight(game, tier="大勝", kind="train", difficulty=0.2, power=1.0):
    record = BattleRecord(id=1, time=0.0, location="湖邊",
                          kind=kind, event="", opponent="誰", ours=[], tier=tier, our_power=power, difficulty=difficulty)
    game._file_battle(record)
    return record


def test_a_win_grows_both_worn_arts_and_writes_it_in_the_record(game):
    m = _on(game)
    record = _fight(game)
    p = game.state.player
    assert p.art_exp[m.wugong_id] == p.art_exp[m.neigong_id] == 5
    assert sum("熟練 +5（第1成 5/10）" in line for line in record.changes) == 2


def test_enough_practice_levels_the_art_up_and_carries_the_rest(game):
    m = _on(game)
    _fight(game, difficulty=0.5)  # 硬仗 ×1.5 → 8
    _fight(game, difficulty=0.5)
    assert m.wugong_level == 2 and game.state.player.art_exp[m.wugong_id] == 6


def test_weak_foes_give_nothing_and_kinds_against_people_count_double(game):
    m = _on(game)
    record = _fight(game, difficulty=0.1)
    assert game.state.player.art_exp == {} and record.changes == ["對手太弱，武學練不到什麼。"]
    _fight(game, tier="落敗", kind="spar")
    assert game.state.player.art_exp[m.wugong_id] == 4


def test_the_daily_cap_stops_the_farming_until_the_next_day(game):
    m = _on(game, cap=8)
    _fight(game)
    _fight(game)  # 5 ＋ 3（夾在上限）
    record = _fight(game)
    assert game.state.player.art_exp_today[m.wugong_id] == 8
    assert any("今天練夠了" in line for line in record.changes)
    game.state.world.time += team.DAY_SECONDS
    _fight(game)
    assert game.state.player.art_exp_today[m.wugong_id] == 5


def test_xinde_no_longer_buys_levels_in_a_fight_practice_season(game):
    """Joy 2026-11-13「為什麼還可以用心得練武學的成數」「拿掉，成數只靠戰鬥」。"""
    m = _on(game)
    _fight(game)  # 5/10
    p = game.state.player
    p.stats["xinde"] = 10_000
    assert team.xinde_practice_off(game.state, game.content)
    assert team.practice_cost(game.state, game.content, "武學") is None
    assert not team.can_practise(game.state, game.content, "武學")
    msgs = team.practice(game.state, game.content, game.world, "武學", random.Random(0))
    assert m.wugong_level == 1 and p.stats["xinde"] == 10_000 and p.art_exp[m.wugong_id] == 5
    assert "去打" in msgs[0]


def test_a_season_without_the_stamp_keeps_the_old_rules(game):
    m = _on(game)
    game.state.world.fight_practice = False
    record = _fight(game)
    assert game.state.player.art_exp == {} and not any("熟練" in line for line in record.changes)
    assert team.practice_cost(game.state, game.content, "武學") == team.practice_price(game.content, m.wugong_level)
