"""cultivation 這一包的測試，從 tests/web/test_jianghu_page_web.py 拆來（全部拆包第 61 批，只搬位置、不改斷言）。"""
from __future__ import annotations
import pytest
import webharness
from test_prologue_web import run as run_prologue_web
from jianghu_kit import _script, glowing  # noqa: F401

pytestmark = pytest.mark.whole_content


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_the_fold_without_a_glowing_duty_button_is_not_opened_by_the_step(glowing):
    """框上帶 glow、但這一處沒有發光的那顆鈕（沒有 act:duty）：沒有東西要露出來，摺疊不自動打開，也不記成自動打開過。"""
    other = {"id": "learn:cuquan", "label": "學粗淺拳腳（學費 0 兩）", "enabled": True, "wait": "", "confirm": ""}  # 摺疊裡留一顆別的鈕，摺疊還畫得出來
    m = {**glowing, "options": [o for o in glowing["options"] if o["id"] != "act:duty"] + [other]}
    out = run_prologue_web(m, _script("H.renderPage(); return { open: fold(), auto: Object.keys(H.S.hereAuto) };"))
    assert out == {"open": None, "auto": []}  # 沒有要露出來的：照平常畫此地可為那一排（介面重整）
