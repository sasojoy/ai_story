"""探索包（走一趟、探索一顆）登記之後的煙霧與接縫：包的內容驗證（原本的 content.check_explore_one、check_outing_lines）照樣擋得下
壞的內容、核心照 FEATURES 叫得到它；核心寫的那一份「旅人」跟包裡的一樣（核心不 import 包，抄了一份字）。"""
from __future__ import annotations

from unittest import mock

import pytest
from jianfa_kit import jianfa_game, ready
from test_outing import _draws, _game, _settle_event, _walked, _with_ink

from conftest import real_content
from tianxia import content as content_mod
from tianxia import sensing, speech
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


def test_the_outing_wall_takes_the_banned_words_from_the_core(monkeypatch):
    """合酒肆包（主動搬六包第 10 批）時禁字搬進核心 naming.BANNED_WORDS（探索包不 import 酒肆包，酒肆包 re-export 同一份）：走一趟的留言
    照核心那一份擋——核心那一份多一個字，留言跟著擋；擋下的不用墨、不刻字。"""
    from tianxia import naming

    game = _game()
    _walked(game)
    _with_ink(game)
    game.content.banned_words = []
    monkeypatch.setattr(naming, "BANNED_WORDS", (*naming.BANNED_WORDS, "驛馬"))
    text = "此處有驛馬"
    assert speech.problem(text, game.content, speech.MOTTO, game.content.config.jianfa.outing_say_max) is None  # 字表碰不到
    assert game.outing_say(text=text) == [speech.BLOCKED]
    assert game.outing_ink_left() == 1 and game.state.world.inscriptions == []


# ── 審查修正（回歸鏡頭）：搬過去的本體裡原本沒有人守的三條路（變異拿掉任何一條，整個包的測試與包外 5,355 條都是綠的）──

def test_leaving_a_stopped_trip_closes_it_as_left_instead_of_walking_on():
    """走一趟停在要選的事上、選完之後人已經不在出發的地方：接著走不再走，這一趟收成「中途離開」（outing_go 的 trip.place 那一道）。"""
    game = _game()
    p = game.state.player
    with _draws(explore_rules.MATERIAL, explore_rules.EVENT, explore_rules.MATERIAL):
        game.outing_go(3)
        _settle_event(game)
        trip = p.outing
        assert (trip.done, trip.end) == (2, "") and game.outing_view()["trip"]["can_go"] is True
        p.location = next(loc for loc in game.content.locations if loc != trip.place)  # 選完事之後走開了
        assert game.outing_go() == [outing_rules.END_LINES[outing_rules.LEFT]]
    assert (trip.done, trip.end) == (2, outing_rules.LEFT)  # 沒再走第三段、第三段的體力沒扣


def test_a_material_beat_asks_the_home_gather_and_keeps_what_it_gives():
    """素材那一拍收完照舊問領地爭奪「站在自家領地多給的那一個」（ctx._home_gather；測試換掉它，包裡經 ctx 叫才打得到），給的字進這一下的回話。"""
    game = _game()
    asked: list[tuple[str, list[str]]] = []

    def home(loc, mids):
        asked.append((loc.id, list(mids)))
        return ["（自家領地多給了一個）"]

    with _draws(explore_rules.MATERIAL), mock.patch.object(game, "_home_gather", side_effect=home):
        said = game.choose(IDLE_MARK)
    assert [place for place, _ in asked] == ["yingshui"] and asked[0][1]  # 問了一次，帶著這一拍找到的素材
    assert "（自家領地多給了一個）" in said


def test_a_sense_missed_today_zeroes_the_insight_beat_at_that_place():
    """這個遊戲日在這一處選錯過做法（sensing.missed_today）：這一處的比重裡感悟是 0（分給其餘的）；沒選錯過寺裡的感悟本來就有。"""
    game = _game()
    game.state.player.location = "baima_temple"
    assert game.outing_plan().weights[explore_rules.INSIGHT] > 0
    with mock.patch.object(sensing, "missed_today", return_value=True):
        weights = game.outing_plan().weights
    assert weights[explore_rules.INSIGHT] == 0 and sum(weights.values()) > 0
