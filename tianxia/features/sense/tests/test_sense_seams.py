"""有所感包 actions.py 裡幾行接縫（全部拆包第 24 批審查）：走一趟停在卡上畫一筆、思名的得失記在那一段（outing_watch）、讀檔清掉作廢的卡、
畫完清掉引導與戰報卡、籌備中不開單、擲特殊頓悟乘走一趟的倍數。拿掉這幾行以前包的測試與混合檔都不會紅（審查的單點突變），
這裡走 Game 的公開方法守它們；same_behavior 的 sense 一軌也有同一批步驟。"""
from __future__ import annotations

import random
from unittest import mock

import pytest
from jianfa_kit import jianfa_game, ready

from tianxia import epiphany, explore_one, glyph, insights, journal, materials, sensing
from tianxia.core.services import PREPARING_REFUSAL
from tianxia.engine import Game
from tianxia.state import BattleRecord, GodNaming

PLACE = "yingshui"
LOOT = "精鐵砂 ×1"


def _game() -> Game:
    """week7 的散人站在潁水河畔、體力補滿；奇遇與頭目這一下不擲，選對做法一定擲中，特殊頓悟不中（要中的條自己開）。"""
    game = ready(jianfa_game("week7"), loc=PLACE)
    cfg = game.content.config
    cfg.rare_explore_chance, cfg.duel.explore_chance = 0.0, 0.0
    cfg.sense_rate_range, cfg.sense_marks_bonus = (100, 100), 0
    cfg.epiphany.chances = [0.0, 0.0, 0.0]
    game.state.player.stamina = 100.0
    return game


def _card(game: Game) -> None:
    """閒著撞上有所感（不在路上）。"""
    sensing.start(game.state, game.content, sensing.pick_scene(game.content.locations[PLACE], game.content, random.Random(0)), random.Random(0))
    assert game.state.player.sensing is not None


def _trip_on_the_card(game: Game):
    """走一趟三段，第一段就撞上有所感停下來：這一下選完的得失要記在那一段（outing_watched）。"""
    with mock.patch.object(explore_one, "draw", return_value=explore_one.INSIGHT):
        game.outing_go(3)
    trip = game.state.player.outing
    assert trip.beats[-1].stop and game.state.player.sensing is not None and not game.outing_can_go()
    return trip


def _pick_right(game: Game) -> None:
    """卡上選一個對的做法（擲中），進感悟狀態。"""
    s, c = game.state.player.sensing, game.content
    scene, pool = c.insight_scenes[s.scene], insights.pool_attributes(c.locations[s.location], c)
    game.choose(f"sense:{next(i for i, j in enumerate(s.order) if scene.methods[j].attribute in pool)}")
    assert game.state.player.sensing is not None and game.state.player.sensing.stage == "draw"


def _stroke_request(game: Game) -> sensing.SenseRequest:
    """畫一筆讀得出來的（A 段）。"""
    req = game.sense_request(glyph.SAMPLES[sorted(glyph.SAMPLES)[0]])
    assert not isinstance(req, str)
    return req


def _naming(game: Game) -> None:
    """心魔過了等著取名、還沒想過名字（那一個神品隨便挑；取名的選單要有，走一趟才算還停著）。"""
    god = next(iter(game.content.traits.god))
    p = game.state.player
    p.sensing = None
    p.god_naming = GodNaming(line="頓悟1", god=god.id, attribute=god.attribute, lean=god.lean, place=game.content.locations[PLACE].name)


# ── 走一趟停在卡上（outing_watch）──


def test_a_stroke_drawn_on_a_stopped_trip_keeps_its_gains_on_that_beat():
    """sense_draw 不經 choose，得失靠它自己掛的 outing_watch 記在那一段（一般的一筆沒有數值變化，這裡讓悟的那一下帶一筆料）。"""
    game = _game()
    trip = _trip_on_the_card(game)
    _pick_right(game)
    req = _stroke_request(game)
    real = sensing.finish

    def finish(*args, **kwargs):
        msgs, own, by_model = real(*args, **kwargs)
        return [*msgs, f"{materials.GRANT_PREFIX}{LOOT}"], own, by_model

    with mock.patch.object(sensing, "finish", finish):
        game.sense_draw(req, None)
    assert LOOT in trip.beats[-1].after


def test_names_thought_up_on_a_stopped_trip_keep_their_gains_on_that_beat():
    """epiphany_names 同一層：C 段那一下寫進紀錄的得失記在那一段。"""
    game = _game()
    trip = _trip_on_the_card(game)
    _naming(game)
    ask = game.epiphany_request()
    real = epiphany.fill

    def fill(state, *args, **kwargs):
        msgs = real(state, *args, **kwargs)
        journal.add_entry(state, journal.Draft("頓悟").entry(state.world.time, [f"{materials.GRANT_PREFIX}{LOOT}"]))
        return msgs

    with mock.patch.object(epiphany, "fill", fill):
        game.epiphany_names(ask, [])
    assert game.state.player.god_naming.asked and LOOT in trip.beats[-1].after


# ── 清失效參照（Review Focus 3：Game._drop_stale_references 中段）──


def test_a_card_left_behind_is_dropped_when_the_save_is_read():
    """人被帶走了（管理者挪人、內容改版）：下一次讀檔就清掉作廢的卡；不然 _idle 一直是假，店進不去、選單卡住。"""
    game = _game()
    _card(game)
    p = game.state.player
    p.location = next(i for i in sorted(game.content.locations) if i != PLACE)
    assert p.sensing is not None and sensing.current(game.state, game.content) is None
    again = Game(game.content, game.state, random.Random(0), game.world)
    assert again.state.player.sensing is None


# ── 畫完那一下（這條路不走 choose，choose 開頭清的那兩格要自己清）──


def test_finishing_a_stroke_clears_the_guide_lines_and_the_battle_card():
    game = _game()
    _card(game)
    _pick_right(game)
    req = _stroke_request(game)
    s = game.state
    s.player.guide_done = ["✔ 上一次行動完成的那一行"]
    record = BattleRecord(id=987654, time=s.world.time, location="潁水河畔", kind="wild", opponent="流寇", ours=[], tier="大勝", our_power=1, difficulty=1)
    s.battles.insert(0, record)
    s.battle_card = record.id
    assert game.battle_card_id() == record.id
    game.sense_draw(req, None)
    assert "✔ 上一次行動完成的那一行" not in s.player.guide_done
    assert s.battle_card is None and game.battle_card_id() is None
    assert s.player.sensing is None


# ── 賽季籌備中 ──


def test_while_the_season_prepares_a_stroke_is_refused():
    game = _game()
    _card(game)
    _pick_right(game)
    points = glyph.SAMPLES[sorted(glyph.SAMPLES)[0]]
    assert not isinstance(game.sense_request(points), str)
    with mock.patch.object(game.world, "season_phase", return_value="preparing"):
        assert game.sense_request(points) == PREPARING_REFUSAL


def test_while_the_season_prepares_no_names_are_asked_for():
    game = _game()
    _naming(game)
    assert game.epiphany_request() is not None
    with mock.patch.object(game.world, "season_phase", return_value="preparing"):
        assert game.epiphany_request() is None


# ── 擲特殊頓悟乘走一趟的倍數 ──


@pytest.mark.parametrize("on_a_trip", [True, False], ids=["走一趟", "不在路上"])
def test_the_god_roll_is_multiplied_by_the_trip(on_a_trip):
    """有所感擲中之後擲特殊頓悟：走一趟照這一趟幾段乘（Config.jianfa.outing_rare，探索包回答），不在路上是 1。"""
    game = _game()
    game.content.config.jianfa.outing_rare["3"] = 4.0
    if on_a_trip:
        _trip_on_the_card(game)
    else:
        _card(game)
    with mock.patch.object(epiphany, "roll", return_value=False) as roll:
        _pick_right(game)
    assert roll.call_args.kwargs["boost"] == (4.0 if on_a_trip else 1.0)
