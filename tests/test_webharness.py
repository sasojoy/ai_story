"""tests/webharness.py 自己的檢查（第 5 區評審之後補強的幾件）：常駐的 node 與各開一個 node（TIANXIA_WEB_HARNESS=process）
對這些情況的結果要一樣。沒有 node 就略過。"""
from __future__ import annotations

import json
import os
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
    """丟出一個連 String() 都轉不了的東西：這個請求馬上以 1 結束，不是等到逾時（以前常駐的 node 會卡住 60 秒）。
    而且是請求自己的失敗（describe 寫得出它是什麼），不是掉進 harness 出錯的那條路（「webharness: …」）：
    describe 只剩 String() 的話會走到那條路，這裡就抓得到。"""
    started = time.monotonic()
    done = webharness.node("throw Object.create(null);", timeout=20)
    assert done.returncode == 1 and done.stderr
    assert "webharness:" not in done.stderr
    assert time.monotonic() - started < 15
    assert webharness.node("process.stdout.write('next');").stdout == "next"  # 下一個請求照常


# 一個什麼都不讓碰的例外：讀它的任何屬性都丟錯，String() 與 Object.prototype.toString 都轉不了，describe 也寫不出來
UNDESCRIBABLE = "new Proxy({}, { get() { throw new Error('碰不得'); } })"


def test_a_throw_even_describe_cannot_handle_fails_at_once_and_clears_its_timers(mode):
    """丟出的東西連 describe 都寫不出來：harness 自己出錯，這個請求馬上失敗（runOne 外層的 try/catch），而且它排下的計時器
    一起清掉——不然那個每 20 毫秒丟一次沒人接的拒絕的計時器會一直跑，算到下一個請求頭上，下一個就無緣無故失敗。"""
    started = time.monotonic()
    done = webharness.node(
        "setInterval(() => { Promise.reject(new Error('上一個請求留下的計時器')); }, 20);"
        f"throw {UNDESCRIBABLE};",
        timeout=20,
    )
    assert done.returncode != 0
    assert time.monotonic() - started < 15
    after = webharness.node("setTimeout(() => process.stdout.write('clean'), 200);", timeout=20)
    assert (after.returncode, after.stdout) == (0, "clean"), after.stderr


def test_a_throw_whose_description_throws_itself_still_fails_at_once(mode):
    """更糟的：寫它的時候丟出來的還是它自己（讀任何屬性都丟出自己的 Proxy），describe 怎樣都寫不出來。harness 出錯的回覆
    （broken）自己接住、寫成「寫不出來的例外」，這個請求一樣馬上失敗（以前常駐的 node 會停在「忙」，之後每個請求都等到逾時）。"""
    started = time.monotonic()
    done = webharness.node("const bad = new Proxy({}, { get() { throw bad; } }); throw bad;", timeout=20)
    assert done.returncode != 0
    assert time.monotonic() - started < 15
    assert webharness.node("process.stdout.write('next');").stdout == "next"


def test_a_bad_exit_code_at_the_end_fails_at_once(mode):
    """結束時才出錯（exitCode 轉不成數字）：等結束的那段非同步程式出錯也馬上失敗（它的 .catch），不是卡到逾時。
    各開一個 node 時，node 在設定 exitCode 的當下就不收，一樣以非 0 結束。"""
    started = time.monotonic()
    done = webharness.node("process.exitCode = { valueOf() { throw new Error('不是數字'); } };", timeout=20)
    assert done.returncode != 0
    assert time.monotonic() - started < 15
    assert webharness.node("process.stdout.write('next');").stdout == "next"


def test_a_line_the_resident_node_cannot_read_gets_an_error_reply():
    """常駐的 node 收到一行讀不懂的東西（不是 JSON）：回一個失敗的回覆（pump 的 try/catch），接下來的請求照常；
    不然 pump 會停在「忙」，之後每個請求都等到逾時。只有常駐的 node 有這條路。"""
    if os.environ.get(webharness.MODE_ENV) == "process":
        pytest.skip("只有常駐的 node 有 pump")
    assert webharness.node("process.stdout.write('up');").stdout == "up"  # 確定常駐的 node 開著
    resident = webharness._RESIDENT
    resident.proc.stdin.write(b"this is not json\n")
    resident.proc.stdin.flush()
    reply = json.loads(resident.replies.get(timeout=20).decode("utf-8"))
    assert reply["code"] == 1 and reply["stderr"].startswith("webharness: ")
    assert webharness.node("process.stdout.write('next');").stdout == "next"


def test_exit_without_a_code_ends_with_the_exit_code_already_set(mode):
    """先設 process.exitCode、再 process.exit() 不帶數字：以那個 exitCode 結束（node 是這樣），exit 之後的程式不跑。"""
    done = webharness.node("process.exitCode = 3; process.stdout.write('a'); process.exit(); process.stdout.write('b');")
    assert (done.returncode, done.stdout) == (3, "a")


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
