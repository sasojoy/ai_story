import random
import re
from pathlib import Path

import pytest

from conftest import FixedRandom
from tianxia.battle import (
    ADVANTAGE, Art, Eff, Rules, Status, Unit, compute_damage, run_battle, stat_of, style_multiplier,
)


def unit(name="甲", atk=10.0, dfn=5.0, spd=5.0, wis=5.0, hp=500.0, **kw):
    hp_max = kw.pop("hp_max", hp)
    return Unit(name=name, atk=atk, dfn=dfn, spd=spd, wis=wis, hp=hp, hp_max=hp_max, **kw)


def test_style_cycle():
    assert style_multiplier("柔", "剛") == ADVANTAGE
    assert style_multiplier("剛", "柔") == pytest.approx(1 / ADVANTAGE)
    assert style_multiplier("剛", "剛") == 1.0
    assert style_multiplier("無", "快") == 1.0


def test_strong_side_wins_and_result_is_from_side_a():
    res = run_battle([unit("強", atk=50, hp=2000)], [unit("弱", atk=5, hp=100)], random.Random(0))
    assert res.outcome == "win" and res.rounds == 1
    assert "弱倒下，敵方敗退。" in res.report
    res2 = run_battle([unit("弱", atk=5, hp=100)], [unit("強", atk=50, hp=2000)], random.Random(0))
    assert res2.outcome == "lose"
    assert "弱倒下，我方敗退。" in res2.report


def test_leader_down_means_defeat_even_if_others_stand():
    leader = unit("隊長", hp=10, leader=True)
    guard = unit("護衛", dfn=100, hp=99999)
    enemy = unit("刺客", atk=40, spd=20, hp=99999)
    res = run_battle([leader, guard], [enemy], random.Random(0), Rules(leader_focus=1.0))
    assert res.outcome == "lose"
    assert res.hp[1] == 99999


def test_draw_after_max_rounds():
    res = run_battle([unit("甲", atk=1, hp=99999)], [unit("乙", atk=1, hp=99999)], random.Random(0), Rules(max_rounds=3))
    assert res.outcome == "draw" and res.rounds == 3
    assert "不分勝負" in res.report[-1]


def test_passive_art_applies_for_whole_battle():
    a = unit("甲", hp=99999, arts=[Art("金鐘罩", "心法", effects=[Eff("buff", 0.5, target="self", stat="dfn")])])
    res = run_battle([a], [unit("乙", hp=99999, atk=1)], random.Random(0), Rules(max_rounds=2))
    assert "【心法】甲運起金鐘罩。" in res.report
    assert stat_of(a, "dfn") == pytest.approx(7.5)


def test_ultimate_with_preparation_fires_next_turn():
    art = Art("開碑手", "絕招", chance=1.0, prep=1, effects=[Eff("damage", 2.0)])
    a = unit("甲", hp=99999, arts=[art])
    res = run_battle([a], [unit("乙", hp=99999, atk=1)], random.Random(0), Rules(max_rounds=2))
    first, second = "\n".join(res.report).split("── 第2回合 ──")
    assert "【絕招】甲開始蓄勢（開碑手）" in first and "施展開碑手" not in first
    assert "【絕招】甲施展開碑手！" in second


def test_sealed_meridians_block_ultimates():
    art = Art("開碑手", "絕招", chance=1.0, effects=[Eff("damage", 2.0)])
    a = unit("甲", hp=99999, arts=[art], statuses=[Status("control", control="封脈", rounds=99)])
    text = "\n".join(run_battle([a], [unit("乙", hp=99999, atk=1)], random.Random(0), Rules(max_rounds=1)).report)
    assert "甲經脈受封，絕招發不出來。" in text and "施展開碑手" not in text


def test_acupoint_lock_skips_turn():
    a = unit("甲", hp=99999, statuses=[Status("control", control="點穴", rounds=99)])
    res = run_battle([a], [unit("乙", hp=99999, atk=1)], random.Random(0), Rules(max_rounds=1))
    assert "甲穴道受制，動彈不得。" in res.report


def test_disarm_blocks_attack_and_combo():
    combo = Art("連環腿", "連招", chance=1.0, effects=[Eff("damage", 1.0)])
    a = unit("甲", hp=99999, arts=[combo], statuses=[Status("control", control="卸兵", rounds=99)])
    text = "\n".join(run_battle([a], [unit("乙", hp=99999, atk=1)], random.Random(0), Rules(max_rounds=1)).report)
    assert "甲兵刃被卸，無法出招。" in text and "連環腿" not in text


def test_combo_follows_normal_attack():
    combo = Art("連環腿", "連招", chance=1.0, effects=[Eff("damage", 1.0)])
    a = unit("甲", hp=99999, arts=[combo])
    text = "\n".join(run_battle([a], [unit("乙", hp=99999, atk=1)], random.Random(0), Rules(max_rounds=1)).report)
    assert text.index("甲的普攻命中乙") < text.index("【連招】甲順勢使出連環腿！")


def test_control_effect_applies_status():
    art = Art("點穴手", "絕招", chance=1.0, effects=[Eff("control", 1.0, control="點穴", rounds=1)])
    a = unit("甲", spd=10, hp=99999, arts=[art])
    b = unit("乙", spd=1, hp=99999, atk=1)
    res = run_battle([a], [b], FixedRandom(0.0), Rules(max_rounds=1))
    assert "乙被點穴了！" in res.report
    assert "乙穴道受制，動彈不得。" in res.report


def test_control_from_slower_caster_skips_targets_next_turn():
    """持續回合以中招者自己的回合計：快的人本回合已出手，一回合的點穴要留到他下一回合。"""
    art = Art("點穴手", "絕招", chance=1.0, effects=[Eff("control", 1.0, control="點穴", rounds=1)])
    slow = unit("甲", spd=1, hp=99999, arts=[art])
    fast = unit("乙", spd=10, hp=99999, atk=1)
    res = run_battle([slow], [fast], FixedRandom(0.0), Rules(max_rounds=2))
    first, second = "\n".join(res.report).split("── 第2回合 ──")
    assert "乙被點穴了！" in first and "乙穴道受制" not in first
    assert "乙穴道受制，動彈不得。" in second


def test_status_gained_on_own_turn_is_not_ticked_that_turn():
    buff = Art("提氣", "絕招", chance=1.0, effects=[Eff("buff", 0.5, target="self", stat="atk", rounds=1)])
    a = unit("甲", spd=10, hp=99999, arts=[buff])
    b = unit("乙", spd=1, hp=99999, atk=1, statuses=[Status("buff", 0.5, stat="dfn", rounds=1)])
    run_battle([a], [b], random.Random(0), Rules(max_rounds=1))
    assert [(s.stat, s.rounds) for s in a.statuses] == [("atk", 1)]  # 自己這回合才得到的，不扣
    assert b.statuses == []  # 回合開始就有的，自己的回合結束時扣掉


def test_heal_targets_lowest_ally():
    heal = Art("回春", "絕招", chance=1.0, effects=[Eff("heal", 0.5, target="ally_lowest")])
    healer = unit("醫", spd=10, hp=1000, arts=[heal])
    hurt = unit("傷", hp=100, hp_max=1000)
    res = run_battle([healer, hurt], [unit("敵", hp=99999, atk=1, spd=1)], random.Random(0), Rules(max_rounds=1))
    assert res.hp[1] > 100


def test_heal_reports_amount_actually_restored():
    heal = Art("回春", "絕招", chance=1.0, effects=[Eff("heal", 0.5, target="ally_lowest")])
    healer = unit("醫", spd=10, hp=1000, arts=[heal])
    hurt = unit("傷", hp=900, hp_max=1000)
    res = run_battle([healer, hurt], [unit("敵", hp=99999, atk=1, spd=1)], random.Random(0), Rules(max_rounds=1))
    assert res.hp[1] == 1000
    assert "傷回復 100 點內力。" in res.report  # 上限只差 100，不是 0.5 × 1000


def _enemy_leader_and_guard():
    return [unit("乙", hp=100, spd=1, leader=True), unit("丙", hp=99999, spd=1)]


def test_turn_ends_when_ultimate_fells_enemy_leader():
    ult = Art("開碑手", "絕招", chance=1.0, effects=[Eff("damage", 5.0)])
    combo = Art("連環腿", "連招", chance=1.0, effects=[Eff("damage", 1.0)])
    a = unit("甲", atk=50, spd=10, hp=99999, arts=[ult, combo])
    res = run_battle([a], _enemy_leader_and_guard(), FixedRandom(0.0), Rules())
    assert res.outcome == "win"
    fell = next(i for i, line in enumerate(res.report) if line.endswith("乙倒下了！"))
    assert res.report[fell + 1:] == ["乙倒下，敵方敗退。"]  # 不再普攻丙，也不接連招


def test_turn_ends_when_normal_attack_fells_enemy_leader():
    combo = Art("連環腿", "連招", chance=1.0, effects=[Eff("damage", 1.0)])
    a = unit("甲", atk=50, spd=10, hp=99999, arts=[combo])
    res = run_battle([a], _enemy_leader_and_guard(), FixedRandom(0.0), Rules())
    assert res.outcome == "win"
    fell = next(i for i, line in enumerate(res.report) if line.endswith("乙倒下了！"))
    assert "的普攻命中乙" in res.report[fell]
    assert res.report[fell + 1:] == ["乙倒下，敵方敗退。"]


def test_damage_scales_with_remaining_pool():
    rules = Rules()
    target = unit("乙", dfn=0)
    full = compute_damage(unit("甲", atk=20, hp=1000), target, 1.0, "無", rules)
    half = compute_damage(unit("甲", atk=20, hp=500, hp_max=1000), target, 1.0, "無", rules)
    assert full == 240 and half == 180


def test_counter_and_aptitude_multiply_damage():
    rules = Rules()
    att = unit("甲", atk=20, aptitude={"柔": 1.2})
    assert compute_damage(att, unit("乙", dfn=0, style="剛"), 1.0, "柔", rules) == round(240 * 1.25 * 1.2)
    assert compute_damage(att, unit("丙", dfn=0, style="無"), 1.0, "柔", rules) == round(240 * 1.2)


# ── 戰鬥事件與我方表現 ─────────────────────────────────


def test_battle_module_stays_pure():
    import tianxia.battle as battle

    source = Path(battle.__file__).read_text(encoding="utf-8")
    assert "models" not in source and "gradio" not in source


def test_ultimate_event_is_recorded_when_cast_not_when_charging():
    art = Art("開碑手", "絕招", chance=1.0, prep=1, effects=[Eff("damage", 2.0)])
    a = unit("甲", hp=99999, arts=[art])
    res = run_battle([a], [unit("乙", hp=99999, atk=1)], random.Random(0), Rules(max_rounds=2))
    ultimates = [e for e in res.events if e.kind == "ultimate"]
    assert [(e.round, e.actor, e.actor_side, e.art) for e in ultimates] == [(2, "甲", 0, "開碑手")]


def test_control_hit_is_an_event_and_is_tallied():
    art = Art("點穴手", "絕招", chance=1.0, effects=[Eff("control", 1.0, control="點穴", rounds=1)])
    a = unit("甲", spd=10, hp=99999, arts=[art])
    b = unit("乙", spd=1, hp=99999, atk=1)
    res = run_battle([a], [b], FixedRandom(0.0), Rules(max_rounds=1))
    controls = [e for e in res.events if e.kind == "control"]
    assert [(e.round, e.actor, e.actor_side, e.target, e.art, e.control) for e in controls] == [
        (1, "甲", 0, "乙", "點穴手", "點穴")
    ]
    assert res.controls == [1]


def test_resisted_control_is_neither_an_event_nor_tallied():
    art = Art("點穴手", "絕招", chance=1.0, effects=[Eff("control", 1.0, control="點穴", rounds=1)])
    a = unit("甲", spd=10, hp=99999, arts=[art])
    res = run_battle([a], [unit("乙", spd=1, hp=99999, atk=1)], FixedRandom(0.99), Rules(max_rounds=1))
    assert "乙化解了點穴。" in res.report
    assert res.controls == [0]
    assert not any(e.kind == "control" for e in res.events)


def test_knockout_is_an_event_and_damage_is_tallied_from_the_report():
    res = run_battle([unit("強", atk=50, hp=2000)], [unit("弱", atk=5, hp=100)], random.Random(0))
    knockouts = [e for e in res.events if e.kind == "knockout"]
    assert [(e.round, e.actor, e.actor_side, e.target, e.is_leader) for e in knockouts] == [(1, "強", 0, "弱", True)]
    shown = sum(int(n) for n in re.findall(r"強的\S+命中弱，造成 (\d+) 點傷害", "\n".join(res.report)))
    assert shown > 0 and res.dealt == [shown]
    assert res.controls == [0]


def test_tallies_count_only_the_current_battle():
    a = unit("強", atk=50, hp=2000)
    first = run_battle([a], [unit("弱", atk=5, hp=100)], random.Random(0))
    second = run_battle([a], [unit("弱", atk=5, hp=100)], random.Random(0))
    assert second.dealt == first.dealt
