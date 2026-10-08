"""FB-102（QA 7cc1fd7，2026-10-08）：管理者把季末往後排時，最後一天的「這一季之內…」說錯了。

換日在名義季長之後寫不出時刻（季曆只寫到第 12 週・週日 23:59），以前一律改寫「這一季之內不能再來…」；可是季末延後時，名義季長
之後照樣換日（每 4 小時 17 分重算），照字面走的人會白白放棄。換日的時刻怎麼算不改（PM：不改什麼時候換日）。

現在（rules.day_turn）分三種：
- 換日在真的季末（排定的 schedule["finale"]）之前、寫得出來：照舊寫那一刻；
- 換日在真的季末之前、但在名義季長之後（寫不出來）：寫一句不承諾時刻的話（「過一陣子」，待 joy 潤）；
- 換日在真的季末那一刻或之後：「這一季之內…」（那時才是真的）。
測試內容（tests/fixtures），第一季縮小的時刻表（conftest.install_season_one）；句子照字比（每一句都是待 joy 潤的初稿，改字時改這裡）。"""
from __future__ import annotations

import random
from unittest import mock

import pytest
from conftest import FixedRandom, walk_to
from test_day_scale import SHORT, WEEKEND, _lake, _miss, _season, _talk_out, SCENE

from tianxia import rules, sensing
from tianxia.models import TimetableEvent

LATER_TEXTS = {
    "warning": "> 選錯了做法，這裡要過一陣子才悟得出。",
    "miss": "心浮氣躁，什麼也沒抓住。要過一陣子，這裡才悟得出東西。",
    "explore": "；這裡要過一陣子才悟得出",
    "talk": "韓鐵起身送客，改日再敘：過一陣子再來拜會吧。",
    "talked_out": "已經談滿 3 輪，過一陣子再來",
    "busy": "韓鐵事忙，過一陣子才得空。",
    "intro": "最多談 3 輪，過一陣子重新算起；",
    "gather": "你留心路邊，這陣子已經撿夠了，沒再去翻（過一陣子再說）。",
    "think": "你邊走邊想，這陣子想得夠多了，沒有新的心得（過一陣子才會再有）。",
}


def _postponed(content, game, finale=16 * SHORT):
    """管理者把季末排到 finale（世界秒）：時刻表要有季末那一件，排定的時間記在 schedule["finale"]。"""
    if not any(e.kind == "finale" for e in content.timetable):
        content.timetable.append(TimetableEvent(id="finale", week=12, title="季末", kind="finale"))
    game.state.world.schedule["finale"] = finale


def test_the_three_kinds_of_day_turn(content):
    content.config.season_one = True
    content.timetable.append(TimetableEvent(id="finale", week=12, title="季末", kind="finale"))
    season = _season(content, WEEKEND, one=True)
    season.schedule["finale"] = 16 * SHORT  # 延後兩個多遊戲日
    season.time = 12.5 * SHORT
    assert rules.day_turn(content, season) == ("at", "第 12 週・週二 00:00")  # 名義季長以內：照舊
    for t in (13.5, 14.5):  # 換日落在名義季長之後、真的季末之前：寫不出時刻，但還會換日
        season.time = t * SHORT
        assert rules.day_turn(content, season) == ("later", None) and rules.day_ends_text(content, season) is None
    season.time = 15.5 * SHORT  # 真的最後一個遊戲日：換日在季末那一刻之後
    assert rules.day_turn(content, season) == ("season", None)
    plain = _season(content, WEEKEND, one=True)  # 沒延後：最後一天照舊是「這一季之內」
    plain.time = 13.5 * SHORT
    assert rules.day_turn(content, plain) == ("season", None)


def test_days_still_turn_after_the_nominal_end(content):
    """換日的時刻不改：名義季長之後照樣每一個遊戲日換一次（以前就是這樣，句子跟著說實話）。"""
    season = _season(content, WEEKEND, one=True)
    days = [rules.game_day(content, season, t * SHORT) for t in (13.5, 14.5, 15.5)]
    assert days == [14, 15, 16]


def _texts(game, content):
    """所有寫「什麼時候再來」的句子，照 LATER_TEXTS 的鍵。"""
    out = {}
    sensing.start(game.state, content, SCENE, random.Random(0))
    out["warning"] = sensing.scene_text(game.state, content)
    game.state.player.sensing = None
    out["miss"] = _miss(game)[-1]
    out["explore"] = game.action_notes(["act:explore"])["act:explore"]
    game.state.player.location = "town"
    out["talk"] = _talk_out(game)[-1]
    out["talked_out"] = game._talked_out_note()  # noqa: SLF001
    with mock.patch("tianxia.engine.pick_event", return_value=None):
        out["busy"] = game.choose("act:socialize")[0]
    content.characters["scholar"].deep_interaction = True
    content.characters["scholar"].audience_fame = 0
    out["intro"] = game._audience_intro()  # noqa: SLF001
    content.config.road_reward_daily_cap = 1
    game.choose("move:lake")
    game.choose("road:think")
    game.rng = FixedRandom(0.1)
    out["gather"] = game.choose("road:gather")[0]
    walk_to(game, "lake")
    game.choose("move:town")
    out["think"] = game.choose("road:think")[0]
    return out


def test_after_the_nominal_end_of_a_postponed_season_nothing_promises_the_whole_season(content):
    game = _lake(content, WEEKEND, one=True)
    _postponed(content, game)
    game.state.world.time = 13.5 * SHORT
    texts = _texts(game, content)
    for key, line in LATER_TEXTS.items():
        assert line in texts[key], key
    assert not any("這一季之內" in t or "23:59" in t or "第 12 週・週日" in t for t in texts.values())


def test_the_real_last_day_still_says_this_season(content):
    game = _lake(content, WEEKEND, one=True)
    _postponed(content, game)
    game.state.world.time = 15.5 * SHORT
    texts = _texts(game, content)
    assert "這一季之內" in texts["talk"] and "這一季之內" in texts["warning"] and "過一陣子" not in texts["talked_out"]
    assert texts["talked_out"] == "已經談滿 3 輪，這一季之內不能再來"


@pytest.mark.parametrize("finale", [None, 10 * SHORT])
def test_a_season_that_was_not_postponed_is_unchanged(content, finale):
    """沒延後（最後一天照舊「這一季之內」）、提前收季（換日在季末之後：也是「這一季之內」）。"""
    game = _lake(content, WEEKEND, one=True)
    if finale is not None:
        _postponed(content, game, finale)
    game.state.world.time = (9.5 if finale else 13.5) * SHORT
    assert rules.day_turn(content, game.state.world) == ("season", None)
    assert game._talked_out_note() == "已經談滿 3 輪，這一季之內不能再來"  # noqa: SLF001
