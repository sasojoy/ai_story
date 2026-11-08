"""帳號綁定的核心那一半（tianxia/core/identity_base.py；帳號與客服第 201 批）：正規化、遮罩、金鑰、phone_ok、名號擋不擋。"""
import json

import pytest

from tianxia.core import identity_base as ib


@pytest.fixture
def keyed(tmp_path, monkeypatch):
    path = tmp_path / "identity.json"
    path.write_text(json.dumps({"key": "k" * 32}), encoding="utf-8")
    monkeypatch.setattr(ib, "KEY_FILE", path)
    return path


@pytest.mark.parametrize("text", [
    "0912345678", "0912-345-678", "0912 345 678", "(0912)345678", "+886912345678", "+886 912 345 678",
    "+886-912-345-678", "０９１２３４５６７８", "　0912345678　",
])
def test_identity_base_normalize_phone_taiwan_forms(text):
    assert ib.normalize_phone(text) == "+886912345678"


@pytest.mark.parametrize("text", ["", None, "02-2345-6789", "091234567", "09123456789", "+85291234567", "8869123456789", "abc"])
def test_identity_base_normalize_phone_rejects(text):
    assert ib.normalize_phone(text) is None


def test_identity_base_normalize_and_mask():
    assert ib.normalize_email("R.a.Y+game@Gmail.com") == "ray@gmail.com"
    assert ib.normalize_email("r.ay+x@googlemail.com") == "ray@googlemail.com"
    assert ib.normalize_email(" Ray.Lin+x@Example.COM ") == "ray.lin@example.com"
    for bad in ("", None, "ray", "a@b", "@gmail.com", "+x@gmail.com", "a@@b.com", "a b@c.com"):
        assert ib.normalize_email(bad) is None, bad
    assert ib.mask_phone("+886912345678") == "09*****678"
    assert ib.mask_email("ray@gmail.com") == "r*@gmail.com"
    assert ib.mask_email("raymond@gmail.com") == "r*@gmail.com"  # 看不出幾個字
    assert "12345" not in ib.mask_phone("+886912345678")


def test_identity_base_key_and_hmac(tmp_path, keyed):
    assert ib.read_key() == b"k" * 32
    assert ib.read_key(tmp_path / "nope.json") is None
    for text in ("not json", json.dumps([1]), json.dumps({"key": "short"}), json.dumps({"key": 5})):
        bad = tmp_path / "bad.json"
        bad.write_text(text, encoding="utf-8")
        assert ib.read_key(bad) is None, text
    a = ib.subject_hmac(b"k" * 32, "phone", "+886912345678")
    assert a == ib.subject_hmac(b"k" * 32, "phone", "+886912345678")
    assert a != ib.subject_hmac(b"k" * 32, "email", "+886912345678")
    assert a != ib.subject_hmac(b"j" * 32, "phone", "+886912345678")
    assert "912345678" not in a


def test_identity_base_on_needs_switch_and_key(content, tmp_path, monkeypatch, keyed):
    assert ib.on(content) is False  # 預設關
    content.config.identity.enabled = True
    assert ib.on(content) is True
    monkeypatch.setattr(ib, "KEY_FILE", tmp_path / "missing.json")
    assert ib.on(content) is False


def _bind(game, provider=None):
    from tianxia.accounts import AccountStore

    store = AccountStore(game.world.db)
    store.register("ray1", "secret1")
    store.bind_character("ray1", game.state.player.name)
    if provider:  # 直接寫一列（綁定的路第 204 批才有）
        with game.world.db.transaction() as conn:
            conn.execute(
                "INSERT INTO logins (provider, subject, account_id, display) "
                "SELECT ?, ?, account_id, '09*****678' FROM logins WHERE provider = 'password' AND subject = 'ray1'",
                (provider, "h" * 64),
            )


def test_phone_ok_order(game, keyed):
    """第 205 批照設計 4.5 的順序：關著、phone_gate 關、不在名單、假人回真；不是假人又查不到帳號回假；其餘看有沒有 phone 列。"""
    from tianxia.state import BotProfile

    cfg = game.content.config.identity
    assert ib.phone_ok(game, "raid") is True  # 關著
    cfg.enabled = True
    assert ib.phone_ok(game, "raid") is True  # phone_gate 關
    cfg.phone_gate = True
    assert ib.phone_ok(game, "raid") is False  # 不是假人、查不到帳號
    assert ib.phone_ok(game, "not_listed") is True  # 不在名單
    game.state.player.bot = BotProfile(personality="普通", seed=1)
    assert ib.phone_ok(game, "raid") is True  # 假人一律過（假人沒有帳號）
    game.state.player.bot = None
    _bind(game)
    assert ib.phone_ok(game, "raid") is False  # 有帳號、沒綁手機
    assert ib.phone_ok(game, "not_listed") is True


def test_phone_ok_true_when_identity_is_off_even_with_phone_gate_on(game, keyed, tmp_path, monkeypatch):
    """緊急關掉 identity（enabled 關、或金鑰讀不到）時 phone_gate 開著也一律過：九個入口不能被關著的包擋住（L 波審查）。"""
    cfg = game.content.config.identity
    cfg.phone_gate = True
    _bind(game)  # 有帳號、沒綁手機：identity 開著的話會擋
    assert ib.phone_ok(game, "raid") is True  # enabled 關
    cfg.enabled = True
    assert ib.phone_ok(game, "raid") is False  # 對照：開著就擋
    monkeypatch.setattr(ib, "KEY_FILE", tmp_path / "missing.json")
    assert ib.phone_ok(game, "raid") is True  # 金鑰讀不到＝沒開


def test_phone_ok_true_once_the_phone_is_bound(game, keyed):
    cfg = game.content.config.identity
    cfg.enabled = True
    cfg.phone_gate = True
    _bind(game, "phone")
    assert ib.phone_ok(game, "raid") is True


def test_phone_subject_only_when_gated_and_bound(game, keyed):
    """phone_subject：走到「有 phone 列」才回那一列的 subject；閘關、不在名單、假人、沒綁都 None。"""
    from tianxia.state import BotProfile

    cfg = game.content.config.identity
    cfg.enabled = True
    _bind(game, "phone")
    assert ib.phone_subject(game, "mall_grant") is None  # phone_gate 關
    cfg.phone_gate = True
    assert ib.phone_subject(game, "mall_grant") == "h" * 64
    assert ib.phone_subject(game, "not_listed") is None
    game.state.player.bot = BotProfile(personality="普通", seed=1)
    assert ib.phone_subject(game, "mall_grant") is None
    game.state.player.bot = None
    with game.world.db.transaction() as conn:
        conn.execute("DELETE FROM logins WHERE provider = 'phone'")
    assert ib.phone_subject(game, "mall_grant") is None  # 沒綁
    assert isinstance(ib.PHONE_NEEDED, str) and ib.PHONE_NEEDED


def test_account_key_for_reads_logins(game):
    """第 203 批：身分綁在哪個帳號——有密碼的回小寫帳號，沒有的回 id:<n>，查無回 None。"""
    from tianxia.accounts import AccountStore

    db = game.world.db
    assert ib.account_key_for(db, "phone", "h" * 64) is None
    _bind(game, "phone")
    assert ib.account_key_for(db, "phone", "h" * 64) == "ray1"
    key = AccountStore(db).create_without_password("email", "e" * 64, "r*@gmail.com")
    assert ib.account_key_for(db, "email", "e" * 64) == key and key.startswith("id:")
    assert ib.account_key_for(db, "email", "h" * 64) is None


def test_account_key_for_is_login_key(game, monkeypatch):
    """第 204 批（K 波審查）：併成一份，就是 AccountStore.login_key。"""
    from tianxia.accounts import AccountStore

    seen = []
    monkeypatch.setattr(AccountStore, "login_key", lambda self, provider, subject: seen.append((provider, subject)) or "k")
    assert ib.account_key_for(game.world.db, "phone", "h" * 64) == "k" and seen == [("phone", "h" * 64)]


def test_staff_session_ok_off_uses_session_created(game, content):
    """第 204 批：identity 關著時看 session 建立的時間（staff_hours 內）；查不到回假。"""
    from tianxia.accounts import AccountStore, SessionStore

    db = game.world.db
    AccountStore(db).register("kefu_01", "secret-pw")
    token = SessionStore(db, clock=lambda: 1000.0).create("kefu_01")
    clocked = SessionStore(db, clock=lambda: 1000.0)
    assert clocked.created_at(token) == 1000.0 and clocked.created_at("nope") is None
    assert content.config.identity.enabled is False
    assert ib.staff_session_ok(db, content, token, 1000.0 + 6 * 3600) is True
    assert ib.staff_session_ok(db, content, token, 1000.0 + 6 * 3600 + 1) is False
    assert ib.staff_session_ok(db, content, "nope", 1000.0) is False
    assert ib.staff_session_ok(db, content, None, 1000.0) is False


def test_session_auth_roundtrip_and_last_checked(tmp_path):
    side = tmp_path / "g-identity.sqlite"
    assert ib.session_auth("t", side) is None
    ib.record_session("t", "phone", 100.0, side)
    assert ib.session_auth("t", side) == {"method": "phone", "at": 100.0, "verified": None, "verified_by": None}
    assert ib.last_checked(ib.session_auth("t", side)) == 100.0
    assert ib.record_reauth("t", "password", 500.0, side) is True
    assert ib.session_auth("t", side)["method"] == "phone" and ib.last_checked(ib.session_auth("t", side)) == 500.0
    assert ib.side_file(tmp_path / "g.db") == side


def test_blocked_name_only_when_on(content, keyed):
    names = ("客服", "GM", "gm", "id:3", "ID:3", "官方", "管理員")
    assert not any(ib.blocked_name(n, content) for n in names)
    content.config.identity.enabled = True
    assert all(ib.blocked_name(n, content) for n in names)
    assert not ib.blocked_name("沈浪", content)
    assert not ib.blocked_name("客服甲", content)
