"""bout 這一包的測試，從 tests/server/test_server.py 拆來（全部拆包第 61 批，只搬位置、不改斷言）。"""
from unittest import mock
import pytest
import server
from conftest import at
from tianxia.core import battle_base as battle_instance  # 第二輪第 102 批：bout.routes 讀核心那一格
from tianxia.sqlite_world import open_world
# autouse 的 fixture 要明列：少一個，這個檔就會在沒有關排程、沒換雜湊參數之下跑（第 61 批）
from server_kit import (  # noqa: F401
    _no_landing, _no_preset_recipes, cheap_password_hashing, fresh_server_memory, game, model_breaker_closed, save_dir,
    scheduler_off, season_already_open,
)

pytestmark = pytest.mark.whole_content


def test_duel_free_text_is_rated_outside_the_action_lock(game, monkeypatch):
    """單人頭目戰的放手一搏（Joy 2026-10-10）：輸入框送到 duel_text，成功率與兩版劇情在鎖外評，C 段照評好的擲骰。"""
    from tianxia.features.bout import duel_rules as duel

    game.client = None
    game.state.player.location = "changshe"
    with at(game, 0.0):
        game._duel_start(duel.available(game.state, game.content))
        view = server.look(game, server.main_view)
        assert view["free_text"] == game.duel_free_text_prompt() and view["free_op"] == "duel_text"
        assert view["free_text_note"] == game.DUEL_GAMBLE_NOTE
        seen = []

        def rate(client, act_, faction_name, text, name, setting, place, target="", sex="男"):
            seen.append((open_world().db.writing(), act_.title, faction_name, text, name, place))
            return battle_instance.GambleVerdict(100, "測試一把撒出石灰。", "測試踩到自己的衣角。")

        monkeypatch.setattr(battle_instance, "assess_gamble", rate)
        with mock.patch("server.time.time", return_value=0.0):
            msgs = server.duel_text(game, "撒石灰")
    assert seen == [(False, "黃巾小帥段鐵頭", "散人", "撒石灰", "測試", duel.PLACE)]
    assert msgs[0].startswith("第 1 回合：測試一把撒出石灰。（氣勢 +")
