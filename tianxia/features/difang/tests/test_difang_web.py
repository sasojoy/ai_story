"""地方大事的畫面（web/difang.js）：眼下那一件、點開的那一層（三幕、墨痕不寫數字、這一幕能做的、收場）。假瀏覽器跑整支 app.js。"""
from __future__ import annotations

import pytest
from test_prologue_web import DRIVER as PROLOGUE_DRIVER

import webharness

pytestmark = [pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")]
DRIVER = PROLOGUE_DRIVER.replace('wholeApp(["S", ', 'wholeApp(["S", "difangEyeItem", "difangSheetHtml", ', 1)
ACTS = [{"name": "搬沙石", "line": "堤上缺沙包。", "state": "done"}, {"name": "擋亂民", "line": "你怎麼處置？", "state": "now"},
        {"name": "堤頂一戰", "line": "大家輪流上堤。", "state": "later"}]
WAYS = [{"id": f"difang:way:{i}", "label": f"潁水決堤・做法{i}", "enabled": True} for i in range(3)]


def _card(**kw):
    c = {"affair": "yingshui_dike", "title": "潁水決堤", "hook": "潁水漲到堤腳。", "region": "潁川汝南", "place": "潁水河畔", "art": "river",
         "status": "open", "act": 2, "acts": ACTS, "fill": 0.4, "foe": "翻江鰍", "heads": 17, "mine": True, "options": WAYS, "result": "", "last": ""}
    c.update(kw)
    return {"difang": {"card": c}, "options": []}


def _run(m, script):
    return webharness.run(DRIVER, {"m": m, "script": script, "S": {}, "menxia": None, "stored": {}, "responses": {}})


def test_the_eye_item_opens_the_sheet_and_names_the_act():
    it = _run(_card(), "return H.difangEyeItem(m);")
    assert it["title"] == "潁水決堤" and it["sub"] == "第二幕・擋亂民" and 'data-sheet="difang"' in it["attrs"]
    assert _run(_card(status="done"), "return H.difangEyeItem(m);") is None


def test_act_two_draws_three_ways_and_no_number_for_progress():
    html = _run(_card(), "return H.difangSheetHtml(m);")
    assert html.count('class="df-way"') == 3 and 'data-id="difang:way:0"' in html and "做法0" in html and "潁水決堤・" not in html
    assert "--w:40%" in html and "40" not in html.replace("--w:40%", "")
    assert "已有 17 人出力" in html and "你也在其中" in html


def test_a_used_way_says_so_instead_of_buttons():
    html = _run(_card(options=[{**w, "enabled": False} for w in WAYS]), "return H.difangSheetHtml(m);")
    assert "df-way" not in html and "出過手" in html


def test_act_three_strike_and_the_done_stamp():
    strike = [{"id": "difang:strike", "label": "潁水決堤・上前對付翻江鰍", "enabled": True}]
    acts = [{**a, "state": "done"} for a in ACTS[:2]] + [{**ACTS[2], "state": "now"}]
    html = _run(_card(act=3, acts=acts, options=strike), "return H.difangSheetHtml(m);")
    assert 'data-id="difang:strike"' in html and "上前對付翻江鰍" in html
    done = _run(_card(status="done", acts=[{**a, "state": "done"} for a in ACTS], result="堤保住了。", last="柳如煙", options=[]), "return H.difangSheetHtml(m);")
    assert "湊滿" in done and "堤保住了。" in done and "柳如煙" in done and "df-way" not in done


def test_the_act_shows_who_else_is_pitching_in_and_done_acts_list_names():
    acts = [{**ACTS[0], "who": ["柳如煙", "陸三刀"], "more": 0}, {**ACTS[1], "who": ["陸三刀", "柳如煙", "韓七"], "more": 4}, ACTS[2]]
    m = {**_card(acts=acts), "status": {"name": "陸三刀"}}
    html = _run(m, "return H.difangSheetHtml(m);")
    assert "也在出力" in html and html.count('<span class="df-pc') == 4 and 'class="df-pc me"' in html and "等 7 位" in html
    assert '<small class="df-names">柳如煙、陸三刀</small>' in html  # 湊齊的那一幕：齊字印旁一行名字


def test_away_shows_where_and_no_buttons():
    html = _run(_card(away=True), "return H.difangSheetHtml(m);")
    assert "這件事在潁川汝南" in html and "df-way" not in html and "df-go" not in html


def test_done_with_a_claim_draws_four_picks_and_the_eye_says_go_claim():
    claim = [{"id": f"difang:claim:m{i}", "name": n} for i, n in enumerate(["熔星髓", "天池露", "奔雷角", "歸墟壤"])]
    m = _card(status="done", acts=[{**a, "state": "done"} for a in ACTS], result="堤保住了。", options=[], claim=claim, marks=["義士"])
    html = _run(m, "return H.difangSheetHtml(m);")
    assert html.count('data-id="difang:claim:') == 4 and "挑一份謝禮" in html and '<span class="df-mark">義士</span>' in html
    it = _run(m, "return H.difangEyeItem(m);")
    assert it["btn"] == "去領" and it["sub"] == "湊滿了，挑一份謝禮"
    done = _run(_card(status="done", acts=[{**a, "state": "done"} for a in ACTS], options=[], claimed=True), "return H.difangSheetHtml(m);")
    assert "謝禮領過了" in done and "difang:claim" not in done
