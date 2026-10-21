"""登入頁的近期改版（Joy 2026-10-21「登入首頁加改版資訊」）：伺服器讀 content/patch_notes.json、/api/patch_notes 不用登入；
登入表單底下一張卡，最新一次的新功能與調整一項一行，更早的收成一行。前端把 app.js 的 gatePatchHtml 切出來交給 node 跑。"""
from __future__ import annotations

import json

import pytest

import server
import webharness

DRIVER = r"""
const H = new Function([...["esc"].map(konst), ...["patchLines", "gatePatchHtml"].map(fn), "return { gatePatchHtml };"].join("\n"))();
finish({ html: H.gatePatchHtml(input.notes) });
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


def test_endpoint_needs_no_login():
    from fastapi.testclient import TestClient

    r = TestClient(server.app).get("/api/patch_notes")
    assert r.status_code == 200 and r.json()["notes"] == server.patch_notes()


@needs_node
def test_card_lists_latest_and_folds_older():
    html = webharness.run(DRIVER, {"notes": NOTES})["html"]
    assert "改版資訊 10/21" in html and "<h4>新功能</h4>" in html and "<li>懸賞榜拿掉求藝。</li>" in html
    assert '<details class="patch-old"><summary>改版資訊 10/14</summary>' in html
    assert "<h4>調整</h4>" not in html.split("<details")[1]  # 10/14 那次沒有調整，不畫空的一段


@needs_node
def test_nothing_without_notes():
    assert webharness.run(DRIVER, {"notes": []})["html"] == ""
