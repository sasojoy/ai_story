"""翻地與爭搶：戰書（輿圖簡化設計 4.4、第九章第 13 條；PM 2026-10-20 第 1、2 條）——這一週在任的第 4 階、自己那一邊的進度到門檻、一邊一天
一張、時段挑最近的、下了那一塊凍結到打完、另一邊可以併進同一場；攻城戰打贏照推滿易手（分紅、冷卻）、打輸砍半；換天只作罷沒開成的；
投票與 22:00 公告結算拿掉了；軍令照「此刻進度最高的那一塊」列與記；救場。"""
from __future__ import annotations

import inspect

import pytest

import server
from conquest_kit import announce, conquest_game, go, join, win_sortie
from tianxia import atlas, bot_policy, conquest, conquest_day, orders, ranks, siege
from tianxia.engine import Game
from tianxia.state import Order

pytestmark = pytest.mark.slow  # 建 Game、載正式內容

NOW = 1_792_000_000.0


def _game(side="guan", loc="hilltop_wilds", name="沈浪", world=None, seated=True):
    game = go(join(conquest_game("season21", name=name, world=world), side), loc)
    game.now = NOW
    if world is not None:
        game.state.world = world.get_season()
    if seated:
        game.state.player.qualified = True
        game.state.world.seats[side] = [name]
    return game


def _fill(game, loc, side, value, who="先鋒"):
    conquest.push(game.state.world, game.content, loc, side, who, value, "attack")


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


def test_a_seated_rank4_letters_the_nearest_slot_and_freezes_the_block():
    game = _game()
    w, c = game.state.world, game.content
    assert ranks.rank_of(game.state) == ranks.SEAT_RANK
    _fill(game, "hilltop_wilds", "guan", 60)
    want = conquest_day.next_slot(w, c, NOW)
    msgs = game.conquest_letter("hilltop_wilds")
    (slot,) = game.state.world.conquest.schedule
    assert (slot.loc, slot.attackers, slot.by, slot.reasons) == ("hilltop_wilds", ["guan"], {"guan": "letter"}, {"guan": "沈浪"})
    assert (slot.key, slot.minute) == want and slot.status == "planned"
    assert slot.muster_at == pytest.approx(slot.at - c.config.conquest.muster_minutes * 60)
    assert any("下了戰書" in m and "荒丘" in m for m in msgs)
    w = game.state.world
    assert conquest.push_problem(w, c, "guan", "hilltop_wilds", "attack") == conquest.WHY_FROZEN
    assert any(r.text.startswith("沈浪替官軍下了戰書") for r in w.rumors)  # 只有真人會下戰書：具名
    assert w.conquest.day_log[-1].by == "letter" and w.conquest.letter_days["guan"] == conquest_day.day_key(NOW, c.config)
    assert any(e.title == "下戰書" for e in game.state.journal)
    _fill(game, "deep_mountain", "guan", 70)
    again = game.conquest_letter("deep_mountain")
    assert "今天已經下過戰書了" in again[0] and len(game.state.world.conquest.schedule) == 1  # 一邊一天一張


def test_only_a_seated_rank4_can_letter_and_only_past_the_threshold():
    game = _game(seated=False)
    _fill(game, "hilltop_wilds", "guan", 80)
    assert game.conquest_letter("hilltop_wilds") == ["（只有這一週在任的第 4 階才能下戰書。）"]
    seated = _game()
    _fill(seated, "hilltop_wilds", "guan", 59)
    assert seated.letter_problem("hilltop_wilds") == "進度要到 60 才能下戰書（此刻 59）"
    assert seated.state.world.conquest.schedule == []


def test_the_other_side_joins_the_same_siege():
    game = _game()
    _fill(game, "hilltop_wilds", "guan", 60)
    _fill(game, "hilltop_wilds", "huang", 65)
    game.conquest_letter("hilltop_wilds")
    game._save_season()
    rival = _game(side="huang", name="張角徒", world=game.world)
    msgs = rival.conquest_letter("hilltop_wilds")
    (slot,) = rival.state.world.conquest.schedule
    assert slot.attackers == ["guan", "huang"] and slot.by == {"guan": "letter", "huang": "letter"}
    assert any("併進" in m for m in msgs)
    assert any("也下了戰書" in r.text for r in rival.state.world.rumors)


def test_a_siege_win_flips_with_payouts_and_cooling():
    game = _game(side="huang", loc="nanyang_road")
    _fill(game, "nanyang_road", "huang", 70, who="沈浪")
    game.conquest_letter("nanyang_road")
    slot = game.state.world.conquest.schedule[0]
    _open(game, slot)
    battle = game.world.get_sieges()[0]
    assert battle.trend_start == 46  # 進度 70：往黃巾偏 4（戰局以官軍為正向）
    game.choose(next(o.id for o in game.options() if o.id.startswith("battle:join:huang")))
    _end(game, 10)
    w, c = game.state.world, game.content
    assert conquest.holder(w, c, "nanyang_road") == "huang" and conquest.cooling(w, c, "nanyang_road")
    assert conquest.bars(w, "nanyang_road") == {}
    (pay,) = [p for p in w.conquest.payouts if p.name == "沈浪"]
    assert (pay.silver, pay.exp, pay.fame, pay.top) == (200, 300, 20, True)
    assert conquest.push_problem(w, c, "huang", "nanyang_road", "hold") != conquest.WHY_FROZEN  # 打完就解凍（冷卻另算）


def test_a_siege_loss_halves_the_bar_and_unfreezes():
    game = _game(side="huang", loc="nanyang_road")
    _fill(game, "nanyang_road", "huang", 80)
    game.conquest_letter("nanyang_road")
    _open(game, game.state.world.conquest.schedule[0])
    _end(game, 60)  # 守將那一邊佔上風
    w, c = game.state.world, game.content
    assert conquest.holder(w, c, "nanyang_road") is None and conquest.bar(w, "nanyang_road", "huang") == 40
    assert conquest.push_problem(w, c, "huang", "nanyang_road", "attack") is None


def test_day_turn_only_voids_letters_that_never_opened():
    game = _game()
    w, c = game.state.world, game.content
    key = conquest_day.day_key(NOW, c.config)
    w.conquest.settled_key = key
    stale = announce(game, "hilltop_wilds", "guan")
    stale.key = key
    tomorrow = announce(game, "deep_mountain", "guan")
    tomorrow.key = key + 1  # 21:30 之後下的戰書排在下一天
    game.now = conquest_day.key_start(key + 1, c.config) + 60
    msgs = game._conquest_tick(save=False)
    assert stale.status == "void" and tomorrow.status == "planned"
    assert any("時辰已過" in m for m in msgs)
    assert [s.id for s in game.state.world.conquest.schedule] == [tomorrow.id]
    assert game.state.world.conquest.settled_key == key + 1


def test_votes_and_the_22_settle_are_gone():
    assert "conquest_vote" not in server.MAIN_ACTIONS and "conquest_letter" in server.MAIN_ACTIONS
    assert "conquest_settle_now" not in server.ADMIN_ACTIONS
    assert {"conquest_progress", "conquest_letter"} <= set(server.ADMIN_ACTIONS)
    assert not hasattr(Game, "conquest_vote")
    assert not any(hasattr(conquest_day, name) for name in ("tally", "plan", "merge", "settle", "settle_now", "commander_picks"))
    assert "conquest_letter" not in inspect.getsource(bot_policy)  # 假人不下戰書


def test_orders_list_and_credit_the_highest_block():
    game = _game(loc="deep_mountain")
    s, c = game.state, game.content
    order = Order(id="t:guan:siege:yingru", template="siege", faction="guan", week=orders.period_of(s, c), front="yingru",
                  quota=6, text="（測試）")
    s.world.orders.append(order)
    _fill(game, "hilltop_wilds", "guan", 30)
    _fill(game, "deep_mountain", "guan", 10)
    assert orders.siege_places(c, "guan", "yingru", s.world) == ["hilltop_wilds"]
    how = atlas.siege_how(s, c, order)
    assert "荒丘" in how and "嵩山深處" not in how
    win_sortie(game)  # 在嵩山深處打贏：不是最高的那一塊，記不到
    assert s.player.name not in order.progress
    go(game, "hilltop_wilds")
    win_sortie(game)
    assert order.progress.get(s.player.name) == 1


def test_admin_tools_flip_and_letter():
    game = _game()
    game.state.player.name = "Rayal"
    w, c = game.state.world, game.content
    game.admin_conquest_progress("hilltop_wilds", "guan", 100)
    w = game.state.world
    assert conquest.holder(w, c, "hilltop_wilds") == "guan" and conquest.cooling(w, c, "hilltop_wilds")
    game.admin_conquest_letter("runan_wilds", "guan")
    (slot,) = game.state.world.conquest.schedule
    assert slot.loc == "runan_wilds" and slot.muster_at == pytest.approx(game.state.world.time)
    assert "guan" not in game.state.world.conquest.letter_days  # 不算那一邊今天的那一張
