"""FB-461（第 32 項 QA，2026-10-20）：有三條分支的地方（北邙山、嵩山深處、綠林山寨、燕山腳），分支兩欄排，「深入」旁邊空一格。
單數條時最後一條佔整列。餵真的引擎資料給 app.js（test_gather_branches_web 的假瀏覽器）；CSS 在 node 裡排不了版，讀 style.css 的
那一條規則。沒有 node 就略過。"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from test_gather_branches_web import _bar, _main

import webharness

pytestmark = [pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過"), pytest.mark.slow]

CSS = (Path(__file__).resolve().parents[1] / "web" / "style.css").read_text(encoding="utf-8")


def _branch_classes(bar: str) -> dict[str, list[str]]:
    found = re.findall(r'<button class="btn gather-branch([^"]*)" data-act="choose" data-id="explore:gather:(\w+)"', bar)
    return {branch: extra.split() for extra, branch in found}


def test_odd_branches_last_one_takes_the_row():
    classes = _branch_classes(_bar(_main(), gatherOpen=True))  # 嵩山深處：挖礦、狩獵、深入
    assert set(classes) == {"mine", "hunt", "deep", "say"}
    assert "wide" in classes["deep"]
    assert "wide" not in classes["mine"] and "wide" not in classes["hunt"] and "wide" not in classes["say"]


def test_odd_branches_while_saying_too():
    classes = _branch_classes(_bar(_main(), gatherOpen=True, gatherSaying=True))  # 「自己說…」換成輸入框，深入照樣佔整列
    assert "say" not in classes and "wide" in classes["deep"]


def test_odd_branches_without_the_say_button():
    m = _main()
    m["options"] = [o for o in m["options"] if o["id"] != "explore:gather:say"]  # Config.gather_branches.say_enabled 關著
    classes = _branch_classes(_bar(m, gatherOpen=True))
    assert set(classes) == {"mine", "hunt", "deep"} and "wide" in classes["deep"]


def test_even_branches_stay_two_by_two():
    classes = _branch_classes(_bar(_main("songshan_foot"), gatherOpen=True))  # 嵩山腳兩條
    assert len([k for k in classes if k != "say"]) == 2
    assert not any("wide" in c for c in classes.values())


def test_the_wide_branch_spans_both_columns():
    rule = re.search(r"([^{}]*\.gather-branch\.wide[^{}]*)\{([^}]*)\}", CSS)
    assert rule, "style.css 沒有 .gather-branch.wide 的規則"
    assert re.search(r"grid-column:\s*1\s*/\s*-1", rule.group(2))
