"""主控台輸出的編碼（2026-10-18）：cp950 編不出來的一個字，不能把 server.py／run_bots.py 弄死。

實際踩到的：`TIANXIA_PROFILE` 沒帶到時，兩個程式啟動時要印 `calendar.PROFILE_MISMATCH`
（開頭是 `⚠`），cp950 編不出 `⚠` → `UnicodeEncodeError` → 啟動即崩。
該提醒人「設定帶錯了」的那一行，自己變成了當機的原因。
"""
from __future__ import annotations

import io
import sys

import console
import run_bots
import server
from tianxia import calendar


def _cp950_stream() -> io.TextIOWrapper:
    """Windows 主控台與重導向的 log 預設長這樣：底下是 bytes，上面包一層 cp950。"""
    return io.TextIOWrapper(io.BytesIO(), encoding="cp950", errors="strict")


def test_cp950_really_cannot_write_the_warning_sign():
    """先確認這個坑是真的：沒換編碼的話，印那一行就是丟例外。"""
    stream = _cp950_stream()
    assert calendar.PROFILE_MISMATCH.startswith("⚠")
    try:
        stream.write(calendar.PROFILE_MISMATCH)
        stream.flush()
    except UnicodeEncodeError:
        return
    raise AssertionError("cp950 竟然寫得出 ⚠，這個測試要重寫")


def test_use_utf8_lets_the_profile_warning_through(monkeypatch):
    stream = _cp950_stream()
    monkeypatch.setattr(sys, "stdout", stream)
    console.use_utf8()
    print(calendar.PROFILE_MISMATCH, flush=True)  # 換過編碼之後，同一行印得出來
    written = sys.stdout.buffer.getvalue().decode("utf-8")
    assert calendar.PROFILE_MISMATCH in written


def test_use_utf8_replaces_what_it_still_cannot_write(monkeypatch):
    """errors="replace"：真的還有編不出來的字，寫成 ? 就好，不要再因為一個字停機。"""
    stream = io.TextIOWrapper(io.BytesIO(), encoding="ascii", errors="strict")
    monkeypatch.setattr(sys, "stdout", stream)
    console.use_utf8()
    print("⚠ 設定對不上", flush=True)
    assert sys.stdout.buffer.getvalue()  # 有寫出東西、而且沒有丟例外


def test_use_utf8_leaves_a_stream_it_cannot_change_alone(monkeypatch):
    """測試或別人把 stdout 換成自己的物件（沒有 reconfigure 也沒有 buffer）時，原樣留著、不要出錯。"""
    class Plain:
        def __init__(self) -> None:
            self.text = ""

        def write(self, s: str) -> int:
            self.text += s
            return len(s)

        def flush(self) -> None:
            pass

    plain = Plain()
    monkeypatch.setattr(sys, "stdout", plain)
    console.use_utf8()
    assert sys.stdout is plain


def test_both_programs_switch_the_encoding_before_they_print_anything():
    """兩個入口的 main() 都要叫它——不然這個修法只存在於 console.py 裡。"""
    assert "use_utf8" in server.main.__code__.co_names
    assert "use_utf8" in run_bots.main.__code__.co_names
