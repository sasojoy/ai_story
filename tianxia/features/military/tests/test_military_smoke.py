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


@pytest.mark.smoke
def test_the_opportunity_and_foreshadow_options_belong_to_the_package(on):
    """機緣 opp:、伏筆 fs:（全部拆包第 34 批）：兩個前綴都是軍情包的，按下去走 choose 掛鉤（標題先拿、動作後做）；舊名 tianxia.opportunities、
    tianxia.foreshadow 是同一個模組物件。"""
    from tianxia import foreshadow, opportunities
    from tianxia.core import features as features_core
    from tianxia.features.military import fs_rules, opp_rules

    assert foreshadow is fs_rules and opportunities is opp_rules
    assert features_core.owner_of("opp:deliver:x").name == "military" and features_core.owner_of("fs:leave").name == "military"
    game = Game.new(on, "甲", rng=random.Random(0))
    taken = features_core.choose(game, "fs", "leave")
    assert taken is not None and taken.title == "作罷" and isinstance(taken.run(), list)
    taken = features_core.choose(game, "opp", "deliver:no_such_opportunity")
    assert taken is not None and isinstance(taken.run(), list)  # 沒有這個機緣：一句「此刻無法這麼做」，不丟錯


@pytest.mark.smoke
def test_the_opportunity_and_foreshadow_admin_tools_refuse_a_player(on):
    """管理者給機緣、給片段（Game 上留的一行委派）：不是管理者回拒絕的一句，不丟錯、不動任何人的存檔。"""
    game = Game.new(on, "甲", rng=random.Random(0))
    assert isinstance(game.admin_give_opportunity("乙", "no_such"), list) and isinstance(game.admin_give_fragment("乙", "no_such:0"), list)


def test_the_pack_owns_both_foreshadow_event_files_and_drops_stale_foreshadow_refs(on):
    """附錄甲：events/foreshadow_* 都歸軍情；內容改版拿掉的伏筆鏈與物品在讀檔時清掉（on_drop_stale）。"""
    feature = next(f for f in FEATURES if f.name == "military")
    assert {"events/foreshadow_fragments.json", "events/foreshadow_prep.json"} <= set(feature.content)
    game = Game.new(on, "甲", rng=random.Random(0))
    p = game.state.player
    p.clue_items, p.fragments, p.fs_asking, p.fs_asked = {"gone_item": 2}, {"gone_chain": 1}, "gone_chain", 3
    game._drop_stale_references()
    assert p.clue_items == {} and p.fragments == {} and p.fs_asking is None and p.fs_asked == 0
