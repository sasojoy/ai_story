"""FB-470（第 36 項「武學隨地理環境」QA，2026-10-19）：輿圖抽屜「地利」那一句（26 字）在 375 寬斷成「…施展不／開。」、
360 與桌面斷成「…施展／不開。」——照 FB-433 掮客那一句（sayHtml）切在「：」「，」後面包成不折行的小段，字一個不改。"""
from __future__ import annotations

import html as htmllib
import re

import pytest
import webharness
from conftest import real_content

from tianxia import terrain

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")

DRIVER = r"""
const H = new Function([konst("esc"), konst("LEDGER_NB"), konst("SAY_AFTER"), fn("sayHtml"), fn("terrainArtsRow"),
  "return { terrainArtsRow };"].join("\n"))();
finish(input.lines.map((t) => H.terrainArtsRow({ terrain_arts: t })));
"""

HEAD = '<div class="m-sec"><h4>地利</h4>'
SPAN = re.compile(r'<span class="nb">([^<]*)</span>')


@pytest.mark.slow
def test_the_terrain_line_breaks_only_after_its_commas():
    c = real_content()
    lines = sorted({terrain.place_line(c, loc) for loc in c.locations} - {""})
    assert len(lines) == 4  # 火、水、山、風
    rows = webharness.run(DRIVER, {"lines": lines})
    for line, row in zip(lines, rows):
        assert row.startswith(HEAD) and row.endswith("</div>")
        body = row[len(HEAD):-len("</div>")]
        assert htmllib.unescape(re.sub(r"<[^>]+>", "", body)) == line  # 字一個不改
        assert SPAN.sub("", body) == ""  # 每一個字都在不折行的小段裡
        chunks = SPAN.findall(body)
        assert "".join(chunks) == line and len(chunks) == 3
        assert [chunk[-1] for chunk in chunks] == ["：", "，", "。"]  # 只在「：」「，」後面換行
        assert chunks[-1].endswith("的施展不開。")  # 「施展不開」整個在同一段


def test_no_terrain_draws_nothing():
    assert webharness.run(DRIVER, {"lines": [""]}) == [""]
