"""FB-672：頭目的次數用完時，練功那一行（與練功鈕括號裡同一句）要說出「誰」不再現身。

以前寫「這一段他不再現身，第 3 天 00:00 再來」，行動列底下獨立成一行之後（FB-670）「他」要回頭猜；頭目還在時那一行寫
「這裡只有頭目段鐵頭」有名字。現在 Game._boss_away 把頭目的名字帶進 explore_modes.boss_gone：
「這一段頭目段鐵頭不再現身，第 3 天 00:00 再來」（7 天濃縮季）、「這一週頭目…不再現身」（21 天季）、「這一季頭目…不再現身」。
名字是這一隻頭目對你露的那一面（Game._boss_face：照陣營），跟「這裡只有頭目某某」、練功鈕上的名字同一個。新字待 joy 潤。
冷卻中那一句（頭目約 N 後才會再現身）本來就有「頭目」兩字，這一張不動。
"""
from __future__ import annotations

import random

import pytest
from conftest import real_content
from jianfa_kit import no_jianfa

from tianxia import explore_modes, howto
from tianxia import duel as duel_rules
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

pytestmark = pytest.mark.slow

HOUR = 3600
MON = 1792339200  # 2026-10-19 週一 00:00（台灣）
NOW = MON + 10 * HOUR
PRACTICE = "explore:practice"


def _game(at, faction, profile="week7"):
    c = no_jianfa(real_content(profile))  # 減法季探索一顆開著時沒有練功鈕（頭目改掛在出門一趟的遭遇拍）：這一份測的是舊的練功鈕
    store = open_world()
    store.seed_first_season(c)
    store.open_season(c, NOW)
    game = Game.new(c, "沈浪", rng=random.Random(0), world=store)
    game.client = None
    game.sync(NOW)
    p = game.state.player
    p.location, p.faction, p.stamina = at, faction, 250.0
    p.tutorial_step = len(c.tutorial.steps)
    return game


def _option(game):
    return next(o for o in game.options() if o.id == PRACTICE)


def _note(game):
    return game.action_notes([o.id for o in game.options()]).get(PRACTICE)


def _reason(option):
    return option.label.split("（", 1)[1].removesuffix("）")


def _use_up(game):
    s, c = game.state, game.content
    boss = duel_rules.here(s, c)[0]
    key = duel_rules.week_key(s, c, boss.id) if c.config.duel.per_boss_week else duel_rules.season_key(s, boss.id)
    s.player.duel_tally[key] = c.config.duel.per_boss_week or c.config.duel.per_boss_season
    return boss


def _face_before(game):
    """頭目還在時，練功那一行寫的名字（「這裡只有頭目某某…」）。"""
    option = _option(game)
    assert option.enabled
    face = option.label.split("・")[1]
    assert _note(game) == howto.PRACTICE_BOSS_NOTE.format(foe=face)
    return face


# 只有頭目的地方（沒有一路是他的對手以外的隊伍）：官軍站長社、黃巾站鉅鹿道壇；反過來站的那一方有尋常對手，練功那一行寫打誰，不走這一句
@pytest.mark.parametrize("faction,place", [("guan", "changshe"), ("huang", "julu_altar")])
def test_week7_names_the_boss_and_the_day_he_comes_back(faction, place):
    game = _game(place, faction)
    face = _face_before(game)
    _use_up(game)
    option = _option(game)
    assert not option.enabled and option.note == ""
    day = game.content.config.season_segments  # 前提：第 1 段兩天，下一段從第 3 天開始
    assert day[0] == 2
    assert _note(game) == _reason(option) == f"這一段頭目{face}不再現身，第 3 天 00:00 再來"
    assert "他不再現身" not in _note(game)


def test_the_last_segment_says_this_season():
    game = _game("changshe", "guan")
    face = _face_before(game)
    _use_up(game)
    game.sync(NOW + 5 * 24 * HOUR)  # 第 6 天：最後一段（第 5～7 天）沒有下一段
    # 換了段，這一段的次數是新的一筆帳：再用完一次
    _use_up(game)
    assert _note(game) == f"這一季頭目{face}不再現身"


def test_season21_says_this_week():
    game = _game("changshe", "guan", "season21")
    face = _face_before(game)
    _use_up(game)
    assert _note(game) == _reason(_option(game)) == f"這一週頭目{face}不再現身"


@pytest.mark.parametrize("profile", ["weekend", None])
def test_the_other_seasons_say_this_season(profile):
    game = _game("changshe", "guan", profile)
    face = _face_before(game)
    _use_up(game)
    assert _note(game) == _reason(_option(game)) == f"這一季頭目{face}不再現身"


@pytest.mark.parametrize("faction,place,seen,other", [("guan", "changshe", "段鐵頭", "韓稜"), ("huang", "julu_altar", "衛重", "梁鶴")])
def test_the_name_is_the_face_he_shows_that_side(faction, place, seen, other):
    """同一隻頭目有兩個面貌（官軍遇上黃巾那一面、黃巾遇上官軍那一面），寫的是你看到的那一個。"""
    game = _game(place, faction)
    _use_up(game)
    assert f"頭目{seen}不再現身" in _note(game) and other not in _note(game)


def test_cooling_keeps_its_own_sentence():
    game = _game("changshe", "guan")
    s = game.state
    s.player.duel_last = [float(s.player.season_number), s.world.time]
    option = _option(game)
    assert not option.enabled and "後才會再現身" in _note(game) and _note(game) == _reason(option)
    assert explore_modes.BOSS_COOLING.split("{")[0] in _note(game)


def test_boss_gone_needs_the_boss_name():
    c = real_content("week7")
    game = _game("changshe", "guan")
    assert explore_modes.boss_gone(game.state, c, "某某").startswith("這一段頭目某某不再現身")
