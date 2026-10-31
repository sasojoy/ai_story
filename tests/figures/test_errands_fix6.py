"""託付的修正輪（減法季批 6 修正輪；PM 2026-10-26 定，交接第四節之十二第 4～6 條、之十四）：
- 託付辦成了的貢獻不吃每天的貢獻上限（deed_contribution_cap，分岔與心意那一本），也不佔那一本的額度；心意一筆照舊共用。
- 託付辦成了的情誼照寫的數字給（不照 affinity_gain_scale 放慢）。
- 收到託付的情誼門檻另開一個數 errand_affinity（20【預設】）；figure_life.letter_affinity（40）照舊給書信與勸降的情誼加成。
- FB-828：投靠了的人只收自己這一邊人物的託付（豪強看此刻幫的那一軍）；散人都收得到。
- FB-827：勸降成了推那一條線 2 點（一次性，不被事件五折），貢獻只記託付的 6；痕跡是 band_turned、有痕跡規則。
正式內容的 season21；模型一律是假的。"""
from __future__ import annotations

import pytest

from stances_kit import BOCAI, LUZHI, at, real_game
from tianxia import calendar, errands, letters, renown, rules


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


@pytest.mark.parametrize("faction, ally, gets", [
    ("guan", None, False),  # 官軍的人收不到波才（黃巾）的託付
    ("huang", None, True),
    ("haoqiang", "guan", False),  # 豪強看此刻幫的那一軍（wins.lean_of）
    ("haoqiang", "huang", True),
    (None, None, True),  # 散人都收得到（本來就不記貢獻）
])
def test_only_your_own_side_figures_send_errands(faction, ally, gets):
    """FB-828：投靠了的人只收自己這一邊人物的託付（豪強看此刻幫的那一軍）；散人都收得到。"""
    g = real_game(faction=faction)
    s = g.state
    s.player.ally = ally
    _friend(g, BOCAI)
    at(g, g.now + 60)
    assert [e.figure for e in s.player.errands] == ([BOCAI] if gets else [])


@pytest.mark.parametrize("fid, eid, faction, line, place", [
    (LUZHI, "luzhi_persuade", "guan", "jizhou", "xiaquyang"),
    (BOCAI, "bocai_persuade", "huang", "yingru", "yingchuan_wilds"),
])
def test_a_won_persuasion_pushes_two_whole_points_and_pays_only_the_errand(fid, eid, faction, line, place):
    """FB-827（設計 5.9）：勸降成了推那一條線 2 點（一次性的推法，同痕跡過門檻：不打事件五折、不吃每人每日上限），貢獻只記託付的 6
    （不另疊推線的貢獻）；留下的痕跡是 band_turned。"""
    def setup(c):
        c.config.jianfa.persuade_floor = c.config.jianfa.persuade_cap = 100
    g = real_game(setup=setup, faction=faction)
    s, c = g.state, g.content
    _friend(g, fid)
    e = _give(g, fid, eid)
    s.player.location = e.target
    assert e.target == place
    before, contrib = rules.trend_value(s, c, line), s.player.contrib
    _press(g, f"errand:persuade:{e.id}")
    g.persuade(g.persuade_request(e.id, "放下刀槍，回家種田吧"), 60)
    assert e.status == "done"
    toward = 1 if faction == "huang" else -1  # 往黃巾為正
    assert rules.trend_value(s, c, line) - before == 2 * toward
    assert s.player.contrib == contrib + 6
    assert s.world.marks == {f"{place}:band_turned": 1}


def test_every_persuasion_mark_is_band_turned_with_a_rule():
    """三件勸降的痕跡都是「地點:band_turned」，每一條都有痕跡規則（地點描寫、傳聞；字待 joy 潤），過了門檻看得見。"""
    g = real_game()
    c = g.content
    rules_by_mark = {r.mark: r for r in c.mark_rules}
    marks = [key for fig in c.figures.values() for d in fig.errands if d.persuade for key in d.persuade.marks]
    assert len(marks) == 3
    for key in marks:
        assert key.endswith(":band_turned") and key in rules_by_mark
        assert rules_by_mark[key].describe and rules_by_mark[key].rumor


def test_a_stance_point_still_shares_the_daily_cap():
    """心意那一筆 1 點照舊跟分岔共用每天的上限：記滿了就不記。"""
    g = real_game()
    s, c = g.state, g.content
    s.player.deed_day, s.player.deed_today = _today(g), c.config.jianfa.deed_contribution_cap
    contrib = s.player.contrib
    assert g.voice_stance(LUZHI, "suzhan")
    assert s.player.contrib == contrib
