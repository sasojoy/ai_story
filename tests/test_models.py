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
