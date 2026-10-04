import pytest
from pydantic import ValidationError

from tianxia.models import Choice, Config, Connection, Event, Location


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
        ("camp", ["營寨", "祭壇", "塢堡"], {"material": 15, "wild": 35, "event": 50}),
        ("town", ["城鎮", "官署", "城池", "寺院", "書院", "莊院", "里巷", "結社"], {"material": 15, "wild": 0, "event": 85}),
        ("wild", [], {"material": 40, "wild": 35, "event": 25}),
    ]
    assert cfg.wild_neili_loss_factor == 0.5
    assert 0 < cfg.rare_explore_chance < 1
    assert not hasattr(cfg, "explore_material_chance")  # 探索前固定滾三成素材已經拿掉，素材改由「素材」那一支給


def test_a_place_takes_the_first_kind_whose_tags_it_has():
    cfg = Config()
    assert cfg.explore_mix_of(["城池", "營寨"]).kind == "camp"  # 廣宗：營寨優先於城鎮
    assert cfg.explore_mix_of(["寺院"]).kind == "town"
    assert cfg.explore_mix_of(["官道", "野外"]).kind == "wild"
    assert cfg.explore_mix_of([]).kind == "wild"  # 沒有標籤也算「其餘」


def _mix(kind, tags, **weights):
    return {"kind": kind, "tags": tags, "weights": weights}


@pytest.mark.parametrize("mix", [
    [_mix("wild", [], material=-1, wild=35, event=25)],  # 權重不能是負的
    [_mix("wild", [], material=0, wild=0, event=0)],  # 三支總和要大於 0
    [_mix("town", ["城鎮"], material=15, event=85)],  # 最後一筆必須是 tags 空的「其餘」
    [_mix("wild", [], material=40), _mix("town", ["城鎮"], event=85)],  # tags 空的只能放最後
    [],  # 一筆都沒有
    [_mix("wild", [], material=40, loot=10)],  # 只有素材、野怪、事件三支
])
def test_explore_mix_rejects_a_broken_table(mix):
    with pytest.raises(ValidationError):
        Config(explore_mix=mix)


@pytest.mark.parametrize("field, value", [
    ("rare_explore_chance", -0.1), ("rare_explore_chance", 1.5),
    ("wild_neili_loss_factor", -0.5), ("wild_neili_loss_factor", 1.5),
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
