"""修練頁最上面的人物面板（企劃者 2026-10-12 給的版面）：剪影身上的光點對上身上的兩門與開著的裝備欄，
底下那一格寫點著的那一個；屬性不放上去（企劃者 2026-10-12）。餵真的引擎資料給 app.js；沒有 node 就略過。"""
from __future__ import annotations

import random

import pytest
from test_prologue_web import run
from test_weapons_web import _gear, _row

import server
import webharness
from tianxia.engine import Game

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


@pytest.fixture
def views(hints_content, world):
    game = Game.new(hints_content, "沈浪", rng=random.Random(0), world=world)
    game.skip_tutorial()
    return server.main_view(game), server.menxia_view(game)


def _panel(page):
    return page.split('<section class="hero"')[1].split("</section>")[0]


def test_the_panel_draws_the_worn_arts_but_no_stats(views):
    m, x = views
    panel = _panel(run(m, "return H.pagePractice();", menxia=x))
    assert 'data-key="內功"' in panel and 'data-key="武學"' in panel
    assert "/static/hero.webp" in panel
    for _name, _value, key in m["status"]["attrs"]:
        assert f'data-key="{key}"' not in panel  # 屬性不放上去（企劃者 2026-10-12）
    assert 'data-act="allocate"' not in panel
    assert 'data-key="weapon"' not in panel  # 裝備欄都關著（測試內容）：不畫那幾個點


def _drawer(page):
    return page.split('class="sheet pr-sheet"')[1]


def test_nothing_is_open_until_a_node_is_tapped_and_an_empty_slot_says_so(views):
    m, x = views  # 測試內容的新角色身上還沒有功法：點暗著；點了，抽屜說還沒有（招式與絕學稿案第四輪：底下那一格改成抽屜）
    page = run(m, "return H.pagePractice();", menxia=x)
    assert 'hero-node dim l" style' in _panel(page).split('data-key="內功"')[0].rsplit("<button", 1)[1]
    assert "pr-sheet" not in page and 'id="hero-ft"' not in page
    tapped = run(m, "return H.pagePractice();", menxia=x, S={"pdrawer": {"t": "worn", "key": "內功"}})
    assert 'hero-node on dim l" style' in _panel(tapped).split('data-key="內功"')[0].rsplit("<button", 1)[1]
    assert "還沒有內功" in _drawer(tapped)


def test_a_tapped_gear_node_opens_that_slot_in_the_drawer_and_gear_nodes_follow_the_open_slots(views):
    m, x = views
    x["gear"] = _gear(weapon={"worn": _row(name="<i>試刃</i>"), "rack": []}, armor={"worn": None, "rack": []})
    page = run(m, "return H.pagePractice();", menxia=x, S={"pdrawer": {"t": "gear", "key": "weapon"}})
    panel = _panel(page)
    assert 'data-key="weapon"' in panel and 'data-key="armor"' in panel and 'data-key="mount"' not in panel
    # 減法季批 1：裝備是人像四角的四格（左上武器、左下防具……），沒穿的那一格虛線框
    assert 'class="self-gear bl empty"' in panel.split('data-key="armor"')[0].rsplit("<button", 1)[1]  # 沒穿防具：空著
    assert 'class="self-gear tl"' in panel.split('data-key="weapon"')[0].rsplit("<button", 1)[1]
    assert "&lt;i&gt;試刃&lt;/i&gt;" in panel and "<i>試刃</i>" not in page  # 名字寫在格子裡，跳脫
    assert 'data-slot="weapon"' in _drawer(page)  # 抽屜裡是那一欄


def test_a_woman_gets_the_female_figure_and_its_own_node_spots(views):
    m, x = views
    man = _panel(run(m, "return H.pagePractice();", menxia=x))
    m["status"]["gender"] = "女"  # 創角色選性別之後由伺服器給（企劃者 2026-10-12）；還沒有這個鍵的角色照男版
    woman = _panel(run(m, "return H.pagePractice();", menxia=x))
    assert "/static/hero.webp" in man and "/static/hero-f.webp" in woman
    spot = lambda page: page.split('data-key="內功"')[0].rsplit("<button", 1)[1]
    assert spot(man) != spot(woman)  # 光點照各自那張圖的位置


def test_settings_offer_old_characters_one_gender_pick(views):
    """設定頁的性別（PM 2026-10-12）：沒選過的舊角色兩顆鈕、先問一次；選過的只寫一行。"""
    m, _ = views
    m["status"].update(gender="男", gender_chosen=False)
    sheet = run(m, "return H.sheetHtml();")
    assert 'data-act="gender-pick" data-value="女"' in sheet and "只能選一次" in sheet
    asked = run(m, "H.S.genderPick = '女'; return H.sheetHtml();")
    assert "往後以女俠行走江湖" in asked and 'data-act="gender-go" data-value="女"' in asked
    m["status"].update(gender="女", gender_chosen=True)
    done = run(m, "return H.sheetHtml();")
    assert "性別：女" in done and "gender-pick" not in done
