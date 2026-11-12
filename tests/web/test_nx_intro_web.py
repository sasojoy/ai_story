"""江湖新事（Joy 2026-11-12「做一個這批新功能的專屬介紹頁面」；web/news.js nxPageHtml）：九樣新功能一樣一張卡、一顆「去看看」，
親衛那一張用 Joy 挑的「拾孤成衛」；進遊戲後每支手機跳一次（看過不再跳，之後在改版資訊小窗頂上與設定裡點得到）；登入頁有一條橫幅；
「去看看」帶到那個功能的最後一層（Joy 11/12「事情不要只做一半」）。正式內容；沒有 node 的略過。"""
# 畫法在 web/news.js、web/news.css；入口在 web/app.js 的登入頁與設定抽屜。寫在這裡 test_for 改這幾支時才挑得到
from __future__ import annotations

import re
from pathlib import Path

import pytest
from test_companions import _player, real  # noqa: F401  real 是 fixture
from test_prologue_web import DRIVER as PROLOGUE_DRIVER

import server
import webharness

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
NAMES_START = 'wholeApp(["S", '
assert PROLOGUE_DRIVER.count(NAMES_START) == 1
DRIVER = PROLOGUE_DRIVER.replace(NAMES_START, 'wholeApp(["S", "patchPopHtml", "nxPageHtml", "nxGo", ')
WEB = Path(__file__).resolve().parents[2] / "web"
NOTE = {"date": "11/12", "new": ["門派"], "tweak": [], "fix": []}
KEY = "2026-11-12"


RESPONSES = {"/api/mingtie": {"mine": None, "box": [], "made_left": 1, "sent_left": 1}, "/api/mail": {"threads": [], "unread": 0}}


def run(m, script, *, S=None, stored=None, menxia=None):
    return webharness.run(DRIVER, {"m": m, "script": script, "S": S or {}, "menxia": menxia, "stored": stored or {}, "responses": RESPONSES})


def test_the_page_has_nine_cards_in_order_each_with_a_go_button_and_real_pictures(real, world):  # noqa: F811
    m = server.main_view(_player(real, world, "沈浪", "guan", "zhuo_county"))
    page = run(m, "return H.nxPageHtml();")
    names = re.findall(r'<div class="nx-body"><h3>(.*?)</h3>', page)
    assert names == ["門　派", "結　義", "拾孤成衛", "帖友書信", "稱號與官職", "合璧成神", "天下名駒", "回爐淬煉", "酒肆題壁"]
    assert re.findall(r'data-act="nx-go" data-id="(\w+)"', page) == ["zongmen", "jieyi", "guard", "mail", "titles", "craft", "horses", "temper", "tavern"]
    for src in set(re.findall(r"/static/([\w/.-]+\.webp)", page + (WEB / "news.css").read_text(encoding="utf-8"))):
        assert (WEB / src).is_file(), src  # 圖都是現成的


def test_it_pops_once_per_phone_before_the_patch_notes_then_lives_in_the_patch_window_and_settings(real, world):  # noqa: F811
    m = server.main_view(_player(real, world, "沈浪", "guan", "zhuo_county"))
    m["story_cards"] = []
    first = run(m, "return H.patchPopHtml(H.S.main);", S={"patchNotes": [NOTE]})
    assert 'class="sheet nx-invite"' in first and "patch-pop" not in first
    script = ("return (async () => { await T.docListeners.click[0]({ target: { closest: () => ({ dataset: { act: 'nx-later' }, "
              "classList: { contains: () => false } }) } }); return { seen: T.ctx.localStorage.getItem('tianxia.introSeen'), pop: H.patchPopHtml(H.S.main) }; })();")
    later = run(m, script, S={"patchNotes": [NOTE]})
    assert later["seen"] == KEY
    assert "nx-invite" not in later["pop"] and "patch-pop" in later["pop"] and 'data-act="nx-open"' in later["pop"]  # 改版資訊小窗頂上那一行
    seen = run(m, "return { pop: H.patchPopHtml(H.S.main), sheet: H.sheetHtml() };", S={"patchNotes": [NOTE]}, stored={"tianxia.introSeen": KEY})
    assert "nx-invite" not in seen["pop"]
    assert 'data-act="nx-open"' in seen["sheet"]  # 設定「新手與說明」裡那一顆


def test_the_login_page_shows_the_banner():
    app = (WEB / "app.js").read_text(encoding="utf-8")
    gate = app.split('<form id="gate-form"')[1].split('id="gate-patch"')[0]
    assert "nxBannerHtml()" in gate  # 登入表單底下、改版資訊上面（不在 #gate-patch 裡：讀到改版資訊會整塊換掉）


def test_go_takes_each_one_to_its_last_layer(real, world):  # noqa: F811
    g = _player(real, world, "沈浪", "guan", "zhuo_county")
    m, x = server.main_view(g), server.menxia_view(g)
    m["guard"] = {"name": "小明", "pron": "他", "meter": 0.6, "band": "親近", "stage": "grow", "stage_text": "初來", "log": [], "lessons": [],
                  "event": {"kind": "milestone", "shown": True, "text": "他在院子裡等你。", "choices": ["陪他坐一會兒"]}, "say_max": 30}
    m["titles"] = {"worn": {}, "rows": []}
    m["options"] = [o for o in m.get("options", []) if o["id"] != "act:smith"]  # 這裡沒有鐵匠鋪
    script = ("return (async () => { const out = {};"
              " for (const id of ['jieyi', 'guard', 'mail', 'titles', 'craft', 'temper']) {"
              "   H.S.titlesOpen = false; await H.nxGo(id);"
              "   out[id] = { tab: H.S.tab, hero: H.S.heroTab, news: H.S.news, titles: !!H.S.titlesOpen }; }"
              " return out; })();")
    out = run(m, script, S={"tab": "jianghu"}, menxia=x)
    assert out["jieyi"]["tab"] == "news" and out["jieyi"]["news"] == "mingtie"  # 名帖匣裡的金蘭譜
    assert out["guard"]["tab"] == "practice" and out["guard"]["hero"] == "mates"  # 同伴那一頁最上面
    assert out["mail"]["news"] in ("mail", "mingtie")
    assert out["titles"]["titles"]  # 頭銜印攤開的那一張
    assert out["craft"]["tab"] == "craft"
    assert out["temper"]["tab"] == "map"  # 鐵匠鋪不在這裡：開輿圖


def test_go_before_login_waits_and_takes_you_there_after(real, world):  # noqa: F811
    m = server.main_view(_player(real, world, "沈浪", "guan", "zhuo_county"))
    m["story_cards"] = []
    out = run(m, "return (async () => { H.S.stage = 'gate'; await H.nxGo('craft'); const kept = H.S.nxAfter; H.S.stage = 'game';"
              " const pop = H.patchPopHtml(H.S.main); return { kept, after: H.S.nxAfter, pop }; })();", stored={"tianxia.introSeen": KEY})
    assert out["kept"] == "craft" and out["after"] is None and out["pop"] == ""


def test_the_fixed_link_opens_the_page():
    """固定網址（Joy 2026-11-12「他會有固定網址嗎」）：/#new 一打開就是這一頁；只是錨點，不是新路由，沒登入也看得到。"""
    news = (WEB / "news.js").read_text(encoding="utf-8")
    assert 'const NX_HASH = "#new";' in news
    assert 'window.addEventListener("hashchange", nxFromHash);' in news and "setTimeout(nxFromHash, 0);" in news
