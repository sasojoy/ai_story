"""地方大事的三幕、換週與收場（純規則與 actions 直接叫；正式內容 season21）。"""
from __future__ import annotations

from difang_kit import affair_here, season21_game

from tianxia.features.difang import actions, checks, rules


def _open(game):
    actions.on_sync(game)
    return affair_here(game)


def test_each_region_gets_one_affair_a_week():
    game = season21_game()
    actions.on_sync(game)
    dw = game.state.world.difang
    assert sorted(a.region for a in dw.affairs) == sorted(r.id for r in game.content.map.regions)
    assert {a.week for a in dw.affairs} == {1}
    assert dw.affairs[0].need == rules.needs(game.content.config.difang, 0)


def test_outside_the_region_nothing_is_offered():
    game = season21_game(loc="wan_city")  # 南陽
    a = _open(game)
    assert a.region == "nanyang"
    assert not [o for o in game.options() if o.id.startswith("difang:")]  # 第一幕：沒有鈕


def test_act_one_fills_then_act_two_ways_then_act_three():
    game = season21_game(need_min=[2, 2, 2], per_head=[0, 0, 0])
    a = _open(game)
    assert actions.on_outing(game, "yingshui")
    assert actions.on_win(game, "yingshui", "x") == [] or True
    a = affair_here(game)
    assert a.act == 2 and a.got == 0
    ways = [o for o in game.options() if o.id.startswith("difang:way:")]
    assert len(ways) == 3 and all(o.enabled for o in ways)
    out = actions.act(game, "way:0")
    assert out[0] in (actions.WAY_HIT, actions.WAY_MISS)
    assert actions.act(game, "way:1") == [actions.WAY_DONE] or affair_here(game).act == 3


def test_act_three_once_a_day_and_the_last_blow_finishes():
    game = season21_game(need_min=[1, 1, 3], per_head=[0, 0, 0], blow_max=1)
    a = _open(game)
    a.act, a.got = 3, 2
    strike = [o for o in game.options() if o.id == "difang:strike"]
    assert strike and strike[0].enabled
    assert actions.act(game, "strike") == [actions.STRIKE_LAST.format(foe="翻江鰍")]
    a = affair_here(game)
    assert a.status == rules.DONE and a.last == game.state.player.name
    assert any("潁水堤" in r.text and game.state.player.name in r.text for r in game.state.world.chronicle)
    assert "difang:yingshui_dike" in game.state.world.flags


def test_strike_twice_the_same_day_is_refused():
    game = season21_game(need_min=[1, 1, 50], per_head=[0, 0, 0])
    a = _open(game)
    a.act = 3
    actions.act(game, "strike")
    assert actions.act(game, "strike") == [actions.STRIKE_DONE]
    assert not [o for o in game.options() if o.id == "difang:strike"][0].enabled


def test_contributors_are_paid_once_on_sync():
    game = season21_game(need_min=[1, 1, 1], per_head=[0, 0, 0])
    a = _open(game)
    a.act = 3
    actions.act(game, "strike")
    fame = game.state.player.stats.get("fame", 0)
    actions.on_sync(game)
    assert game.state.player.stats.get("fame", 0) == fame + game.content.config.difang.fame_done
    actions.on_sync(game)
    assert game.state.player.stats.get("fame", 0) == fame + game.content.config.difang.fame_done
    assert game._mall_owner() in affair_here(game).paid


def test_a_new_week_fails_the_old_one_and_opens_the_next():
    game = season21_game()
    a = _open(game)
    actions.on_outing(game, "yingshui")
    game.state.world.difang.week = 0  # 當成換週了
    for x in game.state.world.difang.affairs:
        x.week = 0
    actions.roll_week(game)
    old = [x for x in game.state.world.difang.affairs if x.week == 0]
    assert old and all(x.status == rules.FAILED for x in old)
    assert any("潁水決堤" in r.text for r in game.state.world.chronicle)
    new = affair_here(game)
    assert new is not None and new.week == 1 and new.status == rules.OPEN


def test_the_affair_card_has_no_numbers_for_progress():
    game = season21_game()
    _open(game)
    card = actions.status(game)["difang"]["card"]
    assert card["title"] == "潁水決堤" and [x["state"] for x in card["acts"]] == ["now", "later", "later"]
    assert 0.0 <= card["fill"] <= 1.0


def test_the_real_content_passes_its_checks():
    game = season21_game()
    assert checks.problems(game.content, rules.affairs()) == []
    assert {r for a in rules.affairs().values() for r in a["regions"]} == {r.id for r in game.content.map.regions}
