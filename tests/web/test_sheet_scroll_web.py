"""設定抽屜在電腦上捲不到管理者工具（企劃者回報「管理者按鈕電腦版看不到，但手機版可以看到」，2026-10-07）。

原因：抽屜（.sheet）在電腦上只有中間 640px 寬、從底部長上來、最高 88vh，自己捲；管理者工具排在一般設定之後，大半在第一屏之下。
滑鼠滾輪只有指標正好在抽屜上才捲得動，兩旁的暗處（.sheet-bg）滾了不會捲抽屜；手機上抽屜滿版，怎麼滑都捲得到。
修法：暗處的滾輪照樣捲抽屜（點暗處照舊關掉抽屜）；管理者的抽屜頂上多一顆「管理者工具 ›」（2026-11-01 起連到自己一頁的管理頁 /admin）。
審查 M-3：滾輪只掛在暗處（畫抽屜時），不掛整份文件；ctrl＋滾輪（縮放）不攔。審查 M-2：抽屜開著時重畫（查玩家、補抓資料）停在原地。

照 tests/web/test_prologue_web.py 的做法把整支 app.js 放進 node 的假瀏覽器跑；沒有 node 就略過。"""
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


# 管理頁（/admin，admin.js；Joy 2026-11-01 管理者工具獨立一個網址）整頁重畫（查完一個人、做完一件事）：捲回原本捲到的地方（以前的審查 M-2
# 是設定抽屜裡的管理者區，現在管理頁捲的是整頁）
ADMIN = {"season_one": True, "showdowns": [], "battles": [], "events": [], "trends": [], "timetable": [], "results": [], "locks": []}
KEEP = """return (async () => {
  const went = [];
  T.ctx.window.scrollY = 480;
  T.ctx.window.scrollTo = (x, y) => went.push([x, y]);
  T.ctx.FormData = function (form) { return Object.entries(form.data); };
  const note = { textContent: "", classList: { toggle() {} } };
  const form = { id: "ad-player-form", data: { name: "沈青衫" }, querySelector: (sel) => (sel === ".form-msg" ? note : null) };
  await T.docListeners.submit[0]({ preventDefault() {}, target: form });
  return { went, player: H.S.adPlayer && H.S.adPlayer.name, page: T.els.app.innerHTML.includes('class="ad-shell"') };
})();"""


def test_a_redraw_keeps_the_admin_page_where_it_was_scrolled():
    view = {"name": "沈青衫", "line": "沈青衫：官軍・鄉勇，在長社", "summons": {"ok": True, "note": "會發第 2 階的召見"},
            "opportunities": [], "fragments": []}
    out = run(_main(admin=True), KEEP, S={"adminPage": True, "admin": ADMIN},
              responses={"/api/admin/player": view, "/api/admin": ADMIN})
    assert out == {"went": [[0, 480]], "player": "沈青衫", "page": True}


def test_the_admin_link_is_drawn_only_for_admins():
    admin = run(_main(admin=True), "return H.sheetHtml();", S={"sheet": True, "admin": ADMIN})
    assert 'href="/admin"' in admin and "管理者工具 ›" in admin
    assert admin.index('href="/admin"') < admin.index("匿名行走")  # 在抽屜頂上，第一屏就看得到
    assert 'data-op="open_season"' not in admin and 'id="reset-form"' not in admin  # 工具都搬到管理頁了
    player = run(_main(admin=False), "return H.sheetHtml();", S={"sheet": True})
    assert 'href="/admin"' not in player


DRAW = """H.render(); return { page: T.els.app.innerHTML.includes('class="ad-shell"'), still: H.S.adminPage };"""


def test_the_admin_page_is_drawn_only_for_admins():
    """網址是 /admin（S.adminPage）：管理者畫管理頁；不是管理者照常畫江湖、不再當成管理頁。"""
    assert run(_main(admin=True), DRAW, S={"adminPage": True, "admin": ADMIN}) == {"page": True, "still": True}
    assert run(_main(admin=False), DRAW, S={"adminPage": True, "admin": ADMIN}) == {"page": False, "still": False}


def test_a_backdrop_click_still_closes_the_sheet():
    out = run(_main(admin=True), """return (async () => {
      const el = { dataset: { act: "sheet-close" }, classList: { contains: () => false } };
      await T.docListeners.click[0]({ target: { closest: () => el } });
      return H.S.sheet;
    })();""", S={"sheet": True})
    assert out is False
