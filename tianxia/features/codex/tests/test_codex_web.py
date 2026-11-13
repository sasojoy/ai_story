"""江湖錄的網頁（web/codex.js）：假瀏覽器跑整支 app.js（test_prologue_web 那一套）。俠客頁多一顆「江湖錄」分頁（開關關著沒有）；
奇遇列表、點進去的下一步與走過的幕、重讀一幕、圖鑑四類；紅點三層（俠客分頁、江湖錄分頁、那一段那一格）。"""
from __future__ import annotations

import json

import pytest
from jianfa_kit import jianfa_game, ready
from test_codex import FORD, _start
from test_prologue_web import DRIVER as PROLOGUE_DRIVER

import server
import webharness
from tianxia.features.codex import view

pytestmark = [pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過"), pytest.mark.whole_content]
NAMES_START = 'wholeApp(["S", '
DRIVER = PROLOGUE_DRIVER.replace(NAMES_START, 'wholeApp(["S", "codexHtml", "dotAt", "pagePractice", ')


def run(m, script, S=None):
    return webharness.run(DRIVER, {"m": m, "script": script, "S": S or {}, "menxia": None, "stored": {}, "responses": {}})


@pytest.fixture
def walked():
    game = ready(jianfa_game(), side="guan", loc=FORD)
    game.content.config.codex.enabled = True
    game.sync(game.now)
    _start(game)
    game.choose("choice:0")
    return game


def test_the_tab_is_there_only_with_the_switch(walked):
    m = server.main_view(walked)
    assert m["codex"]["q"] is True
    out = run(m, "return [H.dotAt('practice'), H.dotAt('practice', 'codex')];")
    assert out == [True, True]
    m.pop("codex")
    out = run(m, "return H.dotAt('practice', 'codex');")
    assert out is False


def test_the_list_the_quest_and_the_reread(walked):
    m = server.main_view(walked)
    page = json.loads(json.dumps(view.page(walked)))
    html = run(m, "return H.codexHtml(m);", S={"heroTab": "codex", "cx": page, "cxSig": json.dumps(m["codex"]["fresh"]), "cxAt": 9e15})
    assert 'data-act="cx-open"' in html and "渡口帳" in html and 'class="dot"' in html and "cx-ghost" in html
    key = next(q["key"] for q in page["quests"]["on"] if q["line"] == "yesanniang")
    html = run(m, "return H.codexHtml(m);", S={"heroTab": "codex", "cx": page, "cxOpen": key, "cxSig": json.dumps(m["codex"]["fresh"]), "cxAt": 9e15})
    assert "下一步" in html and 'data-act="cx-read"' in html and "第一幕" in html and "結局" in html
    text = json.loads(json.dumps(view.scene(walked, 0)))
    html = run(m, "return H.codexHtml(m);", S={"heroTab": "codex", "cx": page, "cxRead": "i=0", "cxText": text})
    assert "cx-pick" in html and text["pick"] in html and text["after"][0] in html


def test_the_codex_book_four_kinds(walked):
    m = server.main_view(walked)
    page = json.loads(json.dumps(view.page(walked)))
    base = {"heroTab": "codex", "cx": page, "cxSeg": "tj", "cxSig": json.dumps(m["codex"]["fresh"]), "cxAt": 9e15}
    for cat, word in (("people", "位見過"), ("things", "寶物"), ("gods", "種神品"), ("ends", "種收法")):
        html = run(m, "return H.codexHtml(m);", S={**base, "cxCat": cat})
        assert word in html and 'data-act="cx-cat"' in html, cat
