"""人物心意同票改成「追過才換」（減法季 7e，PM 2026-10-26；批 6 複驗看到的不公平）。

以前每天 00:00 重算，最多的那一個照內容順序挑：同票時排在前面的心意「追平就換手」（它是 _best），排在後面的心意追平不會換——
兩個心意同票，結果取決於誰排前面。改成：此刻照著做的心意只有在別的心意票數「超過」它時才換，追平不換；兩個方向（前面的追平、
後面的追平）都不換。第一次過門檻那一刻先生效、白天不換、江湖史一週一次，都照舊（test_stances.py、test_stances_fix6.py）。
正式內容的 season21（盧植的三個心意照內容順序是 suzhan、chizhong、xumin）；模型一律是假的。"""
from __future__ import annotations

import pytest

from stances_kit import DAY, HOUR, LUZHI, MON, at, real_game
from tianxia import stances
from tianxia.state import StanceOn


def _set(game, active: str | None, counts: dict[str, int]) -> None:
    """這一週的計數與他此刻照著做的心意（同 stances.check 到門檻那一刻寫的）。"""
    w = game.state.world
    w.stance_week = stances.week_of(game.content, w)
    w.stance_counts = {LUZHI: dict(counts)}
    w.stance_active = {LUZHI: StanceOn(stance=active, at=w.time, week=w.stance_week)} if active is not None else {}


def _now(game) -> str | None:
    now = game.state.world.stance_active.get(LUZHI)
    return now.stance if now is not None else None


def _told(game) -> int:
    """天下大事裡他三個心意的句子共幾則。"""
    lines = {x.rumor for x in game.content.figures[LUZHI].stances}
    return sum(r.layer == "world" and r.text in lines for r in game.state.world.rumors)


# 盧植的順序：suzhan（前）、chizhong（中）、xumin（後）
TABLE = [
    # 此刻照著做的, 計數, 00:00 之後
    ("suzhan", {"suzhan": 31, "chizhong": 31}, "suzhan"),  # 排前面的同票：不換（以前也不換）
    ("chizhong", {"suzhan": 31, "chizhong": 31}, "chizhong"),  # 排後面的同票：不換（以前被排前面的追平就搶走）
    ("xumin", {"suzhan": 33, "chizhong": 33, "xumin": 33}, "xumin"),  # 三個同票：此刻的那個留著
    ("chizhong", {"suzhan": 32, "chizhong": 31}, "suzhan"),  # 前面的超過才換
    ("suzhan", {"suzhan": 31, "chizhong": 32}, "chizhong"),  # 後面的超過才換
    ("suzhan", {"suzhan": 31, "chizhong": 32, "xumin": 32}, "chizhong"),  # 兩個都超過：照內容順序挑前面的（挑戰者之間沒有誰先到）
    ("xumin", {"suzhan": 31, "chizhong": 31, "xumin": 30}, "suzhan"),  # 此刻的反而最少（兩個超過）：照內容順序
]


@pytest.mark.parametrize(("active", "counts", "expected"), TABLE)
def test_midnight_swaps_only_when_someone_passes_him(active, counts, expected):
    g = real_game()
    _set(g, active, counts)
    got = stances.check(g.state, g.content, LUZHI, midnight=True)
    assert got is not None and got.id == expected and _now(g) == expected


@pytest.mark.parametrize(("active", "counts", "expected"), TABLE)
def test_the_real_midnight_hook_does_the_same(active, counts, expected):
    """每天 00:00 真的是 stances.daily 叫的（world.DAY_HOOKS）：跨過週二 00:00 之後，結果跟直接叫 check 一樣。"""
    g = real_game()
    at(g, g.now + HOUR)  # 開季那一天的掛鉤先跑過（週一 11:00）
    _set(g, active, counts)
    g._save_season()
    at(g, MON + DAY + HOUR)  # 週二 00:00 之後
    assert _now(g) == expected


def test_a_tie_says_nothing_to_the_world_and_a_pass_does():
    """追平不換：天下大事一則都不多；超過才換，換了發一則（江湖史這一週已經記過，不再記，FB-826）。"""
    g = real_game()
    _set(g, "chizhong", {"suzhan": 31, "chizhong": 31})
    told = _told(g)
    stances.check(g.state, g.content, LUZHI, midnight=True)
    assert _told(g) == told and _now(g) == "chizhong"
    g.state.world.stance_counts[LUZHI]["suzhan"] = 32
    stances.check(g.state, g.content, LUZHI, midnight=True)
    assert _now(g) == "suzhan" and _told(g) == told + 1


def test_catching_up_again_after_a_swap_does_not_swap_back_until_it_passes():
    """換手之後，被換下來的心意追平不換回去，要再超過才換；兩個方向都走一遍。"""
    g = real_game()
    _set(g, "suzhan", {"suzhan": 30, "chizhong": 30})
    counts = g.state.world.stance_counts[LUZHI]

    def midnight() -> str | None:
        stances.check(g.state, g.content, LUZHI, midnight=True)
        return _now(g)

    assert midnight() == "suzhan"  # 同票
    counts["chizhong"] = 31
    assert midnight() == "chizhong"  # 後面的超過
    counts["suzhan"] = 31
    assert midnight() == "chizhong"  # 前面的追平：不搶回去（以前會，它是 _best）
    counts["suzhan"] = 32
    assert midnight() == "suzhan"  # 前面的超過才換
    counts["chizhong"] = 32
    assert midnight() == "suzhan"  # 後面的追平：不換


def test_by_day_nothing_changes_and_the_first_crossing_still_takes_effect():
    """舊規則照舊：白天（不是 00:00）一律不換；還沒照哪一個做事時，第一個過門檻的當場生效。"""
    g = real_game()
    _set(g, "chizhong", {"suzhan": 40, "chizhong": 31})
    assert stances.check(g.state, g.content, LUZHI).id == "chizhong" and _now(g) == "chizhong"
    _set(g, None, {"suzhan": 29, "chizhong": 5})
    assert stances.record(g.state, g.content, LUZHI, "suzhan") and _now(g) == "suzhan"
