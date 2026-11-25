"""慢慢長出來的小事卡（web/unfold.js）：拿到那一本的新角色，碰到才說的提示畫成一張卡（圖、一句話、去做＋知道了）；舊角色照舊是那個框。
假瀏覽器跑整支 app.js（test_prologue_web 那一套）。"""
from __future__ import annotations

import pytest
from test_prologue_web import DRIVER as PROLOGUE_DRIVER

import webharness

pytestmark = [pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")]
NAMES_START = 'wholeApp(["S", '
DRIVER = PROLOGUE_DRIVER.replace(NAMES_START, 'wholeApp(["S", "guideHtml", "unfoldNowHtml", ')
HINT = {"speaker": "想起師父說過", "key": "h_merge", "scene": "", "text": "「兩個意境揉在一塊。」", "line": "", "done": [], "end": True,
        "pending": False, "full": True, "hint": True}


def _html(unfold):
    m = {"guide": HINT}
    if unfold is not None:
        m["unfold"] = unfold
    return webharness.run(DRIVER, {"m": m, "script": "return H.guideHtml(m.guide, false);", "S": {}, "menxia": None,
                                   "stored": {}, "responses": {}})


def test_a_new_player_sees_the_hint_as_a_card_with_a_go_button():
    html = _html({"hide": [], "fresh": []})
    assert "uf-card" in html and 'data-go="tab:craft"' in html and 'data-act="guide-ack"' in html and "/static/img/events/altar.webp" in html


def test_an_old_player_keeps_the_old_box():
    html = _html(None)
    assert "uf-card" not in html and "guide-text" in html


def test_the_sect_card_carries_the_join_and_later_buttons_and_wins_over_a_hint():
    card = {"kind": "sect", "arg": "baima", "who": "白馬寺山門口", "say": "掃地的門人抬頭：「進來喝口茶？」", "go": "進去看看", "later": "改天"}
    m = {"guide": HINT, "unfold": {"hide": [], "fresh": [], "card": card}}
    html = webharness.run(DRIVER, {"m": m, "script": "return H.unfoldNowHtml(m);", "S": {}, "menxia": None, "stored": {}, "responses": {}})
    assert 'data-go="opt:zongmen:join:baima"' in html and 'data-act="unfold-card-later"' in html and "改天" in html and "進來喝口茶" in html
    assert "兩個意境" not in html  # 一次一張：自己那張先


def test_an_old_player_gets_no_card_from_the_new_slot():
    out = webharness.run(DRIVER, {"m": {"guide": HINT}, "script": "return H.unfoldNowHtml(m);", "S": {}, "menxia": None, "stored": {}, "responses": {}})
    assert out is None
