"""客服查帳號（帳號與客服第 212 批；設計 6.3）：只收完整帳號、Email、手機（比對 HMAC），要帶單號，每位客服每小時 lookup_hourly 次，
每次留紀錄（含查無；只存遮好的字），紀錄沒有路由改得到；看單時單上的帳號帶出帳號卡（不算次數、照樣留紀錄）；假人查起來跟沒有這個人一樣。"""
from __future__ import annotations

import pytest
import server
from fastapi.testclient import TestClient
# autouse 的 fixture 要明列（第 61 批）
from server_kit import (  # noqa: F401
    _no_landing, _no_preset_recipes, cheap_password_hashing, fresh_server_memory, model_breaker_closed, save_dir, scheduler_off,
    season_already_open,
)
from support_kit import player, sidecar, staffer, support_isolated, support_on, ticket  # noqa: F401

from tianxia.accounts import AccountStore
from tianxia.database import open_database

pytestmark = [pytest.mark.whole_content, pytest.mark.usefixtures("support_on")]


def _id_key_client(provider="line", subject="U-line-1", display="LINE 使用者") -> tuple[TestClient, str]:
    """沒有密碼列的帳號（第三方或驗證碼開的，帳號鍵 id:<n>），直接發一張登入狀態。"""
    key = AccountStore(open_database()).create_without_password(provider, subject, display)
    c = TestClient(server.app, raise_server_exceptions=False)
    c.cookies.set(server.COOKIE, server.SESSIONS.create(key))
    return c, key


def test_id_key_account_sends_ticket():
    c, key = _id_key_client()
    r = ticket(c)
    assert r.status_code == 200, r.text
    mine = c.get("/api/support/mine").json()["tickets"]
    assert [t["id"] for t in mine] == [r.json()["id"]]
