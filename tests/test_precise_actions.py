"""正式季整合第 3 批：一類一顆（設計第二章；12.3 第 5～13 條照 PM 提案）。每一顆鈕只給一類東西、按了一定拿到那一類。
開關 Config.precise_actions 照開季蓋章；測試內容關著，這裡用正式內容（週末設定）。"""
from __future__ import annotations

import random

from conftest import real_content

from tianxia import precise
from tianxia.engine import Game
from tianxia.sqlite_world import open_world
from tianxia.world_state import fresh_season, stamp_season

HOUR = 3600
MON = 1792339200  # 2026-10-19 週一 00:00（台灣）
NOW = MON + 10 * HOUR


def _game(profile="weekend", at="yingchuan", faction=None, stamina=250.0, opened=True):
    c = real_content(profile)
    c.config.train_event_chance = 0.0
    store = open_world()
    store.seed_first_season(c)
    if opened:
        store.open_season(c, NOW)
    game = Game.new(c, "沈浪", rng=random.Random(0), world=store)
    game.client = None
    game.sync(NOW)
    p = game.state.player
    p.location, p.faction, p.stamina = at, faction, stamina
    p.tutorial_step = len(c.tutorial.steps)
    return game


def _ids(game):
    return {o.id: o for o in game.options()}


# ── Task 1：開關與蓋章 ──


def test_a_stamped_season_turns_precise_on():
    c = real_content("weekend")
    season = fresh_season(c)
    stamp_season(season, c)
    assert season.precise_actions and precise.on(c, season)


def test_unstamped_season_keeps_the_old_rules():
    c = real_content("weekend")
    season = fresh_season(c)
    stamp_season(season, c)
    season.precise_actions = False  # 設定打開之前就開的季
    assert not precise.on(c, season)


# ── Task 2：找素材一定給、不打仗（2.4）；應召不再換掉（2.10）──


def _press(game, oid):
    game.state.player.stamina = 250.0
    return game.choose(oid)


def test_gathering_always_gives_materials_and_never_fights():
    for at in ("yingchuan", "changshe"):  # 城鎮、城外
        game = _game(at=at)
        for _ in range(40):
            before = sum(game.state.player.materials.values())
            battles = len(game.state.battles)
            _press(game, "explore:gather")
            assert sum(game.state.player.materials.values()) > before, at
            assert len(game.state.battles) == battles and game.state.pending_event is None, at


def test_gathering_at_a_summons_place_still_gathers(monkeypatch):
    from tianxia import ranks

    game = _game(at="changshe")
    monkeypatch.setattr(ranks, "summons_event", lambda *a, **k: next(iter(game.content.events)))
    before = sum(game.state.player.materials.values())
    _press(game, "explore:gather")
    assert sum(game.state.player.materials.values()) > before and game.state.pending_event is None


def test_unstamped_season_still_fights_while_gathering():
    from tianxia import explore_modes

    game = _game(at="changshe")
    game.state.world.precise_actions = False
    game.content.config.explore_modes.encounter_chance = 1.0
    _press(game, "explore:gather")
    assert game.state.battles  # 舊規則：城外撞上一場
    assert explore_modes.on(game.content)


# ── Task 3：練功（2.5）──


def test_practice_always_fights_one_and_is_unlimited():
    game = _game(at="changshe")
    p = game.state.player
    option = _ids(game)["explore:practice"]
    assert option.enabled and option.label.startswith("練功（體力 6") and "經驗約" in option.label
    for n in range(1, 6):
        p.stamina = 250.0
        game.choose("explore:practice")
        assert len(game.state.battles) == n and p.stamina <= 244 + 0.01 and p.duel is None
        assert game.state.pending_event is None  # 練功之後不接戰後事件


def test_practice_greys_out_where_there_is_no_one_to_fight():
    game = _game(at="yingchuan")
    option = _ids(game)["explore:practice"]
    assert not option.enabled and "這裡沒有可以練手的對手" in option.label and "最近的在" in option.label
    stamina = game.state.player.stamina
    game.choose("explore:practice")
    assert game.state.player.stamina == stamina and not game.state.battles


def test_practice_is_not_a_scouting_but_gathering_is(monkeypatch):
    from tianxia import bounties

    calls = []
    monkeypatch.setattr(bounties, "on_explore", lambda *a, **k: calls.append(a) or [])
    game = _game(at="changshe")
    _press(game, "explore:practice")
    assert calls == []
    _press(game, "explore:gather")
    assert len(calls) == 1


def test_practice_rolls_the_boss_instead_of_gathering():
    game = _game(at="changshe")
    game.content.config.duel.explore_chance = 1.0
    _press(game, "explore:gather")
    assert game.state.player.duel is None  # 找素材不再擲頭目
    _press(game, "explore:practice")
    assert game.state.player.duel is not None


def test_a_boss_only_place_practices_straight_against_the_boss():
    game = _game(at="julu_altar", faction="huang")
    assert game._gather_foe(game.content.locations["julu_altar"]) is None
    option = _ids(game)["explore:practice"]
    assert option.enabled
    _press(game, "explore:practice")
    assert game.state.player.duel is not None


def test_practice_finishes_a_strike_bounty():
    from unittest import mock

    from tianxia import team
    from tianxia.encounter import EncounterResult
    from tianxia.state import Bounty

    game = _game(at="changshe")
    w = game.state.world
    w.bounties.append(Bounty(id="b1", kind="strike", faction="huang", week=1, expires=1e12, silver=20, deeds=1,
                             location="changshe", squad="jun_bing", takers=["沈浪"]))
    with mock.patch.object(team, "fight", return_value=EncounterResult(tier="大勝", margin=50, our_power=200, difficulty=10)):
        _press(game, "explore:practice")
    assert game.state.battles[-1].opponent == game.content.squads["jun_bing"].name and w.bounties[-1].done_by == ["沈浪"]


def test_boss_cooldown_and_used_up_grey_the_boss_only_place():
    from tianxia import duel as duel_rules

    game = _game(at="julu_altar", faction="huang")
    s, c = game.state, game.content
    s.player.duel_last = [float(s.player.season_number), s.world.time]
    option = _ids(game)["explore:practice"]
    assert not option.enabled and "後才會再現身" in option.label
    s.player.duel_last = []
    boss = duel_rules.here(s, c)[0]
    s.player.duel_tally[duel_rules.season_key(s, boss.id)] = c.config.duel.per_boss_season
    option = _ids(game)["explore:practice"]
    assert not option.enabled and "這一季他不再現身" in option.label


def test_season21_boss_is_twice_a_week():
    from tianxia import calendar
    from tianxia import duel as duel_rules

    game = _game("season21", at="julu_altar", faction="huang")
    s, c = game.state, game.content
    assert c.config.duel.per_boss_week == 2
    boss = duel_rules.available(s, c)
    s.player.duel_tally[duel_rules.week_key(s, c, boss.id)] = 2
    assert duel_rules.available(s, c) is None
    s.world.time = calendar.week_start(2, c, s.world) + 3 * HOUR
    assert duel_rules.available(s, c) is not None


# ── Task 4：交友只談話、求見併進交友（2.8）；拜入門派另成一顆（2.7）──


def test_one_figure_talks_straight_away():
    game = _game(at="luoyang_road")
    opts = _ids(game)
    assert opts["act:socialize"].label == "交友（體力 3・跟唐周說話）" and opts["act:socialize"].enabled
    assert not any(i.startswith("call:") or i == "act:call" for i in opts)  # 求見不再單獨列
    assert game.dialogue_request("act:socialize") is not None


def test_two_figures_open_the_list_for_free():
    game = _game(at="wan_city")
    opts = _ids(game)
    assert opts["act:call"].label == "交友" and "act:socialize" not in opts
    stamina = game.state.player.stamina
    game.choose("act:call")
    assert game.state.player.picking_audience and game.state.player.stamina == stamina
    names = [o.label for o in game.options()]
    assert any(label.startswith("孫堅") for label in names) and names[-1] == "返回"


def test_no_one_to_talk_to_greys_out_and_costs_nothing():
    game = _game(at="changshe")
    option = _ids(game)["act:socialize"]
    assert not option.enabled and option.label == "交友（名望還差 15）"
    option = _ids(_game(at="yingchuan"))["act:socialize"]
    assert not option.enabled and option.label == "交友（這裡沒有能說上話的人）"


def test_under_fame_in_the_list_is_grey_unless_a_meeting_is_here():
    game = _game(at="dajiangjun_fu")
    game.choose("act:call")
    opts = {o.label.split("（")[0]: o for o in game.options()}
    assert not opts["何進"].enabled and "名望還差" in opts["何進"].label
    assert opts["袁紹"].enabled and "先設法結識" in opts["袁紹"].label
    stamina = game.state.player.stamina
    game.choose(next(o.id for o in game.options() if o.label.startswith("袁紹")))
    assert game.state.pending_event == "meet_yuanshao" and game.state.player.stamina == stamina - 3


def test_a_figure_out_of_reach_is_met_through_his_meeting_event():
    game = _game(at="qiao_county")
    _press(game, "act:socialize")
    assert game.state.pending_event == "meet_caocao"


def test_socialize_events_move_to_seeking():
    from tianxia.events import event_candidates

    game = _game(at="yingchuan")
    s, c = game.state, game.content
    social = event_candidates(s, c, "socialize")
    assert all(precise.kept_social(e) for e in social)
    merged = [e for e in event_candidates(s, c, "explore") if "socialize" in e.actions]
    assert merged and not any(precise.kept_social(e) or precise.joins_sect(e) for e in merged)


def test_joining_a_sect_is_its_own_button():
    game = _game(at="yingchuan_academy")
    opts = _ids(game)
    assert opts["sect:yingchuan_join"].label == "拜入潁川書院"
    stamina = game.state.player.stamina
    game.choose("sect:yingchuan_join")
    assert game.state.pending_event == "yingchuan_join" and game.state.player.stamina == stamina


def test_fortune_with_no_one_free_gives_no_xinde(monkeypatch):
    from tianxia import roster

    game = _game(at="luoyang_road")
    monkeypatch.setattr(roster, "owned_by", lambda *a, **k: "別人")
    monkeypatch.setattr(roster, "fortune_due", lambda *a, **k: True)
    xinde = game.state.player.stats.get("xinde", 0)
    assert game._social_plan() == ("talk", "tangzhou")
    assert game._deliver_fortune() == [] and game.state.player.stats.get("xinde", 0) == xinde


def test_a_summons_place_still_talks(monkeypatch):
    from tianxia import ranks

    game = _game(at="luoyang_road")
    monkeypatch.setattr(ranks, "summons_event", lambda *a, **k: next(iter(game.content.events)))
    assert "act:summons" in _ids(game) and game.dialogue_request("act:socialize") is not None


# ── Task 5：找事件的偏向、併池、空池（2.7）──


def test_seek_names_what_it_mostly_gives():
    option = _ids(_game(at="yingchuan"))["explore:seek"]
    assert option.enabled and option.label.startswith("找事件（體力 6・這裡多半給：")


def test_an_empty_seek_pool_greys_out_for_free(monkeypatch):
    from tianxia import engine as engine_mod

    game = _game(at="yingchuan")
    monkeypatch.setattr(engine_mod, "event_candidates", lambda *a, **k: [])
    option = _ids(game)["explore:seek"]
    assert not option.enabled and option.label == "找事件（這一帶眼下沒什麼事）"


def test_top_kinds_takes_two_unless_one_stands_out():
    assert precise.top_kinds({"名望": 0.5, "銀兩": 0.2}) == ["名望"]
    assert precise.top_kinds({"名望": 0.5, "銀兩": 0.4, "善名": 0.1}) == ["名望", "銀兩"]
    assert precise.top_kinds({"名望": 0.2, "銀兩": 0.1, "善名": 0.05}) == ["名望", "銀兩"]
    assert precise.top_kinds({}) == []


def test_choice_kinds_split_renown_and_skip_stat_points():
    from tianxia.models import Choice, Effect

    c = real_content("weekend")
    choice = Choice(text="x", effect=Effect(stats={"fame": 1, "good": 1, "str": 1, "silver": -5}, stamina=10))
    assert precise.choice_kinds(choice, c) == ("名望", "善名", "裝備與丹藥")
    fight = Choice(text="y", combat="jun_bing", effect=Effect(stats={"xinde": 3}))
    assert precise.choice_kinds(fight, c) == ("經驗", "心得")


def test_after_fight_events_join_seeking_only_in_the_field_with_foes():
    from tianxia.events import event_candidates

    def explore_ids(game):
        return {e.id for e in event_candidates(game.state, game.content, "explore", "common")}

    assert "train_campfire" in explore_ids(_game(at="changshe"))
    assert "train_campfire" not in explore_ids(_game(at="yingchuan"))  # 城鎮
    old = _game(at="changshe")
    old.state.world.precise_actions = False
    assert "train_campfire" not in explore_ids(old)


def test_no_after_fight_event_needs_a_fight_any_more():
    c = real_content("weekend")
    for eid in ("train_fallen_foe", "train_bettors", "train_sore_loser", "train_dropped_letter", "train_old_boxer",
                "train_runaway_cart", "train_campfire", "train_insight", "train_onlooker"):
        assert not c.events[eid].condition.fight_tiers, eid


# ── Task 6：靜心感悟選錯給心得、不鎖（2.9）──


def test_a_wrong_way_of_sensing_gives_xinde_and_does_not_lock():
    from tianxia import insights, sensing

    game = _game(at="yingshui")
    s, c = game.state, game.content
    _press(game, "explore:sense")
    got, scene, loc = sensing.current(s, c)
    assert "下回可以換個做法再試" in sensing.miss_warning(s, c)
    wrong = next(i for i, m in enumerate(got.order) if scene.methods[m].attribute not in insights.pool_attributes(loc, c))
    xinde = s.player.stats.get("xinde", 0)
    game.choose(f"{sensing.PREFIX}{wrong}")
    assert s.player.stats.get("xinde", 0) == xinde + c.config.sense_miss_xinde
    assert s.player.sensing is None and _ids(game)["explore:sense"].enabled


def test_fixture_and_switched_off_content_are_off(content):
    season = fresh_season(content)
    stamp_season(season, content)
    assert not precise.on(content, season)
    c = real_content("weekend")
    c.config.precise_actions = False
    season = fresh_season(c)
    stamp_season(season, c)
    assert not precise.on(c, season)
