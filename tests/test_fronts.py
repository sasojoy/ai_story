"""第一季濃縮版 T1：三條戰線、黃巾聲勢（衍生）、豪強割據，以及第一季的規則沒開（開關關著，或這一季開季時沒蓋「開」的章）時一切照舊。

規則與引擎的測試大多用真實內容（content/）：要驗的就是那三條戰線、起始值與地點歸屬。每個測試自己載一份
（約 0.06 秒），開關在測試裡才打開，不會漏到別的測試。"""
from __future__ import annotations

import random
from pathlib import Path
from unittest import mock

import pytest

from conftest import FixedRandom
from tianxia import atlas, battle_instance, bot_policy, mapview, rules, team, timetable, world
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
    c.config.train_stat_chance = 0.0
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
