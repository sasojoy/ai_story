"""減法季批 4（主機側計畫 Task 4-3 的純規則那一半；整合設計 5.2）：地方痕跡看得見——全服累計到門檻那一刻發一則地方傳聞、
記一筆江湖史、（只有「趕走散兵」那一類）推一下線，地點描寫多接一段，〈天下形勢〉多一句；只發一次。
接線（Game.location_text、sync 之後叫 fire_due、xingshi.facts、行狀）等批 0 的開關。用測試內容的 town（小鎮）與 kou（寇亂）線。"""
import pytest
from pydantic import ValidationError

from conftest import real_content
from tianxia import marks
from tianxia.content import ContentError, _scale_marks, validate
from tianxia.models import Effect, FreeTextChoice, Location, MarkRule, MarkText, Outcome
from tianxia.rules import add_marks, resolve_trends, world_trend_value
from tianxia.state import WorldState, new_game_state

KEY = "town:勸醒"
RULE = MarkRule(
    mark=KEY, describe="街角的醉漢少了，酒肆門口有人掃地。", rumor="小鎮的醉漢被人勸醒了好幾個，街上清靜多了。",
)


@pytest.fixture
def town(content):
    """「醉漢」多一種會留下 town:勸醒 的後果，內容裡有它的痕跡規則。"""
    content.events["drunk"].free_text = FreeTextChoice(prompt="自己想辦法……", stat="str", outcomes=[
        Outcome(id="talk", tag="勸說：好言相勸", check={"stat": "wis", "difficulty": 5},
                effect=Effect(text="醉漢聽了你的話，自己找了個牆角坐下。", stats={"good": 1}, marks={KEY: 1}, contribution=1),
                fail_effect=Effect(text="醉漢根本聽不進去。")),
        Outcome(id="leave", tag="走開：不管", effect=Effect(text="你繞開醉漢走了。")),
    ])
    content.mark_rules = [RULE.model_copy()]
    validate(content)
    return content


def _twenty(state, content, n=20):
    """n 個人各在 town 記一筆（同一個人一天只算一次：每一筆換一個人的帳）。"""
    for _ in range(n):
        state.player.mark_days.clear()
        add_marks({KEY: 1}, state, content)


def test_the_twentieth_mark_fires_once(town, state):
    _twenty(state, town, 19)
    assert marks.fire_due(state, town) == [] and not state.world.marks_fired
    before_rumors, before_chronicle = len(state.world.rumors), len(state.world.chronicle)
    _twenty(state, town, 1)
    state.world.time = 1234.0
    assert [r.mark for r in marks.fire_due(state, town)] == [KEY]
    assert state.world.marks_fired == {KEY: 1234.0}
    rumor = state.world.rumors[-1]
    assert (rumor.text, rumor.location, rumor.layer, rumor.named) == (RULE.rumor, "town", "local", False)  # 不列名字
    assert state.world.chronicle[-1].text == RULE.rumor  # 江湖史沒另寫就照傳聞那一句
    assert len(state.world.rumors) == before_rumors + 1 and len(state.world.chronicle) == before_chronicle + 1
    _twenty(state, town, 5)
    assert marks.fire_due(state, town) == []  # 只發一次
    assert len(state.world.rumors) == before_rumors + 1


def test_the_place_reads_differently_past_the_threshold(town, state):
    loc = town.locations["town"]
    plain = loc.describe(state.world.flags)
    assert marks.describe(loc, state.world, town) == plain  # 沒過門檻：一個字不變
    _twenty(state, town, 19)
    assert marks.describe(loc, state.world, town) == plain
    _twenty(state, town, 1)
    assert marks.describe(loc, state.world, town) == f"{plain}\n\n{RULE.describe}"


def test_the_highest_threshold_segment_wins(town, state):
    """地點自己寫的 desc_marks（同一個痕跡分幾段）跟痕跡規則的那一段比，挑門檻最高的那一段；同門檻挑人數多的。"""
    loc = town.locations["town"]
    loc.desc_marks = [MarkText(mark=KEY, min=5, text="偶爾有人扶醉漢回家。"), MarkText(mark=KEY, min=40, text="小鎮再也看不到醉倒街頭的人。")]
    plain = loc.describe(state.world.flags)
    _twenty(state, town, 5)
    assert marks.describe(loc, state.world, town) == f"{plain}\n\n偶爾有人扶醉漢回家。"
    _twenty(state, town, 15)
    assert marks.describe(loc, state.world, town) == f"{plain}\n\n{RULE.describe}"
    _twenty(state, town, 20)
    assert marks.describe(loc, state.world, town) == f"{plain}\n\n小鎮再也看不到醉倒街頭的人。"


def test_the_xingshi_gets_a_line_after_it_fires(town, state):
    assert marks.xingshi_facts(state.world, town, since=0.0) == []
    _twenty(state, town)
    state.world.time = 500.0
    marks.fire_due(state, town)
    assert marks.xingshi_facts(state.world, town, since=0.0) == [RULE.rumor]  # 沒寫 xingshi 就照傳聞那一句
    assert marks.xingshi_facts(state.world, town, since=600.0) == []  # 上一篇以後才過門檻的才寫
    town.mark_rules[0] = RULE.model_copy(update={"xingshi": "小鎮的街頭清靜了。"})
    assert marks.xingshi_facts(state.world, town, since=0.0) == ["小鎮的街頭清靜了。"]


def test_only_a_rule_with_a_trend_pushes_the_line_once(town, state):
    """企劃者 2026-10-24 第 8 件 b：只有「趕走散兵」那一類推線（MarkRule.trend），照原本的量推一次（同 source="event_once"）。"""
    before = state.world.trends["kou"]
    _twenty(state, town)
    marks.fire_due(state, town)
    assert state.world.trends["kou"] == before  # 勸醒醉漢不推線
    town.mark_rules = [RULE.model_copy(update={"mark": "town:趕寇", "trend": {"kou": -1}})]
    for _ in range(20):
        state.player.mark_days.clear()
        add_marks({"town:趕寇": 1}, state, town)
    marks.fire_due(state, town)
    assert state.world.trends["kou"] == before - 1
    marks.fire_due(state, town)
    assert state.world.trends["kou"] == before - 1


def test_the_threshold_scales_with_the_server(town):
    """跟條件的 marks_min 一樣照 Config.mark_threshold_scale 換算（無條件進位）。"""
    town.locations["town"].desc_marks = [MarkText(mark=KEY, min=5, text="偶爾有人扶醉漢回家。")]
    _scale_marks(town, 2.5)
    assert town.mark_rules[0].threshold == 50 and town.locations["town"].desc_marks[0].min == 13


def test_fired_marks_add_no_key_until_something_fires():
    """存檔一個鍵都不多：沒過門檻的季，WorldState 的 JSON 跟以前一樣。"""
    world = WorldState()
    assert "marks_fired" not in world.model_dump() and "marks_fired" not in world.model_dump_json()
    world.marks_fired["town:勸醒"] = 3.0
    assert world.model_dump()["marks_fired"] == {"town:勸醒": 3.0}
    assert WorldState.model_validate_json(world.model_dump_json()).marks_fired == {"town:勸醒": 3.0}
    loc = Location(id="a", name="甲", description="一處。", connections=[], x=0, y=0)
    assert "desc_marks" not in loc.model_dump()


def test_rule_fields():
    assert MarkRule(mark="town:勸醒", describe="甲。", rumor="乙。").threshold == 20  # 【預設】
    with pytest.raises(ValidationError):
        MarkRule(mark="town:勸醒", threshold=0, describe="甲。", rumor="乙。")


# ── 內容驗證 ───────────────────────────────────────────────


def test_an_outcome_mark_needs_a_rule(town):
    town.mark_rules = []
    with pytest.raises(ContentError, match="痕跡規則"):
        validate(town)


def test_a_rule_nobody_writes_is_refused(town):
    town.mark_rules.append(MarkRule(mark="town:沒人寫", describe="甲。", rumor="乙。"))
    with pytest.raises(ContentError, match="town:沒人寫"):
        validate(town)


@pytest.mark.parametrize("change, words", [
    ({"mark": "nowhere:勸醒"}, "nowhere"),
    ({"rumor": ""}, "rumor"),
    ({"describe": ""}, "describe"),
    ({"rumor": "小鎮有3個醉漢被勸醒了。"}, "數字"),
    ({"trend": {"nope": -1}}, "nope"),
])
def test_bad_rules_are_refused(town, change, words):
    town.mark_rules[0] = RULE.model_copy(update=change)
    with pytest.raises(ContentError, match=words):
        validate(town)


def test_a_rule_is_written_once(town):
    town.mark_rules.append(RULE.model_copy())
    with pytest.raises(ContentError, match="重複"):
        validate(town)


# 趕走散兵那一類（企劃者 2026-10-24 第 8 件 b；PM 2026-10-25 第 5 件的三條，加上接線那一批跟人拉犁一起併進來的「散兵退了」）
STRAGGLERS = {"yingchuan_wilds:拆卡", "nanyang_road:護車", "runan_wilds:奪牛", "yingchuan_wilds:散兵退了"}


@pytest.mark.slow
def test_real_content_has_one_rule_per_outcome_mark_and_only_the_stragglers_push():
    content = real_content()
    written = {key for ev in content.events.values() if ev.free_text is not None for o in ev.free_text.outcomes for key in o.effect.marks}
    rules = {r.mark: r for r in content.mark_rules}
    assert set(rules) == written and len(rules) == 96  # 29 則的 93 個，加上人拉犁的 3 個（PM 2026-10-25 第 7 件）
    assert {mark for mark, rule in rules.items() if rule.trend} == STRAGGLERS
    assert all(rules[mark].trend == {"front": -1} for mark in STRAGGLERS)  # 地方安定：戰線往官軍那邊一點
    assert {rule.threshold for rule in rules.values()} == {20}


@pytest.mark.slow
def test_a_straggler_mark_pushes_its_front_once_in_real_content():
    content = real_content()
    state = new_game_state(content, "甲")
    rule = next(r for r in content.mark_rules if r.mark == "nanyang_road:護車")
    (line,) = resolve_trends(content, state.world, rule.trend, "nanyang_road")
    before = world_trend_value(state.world, content, line)
    state.world.marks[rule.mark] = rule.threshold
    assert rule in marks.fire_due(state, content)
    assert world_trend_value(state.world, content, line) == before - 1
    assert marks.fire_due(state, content) == [] and world_trend_value(state.world, content, line) == before - 1


def test_desc_marks_stay_on_their_own_place(town):
    town.locations["lake"].desc_marks = [MarkText(mark=KEY, min=5, text="湖邊也有人說起小鎮的事。")]
    with pytest.raises(ContentError, match="lake"):
        validate(town)
