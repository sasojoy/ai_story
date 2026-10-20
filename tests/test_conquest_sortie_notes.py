"""領地爭奪第一批 QA 之後：行動列底下出陣那一行照實寫（FB-532、FB-533），敵方大本營與廣宗不給攻（計畫第八章裁決 18）。字待 joy 潤。

翻地與爭搶（輿圖簡化設計第四章）之後碰得到的每一塊都推得動（不再只推今天公告的目標），推不動照 conquest.push_problem 寫原因：
「今天沒有公告」那幾句換成原因（沒人在推、不相連）；裁決 21 的一個括號照留。"""
from __future__ import annotations

import pytest

from conquest_kit import conquest_game, go, join, plain_game
from tianxia import conquest, howto

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
    conquest.push(game.state.world, game.content, "yingchuan_wilds", "huang", "某", 20, "attack")  # 黃巾在推：官軍守拉得回來
    assert _note(game, "yingchuan_wilds") == (
        "這裡是自家地盤：不用打，把對面在這裡的進度拉回來、記貢獻（量是攻的一半）；拿自家隊伍 3 成的心得與經驗。今日還能出陣 5 次。"
    )


@pytest.mark.parametrize("loc", ["hilltop_wilds", "runan_wilds"])
def test_own_idle_block_hold_line_has_one_parenthesis(loc):
    """計畫第八節裁決 21：自家推不動的區塊守（翻地與爭搶之後是「沒人在推」），推不動的原因與「量是攻的一半」合成一個括號。
    荒丘是被管理者定給黃巾的中立地，汝南荒野是黃巾開季的陣營區塊。"""
    game = go(join(conquest_game("season21"), "huang"), loc)
    conquest.set_control(game.state.world, game.content, "hilltop_wilds", "huang")
    note = _note(game, loc)
    assert "）（" not in note and note.count("（") == 1  # 修前兩個括號
    assert note == (
        "這裡是自家地盤：不用打，推不動進度（沒有人在推這裡，守了也拉不動；有人來攻時守拉的量是攻的一半）；拿自家隊伍 3 成的心得與經驗。今日還能出陣 5 次。"
    )


def test_others_block_out_of_reach_line_says_why():
    """別人的區塊、跟自家的領地不相連：一個括號寫原因。"""
    game = go(join(conquest_game("season21"), "guan"), "runan")
    assert _note(game, "runan").startswith("這裡歸別人：打一場，打贏推不動進度（這裡跟自家的領地不相連）；只拿對手 3 成的心得與經驗，")


def test_switch_off_hold_line_is_unchanged():
    """關著：自家大本營照舊寫推動戰局（a73c111e 上量的）。"""
    game = go(join(plain_game("season21"), "guan"), "changshe")
    assert _note(game, "changshe") == (
        "這裡是自家地盤：不用打，推動戰局、記貢獻（量是攻的一半）；拿自家隊伍 3 成的心得與經驗。今日還能出陣 5 次。"
    )


def test_unheld_neutral_block_does_not_say_someone_else_holds_it():
    """FB-533（1）：還沒人佔的中立地，出陣那一行不寫「這裡歸別人」。"""
    game = go(join(conquest_game("season21"), "guan"), "guan_camp")
    note = _note(game, "guan_camp")
    assert note.startswith("這裡還沒有人佔：打一場，打贏推這一塊的進度、記貢獻；只拿對手 3 成的心得與經驗，")
    assert "這裡歸別人" not in note


def test_neutral_block_held_by_the_enemy_still_says_so():
    game = go(join(conquest_game("season21"), "guan"), "hilltop_wilds")
    conquest.set_control(game.state.world, game.content, "hilltop_wilds", "huang")
    assert _note(game, "hilltop_wilds").startswith("這裡歸別人：打一場，打贏推這一塊的進度、記貢獻；")


def test_howto_sortie_line_drops_the_resistance_half_sentence():
    """FB-533（2）：領地爭奪版的出陣說明不寫「越往對方老巢推越難推」（推進度沒有盡頭阻力），還沒人佔的中立地也是打。"""
    game = conquest_game("season21")
    text = " ".join(howto.sortie_lines(game.content, True, game.state.world))
    assert "越往對方老巢推越難推" not in text and "還沒人佔" in text


def test_switch_off_sortie_howto_and_line_unchanged():
    """關著：說明與那一行一個字都不變（a73c111e 上量的）。"""
    plain = plain_game("season21")
    assert howto.sortie_lines(plain.content, True, plain.state.world) == [
        "- **出陣**（體力 6，每天 5 次，台灣時間 00:00 換日）：投靠了陣營才有，只在戰線上的地點。這裡歸別人就打一場，打贏推動戰局、記貢獻；"
        "歸自家就守，不用打；地方豪強照依附的那一邊攻守。守推的量是攻的一半。只拿對手 3 成的心得與經驗，攻打贏銀兩也是 3 成，不掉東西。"
        "越往對方老巢推越難推。"
    ]
    game = go(join(plain_game("season21"), "huang"), "guan_camp")
    assert _note(game, "guan_camp").startswith("這裡歸別人：打一場，打贏推動戰局、記貢獻；")
