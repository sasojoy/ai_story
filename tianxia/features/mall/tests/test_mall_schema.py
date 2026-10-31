"""資料庫第 6 版（商城架構設計 4.9）：帳本、購買紀錄、月卡三張表。新檔一次建好；第 5 版的舊檔在同一筆交易裡就地升上來、
原本的資料不掉；升到一半出錯整筆撤回、檔還是第 5 版。"""
from __future__ import annotations

import sqlite3

import pytest

from tianxia import database
from tianxia.database import Database

MALL_TABLES = {"mall_ledger", "mall_purchases", "mall_entitlements"}


def _tables(path) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        conn.close()


def _version(path) -> int:
    conn = sqlite3.connect(path)
    try:
        return conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()


def _version_5_file(path) -> None:
    """照第 1～5 版的句子建一個舊檔，放一列角色與一個綁了角色的帳號。"""
    conn = sqlite3.connect(path)
    try:
        for statement in (*database.SCHEMA_V1, *database.SCHEMA_V2_TABLES, *database.SCHEMA_V3_TABLES,
                          *database.SCHEMA_V4_TABLES, *database.SCHEMA_V5_TABLES):
            conn.execute(statement)
        conn.execute("INSERT INTO characters (key, name, is_bot, faction, data) VALUES ('沈青衫', '沈青衫', 0, NULL, '{}')")
        conn.execute("INSERT INTO accounts (id, character, character_key, created) VALUES (1, '沈青衫', '沈青衫', 1.0)")
        conn.execute("PRAGMA user_version = 5")
        conn.commit()
    finally:
        conn.close()


@pytest.mark.smoke
def test_new_file_is_version_6(tmp_path):
    path = tmp_path / "new.db"
    db = Database(path)
    db.close()
    assert database.SCHEMA_VERSION >= 6  # 商城是第 6 版；之後再升版（第 7 版真人量表）商城的表照樣在
    assert _version(path) == database.SCHEMA_VERSION
    assert MALL_TABLES <= _tables(path)


def test_version_5_file_upgrades_in_place(tmp_path):
    path = tmp_path / "old.db"
    _version_5_file(path)
    assert _version(path) == 5 and not (MALL_TABLES & _tables(path))
    db = Database(path)
    try:
        with db.snapshot() as conn:
            assert conn.execute("SELECT name FROM characters").fetchall()[0]["name"] == "沈青衫"
            assert conn.execute("SELECT character FROM accounts WHERE id = 1").fetchone()["character"] == "沈青衫"
            assert conn.execute("SELECT COUNT(*) FROM mall_ledger").fetchone()[0] == 0
    finally:
        db.close()
    assert _version(path) == database.SCHEMA_VERSION  # 一路升到現在這一版
    assert MALL_TABLES <= _tables(path)


def test_failed_upgrade_leaves_version_5(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    _version_5_file(path)
    broken = (database.SCHEMA_V6_TABLES[0], "CREATE TABLE this is not sql")
    monkeypatch.setitem(database.MIGRATIONS, 5, broken)
    with pytest.raises(sqlite3.OperationalError):
        Database(path)
    assert _version(path) == 5
    assert not (MALL_TABLES & _tables(path))  # 第一句建的表也跟著撤回
