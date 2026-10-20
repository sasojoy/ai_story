"""翻地與爭搶的純規則（輿圖簡化設計第四章；計畫 docs/superpowers/plans/2026-10-20-翻地與爭搶.md Task 1）：每一塊對每個攻方一條進度、推滿當場翻、
冷卻鎖住兩邊與加成暫停、每日回、集火、守把每一條都拉下、守城功、分紅、戰書門檻、軍令改讀、三方也成立。"""
from __future__ import annotations

import pytest

from conquest_kit import announce, conquest_game
from tianxia import calendar, conquest, territory

pytestmark = pytest.mark.slow  # 每一條都建一局（載正式內容）


def _game():
    game = conquest_game("season21")
    return game, game.state.world, game.content


def _attack(w, c, loc, side, name, amount):
    return conquest.push(w, c, loc, side, name, amount, "attack")


def test_push_fills_the_bar_and_flips_at_full_with_payouts():
    game, w, c = _game()
    assert conquest.push_problem(w, c, "guan", "hilltop_wilds", "attack") is None
    first = _attack(w, c, "hilltop_wilds", "guan", "甲", 60)
    assert first.moved == 60 and not first.flipped and conquest.bar(w, "hilltop_wilds", "guan") == 60
    assert conquest.holder(w, c, "hilltop_wilds") is None
    done = _attack(w, c, "hilltop_wilds", "guan", "乙", 55)  # 只推得動 40：滿了就翻
    assert done.moved == 40 and done.flipped
    assert conquest.holder(w, c, "hilltop_wilds") == "guan"
    assert conquest.bars(w, "hilltop_wilds") == {}
    assert any("荒丘落入" in r.text for r in w.rumors)  # territory 的「落入」天下大事
    assert any(r.text == "甲率先攻入荒丘。" for r in w.chronicle)
    pay = {p.name: p for p in w.conquest.payouts}
    assert (pay["甲"].silver, pay["甲"].exp, pay["甲"].fame, pay["甲"].top) == (120, 180, 12, True)  # 中立地全額 200／300／20，佔六成
    assert (pay["乙"].silver, pay["乙"].exp, pay["乙"].fame, pay["乙"].top) == (80, 120, 8, False)
    note = w.conquest.day_log[-1]
    assert (note.by, note.side, note.loc, note.reason) == ("flip", "guan", "hilltop_wilds", "甲")


def test_faction_block_pool_is_halved():
    game, w, c = _game()
    conquest.push(w, c, "runan_wilds", "guan", "甲", 100, "attack")  # 黃巾開季的領地
    assert conquest.holder(w, c, "runan_wilds") == "guan"
    (pay,) = w.conquest.payouts
    assert (pay.silver, pay.exp, pay.fame) == (100, 150, 10)


def test_cooling_locks_both_sides_and_pauses_the_perks():
    game, w, c = _game()
    _attack(w, c, "hilltop_wilds", "guan", "甲", 100)
    for side, how in (("huang", "attack"), ("guan", "hold")):
        assert conquest.push_problem(w, c, side, "hilltop_wilds", how) == "剛易手，60 分後才能再推"
    assert conquest.cooling(w, c, "hilltop_wilds")
    assert territory.price_factor(w, c, "guan", "hilltop_wilds") == 1.0  # 自家的便宜暫停
    assert territory.price_factor(w, c, "huang", "hilltop_wilds") == 1.0  # 敵方的加價也停
    assert not conquest.is_home(w, c, "guan", "hilltop_wilds") and not conquest.is_home(w, c, None, "hilltop_wilds")
    assert conquest.drop_cap(w, c, "hilltop_wilds") == 1  # 中立駐軍只掉一階
    w.time += 59 * 60
    assert conquest.cooling_minutes(w, c, "hilltop_wilds") == 1
    w.time += 61
    assert not conquest.cooling(w, c, "hilltop_wilds")
    assert conquest.push_problem(w, c, "huang", "hilltop_wilds", "attack") is None
    assert conquest.push_problem(w, c, "guan", "hilltop_wilds", "hold") == conquest.WHY_IDLE  # 沒人推，守了也拉不動
    assert territory.price_factor(w, c, "guan", "hilltop_wilds") == c.config.territory.own_price
    assert conquest.is_home(w, c, "guan", "hilltop_wilds") and conquest.drop_cap(w, c, "hilltop_wilds") is None


def test_hold_pulls_every_bar_down():
    game, w, c = _game()
    conquest.set_control(w, c, "hilltop_wilds", "guan")  # 管理者改的：沒有冷卻
    _attack(w, c, "hilltop_wilds", "huang", "丁", 30)
    _attack(w, c, "hilltop_wilds", "haoqiang", "戊", 20)  # 第三方也各推各的一條（翻地對 N 方成立）
    assert conquest.push_problem(w, c, "guan", "hilltop_wilds", "hold") is None
    pulled = conquest.push(w, c, "hilltop_wilds", "guan", "甲", 25, "hold")
    assert pulled.moved == 45 and conquest.bars(w, "hilltop_wilds") == {"huang": 5}
    assert not pulled.guarded  # 沒有哪一條到過五成：沒有守城功
    assert conquest.push_problem(w, c, "huang", "hilltop_wilds", "hold") == conquest.WHY_OUT  # 守只有佔著的那一方


def test_guard_merit_needs_the_alarm():
    game, w, c = _game()
    conquest.set_control(w, c, "hilltop_wilds", "guan")
    _attack(w, c, "hilltop_wilds", "huang", "丁", 55)  # 過了五成
    conquest.push(w, c, "hilltop_wilds", "guan", "甲", 30, "hold")
    done = conquest.push(w, c, "hilltop_wilds", "guan", "乙", 30, "hold")
    assert done.guarded and conquest.bars(w, "hilltop_wilds") == {}
    pay = {p.name: p for p in w.conquest.payouts if p.kind == "guard"}
    assert (pay["甲"].silver, pay["乙"].silver) == (55, 45)  # 總額 200 × 0.5，照拉回的 30：25 分
    assert any(r.text == "甲力保荒丘不失。" for r in w.chronicle)
    _attack(w, c, "hilltop_wilds", "huang", "丁", 30)  # 這一輪沒到五成
    again = conquest.push(w, c, "hilltop_wilds", "guan", "甲", 30, "hold")
    assert not again.guarded and len([p for p in w.conquest.payouts if p.kind == "guard"]) == 2


def test_decay_only_blocks_nobody_pushed_for_a_whole_day():
    game, w, c = _game()
    conquest.decay(w, c)  # 第一次只記下今天
    today = calendar.day_index(w.time, c, w)
    _attack(w, c, "hilltop_wilds", "guan", "甲", 30)
    _attack(w, c, "deep_mountain", "guan", "甲", 30)
    announce(game, "deep_mountain", "guan")  # 下了戰書：凍結，不回
    w.time = calendar.day_start(today + 2, c, w) + 60  # 跨進第二天：推過的那一天不回
    conquest.decay(w, c)
    assert conquest.bar(w, "hilltop_wilds", "guan") == 30
    w.time = calendar.day_start(today + 3, c, w) + 60  # 再跨一天：前一整天沒人推，回 10
    conquest.decay(w, c)
    assert conquest.bar(w, "hilltop_wilds", "guan") == 20
    assert conquest.bar(w, "deep_mountain", "guan") == 30
    w.time = calendar.day_start(today + 5, c, w) + 60  # 一次跨兩天：回兩次，歸零拿掉、這一輪的帳一起清
    conquest.decay(w, c)
    assert conquest.bar(w, "hilltop_wilds", "guan") == 0 and "guan" not in w.conquest.fights["hilltop_wilds"].bars


def test_focus_counts_other_pushers_of_the_same_side_within_the_hour():
    game, w, c = _game()
    for name in ("甲", "乙"):
        conquest.mark(w, c, "hilltop_wilds", name, "guan", "attack", 5)
    conquest.mark(w, c, "hilltop_wilds", "丁", "huang", "attack", 5)
    assert conquest.focus_bonus(w, c, "hilltop_wilds", "guan", "丙") == pytest.approx(0.2)
    assert conquest.focus_bonus(w, c, "hilltop_wilds", "guan", "甲") == pytest.approx(0.1)  # 自己不算
    assert conquest.focus_bonus(w, c, "hilltop_wilds", "huang", "戊") == pytest.approx(0.1)  # 別一邊不算
    for name in "子丑寅卯辰巳":
        conquest.mark(w, c, "hilltop_wilds", name, "guan", "attack", 5)
    assert conquest.focus_bonus(w, c, "hilltop_wilds", "guan", "丙") == pytest.approx(0.5)  # 最多五成
    w.time += 61 * 60
    assert conquest.focus_bonus(w, c, "hilltop_wilds", "guan", "丙") == 0


def test_clash_names_are_the_other_side_within_ten_minutes():
    game, w, c = _game()
    conquest.mark(w, c, "hilltop_wilds", "戊", "huang", "attack", 5)
    w.time += 11 * 60
    conquest.mark(w, c, "hilltop_wilds", "丁", "huang", "attack", 5)
    conquest.mark(w, c, "hilltop_wilds", "甲", "guan", "attack", 5)
    assert conquest.clash_names(w, c, "hilltop_wilds", "guan", "甲") == ["丁"]  # 戊推的是 11 分鐘前
    assert conquest.clash_names(w, c, "hilltop_wilds", "huang", "丁") == ["甲"]
    assert conquest.clashing(w, c, "hilltop_wilds")
    w.time += 11 * 60
    assert not conquest.clashing(w, c, "hilltop_wilds") and conquest.clash_names(w, c, "hilltop_wilds", "guan", "甲") == []
    names = [row["name"] for row in conquest.pushers(w, c, "hilltop_wilds")]
    assert sorted(names) == ["丁", "戊", "甲"]  # 「正在推這裡的人」照 presence_seconds（一天）


def test_a_third_side_can_fill_and_flip_too():
    game, w, c = _game()
    _attack(w, c, "hilltop_wilds", "guan", "甲", 90)
    done = _attack(w, c, "hilltop_wilds", "haoqiang", "戊", 100)
    assert done.flipped and conquest.holder(w, c, "hilltop_wilds") == "haoqiang"
    assert conquest.bars(w, "hilltop_wilds") == {}  # 每一條都清掉


def test_letter_problem():
    game, w, c = _game()
    key = 7
    assert conquest.letter_problem(w, c, "guan", "hilltop_wilds", key) == "進度要到 60 才能下戰書（此刻 0）"
    _attack(w, c, "hilltop_wilds", "guan", "甲", 60)
    assert conquest.letter_problem(w, c, "guan", "hilltop_wilds", key) is None
    w.conquest.letter_days["guan"] = key
    assert conquest.letter_problem(w, c, "guan", "hilltop_wilds", key).startswith("官軍今天已經下過戰書了")
    assert conquest.letter_problem(w, c, "guan", "hilltop_wilds", key + 1) is None
    _attack(w, c, "hilltop_wilds", "huang", "丁", 70)
    slot = announce(game, "hilltop_wilds", "huang")
    assert conquest.letter_problem(w, c, "guan", "hilltop_wilds", key + 1) is None  # 黃巾下的、還沒開集結：可以併進同一場
    assert conquest.letter_problem(w, c, "huang", "hilltop_wilds", key + 1) == "黃巾軍已經對這一塊下了戰書"
    slot.status = "open"
    assert conquest.letter_problem(w, c, "guan", "hilltop_wilds", key + 1) == conquest.LETTER_OPEN
    assert conquest.letter_problem(w, c, "huang", "runan_wilds", key + 1) == conquest.WHY_OWN


def test_targets_skip_blocks_without_foes():
    game, w, c = _game()
    assert "hilltop_wilds" in conquest.targets(w, c, "guan")
    c.scenario.territory.neutral_garrison["hilltop_wilds"] = []
    c.locations["hilltop_wilds"].enemies = []
    assert "hilltop_wilds" not in conquest.targets(w, c, "guan")
    assert conquest.push_problem(w, c, "guan", "hilltop_wilds", "attack") == conquest.WHY_NO_FOE


def test_orders_read_the_highest_block_per_line():
    game, w, c = _game()
    _attack(w, c, "hilltop_wilds", "guan", "甲", 30)
    _attack(w, c, "deep_mountain", "guan", "甲", 10)
    spots = conquest.focus_blocks(w, c, "guan", "attack")
    assert "hilltop_wilds" in spots and "deep_mountain" not in spots and "guan_camp" not in spots
    assert {"nanyang_road", "nanyang_wilds"} <= set(spots)  # 南陽那條線全是 0：每一塊推得動的都算
    assert conquest.focus_blocks(w, c, "guan", "defend") == []  # 沒人在推自家的地方
    conquest.set_control(w, c, "hilltop_wilds", "guan")
    _attack(w, c, "hilltop_wilds", "huang", "丁", 20)
    _attack(w, c, "runan_wilds", "guan", "甲", 40)  # 黃巾的地方被推：黃巾要守
    assert conquest.focus_blocks(w, c, "guan", "defend") == ["hilltop_wilds"]
    assert conquest.focus_blocks(w, c, "huang", "defend") == ["runan_wilds"]


def test_halve_and_siege_start_shift():
    game, w, c = _game()
    _attack(w, c, "hilltop_wilds", "guan", "甲", 80)
    assert conquest.progress_shift(w, c, "hilltop_wilds", ["guan"]) == -6  # 往官軍偏（戰局以官軍為正向：起點 56）
    assert conquest.progress_shift(w, c, "hilltop_wilds", ["guan", "huang"]) == 0
    conquest.halve(w, c, "hilltop_wilds", ["guan"])
    assert conquest.bar(w, "hilltop_wilds", "guan") == 40


def test_switch_off_nothing_moves():
    from conquest_kit import plain_game

    game = plain_game("season21")
    w, c = game.state.world, game.content
    assert conquest.push_problem(w, c, "guan", "hilltop_wilds", "attack") == conquest.WHY_OFF
    assert conquest.focus_blocks(w, c, "guan", "attack") == [] and not conquest.cooling(w, c, "hilltop_wilds")
    assert w.conquest is None
