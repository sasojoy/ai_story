"""條款：誰要按同意（規則）、同意紀錄只加不刪（小檔）、/api/terms 與 /api/terms/agree（伺服器）、網頁那一層（node）。"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import server
from tianxia.features.terms import routes as terms_routes
from tianxia.features.terms import rules
from tianxia.features.terms.store import ConsentStore

DATA = {"version": "v2", "published": "2026-11-08"}
DAY = 86400


def test_need_must_for_a_new_account_and_none_once_agreed():
    now = rules.published_at(DATA) + 1
    assert rules.need(None, DATA, now, 15) == rules.MUST
    assert rules.need("v2", DATA, now, 15) == rules.NONE


def test_an_old_consent_is_asked_inside_the_grace_days_and_deemed_accepted_after():
    """update_must 關著（第五個參數預設 False）：第 243 批以前的考慮期做法，一個字不變。"""
    start = rules.published_at(DATA)
    assert rules.need("v1", DATA, start + 14 * DAY, 15) == rules.ASK
    assert rules.need("v1", DATA, start + 15 * DAY, 15) == rules.NONE
    assert rules.need(None, DATA, start + 99 * DAY, 15) == rules.MUST  # 沒同意過任何一版：一直要按


def test_update_must_makes_an_old_consent_must_inside_and_after_the_grace_days():
    """第 243 批（企劃者 2026-11-21「改成強制按同意」）：同意過舊版跟沒同意過一樣要按。"""
    start = rules.published_at(DATA)
    for now in (start - DAY, start + 14 * DAY, start + 15 * DAY, start + 99 * DAY):
        assert rules.need("v1", DATA, now, 15, True) == rules.MUST
        assert rules.need(None, DATA, now, 15, True) == rules.MUST
        assert rules.need("v2", DATA, now, 15, True) == rules.NONE


def test_the_store_only_appends(tmp_path):
    store = ConsentStore(tmp_path / "t-terms.sqlite")
    assert store.latest("ab") is None
    store.record("ab", "v1", "register", 1.0)
    store.record("ab", "v2", "update", 2.0)
    assert store.latest("ab") == "v2"
    assert [h["version"] for h in store.history("ab")] == ["v1", "v2"]
    with pytest.raises(ValueError):
        store.record("ab", "v2", "nowhere", 3.0)


def test_check_catches_a_missing_company_field_and_an_unknown_placeholder():
    data = rules.load()
    broken = {**data, "company": {**data["company"], "email": ""}}
    assert any("email" in p for p in rules.check(broken))
    docs = {**data["docs"], "terms": {**data["docs"]["terms"], "sections": [{"h": "x", "p": ["{nope}"]}]}}
    assert any("nope" in p for p in rules.check({**data, "docs": docs}))


@pytest.fixture
def client(monkeypatch):
    from tianxia import accounts

    monkeypatch.setattr(accounts, "SCRYPT_PARAMS", {"n": 2, "r": 1, "p": 1, "dklen": 32})
    monkeypatch.setattr(server.CONTENT.config, "auto_open_first_season", True)
    for store in (server.LOGIN_FAILURES, server.SESSIONS, server.GAMES):
        store.clear()
    server.WORLD_GAME = None
    c = TestClient(server.app)
    # 第 206 批起開著時註冊要勾兩格、會記 register：這裡要的是「還沒同意過」的帳號，先關著註冊再打開
    c.post("/api/register", json={"login": "terms_01", "password": "secret-pw", "again": "secret-pw"})
    monkeypatch.setattr(server.CONTENT.config.terms, "enabled", True)
    yield c
    for store in (server.LOGIN_FAILURES, server.SESSIONS, server.GAMES):
        store.clear()
    server.WORLD_GAME = None


def test_api_asks_until_agreed_then_stays_quiet(client):
    assert TestClient(server.app).get("/api/terms").status_code == 401
    got = client.get("/api/terms").json()
    assert got["need"] == "must" and got["summary"] and got["email"] == "wormholecreativity@gmail.com"
    assert "update" not in got  # 新玩家第一次：不帶改版旗標（第 243 批）
    assert client.post("/api/terms/agree", json={"version": "old"}).status_code == 409
    done = client.post("/api/terms/agree", json={"version": got["version"]}).json()
    assert done["need"] == ""
    assert terms_routes.consent_store(server).history("terms_01")[0]["source"] == "gate"


def test_api_an_old_consent_must_agree_again_with_source_update(client, monkeypatch):
    """第 243 批：同意過舊版、update_must 開著（第 246 批起要明設，預設關）→ must＋update、有 summary、沒有期限；同意後記 update。"""
    monkeypatch.setattr(server.CONTENT.config.terms, "update_must", True)
    terms_routes.consent_store(server).record("terms_01", "2026-11-v1", "register", 1.0)
    got = client.get("/api/terms").json()
    assert got["need"] == "must" and got["update"] is True and got["summary"] and got["deadline"] is None
    done = client.post("/api/terms/agree", json={"version": got["version"], "source": "update"}).json()
    assert done["need"] == "" and "update" not in done
    assert terms_routes.consent_store(server).history("terms_01")[-1]["source"] == "update"


def test_api_update_must_off_keeps_the_grace_days(client, monkeypatch):
    """update_must 關著（第 246 批起是預設）：跟第 243 批以前一樣，ask＋期限、不帶 update。"""
    monkeypatch.setattr(server.CONTENT.config.terms, "update_must", False)
    terms_routes.consent_store(server).record("terms_01", "2026-11-v1", "register", 1.0)
    data = rules.load()

    def shell_at(now):  # 假鐘只給 status 用，不換全域的 time.time（登入的 session 也讀它）
        return SimpleNamespace(CONTENT=server.CONTENT, default_path=server.default_path, time=SimpleNamespace(time=lambda: now))

    got = terms_routes.status(shell_at(rules.published_at(data) + DAY), "terms_01")
    assert got["need"] == "ask" and got["summary"] and got["deadline"] and "update" not in got
    late = terms_routes.status(shell_at(rules.published_at(data) + 99 * DAY), "terms_01")
    assert late == {"need": "", "version": data["version"], "email": data["company"]["email"]}


def test_update_must_defaults_to_the_grace_period(client):
    """第 246 批（企劃者 2026-11-21 下午「這次用 15 天考慮期」）：config.json 那一層與 season21、week7 都不強制；
    預設下同意過 v1、現行 v2、考慮期內 → ask、有期限、不帶 update（跟使用條款第九條一致）。"""
    from conftest import real_content

    for profile in (None, "season21", "week7"):
        assert real_content(profile).config.terms.update_must is False, profile
    assert server.CONTENT.config.terms.update_must is False
    data = rules.load()
    assert data["version"] != "2026-11-v1"
    terms_routes.consent_store(server).record("terms_01", "2026-11-v1", "register", 1.0)
    shell = SimpleNamespace(CONTENT=server.CONTENT, default_path=server.default_path,
                            time=SimpleNamespace(time=lambda: rules.published_at(data) + DAY))
    got = terms_routes.status(shell, "terms_01")
    assert got["need"] == "ask" and got["deadline"] and got["summary"] and "update" not in got


def test_switch_off_never_asks(client, monkeypatch):
    monkeypatch.setattr(server.CONTENT.config.terms, "enabled", False)
    assert client.get("/api/terms").status_code == 404  # 關著 404：網頁把非 200 當「沒事」
    assert client.post("/api/terms/agree", json={"version": "x"}).status_code == 404
    assert client.get("/terms").status_code == 200  # 條款頁本身永遠看得到


def test_record_consent_for_the_register_side(client):
    version = rules.load()["version"]
    with pytest.raises(ValueError):
        terms_routes.record_consent(server, "terms_01", "old")
    terms_routes.record_consent(server, "terms_01", version)
    assert client.get("/api/terms").json()["need"] == ""
    assert terms_routes.consent_store(server).history("terms_01")[-1]["source"] == "register"
