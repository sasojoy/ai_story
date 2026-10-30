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
import json
from test_seal_web import DRIVER, _seal_admin, _sheet, m  # noqa: F401  m 是夾具
import test_map_web
from conquest_kit import conquest_game, go, join, plain_game
from tianxia import atlas, conquest, mapview
from conftest import classic_rules, real_content
import math
import random
from conquest_kit import conquest_rules
from tianxia import territory
from tianxia.engine import Game
from tianxia.models import FactionDef, FactionInk
from tianxia.sqlite_world import open_world
from tianxia.state import TerritoryState
from conquest_kit import announce
from tianxia import conquest, conquest_day, siege
from tianxia.state import DayNote, SiegeSlot

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
ROOT = Path(__file__).parents[2]
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
const S = { main: input.m || {}, news: input.news || "reports", xingshiOpen: input.open ? new Map(input.open) : null };
const many = (name) => src.match(new RegExp(`\\n  const ${name} = \\[[\\s\\S]*?\\n  \\];`))[0]; // 多行的 const：konst 抓不到，照原文切
const H = new Function("S", [
  konst("esc"), many("NEWS"), many("NEWS_PARTS"), many("SELF_NEWS"), konst("newsPart"), konst("selfNews"), konst("XS_EMPTY"), konst("XS_PENDING"),
  fn("xingshiParas"), fn("xingshiHtml"), fn("newsSegHtml"),
  "return { xingshiHtml, newsSegHtml };",
].join("\n"))(S);
finish({ page: input.x === undefined ? "" : H.xingshiHtml(input.x), seg: H.newsSegHtml(input.m || {}) });
"""


def strip(html: str, s):
    return webharness.run(STRIP, {"html": html, "s": s})


def page(x=None, m=None, open_=None, news=None):
    payload = {"m": m or {}, "open": open_, "news": news}
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


@pytest.mark.slow
def test_scene_does_not_repeat_the_strip():
    """PM（第三批 A 回報之後）：有攻城那一條時，場景第二行「某軍攻某地；守方：某某。」不再寫一次（引擎 siege.scene_note）。"""
    m = _sieges_view(["nanyang_road"])
    assert m["siege"]["parts"][0].startswith(siege.BANNER_DEFENDER.format(who=""))
    assert "；守方：" not in m["scene"] and "官軍攻南陽官道" not in m["scene"]


@pytest.mark.slow
def test_melee_scene_keeps_only_the_rule():
    """三方混戰：誰攻、守方是誰也拿掉，只留那一條沒說到的規矩（誰補上最後一刀誰拿下）。"""
    game = go(join(conquest_game("season21"), "huang"), "nanyang_road")
    game.now = NOW
    slot = announce(game, "nanyang_road", "huang", merged=("guan", "huang"))
    w = game.state.world
    slot.muster_at, slot.at, slot.status = w.time, w.time + 1800, "waiting"
    game._save_season()
    siege.open_waiting(game.world, game.content, NOW)
    game.state.world = game.world.get_season()
    scene = server.main_view(game)["scene"]
    assert siege.MELEE_RULE in scene and "兩頭迎戰" not in scene


def _rule(css: str, selector: str) -> dict[str, str]:
    found = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert found, f"style.css 裡找不到 {selector}"
    return {k.strip(): v.strip() for k, v in (part.split(":", 1) for part in found.group(1).split(";") if ":" in part)}


def _top(margin: str) -> float:
    """margin 簡寫的上邊（"-8px 0" → -8；"-4px 0 -8px" → -4）。"""
    return float(margin.split()[0].removesuffix("px"))


def test_fb576_single_join_button_clears_the_strip():
    """FB-576（QA 第三批 A）：只有一顆加入鈕的攻城集結，攻城條自己佔一行、「報名在這裡」與鈕排在它底下；鈕照 FB-105 的 −8px 往上吃，
    6px 的列距吃掉還多 2px，鈕的上緣壓到條的下緣（375／360／320 都量到 2px）。條底下那一排的鈕上邊至少留 2px：
    列距（.muster-head 的 gap 第一個值）＋鈕的 margin-top ≥ 2。名字旁邊的那一顆（沒有攻城條、FB-105）、.wide、.pick 不動。"""
    css = re.sub(r"/\*.*?\*/", "", (ROOT / "web" / "style.css").read_text(encoding="utf-8"), flags=re.S)
    phone = css.split("@media (min-width: 641px)")[0]
    gap = float(_rule(phone, ".scene .muster-head")["gap"].split()[0].removesuffix("px"))
    found = re.search(r"\.scene \.muster-head > p\.siege-strip ~ \.muster-join:not\(\.wide\):not\(\.pick\) \.btn\s*\{([^}]*)\}", phone)
    margin = found.group(1) if found else ""
    top = _top(margin.split("margin-top:")[1].split(";")[0]) if "margin-top:" in margin else _top(_rule(phone, ".scene .muster-join .btn")["margin"])
    assert gap + top >= 2, (gap, top)  # 修前 6 − 8 = −2：壓到 2px
    assert _rule(phone, ".scene .muster-join .btn")["margin"] == "-8px 0"  # 名字旁邊的那一顆照舊（FB-105）
    assert _rule(phone, ".scene .muster-join.wide .btn")["margin"] == "0" and _rule(phone, ".scene .muster-join.pick .btn")["margin"] == "0"


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
    """減法季批 1：見聞五顆籤（大事、傳聞、榜單、江湖史、紀錄；Joy 2026-10-24 榜單回見聞），大事底下一排小的：戰報、大勢，形勢只有開著的季才有、
    排在大勢後面；紀錄底下分紀錄、名帖匣。"""
    off = page(m={})["seg"]
    assert 'data-news="xingshi"' not in off
    on = page(m={"xingshi": True})["seg"]
    assert 'data-news="xingshi"' in on and 'class="seg news-sub"' in on
    names = re.findall(r'data-news="(\w+)"', on)
    assert names == ["reports", "rumors", "boards", "chronicle", "journal", "reports", "trends", "xingshi"]
    assert 'data-news="xingshi"' not in page(m={"xingshi": True}, news="rumors")["seg"]  # 別的籤底下沒有那一排
    journal = re.findall(r'data-news="(\w+)"', page(m={"xingshi": True}, news="mingtie")["seg"])
    assert journal == ["reports", "rumors", "boards", "chronicle", "journal", "journal", "mingtie"]


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


# ── FB-578：形勢頁開著時，新的一篇與「還在落筆」要自己換上 ──

REFRESH = r"""
const S = { tab: input.tab, news: input.news, main: input.now };
const calls = [];
const H = new Function("S", "calls", [
  "const shopPolled = () => false;",
  "const sealActPolled = () => {};",  // 玉璽碎片改版第 2 批合進來時補：refreshPage 第一行換獨門行動那一層（沒開著就什麼都不做）
  "const pageKey = (m) => JSON.stringify(m.page || '');",
  "let pointerHeld = false, redrawHeld = false;",
  "const renderPage = () => calls.push('renderPage');",
  "const paintSealWhen = () => calls.push('paintSealWhen');",
  "const redrawPage = () => calls.push('redrawPage');",
  "const loadXingshi = async () => { calls.push('loadXingshi'); };",
  fn("refreshPage"),
  "return { refreshPage };",
].join("\n"))(S, calls);
H.refreshPage(input.old).then(() => finish(calls));
"""


def _refresh(old: dict, now: dict, news: str = "xingshi", tab: str = "news") -> list[str]:
    return webharness.run(REFRESH, {"old": old, "now": now, "news": news, "tab": tab})


def test_fb578_open_page_reloads_when_the_marker_moves():
    """輪詢拿到的 main 裡 xingshi_mark（最新一篇的篇次＋有沒有一張還在寫）變了，停在見聞「形勢」的頁面就重抓 /api/xingshi。
    修前輪詢不碰它：管理者開了一篇、伺服器一秒內寫好，那一頁等了 25 秒還是舊的，「史官還在落筆」也不會自己換成文章。"""
    assert _refresh({"xingshi_mark": "6"}, {"xingshi_mark": "6+"}) == ["loadXingshi"]  # 開了一張新單：換上「還在落筆」
    assert _refresh({"xingshi_mark": "6+"}, {"xingshi_mark": "7"}) == ["loadXingshi"]  # 寫好了：換上第 7 篇
    assert _refresh({"xingshi_mark": "7"}, {"xingshi_mark": "7"}) == []  # 沒變：不重抓、不重畫
    assert _refresh({"xingshi_mark": "6"}, {"xingshi_mark": "7"}, news="rumors") == []  # 別的子分頁不抓（那幾欄沒變也不重畫）


@pytest.mark.slow
def test_fb578_main_view_carries_the_marker():
    """main_view 的 xingshi_mark：收下的最新一篇的篇次，有一張還在寫就多一個「+」。關著的季沒有這個鍵（一個位元組都不變）。"""
    import calendar as pycal
    from datetime import datetime

    def tw(h, mi=0, d=20):
        return float(pycal.timegm(datetime(2026, 10, d, h, mi).timetuple())) - 8 * 3600

    game = join(conquest_game("season21", xingshi=True), "huang")
    marks = []
    for now in (tw(10), tw(22, 1), tw(22, 20)):  # 起點、開單、過了寬限照固定段收
        game.now = now
        game._conquest_tick()
        game.state.world = game.world.get_season()
        marks.append(server.main_view(game)["xingshi_mark"])
    assert marks == ["0", "0+", "1"]
    off = join(conquest_game("season21"), "huang")  # 〈天下形勢〉關著
    assert "xingshi_mark" not in server.main_view(off) and "xingshi" not in server.main_view(off)


# ── 原 test_conquest_seal_web.py（整檔搬進來） ──
# 領地爭奪第三批 B（計畫 Task 14）的網頁那一半：管理者「玉璽」一組，領地爭奪的季「強制現世」換成「現在藏一片」。
# 餵 Game.admin_seal_choices 給的 hide 旗標給 app.js（tests/test_seal_web.py 的假瀏覽器）。沒有 node 就略過。

def _admin(hide: bool) -> dict:
    admin = _seal_admin()
    admin["seal"]["hide"] = hide
    return admin


def test_the_admin_button_says_hide_now_in_a_conquest_season(m):  # noqa: F811
    sheet = _sheet(m, _admin(True))
    assert "現在藏一片" in sheet and 'data-op="seal_emerge" data-hide="1"' in sheet and "強制現世" not in sheet
    old = _sheet(m, _admin(False))
    assert "強制現世（下一場）" in old and "data-hide" not in old and "現在藏一片" not in old


def test_the_hide_button_asks_its_own_question_then_posts_the_same_route(m):  # noqa: F811
    from test_admin_triggers_web import CLICK

    clicks = [{"act": "admin", "op": "seal_emerge", "hide": "1"}, {"act": "admin", "op": "seal_emerge"}]
    script = CLICK.replace("input.clicks", json.dumps(clicks))
    out = webharness.run(DRIVER, {"m": {**m, "admin": True}, "script": script, "S": {"admin": _admin(True), "sheet": True},
                                  "menxia": None, "stored": {}, "responses": {"/api/do/": {"main": m, "message": "好了"}}})
    assert "藏進一塊開季中立的區塊" in out["asked"][0] and "不公開" in out["asked"][0] and "決戰" not in out["asked"][0]
    assert "現世" in out["asked"][1] and "下一場" in out["asked"][1]  # 舊的問句一個字沒動
    assert [c[0] for c in out["calls"] if c[0].startswith("/api/do/")] == ["/api/do/seal_emerge", "/api/do/seal_emerge"]


# ── 原 test_conquest_mapview.py（整檔搬進來） ──
# 領地爭奪第一批：輿圖上的中立地（計畫三、Task 6 最後一段）。網頁那一條在輿圖第三版第 4 批改寫：中立地的虛線圈拿掉了（輿圖簡化設計 5.4），
# 區圖上是灰的印章框加朱印「寶」。舊的 SVG（render_map）那幾條照舊。

def _game():
    return go(join(conquest_game("season21"), "guan"), "yingchuan")


def test_map_state_marks_neutral_blocks():
    game = _game()
    places = game.map_state()["places"]
    assert places["nanyang_wilds"]["kind"] == "neutral" and places["nanyang_wilds"]["control"] is None
    assert places["yingshui"]["kind"] == "line" and places["changshe"]["kind"] == "base"
    assert places["guangzong"]["kind"] == "fixed"
    conquest.set_control(game.state.world, game.content, "nanyang_wilds", "huang")
    places = game.map_state()["places"]
    assert places["nanyang_wilds"]["kind"] == "neutral" and places["nanyang_wilds"]["control"] == "huang"


def test_detail_line_says_neutral():
    game = _game()
    s, c = game.state, game.content
    assert conquest.NEUTRAL_LINE in atlas.detail_text(s, c, "nanyang_wilds", game.odds)
    conquest.set_control(s.world, c, "nanyang_wilds", "huang")
    assert conquest.NEUTRAL_HELD in atlas.detail_text(s, c, "nanyang_wilds", game.odds)


def test_old_svg_paints_the_neutral_disc_and_legend():
    game = _game()
    svg = mapview.render_map(game.state, game.content, "situation")
    assert mapview.CONTROL_DISC["neutral"] in svg
    assert mapview.LEGEND_NEUTRAL in mapview.legend_data(game.state, game.content, "situation")["layer"]


def test_crossed_swords_on_every_block_you_can_attack():
    game = _game()
    armed = mapview.armed_places(game.state, game.content)
    assert {"yu_river", "hilltop_wilds", "runan", "xinye"} <= armed  # 中立地、黃巾的陣營區塊（城鎮照控制方的巡邏；區塊表 v3）
    assert not armed & {"yingchuan", "changshe", "zhuo_county", "haozu_fort"}  # 自家的、不是區塊的


@pytest.mark.slow  # 單一條超過一秒（2026-10-27 測試整理 4 量的）
def test_ropes_hang_no_beads_without_tug_of_war():
    """領地爭奪沒有拔河：輿圖總覽的三條戰線照舊寫值，繩上不掛照門檻擺的地點（舊拔河 2026-10-27 拿掉，沒有「關著照舊掛」了）。"""
    ropes = _game().map_state()["ropes"]
    assert len(ropes) == 3 and all(r["beads"] == [] for r in ropes)


MARKS = "return H.marksHtml(H.S.mapBase, H.S.mapState, { z: 1, x: 0, y: 0 }, { vw: 2400, vh: 3600 });"


@pytest.mark.slow  # 單一條超過一秒（2026-10-27 測試整理 4 量的）
@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_web_map_draws_unheld_neutral_without_a_side_seal_but_with_the_treasure():
    """還沒人佔的中立地：地是淡灰、小圖左上角一顆「寶」；被佔下地換成佔領方的顏色、寶照樣在（開季中立的，不管此刻誰佔著）。
    名字旁沒有哪一方的小印、沒有「寶」字條（輿圖表現第二版 W1：誰的看地的顏色，寶是徽）。卡上那一句寫「中立・高級資源領地，還沒有人佔」。"""
    game = _game()
    ink = {s["id"]: s for s in game.map_base()["world"]["sides"]}
    p = next(b for b in game.map_base()["places"] if b["id"] == "nanyang_wilds")
    badge = f'<i class="mv-bd mv-bd-rich" style="left:{p["x"] - 11}px;top:{p["y"] - 10}px">寶</i>'
    both = "return [" + MARKS[len("return "):-1] + ", H.groundSvg(H.S.mapBase, H.S.mapState, 1, H.S.mapState.now_week)];"
    out, ground = test_map_web.run(game, both)
    lab = test_map_web._lab(out, "nanyang_wilds")
    assert 'class="mv-side"' not in lab and "mv-rich" not in lab and badge in out
    assert re.search(r'<path class="ld-fill" data-cell="nanyang_wilds" d="[^"]*" fill="#B9B2A0" fill-opacity="0.1"/>', ground)
    card = test_map_web.run(game, 'return H.placeCard(H.S.mapBase, H.S.mapState, "nanyang_wilds");')
    assert "中立・高級資源領地，還沒有人佔" in card
    conquest.set_control(game.state.world, game.content, "nanyang_wilds", "huang")
    out, ground = test_map_web.run(game, both)
    held = test_map_web._lab(out, "nanyang_wilds")
    assert 'class="mv-side"' not in held and "mv-rich" not in held and badge in out
    assert re.search(rf'<path class="ld-fill" data-cell="nanyang_wilds" d="[^"]*" fill="{ink["huang"]["color"]}" fill-opacity="0.34"/>', ground)


# ── 原 test_conquest_siege_map_web.py（整檔搬進來） ──
# 輿圖第三版第 5 批：攻城戰的三種時刻在輿圖上（企劃者 2026-10-22 從對比圖 docs/superpowers/specs/2026-10-20-輿圖簡化-草圖/v5-接縫/
# 挑 A 乙、B 甲、C 甲；計畫 docs/superpowers/plans/2026-10-22-輿圖v3-接縫.md 第六節）：
# - A 戰書下了、還沒開集結：地圖上名字旁一枚「戰」字印；遠看的地面那一格一圈朱紅虛線框。
# - B 集結・交戰中：地面那一格借激戰的紅光、地點外一圈紅（一閃一閃）。（一張到底，2026-10-30：以前的區圖、天下圖合成一張）
# - C 打完（到換天）：地圖不另畫（剛易手本來就畫）。
# - 三種時刻卡上第 2 段底下一段「戰書／攻城／攻城戰果」；攻城那一顆鈕照看的人站哪一格（攻方、守方、散人與不是兩軍的人、另一軍站不進去）。
# 資料：疊層 places[id].siege（mapdata.flip_marks：letter／fight），main_view 的 conquest.today（sides、you、margin）與 conquest.muster。

CARD = 'return Object.fromEntries(["runan_wilds", "yingchuan_wilds", "hilltop_wilds", "changshe"].map((id) => [id, H.placeCard(H.S.mapBase, H.S.mapState, id)]));'


def _sgame(profile="week7", faction="guan", at="yingchuan", content=None):
    """領地爭奪的一局（正式內容）：開季、算好地盤，你站在 at。"""
    c = content or real_content(profile)
    conquest_rules(c)
    c.config.auto_open_first_season = True
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    territory.update(game.state.world, c)
    game.state.player.faction, game.state.player.location = faction, at
    return game


def _moments(game):
    """三種時刻各擺一處（同對比圖）：A 汝南荒野（中立）官軍推 65 下了戰書；B 潁川郊野（官軍的）黃巾推 62、集結・交戰中（真的開一場集結：
    siege.open_waiting；FB-690 的 join 照江湖頁的加入判斷，要有那一場）；
    C 荒丘（中立）官軍的攻城戰打贏（大勝）、剛易手。回三場（時程表那一筆，存檔重讀之後的）。"""
    game.now = game.now or NOW
    w, c = game.state.world, game.content
    conquest.push(w, c, "runan_wilds", "guan", "映雪", 65, "attack")
    announce(game, "runan_wilds", "guan")
    conquest.push(w, c, "yingchuan_wilds", "huang", "黃天客", 62, "attack")
    b = announce(game, "yingchuan_wilds", "huang", minute=20 * 60)
    b.muster_at, b.at, b.status = w.time, w.time + 1800, "waiting"
    key = w.conquest.settled_key
    d = SiegeSlot(id="done-hilltop", key=key, loc="hilltop_wilds", minute=12 * 60, at=w.time - 600, muster_at=w.time - 2400,
                  attackers=["guan"], by={"guan": conquest_day.LETTER}, reasons={"guan": "官帥"}, status="done", winner="guan")
    w.conquest.schedule.append(d)
    conquest.flip(w, c, "hilltop_wilds", "guan", note=False)
    w.conquest.day_log.append(DayNote(key=key, side="guan", loc="hilltop_wilds", minute=12 * 60, by=conquest_day.LETTER, reason="官帥",
                                      result="taken", taken="guan", margin="大勝", keeper="guard", attackers=["guan"]))
    game._save_season()
    siege.open_waiting(game.world, c, game.now)
    game.state.world = game.world.get_season()
    slots = {s.loc: s for s in game.state.world.conquest.schedule}
    assert slots["yingchuan_wilds"].status == "open" and slots["yingchuan_wilds"].record_id is not None
    return slots["runan_wilds"], slots["yingchuan_wilds"], slots["hilltop_wilds"]


# ── 伺服器給的資料 ──
def test_the_map_overlay_says_which_siege_moment_each_block_is_in():
    """疊層 places[id].siege：戰書下了、還沒開集結是 letter，集結・交戰中是 fight，打完、沒有戰書是 None；不是區塊的地點沒有這個鍵。"""
    game = _sgame(profile="season21")
    _moments(game)
    places = game.map_state()["places"]
    assert places["runan_wilds"]["siege"] == "letter" and places["yingchuan_wilds"]["siege"] == "fight"
    assert places["hilltop_wilds"]["siege"] is None and places["yingchuan"]["siege"] is None
    assert "siege" not in places["cao_manor"]


@pytest.mark.parametrize("faction,expect", [
    ("guan", {"runan_wilds": "attack", "yingchuan_wilds": "defend"}),  # 官軍：自己下的戰書、自家的塊被打
    ("huang", {"runan_wilds": "", "yingchuan_wilds": "attack"}),  # 黃巾：官軍單方攻中立地站不進去
    (None, {"runan_wilds": "help", "yingchuan_wilds": "help"}),  # 散人：臨時投效或助守
])
def test_today_rows_say_where_the_viewer_stands(faction, expect):
    """conquest.today 每一場多 sides（攻方的陣營 id）、you（看的人站得進哪一格，siege.slots 同一套）、margin（打完的大勝／險勝）；muster 是開打前幾分鐘集結。"""
    game = _sgame(profile="season21", faction=faction)
    _moments(game)
    view = game.conquest_view()
    rows = {r["loc"]: r for r in view["today"]}
    assert {loc: rows[loc]["you"] for loc in expect} == expect
    assert rows["runan_wilds"]["sides"] == ["guan"] and rows["yingchuan_wilds"]["sides"] == ["huang"]
    assert rows["hilltop_wilds"]["margin"] == "大勝" and rows["runan_wilds"]["margin"] == "" and rows["hilltop_wilds"]["status_text"] == "官軍拿下"
    assert view["muster"] == game.content.config.conquest.muster_minutes == 30


# ── 卡 ──
@pytest.mark.slow  # 單一條超過一秒（2026-10-27 測試整理 4 量的）
def test_the_card_has_a_section_for_each_siege_moment():
    """官軍看：A「戰書」誰約戰、幾點、開打前幾分鐘集結、凍結；B「攻城」狀態字、幾點開打、「去守城」回江湖頁；C「攻城戰果」誰拿下、大勝、
    「看戰報」開見聞的戰報。「正在翻」底下不再多一行「已下戰書」（寫在上面那一段）。沒有攻城的地方沒有這一段。"""
    game = _sgame(profile="season21")
    a, b, _ = _moments(game)
    cards = test_map_web.run(game, CARD)
    letter, fight, done = cards["runan_wilds"], cards["yingchuan_wilds"], cards["hilltop_wilds"]
    assert 'data-siege="letter"' in letter and "<h4>戰書</h4>" in letter
    assert f"官軍約戰 <b>{game.stamp(a.at)}</b>；開打前 30 分鐘在這一帶集結，人要在潁川汝南才加得進去。這一塊的進度凍結到打完。" in letter
    assert 'data-siege="fight"' in fight and "<h4>攻城</h4>" in fight
    assert f"黃巾軍攻潁川郊野：<b>集結・交戰中</b>（{game.stamp(b.at)} 開打）。你在潁川汝南，加得進去。" in fight
    assert re.search(r'<button type="button" class="main" data-act="tab" data-tab="jianghu">去守城<small>回江湖頁</small></button>', fight)
    assert 'data-siege="done"' in done and "<h4>攻城戰果</h4>" in done and "那一仗：<b>官軍拿下</b>（大勝）。" in done
    assert 'data-act="map-report">看戰報' in done
    for card in (letter, fight, done):
        assert "已下戰書" not in card and card.index('class="m-line"') < card.index("m-siege") < card.index('class="m-foes"')
        if "正在翻" in card:
            assert card.index("m-siege") < card.index("正在翻")
    assert "m-siege" not in cards["changshe"]


def test_the_fight_button_follows_where_the_viewer_stands():
    """攻城那一顆鈕：攻方「去加入攻城」；另一軍站不進去（官軍單方攻中立地時的黃巾）不畫鈕、寫站不進去。（一個測試只開一季：散人另一條）"""
    huang = _sgame(profile="season21", faction="huang")
    _moments(huang)
    cards = test_map_web.run(huang, CARD)
    assert ">去加入攻城<small>" in cards["yingchuan_wilds"]
    assert "這一場你這一邊站不進去。" in cards["runan_wilds"] and "才加得進去" not in cards["runan_wilds"]


@pytest.mark.slow  # 單一條超過一秒（2026-10-27 測試整理 4 量的）
def test_a_loner_lends_a_hand():
    """散人「去助陣」（臨時投效或助守）。"""
    loner = _sgame(profile="season21", faction=None)
    _moments(loner)
    assert ">去助陣<small>" in test_map_web.run(loner, CARD)["yingchuan_wilds"]


@pytest.mark.slow  # 單一條超過一秒（2026-10-27 測試整理 4 量的）
def test_fb690_join_follows_whether_you_can_join_from_where_you_are():
    """FB-690：集結・交戰中那一場，卡上那顆「去…」只給此刻加得進去的人（跟江湖頁的加入鈕同一套 Game._joinable：人在那一區、不在路上、
    還沒在任何一場的名單上）。人在別區（QA：黃巾的人站汝南看涿郡那一場）：不畫那一顆，寫要到哪一區、走到那裡幾分；已經在這一場：
    「看戰況」；資料 join 是 go／far／in。"""
    from conquest_kit import go, join

    game = join(_sgame(profile="season21", at="wan_city"), "guan")  # 官軍站宛城（南陽）；一個測試只開一季，同一局搬人
    _moments(game)
    row = next(r for r in game.conquest_view()["today"] if r["loc"] == "yingchuan_wilds")
    assert (row["you"], row["join"], row["region"]) == ("defend", "far", "潁川汝南")
    minutes = game.map_state()["places"]["yingchuan_wilds"]["minutes"]
    card = test_map_web.run(game, CARD)["yingchuan_wilds"]
    assert f"人要在潁川汝南才加得進去（走到這裡步行 {minutes} 分）。" in card
    assert "去守城" not in card and "去加入攻城" not in card and "去助陣" not in card  # 修前照樣寫「去守城」、按了回江湖頁插不上手
    assert 'data-act="map-travel" data-mode="walk"' in card  # 走過去的鈕在卡的動作那一排
    near = go(game, "yingchuan")  # 走到潁川郡（潁川汝南）：加得進去
    assert next(r for r in near.conquest_view()["today"] if r["loc"] == "yingchuan_wilds")["join"] == "go"
    assert ">去守城<small>" in test_map_web.run(near, CARD)["yingchuan_wilds"]
    # 已經在這一場：照江湖頁的加入鈕加入，卡上換成「看戰況」
    opt = next(o for o in near.options() if o.id.startswith("battle:join:") and o.enabled)
    near.choose(opt.id)
    near.state.world = near.world.get_season()
    assert next(r for r in near.conquest_view()["today"] if r["loc"] == "yingchuan_wilds")["join"] == "in"
    card = test_map_web.run(near, CARD)["yingchuan_wilds"]
    assert "你已經在這一場的名單上。" in card and ">看戰況<small>回江湖頁</small>" in card and "去守城" not in card


@pytest.mark.parametrize("faction,mine", [("huang", []), ("guan", ["guan"])])
def test_fb693_the_other_army_is_not_marked_as_us_on_the_siege_gauge(faction, mine):
    """FB-693（第二批就有）：官軍單方攻中立地，守將借的是黃巾那一格；黃巾的人（站不進這一場）看江湖頁的戰局條，兩邊都不標「我方」
    （修前守軍那一邊標「我方」）；官軍的人照舊是官軍那一邊「我方」。"""
    from conquest_kit import join

    game = join(_sgame(profile="season21", faction=faction), faction)  # 站潁川郡：汝南荒野那一場在同一區
    game.now = NOW
    w, c = game.state.world, game.content
    conquest.push(w, c, "runan_wilds", "guan", "映雪", 65, "attack")
    slot = announce(game, "runan_wilds", "guan")
    slot.muster_at, slot.at, slot.status = w.time, w.time + 1800, "waiting"
    game._save_season()
    siege.open_waiting(game.world, c, game.now)
    game.state.world = game.world.get_season()
    g = game.battle_gauge()
    assert g is not None and g["name"].startswith("攻城")
    assert [x["id"] for x in (g["left"], g["right"]) if x["mine"]] == mine


@pytest.mark.slow  # 單一條超過一秒（2026-10-27 測試整理 4 量的）
def test_a_void_siege_has_no_section():
    game = _sgame(profile="season21")
    a, _, _ = _moments(game)
    a.status = "void"
    assert "m-siege" not in test_map_web.run(game, CARD)["runan_wilds"]


def test_the_report_button_opens_the_reports_page():
    """「看戰報」：換到見聞、戰報那一頁（S.news）。"""
    src = webharness.APP.read_text(encoding="utf-8")
    assert re.search(r'case "map-report": S\.news = "reports"; await goTab\("news"\);', src)


# ── 地圖 ──
@pytest.mark.slow  # 單一條超過一秒（2026-10-27 測試整理 4 量的）
def test_the_map_seal_for_a_letter_and_a_ring_for_a_fight():
    """A：汝南荒野的戰書畫在地上（朱紅虛框，下一條），名字旁不再掛「戰」字印（輿圖表現第二版 W1）；B：潁川郊野外一圈紅（.mv-fight）、
    小圖右上一顆 ⚔；C：荒丘不另畫。正在翻的（A 官軍推了 65）也掛 ⚔。名字照舊寫。"""
    game = _sgame(profile="season21")
    _moments(game)
    out = test_map_web.run(game, MARKS)
    assert test_map_web._lab(out, "runan_wilds") and "戰</span>" not in out and "mv-rich" not in out
    pts = {p["id"]: (p["x"], p["y"]) for p in game.map_base()["places"]}
    rings = [tuple(float(v) for v in m) for m in re.findall(r'<i class="mv-fight" style="left:([-\d.]+)px;top:([-\d.]+)px">', out)]
    assert rings == [tuple(float(v) for v in pts["yingchuan_wilds"])]
    swords = {(float(x), float(y)) for x, y in re.findall(r'<i class="mv-bd mv-bd-x" style="left:([-\d.]+)px;top:([-\d.]+)px">⚔</i>', out)}
    at = lambda loc: (pts[loc][0] + 11, pts[loc][1] - 10)  # noqa: E731（小圖右上角）
    assert at("yingchuan_wilds") in swords and at("runan_wilds") in swords and at("hilltop_wilds") not in swords


@pytest.mark.slow  # 單一條超過一秒（2026-10-27 測試整理 4 量的）
def test_the_ground_dashed_frame_for_a_letter_and_the_clash_glow_for_a_fight():
    """A：地面汝南荒野那一塊內側一圈朱紅虛線框（.w-letter）；B：潁川郊野不再借激戰的紅底（輿圖表現第二版 W1 拿掉 .w-melee：地的語言只有
    顏色、斜紋、框；激戰看小圖上的閃圈與 ⚔）；C：荒丘剛易手，內框改成虛線（.w-cool）。看以前的週（版圖變化）都不畫。"""
    game = _sgame(content=real_content("season21"))
    _moments(game)
    now, past = test_map_web.run(game, "return [1, 0].map((w) => H.groundSvg(H.S.mapBase, H.S.mapState, 1, w ? H.S.mapState.now_week : 0));")
    assert re.search(r'<path class="w-letter" data-cell="runan_wilds"[^>]*stroke-dasharray', now)
    assert "w-melee" not in now and "w-melee" not in past
    assert re.findall(r'<path class="w-letter" data-cell="([^"]+)"', now) == ["runan_wilds"]
    assert re.search(r'<path class="w-cool" data-cell="hilltop_wilds"[^>]*stroke-dasharray', now)
    assert "w-letter" not in past and "w-cool" not in past


def _four_sides():
    """四方的測試劇本（設計 3.3、第十二章）：官軍、黃巾之外加魏、吳（各自的顏色）；潁川汝南的地點照方位分給四方。"""
    c = real_content("week7")
    c.scenario.factions = [f for f in c.scenario.factions if f.id != "haoqiang"] + [
        FactionDef(id="wei", name="魏", ink=FactionInk(color="#6A3D7A", soft="#C3A6CC", tint="#EADCEF", short="魏", label="魏")),
        FactionDef(id="wu", name="吳", ink=FactionInk(color="#2E7D5B", soft="#9FD1B8", tint="#DCEFE5", short="吳", label="吳")),
    ]
    c.scenario.territory.lines = {}
    c.config.auto_open_first_season = True
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    territory.update(game.state.world, c)
    game.state.player.faction, game.state.player.location = "guan", "yingchuan"
    sides = ["guan", "huang", "wei", "wu"]
    mine = [p["id"] for p in game.map_base()["places"] if p["region"] == "yingru"]
    cx = sum(c.locations[x].x for x in mine) / len(mine)
    cy = sum(c.locations[x].y for x in mine) / len(mine)
    control = {x: sides[int(((math.atan2(c.locations[x].y - cy, c.locations[x].x - cx) + math.pi / 4) % (2 * math.pi)) // (math.pi / 2))] for x in mine}
    game.state.world.territory = TerritoryState(control=control)
    return game, control


def test_four_sides_marks_do_not_take_any_sides_colour():
    """四方的測試劇本（設計 3.3）：魏攻吳佔著的那一處下了戰書——地面照樣一圈朱紅虛線（不照任何一方的顏色），地照吳的顏色填；
    名字旁不再掛「戰」字印與小印（輿圖表現第二版 W1），小圖角上的徽也不照任何一方的顏色。"""
    game, control = _four_sides()
    st = game.map_state()
    target = next(x for x, sd in control.items() if sd == "wu" and x in st["places"])
    st["places"][target]["siege"] = "letter"
    out, ground = test_map_web.run(game, MARKS.replace("return ", "return [").rstrip(";") + ", H.groundSvg(H.S.mapBase, H.S.mapState, 1, H.S.mapState.now_week)];", st=st)
    lab = test_map_web._lab(out, target)
    assert lab and "戰</span>" not in lab and "mv-side" not in lab
    letter = "".join(re.findall(r'<path class="w-letter"[^>]*>', ground))
    assert f'data-cell="{target}"' in letter and 'stroke="#A8322A"' in letter
    assert re.search(rf'<path class="ld-fill" data-cell="{target}" d="[^"]*" fill="#2E7D5B"', ground)
    badges = "".join(re.findall(r'<i class="mv-(?:dg|bd)[^>]*>[^<]*</i>', out))
    for color in ("#6A3D7A", "#2E7D5B", "#3D5F8F", "#B9821A"):
        assert color not in badges and color not in letter, color


def test_the_siege_code_names_no_side():
    """設計 3.3：攻城那幾段（卡上那一段、字印、地面的框）不寫死陣營 id、名字與顏色；顏色只有前線那一種朱紅與字印的紙色。"""
    src = webharness.APP.read_text(encoding="utf-8").replace("\r\n", "\n")
    block = src[src.index("  function siegeOf(id)"):src.index("  // 第 7 段的「下戰書」")]
    for word in ('"guan"', '"huang"', '"haoqiang"', "官軍", "黃巾", "豪強", "MAP_SIDES", "#3D5F8F", "#B9821A"):
        assert word not in block, word
