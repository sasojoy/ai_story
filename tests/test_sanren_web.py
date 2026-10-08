"""散人玩法的網頁那一半：狀態列展開時的遊俠名號（俠名、下一階、這一階的好處）與江湖頁的懸賞卡（手上揭了的、看懸賞榜）。
餵真的引擎給的 /api/main 給 app.js（tests/test_prologue_web.py 的假瀏覽器）。沒有node 就略過。"""
from __future__ import annotations

import pytest
from test_bounties import _do, _post, setup  # noqa: F401  （setup 是 fixture）
from test_prologue_web import run

import server
import webharness
from tianxia.characters import CharacterStore

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


def _view(content, world, name):
    return _do(content, world, name, server.main_view)[0]


def test_the_expanded_name_shows_the_ranger_ladder(setup):  # noqa: F811
    content, world = setup
    state = CharacterStore(world.db).load("丙")
    state.player.ranger_good = 7  # 第 1 階（5），再 8 點到第 2 階（15）
    CharacterStore(world.db).save(state)
    m = _view(content, world, "丙")
    top = run(m, "return H.topHtml();", S={"showMore": True})
    assert "江湖遊俠" in top and "俠名 7，再攢 8 點可稱「一方豪俠」" in top and "求見門檻 -3" in top
    assert "who-ranger" not in run(m, "return H.topHtml();")  # 收起來只有頭銜那一行
    assert "who-ranger" not in run(_view(content, world, "甲"), "return H.topHtml();", S={"showMore": True})  # 陣營的人凍結：不畫


def test_the_bounty_card_lists_what_you_hold_and_opens_the_board(setup):  # noqa: F811
    content, world = setup
    assert "🪧 懸賞" not in run(_view(content, world, "丙"), "return H.pageJianghu();")  # 沒揭就不畫
    b = _post(world, kind="scout", faction="guan", silver=10, deeds=2, location="lake")
    _do(content, world, "丙", lambda g: g.choose("act:bounties"))
    _do(content, world, "丙", lambda g: g.choose(f"bounty:take:{b.id}"))
    _do(content, world, "丙", lambda g: g.choose("bounty:back"))
    page = run(_view(content, world, "丙"), "return H.pageJianghu();")
    assert "🪧 懸賞（1）" in page and "打探・湖邊" in page and "到湖邊探索一次" in page and "俠名 +2" in page
    assert 'data-act="choose" data-id="act:bounties"' in page.split("🪧")[1]  # 在城鎮：卡底下開得了懸賞榜
    assert page.index("🪧") > page.index('data-id="act:rest"')  # 排在行動列下面，不擠第一屏
    shut = run(_view(content, world, "丙"), "return H.pageJianghu();", S={"bountyShut": b.id})
    assert '<details class="fold bounties" data-key="' + b.id + '" >' in shut  # 收起來照手上那幾張記住

    state = CharacterStore(world.db).load("丙")
    state.player.location = "lake"
    CharacterStore(world.db).save(state)
    away = run(_view(content, world, "丙"), "return H.pageJianghu();")
    assert "到城鎮的懸賞榜前" in away and 'data-id="act:bounties"' not in away


def test_with_the_board_open_the_card_points_nowhere(setup):  # noqa: F811
    content, world = setup
    b = _post(world, kind="scout", faction="guan", silver=10, deeds=2, location="lake")
    _do(content, world, "丙", lambda g: g.choose("act:bounties"))
    _do(content, world, "丙", lambda g: g.choose(f"bounty:take:{b.id}"))
    card = run(_view(content, world, "丙"), "return H.pageJianghu();").split("🪧")[1]
    assert "bounty-foot" not in card.split("</details>")[0]  # 選單就是懸賞榜：不再叫人去看榜
