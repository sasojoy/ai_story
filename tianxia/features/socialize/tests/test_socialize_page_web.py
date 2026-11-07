"""socialize 這一包的測試，從 tests/web/test_jianghu_page_web.py 拆來（全部拆包第 61 批，只搬位置、不改斷言）。"""
from __future__ import annotations
import pytest
import webharness
from tianxia import rules
from jianghu_kit import _bar, _cell, _face, _game  # noqa: F401

pytestmark = pytest.mark.whole_content


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
@pytest.mark.slow
def test_a_talked_out_single_figure_social_cell_says_so_briefly_too():
    """一類一顆開著時，單人地點談滿了的交友是灰的 act:socialize，括號裡整句帶換日的那一刻（跟 call: 談滿同一句）。孟津渡是真的會這樣的地方。"""
    game = _game("mengjin_ford")
    content = game.content
    p = game.state.player
    (cid,) = game._figures_here()
    p.flags.add(f"結識:{cid}")
    p.fortune = True
    p.talks_today[cid] = [rules.game_day(content, game.state.world), content.config.talk_turns_per_day]
    option = next(o for o in game.options() if o.id == "act:socialize")
    note = game._talked_out_note()
    assert not option.enabled and option.label == f"交友（{note}）"
    bar = _bar(game)
    assert "<b>交友</b><small>已談滿</small>" in _cell(bar, "social") and "00:00" not in _face(_cell(bar, "social"))
    assert f'data-why="{note}。"' in _cell(bar, "social")
