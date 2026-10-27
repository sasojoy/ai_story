"""7 天季領地爭奪調整（2026-10-22，計畫 docs/superpowers/plans/2026-10-22-7天季領地爭奪調整.md）的假人策略（開關關著一個字都不變）：

1. 出陣攻打看勝算（bot_policy._outmatched）：那裡出陣會打的幾路平均起來贏面不到 SORTIE_WIN_FLOOR 的地方不攻、不往那裡走（攻城軍令的地方
   也一樣；守城、護糧、打擊照走）。
2. 往這一邊最該推的那一塊走（bot_policy._focus_hop）：推得動、打得贏的目標裡這一邊的條最高的那幾塊；今天出陣用完了不去。

同一輪量到的兩個假人卡住的地方在 test_bot_policy_stuck.py。"""
from __future__ import annotations

import random

import pytest

from conquest_kit import conquest_game, go, join, plain_game, press
from tianxia import bot_policy, conquest, figures, orders
from tianxia.bot_runner import BotRunner
from tianxia.characters import open_characters
from tianxia.engine import Game, Option
from tianxia.state import BotProfile, Order

pytestmark = pytest.mark.slow  # 建 Game、載正式內容

TRAIN = Option(id="act:train", label="出陣・攻")


def _bot(game: Game, side: str) -> Game:
    game.state.player.bot = BotProfile(personality="普通", seed=7, faction=side, season_number=game.world.get_season_number())
    return game


def _odds(monkeypatch, word: str) -> None:
    """勝算一律寫 word（假人照它算贏面；不碰打起來的判定）。"""
    monkeypatch.setattr(Game, "odds", lambda self, squad_id, at=None: word)


def test_a_bot_does_not_attack_where_it_cannot_win(monkeypatch):
    game = _bot(go(join(conquest_game("week7", name="假官"), "guan"), "runan_wilds"), "guan")
    w, c, profile = game.state.world, game.content, game.state.player.bot
    assert conquest.push_problem(w, c, "guan", "runan_wilds", "attack") is None  # 推得動：只差打不打得贏
    assert game._sortie_foes(c.locations["runan_wilds"]) == ["nz_kuibing"]  # 只有中立駐軍（難度 65）
    _odds(monkeypatch, "必敗")
    assert bot_policy._outmatched(game, "runan_wilds")
    assert bot_policy.score(game, TRAIN, profile) is None
    assert bot_policy._train_value(game, profile) == 0.0
    _odds(monkeypatch, "有把握")
    assert not bot_policy._outmatched(game, "runan_wilds")
    assert bot_policy.score(game, TRAIN, profile) is not None
    assert bot_policy._train_value(game, profile) > 0


def test_the_win_chance_averages_every_foe_it_may_meet(monkeypatch):
    """荒丘站流寇散兵（8）與荒丘刀客（58），出陣照 Game.rng 挑一路：贏面是兩路的平均。"""
    game = _bot(go(join(conquest_game("week7", name="假官"), "guan"), "hilltop_wilds"), "guan")
    words = {"dipi": "穩勝", "nz_daoke": "必敗"}
    monkeypatch.setattr(Game, "odds", lambda self, squad_id, at=None: words[squad_id])
    assert game._sortie_foes(game.content.locations["hilltop_wilds"]) == ["dipi", "nz_daoke"]
    assert bot_policy._sortie_win(game, "hilltop_wilds") == pytest.approx((0.95 + 0.03) / 2)
    assert not bot_policy._outmatched(game, "hilltop_wilds")  # 一半機會碰上打得贏的那一路：照攻
    words["dipi"] = "五五波"
    assert bot_policy._sortie_win(game, "hilltop_wilds") == pytest.approx((0.5 + 0.03) / 2)
    assert bot_policy._outmatched(game, "hilltop_wilds")


def test_holding_its_own_block_needs_no_odds(monkeypatch):
    """守自家的塊不打仗：勝算再低也照守（不是 _outmatched）。"""
    game = _bot(go(join(conquest_game("week7", name="假官"), "guan"), "hilltop_wilds"), "guan")
    w, c = game.state.world, game.content
    conquest.set_control(w, c, "hilltop_wilds", "guan")
    press(game, "hilltop_wilds", "huang")  # 對面推了一截：守得動
    _odds(monkeypatch, "必敗")
    assert game.sortie_mode() == "hold"
    assert not bot_policy._outmatched(game, "hilltop_wilds")
    assert bot_policy.score(game, TRAIN, game.state.player.bot) is not None


def _siege_order(game: Game, side: str, front: str) -> None:
    s, c = game.state, game.content
    s.world.orders.clear()
    s.world.orders.append(Order(id=f"t:{side}:siege", template="siege", faction=side, week=orders.period_of(s, c), front=front,
                                quota=99, text="（測試）"))


def test_a_siege_order_does_not_lead_a_bot_to_a_block_it_cannot_win(monkeypatch):
    game = _bot(go(join(conquest_game("week7", name="假官"), "guan"), "changshe"), "guan")
    _siege_order(game, "guan", "yingru")
    places = orders.targets(game.state, game.content, "guan")
    assert places  # 攻城的地方（潁川汝南這一條線上推得動的目標）
    _odds(monkeypatch, "必敗")
    assert bot_policy._order_hop(game) is None  # 打不贏：不往那裡走
    _odds(monkeypatch, "穩勝")
    assert bot_policy._order_hop(game) is not None  # 打得贏：照舊往攻城的地方走


def test_a_defend_order_still_leads_the_bot_even_when_it_is_weak(monkeypatch):
    """守城不靠出陣攻打：勝算再低也照走（自家被推得最高的那一塊）。"""
    game = _bot(go(join(conquest_game("week7", name="假官"), "guan"), "changshe"), "guan")
    s, c = game.state, game.content
    conquest.set_control(s.world, c, "hilltop_wilds", "guan")
    press(game, "hilltop_wilds", "huang")
    s.world.orders.clear()
    s.world.orders.append(Order(id="t:guan:defend", template="defend", faction="guan", week=orders.period_of(s, c), front="yingru",
                                quota=99, text="（測試）"))
    assert orders.targets(s, c, "guan") == ["hilltop_wilds"]
    _odds(monkeypatch, "必敗")
    assert bot_policy._order_hop(game) is not None


def test_a_strike_order_still_leads_the_bot_to_a_figure_standing_on_a_block_it_cannot_take(monkeypatch):
    """打擊軍令是去挑戰人物本人（看的是挑戰的勝算），不是在那一塊出陣：人物站在打不贏駐軍的中立地，照樣往那裡走。"""
    game = _bot(go(join(conquest_game("week7", name="假官"), "guan"), "changshe"), "guan")
    s, c = game.state, game.content
    fid = next(f for f, d in c.figures.items() if d.faction == "huang")
    s.world.figures[fid] = figures.state_of(s, c, fid).model_copy(update={"location": "runan_wilds", "status": "active"})
    s.world.orders.clear()
    s.world.orders.append(Order(id="t:guan:strike", template="strike", faction="guan", week=orders.period_of(s, c), figure=fid,
                                quota=99, text="（測試）"))
    assert orders.targets(s, c, "guan") == ["runan_wilds"]
    _odds(monkeypatch, "必敗")
    assert bot_policy._outmatched(game, "runan_wilds")
    assert bot_policy._order_hop(game) is not None


def test_pick_remembers_the_order_hop_only_inside_one_pick(monkeypatch):
    """同一輪 pick 裡每個前往鈕都問一次軍令要去哪：只算一次；pick 外照舊每次算。"""
    game = _bot(go(join(conquest_game("week7", name="假官"), "guan"), "changshe"), "guan")
    calls = []
    real = bot_policy._order_hop_now
    monkeypatch.setattr(bot_policy, "_order_hop_now", lambda g: calls.append(1) or real(g))
    options = [o for o in game.options(odds=False) if o.enabled and o.id.startswith("move:")]
    assert len(options) >= 2
    bot_policy.pick(game, options, game.state.player.bot, random.Random(0))
    assert len(calls) == 1 and bot_policy._TURN is None
    bot_policy._order_hop(game)
    bot_policy._order_hop(game)
    assert len(calls) == 3


def test_a_bot_heads_for_the_block_its_side_has_pushed_furthest(monkeypatch):
    """宛城往南陽官道、南陽郊野、淯水河畔、綠林山寨各有一條路：都沒人推時往最近的走；官軍在綠林山寨推了一截，就往綠林山寨走。"""
    game = _bot(go(join(conquest_game("week7", name="假官"), "guan"), "wan_city"), "guan")
    w, c = game.state.world, game.content
    _odds(monkeypatch, "穩勝")
    nearest = bot_policy.next_hop(game, [loc for loc in conquest.blocks(c) if conquest.push_problem(w, c, "guan", loc, "attack") is None])
    assert bot_policy._focus_hop(game) == nearest
    assert bot_policy.next_hop(game, ["lulin_zhai"]) == "lulin_zhai" != nearest
    press(game, "lulin_zhai", "guan", 20, name="先鋒")
    assert bot_policy._focus_hop(game) == "lulin_zhai"
    move = next(o for o in game.options(odds=False) if o.id.partition(":")[2].partition(":")[0] == "lulin_zhai")
    other = next(o for o in game.options(odds=False) if o.id.startswith("move:") and o.id != move.id)
    profile = game.state.player.bot
    assert bot_policy.score(game, move, profile) >= bot_policy.score(game, other, profile) + bot_policy.FOCUS_MOVE_SCORE - 1


def test_the_focus_skips_a_higher_block_the_bot_cannot_win(monkeypatch):
    """條最高的那一塊打不贏，就去打得贏的裡面條最高的（勝算照「條高的先、近的先」一塊一塊問，問到打得贏的為止）。"""
    game = _bot(go(join(conquest_game("week7", name="假官"), "guan"), "wan_city"), "guan")
    press(game, "lulin_zhai", "guan", 30, name="先鋒")
    press(game, "nanyang_wilds", "guan", 10, name="先鋒")
    asked = []

    def odds(self, squad_id, at=None):
        asked.append(at)
        return "必敗" if at == "lulin_zhai" else "穩勝"

    monkeypatch.setattr(Game, "odds", odds)
    assert bot_policy._focus_hop(game) == "nanyang_wilds"
    assert set(asked) == {"lulin_zhai", "nanyang_wilds"}  # 條是 0 的那幾塊不必問


def test_bot_games_share_one_odds_memo():
    """假人程式每一下重建 Game：勝算的記憶掛在 BotRunner 上一份，一輪一輪共用（同 server.ODDS_MEMO）。"""
    game = conquest_game("week7", name="假官")
    runner = BotRunner(game.content, game.world, open_characters(game.world.db.path), random.Random(1), clock=lambda: 0.0)
    first, second = runner._bot_game(game.state), runner._bot_game(game.state)
    assert first is not second and first.odds_memo is second.odds_memo is runner.odds_memo is not None


def test_no_focus_when_the_sorties_are_spent_or_the_bot_cannot_win(monkeypatch):
    game = _bot(go(join(conquest_game("week7", name="假官"), "guan"), "wan_city"), "guan")
    press(game, "lulin_zhai", "guan", 20, name="先鋒")
    _odds(monkeypatch, "必敗")
    assert bot_policy._focus_hop(game) is None  # 哪一塊都打不贏
    _odds(monkeypatch, "穩勝")
    assert bot_policy._focus_hop(game) == "lulin_zhai"
    monkeypatch.setattr(Game, "sorties_left", lambda self: 0)
    assert bot_policy._focus_hop(game) is None  # 今天出陣用完：去練功，不往那裡跑
    off = _bot(go(join(plain_game("week7", name="假官"), "guan"), "wan_city"), "guan")
    assert bot_policy._focus_hop(off) is None  # 開關關著

