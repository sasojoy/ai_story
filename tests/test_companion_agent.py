from unittest import mock

from tianxia import companion_agent
from tianxia.companion_agent import DriftSynthesis, resolve_tag_delta
from tianxia.world_state import WorldStateStore


# ── 好感度 tag 查表：個別人物覆寫（還要改進第 6 點）────────────────


def test_resolve_tag_delta_uses_the_shared_default_without_a_character():
    assert resolve_tag_delta("雪中送炭") == 8
    assert resolve_tag_delta("言語冒犯") == -6
    assert resolve_tag_delta("不存在的tag") == 0


def test_resolve_tag_delta_prefers_a_characters_override(content):
    ch = content.characters["mate"]
    ch.affinity_tag_deltas = {"雪中送炭": 99}
    assert resolve_tag_delta("雪中送炭", ch) == 99
    assert resolve_tag_delta("言語冒犯", ch) == -6  # 沒覆寫的 tag 照樣退回共用預設值


def test_resolve_tag_delta_ignores_a_characters_none_override(content):
    ch = content.characters["mate"]
    ch.affinity_tag_deltas = None
    assert resolve_tag_delta("雪中送炭", ch) == 8


# ── 性情漂移語意化（還要改進第 4 點）─────────────────────────────


def test_tag_counts_since_last_drift_starts_at_total_count(world):
    world.record_companion_tag("mate", "言語冒犯")
    world.record_companion_tag("mate", "言語冒犯")
    assert world.tag_counts_since_last_drift("mate") == 2


def test_record_drift_synthesis_resets_the_counter_to_the_total_at_that_moment(world):
    for _ in range(3):
        world.record_companion_tag("mate", "雪中送炭")
    world.record_drift_synthesis("mate", "他待人漸漸和善了起來。")
    assert world.tag_counts_since_last_drift("mate") == 0
    assert world.get_companion_drift_note("mate") == "他待人漸漸和善了起來。"
    world.record_companion_tag("mate", "雪中送炭")
    assert world.tag_counts_since_last_drift("mate") == 1  # 只算新累積的那一次


def test_maybe_synthesize_drift_does_nothing_below_the_interval(content, world):
    ch = content.characters["mate"]
    for _ in range(companion_agent.DRIFT_SYNTHESIS_INTERVAL - 1):
        world.record_companion_tag("mate", "尋常寒暄")
    client = mock.Mock()
    companion_agent._maybe_synthesize_drift(client, ch, "mate", world)
    client.chat_structured.assert_not_called()
    assert world.get_companion_drift_note("mate") == ""


def test_maybe_synthesize_drift_calls_the_llm_once_the_interval_is_reached(content, world):
    ch = content.characters["mate"]
    for _ in range(companion_agent.DRIFT_SYNTHESIS_INTERVAL):
        world.record_companion_tag("mate", "雪中送炭")
    client = mock.Mock()
    client.chat_structured.return_value = DriftSynthesis(drift_note="他待人越來越慷慨大方。")
    companion_agent._maybe_synthesize_drift(client, ch, "mate", world)
    client.chat_structured.assert_called_once()
    assert world.get_companion_drift_note("mate") == "他待人越來越慷慨大方。"
    assert world.tag_counts_since_last_drift("mate") == 0  # 門檻消耗掉了，不會下一輪又立刻觸發


def test_maybe_synthesize_drift_skips_without_a_client(content, world):
    ch = content.characters["mate"]
    for _ in range(companion_agent.DRIFT_SYNTHESIS_INTERVAL):
        world.record_companion_tag("mate", "雪中送炭")
    companion_agent._maybe_synthesize_drift(None, ch, "mate", world)
    assert world.get_companion_drift_note("mate") == ""


def test_maybe_synthesize_drift_leaves_the_note_unset_when_every_retry_fails(content, world):
    ch = content.characters["mate"]
    for _ in range(companion_agent.DRIFT_SYNTHESIS_INTERVAL):
        world.record_companion_tag("mate", "雪中送炭")
    client = mock.Mock()
    client.chat_structured.side_effect = RuntimeError("boom")
    companion_agent._maybe_synthesize_drift(client, ch, "mate", world)
    assert client.chat_structured.call_count == companion_agent.MAX_RETRIES
    assert world.get_companion_drift_note("mate") == ""
    assert world.tag_counts_since_last_drift("mate") == companion_agent.DRIFT_SYNTHESIS_INTERVAL  # 沒消耗門檻，下次還會再試
