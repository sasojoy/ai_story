"""領地爭奪第二批 Task 10：多場戰鬥並存（攻城戰另存一串、找戰場、加入鈕、季終收兵、暫停繼續、假人、補戰報；Review Focus 4、5）。
資料庫結構不動（第 6 版排給商城）：攻城存在既有的 battles 表、world 那一列的 JSON 記流水號。"""
from __future__ import annotations

import random

import pytest

from conquest_kit import conquest_game, go, join, plain_game
from tianxia import battle_instance, conquest
from tianxia.battle_instance import SiegeInfo
from tianxia.bot_runner import BotRunner
from tianxia.characters import open_characters
from tianxia.database import SCHEMA_VERSION
from tianxia.sqlite_world import open_world

pytestmark = pytest.mark.slow  # 建 Game、載正式內容

NOW = 1_792_000_000.0


def _template(content, region: str = "yingru"):
    """那個大區的攻城範本（Task 11 寫進內容；還沒有時照長社火攻借一份，只換 id）。"""
    tid = f"siege_{region}"
    if tid not in content.battles:
        base = content.battles["changshe_fire"]
        content.battles[tid] = base.model_copy(update={"id": tid, "timetable_event": None, "defender": None, "front": None, "region": region})
    return content.battles[tid]


def _siege(game, loc: str, attackers=("huang",), holder="guan", now: float = NOW):
    info = SiegeInfo(slot_id=f"s-{loc}", loc=loc, attackers=list(attackers), holder=holder)
    region = next(r for r in game.content.map.regions if r.id == _region(game, loc))
    return game.world.start_siege(_template(game.content, region.id), now, 50, info)


def _region(game, loc: str) -> str:
    from tianxia import atlas

    return atlas.region_of(game.content, loc).id


def _two(game):
    """潁川汝南的兩場攻城（同一個大區、同時集結）。"""
    w, c = game.state.world, game.content
    blocks = [loc for loc in conquest.blocks(c) if conquest.capturable(c, loc) and _region(game, loc) == "yingru"][:2]
    return _siege(game, blocks[0]), _siege(game, blocks[1])


def _user_version(world) -> int:
    with world.db.snapshot() as conn:
        return conn.execute("PRAGMA user_version").fetchone()[0]


def test_two_sieges_persist_and_reload():
    game = conquest_game("season21")
    a, b = _two(game)
    assert a.record_id is not None and b.record_id is not None and a.record_id != b.record_id
    again = open_world(game.world.db.path)  # 重開資料庫
    assert [s.record_id for s in again.get_sieges()] == [a.record_id, b.record_id]
    assert again.get_sieges()[0].siege.loc == a.siege.loc
    assert again.get_battle() is None  # 決戰那一格不受影響
    # 結構版本不動：領地爭奪不升版。合 develop 之後基準是商城的第 6 版（以前寫死 5，那時 develop 的商城還沒合進來）
    assert _user_version(again) == SCHEMA_VERSION == 7


def test_submit_in_one_battle_does_not_touch_the_other():
    game = go(join(conquest_game("season21"), "huang"), "runan")
    game.now = NOW
    a, b = _two(game)
    joins = [o.id for o in game.options() if o.id.startswith("battle:join")]
    game.choose(next(i for i in joins if i.endswith(f"@{a.record_id}")))
    for rid in (a.record_id, b.record_id):  # 兩場都開打
        game.world.mutate_siege(rid, lambda x: battle_instance.close_muster(x, _template(game.content), random.Random(0), NOW))
    act = next(o.id for o in game.options() if o.id.startswith("battle:act:"))
    assert "@" not in act  # 參戰之後只有那一場：鈕照舊不帶 @
    game.choose(act)
    one, two = game.world.get_sieges()
    assert game.state.player.name in one.round.pending_actions or one.round_number == 1
    assert two.round.pending_actions == {} and two.participants == {}


def test_two_battles_one_region_join_is_explicit():
    game = go(join(conquest_game("season21"), "huang"), "runan")
    game.now = NOW
    a, b = _two(game)
    joins = [o.id for o in game.options() if o.id.startswith("battle:join")]
    assert joins == [f"battle:join:huang@{a.record_id}", f"battle:join:huang@{b.record_id}"]  # 兩顆各帶 @流水號
    game.choose(joins[1])
    assert game.state.player.name in game.world.get_sieges()[1].participants
    assert game.state.player.name not in game.world.get_sieges()[0].participants
    after = [o for o in game.options() if o.id.startswith("battle:join")]
    assert [o.id for o in after] == ["battle:join:huang"] and not after[0].enabled  # 加入了一場：另一場的鈕不見
    game.choose(f"battle:join:huang@{a.record_id}")  # 另一場的鈕已經不在選單上：不收
    assert game.state.player.name not in game.world.get_sieges()[0].participants
    assert game._battle_choose(f"join:huang@{a.record_id}") == ["（你已經在另一場戰局裡。）"]  # 直接送也不收


def test_season_end_shelves_sieges():
    game = go(join(conquest_game("season21"), "huang"), "runan")
    game.now = NOW
    a, _ = _two(game)
    game.choose(next(o.id for o in game.options() if o.id.endswith(f"@{a.record_id}")))
    game.state.world.ended = True
    game._battle_status(tick=True)
    assert game.world.get_sieges() == []  # 收起來了
    ended = game.world.ended_battle(a.record_id)
    assert ended is not None and ended.unfinished and ended.outcome_side == ""  # 不算勝負、不易手
    titles = [e.title for e in game.state.journal]
    assert any(battle_instance.UNFINISHED_TITLE in t for t in titles)


def test_resume_shifts_siege_deadlines():
    game = conquest_game("season21")
    a, _ = _two(game)
    before = a.muster_deadline_real
    assert game.world.pause_clock(NOW + 10)
    game.world.resume_clock(game.content, NOW + 610)
    assert game.world.get_sieges()[0].muster_deadline_real == pytest.approx(before + 600)


def test_bot_runner_owes_both_battles():
    game = go(join(conquest_game("season21", name="甲某"), "huang"), "runan")
    other = go(join(conquest_game("season21", name="乙某", world=game.world), "huang"), "runan")
    game.now = other.now = NOW
    _template(other.content)  # 兩局各自一份內容
    a, b = _two(game)
    game.choose(next(o.id for o in game.options() if o.id.endswith(f"@{a.record_id}")))
    other.choose(next(o.id for o in other.options() if o.id.endswith(f"@{b.record_id}")))
    for rid in (a.record_id, b.record_id):
        game.world.mutate_siege(rid, lambda x: battle_instance.close_muster(x, _template(game.content), random.Random(0), NOW))
    runner = BotRunner(game.content, game.world, open_characters(), random.Random(1), clock=lambda: NOW)
    assert runner._battle_owes() == frozenset({"甲某", "乙某"})
    assert runner.battle_on()


def test_results_are_delivered_out_of_order():
    """先開的那一場晚收場：補戰報不能只看「比補過的最大流水號大」（ended_battles 以前的前提）。"""
    game = go(join(conquest_game("season21"), "huang"), "runan")
    game.now = NOW
    a, b = _two(game)
    game.choose(next(o.id for o in game.options() if o.id.endswith(f"@{a.record_id}")))

    def _end(x):
        x.phase, x.unfinished, x.end_time = "ended", True, 0.0

    game.world.mutate_siege(b.record_id, _end)  # 後開的先收場
    game._deliver_battle_results()
    assert b.record_id in game.state.player.battle_results_seen
    game.world.mutate_siege(a.record_id, _end)  # 先開的（流水號小）後收場
    game._deliver_battle_results()
    assert a.record_id in game.state.player.battle_results_seen


def test_switch_off_single_battle_unchanged():
    game = go(join(plain_game("season21"), "guan"), "changshe")
    game.now = NOW
    assert game.battles_now() == []
    game.world.start_battle(game.content.battles["changshe_fire"], NOW, 50)
    assert [b.record_id for b in game.battles_now()] == [game.world.get_battle().record_id]
    assert "battle:join:guan" in [o.id for o in game.options()]  # 只有一場：鈕不帶 @
    assert game.world.get_sieges() == []
