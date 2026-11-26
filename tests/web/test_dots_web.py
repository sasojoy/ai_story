"""紅點一路標到那件事（Joy 2026-11-12「俠客那邊有紅點點 但是進去後 對應有紅點的事件應該也要標吧…以後事情可以不要只做一半嗎」）：
每個來源（web/shell.js registerDot）亮的時候，底部分頁（或 ⚙）、頁裡的子分頁、那一張卡或那一顆按鈕三層都有紅點；看過之後三層一起滅。
來源：親衛隊長那件事（web/guard.js）、信匣（web/mail.js）、見聞的新一場（web/news.js）、客服回覆（web/support.js）、帳號綁定（web/identity.js）。
正式內容；沒有 node 的略過。"""
# 畫法在 web/shell.js、web/guard.js、web/mail.js、web/news.js、web/support.js、web/identity.js、web/cultivation.js；寫在這裡 test_for 改包檔時才挑得到
from __future__ import annotations

import re

import pytest
from test_companions import _player, real  # noqa: F401  real 是 fixture
from test_prologue_web import DRIVER as PROLOGUE_DRIVER

import server
import webharness

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
DOT = '<i class="dot" aria-hidden="true"></i>'
NAMES_START = 'wholeApp(["S", '
assert PROLOGUE_DRIVER.count(NAMES_START) == 1
DRIVER = PROLOGUE_DRIVER.replace(NAMES_START, 'wholeApp(["S", "pageNews", ')


def run(m, script, *, S=None, menxia=None, responses=None):
    return webharness.run(DRIVER, {"m": m, "script": script, "S": S or {}, "menxia": menxia, "stored": {}, "responses": responses or {}})


def _tab(html: str, tab: str) -> str:
    return html.split(f'data-tab="{tab}"')[1].split("</button>")[0]


def _guard(shown: bool) -> dict:
    return {"name": "小明", "pron": "他", "meter": 0.6, "band": "親近", "stage": "grow", "stage_text": "初來", "log": [], "lessons": [],
            "event": {"kind": "milestone", "shown": shown, "text": "他在院子裡等你。", "choices": ["陪他坐一會兒"]}, "say_max": 30}


def test_the_guard_event_marks_the_tab_the_mates_tab_and_the_event_until_opened(real, world):  # noqa: F811
    g = _player(real, world, "沈浪", "guan", "zhuo_county")
    m, x = server.main_view(g), server.menxia_view(g)
    m["guard"] = _guard(False)
    tabs = run(m, "return H.tabsHtml();", S={"tab": "jianghu"})
    assert DOT in _tab(tabs, "practice")
    arts = run(m, "return H.pagePractice();", menxia=x, S={"tab": "practice", "heroTab": "arts"})
    assert DOT in arts.split('data-tab="mates"')[1].split("</button>")[0]  # 第二層：同伴那一格
    assert DOT not in arts.split('data-tab="arts"')[1].split("</button>")[0]
    mates = run(m, "return H.pagePractice();", menxia=x, S={"tab": "practice", "heroTab": "mates"})
    assert re.search(r"<h4>眼前這件事" + re.escape(DOT) + "</h4>", mates)  # 第三層：那一件事
    m["guard"] = _guard(True)  # 攤開了：三層一起滅
    assert DOT not in _tab(run(m, "return H.tabsHtml();", S={"tab": "jianghu"}), "practice")
    page = run(m, "return H.pagePractice();", menxia=x, S={"tab": "practice", "heroTab": "mates"})
    assert DOT not in page


def test_unread_mail_marks_the_tab_and_the_mailbox_button_until_read(real, world):  # noqa: F811
    g = _player(real, world, "沈浪", "guan", "zhuo_county")
    m, x = server.main_view(g), server.menxia_view(g)
    m["mail"] = {"unread": 2}
    assert DOT in _tab(run(m, "return H.tabsHtml();", S={"tab": "jianghu"}), "practice")
    page = run(m, "return H.pagePractice();", menxia=x, S={"tab": "practice"})
    assert '<i class="mail-dot">2</i>' in page  # 俠客頁上「信匣」那一顆帶數字（信匣裡那一封自己也標，web/mail.js）
    m["mail"] = {"unread": 0}
    assert DOT not in _tab(run(m, "return H.tabsHtml();", S={"tab": "jianghu"}), "practice")


def test_a_new_fight_marks_news_the_reports_segment_and_its_row_until_opened(real, world):  # noqa: F811
    g = _player(real, world, "沈浪", "guan", "zhuo_county")
    m = server.main_view(g)
    reports = {"list": [{"id": 7, "label": "大勝　vs 黃巾兵　第 1 天 10:00"}, {"id": 6, "label": "落敗　vs 黃巾兵　第 1 天 09:00"}], "detail": ""}
    S = {"tab": "jianghu", "unseen": 7, "news": "rumors", "reports": reports}
    out = run(m, "const tabs = H.tabsHtml(); H.S.tab = 'news'; const seg = H.pageNews(); H.S.news = 'reports'; return { tabs, seg, list: H.pageNews() };", S=S)
    assert DOT in _tab(out["tabs"], "news")
    assert DOT in out["seg"].split('data-news="reports"')[1].split("</button>")[0]  # 第二層：戰況那一段
    rows = out["list"].split('class="nw-rep"')
    assert DOT in next(r for r in rows if 'data-id="7"' in r) and DOT not in next(r for r in rows if 'data-id="6"' in r)  # 第三層：新的那一場
    script = ("return (async () => { await T.docListeners.click[0]({ target: { closest: () => ({ dataset: { act: 'report', id: '7' }, "
              "classList: { contains: () => false, add() {}, remove() {} }, isConnected: false }) } }); H.S.reportOpen = false;"
              " return { unseen: H.S.unseen, tabs: H.tabsHtml(), page: H.pageNews() }; })();")
    seen = run(m, script, S={**S, "tab": "news", "news": "reports"}, responses={"/api/reports": {**reports, "selected": 7}})
    assert seen["unseen"] is False and DOT not in seen["tabs"] and DOT not in seen["page"]  # 點開那一場：三層一起滅


def test_support_replies_and_a_missing_phone_mark_the_settings_button(real, world):  # noqa: F811
    g = _player(real, world, "沈浪", "guan", "zhuo_county")
    m = server.main_view(g)
    m["support_unread"] = 1
    top = run(m, "return H.topHtml();", S={"tab": "jianghu"})
    assert DOT in top.split('data-act="sheet"')[1].split("</button>")[0]
    m["support_unread"] = 0
    top = run(m, "return H.topHtml();", S={"tab": "jianghu"})
    assert DOT not in top.split('data-act="sheet"')[1].split("</button>")[0]
