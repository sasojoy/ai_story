import random
from unittest import mock

import pytest

from conftest import FixedRandom
from tianxia import battle_instance as bi
from tianxia.models import (
    BattleAct, BattleActionEffect, BattleDef, BattleFaction, BattleOption, BattleOutcome,
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
            ),
            BattleAct(
                id="a2", title="決戰", text="最終決戰。", goal="決出勝負",
                options=[
                    BattleOption(text="穩紮穩打", tag="safe"),
                    BattleOption(text="全力進攻", tag="aggressive"),
                ],
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


@pytest.fixture
def gamble_definition(definition) -> BattleDef:
    """跟 definition 同一個骨架，但 reckless 選項標成 free_text、並設定了
    free_text_gamble——給「放手一搏」賭局機制的測試用，不影響 definition 自己既有的
    那些測試（那些是純查表路徑，兩者分開測）。"""
    from tianxia.models import FreeTextGamble

    copy = definition.model_copy(deep=True)
    for act in copy.acts:
        for option in act.options:
            if option.tag == "reckless":
                option.free_text = True
    copy.free_text_gamble = FreeTextGamble(
        success_trend_base=5, success_trend_per_risk=0.3, success_neili_damage=10,
        failure_trend_per_risk=0.1, failure_neili_base=20, failure_neili_per_risk=3.0,
    )
    return copy


@pytest.fixture
def showdown() -> BattleDef:
    """照正式內容的黃巾決戰縮小的骨架：三幕、兩邊各有自己的穩守／猛攻、65／35 兩條門檻加一個無門檻的
    保底。每幕幾回合、多懸殊就提前收場都用預設值（3 回合一幕、偏離 40），整場 9 回合。"""
    options = [
        BattleOption(text="穩守陣線", tag="guan_safe", faction="guan"),
        BattleOption(text="率先衝鋒", tag="guan_aggressive", faction="guan"),
        BattleOption(text="死守營寨", tag="huang_safe", faction="huang"),
        BattleOption(text="捨命衝殺", tag="huang_aggressive", faction="huang"),
    ]
    return BattleDef(
        id="showdown",
        name="測試決戰",
        factions=[BattleFaction(id="guan", name="官軍"), BattleFaction(id="huang", name="黃巾")],
        trend_start=50,
        acts=[
            BattleAct(id="s1", title="兩軍對陣", text="兩軍列陣。", goal="推動戰局", options=list(options)),
            BattleAct(id="s2", title="鏖戰正酣", text="犬牙交錯。", goal="撐過消耗", options=list(options)),
            BattleAct(id="s3", title="決勝時刻", text="最後一擊。", goal="分出勝負", options=list(options)),
        ],
        action_tags={
            "guan_safe": BattleActionEffect(trend_delta=2, neili_damage=15),
            "guan_aggressive": BattleActionEffect(trend_delta=6, neili_damage=60),
            "huang_safe": BattleActionEffect(trend_delta=-2, neili_damage=15),
            "huang_aggressive": BattleActionEffect(trend_delta=-6, neili_damage=60),
        },
        outcomes=[
            BattleOutcome(faction="guan", trend_min=65, title="官軍大勝", text="官軍獲勝。"),
            BattleOutcome(faction="huang", trend_max=35, title="黃巾得勢", text="黃巾獲勝。"),
            BattleOutcome(faction="guan", title="兩軍膠著", text="不分勝負。"),
        ],
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
    bi.fill_timed_out_actions(instance, definition)
    assert instance.round.pending_actions == {"甲": "aggressive", "乙": "safe"}


def test_an_away_participant_drops_this_rounds_action_and_the_round_does_not_wait(definition):
    instance = _active_battle(definition)
    bi.submit_action(instance, "乙", "aggressive", text="衝", success_rate=40)
    bi.set_away(instance, "乙", True)
    assert instance.participants["乙"].away
    assert "乙" not in instance.round.pending_actions and "乙" not in instance.round.custom_texts
    assert "乙" not in instance.round.success_rates
    bi.submit_action(instance, "甲", "safe")
    assert bi.round_is_complete(instance)


def test_an_away_participant_cannot_submit_until_they_come_back(definition):
    instance = _active_battle(definition)
    bi.set_away(instance, "甲", True)
    bi.submit_action(instance, "甲", "safe")
    assert "甲" not in instance.round.pending_actions
    bi.set_away(instance, "甲", False)
    bi.submit_action(instance, "甲", "safe")
    assert instance.round.pending_actions["甲"] == "safe"


def test_timed_out_actions_skip_away_participants(definition):
    instance = _active_battle(definition)
    bi.set_away(instance, "乙", True)
    bi.fill_timed_out_actions(instance, definition)
    assert instance.round.pending_actions == {"甲": "safe"}


def test_timed_out_actions_pick_each_sides_own_safest_option(definition):
    """逾時代選只挑自己陣營能選的招：黃巾那邊不會被代選成官軍的穩守、替對面推戰局。"""
    definition.acts[0].options = [
        BattleOption(text="穩守陣線", tag="guan_safe", faction="guan"),
        BattleOption(text="死守營寨", tag="huang_safe", faction="huang"),
        BattleOption(text="全力進攻", tag="aggressive"),
    ]
    definition.action_tags["guan_safe"] = BattleActionEffect(trend_delta=2, neili_damage=15)
    definition.action_tags["huang_safe"] = BattleActionEffect(trend_delta=-2, neili_damage=15)
    instance = _active_battle(definition)
    bi.fill_timed_out_actions(instance, definition)
    assert instance.round.pending_actions == {"甲": "guan_safe", "乙": "huang_safe"}
    bi.resolve_round(instance, definition, random.Random(0))
    assert instance.trend == 50  # 兩邊各守各的，戰局不動


def test_timed_out_actions_fall_back_to_the_mildest_tag_when_no_fixed_option_is_offered(definition):
    definition.acts[0].options = [BattleOption(text="放手一搏", tag="aggressive", free_text=True)]
    instance = _active_battle(definition)
    bi.fill_timed_out_actions(instance, definition)
    assert instance.round.pending_actions == {"甲": "safe", "乙": "safe"}  # 不能讓回合永遠湊不齊


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
    bi.submit_action(instance, "甲", "safe")
    bi.submit_action(instance, "乙", "safe")
    bi.resolve_round(instance, definition, random.Random(0))
    assert instance.trend == 52  # 兩人各 +1
    assert instance.participants["甲"].neili == 95
    assert instance.participants["乙"].neili == 95


def test_submit_action_records_custom_text(definition):
    instance = _active_battle(definition)
    bi.submit_action(instance, "甲", "reckless", text="直取波才首級")
    assert instance.round.custom_texts["甲"] == "直取波才首級"
    assert instance.round.pending_actions["甲"] == "reckless"  # 機制效果還是走 tag 查表


def test_submit_action_without_text_leaves_custom_texts_untouched(definition):
    instance = _active_battle(definition)
    bi.submit_action(instance, "甲", "safe")
    assert "甲" not in instance.round.custom_texts


def test_resolve_round_surfaces_custom_text_in_the_messages(definition):
    """自訂文字不影響查表結果（威力/氣血照舊算），只會被包進訊息裡給 LLM 潤色用。"""
    instance = _active_battle(definition)
    bi.submit_action(instance, "甲", "aggressive", text="直取波才首級")
    bi.submit_action(instance, "乙", "safe")
    msgs = bi.resolve_round(instance, definition, random.Random(0))
    assert any("直取波才首級" in m for m in msgs)
    assert instance.participants["甲"].neili == 80  # 跟沒打字的 aggressive 扣血量一樣（100-20）


# ── 放手一搏：LLM 評成功率、系統擲骰、公式換算（設計討論：「我就是希望看到玩家的
# 奇葩操作對戰局產生影響」）─────────────────────────────────────


def test_resolve_round_gamble_success_pushes_trend_toward_the_actors_faction(gamble_definition):
    instance = _active_battle(gamble_definition)
    bi.submit_action(instance, "甲", "reckless", success_rate=50)  # 甲在 guan（factions[0]，正向）
    bi.submit_action(instance, "乙", "safe")
    msgs = bi.resolve_round(instance, gamble_definition, FixedRandom(0.0))  # random()=0.0，永遠擲骰成功
    assert instance.trend > 50 + 1  # guan_safe 的 乙 本來就會 +1，另外甲賭贏了應該推得更高
    assert any("這一搏成功了" in m for m in msgs)
    assert instance.participants["甲"].neili == 90  # 100 - success_neili_damage(10)


def test_resolve_round_gamble_failure_pushes_trend_away_from_the_actors_faction(gamble_definition):
    instance = _active_battle(gamble_definition)
    bi.submit_action(instance, "甲", "reckless", success_rate=80)  # risk=20，刻意選小一點避免傷害超過上限被夾到 0 看不出公式
    bi.submit_action(instance, "乙", "safe")
    msgs = bi.resolve_round(instance, gamble_definition, FixedRandom(0.999))  # 永遠擲骰失敗
    assert any("這一搏失敗了" in m for m in msgs)
    # risk=20：failure_neili = 20 + 20*3.0 = 80
    assert instance.participants["甲"].neili == 100 - 80


def test_resolve_round_gamble_direction_flips_for_the_second_faction(gamble_definition):
    """乙在 huang（factions[1]，負向）：賭贏了戰局應該往 huang 那邊推（trend 下降）。"""
    instance = _active_battle(gamble_definition)
    bi.submit_action(instance, "甲", "safe")
    bi.submit_action(instance, "乙", "reckless", success_rate=50)
    bi.resolve_round(instance, gamble_definition, FixedRandom(0.0))
    # guan_safe 的甲 +1，huang 賭贏再往下推，trend 應該落在 51 以下
    assert instance.trend < 51


def test_resolve_round_gamble_higher_risk_means_bigger_reward_and_bigger_cost(gamble_definition):
    low_risk = _active_battle(gamble_definition)
    bi.submit_action(low_risk, "甲", "reckless", success_rate=90)  # risk=10
    bi.submit_action(low_risk, "乙", "safe")
    bi.resolve_round(low_risk, gamble_definition, FixedRandom(0.999))  # 失敗
    low_risk_damage = 100 - low_risk.participants["甲"].neili

    high_risk = _active_battle(gamble_definition)
    bi.submit_action(high_risk, "甲", "reckless", success_rate=10)  # risk=90
    bi.submit_action(high_risk, "乙", "safe")
    bi.resolve_round(high_risk, gamble_definition, FixedRandom(0.999))  # 失敗
    high_risk_damage = 100 - high_risk.participants["甲"].neili

    assert high_risk_damage > low_risk_damage  # 風險愈高，失敗代價愈重


def test_resolve_round_gamble_can_eliminate_on_a_bad_roll(gamble_definition):
    """極端的奇葩操作（成功率評很低）賭輸了，傷害可以直接打到出局——跟固定選項的
    reckless 一樣，是數字夠狠，不是程式特判。"""
    instance = _active_battle(gamble_definition)
    bi.submit_action(instance, "甲", "reckless", success_rate=1)  # risk=99
    bi.submit_action(instance, "乙", "safe")
    bi.resolve_round(instance, gamble_definition, FixedRandom(0.999))  # 失敗
    assert instance.participants["甲"].eliminated


def test_resolve_round_gamble_message_includes_the_assessed_success_rate(gamble_definition):
    instance = _active_battle(gamble_definition)
    bi.submit_action(instance, "甲", "reckless", text="直取波才首級", success_rate=25)
    bi.submit_action(instance, "乙", "safe")
    msgs = bi.resolve_round(instance, gamble_definition, FixedRandom(0.0))
    assert any("直取波才首級" in m and "25%" in m for m in msgs)


def test_resolve_round_without_a_gamble_config_falls_back_to_the_tag_lookup(definition):
    """definition（沒設定 free_text_gamble）就算送出了 success_rate，也不會走賭局路徑，
    因為場上根本沒有這套機制可以依循——退回原本 action_tags 查表那條路。用 trend 而不是
    neili 驗證：reckless 固定 neili_damage=200 兩條路徑都會把 100 點氣血打到夾在 0（看
    不出差異），但 trend_delta 是固定的 10，賭局公式算出來的值幾乎不可能剛好湊成同一個數，
    足以分辨走的是哪一條路。"""
    instance = _active_battle(definition)
    bi.submit_action(instance, "甲", "reckless", success_rate=50)
    bi.submit_action(instance, "乙", "safe")
    bi.resolve_round(instance, definition, FixedRandom(0.0))
    assert instance.trend == 50 + 10 + 1  # reckless 固定 trend_delta=10，加上 乙 safe 的 +1
    assert instance.participants["甲"].eliminated  # neili_damage=200 遠超過上限，夾到 0 出局


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
        assert tag != "reckless"  # 這個 definition 裡 reckless 是 free_text


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


# FB-027：參戰者自己的戰報要寫出手幾回合、第幾回合倒下；逾時被系統代選的回合不算自己出手。


def test_each_resolved_round_a_fighter_chose_for_themselves_counts_as_acting(definition):
    instance = _active_battle(definition)
    for _ in range(2):
        bi.submit_action(instance, "甲", "safe")
        bi.submit_action(instance, "乙", "safe")
        bi.resolve_round(instance, definition, random.Random(0))
    assert instance.participants["甲"].acted_rounds == 2 and instance.participants["乙"].acted_rounds == 2


def test_a_timed_out_round_picked_by_the_system_does_not_count_as_acting(definition):
    instance = _active_battle(definition)
    bi.submit_action(instance, "甲", "safe")
    bi.fill_timed_out_actions(instance, definition)  # 乙沒選，系統代選
    bi.resolve_round(instance, definition, random.Random(0))
    assert instance.participants["甲"].acted_rounds == 1
    assert instance.participants["乙"].acted_rounds == 0
    bi.submit_action(instance, "乙", "safe")  # 下一回合乙自己選了：照算
    bi.submit_action(instance, "甲", "safe")
    bi.resolve_round(instance, definition, random.Random(0))
    assert instance.participants["乙"].acted_rounds == 1


def test_a_fighter_who_falls_remembers_the_round(definition):
    instance = _active_battle(definition)
    bi.submit_action(instance, "甲", "safe")
    bi.submit_action(instance, "乙", "safe")
    bi.resolve_round(instance, definition, random.Random(0))
    bi.submit_action(instance, "甲", "reckless")  # 氣血 95，扣 200：第 2 回合倒下
    bi.submit_action(instance, "乙", "safe")
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


def test_mitigated_by_power_reduces_damage_for_a_powerful_participant(definition):
    instance = _active_battle(definition)
    instance.participants["甲"].power = 100
    bi.submit_action(instance, "甲", "aggressive")
    bi.submit_action(instance, "乙", "aggressive")
    bi.resolve_round(instance, definition, random.Random(0))
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


# ── 進幕與終局判定（戰鬥系統設計 3.2：換幕照回合數走，壓倒性才提前收場）──────────


def _to_the_last_round(instance: bi.BattleInstance, definition: BattleDef) -> None:
    """直接跳到最後一幕的最後一回合（結算完就看戰局定結果）。"""
    instance.act_index = len(definition.acts) - 1
    instance.round_number = bi.total_rounds(definition) - 1


def test_advancing_to_the_next_act_after_its_rounds_are_played(definition):
    instance = _active_battle(definition)
    for _ in range(definition.rounds_per_act):  # 每幕 3 回合（預設）
        assert instance.act_index == 0
        bi.submit_action(instance, "甲", "safe")
        bi.submit_action(instance, "乙", "safe")
        msgs = bi.resolve_round(instance, definition, random.Random(0))
    assert instance.act_index == 1
    assert any("決戰" in m for m in msgs)


def test_a_gauge_past_an_outcome_line_but_short_of_decisive_does_not_end_early(definition):
    instance = _active_battle(definition)
    instance.trend = 75  # 已經過了「官軍大勝」的 70，但離 90 還遠：第一回合不判結果
    bi.submit_action(instance, "甲", "safe")
    bi.submit_action(instance, "乙", "safe")
    bi.resolve_round(instance, definition, random.Random(0))
    assert instance.phase == "active" and instance.act_index == 0


def test_outcome_ends_the_battle_once_on_the_final_round(definition):
    instance = _active_battle(definition)
    _to_the_last_round(instance, definition)
    instance.trend = 75
    bi.submit_action(instance, "甲", "safe")
    bi.submit_action(instance, "乙", "safe")
    bi.resolve_round(instance, definition, random.Random(0))
    assert instance.phase == "ended"
    assert instance.outcome_title == "官軍大勝"


def test_outcome_copies_the_season_level_consequences_onto_the_instance(definition):
    definition.outcomes[0].world_flags_add = ["huangjin_decisive_win"]
    definition.outcomes[0].trend_delta = {"huangjin": -35}
    instance = _active_battle(definition)
    _to_the_last_round(instance, definition)
    instance.trend = 75
    bi.submit_action(instance, "甲", "safe")
    bi.submit_action(instance, "乙", "safe")
    bi.resolve_round(instance, definition, random.Random(0))
    assert instance.outcome_world_flags == ["huangjin_decisive_win"]
    assert instance.outcome_trend_delta == {"huangjin": -35}


def test_a_decisive_gauge_ends_the_battle_in_either_direction(definition):
    """壓倒性是雙向的：不管戰局往哪一方傾斜，偏離中線 50 達 decisive_margin（預設 40）就當回合收場，
    不是只有某一方拉開差距才算。"""
    low = _active_battle(definition)
    low.trend = 8  # 8 + 1 + 1 = 10：|10-50| = 40
    bi.submit_action(low, "甲", "safe")
    bi.submit_action(low, "乙", "safe")
    bi.resolve_round(low, definition, random.Random(0))
    assert low.phase == "ended" and low.outcome_title == "黃巾得勝"

    high = _active_battle(definition)
    high.trend = 88  # 88 + 1 + 1 = 90
    bi.submit_action(high, "甲", "safe")
    bi.submit_action(high, "乙", "safe")
    bi.resolve_round(high, definition, random.Random(0))
    assert high.phase == "ended" and high.outcome_title == "官軍大勝"


def test_a_gauge_short_of_the_decisive_margin_neither_ends_nor_changes_act(definition):
    for start in (87, 11):  # 87 + 2 = 89、11 + 2 = 13：都還差一點
        instance = _active_battle(definition)
        instance.trend = start
        bi.submit_action(instance, "甲", "safe")
        bi.submit_action(instance, "乙", "safe")
        bi.resolve_round(instance, definition, random.Random(0))
        assert instance.phase == "active" and instance.act_index == 0, start


def test_the_fallback_outcome_with_no_bounds_catches_a_stalemate(definition):
    instance = _active_battle(definition)
    _to_the_last_round(instance, definition)
    instance.trend = 50  # 不滿足前兩個 outcome 的範圍，落到保底的「僵持」
    bi.submit_action(instance, "甲", "safe")
    bi.submit_action(instance, "乙", "safe")
    bi.resolve_round(instance, definition, random.Random(0))
    assert instance.outcome_title == "僵持"


def _showdown_battle(definition: BattleDef) -> bi.BattleInstance:
    """甲站官軍、乙站黃巾；氣血給足，打滿九回合也不會有人倒下。"""
    instance = bi.start_muster(definition, now=0.0)
    bi.join_faction(instance, "甲", "guan", neili_cap=10_000.0)
    bi.join_faction(instance, "乙", "huang", neili_cap=10_000.0)
    bi.close_muster(instance, definition, random.Random(0))
    return instance


def _play(instance: bi.BattleInstance, definition: BattleDef, guan="guan_safe", huang="huang_safe") -> list[str]:
    """甲、乙各出一招並結算這一回合；預設兩邊都穩守，推力互相抵銷。"""
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
    (86, "guan_aggressive", "huang_safe", "官軍大勝"),  # 86 + 6 - 2 = 90
    (14, "guan_safe", "huang_aggressive", "黃巾得勢"),  # 14 + 2 - 6 = 10
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
    msgs = _play(instance, showdown, "guan_aggressive", "huang_safe")  # 第 3 回合：88 + 4 = 92
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
    _play(lopsided, showdown, "guan_aggressive", "huang_safe")  # 66 + 4 = 70：偏離 20 就收場
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
    assert tag in {"safe", "aggressive", "reckless"}


def test_bot_choose_action_returns_none_for_a_non_participant(definition):
    instance = _active_battle(definition)
    assert bi.bot_choose_action(instance, definition, "幽靈", random.Random(0)) is None


def test_bot_choose_action_prefers_lower_risk_options_on_average(definition):
    instance = _active_battle(definition)
    picks = [bi.bot_choose_action(instance, definition, "甲", random.Random(i)) for i in range(200)]
    counts = {tag: picks.count(tag) for tag in ("safe", "aggressive", "reckless")}
    assert counts["safe"] > counts["reckless"]  # safe 的氣血損耗最低，應該被選到最多次


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
    bi.submit_action(instance, "甲", "safe")
    bi.submit_action(instance, "乙", "aggressive", text="直取波才首級")
    msgs = bi.resolve_round(instance, definition, random.Random(0), now=700.0)
    [record] = instance.rounds
    assert (record.act_index, record.resolved_real, record.trend_after) == (0, 700.0, instance.trend)
    assert record.actions == {"甲": "safe", "乙": "aggressive"}
    assert record.custom_texts == {"乙": "直取波才首級"}
    assert record.messages == msgs and record.id is None


def test_ending_without_fighters_records_the_closing_round(definition):
    instance = _empty_active_battle(definition, now=600.0)
    msgs = bi.end_without_fighters(instance, definition, now=600.0 + definition.round_seconds)
    [record] = instance.rounds
    assert record.actions == {} and record.messages == msgs


def test_ending_without_fighters_counts_the_timed_out_round(definition):
    instance = _active_battle(definition)
    bi.submit_action(instance, "甲", "safe")
    bi.submit_action(instance, "乙", "safe")
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
    """提前收場看 50（戰鬥系統 5.3）：起點 58 的一場，到 90 就收（舊規則偏離起點 40 要到 98），到 18 不收（舊規則會收），
    到 10 才收；起點 50 的 beta 那場收場時機跟以前一樣。"""
    def played(start: int, trend: int, guan="guan_safe", huang="huang_safe") -> bi.BattleInstance:
        instance = bi.start_muster(showdown, now=0.0, trend_start=start)
        bi.join_faction(instance, "甲", "guan", neili_cap=10_000.0)
        bi.join_faction(instance, "乙", "huang", neili_cap=10_000.0)
        bi.close_muster(instance, showdown, random.Random(0))
        instance.trend = trend
        _play(instance, showdown, guan, huang)
        return instance

    assert played(58, 86, "guan_aggressive").phase == "ended"  # 86 + 6 − 2 = 90
    assert played(58, 85, "guan_aggressive").phase == "active"  # 89
    assert played(58, 22, "guan_safe", "huang_aggressive").phase == "active"  # 22 + 2 − 6 = 18：舊規則會收
    assert played(58, 14, "guan_safe", "huang_aggressive").phase == "ended"  # 10
    for trend, phase in ((86, "ended"), (85, "active"), (14, "ended"), (15, "active")):  # beta 那場：起點 50
        guan, huang = ("guan_aggressive", "huang_safe") if trend > 50 else ("guan_safe", "huang_aggressive")
        assert played(50, trend, guan, huang).phase == phase, trend
