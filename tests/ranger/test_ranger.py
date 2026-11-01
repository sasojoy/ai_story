"""遊俠名號（散人的成長階梯，PM 2026-10-08）：散人時攢的善名、惡名與懸賞功績換成名號，每一階解鎖一樣東西；投靠了陣營就凍結。"""
from __future__ import annotations

import random

import pytest

from conftest import install_season_one, real_content
from tianxia import ranger, roster, rules, social
from tianxia.engine import Game
from tianxia.models import Condition, Effect, FactionDef


def _factions(content):
    """名號要劇本有陣營才有（懸賞榜設計 2.2 第 2 點）：測試內容沒有陣營，照 test_raid 的 pair 補兩個。"""
    content.scenario.factions = [
        FactionDef(id="guan", name="官軍", join_at=["town"]),
        FactionDef(id="huang", name="黃巾", join_at=["lake"]),
    ]


@pytest.fixture
def game(content, world):
    install_season_one(content)
    _factions(content)
    content.config.auto_open_first_season = True
    g = Game.new(content, "甲", rng=random.Random(0), world=world)
    g.client = None
    g.sync(1000.0)
    return g


def _gain(game, **stats) -> list[str]:
    return rules.apply_effect(Effect(stats=stats), game.state, game.content, game.world)


@pytest.mark.smoke
def test_good_and_evil_gains_build_the_name_and_pick_the_path(game):
    s, c = game.state, game.content
    assert ranger.tier(s, c) == 0 and ranger.title(c, s) is None
    _gain(game, good=6)
    assert (s.player.ranger_good, ranger.points(s), ranger.tier(s, c)) == (6, 6, 1)
    assert ranger.title(c, s) == "江湖遊俠"
    _gain(game, evil=9)
    assert ranger.path(s) == "寇" and ranger.title(c, s) == "綠林好漢"  # 取高的那一本：9 還是第 1 階
    _gain(game, good=-3)
    assert s.player.ranger_good == 6  # 扣的不算


def test_deeds_add_on_top(game):
    s, c = game.state, game.content
    _gain(game, good=10)
    assert ranger.add_deeds(s, c, 5) == ["俠名 +5"]  # 名聲（2026-10-15）起回寫進紀錄的那一行
    assert ranger.points(s) == 15 and ranger.tier(s, c) == 2 and ranger.title(c, s) == "一方豪俠"


def test_the_status_line_and_the_peer_card(game):
    _gain(game, good=5)
    data = game.status_data()
    assert data["affiliation"] == "散人・江湖遊俠"
    assert data["ranger"]["tier"] == 1 and data["ranger"]["next"] == 15 and data["ranger"]["next_title"] == "一方豪俠"
    assert social.affiliation(game.state, game.content) == "散人・江湖遊俠"


def test_joining_a_faction_freezes_it(game):
    s, c = game.state, game.content
    _gain(game, good=20)
    s.player.faction = "guan"
    _gain(game, good=10)
    assert s.player.ranger_good == 20  # 不再記
    assert ranger.tier(s, c) == 0 and ranger.title(c, s) is None and ranger.status(s, c) is None
    assert ranger.add_deeds(s, c, 5) == []
    assert game.status_data()["ranger"] is None
    s.player.faction = None  # 回到散人（現在沒有這條路；萬一有了，帳原封不動）
    assert ranger.tier(s, c) == 2


def test_nothing_without_factions(content, world):
    """劇本沒有陣營（測試內容）就沒有「散人」可言：什麼都不記。"""
    content.config.auto_open_first_season = True
    g = Game.new(content, "乙", rng=random.Random(0), world=world)
    g.sync(1000.0)
    rules.apply_effect(Effect(stats={"good": 30}), g.state, g.content, g.world)
    assert g.state.player.ranger_good == 0 and ranger.title(g.content, g.state) is None
    assert g.status_data()["affiliation"] == "散人"


def test_the_name_counts_with_the_season_one_switch_off(content, world):
    """第一季規則關著的季、劇本有陣營：照記、照給好處（懸賞榜設計 2.2 第 2 點，企劃者 2026-10-10「整個懸賞榜每季都有」）。"""
    _factions(content)
    content.config.auto_open_first_season = True
    g = Game.new(content, "乙", rng=random.Random(0), world=world)
    g.sync(1000.0)
    assert not g.world.get_season().season_one
    rules.apply_effect(Effect(stats={"good": 15}), g.state, g.content, g.world)
    assert g.state.player.ranger_good == 15 and ranger.tier(g.state, content) == 2
    assert g.status_data()["affiliation"] == "散人・一方豪俠"
    assert ranger.audience_discount(g.state, content) == 2 * content.config.ranger.audience_per_tier


def test_audience_and_recruit_perks(game):
    s, c = game.state, game.content
    cid = next(iter(c.characters))
    c.characters[cid].audience_fame = 20
    bar, chance = rules.audience_bar(s, c, cid), roster.recruit_chance(c, s, cid)
    _gain(game, good=15)  # 第 2 階
    assert bar == 20 and rules.audience_bar(s, c, cid) == 20 - 2 * c.config.ranger.audience_per_tier
    assert roster.recruit_chance(c, s, cid) == pytest.approx(min(0.95, chance + c.config.ranger.recruit_per_tier))
    s.player.faction = "guan"  # 凍結了就不給
    assert roster.recruit_chance(c, s, cid) == pytest.approx(chance)


def test_the_condition(game):
    s, c = game.state, game.content
    cond = Condition(ranger_min=3, ranger_path="寇")
    assert not rules.check_condition(cond, s, c)
    _gain(game, evil=30)
    assert rules.check_condition(cond, s, c)
    assert not rules.check_condition(Condition(ranger_min=3, ranger_path="俠"), s, c)
    assert not rules.check_condition(cond, s)  # 沒給 content 一律不成立
    s.player.faction = "huang"
    assert not rules.check_condition(cond, s, c)


def test_real_content_has_one_qiyu_per_path():
    c = real_content()
    paths = {e.condition.ranger_path for e in c.events.values() if e.condition.ranger_min is not None}
    assert paths == {"俠", "寇"}
    assert all(
        e.qiyu and e.condition.ranger_min == c.config.ranger.qiyu_tier
        for e in c.events.values() if e.condition.ranger_min is not None
    )


def test_unlock_lines_follow_the_config(content):
    lines = ranger.unlocks(content)
    assert len(lines) == len(content.config.ranger.thresholds)
    assert "奇遇" in lines[content.config.ranger.qiyu_tier - 1] and "懸賞" in lines[-1]
