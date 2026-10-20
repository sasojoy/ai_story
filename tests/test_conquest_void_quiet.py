"""領地爭奪第二批：攻方沒人到、這一場攻城作罷時不發天下大事（PM 裁決，第二批開發回報第 3 點；計畫第八章裁決 19）。

人少的服每天空轉一場，天下大事就多一句「一個人都沒到」，洗版（反目標 2）。作罷只記在時程表（那一場 void）與當天的 day_log
（一筆 void="absent"）；公告卡照常寫「作罷」。有人參戰的照舊發。"""
from __future__ import annotations

import pytest

from conquest_kit import announce, conquest_game, go, join
from tianxia import siege
from tianxia.engine import SIEGE_STATUS

pytestmark = pytest.mark.slow  # 建 Game、載正式內容

NOW = 1_792_000_000.0


def _game(side, loc="nanyang_road"):
    game = go(join(conquest_game("season21"), side), loc)
    game.now = NOW
    return game


def _open(game, slot):
    """把這一場排到此刻開集結（半小時後開打），照 world 的路開（同 test_conquest_siege._open）。"""
    w = game.state.world
    slot.muster_at, slot.at, slot.status = w.time, w.time + 1800, "waiting"
    game._save_season()
    siege.open_waiting(game.world, game.content, NOW)
    game.state.world = game.world.get_season()
    return game.world.get_sieges()[0]


def _close_muster(game):
    game.now = NOW + 1801  # 集結截止
    game._battle_status(tick=True)
    game.state.world = game.world.get_season()


def _world_rumors(game) -> list[str]:
    return [r.text for r in game.world.get_season().rumors if r.layer == "world"]


def test_nobody_came_posts_no_world_news():
    game = _game("guan")  # 官軍的人在場、黃巾一個人都沒來
    slot = announce(game, "nanyang_road", "huang")
    battle = _open(game, slot)
    before = _world_rumors(game)
    _close_muster(game)
    ended = game.world.ended_battle(battle.record_id)
    assert ended is not None and ended.unfinished and ended.siege.void == "absent"
    assert _world_rumors(game) == before  # 修前多一句「攻城・南陽官道：黃巾軍一個人都沒到，這一仗作罷。」


def test_nobody_came_is_kept_in_the_schedule_and_the_day_log():
    game = _game("guan")
    slot = announce(game, "nanyang_road", "huang")
    _open(game, slot)
    _close_muster(game)
    state = game.state.world.conquest
    found = next(s for s in state.schedule if s.id == slot.id)
    assert found.status == "void"
    notes = [n for n in state.day_log if n.void]
    assert len(notes) == 1  # 修前 day_log 沒有這一筆
    note = notes[0]
    assert (note.key, note.side, note.loc, note.minute, note.void) == (slot.key, "huang", "nanyang_road", slot.minute, "absent")
    card = next(row for row in game.conquest_view()["today"] if row["id"] == slot.id)  # 公告卡照常寫
    assert card["status"] == "void" and card["status_text"] == SIEGE_STATUS["void"]


def test_a_merged_siege_nobody_came_notes_each_side():
    game = _game("guan", "nanyang_road")
    slot = announce(game, "nanyang_road", "huang", merged=("guan", "huang"))
    battle = _open(game, slot)
    before = _world_rumors(game)
    _close_muster(game)
    assert game.world.ended_battle(battle.record_id).siege.void == "absent"
    assert _world_rumors(game) == before
    notes = [n for n in game.state.world.conquest.day_log if n.void]
    assert sorted(n.side for n in notes) == ["guan", "huang"]


def test_somebody_came_still_posts_the_result():
    game = _game("huang")
    slot = announce(game, "nanyang_road", "huang")
    battle = _open(game, slot)
    game.choose(next(o.id for o in game.options() if o.id.startswith("battle:join:huang")))
    game.world.mutate_siege(battle.record_id, lambda b: setattr(b.participants[game.state.player.name], "acted_rounds", 5))
    _close_muster(game)
    assert game.world.ended_battle(battle.record_id) is None  # 有人到：照常開打，不作罷
    before = _world_rumors(game)

    def _close(b):
        b.phase, b.trend, b.end_time = "ended", 10, game.state.world.time  # 黃巾大勝

    after = game.world.mutate_siege(battle.record_id, _close)
    game._apply_battle_outcome(after)
    news = _world_rumors(game)[len(before):]
    assert any("南陽官道落入" in text for text in news)
    assert not [n for n in game.world.get_season().conquest.day_log if n.void]
