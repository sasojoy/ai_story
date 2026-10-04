import json
import shutil

import pytest
from pydantic import ValidationError

from conftest import FIXTURE
from tianxia.content import ContentError, load_content, profile_line, validate
from tianxia.models import (
    BattleAct, BattleActionEffect, BattleDef, BattleFaction, BattleOption, BattleOutcome, FactionDef, Trend,
)


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
    assert content.characters["mate"].starting_wugong == "palm"
    assert content.squads["thug"].difficulty == 5
    assert content.skills["sword"].kind == "武學"
    assert content.skills["sword"].attribute == "柔"


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


def test_sim_rumor_may_carry_its_own_place(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "scenario.json", lambda d: d["sim_players"][0]["rumors"].append({"text": "{name}在寶洞外轉悠。", "location": "cave"}))
    rumors = load_content(root).scenario.sim_players[0].rumors
    assert rumors[0] == "{name}又劫了一艘船。" and (rumors[1].text, rumors[1].location) == ("{name}在寶洞外轉悠。", "cave")


def test_unknown_sim_rumor_place_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "scenario.json", lambda d: d["sim_players"][0]["rumors"].append({"text": "{name}上了火星。", "location": "mars"}))
    with pytest.raises(ContentError, match="虛擬玩家 翻江龍.*傳聞「{name}上了火星。」.*mars"):
        load_content(root)


def test_connections_may_name_the_kind_of_road(content):
    lake = content.locations["lake"]
    assert lake.connections == ["town", "cave"]  # 照樣能當地點 id 清單用
    assert all(isinstance(c, str) for c in lake.connections)  # 讀路的種類要用 .road，不能拿 isinstance(c, str) 分辨
    assert [(c.to, c.road) for c in lake.connections] == [("town", "路"), ("cave", "山路")]
    assert lake.road_to("cave") == "山路" and lake.road_to("town") == "路"
    assert content.locations["cave"].road_to("lake") == "山路"
    assert lake.road_to("nowhere") == "路"


def test_a_road_must_be_the_same_kind_at_both_ends(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "locations.json", lambda d: d[2].update(connections=["lake"]))  # 寶洞那頭寫成一般路
    with pytest.raises(ContentError, match="地點 cave 到 lake 寫的是路，lake 回來寫的是山路"):
        load_content(root)


def test_an_unknown_kind_of_road_is_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "locations.json", lambda d: d[0].update(connections=[{"to": "lake", "road": "高速公路"}]))
    with pytest.raises(ContentError, match="(?s)Location town.*road"):
        load_content(root)


def test_a_connection_object_needs_a_destination(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "locations.json", lambda d: d[0].update(connections=[{"road": "官道"}]))
    with pytest.raises(ContentError, match="(?s)Location town.*to"):
        load_content(root)


def test_the_same_place_cannot_be_listed_twice(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "locations.json", lambda d: d[0].update(connections=["lake", {"to": "lake", "road": "路"}]))
    with pytest.raises(ContentError, match="地點 town：connections 重複列了同一個地點"):
        load_content(root)


def test_move_cost_is_no_longer_a_location_field(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "locations.json", lambda d: d[1].update(move_cost=5))
    with pytest.raises(ContentError, match="(?s)Location lake.*move_cost"):
        load_content(root)


def test_road_factor_must_cover_every_kind_of_road(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "config.json", lambda d: d.update(road_factor={"官道": 0.8, "路": 1.0}))
    with pytest.raises(ContentError, match="config.road_factor 缺少 山路"):
        load_content(root)


def test_road_factor_rejects_an_unknown_kind_of_road(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "config.json", lambda d: d.update(road_factor={"官道": 0.8, "路": 1.0, "山路": 1.5, "小徑": 2}))
    with pytest.raises(ValidationError, match="road_factor"):
        load_content(root)


def test_a_battle_names_its_region(tmp_path):
    root = copy_fixture(tmp_path)
    write_battles_json(root)
    assert load_content(root).battles["b1"].region == "north"


def test_a_battle_in_an_unknown_region_is_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    battle = json.loads(json.dumps(MINIMAL_BATTLE))
    battle["region"] = "mars"
    write_battles_json(root, [battle])
    with pytest.raises(ContentError, match="戰鬥 b1：未知的大區 mars"):
        load_content(root)


def test_a_battle_must_name_its_region_when_the_map_has_regions(tmp_path):
    root = copy_fixture(tmp_path)
    battle = json.loads(json.dumps(MINIMAL_BATTLE))
    del battle["region"]
    write_battles_json(root, [battle])
    with pytest.raises(ContentError, match="戰鬥 b1：要寫 region"):
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


# ── 同伴招募（sanguo-companions 合併重寫，見設計文件四.4）───


def by_id(items, ident):
    return next(item for item in items if item["id"] == ident)


def test_roster_fields_loaded(content):
    mate, sage = content.characters["mate"], content.characters["sage"]
    assert (mate.kind, mate.recruit_at, mate.starting_wugong) == ("recruitable", "town", "palm")
    assert sage.starting_neigong == "calm"
    assert content.characters["thug"].kind is None
    assert content.events["meet"].choices[0].effect.recruit == "friend"
    assert content.events["meet"].condition.members_none == ["friend"]
    assert content.events["fortune"].fortune and content.events["fortune"].actions == []
    cfg = content.config
    assert (cfg.recruit_stamina, cfg.recruit_base_chance) == (15, 0.35)
    assert (cfg.fortune_day_min, cfg.fortune_day_max) == (2, 7)


ROSTER_ERRORS = [
    ("characters.json", lambda d: by_id(d, "mate").update(starting_wugong="breath"), "人物 mate：starting_wugong 要指向 kind=武學 的武學"),
    ("characters.json", lambda d: by_id(d, "sage").update(starting_neigong="palm"), "人物 sage：starting_neigong 要指向 kind=內功 的武學"),
    ("characters.json", lambda d: by_id(d, "mate").update(starting_wugong="ghost"), "人物 mate：未知的武學 ghost"),
    ("characters.json", lambda d: by_id(d, "scholar").update(recruit_at="mars"), "人物 scholar：未知的地點 mars"),
    ("characters.json", lambda d: by_id(d, "thug").update(recruit_at="town"), "人物 thug：只有 kind=recruitable 的同伴需要 recruit_at"),
    ("events/test.json", lambda d: by_id(d, "meet")["condition"].update(members_none=[]), "事件 meet：結識 friend 的事件，condition.members_none 要列出 friend"),
    ("events/test.json", lambda d: by_id(d, "meet")["condition"].update(members_none=["ghost"]), "事件 meet：未知的人物 ghost"),
    ("events/test.json", lambda d: by_id(d, "meet")["choices"][0]["effect"].update(recruit="thug"), "事件 meet 選項0：結識的 thug 不是可招募的同伴"),
    ("events/test.json", lambda d: by_id(d, "fortune").update(actions=["socialize"]), "事件 fortune：福緣事件只由交友觸發，actions 要是空的"),
    ("events/test.json", lambda d: by_id(d, "fortune")["choices"].append({"text": "婉拒"}), "事件 fortune：福緣事件的每個選項都要結識一個人"),
    ("events/test.json", lambda d: by_id(d, "fortune")["choices"][0].update(combat="thug"), "事件 fortune 選項0：福緣事件的選項不能有檢定或戰鬥"),
    ("events/test.json", lambda d: by_id(d, "fortune")["choices"][0].update(check={"stat": "wis", "difficulty": 5}), "事件 fortune 選項0：福緣事件的選項不能有檢定或戰鬥"),
]


@pytest.mark.parametrize("filename, edit, message", ROSTER_ERRORS)
def test_roster_content_errors_name_the_culprit(tmp_path, filename, edit, message):
    root = copy_fixture(tmp_path)
    edit_json(root / filename, edit)
    with pytest.raises(ContentError, match=message):
        load_content(root)


# ── 全服即時多人戰鬥內容 ──────────────────────────────────

MINIMAL_BATTLE = {
    "id": "b1", "name": "測試決戰",
    "region": "north",
    "factions": [{"id": "a", "name": "甲方"}, {"id": "b", "name": "乙方"}],
    "acts": [
        {
            "id": "a1", "title": "開戰", "text": "開戰了。", "goal": "打贏",
            "options": [{"text": "進攻", "tag": "go"}],
        }
    ],
    "action_tags": {"go": {"trend_delta": 1, "neili_damage": 5}},
    "outcomes": [{"faction": "a", "title": "甲方勝", "text": "甲方贏了。"}],
}


def write_battles_json(root, battles=(MINIMAL_BATTLE,)):
    (root / "battles.json").write_text(json.dumps(list(battles), ensure_ascii=False), encoding="utf-8")


def test_battles_json_is_optional(content):
    assert content.battles == {}  # fixture 沒有 battles.json，預設空字典，不報錯


def test_a_valid_battle_loads(tmp_path):
    root = copy_fixture(tmp_path)
    write_battles_json(root)
    content = load_content(root)
    assert "b1" in content.battles and content.battles["b1"].name == "測試決戰"


def test_threshold_starts_battle_with_unknown_id_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    write_battles_json(root)
    edit_json(root / "scenario.json", lambda d: d["thresholds"][0].update(starts_battle="does_not_exist"))
    with pytest.raises(ContentError, match="does_not_exist"):
        load_content(root)


def test_threshold_starts_battle_with_known_id_loads(tmp_path):
    root = copy_fixture(tmp_path)
    write_battles_json(root)
    edit_json(root / "scenario.json", lambda d: d["thresholds"][0].update(starts_battle="b1"))
    content = load_content(root)
    assert content.scenario.thresholds[0].starts_battle == "b1"


def test_battle_option_with_unknown_tag_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    battle = json.loads(json.dumps(MINIMAL_BATTLE))
    battle["acts"][0]["options"][0]["tag"] = "ghost"
    write_battles_json(root, [battle])
    with pytest.raises(ContentError, match="ghost"):
        load_content(root)


def test_battle_option_restricted_to_an_unknown_faction_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    battle = json.loads(json.dumps(MINIMAL_BATTLE))
    battle["acts"][0]["options"][0]["faction"] = "ghost"
    write_battles_json(root, [battle])
    with pytest.raises(ContentError, match="ghost"):
        load_content(root)


def _two_act_battle() -> dict:
    battle = json.loads(json.dumps(MINIMAL_BATTLE))
    battle["acts"].append(json.loads(json.dumps(battle["acts"][0])))
    battle["acts"][1]["id"] = "a2"
    return battle


def test_battle_acts_change_by_round_count_so_no_act_needs_advance_when(tmp_path):
    """戰鬥系統設計 3.2：換幕照回合數走、不看戰局，所以非最後一幕也不寫換幕條件；每幕幾回合、
    多懸殊提前收場沒寫就是 3 與 40。"""
    root = copy_fixture(tmp_path)
    write_battles_json(root, [_two_act_battle()])
    battle = load_content(root).battles["b1"]
    assert (battle.rounds_per_act, battle.decisive_margin) == (3, 40)


def test_battle_act_no_longer_takes_advance_when(tmp_path):
    root = copy_fixture(tmp_path)
    battle = _two_act_battle()
    battle["acts"][0]["advance_when"] = {"trend_outside": 20}  # 舊的換幕條件：寫了就是內容沒跟上新規則
    write_battles_json(root, [battle])
    with pytest.raises(ContentError, match="advance_when"):
        load_content(root)


def test_battle_reads_rounds_per_act_and_decisive_margin(tmp_path):
    root = copy_fixture(tmp_path)
    battle = _two_act_battle()
    battle.update(rounds_per_act=2, decisive_margin=25)
    write_battles_json(root, [battle])
    loaded = load_content(root).battles["b1"]
    assert (loaded.rounds_per_act, loaded.decisive_margin) == (2, 25)


@pytest.mark.parametrize("field", ["rounds_per_act", "decisive_margin"])
def test_battle_rounds_per_act_and_decisive_margin_must_be_at_least_one(tmp_path, field):
    root = copy_fixture(tmp_path)
    battle = json.loads(json.dumps(MINIMAL_BATTLE))
    battle[field] = 0
    write_battles_json(root, [battle])
    with pytest.raises(ContentError, match=rf"{field}[\s\S]*greater than or equal to 1"):
        load_content(root)


def test_battle_outcome_with_unknown_faction_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    battle = json.loads(json.dumps(MINIMAL_BATTLE))
    battle["outcomes"][0]["faction"] = "ghost"
    write_battles_json(root, [battle])
    with pytest.raises(ContentError, match="ghost"):
        load_content(root)


def test_battle_outcome_trend_delta_with_unknown_trend_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    battle = json.loads(json.dumps(MINIMAL_BATTLE))
    battle["outcomes"][0]["trend_delta"] = {"ghost": -10}
    write_battles_json(root, [battle])
    with pytest.raises(ContentError, match="ghost"):
        load_content(root)


def test_battle_last_outcome_must_be_unconditional(tmp_path):
    root = copy_fixture(tmp_path)
    battle = json.loads(json.dumps(MINIMAL_BATTLE))
    battle["outcomes"][0]["trend_min"] = 80
    write_battles_json(root, [battle])
    with pytest.raises(ContentError, match="最後一個結果必須沒有數值門檻"):
        load_content(root)


def test_duplicate_battle_faction_id_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    battle = json.loads(json.dumps(MINIMAL_BATTLE))
    battle["factions"][1]["id"] = "a"
    write_battles_json(root, [battle])
    with pytest.raises(ContentError, match="陣營 id 重複"):
        load_content(root)


def test_validate_rejects_a_faction_joining_at_an_unknown_place(content):
    content.scenario.factions = [FactionDef(id="guan", name="官軍", join_at=["nowhere"])]
    with pytest.raises(ContentError, match="nowhere"):
        validate(content)


def test_validate_rejects_a_faction_owning_an_unknown_sect(content):
    content.scenario.factions = [FactionDef(id="guan", name="官軍", sects=["no_such_sect"])]
    with pytest.raises(ContentError, match="no_such_sect"):
        validate(content)


def test_validate_rejects_duplicate_faction_ids(content):
    content.scenario.factions = [FactionDef(id="guan", name="官軍"), FactionDef(id="guan", name="又是官軍")]
    with pytest.raises(ContentError, match="陣營 id 重複"):
        validate(content)


def test_validate_rejects_a_faction_goal_on_an_unknown_trend(content):
    content.scenario.factions = [FactionDef(id="guan", name="官軍", goals={"ghost": 1})]
    with pytest.raises(ContentError, match="ghost"):
        validate(content)


def test_validate_rejects_a_faction_goal_that_is_not_up_or_down(content):
    content.scenario.factions = [FactionDef(id="guan", name="官軍", goals={"kou": 2})]
    with pytest.raises(ContentError, match="goals"):
        validate(content)


# ── 煉製素材（無限煉製第一刀）──────────────────────────────


def test_unknown_material_on_a_location_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "locations.json", lambda d: d[0].update(materials=["ghost"]))
    with pytest.raises(ContentError, match="ghost"):
        load_content(root)


def test_unknown_material_in_a_squad_drop_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "squads.json", lambda d: d[0].update(drops=[{"material": "ghost"}]))
    with pytest.raises(ContentError, match="ghost"):
        load_content(root)


def test_unknown_material_in_an_effect_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "events" / "test.json", lambda d: d[0]["choices"][0]["effect"].update(materials={"ghost": 1}))
    with pytest.raises(ContentError, match="ghost"):
        load_content(root)


def test_a_tier_with_no_material_at_all_rejected(tmp_path):
    """沒寫 drops 的對手走依難度的預設掉落表，所以每一階都得有素材可挑。"""
    root = copy_fixture(tmp_path)
    edit_json(root / "materials.json", lambda d: d.remove(next(m for m in d if m["tier"] == 3)))
    with pytest.raises(ContentError, match="天品"):
        load_content(root)


def test_a_material_tier_outside_one_to_three_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "materials.json", lambda d: d[0].update(tier=4))
    with pytest.raises(ContentError):
        load_content(root)


def _strand_the_top_tier(root):
    """造出「鎮山鐵」當初那個情境：所有對手都寫了明確 drops（依難度的預設表因此不會執行），
    於是三階素材沒有任何管道拿得到。"""
    drops = [{"material": "gang_1"}, {"material": "gang_2"}]  # 一、二階仍有來源，只有三階斷掉
    edit_json(root / "squads.json", lambda d: [sq.update(drops=list(drops)) for sq in d])


def test_a_material_with_no_source_at_all_rejected(tmp_path):
    """第一版的「鎮山鐵」就是這樣漏掉的：存在於內容裡，但沒有任何管道拿得到。"""
    root = copy_fixture(tmp_path)
    _strand_the_top_tier(root)
    with pytest.raises(ContentError, match="沒有任何取得管道"):
        load_content(root)


def test_a_material_only_an_event_gives_is_still_reachable(tmp_path):
    """手寫劇情給的素材算有來源（天品的主要管道就是奇遇，見設計 §4.3）。"""
    root = copy_fixture(tmp_path)
    _strand_the_top_tier(root)
    edit_json(
        root / "events" / "test.json",
        lambda d: d[0]["choices"][0]["effect"].update(materials={"gang_3": 1}),
    )
    load_content(root)  # 不該再報錯


def test_a_material_only_a_location_offers_is_still_reachable(tmp_path):
    root = copy_fixture(tmp_path)
    _strand_the_top_tier(root)
    edit_json(root / "locations.json", lambda d: d[0].update(materials=["gang_3"]))
    load_content(root)


def test_road_sights_load_from_their_own_file(content):
    assert {"sight_crow", "sight_cliff"} <= set(content.road_sights)
    assert content.road_sights["sight_cliff"].roads == ["山路"]
    assert content.road_sights["sight_wind"].effect.stats == {}


def test_every_kind_of_road_in_every_region_needs_two_road_sights(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "road_sights.json", lambda d: d.remove(next(s for s in d if s["id"] == "sight_wind")))
    with pytest.raises(ContentError, match="路上見聞：官道・north 只有 1 則可挑"):
        load_content(root)


@pytest.mark.parametrize(("effect", "message"), [
    ({"stats": {"silver": 11}}, "銀兩 1～10 或心得 1～5"),
    ({"stats": {"xinde": 6}}, "銀兩 1～10 或心得 1～5"),
    ({"stats": {"fame": 1}}, "銀兩 1～10 或心得 1～5"),
    ({"materials": {"gang_2": 1}}, "一階 1 個"),
    ({"materials": {"gang_1": 2}}, "一階 1 個"),
    ({"stats": {"xinde": 1}, "materials": {"gang_1": 1}}, "最多一種"),
    ({"rumor": "有人說了什麼。"}, "只能用 stats 或 materials"),
    ({"text": "你笑了。"}, "只能用 stats 或 materials"),
])
def test_a_road_sight_reward_must_stay_small(tmp_path, effect, message):
    root = copy_fixture(tmp_path)
    edit_json(root / "road_sights.json", lambda d: d[0].update(effect=effect))
    with pytest.raises(ContentError, match=f"路上見聞 sight_crow：.*{message}"):
        load_content(root)


def test_a_road_sight_in_simplified_characters_is_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "road_sights.json", lambda d: d[0].update(text="这条路上说话的人很多。"))
    with pytest.raises(ContentError, match="路上見聞 sight_crow：text 只能用繁體中文"):
        load_content(root)


def test_a_road_sight_in_an_unknown_region_is_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "road_sights.json", lambda d: d[0].update(regions=["mars"]))
    with pytest.raises(ContentError, match="路上見聞 sight_crow：未知的大區 mars"):
        load_content(root)


def test_a_road_sight_on_an_unknown_kind_of_road_is_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "road_sights.json", lambda d: d[0].update(roads=["小徑"]))
    with pytest.raises(ContentError, match="(?s)RoadSight sight_crow.*roads"):
        load_content(root)


def test_validate_rejects_a_squad_of_an_unknown_faction(content):
    content.scenario.factions = [FactionDef(id="guan", name="官軍")]
    content.squads["thug"].faction = "ghost"
    with pytest.raises(ContentError, match="ghost"):
        validate(content)


# ── 輿圖美術：河流、地形、指北針（輿圖美術設計第四節）──────────────────


def test_rivers_read_the_old_plain_point_lists_as_blue(content):
    (river,) = content.map.rivers  # 夾具的 map.json 還是舊格式：一串 [x, y] 點
    assert (river.points, river.width, river.color) == ([[0, 150], [400, 150]], (4, 8), "blue")


def test_rivers_read_the_new_objects(tmp_path):
    root = copy_fixture(tmp_path)
    river = {"name": "大河", "points": [[0, 20], [400, 40]], "width": [6, 12], "color": "yellow"}
    edit_json(root / "map.json", lambda d: d.update(rivers=[river]))
    (loaded,) = load_content(root).map.rivers
    assert (loaded.name, loaded.points, loaded.width, loaded.color) == ("大河", [[0, 20], [400, 40]], (6, 12), "yellow")


def test_river_colour_is_blue_or_yellow(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "map.json", lambda d: d.update(rivers=[{"points": [[0, 20], [400, 40]], "color": "green"}]))
    with pytest.raises(ValidationError, match="Input should be 'blue' or 'yellow'"):
        load_content(root)


@pytest.mark.parametrize("river", [
    {"name": "大河", "points": [[0, 20]]},  # 一個點畫不成河
    {"name": "大河", "points": [[0, 20], [999, 40]]},  # 出界
    {"name": "大河", "points": [[0, 20], [400, 40]], "width": [9, 5]},  # 往下游變窄
    {"name": "大河", "points": [[0, 20], [400, 40]], "width": [0, 5]},
])
def test_bad_rivers_rejected(tmp_path, river):
    root = copy_fixture(tmp_path)
    edit_json(root / "map.json", lambda d: d.update(rivers=[river]))
    with pytest.raises(ContentError, match="河流 大河"):
        load_content(root)


TERRAIN = [
    {"kind": "mountains", "name": "測試嶺", "spine": [[20, 60], [120, 50]], "size": 20},
    {"kind": "hills", "spine": [[250, 170], [330, 175]], "size": 10},
    {"kind": "forest", "points": [[300, 20], [380, 20], [380, 70]]},
]


def test_terrain_and_compass_load(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "map.json", lambda d: d.update(terrain=TERRAIN, compass=[370, 120]))
    m = load_content(root).map
    assert [(t.kind, t.name) for t in m.terrain] == [("mountains", "測試嶺"), ("hills", ""), ("forest", "")]
    assert m.terrain[0].spine == [[20, 60], [120, 50]] and m.terrain[2].points == [[300, 20], [380, 20], [380, 70]]
    assert m.compass == (370, 120)


def test_terrain_and_compass_are_optional(content):
    assert content.map.terrain == [] and content.map.compass is None


def test_terrain_kind_must_be_one_of_three(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "map.json", lambda d: d.update(terrain=[{"kind": "volcano", "spine": [[20, 60], [120, 50]], "size": 20}]))
    with pytest.raises(ValidationError, match="Input should be 'mountains', 'hills' or 'forest'"):
        load_content(root)


@pytest.mark.parametrize("piece, message", [
    ({"kind": "mountains", "name": "測試嶺", "spine": [[20, 60]], "size": 20}, "地形 測試嶺：spine"),
    ({"kind": "hills", "spine": [[20, 60], [120, 50]], "size": 7}, "地形第 1 筆：size"),
    ({"kind": "mountains", "name": "測試嶺", "spine": [[20, 60], [120, 50]], "size": 41}, "地形 測試嶺：size"),
    ({"kind": "mountains", "name": "測試嶺", "spine": [[20, 60], [420, 50]], "size": 20}, "地形 測試嶺：座標超出"),
    ({"kind": "forest", "points": [[300, 20], [380, 20]]}, "地形第 1 筆：林地"),
    ({"kind": "forest", "points": [[300, 20], [380, 20], [380, -1]]}, "地形第 1 筆：座標超出"),
])
def test_bad_terrain_rejected(tmp_path, piece, message):
    root = copy_fixture(tmp_path)
    edit_json(root / "map.json", lambda d: d.update(terrain=[piece]))
    with pytest.raises(ContentError, match=message):
        load_content(root)


def test_compass_must_be_on_the_map(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "map.json", lambda d: d.update(compass=[401, 120]))
    with pytest.raises(ContentError, match="指北針"):
        load_content(root)


# ── 第一季濃縮版：戰線與衍生線（T1）──────────────────────────


def _with_fronts(content):
    """夾具改成第一季濃縮版的樣子：北邊大區的戰線 east、南邊的 west，兩條合成 total（各半）。三個地點都在北邊。"""
    content.scenario.trends += [
        Trend(id="east", name="東線", start=40, season_one=True),
        Trend(id="west", name="西線", start=60, season_one=True),
        Trend(id="total", name="總勢", start=25, derived={"east": 0.5, "west": 0.5}),
    ]
    content.map.regions[0].front = "east"
    content.map.regions[1].front = "west"
    return content


def _battle(trend_delta):
    return BattleDef(
        id="t1", name="測試決戰", region="north",
        factions=[BattleFaction(id="guan", name="官軍"), BattleFaction(id="huang", name="黃巾")],
        acts=[BattleAct(id="a1", title="初探", text="雙方試探。", goal="推動戰局",
                        options=[BattleOption(text="穩紮穩打", tag="safe")])],
        action_tags={"safe": BattleActionEffect(trend_delta=1, neili_damage=5)},
        outcomes=[BattleOutcome(faction="guan", title="官軍大勝", text="官軍獲勝。", trend_delta=trend_delta)],
        muster_seconds=600, round_seconds=120,
    )


def test_validate_accepts_fronts_and_a_derived_trend(content):
    validate(_with_fronts(content))


def test_validate_rejects_derived_weights_that_do_not_add_up_to_one(content):
    _with_fronts(content).scenario.trends[-1].derived = {"east": 0.5, "west": 0.4}
    with pytest.raises(ContentError, match="權重加起來要是 1"):
        validate(content)


def test_validate_rejects_a_derived_trend_built_from_another_derived_trend(content):
    _with_fronts(content).scenario.trends.append(Trend(id="meta", name="套娃", derived={"total": 1.0}))
    with pytest.raises(ContentError, match="大勢線 meta：來源不能是另一條衍生線"):
        validate(content)


@pytest.mark.parametrize("front", ["total", "ghost"])
def test_validate_rejects_a_region_front_that_is_derived_or_unknown(content, front):
    _with_fronts(content).map.regions[0].front = front
    with pytest.raises(ContentError, match="大區 north"):
        validate(content)


def test_validate_rejects_training_that_pushes_another_regions_front(content):
    _with_fronts(content).locations["lake"].train_trend = {"west": -1}  # 湖邊在北邊，戰線是 east
    with pytest.raises(ContentError, match="地點 lake：train_trend 的 west 不是這個地點所在大區的戰線"):
        validate(content)


@pytest.mark.parametrize("where", ["train_trend", "sim", "goals", "outcome"])
def test_validate_rejects_pushes_on_a_derived_trend(content, where):
    content = _with_fronts(content)
    if where == "train_trend":
        content.locations["lake"].train_trend = {"total": -1}
    elif where == "sim":
        content.scenario.sim_players[0].trend = {"total": 1}
    elif where == "goals":
        content.scenario.factions = [FactionDef(id="guan", name="官軍", goals={"total": -1})]
    else:
        content.battles["t1"] = _battle({"total": -5})
    with pytest.raises(ContentError, match="不能推衍生線 total"):
        validate(content)


def test_validate_lets_effects_and_training_push_the_local_front(content):
    content = _with_fronts(content)
    content.locations["lake"].train_trend = {"front": -1}
    content.events["drunk"].choices[0].effect.trend = {"front": 1}
    content.battles["t1"] = _battle({"east": -5})
    validate(content)


@pytest.mark.parametrize("where", ["sim", "goals", "outcome", "region"])
def test_validate_rejects_the_front_key_outside_effects_and_training(content, where):
    content = _with_fronts(content)
    if where == "sim":
        content.scenario.sim_players[0].trend = {"front": 1}
    elif where == "goals":
        content.scenario.factions = [FactionDef(id="guan", name="官軍", goals={"front": -1})]
    elif where == "outcome":
        content.battles["t1"] = _battle({"front": -5})
    else:
        content.map.regions[0].trends = ["front"]
    with pytest.raises(ContentError, match="未知的大勢線 front"):
        validate(content)


def test_validate_rejects_the_front_key_when_no_trend_is_built_from_fronts(content):
    content.events["drunk"].choices[0].effect.trend = {"front": 1}  # 夾具原樣：沒有衍生線
    with pytest.raises(ContentError, match="用了 front"):
        validate(content)


def test_validate_reports_a_malformed_region_polygon_instead_of_crashing(tmp_path):
    """train_trend 的戰線歸屬要先查地點在哪個大區，有個點只寫了一個數字時不能在那裡炸成 ValueError，要照舊回報多邊形的錯。"""
    root = copy_fixture(tmp_path)
    edit_json(root / "map.json", lambda d: d["regions"][0].update(points=[[0, 0], [5], [400, 150]]))
    with pytest.raises(ContentError, match="多邊形至少"):
        load_content(root)


# ── 週末設定（計畫 T2「總開關與週末設定」）：一次切換，不手改 content/config.json ──
CONTENT_DIR = FIXTURE.parent.parent.parent / "content"
WEEKEND_KEYS = {"season_one", "season_days", "server_max_players"}


def test_weekend_profile_overrides_three_settings():
    base = load_content(CONTENT_DIR).config
    weekend = load_content(CONTENT_DIR, profile="weekend").config
    assert (weekend.season_one, weekend.season_days, weekend.server_max_players) == (True, 2.5, 2)
    assert (base.season_one, base.season_days, base.server_max_players) == (False, 14, 30)  # 不給 profile 時照 config.json
    assert weekend.model_dump(exclude=WEEKEND_KEYS) == base.model_dump(exclude=WEEKEND_KEYS)  # 其他設定一個都不動


def test_profile_with_unknown_key_fails_to_load(tmp_path):
    root = copy_fixture(tmp_path)
    (root / "profiles").mkdir()
    (root / "profiles" / "typo.json").write_text('{"season_one": true, "season_dayz": 2.5}', encoding="utf-8")
    with pytest.raises(ContentError, match="season_dayz"):
        load_content(root, profile="typo")


def test_a_profile_that_does_not_exist_fails_to_load(tmp_path):
    with pytest.raises(ContentError, match="nope"):
        load_content(copy_fixture(tmp_path), profile="nope")


def test_the_profile_line_says_what_the_profile_turns_on():
    assert profile_line(load_content(CONTENT_DIR), None) == "設定：預設"
    assert profile_line(load_content(CONTENT_DIR, profile="weekend"), "weekend") == (
        "設定：weekend（第一季濃縮版規則開啟、季長 2.5 天、人數上限 2）"
    )


# ── 時刻表（content/timetable.json，計畫 T2）──────────────────────────


def _timetable() -> list[dict]:
    """測試夾具用的小時刻表：一件固定、一件擲骰（有鎖定與豪強）、一件看版本的決戰。"""
    return [
        {"id": "start", "week": 1, "title": "開場", "kind": "fixed", "outcomes": {"fixed": {"text": "開場了。"}}},
        {"id": "raid", "week": 2, "front": "north", "title": "劫江", "kind": "roll", "roll_side": "huang",
         "lock_result": {"huang": "成", "guan": "不成"}, "third_party_trends": {"kou": 3},
         "outcomes": {
             "成": {"text": "劫成了。", "chronicle": "水寇劫江。", "trends": {"kou": 8},
                   "locked_text": {"huang": "{name} 劫成了。"}, "loser_text": {"huang": "{loser} 沒擋住。"},
                   "figures": {"mate": {"fate": "受挫"}}, "chance_mods": {"ambush": -0.1}},
             "不成": {"text": "沒劫成。", "trends": {"kou": -5}},
         }},
        {"id": "ambush", "week": 3, "front": "south", "title": "伏擊", "kind": "roll", "roll_side": "guan",
         "outcomes": {"成": {"text": "伏擊成了。"}, "不成": {"text": "伏擊落空。"}}},
        {"id": "siege", "week": 3, "front": "south", "title": "圍城", "kind": "showdown", "version_from": "raid",
         "versions": {"成": "甲", "不成": "乙"},
         "outcomes": {f"{v}:{side}:{tier}": {"text": "打完了。", "figures": {"@commander:south:guan": {"fate": "受挫"}}}
                      for v in ("甲", "乙") for side in ("guan", "huang") for tier in ("大勝", "險勝")}},
    ]


def _with_timetable(tmp_path, edit=None):
    root = copy_fixture(tmp_path)
    events = _timetable()
    if edit is not None:
        edit(events)
    (root / "timetable.json").write_text(json.dumps(events, ensure_ascii=False), encoding="utf-8")
    return root


def test_the_timetable_loads_and_is_optional(tmp_path):
    assert load_content(copy_fixture(tmp_path / "a")).timetable == []  # 沒有 timetable.json 的內容照舊載得進來
    loaded = load_content(_with_timetable(tmp_path / "b"))
    assert [e.id for e in loaded.timetable] == ["start", "raid", "ambush", "siege"]


@pytest.mark.parametrize(("edit", "message"), [
    (lambda ev: ev[1].update(front="nowhere"), "nowhere"),  # 戰線要是大區 id
    (lambda ev: ev[1]["outcomes"].pop("不成"), "不成"),  # 擲骰要有成與不成
    (lambda ev: ev[3]["outcomes"].pop("乙:huang:險勝"), "乙:huang:險勝"),  # 決戰每個版本四格
    (lambda ev: ev.append(dict(ev[0])), "start"),  # id 重複
    (lambda ev: ev[1].update(roll_side=None), "roll_side"),
    (lambda ev: ev[0].update(roll_side="guan"), "roll_side"),  # 不擲骰的不寫 roll_side（軍令的修正靠它判斷）
    (lambda ev: ev[1]["outcomes"]["成"]["trends"].update(nowhere=3), "nowhere"),  # 未知的大勢線
    (lambda ev: ev[1]["outcomes"]["成"]["figures"].update(ghost={"fate": "受挫"}), "ghost"),  # 未知的人物
    (lambda ev: ev[3]["outcomes"]["甲:guan:大勝"]["figures"].update({"@commander:nowhere:guan": {"fate": "受挫"}}), "nowhere"),
    (lambda ev: ev[1]["outcomes"]["成"]["chance_mods"].update(ghost=0.1), "ghost"),  # 修正要加在時刻表上的大事
    (lambda ev: ev[1]["lock_result"].update(guan="大勝"), "大勝"),  # 鎖定要對到一個結果
    (lambda ev: ev[3].update(version_from="ghost"), "ghost"),
    (lambda ev: ev[1]["outcomes"]["成"].update(chance_mods={"siege": -0.1}), "siege"),  # 決戰不擲骰：修正沒有意義
    (lambda ev: ev[2]["outcomes"]["成"].update(chance_mods={"raid": -0.1}), "raid"),  # 要加在之後的大事上
    (lambda ev: ev[1]["outcomes"]["成"]["figures"].update(mate={"fate": "到任"}), "到任"),  # 到任要寫戰線與地點
    (lambda ev: ev[1].update(week=13), "13"),  # 季曆只有 12 週
    (lambda ev: ev[0]["outcomes"]["fixed"].update(text="开场了。"), "繁體"),  # 公告只能用繁體中文
])
def test_timetable_cross_references_are_checked(tmp_path, edit, message):
    with pytest.raises(ContentError, match=message):
        load_content(_with_timetable(tmp_path, edit))


def test_fate_prestige_only_knows_the_three_fate_words(tmp_path):
    """Config.fate_prestige 只能寫重挫、聲威大減、受挫（退場、重創是歸零，下獄、到任不動聲威）。"""
    root = copy_fixture(tmp_path)
    edit_json(root / "config.json", lambda d: d.update(fate_prestige={"重挫": -30, "重創": -60}))
    with pytest.raises(ValidationError, match="fate_prestige"):
        load_content(root)
