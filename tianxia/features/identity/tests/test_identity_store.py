"""帳號綁定的旁檔（features/identity/store.py；帳號與客服第 201 批）：五張表、檢查並記一筆、跟著 TIANXIA_DB。
第 202 批多兩張：第三方登入的一次性單（讀完就刪、過期當沒有）、還沒開帳號的身分（過期當沒有）；舊旁檔照開、補建。"""
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


B = 1000.0  # 第 203 批的測試時間起點


def _count(path, bucket):
    with sqlite3.connect(path) as conn:
        return conn.execute("SELECT COUNT(*) FROM counters WHERE bucket = ?", (bucket,)).fetchone()[0]


def test_check_all_and_record_is_all_or_nothing(tmp_path):
    """第 203 批：多格一次記；有一格滿了一筆都不記、回那一格的名字（旁檔直接數）。"""
    path = tmp_path / "x-identity.sqlite"
    s = idstore.IdentityStore(path)
    buckets = [("a", 60, 2), ("b", 3600, 1), ("c", 86400, 5)]
    assert s.check_all_and_record(buckets, B) is None
    assert [_count(path, n) for n in "abc"] == [1, 1, 1]
    assert s.check_all_and_record(buckets, B + 1) == "b"
    assert [_count(path, n) for n in "abc"] == [1, 1, 1]  # a、c 也沒記
    assert s.check_all_and_record([("a", 60, 2), ("c", 86400, 5)], B + 2) is None
    assert s.check_all_and_record([("a", 60, 2)], B + 3) == "a"
    assert s.check_all_and_record([("a", 60, 2)], B + 61) is None  # 第一筆出了窗
    assert s.check_all_and_record([], B) is None


def test_challenges_new_voids_old_tries_and_trusted_devices(tmp_path):
    s = idstore.IdentityStore(tmp_path / "x-identity.sqlite")
    s.put_challenge("c1", "login", "phone", "subj", "09*****678", "h1", B + 300, B)
    s.put_challenge("other", "login", "phone", "subj2", "09*****111", "h9", B + 300, B)
    assert s.challenge("c1")["code_hmac"] == "h1" and s.challenge("c1")["channel"] == "phone"
    s.put_challenge("c2", "login", "phone", "subj", "09*****678", "h2", B + 400, B + 10)
    assert s.challenge("c1") is None and s.challenge("c2")["display"] == "09*****678"  # 新碼作廢舊碼
    assert s.challenge("other") is not None  # 別人的單不動
    assert [s.bump_tries("c2", 3) for _ in range(3)] == [1, 2, 3]
    assert s.challenge("c2") is None  # 到 cap 刪單
    assert s.bump_tries("c2", 3) is None
    s.drop_challenge("other")
    assert s.challenge("other") is None
    assert not s.is_trusted("dev1", "subj")
    s.trust_device("dev1", "subj", B)
    s.trust_device("dev1", "subj", B + 5)
    assert s.is_trusted("dev1", "subj") and not s.is_trusted("dev1", "subj2") and not s.is_trusted("dev2", "subj")
    s.put_pending("tok", "email", "subj", expires=B + 600, now=B, display="r*@gmail.com")
    with sqlite3.connect(s.path) as conn:
        assert conn.execute("SELECT provider, subject, display, expires FROM pending").fetchall() == [
            ("email", "subj", "r*@gmail.com", B + 600)]


def test_old_side_file_gets_the_new_columns(tmp_path):
    """第 201 批開的旁檔（challenges 只有七欄）：開檔補 channel、subject_hmac、display，舊列留著。"""
    path = tmp_path / "old-identity.sqlite"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE challenges (id TEXT PRIMARY KEY, purpose TEXT NOT NULL, account_id INTEGER, code_hmac TEXT NOT NULL, "
            "tries INTEGER NOT NULL DEFAULT 0, expires REAL NOT NULL, created REAL NOT NULL)")
        conn.execute("INSERT INTO challenges VALUES ('old', 'login', NULL, 'h', 0, 9e9, 1)")
    s = idstore.IdentityStore(path)
    with sqlite3.connect(path) as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(challenges)")]
    assert cols[-3:] == ["channel", "subject_hmac", "display"]
    assert s.challenge("old")["code_hmac"] == "h"
    idstore.IdentityStore(path)  # 再開一次不重複補


def test_store_follows_tianxia_db(tmp_path, monkeypatch):
    monkeypatch.setenv("TIANXIA_DB", str(tmp_path / "game.db"))
    assert idstore.default_side_path() == tmp_path / "game-identity.sqlite"
    assert idstore.side_path(tmp_path / "a" / "b.db") == tmp_path / "a" / "b-identity.sqlite"
    assert not (tmp_path / "game-identity.sqlite").exists()  # 沒人叫到 IdentityStore 不建


def test_ticket_is_one_time_and_expires(tmp_path):
    s = idstore.IdentityStore(tmp_path / "x-identity.sqlite")
    s.put_ticket("h1", "line", "login", "b1", "no-1", "ver-1", expires=200.0, now=100.0)
    s.put_ticket("h2", "google", "login", "b2", "no-2", "ver-2", expires=150.0, now=100.0)
    assert s.take_ticket("h1", 199.0) == {"provider": "line", "purpose": "login", "browser_hash": "b1", "nonce": "no-1", "verifier": "ver-1"}
    assert s.take_ticket("h1", 199.0) is None  # 讀完就刪：不能重放
    assert s.take_ticket("h2", 150.0) is None  # 到期那一刻就不算
    assert s.take_ticket("nope", 1.0) is None
    s.put_ticket("h3", "line", "login", "b3", "n", "v", expires=120.0, now=100.0)
    s.take_ticket("other", 130.0)  # 順手清掉過期的
    with sqlite3.connect(s.path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM oauth_tickets").fetchone()[0] == 0


def test_pending_expires_and_drops(tmp_path):
    s = idstore.IdentityStore(tmp_path / "x-identity.sqlite")
    s.put_pending("t1", "line", "U1", expires=200.0, now=100.0)
    assert s.get_pending("t1", 150.0) == ("line", "U1")
    assert s.get_pending("t1", 150.0) == ("line", "U1")  # 讀不刪：建角色失敗可以再試
    assert s.get_pending("t1", 200.0) is None
    s.put_pending("t2", "google", "G2", expires=300.0, now=100.0)
    s.drop_pending("t2")
    assert s.get_pending("t2", 150.0) is None
    s.drop_pending("t2")  # 沒有也不出錯


def test_old_side_file_gets_the_new_tables(tmp_path):
    path = tmp_path / "old-identity.sqlite"
    with sqlite3.connect(path) as conn:  # 第 201 批的旁檔：只有五張表，裡面有東西
        for sql in idstore.TABLES[:7]:
            conn.execute(sql)
        conn.execute("INSERT INTO counters (bucket, at) VALUES ('x', 1.0)")
    s = idstore.IdentityStore(path)
    with sqlite3.connect(path) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        kept = conn.execute("SELECT COUNT(*) FROM counters").fetchone()[0]
    assert {"oauth_tickets", "pending"} <= tables and kept == 1
    s.put_pending("t", "line", "U", expires=9.0, now=1.0)
    assert s.get_pending("t", 2.0) == ("line", "U")
