"""客服包（帳號與客服第 211 批）：開關關著（預設）一個字都不變——七條路由登入後 404、沒登入 401（開著關著一樣）、/api/main 不多鍵、不建旁檔、
on_own_turn 對假人與關著什麼都不做。"""
from __future__ import annotations

import pytest
import server
from fastapi.testclient import TestClient
# autouse 的 fixture 要明列（第 61 批）
from server_kit import (  # noqa: F401
    _no_landing, _no_preset_recipes, cheap_password_hashing, fresh_server_memory, game, model_breaker_closed, save_dir, scheduler_off,
    season_already_open,
)
from support_kit import ROUTES, hit, player, sidecar, support_isolated, support_on, ticket  # noqa: F401

from tianxia.core import features as features_core
from tianxia.features import support as package

pytestmark = pytest.mark.whole_content


def test_the_package_is_registered_and_off_by_default():
    assert package.FEATURE in features_core.registered()
    assert package.FEATURE.prefix is None and package.FEATURE.player_fields == ()
    assert server.CONTENT.config.support.enabled is False


def test_routes_404_while_closed():
    c = player()
    replies = {path: hit(c, method, path, body).status_code for method, path, body in ROUTES}
    assert replies == {path: 404 for _, path, _ in ROUTES}


@pytest.mark.parametrize("on", [False, True])
def test_routes_401_without_login_either_way(on, monkeypatch):
    monkeypatch.setattr(server.CONTENT.config.support, "enabled", on)
    anon = TestClient(server.app, raise_server_exceptions=False)
    assert {path: hit(anon, method, path, body).status_code for method, path, body in ROUTES} == {path: 401 for _, path, _ in ROUTES}


def test_main_has_no_support_keys_while_closed():
    c = player()
    main = c.get("/api/main").json()
    assert not [k for k in main if k.startswith("support")]


def test_no_sidecar_while_closed():
    c = player()
    for method, path, body in ROUTES:
        hit(c, method, path, body)
    c.get("/api/main")
    assert not sidecar().exists()


def test_no_sidecar_when_open_until_someone_files(support_on):
    c = player()
    c.get("/api/main")
    assert c.get("/api/support/mine").json()["tickets"] == []
    assert not sidecar().exists()
    assert ticket(c).status_code == 200
    assert sidecar().exists()


def test_on_own_turn_skips_bots_and_closed(game, monkeypatch):
    """假人第一行就跳過、關著也跳過：旁檔的路徑一次都不問。"""
    from tianxia.features.support import notes

    asked = []
    monkeypatch.setattr(notes, "journal_replies", lambda ctx: asked.append(ctx))
    package.FEATURE.on_own_turn(game)  # 關著
    monkeypatch.setattr(server.CONTENT.config.support, "enabled", True)
    game.state.player.bot = object()  # 不驗型別（沒開 validate_assignment）：on_own_turn 只問 is not None
    package.FEATURE.on_own_turn(game)  # 假人
    assert asked == []
    game.state.player.bot = None
    package.FEATURE.on_own_turn(game)
    assert asked == [game]


def test_gate_line_is_empty_while_closed(monkeypatch):
    config = server.CONTENT.config
    assert package.FEATURE.gate_slot(config) == ""
    monkeypatch.setattr(config.support, "enabled", True)
    assert package.FEATURE.gate_slot(config) == "登不進去？寫信到客服信箱：support@tianxiadashi.com（人工回信）"
