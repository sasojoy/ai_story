"""閉關的煙霧測試（開發規範手冊 4.1 第三級：一包一條，走一次最常見的路）：閉關、選單只剩提早出關、自己滿時出關給心得、提早出關按比例給。
原本是 tests/core/test_engine.py 的 test_seclusion_grants_xinde 與 test_break_seclusion_early 的合併（那兩條留在原處，混合檔不拆）。"""
import pytest

HOUR = 3600


@pytest.mark.smoke
def test_seclude_then_wait_out_or_break_early(game):
    assert game.seclude(4)[0].startswith("你閉關靜修")
    assert [o.id for o in game.options() if o.id.startswith("act:")][:1] == ["act:break"]
    game.advance(4 * HOUR)
    assert game.state.player.busy_until is None
    assert game.state.player.stats["xinde"] == 75  # 4 小時 × 15 × (1 + 5/20)
    game.seclude(4)
    game.advance(HOUR)
    game.choose("act:break")
    assert game.state.player.busy_until is None
    assert game.state.player.stats["xinde"] == 75 + 19  # round(1 × 15 × 1.25)
