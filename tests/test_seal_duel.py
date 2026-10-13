"""奪璽單挑的純函式（玉璽碎片設計第五節；計畫 docs/superpowers/plans/2026-10-12-玉璽-1-核心.md Task 7）。"""
from __future__ import annotations

import random

import pytest

from test_seal import SALT, put_shards
from tianxia import duel as duel_rules
from tianxia import seal, seal_duel
from tianxia.models import BattleTuning, DuelTuning, SealTuning
from tianxia.state import WorldState
from tianxia.world_state import SealDuel, SealSide, SharedWorldState


def _side(name, power=80.0, scores=None, role="", seen=None):
    return SealSide(name=name, power=power, scores=scores or {"強攻": 60.0, "固守": 60.0, "奇襲": 60.0}, role=role,
                    hp=300.0, hp_cap=300.0, last_seen=seen)


def _duel(cap=0.25, **over):
    d = SealDuel(id="7:chishou", shard="chishou", record=7, where="長社火攻", phase="active", starts_real=0.0,
                 challenger=_side("挑戰者"), holder=_side("懷璽"), cap=cap)
    return d.model_copy(update=over)


def _shared(content, duel=None, holder="懷璽"):
    st = SharedWorldState(season=WorldState(time=100.0), season_number=3, tianji=2)
    reg = seal.filled(st.seal, content)
    reg.salt = SALT
    reg.shards["chishou"].state, reg.shards["chishou"].holder, reg.shards["chishou"].since_season = "held", holder, 1
    if duel is not None:
        st.seal_duels = [duel]
    return st


def test_the_pure_pieces_draw_exactly_one_number_each():
    """duel.py 抽出來的純函式：gamble_roll 只取一次亂數、push_of 不取（luck 是呼叫端擲好的）；軍師 +10。
    頭目戰（exchange、gamble、verdict）照舊——tests/test_duel.py 一個字都不改照樣全過，是主要的保證。"""
    tuning, battle = DuelTuning(), BattleTuning()
    rng, ref = random.Random(5), random.Random(5)
    duel_rules.gamble_roll(50, 300.0, 80.0, "wis", tuning, battle, rng)
    ref.random()
    assert rng.getstate() == ref.getstate()
    won, delta, hp, rate = duel_rules.gamble_roll(50, 300.0, 80.0, "wis", tuning, battle, random.Random(1))
    assert rate == 60
    assert hp == (round(300 * tuning.success_hp) if won else round(300 * (tuning.fail_hp_base + 40 * tuning.fail_hp_per_risk)))
    assert duel_rules.push_of(60.0, 60.0, 0, "", tuning, battle, 2.6) == 3  # 等份量、不剋：只剩運氣
    assert duel_rules.verdict_at(91.0, 10.0, 1, 5, tuning) == "大勝" and duel_rules.verdict_at(50.0, 0.0, 1, 5, tuning) == "落敗"


def test_both_sides_lose_their_own_pool_and_a_lore_side_takes_half_the_counter():
    """5.2：兩邊各扣自己的池子；被剋的一方是參謀時剋制那一截減半，剋人的一方遇上參謀時推力的那一截也減半。"""
    tuning, battle = DuelTuning(), BattleTuning()
    assert duel_rules.push_of(60.0, 60.0, -1, "", tuning, battle, 0.0) == -8
    assert duel_rules.push_of(60.0, 60.0, -1, "lore", tuning, battle, 0.0) == -4
    assert duel_rules.push_of(60.0, 60.0, 1, "", tuning, battle, 0.0, foe_role="lore") == 4
    assert duel_rules.harm_of(300.0, 60.0, 60.0, -1, tuning) == round(300 * 0.08 * 1.6)
    assert duel_rules.harm_of(300.0, 60.0, 60.0, 1, tuning) == round(300 * 0.08 * 0.5)


def test_a_round_with_one_gamble_ignores_the_other_move(content):
    """只有一邊放手一搏：搏的那一邊照 gamble_roll 擲，另一邊這一招不算、不扣血（同頭目戰「你搶了先手，或自己栽了」）。"""
    put_shards(content)
    d = _duel()
    d.challenger.present = True
    seal_duel.submit(d, "challenger", text="點燃糧車", rate=100, stories=("挑戰者點燃糧車，火光沖天。", "挑戰者被火燎了眉毛。"))
    d.proxy_move["holder"] = "強攻"
    line = seal_duel.resolve(d, content, SALT, 2)
    assert d.holder.hp == 300.0 and d.edge > 50 and d.challenger.gambles == 1
    assert "挑戰者點燃糧車" in line and line.startswith("奪璽第 1 回合")



def test_a_story_that_takes_the_shard_falls_back_to_the_plain_line(content):
    """FB-176（引擎擋）：劇情寫「奪下／奪得／搶下……碎片、印、璽」那一版不用，改播固定句——碎片要到收場再擲才定歸屬。
    沒寫奪璽的照播；兩邊各一版、各自判。"""
    assert seal_duel.claims_shard("陸乙使出誘敵之計，趁韓甲出招空檔，順勢奪下玉璽碎片。")
    assert seal_duel.claims_shard("陸乙虛晃一槍誘使韓甲出招，趁其重心不穩，反手奪下印模勢如破竹。")
    assert seal_duel.claims_shard("陸乙一把搶下了韓甲懷裡的璽。") and seal_duel.claims_shard("陸乙奪得碎片。")
    assert not seal_duel.claims_shard("陸乙踏碎青磚，揚起塵土迷了韓甲的眼。")
    assert not seal_duel.claims_shard("陸乙搶下先手，逼得韓甲連退三步。")
    put_shards(content)
    d = _duel()
    d.challenger.present = True
    seal_duel.submit(d, "challenger", text="反手奪印", rate=100, stories=("挑戰者順勢奪下玉璽碎片。", "挑戰者撲了個空。"))
    assert d.stories["challenger"] == ["", "挑戰者撲了個空。"]
    d.proxy_move["holder"] = "強攻"
    line = seal_duel.resolve(d, content, SALT, 2)
    assert "奪下" not in line and seal_duel.GAMBLE_WON.format(name="挑戰者").rstrip("。") in line


def test_both_gambles_add_up(content):
    put_shards(content)
    d = _duel()
    for who in seal_duel.SIDES:
        getattr(d, who).present = True
        seal_duel.submit(d, who, text="拚了", rate=100)
    seal_duel.resolve(d, content, SALT, 2)
    assert d.edge == 50.0  # 兩邊同強、都成：推力抵銷
    assert d.challenger.gambles == d.holder.gambles == 1


def test_the_verdict_from_the_challenger_side():
    tuning = DuelTuning()
    d = _duel()
    d.holder.hp = 0
    assert seal_duel.verdict(d, tuning) == "大勝"  # 持有者池子見底（不算提前大勝）
    d.challenger.hp = 0
    assert seal_duel.verdict(d, tuning) == "落敗"  # 同一回合兩邊見底：偏持有者
    assert seal_duel.verdict(_duel(edge=92.0), tuning) == "提前大勝"
    assert seal_duel.verdict(_duel(edge=60.0, round=5), tuning) == "險勝"
    assert seal_duel.verdict(_duel(edge=60.0, round=3), tuning) is None


def test_the_proxy_leans_on_the_strongest_move():
    """5.6：招的權重是（份量 ÷ 最高）^4；75／60／90 的人最常出的那一招約 59%。"""
    weights = seal_duel.proxy_weights(_side("某", scores={"強攻": 75.0, "固守": 60.0, "奇襲": 90.0}), SealTuning())
    assert weights[2] / sum(weights) == pytest.approx(0.595, abs=0.01)
    assert seal_duel.proxy_weights(_side("空", scores={"強攻": 0.0}), SealTuning()) == [1.0, 1.0, 1.0]


def test_only_the_absent_side_gets_a_tell_and_cannot_send(content):
    """回合一開：45 秒內推過這場的人才在場；不在場的那一邊預擲一招與一句架勢（只給對手看），這一回合送不出去。"""
    put_shards(content)
    d = _duel()
    d.challenger.last_seen = 970.0
    seal_duel.open_round(d, 1000.0, content, SALT, 2)
    assert d.challenger.present and not d.holder.present
    assert "holder" in d.tell and "challenger" not in d.tell and d.proxy_move["holder"] in ("強攻", "固守", "奇襲")
    assert seal_duel.submit_problem(d, "holder", content.config.seal) == seal_duel.LATE
    assert seal_duel.submit_problem(d, "challenger", content.config.seal) is None
    assert seal_duel.sent(d) == 0  # 代打那一手到結算才算


def test_the_round_waits_at_least_the_pace_and_at_most_the_round_seconds(content):
    put_shards(content)
    cfg = content.config.seal
    d = _duel()
    seal_duel.open_round(d, 1000.0, content, SALT, 2)  # 兩邊都不在場
    assert not seal_duel.due(d, 1019.0, cfg) and seal_duel.due(d, 1020.0, cfg)
    d.challenger.last_seen = 1000.0
    seal_duel.open_round(d, 1000.0, content, SALT, 2)
    assert not seal_duel.due(d, 1060.0, cfg)  # 在場的還沒送：等
    seal_duel.submit(d, "challenger", move="強攻")
    assert not seal_duel.due(d, 1010.0, cfg) and seal_duel.due(d, 1020.0, cfg)  # 送了也等滿 20 秒（節奏看不出誰不在場）
    d.challenger.last_seen = 1990.0
    seal_duel.open_round(d, 2000.0, content, SALT, 2)
    assert not seal_duel.due(d, 2100.0, cfg) and seal_duel.due(d, 2120.0, cfg)  # 在場卻一直沒送：120 秒照樣結算


def test_a_side_may_gamble_at_most_twice(content):
    put_shards(content)
    d = _duel()
    d.challenger.present, d.challenger.gambles = True, 2
    assert seal_duel.submit_problem(d, "challenger", content.config.seal, text=True) == seal_duel.NO_MORE_GAMBLE
    assert seal_duel.submit_problem(d, "challenger", content.config.seal, text=False) is None


@pytest.mark.parametrize("seed", range(30))
def test_the_take_chance_never_passes_the_duel_cap(content, seed):
    """5.8 的性質測試：任意出招、任意成功率、雙方在不在場，易手機率 ≤ cap（＝25% × 局勢 × 護璽）。"""
    put_shards(content)
    rng = random.Random(seed)
    cap = 0.25 * rng.choice([1.0, 0.7])
    d = _duel(cap=cap)
    result = None
    for n in range(5):
        seal_duel.open_round(d, n * 200.0, content, SALT, seed)
        for who in seal_duel.SIDES:
            if rng.random() < 0.5:
                getattr(d, who).present = True
                if rng.random() < 0.5 and getattr(d, who).gambles < 2:
                    seal_duel.submit(d, who, text="亂來", rate=rng.randint(0, 100))
                else:
                    seal_duel.submit(d, who, move=rng.choice(["強攻", "固守", "奇襲"]))
        seal_duel.resolve(d, content, SALT, seed)
        result = seal_duel.verdict(d, content.config.duel)
        if result is not None:
            break
    assert seal_duel.take_chance(d, result or "僵持", content.config.seal) <= cap + 1e-9


def test_a_duel_nobody_attends_finishes_in_paced_rounds_and_is_the_same_every_time(content):
    """兩邊都不在場：每回合 20 秒；最多五回合收場、寫天下大事；同樣的種子結果一模一樣（誰觸發都一樣）。"""
    put_shards(content)

    def run():
        st = _shared(content, _duel(phase="muster", starts_real=0.0))
        lines, t = [], 0.0
        while st.seal_duels and t < 400:
            lines += seal_duel.advance(st, content, t)
            t += 20.0
        return lines, st.seal.history[-1].model_dump(), st.seal.shards["chishou"].holder

    first = run()
    assert first == run()
    _, event, holder = first
    assert event["kind"] in ("take", "keep") and 1 <= len(event["lines"]) <= 5
    assert holder == ("挑戰者" if event["kind"] == "take" else "懷璽")


def test_finish_checks_the_registry_before_handing_over(content):
    """5.9：持有者還是原來那人、挑戰者此刻手上沒有碎片才換；不成立記成沒打成（unsettled）。"""
    put_shards(content)
    d = _duel(fixed=True)
    st = _shared(content, d)
    st.seal.shards["xuanniu"].state, st.seal.shards["xuanniu"].holder = "held", "挑戰者"  # 他排隊的時候拿到了一片
    event = seal_duel.finish(st, d, content, "提前大勝", 500.0)
    assert event.kind == "unsettled" and st.seal.shards["chishou"].holder == "懷璽" and st.seal_duels == []
    d2 = _duel(fixed=True)
    st2 = _shared(content, d2)
    event2 = seal_duel.finish(st2, d2, content, "提前大勝", 500.0)
    shard = st2.seal.shards["chishou"]
    assert event2.kind == "take" and (shard.holder, shard.former, shard.since_season) == ("挑戰者", "懷璽", 3)


def test_the_card_shows_the_tell_only_to_the_opponent_and_flips_the_edge_for_the_holder(content):
    put_shards(content)
    d = _duel(edge=70.0)
    d.tell = {"holder": "他退了半步，門戶守得嚴嚴實實。"}
    as_challenger = seal_duel.card(d, "挑戰者", 1000.0, content)
    as_holder = seal_duel.card(d, "懷璽", 1000.0, content)
    as_crowd = seal_duel.card(d, "路人", 1000.0, content)
    assert as_challenger["tell"] and not as_holder["tell"] and not as_crowd["tell"]
    assert "你" in as_holder["edge"] and as_holder["edge"] != as_challenger["edge"]
    assert (as_crowd["challenger"], as_crowd["holder"], as_crowd["shard"]) == ("挑戰者", "懷璽", "螭首")
