"""假人的共用層 bot_base（第二輪第 89 批）：舊名與新位置是同一批物件，一次 pick 的快取只有一份。

改 bot_base 時 scripts/test_for.py 只挑自己檔名、煙霧與邊界，要有這個檔；讀它的那幾包與舊名另外跑（bot_base 模組說明列的那一串）。"""
from __future__ import annotations

import pytest

from tianxia import bot, bot_base, bot_policy
from tianxia.core import bounty_base
from tianxia.features.bounties import rules as bounty_rules
from tianxia.features.explore import bots as explore_bots
from tianxia.features.figure_acts import bots as figure_bots
from tianxia.features.gear import bots as gear_bots
from tianxia.features.smithy import bots as smithy_bots
from tianxia.features.sortie import bots as sortie_bots
from tianxia.features.travel import bots as travel_bots

BOT_POLICY = {
    bot_base: ("BOUNTY_SCORE", "ORDER_SCORE", "PRACTICE_SCORE", "SORTIE_WIN", "SORTIE_WIN_FLOOR", "TREND_WEIGHT", "_bounty_here", "_cannot_push", "_crippled",
               "_duel_value", "_goals", "_outmatched", "_side", "_sortie_win", "_train_value", "_turn_cached"),
    travel_bots: ("AWAY_MOVE_SCORE", "BOUNTY_MOVE_SCORE", "CLINIC_MOVE_SCORE", "CLINIC_URGENT_SCORE", "FOCUS_MOVE_SCORE", "HOME_MOVE_SCORE", "ORDER_MOVE_SCORE",
                  "SUMMONS_MOVE_SCORE", "TRAIN_MOVE_SCORE", "_bounty_hop", "_clinic_score", "_focus_hop", "_front_hop", "_front_locations", "_home", "_losing_front",
                  "_order_hop", "_order_hop_now", "_summons_hop", "next_hop"),
    sortie_bots: ("DUTY_SCORE", "TRAIN_SCORE"),
    explore_bots: ("ACT_SCORES", "NEED_MATERIAL_SCORE", "OUTING_SCORE"),
    figure_bots: ("CHALLENGE_ODDS", "CHALLENGE_SCORE", "STRIKE_ODDS"),
}
BOT = {
    bot_base: ("CLINIC_MIN_SILVER", "CLINIC_URGENT", "can_pay_clinic", "injury_share"),
    travel_bots: ("CLINIC_AT", "clinic_hop"),
    smithy_bots: ("FORGE_SILVER_RESERVE", "_forge_plans", "forge_ready", "forge_step", "smith_want"),
    gear_bots: ("MOUNT_SILVER_RESERVE", "market_want"),
    sortie_bots: ("duel_moves",),
    figure_bots: ("CHALLENGE_ODDS",),
}


@pytest.mark.parametrize(("old", "table"), [(bot_policy, BOT_POLICY), (bot, BOT)], ids=["bot_policy", "bot"])
def test_the_old_names_are_the_same_objects(old, table):
    for home, names in table.items():
        for name in names:
            assert getattr(old, name) is getattr(home, name), name


def test_the_bounty_half_the_bots_read_is_the_same_objects():
    for name in ("army_of", "rallies", "targets"):
        assert getattr(bounty_rules, name) is getattr(bounty_base, name), name


def test_there_is_one_turn_cache_and_it_lives_in_bot_base():
    assert not hasattr(bot_policy, "_TURN")
    assert bot_base._TURN is None


def test_the_turn_cache_opens_fresh_and_clears_even_on_an_exception():
    with bot_base.turn_cache():
        assert bot_base._TURN == {}
        assert bot_base._turn_cached(("k",), lambda: 1) == 1
        assert bot_base._turn_cached(("k",), lambda: 2) == 1  # 這一輪裡同一個查詢只算一次
    assert bot_base._TURN is None
    assert bot_base._turn_cached(("k",), lambda: 3) == 3  # 不在 pick 裡每次算
    with pytest.raises(ValueError), bot_base.turn_cache():
        raise ValueError
    assert bot_base._TURN is None
