"""scripts/nightly.py：每日整套的摘要（開發規範手冊 4.4：新紅、舊紅、轉綠，跟最近一次跑完的比）。
都是純函式：用 tmp_path 造 junit 與前幾天的 json，不跑 pytest、不碰 git、不碰 .local/。"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("nightly", ROOT / "scripts" / "nightly.py")
nightly = importlib.util.module_from_spec(_spec)
sys.modules["nightly"] = nightly
_spec.loader.exec_module(nightly)

_BODY = {"pass": "", "fail": '<failure message="x"/>', "error": '<error message="x"/>', "skip": "<skipped/>"}


def _junit(path: Path, cases: list[tuple[str, str, str]]) -> None:
    """cases：（classname, name, pass／fail／error／skip）；照 pytest --junitxml 的樣子寫。"""
    kinds = [how for *_, how in cases]
    rows = "".join(f'<testcase classname="{c}" name="{n}" time="0.1">{_BODY[how]}</testcase>' for c, n, how in cases)
    path.write_text(f'<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest" tests="{len(cases)}" '
                    f'failures="{kinds.count("fail")}" errors="{kinds.count("error")}" skipped="{kinds.count("skip")}" '
                    f'time="12.5">{rows}</testsuite></testsuites>', encoding="utf-8")


@pytest.fixture
def place(tmp_path, monkeypatch):
    """（out：.local/nightly 那個資料夾, checkout：測試檔在的地方）；develop 的提交不問 git。"""
    out, checkout = tmp_path / "nightly", tmp_path / "checkout"
    out.mkdir()
    for f in ("tests/core/test_a.py", "tests/core/test_b.py"):
        (checkout / f).parent.mkdir(parents=True, exist_ok=True)
        (checkout / f).write_text("", encoding="utf-8")
    monkeypatch.setattr(nightly, "commits_between", lambda repo, previous, sha: ("a..b", "git log a..b", []))
    return out, checkout


def _summarize(out, checkout, date, sha="1234567890ab", exit=1, cases=None):
    if cases is not None:
        _junit(out / f"{date}.xml", cases)
    extra = {"started": f"{date} 03:30 ", "exit": exit, "minutes": 14.9, "workers": 4, "notes": []}
    return nightly.summarize(out, out, checkout, date, sha, extra)


def test_junit_counts_and_test_ids(place):
    """junit 的 classname 換回 pytest 的 id（檔、類別、函式）；import 失敗的那一個也算紅。"""
    out, checkout = place
    _junit(out / "x.xml", [
        ("tests.core.test_a", "test_one", "pass"),
        ("tests.core.test_a.TestY", "test_two", "fail"),
        ("tests.core.test_b", "test_three[1-2]", "error"),
        ("tests.core.test_b", "test_four", "skip"),
        ("", "tests.test_broken", "error"),
    ])
    r = nightly.parse_junit(out / "x.xml", checkout)
    assert (r["tests"], r["passed"], r["failures"], r["errors"], r["skipped"]) == (5, 1, 1, 2, 1)
    assert r["failed"] == ["::tests.test_broken", "tests/core/test_a.py::TestY::test_two",
                           "tests/core/test_b.py::test_three[1-2]"]
    assert nightly.parse_junit(out / "missing.xml", checkout) is None


def test_compare_splits_new_old_and_fixed():
    new, old, fixed = nightly.compare(["a", "b"], ["b", "c"])
    assert (new, old, fixed) == (["c"], ["b"], ["a"])
    assert nightly.compare(None, ["x"]) == (["x"], [], [])


def test_the_first_run_lists_every_red_as_new(place):
    out, checkout = place
    text = _summarize(out, checkout, "2026-10-31", cases=[("tests.core.test_a", "test_one", "fail"),
                                                          ("tests.core.test_b", "test_two", "pass")])
    assert "沒有前一天可比" in text and "新紅（前一次綠、這一次紅）：1 條" in text
    assert json.loads((out / "2026-10-31.json").read_text(encoding="utf-8"))["failed"] == ["tests/core/test_a.py::test_one"]


def test_a_same_day_rerun_compares_with_the_day_before(place):
    """同一天重跑（修好紅的再跑一次）：跟前一天比，不是跟今天早上那一次比。"""
    out, checkout = place
    _summarize(out, checkout, "2026-10-30", cases=[("tests.core.test_a", "test_one", "fail")])
    _summarize(out, checkout, "2026-10-31", cases=[("tests.core.test_a", "test_one", "fail"),
                                                  ("tests.core.test_b", "test_two", "fail")])
    text = _summarize(out, checkout, "2026-10-31", cases=[("tests.core.test_a", "test_one", "pass"),
                                                         ("tests.core.test_b", "test_two", "fail")])
    assert "前一次：2026-10-30" in text
    assert "新紅（前一次綠、這一次紅）：1 條\n  tests/core/test_b.py::test_two" in text
    assert "舊紅（前一次就紅）：0 條" in text
    assert "轉綠（前一次紅、這一次不紅）：1 條\n  tests/core/test_a.py::test_one" in text


def test_an_unfinished_run_keeps_no_json_and_the_next_compares_with_the_last_finished(place):
    out, checkout = place
    _summarize(out, checkout, "2026-10-29", cases=[("tests.core.test_a", "test_one", "fail")])
    text = _summarize(out, checkout, "2026-10-30", exit=3)  # 沒有 junit
    assert "沒跑完" in text and not (out / "2026-10-30.json").exists()
    text = _summarize(out, checkout, "2026-10-31", cases=[("tests.core.test_a", "test_one", "fail")])
    assert "前一次：2026-10-29" in text and "舊紅（前一次就紅）：1 條" in text


def test_a_rerun_does_not_pick_up_the_morning_junit(place, monkeypatch, tmp_path):
    """同一天重跑時 pytest 沒寫出新的 junit（結束碼 3、4，或被排程的時限砍掉）：不能把早上那一份當成這一次的結果、
    掛在新的 SHA 上存成下一次的比較基準。開跑前先刪掉同一天的 junit。"""
    out, checkout = place
    _junit(out / "2026-10-31.xml", [("tests.core.test_a", "test_one", "pass")])  # 早上那一次，全綠
    monkeypatch.setattr(nightly.tempfile, "gettempdir", lambda: str(tmp_path / "temp"))
    monkeypatch.setattr(nightly.subprocess, "call", lambda *a, **k: 3)  # 內部錯誤：沒寫 junit
    code, _ = nightly.run_suite(checkout, out, "2026-10-31", 4)
    assert code == 3 and not (out / "2026-10-31.xml").exists()
    text = _summarize(out, checkout, "2026-10-31", sha="455664ac0000", exit=code)
    assert "沒跑完" in text and not (out / "2026-10-31.json").exists()


@pytest.mark.parametrize("code", [2, 3, 4, 5])
def test_only_exit_codes_0_and_1_count_as_a_finished_run(place, code):
    """結束碼 2（中斷）時 pytest 會寫出只跑了一半的 junit；3、4、5 也不是跑完整套。只有 0（全綠）、1（有紅）算跑完。"""
    out, checkout = place
    text = _summarize(out, checkout, "2026-10-31", exit=code, cases=[("tests.core.test_a", "test_one", "pass")])
    assert "沒跑完" in text and f"結束碼 {code}" in text and "passed" not in text
    assert not (out / "2026-10-31.json").exists()


def test_an_old_red_says_since_when(place):
    """手冊 4.4「新紅三天沒修，PM revert」：舊紅後面寫從哪一天起紅、第幾天，PM 不必翻交接算；轉綠再紅從頭算。
    json 記每一條紅的起始日（red_since），沒有這一欄的舊 json 當成從那一天起。"""
    out, checkout = place
    red = [("tests.core.test_a", "test_one", "fail")]
    _summarize(out, checkout, "2026-10-29", cases=red)
    _summarize(out, checkout, "2026-10-30", cases=red)
    text = _summarize(out, checkout, "2026-10-31", cases=red)
    assert "  tests/core/test_a.py::test_one（從 2026-10-29 起紅，第 3 天）" in text
    kept = json.loads((out / "2026-10-31.json").read_text(encoding="utf-8"))
    assert kept["red_since"] == {"tests/core/test_a.py::test_one": "2026-10-29"}
    _summarize(out, checkout, "2026-11-01", cases=[("tests.core.test_a", "test_one", "pass")])
    _summarize(out, checkout, "2026-11-02", cases=red)
    text = _summarize(out, checkout, "2026-11-03", cases=red)
    assert "（從 2026-11-02 起紅，第 2 天）" in text
    legacy = json.loads((out / "2026-11-03.json").read_text(encoding="utf-8"))
    del legacy["red_since"]  # 這一批之前寫的 json 沒有這一欄
    (out / "2026-11-03.json").write_text(json.dumps(legacy), encoding="utf-8")
    assert "（從 2026-11-03 起紅，第 2 天）" in _summarize(out, checkout, "2026-11-04", cases=red)


def test_the_more_commits_line_is_a_command_that_runs():
    """提交太多只列前 MAX_COMMITS 筆，「還有幾筆」後面給的是真的跑得了的 git log（沒有前一次時以前印成一句說明）。"""
    summary = {"date": "2026-10-31", "sha": "455664ac00", "exit": 0, "workers": 4, "notes": [],
               "result": {"passed": 1, "failures": 0, "errors": 0, "skipped": 0}}
    commits = [f"c{i}" for i in range(nightly.MAX_COMMITS + 14)]
    text = nightly.render(summary, None, [], [], [], "沒有前一次可比，列一天之內的",
                          'git log --since="1 day ago" 455664ac', commits)
    assert '還有 14 筆（git log --since="1 day ago" 455664ac）' in text


def test_latest_and_the_ps1_carry_a_bom(place):
    """Windows PowerShell 5.1 沒有 BOM 會照 ANSI 讀：nightly.ps1 的中文全變亂碼、Get-Content latest.txt 讀錯。"""
    out, checkout = place
    _summarize(out, checkout, "2026-10-31", cases=[("tests.core.test_a", "test_one", "pass")])
    assert (out / "latest.txt").read_bytes().startswith(b"\xef\xbb\xbf")
    assert (ROOT / "scripts" / "nightly.ps1").read_bytes().startswith(b"\xef\xbb\xbf")
