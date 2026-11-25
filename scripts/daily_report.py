"""主機端：每天一份玩家數字（2026-11-25，企劃者選「每日備份＋玩家數字」）。只讀不改，伺服器開著跑。

印給企劃者看的兩份：短報（手機一屏看得完，先三行重點：人數、新角色卡最多的那一步、備份成敗）與全文。
- 只算真人（characters.is_bot = 0）；假人只給一個總數。不印名號、帳號、IP：只有數字與鈕的名稱（同 scripts/play_metrics.py 的理由）。
- 真的只讀：sqlite 的唯讀模式（mode=ro）直接開檔，不走 open_database（那一條會照版本跑遷移）、不進行動鎖、不寫任何東西到資料庫。
- 「昨天」是台灣日期（回體丹換日那一天，Game._pill_day 的算法）；--date 給報表那一天（預設今天），數的是前一天。
- 備份成敗讀 scripts/backup_db.py --status 寫的小檔（預設 .local/backup_status.json）；超過 36 小時沒有成功的一份也算失敗。
- 短報貼到 Discord：.local/daily_report.json 寫 {"relay": {"script": <主機轉送 relay.py 的完整路徑>, "channel": <頻道代號>}}
  （主機現有的 Discord 機器人，Joy 2026-11-25 選的；python 預設用跑這支的那一個，可另寫 "python"），或 {"discord_webhook": "<網址>"}；
  兩個都有時走 relay，都沒有就只存檔。短報超過 2,000 字截短並寫「全文在主機」；失敗再試一次，還是失敗結束碼 1（全文照樣存好）。
- 存檔：--out（預設 .local/daily_report/）底下 <日期>.txt（全文）與 latest.txt。

執行：.venv/Scripts/python.exe scripts/daily_report.py [--db <資料庫>] [--date 2026-11-25] [--no-post]
排程與安裝步驟看 scripts/daily_ops/README.md。
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import sqlite3
import subprocess
import sys
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tianxia.database import default_path  # noqa: E402

TAIWAN = dt.timezone(dt.timedelta(hours=8))  # Config.pill_day_utc_offset_hours 的預設
NEW_DAYS = 7  # 「新角色」是幾天內註冊的
GONE_DAYS = 2  # 幾天沒回來算流失
STALE_HOURS = 36  # 備份多久沒成功算失敗
OPENING = ROOT / "tianxia" / "features" / "guide" / "content" / "opening.json"  # 城門口那一則事件（guide 包 opening.pending）
STAGES = ("還在城門口沒選路", "選了路未滿 5 級", "5 到 9 級", "10 級以上")
# 量表上的鈕（playlog.button_of 歸過類的）→ 企劃者看得懂的名字；表外的照原樣印
BUTTONS = {
    "act:explore": "探索", "act:train": "出陣", "act:socialize": "交友", "act:rest": "調息", "act:seclusion": "閉關",
    "act:clinic": "醫館", "act:move": "移動", "move": "移動", "travel": "趕路中的選項", "choice": "事件選項", "talk": "跟人物說話",
    "call": "求見", "battle": "決戰", "duel": "單挑", "arena": "擂台", "shop": "店面", "smith": "鐵匠鋪", "tavern": "酒肆",
    "faction": "投靠", "bounty": "懸賞", "raid": "截殺", "seal": "玉璽碎片", "guard": "親衛", "codex": "江湖錄",
    "yiwen": "異聞", "checkin": "簽到", "mall": "商城", "craft": "煉製", "cultivate": "修練", "sense": "感悟",
}


def taiwan_day(d: dt.date) -> int:
    """台灣日期 → 回體丹換日的那一天（playlog 的 day；play_metrics.day_number 同一個算法）。"""
    start = dt.datetime.combine(d, dt.time(), tzinfo=TAIWAN)
    return int((start.timestamp() + 8 * 3600) // 86400)


def day_window(d: dt.date) -> tuple[float, float]:
    start = dt.datetime.combine(d, dt.time(), tzinfo=TAIWAN).timestamp()
    return start, start + 86400


def ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def has_table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone() is not None


def button_name(button: str) -> str:
    return BUTTONS.get(button, button)


def stage_of(data: dict, opening_event: str | None) -> str:
    if opening_event and data.get("pending_event") == opening_event:
        return STAGES[0]
    level = (data.get("player") or {}).get("level", 1)
    return STAGES[1] if level < 5 else STAGES[2] if level < 10 else STAGES[3]


@dataclass
class Numbers:
    day: dt.date  # 數的是這一天（報表那一天的前一天）
    season: int | None = None
    bots: int = 0
    online: int = 0
    online_week: int = 0
    online_season: int = 0
    registered: int = 0
    reg_before: int = 0  # 前天註冊的
    reg_before_back: int = 0  # 其中昨天又回來的
    retention: dict[int, float | None] = field(default_factory=dict)
    stages: Counter = field(default_factory=Counter)  # 近 7 天註冊的停在哪一步
    gone_last: Counter = field(default_factory=Counter)  # 其中流失的人，最後一天按的鈕
    gone: int = 0
    idle: int = 0  # 昨天上線卻一顆都沒按
    few: int = 0  # 只按 1～3 次
    presses: Counter = field(default_factory=Counter)
    buyers: int = 0
    spent: int = 0
    tickets_new: int | None = None  # 客服旁檔不在是 None
    tickets_open: int | None = None
    backup: dict | None = None
    backup_problem: str = ""


def collect(db: Path, today: dt.date, *, status: Path | None, now: dt.datetime) -> Numbers:
    day = today - dt.timedelta(days=1)
    n = Numbers(day=day)
    yday, start_week = taiwan_day(day), taiwan_day(day - dt.timedelta(days=6))
    lo, hi = day_window(day)
    opening_event = json.loads(OPENING.read_text(encoding="utf-8")).get("event") if OPENING.is_file() else None
    conn = ro(db)
    try:
        chars = {r["key"]: r for r in conn.execute("SELECT key, is_bot, data FROM characters")}
        real = {k for k, r in chars.items() if not r["is_bot"]}
        n.bots = len(chars) - len(real)
        row = conn.execute("SELECT MAX(number) FROM seasons").fetchone()
        n.season = row[0] if row else None
        visits: dict[str, dict[int, Counter]] = {}
        if has_table(conn, "action_counts") and n.season is not None:
            for r in conn.execute("SELECT owner, day, buttons FROM action_counts WHERE season = ?", (n.season,)):
                if r["owner"] in real:
                    visits.setdefault(r["owner"], {})[r["day"]] = Counter(json.loads(r["buttons"] or "{}"))
        n.online_season = len(visits)
        n.online_week = sum(1 for v in visits.values() if any(start_week <= d <= yday for d in v))
        for v in visits.values():
            if yday in v:
                n.online += 1
                pressed = sum(v[yday].values())
                n.idle += pressed == 0
                n.few += 1 <= pressed <= 3
                n.presses.update(v[yday])
        if visits:
            first = min(d for v in visits.values() for d in v)
            on_first = [v for v in visits.values() if first in v]
            for k in (3, 7):
                n.retention[k] = (sum(1 for v in on_first if max(v) >= first + k - 1) / len(on_first)) if on_first and yday >= first + k - 1 else None
        accounts = conn.execute("SELECT character_key, created FROM accounts").fetchall()
        new_lo = day_window(day - dt.timedelta(days=NEW_DAYS - 1))[0]
        before_lo, before_hi = day_window(day - dt.timedelta(days=1))
        for a in accounts:
            key, created = a["character_key"], a["created"]
            if key not in real:
                continue
            if lo <= created < hi:
                n.registered += 1
            if before_lo <= created < before_hi:
                n.reg_before += 1
                n.reg_before_back += yday in visits.get(key, {})
            if new_lo <= created < hi:
                try:
                    data = json.loads(chars[key]["data"])
                except (TypeError, ValueError):
                    continue
                n.stages[stage_of(data, opening_event)] += 1
                seen = visits.get(key, {})
                last = max(seen, default=None)
                if created < day_window(day - dt.timedelta(days=GONE_DAYS - 1))[0] and (last is None or last <= yday - GONE_DAYS):
                    n.gone += 1
                    if last is not None:
                        n.gone_last.update(seen[last])
        if has_table(conn, "mall_ledger"):
            rows = conn.execute("SELECT owner, delta FROM mall_ledger WHERE reason = 'buy' AND time >= ? AND time < ?", (lo, hi)).fetchall()
            rows = [r for r in rows if r["owner"] in real]
            n.buyers = len({r["owner"] for r in rows})
            n.spent = -sum(r["delta"] for r in rows)
    finally:
        conn.close()
    support = Path(db).with_name(f"{Path(db).stem}-support.sqlite")
    if support.is_file():
        s = ro(support)
        try:
            if has_table(s, "tickets"):
                n.tickets_new = s.execute("SELECT COUNT(*) FROM tickets WHERE created >= ? AND created < ?", (lo, hi)).fetchone()[0]
                n.tickets_open = s.execute("SELECT COUNT(*) FROM tickets WHERE status != 'closed'").fetchone()[0]
        finally:
            s.close()
    n.backup, n.backup_problem = backup_state(status, now)
    return n


def backup_state(status: Path | None, now: dt.datetime) -> tuple[dict | None, str]:
    if status is None or not Path(status).is_file():
        return None, "沒有備份紀錄（每日備份的排程還沒裝？）"
    try:
        got = json.loads(Path(status).read_text(encoding="utf-8"))
        when = dt.datetime.fromisoformat(got["time"])
    except (OSError, ValueError, KeyError) as e:
        return None, f"備份紀錄讀不懂（{e}）"
    if not got.get("ok"):
        return got, f"{when:%m/%d %H:%M} 那次失敗：{got.get('error', '')[:120]}"
    if now - when > dt.timedelta(hours=STALE_HOURS):
        return got, f"最後一次成功是 {when:%m/%d %H:%M}，已經超過 {STALE_HOURS} 小時"
    return got, ""


def pct(a: int, b: int) -> str:
    return f"{a / b:.0%}" if b else "—"


def top(counter: Counter, k: int) -> str:
    return "、".join(f"{button_name(b)} {c}" for b, c in counter.most_common(k)) or "沒有"


def render(n: Numbers, today: dt.date) -> tuple[str, str]:
    """回（短報, 全文）。短報先三行重點，失敗時第一行就寫失敗。"""
    head = f"【天下大勢　每日數字 {today.month}/{today.day}】（數的是 {n.day.month}/{n.day.day}）"
    if n.backup_problem:
        backup_line = f"⚠ 備份失敗：{n.backup_problem}"
    else:
        b = n.backup or {}
        backup_line = f"・備份：成功 {dt.datetime.fromisoformat(b['time']):%m/%d %H:%M}，{b.get('bytes', 0) / 1e6:.1f} MB" + (
            f"，另開一份讀得回 {b['characters']} 個角色" if b.get("characters") is not None else "")
    people = f"・昨天上線 {n.online} 人（近 7 天 {n.online_week}、這一季 {n.online_season}）；假人 {n.bots}"
    if n.stages:
        stage, cnt = n.stages.most_common(1)[0]
        stuck = f"・新角色（近 {NEW_DAYS} 天 {sum(n.stages.values())} 人）最多停在：{stage} {cnt} 人"
    else:
        stuck = f"・近 {NEW_DAYS} 天沒有新角色"
    key = [backup_line, people, stuck] if n.backup_problem else [people, stuck, backup_line]
    rest = [
        f"新註冊 {n.registered} 人；前天註冊 {n.reg_before} 人，昨天回來 {n.reg_before_back}（{pct(n.reg_before_back, n.reg_before)}）",
        "這一季留存：" + "、".join(f"第 {k} 天 {'—' if v is None else f'{v:.0%}'}" for k, v in sorted(n.retention.items())) if n.retention else "這一季留存：還沒有紀錄",
        f"上線卻沒按鈕 {n.idle} 人；只按 1～3 次 {n.few} 人；平均每人 {sum(n.presses.values()) / n.online:.0f} 次" if n.online else "昨天沒有人上線",
        f"按最多：{top(n.presses, 5)}",
        f"商城：{n.buyers} 人買、花 {n.spent} 元寶",
        "客服：還沒有單" if n.tickets_new is None else f"客服：新單 {n.tickets_new}、沒結 {n.tickets_open}",
    ]
    short = "\n".join([head, *key, "——", *rest])
    stages = "、".join(f"{s} {n.stages[s]}" for s in STAGES if n.stages[s]) or "沒有"
    full = "\n".join([
        short, "", "【細項】",
        f"新角色停在哪一步（近 {NEW_DAYS} 天註冊）：{stages}",
        f"其中 {GONE_DAYS} 天以上沒回來 {n.gone} 人，最後一天按的：{top(n.gone_last, 8)}",
        f"昨天按鈕前 10：{top(n.presses, 10)}",
        f"（只算真人；第 {n.season} 季；不列名號）",
    ])
    return short, full


DISCORD_MAX = 2000  # Discord 一則上限；超過就截短，不讓轉送切成好幾則
CUT_NOTE = "\n…（全文在主機）"


def fit(text: str, limit: int = DISCORD_MAX) -> str:
    return text if len(text) <= limit else text[: limit - len(CUT_NOTE)] + CUT_NOTE


def relay(cfg: dict, text: str, *, tries: int = 2) -> str:
    """走主機現有的 Discord 機器人轉送（Joy 2026-11-25 選的）：python relay.py send <頻道> -，文字從 stdin 給 UTF-8。
    失敗最多再試一次；兩次都失敗丟 OSError。回轉送印的字。"""
    py = cfg.get("python") or sys.executable
    cmd = [py, str(cfg["script"]), "send", str(cfg["channel"]), "-"]
    last = ""
    for _ in range(tries):
        try:
            done = subprocess.run(cmd, input=fit(text).encode("utf-8"), capture_output=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as e:
            last = str(e)
            continue
        out = done.stdout.decode("utf-8", errors="replace").strip()
        if done.returncode == 0:
            return out
        last = (done.stderr.decode("utf-8", errors="replace").strip() or out or f"結束碼 {done.returncode}")[:300]
    raise OSError(f"轉送失敗（試了 {tries} 次）：{last}")


def post(webhook: str, text: str) -> None:
    body = json.dumps({"content": fit(text), "allowed_mentions": {"parse": []}}).encode("utf-8")
    req = urllib.request.Request(webhook, data=body, headers={"Content-Type": "application/json", "User-Agent": "tianxia-daily-report"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        resp.read()


def main(argv: list[str] | None = None) -> int:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="每天一份玩家數字（只讀）")
    parser.add_argument("--db", type=Path, default=None, help="資料庫檔（預設照 TIANXIA_DB 或 saves/tianxia.db）")
    parser.add_argument("--date", default=None, help="報表那一天（台灣日期 YYYY-MM-DD；預設今天），數的是前一天")
    parser.add_argument("--status", type=Path, default=ROOT / ".local" / "backup_status.json", help="backup_db.py --status 寫的檔")
    parser.add_argument("--config", type=Path, default=ROOT / ".local" / "daily_report.json", help="放 discord_webhook 的檔")
    parser.add_argument("--out", type=Path, default=ROOT / ".local" / "daily_report", help="全文存在哪個資料夾")
    parser.add_argument("--no-post", action="store_true", help="不貼 Discord，只印與存檔")
    args = parser.parse_args(argv)
    now = dt.datetime.now(TAIWAN).replace(tzinfo=None)
    today = dt.date.fromisoformat(args.date) if args.date else now.date()
    path = args.db or default_path()
    try:
        numbers = collect(path, today, status=args.status, now=now)
    except sqlite3.Error as e:
        print(f"打不開資料庫 {path}：{e}")
        return 1
    short, full = render(numbers, today)
    print(full)
    try:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / f"{today.isoformat()}.txt").write_text(full + "\n", encoding="utf-8")
        (args.out / "latest.txt").write_text(full + "\n", encoding="utf-8")
    except OSError as e:
        print(f"全文存不進去：{args.out}（{e}）", file=sys.stderr)
    if args.no_post:
        return 0
    try:
        cfg = json.loads(args.config.read_text(encoding="utf-8")) if args.config.is_file() else {}
    except (OSError, ValueError) as e:
        print(f"{args.config} 讀不懂（{e}），這次不貼", file=sys.stderr)
        return 1
    via = cfg.get("relay") or {}
    if via.get("script") and via.get("channel"):
        try:
            relay(via, short)
        except OSError as e:
            print(f"貼不到 Discord：{e}", file=sys.stderr)
            return 1
    elif cfg.get("discord_webhook"):
        try:
            post(cfg["discord_webhook"], short)
        except OSError as e:
            print(f"貼不到 Discord：{e}", file=sys.stderr)
            return 1
    else:
        print(f"沒設 relay 或 discord_webhook（{args.config}），只存檔")
        return 0
    print("已貼到 Discord")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
