"""小太極（煉製頁縮起來的開爐鈕）只畫圓：鈕與太極的 svg 都不能有長方形的光暈（Joy 2026-10-18 iPhone 上的方底）。"""
import re
from pathlib import Path
import webharness

CSS = Path(__file__).resolve().parents[1].joinpath("web", "style.css").read_text(encoding="utf-8")
JS = webharness.app_source()


def rules():
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", CSS):
        yield sel.strip(), body


def test_no_bare_forging_rule_glows_the_kiln():
    # 開爐時鈕（.kiln-hub）與大爐子（.w-furnace）都會加 .forging；裸的 .forging 規則會套到它們身上
    assert not any(sel == ".forging" for sel, _ in rules())


def test_kiln_hub_and_taichi_draw_no_box_shadow():
    for sel, body in rules():
        if "kiln-hub" in sel or "kiln-taichi" in sel:
            m = re.search(r"box-shadow:\s*([^;]+)", body)
            assert m is None or m.group(1).strip() == "none", sel


def test_taichi_glow_is_svg_circles():
    assert 'class="kiln-ember"' in JS and 'class="kiln-ring"' in JS
