"""FB-460（第 32 項 QA，2026-10-20）：找素材「自己說」輸入框的提示字在 320 寬被切到「沿著獸徑」，也沒寫 20 字內。
這一格縮在分支那一排裡，比事件的隨口應對、對話的自己說窄。餵真的引擎資料給 app.js（test_gather_branches_web 的假瀏覽器）；
CSS 在 node 裡排不了版，寬度照字數粗估（實機量的在回饋單裡）。沒有 node 就略過。"""
from __future__ import annotations

import re

import pytest
from test_gather_branches_web import _bar, _main

import webharness

pytestmark = [pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過"), pytest.mark.slow]

# QA 在 320 寬量到的：輸入框扣掉內距剩 152 像素，提示字 16px（一個全形字 16 像素）
NARROW_BOX = 152


def _placeholder(bar: str) -> str:
    found = re.search(r'id="gather-say-form"><input [^>]*placeholder="([^"]*)"', bar)
    assert found, "找不到找素材「自己說」的輸入框"
    return found.group(1)


def _width(text: str, em: float = 16.0) -> float:
    """粗估一行字的寬：全形字一個 em，半形（數字、英文）0.6 em——偏寬估，寧可多算。"""
    return sum(em if ord(ch) > 0xFF else em * 0.6 for ch in text)


def test_hint_says_twenty_characters_like_the_other_boxes():
    hint = _placeholder(_bar(_main(), gatherOpen=True, gatherSaying=True))
    assert hint.endswith("（20字內）")  # 同事件隨口應對「…（20字內）」、對話「想對他說的話（20字內）」


def test_hint_fits_the_box_at_320():
    hint = _placeholder(_bar(_main(), gatherOpen=True, gatherSaying=True))
    assert _width(hint) <= NARROW_BOX, (hint, _width(hint))  # 修前「怎麼找？例：沿著獸徑找落羽」208 像素
