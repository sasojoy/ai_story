"""招募要情誼門檻（Joy 2026-10-21「現在怎麼很隨便的就能邀請武將加入隊伍」，決策卡選「情誼門檻」）：情誼沒到
Config.recruit_min_affinity（40）時招募鈕不畫、「此地還有人可招」（h_recruit）也不說；到了才畫、照舊寫成功率，公式不動。
歷史武將同行（act:recruit:<id>）與舊的 recruit_at 那一條（act:recruit）一樣。假人與整季機器人只按選單上的鈕，跟著一起擋。"""
from __future__ import annotations

import random

from conftest import real_content
from tianxia import roster
from tianxia.engine import Game
from test_companions import _opts, _player


def test_the_gate_is_forty_in_the_real_config():
    assert real_content().config.recruit_min_affinity == 40
    assert real_content("week7").config.recruit_min_affinity == 40


def test_no_button_and_no_hint_below_the_gate(world):
    c = real_content()
    c.config.auto_open_first_season = True
    guan = _player(c, world, "官甲", "guan", "zhuo_county")
    p = guan.state.player
    p.affinities["liubei"] = 39
    assert not any(i.startswith("act:recruit") for i in _opts(guan))
    assert not guan._recruitable_here()
    p.affinities["liubei"] = 40
    button = _opts(guan)["act:recruit:liubei"]
    assert button.enabled and f"成功率約 {roster.recruit_chance(c, guan.state, 'liubei') * 100:.0f}%" in button.label
    assert "act:recruit:guanyu" not in _opts(guan)  # 一位一位看：情誼到了的那一位才有鈕
    assert guan._recruitable_here()


def test_a_stale_click_below_the_gate_does_nothing(world):
    c = real_content()
    c.config.auto_open_first_season = True
    guan = _player(c, world, "官甲", "guan", "zhuo_county")
    stamina = guan.state.player.stamina
    assert guan.choose("act:recruit:liubei") == ["（此刻無法這麼做。）"]
    assert guan.state.player.stamina == stamina and world.get_companion("liubei").owner is None


def test_the_old_recruit_at_path_has_the_same_gate(content):
    content.config.recruit_min_affinity = 40
    game = Game.new(content, "沈浪", rng=random.Random(0))
    assert "act:recruit" not in [o.id for o in game.options()]
    assert game._recruit_target() is None and game._recruit() == ["（此地此刻沒有能招募的人。）"]
    game.state.player.affinities["scholar"] = 40
    assert game._recruit_target() == "scholar"
    assert "act:recruit" in [o.id for o in game.options()]


def test_zero_is_the_old_rule(content):
    assert content.config.recruit_min_affinity == 0  # 測試內容關著，舊的招募測試照舊
    game = Game.new(content, "沈浪", rng=random.Random(0))
    assert game._recruit_target() == "mate"
