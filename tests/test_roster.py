import json
import random

import pytest

from conftest import FIXTURE, FixedRandom
from tianxia import roster, team
from tianxia.content import load_content
from tianxia.engine import Game
from tianxia.models import Check, Surrender
from tianxia.rules import check_condition, learn_skill
from tianxia.save import load_game
from tianxia.state import Member, new_game_state
from tianxia.world import check_thresholds


def join(game, *keys, level=1):
    """測試用：直接讓這些人入門（正式的取得管道見下面「取得管道」一節）。"""
    for key in keys:
        game.state.player.members[key] = Member(level=level)
        game.state.player.loadouts[key] = [None, None]


def teams(game):
    return [list(t.members) for t in game.state.player.teams]


def bench(state, content):
    """候補：名冊裡不在任何一隊的人，依名冊順序（門下頁照 roster.where 標「候補」）。"""
    return [key for key in roster.roster(state, content) if roster.where(state, key) == "候補"]


# ── 隊伍數與統御上限 ─────────────────────────────────────


def test_new_game_has_the_main_team_and_empty_teams(game):
    assert teams(game) == [["player", "mate"], [], [], []]
    assert (game.team_count(), game.command_cap()) == (2, 15)
    assert roster.team_command(game.state, game.content, 0) == 8  # 你 5 ＋ 韓鐵 3
    assert bench(game.state, game.content) == []


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
    assert bench(game.state, game.content) == ["pupil"]
    assert game.set_member(1, 0, "pupil") == ["小六編入第二隊（第二隊統御 2／15）"]
    assert teams(game)[:2] == [["player", "mate"], ["pupil"]]
    assert bench(game.state, game.content) == []
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
    assert bench(game.state, game.content) == ["mate"]


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
    assert game.set_member(10, 0, "pupil") == ["（沒有這個位置。）"]  # 超出隊名的數字也不出錯
    assert game.set_member(-1, 0, "pupil") == ["（沒有這個位置。）"]
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
    assert bench(fresh.state, content) == ["hero", "scholar"]


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


# ── 入門 ──────────────────────────────────────────────


def option(game, option_id):
    found = next(o for o in game.options() if o.id == option_id)
    return found.label, found.enabled


def test_newcomers_start_at_the_lowest_level_in_the_teams(game):
    p = game.state.player
    p.members["player"].level, p.members["mate"].level = 6, 4
    join(game, "pupil", level=1)  # 候補的等級不算
    assert roster.join_level(game.state) == 4
    assert roster.recruit(game.state, game.content, "hero") == [
        "【俠女】入門（地品・柔・統御 5），從第 4 級練起，先列候補。"
    ]
    assert p.members["hero"].level == 4 and p.loadouts["hero"] == [None, None]
    assert bench(game.state, game.content) == ["hero", "pupil"]


def test_recruiting_someone_already_here_turns_into_xinde(game):
    assert roster.recruit(game.state, game.content, "mate") == ["【韓鐵】早已在門下，這份緣分化為心得。", "心得 +20"]
    assert game.state.player.stats["xinde"] == 20


def test_meeting_event_recruits_and_is_written_down(game):
    game.state.pending_event = "meet"
    game.choose("choice:0")
    assert "friend" in bench(game.state, game.content)
    entry = game.state.journal[0]
    assert (entry.title, entry.tag) == ("琴聲・請他入門", "玄品・入門")
    assert entry.lines == ["琴師收起琴，跟你走了。", "【琴師】入門（玄品・柔・統御 4），從第 1 級練起，先列候補。"]


def test_meeting_events_leave_out_people_already_here(game):
    game.state.player.flags.add("heard_music")
    condition = game.content.events["meet"].condition
    assert check_condition(condition, game.state)
    join(game, "friend")
    assert not check_condition(condition, game.state)


# ── 收徒 ──────────────────────────────────────────────


def test_apprentice_is_offered_in_towns_and_sects_only(game):
    assert [o.id for o in game.options()] == ["act:explore", "act:socialize", "act:apprentice", "move:lake"]
    assert option(game, "act:apprentice") == ("收徒（體力 5・銀兩 40）", True)
    game.choose("move:lake")  # 湖畔不是城鎮或門派
    assert "act:apprentice" not in [o.id for o in game.options()]


def test_apprentice_costs_silver_and_stamina_and_brings_someone(game):
    game.choose("act:apprentice")
    p = game.state.player
    assert (p.stamina, p.stats["silver"], p.apprentice_day, p.apprentice_count) == (145, 10, 1, 1)
    assert "scholar" in p.members and "pupil" not in p.members  # 固定亂數 Random(0) 抽到玄品
    entry = game.state.journal[0]
    assert (entry.title, entry.tag, entry.changes) == ("收徒・小鎮", "玄品・入門", ["銀兩 -40"])
    assert entry.lines == ["【書生】入門（玄品・巧・統御 3），從第 1 級練起，先列候補。"]


def test_apprentice_explains_why_it_cannot_be_done(game):
    p = game.state.player
    p.stats["silver"] = 39
    assert option(game, "act:apprentice") == ("收徒（銀兩不足，要 40 兩）", False)
    p.stats["silver"] = 100
    p.stamina = 4
    assert option(game, "act:apprentice") == ("收徒（體力 5・銀兩 40）", False)
    p.stamina = 150
    p.apprentice_day, p.apprentice_count = 1, 2
    assert option(game, "act:apprentice") == ("收徒（今天已收了 2 次）", False)
    assert game.choose("act:apprentice") == ["（此刻無法這麼做。）"]
    join(game, "pupil", "scholar")
    assert option(game, "act:apprentice") == ("此地已無可收之徒", False)


def test_apprentice_count_starts_over_the_next_day(game):
    p = game.state.player
    p.apprentice_day, p.apprentice_count = 1, 2
    game.advance(24 * 3600)
    assert option(game, "act:apprentice") == ("收徒（體力 5・銀兩 40）", True)
    game.choose("act:apprentice")
    assert (p.apprentice_day, p.apprentice_count) == (2, 1)


def test_recruit_at_limits_where_someone_can_be_taken_in(game):
    assert roster.apprentice_candidates(game.state, game.content) == ["pupil", "scholar"]
    game.state.player.location = "lake"
    assert roster.apprentice_candidates(game.state, game.content) == ["pupil"]  # 書生只在小鎮收得到


def test_apprentice_draws_huang_three_times_in_four(content):
    counts = {"黃": 0, "玄": 0}
    for seed in range(400):
        state = new_game_state(content, "測試")
        roster.apprentice(state, content, random.Random(seed))
        newcomer = next(key for key in state.player.members if key in ("pupil", "scholar"))
        counts[content.characters[newcomer].tier] += 1
    assert 270 <= counts["黃"] <= 330, counts  # 黃 75%、玄 25%


def test_apprentice_takes_whoever_is_left(game):
    join(game, "pupil")
    roster.apprentice(game.state, game.content, random.Random(0))
    assert "scholar" in game.state.player.members


# ── 招降 ──────────────────────────────────────────────


def test_beating_a_squad_may_bring_a_surrender(game):
    game.content.squads["thug"].surrender = Surrender(character="captain", chance=1.0)
    game.choose("move:lake")
    game.choose("act:train")
    record = game.state.battles[0]
    assert record.outcome == "win" and "captain" in game.state.player.members
    assert record.notes == [
        "水寇小隊敗退，【頭目】願意投效！", "【頭目】入門（地品・剛・統御 4），從第 1 級練起，先列候補。"
    ]
    entry = game.state.journal[0]
    assert entry.tag.startswith("擊退水寇小隊") and "水寇小隊敗退，【頭目】願意投效！" in entry.lines


def test_event_battles_can_bring_a_surrender_too(game):
    game.content.squads["thug"].surrender = Surrender(character="captain", chance=1.0)
    game.content.events["duel"].choices[0].combat = "thug"
    game.choose("move:lake")
    game.choose("act:socialize")
    game.choose("choice:0")
    assert "captain" in game.state.player.members
    surrender = ["水寇小隊敗退，【頭目】願意投效！", "【頭目】入門（地品・剛・統御 4），從第 1 級練起，先列候補。"]
    record = game.state.battles[0]
    assert record.notes == ["你擊敗了翻江龍！"] + surrender  # 投效接在打贏的劇情之後
    lines = game.state.journal[0].lines
    assert lines[-2:] == surrender and lines.index("你擊敗了翻江龍！") < lines.index(surrender[0])


def test_surrender_uses_the_default_chance(game):
    squad = game.content.squads["boss"]  # 沒寫機率：用 config.surrender_chance 0.25
    assert roster.surrender(game.state, game.content, squad, FixedRandom(0.3)) == []
    assert roster.surrender(game.state, game.content, squad, FixedRandom(0.2))[0] == "翻江龍敗退，【頭目】願意投效！"


def test_no_surrender_roll_once_they_are_here():
    """已經入門就不擲：打完之後的亂數狀態，和那支隊伍根本沒有招降時一模一樣。"""

    def after_training(with_surrender: bool):
        c = load_content(FIXTURE)
        c.config.train_event_chance = c.config.train_stat_chance = 0.0
        if with_surrender:
            c.squads["thug"].surrender = Surrender(character="captain", chance=0.5)
        g = Game.new(c, "沈浪", rng=random.Random(0))
        join(g, "captain")
        g.choose("move:lake")
        g.choose("act:train")
        return g.rng.getstate()

    assert after_training(True) == after_training(False)


# ── 新立門戶福緣 ─────────────────────────────────────────


def test_fortune_comes_first_when_socializing_from_day_two(game):
    game.choose("act:socialize")  # 第一天：照常
    assert game.state.pending_event == "join"
    game.choose("choice:1")
    game.state.world.time = 24 * 3600  # 第二天
    game.choose("act:socialize")
    assert game.state.pending_event == "fortune" and game.state.player.fortune
    game.choose("choice:0")
    assert "hero" in game.state.player.members
    entry = game.state.journal[0]
    assert (entry.title, entry.tag) == ("俠女來投・請她入門", "地品・入門")
    game.choose("act:socialize")
    assert game.state.pending_event == "join"  # 每季只有一次


def test_fortune_arrives_by_itself_after_day_seven(game):
    game.content.config.season_days = 10
    game.content.scenario.sim_players = []  # 不讓水寇提早結束這一季
    game.advance(7 * 24 * 3600 - 3600)
    assert "hero" not in game.state.player.members
    game.advance(3600)
    assert "hero" in game.state.player.members and game.state.player.fortune
    entry = next(e for e in game.state.journal if e.title == "結識【俠女】")
    assert entry.tag == "地品・福緣"
    assert entry.lines == [
        "一位俠女登門拜訪。", "俠女抱拳：「今後請多指教。」", "【俠女】入門（地品・柔・統御 5），從第 1 級練起，先列候補。"
    ]
    game.advance(24 * 3600)
    assert sum(e.title == "結識【俠女】" for e in game.state.journal) == 1


def test_an_old_save_past_day_seven_gets_the_fortune_on_its_next_sync(tmp_path, content, game):
    """1c 以前的存檔（只有 team，沒有 fortune、收徒次數、act_reached）已經過了第 7 天：下一次同步時間就收到福緣。"""
    content.config.season_days = 10
    content.scenario.sim_players = []  # 不讓水寇提早結束這一季
    game.state.world.time = 7 * 24 * 3600 + 3600  # 第 8 天
    game.state.last_real = 1000.0
    dump = game.state.model_dump(mode="json")
    player = dump["player"]
    player["team"] = player.pop("teams")[0]["members"]
    for field in ("fortune", "apprentice_day", "apprentice_count"):
        del player[field]
    del dump["world"]["act_reached"]
    path = tmp_path / "old.json"
    path.write_text(json.dumps(dump, ensure_ascii=False), encoding="utf-8")
    old = Game(content, load_game(path))
    assert not old.state.player.fortune and "hero" not in old.state.player.members
    old.sync(1060.0)
    assert "hero" in old.state.player.members and old.state.player.fortune
    entry = next(e for e in old.state.journal if e.title == "結識【俠女】")
    assert entry.tag == "地品・福緣"


GIFT = "江湖朋友聽說你新立門戶，送來一份賀禮。"


def test_the_fortune_is_a_gift_when_everyone_it_could_bring_is_already_here(game):
    """招賢已經把福緣的人都請進門了：從第 2 天起的第一次交遊，福緣改送一份賀禮（心得）；
    賀禮取代這次的交遊遭遇，不擲亂數，也不算進本季招賢心得。"""
    join(game, "hero")
    game.state.world.time = 24 * 3600
    before = game.rng.getstate()
    game.choose("act:socialize")
    p = game.state.player
    assert game.rng.getstate() == before and game.state.pending_event is None
    assert p.fortune and (p.stats["xinde"], p.gacha_xinde) == (50, 0)
    entry = game.state.journal[0]
    assert (entry.title, entry.lines, entry.changes) == ("福緣", [GIFT], ["心得 +50"])
    game.choose("act:socialize")
    assert game.state.pending_event == "join" and p.stats["xinde"] == 50  # 每季只有一次


def test_day_seven_gives_the_gift_when_everyone_it_could_bring_is_already_here(game):
    join(game, "hero")
    game.content.config.season_days = 10
    game.content.scenario.sim_players = []
    game.advance(7 * 24 * 3600 - 3600)
    assert not game.state.player.fortune
    game.advance(3600)
    p = game.state.player
    assert p.fortune and (p.stats["xinde"], p.gacha_xinde) == (50, 0)
    entry = next(e for e in game.state.journal if e.title == "福緣")
    assert (entry.lines, entry.changes) == ([GIFT], ["心得 +50"])
    assert not any(e.title.startswith("結識") for e in game.state.journal)
    game.advance(24 * 3600)
    assert sum(e.title == "福緣" for e in game.state.journal) == 1 and p.stats["xinde"] == 50


def test_old_save_without_recruiting_fields_loads(tmp_path, content, game):
    dump = game.state.model_dump(mode="json")
    for key in ("apprentice_day", "apprentice_count", "fortune"):
        del dump["player"][key]
    path = tmp_path / "old.json"
    path.write_text(json.dumps(dump, ensure_ascii=False), encoding="utf-8")
    p = Game(content, load_game(path)).state.player
    assert (p.apprentice_day, p.apprentice_count, p.fortune) == (0, 0, False)


def test_a_new_season_starts_the_roster_over(game):
    join(game, "hero")
    game.set_member(1, 0, "hero")
    p = game.state.player
    p.fortune, p.apprentice_day, p.apprentice_count = True, 1, 2
    game.advance(2 * 24 * 3600)  # 夾具一季兩天
    game.choose("season:new")
    p = game.state.player
    assert set(p.members) == {"player", "mate"} and teams(game) == [["player", "mate"], [], [], []]
    assert (p.fortune, p.apprentice_day, p.apprentice_count, game.state.world.act_reached) == (False, 0, 0, 0)
