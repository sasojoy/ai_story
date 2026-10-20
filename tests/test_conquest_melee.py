"""領地爭奪裁決 22（企劃者 2026-10-21）：兩軍同時攻同一塊中立地＝三方混戰（計畫第四章 Task 11b）。

中立的守將留著、兩軍都打他；兩軍之間照決戰互打（戰線只算兩軍之間，強攻打得到對面）；一軍打守將的力道乘這一回合開打時戰線往自己偏多少；
守將的池子歸零那一回合打守將打得多的那一軍拿下（一樣多看戰線、再一樣照自己的亂數）；回合打完守將沒倒，守住、照舊中立。散人可以助守。"""
from __future__ import annotations

import pytest

from conquest_kit import announce, conquest_game, go, join
from tianxia import battle_instance, conquest, siege
from tianxia.battle_instance import GUARD

pytestmark = pytest.mark.slow  # 建 Game、載正式內容

NOW = 1_792_000_000.0
SCORES = {"強攻": 60.0, "固守": 60.0, "奇襲": 60.0}
LOC = "yingchuan_wilds"  # 潁川郊野：守將劫道響馬（新天下的中立地；v1 是南陽官道）


def _game(side="guan", name="沈浪", world=None):
    game = go(join(conquest_game("season21", name=name, world=world), side), LOC)
    game.now = NOW
    return game


def _open(game, merged=("guan", "huang"), side="guan"):
    """排一場攻城、此刻開集結（照 world 的路，siege.open_waiting）；回那一場。"""
    slot = announce(game, LOC, side, merged=merged)
    w = game.state.world
    slot.muster_at, slot.at, slot.status = w.time, w.time + 1800, "waiting"
    game._save_season()
    siege.open_waiting(game.world, game.content, NOW)
    game.state.world = game.world.get_season()
    return next(b for b in game.world.get_sieges() if b.siege.slot_id == slot.id)


def _add(game, battle, who: dict[str, str]):
    """名號 → 站哪一格（集結時加入，份量都一樣）。"""
    def fn(b):
        for name, side in who.items():
            battle_instance.join_faction(b, name, side, 300.0, power=100.0, scores=dict(SCORES))
    return game.world.mutate_siege(battle.record_id, fn)


def _start(game, battle):
    """集結截止：照引擎的路開打（Game._tick_siege → _advance_battle_round，守將的池子在這一下照到場人數定）。"""
    game.now = battle.muster_deadline_real + 1
    game._tick_siege(battle)
    return _now(game, battle)


def _now(game, battle):
    return next(b for b in game.world.get_sieges() if b.record_id == battle.record_id)


def _guard(battle):
    return next(c for c in battle.commanders if c.faction == GUARD)


def _round(game, battle, moves: dict[str, str], setup=None, texts: dict[str, tuple[str, int]] | None = None):
    """每個人出一招（三招的名字），texts 是放手一搏（名號 →（字, 成功率））；setup 在送出之前改這一場。結算一回合，收場了就套結果。"""
    d = game._definition_of(battle)
    log: dict[str, list[str]] = {}

    def fn(b):
        if setup is not None:
            setup(b)
        for name, move in moves.items():
            tag = next(o.tag for o in battle_instance.fixed_options(b, d, name) if o.move == move)
            battle_instance.submit_action(b, name, tag)
        for name, (text, rate) in (texts or {}).items():
            tag = next(o.tag for o in battle_instance.options_for(b, d, name) if o.free_text)
            battle_instance.submit_action(b, name, tag, text, rate)
        log["msgs"] = game._advance_battle_round(b, d)

    after = game.world.mutate_siege(battle.record_id, fn)
    if after.phase == "ended":
        game._apply_battle_outcome(after)
        game.state.world = game.world.get_season()
    return after, log.get("msgs", [])


def _big_guard(b, neili=1000.0, cap=1000.0, order=None):
    g = _guard(b)
    g.neili_cap, g.neili = cap, neili
    if order is not None:
        b.orders[GUARD] = order


def test_melee_keeps_the_neutral_guard():
    game = _game()
    battle = _open(game)
    info = battle.siege
    assert info.attackers == ["guan", "huang"] and info.holder is None and info.guard_side == GUARD
    assert battle_instance.melee(battle)
    guards = [c for c in battle.commanders if c.fid.startswith("squad:")]
    assert len(guards) == 1 and guards[0].faction == GUARD
    assert battle_instance.side_names(battle, game._definition_of(battle))[GUARD] == battle_instance.GUARD_SIDE


def test_single_side_neutral_is_not_a_melee():
    game = _game()
    battle = _open(game, merged=(), side="huang")
    assert battle.siege.guard_side == "guan" and not battle_instance.melee(battle)  # 單方攻中立地照舊（守將站另一軍那一格）


def test_guard_pool_follows_the_head_count_at_the_start():
    game = _game()
    battle = _add(game, _open(game), {"甲": "guan", "丙": "guan", "乙": "huang"})
    battle = _start(game, battle)
    per_head = game.content.config.conquest.melee_pool_per_head
    assert battle.phase == "active"
    assert _guard(battle).neili_cap == _guard(battle).neili == pytest.approx(per_head * 3)


def test_both_armies_hit_the_guard():
    game = _game()
    battle = _start(game, _add(game, _open(game), {"甲": "guan", "乙": "huang"}))
    focus = game.content.config.battle.focus_per_attacker
    after, msgs = _round(game, battle, {"甲": "強攻", "乙": "強攻"}, setup=lambda b: _big_guard(b))
    assert _guard(after).neili == pytest.approx(1000 - 2 * focus)  # 戰線在中線：兩軍各打 focus_per_attacker
    text = "\n".join(msgs)
    assert "官軍的強攻撲向" in text and "黃巾軍的強攻撲向" in text


def test_the_line_scales_how_hard_an_army_hits_the_guard():
    game = _game()
    battle = _start(game, _add(game, _open(game), {"甲": "guan", "乙": "huang"}))
    focus = game.content.config.battle.focus_per_attacker

    def setup(b):
        _big_guard(b)
        b.trend = 70  # 這一回合開打時戰線往官軍偏 20：官軍打守將 ×1.4

    after, _ = _round(game, battle, {"甲": "強攻", "乙": "固守"}, setup=setup)
    assert _guard(after).neili == pytest.approx(1000 - focus * 70 / 50)


def test_strong_attack_still_hits_the_other_army():
    game = _game()
    battle = _start(game, _add(game, _open(game), {"甲": "guan", "乙": "huang"}))

    def setup(b):
        _big_guard(b, order="奇襲")  # 守將不出強攻：乙挨的集火只會是官軍的
        b.marked["乙"] = b.act_index  # 乙這一幕顯眼：對面的強攻集火打得到他

    after, _ = _round(game, battle, {"甲": "強攻", "乙": "奇襲"}, setup=setup)
    assert after.trend > 50  # 強攻剋奇襲：戰線往官軍推（戰線只算兩軍之間）
    assert after.participants["乙"].hurt_taken > 0  # 官軍的強攻集火打到黃巾顯眼的人


def test_the_line_moving_far_does_not_end_a_melee():
    game = _game()
    battle = _start(game, _add(game, _open(game), {"甲": "guan", "乙": "huang"}))

    def setup(b):
        _big_guard(b, order="固守")
        b.trend = 95

    after, _ = _round(game, battle, {"甲": "固守", "乙": "固守"}, setup=setup)
    assert after.phase == "active"  # 偏離中線 40 以上照打：三方混戰只看守將倒下或回合打完


def test_last_blow_takes_the_block():
    game = _game()
    battle = _start(game, _add(game, _open(game), {"甲": "guan", "乙": "huang"}))
    after, msgs = _round(game, battle, {"甲": "強攻", "乙": "固守"}, setup=lambda b: _big_guard(b, neili=10.0, order="固守"))
    assert after.phase == "ended" and after.round_number == 1  # 守將倒下那一回合當場收場
    guard = _guard(after)
    assert guard.fallen_round == 1 and guard.felled_by == "甲"
    assert after.siege.blow == "guan" and after.participants["甲"].slew == 1
    assert any("甲" in m and "最後一刀" in m for m in msgs)
    w = game.state.world
    assert conquest.holder(w, game.content, LOC) == "guan"
    assert any("甲" in r.text and "最後一刀" in r.text for r in w.rumors if r.layer == "world")
    ended = game.world.ended_battle(after.record_id)
    assert ended.outcome_side == "guan" and "最後一刀" in ended.outcome_title and "潁川郊野" in ended.outcome_title
    assert "甲" in ended.outcome_reason and "最後一刀" in ended.outcome_reason


def test_both_armies_reach_zero_in_one_round_more_damage_wins():
    game = _game()
    battle = _start(game, _add(game, _open(game), {"甲": "guan", "丙": "guan", "乙": "huang"}))
    after, _ = _round(game, battle, {"甲": "強攻", "丙": "強攻", "乙": "強攻"}, setup=lambda b: _big_guard(b, neili=20.0, order="固守"))
    assert after.phase == "ended" and after.siege.blow == "guan"  # 官軍兩人打 30、黃巾一人打 15：官軍拿下
    assert _guard(after).felled_by in ("甲", "丙")
    assert conquest.holder(game.state.world, game.content, LOC) == "guan"


def test_blow_side_tie_breaks():
    armies = ("guan", "huang")
    assert battle_instance.blow_side({"guan": 10.0, "huang": 30.0}, 80, armies, "x") == "huang"  # 打得多的那一軍
    assert battle_instance.blow_side({"guan": 15.0, "huang": 15.0}, 60, armies, "x") == "guan"  # 一樣多：戰線偏向誰
    assert battle_instance.blow_side({"guan": 15.0, "huang": 15.0}, 40, armies, "x") == "huang"
    coin = {battle_instance.blow_side({"guan": 15.0, "huang": 15.0}, 50, armies, f"seed{i}") for i in range(20)}
    assert coin == {"guan", "huang"}  # 戰線也在中線：照自己的亂數擲
    assert battle_instance.blow_side({"guan": 15.0, "huang": 15.0}, 50, armies, "seed1") == \
        battle_instance.blow_side({"guan": 15.0, "huang": 15.0}, 50, armies, "seed1")  # 同一個種子同一個結果


def test_same_damage_same_round_follows_the_line():
    game = _game()
    battle = _start(game, _add(game, _open(game), {"甲": "guan", "乙": "huang"}))

    def setup(b):
        _big_guard(b, neili=8.0, order="固守")
        b.trend = 50

    after, _ = _round(game, battle, {"甲": "強攻", "乙": "強攻"}, setup=setup)
    seed = f"最後一刀|{after.battle_id}|{after.record_id}|1"
    assert after.siege.blow == battle_instance.blow_side({"guan": 1.0, "huang": 1.0}, 50, ("guan", "huang"), seed)


def test_guard_survives_and_the_block_stays_neutral():
    game = _game()
    battle = _start(game, _add(game, _open(game), {"甲": "guan", "乙": "huang"}))
    rounds = battle_instance.total_rounds(game._definition_of(battle))
    after = battle
    for _ in range(rounds):
        after, _ = _round(game, after, {"甲": "固守", "乙": "固守"})
    assert after.phase == "ended" and after.round_number == rounds and _guard(after).fallen_round is None
    w = game.state.world
    assert conquest.holder(w, game.content, LOC) is None  # 守將守住：照舊中立
    ended = game.world.ended_battle(after.record_id)
    assert ended.outcome_side == GUARD and "守軍守住潁川郊野" in ended.outcome_title
    assert any("守住" in r.text and "潁川郊野" in r.text for r in w.rumors if r.layer == "world")
    found = next(s for s in w.conquest.schedule if s.id == after.siege.slot_id)
    assert found.status == "done" and found.winner is None


def test_ranger_can_help_the_guard_in_a_melee():
    game = _game()
    battle = _open(game)
    ranger = _game(side=None, name="散某", world=game.world)
    enlists = {o.id for o in ranger.options() if o.id.startswith("battle:enlist:")}
    assert enlists == {"battle:enlist:guan", "battle:enlist:huang", f"battle:enlist:{GUARD}"}
    label = next(o.label for o in ranger.options() if o.id == f"battle:enlist:{GUARD}")
    assert "助守" in label and "守軍" in label
    ranger.choose(f"battle:enlist:{GUARD}")
    battle = _now(game, battle)
    assert battle.participants["散某"].faction == GUARD
    battle = _start(game, _add(game, battle, {"甲": "guan", "乙": "huang"}))  # 裁決 23：只有一軍到場會轉回單方攻中立地，這裡要兩軍都有人
    assert battle_instance.melee(battle) and battle.participants["散某"].faction == GUARD  # 集結結束不被改分到兩軍
    ranger.now = game.now
    acts = [o.label for o in ranger.options() if o.id.startswith("battle:act:")]
    assert len(acts) == 3 and not any(" 分" in a or battle_instance.ORDER_MARK in a for a in acts)  # 份量不推戰線：不寫分數與將令
    focus = game.content.config.battle.focus_per_attacker
    per = game.content.config.battle.generals.guard_per

    def setup(b):
        _big_guard(b, order="固守")
        b.participants["散某"].role = ""  # 不是盾陣：擋 guard_per

    after, _ = _round(game, battle, {"甲": "強攻", "乙": "固守", "散某": "固守"}, setup=setup)
    assert _guard(after).neili == pytest.approx(1000 - focus * (1 - per))  # 助守的固守替守將擋一成
    assert after.participants["散某"].hurt_taken == pytest.approx(focus * per)


def test_helper_gamble_mends_the_guard():
    game = _game()
    battle = _open(game)
    ranger = _game(side=None, name="散某", world=game.world)
    ranger.choose(f"battle:enlist:{GUARD}")
    battle = _start(game, _add(game, _now(game, battle), {"甲": "guan", "乙": "huang"}))
    gen = game.content.config.battle.generals
    after, msgs = _round(game, battle, {"甲": "固守", "乙": "固守"}, setup=lambda b: _big_guard(b, neili=500.0, order="固守"),
                         texts={"散某": ("死守寨門", 100)})
    assert _guard(after).neili == pytest.approx(500 + 1000 * gen.hit_base)  # 成功率 100：風險 0，補回 hit_base
    assert after.trend == battle.trend  # 助守的人不推戰線（兩軍都固守，戰線不動）
    assert any("散某" in m and "補回" in m for m in msgs)


# ── 裁決 23（PM 2026-10-21）：集結結束只有一軍到場，轉回單方攻中立地 ──


def _squad(battle):
    """守將那一個人（隊伍當的，fid 是「squad:…」），不管他站哪一格。"""
    return next(c for c in battle.commanders if c.fid.startswith("squad:"))


def test_one_army_alone_turns_back_into_a_single_attack_on_neutral():
    game = _game()
    battle = _start(game, _add(game, _open(game), {"甲": "guan", "丙": "guan"}))  # 黃巾一個人都沒來
    assert battle.phase == "active"
    assert not battle_instance.melee(battle)  # 不是三方混戰了
    info = battle.siege
    assert info.attackers == ["guan"] and info.holder is None and info.guard_side == "huang"  # 同單方攻中立地：守將站沒來的那一軍那一格
    assert battle_instance.neutral_guard(battle) == "huang"
    names = battle_instance.side_names(battle, game._definition_of(battle))
    assert names["huang"] == battle_instance.GUARD_SIDE  # FB-540：寫給人看的是「守軍」
    assert GUARD not in battle_instance.fields(battle, game._definition_of(battle))
    # 守將跟單方攻中立地一模一樣（同一個人、同一個池子；不是三方混戰那一個小池子）
    expected = siege.guard_squad(game.state.world, game.content, LOC, "huang")
    assert _squad(battle).model_dump() == expected.model_dump()
    assert _squad(battle).neili_cap == game.content.config.battle.generals.pool[0]
    assert battle.orders.get("huang") in battle_instance.MOVES  # 守將照單方的喊令（不是 GUARD 那一格）
    assert GUARD not in battle.orders


def test_the_other_army_alone_also_turns_back():
    game = _game(side="huang")
    battle = _start(game, _add(game, _open(game, side="huang"), {"乙": "huang"}))  # 官軍沒來
    info = battle.siege
    assert not battle_instance.melee(battle)
    assert info.attackers == ["huang"] and info.guard_side == "guan"
    assert _squad(battle).faction == "guan"


def test_the_lone_army_takes_the_block_by_the_line_without_felling_the_guard():
    game = _game()
    battle = _start(game, _add(game, _open(game), {"甲": "guan"}))

    def setup(b):
        _squad(b).score = 1.0  # 守將別把戰線推回來：這一條只看「過了門檻就拿下」
        b.trend = 95

    after, msgs = _round(game, battle, {"甲": "固守"}, setup=setup)
    assert after.phase == "ended"  # 偏離中線 40 以上當場收場（單方攻中立地的老規矩）
    assert _squad(after).fallen_round is None  # 不用把守將打倒
    w = game.state.world
    assert conquest.holder(w, game.content, LOC) == "guan"
    texts = [r.text for r in w.rumors if r.layer == "world"]
    assert any("潁川郊野落入" in t for t in texts) and not any("最後一刀" in t for t in texts)  # 天下大事照單方攻中立地的寫
    ended = game.world.ended_battle(after.record_id)
    assert ended.outcome_side == "guan" and ended.outcome_title == "官軍大勝，拿下潁川郊野"
    found = next(s for s in w.conquest.schedule if s.id == after.siege.slot_id)
    assert found.status == "done" and found.winner == "guan"


def test_the_lone_army_does_not_get_a_harder_fight_than_attacking_alone():
    # 另一軍沒來算棄權：到場的那一軍，比只有自己宣戰時（單方攻中立地）不能更難。同一個局面兩種打法，結果要一樣。
    game = _game()
    melee_battle = _start(game, _add(game, _open(game), {"甲": "guan"}))
    other = _game(world=None)
    single = _start(other, _add(other, _open(other, merged=(), side="guan"), {"甲": "guan"}))
    assert not battle_instance.melee(single)
    assert melee_battle.siege.attackers == single.siege.attackers and melee_battle.siege.guard_side == single.siege.guard_side
    assert _squad(melee_battle).model_dump() == _squad(single).model_dump()
    assert melee_battle.orders == single.orders

    def setup(b):
        _squad(b).score = 1.0
        b.trend = 95

    for g, b in ((game, melee_battle), (other, single)):
        after, _ = _round(g, b, {"甲": "固守"}, setup=setup)
        assert after.phase == "ended" and conquest.holder(g.state.world, g.content, LOC) == "guan"


def test_the_guard_holds_a_lone_army_by_the_line():
    game = _game()
    battle = _start(game, _add(game, _open(game), {"甲": "guan"}))

    def setup(b):
        b.trend = 5  # 戰線壓在守將那一頭

    after, _ = _round(game, battle, {"甲": "固守"}, setup=setup)
    assert after.phase == "ended"
    assert conquest.holder(game.state.world, game.content, LOC) is None  # 照舊中立
    texts = [r.text for r in game.state.world.rumors if r.layer == "world"]
    assert any("守住" in t and "潁川郊野" in t for t in texts) and not any("兩軍都沒能" in t for t in texts)  # 單方的 HELD_LINE


def test_both_armies_present_is_still_a_melee():
    game = _game()
    battle = _start(game, _add(game, _open(game), {"甲": "guan", "乙": "huang"}))  # 各只到一個人也照三方混戰
    assert battle_instance.melee(battle)
    assert battle.siege.attackers == ["guan", "huang"] and battle.siege.guard_side == GUARD
    assert _guard(battle).faction == GUARD and _guard(battle).neili_cap == game.content.config.conquest.melee_pool_per_head * 2


def test_helpers_of_the_guard_follow_the_guard_when_it_turns_back():
    game = _game()
    battle = _open(game)
    ranger = _game(side=None, name="散某", world=game.world)
    ranger.choose(f"battle:enlist:{GUARD}")  # 集結時助守【守軍】
    battle = _start(game, _add(game, _now(game, battle), {"甲": "guan"}))
    assert not battle_instance.melee(battle)
    assert battle.participants["散某"].faction == "huang"  # 助守的人站守將那一格（單方攻中立地的助守）
    assert battle.participants["甲"].faction == "guan"
    ranger.now = game.now
    assert any(o.id.startswith("battle:act:") for o in ranger.options())  # 還能出招
    # 助守的固守替守將擋，跟單方攻中立地的助守一樣（戰線上算進守將那一邊）
    after, _ = _round(game, battle, {"甲": "固守", "散某": "固守"})
    assert after.participants["散某"].faction == "huang"


def test_a_ranger_who_enlisted_for_the_only_army_counts_as_present():
    game = _game()
    battle = _open(game)
    ranger = _game(side=None, name="散某", world=game.world)
    ranger.choose("battle:enlist:huang")  # 只有一個散人投效黃巾，官軍沒人
    battle = _start(game, _now(game, battle))
    assert battle.phase == "active" and not battle_instance.melee(battle)
    assert battle.siege.attackers == ["huang"] and battle.siege.guard_side == "guan"
    assert battle.participants["散某"].faction == "huang"


def test_nobody_shows_up_is_still_void_even_with_a_guard_helper():
    game = _game()
    battle = _open(game)
    ranger = _game(side=None, name="散某", world=game.world)
    ranger.choose(f"battle:enlist:{GUARD}")  # 只有助守的人，兩軍一個人都沒來
    battle = _start(game, _now(game, battle))
    assert battle.phase == "ended" and battle.unfinished and battle.siege.void == "absent"  # 裁決 19：照舊作罷
    w = game.state.world
    found = next(s for s in w.conquest.schedule if s.id == battle.siege.slot_id)
    assert found.status == "void" and conquest.holder(w, game.content, LOC) is None
    assert len([n for n in w.conquest.day_log if n.void == "absent" and n.loc == LOC]) == 2  # 每一個攻方一筆
    assert not any("作罷" in r.text for r in w.rumors if r.layer == "world")


def test_the_absent_army_cannot_come_late_and_the_scene_says_so():
    game = _game()
    battle = _start(game, _add(game, _open(game), {"甲": "guan"}))
    assert siege.join_problem(game.content, battle.siege, "huang", "huang") is not None  # 棄權的那一軍晚到也插不上手
    assert siege.slots(battle.siege, "guan") == ["guan"]
    assert siege.slots(battle.siege, None) == ["guan", "huang"]  # 散人可以投效到場那一軍、或助守
    assert battle.siege.absent == "huang"
    line = siege.scene_line(game.content, battle.siege, battle)
    assert line.startswith(siege.SCENE_LINE.format(attackers="官軍", place="潁川郊野", defender=_squad(battle).name))  # 場景照單方攻中立地的寫
    assert siege.ABSENT_SCENE_LINE.format(absent="黃巾軍") in line  # 再加一句沒到場的是誰
