"""第一季濃縮版 T5：頭銜、召見、第 2 階晉升奇遇、部下（計畫 2026-10-05-T5-晉升）。

用真實內容（content/）：要驗的就是真實的晉升定義、奇遇、部下與大勢人物。每個測試自己載一份，開關在測試裡才打開。"""
from __future__ import annotations

import random
from pathlib import Path
from unittest import mock

import pytest

from tianxia import team
from tianxia.content import load_content
from tianxia.encounter import EncounterResult
from tianxia.engine import Game
from tianxia.models import Config, Effect
from tianxia.state import PlayerState, WorldState

CONTENT_DIR = Path(__file__).parent.parent / "content"


@pytest.fixture
def real():
    c = load_content(CONTENT_DIR)
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    c.config.train_stat_chance = 0.0
    return c


@pytest.fixture
def on(real):
    real.config.season_one, real.config.season_days, real.config.server_max_players = True, 2.5, 2
    return real


def _game(content, name="甲", faction=None, at=None, world=None):
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.state.player.faction = faction
    if at is not None:
        game.state.player.location = at
    return game


def _win():
    return mock.patch.object(
        team, "fight", return_value=EncounterResult(tier="大勝", margin=50, our_power=100, difficulty=15),
    )


# ── Task 1：資料模型與內容 ─────────────────────────────────


def test_new_fields_have_defaults_so_old_saves_load():
    assert Config().rank2_contrib == 300
    p = PlayerState(name="甲", location="x", stats={}, stamina=0)
    assert (p.rank, p.summons, p.followers) == (0, None, [])
    assert WorldState().promoted_today == {}
    assert (Effect().promote, Effect().followers, Effect().affinity) == (None, [], {})


def test_real_promotions_valid(real):
    by_side = {p.faction: p for p in real.promotions}
    assert set(by_side) == {"guan", "huang", "haoqiang"} and all(p.rank == 2 for p in real.promotions)
    guan, huang, gentry = by_side["guan"], by_side["huang"], by_side["haoqiang"]
    assert (guan.figure, guan.successor, guan.location) == ("huangfusong", "zhujun", "changshe")
    assert (huang.figure, huang.successor, huang.location) == ("bocai", "pengtuo", "huangjin_camp")
    assert (gentry.figure, gentry.successor, gentry.location, gentry.event_handoff) == (None, None, "nearest_base", None)
    assert guan.summons_text == "皇甫嵩召你到長社營中。" and guan.summons_handoff == "朱儁召你到長社營中。"
    assert gentry.summons_text == "中山的馬商張世平、蘇雙到了{據點}，指名要見你。"
    for p in real.promotions:
        for event_id in filter(None, (p.event_main, p.event_handoff)):
            event = real.events[event_id]
            assert event.actions == [] and len(event.choices) == 3
            assert all(ch.effect.promote == 2 and len(ch.effect.followers) == 2 for ch in event.choices)
    first = real.events["promo_guan_2"].choices[1]
    assert first.effect.affinity == {"huangfusong": 10} and first.effect.text == "皇甫嵩微微一笑。"
    assert real.events["promo_haoqiang_2"].choices[1].effect.materials == {"kuai_1": 2}


def test_real_followers_valid(real):
    assert set(real.followers) == {
        "follower_guan_spear", "follower_guan_crossbow", "follower_huang_believer",
        "follower_huang_strongman", "follower_haoqiang_retainer", "follower_haoqiang_buqu",
    }
    spear = real.followers["follower_guan_spear"]
    assert (spear.name, spear.faction, spear.wugong, spear.wugong_level) == ("持矛鄉勇", "guan", "xingwu_qiang", 3)
    assert all(f.wugong in real.skills for f in real.followers.values())
    assert real.skills["qiangnu"].name == "強弩射法"
