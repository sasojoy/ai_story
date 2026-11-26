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
        assert note["date"] and (note["new"] or note["tweak"] or note["fix"])
        assert all(len(line) <= 60 for line in note["new"] + note["tweak"] + note["fix"])  # 一項一行，不寫細節


def test_bad_entries_are_skipped(tmp_path):
    path = tmp_path / "p.json"
    path.write_text(json.dumps({"notes": [{"date": ""}, "x", {"date": "1/1", "new": ["a", 3, " "]}, {"date": "1/2"}]}), encoding="utf-8")
    assert server.patch_notes(path) == [{"date": "1/1", "new": ["a"], "tweak": [], "fix": []}]
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


POP_DRIVER = r"""
const store = new Map(Object.entries(input.stored || {}));
const localStorage = { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, String(v)) };
const S = { patchNotes: input.notes };
const H = new Function("S", "localStorage", "pro", "loadPatchNotes", [
  ...["esc", "PATCH_SEEN", "PATCH_OK", "patchKey"].map(konst),
  ...["patchLines", "patchUnseen", "patchPopHtml", "patchPopClose"].map(fn),
  "const nxSeen = () => true, nxLinkHtml = () => '';",  // 江湖新事那一張排在改版資訊前面（PR #247）：這裡測的是改版資訊，當作已經看過
  "return { patchPopHtml, patchPopClose, patchKey };",
].join("\n"))(S, localStorage, () => input.pro || null, () => {});
const first = H.patchPopHtml(input.m || {});
H.patchPopClose();
finish({ first, again: H.patchPopHtml(input.m || {}), key: H.patchKey(input.notes[0]) });
"""


@needs_node
def test_a_new_version_pops_once_after_login():
    """Joy 2026-11-07「以前改版資訊是在登入那邊 但是現在幾乎不會到那頁 因為會記錄session」：進遊戲有沒看過的新版就跳一張
    【天下大勢　改版資訊 M/D】，按「知道了」就不再跳；從沒看過的只給最新那一次，看過舊的、中間漏了幾次的漏掉的各收成一行；
    序章裡、特殊事件的跳顯框還沒看完先不跳。"""
    out = webharness.run(POP_DRIVER, {"notes": NOTES})
    assert 'class="sheet patch-pop"' in out["first"] and "【天下大勢　改版資訊 10/21】" in out["first"] and "萬寶閣" in out["first"]
    assert "10/14" not in out["first"] and ">知道了</button>" in out["first"] and out["again"] == ""
    newer = [{"date": "10/28", "fix": ["修好一件事。"]}, *NOTES]
    seen_old = webharness.run(POP_DRIVER, {"notes": newer, "stored": {"tianxia.patchSeen": out["key"].replace("10/21", "10/14").replace("1,1,0", "1,0,0")}})
    assert "【天下大勢　改版資訊 10/28】" in seen_old["first"] and "<summary>改版資訊 10/21</summary>" in seen_old["first"] and "10/14" not in seen_old["first"]
    assert webharness.run(POP_DRIVER, {"notes": NOTES, "stored": {"tianxia.patchSeen": out["key"]}})["first"] == ""
    assert webharness.run(POP_DRIVER, {"notes": NOTES, "pro": {"step": 1}})["first"] == ""
    assert webharness.run(POP_DRIVER, {"notes": NOTES, "m": {"story_cards": [{"kind": "end"}]}})["first"] == ""
