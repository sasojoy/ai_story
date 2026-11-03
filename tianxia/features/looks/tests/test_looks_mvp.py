"""決戰的回合 MVP（mvp.py；Joy 2026-11-03）：放手一搏成了、送出那一刻身上穿著絕招的人裡挑一位，畫面播他的絕招。純展示。"""
from __future__ import annotations

import random

from conftest import real_content
from test_looks import _game
from test_looks_moves import _art, _made, on  # noqa: F401  fixture

from tianxia.battle_instance import BattleInstance, BattleParticipant, BattleRoundRecord
from tianxia.engine import Game
from tianxia.features.looks import actions, moves, mvp
from tianxia.sqlite_world import open_world
from tianxia.world import open_showdown

BATTLE = "changshe_fire"
ULT = {"move": "m7", "name": "大佛一掌", "look": "moying", "weapon": "劍"}


def _instance(names, won_now):
    b = BattleInstance(battle_id="x", phase="active", round_number=3, record_id=9)
    for n in names:
        b.participants[n] = BattleParticipant(name=n, faction="guan", neili=100, neili_cap=100, gambles_won=won_now.get(n, 0))
    b.rounds.append(BattleRoundRecord(act_index=0, round_number=3, resolved_real=0.0, trend_after=50, custom_texts={"甲": "一掌拍下"}))
    return b


def test_only_a_won_gamble_with_a_move_counts_and_the_riskier_one_is_picked():
    b = _instance(["甲", "乙", "丙", "丁"], {"甲": 1, "乙": 1, "丙": 0, "丁": 1})
    ults = {"甲": ULT, "乙": dict(ULT, move="m8"), "丙": dict(ULT, move="m9")}  # 丁沒穿絕招、丙沒成
    pick = mvp.crown(b, ults, {"甲": 40, "乙": 25, "丙": 5}, {})
    assert pick is not None and pick.name == "乙" and pick.move == "m8" and pick.round == 3  # 乙成功率比較低（比較險）
    assert b.rounds[-1].mvp == "乙" and b.mvps == [pick]


def test_a_tie_is_broken_the_same_way_every_time_and_nobody_means_no_mvp():
    names = ["甲", "乙", "丙"]
    picks = {mvp.crown(_instance(names, dict.fromkeys(names, 1)), dict.fromkeys(names, ULT), {}, {}).name for _ in range(5)}
    assert len(picks) == 1  # 一樣險照雜湊：每次（每個看的人）都同一位
    b = _instance(["甲"], {"甲": 1})
    assert mvp.crown(b, {"甲": ULT}, {}, {"甲": 1}) is None  # 這一回合沒有多成一次
    assert mvp.crown(b, {}, {}, {}) is None and b.mvps == [] and b.rounds[-1].mvp == ""
    assert "mvps" not in b.model_dump(mode="json")  # 沒人當過：JSON 跟加這一欄之前一樣


def test_crowned_adds_the_line_and_latest_only_shows_the_round_just_settled():
    b = _instance(["甲"], {"甲": 0})
    b.round_number = 2
    b.round.ults["甲"] = ULT

    def resolve():
        b.round_number = 3
        b.participants["甲"].gambles_won = 1
        return ["這一回合官軍佔了上風。"]

    msgs = mvp.crowned(b, resolve)
    assert msgs[-1] == "★ 本回合 MVP：甲，絕招「大佛一掌」" and b.rounds[-1].messages[-1] == msgs[-1]
    shown = mvp.latest(b)
    assert shown["name"] == "甲" and shown["move"] == "m7" and shown["look"] == "moying" and shown["text"] == "一掌拍下"
    b.round_number = 4  # 下一回合沒人當選：不再演舊的
    assert mvp.latest(b) is None


def test_battle_ult_needs_a_worn_move_with_a_scene(on):  # noqa: F811
    game = _game(on)
    assert actions.battle_ult(game) is None
    _art(game)
    pid = _made(on, game)
    ult = actions.battle_ult(game)
    assert ult["move"] == moves.move_id(pid) and ult["name"] and ult["weapon"] == ""


def test_a_won_gamble_in_a_real_showdown_crowns_the_player(monkeypatch):
    c = real_content("week7")
    c.config.auto_open_first_season = True
    game = Game.new(c, "甲客", rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.faction, p.location = "guan", "changshe"
    p.tutorial_step = len(c.tutorial.steps)
    game.sync(game.now)
    open_showdown(game.world, c, BATTLE, game.now)
    game.choose("battle:join:guan")
    if any(o.id == "battle:escort:none" for o in game.options()):
        game.choose("battle:escort:none")
    game.world.mutate_battle(lambda b: setattr(b, "muster_deadline_real", -1.0))
    game.options()
    assert game.world.get_battle().phase == "active"
    assert "battle_mvp" not in game.feature_status()
    monkeypatch.setattr(actions, "battle_ult", lambda ctx: dict(ULT))
    game.submit_battle_custom_action("從背後放火燒營", llm_rate=100)
    battle = game.world.get_battle()
    assert [m.name for m in battle.mvps] == ["甲客"] and battle.mvps[0].text == "從背後放火燒營"
    shown = game.feature_status()["battle_mvp"]
    assert shown["move"] == "m7" and shown["round"] == battle.round_number and shown["faction"] == "guan"
    (record,) = game.world.battle_rounds(battle.record_id)
    assert record.mvp == "甲客" and record.messages[-1] == "★ 本回合 MVP：甲客，絕招「大佛一掌」"
