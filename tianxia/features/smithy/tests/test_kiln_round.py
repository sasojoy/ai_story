"""小太極（煉製頁縮起來的開爐鈕）只畫圓：鈕與太極的 svg 都不能有長方形的光暈（Joy 2026-10-18 iPhone 上的方底）。"""
# 畫法在 web/craft.js（全部拆包第 64 批從 app.js 切出來）、樣式在 web/craft.css（第 67 批從 style.css 切出來）；寫在這裡 test_for 改包檔時才挑得到
import re
from pathlib import Path
import webharness
import pytest

pytestmark = pytest.mark.whole_content

# 全部的樣式一起掃：規則切到哪一支都要看得到（第 67 批切檔之後只讀 style.css，迴圈就走不到爐的規則了）
WEB = Path(__file__).resolve().parents[4] / "web"
CSS = re.sub(r"/\*.*?\*/", "", "\n".join(p.read_text(encoding="utf-8") for p in sorted(WEB.glob("*.css"))), flags=re.S)
JS = webharness.app_source()


def rules():
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", CSS):
        yield sel.strip(), body


def test_no_bare_forging_rule_glows_the_kiln():
    # 開爐時鈕（.kiln-hub）與大爐子（.w-furnace）都會加 .forging；裸的 .forging 規則會套到它們身上
    assert not any(sel == ".forging" for sel, _ in rules())


def test_kiln_hub_and_taichi_draw_no_box_shadow():
    seen = set()
    for sel, body in rules():
        if "kiln-hub" in sel or "kiln-taichi" in sel:
            seen.add(sel)
            m = re.search(r"box-shadow:\s*([^;]+)", body)
            assert m is None or m.group(1).strip() == "none", sel
    assert ".kiln-taichi" in seen and ".kiln-hub.forging .kiln-taichi .w-spin" in seen  # 走得到真的規則，不是空轉


def test_taichi_glow_is_svg_circles():
    assert 'class="kiln-ember"' in JS and 'class="kiln-ring"' in JS
