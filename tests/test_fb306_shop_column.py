"""FB-306（FB-225 漏的）：電腦上店面的內容照遊戲那一欄（640）排。web/app.js 每一個店面捲的那一層（.shop-body）裡面一律先包
一層 .shop-col（擂台的台下、擂台榜、打到一半原本沒包，「你還沒報名守擂」那一格與挑戰者的卡拉滿整個螢幕）；web/style.css 電腦寬
那一段讓擂台的紅布底色也只畫在那一欄、剛打完的收場卡貼齊欄邊。手機上 .shop-col 沒有樣式，這兩樣都不動手機。"""
from __future__ import annotations

import re
from pathlib import Path
import webharness

WEB = Path(__file__).resolve().parent.parent / "web"
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
