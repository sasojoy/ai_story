"""換季時上上季的傳聞與決戰回合紀錄搬進封存檔（審查 S-12，企劃者 Joy「上上季的資料存在另一個封存區備用」）。
江湖史、決戰本身不搬；封存檔寫不進去、主檔刪不掉、換季那一筆撤回，都不掉資料、換季照常。"""
import sqlite3

import pytest

from tianxia import log_archive, sqlite_world
from tianxia.battle_instance import BattleInstance, BattleRoundRecord
from tianxia.sqlite_world import open_world
from tianxia.state import Rumor


@pytest.fixture
def store(content):
    world = open_world()
    world.seed_first_season(content)  # 測試內容自動開第一季
    return world


def _fill(store, tag: str) -> None:
    """這一季寫兩則傳聞、一則江湖史、一場有兩回合的決戰（換季時那一場被清掉、列留在 battles 表）。"""
    def _apply(state):
        state.season.rumors += [Rumor(time=1.0, text=f"{tag}傳聞甲", layer="local", location="洛陽"),
                                Rumor(time=2.0, text=f"{tag}傳聞乙")]
        state.season.chronicle.append(Rumor(time=3.0, text=f"{tag}江湖史"))
        state.active_battle = BattleInstance(battle_id=f"{tag}戰", rounds=[
            BattleRoundRecord(act_index=0, round_number=n, resolved_real=float(n), trend_after=n) for n in (1, 2)])
    store.mutate(_apply)


def _roll(store, content, now: float) -> None:
    store.mutate_season(lambda s: setattr(s, "ended", True))  # 休季
    assert store.next_season(content, now) is True


def _main(store, sql: str, *args):
    with store.db.snapshot() as conn:
        return [tuple(r) for r in conn.execute(sql, args)]


def _archive(store, sql: str, *args):
    path = log_archive.archive_path(store.db.path)
    if not path.exists():
        return []
    conn = sqlite3.connect(path)
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


def _seasons(store, table: str) -> list[int]:
    if table == "battle_rounds":
        return sorted({r[0] for r in _main(store, "SELECT b.season FROM battle_rounds r JOIN battles b ON b.id = r.battle_id")})
    return sorted({r[0] for r in _main(store, f"SELECT season FROM {table}")})


def _three_seasons(store, content) -> None:
    _fill(store, "一季")
    _roll(store, content, 100.0)  # 第 2 季：上上季是第 0 季，什麼都不搬
    _fill(store, "二季")
    _roll(store, content, 200.0)  # 第 3 季：第 1 季搬走
    _fill(store, "三季")


def test_the_season_before_last_moves_to_the_archive_and_leaves_the_main_file(store, content):
    _fill(store, "一季")
    _roll(store, content, 100.0)
    assert not log_archive.archive_path(store.db.path).exists()  # 第 2 季：沒東西可搬，也不建封存檔
    _fill(store, "二季")
    _roll(store, content, 200.0)
    _fill(store, "三季")
    assert store.get_season_number() == 3
    assert _seasons(store, "rumors") == [2, 3]
    assert _seasons(store, "battle_rounds") == [2, 3]
    assert _archive(store, "SELECT season, text, layer, location FROM rumors ORDER BY id") == [
        (1, "一季傳聞甲", "local", "洛陽"), (1, "一季傳聞乙", "world", None)]
    archived = _archive(store, "SELECT season, battle_id FROM battle_rounds ORDER BY id")
    assert [s for s, _ in archived] == [1, 1]
    battle_one = _main(store, "SELECT id FROM battles WHERE season = 1")
    assert {b for _, b in archived} == {battle_one[0][0]}  # 決戰本身留在主檔（戰報照它重讀）
    assert store.battle_rounds(battle_one[0][0]) == []
    assert len(store.battle_rounds(_main(store, "SELECT id FROM battles WHERE season = 2")[0][0])) == 2
    # 江湖史一則都不動
    assert _seasons(store, "chronicle") == [1, 2, 3]
    assert [e.text for _, entries in store.chronicle_before(3) for e in entries if e.text.endswith("江湖史")] == ["二季江湖史", "一季江湖史"]
    assert [r.text for r in store.get_season().rumors] == ["三季傳聞甲", "三季傳聞乙"]


def test_older_seasons_left_behind_are_moved_too(store, content):
    """一次搬「上上季與更早」：之前沒搬成（或升級前就有的）幾季，下一次換季一起搬。"""
    _three_seasons(store, content)
    with store.db.transaction() as conn:  # 假裝第 1 季的還留在主檔（例如上一次封存失敗）
        conn.execute("INSERT INTO rumors (season, time, layer, named, text) VALUES (1, 9.0, 'world', 1, '漏網的')")
    _roll(store, content, 300.0)  # 第 4 季：第 1、2 季都搬
    assert _seasons(store, "rumors") == [3]
    assert sorted({s for (s,) in _archive(store, "SELECT season FROM rumors")}) == [1, 2]
    assert "漏網的" in {t for (t,) in _archive(store, "SELECT text FROM rumors")}


def test_reads_after_the_move_do_not_return_archived_rumors(store, content):
    """傳聞的快取（_LOG_CACHES）記過的那一季被搬走之後，再讀那一季是空的；換季的那一筆 COMMIT 之後整份作廢。"""
    _fill(store, "一季")
    assert [r.text for r in store.get_season().rumors] == ["一季傳聞甲", "一季傳聞乙"]  # 第 1 季的記進快取
    assert ("rumors", 1) in sqlite_world._LOG_CACHES[store.db]
    _roll(store, content, 100.0)
    _fill(store, "二季")
    with store.db.snapshot() as conn:  # 第 2 季時再讀一次第 1 季：快取照樣有
        assert len(store._logs(conn, "rumors", 1, sqlite_world._rumor)) == 2
    generation = store.db.generation
    _roll(store, content, 200.0)
    assert store.db.generation > generation  # 搬了：COMMIT 之後作廢（_forget_logs）
    assert ("rumors", 1) not in sqlite_world._LOG_CACHES.get(store.db, {})
    with store.db.snapshot() as conn:
        assert store._logs(conn, "rumors", 1, sqlite_world._rumor) == []
        assert [r.text for r in store._logs(conn, "rumors", 2, sqlite_world._rumor)] == ["二季傳聞甲", "二季傳聞乙"]


def test_the_same_transaction_does_not_read_the_cache_after_the_move(store, content):
    """換季那一筆裡搬完之後再讀（例：管理者開下一季的同一個請求裡），不拿記下的舊的那一份。"""
    _fill(store, "一季")
    store.get_season()
    _roll(store, content, 100.0)
    _fill(store, "二季")
    with store.db.snapshot() as conn:
        store._logs(conn, "rumors", 1, sqlite_world._rumor)
    store.mutate_season(lambda s: setattr(s, "ended", True))
    with store.db.transaction() as conn:
        assert store.next_season(content, 200.0)
        assert store._logs(conn, "rumors", 1, sqlite_world._rumor) == []


def test_a_failed_archive_write_keeps_everything_and_still_changes_season(store, content, monkeypatch):
    _fill(store, "一季")
    _roll(store, content, 100.0)
    _fill(store, "二季")

    def broken(*args, **kwargs):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(log_archive, "_write_archive", broken)
    _roll(store, content, 200.0)
    assert store.get_season_number() == 3  # 換季照常
    assert _seasons(store, "rumors") == [1, 2] and _seasons(store, "battle_rounds") == [1, 2]
    assert not log_archive.archive_path(store.db.path).exists()
    monkeypatch.undo()
    _roll(store, content, 300.0)  # 修好了：下一次換季把第 1、2 季一起搬
    assert _seasons(store, "rumors") == []
    assert sorted({s for (s,) in _archive(store, "SELECT season FROM rumors")}) == [1, 2]


def test_a_failed_delete_keeps_the_main_rows_and_a_retry_does_not_duplicate(store, content):
    _fill(store, "一季")
    _roll(store, content, 100.0)
    _fill(store, "二季")
    with store.db.transaction() as conn:
        conn.execute("CREATE TRIGGER no_delete BEFORE DELETE ON rumors BEGIN SELECT RAISE(ABORT, '刪不掉'); END")
    _roll(store, content, 200.0)
    assert store.get_season_number() == 3
    assert _seasons(store, "rumors") == [1, 2]
    assert _seasons(store, "battle_rounds") == [1, 2]  # 同一個 savepoint：回合紀錄也沒刪
    assert len(_archive(store, "SELECT id FROM rumors")) == 2  # 封存檔多一份備用
    with store.db.transaction() as conn:
        conn.execute("DROP TRIGGER no_delete")
    _roll(store, content, 300.0)
    assert _seasons(store, "rumors") == []
    rows = _archive(store, "SELECT id FROM rumors")
    assert len(rows) == len({r for (r,) in rows}) == 4  # 同一個流水號照蓋，不重複
    assert len(_archive(store, "SELECT id FROM battle_rounds")) == 4


def test_a_season_change_rolled_back_after_archiving_loses_nothing(store, content):
    """封存檔已經 COMMIT、換季那一筆卻撤回了：主檔原封不動（還是第 2 季、第 1 季的傳聞還在），封存檔多一份；再換一次不重複。"""
    _fill(store, "一季")
    _roll(store, content, 100.0)
    _fill(store, "二季")
    store.mutate_season(lambda s: setattr(s, "ended", True))
    with pytest.raises(RuntimeError, match="撤回"):
        with store.action_lock():
            assert store.next_season(content, 200.0)
            raise RuntimeError("撤回")
    assert store.get_season_number() == 2
    assert _seasons(store, "rumors") == [1, 2]
    assert len(_archive(store, "SELECT id FROM rumors")) == 2
    assert store.next_season(content, 200.0)
    assert _seasons(store, "rumors") == [2]
    assert len(_archive(store, "SELECT id FROM rumors")) == 2
    assert len(_archive(store, "SELECT id FROM battle_rounds")) == 2


def test_the_archive_sits_next_to_the_database(tmp_path):
    assert log_archive.archive_path(tmp_path / "tianxia.db") == tmp_path / "tianxia-archive.sqlite"
