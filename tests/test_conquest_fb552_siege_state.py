"""FB-552（PM 2026-10-20，輿圖第 1 批 QA 開的，領地爭奪第二批就有）：攻城集結的那半小時，站在被公告的那一塊，出陣那一行不能寫
「這一塊今天沒有公告攻城」——這一塊明明公告了、正在集結。照實寫這一塊今天的攻城在哪一步（conquest.siege_state）：還沒開打（進度推得動）、
集結中（去加入攻城）、開打中、打完了、作罷了；今天真的沒有公告才寫「沒有公告攻城」。進度推不推得動仍只看 conquest.progress_open
（規則是對的，字不對）；列與記同一個判斷：那一行寫「推不動」，出陣就真的推不動（sortie_progress 是 0）。關著的季一個字都不變。"""
from __future__ import annotations

import pytest

from conquest_kit import announce, conquest_game, go, join, plain_game
from tianxia import conquest, howto

pytestmark = pytest.mark.slow  # 建 Game、載正式內容

STATES = (("open", "muster", howto.SORTIE_SIEGE["muster"]), ("open", "fight", howto.SORTIE_SIEGE["fight"]),
          ("done", "done", howto.SORTIE_SIEGE["done"]), ("void", "void", howto.SORTIE_SIEGE["void"]))


def _note(game, loc_id):
    return game._sortie_line(game.content.locations[loc_id])  # 行動列底下出陣那一行（action_notes 的 act:train）


def _put(game, slot, status, phase):
    """把這一場放在某一步：open 的集結中是世界時間還沒到開打、開打中是過了開打的時刻。"""
    slot.status = status
    w = game.state.world
    w.time = slot.at - 60 if phase == "muster" else slot.at + 60 if phase == "fight" else w.time


def test_state_of_a_block_follows_the_slot():
    game = conquest_game("season21")
    w = game.state.world
    assert conquest.siege_state(w, "nanyang_road") is None  # 今天沒排過
    slot = announce(game, "nanyang_road", "huang")
    assert conquest.siege_state(w, "nanyang_road") == "planned"
    slot.status = "waiting"
    assert conquest.siege_state(w, "nanyang_road") == "planned"  # 到了開集結的時候、還沒開：進度還推得動
    slot.status = "open"
    assert conquest.siege_state(w, "nanyang_road") == "muster"
    w.time = slot.at + 1
    assert conquest.siege_state(w, "nanyang_road") == "fight"
    slot.status = "done"
    assert conquest.siege_state(w, "nanyang_road") == "done"
    slot.status = "void"
    assert conquest.siege_state(w, "nanyang_road") == "void"
    assert conquest.siege_state(w, "hilltop_wilds") is None  # 別的塊不受影響


def test_attack_line_says_where_the_siege_is_not_that_nothing_was_announced():
    game = go(join(conquest_game("season21"), "huang"), "nanyang_road")
    assert howto.SORTIE_NOT_TODAY in _note(game, "nanyang_road")  # 真的沒公告：照舊
    slot = announce(game, "nanyang_road", "huang")
    assert howto.SORTIE_PROGRESS in _note(game, "nanyang_road")  # 還沒開打：推得動
    for status, phase, text in STATES:
        _put(game, slot, status, phase)
        note = _note(game, "nanyang_road")
        assert text in note, (status, phase)
        assert howto.SORTIE_NOT_TODAY not in note and "沒有公告攻城" not in note  # 修前集結中、開打中、打完、作罷都寫「這一塊今天沒有公告攻城」
        assert game.sortie_progress("nanyang_road") == 0.0  # 列與記：寫推不動就真的推不動


def test_own_block_under_siege_says_the_same_in_the_hold_line():
    """自家的區塊被公告要攻（守）：集結中也不寫「今天沒有公告攻城」；那一句不再接「有公告時守推的量…」（已經公告過了，不是沒公告）。"""
    game = go(join(conquest_game("season21"), "guan"), "yingchuan_wilds")
    assert howto.SORTIE_NOT_TODAY_HOLD.format(half="一半") in _note(game, "yingchuan_wilds")  # 真的沒公告：照舊
    slot = announce(game, "yingchuan_wilds", "huang")
    assert howto.SORTIE_PROGRESS in _note(game, "yingchuan_wilds")
    for status, phase, text in STATES:
        _put(game, slot, status, phase)
        note = _note(game, "yingchuan_wilds")
        assert text in note and note.startswith("這裡是自家地盤：不用打，") and "拿自家隊伍" in note, (status, phase)
        assert "沒有公告攻城" not in note and "有公告時" not in note
        assert game.sortie_progress("yingchuan_wilds") == 0.0


def test_another_block_is_not_dragged_along():
    """站在沒被公告的另一塊，不因為別處有一場在集結而改字。"""
    game = go(join(conquest_game("season21"), "huang"), "hilltop_wilds")
    slot = announce(game, "nanyang_road", "huang")
    _put(game, slot, "open", "muster")
    assert howto.SORTIE_NOT_TODAY in _note(game, "hilltop_wilds")


def test_the_base_and_unannounced_neutral_keep_their_lines():
    """大本營（搶不下來）與沒有排過的中立地的字不動。"""
    game = go(join(conquest_game("season21"), "guan"), "changshe")
    assert "沒有進度可推" in _note(game, "changshe")
    go(game, "runan_wilds")  # 區塊表 v3 之前用嵩山深處（現在是官軍的）
    assert howto.SORTIE_NOT_TODAY in _note(game, "runan_wilds")


@pytest.mark.parametrize("profile", ["weekend", None, "season21"])  # 一個測試只開一季
def test_switch_off_the_line_never_mentions_a_siege(profile):
    """領地爭奪關著：行動列這一行沒有任何攻城的字（舊規則推線）；siege_state 關著也沒東西可讀。"""
    game = go(join(plain_game(profile), "huang"), "runan_wilds")
    assert game.state.world.conquest is None
    for text in howto.SORTIE_SIEGE.values():
        assert text not in _note(game, "runan_wilds")
    assert conquest.siege_state(game.state.world, "runan_wilds") is None
