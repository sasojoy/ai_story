"""主機端：真人量表的總數（減法季批 0，設計稿第十章；tianxia/playlog.py、資料庫第 7 版）。只讀不改。

印一季的：幾個帳號、第 3 天與第 7 天的留存（判準【預設】五成、四成）、第幾天不再上線的分布、每顆鈕佔每天行動的幾成、
第一次寫隨口應對與第一次跟人物說話是第幾天（中位數與還沒做過的人數）。只印總數、不印名號：表上只有真人，
列出名號等於從缺席看出誰是假人。
執行：.venv/Scripts/python.exe scripts/play_metrics.py [--season N] [--start 2026-10-25]（沒給 --db 就照 TIANXIA_DB 或 saves/tianxia.db）
--start 是季的第 1 天（台灣日期）；沒給就用這一季最早有人上線的那一天。

真的只讀：用 sqlite 的唯讀模式（mode=ro）直接開檔，不走 open_database（那一條會照版本跑遷移）。第 7 版以前的檔沒有量表，印一句就結束。
"""
from __future__ import annotations

import argparse
import io
import sqlite3
import statistics
import sys
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tianxia.database import default_path  # noqa: E402
from tianxia.playlog import FIGURE_TALK, FIRSTS, FREE_TEXT, PlayLog, last_days, retention  # noqa: E402

PLAY_SCHEMA = 7  # 量表的兩張表是第 7 版加的（database.SCHEMA_V7_TABLES）
TARGETS = {3: 0.5, 7: 0.4}  # 判準【預設】：第 3 天留存五成、第 7 天四成
ENCOUNTER_MAX = 0.4  # 判準【預設】：遭遇佔每日行動不超過四成（遭遇算哪幾顆鈕，等批 2 的探索一顆定了再接）
FIRST_NAMES = {FREE_TEXT: "第一次寫隨口應對", FIGURE_TALK: "第一次跟人物說話"}
TAIWAN = 8  # Config.pill_day_utc_offset_hours 的預設：回體丹換日的時區


class ReadOnly:
    """唯讀地開一個資料庫檔，只給 PlayLog 要的 snapshot()。開不了丟 sqlite3.Error。"""

    def __init__(self, path: Path):
        self.conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        self.conn.row_factory = sqlite3.Row
        self.version = self.conn.execute("PRAGMA user_version").fetchone()[0]

    @contextmanager
    def snapshot(self) -> Iterator[sqlite3.Connection]:
        yield self.conn


def day_number(text: str, offset_hours: float = TAIWAN) -> int:
    """台灣日期（YYYY-MM-DD）→ 回體丹換日的那一天（Game._pill_day 的算法：1970-01-01 起算）。"""
    start = datetime.combine(date.fromisoformat(text), datetime.min.time(), tzinfo=timezone(timedelta(hours=offset_hours)))
    return int((start.timestamp() + offset_hours * 3600) // 86400)


def report(db: ReadOnly, season: int | None, start: int | None) -> list[str]:
    if season is None:
        row = db.conn.execute("SELECT MAX(season) FROM play_days").fetchone()
        season = row[0]
        if season is None:
            return ["量表還是空的：還沒有真人上線過。"]
    accounts = PlayLog(db).accounts(season, start_day=start)
    lines = [f"第 {season} 季：{len(accounts)} 個帳號上線過"]
    if not accounts:
        return lines
    for day, target in TARGETS.items():
        got = retention(accounts, day)
        mark = "—" if got is None else f"{got:.0%}（判準 {target:.0%}，{'過' if got >= target else '未過'}）"
        lines.append(f"第 {day} 天留存：{mark}")
    lines.append("第幾天不再上線：" + "、".join(f"第 {d} 天 {n} 人" for d, n in sorted(last_days(accounts).items())))
    per_day: Counter = Counter()
    total = 0
    for a in accounts:
        per_day.update(a.buttons)
        total += sum(a.buttons.values())
    if total:
        days = sum(len(a.days) for a in accounts)
        lines.append(f"按鈕：共 {total} 次，平均每人每天 {total / days:.1f} 次（遭遇的判準 ≤{ENCOUNTER_MAX:.0%}，等探索一顆定了再算）")
        lines.extend(f"  {button}：{n} 次（{n / total:.0%}）" for button, n in per_day.most_common())
    for kind in FIRSTS:
        got = [a.firsts[kind] for a in accounts if kind in a.firsts]
        mid = f"中位數第 {statistics.median(got):g} 天" if got else "沒有人"
        lines.append(f"{FIRST_NAMES[kind]}：{len(got)} 人，{mid}；還沒做過 {len(accounts) - len(got)} 人")
    return lines


def main(argv: list[str] | None = None) -> int:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # cp950 的主控台印中文不噴錯
    parser = argparse.ArgumentParser(description="真人量表的總數（只讀）")
    parser.add_argument("--db", type=Path, default=None, help="資料庫檔（預設照 TIANXIA_DB 或 saves/tianxia.db）")
    parser.add_argument("--season", type=int, default=None, help="第幾季（預設最新有紀錄的那一季）")
    parser.add_argument("--start", default=None, help="季的第 1 天（台灣日期 YYYY-MM-DD；預設這一季最早有人上線的那一天）")
    args = parser.parse_args(argv)
    path = args.db or default_path()
    try:
        db = ReadOnly(path)
    except sqlite3.Error as e:
        print(f"打不開資料庫 {path}：{e}")
        return 1
    if db.version < PLAY_SCHEMA:
        print(f"資料庫是第 {db.version} 版，還沒有真人量表（第 {PLAY_SCHEMA} 版起才有）。")
        return 0
    start = day_number(args.start) if args.start else None
    print("\n".join(report(db, args.season, start)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
