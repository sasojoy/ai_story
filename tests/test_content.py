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
    with pytest.raises(ContentError, match="conection"):
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


def test_branch_storyline_needs_replaces_when(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "scenario.json", lambda d: d["storylines"][1].pop("replaces_when"))
    with pytest.raises(ContentError, match="treasure"):
        load_content(root)


def test_final_act_cannot_advance(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "scenario.json", lambda d: d["storylines"][0]["acts"][1].update(advance_when={"day_min": 3}))
    with pytest.raises(ContentError, match="a2"):
        load_content(root)


def test_ending_with_unknown_storyline_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "scenario.json", lambda d: d["endings"][0].update(storyline="nope"))
    with pytest.raises(ContentError, match="nope"):
        load_content(root)


def test_tutorial_unknown_location_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "tutorial.json", lambda d: d["steps"][1]["done_when"].update(locations=["mars"]))
    with pytest.raises(ContentError, match="mars"):
        load_content(root)


def test_map_region_color_must_be_hex(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "map.json", lambda d: d["regions"][0].update(fill="red"))
    with pytest.raises(Exception, match="fill"):
        load_content(root)


def test_check_by_must_be_team_or_self(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "events" / "test.json", lambda d: d[0]["choices"][0]["check"].update(by="friend"))
    with pytest.raises(ContentError, match="drunk"):
        load_content(root)


def test_checks_default_to_team(content):
    assert content.events["drunk"].choices[0].check.by == "team"
    assert content.events["insight"].choices[0].check.by == "self"


def test_characters_and_squads_loaded(content):
    assert content.characters["mate"].innate == "palm"
    assert content.squads["thug"].members[0].character == "thug"
    assert content.skills["sword"].kind == "絕招"
    assert content.skills["sword"].effects[0].top == 2.0


def test_buff_effect_needs_stat(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "skills.json", lambda d: d[3]["effects"][0].pop("stat"))
    with pytest.raises(ContentError, match="step"):
        load_content(root)


def test_skill_without_effects_names_the_skill(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "skills.json", lambda d: d[0].update(effects=[]))
    with pytest.raises(ContentError, match="fist"):
        load_content(root)


def test_ultimate_needs_chance(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "skills.json", lambda d: d[2].update(chance_base=0))
    with pytest.raises(ContentError, match="sword"):
        load_content(root)


def test_squad_with_unknown_character_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "squads.json", lambda d: d[0]["members"].append({"character": "ghost"}))
    with pytest.raises(ContentError, match="ghost"):
        load_content(root)


def test_character_missing_combat_stat_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "characters.json", lambda d: d[0]["stats"].pop("wis"))
    with pytest.raises(ContentError, match="mate"):
        load_content(root)


def test_map_and_scenario_places_loaded(content):
    assert [(r.id, r.trends) for r in content.map.regions] == [("north", ["kou"]), ("south", ["bao"])]
    s = content.scenario
    assert [sim.haunts for sim in s.sim_players] == [["lake"], ["cave"]]
    assert [act.places for act in s.storylines[0].acts] == [["lake"], []]
    assert [th.location for th in s.thresholds] == ["lake", None, "cave"]
    assert s.world_events[0].location == "cave"


def test_region_with_unknown_trend_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "map.json", lambda d: d["regions"][0]["trends"].append("ghost"))
    with pytest.raises(ContentError, match="大區 north.*ghost"):
        load_content(root)


def test_duplicate_region_id_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "map.json", lambda d: d["regions"][1].update(id="north"))
    with pytest.raises(ContentError, match="大區 id 重複：north"):
        load_content(root)


def test_region_needs_an_id(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "map.json", lambda d: d["regions"][0].pop("id"))
    with pytest.raises(Exception, match="id"):
        load_content(root)


def test_region_needs_a_polygon(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "map.json", lambda d: d["regions"][1].update(points=[[0, 150], [400, 150]]))
    with pytest.raises(ContentError, match="大區 south"):
        load_content(root)


def test_unknown_haunt_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "scenario.json", lambda d: d["sim_players"][0]["haunts"].append("mars"))
    with pytest.raises(ContentError, match="虛擬玩家 翻江龍.*mars"):
        load_content(root)


def test_unknown_act_place_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "scenario.json", lambda d: d["storylines"][0]["acts"][1].update(places=["mars"]))
    with pytest.raises(ContentError, match="a2.*mars"):
        load_content(root)


def test_unknown_threshold_location_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "scenario.json", lambda d: d["thresholds"][1].update(location="mars"))
    with pytest.raises(ContentError, match="kou80.*mars"):
        load_content(root)


def test_unknown_world_event_location_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "scenario.json", lambda d: d["world_events"][0].update(location="mars"))
    with pytest.raises(ContentError, match="grab.*mars"):
        load_content(root)
