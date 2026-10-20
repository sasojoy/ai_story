"""領地爭奪第一批 Task 3：控制方照佔領、大勢值＝佔領的基準＋偏移（計畫三、Task 3；設計 4.7；裁決 5：分母只算中立、偏移從劇本起點開始）。"""
from __future__ import annotations

import pytest

from conquest_kit import conquest_game, plain_game
from tianxia import conquest, rules, territory

pytestmark = pytest.mark.slow  # 建 Game、載正式內容

LINES = ("yingru", "nanyang", "jizhou")


def _value(game, line):
    return rules.world_trend_value(game.state.world, game.content, line)


def _owner(game, loc):
    return territory.controller(game.state.world, game.content, loc)


def test_opening_base_is_fifty_and_the_offset_keeps_the_scenario_start():
    plain = plain_game("season21")
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    assert {line: conquest.base(w, c, line) for line in LINES} == {line: 50.0 for line in LINES}
    assert {line: _value(game, line) for line in LINES} == {line: _value(plain, line) for line in LINES}  # 40／35／55 照舊
    assert w.conquest.offset["nanyang"] == _value(game, "nanyang") - 50


def test_opening_control_follows_the_block_kinds():
    game = conquest_game("season21")
    assert _owner(game, "changshe") == "guan" and _owner(game, "yingchuan") == "guan" and _owner(game, "yu_river") == "guan"
    assert _owner(game, "runan") == "huang" and _owner(game, "zhuo_county") == "huang" and _owner(game, "guangzong") == "huang"
    assert _owner(game, "nanyang_wilds") is None and _owner(game, "guan_camp") is None  # 中立地沒人佔
    assert _owner(game, "haozu_fort") is None and _owner(game, "jade_cave") is None  # 不是區塊
    game.advance(3600)
    assert not [r for r in game.state.world.rumors if r.text.endswith("之手。")]  # 第一次算不發天下大事、之後不拔河


def test_capture_moves_the_base_and_keeps_the_offset():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    rules.change_trend(game.state, c, "nanyang", 4)  # 其他來源：偏移 +4
    pushed = _value(game, "nanyang")
    conquest.set_control(w, c, "nanyang_wilds", "huang")
    assert _owner(game, "nanyang_wilds") == "huang"
    assert conquest.base(w, c, "nanyang") == pytest.approx(50 + 35 / 3)
    assert _value(game, "nanyang") == round(pushed + 35 / 3)
    assert any("南陽郊野落入" in r.text for r in w.rumors)
    assert any("南陽郊野落入" in r.text for r in w.chronicle)


def test_pushes_still_move_the_line_after_a_capture():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    conquest.set_control(w, c, "nanyang_wilds", "huang")
    before = _value(game, "nanyang")
    msgs = rules.change_trend(game.state, c, "nanyang", -3)
    assert _value(game, "nanyang") == before - 3 and msgs  # 其他來源照舊推（設計 3.8）


def test_push_into_the_wall_is_lost_like_before():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    rules.change_trend(game.state, c, "nanyang", 100)
    assert _value(game, "nanyang") == 100
    assert rules.change_trend(game.state, c, "nanyang", 5) == []  # 推進牆：不動、不寫
    conquest.set_control(w, c, "nanyang_road", "guan")  # 官軍拿下一塊中立：基準往下，值＝新基準＋重錨後的偏移（50）
    assert _value(game, "nanyang") == round(50 - 35 / 3 + 50)


def test_a_direct_write_is_reanchored():
    """決戰收場、管理者這類直接寫 world.trends 的：下一次重算照上一次的基準重錨偏移，易手只動基準。"""
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    w.trends["jizhou"] = _value(game, "jizhou") + 10
    territory.update(w, c)
    moved = _value(game, "jizhou")
    conquest.set_control(w, c, "xiaquyang", "huang")
    assert _value(game, "jizhou") == round(moved + 35 / 4)


def test_capturing_an_enemy_faction_block_weighs_double():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    before = _value(game, "yingru")
    conquest.set_control(w, c, "runan_wilds", "guan")  # 黃巾的陣營區塊（權重 2）被官軍拿下
    assert conquest.base(w, c, "yingru") == pytest.approx(50 - 35 * 2 / 3)
    assert _value(game, "yingru") == round(before - 35 * 2 / 3)
    conquest.set_control(w, c, "runan_wilds", "huang")  # 拿回自己的：不算佔得，回到 50
    assert conquest.base(w, c, "yingru") == 50
    assert any("收復汝南荒野" in r.text for r in w.rumors)


def test_weigh_by_neutral_full_ring_reaches_the_share():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    for loc in ("nanyang_road", "nanyang_wilds", "lulin_zhai"):
        conquest.set_control(w, c, loc, "huang")
    assert conquest.base(w, c, "nanyang") == pytest.approx(85)
    c.config.conquest.weigh_by = "total"  # 設計 4.7 原文：分母是那條線所有可奪區塊的權重和（中立 3、陣營 2 塊 ×2）
    assert conquest.base(w, c, "nanyang") == pytest.approx(50 + 35 * 3 / 7)


def test_timetable_assign_sticks_and_reweighs():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    before = _value(game, "jizhou")
    territory.assign(w, c, {"guangzong": "guan"})
    assert _owner(game, "guangzong") == "guan"
    assert _value(game, "jizhou") == before  # 廣宗是 fixed：不算權重
    game.advance(3600)
    w = game.state.world  # 推進之後讀回來的那一份
    assert _owner(game, "guangzong") == "guan"  # 規則不會把它翻回去
    territory.assign(w, c, {"xiaquyang": "guan"})  # 時刻表指定一塊中立：指定了就是指定了
    assert _owner(game, "xiaquyang") == "guan" and conquest.base(w, c, "jizhou") == pytest.approx(50 - 35 / 4)


def test_switch_off_change_trend_is_unchanged():
    game = plain_game("weekend")
    before = _value(game, "yingru")
    rules.change_trend(game.state, game.content, "yingru", 3)
    assert _value(game, "yingru") == before + 3
    assert game.state.world.conquest is None


def test_admin_sets_a_block():
    game = conquest_game("season21", name="Rayal")
    msgs = game.admin_conquest_set("nanyang_wilds", "huang")
    assert _owner(game, "nanyang_wilds") == "huang" and msgs
    game.admin_conquest_set("nanyang_wilds", None)
    assert _owner(game, "nanyang_wilds") is None  # 放回中立
    before = _owner(game, "changshe")
    game.admin_conquest_set("changshe", "huang")  # 大本營不收
    assert _owner(game, "changshe") == before
    game.admin_conquest_set("yu_river", "haoqiang")  # 只收兩軍
    assert _owner(game, "yu_river") == "guan"


def test_admin_set_refused_for_players():
    game = conquest_game("season21")
    msgs = game.admin_conquest_set("nanyang_wilds", "huang")
    assert _owner(game, "nanyang_wilds") is None and "管理者" in "".join(msgs)
