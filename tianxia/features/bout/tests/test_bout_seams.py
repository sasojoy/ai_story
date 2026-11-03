"""單挑包接上第 11 批掛鉤的那幾處（收店、假人在擂台邊只按返回、坐著的時候開關被關掉照樣開著）、更新分身的形象，與核心兩個小規則
（勝負的門檻、戰績那一句）。搬包的時候只有 scripts/same_behavior.py 守這幾樣（全部拆包第 12 批審查的變異 M14、M6、M7、M8、C3、C4：
包加 26 個混合檔一條都不紅）；第 12 批審查修正補的，不是從別處搬來的。擂台照 test_arena 的 _ring 開（測試內容，沒有頭目）。"""
from __future__ import annotations

import pytest
from test_arena import _do, _join, _ring

from tianxia import atlas
from tianxia.core import arena_ranks, duel_base
from tianxia.core.option import Option
from tianxia.engine import Game
from tianxia.features import bout
from tianxia.features.bout import bots
from tianxia.models import DuelTuning
from tianxia.state import ArenaEntry


@pytest.mark.parametrize("option_id, expected", [
    ("arena:back", 0.0), ("arena:join", None), ("arena:fight:乙", None), ("arena:固守", None), ("arena:yield", None),
    ("duel:固守", None), ("duel:flee", None), ("tavern:back", None),
])
def test_the_bots_score_only_the_way_back_from_the_ring_edge(option_id, expected):
    """假人（bot_policy.score 先問這一包，features_core.bot_pick）：坐在擂台邊只會按返回（0 分）；報名、挑人、三招、認輸是
    bot_policy._arena 與 take_turn 的步驟，頭目戰照架勢出招，都不給分（None＝不按）。審查 M6：返回不給分，假人一直坐在擂台邊。"""
    assert bots.score(Option(id=option_id, label="")) == expected


def test_the_package_stays_open_while_someone_still_sits_at_the_ring_with_the_switch_off(content, world):
    """沒有頭目的內容、擂台關著：沒在打也沒坐著，這一包是關的；坐在擂台邊（開關在坐著的時候被關掉、還沒經過 sync 收店）照樣開著，
    返回才按得到、假人才問得到這一包（審查 M7）。"""
    content, world = _ring(content, world, ("甲",))
    content.config.arena.enabled = False
    _, game = _do(content, world, "甲", lambda g: [])
    assert not content.duels
    p = game.state.player
    assert not p.picking_arena and p.arena is None and p.duel is None
    assert not bout.FEATURE.enabled(game)
    p.picking_arena = True
    assert bout.FEATURE.enabled(game)


def test_sitting_at_the_ring_is_put_away_when_the_ring_closes(content, world):
    """坐在擂台邊：擂台開著時同步不收；開關關掉，下一次同步收起來（店面登記的 close：原本 sync 那一行 picking_arena = False）。審查 M14。"""
    content, world = _ring(content, world, ("甲",))
    _, game = _do(content, world, "甲", lambda g: g.choose("act:arena"))
    assert game.state.player.picking_arena
    _, game = _do(content, world, "甲", lambda g: [])
    assert game.state.player.picking_arena
    content.config.arena.enabled = False
    _, game = _do(content, world, "甲", lambda g: [])
    assert not game.state.player.picking_arena


def test_setting_out_puts_the_ring_away(content, world):
    """坐在擂台邊直接動身（Game._depart；平常從輿圖安排前往會被擋，同酒肆那一軌）：擂台跟別的店一起收起來（原本 _depart 那一行）。"""
    content, world = _ring(content, world, ("甲",))

    def go(g):
        g.choose("act:arena")
        assert g.state.player.picking_arena
        return g._depart(atlas.way_to(g.state, content, "lake"), "walk")

    _, game = _do(content, world, "甲", go)
    assert not game.state.player.picking_arena


def test_signing_up_again_takes_the_look_worn_now(content, world, monkeypatch):
    """更新分身（報名之後再按一次報名）：分身穿哪一套照此刻的重記（形象包的 arena_look，包裡經 ctx 叫；原本 _arena_join 更新那一支）。
    審查 M8：更新那一支不記，test_arena 只驗了第一次報名。"""
    content, world = _ring(content, world, ("甲",))
    look = ["moying"]
    monkeypatch.setattr(Game, "arena_look", lambda self: look[0])
    _join(content, world, "甲")
    assert world.get_season().arena["甲"].look == "moying"
    look[0] = "qingshan"
    _join(content, world, "甲")
    assert world.get_season().arena["甲"].look == "qingshan"


def test_the_bout_verdict_at_its_thresholds():
    """單挑底層的勝負（頭目戰、擂台、奪璽單挑共用）：中途到 early_win 大勝、到 early_lose 或池子見底落敗；打滿看 big、win、draw，
    門檻那一點算上一級（審查 C3：大勝的門檻挪了沒有測試紅）。"""
    t = DuelTuning()
    assert duel_base.verdict_at(t.early_win, 100, 1, 5, t) == "大勝"
    assert duel_base.verdict_at(t.early_win - 0.5, 100, 1, 5, t) is None
    assert duel_base.verdict_at(t.early_lose, 100, 1, 5, t) == "落敗"
    assert duel_base.verdict_at(t.early_lose + 0.5, 100, 1, 5, t) is None
    assert duel_base.verdict_at(t.start, 0, 1, 5, t) == "落敗"
    assert duel_base.verdict_at(t.big, 100, 5, 5, t) == "大勝"
    assert duel_base.verdict_at(t.big - 0.5, 100, 5, 5, t) == "險勝"
    assert duel_base.verdict_at(t.win, 100, 5, 5, t) == "險勝"
    assert duel_base.verdict_at(t.win - 0.5, 100, 5, 5, t) == "僵持"
    assert duel_base.verdict_at(t.draw, 100, 5, 5, t) == "落敗"
    assert duel_base.verdict_at(t.draw + 0.5, 100, 5, 5, t) == "僵持"


def test_the_record_line_names_a_streak_from_two_wins():
    """擂台榜、名帖、玩家卡寫的戰績（核心 arena_ranks.record_text）：沒打過寫還沒打過；連勝兩場起才寫（審查 C4：門檻改成 3 沒有測試紅）。"""
    e = ArenaEntry(name="甲", power=10, hp_cap=100, rank=1)
    assert arena_ranks.record_text(e) == "還沒打過"
    e.wins, e.losses, e.streak = 1, 1, 1
    assert arena_ranks.record_text(e) == "1 勝 1 負"
    e.wins, e.streak = 2, 2
    assert arena_ranks.record_text(e) == "2 勝 1 負・連勝 2"
    e.draws = 1
    assert arena_ranks.record_text(e) == "2 勝 1 負 1 和・連勝 2"
