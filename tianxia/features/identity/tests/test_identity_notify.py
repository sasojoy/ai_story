"""綁定、解綁、補設與忘記密碼的通知（帳號與客服第 208 批；設計 4.3「通知現有的 Email、手機」，企劃者 11/08 選「另存加密的號碼給通知用」）：
綁 Email、手機成功時把號碼用 .local/identity.json 的 notify_key 加密存進旁檔 contacts（跟 HMAC 分開、不進任何查詢與比對），只在寄通知那一刻解開；
每次綁、解綁、補設密碼、忘記密碼經 senders 寄一則給現有的 Email、手機（忘記密碼不寄登入用的那一種）；解綁、刪帳號刪那一列。
讀不到 notify_key 只寫紀錄、不寄；NoSender（fake 關）不 500；登入用途的碼第 209 批起也存號碼（開了 session、建了角色才存；重驗不封）；log 那一行只寫遮過的號碼。"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from test_identity_bind import _pw, _reauth
from test_identity_login import _pending_client
from test_identity_password import _phone_login
from test_identity_recycle import _stale_with_password
from test_identity_server import fresh_server, key_file  # noqa: F401
from test_identity_session import (  # noqa: F401
    bind, clock, error, on, phone_account, register, send, side_rows, subj, token_of, verify,
)

import server
from tianxia import database
from tianxia.accounts import AccountStore
from tianxia.features.identity import admin as idadmin
from tianxia.features.identity import binding, contacts, senders

PHONE, PHONE_N = "0912345678", "+886912345678"
MAIL = "ray.chen@example.com"
HOUR = 3600


@pytest.fixture
def notify(key_file, clock):  # noqa: F811
    data = json.loads(key_file.read_text(encoding="utf-8"))
    data["notify_key"] = "n" * 32
    key_file.write_text(json.dumps(data), encoding="utf-8")
    return clock


def _sms():
    return [t for _to, t in senders.FAKES.sms.outbox]


def _mail():
    return [t for _to, t in senders.FAKES.mail.outbox]


def _contacts():
    return side_rows("SELECT account_id, provider, sealed, display FROM contacts ORDER BY account_id, provider")


def test_bind_phone_stores_sealed_number_and_notifies(notify, capsys):
    c = TestClient(server.app)
    aid = _pw(c)
    assert bind(c).json() == {"message": binding.BOUND}
    [(owner, provider, sealed, display)] = _contacts()
    assert (owner, provider, display) == (aid, "phone", "09*****678")
    assert isinstance(sealed, bytes) and b"912345678" not in sealed and "912345678".encode("utf-16-le") not in sealed
    note = binding.NOTE_BOUND.format(kind="手機")
    assert senders.FAKES.sms.outbox[-1] == (PHONE_N, contacts.SMS_TEXT.format(text=note))
    out = capsys.readouterr().out
    assert "identity 通知 phone 09*****678" in out and "912345678" not in out


def test_bind_email_notifies_existing_phone_and_mail(notify):
    c = TestClient(server.app)
    _pw(c)
    bind(c)
    assert bind(c, MAIL, "email").json() == {"message": binding.BOUND}
    note = binding.NOTE_BOUND.format(kind="Email")
    assert senders.FAKES.sms.outbox[-1] == (PHONE_N, contacts.SMS_TEXT.format(text=note))
    assert senders.FAKES.mail.outbox[-1] == (MAIL, note)
    assert senders.FAKES.mail.subjects[-1] == contacts.MAIL_SUBJECT
    assert sorted(r[1] for r in _contacts()) == ["email", "phone"]


def test_unbind_notifies_the_removed_one_and_drops_it(notify):
    c = TestClient(server.app)
    _pw(c)
    bind(c)
    notify.now += 73 * HOUR
    _reauth(c, notify)
    assert c.post("/api/identity/unbind", json={"provider": "phone"}).json() == {"message": binding.UNBOUND}
    assert senders.FAKES.sms.outbox[-1] == (PHONE_N, contacts.SMS_TEXT.format(text=binding.NOTE_UNBOUND.format(kind="手機")))
    assert _contacts() == []


def test_set_password_notifies(notify):
    c = TestClient(server.app)
    phone_account(c)  # 第 209 批：驗證碼開的帳號也存號碼（之後的通知寄得到）
    assert [r[1] for r in _contacts()] == ["phone"]
    bind(c, MAIL, "email")
    notify.now += 73 * HOUR
    c.post("/api/identity/code/send", json={"channel": "email", "to": MAIL, "turnstile": "ok", "purpose": "reauth"})
    assert verify(c, "email").status_code == 200
    r = c.post("/api/identity/password/set", json={"login": "ray_77", "new": "new-secret-12", "again": "new-secret-12"})
    assert r.json() == {"message": binding.PASSWORD_SET}
    assert _mail()[-1] == binding.NOTE_PASSWORD_SET.format(login="ray_77")
    assert _sms()[-1] == contacts.SMS_TEXT.format(text=binding.NOTE_PASSWORD_SET.format(login="ray_77"))  # 第 209 批：開帳號那支手機也收到


def test_reset_password_skips_the_way_used_to_log_in(notify):
    c = TestClient(server.app)
    _pw(c)
    bind(c)
    bind(c, MAIL, "email")
    notify.now += 73 * HOUR
    d = TestClient(server.app)
    _phone_login(d)
    sms_before = len(senders.FAKES.sms.outbox)
    assert d.post("/api/identity/password/reset", json={"new": "brand-new-pw-1", "again": "brand-new-pw-1"}).json() == \
        {"message": binding.PASSWORD_RESET}
    assert _mail()[-1] == binding.NOTE_PASSWORD_RESET.format(kind="手機")
    assert len(senders.FAKES.sms.outbox) == sms_before  # 登入用的那一支不寄


def test_no_notify_key_only_writes_notes(clock):
    c = TestClient(server.app)
    _pw(c)
    r = bind(c)
    assert r.status_code == 200 and r.json() == {"message": binding.BOUND}
    assert _contacts() == []
    assert not any("綁定了" in t for t in _sms())
    assert [x[0] for x in side_rows("SELECT text FROM account_notes")] == [binding.NOTE_BOUND.format(kind="手機")]


def test_no_sender_does_not_500(notify, monkeypatch):
    c = TestClient(server.app)
    _pw(c)
    bind(c)
    monkeypatch.setattr(senders, "pick", lambda content: senders.Senders(senders.NoSender(), senders.NoSender(), senders.FakeTurnstile()))
    notify.now += 73 * HOUR
    _reauth(c, notify)
    r = c.post("/api/identity/unbind", json={"provider": "phone"})
    assert r.status_code == 200 and r.json() == {"message": binding.UNBOUND}


def test_admin_unbind_and_delete_drop_contacts(notify):
    c = TestClient(server.app)
    aid = _pw(c)
    bind(c)
    bind(c, MAIL, "email")
    sent = (len(senders.FAKES.sms.outbox), len(senders.FAKES.mail.outbox))
    admin = SimpleNamespace(state=SimpleNamespace(player=SimpleNamespace(name="")))  # 管理者工具只讀 game.state.player.name（刪自己的擋）
    idadmin.unbind(server, admin, {"target": "shen_01", "provider": "phone"}, notify.now)
    assert [r[1] for r in _contacts()] == ["email"]
    idadmin.delete(server, admin, {"target": "shen_01"}, notify.now)
    assert _contacts() == [] and AccountStore(database.open_database()).get("shen_01") is None
    assert (len(senders.FAKES.sms.outbox), len(senders.FAKES.mail.outbox)) == sent  # 管理者做的不寄
    assert aid is not None


def test_reauth_code_stores_no_contact(notify):
    """第 209 批起登入用途也封號碼（test_login_code_keeps_contact）；重驗用途照舊不封。"""
    c = TestClient(server.app)
    phone_account(c)
    assert side_rows("SELECT contact FROM challenges") == []
    notify.now += 61  # 同一號 60 秒內不再寄
    assert send(c, purpose="reauth").status_code == 200
    assert side_rows("SELECT contact FROM challenges") == [(None,)]


def test_seal_roundtrip_and_aad(notify):
    blob = contacts.seal("+886900000000", "7|phone")
    assert contacts.unseal(blob, "7|phone") == "+886900000000"
    assert contacts.unseal(blob, "8|phone") is None  # aad 不同解不開
    assert contacts.unseal(b"junk", "7|phone") is None


# ── 第 209 批：登入用途的驗碼與用驗證碼開帳號也存通知用的號碼（之後解綁、補設密碼的通知寄得到）──


def _add_notify_key(key_file):  # noqa: F811
    data = json.loads(key_file.read_text(encoding="utf-8"))
    data["notify_key"] = "n" * 32
    key_file.write_text(json.dumps(data), encoding="utf-8")


def _aid(key):
    return AccountStore(database.open_database()).account_id(key)


def test_login_code_keeps_contact(clock, key_file):  # noqa: F811
    c = TestClient(server.app)
    key = phone_account(c)  # 沒有 notify_key：開帳號那一下不存
    assert _contacts() == []
    _add_notify_key(key_file)
    d = TestClient(server.app)
    clock.now += 61  # 同一號 60 秒內不再寄
    assert send(d).status_code == 200
    assert verify(d).json()["stage"] == "game"
    [(owner, provider, sealed, display)] = _contacts()
    assert (owner, provider, display) == (_aid(key), "phone", "09*****678")
    assert b"912345678" not in sealed and contacts.unseal(sealed, f"{owner}|phone") == PHONE_N


def test_code_signup_keeps_contact(notify):
    c = TestClient(server.app)
    key = phone_account(c)
    [(owner, provider, sealed, display)] = _contacts()
    assert (owner, provider, display) == (_aid(key), "phone", "09*****678")
    assert contacts.unseal(sealed, f"{owner}|phone") == PHONE_N
    assert side_rows("SELECT COUNT(*) FROM pending") == [(0,)]  # 建好角色，待處理那一列連號碼一起刪


def test_oauth_signup_keeps_nothing(notify, monkeypatch):
    c = _pending_client(monkeypatch)
    assert side_rows("SELECT contact FROM pending") == [(None,)]  # 第三方沒有號碼
    assert c.post("/api/identity/character", json={"name": "柳如煙"}).status_code == 200
    assert _contacts() == []


def test_no_notify_key_login_ok_no_row(clock):
    c = TestClient(server.app)
    phone_account(c)
    d = TestClient(server.app)
    clock.now += 61
    assert send(d).status_code == 200
    r = verify(d)
    assert r.status_code == 200 and r.json()["stage"] == "game"
    assert _contacts() == [] and side_rows("SELECT COUNT(*) FROM challenges") == [(0,)]


def test_stale_with_others_keeps_nothing_until_session(notify):
    key = _stale_with_password(notify)
    before = _contacts()  # 開帳號那一下存的
    d = TestClient(server.app)
    assert send(d).status_code == 200
    assert verify(d).json()["stale"] is True
    assert _contacts() == before  # 沒開 session：不存
    [(blob,)] = side_rows("SELECT contact FROM rechecks")
    assert blob is not None and b"912345678" not in blob
    assert _aid(key) == before[0][0]


def test_not_mine_new_account_keeps_contact(notify):
    key = _stale_with_password(notify)
    old = _aid(key)
    d = TestClient(server.app)
    send(d)
    verify(d)
    assert d.post("/api/identity/code/release").status_code == 200
    assert side_rows("SELECT contact IS NOT NULL FROM pending") == [(1,)]
    assert d.post("/api/identity/character", json={"name": "新來的"}).status_code == 200
    new = _aid(server.SESSIONS.get(token_of(d)))
    assert [(r[0], r[1]) for r in _contacts()] == [(new, "phone")] and new != old  # 舊帳號那一列拿掉、新帳號存一列
