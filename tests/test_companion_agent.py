from unittest import mock

import pytest

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


def test_generate_gives_up_when_no_model_can_answer(content, state, world):
    character = content.characters["mate"]
    with pytest.raises(companion_agent.DialogueUnavailable):
        companion_agent._generate(None, character, state, content, world, "mate", "閒聊幾句")
    client = mock.Mock()
    client.chat_structured.side_effect = RuntimeError("模型 'qwen2.5:14b' 未找到")
    with pytest.raises(companion_agent.DialogueUnavailable):
        companion_agent._generate(client, character, state, content, world, "mate", "閒聊幾句")


def test_the_prompt_anchors_the_era_and_forbids_later_events(content, state, world):
    content.scenario.era_note = "東漢靈帝光和七年（公元184年，年底改元中平），黃巾起事。諸葛亮還是孩童。"
    prompt = companion_agent.build_system_prompt(content.characters["mate"], state, content, world, "mate")
    assert "光和七年（公元184年，年底改元中平）" in prompt
    assert "不得提及之後" in prompt
    act = content.scenario.storylines[0].acts[0].title
    assert act in prompt


def test_the_prompt_keeps_the_player_in_the_second_person(content, state, world):
    prompt = companion_agent.build_system_prompt(content.characters["mate"], state, content, world, "mate")
    assert "稱呼玩家一律用「你」" in prompt
    assert "不要替玩家說話" in prompt


def test_generated_text_is_converted_to_traditional_chinese(content, state, world):
    client = mock.Mock()
    client.chat_structured.return_value = companion_agent.CompanionTurn(
        narrative="他说这话时闪过一丝笑意。", options=["说几句话", "告辞", "听他说"],
        option_tags=["尋常寒暄", "尋常寒暄", "尋常寒暄"], relationship_note_update="关系还算融洽",
    )
    turn = companion_agent._generate(client, content.characters["mate"], state, content, world, "mate", "閒聊幾句")
    assert turn.narrative == "他說這話時閃過一絲笑意。"
    assert turn.options[0] == "說幾句話"
    assert turn.relationship_note_update == "關係還算融洽"


def test_generated_tags_are_converted_so_the_affinity_lookup_still_matches(content, state, world):
    """模型有時把清單裡的 tag 寫成簡體（實機見過「由衷讚赏」）；查表是精確比對，不轉就會變成 0。"""
    client = mock.Mock()
    client.chat_structured.return_value = companion_agent.CompanionTurn(
        narrative="他點了點頭。", options=["夸他", "告辞", "闲聊"],
        option_tags=["由衷讚赏", "尋常寒暄", "尋常寒暄"],
    )
    turn = companion_agent._generate(client, content.characters["mate"], state, content, world, "mate", "閒聊幾句")
    assert turn.option_tags[0] == "由衷讚賞"
    assert resolve_tag_delta(turn.option_tags[0]) > 0


def test_every_dialogue_tag_survives_the_traditional_conversion_unchanged():
    from tianxia import zh

    assert [zh.to_traditional(t) for t in companion_agent.DIALOGUE_TAGS] == companion_agent.DIALOGUE_TAGS


def test_the_prompt_frames_the_figure_as_late_han_not_the_three_kingdoms(content, state, world):
    prompt = companion_agent.build_system_prompt(content.characters["mate"], state, content, world, "mate")
    assert "漢末真實歷史人物" in prompt
    assert "貼合漢末時代語境" in prompt
    assert "三國時代" not in prompt
