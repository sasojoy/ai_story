"""江湖頁減法（減法季批 1，整合設計第六章；本週卡照 Joy 2026-10-24 挑的乙案）的網頁部分：本週卡（灰線＋只剩「你這一步」的卡）、
還沒投靠的人的三方卡、「剛剛」收成一行、事件選項前的小圖示、灰掉的主鈕點了浮出為什麼。照 tests/test_prologue_web.py 的做法把整支網頁放進 node 的假瀏覽器，餵它真的引擎給的 /api/main；
沒有 node 就略過。（以前那一排小標的測試 test_peek_row.py 跟著小標一起拿掉了）"""
from __future__ import annotations

import random
import re

import pytest
from conftest import real_content
from test_prologue_web import run

import server
import webharness
from tianxia.engine import Game

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


def _main(*, faction=None, event=None, **over):
    content = real_content("weekend")
    content.config.auto_open_first_season = True
    game = Game.new(content, "沈浪", rng=random.Random(0))
    game.client = None
    game.state.player.faction = faction
    if event:
        game.state.pending_event = event
    m = server.main_view(game)
    m.update(over)
    return m


def _why(m):
    return {"wkOpen": {"key": m["week_card"]["label"] + m["week_card"]["when"], "id": "why"}}


def _title(step):
    return step["text"].split("：", 1)[0]


def test_the_week_card_is_a_strip_and_a_step_card():
    """乙案：上面一條灰線（第幾段、主題、兩軍態勢，整條是「為什麼」的鈕），卡本身只剩「你這一步」——標題、說明、去輿圖、換一件；
    沒有那一排字的連結、沒有簽到。四塊是江湖頁的兄弟（都帶 data-wk），不包一層。"""
    m = _main()
    w = m["week_card"]
    html = run(m, "return H.weekCardHtml(H.S.main);")
    strip = re.search(r'<button data-wk id="week" class="wk-strip"[^>]*>.*?</button>', html, re.S).group(0)
    assert 'data-act="wk" data-id="why"' in strip and w["when"] in strip and w["theme"] in strip
    assert "官 " in strip and "黃 " in strip and "豪強" not in strip
    card = re.search(r'<section data-wk class="card wk-card".*?</section>', html, re.S).group(0)
    assert '<p class="wk-lab">你這一步</p>' in card and f'<h2 class="wk-title">{_title(w["steps"][0])}</h2>' in card
    go = 'data-act="newbie-go"' if w["steps"][0]["kind"] == "newbie" else 'data-act="tab" data-tab="map"'  # 新手目標是「去做」，其餘「去輿圖」
    assert go in card and 'data-act="wk-next"' in card
    for word in ("為什麼</button>", "換一件事", "輿圖 ›</button>", "簽到", "wk-links"):
        assert word not in html
    assert "wk-panel" not in html


def test_another_thing_steps_through_the_candidates():
    m = _main()
    steps = m["week_card"]["steps"]
    assert len(steps) > 1
    key = m["week_card"]["label"] + m["week_card"]["when"]
    second = run(m, "return H.weekCardHtml(H.S.main);", S={"wkStep": {"key": key, "i": 1}})
    assert _title(steps[1]) in second and _title(steps[0]) not in second
    stale = run(m, "return H.weekCardHtml(H.S.main);", S={"wkStep": {"key": "上一週", "i": 1}})  # 換了一週：從第一件重來
    assert _title(steps[0]) in stale


def test_why_opens_the_sides_table_the_next_event_and_the_howto_entry():
    m = _main()
    closed = run(m, "return H.weekCardHtml(H.S.main);")
    assert "wk-panel" not in closed
    panel = run(m, "return H.weekCardHtml(H.S.main);", S=_why(m))
    assert 'class="card wk-panel why"' in panel and 'class="sides"' in panel and 'class="wk-strip on"' in panel
    for col in m["sides_card"]["cols"]:
        assert col["name"] in panel and col["where"][0] in panel
    assert 'data-act="howto-open"' in panel


def test_a_loner_gets_the_sides_card_first_and_a_member_does_not():
    loner = run(_main(), "return H.pageJianghu();")
    assert '<details class="card sides-first">' in loner and loner.index("sides-first") < loner.index("wk-card")  # 收著：不把行動列推出第一屏
    assert "官軍在長社" in loner
    assert '<details class="card sides-first" open>' in run(_main(), "return H.pageJianghu();", S={"sidesOpen": True})
    member = run(_main(faction="guan"), "return H.pageJianghu();")
    assert "sides-first" not in member and "wk-card" in member


def test_the_old_peek_row_fronts_and_minimap_are_gone_from_the_jianghu_page():
    page = run(_main(faction="guan"), "return H.pageJianghu();")
    assert 'class="peek"' not in page and 'class="fronts"' not in page and 'class="mini"' not in page


def test_the_now_card_is_one_line_until_tapped():
    now = '<div class="tx-now"><div class="tx-when">剛剛　第 1 天</div><div class="tx-head">甲事</div><p>第一句 &amp; 第二句</p></div>'
    m = _main(now=now)
    shut = run(m, "return H.pageJianghu();")
    one = re.search(r'<button class="now-one".*?</button>', shut, re.S).group(0)
    assert '<span class="tx-when">剛剛　第 1 天</span>' in one and "甲事　第一句 &amp; 第二句" in one
    opened = run(m, "return H.pageJianghu();", S={"nowOpen": now})
    assert "now-one" not in opened and 'class="now open' in opened


def test_event_options_get_an_icon_and_keep_only_the_action():
    m = _main(event="jz_altar_roster")
    opts = m["event_opts"]
    page = run(m, "return H.pageJianghu();")
    kinds = {v["kind"] for v in opts.values()}
    assert "fight" in kinds
    for oid, ev in opts.items():
        button = re.search(rf'<button[^>]*data-id="{oid}".*?</button>', page, re.S).group(0)
        assert f'class="k ev ev-{ev["kind"] or "plain"}"' in button and ev["act"] in button
        assert ("ev-worry" in button) is bool(ev["worry"])


def test_a_greyed_cell_says_why_when_tapped():
    m = _main()
    page = run(m, "return H.actionBar(H.S.main);")
    for cell in re.findall(r'<button class="act-ink off"[^>]*>', page):
        assert 'data-act="opt-why"' in cell and re.search(r'data-why="[^"]+"', cell) and 'aria-disabled="true"' in cell
