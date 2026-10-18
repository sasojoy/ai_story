"""歷史武將同行第五節：大決戰裡隨主人上陣的同伴（battle_instance.Escort）——照主人的招出手、份量算進那一邊、集火平分、
點名打得到、固守護他、敗走推戰局；主人離開大區他也不在場上。加入決戰時挑一位、打完回江湖在後面幾段。"""
from __future__ import annotations

import random

import pytest

from conftest import real_content
from tianxia import battle_instance as bi
from tianxia import tactics


@pytest.fixture
def c():
    return real_content()


def _battle(c, battle_id="changshe_fire"):
    d = c.battles[battle_id]
    return d, bi.start_muster(d, now=0.0)


def _sides(d):
    return d.factions[0].id, d.factions[1].id


def _join(c, inst, name, side, power=100.0, escort=None):
    scores = bi.move_scores(c.config.battle, power, None, None)
    bi.join_faction(inst, name, side, 400.0, power, scores=scores, escort=escort)


def _escort(name="關羽", cid="guanyu", score=60.0, pool=400.0, neili=None, kit=None):
    return bi.Escort(cid=cid, name=name, score=score, neili=pool if neili is None else neili, neili_cap=pool, kit=kit)


def _open(c, d, inst):
    bi.close_muster(inst, d, random.Random(0), 0.0, c.config.battle)


def _act(inst, d, name, move):
    inst.round.pending_actions[name] = next(o.tag for o in bi.options_for(inst, d, name) if o.move == move)


def _gamble(inst, d, name, text, rate=100):
    inst.round.pending_actions[name] = next(o.tag for o in bi.options_for(inst, d, name) if o.free_text)
    inst.round.success_rates[name] = rate
    inst.round.custom_texts[name] = text


def _round(c, inst, d, seed=0, tuning=None):
    return bi.resolve_round(inst, d, random.Random(seed), now=1.0, tuning=tuning or c.config.battle, tactic=c.config.tactics)


def test_an_escort_follows_his_owners_move_and_adds_weight(c):
    def run(escort, gamble=False):
        d, inst = _battle(c)
        a, b = _sides(d)
        _join(c, inst, "甲", a, escort=escort)
        _join(c, inst, "乙", b)
        _open(c, d, inst)
        if gamble:
            _gamble(inst, d, "甲", "衝陣", rate=50)
        else:
            _act(inst, d, "甲", "強攻")
        _act(inst, d, "乙", "強攻")
        _round(c, inst, d)
        return inst, a

    plain, a = run(None)
    helped, _ = run(_escort())
    assert helped.trend > plain.trend  # 份量加在主人那一邊（第一方往上推）
    assert helped.last_mix[a]["強攻"] == 1.0  # 他照主人的招：強攻
    held, _ = run(_escort(), gamble=True)
    assert held.last_mix[a]["固守"] == 1.0  # 主人放手一搏：他固守


def test_escorts_take_split_focus_in_one_line(c):
    tuning = c.config.battle
    d, inst = _battle(c)
    a, b = _sides(d)
    for i, (cid, name) in enumerate([("guanyu", "關羽"), ("zhangfei", "張飛"), ("liubei", "劉備")]):
        _join(c, inst, f"甲{i}", a, escort=_escort(name, cid, pool=1000.0))
    for i in range(3):
        _join(c, inst, f"乙{i}", b, power=300.0)
    _open(c, d, inst)
    for i in range(3):
        _act(inst, d, f"甲{i}", "奇襲")
        _act(inst, d, f"乙{i}", "強攻")
    msgs = _round(c, inst, d)
    assert len([m for m in msgs if "隨行的 3 位武將" in m]) == 1  # 讀得下去：三位挨打合成一句
    for i in range(3):  # 三個強攻 × focus_per_attacker 平分給三位（沒人固守護）
        assert inst.participants[f"甲{i}"].escort.neili == pytest.approx(1000 - tuning.focus_per_attacker)


def test_an_escort_falls_pushes_the_line_and_counts_a_slay(c):
    def run(push):
        tuning = c.config.battle.model_copy(deep=True)
        tuning.generals.escort_fall_push = push
        d, inst = _battle(c)
        a, b = _sides(d)
        _join(c, inst, "甲", a, escort=_escort(pool=1000.0, neili=5.0))
        _join(c, inst, "乙", b, power=300.0)
        _open(c, d, inst)
        _act(inst, d, "甲", "奇襲")
        _act(inst, d, "乙", "強攻")
        msgs = _round(c, inst, d, tuning=tuning)
        return inst, msgs

    fell, msgs = run(2)
    e = fell.participants["甲"].escort
    assert e.fallen_round == 1 and e.felled_by == "乙" and fell.participants["乙"].slew == 1
    assert any("隨甲出陣的關羽陣前敗走" in m for m in msgs)
    still, _ = run(0)
    assert fell.trend == still.trend - 2  # 戰局往對面（第二方）推 2


def test_naming_an_escort_hits_him_but_a_participant_comes_first(c):
    d, inst = _battle(c)
    a, b = _sides(d)
    _join(c, inst, "甲", a, escort=_escort())
    _join(c, inst, "乙", b)
    _open(c, d, inst)
    _act(inst, d, "甲", "固守")
    _gamble(inst, d, "乙", "一刀劈向關羽")
    _round(c, inst, d)
    e = inst.participants["甲"].escort
    assert e.neili < e.neili_cap and inst.participants["乙"].hits_landed == 1

    d, inst = _battle(c)  # 對面有一個參戰者也叫關羽：參戰者優先
    _join(c, inst, "甲", a, escort=_escort())
    _join(c, inst, "關羽", a)
    _join(c, inst, "乙", b)
    _open(c, d, inst)
    _act(inst, d, "甲", "固守")
    _act(inst, d, "關羽", "固守")
    _gamble(inst, d, "乙", "一刀劈向關羽")
    _round(c, inst, d)
    e = inst.participants["甲"].escort
    assert e.neili == e.neili_cap and inst.participants["關羽"].neili < inst.participants["關羽"].neili_cap


def test_an_absent_owner_takes_his_escort_off_the_field(c):
    d, inst = _battle(c)
    a, b = _sides(d)
    _join(c, inst, "甲", a, escort=_escort())
    _join(c, inst, "乙", b, power=300.0)
    _open(c, d, inst)
    inst.participants["甲"].away = True
    _act(inst, d, "乙", "強攻")
    _round(c, inst, d)
    e = inst.participants["甲"].escort
    assert e.neili == e.neili_cap and not any(inst.last_mix[a].values())  # 不出手、也挨不到集火
    assert bi.find_escort(inst, d, "乙", "一刀劈向關羽") is None  # 點名也找不到他


def test_an_escort_fires_his_war_tactic_under_his_name(c):
    holders = tactics.holders_of(c, [("關羽", "guanyu", "guanyu_wugong", "guanyu_neigong")])
    kit = tactics.side_for(holders, tactics.Ctx(foe="", team=["guanyu"]))
    d, inst = _battle(c)
    a, b = _sides(d)
    _join(c, inst, "甲", a, escort=_escort(kit=kit))
    _join(c, inst, "乙", b)
    _open(c, d, inst)
    fired = []
    for seed in range(9):
        if inst.phase == "ended":
            break
        _act(inst, d, "甲", "強攻")
        _act(inst, d, "乙", "強攻")
        fired += [m for m in _round(c, inst, d, seed=seed) if "〔青龍拖刀〕" in m or "〔刮骨定神〕" in m]
    assert fired and all("關羽" in m for m in fired)
