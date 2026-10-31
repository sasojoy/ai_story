"""正式季整合第 3 批：一類一顆（設計第二章；12.3 第 5～13 條照 PM 提案）。每一顆鈕只給一類東西、按了一定拿到那一類。
開關 Config.precise_actions 照開季蓋章；測試內容關著，這裡用正式內容（週末設定）。"""
from __future__ import annotations

import random

import pytest

from conftest import real_content, renown_unscaled
from jianfa_kit import classic_explore

from tianxia import precise
from tianxia.engine import Game
from tianxia.sqlite_world import open_world
from tianxia.world_state import fresh_season, stamp_season

HOUR = 3600
MON = 1792339200  # 2026-10-19 週一 00:00（台灣）
NOW = MON + 10 * HOUR


def _game(profile="week7", at="yingchuan", faction=None, stamina=250.0, opened=True):
    c = classic_explore(renown_unscaled(real_content(profile)))  # 求見門檻照原數（名望 15）；一類一顆的探索與練功（減法季探索一顆之前）
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
    c = classic_explore(renown_unscaled(real_content("week7")))
    season = fresh_season(c)
    stamp_season(season, c)
    assert season.precise_actions and precise.on(c, season)


def test_unstamped_season_keeps_the_old_rules():
    c = classic_explore(renown_unscaled(real_content("week7")))
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


@pytest.mark.smoke
def test_practice_always_fights_one_and_is_unlimited():
    game = _game(at="changshe")
    p = game.state.player
    option = _ids(game)["explore:practice"]
    assert option.enabled and option.label.startswith("尋敵（體力 6") and "經驗" not in option.label  # 鈕上不寫給多少（設計 9.1）
    for n in range(1, 6):
        p.stamina = 250.0
        game.choose("explore:practice")
        assert len(game.state.battles) == n and p.stamina <= 244 + 0.01 and p.duel is None
        assert game.state.pending_event is None  # 練功之後不接戰後事件


def test_practice_greys_out_where_there_is_no_one_to_fight():
    game = _game(at="yingchuan")
    game.content.config.training.enabled = False  # 城裡操練開著時那一格是操練（tests/test_training.py），這裡測練功收在探索裡的舊樣子
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
    s.player.duel_tally[duel_rules.week_key(s, c, boss.id)] = c.config.duel.per_boss_week  # 7 天季：每段 per_boss_week 次
    option = _ids(game)["explore:practice"]
    # FB-672：次數用完那一句帶頭目的名字（「他」→「頭目某某」，名字是黃巾看到的那一面；tests/test_practice_spots.py）
    assert not option.enabled and "這一段頭目衛重不再現身" in option.label


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


# ── Task 5：找事件的併池、空池（2.7；鈕上的偏向企劃者 2026-10-19 拿掉了，設計 9.1）──


def test_seek_does_not_say_what_it_gives():
    option = _ids(_game(at="yingchuan"))["explore:seek"]
    assert option.enabled and option.label == "找事件（體力 6）"




def test_an_empty_seek_pool_greys_out_for_free(monkeypatch):
    from tianxia import engine as engine_mod

    game = _game(at="yingchuan")
    monkeypatch.setattr(engine_mod, "event_candidates", lambda *a, **k: [])
    option = _ids(game)["explore:seek"]
    assert not option.enabled and option.label == "找事件（這一帶眼下沒什麼事）"






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
    c = classic_explore(renown_unscaled(real_content("week7")))
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


# ── Task 8：假人與整季機器人（9.2）──


def test_the_season_bot_practices_when_it_wants_exp():
    from tianxia import bot

    ids = {"explore:gather", "explore:seek", "explore:practice"}
    assert bot.explore_choice(ids, want="exp") == "explore:practice"
    assert bot.explore_choice(ids) == "explore:gather"  # 打探照舊找素材（練功不算打探）
    assert bot.explore_choice({"explore:gather"}, want="exp") == "explore:gather"


def test_server_bots_practice_for_exp_and_gather_only_when_short():
    from tianxia import bot_policy
    from tianxia.state import BotProfile

    game = _game(at="changshe")
    profile = BotProfile(personality="普通", seed=1, faction=None, season_number=1)
    opts = _ids(game)
    practice = bot_policy.score(game, opts["explore:practice"], profile)
    gather = bot_policy.score(game, opts["explore:gather"], profile)
    assert practice == bot_policy.PRACTICE_SCORE and gather < practice


def test_the_season_bot_does_not_loop_on_a_refused_sect():
    from tianxia import bot

    game = _game(at="yingchuan_academy")
    options = [o for o in game.options() if o.enabled]
    assert any(o.id == "sect:yingchuan_join" for o in options)
    game.state.player.seen_events.add("yingchuan_join")
    rng = random.Random(0)
    assert all(bot.pick(game, game.options(), rng) != "sect:yingchuan_join" for _ in range(50))


def test_fixture_and_switched_off_content_are_off(content):
    season = fresh_season(content)
    stamp_season(season, content)
    assert not precise.on(content, season)
    c = classic_explore(renown_unscaled(real_content("week7")))
    c.config.precise_actions = False
    season = fresh_season(c)
    stamp_season(season, c)
    assert not precise.on(c, season)


# ── 第 3 批畫面（設計 9.1 第 1 組乙）：應召獨立一行 ──


def _summons_page(monkeypatch, precise_on=True):
    from test_prologue_web import run, with_reveal

    import server
    from tianxia import ranks

    game = _game(at="luoyang_road")
    game.state.world.precise_actions = precise_on
    monkeypatch.setattr(ranks, "summons_event", lambda *a, **k: next(iter(game.content.events)))
    m = with_reveal(server.main_view(game), ["all"])
    return m, run(m, "return H.pageJianghu();")


def test_summons_is_a_gold_strip_above_the_action_bar(monkeypatch):
    import webharness

    if webharness.NODE is None:
        return
    m, html = _summons_page(monkeypatch)
    assert m["precise"]
    strip = html.index('class="summons-strip"')
    assert strip < html.index('class="act-bar"') and 'data-act="choose" data-id="act:summons"' in html
    assert "<b>應召晉升</b><small>召見在此・不花體力</small>" in html
    assert html.count('data-id="act:summons"') == 1  # 不再收在「此地還能做」裡


def test_summons_stays_in_the_fold_when_precise_is_off(monkeypatch):
    import webharness

    if webharness.NODE is None:
        return
    m, html = _summons_page(monkeypatch, precise_on=False)
    assert not m["precise"] and 'class="summons-strip"' not in html and 'data-id="act:summons"' in html


# ── 第 3 批 QA 之後（FB-420、FB-421、戰後事件的成數）──


def _strike(game, at="changshe"):
    from tianxia.state import Bounty

    b = Bounty(id="b1", kind="strike", faction="huang", week=1, expires=1e12, silver=20, deeds=1,
               location=at, squad="jun_bing", takers=["沈浪"])
    game.state.world.bounties.append(b)
    return b


def test_a_strike_bounty_says_practice_where_precise_is_on():
    """FB-420：找素材不打仗了，討伐的說明寫練功（懸賞卡、告示、紙上都是這一句）。"""
    from tianxia import bounties

    game = _game()
    b = _strike(game)
    line = bounties.how(game.content, b, game.state)
    assert "尋敵" in line and "找素材" not in line
    rows = bounties.status(game.state, game.content, game.world)
    assert any(r["id"] == "b1" and r["how"] == line for r in rows)
    game.state.world.precise_actions = False  # 沒蓋章的季照舊
    assert "找素材撞上" in bounties.how(game.content, b, game.state)


def test_the_social_list_does_not_say_brushed_off():
    """FB-421：交友打開的名單寫「說話」「見不到」，不寫「求見」「會被打發」。"""
    game = _game(at="wan_city")
    game.choose("act:call")
    text = game.scene_text()
    assert "**交友**" in text and "名望不夠的見不到" in text and "打發" not in text


def _seek_draws(game, n=400):
    from tianxia.events import note_round, pick_event

    rng, s, c = random.Random(3), game.state, game.content
    lent = 0
    for _ in range(n):
        event = pick_event(s, c, "explore", rng, "common")
        note_round(s, c, event, "explore")
        lent += precise.borrowed(event, "explore")
    return lent / n


def test_after_fight_events_take_at_most_three_tenths_of_a_seek_pool():
    """PM 2026-10-19：九則借進找事件的戰後事件在一處池子裡合起來最多三成（QA 量到潁川郊野佔七成），照舊走防重複。"""
    share = _seek_draws(_game(at="yingchuan_wilds"))
    assert 0.2 < share <= 0.36


def test_a_pool_of_only_the_borrowed_ones_is_not_capped():
    from tianxia.events import _capped_group, event_candidates

    game = _game(at="yingchuan_wilds")
    lent = [e for e in event_candidates(game.state, game.content, "explore", "common") if precise.borrowed(e, "explore")]
    assert len(lent) >= 2 and _capped_group(game.state, game.content, lent, "explore", random.Random(0)) == lent


def test_a_ranger_reads_only_practice_on_a_strike_bounty():
    """散人不出陣：討伐只寫練功（STRIKE_PRACTICE）；投靠了陣營的人寫練功或出陣（FB-420 之後 QA）。"""
    from tianxia import bounties

    game = _game()
    b = _strike(game)
    assert game.state.player.faction is None
    assert bounties.how(game.content, b, game.state).startswith("到長社尋敵打贏")
    game.state.player.faction = "guan"
    assert "尋敵或出陣攻打贏" in bounties.how(game.content, b, game.state)


def test_the_howto_follows_precise_actions_and_old_seasons_keep_every_word():
    """FB-422：一類一顆生效的季，玩法說明的探索、練功、交友、意境、名望、情誼照新規則寫；沒蓋章的季跟以前一字不差。"""
    from tianxia import explore_modes, howto
    from tianxia.world_state import fresh_season

    c = classic_explore(renown_unscaled(real_content("week7")))
    season = fresh_season(c)
    stamp_season(season, c)
    text = howto.page(c, season, recruitable=False)
    assert "一定撿得到素材，不打仗" in text and f"**{explore_modes.NAMES['practice']}**" in text and "不限次數" in text
    assert "撞上怪" not in text and "會打發你" not in text and "過一陣子才悟得出" not in text and "求見名單" not in text
    assert f"選錯了得 {c.config.sense_miss_xinde} 心得" in text and "交友名單上也有" in text and "不夠的見不到" in text
    season.precise_actions = False
    old = howto.page(c, season, recruitable=False)
    assert "撞上怪" in old and "會打發你" in old and "過一陣子才悟得出" in old and "求見名單上也有" in old
    assert f"**{explore_modes.NAMES['practice']}**" not in old
