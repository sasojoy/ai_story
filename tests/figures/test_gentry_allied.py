"""第一季豪強分屬兩軍（docs/superpowers/specs/2026-10-15-第一季豪強分屬兩軍-design.md）。

用真實內容的 7 天季（第一季規則開著就是豪強分屬兩軍；2026-10-31 開關與豪強第三方的舊規則連它們的對照測試一起拿掉）。"""
from __future__ import annotations

import random

import pytest

from conftest import real_content
from tianxia import allied, calendar, rules
from tianxia.engine import Game
from tianxia.state import PlayerState, WorldState


@pytest.fixture
def wk():
    c = real_content("week7")
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


# ── Task 1：開關、蓋章、敵我與名冊鍵 ─────────────────────────────


def test_the_week7_profile_turns_it_on(wk):
    assert [f.allies for f in wk.scenario.factions if f.id == "haoqiang"] == [["guan", "huang"]]


def test_old_saves_load_without_the_new_fields():
    p = PlayerState(name="甲", location="x", stats={}, stamina=0)
    assert (p.ally, p.pending_ally) == (None, None)
    assert WorldState.model_validate({"haoqiang_allied": True}).season_one is False  # 2026-10-31 拿掉的章：舊存檔裡的鍵讀進來時丟掉


def test_stamp_and_rule(wk):
    game = _game(wk)
    assert allied.on(wk, game.state.world) and rules.haoqiang_allied(wk, game.state.world)


def test_fourteen_day_season_keeps_the_third_party():
    c = real_content()
    c.config.auto_open_first_season = True
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
    assert "geju" not in [t.id for t in wk.scenario.trends]  # 割據 2026-10-31 連大勢、每小時的推力一起拿掉
    assert "geju" not in w.trends


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
    assert "geju" not in game.state.world.trends
    data = game.status_data()
    assert set(data["stances"]) == {"guan", "huang"} and "haoqiang" not in data["stance_notes"]


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


def test_gentry_manors_are_neither_sides_ground(wk):
    """豪強的投靠點不在戰線上，豪強分屬兩軍的季不算哪一軍的地盤：誰在那裡買東西都是原價（不會讓依附的豪強在自己莊院付貴兩成）。"""
    from tianxia import team, territory

    game = _game(wk, faction="haoqiang", ally="guan", at="cao_manor")
    assert team._price_here(game.state, wk) == 1.0
    assert territory.price_factor(game.state.world, wk, "huang", "cao_manor") == 1.0
    assert territory.price_factor(game.state.world, wk, "guan", "changshe") == wk.config.territory.own_price


def test_donate_goes_to_the_side_stock(wk):
    from tianxia import economy

    game = _game(wk, faction="haoqiang", ally="guan", at="zhuo_militia_hall")
    assert game._at_own_base()
    game.state.player.location = "changshe"  # 依附那一軍的投靠點也算自家大本營
    assert game._at_own_base()
    game.state.player.location = "huangjin_camp"
    assert not game._at_own_base()
    target = economy.donate_target(wk, game.state.world, "guan", "zhuo_militia_hall")
    assert target is not None and target[0] != "geju" and target[1] == -1
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


def test_give_bounties_skip_the_gentry(wk):
    from tianxia import bounties

    game = _settled(_game(wk))
    game.state.world.time = calendar.day_start(2, wk, game.state.world)  # 7 天季的求兵在雙數天 00:00 掛（bounties.issue_day）
    bounties.issue_day(game.state, wk, 2)
    gives = [b.faction for b in game.state.world.bounties if b.kind in bounties.GIVE_KINDS]
    assert gives and "haoqiang" not in gives


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
    assert game.admin_start_showdown("changshe_fire", 1000.0)[0] == "🛡️ 【全服戰報】長社火攻的集結號角已經吹響！"  # 後面接龍頭上陣那一句
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


# ── Task 7：豪強升到第 3 階為止 ─────────────────────────────


def test_gentry_stops_at_rank_three(wk):
    from tianxia import ranks

    game = _game(wk, faction="haoqiang", ally="guan")
    p = game.state.player
    p.rank, p.contrib = 3, 10 ** 6
    p.opp_done = [o.id for o in wk.opportunities if o.faction == "haoqiang"]
    assert allied.rank_cap(game.state, wk) == 3
    assert ranks.check_summons(game.state, wk) == []
    assert p.summons is None and not p.qualified
    assert game._summons_plan(game) == ("（甲已經升到頂了。）", None)  # 管理者「立刻替他發召見」也一樣


def test_armies_still_reach_rank_four(wk):
    from tianxia import ranks

    army = _game(wk, name="乙", faction="guan")
    p = army.state.player
    p.rank, p.contrib = 3, 10 ** 6
    p.opp_done = [o.id for o in wk.opportunities if o.faction == "guan"]
    assert allied.rank_cap(army.state, wk) is None
    assert ranks.check_summons(army.state, wk)  # 召見第 4 階，或說一次沒人能出面


def test_gentry_titles_go_up_to_three(wk):
    from tianxia import ranks

    game = _game(wk, faction="haoqiang", ally="guan")
    game.state.player.rank = 3
    assert ranks.title(wk, game.state) == "地方豪強"


def test_seal_and_battles_read_the_side_from_the_roster(wk):
    game = _game(wk, faction="haoqiang", ally="huang")
    game._record_faction()
    assert game.world.faction_of("甲") == "huang"


# ── Task 8：換邊與互換都是叛投 ─────────────────────────────


def _defect_labels(game):
    return [o.label for o in game.options() if o.id.startswith("defect:")]


def test_gentry_to_pure_army_on_the_same_side_is_a_defection(wk):
    game = _game(wk, faction="haoqiang", ally="guan", at="changshe")
    assert _defect_labels(game) == ["改投官軍"]
    game.state.player.rank = 3
    game.choose("defect:guan")
    game.choose("defect:confirm")
    p = game.state.player
    assert (p.faction, p.ally, p.defected, p.rank) == ("guan", None, True, 0)
    texts = [r.text for r in game.state.world.rumors if r.layer == "faction"]
    assert any("改投官軍" in t for t in texts) and not any("叛離" in t for t in texts)


def test_pure_army_at_a_gentry_base(wk):
    game = _game(wk, faction="guan", at="zhuo_militia_hall")
    assert _defect_labels(game) == ["改投地方豪強（依附官軍）", "叛投地方豪強（依附黃巾軍）"]
    game.choose("defect:haoqiang:huang")
    game.choose("defect:confirm")
    p = game.state.player
    assert (p.faction, p.ally, p.defected) == ("haoqiang", "huang", True)


# ── Task 9：假人選人少的一邊、照那一邊行動 ───────────────────────────


def test_pick_side_takes_the_smaller():
    ids = ["faction:ally:guan", "faction:ally:huang", "faction:cancel"]
    assert allied.pick_side("甲", ids, {"guan": 5, "huang": 3}) == "faction:ally:huang"
    assert allied.pick_side("甲", ids, {"guan": 2, "haoqiang@guan": 1, "huang": 4}) == "faction:ally:guan"
    ties = {allied.pick_side(n, ids, {}) for n in "甲乙丙丁戊己庚辛壬癸"}
    assert ties == {"faction:ally:guan", "faction:ally:huang"}  # 一樣多照名號雜湊，兩邊都有人
    assert allied.pick_side("甲", ["act:explore"], {}) is None


def test_gentry_bot_picks_the_smaller_side(wk):
    from tianxia import bot_policy
    from tianxia.state import BotProfile

    game = _game(wk, name="假人", at="zhuo_militia_hall")
    game.world.record_faction("官一", "guan")
    profile = BotProfile(personality="普通", seed=0, faction="haoqiang", season_number=game.world.get_season_number())
    game.state.player.bot = profile
    for _ in range(5):  # 投靠豪強 → 挑一邊 → 確定
        bot_policy.take_turn(game, profile, random.Random(0))
        if game.state.player.faction is not None:
            break
    assert (game.state.player.faction, game.state.player.ally) == ("haoqiang", "huang")


def test_gentry_bot_after_the_sect_picks_too(wk):
    from tianxia import bot_policy
    from tianxia.state import BotProfile

    game = _game(wk, name="假人", faction="haoqiang", at="cao_manor")
    game.world.record_faction("黃一", "huang")
    profile = BotProfile(personality="普通", seed=0, faction="haoqiang", season_number=game.world.get_season_number())
    game.state.player.bot = profile
    assert bot_policy.pick(game, game.options(), profile, random.Random(0)) == "faction:ally:guan"


def test_season_bot_menu_has_a_side_pick(wk):
    from tianxia import bot

    game = _game(wk, faction="haoqiang", at="cao_manor")
    game.world.record_faction("官一", "guan")
    assert bot.pick(game, game.options(), random.Random(0)) == "faction:ally:huang"


# ── Task 10：引薦人與提示、玩法說明、輿圖 ───────────────────────────


def test_recruiter_has_an_allied_version(wk):
    from tianxia import enlist

    game = _game(wk, faction="haoqiang", ally="guan")
    who = enlist.recruiter(game.state, wk)
    assert "聲威就掉一大截" in who.done  # 14 天的季照用原句
    assert "聲威就掉一大截" not in enlist.line(who, "done", game.state, wk)
    assert "第三階" in enlist.line(who, "done", game.state, wk)
    assert enlist.line(who, "intro", game.state, wk) == who.intro  # 沒寫 allied 的那幾句照舊


def test_hints_have_an_allied_version(wk):
    from tianxia import hints as hint_rules

    game = _game(wk, faction="haoqiang", ally="guan")
    note = hint_rules.note_for(game.state, wk, "h_showdown")
    assert note is not None and "臨時投效" not in note.text and "加入" in note.text


def test_howto_has_no_third_party(wk):
    game = _game(wk, faction="haoqiang", ally="guan")
    page = game.howto_text()
    assert "割據" not in page and "攪局" not in page and "陣營不是交戰的兩軍時" not in page
    assert "依附" in page and "第 3 階" in page
    war = game.status_data()["war_help"]
    assert not any("割據" in line for lines in war.values() for line in lines)


def test_map_state_lists_two_sides(wk):
    game = _game(wk, faction="haoqiang", ally="guan")
    st = game.map_state()
    assert st["sides"] == ["guan", "huang"] and st["faction"] == "guan"


def test_gentry_bot_heads_for_its_side_front(wk):
    from tianxia import bot_policy
    from tianxia.state import BotProfile

    game = _game(wk, name="假人", faction="haoqiang", ally="guan")
    profile = BotProfile(personality="普通", seed=0, faction="haoqiang", season_number=game.world.get_season_number())
    assert bot_policy._goals(game, profile) == game._goals()
    assert bot_policy._losing_front(game, "guan") is not None
