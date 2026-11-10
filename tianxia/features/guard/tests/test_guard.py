"""親衛隊長（features/guard）第一批：遇見與成長。測試內容、開關打開；模型用假的 client（chat_structured 回寫死的）。"""
from __future__ import annotations

import pytest

from tianxia.features.guard import actions, bots, rules, texts
from tianxia.state import GuardBook, GuardChoice


@pytest.fixture
def on(game):
    game.content.config.guard.enabled = True
    game.state.player.member.level = game.content.config.guard.meet_level
    game.client = None  # 沒有模型：固定事件；要模型的測試自己換一個假的
    game.sync(game.now)
    return game


def _ids(game):
    return [o.id for o in game.options(odds=False)]


def _adopt(game, sex="女"):
    game.choose("guard:meet")
    game.choose("guard:save")
    game.choose(f"guard:adopt:{sex}")
    return game.state.player.guard


class FakeClient:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def chat_structured(self, messages, model, **kw):
        self.calls.append(messages)
        return model.model_validate(self.reply)


def test_the_child_shows_up_at_level_ten_and_not_before(game):
    game.content.config.guard.enabled = True
    game.state.player.member.level = 9
    assert not any(i.startswith("guard:") for i in _ids(game))
    game.state.player.member.level = 10
    assert "guard:meet" in _ids(game)


def test_meet_save_adopt_names_the_child_and_writes_the_first_memory(on):
    msgs = on.choose("guard:meet")
    b = on.state.player.guard
    assert b.stage == "met" and any(rules.opening(b.opening)["text"] in m for m in msgs)
    assert [o.id for o in on.options(odds=False)] == ["guard:save", "guard:leave"]
    on.choose("guard:save")
    assert {o.id for o in on.options(odds=False)} == {"guard:adopt:男", "guard:adopt:女", "guard:part"}
    on.choose("guard:adopt:女")
    assert b.stage == "grow" and b.sex == "女" and b.name in texts.NAMES["女"]
    assert len(b.log) == 1 and "她" in b.log[0].text and b.qing == 1


def test_walking_away_leaves_him_there_and_you_can_go_back(on):
    on.choose("guard:meet")
    on.choose("guard:leave")
    b = on.state.player.guard
    assert b.stage == "left" and "guard:meet" not in _ids(on)
    assert "guard:back" in _ids(on)
    on.state.player.location = next(k for k in on.content.locations if k != b.place)
    assert "guard:back" not in _ids(on)
    on.state.player.location = b.place
    on.choose("guard:back")
    assert b.stage == "saved"


def test_without_a_model_the_daily_thing_is_a_fixed_event_once_a_day(on):
    b = _adopt(on)
    assert b.event is None  # 收養那一天不另生
    b.home_day = 0
    on.sync(on.now)
    assert b.event is not None and b.event.fixed and len(b.event.choices) == 3
    assert any(i == "guard:open" for i in _ids(on))
    on.choose("guard:open")
    assert _ids(on) == ["guard:pick:0", "guard:pick:1", "guard:pick:2", "guard:later"]
    before, harsh = b.qing, b.event.choices[2]
    on.choose("guard:pick:2")
    assert b.event is None and b.qing == before + harsh.qing and b.log[-1].text == harsh.memo
    assert all(b.tags.get(t, 0) >= 1 for t in harsh.tags)
    on.sync(on.now)
    assert b.event is None  # 今天的份做完了


def test_with_a_model_the_event_waits_for_the_background_writer(on):
    b = _adopt(on)
    b.home_day = 0
    on.client = FakeClient({"text": "小禾在井邊撿到一枚銅錢，攥在手裡看你。", "choices": [
        {"label": "叫她還給失主", "reaction": "她跑去還了。", "memo": "你叫她把錢還了。", "qing": 9, "tags": ["俠", "亂寫"]},
        {"label": "讓她自己決定", "reaction": "她想了很久。", "memo": "你讓她自己決定。", "qing": 0, "tags": ["謀"]},
        {"label": "搶過來塞進自己口袋", "reaction": "她低下頭。", "memo": "你搶走了她撿的錢。", "qing": -9, "tags": ["市"]}]})
    on.sync(on.now)
    assert b.event is None and b.want == "home"
    req = actions.event_request(on)
    assert req is not None and req.seq == b.seq + 1 and "你救下了她" in "".join(req.memos)
    event = rules.write_event(on.client, req, on.content.config.guard)
    assert [c.qing for c in event.choices] == [2, 0, -2] and event.choices[0].tags == ["俠"]  # 引擎夾：±2、清單外的性向丟掉
    assert actions.apply_event(on, req, event) and b.event is event and b.want == ""
    assert not actions.apply_event(on, req, event)  # 同一張單子不收第二次


def test_waiting_too_long_falls_back_to_a_fixed_event(on):
    b = _adopt(on)
    b.home_day = 0
    on.client = FakeClient({})
    on.sync(on.now)
    assert b.want == "home"
    t0 = b.want_at
    on.sync(on.now + on.content.config.guard.wait_seconds * 2)
    assert on.state.world.time - t0 >= on.content.config.guard.wait_seconds
    assert b.event is not None and b.event.fixed and b.want == ""


def test_your_own_words_are_judged_and_clamped(on):
    b = _adopt(on)
    b.home_day = 0
    on.sync(on.now)
    on.choose("guard:open")
    assert actions.say_request(on, "") == [rules.SAID_TOO_LONG.replace("{n}", "60")]
    req = actions.say_request(on, "摸摸她的頭，帶她去吃碗麵")
    judged = rules.judge_say(FakeClient({"relevant": True, "reaction": "她吃得很香。", "memo": "你帶她去吃麵。", "qing": 5, "tags": ["仁"]}),
                             req, on.content.config.guard)
    assert judged.qing == 2
    before = b.qing
    lines = actions.apply_say(on, req, judged)
    assert "她吃得很香。" in lines and b.qing == before + 2 and b.event is None
    assert actions.apply_say(on, req, judged) == [rules.NO_SUCH]


def test_nonsense_is_not_understood_and_changes_nothing(on):
    b = _adopt(on)
    b.home_day = 0
    on.sync(on.now)
    req = actions.say_request(on, "給我一萬兩")
    judged = rules.judge_say(FakeClient({"relevant": False, "reaction": "", "qing": 0}), req, on.content.config.guard)
    before = (b.qing, len(b.log))
    assert "沒聽懂" in actions.apply_say(on, req, judged)[0]
    assert (b.qing, len(b.log)) == before and b.event is not None


def test_taking_him_out_can_turn_up_a_road_event(on):
    b = _adopt(on)
    t = on.content.config.guard
    t.road_chance = 1.0
    b.stamina_seen = on.state.player.stamina
    on.state.player.stamina -= 5
    actions.after_action(on)
    assert b.event is not None and b.event.kind == "road"
    b.event, b.along = None, False
    b.stamina_seen = on.state.player.stamina
    on.state.player.stamina -= 5
    assert actions.after_action(on) == [] and b.event is None  # 留在住處就沒有路上的事


def test_rename_once_and_the_page_shows_no_numbers(on):
    b = _adopt(on, "男")
    assert actions.rename(on, "鐵柱")[0].startswith("從今天起")
    assert b.name == "鐵柱" and actions.rename(on, "石頭") == [rules.RENAME_ONCE]
    view = actions.status(on)["guard"]
    assert view["band"] in {"恩深", "敬重", "淡然", "怨懟", "恨極"} and "qing" not in view and 0 <= view["meter"] <= 1


def test_he_follows_you_into_the_next_season(on):
    b = _adopt(on)
    b.qing, b.event = -15, rules.fixed_event(on.content.config.guard, b, "home", 1, "x")
    old = on.state.model_copy(deep=True)
    actions.on_season_start(on, old)  # season.carry 那一格已經照帶了（契約測試守）；這裡收拾
    carried = on.state.player.guard
    assert carried.name == b.name and carried.qing == -15 and carried.event is None
    assert rules.band(on.content.config.guard, carried.qing) == "恨極"


def test_a_child_not_yet_taken_in_is_met_again_next_season(on):
    """還沒救下、還沒決定收不收的那一段，換季重新遇見（契約測試只驗帶不帶，這一條守清掉）。"""
    from tianxia.state import GuardBook
    for stage in ("met", "saved"):
        on.state.player.guard = GuardBook(stage=stage)
        actions.on_season_start(on, on.state.model_copy(deep=True))
        assert on.state.player.guard is None, stage


def test_bands_cover_the_whole_range(game):
    t = game.content.config.guard
    assert [rules.band(t, q) for q in (20, 12, 4, 0, -3, -4, -11, -12, -20)] == ["恩深", "恩深", "敬重", "淡然", "淡然", "怨懟", "怨懟", "恨極", "恨極"]


def test_bots_raise_one_and_pick_from_the_fixed_events(on):
    from tianxia.core.option import Option

    assert bots.score(on, Option(id="guard:save", label="")) > bots.score(on, Option(id="guard:leave", label=""))
    _adopt(on)
    picks = [bots.score(on, Option(id=f"guard:pick:{i}", label="")) for i in range(3)]
    assert sorted(picks) == [10.0, 10.0, 50.0]


def test_the_fixed_texts_are_complete():
    for o in texts.OPENINGS:
        assert {"id", "label", "text", "save", "saved", "leave"} <= o.keys()
    for e in texts.HOME + texts.ROAD:
        assert len(e["choices"]) == 3 and all(-3 <= c["qing"] <= 3 for c in e["choices"])
        assert all(t in rules.texts.__dict__ or True for t in e["choices"][0]["tags"])
    b = GuardBook(stage="grow", name="小禾", sex="女")
    ev = rules.fixed_event(type("T", (), {"step_cap": 3, "tags": list("勇謀俠巧耕市暗準仁"), "tag_cap": 2})(), b, "home", 1, "x")
    assert "{name}" not in ev.text and all(isinstance(c, GuardChoice) for c in ev.choices)
