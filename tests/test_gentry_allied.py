"""第一季豪強分屬兩軍（docs/superpowers/specs/2026-10-15-第一季豪強分屬兩軍-design.md）。

用真實內容的週末設定（第一季規則與豪強分屬兩軍都開著）；舊規則的對照另外關掉開關。"""
from __future__ import annotations

import random

import pytest

from conftest import real_content, third_party_gentry
from tianxia import allied, rules
from tianxia.engine import Game
from tianxia.state import PlayerState, WorldState


@pytest.fixture
def wk():
    c = real_content("weekend")
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    return c


def _game(content, name="甲", faction=None, ally=None, at=None):
    game = Game.new(content, name, rng=random.Random(0))
    p = game.state.player
    p.faction, p.ally = faction, ally
    if at is not None:
        p.location = at
    return game


def _old_rules():
    c = third_party_gentry(real_content("weekend"))
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    return c


# ── Task 1：開關、蓋章、敵我與名冊鍵 ─────────────────────────────


def test_weekend_profile_turns_it_on(wk):
    assert wk.config.haoqiang_allied is True
    assert real_content().config.haoqiang_allied is False
    assert [f.allies for f in wk.scenario.factions if f.id == "haoqiang"] == [["guan", "huang"]]


def test_old_saves_load_without_the_new_fields():
    p = PlayerState(name="甲", location="x", stats={}, stamina=0)
    assert (p.ally, p.pending_ally) == (None, None)
    assert WorldState().haoqiang_allied is False


def test_stamp_and_rule(wk):
    game = _game(wk)
    assert game.state.world.haoqiang_allied is True
    assert allied.on(wk, game.state.world) and rules.haoqiang_allied(wk, game.state.world)


def test_fourteen_day_season_keeps_the_third_party():
    c = real_content()
    c.config.auto_open_first_season = True
    c.config.haoqiang_allied = True  # 設定打開了，可是 14 天的季沒有第一季的章
    game = _game(c, faction="haoqiang", ally="guan")
    assert not allied.on(c, game.state.world)
    assert allied.side_of(game.state, c) == "haoqiang"


def test_side_of(wk):
    game = _game(wk, faction="haoqiang", ally="huang")
    assert allied.side_of(game.state, wk) == "huang" and rules.side_of(game.state, wk) == "huang"
    game.state.player.faction, game.state.player.ally = "guan", None
    assert allied.side_of(game.state, wk) == "guan"
    game.state.player.faction = None
    assert allied.side_of(game.state, wk) is None


def test_needs_ally(wk):
    game = _game(wk, faction="haoqiang")
    assert allied.needs_ally(game.state, wk)
    game.state.player.ally = "guan"
    assert not allied.needs_ally(game.state, wk)
    assert not allied.needs_ally(_game(wk, name="丙", faction="guan").state, wk)


# 舊規則的對照各自一支測試：同一支測試裡的 Game 共用同一個資料庫，第一個開的季蓋什麼章，後面的都讀同一季


def test_old_rules_need_no_ally():
    off = _old_rules()
    assert not allied.needs_ally(_game(off, name="乙", faction="haoqiang").state, off)


def test_roll_keys():
    assert allied.roll_key("guan", None) == "guan"
    assert allied.roll_key("haoqiang", "huang") == "haoqiang@huang"
    assert allied.split_key("haoqiang@huang") == ("haoqiang", "huang")
    assert allied.split_key("guan") == ("guan", None)
    assert allied.side_of_key("haoqiang@huang") == "huang" and allied.side_of_key("guan") == "guan"
    assert allied.side_of_key(None) is None
    rolls = {"guan": 9, "haoqiang@guan": 3, "huang": 7, "haoqiang@huang": 2, "haoqiang": 1}
    assert allied.faction_totals(rolls) == {"guan": 9, "haoqiang": 6, "huang": 7}
    assert allied.side_totals(rolls) == {"guan": 12, "huang": 9, "haoqiang": 1}
    assert allied.gentry_totals(rolls) == {"guan": 3, "huang": 2}


def test_roster_counts_by_side_and_by_faction(wk):
    game = _game(wk)
    w = game.world
    w.record_faction("甲", "haoqiang@guan")
    w.record_faction("乙", "guan")
    w.record_faction("丙", "huang")
    assert w.faction_of("甲") == "guan" and w.roll_of("甲") == "haoqiang@guan"
    assert w.faction_of("乙") == "guan" and w.faction_of("無名") is None
    assert w.faction_counts() == {"guan": 1, "haoqiang": 1, "huang": 1}
    assert w.roll_counts() == {"guan": 1, "haoqiang@guan": 1, "huang": 1}


def test_geju_is_gone(wk):
    game = _game(wk)
    w = game.state.world
    assert not rules.trend_shown(wk, w, rules.GEJU)
    assert rules.resolve_trend(wk, w, rules.GEJU) is None
    assert rules.GEJU not in w.trends


def test_old_rules_keep_geju():
    off = _old_rules()
    w = _game(off, name="乙").state.world
    assert rules.trend_shown(off, w, rules.GEJU) and rules.GEJU in w.trends


def test_allies_must_be_real_other_factions(wk):
    from tianxia.content import ContentError, validate

    hao = next(f for f in wk.scenario.factions if f.id == "haoqiang")
    hao.allies = ["guan", "nobody"]
    with pytest.raises(ContentError, match="allies"):
        validate(wk)
    hao.allies = ["haoqiang", "huang"]
    with pytest.raises(ContentError, match="allies"):
        validate(wk)


# ── Task 2：投靠多一步選邊、拜入之後選邊、名冊與名號 ─────────────────────


def _ids(game):
    return [o.id for o in game.options() if o.enabled]


def test_join_gentry_picks_a_side_then_confirms(wk):
    game = _game(wk, at="zhuo_militia_hall")
    game.choose("faction:haoqiang")
    assert _ids(game) == ["faction:ally:guan", "faction:ally:huang", "faction:cancel"]
    assert "依附官軍（目前 0 人）" in [o.label for o in game.options()]
    game.choose("faction:ally:guan")
    assert [o.label for o in game.options()][0] == "確定投靠地方豪強（依附官軍）"
    game.choose("faction:confirm")
    p = game.state.player
    assert (p.faction, p.ally, p.pending_faction, p.pending_ally) == ("haoqiang", "guan", None, None)
    assert game.world.roll_of("甲") == "haoqiang@guan"


def test_cancel_clears_the_pick(wk):
    game = _game(wk, at="zhuo_militia_hall")
    game.choose("faction:haoqiang")
    game.choose("faction:ally:huang")
    assert game.state.player.pending_ally == "huang"
    game.choose("faction:cancel")
    p = game.state.player
    assert (p.faction, p.pending_faction, p.pending_ally) == (None, None, None)


def test_join_army_has_no_side_step(wk):
    game = _game(wk, at="changshe")
    game.choose("faction:guan")
    assert _ids(game) == ["faction:confirm", "faction:cancel"]


def test_sect_join_waits_for_a_side(wk):
    from tianxia import atlas

    game = _game(wk, faction="haoqiang", at="cao_manor")  # 拜入曹氏莊院那一下：陣營有了、還沒挑一邊
    assert _ids(game) == ["faction:ally:guan", "faction:ally:huang"]
    block = atlas.travel_block(game.state, wk)
    assert block is not None and block.to_jianghu
    game._record_faction()
    assert game.world.roll_of("甲") is None
    game.choose("faction:ally:huang")
    assert game.state.player.ally == "huang"
    assert game.world.roll_of("甲") == "haoqiang@huang"
    assert "act:explore" in _ids(game)


def test_roster_text(wk):
    game = _game(wk)
    for name, key in [("a", "guan"), ("b", "haoqiang@guan"), ("c", "huang"), ("d", "huang")]:
        game.world.record_faction(name, key)
    assert game.faction_counts_text() == "目前官軍 2 人（其中豪強 1 人）、黃巾軍 2 人"


def test_old_rules_roster_text():
    off = _old_rules()
    game = _game(off, name="乙")
    game.world.record_faction("a", "haoqiang")
    assert game.faction_counts_text() == "目前官軍 0 人、黃巾軍 0 人、地方豪強 1 人"


def test_affiliation_names_the_side(wk):
    from tianxia import social

    game = _game(wk, faction="haoqiang", ally="guan")
    assert social.affiliation(game.state, wk).startswith("地方豪強（依附官軍）")


def test_allied_gentry_hears_the_side_news(wk):
    game = _game(wk, faction="haoqiang", ally="guan")
    rules.add_rumor(game.state, "官軍的軍情", layer="faction", faction="guan")
    rules.add_rumor(game.state, "豪強的軍情", layer="faction", faction="haoqiang")
    rules.add_rumor(game.state, "黃巾的軍情", layer="faction", faction="huang")
    ears = rules.ears_of(game.state, wk)
    heard = [r.text for r in game.state.world.rumors if rules.audible(r, ears)]
    assert "官軍的軍情" in heard and "豪強的軍情" in heard and "黃巾的軍情" not in heard


# ── Task 3：沒有割據、態勢兩方、結局只比高低 ─────────────────────────


def _set_fronts(game, content, value):
    w = game.state.world
    for line in rules.front_ids(content):
        w.trends[line] = value
    rules.recompute_trends(w, content)


def test_two_stances_and_no_geju_tick(wk):
    game = _game(wk)
    assert set(rules.stances(game.state, wk)) == {"guan", "huang"}
    assert rules.stance_sides(wk, game.state.world) == ("guan", "huang")
    rules.geju_tick(game.state, wk, 24 * 30, players=20)
    assert rules.GEJU not in game.state.world.trends
    data = game.status_data()
    assert set(data["stances"]) == {"guan", "huang"} and "haoqiang" not in data["stance_notes"]


def test_old_rules_have_three_stances():
    off = _old_rules()
    game = _game(off, name="乙")
    assert set(rules.stances(game.state, off)) == {"guan", "huang", "haoqiang"}
    assert "haoqiang" in game.status_data()["stance_notes"]


def test_endings_only_compare_the_two(wk):
    from tianxia import world as world_rules

    game = _game(wk)
    ids = [e.id for e in world_rules.season_endings(game.state, wk)]
    assert "s1_warlords" not in ids and "s1_gentry" not in ids and "s1_turbans_hold" in ids
    _set_fronts(game, wk, 50)
    assert world_rules.evaluate_ending(game.state, wk).id == "s1_turbans_hold"  # 剛好 50 算黃巾坐地（企劃者定）
    _set_fronts(game, wk, 45)
    assert world_rules.evaluate_ending(game.state, wk).id == "s1_turbans_retreat"


def test_rule_note_has_no_warlords(wk):
    game = _game(wk)
    note = rules.stance_rule_note(game.state, wk)
    assert "群雄並起" not in note and "豪強" not in note and "比高低" in note


def test_territory_has_no_geju_hold(wk):
    from tianxia import territory

    game = _game(wk)
    w = game.state.world
    territory.update(w, wk)
    assert w.territory.geju == []
    spots = [loc for line in wk.scenario.territory.lines.values() for loc in line]
    assert "haoqiang" not in {territory.controller(w, wk, loc) for loc in spots}


# ── Task 4：推線、出陣、地盤、守勢與第 3 階行動、機緣、捐軍備照那一邊 ─────────


def _spots(game, content, side):
    """這一方控制的、另一方控制的戰線地點各一處（照此刻的控制方）。"""
    from tianxia import territory

    w = game.state.world
    spots = [loc for line in content.scenario.territory.lines.values() for loc in line]
    own = next(loc for loc in spots if territory.controller(w, content, loc) == side)
    foe = next(loc for loc in spots if territory.controller(w, content, loc) not in (None, side))
    return own, foe


def test_gentry_sortie_attacks_and_holds_like_its_side(wk):
    game = _game(wk, faction="haoqiang", ally="guan")
    own, foe = _spots(game, wk, "guan")
    game.state.player.location = own
    assert game.sortie_mode() == "hold"
    game.state.player.location = foe
    assert game.sortie_mode() == "attack"
    push = game.sortie_push(foe)
    assert push and all(v < 0 for v in push.values())  # 往官軍那一頭（0）推


def test_goals_are_the_sides(wk):
    game = _game(wk, faction="haoqiang", ally="huang")
    goals = game._goals()
    assert set(goals) == set(rules.front_ids(wk)) and all(v == 1 for v in goals.values())


def test_push_buffer_counts_the_allied_gentry(wk):
    game = _game(wk, faction="haoqiang", ally="guan")
    w = game.state.world
    w.active_pushers["guan"] = {"官一": w.time, "官二": w.time, "官三": w.time}
    line = rules.front_ids(wk)[0]
    game.push_trend(line, -4, source="sortie")
    assert "甲" in w.active_pushers["guan"] and "haoqiang" not in w.active_pushers
    assert game.state.player.contrib > 0  # 往官軍的目標推，記貢獻


def test_price_follows_the_side(wk):
    from tianxia import team, territory

    game = _game(wk, faction="haoqiang", ally="guan")
    own, foe = _spots(game, wk, "guan")
    game.state.player.location = own
    assert team._price_here(game.state, wk) == wk.config.territory.own_price
    game.state.player.location = foe
    assert team._price_here(game.state, wk) == wk.config.territory.enemy_price
    assert territory.price_factor(game.state.world, wk, allied.side_of(game.state, wk), foe) == wk.config.territory.enemy_price


def test_duty_pushes_the_front_for_the_side(wk):
    game = _game(wk, faction="haoqiang", ally="huang")
    own, _ = _spots(game, wk, "huang")
    game.state.player.location = own
    line = rules.front_of(wk, own)
    w = game.state.world
    before = w.trends[line] + w.trend_accum.get(line, 0.0)
    msgs = game._duty()
    assert any("保境安民" in m or m for m in msgs)
    assert w.trends[line] + w.trend_accum.get(line, 0.0) > before  # 往黃巾那一頭（100）推
    assert rules.GEJU not in w.trends


def test_donate_goes_to_the_side_stock(wk):
    from tianxia import economy

    game = _game(wk, faction="haoqiang", ally="guan", at="zhuo_militia_hall")
    assert game._at_own_base()
    game.state.player.location = "changshe"  # 依附那一軍的投靠點也算自家大本營
    assert game._at_own_base()
    game.state.player.location = "huangjin_camp"
    assert not game._at_own_base()
    target = economy.donate_target(wk, game.state.world, "guan", "zhuo_militia_hall")
    assert target is not None and target[0] != rules.GEJU and target[1] == -1
    game.state.player.location = "changshe"
    game.state.player.materials = {"man_1": 3}
    game.donate("man_1", 3)
    assert game.state.world.armaments.get("guan") and "haoqiang" not in game.state.world.armaments


# ── Task 5：軍令、懸賞、截殺、挑戰本人、伏筆、事件條件照那一邊 ─────────────


def _settled(game):
    """開季那一刻的結算（第 1 週的週初掛鉤：軍令、懸賞），同 Game._settle_season_start。"""
    from tianxia.world import settle_season_start

    settle_season_start(game.state.world, game.content, random.Random(0))
    return game


def test_orders_skip_the_gentry_and_follow_the_side(wk):
    from tianxia import orders

    game = _settled(_game(wk, faction="haoqiang", ally="guan"))
    w = game.state.world
    assert w.orders, "開季那一刻第 1 週的軍令已經發了"
    assert not [o for o in w.orders if o.faction == "haoqiang"]
    assert orders.current(game.state, wk, allied.side_of(game.state, wk))


def test_old_rules_still_issue_gentry_orders():
    off = _old_rules()
    assert [o for o in _settled(_game(off, name="乙")).state.world.orders if o.faction == "haoqiang"]


def test_give_bounties_skip_the_gentry(wk):
    from tianxia import bounties

    game = _settled(_game(wk))
    gives = [b.faction for b in game.state.world.bounties if b.kind in bounties.GIVE_KINDS]
    assert gives and "haoqiang" not in gives


def test_old_rules_still_issue_gentry_give_bounties():
    from tianxia import bounties

    off = _old_rules()
    game = _settled(_game(off, name="乙"))
    assert "haoqiang" in [b.faction for b in game.state.world.bounties if b.kind in bounties.GIVE_KINDS]


def test_bounties_take_the_sides(wk):
    from tianxia import bounties

    game = _settled(_game(wk, faction="haoqiang", ally="huang"))
    open_ones = [b for b in game.state.world.bounties if b.kind not in bounties.GIVE_KINDS]
    mine = [b for b in open_ones if b.faction == "huang"]
    theirs = [b for b in open_ones if b.faction == "guan"]
    assert mine and all(bounties.can_take(game.state, b) for b in mine)
    assert theirs and not any(bounties.can_take(game.state, b) for b in theirs)


def test_no_raid_on_the_same_side(wk):
    a = _game(wk, faction="haoqiang", ally="guan")
    b = _game(wk, name="乙", faction="guan")
    c = _game(wk, name="丙", faction="huang")
    assert not a.raid_shown(b) and not b.raid_shown(a) and a.raid_shown(c)


def _standing(game, content, side):
    """這一方此刻在場、有所在地的第一位大勢人物。"""
    from tianxia import figures

    return next(
        fid for fid, f in content.figures.items()
        if f.faction == side and (now := figures.state_of(game.state, content, fid)).status == "active" and now.location
    )


def test_challenge_only_the_other_side(wk):
    from tianxia import figures

    game = _game(wk, faction="haoqiang", ally="guan")
    for side, shown in (("guan", False), ("huang", True)):
        fid = _standing(game, wk, side)
        game.state.player.location = figures.state_of(game.state, wk, fid).location
        ids = [o.id for o in game._challenge_options(False)]
        assert (f"act:challenge:{fid}" in ids) is shown


def test_foreshadow_chains_follow_the_side(wk):
    from tianxia import foreshadow

    game = _game(wk, faction="haoqiang", ally="guan")
    sides = {c.side for c in wk.foreshadows.chains if foreshadow.capable(game.state, wk, c)}
    assert sides == {"guan"}


def test_third_party_fragments_hidden(wk):
    from tianxia import events, foreshadow

    assert foreshadow.third_party_events(wk) == {"fs_ev_xinye_clerk", "fs_ev_two_buyers"}
    game = _game(wk, faction="haoqiang", ally="guan", at="xinye")
    assert "fs_ev_xinye_clerk" not in [e.id for e in events.event_candidates(game.state, wk, "explore")]


def test_old_rules_show_third_party_fragments():
    from tianxia import events

    off = _old_rules()
    game = _game(off, name="乙", faction="haoqiang", at="xinye")
    assert "fs_ev_xinye_clerk" in [e.id for e in events.event_candidates(game.state, off, "explore")]


def test_condition_factions_read_both(wk):
    from tianxia.models import Condition

    game = _game(wk, faction="haoqiang", ally="huang")
    assert rules.check_condition(Condition(factions=["haoqiang"]), game.state, wk)
    assert rules.check_condition(Condition(factions=["huang"]), game.state, wk)
    assert not rules.check_condition(Condition(factions=["guan"]), game.state, wk)
    assert not rules.check_condition(Condition(factions_none=["huang"]), game.state, wk)
    assert not rules.check_condition(Condition(factions=["huang"]), game.state)  # 沒給 content 讀不到季的章：照舊只比陣營


# ── Task 6：決戰站依附的那一軍、軍餉記貢獻、玉璽算那一軍 ─────────────────


def _in_region(content, region_id):
    from tianxia import atlas

    return next(loc for loc in content.locations if (r := atlas.region_of(content, loc)) is not None and r.id == region_id)


def _showdown(game):
    """管理者「立刻開這一場」長社火攻（效果同時刻表自然開），人站到決戰的大區；回傳那一場的定義。"""
    game.content.config.admins = [game.state.player.name]
    game.client = None
    game.sync(1000.0)
    assert game.admin_start_showdown("changshe_fire", 1000.0) == ["🛡️ 【全服戰報】長社火攻的集結號角已經吹響！"]
    definition = game.content.battles[game.world.get_battle().battle_id]
    if definition.region is not None:
        game.state.player.location = _in_region(game.content, definition.region)
    return definition


def test_gentry_joins_its_side_not_as_free_agent(wk):
    game = _game(wk, faction="haoqiang", ally="guan")
    definition = _showdown(game)
    assert not game._free_agent(definition)
    ids = [o.id for o in game.options()]
    assert "battle:join:guan" in ids and not [i for i in ids if i.startswith("battle:enlist:")]
    game.choose("battle:join:guan")
    assert game.world.get_battle().participants["甲"].faction == "guan"


def test_gentry_showdown_pay_counts_contribution(wk):
    game = _game(wk, faction="haoqiang", ally="guan")
    _showdown(game)
    game.choose("battle:join:guan")
    battle = game.world.get_battle()
    battle.outcome_side = "guan"
    changes = game._showdown_pay(battle, battle.participants["甲"], [])
    assert any(c.startswith("貢獻 +") for c in changes)


def test_old_rules_gentry_enlists():
    off = _old_rules()
    game = _game(off, name="乙", faction="haoqiang")
    definition = _showdown(game)
    assert game._free_agent(definition)
    assert [o.id for o in game.options() if o.id.startswith("battle:enlist:")]


def test_seal_and_battles_read_the_side_from_the_roster(wk):
    game = _game(wk, faction="haoqiang", ally="huang")
    game._record_faction()
    assert game.world.faction_of("甲") == "huang"
