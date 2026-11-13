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
DRIVER = PROLOGUE_DRIVER.replace(NAMES_START, 'wholeApp(["S", "codexHtml", "codexTrackHtml", "codexWhyHtml", "wkTugHtml", "dotAt", "pagePractice", ')


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


def test_the_tracker_line_and_its_drawer(walked):
    walked.content.config.codex.tracker = True
    m = server.main_view(walked)
    assert m["codex"]["track"]
    parts = [{"key": "orders", "name": "軍令", "seal": "令", "n": 1, "html": "<section>令</section>", "line": "守住長社", "now": 1, "i": 0}]
    html = run(m, "return H.codexTrackHtml(m, parts);".replace("parts", json.dumps(parts)))
    n = len(m["codex"]["track"]) + 1  # 奇事、主線＋那一道軍令
    assert 'class="cx-track"' in html and f">{n}</em>" in html and "class=\"new\"" in html and "cx-tk-sheet" not in html
    html = run(m, "return H.codexTrackHtml(m, parts);".replace("parts", json.dumps(parts)), S={"cxTk": True})
    assert "cx-tk-sheet" in html and html.count('class="cx-tk-go"') == n and "守住長社" in html and 'data-duty="1"' in html
    m["codex"].pop("track")
    assert run(m, "return H.codexTrackHtml(m, []);") == ""


def test_things_still_waiting_fold_under_one_line_and_have_no_go(walked):
    walked.content.config.codex.tracker = True
    m = server.main_view(walked)
    active = [t for t in m["codex"]["track"] if not t["wait"]]
    m["codex"]["track"].append({"key": "1:ch_x", "line": "ch_x", "kind": "主線", "title": "長社火攻", "what": "這一回做完了，等「長社火攻」",
                                "until": "第 2 週・週三 20:00", "wait": True, "ready": True, "loc": None})
    parts = [{"key": "plan", "name": "盤算", "seal": "謀", "n": "", "html": "<section>謀</section>", "line": "波才要圍長社", "now": 0, "i": 0}]
    html = run(m, f"return H.codexTrackHtml(m, {json.dumps(parts)});", S={"cxTk": True})
    assert f">{len(active)}</em>" in html  # 在等的不算進印上的數字
    assert html.count('class="cx-tk-go"') == len(active) and "在等的 2 件" in html and "長社火攻" not in html
    html = run(m, f"return H.codexTrackHtml(m, {json.dumps(parts)});", S={"cxTk": True, "cxTkWait": True})
    waits = html.split('class="cx-tk-waits"')[1]
    assert "長社火攻" in waits and "第 2 週・週三 20:00" in waits and "波才要圍長社" in waits and "cx-tk-go" not in waits


def test_the_page_top_keeps_only_the_tracker_line(walked):
    walked.content.config.codex.tracker = True
    m = server.main_view(walked)
    if not m.get("week_card"):
        pytest.skip("這一局沒有本週卡")
    key = m["week_card"]["label"] + m["week_card"]["when"]
    fresh = run(m, "return H.pageJianghu();")
    assert 'class="cx-track"' in fresh and 'class="card wk-box' in fresh  # 這一週還沒看過：本週卡露一次
    seen = run(m, "return H.pageJianghu();", S={"cxTkMemo": {"seen": [], "week": key}})
    assert 'class="cx-track"' in seen and "wk-box" not in seen and "jh-hints" not in seen and "ch-card" not in seen
    assert ('class="cx-tug"' in seen) == bool(m["week_card"].get("sides"))  # 收起來還有一條細的兩軍態勢
    assert 'class="cx-tug"' not in fresh  # 本週卡露著就不重複
    m["codex"].pop("track")  # 「進行中」關著：照舊
    old = run(m, "return H.pageJianghu();", S={"cxTkMemo": {"seen": [], "week": key}})
    assert "cx-track" not in old and "cx-tug" not in old and "wk-box" in old


def test_the_sides_tug_is_still_one_tap_away_when_the_week_card_folds(walked):
    walked.content.config.codex.tracker = True
    m = server.main_view(walked)
    if not (m.get("week_card") and m["week_card"].get("sides")):
        pytest.skip("這一局沒有兩軍態勢")
    tug = run(m, "return H.wkTugHtml(m, m.week_card);")
    assert tug
    sheet = run(m, "return H.codexWhyHtml(m);", S={"cxWhy": True})
    assert tug in sheet  # 本週卡收起來了，清單最底下那一顆拉起來的那一層最上面就是兩軍態勢


def test_scenes_walked_before_the_book_opened_show_their_names(walked):
    b = walked.state.player.codex
    b.scenes.clear()  # 當作開關打開之前就走過第一幕
    q = next(x for x in view.quests(walked)["on"] if x["line"] == "yesanniang")
    first = q["scenes"][0]
    assert first["i"] is None and first["title"] == walked.content.events["yesanniang_1"].title and first["lost"] == view.LOST
    page = json.loads(json.dumps(view.page(walked)))
    m = server.main_view(walked)
    html = run(m, "return H.codexHtml(m);", S={"heroTab": "codex", "cx": page, "cxOpen": q["key"], "cxSig": json.dumps(m["codex"]["fresh"]), "cxAt": 9e15})
    assert "cx-act lost" in html and view.LOST in html and first["title"] in html
    assert html.count("？？") == 1  # 只有還沒到的那一幕是剪影


def test_quest_rows_are_not_listed_twice(walked):
    walked.content.config.codex.tracker = True
    m = server.main_view(walked)
    m["week_card"] = None
    m["options"] = list(m["options"]) + [{"id": "story:yesanniang", "label": "渡口帳（未了之事：到北邙山）", "enabled": False, "note": ""}]
    on = run(m, "return H.pageJianghu();")
    m["codex"].pop("track")
    off = run(m, "return H.pageJianghu();")
    assert "quest-row" not in on and "quest-row" in off
