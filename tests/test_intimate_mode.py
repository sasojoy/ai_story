from src.intimate_mode import (
    TAG_ACQUISITION_PROBABILITY,
    attempt_intimate_action,
    compute_success_probability,
    list_intimate_actions,
)
from src.models import NPCProfile
from src.scene_templates import SceneTemplateEntry, SceneTemplateVariant


def _profile(intimacy=0, character_tags=None):
    return NPCProfile(
        name="測試角色", identity="測試身份", personality="測試性格",
        location="測試地點", intimacy=intimacy, character_tags=character_tags or [],
    )


class _FakeRng:
    """完全可控的假 rng：random() 依序回傳 queue 裡的值，choice() 永遠回傳序列第一個
    元素，讓測試能精確控制 attempt_intimate_action 內部兩次擲骰的結果。"""

    def __init__(self, random_values):
        self._values = list(random_values)

    def random(self):
        return self._values.pop(0)

    def choice(self, seq):
        return seq[0]


def test_compute_success_probability_boundaries():
    assert compute_success_probability(-50) == 0.05
    assert compute_success_probability(80) == 0.95
    assert 0.05 < compute_success_probability(15) < 0.95


def test_compute_success_probability_clamps_out_of_range_intimacy():
    assert compute_success_probability(-999) == 0.05
    assert compute_success_probability(999) == 0.95


def test_list_intimate_actions_delegates_to_find_matching_templates():
    templates = {
        "act_a": SceneTemplateEntry(required_tags=["巨乳"], variants=[SceneTemplateVariant(text="x")]),
        "act_b": SceneTemplateEntry(required_tags=[], applicable_endings=["bad"], variants=[SceneTemplateVariant(text="y")]),
    }
    profile = _profile(character_tags=["巨乳"])
    matches = list_intimate_actions(profile, templates, "good")
    assert [name for name, _ in matches] == ["act_a"]


def test_attempt_action_without_check_always_succeeds():
    entry = SceneTemplateEntry(requires_check=False, variants=[SceneTemplateVariant(text="{name}被親吻了。")])
    profile = _profile()
    result = attempt_intimate_action(profile, entry, "楚留香", generate_beat=lambda p: "", rng=_FakeRng([0.0]))
    assert result.success is True
    assert result.tag_granted is None
    assert "被親吻了" in result.narrative


def test_attempt_action_with_existing_check_tag_always_succeeds_without_rolling():
    entry = SceneTemplateEntry(
        requires_check=True, check_tag="喜歡口交",
        variants=[SceneTemplateVariant(text="{name}主動了。")],
    )
    profile = _profile(character_tags=["喜歡口交"])
    # rng 的 queue 是空的：如果程式碼真的去擲骰會直接 IndexError，藉此證明
    # 有 check_tag 保底時完全不會呼叫 rng.random()。
    result = attempt_intimate_action(profile, entry, "楚留香", generate_beat=lambda p: "", rng=_FakeRng([]))
    assert result.success is True
    assert result.tag_granted is None
    assert "主動了" in result.narrative


def test_attempt_action_without_check_tag_success_can_grant_tag():
    entry = SceneTemplateEntry(
        requires_check=True, check_tag="喜歡口交",
        variants=[SceneTemplateVariant(text="{name}答應了。")],
    )
    profile = _profile(intimacy=80, character_tags=[])
    # 第一次 random() 判定成功機率（0.0 < 任何成功機率都成功），第二次 random() 判定
    # 是否習得標籤（0.0 < TAG_ACQUISITION_PROBABILITY 一定成功）。
    result = attempt_intimate_action(profile, entry, "楚留香", generate_beat=lambda p: "", rng=_FakeRng([0.0, 0.0]))
    assert result.success is True
    assert result.tag_granted == "喜歡口交"
    assert "喜歡口交" in profile.character_tags


def test_attempt_action_without_check_tag_success_can_fail_to_grant_tag():
    entry = SceneTemplateEntry(
        requires_check=True, check_tag="喜歡口交",
        variants=[SceneTemplateVariant(text="{name}答應了。")],
    )
    profile = _profile(intimacy=80, character_tags=[])
    # 成功判定 0.0 過關，但習得標籤的第二次擲骰用 0.999（高於 TAG_ACQUISITION_PROBABILITY）判定不習得。
    result = attempt_intimate_action(
        profile, entry, "楚留香", generate_beat=lambda p: "",
        rng=_FakeRng([0.0, TAG_ACQUISITION_PROBABILITY + 0.01]),
    )
    assert result.success is True
    assert result.tag_granted is None
    assert "喜歡口交" not in profile.character_tags


def test_attempt_action_without_check_tag_can_fail_and_uses_refusal_text():
    entry = SceneTemplateEntry(
        requires_check=True, check_tag="喜歡口交",
        variants=[SceneTemplateVariant(text="{name}答應了。")],
    )
    profile = _profile(intimacy=-50, character_tags=[])
    # compute_success_probability(-50) == 0.05，用 0.99 一定判定失敗。
    result = attempt_intimate_action(profile, entry, "楚留香", generate_beat=lambda p: "", rng=_FakeRng([0.99]))
    assert result.success is False
    assert result.tag_granted is None
    assert "答應了" not in result.narrative
    assert "喜歡口交" not in profile.character_tags


def test_failed_finisher_action_does_not_report_is_finisher():
    """要求型的收尾動作被拒絕時，性愛模式不該就此結束——玩家得換個方式或再試一次。"""
    entry = SceneTemplateEntry(
        requires_check=True, check_tag="喜歡口交", is_finisher=True,
        variants=[SceneTemplateVariant(text="{name}答應了。")],
    )
    profile = _profile(intimacy=-50, character_tags=[])
    result = attempt_intimate_action(profile, entry, "楚留香", generate_beat=lambda p: "", rng=_FakeRng([0.99]))
    assert result.success is False
    assert result.is_finisher is False


def test_successful_finisher_action_reports_is_finisher():
    entry = SceneTemplateEntry(requires_check=False, is_finisher=True, variants=[SceneTemplateVariant(text="收尾。")])
    profile = _profile()
    result = attempt_intimate_action(profile, entry, "楚留香", generate_beat=lambda p: "", rng=_FakeRng([]))
    assert result.success is True
    assert result.is_finisher is True


def test_attempt_action_fills_beats_with_provided_generator():
    entry = SceneTemplateEntry(requires_check=False, variants=[SceneTemplateVariant(text="開頭{beat:opening}結尾")])
    profile = _profile()
    result = attempt_intimate_action(
        profile, entry, "楚留香", generate_beat=lambda prefix: "[填充]", rng=_FakeRng([]),
    )
    assert result.narrative == "開頭[填充]結尾"
