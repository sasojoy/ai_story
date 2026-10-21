"""首頁近期改版（Joy 2026-10-21「首頁應該有地方顯示近期的更版資訊」）：伺服器讀 content/patch_notes.json，江湖頁那排小標多一顆「改版」，
有沒看過的一次就亮點，點開是最新一次的新功能與調整，更早的收成一行。前端把 app.js 的 patchPeek 與 peekHtml 切出來交給 node 跑。"""
from __future__ import annotations

import json

import pytest

import server
import webharness

DRIVER = r"""
const S = { peekOpen: input.open ? { id: "patch", week: 1 } : null, patchSeen: input.seen };
const H = new Function("S", "pro", [
  ...["esc", "PATCH_SEEN_KEY"].map(konst),
  ...["patchSeen", "patchLines", "patchPeek", "peekHtml"].map(fn),
  "return { patchPeek, peekHtml };",
].join("\n"))(S, () => input.prologue || null);
const part = H.patchPeek(input.m);
finish({ part, html: part ? H.peekHtml([part], 1) : "" });
"""

NOTES = [
    {"date": "10/21", "new": ["萬寶閣：用元寶買東西。"], "tweak": ["懸賞榜拿掉求藝。"]},
    {"date": "10/14", "new": ["擂台"], "tweak": []},
]


def test_real_file_reads_and_is_short():
    notes = server.patch_notes()
    assert notes and len(notes) <= server.PATCH_SHOW
    for note in notes:
        assert note["date"] and (note["new"] or note["tweak"])
        assert all(len(line) <= 60 for line in note["new"] + note["tweak"])  # 一項一行，不寫細節


def test_bad_entries_are_skipped(tmp_path):
    path = tmp_path / "p.json"
    path.write_text(json.dumps({"notes": [{"date": ""}, "x", {"date": "1/1", "new": ["a", 3, " "]}, {"date": "1/2"}]}), encoding="utf-8")
    assert server.patch_notes(path) == [{"date": "1/1", "new": ["a"], "tweak": []}]
    path.write_text("{", encoding="utf-8")
    assert server.patch_notes(path) == []
    assert server.patch_notes(tmp_path / "missing.json") == []


needs_node = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


def run(m, *, open_=False, seen="", prologue=None):
    return webharness.run(DRIVER, {"m": m, "open": open_, "seen": seen, "prologue": prologue})


@needs_node
def test_chip_dot_until_latest_seen():
    out = run({"patch": NOTES})
    assert "改版" in out["html"] and "peek-dot" in out["html"]
    assert "peek-dot" not in run({"patch": NOTES}, seen="10/21")["html"]
    assert "peek-dot" in run({"patch": NOTES}, seen="10/14")["html"]  # 出了新的一次又亮


@needs_node
def test_panel_lists_latest_and_folds_older():
    html = run({"patch": NOTES}, open_=True, seen="10/21")["html"]
    assert "天下大勢　改版資訊 10/21" in html and "<h4>新功能</h4>" in html and "<li>懸賞榜拿掉求藝。</li>" in html
    assert '<details class="patch-old"><summary>改版資訊 10/14</summary>' in html


@needs_node
def test_nothing_without_notes_or_in_prologue():
    assert run({"patch": []})["part"] is None
    assert run({"patch": NOTES}, prologue={"step": 1})["part"] is None
