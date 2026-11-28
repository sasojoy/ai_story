"""門派論劍的畫面（web/lunjian.js）：眼下那一件、點開的那一層（三個時刻寫字、報名鈕、對陣三排、賞）。假瀏覽器跑整支 app.js。"""
from __future__ import annotations

import pytest
import webharness
from test_prologue_web import DRIVER as PROLOGUE_DRIVER

pytestmark = [pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")]
DRIVER = PROLOGUE_DRIVER.replace('wholeApp(["S", ', 'wholeApp(["S", "lunjianEyeItem", "lunjianSheetHtml", ', 1)
SEATS_US = [{"name": "陸三刀", "me": True, "elder": False}, {"name": "丁", "me": False, "elder": False}, {"name": "慧明師兄", "me": False, "elder": True}]
SEATS_THEM = [{"name": "沈石師兄", "me": False, "elder": True}, {"name": "葉松崖師兄", "me": False, "elder": True}, {"name": "丙", "me": False, "elder": False}]
BOUTS = [{"seat": "先鋒", "tier": "落敗", "lines": ["一句。"]}, {"seat": "中堅", "tier": "險勝", "lines": []}, {"seat": "大將", "tier": "大勝", "lines": []}]


def _lj(**kw):
    c = {"title": "門派論劍", "week": 2, "sect": "白馬寺", "phase": "sign", "signed": False, "can_sign": True, "count": 1, "seats": 3,
         "draw": "第 2 週・週日 20:00", "fight": "第 2 週・週日 21:00", "match": None, "seal": "", "picks": 0, "boxes": 0, "top_boxes": 0,
         "moves": 0, "opened": [], "claim": [], "options": []}
    c.update(kw)
    opts = [{"id": "lunjian:sign", "label": "門派論劍・報名", "enabled": True}] if c["can_sign"] else []
    return {"lunjian": c, "options": opts}


def _run(m, script, S=None):
    return webharness.run(DRIVER, {"m": m, "script": script, "S": S or {}, "menxia": None, "stored": {}, "responses": {}})


def test_the_eye_item_follows_the_week():
    it = _run(_lj(), "return H.lunjianEyeItem(m);")
    assert it["seal"] == "論劍" and "截止報名" in it["sub"] and 'data-sheet="lunjian"' in it["attrs"]
    assert _run(_lj(signed=True), "return H.lunjianEyeItem(m);") is None
    match = {"us": "白馬寺", "them": "嵩陽劍廬", "seats_us": SEATS_US, "seats_them": SEATS_THEM, "bouts": BOUTS, "won": "us", "score": [2, 1]}
    it = _run(_lj(phase="fought", can_sign=False, match=match), "return H.lunjianEyeItem(m);")
    assert it["sub"] == "白馬寺勝了嵩陽劍廬"
    assert _run(_lj(boxes=1), "return H.lunjianEyeItem(m);")["sub"] == "有賞還沒拿"


def test_the_sheet_writes_the_times_and_the_sign_button():
    html = _run(_lj(), "return H.lunjianSheetHtml(m);")
    assert "報名" in html and "抽籤" in html and "開打" in html and 'data-id="lunjian:sign"' in html
    assert "週日 21:00" in html and "第 2 週・週日" not in html and "本門已有 1 人報名" in html
    assert "○" not in html and "●" not in html


def test_the_board_shows_three_rows_and_elders_are_marked():
    match = {"us": "白馬寺", "them": "嵩陽劍廬", "seats_us": SEATS_US, "seats_them": SEATS_THEM, "bouts": BOUTS, "won": "us", "score": [2, 1]}
    html = _run(_lj(phase="fought", can_sign=False, match=match, boxes=1, picks=1, claim=[{"id": "lunjian:claim:gang_4", "name": "熔星髓"}], seal="論劍三傑"),
                "return H.lunjianSheetHtml(m);")
    assert html.count('class="lj-row"') == 3 and "先鋒" in html and "大將" in html and "補位" in html
    assert "險勝" in html and 'data-id="lunjian:open"' in html and 'data-id="lunjian:claim:gang_4"' in html and "論劍三傑" in html
    assert "一句。" not in html
    opened = _run(_lj(phase="fought", can_sign=False, match=match), "return H.lunjianSheetHtml(m);", S={"ljBout": 0})
    assert "一句。" in opened


def test_before_the_fight_a_seated_player_sees_the_plan_box_and_the_foes():
    them = [dict(s, arts=["流雲劍"], lean="奇襲") for s in SEATS_THEM]
    match = {"us": "白馬寺", "them": "嵩陽劍廬", "seats_us": SEATS_US, "seats_them": them, "bouts": [], "won": "", "score": [0, 0], "hidden": True, "leader": True}
    plan = {"text": "", "seat": "先鋒", "chars": 30, "until": "第 2 週・週日 21:00",
            "presets": [{"id": "lunjian:preset:0", "text": "開場就搶攻。"}], "swaps": [{"id": "lunjian:swap:0", "a": "陸三刀", "b": "丁"}]}
    m = _lj(phase="drawn", can_sign=False, match=match, plan=plan)
    assert "定戰策" in _run(m, "return H.lunjianEyeItem(m);")["sub"]
    html = _run(m, "return H.lunjianSheetHtml(m);")
    assert 'id="lj-plan"' in html and 'maxlength="30"' in html and 'data-id="lunjian:preset:0"' in html and 'data-id="lunjian:swap:0"' in html
    assert "開打才知道" in html and "流雲劍" in html and "長於奇襲" in html and "lj-vs solo" in html


def test_after_the_fight_the_bout_quotes_both_plans_and_the_story():
    bouts = [dict(b, plans=["以靜制動", ""], story="陸三刀守得滴水不漏。", crowd="台下有人喝了一聲彩。") for b in BOUTS]
    match = {"us": "白馬寺", "them": "嵩陽劍廬", "seats_us": SEATS_US, "seats_them": SEATS_THEM, "bouts": bouts, "won": "us", "score": [2, 1]}
    html = _run(_lj(phase="fought", can_sign=False, match=match), "return H.lunjianSheetHtml(m);", S={"ljBout": 0})
    assert "陸三刀的戰策：以靜制動" in html and "沈石師兄沒定戰策" in html and "滴水不漏" in html and "喝了一聲彩" in html
    assert "一句。" not in html  # 有模型的過程就不寫引擎的回合
