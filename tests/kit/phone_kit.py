"""綁手機才能用（帳號與客服第 205 批；設計 4.5）的測試共用小工具：開 identity＋假金鑰、開關 phone_gate、建帳號（要不要綁手機）。
peers、bounties、mall、looks 四包的 test_*_phone_gate.py 共用。"""
from __future__ import annotations

import json

from tianxia.accounts import AccountStore
from tianxia.core import identity_base

KEY = "k" * 32
PHONE_A = "a" * 64  # logins.subject 存的是加金鑰的雜湊 hex（第 203 批）；測試直接寫一個 64 字的值
PHONE_B = "b" * 64


def keyed(monkeypatch, tmp_path) -> None:
    """金鑰讀得到（identity_base.on 才會真）；identity 的開關另外由 gate 開。"""
    path = tmp_path / "identity.json"
    path.write_text(json.dumps({"key": KEY}), encoding="utf-8")
    monkeypatch.setattr(identity_base, "KEY_FILE", path)


def gate(content, on: bool, identity: bool = True) -> None:
    """identity 開關與 phone_gate。identity=False 是整包關著（不管 phone_gate）。"""
    content.config.identity.enabled = identity
    content.config.identity.phone_gate = on


def account(db, name: str, login: str, phone: str | None = None) -> None:
    """建一個密碼帳號、綁到名號 name；phone 給了就再綁一列 provider='phone'（同 tests/core/test_identity_base.py 的 _bind）。"""
    store = AccountStore(db)
    store.register(login, "secret1")
    store.bind_character(login, name)
    if phone:
        store.add_login(login, "phone", phone, "09*****678")


def bind(db, login: str, phone: str) -> None:
    """已經有的帳號再綁一支手機（add_login）。"""
    AccountStore(db).add_login(login, "phone", phone, "09*****678")


def unbind(db, login: str) -> None:
    """解綁手機（remove_login）：帳本不動，封測的手機編號照舊占著。"""
    AccountStore(db).remove_login(login, "phone")


def hold(db, login: str, until: float) -> int:
    """第 208 批：這個帳號在旁檔記一筆「只剩過期一種」的扣押（holds，到 until 為止）；回 accounts.id。旁檔跟著 TIANXIA_DB（identity_base.side_file）。"""
    import sqlite3

    account_id = AccountStore(db).account_id(login)
    path = identity_base.side_file()
    identity_base.ensure_schema(path, "hold", identity_base.HOLD_TABLES, identity_base.META_COLUMNS)
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO holds (account_id, until) VALUES (?, ?) ON CONFLICT (account_id) DO UPDATE SET until = excluded.until",
                     (account_id, until))
    return account_id
