"""FB-103（QA 7cc1fd7，2026-10-08）：只有一位人物的地點，行動列交友那一格放「求見某某」，底下那一行（Game.action_notes）要跟格子說的是同一回事。

以前談滿的情形已經對了（day-scale 審查 I1）；閉門不見（挑戰本人打贏之後）時格子寫「求見／閉門不見」、那一行卻寫「和董卓談話，聊得投機情誼會漲」；
名望不夠時格子是「求見董卓」（選單上寫「名望還差 N」），那一行寫「名望不夠，董卓會打發你」。現在那一行照選項括號裡的話寫：
閉門不見寫整句「剛吃了敗仗，閉門不見」，名望不夠寫「名望還差 N」與會被打發，談滿照舊，見得到照舊。

用真實內容（週末設定）：官軍站在黃巾別部營寨，那裡只站著波才。句子待 joy 潤：這裡比的是選項括號裡的話有沒有出現在那一行，不鎖死字句。"""
from __future__ import annotations

import random
import re

import pytest

from tianxia import howto, rules
from tianxia.engine import SNUB_NOTE, Game

CALL = "call:bocai"


@pytest.fixture
def guan(on, world):
    game = Game.new(on, "官甲", rng=random.Random(0), world=world)
    game.client = None
    p = game.state.player
    p.faction, p.location = "guan", "huangjin_camp"
    p.tutorial_step = len(on.tutorial.steps)
    game.now = 1000.0
    return game


def _cell_and_note(game):
    option = next(o for o in game.options() if o.id == CALL)
    return option, game.action_notes([o.id for o in game.options()])[CALL]


def _detail(label):
    return re.fullmatch(r"求見.+?（(.*)）", label).group(1)


def test_a_snubbed_audience_says_the_door_is_shut(guan):
    guan.state.player.stats["fame"] = 100
    guan.state.player.snubbed_until["bocai"] = guan.now + 3600
    option, note = _cell_and_note(guan)
    assert not option.enabled and _detail(option.label) == SNUB_NOTE
    assert note == SNUB_NOTE and "談話" not in note  # 跟格子同一句（格子只放得下最後一小句「閉門不見」）


def test_a_fame_short_audience_names_the_gap_like_the_menu(guan):
    guan.state.player.stats["fame"] = 0
    option, note = _cell_and_note(guan)
    gap = _detail(option.label)
    assert option.enabled and gap.startswith("名望還差 ")
    assert note.startswith(gap) and "打發" in note and "不花體力" in note and "談話" not in note


def test_the_talked_out_and_the_open_audience_keep_their_lines(guan, on):
    guan.state.player.stats["fame"] = 100
    option, note = _cell_and_note(guan)
    assert option.enabled and note == howto.call_line("波才", True)
    guan.state.player.talks_today["bocai"] = [rules.game_day(on, guan.state.world), on.config.talk_turns_per_day]
    option, note = _cell_and_note(guan)
    assert not option.enabled and note == _detail(option.label) == guan._talked_out_note()  # noqa: SLF001


@pytest.mark.parametrize("fame, snubbed, talked", [(100, True, False), (0, False, False), (100, False, True), (0, True, False)])
def test_whenever_the_cell_gives_a_reason_the_line_repeats_it(guan, on, fame, snubbed, talked):
    """格子（選項）括號裡寫了原因（不是體力），那一行就從那一句開頭：兩邊說的永遠是同一件事。"""
    p = guan.state.player
    p.stats["fame"] = fame
    if snubbed:
        p.snubbed_until["bocai"] = guan.now + 3600
    if talked:
        p.talks_today["bocai"] = [rules.game_day(on, guan.state.world), on.config.talk_turns_per_day]
    option, note = _cell_and_note(guan)
    reason = _detail(option.label)
    assert not reason.startswith("體力") and note.startswith(reason)
