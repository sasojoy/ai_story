import pytest

from tianxia.models import Check, Condition, Effect
from tianxia.rules import (
    add_world_flags, apply_effect, check_chance, check_condition, check_who, current_day, learn_skill,
)
from tianxia.team import check_actor


def test_new_state(state):
    assert state.player.location == "town"
    assert state.player.stamina == 150
    assert state.world.trends == {"kou": 30, "bao": 0}
    assert state.world.revealed == {"kou"}
    assert state.player.team == []  # 同伴全服唯一，開局不再自動塞給玩家任何一位


def test_empty_condition_passes(state):
    assert check_condition(Condition(), state)


def test_condition_stats_and_flags(state):
    state.player.flags.add("token")
    assert check_condition(Condition(min_stats={"str": 5}, flags_all=["token"]), state)
    assert not check_condition(Condition(min_stats={"str": 6}), state)
    assert not check_condition(Condition(flags_none=["token"]), state)


def test_condition_sect_and_skills(state):
    assert check_condition(Condition(no_sect=True), state)
    assert not check_condition(Condition(sects=["cloud"]), state)
    state.player.sect = "cloud"
    assert check_condition(Condition(sects=["cloud"]), state)
    assert not check_condition(Condition(no_sect=True), state)
    assert check_condition(Condition(skills_none=["fist"]), state)


def test_condition_world(state):
    assert check_condition(Condition(trend_min={"kou": 30}, trend_max={"kou": 30}), state)
    assert not check_condition(Condition(trend_min={"kou": 31}), state)
    state.world.flags.add("blocked")
    assert check_condition(Condition(world_flags_all=["blocked"]), state)
    assert not check_condition(Condition(world_flags_none=["blocked"]), state)


def test_condition_members_none(state):
    assert check_condition(Condition(members_none=["hero", "sage", "mate"]), state)
    state.player.team.append("mate")
    assert not check_condition(Condition(members_none=["hero", "mate"]), state)


def test_check_chance_scales_and_clamps(state, content, world):
    assert check_chance(Check(stat="str", difficulty=5, by="self"), state, content, world) == 0.5
    assert check_chance(Check(stat="str", difficulty=7, by="self"), state, content, world) == pytest.approx(0.3)
    assert check_chance(Check(stat="str", difficulty=50, by="self"), state, content, world) == 0.05
    assert check_chance(Check(stat="str", difficulty=-50, by="self"), state, content, world) == 0.95


def test_team_check_sends_the_member_with_the_highest_stat(state, content, world):
    state.player.team.append("mate")  # 本人臂力 5、韓鐵 6
    check = Check(stat="str", difficulty=5)
    assert check_actor(state, content, world, check) == "mate"
    assert check_chance(check, state, content, world) == pytest.approx(0.6)  # 用出手者的屬性算
    assert check_who(check, state, content, world) == "韓鐵出手"


def test_team_check_tie_goes_to_the_player_first(state, content, world):
    state.player.team.append("mate")
    check = Check(stat="agi", difficulty=5)  # 身法同為 5
    assert check_actor(state, content, world, check) == "player"
    assert check_who(check, state, content, world) == "本人出手"


def test_team_check_counts_level_growth(state, content, world):
    state.player.team.append("mate")
    check = Check(stat="agi", difficulty=5)
    world.update_companion("mate", lambda p: setattr(p, "level", 2))  # 韓鐵身法 5 + 0.2
    assert check_actor(state, content, world, check) == "mate"
    assert check_chance(check, state, content, world) == pytest.approx(0.52)


def test_self_check_is_always_the_player(state, content, world):
    state.player.team.append("mate")  # 韓鐵根骨 6 比本人高，也輪不到他
    check = Check(stat="con", difficulty=5, by="self")
    assert check_actor(state, content, world, check) == "player"
    assert check_chance(check, state, content, world) == 0.5
    assert check_who(check, state, content, world) == "本人"


def test_check_on_a_player_only_stat_is_made_by_the_player(state, content, world):
    state.player.stats["fame"] = 3
    check = Check(stat="fame", difficulty=2)
    assert check_actor(state, content, world, check) == "player"
    assert check_chance(check, state, content, world) == pytest.approx(0.6)


def test_apply_stats_clamps_at_zero(state, content, world):
    msgs = apply_effect(Effect(text="你撿到錢。", stats={"silver": 10, "evil": -3}), state, content, world)
    assert state.player.stats["silver"] == 60
    assert state.player.stats["evil"] == 0
    assert msgs[0] == "你撿到錢。"
    assert "銀兩 +10" in msgs


def test_apply_stamina_clamps(state, content, world):
    apply_effect(Effect(stamina=50), state, content, world)
    assert state.player.stamina == 150
    apply_effect(Effect(stamina=-500), state, content, world)
    assert state.player.stamina == 0


def test_hidden_trend_revealed_by_positive_push(state, content, world):
    msgs = apply_effect(Effect(trend={"bao": 20}), state, content, world)
    assert "bao" in state.world.revealed
    assert state.world.trends["bao"] == 20
    assert any("寶藏" in m for m in msgs)


def test_hidden_trend_ignores_negative_push(state, content, world):
    apply_effect(Effect(trend={"bao": -5}), state, content, world)
    assert "bao" not in state.world.revealed
    assert state.world.trends["bao"] == 0


def test_trend_clamped(state, content, world):
    apply_effect(Effect(trend={"kou": 500}), state, content, world)
    assert state.world.trends["kou"] == 100
    apply_effect(Effect(trend={"kou": -500}), state, content, world)
    assert state.world.trends["kou"] == 0


def test_rumor_respects_anonymity(state, content, world):
    apply_effect(Effect(rumor="{name}撿到了殘卷！", chronicle="{name}發現殘卷。"), state, content, world)
    state.player.anonymous = True
    apply_effect(Effect(rumor="{name}又出手了！"), state, content, world)
    assert [r.text for r in state.world.rumors] == ["沈浪撿到了殘卷！", "某位少俠又出手了！"]
    assert state.world.chronicle[0].text == "沈浪發現殘卷。"


def test_join_sect_sets_the_sect_but_no_longer_teaches_skills(state, content, world):
    """門派不再教武學（設計文件六.4：每人最多一門內功一門武學，取名自創或情誼換本命，
    不再有「拜師自動送武學」這條路），只設定 sect 本身。"""
    msgs = apply_effect(Effect(join_sect="cloud"), state, content, world)
    assert state.player.sect == "cloud"
    assert state.player.member.wugong_id is None
    assert any("流雲派" in m for m in msgs)


def test_leave_sect_sets_flag(state, content, world):
    state.player.sect = "cloud"
    apply_effect(Effect(leave_sect=True), state, content, world)
    assert state.player.sect is None
    assert "叛出:cloud" in state.player.flags


def test_learn_skill_starts_at_first_level(state, content):
    msgs = learn_skill(state, content, "fist")
    assert state.player.member.wugong_id == "fist" and state.player.member.wugong_level == 1
    assert "長拳" in msgs[0]
    assert learn_skill(state, content, "fist") == []


def test_learn_skill_does_not_overwrite_an_existing_wugong(state, content):
    learn_skill(state, content, "fist")
    msgs = learn_skill(state, content, "sword")
    assert state.player.member.wugong_id == "fist"  # 原本那門先到，後來的沒學成
    assert "先無緣習得" in msgs[0]


def test_current_day(state):
    assert current_day(state) == 1
    state.world.time = 86400 * 2 + 5
    assert current_day(state) == 3


def test_condition_day_range(state):
    state.world.time = 86400 * 4  # 第 5 天
    assert check_condition(Condition(day_min=5), state)
    assert not check_condition(Condition(day_min=6), state)
    assert not check_condition(Condition(day_max=4), state)


def test_condition_revealed(state):
    assert check_condition(Condition(revealed_all=["kou"], revealed_none=["bao"]), state)
    state.world.revealed.add("bao")
    assert not check_condition(Condition(revealed_none=["bao"]), state)


def test_condition_any_of(state):
    assert check_condition(Condition(any_of=[Condition(min_stats={"str": 99}), Condition(day_min=1)]), state)
    assert not check_condition(Condition(any_of=[Condition(min_stats={"str": 99})]), state)


def test_world_flag_age(state):
    add_world_flags(state, ["cave_open"])
    cond = Condition(flag_age_hours={"cave_open": 2})
    assert not check_condition(cond, state)
    state.world.time = 7200
    assert check_condition(cond, state)
    add_world_flags(state, ["cave_open"])  # 已存在：不重設時間
    assert state.world.flag_times["cave_open"] == 0


def test_effect_world_flags_record_time(state, content, world):
    state.world.time = 3600
    apply_effect(Effect(world_flags_add=["x"]), state, content, world)
    assert "x" in state.world.flags
    assert state.world.flag_times["x"] == 3600


def test_rumor_is_recorded_where_the_player_stands(state, content, world):
    state.player.location = "lake"
    apply_effect(Effect(rumor="{name}撿到了殘卷！", chronicle="{name}發現殘卷。"), state, content, world)
    assert state.world.rumors[-1].location == "lake"
    assert state.world.chronicle[-1].location is None  # 江湖史不記地點


# ── 傳國玉璽碎片（跨季，還要改進第 2 點）─────────────────────────


def test_newly_set_jade_seal_flag_records_a_fragment(state, content, world):
    content.scenario.jade_seal_flag = "shard_taken"
    apply_effect(Effect(world_flags_add=["shard_taken"], chronicle="{name}取得玉璽碎片。"), state, content, world)
    fragments = world.get_jade_seal_fragments()
    assert len(fragments) == 1
    assert fragments[0].finder == state.player.name
    assert fragments[0].season_name == content.scenario.name
    assert fragments[0].text == f"{state.player.name}取得玉璽碎片。"


def test_jade_seal_flag_already_set_does_not_record_again(state, content, world):
    content.scenario.jade_seal_flag = "shard_taken"
    apply_effect(Effect(world_flags_add=["shard_taken"]), state, content, world)
    apply_effect(Effect(world_flags_add=["shard_taken"]), state, content, world)  # 已經有這個旗標：不重複記錄
    assert len(world.get_jade_seal_fragments()) == 1


def test_unrelated_flags_do_not_record_a_fragment(state, content, world):
    content.scenario.jade_seal_flag = "shard_taken"
    apply_effect(Effect(world_flags_add=["some_other_flag"]), state, content, world)
    assert world.get_jade_seal_fragments() == []


def test_without_a_jade_seal_flag_configured_nothing_is_recorded(state, content, world):
    assert content.scenario.jade_seal_flag is None
    apply_effect(Effect(world_flags_add=["shard_taken"]), state, content, world)
    assert world.get_jade_seal_fragments() == []


def test_fragment_falls_back_to_a_generic_text_without_a_chronicle(state, content, world):
    content.scenario.jade_seal_flag = "shard_taken"
    apply_effect(Effect(world_flags_add=["shard_taken"]), state, content, world)
    assert "取得了傳國玉璽的一塊碎片" in world.get_jade_seal_fragments()[0].text


def test_joining_a_sect_also_joins_the_faction_that_owns_it(state, content, world):
    from tianxia.models import FactionDef

    content.scenario.factions = [FactionDef(id="guan", name="官軍", sects=["cloud"])]
    msgs = apply_effect(Effect(join_sect="cloud"), state, content, world)
    assert state.player.faction == "guan"
    assert any("官軍" in m for m in msgs)


def test_joining_a_sect_keeps_an_existing_faction(state, content, world):
    from tianxia.models import FactionDef

    content.scenario.factions = [FactionDef(id="guan", name="官軍", sects=["cloud"])]
    state.player.faction = "huang"
    apply_effect(Effect(join_sect="cloud"), state, content, world)
    assert state.player.faction == "huang"


def test_effect_materials_land_in_the_bag(state, content, world):
    msgs = apply_effect(Effect(materials={"gang_1": 2}), state, content, world)
    assert "獲得 精鐵砂 ×2" in msgs
    assert state.player.materials == {"gang_1": 2}


def test_effect_with_an_unknown_material_says_nothing(state, content, world):
    msgs = apply_effect(Effect(materials={"ghost": 1}), state, content, world)
    assert msgs == []
    assert state.player.materials == {}


def test_an_event_rumor_is_local_news_of_its_region(state, content, world):
    """傳聞分層設計第二、七節：事件的傳聞是地方傳聞，記下所在大區；觸發者匿名時記成不具名。"""
    from tianxia import atlas

    state.player.anonymous = True
    apply_effect(Effect(rumor="{name}在此留名"), state, content, world)
    rumor = state.world.rumors[-1]
    region = atlas.region_of(content, state.player.location)
    assert rumor.layer == "local" and rumor.location == state.player.location
    assert rumor.region == (region.id if region else None)
    assert rumor.named is False and "某位少俠" in rumor.text
