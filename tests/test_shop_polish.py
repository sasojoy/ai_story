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
    assert '<span class="tag">打探・官軍</span>' in html and bounties.due_line(game.state, content, scout) in html
    assert bounties.how(content, scout) not in html  # 要做什麼寫在紙上
    zoomed = run(m, f'H.S.boardZoom = "{scout.id}"; H.render(); return T.els.app.innerHTML;')
    assert bounties.how(content, scout) in zoomed and 'class="board-sheet"' in zoomed and "reveal-layer" not in zoomed
    assert 'class="shop-body zooming"' in zoomed  # 紙開著時木板底下多留一段，告示捲得到紙的上面


def test_the_board_css_matches_the_mockup(content, world):
    """紅色圖釘、色塊小標籤（討伐紅、打探藍、護送綠、求藝求兵金、通緝黑）、紙貼在畫面下緣、紙太長自己捲。"""
    from test_shop2_web import _css, _rule

    css = _css()
    assert "background: #8e2a22" in _rule(css, ".shop-board .note::before")
    for kind, color in (("strike", "#a8322a"), ("scout", "#2f5d8a"), ("escort", "#3f7d5c"), ("art", "#9a6a2a"), ("wanted", "#2a241d")):
        assert f".shop-board .note.k-{kind} .tag" in css and color in css[css.index(f".shop-board .note.k-{kind} .tag"):][:200]
    sheet = _rule(css, ".shop-board .board-sheet")
    assert "position: absolute" in sheet and "bottom: 12px" in sheet and "max-height:" in sheet and "overflow-y: auto" in sheet
