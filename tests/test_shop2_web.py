"""店面第二批的網頁（店面獨立介面設計第三、四節）：假瀏覽器照 test_prologue_web 的那一套跑整支 app.js（同 tests/test_shop_web.py）。
斷言只看 T.els.app.innerHTML——外殼與店面那一層；江湖頁的舊選單畫在 T.els.page，所以斷言裡的 data-act="choose" 都是店面上的鈕。"""
from __future__ import annotations

import json

import pytest
from test_prologue_web import DRIVER as PROLOGUE_DRIVER
from test_shop2 import ARMS, SCOUT, SWORD, _board, _horse, _ids, _market

import server
import webharness
from tianxia import mounts, shopview
from tianxia.state import Equipment

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
NAMES_START = 'wholeApp(["S", '
assert PROLOGUE_DRIVER.count(NAMES_START) == 1
DRIVER = PROLOGUE_DRIVER.replace(
    NAMES_START, 'wholeApp(["S", "shopHtml", "renderShop", "shopPolled", "marketHtml", "boardHtml", "boardHanded", "divineFormHtml", ')


def run(m, script, S=None, responses=None):
    return webharness.run(DRIVER, {"m": m, "script": script, "S": S or {}, "menxia": None, "stored": {}, "responses": responses or {}})


def _click(dataset: str) -> str:
    """送一次點擊給 app.js 的 click 處理器：點到的元素帶 dataset（JS 物件字面值）。同 tests/test_shop_web.py::_click。"""
    return ("await T.docListeners.click[0]({ target: { closest: () => ({ dataset: " + dataset
            + ", classList: { contains: () => false, add() {}, remove() {} }, isConnected: false }) } });")


@pytest.fixture
def market(content, world):
    game = _market(content, world, horse=_horse(edge=40))
    game.state.player.rack = [_horse("騎:2", "黑鬃馬", 1, "上品")]
    return server.main_view(game)


# ── Task 4：共用店面框與馬市 ──


def test_the_market_draws_a_row_of_stalls_and_the_ridden_horse_card(market):
    html = run(market, "H.render(); return T.els.app.innerHTML;")
    shop = market["shop"]
    assert 'class="shop-layer shop-market"' in html and shop["sign"] in html and shop["line"] in html
    assert f'data-act="choose" data-id="{mounts.BACK}"' in html and "出店" in html
    assert html.count('data-act="shop-horse"') == 3  # 你騎的、待售、裝備庫一匹
    assert f'data-act="choose" data-id="{mounts.FEED}"' in html and f"{mounts.WEAR_WORD} 40" in html  # 預設點著你騎的
    assert shopview.HUNGRY_NOTE in html and "省體力" in html
    assert "shop-tabs" not in html  # 馬市不分頁


def test_tapping_a_stall_shows_its_card(market):
    out = run(market, "return (async () => { H.render(); " + _click('{ act: "shop-horse", id: "騎:2" }') + " return T.els.app.innerHTML; })();")
    assert f'data-id="{mounts.WIELD}騎:2"' in out and shopview.SLOWER in out and f'data-id="{mounts.FEED}"' not in out


def test_no_horse_draws_an_empty_stall_and_focuses_the_sale(content, world):
    m = server.main_view(_market(content, world))
    html = run(m, "H.render(); return T.els.app.innerHTML;")
    assert shopview.NO_HORSE in html and f'data-act="choose" data-id="{mounts.BUY}"' in html
    assert html.count('data-act="shop-horse"') == 1  # 空的那一間點不了


def test_a_greyed_card_button_says_why(content, world):
    m = server.main_view(_market(content, world, silver=10))
    html = run(m, "H.render(); return T.els.app.innerHTML;")
    assert f"還差 {content.config.mounts.shop_price - 10} 兩" in html and "disabled" in html


def test_moving_from_the_smithy_to_the_market_starts_the_market_fresh(content, world, market):
    from test_shop import _smith

    smith = server.main_view(_smith(content, world, name="鐵客"))
    out = run(smith, """
      H.S.shopTab = "rack"; H.S.shopReveal = { id: "兵:1", glow: "none" }; H.S.shopHorse = "騎:9"; H.render();
      const was = H.S.main; H.setMain(H.S.next); const drew = H.shopPolled(was);
      return { tab: H.S.shopTab, reveal: H.S.shopReveal, horse: H.S.shopHorse, drew, html: T.els.app.innerHTML };""", S={"next": market})
    assert (out["tab"], out["reveal"], out["horse"], out["drew"]) == ("shelf", None, None, True)
    assert "shop-market" in out["html"] and "shop-smith" not in out["html"]


def test_a_market_poll_redraws_only_the_shop(market):
    richer = json.loads(json.dumps(market))
    richer["shop"]["silver"] = 999
    out = run(market, """
      H.render(); T.els.page.innerHTML = "OLD";
      const layer = { outerHTML: "" }; T.qs[".shop-layer"] = layer;
      const was = H.S.main; H.setMain(H.S.next); H.shopPolled(was);
      return { page: T.els.page.innerHTML, layer: layer.outerHTML };""", S={"next": richer})
    assert out["page"] == "OLD" and "銀 999" in out["layer"]


# ── Task 5：懸賞榜 ──


@pytest.fixture
def board(content, world):
    game = _board(content, world, [SCOUT, ARMS])
    game.state.player.rack = [Equipment(**SWORD)]
    return game


def test_the_board_draws_the_held_row_and_pinned_notes(board):
    m = server.main_view(board)
    html = run(m, "H.render(); return T.els.app.innerHTML;")
    shop = m["shop"]
    assert 'class="shop-layer shop-board"' in html and shop["held"]["head"] in html and shop["held"]["left_text"] in html
    assert html.count('data-act="board-zoom"') == 2 and "k-scout" in html and "k-arms" in html  # 手上沒有揭著的：只有兩張告示點得開
    assert shop["notes"][0]["have"] in html  # 交得出的求藝求兵排在前面（沒揭著的）
    assert 'data-act="choose" data-id="bounty:back"' in html


def test_tapping_a_note_opens_the_paper_with_take_and_put_back(board):
    m = server.main_view(board)
    scout, _arms = _ids(board)
    out = run(m, "return (async () => { H.render(); " + _click('{ act: "board-zoom", id: "' + scout + '" }') + " return T.els.app.innerHTML; })();")
    assert f'data-act="choose" data-id="bounty:take:{scout}"' in out and 'data-act="board-close"' in out and "放回去" in out
    note = next(n for n in m["shop"]["notes"] if n["id"] == scout)
    assert note["reward"] in out and note["due"] in out


def test_a_greyed_take_shows_its_reason_on_the_paper(content, world):
    from test_shop2 import _board as board_of

    game = board_of(content, world, [dict(kind="escort", faction="guan", silver=15, deeds=2, location="lake", end="cave")])
    (escort,) = _ids(game)
    m = server.main_view(game)
    html = run(m, f'H.S.boardZoom = "{escort}"; H.render(); return T.els.app.innerHTML;')
    assert f"要在{content.locations['lake'].name}接。" in html and "disabled" in html


def test_dropping_asks_first(board):
    scout, _arms = _ids(board)
    board.choose(f"bounty:take:{scout}")
    m = server.main_view(board)
    out = run(m, """return (async () => {
      T.qs['.ask [data-act="ask-no"]'] = { focus() {} };
      H.S.boardZoom = "%s"; H.render();
      %s
      return { asked: T.bodyHtml.join(""), calls: T.calls.map((c) => c[0]), html: T.els.app.innerHTML };
    })();""" % (scout, _click('{ act: "shop-ask", id: "bounty:drop:' + scout + '", confirm: "要放回去嗎", yes: "放棄" }')))
    assert "要放回去嗎" in out["asked"] and "/api/choose" not in out["calls"]
    assert "已揭" in out["html"]


def test_picking_a_hand_in_shows_the_list(board):
    _scout, arms = _ids(board)
    board.choose(f"bounty:pick:{arms}")
    m = server.main_view(board)
    html = run(m, "H.render(); return T.els.app.innerHTML;")
    assert f'data-act="choose" data-id="bounty:give:{arms}:兵:1"' in html  # 伺服器說 picked：自己放大那一張、列出合用的
    assert 'data-act="shop-leave"' in html  # 第三層：出店先回到懸賞榜


def test_closing_the_hand_in_list_unpicks_first(board):
    _scout, arms = _ids(board)
    board.choose(f"bounty:pick:{arms}")
    m = server.main_view(board)
    board.choose("bounty:unpick")
    after = server.main_view(board)
    out = run(m, "return (async () => { H.render(); " + _click('{ act: "board-close" }') + " return { calls: T.calls.map((c) => [c[0], c[1]]), zoom: H.S.boardZoom }; })();",
              responses={"/api/choose": {"main": after}})
    assert ["/api/choose", {"id": "bounty:unpick"}] in out["calls"] and out["zoom"] is None


def test_leaving_from_the_third_layer_goes_back_to_the_board_first(board):
    _scout, arms = _ids(board)
    board.choose(f"bounty:pick:{arms}")
    m = server.main_view(board)
    board.choose("bounty:unpick")
    after = server.main_view(board)
    out = run(m, "return (async () => { H.render(); " + _click('{ act: "shop-leave" }') + " return T.calls.filter((c) => c[0] === '/api/choose').map((c) => c[1].id); })();",
              responses={"/api/choose": {"main": after}})
    assert out == ["bounty:unpick", "bounty:back"]


def test_a_hand_in_stamps_the_note_done(board):
    _scout, arms = _ids(board)
    board.choose(f"bounty:pick:{arms}")
    before = server.main_view(board)
    board.choose(f"bounty:give:{arms}:兵:1")
    after = server.main_view(board)
    out = run(before, """
      H.render(); const was = H.S.main.shop; H.setMain(H.S.next);
      H.boardHanded("bounty:give:%s:兵:1", was);
      return { stamp: H.S.boardStamp, html: T.els.app.innerHTML };""" % arms, S={"next": after})
    assert out["stamp"]["id"] == arms and "交差" in out["html"]


def test_a_refused_hand_in_does_not_stamp(board):
    _scout, arms = _ids(board)
    board.choose(f"bounty:pick:{arms}")
    before = server.main_view(board)
    out = run(before, """
      H.render(); const was = H.S.main.shop; H.setMain(H.S.next);
      H.boardHanded("bounty:give:%s:兵:1", was);
      return H.S.boardStamp;""" % arms, S={"next": before})
    assert out is None


def test_the_stamp_and_notes_respect_reduced_motion():
    from pathlib import Path

    css = (Path(__file__).resolve().parents[1] / "web" / "style.css").read_text(encoding="utf-8")
    assert "@media (prefers-reduced-motion: reduce) { .board-stamp { animation: none; } }" in css


# ── Task 7：FB-191 ──


def test_rack_rows_do_not_break_inside_a_word(content, world):
    """FB-191：店面「裝備庫」頁每一件那一行（「刀・屬剛・一階中品・鋒利度 100・用不上」）照 FB-132 的 nbChunks 切成不折行的小段，
    375 寬折行時不把「用不上」拆成「用不」「上」。"""
    from test_shop import _smith

    from tianxia.state import Weapon

    game = _smith(content, world, name="庫客")
    p = game.state.player
    p.weapon = Weapon(id="兵:9", name="手上刃", kind="劍", attribute="柔", tier=1, quality="下品")
    p.rack = [Weapon(id="兵:1", name="庫刃", kind="刀", attribute="剛", tier=1, quality="中品")]
    html = run(server.main_view(game), 'H.S.shopTab = "rack"; H.render(); return T.els.app.innerHTML;')
    assert '<span class="nb">用不上</span>' in html and '<span class="nb">一階中品・</span>' in html


# ── Task 9：FB-193 ──


def test_a_refused_divine_name_on_the_forged_card_keeps_its_reason(content, world):
    """FB-193：出爐卡（與店面裝備庫那一頁）上定名被拒，原因寫在表單裡一行，改字時還看得到；修練頁那一張共用同一個寫法。"""
    from test_shop import _smith
    from test_shop_web import _SHOP_DIVINE_REFUSED

    m = server.main_view(_smith(content, world, name="定名"))
    m["shop"]["pending"] = {"兵:1": "墜星劍"}
    why = "這個名字不行：名字像是另一種兵器。"
    reply = {"/api/menxia/name_divine": {"menxia": None, "main": m, "message": why}}
    card = {"id": "兵:1", "slot": "weapon", "name": "無名神器", "grade": "三階上品・神器", "kind": "劍", "attribute": "剛", "value": None,
            "fit": "", "glow": "redgold", "first": True, "where": "rack", "divine": "墜星劍"}
    out = run(m, _SHOP_DIVINE_REFUSED.replace(
        "return { kept, posts, toast, after: input.value };",
        "return { kept, why: H.S.divineWhy['兵:1'], form: H.divineFormHtml('兵:1', '墜星劍', true), plain: H.divineFormHtml('兵:1', '墜星劍') };"),
        S={"shopReveal": card, "shopOpened": True}, responses=reply)
    assert out["kept"] == "斬月刀" and out["why"] == why
    assert f'<p class="form-why">{why}</p>' in out["form"] and f'<p class="form-why">{why}</p>' in out["plain"]
