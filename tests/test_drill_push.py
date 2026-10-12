"""FB-165：操練推的大勢照季長縮放（企劃者 2026-10-12：「14 天賽季甚至是真正的賽季，操練給的聲勢就不該那麼大佔比，
要隨著賽季長度而調整」）。

操練（在自己陣營的隊伍那裡遊歷，Game._drill）不會輸、不扣氣血；14 天的季（第一季規則關著）推力沒有人數緩衝、也沒有每人
每曆日的上限，三條戰線又都換算成黃巾聲勢——黃巾三個投靠點一次 +2，開局 250 體力連點三十下就把聲勢從 25 推到 80、
以「黃巾稱霸」收掉一整季。現在每次操練推 train_trend × min(1, Config.drill_push_base_days ÷ 這一季的季長)：週末設定
（2.5 天）是 1、一個字都不變；14 天約 0.18。不足一點的記在這一季的 WorldState.trend_accum，滿一點才真的推；
沒推到整點的那一下不寫推動那一行。"""
import random

import pytest

from tianxia.engine import Game
from tianxia.rules import world_trend_value
from tianxia.sqlite_world import open_world

from conftest import real_content


def _camp(content, world=None, name="黃巾甲"):
    """略過序章、投靠黃巾、站在黃巾別部營寨（那裡的隊伍都是黃巾：遊歷＝操練，train_trend 潁川汝南 -2），體力滿。
    world 不給就開預設的那一個（同一個測試要開兩種季時各給一個，不然第二個會接上第一個開的季）。"""
    game = Game.new(content, name, rng=random.Random(0), world=world or open_world(), prologue=True)
    game.client = None
    game.skip_tutorial()
    p = game.state.player
    p.faction, p.location, p.stamina = "huang", "huangjin_camp", float(content.config.stamina_max)
    return game


def _drill(game) -> list[str]:
    msgs = game.choose("act:train")
    assert any("操軍擺陣" in m for m in msgs), msgs
    return msgs


def _content(profile=None):
    content = real_content(profile)
    content.config.auto_open_first_season = True
    content.config.train_event_chance = 0.0
    return content


def test_the_drill_scale_follows_the_season_length_on_the_seal(tmp_path):
    """倍數＝min(1, 基準季長 ÷ 這一季蓋章的季長)：週末設定 1，14 天 2.5／14，季長比基準短也不放大。"""
    week_end = _camp(_content("weekend"), open_world(tmp_path / "weekend.db"))
    fourteen = _camp(_content(), open_world(tmp_path / "beta.db"))
    assert week_end.drill_scale() == 1.0
    assert fourteen.drill_scale() == pytest.approx(2.5 / 14)
    fourteen.state.world.length_days = 1.0
    assert fourteen.drill_scale() == 1.0


def test_drills_in_a_fourteen_day_season_push_a_scaled_amount_and_carry_the_fraction():
    """14 天的季：每次操練推 2 × 2.5／14 ≈ 0.357，零頭記在 trend_accum，滿一點才推一點、才寫「（黃巾聲勢 +1）」；
    三十次操練一共推 int(30 × 0.357) ＝ 10 點，不是以前的 60。經驗、心得照給。"""
    content = _content()
    assert not content.config.season_one
    game = _camp(content)
    before = world_trend_value(game.state.world, content, "huangjin")
    xinde = game.state.player.stats.get("xinde", 0)
    step = 2 * 2.5 / 14
    said = 0
    for i in range(1, 31):
        msgs = _drill(game)
        moved = world_trend_value(game.state.world, content, "huangjin") - before
        # 零頭照 push.take_whole 存到小數第 9 位（同推力緩衝），剛好落在整數上的那一下可能晚一下才滿一點
        assert int(i * step - 1e-6) <= moved <= int(i * step + 1e-9), (i, moved)
        pushed = [m for m in msgs if "黃巾聲勢" in m]
        assert pushed == (["（黃巾聲勢 +1）"] if moved > said else []), (i, msgs)  # 沒推到整點不寫推動那一行
        said = moved
        assert game.state.world.trend_accum.get("huangjin", 0.0) == pytest.approx(i * step - moved)
    assert world_trend_value(game.state.world, content, "huangjin") == before + 10
    assert not game.state.world.ended
    assert game.state.player.stats.get("xinde", 0) > xinde


def test_drills_in_the_weekend_season_push_as_before_and_stop_at_the_daily_cap():
    """週末設定（第一季規則開著、季長 2.5 天）：倍數 1，操練照舊一次推潁川汝南 2，一個人一個曆日最多推 daily_push_cap。"""
    content = _content("weekend")
    game = _camp(content)
    assert game.state.world.season_one and game.drill_scale() == 1.0
    before = game.state.world.trends["yingru"]
    _drill(game)
    assert game.state.world.trends["yingru"] == before + 2
    for _ in range(20):
        _drill(game)
    assert game.state.world.trends["yingru"] - before == content.config.daily_push_cap
