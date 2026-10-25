"""人物心意的修正輪（減法季批 6 修正輪；PM 2026-10-26 定，交接第四節之十四）：
- FB-825：「你今天勸的」（my_stance_today）只看說話記的那一筆；辦成託付的心意 +1 不改它（行狀照舊兩樣都認）。
- FB-826：心意過門檻那一刻先生效；之後換手只在每天 00:00 重算；同一位人物的江湖史一週只記一次（天下大事照換手發）。
正式內容的 season21；模型一律是假的。"""
from __future__ import annotations

import pytest

from stances_kit import DAY, HOUR, LUZHI, MON, at, real_game, week_start_real
from tianxia import errands, stances

pytestmark = pytest.mark.slow  # 載正式內容、照伺服器開季


def _deliver(g, fid=LUZHI, eid="luzhi_letter"):
    """替他辦成一件送信（ErrandDef.stance：盧植的送信是持重）。"""
    s = g.state
    s.player.affinities[fid] = 50
    errands.give(s, g.content, fid, eid)
    e = s.player.errands[-1]
    s.player.location = e.target
    g.choose(f"errand:deliver:{e.id}")
    assert e.status == "done"


def test_an_errand_does_not_change_what_you_said_today():
    """FB-825：先說速戰、同一天辦成持重的託付——你今天勸的還是速戰；兩樣都記在這一週說過的（行狀用）。"""
    g = real_game()
    s, c = g.state, g.content
    assert stances.record(s, c, LUZHI, "suzhan")
    _deliver(g)
    assert s.world.stance_counts[LUZHI] == {"suzhan": 1, "chizhong": 1}
    assert stances.heard_today(s, c, LUZHI) == "suzhan"
    assert stances.view(s, c, LUZHI)["my_stance_today"] == "suzhan"
    assert s.player.stance_notes[LUZHI].said == ["suzhan", "chizhong"]


def _told(g, fid=LUZHI):
    """這一季寫進共用的季的天下大事（world 層傳聞）與江湖史裡，他那三個心意的句子各幾則。"""
    season = g.world.get_season()
    lines = {x.rumor for x in g.content.figures[fid].stances}
    return (sum(r.layer == "world" and r.text in lines for r in season.rumors),
            sum(e.text in lines or any(e.text == (x.chronicle or x.rumor) for x in g.content.figures[fid].stances)
                for e in season.chronicle))


def test_switching_waits_for_midnight_and_the_chronicle_tells_it_once_a_week():
    """FB-826：過門檻那一刻先生效（天下大事＋江湖史）；之後另一個心意追過去也不馬上換，每天 00:00 才重算——換了照發天下大事，
    江湖史同一位人物一週只記一次。"""
    g = real_game()
    at(g, g.now + HOUR)  # 開季那一天的掛鉤先跑過（週一 11:00）
    s, c = g.state, g.content
    w = s.world
    assert w.hooked_day == 1
    w.stance_week, w.stance_counts = stances.week_of(c, w), {LUZHI: {"suzhan": 29, "chizhong": 29}}
    assert stances.record(s, c, LUZHI, "suzhan")  # 速戰到門檻：馬上生效
    assert w.stance_active[LUZHI].stance == "suzhan"
    g._save_season()
    assert _told(g) == (1, 1)
    w.stance_counts[LUZHI]["chizhong"] = 31  # 持重追過去（例：好幾個人記了一筆）
    assert stances.check(s, c, LUZHI).id == "suzhan"  # 白天不換
    assert stances.push_scale(s, c, LUZHI) == 2 and w.stance_active[LUZHI].stance == "suzhan"
    g._save_season()
    assert _told(g) == (1, 1)
    at(g, MON + DAY + HOUR)  # 跨過週二 00:00：重算，換成持重
    w = g.state.world
    assert w.stance_active[LUZHI].stance == "chizhong" and stances.push_scale(g.state, c, LUZHI) == 0
    assert _told(g) == (2, 1)  # 天下大事照換手發，江湖史這一週不再記
    w.stance_counts[LUZHI]["suzhan"] = 40
    g._save_season()
    at(g, MON + 2 * DAY + HOUR)  # 週三 00:00：又換回速戰
    assert g.state.world.stance_active[LUZHI].stance == "suzhan"
    assert _told(g) == (3, 1)


def test_a_new_week_tells_the_chronicle_again():
    """江湖史一週一次：下一週又過門檻，照樣記一筆。"""
    g = real_game()
    at(g, g.now + HOUR)
    s, c = g.state, g.content
    w = s.world
    w.stance_week, w.stance_counts = stances.week_of(c, w), {LUZHI: {"suzhan": 29}}
    assert stances.record(s, c, LUZHI, "suzhan")
    g._save_season()
    at(g, week_start_real(g, 2))
    s, w = g.state, g.state.world
    assert w.stance_active == {}
    w.stance_counts = {LUZHI: {"chizhong": 29}}
    assert stances.record(s, c, LUZHI, "chizhong")
    g._save_season()
    assert _told(g) == (2, 2)


def test_an_errand_alone_is_not_what_you_said_and_you_can_still_speak():
    """只辦了託付、今天還沒跟他說話：你今天勸的是空的，說話照樣記得到一筆，記的就是說的那一個。"""
    g = real_game()
    s, c = g.state, g.content
    _deliver(g)
    assert stances.heard_today(s, c, LUZHI) is None
    assert stances.record(s, c, LUZHI, "xumin")
    assert stances.heard_today(s, c, LUZHI) == "xumin"
    assert not stances.record(s, c, LUZHI, "suzhan")  # 一人一天一筆照舊
