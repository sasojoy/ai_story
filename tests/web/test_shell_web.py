"""網頁的殼（全部拆包第 64 批；計畫 docs/superpowers/plans/2026-11-06-網頁殼化-第64批.md 第六節）：/ 的 script 由伺服器照 FEATURES 生成、
registerPage、切出去的 web/cultivation.js、web/craft.js。

webharness.app_source() 把每支 js 接成一個 IIFE，函式全提升，**抓不到跨檔的載入順序錯**。這裡照 / 的順序把每支檔當獨立的 script 載進
同一個 vm context（跟瀏覽器一樣：頂層的 const 下一支看得到，還沒載入的碰了就 ReferenceError）。沒有 node 的那幾條略過。"""
# 畫法在 web/smithy.js、web/gear.js、web/outlets.js、web/tavern.js、web/bounties.js、web/bout.js（全部拆包第 65 批從 app.js 切出來）；寫在這裡 test_for 改包檔時才挑得到
# 畫法在 web/notify.js、web/peers.js、web/guide.js、web/sense.js、web/seal.js、web/zhuan.js、web/sortie.js、web/travel.js、web/tale.js、web/story.js、web/companions.js、web/territory_acts.js、web/state.js、web/fit.js（全部拆包第 66 批從 app.js 切出來）；寫在這裡 test_for 改包檔時才挑得到
from __future__ import annotations

import pytest

import webharness
from tianxia.core import features as features_core

needs_node = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")

DRIVER = r"""
const vm = require("vm");
const path = require("path");
const web = path.join(input.web);
const elements = {};
const element = (id) => (elements[id] = elements[id] || {
  id, innerHTML: "", hidden: false, dataset: {}, classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
  querySelector: () => null, querySelectorAll: () => [], setAttribute() {}, append() {}, insertAdjacentHTML() {},
});
const store = new Map();
const document = {
  body: { insertAdjacentHTML() {} },
  getElementById: (id) => (["app", "toast", "page", "top", "peek"].includes(id) ? element(id) : null),
  querySelector: () => null, querySelectorAll: () => [], addEventListener() {}, activeElement: null, hidden: false,
  createElement: () => ({ innerHTML: "", content: { querySelector: () => null } }),
};
const ctx = {
  document, window: { addEventListener() {}, scrollTo() {}, innerWidth: 375, innerHeight: 812 },
  fetch: () => new Promise(() => {}), // app.js 最後一行啟動的呼叫：不回，這裡只看載入
  localStorage: { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => { store.set(k, String(v)); }, removeItem: (k) => { store.delete(k); } },
  setInterval() {}, setTimeout, clearTimeout, performance, console, confirm: () => true, navigator: {}, CSS: { escape: (x) => x },
  requestAnimationFrame: () => 0, Element: class {},
};
vm.createContext(ctx);
const failed = [];
for (const name of input.files) {
  const code = fs.readFileSync(path.join(web, name), "utf8");
  try { vm.runInContext(code, ctx, { filename: name }); }
  catch (e) { failed.push([name, e.name, String(e.message)]); break; }
}
const value = failed.length ? null : vm.runInContext(input.ask, ctx);
finish({ failed, value });
"""


def load(files, ask="null"):
    return webharness.run(DRIVER, {"web": str(webharness.WEB), "files": list(files), "ask": ask})


@needs_node
def test_every_script_loads_on_its_own_in_the_order_the_page_serves():
    """每一支都是獨立的 script：照 / 的順序一支一支載，載入當下不能碰到還沒載入的名字。"""
    assert load(features_core.web_scripts())["failed"] == []


@needs_node
def test_the_load_check_catches_a_package_loaded_before_the_shell():
    """這條測試真的抓得到載入順序錯：包檔排在 shell.js 前面，檔尾的 registerPage 就是 ReferenceError。"""
    order = [name for name in features_core.web_scripts() if name != "shell.js"]
    assert order.index("cultivation.js") < order.index("app.js")
    failed = load(order)["failed"]
    assert failed and failed[0][1] == "ReferenceError" and "registerPage" in failed[0][2]


@needs_node
def test_the_packages_register_their_tabs():
    """renderPage 那張分頁表拿掉 practice、craft 之後照 PAGES 找：兩包登記的就是那兩個畫法。"""
    out = load(features_core.web_scripts(), "[Object.keys(PAGES), PAGES.practice.render === pagePractice, PAGES.craft.render === pageCraft]")
    assert out["failed"] == []
    assert out["value"] == [["practice", "craft"], True, True]


@needs_node
def test_a_wrong_tab_still_throws_where_it_always_did():
    """分頁 id 錯的時候照舊在 fn() 那裡丟 TypeError，不是默默畫一頁空的。"""
    ask = """(() => {
      S.tab = "沒有這一頁";
      try { renderPage(); return "沒有丟"; } catch (e) { return e.name; }
    })()"""
    out = load(features_core.web_scripts(), ask)
    assert out["failed"] == []
    assert out["value"] == "TypeError"


def test_with_scripts_fills_the_one_mark_and_keeps_the_line_ending():
    tags = [f'<script src="/static/{name}"></script>' for name in features_core.web_scripts()]
    assert features_core.with_scripts("a\n<!--scripts-->\nb") == "a\n" + "\n".join(tags) + "\nb"
    assert features_core.with_scripts("a\r\n<!--scripts-->\r\nb") == "a\r\n" + "\r\n".join(tags) + "\r\nb"


@pytest.mark.parametrize("html", ["<html></html>", "<!--scripts--><!--scripts-->"], ids=["沒有標記", "兩個標記"])
def test_with_scripts_refuses_a_page_without_exactly_one_mark(html):
    with pytest.raises(ValueError):
        features_core.with_scripts(html)


def test_web_scripts_is_the_order_table_plus_the_packages_js():
    """集合＝WEB_ORDER ∪ 各包登記的 js；shell.js 最前（包一載入就叫 registerPage），app.js 最後（它最後一行才啟動）。"""
    scripts = features_core.web_scripts()
    package_js = {name for name in features_core.web_files() if name.endswith(".js")}
    assert len(scripts) == len(set(scripts))
    assert set(scripts) == set(features_core.WEB_ORDER) | package_js
    assert scripts[0] == "shell.js" and scripts[-1] == "app.js"
    assert [name for name in scripts if name in features_core.WEB_ORDER] == list(features_core.WEB_ORDER)
    # 煉製的頂層監聽要排在 admin.js 之後（pointerdown 都掛在 document 的冒泡階段，切出來之前就是這個先後）
    assert scripts.index("admin.js") < scripts.index("craft.js") < scripts.index("app.js")
