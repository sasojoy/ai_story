"""行動列：出陣那一格寫今日剩幾次、探索那一格點了展開三顆（出陣探索與地盤設計第七節）。沒有 node 就略過。
這一份先放出陣那一半（PM 2026-10-14：Task 4 另外平行做，探索展開的部分等它合進來再補）。"""
from __future__ import annotations

import random

import pytest
from test_prologue_web import run

import server
import webharness
from conftest import classic_rules, no_conquest, real_content
from jianfa_kit import classic_explore
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


def _game(faction, at, classic=False):
    c = no_conquest(real_content("week7"))  # 出陣推線的舊規則（領地爭奪 PM 2026-10-22 起正式內容打開）
    classic_explore(c)  # 探索三選一（減法季探索一顆開著時只剩一顆）
    c.config.auto_open_first_season = True
    if classic:
        classic_rules(c)
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.faction, p.location, p.stamina = faction, at, float(c.config.stamina_max)
    return game


def _bar(game, **S):
    return run(server.main_view(game), "return H.actionBar(H.S.main);", S=S)


def test_the_sortie_cell_says_how_many_are_left():
    bar = _bar(_game("huang", "huangjin_camp"))
    assert "<b>出陣</b>" in bar and "今日 5 次" in bar and "零風險" in bar  # 格子只寫「出陣」（減法季批 1：四顆主鈕），攻守在出陣那一張卡上


def test_a_used_up_sortie_greys_out():
    game = _game("huang", "huangjin_camp")
    for _ in range(5):
        game.choose("act:train")
    bar = _bar(game)
    assert "今日已滿" in bar and 'data-id="act:train"' not in bar


def test_a_ranger_sees_the_sortie_cell_greyed():
    """FB-250：散人站在戰線上寫散人不能出陣；不在戰線的地方照舊寫「不在戰線」。"""
    from tianxia import sortie

    bar = _bar(_game(None, "changshe"))
    assert "<b>出陣</b>" in bar and sortie.RANGER_NOTE in bar and "不在戰線" not in bar
    bar = _bar(_game(None, "yingshui"))
    assert "<b>出陣</b>" in bar and "不在戰線" in bar


def test_the_explore_cell_unfolds_three_ways():
    game = _game(None, "yingshui")
    bar = _bar(game)
    assert 'data-act="wheel" data-key="explore"' in bar and "act-explore" not in bar
    assert 'data-id="explore:gather"' not in bar  # 收著時三顆不畫，也不掉進「此地還能做」（行動列底下那一行會提到「找素材」）
    bar = _bar(game, wheelSel="explore")
    assert 'class="card act-explore"' in bar
    assert all(f'data-id="explore:{m}"' in bar for m in ("gather", "seek", "sense"))


def test_a_tired_explorer_sees_the_cell_greyed():
    game = _game(None, "yingshui")
    game.state.player.stamina = 0
    bar = _bar(game, wheelSel="explore")
    assert 'data-key="explore"' in bar and "體力不夠" in bar and "act-explore" not in bar


def test_the_switches_off_keep_the_old_cells():
    bar = _bar(_game("huang", "huangjin_camp", classic=True))
    assert "<b>操練</b>" in bar and 'data-act="choose" data-id="act:explore"' in bar
