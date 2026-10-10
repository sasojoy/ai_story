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


POLL = """return (async () => {
  H.S.tab = TAB; H.renderPage();
  const page = T.els.page;
  const drawn = () => page.innerHTML.includes('class="card guide"');
  const first = drawn();
  // 一次輪詢：拿到有提示的新畫面（setMain 之後 refreshPage，跟 poll() 一樣）；上一次畫的頁面清掉，看重畫了沒有
  const was = H.S.main;
  H.setMain(H.S.next);
  await H.refreshPage(was);
  const arrived = drawn();
  // 再一次輪詢，畫面沒有變：不重畫（輪詢每十秒一次，不能每次都整頁重畫）
  page.innerHTML = "";
  const again = H.S.main;
  H.setMain(JSON.parse(JSON.stringify(H.S.main)));
  await H.refreshPage(again);
  const untouched = page.innerHTML === "";
  return { first, arrived, untouched, calls: T.calls.map((c) => c[0]) };
})();"""


@pytest.mark.parametrize("tab", ["practice", "craft"])
def test_a_hint_that_arrives_with_a_poll_is_drawn_on_the_practice_and_craft_pages(game, tab):
    """輪詢（同步）才排進來的提示（大事揭曉、決戰集結、抵達……）也要畫：伺服器在輪詢裡就把它記成說過、寫進江湖紀錄了，
    頁面卻只在修練、煉製的資料變了才重畫，框就不出現，直到下一次動作或切分頁（Task 2 審查 I-1）。沒變的輪詢不重畫。"""
    before, x = views(game)
    game._hint("h_merge")
    after = server.main_view(game)
    assert before["guide"] is None and after["guide"]["hint"] is True
    out = run(before, POLL.replace("TAB", repr(tab)), menxia=x, S={"next": after}, responses={"/api/menxia": x})
    assert out["first"] is False  # 一開始沒有提示
    assert out["arrived"] is True  # 輪詢帶來提示：頁面重畫、框出現
    assert out["untouched"] is True  # 同一份畫面再輪詢一次：不重畫
    # 煉製頁重畫時另問一次說明與「現在合得出來的」（/api/forge_line，企劃者 2026-10-10）；沒變的那一次不問
    assert out["calls"] == (["/api/menxia", "/api/forge_line", "/api/menxia"] if tab == "craft" else ["/api/menxia", "/api/menxia"])


def test_a_poll_that_takes_the_hint_away_redraws_too(game):
    """另一個分頁按了「知道了」之後，這一頁的輪詢拿到沒有提示的畫面：框要收掉。"""
    game._hint("h_merge")
    with_hint, x = views(game)
    game.guide_ack()
    gone = server.main_view(game)
    script = """return (async () => {
      H.S.tab = "practice"; H.renderPage();
      const had = T.els.page.innerHTML.includes('class="card guide"');
      const was = H.S.main;
      H.setMain(H.S.next);
      await H.refreshPage(was);
      return { had, has: T.els.page.innerHTML.includes('class="card guide"') };
    })();"""
    out = run(with_hint, script, menxia=x, S={"next": gone}, responses={"/api/menxia": x})
    assert out == {"had": True, "has": False}


def test_a_second_hint_takes_the_place_of_the_first_on_the_craft_page(game):
    game._hint("h_merge")
    game._hint("h_lose")
    game.guide_ack()
    m, x = views(game)
    assert m["guide"]["key"] == "h_lose"
    page = run(m, "return H.pageCraft();", menxia=x)
    assert "打不過就回去練。" in page and "意境可以合。" not in page
