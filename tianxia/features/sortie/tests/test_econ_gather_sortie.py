"""素材與經濟（docs/superpowers/specs/2026-10-15-素材與經濟-design.md）第七、八節：出陣攻打贏給對手銀兩三成。
正式內容、週末設定（Config.economy 預設開）。"""
from __future__ import annotations

import random
from decimal import ROUND_HALF_UP, Decimal
from types import SimpleNamespace

import pytest
from test_sortie import _fight, _game

from conftest import real_content
from tianxia import explore_one, precise

pytestmark = pytest.mark.whole_content


def _wild(c, danger):
    return next(loc for loc in c.locations.values() if loc.danger == danger and not precise.is_town(c, loc))


def test_gather_second_tier_odds_are_unchanged():
    c = real_content("week7")
    loc = _wild(c, 3)
    got = sum(any(c.materials[m].tier == 2 for m in explore_one.gather_finds(c, loc, random.Random(i))) for i in range(2000))
    assert 0.45 < got / 2000 < 0.55


@pytest.mark.smoke
def test_winning_an_attack_pays_a_third_of_the_silver():
    game = _game(faction="guan")
    p = game.state.player
    silver = p.stats["silver"]
    with _fight():
        msgs = game.choose("act:train")
    record = game.state.battles[-1]
    squad = next(q for q in game.content.squads.values() if q.name == record.opponent)
    pay = int(squad.reward_silver * 0.3 + 0.5)
    assert pay > 0 and record.silver == pay and p.stats["silver"] == silver + pay
    assert f"銀兩 +{pay}" in msgs and record.materials == []


def test_the_third_is_rounded_half_up_for_every_squad():
    """FB-271：三成照四捨五入（逢 .5 進位），不是 Python round 的逢 .5 取偶數；黃巾別部 15 兩的三成 4.5 給 5 兩。"""
    game = _game(faction="guan")
    c = game.content
    share = Decimal(str(c.config.economy.sortie_silver_share))
    paid = {}
    for squad in c.squads.values():
        if squad.reward_silver <= 0:
            continue
        record = SimpleNamespace(silver=0, xinde=0, exp=0, levelups=[], notes=[])
        game._sortie_rewards(squad, record)
        want = int((Decimal(squad.reward_silver) * share).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        assert record.silver == want, squad.name
        paid[squad.reward_silver] = record.silver
    assert paid[15] == 5  # 黃巾別部那一檔（以前給 4）


def test_losing_or_holding_pays_no_silver():
    game = _game(faction="guan")
    game.state.player.stats["silver"] = 100
    with _fight("落敗"):
        game.choose("act:train")
    assert game.state.battles[-1].silver == -10 and game.state.player.stats["silver"] == 90  # 照舊只失一成，不加給
    hold = _game(at="huangjin_camp")  # 黃巾在自家大本營：守
    silver = hold.state.player.stats["silver"]
    hold.choose("act:train")
    assert hold.state.player.stats["silver"] == silver


def test_sortie_silver_off_pays_nothing():
    game = _game(faction="guan")
    game.content.config.economy.sortie_silver = False
    silver = game.state.player.stats["silver"]
    with _fight():
        game.choose("act:train")
    assert game.state.battles[-1].silver == 0 and game.state.player.stats["silver"] == silver
