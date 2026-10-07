"""玩法說明（explain-1）的網頁部分：行動列底下那幾行、體力條點開的說明、設定抽屜的「玩法說明」。
照 tests/test_prologue_web.py 的做法把整支 app.js 放進 node 的假瀏覽器，餵它真的引擎給的 /api/main；沒有 node 就略過。"""
from __future__ import annotations

import random
import re

import pytest
from test_prologue_web import run

import server
import webharness
from conftest import real_content
from tianxia.engine import Game

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


def _main(game=None, **over):
    if game is None:
        content = real_content()
        content.config.auto_open_first_season = True
        game = Game.new(content, "沈浪", rng=random.Random(0))  # 不走序章：跟略過序章的人一樣站在起點
        game.client = None
    m = server.main_view(game)
    m.update(over)
    return m


# ── 行動列底下那幾行 ─────────────────────────────────────────


def test_the_notes_sit_under_the_action_row_in_cell_order():
    m = _main()
    notes = m["action_notes"]
    assert notes["act:explore"].startswith("這裡")  # 伺服器照規則寫好的
    page = run(m, "return H.pageJianghu();")
    bar_end = page.index("</div>", page.index('class="act-bar"'))
    block = re.search(r'<div class="act-notes">(.*?)</div>', page)
    assert block and page.index('class="act-notes"') > page.index('class="act-bar"')
    rows = re.findall(r"<p><b>(.*?)</b>(.*?)</p>", block.group(1))
    assert rows[0] == ("探索", notes["act:explore"])  # 照格子的順序、冠格子上的名字
    for name, text in rows:
        assert text in notes.values() and name in ("探索", "遊歷", "操練", "交友", "求見")
    assert page.index('class="act-notes"') > bar_end  # 在行動列後面：不推動「剛剛」、場景與整排行動


def test_the_notes_give_way_to_the_move_card():
    m = _main()
    page = run(m, "return H.pageJianghu();", S={"wheelSel": "move"})
    assert 'class="card act-move"' in page and 'class="act-notes"' not in page


def test_the_notes_give_way_when_the_guide_points_into_the_here_fold():
    """入伍段要按的鈕收在「此地還能做」裡（guide.glow）：說明不畫，不把那一顆往下推。"""
    m = _main()
    extra = next(o["id"] for o in m["options"] if o["id"].startswith("move:"))  # 隨便一顆不在行動列格子裡的（這裡用前往）
    m["options"] = [o for o in m["options"] if not o["id"].startswith("move:")] + [{"id": "act:duty", "label": "巡哨", "enabled": True}]
    m["guide"] = {"glow": ["act:duty"]}
    bar = run(m, "return H.actionBar(H.S.main);")
    assert 'class="act-notes"' not in bar and "此地還能做" in bar
    m["guide"] = {"glow": [extra]}  # 發光的不在摺疊裡：說明照畫
    assert 'class="act-notes"' in run(m, "return H.actionBar(H.S.main);")


def test_no_notes_without_server_notes():
    """伺服器沒給（舊版、序章裡是空的）：不畫那一塊。"""
    m = _main()
    m.pop("action_notes")
    assert 'class="act-notes"' not in run(m, "return H.pageJianghu();")
    m["action_notes"] = {}
    assert 'class="act-notes"' not in run(m, "return H.pageJianghu();")


def test_the_conversation_view_shows_the_bond(content):
    """談話畫面（場景卡）名字旁寫著情誼：伺服器把引擎的 Markdown 轉成 HTML，網頁照放（explain-1 第二項）。"""
    from unittest import mock

    from test_engine import FAKE_TURN

    from tianxia import companion_agent

    content.characters["mate"].deep_interaction = True
    game = Game.new(content, "沈浪", rng=random.Random(0))
    game.state.player.affinities["mate"] = 12
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        game.choose("act:socialize")
    page = run(_main(game), "return H.pageJianghu();")
    assert re.search(r'<section class="card scene"><p><strong>韓鐵</strong>（情誼 12）</p>', page)


# ── 點體力條看體力怎麼回 ─────────────────────────────────────────


def test_tapping_the_stamina_bar_opens_the_help_and_the_pill_keeps_its_own_target():
    m = _main()
    help_lines = m["status"]["stamina_help"]
    assert help_lines and m["status"]["pills"]  # 新角色有內測贈送的丹：體力條上有那顆鈕
    closed = run(m, "return H.topHtml();")
    bar = re.search(r'<div class="bar stam"[^>]*>', closed).group(0)
    assert 'data-act="stam-help"' in bar and 'aria-expanded="false"' in bar
    # 丹的鈕在體力條裡面、自己帶 data-act="pill"：點它時 closest("[data-act]") 先碰到它，不會走到攤開說明
    inside = closed[closed.index(bar):closed.index("</div>", closed.index(bar))]
    assert 'class="pill-btn" data-act="pill"' in inside
    assert 'class="more-stats stam-help"' not in closed
    out = run(m, """return (async () => {
      const el = { dataset: { act: "stam-help" }, classList: { contains: () => false } };
      await T.docListeners.click[0]({ target: { closest: () => el } });
      const opened = H.topHtml();
      const first = H.S.stamOpen;
      await T.docListeners.click[0]({ target: { closest: () => el } });
      return { first, opened, second: H.S.stamOpen };
    })();""")
    assert out["first"] is True and out["second"] is False
    block = re.search(r'<div class="more-stats stam-help" id="stam-help">(.*?)</div>', out["opened"]).group(1)
    assert re.findall(r"<p>(.*?)</p>", block) == help_lines  # 伺服器寫好的幾行，一行一段
    assert 'aria-expanded="true"' in out["opened"]


def test_the_pill_click_still_takes_a_pill():
    m = _main()
    out = run(m, """return (async () => {
      const el = { dataset: { act: "pill" }, classList: { contains: () => false } };
      await T.docListeners.click[0]({ target: { closest: () => el } });
      return { calls: T.calls.map((c) => c[0]), open: H.S.stamOpen };
    })();""", responses={"/api/do/pill": {"main": m, "message": ""}})
    assert any(url.startswith("/api/do/pill") for url in out["calls"]) and out["open"] is False


def test_no_help_from_an_old_server_means_a_plain_bar():
    m = _main()
    m["status"].pop("stamina_help")
    bar = re.search(r'<div class="bar stam"[^>]*>', run(m, "return H.topHtml();")).group(0)
    assert "data-act" not in bar


def test_the_help_lines_are_escaped():
    m = _main()
    m["status"]["stamina_help"] = ["<b>x</b>"]
    assert "&lt;b&gt;x&lt;/b&gt;" in run(m, "return H.topHtml();", S={"stamOpen": True})


def test_notes_are_escaped():
    m = _main()
    m["action_notes"] = {"act:explore": "<b>x</b>"}
    page = run(m, "return H.pageJianghu();")
    assert "&lt;b&gt;x&lt;/b&gt;" in page
