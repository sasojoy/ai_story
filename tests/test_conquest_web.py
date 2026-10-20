"""領地爭奪的網頁（計畫第四章 Task 13、第五章 Task 17；第三批 A 只做這兩樣，攻城公告與投票的網頁等輿圖重製第 5 批）：

- 攻城戰畫面（企劃者挑甲）：沿用決戰畫面，最上面那一行換成一條「攻城・地點｜守方：某某（或守將）」（main.siege，Game.siege_banner）。
- 見聞「形勢」頁（企劃者挑乙）：一篇一行（「是日：…」＋時刻），最新一篇攤開、其餘點了攤開；空的時候一行「天下尚無定論。」。
  見聞的籤加了「形勢」是九顆，375 寬一排放不下：只在〈天下形勢〉開著的季（main.xingshi）畫第九顆、排成兩排（上五下四）。

把 app.js 的函式切出來交給 node 跑；沒有 node 就略過。"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import server
import webharness
from conquest_kit import announce, conquest_game, go, join
from tianxia import battle_instance, siege

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
ROOT = Path(__file__).parent.parent
NOW = 1_792_000_000.0

STRIP = r"""
const H = new Function([
  konst("esc"),
  fn("siegeStrip"),
  "return { siegeStrip };",
].join("\n"))();
finish(H.siegeStrip(input.html, input.s));
"""

PAGE = r"""
const S = { main: input.m || {}, xingshiOpen: input.open ? new Map(input.open) : null };
const NEWS = src.match(/\n  const NEWS = \[[\s\S]*?\n  \];/)[0]; // 多行的 const：konst 抓不到，照原文切
const H = new Function("S", [
  konst("esc"), NEWS, konst("XS_EMPTY"), konst("XS_PENDING"),
  fn("xingshiParas"), fn("xingshiHtml"), fn("newsSegHtml"),
  "return { xingshiHtml, newsSegHtml };",
].join("\n"))(S);
finish({ page: input.x === undefined ? "" : H.xingshiHtml(input.x), seg: H.newsSegHtml(input.m || {}) });
"""


def strip(html: str, s):
    return webharness.run(STRIP, {"html": html, "s": s})


def page(x=None, m=None, open_=None):
    payload = {"m": m or {}, "open": open_}
    if x is not None:
        payload["x"] = x
    return webharness.run(PAGE, payload)


HEAD = "<p><strong>攻城・荒丘</strong></p>\n<p>黃巾軍攻荒丘；守方：荒丘山賊（守將）。</p>\n"
BANNER = {"title": "攻城・荒丘", "parts": ["守方：荒丘山賊（守將）"], "kind": "neutral"}


# ── 攻城戰畫面（甲）──


def test_strip_replaces_the_title_line():
    out = strip(HEAD, BANNER)
    assert out.startswith('<p class="siege-strip"')
    assert "<p><strong>攻城・荒丘</strong></p>" not in out  # 名字那一行換成這一條，不重複一行
    assert out.count("攻城・荒丘") == 1 and "守方：荒丘山賊（守將）" in out
    assert re.search(r'<span class="ss-sep"[^>]*>｜</span>', out)  # 「攻城・地點｜守方：…」
    assert out.endswith("<p>黃巾軍攻荒丘；守方：荒丘山賊（守將）。</p>\n")  # 底下的場景照舊


def test_strip_inside_the_muster_head_and_after_the_gauge():
    muster = '<div class="muster-head"><p><strong>攻城・荒丘</strong></p><span class="muster-note">n</span></div>\n<div class="gauge"></div>\n<p>x</p>'
    out = strip(muster, BANNER)
    assert out.startswith('<div class="muster-head"><p class="siege-strip"')  # 投效的鈕照舊連在名字那一條後面


def test_no_strip_when_folded_or_not_a_siege():
    folded = '<p class="battle-fold" data-act="battle-open">攻城・荒丘　第 2 回合・點開看</p>\n<hr>'
    assert strip(folded, BANNER) == folded  # 收成一行的觀戰：不畫
    assert strip(HEAD, None) == HEAD  # 決戰：一個字都不變


def test_strip_segments_do_not_break_inside():
    out = strip(HEAD, {"title": "攻城・荒丘", "parts": ["三方混戰", "守方：荒丘山賊（守將）"], "kind": "melee"})
    assert out.count('class="nb') == 3 and out.count("ss-sep") == 2  # 每一段不折行，只在「｜」那裡換行


def test_strip_css_rules():
    css = (ROOT / "web" / "style.css").read_text(encoding="utf-8")
    assert ".scene > p.siege-strip {" in css  # 蓋過 .scene > p:first-child 的大字
    assert ".scene .muster-head > p.siege-strip {" in css


@pytest.mark.slow
def test_server_sends_the_banner_for_a_siege_and_the_page_draws_it():
    game = go(join(conquest_game("season21"), "huang"), "nanyang_road")
    game.now = NOW
    assert "siege" not in server.main_view(game)  # 沒有攻城戰：沒有這個鍵
    slot = announce(game, "nanyang_road", "huang")
    w = game.state.world
    slot.muster_at, slot.at, slot.status = w.time, w.time + 1800, "waiting"
    game._save_season()
    siege.open_waiting(game.world, game.content, NOW)
    game.state.world = game.world.get_season()
    view = server.main_view(game)
    s = view["siege"]
    assert s["title"] == "攻城・南陽官道" and s["kind"] == "neutral"
    assert s["parts"][0].startswith(siege.BANNER_DEFENDER.format(who="")) and battle_instance.GUARD_SUFFIX in s["parts"][0]
    out = strip(view["scene"], s)
    assert out.startswith('<p class="siege-strip"') and "攻城・南陽官道" in out


@pytest.mark.slow
def test_banner_words_for_melee_lone_and_held():
    """三方混戰（裁決 22）、只有一軍到場轉回單方（裁決 23）、陣營佔著的區塊：那一條各怎麼寫（【開發定】，待 joy 潤）。"""
    game = go(join(conquest_game("season21"), "huang"), "nanyang_road")
    game.now = NOW
    slot = announce(game, "nanyang_road", "huang", merged=("guan", "huang"))
    w = game.state.world
    slot.muster_at, slot.at, slot.status = w.time, w.time + 1800, "waiting"
    game._save_season()
    siege.open_waiting(game.world, game.content, NOW)
    battle = game.world.get_sieges()[0]
    assert battle_instance.melee(battle)
    b = siege.banner(game.content, battle)
    assert b["kind"] == "melee" and b["parts"][0] == siege.BANNER_MELEE
    battle.siege.attackers, battle.siege.guard_side, battle.siege.absent = ["huang"], "guan", "guan"  # 轉回單方（lone_army 改的那幾格）
    b = siege.banner(game.content, battle)
    guan = game.content.scenario.faction_name("guan", "guan")
    assert b["kind"] == "lone" and b["parts"][-1] == siege.BANNER_ABSENT.format(absent=guan)
    battle.siege.holder, battle.siege.guard_side, battle.siege.absent = "guan", None, ""  # 陣營佔著的區塊
    b = siege.banner(game.content, battle)
    assert b["kind"] == "held" and b["parts"] == [siege.BANNER_DEFENDER.format(who=guan)]


# ── FB-553：同一州兩場自己這一邊的攻城一起集結，兩顆加入鈕撐出橫捲 ──
# QA（qa/map-1 4be1960e，375×812）：名字那一行的 .options.muster-join 寬 457、documentElement.scrollWidth 488。.muster-join 在名字那一行裡
# 是 flex: none，寬度等於兩顆加起來（鈕上寫是哪一場，字長），wrap 用不上。現在兩顆以上一顆一行、另起一行排在名字底下（同挑同伴那一步的
# .pick），一顆的照舊在名字右邊。版面在 node 裡量不到：這裡鎖住排法與那兩條 CSS，375 寬實量見 docs/superpowers/specs/2026-10-20-領地爭奪-草圖/第三批/。


def _sieges_view(locs):
    """官軍的人站南陽官道，locs 每一塊各排一場官軍攻城、此刻開集結（同一州）：回 server.main_view。"""
    game = go(join(conquest_game("season21"), "guan"), "nanyang_road")
    game.now = NOW
    for loc in locs:
        slot = announce(game, loc, "guan")
        w = game.state.world
        slot.muster_at, slot.at, slot.status = w.time, w.time + 1800, "waiting"
        game._save_season()
    siege.open_waiting(game.world, game.content, NOW)
    game.state.world = game.world.get_season()
    return server.main_view(game)


def _join_row(m):
    from test_prologue_web import run as page_run

    page = page_run(m, "return H.pageJianghu();")
    row = re.search(r'<div class="options muster-join([^"]*)"[^>]*>(.*?)</div>', page, re.S)
    assert row is not None
    return row.group(1), row.group(2)


@pytest.mark.slow
def test_fb553_two_join_buttons_stack_one_per_line():
    m = _sieges_view(["nanyang_road", "nanyang_wilds"])
    joins = [o for o in m["options"] if o["id"].startswith("battle:join:")]
    assert len(joins) == 2 and all("@" in o["id"] for o in joins)  # 一場一顆，鈕上寫是哪一場
    cls, row = _join_row(m)
    assert "pick" in cls.split()  # 修前是空的：兩顆擠在名字那一行
    assert row.count('data-act="choose"') == 2


@pytest.mark.slow
def test_fb553_one_join_button_stays_beside_the_name():
    cls, row = _join_row(_sieges_view(["nanyang_road"]))
    assert cls == "" and row.count('data-act="choose"') == 1  # 一顆的照舊（FB-105 的排法，一個像素都不變）


def test_fb553_stacked_row_takes_its_own_line():
    """.pick 那一排另起一行、一顆一行、鈕佔滿那一行（字長也只往下折，不往右撐）。"""
    css = (ROOT / "web" / "style.css").read_text(encoding="utf-8").split("@media (min-width: 641px)")[0]
    assert ".scene .muster-join.pick { flex-basis: 100%; flex-direction: column; }" in css
    assert re.search(r"\.scene \.muster-join\.pick \.btn \{ width: 100%; min-width: 0;", css)


# ── 見聞「形勢」頁（乙）──

ESSAYS = {"on": True, "pending": False, "essays": [
    {"n": 2, "title": "天下形勢・第 2 篇", "time": "第 2 週・週二 22:00", "line": "是日：黃巾軍拿下南陽官道", "essay": "第一段。\n第二段。"},
    {"n": 1, "title": "天下形勢・第 1 篇", "time": "第 2 週・週一 22:00", "line": "是日：各路按兵，未見勝負", "essay": "<b>舊</b>的一篇。"},
]}


def test_one_row_per_essay_newest_open():
    html = page(ESSAYS)["page"]
    rows = re.findall(r"<details class=\"xs-essay\"[^>]*>", html)
    assert len(rows) == 2 and " open" in rows[0] and " open" not in rows[1]  # 最新一篇攤開、其餘收著
    assert html.index("黃巾軍拿下南陽官道") < html.index("各路按兵")  # 新的在上
    assert "第 2 週・週二 22:00" in html  # 一行是「是日：…」＋時刻
    assert "<p>第一段。</p><p>第二段。</p>" in html  # 一段一個 <p>
    assert "&lt;b&gt;舊&lt;/b&gt;" in html  # 文章照字跳脫


def test_opened_and_closed_rows_are_remembered():
    html = page(ESSAYS, open_=[[1, True], [2, False]])["page"]
    rows = re.findall(r"<details class=\"xs-essay\"[^>]*>", html)
    assert " open" not in rows[0] and " open" in rows[1]


def test_empty_and_pending_and_off():
    assert "天下尚無定論。" in page({"on": True, "pending": False, "essays": []})["page"]
    assert "史官還在落筆" in page({"on": True, "pending": True, "essays": []})["page"]
    assert page(None)["page"] == "" and "載入中" in webharness.run(PAGE, {"m": {}, "x": None})["page"]


def test_tab_only_when_on_and_two_rows_for_nine():
    off = page(m={})["seg"]
    assert 'data-news="xingshi"' not in off and "wrap" not in off  # 關著的季：照舊一排八顆
    on = page(m={"xingshi": True})["seg"]
    assert 'data-news="xingshi"' in on and 'class="seg news-seg wrap"' in on
    names = re.findall(r'data-news="(\w+)"', on)
    assert names[:3] == ["reports", "trends", "xingshi"] and len(names) == 9  # 排在「大勢」後面
    css = (ROOT / "web" / "style.css").read_text(encoding="utf-8")
    phone = css.split("@media (min-width: 641px)")[0]
    assert ".news-seg.wrap { flex-wrap: wrap;" in phone  # 手機：兩排、不橫捲
    assert ".news-seg.wrap button { flex: 1 0 calc(20% - 3px);" in phone


@pytest.mark.slow
def test_real_view_renders():
    import calendar as pycal
    from datetime import datetime

    def tw(h, mi=0, d=20):
        return float(pycal.timegm(datetime(2026, 10, d, h, mi).timetuple())) - 8 * 3600

    game = join(conquest_game("season21", xingshi=True), "huang")
    for now in (tw(10), tw(22, 1), tw(22, 20)):
        game.now = now
        game._conquest_tick()
        game.state.world = game.world.get_season()
    view = game.xingshi_view()
    assert len(view["essays"]) == 1
    out = page(view, m={"xingshi": True})
    assert "天下形勢・第 1 篇" in out["page"] and "是日：" in out["page"]
    assert server.main_view(game).get("xingshi") is True
