"""託付的修正輪（減法季批 6 修正輪；PM 2026-10-26 定，交接第四節之十二第 4～6 條、之十四）：
- 託付辦成了的貢獻不吃每天的貢獻上限（deed_contribution_cap，分岔與心意那一本），也不佔那一本的額度；心意一筆照舊共用。
- 託付辦成了的情誼照寫的數字給（不照 affinity_gain_scale 放慢）。
- 收到託付的情誼門檻另開一個數 errand_affinity（20【預設】）；figure_life.letter_affinity（40）照舊給書信與勸降的情誼加成。
正式內容的 season21；模型一律是假的。"""
from __future__ import annotations

import pytest

from stances_kit import LUZHI, at, real_game
from tianxia import calendar, errands, letters, renown

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


@pytest.mark.parametrize("start, gain", [(50, 5), (98, 2)])
def test_errand_affinity_is_paid_as_written(start, gain):
    """託付辦成了的情誼照寫的數字給（+5 就是 +5），不照 affinity_gain_scale 放慢；照舊夾在 100，訊息寫實際動了多少。"""
    g = real_game()
    s, c = g.state, g.content
    assert renown.warmed(c, 5) != 5  # season21 的情誼放慢：事件給的 +5 實得不到 5
    _friend(g, affinity=start)
    e = _give(g, LUZHI, "luzhi_letter")
    s.player.location = e.target
    msgs = _press(g, f"errand:deliver:{e.id}")
    assert s.player.affinities[LUZHI] == start + gain
    assert f"盧植情誼 +{gain}" in msgs


@pytest.mark.parametrize("affinity, gets", [(20, True), (19, False)])
def test_errands_come_at_their_own_affinity_floor(affinity, gets):
    """收到託付的情誼門檻另開一個數 errand_affinity（20【預設】），不是書信的 letter_affinity（40）。"""
    g = real_game()
    s, c = g.state, g.content
    assert (c.config.jianfa.errand_affinity, c.config.figure_life.letter_affinity) == (20, 40)
    _friend(g, affinity=affinity)
    at(g, g.now + 60)
    assert bool(s.player.errands) == gets
    if gets:
        assert s.player.errands[-1].figure == LUZHI


def test_letters_and_persuasion_still_read_letter_affinity():
    """道賀、邀宴、求援的信照舊要 letter_affinity（40）；勸降的情誼加成照舊算「高於 40 的部分」。"""
    g = real_game()
    s, c = g.state, g.content
    _friend(g, affinity=39)
    assert not letters._reachable(s, c, LUZHI)  # noqa: SLF001
    _friend(g, affinity=40)
    assert letters._reachable(s, c, LUZHI)  # noqa: SLF001
    _friend(g, affinity=48)
    e = _give(g, LUZHI, "luzhi_persuade")
    s.player.stats["fame"] = 0
    assert errands.persuade_rate(s, c, e, 50) == 50 + (48 - 40) // c.config.jianfa.persuade_affinity_step


def test_a_stance_point_still_shares_the_daily_cap():
    """心意那一筆 1 點照舊跟分岔共用每天的上限：記滿了就不記。"""
    g = real_game()
    s, c = g.state, g.content
    s.player.deed_day, s.player.deed_today = _today(g), c.config.jianfa.deed_contribution_cap
    contrib = s.player.contrib
    assert g.voice_stance(LUZHI, "suzhan")
    assert s.player.contrib == contrib
