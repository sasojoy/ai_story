"""舊存檔（帳號與客服第 211 批）：這一包沒有存檔欄位，開關關著時建的角色照讀；打開之後跑本人那一輪，沒有旁檔不建檔、沒有客服回覆時存檔一個位元組不變。"""
from __future__ import annotations

import pytest
import server
from server_kit import (  # noqa: F401
    _no_landing, _no_preset_recipes, cheap_password_hashing, fresh_server_memory, model_breaker_closed, save_dir, scheduler_off,
    season_already_open,
)
from support_kit import player, sidecar, support_isolated, ticket  # noqa: F401

from tianxia.characters import open_characters
from tianxia.engine import Game
from tianxia.features import support as package

pytestmark = pytest.mark.whole_content


def test_an_old_save_reads_and_stays_byte_for_byte(monkeypatch):
    c = player()  # 關著建的角色
    monkeypatch.setattr(server.CONTENT.config.support, "enabled", True)
    game = Game(server.CONTENT, open_characters().load("沈青衫"))  # 照讀
    before = game.state.model_dump_json()
    package.FEATURE.on_own_turn(game)
    assert not sidecar().exists()
    assert game.state.model_dump_json() == before
    assert ticket(c).status_code == 200  # 有旁檔、沒有回覆
    package.FEATURE.on_own_turn(game)
    assert game.state.model_dump_json() == before
