"""假人的共用層 bot_base（第二輪第 89 批）：舊名與新位置是同一批物件，一次 pick 的快取只有一份。

改 bot_base 時 scripts/test_for.py 只挑自己檔名、煙霧與邊界，要有這個檔；讀它的那幾包與舊名另外跑（bot_base 模組說明列的那一串）。"""
from __future__ import annotations

import pytest

from tianxia import bot, bot_base, bot_policy
from tianxia.core import bounty_base
from tianxia.features.battle import bots as battle_bots
from tianxia.features.bounties import bots as bounties_bots
from tianxia.features.bounties import rules as bounty_rules
from tianxia.features.checkin import bots as checkin_bots
from tianxia.features.craft import bots as craft_bots
from tianxia.features.cultivation import bots as cultivation_bots
from tianxia.features.explore import bots as explore_bots
from tianxia.features.faction import bots as faction_bots
from tianxia.features.figure_acts import bots as figure_bots
from tianxia.features.gear import bots as gear_bots
from tianxia.features.outlets import bots as outlets_bots
from tianxia.features.peers import bots as peers_bots
from tianxia.features.sense import bots as sense_bots
from tianxia.features.smithy import bots as smithy_bots
from tianxia.features.sortie import bots as sortie_bots
from tianxia.features.stamina_plays import bots as stamina_bots
from tianxia.features.travel import bots as travel_bots

BOT_POLICY = {
    bot_base: ("BOUNTY_SCORE", "ORDER_SCORE", "PRACTICE_SCORE", "SORTIE_WIN", "SORTIE_WIN_FLOOR", "TREND_WEIGHT", "_bounty_here", "_cannot_push", "_crippled",
               "_duel_value", "_goals", "_outmatched", "_side", "_sortie_win", "_train_value", "_turn_cached",
               "NO_NAME", "DiscussJob", "EpiphanyJob", "ForgeJob", "MasterJob", "NamingSlot", "SenseJob", "next_hop"),  # 這一行第二輪第 101 批
    travel_bots: ("AWAY_MOVE_SCORE", "BOUNTY_MOVE_SCORE", "CLINIC_MOVE_SCORE", "CLINIC_URGENT_SCORE", "FOCUS_MOVE_SCORE", "HOME_MOVE_SCORE", "ORDER_MOVE_SCORE",
                  "SUMMONS_MOVE_SCORE", "TRAIN_MOVE_SCORE", "_bounty_hop", "_clinic_score", "_focus_hop", "_front_hop", "_front_locations", "_home", "_losing_front",
                  "_order_hop", "_order_hop_now", "_summons_hop"),
    sortie_bots: ("DUTY_SCORE", "TRAIN_SCORE"),
    explore_bots: ("ACT_SCORES", "NEED_MATERIAL_SCORE", "OUTING_SCORE"),
    figure_bots: ("CHALLENGE_ODDS", "CHALLENGE_SCORE", "STRIKE_ODDS"),
    # 第二輪第 101 批：每包的按法
    battle_bots: ("_staying_for_the_battle", "_toward_battle"),
    craft_bots: ("_forge",),
    cultivation_bots: ("LEARN_ROOM", "LEARN_SILVER_RESERVE", "_learn_here", "_master", "_too_dear"),
    faction_bots: ("_toward_faction",),
    peers_bots: ("_answer_discuss",),
    sense_bots: ("_god_name", "_sense"),
    smithy_bots: ("DIVINE_NAME_CHANCE", "_name_originals"),
    stamina_bots: ("PLAY_CHANCE", "PLAY_STAMINA", "_stamina_play"),
}
BOT = {
    bot_base: ("CLINIC_MIN_SILVER", "CLINIC_URGENT", "can_pay_clinic", "injury_share", "TRADE_KEEP", "TRADE_MOVES", "trade_keep"),
    travel_bots: ("CLINIC_AT", "clinic_hop"),
    smithy_bots: ("FORGE_SILVER_RESERVE", "_forge_plans", "forge_ready", "forge_step", "smith_want", "TIER3_WANT", "TIER4_WANT", "TRADE_SILVER_RESERVE", "keep_book_names", "trade_at_smith", "trade_want", "visit_smith"),
    gear_bots: ("MOUNT_SILVER_RESERVE", "market_want", "feed_mount", "visit_market", "wear_better"),
    sortie_bots: ("duel_moves",),
    figure_bots: ("CHALLENGE_ODDS",),
    # 第二輪第 101 批：每包的按法
    battle_bots: ("enlist_pick",),
    bounties_bots: ("take_bounties",),
    checkin_bots: ("check_in",),
    craft_bots: ("CREATE_INTENTS", "CREATE_RESERVE", "FORGE_RESERVE", "FORGE_TRIES", "MERGE_SHARE", "ForgePlan", "_name_draft", "create_art", "pick_forge"),
    cultivation_bots: ("CULTIVATE_RESERVE", "TEACH_MAX", "TEACH_RESERVE", "TRAIT_WEIGHT", "_worth", "allocate_points", "awaits_chance", "break_way", "growth_key", "melt_the_weakest",
                       "slot_insights", "switch_to_the_strongest", "takes_the_pill", "teach", "worn_first"),
    explore_bots: ("OUTING_SAY_CHANCE", "OUTING_WEIGHTS", "outing_say", "outing_segments"),
    outlets_bots: ("donate_spare", "donate_want"),
    sense_bots: ("SENSE_DRAW", "SENSE_RIGHT", "sense_draw", "sense_pick", "sense_stroke"),
}


@pytest.mark.parametrize(("old", "table"), [(bot_policy, BOT_POLICY), (bot, BOT)], ids=["bot_policy", "bot"])
def test_the_old_names_are_the_same_objects(old, table):
    for home, names in table.items():
        for name in names:
            assert getattr(old, name) is getattr(home, name), name


def test_next_hop_left_the_travel_package():
    """第二輪第 101 批：移動、決戰、陣營都讀，只留 bot_base 那一份（移動包不留這個名字）。"""
    assert not hasattr(travel_bots, "next_hop")


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
