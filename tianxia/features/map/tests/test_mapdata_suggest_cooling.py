"""輿圖第三版第 5 批（PM 派工的小單，QA 第 4 批複驗的「順帶」）：卡底下「今天去哪裡出陣」第一條推薦的是剛易手、還在冷卻的地——
QA：官軍站潁川郡、潁水河畔剛被黃巾推滿，第一條「潁水河畔 出陣・攻 有把握」，那一塊的卡上卻寫「剛易手，51 分後才能再推」。
冷卻期兩邊都推不動（設計 4.1），推薦要跳過；冷卻過了照舊列。領地爭奪關著的季沒有冷卻，不受影響。"""
from __future__ import annotations

import pytest

from conquest_kit import conquest_game, go, join
from tianxia import conquest

pytestmark = pytest.mark.slow  # 建 Game、載正式內容


def _suggested(game) -> list[str]:
    return [g["id"] for g in game.map_state()["suggest"]]


def _listed(game, loc: str) -> bool:
    """3d（FB-858）之後：潁水河畔剛被黃巾拿下，官軍在那裡出陣打的是黃巾的巡邏（難分勝負、必敗），不再是站在那裡的河灘潑皮（有把握）——
    它是必敗，排在三處打得過的自家地方後面（原本被錯當成有把握才排第一）；這幾條鎖的是冷卻、戰書凍結的那一道篩，所以改問列不列，不問排第幾。"""
    return loc in _suggested(game)


def test_a_cooling_block_is_not_suggested_until_it_cools_down():
    game = go(join(conquest_game("season21"), "guan"), "yingchuan")
    w, c = game.state.world, game.content
    conquest.flip(w, c, "yingshui", "huang")  # 黃巾剛推滿潁水河畔
    assert conquest.cooling(w, c, "yingshui")
    st = game.map_state()
    assert st["places"]["yingshui"]["sortie"] == "attack" and st["places"]["yingshui"]["cool"]
    assert "yingshui" not in _suggested(game)  # 修前排第一（出陣・攻 有把握）
    w.conquest.fights["yingshui"].flipped_at = w.time - 10**8  # 冷卻過了
    assert not conquest.cooling(w, c, "yingshui")
    assert _listed(game, "yingshui")


def test_your_own_cooling_block_is_not_suggested_to_hold_either():
    """自家剛拿下、還在冷卻的那一塊：守也推不動（冷卻期兩邊都推不動），不列。"""
    game = go(join(conquest_game("season21"), "guan"), "hilltop_wilds")  # 站在那裡：路程 0，守也排得上
    w, c = game.state.world, game.content
    conquest.flip(w, c, "hilltop_wilds", "guan")
    st = game.map_state()
    assert st["places"]["hilltop_wilds"]["sortie"] == "hold" and st["places"]["hilltop_wilds"]["cool"]
    assert "hilltop_wilds" not in _suggested(game)
    w.conquest.fights["hilltop_wilds"].flipped_at = w.time - 10**8  # 冷卻過了：照舊列
    assert "hilltop_wilds" in _suggested(game)


def test_fb692_a_block_frozen_by_a_letter_is_not_suggested_until_the_siege_is_over():
    """FB-692：被戰書凍結的塊（設計 4.4：下了戰書到那一場攻城打完，兩邊都推不動）跟冷卻一樣不列；那一場打完（守住、作罷）照舊列。"""
    from conquest_kit import announce

    game = go(join(conquest_game("season21"), "guan"), "yingchuan")
    w, c = game.state.world, game.content
    conquest.flip(w, c, "yingshui", "huang")
    w.conquest.fights["yingshui"].flipped_at = w.time - 10**8  # 冷卻過了：照舊列（同上一條）
    assert _listed(game, "yingshui")
    slot = announce(game, "yingshui", "guan")  # 官軍對潁水河畔下了戰書
    assert conquest.frozen(w, "yingshui") is slot
    assert "yingshui" not in _suggested(game)  # 修前照樣排第一
    slot.status = "open"  # 集結・交戰中也一樣
    assert "yingshui" not in _suggested(game)
    slot.status = "done"  # 打完（守住了）：不凍結了
    assert conquest.frozen(w, "yingshui") is None and _listed(game, "yingshui")
