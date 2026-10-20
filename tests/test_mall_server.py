"""商城的伺服器那一側（商城架構設計 4.4、4.7、4.10）：開關關著時所有商城的 API 都 404；開著時看得到商品、買得到（在行動鎖裡，
同一個編號送兩次只扣一次）、看得到自己的紀錄；管理者查帳、補發、扣回、退一筆。另驗主機端的對帳腳本。"""
from __future__ import annotations

import csv
import io
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server
from tianxia.characters import name_key
from tianxia.database import open_database
from tianxia.wallet import Wallet

pytestmark = pytest.mark.slow  # 每一條都用真實內容建角色（超過一秒）

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def fresh_server(monkeypatch):
    from tianxia import accounts

    monkeypatch.setattr(accounts, "SCRYPT_PARAMS", {"n": 2, "r": 1, "p": 1, "dklen": 32})  # 這裡測的不是密碼
    monkeypatch.setattr(server.CONTENT.config, "auto_open_first_season", True)
    monkeypatch.setattr(server.CONTENT.config, "admins", list(server.CONTENT.config.admins))
    monkeypatch.setattr(server.CONTENT.config.mall, "enabled", True)
    monkeypatch.setattr(server.CONTENT.config.mall, "beta_grant", 5000)
    for store in (server.LOGIN_FAILURES, server.SESSIONS, server.GAMES):
        store.clear()
    server.WORLD_GAME = None
    server.QUEUE = None
    yield
    for store in (server.LOGIN_FAILURES, server.SESSIONS, server.GAMES):
        store.clear()
    server.WORLD_GAME = None


def _player(login="shen_01", name="沈青衫") -> TestClient:
    client = TestClient(server.app)
    client.post("/api/register", json={"login": login, "password": "secret-pw", "again": "secret-pw"})
    client.post("/api/character", json={"name": name})
    client.post("/api/do/skip_tutorial", json={})
    return client


def _wallet() -> Wallet:
    return Wallet(open_database())


def test_everything_is_404_when_off(monkeypatch):
    monkeypatch.setattr(server.CONTENT.config.mall, "enabled", False)
    client = _player()
    assert client.get("/api/mall").status_code == 404
    assert client.get("/api/mall/records").status_code == 404
    assert client.post("/api/mall/buy", json={"item": "pills_5", "ref": "abcdefgh1"}).status_code == 404
    assert client.post("/api/admin/mall", json={"name": "沈青衫"}).status_code == 404
    assert client.post("/api/do/mall_reissue", json={"name": "沈青衫", "amount": 1, "note": "x"}).status_code == 404
    assert _wallet().balance(name_key("沈青衫")) == 0  # 關著不發


def test_buy_and_records():
    client = _player()
    view = client.get("/api/mall").json()
    assert view["balance"] == 5000 and {row["id"] for row in view["items"]} >= {"pills_5", "card_30"}
    first = client.post("/api/mall/buy", json={"item": "pills_5", "ref": "click-0001"}).json()
    again = client.post("/api/mall/buy", json={"item": "pills_5", "ref": "click-0001"}).json()  # 連點、逾時重送
    assert "買下「回體丹五顆」" in first["message"] and "已經買好" in again["message"]  # message 照其他動作轉成 HTML
    assert first["mall"]["balance"] == again["mall"]["balance"] == 4900
    records = client.get("/api/mall/records").json()
    assert [row["reason"] for row in records["ledger"]] == ["購買", "封測發放"]
    assert len(records["purchases"]) == 1


def test_a_missing_or_odd_ref_gets_one_from_the_server():
    client = _player()
    client.post("/api/mall/buy", json={"item": "pills_5"})
    client.post("/api/mall/buy", json={"item": "pills_5", "ref": "<script>"})
    assert _wallet().balance(name_key("沈青衫")) == 4800  # 各自一筆（伺服器產的編號）


def test_admin_tools_need_an_admin():
    client = _player()
    assert client.post("/api/admin/mall", json={"name": "沈青衫"}).status_code == 403
    assert client.post("/api/do/mall_reissue", json={"name": "沈青衫", "amount": 100, "note": "x"}).status_code == 400


def test_admin_reissue_ledger_and_refund():
    client = _player()
    client.post("/api/mall/buy", json={"item": "pills_5", "ref": "click-0002"})
    server.CONTENT.config.admins = ["沈青衫"]  # 名號建好之後才當管理者（玩家不能取管理者的名號）
    out = client.post("/api/do/mall_reissue", json={"name": "沈青衫", "amount": 300, "note": "維修補償", "ref": "admin-0001"}).json()
    assert "補發 300" in out["message"]
    ledger = client.post("/api/admin/mall", json={"name": "沈青衫"}).json()
    assert ledger["balance"] == 5200 and ledger["ledger"][0]["admin"] == "沈青衫"
    pid = ledger["purchases"][0]["id"]
    out = client.post("/api/do/mall_refund", json={"name": "沈青衫", "id": pid, "note": "買錯了"}).json()
    assert "元寶 +100" in out["message"]
    assert _wallet().balance(name_key("沈青衫")) == 5300


def test_export_script_writes_every_row(tmp_path):
    db_path = tmp_path / "export.db"
    wallet = Wallet(open_database(db_path))
    wallet.post("沈青衫", 5000, "grant", "grant:beta:沈青衫", time=1_760_000_000.0)
    wallet.post("沈青衫", -100, "buy", "buy:沈青衫:a", time=1_760_000_060.0)
    out = tmp_path / "ledger.csv"
    run = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "mall_ledger.py"), "--db", str(db_path), "--out", str(out)],
        capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"}, check=True,
    )
    rows = list(csv.reader(io.StringIO(out.read_text(encoding="utf-8-sig"))))
    assert rows[0][0] == "編號" and len(rows) == 3
    assert [row[4] for row in rows[1:]] == ["5000", "-100"] and rows[2][-1] == "4900"
    assert "負的餘額：沒有" in run.stderr
