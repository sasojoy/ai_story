"""碰到才說的網頁那一半（新手引導計畫三 Task 2；Task 1 審查 I-1）。

提示是在動作做完的那一下上框、記說過、記進江湖紀錄的；修練失敗、改練、合成、熔煉這些動作都在修練頁、煉製頁做，可是網頁以前只在江湖頁畫對話框
（修練、煉製頁只在序章畫師父）。這裡把整支 app.js 放進 node 的假瀏覽器（見 tests/web/test_prologue_web.py 的 DRIVER），餵**真的**引擎給的
/api/main 與 /api/menxia：提示的框要畫在修練頁與煉製頁最上面、「知道了」按下去框就沒了；說書人的步驟、結語、入伍段的框仍只在江湖頁。
沒有 node 就略過。"""
from __future__ import annotations

import random

import pytest
from test_prologue_web import run

import server
import webharness
from tianxia.features.guide import rules as guide
from tianxia.engine import Game

pytestmark = [pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過"), pytest.mark.whole_content]

GUIDE_CARD = 'class="card guide"'


@pytest.fixture
def game(hints_content, world):
    game = Game.new(hints_content, "沈浪", rng=random.Random(0), world=world)
    game.skip_tutorial()
    return game


def views(game):
    return server.main_view(game), server.menxia_view(game)


def test_a_hint_is_drawn_on_the_jianghu_page_only(game):
    """碰到才說的提示（「想起師父說過」）只畫在江湖頁，俠客頁的修練、煉製不再各掛一次（Joy 2026-11-08 UI 手感乙批 1-4 選「只留江湖頁」）。"""
    game._hint("h_merge")
    m, x = views(game)
    assert m["guide"]["hint"] is True
    for call in ("H.pagePractice()", "H.pageCraft()"):
        assert GUIDE_CARD not in run(m, f"return {call};", menxia=x), call
    page = run(m, "return H.pageJianghu();", menxia=x)
    assert ("意境可以合。" in page or "data-act=\"guide-open\"" in page), page[:400]


def test_no_hint_no_box_on_those_pages(game):
    m, x = views(game)
    assert m["guide"] is None
    for call in ("H.pagePractice()", "H.pageCraft()"):
        assert GUIDE_CARD not in run(m, f"return {call};", menxia=x), call


def test_the_other_boxes_stay_on_the_jianghu_page_only(hints_content, world):
    """說書人的步驟、結語、入伍段的結尾：不是提示，修練頁與煉製頁照舊不畫（只有序章裡師父在那兩頁）。"""
    step = Game.new(hints_content, "沈浪", rng=random.Random(0), world=world)
    outro = Game.new(hints_content, "乙", rng=random.Random(0), world=world)
    outro.state.player.tutorial_step = len(guide.steps(outro.state, outro.content))
    outro.state.player.guide_outro = True
    for game, key in ((step, "s1"), (outro, "outro")):
        m, x = views(game)
        assert m["guide"]["key"] == key and not m["guide"].get("hint")
        for call in ("H.pagePractice()", "H.pageCraft()"):
            assert GUIDE_CARD not in run(m, f"return {call};", menxia=x), (key, call)
        assert GUIDE_CARD in run(m, "return H.pageJianghu();", menxia=x), key


