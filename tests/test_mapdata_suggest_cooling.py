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
    assert _suggested(game)[0] == "yingshui"


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
