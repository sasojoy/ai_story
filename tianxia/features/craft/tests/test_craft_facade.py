"""craft 這一包的測試，從 tests/core/test_engine.py 拆來（全部拆包第 61 批，只搬位置、不改斷言）。"""
import pytest

pytestmark = pytest.mark.whole_content


# ── 伺服器假人替合成與定名開單（假人的 Game 沒有 client，假人程式在鎖外自己叫模型）──────────


def test_a_forge_request_for_a_caller_who_names_outside(game):
    """伺服器假人的 Game 沒有 client，但假人程式在鎖外自己叫模型：named_outside 時照樣開單。
    煉製只剩意境＋意境：要取名的是兩個不同意境的合併。"""
    p = game.state.player
    p.insights, p.stats["xinde"], p.stamina = ["feng", "huo"], 100, 150
    game.client = None
    assert game.forge_request(None, ["feng", "huo"]) is None
    request = game.forge_request(None, ["feng", "huo"], named_outside=True)
    assert request is not None and request.kind == "merge"
    assert game.forge_request("basic_fist", ["feng", "huo"], named_outside=True) is None  # 爐裡放武學：會被擋下，不開單
