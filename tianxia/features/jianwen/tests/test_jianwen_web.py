"""見聞頁重排（web/jianwen.js）：開關開著時見聞頁換成圖頭、眼下一張卡、五面牌（戰況那面寬、帶三條戰線）；點一面拉起那一塊。
戰況、江湖史、榜單換了新排法，點開一場戰報、一篇戰記照舊是原本那一頁。正式內容；沒有 node 的略過。"""
from __future__ import annotations

import re

import pytest
from test_companions import _player, real  # noqa: F401  real 是 fixture
from test_prologue_web import DRIVER as PROLOGUE_DRIVER

import server
import webharness

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")

NAMES_START = 'wholeApp(["S", '
assert PROLOGUE_DRIVER.count(NAMES_START) == 1
DRIVER = PROLOGUE_DRIVER.replace(NAMES_START, 'wholeApp(["S", "pageNews", ')
REPORTS = {"list": [{"id": 7, "label": "大勝　vs 黃巾兵　第 1 天 10:00"}, {"id": 6, "label": "落敗　vs 黃巾兵　第 1 天 09:00"}], "detail": ""}
CLICK = ("const click = (dataset) => T.docListeners.click[0]({ target: { closest: () => ({ dataset, classList: { contains: () => false, add() {}, remove() {} },"
         " isConnected: false }) } });")


def run(m, script, *, S=None, responses=None):
    return webharness.run(DRIVER, {"m": m, "script": script, "S": S or {}, "menxia": None, "stored": {}, "responses": responses or {}})


def _game(real, world, on=True):  # noqa: F811
    real.config.jianwen.enabled = on
    return _player(real, world, "沈浪", "guan", "zhuo_county", warm=True)


def test_status_carries_the_switch_and_bots_get_nothing(real, world):  # noqa: F811
    g = _game(real, world)
    assert server.main_view(g)["jianwen"] == {"on": True}
    g.state.player.bot = True
    assert "jianwen" not in server.main_view(g)


def test_switch_off_keeps_the_old_segments(real, world):  # noqa: F811
    g = _game(real, world, on=False)
    page = run(server.main_view(g), "return H.pageNews();", S={"tab": "news", "news": "rumors"})
    assert "jw-hero" not in page and "nw-tabs" in page


def test_first_screen_is_hero_eye_and_five_plaques(real, world):  # noqa: F811
    g = _game(real, world)
    m = server.main_view(g)
    m["fronts"] = [{"id": "a", "name": "冀州", "value": 70}, {"id": "b", "name": "潁川", "value": 50, "chaos": True}, {"id": "c", "name": "南陽", "value": 20}]
    page = run(m, "return H.pageNews();", S={"tab": "news", "news": "reports", "unseen": 7, "reports": REPORTS})
    assert "jw-hero" in page and "<h1>見聞</h1>" in page and "nw-tabs" not in page  # 那一排五顆籤不畫
    eye = page.split('aria-label="眼下"')[1].split("</section>")[0]
    assert 'data-act="report" data-id="7"' in eye and 'data-act="jw-later"' in eye  # 新的那一場：鈕在卡上直接看
    plaques = re.findall(r'data-act="jw-open" data-news="(\w+)"', page.split('aria-label="眼下"')[1].split("</section>", 1)[1])
    assert set(plaques) >= {"reports", "rumors", "chronicle", "boards", "journal"}
    assert page.count('class="jw-tug"') == 3 and "黃巾佔上風" in page and "亂局" in page and "70" not in re.sub(r"<[^>]+>", "", page)  # 戰況那面寬牌畫三條拔河，不露數字
    assert "○" not in page  # 不用小圓圈排進度（Joy 11/22）


def test_a_plaque_pulls_up_its_sheet_and_close_goes_back(real, world):  # noqa: F811
    g = _game(real, world)
    script = CLICK + (" return (async () => { await click({ act: 'jw-open', news: 'rumors' }); const open = H.pageNews();"
                      " await click({ act: 'jw-close' }); return { open, sec: H.S.jwSec, back: H.pageNews() }; })();")
    out = run(server.main_view(g), script, S={"tab": "news", "news": "reports"}, responses={"/api/": {}})
    assert "jw-sheet" in out["open"] and 'data-act="jw-close"' in out["open"]
    assert not out["sec"] and "jw-sheet" not in out["back"] and 'aria-label="眼下"' in out["back"]


def test_reports_sheet_has_seals_and_a_fight_opens_the_old_page(real, world):  # noqa: F811
    g = _game(real, world)
    m = server.main_view(g)
    S = {"tab": "news", "news": "reports", "jwSec": "reports", "jwSeen": "reports", "reports": REPORTS}
    page = run(m, "return H.pageNews();", S=S)
    assert "jw-sheet" in page and len(re.findall(r'class="jw-rep[ "]', page)) == 2
    assert 'data-act="report" data-id="7"' in page and "jw-rs" in page  # 一場一行，勝敗蓋印
    old = run(m, "return H.pageNews();", S={**S, "reportOpen": True})
    assert not re.search(r'class="jw-rep[ "]', old)  # 點開一場：照舊是原本那一頁的戰報


def test_empty_reports_sheet_sends_you_back_to_fight(real, world):  # noqa: F811
    g = _game(real, world)
    S = {"tab": "news", "news": "reports", "jwSec": "reports", "jwSeen": "reports", "reports": {"list": [], "detail": ""}}
    page = run(server.main_view(g), "return H.pageNews();", S=S)
    assert "jw-rep" not in page and 'data-tab="jianghu"' in page


def test_chronicle_sheet_puts_lingyan_on_top(real, world):  # noqa: F811
    real.config.lingyan.enabled = True
    g = _game(real, world)
    S = {"tab": "news", "news": "chronicle", "jwSec": "chronicle", "jwSeen": "chronicle"}
    page = run(server.main_view(g), "return H.pageNews();", S=S)
    assert 'href="/lingyan"' in page and "jw-hall" in page


def test_a_jump_from_elsewhere_opens_that_sheet(real, world):  # noqa: F811
    """別的頁照舊只設 S.news（例：江湖頁的戰報連結）：這裡看到它變了就拉起那一塊。"""
    g = _game(real, world)
    page = run(server.main_view(g), "return H.pageNews();", S={"tab": "news", "news": "rumors", "jwSeen": "reports"})
    assert "jw-sheet" in page and "傳聞" in page
