"""FB-113（QA 驗 FB-105，7894，main 17765f9／8745b50，2026-10-08，375×812）：序章裡的新人被拉進決戰。

序章開場（潁川城外）與草廬都在潁川汝南，長社火攻也在那裡：集結時新人的第一個畫面就是「臨時投效」兩顆，按了名字就上了參戰名單；
開打後序章的故事與選項被戰場蓋掉，序章裡又走不開，要等收場才接回序章。投效、出手的新人收場時照領全額軍餉，序章中途連升數級
（FB-122 的那一條）。

現在在引擎端擋（不只改網頁擺放）：序章裡（prologue.active）選單不給投效與加入、直接送也擋下，場景也不畫戰場那一塊，
選單與場景都照序章自己的走；修好之前就上了名單的序章新人也一樣，收場時不領軍餉（戰報與紀錄照寫）。
真實內容、週末的開法（conftest 的 on），長社火攻。"""
from __future__ import annotations

import random

import pytest
from test_prologue import _to_step

from tianxia import atlas, battle_instance, prologue
from tianxia.engine import Game

BATTLE = "changshe_fire"  # 長社火攻（潁川汝南）


def _newbie(on, step=0):
    """沒略過序章的新角色，走到序章第 step 步（0 是開場的遇險，有事件；1 起在草廬、師父說話）。"""
    game = Game.new(on, "新人", rng=random.Random(0), prologue=True)
    game.client = None
    _to_step(game, step)
    assert prologue.active(game.state, on)
    assert atlas.region_of(on, game.state.player.location).id == on.battles[BATTLE].region  # 草廬就在決戰的大區裡
    return game


def _start(game, fighting):
    game.world.start_battle(game.content.battles[BATTLE], now=game.now)
    if fighting:  # 集結時間撥到過去，讀一次選單（options() 把全服戰鬥追到現在）就開打
        game.world.mutate_battle(lambda b: setattr(b, "muster_deadline_real", -1.0))
        game.options()
        assert game.world.get_battle().phase == "active"


@pytest.mark.parametrize("step", [0, 1], ids=["ambush", "hut"])
@pytest.mark.parametrize("fighting", [False, True], ids=["muster", "running"])
def test_a_newbie_in_the_prologue_is_not_drawn_into_the_battle(on, step, fighting):
    """集結中、開打後都一樣：選單與場景跟沒有這場決戰時一模一樣——沒有投效、加入，場景不畫戰場。"""
    game = _newbie(on, step)
    menu, scene = [(o.id, o.label, o.enabled) for o in game.options()], game.scene_text()
    _start(game, fighting)
    assert [(o.id, o.label, o.enabled) for o in game.options()] == menu
    assert game.scene_text() == scene and on.battles[BATTLE].name not in scene
    assert game.battle_free_text_prompt() is None


@pytest.mark.parametrize("fighting", [False, True], ids=["muster", "running"])
def test_sending_the_enlist_or_join_straight_to_the_engine_is_refused_in_the_prologue(on, fighting):
    game = _newbie(on)
    _start(game, fighting)
    for arg in ("enlist:guan", "join:guan", "join_late"):
        assert game.choose(f"battle:{arg}") == ["（此刻無法這麼做。）"]
        assert game._battle_choose(arg) == ["（此刻無法這麼做。）"]
    assert game.world.get_battle().participants == {}


def test_a_newbie_already_on_the_roster_from_before_the_fix_keeps_walking_the_prologue(on):
    """修好之前就投效了的序章新人（名字已經在名單上）：開打後選單、場景照樣是序章的，不給三招、不給放手一搏的輸入框。"""
    game = _newbie(on)
    menu, scene = [o.id for o in game.options()], game.scene_text()
    _start(game, fighting=False)
    name = game.state.player.name
    game.world.mutate_battle(lambda b: battle_instance.join_faction(b, name, "guan", neili_cap=100.0))
    game.world.mutate_battle(lambda b: setattr(b, "muster_deadline_real", -1.0))
    game.options()
    assert game.world.get_battle().phase == "active" and name in game.world.get_battle().participants
    assert [o.id for o in game.options()] == menu and game.scene_text() == scene
    assert game.battle_free_text_prompt() is None
    assert game.submit_battle_custom_action("全軍衝鋒", 50) == ["（此刻無法這麼做。）"]


def _won_showdown(name):
    """長社火攻官軍大勝收場、name 替官軍出手滿 6 回合（直接造一份收場的戰鬥，照 _file_showdown 補戰報）。"""
    battle = battle_instance.BattleInstance(battle_id=BATTLE, phase="ended", outcome_side="guan", outcome_margin="大勝",
                                            outcome_title="官軍大勝")
    me = battle_instance.BattleParticipant(name=name, faction="guan", neili=1, neili_cap=1, acted_rounds=6)
    return battle, me


def test_a_newbie_who_fought_in_the_prologue_draws_no_pay(on):
    """序章裡被拉進決戰（修好之前投效的）的新人：戰報與江湖紀錄照寫，軍餉（銀兩、經驗）不發——以前 1 級大勝拿 120 經驗、
    序章中途升到 5 級、4 點屬性，序章還沒開放配點（FB-122）。走完序章的人照發（對照組）。"""
    game = _newbie(on)
    p = game.state.player
    silver, level, points = p.stats.get("silver", 0), p.member.level, p.stat_points
    game._file_showdown(*_won_showdown(p.name), None)
    entry = game.state.journal[0]
    assert entry.title.endswith("官軍大勝") and game.state.battles[0].kind == "showdown"
    assert not any(c.startswith(("銀兩", "經驗")) for c in entry.changes)
    assert not any("軍餉" in line for line in entry.lines)
    assert (p.stats.get("silver", 0), p.member.level, p.stat_points) == (silver, level, points)

    veteran = Game.new(on, "老手", rng=random.Random(0), world=game.world)
    veteran.client = None
    assert not prologue.active(veteran.state, on)
    veteran._file_showdown(*_won_showdown("老手"), None)
    assert "銀兩 +80" in veteran.state.journal[0].changes and "得勝的軍餉發下來了。" in veteran.state.journal[0].lines
