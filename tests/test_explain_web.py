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


def test_notes_are_escaped():
    m = _main()
    m["action_notes"] = {"act:explore": "<b>x</b>"}
    page = run(m, "return H.pageJianghu();")
    assert "&lt;b&gt;x&lt;/b&gt;" in page
