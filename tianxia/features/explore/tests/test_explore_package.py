"""探索包（走一趟、探索一顆）登記之後的煙霧與接縫：包的內容驗證（原本的 content.check_explore_one、check_outing_lines）照樣擋得下
壞的內容、核心照 FEATURES 叫得到它；核心寫的那一份「旅人」跟包裡的一樣（核心不 import 包，抄了一份字）。"""
from __future__ import annotations

from unittest import mock

import pytest
from jianfa_kit import jianfa_game, ready
from test_outing import _game, _walked, _with_ink

from conftest import real_content
from tianxia import content as content_mod
from tianxia import speech
from tianxia.core import features as features_core
from tianxia.core.option import IDLE_MARK
from tianxia.features.explore import explore_rules, outing_rules


def _problems(c) -> list[str]:
    found: list[str] = []
    features_core.check_content(c, lambda ok, message: None if ok else found.append(message))
    return found


@pytest.mark.smoke
def test_the_package_checks_the_explore_tables_and_the_outing_lines():
    c = real_content("season21")
    assert _problems(c) == []
    c.locations["yingshui"].tags = ["酒肆"]  # 店面標籤不歸表
    c.outing_lines = {**c.outing_lines, "nope": {"x": ["y"]}}
    found = _problems(c)
    assert any("yingshui" in f for f in found) and any("不認得的組 nope" in f for f in found)


def test_the_core_and_the_package_spell_the_traveler_tag_the_same():
    assert content_mod.TRAVELER_TAG == explore_rules.TRAVELER


@pytest.mark.smoke
def test_the_menu_explores_once_and_the_outing_walks_one_segment():
    """審查修正（回歸鏡頭）：上面那一條煙霧只驗內容；核心（選單、IDLE_MARK、services、engine 的委派）改壞了「探索一顆、走一趟按得下去」，
    只改核心時 test_for 挑不到這一包的測試，要等這一條煙霧才紅。week7 正式內容：按一次探索（選單那一顆）、再走一趟一段。"""
    game = ready(jianfa_game("week7"), side="guan", loc="yingshui")
    p, step = game.state.player, game.content.config.jianfa.explore_stamina
    before = p.stamina
    with mock.patch.object(explore_rules, "draw", return_value=explore_rules.MATERIAL):
        assert next(o for o in game.options(odds=False) if o.id == IDLE_MARK).enabled
        game.choose(IDLE_MARK)
        assert (p.explore_seq, p.stamina) == (1, before - step)
        assert game.outing_go(1) == []
    trip = p.outing
    assert (trip.total, trip.done, trip.end) == (1, 1, outing_rules.DONE) and p.stamina == before - 2 * step


def test_the_wall_refuses_the_words_the_tavern_wall_refuses_and_keeps_the_ink():
    """審查修正（回歸鏡頭）：走一趟留言除了字表（髒話）還擋三個字（假人、機器人、外掛；同酒肆題壁，牆上不寫這幾個字，也是不讓畫面透露
    誰是假人的守門）。以前沒有任何測試守這一行（變異成 `if False:` 全綠）：把字表清空，讓擋下的只可能是這一道；擋下的不用墨、不刻字。"""
    game = _game()
    _walked(game)
    _with_ink(game)
    game.content.banned_words = []
    for word in ("假人", "機器人", "外掛"):
        text = f"此處有{word}"
        assert speech.problem(text, game.content, speech.MOTTO, game.content.config.jianfa.outing_say_max) is None  # 字表碰不到
        assert game.outing_say(text=text) == [speech.BLOCKED]
    assert game.outing_ink_left() == 1 and game.state.world.inscriptions == []
    game.outing_say(text="此處風大")  # 沒犯忌的照常刻下去、用掉那一張
    assert [i.text for i in game.state.world.inscriptions] == ["此處風大"] and game.outing_ink_left() == 0
