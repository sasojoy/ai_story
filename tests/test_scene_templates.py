import json
import random

from src.models import NPCProfile
from src.scene_templates import (
    SceneTemplateEntry,
    SceneTemplateVariant,
    fill_scene_template_beats,
    find_matching_templates,
    has_beats,
    load_scene_templates,
    select_template,
    substitute_names,
)


def _profile(character_tags):
    return NPCProfile(
        name="測試角色", identity="測試身份", personality="測試性格",
        location="測試地點", character_tags=character_tags,
    )


def test_find_matching_templates_requires_subset_of_character_tags():
    templates = {
        "act_a": SceneTemplateEntry(required_tags=["巨乳"], variants=[SceneTemplateVariant(text="x")]),
        "act_b": SceneTemplateEntry(required_tags=["巨乳", "嬌小"], variants=[SceneTemplateVariant(text="y")]),
    }
    matches = find_matching_templates(_profile(["巨乳"]), templates)
    assert [name for name, _ in matches] == ["act_a"]


def test_find_matching_templates_skips_entries_without_variants():
    templates = {"act_a": SceneTemplateEntry(required_tags=[], variants=[])}
    assert find_matching_templates(_profile([]), templates) == []


def test_select_template_returns_none_when_nothing_matches():
    assert select_template(_profile([]), {}) is None


def test_select_template_returns_deterministic_choice_with_seeded_rng():
    templates = {
        "act_a": SceneTemplateEntry(required_tags=[], variants=[SceneTemplateVariant(text="固定內容")]),
    }
    result = select_template(_profile([]), templates, rng=random.Random(0))
    assert result == ("act_a", "固定內容")


def test_substitute_names_replaces_both_placeholders():
    profile = NPCProfile(
        name="測試", display_name="小測", identity="測試身份",
        personality="測試性格", location="測試地點",
    )
    text = "{name}望向{player_name}。"
    assert substitute_names(text, profile, "楚留香") == "小測望向楚留香。"


def test_substitute_names_falls_back_to_name_when_no_display_name():
    profile = _profile([])
    text = "{name}"
    assert substitute_names(text, profile, "楚留香") == "測試角色"


def test_has_beats_detects_marker():
    assert has_beats("前文{beat:opening}後文")
    assert not has_beats("完全沒有插槽的文字")


def test_fill_scene_template_beats_replaces_each_slot_in_order():
    calls = []

    def generate_beat(prefix):
        calls.append(prefix)
        return f"[填充{len(calls)}]"

    text = "開頭{beat:opening}中段{beat:reaction}結尾"
    result = fill_scene_template_beats(text, generate_beat)

    assert result == "開頭[填充1]中段[填充2]結尾"
    # 第二個插槽拿到的前綴應該包含第一個插槽已經填好的內容，而不是原始的 {beat:opening}
    assert "[填充1]" in calls[1]
    assert "{beat:opening}" not in calls[1]


def test_fill_scene_template_beats_allows_empty_generation_to_drop_slot():
    result = fill_scene_template_beats("開頭{beat:opening}結尾", lambda prefix: "")
    assert result == "開頭結尾"


def test_load_scene_templates_returns_empty_dict_when_file_missing():
    assert load_scene_templates("config/does_not_exist_scene_templates.json") == {}


def test_load_scene_templates_skips_malformed_entries(tmp_path):
    path = tmp_path / "scene_templates.json"
    path.write_text(
        json.dumps({
            "good_act": {"required_tags": ["巨乳"], "variants": [{"text": "ok"}]},
            "bad_act": {"variants": "這不是一個合法的 variants 格式"},
        }),
        encoding="utf-8",
    )
    templates = load_scene_templates(str(path))
    assert list(templates.keys()) == ["good_act"]
