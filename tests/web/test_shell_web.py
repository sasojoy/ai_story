"""網頁的殼（全部拆包第 64 批；計畫 docs/superpowers/plans/2026-11-06-網頁殼化-第64批.md 第六節）：/ 的 script 由伺服器照 FEATURES 生成、
registerPage、registerClicks（第 84 批）、切出去的 web/cultivation.js、web/craft.js。

webharness.app_source() 把每支 js 接成一個 IIFE，函式全提升，**抓不到跨檔的載入順序錯**。這裡照 / 的順序把每支檔當獨立的 script 載進
同一個 vm context（跟瀏覽器一樣：頂層的 const 下一支看得到，還沒載入的碰了就 ReferenceError）。沒有 node 的那幾條略過。"""
# 畫法在 web/smithy.js、web/gear.js、web/outlets.js、web/tavern.js、web/bounties.js、web/bout.js（全部拆包第 65 批從 app.js 切出來）；寫在這裡 test_for 改包檔時才挑得到
# 畫法在 web/notify.js、web/peers.js、web/guide.js、web/sense.js、web/seal.js、web/zhuan.js、web/sortie.js、web/travel.js、web/tale.js、web/story.js、web/companions.js、web/territory_acts.js、web/state.js、web/fit.js（全部拆包第 66 批從 app.js 切出來）；寫在這裡 test_for 改包檔時才挑得到
# 畫法在 web/battle.js、web/explore.js、web/military.js、web/figure_acts.js、web/checkin.js、web/faction.js、web/hire.js（全部拆包第 67 批從 main.js 切出來）；寫在這裡 test_for 改包檔時才挑得到
# 樣式在 web/battle.css、web/military.css、web/companions.css、web/figure_acts.css、web/bounties.css、web/notify.css、web/guide.css、web/checkin.css、web/explore.css、web/sortie.css、web/peers.css、web/territory_acts.css、web/cultivation.css、web/craft.css、web/tavern.css、web/seal.css、web/story.css、web/smithy.css（全部拆包第 67 批從 style.css 切出來）；寫在這裡 test_for 改包檔時才挑得到
# 點擊框也在 web/map.js、web/mall.js、web/legacy.js、web/looks.js（第 84 批，test_every_click_act_has_one_owner）；寫在這裡 test_for 改包檔時才挑得到
# 表單與 change 的框在 web/peers.js、web/companions.js、web/sense.js、web/explore.js、web/tavern.js、web/cultivation.js、web/smithy.js、web/mall.js、web/admin.js、web/notify.js、web/craft.js（第 85 批，test_every_form_and_change_has_one_owner）；寫在這裡 test_for 改包檔時才挑得到
from __future__ import annotations

import json
import re

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
    """這條測試真的抓得到載入順序錯：包檔排在 shell.js 前面，檔尾的 registerClicks 就是 ReferenceError（第 84 批起第一支炸的是 map.js 檔尾）。"""
    order = [name for name in features_core.web_scripts() if name != "shell.js"]
    assert order.index("cultivation.js") < order.index("app.js")
    failed = load(order)["failed"]
    assert failed and failed[0][1] == "ReferenceError" and "registerClicks" in failed[0][2]


@needs_node
def test_the_packages_register_their_tabs():
    """renderPage 那張分頁表拿掉 practice、craft 之後照 PAGES 找：兩包登記的就是那兩個畫法。"""
    out = load(features_core.web_scripts(), "[Object.keys(PAGES), PAGES.practice.render === pagePractice, PAGES.craft.render === pageCraft]")
    assert out["failed"] == []
    assert out["value"] == [["practice", "craft"], True, True]


def test_every_click_act_has_one_owner():
    """第 84 批：包在 <包>Click 的框裡認自己的 data-act，registerClicks 的清單跟框裡的 case 一個不多一個不少；
    同一個 act 不准兩包都認，也不准包認了、殼的 switch 還留一份（CLICKS 先查，殼那一份會變成靜靜不跑）。"""
    frame = re.compile(r'^  async function (\w+)Click\(act, el, ev\) \{\n    switch \(act\) \{\n(.*?)^    \} // \1Click\n  \} // \1Click\n'
                       r'  registerClicks\(\1Click, (\[[^\n]*\])\);$', re.S | re.M)
    case = re.compile(r'^        case "([^"]+)":', re.M)
    owners: dict[str, list[str]] = {}
    for name in features_core.web_scripts():
        src = (webharness.WEB / name).read_text(encoding="utf-8").replace("\r\n", "\n")
        calls = re.findall(r"^  registerClicks\((\w+)Click, ", src, re.M)
        assert calls in ([], [name[:-len(".js")]]), f"{name} 登記的框要照檔名：{calls}"
        if not calls:
            continue
        found = frame.findall(src)
        assert len(found) == 1, f"{name} 的框要照字面"
        _, body, listed = found[0]
        acts = case.findall(body)
        assert json.loads(listed) == acts, f"{name} 的 registerClicks 清單要等於框裡的 case，照先後"
        for act in acts:
            owners.setdefault(act, []).append(name)
    shell = (webharness.WEB / "app.js").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert "\n      if (clicked) return await clicked(act, el, ev);" in shell  # 一定要 await：這個 try 靠它吞 api() 丟的錯
    lookup = shell.index("\n      if (clicked) return await clicked(act, el, ev);")
    switch = shell[lookup:shell.index("\n    } catch (e) { /* api()", lookup)]
    for act in case.findall(switch):
        owners.setdefault(act, []).append("app.js")
    assert owners["map-home"] == ["map.js"] and "logout" in owners  # 兩邊都真的找到了，不是兩張空表
    assert {act: where for act, where in owners.items() if len(where) != 1} == {}


def test_every_form_and_change_has_one_owner():
    """第 85 批：包在 <包>Form 的框裡認自己的表單，registerForms 的清單跟框裡的判斷一個不多一個不少（照 id 認的寫 id，不照 id 認的寫 op:<data-op>）；
    同一個鍵不准兩包都認，也不准包認了、殼的 submit 鏈還留一份（FORMS 先查，殼那一份會變成靜靜不跑）。<包>Change 同樣照字面，認的東西不准兩包或殼重複。"""
    form_frame = re.compile(r'^  async function (\w+)Form\(form, data\) \{\n(.*?)^      \} // \1Form\n  \} // \1Form\n'
                            r'  registerForms\(\1Form, (\[[^\n]*\])\);$', re.S | re.M)
    form_key = re.compile(r'form\.id === "([^"]+)"|form\.dataset\.op === "([^"]+)"')
    change_frame = re.compile(r'^  async function (\w+)Change\(ev\) \{\n(.*?)^  \} // \1Change\n  registerChanges\(\1Change\);$', re.S | re.M)
    change_key = re.compile(r'ev\.target\.id === "([^"]+)"|classList\.contains\("([^"]+)"\)|dataset\.act === "([^"]+)"')

    def form_keys(text):
        return [one or f"op:{op}" for one, op in form_key.findall(text)]

    def change_keys(text):
        return [one or kind or act for one, kind, act in change_key.findall(text)]

    forms: dict[str, list[str]] = {}
    changes: dict[str, list[str]] = {}
    for name in features_core.web_scripts():
        src = (webharness.WEB / name).read_text(encoding="utf-8").replace("\r\n", "\n")
        stem = name[:-len(".js")]
        calls = re.findall(r"^  registerForms\((\w+)Form, ", src, re.M)
        assert calls in ([], [stem]), f"{name} 登記的框要照檔名：{calls}"
        if calls:
            found = form_frame.findall(src)
            assert len(found) == 1, f"{name} 的表單框要照字面"
            listed = json.loads(found[0][2])
            assert listed == form_keys(found[0][1]), f"{name} 的 registerForms 清單要等於框裡的判斷，照先後"
            for key in listed:
                forms.setdefault(key, []).append(name)
        calls = re.findall(r"^  registerChanges\((\w+)Change\);", src, re.M)
        assert calls in ([], [stem]), f"{name} 登記的框要照檔名：{calls}"
        if calls:
            found = change_frame.findall(src)
            assert len(found) == 1, f"{name} 的 change 框要照字面"
            seen = change_keys(found[0][1])
            assert seen, f"{name} 的 change 框要認得出它認什麼"
            for key in seen:
                changes.setdefault(key, []).append(name)
    shell = (webharness.WEB / "app.js").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert "\n      if (filed) return await filed(form, data);" in shell  # 一定要 await：這個 try 靠它接 api() 丟的錯，重開送出鈕、寫訊息
    lookup = shell.index("\n      if (filed) return await filed(form, data);")
    for key in form_keys(shell[lookup:shell.index("\n    } catch (e) {", lookup)]):
        forms.setdefault(key, []).append("app.js")
    start = shell.index('document.addEventListener("change"')
    listener = shell[start:shell.index("\n  });\n", start)]
    assert "await Promise.all(CHANGES.map((fn) => fn(ev)));" in listener
    for key in change_keys(listener):
        changes.setdefault(key, []).append("app.js")
    assert forms["tav-ask"] == ["tavern.js"] and forms["op:name-divine"] == ["cultivation.js"] and forms["gate-form"] == ["app.js"]  # 兩邊都真的找到了，不是兩張空表
    assert changes["push-kind"] == ["notify.js"] and changes["craft-view"] == ["craft.js"] and changes["hints-off"] == ["app.js"]
    assert {key: where for key, where in forms.items() if len(where) != 1} == {}
    assert {key: where for key, where in changes.items() if len(where) != 1} == {}


@needs_node
def test_the_packages_register_their_forms_and_changes():
    """照 / 的順序真的載一次：九包 17 個表單鍵（查不到才走殼那條鏈）、五包的 change；查表不能碰到原型上的名字。"""
    ask = """[Object.keys(FORMS).length, CHANGES.length, FORMS["tav-q"] === tavernForm, FORMS["op:shop-name-divine"] === smithyForm,
              CHANGES.includes(notifyChange), FORMS.constructor === undefined]"""
    out = load(features_core.web_scripts(), ask)
    assert out["failed"] == []
    assert out["value"] == [17, 5, True, True, True, True]


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
