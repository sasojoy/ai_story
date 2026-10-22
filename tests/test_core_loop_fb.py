"""核心玩法重整第 1 塊 QA 的回饋（docs/superpowers/feedback/試玩回饋.md 的 FB-248～254，PM 2026-10-15 定的修法）。正式內容、週末設定。"""
from __future__ import annotations

import random

from conftest import classic_rules, no_conquest, real_content, third_party_gentry
from tianxia import atlas, orders, territory
from tianxia.engine import Game
from tianxia.sqlite_world import open_world
from tianxia.state import Order


def _game(faction=None, at="yingshui", name="沈浪", content=None):
    c = content or no_conquest(real_content("weekend"))  # 地盤拔河的舊規則（領地爭奪 PM 2026-10-22 起正式內容打開）
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    game = Game.new(c, name, rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.faction, p.location, p.stamina = faction, at, float(c.config.stamina_max)
    p.tutorial_step = len(c.tutorial.steps)
    p.visited.add(at)
    return game


def _sortie(game):
    return next((o for o in game.options() if o.id == "act:train"), None)


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


def test_fb248_the_convoy_stands_only_at_the_intercept_place():
    """官軍截糧汝南荒野那一週：汝南荒野有黃巾糧隊、出陣攻打得到；相鄰的長社（官軍大本營）照舊是守，不變成攻糧隊。"""
    game = _game("guan", "changshe")
    _intercept(game, "guan", "runan_wilds")
    convoy = game.content.orders.convoy_squads["huang"]
    assert orders.extra_enemies(game.state, game.content, "changshe", "guan") == []
    assert _sortie(game).label.startswith("出陣・守")
    game.state.player.location = "runan_wilds"
    assert convoy in orders.extra_enemies(game.state, game.content, "runan_wilds", "guan")
    assert convoy in game._sortie_foes(game.content.locations["runan_wilds"])
    assert orders.win_counts(game.state, game.content, "guan", "runan_wilds")
    assert not orders.win_counts(game.state, game.content, "guan", "changshe")
    assert orders.targets(game.state, game.content, "guan") == ["runan_wilds"]


def test_fb248_the_intercept_card_names_only_the_place():
    game = _game("guan", "changshe")
    order = _intercept(game, "guan", "runan_wilds")
    assert atlas.order_how(game.state, game.content, order) == atlas.INTERCEPT_SORTIE.format(place="汝南荒野")
    assert "附近" not in atlas.order_how(game.state, game.content, order)


def _strike_bounty():
    from tianxia.state import Bounty

    return Bounty(id="b1", kind="strike", faction="guan", week=1, expires=1e12, silver=20, deeds=1, location="yanshan_foot", squad="louluo")


def test_fb249_the_strike_bounty_says_sortie_or_gathering():
    from tianxia import bounties

    c = real_content("weekend")
    line = bounties.how(c, _strike_bounty())
    assert "遊歷" not in line and "燕山腳" in line and "黃巾" in line
    assert bounties.STRIKE_SORTIE in line and bounties.STRIKE_GATHER in line
    c.config.explore_modes.enabled = False
    assert bounties.STRIKE_GATHER not in bounties.how(c, _strike_bounty())
    old = classic_rules(real_content("weekend"))
    assert bounties.how(old, _strike_bounty()) == "到燕山腳遊歷，打贏一場黃巾軍的隊伍"


def test_fb250_a_ranger_on_a_front_sees_why_there_is_no_sortie():
    """散人站在戰線地點（汝南荒野）：出陣那一顆灰著寫真正的原因、底下那一行說投靠之後才有；不在戰線的地方（潁水河畔）照舊沒有那一顆。"""
    from tianxia import sortie

    game = _game(None, "runan_wilds")
    option = _sortie(game)
    assert option is not None and not option.enabled and option.label == f"{sortie.NAME}（{sortie.RANGER_NOTE}）"
    # 一類一顆（正式內容開著）：找素材不打仗，那一行寫練功（FB-420 同一批）；沒蓋章的季照舊寫找素材撞上的仗
    assert game.action_notes([o.id for o in game.options(odds=False)])["act:train"] == sortie.RANGER_LINE_PRECISE
    game.state.world.precise_actions = False
    assert game.action_notes([o.id for o in game.options(odds=False)])["act:train"] == sortie.RANGER_LINE
    assert game.choose("act:train") == ["（此刻無法這麼做。）"]
    assert _sortie(_game(None, "yingshui")) is None


def _map(game):
    from tianxia import mapview

    return mapview.render_map(game.state, game.content)


def test_fb251_the_crossed_swords_mark_where_you_can_attack():
    """⚔ 照地盤畫：此刻歸敵方、能出陣攻的戰線地點才有（官軍看：汝南荒野〔黃巾佔著〕有，長社〔自家大本營〕、荒丘〔不是戰線〕沒有）；
    散人不能出陣，哪裡都沒有。圖例那一句改成出陣的說法。出陣關著時照舊照內容的敵人畫。"""
    from tianxia import mapview

    guan = _game("guan", "changshe")
    svg = _map(guan)
    assert "汝南荒野 ⚔" in svg and "長社 ⚔" not in svg and "荒丘 ⚔" not in svg
    assert "⚔" not in _map(_game(None, "changshe", name="散人甲"))
    legend = mapview.legend_data(guan.state, guan.content)
    assert legend["ring"] == mapview.LEGEND_RING_SORTIE and "遊歷" not in legend["ring"]
    old = _game("guan", "changshe", name="舊規則", content=classic_rules(real_content("weekend")))
    assert "長社 ⚔" in _map(old) and mapview.legend_data(old.state, old.content)["ring"] == mapview.LEGEND_RING


def test_fb251_the_challenge_line_says_the_same_stamina_as_a_sortie():
    from tianxia import howto
    from tianxia.world_state import fresh_season

    c = real_content("weekend")
    page = howto.page(c, fresh_season(c), recruitable=False)
    assert "體力同出陣" in page and "體力同遊歷" not in page
    old = classic_rules(real_content("weekend"))
    assert "體力同遊歷" in howto.page(old, fresh_season(old), recruitable=False)


def _world_lines(game):
    return [r.text for r in game.state.world.rumors if r.layer == "world"]


def test_fb252_taking_a_place_back_reads_as_a_recapture():
    """官軍大營（潁川汝南靠官軍那一頭，門檻 62.5、±5）：推到 70 落入黃巾之手；退回 55，官軍這一季佔過它，寫「官軍收復官軍大營」。
    割據交還、黃巾再拿下一次也是收復。江湖史同一句。"""
    from tianxia import rules

    game = _game("guan", "changshe")
    c, w = game.content, game.state.world
    guan, huang = c.scenario.faction_name("guan"), c.scenario.faction_name("huang")
    territory.update(w, c)  # 這一季第一次算（不發天下大事）：開季的戰況，官軍大營歸官軍
    rules.change_trend(game.state, c, "yingru", 70 - w.trends["yingru"])
    assert territory.FLIP_LINE.format(place="官軍大營", side=huang) in _world_lines(game)
    rules.change_trend(game.state, c, "yingru", 55 - w.trends["yingru"])
    back = territory.RETAKE_LINE.format(place="官軍大營", side=guan)
    assert back in _world_lines(game) and back in [r.text for r in w.chronicle]
    rules.change_trend(game.state, c, "yingru", 70 - w.trends["yingru"])
    assert territory.RETAKE_LINE.format(place="官軍大營", side=huang) in _world_lines(game)


def test_fb253_a_stir_on_a_line_at_fifty_is_greyed_and_costs_nothing():
    """戰線正好 50：攪局推不動，鈕灰著寫原因、底下那一行說等戰局偏了再來；按了不花次數、不花體力。線一偏就又按得下去。"""
    from tianxia import sortie

    game = _game("haoqiang", "runan_wilds", content=third_party_gentry(real_content("weekend")))  # 攪局是豪強第三方的規則
    w, p = game.state.world, game.state.player
    w.trends["yingru"] = 50
    option = _sortie(game)
    assert not option.enabled and option.label == f"{sortie.NAME}・{sortie.MODE_NAMES['stir']}（{sortie.STIR_FLAT}）"
    assert game.action_notes([o.id for o in game.options(odds=False)])["act:train"] == sortie.STIR_FLAT_LINE
    stamina = p.stamina
    assert game.choose("act:train") == ["（此刻無法這麼做。）"]
    assert game.sorties_left() == 5 and p.stamina == stamina
    w.trends["yingru"] = 49
    assert _sortie(game).enabled


def test_fb254_separatism_rises_slower_near_the_top_and_falls_in_full():
    """企劃者 2026-10-15：割據往上漲跟戰線同一套分段（65 以下全額、65～85 一半、85 以上兩成），往下落全額；開關同 push_resistance。"""
    from tianxia import rules

    game = _game("haoqiang", "runan_wilds")
    for value, share in ((40, 1.0), (60, 1.0), (70, 0.5), (90, 0.2)):
        game.state.world.trends[rules.GEJU] = value
        assert rules.geju_resisted(game.state, game.content, 2.0) == 2.0 * share, value
        assert rules.geju_resisted(game.state, game.content, -2.0) == -2.0, value  # 往下落全額
    game.content.config.push_resistance.enabled = False
    assert rules.geju_resisted(game.state, game.content, 2.0) == 2.0


def test_fb254_the_natural_rise_is_resisted():
    """三條戰線都在亂局：割據 90 時一個曆日只漲平常的兩成；60 時照平常。"""
    from tianxia import rules

    game = _game("haoqiang", "runan_wilds", content=third_party_gentry(real_content("weekend")))  # 割據是豪強第三方的規則
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

    game = _game("haoqiang", "runan_wilds", content=third_party_gentry(real_content("weekend")))  # 豪強是第三方的規則
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

    game = _game("haoqiang", "runan_wilds", content=third_party_gentry(real_content("weekend")))  # 割據是豪強第三方的規則
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


def test_fb254_separatism_at_85_no_longer_ends_the_season_early():
    """企劃者 2026-10-15「提前收季只看戰線」：割據 95 到了第 12 週也不提前收季；黃巾聲勢 ≥85 或 ≤15 照舊第 10 週起當場收。"""
    from tianxia import world as world_rules

    c = real_content("weekend")
    _, vehicle = _late_season(c, 12, geju=95)
    assert world_rules.decisive_ending(vehicle, c) is None
    for fronts, ending in ((90, "s1_huangtian"), (10, "s1_pacified")):
        _, vehicle = _late_season(c, 10, geju=95, fronts=fronts)
        assert world_rules.decisive_ending(vehicle, c).id == ending, fronts


def test_fb254_separatism_at_85_is_the_warlords_ending_at_the_finale():
    """季末結算照 evaluate_ending 的先後：割據 ≥85 是群雄並起，黃巾聲勢的門檻排在它前面；割據 84 照態勢比高低（豪強最高是豪強坐大）。"""
    from tianxia import world as world_rules

    c = third_party_gentry(real_content("weekend"))  # 群雄並起、豪強坐大是豪強第三方的規則（豪強分屬兩軍見 test_gentry_allied.py）
    for geju, fronts, ending in ((90, 50, "s1_warlords"), (84, 50, "s1_gentry"), (90, 88, "s1_huangtian")):
        _, vehicle = _late_season(c, 12, geju=geju, fronts=fronts)
        assert world_rules.evaluate_ending(vehicle, c).id == ending, (geju, fronts)


def test_fb254_the_stance_card_says_separatism_waits_for_the_finale():
    """態勢卡（玩法說明「收季：」同一句）：提前收季只寫官軍、黃巾；割據寫季末才判；結局提示不再說豪強「當場收場」。"""
    from tianxia import guide, rules

    c = third_party_gentry(real_content("weekend"))  # 割據那一句是豪強第三方的規則
    season, vehicle = _late_season(c, 3, geju=40)
    note = rules.stance_rule_note(vehicle, c)
    assert note == ("第 10 週起，官軍或黃巾的態勢一到 85，這一季當場收場；"
                    "否則到季末，豪強的態勢在 85 以上是群雄並起，不然比高低。")
    hints = {e.id: e.hint for e in c.scenario.endings}
    assert "當場收場" not in hints["s1_warlords"] and "季末" in hints["s1_warlords"]
    assert "- 群雄並起：到了季末" in guide.quest_text(vehicle, c)


def test_fb255_attacking_a_convoy_on_your_own_ground_does_not_say_it_is_theirs():
    """截糧週在自家佔著的截糧地點（官軍在南陽郊野）出陣是攻打運糧隊：底下那一行不寫「這裡歸別人」，寫運糧隊經過自家地盤。
    別人的地盤照舊寫「這裡歸別人」。"""
    from tianxia import howto

    game = _game("guan", "nanyang_wilds")
    assert territory.controller(game.state.world, game.content, "nanyang_wilds") == "guan"
    _intercept(game, "guan", "nanyang_wilds")
    line = game.action_notes([o.id for o in game.options(odds=False)])["act:train"]
    assert "這裡歸別人" not in line and line.startswith(howto.SORTIE_NOTES["convoy"].split("{")[0])
    game.state.player.location = "huangjin_camp"
    assert game.action_notes([o.id for o in game.options(odds=False)])["act:train"].startswith("這裡歸別人")


def test_fb256_the_legend_line_is_no_longer_than_the_one_that_fit():
    """375 寬的圖例：「⚔ 可出陣攻打」把「打」擠到第二行；出陣的說法不能比原本放得下的「⚔ 可遊歷」那一句長。"""
    from tianxia import mapview

    assert len(mapview.LEGEND_RING_SORTIE) <= len(mapview.LEGEND_RING) and "遊歷" not in mapview.LEGEND_RING_SORTIE


def test_fb257_the_fame_line_does_not_mention_training_when_sorties_are_on():
    from tianxia import howto
    from tianxia.world_state import fresh_season

    c = real_content("weekend")
    season = fresh_season(c)
    line = " ".join(howto.fame_lines(c, season))
    assert "遊歷" not in line and "找事件" in line  # 一類一顆：事件都在找事件（FB-420 同一批）
    season.precise_actions = False  # 沒蓋章的季：出陣開著，戰後事件接在找素材撞上的那一場之後
    line = " ".join(howto.fame_lines(c, season))
    assert "遊歷" not in line and "找素材" in line
    old = classic_rules(real_content("weekend"))
    assert "遊歷之後" in " ".join(howto.fame_lines(old, fresh_season(old)))


def test_fb248_with_the_sortie_off_the_neighbours_still_meet_the_convoy():
    game = _game("guan", "changshe", content=classic_rules(real_content("weekend")))
    _intercept(game, "guan", "runan_wilds")
    assert orders.extra_enemies(game.state, game.content, "changshe", "guan") == [game.content.orders.convoy_squads["huang"]]
