"""本命戰法第二批：對手方的戰法、自己挑招的仗（頭目戰、擂台、奪璽單挑）一回合一回合的戰法、決戰裡只算自己身上的那幾種。"""
from __future__ import annotations

import random

import pytest
from conftest import real_content

from tianxia import battle_instance, duel, rules, tactics
from tianxia.engine import Game
from tianxia.models import BEATS, MOVES, DuelBoss, DuelFoe, FactionDef
from tianxia.state import PLAYER

NOW = 1000.0


def _only(content, skill_id, who="你", key=PLAYER, **params):
    tactic = content.skills[skill_id].tactic.model_copy(update=params)
    return tactics.Holder(who=who, key=key, skill=skill_id, figure=tactics.figure_of(content, skill_id), tactic=tactic)


def _ctx(**kw):
    base = {"foe": "對手", "our_agility": 5.0, "foe_agility": 5.0, "team": [PLAYER]}
    return tactics.Ctx(**(base | kw))


def _bout(a_holders, b_holders):
    a = tactics.side_for(a_holders, _ctx()) if a_holders else None
    b = tactics.side_for(b_holders, _ctx(team=[tactics.FOE_KEY])) if b_holders else None
    return tactics.open_bout(a, b, "你", "對手")


# ── 一般的仗：對手那一方的戰法 ──


def test_the_foe_side_fires_its_own_tactics():
    content = real_content()
    t = content.config.tactics
    roar = _only(content, "zhangfei_wugong", who="張飛", key=tactics.FOE_KEY, rate=1.0, params={"stun_pct": 1.0, "turns": 1.0})
    clash = tactics.play(0.0, 100.0, 4, [], _ctx(), t, random.Random(3), foe_holders=[roar])
    assert "長坂一喝" in clash.foe_fired and not clash.fired
    assert all(turn.ours is None for turn in clash.turns)  # 你被定住，出不了手
    assert clash.margin < 0  # 對手的戰法讓你吃虧


def test_without_any_tactics_the_foe_side_changes_nothing():
    t = real_content().config.tactics
    for seed in range(20):
        clash = tactics.play(12.0, 100.0, 4, [], _ctx(), t, random.Random(seed), foe_holders=[])
        assert clash.margin == 12.0 and not clash.foe_fired


def test_challenging_a_figure_brings_his_own_tactics():
    from tianxia import team

    content = real_content()
    figure = next(f for f in content.figures.values() if f.character and content.characters.get(f.character)
                  and content.skills[content.characters[f.character].starting_wugong].tactic is not None)
    squad = content.squads[figure.squad]
    game = Game.new(content, "試刀客", rng=random.Random(0))
    foe = team.foe_tactics(game.state, content, squad, _ctx())
    assert foe is not None and {h.who for h in foe[0]} == {figure.name}
    content.config.tactics.foe_tactics = False
    assert team.foe_tactics(game.state, content, squad, _ctx()) is None


# ── 自己挑招的仗：兩邊的狀態跨回合 ──


def test_no_tactics_on_either_side_opens_no_bout():
    assert tactics.open_bout(None, None, "你", "對手") is None
    assert tactics.open_bout(tactics.side_for([], _ctx()), None, "你", "對手") is None


def test_a_stun_takes_away_your_move_this_round():
    content = real_content()
    roar = _only(content, "zhangfei_wugong", who="張飛", key=tactics.FOE_KEY, rate=1.0, params={"stun_pct": 1.0, "turns": 1.0})
    bout = _bout([], [roar])
    step = tactics.step(bout, "強攻", "固守", 50.0, content.config.tactics, random.Random(0), b_auto=True)
    assert step.a_move is None and not step.b_hit and step.push < 0
    assert any(line.startswith("〔長坂一喝〕") for line in step.lines)


def test_a_disarm_locks_strong_attack_next_round_and_the_menu_says_so():
    content = real_content()
    t = content.config.tactics
    disarm = _only(content, "liubei_wugong", who="劉備", key=tactics.FOE_KEY, rate=1.0)
    bout = _bout([], [disarm])
    mine = "奇襲"
    his = tactics.answer_to(mine)  # 他剋中你，乘勢卸你的勁
    step = tactics.step(bout, mine, his, 50.0, t, random.Random(0))
    assert step.beat < 0
    tactics.close_round(bout, step.push, t, random.Random(0))
    lock = tactics.locks(bout, "a")
    assert "強攻" in lock.no_moves
    assert "卸勁" in tactics.status_text(bout, "a")
    nxt = tactics.step(bout, "強攻", "固守", 50.0, t, random.Random(1))
    assert nxt.a_move != "強攻"  # 送了強攻也使不出來，換一招
    assert any("使不出強攻" in line for line in nxt.lines)


def test_the_ward_reflects_a_control_back_onto_its_caster():
    content = real_content()
    t = content.config.tactics
    ward = _only(content, "caocao_neigong", rate=1.0, params={"turns": 2.0, "reflect_pct": 1.0})
    roar = _only(content, "zhangfei_wugong", who="張飛", key=tactics.FOE_KEY, rate=1.0, params={"stun_pct": 1.0, "turns": 1.0})
    bout = _bout([ward], [roar])
    step = tactics.step(bout, "強攻", "固守", 50.0, t, random.Random(0))
    assert step.a_move == "強攻" and step.b_move is None
    assert any("反彈回去" in line for line in step.lines)


def test_divine_save_only_rolls_when_carried():
    content = real_content()
    sure = _only(content, "zhangmancheng_wugong", rate=1.0, params={"chance_pct": 1.0})
    assert tactics.divine_save([sure], random.Random(0)) is sure
    rng = random.Random(5)
    before = rng.getstate()
    assert tactics.divine_save([], rng) is None and rng.getstate() == before
    assert tactics.divine_line(sure).startswith("〔神上使〕")


# ── 頭目戰：帶著本命戰法時開一場 bout ──


@pytest.fixture
def boss_game(content, world):
    content.config.auto_open_first_season = True
    content.config.train_event_chance = 0.0
    content.scenario.factions = [FactionDef(id="guan", name="官軍", join_at=["town"]),
                                 FactionDef(id="huang", name="黃巾", join_at=["town"])]
    content.duels = {"lake_boss": DuelBoss(
        id="lake_boss", locations=["lake"], difficulty=30, rounds=3, exp=40, silver=30, xinde=10, fame=1, drops=["gang_1"],
        foes=[DuelFoe(side="huang", name="段鐵頭", title="黃巾小帥", intro="他扛著斧頭攔路。", win="他跑了。", lose="你被拍進泥裡。"),
              DuelFoe(side="guan", name="韓稜", title="官軍督伯", intro="他按著刀柄。", win="他讓開了。", lose="他放你走了。")],
    )}
    game = Game.new(content, "沈浪", rng=random.Random(0), world=world)
    game.client = None
    rules.learn_skill(game.state, content, "fist")
    game.state.player.location = "lake"
    game.state.player.stamina = 200.0
    game.sync(NOW)
    return content, game


def _arm(content, skill_id, kind_from):
    """測試內容沒有本命武學：把真內容裡的一門戰法掛到測試武學上。"""
    tactic = real_content().skills[kind_from].tactic.model_copy(update={"rate": 1.0})
    content.skills[skill_id] = content.skills[skill_id].model_copy(update={"tactic": tactic})


def test_a_duel_without_tactics_opens_no_bout(boss_game):
    content, game = boss_game
    game._duel_start(duel.available(game.state, content))
    assert game.state.player.duel.bout is None


def test_a_duel_with_tactics_fires_them_each_round(boss_game):
    content, game = boss_game
    _arm(content, "fist", "sunjian_wugong")  # 先登斬將：起手、每回合都發
    game._duel_start(duel.available(game.state, content))
    bout = game.state.player.duel.bout
    assert bout is not None and bout.a.holders
    msgs = game.choose("duel:強攻")
    assert any("〔先登斬將〕" in line for line in msgs)
    assert game.state.player.duel is None or game.state.player.duel.bout.round == 1


# ── 決戰：只算自己身上的那幾種 ──


def test_war_kinds_skip_controls_on_the_enemy():
    content = real_content()
    t = content.config.tactics
    side = tactics.side_for([_only(content, "zhangfei_wugong", rate=1.0, params={"stun_pct": 1.0, "turns": 1.0})], _ctx())
    out = tactics.war_round(side, "強攻", 0, 1, 50.0, 1.0, t, random.Random(0))
    assert out.lines == [] and out.force == 1.0  # 長坂一喝是對單一對手的，決戰裡不發


def test_war_vanguard_adds_weight():
    content = real_content()
    t = content.config.tactics
    side = tactics.side_for([_only(content, "sunjian_wugong", rate=1.0)], _ctx())
    out = tactics.war_round(side, "強攻", 0, 1, 50.0, 1.0, t, random.Random(0))
    assert out.force > 1.0 and out.lines and out.lines[0].startswith("〔先登斬將〕")


def _definition():
    from tianxia.models import BattleAct, BattleDef, BattleFaction, BattleOption, BattleOutcome

    codes = {"強攻": "strong", "固守": "hold", "奇襲": "raid"}
    options = [BattleOption(text=m, tag=f"{side}_{codes[m]}", faction=side, move=m) for side in ("guan", "huang") for m in MOVES]
    return BattleDef(
        id="t", name="試陣", factions=[BattleFaction(id="guan", name="官軍"), BattleFaction(id="huang", name="黃巾")],
        acts=[BattleAct(id="a1", title="一", text="開打", goal="推", options=options)], rounds_per_act=9,
        outcomes=[BattleOutcome(faction="guan", title="收場", text="戰罷。")],
    )


def test_a_war_round_with_a_kit_writes_the_line_and_pushes_more():
    content = real_content()
    t = content.config.tactics
    kit = tactics.side_for([_only(content, "sunjian_wugong", who="甲", rate=1.0)], _ctx())
    defn = _definition()
    pushes = []
    for with_kit in (False, True):
        inst = battle_instance.start_muster(defn, now=0)
        battle_instance.join_faction(inst, "甲", "guan", 300.0, scores={m: 50.0 for m in MOVES},
                                     kit=kit.model_copy(deep=True) if with_kit else None)
        battle_instance.join_faction(inst, "乙", "huang", 300.0, scores={m: 50.0 for m in MOVES})
        battle_instance.close_muster(inst, defn, random.Random(0), now=0)
        battle_instance.submit_action(inst, "甲", "guan_strong")
        battle_instance.submit_action(inst, "乙", "huang_strong")
        msgs = battle_instance.resolve_round(inst, defn, random.Random(0), now=1, tactic=t)
        pushes.append(inst.trend - 50)
        if with_kit:
            assert any(line.startswith("官軍這一回合發動本命戰法：〔先登斬將〕") for line in msgs)
            assert "〔先登斬將〕" in inst.participants["甲"].moves[1]
        else:
            assert not any("本命戰法" in line for line in msgs)
    assert pushes[1] > pushes[0]


def test_beats_table_is_what_the_tests_assume():
    assert BEATS["固守"] == "強攻" and tactics.answer_to("奇襲") == "強攻"


# ── 擂台：報名時快照戰法，挑擂時兩邊都打 ──


@pytest.fixture
def ring(content, world):
    from tianxia.characters import CharacterStore

    content.config.auto_open_first_season = True
    content.config.arena.enabled = True
    _arm(content, "fist", "sunjian_wugong")
    for name in ("甲", "乙"):
        game = Game.new(content, name, rng=random.Random(0), world=world)
        game.client = None
        rules.learn_skill(game.state, content, "fist")
        game.state.player.location = "town"
        game.state.player.stamina = 100.0
        game.sync(NOW)
        CharacterStore(world.db).save(game.state)
    return content, world


def _as(content, world, name, act):
    from tianxia.characters import CharacterStore

    state = CharacterStore(world.db).load(name)
    game = Game(content, state, random.Random(0), world)
    game.client = None
    game.sync(NOW)
    msgs = act(game)
    game._save_season()
    CharacterStore(world.db).save(game.state)
    return msgs, game


def test_the_arena_snapshots_the_kit_and_both_sides_fire(ring):
    content, world = ring
    for name in ("乙", "甲"):
        _as(content, world, name, lambda g: g.choose("act:arena") + g.choose("arena:join") + g.choose("arena:back"))
    assert world.get_season().arena["乙"].kit is not None

    def go(g):
        out = g.choose("act:arena") + g.choose("arena:fight:乙")
        assert g.state.player.arena.bout is not None
        assert g.state.player.arena.bout.b.holders  # 分身帶著報名那一刻的戰法
        out += g.choose("arena:強攻")
        return out
    msgs, _game = _as(content, world, "甲", go)
    text = "\n".join(msgs)
    assert text.count("〔先登斬將〕") >= 2  # 兩邊各發一次
