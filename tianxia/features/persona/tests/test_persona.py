"""人物性子（功能包 persona；設計稿「人物性子會變」，Joy 2026-11-06「可以」、換季「全部歸回本性」）：
跟人物說話時模型多歸一次「這句在把他往哪一頭推」，一人一天一筆、份量照情誼；每天 00:00 以後第一個同步的人替全服結算，
換段發傳聞、記江湖史、給勸過的人一則行狀；簡介寫如今與變化紀錄；換季全部歸回本性。用正式內容的 season21（盧植），模型一律是假的。"""
from __future__ import annotations

import pytest
from stances_kit import DAY, LUZHI, at, real_game, talking

from tianxia import annals, companion_agent
from tianxia.features.persona import rules as persona
from tianxia.state import PersonaNote

UPRIGHT, RITES = "upright", "rites"  # 盧植的兩條：剛直↔圓融（起點第 0 段）、守禮↔變通（起點第 1 段）


def _on(c):
    c.config.persona_shift.enabled = True


def game(**kw):
    return real_game(setup=_on, **kw)


def _axis(c, axis_id):
    return next(a for a in c.personas[LUZHI] if a.id == axis_id)


def push(g, end, affinity=90, times=1):
    """替 times 個人各記一筆（同一個角色換一張新的紀錄，當成不同的人）。"""
    s, c = g.state, g.content
    got = 0
    for _ in range(times):
        s.player.persona_notes.pop(LUZHI, None)
        got += persona.record(s, c, LUZHI, end, affinity)
    return got


def next_day(g):
    g._save_season()
    at(g, g.now + DAY)


def test_the_package_rules_are_the_shared_layer_objects():
    """合回第 4 段：純規則的本體在共用層（人物情誼包的 companion_agent 要叫，包不准 import 包）；包的 rules 是同一批物件，沒有第二份。"""
    from tianxia import persona_rules

    names = [n for n, v in vars(persona_rules).items()
             if getattr(v, "__module__", None) == persona_rules.__name__ or (n.isupper() and isinstance(v, (str, int)))]
    assert {"NONE", "ends_for", "prompt_lines", "hear", "covers", "settle", "view", "_one_day", "_shift"} <= set(names)
    assert [n for n in names if getattr(persona, n, None) is not getattr(persona_rules, n)] == []
    assert companion_agent.persona is persona_rules


def test_real_content_has_twelve_people_with_two_axes_each():
    c = real_game().content
    assert real_game(profile="week7").content.config.persona_shift.enabled and c.config.persona_shift.enabled  # Joy 11/6「打開」
    assert len(c.personas) == 12 and all(len(rows) == 2 for rows in c.personas.values())
    assert {"zhangfei", "caocao", "liubei", "guanyu", "luzhi", "bocai"} <= set(c.personas)


def test_closed_changes_nothing():
    """開關關著：沒有叫法、提示詞一個字不多、舊的性情漂移照讀、記不了、簡介沒有如今。"""
    g = real_game(setup=lambda c: setattr(c.config.persona_shift, "enabled", False))
    s, c = g.state, g.content
    assert persona.ends_for(c, LUZHI) == () and persona.prompt_lines(s, c, LUZHI) == "" and not persona.covers(c, LUZHI)
    assert persona.record(s, c, LUZHI, "圓融", 90) == 0 and persona.view(s, c, LUZHI) is None
    g.world.record_drift_synthesis(LUZHI, "近來話少了些")
    assert "近來話少了些" in companion_agent.build_system_prompt(c.characters[LUZHI], s, c, g.world, LUZHI)
    assert "persona" not in s.world.model_dump() and "persona_notes" not in s.player.model_dump()


def test_weight_follows_affinity_and_one_record_a_day():
    g = game()
    s, c = g.state, g.content
    assert persona.record(s, c, LUZHI, "圓融", 29) == 0  # 不熟：聽不進去，也不佔今天那一筆
    assert not persona.heard_today(s, c, LUZHI)
    assert persona.record(s, c, LUZHI, "圓融", 30) == 1
    assert persona.record(s, c, LUZHI, "變通", 90) == 0  # 同一天換一個說法也不算
    assert [persona.weight(c, a) for a in (59, 60, 79, 80, 100)] == [1, 2, 2, 3, 3]
    assert persona.record(s, c, LUZHI, "none", 90) == 0 and persona.record(s, c, "nobody", "圓融", 90) == 0
    assert s.world.persona_push == {LUZHI: {UPRIGHT: 1}}
    assert s.player.persona_notes[LUZHI].said == {"圓融": 1}


def test_a_day_of_pushes_moves_him_at_most_the_daily_cap():
    g = game()
    s, c = g.state, g.content
    start = persona.value(s.world, LUZHI, _axis(c, UPRIGHT))
    assert push(g, "圓融", times=5) == 15  # 五個交情深的人各 3 份
    next_day(g)
    assert persona.value(g.state.world, LUZHI, _axis(c, UPRIGHT)) == start + c.config.persona_shift.daily_cap
    assert g.state.world.persona_push == {}  # 結算完清掉


def test_too_little_net_does_not_move_and_a_tug_of_war_is_torn():
    g = game()
    c = g.content
    push(g, "圓融", affinity=40)  # 1 份
    push(g, "變通", affinity=40, times=2)  # 另一條 2 份：都不到 3 份
    next_day(g)
    w = g.state.world
    assert persona.value(w, LUZHI, _axis(c, UPRIGHT)) == persona.center(0) and persona.value(w, LUZHI, _axis(c, RITES)) == persona.center(1)
    push(g, "圓融", times=2)
    push(g, "剛直", times=2)  # 兩邊各 6 份：淨值 0
    next_day(g)
    assert g.state.world.persona_torn == {LUZHI: [UPRIGHT]}
    assert persona.view(g.state, c, LUZHI)["torn"] == persona.TORN


def test_he_changes_a_stage_and_the_world_hears_of_it():
    g = game()
    s, c = g.state, g.content
    axis = _axis(c, UPRIGHT)
    s.world.persona = {LUZHI: {UPRIGHT: -61}}  # 差一點就到第 1 段
    rumors, chronicle = len(s.world.rumors), len(s.world.chronicle)
    push(g, "圓融", times=2)
    next_day(g)
    w = g.state.world
    assert persona.stage(w, LUZHI, axis) == 1
    [entry] = w.persona_log
    assert (entry.who, entry.axis, entry.stage, entry.toward) == (LUZHI, UPRIGHT, 1, "圓融")
    short = axis.stages[1].short
    assert [(r.text, r.named) for r in w.rumors[rumors:] if "盧植" in r.text] == [(persona.RUMOR.format(name="盧植", short=short), False)]
    assert [r.text for r in w.chronicle[chronicle:] if "性子" in r.text] == [persona.CHRONICLE.format(name="盧植", short=short)]
    assert g.world.get_season().persona_log == w.persona_log  # 存進共用的季
    view = persona.view(g.state, c, LUZHI)
    assert view["now"] == axis.stages[1].text and len(view["history"]) == 1 and view["history"][0].endswith(short)
    assert axis.stages[1].text in persona.prompt_lines(g.state, c, LUZHI)


def test_nobody_pushing_drifts_back_home_and_reach_caps_him():
    g = game()
    s, c = g.state, g.content
    axis = _axis(c, UPRIGHT)
    home = persona.center(axis.start)
    s.world.persona = {LUZHI: {UPRIGHT: home + 3}}
    next_day(g)
    assert persona.value(g.state.world, LUZHI, axis) == home + 1
    next_day(g)
    assert persona.value(g.state.world, LUZHI, axis) == home and LUZHI not in g.state.world.persona
    lo, hi = persona.bounds(c, axis)
    assert persona.stage_of(hi) == axis.start + c.config.persona_shift.reach and lo == -100  # 最多離起點兩段
    g.state.world.persona = {LUZHI: {UPRIGHT: hi - 1}}
    push(g, "圓融", times=5)
    next_day(g)
    assert persona.value(g.state.world, LUZHI, axis) == hi


def test_people_who_pushed_that_way_get_an_annal():
    g = real_game(setup=lambda c: (_on(c), setattr(c.config.biography, "enabled", True)))
    s, c = g.state, g.content
    s.world.persona = {LUZHI: {UPRIGHT: -61}}
    s.player.affinities[LUZHI] = 90
    assert persona.record(s, c, LUZHI, "圓融", 90) == 3
    next_day(g)
    notes = [a for a in g.state.player.annals if a.kind == annals.STANCE and a.figure == LUZHI]
    assert len(notes) == 1 and "圓融" in notes[0].text
    at(g, g.now + 60)
    assert len([a for a in g.state.player.annals if a.kind == annals.STANCE and a.figure == LUZHI]) == 1
    # 推另一頭的人、之後才推的人都沒有
    s2 = g.state
    s2.player.persona_notes[LUZHI] = PersonaNote(said={"剛直": 1}, first={"剛直": 0.0})
    assert persona.annals_due(s2, c) == []
    s2.player.persona_notes[LUZHI] = PersonaNote(said={"圓融": 1}, first={"圓融": s2.world.persona_log[0].at + 1})
    assert persona.annals_due(s2, c) == []


def test_a_talk_turn_counts_and_the_prompt_asks_for_it():
    g = game()
    s, c = g.state, g.content
    talking(g, LUZHI)
    s.player.affinities[LUZHI] = 70
    ends = persona.ends_for(c, LUZHI)
    assert ends == ("剛直", "圓融", "守禮", "變通")
    model = companion_agent.turn_model(("suzhan", "chizhong", "xumin"), ends)
    schema = model.model_json_schema()
    assert schema["properties"]["persona"]["enum"] == [*ends, persona.NONE] and "stance" in schema["properties"]
    turn = model(narrative="盧植沉吟良久。", options=["再勸一句", "告辭"], option_tags=["真誠請教", "尋常寒暄"], persona="圓融")
    prepared = companion_agent.PreparedTurn("talk:0", LUZHI, "勸他趁黃巾未穩速攻廣宗", turn)
    msgs = g.choose("talk:0", prepared=prepared)
    assert persona.HEARD.format(name="盧植") in msgs
    assert g.world.get_season().persona_push == {LUZHI: {UPRIGHT: 2}}
    prompt = companion_agent.build_system_prompt(c.characters[LUZHI], g.state, c, g.world, LUZHI)
    assert persona.prompt_lines(g.state, c, LUZHI) in prompt and "persona 欄位" in prompt


def test_the_old_drift_is_not_read_for_people_it_covers():
    g = game()
    s, c = g.state, g.content
    g.world.record_drift_synthesis(LUZHI, "近來話少了些")
    assert "近來話少了些" not in companion_agent.build_system_prompt(c.characters[LUZHI], s, c, g.world, LUZHI)


def test_the_request_carries_the_ends_to_the_model():
    g = game()
    s, c = g.state, g.content
    talking(g, LUZHI)
    req = companion_agent.build_request(s, c, g.world, LUZHI, "talk:0", "勸他")
    assert req.persona == persona.ends_for(c, LUZHI)


def test_the_intro_shows_now_history_and_your_count():
    import server

    g = game()
    s, c = g.state, g.content
    assert server.figure_intro(LUZHI, g)["now"] is None
    s.world.persona = {LUZHI: {UPRIGHT: -61}}
    persona.record(s, c, LUZHI, "圓融", 90)
    push(g, "圓融")
    next_day(g)
    intro = server.figure_intro(LUZHI, g)
    assert intro["nature"] and intro["now"] == _axis(c, UPRIGHT).stages[1].text
    assert len(intro["history"]) == 2 and intro["history"][-1] == persona.MINE.format(n=1)


def test_a_new_season_returns_everyone_to_who_they_were():
    """換季：季整個重來（Joy 11/6「全部歸回本性」），角色上推過的紀錄也不帶走。"""
    from tianxia.core.registry import FEATURES

    feature = next(f for f in FEATURES if f.name == "persona")
    assert feature.carried == () and feature.player_fields == ("persona_notes",)
    from tianxia.state import WorldState

    assert WorldState().persona == {} and WorldState().persona_log == []


@pytest.mark.parametrize("cid", ["zhangfei", "caocao", "bocai"])
def test_every_axis_starts_inside_its_bounds(cid):
    c = real_game().content
    _on(c)
    for axis in c.personas[cid]:
        lo, hi = persona.bounds(c, axis)
        assert lo <= persona.center(axis.start) <= hi and persona.stage_of(persona.center(axis.start)) == axis.start


def test_every_character_you_can_talk_to_has_an_intro():
    """Joy 11/6「人物簡介都要補上」：人物表上每一位對話人物（招來的一般同伴不算）都有身分、是誰、本性。"""
    import server

    c = real_game().content
    people = [cid for cid, ch in c.characters.items() if ch.deep_interaction and not getattr(ch, "hire_type", None)]
    assert people and [cid for cid in people if not (server.FIGURE_INTROS.get(cid) or {}).get("nature")] == []
