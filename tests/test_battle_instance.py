import math
import random
from math import isclose
from pathlib import Path
from unittest import mock

import pytest

from conftest import FixedRandom
from tianxia import battle_instance as bi
from tianxia.content import load_content
from tianxia.models import (
    MOVES, BattleAct, BattleDef, BattleFaction, BattleOption, BattleOutcome, BattleTuning,
    FreeTextGamble, ThirdParty,
)


CODES = {"強攻": "strong", "固守": "hold", "奇襲": "raid"}


def _three_moves_for(*sides) -> list[BattleOption]:
    """每一邊的三招（決戰改版一）：<陣營>_strong／_hold／_raid，寫 move 與陣營。"""
    return [
        BattleOption(text=f"{side}{move}", tag=f"{side}_{CODES[move]}", faction=side, move=move)
        for side in sides for move in MOVES
    ]


@pytest.fixture
def definition() -> BattleDef:
    return BattleDef(
        id="test_battle",
        name="測試決戰",
        factions=[BattleFaction(id="guan", name="官軍"), BattleFaction(id="huang", name="黃巾")],
        trend_start=50,
        acts=[
            BattleAct(id="a1", title="初探", text="雙方試探。", goal="推動戰局", options=_three_moves_for("guan", "huang")),
            BattleAct(id="a2", title="決戰", text="最終決戰。", goal="決出勝負", options=_three_moves_for("guan", "huang")),
        ],
        outcomes=[
            BattleOutcome(faction="guan", trend_min=70, title="官軍大勝", text="官軍獲勝。"),
            BattleOutcome(faction="huang", trend_max=30, title="黃巾得勝", text="黃巾獲勝。"),
            BattleOutcome(faction="guan", title="僵持", text="不分勝負。"),
        ],
        muster_seconds=600,
        round_seconds=120,
    )


@pytest.fixture
def gamble_definition(definition) -> BattleDef:
    """跟 definition 同一個骨架，但每一幕每邊多一個放手一搏（free_text）、並設定了 free_text_gamble——
    給「放手一搏」賭局機制的測試用，不影響 definition 自己既有的那些測試（那些是三招路徑，兩者分開測）。"""
    copy = definition.model_copy(deep=True)
    for act in copy.acts:
        act.options += [
            BattleOption(text="單刀衝撞敵營", tag=f"{side}_reckless", faction=side, free_text=True)
            for side in ("guan", "huang")
        ]
    # 氣血池是 100（_active_battle）：份量照比例寫成跟舊的絕對數字一樣（成功 -10、失敗 -(20 + 風險×3)），上限放寬到不會碰到
    copy.free_text_gamble = FreeTextGamble(
        success_trend_base=5, success_trend_per_risk=0.3, success_neili_share=0.1,
        failure_trend_per_risk=0.1, failure_trend_cap=100, failure_neili_share_base=0.2, failure_neili_share_per_risk=0.03,
        side_trend_cap=100,
    )
    return copy


@pytest.fixture
def showdown() -> BattleDef:
    """照正式內容的黃巾決戰縮小的骨架：三幕、兩邊各有自己的強攻／固守／奇襲、65／35 兩條門檻加一個無門檻的
    保底。每幕幾回合、多懸殊就提前收場都用預設值（3 回合一幕、偏離 40），整場 9 回合。"""
    return BattleDef(
        id="showdown",
        name="測試決戰",
        factions=[BattleFaction(id="guan", name="官軍"), BattleFaction(id="huang", name="黃巾")],
        trend_start=50,
        acts=[
            BattleAct(id="s1", title="兩軍對陣", text="兩軍列陣。", goal="推動戰局", options=_three_moves_for("guan", "huang")),
            BattleAct(id="s2", title="鏖戰正酣", text="犬牙交錯。", goal="撐過消耗", options=_three_moves_for("guan", "huang")),
            BattleAct(id="s3", title="決勝時刻", text="最後一擊。", goal="分出勝負", options=_three_moves_for("guan", "huang")),
        ],
        outcomes=[
            BattleOutcome(faction="guan", trend_min=65, title="官軍大勝", text="官軍獲勝。"),
            BattleOutcome(faction="huang", trend_max=35, title="黃巾得勢", text="黃巾獲勝。"),
            BattleOutcome(faction="guan", title="兩軍膠著", text="不分勝負。"),
        ],
    )


@pytest.fixture
def three() -> BattleDef:
    """三招的決戰（戰鬥系統 3.4）：一幕九回合，兩邊各三招，沒有放手一搏。"""
    options = [
        BattleOption(text=f"{side}{move}", tag=f"{side}_{CODES[move]}", faction=side, move=move)
        for side in ("guan", "huang") for move in MOVES
    ]
    return BattleDef(
        id="three", name="三招之戰",
        factions=[BattleFaction(id="guan", name="官軍"), BattleFaction(id="huang", name="黃巾")],
        acts=[BattleAct(id="a1", title="對陣", text="兩軍對陣。", goal="推動戰局", options=options)],
        rounds_per_act=9, decisive_margin=40,
        outcomes=[BattleOutcome(faction="guan", title="收場", text="戰罷。")],
    )


def _fight(definition, picks, scores=100.0, power=0.0):
    """picks：[(名號, 陣營, 招), ...]；每個人每招的份量都是 scores、滿血，結算一回合。"""
    battle = bi.start_muster(definition, now=0)
    for name, side, _ in picks:
        bi.join_faction(battle, name, side, neili_cap=1000, power=power, scores={m: scores for m in MOVES})
    bi.close_muster(battle, definition, random.Random(0), now=0)
    for name, side, move in picks:
        bi.submit_action(battle, name, f"{side}_{CODES[move]}")
    bi.resolve_round(battle, definition, random.Random(0), now=1, tuning=BattleTuning())
    return battle


def _two_fighters(definition, scores=50.0):
    """甲（官軍）與乙（黃巾）各帶三招份量 scores、滿血，已經開打、還沒人出手。"""
    battle = bi.start_muster(definition, now=0)
    for name, side in (("甲", "guan"), ("乙", "huang")):
        bi.join_faction(battle, name, side, neili_cap=300, scores={m: scores for m in MOVES})
    bi.close_muster(battle, definition, random.Random(0), now=0)
    return battle


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


def test_auto_assign_latecomer_keeps_a_given_faction_even_when_unbalanced(definition):
    instance = bi.start_muster(definition, now=0.0)
    bi.join_faction(instance, "甲", "guan", neili_cap=100.0)
    bi.auto_assign_latecomer(instance, definition, "乙", neili_cap=100.0, rng=random.Random(0), faction="guan")
    assert instance.participants["乙"].faction == "guan"  # 指定了陣營就站自己那邊，不被平衡規則改邊


def test_auto_assign_latecomer_ignores_a_faction_not_in_the_battle(definition):
    instance = bi.start_muster(definition, now=0.0)
    bi.join_faction(instance, "甲", "guan", neili_cap=100.0)
    bi.auto_assign_latecomer(instance, definition, "乙", neili_cap=100.0, rng=random.Random(0), faction="haoqiang")
    assert instance.participants["乙"].faction == "huang"  # 指定的陣營不在這場戰鬥裡，退回平衡塞人


# ── 每招的份量（決戰改版 1 Task 2，戰鬥系統 3.4）─────────────────────────────


def test_move_scores_follow_the_designs_examples():
    """戰鬥系統 3.4：剛招式＋剛內功 → 強攻 100、固守 75、奇襲 50；剛＋柔 → 80／85／60（實力 100 時：威力 160）。"""
    t = BattleTuning()
    assert bi.move_scores(t, 160, "剛", "剛") == {"強攻": 100, "固守": 75, "奇襲": 50}
    assert bi.move_scores(t, 160, "剛", "柔") == {"強攻": 80, "固守": 85, "奇襲": 60}


def test_the_stronger_you_are_the_more_you_weigh_in_a_battle():
    """越強越有份量（試玩回饋 2026-10-08）：實力 20＋0.5×威力，威力 400 封頂。新手（威力約 25）32.5，
    整季練上去的（威力 300）170，五倍多；舊的 40＋0.4×min(威力,150)、最多 100 只差兩倍。"""
    t = BattleTuning()
    assert bi.move_scores(t, 0, None, None) == {"強攻": 15, "固守": 15, "奇襲": 15}  # 實力 20 × 適性 75%
    newbie, seasoned = bi.strength(t, 25), bi.strength(t, 300)
    assert (newbie, seasoned) == (32.5, 170)
    assert seasoned / newbie > 5
    assert bi.strength(t, 1000) == bi.strength(t, 400) == 220  # 威力 400 封頂
    assert bi.move_scores(t, -20, None, None) == bi.move_scores(t, 0, None, None)  # 負的威力不會把實力壓到底子以下


def test_a_role_adds_a_little_weight_to_its_favourite_move():
    t = BattleTuning()
    plain = bi.move_scores(t, 160, None, None)
    for role, move in bi.ROLE_MOVES.items():
        scores = bi.move_scores(t, 160, None, None, role=role)
        assert scores[move] == round(plain[move] * 1.15, 1)
        assert all(scores[m] == plain[m] for m in MOVES if m != move)
    assert bi.move_scores(t, 160, None, None, role="wis") == plain  # 軍師、參謀不改份量


def test_the_role_is_the_standout_stat_and_nobody_gets_one_when_all_are_even():
    order = ("str", "agi", "con", "wis", "lore")
    assert bi.role_for({k: 5 for k in order}, order) == ""
    assert bi.role_for({**{k: 5 for k in order}, "con": 8}, order) == "con"
    assert bi.role_for({**{k: 5 for k in order}, "agi": 7, "lore": 7}, order) == "agi"  # 同分照順序
    t = BattleTuning()
    assert [bi.role_name(t, k) for k in order] == ["先鋒", "斥候", "盾陣", "軍師", "參謀"]
    assert bi.role_text(t, "str") == "先鋒（強攻的份量多 15%）"
    assert bi.role_text(t, "") == ""


@pytest.mark.parametrize("attribute, good, bad", [
    ("剛", "強攻", "奇襲"), ("實", "強攻", "奇襲"), ("陽", "強攻", "固守"), ("柔", "固守", "強攻"),
    ("陰", "固守", "強攻"), ("慢", "固守", "奇襲"), ("快", "奇襲", "固守"), ("虛", "奇襲", "強攻"),
])
def test_each_attribute_favours_one_move_and_hurts_another(attribute, good, bad):
    """設計 3.4 的表：武學屬性 ±15、內功屬性 ±10，另一招不動（威力 160 → 實力 100，適性就是份量）。"""
    third = next(m for m in MOVES if m not in (good, bad))
    outer = bi.move_scores(BattleTuning(), 160, attribute, None)
    assert (outer[good], outer[third], outer[bad]) == (90, 75, 60)
    inner = bi.move_scores(BattleTuning(), 160, None, attribute)
    assert (inner[good], inner[third], inner[bad]) == (85, 75, 65)


def test_affinity_is_clamped_between_fifty_and_a_hundred():
    """適性夾在 50～100：擅長加到頂不會超過 100，兩邊都不擅長也不會低於 50。"""
    t = BattleTuning(affinity_base=95.0, affinity_outer=30.0, affinity_inner=30.0)
    scores = bi.move_scores(t, 160, "剛", "剛")  # 強攻 95+60 → 夾到 100；奇襲 95−60 → 夾到 50
    assert (scores["強攻"], scores["奇襲"]) == (100, 50)


def test_move_scores_name_all_three_moves_whatever_the_attributes():
    t = BattleTuning()
    assert set(bi.move_scores(t, 80, "不存在的屬性", None)) == set(MOVES)  # 認不得的屬性當作沒學，不加不減
    assert bi.move_scores(t, 80, "不存在的屬性", None) == bi.move_scores(t, 80, None, None)


def test_join_snapshots_the_scores(definition):
    battle = bi.start_muster(definition, now=0)
    bi.join_faction(battle, "甲", "guan", neili_cap=300, power=50, scores={"強攻": 60, "固守": 45, "奇襲": 30})
    assert battle.participants["甲"].scores == {"強攻": 60, "固守": 45, "奇襲": 30}


def test_a_latecomer_snapshots_the_scores_too(definition):
    battle = bi.start_muster(definition, now=0)
    bi.auto_assign_latecomer(
        battle, definition, "乙", neili_cap=300, rng=random.Random(0), power=50,
        scores={"強攻": 20, "固守": 40, "奇襲": 60},
    )
    assert battle.participants["乙"].scores == {"強攻": 20, "固守": 40, "奇襲": 60}


def test_a_snapshot_is_a_copy_so_later_changes_to_the_callers_dict_do_not_leak_in(definition):
    battle = bi.start_muster(definition, now=0)
    mine = {"強攻": 60.0, "固守": 45.0, "奇襲": 30.0}
    bi.join_faction(battle, "甲", "guan", neili_cap=300, scores=mine)
    mine["強攻"] = 0.0
    assert battle.participants["甲"].scores["強攻"] == 60.0


def test_joining_without_scores_leaves_them_empty(definition):
    battle = bi.start_muster(definition, now=0)
    bi.join_faction(battle, "甲", "guan", neili_cap=300)
    bi.auto_assign_latecomer(battle, definition, "乙", neili_cap=300, rng=random.Random(0))
    assert battle.participants["甲"].scores == {} and battle.participants["乙"].scores == {}


def test_a_participant_saved_before_scores_still_loads(definition):
    """戰鬥存成 JSON：上線前就加入的人沒有 scores 這一欄，讀進來是空的（每招份量 0），不當機。"""
    old = bi.BattleParticipant(name="甲", faction="guan", neili=100.0, neili_cap=100.0).model_dump()
    old.pop("scores")
    assert bi.BattleParticipant.model_validate(old).scores == {}


# ── 回合鎖步 ─────────────────────────────────────────────


def _active_battle(definition) -> bi.BattleInstance:
    instance = bi.start_muster(definition, now=0.0)
    for name, side in (("甲", "guan"), ("乙", "huang")):
        bi.join_faction(instance, name, side, neili_cap=100.0, scores={m: 100.0 for m in MOVES})
    bi.close_muster(instance, definition, random.Random(0))
    return instance


def test_round_is_not_complete_until_everyone_submits(definition):
    instance = _active_battle(definition)
    assert not bi.round_is_complete(instance)
    bi.submit_action(instance, "甲", "guan_hold")
    assert not bi.round_is_complete(instance)
    bi.submit_action(instance, "乙", "huang_hold")
    assert bi.round_is_complete(instance)


def test_eliminated_participants_are_not_required_to_submit(definition):
    instance = _active_battle(definition)
    instance.participants["乙"].eliminated = True
    bi.submit_action(instance, "甲", "guan_hold")
    assert bi.round_is_complete(instance)


def test_submit_action_from_an_eliminated_participant_is_ignored(definition):
    instance = _active_battle(definition)
    instance.participants["甲"].eliminated = True
    bi.submit_action(instance, "甲", "guan_hold")
    assert "甲" not in instance.round.pending_actions


def test_fill_timed_out_actions_defaults_the_missing_ones(definition):
    instance = _active_battle(definition)
    bi.submit_action(instance, "甲", "guan_strong")
    bi.fill_timed_out_actions(instance, definition)
    assert instance.round.pending_actions == {"甲": "guan_strong", "乙": "huang_hold"}


def test_an_away_participant_drops_this_rounds_action_and_the_round_does_not_wait(definition):
    instance = _active_battle(definition)
    bi.submit_action(instance, "乙", "huang_strong", text="衝", success_rate=40)
    bi.set_away(instance, "乙", True)
    assert instance.participants["乙"].away
    assert "乙" not in instance.round.pending_actions and "乙" not in instance.round.custom_texts
    assert "乙" not in instance.round.success_rates
    bi.submit_action(instance, "甲", "guan_hold")
    assert bi.round_is_complete(instance)


def test_an_away_participant_cannot_submit_until_they_come_back(definition):
    instance = _active_battle(definition)
    bi.set_away(instance, "甲", True)
    bi.submit_action(instance, "甲", "guan_hold")
    assert "甲" not in instance.round.pending_actions
    bi.set_away(instance, "甲", False)
    bi.submit_action(instance, "甲", "guan_hold")
    assert instance.round.pending_actions["甲"] == "guan_hold"


def test_timed_out_actions_skip_away_participants(definition):
    instance = _active_battle(definition)
    bi.set_away(instance, "乙", True)
    bi.fill_timed_out_actions(instance, definition)
    assert instance.round.pending_actions == {"甲": "guan_hold"}


def test_timed_out_actions_pick_each_sides_own_safest_option(definition):
    """逾時代選只挑自己陣營能選的招：黃巾那邊不會被代選成官軍的固守、替對面推戰局。"""
    instance = _active_battle(definition)
    bi.fill_timed_out_actions(instance, definition)
    assert instance.round.pending_actions == {"甲": "guan_hold", "乙": "huang_hold"}
    bi.resolve_round(instance, definition, random.Random(0))
    assert instance.trend == 50  # 兩邊各守各的、份量一樣，戰局不動
    assert instance.participants["甲"].neili == 85 and instance.participants["乙"].neili == 85  # 各扣固守的 15


def test_timed_out_actions_skip_someone_who_only_has_a_free_text_option(definition):
    """這一幕只有放手一搏（不是固定招）：逾時不替他代選（沒有三招可代選，也沒有舊的查表退路）。"""
    definition.acts[0].options = [BattleOption(text="放手一搏", tag="guan_reckless", faction="guan", free_text=True)]
    instance = _active_battle(definition)
    bi.fill_timed_out_actions(instance, definition)
    assert instance.round.pending_actions == {} and instance.round.auto_picked == []


def test_a_battle_everyone_has_walked_away_from_ends_with_its_fallback(definition):
    instance = _active_battle(definition)
    for name in ("甲", "乙"):
        bi.set_away(instance, name, True)
    bi.end_without_fighters(instance, definition, now=definition.round_seconds)
    assert instance.phase == "ended" and instance.outcome_title == "僵持"


def test_set_away_ignores_someone_not_in_the_battle(definition):
    instance = _active_battle(definition)
    bi.set_away(instance, "路人", True)
    assert "路人" not in instance.participants


# ── 回合結算：trend / 氣血 / 出局 ──────────────────────────


def test_resolve_round_pushes_the_trend_and_drains_neili(definition):
    instance = _active_battle(definition)
    bi.submit_action(instance, "甲", "guan_hold")
    bi.submit_action(instance, "乙", "huang_hold")
    bi.resolve_round(instance, definition, random.Random(0))
    assert instance.trend == 50  # 兩邊各一人、同一招、份量一樣：互相抵銷
    assert instance.participants["甲"].neili == 85  # 固守的損耗 15 ×（2 − 1.0）
    assert instance.participants["乙"].neili == 85
    instance.round.pending_actions.clear()
    bi.submit_action(instance, "甲", "guan_raid")  # 乙這一回合沒出手：甲的一邊推滿 10
    bi.resolve_round(instance, definition, random.Random(0))
    assert instance.trend == 60


def test_submit_action_records_custom_text(gamble_definition):
    instance = _active_battle(gamble_definition)
    bi.submit_action(instance, "甲", "guan_reckless", text="直取波才首級")
    assert instance.round.custom_texts["甲"] == "直取波才首級"
    assert instance.round.pending_actions["甲"] == "guan_reckless"  # 數值不看玩家打了什麼字


def test_submit_action_without_text_leaves_custom_texts_untouched(definition):
    instance = _active_battle(definition)
    bi.submit_action(instance, "甲", "guan_hold")
    assert "甲" not in instance.round.custom_texts


def test_custom_text_on_a_fixed_move_changes_nothing(definition):
    """玩家打的字只有放手一搏的訊息會寫（見 test_resolve_round_gamble_message_includes_the_assessed_success_rate）；
    固定的三招照舊算：份量、剋制、損耗都不看文字。"""
    instance = _active_battle(definition)
    bi.submit_action(instance, "甲", "guan_strong", text="直取波才首級")
    bi.submit_action(instance, "乙", "huang_strong")
    msgs = bi.resolve_round(instance, definition, random.Random(0))
    assert not any("直取波才首級" in m for m in msgs)
    assert instance.participants["甲"].neili == 40  # 跟沒打字的強攻扣血量一樣（100 − 60，沒有威力抵銷）


# ── 放手一搏：LLM 評成功率、系統擲骰、公式換算（設計討論：「我就是希望看到玩家的
# 奇葩操作對戰局產生影響」）─────────────────────────────────────


def test_resolve_round_gamble_success_pushes_trend_toward_the_actors_faction(gamble_definition):
    instance = _active_battle(gamble_definition)
    bi.submit_action(instance, "甲", "guan_reckless", success_rate=50)  # 甲在 guan（factions[0]，正向）
    bi.submit_action(instance, "乙", "huang_hold")
    msgs = bi.resolve_round(instance, gamble_definition, FixedRandom(0.0))  # random()=0.0，永遠擲骰成功
    # 三招：官軍沒人出固定招（甲在賭）、黃巾有乙 → 推 −10；賭贏 5 + 50 × 0.3 ＝ 20，甲威力 0（實力 20）打五折 → +10
    assert instance.trend == 50 - 10 + 10
    assert any("這一搏成功了" in m for m in msgs)
    assert instance.participants["甲"].neili == 90  # 100 - success_neili_damage(10)


def test_resolve_round_gamble_failure_pushes_trend_away_from_the_actors_faction(gamble_definition):
    instance = _active_battle(gamble_definition)
    bi.submit_action(instance, "甲", "guan_reckless", success_rate=80)  # risk=20，刻意選小一點避免傷害超過上限被夾到 0 看不出公式
    bi.submit_action(instance, "乙", "huang_hold")
    msgs = bi.resolve_round(instance, gamble_definition, FixedRandom(0.999))  # 永遠擲骰失敗
    assert any("這一搏失敗了" in m for m in msgs)
    # risk=20：failure_neili = 20 + 20*3.0 = 80
    assert instance.participants["甲"].neili == 100 - 80


def test_resolve_round_gamble_direction_flips_for_the_second_faction(gamble_definition):
    """乙在 huang（factions[1]，負向）：賭贏了戰局應該往 huang 那邊推（trend 下降）。"""
    instance = _active_battle(gamble_definition)
    bi.submit_action(instance, "甲", "guan_hold")
    bi.submit_action(instance, "乙", "huang_reckless", success_rate=50)
    bi.resolve_round(instance, gamble_definition, FixedRandom(0.0))
    # 三招：只有甲出固定招 → +10；乙賭贏往 huang 那邊再推 −20，乙威力 0 打五折 −10，合起來落在 50
    assert instance.trend == 50 + 10 - 10


def test_resolve_round_gamble_higher_risk_means_bigger_reward_and_bigger_cost(gamble_definition):
    low_risk = _active_battle(gamble_definition)
    bi.submit_action(low_risk, "甲", "guan_reckless", success_rate=90)  # risk=10
    bi.submit_action(low_risk, "乙", "huang_hold")
    bi.resolve_round(low_risk, gamble_definition, FixedRandom(0.999))  # 失敗
    low_risk_damage = 100 - low_risk.participants["甲"].neili

    high_risk = _active_battle(gamble_definition)
    bi.submit_action(high_risk, "甲", "guan_reckless", success_rate=10)  # risk=90
    bi.submit_action(high_risk, "乙", "huang_hold")
    bi.resolve_round(high_risk, gamble_definition, FixedRandom(0.999))  # 失敗
    high_risk_damage = 100 - high_risk.participants["甲"].neili

    assert high_risk_damage > low_risk_damage  # 風險愈高，失敗代價愈重


def test_resolve_round_gamble_can_eliminate_on_a_bad_roll(gamble_definition):
    """極端的奇葩操作（成功率評很低）賭輸了，傷害可以直接打到出局——是公式的數字夠狠，不是程式特判。"""
    instance = _active_battle(gamble_definition)
    bi.submit_action(instance, "甲", "guan_reckless", success_rate=1)  # risk=99
    bi.submit_action(instance, "乙", "huang_hold")
    bi.resolve_round(instance, gamble_definition, FixedRandom(0.999))  # 失敗
    assert instance.participants["甲"].eliminated


def test_resolve_round_gamble_message_includes_the_assessed_success_rate(gamble_definition):
    instance = _active_battle(gamble_definition)
    bi.submit_action(instance, "甲", "guan_reckless", text="直取波才首級", success_rate=25)
    bi.submit_action(instance, "乙", "huang_hold")
    msgs = bi.resolve_round(instance, gamble_definition, FixedRandom(0.0))
    assert any("直取波才首級" in m and "25%" in m for m in msgs)


def test_a_gamble_without_a_gamble_config_does_nothing(definition):
    """definition（沒設定 free_text_gamble）就算送出了 success_rate，也沒有賭局可以走：這個人這回合不推戰局、不扣血，
    也不算進三招的比例（舊的查表已經退役，沒有退路）；對面照常。"""
    instance = _active_battle(definition)
    bi.submit_action(instance, "甲", "guan_strong", success_rate=50)
    bi.submit_action(instance, "乙", "huang_hold")
    bi.resolve_round(instance, definition, FixedRandom(0.0))
    assert instance.trend == 40  # 官軍沒人出三招 → 黃巾推滿 10
    assert instance.participants["甲"].neili == 100 and not instance.participants["甲"].eliminated


# ── 三招的結算：剋制、√人數、推力（決戰改版 1 Task 3，戰鬥系統 3.4）──────────────


def test_counter_coefficient_spans_half_to_one_and_a_half():
    """Review Focus 4：對面六成強攻、其餘固守，你出固守 ×1.3；對面全強攻 ×1.5、全奇襲 ×0.5（設計 3.4 的例子）。"""
    t = BattleTuning()
    assert isclose(bi.counter_coefficient(t, "固守", {"強攻": 0.6, "固守": 0.4}), 1.3)
    assert bi.counter_coefficient(t, "固守", {"強攻": 1.0}) == 1.5
    assert bi.counter_coefficient(t, "固守", {"奇襲": 1.0}) == 0.5


def test_every_move_is_beaten_by_exactly_one_other_in_the_coefficient():
    """三招繞一圈：每一招對「被它剋的」×1.5、對「剋它的」×0.5，對自己人（同招）×1。"""
    t = BattleTuning()
    for move, beaten in (("固守", "強攻"), ("強攻", "奇襲"), ("奇襲", "固守")):
        assert bi.counter_coefficient(t, move, {beaten: 1.0}) == 1.5
        assert bi.counter_coefficient(t, beaten, {move: 1.0}) == 0.5
        assert bi.counter_coefficient(t, move, {move: 1.0}) == 1.0
    assert bi.counter_coefficient(t, "強攻", {}) == 1.0  # 對面沒人出固定招


def test_numbers_help_but_with_diminishing_returns(three):
    """Review Focus 1：官軍 1000 人、黃巾 250 人，全出強攻、份量相同：一回合推 3.3，四捨五入 3（設計 3.4）。"""
    picks = [(f"官{i}", "guan", "強攻") for i in range(1000)] + [(f"黃{i}", "huang", "強攻") for i in range(250)]
    assert _fight(three, picks).trend == 53


def test_reading_the_enemy_lets_the_few_beat_the_many(three):
    """100 人固守對 200 人強攻：固守 ×1.5、強攻 ×0.5，少的一邊推 3.6，四捨五入 4。"""
    picks = [(f"官{i}", "guan", "固守") for i in range(100)] + [(f"黃{i}", "huang", "強攻") for i in range(200)]
    battle = _fight(three, picks)
    assert battle.trend == 54
    assert battle.participants["官0"].last_result == "固守（剋制 ×1.5）"
    assert battle.last_mix == {"guan": {"強攻": 0.0, "固守": 1.0, "奇襲": 0.0}, "huang": {"強攻": 1.0, "固守": 0.0, "奇襲": 0.0}}


def test_a_side_with_nobody_on_a_fixed_move_gets_pushed_ten(three):
    """Review Focus 2：一邊沒人出固定招，另一邊推滿 10，不除以零。"""
    assert _fight(three, [("甲", "guan", "奇襲")]).trend == 60
    assert _fight(three, [("乙", "huang", "奇襲")]).trend == 40


def test_nobody_on_a_fixed_move_on_either_side_pushes_nothing(three):
    battle = bi.start_muster(three, now=0)
    bi.join_faction(battle, "甲", "guan", neili_cap=300, scores={m: 50.0 for m in MOVES})
    bi.close_muster(battle, three, random.Random(0), now=0)
    battle.participants["甲"].away = True  # 沒有任何人出手
    bi.resolve_round(battle, three, random.Random(0), now=1, tuning=BattleTuning())
    assert battle.trend == 50 and battle.last_mix == {"guan": {}, "huang": {}}


@pytest.mark.parametrize("out", [
    pytest.param(lambda battle: setattr(battle.participants["乙"], "eliminated", True), id="all-down"),
    pytest.param(lambda battle: bi.set_away(battle, "乙", True), id="all-out-of-the-region"),
])
def test_a_side_with_nobody_left_in_the_fight_gets_pushed_ten(three, out):
    """那一邊的人全倒下、或全離開了大區：這一回合照樣結算，往對方推滿 10。"""
    battle = _two_fighters(three)
    out(battle)
    bi.submit_action(battle, "甲", "guan_hold")
    bi.resolve_round(battle, three, random.Random(0), now=1, tuning=BattleTuning())
    assert battle.trend == 60


def test_a_side_that_is_all_gambling_gets_pushed_ten_and_the_gamble_still_counts(three):
    """放手一搏的人不算進三招的比例、也不算進人數：黃巾只有一個人而且在賭，官軍推滿 10；賭輸再加 1（一個人失手最多倒退 1，
    試玩回饋 2026-10-08），氣血池 300 扣 35%。"""
    gamble = three.model_copy(deep=True)
    gamble.acts[0].options.append(BattleOption(text="放手一搏", tag="huang_reckless", faction="huang", free_text=True))
    gamble.free_text_gamble = FreeTextGamble()
    battle = _two_fighters(gamble)
    bi.submit_action(battle, "甲", "guan_hold")
    bi.submit_action(battle, "乙", "huang_reckless", text="夜襲", success_rate=0)  # 一定失敗
    msgs = bi.resolve_round(battle, gamble, random.Random(0), now=1, tuning=BattleTuning())
    assert battle.trend == 61  # 三招推 +10，黃巾賭輸 −(−1)＝ +1
    assert battle.last_mix["huang"] == {}
    assert "乙這一搏失敗了，付出了慘痛代價：黃巾的戰局倒退 1，自己氣血 -105。" in msgs  # 代價照引擎算的寫（試玩回饋 2026-10-08）


def test_an_empty_side_is_pushed_ten_even_when_the_side_that_is_present_has_no_force(three):
    """設計 3.4：一邊沒有任何人在場時，另一邊每回合推滿 10——就算在場的那一邊沒有快照（份量 0、力量 0，打不出比例）。
    打不出比例時不能因為「兩邊相加是 0」就不推。"""
    for side, name, expected in (("guan", "甲", 60), ("huang", "乙", 40)):
        battle = bi.start_muster(three, now=0)
        bi.join_faction(battle, name, side, neili_cap=300)  # 沒有 scores
        bi.close_muster(battle, three, random.Random(0), now=0)
        bi.submit_action(battle, name, f"{side}_hold")
        bi.resolve_round(battle, three, random.Random(0), now=1, tuning=BattleTuning())
        assert battle.trend == expected, side


def test_the_mix_line_stays_first_in_a_round_where_someone_falls(three):
    """回合訊息的順序：出招比例那一行在最前面，倒下的句子接在後面。"""
    battle = _two_fighters(three)
    battle.participants["甲"].neili = 20  # 強攻撞上固守：60 ×（2 − 0.5）＝ 90，倒下
    bi.submit_action(battle, "甲", "guan_strong")
    bi.submit_action(battle, "乙", "huang_hold")
    msgs = bi.resolve_round(battle, three, random.Random(0), now=1, tuning=BattleTuning())
    assert msgs[0].startswith("官軍：強攻 100%") and "（戰局 " in msgs[0]
    assert msgs[1] == "這一回合黃巾佔了上風（戰局 50→43）：黃巾的固守剋住了官軍的強攻，乙一馬當先。"  # 摘要接在比例後面
    assert "氣血耗盡" in msgs[2] and len(msgs) == 3


def test_the_mix_line_stays_first_when_the_act_changes(three):
    two = three.model_copy(deep=True)
    two.rounds_per_act = 1
    two.acts.append(two.acts[0].model_copy(deep=True, update={"id": "a2", "title": "鏖戰", "text": "犬牙交錯。"}))
    battle = _two_fighters(two)
    bi.submit_action(battle, "甲", "guan_hold")
    bi.submit_action(battle, "乙", "huang_hold")
    msgs = bi.resolve_round(battle, two, random.Random(0), now=1, tuning=BattleTuning())
    assert msgs[0].startswith("官軍：強攻 0%・固守 100%") and msgs[-1] == "【鏖戰】犬牙交錯。" and len(msgs) == 3


def test_without_the_mix_line_keeps_everything_else(three):
    """場景上的記錄不放出招比例那一行（見 Game._advance_battle_round）：有人出固定招才有那一行、而且一定是第一行。"""
    battle = _two_fighters(three)
    bi.submit_action(battle, "甲", "guan_hold")
    bi.submit_action(battle, "乙", "huang_hold")
    msgs = bi.resolve_round(battle, three, random.Random(0), now=1, tuning=BattleTuning())
    assert len(msgs) == 2 and bi.without_mix_line(battle, msgs) == ["這一回合兩軍相持不下（戰局 50）。"]
    assert bi.without_mix_line(battle, ["第一句", "第二句"]) == ["第二句"]  # 這個回合有出招：丟掉第一句
    quiet = _two_fighters(three)  # 沒人出固定招：沒有那一行，什麼都不丟
    assert bi.resolve_round(quiet, three, random.Random(0), now=1, tuning=BattleTuning()) == ["這一回合兩軍相持不下（戰局 50）。"]
    assert bi.without_mix_line(quiet, ["某句"]) == ["某句"]


def test_a_participant_without_scores_counts_as_zero(three):
    """Review Focus 3：上線前就加入、沒有 scores 的人：份量 0，照常扣血，不當機。"""
    battle = bi.start_muster(three, now=0)
    bi.join_faction(battle, "舊人", "guan", neili_cap=300)
    bi.join_faction(battle, "新人", "huang", neili_cap=300, scores={m: 80.0 for m in MOVES})
    bi.close_muster(battle, three, random.Random(0), now=0)
    bi.submit_action(battle, "舊人", "guan_hold")
    bi.submit_action(battle, "新人", "huang_hold")
    bi.resolve_round(battle, three, random.Random(0), now=1, tuning=BattleTuning())
    assert battle.trend == 40 and battle.participants["舊人"].neili == 285


def test_everyone_without_scores_pushes_nothing_but_still_takes_damage(three):
    """兩邊都沒有快照（舊資料整場）：份量全 0、推力 0／0 不除以零，戰局不動，照常扣血。"""
    battle = bi.start_muster(three, now=0)
    bi.join_faction(battle, "甲", "guan", neili_cap=300)
    bi.join_faction(battle, "乙", "huang", neili_cap=300)
    bi.close_muster(battle, three, random.Random(0), now=0)
    bi.submit_action(battle, "甲", "guan_strong")
    bi.submit_action(battle, "乙", "huang_hold")
    bi.resolve_round(battle, three, random.Random(0), now=1, tuning=BattleTuning())
    assert battle.trend == 50
    assert battle.participants["甲"].neili == 300 - 90 and battle.participants["乙"].neili == 300 - 7.5


def test_a_latecomer_without_a_snapshot_counts_as_zero_too(three):
    """晚到的假人若不是走 Game 加入的（沒有快照）：同一條規則，份量 0。"""
    battle = _two_fighters(three)
    bi.auto_assign_latecomer(battle, three, "丙", neili_cap=300, rng=random.Random(0), faction="guan", is_bot=True)
    for name, side in (("甲", "guan"), ("乙", "huang"), ("丙", "guan")):
        bi.submit_action(battle, name, f"{side}_hold")
    bi.resolve_round(battle, three, random.Random(0), now=1, tuning=BattleTuning())
    # 官軍：甲 50 ＋ 丙 0，÷ √2；黃巾：乙 50 ÷ √1，所以黃巾稍強、戰局往黃巾倒
    assert battle.trend == 50 + round(10 * (50 / 2 ** 0.5 - 50) / (50 / 2 ** 0.5 + 50))


def test_being_countered_costs_more_blood(three):
    """強攻撞上全固守：係數 0.5，扣 60 ×（2 − 0.5）＝ 90（威力 0、沒有抵銷）。"""
    battle = _fight(three, [("甲", "guan", "強攻"), ("乙", "huang", "固守")])
    assert battle.participants["甲"].neili == 1000 - 90 and battle.participants["乙"].neili == 1000 - 15 * 0.5


def test_power_softens_only_the_strong_attack_and_at_most_sixty_percent(three):
    """強攻的損耗，自己的武學威力最多抵銷六成（威力 120 → 六成）；威力 40 → 兩成；固守、奇襲不抵銷。"""
    neili = lambda move, power: _fight(three, [("甲", "guan", move)], power=power).participants["甲"].neili  # noqa: E731
    assert neili("強攻", 120) == pytest.approx(1000 - 60 * 0.4)
    assert neili("強攻", 400) == pytest.approx(1000 - 60 * 0.4)  # 威力再高也只抵銷六成
    assert neili("強攻", 40) == pytest.approx(1000 - 60 * 0.8)
    assert neili("奇襲", 120) == 1000 - 35
    assert neili("固守", 120) == 1000 - 15


def test_a_wounded_fighters_share_is_smaller(three):
    """份量乘氣血狀態（0.5＋0.5×剩的÷上限）：半血的人只剩八成五的份量，推力跟著降（戰鬥系統 3.4）。"""
    battle = _two_fighters(three, scores=100.0)
    battle.participants["甲"].neili = 150  # 半血 → 0.75
    bi.submit_action(battle, "甲", "guan_hold")
    bi.submit_action(battle, "乙", "huang_hold")
    bi.resolve_round(battle, three, random.Random(0), now=1, tuning=BattleTuning())
    assert battle.trend == 50 + round(10 * (75 - 100) / (75 + 100))  # 甲 75、乙 100 → −1.43 → −1


def test_tuning_is_honoured(three):
    """一回合最多推多少看 Config.battle.push_max，不是寫死的 10。"""
    battle = _two_fighters(three)
    battle.participants["乙"].eliminated = True
    bi.submit_action(battle, "甲", "guan_hold")
    bi.resolve_round(battle, three, random.Random(0), now=1, tuning=BattleTuning(push_max=4.0))
    assert battle.trend == 54


def test_the_round_message_starts_with_the_mix_and_the_push(three):
    """強攻撞上固守：官軍 ×0.5 → 25、黃巾 ×1.5 → 75，推力 10 × (25 − 75) ÷ 100 ＝ −5。"""
    battle = _two_fighters(three)
    bi.submit_action(battle, "甲", "guan_strong")
    bi.submit_action(battle, "乙", "huang_hold")
    msgs = bi.resolve_round(battle, three, random.Random(0), now=1, tuning=BattleTuning())
    assert msgs[0] == "官軍：強攻 100%・固守 0%・奇襲 0%；黃巾：強攻 0%・固守 100%・奇襲 0%（戰局 -5）"
    assert battle.trend == 45 and battle.rounds[-1].messages == msgs


def test_condition_follows_the_blood_left():
    p = bi.BattleParticipant(name="甲", faction="guan", neili=300.0, neili_cap=300.0)
    assert bi.condition(p) == 1.0
    p.neili = 150.0
    assert bi.condition(p) == 0.75
    p.neili = 0.0
    assert bi.condition(p) == 0.5


def test_last_result_is_cleared_for_anyone_who_did_not_play_a_fixed_move(three):
    """上一回合出過招的人，這一回合放手一搏、離開大區或倒下了：畫面不能還寫著上一回合的「你上一回合：…」。"""
    gamble = three.model_copy(deep=True)
    gamble.acts[0].options.append(BattleOption(text="放手一搏", tag="guan_reckless", faction="guan", free_text=True))
    gamble.free_text_gamble = FreeTextGamble()
    battle = bi.start_muster(gamble, now=0)
    for name, side in (("甲", "guan"), ("乙", "huang"), ("丙", "guan"), ("丁", "guan")):
        bi.join_faction(battle, name, side, neili_cap=300, scores={m: 50.0 for m in MOVES})
    bi.close_muster(battle, gamble, random.Random(0), now=0)
    for name, side in (("甲", "guan"), ("乙", "huang"), ("丙", "guan"), ("丁", "guan")):
        bi.submit_action(battle, name, f"{side}_hold")
    bi.resolve_round(battle, gamble, random.Random(0), now=1, tuning=BattleTuning())
    assert all(battle.participants[n].last_result == "固守（剋制 ×1.0）" for n in "甲乙丙丁")
    bi.submit_action(battle, "甲", "guan_reckless", text="夜襲", success_rate=50)  # 放手一搏
    bi.submit_action(battle, "乙", "huang_hold")  # 照常出固定招
    bi.set_away(battle, "丙", True)  # 走出大區
    battle.participants["丁"].eliminated = True  # 倒下
    bi.resolve_round(battle, gamble, random.Random(0), now=2, tuning=BattleTuning())
    assert [battle.participants[n].last_result for n in "甲丙丁"] == ["", "", ""]
    assert battle.participants["乙"].last_result == "固守（剋制 ×1.0）"


def test_the_act_text_follows_who_leads(three):
    """Review Focus 5：只看公開的戰局；50 或沒寫那一版就用原本的 text。"""
    three.acts[0].text_by_lead = {"guan": "官軍佔了上風。", "huang": "黃巾佔了上風。"}
    battle = bi.start_muster(three, now=0)
    for trend, text in ((60, "官軍佔了上風。"), (40, "黃巾佔了上風。"), (50, "兩軍對陣。")):
        battle.trend = trend
        assert bi.act_text(battle, three) == text
    three.acts[0].text_by_lead = {"guan": "官軍佔了上風。"}
    battle.trend = 30
    assert bi.act_text(battle, three) == "兩軍對陣。"


def test_changing_acts_reads_out_the_version_of_whoever_leads(three):
    """換幕那一句也照誰佔上風：這一回合先推完戰局、再換幕，所以讀的是推完之後的那一版。"""
    two = three.model_copy(deep=True)
    two.rounds_per_act = 1
    second = two.acts[0].model_copy(deep=True, update={
        "id": "a2", "title": "鏖戰", "text": "犬牙交錯。", "text_by_lead": {"guan": "官軍壓過來了。", "huang": "黃巾壓過來了。"},
    })
    two.acts.append(second)
    battle = _two_fighters(two)
    battle.participants["乙"].eliminated = True  # 黃巾沒人 → 官軍推 +10 → 60
    bi.submit_action(battle, "甲", "guan_hold")
    msgs = bi.resolve_round(battle, two, random.Random(0), now=1, tuning=BattleTuning())
    assert "【鏖戰】官軍壓過來了。" in msgs


def test_timed_out_actions_hold_the_line(three):
    """逾時沒出手：代出自己那一邊的固守（計畫二改成照方針與 AI）。"""
    battle = bi.start_muster(three, now=0)
    bi.join_faction(battle, "甲", "guan", neili_cap=300, scores={m: 50.0 for m in MOVES})
    bi.join_faction(battle, "乙", "huang", neili_cap=300, scores={m: 50.0 for m in MOVES})
    bi.close_muster(battle, three, random.Random(0), now=0)
    bi.fill_timed_out_actions(battle, three, tuning=BattleTuning())
    assert battle.round.pending_actions == {"甲": "guan_hold", "乙": "huang_hold"}
    assert battle.round.auto_picked == ["甲", "乙"]


def test_timed_out_fill_with_no_fixed_option_and_no_fallback_table_skips_that_person(three):
    """這一幕沒有他能選的固定選項（也沒有別的退路）：跳過他，不當機（驗過的內容不會走到這裡）。"""
    lonely = three.model_copy(deep=True)
    lonely.acts[0].options = [o for o in lonely.acts[0].options if o.faction == "guan"]
    battle = _two_fighters(lonely)
    bi.fill_timed_out_actions(battle, lonely, tuning=BattleTuning())
    assert battle.round.pending_actions == {"甲": "guan_hold"}


def test_the_bot_mostly_plays_its_best_move(three):
    battle = bi.start_muster(three, now=0)
    bi.join_faction(battle, "機", "guan", neili_cap=300, scores={"強攻": 90.0, "固守": 60.0, "奇襲": 40.0}, is_bot=True)
    bi.close_muster(battle, three, random.Random(0), now=0)
    rng = random.Random(1)
    picks = [bi.bot_choose_action(battle, three, "機", rng, tuning=BattleTuning()) for _ in range(200)]
    assert picks.count("guan_strong") > 120 and set(picks) <= {"guan_strong", "guan_hold", "guan_raid"}


def test_a_bot_without_a_snapshot_falls_back_to_holding_the_line(three):
    """沒有快照（份量全 0）的假人：最好的招看不出來，同分取損耗最低的固守——不是列在最前面的那一招，也不會當機。"""
    battle = bi.start_muster(three, now=0)
    bi.join_faction(battle, "機", "guan", neili_cap=300, is_bot=True)
    bi.close_muster(battle, three, random.Random(0), now=0)
    picks = [bi.bot_choose_action(battle, three, "機", random.Random(seed), tuning=BattleTuning()) for seed in range(200)]
    assert picks.count("guan_hold") > 120 and set(picks) <= {"guan_strong", "guan_hold", "guan_raid"}
    assert bi.bot_choose_action(battle, three, "機", random.Random(5)) == bi.bot_choose_action(  # 同一顆亂數種子，同一個選擇
        battle, three, "機", random.Random(5), tuning=BattleTuning(),
    )


# ── assess_action_success_rate：LLM 評機率 ─────────────────────────


def test_assess_action_success_rate_without_a_client_returns_the_default(gamble_definition):
    act = gamble_definition.acts[0]
    assert bi.assess_action_success_rate(None, act, "官軍", "直取波才首級") == bi.DEFAULT_FREE_TEXT_SUCCESS_RATE


def test_assess_action_success_rate_uses_the_llm_value_when_available(gamble_definition):
    act = gamble_definition.acts[0]
    client = mock.Mock()
    client.chat_structured.return_value = bi.SuccessRateJudgment(success_rate=25, reasoning="風險很高")
    assert bi.assess_action_success_rate(client, act, "官軍", "直取波才首級") == 25


def test_assess_action_success_rate_clamps_an_out_of_range_value(gamble_definition):
    act = gamble_definition.acts[0]
    client = mock.Mock()
    client.chat_structured.return_value = bi.SuccessRateJudgment(success_rate=150)
    assert bi.assess_action_success_rate(client, act, "官軍", "某個行動") == 100


def test_assess_action_success_rate_falls_back_when_the_llm_call_fails(gamble_definition):
    act = gamble_definition.acts[0]
    client = mock.Mock()
    client.chat_structured.side_effect = RuntimeError("連不上")
    assert bi.assess_action_success_rate(client, act, "官軍", "直取波才首級") == bi.DEFAULT_FREE_TEXT_SUCCESS_RATE


def test_bot_choose_action_never_selects_a_free_text_option(gamble_definition):
    """機器人不會自己想描述，free_text 選項對它們來說等同不存在。"""
    instance = _active_battle(gamble_definition)
    for _ in range(50):
        tag = bi.bot_choose_action(instance, gamble_definition, "甲", random.Random())
        assert tag not in ("guan_reckless", "huang_reckless")  # 這個 definition 裡 reckless 是 free_text


def test_a_costly_move_can_eliminate_a_participant_outright(definition):
    """氣血見底的人出了損耗大的強攻（還被固守剋制，×1.5），一回合就能被打到出局——
    不是程式特別判斷「這個行動很魯莽」，是三招的損耗數字本來就狠。"""
    instance = _active_battle(definition)
    instance.participants["甲"].neili = 50
    bi.submit_action(instance, "甲", "guan_strong")
    bi.submit_action(instance, "乙", "huang_hold")
    msgs = bi.resolve_round(instance, definition, random.Random(0))
    assert instance.participants["甲"].eliminated
    assert instance.participants["甲"].neili == 0  # 60 ×（2 − 0.5）＝ 90，遠超過 50
    assert any("氣血耗盡" in m for m in msgs)


def test_eliminated_participant_is_excluded_from_the_next_rounds_requirement(definition):
    instance = _active_battle(definition)
    instance.participants["甲"].neili = 50
    bi.submit_action(instance, "甲", "guan_strong")
    bi.submit_action(instance, "乙", "huang_hold")
    bi.resolve_round(instance, definition, random.Random(0))
    bi.submit_action(instance, "乙", "huang_hold")
    assert bi.round_is_complete(instance)  # 甲已出局，不用等他


# FB-027：參戰者自己的戰報要寫出手幾回合、第幾回合倒下；逾時被系統代選的回合不算自己出手。


def test_each_resolved_round_a_fighter_chose_for_themselves_counts_as_acting(definition):
    instance = _active_battle(definition)
    for _ in range(2):
        bi.submit_action(instance, "甲", "guan_hold")
        bi.submit_action(instance, "乙", "huang_hold")
        bi.resolve_round(instance, definition, random.Random(0))
    assert instance.participants["甲"].acted_rounds == 2 and instance.participants["乙"].acted_rounds == 2


def test_a_timed_out_round_picked_by_the_system_does_not_count_as_acting(definition):
    instance = _active_battle(definition)
    bi.submit_action(instance, "甲", "guan_hold")
    bi.fill_timed_out_actions(instance, definition)  # 乙沒選，系統代選
    bi.resolve_round(instance, definition, random.Random(0))
    assert instance.participants["甲"].acted_rounds == 1
    assert instance.participants["乙"].acted_rounds == 0
    bi.submit_action(instance, "乙", "huang_hold")  # 下一回合乙自己選了：照算
    bi.submit_action(instance, "甲", "guan_hold")
    bi.resolve_round(instance, definition, random.Random(0))
    assert instance.participants["乙"].acted_rounds == 1


def test_a_fighter_who_falls_remembers_the_round(definition):
    instance = _active_battle(definition)
    bi.submit_action(instance, "甲", "guan_hold")
    bi.submit_action(instance, "乙", "huang_hold")
    bi.resolve_round(instance, definition, random.Random(0))
    bi.submit_action(instance, "甲", "guan_strong")  # 氣血 85，被固守剋制扣 90：第 2 回合倒下
    bi.submit_action(instance, "乙", "huang_hold")
    bi.resolve_round(instance, definition, random.Random(0))
    fallen, standing = instance.participants["甲"], instance.participants["乙"]
    assert fallen.eliminated and fallen.fell_round == 2
    assert fallen.acted_rounds == 2  # 倒下的那一回合也是自己出的手
    assert standing.fell_round is None


def test_a_battle_saved_before_these_counts_still_loads(definition):
    old = bi.BattleParticipant(name="甲", faction="guan", neili=100.0, neili_cap=100.0).model_dump()
    for field in ("acted_rounds", "fell_round"):
        old.pop(field)
    loaded = bi.BattleParticipant.model_validate(old)
    assert loaded.acted_rounds == 0 and loaded.fell_round is None

    stored = _active_battle(definition).model_dump()  # 整場：收場時間與這回合代選了誰也是後來才有的
    stored.pop("end_time")
    stored["round"].pop("auto_picked")
    for p in stored["participants"].values():
        p.pop("acted_rounds")
        p.pop("fell_round")
    battle = bi.BattleInstance.model_validate(stored)
    assert battle.end_time is None and battle.round.auto_picked == []
    assert all(p.acted_rounds == 0 and p.fell_round is None for p in battle.participants.values())


def test_a_battle_saved_before_unfinished_existed_is_not_unfinished(definition):
    """FB-035：季終收兵的決戰另外標記；舊資料沒有這一欄，一律當作正常收場（或還在打）。"""
    stored = _active_battle(definition).model_dump()
    assert stored.pop("unfinished") is False
    assert bi.BattleInstance.model_validate(stored).unfinished is False


def test_power_softens_the_strong_attack_for_a_powerful_participant(definition):
    instance = _active_battle(definition)
    instance.participants["甲"].power = 100
    bi.submit_action(instance, "甲", "guan_strong")
    bi.submit_action(instance, "乙", "huang_strong")
    bi.resolve_round(instance, definition, random.Random(0))
    assert instance.participants["甲"].neili == 70 and instance.participants["乙"].neili == 40  # 60 × 0.5 對 60


def test_options_for_returns_only_this_participants_available_options(definition):
    instance = _active_battle(definition)
    assert {o.tag for o in bi.options_for(instance, definition, "甲")} == {"guan_strong", "guan_hold", "guan_raid"}
    assert {o.tag for o in bi.options_for(instance, definition, "乙")} == {"huang_strong", "huang_hold", "huang_raid"}
    assert {o.tag for o in bi.fixed_options(instance, definition, "甲")} == {"guan_strong", "guan_hold", "guan_raid"}


def test_options_for_unknown_name_returns_nothing(definition):
    instance = _active_battle(definition)
    assert bi.options_for(instance, definition, "幽靈") == []


def test_options_for_excludes_options_restricted_to_the_other_faction(definition):
    definition.acts[0].options.append(BattleOption(text="黃巾專屬：符水助陣", tag="huang_charm", faction="huang"))
    instance = _active_battle(definition)
    guan_tags = {o.text for o in bi.options_for(instance, definition, "甲")}  # 甲在 guan
    huang_tags = {o.text for o in bi.options_for(instance, definition, "乙")}  # 乙在 huang
    assert "黃巾專屬：符水助陣" not in guan_tags
    assert "黃巾專屬：符水助陣" in huang_tags


# ── 進幕與終局判定（戰鬥系統設計 3.2：換幕照回合數走，壓倒性才提前收場）──────────


def _to_the_last_round(instance: bi.BattleInstance, definition: BattleDef) -> None:
    """直接跳到最後一幕的最後一回合（結算完就看戰局定結果）。"""
    instance.act_index = len(definition.acts) - 1
    instance.round_number = bi.total_rounds(definition) - 1


def test_advancing_to_the_next_act_after_its_rounds_are_played(definition):
    instance = _active_battle(definition)
    for _ in range(definition.rounds_per_act):  # 每幕 3 回合（預設）
        assert instance.act_index == 0
        bi.submit_action(instance, "甲", "guan_hold")
        bi.submit_action(instance, "乙", "huang_hold")
        msgs = bi.resolve_round(instance, definition, random.Random(0))
    assert instance.act_index == 1
    assert any("決戰" in m for m in msgs)


def test_a_gauge_past_an_outcome_line_but_short_of_decisive_does_not_end_early(definition):
    instance = _active_battle(definition)
    instance.trend = 75  # 已經過了「官軍大勝」的 70，但離 90 還遠：第一回合不判結果
    bi.submit_action(instance, "甲", "guan_hold")
    bi.submit_action(instance, "乙", "huang_hold")
    bi.resolve_round(instance, definition, random.Random(0))
    assert instance.phase == "active" and instance.act_index == 0


def test_outcome_ends_the_battle_once_on_the_final_round(definition):
    instance = _active_battle(definition)
    _to_the_last_round(instance, definition)
    instance.trend = 75
    bi.submit_action(instance, "甲", "guan_hold")
    bi.submit_action(instance, "乙", "huang_hold")
    bi.resolve_round(instance, definition, random.Random(0))
    assert instance.phase == "ended"
    assert instance.outcome_title == "官軍大勝"


def test_outcome_copies_the_season_level_consequences_onto_the_instance(definition):
    definition.outcomes[0].world_flags_add = ["huangjin_decisive_win"]
    definition.outcomes[0].trend_delta = {"huangjin": -35}
    instance = _active_battle(definition)
    _to_the_last_round(instance, definition)
    instance.trend = 75
    bi.submit_action(instance, "甲", "guan_hold")
    bi.submit_action(instance, "乙", "huang_hold")
    bi.resolve_round(instance, definition, random.Random(0))
    assert instance.outcome_world_flags == ["huangjin_decisive_win"]
    assert instance.outcome_trend_delta == {"huangjin": -35}


def test_a_decisive_gauge_ends_the_battle_in_either_direction(definition):
    """壓倒性是雙向的：不管戰局往哪一方傾斜，偏離中線 50 達 decisive_margin（預設 40）就當回合收場，
    不是只有某一方拉開差距才算。（兩邊各出固守、份量一樣：這一回合推 0，戰局停在原地。）"""
    low = _active_battle(definition)
    low.trend = 10  # |10 − 50| ＝ 40
    bi.submit_action(low, "甲", "guan_hold")
    bi.submit_action(low, "乙", "huang_hold")
    bi.resolve_round(low, definition, random.Random(0))
    assert low.phase == "ended" and low.outcome_title == "黃巾得勝"

    high = _active_battle(definition)
    high.trend = 90
    bi.submit_action(high, "甲", "guan_hold")
    bi.submit_action(high, "乙", "huang_hold")
    bi.resolve_round(high, definition, random.Random(0))
    assert high.phase == "ended" and high.outcome_title == "官軍大勝"


def test_a_gauge_short_of_the_decisive_margin_neither_ends_nor_changes_act(definition):
    for start in (89, 11):  # 都還差一點（偏離 39）
        instance = _active_battle(definition)
        instance.trend = start
        bi.submit_action(instance, "甲", "guan_hold")
        bi.submit_action(instance, "乙", "huang_hold")
        bi.resolve_round(instance, definition, random.Random(0))
        assert instance.phase == "active" and instance.act_index == 0, start


def test_the_fallback_outcome_with_no_bounds_catches_a_stalemate(definition):
    instance = _active_battle(definition)
    _to_the_last_round(instance, definition)
    instance.trend = 50  # 不滿足前兩個 outcome 的範圍，落到保底的「僵持」
    bi.submit_action(instance, "甲", "guan_hold")
    bi.submit_action(instance, "乙", "huang_hold")
    bi.resolve_round(instance, definition, random.Random(0))
    assert instance.outcome_title == "僵持"


def _showdown_battle(definition: BattleDef) -> bi.BattleInstance:
    """甲站官軍、乙站黃巾；氣血給足，打滿九回合也不會有人倒下。"""
    instance = bi.start_muster(definition, now=0.0)
    for name, side in (("甲", "guan"), ("乙", "huang")):
        bi.join_faction(instance, name, side, neili_cap=10_000.0, scores={m: 100.0 for m in MOVES})
    bi.close_muster(instance, definition, random.Random(0))
    return instance


def _play(instance: bi.BattleInstance, definition: BattleDef, guan="guan_hold", huang="huang_hold") -> list[str]:
    """甲、乙各出一招並結算這一回合；預設兩邊都固守，推力互相抵銷。固守剋強攻：官軍固守對黃巾強攻推 +5，反過來 −5。"""
    bi.submit_action(instance, "甲", guan)
    bi.submit_action(instance, "乙", huang)
    return bi.resolve_round(instance, definition, random.Random(0))


def test_a_stalled_gauge_changes_act_every_three_rounds_and_ends_after_the_ninth(showdown):
    """FB-016：兩邊推力抵銷、戰局停在 50 時，以前永遠停在第一幕，只能拖到氣血磨光；現在照回合數換幕，
    第 3、6 回合結算完換幕，第 9 回合結算完看戰局收場，第 1～8 回合都不收場。"""
    instance = _showdown_battle(showdown)
    acts, phases, act_lines = [], [], []
    for _ in range(9):
        msgs = _play(instance, showdown)
        acts.append(instance.act_index)
        phases.append(instance.phase)
        act_lines.append([m for m in msgs if m.startswith("【")])
    assert instance.trend == 50
    assert acts == [0, 0, 1, 1, 1, 2, 2, 2, 2]
    assert phases == ["active"] * 8 + ["ended"]
    assert act_lines[2] == ["【鏖戰正酣】犬牙交錯。"] and act_lines[5] == ["【決勝時刻】最後一擊。"]
    assert sum(len(lines) for lines in act_lines) == 2  # 只換兩次幕
    assert instance.outcome_title == "兩軍膠著"


def test_the_final_act_is_fought_for_all_its_rounds(showdown):
    """以前一進最後一幕就判結果（最後那個無門檻的保底永遠成立），第三幕只打一回合。"""
    instance = _showdown_battle(showdown)
    for _ in range(7):  # 第 7 回合是第三幕的第一回合
        _play(instance, showdown)
    assert instance.act_index == 2 and instance.phase == "active"
    _play(instance, showdown)
    assert instance.phase == "active"


@pytest.mark.parametrize("start, guan, huang, title", [
    (86, "guan_hold", "huang_strong", "官軍大勝"),  # 86 + 5 = 91
    (14, "guan_strong", "huang_hold", "黃巾得勢"),  # 14 − 5 = 9
])
def test_a_lopsided_gauge_ends_the_battle_on_that_round(showdown, start, guan, huang, title):
    instance = _showdown_battle(showdown)
    _play(instance, showdown)
    instance.trend = start
    msgs = _play(instance, showdown, guan, huang)  # 第 2 回合
    assert instance.phase == "ended" and instance.outcome_title == title
    assert instance.round_number == 2 and instance.act_index == 0
    assert f"══ {title} ══" in msgs


def test_a_lopsided_gauge_on_an_act_change_round_ends_instead_of_changing_act(showdown):
    """剛好在該換幕的那一回合到門檻：當回合收場，不換幕（以前剛換幕的那回合不判終局）。"""
    instance = _showdown_battle(showdown)
    _play(instance, showdown)
    _play(instance, showdown)
    instance.trend = 88
    msgs = _play(instance, showdown, "guan_hold", "huang_strong")  # 第 3 回合：88 + 5 = 93
    assert instance.phase == "ended" and instance.outcome_title == "官軍大勝"
    assert instance.act_index == 0
    assert not any(m.startswith("【") for m in msgs)


@pytest.mark.parametrize("trend, title", [(65, "官軍大勝"), (35, "黃巾得勢"), (64, "兩軍膠著"), (36, "兩軍膠著")])
def test_the_ninth_round_settles_the_battle_by_where_the_gauge_stands(showdown, trend, title):
    instance = _showdown_battle(showdown)
    for _ in range(8):
        _play(instance, showdown)
    assert instance.phase == "active"
    instance.trend = trend
    _play(instance, showdown)  # 兩邊抵銷，戰局停在 trend
    assert instance.phase == "ended" and instance.outcome_title == title


@pytest.mark.parametrize("trend, title", [
    (100, "官軍大勝"), (65, "官軍大勝"), (64, "兩軍膠著"), (50, "兩軍膠著"), (36, "兩軍膠著"), (35, "黃巾得勢"), (0, "黃巾得勢"),
])
def test_decide_outcome_takes_the_first_outcome_the_gauge_falls_in(showdown, trend, title):
    instance = _showdown_battle(showdown)
    instance.trend = trend
    assert bi.decide_outcome(instance, showdown).title == title


def test_round_numbers_are_kept_on_the_battle_and_on_every_round_record(showdown):
    instance = _showdown_battle(showdown)
    assert instance.round_number == 0
    for _ in range(4):
        _play(instance, showdown)
    assert instance.round_number == 4
    assert [r.round_number for r in instance.rounds] == [1, 2, 3, 4]
    assert [r.act_index for r in instance.rounds] == [0, 0, 0, 1]  # 紀錄的是結算前那一幕


def test_rounds_per_act_and_decisive_margin_come_from_the_definition(showdown):
    showdown.rounds_per_act = 2
    showdown.decisive_margin = 20
    assert bi.total_rounds(showdown) == 6
    stalled = _showdown_battle(showdown)
    acts = []
    for _ in range(6):
        _play(stalled, showdown)
        acts.append(stalled.act_index)
    assert acts == [0, 1, 1, 2, 2, 2]
    assert stalled.phase == "ended" and stalled.round_number == 6

    lopsided = _showdown_battle(showdown)
    lopsided.trend = 66
    _play(lopsided, showdown, "guan_hold", "huang_strong")  # 66 + 5 = 71：偏離 20 以上就收場
    assert lopsided.phase == "ended" and lopsided.outcome_title == "官軍大勝"


# ── 沒有人能打：回合逾時就用保底結果收場 ─────────────────────


def _empty_active_battle(definition, now: float) -> bi.BattleInstance:
    instance = bi.start_muster(definition, now=0.0)
    bi.close_muster(instance, definition, random.Random(0), now=now)
    return instance


def test_end_without_fighters_uses_the_fallback_outcome_once_the_round_times_out(definition):
    definition.outcomes[-1].world_flags_add = ["stalemate"]
    definition.outcomes[-1].trend_delta = {"huangjin": 5}
    instance = _empty_active_battle(definition, now=600.0)
    instance.trend = 75  # 照戰局本該是「官軍大勝」；沒有人在場，一律用保底結果收場
    assert bi.end_without_fighters(instance, definition, now=600.0 + definition.round_seconds - 1) == []
    assert instance.phase == "active"
    msgs = bi.end_without_fighters(instance, definition, now=600.0 + definition.round_seconds)
    assert instance.phase == "ended"
    assert (instance.outcome_title, instance.outcome_text) == ("僵持", "不分勝負。")
    assert instance.outcome_world_flags == ["stalemate"]
    assert instance.outcome_trend_delta == {"huangjin": 5}
    assert "══ 僵持 ══" in msgs and "不分勝負。" in msgs
    assert "僵持" in instance.narrative_log[-1]


def test_end_without_fighters_also_ends_once_everyone_has_fallen(definition):
    instance = _active_battle(definition)
    for p in instance.participants.values():
        p.eliminated = True
    bi.end_without_fighters(instance, definition, now=definition.round_seconds)
    assert instance.phase == "ended" and instance.outcome_title == "僵持"


def test_end_without_fighters_leaves_a_battle_with_someone_still_standing_alone(definition):
    instance = _active_battle(definition)
    instance.participants["甲"].eliminated = True
    assert bi.end_without_fighters(instance, definition, now=10_000.0) == []
    assert instance.phase == "active" and instance.outcome_title is None


def test_end_without_fighters_does_nothing_during_muster(definition):
    instance = bi.start_muster(definition, now=0.0)
    assert bi.end_without_fighters(instance, definition, now=10_000.0) == []
    assert instance.phase == "muster"


# ── 機器人自動選擇 ───────────────────────────────────────


def test_bot_choose_action_returns_a_tag_from_the_available_options(definition):
    instance = _active_battle(definition)
    tag = bi.bot_choose_action(instance, definition, "甲", random.Random(0))
    assert tag in {"guan_strong", "guan_hold", "guan_raid"}


def test_bot_choose_action_returns_none_for_a_non_participant(definition):
    instance = _active_battle(definition)
    assert bi.bot_choose_action(instance, definition, "幽靈", random.Random(0)) is None


def test_the_free_text_judge_is_set_in_the_late_han(definition):
    instance = _active_battle(definition)
    client = mock.Mock()
    client.chat_structured.return_value = bi.SuccessRateJudgment(success_rate=40)
    bi.assess_action_success_rate(client, bi.current_act(instance, definition), "官軍", "從側翼包抄")
    system = client.chat_structured.call_args.args[0][0]["content"]
    assert "漢末" in system and "三國時代" not in system


# ── 回合紀錄（線上架構設計 3.1：戰鬥回合一筆一筆加）────────────────


def test_resolving_a_round_records_it(definition):
    instance = _active_battle(definition)
    bi.submit_action(instance, "甲", "guan_hold")
    bi.submit_action(instance, "乙", "huang_strong", text="直取波才首級")
    msgs = bi.resolve_round(instance, definition, random.Random(0), now=700.0)
    [record] = instance.rounds
    assert (record.act_index, record.resolved_real, record.trend_after) == (0, 700.0, instance.trend)
    assert record.actions == {"甲": "guan_hold", "乙": "huang_strong"}
    assert record.custom_texts == {"乙": "直取波才首級"}
    assert record.messages == msgs and record.id is None


def test_ending_without_fighters_records_the_closing_round(definition):
    instance = _empty_active_battle(definition, now=600.0)
    msgs = bi.end_without_fighters(instance, definition, now=600.0 + definition.round_seconds)
    [record] = instance.rounds
    assert record.actions == {} and record.messages == msgs


def test_ending_without_fighters_counts_the_timed_out_round(definition):
    instance = _active_battle(definition)
    bi.submit_action(instance, "甲", "guan_hold")
    bi.submit_action(instance, "乙", "huang_hold")
    bi.resolve_round(instance, definition, random.Random(0), now=100.0)
    for p in instance.participants.values():
        p.eliminated = True
    bi.end_without_fighters(instance, definition, now=100.0 + definition.round_seconds)
    assert instance.round_number == 2
    assert [r.round_number for r in instance.rounds] == [1, 2]


# ── 三場大戲（計畫 T8；戰鬥系統 4.1、4.2、5.3）────────────────────────────


@pytest.mark.parametrize(("lock", "trend", "expected"), [
    # 沒人鎖定：戰局決定誰贏與輕重；偏離 50 達 15 是大勝
    (None, 70, ("guan", "大勝")), (None, 55, ("guan", "險勝")), (None, 50, ("guan", "險勝")),
    (None, 45, ("huang", "險勝")), (None, 30, ("huang", "大勝")),
    # 官軍鎖定：官軍一定贏，戰場上也贏是大勝、打輸是險勝
    ("guan", 70, ("guan", "大勝")), ("guan", 55, ("guan", "大勝")), ("guan", 50, ("guan", "大勝")),
    ("guan", 45, ("guan", "險勝")), ("guan", 30, ("guan", "險勝")),
    # 黃巾鎖定
    ("huang", 70, ("huang", "險勝")), ("huang", 55, ("huang", "險勝")), ("huang", 50, ("huang", "險勝")),
    ("huang", 45, ("huang", "大勝")), ("huang", 30, ("huang", "大勝")),
    # 門檻剛好的格：65／35 是大勝，64／36 是險勝
    (None, 65, ("guan", "大勝")), (None, 64, ("guan", "險勝")), (None, 36, ("huang", "險勝")), (None, 35, ("huang", "大勝")),
])
def test_decide_result_table(showdown, lock, trend, expected):
    """戰鬥系統 4.1 的表（守方官軍：剛好 50 算官軍守住）；戰局以 factions[0]（官軍）為正向。"""
    instance = _showdown_battle(showdown)
    instance.trend = trend
    assert bi.decide_result(instance, showdown, lock, "guan") == expected


@pytest.mark.parametrize(("defender", "lock", "expected"), [
    ("guan", None, ("guan", "險勝")), ("huang", None, ("huang", "險勝")),  # 剛好 50 算守方守住（4.2）
    ("huang", "guan", ("guan", "險勝")), ("guan", "huang", ("huang", "險勝")),  # 戰場上是守方贏：鎖定方只能險勝
    ("guan", "guan", ("guan", "大勝")), ("huang", "huang", ("huang", "大勝")),
])
def test_tie_goes_to_defender(showdown, defender, lock, expected):
    instance = _showdown_battle(showdown)
    instance.trend = 50
    assert bi.decide_result(instance, showdown, lock, defender) == expected


def test_a_lock_from_a_side_not_in_the_battle_counts_as_no_lock(showdown):
    instance = _showdown_battle(showdown)
    instance.trend = 30
    assert bi.decide_result(instance, showdown, "haoqiang", "guan") == ("huang", "大勝")


@pytest.mark.parametrize(("front", "start"), [(40, 55), (35, 58), (55, 48), (30, 60), (20, 65), (50, 50), (0, 75), (100, 25)])
def test_start_follows_the_front_value(front, start):
    """戰鬥系統 5.3：起點＝50 ＋（50 − 戰況）÷ 2，用 int(x + 0.5) 進位（57.5 → 58、47.5 → 48）。"""
    assert bi.start_from_front(front) == start


def test_start_muster_takes_a_trend_start(showdown):
    """start_muster 多一個 trend_start：給了就用它當這一場的起點，不給照 definition.trend_start（beta 那場不變）。"""
    assert bi.start_muster(showdown, now=0.0).trend == 50
    instance = bi.start_muster(showdown, now=0.0, trend_start=58)
    assert instance.trend == 58
    bi.close_muster(instance, showdown, random.Random(0))
    assert instance.trend == 58  # 集結結束也不重設


def test_early_end_at_ninety_or_ten(showdown):
    """提前收場看 50（戰鬥系統 5.3）：起點 58 的一場，到 90 就收（舊規則偏離起點 40 要到 98），到 17 不收（舊規則會收），
    到 10 以下才收；起點 50 的 beta 那場收場時機跟以前一樣。每回合官軍固守對黃巾強攻推 +5，反過來 −5。"""
    def played(start: int, trend: int, guan="guan_hold", huang="huang_hold") -> bi.BattleInstance:
        instance = bi.start_muster(showdown, now=0.0, trend_start=start)
        for name, side in (("甲", "guan"), ("乙", "huang")):
            bi.join_faction(instance, name, side, neili_cap=10_000.0, scores={m: 100.0 for m in MOVES})
        bi.close_muster(instance, showdown, random.Random(0))
        instance.trend = trend
        _play(instance, showdown, guan, huang)
        return instance

    up, down = ("guan_hold", "huang_strong"), ("guan_strong", "huang_hold")
    assert played(58, 85, *up).phase == "ended"  # 85 + 5 = 90
    assert played(58, 84, *up).phase == "active"  # 89
    assert played(58, 22, *down).phase == "active"  # 22 − 5 = 17：舊規則（偏離起點 40）會收
    assert played(58, 15, *down).phase == "ended"  # 10
    for trend, phase in ((85, "ended"), (84, "active"), (15, "ended"), (16, "active")):  # beta 那場：起點 50
        assert played(50, trend, *(up if trend > 50 else down)).phase == phase, trend


# ── 決戰改版 5：地方豪強第三方（戰鬥系統第六節）──────────────────────────


@pytest.fixture
def with_third(three) -> BattleDef:
    """three 加上第三方「hao」（推 geju）。"""
    return three.model_copy(update={"third": ThirdParty(faction="hao", trend="geju")})


def test_sides_include_the_third_party(with_third, three):
    assert bi.sides(with_third) == ["guan", "huang", "hao"]
    assert bi.sides(three) == ["guan", "huang"]


def test_the_third_party_gets_its_own_two_moves(with_third):
    battle = bi.start_muster(with_third, now=0)
    bi.join_faction(battle, "丙", "hao", neili_cap=1000, scores={m: 100.0 for m in MOVES})
    bi.close_muster(battle, with_third, random.Random(0), now=0)
    options = bi.options_for(battle, with_third, "丙")
    assert [(o.tag, o.text, o.move) for o in options] == [
        (bi.THIRD_GRAB, "趁亂搶地盤", "奇襲"), (bi.THIRD_KEEP, "保存實力", "固守"),
    ]


def test_the_armies_never_get_the_third_partys_moves(with_third):
    battle = bi.start_muster(with_third, now=0)
    bi.join_faction(battle, "甲", "guan", neili_cap=1000)
    bi.close_muster(battle, with_third, random.Random(0), now=0)
    assert {o.tag for o in bi.options_for(battle, with_third, "甲")} == {"guan_strong", "guan_hold", "guan_raid"}
    assert not bi.is_third(with_third, battle.participants["甲"])


def test_the_third_party_stays_itself_at_muster_and_late(with_third):
    """Review Focus 4。"""
    battle = bi.start_muster(with_third, now=0)
    bi.join_faction(battle, "丙", "hao", neili_cap=1000)
    bi.close_muster(battle, with_third, random.Random(0), now=0)
    assert battle.participants["丙"].faction == "hao"
    bi.auto_assign_latecomer(battle, with_third, "丁", 1000, random.Random(0), faction="hao")
    bi.auto_assign_latecomer(battle, with_third, "戊", 1000, random.Random(0))
    assert battle.participants["丁"].faction == "hao"
    assert battle.participants["戊"].faction in ("guan", "huang")  # 沒指定的照舊只補兩軍


def test_nobody_is_pushed_into_the_third_party_when_the_muster_closes_or_a_latecomer_arrives(with_third):
    """Review Focus 4 的鏡像：沒選邊（陣營不認得）的人退回亂數分配，只分到兩軍，不會被分去第三方；
    晚到的人沒指定陣營時，人數的平衡也只看兩軍。"""
    battle = bi.start_muster(with_third, now=0)
    for i in range(40):
        bi.join_faction(battle, f"散{i}", "nobody", neili_cap=1000)
    bi.close_muster(battle, with_third, random.Random(0), now=0)
    assert {p.faction for p in battle.participants.values()} <= {"guan", "huang"}
    for i in range(40):
        bi.auto_assign_latecomer(battle, with_third, f"遲{i}", 1000, random.Random(i))
    assert all(p.faction in ("guan", "huang") for p in battle.participants.values())


def test_a_late_third_party_keeps_its_strength_when_timed_out(with_third):
    battle = bi.start_muster(with_third, now=0)
    bi.join_faction(battle, "丙", "hao", neili_cap=1000)
    bi.close_muster(battle, with_third, random.Random(0), now=0)
    bi.fill_timed_out_actions(battle, with_third)
    assert battle.round.pending_actions["丙"] == bi.THIRD_KEEP and "丙" in battle.round.auto_picked


def test_stalemate_is_one_at_the_centre_and_zero_at_the_ends():
    assert bi.stalemate(50) == 1.0 and bi.stalemate(75) == 0.5 and bi.stalemate(0) == 0.0 and bi.stalemate(100) == 0.0


def _three_way(definition, people, trend=50, neili=None, before=0, with_msgs=False, tuning=None):
    """people：[(名號, 陣營, 出什麼)]，出什麼是三招之一、THIRD_GRAB 或 THIRD_KEEP。每個人每招的份量都是 100。
    before：結算前已經打了幾回合。結算一回合，回傳這一場（with_msgs 時另外回傳 resolve_round 給大家看的那幾句）。"""
    battle = bi.start_muster(definition, now=0)
    for name, side, _ in people:
        bi.join_faction(battle, name, side, neili_cap=1000, scores={m: 100.0 for m in MOVES})
    bi.close_muster(battle, definition, random.Random(0), now=0)
    battle.trend, battle.round_number = trend, before
    for name, value in (neili or {}).items():
        battle.participants[name].neili = value
    for name, side, what in people:
        bi.submit_action(battle, name, what if what in (bi.THIRD_GRAB, bi.THIRD_KEEP) else f"{side}_{CODES[what]}")
    msgs = bi.resolve_round(battle, definition, random.Random(0), now=1, tuning=tuning or BattleTuning())
    return (battle, msgs) if with_msgs else battle


ARMIES = [("甲", "guan", "強攻"), ("乙", "huang", "強攻")]  # 兩邊一樣：推 0，戰局停在原地


def test_the_third_party_never_moves_the_trend(with_third, three):
    """Review Focus 1：同一回合加上第三方，戰局與兩軍的出招比例都不變。"""
    plain = _three_way(three, [("甲", "guan", "強攻"), ("乙", "huang", "固守")])
    mixed = _three_way(with_third, [("甲", "guan", "強攻"), ("乙", "huang", "固守"), ("丙", "hao", bi.THIRD_GRAB)])
    assert mixed.trend == plain.trend and mixed.last_mix == plain.last_mix
    assert "hao" not in mixed.last_mix


def test_grabbing_uses_the_raid_share_and_costs_thirty_five(with_third):
    battle = _three_way(with_third, ARMIES + [("丙", "hao", bi.THIRD_GRAB)])
    assert battle.third_gain == pytest.approx(100.0)  # 100 ÷ √1 × 膠著 1
    assert battle.participants["丙"].neili == 1000 - 35
    assert battle.participants["丙"].last_result == "趁亂搶地盤"
    assert battle.participants["丙"].acted_rounds == 1  # 數一次：主迴圈要跳過第三方，不然豪強被數兩次
    assert any("趁亂搶地盤 1 人" in m for m in battle.rounds[-1].messages)


def test_the_warlords_costs_are_their_own_tuning_numbers_not_the_raids_and_the_holds(with_third):
    """搶地盤扣 third_grab_damage、保存實力扣 third_keep_damage：預設的 35 剛好等於奇襲的損耗，所以改成不一樣來測；
    保存實力的份量折數也讀 third_keep_share。"""
    tuning = BattleTuning(third_grab_damage=50.0, third_keep_damage=20.0, third_keep_share=0.25)
    assert tuning.damage["奇襲"] == 35.0 and tuning.damage["固守"] == 15.0
    battle = _three_way(
        with_third, ARMIES + [("丙", "hao", bi.THIRD_GRAB), ("丁", "hao", bi.THIRD_KEEP)], tuning=tuning,
    )
    assert battle.participants["丙"].neili == 1000 - 50
    assert battle.participants["丁"].neili == 1000 - 20
    assert battle.third_gain == pytest.approx((100.0 + 25.0) / math.sqrt(2))  # 搶 100、保存實力 100×0.25


def test_keeping_strength_counts_half_and_costs_ten(with_third):
    battle = _three_way(with_third, ARMIES + [("丙", "hao", bi.THIRD_KEEP)])
    assert battle.third_gain == pytest.approx(50.0)
    assert battle.participants["丙"].neili == 1000 - 10
    assert battle.participants["丙"].last_result == "保存實力"


def test_more_warlords_gain_by_the_square_root(with_third):
    battle = _three_way(with_third, ARMIES + [("丙", "hao", bi.THIRD_GRAB), ("丁", "hao", bi.THIRD_GRAB)])
    assert battle.third_gain == pytest.approx(200 / math.sqrt(2))


def test_a_lopsided_battle_gives_less(with_third):
    battle = _three_way(with_third, ARMIES + [("丙", "hao", bi.THIRD_GRAB)], trend=75)
    assert battle.third_gain == pytest.approx(50.0)  # 膠著 0.5


@pytest.mark.parametrize("side, name, trend", [("guan", "甲", 60), ("huang", "乙", 40)])
def test_the_warlords_still_gain_when_only_one_army_acts(with_third, side, name, trend):
    """只有一邊有人出手（另一邊全離開大區或全放手一搏）時，豪強照樣有收穫：沒人對打時一邊推滿 10（戰局 60 或 40），
    膠著 0.8，收穫 100 × 0.8。要求兩邊都有人才給收穫是另一種規則（Review Focus 3 只說兩邊都沒人才是 0）。"""
    battle = _three_way(with_third, [(name, side, "強攻"), ("丙", "hao", bi.THIRD_GRAB)])
    assert battle.trend == trend
    assert battle.third_gain == pytest.approx(80.0)


def test_the_stalemate_is_read_from_the_trend_after_the_round(with_third):
    """膠著照這一回合結算完的戰局算，不是結算前的那一格：官軍強攻對黃巾固守會動戰局（不再停在 50），收穫就小於膠著 1 的 100。
    其他收穫的測試兩軍出一樣的招、推力是 0，戰局前後都是 50，分不出這兩種算法。"""
    battle = _three_way(with_third, [("甲", "guan", "強攻"), ("乙", "huang", "固守"), ("丙", "hao", bi.THIRD_GRAB)])
    assert battle.trend != 50  # 這一回合真的把戰局推動了
    assert battle.third_gain == pytest.approx(100.0 * bi.stalemate(battle.trend))
    assert battle.third_gain < 100.0


def test_no_armies_no_gain(with_third):
    """Review Focus 3：這一回合兩軍沒有人出手，就沒有亂可趁。"""
    battle = _three_way(with_third, [("丙", "hao", bi.THIRD_GRAB)])
    assert battle.third_gain == 0.0


def test_the_push_is_settled_when_the_battle_ends(with_third):
    """three 一幕九回合：已經打了 8 回合，這一回合打完就收場。之前累積 250，這回合再 100 → 3.5 → 4。"""
    battle = bi.start_muster(with_third, now=0)
    for name, side, _ in ARMIES + [("丙", "hao", bi.THIRD_GRAB)]:
        bi.join_faction(battle, name, side, neili_cap=1000, scores={m: 100.0 for m in MOVES})
    bi.close_muster(battle, with_third, random.Random(0), now=0)
    battle.round_number, battle.third_gain = 8, 250.0
    for name, side, what in ARMIES + [("丙", "hao", bi.THIRD_GRAB)]:
        bi.submit_action(battle, name, what if what == bi.THIRD_GRAB else f"{side}_{CODES[what]}")
    msgs = bi.resolve_round(battle, with_third, random.Random(0), now=1, tuning=BattleTuning())
    assert battle.phase == "ended" and battle.third_push == 4
    assert msgs[-1] == "兩軍相持之際，地方上有人趁亂坐大。"  # 收場那一句只在真的推了割據時出現，不寫數字


def test_a_battle_that_gave_the_warlords_nothing_says_nothing_about_them(with_third, three):
    battle = bi.start_muster(with_third, now=0)
    assert bi.settle_third(battle, with_third, BattleTuning()) == [] and battle.third_push == 0
    battle = bi.start_muster(three, now=0)
    battle.third_gain = 5000.0
    assert bi.settle_third(battle, three, BattleTuning()) == [] and battle.third_push == 0  # 沒有第三方的決戰不推


def test_the_push_is_capped_at_ten(with_third):
    """Review Focus 2（計畫寫的測試名）：收穫再多，割據也只推 10。"""
    battle = bi.start_muster(with_third, now=0)
    battle.third_gain = 5000.0
    bi.settle_third(battle, with_third, BattleTuning())
    assert battle.third_push == 10


def test_the_push_rounds_half_up(with_third):
    """÷100 後四捨五入（0.5 進位，不是銀行家進位）；一場最多 third_cap。"""
    battle = bi.start_muster(with_third, now=0)
    for gain, push in ((49.9, 0), (50.0, 1), (150.0, 2), (250.0, 3), (1049.0, 10), (5000.0, 10)):
        battle.third_gain = gain
        bi.settle_third(battle, with_third, BattleTuning())
        assert battle.third_push == push, gain


def test_the_ending_round_pushes_by_the_configured_cap(with_third):
    """resolve_round 收場的那一支也吃 Config.battle 的 third_cap（不是預設的 10）：之前累積 250、這回合再 100 → 4，
    上限寫 2 就只推 2。（end_without_fighters 那一支的 tuning 在 test_engine 看。）"""
    battle = bi.start_muster(with_third, now=0)
    for name, side, _ in ARMIES + [("丙", "hao", bi.THIRD_GRAB)]:
        bi.join_faction(battle, name, side, neili_cap=1000, scores={m: 100.0 for m in MOVES})
    bi.close_muster(battle, with_third, random.Random(0), now=0)
    battle.round_number, battle.third_gain = 8, 250.0
    for name, side, what in ARMIES + [("丙", "hao", bi.THIRD_GRAB)]:
        bi.submit_action(battle, name, what if what == bi.THIRD_GRAB else f"{side}_{CODES[what]}")
    bi.resolve_round(battle, with_third, random.Random(0), now=1, tuning=BattleTuning(third_cap=2))
    assert battle.phase == "ended" and battle.third_push == 2


def test_only_the_third_party_left_ends_the_battle(with_third):
    """Review Focus 3：場上只剩第三方，回合一逾時就照保底收場。"""
    battle = bi.start_muster(with_third, now=0)
    bi.join_faction(battle, "丙", "hao", neili_cap=1000)
    bi.close_muster(battle, with_third, random.Random(0), now=0)
    msgs = bi.end_without_fighters(battle, with_third, now=with_third.round_seconds + 1)
    assert msgs and battle.phase == "ended"


def test_the_armies_all_fallen_leaves_the_warlords_no_battle_to_profit_from(with_third):
    """兩軍的人全倒下了、豪強還站著：照樣是「沒人能打」，逾時收場，之前累積的收穫換成推動。"""
    battle = bi.start_muster(with_third, now=0)
    for name, side in (("甲", "guan"), ("乙", "huang"), ("丙", "hao")):
        bi.join_faction(battle, name, side, neili_cap=1000)
    bi.close_muster(battle, with_third, random.Random(0), now=0)
    battle.participants["甲"].eliminated = battle.participants["乙"].eliminated = True
    battle.third_gain = 250.0
    assert bi.end_without_fighters(battle, with_third, now=1) == []  # 回合還沒逾時
    msgs = bi.end_without_fighters(battle, with_third, now=with_third.round_seconds + 1, tuning=BattleTuning())
    assert battle.phase == "ended" and battle.third_push == 3
    assert "兩軍相持之際，地方上有人趁亂坐大。" in msgs


def test_the_armies_still_standing_keep_the_battle_going_whatever_the_warlords_do(with_third):
    battle = bi.start_muster(with_third, now=0)
    for name, side in (("甲", "guan"), ("丙", "hao")):
        bi.join_faction(battle, name, side, neili_cap=1000)
    bi.close_muster(battle, with_third, random.Random(0), now=0)
    battle.participants["丙"].eliminated = True
    assert bi.end_without_fighters(battle, with_third, now=with_third.round_seconds + 1) == []
    assert battle.phase == "active"


def test_a_warlord_can_fall(with_third):
    battle = _three_way(with_third, ARMIES + [("丙", "hao", bi.THIRD_GRAB)], neili={"丙": 30})
    assert battle.participants["丙"].eliminated and battle.participants["丙"].fell_round == 1
    assert battle.third_gain == pytest.approx(51.5)  # 份量在扣血之前算、倒下也算他出過手：氣血 30／1000 的狀態是 0.515


def test_a_timed_out_warlord_keeps_its_strength_and_is_not_counted_as_acting(with_third):
    battle = bi.start_muster(with_third, now=0)
    for name, side, _ in ARMIES + [("丙", "hao", bi.THIRD_GRAB)]:
        bi.join_faction(battle, name, side, neili_cap=1000, scores={m: 100.0 for m in MOVES})
    bi.close_muster(battle, with_third, random.Random(0), now=0)
    for name, side, what in ARMIES:
        bi.submit_action(battle, name, f"{side}_{CODES[what]}")
    bi.fill_timed_out_actions(battle, with_third)  # 豪強逾時：代出保存實力
    bi.resolve_round(battle, with_third, random.Random(0), now=1, tuning=BattleTuning())
    warlord = battle.participants["丙"]
    assert warlord.neili == 1000 - 10 and warlord.acted_rounds == 0
    assert battle.third_gain == pytest.approx(50.0)


SETTLE_LINE = "兩軍相持之際，地方上有人趁亂坐大。"


def _told_to_everyone(msgs, warlords):
    """這一回合發給大家的訊息，拿掉豪強自己的倒下句與收場那一句：這兩句本來就公開（審查 N4，倒下句跟兩軍的人倒下是同一個寫法，
    收場句只在割據真的動了時出現、不寫數字）；其他一個字都不該因為場上有豪強而不同。"""
    return [m for m in msgs if m != SETTLE_LINE and not any(m.startswith(f"{name}氣血耗盡") for name in warlords)]


@pytest.mark.parametrize("warlords, before, neili", [
    ([("丙", "hao", bi.THIRD_GRAB)], 0, None),
    ([("丙", "hao", bi.THIRD_KEEP)], 0, None),
    ([("丙", "hao", bi.THIRD_GRAB), ("丁", "hao", bi.THIRD_KEEP), ("戊", "hao", bi.THIRD_GRAB)], 0, None),
    ([("丙", "hao", bi.THIRD_GRAB), ("丁", "hao", bi.THIRD_KEEP)], 0, {"丙": 30}),  # 一位豪強這回合倒下
    ([("丙", "hao", bi.THIRD_GRAB), ("丁", "hao", bi.THIRD_KEEP)], 8, None),  # 打完最後一回合：收場
])
def test_the_warlords_change_nothing_anyone_is_told(with_third, three, warlords, before, neili):
    """兩軍與場景不該知道豪強選了什麼，也不該知道有幾個豪強、收穫多少：同一回合加不加豪強，resolve_round 回傳給大家看的訊息
    （會進場景的記錄與給模型的判定）、場景的記錄、戰局與出招比例都一樣，除了豪強自己的倒下句與收場句。
    不比對招名字串：換個說法的洩漏（例如「地方上有 2 人蠢蠢欲動」）也會讓這裡失敗。"""
    armies = [("甲", "guan", "強攻"), ("乙", "huang", "固守")]
    plain, plain_msgs = _three_way(three, armies, before=before, with_msgs=True)
    mixed, mixed_msgs = _three_way(with_third, armies + warlords, before=before, neili=neili, with_msgs=True)
    assert _told_to_everyone(mixed_msgs, [name for name, _, _ in warlords]) == plain_msgs
    assert mixed.narrative_log == plain.narrative_log
    assert (mixed.trend, mixed.last_mix, mixed.phase) == (plain.trend, plain.last_mix, plain.phase)
    # 例外只有那兩句：收場時說了收場句、倒下時說了倒下句，其餘一樣
    if before:
        assert mixed_msgs[-1] == SETTLE_LINE and mixed.third_push >= 1
    if neili:
        assert "丙氣血耗盡，倒在戰場上，退出了這場戰鬥（轉為觀戰）。" in mixed_msgs


def test_what_the_warlords_picked_only_reaches_the_round_record(with_third):
    """豪強選了搶地盤還是保存實力只寫進回合紀錄（battle_rounds 只寫不讀回，玩家看不到）。"""
    battle, msgs = _three_way(with_third, ARMIES + [("丙", "hao", bi.THIRD_GRAB), ("丁", "hao", bi.THIRD_KEEP)], with_msgs=True)
    assert not any("趁亂搶地盤" in m or "保存實力" in m for m in msgs)
    assert "趁亂搶地盤 1 人、保存實力 1 人。" in battle.rounds[-1].messages
    assert not any("趁亂搶地盤" in line or "保存實力" in line for line in battle.narrative_log)


# ── 輸贏要看得懂、等待要看得出在等人（試玩回饋 2026-10-08）──────────────────


def _summary(msgs):
    return next(m for m in msgs if m.startswith("這一回合"))


def test_the_round_summary_names_a_counter(three):
    msgs = _fight(three, [("甲", "guan", "強攻"), ("乙", "huang", "固守")]).rounds[-1].messages
    assert _summary(msgs) == "這一回合黃巾佔了上風（戰局 50→45）：黃巾的固守剋住了官軍的強攻，乙一馬當先。"


def test_the_round_summary_names_the_numbers_when_nobody_counters(three):
    picks = [(f"官{i}", "guan", "固守") for i in range(4)] + [("乙", "huang", "固守")]
    msgs = _fight(three, picks).rounds[-1].messages
    assert _summary(msgs) == "這一回合官軍佔了上風（戰局 50→53）：官軍人多勢眾（4 人對 1 人），官3等 4 人結成固守陣勢。"


def test_the_round_summary_says_the_other_side_did_not_come_out(three):
    battle = _two_fighters(three)
    bi.submit_action(battle, "甲", "guan_hold")
    bi.fill_timed_out_actions(battle, three)  # 乙沒出手：被代選固守
    battle.participants["乙"].away = True  # 這一回合走開了：不算出手
    battle.round.pending_actions.pop("乙")
    msgs = bi.resolve_round(battle, three, random.Random(0), now=1, tuning=BattleTuning())
    assert _summary(msgs) == "這一回合官軍佔了上風（戰局 50→60）：黃巾沒有人正面出陣迎戰，官軍放手壓了上去，甲帶頭固守。"


def test_the_round_summary_counts_the_ones_who_never_gave_an_order(three):
    battle = _two_fighters(three)
    bi.submit_action(battle, "甲", "guan_raid")  # 奇襲剋固守：乙逾時被代為固守
    bi.fill_timed_out_actions(battle, three)
    msgs = bi.resolve_round(battle, three, random.Random(0), now=1, tuning=BattleTuning())
    assert _summary(msgs) == (
        "這一回合官軍佔了上風（戰局 50→55）：官軍的奇襲剋住了黃巾的固守，甲一馬當先；黃巾有 1 人遲遲沒有下令，只能原地固守。"
    )


def test_the_round_summary_tells_a_weaker_side_from_a_worn_out_one(three):
    battle = _two_fighters(three)
    battle.participants["乙"].neili = 30  # 份量一樣，乙只剩一成氣血
    bi.submit_action(battle, "甲", "guan_hold")
    bi.submit_action(battle, "乙", "huang_hold")
    msgs = bi.resolve_round(battle, three, random.Random(0), now=1, tuning=BattleTuning())
    assert _summary(msgs).endswith("：黃巾氣血耗損，漸漸撐不住官軍，甲帶頭固守。")
    stronger = _two_fighters(three)
    stronger.participants["甲"].scores = {m: 90.0 for m in MOVES}
    bi.submit_action(stronger, "甲", "guan_hold")
    bi.submit_action(stronger, "乙", "huang_hold")
    msgs = bi.resolve_round(stronger, three, random.Random(0), now=1, tuning=BattleTuning())
    assert _summary(msgs).endswith("：官軍的武藝更勝一籌，甲帶頭固守。")


def test_the_round_summary_counts_the_gambles_per_side(three):
    gamble = three.model_copy(deep=True)
    gamble.acts[0].options.append(BattleOption(text="放手一搏", tag="guan_reckless", faction="guan", free_text=True))
    gamble.free_text_gamble = FreeTextGamble()
    battle = _two_fighters(gamble)
    battle.participants["甲"].neili_cap = battle.participants["甲"].neili = 10_000
    bi.submit_action(battle, "甲", "guan_reckless", text="分兵埋伏", success_rate=0)  # 一定失敗
    bi.submit_action(battle, "乙", "huang_hold")
    msgs = bi.resolve_round(battle, gamble, random.Random(0), now=1, tuning=BattleTuning())
    # 官軍唯一的人在賭：黃巾的固守推滿 10，再加上官軍賭輸倒退 1
    assert _summary(msgs) == (
        "這一回合黃巾佔了上風（戰局 50→39）：官軍沒有人正面出陣迎戰，黃巾放手壓了上去，乙帶頭固守；官軍有人放手一搏失手，戰局倒退了 1。"
    )
    assert "甲這一搏失敗了，付出了慘痛代價：官軍的戰局倒退 1，自己氣血 -3500。" in msgs


def test_a_battle_records_how_each_round_swung_and_names_the_key_rounds(three):
    battle = _two_fighters(three)
    for guan, huang in (("guan_strong", "huang_hold"), ("guan_raid", "huang_hold"), ("guan_raid", "huang_hold")):
        bi.submit_action(battle, "甲", guan)
        bi.submit_action(battle, "乙", huang)
        bi.resolve_round(battle, three, random.Random(0), now=1, tuning=BattleTuning())
    assert [s.round for s in battle.swings] == [1, 2, 3] and [s.delta for s in battle.swings] == [-5, 4, 4]
    battle.trend = 53  # 官軍贏：挑往官軍推最多的兩回合，照回合先後寫
    assert bi.outcome_reason(battle, three) == (
        "勝負的關鍵：第 2 回合，官軍的奇襲剋住了黃巾的固守，甲一馬當先；第 3 回合，官軍的奇襲剋住了黃巾的固守，甲一馬當先。"
    )
    battle.trend = 50
    assert bi.outcome_reason(battle, three) == ""  # 停在中線：不寫


def test_the_outcome_reason_mentions_a_head_start_and_lands_in_the_closing_messages(three):
    one = three.model_copy(deep=True)
    one.rounds_per_act = 1  # 一回合就收場
    battle = bi.start_muster(one, now=0, trend_start=58)
    assert battle.trend_start == 58
    for name, side in (("甲", "guan"), ("乙", "huang")):
        bi.join_faction(battle, name, side, neili_cap=300, scores={m: 50.0 for m in MOVES})
    bi.close_muster(battle, one, random.Random(0), now=0)
    bi.submit_action(battle, "甲", "guan_raid")
    bi.submit_action(battle, "乙", "huang_hold")
    msgs = bi.resolve_round(battle, one, random.Random(0), now=1, tuning=BattleTuning())
    assert battle.phase == "ended"
    reason = "勝負的關鍵：開戰時官軍就佔了地利（戰局從 58 起算）；第 1 回合，官軍的奇襲剋住了黃巾的固守，甲一馬當先。"
    assert battle.outcome_reason == reason and msgs[-1] == reason


def test_a_locked_result_that_the_field_disagrees_with_gets_its_own_reason(three):
    battle = bi.start_muster(three, now=0)
    battle.trend = 60  # 戰場上官軍佔上風
    assert bi.overruled_reason(battle, three, "huang", "guan") == "勝負的關鍵：戰場上官軍佔了上風，卻沒能扭轉大局。"
    assert bi.overruled_reason(battle, three, "guan", "guan") == ""
    assert bi.overruled_reason(battle, three, None, "guan") == ""


def test_round_progress_counts_who_has_sent_among_those_present(three):
    battle = _two_fighters(three)
    battle.participants["丙"] = bi.BattleParticipant(name="丙", faction="guan", neili=1, neili_cap=1, away=True)
    assert bi.round_progress(battle, three) == (0, 2)  # 離開大區的不算在場
    bi.submit_action(battle, "甲", "guan_hold")
    assert bi.round_progress(battle, three) == (1, 2)
    battle.participants["乙"].eliminated = True
    assert bi.round_progress(battle, three) == (1, 1)


# ── 放手一搏只小小影響大局、主要傷自己（試玩回饋 2026-10-08）────────────────


CONTENT_DIR = Path(__file__).resolve().parent.parent / "content"


def _gamblers(n_guan, n_huang, cap=300.0):
    gamble = _gamble_three()
    battle = bi.start_muster(gamble, now=0)
    for i in range(n_guan):
        bi.join_faction(battle, f"官{i}", "guan", neili_cap=cap, scores={m: 50.0 for m in MOVES})
    for i in range(n_huang):
        bi.join_faction(battle, f"黃{i}", "huang", neili_cap=cap, scores={m: 50.0 for m in MOVES})
    bi.close_muster(battle, gamble, random.Random(0), now=0)
    return gamble, battle


def _gamble_three():
    options = [
        BattleOption(text=f"{side}{move}", tag=f"{side}_{CODES[move]}", faction=side, move=move)
        for side in ("guan", "huang") for move in MOVES
    ] + [BattleOption(text="放手一搏", tag=f"{side}_reckless", faction=side, free_text=True) for side in ("guan", "huang")]
    return BattleDef(
        id="gamble3", name="放手一搏之戰",
        factions=[BattleFaction(id="guan", name="官軍"), BattleFaction(id="huang", name="黃巾")],
        acts=[BattleAct(id="a1", title="對陣", text="兩軍對陣。", goal="推動戰局", options=options)],
        rounds_per_act=9, decisive_margin=40, free_text_gamble=FreeTextGamble(),
        outcomes=[
            BattleOutcome(faction="guan", trend_min=65, title="官軍大勝", text="官軍獲勝。"),
            BattleOutcome(faction="huang", trend_max=35, title="黃巾得勢", text="黃巾獲勝。"),
            BattleOutcome(faction="guan", title="兩軍膠著", text="不分勝負。"),
        ],
    )


def test_one_failed_gamble_barely_moves_the_battle_and_mostly_hurts_the_gambler():
    gamble, battle = _gamblers(2, 2)
    bi.submit_action(battle, "官0", "guan_reckless", text="直取張角首級", success_rate=0)
    for name in ("官1", "黃0", "黃1"):
        bi.submit_action(battle, name, f"{battle.participants[name].faction}_hold")
    msgs = bi.resolve_round(battle, gamble, FixedRandom(0.999), now=1, tuning=BattleTuning())
    # 三招：官軍只剩一人固守、黃巾兩人，推 −2（少了一個人出固定招）；失手最多倒退 1
    assert battle.trend == 50 - 2 - 1
    assert "官0這一搏失敗了，付出了慘痛代價：官軍的戰局倒退 1，自己氣血 -105。" in msgs  # 300 × (0.1 + 100 × 0.0025)
    assert battle.participants["官0"].neili == 195


def test_a_wild_gambler_survives_two_failures_and_falls_on_the_third():
    """成功率 0 失手一次扣 35%（試玩回饋 2026-10-08：亂寫的人至少還能多玩幾回合），第三次才倒下。"""
    gamble, battle = _gamblers(2, 2)
    for turn in range(3):
        bi.submit_action(battle, "官0", "guan_reckless", text="單騎衝陣", success_rate=0)
        for name in ("官1", "黃0", "黃1"):
            bi.submit_action(battle, name, f"{battle.participants[name].faction}_hold")
        msgs = bi.resolve_round(battle, gamble, FixedRandom(0.999), now=1, tuning=BattleTuning())
        assert battle.participants["官0"].eliminated == (turn == 2)
    assert "官0氣血耗盡，倒在戰場上，退出了這場戰鬥（轉為觀戰）。" in msgs


def test_a_whole_side_failing_its_gambles_in_one_round_falls_back_at_most_five():
    gamble, battle = _gamblers(6, 6)
    for i in range(6):
        bi.submit_action(battle, f"官{i}", "guan_reckless", text="亂衝", success_rate=0)
        bi.submit_action(battle, f"黃{i}", "huang_hold")
    msgs = bi.resolve_round(battle, gamble, FixedRandom(0.999), now=1, tuning=BattleTuning())
    assert battle.trend == 50 - 10 - 5  # 官軍沒人正面出陣：黃巾推滿 10；六人失手本來 -6，一回合最多 -5
    assert "各路奇招互相牽扯，官軍這一回合放手一搏合起來只倒退了 5。" in msgs


def test_a_successful_gamble_is_still_worth_more_than_one_failure_costs():
    gamble = FreeTextGamble()
    for rate in (0, 5, 45, 80):
        risk = 100 - rate
        win = gamble.success_trend_base + round(risk * gamble.success_trend_per_risk)
        loss = min(gamble.failure_trend_cap, round(risk * gamble.failure_trend_per_risk))
        assert win > loss
        assert win <= gamble.success_trend_base + round(100 * gamble.success_trend_per_risk) <= 8


def test_the_playtest_battle_replayed_is_no_longer_a_rout_for_the_yellow_turbans():
    """試玩回饋 2026-10-08 那一場：12 個官軍，前五回合各有一人放手一搏、成功率 45／5／0／0／0 全失手，其餘出固定招；
    黃巾的固定招跟官軍不相上下（每回合只動 ±1 上下）。舊公式累計 −45、戰局 50→5、黃巾得勢；現在五次失手一共倒退 5，
    失手的人氣血變少、之後固守的份量變弱，戰局滑到 45，兩軍膠著。"""
    gamble, battle = _gamblers(12, 12)
    real = load_content(CONTENT_DIR).battles["huangjin_showdown"]
    gamble.free_text_gamble = real.free_text_gamble  # 照正式內容的數值
    rates = [45, 5, 0, 0, 0]
    for r in range(9):
        for i in range(12):
            if r < len(rates) and i == r:
                bi.submit_action(battle, f"官{i}", "guan_reckless", text="可唔可以快少少", success_rate=rates[r])
            elif not battle.participants[f"官{i}"].eliminated:
                bi.submit_action(battle, f"官{i}", "guan_hold")
            bi.submit_action(battle, f"黃{i}", "huang_hold")
        bi.resolve_round(battle, gamble, FixedRandom(0.999), now=1, tuning=BattleTuning())
        if battle.phase != "active":
            break
    assert battle.trend == 45
    assert bi.decide_outcome(battle, gamble).title == "兩軍膠著"


def test_a_strategist_gets_ten_more_points_on_a_gamble_and_the_line_says_so():
    gamble, battle = _gamblers(1, 1)
    battle.participants["官0"].role = "wis"
    bi.submit_action(battle, "官0", "guan_reckless", text="火燒糧草", success_rate=35)
    bi.submit_action(battle, "黃0", "huang_hold")
    msgs = bi.resolve_round(battle, gamble, FixedRandom(0.44), now=1, tuning=BattleTuning())  # 擲 44：35 不中、45 中
    assert "官0放手一搏：「火燒糧草」（評估成功率 35%，軍師 +10）" in msgs
    assert any(m.startswith("官0這一搏成功了") for m in msgs)


def test_an_adviser_loses_less_when_the_other_side_counters_their_move():
    t = BattleTuning()
    hit = {}
    for role in ("", "lore"):
        battle = _two_fighters(_gamble_three())
        battle.participants["甲"].role = role
        bi.submit_action(battle, "甲", "guan_strong")
        bi.submit_action(battle, "乙", "huang_hold")  # 固守剋強攻
        bi.resolve_round(battle, _gamble_three(), random.Random(0), now=1, tuning=t)
        hit[role] = battle.trend
    assert hit[""] < hit["lore"] <= 50  # 一樣吃虧，參謀吃得少


def test_a_stronger_gambler_pushes_further_when_the_gamble_lands():
    pushed = {}
    for power in (0, 160, 400):
        gamble, battle = _gamblers(1, 1)
        battle.participants["官0"].power = power
        bi.submit_action(battle, "官0", "guan_reckless", text="衝陣", success_rate=90)
        bi.submit_action(battle, "黃0", "huang_hold")
        bi.resolve_round(battle, gamble, FixedRandom(0.0), now=1, tuning=BattleTuning())
        pushed[power] = battle.trend - 40  # 黃巾固守推滿 −10（官軍唯一的人在賭）
    # 2 ＋ 10 × 0.06 ＝ 2.6：威力 0（實力 20）打五折 1、威力 160（實力 100）照算 3、練滿（實力 220，夾在兩倍）5
    assert pushed == {0: 1, 160: 3, 400: 5}


# ── 放手一搏的劇情與最有戲的一幕（試玩回饋 2026-10-08）─────────────────


def test_the_played_story_follows_the_dice_and_the_numbers_follow_the_story():
    for rate, roll, expected in (
        (1, 0.0, "官0扮成絕世美女，對面主將看呆了，陣腳大亂。（官軍的戰局推進 4，自己氣血 -15）"),  # (2＋99×0.06)×0.5
        (0, 0.999, "官0扮成絕世美女，化妝太差，敵軍作嘔把他轟了回來。（官軍的戰局倒退 1，自己氣血 -105）"),
    ):
        gamble, battle = _gamblers(1, 1)
        bi.submit_action(
            battle, "官0", "guan_reckless", text="扮成絕世美女色誘對面主將", success_rate=rate,
            stories=("官0扮成絕世美女，對面主將看呆了，陣腳大亂。", "官0扮成絕世美女，化妝太差，敵軍作嘔把他轟了回來。"),
        )
        bi.submit_action(battle, "黃0", "huang_hold")
        msgs = bi.resolve_round(battle, gamble, FixedRandom(roll), now=1, tuning=BattleTuning())
        assert expected in msgs
        assert not any("慘痛代價" in m for m in msgs)


def test_without_a_story_the_fixed_line_is_played():
    gamble, battle = _gamblers(1, 1)
    bi.submit_action(battle, "官0", "guan_reckless", text="衝陣", success_rate=0, stories=("", ""))
    bi.submit_action(battle, "黃0", "huang_hold")
    msgs = bi.resolve_round(battle, gamble, FixedRandom(0.999), now=1, tuning=BattleTuning())
    assert "官0這一搏失敗了，付出了慘痛代價：官軍的戰局倒退 1，自己氣血 -105。" in msgs


def test_a_story_is_cleaned_before_it_can_be_played():
    assert bi.clean_story("彩加试图色诱敌将，却被追杀十里", "彩加") == "彩加試圖色誘敵將，卻被追殺十里。"  # 轉繁體、補句號
    assert bi.clean_story("**被識破**，挨了一頓打。", "彩加") == "彩加被識破，挨了一頓打。"  # 去 markdown、補名號
    assert bi.clean_story("彩加帶著3萬分身殺過去。", "彩加") == ""  # 數字只能是引擎的
    assert bi.clean_story("彩加" + "很" * 70, "彩加") == ""  # 太長的整段不用
    assert bi.clean_story("", "彩加") == ""


def test_one_model_call_rates_the_gamble_and_writes_both_stories():
    from unittest import mock as _mock
    client = _mock.Mock()
    client.chat_structured.return_value = bi.SuccessRateJudgment(
        success_rate=3, win="彩加的影分身嚇退了敌军", lose="彩加结印结到手抽筋，被一箭射中屁股",
    )
    act = _gamble_three().acts[0]
    verdict = bi.assess_gamble(client, act, "官軍", "用上影分身之術十萬個分身", "彩加")
    assert verdict == (3, "彩加的影分身嚇退了敵軍。", "彩加結印結到手抽筋，被一箭射中屁股。")
    assert client.chat_structured.call_count == 1
    prompt = client.chat_structured.call_args.args[0][0]["content"]
    assert "不要寫任何數字" in prompt and "以「彩加」開頭" in prompt
    client.chat_structured.side_effect = RuntimeError("down")
    assert bi.assess_gamble(client, act, "官軍", "衝", "彩加") == (bi.DEFAULT_FREE_TEXT_SUCCESS_RATE, "", "")


def test_the_most_dramatic_gamble_is_a_long_shot_that_landed():
    def m(rate, won):
        return bi.GambleMoment(name="甲", faction="guan", text="x", rate=rate, won=won)

    assert bi.more_dramatic(m(5, True), m(0, False))  # 成了的勝過沒成的
    assert bi.more_dramatic(m(5, True), m(30, True))  # 同樣成了，越不可能越有戲
    assert bi.more_dramatic(m(0, False), m(40, False))  # 同樣沒成，越荒唐越有戲
    assert not bi.more_dramatic(m(5, True), m(5, True))  # 一樣有戲留先發生的
    gamble, battle = _gamblers(2, 1)
    bi.submit_action(battle, "官0", "guan_reckless", text="刺殺主將", success_rate=5, stories=("官0刺中了。", "官0撲空了。"))
    bi.submit_action(battle, "官1", "guan_reckless", text="可唔可以快少少", success_rate=0)
    bi.submit_action(battle, "黃0", "huang_hold")
    bi.resolve_round(battle, gamble, FixedRandom(0.04), now=1, tuning=BattleTuning())  # 擲 4：5% 中、0% 不中
    assert (battle.highlight.name, battle.highlight.won, battle.highlight.story) == ("官0", True, "官0刺中了。")
