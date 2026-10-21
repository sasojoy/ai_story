"""FB-664（練功入口對比圖開發回報，PM 2026-10-21 給號）：行動列「交友」灰著時，格子小字是整句「這裡沒有能說上話的人」
（10 個字、100 px），四格時兩頭被格子切掉。灰格小字最多六個字（一行約 60 px、10 px 的字）：格子寫短的，整句放行動列底下那一行
（actNotesHtml）。談滿了的交友（一類一顆開著時，單人地點的交友是 act:socialize 不是 call:）同一個毛病，一併改。沒有 node 就略過。
node 排不了版：這裡看格子裡寫什麼、底下那一行寫什麼；375／320 寬有沒有被切在瀏覽器裡量（Range 對格子的矩形），數字寫在試玩回饋 FB-664 那一列。
"""
from __future__ import annotations

import random
import re

import pytest
from test_prologue_web import run

import server
import webharness
from conftest import real_content
from tianxia import rules
from tianxia.engine import SOCIAL_NO_ONE, Game

pytestmark = [pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過"), pytest.mark.slow]


def _game(at, faction=None):
    content = real_content("weekend")  # 一類一顆開著（開季蓋章）
    content.config.auto_open_first_season = True
    game = Game.new(content, "沈浪", rng=random.Random(0))
    game.client = None
    p = game.state.player
    p.location, p.faction, p.stamina = at, faction, float(content.config.stamina_max)
    return game


def _bar(game):
    return run(server.main_view(game), "return H.actionBar(H.S.main);")


def _cell(bar, key):
    return re.search(rf'<button class="act-ink[^"]*" data-key="{key}".*?</button>', bar, re.S).group(0)


def _sub(cell):
    return re.search(r"</b><small>(.*?)</small>", cell).group(1)


def _width(text):
    """格子小字的寬（以一個漢字為 1）：英數與空白算半個。一行約 60 px、10 px 的字，放得下六個漢字（sortie.OUT_NOTE 的註解）。"""
    return sum(1 if ord(ch) > 0x2E80 else 0.5 for ch in text)


def test_the_social_cell_greyed_for_nobody_here_says_it_briefly_and_the_note_row_has_the_sentence():
    game = _game("yingchuan")
    social = next(o for o in game.options() if o.id == "act:socialize")
    assert not social.enabled and social.label == f"交友（{SOCIAL_NO_ONE}）"  # 前提：真的是這一句
    bar = _bar(game)
    cell = _cell(bar, "social")
    assert "<b>交友</b><small>沒有人</small>" in cell and SOCIAL_NO_ONE not in cell
    assert f"<p><b>交友</b>{SOCIAL_NO_ONE}。</p>" in bar  # 整句在行動列底下那一行，不是伺服器寫的那一句「結識這裡的人」
    assert "結識這裡的人" not in bar


def test_every_grey_cell_sub_fits_the_cell():
    """幾個真的會灰的地方：沒有人、名望還差、散人不能出陣、不在戰線。每一格小字都不超過六個字。"""
    for at in ("yingchuan", "changshe", "yingshui", "dajiangjun_fu", "luoyang_road", "wan_city"):
        bar = _bar(_game(at))
        for off in re.findall(r'<button class="act-ink off".*?</button>', bar, re.S):
            assert _width(_sub(off)) <= 6, (at, off)


def test_a_talked_out_single_figure_social_cell_says_so_briefly_too():
    """一類一顆開著時，單人地點談滿了的交友是灰的 act:socialize，括號裡整句帶換日的那一刻（跟 call: 談滿同一句）。孟津渡是真的會這樣的地方。"""
    game = _game("mengjin_ford")
    content = game.content
    p = game.state.player
    (cid,) = game._figures_here()
    p.flags.add(f"結識:{cid}")
    p.fortune = True
    p.talks_today[cid] = [rules.game_day(content, game.state.world), content.config.talk_turns_per_day]
    option = next(o for o in game.options() if o.id == "act:socialize")
    note = game._talked_out_note()
    assert not option.enabled and option.label == f"交友（{note}）"
    bar = _bar(game)
    assert "<b>交友</b><small>已談滿</small>" in _cell(bar, "social") and "00:00" not in _cell(bar, "social")
    assert f"<p><b>交友</b>{note}。</p>" in bar


def test_without_server_notes_the_grey_cell_still_draws_no_note_row():
    """伺服器沒給這一格的說明（舊版、序章裡是空的）：底下那一行照舊不畫（tests/test_explain_web.py::test_no_notes_without_server_notes 的約定），
    有沒有那一行由伺服器說了算，網頁只換句子；格子照樣寫短的。"""
    m = server.main_view(_game("yingchuan"))
    m["action_notes"] = {}
    m["status"]["howto_entry"] = False
    bar = run(m, "return H.actionBar(H.S.main);")
    assert "<b>交友</b><small>沒有人</small>" in _cell(bar, "social") and 'class="act-notes"' not in bar


def test_the_other_grey_reasons_keep_their_cells_and_notes():
    """名望還差：四格時放得下、格子照寫。FB-670（練功多一格，五格每格約 62 px、320 寬約 51 px，灰格小字最多四個字）起，
    「名望還差 15」在 320 寬會被切，改照這一張的做法：格子寫「名望不夠」，還差多少帶句號寫在底下那一行。
    新規則的其他灰格在 tests/test_fb670_practice_cell_web.py。"""
    game = _game("changshe")
    bar = _bar(game)
    assert "<b>交友</b><small>名望不夠</small>" in _cell(bar, "social") and "名望還差 15" not in _cell(bar, "social")
    assert "<p><b>交友</b>名望還差 15。</p>" in bar
