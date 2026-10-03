import random
import time
from unittest import mock

import pytest

from conftest import FixedRandom, walk_to
from tianxia import battle_instance, companion_agent, flavor, rules
from tianxia.engine import Game, Option
from tianxia.state import BotProfile, GameState, Journey
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
    walk_to(game, "lake")
    assert "move:cave" not in ids(game)
    game.state.world.flags.add("cave_open")
    assert "move:cave" in ids(game)


def test_socialize_hidden_when_no_events_here(game):
    game.state.world.flags.add("cave_open")
    walk_to(game, "lake")
    game.state.player.location = "cave"
    assert "act:socialize" not in ids(game)


def test_recruit_option_follows_who_is_free_at_this_location(game):
    assert "招募【韓鐵】（體力 15・成功率約 35%）" in [o.label for o in game.options() if o.id == "act:recruit"]
    walk_to(game, "lake")
    assert "招募【琴師】（體力 15・成功率約 35%）" in [o.label for o in game.options() if o.id == "act:recruit"]
    game.world.try_recruit("friend", "李四")
    game.world.try_recruit("hero", "李四")
    assert "act:recruit" not in ids(game)  # 湖邊兩人都被搶走了


def test_recruit_option_shows_the_real_odds_and_tracks_affinity(game):
    """實機 playtest 發現招募失敗時玩家完全看不出原因、也不知道好感度才是真正的槓桿
    （roster.py::recruit_chance）。選單上的成功率要跟著好感度即時變化，不是寫死的。"""
    def label():
        return next(o.label for o in game.options() if o.id == "act:recruit")

    assert "成功率約 35%" in label()  # 好感度 0：基礎成功率
    game.state.player.affinities["mate"] = 100
    assert "成功率約 85%" in label()  # 基礎 35% + 好感度 100 的加成 50%


def test_walking_to_a_neighbour_costs_no_stamina(game):
    game.state.player.stamina = 0
    move = next(o for o in game.options() if o.id == "move:lake")
    assert move.enabled and move.label == "前往 湖邊（步行約 3 分鐘）"
    game.choose("move:lake")
    assert game.state.player.stamina == 0


def test_invalid_option_rejected(game):
    assert game.choose("move:cave") == ["（此刻無法這麼做。）"]
    assert game.state.player.location == "town"


def test_insufficient_stamina_disables_actions(game):
    game.state.player.stamina = 4
    opts = game.options()
    assert all(not o.enabled for o in opts if o.id != "act:rest" and not o.id.startswith("move:"))
    assert all(o.enabled for o in opts if o.id.startswith("move:"))  # 步行不花體力
    game.choose("act:explore")
    assert game.state.player.stamina == 4


def test_rest_is_always_available_and_never_locks_the_player_out(game):
    """實機 playtest 發現的卡死情境：體力見底時過去完全沒有選項可點，新玩家只能乾等。
    act:rest（打坐）必須永遠是 enabled，坐下來之後時間過去就真的會回體力。"""
    game.state.player.stamina = 0
    rest = next(o for o in game.options() if o.id == "act:rest")
    assert rest.enabled
    game.choose("act:rest")
    game.advance(HOUR)
    assert game.state.player.stamina > 0


# ── 打坐 ──────────────────────────────────────────────


def test_sitting_down_is_a_state_you_stand_up_from(game):
    game.choose("act:rest")
    assert game.state.player.resting_since == game.state.world.time
    assert ids(game) == ["act:stand"]
    assert game.choose("act:explore") == ["（此刻無法這麼做。）"]
    assert game.seclude(4) == ["你現在無法閉關。"]
    assert "打坐中" in game.status_text()
    game.choose("act:stand")
    assert game.state.player.resting_since is None
    assert "act:explore" in ids(game)
    assert game.state.journal[0].title == "起身"


def test_sitting_doubles_the_natural_regen(game):
    cfg = game.content.config
    game.state.player.stamina = 0
    game.choose("act:rest")
    game.advance(1800)
    sitting = 1800 / cfg.stamina_regen_seconds * cfg.rest_regen_multiplier
    assert game.state.player.stamina == pytest.approx(sitting)
    game.choose("act:stand")
    game.advance(1800)
    assert game.state.player.stamina == pytest.approx(sitting + 1800 / cfg.stamina_regen_seconds)


def test_sitting_counts_real_time_between_syncs(game):
    cfg = game.content.config
    game.sync(1000.0)
    game.state.player.stamina = 0
    game.choose("act:rest")
    game.sync(1000.0 + 1800)
    assert game.state.player.stamina == pytest.approx(1800 / cfg.stamina_regen_seconds * cfg.rest_regen_multiplier)


def test_sitting_ends_by_itself_once_stamina_is_full(game):
    game.state.player.stamina = game.content.config.stamina_max - 1
    game.choose("act:rest")
    game.advance(HOUR)
    assert game.state.player.resting_since is None
    assert game.state.player.stamina == game.content.config.stamina_max
    entry = game.state.journal[0]
    assert entry.title == "起身" and "回滿" in entry.lines[0]


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
    walk_to(game, "lake")
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
    rules.learn_skill(game.state, game.content, "fist")  # 沒武學＝威力 0，門檻改成比例後真的打不贏
    walk_to(game, "lake")
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
    rules.learn_skill(game.state, game.content, "fist")
    game.content.events["duel"].choices[0].effect.stats = {"fame": 3}
    game.content.events["duel"].choices[0].effect.rumor = "{name}擊敗了翻江龍！"
    walk_to(game, "lake")
    game.choose("act:socialize")
    game.rng = FixedRandom(1.0)
    game.choose("choice:0")
    record = game.state.battles[0]
    assert record.tier in ("大勝", "險勝")
    assert record.notes == ["你擊敗了翻江龍！", "（寇亂 -20）", "【江湖傳聞】沈浪擊敗了翻江龍！"]
    assert record.changes == ["名望 +3"]


def test_train_win_is_recorded_with_rewards(game):
    rules.learn_skill(game.state, game.content, "fist")  # 壓倒性的威力，穩贏
    game.content.config.train_event_chance = 1.0
    walk_to(game, "lake")
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
    walk_to(game, "lake")
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
    walk_to(game, "lake")
    game.state.player.seen_events.add("scroll")
    game.rng = FixedRandom(0.3)
    game.choose("act:explore")
    record = game.state.battles[0]
    assert record.tier in ("大勝", "險勝")
    assert record.changes and record.changes[0].split(" ")[1] == "+1"
    assert record.notes == ["（寇亂 -1）"]  # 湖邊 train_trend kou:-1


def test_train_event_chain(game):
    game.content.config.train_event_chance = 1.0
    walk_to(game, "lake")
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
        walk_to(game, "lake")  # 第一次去湖邊，不是重遊
    polish.assert_not_called()


def test_revisiting_a_location_appends_the_flavor_sentence(game):
    walk_to(game, "lake")
    with mock.patch.object(flavor, "polish_revisit", return_value="風又吹起了。"):
        msgs = game.travel("town", "dash")  # 疾行：在這次行動裡抵達終點；小鎮開局就去過，是重遊，補一句
    assert f"{game.location_text()}\n\n風又吹起了。" in msgs


def test_a_timed_arrival_never_calls_the_model(game):
    """計時器的 sync 拿著全服行動鎖：路上抵達不叫模型（重遊點綴句、江湖大事潤色都不叫）。"""
    walk_to(game, "lake")
    with mock.patch.object(flavor, "polish_revisit") as revisit, \
            mock.patch.object(flavor, "polish_world_event") as news:
        game.choose("move:town")  # 小鎮開局就去過：重遊
        game.state.world.trends["kou"] = 50  # 抵達時才跨過「水寇封江」
        game.advance(game.state.player.journey.arrive_at[-1] - game.state.world.time)
    assert "blocked" in game.state.world.flags  # 門檻照樣觸發，只是沒潤色
    revisit.assert_not_called()
    news.assert_not_called()


def test_revisiting_an_important_location_skips_flavor(content, game):
    content.locations["town"].important = True
    walk_to(game, "lake")
    with mock.patch.object(flavor, "polish_revisit") as polish:
        game.travel("town", "dash")
    polish.assert_not_called()


def test_revisiting_skips_the_sentence_when_flavor_comes_back_empty(game):
    walk_to(game, "lake")
    with mock.patch.object(flavor, "polish_revisit", return_value=""):
        msgs = game.travel("town", "dash")
    assert game.location_text() in msgs  # 失敗就整句省略，不多附加任何東西


def test_only_the_last_stop_of_a_trip_gets_the_flavor_sentence(game):
    game.state.world.flags.add("cave_open")
    game.state.player.visited |= {"lake", "cave"}
    with mock.patch.object(flavor, "polish_revisit", return_value="風又吹起了。") as polish:
        game.travel("cave", "dash")
    polish.assert_called_once()
    assert polish.call_args.args[1] == "寶洞"


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
    member = game.state.player.member
    member.neili = 10.0  # 只有輕傷：會自己回，不該收錢（療傷按內傷計價，見 team.heal_cost）
    assert game.heal() == ["氣血無恙，不用療傷。"]
    member.injury = 40.0
    game.state.player.stats["silver"] = 999
    msgs = game.heal()
    assert msgs[0].startswith("療傷完畢")
    assert member.injury == 0.0 and member.neili is None


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
    assert game.state.player.stamina == pytest.approx(600 / game.content.config.stamina_regen_seconds)


def test_sync_uses_real_clock_and_time_scale(game):
    game.content.config.time_scale = 60
    game.state.player.stamina = 0
    game.sync(1000.0)
    game.sync(1010.0)
    assert game.state.world.time == pytest.approx(600)
    assert game.state.player.stamina == pytest.approx(600 / game.content.config.stamina_regen_seconds)


def test_season_ends_by_time(game):
    game.advance(2 * DAY)
    w = game.state.world
    assert w.ended and w.ending_title == "風雨飄搖"
    assert "blocked" in w.flags
    assert ids(game) == ["season:resting"]


def test_admin_next_season_resets_and_keeps_the_name_and_last_real(game):
    game.content.config.admins = ["沈浪"]
    game.sync(1000.0)
    game.advance(2 * DAY)
    game.admin_next_season(now=2000.0)
    assert not game.state.world.ended
    assert game.state.world.trends["kou"] == 30
    assert game.state.player.name == "沈浪"
    assert game.state.player.season_number == 2
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
    a.content.config.admins = ["甲"]
    a.admin_next_season(now=1.0)
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


def test_a_fresh_server_waits_for_the_admin(content, world):
    content.config.auto_open_first_season = False
    game = Game.new(content, "甲", rng=random.Random(1), world=world)
    assert [(o.id, o.enabled) for o in game.options()] == [("season:preparing", False)]
    assert game.choose("act:explore") == ["（此刻無法這麼做。）"]


def test_only_an_admin_can_open_the_season(content, world):
    content.config.auto_open_first_season = False
    content.config.admins = ["管理者"]
    player = Game.new(content, "甲", rng=random.Random(1), world=world)
    assert player.admin_open_season(now=0.0) == ["（只有管理者能開季。）"]
    admin = Game.new(content, "管理者", rng=random.Random(2), world=world)
    admin.admin_open_season(now=0.0)
    assert world.season_phase() == "running"
    assert admin.admin_open_season(now=1.0) == ["（現在不是籌備期，無法開季。）"]
    player.sync(10.0)
    assert "act:explore" in ids(player)


def test_the_shared_clock_does_not_run_while_preparing(content, world):
    content.config.auto_open_first_season = False
    content.config.time_scale = 60
    game = Game.new(content, "甲", rng=random.Random(1), world=world)
    game.sync(1000.0)
    game.sync(1010.0)
    assert game.state.world.time == 0


def test_travel_is_refused_while_preparing(content, world):
    content.config.auto_open_first_season = False
    game = Game.new(content, "甲", rng=random.Random(1), world=world)
    assert game.travel("lake") == ["（賽季籌備中，等待管理者開季。）"]
    assert game.state.player.location == "town"


def test_nothing_personal_can_be_done_while_preparing(content, world):
    content.config.auto_open_first_season = False
    game = Game.new(content, "甲", rng=random.Random(1), world=world)
    waiting = ["（賽季籌備中，等待管理者開季。）"]
    assert game.create_skill("驚雷掌", "武學") == waiting
    assert game.practice("武學") == waiting
    assert game.heal() == waiting
    assert game.add_to_team("mate") == waiting
    assert game.remove_from_team("mate") == waiting
    assert game.seclude(4) == ["你現在無法閉關。"]
    assert game.state.player.busy_until is None
    assert game.state.player.member.wugong_id is None
    game.state.player.materials = {"gang_1": 2}
    game.state.player.stats["xinde"] = 500
    assert game.craft(["gang_1", "gang_1"], "武學") == waiting
    assert game.state.player.materials == {"gang_1": 2}
    assert game.switch_art("驚雷掌") == waiting


def test_players_cannot_start_the_next_season_themselves(game):
    game.advance(2 * DAY)
    assert game.choose("season:new") == ["（此刻無法這麼做。）"]
    assert game.admin_next_season(now=0.0) == ["（只有管理者能開啟下一季。）"]
    assert game.state.world.ended


def test_admin_next_season_needs_the_season_to_be_over(game):
    game.content.config.admins = ["沈浪"]
    assert game.admin_next_season(now=0.0) == ["（這一季還沒結束，無法開啟下一季。）"]


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
    walk_to(game, "lake")
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


def test_status_text_shows_the_practice_hint_only_when_xinde_is_idle(game):
    assert "心得" in game.status_text() and "💡" not in game.status_text()
    game.state.player.stats["xinde"] = game.content.config.xinde_hint_threshold
    assert "💡" in game.status_text() and "鍛鍊內功、武學" in game.status_text()
    game.state.player.member.wugong_level = game.state.player.member.neigong_level = 10
    game.state.player.member.wugong_id = game.state.player.member.neigong_id = "fist"
    assert "💡" not in game.status_text()  # 沒東西可練、也湊不出一爐素材


def test_visited_and_map(game):
    assert game.state.player.visited == {"town"}
    walk_to(game, "lake")
    assert game.state.player.visited == {"town", "lake"}
    assert "<svg" in game.world_map_svg()
    assert "<svg" in game.minimap_svg()


# ── 安排前往 ──────────────────────────────────────────────


@pytest.mark.parametrize(("mode", "cost"), [("walk", 0), ("hurry", 8), ("dash", 15)])
def test_travel_charges_the_stamina_of_the_chosen_way_up_front(game, mode, cost):
    game.state.world.flags.add("cave_open")  # 小鎮—湖邊 3 分鐘＋湖邊—寶洞山路 4.5 分鐘
    game.state.player.stamina = 100
    game.travel("cave", mode)
    assert game.state.player.stamina == 100 - cost


def test_dash_arrives_at_once_and_writes_one_entry(game):
    game.state.world.flags.add("cave_open")
    before = len(game.state.journal)
    msgs = game.travel("cave", "dash")
    p = game.state.player
    assert p.location == "cave" and {"lake", "cave"} <= p.visited
    assert len(game.state.journal) == before + 1
    entry = game.state.journal[0]
    assert (entry.title, entry.tag, entry.lines, entry.changes) == ("前往 寶洞（途經 湖邊）", "疾行立刻到", [], ["體力 -15"])
    assert msgs[-1] == game.location_text() == game.scene_text()


def test_dash_stops_when_the_season_ends_on_the_way(game):
    game.state.world.flags.add("cave_open")
    game.state.world.trends["kou"] = 80  # 一走到湖邊就觸發「水寇稱霸」，賽季落幕
    game.travel("cave", "dash")
    assert game.state.world.ended and game.state.player.location == "lake"
    assert game.state.journal[0].tag == "賽季落幕，停在 湖邊"


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
    assert game.travel("lake", "fly") == ["（無法安排前往這裡。）"]
    game.state.player.stamina = 5
    assert game.travel("lake", "dash") == ["（體力不足，疾行要 6 體力。）"]
    assert game.travel_refusal("lake", "hurry") is None
    assert game.state.player.location == "town" and game.state.player.stamina == 5
    assert len(game.state.journal) == before


def test_walking_takes_time_and_arrives_on_the_next_sync(game):
    game.sync(1000.0)
    game.choose("move:lake")  # 夾具：小鎮—湖邊 3 分鐘
    p = game.state.player
    assert p.location == "town" and p.journey.path == ["lake"] and p.journey.arrive_at == [180.0]
    game.sync(1000.0 + 60)
    assert p.location == "town" and p.journey is not None  # 還在路上
    game.sync(1000.0 + 200)
    assert p.location == "lake" and p.journey is None and "lake" in p.visited


def test_hurrying_takes_half_the_time(game):
    game.state.world.flags.add("cave_open")
    game.travel("cave", "hurry")
    assert game.state.player.journey.arrive_at == [pytest.approx(90.0), pytest.approx(225.0)]  # (3＋4.5 分鐘) × 30 秒


def test_on_the_road_you_cannot_act(game):
    game.choose("move:lake")
    opts = game.options()
    assert [(o.id, o.enabled) for o in opts] == [("act:on_road", False)]
    assert "抵達湖邊" in opts[0].label
    assert game.choose("act:explore") == ["（此刻無法這麼做。）"]
    assert game.travel("lake") == ["（在路上，不能另外安排前往。）"]
    assert game.seclude(4) == ["你現在無法閉關。"]


def test_status_and_scene_show_the_arrival_time(game):
    game.choose("move:lake")
    assert "🧭 在路上：往湖邊（步行），第1天 00:03 抵達，還要約 3 分鐘" in game.status_text()
    scene = game.scene_text()
    assert scene.startswith("**在路上**") and "第1天 00:03 抵達" in scene and "到了會自己抵達" in scene


def test_every_station_on_the_way_fires_the_arrival_rules(game):
    game.state.world.flags.add("cave_open")
    game.state.player.tutorial_step = 1  # 下一步是「去湖邊」
    game.travel("cave", "walk")
    game.advance(game.state.player.journey.arrive_at[0] - game.state.world.time)  # 只走到湖邊
    p = game.state.player
    assert p.location == "lake" and "lake" in p.visited and p.journey.reached == 1
    assert p.tutorial_step == 2  # 抵達湖邊就完成這一步，不必等到終點
    game.advance(p.journey.arrive_at[1] - game.state.world.time)
    assert p.location == "cave" and p.journey is None


def test_departing_is_not_arriving_for_the_tutorial(game):
    game.state.player.tutorial_step = 1  # 「去湖邊」
    game.choose("move:lake")
    assert game.state.player.tutorial_step == 1
    game.advance(game.state.player.journey.arrive_at[-1] - game.state.world.time)
    assert game.state.player.tutorial_step == 2


def test_a_threshold_crossed_on_arrival_reaches_the_shared_season(game):
    game.sync(1000.0)
    game.choose("move:lake")
    # sync 會先換成共用賽季的那一份，所以改共用的；追趕那 200 秒不滿一小時，世界本身不檢查門檻
    game.world.mutate_season(lambda season: season.trends.__setitem__("kou", 80))
    game.sync(1000.0 + 200)  # 抵達時才檢查：水寇稱霸，賽季落幕
    assert game.state.world.ended and game.world.get_season().ended


def test_a_season_that_ends_on_the_road_leaves_you_where_you_got_to(game):
    game.state.world.flags.add("cave_open")
    game.travel("cave", "walk")
    game.state.world.ended = True
    game.advance(0)  # 時鐘停在落幕那一刻：還沒到的站不會再到
    assert game.state.player.journey is None and game.state.player.location == "town"
    assert game.state.journal[0].tag == "賽季落幕，停在 小鎮"


def test_a_stale_journey_is_dropped_on_load(content, game):
    game.state.player.journey = Journey(mode="walk", path=["nowhere"], arrive_at=[60.0])
    reloaded = Game(content, game.state, world=game.world)
    assert reloaded.state.player.journey is None


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


def _install_factions(content):
    from tianxia.models import FactionDef

    content.scenario.factions = [
        FactionDef(id="guan", name="官軍", join_at=["town"]),
        FactionDef(id="huang", name="黃巾"),
        FactionDef(id="haoqiang", name="地方豪強"),
    ]


def test_a_free_agent_can_join_a_faction_where_it_recruits(content, game):
    _install_factions(content)
    assert "faction:guan" in ids(game)
    game.choose("faction:guan")
    game.choose("faction:confirm")
    assert game.state.player.faction == "guan"
    assert "faction:guan" not in ids(game)


def test_the_join_option_only_shows_at_the_factions_own_places(content, game):
    _install_factions(content)
    walk_to(game, "lake")
    assert not any(i.startswith("faction:") for i in ids(game))


def test_with_factions_the_muster_only_offers_your_own_side(content, game):
    _install_factions(content)
    definition = _install_battle_def(content)
    game.state.player.faction = "huang"
    game.world.start_battle(definition, now=1000.0)
    with mock.patch("tianxia.engine.time.time", return_value=1000.0):
        assert ids(game) == ["battle:join:huang"]
        assert game.choose("battle:join:guan") == ["（此刻無法這麼做。）"]
        assert "選擇陣營" in game.scene_text()


def test_with_factions_joining_the_other_side_directly_is_refused(content, game):
    """選單上本來就不會出現對方陣營的加入選項；直接呼叫 _battle_choose 也一樣擋得住。"""
    _install_factions(content)
    definition = _install_battle_def(content)
    game.state.player.faction = "huang"
    game.world.start_battle(definition, now=1000.0)
    assert game._battle_choose("join:guan") == ["（你只能站在自己陣營這一邊。）"]
    assert game.world.get_battle().participants == {}


def test_with_factions_a_free_agent_or_an_outside_faction_watches_and_keeps_playing(content, game):
    _install_factions(content)
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=1000.0)
    with mock.patch("tianxia.engine.time.time", return_value=1000.0):
        for faction in (None, "haoqiang"):
            game.state.player.faction = faction
            assert "act:explore" in ids(game)
            assert not any(i.startswith("battle:") for i in ids(game))
            scene = game.scene_text()
            assert "測試決戰" in scene and "觀戰" in scene and "選擇陣營" not in scene


def test_with_factions_a_free_agent_can_leave_the_sidelines_once_the_battle_is_under_way(content, game):
    _install_factions(content)
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=0.0)
    game.world.mutate_battle(lambda b: battle_instance.join_faction(b, "乙玩家", "huang", neili_cap=100.0))
    with mock.patch("tianxia.engine.time.time", return_value=definition.muster_seconds + 1):
        assert game._battle_status()[0].phase == "active"
        assert "act:explore" in ids(game)
        assert not any(i.startswith("battle:") for i in ids(game))
        game.choose("faction:guan")
        game.choose("faction:confirm")
        assert game.state.player.faction == "guan"
        assert ids(game) == ["battle:join_late"]  # 投靠了交戰的一方，就能加入戰局


def test_a_watcher_still_sees_their_own_event_below_the_battle(content, game):
    _install_factions(content)
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=1000.0)
    with mock.patch("tianxia.engine.time.time", return_value=1000.0):
        game.choose("act:explore")
        event = content.events[game.state.pending_event]
        scene = game.scene_text()
    assert "測試決戰" in scene and event.title in scene


def test_with_factions_a_latecomer_joins_their_own_side(content, game):
    _install_factions(content)
    definition = _install_battle_def(content)
    game.state.player.faction = "huang"
    game.world.start_battle(definition, now=0.0)
    # 黃巾已經有人了，單看人數平衡會把後來的人分去官軍；玩家仍要站在自己的黃巾這一邊。
    game.world.mutate_battle(lambda b: battle_instance.join_faction(b, "乙玩家", "huang", neili_cap=100.0))
    with mock.patch("tianxia.engine.time.time", return_value=definition.muster_seconds + 1):
        game._battle_status()
        game.choose("battle:join_late")
    assert game.world.get_battle().participants["沈浪"].faction == "huang"


def test_a_battle_with_no_fighters_ends_with_its_fallback_outcome_once_the_round_times_out(content, game):
    _install_factions(content)
    definition = _install_battle_def(content)
    game.world.start_battle(definition, now=0.0)
    closed = definition.muster_seconds + 1
    with mock.patch("tianxia.engine.time.time", return_value=closed):
        assert game._battle_status()[0].phase == "active"
    with mock.patch("tianxia.engine.time.time", return_value=closed + definition.round_seconds - 1):
        assert game._battle_status() is not None  # 回合還沒逾時，不提前收場
    with mock.patch("tianxia.engine.time.time", return_value=closed + definition.round_seconds):
        assert "act:explore" in ids(game)
    assert game.world.get_battle().phase == "ended"
    assert any("官軍大勝" in r.text for r in game.world.get_season().chronicle)


def test_status_text_shows_the_faction_of_a_player_without_a_sect(content, game):
    _install_factions(content)
    assert "散人" in game.status_text()
    game.choose("faction:guan")
    game.choose("faction:confirm")
    assert "官軍" in game.status_text() and "散人" not in game.status_text()


def test_status_text_shows_both_sect_and_faction(content, game):
    _install_factions(content)
    game.state.player.sect = "cloud"
    assert "流雲派" in game.status_text() and "官軍" not in game.status_text()
    game.state.player.faction = "guan"
    assert "流雲派・官軍" in game.status_text()


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


def test_a_battle_threshold_crossed_in_the_background_starts_the_battle(content, game):
    """伺服器假人設計第八節第 1 項：沒人在行動時，大勢人物在背景把大勢推過開戰門檻，也要開戰。"""
    from tianxia.world import advance_season

    definition = _install_battle_def(content)
    content.scenario.thresholds[0].starts_battle = definition.id  # kou50
    game.world.mutate_season(lambda season: season.trends.__setitem__("kou", 60))
    msgs = advance_season(game.world, content, 3600, random.Random(0))
    battle = game.world.get_battle()
    assert battle is not None and battle.battle_id == definition.id and battle.phase == "muster"
    assert any("集結號角" in m for m in msgs)
    assert game.world.get_season().pending_battle is None


def test_fast_forwarding_across_a_battle_threshold_starts_the_battle(content, game):
    definition = _install_battle_def(content)
    content.scenario.thresholds[0].starts_battle = definition.id
    game.state.world.trends["kou"] = 60
    msgs = game.advance(3600)
    assert game.world.get_battle() is not None
    assert any("集結號角" in m for m in msgs)
    assert game.state.world.pending_battle is None
    assert game.world.get_season().pending_battle is None


def test_each_dialogue_turn_costs_stamina(content, game):
    """伺服器假人設計第八節第 4 項：跟大勢人物對話每一輪扣體力，不再是免費的。"""
    content.characters["mate"].deep_interaction = True
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        game.choose("act:socialize")
        before = game.state.player.stamina
        game.choose("talk:0")
    assert game.state.player.stamina == before - content.config.talk_stamina


def test_dialogue_turns_are_disabled_without_stamina_but_leaving_is_not(content, game):
    content.characters["mate"].deep_interaction = True
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        game.choose("act:socialize")
    game.state.player.stamina = content.config.talk_stamina - 1
    options = {o.id: o for o in game.options()}
    assert not options["talk:0"].enabled and not options["talk:1"].enabled
    assert options["talk:leave"].enabled


def test_joining_a_faction_asks_for_confirmation_and_shows_the_headcount(content, game):
    """伺服器假人設計第八節第 3 項：投靠要確認一次，確認畫面寫明不能改投與三方目前各有幾人。"""
    _install_factions(content)
    game.world.record_faction("別人", "huang")
    game.choose("faction:guan")
    assert game.state.player.faction is None
    assert ids(game) == ["faction:confirm", "faction:cancel"]
    scene = game.scene_text()
    assert "這一季不能改投" in scene
    assert "目前官軍 0 人、黃巾 1 人、地方豪強 0 人" in scene
    game.choose("faction:confirm")
    assert game.state.player.faction == "guan"
    assert game.world.faction_counts() == {"guan": 1, "huang": 1}


def test_thinking_again_leaves_you_a_free_agent(content, game):
    _install_factions(content)
    game.choose("faction:guan")
    game.choose("faction:cancel")
    assert game.state.player.faction is None and game.state.player.pending_faction is None
    assert "faction:guan" in ids(game)
    assert game.world.faction_counts() == {}


def test_a_player_who_joined_before_the_roll_existed_is_counted_on_the_next_sync(content, game):
    _install_factions(content)
    game.state.player.faction = "huang"
    game.sync(time.time())
    assert game.world.faction_counts() == {"huang": 1}


def test_a_new_season_keeps_a_server_bots_profile(content, game):
    profile = BotProfile(personality="積極", seed=7, faction="guan", season_number=1)
    game.state.player.bot = profile
    game.world.mutate_season(lambda season: setattr(season, "ended", True))
    assert game.world.next_season(content, now=time.time())
    game.sync(time.time())
    assert game.state.player.season_number == 2
    assert game.state.player.bot == profile


def test_a_server_bot_looks_exactly_like_a_player_on_screen(content, game):
    """伺服器假人設計第五節：「是假人」只記在存檔裡，畫面上任何地方都看不出來。"""
    before = (game.status_text(), game.scene_text(), game.quest_text(), game.journal_html(1, 5))
    game.state.player.bot = BotProfile(personality="積極", seed=7, faction="guan", season_number=1)
    assert (game.status_text(), game.scene_text(), game.quest_text(), game.journal_html(1, 5)) == before


# ── 管理者觸發（伺服器假人計畫 Task 8）────────────────────────


def _admin(content, game):
    content.config.admins = [game.state.player.name]
    return game


def test_only_an_admin_can_trigger_things(content, game):
    definition = _install_battle_def(content)
    assert game.admin_start_battle(definition.id, now=time.time()) == ["（只有管理者能開戰。）"]
    assert game.admin_fire("kou50") == ["（只有管理者能觸發大事。）"]
    assert game.admin_push_trend("kou", 10) == ["（只有管理者能推動大勢。）"]
    assert game.world.get_battle() is None
    assert "kou50" not in game.world.get_season().fired_thresholds
    assert game.world.get_season().trends["kou"] == 30


def test_an_admin_starts_a_battle_right_away(content, game):
    definition = _install_battle_def(content)
    _admin(content, game)
    msgs = game.admin_start_battle(definition.id, now=time.time())
    assert any("集結號角" in m for m in msgs)
    assert game.world.get_battle().phase == "muster"
    assert game.admin_start_battle(definition.id, now=time.time()) == ["（已經有一場戰鬥在進行。）"]
    assert game.admin_start_battle("no_such_battle", now=time.time()) == ["（沒有這場戰鬥。）"]


def test_an_admin_fires_a_great_event_once(content, game):
    _admin(content, game)
    msgs = game.admin_fire("kou50")
    assert any("水寇封江" in m for m in msgs)
    season = game.world.get_season()
    assert "kou50" in season.fired_thresholds and "blocked" in season.flags
    assert game.admin_fire("kou50") == ["（這件大事已經發生過了。）"]
    assert game.admin_fire("no_such_event") == ["（沒有這件大事。）"]


def test_firing_a_battle_threshold_by_hand_starts_its_battle(content, game):
    definition = _install_battle_def(content)
    content.scenario.thresholds[0].starts_battle = definition.id
    _admin(content, game)
    game.admin_fire("kou50")
    assert game.world.get_battle() is not None


def test_an_admin_push_crosses_thresholds_like_any_push(content, game):
    _admin(content, game)
    game.admin_push_trend("kou", 25)  # 30 → 55，跨過 kou50
    season = game.world.get_season()
    assert season.trends["kou"] == 55
    assert "kou50" in season.fired_thresholds
    assert game.admin_push_trend("no_such_trend", 5) == ["（沒有這條大勢線。）"]


def test_triggers_wait_for_the_season_to_run(content, game):
    _admin(content, game)
    game.world.mutate_season(lambda season: setattr(season, "ended", True))
    game.sync(time.time())
    assert game.admin_fire("kou50") == ["（賽季沒有在進行，無法觸發。）"]
    assert game.admin_push_trend("kou", 5) == ["（賽季沒有在進行，無法觸發。）"]
    assert game.admin_start_battle("t1", now=time.time()) == ["（賽季沒有在進行，無法觸發。）"]


# ── 煉製素材的掉落（無限煉製第一刀）──────────────────────────


def test_train_win_drops_a_material_into_the_bag_and_the_report(game):
    rules.learn_skill(game.state, game.content, "fist")  # 壓倒性的威力，穩贏
    game.content.config.train_event_chance = 1.0
    walk_to(game, "lake")
    game.state.player.seen_events.add("scroll")  # 避開探索遇到殘卷奇遇
    game.rng = FixedRandom(0.3)  # 水寇小隊難度 5：預設掉落表 50% 掉一個一階素材
    msgs = game.choose("act:explore")
    record = game.state.battles[0]
    assert record.materials == ["精鐵砂 ×1"]
    assert game.state.player.materials == {"gang_1": 1}
    assert "獲得 精鐵砂 ×1" in msgs


def test_a_hard_fought_loss_drops_nothing(game):
    game.content.locations["lake"].enemies = ["boss"]  # 打不贏的翻江龍
    game.content.config.train_event_chance = 1.0
    game.content.config.explore_material_chance = 0.0  # 只看戰鬥那條路，不要被探索自己撿到的混進來
    walk_to(game, "lake")
    game.state.player.seen_events.add("scroll")
    game.rng = FixedRandom(0.0)
    game.choose("act:explore")
    assert game.state.battles[0].tier == "落敗"
    assert game.state.player.materials == {}


def test_exploring_a_quiet_place_can_still_turn_up_a_material(game):
    game.state.player.location = "cave"  # fixture 的山洞沒有任何事件也沒有敵人
    game.content.locations["cave"].materials = ["gang_3"]
    game.rng = FixedRandom(0.0)
    msgs = game.choose("act:explore")  # 訊息串後面還會接新手引導的進度
    assert "你在寶洞翻找了一陣。" in msgs and "獲得 隕鐵膽 ×1" in msgs
    assert game.state.player.materials == {"gang_3": 1}


def test_exploring_and_finding_nothing_still_says_so(game):
    game.state.player.location = "cave"
    game.content.config.explore_material_chance = 0.0
    game.rng = FixedRandom(0.99)
    msgs = game.choose("act:explore")
    assert msgs[0] == "你四處走走，一無所獲。"
    assert not any("獲得" in m for m in msgs)
    assert game.state.player.materials == {}


def test_exploring_picks_up_a_material_even_when_an_event_fires(game):
    """素材的判定在事件之前：實測整季 100 次探索都撞到事件，掛在「一無所獲」上等於沒做。"""
    game.content.locations["town"].materials = ["gang_3"]
    game.rng = FixedRandom(0.0)  # 必中素材，也必定撞到鎮上的事件
    msgs = game.choose("act:explore")  # 訊息串後面還會接新手引導的進度
    assert any("【" in m for m in msgs)  # 真的有事件
    assert "獲得 隕鐵膽 ×1" in msgs
    assert game.state.player.materials == {"gang_3": 1}


# ── 歷練（第二層：遭遇戰的唯一管道）──────────────────────────


def test_train_is_offered_only_where_there_are_enemies(game):
    ids = [o.id for o in game.options()]
    assert "act:train" not in ids  # 鎮上沒有敵人
    walk_to(game, "lake")  # 湖邊有水寇小隊
    option = next(o for o in game.options() if o.id == "act:train")
    assert "歷練" in option.label and "水寇小隊" in option.label


def test_training_always_fights_even_though_an_event_would_have_fired(game):
    """探索永遠會撞到事件（pick_event 只在完全沒有候選時才回 None），所以掛在探索後面的
    遭遇戰分支一次都不會執行——歷練就是為了這件事存在的。"""
    rules.learn_skill(game.state, game.content, "fist")
    walk_to(game, "lake")
    game.rng = FixedRandom(0.99)  # 高到不會觸發戰後事件
    msgs = game.choose("act:train")
    assert game.state.battles and game.state.battles[0].opponent == "水寇小隊"
    assert game.state.pending_event is None  # 沒有被事件搶走
    assert any("⚔" in m for m in msgs)


def test_training_costs_the_configured_stamina(game):
    walk_to(game, "lake")
    before = game.state.player.stamina
    game.rng = FixedRandom(0.99)
    game.choose("act:train")
    assert before - game.state.player.stamina == game.content.config.action_cost["train"]


def test_a_post_battle_event_can_follow_the_fight(game):
    """「拆招頓悟」「錦衣少年」的文字本來就是戰後餘韻，現在掛回 actions: ["train"]。"""
    game.content.events["chain_a"].actions = ["train"]  # fixture 裡唯一掛在 train 上的事件
    game.content.config.train_event_chance = 1.0
    rules.learn_skill(game.state, game.content, "fist")
    walk_to(game, "lake")
    game.rng = FixedRandom(0.3)
    game.choose("act:train")
    assert game.state.battles  # 先打了一場
    assert game.state.pending_event == "chain_a"  # 再接上戰後的事件


def test_the_journal_calls_it_a_training_trip(game):
    rules.learn_skill(game.state, game.content, "fist")
    walk_to(game, "lake")
    game.rng = FixedRandom(0.99)
    game.choose("act:train")
    assert any(entry.title == "歷練・湖邊" for entry in game.state.journal)


def test_an_unavailable_dialogue_turn_costs_nothing_and_ends_the_talk(content, game):
    """模型叫不動：這輪不扣體力、不記好感度與交遊 tag，對話直接結束（不再卡在同一句保底反應裡）。"""
    content.characters["mate"].deep_interaction = True
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        game.choose("act:socialize")
    before = game.state.player.stamina
    with mock.patch.object(companion_agent, "_generate", side_effect=companion_agent.DialogueUnavailable("404")):
        msgs = game.choose("talk:0")
    assert msgs == ["韓鐵似乎無心多談，你只好先行告辭。"]
    assert game.state.player.stamina == before
    assert game.state.player.pending_companion is None
    assert game.state.player.affinities.get("mate", 0) == 0
    assert "mate" not in game.world.read().companion_tag_counts


def test_an_unavailable_opening_refunds_the_socialize_cost(content, game):
    content.characters["mate"].deep_interaction = True
    before = game.state.player.stamina
    with mock.patch.object(companion_agent, "_generate", side_effect=companion_agent.DialogueUnavailable("404")):
        msgs = game.choose("act:socialize")
    assert msgs == ["韓鐵似乎無心多談，你只好先行告辭。"]
    assert game.state.player.stamina == before
    assert game.state.player.pending_companion is None

def _training_factions(content):
    from tianxia.models import FactionDef

    content.scenario.factions = [
        FactionDef(id="guan", name="官軍", join_at=["town"], goals={"kou": -1}),
        FactionDef(id="huang", name="黃巾", join_at=["lake"], goals={"kou": 1}),
        FactionDef(id="haoqiang", name="地方豪強"),
    ]


@pytest.mark.parametrize("faction, expected", [("huang", 31), ("guan", 29), ("haoqiang", 29), (None, 29)])
def test_winning_a_training_fight_pushes_the_trend_your_factions_way(content, game, faction, expected):
    """企劃者決定：歷練推大勢的量照地點，方向照自己陣營的目標；散人和沒有這條線目標的陣營照地點原本的方向。"""
    _training_factions(content)
    game.state.player.faction = faction
    rules.learn_skill(game.state, game.content, "fist")  # 壓倒性的威力，穩贏
    walk_to(game, "lake")
    game.choose("act:train")  # 湖邊的對手是水寇小隊（不屬於任何陣營），train_trend kou:-1
    assert game.state.battles[0].kind == "train"
    assert game.state.world.trends["kou"] == expected


def test_training_with_your_own_factions_squad_is_a_drill(content, game):
    """遇到自己陣營的人不開打，改成一起操軍擺陣：不會輸、給經驗與心得、不給銀兩不掉素材，大勢往自己這邊推。"""
    _training_factions(content)
    content.squads["thug"].faction = "huang"
    game.state.player.faction = "huang"  # 沒學武功也沒關係：操練不會輸
    walk_to(game, "lake")
    silver, xinde = game.state.player.stats["silver"], game.state.player.stats.get("xinde", 0)
    msgs = game.choose("act:train")
    assert any("操軍擺陣" in m for m in msgs)
    assert game.state.battles == []
    assert game.state.player.stats["silver"] == silver
    assert game.state.player.stats["xinde"] == xinde + content.squads["thug"].reward_xinde
    assert game.state.player.member.exp > 0 or game.state.player.member.level > 1
    assert game.state.player.materials == {}
    assert game.state.world.trends["kou"] == 31


def test_train_trend_push_previews_the_push_for_your_faction(content, game):
    _training_factions(content)
    game.state.player.faction = "huang"
    assert game.train_trend_push("lake") == {"kou": 1}
    assert game.train_trend_push("town") == {}
    game.state.player.faction = None
    assert game.train_trend_push("lake") == {"kou": -1}

def test_a_drill_is_journaled_as_a_drill_without_a_battle_card(content, game):
    _training_factions(content)
    content.squads["thug"].faction = "huang"
    game.state.player.faction = "huang"
    walk_to(game, "lake")
    game.choose("act:train")
    entry = game.state.journal[0]
    assert (entry.title, entry.tag, entry.battle_id) == ("歷練・湖邊", "操練", None)
    assert entry.changes == ["心得 +10", "經驗 +20（每人）"] and entry.lines == ["（寇亂 +1）"]
    assert game.state.battle_card is None


def test_a_drill_is_not_followed_by_a_post_fight_event(content, game):
    """操練不是打架，不該接「一番苦戰之後」這類戰後事件（試玩回饋 FB-001）。"""
    _training_factions(content)
    content.squads["thug"].faction = "huang"
    content.config.train_event_chance = 1.0
    game.state.player.faction = "huang"
    walk_to(game, "lake")
    msgs = game.choose("act:train")
    assert any("操軍擺陣" in m for m in msgs)
    assert game.state.pending_event is None


def _figure(content, fame=0):
    ch = content.characters["mate"]
    ch.deep_interaction = True
    ch.audience_fame = fame
    return ch


def test_a_newcomer_without_fame_is_turned_away_from_a_figure(content, game):
    _figure(content, fame=10)
    with mock.patch("tianxia.engine.pick_event", return_value=None), \
            mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        msgs = game.choose("act:socialize")
    assert game.state.player.pending_companion is None
    assert msgs == ["你想求見韓鐵，但人微言輕，被擋在門外（名望 10 以上才見得到）。"]


def test_enough_fame_or_a_prior_meeting_opens_the_door(content, game):
    _figure(content, fame=10)
    game.state.player.flags.add("結識:mate")
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        game.choose("act:socialize")
    assert game.state.player.pending_companion == "mate"
    game.choose("talk:leave")
    game.state.player.flags.discard("結識:mate")
    game.state.player.stats["fame"] = 10
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        game.choose("act:socialize")
    assert game.state.player.pending_companion == "mate"


def test_three_turns_a_day_with_the_same_figure(content, game):
    _figure(content)
    game.state.player.fortune = True  # 第二天起交遊會先觸發新立門戶福緣，這裡只測輪數上限
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        game.choose("act:socialize")
        game.choose("talk:0")
        game.choose("talk:0")
        msgs = game.choose("talk:0")
        assert msgs[-1] == "天色已晚，韓鐵起身送客，改日再敘。"
        assert game.state.player.pending_companion is None
        with mock.patch("tianxia.engine.pick_event", return_value=None):
            msgs = game.choose("act:socialize")
        assert msgs == ["韓鐵今日事忙，改日再來拜會吧。"]
        game.state.world.time += 86400  # 隔天重算
        game.choose("act:socialize")
    assert game.state.player.pending_companion == "mate"


def test_socialize_is_offered_where_a_figure_stands_even_if_you_cannot_meet_him(content, game):
    """寶洞沒有交遊事件：沒有大勢人物時不給交遊；有一位見不到的大勢人物時照樣給，按下去才知道為什麼見不到。"""
    game.state.player.location = "cave"
    assert "act:socialize" not in ids(game)
    ch = _figure(content, fame=10)
    ch.kind, ch.recruit_at, ch.talk_at = "locked", None, "cave"
    assert game.state.player.stats.get("fame", 0) < 10
    assert "act:socialize" in ids(game)


def test_a_newcomer_below_the_threshold_gets_the_locations_event_instead_of_a_dialogue(content, game):
    """小鎮有交遊事件（拜師）也有一位名望不夠的大勢人物：不 mock pick_event，交遊照地點事件走，不算被擋在門外。"""
    _figure(content, fame=10)
    msgs = game.choose("act:socialize")
    assert game.state.player.pending_companion is None
    assert game.state.pending_event is not None
    assert "你想求見韓鐵，但人微言輕，被擋在門外（名望 10 以上才見得到）。" not in msgs


# ── 鎖外生成：dialogue_request 與 choose(prepared=...) ────────────────


def _open_dialogue(content, game):
    """停在小鎮、已跟韓鐵開了第一輪對話（選項是「閒聊幾句」「就此告辭」）；福緣設成已領，交遊不會先觸發福緣。"""
    _figure(content)
    game.state.player.fortune = True
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        game.choose("act:socialize")


def _prepared(game, option_id, turn=FAKE_TURN):
    req = game.dialogue_request(option_id)
    return companion_agent.PreparedTurn(req.option_id, req.companion_id, req.player_action, turn)


NEXT_TURN = companion_agent.CompanionTurn(
    narrative="他笑了笑。", options=["再聊聊", "起身告辭"], option_tags=["雪中送炭", "尋常寒暄"],
)


def _no_model():
    """讓任何一條「在鎖內生成」的路徑直接失敗，證明這輪用的是預先生成好的。"""
    return mock.patch.object(companion_agent, "_generate", side_effect=AssertionError("不該在鎖內生成"))


def test_dialogue_request_for_a_talk_option_carries_the_offered_text(content, game):
    _open_dialogue(content, game)
    req = game.dialogue_request("talk:0")
    assert (req.option_id, req.companion_id, req.player_action) == ("talk:0", "mate", "閒聊幾句")
    assert req.messages[-1]["content"].startswith("玩家的行動：「閒聊幾句」")
    assert game.dialogue_request("talk:1").player_action == "就此告辭"


def test_dialogue_request_is_none_for_leaving_and_for_options_that_are_not_offered(content, game):
    _open_dialogue(content, game)
    assert game.dialogue_request("talk:leave") is None
    assert game.dialogue_request("talk:2") is None  # 只有兩個選項
    assert game.dialogue_request("talk:x") is None
    assert game.dialogue_request("act:socialize") is None  # 對話中選單上沒有交遊


def test_dialogue_request_for_socialize_is_the_generic_opening(content, game):
    _figure(content)
    game.state.player.fortune = True
    req = game.dialogue_request("act:socialize")
    assert (req.option_id, req.companion_id, req.player_action) == (
        "act:socialize", "mate", companion_agent.GENERIC_OPENING,
    )
    assert req.messages == companion_agent._build_messages(
        content.characters["mate"], game.state, content, game.world, "mate", companion_agent.GENERIC_OPENING,
    )


def test_dialogue_request_is_none_when_socialize_would_not_open_a_dialogue(content, game):
    _figure(content, fame=10)
    game.state.player.fortune = True
    assert game.dialogue_request("act:socialize") is None  # 名望不夠，見不到
    game.state.player.stats["fame"] = 10
    assert game.dialogue_request("act:socialize") is not None
    game.state.player.stamina = 0
    assert game.dialogue_request("act:socialize") is None  # 選項停用
    game.state.player.stamina = content.config.stamina_max
    game.state.world.time += 86400 * content.config.fortune_day_min
    game.state.player.fortune = False
    assert game.dialogue_request("act:socialize") is None  # 福緣先到，交遊不開對話


def test_dialogue_request_is_none_for_a_non_dialogue_option(content, game):
    _figure(content)
    game.state.player.fortune = True
    assert game.dialogue_request("act:explore") is None
    assert game.dialogue_request("move:lake") is None


def test_dialogue_request_does_not_change_the_game(content, game):
    _open_dialogue(content, game)
    before = game.state.model_dump()
    game.dialogue_request("talk:0")
    game.dialogue_request("act:socialize")
    assert game.state.model_dump() == before


def test_choose_applies_a_prepared_talk_turn_without_calling_the_model(content, game):
    _open_dialogue(content, game)
    before = game.state.player.stamina
    prepared = _prepared(game, "talk:0", turn=NEXT_TURN)
    with _no_model(), mock.patch.object(game.client, "chat_structured", side_effect=AssertionError("不該呼叫模型")):
        msgs = game.choose("talk:0", prepared=prepared)
    assert msgs == ["他笑了笑。", "（好感度 +1）"]
    assert game.state.player.stamina == before - content.config.talk_stamina
    assert game._talks_used("mate") == 1  # 這一輪算進今天的輪數
    assert game.state.player.last_offered_dialogue["mate"] == [["再聊聊", "起身告辭"], ["雪中送炭", "尋常寒暄"]]
    assert game.state.player.affinities["mate"] == 1


def test_choose_applies_a_prepared_opening_without_calling_the_model(content, game):
    _figure(content)
    game.state.player.fortune = True
    before = game.state.player.stamina
    prepared = _prepared(game, "act:socialize", turn=NEXT_TURN)
    with _no_model():
        msgs = game.choose("act:socialize", prepared=prepared)
    assert msgs == ["他笑了笑。"]
    assert game.state.player.pending_companion == "mate"
    assert game.state.player.stamina == before - content.config.action_cost["socialize"]
    assert ids(game) == ["talk:0", "talk:1", "talk:leave"]


def test_a_prepared_failure_for_the_opening_refunds_the_socialize_cost(content, game):
    """鎖外生成失敗（turn=None）：跟鎖內 DialogueUnavailable 完全一樣——退回交遊體力、不開對話、同一句說明。"""
    _figure(content)
    game.state.player.fortune = True
    before = game.state.player.stamina
    prepared = _prepared(game, "act:socialize", turn=None)
    with _no_model():
        msgs = game.choose("act:socialize", prepared=prepared)
    assert msgs == ["韓鐵似乎無心多談，你只好先行告辭。"]
    assert game.state.player.stamina == before
    assert game.state.player.pending_companion is None


def test_a_prepared_failure_for_a_talk_turn_costs_nothing_and_ends_the_talk(content, game):
    _open_dialogue(content, game)
    before = game.state.player.stamina
    prepared = _prepared(game, "talk:0", turn=None)
    with _no_model():
        msgs = game.choose("talk:0", prepared=prepared)
    assert msgs == ["韓鐵似乎無心多談，你只好先行告辭。"]
    assert game.state.player.stamina == before
    assert game.state.player.pending_companion is None
    assert game.state.player.affinities.get("mate", 0) == 0
    assert game._talks_used("mate") == 0
    assert "mate" not in game.world.read().companion_tag_counts


def test_a_mismatched_prepared_turn_is_ignored_and_the_normal_path_generates(content, game):
    """對不上（玩家行動不同，例如選項清單已經換了）：丟掉預先生成的，照一般路徑在鎖內生成。"""
    _open_dialogue(content, game)
    stale = companion_agent.PreparedTurn("talk:0", "mate", "已經不在選單上的話", FAKE_TURN)
    with mock.patch.object(companion_agent, "_generate", return_value=NEXT_TURN) as gen:
        msgs = game.choose("talk:0", prepared=stale)
    gen.assert_called_once()
    assert msgs[0] == "他笑了笑。"  # 用的是現生成的，不是 stale 帶的 FAKE_TURN


def test_a_mismatched_failed_prepared_turn_does_not_end_the_talk(content, game):
    """對不上的 prepared 連同它的失敗一起丟掉：不能因為別張單子失敗，就把這輪對話結束掉。"""
    _open_dialogue(content, game)
    stale = companion_agent.PreparedTurn("talk:0", "mate", "已經不在選單上的話", None)
    with mock.patch.object(companion_agent, "_generate", return_value=NEXT_TURN):
        msgs = game.choose("talk:0", prepared=stale)
    assert msgs[0] == "他笑了笑。"
    assert game.state.player.pending_companion == "mate"


def test_a_prepared_turn_for_another_companion_or_option_is_ignored(content, game):
    for stale in (
        companion_agent.PreparedTurn("talk:0", "someone_else", "閒聊幾句", FAKE_TURN),
        companion_agent.PreparedTurn("talk:1", "mate", "閒聊幾句", FAKE_TURN),
    ):
        _open_dialogue(content, game)
        with mock.patch.object(companion_agent, "_generate", return_value=NEXT_TURN) as gen:
            msgs = game.choose("talk:0", prepared=stale)
        gen.assert_called_once()
        assert msgs[0] == "他笑了笑。"
        game.choose("talk:leave")  # 退出這段對話，下一個 stale 重新開


def test_choose_rejects_a_second_opening_once_a_dialogue_is_already_open(content, game):
    """連點兩下：第二張單子進鎖時對話已經開了，交遊不在選單上——這是 choose() 自己的「選項可用」檢查擋下的，
    不是 prepared 的重驗（重驗見下一個測試）。"""
    _figure(content)
    game.state.player.fortune = True
    first, second = _prepared(game, "act:socialize"), _prepared(game, "act:socialize")
    with _no_model():
        game.choose("act:socialize", prepared=first)
        stamina = game.state.player.stamina
        assert game.choose("act:socialize", prepared=second) == ["（此刻無法這麼做。）"]
    assert game.state.player.stamina == stamina


def test_a_prepared_turn_is_ignored_by_options_that_do_not_use_it(content, game):
    _figure(content)
    game.state.player.fortune = True
    stray = companion_agent.PreparedTurn("act:explore", "mate", "x", FAKE_TURN)
    before = game.state.player.stamina
    with _no_model():
        game.choose("act:explore", prepared=stray)
    assert game.state.player.stamina == before - content.config.action_cost["explore"]
    assert game.state.player.pending_companion is None


def test_a_prepared_opening_is_dropped_by_the_recheck_when_the_fortune_comes_due_meanwhile(content, game):
    """生成的那段時間福緣到期：交遊選項還在、還能按，但這次交遊會先發福緣、不開對話——這才是重驗擋下來的情況。"""
    _figure(content)
    game.state.player.fortune = True
    prepared = _prepared(game, "act:socialize")
    game.state.player.fortune = False
    game.state.world.time += 86400 * content.config.fortune_day_min
    assert any(o.id == "act:socialize" and o.enabled for o in game.options())
    assert game._checked_prepared("act:socialize", prepared) is None
    with _no_model():
        game.choose("act:socialize", prepared=prepared)
    assert game.state.player.pending_companion is None
    assert game.state.player.fortune  # 走的是福緣那條路，不是對話


def _spy_battle_status(game):
    """記下每次 _battle_status 是用 tick=True 還是 tick=False 呼叫的。"""
    calls = []
    real = type(game)._battle_status

    def spy(self, tick=True):
        calls.append(tick)
        return real(self, tick=tick)

    return calls, mock.patch.object(type(game), "_battle_status", spy)


def test_options_passes_tick_through_to_the_battle_status(game):
    calls, patched = _spy_battle_status(game)
    with patched:
        game.options(odds=False, tick=False)
        assert calls == [False]
        game.options(odds=False)
        game.options()
    assert calls == [False, True, True]  # 預設還是 tick=True，其他呼叫端的行為不變


def test_dialogue_request_and_the_recheck_never_tick_the_battle(content, game):
    """一次請求只能推進一次戰鬥（推進可能結算一回合、呼叫 LLM 潤色，而且是握著鎖呼叫）：
    備料（階段 A）與進鎖後的重驗都只讀，推進交給 choose() 自己開頭那一次。"""
    _open_dialogue(content, game)
    prepared = _prepared(game, "talk:0")
    calls, patched = _spy_battle_status(game)
    with patched:
        game.dialogue_request("talk:0")
        game.dialogue_request("act:socialize")
        game._checked_prepared("talk:0", prepared)
    assert calls and True not in calls


def test_choosing_a_prepared_dialogue_option_ticks_the_battle_only_once(content, game):
    _open_dialogue(content, game)
    prepared = _prepared(game, "talk:0")
    calls, patched = _spy_battle_status(game)
    with patched, _no_model():
        game.choose("talk:0", prepared=prepared)
    assert calls.count(True) == 1


# ── 喊停（地圖擴充：停在下一站） ─────────────────────────────────────────


def test_you_can_stop_at_the_next_station(game):
    game.state.world.flags.add("cave_open")
    game.travel("cave", "walk")
    assert [o.id for o in game.options() if o.enabled] == ["act:halt"]
    assert "喊停（到湖邊就停下）" in [o.label for o in game.options()]
    game.choose("act:halt")
    assert game.state.player.journey.stop_at == 0
    assert not any(o.id == "act:halt" for o in game.options())  # 已經喊停了
    assert "已經喊停" in game.scene_text()
    game.advance(game.state.player.journey.arrive_at[0] - game.state.world.time)
    assert game.state.player.location == "lake" and game.state.player.journey is None
    assert game.state.journal[0].tag == "喊停，停在 湖邊"


def test_stopping_does_not_refund_the_stamina_paid_to_hurry(game):
    game.state.world.flags.add("cave_open")
    game.state.player.stamina = 100
    game.travel("cave", "hurry")  # 7.5 分鐘：8 點
    msgs = game.choose("act:halt")
    assert game.state.player.stamina == 92
    assert "（趕路已經花掉的體力不退。）" in msgs


def test_there_is_nothing_to_stop_on_the_last_leg(game):
    game.choose("move:lake")
    assert not any(o.id == "act:halt" for o in game.options())
