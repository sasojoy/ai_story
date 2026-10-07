"""設定抽屜在電腦上捲不到管理者工具（企劃者回報「管理者按鈕電腦版看不到，但手機版可以看到」，2026-10-07）。

原因：抽屜（.sheet）在電腦上只有中間 640px 寬、從底部長上來、最高 88vh，自己捲；管理者工具排在一般設定之後，大半在第一屏之下。
滑鼠滾輪只有指標正好在抽屜上才捲得動，兩旁的暗處（.sheet-bg）滾了不會捲抽屜；手機上抽屜滿版，怎麼滑都捲得到。
修法：暗處的滾輪照樣捲抽屜（點暗處照舊關掉抽屜）；管理者的抽屜頂上多一顆「管理者工具 ↓」，按了捲到管理者工具。

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


WHEEL = """return (async () => {
  const sheet = { top: 0, scrollBy(x, y) { this.top += y; } };
  T.qs[".sheet"] = sheet;
  const over = (sel) => Object.assign(Object.create(T.Element.prototype), { closest: (s) => (s === sel ? {} : null) });
  const roll = (target, deltaY, deltaMode = 0) => {
    const ev = { target, deltaY, deltaMode, prevented: false, preventDefault() { this.prevented = true; } };
    for (const fn of T.docListeners.wheel || []) fn(ev);
    return ev.prevented;
  };
  const backdrop = roll(over(".sheet-bg"), 120);
  const afterBackdrop = sheet.top;
  const elsewhere = roll(over(".page"), 300);  // 不在暗處：交給瀏覽器自己捲，不動抽屜
  const lines = roll(over(".sheet-bg"), 3, 1);  // 以「行」為單位的滾輪（Firefox）：換成像素
  return { backdrop, afterBackdrop, elsewhere, lines, top: sheet.top };
})();"""


def test_a_wheel_over_the_backdrop_scrolls_the_open_sheet():
    out = run(_main(admin=True), WHEEL, S={"sheet": True})
    assert out["backdrop"] is True and out["afterBackdrop"] == 120  # 擋下頁面自己的捲動、改捲抽屜
    assert out["elsewhere"] is False
    assert out["lines"] is True and out["top"] == 120 + 3 * 16


def test_a_wheel_with_no_sheet_open_does_nothing():
    out = run(_main(admin=True), """return (async () => {
      const target = Object.assign(Object.create(T.Element.prototype), { closest: () => ({}) });
      const ev = { target, deltaY: 50, deltaMode: 0, prevented: false, preventDefault() { this.prevented = true; } };
      for (const fn of T.docListeners.wheel || []) fn(ev);
      return ev.prevented;
    })();""")
    assert out is False


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
