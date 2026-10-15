"""第一季豪強分屬兩軍的補修（FB-273～275，QA 2026-10-16）。"""
from __future__ import annotations

import random

from conftest import real_content
from test_gentry_allied import _game, _old_rules, _showdown

from tianxia import allied, battle_instance


def _wk():
    c = real_content("weekend")
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    return c


def _ids(game):
    return [o.id for o in game.options() if o.enabled]


# ── FB-273：還沒選邊的豪強遇上集結 ─────────────────────────────


def test_an_unsided_gentry_only_picks_a_side_during_the_muster():
    game = _game(_wk(), faction="haoqiang")  # 拜入曹氏莊院那一下：陣營有了、還沒挑一邊
    definition = _showdown(game)
    assert not game._free_agent(definition)
    ids = [o.id for o in game.options()]
    assert [i for i in ids if i.startswith("battle:")] == []
    assert ids == ["faction:ally:guan", "faction:ally:huang"]
    assert game.choose("battle:enlist:huang") == ["（此刻無法這麼做。）"]
    assert "甲" not in game.world.get_battle().participants


def test_picking_a_side_moves_the_muster_entry_over():
    game = _game(_wk())  # 散人：先臨時投效黃巾
    definition = _showdown(game)
    game.choose("battle:enlist:huang")
    assert game.world.get_battle().participants["甲"].faction == "huang"
    game.state.player.faction = "haoqiang"  # 接著拜入曹氏莊院（還沒挑一邊）
    msgs = game.choose("faction:ally:guan")
    battle = game.world.get_battle()
    assert battle.participants["甲"].faction == "guan"
    assert allied.ALLY_REJOINED.format(ally="官軍", battle=definition.name) in msgs
    assert game.state.journal[0].lines[-1] == allied.ALLY_REJOINED.format(ally="官軍", battle=definition.name)


def test_picking_the_same_side_says_nothing_more():
    game = _game(_wk())
    _showdown(game)
    game.choose("battle:enlist:guan")
    game.state.player.faction = "haoqiang"
    msgs = game.choose("faction:ally:guan")
    assert game.world.get_battle().participants["甲"].faction == "guan"
    assert msgs == [allied.ALLY_DONE.format(ally="官軍")]


def test_after_the_fight_starts_the_side_stays_for_this_battle():
    game = _game(_wk())
    definition = _showdown(game)
    game.choose("battle:enlist:huang")
    game.world.mutate_battle(lambda b: battle_instance.close_muster(b, definition, random.Random(0), 1000.0))
    game.state.player.faction = "haoqiang"
    assert "faction:ally:guan" not in _ids(game)  # 在場上打著：選單是戰場，打完（或走開）再挑
    game.world.mutate_battle(lambda b: setattr(b.participants["甲"], "away", True))  # 走出決戰的大區：照常遊玩
    msgs = game.choose("faction:ally:guan")
    assert game.state.player.ally == "guan"
    assert game.world.get_battle().participants["甲"].faction == "huang"  # 開打之後不能改投（同臨時投效）
    assert allied.ALLY_STAYS.format(ally="官軍", old="黃巾軍", battle=definition.name) in msgs


def test_an_unsided_gentry_is_not_pulled_into_a_running_fight():
    game = _game(_wk(), faction="haoqiang")
    definition = _showdown(game)
    game.world.mutate_battle(lambda b: battle_instance.close_muster(b, definition, random.Random(0), 1000.0))
    battle = game.world.get_battle()
    assert not game._fighting(battle, definition)
    ids = [o.id for o in game.options()]
    assert "battle:join_late" not in ids and ids[:2] == ["faction:ally:guan", "faction:ally:huang"]
    game.choose("faction:ally:guan")
    assert "battle:join_late" in [o.id for o in game.options()]  # 選了邊就照那一軍晚到


def test_old_rules_gentry_still_enlists_without_a_side():
    off = _old_rules()
    game = _game(off, name="乙", faction="haoqiang")
    definition = _showdown(game)
    assert game._free_agent(definition)
    assert [o.id for o in game.options() if o.id.startswith("battle:enlist:")]
