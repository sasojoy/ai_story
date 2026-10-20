"""FB-530：基準超過 100（裁決 5 分母只算中立之後才有）時，推一條線不該把偏移往回扣（計畫 6.2）。

偏移是「其他來源累積的量」，夾值只在顯示那一刻做；推過牆的那一截丟掉（往牆那一邊推、未夾的值已經在牆外時整個丟掉）。
輿圖重製第 1 批（新天下）：南陽是官軍的出生州、不算進任何一條線；這幾條把 QA 那一季的 v1 南陽那條線（三塊中立加淯水河畔）原樣擺回來
（conquest_kit.conquest_game_with），量的是同一條規則。"""
from __future__ import annotations

import pytest

from conquest_kit import conquest_game_with
from tianxia import conquest, rules

pytestmark = pytest.mark.slow  # 建 Game、載正式內容

V1_NANYANG = {  # v1 地圖的南陽那條線
    "nanyang_road": ("neutral", "nanyang"), "nanyang_wilds": ("neutral", "nanyang"), "lulin_zhai": ("neutral", "nanyang"),
    "yu_river": ("guan", "nanyang"),
}


def conquest_game(profile: str = "season21"):
    return conquest_game_with(V1_NANYANG, profile)


def _value(game, line):
    return rules.world_trend_value(game.state.world, game.content, line)


def _past_the_wall(game):
    """QA 的南陽：三塊中立加淯水河畔（官軍的陣營區塊，權重 2）都歸黃巾，基準 50＋35×5÷3＝108.33、偏移 −7、值 100。"""
    w, c = game.state.world, game.content
    rules.change_trend(game.state, c, "nanyang", 43 - _value(game, "nanyang"))  # QA 那一季開季那一刻張曼成取宛 +8：35 → 43
    for loc in ("nanyang_road", "nanyang_wilds", "lulin_zhai", "yu_river"):
        conquest.set_control(w, c, loc, "huang")
    assert conquest.base(w, c, "nanyang") == pytest.approx(50 + 35 * 5 / 3)
    assert w.conquest.offset["nanyang"] == pytest.approx(-7)
    assert _value(game, "nanyang") == 100
    return w, c


@pytest.mark.parametrize("delta", [1, 5])
def test_pushing_toward_the_wall_past_it_leaves_the_offset_alone(delta):
    game = conquest_game("season21")
    w, c = _past_the_wall(game)
    assert rules.change_trend(game.state, c, "nanyang", delta) == []  # 值不動、不寫
    assert w.conquest.offset["nanyang"] == pytest.approx(-7)
    conquest.set_control(w, c, "yu_river", "guan")  # 官軍收復淯水河畔：基準 85
    assert _value(game, "nanyang") == 78  # 85＋(−7)，跟沒推一樣（修前 77）


def test_pushing_back_from_past_the_wall_counts_once():
    game = conquest_game("season21")
    w, c = _past_the_wall(game)
    rules.change_trend(game.state, c, "nanyang", -1)
    assert w.conquest.offset["nanyang"] == pytest.approx(-8)  # 照推的量記（修前 −9.33）
    assert _value(game, "nanyang") == 100  # 未夾的 100.33，顯示照舊夾在 100
    conquest.set_control(w, c, "yu_river", "guan")
    assert _value(game, "nanyang") == 77  # 85＋(−8)（修前 76）


def test_pushing_back_far_enough_moves_the_value_and_stops_at_the_other_wall():
    game = conquest_game("season21")
    w, c = _past_the_wall(game)
    msgs = rules.change_trend(game.state, c, "nanyang", -11)
    assert _value(game, "nanyang") == 90 and msgs  # 101.33−11＝90.33
    rules.change_trend(game.state, c, "nanyang", -500)
    assert _value(game, "nanyang") == 0
    assert w.conquest.offset["nanyang"] == pytest.approx(-(50 + 35 * 5 / 3))  # 推過 0 那一截丟掉：未夾的剛好 0


def test_a_push_with_a_fractional_base_moves_the_offset_by_the_push():
    """基準有小數（南陽官道歸黃巾：61.67）時，推 1 偏移就走 1（修前照四捨五入過的值重錨，偏移多走 1.33）。"""
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    conquest.set_control(w, c, "nanyang_road", "huang")
    before = _value(game, "nanyang")
    offset = w.conquest.offset["nanyang"]
    rules.change_trend(game.state, c, "nanyang", 1)
    assert _value(game, "nanyang") == before + 1
    assert w.conquest.offset["nanyang"] == pytest.approx(offset + 1)
