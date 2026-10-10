"""放手一搏一幕一次、點名、顯眼、帶頭（Joy 2026-10-10 決戰試玩回饋）：
「跟從預設選項的玩家現在毫無存在感，他們應該也要有出場機會」；「被點名的玩家根本沒受到任何影響……在戰場上引人注目本來就容易被針對」。"""
import random

import pytest

from conftest import FixedRandom
from tianxia import battle_instance as bi
from tianxia.models import MOVES, BattleAct, BattleDef, BattleFaction, BattleOption, BattleOutcome, BattleTuning, FreeTextGamble

CODES = {"強攻": "strong", "固守": "hold", "奇襲": "raid"}
WIN = FixedRandom(0.0)  # 成功率大於 0 一定成
LOSE = FixedRandom(0.999)  # 成功率不到 100 一定失手


@pytest.fixture
def gamble() -> BattleDef:
    """兩幕、一幕兩回合，兩邊各三招加一個放手一搏。"""
    options = [
        BattleOption(text=f"{side}{move}", tag=f"{side}_{CODES[move]}", faction=side, move=move)
        for side in ("guan", "huang") for move in MOVES
    ] + [BattleOption(text="放手一搏", tag=f"{side}_reckless", faction=side, free_text=True) for side in ("guan", "huang")]
    return BattleDef(
        id="g", name="點名之戰",
        factions=[BattleFaction(id="guan", name="官軍"), BattleFaction(id="huang", name="黃巾")],
        acts=[
            BattleAct(id="a1", title="對陣", text="兩軍對陣。", goal="推動戰局", options=options),
            BattleAct(id="a2", title="鏖戰", text="犬牙交錯。", goal="撐過消耗", options=options),
        ],
        rounds_per_act=2, decisive_margin=49,
        outcomes=[BattleOutcome(faction="guan", title="收場", text="戰罷。")],
        free_text_gamble=FreeTextGamble(side_trend_cap=100),
    )


def _battle(definition, people):
    """people：[(名號, 陣營), ...]，每人三招份量 50、氣血 1000。"""
    battle = bi.start_muster(definition, now=0)
    for name, side in people:
        bi.join_faction(battle, name, side, neili_cap=1000, scores={m: 50.0 for m in MOVES})
    bi.close_muster(battle, definition, random.Random(0), now=0)
    return battle


def _round(battle, definition, actions, rng=WIN, tuning=None):
    """actions：{名號: 招或（文字, 成功率）}。"""
    for name, act in actions.items():
        side = battle.participants[name].faction
        if isinstance(act, tuple):
            bi.submit_action(battle, name, f"{side}_reckless", text=act[0], success_rate=act[1], stories=(f"{name}成了。", f"{name}砸了。"))
        else:
            bi.submit_action(battle, name, f"{side}_{CODES[act]}")
    return bi.resolve_round(battle, definition, rng, now=1, tuning=tuning or BattleTuning())


def _tags(battle, definition, name):
    return [o.tag for o in bi.options_for(battle, definition, name)]


# ── 一幕只搏一次 ──────────────────────────────────────────


def test_one_gamble_per_act_then_only_the_three_moves_until_the_next_act(gamble):
    battle = _battle(gamble, [("甲", "guan"), ("乙", "huang")])
    assert "guan_reckless" in _tags(battle, gamble, "甲")
    _round(battle, gamble, {"甲": ("夜襲敵營", 50), "乙": "固守"})
    assert _tags(battle, gamble, "甲") == ["guan_strong", "guan_hold", "guan_raid"]  # 同一幕：搏過了
    assert "huang_reckless" in _tags(battle, gamble, "乙")  # 沒搏的人照舊
    _round(battle, gamble, {"甲": "固守", "乙": "固守"})
    assert battle.act_index == 1
    assert "guan_reckless" in _tags(battle, gamble, "甲")  # 換幕又能搏


def test_per_act_can_allow_more(gamble):
    gamble.free_text_gamble.per_act = 2
    battle = _battle(gamble, [("甲", "guan"), ("乙", "huang")])
    _round(battle, gamble, {"甲": ("夜襲敵營", 50), "乙": "固守"})
    assert "guan_reckless" in _tags(battle, gamble, "甲")


def test_old_participants_without_the_new_fields_can_gamble():
    p = bi.BattleParticipant.model_validate({"name": "舊", "faction": "guan", "neili": 10, "neili_cap": 10})
    assert p.gambled_act == -1 and p.pinned_round == 0 and p.targeted_by == [] and p.hurt_taken == 0
    old = bi.BattleInstance.model_validate({"battle_id": "x", "trend": 50})
    assert old.marked == {} and old.last_targets == {}


# ── 點名 ──────────────────────────────────────────────


def test_find_target_is_the_first_enemy_named_and_never_a_friend(gamble):
    battle = _battle(gamble, [("甲", "guan"), ("張三", "guan"), ("姑姑", "huang"), ("姑姑姑", "huang"), ("李", "huang")])
    assert bi.find_target(battle, gamble, "甲", "生擒姑姑").name == "姑姑"
    assert bi.find_target(battle, gamble, "甲", "生擒姑姑姑").name == "姑姑姑"  # 一樣早取長的
    assert bi.find_target(battle, gamble, "甲", "先救張三再打姑姑").name == "姑姑"  # 自己人不算
    assert bi.find_target(battle, gamble, "甲", "打李") is None  # 一個字的名號不認，免得亂中
    battle.participants["姑姑姑"].eliminated = True
    assert bi.find_target(battle, gamble, "甲", "生擒姑姑姑").name == "姑姑"  # 倒下的不算
    assert bi.find_target(battle, gamble, "姑姑姑", "砍翻張三再砍甲").name == "張三"


def test_the_target_line_tells_the_model_who_it_is_without_numbers(gamble):
    battle = _battle(gamble, [("甲", "guan"), ("姑姑", "huang")])
    battle.participants["姑姑"].power = 400
    battle.participants["姑姑"].neili = 300
    line = bi.target_line(battle, gamble, "甲", "生擒姑姑", BattleTuning())
    assert line == "姑姑（黃巾，身手遠比玩家強，已經帶傷）"
    assert bi.target_line(battle, gamble, "甲", "火燒連營", BattleTuning()) == ""


def test_a_named_success_hurts_the_target_and_halves_the_push(gamble):
    plain = _battle(gamble, [("甲", "guan"), ("姑姑", "huang")])
    _round(plain, gamble, {"甲": ("火燒連營", 40), "姑姑": "固守"})
    named = _battle(gamble, [("甲", "guan"), ("姑姑", "huang")])
    msgs = _round(named, gamble, {"甲": ("生擒姑姑", 40), "姑姑": "固守"})
    plain_push = plain.trend - 50 + 10  # 只有姑姑出固定招：黃巾推滿 −10，剩下的是甲那一搏
    named_push = named.trend - 50 + 10
    tuning = BattleTuning()
    gk = named.participants["姑姑"]
    want = 1000 * (tuning.target_hit_base + 60 * tuning.target_hit_per_risk)  # 風險 60：一成九
    assert named_push == max(1, round(plain_push * tuning.target_push_share))
    assert gk.neili == pytest.approx(plain.participants["姑姑"].neili - want)
    assert gk.hurt_taken == pytest.approx(want) and gk.targeted_by == ["甲"]
    assert named.participants["甲"].hurt_dealt == pytest.approx(want)
    assert any(m.startswith("甲成了。（官軍的戰局推進") and f"姑姑氣血 -{round(want)}" in m for m in msgs)
    assert named.last_targets == {"姑姑": ["甲"]} and named.marked == {"姑姑": 0, "甲": 0}


def test_a_failed_named_gamble_hurts_only_yourself(gamble):
    battle = _battle(gamble, [("甲", "guan"), ("姑姑", "huang")])
    _round(battle, gamble, {"甲": ("生擒姑姑", 40), "姑姑": "固守"}, rng=LOSE)
    gk = battle.participants["姑姑"]
    assert gk.hurt_taken == 0 and battle.participants["甲"].hurt_dealt == 0
    assert gk.targeted_by == ["甲"] and battle.last_targets == {"姑姑": ["甲"]}  # 沒打中，還是盯上了
    assert battle.marked == {"姑姑": 0}  # 失手的人不顯眼


def test_a_long_shot_that_lands_pins_the_target_to_holding_next_round(gamble):
    battle = _battle(gamble, [("甲", "guan"), ("姑姑", "huang")])
    msgs = _round(battle, gamble, {"甲": ("一箭射穿姑姑", 10), "姑姑": "強攻"})
    assert any("姑姑被牽制住了，下一回合只能固守。" in m for m in msgs)
    assert bi.pinned(battle, battle.participants["姑姑"])
    assert _tags(battle, gamble, "姑姑") == ["huang_hold"]
    _round(battle, gamble, {"甲": "固守", "姑姑": "固守"})
    assert not bi.pinned(battle, battle.participants["姑姑"])
    assert "huang_strong" in _tags(battle, gamble, "姑姑")


def test_a_hit_cannot_take_more_than_the_round_cap(gamble):
    people = [(n, "guan") for n in ("甲", "乙", "丙", "丁")] + [("姑姑", "huang")]
    battle = _battle(gamble, people)
    _round(battle, gamble, {**{n: (f"{n}砍姑姑", 0 + 1) for n, _ in people[:4]}, "姑姑": "固守"})
    gk = battle.participants["姑姑"]
    assert gk.hurt_taken == pytest.approx(1000 * BattleTuning().target_round_cap)
    assert gk.targeted_by == ["甲", "乙", "丙", "丁"]


# ── 顯眼的人吃集火 ──────────────────────────────────────


def test_enemy_strikes_focus_on_the_conspicuous(gamble):
    battle = _battle(gamble, [("甲", "guan"), ("乙", "huang"), ("丙", "huang")])
    battle.marked["甲"] = 0
    msgs = _round(battle, gamble, {"甲": "奇襲", "乙": "強攻", "丙": "強攻"})
    tuning = BattleTuning()
    focus = min(2 * tuning.focus_per_attacker, 1000 * tuning.focus_cap)
    assert battle.participants["甲"].hurt_taken == pytest.approx(focus)
    assert f"黃巾的強攻盯著顯眼的人打：甲氣血 -{round(focus)}。" in msgs


def test_the_spotlight_fades_when_the_act_changes(gamble):
    battle = _battle(gamble, [("甲", "guan"), ("乙", "huang")])
    battle.marked["甲"] = 0
    battle.act_index = 1
    _round(battle, gamble, {"甲": "奇襲", "乙": "強攻"})
    assert battle.participants["甲"].hurt_taken == 0


# ── 帶頭的人有名字 ──────────────────────────────────────


def test_the_cause_line_names_who_led(gamble):
    battle = _battle(gamble, [("甲", "guan"), ("乙", "huang")])
    battle.participants["甲"].scores = {m: 80.0 for m in MOVES}
    msgs = _round(battle, gamble, {"甲": "固守", "乙": "固守"})
    assert msgs[1].endswith("甲帶頭固守。") and battle.participants["甲"].led_rounds == 1
    assert battle.participants["乙"].led_rounds == 0


def test_a_crowd_on_one_move_is_a_formation():
    assert bi.lead_clause(("張三", "強攻", 4), 3) == "張三等 4 人結成強攻陣勢"
    assert bi.lead_clause(("張三", "強攻", 2), 3) == "張三帶頭強攻"
    assert bi.lead_clause(("張三", "強攻", 4), 3, with_move=False) == "張三等 4 人結成陣勢"
    assert bi.lead_clause(("張三", "強攻", 1), 3, with_move=False) == "張三一馬當先"


def test_the_model_gets_the_target_line(monkeypatch):
    seen = {}

    class Client:
        def chat_structured(self, messages, schema, **kw):
            seen["text"] = messages[-1]["content"]
            return bi.SuccessRateJudgment(success_rate=30)

    act = BattleAct(id="a", title="對陣", text="兩軍對陣。", goal="", options=[BattleOption(text="衝", tag="x")])
    bi.assess_gamble(Client(), act, "官軍", "生擒姑姑", "甲", target="姑姑（黃巾，身手比玩家強）")
    assert "玩家點名攻擊的對手：姑姑（黃巾，身手比玩家強）\n玩家的行動：「生擒姑姑」" in seen["text"]
