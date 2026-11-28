"""門派論劍：報名、抽籤（師兄補位、單數對試劍客、沒人報名不出場）、開打、賞（一次）、禮匣、假人（正式內容 season21）。"""
from __future__ import annotations

from lunjian_kit import season21_game, seat, to

from tianxia.core.option import Option
from tianxia.features.lunjian import actions, bots, checks, rules


def _week(game):
    return actions.week_of(game, actions._week(game), make=True)


def _fight(game):
    to(game, actions.fight_at(game, actions._week(game)) + 1)
    actions.on_sync(game)
    return _week(game)


def _strong(game, k: float = 5.0):
    """自己那一份分身放大 k 倍（三場穩贏）。"""
    me = _week(game).entries[game._mall_owner()]
    me.kit.power *= k
    me.kit.hp_cap *= k
    me.kit.scores = {m: v * k for m, v in me.kit.scores.items()}
    return me


def test_sign_needs_a_sect_and_closes_at_the_draw():
    game = season21_game(sect="")
    game.state.player.sect = None
    assert not any(o.id == "lunjian:sign" for o in game.options())
    assert actions.act(game, "sign") == [actions.NO_SECT]
    game.state.player.sect = "baima"
    assert any(o.id == "lunjian:sign" for o in game.options())
    out = actions.act(game, "sign")
    assert "白馬寺" in out[0] and "截止" in out[0]
    assert actions.act(game, "sign") == [actions.RESIGNED]
    assert next(o for o in game.options() if o.id == "lunjian:sign").label == actions.RESIGN_LABEL
    to(game, actions.draw_at(game, actions._week(game)))
    assert not any(o.id == "lunjian:sign" for o in game.options())
    assert actions.act(game, "sign") == [actions.CLOSED]


def test_the_draw_fills_with_elders_and_orders_weak_to_strong():
    game = season21_game()
    actions.act(game, "sign")
    w = _week(game)
    w.entries["甲"] = seat("甲", "nanhua", 40)
    for n, p in (("乙", 10), ("丙", 90), ("丁", 50), ("戊", 70)):
        w.entries[n] = seat(n, "songyang", p)
    w = _fight(game)
    assert w.drawn and w.fought and len(w.matches) == 2
    by = {m.a: m for m in w.matches} | {m.b: m for m in w.matches if m.b}
    song = by["songyang"]
    seats = song.seats_a if song.a == "songyang" else song.seats_b
    assert [s.name for s in seats] == ["丁", "戊", "丙"]  # 取最高三位（乙落選），由弱到強
    nan = by["nanhua"]
    mine = nan.seats_a if nan.a == "nanhua" else nan.seats_b
    assert sum(1 for s in mine if not s.key) == 2 and all(s.name.endswith("師兄") for s in mine if not s.key)
    assert [s.kit.power for s in mine] == sorted(s.kit.power for s in mine)
    # 三門：多出來的那一門對試劍客
    odd = next(m for m in w.matches if m.b == "")
    assert all(s.name.startswith("江湖試劍客") for s in odd.seats_b)
    assert all(len(m.bouts) == 3 for m in w.matches)


def test_elders_are_the_median_of_all_entries_times_the_share():
    entries = [seat(n, "nanhua", p) for n, p in (("甲", 10), ("乙", 30), ("丙", 50))]
    power, like = rules.elder_power(entries, 0.9)
    assert power == 27.0 and like.name == "乙"
    kit = rules.elder_kit("某師兄", power, like)
    assert kit.power == 27.0 and kit.kit is None and kit.arts == []


def test_sects_nobody_signed_sit_out_and_an_empty_week_just_closes():
    game = season21_game()
    _week(game)  # 有這一週、沒人報名
    w = _fight(game)
    assert w.fought and w.matches == []
    assert all("論劍" not in r.text for r in game.state.world.chronicle)


def test_pairs_avoid_last_weeks_pair_when_they_can():
    sects = ["a", "b", "c", "d"]
    first = rules.pair_up(sects, set(), 1, 1)
    again = rules.pair_up(sects, {frozenset(p) for p in first}, 1, 2)
    assert not {frozenset(p) for p in first} & {frozenset(p) for p in again}


def test_best_of_three_and_the_captain_breaks_a_tie():
    from tianxia.state import LunjianBout, LunjianMatch

    def m(*tiers):
        x = LunjianMatch(a="a", b="b", bouts=[LunjianBout(seat=i, tier=t) for i, t in enumerate(tiers)])
        sa = sum(rules.SCORE[b.tier] for b in x.bouts)
        sb = sum(rules.SCORE[rules.FLIP[b.tier]] for b in x.bouts)
        if sa == sb:
            last = x.bouts[-1].tier
            sa, sb = (1, 0) if last in rules.WIN_TIERS else (0, 1) if last == "落敗" else (0, 0)
        return "a" if sa > sb else "b" if sb > sa else ""

    assert m("大勝", "落敗", "險勝") == "a"
    assert m("大勝", "落敗", "僵持") == ""
    assert m("僵持", "僵持", "險勝") == "a"


def test_a_sweep_gives_one_top_box_the_seal_and_a_pick_once():
    game = season21_game()
    actions.act(game, "sign")
    _strong(game)
    for n, p in (("甲", 5), ("乙", 6), ("丙", 7)):
        _week(game).entries[n] = seat(n, "nanhua", p)
    w = _fight(game)
    m = w.matches[0]
    side = rules.side_of(m, game._mall_owner())
    assert m.winner == side and rules.sweep(m, side)
    b = game.state.player.lunjian
    assert (b.picks, b.boxes, b.top_boxes) == (1, 0, 1)
    assert actions.status(game)["lunjian"]["seal"] == actions.SEAL
    assert game.state.journal[0].title == actions.TITLE
    actions.on_sync(game)  # 再同步一次不重給
    assert (b.picks, b.top_boxes) == (1, 1)
    to(game, b.seal_until)
    assert actions.status(game)["lunjian"]["seal"] == ""


def test_elders_and_guests_get_nothing_and_losers_get_no_box():
    game = season21_game()
    actions.act(game, "sign")
    _strong(game, 0.01)
    for n, p in (("甲", 500), ("乙", 600), ("丙", 700)):
        _week(game).entries[n] = seat(n, "nanhua", p)
    w = _fight(game)
    b = game.state.player.lunjian
    assert w.matches[0].winner and w.matches[0].winner != rules.side_of(w.matches[0], game._mall_owner())
    assert b is None or (b.boxes, b.top_boxes, b.picks) == (0, 0, 0)


def test_open_a_box_and_pick_a_material():
    game = season21_game(box=[["legend", 2, 1]], top_box=[["mat", 2, 1]])
    b = actions.bag(game, make=True)
    b.boxes, b.top_boxes = 1, 1
    before = game.state.player.legend_items
    assert actions.act(game, "open") == [actions.OPENED["legend"].format(box=actions.BOX, n=2, legend="破境丹", coin="")]
    assert game.state.player.legend_items == before + 2 and b.boxes == 0
    actions.act(game, "open_top")
    assert b.picks == 2 and b.top_boxes == 0
    mid = actions.claim_mats(game.content)[0]
    have = game.state.player.materials.get(mid, 0)
    actions.act(game, f"claim:{mid}")
    assert game.state.player.materials[mid] == have + 1 and b.picks == 1
    assert actions.act(game, "open") == [actions.GONE]


def test_coins_go_to_the_wallet_as_the_gift_kind():
    from tianxia.wallet import GIFT

    game = season21_game(box=[["coin", 100, 1]])
    wallet = game._wallet()
    b = actions.bag(game, make=True)
    b.boxes = 1
    if wallet is None:  # 商城關著：換成一份素材
        actions.act(game, "open")
        assert b.picks == 1
        return
    have = wallet.balance(game._mall_owner(), GIFT)
    actions.act(game, "open")
    assert wallet.balance(game._mall_owner(), GIFT) == have + 100


def test_bots_sign_by_share_and_do_not_keep_resigning():
    game = season21_game(bot_sign_share=1.0)
    sign = Option(id="lunjian:sign", label="")
    assert bots.score(game, sign) == bots.SIGN_SCORE and not bots.idle(game, sign)
    actions.act(game, "sign")
    assert bots.idle(game, sign) and bots.score(game, sign) is None
    game.content.config.lunjian.bot_sign_share = 0.0
    other = season21_game(name="林小乙", content=game.content, world=game.world)
    assert bots.idle(other, sign)
    assert bots.score(game, Option(id="lunjian:open", label="")) == bots.LOOT_SCORE


def test_the_real_content_passes_its_checks():
    game = season21_game()
    assert checks.problems(game.content, rules.table()) == []


def test_a_new_season_keeps_the_boxes_but_not_the_seal():
    from types import SimpleNamespace

    from tianxia.state import LunjianBag

    game = season21_game()
    old = SimpleNamespace(player=SimpleNamespace(lunjian=LunjianBag(boxes=2, picks=1, seal_until=9e9, seal_season=1)))
    game.state.player.lunjian = None
    actions.carry(game, old)
    b = game.state.player.lunjian
    assert (b.boxes, b.picks, b.seal_until) == (2, 1, 0.0)
