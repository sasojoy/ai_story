import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from conftest import FIXTURE
from tianxia import naming
from tianxia.content import ContentError, load_content, profile_line, validate
from tianxia.models import (
    BattleAct, BattleActionEffect, BattleDef, BattleFaction, BattleOption, BattleOutcome, Condition, Config, FactionDef,
    Threshold, Trend,
)

ROOT = Path(__file__).resolve().parent.parent


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


def test_unknown_practice_rejected(tmp_path):
    root = copy_fixture(tmp_path)

    def add_practice(d):
        choice = next(ch for ch in d[0]["choices"] if "check" in ch)
        choice["check"]["practice"] = "luck"

    edit_json(root / "events" / "test.json", add_practice)
    with pytest.raises(ContentError, match="luck"):
        load_content(root)


def test_practice_must_be_a_reputation(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "config.json", lambda d: d.update(practice_bonus={"agi": {"per": 10, "cap": 3}}))
    with pytest.raises(ContentError, match="agi"):
        load_content(root)


def test_practice_cannot_be_lore(tmp_path):
    """熟練加成吃的是名聲類的屬性；博聞跟另外四項一樣是能力值，不能拿來當熟練。"""
    root = copy_fixture(tmp_path)
    edit_json(root / "config.json", lambda d: d.update(practice_bonus={"lore": {"per": 10, "cap": 3}}))
    with pytest.raises(ContentError, match="lore"):
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


def test_a_character_may_have_up_to_three_brush_off_lines(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "characters.json", lambda d: d[0].update(brush_off=["一。", "二。", "三。"]))
    assert load_content(root).characters["mate"].brush_off == ["一。", "二。", "三。"]


def test_more_than_three_brush_off_lines_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "characters.json", lambda d: d[0].update(brush_off=["一。", "二。", "三。", "四。"]))
    with pytest.raises(ContentError, match="mate.*brush_off 最多三句"):
        load_content(root)


def test_brush_off_defaults_to_nothing_and_the_rank_discount_to_five(content):
    assert content.characters["mate"].brush_off == []
    assert content.config.audience_rank_discount == 5


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


def test_season_one_off_loads_and_defaults_to_nothing(tmp_path, content):
    """第一季不觸發的清單（控制者 2026-10-04，與 T4 說好的格式，後來多了個人目標）：五種各自寫那一種內容的 id；沒寫就是空的。"""
    assert content.scenario.season_one_off.model_dump() == {
        "thresholds": [], "storylines": [], "battles": [], "events": [], "milestones": [],
    }
    root = copy_fixture(tmp_path)
    write_battles_json(root)
    edit_json(root / "scenario.json", lambda d: d.update(season_one_off={
        "thresholds": ["kou50"], "storylines": ["main"], "battles": ["b1"], "events": ["drunk"], "milestones": ["m1"],
    }))
    off = load_content(root).scenario.season_one_off
    assert (off.thresholds, off.storylines, off.battles, off.events, off.milestones) == (
        ["kou50"], ["main"], ["b1"], ["drunk"], ["m1"],
    )


@pytest.mark.parametrize(("kind", "ghost", "message"), [
    ("thresholds", "kou99", "門檻 kou99"),
    ("storylines", "side", "主線 side"),
    ("battles", "b9", "戰鬥 b9"),
    ("events", "ghost_event", "事件 ghost_event"),
    ("milestones", "ghost_goal", "個人目標 ghost_goal"),
    ("thresholds", "main", "門檻 main"),  # 照種類各自檢查：主線的 id 不能寫在門檻那一欄
    ("battles", "kou50", "戰鬥 kou50"),
])
def test_season_one_off_ids_are_checked(tmp_path, kind, ghost, message):
    root = copy_fixture(tmp_path)
    write_battles_json(root)
    edit_json(root / "scenario.json", lambda d: d.update(season_one_off={kind: [ghost]}))
    with pytest.raises(ContentError, match=f"第一季不觸發.*未知的{message}"):
        load_content(root)


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


def test_a_higher_tier_material_a_location_lists_is_not_reachable_from_it(tmp_path):
    """探索不再撿素材（武學與成長計畫一）：地點寫的素材只決定路邊採集出什麼屬性，採到的永遠是那個屬性的一階。
    所以地點寫了天品，天品也不會因此拿得到。"""
    root = copy_fixture(tmp_path)
    _strand_the_top_tier(root)
    edit_json(root / "locations.json", lambda d: d[0].update(materials=["gang_3"]))
    with pytest.raises(ContentError, match="隕鐵膽"):
        load_content(root)


def _every_place_lists_only_gang(root):
    """每個地點都只寫剛；快屬性的一階素材原本還有一則路上見聞給，這裡拿掉，路邊採集就成了唯一的可能。"""
    edit_json(root / "locations.json", lambda d: [loc.update(materials=["gang_1"]) for loc in d])
    edit_json(root / "road_sights.json", lambda d: [s.get("effect", {}).pop("materials", None) for s in d])


def test_a_first_tier_material_no_road_can_give_is_rejected(tmp_path):
    """路邊採集只出兩頭地點寫的屬性：每個地點都只寫剛，快屬性的一階素材就沒有任何管道。"""
    root = copy_fixture(tmp_path)
    _every_place_lists_only_gang(root)
    with pytest.raises(ContentError, match="驚羽"):
        load_content(root)


def test_a_first_tier_material_a_road_between_listed_places_can_give_is_reachable(tmp_path):
    root = copy_fixture(tmp_path)
    _every_place_lists_only_gang(root)
    edit_json(root / "locations.json", lambda d: d[0].update(materials=["kuai_1"]))  # 小鎮出快：小鎮到湖邊的路採得到
    load_content(root)


def test_a_road_between_two_unlisted_places_can_give_any_first_tier_material(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "locations.json", lambda d: [loc.pop("materials", None) for loc in d])
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


@pytest.mark.parametrize("bound", ["trend_min", "trend_max"])
@pytest.mark.parametrize("where", ["event", "any_of", "choice", "ending", "storyline", "milestone"])
def test_validate_rejects_a_condition_on_a_season_one_trend(content, where, bound):
    """條件讀的是 world.trends 的原數字：開關關著時戰線沒有值（讀成 0）、季中才開季的那一季讀不到起始值，
    所以條件不能掛在第一季的線上（戰線、割據）；要讀就讀衍生線（黃巾聲勢）或一般的線。"""
    content = _with_fronts(content)
    cond = Condition(**{bound: {"east": 50}})
    if where == "event":
        content.events["drunk"].condition = cond
    elif where == "any_of":
        content.events["drunk"].condition = Condition(any_of=[cond])
    elif where == "choice":
        content.events["drunk"].choices[0].condition = cond
    elif where == "ending":
        content.scenario.endings[0].condition = cond
    elif where == "storyline":
        content.scenario.storylines[0].acts[0].advance_when = cond
    else:
        content.scenario.milestones[0].condition = cond
    with pytest.raises(ContentError, match="條件不能讀第一季的線 east"):
        validate(content)


def test_validate_names_the_place_of_a_condition_on_a_season_one_trend(content):
    content = _with_fronts(content)
    content.events["drunk"].condition = Condition(trend_min={"west": 50})
    with pytest.raises(ContentError, match="事件 drunk：條件不能讀第一季的線 west"):
        validate(content)


def test_validate_still_lets_conditions_read_derived_and_ordinary_trends(content):
    content = _with_fronts(content)
    content.events["drunk"].condition = Condition(trend_min={"total": 40, "kou": 10}, trend_max={"total": 90})
    validate(content)


def test_validate_rejects_a_threshold_on_a_season_one_trend(content):
    content = _with_fronts(content)
    content.scenario.trends.append(Trend(id="geju", name="豪強割據", season_one=True))
    content.scenario.thresholds.append(
        Threshold(id="geju60", trend="geju", op=">=", value=60, text="豪強割據一方！")
    )
    with pytest.raises(ContentError, match="門檻 geju60：不能掛在第一季的線 geju"):
        validate(content)


def test_validate_lets_a_threshold_sit_on_a_derived_trend(content):
    content = _with_fronts(content)
    content.scenario.thresholds.append(
        Threshold(id="total60", trend="total", op=">=", value=60, text="總勢過六成。")
    )
    validate(content)


def test_validate_rejects_a_trend_named_front(content):
    """front 是效果與歷練裡「所在大區的戰線」的特殊鍵：真有一條大勢線叫 front，推它與推本地戰線就分不出來。"""
    content.scenario.trends.append(Trend(id="front", name="撞名"))
    with pytest.raises(ContentError, match="大勢線 front：id 不能叫 front"):
        validate(content)


def test_validate_rejects_chaos_bounds_that_cross(content):
    """亂局是 chaos_low～chaos_high 之間：下界比上界高就永遠沒有戰線在亂局，割據只會一路回落。"""
    content.config.chaos_low, content.config.chaos_high = 70, 30
    with pytest.raises(ContentError, match="chaos_low 不能大於 chaos_high"):
        validate(content)


def test_validate_lets_chaos_bounds_meet(content):
    content.config.chaos_low = content.config.chaos_high = 50
    validate(content)


@pytest.mark.parametrize("field", ["geju_chaos_per_day", "geju_calm_per_day"])
def test_config_rejects_negative_geju_rates(field):
    with pytest.raises(ValidationError):
        Config(**{field: -0.5})
    assert getattr(Config(**{field: 0}), field) == 0


def test_geju_full_players_must_be_positive():
    """滿額人數是除數：0 或負的都不行。"""
    for bad in (0, -3):
        with pytest.raises(ValidationError):
            Config(geju_full_players=bad)
    assert Config(geju_full_players=1).geju_full_players == 1


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


# 可以打開伺服器排程的設定：只有壓測用的（壓測計畫 Task 4 的 content/profiles/loadtest.json 寫 10）。其他設定（試玩的
# weekend 等）一律關著，直到 PM 驗收之後決定在哪一份打開——到時改 test_world_tick_is_off_by_default，寫明是哪一份、為什麼
LOAD_TEST_PROFILES = frozenset({"loadtest"})


def _schedule_switched_on(root: Path) -> list[str]:
    """root/profiles 裡打開了伺服器排程、又不在 LOAD_TEST_PROFILES 的設定名稱。"""
    return [
        path.stem for path in sorted((root / "profiles").glob("*.json"))
        if path.stem not in LOAD_TEST_PROFILES and load_content(root, profile=path.stem).config.world_tick_seconds != 0
    ]


def test_world_tick_is_off_by_default():
    """伺服器排程預設關（線上架構排程計畫）：0＝不開執行緒，世界時間照舊等有人連線才推。
    content/config.json 與玩家用的設定（weekend 等）都還沒打開；只有 LOAD_TEST_PROFILES 列的壓測設定（loadtest）可以打開
    （最終審查 M1）。要在哪一份玩家用的設定打開，由 PM 驗收之後決定，到時改這個測試、寫明是哪一份。"""
    assert load_content(CONTENT_DIR).config.world_tick_seconds == 0
    assert _schedule_switched_on(CONTENT_DIR) == []


def test_only_the_load_test_profiles_may_switch_the_schedule_on(tmp_path):
    root = copy_fixture(tmp_path)
    (root / "profiles").mkdir()
    for name in ("loadtest", "preview"):
        (root / "profiles" / f"{name}.json").write_text('{"world_tick_seconds": 10}', encoding="utf-8")
    (root / "profiles" / "weekend.json").write_text('{"season_days": 2.5}', encoding="utf-8")
    assert _schedule_switched_on(root) == ["preview"]


def test_world_tick_seconds_cannot_be_negative():
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        Config(world_tick_seconds=-1)


def test_world_tick_seconds_is_off_or_at_least_a_second():
    """0 是關；開著至少 1 秒（最終審查 M5：0.1 秒就是每秒十筆寫入交易）。"""
    assert Config(world_tick_seconds=0).world_tick_seconds == 0
    assert Config(world_tick_seconds=1).world_tick_seconds == 1
    with pytest.raises(ValidationError, match="至少 1 秒"):
        Config(world_tick_seconds=0.5)


# ── LLM 佇列與鎖外模型呼叫的時間預算（線上架構第 2 期計畫）──────────────


def test_llm_queue_is_off_by_default():
    """LLM 佇列預設關（線上架構第 2 期計畫）：0＝不建佇列，鎖外的模型呼叫照舊直接叫。content/config.json 與玩家用的設定
    （weekend 等）都不打開；要在哪一份打開由 PM 驗收之後決定，到時改這個測試、寫明是哪一份。"""
    config = load_content(CONTENT_DIR).config
    assert (config.llm_queue_slots, config.llm_queue_bot_cap, config.llm_queue_wait_seconds) == (0, 1, 20)
    for path in sorted((CONTENT_DIR / "profiles").glob("*.json")):
        assert load_content(CONTENT_DIR, profile=path.stem).config.llm_queue_slots == 0, path.stem


@pytest.mark.parametrize("field", ["llm_queue_slots", "llm_queue_bot_cap", "llm_queue_wait_seconds"])
def test_llm_queue_settings_cannot_be_negative(field):
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        Config(**{field: -1})


def test_every_model_call_outside_the_lock_has_a_total_budget():
    """鎖外四種模型呼叫（開爐取名、大場面判讀、對話生成、隨口應對評分）各有一份總預算，預設都是 60 秒：試玩走 trycloudflare，
    一個請求約 100 秒就被切斷，60 秒留下 A、C 兩段等行動鎖與排模型佇列的餘裕。"""
    config = load_content(CONTENT_DIR).config
    assert (
        config.naming_budget_seconds, config.big_fight_budget_seconds,
        config.dialogue_budget_seconds, config.free_text_budget_seconds,
    ) == (60, 60, 60, 60)
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        Config(dialogue_budget_seconds=-1)
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        Config(free_text_budget_seconds=-1)


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
    """fixture 加上時刻表。時刻表的 front 是戰線（大區的 front 指到的大勢線），所以 north、south 兩個大區各有一條
    同名的戰線。"""
    root = copy_fixture(tmp_path)
    scenario = json.loads((root / "scenario.json").read_text(encoding="utf-8"))
    scenario["trends"] += [{"id": rid, "name": name, "start": 50} for rid, name in (("north", "北線"), ("south", "南線"))]
    (root / "scenario.json").write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")
    world_map = json.loads((root / "map.json").read_text(encoding="utf-8"))
    for region in world_map["regions"]:
        region["front"] = region["id"]
    (root / "map.json").write_text(json.dumps(world_map, ensure_ascii=False), encoding="utf-8")
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
    (lambda ev: ev[1].update(front="nowhere"), "nowhere"),  # 戰線要是戰線 id（大區的 front）
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


# ── 三場大戲：時刻表決戰的 BattleDef（計畫 T8）──────────────────────────


def _showdown_battle(**fields) -> dict:
    """接在 _with_timetable 的「圍城」（siege，第 3 週、南線、看 raid 分甲乙兩版）上的甲版決戰。"""
    battle = json.loads(json.dumps(MINIMAL_BATTLE))
    battle.update(
        id="siege_jia", region="south", factions=[{"id": "guan", "name": "官軍"}, {"id": "huang", "name": "黃巾"}],
        defender="huang", timetable_event="siege", version="甲", front="south",
    )
    battle["outcomes"][0]["faction"] = "guan"
    battle.update(fields)
    return battle


def test_a_timetable_showdown_loads(tmp_path):
    root = _with_timetable(tmp_path)
    write_battles_json(root, [_showdown_battle(), _showdown_battle(id="siege_yi", version="乙", defender="guan")])
    loaded = load_content(root).battles
    assert (loaded["siege_jia"].defender, loaded["siege_jia"].timetable_event, loaded["siege_jia"].version) == ("huang", "siege", "甲")
    assert (loaded["siege_yi"].front, loaded["siege_yi"].version) == ("south", "乙")


@pytest.mark.parametrize(("fields", "message"), [
    ({"timetable_event": "ghost"}, "未知的時刻表決戰 ghost"),  # 時刻表上要有這件大事
    ({"timetable_event": "raid", "version": None}, "未知的時刻表決戰 raid"),  # 而且是決戰
    ({"version": "丙"}, "version 丙 不是 siege 的版本"),  # 版本要是那件大事的版本之一
    ({"version": None}, "version None 不是 siege 的版本"),  # 有版本的大事每一筆都要寫版本
    ({"front": "nowhere"}, "未知的戰線 nowhere"),  # 戰線要是戰線 id
    ({"front": None}, "時刻表決戰要寫 front 與 defender"),  # 起點照戰線算、平手算守方贏
    ({"defender": None}, "時刻表決戰要寫 front 與 defender"),
    ({"factions": [{"id": "huang", "name": "黃巾"}, {"id": "guan", "name": "官軍"}]}, "陣營要依序是 guan、huang"),  # 官軍是正向
])
def test_timetable_showdown_fields_are_checked(tmp_path, fields, message):
    root = _with_timetable(tmp_path)
    write_battles_json(root, [_showdown_battle(**fields)])
    with pytest.raises(ContentError, match=message):
        load_content(root)


def test_a_timetable_showdown_version_has_only_one_battle(tmp_path):
    root = _with_timetable(tmp_path)
    write_battles_json(root, [_showdown_battle(), _showdown_battle(id="siege_jia2")])
    with pytest.raises(ContentError, match="時刻表決戰 siege 的 甲 版有兩筆戰鬥"):
        load_content(root)


def test_defender_is_guan_or_huang(tmp_path):
    root = _with_timetable(tmp_path)
    write_battles_json(root, [_showdown_battle(defender="haoqiang")])
    with pytest.raises(ContentError, match="defender"):
        load_content(root)


def test_location_desc_when_is_checked(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "locations.json", lambda d: d[0].update(desc_when=[{"world_flag": "", "text": "城頭換了旗。"}]))
    with pytest.raises(ContentError, match="desc_when"):
        load_content(root)
    edit_json(root / "locations.json", lambda d: d[0].update(desc_when=[{"world_flag": "fallen", "text": "城头换了旗。"}]))
    with pytest.raises(ContentError, match="繁體"):
        load_content(root)


# ── 第一季的結局與季末大事（計畫 T9）──────────────────────────


def _real_copy(tmp_path):
    """真實內容的一份副本（fixture 內容沒有第一季的結局與季末大事）。"""
    from pathlib import Path

    root = tmp_path / "content"
    shutil.copytree(Path(__file__).parent.parent / "content", root)
    return root


def test_stance_fields_only_on_season_one_endings(tmp_path):
    root = _real_copy(tmp_path)
    edit_json(root / "scenario.json", lambda d: d["endings"][0].update(stance_top="guan"))
    with pytest.raises(ContentError, match="第一季"):
        load_content(root)


def test_finale_fields_only_on_the_finale(tmp_path):
    root = _real_copy(tmp_path)
    edit_json(root / "timetable.json", lambda d: d[0].update(early_preface="提早了。"))
    with pytest.raises(ContentError, match="季末"):
        load_content(root)


def test_each_season_keeps_its_own_fallback_ending(tmp_path):
    """beta 季與第一季各自清單的最後一筆是保底：第一季多一筆有門檻的結局排在最後，就沒有保底。"""
    root = _real_copy(tmp_path)
    edit_json(root / "scenario.json", lambda d: d["endings"].append(
        {"id": "x", "season_one": True, "title": "多的", "text": "多的。", "stance_min": {"huang": 99}}))
    with pytest.raises(ContentError, match="保底"):
        load_content(root)


# ── 軍令（計畫 T6）──────────────────────────────────────────


def test_orders_slot_must_be_on_its_front(tmp_path):
    root = _real_copy(tmp_path)
    edit_json(root / "orders.json", lambda d: d["slots"]["yingru"]["guan"].update(intercept="nanyang_wilds"))
    with pytest.raises(ContentError, match="截糧"):
        load_content(root)


def test_orders_escort_must_end_at_a_base_of_its_side(tmp_path):
    root = _real_copy(tmp_path)
    edit_json(root / "orders.json", lambda d: d["slots"]["yingru"]["guan"].update(escort=["luoyang_road", "huangjin_camp"]))
    with pytest.raises(ContentError, match="護糧"):
        load_content(root)


def test_orders_personal_kind_must_match(tmp_path):
    root = _real_copy(tmp_path)
    edit_json(root / "orders.json", lambda d: d["templates"][0].update(personal="convoy"))
    with pytest.raises(ContentError, match="個人部分"):
        load_content(root)


def test_orders_text_slots_must_be_known(tmp_path):
    root = _real_copy(tmp_path)
    edit_json(root / "orders.json", lambda d: d["templates"][0].update(text="{將軍}傳令"))
    with pytest.raises(ContentError, match="插槽"):
        load_content(root)


def test_orders_convoy_squad_must_belong_to_its_side(tmp_path):
    root = _real_copy(tmp_path)
    edit_json(root / "orders.json", lambda d: d["convoy_squads"].update(guan="huang_grain_convoy"))
    with pytest.raises(ContentError, match="糧隊"):
        load_content(root)


def test_season_one_tutorial_steps_must_come_last(tmp_path):
    """存檔記的是第幾步：第一季才有的步驟插在中間，開關一開一關，同一個數字就指到不同的步驟（計畫 T6 Task 8）。"""
    root = copy_fixture(tmp_path)
    edit_json(root / "tutorial.json", lambda d: d["steps"][0].update(season_one=True))
    with pytest.raises(ContentError, match="排在最後"):
        load_content(root)


# ── 晉升（計畫 T5）──────────────────────────────────────────


def test_promote_only_on_promotion_scenes(tmp_path):
    root = _real_copy(tmp_path)
    edit_json(root / "events" / "general.json", lambda d: d[0]["choices"][0].setdefault("effect", {}).update(promote=2))
    with pytest.raises(ContentError, match="晉升奇遇"):
        load_content(root)


def test_promotion_followers_must_be_that_sides(tmp_path):
    root = _real_copy(tmp_path)
    edit_json(root / "events" / "promotion.json",
              lambda d: d[0]["choices"][0]["effect"].update(followers=["follower_huang_believer", "follower_guan_spear"]))
    with pytest.raises(ContentError, match="給的部下要是 guan 的"):
        load_content(root)


def test_promotion_handoff_needs_its_scene_and_summons(tmp_path):
    root = _real_copy(tmp_path)
    edit_json(root / "promotions.json", lambda d: d[0].update(summons_handoff=None))
    with pytest.raises(ContentError, match="接手"):
        load_content(root)


# ── 意境與基礎武學（武學與成長設計附錄 A～C）─────────────────


def test_insights_are_loaded(content):
    assert content.insights["feng"].attribute == "快"
    assert content.insights["haoran"].grant.stat == "good"


def test_a_location_insight_must_exist(content):
    content.locations["lake"].insights.append("nope")
    with pytest.raises(ContentError, match="未知的意境 nope"):
        validate(content)


def test_a_location_cannot_hand_out_a_name_earned_insight(content):
    content.locations["lake"].insights.append("haoran")
    with pytest.raises(ContentError, match="浩然.*只能靠名聲"):
        validate(content)


def test_an_effect_cannot_give_a_name_earned_insight(content):
    content.events["drunk"].choices[0].effect.insights = ["haoran"]
    with pytest.raises(ContentError, match="浩然.*只能靠名聲"):
        validate(content)


def test_an_effect_cannot_give_an_unknown_insight(content):
    content.events["drunk"].choices[0].effect.insights = ["nope"]
    with pytest.raises(ContentError, match="未知的意境 nope"):
        validate(content)


def test_an_effect_can_give_a_basic_insight(content):
    content.events["drunk"].choices[0].effect.insights = ["feng"]
    validate(content)


def test_a_basic_art_must_be_taught_somewhere_that_exists(content):
    content.skills["lake_kick"].learn.at = "nowhere"
    with pytest.raises(ContentError, match="未知的地點 nowhere"):
        validate(content)


def test_a_historical_art_is_not_taught(content):
    content.skills["fist"].learn = content.skills["lake_kick"].learn
    with pytest.raises(ContentError, match="絕學.*不能在各地學"):
        validate(content)


def test_starter_skills_are_one_inner_and_one_outer_art(content):
    content.config.starter_skills = ["basic_fist", "lake_kick"]
    with pytest.raises(ContentError, match="starter_skills"):
        validate(content)


def test_real_content_has_seventeen_basic_arts_and_every_location_an_insight():
    real = load_content(ROOT / "content")
    basics = [s for s in real.skills.values() if s.quality == "下品"]
    assert len(basics) == 17
    assert all(loc.insights for loc in real.locations.values())


def test_every_insight_fallback_name_passes_the_filter(content):
    for prefix in content.craft_names.prefixes:
        for suffix in content.craft_names.insight:
            assert naming.name_problem(prefix + suffix, content) is None


def test_validate_checks_the_insight_fallback_names_too(content):
    content.craft_names.insight = ["龍"]  # 「某某龍」之中有一個會撞上禁用詞時要在載入當下報錯
    content.banned_names = [content.craft_names.prefixes[0] + "龍"]
    with pytest.raises(ContentError, match="craft_names 組出的名字"):
        validate(content)
    content.craft_names.insight = []
    with pytest.raises(ContentError, match="craft_names.insight 不能是空的"):
        validate(content)


def test_check_voice_must_cover_every_checked_stat_and_run_high_to_low(tmp_path):
    """選項底下的人物心聲（content/check_voice.json）：每一檔都要說得出有人檢定的屬性，而且由高到低排。"""
    root = copy_fixture(tmp_path)
    voice = {"bands": [{"min_gap": 0, "lines": {"str": "{who}有把握。"}}, {"min_gap": 2, "lines": {"default": "穩。"}}]}
    (root / "check_voice.json").write_text(json.dumps(voice, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ContentError) as caught:
        load_content(root)
    assert "由高到低" in str(caught.value) and "con" in str(caught.value)  # 調息事件檢定根骨，第一檔沒寫



# ── check_voice.json：檢定選項括號裡的那一句（企劃者 2026-10-05 定案；S1 的 check_lines.json 已退休）──


def _voice_with(tmp_path, line: str, key: str = "default"):
    root = copy_fixture(tmp_path)
    voice = json.loads((root / "check_voice.json").read_text(encoding="utf-8"))
    voice["bands"][0]["lines"][key] = line
    (root / "check_voice.json").write_text(json.dumps(voice, ensure_ascii=False), encoding="utf-8")
    return root


@pytest.mark.parametrize("line", ["成功率 7 成。", "大概五成，七０％吧。", "七成%把握。", "有 ５ 分把握。"])
def test_a_check_voice_line_cannot_give_a_number_away(tmp_path, line):
    """只攔阿拉伯數字（半形、全形）與百分號：選項上不攤出成功率與難度。"""
    with pytest.raises(ContentError, match="數字"):
        load_content(_voice_with(tmp_path, line))


def test_chinese_numerals_are_fine_in_a_check_voice_line(tmp_path):
    load_content(_voice_with(tmp_path, "十拿九穩，難不倒{who}。"))


def test_a_check_voice_line_must_be_traditional_chinese(tmp_path):
    with pytest.raises(ContentError, match="繁體"):
        load_content(_voice_with(tmp_path, "这点力气，{who}使得出来。"))


def test_a_check_voice_line_cannot_be_blank(tmp_path):
    with pytest.raises(ContentError, match="空白"):
        load_content(_voice_with(tmp_path, "   "))


def test_a_check_voice_line_key_must_be_a_stat_or_default(tmp_path):
    with pytest.raises(ContentError, match="strength"):
        load_content(_voice_with(tmp_path, "{who}有把握。", key="strength"))


def test_check_voice_needs_at_least_one_band(tmp_path):
    root = copy_fixture(tmp_path)
    (root / "check_voice.json").write_text(json.dumps({"bands": []}), encoding="utf-8")
    with pytest.raises(ContentError, match="check_voice"):
        load_content(root)


def test_a_missing_or_malformed_check_voice_is_a_content_error_that_names_the_file(tmp_path):
    root = copy_fixture(tmp_path / "a")
    (root / "check_voice.json").unlink()
    with pytest.raises(ContentError, match="check_voice.json"):
        load_content(root)
    root = copy_fixture(tmp_path / "b")
    (root / "check_voice.json").write_text('{"bands": [', encoding="utf-8")
    with pytest.raises(ContentError, match="check_voice.json"):
        load_content(root)
    root = copy_fixture(tmp_path / "c")
    (root / "check_voice.json").write_text('{"bands": [], "voices": []}', encoding="utf-8")  # 拼錯的欄位
    with pytest.raises(ContentError, match="check_voice.json"):
        load_content(root)


# ── combat_lines.json：回合演出的句型（武學與成長設計 8.2、計畫三 Task 1；S1／Joy 照表手改）──


def test_combat_lines_cover_every_attribute(content):
    content.combat_lines.ours.pop("陰")
    with pytest.raises(ContentError, match="combat_lines.ours 缺少屬性 陰"):
        validate(content)


def _lines_with(tmp_path, fn):
    root = copy_fixture(tmp_path)
    edit_json(root / "combat_lines.json", fn)
    return root


@pytest.mark.parametrize(("where", "line", "complaint"), [
    ("ours", "连出数招", "繁體"),
    ("theirs", "掄起兵刃猛砸 3 下", "數字"),
    ("bare", "揮出１拳", "數字"),
    ("theirs_any", "   ", "空白"),
    ("ours", "以【旋風腿】搶攻", "【】"),
])
def test_a_combat_line_must_be_traditional_digit_free_and_not_blank(tmp_path, where, line, complaint):
    """句型接在人名（或「以【武學】」）後面、再接「，對手氣勢 -N」：寫數字會跟回合的數字攪在一起，寫【】會跟武學名撞在一起。"""
    def edit(data):
        if where in ("ours", "theirs"):
            data[where]["剛"].append(line)
        else:
            data[where].append(line)

    with pytest.raises(ContentError, match=complaint):
        load_content(_lines_with(tmp_path, edit))


def test_chinese_numerals_are_fine_in_a_combat_line(tmp_path):
    load_content(_lines_with(tmp_path, lambda d: d["ours"]["剛"].append("一步一步逼上前去")))


def test_a_missing_or_malformed_combat_lines_is_a_content_error_that_names_the_file(tmp_path):
    root = copy_fixture(tmp_path / "a")
    (root / "combat_lines.json").unlink()
    with pytest.raises(ContentError, match="combat_lines.json"):
        load_content(root)
    root = copy_fixture(tmp_path / "b")
    (root / "combat_lines.json").write_text('{"ours": {', encoding="utf-8")
    with pytest.raises(ContentError, match="combat_lines.json"):
        load_content(root)
    root = copy_fixture(tmp_path / "c")
    edit_json(root / "combat_lines.json", lambda d: d.update(their=[]))  # 拼錯的欄位
    with pytest.raises(ContentError, match="combat_lines.json"):
        load_content(root)
    root = copy_fixture(tmp_path / "d")
    edit_json(root / "combat_lines.json", lambda d: d["ours"].update(雷=["轟然一響"]))  # 不認得的屬性
    with pytest.raises(ContentError, match="combat_lines.json"):
        load_content(root)


def test_the_real_combat_lines_are_the_designers_table():
    """正式的句型照設計 session 的內容表（打發話與回合句型 §二，PM 2026-10-05 定）：我方每種屬性五句、對手每種屬性三句、
    沒學武學與沒有屬性的對手各三句；測試夾具留著計畫起手那一組。"""
    lines = load_content(ROOT / "content").combat_lines
    attributes = {"陰", "陽", "剛", "柔", "快", "慢", "虛", "實"}
    assert set(lines.ours) == attributes and all(len(v) == 5 for v in lines.ours.values())
    assert set(lines.theirs) == attributes and all(len(v) == 3 for v in lines.theirs.values())
    assert len(lines.bare) == 3 and len(lines.theirs_any) == 3
    assert "穩穩踏前一步，招式沉而不亂" in lines.ours["慢"] and "一個箭步衝到你面前" in lines.theirs["快"]


def test_s1s_check_lines_file_is_retired():
    """S1 的 check_lines.json（五段 45 句）由 joy 的 check_voice.json（四檔）取代：檔案、模型、載入、驗證都拿掉了。"""
    from tianxia import models

    assert not (ROOT / "content" / "check_lines.json").exists()
    assert not hasattr(models, "CheckLines")
    assert "check_lines" not in models.Content.model_fields


def test_old_content_with_by_on_a_check_still_loads_and_both_values_parse(content):
    """Check.by 讀得進來、不再有作用（每一個事件檢定都看本人的屬性）。"""
    assert content.events["drunk"].choices[0].check.by == "team"
    assert content.events["insight"].choices[0].check.by == "self"


# ── 博聞只靠升級的點數增加（設計 6.3；PM 2026-10-05）─────────────────────────
#
# 事件、奇遇、隨口應對、新手引導、路上見聞的獎勵都不能給博聞，也不能扣（連寫 0 都不行）；檢定可以照樣考博聞。


def _lore_in_choice(event, choice, field, amount):
    def put(root):
        edit_json(root / "events" / "test.json", lambda d: d[event]["choices"][choice].setdefault(field, {}).update(
            stats={"lore": amount}))
    return put


def _lore_in_free_text(field, amount):
    def put(root):
        free = {"prompt": "自己想辦法……", "stat": "str", "effect": {"text": "成了。"}, "fail_effect": {}}
        free[field] = {"stats": {"lore": amount}}
        edit_json(root / "events" / "test.json", lambda d: d[0].update(free_text=free))
    return put


def _lore_in_tutorial(root):
    edit_json(root / "tutorial.json", lambda d: d["steps"][1].update(reward={"stats": {"lore": 1}}))


def _lore_in_road_sight(root):
    edit_json(root / "road_sights.json", lambda d: d[1].update(effect={"stats": {"lore": 1}}))


LORE_PLACES = [
    pytest.param(_lore_in_choice(0, 0, "effect", 1), "事件 drunk 選項0", id="event-choice-effect"),
    pytest.param(_lore_in_choice(0, 0, "fail_effect", -1), "事件 drunk 選項0", id="event-choice-fail-effect-negative"),
    pytest.param(_lore_in_choice(0, 1, "effect", 0), "事件 drunk 選項1", id="event-choice-zero"),
    pytest.param(_lore_in_choice(1, 0, "effect", 2), "事件 scroll 選項0", id="qiyu"),
    pytest.param(_lore_in_free_text("effect", 1), "事件 drunk 隨口應對", id="free-text-effect"),
    pytest.param(_lore_in_free_text("fail_effect", -1), "事件 drunk 隨口應對", id="free-text-fail-effect"),
    pytest.param(_lore_in_tutorial, "新手引導 s2", id="tutorial-reward"),
    pytest.param(_lore_in_road_sight, "路上見聞 sight_wind", id="road-sight"),
]


@pytest.mark.parametrize("put_lore, where", LORE_PLACES)
def test_no_reward_anywhere_may_add_or_take_lore(tmp_path, put_lore, where):
    root = copy_fixture(tmp_path)
    put_lore(root)
    with pytest.raises(ContentError) as caught:
        load_content(root)
    lines = [line for line in str(caught.value).splitlines() if line.startswith(where) and "lore" in line]
    assert lines and all("博聞只能靠升級的點數增加" in line for line in lines), str(caught.value)
    assert len(lines) == 1, str(caught.value)  # 同一處只報一次，不連同別的規則一起吵


def test_a_check_may_still_test_lore(tmp_path):
    """事件檢定與隨口應對可以考博聞（看的是本人的點數），只是獎勵不能給。"""
    root = copy_fixture(tmp_path)
    edit_json(root / "events" / "test.json", lambda d: d[0]["choices"][0]["check"].update(stat="lore"))
    assert load_content(root).events["drunk"].choices[0].check.stat == "lore"


def test_the_free_text_and_bot_reward_lists_leave_lore_out():
    from tianxia import bot_policy, content

    assert "lore" not in content.FREE_TEXT_REWARDS and "lore" not in bot_policy.REWARD_STATS
    assert {"str", "agi", "con", "wis"} <= set(content.FREE_TEXT_REWARDS)  # 另外四項不動
