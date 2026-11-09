"""第三方登入的純規則（features/identity/oauth.py；帳號與客服第 202 批）：授權網址帶 state、nonce、PKCE 與寫死的回呼網址；
id_token 的 iss、aud、exp、nonce、sub 一樣不對就不認；兩家要在 ways 裡、金鑰兩欄都有、redirect_base 不空才算備好。"""
from __future__ import annotations

import base64
import hashlib
import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from tianxia.core import identity_base
from tianxia.core.tuning.identity import IdentityTuning
from tianxia.features.identity import oauth


def _content(**cfg):
    return SimpleNamespace(config=SimpleNamespace(identity=IdentityTuning(**cfg)))


def test_authorize_url_has_state_nonce_pkce_and_fixed_redirect():
    url = oauth.authorize_url("line", "cid-1", "https://example.com/auth/line/callback", "st-1", "no-1", "ver-1")
    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == oauth.PROVIDERS["line"]["authorize"]
    q = {k: v[0] for k, v in parse_qs(parts.query).items()}
    want = base64.urlsafe_b64encode(hashlib.sha256(b"ver-1").digest()).rstrip(b"=").decode()
    assert q == {
        "response_type": "code", "client_id": "cid-1", "redirect_uri": "https://example.com/auth/line/callback",
        "scope": "openid", "state": "st-1", "nonce": "no-1", "code_challenge": want, "code_challenge_method": "S256",
    }
    assert oauth.redirect_uri(_content(redirect_base="https://example.com/"), "google") == "https://example.com/auth/google/callback"
    t = oauth.new_ticket()
    assert len({t["state"], t["nonce"], t["verifier"]}) == 3 and all(len(v) >= 40 for v in t.values())


def _good(**over):
    c = {"iss": "https://access.line.me", "aud": "cid-1", "exp": 1000, "nonce": "no-1", "sub": "U123"}
    c.update(over)
    return c


def test_check_rejects_bad_iss_aud_exp_nonce_and_empty_sub():
    assert oauth.check(_good(), "line", "cid-1", "no-1", 999.0) == "U123"
    assert oauth.check(_good(aud=["x", "cid-1"]), "line", "cid-1", "no-1", 999.0) == "U123"
    assert oauth.check(_good(iss="accounts.google.com"), "google", "cid-1", "no-1", 999.0) == "U123"
    for bad in (_good(iss="https://evil.example"), _good(aud="cid-2"), _good(exp=999), _good(exp="x"), _good(nonce="no-2"),
                _good(sub=""), _good(sub="x" * 256), _good(sub=5), {k: v for k, v in _good().items() if k != "exp"}):
        assert oauth.check(bad, "line", "cid-1", "no-1", 999.0) is None, bad
    assert oauth.check(_good(), "google", "cid-1", "no-1", 999.0) is None  # LINE 的 iss 不是 Google 的
    assert oauth.check(None, "line", "cid-1", "no-1", 999.0) is None
    body = base64.urlsafe_b64encode(json.dumps(_good()).encode()).rstrip(b"=").decode()
    assert oauth.claims(f"h.{body}.s") == _good()
    assert oauth.claims("nope") is None and oauth.claims(f"h.{body[:-3]}!!.s") is None


def test_ready_needs_way_secrets_and_redirect_base(tmp_path, monkeypatch):
    path = tmp_path / "identity.json"
    monkeypatch.setattr(identity_base, "KEY_FILE", path)
    full = {"key": "k" * 32, "line": {"client_id": "a", "client_secret": "b"}, "google": {"client_id": "c", "client_secret": ""}}
    path.write_text(json.dumps(full), encoding="utf-8")
    on = _content(enabled=True, ways=["line", "google"], redirect_base="https://example.com")
    assert oauth.ready(on, "line") and not oauth.ready(on, "google")  # google 少一把
    assert not oauth.ready(_content(enabled=True, ways=["google"], redirect_base="https://example.com"), "line")
    assert not oauth.ready(_content(enabled=True, ways=["line"]), "line")  # 沒有 redirect_base
    assert not oauth.ready(on, "email") and not oauth.ready(on, "nope")
    assert oauth.secrets("line") == {"client_id": "a", "client_secret": "b"} and oauth.secrets("google") is None
    path.write_text("not json", encoding="utf-8")
    assert oauth.secrets("line") is None and not oauth.ready(on, "line")


def test_exchange_goes_through_http_and_swallows_failures(monkeypatch):
    seen = []

    def fake(url, data=None, timeout=None):
        seen.append((url, dict(data), timeout))
        return SimpleNamespace(status_code=200, json=lambda: {"id_token": "a.b.c"})

    monkeypatch.setattr(oauth, "HTTP", fake)
    assert oauth.exchange("google", "code-1", "ver-1", "https://e/auth/google/callback", "cid", "sec") == "a.b.c"
    assert seen == [(oauth.PROVIDERS["google"]["token"], {
        "grant_type": "authorization_code", "code": "code-1", "redirect_uri": "https://e/auth/google/callback",
        "client_id": "cid", "client_secret": "sec", "code_verifier": "ver-1"}, 10)]
    monkeypatch.setattr(oauth, "HTTP", lambda *a, **k: SimpleNamespace(status_code=400, json=lambda: {}))
    assert oauth.exchange("google", "c", "v", "r", "i", "s") is None

    def boom(*a, **k):
        raise OSError("down")

    monkeypatch.setattr(oauth, "HTTP", boom)
    assert oauth.exchange("line", "c", "v", "r", "i", "s") is None
