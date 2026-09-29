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
    assert "（韓鐵出手——成功）" in game.state.log


def test_self_check_names_the_player_and_takes_the_fail_branch(game):
    game.state.pending_event = "insight"
    assert [o.label for o in game.options()] == ["運氣衝關（本人）"]
    game.rng = FixedRandom(0.99)  # 成功率 50%：必定失敗
    game.choose("choice:0")
    log = game.state.log
    assert log.index("（本人——失敗）") < log.index("氣息一亂，只得作罷。")
    assert game.state.player.stats["xinde"] == 0


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
    record = game.state.battles[0]
    assert (record.kind, record.event, record.opponent, record.outcome) == ("event", "挑戰", "翻江龍", "lose")
    assert record.ending == "沈浪倒下，我方敗退。" and not record.leader_ok
    assert record.notes == ["你敗了。"]  # 失敗分支的劇情文字
    assert record.changes == ["銀兩 -10"]  # 失敗分支扣的銀兩是數值變化，不混進敘事
    assert f"⚔ 湖邊：不敵翻江龍，敗退（{record.rounds} 回合）" in game.state.log
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


def test_event_battle_win_splits_story_from_numeric_changes(game):
    game.content.events["duel"].choices[0].combat = "thug"  # 換成打得贏的小嘍囉
    game.content.events["duel"].choices[0].effect.stats = {"fame": 3}
    game.content.events["duel"].choices[0].effect.rumor = "{name}擊敗了翻江龍！"
    game.choose("move:lake")
    game.choose("act:socialize")
    game.choose("choice:0")
    record = game.state.battles[0]
    assert record.outcome == "win"
    assert record.notes == ["你擊敗了翻江龍！", "【江湖傳聞】沈浪擊敗了翻江龍！"]
    assert record.changes == ["名望 +3"]


def test_train_win_stat_bonus_is_recorded_as_a_change_not_a_note(game):
    game.content.config.train_stat_chance = 1.0
    game.choose("move:lake")
    game.choose("act:train")
    record = game.state.battles[0]
    assert record.outcome == "win"
    assert record.changes and record.changes[0] in ("臂力 +1", "身法 +1", "根骨 +1")
    assert record.notes == []


def test_event_battle_draw_takes_the_fail_branch(game):
    game.content.config.battle_rounds = 1  # 一回合打不倒翻江龍，他也打不倒隊長
    game.choose("move:lake")
    game.choose("act:socialize")
    assert game.state.pending_event == "duel"
    game.choose("choice:0")
    p = game.state.player
    record = game.state.battles[0]
    assert record.outcome == "draw" and "不分勝負" in record.ending
    assert game.state.pending_event is None
    assert "你敗了。" in game.state.log and "你擊敗了翻江龍！" not in game.state.log  # 平手算沒打贏
    assert game.state.world.trends["kou"] == 30
    assert p.stats["silver"] == 40 and p.stats["xinde"] == 0  # 失敗分支扣 10 兩；沒有對手獎勵
    assert p.members["player"].exp == 0
    assert "⚔ 湖邊：與翻江龍不分勝負（1 回合）" in game.state.log


def test_train_win_is_recorded_with_rewards(game):
    game.choose("move:lake")
    game.choose("act:train")
    record = game.state.battles[0]
    assert (record.id, record.kind, record.location, record.opponent, record.outcome) == (
        1, "train", "湖邊", "水寇小隊", "win"
    )
    assert [(f.name, f.level) for f in record.ours] == [("沈浪", 1), ("韓鐵", 1)]
    assert [(f.name, f.level) for f in record.theirs] == [("小嘍囉", 1)]
    assert (record.exp, record.xinde, record.silver) == (20, 10, 5)
    assert record.leader_ok and record.ending == record.report[-1] == "小嘍囉倒下，敵方敗退。"
    assert 1 <= len(record.moments) <= 3 and "擊倒敵方隊長小嘍囉" in record.moments[-1]
    assert [p.name for p in record.performance] == ["沈浪", "韓鐵"]
    assert sum(p.damage for p in record.performance) > 0
    assert f"⚔ 湖邊：擊退水寇小隊（{record.rounds} 回合）" in game.state.log
    assert not any("戰報見" in line for line in game.state.log)


def test_train_loss_costs_a_tenth_of_the_silver(game):
    game.content.locations["lake"].enemies = ["boss"]
    game.choose("move:lake")
    game.choose("act:train")
    record = game.state.battles[0]
    assert record.outcome == "lose" and record.silver == -5
    assert game.state.player.stats["silver"] == 45
    assert f"⚔ 湖邊：不敵翻江龍，敗退（{record.rounds} 回合）" in game.state.log


def test_train_draw_changes_nothing(game):
    game.content.locations["lake"].enemies = ["boss"]
    game.content.config.battle_rounds = 1
    game.choose("move:lake")
    game.choose("act:train")
    record = game.state.battles[0]
    assert record.outcome == "draw"
    assert (record.exp, record.xinde, record.silver, record.notes) == (0, 0, 0, [])
    assert game.state.player.stats["silver"] == 50
    assert game.state.world.trends["kou"] == 30  # 大勢變化只在打贏時


def test_odds_word_tiers():
    from tianxia.team import odds_word

    # 平手率低（0）時，五段門檻不受影響。
    assert [odds_word(wins, 0, 40) for wins in (40, 36, 35, 26, 25, 14, 13, 4, 3, 0)] == [
        "穩勝", "穩勝", "有把握", "有把握", "五五波", "五五波", "凶險", "凶險", "必敗", "必敗",
    ]


def test_odds_word_shows_hard_to_tell_when_mostly_draws():
    from tianxia.team import odds_word

    # 勝率 < 35% 且平手率 ≥ 50%：改判「難分勝負」，即使勝率落在凶險／必敗的區間。
    assert odds_word(8, 92, 100) == "難分勝負"  # 新手隊打黑熊：92 平、8 敗
    assert odds_word(13, 20, 40) == "難分勝負"  # 原本會是「凶險」（13/40 ≥ 10%）
    assert odds_word(0, 20, 40) == "難分勝負"  # 平手率剛好 50%
    # 平手率不足五成時，仍照五段門檻。
    assert odds_word(0, 19, 40) == "必敗"
    assert odds_word(13, 19, 40) == "凶險"
    # 勝率已達 35% 以上時，五段門檻不受平手率影響。
    assert odds_word(14, 26, 40) == "五五波"


def test_battle_options_show_opponent_and_odds(game):
    game.choose("move:lake")
    assert game.options()[0].label == "歷練（體力 10・可能遇到：水寇小隊 穩勝）"
    assert game.options(odds=False)[0].label == "歷練（體力 10）"  # 機器人與 choose() 不必模擬
    game.choose("act:socialize")
    assert [o.label for o in game.options()] == ["應戰（對手：翻江龍・必敗）", "迴避"]


def test_draws_do_not_count_as_wins(game):
    game.content.config.battle_rounds = 1  # 一回合分不出勝負：四十場全是平手
    assert game.odds("thug") == "難分勝負"  # 0 勝、全平手：不算贏，但也打不輸——難分勝負而非必敗


def test_odds_are_stable_and_leave_the_game_rng_alone(game, content):
    from tianxia.engine import Game

    before = game.rng.getstate()
    first = game.odds("thug")
    assert game.rng.getstate() == before
    assert Game(content, game.state).odds("thug") == first  # 同樣的情況，重新建立的 Game 也算出一樣的勝算


def test_odds_are_cached_until_something_that_matters_changes(game, monkeypatch):
    from tianxia import team

    calls = []
    real = team.run_battle
    monkeypatch.setattr(team, "run_battle", lambda *args: calls.append(1) or real(*args))
    game.odds("thug")
    assert len(calls) == 40
    game.odds("thug")
    assert len(calls) == 40  # 什麼都沒變：直接用快取
    p = game.state.player
    p.members["player"].neili = 504.4  # 上限 520 的 97%：捨去成 95% 那一級，要重算
    game.odds("thug")
    assert len(calls) == 80
    p.members["player"].neili = 514.8  # 99%：還是 95% 那一級，用快取
    game.odds("thug")
    assert len(calls) == 80
    game.set_loadout("player", 0, None)  # 在門下換了配置：依新陣容重算
    game.odds("thug")
    assert len(calls) == 120


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
    assert "<svg" in game.world_map_svg()


def test_raw_log_keeps_every_message_with_one_break_per_action(game):
    """原始訊息照舊寫進 log（畫面改看江湖紀錄，見 test_journal.py）：依發生順序，每次行動後夾一個分隔標記。"""
    from tianxia.engine import LOG_BREAK

    game.choose("move:lake")
    game.choose("act:train")
    log = game.state.log
    summary = f"⚔ 湖邊：擊退水寇小隊（{game.state.battles[0].rounds} 回合）"
    assert log.index("測試開始。") < log.index("【湖邊】危險 ★★\n\n湖水茫茫。") < log.index(summary)
    assert log[-1] == LOG_BREAK and log.count(LOG_BREAK) == 3
    game.advance(0)  # 沒有訊息的呼叫不產生空的一組
    assert log.count(LOG_BREAK) == 3


def test_raw_log_keeps_order_within_an_action(game):
    game.choose("act:explore")
    log = game.state.log
    assert log.index("【醉漢】") + 1 == log.index("一名醉漢撞上了你。")


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
    assert game.member_card("player").startswith("### 沈浪（隊長）")
    assert game.member_card("mate").startswith("### 韓鐵")
    assert any(label.startswith("長拳") for label, _ in game.skill_library())
    assert game.battle_detail() == "（還沒有戰報。）"
    assert game.battle_list() == [] and game.battle_card() is None and game.battle_card_id() is None
    assert game.team_members() == [("沈浪", "player"), ("韓鐵", "mate")]


def test_battle_card_lasts_until_the_next_action(game):
    game.choose("move:lake")
    game.choose("act:train")
    assert game.battle_card_id() == 1
    card = game.battle_card()
    assert card.startswith("### ⚔ 湖邊・對陣 小嘍囉\n\n第1天 00:00　歷練")
    assert "**勝**・" in card and "隊長沈浪無恙" in card and "經驗 +20（每人）　心得 +10　銀兩 +5" in card
    game.advance(600)  # 時間流逝、計時器重畫都不算行動
    assert game.battle_card_id() == 1
    game.choose("move:town")
    assert game.battle_card() is None and game.battle_card_id() is None
    assert game.latest_battle_id() == 1  # 紀錄還在


def test_seclusion_also_clears_the_battle_card(game):
    game.choose("move:lake")
    game.choose("act:train")
    game.seclude(1)
    assert game.battle_card() is None


def test_battle_history_keeps_the_newest_twenty(game):
    game.choose("move:lake")
    for _ in range(25):
        game.state.player.stamina = 150
        game.choose("act:train")
    battles = game.state.battles
    assert len(battles) == 20
    assert [r.id for r in battles[:2]] == [25, 24] and battles[-1].id == 6
    assert [rid for _, rid in game.battle_list()] == [r.id for r in battles]
    assert game.battle_card_id() == 25


def test_battle_list_and_detail(game):
    game.choose("move:lake")
    game.choose("act:train")
    game.choose("act:train")
    (label, newest), (_, older) = game.battle_list()
    assert (newest, older) == (2, 1)
    assert label.startswith("勝　第2場　第1天 00:00　湖邊　vs 水寇小隊　") and label.endswith(" 回合")
    detail = game.battle_detail(older)
    assert detail.startswith("### ⚔ 湖邊・對陣 小嘍囉\n\n第1天 00:00　歷練　第 1 場")
    for part in ("**我方**　沈浪 Lv1、韓鐵 Lv1", "**對方**　水寇小隊：小嘍囉 Lv1", "**關鍵時刻**",
                 "| 人物 | 造成傷害 | 控制命中 |", "**逐回合戰報**", "#### 第1回合"):
        assert part in detail
    assert game.battle_detail() == game.battle_detail(newest) != detail  # 預設最新一場
    assert game.battle_detail(999) == game.battle_detail(newest)  # 找不到時也顯示最新一場


def test_menxia_page_helpers(game):
    p = game.state.player
    assert game.innate_target("player") == "skill:family"
    assert game.innate_target("mate") == "innate:mate"
    assert game.is_innate("skill:family") and game.is_innate("innate:mate") and not game.is_innate("skill:fist")
    assert game.slot_skill("player", 0) == "fist" and game.slot_skill("player", 1) is None
    assert game.upgrade_cost("skill:fist") == 20
    assert game.upgrade_cost("skill:nothing") is None
    assert game.dispel_refund("skill:fist") is None  # 第一成無功可散
    p.skills["fist"] = 10
    assert game.upgrade_cost("skill:fist") is None
    assert game.dispel_refund("skill:fist") == 720  # 20 × (1 + … + 9) × 0.8
    p.skills["family"] = 3
    assert game.dispel_refund("skill:family") is None  # 本命不能散功


def test_menxia_page_texts(game):
    assert game.menxia_rules().startswith("同一隊同一門武學只能配一次")
    assert game.member_card("player").startswith("### 沈浪（隊長）")
    assert game.slot_label("player", 1) == "自選2　（空）"
    assert [t for _, t in game.skill_library()] == ["skill:fist", "skill:family", "innate:mate"]
    assert game.skill_detail("skill:family").startswith("### 家傳劍")


# ── 安排前往 ──────────────────────────────────────────


def test_travel_walks_hop_by_hop_and_writes_one_entry(game):
    game.state.world.flags.add("cave_open")
    before = len(game.state.journal)
    msgs = game.travel("cave")
    p = game.state.player
    assert p.location == "cave" and p.stamina == 140  # 湖邊 5 ＋ 寶洞 5
    assert {"lake", "cave"} <= p.visited
    assert len(game.state.journal) == before + 1
    entry = game.state.journal[0]
    assert entry.title == "前往 寶洞（途經 湖邊）" and entry.lines == []  # 地點描述由場景顯示
    assert msgs[-1] == game.location_text() == game.scene_text()


def test_travel_to_a_neighbour_has_a_plain_title(game):
    game.travel("lake")
    assert game.state.journal[0].title == "前往 湖邊"


def test_travel_stops_when_the_next_hop_is_unaffordable(game):
    game.state.world.flags.add("cave_open")
    game.state.player.stamina = 7
    game.travel("cave")
    assert game.state.player.location == "lake" and game.state.player.stamina == 2
    assert game.state.journal[0].title == "前往 寶洞（體力不足，停在 湖邊）"


def test_travel_runs_the_guide_and_thresholds_at_every_hop(game, monkeypatch):
    from tianxia import engine

    seen = []
    real = engine.check_thresholds
    monkeypatch.setattr(engine, "check_thresholds", lambda s, c: seen.append(s.player.location) or real(s, c))
    game.state.world.flags.add("cave_open")
    game.state.player.tutorial_step = 1  # 下一步是「去湖邊」
    game.travel("cave")
    assert seen == ["lake", "cave"]
    assert game.state.player.tutorial_step == 2  # 途經湖邊就算完成
    assert game.state.journal[0].lines == ["✔ 引導完成", "【說書人】看看地圖。"]


def test_travel_stops_when_the_season_ends_on_the_way(game):
    game.state.world.flags.add("cave_open")
    game.state.world.trends["kou"] = 80  # 一走到湖邊就觸發「水寇稱霸」，賽季落幕
    game.travel("cave")
    assert game.state.world.ended and game.state.player.location == "lake"
    assert game.state.journal[0].title == "前往 寶洞（賽季落幕，停在 湖邊）"


def test_travel_is_refused_with_a_reason(game):
    before = len(game.state.journal)
    game.state.pending_event = "drunk"
    assert game.travel("lake") == ["（有事件待處理，不能安排前往。）"]
    game.state.pending_event = None
    game.state.player.busy_until = 3600.0
    assert game.travel("lake") == ["（閉關中，不能安排前往。）"]
    game.state.player.busy_until = None
    game.state.world.ended = True
    assert game.travel("lake") == ["（賽季已結束，不能安排前往。）"]
    game.state.world.ended = False
    assert game.travel("town") == ["（無法安排前往這裡。）"]  # 所在地
    assert game.travel("cave") == ["（無法安排前往這裡。）"]  # 未開放
    assert game.travel("nowhere") == ["（無法安排前往這裡。）"]
    game.state.player.stamina = 3
    assert game.travel("lake") == ["（體力不足，第一站要 5 體力。）"]
    assert game.state.player.location == "town" and game.state.player.stamina == 3
    assert len(game.state.journal) == before  # 沒走成，不寫紀錄


def test_travel_clears_the_battle_card(game):
    game.choose("move:lake")
    game.choose("act:train")
    assert game.battle_card_id() is not None
    game.travel("town")
    assert game.battle_card_id() is None


# ── 大地圖不在平常重畫時算勝算 ─────────────────────────


def test_only_the_enemies_layer_simulates(game, monkeypatch):
    from tianxia import team

    calls = []
    real = team.run_battle
    monkeypatch.setattr(team, "run_battle", lambda *args: calls.append(1) or real(*args))
    game.minimap_svg()
    for layer in ("situation", "story", "routes"):
        game.world_map_svg(layer, "lake")
    assert calls == []
    assert "最險：水寇小隊 穩勝" in game.world_map_svg("enemies")
    assert len(calls) == 40  # 湖邊一個對手 × 40 場
    game.world_map_svg("enemies")
    assert len(calls) == 40  # 快取
