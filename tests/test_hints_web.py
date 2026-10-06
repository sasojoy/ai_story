"""碰到才說的網頁那一半（新手引導計畫三 Task 2；Task 1 審查 I-1）。

提示是在動作做完的那一下上框、記說過、記進江湖紀錄的；修練失敗、改練、合成、熔煉這些動作都在修練頁、煉製頁做，可是網頁以前只在江湖頁畫對話框
（修練、煉製頁只在序章畫師父）。這裡把整支 app.js 放進 node 的假瀏覽器（見 tests/test_prologue_web.py 的 DRIVER），餵**真的**引擎給的
/api/main 與 /api/menxia：提示的框要畫在修練頁與煉製頁最上面、「知道了」按下去框就沒了；說書人的步驟、結語、入伍段的框仍只在江湖頁。
沒有 node 就略過。"""
from __future__ import annotations

import random

import pytest
from test_prologue_web import run

import server
import webharness
from tianxia import guide
from tianxia.engine import Game

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")

GUIDE_CARD = 'class="card guide"'
ACK = 'data-act="guide-ack"'


@pytest.fixture
def game(hints_content, world):
    game = Game.new(hints_content, "沈浪", rng=random.Random(0), world=world)
    game.skip_tutorial()
    return game


def views(game):
    return server.main_view(game), server.menxia_view(game)


def test_a_hint_is_drawn_at_the_top_of_the_practice_and_craft_pages(game):
    game._hint("h_merge")
    m, x = views(game)
    assert m["guide"]["hint"] is True
    for call in ("H.pagePractice()", "H.pageCraft()"):
        page = run(m, f"return {call};", menxia=x)
        assert GUIDE_CARD in page and ACK in page and "意境可以合。" in page, call
        assert page.index(GUIDE_CARD) < page.index('id="mx-msg"'), call  # 在頁面最上面


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


def test_got_it_on_the_practice_page_clears_the_box(game):
    """修練頁上按「知道了」：送 guide_ack、換上伺服器回的新畫面，框就沒了（點的是頁面上真的那顆鈕的 data-act）。"""
    game._hint("h_merge")
    m, x = views(game)
    game.guide_ack()
    after = server.main_view(game)
    assert after["guide"] is None
    script = """return (async () => {
      H.S.tab = "practice";
      const before = H.pagePractice();
      const act = (before.match(/data-act="(guide-ack)"/) || [])[1];
      const el = { dataset: { act }, classList: { contains: () => false } };
      await T.docListeners.click[0]({ target: { closest: () => el } });
      return { before: before.includes('class="card guide"'), act, guide: H.S.main.guide, after: H.pagePractice(),
               calls: T.calls.map((c) => c[0]) };
    })();"""
    out = run(m, script, menxia=x, responses={"/api/do/guide_ack": {"main": after}})
    assert out["before"] is True and out["act"] == "guide-ack"
    assert out["calls"] == ["/api/do/guide_ack"] and out["guide"] is None
    assert GUIDE_CARD not in out["after"]


def test_a_second_hint_takes_the_place_of_the_first_on_the_craft_page(game):
    game._hint("h_merge")
    game._hint("h_lose")
    game.guide_ack()
    m, x = views(game)
    assert m["guide"]["key"] == "h_lose"
    page = run(m, "return H.pageCraft();", menxia=x)
    assert "打不過就回去練。" in page and "意境可以合。" not in page
