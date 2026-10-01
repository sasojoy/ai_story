import random
from unittest import mock

import pytest

from tianxia import battle_instance as bi
from tianxia.models import (
    BattleAct, BattleActionEffect, BattleAdvanceWhen, BattleDef, BattleFaction, BattleOption, BattleOutcome,
)


@pytest.fixture
def definition() -> BattleDef:
    return BattleDef(
        id="test_battle",
        name="測試決戰",
        factions=[BattleFaction(id="guan", name="官軍"), BattleFaction(id="huang", name="黃巾")],
        trend_start=50,
        acts=[
            BattleAct(
                id="a1", title="初探", text="雙方試探。", goal="推動戰局",
                options=[
                    BattleOption(text="穩紮穩打", tag="safe"),
                    BattleOption(text="全力進攻", tag="aggressive"),
                    BattleOption(text="單刀衝撞敵營", tag="reckless"),
                ],
                advance_when=BattleAdvanceWhen(trend_min=70),
            ),
            BattleAct(
                id="a2", title="決戰", text="最終決戰。", goal="決出勝負",
                options=[
                    BattleOption(text="穩紮穩打", tag="safe"),
                    BattleOption(text="全力進攻", tag="aggressive"),
                ],
                advance_when=None,
            ),
        ],
        action_tags={
            "safe": BattleActionEffect(trend_delta=1, neili_damage=5),
            "aggressive": BattleActionEffect(trend_delta=5, neili_damage=20, mitigated_by_power=True),
            "reckless": BattleActionEffect(trend_delta=10, neili_damage=200),
        },
        outcomes=[
            BattleOutcome(faction="guan", trend_min=70, title="官軍大勝", text="官軍獲勝。"),
            BattleOutcome(faction="huang", trend_max=30, title="黃巾得勝", text="黃巾獲勝。"),
            BattleOutcome(faction="guan", title="僵持", text="不分勝負。"),
        ],
        muster_seconds=600,
        round_seconds=120,
    )


# ── 集結期 ───────────────────────────────────────────────


def test_start_muster_seeds_trend_from_definition(definition):
    instance = bi.start_muster(definition, now=1000.0)
    assert instance.phase == "muster"
    assert instance.trend == 50
    assert instance.muster_deadline_real == 1600.0


def test_join_faction_during_muster(definition):
    instance = bi.start_muster(definition, now=0.0)
    bi.join_faction(instance, "甲", "guan", neili_cap=100.0)
    assert instance.participants["甲"].faction == "guan"
    assert instance.participants["甲"].neili == 100.0


def test_join_faction_after_muster_closed_is_ignored(definition):
    instance = bi.start_muster(definition, now=0.0)
    bi.close_muster(instance, definition, random.Random(0))
    bi.join_faction(instance, "甲", "guan", neili_cap=100.0)
    assert "甲" not in instance.participants


def test_close_muster_auto_assigns_a_faction_to_whoever_joined_without_choosing(definition):
    instance = bi.start_muster(definition, now=0.0)
    instance.participants["甲"] = bi.BattleParticipant(name="甲", faction="", neili=100, neili_cap=100)
    bi.close_muster(instance, definition, random.Random(0))
    assert instance.participants["甲"].faction in ("guan", "huang")
    assert instance.phase == "active"


def test_auto_assign_latecomer_balances_faction_sizes(definition):
    instance = bi.start_muster(definition, now=0.0)
    bi.join_faction(instance, "甲", "guan", neili_cap=100.0)
    bi.auto_assign_latecomer(instance, definition, "乙", neili_cap=100.0, rng=random.Random(0))
    assert instance.participants["乙"].faction == "huang"  # guan 已經有一人，平衡塞進人少的一方


# ── 回合鎖步 ─────────────────────────────────────────────


def _active_battle(definition) -> bi.BattleInstance:
    instance = bi.start_muster(definition, now=0.0)
    bi.join_faction(instance, "甲", "guan", neili_cap=100.0)
    bi.join_faction(instance, "乙", "huang", neili_cap=100.0)
    bi.close_muster(instance, definition, random.Random(0))
    return instance


def test_round_is_not_complete_until_everyone_submits(definition):
    instance = _active_battle(definition)
    assert not bi.round_is_complete(instance)
    bi.submit_action(instance, "甲", "safe")
    assert not bi.round_is_complete(instance)
    bi.submit_action(instance, "乙", "safe")
    assert bi.round_is_complete(instance)


def test_eliminated_participants_are_not_required_to_submit(definition):
    instance = _active_battle(definition)
    instance.participants["乙"].eliminated = True
    bi.submit_action(instance, "甲", "safe")
    assert bi.round_is_complete(instance)


def test_submit_action_from_an_eliminated_participant_is_ignored(definition):
    instance = _active_battle(definition)
    instance.participants["甲"].eliminated = True
    bi.submit_action(instance, "甲", "safe")
    assert "甲" not in instance.round.pending_actions


def test_fill_timed_out_actions_defaults_the_missing_ones(definition):
    instance = _active_battle(definition)
    bi.submit_action(instance, "甲", "aggressive")
    bi.fill_timed_out_actions(instance, definition, default_tag="safe")
    assert instance.round.pending_actions == {"甲": "aggressive", "乙": "safe"}


# ── 回合結算：trend / 氣血 / 出局 ──────────────────────────


def test_resolve_round_pushes_the_trend_and_drains_neili(definition):
    instance = _active_battle(definition)
    bi.submit_action(instance, "甲", "safe")
    bi.submit_action(instance, "乙", "safe")
    bi.resolve_round(instance, definition, random.Random(0))
    assert instance.trend == 52  # 兩人各 +1
    assert instance.participants["甲"].neili == 95
    assert instance.participants["乙"].neili == 95


def test_reckless_action_can_eliminate_a_participant_outright(definition):
    """單刀衝撞敵營這種框架內選項本身就設定成極高氣血損耗，一回合就能把人打到出局——
    不是程式特別判斷「這個行動很魯莽」，是內容本身的查表數字夠狠。"""
    instance = _active_battle(definition)
    bi.submit_action(instance, "甲", "reckless")
    bi.submit_action(instance, "乙", "safe")
    msgs = bi.resolve_round(instance, definition, random.Random(0))
    assert instance.participants["甲"].eliminated
    assert instance.participants["甲"].neili == 0
    assert any("氣血耗盡" in m for m in msgs)


def test_eliminated_participant_is_excluded_from_the_next_rounds_requirement(definition):
    instance = _active_battle(definition)
    bi.submit_action(instance, "甲", "reckless")
    bi.submit_action(instance, "乙", "safe")
    bi.resolve_round(instance, definition, random.Random(0))
    bi.submit_action(instance, "乙", "safe")
    assert bi.round_is_complete(instance)  # 甲已出局，不用等他


def test_mitigated_by_power_reduces_damage_for_a_powerful_participant(definition):
    instance = _active_battle(definition)
    bi.submit_action(instance, "甲", "aggressive")
    bi.submit_action(instance, "乙", "aggressive")
    bi.resolve_round(instance, definition, random.Random(0), power_of=lambda name: 100 if name == "甲" else None)
    assert instance.participants["甲"].neili > instance.participants["乙"].neili


def test_options_for_returns_only_this_participants_available_options(definition):
    instance = _active_battle(definition)
    opts = bi.options_for(instance, definition, "甲")
    assert {o.tag for o in opts} == {"safe", "aggressive", "reckless"}  # 本幕三個選項都沒限定陣營


def test_options_for_unknown_name_returns_nothing(definition):
    instance = _active_battle(definition)
    assert bi.options_for(instance, definition, "幽靈") == []


def test_options_for_excludes_options_restricted_to_the_other_faction(definition):
    definition.acts[0].options.append(BattleOption(text="黃巾專屬：符水助陣", tag="safe", faction="huang"))
    instance = _active_battle(definition)
    guan_tags = {o.text for o in bi.options_for(instance, definition, "甲")}  # 甲在 guan
    huang_tags = {o.text for o in bi.options_for(instance, definition, "乙")}  # 乙在 huang
    assert "黃巾專屬：符水助陣" not in guan_tags
    assert "黃巾專屬：符水助陣" in huang_tags


# ── 進幕與終局判定 ──────────────────────────────────────────


def test_advancing_to_the_next_act_when_trend_crosses_the_threshold(definition):
    instance = _active_battle(definition)
    instance.trend = 65
    bi.submit_action(instance, "甲", "aggressive")
    bi.submit_action(instance, "乙", "safe")
    msgs = bi.resolve_round(instance, definition, random.Random(0))
    assert instance.act_index == 1
    assert any("決戰" in m for m in msgs)


def test_outcome_is_only_checked_on_the_final_act(definition):
    instance = _active_battle(definition)
    instance.trend = 90  # 已經超過第一幕的終局門檻數字，但第一幕本身不判終局
    bi.submit_action(instance, "甲", "safe")
    bi.submit_action(instance, "乙", "safe")
    bi.resolve_round(instance, definition, random.Random(0))
    assert instance.phase == "active"  # 還在打，只是換到第二幕


def test_outcome_ends_the_battle_once_on_the_final_act(definition):
    instance = _active_battle(definition)
    instance.act_index = 1  # 直接跳到決戰幕
    instance.trend = 75
    bi.submit_action(instance, "甲", "safe")
    bi.submit_action(instance, "乙", "safe")
    bi.resolve_round(instance, definition, random.Random(0))
    assert instance.phase == "ended"
    assert instance.outcome_title == "官軍大勝"


def test_the_fallback_outcome_with_no_bounds_catches_a_stalemate(definition):
    instance = _active_battle(definition)
    instance.act_index = 1
    instance.trend = 50  # 不滿足前兩個 outcome 的範圍，落到保底的「僵持」
    bi.submit_action(instance, "甲", "safe")
    bi.submit_action(instance, "乙", "safe")
    bi.resolve_round(instance, definition, random.Random(0))
    assert instance.outcome_title == "僵持"


# ── LLM 敘事潤色（可選，失敗/無 client 就退回系統訊息）────────────


def test_narrate_round_without_a_client_returns_the_raw_system_messages(definition):
    instance = _active_battle(definition)
    assert bi.narrate_round(None, definition, instance, ["甲選了穩紮穩打。"]) == "甲選了穩紮穩打。"


def test_narrate_round_uses_the_llm_text_when_available(definition):
    instance = _active_battle(definition)
    client = mock.Mock()
    client.chat_text.return_value = "戰場上煙塵四起。"
    assert bi.narrate_round(client, definition, instance, ["甲選了穩紮穩打。"]) == "戰場上煙塵四起。"


def test_narrate_round_falls_back_when_the_llm_call_fails(definition):
    instance = _active_battle(definition)
    client = mock.Mock()
    client.chat_text.side_effect = RuntimeError("連不上")
    assert bi.narrate_round(client, definition, instance, ["甲選了穩紮穩打。"]) == "甲選了穩紮穩打。"
