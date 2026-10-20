"""領地爭奪第二批複驗開的兩張單（dev/conquest-2c）。

FB-542：放手一搏點名守將，以前要照抄顯示名「劫道響馬（守將）」才算；只寫守將的名字本身（隊伍名「劫道響馬」）也要算點名到守將。
三方混戰與單方攻中立地（含裁決 23 轉回單方的那一場）都一樣；只寫一個字、或只是隊伍名的一部分、或隊伍名是另一個人名字的一部分，
照原本的規則判斷（不算）。
FB-543：單方攻中立地時，守將那一格是另一軍的 id；另一軍站在那一區旁觀的人（沒參戰）的場景不能把守將的將令當成自己這邊的令。
助守的人（站在守將那一格）看得到令（他們的鈕本來就寫「主將令」）。字待 joy 潤。"""
from __future__ import annotations

import random

import pytest

from conquest_kit import announce, conquest_game, go, join
from tianxia import battle_instance, siege
from tianxia.battle_instance import GUARD

pytestmark = pytest.mark.slow  # 建 Game、載正式內容

NOW = 1_792_000_000.0
SCORES = {"強攻": 60.0, "固守": 60.0, "奇襲": 60.0}
LOC = "nanyang_road"  # 南陽官道：守將劫道響馬（守將）
PLACE = "hilltop_wilds"  # 荒丘：守將荒丘刀客（守將）
SQUAD = "劫道響馬"


def _game(side="guan", name="沈浪", world=None, loc=LOC):
    game = go(join(conquest_game("season21", name=name, world=world), side), loc)
    game.now = NOW
    return game


def _open(game, merged=("guan", "huang"), side="guan", loc=LOC):
    """排一場攻城、此刻開集結（照 world 的路，siege.open_waiting）；回那一場。"""
    slot = announce(game, loc, side, merged=merged)
    w = game.state.world
    slot.muster_at, slot.at, slot.status = w.time, w.time + 1800, "waiting"
    game._save_season()
    siege.open_waiting(game.world, game.content, NOW)
    game.state.world = game.world.get_season()
    return next(b for b in game.world.get_sieges() if b.siege.slot_id == slot.id)


def _add(game, battle, who: dict[str, str]):
    def fn(b):
        for name, side in who.items():
            battle_instance.join_faction(b, name, side, 300.0, power=100.0, scores=dict(SCORES))
    return game.world.mutate_siege(battle.record_id, fn)


def _now(game, battle):
    return next(b for b in game.world.get_sieges() if b.record_id == battle.record_id)


def _start(game, battle):
    game.now = battle.muster_deadline_real + 1
    game._tick_siege(battle)
    return _now(game, battle)


def _squad(battle):
    return next(c for c in battle.commanders if c.fid.startswith("squad:"))


def _round(game, battle, moves: dict[str, str], setup=None, texts: dict[str, tuple[str, int]] | None = None):
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
    return after, log.get("msgs", [])


def _big(b):
    """守將的池子加大，這一回合打掉的量一眼看得出來。"""
    g = _squad(b)
    g.neili_cap = g.neili = 1000.0


def _melee():
    """三方混戰開打（官甲、黃乙）；回（game, battle）。"""
    game = _game()
    return game, _start(game, _add(game, _open(game), {"甲": "guan", "乙": "huang"}))


def _lone():
    """裁決 23：只有官軍到場，轉回單方攻中立地（守將站黃巾那一格）；回（game, battle）。"""
    game = _game()
    battle = _start(game, _add(game, _open(game), {"甲": "guan", "丙": "guan"}))
    assert not battle_instance.melee(battle) and battle.siege.guard_side == "huang"
    return game, battle


def _single():
    """官軍單方攻南陽官道（merged 空）：守將站黃巾那一格。"""
    game = _game()
    battle = _add(game, _open(game, merged=(), side="guan"), {"甲": "guan", "丙": "guan"})
    battle = _start(game, battle)
    assert not battle_instance.melee(battle) and battle.siege.guard_side == "huang"
    return game, battle


def _gamble_hits(game, battle, text, who="甲"):
    """who 這一回合放手一搏（成功率 100、風險 0）寫 text，其餘人固守；回守將這一回合掉的氣血。"""
    others = {n: "固守" for n, p in battle.participants.items() if n != who and p.faction != GUARD}
    after, _ = _round(game, battle, others, setup=_big, texts={who: (text, 100)})
    return 1000.0 - _squad(after).neili


# ── FB-542 ──

NAMED = [
    "一槍直取劫道響馬的咽喉",  # 修前：只當沒點名
    "劫道響馬",
    "先斬劫道響馬，再取寨門",
    "一槍直取劫道響馬（守將）的咽喉",  # 原本就認
]
NOT_NAMED = [
    "先斬響馬頭目",  # 只是隊伍名的一部分
    "響馬",
    "劫道",
    "馬",  # 一個字
    "劫",
    "殺出一條血路",  # 沒點名
]


@pytest.mark.parametrize("build", [_melee, _lone, _single])
@pytest.mark.parametrize("text", NAMED)
def test_naming_the_guard_by_its_own_name_hits_the_guard(build, text):
    game, battle = build()
    hp = _gamble_hits(game, battle, text)
    want = game.content.config.battle.generals.hit_base * 1000.0  # 成功率 100：風險 0，打掉 hit_base
    assert hp == pytest.approx(want), f"{text}：守將應該被點名打到"


@pytest.mark.parametrize("build", [_melee, _lone])
@pytest.mark.parametrize("text", NOT_NAMED)
def test_not_naming_the_guard_does_not_hit_the_guard(build, text):
    game, battle = build()
    assert _gamble_hits(game, battle, text) == pytest.approx(0.0)  # 沒點名：推戰線，守將的池子不動


def test_find_commander_takes_the_squad_name_and_the_full_name():
    game, battle = _melee()
    d = game._definition_of(battle)
    guard = _squad(battle)
    assert guard.name == f"{SQUAD}（守將）"
    for text in NAMED:
        assert battle_instance.find_commander(battle, d, "甲", text) is guard
        assert battle_instance.find_commander(battle, d, "乙", text) is guard  # 兩軍都點得到他
    for text in NOT_NAMED:
        assert battle_instance.find_commander(battle, d, "甲", text) is None


def test_target_line_describes_the_guard_when_named_by_its_own_name():
    game, battle = _melee()
    d = game._definition_of(battle)
    tuning = game.content.config.battle
    line = battle_instance.target_line(battle, d, "甲", "一槍直取劫道響馬的咽喉", tuning)
    assert SQUAD in line and "守軍" in line and "主將" in line  # 給模型評成功率的那一行也要有
    assert battle_instance.target_line(battle, d, "甲", "先斬響馬頭目", tuning) == ""


def test_a_name_that_is_part_of_another_persons_name_is_not_the_guard():
    """同一邊的人名字裡含著隊伍名（甲方的「劫道響馬王」）：文字寫他，不當成點名守將；find_target 點不到同一邊的人。"""
    game = _game()
    battle = _start(game, _add(game, _open(game), {"甲": "guan", "乙": "huang", "劫道響馬王": "guan"}))  # 集結時才報得了名
    assert "劫道響馬王" in battle.participants
    d = game._definition_of(battle)
    assert battle_instance.find_target(battle, d, "甲", "迎面撞上劫道響馬王") is None  # 同一邊
    assert battle_instance.find_commander(battle, d, "甲", "迎面撞上劫道響馬王") is None
    assert battle_instance.find_commander(battle, d, "甲", "迎面撞上劫道響馬王，一槍直取劫道響馬") is not None  # 另外還寫了守將
    # 對面的人名字含著隊伍名：由 find_target 先認走（參戰者優先），輪不到守將
    assert battle_instance.find_target(battle, d, "乙", "迎面撞上劫道響馬王").name == "劫道響馬王"


def test_other_commanders_keep_their_whole_name_rule():
    """決戰的上陣人物沒有「（守將）」後綴：照原本整個名字比，一個字都不放寬。"""
    game, battle = _melee()
    d = game._definition_of(battle)
    guard = _squad(battle)
    guard.name, guard.fid = "皇甫嵩", "figure:huangfu"
    assert battle_instance.find_commander(battle, d, "甲", "直取皇甫嵩") is guard
    assert battle_instance.find_commander(battle, d, "甲", "直取皇甫") is None
    assert battle_instance.find_commander(battle, d, "甲", "直取嵩") is None


# ── FB-543 ──

def _single_hilltop(attacker="huang", guard="guan"):
    them = _game(attacker, "甲一", loc=PLACE)
    slot = announce(them, PLACE, attacker)
    w = them.state.world
    slot.muster_at, slot.at, slot.status = w.time, w.time + 1800, "waiting"
    them._save_season()
    siege.open_waiting(them.world, them.content, NOW)
    them.state.world = them.world.get_season()
    battle = next(b for b in them.world.get_sieges() if b.siege.slot_id == slot.id)
    assert battle.siege.holder is None and battle.siege.guard_side == guard
    return them, battle


def _begin(game, battle, trend=50):
    definition = game._definition_of(battle)

    def _go(b):
        battle_instance.close_muster(b, definition, random.Random(0), NOW)
        b.trend = trend

    return game.world.mutate_siege(battle.record_id, _go)


def _scene(game, battle):
    return game._battle_scene_text(_now(game, battle), game._definition_of(battle))


@pytest.mark.parametrize(("attacker", "guard"), [("huang", "guan"), ("guan", "huang")])
def test_the_other_army_watching_does_not_read_the_guards_order_as_its_own(attacker, guard):
    them, battle = _single_hilltop(attacker, guard)
    watcher = _game(guard, "乙二", world=them.world, loc=PLACE)  # 守將那一格是他陣營的 id，人沒參戰
    them.choose(f"battle:join:{attacker}")
    battle = _begin(them, battle)
    assert battle_instance.order_text(battle, guard, them.content.config.battle)  # 守將有喊令（規則照舊：守將照令出招，助守的人看得到）
    watcher.now = them.now
    scene = _scene(watcher, battle)
    assert "傳令" not in scene and "照令出招" not in scene  # 修前「荒丘刀客（守將）傳令：強攻（照令出招，份量多 15%）」
    assert "荒丘刀客（守將）" in scene  # 陣容那一行照舊看得到守將
    assert "插不上手" in scene  # 場景照舊說明自己這邊插不上手


def test_a_helper_of_the_guard_still_reads_the_order_and_the_attacker_is_unchanged():
    them, battle = _single_hilltop()
    ranger = _game(None, "散六", world=them.world, loc=PLACE)
    ranger.choose("battle:enlist:guan")  # 助守
    them.choose("battle:join:huang")
    battle = _begin(them, battle)
    ranger.now = them.now
    assert "傳令" in _scene(ranger, battle)  # 助守的人站守將那一格：令是他的（他的鈕也寫主將令）
    assert "傳令" not in _scene(them, battle)  # 攻方這一邊沒有人物，沒有令可寫


def test_an_unaligned_watcher_reads_no_order_either():
    them, battle = _single_hilltop()
    ranger = _game(None, "散六", world=them.world, loc=PLACE)
    them.choose("battle:join:huang")
    battle = _begin(them, battle)
    ranger.now = them.now
    assert "傳令" not in _scene(ranger, battle)


def test_the_absent_army_arriving_late_after_the_turn_back_reads_no_order():
    """裁決 23 轉回單方攻中立地後，沒到場那一軍（守將站它那一格）晚來的人，場景上也不能看到守將的令。"""
    game, battle = _lone()
    late = _game("huang", "黃晚", world=game.world)
    late.now = game.now
    scene = late._battle_scene_text(_now(game, battle), late._definition_of(battle))
    assert "傳令" not in scene and "插不上手" in scene
