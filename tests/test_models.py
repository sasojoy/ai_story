import pytest
from pydantic import ValidationError

from tianxia.models import Choice, Config, Event, Location


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
