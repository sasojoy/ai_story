"""地方大事的三幕、換週與收場（純規則與 actions 直接叫；正式內容 season21）。"""
from __future__ import annotations

from difang_kit import affair_here, open_here, season21_game

from tianxia.features.difang import actions, checks, rules


def _open(game):
    return open_here(game)


def _pitch(game, way: int = 0):
    """赴一次大事、挑第 way 個做法（不擲的那一個在最後；第 0 個都寫了屬性）。"""
    game.state.player.stamina = 100
    out = actions.act(game, "go")
    assert out[0] == actions.GO_LINE.format(place="潁水河畔") or out[0].startswith("你趕到"), out
    return actions.act(game, f"pick:{way}")


def test_one_affair_for_the_whole_server_a_week_and_the_region_rotates(monkeypatch):
    game = season21_game()
    actions.on_sync(game)
    dw = game.state.world.difang
    assert len(dw.affairs) == 1 and dw.affairs[0].week == 1
    assert dw.affairs[0].need == rules.needs(game.content.config.difang, 0)
    seen = [dw.affairs[0].region]
    for week in range(2, 1 + len(game.content.map.regions)):  # 一週換一個大區：輪一圈每一區都輪到
        monkeypatch.setattr(actions, "_week", lambda ctx, w=week: w)
        actions.roll_week(game)
        assert dw.affairs[-1].week == week and dw.affairs[-2].status == rules.FAILED
        seen.append(dw.affairs[-1].region)
    assert sorted(seen) == sorted(r.id for r in game.content.map.regions)


def test_away_from_the_region_the_card_shows_but_nothing_counts():
    game = season21_game(loc="wan_city")  # 南陽
    open_here(game)  # 這一件在潁川汝南
    assert not [o for o in game.options() if o.id.startswith("difang:")]
    card = actions.status(game)["difang"]["card"]
    assert card["away"] is True and card["options"] == []
    assert actions.act(game, "go") == [actions.GONE]
    assert actions.current(game).shares == {}


def test_go_draws_an_event_of_this_act_then_a_way_counts():
    game = season21_game(need_min=[99, 99, 99], per_head=[0, 0, 0])
    _open(game)
    go = [o for o in game.options() if o.id.startswith("difang:")]
    assert [o.id for o in go] == ["difang:go"] and go[0].enabled and "體力" in go[0].label
    stamina = game.state.player.stamina = 100
    out = actions.act(game, "go")
    a = affair_here(game)
    e = actions.event_of(rules.affairs()["yingshui_dike"], a.drawn[game._mall_owner()])
    assert e in rules.affairs()["yingshui_dike"]["acts"][0]["events"] and out[-1] == e["scene"]
    assert game.state.player.stamina == stamina - game.content.config.jianfa.explore_stamina
    picks = [o for o in game.options() if o.id.startswith("difang:")]
    assert [o.id for o in picks] == [f"difang:pick:{i}" for i in range(len(e["ways"]))]  # 赴了就只剩挑做法
    assert actions.act(game, "go") == [actions.GONE]
    xinde = game.state.player.stats.get("xinde", 0)
    out = actions.act(game, "pick:0")
    w = e["ways"][0]
    assert out[0] in (w["hit"], w["miss"])
    t = game.content.config.difang
    hit = out[0] == w["hit"]
    assert a.got == (t.way_hit if hit else t.way_miss) and a.shares[game._mall_owner()] == a.got
    assert game.state.player.stats["xinde"] == xinde + (t.xinde_hit if hit else t.xinde_miss)
    assert a.told[game._mall_owner()] == out and actions.card(game, a)["told"] == out


def test_an_unrolled_way_is_one_steady_share():
    game = season21_game(need_min=[99, 99, 99], per_head=[0, 0, 0])
    a = _open(game)
    game.state.player.stamina = 100
    actions.act(game, "go")
    e = actions.event_of(rules.affairs()["yingshui_dike"], a.drawn[game._mall_owner()])
    i = next(i for i, w in enumerate(e["ways"]) if not w.get("stat")) if any(not w.get("stat") for w in e["ways"]) else None
    if i is None:
        return
    assert actions.act(game, f"pick:{i}")[0] == e["ways"][i]["line"] and a.got == game.content.config.difang.way_miss


def test_three_goes_a_day_and_no_repeat_until_the_act_is_used_up():
    game = season21_game(need_min=[99, 99, 99], per_head=[0, 0, 0])
    a = _open(game)
    t = game.content.config.difang
    for _ in range(t.daily_goes):
        _pitch(game)
    go = [o for o in game.options() if o.id == "difang:go"][0]
    assert not go.enabled and actions.card(game, a)["left"] == 0
    assert actions.act(game, "go") == [actions.GO_FULL.format(n=t.daily_goes)]
    pool = [e["id"] for e in rules.affairs()["yingshui_dike"]["acts"][0]["events"]]
    seen = a.seen[game._mall_owner()]
    assert len(set(seen)) == len(seen) == t.daily_goes
    a.goes.clear()  # 當成隔天
    _pitch(game)
    assert sorted(seen) == sorted(pool)  # 四則都碰過一輪
    a.goes.clear()
    _pitch(game)
    assert len(seen) == 1 and seen[0] in pool  # 下一輪重來


def test_not_enough_stamina_cannot_go():
    game = season21_game()
    _open(game)
    game.state.player.stamina = 0
    assert not [o for o in game.options() if o.id == "difang:go"][0].enabled
    assert actions.act(game, "go") == [actions.GO_TIRED]


def test_act_one_fills_then_act_two_draws_its_own_events():
    game = season21_game(need_min=[1, 99, 99], per_head=[0, 0, 0])
    _open(game)
    _pitch(game)
    a = affair_here(game)
    assert a.act == 2 and a.got == 0
    _pitch(game)
    act2 = {e["id"] for e in rules.affairs()["yingshui_dike"]["acts"][1]["events"]}
    assert a.seen[game._mall_owner()][-1] in act2


def test_explore_no_longer_counts():
    from tianxia.core import features as features_core

    assert "difang" not in features_core.BUS_ORDER["outing"] and "difang" not in features_core.BUS_ORDER["win"]


def test_act_three_once_a_day_and_the_last_blow_finishes():
    game = season21_game(need_min=[1, 1, 3], per_head=[0, 0, 0], blow_max=1)
    a = _open(game)
    a.act, a.got = 3, 2
    strike = [o for o in game.options() if o.id.startswith("difang:strike:")]
    assert len(strike) == 3 and all(o.enabled for o in strike)
    out = actions.act(game, "strike:0")
    w = rules.affairs()["yingshui_dike"]["acts"][2]["ways"][0]
    assert out[0] in (w["hit"], w["miss"]) and out[1] == actions.STRIKE_LAST.format(foe="翻江鰍")
    a = affair_here(game)
    assert a.status == rules.DONE and a.last == game.state.player.name
    assert any("潁水堤" in r.text and game.state.player.name in r.text for r in game.state.world.chronicle)
    assert "difang:yingshui_dike" in game.state.world.flags


def test_strike_twice_the_same_day_is_refused():
    game = season21_game(need_min=[1, 1, 50], per_head=[0, 0, 0])
    a = _open(game)
    a.act = 3
    actions.act(game, "strike:1")
    assert actions.act(game, "strike:2") == [actions.STRIKE_DONE]
    assert not any(o.enabled for o in game.options() if o.id.startswith("difang:strike:"))


def test_done_contributors_pick_a_top_tier_material_once_anywhere():
    game = season21_game(need_min=[1, 1, 1], per_head=[0, 0, 0])
    a = _open(game)
    a.act = 3
    actions.act(game, "strike:0")
    t, p = game.content.config.difang, game.state.player
    game.state.player.location = "wan_city"  # 走遠了也領得到
    claims = [o for o in game.options() if o.id.startswith("difang:claim:")]
    mats = actions.claim_mats(game.content)
    assert [o.id for o in claims] == [f"difang:claim:{m}" for m in mats] and len(mats) == 4
    assert all(game.content.materials[m].tier == t.material_tier for m in mats)
    card = actions.status(game)["difang"]["card"]
    assert [c["id"] for c in card["claim"]] == [o.id for o in claims] and card["marks"] == [actions.YISHI, actions.PILLAR]
    fame, xinde = p.stats.get("fame", 0), p.stats.get("xinde", 0)
    actions.act(game, f"claim:{mats[0]}")
    assert p.materials.get(mats[0]) == 2  # 出力前十：多一份
    assert p.stats.get("fame", 0) == fame + t.fame_done and p.stats.get("xinde", 0) == xinde + t.xinde_done
    assert actions.act(game, f"claim:{mats[1]}") == [actions.CLAIM_DONE] and not p.materials.get(mats[1])
    assert not [o for o in game.options() if o.id.startswith("difang:claim:")]
    actions.on_sync(game)
    assert p.stats.get("fame", 0) == fame + t.fame_done  # 同步不再發一次
    assert actions.status(game)["difang"]["card"]["claimed"] is True


def test_outside_the_top_ten_one_piece():
    game = season21_game(need_min=[1, 1, 1], per_head=[0, 0, 0], top_more=1)
    a = _open(game)
    a.shares.update({"k0": 9})
    a.act = 3
    actions.act(game, "strike:0")
    mid = actions.claim_mats(game.content)[1]
    actions.act(game, f"claim:{mid}")
    assert game.state.player.materials.get(mid) == 1


def test_failed_contributors_get_a_little_fame_on_sync():
    game = season21_game()
    _open(game)
    _pitch(game)
    dw = game.state.world.difang
    dw.week = 0
    for x in dw.affairs:
        x.week = 0
    fame = game.state.player.stats.get("fame", 0)
    actions.on_sync(game)
    assert game.state.player.stats.get("fame", 0) == fame + game.content.config.difang.fame_failed
    actions.on_sync(game)
    assert game.state.player.stats.get("fame", 0) == fame + game.content.config.difang.fame_failed


def test_a_new_week_fails_the_old_one_and_opens_the_next():
    game = season21_game()
    a = _open(game)
    _pitch(game)
    game.state.world.difang.week = 0  # 當成換週了
    for x in game.state.world.difang.affairs:
        x.week = 0
    actions.roll_week(game)
    old = [x for x in game.state.world.difang.affairs if x.week == 0]
    assert old and all(x.status == rules.FAILED for x in old)
    assert any("潁水決堤" in r.text for r in game.state.world.chronicle)
    new = actions.current(game)
    assert new is not None and new.week == 1 and new.status == rules.OPEN and len(game.state.world.difang.affairs) == 2


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


def test_each_act_lists_who_pitched_in_me_first_and_caps_the_row():
    game = season21_game(need_min=[99, 99, 99], per_head=[0, 0, 0])
    a = _open(game)
    for i in range(8):  # 別人先出了力（直接記帳：同一區八位俠客）
        a.by_act.append([]) if not a.by_act else None
        a.by_act[0].append(f"k{i}")
        a.names[f"k{i}"] = f"俠客{i}"
        a.shares[f"k{i}"] = 1
    _pitch(game)
    act1 = actions.card(game, affair_here(game))["acts"][0]
    assert act1["who"][0] == game.state.player.name  # 自己排第一
    assert act1["who"][1] == "俠客7" and len(act1["who"]) == actions.WHO_MAX and act1["more"] == 9 - actions.WHO_MAX
    assert all(not isinstance(x, int) for x in act1["who"])  # 只給名號，不給份數
    assert actions.card(game, affair_here(game))["acts"][1]["who"] == []
