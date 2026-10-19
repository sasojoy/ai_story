"""試玩監控頁（2026-10-14，企劃者「做一個網頁讓我實時查看」）：在線人數、賽季、行程、模型、最近的錯誤。

**跟遊戲伺服器完全分開**：自己一個行程、自己一個埠，資料庫一律唯讀（`mode=ro`），只用標準庫，
所以它掛了不影響遊戲，遊戲忙也不影響它。想看就開，不看就關。

**只聽 127.0.0.1，靠密碼擋人**：這一頁把真人與假人分開數，而「誰是假人」任何玩家都不能看到
（伺服器假人設計第五節）。2026-10-14 起它也走 Cloudflare Tunnel 對外（`monitor.tianxiadashi.com`，
企劃者「我在外面根本看不到」），所以每個請求都要 HTTP Basic 的密碼（見 `password()`）——隧道來的連線
在這裡看起來跟本機一模一樣（cloudflared 跑在同一台），擋不了來源，只能擋密碼。

「在線」的定義跟遊戲一致：`characters` 的 `json_extract(data,'$.last_real')` 在 `presence_seconds`
（600 秒）之內同步過，就是「此地還有誰」會列出來的那些人（`tianxia/social.py::here`）。

用法：
    .venv/Scripts/python.exe scripts/monitor.py                      # http://127.0.0.1:7899
                                                                     # 對外 https://monitor.tianxiadashi.com
    .venv/Scripts/python.exe scripts/monitor.py --port 7900 --db saves/tianxia.db
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import hmac
import html
import json
import os
import re
import secrets
import sqlite3
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRESENCE = 600  # 這一頁的「在線」＝還有人正在按按鈕。**刻意不等於 Config.presence_seconds**：
# 那個是「此地還有／截殺得到」的窗口，2026-10-19 照 Joy 的要求拉到 24 小時（殺得到是重點，城鎮是避風港），
# 拿它當「在線」的話這一頁永遠寫著幾十人在線，看不出此刻到底有沒有人在玩。
FACTIONS = {"guan": "官軍", "huang": "黃巾", "haoqiang": "地方豪強", None: "散人（未投靠）"}


def _reach() -> float:
    """遊戲裡「此地還有／互動得到」的窗口（Config.presence_seconds）。刻意用標準庫直接讀那個檔、
    不 import tianxia：這一頁要能在遊戲掛了的時候照樣開得起來。讀不到就當 24 小時。"""
    try:
        with open(ROOT / "content" / "config.json", encoding="utf-8") as f:
            return float(json.load(f).get("presence_seconds", 86400))
    except Exception:  # noqa: BLE001
        return 86400.0


def _windows() -> tuple[tuple[float, str], ...]:
    """四個窗口：1 分鐘、5 分鐘、「在線」（10 分鐘），最後一個是遊戲裡還互動得到（＝截殺得到）的那一段。"""
    reach = _reach()
    label = f"互動得到（{reach / 3600:g} 小時內）" if reach >= 3600 else f"互動得到（{reach / 60:g} 分鐘內）"
    return ((60, "1 分鐘內"), (300, "5 分鐘內"), (PRESENCE, "在線（10 分鐘內）"), (reach, label))


WINDOWS = _windows()
ONLINE_ROW = 2  # WINDOWS 裡哪一個是「在線」，給大字用


def snapshot(db: Path) -> dict:
    """唯讀抓一份。哪一塊讀不到就記進 problems，不讓整頁壞掉。"""
    out: dict = {"now": time.time(), "problems": [], "windows": [], "recent": [], "season": {}, "battle": None}
    try:
        conn = sqlite3.connect("file:" + db.as_posix() + "?mode=ro", uri=True)
    except sqlite3.Error as exc:
        out["problems"].append("開不了資料庫：" + str(exc))
        return out
    try:
        counts = "SELECT is_bot, COUNT(*) FROM characters WHERE json_extract(data,'$.last_real') >= ? GROUP BY is_bot"
        for seconds, label in WINDOWS:
            got = dict(conn.execute(counts, (out["now"] - seconds,)).fetchall())
            out["windows"].append((label, got.get(0, 0), got.get(1, 0)))
        total = dict(conn.execute("SELECT is_bot, COUNT(*) FROM characters GROUP BY is_bot").fetchall())
        out["total"] = (total.get(0, 0), total.get(1, 0))
        out["accounts"] = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
        out["recent"] = conn.execute(
            "SELECT name, faction, json_extract(data,'$.last_real'), json_extract(data,'$.player.location') "
            "FROM characters WHERE is_bot = 0 AND json_extract(data,'$.last_real') IS NOT NULL "
            "ORDER BY json_extract(data,'$.last_real') DESC LIMIT 12"
        ).fetchall()
        world = json.loads(conn.execute("SELECT data FROM world").fetchone()[0])
        out["season"] = {
            "number": world.get("season_number"), "opened": world.get("season_opened"),
            "paused_at": world.get("paused_at"), "tianji": world.get("tianji"),
        }
        row = conn.execute("SELECT data FROM seasons WHERE number = ?", (world.get("season_number"),)).fetchone()
        if row:
            season = json.loads(row[0])
            out["season"]["time"] = season.get("time", 0)
            out["season"]["ended"] = season.get("ended")
            out["season"]["trends"] = season.get("trends", {})
        out["battle"] = conn.execute(
            "SELECT battle_def, phase FROM battles WHERE id = (SELECT active_battle_id FROM world)"
        ).fetchone()
        # 陣營：照角色自己的 faction 數（真人／假人分開、活躍的另外數），再對一份投靠名冊
        # （faction_rolls，照季分）——陣營規模、人數緩衝與晉升席次看的是名冊，兩邊對不上就是有人拜門派進去的
        by_faction = "SELECT faction, COUNT(*) FROM characters WHERE is_bot = ? {extra} GROUP BY faction"
        out["factions"] = {
            "real": dict(conn.execute(by_faction.format(extra=""), (0,)).fetchall()),
            "bot": dict(conn.execute(by_faction.format(extra=""), (1,)).fetchall()),
            "active": dict(conn.execute(
                by_faction.format(extra="AND json_extract(data,'$.last_real') >= ?"),
                (0, out["now"] - 1800),
            ).fetchall()),
        }
        out["roster"] = dict(conn.execute(
            "SELECT faction, COUNT(*) FROM faction_rolls WHERE season = ? GROUP BY faction",
            (out["season"]["number"] if out.get("season") else world.get("season_number"),),
        ).fetchall())
    except (sqlite3.Error, json.JSONDecodeError, TypeError) as exc:
        out["problems"].append("查詢出錯：" + type(exc).__name__ + " " + str(exc))
    finally:
        conn.close()
    return out


def processes() -> list[tuple[str, bool | None]]:
    """三個該在跑的行程。問不到就回 None（顯示成 ?），不猜。"""
    want = (("伺服器", r"server\.py"), ("假人", r"run_bots\.py"), ("隧道", r"tunnel run"))
    try:
        got = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process | ForEach-Object { $_.CommandLine }"],
            capture_output=True, text=True, timeout=25, encoding="utf-8", errors="replace")
        lines = got.stdout or ""
    except Exception:
        return [(name, None) for name, _ in want]
    return [(name, bool(re.search(pattern, lines))) for name, pattern in want]


def ollama_line() -> str:
    exe = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
    try:
        got = subprocess.run([str(exe), "ps"], capture_output=True, text=True, timeout=25,
                             encoding="utf-8", errors="replace")
        rows = [r.strip() for r in (got.stdout or "").splitlines() if r.strip()]
        return rows[1] if len(rows) > 1 else "沒有模型載入（下一次呼叫要冷啟動）"
    except Exception as exc:
        return "問不到：" + type(exc).__name__


def tail(path: Path, lines: int) -> list[str]:
    """log 是 cp950 寫的（Python 導向檔案時用主控台編碼），所以先試 cp950 再試 utf-8。"""
    try:
        raw = path.read_bytes()
    except OSError:
        return []
    for encoding in ("cp950", "utf-8"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")
    return [line for line in text.splitlines() if line.strip()][-lines:]


STYLE = """
body{font:14px/1.6 -apple-system,"Microsoft JhengHei",sans-serif;background:#14110e;color:#e8e2d8;margin:0;padding:18px}
h1{font-size:16px;margin:0 0 4px}
.t{color:#8a8a8a;font-size:12px}
.box{background:#1d1a16;border:1px solid #2e2a24;border-radius:8px;padding:12px 14px;margin:12px 0}
.box h2{font-size:13px;margin:0 0 8px;color:#c8a96a;font-weight:600}
table{border-collapse:collapse;width:100%}
td,th{padding:3px 8px;text-align:left}
th{color:#8a8a8a;font-weight:400;font-size:12px}
tr+tr td{border-top:1px solid #2a2622}
.n{text-align:right;font-variant-numeric:tabular-nums}
.dim{color:#8a8a8a}
.big{font-size:30px;color:#e8d5a8;font-variant-numeric:tabular-nums;line-height:1.2}
.err{color:#e08a7a;font-size:12px;white-space:pre-wrap;word-break:break-all}
.ok{color:#7aa06a;font-size:12px}
"""


def page(db: Path) -> str:
    data = snapshot(db)
    now = data["now"]
    e = html.escape

    windows = "".join(
        "<tr><td>" + e(label) + "</td><td class=n>" + str(real) + "</td>"
        "<td class='n dim'>" + str(bot) + "</td></tr>"
        for label, real, bot in data["windows"]
    )
    online = data["windows"][ONLINE_ROW][1] if len(data["windows"]) > ONLINE_ROW else "?"
    real_total, bot_total = data.get("total", ("?", "?"))

    season = data["season"]
    if season.get("ended"):
        phase = "休季"
    elif season.get("paused_at"):
        phase = "時鐘停了"
    elif season.get("opened"):
        phase = "進行中"
    else:
        phase = "籌備中"
    hours = season.get("time", 0) / 3600
    trends = "　".join(k + " " + str(v) for k, v in (season.get("trends") or {}).items())
    battle = data["battle"]
    battle_text = (e(battle[0]) + "・" + e(battle[1])) if battle else "沒有"

    procs = "　".join(
        e(name) + ("✔" if ok else ("✘" if ok is False else "?"))
        for name, ok in processes()
    )
    recent = "".join(
        "<tr><td>" + e(name) + "</td><td>" + e(faction or "散人") + "</td><td>" + e(loc or "") + "</td>"
        "<td class=n>" + str(int(now - last)) + " 秒前</td></tr>"
        for name, faction, last, loc in data["recent"]
    )
    f = data.get("factions") or {}
    roster = data.get("roster") or {}
    sides = [k for k in (list(f.get("real", {})) + list(f.get("bot", {})) + list(roster)) if k]
    order = [s for s in ("guan", "huang", "haoqiang") if s in sides] + sorted(set(sides) - {"guan", "huang", "haoqiang"})
    active_total = sum(f.get("active", {}).values()) or 0
    faction_rows = "".join(
        "<tr><td>" + e(FACTIONS.get(side, side)) + "</td>"
        "<td class=n>" + str(f.get("active", {}).get(side, 0))
        + (" <span class=dim>" + format(f["active"][side] / active_total * 100, ".0f") + "%</span>"
           if active_total and f.get("active", {}).get(side) else "") + "</td>"
        "<td class=n>" + str(f.get("real", {}).get(side, 0)) + "</td>"
        "<td class='n dim'>" + str(f.get("bot", {}).get(side, 0)) + "</td>"
        "<td class=n>" + str(roster.get(side, 0)) + "</td></tr>"
        for side in order + [None]
    )
    errors = tail(ROOT / "server_err.log", 6) + tail(ROOT / "bots_err.log", 3)
    error_html = ("".join("<div class=err>" + e(line) + "</div>" for line in errors)
                  or "<div class=ok>兩個 error log 都是空的</div>")
    problems = "".join("<div class=err>" + e(p) + "</div>" for p in data["problems"])

    return (
        "<!doctype html><meta charset=utf-8><meta http-equiv=refresh content=10>"
        "<title>天下大勢 監控</title><style>" + STYLE + "</style>"
        "<h1>天下大勢 監控</h1>"
        "<div class=t>" + dt.datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S")
        + "　每 10 秒自動更新　資料庫唯讀　只聽本機</div>"
        + problems
        + "<div class=box><h2>在線</h2><div class=big>" + str(online)
        + " <span class=t>真人在線</span></div>"
        "<table><tr><th>門檻</th><th class=n>真人</th><th class=n>假人</th></tr>" + windows
        + "<tr><td>角色總數</td><td class=n>" + str(real_total) + "</td><td class='n dim'>" + str(bot_total)
        + "</td></tr><tr><td>帳號總數</td><td class=n>" + str(data.get("accounts", "?")) + "</td><td></td></tr>"
        "</table></div>"
        "<div class=box><h2>賽季</h2>第 " + str(season.get("number", "?")) + " 季・" + phase
        + "　季內時間 " + format(hours, ".1f") + " 小時　天機 " + str(season.get("tianji", "?"))
        + "<div class=t style='margin-top:6px'>" + e(trends) + "</div>"
        "<div class=t>決戰：" + battle_text + "</div></div>"
        "<div class=box><h2>行程與模型</h2>" + procs
        + "<div class=t style='margin-top:6px'>" + e(ollama_line()) + "</div></div>"
        "<div class=box><h2>陣營</h2><table>"
        "<tr><th>陣營</th><th class=n>活躍真人</th><th class=n>真人角色</th><th class=n>假人</th>"
        "<th class=n>投靠名冊</th></tr>" + faction_rows + "</table>"
        "<div class=t style='margin-top:6px'>活躍＝30 分鐘內同步過。"
        "名冊（faction_rolls）才是陣營規模、人數緩衝與晉升席次看的數；跟「真人角色」對不上是正常的"
        "（名冊含假人，而拜入陣營門派的人兩邊算法也不同）。</div></div>"
        "<div class=box><h2>最近同步的真人</h2><table>"
        "<tr><th>名號</th><th>陣營</th><th>所在</th><th class=n>上次同步</th></tr>" + recent + "</table></div>"
        "<div class=box><h2>最近的錯誤</h2>" + error_html + "</div>"
    )


PASSWORD_FILE = ROOT / ".local" / "monitor.txt"


def password() -> str:
    """監控頁的密碼：環境變數 `TIANXIA_MONITOR_PASSWORD` 優先，其次 `.local/monitor.txt`
    （第一行不是 `#` 開頭的）；兩個都沒有就當場產一個寫進 `.local/monitor.txt`
    （`.local/` 在 `.gitignore` 裡，不會進版控）、在啟動訊息印出來。

    **一定要有密碼**：這一頁把真人跟假人分開數，而「誰是假人」任何玩家都不能看到
    （伺服器假人設計第五節）。它現在也走 Cloudflare Tunnel 對外（`monitor.tianxiadashi.com`）：
    隧道來的連線在這裡看起來跟本機一模一樣（cloudflared 跑在同一台），所以擋不了來源，只能擋密碼。"""
    got = (os.environ.get("TIANXIA_MONITOR_PASSWORD") or "").strip()
    if got:
        return got
    if PASSWORD_FILE.exists():
        for line in PASSWORD_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return line
    made = secrets.token_urlsafe(9)
    PASSWORD_FILE.parent.mkdir(parents=True, exist_ok=True)
    note = "# 監控頁的密碼（帳號隨便打）。改這一行就是改密碼，改完要重開 monitor.py。"
    PASSWORD_FILE.write_text(note + chr(10) + made + chr(10), encoding="utf-8")
    return made


def main() -> None:
    sys.path.insert(0, str(ROOT))  # console.py 在 repo 根目錄；它也只用標準庫
    import console

    console.use_utf8()  # 第一件事：cp950 編不出來的字不能把這一頁弄死，log 也固定是 UTF-8
    parser = argparse.ArgumentParser(description="試玩監控頁（唯讀、只聽本機）")
    parser.add_argument("--port", type=int, default=7899)
    parser.add_argument("--db", default=os.environ.get("TIANXIA_DB") or str(ROOT / "saves" / "tianxia.db"))
    args = parser.parse_args()
    db = Path(args.db)
    secret = password()

    class Handler(BaseHTTPRequestHandler):
        def allowed(self) -> bool:
            """HTTP Basic：帳號不管，只比密碼（固定時間比較，免得被試出來）。"""
            got = self.headers.get("Authorization") or ""
            if not got.startswith("Basic "):
                return False
            try:
                raw = base64.b64decode(got[6:], validate=True).decode("utf-8", "replace")
            except ValueError:
                return False
            return hmac.compare_digest(raw.partition(":")[2], secret)

        def do_GET(self) -> None:  # noqa: N802
            if not self.allowed():
                self.send_response(401)
                self.send_header("WWW-Authenticate", 'Basic realm="tianxia monitor", charset="UTF-8"')
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = page(db).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            pass  # 每 10 秒一次更新，不用印

    print("監控頁：http://127.0.0.1:" + str(args.port) + "　資料庫：" + str(db) + "（唯讀）")
    print("對外（隧道）：https://monitor.tianxiadashi.com　帳號隨便打，密碼：" + secret)
    print("有密碼才進得來：這一頁把真人與假人分開數，不能給玩家看到。Ctrl+C 結束。")
    HTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
