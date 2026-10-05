import pytest
from pydantic import ValidationError

from tianxia.models import (
    EXPLORE_BRANCHES, Choice, Config, Connection, Event, InsightDef, InsightGrant, LearnRule, Location, SkillDef,
)


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
    assert cfg.cultivate_odds == {"中品": (20, 10), "上品": (10, 6), "絕學": (4, 3)}
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
