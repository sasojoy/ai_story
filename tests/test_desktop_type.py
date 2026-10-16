"""電腦寬的店面字級（FB-305，企劃者 10/16 從對照圖選甲）：web/style.css 店面那一段（三間店、擂台、素材頁與軍需帳）每一條寫了字級的
規則，在 @media (min-width: 641px) 裡都有一條同一個選擇器、字級 ×1.3（四捨五入到 0.5px）的；手機（沒有 media 的那一條）的值不動。
讀的是 CSS 原文：webharness 沒有排版，量不到 computed style（實機比對在 docs/superpowers/feedback/ 的 FB-305 那一筆）。"""
from __future__ import annotations

import re
from pathlib import Path

CSS = (Path(__file__).resolve().parent.parent / "web" / "style.css").read_text(encoding="utf-8")
SHOP_START = "/* ── 店面（店面獨立介面設計第五節）"
SHOP_END = "/* ── 電腦上的店面與武學譜那本書（FB-225"
K = 1.3


def _strip(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _blocks(css: str) -> list[tuple[str, str]]:
    """最外層的（選擇器或 @規則, 內容）。"""
    out, depth, start, head, body = [], 0, 0, "", 0
    for i, ch in enumerate(css):
        if ch == "{":
            if depth == 0:
                head, body = css[start:i].strip(), i + 1
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                out.append((head, css[body:i]))
                start = i + 1
    return out


def _sizes(body: str) -> dict[str, str]:
    """一條規則裡的 font-size 與 font（有 px 的那幾個）。"""
    found = {}
    for decl in body.split(";"):
        if ":" in decl:
            prop, val = (x.strip() for x in decl.split(":", 1))
            if prop in ("font-size", "font") and "px" in val:
                found[prop] = val
    return found


def _scaled(val: str) -> str:
    return re.sub(r"(\d+(?:\.\d+)?)px", lambda m: f"{round(float(m.group(1)) * K * 2) / 2:g}px", val)


def _shop_base() -> dict[str, dict[str, str]]:
    section = _strip(CSS[CSS.index(SHOP_START): CSS.index(SHOP_END)])
    return {sel: _sizes(body) for sel, body in _blocks(section) if not sel.startswith("@") and _sizes(body)}


def _desktop() -> dict[str, dict[str, str]]:
    rules: dict[str, dict[str, str]] = {}
    for head, body in _blocks(_strip(CSS)):
        if head.replace(" ", "") == "@media(min-width:641px)":
            for sel, inner in _blocks(body):
                rules.setdefault(sel, {}).update(_sizes(inner))
    return rules


def test_every_shop_size_has_a_desktop_rule_one_point_three_times_bigger():
    base, desk = _shop_base(), _desktop()
    assert len(base) > 100  # 三間店、擂台、素材頁與軍需帳都在這一段
    missing = {sel: (sizes, desk.get(sel)) for sel, sizes in base.items()
               if {prop: _scaled(val) for prop, val in sizes.items()} != {prop: desk.get(sel, {}).get(prop) for prop in sizes}}
    assert not missing, missing


def test_the_notice_tag_title_and_due_line_on_desktop():
    desk = _desktop()
    assert desk[".shop-board .note .tag, .shop-board .paper .tag"]["font-size"] == "12.5px"
    assert desk[".shop-board .note b"]["font"].startswith("600 17px")
    assert desk[".shop-board .note small"]["font-size"] == "12.5px"
    assert desk[".shop-board .board-sheet .paper"]["font-size"] == "16px"
    assert desk[".shop-line"]["font"].startswith("17px/")


def test_the_phone_sizes_are_untouched():
    base = _shop_base()
    assert base[".shop-board .note .tag, .shop-board .paper .tag"]["font-size"] == "9.5px"
    assert base[".shop-board .note b"]["font"].startswith("600 13px")
    assert base[".shop-board .note small"]["font-size"] == "9.5px"
    assert base[".shop-line"]["font"].startswith("13px/")


def test_text_that_inherits_its_size_grows_too_but_only_inside_the_shop():
    desk = _desktop()
    assert desk[".shop-layer"]["font-size"] == "19.5px"  # 吃 body 15px 的
    assert desk[".shop-layer .btn"]["font-size"] == "19.5px" and desk[".shop-layer .btn.small"]["font-size"] == "18px"
    assert ".shell" not in desk and "body" not in desk  # 江湖頁、修練頁不動
