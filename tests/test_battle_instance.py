import random
from math import isclose
from unittest import mock

import pytest

from conftest import FixedRandom
from tianxia import battle_instance as bi
from tianxia.models import (
    MOVES, BattleAct, BattleDef, BattleFaction, BattleOption, BattleOutcome, BattleTuning,
    FreeTextGamble,
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
    copy.free_text_gamble = FreeTextGamble(
        success_trend_base=5, success_trend_per_risk=0.3, success_neili_damage=10,
        failure_trend_per_risk=0.1, failure_neili_base=20, failure_neili_per_risk=3.0,
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
    """戰鬥系統 3.4：剛招式＋剛內功 → 強攻 100、固守 75、奇襲 50；剛＋柔 → 80／85／60（實力 100 時）。"""
    t = BattleTuning()
    assert bi.move_scores(t, 150, "剛", "剛") == {"強攻": 100, "固守": 75, "奇襲": 50}
    assert bi.move_scores(t, 150, "剛", "柔") == {"強攻": 80, "固守": 85, "奇襲": 60}


def test_strength_runs_from_forty_to_a_hundred():
    t = BattleTuning()
    assert bi.move_scores(t, 0, None, None) == {"強攻": 30, "固守": 30, "奇襲": 30}  # 實力 40 × 適性 75%
    assert bi.move_scores(t, 400, None, None)["強攻"] == 75  # 威力封頂 150 → 實力 100
    assert bi.move_scores(t, -20, None, None) == bi.move_scores(t, 0, None, None)  # 負的威力不會把實力壓到 40 以下


def test_strength_never_passes_a_hundred_even_with_a_generous_tuning():
    """實力封頂 100：把基準調到 80，威力 150 本來是 80 ＋ 60 ＝ 140，仍然算 100（強攻 75 ＝ 100 × 適性 75%）。"""
    t = BattleTuning(power_base=80)
    assert bi.move_scores(t, 150, None, None) == {"強攻": 75, "固守": 75, "奇襲": 75}
    assert bi.move_scores(t, 0, None, None) == {"強攻": 60, "固守": 60, "奇襲": 60}  # 80 × 75%：沒封頂的地方照算


@pytest.mark.parametrize("attribute, good, bad", [
    ("剛", "強攻", "奇襲"), ("實", "強攻", "奇襲"), ("陽", "強攻", "固守"), ("柔", "固守", "強攻"),
    ("陰", "固守", "強攻"), ("慢", "固守", "奇襲"), ("快", "奇襲", "固守"), ("虛", "奇襲", "強攻"),
])
def test_each_attribute_favours_one_move_and_hurts_another(attribute, good, bad):
    """設計 3.4 的表：武學屬性 ±15、內功屬性 ±10，另一招不動（威力 150 → 實力 100，適性就是份量）。"""
    third = next(m for m in MOVES if m not in (good, bad))
    outer = bi.move_scores(BattleTuning(), 150, attribute, None)
    assert (outer[good], outer[third], outer[bad]) == (90, 75, 60)
    inner = bi.move_scores(BattleTuning(), 150, None, attribute)
    assert (inner[good], inner[third], inner[bad]) == (85, 75, 65)


def test_affinity_is_clamped_between_fifty_and_a_hundred():
    """適性夾在 50～100：擅長加到頂不會超過 100，兩邊都不擅長也不會低於 50。"""
    t = BattleTuning(affinity_base=95.0, affinity_outer=30.0, affinity_inner=30.0)
    scores = bi.move_scores(t, 150, "剛", "剛")  # 強攻 95+60 → 夾到 100；奇襲 95−60 → 夾到 50
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
    # 三招：官軍沒人出固定招（甲在賭）、黃巾有乙 → 推 −10；賭贏 5 + 50 × 0.3 ＝ +20 加在三招合成之後
    assert instance.trend == 50 - 10 + 20
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
    # 三招：只有甲出固定招 → +10；乙賭贏往 huang 那邊再推 −20，合起來落在 40
    assert instance.trend == 50 + 10 - 20


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


def test_a_side_that_is_all_down_gets_pushed_ten(three):
    battle = _two_fighters(three)
    battle.participants["乙"].eliminated = True
    bi.submit_action(battle, "甲", "guan_hold")
    bi.resolve_round(battle, three, random.Random(0), now=1, tuning=BattleTuning())
    assert battle.trend == 60


def test_a_side_that_is_all_out_of_the_region_gets_pushed_ten(three):
    battle = _two_fighters(three)
    bi.set_away(battle, "乙", True)
    bi.submit_action(battle, "甲", "guan_hold")
    bi.resolve_round(battle, three, random.Random(0), now=1, tuning=BattleTuning())
    assert battle.trend == 60


def test_a_side_that_is_all_gambling_gets_pushed_ten_and_the_gamble_still_counts(three):
    """放手一搏的人不算進三招的比例、也不算進人數：黃巾只有一個人而且在賭，官軍推滿 10；賭輸再加 10（舊的賭局公式照舊）。"""
    gamble = three.model_copy(deep=True)
    gamble.acts[0].options.append(BattleOption(text="放手一搏", tag="huang_reckless", faction="huang", free_text=True))
    gamble.free_text_gamble = FreeTextGamble()
    battle = _two_fighters(gamble)
    bi.submit_action(battle, "甲", "guan_hold")
    bi.submit_action(battle, "乙", "huang_reckless", text="夜襲", success_rate=0)  # 一定失敗
    msgs = bi.resolve_round(battle, gamble, random.Random(0), now=1, tuning=BattleTuning())
    assert battle.trend == 70  # 三招推 +10，黃巾賭輸 −(−10)＝ +10，合起來再夾 0～100
    assert battle.last_mix["huang"] == {} and "乙這一搏失敗了，付出了慘痛代價。" in msgs


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


def test_narrate_round_writes_a_late_han_battle_in_traditional_characters(definition):
    """戰況潤色是漢末兩軍對陣，不是武俠單挑；輸出轉成繁體（試玩時出現「劍尖相碰」這種武俠寫法）。"""
    instance = _active_battle(definition)
    client = mock.Mock()
    client.chat_text.return_value = "战场上烟尘四起。"
    text = bi.narrate_round(client, definition, instance, ["甲選了穩紮穩打。"])
    system = client.chat_text.call_args.args[0][0]["content"]
    assert "漢末" in system and "兩軍對陣" in system and "單打獨鬥" in system
    assert "武俠遊戲" not in system
    assert text == "戰場上煙塵四起。"


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


def test_narrate_round_decodes_byte_tokens_the_model_left_in(definition):
    """FB-075：長社火攻第一回合出現「旌旗仍<0xE5><0xB7><0x93>然屹立」，決戰場景列最近五段、玩家看得到。"""
    instance = _active_battle(definition)
    client = mock.Mock()
    client.chat_text.return_value = "火光中，旌旗仍<0xE5><0xB7><0x8D>然屹立。"
    assert bi.narrate_round(client, definition, instance, ["甲選了穩紮穩打。"]) == "火光中，旌旗仍巍然屹立。"
