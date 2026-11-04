"""人物心意（減法季批 6 Task 6-1；整合設計 5.4、5.9；tianxia/stances.py）：跟大勢人物說話時模型多歸一次「玩家在勸他哪一種」，
一人一天一筆、全服計數；這一週到門檻（30【預設】）照最多的那一個改做事（推線加倍、不推、每天拉下對面的進度、痕跡算雙倍），
發天下大事、記江湖史、給勸過的人一則行狀；每週一（7 天的季是每段）歸零。關著的季一個字都不變（對話的提示詞也是）。
用正式內容的 season21（盧植、波才、皇甫嵩的心意就是正式內容那幾筆）；模型一律是假的。"""
from __future__ import annotations

import json

import pytest

from conftest import real_content
from stances_kit import BOCAI, DAY, HOUR, HUANGFU, LUZHI, MON, at, real_game, stance_turn, talking, week_start_real
from tianxia import annals, companion_agent, conquest, figures, rules, stances
from tianxia.state import GameState, PlayerState, QUIET_DEFAULTS, StanceNote, StanceOn, WorldState, new_game_state


def _def(content, fid, sid):
    return next(x for x in content.figures[fid].stances if x.id == sid)


def _on(game, fid, sid):
    """他此刻照 sid 做事（同 stances.check 到門檻那一刻寫的；連這一週的記號一起寫，週初掛鉤才不當成上一週的清掉）。"""
    w = game.state.world
    w.stance_week = stances.week_of(game.content, w)
    w.stance_active = {fid: StanceOn(stance=sid, at=w.time, week=w.stance_week)}


def test_three_figures_have_three_stances_each_in_real_content():
    c = real_content("season21")
    for fid in (LUZHI, BOCAI, HUANGFU):
        rows = c.figures[fid].stances
        assert len(rows) == 3 and len({x.id for x in rows}) == 3
        assert all(x.name and x.hint and x.rumor for x in rows)
    luzhi = {x.id: x.action for x in c.figures[LUZHI].stances}
    assert luzhi["suzhan"].push == 2  # 速戰：推冀州線從 1 改 2
    assert luzhi["chizhong"].push == 0 and luzhi["chizhong"].guard > 0  # 持重：不推線、自家的塊每天守
    assert luzhi["xumin"].push == 0 and luzhi["xumin"].marks  # 恤民：不推線、救濟的痕跡算雙倍
    assert all(not f.stances for fid, f in c.figures.items() if fid not in (LUZHI, BOCAI, HUANGFU))


def test_one_record_per_person_per_day():
    g = real_game()
    s, c = g.state, g.content
    assert stances.record(s, c, LUZHI, "suzhan")
    assert not stances.record(s, c, LUZHI, "chizhong")  # 同一天換一個說法也不算
    assert s.world.stance_counts == {LUZHI: {"suzhan": 1}}
    assert stances.heard_today(s, c, LUZHI) == "suzhan"
    assert stances.record(s, c, BOCAI, "mengong")  # 別的人物各算各的
    g._save_season()
    at(g, g.now + DAY)  # 隔天（台灣 00:00 換日），同一週
    s = g.state
    assert stances.heard_today(s, c, LUZHI) is None
    assert stances.record(s, c, LUZHI, "chizhong")
    assert s.world.stance_counts[LUZHI] == {"suzhan": 1, "chizhong": 1}
    assert s.player.stance_notes[LUZHI].said == ["suzhan", "chizhong"]
    assert not stances.record(s, c, LUZHI, "nosuch") and not stances.record(s, c, "zhangjiao", "suzhan")  # 清單外、沒有心意的人物


def test_reaching_the_threshold_changes_his_course_and_tells_the_world():
    g = real_game()
    s, c = g.state, g.content
    w = s.world
    w.stance_week, w.stance_counts = stances.week_of(c, w), {LUZHI: {"suzhan": 29, "chizhong": 5}}
    rumors, chronicle = len(w.rumors), len(w.chronicle)
    assert stances.active(s, c, LUZHI) is None and stances.push_scale(s, c, LUZHI) == 1
    assert stances.record(s, c, LUZHI, "suzhan")
    suzhan = _def(c, LUZHI, "suzhan")
    assert w.stance_active[LUZHI].stance == "suzhan" and stances.active(s, c, LUZHI) == suzhan
    added = w.rumors[rumors:]
    assert [(r.text, r.layer, r.named) for r in added] == [(suzhan.rumor, "world", False)]  # 不列名字
    assert [r.text for r in w.chronicle[chronicle:]] == [suzhan.chronicle or suzhan.rumor]
    assert stances.push_scale(s, c, LUZHI) == 2 and stances.push_scale(s, c, "zhangjiao") == 1


def test_when_two_reach_it_the_most_wins_and_it_is_told_once():
    g = real_game()
    s, c = g.state, g.content
    w = s.world
    w.stance_week, w.stance_counts = stances.week_of(c, w), {LUZHI: {"suzhan": 31, "chizhong": 30}}
    assert stances.check(s, c, LUZHI).id == "suzhan"
    told = len(w.rumors)
    assert stances.check(s, c, LUZHI).id == "suzhan" and len(w.rumors) == told  # 沒換：不再發
    w.stance_counts[LUZHI]["chizhong"] = 32
    # 換手只在每天 00:00 重算（FB-826，PM 2026-10-26 推翻「一筆就換」；新規則的測試在 test_stances_fix6.py）：白天照舊、00:00 才換
    assert stances.check(s, c, LUZHI).id == "suzhan" and len(w.rumors) == told
    assert stances.check(s, c, LUZHI, midnight=True).id == "chizhong" and w.stance_active[LUZHI].stance == "chizhong"
    assert w.rumors[-1].text == _def(c, LUZHI, "chizhong").rumor and len(w.rumors) == told + 1


@pytest.mark.parametrize("profile", ["season21", "week7"])
def test_counts_and_his_course_reset_every_monday(profile):
    """每週一歸零（整合設計 5.9）；7 天的季的「週」是段（[2, 2, 3] 天，第十二章「一週換成兩天」）。"""
    g = real_game(profile)
    s, c = g.state, g.content
    w = s.world
    w.stance_week, w.stance_counts = stances.week_of(c, w), {LUZHI: {"suzhan": 29}}
    assert stances.record(s, c, LUZHI, "suzhan") and w.stance_active
    g._save_season()
    at(g, week_start_real(g, 2))
    w = g.state.world
    assert (w.stance_counts, w.stance_active, w.stance_week) == ({}, {}, 2)
    assert stances.push_scale(g.state, c, LUZHI) == 1
    assert stances.record(g.state, c, LUZHI, "suzhan") and w.stance_counts == {LUZHI: {"suzhan": 1}}  # 新的一週又可以記


def test_a_rush_doubles_his_daily_push_and_holding_stops_it():
    """速戰推冀州線加倍、持重不推（figures.tick：第一季的大勢人物每曆時推，盧植從週二 12:00 出兵）。往官軍是負的。"""
    g = real_game(open_at=MON + 2 * DAY + 10 * HOUR)
    c = g.content

    def moved(stance):
        st = g.state.model_copy(deep=True)
        if stance is not None:
            st.world.stance_active = {LUZHI: StanceOn(stance=stance, at=st.world.time, week=stances.week_of(c, st.world))}
        before = rules.trend_value(st, c, "jizhou")
        figures.tick(st, c, 24)
        return rules.trend_value(st, c, "jizhou") - before

    plain, rush, hold = moved(None), moved("suzhan"), moved("chizhong")
    assert rush < plain < hold


def test_holding_pulls_the_enemy_bars_on_his_line_every_midnight():
    """持重的「守勢 +1」：每天 00:00 把冀州線上官軍佔著的塊、黃巾的進度拉下 guard 點（領地爭奪的條；不經 conquest.push，不分紅）。"""
    g = real_game()
    at(g, g.now + HOUR)  # 開季那一天的掛鉤先跑過（週一 11:00）
    s, c = g.state, g.content
    w = s.world
    assert w.hooked_day == 1
    mine = [loc for loc in conquest.blocks(c) if conquest.line_of(w, c, loc) == "jizhou" and conquest.holder(w, c, loc) == "guan"]
    theirs = [loc for loc in conquest.blocks(c) if conquest.line_of(w, c, loc) == "jizhou" and conquest.holder(w, c, loc) == "huang"]
    assert mine and theirs
    conquest.push(w, c, mine[0], "huang", "黃巾客", 30.0, "attack")
    conquest.push(w, c, theirs[0], "guan", "官軍客", 30.0, "attack")
    guard = _def(c, LUZHI, "chizhong").action.guard
    stances.daily(s, c)
    assert conquest.bar(w, mine[0], "huang") == pytest.approx(30.0)  # 沒有心意：不動
    _on(g, LUZHI, "chizhong")
    g._save_season()
    at(g, MON + DAY + HOUR)  # 跨過週二 00:00：每天的掛鉤
    w = g.state.world
    assert conquest.bar(w, mine[0], "huang") == pytest.approx(30.0 - guard)
    assert conquest.bar(w, theirs[0], "guan") == pytest.approx(30.0)  # 對面佔著的塊不拉


def test_mercy_counts_his_relief_marks_double():
    g = real_game()
    s, c = g.state, g.content
    key, times = next(iter(_def(c, LUZHI, "xumin").action.marks.items()))
    rules.add_marks({key: 1}, s, c)
    assert s.world.marks[key] == 1
    s.player.mark_days.clear()
    _on(g, LUZHI, "xumin")
    rules.add_marks({key: 1}, s, c)
    assert s.world.marks[key] == 1 + times
    assert stances.mark_scale(s, c, "elsewhere:沒寫的") == 1


def test_the_figure_page_shows_the_bars_and_my_word_today():
    g = real_game()
    s, c = g.state, g.content
    assert stances.record(s, c, LUZHI, "chizhong")
    view = stances.view(s, c, LUZHI)
    assert [x["id"] for x in view["stances"]] == ["suzhan", "chizhong", "xumin"]
    assert view["stances"][1] == {"id": "chizhong", "name": "持重", "count": 1, "threshold": 30, "active": False}
    assert view["my_stance_today"] == "chizhong"
    assert stances.view(s, c, "zhangjiao") is None  # 沒有心意的人物


def test_a_talk_turn_records_the_stance_with_a_point_of_contribution():
    """選上一輪的選項那一輪（talk:N）：模型歸的心意記一筆、陣營貢獻 +stance_contribution（同分岔的每日上限）、紀錄一句。
    同一天第二輪不再記也不再給；none 與清單外的不記。"""
    g = real_game()
    s, c = g.state, g.content
    talking(g, LUZHI)
    contrib = s.player.contrib
    prepared = companion_agent.PreparedTurn("talk:0", LUZHI, "勸他趁黃巾未穩速攻廣宗", stance_turn(g, LUZHI, "suzhan"))
    msgs = g.choose("talk:0", prepared=prepared)
    assert g.state.world.stance_counts == {LUZHI: {"suzhan": 1}}
    assert g.world.get_season().stance_counts == {LUZHI: {"suzhan": 1}}  # 存進共用的季
    assert s.player.contrib == contrib + c.config.jianfa.stance_contribution
    assert any("速戰" in m for m in msgs)
    again = companion_agent.PreparedTurn("talk:0", LUZHI, "勸他速攻", stance_turn(g, LUZHI, "chizhong"))
    g.choose("talk:0", prepared=again)
    assert g.state.world.stance_counts == {LUZHI: {"suzhan": 1}} and s.player.contrib == contrib + 1


@pytest.mark.parametrize("said", ["none", "nosuch", None])
def test_a_turn_that_is_not_advice_records_nothing(said):
    g = real_game()
    talking(g, LUZHI)
    prepared = companion_agent.PreparedTurn("talk:0", LUZHI, "勸他趁黃巾未穩速攻廣宗", stance_turn(g, LUZHI, said))
    g.choose("talk:0", prepared=prepared)
    assert g.state.world.stance_counts == {} and LUZHI not in g.state.player.stance_notes


def test_the_opening_turn_records_nothing():
    """求見開口那一輪（通用的攀談）不是玩家說的話：不記。"""
    g = real_game()
    s, c = g.state, g.content
    companion_agent.start_dialogue(None, s, c, g.world, LUZHI, g.rng, turn=stance_turn(g, LUZHI, "suzhan"))
    assert s.world.stance_counts == {}


def test_people_who_spoke_for_it_get_an_annal_at_their_next_sync():
    g = real_game(setup=lambda c: setattr(c.config.biography, "enabled", True))
    s, c = g.state, g.content
    w = s.world
    w.stance_week, w.stance_counts = stances.week_of(c, w), {LUZHI: {"suzhan": 29}}
    assert stances.record(s, c, LUZHI, "suzhan")
    g._save_season()
    at(g, g.now + 60)
    notes = [a for a in g.state.player.annals if a.kind == annals.STANCE]
    assert len(notes) == 1 and "速戰" in notes[0].text and notes[0].figure == LUZHI and notes[0].quote == ""
    assert annals.STANCE in annals.UNHEARD  # 公開的只有他改做什麼，不列誰勸的
    at(g, g.now + 60)
    assert len([a for a in g.state.player.annals if a.kind == annals.STANCE]) == 1


def test_the_prompt_lists_his_stances_only_when_on():
    g = real_game()
    s, c = g.state, g.content
    ch = c.characters[LUZHI]
    on = companion_agent.build_system_prompt(ch, s, c, g.world, LUZHI)
    block = stances.prompt_lines(s, c, LUZHI)
    assert block and block in on and "stance" in block and all(x.hint in block for x in c.figures[LUZHI].stances)
    assert stances.ids_for(s, c, LUZHI) == ("suzhan", "chizhong", "xumin")
    c.config.jianfa.stances = False
    off = companion_agent.build_system_prompt(ch, s, c, g.world, LUZHI)
    assert off == on.replace(block, "") and stances.prompt_lines(s, c, LUZHI) == "" and stances.ids_for(s, c, LUZHI) == ()
    c.config.jianfa.stances, c.config.jianfa.enabled = True, False
    assert companion_agent.build_system_prompt(ch, s, c, g.world, LUZHI) == off


def test_generate_turn_puts_the_stance_into_the_schema_only_when_asked():
    sent: dict = {}

    class Client:
        def chat_structured(self, messages, model, **kwargs):
            sent.clear()
            sent.update(kwargs, model=model)
            extra = {"stance": "suzhan"} if "stance" in model.model_fields else {}
            return model(narrative="他點頭。", options=["好"], option_tags=["尋常寒暄"], **extra)

    turn = companion_agent.generate_turn(Client(), [], (), stances=("suzhan", "chizhong", "xumin"))
    assert turn.stance == "suzhan" and sent["schema_required"] == ["stance"]
    assert sent["model"].model_json_schema()["properties"]["stance"]["enum"] == ["suzhan", "chizhong", "xumin", "none"]
    plain = companion_agent.generate_turn(Client(), [])
    assert sent["model"] is companion_agent.CompanionTurn and "schema_required" not in sent and not hasattr(plain, "stance")


@pytest.mark.parametrize("profile", [None, "season21-off"])
def test_closed_seasons_do_nothing(profile):
    if profile == "season21-off":
        g = real_game(setup=lambda c: setattr(c.config.jianfa, "stances", False))
    else:
        g = real_game(None)
    s, c = g.state, g.content
    assert not stances.on(c, s.world)
    assert not stances.record(s, c, LUZHI, "suzhan") and s.world.stance_counts == {} and not s.player.stance_notes
    assert stances.view(s, c, LUZHI) is None and stances.ids_for(s, c, LUZHI) == ()
    _on(g, LUZHI, "suzhan")  # 就算季上留著（換了設定），關著一律照 1
    assert stances.push_scale(s, c, LUZHI) == 1 and stances.active(s, c, LUZHI) is None
    assert stances.weekly_reset(s, c, 9) == [] and s.world.stance_active  # 關著不碰季


def test_new_fields_add_no_keys_until_used(content):
    """存檔 JSON：心意、託付的欄位空的時候不多一個鍵（PlayerState 的 QUIET_DEFAULTS、WorldState 的 serializer）；寫了讀得回來；舊檔讀得進來。"""
    state = new_game_state(content, "甲客")
    data = json.loads(state.model_dump_json())
    assert not {"stance_notes", "errands"} & set(data["player"])
    assert {"stance_notes", "errands"} <= set(QUIET_DEFAULTS)
    assert not {"stance_counts", "stance_week", "stance_active"} & set(json.loads(WorldState().model_dump_json()))
    state.player.stance_notes[LUZHI] = StanceNote(week=1, day=2, said=["suzhan"])
    back = GameState.model_validate_json(state.model_dump_json())
    assert back.player.stance_notes[LUZHI].said == ["suzhan"]
    season = WorldState(stance_counts={LUZHI: {"suzhan": 3}}, stance_week=1, stance_active={LUZHI: StanceOn(stance="suzhan", at=5.0, week=1)})
    again = WorldState.model_validate_json(season.model_dump_json())
    assert (again.stance_counts, again.stance_week, again.stance_active[LUZHI].stance) == ({LUZHI: {"suzhan": 3}}, 1, "suzhan")
    old = json.loads(new_game_state(content, "乙客").model_dump_json())
    loaded = GameState.model_validate(old)
    assert loaded.player.stance_notes == {} and WorldState.model_validate({}).stance_active == {}
    assert PlayerState.model_fields["errands"].default_factory() == []
