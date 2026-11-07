"""戰記頁的標記（tale_html.py；Joy 2026-11-04 戰記獨立一頁、可以分享）：抬頭、戰果帶、目錄、一幕一段、玩家原話、名錄、招攬。
伺服器怎麼拼資料、分享代碼與路由在 tests/server/test_server.py（test_a_written_tale_gets_a_share_page_anyone_can_open）。"""
from __future__ import annotations

import re

from tianxia.features.tale import tale_html

VIEW = {
    "title": "長社火攻戰記", "battle_name": "長社火攻", "season": 8, "result": "黃巾大勝", "stamp": "黃巾大勝",
    "kicker": "天下大勢・第 8 季・三國", "sub": "", "lead": "暮色將近。", "cover": "/static/img/places/yingru.webp", "present": 11,
    "sides": [{"name": "官軍", "cls": "guan"}, {"name": "黃巾軍", "cls": "huang"}],
    "acts": [
        {"title": "長社城下", "banner": "第 3 週・週六 21:00", "scenes": [
            {"head": "暮色", "text": "暮色將近，霜刃立於陣前。\n她看著城頭，嘴角一勾。", "said": {"who": "霜刃", "side": "黃巾軍", "line": "包圍城頭那一隊"}},
            {"head": "", "text": "鐵鍋撲上前去，卻被輕巧閃開。"},
        ]},
        {"title": "夜風將起", "no": "收場", "banner": "", "scenes": [{"head": "夜裡", "text": "火沒有燒起來。"}]},
    ],
    "cast": [{"name": "霜刃", "side": "黃巾軍", "line": "放手一搏成了六次。"}, {"name": "鐵鍋", "side": "", "line": "倒在天亮之前。"}],
}


def page(view=VIEW, embedded=False):
    return tale_html.page(view, url="https://x/zhanji/abc", image="https://x/c.webp", embedded=embedded)


def test_the_page_draws_the_cover_the_result_and_the_acts():
    html = page()
    assert "<title>長社火攻戰記・天下大勢</title>" in html and '<img src="/static/img/places/yingru.webp"' in html
    assert "<h1>長社火攻</h1>" in html and "天下大勢・第 8 季・三國" in html
    assert '<div class="zj-side guan"><b>官軍</b></div><div class="zj-stamp">黃巾大勝</div><div class="zj-side huang"><b>黃巾軍</b></div>' in html
    assert "<b>二</b>回" in html and "<b>十一</b>人在場" in html
    assert '<span class="zj-no">第一回</span><h2>長社城下</h2><p class="zj-when">第 3 週・週六 21:00</p>' in html
    assert '<span class="zj-no">收場</span><h2>夜風將起</h2></header>' in html  # 沒有時辰行不畫
    assert '<p class="first">暮色將近，霜刃立於陣前。</p><p>她看著城頭，嘴角一勾。</p>' in html  # 一行一段，每一幕第一段放大第一個字
    assert '<q>包圍城頭那一隊</q><cite><span class="zj-dot huang"></span>霜刃・黃巾軍</cite>' in html
    assert "<h3></h3>" not in html  # 沒有小標的那一拍不畫空的
    assert '<a href="#act1"><i>壹</i>長社城下</a>' in html and '<a href="#act2"><i>收場</i>夜風將起</a>' in html and 'href="#cast"' in html


def test_the_cast_shows_names_and_sides_only():
    html = page()
    assert '<i class="zj-chop huang">霜</i><b>霜刃<small>黃巾軍</small></b><span>放手一搏成了六次。</span>' in html
    assert '<i class="zj-chop ">鐵</i><b>鐵鍋</b>' in html
    assert "zj-cast" not in page({**VIEW, "cast": []})


def test_the_public_page_invites_and_the_game_layer_goes_back():
    public, inside = page(), page(embedded=True)
    assert '<section class="zj-cta">' in public and '<a href="/">天下大勢</a>' in public and 'id="zj-back"' not in public
    assert '<section class="zj-cta">' not in inside and 'id="zj-back"' in inside and 'class="zj in"' in inside
    for html in (public, inside):
        assert 'data-url="https://x/zhanji/abc"' in html and '<meta property="og:image" content="https://x/c.webp">' in html


def test_everything_given_is_escaped():
    bad = {**VIEW, "battle_name": "<b>x</b>", "title": "<i>t</i>",
           "acts": [{"title": "<s>", "scenes": [{"head": "<u>", "text": "<img src=x>", "said": {"who": "<a>", "line": '"><script>'}}]}],
           "cast": [{"name": "<em>甲</em>", "side": "<p>", "line": "<br>"}]}
    html = page(bad)
    for raw in ("<b>x</b>", "<i>t</i>", "<s>", "<u>", "<img src=x>", "<a>", '"><script>', "<em>甲</em>", "<small><p>", "<span><br>"):
        assert raw not in html
    assert "&lt;img src=x&gt;" in html and "&lt;em&gt;甲&lt;/em&gt;" in html


def test_no_game_internals_leak_into_the_page():
    """分享出去的頁不寫假人（同 web/ 的規矩），也不寫帳號；數字只寫幾回、幾人在場。"""
    html = page() + tale_html.missing()
    for word in ("假人", "機器人", "login", "帳號"):
        assert word not in html
    assert not re.search(r"\bbots?\b", html, re.I)
