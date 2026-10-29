"""減法季屬性五段的引擎接線（減法季整合設計 4.5；主機側計畫 Task 2-5）：升級不再給點，第 10、20、30、40、50 級各 5 點；每一點的效果加倍
（威力 6%、閃避 4%、感悟 6、持有 4 格），氣血上限、狀態列、打起來同一個數；配點那一刻寫前後；境界卡 main.milestone；假人照路配滿一項；
江湖水漲的事件加難乘 event_bump_scale；戰報結果段寫屬性起作用的那一句。純規則在 tests/test_stat_milestones.py。正式設定 2026-10-28 起 `stat_milestones` 關著（升級照舊每級給點，FB-899），
所以這個檔每一局都自己把子開關打開（`jianfa_game(stat_milestones=True)`）；關著時怎麼走在 tests/core/test_jianfa_switch.py。用正式內容，整個檔標 slow。"""
from __future__ import annotations

import random
from unittest import mock

import pytest
from jianfa_kit import jianfa_game, plain_game, ready

from tianxia import bot, explore_one, growth, library, rise, sensing, team
from tianxia.battlelog import stat_notes
from tianxia.encounter import EncounterResult

pytestmark = pytest.mark.slow


def test_points_come_only_at_the_five_milestones():
    game = ready(jianfa_game(stat_milestones=True), side="guan", loc="yingshui")
    s, c = game.state, game.content
    assert team.level_points(s, c, 1, 9) == 0
    assert team.level_points(s, c, 9, 10) == 5 and s.player.milestone_due == 10
    assert team.level_points(s, c, 1, 50) == 25 and s.player.milestone_due == 50
    plain = ready(plain_game(), side="guan", loc="yingshui")
    assert team.level_points(plain.state, plain.content, 1, 10) == 9 and plain.state.player.milestone_due == 0


def test_levelling_up_through_a_fight_grants_the_milestone_and_the_card():
    import server

    game = ready(jianfa_game(stat_milestones=True), side="huang", loc="guan_camp")  # 北軍五校：經驗 35
    p = game.state.player
    p.member.level, p.member.exp = 9, team.level_cost(game.content.config, 9) - 1
    points = p.stat_points
    with mock.patch.object(explore_one, "draw", return_value="encounter"), \
            mock.patch.object(team, "fight", return_value=EncounterResult(tier="大勝", margin=50, our_power=200, difficulty=40)):
        game.choose("act:explore")
    assert p.member.level == 10 and p.stat_points == points + 5
    view = server.main_view(game)
    assert view["milestone"] == {"level": 10, "points": p.stat_points, "title": growth.milestone_title(10)}
    for _ in range(p.stat_points):
        game.allocate_stat("str")
    assert "milestone" not in server.main_view(game) and p.milestone_due == 0
    plain = ready(plain_game(), side="guan", loc="yingshui")
    assert "milestone" not in server.main_view(plain)


def test_level_fifty_comes_only_from_a_fight():
    """第 50 級那一次只靠打出來的經驗（45 級以後不是仗的換心得，三道閘）。"""
    game = ready(jianfa_game(stat_milestones=True), side="guan", loc="guan_camp")
    p = game.state.player
    p.member.level, p.member.exp = 49, team.level_cost(game.content.config, 49) - 1
    game._drill_gains(game.content.squads["liangzhou_cavalry"], 1.0, "hold")
    assert p.member.level == 49
    game._drill_gains(game.content.squads["liangzhou_cavalry"], 1.0, "camp_spar")
    assert p.member.level == 50 and p.milestone_due == 50


def test_each_point_weighs_double_in_a_jianfa_season():
    on = ready(jianfa_game(stat_milestones=True), side="guan", loc="yingshui")
    off = ready(plain_game(), side="guan", loc="yingshui")
    c_on, c_off = on.content, off.content
    assert team.stat_bonus(c_on, 10, on.state.world) == pytest.approx(0.30)
    assert team.stat_bonus(c_off, 10, off.state.world) == pytest.approx(0.15)
    assert team.stat_bonus(c_on, 10) == pytest.approx(0.15)  # 沒給 season 照舊
    for game in (on, off):
        game.state.player.stats.update(agi=10, lore=10, wis=10)
    assert team.dodge_chance(on.state, c_on) == pytest.approx(0.20) and team.dodge_chance(off.state, c_off) == pytest.approx(0.10)
    base = library.holding_cap(c_on, 1, 5)
    assert library.cap_of(on.state, c_on) - on.state.player.holding_bonus == base + 5 * 4
    assert library.cap_of(off.state, c_off) - off.state.player.holding_bonus == base + 5 * 2
    loc = c_on.locations["yingshui"]
    for game in (on, off):
        game.state.player.stats["wis"] = 6  # 悟性 10 會頂到感悟的上限，看不出差
    assert sensing.rate(on.state, c_on, loc) - sensing.rate(off.state, c_off, loc) == 6 - 3


def test_hp_cap_is_one_number_everywhere():
    """根骨的氣血上限加倍：狀態列、本人氣血與上限、決戰的池子、角色卡都是同一個數（沒傳 season 的漏網之魚會讓兩邊對不上）。"""
    from tianxia import skillview

    game = ready(jianfa_game(stat_milestones=True), side="guan", loc="yingshui")
    p = game.state.player
    p.stats["con"] = 12
    cap = game._player_hp_and_cap()[1]
    assert game.status_data()["hp_max"] == round(cap) == round(game._battle_neili_cap())
    assert f"/{cap:.0f}" in skillview.member_card(game.state, game.content, game.world, team.PLAYER)
    off = ready(plain_game(), side="guan", loc="yingshui")
    off.state.player.stats["con"] = 12
    assert cap > off._player_hp_and_cap()[1]


def test_allocating_says_what_the_point_did():
    game = ready(jianfa_game(stat_milestones=True), side="guan", loc="yingshui")
    p = game.state.player
    p.stat_points = 1
    p.member.wugong_level = 10  # 威力大一點，+6% 在整數上看得出來
    msgs = game.allocate_stat("str")
    line = msgs[0]
    assert line.startswith("臂力 5 → 6：武學威力 +6%，此刻全隊 ") and "→" in line.split("此刻全隊")[1]
    assert game.state.journal[0].lines == [line] and game.state.journal[0].changes == ["臂力 +1"]
    off = ready(plain_game(), side="guan", loc="yingshui")
    off.state.player.stat_points = 1
    assert off.allocate_stat("str") == ["臂力 +1"]


def test_the_stat_line_shows_numbers_in_a_jianfa_season():
    from tianxia import skillview

    game = ready(jianfa_game(stat_milestones=True), side="guan", loc="yingshui")
    game.state.player.stats["str"] = 8
    uses = dict(skillview.stat_uses(game.content, game.state))
    assert uses["臂力"] == "武學威力 +18%"
    off = ready(plain_game(), side="guan", loc="yingshui")
    assert dict(skillview.stat_uses(off.content, off.state)) == dict(skillview.stat_uses(off.content))


def test_bots_fill_one_stat_before_the_next():
    game = ready(jianfa_game(name="甲客", stat_milestones=True), side="guan", loc="yingshui")
    p = game.state.player
    p.stat_points = 12
    path = growth.stat_path(p.name)
    bot.allocate_points(game, random.Random(0))
    cap = game.content.config.stat_cap
    assert p.stats[path[0]] == cap and p.stats[path[1]] == 5 + 12 - (cap - 5) and p.stat_points == 0


def test_event_bump_is_scaled_down():
    on = ready(jianfa_game(stat_milestones=True), side="guan", loc="yingshui", level=40)
    off = ready(plain_game(), side="guan", loc="yingshui", level=40)
    assert rise.event_bump(off.state, off.content) > 0
    assert rise.event_bump(on.state, on.content) == 0  # 量過定 0（主機側計畫 Task 2-6）
    on.content.config.jianfa.event_bump_scale = 0.5
    assert rise.event_bump(on.state, on.content) == rise.event_bump(off.state, off.content) * 0.5


def test_the_battle_report_says_when_strength_carried_the_fight():
    game = ready(jianfa_game(stat_milestones=True), side="guan", loc="yingshui")
    game.state.player.stats["str"] = 13  # +48%：佔三成以上
    assert stat_notes(game.state, game.content, "wild") == ["臂力沉，這一擊多了五成。"]
    game.state.player.stats["str"] = 9
    assert stat_notes(game.state, game.content, "wild") == []
    off = ready(plain_game(), side="guan", loc="yingshui")
    off.state.player.stats["str"] = 15
    assert stat_notes(off.state, off.content, "wild") == []
