import random
from unittest import mock

from tianxia.world import (
    check_thresholds, current_act, current_storyline, end_season, evaluate_ending, sim_active, sim_tick,
    start_pending_battle,
)


def test_threshold_fires_once_and_sets_flag(state, content):
    state.world.trends["kou"] = 50
    msgs = check_thresholds(state, content)
    assert "blocked" in state.world.flags
    assert msgs == ["【江湖大事】水寇封江！"]
    assert state.world.rumors[-1].text == "水寇封江！"
    assert state.world.chronicle[-1].text == "水寇封江！"
    assert check_thresholds(state, content) == []


def _install_battle_def(content):
    from tianxia.models import BattleAct, BattleActionEffect, BattleDef, BattleFaction, BattleOption, BattleOutcome

    definition = BattleDef(
        id="b1", name="測試決戰", factions=[BattleFaction(id="a", name="甲方"), BattleFaction(id="b", name="乙方")],
        acts=[BattleAct(id="a1", title="開戰", text="開戰了。", goal="打贏", options=[BattleOption(text="進攻", tag="go")])],
        action_tags={"go": BattleActionEffect(trend_delta=1, neili_damage=5)},
        outcomes=[BattleOutcome(faction="a", title="甲方勝", text="甲方贏了。")],
    )
    content.battles[definition.id] = definition
    return definition


def test_threshold_with_starts_battle_opens_a_shared_battle(state, content, world):
    content.scenario.thresholds[0].starts_battle = "b1"
    _install_battle_def(content)
    state.world.trends["kou"] = 50
    msgs = check_thresholds(state, content, world, now=0.0)
    assert world.get_battle() is not None
    assert world.get_battle().battle_id == "b1"
    assert any("集結號角" in m for m in msgs)


def test_a_battle_threshold_during_a_battle_neither_starts_nor_announces_another(state, content, world):
    """管理者先開了戰，聲勢之後才自然跨過開戰門檻：不另開一場、也不再廣播集結（試玩回饋 FB-015）。"""
    content.scenario.thresholds[0].starts_battle = "b1"
    definition = _install_battle_def(content)
    world.start_battle(definition, now=0.0)
    before = world.get_battle()
    state.world.trends["kou"] = 50
    msgs = check_thresholds(state, content, world, now=100.0)
    assert msgs == ["【江湖大事】水寇封江！"]  # 門檻照樣觸發（旗標、傳聞），只是不開戰
    assert world.get_battle() == before


def test_a_pending_battle_is_not_started_during_a_battle_or_after_the_season_ended(content, world):
    definition = _install_battle_def(content)
    world.start_battle(definition, now=0.0)
    before = world.get_battle()
    world.mutate_season(lambda season: setattr(season, "pending_battle", definition.id))
    assert start_pending_battle(world, content, now=100.0) == []
    assert world.get_season().pending_battle is None and world.get_battle() == before  # 還是原來那一場
    world.clear_battle()
    world.mutate_season(lambda season: (setattr(season, "pending_battle", definition.id), setattr(season, "ended", True)))
    assert start_pending_battle(world, content, now=200.0) == []
    assert world.get_battle() is None and world.get_season().pending_battle is None


def test_threshold_with_starts_battle_but_no_matching_content_is_a_safe_no_op(state, content, world):
    content.scenario.thresholds[0].starts_battle = "does_not_exist"
    state.world.trends["kou"] = 50
    msgs = check_thresholds(state, content, world)
    assert world.get_battle() is None
    assert msgs == ["【江湖大事】水寇封江！"]


def test_threshold_with_starts_battle_does_nothing_without_a_world_store(state, content):
    content.scenario.thresholds[0].starts_battle = "b1"
    _install_battle_def(content)
    state.world.trends["kou"] = 50
    msgs = check_thresholds(state, content)  # 沒傳 world，跟既有呼叫端相容
    assert msgs == ["【江湖大事】水寇封江！"]


def test_threshold_without_world_or_client_stays_unflavored(state, content):
    """既有呼叫端（沒傳 world/client）行為完全不變：純文字，沒有潤色句。"""
    state.world.trends["kou"] = 50
    assert check_thresholds(state, content) == ["【江湖大事】水寇封江！"]


def test_threshold_flavor_is_computed_once_and_cached(state, content, world):
    client = mock.Mock()
    client.chat_text.return_value = "碼頭的船家議論紛紛。"
    state.world.trends["kou"] = 50
    msgs = check_thresholds(state, content, world, client)
    assert msgs == ["【江湖大事】水寇封江！\n\n碼頭的船家議論紛紛。"]
    assert client.chat_text.call_count == 1
    assert world.get_event_flavor("kou50") == "碼頭的船家議論紛紛。"


def test_threshold_flavor_reuses_a_cached_value_without_calling_the_llm_again(state, content, world):
    world.set_event_flavor("kou50", "已經有人潤色過的句子。")
    client = mock.Mock()
    state.world.trends["kou"] = 50
    msgs = check_thresholds(state, content, world, client)
    assert msgs == ["【江湖大事】水寇封江！\n\n已經有人潤色過的句子。"]
    client.chat_text.assert_not_called()


def test_threshold_skips_the_flourish_when_the_llm_call_fails(state, content, world):
    client = mock.Mock()
    client.chat_text.side_effect = RuntimeError("連不上")
    state.world.trends["kou"] = 50
    assert check_thresholds(state, content, world, client) == ["【江湖大事】水寇封江！"]


def test_ending_threshold_ends_season(state, content):
    state.world.trends["kou"] = 80
    msgs = check_thresholds(state, content)
    assert state.world.ended
    assert state.world.ending_title == "水寇稱霸"
    assert any("賽季落幕" in m for m in msgs)


def test_evaluate_ending_falls_back(state, content):
    assert evaluate_ending(state, content).id == "default"


def test_end_season_is_idempotent(state, content):
    assert end_season(state, content)
    assert end_season(state, content) == []


def test_end_season_without_world_skips_the_leaderboard(state, content):
    assert "【天下武學榜】" not in "\n".join(end_season(state, content))


def test_end_season_with_world_appends_the_leaderboard(state, content, world):
    msgs = end_season(state, content, world)
    assert "【天下武學榜】" in msgs and "【內功榜】" in msgs


def test_sim_players_push_trends_and_spread_rumors(state, content):
    msgs = sim_tick(state, content, 3, random.Random(0))
    assert state.world.trends["kou"] == 33
    assert msgs.count("【江湖傳聞】翻江龍又劫了一艘船。") == 3
    assert state.world.trends["bao"] == 0  # 鬼手要等寶藏線浮現


def test_sim_player_waits_for_revealed_trend(state, content):
    state.world.revealed.add("bao")
    sim_tick(state, content, 2, random.Random(0))
    assert state.world.trends["bao"] == 2


def test_sim_player_respects_condition(state, content):
    content.scenario.sim_players[0].condition.world_flags_none.append("blocked")
    state.world.flags.add("blocked")
    sim_tick(state, content, 3, random.Random(0))
    assert state.world.trends["kou"] == 30


def test_sim_active_is_the_rule_sim_tick_acts_by(state, content):
    boss, ghost = content.scenario.sim_players
    assert sim_active(boss, state) and not sim_active(ghost, state)  # 鬼手要等寶藏線浮現
    state.world.revealed.add("bao")
    assert sim_active(ghost, state)
    boss.condition.world_flags_none.append("blocked")
    state.world.flags.add("blocked")
    assert not sim_active(boss, state)  # 條件不成立
    before = dict(state.world.trends)
    sim_tick(state, content, 3, random.Random(0))
    assert state.world.trends["kou"] == before["kou"] and state.world.trends["bao"] == before["bao"] + 3  # 只有鬼手動


def test_threshold_records_flag_time(state, content):
    state.world.time = 5000
    state.world.trends["kou"] = 50
    check_thresholds(state, content)
    assert state.world.flag_times["blocked"] == 5000


def test_starts_on_main_storyline(state, content):
    assert current_storyline(state, content).id == "main"
    assert current_act(state, content).id == "a1"


def test_act_advances_when_condition_met(state, content):
    state.world.trends["kou"] = 60
    msgs = check_thresholds(state, content)
    assert state.world.act == 1
    assert any("第2幕" in m and "運河封鎖" in m for m in msgs)


def test_last_act_never_advances(state, content):
    state.world.act = 1
    state.world.trends["kou"] = 60
    check_thresholds(state, content)
    assert state.world.act == 1


def test_hidden_line_rewrites_storyline(state, content):
    state.world.act = 1
    state.world.revealed.add("bao")
    msgs = check_thresholds(state, content)
    assert (state.world.storyline, state.world.act) == ("treasure", 0)
    assert any("主線改寫" in m for m in msgs)
    assert "主線改寫" in state.world.rumors[-1].text


def test_world_event_fires_after_flag_age(state, content):
    state.world.revealed.add("bao")
    state.world.trends["bao"] = 100
    check_thresholds(state, content)  # bao100 → cave_open（時間 0）；主線改寫並推進到 t2
    assert current_act(state, content).id == "t2"
    assert "treasure_lost" not in state.world.flags
    state.world.time = 7200
    msgs = check_thresholds(state, content)
    assert "treasure_lost" in state.world.flags
    assert "【江湖大事】寶藏被搶走了！" in msgs


def test_endings_scoped_to_storyline(state, content):
    state.world.flags.add("treasure_lost")
    assert evaluate_ending(state, content).id == "default"
    state.world.storyline = "treasure"
    assert evaluate_ending(state, content).id == "lost"


def test_world_news_is_recorded_where_it_happens(state, content):
    state.world.trends["kou"] = 50
    check_thresholds(state, content)
    assert state.world.rumors[-1].location == "lake"  # kou50 的發生地
    assert state.world.chronicle[-1].location is None
    state.world.revealed.add("bao")
    check_thresholds(state, content)
    assert "主線改寫" in state.world.rumors[-1].text and state.world.rumors[-1].location is None


def test_world_event_is_recorded_where_it_happens(state, content):
    state.world.flags.add("cave_open")
    state.world.flag_times["cave_open"] = 0
    state.world.time = 2 * 3600
    check_thresholds(state, content)
    assert state.world.rumors[-1].text == "寶藏被搶走了！" and state.world.rumors[-1].location == "cave"


def test_sim_rumors_go_to_the_first_haunt(state, content):
    sim_tick(state, content, 1, random.Random(0))
    assert state.world.rumors[-1].text == "翻江龍又劫了一艘船。" and state.world.rumors[-1].location == "lake"
    content.scenario.sim_players[0].haunts = []
    sim_tick(state, content, 1, random.Random(0))
    assert state.world.rumors[-1].location is None


def test_a_sim_rumor_can_name_its_own_place(state, content):
    from tianxia.models import SimRumor

    content.scenario.sim_players[0].rumors = [SimRumor(text="{name}在寶洞外轉悠。", location="cave")]
    sim_tick(state, content, 1, random.Random(0))
    assert state.world.rumors[-1].text == "翻江龍在寶洞外轉悠。" and state.world.rumors[-1].location == "cave"


def test_haunts_leave_the_world_simulation_unchanged(state, content):
    other = state.model_copy(deep=True)
    rng_a, rng_b = random.Random(5), random.Random(5)
    sim_tick(state, content, 48, rng_a)
    for sim in content.scenario.sim_players:
        sim.haunts = []
    sim_tick(other, content, 48, rng_b)
    assert rng_a.getstate() == rng_b.getstate()  # 亂數用量一樣
    assert state.world.trends == other.world.trends
    assert [r.text for r in state.world.rumors] == [r.text for r in other.world.rumors]


def test_rumor_places_leave_the_world_simulation_unchanged(state, content):
    from tianxia.models import SimRumor

    other = state.model_copy(deep=True)
    content.scenario.sim_players[0].rumors = ["{name}又劫了一艘船。", "{name}在湖上放話。", "{name}又出手了。"]
    rng_a, rng_b = random.Random(5), random.Random(5)
    sim_tick(state, content, 48, rng_a)
    for sim in content.scenario.sim_players:
        sim.rumors = [SimRumor(text=text, location="cave") for text in sim.rumors]
    sim_tick(other, content, 48, rng_b)
    assert rng_a.getstate() == rng_b.getstate()  # 亂數用量一樣，挑中的傳聞也一樣
    assert state.world.trends == other.world.trends
    assert [r.text for r in state.world.rumors] == [r.text for r in other.world.rumors]
    assert {r.location for r in state.world.rumors if "翻江龍" in r.text} == {"lake"}  # 寫成字串：記在第一個常出沒處
    assert {r.location for r in other.world.rumors if "翻江龍" in r.text} == {"cave"}  # 寫成物件：記在它寫的地點


def test_a_threshold_rumor_is_world_news(state, content):
    state.world.trends["kou"] = 50
    check_thresholds(state, content)
    assert state.world.rumors[-1].layer == "world"


def test_the_season_ends_at_its_own_stamped_length(content):
    """季末照那一季蓋章的季長；換成 2.5 天的設定時，蓋 14 天章的那一季不會一口氣收掉。舊季沒有章就照設定。"""
    from tianxia.world import advance_world_state
    from tianxia.world_state import fresh_season

    content.scenario.sim_players = []  # 虛擬玩家推過門檻也會收季，這裡只看時間
    content.config.season_days = 14
    stamped = fresh_season(content)
    content.config.season_days = 2.5
    advance_world_state(stamped, content, 5 * 86400, random.Random(0))
    assert not stamped.ended
    advance_world_state(stamped, content, 9 * 86400, random.Random(0))
    assert stamped.ended
    old = fresh_season(content).model_copy(update={"length_days": None})  # T2 之前開的季：沒有章，一律照開季時的長度
    advance_world_state(old, content, 2.5 * 86400, random.Random(0))  # 換成 2.5 天的設定也不收（FB-037）
    assert not old.ended
    advance_world_state(old, content, 12 * 86400, random.Random(0))
    assert old.ended


def test_an_unstamped_season_keeps_the_length_it_opened_with(content):
    """FB-037：T2 之前開的季（length_days 是 None）都是用預設設定開的，所以一律是 Config.season_days 的預設值 14 天，
    不管現在載入的設定是多少（週末設定 2.5 天只管有蓋章的新季）；蓋了章的季照章。"""
    from tianxia.models import DEFAULT_SEASON_DAYS
    from tianxia.world_state import fresh_season, season_length_days

    assert DEFAULT_SEASON_DAYS == 14
    content.config.season_days = 2.5
    old = fresh_season(content).model_copy(update={"length_days": None})
    assert season_length_days(old, content) == 14
    assert season_length_days(fresh_season(content), content) == 2.5  # 蓋了章的照章
    content.config.season_days = 9
    assert season_length_days(old, content) == 14 and season_length_days(fresh_season(content), content) == 9


# ── 第一季不觸發的 beta 內容（計畫 T8；控制者 2026-10-04 的 season_one_off）────────────────


def _season_one(content, state, **off):
    """開關打開、這一季也蓋了「開」的章（rules.season_one 成立），再寫第一季不觸發的清單。"""
    from tianxia.models import SeasonOneOff

    content.config.season_one = True
    state.world.season_one = True
    content.scenario.season_one_off = SeasonOneOff(**off)


def test_beta_showdown_gone_only_when_switch_on(state, content, world):
    """開關打開時，beta 那場決戰的開戰門檻照樣觸發（旗標、傳聞），但不開戰、背景推進也不記待開；開關關著照舊開。"""
    from tianxia.state import GameState
    from tianxia.world_state import fresh_season

    content.scenario.thresholds[0].starts_battle = "b1"
    _install_battle_def(content)
    _season_one(content, state, battles=["b1"])
    state.world.trends["kou"] = 50
    assert check_thresholds(state, content, world, now=0.0) == ["【江湖大事】水寇封江！"]
    assert world.get_battle() is None
    background = GameState(player=state.player, world=fresh_season(content))  # 背景推進（沒有 store）：不記待開
    background.world.trends["kou"] = 50
    check_thresholds(background, content)
    assert background.world.pending_battle is None and "blocked" in background.world.flags
    world.mutate_season(lambda s: (setattr(s, "season_one", True), setattr(s, "pending_battle", "b1")))  # 開關打開前記下的
    assert start_pending_battle(world, content, now=0.0) == [] and world.get_battle() is None

    content.config.season_one = False  # 開關關著：beta 那場照舊
    state.world.fired_thresholds.clear()
    assert any("集結號角" in m for m in check_thresholds(state, content, world, now=0.0))
    assert world.get_battle().battle_id == "b1"


def test_season_one_off_thresholds_never_fire_even_by_the_admin(state, content):
    from tianxia.world import fire_by_id

    _season_one(content, state, thresholds=["kou50", "kou80"])
    state.world.trends["kou"] = 90
    check_thresholds(state, content)
    w = state.world
    assert not ({"kou50", "kou80"} & w.fired_thresholds) and not ({"blocked", "kou_win"} & w.flags) and not w.ended
    assert fire_by_id(state, content, "kou80") is None and not w.ended  # 管理者也觸發不了
    content.config.season_one = False  # 開關關著：照舊
    check_thresholds(state, content)
    assert {"blocked", "kou_win"} <= w.flags and w.ended


def test_season_one_off_storyline_does_not_advance(state, content):
    """清單裡的主線不推進；支線照舊可以取代它（其餘照舊）。開關關著照舊推進。"""
    from tianxia.world import update_storyline

    _season_one(content, state, storylines=["main"])
    state.world.trends["kou"] = 60
    assert update_storyline(state, content) == [] and state.world.act == 0
    content.config.season_one = False
    assert any("運河封鎖" in m for m in update_storyline(state, content)) and state.world.act == 1
    content.config.season_one = True
    state.world.act = 0
    state.world.revealed.add("bao")
    update_storyline(state, content)
    assert state.world.storyline == "treasure"
