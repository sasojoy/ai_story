"""龍頭上陣（Joy 2026-10-17 第 2 條「大決戰雙方龍頭武將應該要參與且有份量」）：開集結派那條戰線上的大勢人物上陣、
每回合喊一招主將令、照份量出手、被集火與點名打得到、敗走推戰局、收場扣聲威。"""
from __future__ import annotations

import random

import pytest

from conftest import FixedRandom, real_content
from tianxia import battle_instance as bi
from tianxia import figures, generals
from tianxia.models import MOVES, BattleAct, BattleDef, BattleFaction, BattleOption, BattleOutcome, BattleTuning, FreeTextGamble
from tianxia.state import GameState, PlayerState
from tianxia.world_state import fresh_season

CODES = {"強攻": "strong", "固守": "hold", "奇襲": "raid"}
WIN = FixedRandom(0.0)


@pytest.fixture
def d() -> BattleDef:
    options = [
        BattleOption(text=f"{side}{move}", tag=f"{side}_{CODES[move]}", faction=side, move=move)
        for side in ("guan", "huang") for move in MOVES
    ] + [BattleOption(text="放手一搏", tag=f"{side}_reckless", faction=side, free_text=True) for side in ("guan", "huang")]
    return BattleDef(
        id="g", name="龍頭之戰",
        factions=[BattleFaction(id="guan", name="官軍"), BattleFaction(id="huang", name="黃巾")],
        acts=[BattleAct(id="a1", title="對陣", text="兩軍對陣。", goal="推動戰局", options=options)],
        rounds_per_act=9, decisive_margin=49,
        outcomes=[BattleOutcome(faction="guan", title="收場", text="戰罷。")],
        free_text_gamble=FreeTextGamble(side_trend_cap=100),
    )


def _battle(definition, people, chiefs=()):
    """people：[(名號, 陣營)]，三招份量 50、氣血 1000；chiefs：[(名字, 陣營, 份量, 池子)]。"""
    battle = bi.start_muster(definition, now=0)
    for name, side in people:
        bi.join_faction(battle, name, side, neili_cap=1000, scores={m: 50.0 for m in MOVES})
    battle.commanders = [
        bi.Commander(fid=f"f{i}", name=name, faction=side, score=score, neili=pool, neili_cap=pool)
        for i, (name, side, score, pool) in enumerate(chiefs)
    ]
    bi.close_muster(battle, definition, random.Random(0), now=0)
    return battle


def _round(battle, definition, actions, rng=WIN, tuning=None):
    for name, act in actions.items():
        side = battle.participants[name].faction
        if isinstance(act, tuple):
            bi.submit_action(battle, name, f"{side}_reckless", text=act[0], success_rate=act[1], stories=("", ""))
        else:
            bi.submit_action(battle, name, f"{side}_{CODES[act]}")
    return bi.resolve_round(battle, definition, rng, now=1, tuning=tuning or BattleTuning())


def test_a_commander_adds_his_weight_to_his_side(d):
    even = _battle(d, [("甲", "guan"), ("乙", "huang")])
    _round(even, d, {"甲": "強攻", "乙": "強攻"})
    assert even.trend == 50
    led = _battle(d, [("甲", "guan"), ("乙", "huang")], chiefs=[("皇甫嵩", "guan", 150.0, 1500.0)])
    led.orders = {"guan": "強攻"}
    _round(led, d, {"甲": "強攻", "乙": "強攻"})
    assert led.trend > 50  # 官軍那一邊多了主將的份量


def test_following_the_order_is_worth_more(d):
    tuning = BattleTuning()
    base = _battle(d, [("甲", "guan"), ("乙", "huang")], chiefs=[("皇甫嵩", "guan", 1.0, 1500.0)])
    base.orders = {"guan": "奇襲"}  # 甲沒照令
    _round(base, d, {"甲": "強攻", "乙": "強攻"}, tuning=tuning)
    obey = _battle(d, [("甲", "guan"), ("乙", "huang")], chiefs=[("皇甫嵩", "guan", 1.0, 1500.0)])
    obey.orders = {"guan": "強攻"}
    _round(obey, d, {"甲": "強攻", "乙": "強攻"}, tuning=tuning)
    assert obey.trend > base.trend


def test_orders_are_called_each_round_and_read_the_enemy(d):
    battle = _battle(d, [("甲", "guan"), ("乙", "huang")], chiefs=[("皇甫嵩", "guan", 150.0, 1500.0)])
    assert set(battle.orders) == {"guan"}  # 開打那一刻就喊了第一回合；黃巾沒有人上陣，沒人喊令
    tuning = BattleTuning()
    tuning.generals.order_read = 1.0
    for _ in range(3):
        _round(battle, d, {"甲": "奇襲", "乙": "奇襲"}, tuning=tuning)
        assert battle.orders["guan"] == "強攻"  # 強攻剋奇襲：看穿對面上一回合出最多的那一招
    assert "皇甫嵩傳令" in bi.order_text(battle, "guan", tuning)


def test_focus_fire_hits_the_commander_and_holders_take_a_share(d):
    tuning = BattleTuning()
    people = [("甲", "guan")] + [(n, "huang") for n in "乙丙丁"]
    battle = _battle(d, people, chiefs=[("皇甫嵩", "guan", 150.0, 1500.0)])
    battle.orders = {"guan": "固守"}
    _round(battle, d, {"甲": "固守", "乙": "強攻", "丙": "強攻", "丁": "強攻"}, tuning=tuning)
    chief = battle.commanders[0]
    want = tuning.focus_per_attacker * 3
    assert chief.neili == pytest.approx(1500 - want * (1 - tuning.generals.guard_per))
    assert battle.participants["甲"].neili < 1000  # 固守的人替他擋了一份


def test_a_commander_falls_and_the_line_swings(d):
    tuning = BattleTuning()
    battle = _battle(d, [("甲", "guan"), ("乙", "huang")], chiefs=[("皇甫嵩", "guan", 1.0, 1500.0)])
    battle.commanders[0].neili = 5.0  # 一回合最多打掉池子的 round_cap，他只剩一口氣
    battle.orders = {"guan": "奇襲"}
    msgs = _round(battle, d, {"甲": "奇襲", "乙": "強攻"}, tuning=tuning)
    chief = battle.commanders[0]
    assert chief.fallen_round == 1 and chief.felled_by == "乙"
    assert battle.participants["乙"].slew == 1
    assert any("皇甫嵩被乙擊退" in m for m in msgs)
    # 甲出奇襲被乙的強攻剋，戰局本來就往黃巾走；敗走另外再推 fall_push
    assert battle.swings[-1].delta <= -tuning.generals.fall_push
    assert bi.caller(battle, "guan") is None and "guan" not in battle.orders


def test_naming_the_commander_in_a_gamble_hits_him(d):
    tuning = BattleTuning()
    battle = _battle(d, [("甲", "guan"), ("乙", "huang")], chiefs=[("皇甫嵩", "guan", 150.0, 1500.0)])
    battle.orders = {"guan": "奇襲"}
    _round(battle, d, {"甲": "奇襲", "乙": ("一箭射向皇甫嵩", 30)}, tuning=tuning)
    chief = battle.commanders[0]
    g = tuning.generals
    assert chief.neili == pytest.approx(1500 - 1500 * min(g.hit_max, g.hit_base + 70 * g.hit_per_risk))
    assert battle.participants["乙"].hits_landed == 1


def _season(content) -> GameState:
    player = PlayerState(name="", location=content.scenario.start_location, stats={}, stamina=0)
    return GameState(player=player, world=fresh_season(content))


def test_pick_takes_the_figures_on_that_front_in_rank_order():
    c = real_content("weekend")
    s = _season(c)
    rows = generals.pick(s, c, c.battles["changshe_fire"])
    assert [(r.name, r.faction, r.rank) for r in rows] == [("皇甫嵩", "guan", 0), ("朱儁", "guan", 1), ("波才", "huang", 0)]
    s.world.figures["bocai"] = figures.state_of(s, c, "bocai").model_copy(update={"prestige": 30})
    weak = generals.pick(s, c, c.battles["changshe_fire"])[2]
    assert weak.score == pytest.approx(rows[2].score * 0.75, abs=0.2)  # 聲威一半，份量剩四分之三


def test_after_battle_dents_prestige_once(world):
    c = real_content("weekend")
    c.config.auto_open_first_season = True
    world.seed_first_season(c)
    if world.season_phase() == "preparing":
        world.open_season(c, 0.0)
    d = c.battles["changshe_fire"]
    battle = world.start_battle(d, 0.0)
    battle.commanders = [bi.Commander(fid="bocai", name="波才", faction="huang", fallen_round=3, felled_by="甲")]
    start = figures.state_of(_season(c), c, "bocai").prestige
    generals.after_battle(world, c, battle)
    season = world.get_season()
    assert season.figures["bocai"].prestige == start - c.config.battle.generals.fall_prestige
    assert any("甲陣前擊退波才" in r.text for r in season.rumors)
    assert battle.commanders[0].settled
    generals.after_battle(world, c, battle)
    assert world.get_season().figures["bocai"].prestige == start - c.config.battle.generals.fall_prestige


def test_the_showdown_scene_shows_the_lineup_and_the_order(world):
    """長社火攻：開集結派皇甫嵩、朱儁、波才上陣；開打之後畫面寫兩邊的陣容與主將令，照令的那一顆按鈕接「・主將令」。"""
    from test_gentry_allied import _game, _showdown

    c = real_content("weekend")
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    game = _game(c, faction="guan")
    _showdown(game)
    assert [x.name for x in game.world.get_battle().commanders] == ["皇甫嵩", "朱儁", "波才"]
    game.choose("battle:join:guan")
    game.now = game.world.get_battle().muster_deadline_real + 1
    game.options()  # 被動追趕：集結時間到了就開打
    battle = game.world.get_battle()
    assert battle.phase == "active" and battle.orders
    scene = game.scene_text()
    assert "主將皇甫嵩" in scene and "傳令" in scene
    assert any(bi.ORDER_MARK in o.label for o in game.options())
