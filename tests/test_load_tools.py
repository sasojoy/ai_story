"""壓測的共用工具與假的模型（線上架構設計 9.1）。"""
import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import fake_ollama  # noqa: E402
import load_common  # noqa: E402


def test_percentiles_handle_empty_one_and_many():
    """樣本空的、只有一筆：不丟例外（Review Focus 5）。"""
    assert load_common.percentiles([]) == {"count": 0, "p50": None, "p95": None, "p99": None, "max": None}
    one = load_common.percentiles([0.2])
    assert one["count"] == 1 and one["p50"] == one["p95"] == one["max"] == 0.2
    many = load_common.percentiles([i / 100 for i in range(1, 101)])
    assert many["p50"] == 0.5 and many["p95"] == 0.95 and many["p99"] == 0.99 and many["max"] == 1.0


def test_percentiles_are_nearest_rank_on_small_samples():
    """樣本少時真的是第 ceil(q × 筆數) 小那一筆（Python 的 round 是四捨六入五成雙，會把 5 筆的中位數取成第 2 小）。"""
    five = load_common.percentiles([5.0, 1.0, 4.0, 2.0, 3.0])  # 沒排序也行
    assert five["p50"] == 3.0 and five["p95"] == 5.0 and five["max"] == 5.0
    thirty = load_common.percentiles([float(i) for i in range(1, 31)])
    assert thirty["p95"] == 29.0 and thirty["p50"] == 15.0 and thirty["p99"] == 30.0


def test_summarize_reads_like_a_line():
    line = load_common.summarize("/api/main", [0.1, 0.2, 0.3], errors=2)
    assert line.startswith("/api/main") and "3 次" in line and "錯誤 2" in line and "p95" in line


def test_summarize_with_no_samples_does_not_raise():
    """一次都沒成功（全部是錯誤）也要印得出一行，不能丟例外（Review Focus 5）。"""
    assert load_common.summarize("login", [], errors=4) == "login：0 次，錯誤 4"


def test_fake_ollama_waits_then_fails():
    server = fake_ollama.serve(0, delay=(0.2, 0.2))
    try:
        port = server.server_address[1]
        started = time.monotonic()
        r = httpx.post(f"http://127.0.0.1:{port}/api/chat", json={"model": "x", "messages": []}, timeout=5)
        assert r.status_code == 503 and time.monotonic() - started >= 0.2
        assert httpx.get(f"http://127.0.0.1:{port}/api/tags", timeout=5).status_code == 200  # 健檢照常回
    finally:
        server.shutdown()
        server.server_close()


def test_fake_ollama_only_listens_on_this_computer():
    """只綁 127.0.0.1，不對區網開放。"""
    server = fake_ollama.serve(0, delay=(0.0, 0.0))
    try:
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.shutdown()
        server.server_close()


def test_fake_ollama_does_not_share_a_port_with_another_program():
    """埠已經有人在用就要失敗：Windows 上 SO_REUSEADDR 會讓兩個程式同時綁同一個埠、悄悄搶別人的流量。"""
    first = fake_ollama.serve(0, delay=(0.0, 0.0))
    try:
        with pytest.raises(OSError):
            fake_ollama.serve(first.server_address[1], delay=(0.0, 0.0))
    finally:
        first.shutdown()
        first.server_close()


def test_serve_itself_refuses_reserved_ports(monkeypatch):
    """守衛放在 serve 裡，不只在命令列：別的程式（Task 3 的測試、之後的腳本）呼叫 serve 也開不到那些埠。
    伺服器類別換成一碰就失敗的：守衛壞掉時測試直接失敗，不會真的綁到那些埠。"""
    def must_not_bind(*args, **kwargs):
        raise AssertionError("不該開伺服器")

    monkeypatch.setattr(fake_ollama, "_Server", must_not_bind)
    for port in (11434, 11999, 7861):
        with pytest.raises(ValueError):
            fake_ollama.serve(port, delay=(0.0, 0.0))


def test_fake_ollama_refuses_ports_that_belong_to_someone_else(monkeypatch):
    """命令列不能開在真的 Ollama（11434）、別人用的 11999 或試玩伺服器（7861）的埠上。
    serve 換成一碰就失敗的：守衛壞掉時測試直接失敗，不會真的綁到那些埠、也不會卡住。"""
    def must_not_bind(*args, **kwargs):
        raise AssertionError("不該開伺服器")

    monkeypatch.setattr(fake_ollama, "serve", must_not_bind)
    for port in (11434, 11999, 7861):
        with pytest.raises(SystemExit):
            fake_ollama.main(["--port", str(port)])
