"""單人頭目戰（Joy 2026-10-10：「多加一些特殊事件，有種打小 boss 的感覺，也可以算是大事件的單人體驗版，可以放手一搏自訂行動」）。
規則在 tianxia/duel.py，遇上與收場在 Game（_duel_start、_duel_act、duel_gamble、_duel_finish），數字在 Config.duel。"""
from __future__ import annotations

import random

import pytest

from tianxia import battle_instance, bot, bot_policy, duel, rules
from tianxia.content import ContentError, validate
from tianxia.engine import DUEL_FLEE, Game
from tianxia.models import MOVES, DuelBoss, DuelFoe, FactionDef
from tianxia.state import BotProfile

NOW = 1000.0


def _boss(**over) -> DuelBoss:
    data = dict(
        id="lake_boss", locations=["lake"], difficulty=30, rounds=3, exp=40, silver=30, xinde=10, fame=1, drops=["gang_1"],
        foes=[
            DuelFoe(side="huang", name="段鐵頭", title="黃巾小帥", intro="他扛著斧頭攔路。", win="他跑了。", lose="你被拍進泥裡。"),
            DuelFoe(side="guan", name="韓稜", title="官軍督伯", intro="他按著刀柄。", win="他讓開了。", lose="他放你走了。"),
        ],
    )
    data.update(over)
    return DuelBoss(**data)


@pytest.fixture
def setup(content, world):
    content.config.auto_open_first_season = True
    content.config.train_event_chance = 0.0
    content.scenario.factions = [
        FactionDef(id="guan", name="官軍", join_at=["town"]),
        FactionDef(id="huang", name="黃巾", join_at=["town"]),
    ]
    content.duels = {"lake_boss": _boss()}
    game = Game.new(content, "沈浪", rng=random.Random(0), world=world)
    game.client = None
    rules.learn_skill(game.state, content, "fist")
    game.state.player.location = "lake"
    game.state.player.stamina = 200.0
    game.sync(NOW)
    return content, game


def _meet(game) -> list[str]:
    return game._duel_start(duel.available(game.state, game.content))


def test_only_where_a_boss_lives_and_never_twice_at_once(setup):
    content, game = setup
    assert duel.available(game.state, content).id == "lake_boss"
    game.state.player.location = "town"
    assert duel.available(game.state, content) is None
    game.state.player.location = "lake"
    _meet(game)
    assert duel.available(game.state, content) is None  # 正在打


def test_the_face_follows_your_faction(setup):
    content, game = setup
    boss = content.duels["lake_boss"]
    assert duel.foe_index(boss, None) == 0
    assert duel.foe_index(boss, "guan") == 0
    assert duel.foe_index(boss, "huang") == 1  # 黃巾的人不打黃巾小帥，換成官軍督伯
    game.state.player.faction = "huang"
    msgs = _meet(game)
    assert "韓稜" in msgs[0]


def test_exploring_where_a_boss_lives_can_start_one(setup):
    content, game = setup
    content.config.duel.explore_chance = 1.0
    game.choose("act:explore")
    assert game.state.player.duel is not None
    ids = [o.id for o in game.options()]
    assert ids == [f"duel:{m}" for m in MOVES] + [DUEL_FLEE]
    scene = game.scene_text()
    assert "黃巾小帥・段鐵頭" in scene and "第 1／3 回合" in scene
    assert game.duel_free_text_prompt() and "重傷的是你自己" in game.duel_free_text_note()
    assert not game._idle()
    assert game.travel_refusal("town") == "正跟人交手，先分出勝負或抽身退走"


def test_without_a_boss_exploring_does_not_touch_the_dice(setup):
    """沒有頭目的地點不擲那一下：測試內容與沒有頭目的地方，探索的亂數序列一個都不動。"""
    content, game = setup
    game.state.player.location = "cave"
    before = game.rng.getstate()
    assert duel.available(game.state, content) is None
    other = random.Random()
    other.setstate(before)
    game._explore_weights(content.locations["cave"])
    assert game.rng.getstate() == other.getstate()


def test_reading_him_right_wins_and_pays(setup):
    content, game = setup
    content.config.duel.tell_truth = 1.0  # 架勢都是真的：照剋他的出
    p = game.state.player
    silver, xinde = p.stats.get("silver", 0), p.stats.get("xinde", 0)
    _meet(game)
    while p.duel is not None:
        game.choose(f"duel:{duel.answer_to(p.duel)}")
    record = game.state.battles[0]
    assert record.kind == "duel" and record.tier in ("大勝", "險勝")
    assert len(record.rounds) <= 3 and all(line.startswith("第 ") for line in record.rounds)
    share = content.config.duel.reward_share[record.tier]
    assert p.stats["silver"] == silver + round(30 * share)
    assert p.stats["xinde"] == xinde + round(10 * share)
    assert p.materials.get("gang_1") == 1
    assert "名望 +1" in record.changes
    assert game.state.journal[0].title == "頭目戰・段鐵頭"
    assert game.state.battle_card == record.id


def test_the_pool_damage_comes_back_onto_you(setup):
    content, game = setup
    content.config.duel.tell_truth = 1.0
    p = game.state.player
    before, _ = game._player_hp_and_cap()
    _meet(game)
    while p.duel is not None:
        game.choose(f"duel:{next(m for m in MOVES if duel.counter(m, p.duel.move) < 0)}")  # 一直被剋
    record = game.state.battles[0]
    assert record.tier in ("落敗", "僵持")
    after, _ = game._player_hp_and_cap()
    assert after < before
    assert p.member.injury > 0  # 兩成變內傷，同遊歷
    assert f"氣血 -{round(before - after)}" in record.changes


def test_a_loss_pays_nothing(setup):
    content, game = setup
    p = game.state.player
    silver = p.stats.get("silver", 0)
    _meet(game)
    game._duel_finish("落敗", "（測試）")
    assert p.stats.get("silver", 0) == silver and not p.materials.get("gang_1")
    assert game.state.battles[0].tier == "落敗"


def test_the_gamble_rolls_on_the_engine_side(setup):
    content, game = setup
    p = game.state.player
    _meet(game)
    msgs = game.duel_gamble("一斧頭劈他腦門", 100, ("沈浪一斧劈中他的腦門。", "沈浪摔了一跤。"))
    assert "沈浪一斧劈中他的腦門。" in msgs[0] and "氣勢 +" in msgs[0]
    assert p.duel.edge > content.config.duel.start
    edge = p.duel.edge
    msgs = game.duel_gamble("翻三個跟斗", 0, ("沈浪翻了三個跟斗。", "沈浪翻到第二個就暈了。"))
    assert "沈浪翻到第二個就暈了。" in msgs[0]
    assert p.duel is None or p.duel.edge <= edge


def test_the_gamble_without_a_story_uses_a_fixed_line(setup):
    content, game = setup
    _meet(game)
    msgs = game.duel_gamble("一斧頭劈他腦門", 100, ("", ""))
    assert msgs[0].startswith("第 1 回合：你放手一搏：「一斧頭劈他腦門」——成了！")


def test_a_stale_rating_is_thrown_away(setup, monkeypatch):
    """C 段重驗：單子是上一回合開的就不用那個分數，在鎖內重評（沒有模型是保底的 40）。"""
    content, game = setup
    _meet(game)
    request = game.duel_text_request("一斧頭劈他腦門")
    assert request.round == 0 and request.title == "黃巾小帥段鐵頭"
    game.choose("duel:固守")
    seen = []

    def rate(client, act, faction, text, name, setting, place):
        seen.append((act.title, faction, text, setting))
        return battle_instance.GambleVerdict(40)

    monkeypatch.setattr(battle_instance, "assess_gamble", rate)
    assert game.state.player.duel is not None  # 一回合推不到 90 或 10
    game.duel_gamble("一斧頭劈他腦門", 100, ("成", "敗"), request=request)
    assert seen == [("黃巾小帥段鐵頭", "散人", "一斧頭劈他腦門", duel.SETTING)]


def test_a_gamble_needs_a_duel_and_some_words(setup):
    content, game = setup
    assert game.duel_text_request("劈他") == ["（此刻無法這麼做。）"]
    _meet(game)
    assert game.duel_text_request("   ") == ["（請先輸入你想做的事。）"]


def test_fleeing_keeps_the_damage_and_files_nothing(setup):
    content, game = setup
    p = game.state.player
    _meet(game)
    game.choose(f"duel:{next(m for m in MOVES if duel.counter(m, p.duel.move) < 0)}")
    assert p.duel is not None
    battles = len(game.state.battles)
    game.choose(DUEL_FLEE)
    assert p.duel is None and len(game.state.battles) == battles
    assert game.state.journal[0].tag == "抽身退走"


def test_a_season_cap_and_a_cooldown(setup):
    content, game = setup
    cfg = content.config.duel
    _meet(game)
    game._duel_finish(None, "走了")
    assert duel.available(game.state, content) is None  # 冷卻
    game.state.world.time += cfg.cooldown_seconds
    _meet(game)
    game._duel_finish(None, "走了")
    game.state.world.time += cfg.cooldown_seconds
    assert duel.available(game.state, content) is None  # 這一季遇過 per_boss_season 次


def test_the_last_round_settles_on_the_edge(setup):
    content, game = setup
    boss, cfg = content.duels["lake_boss"], content.config.duel
    state = game.state
    _meet(game)
    d = state.player.duel
    d.round = boss.rounds
    for edge, tier in ((80, "大勝"), (60, "險勝"), (50, "僵持"), (40, "落敗")):
        d.edge = edge
        assert duel.verdict(d, boss, cfg) == tier
    d.round, d.edge = 1, 95
    assert duel.verdict(d, boss, cfg) == "大勝"
    d.edge, d.hp = 50, 0
    assert duel.verdict(d, boss, cfg) == "落敗"


def test_the_stronger_you_are_the_more_you_push(setup):
    content, game = setup
    boss, cfg, tuning = content.duels["lake_boss"], content.config.duel, content.config.battle
    cfg.luck = 0

    def push(power):
        d = game.state.player.duel.model_copy(deep=True)
        d.power, d.scores, d.move = power, battle_instance.move_scores(tuning, power, None, None), "固守"
        return duel.exchange(d, boss, "固守", cfg, tuning, random.Random(0))[0]

    _meet(game)
    assert push(300) > push(30) > push(1)


def test_server_bots_answer_the_tell_and_never_write(setup):
    content, game = setup
    _meet(game)
    msgs = bot_policy.take_turn(game, BotProfile(personality="普通", seed=1), random.Random(0))
    assert game.state.player.duel is None or game.state.player.duel.round == 1
    assert any(m.startswith("第 1 回合：你") for m in msgs)


def test_the_season_bot_never_flees(setup):
    content, game = setup
    _meet(game)
    rng = random.Random(0)
    for _ in range(50):
        assert bot.pick(game, game.options(odds=False), rng) != DUEL_FLEE


def test_content_checks_the_faces(setup):
    content, _ = setup
    content.duels = {"x": _boss(foes=[DuelFoe(side="huang", name="甲", title="乙", intro="", win="", lose="")])}
    with pytest.raises(ContentError, match="huang 的人挑不到"):
        validate(content)
    content.duels = {"x": _boss(foes=[DuelFoe(side="wei", name="甲", title="乙", intro="", win="", lose="")])}
    with pytest.raises(ContentError, match="未知的陣營 wei"):
        validate(content)
    content.duels = {"x": _boss(locations=["nowhere"])}
    with pytest.raises(ContentError, match="nowhere"):
        validate(content)


def test_real_content_has_bosses_for_everyone(real):
    assert len(real.duels) >= 4
    for boss in real.duels.values():
        for faction in real.scenario.factions:
            assert boss.foes[duel.foe_index(boss, faction.id)].side != faction.id
