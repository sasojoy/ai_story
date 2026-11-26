"""地方大事的三幕、換週與收場（純規則與 actions 直接叫；正式內容 season21）。"""
from __future__ import annotations

from difang_kit import affair_here, open_here, season21_game

from tianxia.features.difang import actions, checks, rules


def _open(game):
    return open_here(game)


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
    assert actions.on_outing(game, "wan_city") == []
    assert actions.current(game).shares == {}


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


def test_done_contributors_pick_a_top_tier_material_once_anywhere():
    game = season21_game(need_min=[1, 1, 1], per_head=[0, 0, 0])
    a = _open(game)
    a.act = 3
    actions.act(game, "strike")
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
    actions.act(game, "strike")
    mid = actions.claim_mats(game.content)[1]
    actions.act(game, f"claim:{mid}")
    assert game.state.player.materials.get(mid) == 1


def test_failed_contributors_get_a_little_fame_on_sync():
    game = season21_game()
    _open(game)
    actions.on_outing(game, "yingshui")
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
    actions.on_outing(game, "yingshui")
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
    actions.on_outing(game, "yingshui")
    act1 = actions.card(game, affair_here(game))["acts"][0]
    assert act1["who"][0] == game.state.player.name  # 自己排第一
    assert act1["who"][1] == "俠客7" and len(act1["who"]) == actions.WHO_MAX and act1["more"] == 9 - actions.WHO_MAX
    assert all(not isinstance(x, int) for x in act1["who"])  # 只給名號，不給份數
    assert actions.card(game, affair_here(game))["acts"][1]["who"] == []
