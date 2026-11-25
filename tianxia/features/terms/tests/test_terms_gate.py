"""條款第 249 批：必須同意而沒同意的帳號，會改東西的請求（經殼 server._game、不是 GET）由伺服器回 403 與 terms_base.GATE_NEED。
企劃者 2026-11-21「照這個做，兩處可以動」（殼 _game、核心 terms_base）。讀取、登入登出、條款自己、客服、管理者、ask 不擋；
條款關著 gate_problem 第一行回 None、連 must 都不問。_game 不讀 PlayerState.bot：被擋的回應只有那一句，分不出誰是假人
（假人沒有帳號、不經伺服器）。"""
from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import server
from tianxia.core import terms_base
from tianxia.features.terms import audit, rules
from tianxia.features.terms import routes as terms_routes
from tianxia.features.terms.store import ConsentStore

ROOT = Path(__file__).resolve().parents[4]
PW = "secret-pw"
DAY = 86400


def _clear():
    for store in (server.LOGIN_FAILURES, server.SESSIONS, server.GAMES, server.REGISTRATIONS):
        store.clear()
    server.WORLD_GAME = None


@pytest.fixture
def gate(monkeypatch):
    """回一支 make(login, name, ticks=False)：關著條款註冊（不記同意）＋建角色，最後才打開開關。ticks=True 是照註冊頁送兩個勾選。"""
    from tianxia import accounts

    monkeypatch.setattr(accounts, "SCRYPT_PARAMS", {"n": 2, "r": 1, "p": 1, "dklen": 32})
    monkeypatch.setattr(server.CONTENT.config, "auto_open_first_season", True)
    monkeypatch.setattr(server.CONTENT.config.terms, "enabled", False)
    _clear()

    def make(login, name, ticks=False):
        c = TestClient(server.app)
        body = {"login": login, "password": PW, "again": PW}
        if ticks:
            server.CONTENT.config.terms.enabled = True
            body.update(age_ok=True, terms_agree=True, terms_version=rules.load()["version"])
        assert c.post("/api/register", json=body).status_code == 200
        assert c.post("/api/character", json={"name": name, "gender": "男"}).status_code == 200
        server.CONTENT.config.terms.enabled = False
        return c

    yield make
    _clear()


def _on(monkeypatch):
    monkeypatch.setattr(server.CONTENT.config.terms, "enabled", True)


def _blocked(r):
    assert r.status_code == 403, (r.status_code, r.text[:200])
    assert r.json() == {"detail": terms_base.GATE_NEED}


def _passed(r):
    assert r.status_code != 403, r.text[:200]


# ── 擋的 ──

def test_gate_blocks_choose(gate, monkeypatch):
    c = gate("gate_01", "甲未簽")
    _on(monkeypatch)
    _blocked(c.post("/api/choose", json={"id": "act:none"}))


def test_gate_blocks_a_main_action(gate, monkeypatch):
    c = gate("gate_02", "乙未簽")
    _on(monkeypatch)
    _blocked(c.post("/api/do/hints_off", json={"value": True}))


def test_gate_blocks_an_outlock_op(gate, monkeypatch):
    c = gate("gate_03", "丙未簽")
    _on(monkeypatch)
    assert "tavern_ask" in server.OUTLOCK_OPS
    _blocked(c.post("/api/do/tavern_ask", json={"text": "近來可好"}))


def test_gate_blocks_menxia(gate, monkeypatch):
    c = gate("gate_04", "丁未簽")
    _on(monkeypatch)
    _blocked(c.post("/api/menxia/heal", json={}))


def test_gate_blocks_a_mall_purchase(gate, monkeypatch):
    c = gate("gate_05", "戊未簽")
    _on(monkeypatch)
    monkeypatch.setattr(server.CONTENT.config.mall, "enabled", True)
    _blocked(c.post("/api/mall/buy", json={"item": "none", "ref": "gate-05"}))


def test_gate_blocks_mail(gate, monkeypatch):
    c = gate("gate_06", "己未簽")
    _on(monkeypatch)
    monkeypatch.setattr(server.CONTENT.config.mail, "enabled", True)
    _blocked(c.post("/api/mail/send", json={"name": "誰", "text": "久仰"}))


def test_gate_blocks_travel(gate, monkeypatch):
    c = gate("gate_07", "庚未簽")
    _on(monkeypatch)
    _blocked(c.post("/api/travel", json={"place": "none", "mode": "walk"}))


def test_gate_blocks_an_old_consent_when_update_must_is_on(gate, monkeypatch):
    c = gate("gate_08", "辛舊簽")
    _on(monkeypatch)
    monkeypatch.setattr(server.CONTENT.config.terms, "update_must", True)
    terms_routes.consent_store(server).record("gate_08", "2026-11-v0", "register", 1.0)
    _blocked(c.post("/api/do/hints_off", json={"value": True}))


# ── 不擋的 ──

def test_gate_lets_every_get_through(gate, monkeypatch):
    c = gate("gate_11", "壬未簽")
    _on(monkeypatch)
    assert c.get("/api/main").status_code == 200  # 輪詢照回 200（同意那一層底下要畫得出畫面）
    assert c.get("/api/me").status_code == 200


def test_gate_lets_login_and_logout_through(gate, monkeypatch):
    c = gate("gate_12", "癸未簽")
    _on(monkeypatch)
    assert c.post("/api/logout", json={}).status_code == 200  # 同意那一層的「不同意」導向登出
    assert c.post("/api/login", json={"login": "gate_12", "password": PW}).status_code == 200
    _blocked(c.post("/api/do/hints_off", json={"value": True}))  # 重登之後照樣擋


def test_gate_lets_the_terms_routes_through_and_agree_unblocks_the_next_post(gate, monkeypatch):
    c = gate("gate_13", "子未簽")
    _on(monkeypatch)
    _blocked(c.post("/api/do/hints_off", json={"value": True}))
    assert TestClient(server.app).get("/api/terms/version").status_code == 200
    got = c.get("/api/terms").json()
    assert got["need"] == rules.MUST
    assert c.post("/api/terms/agree", json={"version": got["version"]}).json()["need"] == ""
    assert c.post("/api/do/hints_off", json={"value": True}).status_code == 200  # 按了同意，下一個請求就過


def test_gate_lets_support_through(gate, monkeypatch):
    """沒同意的玩家也要找得到客服（客服的路由不經 _game）。"""
    c = gate("gate_14", "丑未簽")
    _on(monkeypatch)
    monkeypatch.setattr(server.CONTENT.config.support, "enabled", True)
    _passed(c.post("/api/support/ticket", json={"category": "account", "body": "條款要先按同意嗎"}))
    _passed(c.get("/api/support/mine"))


def test_gate_lets_an_admin_through(gate, monkeypatch):
    """管理者（名單上的名號）沒同意過照樣打得了管理者工具與一般動作：不然會把自己鎖在管理頁外。"""
    c = gate("gate_15", "寅掌事")
    _on(monkeypatch)
    monkeypatch.setattr(server.CONTENT.config, "admins", [*server.CONTENT.config.admins, "寅掌事"])
    assert c.post("/api/admin/player", json={"name": "寅掌事"}).status_code == 200
    assert c.post("/api/do/hints_off", json={"value": True}).status_code == 200


def test_gate_lets_an_old_consent_inside_the_grace_days_through(gate, monkeypatch):
    """update_must 關著（預設）：同意過舊版的人是 ask（或過了考慮期是空字串），網頁跳改版頁、伺服器不擋。"""
    c = gate("gate_16", "卯舊簽")
    _on(monkeypatch)
    terms_routes.consent_store(server).record("gate_16", "2026-11-v0", "register", 1.0)
    assert c.post("/api/do/hints_off", json={"value": True}).status_code == 200


def test_gate_lets_a_ticked_registration_through(gate, monkeypatch):
    c = gate("gate_17", "辰新簽", ticks=True)
    _on(monkeypatch)
    assert c.post("/api/do/hints_off", json={"value": True}).status_code == 200


def test_gate_off_never_asks_the_hook(gate, monkeypatch):
    """關著：gate_problem 第一行回 None，連 must 都不問——請求走的跟沒有這一批一模一樣（逐位元組由 doorstep 軌的 closed 段守）。"""
    c = gate("gate_18", "巳未簽")
    asked = []
    monkeypatch.setattr(terms_base._HOOK, "must", lambda key: asked.append(key) or True)
    assert c.post("/api/do/hints_off", json={"value": True}).status_code == 200
    assert c.post("/api/choose", json={"id": "act:none"}).status_code != 403
    assert asked == []


def test_gate_lets_through_and_logs_when_the_side_file_breaks(gate, monkeypatch, caplog):
    c = gate("gate_19", "午未簽")
    _on(monkeypatch)

    def broken(key):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(terms_base._HOOK, "must", broken)
    with caplog.at_level(logging.ERROR, logger=terms_base.__name__):
        assert c.post("/api/do/hints_off", json={"value": True}).status_code == 200
    assert any("gate check failed" in r.getMessage() for r in caplog.records)


def test_gate_detail_is_one_line_with_no_name_in_it(gate, monkeypatch):
    """被擋的回應只有那一句（不帶名號、帳號、版號）：_game 不讀 PlayerState.bot，誰被擋都一樣。"""
    c = gate("gate_20", "未未簽")
    _on(monkeypatch)
    r = c.post("/api/do/hints_off", json={"value": True})
    _blocked(r)
    assert "未未簽" not in r.text and "gate_20" not in r.text and rules.load()["version"] not in r.text


def test_the_bot_runner_never_goes_through_the_gate():
    """假人程式那一側不 import server：terms 包不掛 hook，gate_problem 回 None（核心那一條守 None）。"""
    text = (ROOT / "run_bots.py").read_text(encoding="utf-8")
    assert "import server" not in text and "from server" not in text


# ── 掛鉤的 must（不經 HTTP）──

def _shell(db: Path, now: float, **cfg):
    terms = SimpleNamespace(enabled=True, grace_days=15, update_must=False)
    for k, v in cfg.items():
        setattr(terms, k, v)
    return SimpleNamespace(CONTENT=SimpleNamespace(config=SimpleNamespace(terms=terms)), default_path=lambda: db,
                           time=SimpleNamespace(time=lambda: now))


def test_hook_must_ask_is_not_must_inside_or_after_the_grace_days(tmp_path):
    data = rules.load()
    start = rules.published_at(data)
    db = tmp_path / "g.db"
    ConsentStore(audit.side_path(db)).record("ab", "2026-11-v0", "register", 1.0)
    for now in (start + DAY, start + 99 * DAY):
        assert terms_routes._Hook(_shell(db, now)).must("ab") is False
    assert terms_routes._Hook(_shell(db, start + DAY, update_must=True)).must("ab") is True
    assert terms_routes._Hook(_shell(db, start + DAY)).must("cd") is True  # 從沒同意過


def test_hook_must_cache_is_per_side_file(tmp_path):
    """快取的鍵含旁檔路徑：A 庫同意過的同名帳號，換到 B 庫照樣 must（測試每條換一個資料庫，不能串）。"""
    ver = rules.load()["version"]
    a, b = tmp_path / "a.db", tmp_path / "b.db"
    ConsentStore(audit.side_path(a)).record("zhang", ver, "gate", 1.0)
    shell = _shell(a, time.time())
    hook = terms_routes._Hook(shell)
    assert hook.must("zhang") is False and hook.must("zhang") is False
    shell.default_path = lambda: b
    assert hook.must("zhang") is True


# ── 主機用的：唯讀清單與啟動警告 ──

def _world_with_two_accounts(tmp_path, monkeypatch):
    from tianxia import accounts
    from tianxia.accounts import AccountStore
    from tianxia.database import open_database

    monkeypatch.setattr(accounts, "SCRYPT_PARAMS", {"n": 2, "r": 1, "p": 1, "dklen": 32})
    db_path = tmp_path / "host.db"
    db = open_database(db_path)
    store = AccountStore(db)
    with db.transaction():
        store.register("signed_one", PW)
        store.register("never_one", PW)
    db.close()
    ConsentStore(audit.side_path(db_path)).record("signed_one", rules.load()["version"], "gate", 1.0)
    return db_path


def test_list_terms_must_lists_only_the_unsigned_and_writes_nothing(tmp_path, monkeypatch):
    import importlib.util

    spec = importlib.util.spec_from_file_location("list_terms_must", ROOT / "scripts" / "list_terms_must.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    db_path = _world_with_two_accounts(tmp_path, monkeypatch)
    side = audit.side_path(db_path)
    files = (db_path, side)  # 主資料庫與旁檔本身（WAL 的讀者會讓 sqlite 自己開 -shm、-wal，那不是資料，不比）

    def snap():
        return {p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in files}

    before = snap()
    content = SimpleNamespace(config=SimpleNamespace(terms=SimpleNamespace(enabled=True, grace_days=15, update_must=False), admins=[]))
    out = mod.lines(db_path, content, time.time())
    assert out == ["never_one　最後同意：沒有", "共 1 個"]
    content.config.terms.enabled = False
    assert mod.lines(db_path, content, time.time())[-1] == "共 0 個"
    assert snap() == before


def test_startup_warns_when_the_side_file_is_missing(tmp_path, monkeypatch, caplog):
    db_path = _world_with_two_accounts(tmp_path, monkeypatch)
    side = audit.side_path(db_path)
    shell = _shell(db_path, time.time())
    with caplog.at_level(logging.WARNING, logger=terms_routes.__name__):
        assert terms_routes.warn_if_consents_missing(shell) is False  # 現行版有一筆：不吵
        side.unlink()
        assert terms_routes.warn_if_consents_missing(shell) is True
    assert not side.exists()  # 唯讀：不替他建旁檔
    assert any("side file lost" in r.getMessage() for r in caplog.records)
    shell.CONTENT.config.terms.enabled = False
    assert terms_routes.warn_if_consents_missing(shell) is False
