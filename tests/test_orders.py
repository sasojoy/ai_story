"""第一季濃縮版 T6：陣營軍令、最小糧草、第 1 階守勢行動（計畫 2026-10-05-T6-軍令）。

規則與引擎的測試用真實內容（content/）：要驗的就是真實的插槽、戰線與大勢人物。每個測試自己載一份，
開關在測試裡才打開，不會漏到別的測試。開關開著的季是「蓋了章」的：auto_open_first_season 開出來的季
照當下的 Config 蓋章（world_state.stamp_season）。"""
from __future__ import annotations

import random
from pathlib import Path
from unittest import mock

import pytest

from tianxia import calendar, figures, orders, rules, team, timetable
from tianxia.content import load_content
from tianxia.encounter import EncounterResult
from tianxia.engine import Game
from tianxia.models import Config
from tianxia.state import Convoy, Order, PlayerState, WorldState

CONTENT_DIR = Path(__file__).parent.parent / "content"


@pytest.fixture
def real():
    """真實內容，開關關著（beta 那一季的樣子）。"""
    c = load_content(CONTENT_DIR)
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    c.config.train_stat_chance = 0.0
    return c


@pytest.fixture
def on(real):
    """同一份真實內容，照週末設定打開：開關、季長 2.5 天、人數上限 2（每道軍令 4 次）。"""
    real.config.season_one = True
    real.config.season_days = 2.5
    real.config.server_max_players = 2
    return real


def _game(content, name="甲", faction=None, at=None, world=None):
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.state.player.faction = faction
    if at is not None:
        game.state.player.location = at
    return game


def _win():
    """遊歷穩贏（team.fight 的結果寫死）。"""
    return mock.patch.object(
        team, "fight", return_value=EncounterResult(tier="大勝", margin=50, our_power=100, difficulty=15),
    )


def _order(game, template, faction, *, front=None, location=None, start=None, end=None, figure=None, quota=4):
    """直接放一道這一週的軍令（不經過 issue），測記功與效果用。"""
    week = orders.week_of(game.state, game.content)
    order = Order(
        id=f"{week}:{faction}:{template}:{front or figure or location}", template=template, faction=faction,
        week=week, front=front, location=location, start=start, end=end, figure=figure, quota=quota, text="（測試）",
    )
    game.state.world.orders.append(order)
    return order


# ── Task 1：資料模型與內容 ─────────────────────────────────


def test_new_fields_have_defaults_so_old_saves_load():
    cfg = Config()
    assert (cfg.orders_per_week, cfg.order_quota_min, cfg.convoy_ambush_chance, cfg.convoy_grain, cfg.duty_stamina) == (
        3, 4, 0.2, 4, 10,
    )
    assert WorldState().orders == []
    assert PlayerState(name="甲", location="x", stats={}, stamina=0).convoy is None
    assert WorldState.model_validate({"time": 5.0}).orders == []  # 舊的賽季存檔沒有這一欄


def test_real_orders_content(real):
    o = real.orders
    kinds = sorted((t.kind, t.side) for t in o.templates)
    assert kinds == sorted([
        ("defend", "guan"), ("defend", "huang"), ("intercept", "guan"), ("intercept", "huang"),
        ("escort", "guan"), ("escort", "huang"), ("siege", "guan"), ("siege", "huang"),
        ("strike", "guan"), ("strike", "huang"), ("strike", "haoqiang"),
    ])
    assert o.slots["yingru"]["guan"].intercept == "hilltop_wilds"
    assert o.slots["nanyang"]["huang"].escort == ("nanyang_wilds", "nanyang_huangjin_camp")
    assert {f: d.name for f, d in o.duties.items()} == {"guan": "巡哨", "huang": "傳道", "haoqiang": "保境安民"}
    assert real.squads["guan_grain_convoy"].faction == "guan" and real.squads["huang_grain_convoy"].faction == "huang"
    assert real.squads["huang_grain_convoy"].drops[0].material == "man_1"
