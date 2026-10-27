"""決戰名單標稱號（名聲設計 2.5、4.5）：加入時快照；善惡第 1 段起、名望名動一方起。"""
import random

from conftest import real_content, renown_unscaled

from tianxia import battle_instance as bi
from tianxia.engine import Game
from tianxia.models import BattleTuning


def test_board_rows_carry_the_snapshot():
    b = bi.BattleInstance(battle_id="t", phase="muster")
    bi.join_faction(b, "甲", "guan", 100, renown=["名動一方", "一方豪俠"])
    b.phase = "active"
    b.participants["甲"].acted_rounds = 2
    board = bi.merit_board(b, BattleTuning(), "guan", "huang", "甲")
    assert board["left"][0]["renown"] == ["名動一方", "一方豪俠"]


def test_latecomers_carry_it_too():
    c = renown_unscaled(real_content("week7"))
    b = bi.BattleInstance(battle_id="t", phase="active")
    definition = next(iter(c.battles.values()))
    bi.auto_assign_latecomer(b, definition, "乙", 100, random.Random(0), faction=definition.factions[0].id, renown=["天下聞名"])
    assert b.participants["乙"].renown == ["天下聞名"]


def test_marks_start_at_the_second_fame_tier():
    c = renown_unscaled(real_content("week7"))
    c.config.auto_open_first_season = True
    g = Game.new(c, "甲", rng=random.Random(0))
    g.client = None
    g.state.player.stats.update({"fame": 12, "good": 6})
    assert g._battle_marks()["renown"] == ["江湖遊俠"]  # 小有名氣不上決戰名單
    g.state.player.stats["fame"] = 25
    assert g._battle_marks()["renown"] == ["名動一方", "江湖遊俠"]
    c.config.renown.titles = False
    assert g._battle_marks()["renown"] == []
