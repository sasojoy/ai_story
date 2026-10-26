"""減法季批 4（主機側計畫 Task 4-1；整合設計 5.1、5.9）：隨口應對分岔的模型、best_of 檢定、內容驗證（content.validate 的 check_outcomes）。

用測試內容的「醉漢」（town；固定選項：逼問 臂力 5 善名 +2、摸走鐵牌 惡名 +1〔作惡〕、入夥）與「挑戰」（lake；應戰打 boss、沒有作惡選項）。
"""
import pytest
from pydantic import ValidationError

from tianxia.content import ContentError, validate
from tianxia.models import BEST_OF, Check, Effect, FreeTextChoice, MarkRule, Outcome
from tianxia.rules import check_chance, check_outlook

TALK = {
    "id": "talk", "tag": "勸說：好言相勸、講道理", "check": {"stat": "best_of", "stats": ["str", "wis"], "difficulty": 5},
    "effect": {"text": "醉漢聽了你的話，晃了晃腦袋，自己找了個牆角坐下。", "stats": {"good": 1}, "marks": {"town:勸醒": 1},
               "contribution": 2},
    "fail_effect": {"text": "醉漢根本聽不進去，一口酒氣噴在你臉上。", "stamina": -5},
}
PAY = {
    "id": "pay", "tag": "破財：塞幾個錢打發他", "cost": {"silver": 5},
    "effect": {"text": "你塞了幾個錢給他，醉漢嘟囔著去買下一壺酒了。", "stats": {"good": 1}, "marks": {"town:打發": 1},
               "contribution": 1},
}
SHOVE = {
    "id": "shove", "tag": "推開：一把推開、讓他滾", "check": {"stat": "str", "difficulty": 5},
    "effect": {"text": "你一把推開醉漢，他踉蹌幾步跌坐在路邊，周圍的人都笑了。", "stats": {"good": 1}, "marks": {"town:推醉漢": 1},
               "contribution": 1},
    "fail_effect": {"text": "醉漢反手一扯，你們一起滾在泥地裡。", "stamina": -5},
}
ROB = {
    "id": "rob", "tag": "趁醉：摸走他身上的東西", "check": {"stat": "agi", "difficulty": 5},
    "effect": {"text": "你趁他站不穩，伸手把他腰間的東西摸了個乾淨，他還在對著牆說醉話。", "stats": {"good": -1},
               "marks": {"town:摸醉漢": 1}},
    "fail_effect": {"text": "醉漢一把攥住你的手腕大喊有賊，路人都朝你看過來。", "stats": {"fame": -1}},
}
LEAVE = {"id": "leave", "tag": "走開：不管、看著、對不上的", "effect": {"text": "你繞開醉漢走了。"}}


def _outcomes(content, *outcomes, event="drunk"):
    """這則事件換上這幾種後果；後果寫的痕跡各配一條痕跡規則（Task 4-3：分岔寫的痕跡要有規則讀它）。"""
    ev = content.events[event]
    ev.free_text = FreeTextChoice(prompt="自己想辦法……", stat="str", outcomes=[Outcome(**o) for o in outcomes])
    keys = dict.fromkeys(key for o in ev.free_text.outcomes for key in o.effect.marks)
    content.mark_rules = [MarkRule(mark=key, describe="這一帶起了些變化。", rumor="這一帶的人說起了那件事。") for key in keys]
    return content


def _merged(base: dict, **changes) -> dict:
    out = {**base}
    for key, value in changes.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = {**out[key], **value}
        else:
            out[key] = value
    return out


def _bad(content, *outcomes, event="drunk") -> str:
    with pytest.raises(ContentError) as caught:
        validate(_outcomes(content, *outcomes, event=event))
    return str(caught.value)


# ── 模型 ───────────────────────────────────────────────────


def test_a_best_of_check_names_two_or_more_stats():
    check = Check(stat=BEST_OF, stats=["str", "wis"], difficulty=4)
    assert check.stats == ["str", "wis"]
    with pytest.raises(ValidationError):
        Check(stat=BEST_OF, difficulty=4)  # 沒寫取哪幾項
    with pytest.raises(ValidationError):
        Check(stat=BEST_OF, stats=["str"], difficulty=4)  # 一項就不必 best_of
    with pytest.raises(ValidationError):
        Check(stat="str", stats=["wis"], difficulty=4)  # stats 只跟 best_of 一起寫


def test_contribution_is_zero_to_six():
    assert Effect().contribution == 0
    assert Effect(contribution=6).contribution == 6
    for bad in (-1, 7):
        with pytest.raises(ValidationError):
            Effect(contribution=bad)


def test_an_outcome_is_judged_one_way_at_most():
    assert Outcome(**TALK).kind == "check"
    assert Outcome(**PAY).kind == "cost"
    assert Outcome(id="fight", tag="動手：打", combat="boss").kind == "combat"
    assert Outcome(**LEAVE).kind == "fallback"
    with pytest.raises(ValidationError):
        Outcome(id="x", tag="兩樣：又檢定又打", check={"stat": "str", "difficulty": 5}, combat="boss")
    assert Outcome(**ROB).evil and not Outcome(**TALK).evil


def test_new_fields_left_at_their_defaults_add_no_keys():
    """沒有分岔的事件、沒有貢獻的效果、一般的檢定：序列化一個鍵都不多（計畫 Global Constraints）。"""
    assert "contribution" not in Effect(text="x").model_dump()
    assert "stats" not in Check(stat="str", difficulty=5).model_dump()
    assert "outcomes" not in FreeTextChoice(prompt="x", stat="str").model_dump()
    assert Effect(contribution=2).model_dump()["contribution"] == 2
    assert Check(stat=BEST_OF, stats=["str", "wis"], difficulty=5).model_dump()["stats"] == ["str", "wis"]
    assert [o["id"] for o in FreeTextChoice(prompt="x", stat="str", outcomes=[Outcome(**LEAVE)]).model_dump()["outcomes"]] == ["leave"]


# ── best_of 檢定 ───────────────────────────────────────────


def test_best_of_takes_the_highest_of_its_stats(state, content, world):
    best = Check(stat=BEST_OF, stats=["str", "wis"], difficulty=5)
    state.player.stats.update(str=8, wis=3)
    assert check_outlook(best, state, content, world).stat_value == pytest.approx(8)
    state.player.stats.update(str=3, wis=9)
    assert check_outlook(best, state, content, world).stat_value == pytest.approx(9)
    assert check_chance(best, state, content, world) == check_chance(Check(stat="wis", difficulty=5), state, content, world)


# ── 內容驗證 ───────────────────────────────────────────────


def test_good_outcomes_pass(content):
    validate(_outcomes(content, TALK, PAY, SHOVE, LEAVE))
    validate(_outcomes(content, TALK, LEAVE))


def test_the_evil_one_is_counted_apart_from_the_two_to_four(content):
    """企劃者第 8 件 a：原事件有作惡的固定選項才准有一種作惡後果；它不算在 2～4 種裡。"""
    validate(_outcomes(content, TALK, PAY, SHOVE, ROB, LEAVE))
    assert "2～4" in _bad(content, TALK, PAY, SHOVE, _merged(TALK, id="talk2", effect={"marks": {"town:再勸": 1}}), LEAVE)
    assert "作惡" in _bad(content, TALK, ROB, _merged(ROB, id="rob2", effect={"marks": {"town:再摸": 1}}), LEAVE)


@pytest.mark.parametrize("outcomes, words", [
    ((TALK,), "2～4"),
    ((TALK, _merged(LEAVE, effect={"stats": {"good": 1}})), "fallback"),
    ((TALK, _merged(LEAVE, check={"stat": "str", "difficulty": 5})), "fallback"),
    ((_merged(TALK, id="leave"), LEAVE), "重複"),
    ((_merged(TALK, tag="勸說"), LEAVE), "類名"),
    ((_merged(TALK, check={"difficulty": 6}), LEAVE), "難度"),  # 醉漢的固定選項只有逼問（難度 5）
    ((_merged(TALK, combat="boss", check=None), LEAVE), "隊伍"),  # 醉漢這一則沒有打 boss 的固定選項
    ((_merged(PAY, cost={"fame": 1}), LEAVE), "cost"),
    ((_merged(TALK, effect={"stats": {"lore": 1}}), LEAVE), "lore"),
    ((_merged(TALK, effect={"stats": {"evil": 1}}), LEAVE), "evil"),
    ((_merged(TALK, effect={"stats": {"good": 3}}), LEAVE), "good +3"),  # 逼問最多給善名 +2
    ((_merged(TALK, effect={"stats": {"silver": -5}}), LEAVE), "silver"),  # 扣的是 cost 的事，效果只給
    ((_merged(TALK, effect={"marks": {}}), LEAVE), "痕跡"),
    ((_merged(TALK, effect={"marks": {"lake:勸醒": 1}}), LEAVE), "lake"),  # 痕跡要留在這則事件的地點
    ((_merged(TALK, effect={"contribution": 0}), LEAVE), "貢獻"),
    ((_merged(TALK, effect={"rumor": "有人勸醒了醉漢。"}), LEAVE), "rumor"),  # 公開的只有後果與痕跡：不寫傳聞（會帶名號）
    ((_merged(TALK, effect={"trend": {"kou": -1}}), LEAVE), "trend"),
    ((_merged(TALK, effect={"text": "你勸了3句，醉漢晃了晃腦袋，自己找了個牆角坐下。"}), LEAVE), "數字"),
    ((_merged(TALK, fail_effect={"text": ""}), LEAVE), "fail_effect"),
    ((_merged(PAY, fail_effect={"text": "錢掉了。"}), LEAVE), "fail_effect"),  # 掏錢必成（第 8 件 c），沒有失手
    ((_merged(ROB, effect={"stats": {"good": -1, "silver": 5}}), LEAVE), "作惡"),  # 摸走鐵牌沒給銀兩：作惡不准比它多
    ((_merged(ROB, effect={"contribution": 1}), LEAVE), "貢獻"),
])
def test_bad_outcomes_are_refused(content, outcomes, words):
    assert words in _bad(content, *outcomes)


def test_an_evil_outcome_needs_an_evil_fixed_choice(content):
    """挑戰（翻江龍）沒有作惡的固定選項：不能有作惡的後果。"""
    fight = {"id": "fight", "tag": "動手：迎戰翻江龍", "combat": "boss",
             "effect": {"text": "你跟翻江龍過了幾招，把他逼退到江邊，看熱鬧的人都替你喝采。", "marks": {"lake:退江龍": 1},
                        "contribution": 2},
             "fail_effect": {"text": "翻江龍一掌把你打進水裡，你嗆了好幾口水才爬上岸。"}}
    bad = _merged(ROB, effect={"marks": {"lake:趁亂": 1}})
    validate(_outcomes(content, fight, LEAVE, event="duel"))
    assert "作惡" in _bad(content, fight, bad, LEAVE, event="duel")


def test_contribution_is_only_for_outcomes(content):
    """貢獻只有分岔的後果讀（接線之前寫在固定選項上會靜靜沒作用）。"""
    content.events["drunk"].choices[0].effect.contribution = 2
    with pytest.raises(ContentError, match="contribution"):
        validate(content)


def test_best_of_is_only_for_outcomes(content):
    content.events["drunk"].choices[0].check = Check(stat=BEST_OF, stats=["str", "wis"], difficulty=5)
    with pytest.raises(ContentError, match="best_of"):
        validate(content)
