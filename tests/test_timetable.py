"""時刻表（計畫 T2、時刻表結算文件）：大事什麼時候發生、怎麼結算、公告怎麼寫。

用 tests/fixtures/content 加上幾條測試用的戰線與一份縮小的時刻表（照結算文件的寫法），不靠真實內容。"""
import random
from pathlib import Path

import pytest

from conftest import CHANGSHE_LOCKED, CHANGSHE_LOSER, LUZHI_LOCKED, LUZHI_LOSER, FixedRandom, install_season_one
from tianxia import calendar, figures, timetable
from tianxia.content import ContentError, load_content, validate
from tianxia.models import FigureChange, TimetableEvent, TimetableOutcome
from tianxia.state import FigureState, GameState, Lock, PlayerState
from tianxia.world import advance_world_state
from tianxia.world_state import fresh_season

DAY = 86400


def _player() -> PlayerState:
    return PlayerState(name="", location="town", stats={}, stamina=0)


@pytest.fixture
def s1(content):
    """開著第一季開關、季長 2.5 天、有三條戰線與割據的測試內容（見 conftest.install_season_one）。"""
    return install_season_one(content)


@pytest.fixture
def season(s1) -> GameState:
    return GameState(player=_player(), world=fresh_season(s1))


def event(content, event_id: str) -> TimetableEvent:
    return next(e for e in content.timetable if e.id == event_id)


def advance_to_week(state: GameState, content, week: int) -> list[str]:
    """把季推進到第 week 週週一的第一個曆時（那一週週一凌晨的大事都已經結算）。"""
    target = calendar.week_start(week, content, state.world) + calendar.cal_hour_seconds(content, state.world)
    return advance_world_state(state.world, content, target - state.world.time, random.Random(0))


# ── 什麼時候發生 ─────────────────────────────────────────


def test_fixed_event_happens_on_its_week(s1):
    state = GameState(player=_player(), world=fresh_season(s1))
    msgs = advance_world_state(state.world, s1, calendar.cal_hour_seconds(s1), random.Random(0))
    assert list(state.world.timeline) == ["uprising"]
    assert msgs == ["【江湖大事】三十六方同日起事。"]
    assert [r.text for r in state.world.chronicle] == ["張角率三十六方同時起義。"]
    assert [(r.layer, r.text) for r in state.world.rumors] == [("world", "三十六方同日起事。")]


def test_default_schedule_puts_showdowns_on_thursday_evening_and_the_finale_at_the_end(s1):
    sched = timetable.default_schedule(s1)
    assert set(sched) == {"changshe_fire", "wancheng", "finale"}
    thursday = calendar.point(sched["changshe_fire"], s1)
    assert (thursday.week, thursday.weekday, thursday.hour, thursday.minute) == (6, 3, 20, 0)
    assert sched["finale"] == pytest.approx(2.5 * DAY)
    assert fresh_season(s1).schedule == sched  # 開季時填好預設值


def test_when_reads_the_schedule_for_showdowns_and_the_calendar_for_the_rest(s1, season):
    season.world.schedule["changshe_fire"] = 1234.0
    assert timetable.when(season, s1, event(s1, "changshe_fire")) == 1234.0
    assert timetable.when(season, s1, event(s1, "bocai")) == pytest.approx(calendar.week_start(4, s1))
    assert timetable.when(season, s1, event(s1, "xiaquyang")) == season.world.schedule["finale"]


def test_due_skips_showdowns_and_resolved_events(s1, season):
    season.world.time = calendar.week_start(7, s1)
    ids = [e.id for e in timetable.due(season, s1)]
    assert ids == ["uprising", "zhangmancheng", "bocai", "luzhi_siege", "qinjie"]  # 照時間，不含長社（決戰）
    timetable.resolve(season, s1, event(s1, "uprising"), random.Random(0))
    assert "uprising" not in [e.id for e in timetable.due(season, s1)]


# ── 擲骰的機率 ───────────────────────────────────────────


def test_roll_chance_from_front(s1, season):
    assert timetable.roll_chance(season, s1, event(s1, "zhangmancheng")) == pytest.approx(0.35)  # 南陽 35、成對黃巾有利
    season.world.trends["yingru"] = 95
    assert timetable.roll_chance(season, s1, event(s1, "bocai")) == pytest.approx(0.9)  # 夾在 0.9
    assert timetable.roll_chance(season, s1, event(s1, "luzhi_siege")) == pytest.approx(0.45)  # 冀州 55、成對官軍有利


def test_roll_chance_falls_back_to_the_trend_start_then_fifty(s1, season):
    """戰況還沒存值時照劇本的起始值；劇本也沒有這條線（T1 之前的真實內容）才當 50。"""
    del season.world.trends["nanyang"]
    assert timetable.roll_chance(season, s1, event(s1, "zhangmancheng")) == pytest.approx(0.35)
    s1.scenario.trends = [t for t in s1.scenario.trends if t.id != "nanyang"]
    assert timetable.roll_chance(season, s1, event(s1, "zhangmancheng")) == pytest.approx(0.5)


def test_luzhi_jailed_base_half(s1, season):
    assert timetable.roll_chance(season, s1, event(s1, "luzhi_jailed")) == pytest.approx(0.5)


def test_roll_uses_the_chance(s1, monkeypatch):
    zhang = event(s1, "zhangmancheng")
    for chance, roll, key in ((0.9, 0.5, "成"), (0.1, 0.5, "不成")):
        state = GameState(player=_player(), world=fresh_season(s1))
        monkeypatch.setattr(timetable, "roll_chance", lambda *args, c=chance: c)
        timetable.resolve(state, s1, zhang, FixedRandom(roll))
        assert state.world.timeline["zhangmancheng"].key == key


def test_event_mods_capped_bonus_not(s1, season):
    luzhi = event(s1, "luzhi_jailed")
    season.world.event_mods["luzhi_jailed"] = 0.35
    assert timetable.roll_chance(season, s1, luzhi) == pytest.approx(0.7)  # 只算 +0.20
    season.world.event_mods["luzhi_jailed"] = 0.0
    season.world.event_bonus["luzhi_jailed"] = -0.10  # 波才北上這類：不受 ±0.20 的上限
    season.world.event_mods["luzhi_jailed"] = -0.35
    assert timetable.roll_chance(season, s1, luzhi) == pytest.approx(0.5 - 0.30 * 0.5 / 0.5)


def test_mods_scale_proportionally():
    assert timetable.apply_mods(0.5, 0.2) == pytest.approx(0.70)
    assert timetable.apply_mods(0.9, 0.2) == pytest.approx(0.94)
    assert timetable.apply_mods(0.1, -0.3) == pytest.approx(0.04)
    for p in (0.1, 0.5, 0.9):
        for m in (-5.0, -0.4, 0.4, 5.0):
            assert 0.0 <= timetable.apply_mods(p, m) <= 1.0


# ── 結算 ─────────────────────────────────────────────────


def test_lock_beats_the_roll_and_names_the_locker(s1, season):
    w = season.world
    w.locks["luzhi_jailed"] = Lock(side="guan", name="甲", time=0.0)
    w.lock_losers["luzhi_jailed"] = [Lock(side="huang", name="乙", time=1.0), Lock(side="huang", name="丙", time=2.0)]
    msgs = timetable.resolve(season, s1, event(s1, "luzhi_jailed"), FixedRandom(0.0))  # 擲骰本來會「成」
    result = w.timeline["luzhi_jailed"]
    assert result.key == "不成" and result.locked_by == "甲" and result.losers == ["乙", "丙"]
    assert msgs == ["【江湖大事】" + LUZHI_LOCKED["guan"].replace("{name}", "甲")
                    + LUZHI_LOSER["guan"].replace("{loser}", "乙、丙")]
    assert w.trends["jizhou"] == 50  # 照「不成」的效果：冀州往官軍偏 5


def test_same_side_late_finishers_are_not_named_as_losers(s1, season):
    """同陣營後來才做完的人照樣做完、記貢獻，但公告裡「搶輸的一句」只寫對手那一方（伏筆文件 2.4）。"""
    w = season.world
    w.locks["luzhi_jailed"] = Lock(side="guan", name="甲", time=0.0)
    w.lock_losers["luzhi_jailed"] = [Lock(side="guan", name="丁", time=1.0), Lock(side="huang", name="乙", time=2.0)]
    msgs = timetable.resolve(season, s1, event(s1, "luzhi_jailed"), FixedRandom(0.0))
    assert msgs == ["【江湖大事】" + LUZHI_LOCKED["guan"].replace("{name}", "甲") + LUZHI_LOSER["guan"].replace("{loser}", "乙")]
    assert w.timeline["luzhi_jailed"].losers == ["乙"] and "丁" not in msgs[0]


def test_locked_chronicle_names_the_locker_and_falls_back(s1, season):
    """江湖史具名（計畫 T7、伏筆文件 2.4）：有人鎖定、而且是他那一方的具名公告時，江湖史用這件大事寫給那一方的那一行；
    那一方沒寫就在原本那一行後面接「（名號改寫）」。沒人鎖定、或管理者給了另一方的結果（公告沒有具名），照原本那一行。
    豪強做完的人另外記一行（多人用「、」接），不論誰贏。"""
    changshe, luzhi = event(s1, "changshe_fire"), event(s1, "luzhi_jailed")
    changshe.locked_chronicle = {"guan": "皇甫嵩火攻長社；火具是{name}備下的。"}
    changshe.third_party_chronicle = "{name} 趁亂收了兩邊的糧錢。"
    w = season.world
    w.locks["changshe_fire"] = Lock(side="guan", name="甲", time=0.0)
    w.third_party["changshe_fire"] = ["豪甲", "豪乙"]
    timetable.resolve(season, s1, changshe, random.Random(0), key="guan:大勝")
    w.locks["luzhi_jailed"] = Lock(side="huang", name="乙", time=0.0)
    timetable.resolve(season, s1, luzhi, FixedRandom(0.99))  # 擲骰本來會「不成」，鎖定定成「成」
    assert [r.text for r in w.chronicle] == [
        "皇甫嵩火攻長社；火具是甲備下的。", "豪甲、豪乙 趁亂收了兩邊的糧錢。", "盧植被誣下獄。（乙改寫）",
    ]

    plain = GameState(player=_player(), world=fresh_season(s1))
    timetable.resolve(plain, s1, luzhi, FixedRandom(0.0))  # 沒人鎖定
    forced = GameState(player=_player(), world=fresh_season(s1))
    forced.world.locks["changshe_fire"] = Lock(side="guan", name="甲", time=0.0)
    timetable.resolve(forced, s1, changshe, random.Random(0), key="huang:險勝")  # 管理者給了另一方的結果
    assert [r.text for r in plain.world.chronicle] == ["盧植被誣下獄。"]
    assert [r.text for r in forced.world.chronicle] == ["長社火攻失利。"] and forced.world.timeline["changshe_fire"].locked_by is None


def test_shown_names_go_into_the_text_and_real_names_into_the_timeline(s1, season):
    """匿名的鎖定者（Lock.shown 是「某位少俠」）：公告、搶輸的一句、改寫的江湖史、豪強的一句都寫 shown；
    時間軸的 locked_by、losers 留真名。舊資料沒有 shown（None）照舊寫名號；豪強的顯示名記在 third_party_shown。"""
    w = season.world
    w.locks["luzhi_jailed"] = Lock(side="guan", name="甲", time=0.0, shown="某位少俠")
    w.lock_losers["luzhi_jailed"] = [Lock(side="huang", name="乙", time=1.0, shown="某位少俠"), Lock(side="huang", name="丙", time=2.0)]
    w.third_party["luzhi_jailed"] = ["豪甲", "豪乙"]
    w.third_party_shown["luzhi_jailed"] = {"豪甲": "某位少俠"}
    msgs = timetable.resolve(season, s1, event(s1, "luzhi_jailed"), FixedRandom(0.0))
    third = "朝中替盧中郎說話最力的是袁本初。{name} 在他府上坐了三個晚上。".replace("{name}", "某位少俠、豪乙")
    assert msgs == ["【江湖大事】" + LUZHI_LOCKED["guan"].replace("{name}", "某位少俠")
                    + LUZHI_LOSER["guan"].replace("{loser}", "某位少俠、丙") + third]
    result = w.timeline["luzhi_jailed"]
    assert (result.locked_by, result.losers) == ("甲", ["乙", "丙"])
    assert [r.text for r in w.chronicle] == ["盧植續圍廣宗。（某位少俠改寫）"]


def test_a_showdown_resolved_with_a_key_uses_the_named_version_when_locked(s1, season):
    """決戰由 T8 給結果鍵（鎖定方一定贏，戰場上定大勝或險勝）：有人鎖定時照樣用具名公告，開頭不再接 preface。"""
    w = season.world
    w.locks["changshe_fire"] = Lock(side="guan", name="甲", time=0.0)
    w.lock_losers["changshe_fire"] = [Lock(side="huang", name="乙", time=1.0)]
    msgs = timetable.resolve(season, s1, event(s1, "changshe_fire"), random.Random(0), key="guan:險勝")
    assert msgs == ["【江湖大事】" + CHANGSHE_LOCKED.replace("{name}", "甲") + CHANGSHE_LOSER.replace("{loser}", "乙")]
    assert (w.timeline["changshe_fire"].key, w.timeline["changshe_fire"].locked_by) == ("guan:險勝", "甲")
    assert w.trends["yingru"] == 32  # 效果照險勝那一格


def test_a_figure_note_fills_the_commander_slot(s1, season, monkeypatch):
    """人物效果接在公告後面的那一句也經過 fill_slots（跟公告的其他部分一樣）。"""
    qinjie = event(s1, "qinjie")
    for outcome in qinjie.outcomes.values():
        outcome.figures["zhujun"] = outcome.figures["zhujun"].model_copy(update={"note": "{官軍主將}也領兵南下。"})
    season.world.figures["huangfusong"] = FigureState(front="yingru")
    season.world.timeline["zhangmancheng"] = timetable.TimelineResult(key="成", time=0.0)
    msgs = timetable.resolve(season, s1, qinjie, random.Random(0))
    assert msgs == ["【江湖大事】新任南陽太守秦頡引兵來攻。官軍也領兵南下。"]


def test_lock_without_losers_has_no_loser_line(s1, season):
    season.world.locks["luzhi_jailed"] = Lock(side="huang", name="甲", time=0.0)
    msgs = timetable.resolve(season, s1, event(s1, "luzhi_jailed"), FixedRandom(0.99))  # 擲骰本來會「不成」
    assert season.world.timeline["luzhi_jailed"].key == "成"
    assert msgs == ["【江湖大事】" + LUZHI_LOCKED["huang"].replace("{name}", "甲")]


def test_skip_if_figure_out(s1, season):
    season.world.figures["zhangmancheng"] = FigureState(status="retired")
    season.world.timeline["zhangmancheng"] = timetable.TimelineResult(key="成", time=0.0)
    before = dict(season.world.trends)
    assert timetable.resolve(season, s1, event(s1, "qinjie"), random.Random(0)) == []
    assert season.world.timeline["qinjie"].key == timetable.SKIPPED
    assert season.world.trends == before and season.world.rumors == [] and season.world.chronicle == []


def test_figure_fates_minimal(s1, season):
    """測試夾具沒有人物表（content.figures 是空的）：時刻表的人物結局只改 WorldState.figures 的聲威與狀態，沒有接位鏈、也就沒有接手。"""
    w = season.world
    w.figures["zhujun"] = FigureState(prestige=60)
    figures.apply(season, s1, "zhujun", FigureChange(fate="受挫"))
    assert w.figures["zhujun"].prestige == 45
    figures.apply(season, s1, "zhujun", FigureChange(fate="聲威大減"))
    assert w.figures["zhujun"].prestige == 15
    figures.apply(season, s1, "zhujun", FigureChange(fate="聲威大減"))
    assert w.figures["zhujun"].prestige == 0  # 夾在 0
    w.figures["luzhi"] = FigureState(prestige=70, front="jizhou", location="luzhi_camp")
    figures.apply(season, s1, "luzhi", FigureChange(fate="下獄"))
    assert w.figures["luzhi"] == FigureState(prestige=70, status="jailed", front="jizhou", location="luzhi_camp")  # 聲威不變
    w.figures["huangfusong"] = FigureState(prestige=70, front="yingru", location="changshe")
    figures.apply(season, s1, "huangfusong", FigureChange(fate="重挫", front="jizhou", location="luzhi_camp"))
    assert w.figures["huangfusong"] == FigureState(prestige=40, front="jizhou", location="luzhi_camp")
    figures.apply(season, s1, "bocai", FigureChange(fate="退場"))
    assert w.figures["bocai"].status == "retired" and w.figures["bocai"].prestige == 0 and figures.is_out(season, "bocai")
    figures.apply(season, s1, "dongzhuo", FigureChange(fate="到任", front="jizhou", location="luzhi_camp"))
    assert w.figures["dongzhuo"].front == "jizhou" and w.figures["dongzhuo"].location == "luzhi_camp"
    assert figures.commander(season, s1, "jizhou", "guan") is None  # 沒有人物表就沒有主將，也沒有人接手


def test_unseeded_figures_count_as_present_on_their_front(s1, season):
    """伏筆讀的 is_out／on_front（夾具沒有人物表）：還沒種的人物不算退場、當成在場；種過的看狀態與所在戰線，戰線看不出來也當在場。"""
    w = season.world
    assert not figures.is_out(season, "huangfusong") and figures.on_front(season, "huangfusong", "yingru")
    w.figures["huangfusong"] = FigureState(front="yingru")
    assert figures.on_front(season, "huangfusong", "yingru") and not figures.on_front(season, "huangfusong", "jizhou")
    w.figures["zhujun"] = FigureState()  # 時刻表套效果時才建的一筆：戰線是空的，看不出來就當在場
    assert figures.on_front(season, "zhujun", "yingru")
    for status in ("retired", "crippled", "jailed", "away"):
        w.figures["luzhi"] = FigureState(front="jizhou", status=status)
        assert not figures.on_front(season, "luzhi", "jizhou")


def test_bonus_from_outcome(s1, season):
    w = season.world
    msgs = timetable.resolve(season, s1, event(s1, "changshe_fire"), random.Random(0), key="huang:大勝")
    assert w.event_bonus["luzhi_siege"] == pytest.approx(-0.10)
    assert w.trends["jizhou"] == 60 and w.trends["yingru"] == 55
    assert msgs == ["【江湖大事】史書上，皇甫嵩趁夜縱火，大破波才於長社。這一次，火攻沒有成。潁川得手之後，波才分兵北上，往廣宗去了。"]
    assert w.figures["huangfusong"].front == "jizhou"
    assert timetable.roll_chance(season, s1, event(s1, "luzhi_siege")) == pytest.approx(0.40 - 0.10 * 0.40 / 0.5)


def test_figure_change_only_if_and_note(s1):
    note = "右中郎將朱儁也領兵南下，往宛城去了。"
    stays = GameState(player=_player(), world=fresh_season(s1))
    stays.world.figures["huangfusong"] = FigureState(front="yingru")
    stays.world.figures["zhujun"] = FigureState(front="yingru", location="changshe")
    stays.world.timeline["zhangmancheng"] = timetable.TimelineResult(key="成", time=0.0)
    msgs = timetable.resolve(stays, s1, event(s1, "qinjie"), random.Random(0))
    assert msgs == [f"【江湖大事】新任南陽太守秦頡引兵來攻。{note}"]
    assert (stays.world.figures["zhujun"].front, stays.world.figures["zhujun"].location) == ("nanyang", "wan_city")

    moved = GameState(player=_player(), world=fresh_season(s1))
    moved.world.figures["huangfusong"] = FigureState(front="jizhou", location="luzhi_camp")  # 已經重挫轉往冀州
    moved.world.figures["zhujun"] = FigureState(front="yingru", location="changshe")
    moved.world.timeline["zhangmancheng"] = timetable.TimelineResult(key="不成", time=0.0)
    msgs = timetable.resolve(moved, s1, event(s1, "qinjie"), random.Random(0))
    assert msgs == ["【江湖大事】援兵統帥秦頡趕到南陽。"]
    assert moved.world.figures["zhujun"].front == "yingru"  # 朱儁是潁川主將，留在潁川
    assert moved.world.figures["zhangmancheng"].status == "retired"


def test_commander_slot_falls_back(s1, season):
    season.world.timeline["zhangmancheng"] = timetable.TimelineResult(key="成", time=0.0)
    msgs = timetable.resolve(season, s1, event(s1, "wancheng"), random.Random(0), key="huang:大勝")
    assert msgs == ["【江湖大事】甲版huang大勝，官軍也在。"]  # 沒有主將時 {官軍主將} 填「官軍」
    assert season.world.figures == {}  # @commander:nanyang:guan 的效果略過、不丟例外
    assert timetable.fill_slots(season, s1, event(s1, "wancheng"), "{黃巾主將}守城") == "黃巾守城"


def test_commander_slot_uses_the_front_commander_when_there_is_one(s1, season, monkeypatch):
    """T4 補完 commander 之後：{官軍主將} 填那位人物的名字，@commander 的效果落在他身上。"""
    monkeypatch.setattr(figures, "commander", lambda state, content, front, side: "captain" if front == "nanyang" else None)
    season.world.figures["captain"] = FigureState(prestige=60, front="nanyang")  # 測試夾具的人物「頭目」
    season.world.timeline["zhangmancheng"] = timetable.TimelineResult(key="不成", time=0.0)
    msgs = timetable.resolve(season, s1, event(s1, "wancheng"), random.Random(0), key="huang:險勝")
    assert msgs == ["【江湖大事】乙版huang險勝，頭目也在。"]
    assert season.world.figures["captain"].prestige == 45


@pytest.mark.parametrize("key", ["guan:大勝", "huang:險勝"])
def test_third_party_applies_regardless_of_winner(s1, season, key):
    season.world.third_party["changshe_fire"] = ["豪甲"]
    msgs = timetable.resolve(season, s1, event(s1, "changshe_fire"), random.Random(0), key=key)
    assert season.world.trends["geju"] == 30  # 割據 +10，不論誰贏
    assert msgs[0].endswith("事後才有人發現，兩軍吃的糧出自同一家：豪甲 的糧車。")


def test_third_party_line_can_differ_by_outcome(s1, season):
    season.world.third_party["luzhi_jailed"] = ["豪甲", "豪乙"]
    msgs = timetable.resolve(season, s1, event(s1, "luzhi_jailed"), FixedRandom(0.99))  # 不成
    assert msgs[0].endswith("朝中替盧中郎說話最力的是袁本初。豪甲、豪乙 在他府上坐了三個晚上。")
    assert season.world.trends["geju"] == 36  # 兩個名字各套一次 +8


def test_resolve_is_idempotent(s1, season):
    zhang = event(s1, "zhangmancheng")
    first = timetable.resolve(season, s1, zhang, FixedRandom(0.0))
    after = season.world.model_copy(deep=True)
    assert first and timetable.resolve(season, s1, zhang, FixedRandom(0.0)) == []
    assert season.world == after


def test_versioned_event_picks_its_version(s1):
    for week3, version in (("成", "甲"), ("不成", "乙")):
        state = GameState(player=_player(), world=fresh_season(s1))
        state.world.timeline["zhangmancheng"] = timetable.TimelineResult(key=week3, time=0.0)
        timetable.resolve(state, s1, event(s1, "qinjie"), random.Random(0))
        timetable.resolve(state, s1, event(s1, "wancheng"), random.Random(0), key="guan:大勝")
        assert state.world.timeline["qinjie"].key == f"{version}:fixed"
        assert state.world.timeline["wancheng"].key == f"{version}:guan:大勝"


# ── 季的事：照曆時切段推進 ────────────────────────────────


def test_jump_over_several_events_resolves_in_order(s1, season):
    """Review Focus 1：一次推進好幾週，期間的大事照週次逐件結算，每件一次，時間遞增；決戰不在這裡結算。"""
    msgs = advance_to_week(season, s1, 5)
    w = season.world
    assert list(w.timeline) == ["uprising", "zhangmancheng", "bocai"]
    times = [r.time for r in w.timeline.values()]
    assert times == sorted(times) and len(set(times)) == 3
    assert times[1] == pytest.approx(calendar.week_start(3, s1))  # 週一 00:00 本身就是曆時的交界：準時結算
    assert len([m for m in msgs if m.startswith("【江湖大事】")]) == 3
    advance_to_week(season, s1, 8)
    assert list(w.timeline) == ["uprising", "zhangmancheng", "bocai", "luzhi_siege", "qinjie", "luzhi_jailed"]
    assert "changshe_fire" not in w.timeline  # 決戰由 T8 收場時結算


def test_week_hooks_run_once_per_week_in_order(s1, season, monkeypatch):
    from tianxia import world

    seen: list[tuple[int, list[str]]] = []
    monkeypatch.setattr(world, "WEEK_HOOKS", [lambda state, content, rng: seen.append(
        (calendar.point(state.world.time, content).week, list(state.world.timeline))) or [f"第{len(seen)}週"]])
    msgs = advance_to_week(season, s1, 3)
    assert [week for week, _ in seen] == [1, 2, 3]
    assert seen[2][1] == ["uprising"]  # 週初的掛鉤先跑，同一刻的大事接著結算
    assert msgs[:2] == ["第1週", "【江湖大事】三十六方同日起事。"]
    advance_world_state(season.world, s1, calendar.cal_hour_seconds(s1) * 5, random.Random(0))
    assert len(seen) == 3  # 同一週不再跑


def test_the_opening_settles_week_one_but_not_the_per_hour_part(s1, season, monkeypatch):
    """FB-040：開季那一刻只跑「週初掛鉤＋到了的大事」（season_events），不跑每曆時的事——T1 的割據變動掛在
    每曆時那一段，開季多跑一次就會多一次。第一次之後 hooked_week 不是 0，再呼叫什麼都不做。"""
    from tianxia import world

    hours: list[int] = []
    monkeypatch.setattr(world, "season_hour", lambda *a, **k: hours.append(1) or [])  # 每曆時的那一段（含 season_events）
    msgs = world.settle_season_start(season.world, s1, random.Random(0))
    assert msgs == ["【江湖大事】三十六方同日起事。"] and hours == []
    w = season.world
    assert w.hooked_week == 1 and list(w.timeline) == ["uprising"] and w.timeline["uprising"].time == 0
    assert world.settle_season_start(w, s1, random.Random(0)) == [] and list(w.timeline) == ["uprising"]


def test_the_opening_settles_nothing_with_the_switch_off_or_on_an_unstamped_season(s1):
    from tianxia import world

    stamped = fresh_season(s1)
    s1.config.season_one = False
    assert world.settle_season_start(stamped, s1, random.Random(0)) == []  # 開關關著
    s1.config.season_one = True
    old = fresh_season(s1).model_copy(update={"season_one": False})  # 開季時開關是關的
    assert world.settle_season_start(old, s1, random.Random(0)) == []
    assert (stamped.timeline, stamped.hooked_week, old.timeline, old.hooked_week) == ({}, 0, {}, 0)


def test_season_hour_runs_the_per_hour_part_first_and_then_the_season_events(s1, season, monkeypatch):
    """每曆時的 tick 放在 season_events 之前（T1 的 geju_tick 掛在前面）；season_events 本身是週初掛鉤＋到了的大事。"""
    from tianxia import world

    order: list[str] = []
    monkeypatch.setattr(world, "season_events", lambda state, content, rng: order.append("events") or ["大事"])
    assert world.season_hour(season, s1, random.Random(0)) == ["大事"] and order == ["events"]


def test_season_one_off_runs_no_calendar(s1):
    """開關關著（或這一季開季時沒開）：照舊每真實小時跑，季曆、時刻表、週初掛鉤都不動。"""
    s1.config.season_one = False
    state = GameState(player=_player(), world=fresh_season(s1))
    advance_world_state(state.world, s1, 10 * 3600, random.Random(0))
    assert state.world.timeline == {} and state.world.schedule == {} and state.world.hooked_week == 0
    s1.config.season_one = True  # 開關打開了，但這一季開季時是關的
    advance_world_state(state.world, s1, 10 * 3600, random.Random(0))
    assert state.world.timeline == {}


# ── 給軍令（T6）用的兩個小工具（控制者 2026-10-04 追加）────────────────


def test_next_event_on_front(s1, season):
    """那條戰線上最早一件還沒結算的大事，照 when 排，不分固定、擲骰、決戰；沒有就是 None。"""
    assert timetable.next_event_on(season, s1, "nanyang").id == "zhangmancheng"
    assert timetable.next_event_on(season, s1, "yingru").id == "bocai"
    timetable.resolve(season, s1, event(s1, "bocai"), random.Random(0))
    assert timetable.next_event_on(season, s1, "yingru").id == "changshe_fire"  # 決戰也算
    season.world.time = calendar.week_start(10, s1)  # 長社排定的時間已經過了、還沒收場：照樣是下一件
    assert timetable.next_event_on(season, s1, "yingru").id == "changshe_fire"
    timetable.resolve(season, s1, event(s1, "changshe_fire"), random.Random(0), key="guan:險勝")
    assert timetable.next_event_on(season, s1, "yingru") is None
    for done in ("zhangmancheng", "qinjie"):
        timetable.resolve(season, s1, event(s1, done), random.Random(0))
    assert timetable.next_event_on(season, s1, "nanyang").id == "wancheng"
    assert timetable.next_event_on(season, s1, "north") is None


def test_add_mod_converts_side_and_caps(s1, season):
    """軍令寫的是「往官軍 +0.05」，event_mods 加在 roll_side 那一方的成功率上：站在另一邊就變號；累計夾在 ±0.20。"""
    luzhi = event(s1, "luzhi_jailed")  # 成對黃巾有利、基礎 0.5（0.5 時等比例調整剛好等於直接加減）
    timetable.add_mod(season, s1, "luzhi_jailed", "guan", 0.05)
    assert season.world.event_mods["luzhi_jailed"] == pytest.approx(-0.05)
    assert timetable.roll_chance(season, s1, luzhi) == pytest.approx(0.45)
    for _ in range(4):
        timetable.add_mod(season, s1, "luzhi_jailed", "guan", 0.05)
    assert season.world.event_mods["luzhi_jailed"] == pytest.approx(-0.20)  # 五則只算到 -0.20
    assert timetable.roll_chance(season, s1, luzhi) == pytest.approx(0.30)
    timetable.add_mod(season, s1, "luzhi_jailed", "huang", 0.05)
    assert season.world.event_mods["luzhi_jailed"] == pytest.approx(-0.15)  # 從夾過的值往回加
    timetable.add_mod(season, s1, "luzhi_siege", "guan", 0.05)  # 成對官軍有利：同一邊，加正的
    assert season.world.event_mods["luzhi_siege"] == pytest.approx(0.05)


def test_add_mod_ignores_events_without_roll(s1, season):
    for event_id in ("qinjie", "changshe_fire", "xiaquyang"):  # 固定、決戰、季末
        timetable.add_mod(season, s1, event_id, "guan", 0.05)
    assert season.world.event_mods == {}


# ── 季曆照這一季蓋的章（fix round 2）──────────────────────────────


def test_calendar_follows_the_season_stamp_not_the_profile(s1):
    """這一季蓋的是 2.5 天：設定中途換成 5 天，正在跑的這一季週次、時刻、大事的時間都不動。"""
    season_world = fresh_season(s1)  # 蓋章 2.5 天
    state = GameState(player=_player(), world=season_world)
    t = 40000.0
    before = (
        calendar.point(t, s1, season_world), calendar.week_start(5, s1, season_world),
        calendar.event_time(event(s1, "bocai"), s1, season_world), calendar.cal_hour_seconds(s1, season_world),
        calendar.is_night(t, s1, season_world), timetable.when(state, s1, event(s1, "bocai")),
        timetable.default_schedule(s1, season_world),
    )
    s1.config.season_days = 5  # 設定換了
    after = (
        calendar.point(t, s1, season_world), calendar.week_start(5, s1, season_world),
        calendar.event_time(event(s1, "bocai"), s1, season_world), calendar.cal_hour_seconds(s1, season_world),
        calendar.is_night(t, s1, season_world), timetable.when(state, s1, event(s1, "bocai")),
        timetable.default_schedule(s1, season_world),
    )
    assert after == before
    assert calendar.week_start(5, s1) == pytest.approx(2 * calendar.week_start(5, s1, season_world))  # 沒給季才照設定
    advance_to_week(state, s1, 4)  # 季的事也照蓋的章切曆時：第 4 週週一的大事準時結算
    assert state.world.timeline["bocai"].time == pytest.approx(calendar.week_start(4, s1, season_world))


# ── 人物欄位（FB-042，濃縮版內容表第八節）：{人物:<id>} 與 @人物:<id> ─────────────────────
#
# 要人物表（戰線、陣營、接位鏈），所以用真實內容、開關打開；文字與效果在測試裡自己寫，不靠 timetable.json 的句子。

CONTENT_DIR = Path(__file__).parent.parent / "content"


@pytest.fixture
def real_on():
    """真實內容（人物表照濃縮版內容表 1.1），第一季開關打開。"""
    c = load_content(CONTENT_DIR)
    c.config.season_one = True
    return c


def _real_season(c) -> GameState:
    """開季那一刻的一季（人物照人物表種好）＋季的事用的那種空殼玩家。"""
    player = PlayerState(name="", location=c.scenario.start_location, stats={}, stamina=0)
    return GameState(player=player, world=fresh_season(c))


def test_person_slot_names_the_figure_who_is_on_the_events_front(real_on):
    """規則第 1 條：在場、而且在這件大事的戰線上，就寫他自己——不必是主將（朱儁排在皇甫嵩後面，照樣寫朱儁）。"""
    s = _real_season(real_on)
    changshe = event(real_on, "changshe_fire")
    assert timetable.fill_slots(s, real_on, changshe, "{人物:bocai}守營，{人物:zhujun}守城。") == "波才守營，朱儁守城。"


def test_person_slot_names_whoever_took_over_when_he_is_gone(real_on):
    """規則第 2 條：不在場、或不在這條戰線上，寫這條戰線他那一方當時的主將（接手的人）。"""
    s = _real_season(real_on)
    changshe, siege = event(real_on, "changshe_fire"), event(real_on, "luzhi_siege")
    figures.apply(s, real_on, "bocai", FigureChange(fate="退場"))  # 彭脫接手潁川
    figures.apply(s, real_on, "huangfusong", FigureChange(fate="重挫", front="jizhou", location="luzhi_camp"))  # 轉往冀州
    assert timetable.fill_slots(s, real_on, changshe, "{人物:bocai}對{人物:huangfusong}。") == "彭脫對朱儁。"
    figures.apply(s, real_on, "luzhi", FigureChange(fate="下獄"))
    assert timetable.fill_slots(s, real_on, siege, "{人物:luzhi}圍廣宗。") == "皇甫嵩圍廣宗。"  # 長社後轉來的皇甫嵩
    assert timetable.fill_slots(s, real_on, siege, "{人物:huangfusong}也在。") == "皇甫嵩也在。"  # 在冀州，寫他自己


def test_person_slot_falls_back_to_the_generic_title(real_on):
    """規則第 3 條：這條戰線他那一方也沒有人了，官軍寫「官軍主將」、黃巾寫「黃巾渠帥」。"""
    s = _real_season(real_on)
    for fid in ("bocai", "pengtuo", "huangfusong", "zhujun"):
        s.world.figures[fid].status = "retired"
    changshe = event(real_on, "changshe_fire")
    assert timetable.fill_slots(s, real_on, changshe, "{人物:bocai}、{人物:huangfusong}") == "黃巾渠帥、官軍主將"


def test_person_effect_lands_on_whoever_the_text_names(real_on):
    """@人物:<id> 照同一個規則找人：他在就落在他身上，他不在就落在接手的人身上。"""
    changshe = event(real_on, "changshe_fire")
    changshe.outcomes["guan:險勝"] = TimetableOutcome(
        text="這一次，{人物:bocai}敗走。", figures={"@人物:bocai": FigureChange(fate="受挫")},
    )
    here = _real_season(real_on)
    msgs = timetable.resolve(here, real_on, changshe, random.Random(0), key="guan:險勝")
    assert msgs == [f"【江湖大事】{changshe.preface}這一次，波才敗走。"]
    assert here.world.figures["bocai"].prestige == 45  # 60 − 15

    gone = _real_season(real_on)
    figures.apply(gone, real_on, "bocai", FigureChange(fate="退場"))  # 彭脫接手潁川（聲威 40）
    msgs = timetable.resolve(gone, real_on, changshe, random.Random(0), key="guan:險勝")
    assert msgs == [f"【江湖大事】{changshe.preface}這一次，彭脫敗走。"]
    assert gone.world.figures["pengtuo"].prestige == 25


def test_person_effect_is_skipped_when_nobody_is_named(real_on):
    """找到的是泛稱（這條戰線那一方沒有人）：效果略過、不丟例外。"""
    changshe = event(real_on, "changshe_fire")
    changshe.outcomes["guan:險勝"] = TimetableOutcome(
        text="這一次，{人物:bocai}敗走。", figures={"@人物:bocai": FigureChange(fate="受挫")},
    )
    s = _real_season(real_on)
    for fid in ("bocai", "pengtuo"):
        s.world.figures[fid].status = "retired"
    before = {fid: f.model_copy() for fid, f in s.world.figures.items()}
    msgs = timetable.resolve(s, real_on, changshe, random.Random(0), key="guan:險勝")
    assert msgs == [f"【江湖大事】{changshe.preface}這一次，黃巾渠帥敗走。"]
    assert s.world.figures == before


def test_person_targets_are_settled_before_any_effect(real_on):
    """文字寫誰，效果就落在誰身上：前一筆效果讓那個人退場，後一筆 @人物 也不會因此換到下一位（張寶不受牽連）。"""
    guangzong = event(real_on, "guangzong")
    guangzong.outcomes["guan:險勝"] = TimetableOutcome(
        text="這一次，斬{人物:zhangliang}。",
        figures={"zhangjiao": FigureChange(fate="退場"), "@人物:zhangliang": FigureChange(fate="聲威大減")},
    )
    s = _real_season(real_on)
    s.world.figures["zhangliang"].status = "retired"  # 張梁不在：欄位寫冀州黃巾的主將張角
    msgs = timetable.resolve(s, real_on, guangzong, random.Random(0), key="guan:險勝")
    assert msgs == ["【江湖大事】這一次，斬張角。"]
    assert s.world.figures["zhangjiao"].status == "retired"
    assert s.world.figures["zhangbao"].prestige == 60  # 不是「張角退場之後的主將」張寶


def test_person_slots_fill_every_line_and_before_the_effects(real_on):
    """具名公告、搶輸的一句、note、人物效果的 note、江湖史（含具名的那一行）都填；而且都在套效果之前填——
    波才退場、彭脫接手之後，這些句子寫的仍是波才。"""
    changshe = event(real_on, "changshe_fire")
    changshe.outcomes["guan:大勝"] = TimetableOutcome(
        text="這一次，{人物:huangfusong}大勝。",
        locked_text={"guan": "{name} 助{人物:huangfusong}破營。"},
        loser_text={"guan": "{loser} 勸{人物:bocai}移營。"},
        note="{人物:bocai}北走。",
        chronicle="{人物:huangfusong}破{人物:bocai}。",
        figures={"@人物:bocai": FigureChange(fate="退場", note="{人物:bocai}退出戰事。")},
    )
    changshe.locked_chronicle = {"guan": "{人物:huangfusong}與{name}破{人物:bocai}。"}
    s = _real_season(real_on)
    s.world.locks["changshe_fire"] = Lock(side="guan", name="甲", time=0.0)
    s.world.lock_losers["changshe_fire"] = [Lock(side="huang", name="乙", time=1.0)]
    msgs = timetable.resolve(s, real_on, changshe, random.Random(0), key="guan:大勝")
    assert msgs == ["【江湖大事】甲 助皇甫嵩破營。波才北走。波才退出戰事。乙 勸波才移營。"]
    assert s.world.chronicle[-1].text == "皇甫嵩與甲破波才。"
    assert (s.world.figures["bocai"].status, s.world.figures["pengtuo"].front) == ("retired", "yingru")

    plain = _real_season(real_on)  # 沒人鎖定：公告是開頭＋這一格，江湖史是原本那一行
    msgs = timetable.resolve(plain, real_on, changshe, random.Random(0), key="guan:大勝")
    assert msgs == [f"【江湖大事】{changshe.preface}這一次，皇甫嵩大勝。波才北走。波才退出戰事。"]
    assert plain.world.chronicle[-1].text == "皇甫嵩破波才。"


def test_third_party_lines_are_filled_before_the_effects(real_on):
    """FB-042 審查 I2：豪強那一句（公告）與另記的那一行江湖史也在套效果之前填：波才退場、彭脫接手之後仍寫波才。"""
    changshe = event(real_on, "changshe_fire")
    changshe.outcomes["guan:大勝"] = TimetableOutcome(
        text="這一次，{人物:bocai}敗走。", figures={"@人物:bocai": FigureChange(fate="退場")},
        third_party_text="{name} 的糧車餵飽了{人物:bocai}的兵。",
    )
    changshe.third_party_chronicle = "{name} 資助{人物:bocai}。"
    s = _real_season(real_on)
    s.world.third_party["changshe_fire"] = ["丙"]
    msgs = timetable.resolve(s, real_on, changshe, random.Random(0), key="guan:大勝")
    assert msgs[0].endswith("丙 的糧車餵飽了波才的兵。")
    assert s.world.chronicle[-1].text == "丙 資助波才。"
    assert s.world.figures["bocai"].status == "retired"


def test_the_preface_is_not_filled(real_on):
    """preface 只有「史書上」那半句，照寫真名，不經過人物欄位。"""
    changshe = event(real_on, "changshe_fire")
    changshe.preface = "史書上，{人物:bocai}……"
    changshe.outcomes["guan:險勝"] = TimetableOutcome(text="這一次，{人物:bocai}敗走。")
    s = _real_season(real_on)
    msgs = timetable.resolve(s, real_on, changshe, random.Random(0), key="guan:險勝")
    assert msgs == ["【江湖大事】史書上，{人物:bocai}……這一次，波才敗走。"]


def _outcome(c, event_id: str, key: str) -> TimetableOutcome:
    return event(c, event_id).outcomes[key]


@pytest.mark.parametrize(("edit", "message"), [
    (lambda c: setattr(_outcome(c, "bocai_routs_zhujun", "成"), "chronicle", "{人物:ghost}大敗。"), "未知的人物 ghost"),
    (lambda c: setattr(_outcome(c, "bocai_routs_zhujun", "成"), "text", "{人物:caocao}來了。"), "未知的人物 caocao"),  # 對話人物不是大勢人物
    (lambda c: _outcome(c, "changshe_fire", "guan:大勝").locked_text.update(guan="{name} 與{人物:ghost}。"), "未知的人物 ghost"),
    (lambda c: _outcome(c, "changshe_fire", "guan:大勝").figures.update(
        {"@人物:ghost": FigureChange(fate="受挫")}), "未知的人物 ghost"),
    (lambda c: _outcome(c, "changshe_fire", "guan:大勝").figures.update(
        {"zhujun": FigureChange(fate="受挫", note="{人物:ghost}也在。")}), "未知的人物 ghost"),
    (lambda c: setattr(_outcome(c, "luzhi_jailed", "成"), "chronicle", "{人物:luzhi}下獄。"), "front"),  # 沒有戰線的大事不能用
    (lambda c: _outcome(c, "luzhi_jailed", "不成").figures.update({"@人物:luzhi": FigureChange(fate="受挫")}), "front"),
    (lambda c: setattr(c.figures["dongzhuo"], "faction", "haoqiang"), "官軍或黃巾"),  # 泛稱只有官軍、黃巾兩種
])
def test_person_slots_are_checked_at_load(real_on, edit, message):
    """載入檢查：欄位與鍵裡的 id 要在人物表上；用到欄位的大事要有 front；欄位寫的人物要是官軍或黃巾的。"""
    _outcome(real_on, "luzhi_siege", "成").chronicle = "{人物:luzhi}圍{人物:dongzhuo}。"  # 合格的寫法，edit 之前要過得了
    validate(real_on)
    edit(real_on)
    with pytest.raises(ContentError, match=message):
        validate(real_on)
