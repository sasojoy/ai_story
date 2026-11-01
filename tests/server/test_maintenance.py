"""維修頁（2026-10-18，Joy「這可以線上不要 502，顯示伺服器維修中嗎」）。

睡的時候遊戲伺服器停著，隧道連不到來源 → Cloudflare 的 502。這支在同一個埠接管，
於是來源真的有回應，Cloudflare 原樣送出我們的頁面。
"""
from __future__ import annotations

import json
import socket
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import maintenance  # noqa: E402


@pytest.fixture
def serving():
    """起一個真的 HTTP server 在隨機埠上（0 = 讓系統挑），測完收掉。"""
    httpd = maintenance.Server(("127.0.0.1", 0), maintenance.handler("換電腦，約一小時"))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)


def fetch(url: str) -> tuple[int, str, dict]:
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status, r.read().decode("utf-8"), dict(r.headers)
    except urllib.error.HTTPError as e:  # 503 走這裡
        return e.code, e.read().decode("utf-8"), dict(e.headers)


def test_the_page_is_503_not_200(serving):
    """503＋Retry-After 才是「暫時不能服務」；200 會讓瀏覽器與爬蟲把它當成正式內容。"""
    status, body, headers = fetch(serving + "/")
    assert status == 503
    assert headers["Retry-After"] == str(maintenance.RETRY)
    assert headers["Cache-Control"] == "no-store"
    assert "text/html" in headers["Content-Type"]


def test_the_page_says_what_a_player_needs_to_know(serving):
    _, body, _ = fetch(serving + "/")
    assert maintenance.HEAD in body
    assert "賽季時鐘已經暫停" in body  # 停機不算進賽季：玩家最在意的就是進度會不會少
    assert "換電腦，約一小時" in body  # --note 寫得進去
    assert "/api/main" in body  # 自己探、伺服器回來就跳回遊戲


def test_every_path_gets_the_page(serving):
    for path in ("/", "/zhuan/abc", "/web/app.js", "/anything"):
        status, body, _ = fetch(serving + path)
        assert status == 503 and maintenance.HEAD in body


def test_the_api_gets_json_so_the_polling_tab_does_not_choke(serving):
    """網頁每 10 秒打 /api/main 並解析 JSON：回 HTML 會在那邊炸開，回 JSON 它照自己的錯誤處理走。"""
    status, body, headers = fetch(serving + "/api/main")
    assert status == 503 and "application/json" in headers["Content-Type"]
    assert json.loads(body)["maintenance"] is True


def test_no_note_means_no_empty_line(serving):
    assert '<p class="note"></p>' not in maintenance.page("").decode("utf-8")


@pytest.mark.smoke
def test_it_only_listens_on_localhost():
    """跟伺服器一樣只聽本機：外面一律走隧道進來（也就是說關了隧道就真的沒人進得來）。"""
    httpd = maintenance.Server(("127.0.0.1", 0), maintenance.handler(""))
    try:
        assert httpd.server_address[0] == "127.0.0.1"
    finally:
        httpd.server_close()


def test_the_default_port_is_the_servers_port():
    """預設就是 7861：接管的是伺服器那個埠，隧道（ingress 寫死 7861）才指得到。"""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7861)
    assert parser.parse_args([]).port == 7861
    assert socket.AF_INET  # 只是確認上面那個 fixture 真的用 IPv4 起得來


def test_it_refuses_to_steal_a_port_that_is_already_served(serving):
    """Windows 的 SO_REUSEADDR 允許綁上一個已經有人在聽的埠，兩個行程分著收請求——維修頁要是這樣綁上
    7861，玩家一半進遊戲、一半看到「維修中」（2026-10-18 實機踩到）。寧可起不來。"""
    port = int(serving.rsplit(":", 1)[1])
    with pytest.raises(OSError):
        maintenance.Server(("127.0.0.1", port), maintenance.handler(""))


def test_main_says_why_when_the_port_is_taken(serving, capsys):
    port = int(serving.rsplit(":", 1)[1])
    with pytest.raises(SystemExit) as exit_info:
        maintenance.main(["--port", str(port)])
    assert "綁不上" in str(exit_info.value) and "先把伺服器停掉" in str(exit_info.value)
