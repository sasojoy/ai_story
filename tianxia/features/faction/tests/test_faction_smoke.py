"""陣營的煙霧測試（開發規範手冊 4.1 第三級：一包一條，走一次最常見的路）：真實內容（第一季濃縮版，兩軍加豪強）裡，散人站在官軍的投靠點，
按「投靠官軍」出確認畫面（這一包的 choose 掛鉤接走，標題「考慮投靠官軍」）、按「確定」投靠；再走到黃巾的投靠點，選單上多一顆「叛投黃巾軍」，
按下去又出確認畫面，按「再想想」收掉。假人不按這三種前綴（bot_pick 一律 None）。沒有模型（client=None）。"""
import random

import pytest

from conftest import real_content
from tianxia.core.registry import FEATURES
from tianxia.engine import Game


@pytest.mark.smoke
def test_a_loner_joins_the_army_and_then_sees_the_defect_option_through_the_choose_hook():
    feature = next(f for f in FEATURES if f.name == "faction")
    assert feature.prefix == ("faction", "defect", "sect") and feature.bot_always == ("defect:", "faction:lean:")
    content = real_content("week7")
    content.config.auto_open_first_season = True
    guan = content.scenario.faction("guan")
    huang = content.scenario.faction("huang")
    game = Game.new(content, "甲", rng=random.Random(0))
    game.skip_tutorial()
    game.sync(100.0)
    game.state.player.location = guan.join_at[0]
    assert feature.enabled(game)
    [join] = [o for o in game.options(odds=False) if o.id == "faction:guan"]
    assert feature.bot_pick(game, join) is None
    assert "不能改投" in game.choose(join.id)[0] and game.state.player.pending_faction == "guan"
    assert [o.id for o in game.options(odds=False)] == ["faction:confirm", "faction:cancel"]
    game.choose("faction:confirm")
    assert game.state.player.faction == "guan" and game.state.player.pending_faction is None
    assert "考慮投靠官軍" in [e.title for e in game.state.journal]
    game.state.player.location = huang.join_at[0]
    [defect] = [o for o in game.options(odds=False) if o.id.startswith("defect:huang")]
    assert feature.bot_pick(game, defect) is None
    game.choose(defect.id)
    assert game.state.player.pending_defect == "huang"
    game.choose("defect:cancel")
    assert game.state.player.pending_defect is None and game.state.player.faction == "guan"
