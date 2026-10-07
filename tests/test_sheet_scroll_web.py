"""設定抽屜在電腦上捲不到管理者工具（企劃者回報「管理者按鈕電腦版看不到，但手機版可以看到」，2026-10-07）。

原因：抽屜（.sheet）在電腦上只有中間 640px 寬、從底部長上來、最高 88vh，自己捲；管理者工具排在一般設定之後，大半在第一屏之下。
滑鼠滾輪只有指標正好在抽屜上才捲得動，兩旁的暗處（.sheet-bg）滾了不會捲抽屜；手機上抽屜滿版，怎麼滑都捲得到。
修法：暗處的滾輪照樣捲抽屜（點暗處照舊關掉抽屜）；管理者的抽屜頂上多一顆「管理者工具 ↓」，按了捲到管理者工具。
審查 M-3：滾輪只掛在暗處（畫抽屜時），不掛整份文件；ctrl＋滾輪（縮放）不攔。審查 M-2：抽屜開著時重畫（查玩家、補抓資料）停在原地。

照 tests/test_prologue_web.py 的做法把整支 app.js 放進 node 的假瀏覽器跑；沒有 node 就略過。"""
from __future__ import annotations

import random

import pytest
from test_prologue_web import run

import server
import webharness
from conftest import real_content
from tianxia.engine import Game

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


def _main(admin: bool):
    content = real_content()
    content.config.auto_open_first_season = True
    content.config.admins = ["掌門"] if admin else []
    game = Game.new(content, "掌門", rng=random.Random(0))
    game.client = None
    main = server.main_view(game)
    assert main["admin"] is admin
    return main


# 暗處（.sheet-bg）的假元素記下掛在它身上的監聽；畫抽屜（render）時才掛上去（審查 M-3：不掛在整份文件上）
WHEEL = """return (async () => {
  const sheet = { top: 0, clientHeight: 600, scrollBy(x, y) { this.top += y; } };
  T.qs[".sheet"] = sheet;
  const bound = [];
  T.qs[".sheet-bg"] = { addEventListener(type, fn, opts) { bound.push({ type, fn, opts }); } };
  H.render();
  const roll = (deltaY, deltaMode = 0, ctrlKey = false) => {
    const ev = { deltaY, deltaMode, ctrlKey, prevented: false, preventDefault() { this.prevented = true; } };
    for (const b of bound) if (b.type === "wheel") b.fn(ev);
    return ev.prevented;
  };
  const backdrop = roll(120);
  const afterBackdrop = sheet.top;
  const zoom = roll(240, 0, true);  // ctrl＋滾輪（觸控板捏合也是）：瀏覽器的縮放，不攔、不捲
  const afterZoom = sheet.top;
  const lines = roll(3, 1);  // 以「行」為單位的滾輪（Firefox）：換成像素
  return {
    bound: bound.map((b) => [b.type, b.opts && b.opts.passive]), document: (T.docListeners.wheel || []).length,
    backdrop, afterBackdrop, zoom, afterZoom, lines, top: sheet.top, open: H.S.sheet,
  };
})();"""


def test_a_wheel_over_the_backdrop_scrolls_the_open_sheet():
    out = run(_main(admin=True), WHEEL, S={"sheet": True})
    assert out["bound"] == [["wheel", False]] and out["document"] == 0  # 只掛在暗處，不是整份文件（審查 M-3）
    assert out["backdrop"] is True and out["afterBackdrop"] == 120  # 擋下頁面自己的捲動、改捲抽屜
    assert out["zoom"] is False and out["afterZoom"] == 120  # ctrl＋滾輪照舊是瀏覽器的縮放
    assert out["lines"] is True and out["top"] == 120 + 3 * 16
    assert out["open"] is True  # 滾輪只捲、不關抽屜（關抽屜是點暗處）


def test_a_wheel_with_no_sheet_open_does_nothing():
    out = run(_main(admin=True), WHEEL, S={"sheet": False})
    assert out["bound"] == [] and out["document"] == 0 and out["backdrop"] is False


# 抽屜開著時整個重畫（render 換掉 #app 的內容，抽屜是新畫的、捲動回到 0）：照原本捲到的地方放回去（審查 M-2）
KEEP = """return (async () => {
  let sheet = { scrollTop: 480 };
  Object.defineProperty(T.qs, ".sheet", { get: () => sheet, configurable: true, enumerable: true });
  let html = "";
  Object.defineProperty(T.els.app, "innerHTML", { get: () => html, set(v) { html = v; sheet = { scrollTop: 0 }; }, configurable: true });
  T.ctx.FormData = function (form) { return Object.entries(form.data); };
  const note = { textContent: "", classList: { toggle() {} } };
  const form = { id: "ad-player-form", data: { name: "沈青衫" }, querySelector: (sel) => (sel === ".form-msg" ? note : null) };
  await T.docListeners.submit[0]({ preventDefault() {}, target: form });
  const afterLookup = sheet.scrollTop;
  // 打開設定：先畫一次（新開的抽屜在頂上），等管理者資料回來時人已經往下捲了 300，補抓完再畫一次
  const fetch = T.ctx.fetch;
  T.ctx.fetch = (url, opts) => { if (url === "/api/admin") sheet.scrollTop = 300; return fetch(url, opts); };
  H.S.sheet = false;
  const el = { dataset: { act: "sheet" }, classList: { contains: () => false } };
  await T.docListeners.click[0]({ target: { closest: () => el } });
  return { afterLookup, afterOpen: sheet.scrollTop, player: H.S.adPlayer && H.S.adPlayer.name };
})();"""


def test_a_redraw_keeps_the_drawer_where_it_was_scrolled():
    view = {"name": "沈青衫", "line": "沈青衫：官軍・鄉勇，在長社", "summons": {"ok": True, "note": "會發第 2 階的召見"},
            "opportunities": [], "fragments": []}
    out = run(_main(admin=True), KEEP, S={"sheet": True, "admin": {"season_one": True, "showdowns": [], "battles": [],
                                                                     "events": [], "trends": [], "timetable": [],
                                                                     "results": [], "locks": []}},
              responses={"/api/admin/player": view, "/api/admin": {"season_one": True, "showdowns": [], "battles": [],
                                                                   "events": [], "trends": [], "timetable": [],
                                                                   "results": [], "locks": []},
                         "/api/prologue": {"text": ""}})
    assert out == {"afterLookup": 480, "afterOpen": 300, "player": "沈青衫"}


def test_the_admin_link_is_drawn_only_for_admins():
    admin = run(_main(admin=True), "return H.sheetHtml();", S={"sheet": True})
    assert 'data-act="to-admin"' in admin and "管理者工具 ↓" in admin and 'id="admin-zone"' in admin
    assert admin.index('data-act="to-admin"') < admin.index("匿名行走")  # 在抽屜頂上，第一屏就看得到
    player = run(_main(admin=False), "return H.sheetHtml();", S={"sheet": True})
    assert "to-admin" not in player and "admin-zone" not in player


def test_the_admin_link_scrolls_the_admin_zone_into_view():
    out = run(_main(admin=True), """return (async () => {
      const seen = [];
      const zone = { scrollIntoView(opts) { seen.push(opts); } };
      const byId = T.ctx.document.getElementById;
      T.ctx.document.getElementById = (id) => (id === "admin-zone" ? zone : byId(id));
      const el = { dataset: { act: "to-admin" }, classList: { contains: () => false } };
      await T.docListeners.click[0]({ target: { closest: () => el } });
      return { seen, sheet: H.S.sheet };
    })();""", S={"sheet": True})
    assert out == {"seen": [{"behavior": "smooth", "block": "start"}], "sheet": True}


def test_a_backdrop_click_still_closes_the_sheet():
    out = run(_main(admin=True), """return (async () => {
      const el = { dataset: { act: "sheet-close" }, classList: { contains: () => false } };
      await T.docListeners.click[0]({ target: { closest: () => el } });
      return H.S.sheet;
    })();""", S={"sheet": True})
    assert out is False
