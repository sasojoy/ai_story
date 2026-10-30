"""FB-225：桌機上店面拉滿整個螢幕（主料、輔料兩格各半個螢幕寬、素材格四欄拉滿），企劃者「最主要是寬度的設計沒有照著 UI 框架延續」。
遊戲本體在電腦上是一欄 640px（.shell、.tabs-inner）；店面、武學譜那本書、遊戲裡讀傳那一層也照這一欄：底色只畫在欄裡、欄外是頁面底色，
欄裡的東西照欄排，會捲的那一層照舊整片寬（兩邊各留一條捲軸寬的溝）、捲的內容包在 .shop-col。手機（窄於 641px）一條規則都不生效。
CSS 照原字查；畫面照 tests/test_shop2_web.py 的假瀏覽器跑整支 app.js。"""
from __future__ import annotations

import re

import pytest
from test_shop import _smith
from test_shop2 import SCOUT, STRIKE, _board, _horse, _market

import server
import webharness
from pathlib import Path

from tianxia.core import features as features_core

DESKTOP = "@media (min-width: 641px) {"
needs_node = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


def _css(name: str = "style.css") -> str:
    return (server.WEB / name).read_text(encoding="utf-8")


def _block(css: str, marker: str) -> str:
    """marker 那一段註解之後的第一個桌機 @media 區塊（含大括號），照大括號配對切出來。"""
    start = css.index(DESKTOP, css.index(marker))
    depth = 0
    for i in range(start, len(css)):
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
            if depth == 0:
                return css[start:i + 1]
    raise AssertionError("大括號沒配上")


def _rules(block: str) -> dict[str, str]:
    """區塊裡的每一條規則：selector → 大括號裡那一段（同一個 selector 只會寫一次）。"""
    inner = re.sub(r"/\*.*?\*/", "", block[len(DESKTOP):-1], flags=re.S)  # 註解不是選擇器（FB-305 那一段前面有一段說明）
    return {sel.strip(): body.strip() for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", inner)}


def _column() -> int:
    """遊戲那一欄的寬度：.shell 與底部分頁列 .tabs-inner 的 max-width（兩個要一樣）。"""
    css = _css()
    shell = re.search(r"\.shell \{[^}]*max-width: (\d+)px", css)
    tabs = re.search(r"\.tabs-inner \{[^}]*max-width: (\d+)px", css)
    assert shell and tabs and shell.group(1) == tabs.group(1)
    return int(shell.group(1))


def test_the_desktop_block_starts_just_above_the_game_column():
    """斷點是 641px：手機（375、390、430）與欄寬以內的視窗一條都不生效，畫面一個像素都不變。"""
    assert DESKTOP == f"@media (min-width: {_column() + 1}px) {{"
    assert _block(_css(), "FB-225")


def test_the_shop_draws_its_colors_only_in_the_game_column():
    """三間店的底色（爐火、土黃、木紋）照欄寬畫在中間、不重複；欄外是遊戲本來的頁面底色。深色主題的馬市那一條在前面，蓋不掉這一條。
    （功能包切出去的樣式排在 style.css 後面，蓋得掉這一條：見下一條。）"""
    col = _column()
    rules = _rules(_block(_css(), "FB-225"))
    # 軍需帳（素材與經濟 B6）、擂台的紅布（FB-306）、打點的雅間（第 9 批畫面乙）、商城的紫檀（商城第二批）同一條
    bg = rules[".shop-layer.shop-smith, .shop-layer.shop-market, .shop-layer.shop-board, .shop-layer.shop-donate, .shop-layer.shop-arena, "
               ".shop-layer.shop-dadian, .shop-layer.shop-mall"]
    assert "background-color: var(--paper)" in bg and f"background-size: min(100%, {col}px) 100%" in bg
    assert "background-position: 50% 0" in bg and "background-repeat: no-repeat" in bg


def test_a_package_stylesheet_paints_its_shop_color_in_the_game_column_again():
    """功能包切出去的樣式（FEATURES 的 web 裡的 .css，現在是商城的 web/mall.css；開發規範手冊 3.7）在 index.html 排在 style.css 後面：
    它替自己那一層寫的 background 簡寫會把上面那一條欄寬的底色蓋回整片寬（2026-10-31 商城切出來時實機 1280 寬量到的退步）。
    所以上面那一條列到的那一層，只要在功能包的檔裡寫了 background 簡寫，同一個檔在它後面的電腦寬那一段就要照上面那一條再寫一次。"""
    col = _column()
    layers = [s.strip() for s in next(sel for sel in _rules(_block(_css(), "FB-225")) if ".shop-layer.shop-smith" in sel).split(",")]
    page = (server.WEB / "index.html").read_text(encoding="utf-8")
    checked = []
    for name in (n for n in features_core.web_files() if n.endswith(".css")):
        css = re.sub(r"/\*.*?\*/", "", _css(name), flags=re.S)
        assert page.index('href="/static/style.css"') < page.index(f'href="/static/{name}"')
        for layer in layers:
            mobile = re.search(rf"(?m)^{re.escape(layer)} \{{([^}}]*)\}}", css)
            if mobile is None or not re.search(r"(^|;)\s*background:", mobile.group(1)):
                continue
            again = re.search(rf"{re.escape(layer)} \{{([^}}]*)\}}", css[css.index(DESKTOP, mobile.end()):])
            assert again, f"{name} 沒有在電腦寬再寫一次 {layer} 的底色"
            for decl in ("background-color: var(--paper)", f"background-size: min(100%, {col}px) 100%", "background-position: 50% 0",
                         "background-repeat: no-repeat"):
                assert decl in again.group(1), (name, layer, decl)
            checked.append((name, layer))
    assert ("mall.css", ".shop-layer.shop-mall") in checked  # 商城那一層在這裡：讀漏了這一條就空轉


def test_everything_in_the_shop_lines_up_with_the_game_column():
    """招牌那一列、店內分頁、出爐的麻布與卡貼齊欄邊；掌櫃話照手機的 14px、放大的紙照 12px 往裡縮；捲的內容照手機左右各 12px。"""
    half = _column() // 2
    side = f"max(0px, calc(50% - {half}px))"
    rules = _rules(_block(_css(), "FB-225"))
    assert rules[".shop-layer > .shop-bar, .shop-layer > .shop-tabs"] == f"margin-left: {side}; margin-right: {side};"
    line = f"max(14px, calc(50% - {half - 14}px))"
    assert rules[".shop-layer > .shop-line"] == f"margin-left: {line}; margin-right: {line};"
    assert rules[".shop-layer > .reveal-layer"] == f"left: {side}; right: {side};"
    paper = f"max(12px, calc(50% - {half - 12}px))"
    assert rules[".shop-board .board-sheet"] == f"left: {paper}; right: {paper};"
    # 捲的那一層照舊整片寬：滑鼠在欄外也捲得動；兩邊各留一條捲軸寬的溝，內容才正好在中間（不然往左偏半條捲軸）
    assert rules[".shop-layer > .shop-body"] == "scrollbar-gutter: stable both-edges;"
    assert rules[".shop-layer .shop-col"] == f"max-width: {_column() - 24}px; margin: 0 auto;"


def test_the_book_follows_the_same_column():
    """武學譜、鑄譜那本書（店裡的鑄譜鈕也開它）：書頁的底與返回列、封面都在欄裡，欄外是頁面底色；書頁原本就置中。"""
    col, half = _column(), _column() // 2
    rules = _rules(_block(_css(), "FB-225"))
    book = rules[".book-layer"]
    assert "scrollbar-gutter: stable both-edges" in book and book.count(f"50% 0 / min(100%, {col}px) 100% no-repeat") == 2
    assert book.rstrip(";").endswith("var(--paper)") and "var(--bk-paper-2)" in book
    side = f"max(0px, calc(50% - {half}px))"
    assert rules[".book-bar, .book-cover"] == f"margin-left: {side}; margin-right: {side};"


def test_the_desktop_rules_stay_inside_the_shop_and_the_book():
    """這一段只動店面與書：每一條都掛在 .shop-layer／.shop-board／.book- 底下（FB-305 的店面字級用 :where(.shop-layer) 掛、不加權重），
    碰不到江湖頁；.shop-col 與捲軸溝只在桌機區塊裡寫。"""
    css = _css()
    block = _block(css, "FB-225")
    for selector in ",".join(_rules(block)).split(","):
        assert selector.strip().startswith((".shop-layer", ".shop-board", ".book-", ":where(.shop-layer)")), selector
    # 註解裡提到的不算；整頁的捲軸溝（FB-240）是另一段桌機區塊
    rest = re.sub(r"/\*.*?\*/", "", css.replace(block, "").replace(_block(css, "FB-240"), ""), flags=re.S)
    assert ".shop-col" not in rest and "scrollbar-gutter" not in rest


def test_reading_a_biography_in_game_follows_the_column_but_the_public_page_does_not():
    """遊戲裡讀傳那一層（.zhuan-layer）同一套；zhuan.css 也給公開頁用，所以只掛在 .zhuan-layer 底下，公開頁（zhuan_html.py）沒有這個 class。"""
    col, half = _column(), _column() // 2
    rules = _rules(_block(_css("zhuan.css"), "FB-225"))
    layer = rules[".zhuan-layer"]
    assert "scrollbar-gutter: stable both-edges" in layer and f"50% 0 / min(100%, {col}px) 100% no-repeat" in layer
    side = f"max(0px, calc(50% - {half}px))"
    assert rules[".zhuan-layer > .zh-bar, .zhuan-layer > .zh-head"] == f"margin-left: {side}; margin-right: {side};"
    for selector in ",".join(rules).split(","):
        assert selector.strip().startswith(".zhuan-layer"), selector
    assert "zhuan-layer" not in (server.ROOT / "zhuan_html.py").read_text(encoding="utf-8")


def _shop_col(html: str) -> str:
    """.shop-body 裡面第一層一定是 .shop-col（捲的內容都在它裡面）。"""
    found = re.search(r'<div class="shop-body[^"]*"><div class="shop-col">', html)
    assert found, html[:400]
    return html[found.end():]


@needs_node
def test_the_smith_pages_put_their_scrolling_content_in_the_column(content, world):
    """鐵匠鋪四頁：.shop-body 裡面包一層 .shop-col，頁面的東西都在它裡面（一頁一層）。"""
    from test_shop2_web import run

    m = server.main_view(_smith(content, world, name="欄客"))
    pages = run(m, """
      const pages = {};
      for (const tab of ["shelf", "forge", "temper", "rack"]) { H.S.shopTab = tab; H.render(); pages[tab] = T.els.app.innerHTML; }
      return pages;""")
    assert 'class="shop-grid"' in _shop_col(pages["shelf"])
    assert 'class="furnace' in _shop_col(pages["forge"]) and 'class="cells"' in _shop_col(pages["forge"])
    assert 'class="shop-empty"' in _shop_col(pages["temper"]) and 'class="shop-empty"' in _shop_col(pages["rack"])  # 手上沒有兵器、裝備庫空的
    assert all(page.count('class="shop-col"') == 1 for page in pages.values())


@needs_node
def test_the_market_puts_its_stalls_in_the_column(content, world):
    from test_shop2_web import run

    m = server.main_view(_market(content, world, horse=_horse(), name="欄馬"))
    inner = _shop_col(run(m, "H.render(); return T.els.app.innerHTML;"))
    assert 'class="stalls' in inner and 'class="horse-card"' in inner


@needs_node
def test_the_board_puts_its_notes_in_the_column_and_the_paper_outside_the_scroll(content, world):
    """懸賞榜：手上那一排與木板在 .shop-col 裡；放大的紙貼在畫面下緣、是店面那一層自己的（CSS 照欄邊排），畫在捲的那一層後面。"""
    from test_shop2_web import run

    game = _board(content, world, [SCOUT, STRIKE], name="欄榜")
    first = game.state.world.bounties[0].id
    html = run(server.main_view(game), f'H.S.boardZoom = "{first}"; H.render(); return T.els.app.innerHTML;')
    inner = _shop_col(html)
    assert 'class="held-row"' in inner and 'class="board"' in inner
    assert '</div></div>\n      <div class="board-sheet">' in html


# ── FB-240：江湖頁短到沒有整頁捲軸時，進鐵匠鋪、懸賞榜，底下那一頁長出捲軸，店面那一欄往左跳 7.5px ──
# 電腦上整頁的捲軸溝一直留著（html { scrollbar-gutter: stable }）：有沒有捲軸頁面都一樣寬，固定的店面圖層也不跟著窄。
# 實機（1920×1600，江湖頁 1600 高、沒有捲軸）：改前 .shell 640～1280、進鐵匠鋪整頁長到 1665、招牌那一列 632.5～1272.5；
# 改後兩邊都是 632.5～1272.5，出店也是。手機（375）scrollbar-gutter 照舊是 auto。


def test_fb240_the_page_keeps_its_scrollbar_gutter_on_desktop_only():
    css = _css()
    block = _block(css, "FB-240")
    assert DESKTOP == f"@media (min-width: {_column() + 1}px) {{"  # 跟 FB-225 同一個斷點：手機一條都不生效
    assert _rules(block) == {"html": "scrollbar-gutter: stable;"}
    outside = css.replace(block, "")
    assert not re.search(r"(?m)^\s*(html|:root|body)\b[^{]*\{[^}]*scrollbar-gutter", outside)  # 只在桌機那一段寫


# ── 原 test_fb306_shop_column.py（整檔搬進來） ──
# FB-306（FB-225 漏的）：電腦上店面的內容照遊戲那一欄（640）排。web/app.js 每一個店面捲的那一層（.shop-body）裡面一律先包
# 一層 .shop-col（擂台的台下、擂台榜、打到一半原本沒包，「你還沒報名守擂」那一格與挑戰者的卡拉滿整個螢幕）；web/style.css 電腦寬
# 那一段讓擂台的紅布底色也只畫在那一欄、剛打完的收場卡貼齊欄邊。手機上 .shop-col 沒有樣式，這兩樣都不動手機。

WEB = Path(__file__).resolve().parents[2] / "web"


APP = webharness.app_source()


CSS = (WEB / "style.css").read_text(encoding="utf-8")


def _desktop_block() -> str:
    """FB-225 那一段註解之後的第一個 @media (min-width: 641px) 區塊（含大括號）。"""
    start = CSS.index("@media (min-width: 641px) {", CSS.index("/* ── 電腦上的店面與武學譜那本書（FB-225"))
    depth = 0
    for i in range(start, len(CSS)):
        if CSS[i] == "{":
            depth += 1
        elif CSS[i] == "}":
            depth -= 1
            if depth == 0:
                return re.sub(r"/\*.*?\*/", "", CSS[start: i + 1], flags=re.S)
    raise AssertionError("FB-225 那一段沒有收尾")


def test_every_shop_body_wraps_its_content_in_the_column():
    spots = [m.start() for m in re.finditer(r'class="shop-body', APP)]
    assert len(spots) >= 6  # 鐵匠鋪、軍需帳、馬市、懸賞榜、擂台打到一半、擂台台下與擂台榜
    for at in spots:
        tail = APP[at: at + 200]
        after = tail[tail.index('"><') + 2:]  # 開頭那個 tag 收尾之後（懸賞榜的 class 裡有 ${zoom ? " zooming" : ""}）
        assert after.startswith('<div class="shop-col">'), tail


def test_the_arena_paints_its_cloth_in_the_column_on_desktop():
    block = _desktop_block()
    paint = re.search(r"([^{}]+)\{\s*background-color: var\(--paper\); background-size: min\(100%, 640px\) 100%;", block)
    assert paint and ".shop-layer.shop-arena" in [s.strip() for s in paint.group(1).split(",")]


def test_the_arena_result_card_sits_in_the_column_on_desktop():
    assert ".shop-layer.shop-arena .board-sheet { left: max(12px, calc(50% - 308px)); right: max(12px, calc(50% - 308px)); }" in _desktop_block()


def test_the_forge_mouth_and_the_weapon_armor_switch_sit_in_the_column_on_desktop():
    """鐵匠鋪架上頁最上面的爐口與鐵砧（.smith-hero）、兵器／防具切換那一列（.shop-pages）是店面那一層的直接子元素、不在捲的那一層裡：
    內容本來就置中，但那一格原本拉滿整個螢幕；照招牌那一列貼齊欄邊。"""
    side = "max(0px, calc(50% - 320px))"
    assert f".shop-layer > .smith-hero, .shop-layer > .shop-pages {{ margin-left: {side}; margin-right: {side}; }}" in _desktop_block()
