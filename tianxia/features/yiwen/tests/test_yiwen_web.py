"""異聞的網頁（web/yiwen.js）：假瀏覽器跑整支 app.js（test_prologue_web 那一套），直接叫三個畫法（撞見卡、每一幕、收尾卡）。
資料照 main.yiwen.card 的形狀手寫；玩家的原話一律經 esc() 才進 HTML。"""
from __future__ import annotations

import pytest
from test_prologue_web import DRIVER as PROLOGUE_DRIVER

import webharness

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
NAMES_START = 'wholeApp(["S", '
DRIVER = PROLOGUE_DRIVER.replace(NAMES_START, 'wholeApp(["S", "yiwenCard", "yiwenScene", "yiwenClose", ')
BAD = '<img src=x onerror="alert(1)">&\'"'


def run(script, S=None):
    return webharness.run(DRIVER, {"m": None, "script": script, "S": S or {}, "menxia": None, "stored": {}, "responses": {}})


def _card(**over):
    card = {
        "opening": "fog_figure", "tale": 3, "title": "霧裡的身影", "place": "p", "place_name": "汝南荒野", "kind": "wild", "kind_word": "野",
        "mark": "trail", "frame": "這片荒地有人走過，草間的舊腳印還在。你踩了上去。", "hook": "前面濃霧瀰漫，隱約看到一個身影⋯",
        "walkers": 4, "depth": 1, "node": 0, "scenes": [],
        "choices": [{"i": 0, "label": "官軍", "state": "walked", "by": "陸三刀", "steps": 4},
                    {"i": 1, "label": "黃巾", "state": "locked", "by": "", "steps": 0, "note": "這條路還沒開"},
                    {"i": 2, "label": "迷路的老人", "state": "free", "by": "", "steps": 0}],
        "typed": {"state": "off", "max": 30, "tries_left": 3}, "done": False, "close": "", "gains": "",
    }
    card.update(over)
    return card


def _scene(**over):
    sc = {"node": 7, "depth": 1, "pick": "官軍", "who": "陸三刀", "zhupi": True, "zhupi_text": "——當初陸三刀一口咬定，那是「官軍」。",
          "echo": "你以為是官軍。", "luck": "逆", "text": ["這一段說書的記不真了。"], "summary": "", "hidden": "", "replay": True}
    sc.update(over)
    return sc


def test_card_draws_hook_frame_and_three_picks():
    html = run(f"return H.yiwenCard({_js(_card())});")
    assert "霧裡的身影" in html and "前面濃霧瀰漫" in html and "舊腳印還在" in html and "汝南荒野" in html
    assert html.count('data-act="yw-step"') == 3 and "已有 4 人走過" in html
    assert 'data-id="yiwen:drop"' in html


def test_zhupi_and_luck_seal():
    html = run(f"return H.yiwenScene({_js(_scene())});")
    assert "當初陸三刀一口咬定" in html and 'class="yw-luck"' in html and ">逆<" in html
    plain = run(f"return H.yiwenScene({_js(_scene(zhupi=False, zhupi_text='', depth=2))});")
    assert "你以為是官軍。" in plain and "一口咬定" not in plain


def test_choice_small_lines():
    html = run(f"return H.yiwenCard({_js(_card())});")
    assert "陸三刀走過・足跡 4" in html and "這條路還沒開" in html and "沒人走過" in html
    assert html.count("disabled") >= 2  # 鎖著那一顆與自己說那一格


def test_card_null_draws_nothing():
    assert run("return H.yiwenCard(null);") == ""
    done = run(f"return H.yiwenCard({_js(_card(done=True, close='醒木一響。', choices=[]))});", S={"ywLast": ["醒木一響。", "銀兩 +20"]})
    assert "醒木一響。" in done and "銀兩 +20" in done and 'data-act="yw-step"' not in done


def test_player_words_are_escaped():
    card = _card(scenes=[_scene(zhupi_text=BAD, pick=BAD, who=BAD, text=[BAD])],
                 choices=[{"i": 0, "label": BAD, "state": "walked", "by": BAD, "steps": 1}])
    html = run(f"return H.yiwenCard({_js(card)});")
    assert "<img" not in html and "&lt;img" in html and "&amp;" in html
    assert 'onerror="alert' not in html


def _js(value) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)
