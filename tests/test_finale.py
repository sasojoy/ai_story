"""第一季濃縮版 T9：結局、季末公告、決定性勝利、結算畫面（計畫 2026-10-05-T9-結局與結算畫面）。

用真實內容（content/）：要驗的就是那六種結局、三條戰線與季末大事。每個測試自己載一份，開關在測試裡才打開；
auto_open_first_season 開出來的季照當下的 Config 蓋章，所以開關開著的季是「蓋了章」的。"""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from tianxia import guide, rules
from tianxia import world as world_mod
from tianxia.content import load_content
from tianxia.engine import Game

CONTENT_DIR = Path(__file__).parent.parent / "content"


@pytest.fixture
def real():
    """真實內容，開關關著（beta 那一季的樣子）。"""
    c = load_content(CONTENT_DIR)
    c.config.auto_open_first_season = True
    return c


@pytest.fixture
def on(real):
    """同一份真實內容，照週末設定打開：開關、季長 2.5 天、人數上限 2。"""
    real.config.season_one, real.config.season_days, real.config.server_max_players = True, 2.5, 2
    return real


def _game(content, name="甲", world=None):
    return Game.new(content, name, rng=random.Random(0), world=world)


def _stances(game, *, huangjin_fronts, geju):
    """三條戰線都設成 huangjin_fronts（黃巾聲勢就是它），割據設成 geju。"""
    w = game.state.world
    for front in ("yingru", "nanyang", "jizhou"):
        w.trends[front] = huangjin_fronts
    w.trends["geju"] = geju
    rules.recompute_trends(w, game.content)


# ── Task 1：六種結局、態勢比較、「可能的結局」──────────────────


@pytest.mark.parametrize("fronts, geju, expected", [
    (55, 20, "s1_turbans_hold"),     # 黃巾 55、官軍 45、豪強 20
    (40, 20, "s1_turbans_retreat"),  # 官軍 60 最高
    (50, 70, "s1_gentry"),           # 豪強 70 最高
    (50, 20, "s1_turbans_hold"),     # 官黃平手 50：清單裡黃巾坐地排前面（RF4）
    (90, 20, "s1_huangtian"),        # 黃巾聲勢 90：門檻那一種優先
    (10, 20, "s1_pacified"),
    (50, 90, "s1_warlords"),
])
def test_finale_compares_stances(on, fronts, geju, expected):
    game = _game(on)
    _stances(game, huangjin_fronts=fronts, geju=geju)
    assert world_mod.evaluate_ending(game.state, on).id == expected


def test_decisive_only_for_threshold_endings(on):
    game = _game(on)
    _stances(game, huangjin_fronts=60, geju=40)
    assert world_mod.decisive_ending(game.state, on) is None  # 比態勢的那三種不是決定性勝利
    _stances(game, huangjin_fronts=86, geju=40)
    assert world_mod.decisive_ending(game.state, on).id == "s1_huangtian"


def test_switch_off_endings_are_the_beta_ones(real):
    game = _game(real)
    assert world_mod.evaluate_ending(game.state, real).id == "hold"  # beta 主線 huangjin_line 撐到季末的那一個（跟以前一樣）
    assert world_mod.decisive_ending(game.state, real) is None
    assert "黃天當立" not in guide.quest_text(game.state, real)


def test_possible_endings_in_season_one_are_the_six(on):
    game = _game(on)
    text = guide.quest_text(game.state, on)
    assert "**可能的結局**" in text
    for title in ("黃天當立（無璽）", "黃巾平定", "群雄並起", "黃巾坐地", "黃巾敗退", "豪強坐大"):
        assert f"- {title}：" in text
    assert "黃巾稱霸" not in text and "潁川平定" not in text  # beta 的結局（T8 審查 M-4）
