"""店面微調（企劃者 2026-10-14 看了 QA 列的「跟草圖不一樣」，四件都照草圖改；店面獨立介面設計第十一節），加上 FB-194、FB-195。"""
from __future__ import annotations

from test_shop import _smith

# ── 4：打造頁素材格照屬性再照階排 ──

MIXED = {"kuai_1": 2, "gang_3": 1, "gang_1": 4, "gang_2": 1}  # 測試內容只有剛一到三階與快一階；現在的排法是高階先、數量多的先


def test_material_cells_go_by_attribute_then_tier(content, world):
    """剛、柔、快、慢各一排，每排一階到三階；背包沒有的不畫。素材格與「這一爐會怎樣」的格子同一個順序。"""
    game = _smith(content, world)
    game.state.player.materials = dict(MIXED)
    forge = game.shop_view()["forge"]
    order = ["gang_1", "gang_2", "gang_3", "kuai_1"]
    assert [mat["id"] for mat in forge["materials"]] == order
    assert [cell["id"] for cell in forge["line"]["cells"]] == order
    assert [cell["id"] for cell in game.smith_line("劍", "gang_1")["cells"]] == order


def test_an_attribute_outside_the_four_goes_after_them(content, world):
    """陰陽虛實的素材（正式內容現在沒有）排在剛柔快慢後面。"""
    from tianxia import shopview

    rank = shopview.attribute_rank
    assert rank("剛") < rank("柔") < rank("快") < rank("慢") < rank("陰") and rank("慢") < rank("實")


def test_the_forge_page_draws_one_row_per_attribute(content, world):
    """網頁：素材格一屬性一排，排頭寫屬性；仍在 .cells 裡、排在爐子與開爐鈕後面。"""
    import server
    from test_shop_web import run

    game = _smith(content, world, name="排客")
    game.state.player.materials = dict(MIXED)
    html = run(server.main_view(game), 'H.S.shopTab = "forge"; H.render(); return T.els.app.innerHTML;')
    cells = html[html.index('class="cells"'):]
    assert cells.count('class="cell-row"') == 2 and '<span class="row-attr gang">剛</span>' in cells and '<span class="row-attr kuai">快</span>' in cells
    assert cells.index('data-id="gang_1"') < cells.index('data-id="gang_3"') < cells.index('data-id="kuai_1"')
    # 每格照階擺在自己那一欄（一階、二階、三階對齊；少了的那一階空著，不畫格子）
    assert 'class="cell t3"' in cells[cells.index('<span class="row-attr gang">'):cells.index('<span class="row-attr kuai">')]


# ── 1：鐵匠鋪「架上」頁上半一塊爐火加鐵砧 ──


def test_the_shelf_page_opens_with_a_forge_and_anvil_above_the_wares(content, world):
    """企劃者 2026-10-14 微調（草圖 container.html 的 A）：架上那一頁上面一塊爐火與鐵砧（內嵌 SVG），貨卡往下移；只有架上那一頁有。"""
    import server
    from test_shop_web import run

    m = server.main_view(_smith(content, world, name="爐客"))
    shelf = run(m, 'H.S.shopTab = "shelf"; H.render(); return T.els.app.innerHTML;')
    assert 'class="smith-hero"' in shelf and "<svg" in shelf[shelf.index('class="smith-hero"'):]
    assert shelf.index('class="smith-hero"') < shelf.index('class="shop-grid"')
    forge = run(m, 'H.S.shopTab = "forge"; H.render(); return T.els.app.innerHTML;')
    assert 'class="smith-hero"' not in forge


# ── 2：懸賞榜告示照草圖改小、放大的紙貼在畫面下緣 ──


def _board_view(content, world, posts):
    import server
    from test_shop2 import _board

    game = _board(content, world, posts, name="榜客")
    return game, server.main_view(game)


def test_board_notes_are_compact_with_a_colored_tag_and_the_rest_on_the_paper(content, world):
    """企劃者 2026-10-14 微調（草圖 bounty.html）：每張只寫種類・哪一方（色塊小標籤）、目標、期限與名額，重賞、你有幾件合用各一個小字；
    完整的要求放在點開放大的紙上。"""
    from test_shop2 import SCOUT, STRIKE
    from test_shop2_web import run

    from tianxia import bounties

    game, m = _board_view(content, world, [SCOUT, STRIKE])
    scout = game.state.world.bounties[0]
    html = run(m, "H.render(); return T.els.app.innerHTML;")
    assert '<span class="tag">打探・官軍</span>' in html and bounties.due_short(scout, content, game.state.world) in html
    assert bounties.how(content, scout) not in html  # 要做什麼寫在紙上
    zoomed = run(m, f'H.S.boardZoom = "{scout.id}"; H.render(); return T.els.app.innerHTML;')
    assert bounties.how(content, scout) in zoomed and 'class="board-sheet"' in zoomed and "reveal-layer" not in zoomed
    assert 'class="shop-body zooming"' in zoomed  # 紙開著時木板底下多留一段，告示捲得到紙的上面


def test_the_notice_shows_the_short_due_and_the_paper_the_full_one_fb196(content, world):
    """FB-196：告示最後一行在 375 寬折成「期限 第 3 週・週一 00:00・名額還剩」換行一個數字，十四張都這樣。照草圖告示上寫短的
    （due_short，不折行），完整的時刻與「名額還剩 N」（due_line）只在點開的紙上。"""
    from test_shop2 import SCOUT, STRIKE
    from test_shop2_web import _css, _rule, run

    from tianxia import bounties

    game, m = _board_view(content, world, [SCOUT, STRIKE])
    scout = game.state.world.bounties[0]
    full, short = bounties.due_line(game.state, content, scout), bounties.due_short(scout, content, game.state.world)
    note = next(n for n in m["shop"]["notes"] if n["id"] == scout.id)
    assert (note["due"], note["short"]) == (full, short)
    html = run(m, "H.render(); return T.els.app.innerHTML;")
    assert f'<small class="due">{short}</small>' in html and full not in html
    zoomed = run(m, f'H.S.boardZoom = "{scout.id}"; H.render(); return T.els.app.innerHTML;')
    assert f'<p class="due">{full}</p>' in zoomed  # 告示上已經沒有整行，有就是紙上的
    assert "white-space: nowrap" in _rule(_css(), ".shop-board .note .due")


def test_the_board_css_matches_the_mockup(content, world):
    """紅色圖釘、色塊小標籤（討伐紅、打探藍、護送綠、求藝求兵金、通緝黑）、紙貼在畫面下緣、紙太長自己捲。"""
    from test_shop2_web import _css, _rule

    css = _css()
    assert "background: #8e2a22" in _rule(css, ".shop-board .note::before")
    for kind, color in (("strike", "#a8322a"), ("scout", "#2f5d8a"), ("escort", "#3f7d5c"), ("art", "#9a6a2a"), ("wanted", "#2a241d")):
        assert f".shop-board .note.k-{kind} .tag" in css and color in css[css.index(f".shop-board .note.k-{kind} .tag"):][:200]
    sheet = _rule(css, ".shop-board .board-sheet")
    assert "position: absolute" in sheet and "bottom: calc(12px" in sheet and "max-height:" in sheet and "overflow-y: auto" in sheet


# ── 3：交差朱印蓋在那張告示上 ──


def test_a_handed_in_notice_is_stamped_in_place_then_fades(content, world):
    """企劃者 2026-10-14 微調：被交掉的那張告示本身蓋上「交差」，停一下再跟著告示淡出，不再在畫面正中間蓋大印。
    那張還畫在原本的位置（伺服器那一份已經沒有它），點不了。"""
    import server
    from test_shop2 import ARMS, SCOUT, SWORD, _board
    from test_shop2_web import run

    from tianxia.state import Equipment

    game = _board(content, world, [SCOUT, ARMS], name="交差客")
    game.state.player.rack = [Equipment(**SWORD)]
    scout, arms = (b.id for b in game.state.world.bounties)
    game.choose(f"bounty:pick:{arms}")
    before = server.main_view(game)
    game.choose(f"bounty:give:{arms}:兵:1")
    after = server.main_view(game)
    out = run(before, """
      H.render(); const was = H.S.main.shop; H.setMain(H.S.next);
      H.boardHanded("bounty:give:%s:兵:1", was);
      return T.els.app.innerHTML;""" % arms, S={"next": after})
    assert 'class="note k-arms done"' in out and '<i class="stamp">交差</i>' in out and "board-stamp" not in out
    assert out.index('class="note k-arms done"') < out.index(f'data-id="{scout}"')  # 原本排在前面的位置
    done = out[out.index('class="note k-arms done"') - 5:]
    assert 'data-act="board-zoom"' not in done[:done.index("</div>")]


def test_the_stamp_fades_with_the_note_unless_motion_is_reduced():
    from test_shop2_web import _css, _rule

    css = _css()
    assert "animation: notedone" in _rule(css, ".shop-board .note.done")
    assert "@media (prefers-reduced-motion: reduce) { .shop-board .note.done { animation: none; } }" in css
    assert ".board-stamp" not in css and "stampfade" not in css


# ── FB-194：「比你騎的快／慢」跟卡上的數字同一個算法 ──


def test_faster_or_slower_follows_the_speed_bar_on_the_card(content, world):
    """FB-194：照卡上「路上快」那一條（乘了飽足、照畫面上的整數百分比）比，數字大的那匹寫「比你騎的快」；一樣大寫「一樣快」。
    （以前照吃飽的腳力比：騎著餓了的駑馬上品，卡上數字比較大的兩匹反而寫「比你騎的慢」。）"""
    from test_shop2 import _horse, _market

    from tianxia import shopview

    ride = _horse(name="黑鬃馬", tier=1, quality="上品", edge=35)
    game = _market(content, world, horse=ride, name="比馬")
    game.state.player.rack = [_horse("騎:2", "白蹄馬", 1, "下品"), _horse("騎:3", "黃棕馬", 1, "中品"), _horse("騎:4", "花斑馬", 1, "上品", edge=35)]
    stalls = game.shop_view()["stalls"]
    speed = {s["id"]: next(b["value"] for b in s["bars"] if b["key"] == "speed") for s in stalls if not s.get("empty")}
    worn = speed["騎:1"]
    for stall in stalls[2:]:
        want = shopview.FASTER if speed[stall["id"]] > worn else shopview.SLOWER if speed[stall["id"]] < worn else shopview.SAME
        assert stall["compare"] == want, (stall["id"], speed[stall["id"]], worn)
    assert [s["compare"] for s in stalls[2:]] == [shopview.FASTER, shopview.FASTER, shopview.SAME]


# ── FB-195：馬市兩頁搶，按下去被擋時說為什麼 ──


def test_a_market_buy_lost_to_another_tab_says_why(content, world):
    """FB-195：畫面上「買下」亮著，錢卻在另一個分頁花掉了：Game.choose 回為什麼不成的那一句（Refused，伺服器照它跳提示，同懸賞榜 FB-162），
    馬販那一句換成錢不夠那一組；什麼都沒買、錢不動。"""
    from test_shop2 import _market

    from tianxia import mounts, shopview
    from tianxia.engine import Refused

    game = _market(content, world, silver=300, name="搶馬")
    assert any(o.id == mounts.BUY and o.enabled for o in game.options(odds=False))
    p = game.state.player
    p.stats["silver"] = 40
    msgs = game.choose(mounts.BUY)
    price = content.config.mounts.shop_price
    assert isinstance(msgs, Refused) and list(msgs) == [f"（還差 {price - 40} 兩。）"]
    assert p.mount is None and p.stats["silver"] == 40
    assert p.shop_line == "short_silver" and shopview.line_text(game.state, content, "market") in content.shop_lines["market"]["short_silver"]


def test_a_market_feed_or_swap_lost_to_another_tab_says_why(content, world):
    from test_shop2 import _horse, _market

    from tianxia import equipment, mounts
    from tianxia.engine import Refused

    game = _market(content, world, horse=_horse(edge=40), name="搶餵")
    p = game.state.player
    p.rack = [_horse("騎:2", "黑鬃馬", 1, "下品")]
    p.materials = {}  # 料在另一個分頁用掉了
    msgs = game.choose(mounts.FEED)
    assert isinstance(msgs, Refused) and list(msgs) == [f"（{equipment.NO_REPAIR_MATERIAL}。）"]
    p.rack = []  # 那一匹在另一個分頁換走了
    msgs = game.choose(f"{mounts.WIELD}騎:2")
    assert isinstance(msgs, Refused) and list(msgs) == [f"（{equipment.WIELD_MISSING.rstrip('。')}。）"]


def test_the_paper_and_held_slots_stay_light_paper_in_dark_mode():
    """實機看到的（深色主題）：紙是固定淺色，紙上一般的鈕（放回去、收起）與手上那一排的格子卻跟著深色主題變黑。一起固定成紙色。"""
    from test_shop2_web import _css, _rule

    css = _css()
    assert "#f6edd8" in _rule(css, ".shop-board .slot")
    plain = _rule(css, ".shop-board .paper .btn:not(.primary):not(.danger)")
    assert "#fbf7ef" in plain and "#2a241d" in plain


# ── 終審修正 ──


def test_the_held_stamp_on_the_paper_stays_out_of_the_buttons():
    """終審 I1：告示上的「已揭」移到右下角，同一條規則也套到放大的紙上，蓋住「收起」的一角、那一角按不到。紙上的印照舊在右上角、點不到它。"""
    from test_shop2_web import _css, _rule

    stamp = _rule(_css(), ".shop-board .paper .stamp")
    assert "top: 10px" in stamp and "bottom: auto" in stamp and "pointer-events: none" in stamp


def test_the_docked_paper_keeps_clear_of_the_notch_and_the_home_bar():
    """終審 M2（提為 Important）：紙貼在下緣時沒算 iPhone 的安全區域，三層交出清單的鈕伸進底下的橫條、上緣蓋到掌櫃那一句。
    紙也一定在招牌那一列底下（招牌 z-index 3、紙 2）。"""
    from test_shop2_web import _css, _rule

    css = _css()
    sheet = _rule(css, ".shop-board .board-sheet")
    assert "bottom: calc(12px + var(--bottom" in sheet and "var(--top" in sheet and "var(--bottom" in sheet[sheet.index("max-height"):]
    assert "z-index: 2" in sheet and "z-index: 3" in _rule(css, ".shop-board .shop-bar")


def test_a_stale_market_click_leaves_another_shops_keeper_alone(content, world):
    """終審 M1（提為 Important）：另一個分頁已經出了馬市、走進鐵匠鋪，這一頁還停在馬市按「買下」：回馬市那一句原因（FB-195），
    可是不改鐵匠那一句（他在鐵匠鋪什麼都沒做）。"""
    from test_shop2 import _market

    from tianxia import mounts
    from tianxia.engine import Refused

    content.config.weapons.enabled = True
    game = _market(content, world, silver=300, name="跨店")
    game.choose(mounts.BACK)
    game.choose("act:smith")
    p = game.state.player
    assert p.picking_smith and p.shop_line == "enter"
    msgs = game.choose(mounts.BUY)
    assert isinstance(msgs, Refused) and p.shop_line == "enter" and p.shop_hold == ""
