import pytest

from conftest import FixedRandom

HOUR = 3600


def ids(game):
    return [o.id for o in game.options()]


def test_new_game(game):
    p = game.state.player
    assert p.location == "town" and p.stamina == 150
    assert p.skills == {"fist": 1, "family": 1}
    assert p.team == ["player", "mate"]
    assert p.loadouts["player"] == ["fist", None]
    assert "測試開始。" in game.state.log


def test_town_options(game):
    assert ids(game) == ["act:explore", "act:socialize", "move:lake"]  # 城鎮沒有敵人，不能歷練


def test_locked_location_hidden_until_flag(game):
    game.choose("move:lake")
    assert "move:cave" not in ids(game)
    game.state.world.flags.add("cave_open")
    assert "move:cave" in ids(game)


def test_socialize_hidden_when_no_events_here(game):
    game.state.world.flags.add("cave_open")
    game.choose("move:lake")
    game.state.player.location = "cave"
    assert "act:socialize" not in ids(game)


def test_move_costs_stamina(game):
    game.choose("move:lake")
    assert game.state.player.location == "lake"
    assert game.state.player.stamina == 145


def test_invalid_option_rejected(game):
    assert game.choose("move:cave") == ["（此刻無法這麼做。）"]
    assert game.state.player.location == "town"


def test_insufficient_stamina_disables_actions(game):
    game.state.player.stamina = 4
    assert all(not o.enabled for o in game.options())
    game.choose("act:explore")
    assert game.state.player.stamina == 4


def test_explore_presents_event_and_resolves_check(game):
    game.rng = FixedRandom(0.0)  # 檢定必定成功
    game.choose("act:explore")
    assert game.state.pending_event == "drunk"
    assert ids(game) == ["choice:0", "choice:1"]
    game.choose("choice:0")
    assert game.state.pending_event is None
    assert game.state.player.stats["good"] == 2
    assert game.state.world.trends["kou"] == 25
    assert "（檢定成功）" in game.state.log


def test_join_sect_via_socialize(game):
    game.choose("act:socialize")
    game.choose("choice:0")
    assert game.state.player.sect == "cloud"
    assert game.state.player.skills["sword"] == 1


def test_event_battle_is_fully_automatic(game):
    game.choose("move:lake")
    game.choose("act:socialize")
    assert game.state.pending_event == "duel"
    game.choose("choice:0")  # 應戰翻江龍：全自動打完
    assert game.state.pending_event is None
    assert not any(i.startswith("tactic:") for i in ids(game))
    assert game.state.player.stats["silver"] == 40
    assert "你敗了。" in game.state.log
    assert game.state.last_report[0] == "⚔ 對陣：翻江龍"
    from tianxia.team import member_neili

    now, top = member_neili(game.state, game.content, "player")
    assert now < top  # 內力留在戰後的剩餘值


def test_event_battle_win_pays_squad_rewards_once_and_applies_choice_effect(game):
    game.content.events["duel"].choices[0].combat = "thug"  # 換成打得贏的小嘍囉
    game.choose("move:lake")
    game.choose("act:socialize")
    assert game.state.pending_event == "duel"
    game.choose("choice:0")
    p = game.state.player
    assert game.state.pending_event is None
    assert "你擊敗了翻江龍！" in game.state.log  # 選項的 effect
    assert game.state.world.trends["kou"] == 10  # 30 − 20
    assert p.stats["silver"] == 55 and p.stats["xinde"] == 10  # 隊伍獎勵只給一次
    assert p.members["player"].exp == 20 and p.members["mate"].exp == 20


def test_event_battle_draw_clears_event_without_effects(game):
    game.content.config.battle_rounds = 1  # 一回合打不倒翻江龍，他也打不倒隊長
    game.choose("move:lake")
    game.choose("act:socialize")
    assert game.state.pending_event == "duel"
    game.choose("choice:0")
    p = game.state.player
    assert "不分勝負" in game.state.last_report[-1]
    assert game.state.pending_event is None
    assert "你擊敗了翻江龍！" not in game.state.log and "你敗了。" not in game.state.log
    assert game.state.world.trends["kou"] == 30
    assert p.stats["silver"] == 50 and p.stats["xinde"] == 0
    assert p.members["player"].exp == 0


def test_add_exp_crosses_several_levels_and_stops_at_max_level(game):
    from tianxia.team import add_exp

    game.content.config.max_level = 4
    p = game.state.player
    msgs = add_exp(game.state, game.content, 350)  # 第 1→2 級要 100、第 2→3 級要 200，剩 50
    assert (p.members["player"].level, p.members["player"].exp) == (3, 50)
    assert (p.members["mate"].level, p.members["mate"].exp) == (3, 50)
    assert msgs == ["沈浪升到第 2 級！", "沈浪升到第 3 級！", "韓鐵升到第 2 級！", "韓鐵升到第 3 級！"]
    assert add_exp(game.state, game.content, 10000) == ["沈浪升到第 4 級！", "韓鐵升到第 4 級！"]
    assert add_exp(game.state, game.content, 10000) == []
    assert p.members["player"].level == 4 and p.members["mate"].level == 4


def test_train_wins_and_pushes_trend(game):
    game.choose("move:lake")
    game.choose("act:train")
    p = game.state.player
    assert p.stamina == 135
    assert p.stats["silver"] == 55
    assert p.stats["xinde"] == 10
    assert p.members["player"].exp == 20
    assert game.state.world.trends["kou"] == 29


def test_train_event_chain(game):
    game.content.config.train_event_chance = 1.0
    game.choose("move:lake")
    game.choose("act:train")
    assert game.state.pending_event == "chain_a"
    game.choose("choice:0")
    assert game.state.pending_event == "chain_b"


def test_stamina_regenerates_with_time(game):
    game.state.player.stamina = 0
    game.advance(600)
    assert game.state.player.stamina == pytest.approx(2)


def test_sync_uses_real_clock_and_time_scale(game):
    game.content.config.time_scale = 60
    game.state.player.stamina = 0
    game.sync(1000.0)  # 第一次只記下現實時間
    game.sync(1010.0)  # 10 秒 × 60 倍 = 600 秒
    assert game.state.world.time == pytest.approx(600)
    assert game.state.player.stamina == pytest.approx(2)


def test_seclusion_grants_xinde(game):
    game.seclude(4)
    assert ids(game) == ["act:break"]
    game.advance(4 * HOUR)
    assert game.state.player.busy_until is None
    assert game.state.player.stats["xinde"] == 75  # 4 小時 × 15 × (1 + 5/20)


def test_break_seclusion_early(game):
    game.seclude(4)
    game.advance(HOUR)
    game.choose("act:break")
    assert game.state.player.busy_until is None
    assert game.state.player.stats["xinde"] == 19  # round(1 × 15 × 1.25)


def test_season_ends_by_time(game):
    game.advance(2 * 24 * HOUR)
    w = game.state.world
    assert w.ended and w.ending_title == "風雨飄搖"
    assert "blocked" in w.flags  # 翻江龍 48 小時把寇亂推到 78
    assert ids(game) == ["season:new"]


def test_new_season_resets(game):
    game.advance(2 * 24 * HOUR)
    game.choose("season:new")
    assert not game.state.world.ended
    assert game.state.world.trends["kou"] == 30
    assert game.state.player.name == "沈浪"


def test_new_season_keeps_last_real(game):
    game.sync(1000.0)
    game.advance(2 * 24 * HOUR)
    game.choose("season:new")
    assert game.state.last_real == 1000.0


def test_loadout_rules(game):
    game.choose("act:socialize")
    game.choose("choice:0")  # 拜入流雲派，學到 sword
    p = game.state.player
    game.set_loadout("player", 1, "sword")
    assert p.loadouts["player"] == ["fist", "sword"]
    game.set_loadout("mate", 0, "sword")  # 同一門武學只能配給一個人：從本人身上移走
    assert p.loadouts["player"] == ["fist", None]
    assert p.loadouts["mate"] == ["sword", None]
    game.set_loadout("player", 1, "family")  # 本人的本命不能再配一次
    assert p.loadouts["player"] == ["fist", None]
    game.set_loadout("player", 0, None)
    assert p.loadouts["player"] == [None, None]


def test_texts_render(game):
    assert "沈浪" in game.status_text()
    assert "小鎮" in game.scene_text()
    assert "寇亂" in game.trends_text() and "寶藏" not in game.trends_text()
    assert game.rumors_text() == "（尚無傳聞。）"
    game.choose("act:explore")
    assert "醉漢" in game.scene_text()


def test_stale_storyline_is_reset(content, game):
    from tianxia.engine import Game

    game.state.world.storyline = "removed_line"
    game.state.world.act = 5
    fresh = Game(content, game.state)
    assert (fresh.state.world.storyline, fresh.state.world.act) == ("main", 0)


def test_new_game_starts_tutorial_at_step_zero(content):
    from tianxia.engine import Game

    fresh = Game.new(content, "新人")
    assert fresh.state.player.tutorial_step == 0


def test_old_save_missing_tutorial_step_finishes_tutorial(content, game):
    from tianxia.engine import Game
    from tianxia.state import GameState

    dump = game.state.model_dump()
    del dump["player"]["tutorial_step"]  # 模擬引導功能上線前存的舊檔
    old_state = GameState.model_validate(dump)
    fresh = Game(content, old_state)
    assert fresh.state.player.tutorial_step == len(content.tutorial.steps)


def test_skip_tutorial(game):
    msgs = game.skip_tutorial()
    assert game.state.player.tutorial_step == len(game.content.tutorial.steps)
    assert msgs == ["（已略過新手引導。）"]
    assert msgs[0] in game.state.log


def test_new_season_keeps_finished_tutorial_state(game):
    game.skip_tutorial()
    game.advance(2 * 24 * HOUR)
    game.choose("season:new")
    assert game.state.player.tutorial_step == len(game.content.tutorial.steps)


def test_new_season_keeps_unfinished_tutorial_state(game):
    game.choose("act:explore")  # 引導推進到第 1 步，尚未完成
    assert game.state.player.tutorial_step == 1
    game.advance(2 * 24 * HOUR)
    game.choose("season:new")
    assert game.state.player.tutorial_step == 1


def test_stale_world_flags_get_flag_time_backfilled(content, game):
    from tianxia.engine import Game

    game.state.world.time = 12345
    game.state.world.flags.add("legacy_flag")  # 模擬舊存檔在 flag_times 出現前就有的旗標
    fresh = Game(content, game.state)
    assert fresh.state.world.flag_times["legacy_flag"] == 12345


def test_tutorial_runs_through_engine(game):
    assert "【說書人】先探索一下。" in game.state.log
    game.choose("act:explore")
    assert game.state.player.tutorial_step == 1
    if game.state.pending_event:
        game.choose(ids(game)[-1])  # 先把探索遇到的事件處理掉
    game.choose("move:lake")
    assert game.state.player.tutorial_step == 2
    game.view_map()
    assert game.state.player.tutorial_step == 3
    assert "拜入門派" in game.quest_text()


def test_view_map_always_sets_flag_even_when_not_current_step(game):
    game.view_map()
    game.view_map()
    assert "看過地圖" in game.state.player.flags
    assert game.state.player.tutorial_step == 0  # 引導還在第一步（探索），不是看地圖
    game.choose("act:explore")
    if game.state.pending_event:
        game.choose(ids(game)[-1])
    game.choose("move:lake")
    # s2（去湖邊）完成的當下，因為旗標早就成立，s3（看地圖）也一併完成，不用再開一次地圖
    assert game.state.player.tutorial_step == 3


def test_visited_and_map(game):
    assert game.state.player.visited == {"town"}
    game.choose("move:lake")
    assert game.state.player.visited == {"town", "lake"}
    assert "<svg" in game.map_svg()


def test_log_text_shows_newest_action_first(game):
    from tianxia.engine import LOG_BREAK

    game.choose("move:lake")
    game.choose("act:train")
    text = game.log_text()
    assert text.index("你率眾在湖邊與") < text.index("【湖邊】")  # 最新的行動在最上面
    assert text.index("【湖邊】") < text.index("測試開始。")  # 開場紀錄在最下面
    marks = game.state.log.count(LOG_BREAK)
    game.advance(0)  # 沒有訊息的呼叫不產生空的一組
    assert game.state.log.count(LOG_BREAK) == marks


def test_log_text_keeps_order_within_an_action(game):
    game.choose("act:explore")
    text = game.log_text()
    assert text.startswith("【醉漢】")
    assert text.index("【醉漢】") < text.index("一名醉漢撞上了你。")


def test_log_text_limits_groups_and_handles_old_saves(game):
    game.state.log = ["舊紀錄一", "舊紀錄二"]  # 舊存檔沒有分隔標記：整段當成一組
    assert game.log_text() == "舊紀錄一\n\n舊紀錄二"
    for _ in range(5):
        game.choose("move:lake")
        game.choose("move:town")
    assert game.log_text(limit=2).count("---") == 1


def test_upgrade_and_dispel_with_xinde(game):
    p = game.state.player
    p.stats["xinde"] = 100
    game.upgrade("skill:fist")
    game.upgrade("skill:fist")
    assert p.skills["fist"] == 3 and p.stats["xinde"] == 40  # 20 + 40
    assert "心得不足" in game.upgrade("skill:fist")[0]  # 第 3→4 成要 60
    game.dispel("skill:fist")
    assert p.skills["fist"] == 1 and p.stats["xinde"] == 88  # 返還 (20+40)×0.8＝48


def test_innate_arts_can_be_upgraded_but_not_dispelled(game):
    p = game.state.player
    p.stats["xinde"] = 40
    game.upgrade("skill:family")  # 本人的本命
    game.upgrade("innate:mate")  # 同伴的本命
    assert p.skills["family"] == 2 and p.members["mate"].innate_level == 2 and p.stats["xinde"] == 0
    assert game.dispel("skill:family") == ["本命武學不能散功。"]
    assert game.dispel("innate:mate") == ["本命武學不能散功。"]
    assert p.skills["family"] == 2 and p.members["mate"].innate_level == 2 and p.stats["xinde"] == 0


def test_upgrade_companion_innate(game):
    p = game.state.player
    p.stats["xinde"] = 20
    game.upgrade("innate:mate")
    assert p.members["mate"].innate_level == 2
    assert ("韓鐵・本命驚濤掌 第2成", "innate:mate") in game.upgrade_options()


def test_neili_regenerates_over_time(game):
    game.state.player.members["player"].neili = 1.0
    game.advance(2 * HOUR)
    assert game.state.player.members["player"].neili is None  # 回滿（新手期加倍，兩小時綽綽有餘）


def test_texts_for_team_skills_and_report(game):
    assert "韓鐵" in game.team_text() and "（隊長）" in game.team_text()
    assert "長拳" in game.skills_text()
    assert game.report_text() == "（還沒有戰報。）"
    assert game.team_members() == [("沈浪", "player"), ("韓鐵", "mate")]
