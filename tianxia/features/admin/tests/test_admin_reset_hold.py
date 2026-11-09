"""管理者重設密碼之後的扣押（帳號與客服第 208 批；設計 6.4）：identity 開著時重設成功記 reset_hold_hours 的扣押（reset_holds）與一則「帳號」紀錄
（account_notes，identity 包下一輪寫進存檔）；回給管理者的字跟 identity 關著時逐字相同；關著不建旁檔、不寫任何東西。"""
import json
import sqlite3

import pytest
import server
from server_kit import (  # noqa: F401
    _no_landing, _no_preset_recipes, _player, cheap_password_hashing, client, fresh_server_memory,
    model_breaker_closed, save_dir, scheduler_off, season_already_open,
)

from tianxia import database
from tianxia.accounts import STRICT_SHORT_PASSWORD, AccountStore
from tianxia.core import identity_base

pytestmark = pytest.mark.whole_content


def _reset(client, monkeypatch):
    _player(client, password="secret-pw-12")  # identity 開著全體 12 字（第 209 批）
    monkeypatch.setattr(server.CONTENT.config, "admins", ["沈青衫"])
    # 目標在管理者名單上：identity 開著時臨時密碼要 12 字（第 207 批），關著照舊；用 14 字兩邊都過
    return client.post("/api/admin/reset_password", json={"target": "沈青衫", "temp": "temp-pass-1234"}).json()


def test_reset_records_hold_and_note_when_on(client, monkeypatch, tmp_path):
    key = tmp_path / "identity.json"
    key.write_text(json.dumps({"key": "k" * 32}), encoding="utf-8")
    monkeypatch.setattr(identity_base, "KEY_FILE", key)
    monkeypatch.setattr(server.CONTENT.config.identity, "enabled", True)
    before = server.time.time()
    out = _reset(client, monkeypatch)
    assert out == {"message": "已重設 shen_01 的密碼。"}
    aid = AccountStore(database.open_database()).account_id("shen_01")
    hours = server.CONTENT.config.identity.reset_hold_hours
    with sqlite3.connect(identity_base.side_file()) as conn:
        until = conn.execute("SELECT until FROM reset_holds WHERE account_id = ?", (aid,)).fetchone()[0]
        notes = conn.execute("SELECT text, state, at FROM account_notes WHERE account_id = ?", (aid,)).fetchall()
    assert [(t, s) for t, s, _at in notes] == [(identity_base.NOTE_ADMIN_RESET.format(hours=hours), 0)]
    at = notes[0][2]
    assert before <= at <= server.time.time() and until == at + hours * 3600  # 現實時間由殼的 shell.time 給
    assert identity_base.reset_held(aid, until - 1) is True and identity_base.reset_held(aid, until) is False


def test_reset_off_same_reply_and_no_side_file(client, monkeypatch):
    assert server.CONTENT.config.identity.enabled is False
    out = _reset(client, monkeypatch)
    assert out == {"message": "已重設 shen_01 的密碼。"}
    assert not identity_base.side_file().exists()


def test_failed_reset_writes_nothing(client, monkeypatch, tmp_path):
    key = tmp_path / "identity.json"
    key.write_text(json.dumps({"key": "k" * 32}), encoding="utf-8")
    monkeypatch.setattr(identity_base, "KEY_FILE", key)
    monkeypatch.setattr(server.CONTENT.config.identity, "enabled", True)
    _player(client, password="secret-pw-12")  # identity 開著全體 12 字（第 209 批）
    monkeypatch.setattr(server.CONTENT.config, "admins", ["沈青衫"])
    out = client.post("/api/admin/reset_password", json={"target": "沈青衫", "temp": "123"}).json()
    assert out == {"message": STRICT_SHORT_PASSWORD}  # 目標在名單上、identity 開著：12 字那一句（第 207 批）
    aid = AccountStore(database.open_database()).account_id("shen_01")
    assert identity_base.reset_held(aid, server.time.time()) is False  # 旁檔在不在都一樣（登入那一下開著就會記 session_auth）
    if identity_base.side_file().exists():
        with sqlite3.connect(identity_base.side_file()) as conn:
            have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            assert "account_notes" not in have or conn.execute("SELECT COUNT(*) FROM account_notes").fetchone()[0] == 0
