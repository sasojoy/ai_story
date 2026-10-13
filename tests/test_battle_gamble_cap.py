"""放手一搏每邊每回合的名額（Joy 2026-10-13 效能評估：顯卡一次評一句、一句 13～20 秒，二十人一起搏一回合塞不下，
多出來的默默拿保底 40、沒有劇情）：BattleTuning.gamble_per_side，先到先得，A 段開單就佔；滿了輸入框灰掉、只剩三招；
模型失敗或佔太久沒送出就放掉；每回合重新搶，不是冷卻。"""
import random

from conftest import at
from test_engine import _install_battle_def_with_free_text, _join_and_open

from tianxia import battle_instance as bi
from tianxia.models import BattleTuning


def _guan_slots(game, names, now):
    """官軍那一邊多幾個人、各佔一格名額（模型還在評）。"""
    def fill(b):
        for n in names:
            b.participants[n] = bi.BattleParticipant(name=n, faction="guan", neili=100.0, neili_cap=100.0)
            b.round.gamble_slots[n] = now
    game.world.mutate_battle(fill)


def _open(content, game):
    definition = _install_battle_def_with_free_text(content)
    return definition, _join_and_open(content, game, definition)


def test_the_fourth_on_a_side_gets_only_the_three_moves(content, game):
    _, now = _open(content, game)
    _guan_slots(game, ["甲", "乙", "丙"], now)
    with at(game, now):
        full = bi.gamble_full_line(3)
        assert full == "這一回合我方已有三人放手一搏，只能出三招。"
        assert game.battle_free_text_prompt() is None and game.battle_free_text_full() == full
        assert game.battle_text_request("火燒連營") == [f"（{full}）"]
        assert game.submit_battle_custom_action("火燒連營", 50) == [f"（{full}）"]
        assert len(game.options()) == 3  # 三招照出
        assert "沈浪" not in game.world.get_battle().round.gamble_slots


def test_the_cap_is_per_side(content, game):
    _, now = _open(content, game)
    def huang(b):
        for n in ("甲", "乙", "丙"):
            b.participants[n] = bi.BattleParticipant(name=n, faction="huang", neili=100.0, neili_cap=100.0)
            b.round.gamble_slots[n] = now
    game.world.mutate_battle(huang)
    with at(game, now):
        assert game.battle_free_text_prompt() is not None and game.battle_free_text_full() is None


def test_the_ticket_takes_the_slot_and_a_failed_model_call_gives_it_back(content, game):
    _, now = _open(content, game)
    _guan_slots(game, ["甲", "乙"], now)
    with at(game, now):
        request = game.battle_text_request("火燒連營")
        assert not isinstance(request, list)
        assert game.world.get_battle().round.gamble_slots["沈浪"] == now
    battle = game.world.get_battle()
    assert bi.gamble_full(battle, "甲", content.config.battle, now, game._gamble_hold_seconds()) is False  # 自己佔著的照搶得到
    game.world.mutate_battle(lambda b: b.participants.__setitem__(
        "丁", bi.BattleParticipant(name="丁", faction="guan", neili=100.0, neili_cap=100.0)))  # 第四個，還沒佔
    assert bi.gamble_full(game.world.get_battle(), "丁", content.config.battle, now, game._gamble_hold_seconds())
    game.release_battle_gamble()
    assert "沈浪" not in game.world.get_battle().round.gamble_slots
    assert not bi.gamble_full(game.world.get_battle(), "丁", content.config.battle, now, game._gamble_hold_seconds())


def test_the_holder_submits_even_when_the_others_filled_up_meanwhile(content, game):
    _, now = _open(content, game)
    with at(game, now):
        game.battle_text_request("火燒連營")
    _guan_slots(game, ["甲", "乙", "丙"], now)  # 第四、五、六個也佔了：名額超過，但沈浪先到
    with at(game, now + 10):
        assert game.submit_battle_custom_action("火燒連營", 50) != [f"（{bi.gamble_full_line(3)}）"]
        assert "沈浪" in game.world.get_battle().round.success_rates


def test_a_slot_held_too_long_or_traded_for_a_move_frees_up(content, game):
    _, now = _open(content, game)
    hold = game._gamble_hold_seconds()
    _guan_slots(game, ["甲", "乙"], now)
    _guan_slots(game, ["丙"], now - hold)  # 佔太久沒送出：模型卡住
    with at(game, now):
        assert game.battle_free_text_prompt() is not None
    game.world.mutate_battle(lambda b: b.round.gamble_slots.__setitem__("丙", now))
    with at(game, now):
        assert game.battle_free_text_prompt() is None
    game.world.mutate_battle(lambda b: b.round.pending_actions.__setitem__("丙", "guan_hold"))  # 改出三招
    with at(game, now):
        assert game.battle_free_text_prompt() is not None


def test_a_submitted_gamble_keeps_its_slot_and_a_new_round_clears_them(content):
    three = _install_battle_def_with_free_text(content)
    battle = bi.start_muster(three, now=0)
    for n in ("甲", "乙", "丙", "丁"):
        bi.join_faction(battle, n, "guan", neili_cap=1000)
    bi.join_faction(battle, "戊", "huang", neili_cap=1000)
    bi.close_muster(battle, three, random.Random(0), now=0)
    tuning = BattleTuning()
    for n in ("甲", "乙", "丙"):
        bi.claim_gamble(battle, n, 0)
        battle.round.success_rates[n] = 40  # 評不到拿保底也算用掉一格
    bi.release_gamble(battle, "甲")
    assert bi.gamble_full(battle, "丁", tuning, now=10_000, hold_seconds=75)  # 送出了的不會過期
    battle.round = bi.BattleRound()  # 換回合
    assert not bi.gamble_full(battle, "丁", tuning, now=0, hold_seconds=75)


def test_zero_means_no_cap(content, game):
    content.config.battle.gamble_per_side = 0
    _, now = _open(content, game)
    _guan_slots(game, ["甲", "乙", "丙", "丁"], now)
    with at(game, now):
        assert game.battle_free_text_prompt() is not None and game.battle_free_text_full() is None


def test_a_full_side_greys_the_input_box_out(hints_content, world):
    """名額滿了：輸入框還在、灰掉，底下一行寫為什麼（網頁那一半；沒有 node 就略過）。"""
    import pytest
    import webharness
    if webharness.NODE is None:
        pytest.skip("沒有 node，前端畫面測試略過")
    import server
    from test_seal_web import run

    from tianxia.engine import Game

    game = Game.new(hints_content, "沈浪", rng=random.Random(0), world=world)
    game.skip_tutorial()
    m = server.main_view(game)
    m["free_text"], m["free_text_full"] = None, bi.gamble_full_line(3)
    page = run(m, "return H.pageJianghu();")
    assert 'class="free full"' in page and "disabled" in page and "已有三人放手一搏" in page
    m["free_text_full"] = None
    assert 'id="free-form"' not in run(m, "return H.pageJianghu();")
