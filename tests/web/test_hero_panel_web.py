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


# 一顆一顆點（同 test_seal_acts_web.CLICK）：點完記下 #page 畫了什麼
CLICKS = """return (async () => {
  const target = (dataset) => ({ dataset, classList: { contains: () => false, add() {}, remove() {} } });
  const out = [];
  for (const dataset of input.clicks) {
    await T.docListeners.click[0]({ target: { closest: () => target(dataset) } });
    out.push((T.els.page || T.els.app).innerHTML);
  }
  return out;
})();"""


def test_the_bottom_news_tab_brings_back_the_news_tabs_after_the_hero_record(views):
    """從「俠客」進行狀，再按底下的「見聞」：回到見聞上一次看的那一段、五顆籤都在，不是只剩「‹ 俠客」（Joy 2026-10-28「見聞那邊只剩下行狀」）。"""
    import json

    m, x = views
    clicks = [{"act": "tab", "tab": "news"}, {"act": "news", "news": "boards"}, {"act": "tab", "tab": "practice"},
              {"act": "news", "news": "annals"}, {"act": "tab", "tab": "news"}]
    pages = run(m, CLICKS.replace("input.clicks", json.dumps(clicks)), S={"tab": "jianghu"}, menxia=x,
                responses={"/api/": {"main": m, "entries": [], "boards": [], "items": []}})
    hero, back = pages[3], pages[4]
    assert "‹ 俠客" in hero and "news-seg" not in hero
    assert "news-seg" in back and "‹ 俠客" not in back
    assert 'class="on" data-act="news" data-news="boards"' in back


def test_the_worn_move_hangs_under_the_martial_art_card(views):
    """俠客頁武學聯動絕招（Joy 2026-11-03，main.hero_move）：絕招那一條只掛在「武學」那一張底下；演一次、換一招、打法不對、沒穿。"""
    m, x = views
    x["owned_arts"] = [{"id": "a1", "name": "驚濤掌", "kind": "武學", "worn": True, "level": 4, "quality": "下品", "card": ""},
                       {"id": "a2", "name": "太虛吐納", "kind": "內功", "worn": True, "level": 6, "quality": "下品", "card": ""}]
    worn = {"id": "m7", "name": "怒濤擎天", "style": "fist", "style_text": "拳腳", "plays": True, "show": True, "asleep_text": ""}
    m["hero_move"] = {"count": 1, "style": "fist", "style_text": "拳腳", "art": "驚濤掌", "has_art": True, "worn": worn}
    page = run(m, "return H.pagePractice();", menxia=x)
    wrap = page.split('class="self-art-wrap')[1]
    assert page.count('class="self-art-wrap') == 1 and 'data-key="武學"' in wrap.split("hm-strip")[0]
    assert "絕招「怒濤擎天」" in wrap and 'data-act="hero-move-show" data-id="m7"' in wrap and 'data-act="hero-move-go"' in wrap
    assert "scene-preview" not in page  # 還沒按演一次：不放畫布
    shown = run(m, "return H.pagePractice();", menxia=x, S={"heroMoveShow": "m7"})
    assert 'id="scene-preview"' in shown and "收起" in shown
    m["hero_move"]["style"], m["hero_move"]["style_text"] = "slash", "揮砍"
    m["hero_move"]["worn"] = dict(worn, plays=False, asleep_text="這一招是拳腳的，你現在的打法是揮砍——擂台上不會演，換回拳腳才演得出來。")
    asleep = run(m, "return H.pagePractice();", menxia=x)
    assert "擂台上不會演" in asleep and "換一招揮砍的" in asleep
    m["hero_move"] = {"count": 0, "style": "fist", "style_text": "拳腳", "art": "驚濤掌", "has_art": True}
    none = run(m, "return H.pagePractice();", menxia=x)
    assert "還沒有絕招" in none and "替「驚濤掌」寫一招" in none and 'data-act="hero-move-show"' not in none
    del m["hero_move"]
    assert "self-art-wrap" not in run(m, "return H.pagePractice();", menxia=x)  # 沒開賣：照舊
