"""FB-540：單方攻中立地時，守將站的是另一軍的那一格（SiegeInfo.guard_side），畫面、戰報、天下大事卻照那一格的陣營寫成那一軍
（散人的鈕「臨時投效【官軍】」、陣容「〔官軍〕主將…（守將）」、幕文字「漢家的旗」、論功「官軍首功…」、替守將助守加了官軍人物的情誼）。

守中立地的那一邊寫成中立的守軍（battle_instance.GUARD_SIDE），不冠任何一軍；散人助守的鈕寫「助守」；助守中立地不加任何一軍人物的
情誼（PM 2026-10-21：中立守軍不是哪一軍）。陣營佔著的區塊、兩軍同時搶同一塊中立地，照舊寫兩軍的名字。字待 joy 潤。"""
from __future__ import annotations

import random

import pytest

from conquest_kit import announce, conquest_game, go, join
from tianxia import battle_instance, conquest, siege

pytestmark = pytest.mark.slow  # 建 Game、載正式內容

NOW = 1_792_000_000.0
PLACE = "hilltop_wilds"  # 荒丘：還沒人佔的中立地（QA 那一場：黃巾攻荒丘，守將站官軍那一格）


def _game(side, name, world=None, loc=PLACE):
    game = go(join(conquest_game("season21", name=name, world=world), side), loc)
    game.now = NOW
    return game


def _open(game, slot):
    """把這一場排到此刻開集結（半小時後開打），照 world 的路開（同 test_conquest_siege._open）。"""
    w = game.state.world
    slot.muster_at, slot.at, slot.status = w.time, w.time + 1800, "waiting"
    game._save_season()
    siege.open_waiting(game.world, game.content, NOW)
    game.state.world = game.world.get_season()
    return next(b for b in game.world.get_sieges() if b.siege.slot_id == slot.id)


def _neutral(attacker="huang", guard="guan"):
    """attacker 攻還沒人佔的荒丘：守將站 guard 那一格；散人散六、攻方的人甲一。"""
    them = _game(attacker, "甲一")
    battle = _open(them, announce(them, PLACE, attacker))
    assert battle.siege.holder is None and battle.siege.guard_side == guard
    ranger = _game(None, "散六", world=them.world)
    return them, ranger, battle


def _latest(game, battle):
    return next(b for b in game.world.get_sieges() if b.record_id == battle.record_id)


def _start(game, battle, trend: int):
    """集結結束、開打，戰局停在 trend（高於 50 是官軍那一格佔上風）。"""
    definition = game._definition_of(battle)

    def _go(b):
        battle_instance.close_muster(b, definition, random.Random(0), NOW)
        b.trend = trend

    return game.world.mutate_siege(battle.record_id, _go)


def _end(game, battle, trend: int):
    """收場（戰局停在 trend），照收場那一下的路套結果（同 test_conquest_siege._end）。"""
    def _close(b):
        b.phase, b.trend, b.end_time = "ended", trend, game.state.world.time

    after = game.world.mutate_siege(battle.record_id, _close)
    game._apply_battle_outcome(after)
    game.state.world = game.world.get_season()
    return after


@pytest.mark.parametrize(("attacker", "guard", "army"), [("huang", "guan", "官軍"), ("guan", "huang", "黃巾軍")])
def test_ranger_buttons_say_help_guard(attacker, guard, army):
    _, ranger, battle = _neutral(attacker, guard)
    labels = {o.id: o.label for o in ranger.options() if o.id.startswith("battle:enlist:")}
    help_guard = labels[f"battle:enlist:{guard}"]
    assert "助守" in help_guard and army not in help_guard  # 修前「臨時投效【官軍】（只算這一場）」
    other = "黃巾軍" if attacker == "huang" else "官軍"
    assert labels[f"battle:enlist:{attacker}"] == f"臨時投效【{other}】（只算這一場）"  # 攻方那一顆照舊
    msgs = ranger.choose(f"battle:enlist:{guard}")
    assert ranger.world.get_sieges()[0].participants["散六"].faction == guard  # 規則照舊：站守將那一格
    assert not any(army in m for m in msgs) and any("助守" in m for m in msgs)
    after = {o.id: o.label for o in ranger.options() if o.id.startswith("battle:enlist:")}
    assert "助守" in after[f"battle:enlist:{guard}"] and army not in after[f"battle:enlist:{guard}"]
    scene = ranger._battle_scene_text(_latest(ranger, battle), ranger._definition_of(battle))
    assert army not in scene  # 修前「官軍：主將荒丘刀客（守將）」「你已臨時投效【官軍】」
    assert battle_instance.GUARD_SIDE in scene


def test_fight_screen_names_the_guard_side_as_the_garrison():
    them, ranger, battle = _neutral()
    ranger.choose("battle:enlist:guan")
    them.choose("battle:join:huang")
    b = _start(ranger, battle, 70)  # 守將那一格（官軍那一格）佔上風
    definition = ranger._definition_of(b)
    scene = ranger._battle_scene_text(b, definition)
    assert "官軍" not in scene and "漢家" not in scene  # 修前「〔官軍〕主將荒丘刀客（守將）」「寨牆上的旗一面面換成了漢家的」
    assert f"〔{battle_instance.GUARD_SIDE}〕" in scene  # 陣容那一行
    gauge = ranger.battle_gauge()
    assert "官軍" not in gauge["caption"]
    assert gauge["left"]["name"] == battle_instance.GUARD_SIDE and gauge["right"]["name"] == "黃巾軍"
    b = _start(ranger, battle, 30)  # 攻方佔上風：那一句也不寫官軍
    text = battle_instance.act_text(b, definition)
    assert "官軍" not in text and "黃巾" in text
    for g in (ranger, them):  # 打一回合：回合那一句照守軍寫
        g.choose(next(o.id for o in g.options() if o.id.startswith("battle:act:")))
    after = _latest(ranger, battle)
    assert after.round_number == 1
    assert "官軍" not in "\n".join(after.narrative_log)  # 修前「這一回合官軍佔了上風…官軍的武藝更勝一籌」
    assert "官軍" not in ranger._battle_scene_text(after, definition)


def test_reports_and_merit_name_the_garrison_without_army_affinity():
    them, ranger, battle = _neutral()
    ranger.choose("battle:enlist:guan")
    them.choose("battle:join:huang")

    def _acted(b):
        for p in b.participants.values():
            p.acted_rounds = 5

    _start(ranger, battle, 50)
    ranger.world.mutate_siege(battle.record_id, _acted)
    ended = _end(ranger, _latest(ranger, battle), 70)  # 守將那一格守住
    assert conquest.holder(ranger.state.world, ranger.content, PLACE) is None
    assert ended.outcome_side == "guan"  # 規則照舊：守將那一格贏
    mine = next(r for r in ranger.state.battles if r.battle_ref == battle.record_id)
    notes = "\n".join(mine.notes)
    assert "情誼" not in notes  # 修前「皇甫嵩、朱儁、曹操…聽說了這件事，情誼 +2。」（PM：助守中立地不加任何一軍人物的情誼）
    assert "官軍" not in notes  # 修前「在官軍排第 1／1」「你是官軍這一仗的首功」
    assert mine.side == battle_instance.GUARD_SIDE and f"在{battle_instance.GUARD_SIDE}排第 1" in notes
    entry = next(e for e in ranger.state.journal if e.battle_id == mine.id)
    assert "官軍" not in entry.tag and "官軍" not in "\n".join(entry.lines)
    rumors = [r.text for r in ranger.state.world.rumors if "論功" in r.text]
    assert rumors and not any("官軍" in t for t in rumors)  # 修前「攻城・荒丘論功：官軍首功散六，黃巾軍首功甲一。」
    assert any(f"{battle_instance.GUARD_SIDE}首功散六" in t for t in rumors)
    them.state.world = them.world.get_season()
    them._deliver_battle_results()
    theirs = next(r for r in them.state.battles if r.battle_ref == battle.record_id)
    assert theirs.opponent == battle_instance.GUARD_SIDE  # 攻方的戰報：對手是守軍，不是官軍


def test_held_block_keeps_army_names():
    """陣營佔著的區塊（官軍佔南陽官道，黃巾來攻）：沒有守將，兩軍照舊寫自己的名字。"""
    them = _game("huang", "甲一", loc="nanyang_road")
    conquest.set_control(them.state.world, them.content, "nanyang_road", "guan")
    battle = _open(them, announce(them, "nanyang_road", "huang"))
    assert battle.siege.holder == "guan" and battle.siege.guard_side is None
    ranger = _game(None, "散六", world=them.world, loc="nanyang_road")
    labels = {o.id: o.label for o in ranger.options() if o.id.startswith("battle:enlist:")}
    assert labels == {"battle:enlist:guan": "臨時投效【官軍】（只算這一場）", "battle:enlist:huang": "臨時投效【黃巾軍】（只算這一場）"}
    assert battle_instance.side_names(battle, them._definition_of(battle)) == {"guan": "官軍", "huang": "黃巾軍"}
