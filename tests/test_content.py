import json
import shutil

import pytest

from conftest import FIXTURE
from tianxia.content import ContentError, load_content


def copy_fixture(tmp_path):
    dest = tmp_path / "content"
    shutil.copytree(FIXTURE, dest)
    return dest


def edit_json(path, fn):
    data = json.loads(path.read_text(encoding="utf-8"))
    fn(data)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_load_fixture(content):
    assert set(content.locations) == {"town", "lake", "cave"}
    assert "drunk" in content.events and "chain_b" in content.events
    assert content.scenario.start_location == "town"
    assert content.config.starter_skills == ["fist"]


def test_one_way_connection_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "locations.json", lambda d: d[0]["connections"].append("cave"))
    with pytest.raises(ContentError, match="town.*cave"):
        load_content(root)


def test_unknown_enemy_in_choice_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "events" / "test.json", lambda d: d[0]["choices"][0].update(combat="ghost"))
    with pytest.raises(ContentError, match="ghost"):
        load_content(root)


def test_event_needs_unconditional_choice(tmp_path):
    root = copy_fixture(tmp_path)

    def make_all_conditional(d):
        for choice in d[0]["choices"]:
            choice["condition"] = {"min_stats": {"str": 1}}

    edit_json(root / "events" / "test.json", make_all_conditional)
    with pytest.raises(ContentError, match="drunk"):
        load_content(root)


def test_unknown_stat_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "events" / "test.json", lambda d: d[0]["choices"][1]["effect"]["stats"].update(luck=1))
    with pytest.raises(ContentError, match="luck"):
        load_content(root)


def test_last_ending_must_be_unconditional(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "scenario.json", lambda d: d["endings"].pop())
    with pytest.raises(ContentError, match="結局"):
        load_content(root)


def test_duplicate_event_id_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "events" / "test.json", lambda d: d.append(dict(d[0])))
    with pytest.raises(ContentError, match="drunk"):
        load_content(root)


def test_hidden_trend_cannot_use_lte_threshold(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "scenario.json", lambda d: d["thresholds"][2].update(op="<=", value=0))
    with pytest.raises(ContentError, match="bao100"):
        load_content(root)


def test_unknown_field_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "locations.json", lambda d: d[0].update(conection=["lake"]))
    with pytest.raises(Exception, match="conection"):
        load_content(root)


def test_map_loaded(content):
    assert content.map.width == 400
    assert content.map.labels[0].text == "測試區"
    assert (content.locations["town"].x, content.locations["town"].y) == (100, 100)


def test_location_outside_map_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "locations.json", lambda d: d[0].update(x=9999))
    with pytest.raises(ContentError, match="town"):
        load_content(root)


def test_unknown_trend_in_revealed_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "events" / "test.json", lambda d: d[0].update(condition={"revealed_all": ["ghost"]}))
    with pytest.raises(ContentError, match="ghost"):
        load_content(root)
