"""本週卡「你這一步」的第一順位接上託付（減法季批 6；整合設計 6.1；批 1 欄位表「託付的正式來源」）：身上還在辦的那一件人物託付
排在最前面（在懸賞列裡標了 commission 的委託之前），寫「到長社，替盧植交信。」；辦完、作罷、關著的季照舊。正式內容的 season21。"""
from __future__ import annotations

import pytest

from stances_kit import LUZHI, real_game
from tianxia import errands, weekcard

pytestmark = pytest.mark.slow  # 載正式內容、照伺服器開季


def _steps(g):
    return weekcard.week_card(g, g.status_data(), g.orders_view())["steps"]


def test_an_open_errand_leads_your_next_step():
    g = real_game()
    s, c = g.state, g.content
    before = _steps(g)
    s.player.affinities[LUZHI] = 50
    errands.give(s, c, LUZHI, "luzhi_letter")
    e = s.player.errands[-1]
    steps = _steps(g)
    first = steps[0]
    assert first["kind"] == "errand" and first["id"] == e.id and first["who"] == "盧植"
    assert first["text"] == errands.STEP.format(place=c.locations[e.target].name, who="盧植", label=errands.LABELS["letter"])
    assert first["target"]["location"] == e.target and first["target"]["minutes"] >= 1
    assert steps[1:] == before  # 其餘照舊排在後面
    e.status = "done"
    assert _steps(g) == before


def test_closed_seasons_keep_the_old_steps():
    g = real_game(setup=lambda c: setattr(c.config.jianfa, "errands", False))
    s, c = g.state, g.content
    before = _steps(g)
    errands.give(s, c, LUZHI, "luzhi_letter")  # 就算身上有（換了設定），關著不列
    assert _steps(g) == before
