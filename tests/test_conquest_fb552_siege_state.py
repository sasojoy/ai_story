"""FB-552（PM 2026-10-20，輿圖第 1 批 QA 開的，領地爭奪第二批就有）：攻城集結的那半小時，站在那一塊，出陣那一行不能寫錯攻城在哪一步。

第二批（投票、22:00 公告）時的寫法是「只有今天公告、還沒開打的推得動，其餘寫今天沒有公告攻城」，這一支原本鎖的是那一版的字。
翻地與爭搶（dev/flip-1，PM 2026-10-20 第 1、2 條）之後投票與公告拿掉了：沒有排攻城的塊隨時推得動；第 4 階下了戰書，那一塊凍結到那一場
打完或作罷（conquest.frozen）。所以照翻地改字（收尾，2026-10-21）：凍結的那一段，推不動的原因照那一場在哪一步寫（conquest.FROZEN_WHY，
push_problem 照 _step）——已下戰書（還沒開集結）、集結中（去加入攻城）、開打中；打完、作罷就解凍，照常推得動。列與記同一個判斷：那一行寫
推不動，出陣就真的推不動（sortie_progress 是 0）。自家的守那一句也一樣照實寫，不接「有人來攻時守拉的量…」。關著的季一個字都不變。"""
from __future__ import annotations

import pytest

from conquest_kit import announce, conquest_game, go, join, plain_game, press
from tianxia import conquest, howto

pytestmark = pytest.mark.slow  # 建 Game、載正式內容

FROZEN = (("planned", "planned", conquest.WHY_FROZEN), ("open", "muster", conquest.WHY_MUSTER),
          ("open", "fight", conquest.WHY_FIGHTING))


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
    assert conquest.siege_state(w, "nanyang_road") is None  # 沒排過
    slot = announce(game, "nanyang_road", "huang")
    assert conquest.siege_state(w, "nanyang_road") == "planned"
    slot.status = "waiting"
    assert conquest.siege_state(w, "nanyang_road") == "planned"  # 到了開集結的時候、還沒開
    slot.status = "open"
    assert conquest.siege_state(w, "nanyang_road") == "muster"
    w.time = slot.at + 1
    assert conquest.siege_state(w, "nanyang_road") == "fight"
    slot.status = "done"
    assert conquest.siege_state(w, "nanyang_road") == "done"
    slot.status = "void"
    assert conquest.siege_state(w, "nanyang_road") == "void"
    assert conquest.siege_state(w, "hilltop_wilds") is None  # 別的塊不受影響


def test_attack_line_says_where_the_siege_is():
    game = go(join(conquest_game("season21"), "huang"), "nanyang_road")
    assert howto.SORTIE_PROGRESS in _note(game, "nanyang_road")  # 沒排攻城：隨時推得動
    slot = announce(game, "nanyang_road", "huang")  # 戰書排了一場：凍結
    for status, phase, why in FROZEN:
        _put(game, slot, status, phase)
        note = _note(game, "nanyang_road")
        assert howto.SORTIE_BLOCKED.format(why=why) in note, (status, phase)
        assert game.sortie_progress("nanyang_road") == 0.0  # 列與記：寫推不動就真的推不動
    for status in ("done", "void"):  # 打完（這裡沒易手：輸了砍半另算）、作罷：解凍
        _put(game, slot, status, "")
        assert howto.SORTIE_PROGRESS in _note(game, "nanyang_road"), status
        assert game.sortie_progress("nanyang_road") > 0


def test_own_block_under_siege_says_the_same_in_the_hold_line():
    """自家的區塊被下了戰書（守）：凍結的那一段照實寫在哪一步，不接「有人來攻時守拉的量…」（攻城已經排了）；打完照常守得動。"""
    game = go(join(conquest_game("season21"), "guan"), "yingchuan_wilds")
    assert howto.SORTIE_BLOCKED_HOLD.format(why=conquest.WHY_IDLE, half="一半") in _note(game, "yingchuan_wilds")  # 沒人推：照舊
    press(game, "yingchuan_wilds", "huang")
    assert howto.SORTIE_HOLD_PROGRESS in _note(game, "yingchuan_wilds")  # 黃巾在推：守得動
    slot = announce(game, "yingchuan_wilds", "huang")
    for status, phase, why in FROZEN:
        _put(game, slot, status, phase)
        note = _note(game, "yingchuan_wilds")
        assert note.startswith("這裡是自家地盤：不用打，") and "拿自家隊伍" in note, (status, phase)
        assert howto.SORTIE_BLOCKED.format(why=why) in note and "有人來攻時" not in note, (status, phase)
        assert game.sortie_progress("yingchuan_wilds") == 0.0
    _put(game, slot, "done", "")
    assert howto.SORTIE_HOLD_PROGRESS in _note(game, "yingchuan_wilds")


def test_another_block_is_not_dragged_along():
    """站在沒排攻城的另一塊，不因為別處有一場在集結而改字。"""
    game = go(join(conquest_game("season21"), "huang"), "hilltop_wilds")
    slot = announce(game, "nanyang_road", "huang")
    _put(game, slot, "open", "muster")
    note = _note(game, "hilltop_wilds")
    assert not any(why in note for why in conquest.FROZEN_WHY.values())


def test_the_base_keeps_its_line():
    """大本營（搶不下來）的字不動。"""
    game = go(join(conquest_game("season21"), "guan"), "changshe")
    assert "沒有進度可推" in _note(game, "changshe")


@pytest.mark.parametrize("profile", ["weekend", None, "season21"])  # 一個測試只開一季
def test_switch_off_the_line_never_mentions_a_siege(profile):
    """領地爭奪關著：行動列這一行沒有任何攻城的字（舊規則推線）；siege_state 關著也沒東西可讀。"""
    game = go(join(plain_game(profile), "huang"), "runan_wilds")
    assert game.state.world.conquest is None
    for text in conquest.FROZEN_WHY.values():
        assert text not in _note(game, "runan_wilds")
    assert conquest.siege_state(game.state.world, "runan_wilds") is None
