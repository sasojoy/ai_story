"""第一季濃縮版 T1：三條戰線、黃巾聲勢（衍生）、豪強割據，以及第一季的規則沒開（開關關著，或這一季開季時沒蓋「開」的章）時一切照舊。

規則與引擎的測試大多用真實內容（content/）：要驗的就是那三條戰線、起始值與地點歸屬。每個測試自己載一份
（約 0.06 秒），開關在測試裡才打開，不會漏到別的測試。"""
from __future__ import annotations

import random
from pathlib import Path
from unittest import mock

import pytest

from conftest import FixedRandom
from tianxia import atlas, battle_instance, bot_policy, front_lines, mapview, rules, team, timetable, world
from tianxia.content import ContentError, load_content, validate
from tianxia.encounter import EncounterResult
from tianxia.engine import Game
from tianxia.models import Condition, Config, Effect
from tianxia.state import BotProfile, WorldState
from tianxia.world_state import fresh_season

CONTENT_DIR = Path(__file__).parent.parent / "content"
FRONTS = ["yingru", "nanyang", "jizhou"]


@pytest.fixture
def real():
    """真實內容，開關關著（beta 那一季的樣子）。"""
    c = load_content(CONTENT_DIR)
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0  # 遊歷打完不接戰後事件，大勢的變化才寫得死
    return c


@pytest.fixture
def on(real):
    """同一份真實內容，開關打開（第一季濃縮版）。"""
    real.config.season_one = True
    return real


def _game(content, name="甲"):
    return Game.new(content, name, rng=random.Random(0))


def _win():
    """遊歷穩贏（team.fight 的結果寫死），只看大勢怎麼推。"""
    return mock.patch.object(
        team, "fight", return_value=EncounterResult(tier="大勝", margin=50, our_power=100, difficulty=15),
    )


def test_the_season_one_switch_is_off_by_default():
    cfg = Config()
    assert cfg.season_one is False
    assert (cfg.geju_chaos_per_day, cfg.geju_calm_per_day, cfg.chaos_low, cfg.chaos_high) == (1.0, 1.0, 35, 65)
    assert WorldState().trend_accum == {}


# ── Task 2：換算，以及開關關著時一切照舊 ────────────────────────


def test_front_of_location(real):
    assert rules.front_of(real, "changshe") == "yingru"  # 長社
    assert rules.front_of(real, "zhuo_county") == "jizhou"  # 涿郡：幽州的戰況併入冀州
    assert rules.front_of(real, "luoyang_palace") is None  # 洛陽宮城：洛陽沒有戰況
    assert rules.front_ids(real) == FRONTS


def test_switch_off_reads_every_front_as_huangjin(real):
    w = fresh_season(real)  # 開關關著時開的季
    for key in FRONTS:
        assert rules.resolve_trend(real, w, key) == "huangjin"
    assert rules.resolve_trend(real, w, "front", "luoyang_palace") == "huangjin"
    assert rules.resolve_trend(real, w, "front", "changshe") == "huangjin"
    assert rules.resolve_trend(real, w, "geju") is None
    assert (rules.resolve_trend(real, w, "huangjin"), rules.resolve_trend(real, w, "yuxi")) == ("huangjin", "yuxi")
    goals = {f.id: rules.resolve_goals(real, w, f.goals) for f in real.scenario.factions}
    assert goals == {"guan": {"huangjin": -1}, "huang": {"huangjin": 1}, "haoqiang": {}}
    sims = [rules.resolve_trends(real, w, s.trend) for s in real.scenario.sim_players]
    assert sims == [{"huangjin": 1}, {"huangjin": -1}, {"yuxi": 2}]
    shown = [rules.trend_shown(real, w, t) for t in ("huangjin", "yuxi", *FRONTS, "geju")]
    assert shown == [True, True, False, False, False, False]
    assert [rules.pushable(real, w, t) for t in ("huangjin", "yingru")] == [True, False]


def test_switch_on_reads_fronts_as_themselves(on):
    w = fresh_season(on)  # 開關開著時開的季：章是「開」
    assert [rules.resolve_trend(on, w, key) for key in [*FRONTS, "geju"]] == [*FRONTS, "geju"]
    assert rules.resolve_trend(on, w, "front", "changshe") == "yingru"
    assert rules.resolve_trend(on, w, "front", "zhuo_county") == "jizhou"
    assert rules.resolve_trend(on, w, "front", "luoyang_palace") is None
    assert rules.resolve_goals(on, w, on.scenario.factions[0].goals) == {"yingru": -1, "nanyang": -1, "jizhou": -1}
    assert [rules.pushable(on, w, t) for t in ("huangjin", "yingru", "geju")] == [False, True, True]


@pytest.mark.parametrize("faction, delta", [(None, -1), ("guan", -1), ("huang", 1), ("haoqiang", -1)])
def test_switch_off_training_at_changshe_moves_huangjin_as_before(real, faction, delta):
    """開關關著：在長社遊歷打贏（黃巾的人遇上黃巾的隊伍是操練），黃巾聲勢的變化跟 T1 之前一模一樣——
    長社原本寫 huangjin -1：散人、官軍、豪強 -1，黃巾 +1；也不會冒出別的線。"""
    game = _game(real)
    game.state.player.faction = faction
    game.state.player.location = "changshe"
    assert game.train_trend_push() == {"huangjin": delta}
    with _win():
        msgs = game._squad_encounter("louluo")  # 黃巾嘍囉是黃巾的隊伍
    assert game.state.world.trends == {"huangjin": 25 + delta, "yuxi": 0}
    assert f"（黃巾聲勢 {delta:+d}）" in msgs


def test_switch_off_effect_front_pushes_huangjin_anywhere(real):
    """front 在開關關著時一律是黃巾聲勢，連洛陽也一樣（beta 那一季的事件原本都寫 huangjin）。"""
    game = _game(real)
    game.state.player.location = "luoyang_palace"
    msgs = rules.apply_effect(Effect(trend={"front": 2}), game.state, real, game.world)
    assert game.state.world.trends["huangjin"] == 27
    assert msgs == ["（黃巾聲勢 +2）"]


def test_switch_off_world_and_screens_look_as_before(real):
    """新的一季只有黃巾聲勢與玉璽線索；大勢頁、地圖每個大區的標示與顏色、龍頭人物的說明都照舊寫黃巾聲勢。"""
    game = _game(real)
    w = game.state.world
    assert (w.trends, w.revealed) == ({"huangjin": 25, "yuxi": 0}, {"huangjin"})
    assert fresh_season(real).trends == {"huangjin": 25, "yuxi": 0}
    text = game.trends_text()
    assert "黃巾聲勢" in text and not any(name in text for name in ("潁川汝南", "南陽", "冀州", "豪強割據"))
    regions = {r.id: atlas.region_trends(game.state, real, r) for r in real.map.regions}
    assert regions == {
        "youzhou": [("黃巾聲勢", 25)], "jizhou": [("黃巾聲勢", 25)], "luoyang": [],
        "yingru": [("黃巾聲勢", 25)], "nanyang": [("黃巾聲勢", 25)],
    }
    assert "讓黃巾聲勢上升" in atlas.leader_activity(game.state, real, "波才")
    svg = mapview.render_map(game.state, real, "situation")
    for region in real.map.regions:
        if region.id != "luoyang":
            assert mapview._tint(region.fill, 25) in svg, region.id


def test_switch_off_sim_players_and_battle_outcomes_push_huangjin(real):
    real.scenario.sim_players = real.scenario.sim_players[:1]  # 只留波才（原本寫 huangjin +1，現在寫 yingru +1）
    game = _game(real)
    world.sim_tick(game.state, real, 1, FixedRandom(0.0))  # 0.0：這一小時一定出手
    assert game.state.world.trends == {"huangjin": 26, "yuxi": 0}
    battle = battle_instance.BattleInstance(battle_id="huangjin_showdown", outcome_trend_delta={"yingru": -35})
    game._apply_outcome_trends_and_flags(game.state.world, battle)
    assert game.state.world.trends == {"huangjin": 0, "yuxi": 0}


def test_admin_cannot_push_the_derived_trend_while_on(real):
    admin = _game(real, "Rayal")
    assert admin.admin_push_trend("geju", 5) == ["（沒有這條大勢線。）"]  # 開關關著：豪強割據不存在
    admin.admin_push_trend("huangjin", 5)
    assert admin.state.world.trends["huangjin"] == 30
    real.config.season_one = True
    admin.state.world.season_one = True  # 這一季也蓋了「開」的章
    assert admin.admin_push_trend("huangjin", 5) == ["（黃巾聲勢由三條戰線合成，不能直接推；請推其中一條戰線。）"]
    assert admin.state.world.trends["huangjin"] == 30


def test_switch_off_bots_read_the_goals_as_before(real):
    game = _game(real)
    game.state.player.faction = "guan"
    profile = BotProfile(personality="普通", seed=1, faction="guan", season_number=1)
    assert bot_policy._goals(game, profile) == {"huangjin": -1}
    moved = rules.resolve_trends(real, game.state.world, {"front": 2}, "changshe")
    assert bot_policy.effect_score(Effect(trend={"front": 2}), {"huangjin": -1}, moved) == -20.0


def test_the_timetable_reads_fronts_through_trend_value_and_cannot_push_huangjin(real):
    """T2 的兩個替身換掉之後行為不變：時刻表讀戰線＝存的值，沒存讀起始值，劇本沒有的線當 50；
    時刻表的效果也不能推黃巾聲勢（衍生線）。"""
    game = _game(real)
    s = game.state
    assert timetable._front_value(s, real, "yingru") == 40  # 開關關著開的季沒存戰線：起始值
    s.world.trends["yingru"] = 63
    assert timetable._front_value(s, real, "yingru") == 63
    assert timetable._front_value(s, real, "ghost") == 50
    event = next(e for e in real.timetable if e.kind == "roll")
    next(iter(event.outcomes.values())).trends = {"huangjin": 5}
    with pytest.raises(ContentError, match="huangjin"):
        validate(real)


# ── Task 3：開關開著——加權、亂局、態勢、割據 ─────────────────────


def _set_fronts(state, yingru, nanyang, jizhou):
    state.world.trends.update(yingru=yingru, nanyang=nanyang, jizhou=jizhou)


def _join(game, count=1):
    """這一季的投靠名冊上有 count 個人（名冊空著，割據不漲，畫面上的說明也跟著變，見 FB-065 M1）。"""
    for i in range(count):
        game.world.record_faction(f"投靠者{i}", "guan")


def test_huangjin_is_the_weighted_fronts(on):
    game = _game(on)
    s = game.state
    assert rules.trend_value(s, on, "huangjin") == 45  # 40×0.35＋35×0.25＋55×0.40＝44.75→45
    assert s.world.trends["huangjin"] == 45  # 新的一季照三條戰線的起始值算好存著
    rules.change_trend(s, on, "yingru", 10)  # 潁川 50
    assert rules.trend_value(s, on, "huangjin") == 48  # 48.25→48
    assert s.world.trends["huangjin"] == 48
    assert rules.stances(s, on) == {"guan": 52, "huang": 48, "haoqiang": 10}


def test_derived_trend_cannot_be_pushed_directly(real):
    game = _game(real)
    rules.change_trend(game.state, real, "huangjin", 5)  # 開關關著：黃巾聲勢是一般的線，照推
    assert game.state.world.trends["huangjin"] == 30
    real.config.season_one = True
    game.state.world.season_one = True  # 這一季也蓋了「開」的章
    with pytest.raises(ValueError):
        rules.change_trend(game.state, real, "huangjin", 5)


def test_new_season_with_the_switch_on_has_every_line(on):
    season = fresh_season(on)
    assert season.trends == {"huangjin": 45, "yingru": 40, "nanyang": 35, "jizhou": 55, "geju": 10, "yuxi": 0}
    assert season.revealed == {"huangjin", "yingru", "nanyang", "jizhou", "geju"}


def test_old_world_without_fronts_reads_start_values_and_pushes(on):
    """Review Focus 1：beta 那一季在內容改版前開的，存檔只有黃巾聲勢與玉璽線索、revealed 也沒有三條戰線。
    開關打開後：戰線讀起始值、黃巾聲勢讀加權值；推戰線不會被當成還沒浮現的隱藏線吞掉，也不冒出「浮上檯面」；
    背景推進一下，存下來的黃巾聲勢（條件讀的那一份）就對了。"""
    game = _game(on)
    s = game.state
    s.world.trends = {"huangjin": 25, "yuxi": 0}
    s.world.revealed = {"huangjin"}
    assert [rules.trend_value(s, on, t) for t in (*FRONTS, "geju", "huangjin")] == [40, 35, 55, 10, 45]
    assert rules.change_trend(s, on, "yingru", -2) == [front_lines.mark("yingru", -2)]
    assert (s.world.trends["yingru"], s.world.trends["huangjin"]) == (38, 44)  # 13.3＋8.75＋22＝44.05→44
    s.world.trends = {"huangjin": 25, "yuxi": 0}  # 回到沒推過的舊存檔
    world.advance_world_state(s.world, on, 1, random.Random(0))
    assert s.world.trends["huangjin"] == 45
    assert rules.check_condition(Condition(trend_min={"huangjin": 45}), s)
    assert game.push_trend("nanyang", -2, source="train") == [front_lines.mark("nanyang", -2)]  # T3 的推動也不把它當沒浮現的線


def test_old_world_leader_activity_still_names_the_front_pushes(on):
    """同一種舊季（存檔的 revealed 沒有三條戰線）：龍頭人物的活動說明照樣寫出他推哪條戰線，不會把公開的戰線當成還沒浮現。"""
    game = _game(on)
    s = game.state
    assert "潁川汝南下降" in atlas.leader_activity(s, on, "皇甫嵩")  # 新的一季：基準
    s.world.trends = {"huangjin": 25, "yuxi": 0}
    s.world.revealed = {"huangjin"}
    assert "潁川汝南下降" in atlas.leader_activity(s, on, "皇甫嵩")
    assert "潁川汝南上升" in atlas.leader_activity(s, on, "波才")


def test_front_key_at_luoyang_pushes_nothing_when_on(on):
    """Review Focus 2：洛陽沒有戰況，推「所在戰線」的效果什麼都不推、不丟例外；到了長社就推潁川。"""
    game = _game(on)
    s = game.state
    s.player.location = "luoyang_palace"
    before = dict(s.world.trends)
    assert rules.apply_effect(Effect(trend={"front": 2}), s, on, game.world) == []
    assert s.world.trends == before
    s.player.location = "changshe"
    assert rules.apply_effect(Effect(trend={"front": 2}), s, on, game.world) == [front_lines.mark("yingru", 2)]
    assert (s.world.trends["yingru"], s.world.trends["huangjin"]) == (42, 45)  # 14.7＋8.75＋22＝45.45→45


def test_geju_rises_with_chaos_and_falls_when_calm(on):
    game = _game(on)
    s = game.state
    _set_fronts(s, 40, 35, 80)  # 潁川、南陽在亂局（35 也算，含兩端），冀州穩
    for _ in range(24):  # 一曆日
        rules.geju_tick(s, on, 1)
    assert s.world.trends["geju"] == 12
    _set_fronts(s, 20, 34, 66)  # 三條都穩
    for _ in range(24):
        rules.geju_tick(s, on, 1)
    assert s.world.trends["geju"] == 11
    for _ in range(12):  # 半曆日：不足一點，先累積
        rules.geju_tick(s, on, 1)
    assert s.world.trends["geju"] == 11
    assert s.world.trend_accum["geju"] == pytest.approx(-0.5)


def _geju_rise(content, players, hours, fronts=(40, 40, 40)):
    """三條戰線固定在 fronts，跑 hours 個曆時（每曆時一次 geju_tick）後割據漲了幾點；players 是這一季投靠名冊的人數（None＝不知道）。"""
    s = _game(content).state
    _set_fronts(s, *fronts)
    before = s.world.trends["geju"]
    for _ in range(hours):
        rules.geju_tick(s, content, 1, players=players)
    return s.world.trends["geju"] - before


def test_geju_does_not_rise_when_nobody_has_joined_a_faction(on):
    """人數等比例調整（企劃者 2026-10-05）：一個人都沒投靠，三條戰線全在亂局，割據也一點不漲，累積也不攢。"""
    on.config.geju_full_players = 10
    s = _game(on).state
    _set_fronts(s, 40, 40, 40)
    for _ in range(48):
        rules.geju_tick(s, on, 1, players=0)
    assert s.world.trends["geju"] == 10 and s.world.trend_accum["geju"] == 0


@pytest.mark.parametrize("players, rise", [(5, 3), (10, 6), (2, 1)])  # 三條在亂局、兩曆日：全速 3×2＝6 點，按名冊占滿額的比例
def test_geju_rise_is_proportional_to_the_roster_below_the_full_size(on, players, rise):
    on.config.geju_full_players = 10
    assert _geju_rise(on, players, 48) == rise


@pytest.mark.parametrize("players", [10, 11, 40])
def test_geju_rise_is_capped_at_the_designed_speed(on, players):
    """滿額以上不再加快：一季真的湊滿人，割據照設計的速度漲。"""
    on.config.geju_full_players = 10
    assert _geju_rise(on, players, 48) == 6


def test_geju_rise_is_unscaled_when_the_roster_is_unknown(on):
    """沒給名冊（純函式的呼叫，沒有資料庫可查）：照設計速度，不縮放。"""
    on.config.geju_full_players = 10
    assert _geju_rise(on, None, 48) == 6


def test_the_roster_scales_only_the_rise_not_the_calm_down(on):
    """三條都穩下來時回落照 geju_calm_per_day，跟名冊幾個人無關。"""
    on.config.geju_full_players = 10
    assert _geju_rise(on, 0, 24, fronts=(20, 80, 90)) == -1
    assert _geju_rise(on, 2, 24, fronts=(20, 80, 90)) == -1


def test_geju_roster_scaling_does_nothing_while_the_switch_is_off(real):
    real.config.geju_full_players = 10
    game = _game(real)
    for _ in range(48):
        rules.geju_tick(game.state, real, 1, players=0)
        rules.geju_tick(game.state, real, 1, players=40)
    assert game.state.world.trends == {"huangjin": 25, "yuxi": 0}
    assert game.state.world.trend_accum == {}


def test_the_season_clock_reads_the_roster_from_the_store(on):
    """季的時鐘自己去查名冊：真實 24 小時＝6 曆日，三條在亂局全速是 +18；四人投靠、滿額 8 人＝一半＝+9。
    推進包在 mutate_season 裡（背景追趕走這一條）也查得到——讀名冊不是 mutate，不會撞「mutate 不能巢狀」。"""
    on.scenario.sim_players, on.timetable = [], []
    on.config.geju_full_players = 8
    game = _game(on)
    for name in "甲乙丙丁":
        game.world.record_faction(name, "guan")
    game.world.mutate_season(lambda season: season.trends.update(yingru=50, nanyang=50, jizhou=50))
    world.advance_season(game.world, on, 24 * 3600, random.Random(0), now=0.0)
    assert game.world.get_season().trends["geju"] == 19  # 10 + 18 × 4/8


def test_the_players_advance_reads_the_roster_too(on):
    """玩家自己「等待」那一條（Game.advance）一樣按名冊縮放；一個人都沒投靠就一點不漲。"""
    on.scenario.sim_players, on.timetable = [], []
    on.config.geju_full_players = 8
    game = _game(on)
    _set_fronts(game.state, 50, 50, 50)
    game.advance(24 * 3600)
    assert game.world.get_season().trends["geju"] == 10
    for name in "甲乙":
        game.world.record_faction(name, "huang")
    game.advance(24 * 3600)
    assert game.world.get_season().trends["geju"] == 14  # 每曆日 3 點全速、六曆日 18 點，2/8 ＝ 4.5 → 4（餘 0.5 累積）


def test_geju_does_not_move_while_the_switch_is_off(real):
    real.scenario.sim_players = []
    game = _game(real)
    for _ in range(48):
        rules.geju_tick(game.state, real, 1)
    world.advance_world_state(game.state.world, real, 24 * 3600, random.Random(0))
    assert game.state.world.trends == {"huangjin": 25, "yuxi": 0}
    assert game.state.world.trend_accum == {}


def test_the_season_clock_runs_the_geju_tick_once_per_calendar_hour(on):
    """割據掛在 T2 的 season_hour：季長 14 天時一個真實小時是 6 個曆時，所以真實 24 小時＝6 曆日，三條都在亂局
    就是 +18。每小時那一步若也掛了，會多出 +3，這裡看得出來。"""
    on.scenario.sim_players, on.timetable = [], []  # 不讓虛擬玩家與時刻表動戰線，只看割據
    game = _game(on)
    s = game.state
    _set_fronts(s, 50, 50, 50)
    world.advance_world_state(s.world, on, 24 * 3600, random.Random(0))
    assert s.world.trends["geju"] == 28


def test_geju_waits_for_a_season_stamped_with_the_switch_on(real):
    """開關關著時開的季（T2 的章是「關」），之後把開關打開：季的事不跑，割據也不動。"""
    real.scenario.sim_players = []
    game = _game(real)
    real.config.season_one = True
    world.advance_world_state(game.state.world, real, 24 * 3600, random.Random(0))
    assert "geju" not in game.state.world.trends


def test_map_tints_each_region_by_its_front(on):
    """Review Focus 4：開關開著時每個大區照自己的戰線標值、上色；幽州跟著冀州，洛陽不上色。"""
    game = _game(on)
    s = game.state
    _set_fronts(s, 30, 70, 90)
    regions = {r.id: atlas.region_trends(s, on, r) for r in on.map.regions}
    assert regions == {
        "youzhou": [("冀州", 90)], "jizhou": [("冀州", 90)], "luoyang": [],
        "yingru": [("潁川汝南", 30)], "nanyang": [("南陽", 70)],
    }
    svg = mapview.render_map(s, on, "situation")
    fills = {r.id: r.fill for r in on.map.regions}
    for region_id, value in (("yingru", 30), ("nanyang", 70), ("jizhou", 90), ("youzhou", 90)):
        assert mapview._tint(fills[region_id], value) in svg, region_id
    assert "黃巾聲勢" not in svg


# ── Task 4：遊歷照陣營推所在戰線；每一種推動之後黃巾聲勢都對 ──────────


@pytest.mark.parametrize("faction, place, squad, moved", [
    ("guan", "changshe", "louluo", {"yingru": 39}),  # 官軍在長社打贏黃巾：潁川往 0 推
    ("huang", "nanyang_wilds", "jun_bing", {"nanyang": 36}),  # 黃巾在南陽郊野打贏郡國兵：南陽往 100 推
    (None, "changshe", "louluo", {"yingru": 39}),  # 散人照地點原本的方向（長社寫 -1）
    ("haoqiang", "changshe", "louluo", {"geju": 11}),  # 豪強：潁川 40 在亂局，推割據、不動潁川
])
def test_training_pushes_the_local_front_by_faction(on, faction, place, squad, moved):
    game = _game(on)
    s = game.state
    s.player.faction = faction
    s.player.location = place
    before = dict(s.world.trends)
    with _win():
        game._squad_encounter(squad)
    changed = {k: v for k, v in s.world.trends.items() if before.get(k) != v and k != "huangjin"}
    assert changed == moved
    assert s.world.trends["huangjin"] == rules.trend_value(s, on, "huangjin")


def test_warlords_push_nothing_where_the_front_is_settled(on):
    game = _game(on)
    s = game.state
    s.player.faction = "haoqiang"
    s.player.location = "guangzong"
    s.world.trends["jizhou"] = 80  # 冀州穩在黃巾手上：不是亂局
    before = dict(s.world.trends)
    assert game.train_trend_push() == {}
    with _win():
        game._squad_encounter("toumu")
    assert s.world.trends == before


def test_training_at_luoyang_pushes_nothing_when_on(on):
    """Review Focus 2：洛陽官道寫的是 front，洛陽沒有戰況——打贏了也什麼都不推。"""
    game = _game(on)
    s = game.state
    s.player.faction = "guan"
    s.player.location = "luoyang_road"
    before = dict(s.world.trends)
    assert game.train_trend_push() == {}
    with _win():
        game._squad_encounter("louluo")
    assert s.world.trends == before


def test_huangjin_stays_the_weighted_value_after_every_kind_of_push(on):
    """Review Focus 3：事件效果、遊歷、虛擬玩家、決戰結果（直接寫賽季、不經 change_trend）、管理者推戰線、
    割據漲落——每一條路之後，存下來的黃巾聲勢都等於三條戰線的加權。"""
    on.scenario.sim_players = on.scenario.sim_players[:1]  # 波才：潁川 +1
    admin = _game(on, "Rayal")
    s = admin.state

    def consistent() -> bool:
        w = s.world.trends
        expected = int(round(w["yingru"] * 0.35 + w["nanyang"] * 0.25 + w["jizhou"] * 0.40, 6) + 0.5)
        return w["huangjin"] == expected == rules.trend_value(s, on, "huangjin")

    s.player.location = "changshe"
    rules.apply_effect(Effect(trend={"front": -7}), s, on, admin.world)  # 潁川 33
    assert consistent()
    s.player.faction = "guan"
    with _win():
        admin._squad_encounter("louluo")  # 32
    assert consistent()
    world.sim_tick(s, on, 1, FixedRandom(0.0))  # 波才 +1：33
    assert consistent()
    battle = battle_instance.BattleInstance(battle_id="huangjin_showdown", outcome_trend_delta={"yingru": -35})
    admin._apply_outcome_trends_and_flags(s.world, battle)
    assert s.world.trends["yingru"] == 0
    assert consistent()
    admin.admin_push_trend("nanyang", 20)
    assert s.world.trends["nanyang"] == 55
    assert consistent()
    for _ in range(24):
        rules.geju_tick(s, on, 1)
    assert consistent()


# ── Task 5：狀態列 ───────────────────────────────────────


def test_status_shows_three_fronts_and_stances(real):
    game = _game(real)
    data = game.status_data()
    assert not {"fronts", "stances", "chaos_band", "stance_notes"} & set(data)  # 開關關著：狀態列照舊
    real.config.season_one = True
    game.state.world.season_one = True  # 開季時才補蓋「開」的章的季：割據沒存過，讀起始值 10
    _set_fronts(game.state, 30, 70, 90)
    data = game.status_data()
    assert data["fronts"] == [
        {"id": "yingru", "name": "潁川汝南", "value": 30, "chaos": False},
        {"id": "nanyang", "name": "南陽", "value": 70, "chaos": False},
        {"id": "jizhou", "name": "冀州", "value": 90, "chaos": False},
    ]
    assert data["stances"] == {"guan": 36, "huang": 64, "haoqiang": 10}  # 10.5＋17.5＋36＝64


# ── FB-065：圖卡標亂局帶、態勢那一行寫出數字是怎麼來的 ──────────────

# 三條戰線的值（潁川汝南、南陽、冀州）→ 在亂局（戰況 35～65）的有幾條
CHAOS_CASES = [((20, 80, 10), 0), ((40, 80, 10), 1), ((40, 50, 10), 2), ((40, 50, 60), 3)]


@pytest.mark.parametrize("fronts, count", CHAOS_CASES)
def test_chaos_fronts_agree_with_what_geju_tick_does(on, fronts, count):
    """畫面寫的「N 條戰線在亂局，割據漸長／漸消」與 geju_tick 讀的是同一份：N 條就是每曆日漲 N 點，N＝0 就是落 1 點。"""
    s = _game(on).state
    _set_fronts(s, *fronts)
    assert [rules.in_chaos(s, on, f) for f in FRONTS] == [v in range(35, 66) for v in fronts]
    chaos = rules.chaos_fronts(s, on)
    assert len(chaos) == count and chaos == [f for f in FRONTS if rules.in_chaos(s, on, f)]
    before = s.world.trends["geju"]
    for _ in range(24):  # 一曆日（players 不傳＝不縮放）
        rules.geju_tick(s, on, 1)
    delta = s.world.trends["geju"] - before
    assert delta == (count if count else -1)
    note = rules.chaos_note(s, on)
    assert note == (f"{count} 條戰線在亂局，割據漸長" if count else "沒有戰線在亂局，割據漸消")
    assert ("漸長" in note) == (delta > 0) and ("漸消" in note) == (delta < 0)


@pytest.mark.parametrize("value, inside", [(34, False), (35, True), (36, True), (64, True), (65, True), (66, False)])
def test_chaos_band_edges_are_included_everywhere(on, value, inside):
    """35 與 65 都算在亂局裡（含兩端）：in_chaos、chaos_fronts、狀態列的標記、割據的漲落、態勢那一行，一個說法。"""
    game = _game(on)
    s = game.state
    _join(game)
    _set_fronts(s, value, 0, 0)  # 南陽與冀州都在 0：穩
    assert rules.in_chaos(s, on, "yingru") is inside
    assert (rules.chaos_fronts(s, on) == ["yingru"]) is inside
    flags = {f["id"]: f["chaos"] for f in game.status_data()["fronts"]}
    assert flags == {"yingru": inside, "nanyang": False, "jizhou": False}
    before = s.world.trends["geju"]
    for _ in range(24):
        rules.geju_tick(s, on, 1)
    assert s.world.trends["geju"] - before == (1 if inside else -1)
    assert game.status_data()["stance_notes"]["haoqiang"] == (
        "1 條戰線在亂局，割據漸長" if inside else "沒有戰線在亂局，割據漸消")


def test_chaos_band_edges_come_from_config(on):
    """亂局帶的兩端讀設定（跟 in_chaos 同一份），狀態列把它送出去，前端不寫死 35／65。"""
    on.config.chaos_low, on.config.chaos_high = 40, 60
    game = _game(on)
    _join(game)
    _set_fronts(game.state, 39, 40, 61)
    data = game.status_data()
    assert data["chaos_band"] == {"low": 40, "high": 60}
    assert [(f["id"], f["chaos"]) for f in data["fronts"]] == [("yingru", False), ("nanyang", True), ("jizhou", False)]
    assert data["stance_notes"]["haoqiang"] == "1 條戰線在亂局，割據漸長"


def test_status_says_what_the_stance_numbers_are_made_of(on):
    game = _game(on)
    _join(game)
    _set_fronts(game.state, 20, 50, 80)  # 只有南陽在亂局
    data = game.status_data()
    assert data["chaos_band"] == {"low": 35, "high": 65}
    assert data["stance_notes"] == {"sum": "三條戰線合計", "haoqiang": "1 條戰線在亂局，割據漸長"}
    assert not any(ch.isdigit() for ch in data["stance_notes"]["sum"])  # 不印權重
    _set_fronts(game.state, 20, 80, 90)
    assert game.status_data()["stance_notes"]["haoqiang"] == "沒有戰線在亂局，割據漸消"
    _set_fronts(game.state, 40, 50, 60)
    assert game.status_data()["stance_notes"]["haoqiang"] == "3 條戰線在亂局，割據漸長"


def test_the_trends_page_gives_the_geju_note_the_same_wording(on):
    game = _game(on)
    _join(game)
    s = game.state
    _set_fronts(s, 40, 50, 90)
    text = game.trends_text()
    assert "地方豪強割據的程度" in text  # 劇本寫的說明照舊
    assert "2 條戰線在亂局，割據漸長" in text
    assert game.status_data()["stance_notes"]["haoqiang"] in text  # 跟江湖頁同一句
    _set_fronts(s, 10, 90, 90)
    text = game.trends_text()
    assert "沒有戰線在亂局，割據漸消" in text and "戰線在亂局，割據漸長" not in text
    # 這句話跟在割據那一段裡，不跑到別的線底下
    assert "在亂局" not in text[: text.index("豪強割據")]


def test_the_trends_page_is_unchanged_with_the_switch_off(real):
    game = _game(real)
    assert "在亂局" not in game.trends_text()
    assert "stance_notes" not in game.status_data() and "chaos_band" not in game.status_data()


@pytest.mark.parametrize("faction", [None, "guan", "huang", "haoqiang"])
def test_chaos_and_stance_notes_are_the_same_for_every_faction(on, faction):
    """亂局與態勢是全服公開的戰況，不分陣營、散人也看得到：誰看都一樣（沒有別陣營的資訊混進來）。"""
    game = _game(on)
    _join(game)
    game.state.player.faction = faction
    _set_fronts(game.state, 40, 50, 90)
    data = game.status_data()
    assert [f["chaos"] for f in data["fronts"]] == [True, True, False]
    assert data["stance_notes"]["haoqiang"] == "2 條戰線在亂局，割據漸長"


# ── FB-065 M1：名冊空著時，亂局那一句不能說割據在長 ──────────────

EMPTY_ROSTER_NOTE = "2 條戰線在亂局，但還沒有人投靠，割據暫時不動"


def test_an_empty_roster_says_the_geju_is_not_moving(on):
    """geju_tick 的漲速乘人數係數，沒人投靠就是 0：態勢那一行與見聞→大勢的現況，都不能說「漸長」。"""
    game = _game(on)
    _set_fronts(game.state, 40, 50, 90)  # 南陽、潁川在亂局
    assert game.status_data()["stance_notes"]["haoqiang"] == EMPTY_ROSTER_NOTE
    text = game.trends_text()
    assert f"現況：{EMPTY_ROSTER_NOTE}。" in text and "割據漸長" not in text


def test_one_player_on_the_roster_makes_the_note_say_the_geju_grows_again(on):
    game = _game(on)
    _join(game)
    _set_fronts(game.state, 40, 50, 90)
    assert game.status_data()["stance_notes"]["haoqiang"] == "2 條戰線在亂局，割據漸長"
    assert "現況：2 條戰線在亂局，割據漸長。" in game.trends_text()


def test_no_chaos_still_says_the_geju_falls_with_an_empty_roster(on):
    """回落不乘人數係數：名冊空著、沒有戰線在亂局，割據照樣一天落一點，說明寫漸消。"""
    game = _game(on)
    _set_fronts(game.state, 20, 80, 90)
    assert game.status_data()["stance_notes"]["haoqiang"] == "沒有戰線在亂局，割據漸消"
    assert "現況：沒有戰線在亂局，割據漸消。" in game.trends_text()


def test_the_roster_follows_the_store_when_the_note_is_drawn(on):
    """名冊人數是每次畫面現查的（跟 advance_world_state 同一個算式：全服各陣營人數加總），人一投靠說明就跟著變。"""
    game = _game(on)
    _set_fronts(game.state, 40, 50, 90)
    assert game.status_data()["stance_notes"]["haoqiang"] == EMPTY_ROSTER_NOTE
    _join(game)
    assert game.status_data()["stance_notes"]["haoqiang"] == "2 條戰線在亂局，割據漸長"


@pytest.mark.parametrize("players", [None, 0, 1, 15, 40])
@pytest.mark.parametrize("fronts, count", CHAOS_CASES)
def test_the_geju_note_follows_the_same_per_day_change_as_geju_tick(on, fronts, count, players):
    """說明讀的是 geju_tick 用的那個每曆日變動（rules.geju_per_day）：說漸長就真的在漲，說暫時不動就真的一點不動，
    說漸消就真的在落；players 不傳（None）＝不縮放，照舊。"""
    s = _game(on).state
    _set_fronts(s, *fronts)
    per_day = rules.geju_per_day(s, on, players)
    before = s.world.trends["geju"]
    for _ in range(24):  # 一曆日
        rules.geju_tick(s, on, 1, players=players)
    delta = s.world.trends["geju"] - before
    moved = delta + s.world.trend_accum.get("geju", 0.0)  # 不足一點的累積在 trend_accum：整點加零頭就是這一曆日實際的變動
    note = rules.chaos_note(s, on, players)
    assert moved == pytest.approx(per_day)
    if not count:
        assert per_day == -1 and note == "沒有戰線在亂局，割據漸消"
    elif players == 0:
        assert per_day == 0 and delta == 0
        assert note == f"{count} 條戰線在亂局，但還沒有人投靠，割據暫時不動"
    else:
        assert per_day > 0 and note == f"{count} 條戰線在亂局，割據漸長"


def test_a_pure_call_without_the_roster_keeps_the_unscaled_note(on):
    """沒給名冊人數（純函式呼叫）＝不知道，照設計的速度：說漸長，跟以前一字不差。"""
    s = _game(on).state
    _set_fronts(s, 40, 50, 90)
    assert rules.chaos_note(s, on) == "2 條戰線在亂局，割據漸長"


def test_a_geju_that_cannot_rise_for_another_reason_does_not_blame_the_roster(on):
    """設定把每條戰線的漲速調成 0（名冊有人）：割據一樣不動，但不能說「還沒有人投靠」。"""
    on.config.geju_chaos_per_day = 0
    s = _game(on).state
    _set_fronts(s, 40, 50, 90)
    note = rules.chaos_note(s, on, players=5)
    assert "割據漸長" not in note and "還沒有人投靠" not in note and "割據不動" in note


def test_switch_on_but_season_unstamped_behaves_like_switch_off(real):
    """Review Focus 1(a)：開關打開時 beta 那一季還在跑（章是「關」）——一切照 beta：黃巾聲勢不跳成加權值、戰線都算
    黃巾聲勢、遊歷推黃巾聲勢、推黃巾聲勢不丟例外、狀態列、地圖、大勢頁照舊。新規則等開關打開後開的下一季。"""
    real.scenario.sim_players = []
    game = _game(real)
    s = game.state
    real.config.season_one = True
    assert s.world.season_one is False and not rules.season_one(real, s.world)
    world.advance_world_state(s.world, real, 3600, random.Random(0))
    assert s.world.trends == {"huangjin": 25, "yuxi": 0}  # 沒有重算成 45、沒有割據
    assert rules.trend_value(s, real, "huangjin") == 25
    assert rules.resolve_trend(real, s.world, "front", "changshe") == "huangjin"
    s.player.faction = "guan"
    s.player.location = "changshe"
    assert game.train_trend_push() == {"huangjin": -1}
    rules.change_trend(s, real, "huangjin", 5)  # 照 beta 推得動
    assert s.world.trends["huangjin"] == 30
    assert "fronts" not in game.status_data() and "stances" not in game.status_data()
    regions = {r.id: atlas.region_trends(s, real, r) for r in real.map.regions}
    assert regions["jizhou"] == [("黃巾聲勢", 30)] and regions["luoyang"] == []
    assert "潁川汝南" not in game.trends_text()


# ── Task 6：假人往輸得最多的戰線走 ─────────────────────────


def _join_home(content, faction_id):
    """開關關著時假人的地盤（T1 之前的算法）：投靠點與相鄰的地點。"""
    join_at = next(f for f in content.scenario.factions if f.id == faction_id).join_at
    return set(join_at) | {n for loc in join_at for n in content.locations[loc].connections}


def test_bot_heads_to_the_losing_front(real):
    game = _game(real)
    guan, huang, warlord = (
        BotProfile(personality="普通", seed=1, faction=f, season_number=1) for f in ("guan", "huang", "haoqiang")
    )
    assert bot_policy._home(game, guan) == _join_home(real, "guan")  # 開關關著：照舊
    real.config.season_one = True
    assert bot_policy._home(game, guan) == _join_home(real, "guan")  # 這一季沒蓋「開」的章：照舊
    game.state.world.season_one = True
    _set_fronts(game.state, 30, 35, 80)  # 官軍在冀州輸得最多；黃巾在潁川輸得最多
    home = bot_policy._home(game, guan)
    assert {"guangzong", "julu_altar", "zhuo_county"} <= home and "changshe" not in home
    assert {rules.front_of(real, loc) for loc in home} == {"jizhou"}
    home = bot_policy._home(game, huang)
    assert {"changshe", "huangjin_camp"} <= home
    assert {rules.front_of(real, loc) for loc in home} == {"yingru"}
    assert bot_policy._home(game, warlord) == _join_home(real, "haoqiang")  # 豪強對戰線沒有目標：照投靠點


def test_bot_far_from_the_losing_front_takes_the_step_toward_it(real):
    """離戰線還遠的假人（官軍在南陽宛城，冀州輸最多）：只有「往那條戰線路程最近的地點走的下一站」拿 HOME_MOVE_SCORE，
    鄰居都不在冀州，光靠「目的地在地盤裡」的一步偏好沒有方向；已經在戰線上、或開關關著，照舊。"""
    real.config.season_one = True
    game = _game(real)
    game.state.world.season_one = True
    _set_fronts(game.state, 30, 35, 80)
    game.state.player.faction = "guan"
    game.state.player.location = "wan_city"
    profile = BotProfile(personality="普通", seed=1, faction="guan", season_number=1)
    jizhou = [loc for loc in real.locations if rules.front_of(real, loc) == "jizhou"]

    def tier(dest):
        """移動選項的分數去掉「遊歷對自己有利」那一份加分，剩下的是 HOME／AWAY 哪一檔（用同一道加法還原，不留浮點誤差）。"""
        value = bot_policy.score(game, next(o for o in game.options(odds=False) if o.id == f"move:{dest}"), profile)
        for base in (bot_policy.HOME_MOVE_SCORE, bot_policy.AWAY_MOVE_SCORE):
            if value in (base, base + bot_policy.TRAIN_MOVE_SCORE):
                return base
        raise AssertionError(f"move:{dest} scored {value}, neither tier")

    hop = bot_policy.next_hop(game, jizhou)
    neighbours = [str(n) for n in real.locations["wan_city"].connections]
    assert hop in neighbours and hop not in bot_policy._home(game, profile)  # 一步偏好看不到它
    assert bot_policy._front_hop(game, profile) == hop and tier(hop) == bot_policy.HOME_MOVE_SCORE
    assert [tier(n) for n in neighbours if n != hop] == [bot_policy.AWAY_MOVE_SCORE] * (len(neighbours) - 1)

    game.state.player.location = "guangzong"  # 已經在冀州：照舊，往戰線上的地點走拿 HOME
    assert bot_policy.next_hop(game, jizhou) is None and bot_policy._front_hop(game, profile) is None
    here = [str(n) for n in real.locations["guangzong"].connections]
    assert any(rules.front_of(real, n) == "jizhou" for n in here)
    for n in here:
        expected = bot_policy.HOME_MOVE_SCORE if rules.front_of(real, n) == "jizhou" else bot_policy.AWAY_MOVE_SCORE
        assert tier(n) == expected

    game.state.player.location = "wan_city"  # 這一季沒蓋章：照舊，只看投靠點一帶，沒有往戰線的下一站
    game.state.world.season_one = False
    assert bot_policy._front_hop(game, profile) is None
    old_home = _join_home(real, "guan")
    for n in neighbours:
        assert tier(n) == (bot_policy.HOME_MOVE_SCORE if n in old_home else bot_policy.AWAY_MOVE_SCORE)


# ── Task 7：事件只推所在戰線 ─────────────────────────────


def test_validate_rejects_effects_on_derived_trend(real):
    """事件效果寫 {"trend": {"huangjin": 3}} 時 validate 報錯：黃巾聲勢由三條戰線合成，要推就寫 front。"""
    real.events["trend_yingchuan_refugees"].choices[0].effect.trend = {"huangjin": 3}
    with pytest.raises(ContentError, match="不能推衍生線 huangjin"):
        validate(real)
