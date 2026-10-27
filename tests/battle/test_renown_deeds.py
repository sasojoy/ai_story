"""立功給名望（名聲設計 3.1）：出陣攻打贏 +1、挑戰本人打贏 +2、決戰自己出手至少 1 回合 +2、自己那一邊大勝再 +2；
加名望一律走 renown.gain（3.2）。關著一個字都不變。"""
import random

from conftest import real_content

from tianxia import battle_instance as bi
from tianxia import renown
from tianxia.engine import Game
from tianxia.state import new_game_state


def test_gain_moves_the_stat_and_never_goes_below_zero():
    c = real_content("week7")
    s = new_game_state(c, "甲")
    assert renown.gain(s, c, "fame", 3) == ["名望 +3"] and s.player.stats["fame"] == 3
    assert renown.gain(s, c, "fame", -5) == ["名望 -3"] and s.player.stats["fame"] == 0
    assert renown.gain(s, c, "fame", -1) == []


def _game(c):
    c.config.auto_open_first_season = True
    g = Game.new(c, "甲", rng=random.Random(0))
    g.client = None
    g.state.player.faction = "guan"
    return g


def test_deed_fame_reads_the_table_and_the_switch():
    c = real_content("week7")
    g = _game(c)
    assert g._deed_fame("sortie") == ["名望 +1"] and g.state.player.stats["fame"] == 1
    c.config.renown.deeds["sortie"] = 0
    assert g._deed_fame("sortie") == []
    c.config.renown.deed_fame = False
    assert g._deed_fame("challenge") == [] and g.state.player.stats["fame"] == 1


def _showdown(margin="大勝", side="guan"):
    return bi.BattleInstance(battle_id="wancheng_jia", phase="ended", outcome_side=side, outcome_margin=margin)


def test_showdown_pay_gives_fame_only_to_those_who_acted():
    c = real_content("week7")
    g = _game(c)
    idle = bi.BattleParticipant(name="甲", faction="guan", neili=1, neili_cap=1, acted_rounds=0)
    assert not any(x.startswith("名望") for x in g._showdown_pay(_showdown(), idle, []))
    me = bi.BattleParticipant(name="甲", faction="guan", neili=1, neili_cap=1, acted_rounds=2)
    assert "名望 +4" in g._showdown_pay(_showdown(), me, [])  # 參戰 +2、自己那一邊大勝再 +2（合成一行）
    assert "名望 +2" in g._showdown_pay(_showdown("險勝"), me, [])
    assert "名望 +2" in g._showdown_pay(_showdown(side="huang"), me, [])  # 輸的那一邊照樣有參戰的


def test_showdown_pay_without_renown_has_no_fame():
    c = real_content("week7")
    c.config.renown.titles = False
    g = _game(c)
    me = bi.BattleParticipant(name="甲", faction="guan", neili=1, neili_cap=1, acted_rounds=2)
    assert not any(x.startswith("名望") for x in g._showdown_pay(_showdown(), me, []))
