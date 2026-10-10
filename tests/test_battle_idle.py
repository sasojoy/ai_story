"""決戰的掛機懲罰（Joy 2026-10-10：「掛機的人很影響節奏，是不是有掛機懲罰，下一回合預設也固守之類」）：
回合逾時被代選就是掛機，下一回合起不等他（其他人送齊就結算，他照舊被代選固守、份量打折）、戰功沒有；
連續 idle_leave 回合撤下陣；自己按任何行動就解除。畫面的「已送出／在場」不算掛機的人，另寫「掛機 N 人不等」。"""
import random

from test_battle_gauge import showdown  # noqa: F401（fixture）
from test_battle_targeting import CODES, _battle, gamble  # noqa: F401（fixture）

from tianxia import battle_instance as bi
from tianxia.models import BattleTuning


def _submit(battle, name, move):
    bi.submit_action(battle, name, f"{battle.participants[name].faction}_{CODES[move]}")


def _timeout_round(battle, definition, moves, tuning=None):
    """moves 裡的人自己出手，其餘照逾時代選，結算一回合。"""
    for name, move in moves.items():
        _submit(battle, name, move)
    bi.fill_timed_out_actions(battle, definition, tuning)
    return bi.resolve_round(battle, definition, random.Random(0), now=1, tuning=tuning or BattleTuning())


def test_a_timed_out_fighter_is_idle_and_the_next_round_does_not_wait(gamble):
    battle = _battle(gamble, [("甲", "guan"), ("乙", "huang")])
    _timeout_round(battle, gamble, {"甲": "奇襲"})
    b = battle.participants["乙"]
    assert b.idle_streak == 1 and bi.idle(b) and b.acted_rounds == 0
    assert bi.round_progress(battle, gamble) == (0, 1) and bi.idle_count(battle, gamble) == 1
    _submit(battle, "甲", "強攻")
    assert bi.round_is_complete(battle)  # 不等乙
    bi.fill_idle_actions(battle, gamble)
    assert battle.round.pending_actions["乙"] == "huang_hold" and "乙" in battle.round.auto_picked
    bi.resolve_round(battle, gamble, random.Random(0), now=2, tuning=BattleTuning())
    assert b.idle_streak == 2


def test_everyone_idle_still_waits_for_the_timeout(gamble):
    battle = _battle(gamble, [("甲", "guan"), ("乙", "huang")])
    _timeout_round(battle, gamble, {})
    assert not bi.round_is_complete(battle)


def test_an_idle_hold_pushes_at_half_weight(gamble):
    def push(auto):
        battle = _battle(gamble, [("甲", "guan"), ("乙", "huang"), ("丙", "huang")])
        battle.participants["甲"].scores = {m: 10.0 for m in CODES}  # 官軍弱：看得出黃巾推了多少
        _submit(battle, "甲", "固守")
        _submit(battle, "乙", "固守")
        if auto:
            bi.fill_timed_out_actions(battle, gamble)
        else:
            _submit(battle, "丙", "固守")
        bi.resolve_round(battle, gamble, random.Random(0), now=1, tuning=BattleTuning())
        return 50 - battle.trend  # 黃巾那邊推了多少

    assert 0 < push(auto=True) < push(auto=False)


def test_three_idle_rounds_take_you_off_the_field_until_you_act(gamble):
    gamble.rounds_per_act = 5  # 打得夠久
    battle = _battle(gamble, [("甲", "guan"), ("乙", "huang")])
    msgs = []
    for _ in range(BattleTuning().idle_leave):
        msgs = _timeout_round(battle, gamble, {"甲": "固守"})
    b = battle.participants["乙"]
    assert b.left_field and "乙在陣上發呆太久，被撤了下去。" in msgs
    assert b not in bi._active_participants(battle) and bi.idle_count(battle, gamble) == 0
    neili = b.neili
    _timeout_round(battle, gamble, {"甲": "強攻"})  # 撤下陣的人不出手、不挨打、不代選
    assert b.neili == neili and "乙" not in battle.round.pending_actions
    _submit(battle, "乙", "奇襲")  # 自己按了：回到陣上、不算掛機
    assert not b.left_field and b.idle_streak == 0 and b in bi._active_participants(battle)


def test_acting_clears_the_idle_mark_at_once(gamble):
    battle = _battle(gamble, [("甲", "guan"), ("乙", "huang")])
    _timeout_round(battle, gamble, {"甲": "固守"})
    _submit(battle, "乙", "固守")
    assert not bi.idle(battle.participants["乙"]) and bi.round_progress(battle, gamble) == (1, 2)


def test_idle_rounds_earn_no_merit(gamble):
    battle = _battle(gamble, [("甲", "guan"), ("乙", "huang")])
    _timeout_round(battle, gamble, {"甲": "固守"})
    assert bi.merit(BattleTuning(), battle.participants["乙"]) == 0


def test_old_participants_read_as_not_idle():
    p = bi.BattleParticipant.model_validate({"name": "甲", "faction": "guan", "neili": 1, "neili_cap": 1})
    assert (p.idle_streak, p.left_field) == (0, False)


# ── 引擎：不等掛機的人、場景寫出來 ─────────────────────────────


def test_the_round_settles_without_the_idler_and_the_scene_says_so(showdown):
    on, a, b = showdown
    a.world.mutate_battle(lambda x: setattr(x, "muster_deadline_real", -1.0))
    a.options()
    a.choose("battle:act:guan_raid")  # 乙不出手：等到逾時
    definition = on.battles["wancheng_jia"]
    a.now += definition.round_seconds + 1
    a.options()
    battle = a.world.get_battle()
    assert battle.round_number == 1 and battle.participants["乙"].idle_streak == 1
    b.now = a.now
    assert "你上一回合沒出手" in b.scene_text()
    assert "（掛機 1 人不等）" in a.scene_text()
    a.choose("battle:act:guan_raid")  # 甲一出手就結算，不必再等逾時
    assert a.world.get_battle().round_number == 2
