"""店面第一批的網頁（店面獨立介面設計第一、二、五節）：假瀏覽器照 test_prologue_web 的那一套跑整支 app.js。"""
# 畫法在 web/smithy.js（全部拆包第 65 批從 app.js 切出來）；寫在這裡 test_for 改包檔時才挑得到
from __future__ import annotations

import json

import pytest
from test_prologue_web import DRIVER as PROLOGUE_DRIVER
from test_shop import _smith

import server
import webharness

pytestmark = [pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過"), pytest.mark.whole_content]
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
    for tab in ("架上", "打造", "裝備庫"):  # 鐵匠鋪與合成流程 3.4：「淬煉與修」併進裝備庫（素材、神器另外接在後面）
        assert tab in html
    assert "淬煉與修" not in html
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


# ── 設計第七節補測：店面上定名被拒絕，剛打的字留在框裡（同修練頁那一張，tests/web/test_weapons_web.py）──

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


# ── 鐵匠鋪與合成流程 3.3（A 批）：打造頁缺料的灰格就地熬（只用現成的 shop.trade 與 smith_upgrade；
#    小單企劃者 2026-11-03 挑「乙 從畫面底下浮一張」，原本做的是那一排底下展開）──


def _brewing(content, world, bag, upgrade=True):
    """升階開著（測試內容預設關著）的鐵匠鋪，背包換成 bag。測試內容的素材：剛一到三階、快只有一階（剛的二、三階換得出來，快沒有）。"""
    content.config.economy.upgrade = upgrade
    game = _smith(content, world)
    game.state.player.materials = dict(bag)
    return game


def _cell_of(html, attr, tier):
    """打造頁那一格的標記（灰格照 data-attr／data-tier 找）。"""
    at = html.index(f'data-act="shop-brew" data-attr="{attr}" data-tier="{tier}"')
    start = html.rindex("<button", 0, at)
    return html[start:html.index("</button>", at)]


def test_missing_tiers_are_grey_brew_cells_and_tier_one_is_none(content, world):
    game = _brewing(content, world, {"gang_2": 1, "kuai_1": 2})
    m = server.main_view(game)
    html = _forge_page(m, "H.render(); return T.els.app.innerHTML;")
    ups = {(u["attribute"], u["tier"]): u for u in m["shop"]["trade"]["upgrade"]}
    assert html.count('data-act="shop-cell"') == 2  # 背包有的照舊是實格
    t3 = _cell_of(html, "剛", 3)
    assert "熬" in t3 and f"{ups[('剛', 3)]['need']} 個二階" in t3 and ups[("剛", 3)]["short"] in t3 and " off" in t3  # 料不夠：短原因、灰
    assert 'class="cell t1 brew none"' in html and ">無<" in html  # 剛沒有一階：「無」、不可點（不是 button）
    assert 'data-attr="快"' not in html  # 快沒有二、三階的素材（內容裡就沒有）：沒有熬的路就不畫
    assert html.index('class="row-attr gang"') < html.index('data-attr="剛" data-tier="3"') < html.index('class="row-attr kuai"')


def test_tier_one_in_the_bag_makes_tier_two_brewable(content, world):
    game = _brewing(content, world, {"gang_1": 4})
    m = server.main_view(game)
    html = _forge_page(m, "H.render(); return T.els.app.innerHTML;")
    t2 = _cell_of(html, "剛", 2)
    assert "熬" in t2 and "3 個一階" in t2 and " off" not in t2 and 'data-why=""' in t2
    assert "手上 0／10" in _cell_of(html, "剛", 3)


@pytest.mark.slow  # 提示泡泡的 3.2 秒計時器把 node 留到時間到（同 test_a_blocked_cell_only_says_why）
def test_a_brew_cell_that_cannot_brew_only_says_why(content, world):
    game = _brewing(content, world, {"gang_2": 1})
    m = server.main_view(game)
    why = next(u for u in m["shop"]["trade"]["upgrade"] if u["tier"] == 3)["problem"]
    out = _forge_page(m, """return (async () => {
        H.render();
        """ + _click('{ act: "shop-brew", attr: "剛", tier: "3", why: %s }' % json.dumps(why)) + """
        return { brew: H.S.shopBrew, toast: T.els.toast.textContent, html: T.els.app.innerHTML, calls: T.calls.length, asked: T.bodyHtml.join("") };
      })();""")
    assert out["brew"] is None and out["toast"] == why and out["calls"] == 0
    assert "ask-layer" not in out["asked"] and "brew on" not in out["html"]  # 不浮小單、那一格不框


_BREW_ASK = """return (async () => {
    T.qs['.ask [data-act="ask-no"]'] = { focus() {} };
    H.render();
    """ + _click('{ act: "shop-brew", attr: "剛", tier: "2", why: "" }') + """
    const shop = T.els.app.innerHTML, asked = T.bodyHtml.join("");
    %s
    await new Promise((ok) => setTimeout(ok, 5));
    return { shop, asked, after: T.els.app.innerHTML, calls: T.calls.map((c) => c), brew: H.S.shopBrew, note: H.S.shopNote };
  })();"""


def test_tapping_a_brew_cell_floats_a_sheet_from_the_bottom_and_brewing_posts_the_upgrade(content, world):
    """企劃者 2026-11-03 從灰格小單的兩張對比圖挑「乙 從畫面底下浮一張」（原本做的是那一排底下展開）：點得了的灰格，小單從畫面底下
    浮上來（同確認框那一層，ask），問句、素材頁那一句機率、「取消」「熬」；點的那一格框起來。按「熬」送 smith_upgrade（屬性與階照小單
    問的那一筆），收起之後那一格不再框著、結果句換掉鐵匠那一句，再問一次這一爐（素材格跟著變）。"""
    game = _brewing(content, world, {"gang_1": 4})
    m = server.main_view(game)
    up = next(u for u in m["shop"]["trade"]["upgrade"] if u["tier"] == 2)
    out = _forge_page(m, _BREW_ASK % _click('{ act: "ask-yes" }'),
                      responses={"/api/do/smith_upgrade": {"main": m, "message": "<p>你用 3 個精鐵砂熬出了一個玄鋼骨。</p>"},
                                 "/api/smith_line": m["shop"]["forge"]["line"]})
    assert "brew-sheet" not in out["shop"] and "shop-brew-go" not in out["shop"]  # 不在那一排底下展開
    assert 'class="cell t2 brew on" data-act="shop-brew" data-attr="剛" data-tier="2"' in out["shop"]  # 點的那一格框起來
    asked = out["asked"]
    assert 'class="ask-layer"' in asked and f"用 3 個一階剛熬一個二階剛，{up['cost']} 兩？" in _text(asked)  # 設計稿 3.3 的那一句
    assert f'<p class="muted ask-sub">{up["odds"]}' in asked  # 素材頁的機率，問句底下一行淡字
    assert '<button class="btn" data-act="ask-no">取消</button><button class="btn danger" data-act="ask-yes">熬</button>' in asked
    posted = [c for c in out["calls"] if c[0] == "/api/do/smith_upgrade"]
    assert posted == [["/api/do/smith_upgrade", {"attribute": "剛", "tier": 2}]]  # 熬的就是小單問的那一格
    assert out["calls"][-1][0] == "/api/smith_line"
    assert out["brew"] is None and "brew on" not in out["after"]
    assert '<p class="shop-line brewed" role="status">你用 3 個精鐵砂熬出了一個玄鋼骨。</p>' in out["after"]  # 鐵匠那一句換成結果句


_BREW_SCROLL = """return (async () => {
    T.qs['.ask [data-act="ask-no"]'] = { focus() {} };
    // 小單在畫面底下（812 高、小單 %(sheet)s 高）；點的那一格畫上框了才找得到（%(top)s～%(bottom)s）
    const cell = { getBoundingClientRect: () => ({ top: %(top)s, bottom: %(bottom)s }) };
    const body = { scrollTop: 40, querySelector: (s) => (s === ".cell.brew.on" && T.els.app.innerHTML.includes("brew on") ? cell : null) };
    T.qs[".shop-layer .shop-body"] = body;
    T.qs[".ask"] = { offsetHeight: %(sheet)s };
    H.render();
    """ + _click('{ act: "shop-brew", attr: "剛", tier: "2", why: "" }') + """
    return body.scrollTop;
  })();"""


@pytest.mark.parametrize(("top", "bottom", "scrolled"), [(560, 630, 40 + 630 + 8 - (812 - 220)), (400, 470, 40)])
def test_the_framed_cell_is_scrolled_above_the_sheet(content, world, top, bottom, scrolled):
    """小單從畫面底下浮上來會蓋住底下幾排（320×700 點柔的二階：那一格底 567、小單頂 521）：浮上來之後把捲的那一層往上推，
    點的那一格露在小單上面（留 8px）；本來就看得到的不動。小單的頂照它最後停的位置算（視窗高 − 小單高），不量浮上來的半路。"""
    game = _brewing(content, world, {"gang_1": 4})
    out = _forge_page(server.main_view(game), _BREW_SCROLL % {"top": top, "bottom": bottom, "sheet": 220})
    assert out == scrolled


@pytest.mark.slow  # 提示泡泡的計時器（約 3 秒）
def test_a_refused_brew_still_unframes_the_cell(content, world):
    """伺服器拒了（例：今天熬滿了；api() 提示原因、shopDo 不重畫）：小單已經收了，那一格也不能一直框著。"""
    game = _brewing(content, world, {"gang_1": 4})
    m = server.main_view(game)
    refuse = ('T.ctx.fetch = ((orig) => (url, opts) => (url.startsWith("/api/do/") ? Promise.resolve({ ok: false, status: 400, '
              'json: () => Promise.resolve({ detail: "今天熬滿了" }) }) : orig(url, opts)))(T.ctx.fetch);\n')
    out = _forge_page(m, refuse + _BREW_ASK % _click('{ act: "ask-yes" }'), responses={"/api/smith_line": m["shop"]["forge"]["line"]})
    assert out["brew"] is None and "brew on" not in out["after"] and 'class="cell t2 brew" data-act="shop-brew"' in out["after"]


@pytest.mark.parametrize("close", ['{ act: "ask-no" }', "escape"])
def test_closing_the_sheet_unframes_the_cell_and_changing_the_pot_puts_the_smith_line_back(content, world, close):
    """「取消」、點旁邊的暗處（同一個 ask-no）、Esc：小單收起、那一格不再框著、什麼都不送；之後放料，熬的結果句收起（鐵匠那一句換回來）。"""
    game = _brewing(content, world, {"gang_1": 4})
    m = server.main_view(game)
    shut = ('T.docListeners.keydown.forEach((f) => f({ key: "Escape", target: {} }));' if close == "escape" else _click(close))
    out = _forge_page(m, _BREW_ASK % (shut + """
        const closed = T.els.app.innerHTML, sent = T.calls.length, brew = H.S.shopBrew;
        H.S.shopNote = "熬出來了";
        """ + _click('{ act: "shop-cell", id: "gang_1", why: "" }') + """
        return { closed, sent, brew, note: H.S.shopNote };"""), responses={"/api/smith_line": m["shop"]["forge"]["line"]})
    assert out["brew"] is None and "brew on" not in out["closed"] and out["sent"] == 0 and out["note"] is None


def test_no_trade_no_grey_cells(content, world):
    """升階關著（shop.trade 是 None，或只開收購、upgrade 是空的）：打造頁照現在，一格灰格都不畫。"""
    off = server.main_view(_brewing(content, world, {"gang_2": 1, "kuai_1": 2}, upgrade=False))  # 剛沒有一階：開著的話那一格會畫「無」
    assert off["shop"]["trade"] is None
    html = _forge_page(off, "H.render(); return T.els.app.innerHTML;")
    assert "shop-brew" not in html and "brew none" not in html
    sell_only = json.loads(json.dumps(off))
    sell_only["shop"]["trade"] = {"sell": [], "upgrade": [], "hint": "", "up_cap": "", "sell_cap": "", "sell_empty": ""}
    only = _forge_page(sell_only, "H.render(); return T.els.app.innerHTML;")
    assert "shop-brew" not in only and "brew none" not in only
    grid = lambda page: page[page.index('<div class="cells'):page.index('<nav class="shop-tabs">')]  # noqa: E731  素材格一模一樣（只多「素材」那一頁的分頁）
    assert grid(only) == grid(html)


def test_a_brewed_material_turns_into_a_real_cell(content, world):
    """真的熬一次（Game.smith_upgrade，打造頁開著時按得下去）：灰格變實格、數字照背包。手上那一份這一爐的說法（S.shopLine）還是熬之前的
    （沒有新的那一格；/api/smith_line 還沒回來）：素材格照背包（forge.materials）畫，說法裡沒有的那一格當放得進去（Review Focus 3）。"""
    game = _brewing(content, world, {"gang_1": 4})
    stale = server.main_view(game)["shop"]["forge"]["line"]
    game.smith_upgrade("剛", 2)
    assert game.state.player.materials.get("gang_2") == 1
    m = server.main_view(game)
    assert stale["kind"] == m["shop"]["forge"]["kind"] and not any(c["id"] == "gang_2" for c in stale["cells"])
    html = _forge_page(m, "H.render(); return T.els.app.innerHTML;", S={"shopLine": stale})
    assert 'data-act="shop-cell" data-id="gang_2"' in html and 'data-attr="剛" data-tier="2"' not in html


# ── 鐵匠鋪與合成流程 3.2（C 批）：打造頁的爐火可以點、火上一枚小籤（forge.furnace、MAIN_ACTIONS smith_furnace；
#    企劃者 2026-11-03 從三張對比圖挑「丙 火上一枚小籤」，原本做的是爐子底下一行）──


def _fired(**set_):
    """正式內容 week7（銀兩出口開著）的鐵匠鋪（test_shop._fire），玩家欄位照 set_ 改，回 /api/main 那一份。"""
    from test_shop import _fire

    game = _fire()
    for key, value in set_.items():
        if key == "silver":
            game.state.player.stats["silver"] = value
        elif key == "used":
            game.state.player.furnace_ready, game.state.player.furnace_day = False, game._pill_day()
        elif key == "looked":
            game.smith_furnace()
    return game, server.main_view(game)


def _fire(html):
    """爐子中間那團火（一顆鈕，連掛在上面的小籤）。"""
    at = html.index('class="flame fu-fire"')
    start = html.rindex("<button", 0, at)
    return html[start:html.index("</button>", at) + len("</button>")]


def _tag(html):
    """火上那一枚小籤（企劃者 2026-11-03 從爐火那一行的三張對比圖挑「丙 火上一枚小籤」）。"""
    at = html.index('<span class="fu-tag')
    return html[at:html.index("</span>", at) + len("</span>")]


def test_an_unlooked_furnace_hangs_a_price_tag_on_the_fire():
    """還沒看：火上一枚金色小籤寫價錢，整團火（連小籤）是一顆鈕；爐子底下不再另起一行、沒有另一顆「看」（開爐鈕跟著往上）。"""
    _game, m = _fired()
    fu = m["shop"]["forge"]["furnace"]
    assert fu["problem"] is None and not fu["ready"]
    html = _forge_page(m, "H.render(); return T.els.app.innerHTML;")
    fire = _fire(html)
    assert _tag(html) == f'<span class="fu-tag">看火候 {fu["price"]} 兩</span>' and _tag(html) in fire  # 小籤掛在火上
    assert 'data-act="shop-furnace"' in fire and "disabled" not in fire and "aria-disabled" not in fire
    assert f'aria-label="看火候 {fu["price"]} 兩，今天還沒看。"' in fire  # 讀螢幕的人聽整句
    assert "fu-say" not in html and ">看</button>" not in html
    assert html.index('class="furnace"') < html.index("fu-tag") < html.index('class="shop-gorow"')  # 還沒看：火照平常的樣子


def test_a_looked_furnace_burns_hot_and_its_tag_says_so():
    _game, m = _fired(looked=True)
    assert m["shop"]["forge"]["furnace"]["ready"]
    html = _forge_page(m, "H.render(); return T.els.app.innerHTML;")
    assert 'class="furnace hot"' in html and _tag(html) == '<span class="fu-tag hot">火候看過了</span>'
    assert 'aria-label="火候看過了，下一爐照新基準。" aria-disabled="true"' in _fire(html) and "fu-say" not in html


def test_a_furnace_used_today_is_grey_until_tomorrow():
    _game, m = _fired(used=True)
    assert m["shop"]["forge"]["furnace"]["used_today"]
    html = _forge_page(m, "H.render(); return T.els.app.innerHTML;")
    assert _tag(html) == '<span class="fu-tag off">明日再來</span>' and "hot" not in html.split('class="furnace', 1)[1][:6]
    assert 'aria-label="今天看過了，明日再來。" aria-disabled="true"' in _fire(html)


@pytest.mark.slow  # 提示泡泡的計時器（約 3 秒）
def test_a_furnace_you_cannot_afford_is_grey_and_says_why_when_tapped():
    """錢不夠（序章也是）：小籤照舊寫價錢、灰掉；點那一團火只說整句原因（小籤放不下長原因，同打造頁的灰格），什麼都不送。"""
    _game, m = _fired(silver=10)
    fu = m["shop"]["forge"]["furnace"]
    assert fu["problem"] and "還差" in fu["problem"]
    why = f"看火候 {fu['price']} 兩・{fu['problem']}"
    out = _forge_page(m, "return (async () => { H.render(); const html = T.els.app.innerHTML; " + _click('{ act: "shop-furnace" }')
                      + " return { html, toast: T.els.toast.textContent, calls: T.calls.length }; })();")
    assert _tag(out["html"]) == f'<span class="fu-tag off">看火候 {fu["price"]} 兩</span>'
    assert f'aria-label="{why}" aria-disabled="true"' in _fire(out["html"])
    assert out["toast"] == why and out["calls"] == 0


def test_the_furnace_is_not_tappable_when_the_silver_outlets_are_off(m):
    """銀兩出口關著（測試內容；週末、14 天季也是）：forge.furnace 是 None，爐火不可點、小籤不畫，打造頁跟以前一樣。"""
    assert m["shop"]["forge"]["furnace"] is None
    html = _forge_page(m, "H.render(); return T.els.app.innerHTML;")
    assert "shop-furnace" not in html and "fu-tag" not in html and "fu-say" not in html and '<div class="flame">' in html


def test_the_tag_hangs_on_the_fire():
    """小籤是火那一顆鈕裡的一段，絕對定位掛在火的下緣（不佔一行）；字級寫 em（店面那一層照寬度放大），不寫死 px。
    有小籤時中間那一欄也寫 em：照舊 72px 的話電腦寬（字級 ×1.3）小籤壓到兩邊料格的下角 11px（實機量的）；沒有小籤（銀兩出口關著）照舊。"""
    import re

    css = (server.WEB / "style.css").read_text(encoding="utf-8") + (server.WEB / "smithy.css").read_text(encoding="utf-8")
    assert re.search(r"\.shop-layer \.furnace:has\(> \.fu-fire\) \{ grid-template-columns: 1fr [0-9.]+em 1fr; \}", css)
    assert "grid-template-columns: 1fr 72px 1fr;" in css  # 沒有小籤的爐子照舊
    assert re.search(r"\.shop-layer \.furnace \.fu-fire \{[^}]*position: relative", css)
    tag = re.search(r"\.shop-layer \.fu-tag \{([^}]*)\}", css)
    assert tag and "position: absolute" in tag.group(1) and "white-space: nowrap" in tag.group(1)
    assert re.search(r"font: 600 [0-9.]+em", tag.group(1))


@pytest.mark.slow  # 提示泡泡的計時器（約 3 秒）
def test_looking_posts_the_op_and_asks_the_line_again():
    game, m = _fired()
    after = server.main_view(game)
    out = _forge_page(m, """return (async () => {
        H.render();
        """ + _click('{ act: "shop-furnace" }') + """
        await new Promise((ok) => setTimeout(ok, 5));
        return { calls: T.calls.map((c) => c), toast: T.els.toast.textContent };
      })();""", responses={"/api/do/smith_furnace": {"main": after, "message": "<p>老師傅答應下一爐親自替你看火候。</p>"},
                           "/api/smith_line": m["shop"]["forge"]["line"]})
    assert out["calls"][0] == ["/api/do/smith_furnace", {}] and out["calls"][-1][0] == "/api/smith_line"
    assert "老師傅答應" in out["toast"]


def test_looking_at_the_fire_puts_the_smith_line_back_after_a_brew():
    """熬完的結果句蓋著鐵匠那一句（3.3）；同一頁點爐火看火候，回話是提示泡泡、鐵匠那一句伺服器換了新的：結果句收起，換回鐵匠那一句。"""
    game, m = _fired()
    game.smith_furnace()
    after = server.main_view(game)
    line = after["shop"]["line"]
    out = _forge_page(m, """return (async () => {
        H.render();
        """ + _click('{ act: "shop-furnace" }') + """
        await new Promise((ok) => setTimeout(ok, 5));
        return { html: T.els.app.innerHTML, note: H.S.shopNote };
      })();""", S={"shopNote": "你用 3 個精鐵砂熬出了一個玄鋼骨。"},
                      responses={"/api/do/smith_furnace": {"main": after, "message": ""}, "/api/smith_line": m["shop"]["forge"]["line"]})
    assert out["note"] is None and "熬出了一個玄鋼骨" not in out["html"]
    assert f'<p class="shop-line">{line}</p>' in out["html"]


def test_a_poll_with_a_new_smith_line_puts_it_back_after_a_brew(m):
    """輪詢拿到的鐵匠那一句換了（伺服器那一刻說了別的）：熬完的結果句收起；那一句沒換（只是銀兩之類變了）就照舊蓋著，讓人看完。"""
    said = json.loads(json.dumps(m))
    said["shop"]["line"] = "鐵匠抬頭看了你一眼。"
    richer = json.loads(json.dumps(m))
    richer["shop"]["silver"] = 999
    script = """
      H.S.shopTab = "forge"; H.render(); H.S.shopNote = "熬出來了";
      const was = H.S.main; H.setMain(H.S.next); H.shopPolled(was);
      return { note: H.S.shopNote, html: T.els.app.innerHTML };"""
    new_line = run(m, script, S={"next": said})
    assert new_line["note"] is None and "鐵匠抬頭看了你一眼。" in new_line["html"]
    same_line = run(m, script, S={"next": richer})
    assert same_line["note"] == "熬出來了"


@pytest.mark.slow  # 提示泡泡的計時器（約 3 秒）
def test_tapping_a_furnace_that_cannot_look_says_the_whole_line_and_sends_nothing():
    """看過了還沒開爐、今天用掉了：小籤只寫幾個字，點那一團火用提示泡泡講整句（原本爐子底下那一行），不送。"""
    for state, line in ((dict(looked=True), "火候看過了，下一爐照新基準。"), (dict(used=True), "今天看過了，明日再來。")):
        _game, m = _fired(**state)
        out = _forge_page(m, "return (async () => { H.render(); " + _click('{ act: "shop-furnace" }')
                          + " return { calls: T.calls.length, toast: T.els.toast.textContent }; })();")
        assert out == {"calls": 0, "toast": line}


def test_the_hot_fire_stops_for_reduced_motion():
    import re

    css = (server.WEB / "smithy.css").read_text(encoding="utf-8")
    assert re.search(r"\.shop-layer \.furnace\.hot:not\(\.firing\) \.flame svg \{[^}]*animation: fu-hot", css)
    # 同一個選擇器（權重一樣，排在後面才蓋得過）
    assert "@media (prefers-reduced-motion: reduce) { .shop-layer .furnace.hot:not(.firing) .flame svg { animation: none; } }" in css


# ── 鐵匠鋪與合成流程 3.4（C 批）：淬煉、修、拆解併進「裝備庫」一頁；勾選與批量拆解 ──


def _racked(content, world):
    """手上一把（鈍了），裝備庫三把：鈍了淬過兩次的、還利的、神器原品（拆不得、不給勾）。背包精鐵砂 ×4（修、淬煉都收一階）。"""
    from tianxia.state import Weapon

    game = _smith(content, world, name="庫主")
    p = game.state.player
    p.weapon = Weapon(id="兵:9", name="手上刃", kind="劍", attribute="柔", tier=1, quality="下品", edge=60)
    p.rack = [Weapon(id="兵:1", name="鈍刀", kind="刀", attribute="剛", tier=1, quality="中品", edge=40, tempers=2),
              Weapon(id="兵:2", name="利刀", kind="刀", attribute="剛", tier=1, quality="下品"),
              Weapon(id="兵:3", name="原品劍", kind="劍", attribute="快", tier=3, quality="上品", original=True)]
    return game


def _text(html):
    import re

    return re.sub(r"<[^>]+>", "", html)


def _row_of(html, item_id):
    """裝備庫那一列（照 data-id 找；那一列起到下一列之前）。"""
    starts = [i for i in range(len(html)) if html.startswith('<div class="shop-row rk-row', i)]
    for k, start in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else len(html)
        if f'data-id="{item_id}"' in html[start:end]:
            return html[start:end]
    raise AssertionError(item_id)


def _rack_page(m, script="H.render(); return T.els.app.innerHTML;", S=None, responses=None):
    return run(m, 'H.S.shopTab = "rack";' + script, S=S, responses=responses)


def test_the_old_temper_page_opens_the_rack(m):
    html = run(m, "H.render(); return T.els.app.innerHTML;", S={"shopTab": "temper"})  # 網頁沒重新載入、手上還記著舊的那一頁
    assert 'class="shop-tab on" data-act="shop-tab" data-tab="rack"' in html and 'data-tab="temper"' not in html


def test_the_rack_page_has_the_worn_card_on_top_with_its_two_big_buttons(content, world):
    m = server.main_view(_racked(content, world))
    html = _rack_page(m)
    worn = m["shop"]["worn"]
    assert html.index('class="shop-worn"') < html.index(f'data-id="{worn["repair"]["id"]}"') < html.index("rk-cap")
    assert f'data-act="choose" data-id="{worn["temper"]["id"]}"' in html  # 身上那件照舊送原本的選項 id（smith:repair／smith:temper）
    assert f"裝備庫 {m['shop']['rack']['used']}／{m['shop']['rack']['cap']}" in html


def test_each_rack_row_has_a_box_and_four_buttons_with_their_small_print(content, world):
    m = server.main_view(_racked(content, world))
    rows = {r["id"]: r for r in m["shop"]["rack"]["rows"]}
    html = _rack_page(m)
    assert html.count('class="shop-row rk-row') == 3
    dull = _row_of(html, "兵:1")
    assert rows["兵:1"]["repair"]["ok"] and rows["兵:1"]["repair"]["use"] in _text(dull)  # 做得了：小字寫用什麼料多少錢
    assert rows["兵:1"]["temper"]["use"] in _text(dull) and 'data-act="rack-pick" data-id="兵:1"' in dull
    for act in ("shop-wield", "rack-repair", "rack-temper", "shop-dismantle"):
        assert f'data-act="{act}" data-id="兵:1"' in dull
    keen = _row_of(html, "兵:2")
    why = rows["兵:2"]["repair"]["why"]
    assert why and why in _text(keen) and f'disabled title="{why}"><b>修</b>' in keen  # 還不用修：灰掉、原因在鈕的小字
    kept = _row_of(html, "兵:3")
    assert rows["兵:3"]["into"] is None and 'role="checkbox" aria-checked="false" aria-label="勾選【原品劍】" disabled' in kept
    assert "shop-dismantle" not in kept and rows["兵:3"]["keep"] in _text(kept)  # 原品：拆解灰掉寫原因、不給勾


@pytest.mark.slow  # 提示泡泡的計時器（約 3 秒）
def test_repair_and_temper_go_through_menxia_with_the_item_id(content, world):
    m = server.main_view(_racked(content, world))
    reply = {"menxia": None, "main": m, "message": "<p>修好了。</p>"}
    out = _rack_page(m, "return (async () => { H.render(); " + _click('{ act: "rack-repair", id: "兵:1" }')
                     + _click('{ act: "rack-temper", id: "兵:1" }') + " return { calls: T.calls, toast: T.els.toast.textContent }; })();",
                     responses={"/api/menxia/repair_item": reply, "/api/menxia/temper_item": reply})
    assert out["calls"] == [["/api/menxia/repair_item", {"item": "兵:1"}], ["/api/menxia/temper_item", {"item": "兵:1"}]]
    assert "修好了" in out["toast"]


def test_working_a_rack_row_keeps_the_page_where_it_was(content, world):
    """裝備庫那一列按修、淬煉（批量拆解、換上、單件拆解同一條 shopMx）之後，捲的那一層照原本的位置放回去（renderKeepingShop，
    同酒肆 Joy 2026-10-19「操作沒兩下很容易就跑版了」）：不然一件上品淬七次，每按一下都捲回最上面找那一列。"""
    m = server.main_view(_racked(content, world))
    reply = {"menxia": None, "main": m, "message": ""}
    out = _rack_page(m, """return (async () => {
        H.render();
        const body = { scrollTop: 0 };  // 重畫之後的那一層（新畫的，從頂上開始）
        T.qs[".shop-layer"] = { className: "shop-layer shop-smith", querySelector: (s) => (s === ".shop-body" ? { scrollTop: 700 } : null), querySelectorAll: () => [] };
        T.qs[".shop-layer .shop-body"] = body;
        """ + _click('{ act: "rack-repair", id: "兵:1" }') + """
        const repaired = body.scrollTop; body.scrollTop = 0;
        """ + _click('{ act: "rack-temper", id: "兵:1" }') + """
        return { repaired, tempered: body.scrollTop };
      })();""", responses={"/api/menxia/repair_item": reply, "/api/menxia/temper_item": reply})
    assert out == {"repaired": 700, "tempered": 700}


_MELT = """return (async () => {
  T.qs['.ask [data-act="ask-no"]'] = { focus() {} };
  H.render();
  %s
  const lit = T.els.app.innerHTML;
  %s
  const asked = T.bodyHtml.join("");
  const before = T.calls.length;
  %s
  return { lit, asked, before, calls: T.calls, pick: H.S.rackPick };
})();"""


@pytest.mark.slow  # 提示泡泡的計時器（約 3 秒）
def test_ticking_rows_lights_the_batch_button_and_it_asks_with_one_line_each(content, world):
    m = server.main_view(_racked(content, world))
    rows = {r["id"]: r for r in m["shop"]["rack"]["rows"]}
    plain = _rack_page(m)
    assert 'data-act="rack-melt" disabled>拆解勾選的 0 件' in plain  # 一件都沒勾：灰
    script = _MELT % (_click('{ act: "rack-pick", id: "兵:1" }') + _click('{ act: "rack-pick", id: "兵:2" }'),
                      _click('{ act: "rack-melt" }'), _click('{ act: "ask-yes" }'))
    out = _rack_page(m, script, responses={"/api/menxia/dismantle_many": {"menxia": None, "main": m, "message": "<p>拆了 2 件。</p>"}})
    assert 'data-act="rack-melt">拆解勾選的 2 件' in out["lit"] and 'class="shop-row rk-row on"' in out["lit"]
    one, two = rows["兵:1"], rows["兵:2"]
    assert "拆掉這 2 件？拆了就沒了。" in out["asked"] and ">拆掉</button>" in out["asked"]
    import re

    assert [_text(li) for li in re.findall(r"<li>(.*?)</li>", out["asked"])] == [
        f"【鈍刀】→ {one['into']['name']} ×1（淬過 2 次一起沒了）", f"【利刀】→ {two['into']['name']} ×1"]  # 沒淬過不寫
    # 一行裡的字切成不折行的小段（同裝備庫那一列，FB-297）：320 寬折在「淬過 3 次一｜起沒了」中間的那一次（審查 2026-11-01）
    assert '<span class="nb">（淬過 2 次一起沒了）</span>' in out["asked"] and f'<span class="nb">{one["into"]["name"]} ×1</span>' in out["asked"]
    assert out["before"] == 0  # 問了才送
    assert out["calls"] == [["/api/menxia/dismantle_many", {"items": ["兵:1", "兵:2"]}]] and out["pick"] == {}


def test_leaving_and_entering_the_shop_forgets_ticks_the_sheet_and_the_tapped_cell(m):
    """出了店（setMain 看到店收了）、再走進來：裝備庫勾著的、打造頁點開的小單、神器頁點著的格子都清掉，從頭來。"""
    plain = {**m}
    plain.pop("shop")
    picked = {"rackPick": {"兵:1": True}, "shopBrew": {"attr": "剛", "tier": 2}, "divinePick": "wd_x"}
    out = run(m, """
      const now = () => ({ pick: H.S.rackPick, brew: H.S.shopBrew, dv: H.S.divinePick });
      H.render();
      H.setMain(H.S.out); const gone = now();
      Object.assign(H.S, H.S.again); H.S.main = H.S.out;
      H.setMain(H.S.back); return { gone, back: now() };""", S={**picked, "again": picked, "out": plain, "back": m})
    assert out == {"gone": {"pick": {}, "brew": None, "dv": None}, "back": {"pick": {}, "brew": None, "dv": None}}


def test_switching_pages_closes_the_brew_sheet_and_the_tapped_cell(m):
    """換一頁（分頁列）：打造頁點開的小單、神器頁點著的那一格收起，「再列 N 件」收回 8 件；回來那一頁從頭開始。"""
    out = run(m, "return (async () => { H.render(); " + _click('{ act: "shop-tab", tab: "rack" }')
              + " return { brew: H.S.shopBrew, dv: H.S.divinePick, more: H.S.shopMore }; })();",
              S={"shopTab": "forge", "shopBrew": {"attr": "剛", "tier": 2}, "divinePick": "wd_x", "shopMore": True})
    assert out == {"brew": None, "dv": None, "more": False}


def test_ticking_again_unticks(content, world):
    m = server.main_view(_racked(content, world))
    out = _rack_page(m, "return (async () => { H.render(); " + _click('{ act: "rack-pick", id: "兵:1" }') * 2 + " return H.S.rackPick; })();")
    assert out == {}


def test_a_ticked_row_that_is_gone_is_not_sent(content, world):
    """勾了之後那一件不在了（輪詢換了資料：別的分頁拆掉、成了原品）：只認現在列上拆得了的。"""
    m = server.main_view(_racked(content, world))
    script = _MELT % ("", _click('{ act: "rack-melt" }'), _click('{ act: "ask-yes" }'))
    out = _rack_page(m, script, S={"rackPick": {"兵:1": True, "兵:7": True, "兵:3": True}},
                     responses={"/api/menxia/dismantle_many": {"menxia": None, "main": m, "message": ""}})
    assert "拆解勾選的 1 件" in out["lit"] and "拆掉這 1 件？" in out["asked"]
    assert out["calls"] == [["/api/menxia/dismantle_many", {"items": ["兵:1"]}]]


def test_only_ticks_on_rows_you_can_see_count(content, world):
    """先列 8 件（SHOP_RACK_LIST）：按「再列 N 件」勾了第 9 件，換到別頁再回來（列表又收成 8 件），那一件看不見了；鈕上的件數與送出去的
    只算畫面上看得到的列（淬煉之後重排、勾著的那一件被擠到 8 件以後也一樣）。再列出來時那一件照舊勾著。"""
    from tianxia.state import Weapon

    game = _smith(content, world, name="多件客")
    game.state.player.rack = [Weapon(id=f"兵:{k}", name=f"刀{k}", kind="刀", attribute="剛", tier=1, quality="下品") for k in range(1, 11)]
    m = server.main_view(game)
    ninth = m["shop"]["rack"]["rows"][8]["id"]
    out = _rack_page(m, """return (async () => {
        T.qs['.ask [data-act="ask-no"]'] = { focus() {} };
        H.S.shopMore = true; H.render();
        """ + _click('{ act: "rack-pick", id: "%s" }' % ninth) + """
        const ticked = T.els.app.innerHTML;
        """ + _click('{ act: "shop-tab", tab: "forge" }') + _click('{ act: "shop-tab", tab: "rack" }') + """
        const folded = T.els.app.innerHTML;
        """ + _click('{ act: "rack-melt" }') + """
        const asked = T.bodyHtml.length;
        """ + _click('{ act: "shop-more" }') + """
        return { ticked, folded, asked, again: T.els.app.innerHTML };
      })();""")
    assert "拆解勾選的 1 件" in out["ticked"]
    assert f'data-id="{ninth}"' not in out["folded"] and 'data-act="rack-melt" disabled>拆解勾選的 0 件' in out["folded"]
    assert out["asked"] == 0  # 看不見的那一件不問、不送
    assert "拆解勾選的 1 件" in out["again"] and f'aria-checked="true" aria-label="勾選【{m["shop"]["rack"]["rows"][8]["name"]}】"' in out["again"]


def test_rack_rows_keep_words_whole_and_the_buttons_sit_two_by_two_on_the_right(content, world):
    """企劃者 2026-11-03 從三張對比圖挑「乙 右邊二乘二」（原本做的是名字一行、四顆鈕一整行）：勾選框｜名字與那一行數字｜右邊四顆鈕
    二乘二（換上、修／淬煉、拆解）。鈕上的小字切成不折行的小段（FB-297：「精鐵砂×1＋」「5 兩」），右邊那一欄寫 em（小字跟著字級放大，
    375 寬一顆 82px：最長的灰鈕原因「本命兵器不能拆」放得下）；320 這種窄的放不下，二乘二改排在名字底下（≤359px）。"""
    import re

    m = server.main_view(_racked(content, world))
    dull = _row_of(_rack_page(m), "兵:1")
    small = dull[dull.index("<b>修</b>"):]
    small = small[:small.index("</button>")]
    assert small.count('<span class="nb">') >= 2 and "＋" in small
    assert dull.index('class="rk-pick') < dull.index('class="winfo"') < dull.index('class="rk-btns"')  # 二乘二照這個順序排：換上、修／淬煉、拆解
    assert [a for a in re.findall(r'data-act="([\w-]+)"', dull[dull.index('class="rk-btns"'):])][:4] == [
        "shop-wield", "rack-repair", "rack-temper", "shop-dismantle"]
    css = (server.WEB / "smithy.css").read_text(encoding="utf-8")
    assert re.search(r"\.shop-layer \.rk-row \{ display: grid; grid-template-columns: auto minmax\(0, 1fr\) [0-9.]+em;", css)
    assert re.search(r"\.shop-layer \.rk-btns \{ grid-column: 3; grid-row: 1; display: grid; grid-template-columns: repeat\(2, minmax\(0, 1fr\)\);", css)
    assert re.search(r"\.shop-layer \.rk-btn \{ flex-direction: column;", css)
    narrow = re.search(r"@media \(max-width: 359px\) \{([^@]*?)\n\}", css[css.index(".shop-layer .rk-btns {"):])
    assert narrow and ".shop-layer .rk-row { grid-template-columns: auto minmax(0, 1fr); }" in narrow.group(1)
    assert ".shop-layer .rk-btns { grid-column: 1 / -1; grid-row: auto; }" in narrow.group(1)


# ── 鐵匠鋪與合成流程 3.6（E 批）：「淬煉 N/M」照這一件的上限（上品 7）、上品「磨得慢」──


def _qualities(content, world):
    """設定照正式內容（content/config.json）的三組佔位：下 5／中 6／上 7、上品每場少扣 1。手上一把上品淬過兩次，裝備庫上品、下品各一把。"""
    from tianxia.state import Weapon

    content.config.weapons.temper_max_by_quality = {"下品": 5, "中品": 6, "上品": 7}
    content.config.weapons.wear_less_by_quality = {"上品": 1}
    game = _smith(content, world, name="品客")
    p = game.state.player
    p.weapon = Weapon(id="兵:9", name="上品刃", kind="劍", attribute="柔", tier=1, quality="上品", tempers=2)
    p.rack = [Weapon(id="兵:1", name="上品刀", kind="刀", attribute="剛", tier=1, quality="上品"),
              Weapon(id="兵:2", name="下品刀", kind="刀", attribute="剛", tier=1, quality="下品")]
    return game


def test_rack_lines_write_each_items_cap_and_slow_wear(content, world):
    html = _rack_page(server.main_view(_qualities(content, world)))
    top, low = _text(_row_of(html, "兵:1")), _text(_row_of(html, "兵:2"))
    assert "一階上品・淬煉 0/7・鋒利度 100・磨得慢" in top  # 裝備庫就是淬煉的地方：0 次也寫，看得出還能淬幾次
    assert "淬煉 0/5" in low and "磨得慢" not in low


def test_armor_rack_lines_write_each_items_cap_and_slow_wear(content, world):
    """防具頁那一列另一種寫法（耐久度、少扣）：同樣寫「淬煉 N/M」照這一件的上限、上品接「磨得慢」。設定照正式內容防具那一組佔位。"""
    from tianxia.state import Equipment

    content.config.armor.temper_max_by_quality = {"下品": 5, "中品": 6, "上品": 7}
    content.config.armor.wear_less_by_quality = {"上品": 1}
    game = _smith(content, world, name="甲品客")
    game.state.player.rack = [Equipment(id="甲:1", slot="armor", name="上品甲", attribute="柔", tier=1, quality="上品", edge=60),
                              Equipment(id="甲:2", slot="armor", name="下品甲", attribute="剛", tier=1, quality="下品")]
    game.choose("smith:page:armor")
    m = server.main_view(game)
    assert m["shop"]["page"] == "armor"
    html = _rack_page(m)
    rows = {r["id"]: r for r in m["shop"]["rack"]["rows"]}
    top, low = _text(_row_of(html, "甲:1")), _text(_row_of(html, "甲:2"))
    assert f"屬柔・一階上品・淬煉 0/7・{rows['甲:1']['wear_word']} 60・磨得慢・少扣 {rows['甲:1']['cut']}" in top
    assert "淬煉 0/5" in low and "磨得慢" not in low


def test_the_worn_card_draws_this_items_cap_in_pips(content, world):
    html = _rack_page(server.main_view(_qualities(content, world)))
    worn = html[html.index('class="shop-worn"'):html.index('class="shop-bigs"')]
    tempers = worn[worn.index('class="tempers"'):]
    assert tempers.count('<i class="on"></i>') == 2 and tempers.count('<i class=""></i>') == 5  # 上品七格
    assert "淬煉 2/7" in worn and "磨得慢" in worn


def test_the_forged_card_writes_the_cap_and_slow_wear_from_its_row(content, world):
    m = server.main_view(_qualities(content, world))
    script = "H.S.shopReveal = H.S.next; H.S.shopOpened = true; H.render(); return T.els.app.innerHTML;"
    top = run(m, script, S={"next": {**FORGED, "id": "兵:1", "where": "rack"}})
    assert '<p class="meta">淬煉 0/7・磨得慢</p>' in top[top.index('class="forge-card'):]
    low = run(m, script, S={"next": {**FORGED, "id": "兵:2", "where": "rack"}})
    assert '<p class="meta">淬煉 0/5</p>' in low and "磨得慢" not in low[low.index('class="forge-card'):]
