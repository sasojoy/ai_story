"""帳號綁定的旁檔（features/identity/store.py；帳號與客服第 201 批）：五張表、檢查並記一筆、跟著 TIANXIA_DB。"""
import sqlite3

from tianxia.features.identity import store as idstore


def test_store_tables_and_count_and_record(tmp_path):
    path = tmp_path / "x-identity.sqlite"
    s = idstore.IdentityStore(path)
    with sqlite3.connect(path) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert {"bindings_meta", "unbound", "challenges", "counters", "session_auth"} <= tables
    assert mode == "wal"
    assert [s.count_and_record("send:ip:1", 60, 3, 100 + i) for i in range(4)] == [True, True, True, False]
    assert s.count_and_record("send:ip:2", 60, 3, 101) is True  # 別的桶分開算
    assert s.count_and_record("send:ip:1", 60, 3, 159) is False  # 還在窗裡
    assert s.count_and_record("send:ip:1", 60, 3, 161) is True  # 第一筆出了窗
    assert s.count_and_record("x", 60, 0, 1) is False


def test_store_verified_unbound_and_session_auth(tmp_path):
    s = idstore.IdentityStore(tmp_path / "x-identity.sqlite")
    assert s.verified_at(1, "phone") is None
    s.record_verified(1, "phone", "h1", 50.0)
    s.record_verified(1, "phone", "h1", 70.0)
    assert s.verified_at(1, "phone") == 70.0 and s.verified_at(2, "phone") is None
    assert s.unbound_since("h9", "phone") is None
    s.record_unbound("h9", "phone", 1, 80.0)
    s.record_unbound("h9", "phone", 2, 90.0)
    assert s.unbound_since("h9", "phone") == 90.0
    assert s.session_auth("tok") is None
    s.set_session_auth("tok", "line", 5.0)
    s.set_session_auth("tok", "phone", 6.0)
    assert s.session_auth("tok") == ("phone", 6.0)


def test_store_follows_tianxia_db(tmp_path, monkeypatch):
    monkeypatch.setenv("TIANXIA_DB", str(tmp_path / "game.db"))
    assert idstore.default_side_path() == tmp_path / "game-identity.sqlite"
    assert idstore.side_path(tmp_path / "a" / "b.db") == tmp_path / "a" / "b-identity.sqlite"
    assert not (tmp_path / "game-identity.sqlite").exists()  # 沒人叫到 IdentityStore 不建
