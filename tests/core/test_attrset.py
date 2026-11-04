"""五項屬性（屬性與跨季架構 v2 第三節；第 ② 階段第 1 批，tianxia/attrset.py）：開關加開季章、配比回溯、送點、舊鍵對應、新的檢定換算。"""
from __future__ import annotations

import random
import tempfile
from pathlib import Path

from conftest import real_content
from tianxia import attrset, rules, team
from tianxia.engine import Game
from tianxia.models import Check, Effect
from tianxia.sqlite_world import open_world


def _game(on: bool = True, profile: str = "season21") -> Game:
    c = real_content(profile)
    c.config.attributes.v2.enabled = on
    c.config.auto_open_first_season = True
    world = open_world(Path(tempfile.mkdtemp(prefix="attrs-")) / "tianxia.db")
    g = Game.new(c, "沈浪", rng=random.Random(0), world=world)
    g.client = None
    g.state.player.tutorial_step = len(c.tutorial.steps)
    return g


def _level(g: Game, level: int) -> None:
    g.state.player.member.level = level


def test_the_season_stamp_turns_it_on_and_the_switch_alone_does_not():
    g = _game(True)
    assert g.state.world.attrs_v2 and attrset.on(g.content, g.state.world)
    off = _game(False)
    assert not attrset.on(off.content, off.state.world)
    off.content.config.attributes.v2.enabled = True  # 季中打開主機開關：正在跑的季沒蓋章，照舊
    assert not attrset.on(off.content, off.state.world)


def test_values_grow_by_the_preset_and_a_later_pick_is_retroactive():
    g = _game()
    c, v2 = g.content, g.content.config.attributes.v2
    _level(g, 11)
    balanced = attrset.values(g.state, c)
    assert balanced == {k: v2.base + 10 * 2 for k in v2.keys}  # 還沒挑：照均衡長
    g.pick_growth("warrior")
    assert attrset.value(g.state, c, "str") == v2.base + 10 * 4  # 回溯：照現在的等級整條重算
    assert attrset.value(g.state, c, "int") == v2.base + 10 * 1
    names = [row[0] for row in g.status_data()["attrs"]]
    assert names == ["武力", "統御", "悟性", "身法", "魅力"]


def test_custom_split_must_add_up():
    g = _game()
    bad = g.pick_growth("custom", {"str": 9, "lead": 1, "int": 0, "spd": 0, "cha": 0})
    assert "至少" in bad[-1] and g.state.player.growth_preset is None
    g.pick_growth("custom", {"str": 6, "lead": 1, "int": 1, "spd": 1, "cha": 1})
    _level(g, 3)
    assert attrset.value(g.state, g.content, "str") == g.content.config.attributes.v2.base + 12


def test_bonus_points_every_ten_levels_have_no_cap():
    g = _game()
    c = g.content
    assert team.level_points(g.state, c, 9, 10) == c.config.attributes.v2.bonus_points
    assert team.level_points(g.state, c, 10, 19) == 0
    g.state.player.stat_points = 30
    for _ in range(30):
        g.allocate_stat("cha")
    assert g.state.player.attr_alloc == {"cha": 30} and g.state.player.stat_points == 0


def test_old_formulas_read_the_new_value_on_the_old_scale():
    g = _game()
    c = g.content
    assert team.v1_stat(g.state, c, "agi") == 5  # 第 1 級、還沒長：舊尺度的起點
    _level(g, 11)
    g.pick_growth("ranger")  # 身法每級 4
    assert team.v1_stat(g.state, c, "agi") == 5 + 40 / 10
    assert team.v1_stat(g.state, c, "lore") == 5  # 博聞拔掉：當基準
    assert team.con_of(g.state, c, g.world, "player") == team.v1_stat(g.state, c, "con")


def test_the_check_is_relative_to_the_level():
    g = _game()
    c = g.content
    check = Check(stat="wis", grade="normal", tier=2)  # 第二階：減法季的放寬不算進來
    even = rules.check_outlook(check, g.state, c, g.world)
    assert round(even.chance, 6) == c.config.attributes.v2.grade_rates["normal"]  # 第 1 級＝平均人
    _level(g, 21)
    g.pick_growth("strategist")  # 悟性每級 4：高過平均
    high = rules.check_outlook(check, g.state, c, g.world).chance
    g.pick_growth("warrior")  # 悟性每級 1：低過平均，還是有基本的成功率
    low = rules.check_outlook(check, g.state, c, g.world).chance
    assert high > c.config.attributes.v2.grade_rates["normal"] > low >= c.config.checks.floor
    legacy = Check(stat="agi", difficulty=8)  # 舊寫法照帶子分級：8 是「難」＋1
    assert rules.grade_of(legacy, c) == ("hard", 1)


def test_events_give_xinde_instead_of_attribute_points():
    g = _game()
    p = g.state.player
    before = p.stats.get("xinde", 0)
    rules.apply_effect(Effect(stats={"str": 2, "silver": 5}), g.state, g.content, g.world)
    assert p.stats["xinde"] == before + 2 * g.content.config.attributes.v2.attr_xinde
    assert attrset.value(g.state, g.content, "str") == g.content.config.attributes.v2.base


def test_the_old_season_is_untouched():
    g = _game(False)
    assert "growth" not in g.status_data()
    assert [row[2] for row in g.status_data()["attrs"]] == list(team.COMBAT_STATS)
