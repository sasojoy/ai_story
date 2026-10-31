"""盡頭阻力、季長縮放與事件五折（docs/superpowers/specs/2026-10-14-出陣探索與地盤-design.md 第五節、3.2）。
正式內容；預設是 7 天季（第一季規則開著；21 天季的頂與每日上限自己一套，不乘季長倍數）。"""
from __future__ import annotations

import random

import pytest

from conftest import classic_rules, real_content, third_party_gentry
from tianxia import atlas, figures, orders, push, territory, timetable
from tianxia.engine import Game
from tianxia.models import PushResistance
from tianxia.sqlite_world import open_world
from tianxia.state import Order

TUNING = PushResistance()


def _game(profile="week7", days=None, faction="huang", name="沈浪"):
    c = real_content(profile)
    c.config.auto_open_first_season = True
    if days is not None:
        c.config.season_days = days
    game = Game.new(c, name, rng=random.Random(0), world=open_world())
    game.client = None
    game.state.player.faction = faction
    return game


@pytest.mark.parametrize(("value", "direction", "share"), [
    (50, 1, 1.0), (50, -1, 1.0), (65, 1, 1.0), (35, -1, 1.0),
    (66, 1, 0.5), (85, 1, 0.5), (34, -1, 0.5), (15, -1, 0.5),
    (86, 1, 0.2), (99, 1, 0.2), (14, -1, 0.2), (1, -1, 0.2),
    (90, -1, 1.0), (10, 1, 1.0), (70, -1, 1.0), (30, 1, 1.0),  # 往回拉全額
    (70, 0, 1.0),
])
def test_the_resistance_table(value, direction, share):
    assert push.resistance_share(value, direction, TUNING) == share
    assert push.resistance(value, 4 * direction, TUNING) == pytest.approx(4 * direction * share)


def test_rounding_half_away_from_zero():
    assert [push.round_half_away(x) for x in (1.6, 0.6, 0.4, -0.6, -1.5, 2.5)] == [2, 1, 0, -1, -2, 3]


def test_pushing_deeper_is_resisted_and_pulling_back_is_not():
    game = _game()
    w = game.state.world
    w.trends["yingru"] = 70
    msgs = game.push_trend("yingru", 4, source="duty")
    assert w.trends["yingru"] == 72 and push.RESISTED_LINE in msgs  # 65～85 推一半
    assert game.state.player.contrib == 40  # 貢獻照推的名目量全額記：4 點 × contrib_per_push
    game.state.player.faction = "guan"
    msgs = game.push_trend("yingru", -4, source="duty")
    assert w.trends["yingru"] == 68 and push.RESISTED_LINE not in msgs  # 往回拉全額


def test_the_far_end_moves_two_tenths():
    game = _game()
    game.state.world.trends["yingru"] = 90
    game.push_trend("yingru", 5, source="duty")
    assert game.state.world.trends["yingru"] == 91


def test_repeatable_events_push_the_fronts_at_half_and_one_off_events_in_full():
    game = _game()
    w = game.state.world
    w.trends["yingru"] = 50
    game.push_trend("yingru", 2, source="event")
    assert w.trends["yingru"] == 51
    game.push_trend("yingru", 2, source="event_once")
    assert w.trends["yingru"] == 53
    game.content.config.explore_modes.enabled = False
    game.push_trend("yingru", 2, source="event")
    assert w.trends["yingru"] == 55


def test_the_combined_line_of_a_fourteen_day_season_is_resisted_too():
    game = _game(profile=None, faction="guan")
    w = game.state.world
    assert not w.season_one and w.trends["huangjin"] == 25
    msgs = game.push_trend("huangjin", -2, source="duty")
    assert w.trends["huangjin"] == 24 and push.RESISTED_LINE in msgs


def test_figures_push_less_toward_the_end():
    game = _game()
    s, c, w = game.state, game.content, game.state.world
    assert figures.push_goal(s, c, "bocai") > 0  # 波才：黃巾、潁川汝南、每天一下、第 1 週起
    w.trends["yingru"] = 50
    w.trend_accum.pop("fig:bocai", None)
    figures.tick(s, c, 1)
    at_half = w.trend_accum["fig:bocai"]
    w.trends["yingru"] = 90
    w.trend_accum.pop("fig:bocai", None)
    figures.tick(s, c, 1)
    assert w.trend_accum["fig:bocai"] == pytest.approx(at_half * 0.2)


def test_order_completion_is_resisted_but_the_timetable_is_not():
    game = _game()
    s, c, w = game.state, game.content, game.state.world
    w.trends["yingru"] = 90
    moved, _ = orders.front_push(s, c, "yingru", 8)
    assert moved == 2 and w.trends["yingru"] == 92  # 8 × 0.2 = 1.6 → 2
    timetable._push(s, c, "yingru", 5)  # 時刻表大事照寫好的推
    assert w.trends["yingru"] == 97


def test_the_admin_pushes_in_full():
    game = _game(name="Rayal")
    game.state.world.trends["yingru"] = 90
    game.admin_push_trend("yingru", 8)
    assert game.state.world.trends["yingru"] == 98


def test_the_switches_off_keep_the_old_push():
    game = _game()
    classic_rules(game.content)
    game.state.world.trends["yingru"] = 90
    msgs = game.push_trend("yingru", 4, source="duty")
    assert game.state.world.trends["yingru"] == 94 and push.RESISTED_LINE not in msgs
    game.state.world.trends["yingru"] = 50
    game.push_trend("yingru", 2, source="event")
    assert game.state.world.trends["yingru"] == 52


def test_the_order_of_the_bands_is_checked():
    from tianxia.content import ContentError, validate

    c = real_content()
    c.config.push_resistance.full_within = 40
    with pytest.raises(ContentError, match="push_resistance"):
        validate(c)


def test_pushing_too_far_from_your_own_ground_is_not_called_deep_in_enemy_land():
    """FB-432：在自家控制的地方守、巡哨推過頭，接「此地已穩」，不接「深入敵境」；在別人控制的地方照舊。"""
    from tianxia import territory

    game = _game()
    w = game.state.world
    w.trends["yingru"] = 70
    game.state.player.location = "huangjin_camp"  # 黃巾的大本營
    assert territory.controller(w, game.content, "huangjin_camp") == "huang"
    msgs = game.push_trend("yingru", 4, source="duty")
    assert push.STEADY_LINE in msgs and push.RESISTED_LINE not in msgs
    game.state.player.faction = "guan"
    w.trends["yingru"] = 30
    msgs = game.push_trend("yingru", -4, source="sortie")
    assert push.RESISTED_LINE in msgs and push.STEADY_LINE not in msgs  # 官軍在黃巾的地盤上推


# ── FB-248（2026-10-31 從 tests/core/test_core_loop_fb.py 併進來）────────
# 核心玩法重整第 1 塊 QA 的回饋（docs/superpowers/feedback/試玩回饋.md 的 FB-248～254，PM 2026-10-15 定的修法）。正式內容、週末設定。


def _game_fb248(faction=None, at="yingshui", name="沈浪", content=None):
    c = content or real_content("week7")  # 地盤拔河的舊規則（領地爭奪 PM 2026-10-22 起正式內容打開）
    c.config.jianfa.four_wins = False  # 三陣營四勝利之前的規則（挑邊、改依附算叛投、攪局；測試整理批 1 把這個檔從週末搬到 7 天季，減法季開著）；新規則在 tests/test_four_wins_wiring.py
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    game = Game.new(c, name, rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.faction, p.location, p.stamina = faction, at, float(c.config.stamina_max)
    p.tutorial_step = len(c.tutorial.steps)
    p.visited.add(at)
    return game


# ── FB-248：截糧的地點一律在戰線上，糧隊只在那一處 ─────────────────────


def _intercept(game, faction, location):
    order = Order(id=f"1:{faction}:intercept:x", template="intercept", faction=faction, week=orders.week_of(game.state, game.content),
                  front=territory.line_of(game.content, location), location=location, quota=99, text="")
    game.state.world.orders = [o for o in game.state.world.orders if o.template != "intercept"] + [order]
    return order


def test_fb248_every_intercept_slot_is_a_front_place():
    c = real_content()
    for front, sides in c.orders.slots.items():
        for side, slot in sides.items():
            assert territory.line_of(c, slot.intercept) == front, (front, side, slot.intercept)


def test_fb248_the_intercept_card_names_only_the_place():
    game = _game_fb248("guan", "changshe")
    order = _intercept(game, "guan", "runan_wilds")
    assert atlas.order_how(game.state, game.content, order) == atlas.INTERCEPT_SORTIE.format(place="汝南荒野")
    assert "附近" not in atlas.order_how(game.state, game.content, order)


def test_fb254_separatism_rises_slower_near_the_top_and_falls_in_full():
    """企劃者 2026-10-15：割據往上漲跟戰線同一套分段（65 以下全額、65～85 一半、85 以上兩成），往下落全額；開關同 push_resistance。"""
    from tianxia import rules

    game = _game_fb248("haoqiang", "runan_wilds")
    for value, share in ((40, 1.0), (60, 1.0), (70, 0.5), (90, 0.2)):
        game.state.world.trends[rules.GEJU] = value
        assert rules.geju_resisted(game.state, game.content, 2.0) == 2.0 * share, value
        assert rules.geju_resisted(game.state, game.content, -2.0) == -2.0, value  # 往下落全額
    game.content.config.push_resistance.enabled = False
    assert rules.geju_resisted(game.state, game.content, 2.0) == 2.0


def test_fb254_the_natural_rise_is_resisted():
    """三條戰線都在亂局：割據 90 時一個曆日只漲平常的兩成；60 時照平常。"""
    from tianxia import rules

    game = _game_fb248("haoqiang", "runan_wilds", content=third_party_gentry(real_content("week7")))  # 割據是豪強第三方的規則
    s, c, w = game.state, game.content, game.state.world
    for front in rules.front_ids(c):
        w.trends[front] = 50
    full = rules.geju_per_day(s, c)
    assert full > 0
    w.trends[rules.GEJU], w.trend_accum[rules.GEJU] = 90, 0.0
    rules.geju_tick(s, c, 24 * 10)
    assert w.trends[rules.GEJU] == 90 + int(full * 10 * 0.2 + 1e-9)
    w.trends[rules.GEJU], w.trend_accum[rules.GEJU] = 30, 0.0
    rules.geju_tick(s, c, 24)
    assert w.trends[rules.GEJU] == 30 + int(full + 1e-9)


def test_fb254_a_gentry_push_near_the_top_is_resisted():
    """豪強在亂局的戰線上保境安民推割據 1 點：割據 90 時只推兩成（零頭記著），60 時推滿一點。"""
    from tianxia import rules

    game = _game_fb248("haoqiang", "runan_wilds", content=third_party_gentry(real_content("week7")))  # 豪強是第三方的規則
    w = game.state.world
    w.trends["yingru"] = 50
    w.trends[rules.GEJU], w.trend_accum[rules.GEJU] = 90, 0.0
    game.choose("act:duty")
    assert w.trends[rules.GEJU] == 90 and w.trend_accum[rules.GEJU] < 1
    w.trends[rules.GEJU], w.trend_accum[rules.GEJU] = 60, 0.0
    game.choose("act:duty")
    assert w.trends[rules.GEJU] == 61


def test_fb254_an_opportunity_push_on_separatism_is_resisted_too():
    """機緣交付推割據（豪強的收容流民，推 1 點）：割據 90 時打兩成、四捨五入成 0；60 時推滿。"""
    from tianxia import opportunities, rules

    game = _game_fb248("haoqiang", "runan_wilds", content=third_party_gentry(real_content("week7")))  # 割據是豪強第三方的規則
    opp = next(o for o in game.content.opportunities if o.id == "hao_refugees")
    w = game.state.world
    w.trends[rules.GEJU] = 90
    opportunities._trend_on_done(game.state, game.content, opp, "runan_wilds")
    assert w.trends[rules.GEJU] == 90
    w.trends[rules.GEJU] = 60
    opportunities._trend_on_done(game.state, game.content, opp, "runan_wilds")
    assert w.trends[rules.GEJU] == 60 + opp.accumulate.trend


def _late_season(c, week, geju, fronts=50):
    """週末設定的一季停在第 week 週，割據 geju、三條戰線都在 fronts；回傳（季, 給規則看的 GameState）。"""
    from tianxia import calendar, rules
    from tianxia import world as world_rules
    from tianxia.world_state import fresh_season

    season = fresh_season(c)
    for front in rules.front_ids(c):
        season.trends[front] = fronts
    season.trends[rules.GEJU] = geju
    season.time = calendar.week_start(week, c, season) + 1
    return season, world_rules._season_vehicle(c, season)


def test_fb254_separatism_at_85_is_the_warlords_ending_at_the_finale():
    """季末結算照 evaluate_ending 的先後：割據 ≥85 是群雄並起，黃巾聲勢的門檻排在它前面；割據 84 照態勢比高低（豪強最高是豪強坐大）。"""
    from tianxia import world as world_rules

    c = third_party_gentry(real_content("week7"))  # 群雄並起、豪強坐大是豪強第三方的規則（豪強分屬兩軍見 test_gentry_allied.py）
    for geju, fronts, ending in ((90, 50, "s1_warlords"), (84, 50, "s1_gentry"), (90, 88, "s1_huangtian")):
        _, vehicle = _late_season(c, 12, geju=geju, fronts=fronts)
        assert world_rules.evaluate_ending(vehicle, c).id == ending, (geju, fronts)


def test_fb256_the_legend_line_is_no_longer_than_the_one_that_fit():
    """375 寬的圖例：「⚔ 可出陣攻打」把「打」擠到第二行；出陣的說法不能比原本放得下的「⚔ 可遊歷」那一句長。"""
    from tianxia import mapview

    assert len(mapview.LEGEND_RING_SORTIE) <= len(mapview.LEGEND_RING) and "遊歷" not in mapview.LEGEND_RING_SORTIE
