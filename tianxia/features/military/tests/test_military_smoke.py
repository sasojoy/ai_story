"""軍情的煙霧測試（開發規範手冊 4.1 第三級：一包一條，走一次最常見的路）：黃巾第 3 階站在汝南（城鎮、有戰線），選單上多一顆「在一地煽動起事」，
按下去扣體力、記這週一次、過檢定把潁汝線往己方推五點；包認領的欄位 rank_action_weeks 記下這一下。"""
import random
from unittest import mock

import pytest

from tianxia import rules
from tianxia.core.registry import FEATURES
from tianxia.engine import RANK_ACTION_PREFIX, Game


@pytest.mark.smoke
def test_a_yellow_turban_incites_a_town_and_the_front_moves(on):
    feature = next(f for f in FEATURES if f.name == "military")
    assert feature.enabled(None) and feature.player_fields[:3] == ("convoy", "rank2_days", "rank_action_weeks")  # 後面 15 個是機緣、伏筆的（第 34 批）
    game = Game.new(on, "甲", rng=random.Random(0))
    p = game.state.player
    p.faction, p.rank, p.location, p.stamina = "huang", 3, "runan", 100
    assert f"{RANK_ACTION_PREFIX}incite" in {o.id for o in game.options(odds=False) if o.enabled}
    before = rules.trend_value(game.state, on, "yingru")
    with mock.patch.object(rules, "check_chance", return_value=1.0):
        game.choose("act:rank:incite")
    assert rules.trend_value(game.state, on, "yingru") == before + 5
    assert sum(p.rank_action_weeks.values()) == 1 and p.stamina == 80
