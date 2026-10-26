"""一條線（特殊事件與特殊頓悟的底座，tianxia/storyline.py；企劃者 2026-10-26 特殊事件設計稿）：
內容寫的線在開頭的地方探索擲中就開、端出第一段；段落事件的選項記記號、指往下一段或結局；routes 照記號分路；期限過了往 late；
答題、打一場（輸了等再試、輸滿往 lose）、等一件事做成；結局一定寫進傳、排一張卡；季末還沒收的寫「此事未了」。
同時開著幾條照種類（story_caps）；子開關 storylines 關著時一條都不開；沒用到時存檔一個鍵都不多。
用正式內容（season21）加上測試自己組的線，整個檔標 slow。"""
from __future__ import annotations

from unittest import mock

import pytest
from jianfa_kit import jianfa_game, plain_game, ready

from tianxia import annals, explore_one, storyline, team
from tianxia.content import ContentError, _fill_story_lines, validate
from tianxia.encounter import EncounterResult
from tianxia.models import Event, StoryDef
from tianxia.rules import day_seconds

pytestmark = pytest.mark.slow

HERE = "yingshui"  # 潁水河畔（河畔）


def _event(eid: str, choices: list[dict]) -> Event:
    return Event(id=eid, title=f"段落{eid}", text="（段落的旁白）", actions=[], choices=choices)


def _line(game, data: dict, events: list[Event]) -> StoryDef:
    """把測試的事件與線放進這一局的內容，補 line、跑一次內容檢查。"""
    c = game.content
    for ev in events:
        c.events[ev.id] = ev
    line = StoryDef(**data)
    c.storylines[line.id] = line
    _fill_story_lines(c)
    validate(c)
    return line


def _herbs(game, chance: float = 1.0) -> StoryDef:
    """兩段事件：第一段記「醫」或「符」，第二段（同一個地方、直接端出來）照記號分到兩個結局。"""
    first = _event("t_fever", [
        {"text": "診脈", "effect": {"story": {"marks": {"醫": 1}, "go": "s2"}}},
        {"text": "燒符", "effect": {"story": {"marks": {"符": 1}, "go": "s2"}}},
    ])
    second = _event("t_shrine", [{"text": "守著", "effect": {"text": "你守了一夜。"}}])
    return _line(game, {
        "id": "herbs", "title": "符水與湯藥", "intro": "南陽郊外，熱病燒了半個村子。",
        "start": {"where": {"locations": [HERE]}, "chance": chance},
        "stages": [
            {"id": "s1", "event": "t_fever", "hint": "去看病人"},
            {"id": "s2", "event": "t_shrine", "routes": [{"when": {"醫": 1}, "go": "notes"}], "next": "jar"},
        ],
        "endings": [
            {"id": "notes", "title": "仲景手札", "text": "他把手札交給你。", "annal": "{name}在南陽守著病人，得了一卷手札。"},
            {"id": "jar", "title": "一甕符水", "text": "符水一甕甕抬走。", "annal": "{name}在南陽燒了一夜的符。", "failed": True},
        ],
    }, [first, second])


def _explore(game) -> list[str]:
    with mock.patch.object(explore_one, "draw", return_value=explore_one.MATERIAL):  # 拍子照素材；擲中線時換成事件
        return game.choose("act:explore")


def test_a_line_starts_on_explore_and_runs_through_to_an_ending_in_the_biography():
    game = ready(jianfa_game(), side="guan", loc=HERE)
    _herbs(game)
    msgs = _explore(game)
    s = game.state
    assert any("奇事：符水與湯藥" in m for m in msgs)
    assert s.pending_event == "t_fever"
    assert [card.kind for card in s.player.story_cards] == ["start"]
    game.choose("choice:0")  # 診脈：記「醫」，往第二段；人還在這裡，直接端出來
    assert s.pending_event == "t_shrine"
    assert s.player.storylines["herbs"].marks == {"醫": 1}
    msgs = game.choose("choice:0")
    progress = s.player.storylines["herbs"]
    assert progress.ending == "notes" and s.pending_event is None
    assert "他把手札交給你。" in msgs
    entry = s.player.annals[-1]
    assert entry.kind == annals.STORY and entry.weight == 5 and "得了一卷手札" in entry.text
    assert [card.kind for card in game.story_cards()] == ["start", "end"]
    assert game.story_cards()[-1].ending == "仲景手札"
    game.story_seen()
    assert game.story_cards() == []
    _explore(game)  # 一季一條線只開一次
    assert s.player.storylines["herbs"].ending == "notes"


def test_routes_fall_back_to_next_when_no_mark_matches():
    game = ready(jianfa_game(), side="guan", loc=HERE)
    _herbs(game)
    _explore(game)
    game.choose("choice:1")  # 燒符
    game.choose("choice:0")
    assert game.state.player.storylines["herbs"].ending == "jar"


def test_a_stage_elsewhere_waits_for_the_button_and_its_deadline_routes_to_late():
    game = ready(jianfa_game(), side="guan", loc=HERE)
    first = _event("t_go", [{"text": "答應", "effect": {"story": {"go": "away"}}}])
    far = _event("t_far", [{"text": "到了", "effect": {"story": {"go": "done"}}}])
    _line(game, {
        "id": "errand", "title": "遠方的藥", "start": {"where": {"locations": [HERE]}, "chance": 1},
        "stages": [
            {"id": "s1", "event": "t_go"},
            {"id": "away", "event": "t_far", "where": {"locations": ["yingchuan"]}, "hint": "去潁川", "days": 1, "late": "late"},
        ],
        "endings": [
            {"id": "done", "title": "送到", "text": "送到了。", "annal": "{name}把藥送到了。"},
            {"id": "late", "title": "來不及", "text": "人已經走了。", "annal": "{name}的藥晚了一天。", "failed": True},
        ],
    }, [first, far])
    _explore(game)
    game.choose("choice:0")
    s = game.state
    assert s.pending_event is None  # 下一段不在這裡：不端出來
    assert not any(o.id.startswith("story:") for o in game.options(odds=False))
    lines = storyline.pending_lines(s, game.content)
    assert lines and lines[0]["hint"] == "去潁川" and not lines[0]["here"]
    s.player.location = "yingchuan"
    option = next(o for o in game.options(odds=False) if o.id == "story:errand")
    assert option.enabled and "遠方的藥" in option.label and "去潁川" in option.label
    s.player.location = HERE
    s.world.time += day_seconds(game.content, s.world) + 1  # 過了期限
    assert "人已經走了。" in game._story_tick()
    assert s.player.storylines["errand"].ending == "late"
    assert s.player.story_cards[-1].failed


def test_a_quiz_stage_adds_marks_per_answer_and_can_be_left_half_done():
    game = ready(jianfa_game(), side="guan", loc=HERE)
    quiz = StoryDef(**{
        "id": "dunwu_1", "title": "劍意初萌", "kind": "頓悟",
        "stages": [{"id": "q", "kind": "quiz", "hint": "問心", "questions": [
            {"text": "第一問", "answers": [{"text": "攻", "marks": {"攻": 1, "正": 1}}, {"text": "守", "marks": {"守": 1}}]},
            {"text": "第二問", "answers": [{"text": "變", "marks": {"變": 1}}, {"text": "攻", "marks": {"攻": 1, "邪": 1}}]},
        ], "routes": [{"when": {"攻": 2}, "go": "fierce"}], "next": "calm"}],
        "endings": [
            {"id": "fierce", "title": "剛", "text": "剛。", "annal": "{name}悟了剛。"},
            {"id": "calm", "title": "柔", "text": "柔。", "annal": "{name}悟了柔。"},
        ],
    })
    game.story_start(quiz)
    s = game.state
    assert s.player.storylines["dunwu_1"].custom is not None
    msgs = game.choose("story:dunwu_1")
    assert "第一問" in msgs
    assert [o.id for o in game.options(odds=False)] == ["story:dunwu_1:a0", "story:dunwu_1:a1", "story:dunwu_1:later"]
    game.choose("story:dunwu_1:a0")
    game.choose("story:dunwu_1:later")  # 先擱著：回到平常的選單，那一顆還在
    assert s.player.story_open is None and "story:dunwu_1" in [o.id for o in game.options(odds=False)]
    assert "第二問" in game.choose("story:dunwu_1")  # 從第二題接著答
    game.choose("story:dunwu_1:a1")
    progress = s.player.storylines["dunwu_1"]
    assert progress.marks == {"攻": 2, "正": 1, "邪": 1} and progress.ending == "fierce"


def test_a_fight_stage_retries_after_a_wait_and_the_hook_sees_every_bout():
    game = ready(jianfa_game(), side="guan", loc=HERE)
    seen = []
    storyline.FIGHT_HOOKS["測試"] = lambda state, content, progress, stage, record: seen.append(record.tier)
    try:
        game.story_start(StoryDef(**{
            "id": "duel_1", "title": "比劍", "kind": "測試",
            "stages": [{"id": "f", "kind": "fight", "squad": "dipi", "win": "won", "lose": "lost"}],
            "endings": [
                {"id": "won", "title": "勝", "text": "贏了。", "annal": "{name}贏了。"},
                {"id": "lost", "title": "敗", "text": "輸了。", "annal": "{name}輸了。", "failed": True},
            ],
        }))
        s = game.state
        loss = EncounterResult(tier="落敗", margin=-50, our_power=10, difficulty=40)
        with mock.patch.object(team, "fight", return_value=loss):
            game.choose("story:duel_1")
        progress = s.player.storylines["duel_1"]
        assert progress.tries == 1 and progress.ending is None
        option = next(o for o in game.options(odds=False) if o.id == "story:duel_1")
        assert not option.enabled and storyline.RETRY_NOTE in option.label
        s.world.time = progress.retry_at
        with mock.patch.object(team, "fight", return_value=loss):
            game.choose("story:duel_1")
        assert progress.ending == "lost" and s.player.annals[-1].text == f"{s.player.name}輸了。"
        assert seen == ["落敗", "落敗"]
    finally:
        del storyline.FIGHT_HOOKS["測試"]


def test_a_task_stage_moves_on_when_its_condition_holds_and_end_hooks_run():
    game = ready(jianfa_game(), side="guan", loc=HERE)
    ended = []
    storyline.END_HOOKS["測試"] = lambda state, content, world, progress, ending: ended.append(ending.id) or ["鉤子"]
    try:
        game.story_start(StoryDef(**{
            "id": "task_1", "title": "等一件事", "kind": "測試",
            "stages": [{"id": "t", "kind": "task", "until": {"flags_all": ["test_done"]}, "next": "ok"}],
            "endings": [{"id": "ok", "title": "成", "text": "成了。", "annal": "{name}等到了。"}],
        }))
        s = game.state
        assert game._story_tick() == []
        s.player.flags.add("test_done")
        assert game._story_tick() == ["成了。", "鉤子"]
        assert ended == ["ok"]
    finally:
        del storyline.END_HOOKS["測試"]


def test_a_stage_with_a_card_queues_it_after_the_opening_and_the_view_tells_the_kind():
    """段落卡（StoryStage.card，特殊頓悟心魔那一關之前那張）：進那一段時排一張 kind="stage"；第一段就有的排在開頭那張後面。
    網頁那一份（Game.story_card_view）帶這條線的類別，頓悟的卡照它換樣子。"""
    game = ready(jianfa_game(), side="guan", loc=HERE)
    game.story_start(StoryDef(**{
        "id": "dun_card", "title": "雨打殘荷", "kind": "頓悟", "intro": "雨落下來。", "image": "epiphany/enter",
        "stages": [
            {"id": "a", "kind": "task", "until": {"flags_all": ["test_done"]}, "next": "b", "card": "心魔來了。", "image": "epiphany/demon"},
            {"id": "b", "kind": "task", "task": "never", "next": "ok", "card": "又一張。"},
        ],
        "endings": [{"id": "ok", "title": "悟成", "text": "成了。", "annal": "{name}悟了。"}],
    }))
    view = game.story_card_view()
    assert [(c["kind"], c["text"], c["image"], c["sort"]) for c in view] == [
        ("start", "雨落下來。", "epiphany/enter", "頓悟"), ("stage", "心魔來了。", "epiphany/demon", "頓悟")]
    game.story_seen()
    game.state.player.flags.add("test_done")
    game._story_tick()
    assert [(c.kind, c.text, c.image) for c in game.story_cards()] == [("stage", "又一張。", None)]


def test_caps_count_lines_by_kind():
    game = ready(jianfa_game(), side="guan", loc=HERE)

    def line(n: int, kind: str) -> StoryDef:
        return StoryDef(id=f"cap{n}", title="等", kind=kind, stages=[{"id": "t", "kind": "task", "task": "never", "next": "e"}],
                        endings=[{"id": "e", "title": "e", "text": "e", "annal": "e"}])

    assert game.story_start(line(1, "頓悟")) and game.story_start(line(2, "奇事")) and game.story_start(line(3, "奇事"))
    assert game.story_start(line(4, "頓悟")) == [] and game.story_start(line(5, "奇事")) == []
    assert game.story_start(line(6, "別的")) != []  # 沒列的種類不限


def test_unfinished_lines_are_written_into_the_biography_at_season_end():
    game = ready(jianfa_game(), side="guan", loc=HERE)
    _herbs(game)
    _explore(game)
    s = game.state
    s.pending_event = None
    storyline.close_season(s, game.content)
    assert s.player.storylines["herbs"].ending == storyline.UNFINISHED
    assert s.player.annals[-1].kind == annals.STORY and s.player.annals[-1].weight == 3


def test_switched_off_no_line_starts_and_saves_stay_the_same():
    game = ready(jianfa_game(storylines=False), side="guan", loc=HERE)
    _herbs(game)
    _explore(game)
    assert game.state.player.storylines == {}
    assert game.story_start(game.content.storylines["herbs"]) == []
    dumped = game.state.player.model_dump()
    assert not {"storylines", "story_open", "story_cards"} & set(dumped)
    plain = ready(plain_game(), side="guan", loc=HERE)
    _herbs(plain)
    _explore(plain)
    assert plain.state.player.storylines == {}


def test_content_checks_catch_bad_targets_and_stray_story_steps():
    game = jianfa_game()
    c = game.content
    c.events["t_bad"] = _event("t_bad", [{"text": "走", "effect": {"story": {"go": "nowhere"}}}])
    c.storylines["bad"] = StoryDef(id="bad", title="壞", stages=[{"id": "s", "event": "t_bad"}],
                                  endings=[{"id": "e", "title": "e", "text": "e", "annal": "e"}])
    c.events["t_stray"] = Event(id="t_stray", title="野", text="野", choices=[{"text": "x", "effect": {"story": {"line": "bad"}}}])
    _fill_story_lines(c)
    with pytest.raises(ContentError) as err:
        validate(c)
    text = str(err.value)
    assert "指不到" in text and "t_stray" in text


def _win():
    return mock.patch.object(team, "fight", return_value=EncounterResult(tier="大勝", margin=50, our_power=200, difficulty=40))


def _fuzhi(game):
    """《符水與湯藥》：南陽郊野探索、擲中（chance 照 1）就開。"""
    game.content.storylines["fuzhi"].start.chance = 1.0
    _explore(game)
    assert game.state.pending_event == "fuzhi_act1"


def test_fuzhi_buy_medicine_and_guard_the_shrine_ends_in_the_notes():
    game = ready(jianfa_game(), side="guan", loc="nanyang_wilds")
    s = game.state
    _fuzhi(game)
    s.player.stats["con"] = 15
    with mock.patch("random.Random.random", return_value=0.0):
        game.choose("choice:0")  # 留下來幫張機（根骨 5）
    progress = s.player.storylines["fuzhi"]
    assert progress.stage == "act2a" and progress.marks == {"醫": 1} and progress.due is not None
    s.player.location = "lulin_zhai"  # 山林
    s.player.stats["silver"] = 100
    game.choose("story:fuzhi")
    assert s.pending_event == "fuzhi_act2a"
    game.choose("choice:0")  # 買
    assert progress.stage == "act3" and s.player.stats["silver"] == 60
    s.player.location = "yu_river"
    game.choose("story:fuzhi")
    assert "choice:2" not in [o.id for o in game.options(odds=False)]  # 沒帶符水：沒有「倒進井裡」
    with _win():
        game.choose("choice:0")  # 擋在祠堂門口
    assert progress.ending == "notes" and "zhongjing_owes" in s.player.flags
    assert s.player.annals[-1].text == f"{s.player.name}嘗入涅陽疫村，負藥助張機，活一童子。"


def test_fuzhi_carrying_the_jar_ends_in_the_jar_and_missing_the_deadline_is_too_late():
    game = ready(jianfa_game(), side="guan", loc="yu_river")
    s = game.state
    _fuzhi(game)
    game.choose("choice:1")  # 求符水 → 潁川
    s.player.location = "yingchuan"
    game.choose("story:fuzhi")
    game.choose("choice:0")  # 接下甕
    s.player.location = "wan_city"
    game.choose("story:fuzhi")
    assert "choice:2" in [o.id for o in game.options(odds=False)]  # 帶著符水：可以倒進井裡
    with mock.patch("random.Random.random", return_value=0.0):
        game.choose("choice:1")  # 從後門走
    assert s.player.storylines["fuzhi"].ending == "jar"
    late = ready(jianfa_game(name="陸小鳳"), side="guan", loc="yu_river")
    _fuzhi(late)
    late.choose("choice:1")
    late.state.world.time += 3 * day_seconds(late.content, late.state.world)
    late._story_tick()
    assert late.state.player.storylines["fuzhi"].ending == "late"
