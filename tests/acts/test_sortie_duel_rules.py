"""減法季批 3b-1：出陣約戰的純規則（tianxia/sortie_duel.py；整合設計 4.3，計畫第四節 Task 3b-1、4.0 之二）與 conquest.pull。

約戰的狀態機（貼、應戰、同去、到時、假人補位、守軍迎戰、作廢、結算、清掉）與三回合結算都是純函式：不 import engine、不讀電腦時鐘
（時刻一律是傳進來的現實秒）、亂數用每一場自己的 random.Random(f"約戰|{id}|{opened_at}")。資料存在 SharedWorldState.sorties，
空的時候 world 那一列的 JSON 不多這個鍵。接線（引擎、伺服器、假人）是 3b-2～3b-4 的事，這裡不碰。"""
from __future__ import annotations

import json
import random

import pytest
from pydantic import ValidationError

from tianxia import conquest, sortie, sortie_duel
from tianxia.models import MOVES, SortieRules
from tianxia.sqlite_world import open_world
from tianxia.world_state import SharedWorldState, SortieDuel, SortieResult, SortieSide

T0 = 1_000_000.0
CFG = SortieRules()
WINDOW = CFG.window_minutes * 60


def _side(name, side="guan", power=100.0, moves=("強攻", "固守", "奇襲"), region="yingchuan", **kw) -> SortieSide:
    return SortieSide(name=name, side=side, power=power, moves=list(moves), region=region, **kw)


def _open(shared=None, *, attacker=None, now=T0, garrison=None, id="d1", region="yingchuan"):
    shared = shared if shared is not None else SharedWorldState()
    duel = sortie_duel.open(
        shared, id=id, block="changshe", region=region, place="長社", region_name="潁川汝南",
        attacker=attacker or _side("關羽"), now=now, cfg=CFG, garrison=garrison,
    )
    return shared, duel


def _answer_kw(**over):
    kw = dict(name="張角", side="huang", region="yingchuan", answers_left=3, stamina=50.0)
    kw.update(over)
    return kw


def _settle(duel, defender=None):
    """直接結算這一場（不經 advance）：守方沒給就照現有的。"""
    if defender is not None:
        sortie_duel.answer(duel, defender, duel.opened_at + 60)
    duel.result = sortie_duel.resolve(duel, CFG, sortie_duel.rng_for(duel))
    duel.status, duel.settled_at = "settled", duel.expires_at
    return duel.result


# ── 設定 ──


def test_the_numbers_live_in_config_sortie_and_the_old_per_day_stays():
    cfg = SortieRules()
    assert cfg.per_day == 5  # 舊季照讀
    assert (cfg.jianfa_per_day, cfg.jianfa_stamina, cfg.cooldown_minutes, cfg.window_minutes) == (2, 12, 60, 10)
    assert (cfg.answer_per_day, cfg.answer_stamina, cfg.lose_injury, cfg.lose_cooldown_minutes) == (3, 12, 10, 30)
    assert cfg.result_scale == {"big": 1.5, "win": 1.0, "draw": 0.4, "lose": 0.0}
    assert cfg.moves == ["強攻", "固守", "奇襲", "撤退"]
    assert (cfg.retreat_toll, cfg.counter_swing) == (0.3, 0.3)
    assert set(cfg.round_toll) == {"win", "draw", "lose"}
    assert (cfg.duty_contribution, cfg.duty_per_day) == (1, 1)
    with pytest.raises(ValidationError):
        SortieRules(result_scale={"big": 1.5})
    with pytest.raises(ValidationError):
        SortieRules(moves=["強攻", "放手一搏"])  # 放手一搏不放進約戰（企劃者 2026-10-24）
    with pytest.raises(ValidationError):
        SortieRules(round_toll={"win": 0.1})


def test_moves_problem_wants_three_known_moves():
    assert sortie_duel.moves_problem(CFG, ["強攻", "固守", "奇襲"]) is None
    assert sortie_duel.moves_problem(CFG, ["撤退"] * 3) is None
    assert sortie_duel.moves_problem(CFG, ["強攻", "固守"]) is not None
    assert sortie_duel.moves_problem(CFG, ["強攻", "固守", "放手一搏"]) is not None


# ── 貼約戰 ──


def test_open_posts_a_card_for_the_window():
    shared, duel = _open()
    assert shared.sorties["d1"] is duel
    assert duel.status == "open" and duel.defender is None
    assert duel.opened_at == T0 and duel.expires_at == T0 + WINDOW
    assert duel.attacker.sealed_at == T0
    with pytest.raises(ValueError):
        _open(shared)  # 同一個 id 不能貼兩次


def test_open_problem_reasons():
    ok = dict(side="guan", left=2, cooldown_until=None, block_why=None, stamina=50.0)
    assert sortie_duel.open_problem(CFG, T0, **ok) is None
    assert sortie_duel.open_problem(CFG, T0, **{**ok, "side": None}) == sortie.RANGER_NOTE
    assert sortie_duel.open_problem(CFG, T0, **ok, traveling=True) == sortie_duel.WHY_ROAD
    assert sortie_duel.open_problem(CFG, T0, **{**ok, "left": 0}) == sortie.USED_UP.format(n=2)
    assert sortie_duel.open_problem(CFG, T0, **{**ok, "cooldown_until": T0 + 61}) == sortie_duel.WHY_COOL.format(n=2)
    assert sortie_duel.open_problem(CFG, T0, **{**ok, "cooldown_until": T0}) is None  # 時間到了就好
    # 自家的塊沒人約戰時：「等對面來約」（設計 4.3）；其餘推不動的原因照 conquest 寫
    assert sortie_duel.open_problem(CFG, T0, **{**ok, "block_why": conquest.WHY_OWN}) == sortie_duel.WHY_WAIT
    assert sortie_duel.open_problem(CFG, T0, **{**ok, "block_why": conquest.WHY_CUT}) == conquest.WHY_CUT
    tired = sortie_duel.open_problem(CFG, T0, **{**ok, "stamina": 11.0})
    assert tired == sortie_duel.WHY_TIRED.format(n=12)


# ── 應戰與同去 ──


def test_the_other_side_in_the_same_region_can_answer_and_others_get_a_reason():
    _, duel = _open()
    now = T0 + 60
    assert sortie_duel.answer_problem(CFG, duel, now, **_answer_kw()) is None
    # 不同區：看得到卡、鈕灰著寫在哪一區才應得了戰
    assert sortie_duel.answer_problem(CFG, duel, now, **_answer_kw(region="jizhou")) == "在潁川汝南才應得了戰"
    # 同陣營只能同去；自己約的不能應；散人不能應
    assert sortie_duel.answer_problem(CFG, duel, now, **_answer_kw(name="劉備", side="guan")) == sortie_duel.WHY_ALLY
    assert sortie_duel.answer_problem(CFG, duel, now, **_answer_kw(name="關羽", side="guan")) == sortie_duel.WHY_MINE
    assert sortie_duel.answer_problem(CFG, duel, now, **_answer_kw(side=None)) == sortie_duel.WHY_RANGER
    # 次數、體力、輸了的冷卻、在路上、窗過了
    assert sortie_duel.answer_problem(CFG, duel, now, **_answer_kw(answers_left=0)) == sortie_duel.WHY_ANSWERS.format(n=3)
    assert sortie_duel.answer_problem(CFG, duel, now, **_answer_kw(stamina=11.0)) == sortie_duel.WHY_TIRED.format(n=12)
    assert sortie_duel.answer_problem(CFG, duel, now, **_answer_kw(cooldown_until=now + 540)) == sortie_duel.WHY_COOL.format(n=9)
    assert sortie_duel.answer_problem(CFG, duel, now, **_answer_kw(traveling=True)) == sortie_duel.WHY_ROAD
    assert sortie_duel.answer_problem(CFG, duel, T0 + WINDOW, **_answer_kw()) == sortie_duel.WHY_OVER


def test_a_map_without_regions_does_not_limit_the_answer():
    _, duel = _open(region=None)
    assert sortie_duel.answer_problem(CFG, duel, T0 + 60, **_answer_kw(region=None)) is None
    assert sortie_duel.answer_problem(CFG, duel, T0 + 60, **_answer_kw(region="jizhou")) is None


def test_the_first_to_answer_is_the_defender_and_the_second_hears_it_is_taken():
    _, duel = _open()
    sortie_duel.answer(duel, _side("張角", "huang"), T0 + 60)
    assert duel.status == "answered" and duel.defender.name == "張角" and duel.defender.sealed_at == T0 + 60
    assert sortie_duel.answer_problem(CFG, duel, T0 + 90, **_answer_kw(name="張寶")) == sortie_duel.WHY_TAKEN
    assert sortie_duel.answer_problem(CFG, duel, T0 + 90, **_answer_kw()) == sortie_duel.WHY_YOU


def test_comrades_join_instead_of_answering():
    _, duel = _open()
    now = T0 + 60
    assert sortie_duel.join_problem(duel, now, name="劉備", side="guan") is None
    sortie_duel.join(duel, "劉備")
    assert duel.attacker.allies == ["劉備"]
    assert sortie_duel.join_problem(duel, now, name="劉備", side="guan") == sortie_duel.WHY_JOINED
    assert sortie_duel.join_problem(duel, now, name="關羽", side="guan") == sortie_duel.WHY_MINE
    assert sortie_duel.join_problem(duel, now, name="張角", side="huang") == sortie_duel.WHY_NOT_ALLY
    assert sortie_duel.join_problem(duel, T0 + WINDOW, name="張飛", side="guan") == sortie_duel.WHY_OVER
    sortie_duel.join(duel, "劉備")  # 重按不重記
    assert duel.attacker.allies == ["劉備"]


def test_due_only_when_the_window_is_over_and_not_yet_settled():
    _, duel = _open()
    assert not sortie_duel.due(duel, T0 + WINDOW - 1)
    assert sortie_duel.due(duel, T0 + WINDOW)
    sortie_duel.answer(duel, _side("張角", "huang"), T0 + 60)
    assert not sortie_duel.due(duel, T0 + 61)  # 提早應戰也等窗滿
    assert sortie_duel.due(duel, T0 + WINDOW)
    _settle(duel)
    assert not sortie_duel.due(duel, T0 + WINDOW + 999)


# ── 到時沒人：假人補位 ──


def test_the_stand_in_comes_from_the_same_region_first():
    _, duel = _open()
    far, near = _side("遠客", "huang", region="jizhou"), _side("近客", "huang", region="yingchuan")
    comrade, me = _side("同袍", "guan"), _side("關羽", "guan")
    for seed in range(20):
        pick = sortie_duel.bot_answer(duel, [far, comrade, near, me], random.Random(seed))
        assert pick.name == "近客" and pick.side == "huang"
    pick = sortie_duel.bot_answer(duel, [far, comrade, me], random.Random(0))
    assert pick.name == "遠客"  # 同區沒有：這一邊任一個「趕來」
    assert sortie_duel.bot_answer(duel, [comrade, me], random.Random(0)) is None
    assert sortie_duel.bot_answer(duel, [], random.Random(0)) is None


def test_a_stand_in_without_moves_gets_three_and_answers_inside_the_window():
    _, duel = _open()
    bare = _side("近客", "huang", moves=())
    for seed in range(20):
        pick = sortie_duel.bot_answer(duel, [bare], random.Random(seed))
        assert len(pick.moves) == 3 and set(pick.moves) <= set(MOVES)  # 不挑撤退
        assert duel.opened_at <= pick.sealed_at <= duel.expires_at
    assert bare.moves == []  # 不改呼叫端給的那一份
    sealed = _side("近客", "huang", moves=("撤退", "撤退", "強攻"))
    assert sortie_duel.bot_answer(duel, [sealed], random.Random(0)).moves == ["撤退", "撤退", "強攻"]


# ── 三回合 ──


def test_three_rounds_won_is_a_big_win_and_none_won_is_a_loss():
    _, duel = _open(attacker=_side("關羽", power=1000.0))
    result = _settle(duel, _side("張角", "huang", power=10.0))
    assert (result.wins, result.losses, result.tier, result.defender_tier) == (3, 0, "big", "lose")
    assert [r.winner for r in result.rounds] == ["attacker"] * 3
    _, duel = _open(attacker=_side("關羽", power=10.0))
    result = _settle(duel, _side("張角", "huang", power=1000.0))
    assert (result.wins, result.losses, result.tier, result.defender_tier) == (0, 3, "lose", "big")


@pytest.mark.parametrize(("wins", "losses", "tier"), [
    (3, 0, "big"), (2, 0, "win"), (2, 1, "win"), (1, 0, "draw"), (1, 1, "draw"), (1, 2, "draw"),
    (0, 0, "draw"),  # 「平」：三回合全僵持
    (0, 1, "lose"), (0, 2, "lose"), (0, 3, "lose"),
])
def test_the_tally_three_two_one_or_even_zero(wins, losses, tier):
    """整合設計 4.3：三勝大勝、兩勝勝、一勝或平僵持、零勝敗（攻方的角度）。"""
    assert sortie_duel.total_tier(wins, losses) == tier


@pytest.mark.parametrize(("tier", "losses", "theirs"), [
    ("big", 0, "lose"), ("win", 1, "lose"), ("draw", 2, "draw"), ("draw", 0, "draw"),
    ("lose", 3, "big"), ("lose", 2, "win"), ("lose", 1, "win"),
])
def test_the_defender_side_of_the_tally(tier, losses, theirs):
    """守方贏（攻方 lose）時拉回的量照守方贏的回合數：三回合全贏 big、其餘 win（4.0 之二）。"""
    assert sortie_duel.defender_tier(tier, losses) == theirs


def test_retreat_concedes_the_round_and_costs_less():
    toll = CFG.round_toll
    _, duel = _open(attacker=_side("關羽", power=1000.0, moves=("強攻", "撤退", "強攻")))
    result = _settle(duel, _side("張角", "huang", power=10.0))
    assert [r.winner for r in result.rounds] == ["attacker", "defender", "attacker"]
    assert (result.wins, result.losses, result.tier) == (2, 1, "win")
    assert result.attacker_toll == pytest.approx(toll["win"] * 2 + toll["lose"] * CFG.retreat_toll)
    assert result.defender_toll == pytest.approx(toll["lose"] * 2 + toll["win"])
    # 打不過時：三回合都撤退比硬打少扣
    _, fought = _open(attacker=_side("關羽", power=10.0))
    _, fled = _open(attacker=_side("關羽", power=10.0, moves=("撤退",) * 3))
    hard = _settle(fought, _side("張角", "huang", power=1000.0))
    soft = _settle(fled, _side("張角", "huang", power=1000.0))
    assert hard.tier == soft.tier == "lose"
    assert soft.attacker_toll == pytest.approx(toll["lose"] * 3 * CFG.retreat_toll) and soft.attacker_toll < hard.attacker_toll


def test_both_retreating_is_a_draw_that_costs_both_a_little():
    _, duel = _open(attacker=_side("關羽", moves=("撤退",) * 3))
    result = _settle(duel, _side("張角", "huang", moves=("撤退",) * 3))
    assert [r.winner for r in result.rounds] == ["draw"] * 3 and result.tier == "draw"
    each = CFG.round_toll["draw"] * CFG.retreat_toll * 3
    assert result.attacker_toll == pytest.approx(each) and result.defender_toll == pytest.approx(each)


def test_the_counter_swings_the_attacker_power_each_round():
    """固守剋強攻、強攻剋奇襲、奇襲剋固守（tactics.counter）：剋中 ×(1＋counter_swing)、被剋 ×(1−counter_swing)；撤退那一回合不算相剋。"""
    _, duel = _open(attacker=_side("關羽", power=100.0, moves=("固守", "強攻", "撤退")))
    result = _settle(duel, _side("張角", "huang", power=100.0, moves=("強攻", "固守", "強攻")))
    assert [r.beat for r in result.rounds] == [1, -1, 0]
    assert [r.power for r in result.rounds] == pytest.approx([130.0, 70.0, 100.0])
    assert [(r.attacker_move, r.defender_move) for r in result.rounds] == [("固守", "強攻"), ("強攻", "固守"), ("撤退", "強攻")]


def test_changing_one_move_does_not_shift_the_luck_of_the_other_rounds():
    """每一回合都擲一次（撤退的回合也擲），換一招只動那一回合。"""
    _, a = _open(attacker=_side("關羽", moves=("強攻", "強攻", "強攻")))
    _, b = _open(attacker=_side("關羽", moves=("強攻", "撤退", "強攻")))
    ra, rb = _settle(a, _side("張角", "huang", moves=("奇襲",) * 3)), _settle(b, _side("張角", "huang", moves=("奇襲",) * 3))
    assert ra.rounds[0] == rb.rounds[0] and ra.rounds[2] == rb.rounds[2]


def test_the_result_does_not_depend_on_who_settles_it():
    _, a = _open()
    _, b = _open()
    assert _settle(a, _side("張角", "huang")) == _settle(b, _side("張角", "huang"))


# ── 到時結算：只往前走 ──


def _three_duels():
    shared, d1 = _open(id="d1")
    _open(shared, id="d2", attacker=_side("趙雲"))
    _open(shared, id="d3", attacker=_side("張飛"), now=T0 + 200)
    sortie_duel.answer(d1, _side("張角", "huang"), T0 + 30)
    return shared


def test_advance_settles_due_duels_once_and_a_stand_in_answers_the_unanswered():
    shared = _three_duels()
    asked = []

    def candidates_for(duel):
        asked.append(duel.id)
        return [_side("近客", "huang", moves=())]

    done = sortie_duel.advance(shared, CFG, T0 + WINDOW, candidates_for)
    assert sorted(d.id for d in done) == ["d1", "d2"]
    assert asked == ["d2"]  # 有人應戰的不問
    d1, d2, d3 = (shared.sorties[k] for k in ("d1", "d2", "d3"))
    assert d1.defender.name == "張角" and d2.defender.name == "近客" and not d2.defender.garrison
    assert d1.status == d2.status == "settled" and d1.settled_at == d2.settled_at == T0 + WINDOW
    assert d1.result is not None and d2.result is not None
    assert d3.status == "open"
    before = shared.model_dump_json()
    assert sortie_duel.advance(shared, CFG, T0 + WINDOW + 100, candidates_for) == []  # 兩個程式輪流同步：不重複結算、不倒退
    assert shared.model_dump_json() == before and asked == ["d2"]
    done = sortie_duel.advance(shared, CFG, T0 + 200 + WINDOW, candidates_for)
    assert [d.id for d in done] == ["d3"]


def test_the_same_duel_settles_the_same_however_it_is_reached():
    """advance 用的是這一場自己的亂數：伺服器排程或假人程式先到，結果都一樣。"""
    shared = _three_duels()
    copy = SharedWorldState.model_validate_json(shared.model_dump_json())
    sortie_duel.advance(shared, CFG, T0 + WINDOW, lambda d: [_side("近客", "huang", moves=())])
    sortie_duel.advance(copy, CFG, T0 + WINDOW + 7, lambda d: [_side("近客", "huang", moves=())])
    for key in ("d1", "d2"):
        assert shared.sorties[key].result == copy.sorties[key].result
        assert shared.sorties[key].defender == copy.sorties[key].defender


def test_no_one_on_the_other_side_means_the_garrison_and_without_it_nothing():
    garrison = _side("守軍", "huang", power=50.0, moves=(), garrison=True)
    shared, duel = _open(garrison=garrison)
    done = sortie_duel.advance(shared, CFG, T0 + WINDOW, lambda d: [])
    assert done == [duel] and duel.status == "settled"
    assert duel.defender.garrison and len(duel.defender.moves) == 3 and set(duel.defender.moves) <= set(MOVES)
    shared, duel = _open()
    done = sortie_duel.advance(shared, CFG, T0 + WINDOW, lambda d: [])
    assert done == [duel] and duel.status == "void" and duel.result is None and duel.settled_at == T0 + WINDOW


def test_season_end_voids_and_a_pause_holds():
    shared, old = _open(id="d0", now=T0 - WINDOW)
    sortie_duel.advance(shared, CFG, T0, lambda d: [_side("近客", "huang")])
    assert old.status == "settled"
    _, duel = _open(shared)
    shared.paused_at = T0 + 1
    assert sortie_duel.advance(shared, CFG, T0 + WINDOW * 5, lambda d: [_side("近客", "huang")]) == []
    assert duel.status == "open"
    shared.paused_at = None
    shared.season.ended = True
    done = sortie_duel.advance(shared, CFG, T0 + 30, lambda d: [_side("近客", "huang")])
    assert done == [duel] and duel.status == "void" and duel.defender is None
    assert old.status == "settled" and old.settled_at == T0  # 結算過的不再碰


def test_finished_duels_are_kept_for_a_while_then_dropped():
    shared, duel = _open()
    sortie_duel.advance(shared, CFG, T0 + WINDOW, lambda d: [_side("近客", "huang")])
    keep = CFG.keep_hours * 3600
    sortie_duel.advance(shared, CFG, T0 + WINDOW + keep - 1, lambda d: [])
    assert "d1" in shared.sorties
    sortie_duel.advance(shared, CFG, T0 + WINDOW + keep, lambda d: [])
    assert "d1" not in shared.sorties


# ── 懲罰的冷卻、戰報的字 ──


def test_cooldowns_after_a_duel():
    hour, half = CFG.cooldown_minutes * 60, CFG.lose_cooldown_minutes * 60
    _, won = _open(attacker=_side("關羽", power=1000.0))
    _settle(won, _side("張角", "huang", power=10.0))
    assert sortie_duel.cooldown_after(won, "關羽", CFG) == (T0 + hour, None)
    assert sortie_duel.cooldown_after(won, "張角", CFG) == (won.settled_at + half, won.settled_at + half)
    _, lost = _open(attacker=_side("關羽", power=10.0))
    _settle(lost, _side("張角", "huang", power=1000.0))
    assert sortie_duel.cooldown_after(lost, "關羽", CFG) == (T0 + hour + half, lost.settled_at + half)
    assert sortie_duel.cooldown_after(lost, "張角", CFG) == (None, None)
    assert sortie_duel.cooldown_after(lost, "路人", CFG) == (None, None)
    _, even = _open()
    _settle(even, _side("張角", "huang"))
    even.result = even.result.model_copy(update={"tier": "draw", "defender_tier": "draw"})
    assert sortie_duel.cooldown_after(even, "關羽", CFG) == (T0 + hour, None)
    assert sortie_duel.cooldown_after(even, "張角", CFG) == (None, None)


def test_side_tier_reads_the_result_from_each_side():
    _, duel = _open(attacker=_side("關羽", power=1000.0))
    sortie_duel.join(duel, "劉備")
    _settle(duel, _side("張角", "huang", power=10.0))
    assert sortie_duel.side_tier(duel, "關羽") == "大勝"
    assert sortie_duel.side_tier(duel, "劉備") == "大勝"
    assert sortie_duel.side_tier(duel, "張角") == "落敗"
    assert sortie_duel.side_tier(duel, "路人") is None


# ── 約戰卡（欄位表 main.sorties）──


CARD_KEYS = {"id", "block", "place", "attacker", "attacker_side", "defender", "expires_in", "status", "role", "can_answer",
             "can_join", "why_not", "answers_left", "same_region", "travel_minutes"}


def test_card_for_each_kind_of_viewer():
    _, duel = _open()
    now = T0 + 60
    mine = sortie_duel.card(duel, "關羽", "guan", "yingchuan", now, CFG, answers_left=3, stamina=50.0)
    assert set(mine) == CARD_KEYS
    assert (mine["role"], mine["can_answer"], mine["can_join"], mine["why_not"]) == ("mine", False, False, "")
    assert (mine["place"], mine["attacker"], mine["attacker_side"], mine["status"]) == ("長社", "關羽", "guan", "open")
    assert mine["expires_in"] == WINDOW - 60 and mine["defender"] is None
    near = sortie_duel.card(duel, "張角", "huang", "yingchuan", now, CFG, answers_left=3, stamina=50.0, travel_minutes=0)
    assert (near["role"], near["can_answer"], near["why_not"], near["same_region"], near["travel_minutes"]) == (
        "answer", True, "", True, None)
    assert near["answers_left"] == 3
    far = sortie_duel.card(duel, "張寶", "huang", "jizhou", now, CFG, answers_left=2, stamina=50.0, travel_minutes=8)
    assert (far["can_answer"], far["why_not"], far["same_region"], far["travel_minutes"]) == (
        False, "在潁川汝南才應得了戰", False, 8)
    ally = sortie_duel.card(duel, "劉備", "guan", "jizhou", now, CFG, answers_left=3, stamina=50.0)
    assert (ally["role"], ally["can_join"], ally["can_answer"]) == ("join", True, False)
    sortie_duel.answer(duel, _side("張角", "huang"), now)
    taken = sortie_duel.card(duel, "張寶", "huang", "yingchuan", now, CFG, answers_left=3, stamina=50.0)
    assert (taken["status"], taken["defender"], taken["can_answer"], taken["why_not"]) == (
        "answered", "張角", False, sortie_duel.WHY_TAKEN)


def test_card_after_the_window_and_with_the_garrison():
    shared, duel = _open(garrison=_side("某營", "huang", power=50.0, moves=(), garrison=True))
    sortie_duel.advance(shared, CFG, T0 + WINDOW, lambda d: [])
    card = sortie_duel.card(duel, "張角", "huang", "yingchuan", T0 + WINDOW + 5, CFG, answers_left=3, stamina=50.0)
    assert (card["status"], card["defender"], card["expires_in"], card["can_answer"]) == (
        "settled", sortie_duel.GARRISON, 0, False)


# ── 存檔：空的時候不多鍵、舊的讀得進來 ──


ROW_EXCLUDE = {"season", "active_battle", "sieges"}  # sqlite_world._save 寫 world 那一列的樣子


def test_shared_world_json_has_no_sorties_key_until_there_is_one():
    st = SharedWorldState()
    assert "sorties" not in json.loads(st.model_dump_json(exclude=ROW_EXCLUDE)) and "sorties" not in st.model_dump()
    old = json.loads(st.model_dump_json(exclude=ROW_EXCLUDE))
    assert SharedWorldState.model_validate_json(json.dumps(old)).sorties == {}  # 舊的 JSON 少這一格讀得進來
    _open(st)
    row = st.model_dump_json(exclude=ROW_EXCLUDE)
    assert "d1" in json.loads(row)["sorties"]
    back = SharedWorldState.model_validate_json(row)
    assert back.sorties["d1"] == st.sorties["d1"] and isinstance(back.sorties["d1"], SortieDuel)


def test_the_world_row_stores_reads_shifts_and_clears_sorties(content):
    world = open_world()
    world.seed_first_season(content)

    def raw() -> str:
        with world.db.snapshot() as conn:
            return conn.execute("SELECT data FROM world WHERE id = 1").fetchone()["data"]

    assert "sorties" not in json.loads(raw())
    assert world.sortie_duels() == {}
    world.mutate(lambda st: _open(st))
    assert world.sortie_duels()["d1"].attacker.name == "關羽"
    assert world.read().sorties["d1"].expires_at == T0 + WINDOW
    assert "sorties" in json.loads(raw())
    # 暫停：繼續時窗的期限往後挪停的長度（同奪璽單挑；開約戰的時刻不動，這一場的亂數照舊）
    assert world.pause_clock(T0 + 100)
    world.resume_clock(content, T0 + 400)
    moved = world.sortie_duels()["d1"]
    assert moved.expires_at == T0 + WINDOW + 300 and moved.opened_at == T0
    # 換季：不帶進下一季
    world.mutate(lambda st: setattr(st.season, "ended", True))
    assert world.next_season(content, T0 + 1000)
    assert world.sortie_duels() == {} and "sorties" not in json.loads(raw())


def test_result_models_round_trip():
    _, duel = _open()
    result = _settle(duel, _side("張角", "huang"))
    assert SortieResult.model_validate_json(result.model_dump_json()) == result


# ── conquest.pull：守方贏了拉攻方那一條（企劃者 2026-10-24 第 1 件）──


@pytest.mark.slow
def test_pull_lowers_only_that_attackers_bar_and_respects_the_still_times():
    from conquest_kit import announce, conquest_game

    g = conquest_game()
    w, c = g.state.world, g.content
    loc = next(x for x, b in conquest.blocks(c).items() if b.kind == "neutral" and conquest.capturable(c, x))
    conquest.push(w, c, loc, "huang", "甲", 30, "attack")
    conquest.push(w, c, loc, "guan", "乙", 20, "attack")
    done = conquest.pull(w, c, loc, "huang", 10)
    assert done.moved == pytest.approx(10) and done.value == pytest.approx(20) and not done.guarded
    assert conquest.bars(w, loc) == pytest.approx({"huang": 20, "guan": 20})  # 守方自己的條、別的攻方的條都不動
    assert conquest.fight_of(w, loc).bars["huang"].pushers == {"甲": pytest.approx(30)}  # 這一輪的帳照留
    done = conquest.pull(w, c, loc, "huang", 50)  # 夾 0、那一條拿掉
    assert done.moved == pytest.approx(20) and done.value == 0 and "huang" not in conquest.fight_of(w, loc).bars
    assert conquest.bars(w, loc) == pytest.approx({"guan": 20})
    assert conquest.pull(w, c, loc, "huang", 5).moved == 0  # 沒有那一條：什麼都不動
    # 剛易手的冷卻：兩邊都推不動（翻地設計 4.1）
    fight = conquest.fight_of(w, loc)
    fight.flipped_at = w.time
    assert conquest.pull(w, c, loc, "guan", 5).moved == 0 and conquest.bar(w, loc, "guan") == pytest.approx(20)
    fight.flipped_at = None
    # 被戰書凍結：不動
    slot = announce(g, loc, "guan")
    assert conquest.pull(w, c, loc, "guan", 5).moved == 0
    w.conquest.schedule.remove(slot)
    assert conquest.pull(w, c, loc, "guan", 5).moved == pytest.approx(5)


@pytest.mark.slow
def test_pull_to_zero_after_the_alarm_reports_guarded_and_clears_the_alarm():
    from conquest_kit import conquest_game

    g = conquest_game()
    w, c = g.state.world, g.content
    loc = next(x for x, b in conquest.blocks(c).items() if b.kind == "neutral" and conquest.capturable(c, x))
    conquest.push(w, c, loc, "huang", "甲", c.config.conquest.alarm_at + 5, "attack")
    fight = conquest.fight_of(w, loc)
    assert fight.alarm
    w.time += 100
    done = conquest.pull(w, c, loc, "huang", 100)
    assert done.guarded and not fight.alarm and fight.bars == {} and fight.guards == {}
    assert fight.last_push == w.time
    assert w.conquest.payouts == []  # 分不分守城功是接線那一批的事
