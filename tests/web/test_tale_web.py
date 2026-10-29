"""戰記（原稱戰役話本）的畫面（Joy 2026-10-29；寫法、產生、存放歸主機，這裡只有網頁）：戰報頁「‹ 全部戰報」那一行右邊的「戰記 ›」
（寫好了才按得下去、還在寫灰掉、沒有不畫）、戰記頁（幕、回、玩家原話、尾段名錄）、江湖史的目錄。主機還沒接上，用假的 /api/tale。"""
from __future__ import annotations

import json
import random

import pytest
from test_prologue_web import DRIVER as PROLOGUE_DRIVER

import server
import webharness
from tianxia.engine import Game

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")

NAMES_START = 'wholeApp(["S", '
assert PROLOGUE_DRIVER.count(NAMES_START) == 1
DRIVER = PROLOGUE_DRIVER.replace(NAMES_START, 'wholeApp(["S", "taleHtml", "taleLink", "taleIndexHtml", "pageNews", ')

TALE = {
    "status": "ready", "title": "長社火攻戰記", "season": 8, "battle_name": "長社火攻", "result": "黃巾大勝", "made_at": 0,
    "acts": [
        {"title": "長社城下", "scenes": [
            {"head": "暮色", "text": "暮色將近，霜刃立於陣前。\n她看著城頭，嘴角一勾。", "said": {"who": "霜刃", "side": "黃巾", "line": "包圍城頭那一隊"}},
            {"head": "", "text": "鐵鍋撲上前去，卻被輕巧閃開。"},
        ]},
        {"title": "夜風將起", "banner": "入夜之後，黃巾已經摸到城根。", "scenes": [{"head": "夜裡", "text": "火沒有燒起來。"}]},
    ],
    "cast": [{"name": "霜刃", "side": "黃巾", "line": "放手一搏成了六次，全場最敢。"}, {"name": "鐵鍋", "line": "倒在天亮之前。"}],
}

# 一顆一顆點（同 test_seal_acts_web.CLICK）：點完記下 #page 畫了什麼
CLICKS = """return (async () => {
  const target = (dataset) => ({ dataset, classList: { contains: () => false, add() {}, remove() {} } });
  const out = [];
  for (const dataset of input.clicks) {
    await T.docListeners.click[0]({ target: { closest: () => target(dataset) } });
    out.push((T.els.page || T.els.app).innerHTML);
  }
  return { out, calls: T.calls.map((c) => c[0]) };
})();"""


@pytest.fixture
def m(hints_content, world):
    game = Game.new(hints_content, "沈浪", rng=random.Random(0), world=world)
    game.skip_tutorial()
    return server.main_view(game)


def run(m, script, S=None, responses=None):
    return webharness.run(DRIVER, {"m": m, "script": script, "S": S or {"tab": "news", "news": "reports"}, "menxia": None, "stored": {},
                                   "responses": responses or {}})


def clicks(m, seq, tale, S=None, main=None):
    reports = {"list": [{"label": "長社火攻", "id": 3, "big": True}], "selected": 3, "detail": "<p>戰況</p>", "gauge": None, "tale_id": 41}
    script = CLICKS.replace("input.clicks", json.dumps(seq, ensure_ascii=False))
    return run(main or m, script, S=S, responses={"/api/reports": reports, "/api/tale/": tale})


def test_the_link_is_live_only_when_the_tale_is_ready(m):
    """寫好了：「戰記 ›」帶 data-act="tale"；還在寫：灰掉寫「史官還在落筆」；沒有、沒問到、不是決戰：不畫。"""
    link = lambda tales, ref=41: run(m, f"H.S.tales = {json.dumps(tales)}; return H.taleLink({json.dumps(ref)});")
    assert 'data-act="tale" data-id="41"' in link({"41": {"status": "ready"}}) and "戰記 ›" in link({"41": {"status": "ready"}})
    pending = link({"41": {"status": "pending"}})
    assert "史官還在落筆" in pending and "disabled" in pending and "data-act" not in pending
    assert link({"41": {"status": "none"}}) == "" and link({}) == "" and link({"41": {"status": "ready"}}, None) == ""


def test_the_tale_page_draws_acts_said_lines_and_the_cast(m):
    page = run(m, f"return H.taleHtml({json.dumps(TALE, ensure_ascii=False)});")
    assert "<h2>長社火攻戰記</h2>" in page and "第 8 季・黃巾大勝" in page
    assert '<span class="no">第一回</span>長社城下' in page and '<span class="no">第二回</span>夜風將起' in page
    assert "<p>暮色將近，霜刃立於陣前。</p><p>她看著城頭，嘴角一勾。</p>" in page  # 一行一段
    assert '<span class="who">霜刃・黃巾</span><span class="line">「包圍城頭那一隊」</span>' in page
    assert '<p class="huaben-banner">入夜之後，黃巾已經摸到城根。</p>' in page
    assert page.count("<li>") == 2 and '<span class="cast-side">黃巾</span>' in page and "倒在天亮之前。" in page
    assert '<h4></h4>' not in page  # 沒有小標的那一回不畫空的小標


def test_the_tale_page_escapes_what_it_is_given(m):
    bad = {**TALE, "battle_name": "<b>x</b>", "acts": [{"title": "t", "scenes": [{"head": "", "text": "<img src=x>"}]}], "cast": []}
    page = run(m, f"return H.taleHtml({json.dumps(bad, ensure_ascii=False)});")
    assert "<b>x</b>" not in page and "<img" not in page and "&lt;img src=x&gt;" in page
    assert "huaben-cast" not in page  # 名錄是空的就不畫那一段


def test_pending_and_none_pages_say_so(m):
    assert "史官還在落筆" in run(m, 'return H.taleHtml({status: "pending"});')
    assert "這一場沒有戰記" in run(m, 'return H.taleHtml({status: "none"});')


def test_open_a_report_then_the_tale_and_back(m):
    """戰報列表 → 那一場（問一次 /api/tale/41，右上畫「戰記 ›」）→ 戰記頁 → 「‹ 戰報」回到那一場的戰報。"""
    r = clicks(m, [{"act": "report", "id": "3"}, {"act": "tale", "id": "41"}, {"act": "tale-back"}], TALE)
    report, tale, back = r["out"]
    assert "‹ 全部戰報" in report and 'data-act="tale" data-id="41"' in report
    assert "<h2>長社火攻戰記</h2>" in tale and "‹ 戰報" in tale and "全部戰報" not in tale
    assert "‹ 全部戰報" in back and "<h2>長社火攻戰記</h2>" not in back
    assert "/api/tale/41" in r["calls"]


def test_a_pending_tale_greys_the_link_on_the_report(m):
    report = clicks(m, [{"act": "report", "id": "3"}], {"status": "pending"})["out"][0]
    assert "史官還在落筆" in report and 'data-act="tale"' not in report


def test_a_report_without_a_tale_draws_no_link(m):
    report = clicks(m, [{"act": "report", "id": "3"}], {"status": "none"})["out"][0]
    assert "‹ 全部戰報" in report and "戰記" not in report and "史官" not in report


def test_the_chronicle_lists_tales_only_when_the_server_sends_them(m):
    """江湖史最上面那排「戰記」：伺服器的開關關著（main.tales 是空的）不畫；有就一場一顆，點了開同一頁、「‹ 江湖史」回去。"""
    assert m["tales"] == []
    assert "戰記" not in run(m, "return H.pageNews();", S={"tab": "news", "news": "chronicle"})
    listed = {**m, "tales": [{"battle_id": 41, "title": "長社火攻", "season": 8, "result": "黃巾大勝"}]}
    page = run(listed, "return H.pageNews();", S={"tab": "news", "news": "chronicle"})
    assert 'data-act="tale" data-id="41"' in page and "第 8 季・黃巾大勝" in page
    assert "長社火攻戰記" in page  # 目錄也寫「<戰名>戰記」
    r = clicks(m, [{"act": "tale", "id": "41"}, {"act": "tale-back"}], TALE, S={"tab": "news", "news": "chronicle"}, main=listed)
    tale, back = r["out"]
    assert "‹ 江湖史" in tale and "<h2>長社火攻戰記</h2>" in tale
    assert 'class="list huaben-index"' in back
