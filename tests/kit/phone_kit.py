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


def unbind(db, login: str) -> None:
    """解綁手機（remove_login）：帳本不動，封測的手機編號照舊占著。"""
    AccountStore(db).remove_login(login, "phone")
