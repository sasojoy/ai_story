"""第一季濃縮版 T1：三條戰線、黃巾聲勢（衍生）、豪強割據，以及第一季的規則沒開（開關關著，或這一季開季時沒蓋「開」的章）時一切照舊。

規則與引擎的測試大多用真實內容（content/）：要驗的就是那三條戰線、起始值與地點歸屬。每個測試自己載一份
（約 0.06 秒），開關在測試裡才打開，不會漏到別的測試。"""
from __future__ import annotations

import random
from pathlib import Path
from unittest import mock

import pytest

from conftest import FixedRandom
from tianxia import atlas, battle_instance, bot_policy, mapview, rules, team, timetable, world
from tianxia.content import ContentError, load_content, validate
from tianxia.encounter import EncounterResult
from tianxia.engine import Game
from tianxia.models import Condition, Config, Effect
from tianxia.state import BotProfile, WorldState
from tianxia.world_state import fresh_season

CONTENT_DIR = Path(__file__).parent.parent / "content"
FRONTS = ["yingru", "nanyang", "jizhou"]


@pytest.fixture
def real():
    """真實內容，開關關著（beta 那一季的樣子）。"""
    c = load_content(CONTENT_DIR)
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0  # 遊歷打完不接戰後事件，大勢的變化才寫得死
    c.config.train_stat_chance = 0.0
    return c


@pytest.fixture
def on(real):
    """同一份真實內容，開關打開（第一季濃縮版）。"""
    real.config.season_one = True
    return real


def _game(content, name="甲"):
    return Game.new(content, name, rng=random.Random(0))


def _win():
    """遊歷穩贏（team.fight 的結果寫死），只看大勢怎麼推。"""
    return mock.patch.object(
        team, "fight", return_value=EncounterResult(tier="大勝", margin=50, our_power=100, difficulty=15),
    )


def test_the_season_one_switch_is_off_by_default():
    cfg = Config()
    assert cfg.season_one is False
    assert (cfg.geju_chaos_per_day, cfg.geju_calm_per_day, cfg.chaos_low, cfg.chaos_high) == (1.0, 1.0, 35, 65)
    assert WorldState().trend_accum == {}
