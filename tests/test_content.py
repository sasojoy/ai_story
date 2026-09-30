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


def test_negative_move_cost_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "locations.json", lambda d: d[1].update(move_cost=-1))
    with pytest.raises(ContentError, match="(?s)Location lake.*move_cost"):
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


# ── 名冊：同伴的品階、統御、取得管道 ─────────────────────


def by_id(items, ident):
    return next(item for item in items if item["id"] == ident)


def test_roster_fields_loaded(content):
    mate, sage = content.characters["mate"], content.characters["sage"]
    assert (mate.command, mate.sources, mate.recruit_at, mate.trait) == (3, ["開局"], [], None)
    assert (sage.tier, sage.command, sage.innate, sage.trait) == ("天", 7, "sky", "calm")
    assert content.characters["scholar"].recruit_at == ["town"]
    assert content.characters["thug"].command is None and content.characters["thug"].sources == []
    surrender = content.squads["boss"].surrender
    assert (surrender.character, surrender.chance) == ("captain", None)  # 省略機率時用 config.surrender_chance
    assert content.squads["thug"].surrender is None
    assert content.events["meet"].choices[0].effect.recruit == "friend"
    assert content.events["meet"].condition.members_none == ["friend"]
    assert content.events["fortune"].fortune and content.events["fortune"].actions == []
    cfg = content.config
    assert (cfg.team_counts, cfg.command_caps, cfg.player_command) == ([2, 3, 4], [15, 18, 20], 5)
    assert (cfg.apprentice_silver, cfg.apprentice_stamina, cfg.apprentice_per_day) == (40, 5, 2)
    assert cfg.apprentice_weights == {"黃": 75, "玄": 25} and cfg.surrender_chance == 0.25
    assert (cfg.fortune_day_min, cfg.fortune_day_max) == (2, 7)
    assert cfg.duplicate_xinde == {"黃": 10, "玄": 20, "地": 50, "天": 100}


ROSTER_ERRORS = [
    ("characters.json", lambda d: by_id(d, "mate").update(command=5), "人物 mate：玄品的統御要在 3～4（現在是 5）"),
    ("characters.json", lambda d: by_id(d, "mate").pop("command"), "人物 mate：玄品的統御要在 3～4（沒有填 command）"),
    ("characters.json", lambda d: by_id(d, "sage").update(command=5), "人物 sage：天品的統御要在 6～7"),
    ("characters.json", lambda d: by_id(d, "thug").update(command=2), "人物 thug：敵人不能有統御、取得管道、收徒地點或特性"),
    ("skills.json", lambda d: by_id(d, "palm").update(quality="中"), "人物 mate：玄品的本命要是下品（驚濤掌 是中品）"),
    ("characters.json", lambda d: by_id(d, "pupil").update(innate="fist"), "人物 pupil：黃品沒有本命武學"),
    ("characters.json", lambda d: by_id(d, "hero").pop("innate"), "人物 hero：地品要有本命武學"),
    ("characters.json", lambda d: by_id(d, "hero")["aptitude"].update(剛="S"), "人物 hero：地品的流派資質要剛好 1 項 S"),
    ("characters.json", lambda d: by_id(d, "sage")["aptitude"].update(巧="A"), "人物 sage：天品的流派資質要剛好 2 項 S"),
    ("characters.json", lambda d: by_id(d, "scholar")["aptitude"].update(巧="S"), "人物 scholar：玄品的流派資質最高 A"),
    ("characters.json", lambda d: by_id(d, "pupil")["aptitude"].update(快="A"), "人物 pupil：黃品的流派資質最高 B"),
    ("characters.json", lambda d: by_id(d, "sage").pop("trait"), "人物 sage：天品要有特性 trait"),
    ("characters.json", lambda d: by_id(d, "hero").update(trait="calm"), "人物 hero：只有天品有特性"),
    ("characters.json", lambda d: by_id(d, "sage").update(trait="fist"), "人物 sage：特性 fist 要是效果固定（不寫 top）的心法"),
    ("characters.json", lambda d: by_id(d, "sage").update(trait="breath"), "人物 sage：特性 breath 要是效果固定（不寫 top）的心法"),
    ("characters.json", lambda d: by_id(d, "mate").update(sources=[]), "人物 mate：同伴要寫取得管道 sources"),
    ("characters.json", lambda d: by_id(d, "pupil").update(sources=["招賢"]), "人物 pupil：至少要有一條招賢以外的免費管道"),
    ("characters.json", lambda d: by_id(d, "pupil")["sources"].append("開局"), "人物 pupil：「開局」管道要和 config.start_companions 一致"),
    ("characters.json", lambda d: by_id(d, "pupil")["sources"].append("福緣"), "人物 pupil：「福緣」管道只給地品"),
    ("characters.json", lambda d: by_id(d, "hero")["sources"].append("收徒"), "人物 hero：「收徒」管道只給黃品、玄品"),
    ("characters.json", lambda d: by_id(d, "scholar").update(recruit_at=["lake"]), "人物 scholar：收徒地點 lake 不是城鎮或門派"),
    ("characters.json", lambda d: by_id(d, "scholar").update(recruit_at=["mars"]), "人物 scholar：未知的地點 mars"),
    ("characters.json", lambda d: by_id(d, "friend").update(recruit_at=["town"]), "人物 friend：有收徒地點 recruit_at 就要有「收徒」管道"),
    ("squads.json", lambda d: by_id(d, "boss").update(surrender={"character": "ghost"}), "敵方隊伍 boss：未知的人物 ghost"),
    ("squads.json", lambda d: by_id(d, "boss").update(surrender={"character": "thug"}), "敵方隊伍 boss：招降的 thug 不是同伴"),
    ("squads.json", lambda d: by_id(d, "boss").update(surrender={"character": "hero"}), "敵方隊伍 boss：招降帶來的 hero 要有「招降」管道"),
    ("squads.json", lambda d: by_id(d, "boss").pop("surrender"), "人物 captain：「招降」管道沒有敵方隊伍帶得來"),
    ("events/test.json", lambda d: by_id(d, "meet")["condition"].update(members_none=[]), "事件 meet：結識 friend 的事件，condition.members_none 要列出 friend"),
    ("events/test.json", lambda d: by_id(d, "meet")["condition"].update(members_none=["ghost"]), "事件 meet：未知的人物 ghost"),
    ("events/test.json", lambda d: by_id(d, "meet")["choices"][0]["effect"].update(recruit="thug"), "事件 meet 選項0：結識的 thug 不是同伴"),
    ("events/test.json", lambda d: by_id(d, "hermit").update(qiyu=False), "事件 hermit：交遊帶來的 sage 要有「交遊」管道"),
    ("events/test.json", lambda d: by_id(d, "hermit").update(qiyu=False), "人物 sage：「奇遇」管道沒有事件帶得來"),
    ("events/test.json", lambda d: by_id(d, "fortune").update(actions=["socialize"]), "事件 fortune：福緣事件只由交遊觸發，actions 要是空的"),
    ("events/test.json", lambda d: by_id(d, "fortune")["choices"].append({"text": "婉拒"}), "事件 fortune：福緣事件的每個選項都要結識一個人"),
    ("events/test.json", lambda d: by_id(d, "fortune")["choices"][0].update(combat="thug"), "事件 fortune 選項0：福緣事件的選項不能有檢定或戰鬥"),
    ("events/test.json", lambda d: by_id(d, "fortune")["choices"][0].update(check={"stat": "wis", "difficulty": 5}), "事件 fortune 選項0：福緣事件的選項不能有檢定或戰鬥"),
    ("config.json", lambda d: d.update(team_counts=[2, 3]), "config.team_counts 與 config.command_caps 要一樣長"),
    ("config.json", lambda d: d.update(command_caps=[15, 20, 18]), "config.team_counts 與 config.command_caps 不能遞減"),
    ("config.json", lambda d: d.update(apprentice_weights={"地": 10}), "config.apprentice_weights：未知的品階 地"),
    ("config.json", lambda d: d.update(duplicate_xinde={"黃": 10}), "config.duplicate_xinde 要寫齊天地玄黃"),
]


@pytest.mark.parametrize("filename, edit, message", ROSTER_ERRORS)
def test_roster_content_errors_name_the_culprit(tmp_path, filename, edit, message):
    root = copy_fixture(tmp_path)
    edit_json(root / filename, edit)
    with pytest.raises(ContentError, match=message):
        load_content(root)


def test_at_least_one_fortune_di_tier_is_required(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "characters.json", lambda d: by_id(d, "hero").update(sources=["招賢", "奇遇"]))
    with pytest.raises(ContentError, match="至少要有一名標了「福緣」的地品"):
        load_content(root)


# ── 招賢（1c-3）──────────────────────────────────────────


def test_gacha_config_defaults(content):
    cfg = content.config
    assert (cfg.gacha_single, cfg.gacha_ten, cfg.gacha_pity, cfg.gacha_ten_floor) == (100, 1000, 40, "地")
    assert cfg.gacha_rates == {"天": 3, "地": 12, "玄": 35, "黃": 50}
    assert (cfg.gacha_xinde_half, cfg.gacha_xinde_cap) == (150, 300)
    assert cfg.gacha_silver == {"黃": 10, "玄": 20, "地": 50, "天": 100}
    assert cfg.test_yuanbao == 1000 and cfg.provisional == []


GACHA_ERRORS = [
    ("config.json", lambda d: d.update(gacha_rates={"天": 3, "地": 12, "玄": 35, "黃": 40}), "config.gacha_rates 要寫齊天地玄黃、不能是負的，加起來是 100"),
    ("config.json", lambda d: d.update(gacha_rates={"天": 3, "地": 12, "玄": 85}), "config.gacha_rates 要寫齊天地玄黃"),
    ("config.json", lambda d: d.update(gacha_rates={"天": 0, "地": 15, "玄": 35, "黃": 50}), "config.gacha_rates：天品的機率要大於 0（保底必得天品）"),
    ("characters.json", lambda d: by_id(d, "hero")["sources"].remove("招賢"), "config.gacha_rates：地品的機率大於 0，卡池裡卻沒有地品"),
    ("config.json", lambda d: d.update(gacha_ten_floor="敵"), "config.gacha_ten_floor：未知的品階 敵"),
    ("config.json", lambda d: d.update(gacha_silver={"天": 100}), "config.gacha_silver 要寫齊天地玄黃"),
    ("config.json", lambda d: d.update(gacha_silver={"黃": -1, "玄": 20, "地": 50, "天": 100}), "config.gacha_silver 的銀兩不能是負的"),
    ("config.json", lambda d: d.update(duplicate_xinde={"黃": 10, "玄": -20, "地": 50, "天": 100}), "config.duplicate_xinde 的心得不能是負的"),
    ("config.json", lambda d: d.update(gacha_pity=0), "config.gacha_single、gacha_ten、gacha_pity 至少要是 1"),
    ("config.json", lambda d: d.update(test_yuanbao=0), "config.test_yuanbao 至少要是 1"),
    ("config.json", lambda d: d.update(gacha_xinde_half=400), "config.gacha_xinde_half 要在 0 到 gacha_xinde_cap 之間"),
    ("config.json", lambda d: d.update(provisional=["gacha_price"]), "config.provisional：未知的設定 gacha_price"),
]


@pytest.mark.parametrize("filename, edit, message", GACHA_ERRORS)
def test_gacha_content_errors_name_the_culprit(tmp_path, filename, edit, message):
    root = copy_fixture(tmp_path)
    edit_json(root / filename, edit)
    with pytest.raises(ContentError, match=message):
        load_content(root)
