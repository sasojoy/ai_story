from random import Random
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


def test_the_prompt_asks_for_a_short_reply(content, state, world):
    """企劃者 2026-10-03：每輪控制在兩三句，縮短等待（gemma4:26b 每輪原本約 11 秒）。"""
    prompt = companion_agent.build_system_prompt(content.characters["mate"], state, content, world, "mate")
    assert "兩三句" in prompt and "80~150 字" in prompt
    assert "100~200 字" not in prompt


# ── 鎖外生成（對話輪次先在鎖外生成，再進鎖套用）──────────────────

FAKE_TURN = companion_agent.CompanionTurn(
    narrative="他點了點頭。", options=["閒聊幾句", "就此告辭"], option_tags=["尋常寒暄", "雪中送炭"],
)


def test_start_dialogue_applies_a_given_turn_without_a_client(content, state, world):
    """給了現成的一輪就不再生成：沒有模型（client=None）也能開始對話；不給時照舊拋 DialogueUnavailable。"""
    msgs = companion_agent.start_dialogue(None, state, content, world, "mate", Random(0), turn=FAKE_TURN)
    assert msgs == ["他點了點頭。"]
    assert state.player.pending_companion == "mate"
    assert state.player.last_offered_dialogue["mate"] == [["閒聊幾句", "就此告辭"], ["尋常寒暄", "雪中送炭"]]
    with pytest.raises(companion_agent.DialogueUnavailable):
        companion_agent.start_dialogue(None, state, content, world, "mate", Random(0))


def test_continue_dialogue_applies_a_given_turn_without_a_client(content, state, world):
    state.player.pending_companion = "mate"
    state.player.last_offered_dialogue["mate"] = [["誇他兩句", "告辭"], ["雪中送炭", "尋常寒暄"]]
    msgs = companion_agent.continue_dialogue(None, state, content, world, "mate", 0, Random(0), turn=FAKE_TURN)
    assert msgs == ["他點了點頭。", "（情誼 +8）"]  # 情誼（程式裡叫好感度）照玩家選的選項（上一輪的 tag）查表
    assert state.player.affinities["mate"] == 8
    assert state.player.dialogue_history["mate"][0] == {"role": "user", "content": "誇他兩句"}
    assert world.read().companion_tag_counts["mate"] == {"雪中送炭": 1}


def test_a_given_turn_skips_generation_entirely(content, state, world):
    state.player.last_offered_dialogue["mate"] = [["閒聊幾句"], ["尋常寒暄"]]
    with mock.patch.object(companion_agent, "_generate", side_effect=AssertionError("不該生成")), \
            mock.patch.object(companion_agent, "generate_turn", side_effect=AssertionError("不該生成")):
        companion_agent.start_dialogue(None, state, content, world, "mate", Random(0), turn=FAKE_TURN)
        companion_agent.continue_dialogue(None, state, content, world, "mate", 0, Random(0), turn=FAKE_TURN)


def test_generate_turn_converts_simplified_text_to_traditional():
    client = mock.Mock()
    client.chat_structured.return_value = companion_agent.CompanionTurn(
        narrative="他说这话时闪过一丝笑意。", options=["说几句话", "告辞", "听他说"],
        option_tags=["由衷讚赏", "尋常寒暄", "尋常寒暄"], relationship_note_update="关系还算融洽",
    )
    messages = [{"role": "user", "content": "hi"}]
    turn = companion_agent.generate_turn(client, messages)
    assert client.chat_structured.call_args.args[0] == messages
    assert turn.narrative == "他說這話時閃過一絲笑意。"
    assert turn.options == ["說幾句話", "告辭", "聽他說"]
    assert turn.option_tags[0] == "由衷讚賞"
    assert turn.relationship_note_update == "關係還算融洽"


def test_generate_turn_raises_dialogue_unavailable_when_the_client_fails_or_is_missing():
    client = mock.Mock()
    client.chat_structured.side_effect = RuntimeError("模型 'gemma4:26b' 未找到")
    with pytest.raises(companion_agent.DialogueUnavailable):
        companion_agent.generate_turn(client, [])
    with pytest.raises(companion_agent.DialogueUnavailable):
        companion_agent.generate_turn(None, [])


def test_generate_is_build_messages_plus_generate_turn(content, state, world):
    """_generate 只是 _build_messages 加 generate_turn：鎖外與鎖內走同一條生成路徑。"""
    character = content.characters["mate"]
    expected = companion_agent._build_messages(character, state, content, world, "mate", "閒聊幾句")
    with mock.patch.object(companion_agent, "generate_turn", return_value=FAKE_TURN) as gen:
        turn = companion_agent._generate(mock.Mock(), character, state, content, world, "mate", "閒聊幾句")
    assert turn is FAKE_TURN
    assert gen.call_args.args[1] == expected


def test_build_request_carries_the_same_messages_generate_would_send(content, state, world):
    request = companion_agent.build_request(state, content, world, "mate", "talk:0", "閒聊幾句")
    assert (request.option_id, request.companion_id, request.player_action) == ("talk:0", "mate", "閒聊幾句")
    assert request.messages == companion_agent._build_messages(
        content.characters["mate"], state, content, world, "mate", "閒聊幾句",
    )


def test_prepare_turn_wraps_the_outcome_and_marks_failure_with_no_turn(content, state, world):
    request = companion_agent.build_request(state, content, world, "mate", "talk:0", "閒聊幾句")
    with mock.patch.object(companion_agent, "generate_turn", return_value=FAKE_TURN) as gen:
        prepared = companion_agent.prepare_turn(mock.Mock(), request)
    assert gen.call_args.args[1] == request.messages
    assert prepared == companion_agent.PreparedTurn("talk:0", "mate", "閒聊幾句", FAKE_TURN)
    with mock.patch.object(companion_agent, "generate_turn", side_effect=companion_agent.DialogueUnavailable("404")):
        failed = companion_agent.prepare_turn(mock.Mock(), request)
    assert failed == companion_agent.PreparedTurn("talk:0", "mate", "閒聊幾句", None)


def test_prepare_turn_logs_which_companion_failed(content, state, world, caplog):
    request = companion_agent.build_request(state, content, world, "mate", "talk:0", "閒聊幾句")
    with mock.patch.object(companion_agent, "generate_turn", side_effect=companion_agent.DialogueUnavailable("連不上")), \
            caplog.at_level("WARNING", logger="tianxia.companion_agent"):
        companion_agent.prepare_turn(mock.Mock(), request)
    assert any("mate" in r.getMessage() and "連不上" in r.getMessage() for r in caplog.records)


# ── 上一季的交情（第一季設計第十四節；正式版辛）─────────────────


def test_the_prompt_carries_last_seasons_bond_separately(content, state, world):
    state.player.past_notes = {"mate": "曾在潁川並肩殺敵"}
    state.player.affinities = {"mate": 8}
    prompt = companion_agent.build_system_prompt(content.characters["mate"], state, content, world, "mate")
    assert "【上一季】你們以前的交情：曾在潁川並肩殺敵。" in prompt
    assert "交情淡了" in prompt and "先前" in prompt and "上回" in prompt
    assert "目前好感度 8" in prompt and "你與玩家目前的關係現況：還沒交談過" in prompt


def test_the_past_line_does_not_double_the_full_stop(content, state, world):
    """關係筆記通常自己就以句號結尾（模型寫的、退路那句都是）：【上一季】那句不再補一個。"""
    state.player.past_notes = {"mate": "曾在潁川並肩殺敵。"}
    prompt = companion_agent.build_system_prompt(content.characters["mate"], state, content, world, "mate")
    assert "你們以前的交情：曾在潁川並肩殺敵。你仍記得" in prompt


def test_the_past_section_tells_the_model_not_to_say_season(content, state, world):
    """「季」是遊戲的說法，不是漢末的人會講的話：【上一季】那一段叫模型提舊事時說先前、上回，別把這一季、上一季帶進對白。
    那一段自己的敘述（給模型看的）也不再寫「這一季」。"""
    state.player.past_notes = {"mate": "曾在潁川並肩殺敵"}
    prompt = companion_agent.build_system_prompt(content.characters["mate"], state, content, world, "mate")
    section = next(line for line in prompt.splitlines() if line.startswith("【上一季】"))
    assert "「先前」" in section and "「上回」" in section
    assert "不要說「這一季」「上一季」" in section
    assert section.count("這一季") == 1 and section.count("上一季") == 2  # 只剩那句禁令裡的各一次（標題那個「上一季」另算）


def test_the_prompt_never_says_season_to_the_model(content, state, world):
    """「季」是遊戲的說法：沒有【上一季】那一段的提示（第一季的玩家、沒聊過的人物）裡，連「這一季」「上一季」都不出現，
    模型就沒有字可以學去講進對白；有那一段時，這兩個詞只出現在「不要說」的那一句裡。"""
    prompt = companion_agent.build_system_prompt(content.characters["mate"], state, content, world, "mate")
    assert "這一季" not in prompt and "上一季" not in prompt and "關係現況：還沒交談過" in prompt
    state.player.past_notes = {"mate": "曾在潁川並肩殺敵"}
    section = next(line for line in companion_agent.build_system_prompt(
        content.characters["mate"], state, content, world, "mate").splitlines() if line.startswith("【上一季】"))
    assert "不要說「這一季」「上一季」" in section


def test_no_past_section_without_past_notes(content, state, world):
    prompt = companion_agent.build_system_prompt(content.characters["mate"], state, content, world, "mate")
    assert "【上一季】" not in prompt
    state.player.past_notes = {"friend": "別人的舊事"}  # 別的人物有、這一位沒有：照樣不冒出空的段落
    prompt = companion_agent.build_system_prompt(content.characters["mate"], state, content, world, "mate")
    assert "【上一季】" not in prompt


def test_this_seasons_note_is_what_the_relationship_line_shows(content, state, world):
    state.player.past_notes = {"mate": "舊交"}
    state.player.relationship_notes = {"mate": "新結識的酒友"}
    prompt = companion_agent.build_system_prompt(content.characters["mate"], state, content, world, "mate")
    assert "你與玩家目前的關係現況：新結識的酒友" in prompt
    assert "【上一季】你們以前的交情：舊交。" in prompt


def test_the_model_only_sees_this_seasons_dialogue(content, state, world):
    old = [{"role": "user", "content": f"舊話{i}"} for i in range(5)]
    state.player.dialogue_history = {"mate": old + [{"role": "user", "content": "新話"}]}
    state.player.history_start = {"mate": 5}
    messages = companion_agent._build_messages(  # noqa: SLF001
        content.characters["mate"], state, content, world, "mate", "拱手",
    )
    said = [m["content"] for m in messages if m["role"] != "system"]
    assert said[0] == "新話" and not any(s.startswith("舊話") for s in said)


def test_trimming_the_history_moves_the_season_start_with_it(content, state, world):
    """對話紀錄只留最近 MAX_HISTORY_MESSAGES 則：前面被丟掉時，這一季從第幾則開始也要跟著往前挪，
    不然停在原來的數字會指到這一季的對話之後，模型就什麼都看不到了。"""
    old = [{"role": "user", "content": f"舊話{i}"} for i in range(companion_agent.MAX_HISTORY_MESSAGES)]
    state.player.dialogue_history = {"mate": old}
    state.player.history_start = {"mate": len(old)}  # 整份都是上一季的
    turn = companion_agent.CompanionTurn(narrative="他點了點頭。", options=["a", "b"], option_tags=["尋常寒暄", "尋常寒暄"])
    companion_agent._record_turn(state, "mate", "拱手", turn)  # noqa: SLF001
    assert len(state.player.dialogue_history["mate"]) == companion_agent.MAX_HISTORY_MESSAGES
    assert state.player.history_start["mate"] == companion_agent.MAX_HISTORY_MESSAGES - 2
    messages = companion_agent._build_messages(  # noqa: SLF001
        content.characters["mate"], state, content, world, "mate", "再拱手",
    )
    said = [m["content"] for m in messages if m["role"] != "system"]
    assert said[:2] == ["拱手", "他點了點頭。"] and not any(s.startswith("舊話") for s in said)


def test_consolidation_only_reads_this_seasons_dialogue(content, state, world):
    """每隔幾輪的記憶梳理也只讀這一季的對話：不然上一季的事會被寫進「這一季的關係」。"""
    p = state.player
    p.dialogue_history = {"mate": [{"role": "user", "content": "上一季的話"}, {"role": "user", "content": "這一季的話"}]}
    p.history_start = {"mate": 1}
    p.turns_since_consolidation = {"mate": companion_agent.MEMORY_CONSOLIDATION_INTERVAL}
    client = mock.Mock()
    client.chat_structured.return_value = companion_agent.MemoryConsolidation(
        relationship_summary="這一季的交情", new_milestones=["一件事"],
    )
    companion_agent._maybe_consolidate_memory(client, state, content.characters["mate"], "mate")  # noqa: SLF001
    sent = client.chat_structured.call_args.args[0][1]["content"]
    assert "這一季的話" in sent and "上一季的話" not in sent
    assert p.relationship_notes["mate"] == "這一季的交情"


def test_memory_consolidation_stores_a_cleaned_note(content, state):
    """FB-075 延伸：記憶整理的那句關係現況會餵回之後的對話，位元組碼與簡體字不能一路帶下去。"""
    p = state.player
    p.turns_since_consolidation["mate"] = companion_agent.MEMORY_CONSOLIDATION_INTERVAL
    p.dialogue_history["mate"] = [{"role": "user", "content": "你好"}, {"role": "assistant", "content": "他點了點頭。"}]
    client = mock.Mock()
    client.chat_structured.return_value = companion_agent.MemoryConsolidation(
        relationship_summary="他对你<0xE5><0xB7><0x8D>然敬重", new_milestones=["初次見面"])
    companion_agent._maybe_consolidate_memory(client, state, content.characters["mate"], "mate")
    assert p.relationship_notes["mate"] == "他對你巍然敬重"


def test_drift_synthesis_stores_a_cleaned_note(content, world):
    """FB-075 延伸：全服的性情漂移也餵回模型，同樣先清掉位元組碼、轉成繁體。"""
    ch = content.characters["mate"]
    for _ in range(companion_agent.DRIFT_SYNTHESIS_INTERVAL):
        world.record_companion_tag("mate", "雪中送炭")
    client = mock.Mock()
    client.chat_structured.return_value = DriftSynthesis(drift_note="他待人越来越<0xE5><0xB7><0x8D>然大方。")
    companion_agent._maybe_synthesize_drift(client, ch, "mate", world)
    assert world.get_companion_drift_note("mate") == "他待人越來越巍然大方。"
