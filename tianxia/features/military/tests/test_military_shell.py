"""military 這一包的測試，從 tests/server/test_server.py 拆來（全部拆包第 61 批，只搬位置、不改斷言）。"""
import pytest
import server
# autouse 的 fixture 要明列：少一個，這個檔就會在沒有關排程、沒換雜湊參數之下跑（第 61 批）
from server_kit import (  # noqa: F401
    _no_landing, _no_preset_recipes, _season_one_now, cheap_password_hashing, fresh_server_memory, game,
    model_breaker_closed, save_dir, scheduler_off, season_already_open,
)

pytestmark = pytest.mark.whole_content


def test_resting_season_sends_no_orders_and_no_cart(game, monkeypatch):
    """FB-045：收季之後（休季）江湖頁不再有本週軍令卡，也不再寫押糧那一行：收季那一週的軍令截止已經過了。"""
    from tianxia.state import Convoy

    _season_one_now(game, monkeypatch)
    monkeypatch.setattr(server.CONTENT.config, "admins", ["測試"])
    game.sync(game.now)  # 拉回蓋了第一季章的那一份季
    game.state.player.faction = "guan"
    game.advance(700)  # 跨過第一個曆時交界：第 1 週發令
    game.state.player.convoy = Convoy(order="x", grain=4, from_loc="xinye", to_loc="wan_city")
    view = server.main_view(game)
    assert view["orders"] and view["convoy"]
    game.admin_end_season(now=game.now)
    assert game.state.world.ended
    view = server.main_view(game)
    assert "orders" not in view and "convoy" not in view
    assert game.orders_view() == [] and game.convoy_line() is None
