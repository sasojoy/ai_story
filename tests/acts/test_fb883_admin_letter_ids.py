"""FB-883：管理者「立刻下戰書」（Game.admin_conquest_letter → conquest_day.place_now）在同一個世界秒裡替同一邊連下幾張，
攻城的 id 不准撞號。以前 id 是 now-<世界秒>-<邊>，三張全一樣：撤第二張撤到第一張，開集結時 siege.open_waiting 照 id 寫回，已經作罷的那張
又被改回 open，三場共用同一個 record_id。玩家碰不到（一般的戰書 L<天>-<秒>-<邊> 一邊一天一張），會撞的是一次叫好幾次的 QA 腳本。

修法：第一張還是 now-<秒>-<邊>（單張的樣子不變），同一秒同一邊再下的往後加 -2、-3…（時程表上已經有的 id 一律不重複）。
玩家自然下的戰書 id 規則不動。"""
from __future__ import annotations

import pytest
from conquest_kit import conquest_game, go, join

from tianxia import conquest_day, siege

pytestmark = pytest.mark.slow  # 建 Game、載正式內容

NOW = 1_792_000_000.0
TARGETS = ["xiaquyang", "loushang_village", "yingshui"]  # QA 重現的三處：下曲陽、樓桑里、潁水河畔（黃巾都能攻）


def _admin(profile="season21", side="huang"):
    game = go(join(conquest_game(profile, name="Rayal"), side), "xiaquyang")
    game.now = NOW
    return game


def _letters(game, side="huang", places=TARGETS):
    """同一個管理者動作（同一個世界秒）替 side 依序對 places 各下一張，回時程表上多出來的那幾張。"""
    for loc in places:
        game.admin_conquest_letter(loc, side)
    return list(game.state.world.conquest.schedule)


def _muster_now(game, slots):
    """把這幾張排成「集結馬上開」，照伺服器開集結（siege.open_waiting）。"""
    w = game.state.world
    for slot in slots:
        slot.muster_at, slot.at, slot.status = w.time, w.time + 1800, "waiting"
    game._save_season()
    siege.open_waiting(game.world, game.content, NOW)
    game.state.world = game.world.get_season()


def test_three_letters_for_one_side_in_one_second_get_three_ids():
    game = _admin()
    w = game.state.world
    t = int(w.time)
    slots = _letters(game)
    assert [s.loc for s in slots] == TARGETS or {s.loc for s in slots} == set(TARGETS)
    ids = [s.id for s in sorted(slots, key=lambda s: TARGETS.index(s.loc))]
    assert len(set(ids)) == 3, ids
    assert ids[0] == f"now-{t}-huang"  # 單張的樣子不變
    assert all(i.startswith(f"now-{t}-huang") for i in ids)


def test_a_single_letter_keeps_the_old_id():
    game = _admin()
    t = int(game.state.world.time)
    (slot,) = _letters(game, places=["xiaquyang"])
    assert slot.id == f"now-{t}-huang"


def test_cancelling_the_second_letter_cancels_only_the_second():
    game = _admin()
    slots = _letters(game)
    by_loc = {s.loc: s for s in slots}
    mid = by_loc["loushang_village"]
    text = game.admin_conquest_cancel(mid.id)
    assert "樓桑里" in text[-1] and "作罷" in text[-1]  # 撤到的就是樓桑里那一張（修前撤到第一張下曲陽）
    status = {s.loc: s.status for s in game.state.world.conquest.schedule}
    assert status == {"xiaquyang": "planned", "loushang_village": "void", "yingshui": "planned"}


def test_the_siege_choices_list_each_letter_under_its_own_id():
    game = _admin()
    _letters(game)
    ids = [row["id"] for row in game.admin_conquest_choices()["sieges"]]
    assert len(ids) == 3 and len(set(ids)) == 3


def test_opening_the_muster_does_not_reopen_a_cancelled_letter():
    """三張裡撤掉第二張，其餘兩張開集結：作罷的那張還是 void（修前被改回 open），開了的兩場各有自己的紀錄（修前三張的 record_id 同一個），
    每一場戰鬥的 slot_id 與地點指著自己那一張。"""
    game = _admin()
    slots = _letters(game)
    by_loc = {s.loc: s for s in slots}
    game.admin_conquest_cancel(by_loc["loushang_village"].id)
    w = game.state.world
    _muster_now(game, [s for s in w.conquest.schedule if s.status == "planned"])
    got = {s.loc: s for s in game.state.world.conquest.schedule}
    assert got["loushang_village"].status == "void" and got["loushang_village"].record_id is None
    assert got["xiaquyang"].status == got["yingshui"].status == "open"
    a, b = got["xiaquyang"].record_id, got["yingshui"].record_id
    assert a is not None and b is not None and a != b
    battles = {b.record_id: b for b in game.world.get_sieges()}
    assert set(battles) == {a, b}
    for slot in (got["xiaquyang"], got["yingshui"]):
        info = battles[slot.record_id].siege
        assert (info.slot_id, info.loc) == (slot.id, slot.loc)


def test_opening_all_three_gives_three_records():
    game = _admin()
    slots = _letters(game)
    _muster_now(game, slots)
    got = game.state.world.conquest.schedule
    assert [s.status for s in got] == ["open"] * 3
    assert len({s.record_id for s in got}) == 3


def test_ids_stay_unique_when_an_old_one_is_still_on_the_schedule():
    """時程表上已經有同樣 id 的（打完或作罷了還沒被換天清掉）：新的往後加，不蓋也不撞。"""
    game = _admin()
    w = game.state.world
    (first,) = _letters(game, places=["xiaquyang"])
    conquest_day.void(w, game.content, first)  # 作罷了，但還在時程表上
    game._save_season()
    again = game.admin_conquest_letter("xiaquyang", "huang")
    ids = [s.id for s in game.state.world.conquest.schedule]
    assert len(ids) == 2 and len(set(ids)) == 2, (ids, again)
