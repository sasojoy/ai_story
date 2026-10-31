"""店面第一批的網頁（店面獨立介面設計第一、二、五節）：假瀏覽器照 test_prologue_web 的那一套跑整支 app.js。"""
from __future__ import annotations

import json

import pytest
from test_prologue_web import DRIVER as PROLOGUE_DRIVER
from test_shop import _smith

import server
import webharness

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
NAMES_START = 'wholeApp(["S", '
assert PROLOGUE_DRIVER.count(NAMES_START) == 1
DRIVER = PROLOGUE_DRIVER.replace(NAMES_START, 'wholeApp(["S", "shopHtml", "renderShop", "shopPolled", "smithForge", "revealHtml", ')


def run(m, script, S=None, responses=None):
    return webharness.run(DRIVER, {"m": m, "script": script, "S": S or {}, "menxia": None, "stored": {}, "responses": responses or {}})


@pytest.fixture
def m(content, world):
    return server.main_view(_smith(content, world))


# ── Task 5：店面那一層 ──


def test_the_shop_covers_the_screen_with_the_sign_line_and_four_tabs(m):
    html = run(m, "H.render(); return T.els.app.innerHTML;")
    shop = m["shop"]
    assert 'class="shop-layer shop-smith"' in html and shop["sign"] in html and shop["line"] in html
    assert f'data-act="choose" data-id="{shop["back"]}"' in html and "出店" in html
    for tab in ("架上", "打造", "淬煉與修", "裝備庫"):
        assert tab in html
    assert 'data-act="choose" data-id="smith:page:armor"' in html  # 兵器／防具切換
    assert html.count('data-act="choose" data-id="smith:buy:') == 6


@pytest.mark.smoke
def test_each_page_sends_the_right_action(m):
    out = run(m, """
      const pages = {};
      for (const tab of ["shelf", "temper", "rack", "forge"]) { H.S.shopTab = tab; H.render(); pages[tab] = T.els.app.innerHTML; }
      return pages;""")
    assert 'data-id="smith:buy:劍"' in out["shelf"]
    assert m["shop"]["worn"]["empty"] in out["temper"]  # 手上沒有兵器
    assert "shop-cell" in out["forge"] and 'data-act="shop-go"' in out["forge"] and 'data-book="forge"' in out["forge"]


def test_no_shop_layer_without_a_shop(m):
    plain = {**m}
    plain.pop("shop")
    assert "shop-layer" not in run(plain, "H.render(); return T.els.app.innerHTML;")


def test_the_shop_layer_follows_the_server(m):
    plain = {**m}
    plain.pop("shop")
    out = run(m, """
      H.S.tab = "jianghu"; H.render();
      const was = H.S.main; H.setMain(H.S.next); const closed = H.shopPolled(was);
      return { closed, html: T.els.app.innerHTML };""", S={"next": plain})
    assert out["closed"] is True and "shop-layer" not in out["html"]


def test_a_poll_redraws_only_the_shop(m):
    richer = json.loads(json.dumps(m))
    richer["shop"]["silver"] = 999
    out = run(m, """
      H.render(); T.els.page.innerHTML = "OLD";
      const layer = { outerHTML: "" }; T.qs[".shop-layer"] = layer;
      const was = H.S.main; H.setMain(H.S.next); H.shopPolled(was);
      return { page: T.els.page.innerHTML, layer: layer.outerHTML };""", S={"next": richer})
    assert out["page"] == "OLD" and "銀 999" in out["layer"]


def test_the_shop_waits_for_the_finger(m):
    richer = json.loads(json.dumps(m))
    richer["shop"]["silver"] = 999
    out = run(m, """
      return (async () => {
        H.render();
        const layer = { outerHTML: "" }; T.qs[".shop-layer"] = layer;
        T.docListeners.pointerdown.forEach((f) => f({}));
        const was = H.S.main; H.setMain(H.S.next); H.shopPolled(was);
        const held = layer.outerHTML;
        T.docListeners.pointerup.forEach((f) => f({}));
        await new Promise((ok) => setTimeout(ok, 5));
        return { held, after: layer.outerHTML };
      })();""", S={"next": richer})
    assert out["held"] == "" and "銀 999" in out["after"]


def test_rack_rows_wield_and_dismantle_through_menxia(content, world):
    from tianxia.state import Weapon

    game = _smith(content, world)
    p = game.state.player
    p.weapon = Weapon(id="兵:9", name="手上刃", kind="劍", attribute="柔", tier=1, quality="下品")
    p.rack = [Weapon(id=f"兵:{i}", name=f"庫刃{i}", kind="刀", attribute="剛", tier=1, quality="下品") for i in range(1, 11)]
    m = server.main_view(game)
    out = run(m, 'H.S.shopTab = "rack"; H.render(); return T.els.app.innerHTML;')
    assert out.count('data-act="shop-wield"') == 8 and "再列 2 件" in out and 'data-act="shop-dismantle"' in out


# ── Task 6：打造頁 ──


def _forge_page(m, script, responses=None, S=None):
    return run(m, 'H.S.shopTab = "forge";' + script, responses=responses, S=S)


def _click(dataset):
    """送一次點擊給 app.js 的 click 處理器：點到的元素帶 dataset。"""
    return ("await T.docListeners.click[0]({ target: { closest: () => ({ dataset: " + dataset
            + ", classList: { contains: () => false, add() {}, remove() {} }, isConnected: false }) } });")


def test_the_forge_page_has_kinds_a_two_slot_furnace_and_material_cells(m):
    html = _forge_page(m, "H.render(); return T.els.app.innerHTML;")
    assert 'data-act="shop-kind" data-kind="劍"' in html and "<sup>配</sup>" in html  # 配得上身上武學的那一種
    assert html.count('data-act="shop-slot"') == 2 and html.count('data-act="shop-cell"') == len(m["shop"]["forge"]["materials"])
    assert html.index("furnace") < html.index("shop-go") < html.index('class="cells"')  # 375×812：爐子、開爐鈕在素材格前面


def test_placing_a_material_asks_the_smith_line(m):
    line = json.loads(json.dumps(m["shop"]["forge"]["line"]))
    line["main"] = "gang_1"
    out = _forge_page(m, """
      return (async () => {
        H.render();
        """ + _click('{ act: "shop-cell", id: "gang_1", why: "" }') + """
        await new Promise((ok) => setTimeout(ok, 5));
        return { calls: T.calls.filter((c) => c[0] === "/api/smith_line").map((c) => c[1]), pot: H.S.shopPot };
      })();""", responses={"/api/smith_line": line})
    assert out["calls"][-1] == {"kind": "劍", "main": "gang_1", "aux": None} and out["pot"]["main"] == "gang_1"


def test_a_blocked_cell_only_says_why(m):
    out = _forge_page(m, """
      return (async () => {
        H.render();
        """ + _click('{ act: "shop-cell", id: "gang_2", why: "工錢不夠，還差 30 兩" }') + """
        await new Promise((ok) => setTimeout(ok, 5));
        return { calls: T.calls.filter((c) => c[0] === "/api/smith_line").length, toast: T.els.toast.textContent, pot: H.S.shopPot };
      })();""")
    assert out["calls"] == 0 and "還差 30 兩" in out["toast"] and out["pot"] is None


def test_taking_the_main_out_empties_both_slots(m):
    out = _forge_page(m, """
      return (async () => {
        H.S.shopPot = { slot: "weapon", kind: "劍", main: "gang_1", aux: "kuai_1" };
        H.render();
        """ + _click('{ act: "shop-slot", role: "main" }') + """
        return H.S.shopPot;
      })();""", responses={"/api/smith_line": m["shop"]["forge"]["line"]})
    assert (out["main"], out["aux"]) == (None, None)


def test_a_ready_pot_shows_the_odds_the_head_and_a_live_go_button(content, world):
    game = _smith(content, world)
    m = server.main_view(game)
    line = game.smith_line("劍", "gang_1", "kuai_1")
    html = _forge_page(m, "H.S.shopPot = { slot: 'weapon', kind: '劍', main: 'gang_1', aux: 'kuai_1' }; H.S.shopLine = H.S.next; H.render(); return T.els.app.innerHTML;",
                       S={"next": line})
    assert line["go"] in html and 'class="odds"' in html and 'data-act="shop-go"' in html and 'data-act="shop-go" disabled' not in html


def test_a_tier4_pot_says_named_gear_is_likely(content, world):
    """FB-341：伺服器給了 named_hint（主料四階）就畫在說明那一段；沒給不畫。"""
    game = _smith(content, world)
    m = server.main_view(game)
    line = dict(game.smith_line("劍", "gang_1", "kuai_1"), named_hint="四階的料，<打出名器>的機會很大")
    script = "H.S.shopPot = { slot: 'weapon', kind: '劍', main: 'gang_1', aux: 'kuai_1' }; H.S.shopLine = H.S.next; H.render(); return T.els.app.innerHTML;"
    html = _forge_page(m, script, S={"next": line})
    assert "&lt;打出名器&gt;" in html and "<打出名器>" not in html
    plain = _forge_page(m, script, S={"next": dict(line, named_hint="")})
    assert "打出名器" not in plain


# ── Task 7：開爐與出爐 ──

FORGED = {"id": "兵:1", "slot": "weapon", "name": "試鍛劍", "grade": "一階上品", "kind": "劍", "attribute": "陽", "value": "加成 +9%",
          "fit": "配得上你的武學", "glow": "gold", "first": False, "where": "worn", "divine": None}


def test_forging_posts_the_pot_and_wraps_the_result_in_cloth(m):
    out = _forge_page(m, """
      return (async () => {
        H.S.shopPot = { slot: "weapon", kind: "劍", main: "gang_1", aux: "kuai_1" };
        await H.smithForge();
        return { call: T.calls.find((c) => c[0] === "/api/do/smith_forge"), html: T.els.app.innerHTML, pot: H.S.shopPot };
      })();""", responses={"/api/do/smith_forge": {"main": m, "message": "", "forged": FORGED}})
    assert out["call"][1] == {"kind": "劍", "main": "gang_1", "aux": "kuai_1"}
    assert 'class="bundle g-gold"' in out["html"] and "試鍛劍" not in out["html"]  # 先包著：點開才看到名字
    assert (out["pot"]["main"], out["pot"]["aux"]) == (None, None)


@pytest.mark.parametrize("glow", ["none", "cyan", "gold", "purple", "red", "redgold"])
def test_each_result_has_its_own_light(m, glow):
    html = run(m, "H.S.shopReveal = H.S.next; H.render(); return T.els.app.innerHTML;", S={"next": {**FORGED, "glow": glow}})
    assert f'class="bundle g-{glow}"' in html


def test_unwrapping_shows_the_card_with_its_buttons(m):
    html = run(m, "H.S.shopReveal = H.S.next; H.S.shopOpened = true; H.render(); return T.els.app.innerHTML;", S={"next": FORGED})
    assert "試鍛劍" in html and "一階上品" in html and "加成 +9%" in html and 'data-act="shop-keep"' in html and "收下" in html
    stored = run(m, "H.S.shopReveal = H.S.next; H.S.shopOpened = true; H.render(); return T.els.app.innerHTML;",
                 S={"next": {**FORGED, "where": "rack"}})
    assert 'data-act="shop-wield" data-id="兵:1"' in stored and "留在裝備庫" in stored


def test_a_first_find_carries_the_seal_and_an_original_carries_the_naming_form(m):
    shop = json.loads(json.dumps(m["shop"]))
    shop["pending"] = {"兵:1": "墜星劍"}
    html = run({**m, "shop": shop}, "H.S.shopReveal = H.S.next; H.S.shopOpened = true; H.render(); return T.els.app.innerHTML;",
               S={"next": {**FORGED, "first": True, "glow": "redgold", "divine": "墜星劍"}})
    assert "首位發現" in html and 'id="shop-name-divine-兵:1"' in html and "沿用譜名【墜星劍】" in html


def test_a_refused_forge_keeps_the_pot(m):
    out = _forge_page(m, """
      return (async () => {
        H.S.shopPot = { slot: "weapon", kind: "劍", main: "gang_2", aux: "gang_2" };
        await H.smithForge();
        return { reveal: H.S.shopReveal, pot: H.S.shopPot, toast: T.els.toast.textContent };
      })();""", responses={"/api/do/smith_forge": {"main": m, "message": "（玄鋼骨不夠（要 2 個）。）", "forged": None},
                           "/api/smith_line": m["shop"]["forge"]["line"]})
    assert out["reveal"] is None and out["pot"]["kind"] == "劍" and "玄鋼骨不夠" in out["toast"]


def test_reduced_motion_skips_the_fire(m):
    out = _forge_page(m, """
      return (async () => {
        T.ctx.window.matchMedia = () => ({ matches: true });
        H.S.shopPot = { slot: "weapon", kind: "劍", main: "gang_1", aux: "kuai_1" };
        const seen = [];
        const p = H.smithForge(); seen.push(H.S.shopFiring); await p;
        return seen;
      })();""", responses={"/api/do/smith_forge": {"main": m, "message": "", "forged": FORGED}})
    assert out == [False]


def test_the_fire_runs_without_reduced_motion(m):
    out = _forge_page(m, """
      return (async () => {
        H.S.shopPot = { slot: "weapon", kind: "劍", main: "gang_1", aux: "kuai_1" };
        const seen = [];
        const p = H.smithForge(); seen.push(H.S.shopFiring); await p; seen.push(H.S.shopFiring);
        return seen;
      })();""", responses={"/api/do/smith_forge": {"main": m, "message": "", "forged": FORGED}})
    assert out == [True, False]


def test_a_redraw_keeps_the_shop_scrolled_where_it_was(m):
    """放一格素材、輪詢都把整層換掉：店裡捲到哪裡照放回去；換頁才回到頂上（實機看 375 寬時發現的）。"""
    out = run(m, """
      H.S.shopTab = "forge"; H.render();
      const fresh = { scrollTop: 0 };
      const layer = { outerHTML: "", querySelector: () => ({ scrollTop: 240 }) };
      T.qs[".shop-layer"] = layer; T.qs[".shop-layer .shop-body"] = fresh;
      H.renderShop();
      const kept = fresh.scrollTop;
      fresh.scrollTop = 0; H.renderShop(false);
      return { kept, reset: fresh.scrollTop };""")
    assert out == {"kept": 240, "reset": 0}


# ── 終審 Important：煉製頁的 .odds 不能滲進店面；店裡紙底表單上的淡框鈕要看得見 ──


def test_the_craft_page_odds_rules_do_not_bleed_into_the_shop():
    """煉製頁的 .odds span 是 --ink-2 色，深色主題下剛好等於店面下品那一格的底色（看不見）；.odds 的 gap、margin 也會滲進來。
    店面上的「沿用譜名」在紙底的定名表單裡，不能用暗底那一套淡色字。"""
    import re

    css = (server.WEB / "style.css").read_text(encoding="utf-8")
    assert re.search(r"\.shop-layer \.odds span \{[^}]*color: inherit[^}]*margin: 0", css)
    assert re.search(r"\.shop-layer \.odds \{[^}]*gap: 0[^}]*margin-top: 0", css)
    assert re.search(r"\.shop-layer \.naming \.btn\.ghost \{[^}]*color: var\(--ink\)", css)


def test_a_second_quick_tap_goes_to_the_aux_slot(m):
    """點了主料、回應還沒回來又點第二格（手上的這一爐說法還是空爐那一份，格子寫著放主料）：第二格照爐裡現在的樣子放進輔料，
    不是把主料換掉。"""
    out = _forge_page(m, """
      return (async () => {
        H.S.shopPot = { slot: "weapon", kind: "劍", main: "gang_1", aux: null };
        H.render();
        """ + _click('{ act: "shop-cell", id: "kuai_1", why: "" }') + """
        return H.S.shopPot;
      })();""", responses={"/api/smith_line": {"kind": "劍", "main": "gang_1", "aux": "kuai_1", "cells": [], "ready": False}})
    assert (out["main"], out["aux"]) == ("gang_1", "kuai_1")


def test_a_line_for_another_pot_is_not_shown_as_ready(content, world):
    """爐裡換了一樣、回應還沒回來：手上那一份說的是上一爐，不能拿它的機率與亮著的開爐鈕。"""
    game = _smith(content, world)
    m = server.main_view(game)
    old = game.smith_line("劍", "gang_1", "rou_1") if "rou_1" in game.state.player.materials else game.smith_line("劍", "gang_1", "gang_1")
    html = _forge_page(m, "H.S.shopPot = { slot: 'weapon', kind: '劍', main: 'gang_1', aux: 'kuai_1' }; H.S.shopLine = H.S.next; H.render(); return T.els.app.innerHTML;",
                       S={"next": old})
    assert old["ready"] and 'class="odds"' not in html and 'data-act="shop-go" disabled' in html


# ── 設計第七節補測：店面上定名被拒絕，剛打的字留在框裡（同修練頁那一張，tests/test_weapons_web.py）──

_SHOP_DIVINE_REFUSED = """return (async () => {
  T.ctx.FormData = function (form) { return Object.entries(form.data); };  // 假瀏覽器沒有 FormData：表單的欄位直接給
  const input = { value: "" };
  const real = T.ctx.document.getElementById;
  // 被拒了：伺服器回來重畫的出爐卡上表單還在（假瀏覽器沒有真的 DOM，這裡替它放一張）；定成了表單就不再畫，getElementById 找不到
  let still = true;
  T.ctx.document.getElementById = (id) => (id === "shop-name-divine-兵:1" && still ? { querySelector: (sel) => (sel === 'input[name="name"]' ? input : null) } : real(id));
  const form = { id: "shop-name-divine-兵:1", dataset: { op: "shop-name-divine", id: "兵:1" }, data: { name: "斬月刀" }, querySelector: () => null };
  H.render();
  await T.docListeners.submit[0]({ preventDefault() {}, target: form });
  const kept = input.value;
  const toast = T.els.toast.textContent;
  still = false;
  input.value = "";
  await T.docListeners.submit[0]({ preventDefault() {}, target: form });
  const posts = T.calls.filter((c) => c[0] === "/api/menxia/name_divine").map((c) => c[1]);
  return { kept, posts, toast, after: input.value };
})();"""


def test_a_refused_divine_name_on_the_forged_card_stays_in_the_box(m):
    """出爐卡（與裝備庫那一頁）上的定名表單：送 /api/menxia/name_divine，伺服器拒絕時提示泡泡講原因、重畫出來的表單放回剛打的字，
    不用重打；定成了表單不再畫，什麼都不放。"""
    reply = {"/api/menxia/name_divine": {"menxia": None, "main": m, "message": "這個名字不行：跟鐵匠鋪尋常打得出的名字同名。"}}
    out = run(m, _SHOP_DIVINE_REFUSED, S={"shopReveal": {"id": "兵:1", "slot": "weapon", "name": "無名神器", "grade": "三階上品・神器",
                                             "kind": "劍", "attribute": "剛", "value": None, "fit": "", "glow": "redgold",
                                             "first": True, "where": "rack", "divine": "墜星劍"}, "shopOpened": True},
              responses=reply)
    assert out["kept"] == "斬月刀" and "同名" in out["toast"]
    assert [(p.get("weapon"), p.get("name")) for p in out["posts"]] == [("兵:1", "斬月刀"), ("兵:1", "斬月刀")]
    assert out["after"] == ""
