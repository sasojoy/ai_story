"""出陣（docs/superpowers/specs/2026-10-14-出陣探索與地盤-design.md 第二節）。正式內容、週末設定。
開季：潁川汝南 40；黃巾別部營寨是黃巾的大本營（站黃巾別部、黃巾渠帥，train_trend 潁川汝南 −2）；汝南荒野此刻歸黃巾。"""
from __future__ import annotations

import random
from unittest import mock

import pytest

from conftest import classic_rules, real_content, third_party_gentry
from conquest_kit import conquest_rules
from test_real_content import _walk_the_hut

import server
from tianxia import sortie, team
from tianxia.encounter import EncounterResult
from tianxia.engine import Game, drill_share
from tianxia.sqlite_world import open_world
from tianxia.state import Order

TW_MIDNIGHT = 16 * 3600  # UTC 16:00＝台灣 00:00（1970-01-02）


def _game(faction="huang", at="runan_wilds", profile="week7", name="沈浪", third_party=False):
    c = conquest_rules(real_content(profile))  # 出陣約戰關掉，攻一下就打一場；翻地與爭搶本身在 tests/acts/test_conquest_*.py
    c.config.auto_open_first_season = True
    if third_party:
        third_party_gentry(c)  # 豪強是第三方、出陣攪局的規則（豪強分屬兩軍之前）
    c.config.train_event_chance = 0.0
    # 第 4 批之前的出陣獎勵（三成、不掉東西）：新規則在 tests/test_sortie_rewards.py（設計 8.4）
    c.config.precise_actions = False
    c.config.four_tiers.enabled = False
    game = Game.new(c, name, rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.faction, p.location, p.stamina = faction, at, float(c.config.stamina_max)
    p.tutorial_step = len(c.tutorial.steps)  # 引導走完：完成步驟的獎勵不混進心得、經驗的帳
    p.visited.add(at)
    return game


def _sortie(game):
    return next((o for o in game.options() if o.id == "act:train"), None)


def _fight(tier="大勝"):
    return mock.patch.object(team, "fight", return_value=EncounterResult(tier=tier, margin=50, our_power=200, difficulty=40))


@pytest.mark.smoke
def test_losing_an_attack_costs_silver_and_pushes_nothing():
    game = _game(faction="guan")
    game.state.player.stats["silver"] = 100
    with _fight("落敗"):
        game.choose("act:train")
    assert game.state.player.stats["silver"] == 90 and game.state.world.trends["yingru"] == 40


def test_five_a_day_then_grey_until_taiwan_midnight():
    """Review Focus 1：UTC 15:59:59（台灣 23:59:59）用滿五次，下一秒台灣 00:00 又有五次。"""
    game = _game()
    game.now = TW_MIDNIGHT - 1
    for _ in range(5):
        game.choose("act:train")
    option = _sortie(game)
    assert not option.enabled and sortie.USED_UP.format(n=5) in option.label
    assert game.choose("act:train") == ["（此刻無法這麼做。）"]
    game.now = TW_MIDNIGHT
    assert _sortie(game).enabled and game.sorties_left() == 5


def test_advancing_rolls_the_sortie_day():
    """整季機器人只 advance、不 sync：次數照 advanced_real 換日（同回體丹）。now 0＝台灣 08:00。"""
    game = _game()
    for _ in range(5):
        game.choose("act:train")
    assert game.sorties_left() == 0
    game.advance(TW_MIDNIGHT)
    assert game.sorties_left() == 5


def test_a_new_season_does_not_give_another_five_the_same_day():
    """次數跨季保留（state.py：換季不能多出一輪；同回體丹）：當天用完五次之後換季，還是灰的。"""
    from conftest import next_season

    game = _game()
    game.now = 100.0
    for _ in range(5):
        game.choose("act:train")
    next_season(game.content, game.world, game)
    assert game.state.player.sortie_day != -1 and game.sorties_left() == 0


def test_a_hold_never_asks_the_model():
    game = _game()
    game.client = mock.Mock()
    assert server.may_judge_fight("act:train") and game.fight_request("act:train") is None


def test_the_siege_card_says_sortie():
    from tianxia import atlas

    game = _game()
    order = Order(id="1:huang:siege:yingru", template="siege", faction="huang", week=1, front="yingru", quota=9, text="")
    assert "出陣" in atlas.order_how(game.state, game.content, order) and "遊歷" not in atlas.order_how(game.state, game.content, order)


# ── 守勢行動（PM 2026-10-14 對計畫第 17 條的決定）──────────────────


def _duty(game):
    return next((o for o in game.options() if o.id == "act:duty"), None)


def test_rank_actions_do_not_spend_sorties():
    """PM 2026-10-14：只有守勢行動跟出陣共用次數；第 2、3 階（第 4 階同一條路）的行動不扣。"""
    from tianxia import rules

    game = _game(at="julu_altar")
    p = game.state.player
    p.rank = 2
    before = p.stamina
    with mock.patch.object(rules, "check_chance", return_value=1.0):
        game.choose("act:rank2")
        p.rank, p.location = 3, "runan"
        game.choose("act:rank:incite")
    cfg = game.content.config
    assert p.stamina == before - cfg.rank2_stamina - 20  # 兩下都真的做了
    assert game.sorties_left() == 5 and p.sortie_day == -1
