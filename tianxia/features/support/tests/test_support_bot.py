"""客服官的 token 身分（客服自動受理第 216 批；設計 5.2、5.3、第八節，企劃者 2026-11-10「照計畫繼續」）：
Authorization: Bearer 只在客服的路由認；錯的、沒設的一律 404 同一句；token 不能查帳號；別的路由 Bearer 不認。"""
from __future__ import annotations

import pytest
import server
from server_kit import (  # noqa: F401
    _no_landing, _no_preset_recipes, cheap_password_hashing, fresh_server_memory, model_breaker_closed, save_dir, scheduler_off,
    season_already_open,
)
from support_kit import bot_setup, player, staffer, support_isolated, support_on, ticket  # noqa: F401

from tianxia.database import open_database
from tianxia.features.support import accounts_view, staff

pytestmark = [pytest.mark.whole_content, pytest.mark.usefixtures("support_on")]


def test_bot_account_id_by_id_or_login(monkeypatch):
    player("desk_01", "青鸞")
    db, config = open_database(), server.CONTENT.config
    me = accounts_view.by_key(db, "desk_01")
    monkeypatch.setattr(config.support, "bot_account", "")
    assert staff.bot_account_id(config, db) is None  # 空
    monkeypatch.setattr(config.support, "bot_account", "  ")
    assert staff.bot_account_id(config, db) is None
    monkeypatch.setattr(config.support, "bot_account", str(me.id))
    assert staff.bot_account_id(config, db) == me.id  # id
    monkeypatch.setattr(config.support, "bot_account", " DESK_01 ")
    assert staff.bot_account_id(config, db) == me.id  # 登入名，不分大小寫
    monkeypatch.setattr(config.support, "bot_account", "nobody_9")
    assert staff.bot_account_id(config, db) is None  # 不存在
    monkeypatch.setattr(config.support, "bot_account", "999")
    assert staff.bot_account_id(config, db) is None  # id 不在
    monkeypatch.setattr(config.support, "bot_account", "青鸞")
    assert staff.bot_account_id(config, db) is None  # 名號不認
