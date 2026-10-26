"""功能照週解鎖與三週主題的網頁部分（減法季批 5，整合設計 6.3、6.6、6.8）：本週卡灰線底下那一行（第 3 週離贏還差多少、功能開了、45 級）、
「為什麼」裡哪幾樣第 2 週開、四格探索那一格的小字「城裡多事」、輿圖天下層抽屜的同一句。照 tests/test_week_card_web.py 的做法把整支網頁放進
node 的假瀏覽器；沒有 node 就略過。"""
from __future__ import annotations

import random

import pytest
from conftest import real_content
from test_prologue_web import run
from test_world_map_web import run as run_map

import server
import webharness
from tianxia import week_unlock
from tianxia.engine import Game

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")

GAP = "官軍離平定還差 12，黃巾離當立還差 28。"
UNLOCK = week_unlock.CARD.format(names="打造、擂台、自創、懸賞榜")
LOCKED = week_unlock.LOCKED.format(names="打造、擂台、自創、懸賞榜", when="第 2 段")


def _game():
    content = real_content("week7")
    content.config.auto_open_first_season = True
    game = Game.new(content, "沈浪", rng=random.Random(0))
    game.client = None
    return game


def _main(**card):
    m = server.main_view(_game())
    m["week_card"] = {**m["week_card"], **card}
    return m


def _why(m):
    return {"wkOpen": {"key": m["week_card"]["label"] + m["week_card"]["when"], "id": "why"}}


def test_the_strip_gets_a_note_line_only_when_there_is_something_to_say():
    plain = run(_main(gap=None, unlock=None, cap=None), "return H.weekCardHtml(H.S.main);")
    assert "wk-note" not in plain
    html = run(_main(gap=GAP, unlock=UNLOCK, cap=week_unlock.CAP_NOTE), "return H.weekCardHtml(H.S.main);")
    note = html[html.index('<p data-wk class="wk-note">'):]
    note = note[: note.index("</p>")]
    assert GAP in note and UNLOCK in note and week_unlock.CAP_NOTE in note
    assert html.index("wk-card") < html.index("wk-strip") < html.index("wk-note")  # 灰線底下（「眼下要事」排在灰線上面）


def test_why_lists_what_opens_in_week_two():
    m = _main(locked=LOCKED)
    panel = run(m, "return H.weekCardHtml(H.S.main);", S=_why(m))
    assert f'<p class="wk-locked">{LOCKED}</p>' in panel
    m = _main(locked=None)
    assert "wk-locked" not in run(m, "return H.weekCardHtml(H.S.main);", S=_why(m))


def test_the_explore_cell_says_what_this_place_mostly_gives():
    m = server.main_view(_game())
    assert m["mostly"] == "城裡多事"
    bar = run(m, "return H.actionBar(H.S.main);")
    cell = bar[bar.index('data-key="explore"'):]
    cell = cell[: cell.index("</button>")]
    assert "<small>城裡多事</small>" in cell
    del m["mostly"]  # 在路上沒有：照以前的小字
    bar = run(m, "return H.actionBar(H.S.main);")
    cell = bar[bar.index('data-key="explore"'):]
    assert "城裡多事" not in cell[: cell.index("</button>")]


def test_the_world_drawer_writes_the_same_gap_sentence():
    game = _game()
    st = game.map_state()
    assert st["gap"] is None
    assert "m-gap" not in run_map(game, "return H.worldDrawerHtml(H.S.mapBase, H.S.mapState);", st=st, mapDrawer="half")
    st["gap"] = GAP
    full = run_map(game, "return H.worldDrawerHtml(H.S.mapBase, H.S.mapState);", st=st, mapDrawer="half")
    assert f'<p class="m-gap">{GAP}</p>' in full
