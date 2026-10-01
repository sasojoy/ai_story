import random
from unittest import mock

import pytest

from conftest import FixedRandom
from tianxia import battle_instance, companion_agent, flavor, rules
from tianxia.engine import Game, Option
from tianxia.state import GameState
from tianxia.world_state import WorldStateStore

HOUR = 3600
DAY = 86400


def ids(game):
    return [o.id for o in game.options()]


# ── 新遊戲與選項 ─────────────────────────────────────────


def test_new_game(game):
    p = game.state.player
    assert p.location == "town" and p.stamina == 150
    assert p.team == [] and p.member.level == 1
    assert "測試開始。" in game.state.log


def test_town_options(game):
    # 小鎮有事件可交遊（拜師）、有可招募的人（韓鐵），沒有敵人所以不能歷練
    assert ids(game) == ["act:explore", "act:socialize", "act:recruit", "move:lake", "act:rest"]


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


def test_recruit_option_follows_who_is_free_at_this_location(game):
    assert "招募【韓鐵】（體力 15）" in [o.label for o in game.options() if o.id == "act:recruit"]
    game.choose("move:lake")
    assert "招募【琴師】（體力 15）" in [o.label for o in game.options() if o.id == "act:recruit"]
    game.world.try_recruit("friend", "李四")
    game.world.try_recruit("hero", "李四")
    assert "act:recruit" not in ids(game)  # 湖邊兩人都被搶走了


def test_move_costs_stamina(game):
    game.choose("move:lake")
    assert game.state.player.location == "lake"
    assert game.state.player.stamina == 145


def test_invalid_option_rejected(game):
    assert game.choose("move:cave") == ["（此刻無法這麼做。）"]
    assert game.state.player.location == "town"


def test_insufficient_stamina_disables_actions(game):
    game.state.player.stamina = 4
    opts = game.options()
    assert all(not o.enabled for o in opts if o.id != "act:rest")
    game.choose("act:explore")
    assert game.state.player.stamina == 4


def test_rest_is_always_available_and_never_locks_the_player_out(game):
    """實機 playtest 發現的卡死情境：體力見底時過去完全沒有選項可點（連移動都不行），
    玩家只能乾等現實時間過去或自己發現「門下」頁的閉關分頁——新玩家根本不知道要這麼做。
    act:rest 必須永遠是 enabled，且真的能恢復體力，不管共用賽季時鐘怎麼走。"""
    game.state.player.stamina = 0
    opts = game.options()
    rest = next(o for o in opts if o.id == "act:rest")
    assert rest.enabled
    game.choose("act:rest")
    assert game.state.player.stamina > 0


def test_rest_does_not_advance_the_shared_season_clock(game):
    """跟 advance()（測試用時間快轉，連共用賽季一起推進）不同：一個人缺體力想歇息，
    不該連帶把全服的大勢/倒數也推走。"""
    before = game.state.world.time
    game.choose("act:rest")
    assert game.state.world.time == before


# ── 事件與檢定 ────────────────────────────────────────────


def test_explore_presents_event_and_resolves_check(game):
    game.rng = FixedRandom(0.0)  # 檢定必定成功
    game.choose("act:explore")
    assert game.state.pending_event == "drunk"
    assert ids(game) == ["choice:0", "choice:1"]
    game.choose("choice:0")
    assert game.state.pending_event is None
    assert game.state.player.stats["good"] == 2
    assert game.state.world.trends["kou"] == 25
    assert "（本人出手——成功）" in game.state.log


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
    assert game.state.pending_event == "join"
    game.choose("choice:0")
    assert game.state.player.sect == "cloud"


def test_declining_the_sect_leaves_the_player_unaffiliated(game):
    game.choose("act:socialize")
    game.choose("choice:1")
    assert game.state.player.sect is None


# ── 遭遇/劇情戰：單次判定 ───────────────────────────────────


def test_event_battle_is_fully_automatic_and_a_loss_applies_the_fail_effect(game):
    game.choose("move:lake")
    game.choose("act:socialize")
    assert game.state.pending_event == "duel"
    game.choose("choice:0")  # 應戰翻江龍：必敗，全自動打完
    assert game.state.pending_event is None
    assert not any(i.startswith("tactic:") for i in ids(game))
    assert game.state.player.stats["silver"] == 40
    assert "你敗了。" in game.state.log
    record = game.state.battles[0]
    assert (record.kind, record.event, record.opponent, record.tier) == ("event", "挑戰", "翻江龍", "落敗")
    assert record.notes == ["你敗了。"]
    assert record.changes == ["銀兩 -10"]
    assert "⚔ 湖邊：落敗翻江龍" in game.state.log


def test_event_battle_win_pays_squad_rewards_once_and_applies_choice_effect(game):
    game.content.events["duel"].choices[0].combat = "thug"  # 換成打得贏的水寇小隊
    game.choose("move:lake")
    game.choose("act:socialize")
    game.rng = FixedRandom(1.0)  # 最佳運氣：穩穩打贏
    game.choose("choice:0")
    p = game.state.player
    assert game.state.pending_event is None
    assert "你擊敗了翻江龍！" in game.state.log
    assert game.state.world.trends["kou"] == 10  # 30 − 20
    assert p.stats["silver"] == 55 and p.stats["xinde"] == 10
    assert p.member.exp == 20


def test_event_battle_win_splits_story_from_numeric_changes(game):
    game.content.events["duel"].choices[0].combat = "thug"
    game.content.events["duel"].choices[0].effect.stats = {"fame": 3}
    game.content.events["duel"].choices[0].effect.rumor = "{name}擊敗了翻江龍！"
    game.choose("move:lake")
    game.choose("act:socialize")
    game.rng = FixedRandom(1.0)
    game.choose("choice:0")
    record = game.state.battles[0]
    assert record.tier in ("大勝", "險勝")
    assert record.notes == ["你擊敗了翻江龍！", "【江湖傳聞】沈浪擊敗了翻江龍！"]
    assert record.changes == ["名望 +3"]


def test_train_win_is_recorded_with_rewards(game):
    rules.learn_skill(game.state, game.content, "fist")  # 壓倒性的威力，穩贏
    game.content.config.train_event_chance = 1.0
    game.choose("move:lake")
    game.state.player.seen_events.add("scroll")  # 避開探索遇到殘卷奇遇
    game.rng = FixedRandom(0.3)
    game.choose("act:explore")
    record = game.state.battles[0]
    assert (record.kind, record.location, record.opponent) == ("train", "湖邊", "水寇小隊")
    assert record.tier in ("大勝", "險勝")
    assert [(f.name, f.level) for f in record.ours] == [("沈浪", 1)]
    assert (record.exp, record.xinde, record.silver) == (20, 10, 5)
    assert game.state.world.trends["kou"] == 29  # 湖邊 train_trend kou:-1
    assert "⚔ 湖邊：" in "\n".join(game.state.log)


def test_train_loss_costs_a_tenth_of_the_silver(game):
    game.content.locations["lake"].enemies = ["boss"]  # 換成打不贏的翻江龍
    game.content.config.train_event_chance = 1.0
    game.choose("move:lake")
    game.state.player.seen_events.add("scroll")
    game.rng = FixedRandom(0.0)
    game.choose("act:explore")
    record = game.state.battles[0]
    assert record.tier == "落敗" and record.silver == -5
    assert game.state.player.stats["silver"] == 50  # -5 落敗損失，+5 這一步剛好完成新手引導第一步的獎勵


def test_train_win_stat_bonus_is_recorded_as_a_change_not_a_note(game):
    rules.learn_skill(game.state, game.content, "fist")
    game.content.config.train_stat_chance = 1.0
    game.content.config.train_event_chance = 1.0
    game.choose("move:lake")
    game.state.player.seen_events.add("scroll")
    game.rng = FixedRandom(0.3)
    game.choose("act:explore")
    record = game.state.battles[0]
    assert record.tier in ("大勝", "險勝")
    assert record.changes and record.changes[0].split(" ")[1] == "+1"
    assert record.notes == []


def test_train_event_chain(game):
    game.content.config.train_event_chance = 1.0
    game.choose("move:lake")
    game.choose("act:explore")
    assert game.state.pending_event == "scroll"


# ── 招募與隊伍 ────────────────────────────────────────────


def test_recruit_action_succeeds_and_joins_the_team(game):
    game.rng = FixedRandom(0.1)  # < 0.35：成功
    msgs = game.choose("act:recruit")
    assert msgs == ["【韓鐵】被你的誠意打動，願意追隨於你！"]
    assert game.state.player.team == ["mate"]
    assert game.state.player.stamina == 135  # 只扣一次 15 體力，不是兩次


def test_recruit_action_can_fail(game):
    game.rng = FixedRandom(0.99)  # 遠高於成功率與決鬥率
    msgs = game.choose("act:recruit")
    assert "婉拒" in msgs[0]
    assert game.state.player.team == []


def test_no_recruit_option_when_nobody_is_free_here(game):
    game.world.try_recruit("mate", "李四")
    game.world.try_recruit("pupil", "李四")
    game.world.try_recruit("scholar", "李四")
    assert "act:recruit" not in ids(game)
    assert game.choose("act:recruit") == ["（此刻無法這麼做。）"]


def test_add_and_remove_from_team(game):
    game.rng = FixedRandom(0.1)
    game.choose("act:recruit")
    assert game.team_members() == [("沈浪", "player"), ("韓鐵", "mate")]
    game.remove_from_team("mate")
    assert game.team_members() == [("沈浪", "player")]
    game.add_to_team("mate")
    assert game.team_members() == [("沈浪", "player"), ("韓鐵", "mate")]


def test_owned_companions_and_roster_lines(game):
    game.rng = FixedRandom(0.1)
    game.choose("act:recruit")
    assert game.owned_companions() == ["mate"]
    assert game.roster_lines() == [
        ("本人　沈浪　第 1 級", "player"),
        ("韓鐵　第 1 級　出戰", "mate"),
    ]


# ── 深度對話（companion_agent.py 的引擎接線）────────────────


FAKE_TURN = companion_agent.CompanionTurn(
    narrative="他點了點頭。", options=["閒聊幾句", "就此告辭"], option_tags=["尋常寒暄", "尋常寒暄"],
)


def test_socializing_with_a_deep_interaction_companion_starts_a_dialogue(content, game):
    content.characters["mate"].deep_interaction = True
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        msgs = game.choose("act:socialize")
    assert msgs == ["他點了點頭。"]
    assert game.state.player.pending_companion == "mate"
    assert ids(game) == ["talk:0", "talk:1", "talk:leave"]
    assert game.scene_text() == "**韓鐵**\n\n他點了點頭。"


def test_continuing_and_leaving_a_dialogue(content, game):
    content.characters["mate"].deep_interaction = True
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        game.choose("act:socialize")
        msgs = game.choose("talk:0")
        assert msgs == ["他點了點頭。", "（好感度 +1）"]
        assert game.state.player.affinities["mate"] == 1
        msgs = game.choose("talk:leave")
    assert msgs == ["你結束了這段交談，先行告辭。"]
    assert game.state.player.pending_companion is None
    assert ids(game) == ["act:explore", "act:socialize", "act:recruit", "move:lake", "act:rest"]


def test_socializing_without_a_deep_interaction_companion_falls_through_to_events(game):
    """小鎮的韓鐵沒有標 deep_interaction：交遊照舊走一般事件（例如拜師），不會誤觸發對話。"""
    game.choose("act:socialize")
    assert game.state.pending_event == "join"
    assert game.state.player.pending_companion is None


def test_locked_figures_use_talk_at_instead_of_recruit_at_for_dialogue(content, game):
    """龍頭人物（kind=locked）不可招募，深度對話走 talk_at，不是 recruit_at。"""
    ch = content.characters["mate"]
    ch.kind, ch.recruit_at, ch.talk_at, ch.deep_interaction = "locked", None, "town", True
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        msgs = game.choose("act:socialize")
    assert msgs == ["他點了點頭。"]
    assert game.state.player.pending_companion == "mate"
    assert "act:recruit" not in ids(game)  # 鎖定人物不會因為 talk_at 而冒出招募選項


# ── 重複內容的潤色（還要改進第 3 點）─────────────────────────


def test_first_visit_to_a_location_does_not_call_flavor(game):
    with mock.patch.object(flavor, "polish_revisit") as polish:
        game.choose("move:lake")  # 第一次去湖邊，不是重遊
    polish.assert_not_called()


def test_revisiting_a_location_appends_the_flavor_sentence(game):
    game.choose("move:lake")
    with mock.patch.object(flavor, "polish_revisit", return_value="風又吹起了。"):
        msgs = game.choose("move:town")  # 小鎮開局就去過，這次是重遊
    assert msgs[0].endswith("\n\n風又吹起了。")


def test_revisiting_an_important_location_skips_flavor(content, game):
    content.locations["town"].important = True
    game.choose("move:lake")
    with mock.patch.object(flavor, "polish_revisit") as polish:
        game.choose("move:town")
    polish.assert_not_called()


def test_revisiting_skips_the_sentence_when_flavor_comes_back_empty(game):
    game.choose("move:lake")
    with mock.patch.object(flavor, "polish_revisit", return_value=""):
        msgs = game.choose("move:town")
    assert msgs[0] == game.location_text()  # 失敗就整句省略，不多附加任何東西


def test_presenting_an_event_for_the_first_time_does_not_call_flavor(game):
    event = next(iter(game.content.events.values()))
    with mock.patch.object(flavor, "polish_event_repeat") as polish:
        game._present(event)
    polish.assert_not_called()


def test_presenting_a_repeated_event_appends_the_flavor_sentence(game):
    event = next(iter(game.content.events.values()))
    game._present(event)
    with mock.patch.object(flavor, "polish_event_repeat", return_value="巷口又傳來同樣的吆喝聲。"):
        head, text = game._present(event)
    assert text.endswith("\n\n巷口又傳來同樣的吆喝聲。")


# ── 練功、療傷 ───────────────────────────────────────────


def test_create_skill_and_practice(game):
    msgs = game.create_skill("龍吟九霄", "武學")
    assert msgs == ["你自創了一門武學【龍吟九霄】（中品，屬陰）！"]
    assert game.state.player.member.wugong_id == "龍吟九霄"
    entry = game.state.journal[0]
    assert entry.title == "門下" and entry.tag == msgs[0]
    game.practice("武學")
    assert game.state.player.member.wugong_level == 2
    assert game.state.journal[0].title == "門下"  # 併進同一則


def test_create_skill_rejects_a_taken_name(game):
    game.create_skill("龍吟九霄", "武學")
    other = Game(game.content, GameState(player=game.state.player.model_copy(), world=game.state.world), world=game.world)
    other.state.player.member.wugong_id = None
    msgs = other.create_skill("龍吟九霄", "內功")
    assert "已經有人取走了" in msgs[0]


def test_heal(game):
    assert game.heal() == ["氣血無恙，不用療傷。"]
    game.state.player.member.neili = 10.0
    game.state.player.stats["silver"] = 999
    msgs = game.heal()
    assert msgs[0].startswith("療傷完畢")
    assert game.state.player.member.neili is None


# ── 閉關 ──────────────────────────────────────────────


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


def test_cannot_seclude_while_busy_with_something_else(game):
    game.state.pending_event = "drunk"
    assert game.seclude(4) == ["你現在無法閉關。"]


# ── 時間、賽季 ────────────────────────────────────────────


def test_stamina_regenerates_with_time(game):
    game.state.player.stamina = 0
    game.advance(600)
    assert game.state.player.stamina == pytest.approx(2)


def test_sync_uses_real_clock_and_time_scale(game):
    game.content.config.time_scale = 60
    game.state.player.stamina = 0
    game.sync(1000.0)
    game.sync(1010.0)
    assert game.state.world.time == pytest.approx(600)
    assert game.state.player.stamina == pytest.approx(2)


def test_season_ends_by_time(game):
    game.advance(2 * DAY)
    w = game.state.world
    assert w.ended and w.ending_title == "風雨飄搖"
    assert "blocked" in w.flags
    assert ids(game) == ["season:new"]


def test_new_season_resets_and_keeps_the_name_and_last_real(game):
    game.sync(1000.0)
    game.advance(2 * DAY)
    game.choose("season:new")
    assert not game.state.world.ended
    assert game.state.world.trends["kou"] == 30
    assert game.state.player.name == "沈浪"
    assert game.state.last_real == 1000.0


# ── 共享賽季：跨玩家傳播（真正共享賽季，取代每個玩家各自獨立的大勢/門檻）──────────


def test_two_players_start_in_the_same_shared_season(content, world):
    a = Game.new(content, "甲", rng=random.Random(1), world=world)
    b = Game.new(content, "乙", rng=random.Random(2), world=world)
    assert a.state.world.trends == b.state.world.trends
    assert a.state.world.storyline == b.state.world.storyline


def test_one_players_trend_push_is_invisible_to_another_until_they_sync(content, world):
    a = Game.new(content, "甲", rng=random.Random(1), world=world)
    b = Game.new(content, "乙", rng=random.Random(2), world=world)
    a.state.world.trends["kou"] = 55
    a._save_season()
    assert b.state.world.trends["kou"] == 30  # 乙還沒同步，看不到甲剛才的改動
    b.sync(1000.0)
    assert b.state.world.trends["kou"] == 55  # 同步後就看到了


def test_one_players_action_ending_the_season_propagates_to_another_on_sync(content, world):
    a = Game.new(content, "甲", rng=random.Random(1), world=world)
    b = Game.new(content, "乙", rng=random.Random(2), world=world)
    a.state.world.trends["kou"] = 80
    from tianxia.world import check_thresholds
    check_thresholds(a.state, content, a.world, a.client)
    a._save_season()
    assert a.state.world.ended
    assert not b.state.world.ended  # 乙還沒同步
    b.sync(1000.0)
    assert b.state.world.ended and b.state.world.ending_title == a.state.world.ending_title


def test_new_season_propagates_to_another_player_on_their_next_sync(content, world):
    a = Game.new(content, "甲", rng=random.Random(1), world=world)
    b = Game.new(content, "乙", rng=random.Random(2), world=world)
    b.state.player.affinities["mate"] = 42
    b.state.player.member.level = 5
    a.advance(2 * DAY)
    assert a.state.world.ended
    a.choose("season:new")
    assert a.state.player.season_number == 2

    b.sync(1000.0)  # 乙完全沒點任何東西，只是連線期間剛好同步到
    assert b.state.player.season_number == 2
    assert not b.state.world.ended
    assert b.state.player.affinities["mate"] == 42  # 好感度保留
    assert b.state.player.member.level == 1  # 角色本身重新開始


def test_a_brand_new_player_joining_mid_season_sees_the_current_shared_state(content, world):
    a = Game.new(content, "甲", rng=random.Random(1), world=world)
    a.state.world.trends["kou"] = 70
    a._save_season()
    b = Game.new(content, "乙", rng=random.Random(2), world=world)  # 乙中途才加入
    assert b.state.world.trends["kou"] == 70
    assert b.state.player.season_number == 1


# ── 新手引導 ──────────────────────────────────────────────


def test_new_game_starts_tutorial_at_step_zero(content):
    fresh = Game.new(content, "新人", world=WorldStateStore(None))
    assert fresh.state.player.tutorial_step == 0


def test_skip_tutorial(game):
    msgs = game.skip_tutorial()
    assert game.state.player.tutorial_step == len(game.content.tutorial.steps)
    assert msgs == ["（已略過新手引導。）"]


def test_tutorial_runs_through_engine(game):
    assert "【說書人】先探索一下。" in game.state.log
    game.choose("act:explore")
    assert game.state.player.tutorial_step == 1
    if game.state.pending_event:
        game.choose(ids(game)[-1])
    game.choose("move:lake")
    assert game.state.player.tutorial_step == 2
    game.view_map()
    assert game.state.player.tutorial_step == 3
    assert "拜入門派" in game.quest_text()


def test_view_map_always_sets_the_flag_even_when_not_the_current_step(game):
    game.view_map()
    game.view_map()
    assert "看過地圖" in game.state.player.flags
    assert game.state.player.tutorial_step == 0


# ── 舊存檔相容 ────────────────────────────────────────────


def test_stale_storyline_is_reset(content, game):
    game.state.world.storyline = "removed_line"
    game.state.world.act = 5
    fresh = Game(content, game.state, world=game.world)
    assert (fresh.state.world.storyline, fresh.state.world.act) == ("main", 0)


def test_old_save_missing_tutorial_step_finishes_the_tutorial(content, game):
    dump = game.state.model_dump()
    del dump["player"]["tutorial_step"]
    old_state = GameState.model_validate(dump)
    fresh = Game(content, old_state, world=game.world)
    assert fresh.state.player.tutorial_step == len(content.tutorial.steps)


def test_stale_world_flags_get_flag_time_backfilled(content, game):
    """共用賽季本身的存檔格式較舊、缺 flag_times 時也要能補上——世界狀態現在是從共用
    儲存拉回來的（見 _reconcile_season），不是直接改 game.state.world 就能模擬，要改
    的是共用儲存裡實際存著的那一份。"""
    season = game.world.get_season()
    season.time = 12345
    season.flags.add("legacy_flag")
    game.world.save_season(season)
    fresh = Game(content, game.state, world=game.world)
    assert fresh.state.world.flag_times["legacy_flag"] == 12345


def test_stale_dialogue_reference_is_dropped(content, game):
    game.state.player.pending_companion = "ghost"
    fresh = Game(content, game.state, world=game.world)
    assert fresh.state.player.pending_companion is None


def test_stale_learned_skill_reference_is_dropped(content, game):
    game.state.player.member.wugong_id = "ghost_skill"
    fresh = Game(content, game.state, world=game.world)
    assert fresh.state.player.member.wugong_id is None


def test_team_members_beyond_the_cap_or_unknown_are_trimmed(content, game):
    game.state.player.team = ["mate", "ghost", "pupil", "scholar", "friend", "hero"]
    fresh = Game(content, game.state, world=game.world)
    from tianxia import team as team_mod

    assert fresh.state.player.team == ["mate", "pupil", "scholar", "friend"][: team_mod.MAX_TEAM_COMPANIONS]


# ── 畫面文字 ──────────────────────────────────────────────


def test_texts_render(game):
    assert "沈浪" in game.status_text()
    assert "小鎮" in game.scene_text()
    assert "寇亂" in game.trends_text() and "寶藏" not in game.trends_text()
    assert game.rumors_text() == "（尚無傳聞。）"
    game.choose("act:explore")
    assert "醉漢" in game.scene_text()


def test_visited_and_map(game):
    assert game.state.player.visited == {"town"}
    game.choose("move:lake")
    assert game.state.player.visited == {"town", "lake"}
    assert "<svg" in game.world_map_svg()
    assert "<svg" in game.minimap_svg()


# ── 安排前往 ──────────────────────────────────────────────


def test_travel_walks_hop_by_hop_and_writes_one_entry(game):
    game.state.world.flags.add("cave_open")
    before = len(game.state.journal)
    msgs = game.travel("cave")
    p = game.state.player
    assert p.location == "cave" and p.stamina == 140  # 湖邊 5 ＋ 寶洞 5
    assert {"lake", "cave"} <= p.visited
    assert len(game.state.journal) == before + 1
    entry = game.state.journal[0]
    assert entry.title == "前往 寶洞（途經 湖邊）" and entry.lines == []
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
    assert len(game.state.journal) == before


# ── 全服即時多人戰鬥（設計討論：集結選陣營→逐幕逐回合鎖步）──────────


def _install_battle_def(content):
    from tianxia.models import (
        BattleAct, BattleActionEffect, BattleAdvanceWhen, BattleDef, BattleFaction, BattleOption, BattleOutcome,
    )

    definition = BattleDef(
        id="t1", name="測試決戰",
        factions=[BattleFaction(id="guan", name="官軍"), BattleFaction(id="huang", name="黃巾")],
        acts=[
            BattleAct(
                id="a1", title="初探", text="雙方試探。", goal="推動戰局",
                options=[BattleOption(text="穩紮穩打", tag="safe"), BattleOption(text="全力進攻", tag="aggressive")],
                advance_when=BattleAdvanceWhen(trend_min=90),
            ),
        ],
        action_tags={
            "safe": BattleActionEffect(trend_delta=1, neili_damage=5),
            "aggressive": BattleActionEffect(trend_delta=5, neili_damage=20),
        },
        outcomes=[BattleOutcome(faction="guan", title="官軍大勝", text="官軍獲勝。")],
        muster_seconds=600, round_seconds=120,
    )
    content.battles[definition.id] = definition
    return definition


def test_no_active_battle_leaves_normal_gameplay_untouched(content, game):
    assert game._battle_status() is None
    assert ids(game)[0] == "act:explore"


def test_an_active_muster_shows_faction_join_options(content, game):
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=1000.0)
    with mock.patch("tianxia.engine.time.time", return_value=1000.0):
        assert ids(game) == ["battle:join:guan", "battle:join:huang"]
        assert "測試決戰" in game.scene_text()


def test_joining_a_faction_during_muster(content, game):
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=1000.0)
    with mock.patch("tianxia.engine.time.time", return_value=1000.0):
        game.choose("battle:join:guan")
    assert game.world.get_battle().participants["沈浪"].faction == "guan"


def test_muster_auto_closes_once_the_deadline_passes(content, game):
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=1000.0)
    with mock.patch("tianxia.engine.time.time", return_value=1000.0):
        game.choose("battle:join:guan")
    with mock.patch("tianxia.engine.time.time", return_value=1000.0 + definition.muster_seconds + 1):
        status = game._battle_status()
    assert status is not None and status[0].phase == "active"


def test_submitting_an_action_and_a_bot_auto_fills_then_the_round_resolves(content, game):
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=0.0)
    with mock.patch("tianxia.engine.time.time", return_value=0.0):
        game.choose("battle:join:guan")
        game.world.mutate_battle(
            lambda b: battle_instance.join_faction(b, "機器人", "huang", neili_cap=100.0, is_bot=True)
        )
    after_muster = definition.muster_seconds + 1
    with mock.patch("tianxia.engine.time.time", return_value=after_muster):
        game._battle_status()  # 推進一次，確保集結已關閉、進入 active
        game.choose("battle:act:safe")  # 人類送出，機器人在同一次 tick 裡自動補上，回合應該已經結算
    battle = game.world.get_battle()
    assert battle.trend != 50  # 已經結算過，trend 被推動了
    assert battle.round.pending_actions == {}  # 回合已經重置


def test_the_player_whose_action_completes_the_round_sees_the_resolution_text(content, game):
    """送出最後一個行動的那個人，自己這次 choose() 的回傳就該看到這一回合真正發生的事
    （不能是空清單）——不管這回合只是普通推進，還是剛好把戰鬥打完。"""
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=0.0)
    with mock.patch("tianxia.engine.time.time", return_value=0.0):
        game.choose("battle:join:guan")
        game.world.mutate_battle(
            lambda b: battle_instance.join_faction(b, "機器人", "huang", neili_cap=100.0, is_bot=True)
        )
    after_muster = definition.muster_seconds + 1
    with mock.patch("tianxia.engine.time.time", return_value=after_muster):
        game._battle_status()
        msgs = game.choose("battle:act:safe")
    assert msgs != []
    assert any("官軍大勝" in m or "官軍獲勝" in m for m in msgs)  # _install_battle_def 的保底結果沒有數值門檻，第一回合就分出勝負


def test_waiting_for_others_returns_a_placeholder_message(content, game):
    """送出行動但還有人沒選完，回合不會結算：至少要有個訊息，不能讓畫面看起來像沒反應。"""
    definition = _install_battle_def(content)
    definition.outcomes[0] = definition.outcomes[0].model_copy(update={"trend_min": 999})  # 讓這回合分不出勝負
    game.world.start_battle(definition, now=0.0)
    with mock.patch("tianxia.engine.time.time", return_value=0.0):
        game.choose("battle:join:guan")
        game.world.mutate_battle(lambda b: battle_instance.join_faction(b, "乙玩家", "huang", neili_cap=100.0))
    after_muster = definition.muster_seconds + 1
    with mock.patch("tianxia.engine.time.time", return_value=after_muster):
        game._battle_status()
        msgs = game.choose("battle:act:safe")
    assert msgs == ["你選擇了行動，等待其他人……"]


def test_battle_outcome_applies_trend_delta_and_flags_to_the_shared_season(content, game):
    definition = _install_battle_def(content)
    definition.outcomes[0] = definition.outcomes[0].model_copy(
        update={"world_flags_add": ["huangjin_decisive_win"], "trend_delta": {"kou": -40}}
    )
    game.world.start_battle(definition, now=0.0)
    with mock.patch("tianxia.engine.time.time", return_value=0.0):
        game.choose("battle:join:guan")
        game.world.mutate_battle(
            lambda b: battle_instance.join_faction(b, "機器人", "huang", neili_cap=100.0, is_bot=True)
        )
    before = game.world.get_season().trends["kou"]
    after_muster = definition.muster_seconds + 1
    with mock.patch("tianxia.engine.time.time", return_value=after_muster):
        game._battle_status()
        game.choose("battle:act:safe")
    season = game.world.get_season()
    assert season.trends["kou"] == max(0, before - 40)
    assert "huangjin_decisive_win" in season.flags
    assert any("官軍大勝" in r.text for r in season.chronicle)


def test_an_eliminated_participant_sees_a_spectate_only_option(content, game):
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=0.0)
    with mock.patch("tianxia.engine.time.time", return_value=0.0):
        game.choose("battle:join:guan")
    after_muster = definition.muster_seconds + 1
    with mock.patch("tianxia.engine.time.time", return_value=after_muster):
        game._battle_status()  # 讓集結自動關閉
    game.world.mutate_battle(lambda b: setattr(b.participants["沈浪"], "eliminated", True))
    with mock.patch("tianxia.engine.time.time", return_value=after_muster):
        opts = game.options()
    assert opts == [Option(id="battle:spectate", label="（觀戰中，無法行動）", enabled=False)]


def test_a_latecomer_can_join_an_already_active_battle(content, game):
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=0.0)
    with mock.patch("tianxia.engine.time.time", return_value=definition.muster_seconds + 1):
        game._battle_status()  # 讓集結自動關閉，模擬戰鬥已經開打
        assert ids(game) == ["battle:join_late"]
        game.choose("battle:join_late")
    assert "沈浪" in game.world.get_battle().participants


def test_battle_ending_falls_back_to_normal_gameplay_on_the_next_render(content, game):
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=0.0)
    game.world.mutate_battle(lambda b: setattr(b, "phase", "ended"))
    assert game._battle_status() is None
    assert ids(game)[0] == "act:explore"


# ── 自訂行動輸入框（設計討論：魯莽該是玩家自己想出來的招，不是固定選單）────────


def _install_battle_def_with_free_text(content):
    from tianxia.models import (
        BattleAct, BattleActionEffect, BattleDef, BattleFaction, BattleOption, BattleOutcome,
    )

    definition = BattleDef(
        id="t2", name="測試決戰（自訂行動）",
        factions=[BattleFaction(id="guan", name="官軍"), BattleFaction(id="huang", name="黃巾")],
        acts=[
            BattleAct(
                id="a1", title="初探", text="雙方試探。", goal="推動戰局",
                options=[
                    BattleOption(text="穩紮穩打", tag="safe", faction="guan"),
                    BattleOption(text="放手一搏（20字內）", tag="reckless", faction="guan", free_text=True),
                    BattleOption(text="死守營寨", tag="huang_safe", faction="huang"),
                ],
            ),
        ],
        action_tags={
            "safe": BattleActionEffect(trend_delta=1, neili_damage=5),
            "reckless": BattleActionEffect(trend_delta=10, neili_damage=50),
            "huang_safe": BattleActionEffect(trend_delta=-1, neili_damage=5),
        },
        outcomes=[BattleOutcome(faction="guan", title="官軍大勝", text="官軍獲勝。")],
        muster_seconds=600, round_seconds=120,
    )
    content.battles[definition.id] = definition
    return definition


def _join_and_open(content, game, definition):
    game.world.start_battle(definition, now=0.0)
    with mock.patch("tianxia.engine.time.time", return_value=0.0):
        game.choose("battle:join:guan")
        game.world.mutate_battle(
            lambda b: battle_instance.join_faction(b, "機器人", "huang", neili_cap=100.0, is_bot=True)
        )
    after_muster = definition.muster_seconds + 1
    with mock.patch("tianxia.engine.time.time", return_value=after_muster):
        game._battle_status()
    return after_muster


def test_free_text_option_is_excluded_from_the_button_list(content, game):
    definition = _install_battle_def_with_free_text(content)
    after_muster = _join_and_open(content, game, definition)
    with mock.patch("tianxia.engine.time.time", return_value=after_muster):
        assert [o.label for o in game.options()] == ["穩紮穩打"]  # 自訂行動不是按鈕


def test_battle_free_text_prompt_shows_when_available(content, game):
    definition = _install_battle_def_with_free_text(content)
    after_muster = _join_and_open(content, game, definition)
    with mock.patch("tianxia.engine.time.time", return_value=after_muster):
        assert game.battle_free_text_prompt() == "放手一搏（20字內）"


def test_battle_free_text_prompt_is_none_outside_battle(content, game):
    assert game.battle_free_text_prompt() is None


def test_battle_free_text_prompt_is_none_after_submitting(content, game):
    definition = _install_battle_def_with_free_text(content)
    after_muster = _join_and_open(content, game, definition)
    with mock.patch("tianxia.engine.time.time", return_value=after_muster):
        game.submit_battle_custom_action("直取波才首級")
        assert game.battle_free_text_prompt() is None


def test_submit_battle_custom_action_truncates_to_20_characters(content, game):
    """這場測試戰鬥只有一幕、保底結果沒有數值門檻，機器人補位後這回合會立刻結算（round
    也會跟著重置），所以改檢查 narrative_log（結算後仍然保留）而不是 round.custom_texts
    （結算後已經清空）。"""
    definition = _install_battle_def_with_free_text(content)
    after_muster = _join_and_open(content, game, definition)
    long_text = "一二三四五六七八九十" * 3  # 30 字
    with mock.patch("tianxia.engine.time.time", return_value=after_muster):
        game.submit_battle_custom_action(long_text)
    battle = game.world.get_battle()
    assert any(long_text[:20] in line for line in battle.narrative_log)
    assert not any(long_text in line for line in battle.narrative_log)  # 完整 30 字版本不該出現


def test_submit_battle_custom_action_rejects_empty_input(content, game):
    definition = _install_battle_def_with_free_text(content)
    after_muster = _join_and_open(content, game, definition)
    with mock.patch("tianxia.engine.time.time", return_value=after_muster):
        msgs = game.submit_battle_custom_action("   ")
    assert msgs == ["（請先輸入你想做的事。）"]
    assert "沈浪" not in game.world.get_battle().round.pending_actions


def test_submit_battle_custom_action_outside_battle_is_a_no_op(content, game):
    assert game.submit_battle_custom_action("test") == ["（此刻無法這麼做。）"]


def test_submit_battle_custom_action_works_even_as_the_very_first_call_after_muster_overruns(content, game):
    """自訂行動輸入框不是透過 choose() 進來的，沒有 choose() 開頭那次 self.options()
    順便推進過一次的保護——真的抓到過的 bug：如果這是集結逾時後的第一個請求，
    submit_battle_custom_action() 自己沒有先追趕，battle_instance.submit_action()
    內部看到 battle.phase 還是 "muster" 會悄悄把這次送出的行動吃掉，玩家完全不知道
    自己其實白打了一輪字。"""
    definition = _install_battle_def_with_free_text(content)
    game.world.start_battle(definition, now=0.0)
    with mock.patch("tianxia.engine.time.time", return_value=0.0):
        game.choose("battle:join:guan")
        game.world.mutate_battle(
            lambda b: battle_instance.join_faction(b, "機器人", "huang", neili_cap=100.0, is_bot=True)
        )
    after_muster = definition.muster_seconds + 1
    with mock.patch("tianxia.engine.time.time", return_value=after_muster):
        # 注意：這裡故意不先呼叫 game.options()/game._battle_status() 暖身，
        # 直接送出自訂行動，模擬「這是逾時後第一個進來的請求」。
        msgs = game.submit_battle_custom_action("直取波才首級")
    assert msgs != ["（此刻無法這麼做。）"]
    battle = game.world.get_battle()
    assert any("直取波才首級" in line for line in battle.narrative_log)


def test_custom_action_mechanics_match_the_fixed_tag_regardless_of_text(content, game):
    """這個 fixture 沒有設定 free_text_gamble，所以就算玩家打的字會先被送去評成功率，
    resolve_round 還是會退回 action_tags 查表那條路（見 battle_instance.py 的對應測試），
    機制效果不會因為文字內容不同而有不同結果——有設定 free_text_gamble 的戰鬥則相反，
    見 test_submit_battle_custom_action_assesses_success_rate_and_feeds_the_gamble。"""
    definition = _install_battle_def_with_free_text(content)
    after_muster = _join_and_open(content, game, definition)
    with mock.patch("tianxia.engine.time.time", return_value=after_muster):
        game.submit_battle_custom_action("直取波才首級")
    battle = game.world.get_battle()
    cap = game._battle_neili_cap()  # 玩家真實的氣血上限（join 時是這樣算的，不是隨便假設的數字）
    assert battle.participants["沈浪"].neili == cap - 50  # reckless 的 50 點損耗


def _install_battle_def_with_gamble(content):
    from tianxia.models import FreeTextGamble

    definition = _install_battle_def_with_free_text(content)
    definition.id = "t3"
    content.battles[definition.id] = definition
    definition.free_text_gamble = FreeTextGamble(
        success_trend_base=5, success_trend_per_risk=0.3, success_neili_damage=10,
        failure_trend_per_risk=0.1, failure_neili_base=20, failure_neili_per_risk=3.0,
    )
    return definition


def test_submit_battle_custom_action_assesses_success_rate_and_feeds_the_gamble(content, game):
    """跟上一個測試同一套劇本，差別只在這個 definition 有設定 free_text_gamble——這次
    送出的自訂行動會先呼叫 LLM（這裡用 mock）評成功率，評出來的結果真的拿去擲骰、
    算出不是固定 50 點的傷害，證明整條鏈路（engine.submit_battle_custom_action →
    battle_instance.assess_action_success_rate → resolve_round 的賭局分支）真的接起來了。"""
    definition = _install_battle_def_with_gamble(content)
    after_muster = _join_and_open(content, game, definition)
    with mock.patch("tianxia.engine.time.time", return_value=after_muster), \
         mock.patch.object(game.client, "chat_structured", return_value=battle_instance.SuccessRateJudgment(success_rate=20)):
        game.submit_battle_custom_action("直取波才首級")
    battle = game.world.get_battle()
    cap = game._battle_neili_cap()
    # success_rate=20、risk=80：成功時只扣固定的 10（傷害很小，賭贏代價低），失敗時扣
    # 20+80*3=260——用的是 game.rng（真的隨機，不是 FixedRandom），究竟成功還是失敗
    # 不好預測，但傷害一定精確落在這兩個數字其中之一，不會是固定查表的 50，證明真的
    # 走了賭局公式（不是退回 action_tags 查表那條路）。
    damage = cap - battle.participants["沈浪"].neili
    assert damage in (10, 260)
