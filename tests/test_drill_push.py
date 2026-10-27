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

from conftest import classic_rules, real_content


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
    content = classic_rules(real_content(profile))  # 測的是操練（出陣探索與地盤之前的遊歷），四個開關都關掉
    content.config.auto_open_first_season = True
    content.config.train_event_chance = 0.0
    return content


def test_the_scales_follow_the_season_length_on_the_seal(tmp_path):
    """季長倍數（season_scale）＝min(1, 基準季長 ÷ 這一季蓋章的季長)：週末設定 1，14 天 2.5／14，季長比基準短也不放大。
    操練的倍數（drill_scale）在季長倍數小於 1 時再乘 drill_long_season_share（0.5，PM 2026-10-12）：14 天約 0.09；週末設定照舊 1。"""
    fourteen = _camp(_content(), open_world(tmp_path / "beta.db"))
    assert fourteen.season_scale() == pytest.approx(2.5 / 14)
    assert fourteen.drill_scale() == pytest.approx(2.5 / 14 * 0.5)
    fourteen.state.world.length_days = 1.0
    assert fourteen.season_scale() == fourteen.drill_scale() == 1.0


def test_drills_in_a_fourteen_day_season_push_a_scaled_amount_and_carry_the_fraction():
    """14 天的季：每次操練推 2 × 2.5／14 × 0.5 ≈ 0.179，零頭記在 trend_accum，滿一點才推一點、才寫「（黃巾聲勢 +1）」；
    三十次操練一共推 int(30 × 0.179) ＝ 5 點，不是以前的 60。經驗、心得照給。"""
    content = _content()
    assert not content.config.season_one
    game = _camp(content)
    before = world_trend_value(game.state.world, content, "huangjin")
    xinde = game.state.player.stats.get("xinde", 0)
    step = 2 * 2.5 / 14 * 0.5
    said = 0
    for i in range(1, 31):
        msgs = _drill(game)
        moved = world_trend_value(game.state.world, content, "huangjin") - before
        # 零頭照 push.take_whole 存到小數第 9 位（同推力緩衝），剛好落在整數上的那一下可能晚一下才滿一點
        assert int(i * step - 1e-6) <= moved <= int(i * step + 1e-9), (i, moved)
        pushed = [m for m in msgs if "黃巾聲勢" in m]
        assert pushed == (["（黃巾聲勢 +1）"] if moved > said else []), (i, msgs)  # 沒推到整點不寫推動那一行
        said = moved
        assert game.state.world.trend_accum.get("huangjin", 0.0) == pytest.approx(i * step - moved, abs=1e-6)
    assert world_trend_value(game.state.world, content, "huangjin") == before + 5
    assert not game.state.world.ended
    assert game.state.player.stats.get("xinde", 0) > xinde


def _sight(game, trend: dict[str, int]) -> list[str]:
    """一則事件的大勢效果，照玩家選事件那一條路（rules.apply_effect 交給 Game.push_trend，source="event"）。"""
    from tianxia.models import Effect
    from tianxia.rules import apply_effect

    return apply_effect(Effect(trend=trend), game.state, game.content, game.world, push=game.push_trend)


def test_event_pushes_in_a_fourteen_day_season_follow_the_season_scale_and_carry_the_fraction():
    """規則關著的季，事件的大勢效果照季長縮放（同一個季長倍數，不再另打折）：每一則推 2 × 2.5／14 ≈ 0.357，零頭跟操練
    記在同一個 trend_accum（正負抵銷），滿一點才推、才寫推動那一行。"""
    content = _content()
    game = _camp(content)
    game.state.player.location = "yingchuan"
    before = world_trend_value(game.state.world, content, "huangjin")
    step = 2 * 2.5 / 14
    said = 0
    for i in range(1, 11):
        msgs = _sight(game, {"front": 2})
        moved = world_trend_value(game.state.world, content, "huangjin") - before
        assert int(i * step - 1e-6) <= moved <= int(i * step + 1e-9), (i, moved)
        assert [m for m in msgs if "黃巾聲勢" in m] == (["（黃巾聲勢 +1）"] if moved > said else []), (i, msgs)
        said = moved
    assert moved == 3  # 十則 × 0.357 ＝ 3.57，不是以前的 20
    _sight(game, {"front": -2})  # 往回推的抵掉零頭：0.57 − 0.357 ＝ 0.21，不動
    assert world_trend_value(game.state.world, content, "huangjin") == before + 3
    assert game.state.world.trend_accum["huangjin"] == pytest.approx(10 * step - 3 - step, abs=1e-6)


def test_the_first_push_that_reveals_a_hidden_line_is_not_scaled():
    """隱藏線（玉璽碎片線索）照舊只在正向推進時浮現：浮現的那一下照原本的量推、照舊寫浮現那一句，之後才照季長縮放。"""
    content = _content()
    game = _camp(content)
    assert "yuxi" not in game.state.world.revealed
    msgs = _sight(game, {"yuxi": 2})
    assert game.state.world.trends["yuxi"] == 2 and "yuxi" in game.state.world.revealed
    assert any("浮上檯面" in m for m in msgs)
    _sight(game, {"yuxi": 2})
    assert game.state.world.trends["yuxi"] == 2  # 0.357，還不到一點


def test_a_once_a_season_event_pushes_its_full_amount_in_a_fourteen_day_season():
    """FB-166（PM 2026-10-13）：規則關著的季，一季只會發生一次的事件不照季長縮放——季再長也不會多發生一次。照內容判斷：效果這一下
    新立世界旗標（例：擊敗波才立 bocai_defeated，-25 以前被縮成 -4）、或事件標了 once，照原本的量推；其餘照舊縮放。
    旗標早就立了的再立一次不算（那不是這一季的第一次）。"""
    from tianxia.models import Effect
    from tianxia.rules import apply_effect

    content = _content()
    game = _camp(content)
    game.state.player.location = "yingchuan"
    w = game.state.world
    w.trends["huangjin"] = 60
    boss = content.events["kou_boss"].choices[0].effect
    assert boss.trend == {"front": -25} and boss.world_flags_add == ["bocai_defeated"]
    apply_effect(boss, game.state, content, game.world, push=game.push_trend)
    assert world_trend_value(w, content, "huangjin") == 35 and "bocai_defeated" in w.flags  # 照推 -25，不是 -4
    again = Effect(trend={"front": 2}, world_flags_add=["bocai_defeated"])  # 旗標已經立了：照舊縮放（0.357，不到一點）
    apply_effect(again, game.state, content, game.world, push=game.push_trend)
    assert world_trend_value(w, content, "huangjin") == 35
    apply_effect(Effect(trend={"front": 2}), game.state, content, game.world, push=game.push_trend, once=True)  # 事件標了 once
    assert world_trend_value(w, content, "huangjin") == 37
    _sight(game, {"front": 2})  # 一般可重複的事件照舊縮放
    assert world_trend_value(w, content, "huangjin") == 37


def test_once_events_reach_the_effect_unscaled_through_the_game():
    """Game 選事件那一條路把事件的 once 帶給 apply_effect（_choose、劇情戰、隨口應對都是）：一次性事件的選項照原本的量推。"""
    content = _content()
    once = next(e for e in content.events.values() if e.once and any(
        ch.effect.trend and not ch.check and not ch.combat and not ch.effect.world_flags_add for ch in e.choices))
    index = next(i for i, ch in enumerate(once.choices)
                 if ch.effect.trend and not ch.check and not ch.combat and not ch.effect.world_flags_add)
    from tianxia.rules import resolve_trends

    game = _camp(content)
    w = game.state.world
    for t in list(w.trends):
        w.trends[t] = 50  # 離兩頭都遠，照原本的量推不會被夾
    want = {t: d for t, d in resolve_trends(content, w, once.choices[index].effect.trend, game.state.player.location).items() if d}
    before = dict(w.trends)
    game.state.pending_event = once.id
    game._choose(index)
    pushed = {t: v - before.get(t, 0) for t, v in w.trends.items() if v != before.get(t, 0)}
    assert pushed == want, (once.id, pushed, want)  # 照原本的量，不是乘 2.5／14


def test_train_wins_in_a_fourteen_day_season_follow_the_season_scale():
    """企劃者 2026-10-13（FB-168）：遊歷打贏推的大勢在長季也照季長縮放（同 season_scale，零頭記在同一個 trend_accum），不然兩天裡
    兩邊的遊歷就能把黃巾聲勢從 25 推到 60 或砸到 0（量表：-110～+56）。每一下 -2 × 2.5／14 ≈ -0.357，十下動 3 點。"""
    content = _content()
    game = _camp(content)
    w = game.state.world
    w.trends["huangjin"] = 50
    for _ in range(10):
        game.push_trend("huangjin", -2, source="train")
    assert world_trend_value(w, content, "huangjin") == 47
    assert w.trend_accum["huangjin"] == pytest.approx(-(10 * 2 * 2.5 / 14 - 3), abs=1e-6)


def test_train_wins_in_the_weekend_season_are_unchanged():
    """第一季規則開著（週末設定）：遊歷打贏推的大勢一個字都不變（推力緩衝與上限照舊、沒有季長倍數）。"""
    content = _content("week7")
    game = _camp(content)
    game.state.player.location = "yingchuan"
    before = game.state.world.trends["yingru"]
    game.push_trend("yingru", 2, source="train")
    assert game.state.world.trends["yingru"] == before + 2
