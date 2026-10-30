"""世界活起來（Joy 2026-10-29）：人物的行程與盤算（tianxia/plans.py）、世界記事（tianxia/deeds.py）。用真實內容（Config.plans 開著、
content/itineraries.json）；每個測試拿自己的一份複本。"""
from __future__ import annotations

import pytest

from conftest import real_content
from tianxia import deeds, figure_life, figures, plans, seal_acts
from tianxia.models import Itinerary, ItineraryStop, PlanContest
from tianxia.state import GameState, PlayerState, SealAct
from tianxia.world_state import fresh_season

END = 14 * 86400.0  # 預設設定的季長（14 天）：day7 1.0～8.0 對 0～END


@pytest.fixture
def c():
    return real_content()


def _season(content, *, faction: str | None = None, location: str = "changshe") -> GameState:
    player = PlayerState(name="甲", location=location, stats={}, stamina=100, faction=faction)
    return GameState(player=player, world=fresh_season(content))


def _at(s: GameState, day: float) -> None:
    s.world.time = (day - 1) / 7 * END


def _only(content, *stops: ItineraryStop, who: str = "liubei") -> None:
    content.itineraries = [Itinerary(who=who, stops=list(stops))]


def _contest(**kw) -> PlanContest:
    base = dict(side="guan", announce="{name}打算在{place}做一件事。", win="{name}在{place}成了。", lose="{name}在{place}沒成。")
    return PlanContest(**{**base, **kw})


def test_the_real_itineraries_load_and_validate(c):
    assert c.config.plans.enabled and len(c.itineraries) >= 20  # 載入時 content.check_itineraries 驗過了
    assert all(it.who in c.characters for it in c.itineraries)


def test_a_plain_stop_moves_the_figure_and_his_followers(c):
    _only(c, ItineraryStop(id="t_raise", day=2.0, place="juma_river", text="{name}到了{place}。"))
    s = _season(c)
    _at(s, 1.9)
    plans.tick(s, c, END)
    assert "t_raise" not in s.world.stops_done
    _at(s, 2.0)
    plans.tick(s, c, END)
    assert s.world.stops_done["t_raise"] is True
    assert figure_life.where(s, c, "liubei") == "juma_river"
    assert figure_life.where(s, c, "guanyu") == "juma_river"  # 關羽跟著劉備
    assert any("劉備到了拒馬河畔" in r.text for r in s.world.rumors)
    assert s.world.deeds[-1].kind == "move" and "guanyu" in s.world.deeds[-1].figures


def test_a_contest_opens_a_lead_ahead_and_the_figure_waits_there(c):
    _only(c, ItineraryStop(id="t_fight", day=3.0, place="juma_river", contest=_contest()))
    s = _season(c)
    _at(s, 1.9)
    plans.tick(s, c, END)
    assert plans.find(s, "t_fight") is None
    _at(s, 2.0)  # 提前 lead_days7（1 天）公告
    plans.tick(s, c, END)
    plan = plans.find(s, "t_fight")
    assert plan is not None and not plan.settled
    assert figure_life.where(s, c, "liubei") == "juma_river"
    assert any("打算" in r.text for r in s.world.rumors)


def test_players_join_once_and_the_count_moves_the_odds(c):
    stop = ItineraryStop(id="t_fight", day=3.0, place="changshe", contest=_contest(base=0.5))
    _only(c, stop)
    s = _season(c, faction="guan")
    _at(s, 2.0)
    plans.tick(s, c, END)
    opts = plans.options(s, c)
    assert [o[0] for o in opts] == ["plan:help:t_fight"]  # 官軍只能助
    assert plans.problem(s, c, "block", "t_fight") == plans.WRONG_SIDE
    assert plans.problem(s, c, "help", "t_fight") is None
    plans.join(s, c, "help", "t_fight", "第 3 天 00:00")
    assert plans.problem(s, c, "help", "t_fight") == plans.ALREADY
    plan = plans.find(s, "t_fight")
    assert plans.chance(c, stop, plan) > 0.5
    plan.blockers += ["乙", "丙", "丁"]
    assert plans.chance(c, stop, plan) < 0.5
    s.player.faction = None  # 散人兩樣都行
    s.player.name = "戊"
    assert {o[0] for o in plans.options(s, c)} == {"plan:help:t_fight", "plan:block:t_fight"}


def test_away_from_the_place_you_cannot_join(c):
    _only(c, ItineraryStop(id="t_fight", day=3.0, place="juma_river", contest=_contest()))
    s = _season(c, faction="guan", location="changshe")
    _at(s, 2.0)
    plans.tick(s, c, END)
    assert plans.options(s, c) == []
    assert plans.problem(s, c, "help", "t_fight") == plans.NOT_HERE


def test_at_most_max_open_plans_at_once(c):
    c.itineraries = [
        Itinerary(who=who, stops=[ItineraryStop(id=f"t_{who}", day=3.0, place="changshe", contest=_contest())])
        for who in ("liubei", "caocao", "wangyun")
    ]
    s = _season(c)
    _at(s, 2.5)
    plans.tick(s, c, END)
    assert len(plans.open_plans(s)) == c.config.plans.max_open
    _at(s, 3.0)  # 到點：開著的結算，等不到空位的那一件不讓人插手、直接照 base 擲
    plans.tick(s, c, END)
    assert plans.open_plans(s) == []
    assert all(k in s.world.stops_done for k in ("t_liubei", "t_caocao", "t_wangyun"))


def test_settling_pushes_the_line_records_a_deed_and_pays_the_right_side(c):
    stop = ItineraryStop(id="t_fight", day=3.0, place="changshe",
                         contest=_contest(base=1.0, trends_win={"yingru": -2}, flag_win="t_flag"))
    _only(c, stop)
    c.config.plans.floor, c.config.plans.cap = 1.0, 1.0  # 一定成
    s = _season(c, faction="guan")
    _at(s, 2.0)
    plans.tick(s, c, END)
    plans.join(s, c, "help", "t_fight", "")
    _at(s, 3.0)
    plans.tick(s, c, END)
    plan = plans.find(s, "t_fight")
    assert plan.settled and plan.won and s.world.stops_done["t_fight"] is True
    assert "t_flag" in s.world.flags
    deed = s.world.deeds[-1]
    assert deed.kind == "plan" and deed.actors == ["甲"] and deed.side == "guan" and "liubei" in deed.figures
    before = s.player.affinities.get("liubei", 0)
    lines = plans.deliver(s, c)
    assert any("你出的那一份力他記著" in x for x in lines)
    assert s.player.affinities["liubei"] > before
    assert plans.deliver(s, c) == []  # 只領一次
    assert "江湖上記得的事" in deeds.prompt_lines(s, c, "liubei")  # 劉備見到你會提起


def test_a_lost_contest_retreats_and_gates_the_branches(c):
    lost = ItineraryStop(id="t_fight", day=3.0, place="juma_river", contest=_contest(base=0.0, lose_place="loushang_village"))
    then_won = ItineraryStop(id="t_won", day=4.0, place="luzhi_camp", text="{name}投盧植。", if_won=["t_fight"])
    then_lost = ItineraryStop(id="t_lost", day=4.0, place="zhuo_county", text="{name}回涿郡。", if_lost=["t_fight"])
    _only(c, lost, then_won, then_lost)
    c.config.plans.floor = c.config.plans.cap = 0.0  # 一定不成
    s = _season(c)
    _at(s, 3.0)
    plans.tick(s, c, END)
    assert s.world.stops_done["t_fight"] is False
    assert figure_life.where(s, c, "liubei") == "loushang_village"
    _at(s, 4.0)
    plans.tick(s, c, END)
    assert s.world.stops_done["t_won"] is False and s.world.stops_done["t_lost"] is True
    assert figure_life.where(s, c, "liubei") == "zhuo_county"


def _pinned(s: GameState, c, fid: str, *, place: str, origin: str, until_day: float) -> SealAct:
    """引將（玄紐）把 fid 從 origin 引到 place，預定 until_day（7 天季的第幾天）期滿。"""
    figures._ensure(s, c, fid).location = place  # noqa: SLF001
    act = SealAct(kind="yinjiang", shard="xuanniu", start=s.world.time, until=(until_day - 1) / 7 * END, target=fid, place=place, origin=origin)
    s.world.seal_acts.append(act)
    return act


def test_a_stop_ends_the_pull_of_a_figure_pinned_by_yinjiang_early(c):
    """FB-9036：行程比照時刻表（玉璽碎片改版五之一 1「時刻表優先」）——要搬一個正被引將釘著的人，引將先提前結束、回原處，再照行程搬；
    不讓行程等，也不讓引將期滿那一刻把他從行程的那一站拉回去。"""
    _only(c, ItineraryStop(id="t_raise", day=2.0, place="juma_river", text="{name}到了{place}。"), who="bocai")
    s = _season(c)
    act = _pinned(s, c, "bocai", place="changshe", origin="huangjin_camp", until_day=4.0)
    assert seal_acts.pinned(s.world, "bocai") is act
    _at(s, 2.0)
    plans.tick(s, c, END)
    assert s.world.stops_done["t_raise"] is True
    assert act.ended == pytest.approx(s.world.time) and seal_acts.pinned(s.world, "bocai") is None
    assert figures.state_of(s, c, "bocai").location == "juma_river"  # 人在行程的那一站
    _at(s, 4.0)  # 引將原本的期滿：已經提前結束了，不會再把他拉回去
    assert seal_acts.tick(s, c) == []
    assert figures.state_of(s, c, "bocai").location == "juma_river"


def test_a_stop_at_the_pinned_place_still_lets_the_pull_end_and_the_figure_stays(c):
    """行程要他待的地方就是被引到的地方：引將照樣提前結束，期滿那一刻他不會被送回原處（行程說他在那裡）。"""
    _only(c, ItineraryStop(id="t_raise", day=2.0, place="changshe", text="{name}到了{place}。"), who="bocai")
    s = _season(c)
    act = _pinned(s, c, "bocai", place="changshe", origin="huangjin_camp", until_day=4.0)
    _at(s, 2.0)
    plans.tick(s, c, END)
    assert act.ended is not None and figures.state_of(s, c, "bocai").location == "changshe"
    _at(s, 4.0)
    assert seal_acts.tick(s, c) == []
    assert figures.state_of(s, c, "bocai").location == "changshe"


def test_a_contest_announcement_and_its_result_also_end_the_pull(c):
    """盤算公告時人先走到那裡（_open）、到點結算時走到那裡或退回 lose_place（_settle）：兩處搬人都問引將。"""
    _only(c, ItineraryStop(id="t_fight", day=3.0, place="juma_river", contest=_contest(base=0.0, lose_place="loushang_village")), who="bocai")
    c.config.plans.floor = c.config.plans.cap = 0.0  # 一定不成
    s = _season(c)
    first = _pinned(s, c, "bocai", place="changshe", origin="huangjin_camp", until_day=7.0)
    _at(s, 2.0)  # 提前 lead_days7（1 天）公告
    plans.tick(s, c, END)
    assert plans.find(s, "t_fight") is not None and first.ended is not None
    assert figures.state_of(s, c, "bocai").location == "juma_river"
    second = _pinned(s, c, "bocai", place="changshe", origin="huangjin_camp", until_day=7.0)  # 公告期間又被引走
    _at(s, 3.0)
    plans.tick(s, c, END)
    assert s.world.stops_done["t_fight"] is False and second.ended is not None
    assert figures.state_of(s, c, "bocai").location == "loushang_village"


def test_a_follower_pinned_by_yinjiang_is_released_when_the_leader_walks(c):
    """跟著他走的人（部將）正被引將釘著：行程帶隊伍走時他也一樣先提前結束、再跟著搬。沒被釘著的部將照舊跟著走。"""
    _only(c, ItineraryStop(id="t_raise", day=2.0, place="juma_river", text="{name}到了{place}。"), who="bocai")
    for cid in ("zhangmancheng", "zhaohong"):
        c.characters[cid].follows, c.characters[cid].deep_interaction = "bocai", True
    s = _season(c)
    act = _pinned(s, c, "zhaohong", place="changshe", origin="nanyang_huangjin_camp", until_day=4.0)
    _at(s, 2.0)
    plans.tick(s, c, END)
    assert act.ended is not None and seal_acts.pinned(s.world, "zhaohong") is None
    assert {figures.state_of(s, c, f).location for f in ("bocai", "zhaohong", "zhangmancheng")} == {"juma_river"}
    _at(s, 4.0)
    assert seal_acts.tick(s, c) == []
    assert figures.state_of(s, c, "zhaohong").location == "juma_river"


def test_a_stop_for_a_figure_nobody_pinned_does_not_touch_other_pulls(c):
    """別人被引將釘著不受影響：行程只問「要搬的那幾位」。"""
    _only(c, ItineraryStop(id="t_raise", day=2.0, place="juma_river", text="{name}到了{place}。"), who="bocai")
    s = _season(c)
    other = _pinned(s, c, "zhangjiao", place="changshe", origin="huangjin_camp", until_day=4.0)
    _at(s, 2.0)
    plans.tick(s, c, END)
    assert other.ended is None and seal_acts.pinned(s.world, "zhangjiao") is other
    assert figures.state_of(s, c, "zhangjiao").location == "changshe"
    assert figures.state_of(s, c, "bocai").location == "juma_river"


def test_a_figure_with_an_itinerary_does_not_stroll(c):
    _only(c, ItineraryStop(id="t_raise", day=7.9, place="juma_river", text="{name}到了{place}。"))
    assert plans.holds(c, "liubei") and not plans.holds(c, "caocao")
    c.config.plans.enabled = False
    assert not plans.holds(c, "liubei")


def test_place_deeds_list_the_newest_here(c):
    s = _season(c)
    for i in range(5):
        deeds.record(s, c, "move", f"第{i}件", place="changshe")
    deeds.record(s, c, "move", "別處", place="runan")
    assert [d.text for d in deeds.at_place(s, c, "changshe")] == ["第4件", "第3件", "第2件"]


def test_the_switch_off_records_nothing(c):
    c.config.plans.enabled = False
    s = _season(c)
    assert deeds.record(s, c, "move", "x", place="changshe") is None
    plans.tick(s, c, END)
    assert s.world.deeds == [] and s.world.plans == [] and s.world.stops_done == {}
    assert "plans" not in s.world.model_dump() and "deeds" not in s.world.model_dump()  # 空的不寫進存檔


@pytest.mark.slow  # 整季跑
def test_a_season_runs_every_stop_once():
    import random

    from tianxia import world
    from tianxia.world_state import stamp_season

    content = real_content("week7")
    season = fresh_season(content)
    stamp_season(season, content, now=1792549800)  # 週三 10:30 開季
    world.settle_season_start(season, content, random.Random(0))
    w = world._season_vehicle(content, season).world
    while not w.ended:
        world.advance_world_state(w, content, 3 * 3600, random.Random(1))
    every = [st.id for it in content.itineraries for st in it.stops]
    assert set(w.stops_done) == set(every)  # 每一站都有結果（做了、沒成、或這一季不會有）
    assert len(w.plans) >= 10 and all(p.settled for p in w.plans)

