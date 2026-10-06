"""tests/webharness.py 自己的檢查（第 5 區評審之後補強的幾件）：常駐的 node 與各開一個 node（TIANXIA_WEB_HARNESS=process）
對這些情況的結果要一樣。沒有 node 就略過。"""
from __future__ import annotations

import time

import pytest

import webharness

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node")
MODES = ["resident", "process"]


@pytest.fixture(params=MODES)
def mode(request, monkeypatch):
    if request.param == "process":
        monkeypatch.setenv(webharness.MODE_ENV, "process")
    else:
        monkeypatch.delenv(webharness.MODE_ENV, raising=False)
    return request.param


def test_a_throw_the_harness_cannot_print_fails_at_once(mode):
    """丟出一個連 String() 都轉不了的東西：這個請求馬上以 1 結束，不是等到逾時（以前常駐的 node 會卡住 60 秒）。"""
    started = time.monotonic()
    done = webharness.node("throw Object.create(null);", timeout=20)
    assert done.returncode == 1 and done.stderr
    assert time.monotonic() - started < 15
    assert webharness.node("process.stdout.write('next');").stdout == "next"  # 下一個請求照常


def test_the_harness_names_are_free_for_a_driver(mode):
    """harness 自己的函式（runOne、pump）不是請求的全域：驅動程式用 const、let、class 宣告同名的東西不會撞名。"""
    done = webharness.node(
        "const pump = 1; let runOne = 2; class active {}; const describe = 3;"
        "process.stdout.write([typeof pump, typeof runOne, typeof active, typeof describe].join(','));",
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout == "number,number,function,number"


def test_clear_timeout_takes_the_numeric_id(mode):
    """clearTimeout(+t)：node 認計時器的數字 id，清掉之後請求馬上結束，不是等那個計時器（以前常駐的 node 會等到逾時）。"""
    started = time.monotonic()
    done = webharness.node(
        "const t = setTimeout(() => process.stdout.write('late'), 30000); clearTimeout(+t);"
        "const u = setInterval(() => process.stdout.write('tick'), 30000); clearInterval(+u);"
        "process.stdout.write('ok');",
        timeout=20,
    )
    assert (done.returncode, done.stdout) == (0, "ok")
    assert time.monotonic() - started < 15


def test_a_nonzero_exit_code_fails_the_request_and_stays_with_it(mode):
    """process.exitCode 設成非 0：這個請求以那個數字結束（node 也是），而且不會留給下一個請求。"""
    done = webharness.node("process.exitCode = 3; process.stdout.write('set');")
    assert (done.returncode, done.stdout) == (3, "set")
    after = webharness.node("process.stdout.write(String(process.exitCode));")
    assert (after.returncode, after.stdout) == (0, "undefined")
