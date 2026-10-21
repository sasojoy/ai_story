"""FB-605（flip-1 收尾開發回報，PM 2026-10-21 給號；QA 驗輿圖第三版第 1 批照樣重現）：自家那一塊被戰書凍結時，守城卡寫「此刻沒有可守的」。

翻地之後守城軍令只認「自家被推得最高、守得動」的那幾塊（orders.defend_places → conquest.focus_blocks(…, "defend")），被戰書凍結的那一塊
push_problem 回凍結的原因、守不動，所以不列——可是那一塊正等著一場攻城，正是最該守的地方。PM 定的修法：凍結的那一塊照樣列進守城
（列與記同一個判斷），在那一場攻城戰站守方、守方守住時記一次（orders.SIEGE_GUARD）；在那裡出陣守、按守勢行動不算（守不動進度）。"""
from __future__ import annotations

import pytest

from conquest_kit import announce, conquest_game, go, join, press
from tianxia import atlas, conquest, mapdata, orders, siege
from tianxia.state import Order

pytestmark = pytest.mark.slow  # 建 Game、載正式內容

NOW = 1_792_000_000.0


def _game(name: str = "沈浪", world=None):
    """黃巾的人站在汝南（黃巾開季的陣營區塊）；官軍在那裡推到 60、下了戰書（announce：排進時程表＝那一塊被凍結）。開季的軍令清掉，
    只剩一道黃巾潁川汝南的守城。"""
    game = go(join(conquest_game("season21", name=name, world=world), "huang"), "runan")
    game.now = NOW
    if world is not None:
        game.state.world = world.get_season()
    return game


def _setup(game):
    s, c = game.state, game.content
    s.world.orders.clear()
    order = Order(id="t:huang:defend", template="defend", faction="huang", week=orders.period_of(s, c), front="yingru",
                  quota=99, text="（測試）")
    s.world.orders.append(order)
    press(game, "runan", "guan", 60)
    slot = announce(game, "runan", "guan")
    return order, slot


def _open(game, slot):
    w = game.state.world
    slot.muster_at, slot.at, slot.status = w.time, w.time + 1800, "waiting"
    game._save_season()
    siege.open_waiting(game.world, game.content, NOW)
    game.state.world = game.world.get_season()


def _end(game, trend):
    battle = next(b for b in game.world.get_sieges() if b.phase != "ended")

    def _close(b):
        b.phase, b.trend, b.end_time = "ended", trend, game.state.world.time

    game._apply_battle_outcome(game.world.mutate_siege(battle.record_id, _close))
    game.state.world = game.world.get_season()


def _order(game) -> Order:
    return next(o for o in game.state.world.orders if o.id == "t:huang:defend")


def test_a_frozen_own_block_is_listed_for_defend_on_the_card_map_and_bots():
    game = _game()
    order, _ = _setup(game)
    c, w = game.content, game.state.world
    assert conquest.push_problem(w, c, "huang", "runan", "hold") == conquest.WHY_FROZEN  # 守不動進度（規則沒變）
    assert orders.defend_places(c, w, order) == ["runan"]  # 修前是空的
    text = atlas.order_how(game.state, c, order)
    assert text != atlas.DEFEND_NONE_CONQUEST.format(front=atlas.trend_name(c, "yingru"))  # 修前「此刻沒有…沒有可守的」
    assert text == atlas.DEFEND_SIEGE_CONQUEST.format(where="汝南")
    assert mapdata._order_marks(game.state, c, "huang").get("runan") == mapdata.ORDER_WORDS["defend"]
    assert "runan" in orders.targets(game.state, c, "huang")


def test_on_the_frozen_block_only_the_siege_guard_counts():
    """列與記同一個判斷：凍結的那一塊在清單上，記的是攻城戰守住；在那裡出陣守、按守勢行動不算（守不動），別的守城地方反過來只認那兩種。"""
    game = _game()
    order, _ = _setup(game)
    c, w = game.content, game.state.world
    press(game, "runan_academy", "guan", 10)  # 另一塊自家的地方被推：照舊是出陣守、守勢行動的地方
    assert orders.defend_places(c, w, order) == ["runan", "runan_academy"]

    def counts(kind, loc):
        return orders._counts(c, order, kind, loc, None, None, None, None, None, w)

    assert counts(orders.SIEGE_GUARD, "runan") and not counts("duty", "runan")
    assert counts("duty", "runan_academy") and not counts(orders.SIEGE_GUARD, "runan_academy")
    assert not orders.duty_counts(game.state, c, "huang", "runan") and orders.duty_counts(game.state, c, "huang", "runan_academy")
    text = atlas.order_how(game.state, c, order)
    assert "汝南學宮" in text and "汝南正等著一場攻城" in text


def test_a_hold_sortie_on_the_frozen_block_does_not_count():
    game = _game()
    order, _ = _setup(game)
    game.choose("act:train")  # 自家的區塊：出陣・守（凍結，推不動）
    assert _order(game).progress == {}


def test_defenders_who_hold_the_siege_get_one_credit_each():
    game = _game()
    order, slot = _setup(game)
    other = _game(name="張角徒", world=game.world)  # 同一邊、沒去打的人
    _open(game, slot)
    game.choose(next(o.id for o in game.options() if o.id.startswith("battle:join:huang")))
    _end(game, 10)  # 戰局往黃巾（守方）那一邊：守住
    w, c = game.state.world, game.content
    assert conquest.holder(w, c, "runan") == "huang" and conquest.frozen(w, "runan") is None
    assert _order(game).progress == {"沈浪": 1}  # 修前沒有記：卡上寫沒有可守的、攻城戰也不記
    assert "張角徒" not in _order(game).progress
    assert other.state.player.name == "張角徒"


def test_no_credit_when_the_block_falls():
    game = _game()
    order, slot = _setup(game)
    _open(game, slot)
    game.choose(next(o.id for o in game.options() if o.id.startswith("battle:join:huang")))
    _end(game, 90)  # 官軍拿下
    w, c = game.state.world, game.content
    assert conquest.holder(w, c, "runan") == "guan"
    assert _order(game).progress == {}


def test_a_ranger_helping_the_defence_is_not_credited():
    """臨時投效、助守的散人只算這一場：不記軍令（他沒有陣營，也不能記到黃巾的軍令上）。"""
    game = _game()
    order, slot = _setup(game)
    ranger = go(join(conquest_game("season21", name="浪人", world=game.world), None), "runan")
    ranger.now = NOW
    _open(game, slot)
    ranger.state.world = ranger.world.get_season()
    joins = [o.id for o in ranger.options() if o.id.startswith("battle:") and "huang" in o.id and o.enabled]
    assert joins, [o.id for o in ranger.options() if o.id.startswith("battle:")]
    ranger.choose(joins[0])
    _end(game, 10)
    assert "浪人" not in _order(game).progress
