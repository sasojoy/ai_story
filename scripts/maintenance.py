"""維修頁（Joy 2026-10-18「這可以線上不要 502，顯示伺服器維修中嗎」）。

睡（`tianxia-sleep.ps1`）的時候遊戲伺服器停著，隧道連不到來源，外面看到的是 Cloudflare 的 502。
這支程式在同一個埠（7861）上接管，於是隧道連得到、回的是我們自己的頁面：**來源真的回應了，
Cloudflare 就原樣送出去**（它只有在連不到來源時才塞自己的錯誤頁）。醒的時候先把它收掉再開伺服器
——兩個都想聽 7861，順序弄反伺服器會綁不上。

刻意極小：只用標準庫、一個行程、不碰資料庫也不碰任何遊戲狀態（睡的意義就是把機器讓出來）。
狀態碼是 **503 ＋ Retry-After**（不是 200）：這才是「暫時不能服務」的意思，瀏覽器與爬蟲都不會把它當成正式內容。
頁面自己每 `RETRY` 秒探一次 `/api/main`，伺服器回來了就自動跳回遊戲，玩家不必自己重整。

用法：
    .venv/Scripts/python.exe -u scripts/maintenance.py                 # 聽 127.0.0.1:7861
    .venv/Scripts/python.exe -u scripts/maintenance.py --port 7861 --note "換電腦，約一小時"
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import console  # noqa: E402

RETRY = 30  # 頁面每幾秒探一次伺服器回來了沒（也寫進 Retry-After）
TITLE = "天下大勢"
HEAD = "江湖暫歇"
LINES = (
    "主機正在維修，稍後再來。",
    "賽季時鐘已經暫停：停機這一段不算進賽季，季末跟著往後延，進度一分都不會少。",
    "伺服器一回來，這一頁會自己跳回江湖。",
)

PAGE = """<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}・維修中</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ margin:0; min-height:100vh; display:grid; place-items:center;
         background:#efe7d7; color:#2b2b2b; font-family:"Noto Serif TC",serif; padding:24px; }}
  .box {{ max-width:30rem; text-align:center; }}
  .seal {{ width:3.5rem; height:3.5rem; margin:0 auto 1.2rem; border:2px solid #9a3b2f; color:#9a3b2f;
           border-radius:4px; display:grid; place-items:center; font-size:1.6rem; letter-spacing:.1em; }}
  h1 {{ font-size:1.6rem; margin:0 0 1rem; letter-spacing:.3em; }}
  p {{ margin:.6rem 0; line-height:1.9; font-size:1rem; }}
  .note {{ margin-top:1.4rem; padding-top:1rem; border-top:1px solid #d6c9b0; }}
  .dim {{ color:#6b6257; font-size:.85rem; }}
  @media (prefers-color-scheme: dark) {{
    body {{ background:#1c1a17; color:#e6ddcc; }} .note {{ border-top-color:#3a352e; }} .dim {{ color:#9a9183; }}
  }}
</style></head>
<body><div class="box">
  <div class="seal">歇</div>
  <h1>{head}</h1>
  {body}
  {note}
  <p class="dim">（每 {retry} 秒自己探一次）</p>
</div>
<script>
  setInterval(function () {{
    fetch("/api/main", {{ method: "POST", headers: {{ "Content-Type": "application/json" }}, body: "{{}}" }})
      .then(function (r) {{ if (r.status !== 503) location.reload(); }})
      .catch(function () {{}});
  }}, {retry} * 1000);
</script>
</body></html>
"""


def page(note: str = "") -> bytes:
    body = "\n  ".join(f"<p>{html.escape(line)}</p>" for line in LINES)
    extra = f'<p class="note">{html.escape(note)}</p>' if note else ""
    return PAGE.format(title=html.escape(TITLE), head=html.escape(HEAD), body=body, note=extra, retry=RETRY).encode("utf-8")


def handler(note: str) -> type[BaseHTTPRequestHandler]:
    body = page(note)
    api = json.dumps({"detail": "維修中", "maintenance": True}, ensure_ascii=False).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        server_version = "tianxia-maintenance"

        def _send(self) -> None:
            """每一條路徑都回 503：/api/ 給 JSON（網頁的輪詢在解析 JSON），其餘給那一頁。"""
            data, kind = (api, "application/json; charset=utf-8") if self.path.startswith("/api/") else (body, "text/html; charset=utf-8")
            self.send_response(503)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Retry-After", str(RETRY))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        do_GET = do_POST = do_HEAD = do_PUT = do_DELETE = _send

        def log_message(self, *args: object) -> None:
            pass  # 維修中不需要存取紀錄

    return Handler


class Server(ThreadingHTTPServer):
    """埠被佔著就要綁不上、而且說清楚。

    `HTTPServer` 預設 `allow_reuse_address = 1`（SO_REUSEADDR），而 **Windows 的 SO_REUSEADDR 允許綁上
    一個已經有人在聽的埠**，兩個行程會分著收請求——維修頁要是這樣綁上 7861，玩家的請求就一半進遊戲、
    一半看到「維修中」（2026-10-18 實機踩到：監控頁跟維修頁同時聽著 7899，回的是維修頁）。
    維修頁寧可起不來，也不能從活著的伺服器手上偷走流量。
    """

    allow_reuse_address = False


def main(argv: list[str] | None = None) -> None:
    console.use_utf8()
    parser = argparse.ArgumentParser(description="維修頁（停機時替伺服器接管那個埠，外面看到的不是 502）")
    parser.add_argument("--port", type=int, default=7861, help="聽哪個埠（預設 7861，跟伺服器同一個）")
    parser.add_argument("--note", default="", help="多寫一句（例：換電腦，約一小時）")
    args = parser.parse_args(argv)
    try:
        httpd = Server(("127.0.0.1", args.port), handler(args.note))
    except OSError as exc:
        sys.exit(f"綁不上 127.0.0.1:{args.port}（{exc}）——那個埠還有人在聽。"
                 f"伺服器還開著就不該開維修頁：先把伺服器停掉，再開這一支。")
    print(f"維修頁：http://127.0.0.1:{args.port}　回 503＋Retry-After {RETRY}（Ctrl+C 結束）", flush=True)
    print("隧道照舊通，外面看到的是這一頁；醒的時候要先把這支停掉，再開伺服器（兩個都要聽同一個埠）。", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
