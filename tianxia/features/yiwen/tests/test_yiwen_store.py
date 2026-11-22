"""異聞的旁檔 <db>-yiwen.sqlite（總計畫「異聞一」的表）。"""
import contextlib
import sqlite3

import pytest

from tianxia.features.yiwen import store as yiwen_store


@pytest.fixture
def side(tmp_path):
    return yiwen_store.for_db(tmp_path / "main.db")


def _node(st, tale, parent, pick, depth=1, by="甲"):
    return st.add_node(tale=tale, parent=parent, depth=depth, pick=pick, typed=False, by=by, shown=by, luck="good", text=["一段"],
                       options=["a", "b", "c"], ledger=[], fallback=True, at=1.0, branch_cap=5, free_branches=2, can_pay=False, own=True)


def test_side_file_beside_db_and_tables(tmp_path, side):
    """第 251 批：開了 store 還不建檔（讀回空）；第一次寫（開則）才建檔、建表。"""
    assert side.path == tmp_path / "main-yiwen.sqlite" and not side.path.exists()
    assert side.tales(1) == [] and not side.path.exists()
    side.open_tale(season=1, opening="clay_faces", place="p", by="甲", shown="甲", at=0.0)
    assert side.path.is_file()
    with contextlib.closing(sqlite3.connect(side.path)) as conn:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert set(yiwen_store.TABLES) <= names
    side.open_tale(season=1, opening="fog_figure", place="p", by="甲", shown="甲", at=0.0)
    again = yiwen_store.YiwenStore(side.path)  # 再開不重建（資料還在）
    assert len(again.tales(1)) == 2
    assert yiwen_store.for_db(tmp_path / "main.db") is side


def test_reads_never_create_the_file(side):
    """檔不在時每一種讀法都回空、不建檔（sqlite3.connect 會建出空檔）。"""
    assert side.tales(1) == [] and side.walking(1) == [] and side.tale(1) is None and side.node(1) is None
    assert side.walk(1, "甲") is None and side.children(1, 0) == [] and side.nodes(1) == []
    assert side.footprints(1) == {} and side.steps(1) == {}
    assert not side.path.exists()


def test_write_after_file_removed_rebuilds_tables(side):
    """寫過一次之後檔被刪（還原、手動清）：下一次寫照樣建表，不寫進沒有表的空檔。"""
    side.open_tale(season=1, opening="fog_figure", place="p", by="甲", shown="甲", at=0.0)
    side.path.unlink()
    for extra in ("-wal", "-shm"):
        side.path.with_name(side.path.name + extra).unlink(missing_ok=True)
    assert side.tales(1) == [] and not side.path.exists()
    assert side.open_tale(season=1, opening="fog_figure", place="p", by="甲", shown="甲", at=0.0) > 0
    assert len(side.tales(1)) == 1


def test_one_tale_per_opening_per_season(side):
    side.open_tale(season=1, opening="fog_figure", place="p", by="甲", shown="甲", at=0.0)
    with pytest.raises(yiwen_store.Taken):
        side.open_tale(season=1, opening="fog_figure", place="p", by="乙", shown="乙", at=1.0)
    assert side.open_tale(season=2, opening="fog_figure", place="p", by="乙", shown="乙", at=1.0) > 0  # 下一季又是新的


def test_same_parent_same_pick_is_one_node(side):
    tid = side.open_tale(season=1, opening="fog_figure", place="p", by="甲", shown="甲", at=0.0)
    first = _node(side, tid, 0, "官軍")
    second = _node(side, tid, 0, "官軍", by="乙")
    assert first.kind == "new" and second.kind == "taken"
    assert second.node["id"] == first.node["id"] and second.node["by"] == "甲"
    assert len(side.nodes(tid)) == 1


def test_finish_walk_counts_once(side):
    tid = side.open_tale(season=1, opening="fog_figure", place="p", by="甲", shown="甲", at=0.0)
    side.step_walk(tale=tid, account="乙", season=1, node=5, at=1.0)
    assert side.finish_walk(tale=tid, account="乙", side="guan", at=2.0) is True
    assert side.finish_walk(tale=tid, account="乙", side="guan", at=3.0) is False
    assert side.walk(tid, "乙")["finished_at"] == 2.0


def test_footprints_and_steps_count_finished_only(side):
    tid = side.open_tale(season=1, opening="fog_figure", place="p", by="甲", shown="甲", at=0.0)
    a = _node(side, tid, 0, "官軍").node["id"]
    b = _node(side, tid, a, "走近", depth=2).node["id"]
    c = _node(side, tid, b, "問", depth=3).node["id"]
    for who, path, done in (("甲", [a, b, c], True), ("乙", [a, b, c], True), ("丙", [a, b], False)):
        for nid in path:
            side.step_walk(tale=tid, account=who, season=1, node=nid, at=1.0)
        if done:
            side.finish_walk(tale=tid, account=who, side="", at=2.0)
    assert side.footprints(tid) == {c: 2}
    assert side.steps(tid) == {a: 2, b: 2, c: 2}
