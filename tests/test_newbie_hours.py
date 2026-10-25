"""新手期照現實時間（Joy 2026-10-17「新手期 48 小時」；Config.newbie_real_hours）：體力回復不分新手期、氣血不加倍。"""
from __future__ import annotations

from conftest import real_content

from tianxia import roster
from tianxia.engine import HOUR


def test_real_content_newbie_rules():
    for content in (real_content(), real_content("week7")):
        cfg = content.config
        assert cfg.newbie_real_hours == 48 and cfg.newbie_stamina_multiplier == 1 and not cfg.newbie_hp_double


def test_newbie_counts_real_hours_from_joining(game):
    cfg = game.content.config
    cfg.newbie_real_hours = 48
    s = game.state
    s.player.joined_at = s.world.time - 47 * HOUR * cfg.time_scale
    assert roster.newbie(s, game.content) and roster.raid_newbie(s, game.content)
    s.player.joined_at = s.world.time - 49 * HOUR * cfg.time_scale
    assert not roster.newbie(s, game.content) and not roster.raid_newbie(s, game.content)


def test_hp_does_not_double_when_turned_off(game):
    cfg = game.content.config
    cfg.newbie_real_hours = 48
    s = game.state
    s.player.joined_at = s.world.time
    member = s.player.member
    rates = []
    for double in (True, False):
        cfg.newbie_hp_double = double
        member.neili = 1.0
        game._advance_player_local(600.0)
        rates.append(member.neili)
    assert rates[0] > rates[1] > 1.0
