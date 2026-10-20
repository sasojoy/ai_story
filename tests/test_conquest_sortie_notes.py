"""領地爭奪第一批 QA 之後：行動列底下出陣那一行照實寫（FB-532、FB-533），敵方大本營與廣宗不給攻（計畫第八章裁決 18）。字待 joy 潤。"""
from __future__ import annotations

import pytest

from conquest_kit import conquest_game, go, join, plain_game

pytestmark = pytest.mark.slow  # 建 Game、載正式內容


def _note(game, loc_id):
    return game._sortie_line(game.content.locations[loc_id])  # 行動列底下出陣那一行（action_notes 的 act:train）


@pytest.mark.parametrize(("side", "base"), [("guan", "changshe"), ("huang", "huangjin_camp")])
def test_own_base_hold_line_reads_right(side, base):
    """FB-532：站在自家大本營守，那一行不再寫「推不動進度（這裡搶不下來）（量是攻的一半）」。"""
    game = go(join(conquest_game("season21"), side), base)
    note = _note(game, base)
    assert note == "這裡是自家地盤，不在爭奪之列：不用打，也沒有進度可推；拿自家隊伍 3 成的心得與經驗。今日還能出陣 5 次。"


def test_own_fixed_block_hold_line_reads_right():
    """廣宗（fixed）在黃巾手上：同自家大本營。"""
    game = go(join(conquest_game("season21"), "huang"), "guangzong")
    assert _note(game, "guangzong").startswith("這裡是自家地盤，不在爭奪之列：")


def test_own_capturable_block_hold_line_is_unchanged():
    game = go(join(conquest_game("season21"), "guan"), "yingchuan_wilds")
    assert _note(game, "yingchuan_wilds") == (
        "這裡是自家地盤：不用打，推這一塊的進度、記貢獻（量是攻的一半）；拿自家隊伍 3 成的心得與經驗。今日還能出陣 5 次。"
    )


def test_switch_off_hold_line_is_unchanged():
    """關著：自家大本營照舊寫推動戰局（a73c111e 上量的）。"""
    game = go(join(plain_game("season21"), "guan"), "changshe")
    assert _note(game, "changshe") == (
        "這裡是自家地盤：不用打，推動戰局、記貢獻（量是攻的一半）；拿自家隊伍 3 成的心得與經驗。今日還能出陣 5 次。"
    )
