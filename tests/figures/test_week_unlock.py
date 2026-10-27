"""功能照週解鎖與三週主題（減法季整合設計 6.6、6.8、4.2；批 5；tianxia/week_unlock.py）：
第 2 週才開的擂台、自創、懸賞榜（鐵匠鋪開季就有）；新手期內照自己的時鐘；開了那一刻一則紀錄、本週卡一句；第 3 週「離贏還差多少」留位；
45 級之後那一句；四格探索的小字「城裡多事」。7 天與 21 天兩種季各走一遍；規則關著一個字都不變。"""
from __future__ import annotations

import random

import pytest

from conftest import no_week_unlock, real_content
from tianxia import arena, bounties, calendar, create, equipment, explore_one, mapdata, roster, rules, week_unlock, weekcard
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

HOUR, DAY = 3600, 86400
MON = 1792339200  # 2026-10-19 週一 00:00（台灣），同 tests/test_checkin.py
TOWN = "yingchuan"  # 城鎮類的地點：懸賞榜、鐵匠鋪在這種地方


def _game(profile, open_at=MON + 10 * HOUR, *, setup=None):
    """照伺服器開一季（store.open_season 蓋章）、建一個走完引導的角色、同步到開季那一刻。"""
    c = real_content(profile)
    c.config.train_event_chance = 0.0
    c.config.jianfa.week_unlock = True  # 7 天版內測關著（企劃者 2026-10-27「先把鎖第二周才能觸發的條件拿掉」）；這裡量的是開著的規則
    if setup is not None:
        setup(c)
    store = open_world()
    store.seed_first_season(c)
    store.open_season(c, open_at)
    game = Game.new(c, "沈浪", rng=random.Random(0), world=store)
    game.client = None
    game.state.player.tutorial_step = len(c.tutorial.steps)
    game.state.player.location = TOWN
    _at(game, open_at)
    return game


def _at(game, now):
    game.world.catch_up_season(game.content, now, random.Random(0))
    game.sync(now)


def _stage(game, stage, after=HOUR):
    """移到第 stage 段（週）開始之後 after 現實秒。"""
    w = game.state.world
    return game.now + (calendar.week_start(stage, game.content, w) - w.time) / game.content.config.time_scale + after


def _open(game):
    s, c = game.state, game.content
    return {"smith": equipment.smith_open(s, c), "arena": arena.here(s, c), "bounties": bounties.board_here(s, c),
            "create": create.allowed(s, c) is None}


def _card(game):
    return weekcard.week_card(game, game.status_data(), game.orders_view())


def test_phase_cuts_the_season_in_three_and_weekcard_still_exports_it():
    assert [week_unlock.phase(w, 3) for w in (1, 2, 3)] == [0, 1, 2]
    assert [week_unlock.phase(w, 12) for w in (1, 4, 5, 8, 9, 12)] == [0, 0, 1, 1, 2, 2]
    assert weekcard.phase is week_unlock.phase


@pytest.mark.parametrize("profile", ["week7", "season21"])
def test_week_two_features_are_locked_on_day_one_and_open_in_stage_two(profile):
    """開季第一天三樣都鎖著（鐵匠鋪不鎖，企劃者 2026-10-27）：入口不給、自創回「第 2 週起才開」、本週卡「為什麼」寫哪幾樣第 2 週開；走到第 2 段（新手期也過了）全開，
    紀錄一行、本週卡一句；再過一個季曆天那一句不寫了，紀錄只寫一次。"""
    g = _game(profile)
    s, c = g.state, g.content
    assert rules.jianfa(c, s.world, "week_unlock")
    assert week_unlock.phase_now(s, c) == 0
    assert _open(g) == {"smith": True, "arena": False, "bounties": False, "create": False}
    assert create.allowed(s, c) == create.LOCKED.format(when=week_unlock.stage_label(1, c, s.world))
    assert create.view(s, c, g.world)["on"] is False
    card = _card(g)
    assert card["theme"] == c.scenario.week_themes[0]
    assert card["unlock"] is None and card["gap"] is None and card["cap"] is None
    assert card["locked"] == week_unlock.LOCKED.format(names="擂台、自創、懸賞榜", when=week_unlock.stage_label(1, c, s.world))
    assert s.player.week_unlocked_at is None and not [e for e in s.journal if e.title == week_unlock.TITLE]

    _at(g, _stage(g, 2))
    s = g.state
    assert week_unlock.phase_now(s, c) == 1
    if roster.newbie(s, c):  # 7 天的季：開季那天 10:00 建的角色，第 3 天 00:00 進第 2 段時 48 小時的新手期還沒過——照自己的時鐘，再等 10 小時
        assert profile == "week7"
        assert _open(g) == {"smith": True, "arena": False, "bounties": False, "create": False}
        assert s.player.week_unlocked_at is None and _card(g)["locked"] is not None
        _at(g, MON + 10 * HOUR + c.config.newbie_real_hours * HOUR + 60)
        s = g.state
    assert not roster.newbie(s, c)
    assert _open(g) == {"smith": True, "arena": True, "bounties": True, "create": True}
    assert create.view(s, c, g.world)["on"] is True
    assert s.player.week_unlocked_at == s.world.time
    entries = [e for e in s.journal if e.title == week_unlock.TITLE]
    assert len(entries) == 1
    assert entries[0].lines == [week_unlock.journal_line(["擂台", "自創", "懸賞榜"], c, s.world)]
    card = _card(g)
    assert card["theme"] == c.scenario.week_themes[1]
    assert card["unlock"] == week_unlock.CARD.format(names="擂台、自創、懸賞榜") and card["locked"] is None

    stamped = s.player.week_unlocked_at
    _at(g, g.now + (week_unlock.CARD_DAYS * DAY / calendar.cal_scale(c, s.world)) / c.config.time_scale + 60)
    s = g.state
    assert s.player.week_unlocked_at == stamped
    assert _card(g)["unlock"] is None
    assert len([e for e in s.journal if e.title == week_unlock.TITLE]) == 1


@pytest.mark.parametrize("profile", ["week7", "season21"])
def test_a_late_joiner_waits_out_the_newbie_period_on_their_own_clock(profile):
    """第 2 段才來的人（6.6「新手期內照自己的時鐘開」）：季已經走到第 2 段，自己的新手期（newbie_real_hours）還沒過，四樣照鎖；
    過了那一刻才開、才寫紀錄。"""
    c = real_content(profile)
    c.config.train_event_chance = 0.0
    c.config.jianfa.week_unlock = True  # 7 天版內測關著；這裡量的是開著的規則
    store = open_world()
    store.seed_first_season(c)
    store.open_season(c, MON + 10 * HOUR)
    probe = Game.new(c, "探路", rng=random.Random(0), world=store)
    probe.client = None
    _at(probe, MON + 10 * HOUR)
    joined = _stage(probe, 2, after=2 * HOUR)
    g = Game.new(c, "沈浪", rng=random.Random(1), world=store)
    g.client = None
    g.state.player.tutorial_step = len(c.tutorial.steps)
    g.state.player.location = TOWN
    _at(g, joined)
    s = g.state
    assert week_unlock.phase_now(s, c) >= 1 and roster.newbie(s, c)
    assert _open(g) == {"smith": True, "arena": False, "bounties": False, "create": False}
    assert s.player.week_unlocked_at is None
    assert _card(g)["locked"] is not None
    hours = c.config.newbie_real_hours
    assert hours > 0
    _at(g, joined + hours * HOUR - 60)
    assert _open(g)["arena"] is False
    _at(g, joined + hours * HOUR + 60)
    s = g.state
    assert _open(g) == {"smith": True, "arena": True, "bounties": True, "create": True}
    assert s.player.week_unlocked_at == s.world.time
    assert len([e for e in s.journal if e.title == week_unlock.TITLE]) == 1


@pytest.mark.parametrize("profile", ["week7", "season21"])
def test_stage_three_writes_the_win_gap_on_the_card_and_the_world_map(profile):
    """第 3 段：本週卡多一句「離贏還差多少」，輿圖天下層同一句；前兩段沒有。批 3c 接上之後（四勝利開著，這兩種季都開）寫兩軍各自離
    勝利條件還差多少（wins.gap_line）；以前這裡是留位、鎖的是結局門檻那一句（rules.stance_rule_note），四勝利關著的季照舊是它
    （tests/test_sides_card.py::test_last_week_says_how_far_from_winning）。"""
    g = _game(profile)
    assert _card(g)["gap"] is None and g.map_state()["gap"] is None
    _at(g, _stage(g, 2))
    assert _card(g)["gap"] is None
    _at(g, _stage(g, 3))
    s, c = g.state, g.content
    from tianxia import wins

    note = wins.gap_line(c, rules.stances(s, c))
    assert note and "還差" in note
    card = _card(g)
    assert card["theme"] == c.scenario.week_themes[2] and card["gap"] == note
    assert g.map_state()["gap"] == note


def test_the_switch_off_changes_nothing():
    """子開關關著（no_week_unlock）：開季第一天四樣都開、沒有鎖著那一句、不蓋章、不寫紀錄；本週卡的主題句照舊。"""
    g = _game("week7", setup=no_week_unlock)
    s, c = g.state, g.content
    assert not rules.jianfa(c, s.world, "week_unlock")
    assert _open(g) == {"smith": True, "arena": True, "bounties": True, "create": True}
    card = _card(g)
    assert card["theme"] == c.scenario.week_themes[0] and card["locked"] is None and card["unlock"] is None
    _at(g, _stage(g, 2))
    assert g.state.player.week_unlocked_at is None
    assert not [e for e in g.state.journal if e.title == week_unlock.TITLE]


def test_a_season_without_the_jianfa_stamp_locks_nothing(content):
    """測試內容（Config.jianfa 關著、季上沒有章）：open 一律真，一個字都不變。"""
    g = Game.new(content, "甲", rng=random.Random(0))
    g.client = None
    s = g.state
    assert all(week_unlock.open(s, content, f) for f in week_unlock.WEEK2)
    assert week_unlock.locked_line(s, content, ["打造"]) is None and week_unlock.card_line(s, content, ["打造"]) is None


def test_names_follow_what_this_season_really_has():
    """紀錄與那一句只列這一季真的開著的：擂台關了就不寫擂台；一樣都沒有時什麼都不寫。"""
    def off(c):
        c.config.arena.enabled = False

    g = _game("week7", setup=off)
    assert g.week_unlock_names() == ["自創", "懸賞榜"]
    assert "擂台" not in _card(g)["locked"]
    assert week_unlock.card_line(g.state, g.content, []) is None and week_unlock.locked_line(g.state, g.content, []) is None


def test_the_level_cap_sentence_appears_at_forty_five_when_the_gates_are_on():
    g = _game("week7")
    s, c = g.state, g.content
    assert week_unlock.cap_level(c) == 45
    assert _card(g)["cap"] is None
    s.player.member.level = 45
    assert _card(g)["cap"] == week_unlock.CAP_NOTE
    c.config.jianfa.drill_gates = False
    assert _card(g)["cap"] is None


def test_mostly_here_names_what_this_place_mostly_gives():
    """四格探索的小字（6.3）：城鎮「城裡多事」；伺服器的 /api/main 帶 mostly；在路上沒有。"""
    import server

    g = _game("week7")
    s, c = g.state, g.content
    assert mapdata.mostly_here(s, c) == "城裡多事"
    assert server.main_view(g)["mostly"] == "城裡多事"
    kinds = {mapdata.mostly_here(_relocate(g, loc_id), c) for loc_id in c.locations}
    # 探索一顆開著（week7）的字照表算（explore_one.hint_in，2e FB-882：寺是「寺裡多事」）；雲端批 5 那一套（MOSTLY_HERE）是關著時的
    tables = {explore_one.hint_in(t) for t in c.config.jianfa.explore_tables}
    assert kinds <= tables | {""} and len(kinds) >= 3
    g.state.player.location = TOWN
    g.state.player.journey = _journey(g)
    assert mapdata.mostly_here(g.state, c) == ""
    assert "mostly" not in server.main_view(g)


def _relocate(game, loc_id):
    game.state.player.location = loc_id
    return game.state


def _journey(game):
    """一段在路上：照 Game.travel 真的出發一次最準，拿它記的 journey。"""
    to = next(iter(game.content.locations[TOWN].connections))
    game.travel(to)
    j = game.state.player.journey
    assert j is not None
    return j


def test_the_week7_profile_has_the_week_lock_off_for_the_closed_beta():
    """7 天版內測先不鎖第 2 週（企劃者 2026-10-27）：子開關讀的是此刻的設定、不是開季的章，重開伺服器就生效、不必換季。"""
    c = real_content("week7")
    assert c.config.jianfa.enabled and not c.config.jianfa.week_unlock
    store = open_world()
    store.seed_first_season(c)
    store.open_season(c, MON + 10 * HOUR)
    g = Game.new(c, "沈浪", rng=random.Random(0), world=store)
    g.client = None
    g.state.player.tutorial_step = len(c.tutorial.steps)
    g.state.player.location = TOWN
    _at(g, MON + 10 * HOUR)
    assert week_unlock.phase_now(g.state, c) == 0 and roster.newbie(g.state, c)
    assert _open(g) == {"smith": True, "arena": True, "bounties": True, "create": True}
    assert _card(g)["locked"] is None
