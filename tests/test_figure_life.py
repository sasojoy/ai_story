"""大勢人物擴充第一批（Joy 2026-10-17「歷史武將人數新增多一些，更智能化，像是真的活在這個亂世」）：
每日行事（figure_life.tick）、心事（figures.mood_of）、聲威一天的上限、風聞（figure_life.spread）、華佗坐診。

用真實內容（content/，figure_life 預設開著）；每個測試拿自己的一份複本。"""
from __future__ import annotations

import random

import pytest

from conftest import real_content
from tianxia import figure_life, figures, team, world
from tianxia.engine import Game
from tianxia.state import GameState, PlayerState
from tianxia.world_state import fresh_season


@pytest.fixture
def c():
    c = real_content()
    c.config.affinity_gain_scale = 1.0  # 這裡量的是寫好的情誼數字；歷史武將同行的情誼放慢（Config.affinity_gain_scale）另測（tests/test_companions.py）
    return c


def _season(content) -> GameState:
    player = PlayerState(name="甲", location=content.scenario.start_location, stats={}, stamina=0)
    return GameState(player=player, world=fresh_season(content))


def _turns(s: GameState, content, n: int) -> None:
    """往前推 n 輪每日行事（直接叫 tick，不跑季的其他事）。"""
    step = figure_life.period(content, s.world)
    figure_life.tick(s, content)  # 開季後第一次只記輪數
    for _ in range(n):
        s.world.time += step
        figure_life.tick(s, content)


def test_the_first_tick_only_records_the_turn(c):
    s = _season(c)
    figure_life.tick(s, c)
    assert s.world.life_turn == 0 and s.world.whereabouts == {} and s.world.rumors == []


def test_people_walk_their_haunts_and_the_sworn_brothers_follow_liu_bei(c):
    s = _season(c)
    seen = set()
    for _ in range(30):
        _turns(s, c, 1)
        here = figure_life.where(s, c, "tangzhou")
        assert here in c.characters["tangzhou"].haunts
        seen.add(here)
        brother = figure_life.where(s, c, "liubei")
        assert figure_life.where(s, c, "guanyu") == brother == figure_life.where(s, c, "zhangfei")
    assert len(seen) > 1  # 唐周真的走動了
    assert any("見到了唐周" in r.text for r in s.world.rumors)  # 不是大勢人物的走動是地方傳聞


def test_whereabouts_decide_who_is_here(c):
    s = _season(c)
    s.world.whereabouts["tangzhou"] = "baima_temple"
    assert figures.placed_characters(s, c)["tangzhou"] == "baima_temple"
    assert figure_life.where(s, c, "tangzhou") == "baima_temple"


def test_season_one_figures_do_not_move_themselves(c):
    c.config.season_one = True
    s = _season(c)
    start = {fid: f.location for fid, f in s.world.figures.items()}
    _turns(s, c, 20)
    assert {fid: f.location for fid, f in s.world.figures.items()} == start


def test_untimed_figures_walk_within_their_haunts(c):
    s = _season(c)
    moved = False
    for _ in range(30):
        _turns(s, c, 1)
        loc = figures.state_of(s, c, "bocai").location
        assert loc in c.characters["bocai"].haunts
        moved |= loc != c.figures["bocai"].location
    assert moved


def test_the_switch_off_does_nothing(c):
    c.config.figure_life.enabled = False
    s = _season(c)
    _turns(s, c, 10)
    assert s.world.whereabouts == {} and s.world.rumors == [] and s.world.life_turn == -1
    assert figures.mood_of(s, c, "bocai") is None


def test_a_beaten_figure_is_hurt_and_easier(c):
    s = _season(c)
    base = figures.difficulty(s, c, "bocai")
    figures.defeat(s, c, "bocai", 5)
    assert figures.mood_of(s, c, "bocai") == "負傷"
    prestige = figures.state_of(s, c, "bocai").prestige
    assert figures.difficulty(s, c, "bocai") < base
    s.world.time += figures.mood_span(c, s.world) + 1
    assert figures.mood_of(s, c, "bocai") != "負傷"
    assert figures.state_of(s, c, "bocai").prestige == prestige


def test_an_ally_falling_on_the_same_line_makes_grief(c):
    s = _season(c)
    figures.defeat(s, c, "zhujun", 999)  # 朱儁倒下（同一條潁川汝南線）
    assert figures.mood_of(s, c, "huangfusong") == "悲憤"
    assert figures.mood_of(s, c, "fuxie") == "悲憤"  # 偏將沒有戰線，照所在地點的大區
    assert figures.mood_scale(s, c, "huangfusong") == c.config.figure_life.grief_scale


def test_regen_and_recruits_share_one_daily_cap(c):
    s = _season(c)
    w = s.world
    figures._ensure(s, c, "bocai").prestige = 10
    cap = c.config.figure_life.daily_gain_cap
    figures.recover(s, c, 24 * 30)  # 一個月份量的自然回復，一天之內
    assert figures.state_of(s, c, "bocai").prestige == 10 + cap
    figure_life._recruit(s, c, "bocai")
    assert figures.state_of(s, c, "bocai").prestige == 10 + cap  # 額度用完
    w.time += 86400
    figure_life._recruit(s, c, "bocai")
    assert figures.state_of(s, c, "bocai").prestige == 10 + cap + c.config.figure_life.recruit


def test_beating_a_figure_spreads_to_people_in_that_region(c):
    s = _season(c)
    p = s.player
    p.location = "changshe"
    lines = figure_life.spread(s, c, "beat", "bocai", at="changshe", side="huang", text="在長社打退了波才")
    tuning = c.config.figure_life
    assert p.affinities.get("huangfusong") == tuning.foe_beaten  # 對頭聽了高興
    assert p.affinities.get("bocai") is None  # 被打的本人不算在這裡（_rout 另扣）
    assert p.hearsay["huangfusong"] == ["在長社打退了波才"]
    assert "zhangjiao" not in p.affinities  # 冀州的人聽不到
    assert lines and "情誼 +3" in lines[0]
    assert figure_life.spread(s, c, "beat", "bocai", at="changshe", side="huang", text="又一次") == []  # 一季一次


def test_allies_of_the_beaten_side_cool_off(c):
    s = _season(c)
    s.player.affinities["liupi"] = 20
    figure_life.spread(s, c, "beat", "bocai", at="huangjin_camp", side="huang", text="打退了波才")
    assert s.player.affinities["liupi"] == 20 + c.config.figure_life.ally_beaten


def test_the_prompt_carries_mood_and_hearsay(c):
    s = _season(c)
    figures.defeat(s, c, "bocai", 5)
    s.player.hearsay["bocai"] = ["在長社打退了波才"]
    text = figure_life.prompt_lines(s, c, "bocai")
    assert "負傷" in text and "打退了波才" in text
    c.config.figure_life.enabled = False
    assert figure_life.prompt_lines(s, c, "bocai") == ""


def test_hua_tuo_halves_the_clinic_price_where_he_sits(c):
    game = Game.new(c, "求醫者", rng=random.Random(1))
    game.world.open_season(game.content, now=0.0)
    s = game.state
    s.player.member.injury = 40
    s.player.location = "baima_temple"
    here = team.heal_cost(c, s.player.member, s)
    s.player.location = "yingchuan"
    away = team.heal_cost(c, s.player.member, s)
    assert figure_life.healer_here(s, c) is False
    s.world.whereabouts["huatuo"] = "yingchuan"
    assert team.heal_cost(c, s.player.member, s) < away and figure_life.healer_here(s, c)
    assert here <= away


def test_a_whole_untimed_season_runs_with_people_alive(c):
    w = fresh_season(c)
    from tianxia.world_state import season_length_days

    world.advance_world_state(w, c, season_length_days(w, c) * 86400 + 3600, random.Random(0))
    assert w.ended and w.life_turn > 0
    assert any("移往" in r.text for r in w.rumors)


def test_routing_a_figure_in_the_engine_spreads_the_word(c):
    game = Game.new(c, "挑戰者", rng=random.Random(1))
    game.world.open_season(game.content, now=0.0)
    p = game.state.player
    p.faction = "guan"
    p.location = "huangjin_camp"
    msgs = game._rout("bocai")
    assert any("聽說了這件事" in m for m in msgs)
    assert p.hearsay["liupi"][0].endswith("打退了波才")  # 同一區的劉辟聽說了


def test_untimed_raids_nudge_the_huangjin_trend_by_the_season_scale(c):
    s = _season(c)
    before = s.world.trends["huangjin"]
    for _ in range(40):
        figure_life._raid_front(s, c, "bocai")
    assert s.world.trends["huangjin"] > before  # 黃巾那一方往上推
    assert s.world.trends["huangjin"] - before <= 40 * c.config.drill_push_base_days / 14 + 1  # 14 天的季照季長倍數縮


def test_season_one_raids_are_only_rumors(c):
    c.config.season_one = True
    s = _season(c)
    before = dict(s.world.trends)
    figure_life._raid_front(s, c, "bocai")
    assert s.world.trends == before and s.world.rumors
