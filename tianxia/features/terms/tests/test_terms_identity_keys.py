"""條款第 257 批：帳號綁定（identity）開著時，記同意的鍵與伺服器擋（殼 _game → terms_base.gate_problem）查的鍵對得上。
起因是 AG 波（第 249 批）留的一句：identity 開著時 session 的帳號鍵（id:<n>）和註冊時記同意的鍵可能對不上。
鍵表在計畫 docs/superpowers/plans/2026-11-23-條款-第257批.md 第二節，每條測試的說明寫它守哪一列：
R1 殼 /api/register 記 normalize(login)；R2 identity 建角色記 id:<n>；R3 /api/terms/agree 記 session 的鍵；
Q1 密碼登入、identity 關；Q2 密碼登入、identity 開（get().key）；Q3 第三方、驗證碼登入（login_key）；Q4 建角色直接開 session；
K1 綁定、解綁、補設密碼不改鍵；A1 audit.must_rows（scripts/list_terms_must.py）與伺服器擋的是同一批。
identity 用它測試現成的假服務（fake_services）打開，金鑰由 key_file 寫在 tmp，不讀 .local/。
條款包的程式不 import identity；測試照 identity 包 test_identity_terms.py 反過來的做法借它的測試工具。"""
from __future__ import annotations

from fastapi.testclient import TestClient
from test_identity_server import fresh_server, key_file  # noqa: F401  fresh_server 是 autouse
from test_identity_session import (  # noqa: F401
    bind, clock, on, send, token_of, verify,
)

import server
from tianxia import database
from tianxia.core import terms_base
from tianxia.features.terms import audit, rules

PW = "secret-pw-12"  # identity 開著全體密碼至少 12 字


def _ticks():
    return {"age_ok": True, "terms_agree": True, "terms_version": rules.load()["version"]}


def _terms(monkeypatch, on_=True):
    monkeypatch.setattr(server.CONTENT.config.terms, "enabled", on_)


def _identity(monkeypatch, on_):
    monkeypatch.setattr(server.CONTENT.config.identity, "enabled", on_)


def _key(c):
    return server.SESSIONS.get(token_of(c))


def _probe(c):
    return c.post("/api/choose", json={"id": "act:none"})


def _blocked(c):
    r = _probe(c)
    assert r.status_code == 403, (r.status_code, r.text[:200])
    assert r.json() == {"detail": terms_base.GATE_NEED}


def _passed(c):
    r = _probe(c)
    assert r.status_code != 403, r.text[:200]


def _phone_new(c, to, name, ticks=True):
    """驗證碼開一個沒有密碼的帳號（建角色那一步，R2＋Q4），回 session 的鍵。"""
    assert send(c, to).status_code == 200
    assert verify(c).json() == {"stage": "create", "pending": True}
    r = c.post("/api/identity/character", json={"name": name, **(_ticks() if ticks else {})})
    assert r.status_code == 200 and r.json()["stage"] == "game", r.text
    return _key(c)


def _phone_login(to, clock):
    """新的一台用驗證碼登入已有的帳號（Q3），回 client。同一個號碼 resend_seconds 內不再寄，先撥過去。"""
    clock.now += server.CONTENT.config.identity.resend_seconds + 1
    c = TestClient(server.app)
    assert send(c, to).status_code == 200
    r = verify(c)
    assert r.status_code == 200 and r.json()["stage"] == "game", r.text
    return c


def _register(c, login, name, ticks=True):
    """殼的 /api/register（R1）＋建角色。"""
    body = {"login": login, "password": PW, "again": PW, **(_ticks() if ticks else {})}
    assert c.post("/api/register", json=body).status_code == 200
    assert c.post("/api/character", json={"name": name}).status_code == 200
    return _key(c)


def _pw_login(login, password=PW):
    c = TestClient(server.app)
    r = c.post("/api/login", json={"login": login, "password": password})
    assert r.status_code == 200 and r.json()["stage"] == "game", r.text
    return c


def _set_password(c, login, new=PW):
    r = c.post("/api/identity/password/set", json={"login": login, "new": new, "again": new})
    assert r.status_code == 200, r.text


def _audit_matches(clients):
    """A1：audit.must_rows 列的帳號鍵＝這一刻打 /api/choose 實際 403 的那些 client 的 session 鍵。"""
    rows = audit.must_rows(database.default_path(), server.CONTENT.config.terms, set(), server.time.time())
    listed = {row["key"] for row in rows if not row["admin"]}
    blocked = {_key(c) for c in clients if _probe(c).status_code == 403}
    assert listed == blocked, (listed, blocked)
    return listed


# ── (a) R2＋Q4、Q3 ──

def test_a_identity_character_with_ticks_passes(clock, monkeypatch):
    """R2＋Q4：identity 開、條款開，驗證碼開帳號勾兩個 → session id:<n>、不擋；
    Q3：登出、新的一台用驗證碼登入（login_key 回 id:<n>）→ 不擋。A1：沒有人被列。"""
    _terms(monkeypatch)
    c = TestClient(server.app)
    key = _phone_new(c, "0912000001", "柳如煙")
    assert key.startswith("id:")
    _passed(c)
    c.post("/api/logout")
    again = _phone_login("0912000001", clock)
    assert _key(again) == key
    _passed(again)
    assert _audit_matches([again]) == set()


# ── (b) R1＋Q1、Q2 ──

def test_b_old_register_then_identity_on_password_login_passes(clock, monkeypatch):
    """R1＋Q1：identity 關著用 /api/register 帶勾選註冊（記 shen_b1），舊 session 鍵是小寫名；
    Q2：identity 打開後新的一台密碼登入（get().key＝小寫名）→ 不擋；打開前的舊 session 也不擋。A1：沒有人被列。"""
    _terms(monkeypatch)
    _identity(monkeypatch, False)
    old = TestClient(server.app)
    assert _register(old, "Shen_B1", "沈青衫") == "shen_b1"
    _identity(monkeypatch, True)
    c = _pw_login("SHEN_B1")
    assert _key(c) == "shen_b1"
    _passed(c)
    _passed(old)
    assert _audit_matches([c, old]) == set()


# ── (c) K1 ──

def test_c_bind_and_unbind_keep_the_key(clock, monkeypatch):
    """K1：(b) 那種帳號（R1 記小寫名）綁手機 → 鍵不變、不擋；Q3 用手機登入（login_key 回小寫名）→ 不擋；
    再綁 Email、解綁手機 → 鍵不變、不擋。A1：沒有人被列。
    打開那一天已登入的人走密碼重新驗證（第 259 批）再綁，全程在打開前就登入的那一台上做。"""
    _terms(monkeypatch)
    _identity(monkeypatch, False)
    old = TestClient(server.app)
    key = _register(old, "shen_c1", "沈青衫")
    _identity(monkeypatch, True)
    assert send(old, "0912000003", purpose="bind").status_code == 400  # 沒重驗前被擋（擋在寄碼之前）
    assert old.post("/api/identity/reauth", json={"password": PW}).status_code == 200
    assert bind(old, "0912000003").status_code == 200
    assert _key(old) == key
    _passed(old)
    phone = _phone_login("0912000003", clock)
    assert _key(phone) == key
    _passed(phone)
    assert bind(old, "c1@example.com", "email").status_code == 200
    assert old.post("/api/identity/unbind", json={"provider": "phone"}).status_code == 200
    assert _key(old) == key
    _passed(old)
    assert _audit_matches([old, phone]) == set()


def test_c_password_set_keeps_the_id_key(clock, monkeypatch):
    """K1＋Q2：(a) 那種帳號（R2 記 id:<n>）補設密碼 → session 不換；登出後用新帳號名密碼登入（Q2 回 id:<n>）→ 不擋。A1：沒有人被列。"""
    _terms(monkeypatch)
    c = TestClient(server.app)
    key = _phone_new(c, "0912000004", "李白衣")
    _set_password(c, "Ray_C2")
    assert _key(c) == key
    _passed(c)
    c.post("/api/logout")
    again = _pw_login("RAY_C2")
    assert _key(again) == key
    _passed(again)
    assert _audit_matches([again]) == set()


# ── (d) R3＋(e) 反面 ──

def test_d_e_unsigned_blocked_in_every_key_shape_then_agree_passes(clock, monkeypatch):
    """(e)：identity 開、條款關時開的三種鍵的形狀——小寫名（密碼註冊，Q2）、id:<n>（驗證碼，Q4）、補設過密碼的 id:<n>（Q2）——
    都沒有同意紀錄；條款打開 → 三個都 403、GATE_NEED（鍵對不上不會變成全部放行）。A1：audit 列的就是這三個。
    (d) R3：各自在同意層 /api/terms/agree 按現行版 → 不擋；A1：沒有人被列。"""
    _terms(monkeypatch, False)
    name = TestClient(server.app)
    assert _register(name, "shen_d1", "沈青衫", ticks=False) == "shen_d1"
    plain = TestClient(server.app)
    pid = _phone_new(plain, "0912000005", "柳如煙", ticks=False)
    marked = TestClient(server.app)
    mid = _phone_new(marked, "0912000006", "李白衣", ticks=False)
    _set_password(marked, "ray_d3")
    marked.post("/api/logout")
    marked = _pw_login("ray_d3")
    assert pid.startswith("id:") and _key(marked) == mid and mid.startswith("id:") and mid != pid
    _terms(monkeypatch)
    clients = [name, plain, marked]
    for c in clients:
        _blocked(c)
    assert _audit_matches(clients) == {"shen_d1", pid, mid}
    for c in clients:
        r = c.post("/api/terms/agree", json={"version": rules.load()["version"]})
        assert r.status_code == 200 and r.json()["need"] == "", r.text
        _passed(c)
    assert _audit_matches(clients) == set()


# ── (g) 範圍外的一處（現況，是否要修交 PM）──

def test_g_marked_account_after_identity_turned_off_is_asked_once(clock, monkeypatch):
    """現況，是否要修交 PM（計畫第二節最後一段）：補設過密碼的帳號（R2 記 id:<n>）在 identity 打開過又關掉之後用密碼登入，
    Q1 的 session 是小寫名、對不到 id:<n> 的同意 → 403；audit 照 _get 的算法算成 id:<n>、不列它（A1 這裡對不上）。
    按一次同意（R3 記在小寫名）之後放行，不會一直卡住。"""
    _terms(monkeypatch)
    c = TestClient(server.app)
    key = _phone_new(c, "0912000007", "柳如煙")
    _set_password(c, "ray_g1")
    _identity(monkeypatch, False)
    off = _pw_login("ray_g1")
    assert _key(off) == "ray_g1" and key.startswith("id:")
    _blocked(off)
    rows = audit.must_rows(database.default_path(), server.CONTENT.config.terms, set(), server.time.time())
    assert {row["key"] for row in rows} == set()  # 現況：清單漏了這一個
    r = off.post("/api/terms/agree", json={"version": rules.load()["version"]})
    assert r.status_code == 200 and r.json()["need"] == "", r.text
    _passed(off)
