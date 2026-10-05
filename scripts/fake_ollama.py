"""假的模型伺服器（線上架構設計 9.1：LLM 用模擬的，延遲 5～20 秒）。每一個 /api/chat 等一段隨機的時間再回 503，
所以伺服器每個叫模型的地方都會等滿、再走退路——這是「模型很慢而且常失敗」的最壞情況。/api/tags 照常回 200（健檢用）。

只聽 127.0.0.1。預設埠 11990（這台電腦上 11990～11998 留給壓測的假模型；11434 是真的 Ollama、11999 是別人的程式，
命令列會拒絕開在那些埠上）。

執行：.venv/Scripts/python.exe scripts/fake_ollama.py --port 11990 --min 5 --max 20
壓測的設定檔（content/profiles/loadtest.json）把 ollama_url 指到這裡。"""
from __future__ import annotations

import argparse
import json
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_PORT = 11990
# 不能開在這些埠上：真的 Ollama、別人的程式、試玩伺服器
RESERVED_PORTS = {11434: "真的 Ollama", 11999: "別人的程式", 7861: "試玩伺服器"}


class _Server(ThreadingHTTPServer):
    # HTTPServer 預設 allow_reuse_address = 1；Windows 上那會讓兩個程式同時綁同一個埠、悄悄搶別人的流量。
    # 關掉：埠已經有人在用就直接 OSError。
    allow_reuse_address = False
    daemon_threads = True


def serve(port: int, delay: tuple[float, float], status: int = 503) -> ThreadingHTTPServer:
    """開在 127.0.0.1:port 的背景執行緒（port 給 0 就由系統挑一個，看 server_address[1]）；shutdown() 關。"""
    low, high = delay

    class Handler(BaseHTTPRequestHandler):
        def _reply(self, code: int, body: dict) -> None:
            data = json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802
            self._reply(200, {"models": [{"name": "fake"}]})

        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            time.sleep(random.uniform(low, high))
            self._reply(status, {"error": "fake ollama is slow on purpose"})

        def log_message(self, *args):  # 不洗版
            pass

    server = _Server(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="假的模型伺服器：延遲之後回 503")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--min", type=float, default=5.0)
    parser.add_argument("--max", type=float, default=20.0)
    args = parser.parse_args(argv)
    if args.port in RESERVED_PORTS:
        parser.error(f"埠 {args.port} 是{RESERVED_PORTS[args.port]}在用的，不能開在這裡")
    server = serve(args.port, (args.min, args.max))
    print(f"假的模型：http://127.0.0.1:{server.server_address[1]}（每次等 {args.min:g}～{args.max:g} 秒再回 503）", flush=True)
    try:
        while True:  # 一次睡短一點：Windows 上整個卡在沒有逾時的 wait() 時，Ctrl+C 要等到它醒來才收得到
            time.sleep(0.5)
    except KeyboardInterrupt:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
