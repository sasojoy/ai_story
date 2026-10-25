"""託付的修正輪（減法季批 6 修正輪；PM 2026-10-26 定，交接第四節之十二第 4～6 條、之十四）：
- 託付辦成了的貢獻不吃每天的貢獻上限（deed_contribution_cap，分岔與心意那一本），也不佔那一本的額度；心意一筆照舊共用。
正式內容的 season21；模型一律是假的。"""
from __future__ import annotations

import pytest

from stances_kit import LUZHI, real_game
from tianxia import calendar, errands

pytestmark = pytest.mark.slow  # 載正式內容、照伺服器開季


def _friend(g, cid=LUZHI, affinity=50):
    g.state.player.affinities[cid] = affinity


def _give(g, fid, eid):
    errands.give(g.state, g.content, fid, eid)
    return g.state.player.errands[-1]


def _press(g, option_id):
    opts = {o.id: o for o in g.options(odds=False)}
    assert option_id in opts and opts[option_id].enabled, sorted(opts)
    return g.choose(option_id)


def _today(g) -> int:
    w = g.state.world
    return calendar.point(w.time, g.content, w).cal_day


@pytest.mark.parametrize("used", [0, 12])
def test_errand_contribution_ignores_the_daily_deed_cap(used):
    """分岔的後果記滿了那一天（12），辦成託付照樣記足（送信 +4）；也不佔那一本：記完那一本還是原本的數。"""
    g = real_game()
    s, c = g.state, g.content
    assert c.config.jianfa.deed_contribution_cap == 12
    _friend(g)
    e = _give(g, LUZHI, "luzhi_letter")
    s.player.location = e.target
    s.player.deed_day, s.player.deed_today = _today(g), used
    contrib = s.player.contrib
    _press(g, f"errand:deliver:{e.id}")
    assert e.status == "done"
    assert s.player.contrib == contrib + 4
    assert (s.player.deed_day, s.player.deed_today) == (_today(g), used)


def test_a_stance_point_still_shares_the_daily_cap():
    """心意那一筆 1 點照舊跟分岔共用每天的上限：記滿了就不記。"""
    g = real_game()
    s, c = g.state, g.content
    s.player.deed_day, s.player.deed_today = _today(g), c.config.jianfa.deed_contribution_cap
    contrib = s.player.contrib
    assert g.voice_stance(LUZHI, "suzhan")
    assert s.player.contrib == contrib
