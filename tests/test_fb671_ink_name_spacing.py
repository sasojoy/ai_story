"""FB-671：360 寬「出陣・守」「出陣・攻」名字 54 px、格子內寬 52.8 px，差 1 px 折成兩行，整排行動列多 21.5 px。

字距 0.5 px 是每個字後面都加（四個字 2 px）：54 = 4 × 13 + 4 × 0.5。帶「・」的名字（`inkName` 包成 `<span class="nb">`）
把字距收到 0 就是 52 px，放得進 360 寬的 52.8 px；沒有「・」的名字（探索、練功、交友、移動、出陣）字距照舊，畫面一個像素都不變。
CSS 排不出版面，幾何（360／375／320 寬的行數與列高）在瀏覽器裡量；這裡鎖住那條規則。
"""

from __future__ import annotations

import re
from pathlib import Path

CSS = (Path(__file__).resolve().parent.parent / "web" / "style.css").read_text(encoding="utf-8")


def _rule(selector: str) -> str:
    match = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert match, f"style.css 找不到 {selector} 這條規則"
    return match.group(1)


def test_names_with_a_middle_dot_drop_the_letter_spacing():
    assert re.search(r"letter-spacing:\s*0\s*;", _rule(".act-ink b .nb"))


def test_plain_names_keep_their_letter_spacing():
    base = _rule(".act-ink b")
    assert "letter-spacing: 0.5px" in base and "font-size: 13px" in base


def test_the_sums_fit_a_360_wide_cell():
    # 360 寬：格子 58.8 − 內距 4 − 邊框 2 = 52.8；四個字 13 px 一字不加字距 = 52。
    inner = 58.8 - 2 * 2 - 2 * 1
    assert 4 * 13 <= inner < 4 * (13 + 0.5)
