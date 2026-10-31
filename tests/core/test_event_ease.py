"""第一階事件放寬（Config.jianfa.event_ease；企劃者 2026-10-26「事件初期根本一個都過不了…只需調低能力檢定的基礎」）：
減法季開著時檢定的差值加 event_ease，成功率與選項上的心裡話一起變；關著一個字都不變。用正式內容（以前整個檔標 slow，2026-10-31 起只有超過一秒的那幾條標）。"""
from __future__ import annotations

import pytest

from jianfa_kit import jianfa_game, plain_game
from tianxia import rules
from tianxia.models import Check


def _even(game) -> Check:
    return Check(stat="agi", difficulty=game.state.player.stats["agi"])


def test_jianfa_eases_every_check_by_the_configured_points():
    game = jianfa_game()
    ease = game.content.config.jianfa.event_ease
    assert ease == 1.5  # 待企劃者定（前後對照表）
    outlook = rules.check_outlook(_even(game), game.state, game.content, game.world)
    assert outlook.gap == ease
    assert outlook.chance == pytest.approx(0.5 + ease * 0.1)


def test_ease_zero_and_plain_seasons_keep_even_odds():
    game = jianfa_game()
    game.content.config.jianfa.event_ease = 0
    assert rules.check_chance(_even(game), game.state, game.content, game.world) == pytest.approx(0.5)
    off = plain_game()
    assert rules.check_chance(_even(off), off.state, off.content, off.world) == pytest.approx(0.5)


def test_the_ceiling_still_holds():
    game = jianfa_game()
    check = Check(stat="agi", difficulty=0)
    assert rules.check_chance(check, game.state, game.content, game.world) == pytest.approx(0.95)
