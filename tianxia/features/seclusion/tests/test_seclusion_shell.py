"""seclusion 這一包的測試，從 tests/server/test_server.py 拆來（全部拆包第 61 批，只搬位置、不改斷言）。"""
import pytest
# autouse 的 fixture 要明列：少一個，這個檔就會在沒有關排程、沒換雜湊參數之下跑（第 61 批）
from server_kit import (  # noqa: F401
    _no_landing, _no_preset_recipes, _player, cheap_password_hashing, client, fresh_server_memory, model_breaker_closed,
    save_dir, scheduler_off, season_already_open,
)

pytestmark = pytest.mark.whole_content


def test_seclude_and_anonymous(client):
    _player(client)
    out = client.post("/api/do/anonymous", json={"value": True}).json()
    assert out["main"]["status"]["anonymous"] is True
    out = client.post("/api/do/seclude", json={"hours": 2}).json()
    assert out["main"]["status"]["busy_hours"] is not None
