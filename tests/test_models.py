import pytest
from pydantic import ValidationError

from tianxia.models import (
    BEATS, EXPLORE_BRANCHES, MOVES, BattleAct, BattleDef, BattleFaction, BattleOption, BattleOutcome, BattleTuning,
    Choice, Config, Connection, Event, InsightDef, InsightGrant, LearnRule, Location, SkillDef,
)

# 戰鬥系統設計 3.4 的對應表（擅長, 不擅長）：預設值要跟它一個字一個字對得上
SPEC_AFFINITY = {
    "剛": ("強攻", "奇襲"), "實": ("強攻", "奇襲"), "陽": ("強攻", "固守"), "柔": ("固守", "強攻"),
    "陰": ("固守", "強攻"), "慢": ("固守", "奇襲"), "快": ("奇襲", "固守"), "虛": ("奇襲", "強攻"),
}


def test_event_requires_at_least_one_choice():
    with pytest.raises(ValidationError):
        Event(id="e", title="t", text="x", choices=[])


def test_event_defaults():
    ev = Event(id="e", title="t", text="x", choices=[Choice(text="走")])
    assert ev.actions == ["explore"]
    assert ev.weight == 1.0 and not ev.once and not ev.qiyu
    assert ev.choices[0].effect.stats == {}


def test_location_danger_range():
    with pytest.raises(ValidationError):
        Location(id="a", name="A", description="d", connections=[], danger=4)


def test_config_defaults():
    cfg = Config()
    assert cfg.stamina_max == 150
    assert cfg.action_cost == {"explore": 10, "train": 10, "socialize": 5}
    assert cfg.stat_names["str"] == "臂力"


def test_travel_config_defaults():
    cfg = Config()
    assert cfg.stamina_regen_seconds == 180 and cfg.rest_regen_multiplier == 2
    assert cfg.road_factor == {"官道": 0.8, "路": 1.0, "山路": 1.5}
    assert (cfg.hurry_stamina_per_minute, cfg.dash_stamina_per_minute) == (1, 2)
    assert cfg.travel_minutes_per_unit > 0


# ── 探索三選一的設定（探索三選一設計第三節）──────────────────


def test_explore_mix_defaults_follow_the_design_table():
    cfg = Config()
    table = [(m.kind, m.tags, m.weights) for m in cfg.explore_mix]
    assert table == [
        ("camp", ["營寨", "祭壇", "塢堡"], {"insight": 15, "wild": 35, "event": 50}),
        ("town", ["城鎮", "官署", "城池", "寺院", "書院", "莊院", "里巷", "結社"], {"insight": 15, "wild": 0, "event": 85}),
        ("wild", [], {"insight": 40, "wild": 35, "event": 25}),
    ]
    assert cfg.wild_neili_loss_factor == 0.5
    assert 0 < cfg.rare_explore_chance < 1
    assert not hasattr(cfg, "explore_material_chance")  # 探索前固定滾三成素材已經拿掉，探索三選一的第一支改成悟意境（探索不再撿素材）
    assert EXPLORE_BRANCHES == ("insight", "wild", "event")  # 悟意境、野怪、事件


def test_a_place_takes_the_first_kind_whose_tags_it_has():
    cfg = Config()
    assert cfg.explore_mix_of(["城池", "營寨"]).kind == "camp"  # 廣宗：營寨優先於城鎮
    assert cfg.explore_mix_of(["寺院"]).kind == "town"
    assert cfg.explore_mix_of(["官道", "野外"]).kind == "wild"
    assert cfg.explore_mix_of([]).kind == "wild"  # 沒有標籤也算「其餘」


def _mix(kind, tags, **weights):
    return {"kind": kind, "tags": tags, "weights": weights}


@pytest.mark.parametrize("mix", [
    [_mix("wild", [], insight=-1, wild=35, event=25)],  # 權重不能是負的
    [_mix("wild", [], insight=0, wild=0, event=0)],  # 三支總和要大於 0
    [_mix("town", ["城鎮"], insight=15, event=85)],  # 最後一筆必須是 tags 空的「其餘」
    [_mix("wild", [], insight=40), _mix("town", ["城鎮"], event=85)],  # tags 空的只能放最後
    [],  # 一筆都沒有
    [_mix("wild", [], insight=40, loot=10)],  # 只有悟意境、野怪、事件三支
])
def test_explore_mix_rejects_a_broken_table(mix):
    with pytest.raises(ValidationError):
        Config(explore_mix=mix)


@pytest.mark.parametrize("field, value", [
    ("rare_explore_chance", -0.1), ("rare_explore_chance", 1.5),
    ("wild_neili_loss_factor", -0.5), ("wild_neili_loss_factor", 1.5),
    ("explore_legend_chance", -0.1), ("explore_legend_chance", 1.5),
])
def test_explore_chances_must_be_fractions(field, value):
    with pytest.raises(ValidationError):
        Config(**{field: value})


def test_a_connection_is_its_destination_id_with_a_road_kind():
    loc = Location(id="a", name="A", description="d", connections=["b", {"to": "c", "road": "官道"}], x=0, y=0)
    assert loc.connections == ["b", "c"] and f"move:{loc.connections[1]}" == "move:c"
    assert (loc.connections[1].to, loc.connections[1].road) == ("c", "官道")
    assert type(loc.connections[1].to) is str
    assert loc.model_dump()["connections"] == ["b", {"to": "c", "road": "官道"}]  # 寫回去跟內容檔同一個樣子
    assert Location.model_validate(loc.model_dump()).connections[1].road == "官道"
    assert loc.model_copy(deep=True).connections[1].road == "官道"
    assert Connection("x") == "x" and Connection("x").road == "路"
    loc.connections.append("d")  # 程式或測試直接塞進清單的一般字串，寫回去也要行
    assert loc.model_dump()["connections"][-1] == "d"


# ── 武學與成長（武學與成長設計第四節的預設數字、附錄 A～B 的欄位）──────────────


def test_growth_config_defaults_follow_the_design():
    cfg = Config()
    assert (cfg.fuse_xinde, cfg.merge_xinde, cfg.cultivate_stamina, cfg.practice_xinde_per_level) == (5, 5, 10, 1)
    assert cfg.merge_stamina == 5  # 企劃者 2026-10-05：合併要花體力，合成不花；FB-067 從 10（跟修練一次一樣）降到 5
    # 企劃者 2026-10-06（W8）：下品→中品放寬成 40% 起、每失敗一次 +20%、第三次必成；中品→上品、上品→絕學照舊
    assert cfg.cultivate_odds == {"中品": (40, 20), "上品": (10, 6), "絕學": (4, 3)}
    assert cfg.cultivate_sure_by == {"中品": 3}  # 只有中品寫明第幾次必成；上品靠加到 100%，絕學沒有保底
    assert cfg.melt_refund_ratio == 0.8
    assert cfg.melt_quality_bonus == {"下品": 0, "中品": 5, "上品": 15, "絕學": 40}
    assert (cfg.melt_insight_xinde, cfg.duplicate_insight_xinde) == (10, 10)
    assert (cfg.holding_cap_base, cfg.holding_cap_levels, cfg.holding_cap_step) == (50, 5, 3)  # 企劃者 2026-10-05 從 5 改成 3
    assert cfg.holding_per_lore_point == 2  # 博聞比基準每多一點多 2 格（設計 6.3）


def test_a_peerless_art_has_no_sure_thing_and_the_legend_item_is_a_small_help():
    """企劃者 2026-10-05：絕學沒有保底（機會最多 50%），探索偶爾拿到的破境丹替那一次多加 15%。"""
    cfg = Config()
    assert cfg.cultivate_cap == {"絕學": 50}
    assert (cfg.legend_item_name, cfg.legend_item_bonus, cfg.explore_legend_chance) == ("破境丹", 15, 0.02)
    assert "絕學" in cfg.legend_item_note and "可以服下" in cfg.legend_item_note and "自動" not in cfg.legend_item_note


@pytest.mark.parametrize("ratio", [-0.1, 1.1])
def test_the_melt_refund_must_be_a_fraction(ratio):
    with pytest.raises(ValidationError):
        Config(melt_refund_ratio=ratio)


def test_a_skill_is_a_historical_art_unless_it_says_otherwise():
    art = SkillDef(id="a", name="甲", kind="武學", attribute="剛")
    assert art.quality == "絕學" and art.learn is None
    basic = SkillDef(
        id="b", name="乙", kind="武學", attribute="快", quality="下品", learn={"at": "lake", "fame": 5, "silver": 20},
    )
    assert basic.learn == LearnRule(at="lake", fame=5, silver=20)
    assert basic.learn.faction is None and basic.learn.sect is None
    with pytest.raises(ValidationError):
        SkillDef(id="c", name="丙", kind="武學", attribute="快", quality="神品")


def test_an_insight_may_be_earned_by_name():
    plain = InsightDef(id="feng", name="風", attribute="快")
    assert plain.lean == "無" and plain.grant is None
    earned = InsightDef(id="haoran", name="浩然", attribute="陽", lean="正", grant={"stat": "good", "at": 15})
    assert earned.grant == InsightGrant(stat="good", at=15)
    with pytest.raises(ValidationError):
        InsightDef(id="x", name="x", attribute="快", grant={"stat": "fame", "at": 15})
    with pytest.raises(ValidationError):
        InsightDef(id="x", name="x", attribute="快", lean="善")


def test_a_location_starts_with_no_insights():
    assert Location(id="a", name="A", description="d", connections=[], x=0, y=0).insights == []


# ── 全服決戰的三招與推力（決戰改版 1，戰鬥系統設計 3.4）──────────────────


def test_battle_tuning_defaults_are_the_designs():
    """戰鬥系統設計 3.4【預設】。"""
    t = Config().battle
    assert (t.power_base, t.power_per, t.power_cap) == (40.0, 0.4, 150.0)
    assert (t.affinity_base, t.affinity_outer, t.affinity_inner) == (75.0, 15.0, 10.0)
    assert (t.counter, t.push_max) == (0.5, 10.0)
    assert t.damage == {"強攻": 60.0, "奇襲": 35.0, "固守": 15.0} and t.strong_mitigation_cap == 0.6
    assert t.affinity["剛"] == ("強攻", "奇襲") and t.affinity["快"] == ("奇襲", "固守")
    assert set(t.affinity) == {"剛", "實", "陽", "柔", "陰", "慢", "快", "虛"}


def test_each_move_beats_exactly_one_other():
    assert BEATS == {"固守": "強攻", "強攻": "奇襲", "奇襲": "固守"}
    assert sorted(BEATS) == sorted(MOVES) == sorted(BEATS.values())


def test_every_affinity_names_two_different_moves():
    """每個屬性擅長一招、不擅長另一招，不會同一招又擅長又不擅長。"""
    for attribute, (good, bad) in Config().battle.affinity.items():
        assert good in MOVES and bad in MOVES and good != bad, attribute


def test_the_default_affinity_table_is_the_designs_row_by_row():
    """八個屬性一列一列對設計 3.4 的表（不只剛與快：陽、陰、慢、虛一個也不能被改反）。"""
    assert Config().battle.affinity == SPEC_AFFINITY


@pytest.mark.parametrize("override", [
    {"damage": {"強攻": 70.0}},  # 少寫兩招：結算時 tuning.damage[move] 會 KeyError
    {"damage": {"強攻": 60.0, "固守": 15.0}},
    {"damage": {"強攻": 60.0, "固守": 15.0, "奇襲": 35.0, "亂招": 5.0}},  # 多一招
    {"damage": {"強攻": 60.0, "固守": 0.0, "奇襲": 35.0}},  # 零與負的損耗
    {"damage": {"強攻": 60.0, "固守": 15.0, "奇襲": -35.0}},
    {"affinity": {"剛": ("強攻", "強攻")}},  # 擅長與不擅長同一招
    {"affinity": {"剛": ("強攻", "亂招")}},
    {"power_base": 0}, {"power_base": -1}, {"power_per": 0}, {"power_per": -0.4}, {"power_cap": 0}, {"power_cap": -150},
    {"affinity_base": 0}, {"affinity_outer": -15}, {"affinity_inner": -10}, {"push_max": 0}, {"push_max": -5},
    {"counter": -0.5}, {"counter": 3.0}, {"strong_mitigation_cap": -0.1}, {"strong_mitigation_cap": 1.5},
])
def test_a_tuning_that_would_break_the_resolution_is_rejected_when_it_loads(override):
    """企劃者測完要調數字：寫壞的值在載入設定時就被擋下，不是等第一場決戰的第一回合才在行動鎖裡丟 KeyError、把整場卡住。"""
    with pytest.raises(ValidationError):
        BattleTuning(**override)
    with pytest.raises(ValidationError):
        Config(battle=override)  # 從 config.json 的 "battle" 讀進來走的是這一條


@pytest.mark.parametrize("override", [
    {"damage": {"強攻": 70.0, "固守": 10.0, "奇襲": 40.0}},
    {"counter": 0.0}, {"counter": 1.0}, {"affinity_outer": 0.0}, {"affinity_inner": 0.0}, {"strong_mitigation_cap": 0.0},
    {"push_max": 20},
])
def test_a_sensible_tuning_override_is_accepted(override):
    tuning = Config(battle=override).battle
    for name, value in override.items():
        assert getattr(tuning, name) == value


def test_a_fixed_option_may_name_its_move_and_a_gamble_does_not():
    assert BattleOption(text="強攻", tag="x", move="強攻").move == "強攻"
    assert BattleOption(text="放手一搏", tag="x", free_text=True).move is None
    with pytest.raises(ValidationError):
        BattleOption(text="亂招", tag="x", move="亂來")


def test_an_act_has_no_lead_texts_unless_it_writes_them():
    act = BattleAct(id="a", title="t", text="x", goal="g", options=[BattleOption(text="o", tag="x")])
    assert act.text_by_lead == {}
    # 兩幕的字典各自一份，改一幕不會動到另一幕
    other = BattleAct(id="b", title="t", text="x", goal="g", options=[BattleOption(text="o", tag="x")])
    act.text_by_lead["guan"] = "官軍佔上風。"
    assert other.text_by_lead == {}


def test_a_battle_may_leave_its_action_tags_out():
    """三招之後固定招看 BattleOption.move；action_tags 只剩放手一搏找不到成功率時的退路，可以省略。"""
    battle = BattleDef(
        id="t", name="測試", factions=[BattleFaction(id="a", name="甲"), BattleFaction(id="b", name="乙")],
        acts=[BattleAct(id="a1", title="t", text="x", goal="g", options=[BattleOption(text="o", tag="x")])],
        outcomes=[BattleOutcome(faction="a", title="甲勝", text="甲勝。")],
    )
    assert battle.action_tags == {}


def test_a_partial_affinity_override_changes_only_the_rows_it_names():
    """審查 m3：config.json 的 battle.affinity 只寫一個屬性，其餘七個照預設表——不會整張表被換掉、
    其他屬性悄悄變成沒有擅長也沒有不擅長。"""
    t = Config(battle={"affinity": {"陽": ["奇襲", "固守"]}}).battle
    assert t.affinity["陽"] == ("奇襲", "固守")
    assert {k: v for k, v in t.affinity.items() if k != "陽"} == {k: v for k, v in SPEC_AFFINITY.items() if k != "陽"}
    assert set(t.affinity) == set(SPEC_AFFINITY)
    assert BattleTuning().affinity == SPEC_AFFINITY  # 沒寫覆寫就是預設表，而且各個 Config 的那一份互不相干
    BattleTuning().affinity["剛"] = ("奇襲", "強攻")
    assert BattleTuning().affinity["剛"] == ("強攻", "奇襲")


def test_a_bad_row_inside_a_partial_affinity_override_is_still_rejected():
    with pytest.raises(ValidationError):
        Config(battle={"affinity": {"陽": ["強攻", "強攻"]}})
