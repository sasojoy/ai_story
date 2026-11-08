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


def test_phone_ok_true_for_bots_and_no_account(game, keyed):
    from tianxia.state import BotProfile

    cfg = game.content.config.identity
    assert ib.phone_ok(game, "raid") is True  # 關著
    cfg.enabled = True
    assert ib.phone_ok(game, "raid") is True  # phone_gate 關
    cfg.phone_gate = True
    assert ib.phone_ok(game, "raid") is True  # 沒帳號
    assert ib.phone_ok(game, "not_listed") is True  # 不在名單
    game.state.player.bot = BotProfile(personality="普通", seed=1)
    assert ib.phone_ok(game, "raid") is True  # 假人跟沒帳號同值
    game.state.player.bot = None
    _bind(game)
    assert ib.phone_ok(game, "raid") is False  # 有帳號、沒綁手機
    assert ib.phone_ok(game, "not_listed") is True


def test_phone_ok_true_once_the_phone_is_bound(game, keyed):
    cfg = game.content.config.identity
    cfg.enabled = True
    cfg.phone_gate = True
    _bind(game, "phone")
    assert ib.phone_ok(game, "raid") is True


def test_blocked_name_only_when_on(content, keyed):
    names = ("客服", "GM", "gm", "id:3", "ID:3", "官方", "管理員")
    assert not any(ib.blocked_name(n, content) for n in names)
    content.config.identity.enabled = True
    assert all(ib.blocked_name(n, content) for n in names)
    assert not ib.blocked_name("沈浪", content)
    assert not ib.blocked_name("客服甲", content)
