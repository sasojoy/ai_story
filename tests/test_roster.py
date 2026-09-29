import json

import pytest

from tianxia import roster, team
from tianxia.engine import Game
from tianxia.models import Check
from tianxia.rules import learn_skill
from tianxia.save import load_game
from tianxia.state import Member
from tianxia.world import check_thresholds


def join(game, *keys, level=1):
    """測試用：直接讓這些人入門（正式的取得管道見下面「取得管道」一節）。"""
    for key in keys:
        game.state.player.members[key] = Member(level=level)
        game.state.player.loadouts[key] = [None, None]


def teams(game):
    return [list(t.members) for t in game.state.player.teams]


# ── 隊伍數與統御上限 ─────────────────────────────────────


def test_new_game_has_the_main_team_and_empty_teams(game):
    assert teams(game) == [["player", "mate"], [], [], []]
    assert (game.team_count(), game.command_cap()) == (2, 15)
    assert roster.team_command(game.state, game.content, 0) == 8  # 你 5 ＋ 韓鐵 3
    assert roster.bench(game.state, game.content) == []


@pytest.mark.parametrize("reached, count, cap", [(0, 2, 15), (1, 3, 18), (2, 4, 20), (3, 4, 20)])
def test_teams_and_cap_follow_the_furthest_act(game, reached, count, cap):
    game.state.world.act_reached = reached
    assert (game.team_count(), game.command_cap()) == (count, cap)


def test_branch_storyline_does_not_close_teams(game):
    w = game.state.world
    w.trends["kou"] = 60  # 第一幕 → 第二幕
    check_thresholds(game.state, game.content)
    assert (w.storyline, w.act, w.act_reached) == ("main", 1, 1)
    w.revealed.add("bao")  # 寶藏線浮現：主線改寫，幕數歸零
    check_thresholds(game.state, game.content)
    assert (w.storyline, w.act, w.act_reached) == ("treasure", 0, 1)
    assert (game.team_count(), game.command_cap()) == (3, 18)


def test_team_names_and_when_they_open(content):
    assert [roster.team_name(i) for i in range(4)] == ["本隊", "第二隊", "第三隊", "第四隊"]
    assert [roster.opens_at(content, i) for i in range(5)] == [
        "第一幕開放", "第一幕開放", "第二幕開放", "第三幕開放", "未開放",
    ]


def test_roster_lists_the_player_then_by_tier_then_by_joining(game):
    join(game, "pupil", "hero", "scholar", "sage")
    assert roster.roster(game.state, game.content) == ["player", "sage", "hero", "mate", "scholar", "pupil"]


# ── 換人 ──────────────────────────────────────────────


def test_put_a_bench_member_into_the_second_team(game):
    join(game, "pupil")
    assert roster.bench(game.state, game.content) == ["pupil"]
    assert game.set_member(1, 0, "pupil") == ["小六編入第二隊（第二隊統御 2／15）"]
    assert teams(game)[:2] == [["player", "mate"], ["pupil"]]
    assert roster.bench(game.state, game.content) == []
    entry = game.state.journal[0]
    assert (entry.title, entry.tag) == ("門下", "小六編入第二隊（第二隊統御 2／15）")


def test_moving_someone_takes_them_out_of_their_old_team(game):
    join(game, "pupil")
    game.set_member(1, 0, "pupil")
    assert game.set_member(1, 1, "mate") == ["韓鐵從本隊編入第二隊（第二隊統御 5／15）"]
    assert teams(game)[:2] == [["player"], ["pupil", "mate"]]


def test_replacing_sends_the_old_member_to_the_bench(game):
    join(game, "pupil")
    assert game.set_member(0, 1, "pupil") == ["小六編入本隊，韓鐵移到候補（本隊統御 7／15）"]
    assert teams(game)[0] == ["player", "pupil"]
    assert roster.bench(game.state, game.content) == ["mate"]


def test_emptying_a_slot_moves_the_rest_forward(game):
    join(game, "pupil", "scholar")
    game.set_member(1, 0, "pupil")
    game.set_member(1, 1, "scholar")
    assert game.set_member(1, 0, None) == ["小六移到候補（第二隊統御 3／15）"]
    assert teams(game)[1] == ["scholar"]
    assert game.set_member(1, 2, None) == []  # 空位本來就空著


def test_command_cap_refuses_and_says_by_how_much(game):
    join(game, "sage", "hero", "captain")
    game.set_member(1, 0, "sage")  # 7
    game.set_member(1, 1, "hero")  # 12
    before = (teams(game), len(game.state.journal))
    assert game.set_member(1, 2, "captain") == ["（統御 16／15，頭目換不進第二隊。）"]
    assert (teams(game), len(game.state.journal)) == before  # 沒換成，不改也不寫紀錄
    game.state.world.act_reached = 1  # 第二幕：上限 18
    assert game.set_member(1, 2, "captain") == ["頭目編入第二隊（第二隊統御 16／18）"]


def test_the_player_stays_captain_of_the_main_team(game):
    join(game, "pupil")
    assert game.set_member(0, 0, "pupil") == ["（你本人固定是本隊的隊長。）"]
    assert game.set_member(0, 0, None) == ["（你本人固定是本隊的隊長。）"]
    assert game.set_member(1, 0, "player") == ["（你本人只能待在本隊。）"]
    assert teams(game)[:2] == [["player", "mate"], []]


def test_unopened_teams_and_unknown_people_are_refused(game):
    join(game, "pupil")
    assert game.set_member(2, 0, "pupil") == ["（第三隊第二幕開放。）"]
    assert game.set_member(1, 0, "ghost") == ["（名冊裡沒有這個人。）"]
    assert game.set_member(1, 0, "sage") == ["（名冊裡沒有這個人。）"]  # 還沒入門
    assert game.set_member(9, 0, "pupil") == ["（沒有這個位置。）"]
    assert game.set_member(1, 3, "pupil") == ["（沒有這個位置。）"]
    assert game.set_member(0, 2, "mate") == ["（韓鐵已經在本隊。）"]
    assert teams(game) == [["player", "mate"], [], [], []]


# ── 舊存檔與整理 ─────────────────────────────────────────


def test_old_save_with_a_single_team_loads_as_the_main_team(tmp_path, content, game):
    dump = game.state.model_dump(mode="json")
    dump["player"]["team"] = dump["player"].pop("teams")[0]["members"]  # 1c 以前的存檔只有一支出戰隊伍
    del dump["world"]["act_reached"]
    dump["world"]["act"] = 1
    path = tmp_path / "old.json"
    path.write_text(json.dumps(dump, ensure_ascii=False), encoding="utf-8")
    old = Game(content, load_game(path))
    assert teams(old) == [["player", "mate"], [], [], []]
    assert old.state.world.act_reached == 1 and old.team_count() == 3


def test_loading_tidies_up_the_teams(content, game):
    join(game, "pupil", "scholar", "friend", "hero")
    p = game.state.player
    p.teams = p.teams[:3]  # 設定改成更多隊之前的存檔
    p.teams[0].members = ["mate", "player", "pupil", "scholar"]  # 你不在第一位、人數超過
    p.teams[1].members = ["pupil", "ghost", "friend"]  # 重複的人、不在名冊的人
    p.teams[2].members = ["hero"]  # 第三隊還沒開放
    fresh = Game(content, game.state)
    assert teams(fresh) == [["player", "mate", "pupil"], ["friend"], [], []]
    assert roster.bench(fresh.state, content) == ["hero", "scholar"]


# ── 只有本隊出手 ─────────────────────────────────────────


def test_only_the_main_team_gains_experience(game):
    join(game, "pupil")
    game.set_member(1, 0, "pupil")
    game.choose("move:lake")
    game.choose("act:train")
    p = game.state.player
    assert p.members["player"].exp == 20 and p.members["mate"].exp == 20
    assert p.members["pupil"].exp == 0


def test_team_checks_only_look_at_the_main_team(game):
    join(game, "scholar")  # 悟性 7
    check = Check(stat="wis", difficulty=5)
    game.set_member(1, 0, "scholar")
    assert team.check_actor(game.state, game.content, check) == "player"  # 本人悟性 5、韓鐵 4
    game.set_member(0, 2, "scholar")
    assert team.check_actor(game.state, game.content, check) == "scholar"


def test_status_lists_only_the_main_team(game):
    join(game, "pupil")
    game.set_member(1, 0, "pupil")
    status = game.status_text()
    assert "韓鐵" in status and "小六" not in status


def test_odds_follow_the_main_team_lineup(game, monkeypatch):
    calls = []
    real = team.run_battle
    monkeypatch.setattr(team, "run_battle", lambda *args: calls.append(1) or real(*args))
    game.odds("thug")
    join(game, "pupil")
    game.set_member(1, 0, "pupil")  # 第二隊的變化不影響本隊的勝算
    game.odds("thug")
    assert len(calls) == 40
    game.set_member(0, 2, "pupil")
    game.odds("thug")
    assert len(calls) == 80


# ── 武學配置跨隊 ─────────────────────────────────────────


def test_an_innate_blocks_only_its_own_team(game):
    learn_skill(game.state, game.content, "palm")  # 韓鐵的本命
    p = game.state.player
    game.set_loadout("player", 1, "palm")
    assert p.loadouts["player"] == ["fist", None]  # 韓鐵在本隊：他的本命不能再配給本隊的人
    join(game, "pupil")
    game.set_member(1, 0, "pupil")
    game.set_loadout("pupil", 0, "palm")
    assert p.loadouts["pupil"] == ["palm", None]  # 第二隊沒有人以它為本命
    game.set_loadout("pupil", 1, "fist")
    assert p.loadouts["player"] == [None, None] and p.loadouts["pupil"] == ["palm", "fist"]  # 同一門武學跨隊也只給一人


def test_joining_a_team_unequips_a_teammates_innate(game):
    learn_skill(game.state, game.content, "palm")  # 韓鐵的本命
    join(game, "pupil")
    game.set_member(1, 0, "pupil")
    game.set_loadout("pupil", 0, "palm")  # 第二隊沒有人以它為本命，配得上
    p = game.state.player
    assert p.loadouts["pupil"] == ["palm", None]
    assert game.set_member(0, 2, "pupil") == [
        "小六從第二隊編入本隊（本隊統御 10／15）",
        "驚濤掌是韓鐵的本命，已從小六的武學欄卸下。",
    ]
    assert teams(game)[:2] == [["player", "mate", "pupil"], []]
    assert p.loadouts["pupil"] == [None, None]
    assert game.state.journal[0].tag == "小六從第二隊編入本隊（本隊統御 10／15）"


def test_moving_the_owner_of_an_innate_unequips_it_from_his_new_teammates(game):
    learn_skill(game.state, game.content, "palm")
    join(game, "pupil")
    game.set_member(1, 0, "pupil")
    game.set_loadout("pupil", 1, "palm")
    assert game.state.player.loadouts["pupil"] == [None, "palm"]
    assert game.set_member(1, 1, "mate") == [
        "韓鐵從本隊編入第二隊（第二隊統御 5／15）",
        "驚濤掌是韓鐵的本命，已從小六的武學欄卸下。",
    ]
    assert game.state.player.loadouts["pupil"] == [None, None]


def test_a_move_that_touches_no_innate_keeps_the_loadouts(game):
    learn_skill(game.state, game.content, "palm")
    join(game, "pupil", "scholar")
    game.set_member(1, 0, "pupil")
    game.set_loadout("pupil", 0, "palm")
    assert game.set_member(1, 1, "scholar") == ["書生編入第二隊（第二隊統御 5／15）"]  # 書生的本命是 needle，和 palm 無關
    assert game.state.player.loadouts["pupil"] == ["palm", None]


# ── 天品特性 ──────────────────────────────────────────


def test_trait_goes_into_battle_as_a_fixed_xinfa(game):
    join(game, "sage", level=3)
    p = game.state.player
    unit = team.build_unit(game.state, game.content, "sage", leader=False)
    assert [(a.name, a.kind) for a in unit.arts] == [("天外劍", "絕招"), ("靜心訣", "心法")]
    assert unit.arts[1].effects[0].value == 0.1
    assert [a.name for a in team.build_unit(game.state, game.content, "mate", leader=False).arts] == ["驚濤掌"]
    # 特性不是「習得」的武學：不在武學庫、不能升級或散功、不占自選欄
    assert "calm" not in p.skills
    options = game.upgrade_options()
    assert ("隱士・本命天外劍 第1成", "innate:sage") in options
    assert not any("靜心訣" in label or target == "skill:calm" for label, target in options)
    assert team.upgrade(game.state, game.content, "skill:calm") == ["沒有這門武學。"]
    assert team.dispel(game.state, game.content, "skill:calm") == ["沒有這門武學。"]
    assert p.loadouts["sage"] == [None, None]
