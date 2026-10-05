import pytest

from tianxia.models import Check, Condition, Effect, FigureDef, FreeTextChoice
from tianxia.rules import (
    add_world_flags, apply_effect, audience_bar, can_meet, check_chance, check_condition, check_gap, check_outlook,
    current_day, free_text_rate, learn_skill, practice_line,
)


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


def test_every_check_uses_your_own_stat_even_with_a_stronger_companion(state, content, world):
    """企劃者 2026-10-05「探索應該沒有本人跟夥伴之分了」：隊伍檢定（by="team"）跟本人檢定完全一樣，只看本人。"""
    state.player.team.append("mate")  # 本人臂力 5、韓鐵 6
    team_check, self_check = Check(stat="str", difficulty=5), Check(stat="str", difficulty=5, by="self")
    assert team_check.by == "team"  # 舊內容照樣讀得進來，只是不再有作用
    assert check_chance(team_check, state, content, world) == check_chance(self_check, state, content, world) == 0.5
    assert check_gap(team_check, state, content, world) == check_gap(self_check, state, content, world) == 0


def test_a_companions_level_growth_does_not_help_a_check(state, content, world):
    state.player.team.append("mate")
    world.update_companion("mate", lambda p: setattr(p, "level", 5))  # 韓鐵身法 5 + 0.8
    assert check_chance(Check(stat="agi", difficulty=5), state, content, world) == 0.5


def test_your_own_allocated_points_count_and_level_alone_does_not(state, content, world):
    """計畫二 Task 1 起本人不再每級自動長屬性，只看存檔裡的數字（升級給的點自己配）。"""
    state.player.member.level = 2
    outlook = check_outlook(Check(stat="agi", difficulty=5), state, content, world)
    assert outlook.stat_value == pytest.approx(5.0)
    state.player.stats["agi"] = 6  # 配了一點身法
    outlook = check_outlook(Check(stat="agi", difficulty=5), state, content, world)
    assert outlook.stat_value == pytest.approx(6.0)
    assert outlook.chance == pytest.approx(0.6)


def test_practice_adds_one_point_per_ten_infamy_up_to_the_cap(state, content, world):
    check = Check(stat="agi", difficulty=5, by="self", practice="evil")
    for evil, chance in ((0, 0.5), (9, 0.5), (10, 0.6), (25, 0.7), (30, 0.8), (99, 0.8), (-20, 0.5)):
        state.player.stats["evil"] = evil
        assert check_chance(check, state, content, world) == pytest.approx(chance), evil


def test_without_practice_infamy_does_not_help(state, content, world):
    state.player.stats["evil"] = 30
    assert check_chance(Check(stat="agi", difficulty=5, by="self"), state, content, world) == 0.5


def test_practice_applies_to_you_on_a_team_check_too(state, content, world):
    """熟練加成照舊算在本人身上；隊伍裡有臂力更高的同伴也一樣是本人出手，同伴不吃本人的惡名。"""
    state.player.team.append("mate")  # 本人臂力 5、韓鐵 6
    state.player.stats["evil"] = 20  # 熟練 +2
    check = Check(stat="str", difficulty=5, practice="evil")
    outlook = check_outlook(check, state, content, world)
    assert (outlook.stat_value, outlook.bonus, outlook.gap) == (5, 2, 2)
    assert check_chance(check, state, content, world) == pytest.approx(0.7)
    state.player.stats["evil"] = 0
    assert check_chance(check, state, content, world) == pytest.approx(0.5)  # 沒有熟練：還是本人的 5，不換韓鐵


def test_practice_line_only_when_the_bonus_applies(state, content, world):
    check = Check(stat="agi", difficulty=5, by="self", practice="evil")
    state.player.stats["evil"] = 5
    assert practice_line(check, state, content, world) == ""
    state.player.stats["evil"] = 10
    assert practice_line(check, state, content, world) == "這種事你幹得多了。"
    assert practice_line(Check(stat="agi", difficulty=5, by="self"), state, content, world) == ""


def test_check_on_a_player_only_stat_uses_that_stat(state, content, world):
    state.player.stats["fame"] = 3
    assert check_chance(Check(stat="fame", difficulty=2), state, content, world) == pytest.approx(0.6)


def test_the_roll_reads_the_same_gap_the_label_reads(state, content, world):
    """擲骰的成功率與選項標籤挑心裡話的那一檔都出自 check_outlook 的同一個差值：50% ＋ 差值 × 10%，夾在 5%～95%。"""
    state.player.member.level = 3  # 帶小數的屬性：5.6
    for stat_value in range(0, 13):
        state.player.stats["str"] = stat_value
        for evil in (0, 10, 30):
            state.player.stats["evil"] = evil
            check = Check(stat="str", difficulty=6, practice="evil")
            gap = check_gap(check, state, content, world)
            assert gap == check_outlook(check, state, content, world).gap
            assert check_chance(check, state, content, world) == pytest.approx(min(0.95, max(0.05, 0.5 + gap * 0.1)))


def test_a_free_text_answer_uses_your_own_stat_too(state, content, world):
    """隨口應對的屬性修正也一樣只看本人（by 讀得進來、不再有作用）。"""
    gamble = FreeTextChoice(prompt="自己想辦法……", stat="str", by="team", effect=Effect(text="成了。"), fail_effect=Effect(text="砸了。"))
    alone = free_text_rate(50, gamble, state, content, world)
    state.player.team.append("mate")  # 韓鐵臂力 6
    assert free_text_rate(50, gamble, state, content, world) == alone == 50


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


def test_learn_skill_puts_a_second_art_in_the_library(state, content):
    """事件教的武學（追風步、混元一氣）：欄位已經有東西時不覆蓋、也不消失，進功法庫（武學與成長計畫 F2、設計附錄 B.1）。"""
    learn_skill(state, content, "fist")
    msgs = learn_skill(state, content, "sword")
    assert state.player.member.wugong_id == "fist"  # 原本那門先到，不被蓋掉
    assert state.player.arts == ["sword"]
    assert "流雲劍" in msgs[0] and "功法庫" in msgs[-1]
    assert learn_skill(state, content, "sword") == [] and state.player.arts == ["sword"]  # 已經有了就不再收一次


def test_skill_conditions_see_arts_in_the_library_too(state, content):
    """事件教的武學在欄位滿了時進功法庫（F2）：skills_none／skills_all 要看所有擁有的武學（身上＋功法庫），
    不然「還沒學過才出現」的付費課程，學完收進功法庫之後還會一直回來、再收一次錢（最終審查 Important 1）。"""
    learn_skill(state, content, "fist")
    learn_skill(state, content, "sword")
    assert state.player.arts == ["sword"]  # 在功法庫，不在身上
    assert not check_condition(Condition(skills_none=["sword"]), state)
    assert check_condition(Condition(skills_all=["sword", "fist"]), state)


def test_learn_skill_ignores_the_holding_cap(state, content):
    """付了錢、或是奇遇給的，不能因為滿了就憑空消失（跟悟意境一樣不受上限擋）。"""
    content.config.holding_cap_base = 1
    learn_skill(state, content, "fist")
    learn_skill(state, content, "sword")
    assert state.player.arts == ["sword"]


def test_an_effect_can_grant_an_insight(state, content, world):
    msgs = apply_effect(Effect(insights=["feng"]), state, content, world)
    assert state.player.insights == ["feng"] and any("悟得" in m for m in msgs)


def test_an_effect_that_grants_a_known_insight_again_gives_xinde(state, content, world):
    state.player.insights = ["feng"]
    state.player.stats["xinde"] = 0
    msgs = apply_effect(Effect(insights=["feng"]), state, content, world)
    assert state.player.insights == ["feng"] and state.player.stats["xinde"] == 10 and "心得 +10" in msgs


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


# ── 求見的門檻（武學與成長設計 9.1）：名望為主，同陣營的階級每階抵 audience_rank_discount ──


def _figure_for(content, character_id, faction="guan"):
    content.figures["f_test"] = FigureDef(
        id="f_test", character=character_id, name=content.characters[character_id].name,
        faction=faction, location=content.scenario.start_location, squad=next(iter(content.squads)),
    )


def test_each_promotion_in_the_figures_own_faction_lowers_the_bar(state, content):
    """每升一階抵 audience_rank_discount（設計 9.1）；存檔裡的階 0 是投靠了還沒晉升過、第一次晉升後是 2（PlayerState.rank）。"""
    cid = "mate"
    content.characters[cid].audience_fame = 20
    _figure_for(content, cid, "guan")
    state.player.stats["fame"] = 10
    assert audience_bar(state, content, cid) == 20 and not can_meet(state, content, cid)
    state.player.faction, state.player.rank = "guan", 2  # 晉升過一次：抵 5
    assert audience_bar(state, content, cid) == 15 and not can_meet(state, content, cid)
    state.player.rank = 3  # 兩次：抵 10，剛好到也算
    assert audience_bar(state, content, cid) == 10 and can_meet(state, content, cid)


def test_joining_the_figures_faction_without_a_promotion_takes_nothing_off(state, content):
    cid = "mate"
    content.characters[cid].audience_fame = 20
    _figure_for(content, cid, "guan")
    state.player.faction = "guan"
    for stored in (0, 1):  # 存檔裡的 0 是投靠了還沒晉升過（rank_of 算第 1 階）；階 1 同樣是還沒升
        state.player.rank = stored
        assert audience_bar(state, content, cid) == 20


def test_rank_in_another_faction_does_not_count(state, content):
    cid = "mate"
    content.characters[cid].audience_fame = 20
    _figure_for(content, cid, "guan")
    state.player.faction, state.player.rank = "huang", 3
    assert audience_bar(state, content, cid) == 20


def test_a_loner_and_a_figure_without_a_faction_entry_only_count_fame(state, content):
    cid = "mate"
    content.characters[cid].audience_fame = 20
    state.player.rank = 3  # 散人的階級不抵（沒有陣營）
    assert audience_bar(state, content, cid) == 20  # 這個人物也不在大勢人物表上
    _figure_for(content, cid, "guan")
    assert audience_bar(state, content, cid) == 20


def test_the_bar_never_drops_below_zero_and_the_discount_is_configurable(state, content):
    cid = "mate"
    content.characters[cid].audience_fame = 8
    _figure_for(content, cid, "guan")
    state.player.faction, state.player.rank = "guan", 4
    assert audience_bar(state, content, cid) == 0  # 8 - 3×5 夾到 0
    content.config.audience_rank_discount = 1
    assert audience_bar(state, content, cid) == 5  # 8 - 3×1


def test_a_prior_meeting_still_opens_the_door_whatever_the_bar(state, content):
    cid = "mate"
    content.characters[cid].audience_fame = 99
    assert not can_meet(state, content, cid)
    state.player.flags.add(f"結識:{cid}")
    assert can_meet(state, content, cid)


# ── 四屬性每項最高 stat_cap（武學與成長設計 6.2）──────────────────────────────


def test_an_event_cannot_push_a_stat_past_the_cap(state, content, world):
    state.player.stats["str"] = 14
    msgs = apply_effect(Effect(stats={"str": 3}), state, content, world)
    assert state.player.stats["str"] == 15
    assert "臂力 +1" in msgs  # 照實際加了多少寫
    assert "（臂力已到頂 15）" in msgs  # 被上限夾掉了，玩家要知道是到頂


def test_an_event_at_the_cap_writes_no_plus_line_and_one_cap_line(state, content, world):
    state.player.stats["str"] = 15
    msgs = apply_effect(Effect(stats={"str": 1}), state, content, world)
    assert state.player.stats["str"] == 15
    assert not any(m.startswith("臂力 ") for m in msgs)  # 沒動就不寫「臂力 +0」（江湖紀錄也會丟掉零）
    assert msgs.count("（臂力已到頂 15）") == 1


def test_a_stat_that_reaches_the_cap_exactly_says_nothing_about_it(state, content, world):
    state.player.stats["wis"] = 14
    msgs = apply_effect(Effect(stats={"wis": 1}), state, content, world)
    assert state.player.stats["wis"] == 15 and "悟性 +1" in msgs
    assert not any("到頂" in m for m in msgs)  # 沒有被夾掉，不提


def test_a_stat_below_the_cap_is_written_in_full(state, content, world):
    msgs = apply_effect(Effect(stats={"con": 2}), state, content, world)
    assert state.player.stats["con"] == 7 and msgs == ["根骨 +2"]


def test_only_the_four_combat_stats_have_a_cap(state, content, world):
    """銀兩、善名這些沒有上限（stat_cap 只管臂力、身法、根骨、悟性）。"""
    state.player.stats["silver"] = 500
    msgs = apply_effect(Effect(stats={"silver": 40}), state, content, world)
    assert state.player.stats["silver"] == 540 and msgs == ["銀兩 +40"]


def test_a_floor_clamp_writes_what_really_moved_and_nothing_when_nothing_did(state, content, world):
    """下限（不低於 0）夾住時也照實際動了多少寫，一點都沒動就不寫（不會冒出「惡名 +0」）。"""
    state.player.stats["evil"] = 1
    assert apply_effect(Effect(stats={"evil": -3}), state, content, world) == ["惡名 -1"]
    assert state.player.stats["evil"] == 0
    assert apply_effect(Effect(stats={"evil": -3}), state, content, world) == []
