"""map 這一包的測試，從 tests/core/test_engine.py 拆來（全部拆包第 61 批，只搬位置、不改斷言）。"""
import pytest
from conftest import walk_to

pytestmark = pytest.mark.whole_content


def test_visited_and_map(game):
    assert game.state.player.visited == {"town"}
    walk_to(game, "lake")
    assert game.state.player.visited == {"town", "lake"}
    assert "<svg" in game.world_map_svg()
    assert "<svg" in game.minimap_svg()
